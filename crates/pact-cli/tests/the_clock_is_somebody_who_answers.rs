//! `asked-of: [the-clock]` passes CHK-7: the clock is somebody who answers, at
//! the time `answer-within:` names (02W §2.8, §3 WF-21 and WF-22, §4 R12, §8).
//! A question only the clock answers has no gate — no wording, no answer — and
//! its one exit is `nobody-answered`; `pact waits` lists it with
//! `waiting-for-a-time`. Over #16's tree (`tests/trees/a-trial-booking-case/`,
//! 02W §5.1) and mutations of it.

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
const WAIT: &str = "    asked-of: [the-clock]\n";

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

/// Run `verb` on a copy of #16 with each `(file, from, to)` edit made.
fn run(name: &str, verb: &str, edits: &[(&str, &str, &str)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-clock-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(TREE), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    let out = pact()
        .args([verb, dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    let mut said = String::from_utf8_lossy(&out.stdout).into_owned();
    said.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), said)
}

#[test]
fn a_wait_for_the_clock_loads_with_nobody_named_and_nothing_to_say() {
    let (ok, text) = run("clean", "check", &[]);
    assert!(ok, "{text}");
    assert!(!text.contains("loader/nobody-can-answer"), "{text}");
    assert!(
        !text.contains("loader/a-question-with-nothing-to-say"),
        "{text}"
    );
}

#[test]
fn pact_waits_lists_the_clock_wait_with_waiting_for_a_time() {
    let (ok, text) = run("waits", "waits", &[]);
    assert!(ok, "{text}");
    let json = &text[text.find('{').unwrap()..=text.rfind('}').unwrap()];
    let report: serde_json::Value = serde_json::from_str(json).expect("pact waits prints JSON");
    let waits = report["waits"].as_array().unwrap();
    assert_eq!(waits.len(), 1, "{text}");
    let w = &waits[0];
    assert_eq!(w["reason"], "waiting-for-a-time");
    assert_eq!(w["workflow"], "trial-booking");
    assert_eq!(w["stage"], "day-before");
    assert_eq!(w["question"], "day-before-the-lesson");
    assert_eq!(
        w["nobody-answered"], "consent",
        "the one exit, taken when the time comes"
    );
    assert_eq!(w["moment"]["at"], "input.starts-at");
    assert_eq!(w["moment"]["before"], "24h");
    assert_eq!(w["wakes"], true, "a moment is a time a scheduler wakes at");
    assert_eq!(report["wake-ups"][0], "day-before-the-lesson");
}

#[test]
fn a_clock_only_wait_has_one_exit() {
    let (ok, text) = run(
        "answered",
        "check",
        &[(
            FLOW,
            "then: { nobody-answered: consent }",
            "then: { answered: consent, nobody-answered: consent }",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("loader/a-line-this-stage-never-reads"),
        "{text}"
    );
    assert!(text.contains("which only the clock answer"), "{text}");
}

#[test]
fn a_clock_only_wait_has_no_gate() {
    let (ok, text) = run(
        "gate",
        "check",
        &[(
            FLOW,
            WAIT,
            "    asked-of: [the-clock]\n    answer: { approved: yes or no }\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/nobody-can-answer"), "{text}");
    assert!(
        text.contains("asked only of the clock and of events"),
        "{text}"
    );
}

#[test]
fn the_clock_with_no_time_never_answers() {
    let (ok, text) = run(
        "no-time",
        "check",
        &[(
            FLOW,
            "    answer-within: { at: input.starts-at, before: 24h, in-time-zone: steps.tutor.zone }\n",
            "",
        )],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/nobody-can-answer"), "{text}");
    assert!(
        text.contains("is asked of the clock and says no time"),
        "{text}"
    );
}

#[test]
fn a_person_asked_must_be_told_something() {
    // WF-22: the same question, asked of a team, needs its words and its shape.
    let (ok, text) = run(
        "person",
        "check",
        &[(FLOW, WAIT, "    asked-of: [front-desk]\n")],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("loader/a-question-with-nothing-to-say"),
        "{text}"
    );
    assert!(text.contains("no `says:` and `answer:`"), "{text}");
}

#[test]
fn an_empty_list_is_still_nobody() {
    let (ok, text) = run("nobody", "check", &[(FLOW, WAIT, "    asked-of: []\n")]);
    assert!(!ok, "{text}");
    assert!(text.contains("loader/nobody-can-answer"), "{text}");
}

#[test]
fn a_reminder_does_exactly_one_thing() {
    let at =
        "    answer-within: { at: input.starts-at, before: 24h, in-time-zone: steps.tutor.zone }\n";
    for (name, reminder, says) in [
        (
            "two",
            "{ at: 1h, nudges: yes, tells: [front-desk] }",
            "does two things at once",
        ),
        ("none", "{ at: 1h }", "does nothing when its time comes"),
    ] {
        let (ok, text) = run(
            name,
            "check",
            &[(
                FLOW,
                at,
                &format!("{at}    reminds-at:\n      - {reminder}\n"),
            )],
        );
        assert!(!ok, "[{name}] {text}");
        assert!(text.contains("loader/nobody-can-answer"), "[{name}] {text}");
        assert!(text.contains(says), "[{name}] {text}");
    }
    let (ok, text) = run(
        "one",
        "check",
        &[(
            FLOW,
            at,
            &format!("{at}    reminds-at:\n      - {{ at: 1h, tells: [front-desk] }}\n"),
        )],
    );
    assert!(ok, "{text}");
}

#[test]
fn an_agent_waits_for_people_and_not_for_the_clock() {
    // A question no workflow asks is an agent's, and an agent's run waits for
    // people: the clock and events are a workflow's waits.
    let dst = std::env::temp_dir().join(format!("pact-clock-agent-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join("examples/refund-desk"), &dst);
    let p = dst.join("questions/is-this-ok.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    let edited = text.replacen(
        "asked-of: [support-leads]",
        "asked-of: [support-leads, the-clock]",
        1,
    );
    std::fs::write(&p, edited).unwrap();
    let out = pact()
        .args(["check", dst.to_str().unwrap()])
        .output()
        .unwrap();
    let said = String::from_utf8_lossy(&out.stdout).into_owned();
    let _ = std::fs::remove_dir_all(&dst);
    assert!(!out.status.success(), "{said}");
    assert!(said.contains("loader/a-workflow-only-spelling"), "{said}");
}

#[test]
fn a_line_named_at_is_not_a_moment() {
    // With no `time-zone:` anywhere, an input, an answer, a bound key and a
    // question's answer line named `at` are fields, not moments: only the lines
    // whose type is a moment are read so.
    let dst = std::env::temp_dir().join(format!("pact-clock-named-at-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(TREE), &dst);
    let ws = dst.join("workspace.yaml");
    let w = std::fs::read_to_string(&ws).unwrap();
    std::fs::write(&ws, w.replacen("time-zone: America/Chicago\n", "", 1)).unwrap();
    std::fs::write(
        dst.join("workflows/stamp.yaml"),
        "description: x\naccepts: { at: text }\nanswers-with: { at: text }\n\
         starts-at: reply\nsteps:\n  reply:\n    does: answer\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("workflows/stamp-caller.yaml"),
        "description: x\naccepts: { when: text }\nstarts-at: ask\nsteps:\n  ask:\n    \
         does: ask-someone\n    asks: when-was-it\n    then: { answered: stamp, \
         nobody-answered: stamp }\n  stamp:\n    does: call\n    call: stamp\n    \
         bind: { at: input.when }\n    then: { answered: reply }\n  reply:\n    \
         does: answer\nquestions:\n  when-was-it:\n    description: x\n    \
         asked-of: [front-desk]\n    says: When was it?\n    answer: { at: date }\n    \
         answer-within: 2 days\n",
    )
    .unwrap();
    let out = pact()
        .args(["check", dst.to_str().unwrap()])
        .output()
        .unwrap();
    let said = String::from_utf8_lossy(&out.stdout).into_owned();
    let _ = std::fs::remove_dir_all(&dst);
    assert!(out.status.success(), "{said}");
    assert!(!said.contains("loader/a-time-with-no-zone"), "{said}");
}

#[test]
fn a_question_an_agent_asks_is_not_also_a_workflows() {
    // refund-desk's `is-this-ok` is asked by its approval policy; a workflow
    // asking it too, written the workflow's way, leaves the agent's run with
    // nothing to do on silence. Refused once, with the fix to split it.
    let dst = std::env::temp_dir().join(format!("pact-clock-shared-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join("examples/refund-desk"), &dst);
    let p = dst.join("questions/is-this-ok.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    std::fs::write(&p, text.replacen("if-nobody-answers: escalate\n", "", 1)).unwrap();
    std::fs::create_dir_all(dst.join("workflows")).unwrap();
    std::fs::write(
        dst.join("workflows/review.yaml"),
        "description: x\nstarts-at: check\nsteps:\n  check:\n    does: ask-someone\n    \
         asks: is-this-ok\n    then: { nobody-answered: done }\n",
    )
    .unwrap();
    let out = pact()
        .args(["check", dst.to_str().unwrap()])
        .output()
        .unwrap();
    let said = String::from_utf8_lossy(&out.stdout).into_owned();
    let _ = std::fs::remove_dir_all(&dst);
    assert!(!out.status.success(), "{said}");
    assert_eq!(
        said.matches("loader/a-workflow-only-spelling").count(),
        1,
        "{said}"
    );
    assert!(said.contains("Give each its own question"), "{said}");
}

#[test]
fn a_clock_wait_before_the_answer_is_a_path_that_answers() {
    // A wait only the clock answers never ends `answered`, so its one exit is
    // the way on: a workflow that answers may wait for the clock before it does.
    let (ok, text) = run(
        "before-the-answer",
        "check",
        &[
            (
                "workflows/parent-contact.yaml",
                "    then: { answered: reply }\n",
                "    then: { answered: pause }\n  pause:\n    does: ask-someone\n    asks: a-moment\n    \
             then: { nobody-answered: reply }\n",
            ),
            (
                "workflows/parent-contact.yaml",
                "    does: answer\n",
                "    does: answer\nquestions:\n  a-moment:\n    description: x\n    \
             asked-of: [the-clock]\n    answer-within: 1 minute\n",
            ),
        ],
    );
    assert!(ok, "{text}");
    assert!(
        !text.contains("loader/a-path-that-answers-nothing"),
        "{text}"
    );
}
