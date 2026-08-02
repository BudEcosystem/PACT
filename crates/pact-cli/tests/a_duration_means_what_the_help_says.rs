//! Durations, through the door an author actually uses.
//!
//! Everything here edits a line of the worked example and runs the real binary
//! on it. Building a `Ty::Duration` in Rust and asserting about it would prove
//! the type works and say nothing about whether the author's line reaches it —
//! which is the shape of defect this project has shipped five rounds running.
//!
//! Two guarantees, both about the same gap between what a duration is
//! documented to be and what the checker does:
//!
//! * every spelling the help advertises loads in a real workspace, and
//! * a promise of zero time is refused before anything runs.

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
    assert!(text.contains(from), "fixture drifted: {from:?} not in {file}");
    std::fs::write(&p, text.replace(from, to)).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
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
    let root = edited("zero", "agents/refund-desk/limits.yaml", "finishes-within: 30s", "finishes-within: 0s");
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(!out.status.success(), "zero time must be refused:\n{text}");
    assert!(text.contains("schema/below-the-floor"), "the same rule a stage gets:\n{text}");
    assert!(text.contains("'finishes-within' is 0s"), "must name the setting and what was written:\n{text}");
    assert!(text.contains("limits.yaml:10"), "must name the file and the line:\n{text}");
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
    // a question deadline parks a run waiting for a person, and `forget-after`
    // is the only thing that ever discards what was remembered about them.
    let cases: &[(&str, &str, &str, &str)] = &[
        ("answer", "questions/how-much-to-refund.yaml", "answer-within: 4h", "answer-within: 0h"),
        ("forget", "agents/refund-desk/agent.yaml", "forget-after: 30d", "forget-after: 0d"),
    ];
    for (name, file, from, to) in cases {
        let root = edited(name, file, from, to);
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);

        let field = to.split(':').next().unwrap().trim();
        assert!(!out.status.success(), "[{name}] zero time must be refused:\n{text}");
        assert!(text.contains("schema/below-the-floor"), "[{name}] wrong rule:\n{text}");
        assert!(text.contains(field), "[{name}] must name the setting:\n{text}");
        assert!(text.contains("  fix: "), "[{name}] no fix offered:\n{text}");
        assert!(text.contains(".yaml:"), "[{name}] no file:line given:\n{text}");
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
    assert!(!out.status.success(), "a number with no unit must be refused:\n{text}");
    assert!(text.contains("limits.yaml:10"), "must name the file and the line:\n{text}");
    assert!(text.contains("`5 minutes`"), "the fix must show the spellings that work:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}
