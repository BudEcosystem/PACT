//! Auto-discovery for `gaia-ai-runtime` (decision D2, AC-6.1).
//!
//! The runtime must be able to find and run a PACT tree **with no build step**
//! and **no per-agent registration**. That is the whole content of D2: the tree
//! is the native form, so discovery is a filesystem walk plus a projection, not
//! a compile.
//!
//! Two projections are emitted:
//!
//! * an **inventory** — what agents exist, what each needs, what it may use, and
//!   what it must pass — which is what the runtime indexes and schedules;
//! * an **A2A Agent Card** per agent, so an agent is discoverable through the
//!   facade the runtime already publishes rather than a second catalogue.
//!
//! Nothing here reads `.pact/`. Deleting the cache costs time, never
//! correctness.

use camino::{Utf8Path, Utf8PathBuf};
use pact_diag::Diagnostics;
use pact_doc::{Node, SPEC_VERSION, Value};
use pact_loader::Loader;
use serde_json::{Map, Value as J};

/// A workspace found on disk, reduced to what a runtime needs to decide.
pub struct Found {
    pub root: Utf8PathBuf,
    pub document: Node,
}

/// Walk `root` for PACT workspaces. A directory is one if it holds a
/// `workspace.yaml`; that single marker is the entire discovery contract, so a
/// runtime never has to guess and an author never has to register.
pub fn find_workspaces(root: &Utf8Path, max_depth: usize) -> Vec<Utf8PathBuf> {
    let mut out = Vec::new();
    walk(root, 0, max_depth, &mut out);
    out.sort();
    out
}

fn walk(dir: &Utf8Path, depth: usize, max_depth: usize, out: &mut Vec<Utf8PathBuf>) {
    if depth > max_depth {
        return;
    }
    for stem in ["workspace.yaml", "workspace.yml"] {
        if dir.join(stem).exists() {
            out.push(dir.to_owned());
            return; // a workspace is not nested inside another workspace
        }
    }
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    for e in entries.flatten() {
        let Ok(name) = e.file_name().into_string() else { continue };
        if name.starts_with('.') || matches!(name.as_str(), "target" | "node_modules") {
            continue;
        }
        if e.file_type().map(|t| t.is_dir()).unwrap_or(false) {
            walk(&dir.join(name), depth + 1, max_depth, out);
        }
    }
}

pub fn load(root: &Utf8Path, diags: &mut Diagnostics) -> Option<Found> {
    Loader::new(root.to_owned())
        .load(root, diags)
        .map(|document| Found { root: root.to_owned(), document })
}

/// The inventory the runtime indexes.
pub fn inventory(found: &Found) -> J {
    let doc = &found.document;
    let agents = doc.get("agents").and_then(Node::as_map);

    let mut list = Vec::new();
    for (key, entry) in agents.into_iter().flatten() {
        let a = &entry.node;
        let mut o = Map::new();
        o.insert("id".into(), J::String(format!("pact:{key}")));
        o.insert("name".into(), text(a, "name").unwrap_or_else(|| J::String(key.clone())));
        o.insert("description".into(), text(a, "description").unwrap_or(J::Null));
        o.insert("path".into(), J::String(found.root.join("agents").join(key).to_string()));
        // What the runtime must be able to supply. It already owns models,
        // tools and skills; discovery tells it which ones this agent needs so it
        // can refuse cleanly instead of failing mid-run.
        o.insert("capabilities".into(), capabilities(a));
        o.insert("uses".into(), uses(a));
        o.insert("model".into(), text(a, "model").unwrap_or(J::Null));
        // `limits:` and `slo:` are two different questions and this line answered
        // both with the first one's data: the key said `slo` and the value was the
        // whole `limits` block, so a runtime indexing this to learn an agent's
        // LATENCY promise was handed its termination ceilings — `steps-at-most`
        // read as a service level. Both are emitted now, each with its own keys.
        o.insert("limits".into(), a.get("limits").map(Node::to_json).unwrap_or(J::Null));
        o.insert("slo".into(), latency(a));
        o.insert("team".into(), J::Array(team(a)));
        // THIS AGENT's own `evals:` line, not the workspace suite. Reading the
        // workspace made `pact discover examples/refund-desk` report
        // `evals: true` for all three agents while only one of them has the
        // line — a false positive on two of three for any runtime indexing this
        // to decide which agents are verified. The suite NAME rather than a
        // boolean, because "which checks" is the question a reader has next and
        // `evals:` was made resolvable precisely so it could not lie.
        o.insert(
            "evals".into(),
            text(a, "evals").unwrap_or(J::Null),
        );
        // WHETHER IT IS GOVERNED, and by what. None of this was emitted, so a
        // runtime indexing the inventory to route work could not tell an agent
        // that stops to ask a person from one that does not, could not see that a
        // redaction rule applies to its traffic, and could not learn that it
        // delegates. Each is the author's own name, so the runtime can fetch the
        // document by it; a boolean would answer "is it governed" and not "how".
        o.insert("governance".into(), governance(a));
        o.insert("runnable".into(), J::Bool(a.get("instructions").is_some()));
        list.push(J::Object(o));
    }

    let mut root_obj = Map::new();
    // `pact_doc::SPEC_VERSION`, not a literal. This line WAS the literal, and it
    // meant the index and the document could come to claim different versions of
    // the same format with nothing comparing them.
    root_obj.insert("apiVersion".into(), J::String(SPEC_VERSION.to_string()));
    root_obj.insert("kind".into(), J::String("Inventory".into()));
    root_obj.insert("workspace".into(), text(doc, "name").unwrap_or(J::Null));
    root_obj.insert("root".into(), J::String(found.root.to_string()));
    root_obj.insert("agents".into(), J::Array(list));
    root_obj.insert("digest".into(), J::String(pact_doc::digest(doc)));
    J::Object(root_obj)
}

/// What governs this agent, by the author's own names.
///
/// Emitted because the inventory is what a runtime routes on, and it carried
/// nothing about governance at all: `policy:`, `interceptors:`, `teamwork:` and
/// `remembers:` were all absent, so a host choosing between two agents could not
/// see that one of them stops for a person before moving money.
///
/// Names and not contents. A runtime that needs the rules reads `pact show`; what
/// it needs HERE is enough to decide, and enough to fetch the rest by.
fn governance(a: &Node) -> J {
    let mut o = Map::new();
    o.insert("policy".into(), text(a, "policy").unwrap_or(J::Null));
    o.insert("context-policy".into(), text(a, "context-policy").unwrap_or(J::Null));
    for key in ["interceptors", "remembers"] {
        let listed = a.get(key).map(|n| match n.to_json() {
            // `interceptors:` is a list of names; `remembers:` is a map keyed by
            // them. Both answer "which ones", so both come back as a sorted list
            // of names and a consumer needs one shape rather than two.
            J::Array(items) => J::Array(items),
            J::Object(map) => {
                let mut names: Vec<String> = map.keys().cloned().collect();
                names.sort();
                J::Array(names.into_iter().map(J::String).collect())
            }
            other => other,
        });
        o.insert((*key).to_string(), listed.unwrap_or(J::Array(Vec::new())));
    }
    // `teamwork:` is a block of join rules, not a name, so the honest answer is
    // whether the author wrote one — a runtime that needs the shares reads `show`.
    o.insert("teamwork".into(), J::Bool(a.get("teamwork").is_some()));
    J::Object(o)
}

/// The latency half of `limits:`, and nothing else.
///
/// `finishes-within` is deliberately in BOTH: the author's own file says it is
/// *"both the promise and, with no `runs-for-at-most` written, the wall-clock
/// stop"*, so a projection that put it in one and not the other would drop half
/// of what it means. Every other key belongs to exactly one side.
fn latency(a: &Node) -> J {
    const PROMISES: &[&str] = &[
        "feel",
        "finishes-within",
        "first-reply-within",
        "per-word-under",
        "measured-at",
    ];
    let Some(limits) = a.get("limits") else { return J::Null };
    let mut o = Map::new();
    for key in PROMISES {
        if let Some(found) = limits.get(key) {
            o.insert((*key).to_string(), found.to_json());
        }
    }
    if o.is_empty() { J::Null } else { J::Object(o) }
}

/// Project one agent to an A2A Agent Card.
///
/// Deliberately a *facade*: instructions, filesystem paths and credential
/// bindings are not projected. A card is for discovery and invocation, not an
/// internal dump — the same rule the runtime's existing card projection follows.
pub fn agent_card(found: &Found, agent_key: &str, base_url: &str) -> Option<J> {
    let a = found.document.get("agents")?.get(agent_key)?;
    let name = a.get("name").and_then(Node::as_str).unwrap_or(agent_key);

    let mut skills = Vec::new();
    if let Some(J::Array(items)) = Some(uses(a)) {
        for u in items {
            if let J::String(s) = u {
                let mut sk = Map::new();
                sk.insert("id".into(), J::String(s.clone()));
                sk.insert("name".into(), J::String(s.clone()));
                sk.insert("description".into(), J::String(format!("uses {s}")));
                sk.insert("tags".into(), J::Array(vec![J::String("pact".into())]));
                skills.push(J::Object(sk));
            }
        }
    }
    for member in team(a) {
        if let J::String(m) = member {
            let mut sk = Map::new();
            sk.insert("id".into(), J::String(format!("handoff:{m}")));
            sk.insert("name".into(), J::String(m.clone()));
            sk.insert("description".into(), J::String(format!("delegates to {m}")));
            sk.insert("tags".into(), J::Array(vec![J::String("handoff".into())]));
            skills.push(J::Object(sk));
        }
    }

    let mut card = Map::new();
    card.insert("protocolVersion".into(), J::String("1.0".into()));
    card.insert("name".into(), J::String(name.to_string()));
    card.insert(
        "description".into(),
        text(a, "description").unwrap_or(J::String(String::new())),
    );
    card.insert("url".into(), J::String(format!("{base_url}/pact/{agent_key}")));
    card.insert("skills".into(), J::Array(skills));
    let mut meta = Map::new();
    meta.insert("source".into(), J::String("pact".into()));
    meta.insert("capabilities".into(), capabilities(a));
    card.insert("metadata".into(), J::Object(meta));
    Some(J::Object(card))
}

fn text(n: &Node, key: &str) -> Option<J> {
    n.get(key).and_then(Node::as_str).map(|s| J::String(s.to_string()))
}

/// Capability *requirements*, flattened to the tags a registry can index.
fn capabilities(a: &Node) -> J {
    let mut tags = Vec::new();
    if let Some(needs) = a.get("needs").and_then(Node::as_map) {
        for (k, e) in needs {
            match &e.node.value {
                Value::Str(s) if matches!(s.as_str(), "yes" | "true" | "on") => {
                    tags.push(J::String(k.clone()))
                }
                Value::Bool(true) => tags.push(J::String(k.clone())),
                Value::Str(s) if k == "reasoning" => {
                    tags.push(J::String(format!("reasoning:{s}")))
                }
                _ => {}
            }
        }
    }
    tags.sort_by_key(std::string::ToString::to_string);
    J::Array(tags)
}

fn uses(a: &Node) -> J {
    match a.get("uses").map(|n| &n.value) {
        Some(Value::List(items)) => J::Array(
            items.iter().filter_map(|i| i.as_str().map(|s| J::String(s.into()))).collect(),
        ),
        Some(Value::Str(s)) => J::Array(vec![J::String(s.clone())]),
        _ => J::Array(vec![]),
    }
}

fn team(a: &Node) -> Vec<J> {
    a.get("team")
        .and_then(Node::as_map)
        .map(|m| m.keys().map(|k| J::String(k.clone())).collect())
        .unwrap_or_default()
}
