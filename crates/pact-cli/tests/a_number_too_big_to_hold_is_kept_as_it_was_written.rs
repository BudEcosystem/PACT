//! A number too big for the machine to hold keeps what the author wrote,
//! instead of quietly becoming nothing at all.
//!
//! AC-1.3 says an unknown `x-` field "round-trips untouched through import → IR
//! → export". The NAME round-tripped; the VALUE did not. `1e999` parses happily
//! as a floating-point number and comes back as infinity, and infinity is not
//! something JSON can write down — so it left as `null`, with no problem
//! reported by `pact check` and nothing in `pact show` to say a value had been
//! lost:
//!
//! ```text
//! $ cat agents/desk/agent.yaml
//! name: Desk
//! description: A desk.
//! instructions: Do it.
//! x-threshold: 1e999
//! x-note: 1e400
//!
//! $ pact show .
//!       "x-threshold": null,
//!       "x-note": null
//!
//! $ pact check .
//! OK — ws loaded cleanly (14 settings).
//! $ echo $?
//! 0
//! ```
//!
//! Worse than the display: the digest is computed over that same `null`, so a
//! document saying `x-threshold: 1e999` and a document saying `x-threshold:`
//! hashed to the same thing, and a lockfile could not tell them apart.
//!
//! The answer is the one the leading-zero rule two lines above it in
//! `resolve_scalar` already takes: a scalar this cannot hold as a number is not
//! turned into a different number, it is kept exactly as it was written, as
//! text. Nothing is lost, which is what `x-` promises.
//!
//! **Where the specification does say a number is wanted**, keeping the text is
//! only half an answer — `settings: temperature: 1e999` would then be refused as
//! *"should be a number, but it is some text"*, which is the sentence this repo
//! condemns three times over for a line that is spelled correctly and simply
//! does not fit (`pact-schema/src/lib.rs:1659`, `:1698`, and the sibling test
//! `a_size_this_cannot_count_is_refused_rather_than_changed`). It is refused by
//! the same door `99999999999999999999h` and `1e400 USD` go through instead:
//! `Schema::check_ceiling`, which knows the field's name and line and can say
//! *"more than this can keep track of"*. Both ends of the number line have their
//! own sentence, because an author told that `-1e999` is "more than" anything
//! would go looking for a smaller number and find the one they already wrote.
//!
//! **`inf` and `nan` are deliberately NOT that.** They carry no digit, so they
//! are words spelled where a figure goes, and they stay `schema/wrong-type` —
//! the same line `money_past_counting` draws for `1e400 USD` against `inf USD`.
//!
//! **What this file does not cover, and where the rest of it lives now.** The
//! bottom of the same scale rewrites what the author wrote by a different route:
//! `x-tiny: 1e-999` underflows to `0.0`, and for a round `pact check` said
//! nothing and it digested identically to an authored `x-tiny: 0` — the same
//! digest collision as above. It was left out of THIS file because it is a
//! different judgement — `1e999` cannot be held AT ALL and so is a category
//! error, while `1e-999` is held as a representable number that is merely the
//! wrong one, and the general rule that would catch it, "only accept a float
//! that round-trips its own text", refuses `1e10` too, which comes back as
//! `10000000000.0` and is a number nobody would call corrupted. It was recorded
//! as **C10** in `docs/70-PRODUCTION-GAP-REGISTER.md` rather than left in a
//! review transcript, and it is now closed by its own narrow rule, in its own
//! sibling file: `a_number_too_small_to_hold_is_kept_as_it_was_written.rs`.
//!
//! **THE SPELLING THIS FILE SHIPPED A COUNTER-EXAMPLE TO, AND THE ROUNDS THAT
//! CLOSED IT.** For one round the claim in this file's own title was false in
//! the shipped binary and all nine tests here were green over it. A bare run of
//! digits past `i64` — `x-big: 99999999999999999999` — is not `1e999`: it
//! parses to `1e20`, which is perfectly FINITE, so the `&& f.is_finite()` guard
//! could not see it by construction. It became a `Value::Float`, `pact show`
//! printed `1e+20` where twenty nines had been written, and three workspaces
//! differing only in that line — `…9999`, `…9998` and `100000000000000000000` —
//! all published
//! `sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888`.
//! One hash for three documents: verbatim the lockfile harm four paragraphs up,
//! with the value rewritten instead of deleted. On `settings: temperature:` the
//! same line loaded clean, exit 0, and handed the runtime `1e20`.
//!
//! **AND THE ROUND AFTER THAT, WHICH IS WHY THE RULE IS ABOUT THE FIGURE.** The
//! rule written to close it read *"a run of ASCII digits that `i64` cannot
//! parse"* — a rule about how a figure is PUNCTUATED — and it was one character
//! wide. Measured through the shipped binary with the fix fully in place:
//!
//! ```text
//! x-big: 99999999999999999999.0   -> sha256:2aa9f0c926a7fe…
//! x-big: 99999999999999999998.0   -> sha256:2aa9f0c926a7fe…
//! x-big: 100000000000000000000.0  -> sha256:2aa9f0c926a7fe…
//! settings: temperature: 99999999999999999999.0 -> OK — loaded cleanly, exit 0
//! pact show                                     -> "temperature": 1e+20
//! ```
//!
//! One hash for three documents again, byte for byte the hash this file names as
//! the harm, and the runtime handed a figure nobody wrote. The same rule made
//! the ceiling disagree with itself about one value: `temperature: 1e19` loaded
//! cleanly while `temperature: 10000000000000000000` — the same `f64` to the
//! last bit, and exactly representable — was refused as *"more than this can
//! keep track of"*, a sentence the first line proves false. `coerce::size` had
//! the mirror: `context-at-least: 1e19` was *"not a size"* and
//! `context-at-least: 10000000000000000000` loaded cleanly.
//!
//! So both halves now ask about the FIGURE, in one place each:
//!
//! * `pact_doc::whole_number_past_holding` — the document layer's question. Does
//!   the whole number this text spells come back out of the `f64` as the same
//!   whole number? `99999999999999999999` writes back `100000000000000000000`
//!   and `9223372036854775808` writes back `9223372036854776000`, so both are
//!   kept as text; `1e10`, `1e20` and `10000000000000000000` write back exactly
//!   what was written and stay numbers. It cannot be dodged with a `.` or an
//!   `e`, because it never looks at either.
//! * `coerce::PAST_COUNTING` — the schema layer's. 2^53 is the last whole number
//!   a double can tell from its neighbour, which is precisely what *"more than
//!   this can keep track of"* has always claimed. `Ty::Number`, `Ty::Threshold`
//!   and `Ty::Size` all ask it, so one figure gets one answer whichever field
//!   and whichever spelling it arrives in. `Ty::Integer` keeps `i64`, because
//!   there the machine really is an `i64`.
//!
//! **What is deliberately NOT past holding.** `0.1` and `0.7` are not whole
//! numbers, and ordinary rounding near one is what every double does — refusing
//! it would mean refusing every number in the format. The bound that leaves is
//! recorded rather than hidden: a FRACTIONAL literal past 2^53, such as
//! `x-big: 9999999999999999999999e-2`, still rounds onto its neighbour and still
//! digests with it. `inf` and `nan` are words spelled where a figure goes and
//! stay `schema/wrong-type`, at every one of the five doors.
//!
//! **The types that were still giving the false sentence, and the round each was
//! closed in.** `context-at-least: 1e999` and `tool-calls-at-most:
//! 9223372036854775808` were closed with the digits rule and are pinned in
//! `a_size_this_cannot_count_is_refused_rather_than_changed` and here. Four more
//! were found by attacking that fix rather than reading it, all measured through
//! the shipped binary:
//!
//! * `finishes-within: 1e999s`, `1e300h`, `1e999 seconds`, `1e400 ms` — *"but it
//!   is some text"*, about a line carrying exactly the unit the help prescribes,
//!   because only the BARE spelling had been closed and the parse loop read the
//!   `e` of a unit-carrying figure as a unit called `e`. `1e6s`, an ordinary
//!   million seconds, got it too. The loop now reads an exponent as part of the
//!   figure, and `pact_adapters.limits.seconds` and the TypeScript port were
//!   moved with it — a spelling the gate passes and the reader answers `None` to
//!   is no ceiling at all.
//! * `tokens-at-most: 1e6` — *"should be a whole number, but it is a number"*,
//!   with the fix *"Change it to a whole number"*, about a line that says one
//!   million.
//! * `when-full: 1e999%` — *"should be a percentage, like `90%`, but it is some
//!   text"*, while `1e-999%` one round earlier had been named. One field reading
//!   correctly at one end only.
//! * `finishes-within: inf` — the mutation below shows this had NO test in the
//!   repository; the guard that kept a word from being called a figure was
//!   deletable with the whole suite green.
//!
//! **The fix line was false, and its test only checked it was present.**
//! *"or any smaller number"* — measured, `temperature: 1e999` was refused with
//! that fix and `temperature: 9223372036854775808`, a smaller number written in
//! obedience to it, was refused by the identical rule. The sentence now names a
//! set the checker really accepts, and `the_fix_is_followed_rather_than_matched`
//! types the offered line back into the file instead of matching the string.
//!
//! **THE MUTATIONS.** Thirteen edits hold this, in three files. Each was applied
//! on its own, rebuilt, and the counts below are what `cargo test -p pact-cli
//! --test a_number_too_big_to_hold_is_kept_as_it_was_written` then printed —
//! measured on this tree, against these nineteen tests. The baseline is
//! `19 passed; 0 failed`.
//!
//! **A** — drop `&& f.is_finite()` from the float arm of `resolve_scalar`
//! (`crates/pact-doc/src/yaml.rs`). `14 passed; 5 failed`:
//! `a_number_too_big_to_hold_survives_show`,
//! `a_number_field_given_one_is_refused_by_name`,
//! `a_number_field_given_the_far_bottom_end_says_so`,
//! `a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo`,
//! `a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo`.
//! `cargo test -p pact-doc --lib`: `51 passed; 2 failed`.
//!
//! **B** — drop the `Coerced::Number(n) if past_counting_figure` arm from
//! `Schema::check_ceiling`. `14 passed; 5 failed`: the two `1e999` number tests,
//! `a_number_field_given_a_whole_number_past_holding_is_refused_by_name`,
//! `one_figure_gets_one_answer_however_it_is_spelled`,
//! `the_fix_is_followed_rather_than_matched`.
//!
//! **C** — drop the `Coerced::Threshold` arm from that same match.
//! `17 passed; 2 failed`: `a_bar_no_score_could_ever_clear_is_refused_too` and
//! `one_figure_gets_one_answer_however_it_is_spelled`.
//!
//! **D** — drop the word-or-figure guard from `coerce::number` (replace the
//! whole condition with `Some(f)`). `18 passed; 1 failed`:
//! `the_word_infinity_where_a_number_goes_is_still_a_typo`, which now gets a
//! figure's sentence about a word. `pact-schema --lib`: `56 passed; 1 failed`
//! (`a_figure_past_the_end_is_kept_and_a_word_is_not`).
//!
//! **E** — drop the `whole_number_past_holding` arm from `resolve_scalar`, the
//! one that keeps a whole number a double would rewrite. `14 passed; 5 failed`:
//! `a_whole_number_too_big_to_hold_survives_show_too`,
//! `three_documents_that_differ_do_not_digest_the_same`,
//! `a_number_field_given_a_whole_number_past_holding_is_refused_by_name`,
//! `a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo`,
//! `the_bottom_end_of_a_length_of_time_and_a_size_is_not_called_text_either`.
//! `pact-doc --lib`: `51 passed; 2 failed`.
//!
//! **F** — narrow `coerce::past_counting_figure` back to `!v.is_finite()`, i.e.
//! keep the overflow half and drop the 2^53 half. `15 passed; 4 failed`:
//! `one_figure_gets_one_answer_however_it_is_spelled`,
//! `the_fix_is_followed_rather_than_matched`,
//! `a_number_field_given_a_whole_number_past_holding_is_refused_by_name`,
//! `a_bar_no_score_could_ever_clear_is_refused_too`. `pact-schema --lib`:
//! `56 passed; 1 failed`.
//!
//! **G** — put the digits-only rule back inside
//! `pact_doc::whole_number_past_holding` (`digits.all(is_ascii_digit) &&
//! parse::<i64>().is_err()`), which is the exact rule the round before this one
//! shipped. `17 passed; 2 failed`:
//! `three_documents_that_differ_do_not_digest_the_same` and
//! `a_number_field_given_a_whole_number_past_holding_is_refused_by_name` — the
//! `.0` spelling collapses to one hash again. `pact-doc --lib`:
//! `50 passed; 3 failed`.
//!
//! **H** — drop the `Value::Float` arm from `coerce::size`. `18 passed; 1
//! failed`: `one_figure_gets_one_answer_however_it_is_spelled`, where
//! `context-at-least: 1e19` goes back to being called text.
//! `pact-schema --lib`: `56 passed; 1 failed`.
//!
//! **I** — make `coerce::integer` refuse anything with a point or an exponent
//! again. `17 passed; 2 failed`:
//! `a_whole_number_field_takes_a_whole_number_however_it_is_punctuated` and
//! `a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo`.
//! `pact-schema --lib`: `56 passed; 1 failed`.
//!
//! **J** — make `coerce::duration`'s exponent test always false, so the `e` of
//! `1e999s` is a unit again. `18 passed; 1 failed`:
//! `a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo`.
//!
//! **K** — drop the `Value::Float` arm for `Ty::Duration` (the bare figure no
//! unit could save). `18 passed; 1 failed`: the same test, on `1e308`.
//!
//! **L** — disable the `Coerced::PercentPastHolding` arm of `check_ceiling`.
//! `18 passed; 1 failed`: `a_share_of_the_whole_reads_the_same_at_both_ends`.
//!
//! **M** — put `node.as_str()` back in `check_floor`'s `Size(0)` guard, where
//! `as_written(node)` now is. `18 passed; 1 failed`:
//! `one_figure_gets_one_answer_however_it_is_spelled`, whose last block is the
//! silence this repair opened and closed — a bare `context-at-least: 0.5`
//! loading cleanly as a context window of zero. It was measured red BEFORE the
//! block was written, which is the only reason the block exists.
//!
//! No test here is red under all thirteen, and none of the schema-side edits
//! touches `a_number_too_big_to_hold_survives_show` or
//! `a_whole_number_too_big_to_hold_survives_show_too`, which are the two that
//! carry the `x-` claim.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A one-agent workspace whose `agent.yaml` holds `extra`, returned as a path.
fn workspace(name: &str, extra: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-toobig-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).expect("makes the tree");
    std::fs::write(
        dst.join("workspace.yaml"),
        "name: desk-shop\ndescription: A workspace.\n",
    )
    .expect("writes the workspace");
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        format!("name: Desk\ndescription: A desk.\ninstructions: Do it.\n{extra}"),
    )
    .expect("writes the agent");
    dst
}

fn shown(root: &std::path::Path) -> String {
    let out = pact()
        .args(["show", &root.to_string_lossy()])
        .output()
        .expect("runs");
    let text = String::from_utf8_lossy(&out.stdout).into_owned();
    assert!(out.status.success(), "`pact show` must succeed:\n{text}");
    text
}

/// The `sha256:` a workspace publishes through `pact discover` — the figure a
/// lockfile pins, and the one that must differ when the document does.
fn digest(root: &std::path::Path) -> String {
    let out = pact()
        .args(["discover", &root.to_string_lossy()])
        .output()
        .expect("runs");
    let text = String::from_utf8_lossy(&out.stdout).into_owned();
    assert!(
        out.status.success(),
        "`pact discover` must succeed:\n{text}"
    );
    let at = text
        .find("sha256:")
        .unwrap_or_else(|| panic!("a digest is published:\n{text}"));
    text[at..].chars().take_while(|c| *c != '"').collect()
}

/// `pact check`, returning what the author is shown and whether it passed.
fn checked(root: &std::path::Path) -> (bool, String) {
    let out = pact()
        .args(["check", &root.to_string_lossy()])
        .output()
        .expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

#[test]
fn a_number_too_big_to_hold_survives_show() {
    let root = workspace(
        "show",
        "x-threshold: 1e999\nx-note: 1e400\nx-below: -1e999\n",
    );
    let text = shown(&root);

    assert!(
        text.contains(r#""x-threshold": "1e999""#),
        "what the author wrote must come back out:\n{text}"
    );
    assert!(
        text.contains(r#""x-note": "1e400""#),
        "the same at the other size:\n{text}"
    );
    assert!(
        text.contains(r#""x-below": "-1e999""#),
        "and at the bottom of the number line too:\n{text}"
    );
    assert!(
        !text.contains("null"),
        "no value may vanish into nothing:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_whole_number_too_big_to_hold_survives_show_too() {
    // THE THIRD SPELLING, and for a round it was the one the guard could not
    // see. `99999999999999999999` is not `1e999` — it parses to `1e20`, which
    // is perfectly finite, so `f.is_finite()` waved it through and `pact show`
    // printed `1e+20` where the author had written twenty nines. The claim this
    // file makes is about a number too big to HOLD, and `i64` refusing to parse
    // this one is the machine saying exactly that.
    let root = workspace(
        "showint",
        "x-a: 99999999999999999999\nx-b: 9223372036854775808\nx-c: -99999999999999999999\n\
         x-d: 1234567890123456789012345678901234567890\n",
    );
    let text = shown(&root);

    for (field, written) in [
        ("x-a", "99999999999999999999"),
        // One past `i64::MAX`, which is the exact edge of what can be held.
        ("x-b", "9223372036854775808"),
        ("x-c", "-99999999999999999999"),
        ("x-d", "1234567890123456789012345678901234567890"),
    ] {
        assert!(
            text.contains(&format!(r#""{field}": "{written}""#)),
            "`{field}` must come back as the digits that were written:\n{text}"
        );
    }
    assert!(
        !text.contains("e+"),
        "no figure may come back in a notation nobody wrote:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // And the edge itself is NOT touched: `i64::MAX` is held exactly, so it is
    // a number and stays one. A rule that took this too would be refusing
    // something legitimate.
    let root = workspace("showedge", "x-max: 9223372036854775807\n");
    let text = shown(&root);
    assert!(
        text.contains(r#""x-max": 9223372036854775807"#),
        "the largest whole number this CAN hold is still a number:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn three_documents_that_differ_do_not_digest_the_same() {
    // The harm stated as the thing a lockfile does, for the integer spelling.
    // Measured before this: all three of these published
    // `sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888`
    // — one hash for three documents an author would call three different
    // documents, because all three arrived as the same `1e20`.
    let a = workspace("dg-a", "x-big: 99999999999999999999\n");
    let b = workspace("dg-b", "x-big: 99999999999999999998\n");
    let c = workspace("dg-c", "x-big: 100000000000000000000\n");
    let (da, db, dc) = (digest(&a), digest(&b), digest(&c));
    assert_ne!(da, db, "two figures one apart are two documents");
    assert_ne!(db, dc, "and so are these two");
    assert_ne!(da, dc, "and so are these two");
    for root in [a, b, c] {
        let _ = std::fs::remove_dir_all(&root);
    }

    // AND THE SAME THREE WITH A POINT ON THE END, which is where the rule that
    // keyed on a run of ASCII digits could not follow — so the collapse this
    // test was written to delete was still live, one character away, with the
    // fix fully in place. Measured on that build: all three of these published
    // `sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888`,
    // the byte-identical hash this test's own note calls the harm, and
    // `settings: temperature: 99999999999999999999.0` loaded cleanly and handed
    // the runtime `1e+20`.
    let a = workspace("dg-a-pt", "x-big: 99999999999999999999.0\n");
    let b = workspace("dg-b-pt", "x-big: 99999999999999999998.0\n");
    let c = workspace("dg-c-pt", "x-big: 100000000000000000000.0\n");
    let (da, db, dc) = (digest(&a), digest(&b), digest(&c));
    assert_ne!(da, db, "a point on the end does not make two documents one");
    assert_ne!(db, dc, "and neither does it here");
    assert_ne!(da, dc, "nor here");
    for root in [a, b, c] {
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_number_too_big_to_hold_is_not_a_problem_of_its_own() {
    // `x-` is the author's own space and PACT does not read it, so keeping the
    // text is the whole answer here — there is nothing to complain about.
    let root = workspace("check", "x-threshold: 1e999\n");
    let out = pact()
        .args(["check", &root.to_string_lossy(), "--deny-warnings"])
        .output()
        .unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "an `x-` field PACT does not read must load:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_number_field_given_one_is_refused_by_name() {
    // The other side of keeping it as text: where the specification says a
    // number is wanted, `1e999` is refused at the author's own line instead of
    // loading clean and holding nothing — and refused by the sentence for a
    // line that is spelled correctly, not the one for a typo.
    let root = workspace("typed", "settings:\n  temperature: 1e999\n");
    let (ok, text) = checked(&root);

    assert!(!ok, "a number field must not quietly hold nothing:\n{text}");
    assert!(
        text.contains("schema/too-big-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        !text.contains("schema/wrong-type"),
        "`1e999` is spelled the way a number is spelled; sending its author \
         hunting for a typo is the thing this rule exists to stop:\n{text}"
    );
    assert!(
        text.contains("'temperature' is 1e999, which is more than this can keep track of."),
        "the sentence must name the value and say what is wrong with it:\n{text}"
    );
    assert!(
        text.contains("agent.yaml:5"),
        "must name the file and the line:\n{text}"
    );
    assert!(
        text.contains(
            "fix: Write `temperature: 10`, or any figure of fifteen digits or fewer, or remove \
             the line."
        ),
        "the fix must be typeable:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_is_followed_rather_than_matched() {
    // THE BLIND SPOT THIS FILE DIAGNOSED IN ANOTHER TEST AND THEN HAD ITSELF:
    // every guard on the sentence above checks that a fix string is PRESENT,
    // never that the sentence is TRUE. It said *"or any smaller number"*, and
    // the accepted set does not run downward — measured through the shipped
    // binary, `temperature: 1e999` was refused with that fix and
    // `temperature: 9223372036854775808`, a smaller number written in obedience
    // to it, was refused by the identical rule, as were `9999999999999999999`
    // and `9300000000000000000`. Meanwhile `1e19`, which is LARGER than the
    // first of those, loaded cleanly.
    //
    // So this test does what a reader would do: it takes the fix the checker
    // offers, types it into the file, and requires the workspace to load.
    let root = workspace("follow", "settings:\n  temperature: 99999999999999999999\n");
    let (ok, text) = checked(&root);
    assert!(!ok, "the figure must be refused to begin with:\n{text}");

    let at = text.find("fix: Write `").expect("a fix is offered");
    let offered: String = text[at + "fix: Write `".len()..]
        .chars()
        .take_while(|c| *c != '`')
        .collect();
    assert_eq!(offered, "temperature: 10", "the fix names a line to type");
    let _ = std::fs::remove_dir_all(&root);

    // The line the fix offers, and then the set it promises. Fifteen digits is
    // what the sentence says is held, so fifteen digits must load — at both
    // ends of the scale, because the sentence at the bottom end offers the same
    // set.
    for written in ["10", "999999999999999", "-999999999999999", "0.7"] {
        let root = workspace(
            "followed",
            &format!("settings:\n  temperature: {written}\n"),
        );
        let (ok, text) = checked(&root);
        assert!(
            ok,
            "the checker offered `{written}` (or promised it) and must accept it:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // And the promise is kept one type over, where the same sentence is used.
    for (block, written) in [
        (
            "needs:\n  because: strong.\n  context-at-least: {}\n",
            "999999999999999",
        ),
        (
            "limits:\n  tokens-at-most: {}\n  when-it-runs-out: stop-and-say-so\n",
            "999999999999999",
        ),
    ] {
        let root = workspace("followed-other", &block.replace("{}", written));
        let (ok, text) = checked(&root);
        assert!(
            ok,
            "`{written}` is inside the set the fix promises:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // AND AT THE OTHER TWO DOORS THAT PRINT A SET, which for one round this
    // repair did not reach. It replaced the false sentence on `Ty::Number` and
    // `Ty::Threshold` and left `Ty::Size` saying *"or any smaller number"* and
    // `Ty::Duration` saying *"or any shorter length of time"* — both false in
    // exactly the demonstrated way. Measured through the shipped binary before
    // the arms were corrected: `context-at-least: 1e19` was refused with *"any
    // smaller number"* and the smaller `1e16` and `9007199254740992.0` were
    // refused with it; `finishes-within: 1e999s` was refused with *"any shorter
    // length of time"* and the shorter `1e300h` and `18446744073709551616ms`
    // were refused with it. Nothing in the repository asserted either string,
    // which is why the first repair could stop halfway and stay green.
    //
    // So: refuse the figure, require the sentence not to promise a set that
    // does not hold, then type a member of the set it does promise and require
    // the workspace to load.
    for (block, refused, promised) in [
        (
            "needs:\n  because: strong.\n  context-at-least: {}\n",
            "1e19",
            "999999999999999",
        ),
        (
            "limits:\n  finishes-within: {}\n  when-it-runs-out: stop-and-say-so\n",
            "1e999s",
            "1000d",
        ),
    ] {
        let root = workspace("followed-set", &block.replace("{}", refused));
        let (ok, text) = checked(&root);
        assert!(!ok, "`{refused}` must be refused to begin with:\n{text}");
        assert!(
            !text.contains("any smaller number") && !text.contains("any shorter length of time"),
            "`{refused}` is refused and so are the figures below it, so the fix must not send \
             the author downward:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);

        let root = workspace("followed-set-ok", &block.replace("{}", promised));
        let (ok, text) = checked(&root);
        assert!(
            ok,
            "`{promised}` is inside the set the fix now promises:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn one_figure_gets_one_answer_however_it_is_spelled() {
    // THE DEFECT THE `parse::<i64>()` CEILING SHIPPED, AND THE ONE THIS FILE'S
    // OWN TITLE PROMISES AGAINST: the test was of the SPELLING, so one value got
    // two opposite verdicts. Measured through the shipped binary with the first
    // round of this fix fully in place:
    //
    //     settings: temperature: 1e19                  -> OK — loaded cleanly
    //     settings: temperature: 10000000000000000000  -> 'temperature' is …,
    //                                which is more than this can keep track of
    //
    // The two literals are the same `f64` to the last bit
    // (`float('1e19') == float('10000000000000000000')`, and it is exact), so
    // the first line proves the second's sentence false. The size half was the
    // mirror, and this fix's first round created it: `context-at-least: 1e19`
    // was *"not a size"* while `context-at-least: 10000000000000000000` loaded
    // cleanly as a requirement no model can meet.
    for (block, name) in [
        ("settings:\n  temperature: {}\n", "temperature"),
        (
            "needs:\n  because: strong.\n  context-at-least: {}\n",
            "context-at-least",
        ),
    ] {
        for written in ["1e19", "10000000000000000000"] {
            let root = workspace("spelling", &block.replace("{}", written));
            let (ok, text) = checked(&root);
            assert!(
                !ok,
                "`{name}: {written}` is past counting whichever way it is written:\n{text}"
            );
            assert!(
                text.contains("schema/too-big-to-count"),
                "one figure, one rule, for `{name}: {written}`:\n{text}"
            );
            assert!(
                text.contains(&format!(
                    "'{name}' is 10000000000000000000, which is more than this can keep track of."
                )),
                "and one sentence, naming the same figure, for `{written}`:\n{text}"
            );
            let _ = std::fs::remove_dir_all(&root);
        }
    }

    // The comparison against that figure answers the same way, for the same
    // reason `past_counting` gives: a number and a bar to clear are one figure.
    for written in ["> 1e19", "> 10000000000000000000"] {
        let root = workspace(
            "spelling-bar",
            &format!("needs:\n  because: strong.\n  scores:\n    MMLU: \"{written}\"\n"),
        );
        let (ok, text) = checked(&root);
        assert!(!ok, "`{written}` is past counting either way:\n{text}");
        assert!(
            text.contains("schema/too-big-to-count"),
            "one rule for `{written}`:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // THE SILENCE THE DOOR ABOVE OPENED, AND THE ONE THING THAT SHUTS IT.
    // Letting `coerce::size` read a figure the document layer held as a number
    // is what gives `1e19` and `10000000000000000000` one answer — and it also
    // put a `Value::Float` in front of `check_floor`'s zero arm, which asked
    // `node.as_str()` and gets nothing from one. Measured with that arm
    // unchanged: `context-at-least: "0.5"` was `schema/below-the-floor` and the
    // same line without the quotes was `OK — loaded cleanly`, a context window
    // of zero from a line asking for one, which is the silent degradation this
    // whole file is about arriving through this file's own repair.
    for written in ["0.5", "\"0.5\"", "0.9"] {
        let root = workspace(
            "sizefloor",
            &format!("needs:\n  because: strong.\n  context-at-least: {written}\n"),
        );
        let (ok, text) = checked(&root);
        assert!(
            !ok,
            "`{written}` is no tokens at all and must be said so:\n{text}"
        );
        assert!(
            text.contains("schema/below-the-floor"),
            "quoted and unquoted are one rule for `{written}`:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
    // And a zero somebody MEANT is still none of that arm's business.
    let root = workspace(
        "sizezero",
        "needs:\n  because: strong.\n  context-at-least: 0\n",
    );
    let (ok, text) = checked(&root);
    assert!(ok, "an authored zero is a zero and says nothing:\n{text}");
    let _ = std::fs::remove_dir_all(&root);

    // And the edge is where the sentence says it is: 2^53 is the last whole
    // number a double can tell from the next one, so one below it loads and it
    // does not. Nothing that was refused before is accepted now — the bound
    // this replaced was `i64`, which is a thousand times further out.
    for (written, want_ok) in [("9007199254740991", true), ("9007199254740992", false)] {
        let root = workspace("edge", &format!("settings:\n  temperature: {written}\n"));
        let (ok, text) = checked(&root);
        assert_eq!(
            ok, want_ok,
            "`{written}` is on the wrong side of the line:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_whole_number_field_takes_a_whole_number_however_it_is_punctuated() {
    // The same self-contradicting sentence this file was written to delete,
    // still live one type over: measured through the shipped binary,
    // `tokens-at-most: 1e6` was *"should be a whole number, but it is a
    // number"* with the fix *"Change it to a whole number"* — about a line that
    // says one million, which IS a whole number and which an `i64` holds to the
    // last bit. `1000000.0` got the same.
    for written in ["1e6", "1000000.0", "1000000"] {
        let root = workspace(
            "wholeexp",
            &format!("limits:\n  tokens-at-most: {written}\n  when-it-runs-out: stop-and-say-so\n"),
        );
        let (ok, text) = checked(&root);
        assert!(
            ok,
            "`{written}` is a million and is a whole number:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // And the same figure past the end of the machine that holds it is still
    // refused, by the figure and not by the punctuation.
    for written in ["1e19", "9223372036854775808.0"] {
        let root = workspace(
            "wholeexpbig",
            &format!("limits:\n  tokens-at-most: {written}\n  when-it-runs-out: stop-and-say-so\n"),
        );
        let (ok, text) = checked(&root);
        assert!(
            !ok,
            "`{written}` is past what a whole number here can hold:\n{text}"
        );
        assert!(
            text.contains("schema/too-big-to-count"),
            "wrong rule for `{written}`:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // A fraction is still the wrong KIND of figure, and the true sentence about
    // it is the one it already got.
    let root = workspace(
        "wholefrac",
        "limits:\n  tokens-at-most: 1.5\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "`1.5` is not a whole number:\n{text}");
    assert!(
        text.contains("should be a whole number, but it is a number."),
        "the wrong-kind sentence is true about `1.5`:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_share_of_the_whole_reads_the_same_at_both_ends() {
    // The round before this one gave `Ty::Percent` a bottom end and no top, so
    // one field read correctly at one end only. Measured through the shipped
    // binary with the bottom in place: `must-pass: 1e-999%` was *"closer to
    // zero than this can keep track of"* and `must-pass: 1e999%` was *"should
    // be a percentage, like `90%`, but it is some text"* — the sentence this
    // file exists to delete, about a line that is a figure.
    let policy = |v: &str| {
        format!("description: Keeps it tidy.\nwhen-full: {v}\nalways-keep: [the last message]\n")
    };
    for (written, sentence) in [
        (
            "1e999%",
            "'when-full' is 1e999%, which is more than this can keep track of.",
        ),
        (
            "-1e999%",
            "'when-full' is -1e999%, which is further below zero than this can keep track of.",
        ),
    ] {
        let root = workspace("pct", "context-policy: long-threads\n");
        std::fs::create_dir_all(root.join("context-policies")).expect("makes the folder");
        std::fs::write(
            root.join("context-policies/long-threads.yaml"),
            policy(written),
        )
        .expect("writes the policy");
        let (ok, text) = checked(&root);
        assert!(!ok, "`{written}` must be refused:\n{text}");
        assert!(
            text.contains("schema/too-big-to-count"),
            "wrong rule for `{written}`:\n{text}"
        );
        assert!(
            !text.contains("but it is some text"),
            "`{written}` is spelled exactly the way a share is spelled:\n{text}"
        );
        assert!(
            text.contains(sentence),
            "the sentence must quote what was written:\n{text}"
        );
        assert!(
            text.contains(
                "fix: Write `when-full: 90%`, or any share between `0%` and `100%`, \
                           or remove the line."
            ),
            "and the fix must name the set a share lives in:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // `150%` is NOT that, and the difference is the whole point: it is a share
    // this holds perfectly well and simply more than all of it, which is a
    // different thing to tell an author. So is a word.
    for written in ["150%", "inf%"] {
        let root = workspace("pctrange", "context-policy: long-threads\n");
        std::fs::create_dir_all(root.join("context-policies")).expect("makes the folder");
        std::fs::write(
            root.join("context-policies/long-threads.yaml"),
            policy(written),
        )
        .expect("writes the policy");
        let (ok, text) = checked(&root);
        assert!(!ok, "`{written}` must be refused:\n{text}");
        assert!(
            text.contains("schema/wrong-type"),
            "`{written}` did not run off the end of anything:\n{text}"
        );
        assert!(
            !text.contains("too-big-to-count"),
            "a share out of range is not a figure past holding:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // And an ordinary share still loads, both ways of writing one.
    for written in ["85%", "0.8"] {
        let root = workspace("pctok", "context-policy: long-threads\n");
        std::fs::create_dir_all(root.join("context-policies")).expect("makes the folder");
        std::fs::write(
            root.join("context-policies/long-threads.yaml"),
            policy(written),
        )
        .expect("writes the policy");
        let (ok, text) = checked(&root);
        assert!(ok, "`{written}` is a share and must load:\n{text}");
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_number_field_given_the_far_bottom_end_says_so() {
    // The mirror sentence. Told that `-1e999` is "more than" something, an
    // author would go looking for a smaller number and find the one they had
    // already written.
    let root = workspace("typedneg", "settings:\n  temperature: -1e999\n");
    let (ok, text) = checked(&root);

    assert!(!ok, "the bottom end must be refused too:\n{text}");
    assert!(
        text.contains("schema/too-big-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        text.contains(
            "'temperature' is -1e999, which is further below zero than this can keep track of."
        ),
        "the sentence must say WHICH end:\n{text}"
    );
    assert!(
        text.contains(
            "fix: Write `temperature: 10`, or any figure of fifteen digits or fewer, or remove \
             the line."
        ),
        "and the fix must point the same way:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_number_field_given_a_whole_number_past_holding_is_refused_by_name() {
    // Keeping the digits as text is only half the answer, and for the integer
    // spelling the other half needed its own door: `99999999999999999999` reads
    // back out of that text as `1e20`, which is FINITE, so the `!n.is_finite()`
    // arm of `check_ceiling` passed straight over it. Measured before this:
    // `OK — loaded cleanly (10 settings)`, exit 0, and `pact show` handing the
    // runtime `1e+20` — a figure nobody wrote, with no report. That is the
    // silent degradation T7 and FR-8.1.1 forbid.
    let root = workspace(
        "typedint",
        "settings:\n  temperature: 99999999999999999999\n",
    );
    let (ok, text) = checked(&root);

    assert!(
        !ok,
        "a number field must not quietly hold a figure nobody wrote:\n{text}"
    );
    assert!(
        text.contains("schema/too-big-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        !text.contains("schema/wrong-type"),
        "twenty nines are spelled exactly the way a number is spelled:\n{text}"
    );
    assert!(
        text.contains(
            "'temperature' is 99999999999999999999, which is more than this can keep track of."
        ),
        "the sentence must quote what was written:\n{text}"
    );
    assert!(
        text.contains(
            "fix: Write `temperature: 10`, or any figure of fifteen digits or fewer, or remove \
             the line."
        ),
        "the fix must be typeable:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // The other end of the same spelling gets the other end's words.
    let root = workspace(
        "typedintneg",
        "settings:\n  temperature: -99999999999999999999\n",
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "the bottom end must be refused too:\n{text}");
    assert!(
        text.contains(
            "'temperature' is -99999999999999999999, which is further below zero than this can \
             keep track of."
        ),
        "the sentence must say WHICH end:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // AND THE SAME FIGURE WITH A POINT ON THE END, which the digits-only rule
    // could not see: measured with that rule in place, `temperature:
    // 99999999999999999999.0` was `OK — loaded cleanly (10 settings)`, exit 0,
    // and `pact show` printed `"temperature": 1e+20` — a figure nobody wrote,
    // handed to the runtime with no report, which is verbatim the harm the
    // paragraph above records. The markdown door did the same.
    for written in [
        "99999999999999999999.0",
        "99999999999999999999.00",
        "999999999999999999990e-1",
    ] {
        let root = workspace(
            "typedintpt",
            &format!("settings:\n  temperature: {written}\n"),
        );
        let (ok, text) = checked(&root);
        assert!(
            !ok,
            "`{written}` is the same figure and must be refused:\n{text}"
        );
        assert!(
            text.contains("schema/too-big-to-count"),
            "wrong rule for `{written}`:\n{text}"
        );
        assert!(
            !text.contains("schema/wrong-type"),
            "`{written}` is spelled exactly the way a number is spelled:\n{text}"
        );
        assert!(
            text.contains(&format!(
                "'temperature' is {written}, which is more than this can keep track of."
            )),
            "the sentence must quote what was written:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo() {
    // `Ty::Integer` was the last type still giving the false sentence. A bare
    // digit run past `i64` used to arrive as a `Value::Float` and be refused as
    // *"should be a whole number, but it is a number"* — false about the line,
    // and contradicted by its own `fix:`, which offers `10`. Keeping the digits
    // as text alone would have made it *"but it is some text"*, which is the
    // same false sentence one register over, so the coercer answers
    // `Coerced::IntegerTooBig` and the ceiling names the field.
    for written in ["9223372036854775808", "1e999"] {
        let root = workspace(
            "wholebig",
            &format!(
                "limits:\n  tool-calls-at-most: {written}\n  when-it-runs-out: stop-and-say-so\n"
            ),
        );
        let (ok, text) = checked(&root);
        assert!(
            !ok,
            "`{written}` is not a whole number this can hold:\n{text}"
        );
        assert!(
            text.contains("schema/too-big-to-count"),
            "wrong rule for `{written}`:\n{text}"
        );
        assert!(
            !text.contains("schema/wrong-type"),
            "`{written}` is spelled the way a whole number is spelled:\n{text}"
        );
        assert!(
            text.contains(&format!(
                "'tool-calls-at-most' is {written}, which is more than this can keep track of."
            )),
            "the sentence must quote what was written:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // `i64::MAX` itself is held, so it loads. The refusal must stop exactly at
    // the edge of what can be held and not one figure before it.
    let root = workspace(
        "wholeedge",
        "limits:\n  tool-calls-at-most: 9223372036854775807\n  \
         when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, text) = checked(&root);
    assert!(
        ok,
        "the largest whole number this CAN hold must load:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // And a word where a whole number goes is still a word.
    let root = workspace(
        "wholeword",
        "limits:\n  tool-calls-at-most: inf\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "`inf` is not a whole number:\n{text}");
    assert!(
        text.contains("schema/wrong-type"),
        "`inf` never overflowed anything; it is a typo:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo() {
    // A bare figure is a number of seconds by `coerce::duration`'s own rule,
    // and `1e999` is a bare figure — but the parse loop read the `e` as a unit,
    // found no such unit and answered `None`, so the author of a line that is a
    // figure was told it *"should be a length of time … but it is some text"*.
    // `99999999999999999999h` already left by the right door; this is the same
    // mistake and now leaves by the same one.
    let root = workspace(
        "durbig",
        "limits:\n  finishes-within: 1e999\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "a wait nothing can count must be refused:\n{text}");
    assert!(
        text.contains("schema/too-long-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        !text.contains("schema/wrong-type"),
        "`1e999` is a figure, not a typo:\n{text}"
    );
    assert!(
        text.contains(
            "'finishes-within' is 1e999, which is a longer time than this can keep \
                       track of."
        ),
        "the sentence must quote what was written:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // THE SPELLING THE HELP PRESCRIBES, which the bare-figure special case
    // could not reach and which was still getting the condemned sentence with
    // the fix fully in place. Measured through the shipped binary:
    // `finishes-within: 1e999s`, `1e300h`, `1e999 seconds` and `1e400 ms` were
    // every one of them *"should be a length of time, like `2s`, `500ms` or `5
    // minutes`, but it is some text"* — about a line carrying exactly the unit
    // that sentence asks for — while `99999999999999999999h`, the same figure
    // spelled without an exponent, was `schema/too-long-to-count`. The special
    // case fired on a whole string that parsed as `+inf`, so anything with a
    // unit on it fell into the loop below, which read the `e` as a unit.
    for written in ["1e999s", "1e300h", "1e999 seconds", "1e400 ms", "1e999ms"] {
        let root = workspace(
            "durunit",
            &format!(
                "limits:\n  finishes-within: {written}\n  when-it-runs-out: stop-and-say-so\n"
            ),
        );
        let (ok, text) = checked(&root);
        assert!(
            !ok,
            "`{written}` is longer than anything can count:\n{text}"
        );
        assert!(
            text.contains("schema/too-long-to-count"),
            "wrong rule for `{written}`:\n{text}"
        );
        assert!(
            !text.contains("but it is some text"),
            "`{written}` is a figure and a unit, which is what the help asks for:\n{text}"
        );
        assert!(
            text.contains(&format!(
                "'finishes-within' is {written}, which is a longer time than this can keep track \
                 of."
            )),
            "the sentence must quote what was written:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // A BARE FIGURE PAST HOLDING ANSWERS THE SAME WHETHER OR NOT THE DOCUMENT
    // LAYER COULD HOLD IT. `1e308` is a figure a double keeps, so it arrived as
    // a number rather than as text and was told *"should be a length of time …
    // but it is a number"* — while `1e999`, a LONGER time, was told it was too
    // long. An author following the first message's own fix (*"any shorter
    // length of time"*) could land on the second and be told their line was
    // never a length of time at all. Milliseconds are the smallest unit there
    // is, so a figure past the milliseconds this counts in is past them however
    // it is meant, and the missing unit is not what is wrong with the line.
    let root = workspace(
        "durbare",
        "limits:\n  finishes-within: 1e308\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, text) = checked(&root);
    assert!(
        !ok,
        "`1e308` seconds is longer than anything can count:\n{text}"
    );
    assert!(
        text.contains("schema/too-long-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        text.contains(
            "'finishes-within' is 1e308, which is a longer time than this can keep \
                       track of."
        ),
        "and the sentence names the figure rather than three hundred zeros:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // And the boundary of THAT rule, which is the deliberate one: a bare figure
    // a unit could still have saved is refused for the missing unit, because
    // `90` is as likely to mean ninety minutes as ninety seconds and guessing
    // moves a ceiling by sixty times in silence.
    for written in ["90", "1e15"] {
        let root = workspace(
            "durnounit",
            &format!(
                "limits:\n  finishes-within: {written}\n  when-it-runs-out: stop-and-say-so\n"
            ),
        );
        let (ok, text) = checked(&root);
        assert!(!ok, "`{written}` has no unit and must be refused:\n{text}");
        assert!(
            text.contains("schema/wrong-type"),
            "the unit is what is missing from `{written}`:\n{text}"
        );
        assert!(
            text.contains("`5 minutes`"),
            "and the fix must teach the unit for `{written}`:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // And the ordinary spellings are untouched — including one that carries an
    // exponent and is a perfectly ordinary million seconds, which the loop used
    // to answer *"but it is some text"* about.
    for written in ["30s", "1m30s", "2 minutes", "500ms", "1e6s", "2.5e2 ms"] {
        let root = workspace(
            "durok",
            &format!(
                "limits:\n  finishes-within: {written}\n  when-it-runs-out: stop-and-say-so\n"
            ),
        );
        let (ok, text) = checked(&root);
        assert!(ok, "`{written}` must still load:\n{text}");
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_bottom_end_of_a_length_of_time_and_a_size_is_not_called_text_either() {
    // THE HALF OF THIS FILE'S OWN TITLE THAT ITS OWN TESTS DID NOT HOLD, found
    // by attacking the landed change rather than by reading it.
    //
    // "Both ends of the number line have their own sentence" is true for the
    // three types that reach `Schema::check_ceiling` — a number, a whole number
    // and a comparison — and every one of those ends is pinned above. It is NOT
    // reached that way for the two types whose bottom end is not a size at all:
    // a length of time and a count of tokens have no negative end to run off,
    // so `finishes-within: -1e999` and `context-at-least: -1e999` fall through
    // to `schema/wrong-type`, exactly as `-5s` and `-5` do, and the only thing
    // keeping them from being called *"some text"* there is `kind_as_written`,
    // which reads the noun off the author's text because keeping a figure past
    // holding as text is what put a run of digits in front of `wrong_type` in
    // the first place.
    //
    // That function has ONE door in this repository and it is in the sibling
    // file, on `steps-at-most` — a `type: integer` field, which is the one type
    // whose bottom end goes to the ceiling instead. Measured: replacing
    // `kind_as_written`'s body with `node.value.kind_name()` leaves THIS FILE
    // at `14 passed; 0 failed` while `pact check` says
    //
    //     'finishes-within' should be a length of time, like `2s`, `500ms` or
    //     `5 minutes`, but it is some text.
    //
    // about `-1e999` — verbatim the sentence this file's header condemns four
    // times over, at the end of the number line this file's header claims. A
    // test that is green over its own headline claim is the thing worth finding,
    // so the claim is held here rather than borrowed from a neighbour.
    for (field, block, noun) in [
        (
            "finishes-within",
            "limits:\n  finishes-within: {}\n  when-it-runs-out: stop-and-say-so\n",
            "a length of time",
        ),
        (
            "context-at-least",
            "needs:\n  because: strong.\n  context-at-least: {}\n",
            "a size",
        ),
    ] {
        // `-1e999` is the exponent spelling and `-99999999999999999999` the
        // digit-run spelling; both are kept as the author's text by
        // `resolve_scalar`, and each has its own true noun — the one the value
        // kinds would have given had the tree been able to hold the figure.
        for (written, want) in [
            ("-1e999", "a number"),
            ("-99999999999999999999", "a whole number"),
        ] {
            let root = workspace("bottomtext", &block.replace("{}", written));
            let (ok, text) = checked(&root);
            assert!(!ok, "`{field}: {written}` is not {noun}:\n{text}");
            assert!(
                text.contains("schema/wrong-type"),
                "there is no bottom end to run off for {noun}, so this is the \
                 same refusal `-5` gets, for `{field}: {written}`:\n{text}"
            );
            assert!(
                !text.contains("but it is some text"),
                "`{written}` is spelled exactly the way a figure is spelled; \
                 calling it text is the sentence this file exists to delete, \
                 for `{field}`:\n{text}"
            );
            assert!(
                text.contains(&format!("but it is {want}.")),
                "the noun must be the one the figure earns (`{want}`) for \
                 `{field}: {written}`:\n{text}"
            );
            let _ = std::fs::remove_dir_all(&root);
        }

        // The guard, so the rule above cannot be satisfied by calling
        // everything a figure: a WORD where a figure goes is text and must keep
        // saying so, and this is the same line `the_word_infinity_where_a_
        // number_goes_is_still_a_typo` draws one type over.
        let root = workspace("bottomword", &block.replace("{}", "-inf"));
        let (ok, text) = checked(&root);
        assert!(!ok, "`{field}: -inf` is not {noun}:\n{text}");
        assert!(
            text.contains("but it is some text"),
            "`-inf` carries no digit, so text is the TRUE noun for it on \
             `{field}`:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_word_infinity_where_a_number_goes_is_still_a_typo() {
    // `inf` and `nan` carry no digit, so they are not a figure that overflowed
    // — they are a word spelled where a figure goes, and "should be a number,
    // but it is some text" is the true sentence for them. This is the same line
    // `money_past_counting` draws, and it is what keeps the ceiling's sentence
    // meaning what it says.
    for word in ["inf", "nan", "Infinity"] {
        let root = workspace("word", &format!("settings:\n  temperature: {word}\n"));
        let (ok, text) = checked(&root);
        assert!(!ok, "`{word}` is not a number:\n{text}");
        assert!(
            text.contains("schema/wrong-type"),
            "`{word}` is a typo, not a size:\n{text}"
        );
        assert!(
            !text.contains("too-big-to-count"),
            "`{word}` never overflowed anything, so it is not over any ceiling:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // THE DOOR THAT HAD NO TEST, found by mutating rather than by reading. Four
    // of the five types drew this line and four had it held; a length of time
    // drew it in a special case of its own — `parse::<f64>() == inf && has_a_
    // digit` — and NOTHING in the repository pinned the second half. Deleting
    // it left this file green, the whole `pact-cli` suite green under
    // `--no-fail-fast` and the whole of `pact-schema` green, while the shipped
    // binary told the author of `finishes-within: inf` that their line was
    // *"a longer time than this can keep track of"* — a figure's sentence about
    // a word, which is the mirror of the mistake this whole file exists to
    // delete. The special case is gone now (the parse loop reads an exponent as
    // part of the figure, so `1e999` needs no help), but the line it drew is a
    // claim this file makes and it is held here.
    for word in ["inf", "nan", "Infinity", "-inf"] {
        let root = workspace(
            "durword",
            &format!("limits:\n  finishes-within: {word}\n  when-it-runs-out: stop-and-say-so\n"),
        );
        let (ok, text) = checked(&root);
        assert!(!ok, "`{word}` is not a length of time:\n{text}");
        assert!(
            text.contains("schema/wrong-type"),
            "`{word}` is a typo, not a length of time:\n{text}"
        );
        assert!(
            text.contains("but it is some text."),
            "`{word}` carries no digit, so text is the TRUE noun for it:\n{text}"
        );
        assert!(
            !text.contains("too-long-to-count"),
            "`{word}` never overflowed anything, so it is over no ceiling:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_bar_no_score_could_ever_clear_is_refused_too() {
    // The same unguarded parse, one type over: a comparison's figure. `> 1e999`
    // read back as `> inf` is a bar no published benchmark score can ever clear,
    // and it used to load clean — the whole `needs:` block became unmeetable
    // with nothing said.
    let root = workspace(
        "bar",
        "needs:\n  because: we need a strong model.\n  scores:\n    MMLU: \"> 1e999\"\n",
    );
    let (ok, text) = checked(&root);

    assert!(!ok, "a bar nothing can clear must not load clean:\n{text}");
    assert!(
        text.contains("schema/too-big-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        text.contains("which is more than this can keep track of."),
        "the same sentence as the number it is a comparison against:\n{text}"
    );
    // Every entry of a map is checked against the MAP's field, so the name in
    // the sentence is `scores` and not `MMLU` — which is how every other rule
    // reports a map entry here, and is why the fix must not try to build a line
    // out of that name. `Write `scores: > 80`` is a fix that fails if it is
    // typed.
    assert!(
        text.contains(
            "fix: Write `> 80`, or any figure of fifteen digits or fewer, or remove the line."
        ),
        "the fix must be typeable where it is reported:\n{text}"
    );
    assert!(
        !text.contains("`scores: > 80`"),
        "that is not a line anyone can write:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // And the integer spelling, one type over. `past_counting`'s own note says
    // a number and a comparison against one are the same figure and must not
    // drift into two different sentences for it, so the operator is stripped and
    // the digits are asked the same question `temperature:` asks them.
    let root = workspace(
        "barint",
        "needs:\n  because: we need a strong model.\n  scores:\n    \
         MMLU: \"> 99999999999999999999\"\n",
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "a bar of `> 1e20` is not the bar written:\n{text}");
    assert!(
        text.contains("schema/too-big-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        text.contains(
            "'scores' is > 99999999999999999999, which is more than this can keep track of."
        ),
        "the sentence must quote what was written:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // And the word, one type over, keeps the word's answer.
    let root = workspace(
        "barword",
        "needs:\n  because: we need a strong model.\n  scores:\n    MMLU: \"> inf\"\n",
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "`> inf` is not a comparison:\n{text}");
    assert!(
        text.contains("schema/wrong-type"),
        "`> inf` is a typo, not a size:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_words_for_infinity_are_still_plain_text() {
    // `.inf` and `.nan` are YAML's own spellings and were never numbers here —
    // `resolve_scalar` wants a digit before it will read a scalar as a number,
    // so they have always come out as the text they were. Refusing overflow
    // must not have changed that in either direction.
    let root = workspace("words", "x-a: .inf\nx-b: -.inf\nx-c: .nan\n");
    let text = shown(&root);
    assert!(
        text.contains(r#""x-a": ".inf""#),
        "`.inf` is the text `.inf`:\n{text}"
    );
    assert!(
        text.contains(r#""x-b": "-.inf""#),
        "and so is `-.inf`:\n{text}"
    );
    assert!(
        text.contains(r#""x-c": ".nan""#),
        "and so is `.nan`:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn ordinary_numbers_are_untouched() {
    // The refusal must reach nothing but the far end. These are numbers, they
    // stay numbers, and they print as numbers rather than as quoted text.
    let root = workspace(
        "ordinary",
        "x-a: 1.5\nx-b: 1e10\nx-c: 0.5\nx-d: 42\nx-e: -3.25\n",
    );
    let text = shown(&root);
    for (field, written) in [
        ("x-a", "1.5"),
        ("x-b", "10000000000.0"),
        ("x-c", "0.5"),
        ("x-d", "42"),
        ("x-e", "-3.25"),
    ] {
        assert!(
            text.contains(&format!(r#""{field}": {written}"#)),
            "`{field}` must still be the number {written}:\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_ordinary_number_field_still_takes_an_ordinary_number() {
    // The ceiling must not have narrowed what a number field accepts. Both the
    // number types are here, from both spellings.
    let root = workspace(
        "fine",
        "settings:\n  temperature: 0.7\n  top-p: 1e-3\n  top-k: 40\n",
    );
    let (ok, text) = checked(&root);
    assert!(ok, "an ordinary settings block must still load:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}
