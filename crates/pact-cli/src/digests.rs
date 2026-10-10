//! **The two digests a workflow's run pins** (02W §7.2, DUR-2).
//!
//! A workspace's own digest (`pact_doc::digest` over the whole document) moves
//! under every meaningful change anywhere in it, so a runtime that keyed a
//! waiting run by it would refuse to resume that run after any edit at all —
//! a new eval case, a second workflow nobody calls. 02W §7.2 asks for two
//! narrower digests per workflow instead, and this module is the one place
//! they are computed, so every runtime reading `pact discover` agrees on what
//! "the same version" means:
//!
//! * **`doc-digest`** — what the run itself relies on. The canonical digest of
//!   the document with three things left out: every workflow this one never
//!   reaches, with the ports that answer one; and the owners and release
//!   settings (`owners:`, `release:` and a workflow's own `release:`), which
//!   02W leaves out of both digests because they are the release service's,
//!   not the run's. Everything else stays in:
//!   its own stages, questions and policy, the tools, agents and programs of
//!   the workspace (a program's body is in the document as its file's digest),
//!   the workspace's settings. That is wider than 02W's list (its local
//!   questions, its named policy, the actions it calls), and on purpose: a
//!   policy that `applies-to: every-agent` or a redaction rule governs the
//!   run without the workflow naming it, so leaving out what it does not name
//!   would let a change the run depends on through it.
//! * **`contract-digest`** — what its callers rely on: `accepts:`,
//!   `answers-with:`, `published-as:`, and each port that answers it with its
//!   key (`same-conversation-when:`) and its `if-still-running:`. The derived
//!   effect badge 02W also lists is not derived anywhere yet; it joins this
//!   digest when it is.
//!
//! **Which workflows one reaches.** Its own, and every workflow named by a
//! value anywhere it reaches: in its own entry, in a reached workflow's, and in
//! every collection of the workspace outside `workflows:` and `ports:` (an
//! action's `undone-by:` may name a workflow, and the action is in the
//! document). The workspace's own one-line settings (`name:` may well be a
//! workflow's name) name nothing. A
//! name is read as a whole value or as the part before the first `/` (`call:
//! <tool>/<action>`). Reading every value for a name can only keep in a
//! workflow that is not reached — more refusing, never less. Ports are not
//! read for names: a port names the workflow it starts, which is what reaches
//! the port, not what the workflow reaches.
//!
//! Both are `sha256:` digests of the canonical form, so reordering, comments
//! and moving a field between a file and its folder move neither.

use pact_doc::{Map, Node, Value};
use serde_json::{Map as JMap, Value as J};
use std::collections::BTreeSet;

/// What `pact discover` prints under `workflows`: each workflow by name, with
/// its two digests, in name order.
pub fn of(doc: &Node) -> J {
    let Some(flows) = doc.get("workflows").and_then(Node::as_map) else {
        return J::Array(Vec::new());
    };
    let mut names: Vec<&String> = flows.keys().collect();
    names.sort();
    let outside = names_outside(doc, flows);
    let list = names
        .into_iter()
        .map(|name| {
            let mut o = JMap::new();
            o.insert("name".into(), J::String(name.clone()));
            let reached = reached(name, flows, &outside);
            o.insert(
                "doc-digest".into(),
                J::String(doc_digest(doc, flows, &reached)),
            );
            o.insert(
                "contract-digest".into(),
                J::String(contract_digest(doc, name)),
            );
            J::Object(o)
        })
        .collect();
    J::Array(list)
}

/// The workflows named anywhere outside `workflows:` and `ports:` (and the
/// owners and release settings, which no digest covers).
fn names_outside(doc: &Node, flows: &Map) -> BTreeSet<String> {
    let mut found = BTreeSet::new();
    for (key, entry) in doc.as_map().into_iter().flatten() {
        // A setting of the workspace's own (`name:`, `description:`) names
        // nothing; its collections and groups are what can call a workflow.
        let scalar = !matches!(entry.node.value, Value::Map(_) | Value::List(_));
        if !scalar && !matches!(key.as_str(), "workflows" | "ports" | "owners" | "release") {
            named(&entry.node, flows, &mut found);
        }
    }
    found
}

/// `name` and every workflow it reaches.
fn reached(name: &str, flows: &Map, outside: &BTreeSet<String>) -> BTreeSet<String> {
    let mut kept: BTreeSet<String> = outside.clone();
    kept.insert(name.to_string());
    let mut todo: Vec<String> = kept.iter().cloned().collect();
    while let Some(next) = todo.pop() {
        let mut found = BTreeSet::new();
        if let Some(entry) = flows.get(&next) {
            named(&entry.node, flows, &mut found);
        }
        for more in found {
            if kept.insert(more.clone()) {
                todo.push(more);
            }
        }
    }
    kept
}

/// Every workflow `node` names, by a whole value or the part before a `/`.
fn named(node: &Node, flows: &Map, found: &mut BTreeSet<String>) {
    match &node.value {
        Value::Str(s) => {
            let s = s.trim();
            for candidate in [s, s.split('/').next().unwrap_or(s).trim()] {
                if flows.contains_key(candidate) {
                    found.insert(candidate.to_string());
                }
            }
        }
        Value::List(items) => items.iter().for_each(|i| named(i, flows, found)),
        Value::Map(map) => map.values().for_each(|e| named(&e.node, flows, found)),
        _ => {}
    }
}

fn doc_digest(doc: &Node, flows: &Map, reached: &BTreeSet<String>) -> String {
    let mut kept = doc.clone();
    if let Some(map) = kept.as_map_mut() {
        map.shift_remove("owners");
        map.shift_remove("release");
        if let Some(flows) = map.get_mut("workflows").and_then(|e| e.node.as_map_mut()) {
            flows.retain(|name, _| reached.contains(name));
            for entry in flows.values_mut() {
                if let Some(flow) = entry.node.as_map_mut() {
                    flow.shift_remove("release");
                }
            }
        }
        let gone = |port: &Node| {
            port.get("answers")
                .and_then(Node::as_str)
                .is_some_and(|a| flows.contains_key(a.trim()) && !reached.contains(a.trim()))
        };
        if let Some(ports) = map.get_mut("ports").and_then(|e| e.node.as_map_mut()) {
            ports.retain(|_, entry| !gone(&entry.node));
        }
    }
    pact_doc::digest(&kept)
}

fn contract_digest(doc: &Node, name: &str) -> String {
    let span = doc.span.clone();
    let mut contract = Node::map(Map::new(), span.clone());
    if let Some(flow) = doc.get("workflows").and_then(|w| w.get(name)) {
        for field in ["accepts", "answers-with", "published-as"] {
            if let Some(value) = flow.get(field) {
                contract.insert(field, span.clone(), value.clone());
            }
        }
    }
    let mut ports = Node::map(Map::new(), span.clone());
    for (port, entry) in doc
        .get("ports")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        if entry
            .node
            .get("answers")
            .and_then(Node::as_str)
            .map(str::trim)
            != Some(name)
        {
            continue;
        }
        let mut kept = Node::map(Map::new(), span.clone());
        for field in ["same-conversation-when", "if-still-running"] {
            if let Some(value) = entry.node.get(field) {
                kept.insert(field, span.clone(), value.clone());
            }
        }
        ports.insert(port.clone(), span.clone(), kept);
    }
    contract.insert("ports", span, ports);
    pact_doc::digest(&contract)
}
