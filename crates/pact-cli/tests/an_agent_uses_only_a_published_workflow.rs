//! **An agent may use a workflow as a tool only when the workflow is published as one** (N2).
//!
//! 02W gave `published-as: [tool]` to a workflow and said an agent may then be
//! given it, without saying how an agent names it. It names it as it names
//! everything else it may use: on its `uses:` line, which now draws from
//! `workflows` too. Two things are refused, each where the author wrote it:
//!
//! - a workflow whose `published-as:` does not list `tool` (nobody offered it to
//!   agents, so no model is handed it by a stray line);
//! - a name that is a workflow and also a tool, a skill, a set of documents or a
//!   program, since nothing could tell which one the agent is given.
//!
//! Fixture: `tests/trees/an-agent-that-uses-a-workflow/`. Every test drives the
//! real binary over a real tree.

use std::path::{Path, PathBuf};
use std::process::Command;

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/an-agent-that-uses-a-workflow"
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

/// A copy of the tree with one edit (file, text to find, its replacement) and
/// any extra files written.
fn edited(name: &str, edit: (&str, &str, &str), extra: &[(&str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-flow-tool-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    let (file, from, to) = edit;
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    for (file, text) in extra {
        std::fs::write(dst.join(file), text).unwrap();
    }
    dst
}

fn run(args: &[&str]) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .output()
        .expect("runs");
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.success(), said)
}

const FLOW: &str = "workflows/order-status.yaml";

#[test]
fn an_agent_names_a_published_workflow_on_its_uses_line() {
    let root = tree();
    let (ok, said) = run(&["check", root.to_str().unwrap(), "--deny-warnings"]);
    assert!(
        ok,
        "a desk using a workflow published as a tool loads clean:\n{said}"
    );
    let (ok, shown) = run(&["show", root.to_str().unwrap()]);
    assert!(ok, "{shown}");
    let document: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    assert_eq!(document["agents"]["desk"]["uses"][0], "order-status");
    assert_eq!(
        document["workflows"]["order-status"]["published-as"][0],
        "tool"
    );
}

#[test]
fn a_workflow_nobody_published_as_a_tool_is_refused_where_the_agent_names_it() {
    let root = edited("unpublished", (FLOW, "published-as: [tool]\n", ""), &[]);
    let (ok, said) = run(&["check", root.to_str().unwrap()]);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-workflow-nobody-published-as-a-tool"),
        "{said}"
    );
    assert!(
        said.contains("agents/desk.yaml:5:5"),
        "the caret is on the `uses:` entry:\n{said}"
    );
    assert!(
        said.contains("fix: Add `published-as: [tool]` to `workflows/order-status.yaml`"),
        "{said}"
    );
}

#[test]
fn a_workflow_published_only_another_way_is_not_a_tool() {
    let root = edited(
        "as-api",
        (
            FLOW,
            "published-as: [tool]",
            "published-as: [api, mcp-tool]",
        ),
        &[],
    );
    let (ok, said) = run(&["check", root.to_str().unwrap()]);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-workflow-nobody-published-as-a-tool"),
        "{said}"
    );
}

#[test]
fn a_name_that_is_a_workflow_and_a_tool_cannot_be_used() {
    let tool = std::fs::read_to_string(tree().join("tools/orders.yaml")).unwrap();
    let root = edited(
        "two-things",
        ("agents/desk.yaml", "Answers questions", "Answers questions"),
        &[("tools/order-status.yaml", &tool)],
    );
    let (ok, said) = run(&["check", root.to_str().unwrap()]);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-name-the-workspace-already-has"),
        "{said}"
    );
    assert!(
        said.contains("both a workflow and one of the workspace's tools"),
        "{said}"
    );
}

#[test]
fn a_name_nothing_has_is_still_no_such_name() {
    let root = edited(
        "missing",
        ("agents/desk.yaml", "  - order-status", "  - order-statu"),
        &[],
    );
    let (ok, said) = run(&["check", root.to_str().unwrap()]);
    assert!(!ok, "{said}");
    assert!(
        said.contains("order-status"),
        "the nearest name is offered:\n{said}"
    );
}
