//! `pact about` says which commit the binary was built from, and whether it
//! was built with uncommitted changes.
//!
//! A runtime pins PACT by commit and then runs whatever `pact` it finds on the
//! machine. The binary could not say what it was, so one built from an edited
//! checkout, or left over from another commit, passed every check a pin makes
//! of the source beside it. Bud Agent Flow's pin guard compared the checkout's
//! `HEAD` and its clean tree and had nothing to compare the binary with.
//!
//! What is held: the three lines are there and a script can read them; the
//! commit is this checkout's `HEAD`; and `uncommitted:` is what `git status`
//! says of the things the binary is built from, as they were when it was
//! built — which is now, since `cargo test` has just built it.

use std::path::PathBuf;
use std::process::Command;

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

fn about() -> Vec<(String, String)> {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("about")
        .output()
        .expect("runs");
    assert!(out.status.success());
    let text = String::from_utf8_lossy(&out.stdout).into_owned();
    text.lines()
        .map(|l| {
            let (key, value) = l.split_once(": ").expect("`<name>: <value>`");
            (key.to_string(), value.to_string())
        })
        .collect()
}

fn git(args: &[&str]) -> Option<String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(repo())
        .args(args)
        .output()
        .ok()?;
    out.status
        .success()
        .then(|| String::from_utf8_lossy(&out.stdout).trim().to_string())
}

#[test]
fn it_says_its_version_its_commit_and_whether_anything_was_uncommitted() {
    let said = about();
    let names: Vec<&str> = said.iter().map(|(k, _)| k.as_str()).collect();
    assert_eq!(names, ["version", "commit", "uncommitted"]);
    assert_eq!(said[0].1, env!("CARGO_PKG_VERSION"));
    let (commit, uncommitted) = (&said[1].1, &said[2].1);
    assert!(
        commit == "unknown" || (commit.len() == 40 && commit.chars().all(|c| c.is_ascii_hexdigit())),
        "{commit}"
    );
    assert!(["no", "yes", "unknown"].contains(&uncommitted.as_str()), "{uncommitted}");
    // No commit, no claim about what was changed since it.
    if commit == "unknown" {
        assert_eq!(uncommitted, "unknown");
    }
}

#[test]
fn the_commit_is_the_one_this_checkout_is_at() {
    // A source archive has no repository around it; there the binary says
    // `unknown` and there is nothing to compare.
    let Some(head) = git(&["rev-parse", "HEAD"]) else {
        return;
    };
    let said = about();
    assert_eq!(said[1].1, head);
    let changed = git(&[
        "status",
        "--porcelain",
        "--",
        "crates",
        "spec",
        "models",
        "Cargo.toml",
        "Cargo.lock",
    ])
    .expect("git status");
    assert_eq!(said[2].1, if changed.is_empty() { "no" } else { "yes" });
}

#[test]
fn it_is_a_command_the_usage_names_and_a_misspelling_is_answered_with_it() {
    let help = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("help")
        .output()
        .expect("runs");
    assert!(String::from_utf8_lossy(&help.stdout).contains("pact about"));
    let typo = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("abuot")
        .output()
        .expect("runs");
    assert!(!typo.status.success());
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&typo.stdout),
        String::from_utf8_lossy(&typo.stderr)
    );
    assert!(said.contains("Did you mean `pact about`?"), "{said}");
}
