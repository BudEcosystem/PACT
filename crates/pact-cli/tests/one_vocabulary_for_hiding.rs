//! One set of words for one act: `redaction.hide` and `interceptor.rules`.
//!
//! There were two closed vocabularies for hiding a value, and each was missing
//! what the other had. `redaction.hide` knew `anything that looks like <a
//! thing>`; `interceptor.rules` knew `replace anything that looks like <a thing>
//! with "<text>"` and `do the same for anything that looks like <a thing>`. The
//! two files are three lines apart in the worked example and describe the same
//! act — take this out before it leaves — and a sentence copied from one to the
//! other was refused by name, in both directions.
//!
//! That is D13's one-thing-one-name broken where it costs most. An author who
//! learned to write a redaction had learned nothing about writing an
//! interceptor, and what they were writing about both times was a card number in
//! somebody's transcript.
//!
//! They are one list now, shared by the `&the-hiding-sentences` anchor in
//! `spec/schema.yaml`, so the next sentence added is added to both by
//! construction. What the two kinds do NOT share is what they may do: an
//! interceptor says so under `may:` and a redaction hides and nothing else, so
//! the two counting sentences are refused there — with the sentences that DO
//! work printed under the refusal, because a redaction file has no `may:` line
//! and "add one under `may:`" is a fix nobody can type.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the example, apply `edits` as (file, from, to), return the temp root.
fn edited(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-hiding-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
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

fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("the binary runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

#[test]
fn a_sentence_written_in_one_of_the_two_files_is_accepted_in_the_other() {
    // The measurement this whole item exists for, run in both directions on the
    // two shipped files. Before the merge each of these printed a refusal naming
    // the sentence the OTHER file writes as the only thing it knows.
    let root = edited(
        "both-directions",
        &[
            // The interceptor's spelling, written in the redaction file.
            (
                "redaction.yaml",
                "  - anything that looks like a bank account",
                "  - replace anything that looks like a bank account with \"[gone]\"\n\
                 \x20 - do the same for anything that looks like a phone number",
            ),
            // The redaction's spelling, written in the interceptor file.
            (
                "interceptors/redact-card-numbers.yaml",
                "  - do the same for anything that looks like a bank account",
                "  - anything that looks like a bank account",
            ),
        ],
    );
    let (ok, text) = check(&root);
    assert!(ok, "one vocabulary means each file takes the other's words:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_sentence_the_shared_list_has_but_a_redaction_cannot_perform_is_refused_where_it_is_written() {
    // The hazard the merge creates and the reason `always-may:` exists. The one
    // list holds five sentences and a redaction can carry out three; the other
    // two must be refused HERE, at check time, rather than loaded beside real
    // rules and counting nothing — which is the R42/R58 failure arriving through
    // the fix for another one.
    let root = edited(
        "counting-in-a-redaction",
        &[(
            "redaction.yaml",
            "  - anything that looks like a card number",
            "  - anything that looks like a card number\n\
             \x20 - if payments is called more than 1 time in one run, stop and say \"no\"",
        )],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "a redaction that stops the run must be refused:\n{text}");
    assert!(text.contains("redaction.yaml:"), "name the file and the line: {text}");
    assert!(
        text.contains("a redaction may only hide values"),
        "say what this kind can do, in words: {text}"
    );
    // And the fix must be typeable IN THAT FILE — which "add a line under `may:`"
    // is not, because a redaction has no `may:`.
    assert!(!text.contains("Add a line under `may:`"), "untypeable fix offered: {text}");
    assert!(
        text.contains("anything that looks like <a thing>"),
        "offer the sentences this file CAN carry out: {text}"
    );
    assert!(
        !text.contains("stop and say \"<why>\""),
        "a refusal must not offer back the sentence it just refused: {text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn free_prose_in_a_redaction_is_refused_with_the_sentences_that_work() {
    // The vocabulary is closed on both sides, and the closed-ness is what makes
    // "loaded cleanly" mean something. A redaction is offered the three it can
    // perform, not the five the list holds.
    let root = edited(
        "prose",
        &[(
            "redaction.yaml",
            "  - anything that looks like a card number",
            "  - never send anything private to the customer",
        )],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "free prose must be refused:\n{text}");
    assert!(text.contains("redaction.yaml:"), "{text}");
    assert!(
        text.contains("is not a rule PACT knows how to carry out"),
        "say what is wrong: {text}"
    );
    for offered in [
        "anything that looks like <a thing>",
        "replace anything that looks like <a thing> with \"<text>\"",
        "do the same for anything that looks like <a thing>",
    ] {
        assert!(text.contains(offered), "must offer {offered:?}: {text}");
    }
    // And only those three. The two counting sentences are in the same list, and
    // offering them here would be advice that leads to the next refusal.
    assert!(
        !text.contains("stop and say \"<why>\"") && !text.contains("<stage> stage instead"),
        "a redaction must not be offered sentences it cannot carry out: {text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_thing_nothing_can_recognise_is_refused_in_a_redaction_and_in_an_interceptor_alike() {
    // The hole vocabulary is shared with the sentences, so it cannot drift
    // between the two kinds: the same phrase in the two files meets the same
    // refusal, which is what "the author must not be able to tell which half
    // refused them" means.
    for (name, file, from, to) in [
        (
            "unknown-in-redaction",
            "redaction.yaml",
            "  - anything that looks like a card number",
            "  - anything that looks like a passport number",
        ),
        (
            "unknown-in-interceptor",
            "interceptors/redact-card-numbers.yaml",
            "  - replace anything that looks like a card number with \"[card number removed]\"",
            "  - replace anything that looks like a passport number with \"[gone]\"",
        ),
    ] {
        let root = edited(name, &[(file, from, to)]);
        let (ok, text) = check(&root);
        assert!(!ok, "[{name}] must be refused:\n{text}");
        assert!(
            text.contains("Nothing here knows what 'passport number' looks like"),
            "[{name}] {text}"
        );
        assert!(
            text.contains("card number, bank account, email address, phone number"),
            "[{name}] the fix must list what can be recognised: {text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_two_fields_are_held_against_one_list_and_not_two_copies_of_it() {
    // The anchor, asserted on the specification itself. Two `one-of:` blocks that
    // happen to agree today are two places to add the next sentence and two
    // places for them to disagree — which is what this file measured them doing.
    let text = std::fs::read_to_string(format!(
        "{}/../../spec/schema.yaml",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    assert!(
        text.contains("forms: &the-hiding-sentences"),
        "the shared list must be anchored on `interceptor.rules`"
    );
    assert!(
        text.contains("forms: *the-hiding-sentences"),
        "`redaction.hide` must take the list by reference"
    );
    assert_eq!(
        text.matches("say: anything that looks like <a thing>").count(),
        1,
        "the bare hiding sentence must be written once, not once per kind"
    );
    assert_eq!(
        text.matches(
            "a thing: [card number, bank account, email address, phone number, social security number]",
        )
            .count(),
        1,
        "the things that can be recognised must be written once, not once per kind"
    );
}

#[test]
fn the_shipped_redaction_and_the_shipped_interceptor_still_load_together() {
    // Both files unedited. The merge must not have made either of them illegal —
    // `redaction.yaml` writes the bare sentence three times and
    // `interceptors/redact-card-numbers.yaml` writes `replace …` and `do the same
    // …`, and after the merge all five of those lines are drawn from one list.
    let (ok, text) = check(&example());
    assert!(ok, "the worked example must stay valid:\n{text}");
}

/// A two-file workspace with one interceptor in it, written from scratch.
///
/// Not a copy of the worked example, deliberately: the file below is about a
/// tree an author is part-way through writing, and the smallest workspace that
/// can hold an interceptor is the honest shape of that.
fn a_workspace_with_one_rule(name: &str, rules: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-carries-on-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("interceptors")).unwrap();
    std::fs::create_dir_all(dst.join("agents/a")).unwrap();
    std::fs::write(
        dst.join("workspace.yaml"),
        "name: Tiny\ndescription: One agent and one rule.\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("agents/a/agent.yaml"),
        "description: Answers questions.\ninstructions: Answer the question.\ninterceptors: [x]\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("interceptors/x.yaml"),
        format!(
            "description: Hides card numbers.\nwhen: step.message.before\nmay:\n  - hide-values\nrules:\n{rules}"
        ),
    )
    .unwrap();
    dst.to_string_lossy().into_owned()
}

#[test]
fn a_sentence_that_carries_on_from_another_one_is_refused_when_nothing_is_above_it() {
    // THE AUTHORED PATH, through the one tool D13's reader runs. `do the same
    // for …` is one of the three hiding sentences the merged list gives both
    // fields, and it is the only one that is not a rule on its own — written
    // first it hides nothing.
    //
    // Measured on this exact tree before `continues: yes` was written in
    // `spec/schema.yaml`: `OK — …/mini loaded cleanly (17 settings).`, and then
    // the run refused the same line. A file the author's own tool passes and the
    // run rejects is the split this vocabulary exists to close, so the merge
    // that made the sentence writeable in a second file had to close it in both.
    let root = a_workspace_with_one_rule(
        "alone",
        "  - do the same for anything that looks like a card number\n",
    );
    let (ok, text) = check(&root);
    assert!(!ok, "a rule that hides nothing must not print 'loaded cleanly':\n{text}");
    assert!(text.contains("interceptors/x.yaml:6"), "name the file and the line: {text}");
    assert!(
        text.contains("no rule before it says what to do"),
        "say what is wrong in the author's words: {text}"
    );
    assert!(
        text.contains("anything that looks like <a thing>"),
        "and offer a sentence that stands on its own: {text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_same_two_sentences_in_the_order_the_worked_example_writes_them_load_cleanly() {
    // The half that keeps the check above from being a regression. `replace … `
    // followed by `do the same …` is what
    // `interceptors/redact-card-numbers.yaml` ships, and it must stay a file
    // that loads.
    let root = a_workspace_with_one_rule(
        "in-order",
        "  - replace anything that looks like a card number with \"[card number removed]\"\n\
         \x20 - do the same for anything that looks like a bank account\n",
    );
    let (ok, text) = check(&root);
    assert!(ok, "the shipped pair must load:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}
