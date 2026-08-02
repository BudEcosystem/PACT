//! `--deny-warnings`, and the census that says it is safe to have (P2).
//!
//! A warning here is a heuristic cross-document judgement, and what makes those
//! safe to ADD is that a false positive costs a line of noise rather than a
//! broken build. This flag gives that up on purpose, per run, where somebody has
//! decided the trade.
//!
//! It is sequenced a phase AFTER the warnings were made fixable, and that order
//! is load-bearing: `loader/never-offered` used to offer a fix that was itself
//! refused when typed — *"Add `skills:`"*, and `skills` is not something an
//! agent can have — so this flag would have turned an unfixable warning into a
//! wall. A flag that freezes the warning surface may not land in the same phase
//! as a redesign of it.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

/// Every workspace this repository ships, found rather than listed.
fn shipped_trees() -> Vec<std::path::PathBuf> {
    let mut out = vec![repo().join("examples/refund-desk")];
    let patterns = repo().join("examples/patterns");
    let mut dirs: Vec<std::path::PathBuf> = std::fs::read_dir(&patterns)
        .expect("examples/patterns exists")
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_dir())
        .collect();
    dirs.sort();
    out.extend(dirs);
    out
}

#[test]
fn every_shipped_tree_is_clean_under_deny_warnings() {
    // The census, run as a test rather than quoted from a note. Nine trees,
    // zero warnings — which is what makes the flag a no-op today and therefore
    // safe to ship: it changes nothing that is already right.
    let trees = shipped_trees();
    assert!(trees.len() >= 9, "only {} shipped trees found", trees.len());
    let mut dirty = Vec::new();
    for tree in &trees {
        let out = pact()
            .args(["check", tree.to_str().unwrap(), "--deny-warnings"])
            .output()
            .expect("runs");
        if !out.status.success() {
            dirty.push(format!(
                "{}:\n{}",
                tree.display(),
                String::from_utf8_lossy(&out.stdout)
            ));
        }
    }
    assert!(
        dirty.is_empty(),
        "{} shipped tree(s) do not survive their own flag:\n\n{}",
        dirty.len(),
        dirty.join("\n\n")
    );
}

#[test]
fn a_warning_fails_the_run_only_when_the_flag_is_given() {
    // The flag has to DO something, or the test above is asserting that a
    // no-op is a no-op.
    let dst = std::env::temp_dir().join(format!("pact-deny-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&repo().join("examples/refund-desk"), &dst);

    // Delete `spends-money:` — a warning with a fix, which is the state this
    // flag exists to stop reaching a pipeline unnoticed.
    let p = dst.join("tools/payments.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    let kept: Vec<&str> =
        text.lines().filter(|l| !l.trim_start().starts_with("spends-money:")).collect();
    assert!(kept.len() < text.lines().count(), "the fixture drifted");
    std::fs::write(&p, kept.join("\n") + "\n").unwrap();

    let lax = pact().args(["check", dst.to_str().unwrap()]).output().expect("runs");
    assert!(lax.status.success(), "a warning is not a failure by default");

    let strict = pact()
        .args(["check", dst.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    assert!(!strict.status.success(), "the flag has to fail the run");
    assert!(
        String::from_utf8_lossy(&strict.stdout).contains("warning"),
        "and it still has to say what the warning was"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn a_misspelt_flag_is_still_refused_by_name() {
    // The flag joins `OPTIONS`, so the suggester covers it: a new flag that
    // silently did nothing when misspelt would be the defect this whole CLI
    // refuses everywhere else.
    let out = pact()
        .args(["check", repo().join("examples/refund-desk").to_str().unwrap(), "--deny-warning"])
        .output()
        .expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!out.status.success(), "{text}");
    assert!(text.contains("--deny-warning"), "{text}");
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
