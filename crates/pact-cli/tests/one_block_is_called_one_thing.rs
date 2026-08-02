//! A report about one block must call that block one thing.
//!
//! Measured on a copy of `examples/refund-desk`, with `auth: { by-reference:
//! host/zendesk-credential }` in `resources/zendesk-server.yaml` replaced by a
//! key the schema has never heard of. `pact check` printed, about one line:
//!
//! ```text
//! error: A credential-reference must have a 'by-reference'.
//!   fix: Add a line: `by-reference: ...` — the name your platform team publishes …
//!
//!   rule: schema/missing-field
//! error: 'vault-path' is not something a credential reference can have.
//! ```
//!
//! Three separate faults in five lines, all of them things the D13 reader sees
//! and the tool's authors do not:
//!
//! 1. **One group, two names.** `a credential-reference` and `a credential
//!    reference` are the same block. `spec/schema.yaml` carries a `describe:`
//!    line for exactly this, and only the unknown-field sentence read it.
//! 2. **An internal key on screen.** `credential-reference` is a key in the
//!    specification's own YAML. Nothing the author has ever typed or read uses
//!    it, so it reads as a different thing entirely.
//! 3. **A blank line inside the block.** The fix quotes the field's `help:`, and
//!    a folded YAML scalar ends in a newline, so the report broke open between
//!    the line to type and the rule under it.
//!
//! Run against the real binary on a real copy of the worked example, because
//! the thing under test is what the author is SHOWN. A `Diagnostics` value
//! checked in-process would have passed with the blank line still in it — the
//! newline is invisible until something prints it.

use std::process::Command;

fn example() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/refund-desk")
}

/// A private copy of the worked example with `edits` applied, as (file, from, to).
///
/// Named per test so two of these can run at once — `cargo test` is threaded,
/// and a shared directory would make the failures depend on the schedule.
fn copy_with(name: &str, edits: &[(&str, &str, &str)]) -> std::path::PathBuf {
    let dst = std::env::temp_dir()
        .join(format!("pact-one-block-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&example(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(text.contains(from), "fixture drifted: {from:?} is not in {file}");
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    dst
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

fn check(root: &std::path::Path) -> String {
    let o = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    String::from_utf8_lossy(&o.stdout).into_owned()
}

/// The measured tree: one credential block, one key nothing knows.
///
/// A key far enough from `by-reference` that it draws no "did you mean" — which
/// is what makes both sentences appear at once, and is exactly the shape an
/// author lands in when they bring a spelling from another system.
fn a_credential_block_with_a_key_from_somewhere_else(name: &str) -> String {
    let tree = copy_with(
        name,
        &[(
            "resources/zendesk-server.yaml",
            "auth: { by-reference: host/zendesk-credential }",
            "auth: { vault-path: host/zendesk-credential }",
        )],
    );
    check(&tree)
}

#[test]
fn two_sentences_about_one_credential_block_call_it_the_same_thing() {
    let said = a_credential_block_with_a_key_from_somewhere_else("two-sentences");
    assert!(
        said.contains("A credential reference must have a 'by-reference'."),
        "the missing-setting sentence must use the words `describe:` gives it:\n{said}"
    );
    assert!(
        said.contains("'vault-path' is not something a credential reference can have."),
        "the sentence that already did must not have moved:\n{said}"
    );
}

#[test]
fn a_key_out_of_the_specification_is_never_shown_to_the_author() {
    // `credential-reference` is a key in `spec/schema.yaml`. An author who has
    // only ever written `auth:` has no way to connect the two, so a report that
    // names it has stopped being about their file.
    let said = a_credential_block_with_a_key_from_somewhere_else("no-internal-key");
    assert!(
        !said.contains("credential-reference"),
        "the specification's own key is on screen:\n{said}"
    );
}

#[test]
fn no_problem_in_a_report_is_broken_open_by_a_blank_line() {
    // The `fix:` line and the `rule:` line under it are one block the reader
    // takes in at once. A `help:` written as a folded YAML scalar ends in a
    // newline, and quoting it untrimmed split that block in two.
    //
    // Swept over the whole report rather than the one message, because the
    // trailing newline is a property of `help:` and every fix that quotes one
    // was at risk of it.
    let said = a_credential_block_with_a_key_from_somewhere_else("no-blank-line");
    let lines: Vec<&str> = said.lines().collect();
    for (i, line) in lines.iter().enumerate() {
        if !line.trim_start().starts_with("rule: ") {
            continue;
        }
        let before = lines[i.saturating_sub(1)];
        assert!(
            !before.trim().is_empty(),
            "a problem is split open before its rule name:\n{}",
            lines[i.saturating_sub(4)..=i].join("\n")
        );
    }
}
