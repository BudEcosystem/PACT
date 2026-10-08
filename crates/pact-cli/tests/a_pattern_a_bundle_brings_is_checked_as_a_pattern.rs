//! A pattern a bundle contributes is checked as a pattern, not as a finished
//! document.
//!
//! In a workspace, a pattern (`expects:`) is held to its own declarations and
//! removed before anything else reads the tree, so the money checks meet only
//! the rule made from it, with its figure filled. A pattern under a bundle's
//! `contributes/` stays where it was written, and the walk that reads every
//! `more-than:` met `<limit>` there and refused the bundle with
//! `loader/threshold-is-not-a-figure`. The `approve-requests` template could
//! not be mounted as a bundle for that reason.
//!
//! Fixture: `tests/trees/a-bundle-that-brings-a-pattern/`.

use std::process::Command;

fn tree() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/trees/a-bundle-that-brings-a-pattern")
}

fn check(root: &std::path::Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", "--deny-warnings"])
        .arg(root)
        .output()
        .expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.success(), text)
}

/// A copy of the fixture with one edit to the contributed pattern.
fn edited(name: &str, from: &str, to: &str) -> std::path::PathBuf {
    let dst =
        std::env::temp_dir().join(format!("pact-bundle-pattern-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&tree(), &dst);
    let file = dst.join("bundles/approvals-kit/contributes/policies/approval-limit.yaml");
    let text = std::fs::read_to_string(&file).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} is not in the pattern"
    );
    std::fs::write(&file, text.replace(from, to)).unwrap();
    dst
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

/// Mutation: let the `more-than:` walk descend into a pattern again, and this
/// fails with `loader/threshold-is-not-a-figure` at `<limit>`.
#[test]
fn a_hole_the_pattern_declares_loads_clean() {
    let (ok, text) = check(&tree());
    assert!(
        ok,
        "a contributed pattern with a declared hole must load clean:\n{text}"
    );
    assert!(!text.contains("threshold-is-not-a-figure"), "{text}");
}

/// Checked AS a pattern, not skipped: a hole nothing under `expects:` declares
/// is refused at the pattern, as it is in a workspace.
#[test]
fn a_hole_the_pattern_does_not_declare_is_refused_at_the_pattern() {
    let root = edited("undeclared", "more-than: <limit>", "more-than: <ceiling>");
    let (ok, text) = check(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(!ok, "an undeclared hole must be refused:\n{text}");
    assert!(text.contains("rule: loader/a-hole-nothing-fills"), "{text}");
    assert!(
        text.contains("`<ceiling>`"),
        "the refusal must name the hole: {text}"
    );
}

/// And a finished rule a bundle contributes is still held to a real figure:
/// without `expects:` the same file is a rule, and `<limit>` is not a figure.
#[test]
fn a_finished_rule_a_bundle_brings_still_needs_a_figure() {
    let root = edited(
        "finished",
        "expects:\n  limit:\n    shape: money\n    help: the largest request recorded without asking, for example 500 USD\n",
        "",
    );
    let (ok, text) = check(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(
        !ok,
        "a finished rule with a hole for a figure must be refused:\n{text}"
    );
    assert!(
        text.contains("rule: loader/threshold-is-not-a-figure"),
        "{text}"
    );
}
