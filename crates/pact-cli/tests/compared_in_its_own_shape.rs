//! A score against money, or a date against a number, is refused in every
//! position (02W §3 WF-18, §8), over mutations of #48's routing and tiers
//! (`tests/trees/an-invoice-case/`) and of the shipped approval rule.
//!
//! A value is compared in its own shape: the shape is read where what the line
//! looks at is declared — the workflow's `accepts:` (`invoice` is a named shape
//! with `total: money`, `lowest-confidence: number`, `due-on: date`,
//! `arrived-at: time`, `cutoff: time`), the
//! answer of the stage a binding reads, an action's `takes:` — and the figure
//! is read as written (`5000 USD`, `0.85`, `2026-01-01`, `14:30`, `{now-plus: 14 days}`,
//! `{value: <binding>}`). Where the shape is not known before a run, nothing is
//! refused.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

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

fn check_edited(tree: &str, name: &str, file: &str, from: &str, to: &str) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-own-shape-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(tree), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    let out = pact()
        .args(["check", dst.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

const TREE: &str = "tests/trees/an-invoice-case";
const FLOW: &str = "workflows/one-invoice.yaml";
const TOTAL: &str = "{ value: input.invoice.total, less-than: 5000 USD }";
const SCORE: &str = "{ value: input.invoice.lowest-confidence, less-than: 0.85 }";

#[test]
fn a_mismatch_is_refused_in_a_routing_rule() {
    for (name, from, to, says) in [
        (
            "score-money",
            SCORE,
            "{ value: input.invoice.lowest-confidence, less-than: 5000 USD }",
            "`input.invoice.lowest-confidence` is a number and `less-than: 5000 USD` is an amount of money",
        ),
        (
            "money-number",
            TOTAL,
            "{ value: input.invoice.total, less-than: 5000 }",
            "`input.invoice.total` is an amount of money and `less-than: 5000` is a number",
        ),
        (
            "date-number",
            TOTAL,
            "{ value: input.invoice.due-on, less-than: 30 }",
            "`input.invoice.due-on` is a date and `less-than: 30` is a number",
        ),
        (
            "money-now",
            TOTAL,
            "{ value: input.invoice.total, more-than: { now-plus: 14 days } }",
            "`input.invoice.total` is an amount of money and `more-than: {now-plus: 14 days}` is a date",
        ),
        (
            "money-date-binding",
            TOTAL,
            "{ value: input.invoice.total, is: { value: input.invoice.due-on } }",
            "`input.invoice.total` is an amount of money and `is: {value: input.invoice.due-on}` is a date",
        ),
        (
            "money-words",
            TOTAL,
            "{ value: input.invoice.total, contains-any-of: [large] }",
            "`input.invoice.total` is an amount of money and `contains-any-of:` looks for words",
        ),
        (
            "time-number",
            TOTAL,
            "{ value: input.invoice.arrived-at, more-than: 14 }",
            "`input.invoice.arrived-at` is a time of day and `more-than: 14` is a number",
        ),
        (
            "time-date",
            TOTAL,
            "{ value: input.invoice.arrived-at, more-than: 2026-01-01 }",
            "`input.invoice.arrived-at` is a time of day and `more-than: 2026-01-01` is a date",
        ),
        (
            "date-time",
            TOTAL,
            "{ value: input.invoice.due-on, less-than: 14:30 }",
            "`input.invoice.due-on` is a date and `less-than: 14:30` is a time of day",
        ),
        (
            "a-choice-ordered",
            TOTAL,
            "{ value: steps.match.result, more-than: 3 }",
            "`steps.match.result` is some text and `more-than: 3` is a number",
        ),
    ] {
        let (ok, text) = check_edited(TREE, name, FLOW, from, to);
        if name == "a-choice-ordered" {
            // Text keeps its old reading: only money against it is refused.
            assert!(ok, "[{name}] {text}");
            continue;
        }
        assert!(!ok, "[{name}] {text}");
        assert!(
            text.contains("rule: loader/compared-in-the-wrong-shape"),
            "[{name}] {text}"
        );
        assert!(text.contains(says), "[{name}] {text}");
        assert!(
            text.contains("two different kinds of thing"),
            "[{name}] {text}"
        );
    }
}

#[test]
fn a_mismatch_is_refused_in_an_until() {
    let (ok, text) = check_edited(
        TREE,
        "until-date",
        "workflows/wait-for-the-po.yaml",
        "      - { value: steps.look.result, is: matched }\n",
        "      - { value: steps.look.result, is: matched }\n      - { value: input.invoice.due-on, more-than: 5000 USD }\n",
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "`input.invoice.due-on` is a date and `more-than: 5000 USD` is an amount of money"
        ),
        "{text}"
    );
}

#[test]
fn a_mismatch_is_refused_in_an_approval_rule() {
    let (ok, text) = check_edited(
        "examples/refund-desk",
        "policy-date",
        "policies/approvals.yaml",
        "{ tool: payments/issue-refund, arg: amount, more-than: 200 USD }",
        "{ tool: payments/issue-refund, arg: amount, less-than: 2026-01-01 }",
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "`amount` is an amount of money and `less-than: 2026-01-01` is a date"
        ),
        "{text}"
    );
}

#[test]
fn a_figure_in_the_values_own_shape_loads() {
    for (name, from, to) in [
        (
            "date-now",
            TOTAL,
            "{ value: input.invoice.due-on, less-than: { now-plus: 30 days } }",
        ),
        (
            "date-date",
            TOTAL,
            "{ value: input.invoice.due-on, more-than: 2026-01-01 }",
        ),
        (
            "money-binding",
            TOTAL,
            "{ value: input.invoice.total, more-than: { value: input.invoice.total } }",
        ),
        (
            "time-time",
            TOTAL,
            "{ value: input.invoice.arrived-at, more-than: 14:30 }",
        ),
        (
            "time-quoted",
            TOTAL,
            "{ value: input.invoice.arrived-at, less-than: '9:05' }",
        ),
        (
            "time-binding",
            TOTAL,
            "{ value: input.invoice.arrived-at, more-than: { value: input.invoice.cutoff } }",
        ),
        ("empty", TOTAL, "{ value: input.invoice.po, is-empty: yes }"),
        (
            "words",
            TOTAL,
            "{ value: input.invoice.po, contains-any-of: [PO-, X] }",
        ),
        (
            "score",
            SCORE,
            "{ value: input.invoice.lowest-confidence, more-than: 0.5 }",
        ),
    ] {
        let (ok, text) = check_edited(TREE, name, FLOW, from, to);
        assert!(ok, "[{name}] {text}");
    }
}

#[test]
fn an_approval_rule_compares_with_a_figure_written_there() {
    // A gate decides at the call, from the call: no other value to read and no
    // journaled clock to count from.
    for (name, figure) in [
        ("now", "{ now-plus: 3 days }"),
        ("value", "{ value: run-inputs.customer-id }"),
    ] {
        let (ok, text) = check_edited(
            "examples/refund-desk",
            &format!("policy-{name}"),
            "policies/approvals.yaml",
            "{ tool: payments/issue-refund, arg: amount, more-than: 200 USD }",
            &format!("{{ tool: payments/issue-refund, arg: amount, more-than: {figure} }}"),
        );
        assert!(!ok, "[{name}] {text}");
        assert!(
            text.contains("a gate has no other value to read and no clock to count from"),
            "[{name}] {text}"
        );
        assert!(
            text.contains("fix: Write the figure itself — `more-than: 200 USD`"),
            "[{name}] {text}"
        );
    }
}
