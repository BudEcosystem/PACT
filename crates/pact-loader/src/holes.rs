//! **Run-time holes in an agent's words** (02P §3.2 A1).
//!
//! `{{run-inputs.<name>}}` and `{{remembers.<name>}}` in `instructions:` or
//! `description:` are filled by the host when a run starts; the model never
//! fills them. They use the same two addresses `bind:` already takes, so there
//! is no new address grammar.
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
//! grammar is `pact_adapters.holes.HOLE` on the Python side.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Node, Value};
use std::collections::BTreeSet;

/// The two namespaces a hole may name.
const RUN_INPUTS: &str = "run-inputs";
const REMEMBERS: &str = "remembers";

/// The agent fields whose text may carry holes.
const FIELDS: [&str; 2] = ["instructions", "description"];

/// One hole found in some text: the name between the braces, and how many
/// lines into the text it sits.
#[derive(Debug, PartialEq, Eq)]
pub struct Hole {
    pub written: String,
    pub line_offset: usize,
}

/// Every hole in `text`, in order.
pub fn holes_in(text: &str) -> Vec<Hole> {
    let mut out = Vec::new();
    let mut rest = text;
    let mut consumed = 0usize;
    while let Some(open) = rest.find("{{") {
        let after = &rest[open + 2..];
        let Some(close) = after.find("}}") else { break };
        let inner = after[..close].trim();
        let is_name = !inner.is_empty()
            && inner
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'));
        if is_name {
            let at = consumed + open;
            out.push(Hole {
                written: inner.to_string(),
                line_offset: text[..at].matches('\n').count(),
            });
            consumed += open + 2 + close + 2;
            rest = &after[close + 2..];
        } else {
            consumed += open + 2;
            rest = after;
        }
    }
    out
}

/// Refuse a hole that names an undeclared run input or remembered fact, or a
/// namespace a hole cannot name.
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
        for field in FIELDS {
            let Some(node) = entry.node.get(field) else {
                continue;
            };
            let mut texts = Vec::new();
            prose(node, &mut texts);
            for (text, span) in texts {
                for hole in holes_in(text) {
                    if let Some(d) = judge(agent, field, &hole, span, &inputs, &remembered) {
                        diags.push(d);
                    }
                }
            }
        }
    }
}

/// Every piece of text under a field: one string, or the prose of a folder.
fn prose<'a>(node: &'a Node, out: &mut Vec<(&'a str, &'a Span)>) {
    match &node.value {
        Value::Str(s) => out.push((s, &node.span)),
        Value::Map(m) => m.values().for_each(|e| prose(&e.node, out)),
        Value::List(items) => items.iter().for_each(|n| prose(n, out)),
        _ => {}
    }
}

/// The diagnostic for one hole, or `None` when it names something declared.
fn judge(
    agent: &str,
    field: &str,
    hole: &Hole,
    span: &Span,
    inputs: &BTreeSet<String>,
    remembered: &BTreeSet<String>,
) -> Option<Diagnostic> {
    let at = Span::new(
        span.file.clone(),
        span.line + hole.line_offset,
        if hole.line_offset == 0 { span.col } else { 1 },
        span.byte_start,
        span.byte_end,
    );
    let written = &hole.written;
    let (namespace, name) = written.split_once('.').unwrap_or((written.as_str(), ""));
    let (known, noun, rule) = match namespace {
        RUN_INPUTS => (inputs, "run input", "loader/no-such-run-input"),
        REMEMBERS => (
            remembered,
            "remembered fact",
            "loader/no-such-remembered-fact",
        ),
        _ => {
            return Some(Diagnostic::error(
                "loader/not-a-hole",
                at,
                format!(
                    "`{{{{{written}}}}}` in `{agent}`'s `{field}:` names neither a run input \
                     nor a remembered fact, so it would reach the model as literal braces."
                ),
                format!("Write {}.", offer(agent, inputs, remembered, written)),
            ));
        }
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

/// What to write to declare `name` under `namespace`: a run input is one line,
/// a remembered fact is a block with the two lines `state` requires.
fn declaration(namespace: &str, name: &str) -> String {
    if namespace == REMEMBERS {
        format!("`{name}:` under `remembers:`, with its `description:` and `lasts:` lines")
    } else {
        format!("`{name}: text` under `run-inputs:`")
    }
}

/// The holes an agent could write instead, named in full.
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
        assert!(e.fix.contains("{{run-inputs.brand}}"), "{}", e.fix);
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
