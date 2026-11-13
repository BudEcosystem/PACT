//! Every kernel operation is written somewhere, and every field that says it is
//! one names an operation that exists.
//!
//! `spec/kernel.yaml` lists the 76 operations of the seven primitives (docs/97
//! §2 and §5.4). `spec/schema.yaml` says on each field which of them the field
//! IS, with `kernel-op:`. The two are kept in two files because they answer two
//! questions — what the kernel can do, and where an author writes it — and a
//! pair of hand-kept lists drifts unless something holds them to each other.
//! This is that thing, in both directions:
//!
//! - a `kernel-op:` naming an operation `spec/kernel.yaml` does not list is a
//!   field claiming to be something the kernel cannot do;
//! - an operation no field names and no `written-in:` places is one an author
//!   has no way to write, which is the gap docs/97 §9 closed for sixteen
//!   operations and which nothing stopped from reopening.
//!
//! The last test runs the same check on the real files with one line changed
//! each way, so neither half can pass by checking nothing.

use camino::Utf8Path;
use pact_diag::Diagnostics;
use pact_doc::{Node, parse_yaml};
use pact_schema::Schema;
use pact_schema::from_doc::schema_from_yaml;
use std::collections::{BTreeMap, BTreeSet};

/// The seven primitives, and the prefix every operation of each carries.
const PRIMITIVES: [(&str, &str); 7] = [
    ("Shape", "shape"),
    ("Origin", "label"),
    ("Store", "store"),
    ("Actor", "actor"),
    ("Flow", "flow"),
    ("Check", "check"),
    ("Allowance", "allowance"),
];

fn read(name: &str) -> String {
    let path = Utf8Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../spec/{name}"));
    std::fs::read_to_string(&path).unwrap_or_else(|_| panic!("spec/{name} is part of the repository"))
}

fn schema(text: &str) -> Schema {
    let mut diags = Diagnostics::new();
    let schema = schema_from_yaml(text, &mut diags);
    assert!(!diags.has_errors(), "spec/schema.yaml loads clean");
    schema
}

/// One operation of `spec/kernel.yaml`.
struct Op {
    primitive: String,
    meaning: String,
    keyword: String,
    written_in: Option<String>,
}

fn kernel(text: &str) -> BTreeMap<String, Op> {
    let doc = parse_yaml(text, Utf8Path::new("spec/kernel.yaml")).expect("spec/kernel.yaml parses");
    let ops = doc
        .get("ops")
        .and_then(Node::as_map)
        .expect("spec/kernel.yaml states `ops:`");
    let text_at = |node: &Node, key: &str| node.get(key).and_then(Node::as_str).map(str::to_string);
    ops.iter()
        .map(|(name, entry)| {
            let node = &entry.node;
            (
                name.clone(),
                Op {
                    primitive: text_at(node, "primitive").unwrap_or_default(),
                    meaning: text_at(node, "meaning").unwrap_or_default(),
                    keyword: text_at(node, "keyword").unwrap_or_default(),
                    written_in: text_at(node, "written-in"),
                },
            )
        })
        .collect()
}

/// Which fields name each operation, as `<group>.<field>`.
fn named_by(schema: &Schema) -> BTreeMap<String, BTreeSet<String>> {
    let mut by: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for group in schema.groups() {
        for field in &group.fields {
            for op in &field.kernel_ops {
                by.entry(op.clone())
                    .or_default()
                    .insert(format!("{}.{}", group.name, field.name));
            }
        }
    }
    by
}

/// Everything wrong between the two files, one sentence each.
fn problems(schema: &Schema, ops: &BTreeMap<String, Op>) -> Vec<String> {
    let mut found = Vec::new();
    let by = named_by(schema);
    for (op, fields) in &by {
        if !ops.contains_key(op) {
            found.push(format!(
                "{} say they are `{op}`, and spec/kernel.yaml lists no such operation",
                fields.iter().cloned().collect::<Vec<_>>().join(", ")
            ));
        }
    }
    for (name, op) in ops {
        if !by.contains_key(name) && op.written_in.is_none() {
            found.push(format!(
                "`{name}` is named by no field's `kernel-op:` and says nowhere else it is written (`written-in:`)"
            ));
        }
    }
    found
}

#[test]
fn every_operation_says_its_primitive_what_it_does_and_its_keyword() {
    let ops = kernel(&read("kernel.yaml"));
    assert_eq!(
        ops.len(),
        76,
        "docs/97 §5.4 counts 76 operations; a change to that number is a change to the kernel and to the document"
    );
    for (name, op) in &ops {
        let prefix = PRIMITIVES
            .iter()
            .find(|(primitive, _)| *primitive == op.primitive)
            .map(|(_, prefix)| *prefix)
            .unwrap_or_else(|| panic!("`{name}` belongs to '{}', which is not one of the seven", op.primitive));
        assert!(
            name.split_once('.').is_some_and(|(head, tail)| head == prefix && !tail.is_empty()),
            "`{name}` is a {} operation and is named `{prefix}.<what it does>`",
            op.primitive
        );
        assert!(!op.meaning.trim().is_empty(), "`{name}` says what it does");
        assert!(!op.keyword.trim().is_empty(), "`{name}` names the keyword that is it today");
    }
}

#[test]
fn the_schema_and_the_kernel_agree_in_both_directions() {
    let found = problems(&schema(&read("schema.yaml")), &kernel(&read("kernel.yaml")));
    assert!(found.is_empty(), "{}", found.join("\n"));
}

#[test]
fn a_field_shared_through_an_anchor_carries_its_operation_everywhere_it_is_used() {
    // `interface:` and `chosen-by:` are written once, on `knowledge`, and reused
    // on `skill` and `tool` by anchor. The attribute travels with them.
    let by = named_by(&schema(&read("schema.yaml")));
    let requirement = &by["actor.by-requirement"];
    for field in ["knowledge.interface", "skill.interface", "tool.interface", "tool.chosen-by"] {
        assert!(requirement.contains(field), "{field} is `actor.by-requirement`");
    }
    let pairs = by.values().map(BTreeSet::len).sum::<usize>();
    assert!(
        pairs >= 340,
        "the schema pairs a field with an operation {pairs} times; it did more than 340 times, \
         and a list that shrinks is one that stopped being kept"
    );
}

#[test]
fn the_check_fails_on_a_name_nothing_lists_and_on_an_operation_nothing_writes() {
    let schema_text = read("schema.yaml");
    let kernel_text = read("kernel.yaml");

    // A field claiming an operation the kernel does not have.
    let claimed = schema_text.replacen("kernel-op: store.fork", "kernel-op: store.spoon", 1);
    assert_ne!(claimed, schema_text, "`stage.forks` is `store.fork` in the shipped schema");
    let found = problems(&schema(&claimed), &kernel(&kernel_text));
    assert!(
        found.iter().any(|p| p.contains("stage.forks") && p.contains("`store.spoon`")),
        "{found:?}"
    );
    // ...which also leaves `store.fork` with nowhere it is written.
    assert!(found.iter().any(|p| p.starts_with("`store.fork`")), "{found:?}");

    // An operation whose only place was `written-in:`, with that line gone.
    let unplaced = kernel_text.replacen(
        "    written-in: \"a shape line: `one of a, b`, wherever a field takes an answer shape\"\n",
        "",
        1,
    );
    assert_ne!(unplaced, kernel_text, "`shape.one-of` is written in a shape line");
    let found = problems(&schema(&schema_text), &kernel(&unplaced));
    assert_eq!(
        found,
        vec!["`shape.one-of` is named by no field's `kernel-op:` and says nowhere else it is written (`written-in:`)"]
    );
}
