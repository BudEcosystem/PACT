//! **`inspects:` — a field that was read by nobody, held where the author is.**
//!
//! `action.inspects:` says, in its own help, that it names *"the arguments an
//! approval rule is allowed to look at"*. Nothing anywhere enforced the word
//! *allowed*.
//!
//! Two halves, both measured on the worked example before this round:
//!
//! * **Check time.** A rule whose `arg:` was outside the action's `inspects:`
//!   produced `loader/argument-not-offered-for-inspection`, a **warning**, so
//!   `pact check` printed the sentence and exited **0** — while its sibling one
//!   branch up, `loader/no-such-argument-to-look-at`, has always been an error
//!   for the same stated consequence. The rule had no test at all.
//! * **Run time.** The sentence said *"so nothing is compared and nobody is
//!   asked"*, which described something that could not happen: no code in either
//!   language read `inspects:`. With `inspects: [order-number]` and with
//!   `inspects: [amount]`, the identical 300 USD refund produced the identical
//!   `Question`.
//!
//! It now bites in both places, and they agree: `questions._atom_stops` refuses
//! to read an argument the action does not offer, and a condition PACT may not
//! evaluate **stops** the call — the direction the neighbouring
//! malformed-threshold rule already settled, because turning a mistake into a
//! disabled gate is the one way this area must never fail. `pact check` refuses
//! the tree so the author hears about it before a customer is waiting, rather
//! than by watching every call park.
//!
//! Driven through the real binary against the real worked example with one line
//! edited, for the reason `money_that_moves_with_nobody_asked.rs` gives: what is
//! proved is that the author's own line arrives.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// A copy of the worked example with one line of one file replaced.
fn edited(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-inspects-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|_| panic!("{file} is there"));
    assert!(text.contains(from), "fixture drifted: {file} no longer contains `{from}`");
    std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
    }
}

fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

#[test]
fn a_rule_looking_outside_the_inspects_line_fails_the_command_the_author_runs() {
    // `tools/payments.yaml` writes `inspects: [amount]`. Point the money rule at
    // the order number instead and the gate is asked to compare a value it is
    // not allowed to read. This printed the sentence and exited 0 before.
    let root = edited(
        "outside",
        "policies/approvals.yaml",
        "arg: amount, more-than: 200 USD",
        "arg: order-number, more-than: 200 USD",
    );
    let (ok, text) = check(&root);

    assert!(!ok, "a warning exits 0, and this is the rule that stops a refund:\n{text}");
    assert!(text.contains("rule: loader/argument-not-offered-for-inspection"), "{text}");
    assert!(text.contains("policies/approvals.yaml:"), "must name the line: {text}");
    assert!(
        text.contains("inspects:") && text.contains("tools/payments.yaml"),
        "the fix has to be typeable, and it has to say which file: {text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_sentence_says_what_the_gate_really_does_and_not_the_opposite() {
    // The message used to promise *"nothing is compared and nobody is asked"* —
    // a fail-open, and untrue twice over, because nothing read the line at all.
    // What really happens is the other way round: the author's figure stops
    // governing and every call to that action waits.
    let root = edited(
        "wording",
        "policies/approvals.yaml",
        "arg: amount, more-than: 200 USD",
        "arg: order-number, more-than: 200 USD",
    );
    let (_, text) = check(&root);

    assert!(text.contains("stops and asks"), "{text}");
    assert!(
        !text.contains("nobody is asked"),
        "a diagnostic that describes a consequence the runtime does not have is the \
         defect, not the report of it:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn no_sentence_about_inspects_assumes_programming_knowledge() {
    // D13's reader is a support lead. The bar every diagnostic in this project
    // holds, applied to the one this round changes.
    let root = edited(
        "jargon",
        "policies/approvals.yaml",
        "arg: amount, more-than: 200 USD",
        "arg: order-number, more-than: 200 USD",
    );
    let (_, text) = check(&root);
    let lower = text.to_lowercase();
    for word in [
        "enum", "variant", "deserialize", "serde", "unwrap", "panic", "trait", "struct",
        "vec<", "option<", "predicate", "atom", "boolean", "null", "assertion", "invariant",
    ] {
        assert!(!lower.contains(word), "message assumes programming knowledge ('{word}'):\n{text}");
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn taking_the_inspects_line_away_altogether_leaves_the_same_rule_alone() {
    // The permission is the AUTHOR'S line, and most tool files have not written
    // one. An absent `inspects:` must never be read as "no argument may be
    // looked at", or every gate in every workspace that has not written it would
    // start stopping everything.
    let root = edited("no-line", "tools/payments.yaml", "\n    inspects: [amount]", "");
    let (ok, text) = check(&root);

    assert!(ok, "an action that offers nothing for inspection restricts nothing:\n{text}");
    assert!(!text.contains("argument-not-offered-for-inspection"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_worked_example_reads_only_what_its_own_tool_file_offers() {
    // The floor. `policies/approvals.yaml` looks at `amount`, and
    // `tools/payments.yaml` offers `amount`. A false positive on the flagship
    // example costs an author their trust in every other line the tool prints.
    let (ok, text) = check(&example());
    assert!(ok, "the worked example must load:\n{text}");
    assert!(!text.contains("argument-not-offered-for-inspection"), "{text}");
}
