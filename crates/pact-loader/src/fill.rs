//! **Filling an agent's words for one run** (02P §3.2 A1, 96 §C): the
//! renderer every runtime calls, so the words a model reads are the same in
//! Rust, Python and TypeScript.
//!
//! [`fill`] takes one authored text, the workspace's `template-language:` and
//! the two sets of values a run starts with (`run-inputs` and `remembers`),
//! and returns the words. It is the reference `pact_adapters.holes.fill`
//! matches step for step, and the one `pact fill` and the WebAssembly build
//! (`crates/pact-fill-wasm`) expose; `tests/conformance/fill.json` holds all
//! three to the same answers.
//!
//! # `holes` (the default)
//!
//! Each `{{run-inputs.<name>}}` and `{{remembers.<name>}}` is replaced by its
//! value: text as written, any other value as JSON ([`json_text`]: `, ` and
//! `: ` between items, non-ASCII kept, a number as ECMAScript writes it), so a
//! list of examples reads as a list. An escaped `\{{` is sent as `{{`. Any
//! other pair of braces is the author's own text and is left alone. A hole
//! whose value is absent or `null` is [`FillError::Unfilled`]: a model never
//! reads the braces.
//!
//! # `jinja`
//!
//! The text is a template over `run_inputs` and `remembers`, each name written
//! with `_` for `-` ([`crate::jinja::template_name`]). The environment has no
//! globals, only the filters and tests both ports ship with one meaning
//! ([`crate::jinja::FILTERS`], [`crate::jinja::TESTS`]), strict undefined
//! values, no autoescape and the trailing newline kept. What `{{ … }}` prints
//! follows the `holes` rule: text as written, anything else as JSON, so `true`,
//! `null`, `5` and a list print the same in every port (Jinja2 alone would print
//! `True`, `None`, `5.0` and a Python list). A value is data: what is inserted is
//! never rendered again, so `{{ 7*7 }}` typed into a run input stays those
//! characters.

use crate::holes::{Brace, REMEMBERS, RUN_INPUTS, braces};
use crate::jinja::{FILTERS, TESTS, template_name};
use minijinja::value::Value as JinjaValue;
use minijinja::{AutoEscape, Environment, Error, ErrorKind, UndefinedBehavior};
use serde_json::{Map, Value};

/// Which language an agent's words are written in: the workspace's `template-language:`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Language {
    /// `{{run-inputs.<name>}}` and `{{remembers.<name>}}`, and nothing else.
    Holes,
    /// A template in the shared Jinja dialect.
    Jinja,
}

impl Language {
    /// The language `template-language:` names: `jinja`, or `holes` for anything else, as the
    /// checker reads it (an unknown word is refused there, before any run).
    pub fn written(word: Option<&str>) -> Language {
        if word == Some("jinja") {
            Language::Jinja
        } else {
            Language::Holes
        }
    }
}

/// Why a text could not be filled.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FillError {
    /// A name the run has no value for. `namespace` is `run-inputs` or `remembers`; under
    /// `jinja`, `name` is written as the template writes it (`brand_voice`), and is the engine's
    /// own account when the missing value is not one of the run's names.
    Unfilled { namespace: String, name: String },
    /// The template cannot be rendered: a dialect `pact check` refuses, or a value of the wrong
    /// kind for what the template does with it.
    NotRendered(String),
}

impl std::fmt::Display for FillError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            FillError::Unfilled { namespace, name } => {
                let from = if namespace == RUN_INPUTS {
                    "run_inputs"
                } else {
                    "what the agent remembers"
                };
                write!(
                    f,
                    "{{{{{namespace}.{name}}}}} has no value for this run; pass '{name}' in {from}"
                )
            }
            FillError::NotRendered(why) => write!(f, "this template cannot be rendered: {why}"),
        }
    }
}

impl std::error::Error for FillError {}

/// `text` filled from one run's values, in `language`.
///
/// `run_inputs` and `remembers` are keyed by the names the agent declares (`brand-voice`, not
/// `brand_voice`).
pub fn fill(
    text: &str,
    language: Language,
    run_inputs: &Map<String, Value>,
    remembers: &Map<String, Value>,
) -> Result<String, FillError> {
    match language {
        Language::Holes => fill_holes(text, run_inputs, remembers),
        Language::Jinja => render_jinja(text, run_inputs, remembers),
    }
}

fn fill_holes(
    text: &str,
    run_inputs: &Map<String, Value>,
    remembers: &Map<String, Value>,
) -> Result<String, FillError> {
    let mut out = String::with_capacity(text.len());
    let mut at = 0usize;
    for brace in braces(text) {
        match brace {
            Brace::Escaped { at: start, end } => {
                out.push_str(&text[at..start]);
                out.push_str("{{");
                at = end;
            }
            Brace::Name {
                at: start,
                end,
                name,
            } => {
                let (namespace, rest) = name.split_once('.').unwrap_or((name.as_str(), ""));
                let values = match namespace {
                    RUN_INPUTS => run_inputs,
                    REMEMBERS => remembers,
                    // A name in neither namespace is the author's own braces: text.
                    _ => continue,
                };
                out.push_str(&text[at..start]);
                match values.get(rest) {
                    None | Some(Value::Null) => {
                        return Err(FillError::Unfilled {
                            namespace: namespace.to_string(),
                            name: rest.to_string(),
                        });
                    }
                    Some(Value::String(said)) => out.push_str(said),
                    Some(other) => out.push_str(&json_text(other)),
                }
                at = end;
            }
            Brace::Other { .. } => {}
        }
    }
    out.push_str(&text[at..]);
    Ok(out)
}

/// The environment of the shared dialect: nothing but the shared filters and tests.
fn environment() -> Environment<'static> {
    use minijinja::{filters, tests};
    let mut env = Environment::empty();
    env.set_undefined_behavior(UndefinedBehavior::Strict);
    env.set_keep_trailing_newline(true);
    env.set_auto_escape_callback(|_| AutoEscape::None);
    env.set_formatter(|out, _state, value| {
        if value.is_undefined() {
            return Err(Error::from(ErrorKind::UndefinedError));
        }
        let said = match value.as_str() {
            Some(text) => text.to_string(),
            None => json_text(
                &serde_json::to_value(value)
                    .map_err(|e| Error::new(ErrorKind::BadSerialization, e.to_string()))?,
            ),
        };
        out.write_str(&said)
            .map_err(|e| Error::new(ErrorKind::WriteFailure, e.to_string()))
    });
    for name in FILTERS {
        match *name {
            "abs" => env.add_filter("abs", filters::abs),
            "capitalize" => env.add_filter("capitalize", filters::capitalize),
            "count" | "length" => env.add_filter(*name, filters::length),
            "d" | "default" => env.add_filter(*name, filters::default),
            "first" => env.add_filter("first", filters::first),
            "float" => env.add_filter("float", filters::float),
            "indent" => env.add_filter("indent", filters::indent),
            "int" => env.add_filter("int", filters::int),
            "items" => env.add_filter("items", filters::items),
            "join" => env.add_filter("join", filters::join),
            "last" => env.add_filter("last", filters::last),
            "list" => env.add_filter("list", filters::list),
            "lower" => env.add_filter("lower", filters::lower),
            "max" => env.add_filter("max", filters::max),
            "min" => env.add_filter("min", filters::min),
            "replace" => env.add_filter("replace", filters::replace),
            "reverse" => env.add_filter("reverse", filters::reverse),
            "round" => env.add_filter("round", filters::round),
            "sort" => env.add_filter("sort", filters::sort),
            "string" => env.add_filter("string", filters::string),
            "sum" => env.add_filter("sum", filters::sum),
            "title" => env.add_filter("title", filters::title),
            "trim" => env.add_filter("trim", filters::trim),
            "unique" => env.add_filter("unique", filters::unique),
            "upper" => env.add_filter("upper", filters::upper),
            other => unreachable!("FILTERS names `{other}`, which `environment` does not register"),
        }
    }
    for name in TESTS {
        match *name {
            "defined" => env.add_test("defined", tests::is_defined),
            "undefined" => env.add_test("undefined", tests::is_undefined),
            "none" => env.add_test("none", tests::is_none),
            "number" => env.add_test("number", tests::is_number),
            "string" => env.add_test("string", tests::is_string),
            "sequence" => env.add_test("sequence", tests::is_sequence),
            "mapping" => env.add_test("mapping", tests::is_mapping),
            "even" => env.add_test("even", tests::is_even),
            "odd" => env.add_test("odd", tests::is_odd),
            other => unreachable!("TESTS names `{other}`, which `environment` does not register"),
        }
    }
    env
}

fn render_jinja(
    text: &str,
    run_inputs: &Map<String, Value>,
    remembers: &Map<String, Value>,
) -> Result<String, FillError> {
    let named = |values: &Map<String, Value>| -> Map<String, Value> {
        values
            .iter()
            .map(|(k, v)| (template_name(k), v.clone()))
            .collect()
    };
    let (inputs, facts) = (named(run_inputs), named(remembers));
    let env = environment();
    let template = env
        .template_from_str(text)
        .map_err(|e| FillError::NotRendered(e.to_string()))?;
    let context = JinjaValue::from_serialize(serde_json::json!({
        "run_inputs": inputs,
        "remembers": facts,
    }));
    template.render(context).map_err(|e| match e.kind() {
        ErrorKind::UndefinedError => {
            // The engine does not say which name it missed: the first one the text reads that
            // the run did not give is the one to ask for.
            let mut read: Vec<String> = template.undeclared_variables(true).into_iter().collect();
            read.sort_by_key(|name| (text.find(name.as_str()).unwrap_or(usize::MAX), name.clone()));
            read.iter()
                .filter_map(|name| {
                    let (root, rest) = name.split_once('.')?;
                    let first = rest.split('.').next().unwrap_or(rest);
                    let (namespace, given) = match root {
                        "run_inputs" => (RUN_INPUTS, &inputs),
                        "remembers" => (REMEMBERS, &facts),
                        _ => return None,
                    };
                    (!given.contains_key(first)).then(|| FillError::Unfilled {
                        namespace: namespace.to_string(),
                        name: first.to_string(),
                    })
                })
                .next()
                .unwrap_or_else(|| FillError::Unfilled {
                    namespace: RUN_INPUTS.to_string(),
                    name: e.to_string(),
                })
        }
        _ => FillError::NotRendered(e.to_string()),
    })
}

/// `value` as JSON the way every port writes it into words: `, ` between items, `: ` after a
/// key (as Python's `json.dumps` does), non-ASCII kept, and a number as ECMAScript's
/// `Number.prototype.toString` writes it ([`number_text`]). A runtime in TypeScript holds no
/// `2.0` apart from `2`, so the shared rule is the one it can keep.
pub fn json_text(value: &Value) -> String {
    let mut out = String::new();
    write_json(value, &mut out);
    out
}

fn write_json(value: &Value, out: &mut String) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(yes) => out.push_str(if *yes { "true" } else { "false" }),
        Value::Number(n) => match (n.as_i64(), n.as_u64(), n.as_f64()) {
            (Some(i), _, _) => out.push_str(&i.to_string()),
            (None, Some(u), _) => out.push_str(&u.to_string()),
            (None, None, Some(f)) => out.push_str(&number_text(f)),
            (None, None, None) => out.push_str(&n.to_string()),
        },
        // serde_json escapes the same characters `json.dumps` does once ASCII is not forced:
        // the quote, the backslash and the control characters.
        Value::String(text) => out.push_str(&Value::String(text.clone()).to_string()),
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                write_json(item, out);
            }
            out.push(']');
        }
        Value::Object(entries) => {
            out.push('{');
            for (i, (key, item)) in entries.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                out.push_str(&Value::String(key.clone()).to_string());
                out.push_str(": ");
                write_json(item, out);
            }
            out.push('}');
        }
    }
}

/// A finite number as ECMAScript's `Number::toString` writes it (ECMA-262 §6.1.6.1.20): the
/// shortest digits that read back the same; positional from 1e-6 up to (not including) 1e21,
/// with no fraction when there is none (`2`, not `2.0`); otherwise `<d>[.<digits>]e<sign><exp>`.
/// Zero is `0`, whatever its sign.
pub fn number_text(f: f64) -> String {
    if f == 0.0 {
        return "0".to_string();
    }
    // `{:e}` gives the shortest round-trip digits: `1.5e-5`, `1e16`, `-2.5e0`.
    let shortest = format!("{f:e}");
    let (mantissa, exponent) = shortest.split_once('e').unwrap_or((shortest.as_str(), "0"));
    // ECMAScript's `n`: 10^(n-1) <= |f| < 10^n.
    let n: i32 = exponent.parse::<i32>().unwrap_or(0) + 1;
    let sign = if mantissa.starts_with('-') { "-" } else { "" };
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let k = i32::try_from(digits.len()).unwrap_or(i32::MAX);
    let zeros = |count: i32| "0".repeat(usize::try_from(count).unwrap_or(0));
    let at = |count: i32| usize::try_from(count).unwrap_or(0);
    if k <= n && n <= 21 {
        format!("{sign}{digits}{}", zeros(n - k))
    } else if 0 < n && n <= 21 {
        format!("{sign}{}.{}", &digits[..at(n)], &digits[at(n)..])
    } else if -6 < n && n <= 0 {
        format!("{sign}0.{}{digits}", zeros(-n))
    } else {
        let exponent = n - 1;
        let exponent_sign = if exponent < 0 { '-' } else { '+' };
        let mantissa = if k > 1 {
            format!("{}.{}", &digits[..1], &digits[1..])
        } else {
            digits
        };
        format!("{sign}{mantissa}e{exponent_sign}{}", exponent.abs())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_number_is_written_as_ecmascript_writes_it() {
        for (value, written) in [
            (0.1, "0.1"),
            (2.0, "2"),
            (-2.5, "-2.5"),
            (1e16, "10000000000000000"),
            (1.5e-5, "0.000015"),
            (1.5e-7, "1.5e-7"),
            (0.000001, "0.000001"),
            (123456789.125, "123456789.125"),
            (1e21, "1e+21"),
            (1.5e22, "1.5e+22"),
            (-0.0, "0"),
            (0.30000000000000004, "0.30000000000000004"),
            (1.2345e-300, "1.2345e-300"),
        ] {
            assert_eq!(number_text(value), written, "{value}");
        }
    }

    #[test]
    fn the_environment_holds_the_shared_dialect_and_nothing_else() {
        // `environment` reaches `unreachable!` for a shared name it does not register.
        let none = Map::new();
        let said = |text: &str| fill(text, Language::Jinja, &none, &none);
        assert_eq!(
            said("{{ run_inputs.tier }} {% for n in remembers.caller_notes %}{% endfor %}"),
            Err(FillError::Unfilled {
                namespace: RUN_INPUTS.into(),
                name: "tier".into()
            })
        );
        let tier = Map::from_iter([("tier".to_string(), Value::from("gold"))]);
        assert_eq!(
            fill(
                "{{ run_inputs.tier }}{{ remembers.caller_notes }}",
                Language::Jinja,
                &tier,
                &none
            ),
            Err(FillError::Unfilled {
                namespace: REMEMBERS.into(),
                name: "caller_notes".into()
            })
        );
        assert_eq!(
            said("{{ [3, 1] | sort | first }} {{ 4 is even }}"),
            Ok("1 true".to_string())
        );
        for outside in [
            "{{ 'x' | tojson }}",
            "{{ range(3) }}",
            "{{ 1 is divisibleby(1) }}",
        ] {
            assert!(
                matches!(said(outside), Err(FillError::NotRendered(_))),
                "{outside}"
            );
        }
    }
}
