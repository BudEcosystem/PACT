//! An approval gate whose threshold is not a figure — `more-than: NaN USD`.
//!
//! B3 put a floor under money where the two CEILINGS priced in money are typed
//! (`limits.cost-per-request-under`, `learning.cycle-limits.per-month`), and
//! deliberately left the third money-shaped field out of it: `more-than:` is a
//! GATE, not a ceiling. `more-than: 0 USD` means "stop for a person on ANY
//! spend", which is a strict rule rather than a broken one, and nothing ever
//! runs out against a threshold. That decision stands and is held by
//! `crates/pact-schema/tests/a_spend_cap_is_an_amount_of_money_and_has_a_bottom.rs`.
//!
//! **A non-finite threshold is not that**, and it was still loading clean.
//! Measured on a copy of `examples/refund-desk` with the first rule's
//! `more-than: 200 USD` changed:
//!
//! ```text
//! $ pact check rd
//! OK — rd loaded cleanly (498 settings).
//! $ echo $?
//! 0
//! ```
//!
//! What that document then does, measured through the reader rather than
//! inferred from the arithmetic — `amount > NaN` is never evaluated, because the
//! threshold never becomes a number at all:
//!
//! ```text
//! >>> questions._amount('NaN USD')
//! None
//! >>> questions._atom_stops(
//! ...     {'tool': 'payments/issue-refund', 'arg': 'amount', 'more-than': 'NaN USD'},
//! ...     {'amount': '1 USD'})
//! True
//! ```
//!
//! `_atom_stops` answers `True` for a threshold it cannot read, on purpose — its
//! own docstring says *"a malformed `more-than:` is a mistake, and refusing to
//! ask because of one would turn a typo into a disabled gate"*. So the gate does
//! not vanish; it swallows the figure, and every call to that action parks for a
//! person however small. A refund desk that stops for a manager over a 1 USD
//! refund is a desk nobody keeps using, and the line that did it reads exactly
//! like a threshold.
//!
//! The schema cannot say any of this: A3 made `more-than:` `type: text` so a
//! score could be gated by a score, so it never coerces to money and
//! `Schema::check_floor` never sees one. The refusal is therefore in
//! `crates/pact-loader/src/money.rs`, the only file that already reads this
//! field as a figure.
//!
//! # Two halves, and only one of them is here
//!
//! A threshold can be wrong in two ways, and this file can only see one.
//!
//! * **No figure at all** — `NaN USD`, `.nan USD`, `TBD USD`, `<amount> USD`.
//!   The run-time state is fail-CLOSED and absurd: every call parks. That is
//!   this file.
//! * **A figure, read back as a DIFFERENT figure.** `more-than: .50 USD` loads
//!   clean here and always will, because it IS a figure — and
//!   `questions._amount` used to read it as **50.0**, so a gate written at fifty
//!   cents did not fire on a 40 USD refund. That one is fail-OPEN, and no
//!   refusal in this crate could ever have caught it. It is fixed in the READER
//!   and pinned in
//!   `adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py`,
//!   which asserts that for every threshold this file lets through the figure
//!   the runtime reads back is the figure that was written. The two files are
//!   one guard; neither is sufficient alone.
//!
//! # Mutations this file is answerable to
//!
//! Each of these was applied, the suite re-run, and the result recorded.
//!
//! * Delete the `a_threshold_that_is_not_a_figure(document, diags);` call from
//!   `money::check`. Every test below fails with "loaded cleanly", and the
//!   schema-side suite one crate over stays entirely green — which is how this
//!   hole survived the first round.
//! * `for rule in rules` -> `for rule in rules.iter().take(1)` in
//!   `a_threshold_that_is_not_a_figure` (before the walk was generalised; the
//!   equivalent today is restricting `every_gate` to the first list item).
//!   MEASURED before `a_rule_that_is_not_the_first_one_is_walked_too` existed:
//!   this binary 6 passed, `pact-loader` + `pact-cli` 76 test binaries green,
//!   `test_a_spend_cap_that_can_never_be_reached.py` 8 passed — while
//!   `pact check` over a real tree with `more-than: NaN USD` on the SECOND
//!   approval rule printed "OK — loaded cleanly (498 settings)" and exited 0.
//! * `figure.span.clone()` -> `when.get("tool").map(|t| t.span.clone())` at the
//!   `Diagnostic::error` below it. MEASURED: this binary 6 passed and
//!   `a_caret_points_at_what_the_message_names` 6 passed, with the caret landing
//!   under `payments/issue-refund` — because the message quotes
//!   `more-than: NaN USD` from the FORMAT STRING and the only location assertion
//!   was `said.contains("approvals.yaml:")`, which any span in that file
//!   satisfies. The column is now asserted.
//! * An extra `loader/threshold-below-the-floor` for any threshold parsing
//!   `<= 0.0`. MEASURED: this binary 6 passed, while the shipped binary refused
//!   `more-than: 0 USD` — the decision at the bottom of this file was held only
//!   by the Python suite, because the loop asserted a DISJUNCTION
//!   (`ok || !said.contains(...)`). It now asserts `ok`.
//! * One line on the `agent` group of a copy of `spec/schema.yaml` —
//!   `ask-a-person: {type: list of group:question-rule}` — which is a second
//!   route to the same field. MEASURED before `every_gate`: "OK — loaded cleanly
//!   (507 settings)", exit 0, with the growth guard in `currency.rs` green,
//!   because that guard pins field NAMES and a second route adds no name.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply one edit, return the temp root.
fn edited(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-gate-{name}-{}", std::process::id()));
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

fn ran(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("runs");
    let said =
        String::from_utf8_lossy(&out.stdout).into_owned() + &String::from_utf8_lossy(&out.stderr);
    let _ = std::fs::remove_dir_all(root);
    (out.status.success(), said)
}

/// The FIRST rule of the only policy file, at `approvals.yaml:26`.
fn gated_at(name: &str, written: &str) -> (bool, String) {
    let root = edited(
        name,
        "policies/approvals.yaml",
        "more-than: 200 USD",
        &format!("more-than: {written}"),
    );
    ran(&root)
}

/// The SECOND rule of the same file, at `approvals.yaml:31`.
///
/// Not a convenience. [`gated_at`] edits the first `more-than:` of the first
/// rule of the only policy of the only fixture, so every loop the check walks —
/// policies, rules, `when:` clauses — was crossed exactly once with an index of
/// zero, and a walk that only ever looked at index 0 stayed green. See the
/// `.take(1)` mutation in this file's prose.
fn gated_at_the_second_rule(name: &str, written: &str) -> (bool, String) {
    let root = edited(
        name,
        "policies/approvals.yaml",
        "more-than: 500 USD",
        &format!("more-than: {written}"),
    );
    ran(&root)
}

/// A `when:` list with TWO clauses, the bad figure on the second, at
/// `approvals.yaml:27`.
///
/// The shipped example has one clause per rule, so `for when in whens` was as
/// unwitnessed as the rule loop above it.
fn gated_at_the_second_clause(name: &str, written: &str) -> (bool, String) {
    let one = "      - { tool: payments/issue-refund, arg: amount, more-than: 200 USD }";
    let root = edited(
        name,
        "policies/approvals.yaml",
        one,
        &format!(
            "{one}\n      - {{ tool: payments/issue-refund, arg: amount, \
             more-than: {written} }}"
        ),
    );
    ran(&root)
}

#[test]
fn a_threshold_spelled_like_a_number_and_not_one_is_refused_where_it_is_written() {
    for (name, written) in [("nan", "NaN USD"), ("inf", "inf USD"), ("neg", "-inf USD")] {
        let (ok, said) = gated_at(name, written);
        assert!(!ok, "`more-than: {written}` loaded cleanly:\n{said}");
        assert!(
            said.contains("rule: loader/threshold-is-not-a-figure"),
            "`{written}` was not refused as a threshold with no figure in it:\n{said}"
        );
        assert!(
            said.contains(&format!("`more-than: {written}`")),
            "must quote what was written:\n{said}"
        );
        assert!(
            said.contains("payments/issue-refund"),
            "must name the action the rule watches:\n{said}"
        );
        // THE COLUMN, not just the file. `approvals.yaml:` alone is satisfied by
        // any span anywhere in that file, and the sentence quotes
        // `more-than: NaN USD` from the format string rather than from the
        // span — so pointing the caret at the `tool:` key instead left every
        // other assertion here true. Measured: the caret went to 26:17, under
        // `payments/issue-refund`, and this binary stayed green. Column 64 is
        // where the figure the message names is written.
        assert!(
            said.contains("approvals.yaml:26:64"),
            "the caret must be on the figure, not merely in the file:\n{said}"
        );
        assert!(
            said.contains(&"^".repeat(written.len())),
            "the underline must cover the figure that was written:\n{said}"
        );
    }
}

#[test]
fn a_rule_that_is_not_the_first_one_is_walked_too() {
    // THE MUTATION THE FIRST ROUND COULD NOT SEE. Everything above edits the
    // first `more-than:` of the first rule of the only policy, so `take(1)` on
    // the rule loop kept all six tests green while `pact check` over a real tree
    // with a broken threshold on the SECOND approval rule printed "OK — loaded
    // cleanly (498 settings)" and exited 0. The `when:` half is the same
    // argument one loop further in: the shipped example writes one clause per
    // rule, so `for when in whens` had never been crossed twice either.
    let (ok, said) = gated_at_the_second_rule("rule2", "NaN USD");
    assert!(
        !ok,
        "a bad threshold on the second rule loaded cleanly:\n{said}"
    );
    assert!(
        said.contains("rule: loader/threshold-is-not-a-figure"),
        "{said}"
    );
    assert!(
        said.contains("approvals.yaml:31:64"),
        "the caret must land on the SECOND rule's line, not the first:\n{said}"
    );
    // And the first rule, which is untouched and correct, draws nothing.
    assert_eq!(
        said.matches("loader/threshold-is-not-a-figure").count(),
        1,
        "one broken rule, one complaint:\n{said}"
    );

    let (ok, said) = gated_at_the_second_clause("when2", "NaN USD");
    assert!(
        !ok,
        "a bad threshold on the second `when:` clause loaded cleanly:\n{said}"
    );
    assert!(
        said.contains("rule: loader/threshold-is-not-a-figure"),
        "{said}"
    );
    assert!(
        said.contains("approvals.yaml:27:64"),
        "the caret must land on the second clause of the first rule:\n{said}"
    );
}

#[test]
fn the_spellings_yaml_itself_documents_are_refused_like_the_ones_rust_takes() {
    // THE HOLE THE FIRST ROUND LEFT. `NaN`, `inf` and `-inf` are Rust's float
    // grammar; `.nan`, `.inf` and `-.inf` are YAML's, and YAML's are the ones an
    // author writing a `.yaml` file reaches for. `crates/pact-doc/src/yaml.rs`
    // deliberately keeps them as TEXT ("`.inf` and `.nan` never reached here"),
    // which is right and is exactly why asking `str::parse::<f64>` alone missed
    // them: measured before this, `more-than: .nan USD` printed "OK — … loaded
    // cleanly (498 settings)" and exited 0, and `questions._amount('.nan USD')`
    // is `None` just as it is for `NaN USD`, so every refund parked for a
    // person. `$.nan` is the same value on a field an author has been shown
    // `$25` on.
    for (name, written) in [
        ("dotnan", ".nan USD"),
        ("dotinf", ".inf USD"),
        ("dotneg", "-.inf USD"),
        ("dotcaps", ".NaN USD"),
        ("dollarnan", "$.nan"),
    ] {
        let (ok, said) = gated_at(name, written);
        assert!(!ok, "`more-than: {written}` loaded cleanly:\n{said}");
        assert!(
            said.contains("rule: loader/threshold-is-not-a-figure"),
            "`{written}` is YAML's own spelling of the same value:\n{said}"
        );
        assert!(
            said.contains("is not a figure at all"),
            "`.inf` is a spelling, not an overflowed figure:\n{said}"
        );
        assert!(
            said.contains(&format!("`more-than: {written}`")),
            "must quote what was written:\n{said}"
        );
    }
}

#[test]
fn a_threshold_that_is_no_kind_of_number_is_refused_like_the_ones_that_are() {
    // THE OPEN CLASS BEHIND THE SPELLINGS ABOVE, and the second thing this round
    // fixed. The rule id says "is not a figure", and the check enforced a LIST of
    // four non-finite spellings — so everything it had never heard of went
    // through. Measured, one `more-than:` rewritten per run against the built
    // binary, before the test was inverted: every line below printed
    // "OK — … loaded cleanly (498 settings)" and exited 0, and every one of them
    // produces the identical run-time state the check exists to refuse
    // (`_amount` -> None, `_atom_stops` -> True, every refund parks).
    //
    // `<amount> USD` is not a hypothetical: it is verbatim what the neighbouring
    // `loader/currency-nothing-can-price` fix line hands the author. `NaN$ USD`
    // is verbatim what `loader/compared-in-the-wrong-shape` handed them for
    // `more-than: NaN$` — measured end to end: the tool refused `NaN$`, said
    // "like `NaN$ USD`", and doing exactly that loaded cleanly. A refusal an
    // author can be walked into by the tool's own advice is not a refusal.
    for (name, written) in [
        ("tbd", "TBD USD"),
        ("qqq", "??? USD"),
        ("abc", "abc USD"),
        ("words", "two hundred USD"),
        ("placeholder", "<amount> USD"),
        ("dollarnanbare", "NaN$"),
        ("dollarnanusd", "NaN$ USD"),
        ("empty", "\"\""),
        // NOT ASCII, and this row is a crash regression. `more-than:` is free
        // text an author types, so it holds whatever they typed — a maths
        // symbol, a currency sign this project does not price, full-width
        // digits. The first draft of `figure_slot` took the last three BYTES off
        // and `pact check` died on the first of these: *"start byte index 1 is
        // not a char boundary; it is inside '≥'"*, exit 101. A checker that
        // panics on a document tells the author nothing at all, which is worse
        // than the hole it was closing (B4, same failure, different field).
        ("mathsymbol", "\"≥5 USD\""),
        ("euro", "\"€5\""),
        ("pound", "\"£200\""),
        ("fullwidth", "\"２００ USD\""),
    ] {
        let (ok, said) = gated_at(name, written);
        assert!(!ok, "`more-than: {written}` loaded cleanly:\n{said}");
        assert!(
            said.contains("rule: loader/threshold-is-not-a-figure"),
            "`{written}` has no figure in it and was let through:\n{said}"
        );
        assert!(
            said.contains("is not a figure at all"),
            "it is not an overflowed figure, it is not a figure:\n{said}"
        );
    }
}

#[test]
fn the_fix_offered_is_a_line_a_person_who_is_not_a_programmer_can_type() {
    // The reader is a domain expert with no source to read. "Non-finite" is not
    // a word that appears anywhere, and the fix has to show both shapes the
    // field takes, because which one is right depends on the tool's `takes:`.
    let (_, said) = gated_at("fixline", "NaN USD");
    assert!(
        said.contains("fix: Write the figure a person should be asked above"),
        "{said}"
    );
    assert!(
        said.contains("`more-than: 200 USD`"),
        "the money spelling:\n{said}"
    );
    assert!(
        said.contains("`more-than: 80`"),
        "and the score spelling:\n{said}"
    );
    for jargon in ["NaN", "non-finite", "IEEE", "f64", "float"] {
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
fn a_fix_line_never_proposes_a_threshold_this_would_refuse() {
    // THE INVARIANT, not the wording. `loader/compared-in-the-wrong-shape` built
    // its advice by interpolating the author's own token — "like `{written}
    // USD`" — so whatever was wrong with the token was inherited by the line
    // telling them how to fix it. Measured, two runs: `more-than: NaN$` was
    // refused with *"fix: … like `NaN$ USD`"*, and `more-than: NaN$ USD` then
    // printed "OK — loaded cleanly (498 settings)" and exited 0, with
    // `_atom_stops` answering True for a 1 USD refund. The tool talked the
    // author into the exact document this suite exists to refuse.
    //
    // So the test is mechanical: take the replacement the fix line actually
    // proposes, put it back in the file, and run the checker over it again. The
    // wording may change; this may not.
    for (name, written) in [
        ("echo_bare", "200"),
        ("echo_grouped", "'1,000'"),
        ("echo_attached", "200USD"),
        ("echo_prefix", "'USD 200'"),
        ("echo_score", "80"),
    ] {
        let (ok, said) = gated_at(name, written);
        assert!(
            !ok,
            "`more-than: {written}` is not money and should be refused:\n{said}"
        );
        assert!(
            said.contains("loader/compared-in-the-wrong-shape"),
            "{said}"
        );
        let fix = said
            .lines()
            .find(|l| l.trim_start().starts_with("fix:"))
            .unwrap_or_else(|| panic!("no fix line:\n{said}"));
        let proposed = fix
            .split('`')
            .nth(1)
            .unwrap_or_else(|| panic!("the fix proposes nothing to type: {fix}"));
        // Quoted going back in, because the fixture writes its rules as a YAML
        // FLOW mapping and `1,000 USD` carries a comma. That is this fixture's
        // punctuation, not the advice's: the same line in a block mapping needs
        // no quotes. What is being tested is the figure, not the braces.
        let (ok, after) = gated_at(&format!("{name}_again"), &format!("'{proposed}'"));
        assert!(
            ok,
            "doing exactly what the fix said (`more-than: {proposed}`) did not load:\n{after}"
        );
        assert!(
            !after.contains("loader/threshold-is-not-a-figure"),
            "the fix line proposed a threshold with no figure in it:\n{after}"
        );
    }
}

#[test]
fn a_threshold_past_the_end_of_counting_is_not_told_it_is_not_a_figure() {
    // `1e400` and `inf` are one `f64::INFINITY` after the parse and two
    // different mistakes. Somebody who wrote `1e400 USD` wrote a figure, and
    // being told it "is not a figure at all" sends them hunting a typo that is
    // not there.
    let (ok, said) = gated_at("overflow", "1e400 USD");
    assert!(!ok, "`more-than: 1e400 USD` loaded cleanly:\n{said}");
    assert!(
        said.contains("rule: loader/threshold-is-not-a-figure"),
        "{said}"
    );
    assert!(
        said.contains("is a larger figure than this can keep track of"),
        "it is a figure, and too big a one:\n{said}"
    );
    assert!(
        !said.contains("is not a figure at all"),
        "wrong of the two sentences:\n{said}"
    );
}

#[test]
fn one_mistake_still_gets_one_message() {
    // `NaN USD` is spelled exactly the way the money argument it gates is
    // spelled, so `loader/compared-in-the-wrong-shape` has nothing to say about
    // it — and telling somebody to "write the figure the way the argument is
    // declared" when that is what they did is a dead end. Held here because the
    // suppression is a deliberate early return in that check and would be easy
    // to drop while tidying.
    let (_, said) = gated_at("one", "NaN USD");
    assert!(
        !said.contains("loader/compared-in-the-wrong-shape"),
        "two messages for one edit:\n{said}"
    );
    assert_eq!(
        said.matches("loader/threshold-is-not-a-figure").count(),
        1,
        "one line, one complaint:\n{said}"
    );

    // AND THE SPELLING THAT ACTUALLY REACHES THE SUPPRESSION. `NaN USD` above
    // ends in a currency, so the shape check's own `is_money == looks_like_money`
    // sends it away one line later whether the early return is there or not —
    // MEASURED: with it deleted, all 76 test binaries in `pact-loader` and
    // `pact-cli` stayed green. `.nan` carries no currency on a money argument,
    // so the shape check has a complaint and the suppression is the only thing
    // stopping it, with a fix line reading "write the figure the way the
    // argument is declared, like `.nan USD`" — which is advice to write the
    // value this whole check exists to refuse.
    let (_, said) = gated_at("one_bare", ".nan");
    assert!(
        !said.contains("loader/compared-in-the-wrong-shape"),
        "the shape is not what is wrong with `.nan`, and the fix it offers is `.nan USD`:\n{said}"
    );
    assert_eq!(
        said.matches("loader/threshold-is-not-a-figure").count(),
        1,
        "one line, one complaint:\n{said}"
    );

    // THE THIRD NEIGHBOUR, and the one the first round never considered. The
    // suppression above was aimed at the shape check in the same module;
    // `currency.rs` is a different module and was never asked. MEASURED on
    // `more-than: 200 NaN`, one run, two errors from one token: one saying NAN
    // is a currency this workspace could genuinely deal in and offering to price
    // it in `models/catalog.yaml`, the other saying the value "is not a figure at
    // all" — of a value that plainly contains `200`. Two messages that
    // contradicted each other about what was wrong.
    //
    // Both halves are settled. `no_figure_in` now looks only at the FIGURE slot,
    // so `200 NaN` is a figure in a currency nothing prices and draws the
    // currency error alone…
    let (ok, said) = gated_at("currency_only", "200 NaN");
    assert!(!ok, "`more-than: 200 NaN` loaded cleanly:\n{said}");
    assert!(said.contains("loader/currency-nothing-can-price"), "{said}");
    assert!(
        !said.contains("loader/threshold-is-not-a-figure"),
        "`200` is a figure, whatever currency follows it:\n{said}"
    );
    // …and `NaN JPY`, where both checks really do have something to say, gets
    // the more fundamental one: a value with no readable figure has nothing to
    // price.
    let (ok, said) = gated_at("figure_first", "NaN JPY");
    assert!(!ok, "`more-than: NaN JPY` loaded cleanly:\n{said}");
    assert!(said.contains("loader/threshold-is-not-a-figure"), "{said}");
    assert!(
        !said.contains("loader/currency-nothing-can-price"),
        "there is no figure here to price:\n{said}"
    );
}

#[test]
fn a_gate_that_stops_for_a_person_on_any_spend_at_all_is_left_alone() {
    // THE DECISION, at the far end of the same check. A threshold is not a
    // ceiling: `more-than: 0 USD` means "ask a person about every refund", which
    // is a workspace being strict, and `-5 USD` is the same rule written oddly.
    // Neither can stop a run the way a zero CEILING does — nothing runs out
    // against a gate — so neither is refused, and the floor added to money in
    // `Schema::check_floor` deliberately never reaches this field.
    //
    // ASSERTED, not disjoined. This loop used to read
    // `ok || !said.contains("loader/threshold-is-not-a-figure")`, which lets the
    // document start being REFUSED under any other rule id and stay green.
    // Measured: an extra `loader/threshold-below-the-floor` for any threshold
    // parsing `<= 0.0` kept this binary at 6 passed while the shipped checker
    // refused the decision's own example — the decision was held only by
    // `test_a_spend_cap_that_can_never_be_reached.py`, one language over, and
    // not where this docstring says it lives.
    for (name, written) in [("zero", "0 USD"), ("neg5", "-5 USD")] {
        let (ok, said) = gated_at(name, written);
        assert!(
            ok,
            "`more-than: {written}` is a strict gate, not a broken one:\n{said}"
        );
    }

    // AND THE FIGURES THE READER USED TO MISREAD. Every one of these is a
    // perfectly good figure, so this file must go on accepting them — the defect
    // they carried was in `questions._amount`, which read `.50 USD` as 50 and
    // `-.5 USD` as +5. Pinned here so that "just refuse the odd spellings" is
    // not available as a cheaper answer than fixing the reader, and pinned on
    // the other side, with the figure each one is read back as, in
    // `adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py`.
    for (name, written) in [
        ("cents", "$.50"),
        ("centsusd", ".50 USD"),
        ("halfusd", ".5 USD"),
        ("negcents", "-.5 USD"),
        ("exponent", "1e5 USD"),
        ("grouped", "'1,000 USD'"),
        ("plus", "+5 USD"),
    ] {
        let (ok, said) = gated_at(name, written);
        assert!(
            ok,
            "`more-than: {written}` is a figure and must load:\n{said}"
        );
    }

    // A bare `80` on a money argument IS refused, and by the right rule — the
    // shape, not the figure. Kept as the weaker assertion because that refusal
    // is A3's and not this file's.
    let (_, said) = gated_at("score", "80");
    assert!(
        !said.contains("loader/threshold-is-not-a-figure"),
        "`80` is a figure; what is wrong with it is its shape:\n{said}"
    );

    // POSITIVE CONTROL: the same edits through the same helper, with the one
    // value that must be refused. Without this, deleting the check entirely
    // would leave the loops above green.
    let (ok, said) = gated_at("control", "NaN USD");
    assert!(
        !ok && said.contains("loader/threshold-is-not-a-figure"),
        "{said}"
    );
}

#[test]
fn a_second_route_to_the_same_field_is_walked_too() {
    // THE GROWTH HAZARD, DEMONSTRATED RATHER THAN ASSERTED ABOUT. The guard in
    // `crates/pact-loader/src/currency.rs` pins the set of `may-be-money` FIELD
    // NAMES at `{more-than}` and tells the next author to "teach
    // `a_threshold_that_is_not_a_figure` to reach the new field". It cannot see
    // a second route to the SAME field: `spec/schema.yaml` references
    // `group:question-rule` in exactly one place today, and one more line of
    // YAML adds no field name at all.
    //
    // MEASURED, before the walk was generalised, with `ask-a-person: {type: list
    // of group:question-rule}` added to the `agent` group of a copy of the
    // specification and an agent carrying
    // `- {tool: payments/issue-refund, arg: amount, more-than: NaN USD}`:
    // "OK — … loaded cleanly (507 settings)", exit 0 — with every test in the
    // repository, that guard included, green.
    //
    // The fix was not a second hard-coded path. `money::every_gate` walks the
    // DOCUMENT for the key wherever it is written, exactly as `currency::walk`
    // already did for its own field names, so there is no path left to forget.
    // No repository file is touched: the spec is a copy under `PACT_SPEC`, read
    // only with `--unsafe-spec` and only by a debug binary.
    let spec = std::fs::read_to_string(format!(
        "{}/../../spec/schema.yaml",
        env!("CARGO_MANIFEST_DIR")
    ))
    .expect("the shipped specification");
    let anchor = "  agent:\n    fields:\n      name:";
    assert!(
        spec.contains(anchor),
        "the specification drifted: no `agent` group at {anchor:?}"
    );
    let second_path = spec.replacen(
        anchor,
        "  agent:\n    fields:\n      ask-a-person:\n        \
         type: list of group:question-rule\n        surface: S-EXEC\n        \
         tier: core\n        help: a second route to the same field\n      name:",
        1,
    );

    let root = edited(
        "secondroute",
        "policies/approvals.yaml",
        "ask-a-person:",
        "ask-a-person:",
    );
    let spec_at = std::path::Path::new(&root).join("schema-second-route.yaml");
    std::fs::write(&spec_at, &second_path).unwrap();
    let agent = std::path::Path::new(&root).join("agents/refund-desk/agent.yaml");
    let mut text = std::fs::read_to_string(&agent).unwrap();
    text.push_str(
        "\nask-a-person:\n  - when:\n      - { tool: payments/issue-refund, arg: amount, \
         more-than: NaN USD }\n    because: a second route to the same field\n    \
         question: is-this-ok\n",
    );
    std::fs::write(&agent, text).unwrap();

    let out = pact()
        .args(["check", &root, "--unsafe-spec"])
        .env("PACT_SPEC", &spec_at)
        .output()
        .expect("runs");
    let said =
        String::from_utf8_lossy(&out.stdout).into_owned() + &String::from_utf8_lossy(&out.stderr);
    let _ = std::fs::remove_dir_all(&root);

    assert!(
        said.contains("from PACT_SPEC"),
        "the modified specification was not the one used, so this proves nothing:\n{said}"
    );
    assert!(
        !out.status.success(),
        "a second route to `more-than:` loaded cleanly:\n{said}"
    );
    assert!(
        said.contains("rule: loader/threshold-is-not-a-figure"),
        "the walk still knows one path rather than one field:\n{said}"
    );
    assert!(
        said.contains("agent.yaml:"),
        "the caret must land where the second route was written:\n{said}"
    );
}
