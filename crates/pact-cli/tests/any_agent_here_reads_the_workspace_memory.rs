//! **The workspace's memory is read by any agent here, and written by two actions only.**
//!
//! `workspace.remembers:` says it is "named memory any agent or workflow here may
//! read as `remembers.<name>`, written only by the stock actions `bud/remember`
//! and `bud/forget`". Before this, the checker read an agent's `remembers.` as the
//! agent's own entries alone: a hole `{{remembers.house-style}}` naming the
//! workspace's memory was refused (`loader/no-such-remembered-fact`), and a
//! tool's `bind: remembers.house-style` was refused whenever any agent remembered
//! anything of its own. And a `remember-as:` naming only the workspace's memory
//! loaded, though a tool's answer is not one of the two actions that write it.
//!
//! Fixture: `tests/trees/an-agent-that-reads-the-workspace-memory/`.

use std::process::Command;

fn tree() -> String {
    format!(
        "{}/../../tests/trees/an-agent-that-reads-the-workspace-memory",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn run(args: &[&str]) -> (Option<i32>, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .output()
        .expect("runs");
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.code(), said)
}

fn edited(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-wsmem-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&tree()), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replace(from, to)).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy_dir(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}

/// A hole in an agent's words and a tool's `bind:` both read the workspace's
/// memory, beside the agent's own (the positive control for the refusals below).
#[test]
fn an_agent_reads_the_workspace_memory_in_its_words_and_its_bindings() {
    let (code, said) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(code, Some(0), "{said}");
}

/// A name neither the workspace nor the agent remembers is still refused, and the
/// fix offers the workspace's memory too.
#[test]
fn a_hole_naming_memory_nobody_keeps_is_refused_with_the_workspace_memory_offered() {
    let dst = edited(
        "hole",
        "agents/desk.yaml",
        "{{remembers.house-style}}",
        "{{remembers.house-stile}}",
    );
    let (code, said) = run(&["check", &dst]);
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/no-such-remembered-fact"), "{said}");
    assert!(said.contains("{{remembers.house-style}}"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A binding from memory nobody keeps is refused, naming the workspace's memory.
#[test]
fn a_binding_from_memory_nobody_keeps_is_refused_with_the_workspace_memory_offered() {
    let dst = edited(
        "bind",
        "tools/orders.yaml",
        "remembers.house-style",
        "remembers.house-stile",
    );
    let (code, said) = run(&["check", &dst]);
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/no-such-remembered-fact"), "{said}");
    assert!(said.contains("house-style"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A tool's answer may not be kept in the workspace's memory: only `bud/remember`
/// and `bud/forget` write it.
#[test]
fn a_tools_answer_is_never_kept_in_the_workspace_memory() {
    let dst = edited(
        "remember-as",
        "tools/orders.yaml",
        "remember-as: last-order-seen",
        "remember-as: house-style",
    );
    let (code, said) = run(&["check", &dst]);
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-tool-may-not-write-there"), "{said}");
    assert!(said.contains("bud/remember"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}
