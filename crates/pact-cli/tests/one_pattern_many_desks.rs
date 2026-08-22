//! **P2 — a pattern that takes arguments** (`docs/27` §C2).
//!
//! `based-on:` already lets one document inherit another's fields. What it could
//! not do is inherit them *with a difference supplied by the caller*, so the
//! worked example carried two interceptor files differing in two lines, and the
//! only way to have two desks with two spend caps was two whole desks.
//!
//! `expects:` turns a base into a function: it declares typed parameters, the
//! caller supplies them under `with:`, and the loader fills the holes.
//!
//! Three rules make it decidable, and each has a test here:
//!
//!   * **holes fill values, never keys and never structure.** A template cannot
//!     manufacture a field, so the governance surface of the result is exactly
//!     the governance surface of the template — which is what keeps the
//!     blast-radius classifier sound (§8.2 computes a zone per field, and a
//!     field it has never seen has no zone).
//!   * **every parameter is declared and shape-checked.** An argument nobody
//!     declared is refused; a parameter nobody filled is refused.
//!   * **the template is gone once it has been used.** Its body carries holes,
//!     so it is not a document anybody could run or validate — and a tree that
//!     used a pattern and a tree that wrote both desks out longhand are the
//!     same document, byte for byte.
//!
//! Fixtures: `tests/trees/two-desks-one-pattern/` and
//! `tests/trees/two-desks-longhand/`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree(name: &str) -> String {
    format!("{}/../../tests/trees/{name}", env!("CARGO_MANIFEST_DIR"))
}

fn run(args: &[&str]) -> (Option<i32>, String, String) {
    let out = pact().args(args).output().expect("runs");
    (
        out.status.code(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

fn broken(name: &str, from_tree: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-tmpl-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&tree(from_tree)), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(text.contains(from), "fixture drifted: {from:?} not found in {file}");
        std::fs::write(&p, text.replace(from, to)).unwrap();
    }
    dst.to_string_lossy().into_owned()
}

fn copy_dir(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}

/// Two desks out of one pattern, each carrying what its own caller supplied.
///
/// The two shapes are both exercised: `<domain>` is a hole INSIDE a sentence, so
/// it is text put into text; `<daily-cap>` is the whole of its value, so the
/// argument arrives with its own type intact rather than as the string `"0.05
/// USD"` spelled out again.
///
/// Mutation: stop substituting, and `description` reads "questions about
/// <domain>" — which loads, and is why the hole cannot simply be left in.
#[test]
fn one_pattern_makes_two_desks() {
    let (code, out, err) = run(&["check", &tree("two-desks-one-pattern"), "--deny-warnings"]);
    assert_eq!(code, Some(0), "the tree has to load clean:\n{out}{err}");

    let (code, shown, err) = run(&["show", &tree("two-desks-one-pattern")]);
    assert_eq!(code, Some(0), "{shown}{err}");
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");

    let refunds = &doc["agents"]["refunds"];
    assert_eq!(refunds["description"], "A desk that answers questions about refunds.", "{shown}");
    assert_eq!(refunds["limits"]["cost-per-request-under"], "0.05 USD", "{shown}");
    assert!(
        refunds["instructions"].as_str().unwrap_or_default().contains("about refunds"),
        "a hole inside a sentence is filled too:\n{shown}"
    );

    let returns = &doc["agents"]["returns"];
    assert_eq!(returns["description"], "A desk that answers questions about returns.", "{shown}");
    assert_eq!(returns["limits"]["cost-per-request-under"], "0.10 USD", "{shown}");
}

/// The pattern is not in the tree it made.
///
/// A template's body carries holes, so it is not a document anybody could run,
/// offer, publish or validate. Keeping it would mean either validating a
/// document that cannot be valid, or inventing a second exemption beside
/// `base: yes` — so it goes, the way `based-on:` and `values:` go.
#[test]
fn the_pattern_itself_is_not_one_of_the_desks() {
    let (_, shown, _) = run(&["show", &tree("two-desks-one-pattern")]);
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    let agents = doc["agents"].as_object().expect("agents");
    assert!(agents.contains_key("refunds") && agents.contains_key("returns"), "{shown}");
    assert!(
        !agents.contains_key("desk-pattern"),
        "a pattern is a way of making a desk, not a desk:\n{shown}"
    );

    // And nothing downstream is offered it either.
    let (_, found, _) = run(&["discover", &tree("two-desks-one-pattern")]);
    assert!(!found.contains("desk-pattern"), "not published either:\n{found}");
}

/// The tree that used a pattern and the tree that wrote it out are one document.
#[test]
fn the_pattern_tree_and_the_longhand_tree_are_one_document() {
    let (ca, a, ea) = run(&["show", &tree("two-desks-one-pattern")]);
    let (cb, b, eb) = run(&["show", &tree("two-desks-longhand")]);
    assert_eq!(ca, Some(0), "{a}{ea}");
    assert_eq!(cb, Some(0), "{b}{eb}");
    assert_eq!(a, b, "a pattern is a way of writing a document, not a different document");
}

/// A parameter nobody filled in is refused, naming it and what it is.
#[test]
fn an_unfilled_parameter_is_refused_naming_it() {
    let dst = broken(
        "unfilled",
        "two-desks-one-pattern",
        &[("agents/refunds/agent.yaml", "  daily-cap: 0.05 USD\n", "")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-pattern-needs-what-it-expects"), "{said}");
    assert!(said.contains("daily-cap"), "name the one that is missing:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// The positive control: the same tree, unedited, loads clean.
#[test]
fn the_same_tree_with_every_argument_supplied_loads_clean() {
    let (code, out, err) = run(&["check", &tree("two-desks-one-pattern"), "--deny-warnings"]);
    assert_eq!(code, Some(0), "the refusals above prove nothing unless this passes:\n{out}{err}");
}

/// An argument no parameter declares is refused, with the ones that are declared.
///
/// The commonest real case is a typo, and the fix is the list — which is why the
/// declared names are in the message rather than only in the template.
#[test]
fn an_argument_no_parameter_declares_is_refused() {
    let dst = broken(
        "extra",
        "two-desks-one-pattern",
        &[("agents/refunds/agent.yaml", "daily-cap: 0.05 USD", "dailycap: 0.05 USD")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-pattern-takes-only-what-it-expects"), "{said}");
    assert!(said.contains("dailycap"), "the one they typed:\n{said}");
    assert!(said.contains("daily-cap"), "and the one that is declared:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// An argument that is not the shape its parameter declares is refused.
#[test]
fn an_argument_of_the_wrong_shape_is_refused() {
    let dst = broken(
        "shape",
        "two-desks-one-pattern",
        &[("agents/refunds/agent.yaml", "daily-cap: 0.05 USD", "daily-cap: whenever")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/an-argument-is-not-its-shape"), "{said}");
    assert!(said.contains("daily-cap"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A hole the template never declared is refused at the template.
///
/// Otherwise it survives into every document the pattern makes, as literal text
/// that reads like a mistake nobody can find — the "loads and does nothing"
/// failure, one level up.
#[test]
fn a_hole_no_parameter_declares_is_refused_at_the_pattern() {
    let dst = broken(
        "loose-hole",
        "two-desks-one-pattern",
        &[("agents/desk-pattern/agent.yaml", "questions about <domain>, briefly", "questions about <domain>, briefly, in <tone>")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-hole-nothing-fills"), "{said}");
    assert!(said.contains("tone"), "name the hole:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// `with:` on a document that is based on nothing has nothing to fill.
#[test]
fn arguments_without_a_pattern_are_refused() {
    let dst = broken(
        "orphan-with",
        "two-desks-longhand",
        &[("agents/refunds/agent.yaml", "description:", "with:\n  domain: refunds\ndescription:")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/arguments-with-no-pattern"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A pattern nothing uses is said out loud, and is still not a document.
#[test]
fn a_pattern_nothing_uses_is_said_out_loud() {
    let dst = broken(
        "unused-pattern",
        "two-desks-one-pattern",
        &[
            ("agents/refunds/agent.yaml", "based-on: desk-pattern\nwith:\n  domain: refunds\n  daily-cap: 0.05 USD\n", "description: A plain desk.\ninstructions: Answer briefly.\n"),
            ("agents/returns/agent.yaml", "based-on: desk-pattern\nwith:\n  domain: returns\n  daily-cap: 0.10 USD\n", "description: Another plain desk.\ninstructions: Answer briefly.\n"),
        ],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(0), "an unused pattern is a warning, not a wall:\n{said}");
    assert!(said.contains("loader/nothing-uses-this-pattern"), "{said}");
    assert!(said.contains("desk-pattern"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// An argument may itself be a shared figure — P1 and P2 compose.
///
/// Values are substituted before derivation, so by the time the pattern is
/// filled the argument is already the figure. That ordering is the whole reason
/// the two features do not need to know about each other.
#[test]
fn an_argument_may_be_a_shared_figure() {
    let dst = broken(
        "value-arg",
        "two-desks-one-pattern",
        &[
            ("workspace.yaml", "allow-egress: []", "allow-egress: []\nvalues:\n  house-cap:\n    description: The cap every desk here shares.\n    shape: money\n    value: 0.25 USD\n"),
            ("agents/refunds/agent.yaml", "daily-cap: 0.05 USD", "daily-cap: {use: house-cap}"),
        ],
    );
    let (code, shown, err) = run(&["show", &dst]);
    assert_eq!(code, Some(0), "{shown}{err}");
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    assert_eq!(
        doc["agents"]["refunds"]["limits"]["cost-per-request-under"], "0.25 USD",
        "the figure reached the pattern's hole:\n{shown}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// Rule 1 holds against the CALLER too: an argument is a figure, not a block.
///
/// The rule the whole feature is defended with — *"holes fill VALUES, never
/// keys, never structure"* — was checked against the PATTERN and never against
/// what a caller handed it. `fill`'s exactly-one-hole branch splices the
/// argument's value in whole, so a Map argument landed where a Map was never
/// written: the caller, not the pattern, decided the governance surface of the
/// result, which is exactly the property the rule exists to deny. Found by
/// audit.
///
/// Mutation: accept a non-scalar argument and a caller can manufacture fields
/// the classifier has never seen (LOAD-13).
#[test]
fn an_argument_is_a_figure_and_not_a_block_of_settings() {
    let dst = broken(
        "block-arg",
        "two-desks-one-pattern",
        &[("agents/refunds/agent.yaml", "  daily-cap: 0.05 USD", "  daily-cap:\n    run-arbitrary: yes\n    cost-per-request-under: 0.05 USD")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/an-argument-is-a-figure-not-a-block"), "{said}");
    assert!(said.contains("daily-cap"), "name the parameter:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A hole inside an ARGUMENT is not a hole, and is refused.
///
/// The other direction of the same rule: `fill` walks the merged document, so
/// text a caller supplied is walked too — and an argument whose own text carries
/// `<something>` would be filled by a later parameter. A caller writes figures,
/// not templates.
#[test]
fn a_hole_inside_an_argument_is_refused() {
    let dst = broken(
        "hole-arg",
        "two-desks-one-pattern",
        &[("agents/refunds/agent.yaml", "  domain: refunds", "  domain: refunds for <domain>")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/an-argument-is-not-a-pattern"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A pattern built on a pattern is still a pattern, and still leaves the tree.
///
/// `derive_one` stripped `expects:` from the merged result unconditionally,
/// which is right for the BASE's declarations and wrong for the deriving
/// entry's own. An entry that both derives from a pattern and declares its own
/// parameters therefore stopped being a pattern before the removal pass looked,
/// so it survived into the document carrying literal unfilled `<holes>` — a
/// document nobody wrote and nothing could run. Found by audit.
///
/// Mutation: strip the deriving entry's own `expects:` again and a half-filled
/// pattern ships in `canonical.json`.
#[test]
fn a_pattern_built_on_a_pattern_is_still_a_pattern() {
    let dst = broken(
        "pattern-on-pattern",
        "two-desks-one-pattern",
        &[
            // A middle layer: fixes the cap, still expects the domain.
            ("agents/refunds/agent.yaml",
             "based-on: desk-pattern\nwith:\n  domain: refunds\n  daily-cap: 0.05 USD\n",
             "based-on: desk-pattern\nexpects:\n  domain:\n    shape: text\n    help: what this desk answers about\nwith:\n  domain: <domain>\n  daily-cap: 0.05 USD\n"),
            // And a leaf built on the middle layer.
            ("agents/returns/agent.yaml",
             "based-on: desk-pattern\nwith:\n  domain: returns\n  daily-cap: 0.10 USD\n",
             "based-on: refunds\nwith:\n  domain: returns\n"),
        ],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(0), "a pattern chain is legal:\n{said}");

    let (_, shown, _) = run(&["show", &dst]);
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    let agents = doc["agents"].as_object().expect("agents");
    assert!(!agents.contains_key("desk-pattern"), "the root pattern is gone:\n{shown}");
    assert!(
        !agents.contains_key("refunds"),
        "and so is the middle one — it declares `expects:`, so it is a way of making a desk:\n{shown}"
    );
    assert!(agents.contains_key("returns"), "the leaf is the only desk:\n{shown}");
    assert!(
        !shown.contains('<'),
        "and no unfilled hole survives into the document:\n{shown}"
    );
    assert_eq!(agents["returns"]["description"], "A desk that answers questions about returns.");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A figure whose `shape:` word is not one the format knows is refused.
///
/// `values:` is stripped before the schema sees it, so the `value` group's own
/// `choices:` never fired: a misspelt `shape:` turned OFF the only check that
/// line exists to perform, in silence. That is R41's shape — an unvalidated
/// group is an unclassified group — and it is refused here, at the definition,
/// because that is where the wrong word is.
#[test]
fn a_figure_whose_shape_is_not_a_shape_is_refused() {
    let dst = broken(
        "bad-shape",
        "two-desks-longhand",
        &[("workspace.yaml", "allow-egress: []", "allow-egress: []\nvalues:\n  cap:\n    description: a figure\n    shape: munny\n    value: 0.05 USD\n")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/not-a-shape-a-figure-can-have"), "{said}");
    assert!(said.contains("munny"), "the word they typed:\n{said}");
    assert!(said.contains("money"), "and the ones that work:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A figure with no figure in it is refused at the definition.
///
/// `value.value` is `required: yes` in the specification and the requirement
/// never fired, because the collection is removed before validation. The
/// definition site is where it is missing, so that is where it is said.
#[test]
fn a_figure_with_nothing_in_it_is_refused() {
    let dst = broken(
        "no-value",
        "two-desks-longhand",
        &[("workspace.yaml", "allow-egress: []", "allow-egress: []\nvalues:\n  cap:\n    description: a figure nobody finished writing\n")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-figure-with-nothing-in-it"), "{said}");
    assert!(said.contains("cap"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}
