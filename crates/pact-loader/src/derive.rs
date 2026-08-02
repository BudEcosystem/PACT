//! `based-on:` for every kind — restate what differs, inherit the rest (G11).
//!
//! # Why this exists
//!
//! For a round `based-on:` worked on exactly one kind, `loop`, and only for the
//! two shapes PACT ships: `spec/schema.yaml` gave it `names: []`, so a workspace
//! could not even derive one of its own loops from another. Every other kind had
//! nothing, and the cost of that showed up in the tree itself — the worked
//! example carried `interceptors/redact-card-numbers.yaml` and
//! `interceptors/redact-card-numbers-in-tool-calls.yaml` differing in **two
//! lines**, `description:` and `when:`, and holding the same `may:`, the same
//! `applies-to:` and the same two sentences. Two copies of one rule is two
//! places to add the next thing that must be hidden, and two places for them to
//! disagree.
//!
//! Eve solves the same problem for tools alone and only in TypeScript:
//! `...writeFile` spreads the framework default and your object overrides what
//! it restates (`docs/concepts/default-harness.md`). That is the right idea
//! reachable from one language, for one kind. This is the same idea as data, for
//! every kind, resolved by the loader so both ports inherit it and neither
//! implements it.
//!
//! # What it does, exactly
//!
//! For every entry of every collection, `based-on: <name>` names a sibling of
//! the same kind. The base's fields are taken, the deriving entry's fields are
//! laid over the top, and the result replaces the deriving entry. `based-on:`
//! itself is removed once resolved, so a document that has been derived reads
//! like one that was written out longhand — which is what makes the digest of
//! a derived tree comparable to the digest of an expanded one.
//!
//! **Shallow, deliberately.** A restated map replaces the base's map rather than
//! merging into it. Deep merge cannot express *removal*: an author who restates
//! `may: [hide-values]` over a base carrying `[hide-values, stop-the-run]` means
//! to take a power away, and a merge that unions them silently keeps it. Losing
//! the ability to narrow a permission is a worse failure than typing one extra
//! line, so the shallow rule is the safe one.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node, Value};
use pact_schema::{Schema, Ty};

/// Collections whose entries may derive from a sibling — computed, not written.
///
/// A collection is any workspace field typed `map of group:<kind>`. That is
/// exactly the distinction the list below used to make in prose and get wrong:
/// not every map is a collection of definitions — `steps:` inside a loop is a
/// map of stages, and a stage named `based-on` would be a stage, not a
/// derivation — but a workspace field holding named blocks of settings always
/// is, and the specification already says which those are.
///
/// The fourteen names this replaces contained four that name nothing a
/// workspace has (`watches`, `schedules`, `evals`, `redactions`) and were
/// missing two that it does (`watch`, `bundles`), so `based-on:` inside a watch
/// or a nested bundle was read, accepted by the schema, and never resolved.
fn collections(schema: &Schema) -> Vec<String> {
    let Some(workspace) = schema.group("workspace") else { return Vec::new() };
    workspace
        .fields
        .iter()
        .filter_map(|f| match &f.ty {
            Ty::MapOf(inner) => match inner.as_ref() {
                Ty::Group(_) => Some(f.name.clone()),
                _ => None,
            },
            _ => None,
        })
        .collect()
}

/// Resolve every `based-on:` in the document, in place.
pub fn resolve(root: &mut Node, schema: &Schema, diags: &mut Diagnostics) {
    let Some(top) = root.as_map_mut() else { return };
    for name in collections(schema) {
        let Some(slot) = top.get_mut(&name) else { continue };
        let Some(entries) = slot.node.as_map_mut() else { continue };
        resolve_collection(&name, entries, diags);
    }
}

fn resolve_collection(kind: &str, entries: &mut Map, diags: &mut Diagnostics) {
    let names: Vec<String> = entries.keys().cloned().collect();
    for name in &names {
        let mut seen: Vec<String> = Vec::new();
        if let Err(d) = derive_one(kind, entries, name, &mut seen) {
            diags.push(*d);
            // One mistake, one message. An entry whose base did not resolve is
            // not a half-built entry, it is a document nobody can read: it holds
            // only the fields that DIFFER from something that was never found.
            // Left in place it drew three more errors — a required `when:` it
            // was never going to restate, a required `may:` likewise, and
            // `'based-on' is not something an interceptor can have`, which is
            // only true because resolution failed. Removing it here is the same
            // move `not_a_workspace` makes in the CLI, for the same reason.
            entries.shift_remove(name);
        }
    }
}

fn derive_one(
    kind: &str,
    entries: &mut Map,
    name: &str,
    seen: &mut Vec<String>,
) -> Result<(), Box<Diagnostic>> {
    let Some(entry) = entries.get(name) else { return Ok(()) };
    let Some(map) = entry.node.as_map() else { return Ok(()) };
    let Some(base_entry) = map.get("based-on") else { return Ok(()) };
    let base_node = &base_entry.node;
    let Some(base_name) = base_node.as_str().map(str::to_owned) else { return Ok(()) };
    let base_name = base_name.trim().to_owned();
    if base_name.is_empty() || base_name.starts_with("pact:") {
        // A library shape. `loops.rs` owns those; this pass only joins entries
        // that live in the same tree.
        return Ok(());
    }

    let span = base_node.span.clone();

    // A ring is the one shape that cannot terminate, so it is refused by name
    // rather than by a recursion limit — a depth message tells an author a
    // number, and the ring tells them which files to look at.
    if seen.iter().any(|s| s == name) {
        let mut ring = seen.clone();
        ring.push(name.to_owned());
        let start = ring.iter().position(|s| s == name).unwrap_or(0);
        return Err(Box::new(Diagnostic::error(
            "loader/based-on-goes-in-a-circle",
            span,
            format!(
                "'{}' is based on itself, going {}.",
                name,
                ring[start..].join(" → ")
            ),
            "Point one of them at something else, or write that one out in full.",
        )));
    }

    if !entries.contains_key(&base_name) {
        let mut known: Vec<&String> = entries.keys().filter(|k| *k != name).collect();
        known.sort();
        let list = known.iter().map(|k| format!("`{k}`")).collect::<Vec<_>>().join(", ");
        return Err(Box::new(Diagnostic::error(
            "loader/no-such-name",
            span,
            format!("'{name}' is based on '{base_name}', and there is no such entry in `{kind}:`."),
            if list.is_empty() {
                format!("There is nothing else in `{kind}:` to be based on. Remove the line and write it out in full.")
            } else {
                format!("Change it to one of: {list} — or remove the `based-on:` line.")
            },
        )));
    }

    // The base may itself derive. Resolve it first so this entry inherits the
    // finished thing, not a half-derived one.
    seen.push(name.to_owned());
    derive_one(kind, entries, &base_name, seen)?;
    seen.pop();

    let base_map = match entries.get(&base_name).and_then(|e| e.node.as_map()) {
        Some(m) => m.clone(),
        None => return Ok(()),
    };
    let own = match entries.get(name).and_then(|e| e.node.as_map()) {
        Some(m) => m.clone(),
        None => return Ok(()),
    };

    let mut merged = base_map;
    for (k, v) in own.iter() {
        if k == "based-on" {
            continue;
        }
        merged.insert(k.clone(), v.clone());
    }
    merged.shift_remove("based-on");

    if let Some(slot) = entries.get_mut(name) {
        let keep = slot.node.span.clone();
        slot.node = Node::new(Value::Map(merged), keep);
    }
    Ok(())
}

#[cfg(test)]
mod tests {

    /// The shipped specification, which is where the collection list now lives.
    fn spec() -> Schema {
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
        assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
        s
    }
    use super::*;
    use pact_diag::Span;
    use pact_doc::Entry;

    fn span() -> Span {
        Span::whole_file(camino::Utf8Path::new("derive-test.yaml"))
    }

    fn entry(node: Node) -> Entry {
        Entry { key_span: span(), node }
    }

    fn map(pairs: &[(&str, &str)]) -> Node {
        let mut m = Map::new();
        for (k, v) in pairs {
            m.insert((*k).to_owned(), entry(Node::new(Value::Str((*v).to_owned()), span())));
        }
        Node::new(Value::Map(m), span())
    }

    fn doc(entries: &[(&str, Node)]) -> Node {
        let mut inner = Map::new();
        for (k, v) in entries {
            inner.insert((*k).to_owned(), entry(v.clone()));
        }
        let mut top = Map::new();
        top.insert("interceptors".to_owned(), entry(Node::new(Value::Map(inner), span())));
        Node::new(Value::Map(top), span())
    }

    fn interceptors(root: &Node, name: &str) -> Map {
        root.as_map()
            
            .unwrap()
            .get("interceptors")
            .unwrap()
            .node
            .as_map()
            .unwrap()
            .get(name)
            .unwrap()
            .node
            .as_map()
            .unwrap()
            .clone()
    }

    #[test]
    fn what_is_not_restated_is_inherited() {
        let mut root = doc(&[
            ("base", map(&[("description", "hides cards"), ("may", "hide-values")])),
            ("derived", map(&[("based-on", "base"), ("description", "same, on tool calls")])),
        ]);
        let mut d = Diagnostics::default();
        resolve(&mut root, &spec(), &mut d);
        let got = interceptors(&root, "derived");
        assert_eq!(got.get("may").unwrap().node.as_str(), Some("hide-values"));
        assert_eq!(got.get("description").unwrap().node.as_str(), Some("same, on tool calls"));
        assert!(!d.has_errors());
    }

    #[test]
    fn the_based_on_line_is_gone_once_it_is_resolved() {
        // So a derived document reads like one written out longhand, and its
        // digest is comparable with an expanded tree's.
        let mut root = doc(&[
            ("base", map(&[("description", "a")])),
            ("derived", map(&[("based-on", "base")])),
        ]);
        resolve(&mut root, &spec(), &mut Diagnostics::default());
        assert!(interceptors(&root, "derived").get("based-on").is_none());
    }

    #[test]
    fn a_restated_field_replaces_rather_than_merges_so_a_permission_can_be_narrowed() {
        let mut root = doc(&[
            ("base", map(&[("may", "hide-values, stop-the-run")])),
            ("derived", map(&[("based-on", "base"), ("may", "hide-values")])),
        ]);
        resolve(&mut root, &spec(), &mut Diagnostics::default());
        assert_eq!(
            interceptors(&root, "derived").get("may").unwrap().node.as_str(),
            Some("hide-values"),
            "a deep merge would union these and silently keep `stop-the-run`"
        );
    }

    #[test]
    fn a_chain_resolves_the_base_before_the_thing_that_derives_from_it() {
        let mut root = doc(&[
            ("a", map(&[("description", "root"), ("may", "hide-values")])),
            ("b", map(&[("based-on", "a"), ("description", "middle")])),
            ("c", map(&[("based-on", "b")])),
        ]);
        resolve(&mut root, &spec(), &mut Diagnostics::default());
        let c = interceptors(&root, "c");
        assert_eq!(c.get("may").unwrap().node.as_str(), Some("hide-values"));
        assert_eq!(c.get("description").unwrap().node.as_str(), Some("middle"));
    }

    #[test]
    fn a_ring_names_the_files_rather_than_a_recursion_depth() {
        let mut root = doc(&[
            ("a", map(&[("based-on", "b")])),
            ("b", map(&[("based-on", "a")])),
        ]);
        let mut d = Diagnostics::default();
        resolve(&mut root, &spec(), &mut d);
        let e = d.items().first().expect("a ring must be refused");
        assert_eq!(e.rule, "loader/based-on-goes-in-a-circle");
        assert!(e.message.contains("→"), "the ring is shown: {}", e.message);
    }

    #[test]
    fn a_name_nothing_answers_to_lists_what_is_there() {
        let mut root = doc(&[
            ("careful", map(&[("description", "a")])),
            ("mine", map(&[("based-on", "carefull")])),
        ]);
        let mut d = Diagnostics::default();
        resolve(&mut root, &spec(), &mut d);
        let e = d.items().first().expect("a typo must be refused");
        assert_eq!(e.rule, "loader/no-such-name");
        assert!(e.fix.contains("`careful`"), "the fix names the real one: {}", e.fix);
    }

    #[test]
    fn a_library_shape_is_left_for_the_kind_that_owns_it() {
        let mut root = doc(&[("mine", map(&[("based-on", "pact:loop/standard")]))]);
        let mut d = Diagnostics::default();
        resolve(&mut root, &spec(), &mut d);
        assert!(!d.has_errors());
        assert_eq!(
            interceptors(&root, "mine").get("based-on").unwrap().node.as_str(),
            Some("pact:loop/standard"),
            "`loops.rs` resolves the shipped shapes; this pass must not eat the line"
        );
    }
}
