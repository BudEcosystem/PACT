//! End-to-end: an action that moves money with no rule naming it must be said
//! out loud by the one command a non-technical author actually runs.
//!
//! `spends-money:`' own help promises the call is *"routed through your approval
//! policy"*. Whether it is, is a fact about a **different** document — the policy
//! the agent's `policy:` line points at, naming `<tool>/<action>` — so nothing
//! the schema can say about a field reaches it, and for a round the only thing
//! that decided it was **running the agent**: `_money_moving` in
//! `adapters/python/src/pact_adapters/ir.py` put the sentence on
//! `RunResult.money_moving`, a field of a result object, in another language, in
//! a process D13's reader never starts. An author who never runs it never learns.
//!
//! Reproduced before this test existed: delete the two `payments/issue-refund`
//! rules from `examples/refund-desk/policies/approvals.yaml` and
//! `pact check examples/refund-desk` printed *"OK — … loaded cleanly (489
//! settings)"* and exited 0.
//!
//! These tests drive the real binary against the **real worked example**, edited
//! by one line, for the reason `authoring_surface.rs`' `broken()` helper does:
//! what is being proved is that the author's own `spends-money: yes` reaches the
//! rule, with nothing passed and no object built by hand. A fixture written from
//! scratch would prove the walk works and say nothing about whether the shipped
//! tree's line arrives. The unit tests live beside the walk in
//! `pact-loader/src/money.rs`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// The two rules in the shipped example that name the money-moving action.
///
/// Written out in full so that an edit to the worked example which changes them
/// fails this test loudly, rather than silently leaving it asserting nothing.
/// The opening quote is on the same line as the first setting on purpose: a
/// `\` line continuation eats the leading indentation as well as the newline,
/// which matched two characters short and left the file unparseable.
const GUARDED: &str = "  - when:
      - { tool: payments/issue-refund, arg: amount, more-than: 200 USD }
    because: a refund over 200 USD is a management decision
    question: is-this-ok

  - when:
      - { tool: payments/issue-refund, arg: amount, more-than: 500 USD }
    because: above 500 USD a person sets the figure, rather than approving one the model chose
    question: how-much-to-refund

";

/// A copy of the worked example with both money rules taken out — the exact
/// edit that reproduced the hole. Everything else is the author's own tree:
/// their `uses:` line, their `spends-money: yes`, their `policy:` line.
fn ungoverned(name: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-money-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join("policies/approvals.yaml");
    let text = std::fs::read_to_string(&p).expect("the worked example has an approval policy");
    assert!(
        text.contains(GUARDED),
        "fixture drifted: the two money rules are not as written"
    );
    std::fs::write(&p, text.replace(GUARDED, "")).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
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

fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

/// Just the paragraph about money, out of everything `check` printed.
fn about_money(text: &str) -> String {
    text.split("\n\n")
        .filter(|p| p.contains("loader/money-moves-with-nobody-asked"))
        .collect::<Vec<_>>()
        .join("\n\n")
}

#[test]
fn the_worked_example_names_its_own_money_moving_action_so_nothing_is_said_about_it() {
    // The half that matters most, and the one the shipped tree is the proof of:
    // `policies/approvals.yaml` names `payments/issue-refund` twice, so a
    // correct workspace must not be warned. A false positive on the flagship
    // example costs an author their trust in every other line the tool prints.
    let (ok, text) = check(&example());
    assert!(ok, "the worked example must load:\n{text}");
    assert!(
        !text.contains("money-moves-with-nobody-asked"),
        "the example guards its own refund; nothing may be said:\n{text}"
    );
    assert!(text.contains("loaded cleanly"), "{text}");
}

#[test]
fn an_action_that_moves_money_and_no_rule_names_is_warned_about_at_check_time() {
    // The exact edit that reproduced the hole, through the author's own files
    // and the author's own command. Nothing is constructed here — `uses:`,
    // `spends-money:` and `policy:` are read off the tree by the loader, which
    // is the only thing that proves the line the author typed reaches the rule.
    let (_, text) = check(&ungoverned("ungoverned"));
    let said = about_money(&text);
    assert!(
        !said.is_empty(),
        "an ungated spend must be said out loud:\n{text}"
    );

    // Where: the file and line of the `spends-money: yes` itself, not of the
    // policy that is missing a rule — the author has to see the tick that made
    // the promise.
    assert!(
        said.contains("tools/payments.yaml:34:5"),
        "must name file and line: {said}"
    );
    assert!(
        said.contains("34 |     spends-money: yes"),
        "must show the line: {said}"
    );
    // What: in plain words, naming the agent that can call it.
    //
    // The quoted tick is the author's own word, and this file is the reason to
    // check it against a real tree rather than a fixture: recovering it by
    // slicing the source at the span looked right and was not — `Span` counts
    // CHARACTERS, and the three em-dashes in this very file's comments put the
    // slice six bytes out, so the sentence read `spends-money: one`, the middle
    // of the word `money` on the line above.
    assert!(
        said.contains("`spends-money: yes` on `issue-refund`"),
        "{said}"
    );
    assert!(said.contains("`refund-desk` can call it"), "{said}");
    assert!(
        said.contains("money moves without anybody being asked"),
        "{said}"
    );
    // How: a line the author can type, with both halves the rule needs.
    assert!(
        said.contains("`- when: [{ tool: payments/issue-refund }]`"),
        "typeable: {said}"
    );
    assert!(
        said.contains("`because:`") && said.contains("`question:`"),
        "{said}"
    );
}

#[test]
fn money_moving_with_nobody_asked_is_a_warning_because_a_workspace_may_mean_it() {
    // Not an error. A tree may genuinely intend an ungated spend — an internal
    // transfer, a top-up under a figure nobody reviews, a policy being written
    // next — and refusing to load would make that unauthorable, which is the
    // wrong ceiling. What it may never be is silent.
    let (ok, text) = check(&ungoverned("warning-not-error"));
    let said = about_money(&text);
    assert!(
        !said.is_empty(),
        "an ungated spend must be said out loud:\n{text}"
    );
    assert!(said.starts_with("warning:"), "not an error: {said}");
    assert!(ok, "an ungated spend must still load, and exit 0:\n{text}");
    assert!(
        text.contains("loaded with"),
        "counted as a warning, not a problem: {text}"
    );
}

#[test]
fn the_warning_about_money_uses_no_words_a_non_coder_would_have_to_look_up() {
    let (_, text) = check(&ungoverned("plain"));
    let said = about_money(&text).to_lowercase();
    assert!(!said.is_empty());
    for jargon in [
        "boolean",
        "predicate",
        "null",
        "field type",
        "schema",
        "validate",
        "traversal",
        "cross-document",
        "identifier",
        "namespace",
        "resolve",
        "invariant",
        "enum",
    ] {
        assert!(
            !said.contains(jargon),
            "the sentence leaked '{jargon}':\n{said}"
        );
    }
}

#[test]
fn the_indefinite_articles_in_the_warning_agree_with_the_words_after_them() {
    // The bar `pact-schema/tests/diagnostics_read_as_english.rs` sets, applied
    // to this sentence: *"A agent must have a 'description'"* is the first thing
    // a D13 reader ever got from the tool on the day they were already wrong
    // about something, and a diagnostic about money is read on a worse day than
    // that. No article may sit in front of a plural, either — `a policies` is
    // not fixed by `an policies`.
    let (_, text) = check(&ungoverned("english"));
    let said = about_money(&text);
    assert!(!said.is_empty());
    let words: Vec<&str> = said.split_whitespace().collect();
    for pair in words.windows(2) {
        let article = pair[0]
            .trim_matches(|c: char| !c.is_alphanumeric())
            .to_lowercase();
        if article != "a" && article != "an" {
            continue;
        }
        let word = pair[1]
            .trim_matches(|c: char| !c.is_alphanumeric())
            .to_lowercase();
        if word.is_empty() {
            continue;
        }
        let vowel = word.starts_with(['a', 'e', 'i', 'o', 'u']);
        assert_eq!(
            article,
            if vowel { "an" } else { "a" },
            "'{article} {word}' does not agree, in:\n{said}"
        );
        // A plural takes no article at all: `an policies` is not a fix for
        // `a policies`. `ss` is the exception — `business`, `address`.
        assert!(
            !word.ends_with('s') || word.ends_with("ss"),
            "nothing may be '{article} {word}', in:\n{said}"
        );
    }
}

// ─────────────────────────────────────────────────── B12: inferred from the type

/// A copy of the worked example with `spends-money:` deleted from `payments`.
fn without_the_switch(name: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-b12-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(
        std::path::Path::new(&format!(
            "{}/../../examples/refund-desk",
            env!("CARGO_MANIFEST_DIR")
        )),
        &dst,
    );
    let p = dst.join("tools/payments.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    let kept: Vec<&str> = text
        .lines()
        .filter(|l| !l.trim_start().starts_with("spends-money:"))
        .collect();
    assert!(
        kept.len() < text.lines().count(),
        "the worked example no longer writes `spends-money:` — this test asserts nothing"
    );
    std::fs::write(&p, kept.join("\n") + "\n").unwrap();
    dst
}

#[test]
fn an_argument_typed_money_is_money_moving_whether_or_not_anybody_said_so() {
    // Measured before this check: `takes: {amount: money}` with no
    // `spends-money:` printed "OK — loaded cleanly (51 settings)" and zero
    // diagnostics, so the same-request key, the approval rule and the
    // cross-agent walk were all off. The type is the evidence; the author had
    // already said what the argument is.
    let root = without_the_switch("inferred");
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        text.contains("loader/money-that-moves-with-nobody-asked"),
        "an amount of money with no switch must be said out loud:\n{text}"
    );
    assert!(
        text.contains("no same-request key"),
        "the message names what is off:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn it_is_a_warning_because_an_action_may_only_report_a_figure() {
    // A quote, an estimate, a balance: `spends-money: no` is the line that says
    // so, and refusing outright would break the case the field exists for.
    let root = without_the_switch("warns");
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "an action that only reports a figure must still check:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn either_half_of_the_fix_ends_it() {
    for (answer, name) in [("yes", "yes"), ("no", "no")] {
        let root = without_the_switch(name);
        let p = root.join("tools/payments.yaml");
        let text = std::fs::read_to_string(&p).unwrap();
        std::fs::write(
            &p,
            text.replace(
                "      amount: money",
                &format!("      amount: money\n    spends-money: {answer}"),
            ),
        )
        .unwrap();
        let out = pact()
            .args(["check", root.to_str().unwrap()])
            .output()
            .expect("runs");
        let said = format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
        assert!(
            !said.contains("loader/money-that-moves-with-nobody-asked"),
            "`spends-money: {answer}` answers the question:\n{said}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_shipped_example_gains_nothing_from_this() {
    let path = format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"));
    let out = pact().args(["check", &path]).output().expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(out.status.success(), "{text}");
    assert!(
        !text.contains("loader/money-that-moves-with-nobody-asked"),
        "{text}"
    );
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
