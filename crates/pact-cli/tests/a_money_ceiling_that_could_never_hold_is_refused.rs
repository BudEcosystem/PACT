//! The money floor, through the shipped binary, over a real workspace.
//!
//! `Schema::check_floor` grew a `Coerced::Money` arm because money was the only
//! quantity in PACT with no bottom under it: a length of time carries one in its
//! type (`finishes-within: 0s` is `schema/below-the-floor`, *"which is no time
//! at all"*) and a percentage carries `0..=1`. Money carried only its currency,
//! so `cost-per-request-under: NaN USD` printed *"OK — loaded cleanly"*.
//!
//! **The arm had no test in this crate at all**, and that is what this file is
//! for rather than for the floor's wording, which
//! `crates/pact-schema/tests/a_spend_cap_is_an_amount_of_money_and_has_a_bottom.rs`
//! already holds against the schema seam. MEASURED, by guarding the arm with
//! `if false && …` in `crates/pact-schema/src/lib.rs` and running
//! `cargo test -p pact-cli`: **all 60 test targets reported `test result: ok`**,
//! 0 failed. The only end-to-end doors were two tests inside the Python adapter
//! suite, and both open with
//!
//! ```text
//! if not PACT_BIN.exists():
//!     pytest.skip("build the CLI first: cargo build -p pact-cli")
//! ```
//!
//! which is a real hazard and not a theoretical one: the tree's
//! `target/debug/pact` was a pre-fix binary during that measurement, and the
//! adapter suite reported `learning-NaN-USD loaded cleanly (498 settings)` until
//! it was rebuilt. A check whose only end-to-end proof depends on somebody
//! having remembered to build the binary is a check that can be deleted by
//! accident. `CARGO_BIN_EXE_pact` cannot be stale: cargo builds it as a
//! dependency of this test.
//!
//! Both money ceilings, because the whole argument for putting the floor in the
//! TYPE rather than on a field is that it reaches every money field without
//! being remembered per field — and a test that only ever pointed at
//! `cost-per-request-under` could not tell that apart from a check wired to one
//! field's name. `learning.cycle-limits.per-month` is `tier: core` and `S-GOV`,
//! a spend cap on a system that rewrites itself, and it is a shipped line in the
//! worked example.
//!
//! The third field that can carry money — `question-rule.more-than` — is
//! deliberately NOT here. It is a GATE and not a ceiling, nothing ever runs out
//! against it, and `more-than: 0 USD` is a workspace being strict. Its own
//! refusal, for the non-finite case only, is
//! `a_gate_whose_figure_is_not_a_figure_is_refused.rs`.
//!
//! Mutation: guard the `coerce::Coerced::Money { .. }` arm of
//! `Schema::check_floor` with `if false &&` (equivalently, delete it and let
//! `_ => return` take over). Measured with it guarded: **3 of the 5 tests here
//! fail**, the first of them printing
//! `OK — /tmp/pact-floor-month-NaN_USD-… loaded cleanly (498 settings).`
//! The two that stay green are the two that are not about this arm — the
//! overflow test, whose refusal is `schema/too-much-to-count`, and the control,
//! which asserts the shipped example still loads. Before this file existed the
//! same mutation left all 60 test targets in this crate reporting
//! `test result: ok`.

use std::process::Command;

const LIMITS: &str = "agents/refund-desk/limits.yaml";
const LEARNING: &str = "learning.yaml";

/// Every way of writing an amount that is not an amount of money to spend.
///
/// Two mistakes with two sentences: the first pair are not amounts at all, the
/// second pair are amounts and not spendable ones. Both must be refused and
/// they must not be refused with each other's words — being told that infinity
/// is "too small" sends its author looking for a bigger number to write.
const NOT_A_CEILING: [(&str, &str); 4] = [
    ("NaN USD", "is not an amount of money"),
    ("inf USD", "is not an amount of money"),
    ("-5 USD", "is less than nothing"),
    ("0 USD", "is no money at all"),
];

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply one edit, return the temp root.
fn edited(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-floor-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
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

/// `pact check` over the worked example with one ceiling rewritten.
fn checked(name: &str, file: &str, from: &str, to: &str) -> (bool, String) {
    let root = edited(name, file, from, to);
    let out = pact().args(["check", &root]).output().expect("runs");
    let said =
        String::from_utf8_lossy(&out.stdout).into_owned() + &String::from_utf8_lossy(&out.stderr);
    let _ = std::fs::remove_dir_all(&root);
    (out.status.success(), said)
}

fn cap_of(name: &str, written: &str) -> (bool, String) {
    checked(
        name,
        LIMITS,
        "cost-per-request-under: 0.05 USD",
        &format!("cost-per-request-under: {written}"),
    )
}

fn per_month_of(name: &str, written: &str) -> (bool, String) {
    checked(
        name,
        LEARNING,
        "per-month: 20 USD",
        &format!("per-month: {written}"),
    )
}

#[test]
fn a_spend_cap_that_could_never_have_fired_is_refused_where_it_is_written() {
    for (written, because) in NOT_A_CEILING {
        let name = format!("cap-{}", written.replace([' ', '-'], "_"));
        let (ok, said) = cap_of(&name, written);
        assert!(
            !ok,
            "`cost-per-request-under: {written}` loaded cleanly:\n{said}"
        );
        assert!(
            said.contains("rule: schema/below-the-floor"),
            "`{written}` was not refused as a cap that could never work:\n{said}"
        );
        assert!(
            said.contains(&format!("'cost-per-request-under' is {written}")),
            "the field and what was written must both be quoted:\n{said}"
        );
        assert!(
            said.contains(because),
            "the wrong one of the two sentences:\n{said}"
        );
        assert!(
            said.contains("limits.yaml:"),
            "must name the file and the line:\n{said}"
        );
    }
}

#[test]
fn the_other_ceiling_priced_in_money_has_the_same_bottom_through_the_same_command() {
    // The floor belongs to the TYPE, and this is the assertion that says so:
    // nothing in `check_floor` names `cost-per-request-under`, so the second
    // money field is held by the same three lines with no edit of its own.
    for (written, because) in NOT_A_CEILING {
        let name = format!("month-{}", written.replace([' ', '-'], "_"));
        let (ok, said) = per_month_of(&name, written);
        assert!(!ok, "`per-month: {written}` loaded cleanly:\n{said}");
        assert!(said.contains("rule: schema/below-the-floor"), "{said}");
        assert!(
            said.contains(&format!("'per-month' is {written}")),
            "the field and what was written must both be quoted:\n{said}"
        );
        assert!(
            said.contains(because),
            "the wrong one of the two sentences:\n{said}"
        );
        assert!(
            said.contains("learning.yaml:"),
            "must name the file and the line:\n{said}"
        );
    }
}

#[test]
fn the_fix_a_person_is_offered_is_a_line_they_can_type() {
    // The reader is a domain expert with no source to read, so the fix is the
    // line and not the rule it has to satisfy, and it carries the field's own
    // help so they are told what the line is FOR as well as how to spell it.
    let (_, said) = cap_of("fixline", "NaN USD");
    assert!(
        said.contains("cost-per-request-under: 0.05 USD"),
        "not typeable:\n{said}"
    );
    assert!(
        said.contains("the most one request may cost"),
        "the help is missing:\n{said}"
    );
    for jargon in ["non-finite", "IEEE", "f64", "NaN is", "float"] {
        let fix = said
            .lines()
            .find(|l| l.trim_start().starts_with("fix:"))
            .unwrap_or_else(|| panic!("no fix line:\n{said}"));
        assert!(
            !fix.contains(jargon),
            "the fix says {jargon:?} to a non-programmer: {fix}"
        );
    }
}

#[test]
fn a_ceiling_past_the_end_of_counting_is_not_told_it_is_not_an_amount() {
    // `1e400` and `inf` are one `f64::INFINITY` after the parse and two
    // different mistakes. Somebody who wrote `1e400 USD` wrote a figure, and
    // being told it "is not an amount of money" sends them hunting a typo that
    // is not there. Held from the binary because the split is the kind of thing
    // a later tidy-up collapses.
    let (ok, said) = cap_of("overflow", "1e400 USD");
    assert!(!ok, "`1e400 USD` loaded cleanly:\n{said}");
    assert!(said.contains("rule: schema/too-much-to-count"), "{said}");
    assert!(
        said.contains("a larger amount than this can keep track of"),
        "it is a figure, and too big a one:\n{said}"
    );
    assert!(
        !said.contains("is not an amount of money"),
        "wrong of the two:\n{said}"
    );
    assert!(
        !said.contains("schema/below-the-floor"),
        "under the floor AND over it:\n{said}"
    );
}

#[test]
fn the_worked_example_this_file_edits_still_loads_clean() {
    // THE CONTROL, and it is not a formality. Every assertion above is a
    // refusal, so a floor that refused everything — or a fixture that had
    // drifted into refusing for some other reason — would leave all of them
    // green. This is the one test here that fails if the floor swallowed the
    // ordinary case.
    let out = pact().args(["check", &example()]).output().expect("runs");
    let said =
        String::from_utf8_lossy(&out.stdout).into_owned() + &String::from_utf8_lossy(&out.stderr);
    assert!(
        out.status.success(),
        "the shipped example must load:\n{said}"
    );
    assert!(!said.contains("below-the-floor"), "{said}");
}
