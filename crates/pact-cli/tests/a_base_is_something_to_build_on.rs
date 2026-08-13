//! A base is something to build on, not something to run — held at the three
//! side doors a runnable-looking base could leak through.
//!
//! `base: yes` promises "it never runs": `pact discover` leaves it out and
//! `pact card` has nothing to publish for it. That promise is only true if
//! every OTHER way of putting an agent to work refuses a base too — a `team:`
//! entry naming one, and a workspace whose every agent is one. Each door is
//! held here end to end, through the real binary, on trees written by this
//! test so the clean fixture trees stay clean.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A fresh workspace under the system temp dir, torn down and rebuilt per test.
fn workspace(name: &str, agents: &[(&str, &str)]) -> std::path::PathBuf {
    let root = std::env::temp_dir().join(format!("pact-base-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(root.join("agents")).unwrap();
    std::fs::write(root.join("workspace.yaml"), format!("name: {name}\n")).unwrap();
    for (agent, body) in agents {
        std::fs::write(root.join(format!("agents/{agent}.yaml")), body).unwrap();
    }
    root
}

const PATTERN: &str = "base: yes\ndescription: The shape of a desk, for real desks to be based on.\n";
const DESK: &str = "based-on: pattern\ninstructions: Answer the question in plain words.\n";
const LONELY: &str =
    "description: Keeps to itself.\ninstructions: Do the work alone.\nteam:\n  pattern: helps\n";

#[test]
fn naming_a_base_under_team_is_refused() {
    let root = workspace(
        "team-door",
        &[("pattern", PATTERN), ("desk", DESK), ("lonely", LONELY)],
    );
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    // `pact check` reports on stdout; both streams are read so a message that
    // moved would fail loudly rather than by absence.
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(out.status.code(), Some(1), "a base on a team is an error:\n{said}");
    assert!(
        said.contains("loader/a-teammate-that-is-only-a-base"),
        "the refusal must be the base one:\n{said}"
    );
    assert!(
        said.contains("based-on: pattern"),
        "the fix names the way through:\n{said}"
    );
}

#[test]
fn a_workspace_of_only_bases_has_nothing_to_run() {
    let root = workspace("all-bases", &[("pattern", PATTERN)]);
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        out.status.success(),
        "half-built is a warning, not an error:\n{said}"
    );
    assert!(
        said.contains("loader/nothing-can-run-this"),
        "an author must not be left believing something here will run:\n{said}"
    );
    assert!(
        said.contains("every agent says `base: yes`"),
        "the sentence says WHY nothing runs — entries exist:\n{said}"
    );

    // And discovery agrees: the workspace is found, and it offers no agents.
    let out = pact().args(["discover", root.to_str().unwrap()]).output().expect("runs");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let inv: serde_json::Value = serde_json::from_slice(&out.stdout).expect("discover emits JSON");
    let ws = inv
        .as_array()
        .expect("an array of workspaces")
        .iter()
        .find(|w| w["workspace"] == "all-bases")
        .expect("the workspace itself is still discovered");
    assert_eq!(
        ws["agents"].as_array().map(Vec::len),
        Some(0),
        "a base is never offered: {ws}"
    );
}

#[test]
fn a_base_is_not_in_the_inventory() {
    let root = workspace("inventory-door", &[("pattern", PATTERN), ("desk", DESK)]);
    let out = pact().args(["discover", root.to_str().unwrap()]).output().expect("runs");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let inv: serde_json::Value = serde_json::from_slice(&out.stdout).expect("discover emits JSON");
    let agents = inv
        .as_array()
        .expect("an array of workspaces")
        .iter()
        .find(|w| w["workspace"] == "inventory-door")
        .expect("the workspace must be discovered")["agents"]
        .as_array()
        .expect("an agents array")
        .clone();
    let ids: Vec<&str> = agents.iter().map(|a| a["id"].as_str().unwrap()).collect();
    assert!(ids.contains(&"pact:desk"), "the agent built ON the base runs: {ids:?}");
    assert!(!ids.contains(&"pact:pattern"), "the base itself is left out: {ids:?}");
    let desk = agents.iter().find(|a| a["id"] == "pact:desk").unwrap();
    assert_eq!(desk["runnable"], true, "the descendant is whole: {desk}");
}
