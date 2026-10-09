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
    let out = pact()
        .args(["show", root.to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_str(&String::from_utf8_lossy(&out.stdout)).expect("show emits JSON")
}

fn digest_of(root: &std::path::Path) -> String {
    let out = pact()
        .args(["discover", root.to_str().unwrap()])
        .output()
        .expect("runs");
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
    let files = scripts["files"]
        .as_array()
        .expect("a payload lists its files");
    let script = files
        .iter()
        .find(|f| f["$file"].as_str() == Some("check_window.py"))
        .expect("the shipped script is carried");

    let digest = script["digest"]
        .as_str()
        .expect("every carried file says what is in it");
    assert_eq!(
        digest.len(),
        64,
        "a sha256 in hex is 64 characters: {digest}"
    );
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
    assert_eq!(
        swapped.len(),
        text.len(),
        "the fixture must keep the size identical"
    );
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
    assert_ne!(
        pick(&before_file),
        pick(&after_file),
        "the file's fingerprint has to move"
    );
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
        format!(
            "open({:?}, 'w').write('executed')\n",
            canary.to_str().unwrap()
        ),
    )
    .unwrap();

    for verb in ["check", "show", "waits", "discover"] {
        let _ = pact()
            .args([verb, root.to_str().unwrap()])
            .output()
            .expect("runs");
        assert!(
            !canary.exists(),
            "`pact {verb}` ran a body it was only supposed to fingerprint"
        );
    }
    // And it was fingerprinted, so the test above is not passing by the file
    // having been skipped.
    let doc = shown(&root);
    let files = doc["skills"]["refund-policy"]["scripts"]["files"]
        .as_array()
        .unwrap();
    assert!(
        files
            .iter()
            .any(|f| f["$file"].as_str() == Some("hostile.py") && f["digest"].is_string()),
        "the file was carried and fingerprinted: {files:?}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

/// Two runs over the same tree produce the same fingerprints.
#[test]
fn the_fingerprint_is_the_same_on_every_run() {
    let root = copy_of("stable");
    assert_eq!(
        shown(&root),
        shown(&root),
        "reproducible, or a lockfile means nothing"
    );
    assert_eq!(digest_of(&root), digest_of(&root));
    let _ = std::fs::remove_dir_all(&root);
}

/// Leaving a carried file out moves the workspace digest, and says so on the way.
///
/// This is the laundering channel P3 was written to close, and it is the half
/// the plan proposed to close a different way. The plan asked for the ignore
/// FILE to be lifted into the canonical document, on the theory that otherwise
/// `.pactignore` could take a body out of a workspace with nothing moving.
///
/// It cannot, and the reason is that a rule which takes effect takes a FILE out
/// of the payload — and the payload is what the digest is over. So the digest
/// moves because the tree really is different, which is the honest reason for it
/// to move, and a `.pactignore` line that matches nothing changes nothing at all
/// — which is right, and is what lifting the file into the document would have
/// broken: two trees that behave identically would have digested differently.
///
/// Nothing is silent about it either: a note names the file, the rule, and the
/// line to delete to bring it back.
///
/// Written here because it was measured and never pinned. See docs/41 §0.1 for
/// the withdrawal of `an_ignore_rule_is_part_of_the_document`.
#[test]
fn leaving_a_carried_file_out_moves_the_digest_and_is_said_out_loud() {
    let root = copy_of("ignored");
    let before = digest_of(&root);

    std::fs::write(root.join(".pactignore"), "check_window.py\n").unwrap();
    let after = digest_of(&root);
    assert_ne!(
        before, after,
        "a body taken out of the workspace is a different workspace"
    );

    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(said.contains("loader/ignored-on-purpose"), "{said}");
    assert!(said.contains("check_window.py"), "name the file:\n{said}");
    assert!(
        said.contains(".pactignore"),
        "and where the line is:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

/// A rule that matches nothing changes nothing.
///
/// The control the test above needs, and the reason the ignore file is not part
/// of the document: a line about a file that is not there is not a fact about
/// this workspace, and a digest that moved for it would be reporting a change
/// nobody made.
#[test]
fn an_ignore_rule_that_matches_nothing_moves_nothing() {
    let root = copy_of("ignored-nothing");
    let before = digest_of(&root);
    std::fs::write(root.join(".pactignore"), "a-file-that-is-not-here.txt\n").unwrap();
    assert_eq!(
        before,
        digest_of(&root),
        "nothing was left out, so nothing changed"
    );
    let _ = std::fs::remove_dir_all(&root);
}
