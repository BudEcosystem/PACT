//! **A setting the pinned model would throw away** (96 §B5).
//!
//! `settings:` is one closed list with one meaning per key on every provider —
//! and not every model takes every key. In the code this repository pins
//! (Pydantic AI 2.54), OpenAI's chat models are never sent `top_k`, drop
//! `temperature`, `top_p` and the two penalties while they reason, and
//! Anthropic's newest models drop `temperature`, `top_p` and `top_k` always.
//! Each drop is a Python `UserWarning` and nothing more, so `model: gpt-5.5`
//! with `temperature: 0.2` loaded clean and ran at the model's own default —
//! GPT-5.5 reasons unless told not to, so the line never reached it.
//!
//! What each model ignores is a figure on its catalogue row
//! (`model-can.ignores`, `ignores-while-thinking`, `thinks-unless-told`), read
//! here and nowhere else. A row that says nothing is not judged: an unrecorded
//! figure is unknown, never "takes everything" or "takes nothing" (Y12).
//!
//! Every model a line can reach is held: each of a fallback list (any may be
//! the one that answers), `model-for-checking:`, and the catalogue's default
//! for an agent that pins none.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/a-setting-the-model-ignores` | a key the model's row says it never takes |
//! | `loader/a-setting-ignored-while-it-thinks` | a key the row says it drops while thinking, on an agent whose model thinks — `thinking:` low, medium or high, or not written on a model that thinks unless told |

use crate::modelkinds::{self, Row};
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;
use std::collections::BTreeMap;

pub fn check(document: &Node, builtin: &str, diags: &mut Diagnostics) {
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        return;
    };
    let rows = modelkinds::catalogue(builtin, document);
    let default = document
        .get("models")
        .and_then(|m| m.get("default"))
        .and_then(Node::as_str)
        .map(str::to_string)
        .or_else(|| {
            pact_doc::parse_yaml(builtin, camino::Utf8Path::new("models/catalog.yaml"))
                .ok()
                .and_then(|c| c.get("default").and_then(Node::as_str).map(str::to_string))
        });
    for (agent, entry) in agents {
        let Some(settings) = entry.node.get("settings").and_then(Node::as_map) else {
            continue;
        };
        let mut models: Vec<String> = entry
            .node
            .get("model")
            .map(crate::workflows::list)
            .into_iter()
            .flatten()
            .filter_map(Node::as_str)
            .map(|s| s.trim().to_string())
            .collect();
        if models.is_empty() {
            models.extend(default.clone());
        }
        if let Some(checker) = entry.node.get("model-for-checking").and_then(Node::as_str) {
            models.push(checker.trim().to_string());
        }
        let thinking = settings
            .get("thinking")
            .and_then(|e| e.node.as_str())
            .map(str::trim);
        for model in &models {
            let Some(row) = rows.get(model) else { continue };
            let thinks = match thinking {
                Some("none") => false,
                Some(_) => true,
                None => row.thinks_unless_told,
            };
            for (key, line) in settings {
                let at = line.key_span.clone().merge(&line.node.span);
                if row.ignores.iter().any(|k| k == key) {
                    diags.push(ignored(agent, key, model, &rows, at, false));
                } else if thinks && row.ignores_while_thinking.iter().any(|k| k == key) {
                    diags.push(ignored(agent, key, model, &rows, at, true));
                }
            }
        }
    }
}

fn ignored(
    agent: &str,
    key: &str,
    model: &str,
    rows: &BTreeMap<String, Row>,
    at: Span,
    while_thinking: bool,
) -> Diagnostic {
    if while_thinking {
        return Diagnostic::error(
            "loader/a-setting-ignored-while-it-thinks",
            at,
            format!(
                "`{agent}` sets `{key}:`, and '{model}' takes no notice of it while it is \
                 thinking — which it does here, so the run would use the model's own {key} and \
                 nothing would say so."
            ),
            format!(
                "Write `thinking: none` under `settings:` to keep `{key}:` (the model then \
                 answers without reasoning first), or take `{key}:` out and let it think."
            ),
        );
    }
    let mut takes: Vec<&str> = rows
        .values()
        .filter(|r| r.kind == "language" && !r.ignores.iter().any(|k| k == key))
        .filter(|r| !r.ignores.is_empty() || !r.ignores_while_thinking.is_empty())
        .map(|r| r.name.as_str())
        .collect();
    takes.sort_unstable();
    takes.dedup();
    Diagnostic::error(
        "loader/a-setting-the-model-ignores",
        at,
        format!(
            "`{agent}` sets `{key}:`, and '{model}' takes no notice of `{key}` at all — the line \
             would change nothing about how it answers."
        ),
        if takes.is_empty() {
            format!("Take `{key}:` out, or pin a model that takes it.")
        } else {
            format!(
                "Take `{key}:` out, or pin a model the catalogue says takes it: {}.",
                takes.join(", ")
            )
        },
    )
}
