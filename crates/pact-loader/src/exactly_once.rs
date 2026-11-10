//! **"Exactly once" survives repetition** (law 3 of `docs/97-PRIMITIVES.md`;
//! `docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-4).
//!
//! | Rule | Severity | Fires when |
//! |---|---|---|
//! | `loader/repeated-with-no-claim` | error | a workflow stage calls a tool action that cannot be undone, with no `same-request-key`, where the call can happen more than once: a retry (`at-most:` above 1 on the call), the body of a `repeat`, or a branch of a `together` |
//! | `loader/a-key-that-changes-every-attempt` | error | inside a `repeat`, the argument a call's `same-request-key` names is bound from something the round itself produces — a stage inside the same `repeat`, or what the `repeat` remembers — so every round's key is new and the claim never matches |
//! | `loader/a-claim-wider-than-what-keeps-it` | warning | `same-request-key-across: the-team` or `the-workspace` in a workspace whose `durability:` keeps nothing outside one run |
//!
//! # Why
//!
//! The schema already makes a key necessary on an action that moves money.
//! What it cannot see is the context: a write with no undo is safe once and
//! not twice, and "twice" is exactly what a retry, a `repeat` and a `together`
//! are for. The second rule is the subtle one. A key is only a claim if two
//! attempts at the same thing produce the same key; bound to `steps.draft.id`
//! where `draft` runs again each round, it is a fresh key every round, and the
//! claim it seems to make never matches anything.
//!
//! An `each` is not repetition here: its items are different things on
//! purpose, and `identified-by:` (`loader/items-told-apart-by-position`)
//! is what makes a retried item the same item.

use std::collections::BTreeSet;

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node};

use crate::effects::{Level, of_action};
use crate::workflows::{does, entry_in};

/// What makes a call inside here happen more than once.
#[derive(Clone)]
enum Again<'a> {
    Once,
    /// The body of a `repeat`: its stages' names, which a key bound from them
    /// changes every round.
    Repeat {
        name: &'a str,
        inside: BTreeSet<&'a str>,
    },
    /// A branch of a `together`.
    Together(&'a str),
}

/// Every rule, over the loaded document.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    if let Some(workflows) = root.get("workflows").and_then(Node::as_map) {
        for (name, entry) in workflows {
            if let Some(steps) = entry.node.get("steps").and_then(Node::as_map) {
                walk(root, name, steps, &Again::Once, diags);
            }
        }
    }
    claims_wider_than_what_keeps_them(root, diags);
}

fn walk(root: &Node, workflow: &str, steps: &Map, again: &Again, diags: &mut Diagnostics) {
    for (stage, entry) in steps {
        let Some(fields) = entry.node.as_map() else {
            continue;
        };
        let doing = does(&entry.node);
        if doing == Some("call") {
            call(root, workflow, stage, &entry.node, again, diags);
        }
        let Some(inner) = fields.get("steps").and_then(|e| e.node.as_map()) else {
            continue;
        };
        let inside = match doing {
            Some("repeat") => Again::Repeat {
                name: stage.as_str(),
                inside: inner.keys().map(String::as_str).collect(),
            },
            Some("together") => Again::Together(stage.as_str()),
            _ => again.clone(),
        };
        walk(root, workflow, inner, &inside, diags);
    }
}

fn call(
    root: &Node,
    workflow: &str,
    stage: &str,
    fields: &Node,
    again: &Again,
    diags: &mut Diagnostics,
) {
    let Some(target) = fields.get("call").and_then(Node::as_str).map(str::trim) else {
        return;
    };
    let Some((tool, action_name)) = target.split_once('/') else {
        return;
    };
    let Some(action) = entry_in(root, "tools", tool)
        .and_then(|t| t.get("actions"))
        .and_then(|a| a.get(action_name))
    else {
        return;
    };
    let key = action
        .get("same-request-key")
        .and_then(Node::as_str)
        .map(str::trim);
    let retries = fields.get("at-most").is_some_and(|n| match &n.value {
        pact_doc::Value::Int(i) => *i > 1,
        pact_doc::Value::Str(s) => s.trim().parse::<i64>().is_ok_and(|i| i > 1),
        _ => false,
    });
    let why = match again {
        Again::Once if retries => Some("it may be tried again (`at-most:` above 1)".to_string()),
        Again::Once => None,
        Again::Repeat { name, .. } => Some(format!("it runs again every round of '{name}'")),
        Again::Together(name) => Some(format!("it is one branch of '{name}', run side by side")),
    };
    let Some(why) = why else {
        return;
    };
    let effect = of_action(action);
    let undone_here = fields.get("undone-by").is_some();
    let at = fields
        .get("call")
        .map_or_else(|| fields.span.clone(), |n| n.span.clone());
    if key.is_none() && effect.level == Level::CannotBeUndone && !undone_here {
        diags.push(Diagnostic::error(
            "loader/repeated-with-no-claim",
            at.clone(),
            format!(
                "'{workflow}/{stage}' calls '{target}', which cannot be undone, and {why} — \
                 with nothing to say two attempts are the same call, the second one does it \
                 again."
            ),
            format!(
                "Give '{target}' a `same-request-key:` naming the argument that makes two calls \
                 the same one, or give it (or this stage) an `undone-by:`."
            ),
        ));
    }
    if let (Some(key), Again::Repeat { name, inside }) = (key, again)
        && let Some(bound) = fields.get("bind").and_then(|b| b.get(key))
        && let Some(from) = bound.as_str().map(str::trim)
        && changes_every_round(from, inside)
    {
        diags.push(key_changes(
            workflow,
            stage,
            target,
            key,
            from,
            name,
            bound.span.clone(),
        ));
    }
}

/// `steps.<a stage inside the repeat>...` or `remembers....`: both are new each
/// round.
fn changes_every_round(from: &str, inside: &BTreeSet<&str>) -> bool {
    if from.starts_with("remembers.") {
        return true;
    }
    from.strip_prefix("steps.")
        .and_then(|rest| rest.split('.').next())
        .is_some_and(|s| inside.contains(s))
}

fn key_changes(
    workflow: &str,
    stage: &str,
    target: &str,
    key: &str,
    from: &str,
    repeat: &str,
    at: Span,
) -> Diagnostic {
    Diagnostic::error(
        "loader/a-key-that-changes-every-attempt",
        at,
        format!(
            "'{workflow}/{stage}' calls '{target}', whose same-request key is `{key}`, and binds \
             `{key}` from `{from}` — something '{repeat}' produces anew each round. Every round's \
             key is different, so the claim never matches and nothing stops the second round \
             doing it again."
        ),
        format!(
            "Bind `{key}` from something the same in every round — the run's own input, or a \
             stage before '{repeat}' — so two rounds aiming at the same thing make the same key."
        ),
    )
}

fn claims_wider_than_what_keeps_them(root: &Node, diags: &mut Diagnostics) {
    let durability = root
        .get("durability")
        .and_then(Node::as_str)
        .map_or("none", str::trim);
    if durability != "none" {
        return;
    }
    let Some(tools) = root.get("tools").and_then(Node::as_map) else {
        return;
    };
    for (tool, entry) in tools {
        let Some(actions) = entry.node.get("actions").and_then(Node::as_map) else {
            continue;
        };
        for (action, line) in actions {
            let Some(across) = line.node.get("same-request-key-across") else {
                continue;
            };
            let Some(scope) = across.as_str().map(str::trim) else {
                continue;
            };
            if scope == "this-run" {
                continue;
            }
            diags.push(Diagnostic::warning(
                "loader/a-claim-wider-than-what-keeps-it",
                across.span.clone(),
                format!(
                    "'{tool}/{action}' says the same call reaches `{scope}`, and this workspace \
                     keeps nothing outside one run (`durability:` is `none`, or not written). A \
                     claim nobody keeps past the run cannot stop another run making the same \
                     call."
                ),
                "Write `durability: checkpoint` (or `durable-execution`) in workspace.yaml, so \
                 the claim is kept where other runs can see it, or say `this-run`."
                    .to_string(),
            ));
        }
    }
}
