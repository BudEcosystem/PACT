//! Money was the only quantity in PACT with no floor under it, and the spend
//! cap is the one field where that is not a tidiness complaint.
//!
//! A length of time carries its own bottom — `finishes-within: 0s` is refused by
//! `schema/below-the-floor`, *"which is no time at all"* — and a percentage
//! carries a `0..=1` range in the type. Money carried only its currency. So all
//! four of these loaded clean:
//!
//! ```text
//! $ cat agents/desk/limits.yaml
//! cost-per-request-under: NaN USD
//! when-it-runs-out: stop-and-say-so
//!
//! $ pact check .
//! OK — . loaded cleanly (9 settings).
//!
//! (and the same for `inf USD`, `-5 USD` and `0 USD`, while `finishes-within: 0s`
//!  one line up was refused with schema/below-the-floor)
//! ```
//!
//! What each of them then does at run time is the point, because the ceiling is
//! compared as `spent >= limit` (`limits.py`, `Limits.reached`):
//!
//! * `NaN` — every comparison against it is false, so THE CAP NEVER FIRES,
//!   under an author who believes they capped their spend. `inf` likewise.
//! * `0` and `-5` — reached before the first step, so every run stops instantly
//!   and reports a ceiling the author believed they were being generous with.
//!
//! The half that never fires is held on the other side of the wire, in
//! `adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py`, which
//! runs a real agent against a transport that reports what it spent and watches
//! the cap say nothing. This file is the refusal that stops such a document
//! being written in the first place.
//!
//! # Which money fields, and where the third one went
//!
//! The floor is the TYPE's, so it reaches both fields the specification types
//! `money`: `limits.cost-per-request-under` and `learning.cycle-limits.per-month`.
//! Both are ceilings, and a ceiling of nothing is a broken ceiling on both — but
//! not in the same way, and `Schema::check_floor`'s own doc says which. The
//! first is compared `spent >= limit` and stops every run instantly. The second
//! is compared `would_reach > amount` against a forecast that is `0.0` until
//! something has been scored, so `per-month: 0 USD` lets the first cycle of a
//! month spend and refuses from then on — measured at 8.00 USD, in
//! `adapters/python/tests/test_a_monthly_ceiling_nothing_can_reach_refuses_the_cycle.py`.
//! A ceiling that lets through exactly the spend it was written to prevent is
//! still one to refuse where it is written; it is a different sentence's worth
//! of reason, and the code says so rather than borrowing the duration's.
//!
//! `more-than:` on an approval gate is the third field that can carry money and
//! is NOT one of them, on purpose: it is a threshold rather than a ceiling,
//! nothing ever runs out against it, and `more-than: 0 USD` — "ask a person
//! about every refund" — is a workspace being strict rather than a workspace
//! being broken. A NON-finite threshold is not that either, and is refused one
//! crate over by `loader/threshold-is-not-a-figure`
//! (`crates/pact-loader/src/money.rs`), which is the only place that reads the
//! field as a figure — the schema cannot, because A3 made it `type: text` so a
//! score could be gated by a score.
//!
//! # The other end
//!
//! `1e400 USD` and `inf USD` are one `f64::INFINITY` after the parse and two
//! different mistakes, so they get two different answers: the first is over the
//! CEILING (`schema/too-much-to-count`, beside the duration and the size that
//! overflow the same way), the second is under the floor and *"not an amount of
//! money"*. Telling somebody who wrote a very large number that they did not
//! write a number sends them hunting a typo that is not there.
//!
//! Mutation: restore `_ => return` as the last arm of `Schema::check_floor` in
//! `crates/pact-schema/src/lib.rs` (i.e. delete the `Coerced::Money` arm above
//! it). Measured with it back: **7 of these 10 fail**, and the three that stay
//! green are the three that assert silence about something the floor was never
//! meant to reach — an ordinary amount, a bare number with no currency, and a
//! `more-than:` gate.
//!
//! `a_threshold_a_person_is_asked_above_is_not_a_ceiling_and_keeps_its_zero` is
//! among the seven that fail, and that is the whole point of the control inside
//! it. For a round that test asked the `question-rule` group for a document
//! whose three keys live in `when-this` one level down — so all three came back
//! `schema/unknown-field`, the figure was never looked at, and the absence it
//! asserted was true of a document that had already fallen apart. It passed
//! whether or not the decision it names was still the decision. An absence
//! assertion with no positive control beside it is not a test.

use pact_diag::Diagnostics;
use pact_doc::parse_yaml;
use pact_schema::Schema;

/// The shipped specification, not a schema written here.
///
/// The three fields under test are typed in `spec/schema.yaml` and their help
/// text is what an author is shown, so a fabricated `Group` would prove the
/// refusal works on a field nobody has.
fn spec() -> Schema {
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

/// One `limits.yaml`, held against the real `limits` group.
///
/// `when-it-runs-out:` is written every time because `cost-per-request-under`
/// declares `needs-also: [when-it-runs-out]` — without it the answer would be
/// a companion diagnostic and the floor would never be reached.
fn limits(line: &str) -> Diagnostics {
    let yaml = format!("{line}\nwhen-it-runs-out: stop-and-say-so\n");
    check(&yaml, "limits")
}

fn check(yaml: &str, group: &str) -> Diagnostics {
    let node = parse_yaml(yaml, camino::Utf8Path::new("limits.yaml")).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source("limits.yaml", yaml);
    spec().validate(&node, group, &mut d);
    d
}

/// The one diagnostic this file is about, or a panic naming what got through.
fn below_the_floor<'a>(d: &'a Diagnostics, written: &str) -> &'a pact_diag::Diagnostic {
    d.items()
        .iter()
        .find(|x| x.rule == "schema/below-the-floor")
        .unwrap_or_else(|| {
            panic!(
                "`{written}` is not a spend cap and loaded clean:\n{}",
                d.render()
            )
        })
}

/// Every way of writing an amount that is not an amount of money to spend.
const NOT_A_CAP: [&str; 4] = ["NaN USD", "inf USD", "-5 USD", "0 USD"];

#[test]
fn a_spend_cap_that_is_no_money_at_all_is_refused_where_the_author_wrote_it() {
    for written in NOT_A_CAP {
        let d = limits(&format!("cost-per-request-under: {written}"));
        let e = below_the_floor(&d, written);
        assert_eq!(e.rule, "schema/below-the-floor", "{}", d.render());
        assert!(
            e.message.contains("cost-per-request-under"),
            "must name the field: {}",
            e.message
        );
        assert!(
            e.message.contains(written),
            "must quote what was written: {}",
            e.message
        );
    }
}

#[test]
fn the_fix_for_a_spend_cap_with_no_money_in_it_is_a_line_they_can_type() {
    // The reader is a non-technical domain expert with no source to read: the
    // fix has to be the line, not the rule it has to satisfy.
    for written in NOT_A_CAP {
        let d = limits(&format!("cost-per-request-under: {written}"));
        let e = below_the_floor(&d, written);
        assert!(
            e.fix.contains("cost-per-request-under: 0.05 USD"),
            "the fix must be typeable: {}",
            e.fix
        );
        // And it must carry the field's own help, the way every other floor
        // refusal does, so the author is told what the line is for as well as
        // how to spell it.
        assert!(
            e.fix.contains("the most one request may cost"),
            "the help is missing: {}",
            e.fix
        );
    }
}

#[test]
fn an_amount_that_is_not_an_amount_is_not_told_it_is_too_small() {
    // `-5 USD` and `0 USD` are amounts of money, and small ones. `NaN USD` and
    // `inf USD` are not amounts at all, and telling somebody that infinity is
    // below the floor would send them looking for a bigger number to write.
    for written in ["NaN USD", "inf USD", "Infinity USD", "-inf USD"] {
        let d = limits(&format!("cost-per-request-under: {written}"));
        let e = below_the_floor(&d, written);
        let said = e.message.to_lowercase();
        assert!(
            said.contains("is not an amount of money"),
            "`{written}` is not a small amount, it is not one: {}",
            e.message
        );
        assert!(
            !said.contains("no money at all") && !said.contains("smallest"),
            "`{written}` was reported as though it were merely too small: {}",
            e.message
        );
    }
    // And the other way round: a real amount that is too small keeps the
    // wording the duration floor set, so the two floors read as one rule.
    for (written, said) in [
        ("0 USD", "which is no money at all"),
        ("-5 USD", "less than nothing"),
    ] {
        let d = limits(&format!("cost-per-request-under: {written}"));
        let e = below_the_floor(&d, written);
        assert!(
            e.message.contains(said),
            "`{written}` is an amount, just not a spendable one: {}",
            e.message
        );
    }
}

#[test]
fn every_spelling_of_a_number_that_is_not_one_is_caught() {
    // Rust's own float parser takes all of these, so each one reaches the
    // schema as a `Money` whose amount no comparison can be made against. A
    // spelling this check did not recognise would be a cap that silently
    // stopped existing.
    for written in [
        "NaN USD",
        "nan USD",
        "NAN USD",
        "USD NaN",
        "inf USD",
        "-inf USD",
        "infinity USD",
        "Infinity USD",
        "USD inf",
        "$NaN",
        "$inf",
    ] {
        let d = limits(&format!("cost-per-request-under: {written}"));
        below_the_floor(&d, written);
    }
}

#[test]
fn the_other_ceiling_priced_in_money_has_the_same_bottom() {
    // `learning.cycle-limits.per-month` is the second field the specification
    // types `money`, and it is a ceiling for the same reason: how much
    // improving itself may cost in a month. The floor belongs to the TYPE, so
    // it costs nothing per field and cannot be forgotten on the next one —
    // exactly the argument `check_floor` already makes about durations.
    for written in NOT_A_CAP {
        let yaml = format!("per-month: {written}\n");
        let d = check(&yaml, "cycle-limits");
        below_the_floor(&d, written);
    }
}

#[test]
fn a_threshold_a_person_is_asked_above_is_not_a_ceiling_and_keeps_its_zero() {
    // THE DECISION, held here so it cannot be changed by accident.
    //
    // `more-than:` is the third field that can carry money, and it is a GATE
    // rather than a ceiling: `more-than: 0 USD` means "stop for a person on ANY
    // spend", which is a sensible and deliberately strict rule, and a zero or
    // negative threshold never stops a run the way a zero ceiling does. So the
    // floor must not reach it. It does not, and by construction rather than by
    // an exception written here: A3 made the field `type: text` so a score
    // could be gated by a score, so it never coerces to `Money` at all and
    // `check_floor` never sees one.
    //
    // The group is `when-this`, which is where those three keys actually live.
    // This test asked `question-rule` for a round — the rule one level out, whose
    // fields are `when:`, `because:` and `question:` — so all three keys came
    // back `schema/unknown-field`, the value never reached `check_value` at all,
    // and the absence below was true of a document that had fallen apart before
    // anything looked at the figure. It passed either way, which is the whole
    // reason the positive control underneath it is not optional.
    for written in ["0 USD", "-5 USD", "200 USD", "80", "$0"] {
        let yaml = format!("tool: payments/issue-refund\narg: amount\nmore-than: {written}\n");
        let d = check(&yaml, "when-this");
        // POSITIVE CONTROL. An absence assertion is worth nothing unless the
        // document it is made about is otherwise whole: this one says every key
        // was recognised and every value accepted, so the silence below is the
        // decision and not a rule that never ran.
        assert!(
            !d.has_errors(),
            "the gate itself must load, or the absence below proves nothing:\n{}",
            d.render()
        );
        assert!(
            !d.items().iter().any(|x| x.rule == "schema/below-the-floor"),
            "`more-than: {written}` is a threshold, not a ceiling:\n{}",
            d.render()
        );
    }
    // SECOND CONTROL, in the same run: the floor this test says must not reach
    // `more-than:` is switched on and speaking. If it were ever deleted, the
    // loop above would keep passing and this line would not.
    let d = limits("cost-per-request-under: 0 USD");
    below_the_floor(&d, "0 USD");
}

#[test]
fn a_gate_that_cannot_be_read_as_money_is_still_refused_somewhere_else() {
    // The other half of the decision, and the half that is NOT the schema's.
    // "Non-finite is never legitimate anywhere" — a `more-than: NaN USD` is not
    // a strict gate, it is a gate with nothing to compare against. The schema
    // cannot say so, for the reason above: the field is `type: text` and never
    // becomes money here, so no arm of `check_floor` can ever see it.
    //
    // So the refusal lives in `crates/pact-loader/src/money.rs`
    // (`a_threshold_that_is_not_a_figure`, rule `loader/threshold-is-not-a-figure`),
    // which is the only place that already reads this field as a figure, and it
    // is held end to end by
    // `crates/pact-cli/tests/a_gate_whose_figure_is_not_a_figure_is_refused.rs`.
    // This test is here so that anybody reading the schema half is told where the
    // other half went, and so that "the schema stays quiet about it" is an
    // assertion rather than a comment.
    for written in ["NaN USD", "inf USD", "1e400 USD"] {
        let yaml = format!("tool: payments/issue-refund\narg: amount\nmore-than: {written}\n");
        let d = check(&yaml, "when-this");
        assert!(
            !d.has_errors(),
            "the schema must not try to judge this figure — the loader does:\n{}",
            d.render()
        );
    }
}

#[test]
fn an_amount_that_is_too_large_to_count_is_not_told_it_is_not_an_amount() {
    // `1e400 USD` and `inf USD` are one `f64::INFINITY` by the time anything
    // here sees them, and they are two different mistakes. The first is a figure
    // somebody meant, past the end of what can be counted; telling its author it
    // "is not an amount of money" sends them hunting a typo that is not there.
    // So it goes over the CEILING, beside the duration and the size that
    // overflow the same way, and not under the floor.
    let d = limits("cost-per-request-under: 1e400 USD");
    let e = d
        .items()
        .iter()
        .find(|x| x.rule == "schema/too-much-to-count")
        .unwrap_or_else(|| panic!("`1e400 USD` is not a countable amount:\n{}", d.render()));
    assert!(
        e.message
            .contains("a larger amount than this can keep track of"),
        "it is a figure, and too big a one: {}",
        e.message
    );
    assert!(
        e.fix.contains("any smaller amount"),
        "the fix points downward: {}",
        e.fix
    );
    assert!(
        !d.items().iter().any(|x| x.rule == "schema/below-the-floor"),
        "nothing is under the floor and over the ceiling at once:\n{}",
        d.render()
    );

    // A negative overflow keeps the floor's sentence, because it is less than
    // nothing before it is large and that is the edit its author has to make.
    let d = limits("cost-per-request-under: -1e400 USD");
    let e = below_the_floor(&d, "-1e400 USD");
    assert!(e.message.contains("less than nothing"), "{}", e.message);
}

#[test]
fn an_amount_of_money_anybody_would_write_is_still_an_amount_of_money() {
    // The floor must not have swallowed the ordinary case, or the half-penny
    // one: `Field::at_least` is a whole number and could not have expressed
    // this bottom, which is the other reason it belongs to the type.
    for written in [
        "0.05 USD",
        "0.0001 USD",
        "500 JPY",
        "$0.05",
        "USD 12",
        "1000000 EUR",
    ] {
        let d = limits(&format!("cost-per-request-under: {written}"));
        assert!(!d.has_errors(), "`{written}` must load:\n{}", d.render());
    }
}

#[test]
fn a_figure_with_no_currency_on_it_still_gets_the_one_message_it_already_had() {
    // One mistake gets one message. `cost-per-request-under: 0` is a bare
    // number, which `Ty::Money` does not coerce at all, and it is already
    // `schema/wrong-type` at that line with a fix that shows the spelling. A
    // floor complaining as well would send the reader looking for a bigger
    // number when what is missing is the currency.
    for written in ["0", "-5", "0.05"] {
        let d = limits(&format!("cost-per-request-under: {written}"));
        assert!(
            d.items().iter().any(|x| x.rule == "schema/wrong-type"),
            "`{written}` is not money at all:\n{}",
            d.render()
        );
        assert!(
            !d.items().iter().any(|x| x.rule == "schema/below-the-floor"),
            "two messages for one edit:\n{}",
            d.render()
        );
    }
}
