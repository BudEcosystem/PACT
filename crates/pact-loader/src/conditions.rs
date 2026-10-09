//! **One condition grammar, read by one function** (02W §2.6, §3, F1 reopened).
//!
//! An approval rule's `when:`, a routing rule's `when:`, a repeat's `until:`
//! and a port's `only-when:` all write `when-this` lines, and every line is
//! held here by [`line`], so the same mistake gets the same words wherever it
//! is written (`one_grammar_for_every_condition`). Python's
//! `pact_adapters.conditions.holds` is the run-time half, and reads the lines
//! this lets through the same way.
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/compared-in-the-wrong-shape` | WF-18 (extended) | a line compares a value with a figure of another shape (money with a date, a score with money), looks at both `tool:` and `value:` or at neither, looks at the wrong one for where it is written (`tool:` in an approval rule, `value:` everywhere else), compares an argument it never names, or, in an approval rule, compares with `{value: ...}`, `{now-plus: ...}` or `{now-minus: ...}` (a gate has only the call) |
//! | `loader/a-label-with-nowhere-to-go` | WF-15 (rules half) | a routing rule chooses a label its stage's `chooses-between:` does not have |
//! | `loader/a-decide-that-can-run-out-of-rungs` | WF-16 (rules half) | a `decide`'s last rung is written rules and none of them is an "otherwise" (a rule with no `when:`), or it has no rung at all |
//!
//! A line's shape is known where what it looks at is declared: an argument's
//! line under its action's `takes:`, a binding's under the workflow's
//! `accepts:` or the answer of the stage it reads (`bindings.rs` resolves it),
//! `used.<ceiling>` a percentage, `now-plus:`/`now-minus:` a date. Where the
//! shape cannot be known before a run, nothing is refused. A figure that is no
//! figure at all is `money.rs`'s `loader/threshold-is-not-a-figure`, told once.

use crate::bindings::Shapes;
use crate::money::{add_a_currency_to, is_a_currency_code, no_figure_in};
use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node, Value};
use pact_schema::shape::Shape;
use pact_schema::{Schema, suggest};

/// The six condition words, in 03's order.
pub(crate) const WORDS: &[&str] = &[
    "is",
    "is-one-of",
    "more-than",
    "less-than",
    "contains-any-of",
    "is-empty",
];

/// What a value, or a figure written against it, is — as far as comparing goes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Kind {
    Money,
    Percent,
    Number,
    Date,
    Time,
    YesNo,
    Text,
    List,
    Record,
}

impl Kind {
    fn said(self) -> &'static str {
        match self {
            Kind::Money => "an amount of money",
            Kind::Percent => "a percentage",
            Kind::Number => "a number",
            Kind::Date => "a date",
            Kind::Time => "a time of day",
            Kind::YesNo => "a yes or no",
            Kind::Text => "some text",
            Kind::List => "a list",
            Kind::Record => "a record with parts",
        }
    }

    /// What to write against a value of this kind.
    fn example(self) -> &'static str {
        match self {
            Kind::Money => "an amount of money, with the currency after it, like `200 USD`",
            Kind::Percent => "a percentage, like `80%`",
            Kind::Number => "a bare number, like `80`, with no currency after it",
            Kind::Date => "a date, like `2026-10-09`, or `{now-plus: 14 days}`",
            Kind::Time => "a time of day, like `14:30`",
            Kind::YesNo => "`yes` or `no`",
            Kind::Text | Kind::List | Kind::Record => "a word, like `enterprise`",
        }
    }

    /// The kinds a figure can be written in.
    fn is_a_figure(self) -> bool {
        matches!(
            self,
            Kind::Money | Kind::Percent | Kind::Number | Kind::Date | Kind::Time
        )
    }
}

/// The kind of a value in this shape, when comparing can know it.
pub(crate) fn of_shape(shape: &Shape) -> Option<Kind> {
    Some(match shape {
        Shape::Plain(name) => match name.as_str() {
            "money" => Kind::Money,
            "number" | "whole-number" => Kind::Number,
            "date" | "date-and-time" => Kind::Date,
            "time" => Kind::Time,
            "yes-or-no" => Kind::YesNo,
            "text" | "agent" => Kind::Text,
            _ => return None,
        },
        Shape::OneOf(_) => Kind::Text,
        Shape::ListOf(_) => Kind::List,
        Shape::Named(_) => Kind::Record,
    })
}

/// Whether `written` begins as an ISO 8601 date does (`2026-10-09`).
fn looks_like_a_date(written: &str) -> bool {
    let b = written.trim().as_bytes();
    b.len() >= 10
        && b[..4].iter().all(u8::is_ascii_digit)
        && b[4] == b'-'
        && b[5..7].iter().all(u8::is_ascii_digit)
        && b[7] == b'-'
        && b[8..10].iter().all(u8::is_ascii_digit)
}

/// Whether `written` is a time of day (`14:30`, `9:05`, `14:30:15`): the
/// spelling `pact_adapters.conditions` reads as one, so a time is compared
/// with a time, never by its hour as a number.
pub(crate) fn looks_like_a_time(written: &str) -> bool {
    let parts: Vec<&str> = written.trim().split(':').collect();
    let below = |p: &str, digits: std::ops::RangeInclusive<usize>, limit: u32| {
        digits.contains(&p.len())
            && p.bytes().all(|b| b.is_ascii_digit())
            && p.parse::<u32>().is_ok_and(|n| n < limit)
    };
    (2..=3).contains(&parts.len())
        && below(parts[0], 1..=2, 24)
        && below(parts[1], 2..=2, 60)
        && parts.get(2).is_none_or(|s| below(s, 2..=2, 60))
}

/// Whether `written` is compared as a moment rather than a figure: a date
/// (with or without its clock time) or a time of day.
pub(crate) fn looks_like_a_date_or_time(written: &str) -> bool {
    looks_like_a_date(written) || looks_like_a_time(written)
}

/// The kind of a figure as written: `5000 USD`, `85%`, `0.85`, `2026-10-09`,
/// `14:30`, `yes`. `None` for a word that is no figure (`enterprise`).
fn of_written(node: &Node) -> Option<Kind> {
    let written = match &node.value {
        Value::Int(_) | Value::Float(_) => return Some(Kind::Number),
        Value::Bool(_) => return Some(Kind::YesNo),
        Value::Str(s) => s.trim(),
        _ => return None,
    };
    if looks_like_a_date(written) {
        return Some(Kind::Date);
    }
    if looks_like_a_time(written) {
        return Some(Kind::Time);
    }
    if matches!(
        written.to_ascii_lowercase().as_str(),
        "yes" | "no" | "true" | "false" | "on" | "off" | "y" | "n" | "enabled" | "disabled"
    ) {
        return Some(Kind::YesNo);
    }
    if no_figure_in(written).is_some() {
        return None;
    }
    // Money is written with its currency after the figure, or `$` before it
    // (`USD 200` is refused with the spelling to write instead, as it was).
    let money = written.starts_with('$')
        || written.split_whitespace().count() > 1
            && written
                .split_whitespace()
                .last()
                .is_some_and(is_a_currency_code);
    Some(if money {
        Kind::Money
    } else if written.ends_with('%') {
        Kind::Percent
    } else {
        Kind::Number
    })
}

/// Where a line is written: an approval rule looks at a call, every other
/// position at a value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Position {
    Policy,
    Elsewhere,
}

/// Every check one `when-this` line answers to, wherever it is written.
///
/// `left` is the kind of what the line looks at, when that is known where it
/// is declared; `binding` gives the kind of a `{value: <binding>}` comparand.
pub(crate) fn line(
    when: &Node,
    position: Position,
    left: Option<Kind>,
    binding: &dyn Fn(&Node) -> Option<Kind>,
    diags: &mut Diagnostics,
) {
    let Some(map) = when.as_map() else { return };
    let (tool, value) = (map.get("tool"), map.get("value"));
    let wrong = |message: String, fix: &str| {
        Diagnostic::error(
            "loader/compared-in-the-wrong-shape",
            when.span.clone(),
            message,
            fix.to_string(),
        )
    };
    match (tool, value, position) {
        (Some(_), Some(_), _) => {
            diags.push(wrong(
                "This condition looks at a call's argument (`tool:`) and at a value (`value:`) \
                 at once, so nothing says which one it compares."
                    .to_string(),
                "Write exactly one of the two: `tool:` in an approval rule, `value:` everywhere \
                 else.",
            ));
            return;
        }
        (None, None, _) => {
            diags.push(wrong(
                "This condition looks at nothing — no `tool:` and no `value:` — so it can never \
                 hold."
                    .to_string(),
                "Write exactly one of the two: `tool:` in an approval rule, `value:` everywhere \
                 else.",
            ));
            return;
        }
        (None, Some(_), Position::Policy) => {
            diags.push(wrong(
                "An approval rule is about a call, and this condition looks at a value \
                 (`value:`) instead of the call, so no call is ever stopped by it."
                    .to_string(),
                "Name the call — `tool: <tool>/<action>`, with `arg:` for the argument to \
                 look at.",
            ));
            return;
        }
        (Some(_), None, Position::Elsewhere) => {
            diags.push(wrong(
                "This condition looks at a call's argument (`tool:`), and nothing here is a \
                 call: a routing rule, an `until:` and a port's `only-when:` look at values."
                    .to_string(),
                "Write `value:` instead, naming what to look at — `value: \
                 steps.<stage>.<field>`.",
            ));
            return;
        }
        _ => {}
    }
    let word = WORDS.iter().copied().find(|w| map.contains_key(*w));
    let arg = map.get("arg").and_then(|e| e.node.as_str()).map(str::trim);
    if value.is_some() && map.contains_key("arg") {
        diags.push(wrong(
            "`arg:` names an argument of a call, and this condition looks at a value, which \
             has no arguments."
                .to_string(),
            "Delete `arg:`; `value:` already says what to look at.",
        ));
        return;
    }
    if let (Some(word), None, Some(_)) = (word, arg, tool) {
        diags.push(wrong(
            format!(
                "`{word}:` compares an argument of the call, and this rule names none, so \
                 nothing is compared."
            ),
            "Add `arg:` naming the argument to look at — one of the names under the action's \
             `takes:`.",
        ));
        return;
    }
    // A gate decides at the call, from the call: there is no other value for
    // it to read and no journaled clock to count from, so a `{value: ...}` or
    // `{now-plus: ...}` there would stop every call and ask.
    if let (Some(word), Position::Policy) = (word, position)
        && let Some(written) = map.get(word).filter(|e| e.node.as_map().is_some())
    {
        diags.push(Diagnostic::error(
            "loader/compared-in-the-wrong-shape",
            written.node.span.clone(),
            format!(
                "An approval rule compares the call's argument with a figure written here, and \
                 `{word}:` names something else to compare with — a gate has no other value to \
                 read and no clock to count from, so every call would stop and ask."
            ),
            format!("Write the figure itself — `{word}: 200 USD`, `{word}: 80`."),
        ));
        return;
    }
    let (Some(word), Some(left)) = (word, left) else {
        return;
    };
    let looked_at = arg
        .or_else(|| value.and_then(|e| e.node.as_str()).map(str::trim))
        .unwrap_or("");
    let figure = &map.get(word).expect("the word is written").node;
    let wrote = |n: &Node| match &n.value {
        Value::Str(s) => s.trim().to_string(),
        Value::Int(i) => i.to_string(),
        Value::Float(f) => f.to_string(),
        Value::Bool(b) => b.to_string(),
        _ => n
            .as_map()
            .and_then(|m| m.iter().next())
            .map_or_else(String::new, |(k, e)| {
                format!("{{{k}: {}}}", e.node.as_str().map(str::trim).unwrap_or("…"))
            }),
    };
    let mismatch = |right: Option<Kind>| -> Option<Kind> {
        let right = right?;
        let refused = match word {
            "more-than" | "less-than" => match left {
                // Text keeps its old reading: only money against it is refused.
                Kind::Text => right == Kind::Money,
                Kind::YesNo | Kind::List | Kind::Record => true,
                _ => right != left,
            },
            "is" | "is-one-of" => left.is_a_figure() && right.is_a_figure() && right != left,
            _ => false,
        };
        refused.then_some(right)
    };
    let kind_of = |n: &Node| -> Option<Kind> {
        match n.as_map() {
            Some(m) if m.contains_key("value") => binding(&m.get("value")?.node),
            Some(m) if m.contains_key("now-plus") || m.contains_key("now-minus") => {
                Some(Kind::Date)
            }
            Some(_) => None,
            None => of_written(n),
        }
    };
    if word == "contains-any-of" {
        if matches!(left, Kind::Text | Kind::List) {
            return;
        }
        diags.push(wrong(
            format!(
                "`{looked_at}` is {} and `contains-any-of:` looks for words in text or a list — \
                 so the condition compares two different kinds of thing.",
                left.said()
            ),
            &format!(
                "Compare it with `is:`, `more-than:` or `less-than:`, written as {}.",
                left.example()
            ),
        ));
        return;
    }
    let figures: Vec<&Node> = match &figure.value {
        Value::List(items) => items.iter().collect(),
        _ => vec![figure],
    };
    for f in figures {
        // A figure that is no figure is `money.rs`'s to tell, once.
        if matches!(word, "more-than" | "less-than")
            && f.as_str()
                .is_some_and(|s| !looks_like_a_date_or_time(s) && no_figure_in(s).is_some())
        {
            continue;
        }
        let Some(right) = mismatch(kind_of(f)) else {
            continue;
        };
        let written = wrote(f);
        let fix = if left == Kind::Money && right == Kind::Number && f.as_map().is_none() {
            add_a_currency_to(&written)
        } else {
            format!(
                "Write the figure the way `{looked_at}` is — {}.",
                left.example()
            )
        };
        diags.push(Diagnostic::error(
            "loader/compared-in-the-wrong-shape",
            f.span.clone(),
            format!(
                "`{looked_at}` is {} and `{word}: {written}` is {} — so the condition compares \
                 two different kinds of thing.",
                left.said(),
                right.said()
            ),
            fix,
        ));
        return;
    }
}

/// Every approval rule's lines, each held by [`line`], with the argument's
/// shape read off its action's `takes:`.
pub fn check(document: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let shapes = Shapes::of(document, schema);
    let tools = document.get("tools");
    for (_, policy) in document
        .get("policies")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let rules = policy.node.get("ask-a-person").and_then(Node::as_list);
        for rule in rules.into_iter().flatten() {
            let whens = rule.get("when").and_then(Node::as_list);
            for when in whens.into_iter().flatten() {
                let left = (|| {
                    let named = when.get("tool")?.as_str()?.trim();
                    let (tool, action) = named.split_once('/')?;
                    let declared = tools?
                        .get(tool.trim())?
                        .get("actions")?
                        .get(action.trim())?
                        .get("takes")?
                        .get(when.get("arg")?.as_str()?.trim())?;
                    of_shape(&shapes.line(declared)?.shape)
                })();
                line(when, Position::Policy, left, &|_| None, diags);
            }
        }
    }
}

/// A `decide` stage's rules rung: every label it chooses is one of its
/// `chooses-between:` (WF-15), and the last rung decides every case (WF-16).
pub(crate) fn decides(stage: &str, fields: &Map, at: &Node, diags: &mut Diagnostics) {
    let labels: Vec<&str> = fields
        .get("chooses-between")
        .and_then(|e| e.node.as_map())
        .map(|m| m.keys().map(String::as_str).collect())
        .unwrap_or_default();
    let first = labels.first().copied().unwrap_or("<label>");
    let rungs = fields.get("by").and_then(|e| e.node.as_list());
    for rung in rungs.into_iter().flatten() {
        let rules = rung.get("rules").and_then(Node::as_list);
        for rule in rules.into_iter().flatten() {
            let Some(choose) = rule.as_map().and_then(|m| m.get("choose")) else {
                continue;
            };
            let Some(label) = choose.node.as_str().map(str::trim) else {
                continue;
            };
            if labels.is_empty() || labels.contains(&label) {
                continue;
            }
            let near = suggest::nearest(label, &labels, 3)
                .iter()
                .map(|n| format!("`{n}`"))
                .collect::<Vec<_>>()
                .join(", ");
            diags.push(Diagnostic::error(
                "loader/a-label-with-nowhere-to-go",
                choose.node.span.clone(),
                format!(
                    "A rule of '{stage}' chooses '{label}', and '{stage}' chooses between {} — \
                     so when this rule holds, the run has nowhere to go.",
                    labels
                        .iter()
                        .map(|l| format!("'{l}'"))
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
                format!(
                    "Choose one of the labels offered: {near} — or add `{label}: <stage>` under \
                     `chooses-between:`."
                ),
            ));
        }
    }
    let last = rungs.and_then(|r| r.last());
    let otherwise = |rules: &[Node]| {
        rules.last().is_some_and(|r| {
            r.get("when")
                .and_then(Node::as_list)
                .is_none_or(<[Node]>::is_empty)
        })
    };
    let (span, said, fix) = match last {
        None => (
            fields
                .get("does")
                .map_or_else(|| at.span.clone(), |e| e.node.span.clone()),
            format!("'{stage}' decides with no rung at all, so nothing ever picks a label."),
            format!(
                "Add `by:` with written rules that end in an \"otherwise\", a rule with no \
                 `when:` — `by: [{{rules: [{{choose: {first}}}]}}]`."
            ),
        ),
        Some(rung) => match rung.get("rules").and_then(Node::as_list) {
            Some(rules) if !otherwise(rules) => (
                rung.span.clone(),
                format!(
                    "'{stage}' ends with written rules, and every one of them has a `when:` — so \
                     a case none of them fits is decided by nobody and the run stops there."
                ),
                format!(
                    "End with an \"otherwise\" rule — a last rule with no `when:`, `- choose: \
                     {first}` — so every case has a label."
                ),
            ),
            _ => return,
        },
    };
    diags.push(Diagnostic::error(
        "loader/a-decide-that-can-run-out-of-rungs",
        span,
        said,
        fix,
    ));
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn node(text: &str) -> Node {
        parse_yaml(text, camino::Utf8Path::new("conditions-test.yaml")).expect("parses")
    }

    fn said(text: &str, position: Position, left: Option<Kind>) -> Vec<String> {
        let mut d = Diagnostics::new();
        line(&node(text), position, left, &|_| None, &mut d);
        d.items()
            .iter()
            .map(|x| format!("{}: {}", x.rule, x.message))
            .collect()
    }

    #[test]
    fn a_figure_is_read_as_the_kind_it_is_written_in() {
        for (written, kind) in [
            ("v: 5000 USD", Some(Kind::Money)),
            ("v: $25", Some(Kind::Money)),
            ("v: 85%", Some(Kind::Percent)),
            ("v: 0.85", Some(Kind::Number)),
            ("v: '1,000'", Some(Kind::Number)),
            ("v: 2026-10-09", Some(Kind::Date)),
            ("v: 14:30", Some(Kind::Time)),
            ("v: '9:05'", Some(Kind::Time)),
            ("v: 14:30:15", Some(Kind::Time)),
            ("v: 25:00", None),
            ("v: yes", Some(Kind::YesNo)),
            ("v: enterprise", None),
            ("v: USD 200", Some(Kind::Number)),
        ] {
            let doc = node(written);
            assert_eq!(of_written(doc.get("v").unwrap()), kind, "{written}");
        }
    }

    #[test]
    fn a_comparison_with_no_argument_to_compare_is_refused() {
        let got = said("{ tool: t/a, is: x }", Position::Policy, None);
        assert_eq!(got.len(), 1, "{got:?}");
        assert!(
            got[0].contains("`is:` compares an argument of the call"),
            "{got:?}"
        );
    }

    #[test]
    fn an_argument_on_a_value_line_is_refused() {
        let got = said(
            "{ value: input.x, arg: y, is: x }",
            Position::Elsewhere,
            None,
        );
        assert_eq!(got.len(), 1, "{got:?}");
        assert!(
            got[0].contains("`arg:` names an argument of a call"),
            "{got:?}"
        );
    }

    #[test]
    fn a_line_whose_shape_is_not_known_is_left_alone() {
        assert!(
            said(
                "{ value: input.x, less-than: 5000 USD }",
                Position::Elsewhere,
                None
            )
            .is_empty()
        );
        assert!(
            said(
                "{ value: input.x, is: 3 }",
                Position::Elsewhere,
                Some(Kind::Text)
            )
            .is_empty()
        );
    }

    #[test]
    fn a_yes_or_no_has_no_order() {
        let got = said(
            "{ value: input.ok, more-than: 3 }",
            Position::Elsewhere,
            Some(Kind::YesNo),
        );
        assert!(
            got[0].contains("`input.ok` is a yes or no and `more-than: 3` is a number"),
            "{got:?}"
        );
    }
}
