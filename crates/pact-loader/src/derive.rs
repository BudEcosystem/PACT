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
    let Some(workspace) = schema.group("workspace") else {
        return Vec::new();
    };
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
pub fn resolve(
    root: &mut Node,
    schema: &Schema,
    diags: &mut Diagnostics,
    recorded: &mut Vec<crate::report::Substitution>,
) {
    let Some(top) = root.as_map_mut() else { return };
    for name in collections(schema) {
        let Some(slot) = top.get_mut(&name) else {
            continue;
        };
        let Some(entries) = slot.node.as_map_mut() else {
            continue;
        };
        resolve_collection(&name, entries, diags, recorded);
    }
}

fn resolve_collection(
    kind: &str,
    entries: &mut Map,
    diags: &mut Diagnostics,
    recorded: &mut Vec<crate::report::Substitution>,
) {
    let names: Vec<String> = entries.keys().cloned().collect();

    // A pattern is held to its own declarations before anything is built from
    // it, so a loose hole is one message about the pattern rather than one per
    // caller about a document that was never written wrong.
    for name in &names {
        if let Some(entry) = entries.get(name)
            && crate::templates::is_a_pattern(&entry.node)
            && let Err(d) = crate::templates::holes_match_declarations(name, &entry.node)
        {
            diags.push(*d);
        }
    }

    // Arguments with nothing to fill. `derive_one` never sees these — it starts
    // at `based-on:` — so without this the schema meets them instead and calls
    // `with` an unknown field, which is true and is not the mistake: the mistake
    // is that the line naming the pattern is missing.
    for name in &names {
        let Some(entry) = entries.get(name) else {
            continue;
        };
        if entry.node.get(crate::templates::WITH).is_some() && entry.node.get("based-on").is_none()
        {
            let at = entry
                .node
                .get(crate::templates::WITH)
                .map_or_else(|| entry.key_span.clone(), |n| n.span.clone());
            diags.push(Diagnostic::error(
                "loader/arguments-with-no-pattern",
                at,
                format!(
                    "'{name}' supplies arguments and is based on nothing, so there is no pattern for them to fill."
                ),
                format!(
                    "Add `based-on: <pattern>` naming something in `{kind}:` that declares `expects:`, or remove the `with:` block."
                ),
            ));
        }
    }

    let mut used: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    for name in &names {
        let mut seen: Vec<String> = Vec::new();
        if let Err(d) = derive_one(kind, entries, name, &mut seen, &mut used, diags, recorded) {
            diags.push(*d);
            // One mistake, one message. An entry whose base did not resolve is
            // not a half-built entry, it is a document nobody can read: it holds
            // only the fields that DIFFER from something that was never found.
            // Left in place it drew three more errors — a required `when:` it
            // was never going to restate, a required `may:` likewise, and
            // `'based-on' is not something an interceptor can have`, which is
            // only true because resolution failed. Removing it here is the same
            // move `not_a_workspace` makes in the CLI, for the same reason. \
            entries.shift_remove(name);
        }
    }

    // A pattern is a way of making a document, not a document. Its body carries
    // holes, so it is not something that could be run, offered, published or
    // validated — and leaving it in would mean either validating a document that
    // cannot be valid, or inventing a second exemption beside `base: yes`. It
    // goes, exactly as `based-on:` and `values:` go, so a tree that used a
    // pattern and a tree that wrote every document out longhand are one
    // document.
    let patterns: Vec<String> = entries
        .iter()
        .filter(|(_, e)| crate::templates::is_a_pattern(&e.node))
        .map(|(k, _)| k.clone())
        .collect();
    for name in patterns {
        if !used.contains(&name)
            && let Some(entry) = entries.get(&name)
        {
            diags.push(Diagnostic::warning(
                "loader/nothing-uses-this-pattern",
                crate::templates::where_it_is(&entry.key_span),
                format!(
                    "'{name}' is a pattern nothing here is based on, so nothing is made from it — the file loads, and no document comes out of it."
                ),
                format!(
                    "Write `based-on: {name}` with a `with:` block on something in `{kind}:`, or delete it."
                ),
            ));
        }
        entries.shift_remove(&name);
    }
}

fn derive_one(
    kind: &str,
    entries: &mut Map,
    name: &str,
    seen: &mut Vec<String>,
    used: &mut std::collections::BTreeSet<String>,
    diags: &mut Diagnostics,
    recorded: &mut Vec<crate::report::Substitution>,
) -> Result<(), Box<Diagnostic>> {
    let Some(entry) = entries.get(name) else {
        return Ok(());
    };
    let Some(map) = entry.node.as_map() else {
        return Ok(());
    };
    let Some(base_entry) = map.get("based-on") else {
        return Ok(());
    };
    let base_node = &base_entry.node;
    let Some(base_name) = base_node.as_str().map(str::to_owned) else {
        return Ok(());
    };
    let base_name = base_name.trim().to_owned();
    if base_name.is_empty() || base_name.starts_with("pact:") {
        // A library shape. `loops.rs` owns those; this pass only joins entries
        // that live in the same tree. \
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
        let list = known
            .iter()
            .map(|k| format!("`{k}`"))
            .collect::<Vec<_>>()
            .join(", ");
        return Err(Box::new(Diagnostic::error(
            "loader/no-such-name",
            span,
            format!("'{name}' is based on '{base_name}', and there is no such entry in `{kind}:`."),
            if list.is_empty() {
                format!(
                    "There is nothing else in `{kind}:` to be based on. Remove the line and write it out in full."
                )
            } else {
                format!("Change it to one of: {list} — or remove the `based-on:` line.")
            },
        )));
    }

    // The base may itself derive. Resolve it first so this entry inherits the
    // finished thing, not a half-derived one.
    seen.push(name.to_owned());
    derive_one(kind, entries, &base_name, seen, used, diags, recorded)?;
    seen.pop();

    // The arguments, held against what the base declares, BEFORE anything is
    // merged: a caller that supplied the wrong ones gets one message naming
    // them, rather than a merged document full of holes and a refusal per hole.
    let (args, base_is_a_pattern) = {
        let Some(base_node) = entries.get(&base_name).map(|e| e.node.clone()) else {
            return Ok(());
        };
        let Some(own_node) = entries.get(name).map(|e| e.node.clone()) else {
            return Ok(());
        };
        let pattern = crate::templates::is_a_pattern(&base_node);
        (
            crate::templates::arguments(kind, name, &base_name, &base_node, &own_node)?,
            pattern,
        )
    };
    if base_is_a_pattern {
        used.insert(base_name.clone());
        // WHERE THIS DOCUMENT CAME FROM, recorded as it happens.
        //
        // A pattern is resolved and REMOVED, exactly as a figure is, so the
        // finished document cannot be asked afterwards — and here the answer
        // matters more than it does for a figure, because changing a pattern
        // changes every document built from it. The report's own type has said
        // `figure` or `pattern` since P2 and only ever carried the first, so a
        // reviewer reading a tree where every desk came out of one shape was
        // told nothing at all about the feature whose selling point is exactly
        // that they share it.
        recorded.push(crate::report::Substitution {
            kind: "pattern",
            name: base_name.clone(),
            at: span.file.to_string(),
        });
    }

    let base_map = match entries.get(&base_name).and_then(|e| e.node.as_map()) {
        Some(m) => m.clone(),
        None => return Ok(()),
    };
    let own = match entries.get(name).and_then(|e| e.node.as_map()) {
        Some(m) => m.clone(),
        None => return Ok(()),
    };

    let mut merged = base_map;
    // A base is something to be based on; being based on one must not make
    // YOU one. Restating `base: yes` yourself (a base built on a base) is
    // laid back over the top below.
    merged.shift_remove("base");
    for (k, v) in own.iter() {
        if k == "based-on" || k == crate::templates::WITH {
            continue;
        }
        // Replacement is the rule — shallow, so narrowing stays expressible —
        // and replacing a whole BLOCK is said out loud, naming what fell out
        // of it: "removal expressible" and "removal silent" are different
        // sentences (C8 §7 D-1). \
        if let (Some(base_had), Some(own_map)) = (merged.get(k), v.node.as_map())
            && let Some(base_inner) = base_had.node.as_map()
        {
            let dropped: Vec<String> = base_inner
                .iter()
                .filter(|(bk, _)| !own_map.contains_key(bk.as_str()))
                .map(|(bk, be)| match be.node.as_str() {
                    Some(s) => format!("`{bk}: {s}`"),
                    None => format!("`{bk}:`"),
                })
                .collect();
            if !dropped.is_empty() {
                diags.push(Diagnostic::warning(
                    "loader/restating-a-block-drops-the-rest",
                    v.key_span.clone(),
                    format!(
                        "`{k}:` here replaces the whole block '{base_name}' set, so {} {} not apply to '{name}'.",
                        dropped.join(" and "),
                        if dropped.len() == 1 { "does" } else { "do" }
                    ),
                    format!(
                        "Restate the lines you meant to keep under `{k}:`, or leave this as it is to take them away on purpose."
                    ),
                ));
            }
        }
        merged.insert(k.clone(), v.clone());
    }
    merged.shift_remove("based-on");
    // The BASE's declarations belong to the base, not to what it made — but the
    // deriving entry's OWN `expects:` is its own, and an entry that both derives
    // from a pattern and declares parameters of its own is still a pattern.
    // Stripping both left such an entry looking like an ordinary document, so
    // the removal pass walked past it and it shipped into `canonical.json`
    // carrying literal unfilled holes: a document nobody wrote and nothing could
    // run.
    merged.shift_remove(crate::templates::EXPECTS);
    merged.shift_remove(crate::templates::WITH);
    if let Some(mine) = own.get(crate::templates::EXPECTS) {
        merged.insert(crate::templates::EXPECTS.to_string(), mine.clone());
    }

    if let Some(slot) = entries.get_mut(name) {
        let keep = slot.node.span.clone();
        let mut built = Node::new(Value::Map(merged), keep);
        if !args.is_empty() {
            crate::templates::fill(&mut built, &args);
        }
        slot.node = built;
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
        assert!(
            !d.has_errors(),
            "the shipped specification does not load:\n{}",
            d.render()
        );
        s
    }
    use super::*;
    use pact_diag::Span;
    use pact_doc::Entry;

    fn span() -> Span {
        Span::whole_file(camino::Utf8Path::new("derive-test.yaml"))
    }

    fn entry(node: Node) -> Entry {
        Entry {
            key_span: span(),
            node,
        }
    }

    fn map(pairs: &[(&str, &str)]) -> Node {
        let mut m = Map::new();
        for (k, v) in pairs {
            m.insert(
                (*k).to_owned(),
                entry(Node::new(Value::Str((*v).to_owned()), span())),
            );
        }
        Node::new(Value::Map(m), span())
    }

    fn doc(entries: &[(&str, Node)]) -> Node {
        let mut inner = Map::new();
        for (k, v) in entries {
            inner.insert((*k).to_owned(), entry(v.clone()));
        }
        let mut top = Map::new();
        top.insert(
            "interceptors".to_owned(),
            entry(Node::new(Value::Map(inner), span())),
        );
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
            (
                "base",
                map(&[("description", "hides cards"), ("may", "hide-values")]),
            ),
            (
                "derived",
                map(&[("based-on", "base"), ("description", "same, on tool calls")]),
            ),
        ]);
        let mut d = Diagnostics::default();
        resolve(&mut root, &spec(), &mut d, &mut Vec::new());
        let got = interceptors(&root, "derived");
        assert_eq!(got.get("may").unwrap().node.as_str(), Some("hide-values"));
        assert_eq!(
            got.get("description").unwrap().node.as_str(),
            Some("same, on tool calls")
        );
        assert!(!d.has_errors());
    }

    #[test]
    fn the_based_on_line_is_gone_once_it_is_resolved() {
        // So a derived document reads like one written out longhand, and its
        // digest is comparable with an expanded tree's. \
        let mut root = doc(&[
            ("base", map(&[("description", "a")])),
            ("derived", map(&[("based-on", "base")])),
        ]);
        resolve(
            &mut root,
            &spec(),
            &mut Diagnostics::default(),
            &mut Vec::new(),
        );
        assert!(interceptors(&root, "derived").get("based-on").is_none());
    }

    #[test]
    fn a_restated_field_replaces_rather_than_merges_so_a_permission_can_be_narrowed() {
        let mut root = doc(&[
            ("base", map(&[("may", "hide-values, stop-the-run")])),
            (
                "derived",
                map(&[("based-on", "base"), ("may", "hide-values")]),
            ),
        ]);
        resolve(
            &mut root,
            &spec(),
            &mut Diagnostics::default(),
            &mut Vec::new(),
        );
        assert_eq!(
            interceptors(&root, "derived")
                .get("may")
                .unwrap()
                .node
                .as_str(),
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
        resolve(
            &mut root,
            &spec(),
            &mut Diagnostics::default(),
            &mut Vec::new(),
        );
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
        resolve(&mut root, &spec(), &mut d, &mut Vec::new());
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
        resolve(&mut root, &spec(), &mut d, &mut Vec::new());
        let e = d.items().first().expect("a typo must be refused");
        assert_eq!(e.rule, "loader/no-such-name");
        assert!(
            e.fix.contains("`careful`"),
            "the fix names the real one: {}",
            e.fix
        );
    }

    #[test]
    fn a_library_shape_is_left_for_the_kind_that_owns_it() {
        let mut root = doc(&[("mine", map(&[("based-on", "pact:loop/standard")]))]);
        let mut d = Diagnostics::default();
        resolve(&mut root, &spec(), &mut d, &mut Vec::new());
        assert!(!d.has_errors());
        assert_eq!(
            interceptors(&root, "mine")
                .get("based-on")
                .unwrap()
                .node
                .as_str(),
            Some("pact:loop/standard"),
            "`loops.rs` resolves the shipped shapes; this pass must not eat the line"
        );
    }

    /// These trees carry nested `limits:` blocks, which the flat str→str
    /// helper above cannot spell — so they parse real YAML, the way the
    /// teams tests do.
    fn resolved(text: &str) -> (Node, Diagnostics) {
        let mut root =
            pact_doc::parse_yaml(text, camino::Utf8Path::new("derive-test.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        resolve(&mut root, &spec(), &mut d, &mut Vec::new());
        (root, d)
    }

    fn agent(root: &Node, name: &str) -> Map {
        root.as_map()
            .unwrap()
            .get("agents")
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
    fn a_restated_block_says_what_it_dropped() {
        let (root, d) = resolved(
            "agents:\n\
             \x20 pattern:\n\
             \x20   limits:\n\
             \x20     cost-per-request-under: 0.05 USD\n\
             \x20     finishes-within: 30s\n\
             \x20     when-it-runs-out: stop-and-say-so\n\
             \x20 desk:\n\
             \x20   based-on: pattern\n\
             \x20   limits:\n\
             \x20     steps-at-most: 4\n\
             \x20     when-it-runs-out: stop-and-say-so\n",
        );
        assert_eq!(
            d.items().len(),
            1,
            "one restated block is one warning:\n{}",
            d.render()
        );
        assert_eq!(
            d.warning_count(),
            1,
            "a warning, not an error:\n{}",
            d.render()
        );
        let w = &d.items()[0];
        assert_eq!(w.rule, "loader/restating-a-block-drops-the-rest");
        assert!(
            w.message.contains("`cost-per-request-under: 0.05 USD`"),
            "the dropped key is named with its value: {}",
            w.message
        );
        assert!(w.message.contains("finishes-within"), "{}", w.message);
        assert!(
            !w.message.contains("when-it-runs-out"),
            "a restated key was not dropped: {}",
            w.message
        );
        // The replacement itself still holds — the warning reports it, it
        // does not undo it. \
        let limits = agent(&root, "desk")
            .get("limits")
            .unwrap()
            .node
            .as_map()
            .unwrap()
            .clone();
        assert!(limits.get("steps-at-most").is_some());
        assert!(limits.get("cost-per-request-under").is_none());
    }

    #[test]
    fn a_restated_block_that_keeps_every_key_is_silent() {
        let (_, d) = resolved(
            "agents:\n\
             \x20 pattern:\n\
             \x20   limits:\n\
             \x20     cost-per-request-under: 0.05 USD\n\
             \x20     finishes-within: 30s\n\
             \x20     when-it-runs-out: stop-and-say-so\n\
             \x20 desk:\n\
             \x20   based-on: pattern\n\
             \x20   limits:\n\
             \x20     cost-per-request-under: 0.01 USD\n\
             \x20     finishes-within: 10s\n\
             \x20     when-it-runs-out: stop-and-say-so\n",
        );
        assert!(
            d.is_empty(),
            "nothing fell out, so nothing to say:\n{}",
            d.render()
        );
    }

    #[test]
    fn deriving_from_a_base_does_not_make_you_one() {
        // The strip asserts on a key the schema has not met yet — legal here,
        // derive runs before validation. \
        let (root, d) = resolved(
            "agents:\n\
             \x20 house:\n\
             \x20   base: yes\n\
             \x20   description: a pattern\n\
             \x20 desk:\n\
             \x20   based-on: house\n\
             \x20   instructions: answer plainly\n",
        );
        assert!(d.is_empty(), "{}", d.render());
        let desk = agent(&root, "desk");
        assert!(
            desk.get("base").is_none(),
            "being based on a base must not make you one"
        );
        assert!(desk.get("based-on").is_none());
        assert_eq!(
            desk.get("description").unwrap().node.as_str(),
            Some("a pattern")
        );
        assert!(
            agent(&root, "house").get("base").is_some(),
            "the base itself still carries the line"
        );
    }
}
