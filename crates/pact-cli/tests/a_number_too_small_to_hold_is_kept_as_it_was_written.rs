//! The BOTTOM of the number line, which the overflow fix left open on purpose
//! and which is the same harm.
//!
//! `crates/pact-cli/tests/a_number_too_big_to_hold_is_kept_as_it_was_written.rs`
//! closed the top: `x-threshold: 1e999` parses to infinity, could not be written
//! down, and left as `null`. Its own prose recorded what it did not close, and
//! the register kept the row (C10 in `docs/70-PRODUCTION-GAP-REGISTER.md`):
//!
//! ```text
//! $ cat agents/desk/agent.yaml
//! x-tiny: 1e-999
//!
//! $ pact show .
//!       "x-tiny": 0.0,
//!
//! $ pact check .
//! OK — … loaded cleanly (14 settings).
//! $ echo $?
//! 0
//! ```
//!
//! Nothing is null this time, which is exactly why it is worse to read: `0.0` is
//! a perfectly ordinary number sitting where a figure was written, so there is
//! no sign at all that anything was lost. Measured on the build before this
//! change, a workspace saying `x-tiny: 1e-999` and one saying `x-tiny: 0` were
//! given the **identical** digest by `pact discover`, so a lockfile pinned one
//! and could not tell it from the other. That is the same sentence AC-1.3's
//! *"round-trips untouched"* is about, and the same sentence the overflow fix
//! was written to delete.
//!
//! # Why the rule is this narrow, and the two wider ones that do not work
//!
//! Both were measured rather than reasoned about:
//!
//! * *"only accept a float that round-trips its own text"* refuses **`1e10`**,
//!   which comes back as `10000000000.0` — the same number, reformatted. Nobody
//!   would call that corrupted, and a checker that did would be refusing the
//!   ordinary way people write big round numbers.
//! * *"any text that parses to zero is suspect"* refuses `0`, `0.0`, `-0.0` and
//!   `0e10`, which are zeros an author meant and which lose nothing at all by
//!   being read as zero.
//!
//! What is left is the narrow one the register named: **a scalar that comes back
//! as zero while its significand carries a figure other than zero is not zero.**
//! The exponent is deliberately not looked at — the `10` of `0e10` scales a
//! nothing and says nothing about what was meant, while the `1` of `1e-999` is
//! the whole of what the author wrote.
//!
//! # The second half, which the register also named
//!
//! Keeping the text is the whole answer for `x-`, which PACT does not read. For
//! a field where the specification says a figure is wanted it is half an answer:
//! the document layer hands the text on, `coerce::number` parses `0.0` straight
//! back out of it, and `settings: temperature: 1e-999` would still be checked —
//! silently — as a setting the author never wrote. So `Schema::check_ceiling`
//! grew the mirror of its own top-end arm, `schema/too-small-to-count`.
//!
//! It is NOT `schema/wrong-type`, for the reason the top end is not: `1e-999` is
//! spelled exactly the way a number is spelled, and *"should be a number, but it
//! is some text"* sends its author hunting for a typo that is not there.
//!
//! **Which is a claim about five types and not about every type, and the
//! difference is measured rather than assumed.** `number`, `integer`,
//! `threshold`, `percent` and `size` all name the bottom of their own scale
//! (`schema/too-small-to-count`). `duration` and `money` do not, and are right
//! not to: `finishes-within: 1e-999` carries no unit and
//! `cost-per-request-under: "1e-999"` carries no currency, so *"should be a
//! length of time, like `2s`"* and *"should be an amount of money, like `0.05
//! USD`"* are the TRUE sentences about them — the same answer `0.5` gets, which
//! is the same mistake. What was never acceptable is the NOUN, and for one round
//! this fix broke exactly that; see
//! [`a_figure_on_the_page_is_never_called_some_text`] and mutation **H**.
//!
//! One sentence covers both signs, which the top end needed two for. `-1e999` is
//! genuinely at the far end of the scale and had to be told so; `-1e-999` is
//! `-0.0`, and "closer to zero than this can keep track of" is true of it and of
//! `1e-999` alike — the edit both authors need is the same one.
//!
//! # The three zeros, which for one round were one
//!
//! A count of tokens is the one type here where "arrived as zero" is not one
//! question but three, because `coerce::size` multiplies by the `k` or `m` and
//! CASTS, so two different losses meet at the same `Size(0)`:
//!
//! | written | figure | what happened | answer |
//! |---|---|---|---|
//! | `0`, `0k` | 0 | nothing; a zero somebody meant | loads |
//! | `0.0004k`, `"0.5"` | 0.4, 0.5 | held to the last bit, TRUNCATED by `as u64` | `schema/below-the-floor` |
//! | `1e-999`, `1e-999m` | — | never held at all | `schema/too-small-to-count` |
//!
//! For one round the middle row got the bottom row's sentence, because the arm
//! asked `underflowed_to_zero(0.0, node)` — a HARD-CODED zero, which never asks
//! whether anything underflowed and only asks whether the text carries a figure.
//! So `context-at-least: "0.5"` was told it was *"closer to zero than this can
//! keep track of"* and offered *"any number further from zero"* as the fix, both
//! false: an `f64` holds 0.5 exactly, and `0.0004k` already is a number further
//! from zero than zero. The middle row's true sentence was already in the tree
//! one type over — `finishes-within: 0.4ms` is *"which is no time at all"*,
//! `schema/below-the-floor` — so the size floor says *"which is no tokens at
//! all"* and `coerce::size` now separates the two while it still can, at the
//! figure BEFORE the multiplier, which is the last point at which `1e-999m` and
//! `0.0004k` are distinguishable.
//!
//! **The one spelling that still answers differently, recorded rather than
//! hidden.** A bare `context-at-least: 0.5` is a `Value::Float` and leaves
//! `coerce::size` at its `_ => return None`, so it is *"should be a size, like
//! `32k` or `200000`, but it is a number"* where the quoted `"0.5"` is *"is 0.5,
//! which is no tokens at all"*. Both are true and both point at `32k`. Closing
//! the gap means accepting `Value::Float` as a size, which WIDENS what loads
//! (`context-at-least: 32000.0` is refused today and would stop being) — a
//! change to the grammar, not to this fix.
//!
//! # Mutations
//!
//! Each was applied on its own, rebuilt, this file run, and REVERTED before the
//! next, with a full green run in between to prove the revert took. Nothing here
//! is recalled: every figure below is the line `cargo test -p pact-cli --test
//! a_number_too_small_to_hold_is_kept_as_it_was_written` printed. **Every row's
//! passed + failed is 15**, which is the count of tests in this file and the
//! cheapest way for a reader to catch a record that has gone stale — an earlier
//! version of this list reported totals of 10 and 11 for a file that had grown
//! past both, and one row's result was simply wrong.
//!
//! * **A** — drop `&& !underflowed_to_zero(f, text)` from the float arm of
//!   `resolve_scalar` in `crates/pact-doc/src/yaml.rs`. `8 passed; 7 failed`:
//!   `a_number_too_small_to_hold_survives_show` (`"x-tiny": 0.0` again),
//!   `two_documents_that_differ_do_not_digest_the_same` (one digest for two
//!   documents), `a_number_field_given_one_is_refused_by_name`,
//!   `the_same_sentence_covers_the_other_sign`,
//!   `a_whole_number_field_given_one_is_refused_by_name_too`,
//!   `a_count_of_tokens_that_underflowed_is_refused_rather_than_read_as_none`
//!   and `a_share_of_the_whole_that_underflowed_is_refused_too` — the node is a
//!   `Float` again and `as_str` has nothing for any significand test to read.
//!   The share test is in this list for ONE of its three cases, `must-pass:
//!   1e-999` with no `%`, which is the only unquoted spelling it writes and so
//!   the only one that goes through the document layer; that single case is the
//!   whole seam between the two halves of this fix.
//!   `a_bar_no_score_could_ever_miss_is_refused_too` stays GREEN, because a
//!   comparison is written quoted and the document layer never touches it: that
//!   one is the schema arm's alone, which is why both edits are needed and
//!   neither is a second copy of the other.
//! * **B** — drop the `Coerced::Number` and `Coerced::Threshold` underflow arms
//!   from `Schema::check_ceiling`. `12 passed; 3 failed`:
//!   `a_number_field_given_one_is_refused_by_name`,
//!   `the_same_sentence_covers_the_other_sign` and
//!   `a_bar_no_score_could_ever_miss_is_refused_too`, each with `OK — … loaded
//!   cleanly`, exit 0. The `x-` and digest claims stay green — those are the
//!   document layer's alone.
//! * **C** — widen `underflowed_to_zero` in `yaml.rs` to look at the whole text
//!   rather than the significand. `14 passed; 1 failed`:
//!   `a_zero_somebody_meant_is_still_a_zero` gets the text `"0.0e10"` back
//!   instead of the zero it is.
//! * **D** — widen it again to *"the float does not round-trip its text"*
//!   (`f.to_string() != text`). `13 passed; 2 failed`:
//!   `a_number_nobody_would_call_corrupted_is_left_alone` on `1e10`, and the
//!   zeros test on `-0.0` and `0.000`, which do not print back as they were
//!   written either.
//! * **E** — drop the `Coerced::SizeTooSmall` arm from `Schema::check_ceiling`.
//!   `14 passed; 1 failed`:
//!   `a_count_of_tokens_that_underflowed_is_refused_rather_than_read_as_none`,
//!   with `OK — … loaded cleanly` and exit 0 on a context window of nothing.
//! * **F** — drop the `Coerced::Percent` arm from `Schema::check_ceiling`.
//!   `14 passed; 1 failed`:
//!   `a_share_of_the_whole_that_underflowed_is_refused_too` alone, with `OK — …
//!   loaded cleanly` and exit 0 on an eval bar every suite clears.
//! * **G** — drop the `Coerced::IntegerTooSmall` arm from
//!   `Schema::check_ceiling`. `14 passed; 1 failed`:
//!   `a_whole_number_field_given_one_is_refused_by_name_too`, which gets
//!   `schema/wrong-type` and *"but it is some text"* back.
//! * **H** — put `wrong_type` back on `node.value.kind_name()` in place of
//!   `kind_as_written`. `14 passed; 1 failed`:
//!   `a_figure_on_the_page_is_never_called_some_text`. This is the mutation that
//!   reproduces the regression this fix CAUSED and had to undo.
//! * **I** — drop the `Coerced::Size(0)` arm from `Schema::check_floor`.
//!   `14 passed; 1 failed`:
//!   `a_size_that_rounds_to_no_tokens_is_not_told_its_figure_vanished`, with
//!   `OK — … loaded cleanly` on `context-at-least: 0.0004k`.
//! * **J** — drop the `underflowed_to_zero(v, digits)` branch from
//!   `coerce::size`, so an underflowing size falls through to the truncation
//!   zero. `14 passed; 1 failed`:
//!   `a_count_of_tokens_that_underflowed_is_refused_rather_than_read_as_none` —
//!   `1e-999` is told it is *"no tokens at all"*, which is the middle row's
//!   sentence about the bottom row's mistake. E and J are the two halves of the
//!   same claim and neither covers the other.
//! * **K** — drop the `underflowed_to_zero(f, s)` branch from `coerce::integer`.
//!   `14 passed; 1 failed`:
//!   `a_whole_number_field_given_one_is_refused_by_name_too`, the same test G
//!   fails, from the other end of the same route.
//!
//! Which suites are BLIND to each of these was measured too, because it reads
//! like coverage that is not there. **`cargo test -p pact-doc` is blind to A** —
//! 52 passed with the guard gone. **`cargo test -p pact-schema` is blind to B,
//! E, G and I** — every one of its ten binaries green with those arms deleted,
//! because a `Schema::check_*` arm is only reachable through a loaded document.
//! It is NOT blind to J or K: `coerce::tests` asks the coercer directly, and
//! both mutations turn it red. So the schema arms are held by this file alone,
//! through the shipped binary, and the coercion answers underneath them are held
//! in both places.
//!
//! # The consumer this change reached without being checked against
//!
//! Keeping an underflowing scalar as text does not only stop `pact show` losing
//! it — it changes what every TYPED field is handed, and two of them got worse.
//!
//! `needs.context-at-least` is a `size`, and `coerce::size` accepts a
//! `Value::Str` and refuses a `Value::Float` at its `_ => return None`. So
//! before this change `context-at-least: 1e-999` was a `Float(0.0)` and was
//! refused; after it, the text reached `size`, parsed to `0.0`, multiplied,
//! cast, and came out as `Coerced::Size(0)` — and `pact check` said `OK — rd
//! loaded cleanly (498 settings)`, exit 0, on a governance requirement that had
//! become indistinguishable from an authored `context-at-least: 0`. The blast
//! radius said the size consumer had been checked; it had not, and mutations E
//! and J are what now hold it.
//!
//! `Schema::wrong_type` is the second and was missed for longer, because it
//! fails in the SENTENCE rather than in the rule. It builds its noun from
//! `Value::kind_name`, so the moment a figure started being carried as text
//! every typed field that falls through to `wrong-type` began calling a run of
//! digits *"some text"*: `finishes-within: 1e-999` and `finishes-within: abc`
//! produced byte-identical reports, and `steps-at-most: 1e-999` was given the
//! sentence `steps-at-most: abc` gets while `steps-at-most: 1e999`, one order up
//! the same scale, was named. `kind_as_written` reads the noun off the text
//! instead — the same argument `underflowed_to_zero` and
//! `whole_number_past_holding` already make — and mutation H holds it.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A one-agent workspace whose `agent.yaml` holds `extra`, returned as a path.
fn workspace(name: &str, extra: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-toosmall-{name}-{}", std::process::id()));
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

/// The same workspace with an `evals/suite.yaml` whose bar is `bar`.
///
/// A share of the whole is the one type in this file that cannot be written in
/// `agent.yaml` at all: every `type: percent` field in `spec/schema.yaml` lives
/// in an eval suite, a context policy, a metric or a drift limit. Measured with
/// the block below and `must-pass: 1e-999%`: `error: 'must-pass' is 1e-999%,
/// which is closer to zero than this can keep track of.` — and, before the arm
/// that says it, `OK — … loaded cleanly`, exit 0.
fn suite(name: &str, bar: &str) -> std::path::PathBuf {
    let dst = workspace(name, "");
    std::fs::create_dir_all(dst.join("evals")).expect("makes the suite folder");
    std::fs::write(
        dst.join("evals/suite.yaml"),
        format!(
            "description: Checks the desk.\npopulation: authored-enumeration\nmust-pass: {bar}\n"
        ),
    )
    .expect("writes the suite");
    dst
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

/// The digest `pact discover` publishes for the one workspace in `root`.
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

#[test]
fn a_number_too_small_to_hold_survives_show() {
    let root = workspace("show", "x-tiny: 1e-999\nx-below: -1e-999\nx-also: 1e-400\n");
    let text = shown(&root);

    assert!(
        text.contains(r#""x-tiny": "1e-999""#),
        "what the author wrote must come back out:\n{text}"
    );
    assert!(
        text.contains(r#""x-below": "-1e-999""#),
        "and at the other sign, which arrives as `-0.0`:\n{text}"
    );
    assert!(
        text.contains(r#""x-also": "1e-400""#),
        "the same one order up:\n{text}"
    );
    assert!(
        !text.contains(": 0.0"),
        "no figure the author wrote may come back as a zero they did not:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn two_documents_that_differ_do_not_digest_the_same() {
    // The harm, stated as the thing a lockfile does. Before this change these
    // two workspaces were given the same `sha256:` and nothing could tell the
    // pinned one from the other.
    let tiny = workspace("digest-tiny", "x-tiny: 1e-999\n");
    let zero = workspace("digest-zero", "x-tiny: 0\n");
    assert_ne!(
        digest(&tiny),
        digest(&zero),
        "`x-tiny: 1e-999` and `x-tiny: 0` are different documents and a lockfile \
         has to be able to say so"
    );
    let _ = std::fs::remove_dir_all(&tiny);
    let _ = std::fs::remove_dir_all(&zero);
}

#[test]
fn a_number_too_small_to_hold_is_not_a_problem_of_its_own() {
    // `x-` is the author's own space and PACT does not read it, so keeping the
    // text is the whole answer here — there is nothing to complain about.
    let root = workspace("check", "x-tiny: 1e-999\n");
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
fn a_zero_somebody_meant_is_still_a_zero() {
    // The guard on the rule. Every one of these parses to zero and every one of
    // them is a zero the author wrote, so nothing may be said about any of them
    // and none may be turned into text.
    //
    // `0.0e10` and not `0e10`, which reads like the better example and is not:
    // the leading-zero rule a few lines above this one in `resolve_scalar` — the
    // one that keeps `01234` and `007` as the codes they are — already owns
    // every plain scalar starting `0` that is not `0.`, so `0e10` comes back as
    // the text `"0e10"` and has done since before any of this. Asserting the
    // significand rule against a value a different rule decides would be a test
    // that passes for the wrong reason.
    let root = workspace(
        "zeros",
        "x-a: 0\nx-b: 0.0\nx-c: -0.0\nx-d: 0.0e10\nx-e: 0.000\n",
    );
    let (ok, said) = checked(&root);
    assert!(ok, "a zero somebody meant is not a problem:\n{said}");

    let text = shown(&root);
    for (name, shown_as) in [
        ("x-a", "0"),
        ("x-b", "0.0"),
        ("x-c", "-0.0"),
        ("x-d", "0.0"),
        ("x-e", "0.0"),
    ] {
        assert!(
            text.contains(&format!(r#""{name}": {shown_as}"#)),
            "`{name}` is a number and must stay one:\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_number_nobody_would_call_corrupted_is_left_alone() {
    // The other guard, and the one that killed the obvious general rule. `1e10`
    // does not round-trip its own text — it comes back as `10000000000.0` — and
    // it is the same number. `1e-300` is small enough to look like the case
    // above and is held exactly, so it is a number too.
    let root = workspace(
        "ordinary",
        "x-big: 1e10\nx-small: 1e-300\nx-tenth: 0.1\nx-one: 1.50\n",
    );
    let text = shown(&root);
    assert!(
        text.contains(r#""x-big": 10000000000.0"#),
        "`1e10` is a number:\n{text}"
    );
    assert!(
        text.contains(r#""x-small": 1e-300"#),
        "`1e-300` is held exactly:\n{text}"
    );
    assert!(
        text.contains(r#""x-tenth": 0.1"#),
        "and the ordinary ones are untouched:\n{text}"
    );
    assert!(
        text.contains(r#""x-one": 1.5"#),
        "`1.50` is the number 1.5:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_number_field_given_one_is_refused_by_name() {
    // The other side of keeping it as text: where the specification says a
    // number is wanted, `1e-999` is refused at the author's own line instead of
    // being read as a zero they never wrote.
    let root = workspace("typed", "settings:\n  temperature: 1e-999\n");
    let (ok, text) = checked(&root);

    assert!(!ok, "a number field must not quietly hold a zero:\n{text}");
    assert!(
        text.contains("schema/too-small-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        !text.contains("schema/wrong-type"),
        "`1e-999` is spelled the way a number is spelled; sending its author \
         hunting for a typo is the thing this rule exists to stop:\n{text}"
    );
    assert!(
        text.contains(
            "'temperature' is 1e-999, which is closer to zero than this can keep track of."
        ),
        "the sentence must name the value and say what is wrong with it:\n{text}"
    );
    assert!(
        text.contains("agent.yaml:5"),
        "must name the file and the line:\n{text}"
    );
    assert!(
        text.contains(
            "fix: Write `temperature: 10`, or any number further from zero, or remove the line."
        ),
        "the fix must be typeable:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_count_of_tokens_that_underflowed_is_refused_rather_than_read_as_none() {
    // THE CONSUMER THE OVERFLOW FIX REACHED WITHOUT BEING CHECKED AGAINST.
    // Before a scalar that underflows was kept as text, `context-at-least:
    // 1e-999` was a `Value::Float(0.0)` and `coerce::size` refused it outright
    // at its `_ => return None`. Keeping the text handed `size` a `Value::Str`
    // instead — a spelling it accepts — so the line started loading CLEANLY as
    // a context window of zero, indistinguishable from an authored
    // `context-at-least: 0`: a governance requirement no model has to meet, out
    // of a line that was asking for one, silently. Measured with the ceiling
    // arm removed: `OK — rd loaded cleanly (498 settings)`, exit 0.
    for written in ["1e-999", "1e-999m"] {
        let root = workspace(
            "size-underflow",
            &format!("needs:\n  because: it has to read a long thread.\n  context-at-least: {written}\n"),
        );
        let (ok, text) = checked(&root);
        assert!(
            !ok,
            "`{written}` must not load as a context window of nothing:\n{text}"
        );
        assert!(
            text.contains("schema/too-small-to-count"),
            "wrong rule for `{written}`:\n{text}"
        );
        assert!(
            !text.contains("schema/wrong-type"),
            "`{written}` is spelled the way a size is spelled:\n{text}"
        );
        assert!(
            text.contains(&format!(
                "'context-at-least' is {written}, which is closer to zero than this can keep \
                 track of."
            )),
            "the sentence must quote what was written:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // A zero somebody MEANT is not this, and neither is an ordinary size. The
    // refusal reads the significand, so `0` and `0k` carry no figure that was
    // lost and are none of its business.
    for written in ["0", "0k", "32k", "200000"] {
        let root = workspace(
            "size-honest",
            &format!("needs:\n  because: it has to read a long thread.\n  context-at-least: {written}\n"),
        );
        let (ok, text) = checked(&root);
        assert!(ok, "`{written}` must still load:\n{text}");
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_size_that_rounds_to_no_tokens_is_not_told_its_figure_vanished() {
    // THE OTHER ZERO, AND FOR ONE ROUND THIS FILE ASSERTED THE FALSE SENTENCE
    // ABOUT IT. `coerce::size` multiplies by the `k` and casts to a whole
    // number, so `0.0004k` (0.4 tokens), `0.0000001k` and a quoted `"0.5"`
    // all arrive as `Size(0)` — and the ceiling arm asked
    // `underflowed_to_zero(0.0, node)`, a HARD-CODED zero, which never asked
    // whether anything had underflowed and only asked whether the text carried
    // a figure. So every one of them was told it was "closer to zero than this
    // can keep track of" and offered *"any number further from zero"* as the
    // fix. Both halves are false: an `f64` holds 0.4 and 0.5 to the last bit,
    // and `0.0004k` already IS a number further from zero than zero.
    //
    // The project already owns this shape one type over — `finishes-within:
    // 0.4ms` is `schema/below-the-floor`, "which is no time at all" — so this
    // gets the same door and the matching sentence. `coerce::size` now decides
    // it where the two are still distinguishable, before the multiplier.
    for written in ["0.0000001k", "0.0004k", "0.0009k", "\"0.5\"", "\"0.9\""] {
        let root = workspace(
            "size-floor",
            &format!("needs:\n  because: it has to read a long thread.\n  context-at-least: {written}\n"),
        );
        let (ok, text) = checked(&root);
        assert!(!ok, "`{written}` is a context window of nothing:\n{text}");
        assert!(
            text.contains("schema/below-the-floor"),
            "a figure held exactly that rounds to nothing is the floor's, not the \
             ceiling's, for `{written}`:\n{text}"
        );
        assert!(
            !text.contains("closer to zero than this can keep track of"),
            "`{written}` was held exactly; nothing about it ran off the bottom of \
             anything, and saying so sends its author looking for a bigger number \
             when they need a bigger UNIT:\n{text}"
        );
        assert!(
            text.contains(&format!(
                "'context-at-least' is {}, which is no tokens at all.",
                written.trim_matches('"')
            )),
            "the sentence must quote what was written and say what is wrong:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_whole_number_field_given_one_is_refused_by_name_too() {
    // THE LAST TYPE THIS PASS REACHED AND MADE WORSE. `steps-at-most` is
    // `type: integer`; its TOP end is refused by name
    // (`schema/too-big-to-count`, measured below in the same run), and its
    // bottom end was not refused at all until C12 — after which it was refused
    // as `schema/wrong-type` saying *"should be a whole number, but it is some
    // text"*, which is the sentence `steps-at-most: abc` gets, byte for byte.
    // That is the one outcome the header of this file names as the thing the
    // rule exists to prevent, produced by the fix, one type over from where it
    // enforces it.
    for written in ["1e-999", "-1e-999", "1e-400"] {
        let root = workspace(
            "int-underflow",
            &format!("limits:\n  steps-at-most: {written}\n  when-it-runs-out: stop-and-say-so\n"),
        );
        let (ok, text) = checked(&root);
        assert!(!ok, "`steps-at-most: {written}` is not a count:\n{text}");
        assert!(
            text.contains("schema/too-small-to-count"),
            "the bottom of a whole-number field is named, as its top is, for \
             `{written}`:\n{text}"
        );
        assert!(
            !text.contains("but it is some text"),
            "`{written}` is spelled exactly the way a number is spelled; calling it \
             text is what sends its author hunting for a typo that is not there:\n{text}"
        );
        assert!(
            text.contains(&format!(
                "'steps-at-most' is {written}, which is closer to zero than this can keep \
                 track of."
            )),
            "the sentence must name the value:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // The guards. A WORD is text and must keep saying so, and a fraction this
    // holds exactly is the wrong KIND of figure, not one that ran off an end.
    for (written, wanted) in [
        ("abc", "but it is some text"),
        ("0.5", "but it is a number"),
        ("1.5", "but it is a number"),
    ] {
        let root = workspace(
            "int-guard",
            &format!("limits:\n  steps-at-most: {written}\n  when-it-runs-out: stop-and-say-so\n"),
        );
        let (_, text) = checked(&root);
        assert!(
            text.contains(wanted),
            "`steps-at-most: {written}` must say `{wanted}`:\n{text}"
        );
        assert!(
            !text.contains("too-small-to-count"),
            "`{written}` did not run off the bottom of anything:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_figure_on_the_page_is_never_called_some_text() {
    // THE REGRESSION THIS CHANGE CAUSED AND THEN HAD TO UNDO, held here because
    // it is invisible from either mechanism on its own.
    //
    // Keeping an underflowing scalar as the author's text is what stops `pact
    // show` and the digest losing it — and `Schema::wrong_type` read its noun
    // off `Value::kind_name`, so the moment `1e-999` became a `Value::Str`
    // every typed field that falls through to `wrong-type` began calling a run
    // of digits *"some text"*. Measured on the build before `kind_as_written`:
    // `finishes-within: 1e-999` and `finishes-within: abc` produced
    // byte-identical reports, while `finishes-within: 0.5` — one order up the
    // same scale, held exactly, still a `Value::Float` — said *"a number"*.
    // That is D13 (`crates/pact-doc/src/value.rs:261`) and the sentence
    // `coerce::size` names in capitals as the thing it exists to prevent, both
    // broken by the fix that cites them.
    //
    // The noun now answers what the author WROTE — which is the same argument
    // `underflowed_to_zero` and `whole_number_past_holding` already make — and
    // it answers exactly what the value kinds would have said had the tree been
    // able to hold the figure.
    // C10 MOVED THIS ONE ON, AND THE CLAIM IT IS HERE FOR IS UNCHANGED. When
    // `coerce::duration` learned that the `e` of `1e999s` is part of the figure
    // and not the start of a unit, `1e-999` stopped falling out of that function
    // as "not a length of time" and started being read the way a bare figure in
    // text has always been read there — as seconds, of which `1e-999` is none —
    // so the answer is now the one `0.4ms` gets, by name and at the floor. What
    // this test exists to hold is that a run of digits is never called text, and
    // that is asserted directly below rather than through whichever rule owns
    // the line this week.
    let root = workspace(
        "noun",
        "limits:\n  finishes-within: 1e-999\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (_, text) = checked(&root);
    assert!(
        !text.contains("some text"),
        "a figure is a figure however it had to be carried:\n{text}"
    );
    assert!(
        text.contains("'finishes-within' is 1e-999, which is no time at all."),
        "and it is named as the figure it is:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // Money, one type over, where `wrong-type` IS the right rule — `1e-999`
    // carries no currency — and only the noun was ever wrong.
    let root = workspace(
        "noun-money",
        "limits:\n  cost-per-request-under: \"1e-999\"\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (_, text) = checked(&root);
    assert!(
        text.contains("but it is a number."),
        "an amount with no currency is still a figure:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // A digit run past `i64` is the same claim at the TOP of the scale, kept as
    // text for the sibling fix's reason and just as much a figure.
    let root = workspace(
        "noun-big",
        "limits:\n  cost-per-request-under: \"99999999999999999999\"\n  \
         when-it-runs-out: stop-and-say-so\n",
    );
    let (_, text) = checked(&root);
    assert!(
        text.contains("but it is a whole number."),
        "a run of digits is a whole number, which is what `Value::Int` would have \
         said had one been able to hold it:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);

    // AND THE GUARD, which is the line the sibling file draws at the top end:
    // a WORD spelled where a figure goes is text and must keep being told so.
    // `.inf` and `.nan` carry no digit, and `"inf"` parses as a float but
    // carries no digit either.
    for written in ["abc", ".inf", ".nan", "quite a while"] {
        let root = workspace(
            "noun-word",
            &format!(
                "limits:\n  finishes-within: {written}\n  when-it-runs-out: stop-and-say-so\n"
            ),
        );
        let (_, text) = checked(&root);
        assert!(
            text.contains("but it is some text."),
            "`{written}` is a word and the true sentence says so:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_same_sentence_covers_the_other_sign() {
    // `-1e-999` arrives as `-0.0`, and the edit its author needs is the one
    // `1e-999`'s author needs, so it gets the same words rather than a mirrored
    // pair that would only ever confuse.
    let root = workspace("typedneg", "settings:\n  temperature: -1e-999\n");
    let (ok, text) = checked(&root);
    assert!(!ok, "the other sign must be refused too:\n{text}");
    assert!(
        text.contains(
            "'temperature' is -1e-999, which is closer to zero than this can keep track of."
        ),
        "the sentence must quote what was written:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_number_field_given_a_zero_is_not_told_it_is_too_small() {
    // The floor and this are different questions. A `0` an author meant is
    // either fine or is the floor's business, and it must never be told it is
    // a figure that could not be held.
    for written in ["0", "0.0"] {
        let root = workspace(
            "typedzero",
            &format!("settings:\n  temperature: {written}\n"),
        );
        let (ok, text) = checked(&root);
        assert!(
            ok,
            "`temperature: {written}` is a number somebody meant:\n{text}"
        );
        assert!(
            !text.contains("too-small-to-count"),
            "`{written}` was held exactly:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_bar_no_score_could_ever_miss_is_refused_too() {
    // The comparison type, one type over, and the mirror of the `> 1e999` case
    // its sibling file holds: `> 1e-999` read back as `> 0` is a bar every
    // published score clears, so the `needs:` block it belongs to constrains
    // nothing at all — and it used to load clean.
    let root = workspace(
        "bar",
        "needs:\n  because: we need a strong model.\n  scores:\n    MMLU: \"> 1e-999\"\n",
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "a bar nothing can miss must not load clean:\n{text}");
    assert!(
        text.contains("schema/too-small-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        text.contains("which is closer to zero than this can keep track of."),
        "the same sentence as the number it is a comparison against:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_share_of_the_whole_that_underflowed_is_refused_too() {
    // THE TYPE THIS PASS REACHED AND DID NOT CLOSE FOR A ROUND, found by asking
    // every `type: percent` field in `spec/schema.yaml` the question the
    // comparison above was asked. `must-pass: 1e-999%` is `> 1e-999` written the
    // way an eval suite writes a bar: `coerce::percent` divides by a hundred,
    // finds `0.0` inside `0.0..=1.0`, and hands up `Percent(0.0)` — a bar every
    // suite on earth clears, out of a line that was setting one. Measured on
    // `examples/refund-desk` with its `must-pass: 70%` replaced by `1e-999%`:
    // `OK — rd loaded cleanly (498 settings)`, exit 0, both before this whole
    // change and after it. `Number`, `Threshold` and `Size` got the arm and
    // `Percent` did not.
    for written in ["1e-999%", "-1e-999%", "1e-999"] {
        let root = suite("pct", written);
        let (ok, text) = checked(&root);
        assert!(!ok, "`must-pass: {written}` is a bar of nothing:\n{text}");
        assert!(
            text.contains("schema/too-small-to-count"),
            "wrong rule for `{written}`:\n{text}"
        );
        assert!(
            !text.contains("schema/wrong-type"),
            "`{written}` is spelled the way a share is spelled:\n{text}"
        );
        assert!(
            text.contains(&format!(
                "'must-pass' is {written}, which is closer to zero than this can keep track of."
            )),
            "the sentence must quote what was written:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // The guards, which are the same two the plain number has. A share somebody
    // MEANT is zero with nothing lost — `0%`, `0.0`, `0.00%` and `0.0e10%` carry
    // no non-zero figure — and `0.0000001%` is `1e-9`, held exactly, so it never
    // underflowed anything and is not this.
    for written in ["0%", "0.0", "0", "0.00%", "0.0e10%", "0.0000001%", "70%", "0.7"] {
        let root = suite("pct-honest", written);
        let (ok, text) = checked(&root);
        assert!(ok, "`must-pass: {written}` is a share somebody meant:\n{text}");
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_words_for_nothing_are_still_plain_text() {
    // The line the sibling file draws at the top end, drawn again here: a WORD
    // spelled where a figure goes never underflowed anything. `.nan` and `.inf`
    // carry no digit and stay the text they were written as.
    let root = workspace("words", "x-a: .nan\nx-b: .inf\nx-c: -.inf\n");
    let text = shown(&root);
    assert!(
        text.contains(r#""x-a": ".nan""#),
        "`.nan` is a word:\n{text}"
    );
    assert!(
        text.contains(r#""x-b": ".inf""#),
        "`.inf` is a word:\n{text}"
    );
    assert!(
        text.contains(r#""x-c": "-.inf""#),
        "and so is `-.inf`:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}
