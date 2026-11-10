//! **Every cycle has a limit, unless an owner says otherwise** (law 2 of
//! `docs/97-PRIMITIVES.md`, option A; `docs/98-PRIMITIVES-ENGINEERING-PLAN.md`
//! WP-3).
//!
//! | Rule | Severity | Fires when |
//! |---|---|---|
//! | `loader/unbounded-without-an-owner` | error | `limits.unbounded: yes` on an agent or workflow that no `owners:` entry names with an `owned-by:` |
//! | `loader/unbounded-beside-a-limit` | error | `unbounded: yes` beside `steps-at-most:` in the same block |
//! | `loader/unbounded-where-it-means-nothing` | error | `unbounded:` on a stage's own `limits:` |
//! | `loader/this-tree-may-not-stop` | note | every `unbounded: yes` that passed the three above |
//!
//! # The decision this carries out
//!
//! A language in which every program provably stops is not Turing complete,
//! and one in which none does cannot promise anything. PACT picks per agent: by
//! default every loop has a ceiling (the author's, or the default the harness
//! now hands every host), and the checker can say "this stops". An owner who
//! needs a loop that runs for as long as the work takes says `unbounded: yes`,
//! and the price is written down twice — in `owners:`, so the line cannot be
//! added without the owner's yes, and on every `pact check`, as a note that
//! does not fail a build and does not go away.
//!
//! A note and not a warning: `--deny-warnings` fails a pipeline, and a decision
//! the owner already made is not something a pipeline should keep refusing. It
//! is still printed every time, so nobody inherits the tree without being told.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node};

use crate::teams::says_yes;

/// Every rule, over the loaded document.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    let owners = root.get("owners").and_then(Node::as_map);
    for collection in ["agents", "workflows"] {
        let Some(entries) = root.get(collection).and_then(Node::as_map) else {
            continue;
        };
        for (name, entry) in entries {
            if let Some(limits) = entry.node.get("limits") {
                whole(collection, name, limits, owners, diags);
            }
            if collection == "workflows"
                && let Some(steps) = entry.node.get("steps").and_then(Node::as_map)
            {
                stages(name, steps, diags);
            }
        }
    }
}

fn whole(
    collection: &str,
    name: &str,
    limits: &Node,
    owners: Option<&Map>,
    diags: &mut Diagnostics,
) {
    let Some(line) = limits.get("unbounded") else {
        return;
    };
    if !says_yes(Some(line)) {
        return;
    }
    let what = if collection == "agents" {
        format!("the agent '{name}'")
    } else {
        format!("the workflow '{name}'")
    };
    if let Some(ceiling) = limits.get("steps-at-most") {
        diags.push(Diagnostic::error(
            "loader/unbounded-beside-a-limit",
            ceiling.span.clone(),
            format!(
                "{what} says `unbounded: yes` and `steps-at-most:` in the same block, so one \
                 of them is not true."
            ),
            "Keep `steps-at-most:` and take out `unbounded: yes`, or the other way round."
                .to_string(),
        ));
        return;
    }
    let Some(owner) = owner_of(owners, collection, name) else {
        diags.push(Diagnostic::error(
            "loader/unbounded-without-an-owner",
            line.span.clone(),
            format!(
                "{what} says `unbounded: yes`, which takes away the limit that lets this tree \
                 promise it stops. That is an owner's decision, and no entry under `owners:` \
                 names {what} with an `owned-by:`."
            ),
            format!(
                "Add to workspace.yaml:\n  owners:\n    {collection}.{name}.limits:\n      \
                 owned-by: <the person or team who decides this>\nor give {what} a \
                 `steps-at-most:` instead."
            ),
        ));
        return;
    };
    diags.push(Diagnostic::note(
        "loader/this-tree-may-not-stop",
        line.span.clone(),
        format!(
            "{what} has no step limit ({owner} decided this, under `owners:`), so nothing can \
             promise that a run of it stops. Every other loop in this tree still has one."
        ),
        "Nothing to do if this is still meant. To bring the limit back, take out \
         `unbounded: yes`, and the default applies again."
            .to_string(),
    ));
}

/// `unbounded:` on a stage means nothing: a stage's rounds are `at-most:`, and
/// the whole workflow's are the workflow's `limits:`.
fn stages(workflow: &str, steps: &Map, diags: &mut Diagnostics) {
    for (stage, entry) in steps {
        if let Some(line) = entry.node.get("limits").and_then(|l| l.get("unbounded")) {
            diags.push(Diagnostic::error(
                "loader/unbounded-where-it-means-nothing",
                line.span.clone(),
                format!(
                    "'{workflow}/{stage}' says `unbounded:` on its own `limits:`, and a stage's \
                     rounds are counted by `at-most:` beside it — nothing reads this line."
                ),
                format!(
                    "Write `unbounded: yes` under the workflow's own `limits:` (with an owner \
                     under `owners:`), or give '{stage}' an `at-most:`."
                ),
            ));
        }
        if let Some(inner) = entry.node.get("steps").and_then(Node::as_map) {
            stages(workflow, inner, diags);
        }
    }
}

/// Whoever `owners:` names for this agent's or workflow's limits: a key naming
/// it whole, its `limits`, or the `unbounded` line itself, written with dots or
/// with slashes (`agents.desk.limits`, `agents/desk`).
pub(crate) fn owner_of(owners: Option<&Map>, collection: &str, name: &str) -> Option<String> {
    let owners = owners?;
    let wanted = [
        vec![collection, name],
        vec![collection, name, "limits"],
        vec![collection, name, "limits", "unbounded"],
    ];
    owners.iter().find_map(|(key, entry)| {
        let parts: Vec<&str> = key.split(['.', '/']).map(str::trim).collect();
        if !wanted.contains(&parts) {
            return None;
        }
        entry
            .node
            .get("owned-by")
            .and_then(Node::as_str)
            .map(|o| format!("'{}'", o.trim()))
    })
}

/// Whether this workflow's own `limits:` say `unbounded: yes` — which lets its
/// `repeat`s go without `at-most:`.
pub(crate) fn workflow_is_unbounded(workflow: &Node) -> bool {
    says_yes(workflow.get("limits").and_then(|l| l.get("unbounded")))
}
