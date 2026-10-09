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
fn an_until_of_tool_lines_only_loads_and_asks_its_tool_each_round() {
    // WF-14 reads what an `until:` line's `value:` names. Until `value:` lines
    // can be written (the condition grammar), a line that asks a tool each
    // round may answer differently, so it is left to the tool.
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
    assert!(ok, "{text}");
}

#[test]
fn a_value_remembered_from_a_stage_a_round_can_end_without_is_refused() {
    // 02W §2.0: `steps.<stage>` only where every path passes it, and
    // `comes-from:` has no `, optional`. A decision can end the round first.
    let root = edited(
        "from-a-branch",
        &[(
            FLOW,
            "    at-most: 2\n    starts-at: recheck\n    steps:\n      recheck:\n",
            "    at-most: 2\n    remembers:\n      tries:\n        description: what each round found\n        lasts: one-run\n        comes-from: steps.recheck.run\n        combines-by: keep-all\n    starts-at: pick\n    steps:\n      pick:\n        does: decide\n        chooses-between:\n          again: recheck\n          enough: done\n      recheck:\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-binding-to-a-stage-that-may-not-have-run"),
        "{text}"
    );
    assert!(
        text.contains(
            "'check-twice' reads 'steps.recheck.run' when a round ends, but a round can end on \
             the path through 'enough' without running 'recheck'."
        ),
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
