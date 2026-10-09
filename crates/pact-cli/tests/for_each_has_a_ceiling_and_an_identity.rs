//! An `each` has a ceiling and an identity (02W §3 WF-10, WF-11, §8).
//!
//! WF-10: an `each` with no `limits.items-at-most` is refused, worded as 02W §3
//! prints it — the second of its three printed examples. WF-11: an `each`
//! whose inside writes and does not say what makes an item itself is refused,
//! because retries and "the same call" are worked out from `identified-by:`,
//! never from where an item sits in the list.
//!
//! Every test drives the real binary over a copy of
//! `tests/trees/a-workflow-of-every-shape/`, which loads clean.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/a-workflow-of-every-shape"
    ))
}

fn copy(src: &Path, dst: &Path) {
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

/// A copy of the tree with `edits` applied (file, text to find, its
/// replacement), and any extra files written.
fn edited(name: &str, edits: &[(&str, &str, &str)], extra: &[(&str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-every-shape-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    for (file, text) in extra {
        let p = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    }
    dst
}

fn check(root: &Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

const FLOW: &str = "workflows/invoices.yaml";
const CEILING: &str =
    "    limits:\n      items-at-most: 20\n      when-it-runs-out: stop-and-say-so\n";

#[test]
fn the_tree_with_a_ceiling_and_an_identity_loads_clean() {
    let (ok, text) = check(&tree());
    assert!(ok, "{text}");
}

#[test]
fn for_each_with_no_ceiling_prints_as_the_design_shows_it() {
    let root = edited("no-ceiling", &[(FLOW, CEILING, "")], &[]);
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    // The design's own print, with what the binding names in place of the
    // email of its example: `over: input.attachments` goes through attachments.
    assert!(
        text.contains(
            "error: 'each-attachment' goes through a list with no ceiling, so five thousand \
             attachments start five thousand runs."
        ),
        "{text}"
    );
    assert!(text.contains("|     does: each\n"), "{text}");
    assert!(
        text.contains("|     ^^^^^^^^^^\n"),
        "the caret is under `does: each`:\n{text}"
    );
    assert!(
        text.contains(
            "fix: Add under `limits:` the most it should take and what happens past that — \
             `items-at-most: 20` and `when-it-runs-out: ask-a-person`."
        ),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/for-each-with-no-ceiling"),
        "{text}"
    );
}

#[test]
fn a_ceiling_with_no_action_beside_it_is_the_companion_rule_not_this_one() {
    let root = edited(
        "no-action",
        &[(FLOW, "      when-it-runs-out: stop-and-say-so\n", "")],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok && text.contains("schema/missing-companion"), "{text}");
    assert!(!text.contains("for-each-with-no-ceiling"), "{text}");
}

#[test]
fn items_told_apart_by_position_are_refused_when_the_inside_writes() {
    let root = edited(
        "by-position",
        &[(FLOW, "    identified-by: [content-hash]\n", "")],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/items-told-apart-by-position"),
        "{text}"
    );
    assert!(
        text.contains("'each-attachment' writes for each item ('pay' does)"),
        "{text}"
    );
    assert!(text.contains("`identified-by: [content-hash]`"), "{text}");
}

#[test]
fn an_inside_that_only_reads_needs_no_identity() {
    let root = edited(
        "only-reads",
        &[
            (FLOW, "    identified-by: [content-hash]\n", ""),
            (
                FLOW,
                "        call: ledger/post\n",
                "        call: ledger/read-invoice\n",
            ),
            (FLOW, "        undone-by: ledger/unpost\n", ""),
        ],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(
        ok,
        "an `each` that only looks things up is told apart by nothing it writes:\n{text}"
    );
}

#[test]
fn a_write_inside_a_called_workflow_is_a_write_inside_the_each() {
    let root = edited(
        "called-writes",
        &[
            (FLOW, "    identified-by: [content-hash]\n", ""),
            (
                FLOW,
                "        call: ledger/post\n",
                "        call: recheck\n",
            ),
            (FLOW, "        undone-by: ledger/unpost\n", ""),
            (
                "workflows/recheck.yaml",
                "call: ledger/read-invoice",
                "call: ledger/post",
            ),
        ],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(
        !ok && text.contains("rule: loader/items-told-apart-by-position"),
        "{text}"
    );
}
