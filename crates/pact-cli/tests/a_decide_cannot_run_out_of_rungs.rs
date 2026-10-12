//! A `decide` cannot run out of rungs (02W §3 WF-15, WF-16, WF-17, §8).
//!
//! The rules half, over #48's routing and tiers (`tests/trees/an-invoice-case/`):
//! a decision by written rules always chooses — its last rung ends with an
//! "otherwise" (a rule with no `when:`), so a case none of the rules fits still
//! has a label, and every label a rule picks is one the stage can go to.
//!
//! The agent and person half, over #48's attachment sorter as 02W §5.2 prints
//! it (`tests/trees/workflows-48-invoices/`, `ap-inbox`'s `sort`): a decision
//! model under 85% sure passes the decision to a clerk, so the decide never
//! runs out; an agent that may pass the decision on is never the last rung; a
//! language model has no honest score to be unsure below; a rung is one way of
//! deciding, a person decides last, and an agent and a question each pick
//! exactly the labels the stage goes to. A decision model needs no
//! instructions. 02W §8 names #8 and #27 as the fixtures; neither tree is in
//! PACT, and #48's sorter is the same construct (rules, a decision model, a
//! person).

use std::path::{Path, PathBuf};
use std::process::Command;

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

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

const FLOW: &str = "workflows/one-invoice.yaml";

fn check_edited(name: &str, from: &str, to: &str) -> (bool, String) {
    edited(name, "an-invoice-case", &[(FLOW, from, to)])
}

/// `pact check --deny-warnings` on a copy of `tree` with each `(file, from,
/// to)` edit made once.
fn edited(name: &str, tree: &str, edits: &[(&str, &str, &str)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-rungs-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join("tests/trees").join(tree), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(text.contains(from), "fixture drifted: {from:?}");
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dst.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

const OTHERWISE: &str = "          - choose: owner\n";

#[test]
fn rules_with_no_otherwise_are_refused() {
    let (ok, text) = check_edited(
        "no-otherwise",
        OTHERWISE,
        "          - when: [{ value: input.invoice.total, less-than: 50000 USD }]\n            choose: owner\n",
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-decide-that-can-run-out-of-rungs"),
        "{text}"
    );
    assert!(
        text.contains(
            "'tiers' ends with written rules, and every one of them has a `when:` — so a case \
             none of them fits is decided by nobody and the run stops there."
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "fix: End with an \"otherwise\" rule — a last rule with no `when:`, `- choose: auto`"
        ),
        "{text}"
    );
}

#[test]
fn a_decide_with_no_rung_is_refused() {
    let flow =
        std::fs::read_to_string(repo().join("tests/trees/an-invoice-case").join(FLOW)).unwrap();
    let start = flow.find("  tiers:\n").unwrap();
    let by = start + flow[start..].find("    by:\n").unwrap();
    let end = by + flow[by..].find("\n\n").unwrap() + 1;
    let (ok, text) = check_edited("no-rung-at-all", &flow[by..end], "");
    assert!(!ok, "{text}");
    assert!(
        text.contains("'tiers' decides with no rung at all, so nothing ever picks a label."),
        "{text}"
    );
    assert!(
        text.contains("fix: Add `by:` with written rules that end in an \"otherwise\""),
        "{text}"
    );
}

#[test]
fn a_label_with_nowhere_to_go_is_refused_and_the_nearest_offered() {
    let (ok, text) = check_edited(
        "label",
        "            choose: auto\n",
        "            choose: autp\n",
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-label-with-nowhere-to-go"),
        "{text}"
    );
    assert!(
        text.contains(
            "A rule of 'tiers' chooses 'autp', and 'tiers' chooses between 'auto', 'owner' — so \
             when this rule holds, the run has nowhere to go."
        ),
        "{text}"
    );
    assert!(
        text.contains("fix: Choose one of the labels offered: `auto`, `owner`"),
        "{text}"
    );
}

#[test]
fn an_otherwise_may_be_written_with_an_empty_when() {
    let (ok, text) = check_edited(
        "empty-when",
        OTHERWISE,
        "          - when: []\n            choose: owner\n",
    );
    assert!(ok, "{text}");
}

#[test]
fn the_tree_decides_every_case_and_loads_clean() {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args([
            "check",
            repo().join("tests/trees/an-invoice-case").to_str().unwrap(),
            "--deny-warnings",
        ])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stdout)
    );
}

// ───────────────────────────────────────────── the agent and the person rungs

const INBOX: &str = "workflows-48-invoices";
const SORT: &str = "workflows/ap-inbox.yaml";
const SORTER: &str = "agents/attachment-sorter/agent.yaml";
const CATALOGUE: &str = "models/catalog.yaml";
const PERSON: &str = "          - asks: what-is-this-attachment\n";
const UNSURE: &str = "            if-unsure-below: 85%\n";
const LABELS: &str = "  label: one of invoice, other\n";

#[test]
fn a_decision_model_then_a_person_decides_every_case_and_needs_no_instructions() {
    // 02W §5.2 as printed: the sorter is an agent on a `kind: decision` row,
    // with no `instructions:` at all.
    let (ok, text) = edited("as-printed", INBOX, &[]);
    assert!(ok, "{text}");
    assert!(!text.contains("'instructions'"), "{text}");
}

#[test]
fn a_decision_model_that_may_pass_the_decision_on_is_not_the_last_rung() {
    let (ok, text) = edited("no-person", INBOX, &[(SORT, PERSON, "")]);
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'sort' ends with 'attachment-sorter', which passes the decision on when it is \
             unsure — so a case it is unsure of is decided by nobody and the run stops there."
        ),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/a-decide-that-can-run-out-of-rungs"),
        "{text}"
    );
    assert!(
        text.contains("fix: End with a person rung after it — `- asks: <a question>`"),
        "{text}"
    );
}

#[test]
fn an_agent_that_may_say_not_sure_is_not_the_last_rung() {
    let (ok, text) = edited(
        "not-sure-last",
        INBOX,
        &[
            (SORT, PERSON, ""),
            (SORT, UNSURE, ""),
            (SORTER, LABELS, "  label: one of invoice, other, not-sure\n"),
        ],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("'sort' ends with 'attachment-sorter', which may answer `not-sure`"),
        "{text}"
    );
}

#[test]
fn not_sure_passes_the_decision_on_to_a_rung_after_it() {
    let (ok, text) = edited(
        "not-sure-then-person",
        INBOX,
        &[(SORTER, LABELS, "  label: one of invoice, other, not-sure\n")],
    );
    assert!(ok, "{text}");
}

#[test]
fn sure_only_a_decision_model_can_be() {
    let (ok, text) = edited(
        "language",
        INBOX,
        &[(CATALOGUE, "kind: decision", "kind: language")],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/sure-only-a-decision-model-can-be"),
        "{text}"
    );
    assert!(
        text.contains(
            "'sort' passes the decision on when 'attachment-sorter' is under 85% sure, and \
             'attachment-sorter' runs on a language model, which has no honest score — so the \
             line can never be kept."
        ),
        "{text}"
    );
    assert!(
        text.contains("fix: Delete `if-unsure-below:` and add `not-sure` to the agent's"),
        "{text}"
    );
    // ...and a language model is given words: the instructions are owed again.
    assert!(
        text.contains("An agent must have 'instructions'."),
        "{text}"
    );
}

#[test]
fn an_agent_that_picks_other_labels_has_nowhere_to_go() {
    let (ok, text) = edited(
        "labels",
        INBOX,
        &[(SORTER, LABELS, "  label: one of invoice, receipt\n")],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'sort' asks the agent 'attachment-sorter', which answers `label: one of invoice, \
             receipt`, and 'sort' chooses between 'invoice', 'other' — so 'receipt' has nowhere \
             to go, and 'other' is never picked."
        ),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/a-label-with-nowhere-to-go"),
        "{text}"
    );
}

#[test]
fn a_person_may_not_say_not_sure() {
    let (ok, text) = edited(
        "person-unsure",
        INBOX,
        &[(
            SORT,
            "      label: one of invoice, other\n",
            "      label: one of invoice, other, not-sure\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("'sort' asks the question 'what-is-this-attachment'"),
        "{text}"
    );
    assert!(text.contains("'not-sure' has nowhere to go"), "{text}");
}

#[test]
fn a_person_decides_last() {
    let (ok, text) = edited(
        "person-first",
        INBOX,
        &[(
            SORT,
            "          - agent: attachment-sorter\n            if-unsure-below: 85%\n          - asks: what-is-this-attachment\n",
            "          - asks: what-is-this-attachment\n          - agent: attachment-sorter\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'sort' asks a person in a rung that is not its last, and a person always decides — \
             so the rungs after it are never tried."
        ),
        "{text}"
    );
    assert!(text.contains("rule: loader/a-rung-out-of-order"), "{text}");
}

#[test]
fn a_rung_is_one_way_of_deciding() {
    let (ok, text) = edited(
        "two-ways",
        INBOX,
        &[(SORT, PERSON, "            asks: what-is-this-attachment\n")],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "A rung of 'sort' writes `agent:` and `asks:`, and a rung is one way of deciding — so \
             nothing says which is tried first."
        ),
        "{text}"
    );
    assert!(text.contains("rule: loader/one-rung-one-way"), "{text}");
}

#[test]
fn the_first_rung_has_nobody_to_disagree_with() {
    let (ok, text) = edited(
        "disagrees",
        INBOX,
        &[(
            SORT,
            UNSURE,
            "            if-unsure-below: 85%\n            if-it-disagrees: go-on\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "The first rung of 'sort' writes `if-it-disagrees:`, and there is no rung before it \
             to disagree with."
        ),
        "{text}"
    );
}

#[test]
fn an_agent_that_goes_on_when_it_disagrees_is_not_the_last_rung() {
    // Rules first, then the sorter, which passes the decision on when it
    // picks another label than the rules did: as the last rung, to nobody.
    let (ok, text) = edited(
        "disagrees-last",
        INBOX,
        &[
            (SORT, PERSON, ""),
            (
                SORT,
                "          - agent: attachment-sorter\n            if-unsure-below: 85%\n",
                "          - rules:\n              - when: [{ value: item.name, is: invoice.pdf }]\n                choose: invoice\n          - agent: attachment-sorter\n            if-it-disagrees: go-on\n",
            ),
        ],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'sort' ends with 'attachment-sorter', which passes the decision on when it \
             disagrees with the rung before it — so a case they disagree on is decided by nobody \
             and the run stops there."
        ),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/a-decide-that-can-run-out-of-rungs"),
        "{text}"
    );
}

#[test]
fn an_agent_that_goes_on_when_it_disagrees_passes_to_a_rung_after_it() {
    let (ok, text) = edited(
        "disagrees-then-person",
        INBOX,
        &[(
            SORT,
            "          - agent: attachment-sorter\n            if-unsure-below: 85%\n",
            "          - rules:\n              - when: [{ value: item.name, is: invoice.pdf }]\n                choose: invoice\n          - agent: attachment-sorter\n            if-unsure-below: 85%\n            if-it-disagrees: go-on\n",
        )],
    );
    assert!(ok, "{text}");
}
