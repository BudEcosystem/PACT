//! `runs-in:` on a `run-code` stage (WP-34, decision B2): code that needs
//! packages and calls nothing runs in the locked room the stage names, which a
//! host binds to a sandbox. What `pact check` holds before anything runs:
//!
//! 1. the room is a `sandbox` that hosts `python`, the language the model writes
//!    (`loader/nothing-here-can-run-that-program`, as for a carried program);
//! 2. a stage that names a room names nothing in `may-use:`, since that room has
//!    no way back to the tools (F7: `loader/code-in-a-room-calls-nothing`);
//! 3. `runs-in:` beside a stage that runs no code is never read
//!    (`loader/a-line-this-stage-never-reads`), and a name that is no resource is
//!    refused by the schema (`names: resources`).
//!
//! Driven against the shipped `an-agent-that-uses-a-workflow` tree, given a
//! locked room for packages and a loop whose one stage runs code.

use std::path::{Path, PathBuf};
use std::process::Command;

const FUEL: &str =
    "    fuel:\n      runs-for-at-most: 30s\n      when-it-runs-out: stop-and-say-so\n";

/// The shipped tree, with `files` written over it.
fn tree(name: &str, files: &[(&str, &str)]) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/trees/an-agent-that-uses-a-workflow");
    let dst = std::env::temp_dir().join(format!("pact-room-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    let base: [(&str, &str); 2] = [
        (
            "resources/algebra-room.yaml",
            "resource-kind: sandbox\ndescription: A room with SymPy.\nengines:\n  - python\n",
        ),
        (
            "agents/desk.yaml",
            "description: Answers questions about an order.\ninstructions: Find the order.\n\
             loop: compute\nuses:\n  - order-status\n",
        ),
    ];
    for (file, text) in base.iter().chain(files) {
        let at = dst.join(file);
        std::fs::create_dir_all(at.parent().unwrap()).unwrap();
        std::fs::write(at, text).unwrap();
    }
    dst
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for entry in std::fs::read_dir(src).unwrap() {
        let entry = entry.unwrap();
        let to = dst.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &to);
        } else {
            std::fs::copy(entry.path(), to).unwrap();
        }
    }
}

/// A loop whose one stage `does` something in room `room`, with `extra` lines beside it.
fn room_loop(does: &str, room: &str, extra: &str) -> String {
    format!(
        "description: Work it out in code.\nstarts-at: work\nsteps:\n  work:\n    does: {does}\n    \
         runs-in: {room}\n{extra}    then:\n      answered: done\n"
    )
}

fn check(tree: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(tree)
        .output()
        .unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

#[test]
fn code_that_runs_in_a_room_for_python_and_calls_nothing_loads() {
    let loop_ = room_loop("run-code", "algebra-room", FUEL);
    let (ok, said) = check(&tree("clean", &[("loops/compute.yaml", &loop_)]));
    assert!(ok, "{said}");
}

#[test]
fn code_that_runs_in_a_room_and_may_call_a_tool_is_refused() {
    let extra = format!("{FUEL}    may-use:\n      - orders\n");
    let loop_ = room_loop("run-code", "algebra-room", &extra);
    let (ok, said) = check(&tree("calls", &[("loops/compute.yaml", &loop_)]));
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/code-in-a-room-calls-nothing"),
        "{said}"
    );
    assert!(said.contains("no way back"), "{said}");
    assert!(said.contains("'orders'"), "{said}");
}

#[test]
fn code_that_runs_in_a_server_is_refused() {
    let loop_ = room_loop("run-code", "order-server", FUEL);
    let (ok, said) = check(&tree("server", &[("loops/compute.yaml", &loop_)]));
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/nothing-here-can-run-that-program"),
        "{said}"
    );
    assert!(said.contains("which is a mcp-server"), "{said}");
}

#[test]
fn code_that_runs_in_a_room_that_cannot_run_python_is_refused() {
    let room = "resource-kind: sandbox\ndescription: A room for wasm.\nengines:\n  - wasm\n";
    let loop_ = room_loop("run-code", "algebra-room", FUEL);
    let (ok, said) = check(&tree(
        "wasm",
        &[
            ("loops/compute.yaml", &loop_),
            ("resources/algebra-room.yaml", room),
        ],
    ));
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/nothing-here-can-run-that-program"),
        "{said}"
    );
    assert!(said.contains("hosts only wasm"), "{said}");
}

#[test]
fn a_room_beside_a_stage_that_runs_no_code_is_never_read() {
    let loop_ = room_loop("think", "algebra-room", "");
    let (ok, said) = check(&tree("think", &[("loops/compute.yaml", &loop_)]));
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-line-this-stage-never-reads"),
        "{said}"
    );
    assert!(said.contains("`runs-in:`"), "{said}");
}

#[test]
fn a_room_that_is_not_in_the_workspace_is_refused() {
    let loop_ = room_loop("run-code", "algebra-rom", FUEL);
    let (ok, said) = check(&tree("typo", &[("loops/compute.yaml", &loop_)]));
    assert!(!ok, "{said}");
    assert!(said.contains("algebra-rom"), "{said}");
}
