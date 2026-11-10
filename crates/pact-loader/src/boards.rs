//! **The team store** (`docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-8): memory a
//! lead shares with its team, written only through an admission gate.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/shared-with-no-team` | an agent remembers a fact `shared-with: the-team` and has no `team:` |
//! | `loader/shared-where-it-means-nothing` | `shared-with:` on memory that is not an agent's — the workspace's, a workflow's, a port's or a stage's |
//! | `loader/admission-on-memory-nobody-shares` | `admitted-when:` or `admitted-by:` on a fact that is not `shared-with: the-team`, where nothing writes through the gate |
//! | `loader/an-admitter-that-cannot-say-yes` | `admitted-by:` names an agent whose `answers-with:` has no `yes or no` line |
//! | `loader/admitted-when-reads-no-part` | an `admitted-when:` line reads something other than `entry.<part>`, or a part `shaped-like:` does not have |
//!
//! # Why a gate and not just a store
//!
//! `docs/remediation/F7` refused a blackboard because nothing an agent wrote
//! could be read by another. `docs/92-SWARM.md` §6.3 said what a store would
//! need if it were ever added: "The accuracy lives in the admission gate, not
//! the queue" — a shared store without a check on what goes in reproduces the
//! systems that measured no benefit. So the store is declared with its gate,
//! and these rules hold that the gate can actually be applied.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node};
use pact_schema::Schema;
use pact_schema::shape::{self, Shape};

use crate::workflows::list;

/// Every rule, over the loaded document.
pub fn check(root: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let vocabulary = shape::vocabulary(schema);
    let named: Vec<&str> = root
        .get("shapes")
        .and_then(Node::as_map)
        .map(|m| m.keys().map(String::as_str).collect())
        .unwrap_or_default();
    let agents = root.get("agents").and_then(Node::as_map);
    for (name, entry) in agents.into_iter().flatten() {
        let has_team = entry
            .node
            .get("team")
            .and_then(Node::as_map)
            .is_some_and(|t| !t.is_empty());
        let Some(facts) = entry.node.get("remembers").and_then(Node::as_map) else {
            continue;
        };
        for (fact, state) in facts {
            let shared = state.node.get("shared-with");
            let to_team = shared.and_then(Node::as_str).map(str::trim) == Some("the-team");
            if to_team && !has_team {
                diags.push(Diagnostic::error(
                    "loader/shared-with-no-team",
                    shared.map_or_else(|| state.key_span.clone(), |n| n.span.clone()),
                    format!(
                        "'{name}' shares '{fact}' with its team, and '{name}' has no `team:` — \
                         there is nobody to share it with."
                    ),
                    format!(
                        "Give '{name}' a `team:`, or take out `shared-with: the-team` so '{fact}' \
                         is its own."
                    ),
                ));
            }
            for line in ["admitted-when", "admitted-by"] {
                if let Some(n) = state.node.get(line)
                    && !to_team
                {
                    diags.push(Diagnostic::error(
                        "loader/admission-on-memory-nobody-shares",
                        n.span.clone(),
                        format!(
                            "'{fact}', which '{name}' remembers, says `{line}:`, and it is not \
                             `shared-with: the-team` — nothing writes to it through the gate this \
                             line sets."
                        ),
                        format!("Write `shared-with: the-team` beside it, or take `{line}:` out."),
                    ));
                }
            }
            if let Some(judge) = state.node.get("admitted-by") {
                admitter_says_yes(root, name, fact, judge, &vocabulary, &named, diags);
            }
            if let Some(lines) = state.node.get("admitted-when") {
                reads_parts(name, fact, &state.node, lines, diags);
            }
        }
    }
    // Memory that is not an agent's: sharing it means nothing.
    for (who, block) in elsewhere(root) {
        for (fact, state) in block {
            if let Some(n) = state.node.get("shared-with") {
                diags.push(Diagnostic::error(
                    "loader/shared-where-it-means-nothing",
                    n.span.clone(),
                    format!(
                        "'{fact}' is {who}'s memory, and only an agent's memory is shared with a \
                         team — nothing reads `shared-with:` here."
                    ),
                    "Take `shared-with:` out, or move the fact under the `remembers:` of the \
                     agent whose team shares it."
                        .to_string(),
                ));
            }
        }
    }
}

/// Every `remembers:` block that is not an agent's, with whose it is.
fn elsewhere(root: &Node) -> Vec<(String, &Map)> {
    let mut out = Vec::new();
    if let Some(m) = root.get("remembers").and_then(Node::as_map) {
        out.push(("the workspace".to_string(), m));
    }
    for (collection, what) in [("workflows", "the workflow"), ("ports", "the port")] {
        for (name, entry) in root
            .get(collection)
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            if let Some(m) = entry.node.get("remembers").and_then(Node::as_map) {
                out.push((format!("{what} '{name}'"), m));
            }
            if collection == "workflows"
                && let Some(steps) = entry.node.get("steps").and_then(Node::as_map)
            {
                stage_memory(name, steps, &mut out);
            }
        }
    }
    out
}

fn stage_memory<'a>(workflow: &str, steps: &'a Map, out: &mut Vec<(String, &'a Map)>) {
    for (stage, entry) in steps {
        if let Some(m) = entry.node.get("remembers").and_then(Node::as_map) {
            out.push((format!("the stage '{workflow}/{stage}'"), m));
        }
        if let Some(inner) = entry.node.get("steps").and_then(Node::as_map) {
            stage_memory(workflow, inner, out);
        }
    }
}

fn admitter_says_yes(
    root: &Node,
    agent: &str,
    fact: &str,
    judge: &Node,
    vocabulary: &[(String, Vec<String>)],
    named: &[&str],
    diags: &mut Diagnostics,
) {
    let Some(judge_name) = judge.as_str().map(str::trim) else {
        return;
    };
    // A name the workspace lacks is `schema/no-such-name`, said where typed.
    let Some(judge_entry) = root
        .get("agents")
        .and_then(Node::as_map)
        .and_then(|a| a.get(judge_name))
    else {
        return;
    };
    let says_yes = judge_entry
        .node
        .get("answers-with")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .any(|(_, e)| {
            e.node
                .as_str()
                .and_then(|w| shape::parse(w, vocabulary, named).ok())
                .is_some_and(|l| l.shape == Shape::Plain("yes-or-no".to_string()))
        });
    if says_yes {
        return;
    }
    diags.push(Diagnostic::error(
        "loader/an-admitter-that-cannot-say-yes",
        judge.span.clone(),
        format!(
            "'{fact}', which '{agent}' shares with its team, is admitted by '{judge_name}', and \
             '{judge_name}' answers with no `yes or no` line — so no answer of its can let an \
             entry in or keep one out."
        ),
        format!(
            "Give '{judge_name}' `answers-with:` a line like `admit: yes or no` (and a \
             `because: text` beside it, which the writer is shown on a no)."
        ),
    ));
}

fn reads_parts(agent: &str, fact: &str, state: &Node, lines: &Node, diags: &mut Diagnostics) {
    let parts: Option<Vec<&str>> = state
        .get("shaped-like")
        .and_then(Node::as_map)
        .map(|m| m.keys().map(String::as_str).collect());
    for line in list(lines) {
        let Some(value) = line.get("value") else {
            continue;
        };
        let Some(read) = value.as_str().map(str::trim) else {
            continue;
        };
        let part = read
            .strip_prefix("entry.")
            .map(|p| p.split('.').next().unwrap_or(p));
        let fine = match (part, &parts) {
            (Some(p), Some(parts)) => parts.contains(&p),
            (Some(_), None) => true,
            (None, _) => false,
        };
        if fine {
            continue;
        }
        let offered = parts.as_ref().map_or_else(
            || "`entry.<part>`".to_string(),
            |p| {
                p.iter()
                    .map(|x| format!("`entry.{x}`"))
                    .collect::<Vec<_>>()
                    .join(", ")
            },
        );
        diags.push(Diagnostic::error(
            "loader/admitted-when-reads-no-part",
            value.span.clone(),
            format!(
                "'{fact}', which '{agent}' shares, admits an entry when `{read}` holds, and the \
                 only thing an admission line can read is the entry being written."
            ),
            format!("Read one of: {offered}."),
        ));
    }
}
