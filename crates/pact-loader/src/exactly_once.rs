//! **"Exactly once" survives repetition** (law 3 of `docs/97-PRIMITIVES.md`;
//! `docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-4).
//!
//! | Rule | Severity | Fires when |
//! |---|---|---|
//! | `loader/repeated-with-no-claim` | error | a workflow stage calls a tool action that cannot be undone, with no `same-request-key`, where the call can happen more than once: a retry (`at-most:` above 1 on the call), the body of a `repeat`, or two branches of one `together` that call the same action |
//! | `loader/a-key-that-changes-every-attempt` | warning | inside a `repeat`, the argument a call's `same-request-key` names is bound from something the round itself produces — a stage inside the same `repeat`, or what the `repeat` remembers — so every round's key is new and the claim never matches |
//! | `loader/a-claim-wider-than-what-keeps-it` | warning | `same-request-key-across: the-team` or `the-workspace` in a workspace that says `durability: none` (an unwritten `durability:` assumes nothing, so it is not read as `none`) |
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
//! A key bound from the round's own output is a warning, not an error: the
//! author has written a claim, and a retry of the same round produces the same
//! output, so the same key, in any host that keeps what a round did. Whether two
//! *different* rounds aim at the same thing (and so should share a key) is an
//! intent the checker cannot see; a rolling plan whose every round posts a new
//! update is the other reading, and it is common.
//!
//! The stock memory tools, `bud/remember` and `bud/forget`, are not held by
//! the first rule: a round keeping what it learned for the next one is what a
//! `repeat`'s memory is for, and the memory is the workspace's own, not a
//! write into somebody's system.
//!
//! `same-request-key: the-call` is a claim like any other: the call's own place in
//! the run, which the host sends as the request's idempotency key ([`THE_CALL`]).
//!
//! An `each` is not repetition here: its items are different things on
//! purpose, and `identified-by:` (`loader/items-told-apart-by-position`)
//! is what makes a retried item the same item. Nor is a `together` by itself:
//! its branches are different stages, each run once, so an email in one branch
//! and a chat message in the other are two calls, not one call twice. What a
//! `together` can do is call the *same* action from two branches, side by side,
//! and that is repetition. A `together` inside a `repeat` still runs again
//! every round.

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
    /// Inside a `together`: the actions two or more of its branches call,
    /// and what was repeating around the `together` itself.
    Together {
        name: &'a str,
        twice: BTreeSet<String>,
        around: Box<Again<'a>>,
    },
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
            Some("together") => Again::Together {
                name: stage.as_str(),
                twice: called_from_two_branches(inner),
                around: Box::new(again.clone()),
            },
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
    if MEMORY_TOOLS.contains(&target) {
        return;
    }
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
    let Some(why) = repeated_because(again, target, retries) else {
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
    if let (Some(key), Again::Repeat { name, inside }) = (key, innermost_repeat(again))
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

/// `same-request-key: the-call`: the call's own place in the run (its stage, its
/// round, its item, never its attempt) is its identity. A host sends it to the
/// server as the request's idempotency key, so a retry carries the same one and
/// every other call a new one. It is the claim for a write the business gives no
/// key of its own, or one a flow means to repeat with the same arguments (a
/// reminder, a second notice on a new event).
pub const THE_CALL: &str = "the-call";

/// The stock memory tools: their writes are the workspace's own memory, which a
/// round is meant to update (module docs).
const MEMORY_TOOLS: [&str; 2] = ["bud/remember", "bud/forget"];

/// Why a call to `target` here may happen more than once, or `None`.
fn repeated_because(again: &Again, target: &str, retries: bool) -> Option<String> {
    match again {
        Again::Once if retries => Some("it may be tried again (`at-most:` above 1)".to_string()),
        Again::Once => None,
        Again::Repeat { name, .. } => Some(format!("it runs again every round of '{name}'")),
        Again::Together {
            name,
            twice,
            around,
        } => {
            if twice.contains(target) {
                Some(format!(
                    "more than one branch of '{name}' calls it, side by side"
                ))
            } else {
                repeated_because(around, target, retries)
            }
        }
    }
}

/// The `repeat` a call sits in, looking through any `together` between them.
fn innermost_repeat<'b, 'a>(again: &'b Again<'a>) -> &'b Again<'a> {
    match again {
        Again::Together { around, .. } => innermost_repeat(around),
        other => other,
    }
}

/// The `tool/action`s that two or more branches of a `together` call, anywhere
/// inside each branch.
fn called_from_two_branches(branches: &Map) -> BTreeSet<String> {
    let mut seen: BTreeSet<String> = BTreeSet::new();
    let mut twice: BTreeSet<String> = BTreeSet::new();
    for entry in branches.values() {
        let mut here: BTreeSet<String> = BTreeSet::new();
        calls_in(&entry.node, &mut here);
        for target in here {
            if !seen.insert(target.clone()) {
                twice.insert(target);
            }
        }
    }
    twice
}

fn calls_in(stage: &Node, found: &mut BTreeSet<String>) {
    if does(stage) == Some("call")
        && let Some(target) = stage.get("call").and_then(Node::as_str)
    {
        found.insert(target.trim().to_string());
    }
    if let Some(inner) = stage.get("steps").and_then(Node::as_map) {
        for entry in inner.values() {
            calls_in(&entry.node, found);
        }
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
    Diagnostic::warning(
        "loader/a-key-that-changes-every-attempt",
        at,
        format!(
            "'{workflow}/{stage}' calls '{target}', whose same-request key is `{key}`, and binds \
             `{key}` from `{from}` — something '{repeat}' produces anew each round. Every round's \
             key is different, so the claim never matches and nothing stops the second round \
             doing it again."
        ),
        format!(
            "If two rounds may aim at the same thing, bind `{key}` from something the same in \
             every round — the run's own input, or a stage before '{repeat}' — so they make the \
             same key. If every round makes a new thing (a new update, a new booking), this key \
             is right: a retry of one round still makes the same key."
        ),
    )
}

fn claims_wider_than_what_keeps_them(root: &Node, diags: &mut Diagnostics) {
    // Only a workspace that SAYS nothing survives a run is one where a wider claim
    // is kept by nothing: the schema reads an unwritten `durability:` as "PACT
    // assumes nothing", and a host may well keep claims in its own store.
    let Some(durability) = root.get("durability").and_then(Node::as_str).map(str::trim) else {
        return;
    };
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
                     says it keeps nothing outside one run (`durability: none`). A claim nobody \
                     keeps past the run cannot stop another run making the same call."
                ),
                "Write `durability: checkpoint` (or `durable-execution`) in workspace.yaml, so \
                 the claim is kept where other runs can see it, or say `this-run`."
                    .to_string(),
            ));
        }
    }
}
