//! A question appears where its answerer chose (02W §2.8, §3 WF-36 and WF-40,
//! §8): `asked-in:` is written only for a channel, `the-requester` or an outside
//! contact, because a person, a role or a team is reached the way they chose;
//! and a question a workflow asks has no `if-nobody-answers:`, because the
//! asking stage's `nobody-answered:` exit is the one place silence goes. Over
//! mutations of #48's tree (`tests/trees/an-invoice-case/`), and of the worked
//! #48 (`tests/trees/workflows-48-invoices/`) for the question a failure plan
//! asks, which is the workflow's too.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

const TREE: &str = "tests/trees/an-invoice-case";
const QUESTION: &str = "questions/budget-owner-approves.yaml";
const ASKED: &str = "asked-of: [the-requester]";

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

fn check(name: &str, file: &str, from: &str, to: &str) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-asked-in-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(TREE), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
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
fn a_place_is_named_for_the_requester_a_channel_and_an_outside_contact() {
    for (name, asked) in [
        ("requester", "asked-of: [the-requester]"),
        ("channel", "asked-of: [\"#ap-approvals\"]"),
        ("contact", "asked-of: [input.invoice.po]"),
    ] {
        let (ok, text) = check(
            name,
            QUESTION,
            ASKED,
            &format!("{asked}\nasked-in: slack #ap-approvals"),
        );
        assert!(ok, "[{name}] {text}");
    }
}

#[test]
fn a_person_a_role_or_a_team_is_reached_the_way_they_chose() {
    let (ok, text) = check(
        "team",
        QUESTION,
        ASKED,
        "asked-of: [ap-clerks]\nasked-in: slack #ap-approvals",
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("loader/asked-in-for-someone-who-chooses"),
        "{text}"
    );
    assert!(
        text.contains("asked of 'ap-clerks', a person, a role or a team"),
        "{text}"
    );
    assert!(text.contains("fix: Delete it."), "{text}");
}

#[test]
fn silence_in_a_workflow_goes_to_its_stages_exit() {
    let (ok, text) = check(
        "silence",
        QUESTION,
        "answer-within: 2 days",
        "answer-within: 2 days\nif-nobody-answers: decline",
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/an-agent-only-spelling"), "{text}");
    assert!(
        text.contains("asked by the workflow 'one-invoice'"),
        "{text}"
    );
    assert!(
        text.contains("`then: {nobody-answered: <a stage>}`"),
        "{text}"
    );
}

#[test]
fn a_question_only_an_agent_asks_still_says_what_silence_does() {
    // The schema's `required: yes` moved to the loader, unchanged for agents.
    let dst = std::env::temp_dir().join(format!("pact-asked-in-agent-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join("examples/refund-desk"), &dst);
    let p = dst.join("questions/is-this-ok.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    std::fs::write(&p, text.replacen("if-nobody-answers: escalate\n", "", 1)).unwrap();
    let out = pact()
        .args(["check", dst.to_str().unwrap()])
        .output()
        .unwrap();
    let said = String::from_utf8_lossy(&out.stdout).into_owned();
    let _ = std::fs::remove_dir_all(&dst);
    assert!(!out.status.success(), "{said}");
    assert!(
        said.contains("A question must have an 'if-nobody-answers'."),
        "{said}"
    );
}

#[test]
fn carrying_on_is_spelled_carry_on_in_a_workflow() {
    let (ok, text) = check(
        "carry-on",
        "workflows/one-invoice.yaml",
        "starts-at: match",
        "limits:\n  finishes-within: 7 days\n  when-it-runs-out: answer-with-what-it-has\nstarts-at: match",
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/an-agent-only-spelling"), "{text}");
    assert!(text.contains("Write `carry-on`"), "{text}");
    let (ok, text) = check(
        "carry-on-ok",
        "workflows/one-invoice.yaml",
        "starts-at: match",
        "limits:\n  finishes-within: 7 days\n  when-it-runs-out: carry-on\nstarts-at: match",
    );
    assert!(ok, "{text}");
}

/// #48 with the question its `vendor` stage's failure plan asks moved out of
/// the workflow into `questions/`, written as given.
fn a_failure_plans_question_in_the_workspace(name: &str, extra: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-plan-asks-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join("tests/trees/workflows-48-invoices"), &dst);
    let flow = dst.join("workflows/one-invoice.yaml");
    let text = std::fs::read_to_string(&flow).unwrap();
    let start = text
        .find("  create-the-vendor:\n")
        .expect("fixture drifted");
    let end = start
        + text[start..]
            .find("  posting-failed:\n")
            .expect("fixture drifted");
    let question: String = text[start..end]
        .lines()
        .skip(1)
        .map(|l| format!("{}\n", l.strip_prefix("    ").unwrap_or(l)))
        .collect();
    std::fs::write(&flow, format!("{}{}", &text[..start], &text[end..])).unwrap();
    std::fs::create_dir_all(dst.join("questions")).unwrap();
    std::fs::write(
        dst.join("questions/create-the-vendor.yaml"),
        format!("{question}{extra}"),
    )
    .unwrap();
    dst
}

fn pact_on(verb: &str, root: &Path) -> (bool, String) {
    let out = pact()
        .args([verb, root.to_str().unwrap()])
        .output()
        .expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

#[test]
fn a_question_a_failure_plan_asks_is_the_workflows() {
    // Asked by `if-it-fails.asks:`, it is the workflow's question: written
    // without `if-nobody-answers:`, it loads, and `pact waits` lists the park.
    let root = a_failure_plans_question_in_the_workspace("as-a-workflows", "");
    let (ok, text) = pact_on("check", &root);
    let (_, waits) = pact_on("waits", &root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(ok, "{text}");
    let waits: serde_json::Value = serde_json::from_str(&waits).expect("JSON");
    let park = waits["waits"]
        .as_array()
        .unwrap()
        .iter()
        .find(|w| w["question"] == "create-the-vendor")
        .unwrap_or_else(|| panic!("{waits}"));
    assert_eq!(park["workflow"], "one-invoice", "{park}");
    assert_eq!(park["stage"], "vendor", "{park}");
    assert_eq!(park["nobody-answered"], "stop-and-say-so", "{park}");
    assert_eq!(park["reason"], "waiting-for-a-person", "{park}");
}

#[test]
fn a_question_a_failure_plan_asks_is_held_as_the_workflows() {
    // WF-40 runs on it: `if-nobody-answers:` is refused there.
    let root = a_failure_plans_question_in_the_workspace(
        "with-silence",
        "if-nobody-answers: stop-and-say-so\n",
    );
    let (ok, text) = pact_on("check", &root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/an-agent-only-spelling"),
        "{text}"
    );
    assert!(!text.contains("schema/missing-field"), "{text}");
}
