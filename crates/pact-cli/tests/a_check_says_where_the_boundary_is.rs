//! `pact check` and `pact discover` say where a workspace draws its egress
//! boundary, every time, and never as a warning.
//!
//! Leaving `allow-egress:` out draws no boundary: every part of the workspace
//! may talk to something outside the box (decision Q17, held by
//! `a_workspace_that_writes_no_boundary_binds_any_model.rs`). That is a choice
//! an author may make. It is also exactly what a forgotten line looks like, and
//! both printed `OK — loaded cleanly`: the tree that chose to be open and the
//! tree that forgot were the same output, and nobody reading either was told
//! which they had. `pact discover`, which a runtime reads to decide whether to
//! take a tree, did not carry the line at all, so an absent line and an empty
//! list — opposite answers — were both simply missing from the index.
//!
//! So it is said: one line after the result of a check, and an `egress` entry
//! on each workspace `pact discover` lists. It is **not a warning**. A team
//! that runs `--deny-warnings` fails its build on any warning, so a warning
//! here would fail every workspace that chose to be open and make each of them
//! write the line: "open unless you say otherwise" turned back into "write it
//! or fail", by the back door. The control for that is in this file.
//!
//! Each case runs the real binary over files on disk.

use serde_json::Value;
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A one-agent workspace on a model served on this machine, with the given
/// `allow-egress:` line (or none).
fn desk(name: &str, egress: Option<&str>) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-says-boundary-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    let line = egress.map(|e| format!("allow-egress: {e}\n")).unwrap_or_default();
    std::fs::write(
        dst.join("workspace.yaml"),
        format!("name: Probe\ndescription: A probe workspace.\n{line}"),
    )
    .unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        "name: Desk\ndescription: Answers.\ninstructions: Answer the question.\n",
    )
    .unwrap();
    dst
}

/// Whether it exited 0, what it printed on stdout, and what on stderr.
fn run(args: &[&str]) -> (bool, String, String) {
    let out = pact().args(args).output().expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

/// The one workspace `pact discover` lists under `root`.
fn inventory(root: &std::path::Path) -> Value {
    let (ok, out, err) = run(&["discover", root.to_str().unwrap()]);
    assert!(ok, "{err}");
    let all: Value = serde_json::from_str(&out).expect("JSON");
    all.as_array()
        .and_then(|a| a.first())
        .cloned()
        .unwrap_or_else(|| panic!("nothing listed: {out}{err}"))
}

#[test]
fn a_workspace_that_writes_no_line_is_told_it_drew_no_boundary() {
    let dst = desk("absent", None);
    let (ok, out, err) = run(&["check", dst.to_str().unwrap()]);
    assert!(ok, "{out}{err}");
    assert!(
        out.contains(
            "Egress: no `allow-egress:` line is written, so this workspace draws no boundary \
             and every part of it may talk to something outside this box. Write \
             `allow-egress: []` to let nothing out."
        ),
        "{out}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn saying_so_is_not_a_warning_and_fails_no_build() {
    // The control. `--deny-warnings` exits 1 on any warning; a workspace that
    // chose to be open has done nothing wrong, and is still told.
    let dst = desk("deny", None);
    let (ok, out, err) = run(&["check", dst.to_str().unwrap(), "--deny-warnings"]);
    assert!(ok, "an open workspace failed `--deny-warnings`:\n{out}{err}");
    assert!(out.contains("loaded cleanly"), "{out}");
    assert!(!out.contains("warning"), "{out}");
    assert!(out.contains("Egress: no `allow-egress:` line is written"), "{out}");
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn a_workspace_that_lets_nothing_out_is_told_so() {
    let dst = desk("closed", Some("[]"));
    let (ok, out, err) = run(&["check", dst.to_str().unwrap()]);
    assert!(ok, "{out}{err}");
    assert!(
        out.contains(
            "Egress: `allow-egress: []`, so nothing here may talk to anything outside this box."
        ),
        "{out}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn a_workspace_that_lists_parts_is_told_which() {
    let one = desk("one", Some("[llm]"));
    let (ok, out, err) = run(&["check", one.to_str().unwrap()]);
    assert!(ok, "{out}{err}");
    assert!(
        out.contains(
            "Egress: `allow-egress: [llm]`, so only that part may talk to something outside \
             this box."
        ),
        "{out}"
    );
    let two = desk("two", Some("[llm, tools]"));
    let (ok, out, err) = run(&["check", two.to_str().unwrap()]);
    assert!(ok, "{out}{err}");
    assert!(
        out.contains(
            "Egress: `allow-egress: [llm, tools]`, so only those parts may talk to something \
             outside this box."
        ),
        "{out}"
    );
    let _ = std::fs::remove_dir_all(&one);
    let _ = std::fs::remove_dir_all(&two);
}

#[test]
fn an_agent_checked_on_its_own_is_told_the_boundary_of_the_workspace_around_it() {
    // The boundary is the workspace's, and it is the one the agent runs inside.
    let dst = desk("inside", Some("[]"));
    let (ok, out, err) = run(&["check", dst.join("agents/desk").to_str().unwrap()]);
    assert!(ok, "{out}{err}");
    assert!(out.contains("checked inside"), "{out}");
    assert!(
        out.contains("Egress: `allow-egress: []`, so nothing here may talk to anything outside"),
        "{out}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn quiet_says_nothing_and_a_tree_with_problems_is_not_described() {
    let dst = desk("quiet", None);
    let (ok, out, _) = run(&["check", dst.to_str().unwrap(), "--quiet"]);
    assert!(ok);
    assert!(!out.contains("Egress:"), "{out}");
    // A tree that did not load has said nothing a runtime will act on.
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        "name: Desk\ndescription: Answers.\ninstructions: Answer.\nnot-a-setting: 1\n",
    )
    .unwrap();
    let (ok, out, err) = run(&["check", dst.to_str().unwrap()]);
    assert!(!ok, "{out}{err}");
    assert!(!out.contains("Egress:"), "{out}");
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn the_inventory_carries_the_boundary_in_a_word_and_the_parts_written() {
    for (name, line, word, allows) in [
        ("inv-open", None, "open", vec![]),
        ("inv-closed", Some("[]"), "closed", vec![]),
        ("inv-listed", Some("[llm, tools]"), "listed", vec!["llm", "tools"]),
    ] {
        let dst = desk(name, line);
        let ws = inventory(&dst);
        assert_eq!(ws["egress"]["boundary"], word, "{name}: {ws}");
        let got: Vec<&str> = ws["egress"]["allows"]
            .as_array()
            .expect("a list")
            .iter()
            .filter_map(Value::as_str)
            .collect();
        assert_eq!(got, allows, "{name}");
        let _ = std::fs::remove_dir_all(&dst);
    }
}
