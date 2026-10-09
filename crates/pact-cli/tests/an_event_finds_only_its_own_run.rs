//! R23 reopened for workflows (02W §4, §3 WF-19 and WF-27, §8): an event
//! reaches only a run of the workflow its port `answers:` whose key it carries.
//! A wait that hears a port is held to it: the port answers this workflow,
//! hands what arrives to the open run (`if-still-running: join`) and tells its
//! arrivals apart by the same `same-conversation-when:` as the ports that start
//! the runs, and every key names a field of what arrives. Over #16's tree
//! (`tests/trees/a-trial-booking-case/`) with a port the lesson-day wait hears.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

const TREE: &str = "tests/trees/a-trial-booking-case";
const FLOW: &str = "workflows/trial-booking.yaml";
const MOVED: &str = "ports/lesson-moved.yaml";

/// A port the wait hears: the lesson moved, so the reminder waits again.
const PORT: &str = "description: The tutor moves the lesson to another time.
kind: event
through: calendly
answers: trial-booking
accepts: { invitee-uri: text, starts-at: date and time }
same-conversation-when: [invitee-uri]
if-still-running: join
who-can-reach-it: [calendly]
";

/// The lesson-day wait listening for it as well as for the clock.
const HEARS: [(&str, &str, &str); 2] = [
    (
        FLOW,
        "    asked-of: [the-clock]\n",
        "    asked-of: [the-clock, lesson-moved]\n",
    ),
    (
        FLOW,
        "then: { nobody-answered: consent }",
        "then: { nobody-answered: consent, heard: { lesson-moved: day-before } }",
    ),
];

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

/// `pact check` on #16 with the hearing port written as `port` and each edit made.
fn check(name: &str, port: &str, edits: &[(&str, &str, &str)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-own-run-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(TREE), &dst);
    std::fs::write(dst.join(MOVED), port).unwrap();
    for (file, from, to) in HEARS.iter().chain(edits) {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
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

#[test]
fn a_port_that_joins_with_the_runs_key_is_heard() {
    let (ok, text) = check("clean", PORT, &[]);
    assert!(ok, "{text}");
    assert!(
        !text.contains("loader/an-event-the-wait-will-never-hear"),
        "{text}"
    );
}

#[test]
fn a_port_of_another_workflow_never_reaches_this_run() {
    let port = PORT
        .replace("answers: trial-booking", "answers: parent-contact")
        .replace(
            "accepts: { invitee-uri: text, starts-at: date and time }",
            "accepts: { email: text, invitee-uri: text }",
        );
    let (ok, text) = check("other-flow", &port, &[]);
    assert!(!ok, "{text}");
    assert!(
        text.contains("loader/an-event-the-wait-will-never-hear"),
        "{text}"
    );
    assert!(
        text.contains("answers 'parent-contact', not this workflow"),
        "{text}"
    );
    assert!(text.contains("fix: Add `answers: trial-booking`"), "{text}");
}

#[test]
fn a_port_that_does_not_join_never_reaches_the_open_run() {
    let (ok, text) = check(
        "queue",
        &PORT.replace("if-still-running: join", "if-still-running: queue"),
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("does not hand what arrives to the open run (`if-still-running: queue`)"),
        "{text}"
    );
}

#[test]
fn a_port_keyed_otherwise_finds_another_case() {
    let port = PORT
        .replace(
            "accepts: { invitee-uri: text, starts-at: date and time }",
            "accepts: { email: text, starts-at: date and time }",
        )
        .replace(
            "same-conversation-when: [invitee-uri]",
            "same-conversation-when: [email]",
        );
    let (ok, text) = check("other-key", &port, &[]);
    assert!(!ok, "{text}");
    assert!(
        text.contains("the run was started by 'trial-booked', keyed by [`invitee-uri`]"),
        "{text}"
    );
    assert!(
        text.contains("`same-conversation-when: [invitee-uri]`"),
        "{text}"
    );
}

#[test]
fn a_wait_hears_only_the_ports_its_question_is_asked_of() {
    let (ok, text) = check(
        "not-asked",
        PORT,
        &[(
            FLOW,
            "    asked-of: [the-clock, lesson-moved]\n",
            "    asked-of: [the-clock]\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("is not asked of 'lesson-moved', so this wait never listens for it"),
        "{text}"
    );
}

#[test]
fn a_key_is_a_field_of_what_arrives() {
    let (ok, text) = check(
        "not-a-field",
        PORT,
        &[(
            "ports/trial-booked.yaml",
            "same-conversation-when: [invitee-uri]",
            "same-conversation-when: [invitee-id]",
        )],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/a-key-that-is-not-a-field"), "{text}");
    assert!(
        text.contains("`invitee-uri`"),
        "the fields are offered:\n{text}"
    );
}

#[test]
fn what_a_port_reads_is_what_arrives_at_it() {
    let (ok, text) = check(
        "reads",
        PORT,
        &[(
            "ports/trial-booked.yaml",
            "value: input.event-type",
            "value: input.event-kind",
        )],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/a-binding-to-nothing"), "{text}");
    // ...through the one condition reader: a date compared with a word is WF-18.
    let (ok, text) = check(
        "shape",
        PORT,
        &[(
            "ports/trial-booked.yaml",
            "value: input.event-type, is: Free Trial Lesson",
            "value: input.starts-at, more-than: 5000 USD",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("loader/compared-in-the-wrong-shape"),
        "{text}"
    );
}
