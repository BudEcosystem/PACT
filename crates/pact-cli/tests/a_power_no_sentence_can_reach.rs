//! A power declared at a moment where nothing can use it (R24, G5).
//!
//! `docs/50-NOT-COPIED.md` §G5 states the invariant this holds: *"Every power in
//! that list has a sentence that reaches it and an address that carries it
//! out."* Nothing held it.
//!
//! Measured, before this check existed:
//!
//! ```text
//! when: turn.message.after
//! may: [hide-values, stop-the-run]
//! rules:
//!   - replace anything that looks like a card number with "***"
//!
//! OK — loaded cleanly (19 settings)
//! ```
//!
//! `stop-the-run` is a real power. The harness honours it at
//! `turn.message.after`. And no sentence in the closed vocabulary produces one
//! there — the only sentence that needs it is bound to `step.tool.before`. So
//! the line reads to a reviewer as a safety control, and it is not one.
//!
//! This is R24's own defect — a setting nothing can reach — surviving INSIDE the
//! list R24 was applied to, which is why the check runs over
//! (power × moment) rather than over sentences.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A workspace whose one interceptor is written as given.
fn with_interceptor(name: &str, body: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-power-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    std::fs::create_dir_all(dst.join("interceptors")).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Probe\ndescription: A probe workspace.\n")
        .unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        "name: Desk\ndescription: Answers questions.\ninstructions: Answer plainly.\n\
         interceptors: [house-rule]\n",
    )
    .unwrap();
    std::fs::write(dst.join("interceptors/house-rule.yaml"), body).unwrap();
    dst
}

fn check(root: &std::path::Path) -> String {
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr))
}

/// `send-elsewhere` is produced by exactly one sentence and that sentence is
/// pinned to `step.tool.before`, so declaring it at `turn.message.after` is a
/// power nothing there can reach.
///
/// This fixture used to declare `stop-the-run`, and that stopped being a defect
/// the moment F7 landed: `if the answer mentions ..., stop and say "..."` works
/// at `turn.message.after`, so the power now has a sentence and the warning
/// would be a false refusal. A check like this one is only as good as its
/// example, and its example has to move when the vocabulary does.
const A_POWER_NOTHING_HERE_PRODUCES: &str = "\
description: Hide card numbers in the answer.
when: turn.message.after
may: [hide-values, send-elsewhere]
rules:
  - replace anything that looks like a card number with \"***\"
";

#[test]
fn a_may_entry_no_rule_at_any_of_this_files_moments_can_produce_is_refused() {
    let root = with_interceptor("declared", A_POWER_NOTHING_HERE_PRODUCES);
    let text = check(&root);
    assert!(
        text.contains("loader/power-nothing-can-use"),
        "a power nothing at these moments can use must be refused:\n{text}"
    );
    assert!(
        text.contains("send-elsewhere"),
        "the message has to name which power:\n{text}"
    );
    assert!(
        text.contains("turn.message.after"),
        "and at which moment:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_caret_sits_on_the_line_the_fix_says_to_change() {
    // The message is about `may:` and the fix says to edit `may:`. Anchoring on
    // `rules:` would send an author to change sentences that are all correct.
    let root = with_interceptor("caret", A_POWER_NOTHING_HERE_PRODUCES);
    let text = check(&root);
    let line = text
        .lines()
        .find(|l| l.contains("may: [hide-values, send-elsewhere]"))
        .expect("the may: line is quoted back");
    assert!(line.trim_start().starts_with('3'), "quoted the wrong line: {line}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_power_that_gained_a_sentence_stops_being_reported() {
    // The other direction, and the reason this check has to be computed from
    // the vocabulary rather than from a list of known-bad pairs. `stop-the-run`
    // at `turn.message.after` WAS this defect and is not any more, because F7
    // added a sentence that works there. Nothing in this file had to be told.
    let root = with_interceptor(
        "gained",
        "description: This desk books appointments; it does not advise.\n\
         when: turn.message.after\n\
         may: [stop-the-run]\n\
         rules:\n  \
         - if the answer mentions \"diagnosis\", stop and say \"A nurse will call you back.\"\n",
    );
    let text = check(&root);
    assert!(
        !text.contains("loader/power-nothing-can-use"),
        "a power with a sentence at this moment must not be reported:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_names_a_moment_the_power_really_works_at() {
    // R24 again, one level in: a fix that offers a moment the power still
    // cannot be used at is a fix in shape only.
    let root = with_interceptor("fix", A_POWER_NOTHING_HERE_PRODUCES);
    let text = check(&root);
    assert!(
        text.contains("add a moment it works at: step.tool.before"),
        "the fix has to name where the power is actually reachable:\n{text}"
    );

    // And typing it leaves a tree that checks clean.
    let fixed = with_interceptor(
        "typed",
        "description: Send it elsewhere after too many calls.\n\
         when: step.tool.before\n\
         may: [hide-values, send-elsewhere]\n\
         rules:\n  \
         - replace anything that looks like a card number with \"***\"\n  \
         - if payments is called more than 3 times in one run, go to the reply stage instead\n",
    );
    std::fs::create_dir_all(fixed.join("tools")).unwrap();
    std::fs::write(
        fixed.join("tools/payments.yaml"),
        "description: Moves money.\nconnect: none\nactions:\n  pay:\n    description: Pays.\n",
    )
    .unwrap();
    let after = check(&fixed);
    assert!(
        !after.contains("loader/power-nothing-can-use"),
        "at a moment the power works, it must be silent:\n{after}"
    );
    let _ = std::fs::remove_dir_all(&root);
    let _ = std::fs::remove_dir_all(&fixed);
}

#[test]
fn a_power_every_moment_can_use_is_never_questioned() {
    let root = with_interceptor(
        "quiet",
        "description: Hide card numbers in the answer.\n\
         when: turn.message.after\n\
         may: [hide-values]\n\
         rules:\n  - replace anything that looks like a card number with \"***\"\n",
    );
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    assert!(
        out.status.success(),
        "a declared power its own sentence uses is correct:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_shipped_trees_gain_nothing_from_this() {
    for tree in ["examples/refund-desk", "examples/patterns/escalation"] {
        let path = format!("{}/../../{tree}", env!("CARGO_MANIFEST_DIR"));
        let out = pact().args(["check", &path]).output().expect("runs");
        let text = format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
        assert!(out.status.success(), "{tree}:\n{text}");
        assert!(!text.contains("loader/power-nothing-can-use"), "{tree}:\n{text}");
    }
}
