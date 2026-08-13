//! A duration has to be exactly as wide as it says it is, and it has to have a
//! bottom.
//!
//! Two failures, one type. The coercer has always taken `5 minutes`, `1m 30s`,
//! `30S` and `1d` — good spellings for somebody who cannot write code, and the
//! leniency is deliberate, since `pact_adapters.limits.seconds` reads the same
//! spellings on the other side. What was missing was anybody being TOLD: the type
//! described itself as "`2s` or `500ms`" and the fix offered three spellings, so
//! the friendliest ones worked and were undiscoverable. A capability nobody can
//! find is not a capability, and for the D13 reader — who has no source to read
//! and no grammar to consult — the diagnostic IS the documentation.
//!
//! And in the other direction the type had no bottom at all. `finishes-within:
//! 0s` loaded clean: a promise of zero time, which no run can keep. Compare
//! `stage.at-most`, which carries `at-least: 1` and produces a good refusal.
//!
//! So the two halves are held together here: every spelling the help advertises
//! must work, and every way of writing "no time at all" must be refused.
//!
//! And the third half, found later, is the far end of the same line. The parts
//! of a duration were added up with `*total += (v * mult) as u64`, and a
//! float-to-integer cast in Rust SATURATES rather than wrapping, so one
//! oversized part pinned the running total at the largest number there is and
//! the next part's `+=` went over the top of it:
//!
//! ```text
//! $ cat agents/refund-desk/limits.yaml
//! finishes-within: "99999999999999999999h 99999999999999999999h 99999999999999999999h"
//! when-it-runs-out: stop-and-say-so
//!
//! $ pact check .
//! thread 'main' panicked at crates/pact-schema/src/coerce.rs:174:
//! attempt to add with overflow
//! ```
//!
//! That is the debug build, which is what `cargo run` gives and what the README
//! tells an author to run. A release build did not panic — it wrapped, loaded
//! clean, and kept a ceiling with no relation to the line anybody wrote. Both
//! are the same missing sentence: a length of time nobody can count is still
//! spelled correctly, so it is refused one layer up by name, exactly as `0s` is.

use pact_diag::Diagnostics;
use pact_doc::parse_yaml;
use pact_schema::{Field, Group, Schema, Ty};

/// The three duration fields the worked example actually carries, so a rule
/// proved here is proved on the fields that park or stop a real run.
fn schema() -> Schema {
    Schema::new().with(Group {
        name: "limits".into(),
        fields: vec![
            Field::new("finishes-within", Ty::Duration, "how long the whole thing may take"),
            Field::new("answer-within", Ty::Duration, "how long they have to answer"),
            Field::new("forget-after", Ty::Duration, "when to discard it"),
        ],
        ..Default::default()
    })
}

fn check(line: &str) -> Diagnostics {
    let yaml = format!("{line}\n");
    let node = parse_yaml(&yaml, camino::Utf8Path::new("limits.yaml")).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source("limits.yaml", &yaml);
    schema().validate(&node, "limits", &mut d);
    d
}

/// Everything an author is shown about what a duration may be: the sentence the
/// type uses to describe itself, and the fix they get for writing one wrong.
fn what_the_author_is_told() -> String {
    let d = check("finishes-within: soon");
    let wrong = d
        .items()
        .iter()
        .find(|x| x.rule == "schema/wrong-type")
        .expect("a word that is not a length of time is refused");
    format!("{} {}", Ty::Duration.describe(), wrong.fix)
}

/// The backticked samples in a sentence — `2s`, `ms`, `minutes`.
fn quoted(text: &str) -> Vec<String> {
    text.split('`')
        .skip(1)
        .step_by(2)
        .map(str::to_string)
        .collect()
}

#[test]
fn the_duration_spellings_the_help_advertises_are_all_the_ones_that_work() {
    let told = what_the_author_is_told();
    let samples = quoted(&told);
    assert!(samples.len() >= 5, "the help offers almost no examples: {told}");

    for sample in &samples {
        // A sample with a number in it is a whole spelling and must load as
        // written. A bare word is a unit, and the promise made about a unit is
        // that a number in front of it — with or without the space the sentence
        // says is optional — is a length of time.
        let attempts: Vec<String> = if sample.chars().any(|c| c.is_ascii_digit()) {
            vec![sample.clone()]
        } else {
            vec![format!("2{sample}"), format!("2 {sample}")]
        };
        for attempt in attempts {
            let d = check(&format!("finishes-within: \"{attempt}\""));
            assert!(
                !d.has_errors(),
                "the help offers `{attempt}` and the checker refuses it:\n{}",
                d.render()
            );
        }
    }
}

#[test]
fn the_spellings_a_non_coder_reaches_for_are_all_named_in_the_help() {
    // The other direction, and the one that was broken: a spelling that loads
    // fine but appears nowhere an author can see it. Each of these was verified
    // to pass `pact check` on the worked example while the help named only
    // `2s`, `500ms` and `1m30s`.
    let told = what_the_author_is_told().to_lowercase();
    for (spelling, mentioned) in [
        ("5 minutes", "minutes"),
        ("1m 30s", "optional"), // the space between number and unit
        ("30S", "s"),
        ("1d", "d"),
        ("2 hours", "hours"),
        ("999999h", "h"),
        ("250 milliseconds", "milliseconds"),
    ] {
        let d = check(&format!("finishes-within: \"{spelling}\""));
        assert!(!d.has_errors(), "`{spelling}` used to work:\n{}", d.render());
        assert!(
            told.contains(mentioned),
            "`{spelling}` works and the author is never told — the help says nothing \
             about {mentioned:?}:\n{told}"
        );
    }
}

#[test]
fn a_length_of_time_with_no_unit_is_refused_because_it_could_mean_anything() {
    // The one tolerance the help deliberately does not advertise. `90` is
    // ninety seconds to the coercer, and to an author it is as likely to be
    // ninety minutes — a ceiling out by sixty times, silently. So it stays out
    // of the sentence, and written the way a person writes it (no quotes, so
    // YAML hands over a whole number rather than text) it is refused here with
    // the fix that teaches the unit. Same argument as `Ty::Percent`, which
    // refuses a bare `90` because it might be 90% or 9000%.
    let d = check("finishes-within: 90");
    let e = d
        .items()
        .iter()
        .find(|x| x.rule == "schema/wrong-type")
        .expect("a number with no unit is not a length of time");
    assert!(e.fix.contains("`2s`"), "the fix must show the unit: {}", e.fix);
    assert!(
        !e.fix.to_lowercase().contains("on its own"),
        "the help must not offer a spelling whose meaning it has to guess: {}",
        e.fix
    );
}

#[test]
fn every_way_of_writing_no_time_at_all_is_refused() {
    // Including the two nobody would predict: a bare `0` (seconds), and a
    // fraction of a millisecond, which reads as a length of time and rounds to
    // none of one.
    for written in ["0s", "0", "0ms", "0m", "0.4ms", "0h", "0 minutes"] {
        let d = check(&format!("finishes-within: \"{written}\""));
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "schema/below-the-floor")
            .unwrap_or_else(|| panic!("`{written}` is no time at all and loaded clean"));
        assert!(e.message.contains("finishes-within"), "must name the field: {}", e.message);
        assert!(e.message.contains(written), "must quote what was written: {}", e.message);
        // The fix has to be a line they can type, not a rule to satisfy.
        assert!(e.fix.contains("finishes-within: 30s"), "the fix must be typeable: {}", e.fix);
    }
}

#[test]
fn a_deadline_and_a_forgetting_have_the_same_floor_as_a_promise() {
    // The floor belongs to the TYPE, so it costs nothing per field and cannot be
    // forgotten on the next one. `answer-within: 0s` is a deadline that expires
    // before anybody is asked; `forget-after: 0s` discards what it remembers on
    // the way in. Neither carries an `at-least:` line and neither needs one.
    for field in ["answer-within", "forget-after"] {
        let d = check(&format!("{field}: 0s"));
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "schema/below-the-floor")
            .unwrap_or_else(|| panic!("`{field}: 0s` loaded clean"));
        assert!(e.message.contains(field), "must name the field: {}", e.message);
        assert!(e.fix.contains(&format!("{field}: 30s")), "must be typeable: {}", e.fix);
    }
}

#[test]
fn a_length_of_time_nobody_can_count_is_refused_by_name_rather_than_crashing() {
    // The far end of the floor. Each of these is spelled the way the help says
    // to spell it and asks for more milliseconds than the checker counts them
    // in, and each one either crashed `pact check` outright or was quietly kept
    // as a ceiling nobody wrote.
    //
    // Mutation: put `*total += (v * mult) as u64;` back in `coerce::duration`.
    // Measured with it back: a debug build — the one `cargo run` and the README
    // give an author — dies on the first line here with "attempt to add with
    // overflow", and a release build refuses none of the three.
    // `99999999999999999999h` comes back as 18_446_744_073_709_551_615ms (the
    // cast saturating) and the last line as 53_255_926_290_448_384ms (the
    // addition wrapping round), and nothing at all is reported about either. So
    // it is the refusal below, not the absence of a panic, that holds this.
    for written in [
        // The reported line: three oversized parts, the first pinning the
        // total at the largest number there is and the second going over it.
        "99999999999999999999h 99999999999999999999h 99999999999999999999h",
        // One part on its own, which needs no addition to be out of range.
        "99999999999999999999h",
        // And three parts that are each a number the checker can hold, and
        // together are not.
        "18000000000000000000ms 400000000000000000ms 100000000000000000ms",
        // And the boundary the guard itself is written on: 2^64 milliseconds
        // exactly, which is `u64::MAX as f64` and so the first figure the cast
        // would saturate on rather than convert. It is the only value that can
        // tell `ms >= u64::MAX as f64` from `ms >`, and under the latter it
        // loads clean as the saturated top — a ceiling nobody wrote, which is
        // this test's whole subject arriving by the one route the three lines
        // above leave open.
        "18446744073709551616ms",
    ] {
        let d = check(&format!("finishes-within: \"{written}\""));
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "schema/too-long-to-count")
            .unwrap_or_else(|| {
                panic!("`{written}` is longer than can be counted and got through:\n{}", d.render())
            });
        assert!(e.message.contains("finishes-within"), "must name the field: {}", e.message);
        assert!(e.message.contains(written), "must quote what was written: {}", e.message);
        // Same shape of fix as the floor's: a line they can type, not a rule.
        assert!(e.fix.contains("finishes-within: 30s"), "the fix must be typeable: {}", e.fix);
        // "not a length of time" would be a lie about a line spelled correctly,
        // and would send the author looking for a typo that is not there.
        assert!(
            !d.items().iter().any(|x| x.rule == "schema/wrong-type"),
            "it IS a length of time, just an uncountable one:\n{}",
            d.render()
        );
    }
}

#[test]
fn the_longest_length_of_time_anybody_writes_is_still_a_length_of_time() {
    // The refusal above must not have taken the big-but-sane ones with it.
    // `999999h` is a hundred and fourteen years and is in the help's own table;
    // the rest are parts that add up without going anywhere near the top.
    //
    // "Loads clean" is only half the claim, and the weaker half: a wrap loads
    // clean too. The other half — that the number kept is the number written —
    // is asserted where a scheduler actually reads it, in pact-cli's
    // `a_duration_means_what_the_help_says::the_longest_deadline_that_fits_reaches_a_scheduler_as_the_number_written`,
    // which runs `pact waits` on the worked example and requires
    // `"deadline-ms": 360001800000` for the `100000h 30m` below. The
    // millisecond values for the rest are in `coerce`'s own table.
    for written in ["999999h", "1000000h", "100000h 30m", "9999d 23h 59m 59s 999ms"] {
        let d = check(&format!("finishes-within: \"{written}\""));
        assert!(!d.has_errors(), "`{written}` must load:\n{}", d.render());
    }
}

#[test]
fn a_length_of_time_above_zero_is_still_accepted() {
    // The floor must not have swallowed the ordinary case. `1ms` is the smallest
    // thing anybody could write and it is a real length of time.
    for written in ["1ms", "30s", "30m", "30d", "1m30s"] {
        let d = check(&format!("finishes-within: \"{written}\""));
        assert!(!d.has_errors(), "`{written}` must load:\n{}", d.render());
    }
}
