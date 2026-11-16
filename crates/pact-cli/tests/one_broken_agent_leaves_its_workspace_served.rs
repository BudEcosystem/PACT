//! With `--leave-out-broken-agents`, an error in one agent's own folder leaves
//! that agent out of what `pact show` and `pact discover` serve, not the whole
//! workspace; without it, nothing changes.
//!
//! Editing an agent online used to withdraw every agent of its workspace the
//! moment the edit was invalid: a runtime serving the tree read `discover`'s
//! `skipping .: 1 problem(s)` and `show`'s exit 1, and stopped serving agents
//! nobody had touched. `pact check` still refuses the tree, so an author is
//! told; a runtime that asks keeps serving what is still valid, and hears which
//! agents were left out.

use std::path::{Path, PathBuf};
use std::process::Command;

const LEAVE_OUT: &str = "--leave-out-broken-agents";

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A workspace with a valid `clerk` and an `auditor` whose limit is below the floor.
fn tree(name: &str, clerk_team: bool) -> PathBuf {
    let root = std::env::temp_dir().join(format!("pact-one-broken-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let write = |path: &str, text: &str| {
        let p = root.join(path);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    };
    write("workspace.yaml", "name: desk\ndescription: A desk of two agents.\n");
    let team = if clerk_team { "team:\n  auditor: reads the clerk's decisions\n" } else { "" };
    write(
        "agents/clerk/agent.yaml",
        &format!("description: Decides tickets.\ninstructions: Decide each ticket.\n{team}"),
    );
    write(
        "agents/auditor/agent.yaml",
        "description: Audits decisions.\ninstructions: Read the decisions.\nlimits:\n  steps-at-most: -1\n  when-it-runs-out: answer-with-what-it-has\n",
    );
    root
}

fn run(args: &[&str], root: &Path) -> (i32, String, String) {
    let out = pact().args(args).arg(root).output().unwrap();
    (
        out.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

#[test]
fn the_broken_agent_is_left_out_and_its_sibling_is_served() {
    let root = tree("sibling", false);
    let (code, stdout, stderr) = run(&["discover", LEAVE_OUT], &root);
    assert_eq!(code, 0, "{stderr}");
    let inventory: serde_json::Value = serde_json::from_str(&stdout).unwrap();
    let ids: Vec<&str> = inventory[0]["agents"].as_array().unwrap().iter().map(|a| a["id"].as_str().unwrap()).collect();
    assert_eq!(ids, ["pact:clerk"], "{stdout}");
    assert_eq!(inventory[0]["left-out"], serde_json::json!([{ "id": "pact:auditor", "problems": 1 }]));
    assert!(stderr.contains("Agent 'auditor' is left out until its 1 problem(s) are fixed"), "{stderr}");
    assert!(stderr.contains("loader/agent-left-out") && stderr.contains("schema/below-the-floor"), "{stderr}");

    let (code, stdout, stderr) = run(&["show", LEAVE_OUT], &root);
    assert_eq!(code, 0, "{stderr}");
    let document: serde_json::Value = serde_json::from_str(&stdout).unwrap();
    let agents: Vec<&String> = document["agents"].as_object().unwrap().keys().collect();
    assert_eq!(agents, ["clerk"], "{stdout}");

    // Without the flag the workspace is refused whole, as a session's door and a
    // sealed plan need it to be.
    let (code, stdout, stderr) = run(&["discover"], &root);
    assert_eq!((code, stdout.trim()), (0, "[]"), "{stderr}");
    assert!(stderr.contains("skipping"), "{stderr}");
    let (code, _, _) = run(&["show"], &root);
    assert_eq!(code, 1);

    // The author is still refused, and checking the clean agent says what a runtime does.
    let (code, stdout, _) = run(&["check"], &root.join("agents/clerk"));
    assert_eq!(code, 0, "{stdout}");
    assert!(stdout.contains("loader/other-agents-left-out"), "{stdout}");
    let (code, stdout, _) = run(&["check"], &root);
    assert_eq!(code, 1, "{stdout}");
    assert!(stdout.contains("schema/below-the-floor"), "{stdout}");
}

#[test]
fn a_teammate_that_names_the_broken_agent_keeps_the_whole_workspace_refused() {
    let root = tree("teammate", true);
    let (code, stdout, stderr) = run(&["discover", LEAVE_OUT], &root);
    assert_eq!(code, 0, "{stderr}");
    assert_eq!(stdout.trim(), "[]", "{stdout}");
    assert!(stderr.contains("problem(s)"), "{stderr}");
    let (code, _, _) = run(&["show", LEAVE_OUT], &root);
    assert_eq!(code, 1);
}
