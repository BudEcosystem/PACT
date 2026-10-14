//! End-to-end: a rule's phrase is searched for in every answer, and every answer
//! contains the empty phrase, so `pact check` refuses an empty or blank entry
//! under `must-contain:`, `must-not-contain:` or `must-say-one-of:`
//! (`pact-loader/src/phrases.rs`), where a suite's rule is written and where a
//! stage's `checked-by:` is. `[]` checks nothing and loads. Driven against the
//! shipped `workflows-48-invoices` tree.

use std::path::{Path, PathBuf};
use std::process::Command;

fn copied(name: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/workflows-48-invoices");
    let dst = std::env::temp_dir().join(format!("pact-phrases-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
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

/// A workflow of the tree with `checked-by: [rule]` on the first stage that calls something,
/// written at that stage's own indent.
fn with_a_check(name: &str, rule: &str) -> PathBuf {
    let tree = copied(name);
    let file = tree.join("workflows/ap-inbox.yaml");
    let text = std::fs::read_to_string(&file).unwrap();
    let line = text
        .lines()
        .find(|l| l.trim_start() == "does: call")
        .expect("a stage that calls something");
    let indent = &line[..line.len() - line.trim_start().len()];
    let checked = format!("{indent}checked-by:\n{indent}  - {rule}\n{line}");
    std::fs::write(&file, text.replacen(line, &checked, 1)).unwrap();
    tree
}

#[test]
fn a_rule_with_no_empty_phrase_loads_and_so_does_one_that_checks_nothing() {
    let (ok, said) = check(&copied("as-shipped"));
    assert!(ok, "{said}");
    let (_, said) = check(&with_a_check("none", "{ must-not-contain: [] }"));
    assert!(!said.contains("loader/an-empty-phrase"), "{said}");
    assert!(!said.contains("doc/yaml-syntax"), "{said}");
}

#[test]
fn an_empty_phrase_a_stage_is_checked_against_is_refused_where_it_is_written() {
    for (name, rule) in [
        ("blank", "{ must-not-contain: [\"\"] }"),
        ("spaces", "{ must-not-contain: [refund, \"  \"] }"),
        ("contain", "{ must-contain: [\"\"] }"),
        ("one-of", "{ must-say-one-of: [approved, \"\"] }"),
    ] {
        let (ok, said) = check(&with_a_check(name, rule));
        assert!(!ok, "{name}: {said}");
        assert!(said.contains("loader/an-empty-phrase"), "{name}: {said}");
        assert!(
            said.contains("To check nothing, write `[]`"),
            "{name}: {said}"
        );
    }
}
