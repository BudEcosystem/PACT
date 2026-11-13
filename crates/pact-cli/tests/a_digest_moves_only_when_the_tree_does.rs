//! A tree's digests are a function of the tree, and of nothing else: not of
//! which version of PACT read it.
//!
//! A runtime keys a waiting run to a digest `pact discover` printed (02W §7.2,
//! DUR-2). If a new version of PACT printed another digest for the same
//! files, every run parked under the old version could no longer be resumed,
//! though nobody had edited anything. The neighbouring tests hold a digest to
//! an EDIT (it moves when the run relies on what changed, and stays when it
//! does not). None held it to a VERSION: a change to PACT that moved every
//! tree's digest passed the whole suite. Bud Agent Flow asked whether that
//! was a rule PACT held, with a check, and the honest answer was no.
//!
//! `tests/conformance/digests.json` is the digests of trees in this
//! repository, as checked in. This test reads each tree and compares. A
//! change to PACT that moves one fails here, and has to change that file in
//! the same commit and say in the changelog which trees move and why: it is
//! then a decision somebody made, with the cost named, and not an accident.
//! Editing a listed tree moves its digests too, which is the digest doing its
//! job; the file changes with the tree.
//!
//! A second runtime holds the same file with one `pact discover` per tree.
//!
//! `PACT_BLESS=1` writes the file from what this build prints.

use serde_json::{json, Map, Value};
use std::path::PathBuf;
use std::process::Command;

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

const HELD: &str = "tests/conformance/digests.json";

/// What `pact discover` prints for one tree, down to the digests.
fn digests_of(tree: &str) -> Value {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["discover", repo().join(tree).to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{tree}: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    let inventory: Value = serde_json::from_slice(&out.stdout).expect("JSON");
    let ws = inventory
        .as_array()
        .and_then(|a| a.first())
        .unwrap_or_else(|| panic!("{tree} is not a workspace `pact discover` lists"));
    let mut flows = Map::new();
    for w in ws["workflows"].as_array().into_iter().flatten() {
        flows.insert(
            w["name"].as_str().expect("name").to_string(),
            json!({
                "doc-digest": w["doc-digest"],
                "contract-digest": w["contract-digest"],
            }),
        );
    }
    json!({ "digest": ws["digest"], "workflows": flows })
}

fn held() -> Value {
    let text = std::fs::read_to_string(repo().join(HELD)).expect(HELD);
    serde_json::from_str(&text).expect("JSON")
}

#[test]
fn every_listed_tree_has_the_digests_that_are_checked_in() {
    let mut file = held();
    let trees: Vec<String> = file["trees"]
        .as_object()
        .expect("`trees`")
        .keys()
        .cloned()
        .collect();
    assert!(!trees.is_empty());
    let mut moved = Vec::new();
    for tree in &trees {
        let now = digests_of(tree);
        if file["trees"][tree] != now {
            moved.push(format!(
                "{tree}\n  checked in: {}\n  this build: {}",
                file["trees"][tree], now
            ));
            file["trees"][tree] = now;
        }
    }
    if std::env::var("PACT_BLESS").is_ok() {
        let mut text = serde_json::to_string_pretty(&file).unwrap();
        text.push('\n');
        std::fs::write(repo().join(HELD), text).unwrap();
        return;
    }
    assert!(
        moved.is_empty(),
        "these trees' digests are not the ones checked in ({HELD}).\n\n{}\n\n\
         If a listed tree was edited, that is the digest doing its job: run with \
         PACT_BLESS=1 and commit the file with the tree.\n\
         If no tree was edited, this change to PACT moves the digest of files nobody \
         touched, and every run parked under the last version can no longer be resumed. \
         Either undo that, or bless the file AND say in the changelog which trees move \
         and why.",
        moved.join("\n\n")
    );
}

#[test]
fn every_shared_tree_is_listed() {
    let file = held();
    let listed = file["trees"].as_object().expect("`trees`");
    let mut missing = Vec::new();
    for entry in std::fs::read_dir(repo().join("tests/conformance/trees"))
        .unwrap()
        .flatten()
    {
        let name = format!(
            "tests/conformance/trees/{}",
            entry.file_name().to_string_lossy()
        );
        if entry.path().is_dir() && !listed.contains_key(&name) {
            missing.push(name);
        }
    }
    assert!(
        missing.is_empty(),
        "a tree the shared cases run on is not in {HELD}: {missing:?}"
    );
}

#[test]
fn a_digest_is_the_same_wherever_the_tree_is_read_from() {
    // The same files in another folder: no part of the path is in a digest,
    // so a tree moved or checked out elsewhere keeps its runs.
    let tree = "tests/conformance/trees/triaged-defects";
    let dst = std::env::temp_dir().join(format!("pact-digest-elsewhere-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(&dst).unwrap();
    for e in std::fs::read_dir(repo().join(tree)).unwrap().flatten() {
        std::fs::copy(e.path(), dst.join(e.file_name())).unwrap();
    }
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["discover", dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    let inventory: Value = serde_json::from_slice(&out.stdout).expect("JSON");
    assert_eq!(inventory[0]["digest"], digests_of(tree)["digest"]);
}
