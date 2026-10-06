//! **Run-time holes in an agent's words** (02P §3.2 A1).
//!
//! `{{run-inputs.<name>}}` and `{{remembers.<name>}}` in `instructions:` or
//! `description:`, and in a variant's `instructions:` or `says:`, are filled by
//! the host when a run starts; the model never fills them. They use the same
//! two addresses `bind:` already takes, so there is no new address grammar.
//!
//! What only a check can say is whether a hole names something the agent
//! declares. A hole naming nothing would reach the model as literal braces —
//! the silent mis-translation this addition exists to end — so it is refused
//! here, where the author is, with the names that do exist.
//!
//! # What counts as a hole
//!
//! `{{`, optional spaces, a dotted name made of letters, digits, `-`, `_` and
//! `.`, optional spaces, `}}`. Anything else between double braces (a
//! Handlebars helper such as `{{#each}}`, an example of JSON) is not a hole and
//! is left alone: it is text, and it reaches the model as text. The same
//! grammar is `pact_adapters.holes` on the Python side.
//!
//! # Braces the model is meant to read
//!
//! Instructions that tell a model to WRITE a template say `{{first_name}}` and
//! mean those braces. So a name in neither namespace that the agent does not
//! declare is text, with a warning (`loader/not-a-hole`) in case it was a typo;
//! refusing it left such an agent with no way to be written at all. The one
//! escape is a backslash: `\{{first_name}}` is the braces, said on purpose, and
//! is how `\{{run-inputs.brand}}` is written literally too. A runtime sends an
//! escaped pair without its backslash.
//!
//! A bare name the agent DOES declare (`{{brand}}` beside `run-inputs: brand`)
//! is still refused: the author meant the hole, and the fix is one word.
//!
//! # Nearly a hole
//!
//! `{{{run-inputs.brand}}}`, `{{run-inputs.brand | upper}}` and
//! `{{ run-inputs. brand }}` name a namespace and are not holes, so nothing
//! fills them and the model reads the braces. That is almost never what was
//! meant, so each is a warning (`loader/almost-a-hole`).

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Node, Value};
use std::collections::BTreeSet;

/// The two namespaces a hole may name.
const RUN_INPUTS: &str = "run-inputs";
const REMEMBERS: &str = "remembers";

/// The agent fields whose text may carry holes.
const FIELDS: [&str; 2] = ["instructions", "description"];
/// The fields of one variant that become the agent's instructions.
const VARIANT_FIELDS: [&str; 2] = ["instructions", "says"];

/// One hole found in some text: the name between the braces, and how many
/// lines into the text it sits.
#[derive(Debug, PartialEq, Eq)]
pub struct Hole {
    pub written: String,
    pub line_offset: usize,
}

/// One pair of double braces worth a word: a hole, or nearly one.
#[derive(Debug, PartialEq, Eq)]
struct Found {
    /// The name between the braces; for a near-miss, the braces as written.
    written: String,
    /// Where its `{{` starts in the text scanned.
    at: usize,
    almost: bool,
}

/// Every hole and near-miss in `text`, in order.
///
/// Leftmost `{{`, first `}}` after it, and on anything that is not a name step
/// past the `{{` only — so `{{{run-inputs.x}}}` is not a hole. A `{{` with a
/// backslash before it is the author's own braces and is stepped over.
fn scan(text: &str) -> Vec<Found> {
    let mut out = Vec::new();
    let mut from = 0usize;
    while let Some(open) = text[from..].find("{{").map(|i| from + i) {
        let after = open + 2;
        if text[..open].ends_with('\\') {
            from = after;
            continue;
        }
        let Some(close) = text[after..].find("}}").map(|i| after + i) else { break };
        let inner = text[after..close].trim();
        let is_name = !inner.is_empty()
            && inner.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'));
        if is_name {
            out.push(Found { written: inner.to_string(), at: open, almost: false });
            from = close + 2;
            continue;
        }
        // Nearly a hole: it names a namespace and is one pair of braces (a
        // second `{{` inside means this pair closes somewhere else).
        let names_one = [RUN_INPUTS, REMEMBERS].iter().any(|n| inner.contains(&format!("{n}.")));
        if names_one && !inner.contains("{{") {
            // `{{{x}}}` is shown whole: its third brace is part of the mistake.
            let end = close + 2 + usize::from(text[close + 2..].starts_with('}'));
            out.push(Found { written: text[open..end].to_string(), at: open, almost: true });
        }
        from = after;
    }
    out
}

/// Every hole in `text`, in order.
pub fn holes_in(text: &str) -> Vec<Hole> {
    scan(text)
        .into_iter()
        .filter(|f| !f.almost)
        .map(|f| Hole { line_offset: text[..f.at].matches('\n').count(), written: f.written })
        .collect()
}

/// Refuse a hole that names an undeclared run input or remembered fact, and
/// warn about braces that look like a hole and are not one.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        return;
    };
    for (agent, entry) in agents {
        let declared = |field: &str| -> BTreeSet<String> {
            entry
                .node
                .get(field)
                .and_then(Node::as_map)
                .map(|m| m.keys().cloned().collect())
                .unwrap_or_default()
        };
        let inputs = declared(RUN_INPUTS);
        let remembered = declared(REMEMBERS);
        // Each text that becomes this agent's words, with what to call it.
        let mut texts: Vec<(String, &str, &Span)> = Vec::new();
        for field in FIELDS {
            if let Some(node) = entry.node.get(field) {
                prose(node, field, &mut texts);
            }
        }
        // A variant's words are filled like the agent's own, so they are held
        // like them: unchecked, a hole there loaded cleanly and stopped the
        // first run that chose the variant.
        for (name, variant) in entry.node.get("variants").and_then(Node::as_map).into_iter().flatten() {
            for field in VARIANT_FIELDS {
                if let Some(node) = variant.node.get(field) {
                    prose(node, &format!("variants.{name}.{field}"), &mut texts);
                }
            }
        }
        for (field, text, span) in texts {
            let found = scan(text);
            let places = in_the_source(diags, span, &found);
            for (i, one) in found.iter().enumerate() {
                let at = places.as_ref().map_or_else(|| guessed(span, text, one), |p| p[i].clone());
                if let Some(d) = judge(agent, &field, one, at, &inputs, &remembered) {
                    diags.push(d);
                }
            }
        }
    }
}

/// Every piece of text under a field: one string, or the prose of a folder.
fn prose<'a>(node: &'a Node, field: &str, out: &mut Vec<(String, &'a str, &'a Span)>) {
    match &node.value {
        Value::Str(s) => out.push((field.to_string(), s, &node.span)),
        Value::Map(m) => m.values().for_each(|e| prose(&e.node, field, out)),
        Value::List(items) => items.iter().for_each(|n| prose(n, field, out)),
        _ => {}
    }
}

/// Where each of `found` sits in the file, read off the file's own bytes.
///
/// A value's span is where the value STARTS, and the value is not the file: a
/// `|` block starts on the line after its key, a `>` block joins its lines, and
/// a quoted scalar folds them. Counting newlines in the VALUE pointed at the
/// wrong line for all three. The same scan over the bytes the value was read
/// from finds the same braces in the same order, and those have a line.
///
/// Scanned from the value's first byte to the end of the file, and only the
/// first `found.len()` taken: a span's end is not where a folded value ends in
/// the file, and what comes after this value is some other field's business.
///
/// `None` when the file's text is not at hand, or the scan of it disagrees with
/// the scan of the value (an escaped brace in a quoted scalar): the caller then
/// falls back to the value's own start rather than pointing somewhere wrong.
fn in_the_source(diags: &Diagnostics, span: &Span, found: &[Found]) -> Option<Vec<Span>> {
    let source = diags.source_of(&span.file)?;
    let written = source.get(span.byte_start..)?;
    let there = scan(written);
    let same = there.len() >= found.len()
        && there.iter().zip(found).all(|(a, b)| a.almost == b.almost && a.written == b.written);
    if !same {
        return None;
    }
    Some(
        there
            .iter()
            .take(found.len())
            .map(|f| {
                let start = span.byte_start + f.at;
                let before = &source[..start];
                let line = before.matches('\n').count() + 1;
                let col = before.rfind('\n').map_or(start, |nl| start - nl - 1) + 1;
                // To the end of its braces, or of the mistake when it is nearly one.
                let len = if f.almost {
                    f.written.len()
                } else {
                    written[f.at..].find("}}").map_or(2, |i| i + 2)
                };
                Span::new(span.file.clone(), line, col, start, start + len)
            })
            .collect(),
    )
}

/// The value's own position, moved down by the lines before the hole: right
/// for a plain one-line value, and the best there is without the file.
fn guessed(span: &Span, text: &str, found: &Found) -> Span {
    let down = text[..found.at].matches('\n').count();
    Span::new(
        span.file.clone(),
        span.line + down,
        if down == 0 { span.col } else { 1 },
        span.byte_start,
        span.byte_end,
    )
}

/// The diagnostic for one hole, or `None` when it names something declared.
fn judge(
    agent: &str,
    field: &str,
    found: &Found,
    at: Span,
    inputs: &BTreeSet<String>,
    remembered: &BTreeSet<String>,
) -> Option<Diagnostic> {
    let written = &found.written;
    if found.almost {
        return Some(Diagnostic::warning(
            "loader/almost-a-hole",
            at,
            format!(
                "`{written}` in `{agent}`'s `{field}:` names a run input or a remembered \
                 fact and is not a hole, so nothing fills it and the model reads these \
                 braces as they are written."
            ),
            "A hole is two braces each side of one name and nothing else, like \
             `{{run-inputs.brand}}`. If the model is meant to read the braces, put a \
             backslash in front: `\\{{`."
                .to_string(),
        ));
    }
    let (namespace, name) = written.split_once('.').unwrap_or((written.as_str(), ""));
    let (known, noun, rule) = match namespace {
        RUN_INPUTS => (inputs, "run input", "loader/no-such-run-input"),
        REMEMBERS => (
            remembered,
            "remembered fact",
            "loader/no-such-remembered-fact",
        ),
        _ => return Some(not_a_hole(agent, field, written, at, inputs, remembered)),
    };
    if !name.is_empty() && known.contains(name) {
        return None;
    }
    Some(Diagnostic::error(
        rule,
        at,
        format!(
            "`{{{{{written}}}}}` in `{agent}`'s `{field}:` names a {noun} called '{name}', \
             and `{agent}` declares no such {noun} under `{namespace}:` — so there is \
             nothing to fill it with when a run starts."
        ),
        if known.is_empty() {
            format!(
                "Add {} in `{agent}`, or take the hole out.",
                declaration(namespace, name)
            )
        } else {
            format!(
                "Change it to one of: {} — or add `{name}:` under `{namespace}:` in `{agent}`.",
                known
                    .iter()
                    .map(|n| format!("`{{{{{namespace}.{n}}}}}`"))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        },
    ))
}

/// A name in neither namespace. Refused when the agent declares that very name
/// (the author meant the hole, and is told the one it is); otherwise it is the
/// author's own braces, which reach the model as written, and a warning says so
/// and says how to mean it.
fn not_a_hole(
    agent: &str,
    field: &str,
    written: &str,
    at: Span,
    inputs: &BTreeSet<String>,
    remembered: &BTreeSet<String>,
) -> Diagnostic {
    let meant: Vec<String> = [(RUN_INPUTS, inputs), (REMEMBERS, remembered)]
        .iter()
        .filter(|(_, known)| known.contains(written))
        .map(|(namespace, _)| format!("`{{{{{namespace}.{written}}}}}`"))
        .collect();
    let said = format!(
        "`{{{{{written}}}}}` in `{agent}`'s `{field}:` names neither a run input nor a \
         remembered fact, so nothing fills it and it reaches the model as literal braces."
    );
    if !meant.is_empty() {
        return Diagnostic::error(
            "loader/not-a-hole",
            at,
            said,
            format!("Write {}.", meant.join(" or ")),
        );
    }
    Diagnostic::warning(
        "loader/not-a-hole",
        at,
        said,
        format!(
            "If the model is meant to read the braces, say so with a backslash: \
             `\\{{{{{written}}}}}`. If a value belongs there, write {}.",
            offer(agent, inputs, remembered, written)
        ),
    )
}

/// What to write to declare `name` under `namespace`: a run input is one line,
/// a remembered fact is a block with the two lines `state` requires.
fn declaration(namespace: &str, name: &str) -> String {
    if namespace == REMEMBERS {
        format!("`{name}:` under `remembers:`, with its `description:` and `lasts:` lines")
    } else {
        format!("`{name}: text` under `run-inputs:`")
    }
}

/// The holes an agent could write instead of a name nothing declares, named in
/// full, and the declaration that would make the name a run input.
fn offer(
    agent: &str,
    inputs: &BTreeSet<String>,
    remembered: &BTreeSet<String>,
    written: &str,
) -> String {
    let both: Vec<String> = inputs
        .iter()
        .map(|n| format!("`{{{{{RUN_INPUTS}.{n}}}}}`"))
        .chain(
            remembered
                .iter()
                .map(|n| format!("`{{{{{REMEMBERS}.{n}}}}}`")),
        )
        .collect();
    let declare = format!(
        "`{{{{run-inputs.{written}}}}}` and add `{written}: text` under `run-inputs:` in `{agent}`"
    );
    if both.is_empty() {
        declare
    } else {
        format!("one of: {} — or {declare}", both.join(", "))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    const TREE: &str = "
agents:
  writer:
    description: Writes listings for {{run-inputs.brand}}
    run-inputs:
      brand: text
      examples: text
    remembers:
      tone:
        help: x
    instructions: |
      Write in this voice: {{ run-inputs.brand }}
      Match {{run-inputs.examples}} and keep {{remembers.tone}}.
      A JSON example is not a hole: {{\"a\": 1}} and neither is {{#each x}}.
";

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("w.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        // The file's text, as the loader registers it: a hole is located in it.
        d.add_source("w.yaml", text);
        check(&node, &mut d);
        d
    }

    #[test]
    fn holes_naming_what_the_agent_declares_are_left_alone() {
        let d = check_text(TREE);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn the_grammar_takes_dotted_names_and_skips_everything_else() {
        let found: Vec<String> =
            holes_in("a {{ run-inputs.x }} b {{#each}} {{\"k\": 1}} {{remembers.y}}\n{{z}}")
                .into_iter()
                .map(|h| h.written)
                .collect();
        assert_eq!(found, ["run-inputs.x", "remembers.y", "z"]);
        assert_eq!(holes_in("one\ntwo {{run-inputs.a}}")[0].line_offset, 1);
    }

    #[test]
    fn a_misspelt_run_input_is_refused_with_the_names_that_exist() {
        let d = check_text(&TREE.replace("{{run-inputs.examples}}", "{{run-inputs.exampels}}"));
        let e = d.items().first().expect("caught");
        assert_eq!(e.rule, "loader/no-such-run-input");
        assert!(e.message.contains("exampels"), "{}", e.message);
        assert!(e.fix.contains("{{run-inputs.examples}}"), "{}", e.fix);
        assert_eq!(
            e.span.line,
            TREE.lines().position(|l| l.contains("Match")).unwrap() + 1
        );
    }

    #[test]
    fn a_hole_in_the_description_is_held_too() {
        let d = check_text(&TREE.replace("for {{run-inputs.brand}}", "for {{run-inputs.brnad}}"));
        assert_eq!(
            d.items().first().expect("caught").rule,
            "loader/no-such-run-input"
        );
    }

    #[test]
    fn a_remembered_fact_nobody_declares_is_refused() {
        let d = check_text(&TREE.replace("{{remembers.tone}}", "{{remembers.mood}}"));
        let e = d.items().first().expect("caught");
        assert_eq!(e.rule, "loader/no-such-remembered-fact");
        assert!(e.fix.contains("{{remembers.tone}}"), "{}", e.fix);
    }

    #[test]
    fn an_agent_with_no_memory_is_told_what_a_remembered_fact_needs() {
        let d = check_text(
            "agents:\n  a:\n    description: x\n    instructions: Keep {{remembers.tone}}\n",
        );
        let e = d.items().first().expect("caught");
        assert_eq!(e.rule, "loader/no-such-remembered-fact");
        assert!(e.fix.contains("`description:` and `lasts:`"), "{}", e.fix);
    }

    #[test]
    fn a_bare_pydantic_ai_style_hole_is_told_its_namespace() {
        let d = check_text(&TREE.replace("{{ run-inputs.brand }}", "{{brand}}"));
        let e = d.items().first().expect("caught");
        assert_eq!(e.rule, "loader/not-a-hole");
        assert_eq!(e.fix, "Write `{{run-inputs.brand}}`.");
    }

    #[test]
    fn a_bare_name_nothing_declares_is_offered_the_holes_and_a_declaration() {
        let d = check_text(&TREE.replace("{{ run-inputs.brand }}", "{{brnd}}"));
        let e = d.items().first().expect("caught");
        assert_eq!(e.rule, "loader/not-a-hole");
        // Braces a model may be meant to read: said, not refused. Refusing it
        // left instructions that tell a model to write a template unwritable.
        assert_eq!(e.severity, pact_diag::Severity::Warning);
        assert!(e.fix.contains("`\\{{brnd}}`"), "the escape is offered: {}", e.fix);
        assert!(
            e.fix.contains("one of: `{{run-inputs.brand}}`"),
            "{}",
            e.fix
        );
        assert!(
            e.fix.contains("add `brnd: text` under `run-inputs:`"),
            "{}",
            e.fix
        );
    }

    #[test]
    fn a_bare_name_that_is_a_remembered_fact_is_told_that_hole() {
        let d = check_text(&TREE.replace("{{ run-inputs.brand }}", "{{tone}}"));
        let e = d.items().first().expect("caught");
        assert_eq!(e.fix, "Write `{{remembers.tone}}`.");
    }

    #[test]
    fn a_bare_name_the_agent_declares_is_still_refused() {
        let d = check_text(&TREE.replace("{{ run-inputs.brand }}", "{{brand}}"));
        assert_eq!(d.items().first().expect("caught").severity, pact_diag::Severity::Error);
    }

    #[test]
    fn braces_said_on_purpose_are_left_alone() {
        // The one escape, for a name that is nothing and for one that would
        // have been a hole.
        let d = check_text(
            &TREE.replace("{{ run-inputs.brand }}", "\\{{first_name}} \\{{run-inputs.nobody}}"),
        );
        assert!(d.is_empty(), "{}", d.render());
        assert!(holes_in("a \\{{run-inputs.x}} b").is_empty());
    }

    #[test]
    fn braces_that_are_nearly_a_hole_are_each_warned_about() {
        for nearly in
            ["{{{run-inputs.brand}}}", "{{run-inputs.brand | upper}}", "{{ run-inputs. brand }}"]
        {
            let d = check_text(&TREE.replace("{{ run-inputs.brand }}", nearly));
            let [w] = d.items() else { panic!("one warning for {nearly}:\n{}", d.render()) };
            assert_eq!(w.rule, "loader/almost-a-hole");
            assert_eq!(w.severity, pact_diag::Severity::Warning);
            assert!(w.message.contains(nearly), "{}", w.message);
        }
        // Text that only happens to stand before a hole is not nearly one.
        let d = check_text(&TREE.replace("{{ run-inputs.brand }}", "{{\"k\": 1} then"));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_variants_words_are_held_like_the_agents_own() {
        let variants = "    variants:
      small:
        when: a smaller model
        says: Keep to {{run-inputs.brand}} and match {{run-inputs.tone}}.
      terse:
        when: long instructions read badly
        instructions: Keep {{remembers.mood}}.
";
        let d = check_text(&format!("{TREE}{variants}"));
        let rules: Vec<(&str, bool)> = d
            .items()
            .iter()
            .map(|e| (e.rule, e.message.contains("`variants.small.says:`")))
            .collect();
        assert_eq!(
            rules,
            [("loader/no-such-run-input", true), ("loader/no-such-remembered-fact", false)],
            "{}",
            d.render()
        );
        assert!(d.items()[1].message.contains("`variants.terse.instructions:`"));
    }

    #[test]
    fn a_hole_is_reported_at_the_line_it_is_written_on_however_the_words_are_folded() {
        let folded = "agents:
  writer:
    run-inputs:
      brand: text
    description: \"Writes listings
      for one brand,
      which is {{run-inputs.brnad}}.\"
    instructions: >
      Write in this voice.

      Use the brand {{run-inputs.band}} by name.
";
        let d = check_text(folded);
        let at: Vec<(usize, usize)> = d.items().iter().map(|e| (e.span.line, e.span.col)).collect();
        // `instructions:` is read first, then `description:`.
        assert_eq!(at, [(11, 21), (7, 16)], "{}", d.render());
    }

    #[test]
    fn an_agent_with_no_run_inputs_is_told_to_declare_one() {
        let d = check_text(
            "agents:\n  a:\n    description: x\n    instructions: Hi {{run-inputs.who}}\n",
        );
        let e = d.items().first().expect("caught");
        assert_eq!(e.rule, "loader/no-such-run-input");
        assert!(
            e.fix.contains("`who: text` under `run-inputs:`"),
            "{}",
            e.fix
        );
    }
}
