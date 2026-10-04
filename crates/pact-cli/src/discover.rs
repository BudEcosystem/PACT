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

use camino::{Utf8Component, Utf8Path, Utf8PathBuf};
use pact_doc::{Entry, Node, SPEC_VERSION, Value};
use pact_loader::policy::Policy;
use serde_json::{Map, Value as J};

/// A workspace found on disk, reduced to what a runtime needs to decide.
pub struct Found {
    pub root: Utf8PathBuf,
    pub document: Node,
}

/// Walk `root` for PACT workspaces. A directory is one if it holds a
/// `workspace.yaml` (or `workspace.yml`); that single marker is the entire
/// discovery contract, so a runtime never has to guess and an author never has
/// to register — and it is the checker's marker too, read through the one
/// predicate both of them call.
pub fn find_workspaces(root: &Utf8Path, max_depth: usize) -> Vec<Utf8PathBuf> {
    let mut out = Vec::new();
    // One `Policy`, built once and lent down the walk — the same object the
    // loader answers `is_ignored` from. See the call site below for why this
    // walk asks it at all.
    let policy = Policy::default();
    walk(root, 0, max_depth, &policy, &mut out);
    out.sort();
    out
}

fn walk(
    dir: &Utf8Path,
    depth: usize,
    max_depth: usize,
    policy: &Policy,
    out: &mut Vec<Utf8PathBuf>,
) {
    if depth > max_depth {
        return;
    }
    // The SAME predicate the checker walks up with — `crate::
    // looks_like_a_workspace_root` — and not a second copy of the two file
    // names. This loop used to spell them out itself, which is one of the three
    // places that answered *what is a workspace* on its own; the checker's copy
    // accepted an `agents/` folder with no self file, so `pact check` reported an
    // agent as sitting inside a workspace this walk finds nothing in. Whatever
    // the answer becomes, it lands in one place — which is a property of the
    // code as it stands and not one anything enforces: re-inlining the two names
    // here would pass the whole suite, because every tree the tests can build
    // uses a spelling both sides already know.
    if crate::looks_like_a_workspace_root(dir) {
        out.push(dir.to_owned());
        return; // a workspace is not nested inside another workspace
    }
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for e in entries.flatten() {
        let Ok(name) = e.file_name().into_string() else {
            continue;
        };
        // The SAME list the loader skips, asked through the same function, and
        // not a second copy of two of its names. This line used to read
        // `matches!(name.as_str(), "target" | "node_modules")` — two names
        // against the loader's six, hardcoded outside the policy module that
        // invariant F-1 and AC-7.2 reserve for exactly this kind of literal.
        //
        // The divergence was audible: measured on a tree holding an identical
        // workspace under each of the six names, `pact check` told the author to
        // rename `dist/`, `build/`, `venv/` and `__pycache__/` while this walk
        // indexed the workspaces inside all four and published them to the
        // runtime — one binary giving two answers about the same six folders.
        //
        // `at_workspace_root` is false because this walk is looking for
        // workspaces, not loading one, so no directory it enumerates is the top
        // of anything yet. It only affects prose FILES, and this walk asks
        // about directories alone.
        if !e.file_type().map(|t| t.is_dir()).unwrap_or(false) {
            continue;
        }
        if policy.is_ignored(&name, true, false).is_some() {
            continue;
        }
        walk(&dir.join(name), depth + 1, max_depth, policy, out);
    }
}

/// Whether this entry says `base: yes` — something to be based on, not run.
pub(crate) fn is_base(a: &Node) -> bool {
    a.get("base").is_some_and(|n| match &n.value {
        Value::Bool(b) => *b,
        Value::Str(s) => matches!(s.trim(), "yes" | "true" | "on"),
        _ => false,
    })
}

/// The inventory the runtime indexes.
pub fn inventory(found: &Found) -> J {
    let doc = &found.document;
    let agents = doc.get("agents").and_then(Node::as_map);

    // ONE coordinate system for both location keys, settled once here. `root`
    // used to be emitted exactly as typed on the command line while `path` was
    // absolute, so `path.strip_prefix(root)` — the obvious way for a consumer to
    // ask where in the workspace an agent lives — failed on every invocation
    // that was not already absolute. See `absolutise` for the rule.
    let root = absolutise(&found.root).unwrap_or_else(|| found.root.clone());

    let mut list = Vec::new();
    for (key, entry) in agents.into_iter().flatten() {
        let a = &entry.node;
        // A base exists only to be based on. Publishing it was C8 §6 price 6's
        // measured defect: `pact:house` indexed with `"runnable": true`.
        if is_base(a) {
            continue;
        }
        let mut o = Map::new();
        o.insert("id".into(), J::String(format!("pact:{key}")));
        o.insert(
            "name".into(),
            text(a, "name").unwrap_or_else(|| J::String(key.clone())),
        );
        o.insert(
            "description".into(),
            text(a, "description").unwrap_or(J::Null),
        );
        // OBSERVED, never constructed. This line was
        // `found.root.join("agents").join(key)` — a path assembled out of the map
        // key and published for all three authoring forms, while only one of them
        // has that directory. The Expansion Rule's whole claim is that the folder
        // form, the flat file `agents/desk.yaml` and an agent written inline in
        // `workspace.yaml` are ONE document, so a runtime handed
        // `<root>/agents/desk` was sent to open a directory that does not exist
        // for two of the three. Every node carries the span of the file it was
        // really read from, so that file is what is emitted.
        o.insert("path".into(), observed_path(entry, &root));
        // What the runtime must be able to supply. It already owns models,
        // tools and skills; discovery tells it which ones this agent needs so it
        // can refuse cleanly instead of failing mid-run.
        o.insert("capabilities".into(), capabilities(a));
        o.insert("uses".into(), uses(a));
        // `model:` may be one id or an ordered fallback list (02P A2). `model`
        // stays the one a run starts on, so a reader indexing a single id is
        // not handed an array; `models` is the whole chain, in order.
        let models = model_ids(a);
        o.insert(
            "model".into(),
            models.first().map_or(J::Null, |m| J::String(m.clone())),
        );
        o.insert(
            "models".into(),
            J::Array(models.into_iter().map(J::String).collect()),
        );
        // `limits:` and `slo:` are two different questions and this line answered
        // both with the first one's data: the key said `slo` and the value was the
        // whole `limits` block, so a runtime indexing this to learn an agent's
        // LATENCY promise was handed its termination ceilings — `steps-at-most`
        // read as a service level. Both are emitted now, each with its own keys.
        o.insert(
            "limits".into(),
            a.get("limits").map(Node::to_json).unwrap_or(J::Null),
        );
        o.insert("slo".into(), latency(a));
        o.insert("team".into(), J::Array(team(a)));
        // THIS AGENT's own `evals:` line, not the workspace suite. Reading the
        // workspace made `pact discover examples/refund-desk` report
        // `evals: true` for all three agents while only one of them has the
        // line — a false positive on two of three for any runtime indexing this
        // to decide which agents are verified. The suite NAME rather than a
        // boolean, because "which checks" is the question a reader has next and
        // `evals:` was made resolvable precisely so it could not lie.
        o.insert("evals".into(), text(a, "evals").unwrap_or(J::Null));
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
    // The SAME rule as `path`, and in the same commit. These two are the only
    // keys in the object that name a place, and a consumer joins them.
    root_obj.insert("root".into(), J::String(root.to_string()));
    root_obj.insert("agents".into(), J::Array(list));
    root_obj.insert("digest".into(), J::String(pact_doc::digest(doc)));
    J::Object(root_obj)
}

/// The place inside the workspace that carries this agent's own settings.
///
/// **The published contract is exactly: a place that is on disk and inside
/// `root`, or `null`.** Deliberately not "a file" — the shape is file, or
/// directory, or null, and all three are reachable from a tree an author can
/// write today, so each is pinned by a fixture in `tests/discovery.rs`:
///
/// * the folder form — `agents/desk/agent.yaml`, the settings file inside it;
/// * the flat form — `agents/desk.yaml`, one file and no folder at all;
/// * the inline form — `workspace.yaml` itself, because that is genuinely the
///   only file the agent is written in;
/// * a folder whose settings have no file of their own yet — every field
///   carried by a sibling like `instructions.md` — gives **the folder**, which
///   is what [`pact_doc::Span::in_folder`] names and is equally on disk. A
///   consumer that blindly opens this gets a directory, so the contract says
///   "a place", and a consumer that needs a file asks the filesystem which it
///   got.
///
/// It is NOT a promise about where to write an edit back. In the folder form a
/// field can be carried by a sibling file — `description.md` beside
/// `agent.yaml` — and writing that field into the path emitted here produces a
/// tree that fails `pact check` with `loader/ambiguous-field`. Only the span of
/// the individual field can answer that question, and this is the span of the
/// agent node.
///
/// **The rule is: always absolute, lexically cleaned, and never resolved
/// through a shortcut.** Two halves, and both were wrong:
///
/// * *Absolute*, because `found.root` is whatever was typed on the command
///   line, so `pact discover .` published `./agents/x` and the same tree
///   discovered by absolute path published a different string for the same
///   agent — an index keyed on this held two entries for one agent depending on
///   the directory the runtime was started in. [`absolutise`] settles that in
///   one direction, and `root` is put through the same function so the two keys
///   stay joinable.
/// * *Never resolved*, because `std::fs::canonicalize` follows shortcuts, and
///   the loader refuses them: a symlinked `agents/desk.yaml` is reported by
///   `pact check` as `loader/symlink-skipped` — "Shortcuts are ignored because
///   they can point outside the project" — and PACT reads nothing from it. A
///   canonicalising emit published the target's path anyway, so the inventory
///   named a real, readable file OUTSIDE the workspace that PACT had never
///   opened, beside `runnable: false` and `description: null`. The link's own
///   in-workspace path is the honest answer: it is the place the author must go
///   and fix, it is the path the warning already names, and it never leaves the
///   project. The containment check below then holds that as an invariant
///   rather than a consequence.
///
/// `null` when nothing is there — a dangling shortcut, or a place outside
/// `root`. An absent answer is one a runtime can act on: read the agent from
/// the document discovery already handed it, and do not offer to open anything.
/// A present but wrong path is an answer it cannot even question — it opens it,
/// gets "no such file", and blames the tree. Null is also what `description`,
/// `model` and `evals` already say for "the author wrote none", so a consumer
/// needs one habit rather than two.
fn observed_path(entry: &Entry, root: &Utf8Path) -> J {
    let Some(p) = absolutise(&entry.node.span.file) else {
        return J::Null;
    };
    // The loader's boundary, restated as an invariant of the projection: the
    // inventory never names a place outside the workspace it is describing.
    if !p.starts_with(root) {
        return J::Null;
    }
    // `exists` follows the link, so a shortcut to a real file inside or outside
    // the project still yields the link's own in-workspace path, and a DANGLING
    // shortcut — nothing on the other end — yields `null`. That is what makes
    // "on disk" literally true of every string this field ever holds.
    if !p.exists() {
        return J::Null;
    }
    J::String(p.to_string())
}

/// Absolute and lexically cleaned, without touching the filesystem.
///
/// Relative input is joined onto the current directory; `.` components are
/// dropped and `..` pops. Purely lexical is the point: `canonicalize` would
/// also resolve shortcuts, which is the one thing the loader has already
/// refused to do (`loader/symlink-skipped`), so resolving here would let a
/// projection name a file PACT was never allowed to read. Lexical `..` removal
/// differs from the resolved answer only when a shortcut sits in the path — and
/// inside a workspace the loader has refused every one of those already.
fn absolutise(p: &Utf8Path) -> Option<Utf8PathBuf> {
    let joined = if p.is_absolute() {
        p.to_owned()
    } else {
        Utf8PathBuf::from_path_buf(std::env::current_dir().ok()?)
            .ok()?
            .join(p)
    };
    let mut out = Utf8PathBuf::new();
    for c in joined.components() {
        match c {
            Utf8Component::CurDir => {}
            Utf8Component::ParentDir => {
                out.pop();
            }
            other => out.push(other.as_str()),
        }
    }
    Some(out)
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
    o.insert(
        "context-policy".into(),
        text(a, "context-policy").unwrap_or(J::Null),
    );
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
    let Some(limits) = a.get("limits") else {
        return J::Null;
    };
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
    // A base has nothing to publish: `base: yes` says nothing can run it, so a
    // card — an invitation to invoke — would be a lie with a URL on it.
    if is_base(a) {
        return None;
    }
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
    card.insert(
        "url".into(),
        J::String(format!("{base_url}/pact/{agent_key}")),
    );
    card.insert("skills".into(), J::Array(skills));
    let mut meta = Map::new();
    meta.insert("source".into(), J::String("pact".into()));
    meta.insert("capabilities".into(), capabilities(a));
    card.insert("metadata".into(), J::Object(meta));
    Some(J::Object(card))
}

/// The agent's `model:` as ids, in order: one id, a fallback list, or nothing.
fn model_ids(a: &Node) -> Vec<String> {
    match a.get("model").map(|m| &m.value) {
        Some(Value::List(items)) => items
            .iter()
            .filter_map(|n| n.as_str().map(str::to_string))
            .collect(),
        Some(Value::Str(s)) => vec![s.clone()],
        _ => Vec::new(),
    }
}

fn text(n: &Node, key: &str) -> Option<J> {
    n.get(key)
        .and_then(Node::as_str)
        .map(|s| J::String(s.to_string()))
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
                Value::Str(s) if k == "reasoning" => tags.push(J::String(format!("reasoning:{s}"))),
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
            items
                .iter()
                .filter_map(|i| i.as_str().map(|s| J::String(s.into())))
                .collect(),
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
