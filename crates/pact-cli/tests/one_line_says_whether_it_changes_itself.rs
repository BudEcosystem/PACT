//! One decision, one setting: whether the agent may change itself.
//!
//! `learning.enabled:` was `one-of [off, propose-only, yes]` and
//! `learning.auto-apply:` was yes-or-no beside it. Six spellings for three real
//! states, and the pair could disagree without anybody being told. Measured on
//! the shipped worked example before the fix:
//!
//! ```text
//! enabled: propose-only
//! auto-apply: yes
//! → OK — examples/refund-desk loaded cleanly (492 settings).   exit 0
//! ```
//!
//! The reader takes `enabled:` first, so the author's `yes` was discarded and
//! nothing said so. The other direction was worse: `enabled: yes` with no
//! `auto-apply:` line at all defaulted to `no`, so the strongest word on the one
//! setting that decides whether a system rewrites itself with nobody watching
//! meant nothing.
//!
//! This holds the surviving single setting to what a governance line has to do:
//! refuse the deleted spelling by name, refuse a word it no longer has, and ask
//! for the list of what may change exactly when — and only when — it is owed.
//! `docs/50-NOT-COPIED.md` §5 R59 is the record of the deletion.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/refund-desk")
}

/// Copy the worked example and rewrite `learning.yaml`, returning the temp root.
///
/// Deliberately the whole tree rather than a hand-built fixture: the point of
/// every test here is that the line the AUTHOR wrote is what decides, and a
/// document assembled in Rust proves only that Rust can assemble a document.
fn with_learning(name: &str, from: &str, to: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-learning-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&example(), &dst);
    let p = dst.join("learning.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} is not in examples/refund-desk/learning.yaml"
    );
    std::fs::write(&p, text.replace(from, to)).unwrap();
    dst
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
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

fn check(root: &std::path::Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

#[test]
fn the_deleted_second_setting_is_refused_by_name_rather_than_ignored() {
    // The exact line a workspace written against the previous version carries.
    // It must not load and do nothing — that is the state this whole deletion
    // exists to end — and the message has to name the file, the line, and a
    // setting the author can type instead.
    let root = with_learning(
        "auto-apply",
        "enabled: propose-only",
        "enabled: propose-only\nauto-apply: no",
    );
    let (ok, text) = check(&root);

    assert!(
        !ok,
        "`auto-apply:` must be refused, and it loaded cleanly:\n{text}"
    );
    assert!(
        text.contains("'auto-apply' is not something learning can have"),
        "{text}"
    );
    assert!(
        text.contains("learning.yaml:"),
        "must name the file and the line:\n{text}"
    );
    assert!(text.contains("  fix: "), "must offer a fix:\n{text}");
    assert!(
        text.contains("enabled"),
        "the fix has to point at the setting that now carries the decision:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_word_that_used_to_mean_the_strongest_answer_is_refused_with_the_three_that_exist() {
    // `enabled: yes` was legal last version and meant nothing without a second
    // line. A word that is silently not a choice any more is the worst outcome
    // on this setting: the author believes they switched self-improvement on.
    let root = with_learning("stale-yes", "enabled: propose-only", "enabled: yes");
    let (ok, text) = check(&root);

    assert!(
        !ok,
        "`enabled: yes` is no longer a choice and must be refused:\n{text}"
    );
    assert!(
        text.contains("learning.yaml:"),
        "must name the file and the line:\n{text}"
    );
    for choice in ["off", "propose-only", "applies-safe-changes-itself"] {
        assert!(
            text.contains(choice),
            "the fix must offer '{choice}':\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn saying_it_applies_changes_itself_makes_the_author_say_which_ones() {
    // The obligation `auto-apply:` used to carry, moved onto the value that
    // earns it. The fix has to name all four choices: picking one blind, on the
    // line that puts wording changes live with nobody reading them, is the
    // wrong governance decision made by accident.
    let root = with_learning(
        "no-list",
        "enabled: propose-only",
        "enabled: applies-safe-changes-itself",
    );
    // And take the list away, which is what a first-time author writing the
    // third choice would have.
    let p = root.join("learning.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    let stripped: String = text
        .lines()
        .filter(|l| {
            !l.starts_with("may-improve-on-its-own:")
                && !matches!(l.trim(), "- phrasing" | "- examples" | "- skill-notes")
        })
        .collect::<Vec<_>>()
        .join("\n");
    std::fs::write(&p, stripped).unwrap();

    let (ok, text) = check(&root);
    assert!(
        !ok,
        "the third choice with nothing saying what may change must be refused:\n{text}"
    );
    assert!(
        text.contains("may-improve-on-its-own"),
        "must name the missing setting:\n{text}"
    );
    assert!(
        text.contains("applies-safe-changes-itself"),
        "must quote the value that made it necessary, or the reader cannot tell why:\n{text}"
    );
    assert!(
        text.contains("learning.yaml:"),
        "must name the file and the line:\n{text}"
    );
    for choice in [
        "phrasing",
        "examples",
        "skill-notes",
        "when-skills-are-used",
    ] {
        assert!(
            text.contains(choice),
            "the fix must offer '{choice}':\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn saying_nothing_applies_itself_does_not_demand_a_list_of_what_may() {
    // The other half of the same move, and the reason `needs-also:` was the
    // wrong mechanism: it fires on PRESENCE, so `auto-apply: no` — the line
    // meaning *"nothing takes effect without a person"* — demanded a list of
    // what does. A workspace on `propose-only` owes no such list.
    let root = with_learning(
        "propose-only-no-list",
        "enabled: propose-only",
        "enabled: propose-only",
    );
    let p = root.join("learning.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    let stripped: String = text
        .lines()
        .filter(|l| {
            !l.starts_with("may-improve-on-its-own:")
                && !matches!(l.trim(), "- phrasing" | "- examples" | "- skill-notes")
        })
        .collect::<Vec<_>>()
        .join("\n");
    std::fs::write(&p, stripped).unwrap();

    let (ok, text) = check(&root);
    assert!(
        ok,
        "`propose-only` owes no list of what may change itself:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_specification_has_exactly_one_setting_for_this_decision() {
    // The structural half. A second setting could come back as a YAML edit, and
    // the two would agree for exactly as long as nobody edited one of them.
    let schema = std::fs::read_to_string(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../spec/schema.yaml"),
    )
    .unwrap();
    let doc = pact_doc::parse_yaml(&schema, camino::Utf8Path::new("spec/schema.yaml"))
        .expect("the specification parses");
    let learning = doc
        .get("groups")
        .and_then(|g| g.get("learning"))
        .and_then(|l| l.get("fields"))
        .and_then(pact_doc::Node::as_map)
        .expect("the specification has a `learning` kind with fields");

    assert!(
        !learning.contains_key("auto-apply"),
        "`auto-apply:` is back beside `enabled:`. Two settings for one decision \
         is what §5 R59 records deleting — see docs/50-NOT-COPIED.md."
    );
    let enabled = learning
        .get("enabled")
        .expect("`enabled:` is the surviving setting");
    let choices: Vec<&str> = enabled
        .node
        .get("choices")
        .and_then(pact_doc::Node::as_list)
        .expect("`enabled:` offers a closed set of answers")
        .iter()
        .filter_map(pact_doc::Node::as_str)
        .collect();
    assert_eq!(
        choices,
        ["off", "propose-only", "applies-safe-changes-itself"],
        "three real states, and each answer has to be named for what happens — \
         `yes` described nothing, which is how it came to mean nothing"
    );
}

#[test]
fn the_refusal_ledger_records_the_deletion() {
    // A field removed from an authoring surface without a row is a capability
    // that quietly became a to-do, which is the thing 50-NOT-COPIED.md exists to
    // prevent. `eve_inventory.rs` and `deliberate_refusals.rs` hold the SHAPE of
    // every row; this holds that THIS one is there.
    let doc = std::fs::read_to_string(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../docs/50-NOT-COPIED.md"),
    )
    .unwrap();
    let row = doc
        .lines()
        .find(|l| l.starts_with("| R59 "))
        .expect("§5 must carry the row that argues deleting `learning.auto-apply:`");
    assert!(
        row.contains("auto-apply"),
        "R59 must name what was deleted: {row}"
    );
    assert!(
        row.contains("applies-safe-changes-itself"),
        "R59 must name what an author writes instead: {row}"
    );
}
