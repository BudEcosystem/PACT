//! R44 reopened (02W §4, §3 WF-28 and WF-29, §8): what an arrival does while a
//! run with the same key is open is one line, `if-still-running:`, with the same
//! six choices on every kind of port — an event, a conversation, a system
//! calling in and a timer. A port that is not a timer says what makes two
//! arrivals the same case before any choice but `start` can mean anything. The
//! loader half: every choice loads on every kind, over #16's ports
//! (`tests/trees/workflows-16-trial-booking/`) and the worked example's own.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

const SIX: [&str; 6] = ["start", "queue", "join", "cancel-previous", "skip", "stop"];

fn copy(src: &Path, dst: &Path) {
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

fn check(name: &str, tree: &str, file: &str, from: &str, to: &str) -> (bool, String) {
    edited(name, tree, file, &[(from, to)])
}

/// `pact check` on a copy of `tree` with each edit made to `file`.
fn edited(name: &str, tree: &str, file: &str, edits: &[(&str, &str)]) -> (bool, String) {
    // One folder per call: the tests run side by side and reuse choice names.
    static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let n = N.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dst = std::env::temp_dir().join(format!("pact-overlap-{name}-{n}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(tree), &dst);
    let p = dst.join(file);
    let mut text = std::fs::read_to_string(&p).unwrap();
    for (from, to) in edits {
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        text = text.replacen(from, to, 1);
    }
    std::fs::write(&p, text).unwrap();
    let out = pact()
        .args(["check", dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

const TRIAL: &str = "tests/trees/workflows-16-trial-booking";
const DESK: &str = "examples/refund-desk";

#[test]
fn every_choice_loads_on_an_event_and_on_a_system_calling_in() {
    for choice in SIX {
        for (file, written) in [
            ("ports/trial-booked.yaml", "if-still-running: skip"),
            ("ports/parent-contact-calls.yaml", "if-still-running: queue"),
        ] {
            let (ok, text) = check(
                choice,
                TRIAL,
                file,
                written,
                &format!("if-still-running: {choice}"),
            );
            assert!(ok, "[{file} {choice}] {text}");
        }
    }
}

#[test]
fn every_choice_but_join_loads_on_a_conversation_with_an_agent() {
    for choice in SIX {
        let (ok, text) = check(
            choice,
            DESK,
            "ports/slack.yaml",
            "who-can-reach-it:",
            &format!("if-still-running: {choice}\nwho-can-reach-it:"),
        );
        if choice == "join" {
            // R23 stays refused for an agent: its conversation is reached by
            // its own port only.
            assert!(!ok, "{text}");
            assert!(text.contains("loader/a-workflow-only-spelling"), "{text}");
        } else {
            assert!(ok, "[{choice}] {text}");
        }
    }
}

#[test]
fn every_choice_loads_on_a_timer_with_no_key() {
    for choice in SIX.into_iter().filter(|c| *c != "join") {
        let (ok, text) = check(
            choice,
            DESK,
            "ports/weekly-review.yaml",
            "if-still-running: skip",
            &format!("if-still-running: {choice}"),
        );
        assert!(ok, "[{choice}] {text}");
    }
}

#[test]
fn a_choice_with_no_key_to_tell_cases_apart_is_refused() {
    let (ok, text) = check(
        "no-key",
        TRIAL,
        "ports/trial-cancelled.yaml",
        "same-conversation-when: [invitee-uri]\n",
        "",
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/overlap-with-no-key"), "{text}");
    assert!(text.contains("`if-still-running: stop`"), "{text}");
    // `start` begins another run anyway, so it needs no key.
    let (ok, text) = check(
        "start",
        TRIAL,
        "ports/parent-contact-calls.yaml",
        "same-conversation-when: [email]\n",
        "",
    );
    assert!(!ok, "a system calling in is held the same: {text}");
    assert!(text.contains("loader/overlap-with-no-key"), "{text}");
    let (ok, text) = edited(
        "start",
        TRIAL,
        "ports/parent-contact-calls.yaml",
        &[
            ("same-conversation-when: [email]\n", ""),
            ("if-still-running: queue", "if-still-running: start"),
        ],
    );
    assert!(ok, "{text}");
}

#[test]
fn a_port_that_cannot_fill_the_inputs_only_joins_and_is_noted() {
    let (ok, text) = check(
        "note",
        TRIAL,
        "ports/trial-cancelled.yaml",
        "kind: event",
        "kind: event",
    );
    assert!(ok, "{text}");
    assert!(
        text.contains("note: 'trial-cancelled' cannot fill every input 'trial-booking' needs"),
        "{text}"
    );
    assert!(
        text.contains("loader/a-port-that-cannot-start-a-run"),
        "{text}"
    );
    assert!(!text.contains("'trial-booked' cannot fill"), "{text}");
}

#[test]
fn skip_for_a_while_loads_beside_its_choice() {
    let (ok, text) = check(
        "for-a-while",
        TRIAL,
        "ports/trial-booked.yaml",
        "if-still-running: skip",
        "if-still-running: skip\ncounts-as-the-same-for: 10 minutes",
    );
    assert!(ok, "{text}");
}

#[test]
fn a_timer_for_a_workflow_says_which_zone_its_time_is_in() {
    // WF-30: a time of day means nothing without a zone. Here the workspace
    // names none, so the timer must.
    let timer = "description: Each weekday morning, look again at yesterday's bookings.
every: weekday mornings at 9
answers: parent-contact
";
    for (name, port, refused) in [
        ("no-zone", timer.to_string(), true),
        (
            "zoned",
            format!("{timer}in-time-zone: America/Chicago\n"),
            false,
        ),
        (
            "interval",
            timer.replace("weekday mornings at 9", "every 10 minutes"),
            false,
        ),
    ] {
        static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let n = N.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let dst =
            std::env::temp_dir().join(format!("pact-overlap-zone-{n}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dst);
        copy(&repo().join(TRIAL), &dst);
        let ws = dst.join("workspace.yaml");
        let text = std::fs::read_to_string(&ws).unwrap();
        std::fs::write(&ws, text.replacen("time-zone: America/Chicago\n", "", 1)).unwrap();
        std::fs::write(dst.join("ports/mornings.yaml"), port).unwrap();
        let out = pact()
            .args(["check", dst.to_str().unwrap()])
            .output()
            .expect("runs");
        let said = String::from_utf8_lossy(&out.stdout).into_owned();
        let _ = std::fs::remove_dir_all(&dst);
        assert_eq!(
            said.contains("loader/a-time-with-no-zone"),
            refused,
            "[{name}] {said}"
        );
    }
}
