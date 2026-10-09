//! The `teamwork.shares` arithmetic, held against the tool D13's author runs.
//!
//! Both rules were real and both were out of reach.
//! `adapters/python/src/pact_adapters/delegation.py` refuses a teammate with no
//! share (`Teamwork.check`, the `missing` list) and a list adding up to more than
//! the pot — but from `Teamwork.from_document`, which runs when a RUN starts: in
//! another language, in a process a support lead never starts.
//!
//! Verified before this existed, on this exact edit: `shares:` reading
//! `policy-checker: 60%` and `fraud-checker: 90%` — 150% of one pot — printed
//! `OK — … loaded cleanly (468 settings).` and exited 0, with nothing else on
//! the screen.
//!
//! Held from the CLI and not from the loader, for the reason
//! `a_wait_whose_deadline_was_never_written_is_reported_by_the_tool_the_author_runs`
//! gives: a loader test is a Rust caller, and a Rust caller is exactly what kept
//! the last unreachable diagnostic looking alive. These load the worked example
//! off disk, pass nothing, and run the binary.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply `edits` as (file, from, to), return the root.
fn edited(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-shares-{name}-{}", std::process::id()));
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

const TEAMWORK: &str = "agents/refund-desk/teamwork.yaml";

#[test]
fn shares_that_add_up_to_more_than_the_pot_are_refused_at_check_time() {
    let root = edited(
        "over",
        &[(TEAMWORK, "fraud-checker: 40%", "fraud-checker: 90%")],
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        !out.status.success(),
        "150% of a pot must not load cleanly:\n{text}"
    );
    assert!(
        text.contains("rule: loader/shares-add-up-to-more-than-the-pot"),
        "{text}"
    );
    // The total that was WRITTEN, not "too much" — an author who cannot see the
    // sum cannot tell which line to change.
    assert!(
        text.contains("add up to 150%"),
        "must state the total: {text}"
    );
    assert!(
        text.contains("teamwork.yaml:"),
        "must name the file and line: {text}"
    );
    assert!(
        text.contains("shares:"),
        "must point at the block that is wrong: {text}"
    );
    // A fix that is a list to type, not an instruction to work one out.
    assert!(text.contains("`policy-checker: 40%`"), "{text}");
    assert!(text.contains("`fraud-checker: 60%`"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_teammate_left_out_of_by_share_is_named_at_check_time() {
    let root = edited("missing", &[(TEAMWORK, "  fraud-checker: 40%\n", "")]);
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        !out.status.success(),
        "a teammate with no share must not load cleanly:\n{text}"
    );
    assert!(
        text.contains("rule: loader/teammate-with-no-share"),
        "{text}"
    );
    assert!(
        text.contains("'fraud-checker'"),
        "must name who was left out: {text}"
    );
    assert!(
        text.contains("teamwork.yaml:"),
        "must name the file and line: {text}"
    );
    // The exact line to type, with what is left of the pot already worked out.
    assert!(
        text.contains("Add a line under `shares:`: `fraud-checker: 40%`"),
        "{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn shares_that_add_up_to_less_than_the_pot_stay_legal() {
    // The decision this rule had to take and state: `Pool.share_of` multiplies,
    // so 90% of the pot is nine tenths of the budget spent and a tenth held
    // back. That is a coherent thing to want, the field's help already promises
    // it ("adding up to 100% or less"), and refusing it would make the schema
    // lie in the other direction.
    let root = edited(
        "under",
        &[(TEAMWORK, "policy-checker: 60%", "policy-checker: 50%")],
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        out.status.success(),
        "90% of a pot is a reserve, not a mistake:\n{text}"
    );
    // Nothing may be said ABOUT THE SHARES, which is what this test is about. It
    // used to assert that no `loader/` rule fired at all, which was the same
    // thing for as long as the shares were the only thing this tree could draw a
    // line about — and stopped being so when §8.3a rule 4 began saying, of a
    // skill, how many written rules it holds. A note about a document the author
    // asked to be told about is not a complaint about their percentages.
    assert!(
        !text.contains("loader/shares") && !text.to_lowercase().contains("share of"),
        "and nothing may be said about it: {text}"
    );
    assert!(
        !text.contains("warning:") && !text.contains("error:"),
        "{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_for_an_over_allocated_list_says_out_loud_that_under_is_allowed() {
    // Without this sentence the author is told "100% or less", lands on 90%,
    // and has no way to know they have not made a second mistake nobody
    // mentioned. Read by the same person, in the same session, seconds apart.
    let root = edited(
        "under-is-fine",
        &[(TEAMWORK, "fraud-checker: 40%", "fraud-checker: 90%")],
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(text.contains("Less than 100% is allowed"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_share_for_somebody_who_is_not_on_the_team_is_refused_at_check_time() {
    // The line that costs money. `sum(self.shares.values())` at run time counts
    // the stranger, and `Pool.share_of` is only ever asked about members — so
    // `fruad-checker: 40%` takes 40% out of the pot, gives it to nobody, and
    // leaves the real `fraud-checker` on a slice of 0.0.
    let root = edited(
        "stranger",
        &[(TEAMWORK, "  fraud-checker: 40%", "  fruad-checker: 40%")],
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(!out.status.success(), "{text}");
    assert!(
        text.contains("rule: loader/share-for-someone-not-on-the-team"),
        "{text}"
    );
    assert!(
        text.contains("'fruad-checker'"),
        "must name the line that reaches nobody: {text}"
    );
    assert!(
        text.contains("teamwork.yaml:"),
        "must name the file and line: {text}"
    );
    assert!(
        text.contains("policy-checker, fraud-checker"),
        "must list the real team: {text}"
    );

    // And ONCE. The same typo also leaves `fraud-checker` without a share, and
    // that second sentence's fix is a line to ADD — the wrong edit, and the
    // wrong number. One mistake, one message; the same rule
    // `loader/wait-with-no-deadline` keeps when three lines put one question.
    assert!(
        !text.contains("rule: loader/teammate-with-no-share"),
        "one typo must not be said twice:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn shares_nothing_divides_by_are_reported_as_lines_that_reach_nobody() {
    // `Pool.share_of` consults `self.shares` only under `by-share`. Under
    // `evenly` the block is decoration, and the run splits the budget a
    // different way from the one written down — the same silent-loss shape
    // `loader/shows-nothing-can-supply` reports about a `shows:` name.
    let root = edited(
        "ignored",
        &[(
            TEAMWORK,
            "divides-the-budget: by-share",
            "divides-the-budget: evenly",
        )],
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        text.contains("rule: loader/shares-nothing-divides-by"),
        "{text}"
    );
    assert!(text.contains("read by nobody"), "{text}");
    assert!(
        text.contains("Write `divides-the-budget: by-share`"),
        "the fix has to be typeable: {text}"
    );
    // A warning, not a refusal: the tree still runs, it just does not do what
    // the author wrote.
    assert!(out.status.success(), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn no_message_about_shares_assumes_programming_knowledge() {
    let root = edited(
        "jargon",
        &[(TEAMWORK, "fraud-checker: 40%", "fraud-checker: 90%")],
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout).to_lowercase();
    for word in [
        "enum",
        "variant",
        "deserialize",
        "serde",
        "unwrap",
        "panic",
        "trait",
        "struct",
        "vec<",
        "option<",
        "float",
        "sum(",
        "assertion",
        "invariant",
    ] {
        assert!(
            !text.contains(word),
            "message assumes programming knowledge ('{word}'):\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}
