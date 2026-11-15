//! A workspace that writes no `allow-egress:` draws no boundary, for models too.
//!
//! Two of the three checks that read `allow-egress:` already answered an absent
//! line with "this author has not decided" (`a_workspace_that_drew_no_boundary_is_not_given_one`
//! in `one_file_says_what_reaches_outside.rs`), while the model-binding check
//! answered it with "nothing may leave": a tree with no line, pinning a hosted
//! model, was refused with `loader/leaves-the-box` quoting `allow-egress: []`, a
//! line its author never wrote. Constraining is a declaration: the air-gapped
//! desk writes `allow-egress: []`, and that is held exactly as before.
//!
//! Each case runs the real `pact check` over files on disk, with a CONTROL: the
//! same tree under `allow-egress: []` must be refused, so the pass is not a
//! tree that fails to bind a model at all.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A one-agent workspace pinning a model served only off this machine, with the
/// given `allow-egress:` line (or none).
fn desk(name: &str, egress: Option<&str>) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-no-boundary-{name}-{}", std::process::id()));
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
        "name: Desk\ndescription: Answers.\ninstructions: Answer the question.\nmodel: claude-opus-5\n",
    )
    .unwrap();
    dst
}

fn check(root: &std::path::Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.success(), said)
}

#[test]
fn a_hosted_model_binds_where_no_boundary_is_written() {
    let dst = desk("absent", None);
    let (ok, said) = check(&dst);
    assert!(ok, "{said}");
    assert!(!said.contains("loader/leaves-the-box"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn the_same_model_is_refused_where_nothing_may_leave() {
    let dst = desk("empty", Some("[]"));
    let (ok, said) = check(&dst);
    assert!(!ok, "{said}");
    assert!(said.contains("loader/leaves-the-box"), "{said}");
    assert!(said.contains("allow-egress: []"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn a_list_that_names_the_role_admits_it() {
    let dst = desk("llm", Some("[llm]"));
    let (ok, said) = check(&dst);
    assert!(ok, "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}
