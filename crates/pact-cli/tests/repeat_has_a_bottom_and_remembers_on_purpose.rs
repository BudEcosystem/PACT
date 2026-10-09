//! A `repeat` has a bottom and remembers on purpose (02W §3 WF-12, WF-13,
//! WF-14, §8).
//!
//! "Forever" is a schedule plus memory, never a `repeat`: one with no
//! `at-most:` is refused (WF-12). What it remembers between rounds says where
//! each value comes from, a stage inside the round (WF-13), and its `until:`
//! reads something the round writes (WF-14), or it could never change. That
//! `.ended` and `.rounds` are set is the runtime's half.
//!
//! Over a copy of `tests/trees/a-workflow-of-every-shape/`.

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

#[test]
fn repeat_with_no_bottom_is_refused_and_told_how_to_end() {
    let root = edited(
        "no-bottom",
        &[(
            FLOW,
            "    at-most: 2\n    starts-at: recheck\n",
            "    starts-at: recheck\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/repeat-with-no-bottom"),
        "{text}"
    );
    assert!(
        text.contains("'check-twice' repeats with no bottom"),
        "{text}"
    );
    assert!(
        text.contains("fix: Add `at-most:` — `at-most: 5`. \"Forever\" is a schedule plus memory."),
        "{text}"
    );
    assert!(
        text.contains("|     does: repeat"),
        "the caret is on the stage's `does:`:\n{text}"
    );
}

#[test]
fn a_repeat_with_a_bottom_loads_clean() {
    let (ok, text) = check(&tree());
    assert!(ok, "{text}");
}

const ROUND: &str = "    at-most: 2\n    starts-at: recheck\n";

#[test]
fn a_value_remembered_from_nowhere_is_refused() {
    let root = edited(
        "from-nowhere",
        &[(
            FLOW,
            ROUND,
            "    at-most: 2\n    remembers:\n      tries:\n        description: what each round found\n        lasts: one-run\n    starts-at: recheck\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/remembered-from-nowhere"),
        "{text}"
    );
    assert!(
        text.contains(
            "'check-twice' remembers 'tries' between rounds and does not say where it comes from"
        ),
        "{text}"
    );
    assert!(text.contains("fix: Point `comes-from:` at a stage inside the round — `comes-from: steps.recheck.<field>`."), "{text}");
}

#[test]
fn a_value_remembered_from_outside_the_round_is_refused() {
    let root = edited(
        "from-outside",
        &[(
            FLOW,
            ROUND,
            "    at-most: 2\n    remembers:\n      tries:\n        description: what each round found\n        lasts: one-run\n        comes-from: input.attachments\n        combines-by: keep-all\n    starts-at: recheck\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/remembered-from-nowhere"),
        "{text}"
    );
    assert!(
        text.contains("from 'input.attachments', which is not a stage inside the round"),
        "{text}"
    );
}

#[test]
fn a_value_remembered_from_inside_the_round_loads_clean() {
    let root = edited(
        "from-inside",
        &[(
            FLOW,
            ROUND,
            "    at-most: 2\n    remembers:\n      tries:\n        description: what each round found\n        lasts: one-run\n        comes-from: steps.recheck.run\n        combines-by: keep-all\n    starts-at: recheck\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(ok, "{text}");
}

#[test]
fn an_until_that_reads_what_the_round_writes_loads_clean() {
    // WF-14's positive half, now that `value:` can be written (02W §2.6): the
    // round's own stage changes every round, so the `until:` can come to hold.
    let root = edited(
        "until-round",
        &[(
            FLOW,
            ROUND,
            "    at-most: 2\n    until:\n      - { value: steps.recheck.run, is-empty: no }\n    starts-at: recheck\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(ok, "{text}");
}

#[test]
fn an_until_that_reads_nothing_the_round_writes_is_refused() {
    let root = edited(
        "until-fixed",
        &[(
            FLOW,
            ROUND,
            "    at-most: 2\n    until:\n      - { value: input.received-on, is-empty: no }\n    starts-at: recheck\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/until-that-cannot-change"),
        "{text}"
    );
    assert!(
        text.contains("'check-twice' repeats until something holds, and its `until:` reads nothing the round writes"),
        "{text}"
    );
}

#[test]
fn an_until_that_looks_at_a_call_is_refused_because_a_round_calls_nothing_there() {
    // `tool:` is an approval rule's: a condition in a workflow looks at a value
    // (WF-18). Before the condition grammar it loaded and was left to the tool.
    let root = edited(
        "until-tool",
        &[(
            FLOW,
            ROUND,
            "    at-most: 2\n    until:\n      - tool: ledger/read-invoice\n    starts-at: recheck\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/compared-in-the-wrong-shape"),
        "{text}"
    );
    assert!(text.contains("fix: Write `value:` instead"), "{text}");
}

#[test]
fn a_value_remembered_from_a_stage_some_rounds_skip_adds_nothing_from_those_rounds() {
    // 02W §5.3 (#69): a lesson is written only when the verdict fails, so a
    // round that ends without running the stage `comes-from:` names adds
    // nothing to what is remembered. An `until:` still reads only a stage every
    // way out of the round passes (the unit tests of `bindings.rs`).
    let root = edited(
        "from-a-branch",
        &[(
            FLOW,
            "    at-most: 2\n    starts-at: recheck\n    steps:\n      recheck:\n",
            "    at-most: 2\n    remembers:\n      tries:\n        description: what each round found\n        lasts: one-run\n        comes-from: steps.recheck.run\n        combines-by: keep-all\n    starts-at: pick\n    steps:\n      pick:\n        does: decide\n        chooses-between:\n          again: recheck\n          enough: done\n        by:\n          - rules:\n              - choose: again\n      recheck:\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(ok, "{text}");
    assert!(
        !text.contains("loader/a-binding-to-a-stage-that-may-not-have-run"),
        "{text}"
    );
}

#[test]
fn a_line_only_a_repeat_reads_is_refused_on_the_workspaces_memory() {
    let root = edited(
        "workspace-round",
        &[(
            "workspace.yaml",
            "    kept-for: 30 days\n",
            "    kept-for: 30 days\n    comes-from: steps.recheck.run\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-line-this-stage-never-reads"),
        "{text}"
    );
    assert!(
        text.contains("'paused', which the workspace remembers, writes `comes-from:`"),
        "{text}"
    );
}
