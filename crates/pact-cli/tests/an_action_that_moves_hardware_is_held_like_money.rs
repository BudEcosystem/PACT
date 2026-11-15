//! An action that moves something in the physical world is held the way money is.
//!
//! Physical AI needs the same two guarantees a payment does: one instruction
//! never moves the machine twice, and the effect is a fact a policy can name.
//! `moves-hardware: yes` makes a same-request key necessary, `pact discover`
//! prints `moves-hardware` beside `moves-money`, and `effect: moves-hardware`
//! in a policy's `when-this` names every action that moves hardware.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A one-agent workspace whose `arm/move` action carries the given lines.
fn cell(name: &str, action: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-hardware-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/operator")).unwrap();
    std::fs::create_dir_all(dst.join("tools")).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Cell\ndescription: A robot cell.\n").unwrap();
    std::fs::write(
        dst.join("agents/operator/agent.yaml"),
        "name: Operator\ndescription: Moves parts.\ninstructions: Move the part.\nuses: [arm]\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("tools/arm.yaml"),
        format!(
            "description: The robot arm.\nurl: http://localhost:8080/arm\nmethod: post\nactions:\n  move:\n    description: Moves the arm to a pose.\n    \
             takes:\n      pose: text\n      job: text\n{action}"
        ),
    )
    .unwrap();
    dst
}

fn run(args: &[&str], root: &std::path::Path) -> (bool, String) {
    let out = pact().args(args).arg(root).output().expect("runs");
    (
        out.status.success(),
        format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr)),
    )
}

#[test]
fn moving_hardware_needs_a_same_request_key() {
    let dst = cell("no-key", "    moves-hardware: yes\n");
    let (ok, said) = run(&["check"], &dst);
    assert!(!ok, "{said}");
    assert!(said.contains("same-request-key"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn discover_prints_that_the_agent_moves_hardware() {
    let dst = cell("keyed", "    moves-hardware: yes\n    same-request-key: job\n");
    let (ok, said) = run(&["check"], &dst);
    assert!(ok, "{said}");
    let (ok, listed) = run(&["discover"], &dst);
    assert!(ok, "{listed}");
    assert!(listed.contains("\"moves-hardware\": true"), "{listed}");
    assert!(listed.contains("\"moves-money\": false"), "{listed}");
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn an_arm_that_only_reads_moves_nothing() {
    let dst = cell("reads", "    reads-only: yes\n");
    let (_, listed) = run(&["discover"], &dst);
    assert!(listed.contains("\"moves-hardware\": false"), "{listed}");
    let _ = std::fs::remove_dir_all(&dst);
}
