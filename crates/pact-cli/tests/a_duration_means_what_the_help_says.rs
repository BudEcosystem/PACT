//! Durations, through the door an author actually uses.
//!
//! Everything here edits a line of the worked example and runs the real binary
//! on it. Building a `Ty::Duration` in Rust and asserting about it would prove
//! the type works and say nothing about whether the author's line reaches it —
//! which is the shape of defect this project has shipped five rounds running.
//!
//! Four guarantees, all about the same gap between what a duration is
//! documented to be and what the checker does:
//!
//! * every spelling the help advertises loads in a real workspace,
//! * a promise of zero time is refused before anything runs,
//! * a length of time too long to count is refused the same way — it used to
//!   take the whole command down with it — and
//! * a long one that DOES fit arrives at a scheduler as the number that was
//!   written, so "it stopped crashing" and "it kept the right ceiling" are not
//!   the same claim.
//!
//! The last two are one defect from both sides. `finishes-within:
//! "99999999999999999999h 99999999999999999999h 99999999999999999999h"` was
//! added up with `*total += (v * mult) as u64`, and a float-to-integer cast in
//! Rust SATURATES rather than wrapping, so the first part pinned the total at
//! the largest number there is and the second went over the top of it:
//!
//! ```text
//! $ pact check .
//! thread 'main' panicked at crates/pact-schema/src/coerce.rs:174:
//! attempt to add with overflow
//! ```
//!
//! That is the debug build — the one `cargo run` and the README both give an
//! author. A release build did not die: it wrapped, said `OK — loaded cleanly`,
//! and kept a ceiling with no relation to the line anybody wrote. So the
//! refusal is asserted here, and the number is asserted here, because only the
//! pair of them rules out both halves.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply one edit, return the temp root.
fn edited(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-duration-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replace(from, to)).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

fn check(root: &str) -> String {
    let out = pact().args(["check", root]).output().expect("runs");
    String::from_utf8_lossy(&out.stdout).into_owned()
}

#[test]
fn a_promise_of_zero_time_is_refused_at_check_time() {
    // `finishes-within` is the promise made to whoever waits and, with no
    // `runs-for-at-most` beside it, the wall-clock stop as well. At `0s` it is
    // reached before the first step — every run halts instantly and reports a
    // ceiling the author believed they were being generous with. It loaded
    // clean for five rounds.
    let root = edited(
        "zero",
        "agents/refund-desk/limits.yaml",
        "finishes-within: 30s",
        "finishes-within: 0s",
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(!out.status.success(), "zero time must be refused:\n{text}");
    assert!(
        text.contains("schema/below-the-floor"),
        "the same rule a stage gets:\n{text}"
    );
    assert!(
        text.contains("'finishes-within' is 0s"),
        "must name the setting and what was written:\n{text}"
    );
    assert!(
        text.contains("limits.yaml:10"),
        "must name the file and the line:\n{text}"
    );
    assert!(
        text.contains("fix: Write `finishes-within: 30s`"),
        "the fix must be a line they can type:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn every_deadline_in_the_worked_example_has_the_same_floor() {
    // The floor belongs to the type, so it arrives on every duration field at
    // once rather than on the one somebody remembered. These are the other two
    // the worked example carries, and each is load-bearing in a different way:
    // a question deadline parks a run waiting for a person, and `kept-for`
    // is the only thing that ever discards what was remembered about them.
    // It is a moment, and a moment written as a length of time is a duration.
    let cases: &[(&str, &str, &str, &str)] = &[
        (
            "answer",
            "questions/how-much-to-refund.yaml",
            "answer-within: 4h",
            "answer-within: 0h",
        ),
        (
            "forget",
            "agents/refund-desk/agent.yaml",
            "kept-for: 30d",
            "kept-for: 0d",
        ),
    ];
    for (name, file, from, to) in cases {
        let root = edited(name, file, from, to);
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);

        let field = to.split(':').next().unwrap().trim();
        assert!(
            !out.status.success(),
            "[{name}] zero time must be refused:\n{text}"
        );
        assert!(
            text.contains("schema/below-the-floor"),
            "[{name}] wrong rule:\n{text}"
        );
        assert!(
            text.contains(field),
            "[{name}] must name the setting:\n{text}"
        );
        assert!(text.contains("  fix: "), "[{name}] no fix offered:\n{text}");
        assert!(
            text.contains(".yaml:"),
            "[{name}] no file:line given:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_friendly_spellings_the_help_advertises_load_in_a_real_workspace() {
    // Each of these already worked and was named nowhere an author could see
    // it. The assertion is per-field rather than "the whole tree is clean",
    // because an unrelated problem elsewhere in the example would then read as
    // this line being wrong.
    for (name, spelling) in [
        ("long-unit", "5 minutes"),
        ("spaced", "1m 30s"),
        ("shouted", "30S"),
        ("days", "1d"),
        ("huge", "999999h"),
    ] {
        let root = edited(
            name,
            "agents/refund-desk/limits.yaml",
            "finishes-within: 30s",
            &format!("finishes-within: {spelling}"),
        );
        let text = check(&root);
        assert!(
            !text.contains("finishes-within"),
            "`{spelling}` is offered in the help and the checker complains about it:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_deadline_with_no_unit_is_refused_where_the_author_is() {
    // The boundary of the sentence above, held so nobody widens it later by
    // being helpful. `finishes-within: 90` is as likely to mean ninety minutes
    // as ninety seconds, and a ceiling out by sixty times would be applied
    // silently — so the unit is required and the fix teaches it, the same way
    // a bare `90` is refused for a percentage.
    let root = edited(
        "no-unit",
        "agents/refund-desk/limits.yaml",
        "finishes-within: 30s",
        "finishes-within: 90",
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        !out.status.success(),
        "a number with no unit must be refused:\n{text}"
    );
    assert!(
        text.contains("limits.yaml:10"),
        "must name the file and the line:\n{text}"
    );
    assert!(
        text.contains("`5 minutes`"),
        "the fix must show the spellings that work:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_length_of_time_too_long_to_count_is_refused_at_check_time() {
    // The far end of the same line, and the one that did not merely load wrong
    // — it took the command down. `finishes-within` is the promise made to
    // whoever waits and, with no `runs-for-at-most` beside it, the wall-clock
    // stop as well, so a ceiling that wrapped is a run that stops at a moment
    // nobody chose.
    //
    // Mutation: put `*total += (v * mult) as u64;` back in `coerce::duration`.
    // Measured with it back: this test fails on a debug build with
    // `attempt to add with overflow` and no diagnostic at all, and on a release
    // build with `OK — loaded cleanly (498 settings)` and exit 0.
    let root = edited(
        "too-long",
        "agents/refund-desk/limits.yaml",
        "finishes-within: 30s",
        "finishes-within: \"99999999999999999999h 99999999999999999999h 99999999999999999999h\"",
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        !out.status.success(),
        "a length of time nobody can count must be refused:\n{text}"
    );
    assert!(
        text.contains("schema/too-long-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        text.contains("'finishes-within' is 99999999999999999999h"),
        "must name the setting and quote what was written:\n{text}"
    );
    assert!(
        text.contains("limits.yaml:10"),
        "must name the file and the line:\n{text}"
    );
    assert!(
        text.contains("fix: Write `finishes-within: 30s`"),
        "the fix must be a line they can type:\n{text}"
    );
    // It IS a length of time, just an uncountable one. "not a length of time"
    // would send its author hunting for a typo that is not there.
    assert!(
        !text.contains("schema/wrong-type"),
        "the line is spelled correctly:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_deadline_too_long_to_count_is_reported_once_and_not_also_called_missing() {
    // One mistake, one message — the rule this repository already holds for a
    // question named by three lines. `answer-within` is read twice: the schema
    // judges the length of time, and `loader/wait-with-no-deadline` asks whether
    // there is one at all. The second used to ask by trying to PARSE it, so a
    // deadline the schema had just refused by name was, in the next paragraph,
    // reported as never written — a sentence that is plainly false beside an
    // error quoting the line.
    //
    // Mutation: put `milliseconds(written).is_some()` back in
    // `report::check_deadline`. Without it the warning returns and this fails.
    let root = edited(
        "too-long-deadline",
        "questions/keep-going.yaml",
        "answer-within: 10m",
        "answer-within: \"99999999999999999999h 99999999999999999999h\"",
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        !out.status.success(),
        "the deadline must still be refused:\n{text}"
    );
    assert!(
        text.contains("schema/too-long-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        !text.contains("loader/wait-with-no-deadline"),
        "the deadline is written, and quoted in the error above it:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_deadline_never_written_at_all_is_still_reported() {
    // The boundary of the sentence above: the warning is about silence, and
    // silence is still silence. Deleting the line — not writing a bad one — is
    // what `loader/wait-with-no-deadline` is for, and narrowing the gate must
    // not have narrowed it to nothing.
    let root = edited(
        "no-deadline-at-all",
        "questions/keep-going.yaml",
        "answer-within: 10m\n",
        "",
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        text.contains("loader/wait-with-no-deadline"),
        "a wait that never ends:\n{text}"
    );
    assert!(
        text.contains("`answer-within: 30m`"),
        "the fix has to be typeable:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_longest_deadline_that_fits_reaches_a_scheduler_as_the_number_written() {
    // "It stopped crashing" is not the claim. A release build never crashed —
    // it wrapped `99999999999999999999h` round to a ceiling nobody wrote and
    // said nothing. So the number is asserted, at the far end of the tool that
    // hands deadlines to whatever times them: `100000h 30m` is eleven years and
    // half an hour, comfortably inside what fits, and it must arrive as
    // 360_000_000_000 + 1_800_000 milliseconds and not as anything else.
    //
    // Mutation: put `*total += (v * mult) as u64;` back. This line still adds
    // up correctly under it — which is the point of pairing it with the refusal
    // above rather than trusting either alone.
    let root = edited(
        "big-but-sane",
        "questions/how-much-to-refund.yaml",
        "answer-within: 4h",
        "answer-within: \"100000h 30m\"",
    );
    let checked = check(&root);
    assert!(
        checked.contains("loaded cleanly"),
        "a deadline that fits must load:\n{checked}"
    );

    let out = pact().args(["waits", &root]).output().expect("runs");
    let json = String::from_utf8_lossy(&out.stdout);
    assert!(out.status.success(), "waits must be projectable:\n{json}");
    assert!(
        json.contains("\"deadline-ms\": 360001800000"),
        "the scheduler must be handed the length of time that was written:\n{json}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_fraction_of_a_second_reaches_a_scheduler_as_the_fraction_written() {
    // The same claim as the test above — the number that was written is the
    // number that arrives — at the other end of the scale, where it was NOT
    // true. A fraction of a second is not held exactly by the kind of number
    // the multiplication uses: `1.001 * 1000.0` comes to `1000.9999999999999`,
    // and the conversion to whole milliseconds threw the tail away, so a wait
    // written as `1.001s` was handed to whatever times it as 1000ms.
    //
    // One millisecond, and it is here for the reason the eleven-year deadline
    // above is: nothing anywhere said the figure had moved. The complaint is
    // the same one the file's own header makes about reading `1m30s` as one
    // second, only smaller.
    //
    // Mutation: put `ms as u64` back in place of `ms.round() as u64` in
    // `coerce::duration`. Measured with it back, through this exact command:
    // `"deadline-ms": 1000`, and this test fails. `100000h 30m` above still
    // arrives correctly under the same mutation, which is why that test cannot
    // hold this one.
    let root = edited(
        "fractional",
        "questions/how-much-to-refund.yaml",
        "answer-within: 4h",
        "answer-within: \"1.001s\"",
    );
    let checked = check(&root);
    assert!(
        checked.contains("loaded cleanly"),
        "a fraction of a second must load:\n{checked}"
    );

    let out = pact().args(["waits", &root]).output().expect("runs");
    let json = String::from_utf8_lossy(&out.stdout);
    assert!(out.status.success(), "waits must be projectable:\n{json}");
    assert!(
        json.contains("\"deadline-ms\": 1001"),
        "1.001s is 1001 milliseconds, not 1000:\n{json}"
    );
    let _ = std::fs::remove_dir_all(&root);
}
