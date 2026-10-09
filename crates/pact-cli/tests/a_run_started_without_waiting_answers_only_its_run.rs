//! **A call that does not wait for its workflow answers only the run it started** (02W §2.3).
//!
//! `waits-for-result: no` "starts it and goes on at once. The stage gets back the
//! new run as `.run`, or `.outcome: already-done`". The binding checks read a
//! call's answer as its target's `answers-with:`, whether or not the call waits,
//! so `steps.start.status` loaded beside a call that never has the status: the
//! run reads a field nothing ever hands back. A call that does not wait now
//! answers no field; `.run` and `.outcome` are what every stage has.
//!
//! Fixture: `tests/trees/a-workflow-that-calls-and-answers/`, with a starter
//! flow written beside it.

use std::path::{Path, PathBuf};
use std::process::Command;

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

const STARTER: &str = "description: Starts an order look-up and goes on.
accepts:
  order-number: text
answers-with:
  started: text
starts-at: start
steps:
  start:
    does: call
    call: order-status
    WAITS
    bind:
      order-number: input.order-number
    then:
      answered: reply
  reply:
    does: answer
    bind:
      started: steps.start.READ
";

fn starter(name: &str, waits: &str, read: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-start-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    let flow = STARTER.replace("WAITS", waits).replace("READ", read);
    std::fs::write(dst.join("workflows/starter.yaml"), flow).unwrap();
    dst
}

fn check(root: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

#[test]
fn a_call_that_does_not_wait_answers_its_run() {
    let (ok, said) = check(&starter("run", "waits-for-result: no", "run"));
    assert!(
        ok,
        "`.run` is what a call that does not wait hands back:\n{said}"
    );
}

#[test]
fn a_call_that_does_not_wait_has_no_answer_field_to_read() {
    let (ok, said) = check(&starter("status", "waits-for-result: no", "status"));
    assert!(!ok, "{said}");
    assert!(said.contains("rule: loader/a-binding-to-nothing"), "{said}");
    assert!(said.contains("'start' answers with no 'status'"), "{said}");
    assert!(
        said.contains("steps.start.run"),
        "the fix offers `.run`:\n{said}"
    );
}

#[test]
fn a_call_that_waits_answers_what_its_workflow_answers() {
    let (ok, said) = check(&starter("waits", "waits-for-result: yes", "status"));
    assert!(ok, "{said}");
}
