//! **P1 — a figure written once, used wherever it belongs** (`docs/27` §C1).
//!
//! The defect this closes is convergence. In the worked example the 200 USD
//! approval threshold exists three times — in the gate (`more-than: 200 USD`),
//! in the runaway-refund sentence, and in an eval case — and nothing in the
//! format holds the three together. Raising it is three edits, and the tree
//! that has had two of them is a tree whose gate and whose test disagree about
//! what the business rule is. `pact check` reports nothing, because each line
//! is individually correct.
//!
//! `values:` is the one-write form. `{use: <name>}` stands where the figure
//! would, and the loader puts the figure there before anything else looks.
//!
//! **The substitution is total, and then it is gone.** `values:` is stripped
//! from the document once resolved — exactly what `based-on:` does and for
//! exactly the same reason (`derive.rs:28-30`): a tree that used a value and a
//! tree that wrote the figure out longhand must be *the same document*, so the
//! digest is comparable, `pact show` prints one shape, and no adapter, no
//! second port and no runtime ever learns that values exist. That is what makes
//! this feature free at every layer below the loader.
//!
//! Fixtures: `tests/trees/one-figure-in-three-places/` (uses three values
//! across two agents) and `tests/trees/one-figure-longhand/` (the same document
//! typed out). They are compared byte for byte.

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

/// A workspace built from `edits` applied to a fixture tree.
fn broken(name: &str, from_tree: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-values-{name}-{}", std::process::id()));
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

/// The tree loads, and the figure is at every line that asked for it.
///
/// Three shapes on purpose — money, a duration and a whole number — because a
/// substitution that only ever carried text would pass a one-shape test and
/// fail the first author who wrote a deadline.
///
/// Mutation: stop substituting, and `{use: spend-cap}` reaches the schema as a
/// set of settings where an amount of money belongs.
#[test]
fn a_value_reaches_every_line_that_uses_it() {
    let (code, out, err) = run(&["check", &tree("one-figure-in-three-places")]);
    assert_eq!(code, Some(0), "the tree has to load:\n{out}{err}");

    let (code, shown, err) = run(&["show", &tree("one-figure-in-three-places")]);
    assert_eq!(code, Some(0), "{shown}{err}");
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("show emits JSON");

    let desk = &doc["agents"]["desk"]["limits"];
    assert_eq!(desk["cost-per-request-under"], "0.05 USD", "{shown}");
    assert_eq!(desk["finishes-within"], "30s", "{shown}");
    assert_eq!(desk["steps-at-most"], 4, "a whole number stays a whole number:\n{shown}");

    // The second reader of the same figure. This is the whole point: one line
    // written, two agents bound.
    assert_eq!(
        doc["agents"]["second-desk"]["limits"]["cost-per-request-under"], "0.05 USD",
        "{shown}"
    );
}

/// A value used by a line is a value nothing has to remember to update twice.
///
/// The convergence claim, measured: change the one file and every reader moves.
#[test]
fn changing_the_one_line_changes_every_reader() {
    let dst = broken(
        "raise",
        "one-figure-in-three-places",
        &[("values/spend-cap.yaml", "value: 0.05 USD", "value: 0.50 USD")],
    );
    let (code, shown, err) = run(&["show", &dst]);
    assert_eq!(code, Some(0), "{shown}{err}");
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    assert_eq!(doc["agents"]["desk"]["limits"]["cost-per-request-under"], "0.50 USD");
    assert_eq!(doc["agents"]["second-desk"]["limits"]["cost-per-request-under"], "0.50 USD");
    let _ = std::fs::remove_dir_all(&dst);
}

/// The expanded tree and the longhand tree are ONE document.
///
/// `values:` is removed once resolved, so nothing downstream — no adapter, no
/// second port, no runtime — ever learns the feature exists. This is the test
/// that says so, and it is the reason P1 needs no change outside the loader.
///
/// Mutation: keep `values:` in the resolved document and the two diverge.
#[test]
fn the_expanded_tree_and_the_longhand_tree_are_one_document() {
    let (ca, a, ea) = run(&["show", &tree("one-figure-in-three-places")]);
    let (cb, b, eb) = run(&["show", &tree("one-figure-longhand")]);
    assert_eq!(ca, Some(0), "{a}{ea}");
    assert_eq!(cb, Some(0), "{b}{eb}");
    assert_eq!(
        a, b,
        "a tree that uses a value and a tree that writes the figure out are the same \
         document, or the digest of one means nothing about the other"
    );
}

/// A name that is not there is refused where it was written, with the ones that are.
///
/// Positive control below: the same tree unedited loads clean, so this is
/// measuring the misspelling and not the fixture.
#[test]
fn a_use_of_a_name_that_is_not_there_is_refused() {
    let dst = broken(
        "typo",
        "one-figure-in-three-places",
        &[("agents/desk/agent.yaml", "{use: spend-cap}", "{use: spend-capp}")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "a name that is not there is a refusal:\n{said}");
    assert!(said.contains("loader/no-such-value"), "{said}");
    assert!(said.contains("spend-capp"), "the name they typed:\n{said}");
    assert!(said.contains("spend-cap"), "and the one that is there:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// The positive control for the test above.
#[test]
fn the_same_tree_without_the_typo_loads_clean() {
    let (code, out, err) = run(&["check", &tree("one-figure-in-three-places"), "--deny-warnings"]);
    assert_eq!(code, Some(0), "the silence above proves nothing unless this passes:\n{out}{err}");
}

/// A figure that is not what the value says it is, refused where it is written.
///
/// `shape:` is optional; when it IS written it is a claim about the figure, and
/// a claim nothing checks is decoration. Refused at the definition, because
/// that is the line that is wrong — every use site is innocent.
#[test]
fn a_value_that_is_not_the_shape_it_declares_is_refused_at_the_definition() {
    let dst = broken(
        "shape",
        "one-figure-in-three-places",
        &[("values/spend-cap.yaml", "value: 0.05 USD", "value: sometime next week")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/value-is-not-its-shape"), "{said}");
    assert!(said.contains("spend-cap"), "name the value:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A substituted figure is still held to the line it lands in.
///
/// Substitution is not an escape from validation: putting an amount of money
/// where a whole number belongs is the ordinary `schema/wrong-type`, reported at
/// the line the author wrote `{use:}` on — which is where they can fix it.
#[test]
fn a_substituted_value_is_still_held_to_the_field_it_lands_in() {
    let dst = broken(
        "mismatch",
        "one-figure-in-three-places",
        &[("agents/desk/agent.yaml", "steps-at-most: {use: patience}", "steps-at-most: {use: spend-cap}")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "a money figure is not a step count:\n{said}");
    assert!(said.contains("schema/wrong-type"), "the ordinary refusal, at the use site:\n{said}");
    assert!(said.contains("agent.yaml"), "reported where the author wrote it:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A value nothing uses is said out loud.
///
/// The same reading `loader/nothing-points-at-it` gives every other kind: a
/// definition nothing reaches is a line the author believes is doing something.
/// It cannot be the generic check — by the time that runs, every `{use:}` has
/// been replaced and the reference is gone — so the pass that does the
/// substituting is the only thing that can count.
#[test]
fn a_value_nothing_uses_is_said_out_loud() {
    let dst = broken(
        "unused",
        "one-figure-in-three-places",
        &[("agents/desk/agent.yaml", "  finishes-within: {use: deadline}\n", "")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(0), "an unused value is a warning, not a wall:\n{said}");
    assert!(said.contains("loader/nothing-uses-this-value"), "{said}");
    assert!(said.contains("deadline"), "name it:\n{said}");

    let (strict, _, _) = run(&["check", &dst, "--deny-warnings"]);
    assert_eq!(strict, Some(1), "and it has teeth for whoever asks for them");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A use site takes the one key and nothing else.
///
/// `{use: x, description: y}` is either a typo or a misunderstanding, and both
/// are better met here than by silently loading a two-key map where a figure
/// belongs.
#[test]
fn a_use_site_carries_nothing_but_the_name() {
    let dst = broken(
        "extra",
        "one-figure-in-three-places",
        &[("agents/desk/agent.yaml", "{use: spend-cap}", "{use: spend-cap, because: tight}")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-use-carries-only-a-name"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A value built from another value works, and a circle of them is refused.
///
/// The ring diagnostic is `derive.rs`'s, in shape and in wording: a circle has
/// no bottom, and the message writes the circle out so the reader can see which
/// line to cut.
#[test]
fn a_circle_of_values_is_refused_with_the_circle_written_out() {
    let dst = broken(
        "circle",
        "one-figure-in-three-places",
        &[
            ("values/spend-cap.yaml", "value: 0.05 USD", "value: {use: deadline}"),
            ("values/deadline.yaml", "value: 30s", "value: {use: spend-cap}"),
        ],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-value-built-from-itself"), "{said}");
    assert!(said.contains("→"), "the circle is written out:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}
