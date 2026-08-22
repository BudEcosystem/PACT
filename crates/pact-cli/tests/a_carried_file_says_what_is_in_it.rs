//! **P3 — a carried file says what is in it.**
//!
//! A payload directory is carried through verbatim: `skills/<n>/scripts/`,
//! `assets/`, `references/`, `documents/`. The loader records each file's name,
//! its media type and its size — and, until now, nothing about its CONTENTS.
//!
//! That is the gap this closes, and it is a gap the architecture already
//! specified against. EXP-8 (`docs/20-ARCHITECTURE-DRAFT.md` §1.3) says a
//! non-text file becomes `{ $file, contentType, sizeBytes, digest }`. Without
//! the digest, two workspaces holding the same filenames at the same sizes and
//! completely different bytes have the same `workspace-digest` — so signing a
//! tree says nothing about the scripts inside it, a lockfile cannot pin one, and
//! a reviewer who has read a body has no way to say later that it is still the
//! body they read.
//!
//! It matters more the moment a body is something a runtime will EXECUTE
//! (`docs/41` P6), which is why it lands first and on its own.
//!
//! The bytes themselves still never enter the document — that is what keeps
//! `pact check` a reading of the tree rather than a loading of it. What is
//! recorded is a fingerprint of them.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

fn copy_of(name: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-digest-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
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

fn shown(root: &std::path::Path) -> serde_json::Value {
    let out = pact().args(["show", root.to_str().unwrap()]).output().expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_str(&String::from_utf8_lossy(&out.stdout)).expect("show emits JSON")
}

fn digest_of(root: &std::path::Path) -> String {
    let out = pact().args(["discover", root.to_str().unwrap()]).output().expect("runs");
    let found: serde_json::Value =
        serde_json::from_str(&String::from_utf8_lossy(&out.stdout)).expect("discover emits JSON");
    found[0]["digest"].as_str().expect("a digest").to_owned()
}

/// The carried script carries its fingerprint.
///
/// Mutation: drop `digest` from `FileRef` and this names the field that is gone.
#[test]
fn a_carried_file_carries_its_digest() {
    let root = copy_of("has-one");
    let doc = shown(&root);
    let scripts = &doc["skills"]["refund-policy"]["scripts"];
    let files = scripts["files"].as_array().expect("a payload lists its files");
    let script = files
        .iter()
        .find(|f| f["$file"].as_str() == Some("check_window.py"))
        .expect("the shipped script is carried");

    let digest = script["digest"].as_str().expect("every carried file says what is in it");
    assert_eq!(digest.len(), 64, "a sha256 in hex is 64 characters: {digest}");
    assert!(digest.chars().all(|c| c.is_ascii_hexdigit()), "{digest}");
    // The other three stay exactly as they were — this is an addition.
    assert!(script["contentType"].is_string(), "{script}");
    assert!(script["sizeBytes"].is_number(), "{script}");
    let _ = std::fs::remove_dir_all(&root);
}

/// Changing what is in a carried file changes the fingerprint, and the digest of
/// the whole workspace with it.
///
/// This is the property the feature exists for: before it, a body could be
/// swapped for another body of the same length and nothing anywhere moved.
#[test]
fn changing_the_bytes_changes_the_digest_even_at_the_same_size() {
    let a = copy_of("before");
    let before_file = shown(&a);
    let before_workspace = digest_of(&a);

    // Same length, different bytes — the case a size alone cannot see.
    let p = a.join("skills/refund-policy/scripts/check_window.py");
    let text = std::fs::read_to_string(&p).unwrap();
    let swapped = text.replacen("inside", "INSIDE", 1);
    assert_eq!(swapped.len(), text.len(), "the fixture must keep the size identical");
    assert_ne!(swapped, text, "and must actually change the bytes");
    std::fs::write(&p, &swapped).unwrap();

    let after_file = shown(&a);
    let after_workspace = digest_of(&a);

    let pick = |doc: &serde_json::Value| -> String {
        doc["skills"]["refund-policy"]["scripts"]["files"]
            .as_array()
            .unwrap()
            .iter()
            .find(|f| f["$file"].as_str() == Some("check_window.py"))
            .unwrap()["digest"]
            .as_str()
            .unwrap()
            .to_owned()
    };
    assert_ne!(pick(&before_file), pick(&after_file), "the file's fingerprint has to move");
    assert_ne!(
        before_workspace, after_workspace,
        "and so does the workspace's, or signing a tree says nothing about the bodies in it"
    );
    let _ = std::fs::remove_dir_all(&a);
}

/// Reading the bytes to fingerprint them is still not running them.
///
/// The purity rule is the one every later phase leans on, and this phase is the
/// first that opens a payload file at all. It opens it to hash it and for
/// nothing else.
#[test]
fn fingerprinting_a_body_is_not_executing_it() {
    let root = copy_of("purity");
    let canary = root.join("canary-was-executed");
    let scripts = root.join("skills/refund-policy/scripts");
    std::fs::write(
        scripts.join("hostile.py"),
        format!("open({:?}, 'w').write('executed')\n", canary.to_str().unwrap()),
    )
    .unwrap();

    for verb in ["check", "show", "waits", "discover"] {
        let _ = pact().args([verb, root.to_str().unwrap()]).output().expect("runs");
        assert!(!canary.exists(), "`pact {verb}` ran a body it was only supposed to fingerprint");
    }
    // And it was fingerprinted, so the test above is not passing by the file
    // having been skipped.
    let doc = shown(&root);
    let files = doc["skills"]["refund-policy"]["scripts"]["files"].as_array().unwrap();
    assert!(
        files.iter().any(|f| f["$file"].as_str() == Some("hostile.py") && f["digest"].is_string()),
        "the file was carried and fingerprinted: {files:?}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

/// Two runs over the same tree produce the same fingerprints.
#[test]
fn the_fingerprint_is_the_same_on_every_run() {
    let root = copy_of("stable");
    assert_eq!(shown(&root), shown(&root), "reproducible, or a lockfile means nothing");
    assert_eq!(digest_of(&root), digest_of(&root));
    let _ = std::fs::remove_dir_all(&root);
}
