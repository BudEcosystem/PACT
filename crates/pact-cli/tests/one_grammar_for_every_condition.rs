//! `when-this` is read by one function wherever a condition is written, and a
//! mistake in it is told in the same words in every position (02W §2.6, §8,
//! F1 reopened).
//!
//! Three positions exist today: an approval rule's `when:` (the shipped
//! `examples/refund-desk`), a routing rule's `when:` and a repeat's `until:`
//! (`tests/trees/an-invoice-case/`, #48's routing and tiers). A port's
//! `only-when:` goes through the same `conditions::line` when ports gain it.
//! The same mistake is written into each and the diagnostics are compared with
//! the name of what the line looks at taken out — that name is the only thing
//! that differs, because it is what the author wrote.
//!
//! Mutation: give `conditions::line` a position-specific sentence for the
//! shape refusal (or route `until:` around it) and these go red.

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

/// A copy of `tree` with `from` replaced by `to` in `file`.
fn edited(tree: &str, name: &str, file: &str, from: &str, to: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-one-grammar-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(tree), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    dst
}

/// The `error:` and `fix:` lines of every `rule` diagnostic, with `` `looked_at` ``
/// written as `` `<it>` ``.
fn told(root: &Path, rule: &str, looked_at: &str) -> Vec<(String, String)> {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let text = String::from_utf8_lossy(&out.stdout).into_owned();
    assert!(!out.status.success(), "the mistake loaded:\n{text}");
    let lines: Vec<&str> = text.lines().collect();
    let mut found = Vec::new();
    for (i, l) in lines.iter().enumerate() {
        if l.trim() != format!("rule: {rule}") {
            continue;
        }
        let start = lines[..i]
            .iter()
            .rposition(|x| x.starts_with("error:"))
            .expect("an error line");
        let fix = lines[start..i]
            .iter()
            .find(|x| x.trim_start().starts_with("fix:"))
            .expect("a fix line");
        let blank = |s: &str| s.trim().replace(&format!("`{looked_at}`"), "`<it>`");
        found.push((blank(lines[start]), blank(fix)));
    }
    assert!(!found.is_empty(), "no `{rule}` in:\n{text}");
    found
}

const POLICY: (&str, &str, &str) = (
    "examples/refund-desk",
    "policies/approvals.yaml",
    "{ tool: payments/issue-refund, arg: amount, more-than: 200 USD }",
);
const ROUTE: (&str, &str, &str) = (
    "tests/trees/an-invoice-case",
    "workflows/one-invoice.yaml",
    "{ value: input.invoice.total, less-than: 5000 USD }",
);
const UNTIL: (&str, &str, &str) = (
    "tests/trees/an-invoice-case",
    "workflows/wait-for-the-po.yaml",
    "      - { value: steps.look.result, is: matched }\n",
);

/// The same mistake in all three positions: `(tree, file, line, replacement)`.
fn everywhere(
    policy: &str,
    route: &str,
    until: &str,
) -> [(&'static str, &'static str, &'static str, String); 3] {
    [
        (POLICY.0, POLICY.1, POLICY.2, policy.to_string()),
        (ROUTE.0, ROUTE.1, ROUTE.2, route.to_string()),
        // An `until:` keeps a line that reads the round, so WF-14 stays quiet.
        (
            UNTIL.0,
            UNTIL.1,
            UNTIL.2,
            format!("{}      - {until}\n", UNTIL.2),
        ),
    ]
}

#[test]
fn a_comparison_in_the_wrong_shape_is_told_the_same_way_everywhere() {
    let cases = everywhere(
        "{ tool: payments/issue-refund, arg: amount, less-than: 2026-01-01 }",
        "{ value: input.invoice.total, less-than: 2026-01-01 }",
        "{ value: input.invoice.total, less-than: 2026-01-01 }",
    );
    let looked_at = ["amount", "input.invoice.total", "input.invoice.total"];
    let mut said = Vec::new();
    for (i, (tree, file, from, to)) in cases.iter().enumerate() {
        let root = edited(tree, &format!("shape-{i}"), file, from, to);
        let got = told(&root, "loader/compared-in-the-wrong-shape", looked_at[i]);
        assert_eq!(got.len(), 1, "one mistake, one message: {got:?}");
        said.push(got[0].clone());
        let _ = std::fs::remove_dir_all(&root);
    }
    assert_eq!(
        said[0].0,
        "error: `<it>` is an amount of money and `less-than: 2026-01-01` is a date — so the \
         condition compares two different kinds of thing."
    );
    assert!(said.iter().all(|s| s == &said[0]), "{said:#?}");
}

#[test]
fn a_line_that_looks_at_two_things_or_none_is_told_the_same_way_everywhere() {
    for (mistake, policy, workflow) in [
        (
            "both",
            "{ tool: payments/issue-refund, value: run-inputs.customer-id, is: x }",
            "{ tool: netsuite/match-po, value: steps.match.result, is: x }",
        ),
        ("neither", "{ is: x }", "{ is: x }"),
    ] {
        let until_line = workflow.replace("steps.match.result", "steps.look.result");
        let cases = everywhere(policy, workflow, &until_line);
        let mut said = Vec::new();
        for (i, (tree, file, from, to)) in cases.iter().enumerate() {
            let root = edited(tree, &format!("{mistake}-{i}"), file, from, to);
            said.extend(told(&root, "loader/compared-in-the-wrong-shape", "\u{0}"));
            let _ = std::fs::remove_dir_all(&root);
        }
        assert_eq!(
            said.len(),
            3,
            "[{mistake}] one message per position: {said:#?}"
        );
        assert!(said.iter().all(|s| s == &said[0]), "[{mistake}] {said:#?}");
        assert_eq!(
            said[0].1,
            "fix: Write exactly one of the two: `tool:` in an approval rule, `value:` everywhere \
             else."
        );
    }
}

#[test]
fn a_figure_that_is_no_figure_is_told_the_same_way_in_every_workflow_position() {
    let route = edited(
        ROUTE.0,
        "nan-route",
        ROUTE.1,
        ROUTE.2,
        "{ value: input.invoice.total, less-than: NaN USD }",
    );
    let until = edited(
        UNTIL.0,
        "nan-until",
        UNTIL.1,
        UNTIL.2,
        &format!(
            "{}      - {{ value: input.invoice.total, less-than: NaN USD }}\n",
            UNTIL.2
        ),
    );
    let a = told(&route, "loader/threshold-is-not-a-figure", "\u{0}");
    let b = told(&until, "loader/threshold-is-not-a-figure", "\u{0}");
    assert_eq!(a, b);
    assert!(
        a[0].0
            .contains("`less-than: NaN USD` is not a figure at all"),
        "{a:?}"
    );
    for root in [route, until] {
        let _ = std::fs::remove_dir_all(root);
    }
}

#[test]
fn a_call_is_looked_at_only_by_an_approval_rule_and_a_value_only_elsewhere() {
    let policy = edited(
        POLICY.0,
        "value-in-policy",
        POLICY.1,
        POLICY.2,
        "{ value: run-inputs.customer-id, is: x }",
    );
    let (error, fix) = told(&policy, "loader/compared-in-the-wrong-shape", "\u{0}").remove(0);
    assert!(
        error.contains("An approval rule is about a call"),
        "{error}"
    );
    assert!(fix.contains("`tool: <tool>/<action>`"), "{fix}");
    let route = edited(
        ROUTE.0,
        "tool-in-route",
        ROUTE.1,
        ROUTE.2,
        "{ tool: netsuite/match-po, arg: po, is: x }",
    );
    let (error, fix) = told(&route, "loader/compared-in-the-wrong-shape", "\u{0}").remove(0);
    assert!(error.contains("nothing here is a call"), "{error}");
    assert!(fix.contains("Write `value:` instead"), "{fix}");
    for root in [policy, route] {
        let _ = std::fs::remove_dir_all(root);
    }
}

#[test]
fn every_position_loads_clean_as_shipped() {
    for tree in [POLICY.0, ROUTE.0] {
        let out = pact()
            .args([
                "check",
                repo().join(tree).to_str().unwrap(),
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
}
