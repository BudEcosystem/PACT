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
    Money {
        amount: f64,
        currency: String,
    },
    /// A fraction in `0.0..=1.0`. `90%` becomes `0.9`.
    Percent(f64),
    Threshold {
        op: Op,
        value: f64,
    },
    /// A count of tokens: `32k` becomes 32000.
    Size(u64),
}

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
            Op::Eq => (lhs - rhs).abs() < f64::EPSILON,
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
            Value::Str(s) => s.trim().parse::<i64>().ok().map(Coerced::Integer),
            _ => None,
        },
        Ty::Duration => node.as_str().and_then(duration).map(Coerced::Duration),
        Ty::Money => node.as_str().and_then(money),
        Ty::Percent => percent(node).map(Coerced::Percent),
        Ty::Threshold => node.as_str().and_then(threshold),
        Ty::Size => size(node).map(Coerced::Size),
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

fn number(node: &Node) -> Option<f64> {
    match &node.value {
        Value::Int(i) => Some(*i as f64),
        Value::Float(f) => Some(*f),
        Value::Str(s) => s.trim().parse::<f64>().ok(),
        _ => None,
    }
}

/// `2s`, `500ms`, `1m30s`, `1m 30s`, `2 minutes`, `30S`, `1d`. Returns
/// milliseconds.
///
/// A number and a unit: `ms`, `s`, `m`, `h`, `d` or any of their long names,
/// case-insensitive, the space optional, several parts running together, and a
/// bare number read as seconds. Every one of those is a spelling somebody
/// reaches for, and the same set is accepted on the other side by
/// `pact_adapters.limits.seconds` — an author who writes `1m30s` and gets 1.0
/// back would have a ceiling ninety times tighter than the one they wrote.
///
/// What this deliberately does NOT decide is whether the length of time is a
/// USABLE one. `0s` parses here — it is a well-formed length of time — and is
/// refused one layer up by `Schema::check_floor`, where the field's name and
/// line are known and the message can name them. Refusing it here would report
/// `0s` as "not a length of time", which is both false and unfixable.
fn duration(s: &str) -> Option<u64> {
    let s = s.trim().to_ascii_lowercase();
    if s.is_empty() {
        return None;
    }
    let mut total: u64 = 0;
    let mut num = String::new();
    let mut unit = String::new();
    let mut any = false;

    let flush = |num: &mut String, unit: &mut String, total: &mut u64, any: &mut bool| -> bool {
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
        *total += (v * mult) as u64;
        *any = true;
        num.clear();
        unit.clear();
        true
    };

    for c in s.chars() {
        if c.is_ascii_digit() || c == '.' {
            if !unit.is_empty() && !flush(&mut num, &mut unit, &mut total, &mut any) {
                return None;
            }
            num.push(c);
        } else if c.is_ascii_alphabetic() {
            unit.push(c);
        } else if c.is_whitespace() {
            // `2 minutes` — a space between number and unit is fine.
        } else {
            return None;
        }
    }
    if !flush(&mut num, &mut unit, &mut total, &mut any) {
        return None;
    }
    any.then_some(total)
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
fn percent(node: &Node) -> Option<f64> {
    match &node.value {
        Value::Str(s) => {
            let t = s.trim();
            match t.strip_suffix('%') {
                Some(n) => n
                    .trim()
                    .parse::<f64>()
                    .ok()
                    .map(|v| v / 100.0)
                    .filter(|v| (0.0..=1.0).contains(v)),
                None => t.parse::<f64>().ok().filter(|v| (0.0..=1.0).contains(v)),
            }
        }
        Value::Float(f) if (0.0..=1.0).contains(f) => Some(*f),
        Value::Int(0) => Some(0.0),
        Value::Int(1) => Some(1.0),
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
fn size(node: &Node) -> Option<u64> {
    let text = match &node.value {
        Value::Int(i) if *i >= 0 => return Some(*i as u64),
        Value::Str(s) => s.trim().to_ascii_lowercase(),
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
    if v < 0.0 {
        return None;
    }
    Some((v * mult) as u64)
}

/// `> 80`, `>=0.8`, `< 200`. The syntax an author writes for a bar to clear.
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
        for s in ["quite a lot really", "-5k", "k", ""] {
            assert_eq!(check(&val(&format!("\"{s}\"")), &Ty::Size), None, "'{s}' is not a size");
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

    #[test]
    fn one_of_is_case_insensitive_and_returns_the_canonical_spelling() {
        let ty = Ty::OneOf(vec!["careful".into(), "expert".into()]);
        assert_eq!(check(&val("CAREFUL"), &ty), Some(Coerced::Text("careful".into())));
        assert_eq!(check(&val("sloppy"), &ty), None);
    }
}
