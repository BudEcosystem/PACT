//! Every worked tree of 02W §5 loads clean (02W §8).
//!
//! The five trees — trial-lesson booking (#16), invoices with For each and
//! approval (#48), Reflexion as a Repeat (#69), a supervisor with specialists
//! (#79) and the long-running interconnection case (#60) — are written under
//! `tests/trees/workflows-*` as the design prints them, with the agents, tools,
//! programs and values they name but do not show. Each prints OK with no error
//! and no warning, and the only notes are the two the design expects: a write
//! that cannot be undone and is asked of nobody (WF-25, the reminder text of
//! #16 and the other messages a flow sends), and a port that only joins open
//! runs (WF-29).

use std::path::PathBuf;
use std::process::Command;

const TREES: [&str; 5] = [
    "workflows-16-trial-booking",
    "workflows-48-invoices",
    "workflows-69-reflexion",
    "workflows-79-supervisor",
    "workflows-60-interconnection",
];

const EXPECTED_NOTES: [&str; 2] = [
    "loader/cannot-be-undone-and-nobody-asked",
    "loader/a-port-that-cannot-start-a-run",
];

fn check(name: &str) -> (bool, String) {
    let root = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/trees")).join(name);
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

/// Each diagnostic's severity and rule, in the order printed.
fn told(text: &str) -> Vec<(String, String)> {
    let mut out = Vec::new();
    let mut severity = String::new();
    for line in text.lines() {
        for word in ["error", "warning", "note"] {
            if line.starts_with(&format!("{word}:")) {
                severity = word.to_string();
            }
        }
        if let Some(rule) = line.trim().strip_prefix("rule: ") {
            out.push((severity.clone(), rule.to_string()));
        }
    }
    out
}

#[test]
fn every_worked_tree_loads_clean_with_only_the_notes_expected() {
    for name in TREES {
        let (ok, text) = check(name);
        assert!(ok, "{name}:\n{text}");
        assert!(text.contains("loaded cleanly"), "{name}:\n{text}");
        for (severity, rule) in told(&text) {
            assert_eq!(severity, "note", "{name}: {rule}\n{text}");
            assert!(
                EXPECTED_NOTES.contains(&rule.as_str()),
                "{name}: an unexpected note {rule}\n{text}"
            );
        }
    }
}

#[test]
fn the_trial_booking_notes_the_reminder_text_and_the_cancel_port_only() {
    let (_, text) = check("workflows-16-trial-booking");
    let notes = told(&text);
    assert_eq!(notes.len(), 2, "{text}");
    assert!(
        text.contains(
            "note: 'remind' calls `twilio/send-sms`, which cannot be undone, and nobody is asked \
             before it runs."
        ),
        "{text}"
    );
    assert!(
        text.contains("note: 'trial-cancelled' cannot fill every input 'trial-booking' needs"),
        "{text}"
    );
}

#[test]
fn a_write_with_an_undo_is_not_noted() {
    // #48 posts the bill and schedules the payment, both with `undone-by:`;
    // only the messages it sends are noted.
    let (_, text) = check("workflows-48-invoices");
    for stage in ["post", "pay"] {
        assert!(!text.contains(&format!("note: '{stage}' calls")), "{text}");
    }
    assert!(text.contains("note: 'tell-sender' calls `outlook/send-email`"), "{text}");
}
