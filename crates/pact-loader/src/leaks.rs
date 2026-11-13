//! **Leaks and collisions** (`docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-13):
//! the Check primitive's reachability, and the Actor's declared write set.
//!
//! | Rule | Severity | Fires when |
//! |---|---|---|
//! | `loader/three-things-that-make-a-leak` | error | an agent can reach — itself, through its team, or through an agent its work wakes (`docs/99`) — tools that carry `private-data`, `untrusted-content` and `a-way-out`, and an action of a way-out tool writes with no person's yes before it |
//! | `loader/two-branches-write-the-same-place` | warning | two branches of a `together`, or the items of an `each`, call actions that `writes:` the same place, with no `same-request-key:` making them one call |
//!
//! # The leak
//!
//! The lethal trifecta: text a stranger wrote can tell a model to read
//! somebody's records and send them out, and each of the three tools that make
//! that possible is harmless alone. Allowance cannot see it — every step is
//! permitted — and Origin at run time sees it only after the fact. What the
//! checker can see is that one agent reaches all three, and whether a person
//! stands at the door out. If one does, a stranger's sentence can at most make
//! the agent ASK to send, and a person reads the request.

use std::collections::BTreeSet;

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node};

use crate::money::guarded_by;
use crate::teams::says_yes;
use crate::workflows::{does, entry_in, list};

/// Every rule, over the loaded document.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    leaks(root, diags);
    collisions(root, diags);
}

fn carries(tool: &Node) -> Vec<String> {
    tool.get("carries")
        .map(list)
        .unwrap_or_default()
        .into_iter()
        .filter_map(Node::as_str)
        .map(|s| s.trim().to_string())
        .collect()
}

/// The agents each agent's work WAKES (`docs/99` §2): the ones a reaction that
/// covers it consults or tells, and every other agent that `listens-for:`
/// something. What the first agent read is put in front of the second, so for
/// a leak the second is reached exactly as a teammate is — and it is the edge
/// nobody wrote in the first agent's own file.
fn woken<'a>(root: &'a Node, agents: &'a Map) -> std::collections::BTreeMap<&'a str, Vec<&'a str>> {
    let listeners: Vec<&str> = agents
        .iter()
        .filter(|(_, a)| a.node.get("listens-for").map(list).is_some_and(|l| !l.is_empty()))
        .map(|(name, _)| name.as_str())
        .collect();
    let reactions = root.get("reactions").and_then(Node::as_map);
    let mut out = std::collections::BTreeMap::new();
    for (name, agent) in agents {
        let mut wakes: Vec<&str> = listeners.iter().copied().filter(|l| *l != name).collect();
        let named: Vec<&str> = agent
            .node
            .get("reactions")
            .map(list)
            .unwrap_or_default()
            .into_iter()
            .filter_map(Node::as_str)
            .map(str::trim)
            .collect();
        for (id, reaction) in reactions.into_iter().flatten() {
            let everyone = reaction.node.get("applies-to").and_then(Node::as_str).map(str::trim)
                == Some("every-agent");
            if !everyone && !named.contains(&id.as_str()) {
                continue;
            }
            for step in reaction.node.get("then").map(list).unwrap_or_default() {
                for verb in ["consult", "tell"] {
                    if let Some(who) = step.get(verb).and_then(Node::as_str).map(str::trim)
                        && who != name
                    {
                        wakes.push(who);
                    }
                }
            }
        }
        out.insert(name.as_str(), wakes);
    }
    out
}

/// Every `(agent, tool)` an agent reaches: its own `uses:`, its team's, and
/// those of every agent its work wakes.
fn reached<'a>(
    agents: &'a Map,
    wakes: &std::collections::BTreeMap<&'a str, Vec<&'a str>>,
    name: &'a str,
    seen: &mut BTreeSet<&'a str>,
    out: &mut Vec<(&'a str, String)>,
) {
    if !seen.insert(name) {
        return;
    }
    let Some(agent) = agents.get(name) else {
        return;
    };
    for used in agent
        .node
        .get("uses")
        .map(list)
        .unwrap_or_default()
        .into_iter()
        .filter_map(Node::as_str)
    {
        out.push((name, used.trim().to_string()));
    }
    for member in agent
        .node
        .get("team")
        .and_then(Node::as_map)
        .into_iter()
        .flat_map(|m| m.keys())
    {
        reached(agents, wakes, member, seen, out);
    }
    for woken in wakes.get(name).into_iter().flatten() {
        reached(agents, wakes, woken, seen, out);
    }
}

fn leaks(root: &Node, diags: &mut Diagnostics) {
    let Some(agents) = root.get("agents").and_then(Node::as_map) else {
        return;
    };
    let policies = root.get("policies").and_then(Node::as_map);
    let wakes = woken(root, agents);
    for (name, entry) in agents {
        if says_yes(entry.node.get("base")) {
            continue;
        }
        let mut seen = BTreeSet::new();
        let mut uses = Vec::new();
        reached(agents, &wakes, name, &mut seen, &mut uses);
        let mut found: BTreeSet<String> = BTreeSet::new();
        let mut by_what: Vec<(String, String)> = Vec::new();
        for (_, tool) in &uses {
            if let Some(t) = entry_in(root, "tools", tool) {
                for c in carries(t) {
                    by_what.push((c.clone(), tool.clone()));
                    found.insert(c);
                }
            }
        }
        if found.len() < 3 {
            continue;
        }
        // Every way out, and whether each of its writing actions has a person
        // before it: `needs-a-person: yes`, or an approval rule over the agent
        // that uses it naming the tool or the action.
        let mut open: Vec<String> = Vec::new();
        for (user, tool) in &uses {
            let Some(t) = entry_in(root, "tools", tool) else {
                continue;
            };
            if !carries(t).iter().any(|c| c == "a-way-out") {
                continue;
            }
            let guarded = agents
                .get(*user)
                .and_then(|a| guarded_by(&a.node, policies))
                .unwrap_or_default();
            for (action, line) in t
                .get("actions")
                .and_then(Node::as_map)
                .into_iter()
                .flatten()
            {
                if says_yes(line.node.get("reads-only"))
                    || says_yes(line.node.get("needs-a-person"))
                {
                    continue;
                }
                let key = format!("{tool}/{action}");
                if guarded.contains(tool) || guarded.contains(&key) {
                    continue;
                }
                open.push(key);
            }
        }
        if open.is_empty() {
            continue;
        }
        let said = |what: &str| {
            by_what
                .iter()
                .filter(|(c, _)| c == what)
                .map(|(_, t)| format!("'{t}'"))
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect::<Vec<_>>()
                .join(", ")
        };
        diags.push(Diagnostic::error(
            "loader/three-things-that-make-a-leak",
            entry.key_span.clone(),
            format!(
                "'{name}' can reach private data ({}), content a stranger wrote ({}) and a way \
                 out ({}) — so a sentence in that content can tell it to send the data out, \
                 and nothing stands in the way: {} send with nobody asked.",
                said("private-data"),
                said("untrusted-content"),
                said("a-way-out"),
                open.iter()
                    .map(|k| format!("`{k}`"))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            "Put a person at the door out — `needs-a-person: yes` on each of those actions, or \
             an approval rule in `policies/` naming them — or take one of the three tools away \
             from this agent, its team, and the agents that are asked or told about its work."
                .to_string(),
        ));
    }
}

/// The places a call writes, and whether it is one call however often it is made.
fn writes_of(root: &Node, target: &str) -> Option<(Vec<String>, bool)> {
    let (tool, action) = target.split_once('/')?;
    let line = entry_in(root, "tools", tool)?.get("actions")?.get(action)?;
    let places: Vec<String> = line
        .get("writes")
        .map(list)
        .unwrap_or_default()
        .into_iter()
        .filter_map(Node::as_str)
        .map(|s| s.trim().to_string())
        .collect();
    Some((places, line.get("same-request-key").is_some()))
}

/// Every `(place, tool/action)` a block of stages writes without a claim.
fn unclaimed_writes(root: &Node, steps: &Map, out: &mut Vec<(String, String)>) {
    for entry in steps.values() {
        let fields = &entry.node;
        if does(fields) == Some("call")
            && let Some(target) = fields.get("call").and_then(Node::as_str).map(str::trim)
            && let Some((places, claimed)) = writes_of(root, target)
            && !claimed
        {
            out.extend(places.into_iter().map(|p| (p, target.to_string())));
        }
        if let Some(inner) = fields.get("steps").and_then(Node::as_map) {
            unclaimed_writes(root, inner, out);
        }
    }
}

fn collisions(root: &Node, diags: &mut Diagnostics) {
    let Some(workflows) = root.get("workflows").and_then(Node::as_map) else {
        return;
    };
    for (name, entry) in workflows {
        if let Some(steps) = entry.node.get("steps").and_then(Node::as_map) {
            collide(root, name, steps, diags);
        }
    }
}

fn collide(root: &Node, workflow: &str, steps: &Map, diags: &mut Diagnostics) {
    for (stage, entry) in steps {
        let fields = &entry.node;
        let Some(inner) = fields.get("steps").and_then(Node::as_map) else {
            continue;
        };
        match does(fields) {
            Some("together") => {
                let mut seen: Vec<(String, String, String)> = Vec::new();
                for (branch, b) in inner {
                    let mut mine = Vec::new();
                    let one: Map = std::iter::once((branch.clone(), b.clone())).collect();
                    unclaimed_writes(root, &one, &mut mine);
                    for (place, target) in mine {
                        if let Some((_, other, other_target)) =
                            seen.iter().find(|(p, o, _)| *p == place && o != branch)
                        {
                            diags.push(clash(
                                workflow,
                                stage,
                                &place,
                                &format!(
                                    "the branches '{other}' (`{other_target}`) and '{branch}' \
                                     (`{target}`)"
                                ),
                                fields,
                            ));
                        }
                        seen.push((place, branch.clone(), target));
                    }
                }
            }
            Some("each") => {
                let one_at_a_time = fields
                    .get("limits")
                    .and_then(|l| l.get("at-once-at-most"))
                    .is_some_and(|n| matches!(&n.value, pact_doc::Value::Int(1)));
                if !one_at_a_time {
                    let mut mine = Vec::new();
                    unclaimed_writes(root, inner, &mut mine);
                    if let Some((place, target)) = mine.first() {
                        diags.push(clash(
                            workflow,
                            stage,
                            place,
                            &format!("its items, each calling `{target}` side by side"),
                            fields,
                        ));
                    }
                }
            }
            _ => {}
        }
        collide(root, workflow, inner, diags);
    }
}

fn clash(workflow: &str, stage: &str, place: &str, who: &str, fields: &Node) -> Diagnostic {
    Diagnostic::warning(
        "loader/two-branches-write-the-same-place",
        fields
            .get("does")
            .map_or_else(|| fields.span.clone(), |n| n.span.clone()),
        format!(
            "'{workflow}/{stage}' runs {who} at the same time, and both write '{place}' — \
             whichever finishes second decides what is there."
        ),
        "Give the action a `same-request-key:` so two attempts at the same thing are one call, \
         run them one after the other (`at-once-at-most: 1` on an `each`), or have them write \
         different places."
            .to_string(),
    )
}
