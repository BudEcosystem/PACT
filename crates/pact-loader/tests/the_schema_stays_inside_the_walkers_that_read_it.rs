//! **Four walkers read the specification's own types, and each stops at a depth.**
//!
//! `values.rs`, `programs.rs`, `handover.rs` and `pact-schema`'s own
//! `sentences_of` all descend the schema's groups to find the places a figure
//! may stand, a program may be reached, an agent may be handed over, or a
//! sentence may name something. Each carries a line like
//!
//! ```text
//! // The specification is a few levels deep and acyclic; the cap is a
//! // backstop, not a design.
//! if depth > 12 { return; }
//! ```
//!
//! That is true, and nothing checks it stays true. **The failure mode is
//! silence**: a group nested one level past the cap would make a figure stop
//! being substituted, a program stop being found, or a sentence stop being read
//! — with no diagnostic, because a walker that returns early has nothing to say.
//! Every other check in this repository is written so its absence is loud; these
//! four are written so their absence is invisible.
//!
//! Measured when this was written: the deepest chain in `spec/schema.yaml` is
//! **six** —
//!
//! ```text
//! workspace → workspace.models → catalog.models → model.capabilities
//!           → model-can.context-window → figure.provenance
//! ```
//!
//! — so there are six levels of headroom. This test exists so that the day
//! somebody spends them, they are told, rather than finding out from a figure
//! that quietly did not substitute.

use std::collections::BTreeSet;

/// The smallest cap any of the four walkers carries.
///
/// Written here rather than read out of the source, because the point is to be
/// told when the schema approaches it — and a test that read the cap from the
/// same file it is guarding would follow the cap up and never fire.
const SHALLOWEST_WALKER: usize = 12;

/// How far one group's own fields can descend into other groups.
fn deepest(schema: &pact_doc::Node) -> (usize, Vec<String>) {
    let groups = schema
        .get("groups")
        .and_then(pact_doc::Node::as_map)
        .expect("groups:");
    let group_of = |ty: &str| -> Option<String> {
        for prefix in ["group:", "map of group:", "list of group:"] {
            if let Some(rest) = ty.strip_prefix(prefix) {
                return Some(rest.to_string());
            }
        }
        None
    };
    let mut best = (0usize, Vec::new());
    // An explicit stack rather than recursion: a test that overflows its own
    // stack proving a depth bound would be an unusually poor joke.
    let mut work: Vec<(String, BTreeSet<String>, Vec<String>)> = groups
        .iter()
        .map(|(name, _)| (name.clone(), BTreeSet::new(), vec![name.clone()]))
        .collect();
    while let Some((name, seen, path)) = work.pop() {
        if seen.contains(&name) {
            continue;
        }
        if path.len() > best.0 {
            best = (path.len(), path.clone());
        }
        let Some(entry) = groups.get(name.as_str()) else {
            continue;
        };
        let Some(fields) = entry.node.get("fields").and_then(pact_doc::Node::as_map) else {
            continue;
        };
        for (field, f) in fields {
            let Some(ty) = f.node.get("type").and_then(pact_doc::Node::as_str) else {
                continue;
            };
            let Some(sub) = group_of(ty) else { continue };
            let mut below = seen.clone();
            below.insert(name.clone());
            let mut trail = path.clone();
            trail.push(format!("{name}.{field}"));
            work.push((sub, below, trail));
        }
    }
    best
}

#[test]
fn the_specification_does_not_nest_deeper_than_the_walkers_descend() {
    const SPEC: &str = include_str!("../../../spec/schema.yaml");
    let doc = pact_doc::parse_yaml(SPEC, camino::Utf8Path::new("spec/schema.yaml"))
        .expect("the shipped specification parses");
    let (depth, chain) = deepest(&doc);

    assert!(
        depth < SHALLOWEST_WALKER,
        "the specification now nests {depth} groups deep, and the walkers that read it \
         stop at {SHALLOWEST_WALKER}.\n  the chain: {}\n  \
         fix: raise the cap in `values.rs`, `programs.rs`, `handover.rs` and \
         `pact-schema`'s `sentences_of` — all four, because a figure that stops \
         substituting and a program that stops being found are both SILENT, which is \
         why this test exists at all.",
        chain.join(" → ")
    );

    // And a floor, so the test cannot pass by measuring nothing. A walk that
    // returned 0 or 1 would mean the type spellings changed and this stopped
    // following them — which would leave the cap unguarded while looking green.
    assert!(
        depth >= 4,
        "the walk found only {depth} levels, which means it is no longer following the \
         schema's `group:` / `map of group:` / `list of group:` spellings — the guard is \
         measuring nothing"
    );
}
