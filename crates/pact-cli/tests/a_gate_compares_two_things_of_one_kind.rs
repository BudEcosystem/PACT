//! An approval gate that could only ever compare money (A3).
//!
//! Two defects, one field.
//!
//! **(a) `is:` could not be written.** `when-this.arg` carried
//! `needs-also: [more-than]`, and `needs-also:` fires on PRESENCE and names ONE
//! field — so `{tool: t/go, arg: reason, is: fraud}` was refused with *"'arg' is
//! set, but 'more-than' is not"*, a rule the author had written correctly. A
//! gate on a customer tier, a country or a reason code was unwritable.
//!
//! **(b) The figure was not held against the argument.** `more-than:` was
//! `type: money`, so a lead score gated with `more-than: 80` was told *"Write it
//! like `0.05 USD`"* — and doing exactly what that said printed *"OK — loaded
//! cleanly"*, after which `pact waits` showed a live thirty-minute human gate
//! comparing a score to dollars.
//!
//! The shape cannot be stated in the schema, because it is the shape of an
//! argument declared in a different document. So the schema is permissive and
//! the loader, which reads both, decides.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

/// A copy of the worked example whose `payments` also takes a score, and whose
/// first approval rule is written as given.
fn gated_by(name: &str, rule: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-gate-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&repo().join("examples/refund-desk"), &dst);

    let tools = dst.join("tools/payments.yaml");
    let text = std::fs::read_to_string(&tools).unwrap();
    assert!(text.contains("      amount: money"), "the fixture drifted");
    // `inspects:` has to grow with `takes:`, or the pre-existing check that a
    // rule may only look at what the action offers fires first and this file
    // ends up testing that instead.
    let text = text.replace(
        "      amount: money",
        "      amount: money\n      score: number",
    );
    assert!(text.contains("inspects: [amount]"), "the fixture drifted");
    std::fs::write(
        &tools,
        text.replace("inspects: [amount]", "inspects: [amount, score]"),
    )
    .unwrap();

    let policy = dst.join("policies/approvals.yaml");
    let text = std::fs::read_to_string(&policy).unwrap();
    let original = "{ tool: payments/issue-refund, arg: amount, more-than: 200 USD }";
    assert!(text.contains(original), "the fixture drifted");
    std::fs::write(&policy, text.replace(original, rule)).unwrap();
    dst
}

fn check(root: &std::path::Path) -> String {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}

#[test]
fn a_gate_can_compare_something_that_is_not_money() {
    let root = gated_by(
        "is",
        "{ tool: payments/issue-refund, arg: score, is: high }",
    );
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "a tier, a country, a reason code — none of them is a number:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_gate_can_compare_against_several_values() {
    let root = gated_by(
        "isoneof",
        "{ tool: payments/issue-refund, arg: score, is-one-of: [high, urgent] }",
    );
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_rule_that_says_what_to_look_at_and_never_what_to_look_for_is_refused() {
    // `needs-one-of:`. `needs-also:` names one field and fires on presence, so
    // it could not say "exactly one of these three".
    let root = gated_by("bare", "{ tool: payments/issue-refund, arg: amount }");
    let text = check(&root);
    assert!(text.contains("schema/missing-one-of"), "{text}");
    assert!(
        text.contains("more-than"),
        "the fix lists the ways to compare:\n{text}"
    );
    assert!(text.contains("is-one-of"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_score_gated_by_an_amount_of_money_is_refused() {
    let root = gated_by(
        "scoreusd",
        "{ tool: payments/issue-refund, arg: score, more-than: 200 USD }",
    );
    let text = check(&root);
    assert!(
        text.contains("loader/compared-in-the-wrong-shape"),
        "{text}"
    );
    assert!(text.contains("two different kinds of thing"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_amount_of_money_gated_by_a_bare_number_is_refused_too() {
    // The mirror, and the one a reader-only check would miss: a bare `200`
    // parses as an integer, not a string.
    let root = gated_by(
        "amountbare",
        "{ tool: payments/issue-refund, arg: amount, more-than: 200 }",
    );
    let text = check(&root);
    assert!(
        text.contains("loader/compared-in-the-wrong-shape"),
        "{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_figure_written_the_way_its_argument_is_declared_is_left_alone() {
    for (name, rule) in [
        (
            "okmoney",
            "{ tool: payments/issue-refund, arg: amount, more-than: 200 USD }",
        ),
        (
            "oknumber",
            "{ tool: payments/issue-refund, arg: score, more-than: 80 }",
        ),
    ] {
        let root = gated_by(name, rule);
        let out = pact()
            .args(["check", root.to_str().unwrap()])
            .output()
            .expect("runs");
        assert!(
            out.status.success(),
            "{rule} is correct:\n{}",
            String::from_utf8_lossy(&out.stdout)
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_shipped_example_gains_nothing_from_either_half() {
    let path = repo().join("examples/refund-desk");
    let out = pact()
        .args(["check", path.to_str().unwrap()])
        .output()
        .expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(out.status.success(), "{text}");
    assert!(!text.contains("compared-in-the-wrong-shape"), "{text}");
    assert!(!text.contains("missing-one-of"), "{text}");
}

fn copy_dir(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}
