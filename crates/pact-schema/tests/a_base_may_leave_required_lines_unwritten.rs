//! A base is something to build on, not something to run — so the lines only a
//! running agent must have may stay unwritten on it.
//!
//! `instructions:` is required on an agent because it is the only line that
//! makes the agent do anything. A base does nothing by design: `base: yes`
//! says it exists only for others to be `based-on:`, `pact discover` leaves it
//! out and no `team:` may name it. Requiring its instructions would force
//! every pattern to carry words nothing will ever read — so the one
//! `schema/missing-field` arm carries a fourth condition, keyed off the group
//! DECLARING a `base:` field, and the exemption exists only where the
//! specification put it (today: agents).
//!
//! The exemption is for the UNWRITTEN, not the badly written. A base that
//! writes `instructions: ""` has made a different mistake — a line that says
//! nothing at all — and the blank-text refusal still fires: an author who
//! wrote the line meant to put something in it, `base:` or no `base:`.

use pact_diag::Diagnostics;
use pact_doc::parse_yaml;
use pact_schema::Schema;

/// The shipped specification, not a schema written here: `base:` and the
/// required `instructions:` are both typed in `spec/schema.yaml`, and a
/// fabricated `Group` would prove the exemption works on a field nobody has.
fn spec() -> Schema {
    const SPEC: &str = include_str!("../../../spec/schema.yaml");
    let mut d = Diagnostics::new();
    let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
    assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
    s
}

/// One agent block, held against the real `agent` group.
fn agent(yaml: &str) -> Diagnostics {
    let node = parse_yaml(yaml, camino::Utf8Path::new("agent.yaml")).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source("agent.yaml", yaml);
    spec().validate(&node, "agent", &mut d);
    d
}

#[test]
fn a_base_with_no_instructions_is_not_refused() {
    let d = agent("base: yes\ndescription: a pattern\n");
    assert!(
        !d.items().iter().any(|x| x.rule == "schema/missing-field"),
        "a base may leave required lines unwritten:\n{}",
        d.render()
    );
}

#[test]
fn the_same_agent_without_the_base_line_is_refused() {
    // POSITIVE CONTROL: the silence above proves nothing unless the same block
    // without `base: yes` still draws the ordinary refusal, about the one line
    // it is missing (`description:` is present, so `instructions:` is it).
    let d = agent("description: a pattern\n");
    let missing: Vec<_> = d
        .items()
        .iter()
        .filter(|x| x.rule == "schema/missing-field")
        .collect();
    assert!(
        !missing.is_empty(),
        "without `base: yes` the requirement must still stand:\n{}",
        d.render()
    );
    for e in &missing {
        assert!(
            e.message.contains("instructions"),
            "the only line missing is 'instructions': {}",
            e.message
        );
    }
}

#[test]
fn a_base_that_writes_a_blank_line_is_still_refused() {
    // The exemption is for the unwritten, not the badly written.
    let d = agent("base: yes\ndescription: a pattern\ninstructions: \"\"\n");
    assert!(
        d.items().iter().any(|x| x.rule == "schema/nothing-written-here"),
        "a written blank is its own mistake, `base:` or no `base:`:\n{}",
        d.render()
    );
}
