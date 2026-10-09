//! **A name no model can call.**
//!
//! Every model provider holds a callable name to `^[a-zA-Z0-9_-]{1,64}$` and
//! refuses the request — not the call, the whole request — when one does not
//! match. Nothing anywhere held PACT's names to that shape, and PACT's names go
//! onto the wire untouched: `harness.py` builds the model's tool list from
//! `spec.tools` and `spec.team`, and both carry the author's key verbatim
//! (`ir.py` lowers `for n, t in sorted(doc["tools"].items())` into
//! `ToolSpec(name=n, ...)`, and `team` the same way one line down).
//!
//! Measured on a copy of `examples/refund-desk` with `tools/Get Weather.yaml`
//! added and `- Get Weather` appended to the agent's `uses:` list:
//!
//! ```text
//! $ pact check <copy>
//! OK — <copy> loaded cleanly (497 settings).
//! $ echo $?
//! 0
//! ```
//!
//! …and the lowered payload read `{'name': 'Get Weather'}`. So `pact check`
//! passed a workspace whose *first* model call is a guaranteed provider refusal,
//! before a single token was spent, for a reason the author cannot see anywhere
//! in the tree.
//!
//! # Why the rule here is narrower than the providers'
//!
//! The providers allow capitals; this refuses them. Decision D2 is the reason:
//! the tree is the native form, so one of these names is a **file or folder
//! name**, and `tools/Payments.yaml` beside `tools/payments.yaml` is two tools
//! on Linux and one file on macOS and Windows. A workspace that loads on the
//! author's machine and collapses on the reviewer's is the silent loss T7
//! forbids, and D18 puts four surfaces — editor, UI, builder agent, git review —
//! on the same files. A leading `-` is a list item in YAML and needs quoting to
//! be a name at all.
//!
//! Every name that passes here passes every provider. A name that passes the
//! providers and fails here is a name that works on one machine, which is worse
//! than one that works nowhere: it ships.
//!
//! # What is deliberately not checked
//!
//! **Action names.** An action is not a callable name — `ir.py`'s `_takes`
//! lowers `actions:` into `action: one of look-up-order, issue-refund`, a VALUE
//! of an argument. No provider constrains a value, so refusing `Look Up Order`
//! would refuse something that works.
//!
//! **Skill names.** A skill is a document to read, not something to call, and
//! `ir.py` says so explicitly: it becomes text in the system message and
//! deliberately never becomes a `ToolSpec`.
//!
//! **Agent keys nothing delegates to.** A top-level agent is invoked by a
//! runtime, not chosen by a model out of a tool list. The moment one is put on a
//! `team:` it *is* offered to a model, and that is the line this check reads —
//! which is also the line the author has to retype, so the message lands where
//! the work is.
//!
//! **Ports, resources, questions, loops, policies.** None of them reach a tool
//! list. A check that refuses a name for a reason that does not apply to it
//! teaches an author to distrust the checker.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node};

/// The longest a callable name may be. Every provider's own ceiling.
const LONGEST: usize = 64;

/// Refuse a tool or teammate name the model would be handed and could not call.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    for (name, entry) in document
        .get("tools")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let Some(wrong) = what_is_wrong_with(name) else {
            continue;
        };
        diags.push(a_tool(document, name, &entry.key_span, &wrong));
    }

    // A single-agent folder has `team:` at the top and no `agents:` around it,
    // which is the shape `pact check examples/refund-desk/agents/refund-desk`
    // loads. Both shapes are walked so the refusal does not depend on which
    // folder the reader pointed the command at.
    let agents: Vec<(&str, &Node)> = match document.get("agents").and_then(Node::as_map) {
        Some(m) => m.iter().map(|(k, e)| (k.as_str(), &e.node)).collect(),
        None => vec![("", document)],
    };
    for (_, agent) in agents {
        let Some(team) = agent.get("team").and_then(Node::as_map) else {
            continue;
        };
        for (name, entry) in team {
            // A teammate with no agent behind it is already reported at this
            // exact line by `key-names: agents`, and one mistake gets one
            // message — the same deferral `teams.rs` makes.
            if !names_an_agent(document, name) {
                continue;
            }
            let Some(wrong) = what_is_wrong_with(name) else {
                continue;
            };
            diags.push(a_teammate(document, agent, name, &entry.key_span, &wrong));
        }
    }
}

/// The diagnostic for a tool whose key a model cannot call.
fn a_tool(document: &Node, name: &str, at: &Span, wrong: &str) -> Diagnostic {
    let good = spelled_for_a_model(name);
    let mut fix = rename_to("tools", name, &good, at);
    // Only when somebody really lists it. Telling an author to change a `uses:`
    // line they never wrote sends them looking for a file that has no such line.
    let users = uses_lines(document, name);
    if !users.is_empty() {
        fix.push_str(&format!(
            " and change the `uses:` line to `- {}`",
            spelled(&good)
        ));
    }
    fix.push('.');

    let mut d = Diagnostic::error(
        "loader/name-a-model-cannot-call",
        at.clone(),
        format!("'{name}' is a tool name no model can call — {wrong}. {WHY}"),
        fix,
    );
    for (span, whose) in users {
        d = d.with_related(
            span,
            format!("'{whose}' names it here too — change this line as well"),
        );
    }
    d
}

/// The diagnostic for a teammate whose key a model cannot call.
fn a_teammate(document: &Node, agent: &Node, name: &str, at: &Span, wrong: &str) -> Diagnostic {
    let good = spelled_for_a_model(name);
    // An agent is a FOLDER with an `agent.yaml` in it (`agent.team`'s own help
    // says so), so the rename is written against the folder even when the
    // teammate's own key was typed inline.
    let folder = agents_key_span(document, name);
    let mut fix = match &folder {
        Some(span) => format!("{} and change", rename_to("agents", name, &good, span)),
        None => "Change".to_string(),
    };
    fix.push_str(&format!(
        " the `{name}:` line under `team:` to `{}:`.",
        spelled(&good)
    ));

    let mut d = Diagnostic::error(
        "loader/name-a-model-cannot-call",
        at.clone(),
        format!(
            "'{name}' is a teammate name no model can call — {wrong}. {WHY} \
             It is offered to the model as somebody this agent can ask, by this name."
        ),
        fix,
    );
    if let Some(span) = folder {
        d = d.with_related(span, "the folder that has to be renamed");
    }
    // The sibling line that has to move with it: what the team may spend is
    // divided by name, so a `shares:` key left behind stops matching anybody and
    // `Pool.share_of` hands the renamed member 0.0.
    if let Some(span) = shares_key_span(agent, name) {
        d = d.with_related(
            span,
            "this share is written against the same name — change it as well",
        );
    }
    d
}

/// The sentence every one of these messages ends with.
const WHY: &str = "Every model refuses a name that is not made of lowercase letters, numbers, `-` and `_`, \
     so the first thing this agent tries to do fails before a word is written.";

/// "Rename the file to `tools/get-weather.yaml`", in whichever form was written.
///
/// Which form it is comes from the span: a document that IS a file or a folder
/// was given [`Span::whole_file`] by the Expansion Rule, so it has no width. One
/// written inline in `workspace.yaml` has a real key position, and telling that
/// author to rename a file would send them looking for one that does not exist.
fn rename_to(section: &str, name: &str, good: &str, at: &Span) -> String {
    let good = spelled(good);
    if !is_a_whole_file(at) {
        return format!("Change the `{name}:` line under `{section}:` to `{good}:`");
    }
    match document_extension(at) {
        Some(ext) => format!("Rename the file to `{section}/{good}.{ext}`"),
        None => format!("Rename the folder to `{section}/{good}`"),
    }
}

/// A span that identifies a whole file or folder rather than a position in one.
fn is_a_whole_file(at: &Span) -> bool {
    at.byte_start == 0 && at.byte_end == 0
}

/// The extension of the document a whole-file span names, when it is one the
/// loader reads.
///
/// Held to the loader's own list rather than to "has a dot in it". A FOLDER
/// called `tools/fraud.checker` has an extension by that test, and telling its
/// author to rename a file to `tools/fraud-checker.checker` is a fix that
/// creates a second mistake — and the dot is exactly the kind of character that
/// gets one of these documents reported in the first place.
fn document_extension(at: &Span) -> Option<&str> {
    at.file
        .extension()
        .filter(|e| matches!(*e, "yaml" | "yml" | "json" | "md" | "markdown"))
}

/// Why this name cannot be called, in the author's own terms.
///
/// Every reason that applies, not the first: `Get.Weather` is wrong twice, and
/// an author who fixes the capital and runs again to be told about the dot has
/// been made to do two rounds for one edit. Returns `None` for a name that is
/// already callable.
fn what_is_wrong_with(name: &str) -> Option<String> {
    let mut said: Vec<String> = Vec::new();

    if name.is_empty() {
        return Some("it is empty".to_string());
    }
    if name.chars().count() > LONGEST {
        said.push(format!(
            "it is {} characters long and the most a name may be is {LONGEST}",
            name.chars().count()
        ));
    }
    if name.contains(' ') {
        said.push("it has a space in it".to_string());
    }
    if name.chars().any(|c| c.is_ascii_uppercase()) {
        said.push("it has a capital letter in it".to_string());
    }
    // Said separately from "a character that is not allowed", because `-` and
    // `_` ARE allowed — just not first — and telling an author that `-` is not
    // allowed in a name full of them reads as a checker that cannot count.
    // A leading space is already covered by the line above; saying it twice, the
    // second time as an unreadable pair of backticks around nothing, is worse
    // than not saying it.
    let first = name.chars().next().expect("not empty");
    let starts_well = first.is_ascii_lowercase() || first.is_ascii_digit();
    if !starts_well && !first.is_ascii_uppercase() && first != ' ' {
        said.push(format!(
            "it starts with a `{first}`, and a name has to start with a letter or a number"
        ));
    }
    if let Some(bad) = name.chars().find(|c| !allowed_anywhere(*c)) {
        said.push(format!("it has a `{bad}` in it"));
    }

    if said.is_empty() {
        None
    } else {
        Some(said.join(", and "))
    }
}

/// A character a callable name may hold somewhere, capitals aside.
///
/// A space is excluded here and reported by its own sentence: "it has a ` ` in
/// it" is a pair of backticks around nothing.
fn allowed_anywhere(c: char) -> bool {
    c.is_ascii_lowercase()
        || c.is_ascii_uppercase()
        || c.is_ascii_digit()
        || c == '-'
        || c == '_'
        || c == ' '
}

/// The same name, spelled the way an author would have typed it.
///
/// Mechanical on purpose. The message names what is wrong and this names the
/// answer, so the author retypes rather than guesses — but a clever rewrite that
/// nobody can predict is worse than a plain one, because the next name they
/// invent has to follow the same rule by hand.
fn spelled_for_a_model(name: &str) -> String {
    let mut out = String::new();
    let mut after_lower_or_digit = false;
    for ch in name.chars() {
        if ch.is_ascii_uppercase() {
            // `getWeather` is two words to everyone who reads it, so the break
            // goes where the capital was rather than being swallowed.
            if after_lower_or_digit {
                out.push('-');
            }
            out.push(ch.to_ascii_lowercase());
            after_lower_or_digit = false;
        } else if ch.is_ascii_lowercase() || ch.is_ascii_digit() {
            out.push(ch);
            after_lower_or_digit = true;
        } else if ch == '_' {
            out.push('_');
            after_lower_or_digit = false;
        } else {
            // A space, a dot, a slash, an accent — all of them are where one
            // word ended and the next began.
            out.push('-');
            after_lower_or_digit = false;
        }
    }

    // A run of separators is one separator, and it keeps the first one written:
    // `Get_ Weather` was meant to be `get_weather`, not `get_-weather`.
    let mut collapsed = String::new();
    let mut run = false;
    for ch in out.chars() {
        let sep = ch == '-' || ch == '_';
        if sep && run {
            continue;
        }
        run = sep;
        collapsed.push(ch);
    }

    let trimmed = collapsed.trim_matches(|c| c == '-' || c == '_');
    let mut good: String = trimmed.chars().take(LONGEST).collect();
    // Truncating can leave a name ending in the separator it was cut at.
    while good.ends_with('-') || good.ends_with('_') {
        good.pop();
    }
    good
}

/// Whether the workspace has an agent by this name.
fn names_an_agent(document: &Node, name: &str) -> bool {
    document
        .get("agents")
        .and_then(Node::as_map)
        .is_some_and(|m| m.contains_key(name))
}

/// Where the agent of this name was written.
fn agents_key_span(document: &Node, name: &str) -> Option<Span> {
    document
        .get("agents")
        .and_then(Node::as_map)
        .and_then(|m: &Map| m.get(name))
        .map(|e| e.key_span.clone())
}

/// Where a share is written against this name, on this agent's `teamwork:`.
fn shares_key_span(agent: &Node, name: &str) -> Option<Span> {
    agent
        .get("teamwork")
        .and_then(|t| t.get("shares"))
        .and_then(Node::as_map)
        .and_then(|m: &Map| m.get(name))
        .map(|e| e.key_span.clone())
}

/// Every `uses:` line naming this tool, with the agent that wrote it.
fn uses_lines<'a>(document: &'a Node, name: &str) -> Vec<(Span, &'a str)> {
    let mut out = Vec::new();
    let agents: Vec<(&str, &Node)> = match document.get("agents").and_then(Node::as_map) {
        Some(m) => m.iter().map(|(k, e)| (k.as_str(), &e.node)).collect(),
        None => vec![("this agent", document)],
    };
    for (who, agent) in agents {
        for item in agent
            .get("uses")
            .and_then(Node::as_list)
            .unwrap_or_default()
        {
            if item.as_str().map(str::trim) == Some(name) {
                out.push((item.span.clone(), who));
            }
        }
    }
    out
}

/// The corrected name as the fix writes it, or a placeholder when there is
/// nothing left to correct.
///
/// `tools/!!!.yaml` reduces to nothing at all, and a fix reading "rename it to
/// ``" is worse than no fix. One function so the empty case has one answer
/// rather than one per place that writes the name out.
fn spelled(good: &str) -> &str {
    if good.is_empty() {
        "<a-name-you-choose>"
    } else {
        good
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        check(&node, &mut d);
        d
    }

    #[test]
    fn a_tool_name_with_a_space_in_it_is_refused_and_the_fix_spells_the_new_name() {
        let d = check_text(
            "agents:\n  desk:\n    uses:\n      - Get Weather\ntools:\n  Get Weather:\n    description: x\n",
        );
        let e = d
            .items()
            .first()
            .expect("a name no model can call must be refused");
        assert_eq!(e.rule, "loader/name-a-model-cannot-call");
        assert_eq!(
            e.severity,
            pact_diag::Severity::Error,
            "the first model call fails"
        );
        assert!(
            e.message.contains("'Get Weather'"),
            "name what is wrong: {}",
            e.message
        );
        assert!(
            e.message.contains("space"),
            "say why, in the author's terms: {}",
            e.message
        );
        assert!(
            e.fix.contains("get-weather"),
            "spell the corrected name: {}",
            e.fix
        );
        assert!(
            e.fix.contains("`uses:`"),
            "the other line to retype: {}",
            e.fix
        );
    }

    #[test]
    fn a_tool_written_as_its_own_file_is_told_to_rename_the_file() {
        // The Expansion Rule gives a document that IS a file a whole-file span,
        // and that is the only thing that distinguishes the two fixes: "rename
        // the file" is useless advice to somebody who wrote the tool inline.
        let mut node = parse_yaml("tools:\n  x: {}\n", camino::Utf8Path::new("workspace.yaml"))
            .expect("parses");
        let tools = node.as_map_mut().unwrap().get_mut("tools").unwrap();
        let inner = tools.node.as_map_mut().unwrap();
        let entry = inner.shift_remove("x").unwrap();
        inner.insert(
            "Get Weather".to_string(),
            pact_doc::Entry {
                key_span: Span::whole_file("tools/Get Weather.yaml"),
                node: entry.node,
            },
        );
        let mut d = Diagnostics::new();
        check(&node, &mut d);
        let e = d.items().first().expect("refused");
        assert!(
            e.fix
                .contains("Rename the file to `tools/get-weather.yaml`"),
            "name the file the author would rename: {}",
            e.fix
        );
    }

    #[test]
    fn a_tool_written_inline_is_told_to_change_the_line_rather_than_rename_a_file() {
        let d = check_text("tools:\n  Get Weather:\n    description: x\n");
        let e = d.items().first().expect("refused");
        assert!(
            e.fix.contains("Change the `Get Weather:` line"),
            "{}",
            e.fix
        );
        assert!(
            !e.fix.contains("Rename"),
            "there is no file to rename here: {}",
            e.fix
        );
    }

    #[test]
    fn a_teammate_name_with_a_capital_letter_in_it_is_refused() {
        let d = check_text(
            "agents:\n  desk:\n    team:\n      Fraud Checker: looks for fraud\n\
             \n  Fraud Checker:\n    description: x\n",
        );
        let e = d
            .items()
            .first()
            .expect("a teammate is offered to the model by this name");
        assert_eq!(e.rule, "loader/name-a-model-cannot-call");
        assert!(e.message.contains("capital letter"), "{}", e.message);
        assert!(
            e.fix.contains("fraud-checker"),
            "spell the corrected name: {}",
            e.fix
        );
        assert!(
            e.fix.contains("`team:`"),
            "the line the author retypes: {}",
            e.fix
        );
    }

    #[test]
    fn a_teammate_with_no_agent_behind_it_is_left_to_the_reference_check() {
        // `key-names: agents` already reports it at this exact line. One mistake
        // gets one message — the same deferral `teams.rs` makes.
        let d = check_text("agents:\n  desk:\n    team:\n      Nobody At All: helps\n");
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_name_longer_than_a_provider_accepts_is_refused_and_the_fix_is_short_enough() {
        let long = "a".repeat(70);
        let d = check_text(&format!("tools:\n  {long}:\n    description: x\n"));
        let e = d
            .items()
            .first()
            .expect("70 characters is a provider refusal");
        assert!(
            e.message.contains("70 characters"),
            "count it for them: {}",
            e.message
        );
        assert!(e.message.contains("64"), "say the ceiling: {}", e.message);
        // The offered spelling is cut to the ceiling, not handed back at full
        // length: a fix that reproduces the mistake is not a fix.
        assert!(
            e.fix.contains(&format!("to `{}:`", "a".repeat(LONGEST))),
            "the offered name has to fit: {}",
            e.fix
        );
    }

    #[test]
    fn a_name_that_starts_with_a_dash_is_refused_for_starting_with_it_and_not_for_having_it() {
        let d = check_text("tools:\n  \"-refund\":\n    description: x\n");
        let e = d.items().first().expect("refused");
        assert!(e.message.contains("starts with"), "{}", e.message);
        assert!(
            !e.message.contains("it has a `-` in it"),
            "a name full of dashes must not be told dashes are banned: {}",
            e.message
        );
        assert!(e.fix.contains("refund"), "{}", e.fix);
    }

    #[test]
    fn every_name_the_worked_example_uses_is_left_alone() {
        // A check that refuses correct documents is not a check.
        let d = check_text(
            "agents:\n  refund-desk:\n    uses:\n      - zendesk\n      - payments\n      \
             - refund-policy\n    team:\n      policy-checker: x\n      fraud-checker: y\n\
             \n  policy-checker:\n    description: x\n  fraud-checker:\n    description: y\n\
             tools:\n  zendesk: {}\n  payments: {}\n",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn an_underscore_and_a_digit_are_ordinary_parts_of_a_name() {
        // The providers allow both and so does this. Refusing more than the
        // reason justifies is how a checker loses an author's trust.
        let d = check_text("tools:\n  get_order_v2: {}\n  s3: {}\n");
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn the_offered_spelling_is_itself_a_name_a_model_can_call() {
        // The one property the fix cannot be allowed to get wrong: retyping what
        // it says has to end the diagnostic rather than produce a second one.
        for bad in [
            "Get Weather",
            "getWeather",
            "Get.Weather",
            "  spaced  out  ",
            "Get_ Weather",
            "--leading--",
            "über",
            &"A".repeat(90),
        ] {
            let good = spelled_for_a_model(bad);
            assert!(!good.is_empty(), "no spelling offered for {bad:?}");
            assert!(
                what_is_wrong_with(&good).is_none(),
                "{bad:?} was corrected to {good:?}, which is still not callable: {:?}",
                what_is_wrong_with(&good)
            );
        }
    }

    #[test]
    fn a_name_with_nothing_callable_left_in_it_asks_for_one_rather_than_offering_an_empty_fix() {
        // `tools/!!!.yaml` reduces to nothing, and "rename it to ``" is worse
        // than no fix at all — it looks like the checker lost the answer.
        let d = check_text("tools:\n  \"!!!\":\n    description: x\n");
        let e = d.items().first().expect("refused");
        assert!(
            e.fix.contains("<a-name-you-choose>"),
            "ask for a name: {}",
            e.fix
        );
        assert!(
            !e.fix.contains("``"),
            "no empty spelling may reach the author: {}",
            e.fix
        );
    }

    #[test]
    fn a_folder_with_a_dot_in_its_name_is_not_mistaken_for_a_file_with_an_extension() {
        // "Has a dot in it" is not the same question as "is a file the loader
        // reads", and the dot is exactly the sort of character that gets a
        // document reported here in the first place. Telling this author to
        // rename a file to `tools/fraud-checker.checker` would hand them a
        // second mistake in place of the first.
        let mut node =
            parse_yaml("tools:\n  x: {}\n", camino::Utf8Path::new("w.yaml")).expect("parses");
        let inner = node
            .as_map_mut()
            .unwrap()
            .get_mut("tools")
            .unwrap()
            .node
            .as_map_mut()
            .unwrap();
        let entry = inner.shift_remove("x").unwrap();
        inner.insert(
            "fraud.checker".to_string(),
            pact_doc::Entry {
                key_span: Span::whole_file("tools/fraud.checker"),
                node: entry.node,
            },
        );
        let mut d = Diagnostics::new();
        check(&node, &mut d);
        let e = d.items().first().expect("refused");
        assert!(
            e.fix.contains("Rename the folder to `tools/fraud-checker`"),
            "a folder is a folder: {}",
            e.fix
        );
    }

    #[test]
    fn a_share_written_against_a_name_that_has_to_change_is_pointed_at_as_well() {
        // The sibling line. Renaming the teammate and leaving the share behind
        // hands the renamed member 0.0 of the pot, silently.
        let d = check_text(
            "agents:\n  desk:\n    team:\n      Fraud Checker: y\n    teamwork:\n      \
             shares:\n        Fraud Checker: 40%\n  Fraud Checker:\n    description: x\n",
        );
        let e = d.items().first().expect("refused");
        assert!(
            e.related.iter().any(|r| r.message.contains("share")),
            "the share line has to move with it: {:?}",
            e.related
        );
    }
}
