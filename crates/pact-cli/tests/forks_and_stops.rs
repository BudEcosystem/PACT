//! `docs/98` WP-10: `forks:`, `does: stop` and `keeps-taking:` as lines a tree
//! can write, and the two rules that hold them.

use std::path::{Path, PathBuf};
use std::process::Command;

fn copy(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}

fn tree(src: &str, name: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join(src);
    let dst = std::env::temp_dir().join(format!("pact-forks-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    dst
}

fn edit(tree: &Path, file: &str, from: &str, to: &str) {
    let path = tree.join(file);
    let text = std::fs::read_to_string(&path).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {file} has no {from:?}"
    );
    std::fs::write(&path, text.replacen(from, to, 1)).unwrap();
}

fn check(tree: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(tree)
        .output()
        .unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

const SHAPES: &str = "tests/trees/a-workflow-of-every-shape";
const FLOW: &str = "workflows/invoices.yaml";

#[test]
fn a_stop_stage_may_stop_what_a_call_started_without_waiting() {
    let t = tree(SHAPES, "stop");
    edit(
        &t,
        FLOW,
        "    then:\n      answered: both\n",
        "    then:\n      answered: halt\n  halt:\n    does: stop\n    stops: steps.recheck.run\n    then:\n      answered: both\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

#[test]
fn a_stop_stage_may_not_stop_a_run_that_was_waited_for() {
    let t = tree(SHAPES, "stop-sort");
    edit(
        &t,
        FLOW,
        "    then:\n      answered: both\n",
        "    then:\n      answered: halt\n  halt:\n    does: stop\n    stops: steps.sort.run\n    then:\n      answered: both\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/stops-what-was-never-started-apart"),
        "{said}"
    );
    assert!(
        said.contains("`steps.recheck.run`"),
        "the fix names the one that can be: {said}"
    );
}

#[test]
fn a_stop_stage_with_nothing_to_stop_is_told_what_is_missing() {
    let t = tree(SHAPES, "stop-nothing");
    edit(
        &t,
        FLOW,
        "    then:\n      answered: both\n",
        "    then:\n      answered: halt\n  halt:\n    does: stop\n    then:\n      answered: both\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(said.contains("schema/missing-companion"), "{said}");
}

#[test]
fn a_stop_stage_has_no_place_in_an_agents_loop() {
    let t = tree("examples/refund-desk", "loop-stop");
    edit(
        &t,
        "loops/careful.yaml",
        "  reply:\n    does: answer\n",
        "  reply:\n    does: stop\n    stops: steps.x.run\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-stage-an-agent-cannot-have"),
        "{said}"
    );
}

#[test]
fn forks_on_a_branching_stage_and_a_loop_stage_load() {
    let t = tree(SHAPES, "forks");
    edit(
        &t,
        FLOW,
        "    does: repeat\n",
        "    does: repeat\n    forks: yes\n",
    );
    edit(
        &t,
        FLOW,
        "    does: together\n",
        "    does: together\n    forks: yes\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");

    let t = tree("examples/refund-desk", "loop-forks");
    edit(
        &t,
        "loops/careful.yaml",
        "    does: check-its-work\n",
        "    does: check-its-work\n    forks: yes\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

#[test]
fn forks_on_a_single_call_means_nothing_and_says_so() {
    let t = tree(SHAPES, "forks-call");
    edit(
        &t,
        FLOW,
        "    call: sorter\n",
        "    call: sorter\n    forks: yes\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/forks-where-nothing-branches"),
        "{said}"
    );
}

#[test]
fn keeps_taking_is_only_an_eachs() {
    let t = tree(SHAPES, "keeps");
    edit(
        &t,
        FLOW,
        "    over: input.attachments\n",
        "    over: input.attachments\n    keeps-taking: yes\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");

    let t = tree(SHAPES, "keeps-repeat");
    edit(
        &t,
        FLOW,
        "    does: repeat\n",
        "    does: repeat\n    keeps-taking: yes\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-line-this-stage-never-reads"),
        "{said}"
    );
}
