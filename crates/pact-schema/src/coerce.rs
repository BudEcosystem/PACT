//! Type-directed coercion.
//!
//! The YAML layer deliberately leaves plain scalars as text so that `NO` stays
//! Norway (see `pact_doc::yaml`). This module is the other half of that
//! bargain: once the schema says a field *is* a yes/no, `"yes"` becomes `true`
//! — but only there, and never by guessing.
//!
//! Coercion is also where an author's natural spellings are accepted. Someone
//! writing `finishes-within: 30s` should not have to learn that the canonical
//! form is a number of milliseconds.

use pact_doc::{Node, Value};

/// A coerced value. Durations are milliseconds; money keeps its currency
/// because silently normalising currencies would be a correctness bug.
#[derive(Debug, Clone, PartialEq)]
pub enum Coerced {
    Text(String),
    YesNo(bool),
    Number(f64),
    Integer(i64),
    /// Milliseconds.
    Duration(u64),
    /// A length of time spelled correctly and longer than the milliseconds
    /// above can count — `99999999999999999999h`. It carries no number,
    /// because there is no number to carry: the point is that the one the
    /// author wrote does not fit. Refused by name one layer up, in
    /// `Schema::check_ceiling`, for the same reason `Duration(0)` is.
    DurationTooLong,
    Money {
        amount: f64,
        currency: String,
    },
    /// A fraction in `0.0..=1.0`. `90%` becomes `0.9`.
    Percent(f64),
    /// A share whose FIGURE ran off the end of the `f64` it is read in —
    /// `when-full: 1e999%`, `must-pass: -1e999%`.
    ///
    /// The top of the scale [`Coerced::Percent`] got the bottom of in the round
    /// before this one, and it was left open: `1e-999%` was refused by name as
    /// `schema/too-small-to-count` while `1e999%` — the same mistake, the same
    /// spelling, the other end — was *"should be a percentage, like `90%`, but
    /// it is some text"*. It carries the figure only so the sentence can name
    /// which end it ran off.
    PercentPastHolding(f64),
    Threshold {
        op: Op,
        value: f64,
    },
    /// A count of tokens: `32k` becomes 32000.
    Size(u64),
    /// A count of tokens spelled correctly and bigger than the whole number
    /// above can hold — `99999999999999999999m`. Same argument as
    /// [`Coerced::DurationTooLong`], and the same one-layer-up refusal, because
    /// it is the same cast: `k` and `m` multiply in floating point and the
    /// product is cast, and the cast saturates.
    SizeTooBig,
    /// A count of tokens spelled correctly whose FIGURE ran off the bottom of
    /// the `f64` it is read in — `context-at-least: 1e-999`, `1e-999m`.
    ///
    /// The exact mirror of [`Coerced::SizeTooBig`], and it exists because
    /// `Size(0)` could not tell three different things apart. `0` and `0k` are
    /// zeros an author meant; `0.0004k` is 0.4 tokens, a figure this holds
    /// exactly that TRUNCATES to no tokens at the cast below; and `1e-999` is a
    /// figure that was never held at all. Only the last is "closer to zero than
    /// this can keep track of", and for one round all three said so — `0.5`
    /// and `0.9`, which an `f64` holds to the last bit, were told they were
    /// past counting. The first stays silent, the second is
    /// `schema/below-the-floor` ("no tokens at all", the sentence
    /// [`Coerced::Duration`]`(0)` already uses for `0.4ms`), and this is the
    /// third.
    SizeTooSmall,
    /// A whole number spelled correctly and bigger than [`Coerced::Integer`]
    /// can hold — `tool-calls-at-most: 9223372036854775808`, which is
    /// `i64::MAX` plus one, or `steps-at-most: 1e999`.
    ///
    /// It carries the figure only so that [`Schema::check_ceiling`](crate::Schema)
    /// can tell which END of the scale it ran off; the value itself is not a
    /// number anything downstream may use, which is the whole point of it being
    /// a variant of its own rather than a saturated `i64`.
    ///
    /// The last of the four types to get this answer, and the only reason it
    /// was last is that a bare `9223372036854775808` used to arrive here as a
    /// `Value::Float` and be refused as *"should be a whole number, but it is a
    /// number"* — a sentence that is both false about a correctly-spelled line
    /// and, since it offers `10` as the example, self-contradicting.
    IntegerTooBig(f64),
    /// A whole-number field given a figure that ran off the BOTTOM of the `f64`
    /// it is read in — `steps-at-most: 1e-999`, `-1e-999`.
    ///
    /// The mirror of [`Coerced::IntegerTooBig`], and the last hole C12 left.
    /// `steps-at-most: 1e999` is refused by name as `schema/too-big-to-count`;
    /// measured on the build before this variant, `steps-at-most: 1e-999` got
    /// *"should be a whole number, but it is some text"* — the sentence
    /// `steps-at-most: abc` gets, byte for byte — because keeping an
    /// underflowing scalar as the author's text (which is what stops `pact
    /// show` and the digest losing it) also handed this field a `Value::Str`,
    /// and the noun is read off the value. A line spelled exactly the way a
    /// number is spelled was called text and its author sent hunting for a typo
    /// that is not there, which is the one thing every other arm in this file
    /// exists to prevent.
    ///
    /// It carries no useful figure — `1e-999` and `-1e-999` both arrive as a
    /// zero — so the sign is read off the text, exactly as
    /// [`Coerced::IntegerTooBig`] reads it for a digit run past `i64`.
    ///
    /// **`1.5` is not here**, for the reason it is not at the top either: a
    /// fraction this holds exactly is the wrong KIND of figure, not a figure
    /// that ran off an end, and *"should be a whole number, but it is a
    /// number"* is the true sentence about it.
    IntegerTooSmall(f64),
}

/// Text that parses to zero while the figure the author wrote is not zero — the
/// bottom of the number line, where the parse succeeds and hands back a number
/// this CAN hold that is not the one on the page.
///
/// The same significand rule `yaml::resolve_scalar` and
/// `Schema::check_ceiling` draw, drawn here so the two types that need it
/// during coercion — [`integer`] and [`size`] — ask it in exactly the same
/// words rather than growing two spellings of one question.
///
/// The exponent is deliberately not looked at: the `10` of `0e10` scales a
/// nothing and says nothing about what was meant, while the `1` of `1e-999` is
/// the whole of what the author wrote.
fn underflowed_to_zero(f: f64, text: &str) -> bool {
    if f != 0.0 {
        return false;
    }
    let significand = text.split(['e', 'E']).next().unwrap_or(text);
    significand.chars().any(|c| c.is_ascii_digit() && c != '0')
}

/// The last whole number a double can tell from the next one: 2^53.
///
/// **This is what *"more than this can keep track of"* means**, and for a round
/// the sentence was measured against something else. The ceiling asked
/// `text.parse::<i64>()` — a question about how the figure was SPELLED — so one
/// value got two opposite answers: `temperature: 1e19` loaded cleanly while
/// `temperature: 10000000000000000000`, the same `f64` to the last bit, was
/// refused as *"more than this can keep track of"*, a sentence the first line
/// proves false. Both measured through the shipped binary.
///
/// Past 2^53 the doubles this format reads its numbers in are further apart
/// than 1, so consecutive whole numbers stop being different numbers:
/// `9007199254740993` cannot be written down at all, and `99999999999999999999`
/// and `99999999999999999998` are one figure. Below it every whole number is
/// exact and every author's figure arrives as the figure they wrote. That is a
/// property of the VALUE, so the same bound answers every spelling of it.
///
/// It is deliberately smaller than `i64::MAX`, which it replaced: nothing that
/// was refused before is accepted now, and the sentence is true where it was
/// false. [`crate::Ty::Integer`] keeps `i64` as its own yardstick, because
/// there the machine really is an `i64` and `tool-calls-at-most:
/// 9223372036854775807` is a whole number this holds exactly.
pub const PAST_COUNTING: f64 = 9_007_199_254_740_992.0;

/// A figure a number field cannot keep track of: one that overflowed, or one
/// past the last whole number a double can tell from its neighbour.
///
/// The one question `Ty::Number`, `Ty::Threshold` and `Ty::Size` all ask, so
/// that the three cannot drift into three answers for one figure — which is
/// exactly what happened while the question was asked of the spelling:
/// `context-at-least: 1e19` was *"not a size"* and `context-at-least:
/// 10000000000000000000` loaded cleanly, one value, two doors.
pub(crate) fn past_counting_figure(v: f64) -> bool {
    !v.is_finite() || v.abs() >= PAST_COUNTING
}

/// How close two published figures have to be before `= 80` calls them equal.
///
/// A billionth, and the figure is stated in `spec/comparisons.yaml` rather than
/// only here, because the resolver on the other side of the wire has to allow
/// exactly the same slack: `adapters/python/src/pact_adapters/resolve.py` says
/// its `_HOLDS` table *mirrors* this one, and *"a difference between the two is
/// a model bound on a rule the checker read differently"*. For a release it was
/// not a mirror — this side allowed `f64::EPSILON` and that side `1e-12`, four
/// orders of magnitude apart.
///
/// `f64::EPSILON` was never a tolerance. It is the gap between 1 and the next
/// number a double can hold; around a score of 80 the gap is about `1.4e-14`,
/// sixty-four times wider, so no figure other than a bit-for-bit 80 could ever
/// fall inside an EPSILON of it. `= 80` was an exact-bits test in a tolerance's
/// clothes, and a catalogue publishing `79.999999999999` — the same score, after
/// being written down as text and read back — missed the bar by an amount no
/// reader could see.
///
/// A billionth sits in the gap between the two things a figure can differ by:
/// far wider than the noise of parsing, dividing and adding (hundreds of steps
/// at a score of 80), and far narrower than the two decimal places benchmarks
/// are actually published to (`79.99` is a different score, and is refused).
///
/// Pinned across both ports by
/// `crates/pact-schema/tests/a_comparison_means_the_same_thing_in_both_ports.rs`
/// and its Python twin.
pub const SCORE_TOLERANCE: f64 = 1e-9;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Op {
    Gt,
    Ge,
    Lt,
    Le,
    Eq,
}

impl Op {
    pub fn holds(self, lhs: f64, rhs: f64) -> bool {
        match self {
            Op::Gt => lhs > rhs,
            Op::Ge => lhs >= rhs,
            Op::Lt => lhs < rhs,
            Op::Le => lhs <= rhs,
            Op::Eq => (lhs - rhs).abs() < SCORE_TOLERANCE,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Op::Gt => ">",
            Op::Ge => ">=",
            Op::Lt => "<",
            Op::Le => "<=",
            Op::Eq => "==",
        }
    }
}

/// Try to read `node` as type `ty`. `None` means the value does not fit, and
/// the caller turns that into a diagnostic naming the field.
pub fn check(node: &Node, ty: &crate::Ty) -> Option<Coerced> {
    use crate::Ty;
    match ty {
        Ty::Text => match &node.value {
            Value::Str(s) => Some(Coerced::Text(s.clone())),
            // Numbers and booleans read fine as text; refusing them would be
            // pedantry (`name: 2024` is a perfectly good name).
            Value::Int(i) => Some(Coerced::Text(i.to_string())),
            Value::Float(f) => Some(Coerced::Text(f.to_string())),
            Value::Bool(b) => Some(Coerced::Text(b.to_string())),
            _ => None,
        },
        Ty::YesNo => match &node.value {
            Value::Bool(b) => Some(Coerced::YesNo(*b)),
            Value::Str(s) => yes_no(s).map(Coerced::YesNo),
            _ => None,
        },
        Ty::Number => number(node).map(Coerced::Number),
        Ty::Integer => match &node.value {
            Value::Int(i) => Some(Coerced::Integer(*i)),
            Value::Str(s) => integer(s),
            // A figure the document layer read as a number is asked the same
            // question its text would have been: `tokens-at-most: 1e6` is a
            // million and is a whole number, however it is punctuated. Writing
            // the double back out and reading it as text is not a detour — it is
            // how the two spellings are kept to ONE answer, which is the whole
            // complaint against the round where `1e6` was *"not a whole
            // number"* and `1000000` was.
            Value::Float(f) => integer(&format!("{f}")),
            _ => None,
        },
        Ty::Duration => match &node.value {
            Value::Str(s) => duration(s),
            // A BARE YAML NUMBER IS NOT A LENGTH OF TIME — `finishes-within: 90`
            // is as likely to mean ninety minutes as ninety seconds, and
            // guessing moves a ceiling by sixty times in silence, so the unit is
            // required and `wrong_type` teaches it.
            //
            // **Unless no unit could have saved it.** A figure past the
            // milliseconds this counts in is past them in every unit there is —
            // milliseconds are the smallest — so the missing unit is not what is
            // wrong with the line and "write it like `2s`" is advice that cannot
            // work. Measured before this arm: `finishes-within: 1e999` was
            // *"a longer time than this can keep track of"* while
            // `finishes-within: 1e308` — the same shape, a shorter time — was
            // *"should be a length of time … but it is a number"*, so an author
            // following the first message's own fix could land on the second.
            Value::Float(f) if *f >= u64::MAX as f64 => Some(Coerced::DurationTooLong),
            _ => None,
        },
        Ty::Money => node.as_str().and_then(money),
        Ty::Percent => percent(node),
        Ty::Threshold => node.as_str().and_then(threshold),
        Ty::Size => size(node),
        // A plain file name and an answer shape are both text with one rule
        // about their spelling, so they coerce to the text they are and are
        // checked in `Schema::check_shape` where the field's name is known.
        Ty::FileName | Ty::AnswerShape(_) => node.as_str().map(|s| Coerced::Text(s.to_string())),
        Ty::OneOf(allowed) => {
            let s = node.as_str()?;
            allowed
                .iter()
                .find(|a| a.eq_ignore_ascii_case(s))
                .map(|a| Coerced::Text(a.clone()))
        }
        // Container, address and pass-through types are handled by the caller —
        // an address is checked position by position so the diagnostic can name
        // which of the three words is the wrong one.
        Ty::ListOf(_) | Ty::MapOf(_) | Ty::Group(_) | Ty::EventAddress(..) | Ty::Anything => {
            Some(Coerced::Text(String::new()))
        }
    }
}

fn yes_no(s: &str) -> Option<bool> {
    match s.trim().to_ascii_lowercase().as_str() {
        "yes" | "y" | "true" | "on" | "enabled" => Some(true),
        "no" | "n" | "false" | "off" | "disabled" => Some(false),
        _ => None,
    }
}

/// A whole number, from text spelling one.
///
/// **The same line [`number`], [`duration`] and [`size`] draw, drawn once more
/// for the last type that had not got it.** `tool-calls-at-most:
/// 9223372036854775808` is `i64::MAX` plus one; it is spelled exactly the way a
/// whole number is spelled, and the answer *"should be a whole number, but it
/// is a number"* — which is what it got, because a bare digit run past `i64`
/// used to reach here as a `Value::Float` — is false about the line AND
/// contradicted by its own `fix:`, which offers `10`. It leaves as
/// [`Coerced::IntegerTooBig`] and `Schema::check_ceiling` refuses it by name.
///
/// `steps-at-most: 1e999` is the same sentence one spelling over: it ran off
/// the top of the `f64` it was read as rather than the top of `i64`, and its
/// author needs the same edit — a smaller figure — not a hunt for a typo.
///
/// **Unless there is no digit in it,** exactly as in [`number`]: `inf`, `nan`
/// and `lots` are words spelled where a figure goes, and *"should be a whole
/// number, but it is some text"* is the true sentence for them.
///
/// **And `1.5` is not here at all.** A fraction is not a whole number that ran
/// off an end; it is the wrong kind of figure, `None`, and the wrong-type
/// sentence about it is a true one.
///
/// **BUT `1e6` IS A WHOLE NUMBER**, and saying otherwise was the same
/// self-contradicting sentence one spelling further on. Measured through the
/// shipped binary: `tokens-at-most: 1e6` was refused as *"should be a whole
/// number, but it is a number"* with the fix *"Change it to a whole number"* —
/// about a line that says one million, which is a whole number, and an `i64`
/// holds it to the last bit. `1000000.0` got the same. A whole number the
/// author spelled with an exponent or a trailing point is read as the whole
/// number it spells, through `pact_doc::whole_number_written`, which is the same
/// function the document layer decides losslessness with. `1.5` still spells no
/// whole number and is still `None`.
fn integer(s: &str) -> Option<Coerced> {
    let s = s.trim();
    if let Ok(i) = s.parse::<i64>() {
        return Some(Coerced::Integer(i));
    }
    let f = s.parse::<f64>().ok()?;
    // The bottom of the same scale, asked before the top because a figure that
    // underflowed is finite and would otherwise fall out of this function as
    // `None` and be called text. See [`Coerced::IntegerTooSmall`]. The sign is
    // read off the text because `1e-999` and `-1e-999` both arrive as a zero,
    // and the figure is used only to pick which end of the scale the sentence
    // names.
    if underflowed_to_zero(f, s) {
        return Some(Coerced::IntegerTooSmall(if s.starts_with('-') {
            -0.0
        } else {
            0.0
        }));
    }
    if !f.is_finite() {
        // `steps-at-most: 1e999` ran off the top of the double it was read as
        // rather than the top of `i64`, and its author needs the same edit — a
        // smaller figure — not a hunt for a typo. `inf` and `lots` carry no
        // digit, never overflowed anything, and are words.
        return crate::has_a_digit(s).then_some(Coerced::IntegerTooBig(f));
    }
    // Not a whole number at all — the wrong KIND of figure, and `wrong_type`
    // says so truthfully.
    pact_doc::whole_number_written(s)?;
    // A whole number `i64` cannot hold. The two ways of not holding one are the
    // same edit for the author: `9223372036854775808` is past the end of the
    // machine, and `99999999999999999999` is past the point where the double it
    // was read through can tell one figure from the next (it comes back as
    // `1e20`), so the figure that would be stored is not the figure on the page.
    //
    // `9.223_372_036_854_776e18` is 2^63 exactly, so the half-open range is
    // precisely the figures the cast below is exact for.
    const PAST_I64: std::ops::Range<f64> = -9.223_372_036_854_776e18..9.223_372_036_854_776e18;
    if pact_doc::whole_number_past_holding(s) || !PAST_I64.contains(&f) {
        return Some(Coerced::IntegerTooBig(f));
    }
    Some(Coerced::Integer(f as i64))
}

/// A number, from a number or from text spelling one.
///
/// **A figure that overflowed is not the same mistake as a word.**
/// `"1e999".parse::<f64>()` does not fail — it hands back infinity, and
/// `temperature: 1e999` loaded clean and travelled on as a setting no provider
/// can be given. `yaml::resolve_scalar` no longer reads a number it cannot hold
/// as a number and keeps the author's text instead, which is what stops the
/// value vanishing; but the text arm here would parse that text straight back
/// into the infinity it was kept out of, and the refusal one layer down would
/// buy nothing.
///
/// So a non-finite result is kept and handed up as [`Coerced::Number`], where
/// [`Schema::check_ceiling`](crate::Schema) refuses it by the field's own name
/// and line — the same door `99999999999999999999h` and `1e400 USD` go through,
/// and for the same reason: `1e999` is spelled exactly the way a number is
/// spelled, so *"should be a number, but it is some text"* would send its author
/// hunting for a typo that is not there.
///
/// **Unless there is no digit in it.** `inf`, `nan` and `Infinity` all parse to
/// a non-finite float and none of them overflowed anything — they are words
/// spelled where a figure goes, `None` here, and `schema/wrong-type` above,
/// which is the true sentence for them. That is the line `money_past_counting`
/// draws for money, drawn once more in the same place.
fn number(node: &Node) -> Option<f64> {
    let f = match &node.value {
        Value::Int(i) => *i as f64,
        Value::Float(f) => *f,
        Value::Str(s) => s.trim().parse::<f64>().ok()?,
        _ => return None,
    };
    (f.is_finite() || crate::has_a_digit(node.as_str().unwrap_or_default())).then_some(f)
}

/// `2s`, `500ms`, `1m30s`, `1m 30s`, `2 minutes`, `30S`, `1d`. Returns
/// milliseconds.
///
/// A number and a unit: `ms`, `s`, `m`, `h`, `d` or any of their long names,
/// case-insensitive, the space optional, several parts running together, and a
/// bare number read as seconds. Every one of those is a spelling somebody
/// reaches for, and the same SPELLINGS are read on the other side by
/// `pact_adapters.limits.seconds` — an author who writes `1m30s` and gets 1.0
/// back would have a ceiling ninety times tighter than the one they wrote.
///
/// The two are not the same set at both ends, and deliberately: this side is
/// the stricter one. A length of time past the milliseconds it is counted in is
/// refused as `schema/too-long-to-count`, while the Python reader — which counts
/// in floats and has no such end — takes it. Nothing can travel through the gap,
/// because `pact check` is the gate and it is this side.
///
/// **Where the bare figure written in a file is refused, and where it is not.**
/// A bare `90` typed into a document is a YAML number, never reaches this
/// function, and is refused as `schema/wrong-type` with the fix that teaches the
/// unit — ninety could be minutes or seconds and a ceiling out by sixty times
/// would be applied in silence. That rule lives in [`check`], where the value's
/// own kind can still be seen; here, where everything is text, a bare figure is
/// a number of seconds, which is what `"90"` in quotes means and what the Python
/// reader takes.
///
/// **An exponent is part of the figure, not a unit.** For a round the loop below
/// read the `e` of `1e999s` as the start of a unit called `e`, found no such
/// unit and answered `None`, so every figure written that way — `1e999s`,
/// `1e300h`, `1e999 seconds`, and `1e6s`, which is a perfectly ordinary million
/// seconds — was told it *"should be a length of time … but it is some text"*,
/// the sentence this whole file exists to delete, about a line carrying exactly
/// the unit the help prescribes. Only the bare spelling had been closed, by a
/// special case above the loop that fired on `+inf` alone.
///
/// What this deliberately does NOT decide is whether the length of time is a
/// USABLE one. `0s` parses here — it is a well-formed length of time — and is
/// refused one layer up by `Schema::check_floor`, where the field's name and
/// line are known and the message can name them. Refusing it here would report
/// `0s` as "not a length of time", which is both false and unfixable.
///
/// The same goes for the other end. `99999999999999999999h` is spelled exactly
/// the way the help says to spell it and is more milliseconds than there are
/// milliseconds to count with, so it comes back as [`Coerced::DurationTooLong`]
/// and `Schema::check_ceiling` refuses it by name. It is not `None` for the
/// same reason `0s` is not: the author's line is not misspelled and telling
/// them it is would send them hunting for a typo that is not there.
fn duration(s: &str) -> Option<Coerced> {
    let s = s.trim().to_ascii_lowercase();
    if s.is_empty() {
        return None;
    }
    // `None` here does not mean "not a length of time" — it means the parts so
    // far have already run off the end of the milliseconds they are kept in.
    // See `flush`, which is where they run off it.
    let mut total: Option<u64> = Some(0);
    let mut num = String::new();
    let mut unit = String::new();
    let mut any = false;

    let flush = |num: &mut String,
                 unit: &mut String,
                 total: &mut Option<u64>,
                 any: &mut bool|
     -> bool {
        if num.is_empty() {
            return unit.is_empty();
        }
        let Ok(v) = num.parse::<f64>() else { return false };
        let mult = match unit.trim() {
            "ms" | "millisecond" | "milliseconds" => 1.0,
            "s" | "sec" | "secs" | "second" | "seconds" | "" => 1000.0,
            "m" | "min" | "mins" | "minute" | "minutes" => 60_000.0,
            "h" | "hr" | "hrs" | "hour" | "hours" => 3_600_000.0,
            "d" | "day" | "days" => 86_400_000.0,
            _ => return false,
        };
        // This was `*total += (v * mult) as u64`, and both halves of that were
        // a trap. A float-to-integer cast in Rust SATURATES rather than
        // wrapping, so one oversized part pinned the running total at the
        // largest number there is; the NEXT part's addition then went over the
        // top of it — `attempt to add with overflow` in a debug build, which is
        // what `cargo run` and the README's own instructions give an author,
        // and in a release build a silent wrap to a ceiling nobody asked for.
        //
        // So the cast is guarded before it can saturate and the addition is
        // checked, and either way the answer is the same: this is a length of
        // time, and it is not one that fits, so it is carried out of here as
        // that rather than added up into a number that is a lie.
        let ms = v * mult;
        // And the cast ROUNDS rather than truncating, which is the other half
        // of "the number that was written is the number that arrives". A
        // fraction of a second is not held exactly by a double: `1.001 * 1000.0`
        // is `1000.9999999999999`, and a cast that throws the tail away handed
        // a scheduler 1000 ms for `answer-within: 1.001s` — a wait a
        // millisecond shorter than the one written, silently, which is the
        // small end of the same complaint `1m30s` makes at the large end.
        // Measured through the shipped command before this line rounded:
        // `pact waits` reported `"deadline-ms": 1000`.
        //
        // Rounding cannot lift anything over the top, because it only moves a
        // figure by half a millisecond and the guard below is checked on the
        // unrounded product; and it cannot turn no time at all into some, since
        // `0.4ms` still rounds to zero and is still refused at the floor.
        //
        // `u64::MAX as f64` is 2^64 exactly, so `ms >= it` is precisely "the
        // cast below is the one that would saturate".
        *total = if ms >= u64::MAX as f64 {
            None
        } else {
            (*total).and_then(|t| t.checked_add(ms.round() as u64))
        };
        *any = true;
        num.clear();
        unit.clear();
        true
    };

    let chars: Vec<char> = s.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c.is_ascii_digit() || c == '.' {
            if !unit.is_empty() && !flush(&mut num, &mut unit, &mut total, &mut any) {
                return None;
            }
            num.push(c);
        } else if is_exponent_at(&chars, i, &num, &unit) {
            // `1e999s`, `1e300h`, `1e6 seconds`. The `e` belongs to the figure,
            // and the sign after it, if there is one.
            num.push('e');
            if matches!(chars.get(i + 1), Some('+' | '-')) {
                i += 1;
                num.push(chars[i]);
            }
        } else if c.is_ascii_alphabetic() {
            unit.push(c);
        } else if c.is_whitespace() {
            // `2 minutes` — a space between number and unit is fine.
        } else {
            return None;
        }
        i += 1;
    }
    if !flush(&mut num, &mut unit, &mut total, &mut any) {
        return None;
    }
    match (any, total) {
        // Nothing at all was written, which is not a length of time.
        (false, _) => None,
        (true, Some(ms)) => Some(Coerced::Duration(ms)),
        (true, None) => Some(Coerced::DurationTooLong),
    }
}

/// Whether the character at `i` is the `e` of an exponent rather than the first
/// letter of a unit.
///
/// It is one when a figure has already been written, no unit has started, and
/// what follows is a run of digits with an optional sign in front — which is the
/// whole of what an exponent is. No unit this reads begins with `e`, so nothing
/// legitimate is taken away: `2 seconds` starts its unit at the `s`, and by the
/// time the `e` of *seconds* arrives the unit is not empty.
fn is_exponent_at(chars: &[char], i: usize, num: &str, unit: &str) -> bool {
    if chars[i] != 'e' || num.is_empty() || !unit.is_empty() {
        return false;
    }
    let mut j = i + 1;
    if matches!(chars.get(j), Some('+' | '-')) {
        j += 1;
    }
    matches!(chars.get(j), Some(c) if c.is_ascii_digit())
}

/// `0.05 USD`, `USD 0.05`, `$0.05`. Currency is preserved, never converted.
fn money(s: &str) -> Option<Coerced> {
    let s = s.trim();
    let (amount, currency) = if let Some(rest) = s.strip_prefix('$') {
        (rest.trim().parse::<f64>().ok()?, "USD".to_string())
    } else {
        let mut parts = s.split_whitespace();
        let a = parts.next()?;
        let b = parts.next();
        if parts.next().is_some() {
            return None;
        }
        match (a.parse::<f64>(), b) {
            (Ok(v), Some(c)) => (v, c.to_ascii_uppercase()),
            (Err(_), Some(v)) => (v.parse::<f64>().ok()?, a.to_ascii_uppercase()),
            _ => return None,
        }
    };
    if currency.len() != 3 || !currency.chars().all(|c| c.is_ascii_alphabetic()) {
        return None;
    }
    Some(Coerced::Money { amount, currency })
}

/// `90%` → 0.9. A bare `0.9` is also accepted, but `90` is not — it would be
/// ambiguous, and guessing wrong here silently changes a pass threshold.
///
/// **Both spellings are held to the same range**, and for one round only the
/// bare-decimal one was. `must-pass: -50%` loaded clean and made a six-of-six
/// failing suite report PASS; `when-full: 900%` loaded clean and meant tidying
/// could never fire; `shares: {a: -50%, b: 150%}` summed to exactly 1.0, so the
/// share check passed and one real teammate got an allowance of zero. A share of
/// the whole is between none of it and all of it — that is a property of the
/// TYPE, so it belongs here where no field can forget it, exactly as money
/// carries a currency and a duration is more than nothing.
///
/// **And both ENDS of it are answered, which for a round only one was.** The
/// bottom got its own sentence — `must-pass: 1e-999%` is *"closer to zero than
/// this can keep track of"* — while the top was left as *"should be a
/// percentage, like `90%`, but it is some text"*, measured on `when-full:
/// 1e999%` through the shipped binary. One field reading correctly at one end
/// only is the defect this pass exists to close, and *"some text"* about a line
/// that is a figure is the sentence it exists to delete. A share past holding is
/// [`Coerced::PercentPastHolding`] and `Schema::check_ceiling` names it.
///
/// `150%` is deliberately NOT that. It is a share this holds perfectly well and
/// simply more than all of it, which is a different thing to tell an author, and
/// `wrong_type` — whose fix says *"a share of the whole, so between `0%` and
/// `100%`"* — is the sentence for it.
fn percent(node: &Node) -> Option<Coerced> {
    let held = |v: f64| (0.0..=1.0).contains(&v).then_some(Coerced::Percent(v));
    match &node.value {
        Value::Str(s) => {
            let t = s.trim();
            let v = match t.strip_suffix('%') {
                Some(n) => n.trim().parse::<f64>().ok()? / 100.0,
                None => t.parse::<f64>().ok()?,
            };
            // A figure that overflowed on the way in, told apart from a WORD by
            // the same line every other type here draws: `inf%` carries no digit
            // and never overflowed anything.
            if !v.is_finite() {
                return crate::has_a_digit(t).then_some(Coerced::PercentPastHolding(v));
            }
            held(v)
        }
        Value::Float(f) => held(*f),
        Value::Int(0) => Some(Coerced::Percent(0.0)),
        Value::Int(1) => Some(Coerced::Percent(1.0)),
        _ => None,
    }
}

/// `32k`, `128k`, `1m`, `200000` — a count of tokens.
///
/// It exists because `needs.context-at-least` was `type: text` and
/// `context-at-least: quite a lot really` loaded clean and reached the resolver
/// verbatim, where it was compared against a real context window. Every other
/// quantity in the format has a type; a token count is a quantity.
///
/// `k` and `m` are decimal thousands and millions, not 1024s: an author writing
/// `32k` means the number a model card prints, and model cards print 32000.
///
/// The top end is [`Coerced::SizeTooBig`] rather than `None`, for the reason
/// [`duration`] gives at length: `99999999999999999999m` is spelled the way the
/// help says to spell it, so "not a size" would be a false sentence about a
/// correct line. `Schema::check_ceiling` refuses it by name.
///
/// **A figure the document layer read as a number is a count too**, and for a
/// round it was not: `context-at-least: 1e19` fell out of the `_ => None` below
/// and was told it *"should be a size, like `32k` or `200000`, but it is a
/// number"* — a sentence that contradicts its own example — while
/// `context-at-least: 10000000000000000000`, the same `f64` to the last bit,
/// loaded cleanly. One value, two doors, two opposite answers; both measured
/// through the shipped binary. The double is written back out and read as the
/// text it would have been, so there is one door.
fn size(node: &Node) -> Option<Coerced> {
    let text = match &node.value {
        Value::Int(i) if *i >= 0 => return Some(Coerced::Size(*i as u64)),
        Value::Str(s) => s.trim().to_ascii_lowercase(),
        Value::Float(f) => format!("{f}"),
        _ => return None,
    };
    if text.is_empty() {
        return None;
    }
    let (digits, mult) = match text.strip_suffix('k') {
        Some(rest) => (rest, 1_000.0),
        None => match text.strip_suffix('m') {
            Some(rest) => (rest, 1_000_000.0),
            None => (text.as_str(), 1.0),
        },
    };
    let digits = digits.trim();
    if digits.is_empty() {
        return None;
    }
    let v = digits.parse::<f64>().ok()?;
    // `nan` and `inf` parse as numbers and are not counts of anything, so they
    // leave as `None` — "not a size" is the true sentence about them — rather
    // than as the "too big" below, which would send an author looking for a
    // smaller number to write in place of a word. A count below zero is not a
    // count either, and `-1e999` gets the same answer as `-5` for the same
    // reason rather than a ranking of how far below zero it is.
    if v.is_nan() || v < 0.0 {
        return None;
    }
    // **BUT A FIGURE THAT OVERFLOWED IS NOT A WORD**, and for one round this
    // line did not know the difference: `!v.is_finite()` sent
    // `context-at-least: 1e999` out as `None` and the author was told their
    // line *"should be a size, like `32k` or `200000`, but it is some text"* —
    // about a line that is a figure, with the correct answer
    // (`schema/too-big-to-count`) sitting one branch below and unreachable.
    // This is the same `is_finite`-or-a-digit line `number` draws at the top of
    // this file and `money_past_counting` draws for money; it is drawn here
    // because `1e999` and `99999999999999999999m` are the same mistake and must
    // not get two different sentences.
    if !v.is_finite() {
        return crate::has_a_digit(digits).then_some(Coerced::SizeTooBig);
    }
    // **AND A FIGURE THAT UNDERFLOWED IS NOT A COUNT OF NOTHING.** The exact
    // mirror of the arm above, and it is asked of the FIGURE BEFORE the
    // multiplier because that is the only place the two lossy zeros can still
    // be told apart: `1e-999m` and `0.0004k` both reach the cast below as a
    // product that truncates to zero, and only the first one lost its figure on
    // the way in. See [`Coerced::SizeTooSmall`].
    if underflowed_to_zero(v, digits) {
        return Some(Coerced::SizeTooSmall);
    }
    // This was `Some((v * mult) as u64)`, and it is the same trap `duration`
    // fell into one screen up: a float-to-integer cast in Rust SATURATES, so
    // `99999999999999999999m` came out as the largest whole number there is —
    // a requirement no model can meet — and `pact check` said `OK — loaded
    // cleanly` about it. There is no addition here to overflow afterwards, so
    // it never crashed; it was only ever quietly wrong, which is the half of
    // the duration defect that a release build had.
    //
    // The bound is [`PAST_COUNTING`] and not `u64::MAX`, because the count is
    // multiplied and compared as a double and a double stops telling one whole
    // number from the next at 2^53. `context-at-least: 10000000000000000000`
    // used to load cleanly as 10000000000000000000 tokens — a requirement no
    // model can meet, out of a figure the machine cannot count to — while
    // `context-at-least: 1e19`, the same value, was refused as not a size at
    // all. One figure, one answer, and the answer is the true one.
    let tokens = v * mult;
    if past_counting_figure(tokens) {
        return Some(Coerced::SizeTooBig);
    }
    Some(Coerced::Size(tokens as u64))
}

/// `> 80`, `>=0.8`, `< 200`. The syntax an author writes for a bar to clear.
///
/// The figure is read by exactly the rule [`number`] reads one by, because it is
/// the same figure with a comparison in front of it: `MMLU: "> 1e999"` parsed to
/// a bar of `> inf`, which no published benchmark score can ever clear, and the
/// whole `needs:` block became unmeetable with `pact check` saying *"loaded
/// cleanly"*. It is handed up and refused by name in
/// [`Schema::check_ceiling`](crate::Schema); `> inf`, carrying no digit, is a
/// word and stays `schema/wrong-type`.
fn threshold(s: &str) -> Option<Coerced> {
    let s = s.trim();
    let (op, rest) = if let Some(r) = s.strip_prefix(">=") {
        (Op::Ge, r)
    } else if let Some(r) = s.strip_prefix("<=") {
        (Op::Le, r)
    } else if let Some(r) = s.strip_prefix("==") {
        (Op::Eq, r)
    } else if let Some(r) = s.strip_prefix('>') {
        (Op::Gt, r)
    } else if let Some(r) = s.strip_prefix('<') {
        (Op::Lt, r)
    } else if let Some(r) = s.strip_prefix('=') {
        (Op::Eq, r)
    } else {
        return None;
    };
    let rest = rest.trim();
    let value = match rest.strip_suffix('%') {
        Some(n) => n.trim().parse::<f64>().ok()? / 100.0,
        None => rest.parse::<f64>().ok()?,
    };
    if !value.is_finite() && !crate::has_a_digit(rest) {
        return None;
    }
    Some(Coerced::Threshold { op, value })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Ty;
    use camino::Utf8Path;
    use pact_doc::parse_yaml;

    fn val(yaml_value: &str) -> Node {
        let doc = parse_yaml(&format!("v: {yaml_value}\n"), Utf8Path::new("t.yaml")).unwrap();
        doc.get("v").unwrap().clone()
    }

    #[test]
    fn yes_no_accepts_what_people_actually_write() {
        for (s, expected) in [
            ("yes", true), ("Yes", true), ("y", true), ("true", true), ("on", true),
            ("enabled", true), ("no", false), ("N", false), ("false", false), ("off", false),
        ] {
            assert_eq!(
                check(&val(s), &Ty::YesNo),
                Some(Coerced::YesNo(expected)),
                "'{s}' should read as {expected}"
            );
        }
        assert_eq!(check(&val("maybe"), &Ty::YesNo), None);
    }

    #[test]
    fn norway_is_only_a_boolean_where_a_boolean_was_asked_for() {
        // As text, `NO` is the country. The two layers together are what make
        // this safe: the parser never guesses, the schema always asks.
        assert_eq!(check(&val("NO"), &Ty::Text), Some(Coerced::Text("NO".into())));
        assert_eq!(check(&val("NO"), &Ty::YesNo), Some(Coerced::YesNo(false)));
    }

    #[test]
    fn durations_accept_the_obvious_spellings() {
        for (s, ms) in [
            ("500ms", 500), ("2s", 2000), ("30s", 30_000), ("1m", 60_000),
            ("1m30s", 90_000), ("2 minutes", 120_000), ("1h", 3_600_000), ("90", 90_000),
            // The rest of the grammar, which worked all along and which the
            // help now names — the point being that this table and the sentence
            // in `wrong_type` must not be allowed to drift apart. The test that
            // holds them together is
            // `durations_say_what_they_accept.rs`.
            ("1m 30s", 90_000), ("5 minutes", 300_000), ("30S", 30_000),
            ("1d", 86_400_000), ("999999h", 3_599_996_400_000),
            ("250 milliseconds", 250), ("2 hours 30 minutes", 9_000_000),
            // Big, and each one still a number of milliseconds that fits. The
            // guard against the ones that do NOT fit must not have taken these
            // with it, and the sums have to come out to the millisecond: a
            // wrapped total is a wrong ceiling that says nothing about itself.
            ("1000000h", 3_600_000_000_000), ("100000h 30m", 360_001_800_000),
            ("9999d 23h 59m 59s 999ms", 863_999_999_999),
        ] {
            assert_eq!(
                check(&val(&format!("\"{s}\"")), &Ty::Duration),
                Some(Coerced::Duration(ms)),
                "'{s}' should be {ms}ms"
            );
        }
        assert_eq!(check(&val("soon"), &Ty::Duration), None);
        assert_eq!(check(&val("\"5 bananas\""), &Ty::Duration), None);
    }

    /// A fraction of a second comes out as the fraction that was written.
    ///
    /// The small end of the same rule the large end is held to above: a
    /// ceiling that is not the one on the page is wrong however small the
    /// difference, because nothing anywhere says it moved. `1.001 * 1000.0` is
    /// `1000.9999999999999` in a double, and a cast that threw the tail away
    /// made `1.001s` into a wait of 1000ms.
    ///
    /// Mutation: put `ms as u64` back in place of `ms.round() as u64`. Measured
    /// with it back: `1.001s` reports 1000, `1.005s` reports 1004, and this
    /// test fails on its first line. The whole-millisecond spellings above stay
    /// green under it, which is why they cannot hold this on their own.
    #[test]
    fn a_fraction_of_a_second_is_the_fraction_that_was_written() {
        for (s, ms) in [
            ("1.001s", 1_001_u64),
            ("1.005s", 1_005),
            ("1.007s", 1_007),
            ("2.29m", 137_400),
            // Rounding must not have invented time where there was none: this
            // is still no time at all, and still the floor's business.
            ("0.4ms", 0),
            // Nor lost any: a half is a half and rounds up, not away.
            ("0.5ms", 1),
        ] {
            assert_eq!(
                check(&val(&format!("\"{s}\"")), &Ty::Duration),
                Some(Coerced::Duration(ms)),
                "'{s}' should be {ms}ms"
            );
        }
    }

    #[test]
    fn a_length_of_time_too_long_to_count_parses_here_and_is_refused_one_layer_up() {
        // The other end of the same argument, and the one that used to crash.
        // These are spelled correctly and come to more milliseconds than a
        // whole number here holds, so they leave as what they are — a length of
        // time that does not fit — rather than as `None` ("not a length of
        // time", untrue) or a number (`Schema::check_ceiling` names the field).
        for s in [
            // One part on its own, whose cast to a whole number saturates.
            "99999999999999999999h",
            // The reported line, where the second part was added to a total
            // already pinned at the largest number there is.
            "99999999999999999999h 99999999999999999999h 99999999999999999999h",
            // And parts that each fit and together do not.
            "18000000000000000000ms 400000000000000000ms 100000000000000000ms",
            // THE BOUNDARY THE GUARD IS WRITTEN ON, which is the one thing the
            // three lines above cannot reach. `u64::MAX as f64` is 2^64 exactly
            // and this is 2^64 milliseconds, so it is the first figure the cast
            // would saturate on rather than convert — the only value that can
            // tell `ms >= u64::MAX as f64` from `ms >`.
            //
            // Mutation: write the guard `>` instead of `>=`. Measured with it:
            // this comes back as `Duration(18446744073709551615)`, `pact check`
            // says `OK — loaded cleanly` and `pact waits` hands a scheduler
            // `"deadline-ms": 18446744073709551615` — the saturated top, one
            // short of what was written and a ceiling nobody chose, which is
            // exactly the defect the other three lines exist to refuse. Without
            // this line the whole suite stays green under that edit.
            "18446744073709551616ms",
        ] {
            assert_eq!(
                check(&val(&format!("\"{s}\"")), &Ty::Duration),
                Some(Coerced::DurationTooLong),
                "'{s}' is longer than can be counted"
            );
        }
    }

    #[test]
    fn a_length_of_time_of_none_parses_here_and_is_refused_one_layer_up() {
        // `0s` IS a well-formed length of time and this layer says so. Whether
        // it is a USABLE one is a question about the field it was written on —
        // its name, its line, and what a promise of no time would do to a run —
        // and that is `Schema::check_floor`, which refuses it with
        // `schema/below-the-floor`. Refusing it here would report `0s` as "not
        // a length of time", which is both false and unfixable.
        for s in ["0s", "0", "0ms", "0.4ms"] {
            assert_eq!(
                check(&val(&format!("\"{s}\"")), &Ty::Duration),
                Some(Coerced::Duration(0)),
                "'{s}' is no time at all"
            );
        }
    }

    #[test]
    fn money_keeps_its_currency() {
        let expect = |a: f64, c: &str| Some(Coerced::Money { amount: a, currency: c.into() });
        assert_eq!(check(&val("\"0.05 USD\""), &Ty::Money), expect(0.05, "USD"));
        assert_eq!(check(&val("\"USD 0.05\""), &Ty::Money), expect(0.05, "USD"));
        assert_eq!(check(&val("\"$0.05\""), &Ty::Money), expect(0.05, "USD"));
        assert_eq!(check(&val("\"12 eur\""), &Ty::Money), expect(12.0, "EUR"));
        // No implicit currency: a bare number could mean anything.
        assert_eq!(check(&val("0.05"), &Ty::Money), None);
        assert_eq!(check(&val("\"0.05 DOLLARS\""), &Ty::Money), None);
    }

    #[test]
    fn percentages_refuse_the_ambiguous_form() {
        assert_eq!(check(&val("\"90%\""), &Ty::Percent), Some(Coerced::Percent(0.9)));
        assert_eq!(check(&val("0.9"), &Ty::Percent), Some(Coerced::Percent(0.9)));
        // `90` might mean 90% or 9000%. Guessing would silently move a pass bar.
        assert_eq!(check(&val("90"), &Ty::Percent), None);
    }

    #[test]
    fn a_share_of_the_whole_is_between_none_of_it_and_all_of_it() {
        // For one round the `%` spelling was unbounded while the bare-decimal
        // one was filtered, so `must-pass: -50%` loaded clean and a suite where
        // every case failed reported PASS. Both spellings, one range.
        for s in ["-50%", "150%", "900%", "-0.5"] {
            assert_eq!(check(&val(&format!("\"{s}\"")), &Ty::Percent), None, "'{s}' is not a share");
        }
        assert_eq!(check(&val("\"0%\""), &Ty::Percent), Some(Coerced::Percent(0.0)));
        assert_eq!(check(&val("\"100%\""), &Ty::Percent), Some(Coerced::Percent(1.0)));
    }

    #[test]
    fn a_size_accepts_the_spellings_a_model_card_prints() {
        for (s, n) in [("32k", 32_000), ("128k", 128_000), ("1m", 1_000_000), ("200000", 200_000)] {
            assert_eq!(
                check(&val(&format!("\"{s}\"")), &Ty::Size),
                Some(Coerced::Size(n)),
                "'{s}' should be {n}"
            );
        }
        assert_eq!(check(&val("200000"), &Ty::Size), Some(Coerced::Size(200_000)));
        for s in ["quite a lot really", "-5k", "k", "", "nan", "inf"] {
            assert_eq!(check(&val(&format!("\"{s}\"")), &Ty::Size), None, "'{s}' is not a size");
        }
        // Big and still a number a model card could print — well under the top.
        assert_eq!(
            check(&val("\"9999999999k\""), &Ty::Size),
            Some(Coerced::Size(9_999_999_999_000))
        );
        // And past the top, where the cast used to saturate silently. Not
        // `None`: the spelling is the same spelling `32k` uses.
        for s in ["99999999999999999999m", "99999999999999999999999999999", "1e300m"] {
            assert_eq!(
                check(&val(&format!("\"{s}\"")), &Ty::Size),
                Some(Coerced::SizeTooBig),
                "'{s}' is more tokens than can be counted"
            );
        }
        // UNQUOTED, which is the form this field's own `fix:` prescribes and
        // the only form an author is ever told to write. Every case above wraps
        // its input in quotes before `val` sees it, so all of them exercise a
        // `Value::Str` — and for these three spellings the document layer used
        // to hand up a `Value::Float` instead, which fell out of `size` at its
        // `_ => return None` and never reached the branch this test certifies.
        for s in ["99999999999999999999", "1e999", "1e999k"] {
            assert_eq!(
                check(&val(s), &Ty::Size),
                Some(Coerced::SizeTooBig),
                "'{s}' unquoted must answer what '{s}' quoted answers"
            );
        }
        // A figure that ran off the BOTTOM is not a count of no tokens. It is
        // the same corruption at the other end of the same scale, and
        // `Schema::check_ceiling` says so by name.
        //
        // THE THREE ZEROS, WHICH FOR ONE ROUND WERE ONE. This loop used to
        // require `Some(Size(0))` for `1e-999`, `1e-999m` AND `0.0000001k`
        // together, and that grouping is what let the ceiling tell `0.0004k`
        // and `"0.5"` they were "closer to zero than this can keep track of" —
        // false about a figure an `f64` holds to the last bit, with a fix
        // (*"any number further from zero"*) they already satisfied. Only the
        // first two lost anything on the way in; the rest are real figures that
        // TRUNCATE at the `as u64`, which is `check_floor`'s "no tokens at all",
        // and an authored `0k` is neither.
        for s in ["1e-999", "1e-999m"] {
            assert_eq!(
                check(&val(s), &Ty::Size),
                Some(Coerced::SizeTooSmall),
                "'{s}' lost its figure on the way in; the ceiling names it"
            );
        }
        for s in ["0.0000001k", "0.0004k", "\"0.5\"", "\"0.9\""] {
            assert_eq!(
                check(&val(s), &Ty::Size),
                Some(Coerced::Size(0)),
                "'{s}' is a figure this holds exactly that rounds to no tokens; the floor's"
            );
        }
        for s in ["0", "0k", "\"0.0\"", "0e10"] {
            assert_eq!(
                check(&val(s), &Ty::Size),
                Some(Coerced::Size(0)),
                "'{s}' is a zero somebody meant and carries no figure that was lost"
            );
        }
        // THE SPELLING THAT USED TO ANSWER DIFFERENTLY, and no longer does.
        // C12 recorded it as a known gap rather than closing it: a bare `0.5`
        // was a `Value::Float`, left at the `_ => return None`, and its author
        // was told *"should be a size, like `32k` or `200000`, but it is a
        // number"* where the quoted `"0.5"` was told *"is 0.5, which is no
        // tokens at all"*.
        //
        // C10 closed it, because the same gap at the TOP of the scale was not
        // survivable: `context-at-least: 1e19` was refused as not-a-size while
        // `context-at-least: 10000000000000000000`, the same `f64` to the last
        // bit, loaded cleanly as a requirement no model can meet. One figure
        // cannot have two answers, so the double is written back out and read
        // as the text it would have been — and `32000.0` is a size now, which
        // is the widening C12 named as the price and is the same leniency
        // `Value::Int` has always had.
        assert_eq!(
            check(&val("0.5"), &Ty::Size),
            Some(Coerced::Size(0)),
            "a bare float answers exactly as its quoted twin: the floor's"
        );
        assert_eq!(
            check(&val("32000.0"), &Ty::Size),
            Some(Coerced::Size(32000)),
            "and a round figure with a point on it is the size it says"
        );
        assert_eq!(
            check(&val("1e19"), &Ty::Size),
            Some(Coerced::SizeTooBig),
            "one figure, one answer, at the end where it mattered"
        );
        assert_eq!(check(&val("10000000000000000000"), &Ty::Size), Some(Coerced::SizeTooBig));
    }

    /// The bottom of the whole-number scale, which is the mirror of
    /// [`Coerced::IntegerTooBig`] and was the last spelling C12 left calling a
    /// figure text.
    #[test]
    fn a_whole_number_field_tells_a_vanished_figure_from_a_word() {
        // Ran off the bottom: refused by name, both signs.
        for s in ["1e-999", "-1e-999", "1e-400"] {
            assert!(
                matches!(check(&val(s), &Ty::Integer), Some(Coerced::IntegerTooSmall(_))),
                "'{s}' is a figure that vanished, not a word"
            );
        }
        // A WORD is not this, and neither is a fraction this holds exactly:
        // `1.5` is the wrong KIND of figure and "should be a whole number, but
        // it is a number" is the true sentence about it.
        for s in ["abc", "lots", "1.5", "0.5"] {
            assert!(
                !matches!(check(&val(s), &Ty::Integer), Some(Coerced::IntegerTooSmall(_))),
                "'{s}' did not run off the bottom of anything"
            );
        }
        // And a zero somebody meant stays a whole number.
        assert_eq!(check(&val("0"), &Ty::Integer), Some(Coerced::Integer(0)));
    }

    #[test]
    fn a_whole_number_past_holding_is_too_big_rather_than_a_typo() {
        assert_eq!(check(&val("25"), &Ty::Integer), Some(Coerced::Integer(25)));
        assert_eq!(
            check(&val("9223372036854775807"), &Ty::Integer),
            Some(Coerced::Integer(i64::MAX)),
            "the largest whole number this can hold is still one"
        );
        // Past holding — `9223372036854775808` is `i64::MAX` plus one, and
        // `1e999` ran off the top of the float it was read as. Both are spelled
        // the way a whole number is spelled.
        for (s, positive) in [("9223372036854775808", true), ("1e999", true), ("-1e999", false)] {
            match check(&val(s), &Ty::Integer) {
                Some(Coerced::IntegerTooBig(n)) => assert_eq!(
                    n.is_sign_positive(),
                    positive,
                    "'{s}' must say which end of the scale it ran off"
                ),
                other => panic!("'{s}' is a whole number past holding, got {other:?}"),
            }
        }
        assert!(
            matches!(
                check(&val("-9223372036854775809"), &Ty::Integer),
                Some(Coerced::IntegerTooBig(_))
            ),
            "one past the bottom of `i64` is past holding too"
        );
        // And the things that are NOT that: a word carries no digit, and a
        // fraction is not a whole number that ran off an end — it is the wrong
        // kind of figure, and "not a whole number" is true about it.
        for s in ["inf", "nan", "lots", "1.5"] {
            assert_eq!(check(&val(s), &Ty::Integer), None, "'{s}' is not a whole number");
        }
    }

    #[test]
    fn thresholds_parse_the_form_the_brief_asked_for() {
        // The brief's own example: MMLU > 80 && SWE-Verified > 40.
        assert_eq!(
            check(&val("\"> 80\""), &Ty::Threshold),
            Some(Coerced::Threshold { op: Op::Gt, value: 80.0 })
        );
        assert_eq!(
            check(&val("\">=0.8\""), &Ty::Threshold),
            Some(Coerced::Threshold { op: Op::Ge, value: 0.8 })
        );
        assert_eq!(
            check(&val("\"< 200\""), &Ty::Threshold),
            Some(Coerced::Threshold { op: Op::Lt, value: 200.0 })
        );
        assert_eq!(check(&val("80"), &Ty::Threshold), None, "a bare number states no comparison");
    }

    #[test]
    fn threshold_comparison_works_both_ways() {
        assert!(Op::Gt.holds(81.0, 80.0));
        assert!(!Op::Gt.holds(80.0, 80.0));
        assert!(Op::Ge.holds(80.0, 80.0));
        assert!(Op::Le.holds(79.0, 80.0));
    }

    /// A figure that ran off the end of the number line and a WORD spelled
    /// where a figure goes are two different mistakes, and this is the line
    /// between them. The figure is carried up so `Schema::check_ceiling` can
    /// name it at the author's own line; the word is `None`, which is
    /// `schema/wrong-type` — the true sentence for it.
    ///
    /// Mutation: drop the `|| crate::has_a_digit(...)` from `number` and the
    /// same guard from `threshold`. `1e999` then reads as text that is not a
    /// number and the ceiling never sees it. Drop the whole condition instead
    /// and `inf` becomes a size complaint about a word.
    #[test]
    fn a_figure_past_the_end_is_kept_and_a_word_is_not() {
        // Carried up, and infinite, so the ceiling has something to refuse.
        for s in ["1e999", "1e400"] {
            assert_eq!(check(&val(s), &Ty::Number), Some(Coerced::Number(f64::INFINITY)), "{s}");
        }
        assert_eq!(
            check(&val("-1e999"), &Ty::Number),
            Some(Coerced::Number(f64::NEG_INFINITY)),
            "both ends"
        );
        assert_eq!(
            check(&val("\"> 1e999\""), &Ty::Threshold),
            Some(Coerced::Threshold { op: Op::Gt, value: f64::INFINITY }),
            "a comparison is the same figure with an operator in front of it"
        );

        // Words. None of these overflowed anything.
        for s in ["inf", "Infinity", "nan", "-inf", ".inf", ".nan"] {
            assert_eq!(check(&val(s), &Ty::Number), None, "'{s}' is a word, not a size");
        }
        assert_eq!(check(&val("\"> inf\""), &Ty::Threshold), None, "and one type over");

        // And the ordinary numbers are exactly where they were.
        assert_eq!(check(&val("0.7"), &Ty::Number), Some(Coerced::Number(0.7)));
        assert_eq!(check(&val("1e10"), &Ty::Number), Some(Coerced::Number(1e10)));
        assert_eq!(check(&val("42"), &Ty::Number), Some(Coerced::Number(42.0)));
        assert_eq!(check(&val("-3.25"), &Ty::Number), Some(Coerced::Number(-3.25)));
    }

    #[test]
    fn one_of_is_case_insensitive_and_returns_the_canonical_spelling() {
        let ty = Ty::OneOf(vec!["careful".into(), "expert".into()]);
        assert_eq!(check(&val("CAREFUL"), &ty), Some(Coerced::Text("careful".into())));
        assert_eq!(check(&val("sloppy"), &ty), None);
    }
}
