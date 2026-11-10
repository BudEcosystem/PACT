//! **Where a value came from travels with it** — the static half of law 7 of
//! `docs/97-PRIMITIVES.md` (`docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-6).
//!
//! | Rule | Severity | Fires when |
//! |---|---|---|
//! | `loader/written-from-a-source-it-refuses` | error | a workflow's remembered fact `comes-from:` a value whose origin its own `never-from:` lists — the run's input (`the customer`), a tool's answer (`tool output`), an agent's answer (`a teammate`) |
//! | `loader/hidden-from-the-ai-but-handed-to-it` | error | a workflow `hides:` a value from `the-ai` and a stage binds that value into a call to an agent |
//! | `loader/a-model-outside-the-region` | error | a workflow says `data-stays-in: <region>` and calls an agent pinned to a model the workspace's catalogue records as served somewhere else |
//!
//! # What the run adds
//!
//! These are the origins a reader of the tree can see. What only the run can
//! see — a value a tool returned, carried through the conversation into what a
//! model then wrote — is the harness's (`docs/98` WP-11). `never-from: tool
//! output` on an agent's own memory was already held for a tool action's
//! `remember-as:` (`approvals.rs`, `loader/a-tool-may-not-write-there`); this
//! adds the other three sources and the workflow's `comes-from:`.

use std::collections::BTreeMap;

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node};

use crate::workflows::{does, entry_in, list};

/// Every rule, over the loaded document.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    let Some(workflows) = root.get("workflows").and_then(Node::as_map) else {
        return;
    };
    for (name, entry) in workflows {
        let w = &entry.node;
        let Some(steps) = w.get("steps").and_then(Node::as_map) else {
            continue;
        };
        let mut every: BTreeMap<&str, &Node> = BTreeMap::new();
        gather(steps, &mut every);
        remembered_from(root, name, w.get("remembers"), &every, diags);
        for stage in every.values() {
            remembered_from(root, name, stage.get("remembers"), &every, diags);
        }
        hidden_from_the_ai(root, name, w, &every, diags);
        stays_in_its_region(root, name, w, &every, diags);
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

/// Where a binding's value comes from, in `never-from:`'s own words.
fn origin_of(root: &Node, binding: &str, stages: &BTreeMap<&str, &Node>) -> Option<&'static str> {
    if binding.starts_with("input.") || binding == "input" {
        return Some("the customer");
    }
    let stage = binding.strip_prefix("steps.")?.split('.').next()?;
    origin_of_stage(root, stages.get(stage)?)
}

/// What a stage hands back is made of what it calls: a tool's answer is `tool
/// output`, an agent's is `a teammate`'s. An `each`, a `together` or a
/// `repeat` hands back what the calls inside it answered; a call written as a
/// binding may be anything on its `may-call:`. Tool output wins a tie, being
/// the source `never-from:` exists for.
fn origin_of_stage(root: &Node, fields: &Node) -> Option<&'static str> {
    let mut found: Option<&'static str> = None;
    if does(fields) == Some("call") {
        let mut targets: Vec<&str> = fields
            .get("call")
            .and_then(Node::as_str)
            .map(str::trim)
            .into_iter()
            .collect();
        targets.extend(
            fields
                .get("may-call")
                .map(list)
                .unwrap_or_default()
                .into_iter()
                .filter_map(Node::as_str)
                .map(str::trim),
        );
        for target in targets {
            if target.contains('/') || entry_in(root, "tools", target).is_some() {
                return Some("tool output");
            }
            if entry_in(root, "agents", target).is_some() {
                found = Some("a teammate");
            }
        }
        return found;
    }
    for (_, inner) in fields
        .get("steps")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        match origin_of_stage(root, &inner.node) {
            Some("tool output") => return Some("tool output"),
            Some(o) => found = Some(o),
            None => {}
        }
    }
    found
}

fn remembered_from(
    root: &Node,
    workflow: &str,
    remembers: Option<&Node>,
    stages: &BTreeMap<&str, &Node>,
    diags: &mut Diagnostics,
) {
    let Some(facts) = remembers.and_then(Node::as_map) else {
        return;
    };
    for (fact, state) in facts {
        let Some(from) = state.node.get("comes-from") else {
            continue;
        };
        let Some(binding) = from.as_str().map(str::trim) else {
            continue;
        };
        let Some(origin) = origin_of(root, binding, stages) else {
            continue;
        };
        let refused: Vec<&str> = state
            .node
            .get("never-from")
            .map(list)
            .unwrap_or_default()
            .into_iter()
            .filter_map(Node::as_str)
            .map(str::trim)
            .collect();
        if !refused.contains(&origin) {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/written-from-a-source-it-refuses",
            from.span.clone(),
            format!(
                "'{workflow}' remembers '{fact}' from `{binding}`, which is {origin}, and \
                 '{fact}' says `never-from: {origin}`. The line that keeps a source out of \
                 memory is the one this write goes through."
            ),
            format!(
                "Remember it from something else, or take `{origin}` off '{fact}'s \
                 `never-from:` if it really may decide what is kept."
            ),
        ));
    }
}

/// `hides: {<binding>: [the-ai, ...]}`, and a call to an agent bound from it.
fn hidden_from_the_ai(
    root: &Node,
    workflow: &str,
    w: &Node,
    stages: &BTreeMap<&str, &Node>,
    diags: &mut Diagnostics,
) {
    let Some(hides) = w.get("hides").and_then(Node::as_map) else {
        return;
    };
    let from_the_ai: Vec<&str> = hides
        .iter()
        .filter(|(_, readers)| {
            list(&readers.node)
                .into_iter()
                .filter_map(Node::as_str)
                .any(|r| r.trim() == "the-ai")
        })
        .map(|(b, _)| b.as_str())
        .collect();
    if from_the_ai.is_empty() {
        return;
    }
    for (stage, fields) in stages {
        let Some(target) = fields.get("call").and_then(Node::as_str).map(str::trim) else {
            continue;
        };
        if entry_in(root, "agents", target).is_none() {
            continue;
        }
        let Some(bind) = fields.get("bind").and_then(Node::as_map) else {
            continue;
        };
        for (input, value) in bind {
            let Some(bound) = value.node.as_str().map(str::trim) else {
                continue;
            };
            let Some(hidden) = from_the_ai
                .iter()
                .find(|h| bound == **h || bound.starts_with(&format!("{h}.")))
            else {
                continue;
            };
            diags.push(Diagnostic::error(
                "loader/hidden-from-the-ai-but-handed-to-it",
                value.node.span.clone(),
                format!(
                    "'{workflow}' hides `{hidden}` from `the-ai`, and '{stage}' hands it to the \
                     agent '{target}' as `{input}` — the one reader it is hidden from."
                ),
                format!(
                    "Hand '{target}' something that is not `{hidden}`, take `the-ai` off its \
                     line under `hides:`, or call a tool or a program instead of an agent here."
                ),
            ));
        }
    }
}

/// `data-stays-in: <region>`, and an agent it calls pinned to a model the
/// workspace's catalogue records as served elsewhere.
fn stays_in_its_region(
    root: &Node,
    workflow: &str,
    w: &Node,
    stages: &BTreeMap<&str, &Node>,
    diags: &mut Diagnostics,
) {
    let Some(region) = w.get("data-stays-in").and_then(Node::as_str).map(str::trim) else {
        return;
    };
    // A binding (`input.region`) is the run's to hold: only a written region
    // can be compared here.
    if region.contains('.') {
        return;
    }
    let catalogue = root
        .get("models")
        .and_then(|m| m.get("models"))
        .and_then(Node::as_map);
    for (stage, fields) in stages {
        let Some(target) = fields.get("call").and_then(Node::as_str).map(str::trim) else {
            continue;
        };
        let Some(agent) = entry_in(root, "agents", target) else {
            continue;
        };
        for pinned in agent
            .get("model")
            .map(list)
            .unwrap_or_default()
            .into_iter()
            .filter_map(Node::as_str)
            .map(str::trim)
        {
            let Some(served) = catalogue
                .and_then(|c| c.get(pinned))
                .and_then(|m| m.node.get("served-by"))
                .and_then(|s| s.get("region"))
                .and_then(Node::as_str)
                .map(str::trim)
            else {
                continue;
            };
            if served == region {
                continue;
            }
            let at = fields
                .get("call")
                .map_or_else(|| fields.span.clone(), |n| n.span.clone());
            diags.push(Diagnostic::error(
                "loader/a-model-outside-the-region",
                at,
                format!(
                    "'{workflow}' keeps its data in '{region}', and '{stage}' calls '{target}', \
                     pinned to '{pinned}', which this workspace's catalogue says is served in \
                     '{served}'."
                ),
                format!(
                    "Pin '{target}' to a model served in '{region}', or take `model:` off it so \
                     one served there is chosen."
                ),
            ));
        }
    }
}
