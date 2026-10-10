//! **A workflow never starts itself through an agent** (N123, FIX-04).
//!
//! WF-8 refuses workflows that call each other in a circle. The same circle can
//! run through an agent: a stage calls an agent whose `uses:` names a workflow
//! (N2), and the agent's model may start that workflow as a tool, which leads
//! back to the stage. One run could then start itself without end, so the
//! loader refuses it where the circle closes, as it refuses WF-8's: the agent's
//! `uses:` entry, with a fix that says which line to take away.
//!
//! Fixture: `tests/trees/an-agent-that-uses-a-workflow/` (a desk that uses the
//! published `order-status` flow), which loads clean. Every test drives the real
//! binary over a real tree.

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

/// A copy of the tree with `edits` made (file, text to find, its replacement)
/// and `extra` files written.
fn edited(name: &str, edits: &[(&str, &str, &str)], extra: &[(&str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-agent-circle-{name}-{}", std::process::id()));
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
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
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
fn an_agent_that_uses_a_workflow_which_does_not_come_back_loads_clean() {
    let (ok, said) = check(&tree());
    assert!(ok, "{said}");
}

#[test]
fn a_workflow_calling_the_agent_that_uses_it_is_refused_at_the_uses_line() {
    let root = edited(
        "direct",
        &[(FLOW, "    call: orders/look-up\n", "    call: desk\n")],
        &[],
    );
    let (ok, said) = check(&root);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-workflow-its-own-agent-starts"),
        "{said}"
    );
    assert!(
        said.contains(
            "'order-status' calls the agent 'desk', which uses 'order-status' again, so one run \
             can start itself without end."
        ),
        "{said}"
    );
    assert!(
        said.contains("agents/desk.yaml:5:5"),
        "the caret is on the `uses:` entry that closes the circle:\n{said}"
    );
    assert!(
        said.contains("fix: Break the circle: take 'order-status' off the `uses:` of 'desk'"),
        "{said}"
    );
    assert_eq!(
        said.matches("rule: loader/").count(),
        1,
        "one circle, one message:\n{said}"
    );
}

#[test]
fn a_longer_circle_through_another_workflow_and_an_agent_is_refused_once() {
    let hand_on = "description: Hands an order on to the desk.\naccepts:\n  order-number: text\n\
                   answers-with:\n  status: text\nstarts-at: ask\nsteps:\n  ask:\n    does: call\n\
                   \x20   call: desk\n    then:\n      answered: reply\n  reply:\n    does: answer\n\
                   \x20   bind:\n      status: steps.ask.status\n";
    let root = edited(
        "longer",
        &[(FLOW, "    call: orders/look-up\n", "    call: hand-on\n")],
        &[("workflows/hand-on.yaml", hand_on)],
    );
    let (ok, said) = check(&root);
    assert!(!ok, "{said}");
    assert!(
        said.contains(
            "'hand-on' calls the agent 'desk', which uses 'order-status' calls 'hand-on' again"
        ),
        "{said}"
    );
    assert_eq!(
        said.matches("rule: loader/a-workflow-its-own-agent-starts")
            .count(),
        1,
        "one circle, one message:\n{said}"
    );
    assert!(
        !said.contains("loader/workflows-that-call-each-other"),
        "a circle through an agent is not WF-8's:\n{said}"
    );
}
