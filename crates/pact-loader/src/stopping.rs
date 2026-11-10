//! **Forks and stops** (`docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-10): the
//! Store's `fork` and the Flow's `cancel`, as lines a workflow can write.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/stops-what-was-never-started-apart` | a `stop` stage's `stops:` is not `steps.<stage>.run` for a `call` with `waits-for-result: no` in the same workflow |
//! | `loader/forks-where-nothing-branches` | `forks:` on a workflow stage that is not an `each`, a `together` or a `repeat` — there is nothing there to start from a copy |
//!
//! A run only has a reference to stop when a `call` did not wait for it; every
//! other run is over by the time the next stage starts. So `stops:` names that
//! reference, and nothing else is a run.

use std::collections::BTreeMap;

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node};

use crate::teams::says_yes;
use crate::workflows::does;

/// Every rule, over the loaded document.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    let Some(workflows) = root.get("workflows").and_then(Node::as_map) else {
        return;
    };
    for (name, entry) in workflows {
        let Some(steps) = entry.node.get("steps").and_then(Node::as_map) else {
            continue;
        };
        let mut every: BTreeMap<&str, &Node> = BTreeMap::new();
        gather(steps, &mut every);
        for (stage, fields) in &every {
            if let Some(line) = fields.get("forks")
                && says_yes(Some(line))
                && !matches!(does(fields), Some("each" | "together" | "repeat"))
            {
                diags.push(Diagnostic::error(
                    "loader/forks-where-nothing-branches",
                    line.span.clone(),
                    format!(
                        "'{name}/{stage}' says `forks: yes`, and it does `{}` — one thing, \
                         once, with nothing to start from a copy.",
                        does(fields).unwrap_or("nothing")
                    ),
                    "Write `forks:` on the `each`, `together` or `repeat` whose items, \
                     branches or rounds should not see each other, or take it out."
                        .to_string(),
                ));
            }
            if does(fields) != Some("stop") {
                continue;
            }
            let Some(line) = fields.get("stops") else {
                continue; // `schema/missing-companion`, said where typed
            };
            let written = line.as_str().map(str::trim).unwrap_or("");
            let target = written
                .strip_prefix("steps.")
                .and_then(|r| r.strip_suffix(".run"))
                .filter(|s| !s.contains('.'));
            let detached = target.and_then(|t| every.get(t)).is_some_and(|f| {
                does(f) == Some("call")
                    && f.get("waits-for-result")
                        .is_some_and(|w| !says_yes(Some(w)))
            });
            if detached {
                continue;
            }
            let started: Vec<String> = every
                .iter()
                .filter(|(_, f)| {
                    does(f) == Some("call")
                        && f.get("waits-for-result")
                            .is_some_and(|w| !says_yes(Some(w)))
                })
                .map(|(s, _)| format!("`steps.{s}.run`"))
                .collect();
            let offered = if started.is_empty() {
                "nothing here starts a run without waiting for it — give the `call` you mean \
                 to stop `waits-for-result: no`"
                    .to_string()
            } else {
                format!("stop one of: {}", started.join(", "))
            };
            diags.push(Diagnostic::error(
                "loader/stops-what-was-never-started-apart",
                line.span.clone(),
                format!(
                    "'{name}/{stage}' stops `{written}`, which is not a run this workflow \
                     started without waiting for it — any other run is over before this stage \
                     starts."
                ),
                format!("Write `stops: steps.<stage>.run` for such a `call`: {offered}."),
            ));
        }
    }
}

fn gather<'a>(steps: &'a Map, into: &mut BTreeMap<&'a str, &'a Node>) {
    for (name, entry) in steps {
        into.insert(name.as_str(), &entry.node);
        if let Some(inner) = entry.node.get("steps").and_then(Node::as_map) {
            gather(inner, into);
        }
    }
}
