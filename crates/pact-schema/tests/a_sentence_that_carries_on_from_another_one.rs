//! **A sentence that is not a rule on its own, written on its own.**
//!
//! `redaction.hide` and `interceptor.rules` share one closed vocabulary — the
//! `&the-hiding-sentences` anchor in `spec/schema.yaml` — and one of its five
//! sentences is not a rule by itself. `do the same for anything that looks like
//! <a thing>` reuses the words the line above it left behind, so written first
//! there is nothing to be the same as and it hides nothing at all.
//!
//! That fact lived only in the adapter for a round. Measured on a two-file
//! workspace whose one interceptor rule was `do the same for anything that looks
//! like a card number`:
//!
//! ```text
//! OK — …/mini loaded cleanly (17 settings).
//! ```
//!
//! and then `Chain.from_document` refused the same line. `pact check` is the only
//! tool decision D13's author runs, so a file it passes and the run rejects is
//! the exact split this whole `forms:` block exists to close — and sharing the
//! list with `redaction.hide` doubled the surface, because the same sentence in
//! the same shape is now writeable in the other file too.
//!
//! `continues: yes` is that fact as DATA, beside the sentence it is about. What
//! a continuing sentence may carry on FROM is derived rather than listed: an
//! earlier sentence needing the same power that does not itself continue. So a
//! `do the same …` cannot carry on from `stop and say "…"`, and nothing anywhere
//! had to write down that it cannot.
//!
//! The tests here go through the **shipped** `spec/schema.yaml` rather than a
//! schema built in this file. A hand-built vocabulary would prove this file
//! agrees with itself and say nothing about whether the sentence an author reads
//! in the help text is the sentence the checker holds them to — which is the way
//! the two hiding vocabularies drifted apart in the first place.

use pact_diag::Diagnostics;

/// The specification as it actually ships.
fn spec() -> pact_schema::Schema {
    const SPEC: &str = include_str!("../../../spec/schema.yaml");
    let mut d = Diagnostics::new();
    let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
    assert!(
        !d.has_errors(),
        "the shipped specification does not load:\n{}",
        d.render()
    );
    s
}

/// Check one document against one kind, the way `pact check` does.
fn checked(kind: &str, file: &str, text: &str) -> Diagnostics {
    let node = pact_doc::parse_yaml(text, camino::Utf8Path::new(file)).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source(file, text);
    spec().validate(&node, kind, &mut d);
    d
}

/// The refusal, or a panic naming what was accepted instead.
fn refusal(d: &Diagnostics) -> &pact_diag::Diagnostic {
    d.items()
        .iter()
        .find(|e| e.rule == "schema/rule-with-nothing-above-it")
        .unwrap_or_else(|| {
            panic!(
                "a sentence with nothing above it must be refused here:\n{}",
                d.render()
            )
        })
}

const AN_INTERCEPTOR: &str = "\
description: Hides card numbers.
when: step.message.before
may:
  - hide-values
rules:
";

const A_REDACTION: &str = "\
description: What may never leave.
hide:
";

#[test]
fn an_interceptor_whose_first_rule_carries_on_from_another_one_is_refused() {
    // The file that printed "loaded cleanly" and was then rejected by the run.
    let d = checked(
        "interceptor",
        "interceptors/x.yaml",
        &format!("{AN_INTERCEPTOR}  - do the same for anything that looks like a card number\n"),
    );
    let e = refusal(&d);
    assert_eq!(
        e.span.line, 6,
        "point at the rule, not the file: {:?}",
        e.span
    );
    assert!(
        e.message.contains("no rule before it says what to do"),
        "say what is wrong in the author's words: {}",
        e.message
    );
}

#[test]
fn a_redaction_whose_first_line_carries_on_from_another_one_is_refused_the_same_way() {
    // The other half of the shared list. `hide:` gained `do the same for …` with
    // the merge, so it gained this way of writing a line that hides nothing —
    // and a redaction that hides nothing is the failure `hide:` is `required:`
    // to prevent, arriving one level in.
    let d = checked(
        "redaction",
        "redaction.yaml",
        &format!("{A_REDACTION}  - do the same for anything that looks like a card number\n"),
    );
    let e = refusal(&d);
    assert!(
        e.message.contains("no rule before it says what to do"),
        "the author must not be able to tell which of the two files they are in: {}",
        e.message
    );
}

#[test]
fn the_repair_it_offers_is_a_sentence_that_is_accepted_on_its_own() {
    // A fix that does not survive being followed is not a typeable fix. Every
    // line offered is written back into the same kind of file, on its own, and
    // has to be accepted — with the hole filled in the way an author fills it.
    let d = checked(
        "redaction",
        "redaction.yaml",
        &format!("{A_REDACTION}  - do the same for anything that looks like a card number\n"),
    );
    let offered: Vec<String> = refusal(&d)
        .fix
        .lines()
        .map(str::trim)
        .filter(|l| l.starts_with("replace ") || l.starts_with("anything "))
        .map(|l| {
            l.replace("<a thing>", "a card number")
                .replace("\"<text>\"", "\"[gone]\"")
        })
        .collect();
    assert!(
        !offered.is_empty(),
        "the refusal must offer something to type:\n{}",
        refusal(&d).fix
    );

    for sentence in &offered {
        let d = checked(
            "redaction",
            "redaction.yaml",
            &format!("{A_REDACTION}  - {sentence}\n"),
        );
        assert!(
            !d.has_errors(),
            "'{sentence}' was offered as the repair and is itself refused:\n{}",
            d.render()
        );
    }
}

#[test]
fn a_sentence_written_under_one_it_can_carry_on_from_is_left_alone() {
    // The half that matters most: the shipped worked example writes exactly this
    // pair, and a check that refused it would have made the merge a regression
    // rather than a fix.
    let d = checked(
        "interceptor",
        "interceptors/x.yaml",
        &format!(
            "{AN_INTERCEPTOR}  - replace anything that looks like a card number with \"[gone]\"\n\
             \x20 - do the same for anything that looks like a bank account\n"
        ),
    );
    assert!(!d.has_errors(), "{}", d.render());

    // And under the sentence that names no replacement, which is the form
    // `redaction.hide` brought to the shared list. It leaves `[removed]` behind,
    // so there IS something above to be the same as — refusing here would tell an
    // author that a line plainly hiding something says nothing about hiding.
    let d = checked(
        "redaction",
        "redaction.yaml",
        &format!(
            "{A_REDACTION}  - anything that looks like a card number\n\
             \x20 - do the same for anything that looks like an email address\n"
        ),
    );
    assert!(!d.has_errors(), "{}", d.render());
}

#[test]
fn a_hiding_sentence_cannot_carry_on_from_a_counting_one() {
    // What `continues:` derives rather than lists. The line above hides nothing
    // and leaves no words behind, so `do the same …` under it still has nothing
    // to be the same as — and nobody had to write down that a counting sentence
    // is not one of the two it can follow.
    let d = checked(
        "interceptor",
        "interceptors/x.yaml",
        "description: Guards the payments tool.\n\
         when: step.tool.before\n\
         may:\n\
         \x20 - hide-values\n\
         \x20 - stop-the-run\n\
         rules:\n\
         \x20 - if payments is called more than 1 time in one run, stop and say \"no\"\n\
         \x20 - do the same for anything that looks like a card number\n",
    );
    let e = refusal(&d);
    assert_eq!(e.span.line, 8, "point at the second rule: {:?}", e.span);
}

#[test]
fn the_worked_examples_own_two_files_are_not_refused_by_any_of_this() {
    // The sentences an author is actually shipped, held against the check that
    // was added around them. `redaction.yaml` writes three bare lines and
    // `interceptors/redact-card-numbers.yaml` writes a `replace …` followed by a
    // `do the same …`; neither may become a file the tool refuses.
    let d = checked(
        "redaction",
        "redaction.yaml",
        &format!(
            "{A_REDACTION}  - anything that looks like a card number\n\
             \x20 - anything that looks like a bank account\n\
             \x20 - anything that looks like an email address\n"
        ),
    );
    assert!(!d.has_errors(), "{}", d.render());

    let d = checked(
        "interceptor",
        "interceptors/redact-card-numbers.yaml",
        "description: Stops card numbers reaching the model, a tool, or the transcript.\n\
         applies-to: every-agent\n\
         when:\n\
         \x20 - step.message.before\n\
         \x20 - step.tool.before\n\
         may:\n\
         \x20 - hide-values\n\
         rules:\n\
         \x20 - replace anything that looks like a card number with \"[card number removed]\"\n\
         \x20 - do the same for anything that looks like a bank account\n",
    );
    assert!(!d.has_errors(), "{}", d.render());
}
