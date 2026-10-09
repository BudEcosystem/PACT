//! A loop with no way out, held against the one command a non-technical author
//! actually runs.
//!
//! The forward walk in `pact-loader/src/reachability.rs` seeds `done` as
//! already-reached — it is the finish line, not a stage — so it could say which
//! stages the run gets *to* and never whether the run gets *out*. Nobody asked
//! the backward question, and a loop that cannot end is the more expensive of
//! the two mistakes: an unreachable stage costs an author some dead text, and a
//! loop with no ending costs a customer their answer and the workspace the whole
//! budget it took to write it.
//!
//! Measured before this existed, on a copy of the worked example: change the
//! last two lines of `loops/careful.yaml`'s `reply` stage from `answered: done`
//! to `answered: reply` and `pact check` printed *"OK — … loaded cleanly (492
//! settings)"* and exited 0. Every line is individually correct — `reply` is a
//! real stage, `answered:` is a real outcome — and the run then writes the
//! refund decision, goes round again instead of handing it over, and hands back
//! whatever `harness._ran_out` does at the ceiling. Measured on that tree with
//! the same question and the same scripted model: **4 model calls became 12** —
//! the whole of `steps-at-most: 12` — and the decision written at step four came
//! back as a person interrupted with "keep going?" under this example's own
//! `when-it-runs-out: ask-a-person`, and as *"Stopped before finishing: this run
//! reached the limit you set with `steps-at-most` (12 of 12 steps)"* under the
//! default `stop-and-say-so`.
//!
//! These drive the real binary against the **real worked example**, edited by
//! one line, for the reason `money_that_moves_with_nobody_asked.rs` gives: what
//! is being proved here is that the author's own `then:` line reaches the rule,
//! with nothing passed and no object built by hand. The unit tests live beside
//! the walk in `pact-loader/src/reachability.rs`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

const LOOP: &str = "loops/careful.yaml";

/// The one line in the worked example that ends the run. Written out so an edit
/// to the example which moves the ending fails these loudly instead of leaving
/// them asserting nothing.
const THE_ENDING: &str = "answered: done";

/// Copy the worked example, apply `edits` as (file, from, to), return the root.
fn edited(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-endless-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not found in {file}"
        );
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

fn checked(root: &str) -> String {
    let out = pact().args(["check", root]).output().expect("runs");
    let mut text = String::from_utf8_lossy(&out.stdout).into_owned();
    if !out.status.success() {
        text.push_str("\n(exit was a refusal)");
    }
    text
}

#[test]
fn a_loop_no_path_of_which_reaches_done_is_refused_before_it_burns_a_budget() {
    // The exact measured edit, through the author's own file and the author's
    // own command.
    let root = edited("measured", &[(LOOP, THE_ENDING, "answered: reply")]);
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        !out.status.success(),
        "a loop that cannot end must not load cleanly:\n{text}"
    );
    assert!(
        text.contains("rule: loader/loop-that-never-finishes"),
        "{text}"
    );
    assert!(
        text.contains("loops/careful.yaml:"),
        "must name the file and line: {text}"
    );
    assert!(
        text.contains("the loop 'careful'"),
        "must name the loop: {text}"
    );
    // The caret lands on a line the author can see is wrong, not on the file.
    assert!(
        text.contains("answered: reply"),
        "must show the line: {text}"
    );
    // What it costs, in the terms a support lead has: not "no terminal state".
    // Both halves measured on this very tree — 4 model calls became 12, and all
    // three `when-it-runs-out:` actions came back carrying the ceiling.
    assert!(text.contains("goes round again"), "{text}");
    assert!(text.contains("paid for over and over"), "{text}");
    assert!(
        text.contains("ran out rather than that it finished"),
        "{text}"
    );
    // And the fix is a line to change, with the stage to change it in.
    assert!(
        text.contains("Change one of these lines to `done`"),
        "{text}"
    );
    assert!(
        text.contains("`answered: done`"),
        "the fix must be typeable: {text}"
    );
    assert!(
        text.contains("under `reply`"),
        "and say where to type it: {text}"
    );
    // The escape hatch, because this rule refuses one shape somebody may have
    // meant: a loop that goes round a bounded number of times and then stops.
    assert!(
        text.contains("`at-most: 3`") && text.contains("`too-many-times:`"),
        "{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_other_stages_that_could_have_carried_the_ending_are_named_beside_it() {
    // "Change one of these lines" is only a fix if the author can see which
    // lines. One problem, one sentence, and a pointer at each of the others —
    // the same collapse the unreachable-stage message makes.
    let root = edited("others", &[(LOOP, THE_ENDING, "answered: reply")]);
    let text = checked(&root);
    assert_eq!(
        text.matches("ever finishes").count(),
        1,
        "the sentence must not be repeated per stage:\n{text}"
    );
    assert!(text.contains("'gather' does not finish either"), "{text}");
    assert!(text.contains("'re-read' does not finish either"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_worked_example_as_shipped_is_never_told_its_loop_cannot_end() {
    // The half that matters most: a correct loop must not be refused. A rule
    // that reports a false positive on the shipped example costs an author their
    // trust in every other diagnostic the tool prints.
    //
    // Scoped to this rule rather than to a clean exit on purpose — the example is
    // shared, and a test about endings has no business failing because somebody
    // is midway through editing a redaction.
    let file = format!("{}/{LOOP}", example());
    let careful = std::fs::read_to_string(&file).expect("the worked example is there");
    assert!(
        careful.contains(THE_ENDING),
        "fixture drifted: {file} no longer ends anywhere"
    );

    let text = checked(&example());
    assert!(
        !text.contains("loop-that-never-finishes"),
        "the shipped loop was refused:\n{text}"
    );
}

#[test]
fn a_loop_that_ends_only_when_a_stage_runs_out_of_turns_is_left_alone() {
    // `too-many-times: done` is a real ending: `harness._stage_to_run` routes a
    // spent stage down that line before entering it. Refusing this would make a
    // bounded loop — the shape somebody reaches for precisely because they are
    // worried about a runaway — unwritable.
    let root = edited(
        "bounded",
        &[(
            LOOP,
            "    then:\n      answered: done",
            "    at-most: 1\n    then:\n      answered: reply\n      too-many-times: done",
        )],
    );
    let text = checked(&root);
    assert!(
        !text.contains("loop-that-never-finishes"),
        "a bounded loop was refused:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn no_message_about_a_loop_that_cannot_end_uses_a_word_a_non_coder_would_look_up() {
    let root = edited("plain", &[(LOOP, THE_ENDING, "answered: reply")]);
    let text = checked(&root).to_lowercase();
    for jargon in [
        "reachab",
        "graph",
        "node",
        "traversal",
        "orphan",
        "cycle",
        "vertex",
        "infinite",
        "terminal",
        "dead code",
        "invariant",
        "predicate",
        "enum",
        "unwrap",
        "panic",
    ] {
        assert!(
            !text.contains(jargon),
            "diagnostic leaked '{jargon}':\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}
