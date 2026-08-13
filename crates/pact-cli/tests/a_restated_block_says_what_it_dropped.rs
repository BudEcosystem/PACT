//! **A restated block says what it dropped** — C8 §8 acceptance row 3, from
//! disk, against the real binary.
//!
//! The merge is shallow on purpose: a restated map REPLACES the base's map,
//! because deep merge cannot express removal — an author who restates a
//! narrower `limits:` means to take something away. What D-1 priced was the
//! silence: the spend cap fell out and nothing said so. The warning under test
//! here is that provenance, and this file measures it the way an author meets
//! it — `pact check` over `tests/trees/a-narrower-desk/`, a tree whose desk
//! restates its pattern's `limits:` block and drops the cap on purpose, to be
//! seen.
//!
//! That tree lives in `tests/trees/` and not `examples/` because it MUST warn:
//! the examples census runs `--deny-warnings`, and downgrading a diagnostic to
//! keep a script green is how a checker stops checking.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> String {
    format!(
        "{}/../../tests/trees/a-narrower-desk",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn run(args: &[&str]) -> (Option<i32>, String, String) {
    let out = pact().args(args).output().expect("runs");
    (
        out.status.code(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

/// The dropped keys are named, with their values; the restated one is not.
///
/// A warning and not a refusal — narrowing is the case the shallow rule
/// exists for — so the check still exits 0. The sentence names what fell out
/// (`cost-per-request-under: 0.05 USD`, `finishes-within: 30s`) and does not
/// name what the desk restated: `steps-at-most` was written, not dropped.
///
/// Mutation: make the loss silent again (delete the diags.push in derive_one)
/// or make the merge deep (nothing is dropped, so nothing is said — and the
/// pinned narrowing test dies with this one).
#[test]
fn the_dropped_keys_are_named() {
    // `pact check` reports on stdout — the channel every other check test
    // reads — so that is where the author meets this sentence.
    let (code, out, err) = run(&["check", &tree()]);
    assert_eq!(code, Some(0), "a narrowing is allowed, out loud:\n{out}{err}");
    assert!(
        out.contains("loader/restating-a-block-drops-the-rest"),
        "the warning reaches the author from disk, not only from a hand-built map:\n{out}{err}"
    );
    assert!(
        out.contains("`cost-per-request-under: 0.05 USD`"),
        "the dropped cap is named with its value:\n{out}"
    );
    assert!(out.contains("finishes-within"), "and so is the deadline:\n{out}");
    assert!(
        !out.contains("`steps-at-most: 4`"),
        "a key the desk wrote itself is not something it dropped:\n{out}"
    );
}

/// `--deny-warnings` turns the same sentence fatal.
///
/// The provenance has teeth for whoever asks for them: a fleet that will not
/// ship a silent narrowing gates on this exit code.
#[test]
fn deny_warnings_makes_it_fatal() {
    let (code, out, err) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(
        code,
        Some(1),
        "under --deny-warnings a dropped cap is a stop, not a shrug:\n{out}{err}"
    );
}
