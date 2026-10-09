//! A `repeat` has a bottom (02W §3 WF-12, §8).
//!
//! "Forever" is a schedule plus memory, never a `repeat`: one with no
//! `at-most:` is refused. WF-13 and WF-14 (`remembers:` and `until:` that read
//! the round) join this file with the binding rules that hold them.
//!
//! Over a copy of `tests/trees/a-workflow-of-every-shape/`.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/a-workflow-of-every-shape"
    ))
}

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

/// A copy of the tree with `edits` applied (file, text to find, its
/// replacement), and any extra files written.
fn edited(name: &str, edits: &[(&str, &str, &str)], extra: &[(&str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-every-shape-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    for (file, text) in extra {
        let p = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    }
    dst
}

fn check(root: &Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

const FLOW: &str = "workflows/invoices.yaml";

#[test]
fn repeat_with_no_bottom_is_refused_and_told_how_to_end() {
    let root = edited(
        "no-bottom",
        &[(
            FLOW,
            "    at-most: 2\n    starts-at: recheck\n",
            "    starts-at: recheck\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/repeat-with-no-bottom"),
        "{text}"
    );
    assert!(
        text.contains("'check-twice' repeats with no bottom"),
        "{text}"
    );
    assert!(
        text.contains("fix: Add `at-most:` — `at-most: 5`. \"Forever\" is a schedule plus memory."),
        "{text}"
    );
    assert!(
        text.contains("|     does: repeat"),
        "the caret is on the stage's `does:`:\n{text}"
    );
}

#[test]
fn a_repeat_with_a_bottom_loads_clean() {
    let (ok, text) = check(&tree());
    assert!(ok, "{text}");
}
