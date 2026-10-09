//! A workflow is held to the structure only a whole-tree walk can see
//! (02W §3): a line beside a `does:` it does not belong to (WF-3), workflows
//! that call each other in a circle (WF-8), a version of something that has
//! none (WF-35), the old name `forget-after:` (WF-37), a path that answers
//! nothing (WF-38), a stage nothing reaches, and the stage a `then:` names.
//!
//! Over a copy of `tests/trees/a-workflow-of-every-shape/`, which loads clean.

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
    let dst = std::env::temp_dir().join(format!("pact-structure-{name}-{}", std::process::id()));
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

fn refused(name: &str, edits: &[(&str, &str, &str)], rule: &str) -> String {
    let (ok, text) = check(&edited(name, edits, &[]));
    assert!(!ok, "{name}: expected `{rule}`:\n{text}");
    assert!(
        text.contains(&format!("rule: {rule}")),
        "{name}: expected `{rule}`:\n{text}"
    );
    text
}

#[test]
fn a_line_beside_the_wrong_does_is_never_read_and_says_where_it_belongs() {
    let text = refused(
        "over-on-a-call",
        &[(
            FLOW,
            "    call: sorter\n",
            "    call: sorter\n    over: input.attachments\n",
        )],
        "loader/a-line-this-stage-never-reads",
    );
    assert!(
        text.contains(
            "'sort' does `call` and writes `over:`, which only a stage that does `each` reads"
        ),
        "{text}"
    );
    assert!(
        text.contains("fix: Delete it, or change `does:` to `each`."),
        "{text}"
    );
    // `together` starts every inside stage at once, so it has no first one.
    let text = refused(
        "starts-at-on-together",
        &[(
            FLOW,
            "    does: together\n",
            "    does: together\n    starts-at: left\n",
        )],
        "loader/a-line-this-stage-never-reads",
    );
    assert!(
        text.contains("'both' does `together` and writes `starts-at:`"),
        "{text}"
    );
    // A named team's words, on an `each`.
    let text = refused(
        "shares-on-each",
        &[(
            FLOW,
            "      waits-for: everyone\n",
            "      waits-for: everyone\n      shares:\n        sorter: 50%\n",
        )],
        "loader/a-line-this-stage-never-reads",
    );
    assert!(
        text.contains("writes `teamwork.shares:`, which belongs to a named team"),
        "{text}"
    );
}

#[test]
fn workflows_that_call_each_other_are_refused_at_the_line_that_closes_the_circle() {
    let text = refused(
        "circle",
        &[(
            "workflows/recheck.yaml",
            "    call: ledger/read-invoice\n",
            "    call: invoices\n",
        )],
        "loader/workflows-that-call-each-other",
    );
    assert!(
        text.contains("'invoices' calls 'recheck' calls 'invoices' again"),
        "{text}"
    );
    assert!(
        text.contains("a workflow that must come back is a `repeat`"),
        "{text}"
    );
    assert_eq!(
        text.matches("workflows-that-call-each-other").count(),
        1,
        "one circle, one message:\n{text}"
    );
}

#[test]
fn a_version_is_only_on_a_call_to_a_workflow() {
    let text = refused(
        "version-on-an-agent",
        &[(
            FLOW,
            "    call: sorter\n",
            "    call: sorter\n    version: latest\n",
        )],
        "loader/a-version-of-something-that-has-none",
    );
    assert!(
        text.contains("'sort' asks for version 'latest' of 'sorter', which is an agent"),
        "{text}"
    );
    assert!(text.contains("fix: Delete `version:`."), "{text}");
}

#[test]
fn forget_after_still_loads_and_says_it_is_now_kept_for() {
    let root = edited(
        "forget-after",
        &[(
            "workspace.yaml",
            "    kept-for: 30 days\n",
            "    forget-after: 30d\n",
        )],
        &[],
    );
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(out.status.success(), "a warning, for one release:\n{text}");
    assert!(
        text.contains("warning: `forget-after:` is now called `kept-for:`"),
        "{text}"
    );
    assert!(
        text.contains("fix: Rename it `kept-for:`; the value is unchanged."),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/forget-after-is-now-kept-for"),
        "{text}"
    );
}

#[test]
fn a_path_that_answers_nothing_is_refused_when_the_workflow_answers() {
    let text = refused(
        "no-answer",
        &[(FLOW, "      other: reply\n", "      other: done\n")],
        "loader/a-path-that-answers-nothing",
    );
    assert!(
        text.contains("the path 'sort' → 'what-is-it' reaches the end with no `answer` stage"),
        "{text}"
    );
    // A flow nobody waits on may end anywhere.
    let (ok, text) = check(&edited(
        "nobody-waits",
        &[
            (FLOW, "      other: reply\n", "      other: done\n"),
            (FLOW, "answers-with:\n  posted: yes or no\n", ""),
        ],
        &[],
    ));
    assert!(ok, "{text}");
}

#[test]
fn a_stage_nothing_reaches_is_dead_text_in_a_workflow_and_inside_an_each() {
    let text = refused(
        "unreached",
        &[(
            FLOW,
            "  reply:\n    does: answer\n",
            "  reply:\n    does: answer\n  spare:\n    does: answer\n",
        )],
        "loader/stage-nothing-reaches",
    );
    assert!(
        text.contains("Nothing in the workflow 'invoices' ever sends the run to 'spare'"),
        "{text}"
    );
    let text = refused(
        "unreached-inside",
        &[(FLOW, "        then:\n          answered: pay\n", "")],
        "loader/stage-nothing-reaches",
    );
    assert!(
        text.contains("Nothing in 'each-attachment' ever sends the run to 'pay'"),
        "{text}"
    );
    let text = refused(
        "no-first-inside",
        &[(FLOW, "    starts-at: read\n", "")],
        "loader/loop-with-no-first-stage",
    );
    assert!(
        text.contains("'each-attachment' does not say which of its own stages runs first"),
        "{text}"
    );
}

#[test]
fn a_then_names_the_stages_beside_it_and_never_the_ones_inside_it() {
    // `each-attachment`'s own `then:` leads to a sibling; its inside stage
    // `read` is not one, however near it is written.
    let text = refused(
        "into-the-body",
        &[(
            FLOW,
            "      answered: check-twice\n",
            "      answered: read\n",
        )],
        "schema/no-such-name",
    );
    assert!(text.contains("'answered' names 'read'"), "{text}");
}

#[test]
fn a_combine_rule_is_one_of_the_six_and_a_moment_is_a_time_or_a_moment() {
    let text = refused(
        "bad-rule",
        &[(FLOW, "      posted: vote\n", "      posted: average\n")],
        "schema/not-a-combine-rule",
    );
    assert!(
        text.contains("'average' is not a way of combining answers"),
        "{text}"
    );
    assert!(text.contains("`top <n> highest by <field>`"), "{text}");
    refused(
        "top-zero",
        &[(FLOW, "top 1 highest by total", "top 0 highest by total")],
        "schema/not-a-combine-rule",
    );
    let (ok, text) = check(&edited(
        "moment-as-time",
        &[(
            FLOW,
            "kept-for:\n  at: input.received-on\n  after: 7 days\n",
            "kept-for: 90 days\n",
        )],
        &[],
    ));
    assert!(ok, "a moment written as a length of time:\n{text}");
    refused(
        "moment-wrong",
        &[(FLOW, "  after: 7 days\n", "  after: soon\n")],
        "schema/wrong-type",
    );
    refused(
        "moment-field",
        &[(FLOW, "  after: 7 days\n", "  later: 7 days\n")],
        "schema/unknown-field",
    );
}

#[test]
fn an_undo_names_a_tools_action_or_a_workflow() {
    let text = refused(
        "undo-agent",
        &[(FLOW, "undone-by: ledger/unpost-all\n", "undone-by: sorter\n")],
        "loader/no-such-name",
    );
    assert!(
        text.contains("'invoices' is undone by 'sorter', which is an agent"),
        "{text}"
    );
    refused(
        "undo-missing",
        &[(
            FLOW,
            "        undone-by: ledger/unpost\n",
            "        undone-by: ledger/void\n",
        )],
        "loader/no-such-name",
    );
}
