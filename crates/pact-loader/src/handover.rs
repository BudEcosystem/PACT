//! A name nothing can be handed to.
//!
//! # Why this exists
//!
//! The `agent` answer shape lets a field hold the NAME of one of this
//! workspace's agents — `run-inputs: {takes-this-one: agent}` is the surrounding
//! system saying *which* agent should do a piece of the work, and the schema's
//! own help says what is handed over is "a name from this same tree, never a
//! place to fetch anything from".
//!
//! Putting that name to work needs a rule, and the rule is not the one the
//! static graph uses. `teams.rs` allows a delegation circle exactly when every
//! agent ON the circle writes `limits.asks-itself-at-most:`, which it can only
//! decide because the circle is written down. An agent named at run time is on
//! no written circle, so the obligation moves from the circle to the agent that
//! can be named:
//!
//! > An agent may be put to work BY VALUE only if it writes its own
//! > `limits.asks-itself-at-most:` figure.
//!
//! The harness enforces that where the value is. What the CHECKER can say —
//! before anything runs, where the author is — is the case that can never work:
//! a workspace that asks to be handed an agent's name and holds no agent that
//! could be handed over. Every name it is ever given would be refused, so the
//! line loads and does nothing, which is the failure this format refuses
//! everywhere else.
//!
//! # Why a base does not count
//!
//! `base: yes` says the agent never runs, and five doors already hold that
//! promise — `team:`, a port's `answers:`, a stage's `may-use:`, `discover` and
//! `card`. A name handed over at run time would be a sixth, so a base is not an
//! agent this check counts as handable. A workspace whose only budgeted agent is
//! abstract still cannot answer the question it is asking.
//!
//! # What it deliberately does not do
//!
//! It does not warn when SOME agents are handable and others are not. Which of
//! them the surrounding system will name is a fact about the surrounding system,
//! and refusing an author's correct line because a different agent has no figure
//! would be a warning about somebody else's document. Only the total case — no
//! agent at all — is knowable here.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;
use pact_schema::{Schema, Ty};

/// The shape whose values are the name of an agent.
const AGENT_SHAPE: &str = "agent";

/// Every place this document declares something to be an agent's name.
///
/// Found by walking the specification's own types rather than by keeping a list
/// of the five fields that carry the answer-shape vocabulary today. A sixth one
/// added to `spec/schema.yaml` joins this check by existing, which is the same
/// rule `currency.rs` and `available.rs` are written to.
fn declarations(
    node: &Node,
    group: &str,
    schema: &Schema,
    depth: usize,
    found: &mut Vec<(String, String, Span)>,
) {
    // The specification is a few levels deep and acyclic; the cap is a
    // backstop, not a design.
    if depth > 12 {
        return;
    }
    let Some(g) = schema.group(group) else { return };
    let Some(map) = node.as_map() else { return };
    for field in &g.fields {
        let Some(entry) = map.get(field.name.as_str()) else { continue };
        match &field.ty {
            Ty::MapOf(inner) => match inner.as_ref() {
                Ty::AnswerShape(shapes) => {
                    let Some(spellings) =
                        shapes.iter().find(|(n, _)| n == AGENT_SHAPE).map(|(_, s)| s)
                    else {
                        continue;
                    };
                    let Some(declared) = entry.node.as_map() else { continue };
                    for (asked, what) in declared {
                        let Some(spelt) = what.node.as_str() else { continue };
                        let spelt = spelt.trim().to_ascii_lowercase();
                        if spellings.iter().any(|s| s.eq_ignore_ascii_case(&spelt)) {
                            // The KEY the author wrote, not just the block it
                            // sits in: `run-inputs:` is where to look and
                            // `takes-this-one:` is the line that asks.
                            found.push((
                                asked.clone(),
                                field.name.clone(),
                                what.node.span.clone(),
                            ));
                        }
                    }
                }
                Ty::Group(kind) => {
                    if let Some(entries) = entry.node.as_map() {
                        for (_, e) in entries {
                            declarations(&e.node, kind, schema, depth + 1, found);
                        }
                    }
                }
                _ => {}
            },
            Ty::Group(kind) => declarations(&entry.node, kind, schema, depth + 1, found),
            Ty::ListOf(inner) => {
                if let Ty::Group(kind) = inner.as_ref()
                    && let Some(items) = entry.node.as_list()
                {
                    for item in items {
                        declarations(item, kind, schema, depth + 1, found);
                    }
                }
            }
            _ => {}
        }
    }
}

/// Whether this agent could be handed work by name.
///
/// Two halves, and both are load-bearing: it writes its own bottom, and it is
/// something that runs at all.
fn can_be_handed_work(agent: &Node) -> bool {
    let budgeted = agent
        .get("limits")
        .and_then(|l| l.get("asks-itself-at-most"))
        .is_some();
    let abstract_base = matches!(
        agent.get("base").and_then(Node::as_str).map(str::trim),
        Some("yes" | "true" | "on")
    ) || matches!(agent.get("base").map(|n| &n.value), Some(pact_doc::Value::Bool(true)));
    budgeted && !abstract_base
}

/// Warn where a workspace asks for an agent's name and holds nobody to name.
pub fn check(root: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let mut found: Vec<(String, String, Span)> = Vec::new();
    declarations(root, "workspace", schema, 0, &mut found);
    if found.is_empty() {
        return;
    }

    let agents = root.get("agents").and_then(Node::as_map);
    let handable: Vec<&String> = agents
        .map(|m| m.iter().filter(|(_, e)| can_be_handed_work(&e.node)).map(|(k, _)| k).collect())
        .unwrap_or_default();
    if !handable.is_empty() {
        return;
    }

    let total = agents.map_or(0, pact_doc::Map::len);
    for (asked, field, at) in found {
        diags.push(Diagnostic::warning(
            "loader/a-name-nothing-can-be-handed-to",
            at,
            format!(
                "`{asked}:` under `{field}:` asks to be handed the name of an agent, and no \
                 agent here can be handed work by name — a name is only put to work when the \
                 agent it names writes its own `asks-itself-at-most:` under `limits:`, and {}.",
                if total == 0 {
                    "this workspace has no agents".to_string()
                } else {
                    "none of them does".to_string()
                }
            ),
            "Write `asks-itself-at-most:` under `limits:` on the agent that should be handed \
             this work — it says how many times one request may put that agent to work, which \
             is what gives handing work by name a bottom. An agent that says `base: yes` never \
             runs, so it does not count."
                .to_string(),
        ));
    }
}
