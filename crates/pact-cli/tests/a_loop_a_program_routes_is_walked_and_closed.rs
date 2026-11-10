//! Laws 4 and 6 of `docs/97-PRIMITIVES.md`, as `docs/98` WP-1 makes them rules.
//!
//! - A loop whose stage lets a carried program pick the next stage is WALKED:
//!   `may-go-to:` is the list of edges, and the program's name is not a stage.
//!   Before this, the walk gave up on any such loop, and `loader/stage-nothing-
//!   reaches` and `loader/loop-that-never-finishes` were silently off for it.
//! - The program can only pick from that list: its answer is a `one of` whose
//!   choices `may-go-to:` names (`loader/a-program-may-pick-a-stage-not-listed`).
//! - A stage's `may-use:` only narrows what the agent running it has
//!   (`loader/a-stage-may-use-what-the-agent-cannot`).

use std::path::{Path, PathBuf};
use std::process::Command;

fn copy(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}

fn copied(name: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/trees/a-desk-whose-program-decides");
    let dst = std::env::temp_dir().join(format!("pact-closed-world-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    dst
}

fn edit(tree: &Path, file: &str, from: &str, to: &str) {
    let path = tree.join(file);
    let text = std::fs::read_to_string(&path).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {file} has no {from:?}"
    );
    std::fs::write(&path, text.replacen(from, to, 1)).unwrap();
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

const LOOP: &str = "loops/works-it-out.yaml";
const PROGRAM: &str = "programs/pick-next/program.yaml";
const AGENT: &str = "agents/desk/agent.yaml";

#[test]
fn the_fixture_as_shipped_loads_clean() {
    let (ok, said) = check(&copied("as-shipped"));
    assert!(ok, "{said}");
}

#[test]
fn a_stage_only_the_program_could_reach_is_found_once_it_leaves_the_list() {
    // `think-again` is reached only through `may-go-to:`. Take it off the list
    // and nothing reaches it — which the walk can now say, because it no longer
    // gives up on a loop with a deciding program in it.
    let tree = copied("unreached");
    edit(&tree, LOOP, "        - think-again\n", "");
    edit(&tree, PROGRAM, "one of reply, think-again", "one of reply");
    let (ok, said) = check(&tree);
    assert!(!ok, "{said}");
    assert!(said.contains("loader/stage-nothing-reaches"), "{said}");
}

#[test]
fn a_program_that_answers_free_text_can_pick_anything_and_is_refused() {
    let tree = copied("free-text");
    edit(
        &tree,
        PROGRAM,
        "next: one of reply, think-again",
        "next: text",
    );
    let (ok, said) = check(&tree);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-program-may-pick-a-stage-not-listed"),
        "{said}"
    );
    assert!(
        said.contains("next: one of reply, think-again"),
        "the fix names the line: {said}"
    );
}

#[test]
fn a_program_whose_choice_is_off_the_list_is_refused_naming_it() {
    let tree = copied("off-list");
    edit(
        &tree,
        PROGRAM,
        "one of reply, think-again",
        "one of reply, think-again, gather",
    );
    let (ok, said) = check(&tree);
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-program-may-pick-a-stage-not-listed"),
        "{said}"
    );
    assert!(said.contains("'gather'"), "{said}");
}

#[test]
fn done_is_always_a_place_a_program_may_send_the_run() {
    let tree = copied("done");
    edit(
        &tree,
        PROGRAM,
        "one of reply, think-again",
        "one of reply, think-again, done",
    );
    let (ok, said) = check(&tree);
    assert!(ok, "{said}");
}

#[test]
fn a_stage_may_not_use_what_its_agent_was_never_given() {
    let tree = copied("wider");
    edit(
        &tree,
        AGENT,
        "uses:\n  - refund-window\n",
        "uses:\n  - check-window\n",
    );
    edit(
        &tree,
        LOOP,
        "    at-most: 2\n",
        "    at-most: 2\n    may-use:\n      - refund-window\n",
    );
    let (ok, said) = check(&tree);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-stage-may-use-what-the-agent-cannot"),
        "{said}"
    );
    assert!(said.contains("'refund-window'"), "{said}");
}

#[test]
fn a_stage_that_narrows_to_something_the_agent_has_loads() {
    let tree = copied("narrower");
    edit(
        &tree,
        LOOP,
        "    at-most: 2\n",
        "    at-most: 2\n    may-use:\n      - refund-window\n",
    );
    let (ok, said) = check(&tree);
    assert!(ok, "{said}");
}
