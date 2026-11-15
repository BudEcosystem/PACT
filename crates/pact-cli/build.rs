//! What `pact about` reports: the commit this binary was built from, and
//! whether anything it is built from was changed and not committed.
//!
//! A runtime pins PACT by commit and then runs whatever `pact` binary it
//! finds. Until this, the binary could not say what it was: one built from an
//! edited checkout, or at another commit, passed every check a pin makes. Bud
//! Agent Flow found it when an uncommitted rule of PACT's refused one of its
//! trees through a binary nothing had vouched for.
//!
//! Both are read from `git` when the crate is built and compiled in. Built
//! from a source archive with no repository around it, both say `unknown` —
//! which is the truth, and what a pin check should refuse.

use std::path::Path;
use std::process::Command;

/// What the binary is built from, as paths from the repository's root: the
/// crates, the specification and the catalogue compiled into it, and the
/// manifests that choose its dependencies.
const BUILT_FROM: [&str; 5] = ["crates", "spec", "models", "Cargo.toml", "Cargo.lock"];

fn git(root: &Path, args: &[&str]) -> Option<String> {
    let out = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(args)
        .output()
        .ok()?;
    out.status
        .success()
        .then(|| String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn main() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    // Only a repository whose top is this workspace counts: a source archive
    // unpacked inside somebody else's checkout is not built from THEIR commit.
    let here = git(&root, &["rev-parse", "--show-toplevel"])
        .and_then(|top| Some(Path::new(&top).canonicalize().ok()? == root.canonicalize().ok()?))
        .unwrap_or(false);
    let commit = here
        .then(|| git(&root, &["rev-parse", "HEAD"]))
        .flatten()
        .filter(|c| c.len() == 40 && c.chars().all(|ch| ch.is_ascii_hexdigit()));
    let uncommitted = match &commit {
        None => "unknown",
        Some(_) => {
            let mut args = vec!["status", "--porcelain", "--"];
            args.extend(BUILT_FROM);
            match git(&root, &args) {
                Some(changed) if changed.is_empty() => "no",
                Some(_) => "yes",
                None => "unknown",
            }
        }
    };
    println!(
        "cargo:rustc-env=PACT_BUILT_FROM_COMMIT={}",
        commit.as_deref().unwrap_or("unknown")
    );
    println!("cargo:rustc-env=PACT_BUILT_UNCOMMITTED={uncommitted}");

    // Asked again whenever the answer can have changed: a file the binary is
    // built from, or what is checked out and committed.
    for path in BUILT_FROM {
        println!("cargo:rerun-if-changed={}", root.join(path).display());
    }
    if let Some(dir) = git(&root, &["rev-parse", "--absolute-git-dir"]) {
        for file in ["HEAD", "index", "logs/HEAD"] {
            println!("cargo:rerun-if-changed={}", Path::new(&dir).join(file).display());
        }
    }
}
