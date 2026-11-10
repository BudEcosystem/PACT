//! Law 2 of `docs/97-PRIMITIVES.md`, option A (`docs/98` WP-3): every cycle has
//! a limit, and the one way to have none is an owner's `limits.unbounded: yes`.
//!
//! - `unbounded: yes` with no `owners:` entry naming the agent or workflow is
//!   refused (`loader/unbounded-without-an-owner`).
//! - With one, the tree loads, says `loader/this-tree-may-not-stop` as a note,
//!   and still passes `--deny-warnings`.
//! - Beside `steps-at-most:` it is a contradiction; on a stage it means nothing.
//! - An owner-approved unbounded workflow's `repeat` may go without `at-most:`.
//! - A workflow that calls an agent whose TEAMMATE uses that workflow starts
//!   itself, and the call graph now sees the teammate hop.

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

fn copied(tree: &str, name: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join(tree);
    let dst = std::env::temp_dir().join(format!("pact-unbounded-{name}-{}", std::process::id()));
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

fn append(tree: &Path, file: &str, text: &str) {
    let path = tree.join(file);
    let mut was = std::fs::read_to_string(&path).unwrap_or_default();
    was.push_str(text);
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(&path, was).unwrap();
}

fn check(tree: &Path, deny: bool) -> (bool, String) {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_pact"));
    cmd.arg("check").arg(tree);
    if deny {
        cmd.arg("--deny-warnings");
    }
    let out = cmd.output().unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

const DESK: &str = "examples/refund-desk";
const LIMITS: &str = "agents/refund-desk/limits.yaml";
const SHAPES: &str = "tests/trees/a-workflow-of-every-shape";
const INVOICES: &str = "workflows/invoices.yaml";

#[test]
fn an_agent_with_no_limit_and_no_owner_is_refused() {
    let tree = copied(DESK, "no-owner");
    edit(&tree, LIMITS, "steps-at-most: 12\n", "unbounded: yes\n");
    let (ok, said) = check(&tree, false);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/unbounded-without-an-owner"),
        "{said}"
    );
    assert!(
        said.contains("agents.refund-desk.limits"),
        "the fix names the key: {said}"
    );
}

#[test]
fn an_owners_unbounded_loads_says_so_and_passes_deny_warnings() {
    let tree = copied(DESK, "owned");
    edit(&tree, LIMITS, "steps-at-most: 12\n", "unbounded: yes\n");
    append(
        &tree,
        "workspace.yaml",
        "owners:\n  agents.refund-desk.limits:\n    owned-by: support-operations\n",
    );
    let (ok, said) = check(&tree, true);
    assert!(ok, "{said}");
    assert!(said.contains("note:"), "{said}");
    assert!(said.contains("loader/this-tree-may-not-stop"), "{said}");
    assert!(said.contains("'support-operations'"), "{said}");
}

#[test]
fn the_owner_may_be_named_with_slashes_or_for_the_whole_agent() {
    let tree = copied(DESK, "slashes");
    edit(&tree, LIMITS, "steps-at-most: 12\n", "unbounded: yes\n");
    append(
        &tree,
        "workspace.yaml",
        "owners:\n  agents/refund-desk:\n    owned-by: support-operations\n",
    );
    let (ok, said) = check(&tree, false);
    assert!(ok, "{said}");
    assert!(said.contains("loader/this-tree-may-not-stop"), "{said}");
}

#[test]
fn unbounded_beside_a_written_limit_is_a_contradiction() {
    let tree = copied(DESK, "both");
    edit(
        &tree,
        LIMITS,
        "steps-at-most: 12\n",
        "steps-at-most: 12\nunbounded: yes\n",
    );
    let (ok, said) = check(&tree, false);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/unbounded-beside-a-limit"),
        "{said}"
    );
}

#[test]
fn a_repeat_with_no_bottom_is_still_refused_by_default() {
    let tree = copied(SHAPES, "bottomless");
    edit(&tree, INVOICES, "    at-most: 2\n", "");
    let (ok, said) = check(&tree, false);
    assert!(!ok, "{said}");
    assert!(said.contains("loader/repeat-with-no-bottom"), "{said}");
}

#[test]
fn an_owners_unbounded_workflow_may_repeat_with_no_bottom() {
    let tree = copied(SHAPES, "owned-repeat");
    edit(&tree, INVOICES, "    at-most: 2\n", "");
    edit(
        &tree,
        INVOICES,
        "published-as: [tool]\n",
        "published-as: [tool]\nlimits:\n  unbounded: yes\n",
    );
    edit(
        &tree,
        "workspace.yaml",
        "owners:\n",
        "owners:\n  workflows.invoices.limits:\n    owned-by: finance\n",
    );
    let (ok, said) = check(&tree, false);
    assert!(ok, "{said}");
    assert!(!said.contains("loader/repeat-with-no-bottom"), "{said}");
    assert!(said.contains("loader/this-tree-may-not-stop"), "{said}");
}

#[test]
fn unbounded_on_a_stage_means_nothing_and_says_so() {
    let tree = copied(SHAPES, "stage");
    edit(
        &tree,
        INVOICES,
        "      items-at-most: 20\n",
        "      items-at-most: 20\n      unbounded: yes\n",
    );
    let (ok, said) = check(&tree, false);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/unbounded-where-it-means-nothing"),
        "{said}"
    );
}

#[test]
fn a_workflow_whose_agents_teammate_uses_it_starts_itself() {
    let tree = copied(SHAPES, "teammate");
    edit(
        &tree,
        "agents/sorter/agent.yaml",
        "answers-with:",
        "team:\n  helper: Helps sort.\nanswers-with:",
    );
    append(
        &tree,
        "agents/helper/agent.yaml",
        "description: Helps sort.\ninstructions: Help sort.\nuses:\n  - invoices\n",
    );
    let (ok, said) = check(&tree, false);
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-workflow-its-own-agent-starts")
            || said.contains("loader/workflows-that-call-each-other"),
        "{said}"
    );
    assert!(said.contains("'helper'"), "{said}");
}
