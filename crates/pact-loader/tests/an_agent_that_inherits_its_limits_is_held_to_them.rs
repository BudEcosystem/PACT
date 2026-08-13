//! **An agent that inherits its limits is held to them** — C8 §7 D-3's own
//! name for its acceptance test, witnessed from a real folder of files.
//!
//! Every test `derive.rs` had built its own document: `resolved()` hands the
//! pass a string no author ever typed. That is the Production Gap Register's
//! Class A signature — *"the tests construct its object directly; nothing on
//! the authored path ever builds one"* — and for `based-on:` the authored path
//! is the whole question, because inheritance is a promise about what a tree
//! ON DISK becomes. Everything below reads
//! `tests/trees/an-agent-built-on-another/` through the real `Loader`, against
//! the shipped `spec/schema.yaml`, and resolves it with the real
//! `derive::resolve` — the same three steps `pact check` takes.
//!
//! The tree holds a base with a hole (`desk-pattern` writes no
//! `instructions:`), a descendant that fills it (`refunds`), a budgeted
//! self-team (`second-look`) and a budgeted two-ring (`drafter` ⇄ `checker`),
//! and `pact check <tree> --deny-warnings` exits 0 — the companion CLI test
//! `an_inherited_ceiling_reaches_discovery_and_the_card` measures that from
//! the binary.

use camino::Utf8PathBuf;
use pact_diag::Diagnostics;
use pact_doc::Node;
use pact_loader::Loader;
use pact_schema::Schema;

fn tree() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/an-agent-built-on-another")
}

/// The shipped specification, read from the file rather than restated.
fn spec() -> Schema {
    let path = Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../spec/schema.yaml");
    let text = std::fs::read_to_string(&path).expect("spec/schema.yaml");
    let mut d = Diagnostics::new();
    let s = pact_schema::from_doc::schema_from_yaml(&text, &mut d);
    assert!(
        !d.has_errors(),
        "the shipped specification does not load:\n{}",
        d.render()
    );
    s
}

/// The tree off disk, resolved, and everything the derive pass said doing it.
fn resolved() -> (Node, Diagnostics) {
    let root = tree();
    let mut load = Diagnostics::new();
    let mut doc = Loader::new(root.clone())
        .load(&root, &mut load)
        .expect("the tree loads");
    assert!(
        !load.has_errors(),
        "the shipped tree must load before anything can be asserted about it:\n{}",
        load.render()
    );
    let mut d = Diagnostics::new();
    pact_loader::derive::resolve(&mut doc, &spec(), &mut d);
    d.sort();
    (doc, d)
}

fn agent<'a>(doc: &'a Node, name: &str) -> &'a Node {
    doc.get("agents")
        .and_then(|a| a.get(name))
        .unwrap_or_else(|| panic!("'{name}' is in the tree"))
}

/// The inherited ceiling is on the derived agent, whole and non-null.
///
/// `refunds/agent.yaml` writes two lines — `based-on:` and `instructions:` —
/// and after resolution it carries the pattern's spend cap as if it had been
/// written out longhand. This is the sentence D-3 is about: the cap a runtime
/// holds the agent to is the one its base declared.
///
/// Mutation: make derive_one skip `limits`, or resolve nothing on disk-loaded
/// trees.
#[test]
fn the_inherited_spend_cap_is_on_the_derived_agent() {
    let (doc, _) = resolved();
    let cap = agent(&doc, "refunds")
        .get("limits")
        .and_then(|l| l.get("cost-per-request-under"))
        .and_then(Node::as_str);
    assert_eq!(
        cap,
        Some("0.05 USD"),
        "refunds writes no `limits:` of its own — the cap must arrive from desk-pattern"
    );
}

/// Deriving from a base does not make you one, and the seam is gone.
///
/// A resolved document reads like one written out longhand: no `based-on:`
/// left behind, and no inherited `base: yes` — the strip in derive_one is what
/// keeps a real desk from vanishing out of `pact discover` because its pattern
/// never runs.
///
/// Mutation: drop either `shift_remove` in derive_one.
#[test]
fn the_derived_agent_carries_neither_based_on_nor_base() {
    let (doc, _) = resolved();
    let refunds = agent(&doc, "refunds");
    assert!(
        refunds.get("based-on").is_none(),
        "`based-on:` is removed once resolved"
    );
    assert!(
        refunds.get("base").is_none(),
        "being based on a base must not make refunds one"
    );
}

/// The description is inherited too — the same sentence, not a copy's drift.
///
/// The companion CLI test watches this reach `pact card`; here it is pinned at
/// the document, where the inheritance actually happens.
#[test]
fn the_description_is_the_patterns_sentence() {
    let (doc, _) = resolved();
    assert_eq!(
        agent(&doc, "refunds").get("description").and_then(Node::as_str),
        Some("The shape of a desk — a spend cap and a stop rule — for real desks to be based on."),
        "refunds writes no `description:` — it is the pattern's, inherited"
    );
}

/// Resolution changes the derived entry and leaves the base as written.
///
/// `desk-pattern` still says `base: yes` and still has no `instructions:` —
/// the hole is the base's to keep (`pact show` must not lie about the tree),
/// and the schema's exemption is what lets it check clean.
#[test]
fn the_base_is_left_as_its_author_wrote_it() {
    let (doc, _) = resolved();
    let pattern = agent(&doc, "desk-pattern");
    assert!(
        pattern.get("base").is_some(),
        "the base keeps its `base: yes` line"
    );
    assert!(
        pattern.get("instructions").is_none(),
        "and keeps its hole — filling it is the descendant's job, not the resolver's"
    );
}

/// The whole pass has nothing to say about this tree.
///
/// `refunds` restates no block, so the D-1 warning stays quiet — the tree that
/// deliberately draws it is `tests/trees/a-narrower-desk`, kept apart so this
/// one can check clean under `--deny-warnings`.
#[test]
fn resolving_this_tree_draws_no_diagnostic_at_all() {
    let (_, d) = resolved();
    assert!(
        d.is_empty(),
        "zero errors and zero warnings, or the clean fixture is not clean:\n{}",
        d.render()
    );
}
