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

/// An author's own `use:` key, in a slot the schema types `anything`, is data.
///
/// The defect this pins was found by an audit and reproduced: `looks_like_a_use`
/// fired on ANY map carrying a `use` key, anywhere in the document, and
/// `substitute` walked every node of every top-level key. So a workspace that
/// had a `values/` folder at all hijacked the author's own data wherever it
/// happened to use that word — `case.with:`, `case.expect:`, `metric.with:`,
/// `knowledge.documents:` and `state.starts-as:` are all `anything`-typed, which
/// is the schema saying *these keys are the author's, read them verbatim*. Two
/// failure modes, and the quiet one is worse: a name that matches no figure was
/// hard-refused, and a name that happened to match one was silently REPLACED.
///
/// `metric.with:`'s own help is the sharpest statement of the contract being
/// broken — *"written exactly as its own documentation names them. Nothing is
/// renamed and nothing is filled in for you"*.
///
/// So substitution is schema-aware: a `{use:}` is only a use site where the
/// specification says a scalar belongs, and an `anything` slot is never
/// descended into at all.
///
/// Mutation: drop the `Ty` from `substitute` and walk untyped — this refuses a
/// document whose only mistake was using an ordinary English word as a key.
#[test]
fn an_authors_own_use_key_in_a_verbatim_slot_is_left_alone() {
    let dst = broken(
        "verbatim",
        "one-figure-in-three-places",
        &[(
            "workspace.yaml",
            "allow-egress: []",
            "allow-egress: []\nevals:\n  description: checks\n  population: authored-enumeration\n  cases:\n    one:\n      when: a customer asks about an order\n      with:\n        use: the winter catalogue\n      expect: an answer\n",
        )],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(
        code,
        Some(0),
        "an ordinary English word as an author's own key is not a reference:\n{said}"
    );
    assert!(!said.contains("loader/no-such-value"), "{said}");

    // And it is still there, verbatim, rather than replaced or dropped.
    let (_, shown, _) = run(&["show", &dst]);
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    assert_eq!(
        doc["evals"]["cases"]["one"]["with"]["use"], "the winter catalogue",
        "the author's data reaches the document as written:\n{shown}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// And the quiet direction: a name that DOES match a figure is still not a
/// reference when it sits in a verbatim slot.
///
/// This is the half that would never have been noticed — no diagnostic, no
/// failure, just an author's own string replaced by a figure somewhere else in
/// the tree.
#[test]
fn a_verbatim_slot_is_not_rewritten_even_when_the_name_matches_a_figure() {
    let dst = broken(
        "verbatim-match",
        "one-figure-in-three-places",
        &[(
            "workspace.yaml",
            "allow-egress: []",
            "allow-egress: []\nevals:\n  description: checks\n  population: authored-enumeration\n  cases:\n    one:\n      when: a customer asks about an order\n      with:\n        use: spend-cap\n      expect: an answer\n",
        )],
    );
    let (code, out, err) = run(&["check", &dst]);
    assert_eq!(code, Some(0), "{out}{err}");
    let (_, shown, _) = run(&["show", &dst]);
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    assert_eq!(
        doc["evals"]["cases"]["one"]["with"]["use"], "spend-cap",
        "a figure's NAME is not a figure when the author wrote it as data:\n{shown}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// A figure cannot reach the model catalogue, and is refused where it is written.
///
/// `models:` is the one collection BOTH ports read directly rather than through
/// the loaded document: `adapters/python/src/pact_adapters/resolve.py` opens
/// `<workspace>/models/catalog.yaml` off disk with its own reader (D8, §4.2),
/// because the catalogue is distribution data and the override layer is applied
/// row by row rather than merged into the tree.
///
/// So a figure written there would be substituted by the Rust loader — making
/// `pact check` pass — and NOT by the port that binds the model, which would see
/// the raw map and read no id at all. That is the "free below the loader" claim
/// failing in the one place it can, and the run would fail later, in another
/// language, in a process the author never starts. Refused here instead, naming
/// why.
///
/// Mutation: substitute under `models:` and this passes silently while the
/// second port cannot read the catalogue it was handed.
#[test]
fn a_figure_cannot_reach_the_model_catalogue() {
    let dst = broken(
        "catalogue",
        "one-figure-in-three-places",
        &[(
            "workspace.yaml",
            "allow-egress: []",
            "allow-egress: []\nvalues:\n  house-model:\n    description: the model every desk here shares\n    value: qwen2.5-7b-instruct\nmodels:\n  version: '1'\n  default: {use: house-model}\n",
        )],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-figure-cannot-reach-the-catalogue"), "{said}");
    assert!(said.contains("house-model"), "name the figure:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// Every message this format prints reads as one sentence.
///
/// A `format!` string wrapped across source lines without a `\` continuation
/// carries the source indentation into the sentence, and the author sees twenty
/// spaces in the middle of the line telling them what to type. Four messages
/// shipped that way and an audit found them; O7.3 makes the diagnostic the
/// product surface, so this is a defect in the product rather than in the
/// source.
///
/// Held here rather than at each site, because the next one will be written
/// somewhere else.
#[test]
fn no_message_carries_the_indentation_of_the_file_it_was_written_in() {
    let mut mangled: Vec<String> = Vec::new();
    let src = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../pact-loader/src");
    for entry in std::fs::read_dir(&src).expect("the loader's source").flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("rs") {
            continue;
        }
        let text = std::fs::read_to_string(&path).unwrap();
        for (n, line) in text.lines().enumerate() {
            // A string literal's interior, on one source line, holding a run of
            // spaces between two words. Indentation is at the START of a line
            // and is not this.
            let trimmed = line.trim_start();
            if !trimmed.starts_with('"') && !trimmed.starts_with("format!(") && !line.contains('"')
            {
                continue;
            }
            if let Some(body) = line.split('"').nth(1)
                && body.trim_start().len() == body.len()
                && body.contains("  ")
                && body.trim().contains(' ')
                // A fixture, not a sentence. Test modules hold YAML as string
                // literals and YAML is indented, so a run of spaces there is the
                // document rather than a mangled message. A diagnostic is one
                // sentence of prose and never carries a newline.
                && !body.contains("\\n")
                && !body.contains(": ")
            {
                mangled.push(format!(
                    "{}:{}: {}",
                    path.file_name().unwrap().to_string_lossy(),
                    n + 1,
                    body.trim()
                ));
            }
        }
    }
    assert!(
        mangled.is_empty(),
        "{} message(s) carry the indentation of the file they were written in — an author \
         reading one sees a gap in the middle of the sentence. Add the missing `\\` line \
         continuation:\n  {}",
        mangled.len(),
        mangled.join("\n  ")
    );
}

/// The shapes a figure may declare are the shapes the specification offers.
///
/// `values:` is resolved and removed before the schema could hold anything
/// against it, so the vocabulary is enforced in Rust — which means the two lists
/// can drift, and a word the schema offers would be refused by the loader, or
/// the reverse. Held equal here.
#[test]
fn a_figure_may_declare_exactly_the_shapes_the_specification_offers() {
    let text = std::fs::read_to_string(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../spec/schema.yaml"),
    )
    .unwrap();
    let doc = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml")).unwrap();
    let choices = doc
        .get("groups")
        .and_then(|g| g.get("value"))
        .and_then(|v| v.get("fields"))
        .and_then(|f| f.get("shape"))
        .and_then(|s| s.get("choices"))
        .and_then(pact_doc::Node::as_list)
        .expect("`value.shape` declares its choices");
    let offered: Vec<String> =
        choices.iter().filter_map(|c| c.as_str().map(str::to_owned)).collect();

    // Every word the specification offers is one the loader can read, checked
    // through the real binary: a figure declaring it must load.
    for word in &offered {
        let dst =
            std::env::temp_dir().join(format!("pact-shape-{word}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dst);
        std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
        std::fs::write(
            dst.join("workspace.yaml"),
            format!(
                "name: shapes\nworkspace-id: 01JEQ8Z3M4N5P6Q7R8S9T0V7X7\n\
                 description: one shape.\nowner: platform\nallow-egress: []\n\
                 values:\n  it:\n    description: a figure\n    shape: {word}\n\
                 \x20   value: {}\n",
                example_for(word)
            ),
        )
        .unwrap();
        std::fs::write(
            dst.join("agents/desk/agent.yaml"),
            "description: A desk.\ninstructions: Answer briefly.\nname: {use: it}\n",
        )
        .unwrap();
        let (_, out, err) = run(&["check", dst.to_str().unwrap()]);
        assert!(
            !format!("{out}{err}").contains("not a kind of figure this format knows"),
            "the specification offers `{word}` and the loader does not know it:\n{out}{err}"
        );
        let _ = std::fs::remove_dir_all(&dst);
    }
}

/// A figure of each declared shape, written the way an author would.
fn example_for(shape: &str) -> &'static str {
    match shape {
        "money" => "0.05 USD",
        "duration" => "30s",
        "percent" => "80%",
        "size" => "32k",
        "number" => "1.5",
        "whole-number" => "4",
        "yes-or-no" => "yes",
        _ => "some words",
    }
}

/// `with:` is a pattern's arguments in the kinds that have patterns, and an
/// author's own key everywhere else.
///
/// The word is not reserved. `case.with:` and `metric.with:` are real fields
/// typed `anything` — the format saying *these keys are the author's, read them
/// verbatim* — and a pattern's `with:` is a loader key no group declares. When
/// the substitution pass learned to fill figures inside a pattern's arguments it
/// keyed on the WORD, so it reached into both, and an eval case's own data was
/// rewritten into a figure with nothing said. Measured: `with: {attachment:
/// {use: spend-cap}}` on a case came out as `{"attachment": "0.05 USD"}`.
///
/// That is the untyped-walk defect this pass had just been fixed for, arriving
/// again through the fix. So the interception is gated on the SPECIFICATION: a
/// group that declares a field called `with` has one, and its `with:` is data.
///
/// Mutation: drop the `!group.fields.iter().any(...)` guard and this goes red.
#[test]
fn a_kind_that_declares_with_keeps_its_own() {
    let dst = broken(
        "case-with",
        "one-figure-in-three-places",
        &[(
            "workspace.yaml",
            "allow-egress: []",
            "allow-egress: []\nevals:\n  description: checks\n  population: authored-enumeration\n  cases:\n    one:\n      when: a customer asks\n      with:\n        attachment:\n          use: spend-cap\n      expect: an answer\n",
        )],
    );
    let (code, shown, err) = run(&["show", &dst]);
    assert_eq!(code, Some(0), "{shown}{err}");
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    assert_eq!(
        doc["evals"]["cases"]["one"]["with"]["attachment"]["use"], "spend-cap",
        "an eval case's own data is read verbatim, however deep it goes:\n{shown}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// A figure written where one cannot stand is said out loud.
///
/// The verbatim rule and the never-quietly-ignored rule pull in opposite
/// directions, and both are right. `case.expect:` and `case.with:` are typed
/// `anything`, so a map carrying the word `use` there is the author's own data
/// and is read as written — that is the contract, and it is what stops an
/// ordinary English word becoming a reference.
///
/// But an author who wrote `{use: spend-cap}` and meant the figure gets nothing:
/// no substitution, no message, and the literal map ships into the document and
/// on to whatever reads it. "Loads and does nothing" is the failure this format
/// refuses everywhere else.
///
/// The two are separable, and the separator is whether the name is a figure this
/// workspace actually has. `{use: the winter catalogue}` names nothing and is
/// plainly data. `{use: spend-cap}` names a figure, in a slot that cannot take
/// one — so it is said, as a warning, with what to do about it.
///
/// Found by audit.
#[test]
fn a_figure_written_where_one_cannot_stand_is_said_out_loud() {
    let dst = broken(
        "unsubstitutable",
        "one-figure-in-three-places",
        &[(
            "workspace.yaml",
            "allow-egress: []",
            "allow-egress: []\nevals:\n  description: checks\n  population: authored-enumeration\n  cases:\n    one:\n      when: a customer asks\n      expect:\n        use: spend-cap\n",
        )],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(0), "a warning, not a wall — the data is still valid:\n{said}");
    assert!(said.contains("loader/a-figure-cannot-stand-here"), "{said}");
    assert!(said.contains("spend-cap"), "name it:\n{said}");

    // And it was NOT substituted: the contract for a verbatim slot holds.
    let (_, shown, _) = run(&["show", &dst]);
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    assert_eq!(doc["evals"]["cases"]["one"]["expect"]["use"], "spend-cap", "{shown}");

    let (strict, _, _) = run(&["check", &dst, "--deny-warnings"]);
    assert_eq!(strict, Some(1), "and it has teeth for whoever asks for them");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A word that names no figure is data, and draws nothing.
///
/// The other side of the separator, and the reason it is a separator: an
/// author's ordinary English key must not become a warning because a feature
/// they never used exists.
#[test]
fn a_use_key_naming_no_figure_draws_nothing() {
    let dst = broken(
        "plain-data",
        "one-figure-in-three-places",
        &[(
            "workspace.yaml",
            "allow-egress: []",
            "allow-egress: []\nevals:\n  description: checks\n  population: authored-enumeration\n  cases:\n    one:\n      when: a customer asks\n      expect:\n        use: the winter catalogue\n",
        )],
    );
    let (code, out, err) = run(&["check", &dst, "--deny-warnings"]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(0), "an ordinary word is not a mistake:\n{said}");
    assert!(!said.contains("a-figure-cannot-stand-here"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// What was substituted is recorded, so a resolved tree can say where it came from.
///
/// `values:` and a pattern are both resolved and REMOVED — that is what makes a
/// tree using them the same document as one written longhand, and it is the
/// property everything downstream depends on. The cost is that afterwards
/// nothing says which lines an author actually typed and which arrived from a
/// figure or a pattern, so a reviewer reading `pact show` cannot tell a spend cap
/// somebody wrote from one three desks share.
///
/// P2's own exit gate in `docs/41` asks for that provenance. It cannot be
/// recomputed from the finished document — by then the reference is gone — so it
/// is recorded as it happens and carried on the report `pact waits` already
/// emits. Nothing is printed on `check`: this is for whoever asks, not noise on
/// every run.
#[test]
fn what_was_substituted_is_on_the_report() {
    let (code, waits, err) = run(&["waits", &tree("one-figure-in-three-places")]);
    assert_eq!(code, Some(0), "{waits}{err}");
    let report: serde_json::Value = serde_json::from_str(&waits).expect("waits emits JSON");
    let subs = report["substitutions"].as_array().expect("the report carries them");

    let capped: Vec<&serde_json::Value> = subs
        .iter()
        .filter(|s| s["name"].as_str() == Some("spend-cap"))
        .collect();
    assert_eq!(capped.len(), 2, "both desks used it:\n{waits}");
    for one in capped {
        assert_eq!(one["kind"], "figure", "{waits}");
        assert!(
            one["at"].as_str().is_some_and(|p| p.ends_with("agent.yaml")),
            "and each says where it landed: {one}"
        );
    }
}

/// A tree that substitutes nothing carries an empty list, not a missing key.
#[test]
fn a_tree_that_substitutes_nothing_says_so_plainly() {
    let (code, waits, err) = run(&["waits", &tree("one-figure-longhand")]);
    assert_eq!(code, Some(0), "{waits}{err}");
    let report: serde_json::Value = serde_json::from_str(&waits).expect("JSON");
    assert_eq!(
        report["substitutions"].as_array().map(Vec::len),
        Some(0),
        "an empty list and a missing key are different answers:\n{waits}"
    );
}
