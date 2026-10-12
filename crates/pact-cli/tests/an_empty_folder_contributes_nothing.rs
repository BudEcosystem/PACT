//! **An empty folder contributes nothing** (FIX-06).
//!
//! Git cannot carry an empty folder, so a tree checked out from a commit has
//! none, while the working tree it was committed from may: a `questions/` left
//! with no file in it. The loader used to read that folder as `questions: {}`,
//! so the document and its digest differed between the two, and a journal
//! recorded under one refused to replay under the other. A folder with no
//! file at any depth now contributes exactly nothing: the same document, the
//! same digest, the same diagnostics as the tree without it.
//!
//! Fixture: `tests/trees/one-line-gate/`, copied, then given empty folders.
//! Every test drives the real binary over a real tree.

use std::path::{Path, PathBuf};
use std::process::Command;

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

fn copied(name: &str) -> PathBuf {
    let src = PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/one-line-gate"
    ));
    let dst = std::env::temp_dir().join(format!("pact-empty-folder-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    dst
}

fn pact(command: &str, root: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args([command, root.to_str().unwrap()])
        .output()
        .expect("runs");
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.success(), said)
}

/// What a tree loads to: its document, its inventory (digests) and what
/// `pact check` says of it.
fn read(root: &Path) -> [String; 3] {
    ["show", "discover", "check"].map(|command| {
        let (ok, said) = pact(command, root);
        assert!(ok, "pact {command}: {said}");
        said
    })
}

#[test]
fn an_empty_folder_at_any_depth_leaves_the_document_and_its_digest_as_they_were() {
    let root = copied("any-depth");
    let before = read(&root);
    for empty in [
        "questions",
        "evals/nested/deeper",
        "agents/desk/examples",
        "agents/desk/skills/a/b",
        "tools/scripts",
    ] {
        std::fs::create_dir_all(root.join(empty)).unwrap();
    }
    let after = read(&root);
    assert_eq!(before[0], after[0], "the document changed");
    assert_eq!(before[1], after[1], "the digests changed");
    assert_eq!(before[2], after[2], "what `pact check` says changed");
}

#[test]
fn a_folder_with_a_file_in_it_still_counts() {
    let root = copied("with-a-file");
    let before = read(&root);
    std::fs::create_dir_all(root.join("questions/empty")).unwrap();
    std::fs::write(
        root.join("questions/is-it-fine.yaml"),
        "description: Whether it is fine.\nsays: Is it fine?\nanswer:\n  fine: yes or no\n\
         asked-of: [the-requester]\nanswer-within: 2 days\nif-nobody-answers: decline\n",
    )
    .unwrap();
    let after = read(&root);
    assert_ne!(
        before[1], after[1],
        "a folder holding a file is part of the tree"
    );
    assert!(after[0].contains("\"is-it-fine\""), "{}", after[0]);
    assert!(
        !after[0].contains("\"empty\""),
        "its empty folder is not: {}",
        after[0]
    );
}
