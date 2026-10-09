//! A human-in-the-loop gate answered by one of this workspace's own agents.
//!
//! The whole of the gate is that a PERSON decides. `asked-of:` is `list of text`
//! with no `names:`, deliberately — a register of people would make the portable
//! folder depend on one host's inventory (`docs/50-NOT-COPIED.md` §4) — and the
//! cost of that freedom was that it accepted anything, including the name of the
//! agent it gates.
//!
//! Measured:
//!
//! ```text
//! asked-of: [desk]     # `desk` is the agent this question gates
//! OK — loaded cleanly (51 settings)
//!
//! pact waits:
//! { "reason": "needs-approval", "agent": "desk", "asked-of": ["desk"],
//!   "escalates-to": ["desk"], "wakes": true }
//! ```
//!
//! A live gate where the thing being checked does the checking, and escalates to
//! itself when nobody answers — so the timer opens it. Both fields are held,
//! because escalation is where a gate ends up when the first person is away.
//!
//! The constraint is NEGATIVE, which is why it costs no register: saying who may
//! not answer needs nothing a portable folder cannot already know.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A workspace whose one question is written as given.
fn asking(name: &str, question: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-selfapprove-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    std::fs::create_dir_all(dst.join("agents/checker")).unwrap();
    std::fs::create_dir_all(dst.join("questions")).unwrap();
    std::fs::write(
        dst.join("workspace.yaml"),
        "name: Probe\ndescription: A probe workspace.\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        "name: Desk\ndescription: Decides refunds.\ninstructions: Decide, then pay.\n\
         limits:\n  steps-at-most: 6\n  when-it-runs-out: ask-a-person\n  asks: is-this-ok\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("agents/checker/agent.yaml"),
        "name: Checker\ndescription: Checks things.\ninstructions: Check it.\n",
    )
    .unwrap();
    std::fs::write(dst.join("questions/is-this-ok.yaml"), question).unwrap();
    dst
}

fn question(asked_of: &str, escalates_to: &str) -> String {
    let mut q = String::from(
        "description: Ask before paying.\nsays: May we issue this refund?\n\
         answer:\n  approved: yes or no\nanswer-within: 4h\n\
         if-nobody-answers: stop-and-say-so\n",
    );
    q.push_str(&format!("asked-of: [{asked_of}]\n"));
    if !escalates_to.is_empty() {
        q.push_str(&format!("escalates-to: [{escalates_to}]\n"));
    }
    q
}

fn check(root: &std::path::Path) -> String {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}

#[test]
fn an_agent_may_not_be_named_as_the_person_who_approves_it() {
    let root = asking("askedof", &question("checker", ""));
    let text = check(&root);
    assert!(
        text.contains("loader/approves-its-own-work"),
        "an agent standing in for a person must be refused:\n{text}"
    );
    assert!(
        text.contains("the thing being checked is what does the checking"),
        "the message has to say what is lost:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_agent_the_question_gates_may_not_approve_itself() {
    // The sharpest case: not another agent, but this one.
    let root = asking("itself", &question("desk", ""));
    let text = check(&root);
    assert!(text.contains("loader/approves-its-own-work"), "{text}");
    assert!(text.contains("'desk'"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn escalating_to_an_agent_is_refused_too() {
    // A gate that escalates to the agent is a gate that opens itself on a
    // timer, which is worse than one that never opens.
    let root = asking("escalates", &question("support-leads", "checker"));
    let text = check(&root);
    assert!(
        text.contains("loader/approves-its-own-work"),
        "escalation is where a gate ends up when the first person is away:\n{text}"
    );
    assert!(
        text.contains("escalates to"),
        "the message names which field:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_audience_that_is_not_an_agent_is_left_alone() {
    let root = asking("people", &question("support-leads", "duty-manager"));
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "naming people is the whole point of the field:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_is_a_line_that_leaves_a_tree_that_checks_clean() {
    // R24. The fix says to name an audience; typing one has to finish the job.
    let root = asking("typed", &question("desk", ""));
    let told = check(&root);
    assert!(
        told.contains("support-leads"),
        "the fix offers something typeable:\n{told}"
    );

    std::fs::write(
        root.join("questions/is-this-ok.yaml"),
        question("support-leads", ""),
    )
    .unwrap();
    let after = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        after.status.success(),
        "following the fix has to finish the job:\n{}",
        String::from_utf8_lossy(&after.stdout)
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_shipped_example_gains_nothing_from_this() {
    let path = format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"));
    let out = pact().args(["check", &path]).output().expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(out.status.success(), "{text}");
    assert!(!text.contains("loader/approves-its-own-work"), "{text}");
}
