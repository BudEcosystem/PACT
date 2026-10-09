//! A workflow is a stage loop that belongs to no agent (02W §1, §8).
//!
//! It calls agents, tools, programs and other workflows, and it has no mind of
//! its own: `model:`, `instructions:`, `loop:`, `team:` and `uses:` are refused
//! on it (WF-1), and so are the four stages that think (WF-2). The other way
//! round, an agent's own loop may not write a workflow's stages.
//!
//! Every test drives the real binary over a copy of
//! `tests/trees/a-workflow-that-calls-and-answers/`, the smallest workflow there
//! is: one call to a tool's action, then the answer.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/a-workflow-that-calls-and-answers"
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
    let dst = std::env::temp_dir().join(format!("pact-workflow-{name}-{}", std::process::id()));
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

const FLOW: &str = "workflows/order-status.yaml";

#[test]
fn the_smallest_workflow_loads_clean_and_is_in_the_document_every_adapter_reads() {
    let (ok, text) = check(&tree());
    assert!(ok, "a call and an answer is a whole workflow:\n{text}");
    // A tree of workflows alone has something to run.
    assert!(!text.contains("nothing-can-run-this"), "{text}");
    let out = pact()
        .args(["show", tree().to_str().unwrap()])
        .output()
        .unwrap();
    let doc: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(
        doc["workflows"]["order-status"]["steps"]["look"]["call"],
        "orders/look-up"
    );
    assert_eq!(doc["workflows"]["order-status"]["starts-at"], "look");
}

#[test]
fn the_trees_digest_moves_when_a_workflow_does() {
    let digest = |root: &Path| {
        let out = pact()
            .args(["discover", root.to_str().unwrap()])
            .output()
            .unwrap();
        let found: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
        let one = if found.is_array() {
            found[0].clone()
        } else {
            found
        };
        one["digest"].as_str().unwrap().to_owned()
    };
    let reworded = edited(
        "digest",
        &[(
            FLOW,
            "Looks up an order and says where it is.",
            "Says where an order is.",
        )],
        &[],
    );
    assert_ne!(
        digest(&tree()),
        digest(&reworded),
        "a workflow is part of what the tree is"
    );
}

#[test]
fn a_workflow_that_writes_a_mind_of_its_own_is_told_to_call_an_agent_once_per_line() {
    for (key, line) in [
        ("model", "model: deepseek-chat\n"),
        ("instructions", "instructions: Be helpful.\n"),
        ("loop", "loop: pact:loop/standard\n"),
        ("team", "team:\n  helper: Helps.\n"),
        ("uses", "uses: [orders]\n"),
    ] {
        let root = edited(
            &format!("mind-{key}"),
            &[(FLOW, "accepts:\n", &format!("{line}accepts:\n"))],
            &[],
        );
        let (ok, text) = check(&root);
        assert!(!ok, "`{key}:` on a workflow must be refused:\n{text}");
        assert!(
            text.contains("rule: loader/a-workflow-with-a-mind-of-its-own"),
            "{text}"
        );
        assert!(text.contains(&format!("writes `{key}:`")), "{text}");
        assert!(
            text.contains("`does: call` and `call: <the agent>`"),
            "{text}"
        );
        // One mistake, one message: not also "not something a workflow can have".
        assert!(
            !text.contains("schema/unknown-field"),
            "{key} was told twice:\n{text}"
        );
        assert_eq!(text.matches("error:").count(), 1, "{text}");
    }
}

#[test]
fn a_stage_that_thinks_is_refused_in_a_workflow() {
    for does in ["think", "use-tools", "check-its-work", "run-code"] {
        let root = edited(
            &format!("thinks-{does}"),
            &[(
                FLOW,
                "  reply:\n    does: answer\n",
                &format!("  reply:\n    does: {does}\n"),
            )],
            &[],
        );
        let (ok, text) = check(&root);
        assert!(!ok, "`does: {does}` in a workflow must be refused:\n{text}");
        assert!(
            text.contains("rule: loader/a-stage-a-workflow-cannot-have"),
            "{text}"
        );
        assert!(text.contains(&format!("'reply' does `{does}`")), "{text}");
        assert!(text.contains("Call an agent that does it"), "{text}");
    }
}

#[test]
fn an_agents_loop_may_not_write_a_workflows_stage() {
    let root = edited(
        "agent-loop",
        &[],
        &[
            (
                "agents/desk/agent.yaml",
                "description: Answers.\ninstructions: Answer.\nloop: mine\n",
            ),
            (
                "loops/mine.yaml",
                "description: One stage.\nstarts-at: go\nsteps:\n  go:\n    does: each\n    over: input.x\n",
            ),
        ],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-stage-an-agent-cannot-have"),
        "{text}"
    );
    assert!(
        text.contains("'go' in the loop 'mine' does `each`"),
        "{text}"
    );
}

#[test]
fn a_call_to_something_that_is_not_here_names_what_is() {
    let root = edited(
        "no-such",
        &[(FLOW, "call: orders/look-up", "call: orders/lookup")],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(text.contains("rule: loader/no-such-name"), "{text}");
    assert!(
        text.contains("Change it to one of: `orders/look-up`"),
        "{text}"
    );
    let root = edited(
        "no-such-agent",
        &[(FLOW, "call: orders/look-up", "call: helper")],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(
        !ok && text.contains("'look' calls 'helper', and this workspace has nothing by that name"),
        "{text}"
    );
}
