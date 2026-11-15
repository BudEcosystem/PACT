//! `checks-at-most:` is read beside `answers-with:`, or `checked-by:`, or both.
//!
//! It says how many times an agent is asked for its answer. An answer is held
//! to the rules the author wrote (`checked-by:`) and, since the owner's ruling
//! of 14 November ("if there is a promised shape, it must be honored"), to the
//! shape the agent says it gives (`answers-with:`), from the same count.
//!
//! The line was `needs-also: [checked-by]`, so an agent with a shape and no
//! rules of its own could not say how many tries it gets. Written as
//! `needs-one-of:`, which means EXACTLY one, the most careful agent in the tree
//! — a shape and rules both — was refused for having both
//! (`examples/kernel/fallback`). It is `needs-any-of:`, a new attribute of the
//! schema: at least one of these, or nothing reads the line.
//!
//! Each case runs the real `pact check` over files on disk.

use std::process::Command;

/// A one-agent workspace whose agent writes these lines besides its own.
fn desk(name: &str, lines: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-tries-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    std::fs::write(
        dst.join("workspace.yaml"),
        "name: Probe\ndescription: A probe workspace.\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        format!("name: Desk\ndescription: Answers.\ninstructions: Answer the question.\n{lines}"),
    )
    .unwrap();
    dst
}

fn check(root: &std::path::Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(root);
    (
        out.status.success(),
        format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    )
}

const SHAPE: &str = "answers-with:\n  decision: one of approved, declined\n";
const RULES: &str = "checked-by:\n  - must-contain: [refund]\n";

#[test]
fn beside_a_shape_alone_it_loads() {
    let (ok, said) = check(&desk("shape", &format!("{SHAPE}checks-at-most: 3\n")));
    assert!(ok, "{said}");
}

#[test]
fn beside_rules_alone_it_loads_as_it_always_did() {
    let (ok, said) = check(&desk("rules", &format!("{RULES}checks-at-most: 3\n")));
    assert!(ok, "{said}");
}

#[test]
fn beside_both_it_loads() {
    // Refused while the line was `needs-one-of:`, which means exactly one.
    let (ok, said) = check(&desk("both", &format!("{SHAPE}{RULES}checks-at-most: 1\n")));
    assert!(ok, "{said}");
}

#[test]
fn beside_neither_nothing_reads_it_and_it_is_refused() {
    let (ok, said) = check(&desk("neither", "checks-at-most: 3\n"));
    assert!(!ok, "{said}");
    assert!(said.contains("rule: schema/missing-any-of"), "{said}");
    assert!(
        said.contains(
            "'checks-at-most' is set, and it is read only beside `checked-by` or \
             `answers-with` — none of which is written, so nothing reads it."
        ),
        "{said}"
    );
    assert!(
        said.contains(
            "fix: Add one of them beside it: `checked-by: …`, `answers-with: …`. Or take \
             'checks-at-most' out."
        ),
        "{said}"
    );
}

#[test]
fn a_workflow_stage_still_needs_its_rules() {
    // A stage has no shape of its own (it is the workflow's, or the agent's it
    // calls), so there the line is read beside `checked-by:` and nothing else.
    let dst = desk("stage", "");
    std::fs::create_dir_all(dst.join("workflows")).unwrap();
    std::fs::write(
        dst.join("workflows/ask.yaml"),
        "description: Ask the desk.\naccepts:\n  message: text\nsteps:\n  ask:\n    does: call\n    \
         call: desk\n    bind: { message: input.message }\n    checks-at-most: 2\n",
    )
    .unwrap();
    let (ok, said) = check(&dst);
    assert!(!ok, "{said}");
    assert!(said.contains("'checks-at-most' is set, but 'checked-by' is not"), "{said}");
}
