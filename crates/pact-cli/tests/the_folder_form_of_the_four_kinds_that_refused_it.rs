//! A tool, a policy, a resource and a redaction may be written as a folder,
//! the same way an agent, a port and a question already could.
//!
//! # What was measured
//!
//! In a copy of `examples/refund-desk`, `tools/weather.yaml` deleted and
//! `tools/weather/tool.yaml` written in its place, holding the same
//! `description:`, `url:` and `method:`. `pact check` answered with three
//! problems, of which two were unactionable:
//!
//! ```text
//! error: A tool must have a 'description'.
//!   --> …/tools/weather
//!   fix: Create `…/tools/weather/weather.yaml` and put one line in it: …
//!
//! error: 'tool' is not something a tool can have.
//!   --> …/tools/weather/tool.yaml:1:1
//!   fix: Remove it, or use one of: description, connect, url, method, says, actions.
//! ```
//!
//! The arrow on the first points at a DIRECTORY, with no line to underline,
//! because the three settings had landed one level down inside a field called
//! `tool`. The second asks the author to *remove* `tool` — which is the
//! FILENAME, the one thing in that message they cannot remove. Following either
//! fix makes the tree worse. `policies/approvals/policy.yaml` and
//! `resources/payments-server/resource.yaml` failed the same way, the second
//! offering *"Did you mean 'resource-kind'?"*.
//!
//! The cause was one list: `Policy::default().kind_stems` in
//! `crates/pact-loader/src/policy.rs`. `agent`, `port`, `question`, `watch`,
//! `loop` and the rest are in it; `tool`, `policy` and `resource` are older than
//! the list and were never added, so the folder spelling the Expansion Rule
//! accepts everywhere else was the one spelling it refused here.
//!
//! # Why these tests build trees and run the binary
//!
//! Asserting `Policy::default().kind_stems.contains("tool")` would prove the
//! list holds a string. It would say nothing about whether an author who makes
//! that folder gets a clean load — which is the whole claim, and which depends
//! on the loader, the schema and every check downstream of both agreeing. So
//! every fixture here is the worked example with one file moved, and every
//! assertion is on what `pact` printed.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> PathBuf {
    PathBuf::from(format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR")))
}

/// A private copy of the worked example. Tests in one binary share a process
/// and cargo runs them at the same time, so the name goes in the path too.
fn copy_of_the_example(name: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-folder-form-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&example(), &dst);
    dst
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
    }
}

/// `tools/payments.yaml` → `tools/payments/tool.yaml`: the same bytes, one
/// level down, in a file named after WHAT THE THING IS. This is the edit an
/// author makes the day a tool grows a second file beside it.
fn give_it_a_folder(root: &Path, was: &str, kind: &str) {
    let file = root.join(was);
    let body = std::fs::read(&file).unwrap_or_else(|e| panic!("{was} is in the worked example: {e}"));
    std::fs::remove_file(&file).unwrap();
    let dir = file.with_extension("");
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join(format!("{kind}.yaml")), body).unwrap();
}

/// What `pact check` said, and whether it agreed to load the tree.
fn check(root: &Path) -> (bool, String) {
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("the binary runs");
    let mut text = String::from_utf8_lossy(&out.stdout).into_owned();
    text.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), text)
}

/// The loaded document, as the only door an adapter comes through (P-1).
fn show(root: &Path) -> serde_json::Value {
    let out = pact().args(["show", root.to_str().unwrap()]).output().expect("the binary runs");
    assert!(
        out.status.success(),
        "`show` refused the tree:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(&out.stdout).expect("`show` prints JSON")
}

/// The content digest `discover` publishes for a workspace.
fn digest(root: &Path) -> String {
    let out = pact().args(["discover", root.to_str().unwrap()]).output().expect("the binary runs");
    let v: serde_json::Value =
        serde_json::from_slice(&out.stdout).expect("`discover` prints JSON");
    v.get(0)
        .and_then(|w| w.get("digest"))
        .and_then(serde_json::Value::as_str)
        .unwrap_or_else(|| panic!("no digest in:\n{}", String::from_utf8_lossy(&out.stdout)))
        .to_string()
}

/// Each kind on its own, so a regression names the kind that broke rather than
/// telling the reader that one of four did.
fn one_kind_moves_into_a_folder(name: &str, was: &str, kind: &str) {
    let root = copy_of_the_example(name);
    give_it_a_folder(&root, was, kind);

    let (ok, text) = check(&root);
    assert!(ok, "`{was}` written as `{kind}.yaml` in a folder must load:\n{text}");
    assert!(
        !text.contains("is not something"),
        "the settings landed in a field named after the file:\n{text}"
    );
    // Not merely clean — the SAME document. A loader that quietly ignored the
    // folder would also print "loaded cleanly", and two documents that both
    // lost the same thing hash alike, so the digest is taken against the tree
    // the file form produces.
    assert_eq!(
        digest(&root),
        digest(&example()),
        "`{was}` moved into a folder changed the artifact, so the two spellings \
         are two different systems and a lockfile means whichever one the author \
         happened to write"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_tool_written_as_a_folder_is_the_same_tool() {
    one_kind_moves_into_a_folder("tool", "tools/payments.yaml", "tool");
}

#[test]
fn a_policy_written_as_a_folder_is_the_same_policy() {
    one_kind_moves_into_a_folder("policy", "policies/approvals.yaml", "policy");
}

#[test]
fn a_resource_written_as_a_folder_is_the_same_resource() {
    one_kind_moves_into_a_folder("resource", "resources/payments-server.yaml", "resource");
}

#[test]
fn a_redaction_written_as_a_folder_is_the_same_redaction() {
    // This one already worked, by the directory-name rule: there is exactly one
    // redaction per workspace, so its folder is `redaction/` and
    // `redaction/redaction.yaml` is a self file because the stem matches the
    // folder. It is asserted anyway, because the point of the round was that all
    // four spellings behave alike, and a change that fixed three while quietly
    // breaking the fourth would otherwise pass.
    one_kind_moves_into_a_folder("redaction", "redaction.yaml", "redaction");
}

#[test]
fn all_four_folders_at_once_are_still_the_worked_example() {
    // Separately from the four above, because the failure they cannot catch is
    // interference: `tool` becoming a self file changes what `tools/` means for
    // every entry in it, and a stem that is right on its own can still collide
    // with another. One tree, all four moved, held against the shipped one.
    let root = copy_of_the_example("all-four");
    give_it_a_folder(&root, "tools/payments.yaml", "tool");
    give_it_a_folder(&root, "policies/approvals.yaml", "policy");
    give_it_a_folder(&root, "resources/payments-server.yaml", "resource");
    give_it_a_folder(&root, "redaction.yaml", "redaction");

    let (ok, text) = check(&root);
    assert!(ok, "all four folder forms together must load:\n{text}");
    assert_eq!(digest(&root), digest(&example()), "four folders, one artifact");

    // And the settings are really in there, at full depth. `loaded cleanly` is
    // what the tree printed BEFORE this round too, for a tree that had dropped
    // the whole tool — so the reading is checked, not the verdict.
    let doc = show(&root);
    assert_eq!(
        doc["tools"]["payments"]["actions"]["issue-refund"]["spends-money"],
        serde_json::json!("yes"),
        "a setting three levels inside the tool's folder"
    );
    assert_eq!(
        doc["policies"]["approvals"]["applies-to"],
        serde_json::json!("every-agent"),
        "a setting inside the policy's folder"
    );
    assert_eq!(
        doc["resources"]["payments-server"]["asks-to-connect"],
        serde_json::json!("may-we-connect"),
        "a setting inside the resource's folder — the human consent gate on money"
    );
    assert_eq!(
        doc["redaction"]["hide"][0],
        serde_json::json!("anything that looks like a card number"),
        "a setting inside the redaction's folder"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_new_tool_in_a_folder_is_never_told_to_remove_its_own_filename() {
    // The measurement at the top of this file, as an assertion. A tool that has
    // never existed as a flat file, written straight into the folder form —
    // which is what somebody does who has only ever seen `agents/<n>/agent.yaml`
    // and reasoned by analogy.
    let root = copy_of_the_example("new-tool");
    // A host-resolved address, because this test is about the FOLDER FORM and
    // the worked example it is grafted onto writes `allow-egress: []`. An
    // `https://` address here would make the test assert a workspace that
    // breaks its own stated boundary, and the failure would read as a folder
    // problem. `host/weather` is what the flagship already does for
    // `host/payments-mcp`.
    std::fs::create_dir_all(root.join("tools/weather")).unwrap();
    std::fs::write(
        root.join("tools/weather/tool.yaml"),
        "description: Looks up the weather where the customer is.\n\
         url: host/weather\n\
         method: get\n",
    )
    .unwrap();

    let (ok, text) = check(&root);
    assert!(ok, "a tool written straight into a folder must load:\n{text}");
    for unactionable in [
        // "Remove it" — `tool` is the filename.
        "'tool' is not something a tool can have.",
        // Pointed at the directory, because the settings went a level down.
        "A tool must have a 'description'.",
        "does not say where it reaches",
    ] {
        assert!(!text.contains(unactionable), "still says {unactionable:?}:\n{text}");
    }

    let doc = show(&root);
    assert_eq!(
        doc["tools"]["weather"]["url"],
        serde_json::json!("host/weather"),
        "the tool loaded but its address did not arrive"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_redaction_beside_the_workspace_is_still_the_workspaces_own_setting() {
    // The pin on the decision NOT to put `redaction` in `kind_stems`, and the
    // reason it is not an oversight. `agent.policy` is a NAME, so making
    // `policy` a stem costs one field its file — the narrow, teachable
    // limitation `policy.rs` already documents and that `loop` and
    // `context-policy` already pay. `workspace.redaction` is a whole GROUP, and
    // `redaction.yaml` beside `workspace.yaml` is not one author's style: it is
    // the spelling the schema's help gives, the spelling `redaction.rs` tells an
    // author to create, and the spelling this example ships.
    //
    // Measured with "redaction" added to the list:
    //
    //     error: This folder has two files describing itself:
    //     'workspace.yaml' and 'redaction.yaml'.
    //       fix: Keep only one of them.
    //
    // — advice that deletes either the workspace or everything the workspace may
    // never let out. So this test fails the moment somebody adds the stem, here,
    // next to the reason, instead of in the worked example.
    let root = example();
    assert!(root.join("redaction.yaml").is_file(), "the example still ships the flat spelling");

    let (ok, text) = check(&root);
    assert!(ok, "the shipped worked example must load:\n{text}");
    assert!(
        !text.contains("two files describing itself"),
        "`redaction.yaml` became a second file describing the workspace:\n{text}"
    );

    let doc = show(&root);
    assert!(
        doc["redaction"]["hide"].as_array().is_some_and(|h| !h.is_empty()),
        "`redaction.yaml` must arrive as the workspace's `redaction:` setting, \
         not as part of the workspace's own fields"
    );
    // The other half of the same fact: its contents must NOT have been merged
    // into the workspace. A `hide:` at the top of the document is what a stem
    // for `redaction` would produce.
    assert!(doc.get("hide").is_none(), "the redaction's settings leaked into the workspace");
}
