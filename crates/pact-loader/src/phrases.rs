//! **An empty phrase in a rule about what an answer says.**
//!
//! `must-contain:`, `must-not-contain:` and `must-say-one-of:` hold phrases an
//! answer is searched for, wherever a rule is written (a suite's `rules:`, an
//! agent's or a stage's `checked-by:`). Every answer contains the empty
//! phrase, so one empty entry makes the rule say nothing the author meant:
//! `must-not-contain: [""]` fails every answer, so every checked answer is
//! asked for again and every request goes to the backup, and `must-contain:`
//! or `must-say-one-of:` holds for every answer. It loaded clean. Found by Bud
//! Agent Flow's *Route to a specialist* template, whose `never-say` hole fills
//! `must-not-contain:`: an author who wrote `never-say: ""` to turn the check
//! off turned every answer over to the backup. The fix says how to check
//! nothing: `[]`, or no rule.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Node, Value};

/// The rule words whose phrases are searched for in an answer.
const PHRASES: [&str; 3] = ["must-contain", "must-not-contain", "must-say-one-of"];

/// Refuse every empty or blank phrase under one of `PHRASES`, anywhere.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    walk(document, diags);
}

fn walk(node: &Node, diags: &mut Diagnostics) {
    match &node.value {
        Value::Map(map) => {
            for (key, entry) in map {
                if PHRASES.contains(&key.as_str()) {
                    for at in empty(&entry.node) {
                        let d = refused(key, at);
                        // A hole two stages fill from one `with:` is one empty phrase.
                        if !diags
                            .items()
                            .iter()
                            .any(|x| x.rule == d.rule && x.span == d.span)
                        {
                            diags.push(d);
                        }
                    }
                }
                walk(&entry.node, diags);
            }
        }
        Value::List(items) => items.iter().for_each(|n| walk(n, diags)),
        _ => {}
    }
}

/// Where each empty phrase is: the value itself when it is one, or each entry.
fn empty(node: &Node) -> Vec<Span> {
    let blank = |n: &Node| n.as_str().is_some_and(|s| s.trim().is_empty());
    match node.as_list() {
        Some(items) => items
            .iter()
            .filter(|n| blank(n))
            .map(|n| n.span.clone())
            .collect(),
        None if blank(node) => vec![node.span.clone()],
        None => Vec::new(),
    }
}

fn refused(key: &str, at: Span) -> Diagnostic {
    let what = if key == "must-not-contain" {
        "so every answer breaks the rule: each one checked is asked for again, and none can pass"
    } else {
        "so the rule holds for every answer and checks nothing"
    };
    Diagnostic::error(
        "loader/an-empty-phrase",
        at,
        format!(
            "`{key}:` has an empty phrase, and every answer contains the empty phrase, {what}."
        ),
        "Delete the empty phrase. To check nothing, write `[]` or leave the rule out.".to_string(),
    )
}
