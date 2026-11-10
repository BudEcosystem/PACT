//! Law 1 of `docs/97-PRIMITIVES.md`, as `docs/98` WP-2 makes it real: what a
//! part does to the world is computed from everything it can reach, and never
//! declared.
//!
//! - `pact discover` prints each agent's and each workflow's effect — `nothing`,
//!   `reads`, `writes` or `cannot-be-undone` — and whether it moves money.
//! - A stage's own `undone-by:` makes what it calls undoable there.
//! - An action marked `reads-only: yes` that its server publishes as
//!   destructive is warned about (`loader/declared-lighter-than-the-server-says`).

use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::Value;

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

fn copied(tree: &str, name: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join(tree);
    let dst = std::env::temp_dir().join(format!("pact-effects-{name}-{}", std::process::id()));
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

fn pact(args: &[&str], tree: &Path) -> (bool, String, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .arg(tree)
        .output()
        .unwrap();
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).to_string(),
        String::from_utf8_lossy(&out.stderr).to_string(),
    )
}

fn inventory(tree: &Path) -> Value {
    let (ok, out, err) = pact(&["discover"], tree);
    assert!(ok, "{out}{err}");
    let v: Value = serde_json::from_str(&out).unwrap();
    v.as_array().and_then(|a| a.first()).cloned().unwrap_or(v)
}

fn named<'a>(list: &'a Value, key: &str, name: &str) -> &'a Value {
    list.as_array()
        .unwrap()
        .iter()
        .find(|e| e[key].as_str() == Some(name))
        .unwrap_or_else(|| panic!("{name} not in {list}"))
}

#[test]
fn every_agent_carries_the_worst_of_what_it_reaches() {
    let tree = copied("examples/refund-desk", "agents");
    let inv = inventory(&tree);
    let desk = named(&inv["agents"], "id", "pact:refund-desk");
    assert_eq!(desk["effect"], "cannot-be-undone", "{desk}");
    assert_eq!(desk["moves-money"], true, "{desk}");
    // It reads one written policy and calls nothing.
    let policy = named(&inv["agents"], "id", "pact:policy-checker");
    assert_eq!(policy["effect"], "nothing", "{policy}");
    assert_eq!(policy["moves-money"], false, "{policy}");
}

#[test]
fn a_workflow_is_as_heavy_as_its_heaviest_stage_and_its_undo_counts() {
    let tree = copied("tests/trees/a-workflow-of-every-shape", "workflows");
    let inv = inventory(&tree);
    // `pay` calls `ledger/post`, which says nothing about undoing itself, and
    // the stage writes `undone-by: ledger/unpost` beside the call.
    assert_eq!(
        named(&inv["workflows"], "name", "invoices")["effect"],
        "writes"
    );
    assert_eq!(
        named(&inv["workflows"], "name", "recheck")["effect"],
        "reads"
    );

    let tree = copied("tests/trees/a-workflow-of-every-shape", "no-undo");
    edit(
        &tree,
        "workflows/invoices.yaml",
        "        undone-by: ledger/unpost\n",
        "",
    );
    let inv = inventory(&tree);
    assert_eq!(
        named(&inv["workflows"], "name", "invoices")["effect"],
        "cannot-be-undone"
    );
}

#[test]
fn an_action_lighter_than_its_server_says_is_warned() {
    let tree = copied("tests/trees/a-desk-that-listens-reads-and-chooses", "hint");
    edit(
        &tree,
        "tools/gmail.yaml",
        "    calls: send_email\n",
        "    calls: send_email\n    reads-only: yes\n",
    );
    let resource = tree.join("resources/gmail-server.yaml");
    let mut text = std::fs::read_to_string(&resource).unwrap();
    text.push_str("      hints:\n        destructiveHint: true\n");
    std::fs::write(&resource, text).unwrap();
    let (_, out, err) = pact(&["check"], &tree);
    let said = out + &err;
    assert!(
        said.contains("rule: loader/declared-lighter-than-the-server-says"),
        "{said}"
    );
    assert!(said.contains("destructiveHint: true"), "{said}");
}

#[test]
fn a_hint_that_agrees_says_nothing() {
    let tree = copied("tests/trees/a-desk-that-listens-reads-and-chooses", "agree");
    edit(
        &tree,
        "tools/gmail.yaml",
        "    calls: search_threads\n",
        "    calls: search_threads\n    reads-only: yes\n",
    );
    let (_, out, err) = pact(&["check"], &tree);
    assert!(
        !(out + &err).contains("declared-lighter-than-the-server-says"),
        "search_threads publishes readOnlyHint: true"
    );
}
