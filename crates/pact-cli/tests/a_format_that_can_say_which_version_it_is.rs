//! **Register row C1: a format that cannot version cannot evolve.**
//!
//! `apiVersion: pact.dev/v1` existed in exactly one place — a bare string literal
//! inside `discover.rs` — so the only versioned thing in the system was the
//! *discovery index*. A workspace had no way to say which version of the format it
//! was written against, and a runtime had no way to refuse one it could not read.
//! The failure mode is the quiet one: a document read under the wrong version of a
//! format loads, validates, and means something else.
//!
//! Three things had to become true together, and each is asserted below:
//!
//! * the version lives in **one** place (`pact_doc::SPEC_VERSION`), so the index
//!   and the document cannot come to claim different versions of one format;
//! * a workspace **may** state it, and stating the current one changes nothing;
//! * stating one this build cannot read is an **error**, not a warning — refusing
//!   is the entire reason to write the line.
//!
//! Absent stays the ordinary case. A no-code author never writes this, and
//! `pact-version:`'s own help says PACT then reads the tree as the version this
//! build understands — so nothing in the shipped example changes.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
    }
}

/// The shipped example with one line appended to `workspace.yaml`.
fn saying(name: &str, line: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-version-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join("workspace.yaml");
    let mut text = std::fs::read_to_string(&p).unwrap();
    text.push('\n');
    text.push_str(line);
    text.push('\n');
    std::fs::write(&p, text).unwrap();
    dst.to_string_lossy().into_owned()
}

/// `(accepted, what a reader sees)` — stdout, where `check` writes both.
fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("the binary runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned()
            + &String::from_utf8_lossy(&out.stderr),
    )
}

#[test]
fn the_shipped_example_writes_no_version_and_still_loads() {
    // The ordinary case, and the one that must not regress: this field is for a
    // tree crossing an upgrade, not for every author to learn.
    let (ok, said) = check(&example());
    assert!(ok, "{said}");
    assert!(said.contains("loaded cleanly"), "{said}");
}

#[test]
fn a_workspace_may_say_the_version_this_build_reads() {
    let root = saying("current", &format!("pact-version: {}", pact_doc::SPEC_VERSION));
    let (ok, said) = check(&root);
    assert!(ok, "stating the current version must change nothing:\n{said}");
    assert!(said.contains("loaded cleanly"), "{said}");
}

#[test]
fn a_version_this_build_cannot_read_is_refused_and_says_both_versions() {
    let root = saying("future", "pact-version: pact.dev/v9");
    let (ok, said) = check(&root);
    assert!(!ok, "a tree written for a format this build cannot read must be refused");
    assert!(said.contains("pact.dev/v9"), "it must quote what the tree said: {said}");
    assert!(
        said.contains(pact_doc::SPEC_VERSION),
        "and what this build reads, or the author cannot act on it: {said}"
    );
    assert!(said.contains("loader/unreadable-spec-version"), "{said}");
    // An ERROR, not a warning. A warning here would be read past, and the whole
    // point of the field is the loud refusal.
    assert!(said.contains("error"), "{said}");
}

#[test]
fn an_empty_version_line_is_the_same_as_no_line() {
    // A key an author left blank while editing is not a claim about a version, and
    // refusing it would punish saving a file mid-thought.
    let root = saying("blank", "pact-version: \"\"");
    let (ok, said) = check(&root);
    assert!(ok, "{said}");
}

#[test]
fn the_version_lives_in_one_place() {
    // `discover.rs` carried the literal. The index and the document claiming
    // different versions of one format, with nothing comparing them, is the shape
    // of every stale-document defect in this repository.
    let out = pact().args(["discover", &example()]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        text.contains(&format!("\"apiVersion\": \"{}\"", pact_doc::SPEC_VERSION)),
        "the inventory must publish the same constant the loader enforces: {text:.400}"
    );

    let src = std::fs::read_to_string(format!(
        "{}/src/discover.rs",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    assert!(
        !src.contains("\"pact.dev/v"),
        "the version is back as a literal in discover.rs — one string, one place"
    );
}
