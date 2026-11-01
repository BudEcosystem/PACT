//! **`needs.accept-when:`** (96 §B4): the figures a model has to reach to be
//! used for an agent — `mmlu.score > 50`, `refund-tone.score >= 0.8`,
//! `cost < 0.05 USD` — one comparison per line, all of which have to hold.
//!
//! The Python resolver decides each line (`pact_adapters.selection`); this
//! refuses every line it could not decide, where the author wrote it, and
//! `spec/accept-when.yaml` holds the two readers to one table. What a line may
//! name is closed:
//!
//! * a **benchmark** the catalogue declares under `benchmarks:` — the
//!   distribution's or the workspace's own — by its key or any `also-known-as:`,
//!   with an optional `.score`, on its `scale:` (`percent`: points out of 100,
//!   `%` optional; `fraction`: out of one);
//! * a **metric** of the suite, by its `name:` or the part of its `uri:` after
//!   the colon, with `.score` (its mean, the default) or `.pass-rate`, as a
//!   share (`0.8` or `80%`);
//! * one of six **figures**: `pass-rate` (a share), `cost` (money per case),
//!   `input-price` and `output-price` (money per million tokens),
//!   `context-window` (a size), `first-words-within` (a length of time).
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/not-a-comparison` | the line is not `<name> <op> <figure>` |
//! | `loader/no-such-measure` | the name is none of the above |
//! | `loader/a-part-a-measure-does-not-have` | `.something` the measure has no such part |
//! | `loader/a-comparison-in-the-wrong-unit` | money with no currency or not USD, a share above one, a size or a time that does not read |
//! | `loader/a-suite-figure-with-no-suite` | a metric, `pass-rate` or `cost` line in a workspace whose suite has no cases |
//! | `loader/a-benchmark-held-twice` | the same benchmark under `scores:` and `accept-when:` — two bars that can disagree |
//! | `loader/a-score-for-no-benchmark` | a workspace catalogue row records a score under a name no benchmark has |
//! | `loader/two-metrics-one-name` | two of the suite's metrics would be called by one name |
//! | `loader/a-metric-named-like-a-figure` | a metric is called by a benchmark's or a figure's name |
//! | `loader/a-benchmark-nobody-has-measured` (warning) | no catalogue row records the benchmark a line names, so the line accepts no model yet |

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Node, Value};
use pact_schema::Ty;
use std::collections::{BTreeMap, BTreeSet};

/// The figures every model has, and each one's unit — `selection.BEFORE`
/// and `selection.AFTER`, in one list.
pub const FIGURES: [(&str, &str); 6] = [
    ("input-price", "money"),
    ("output-price", "money"),
    ("context-window", "size"),
    ("first-words-within", "duration"),
    ("pass-rate", "fraction"),
    ("cost", "money"),
];

/// The figures known only once a candidate has run the suite.
const AFTER: [&str; 2] = ["pass-rate", "cost"];

/// One line, read: the measure's own name, what kind it is, which part, the
/// operator and the figure in the measure's own unit.
#[derive(Debug, Clone, PartialEq)]
pub struct Read {
    pub measure: String,
    pub kind: &'static str,
    pub part: String,
    pub op: String,
    pub value: f64,
    pub unit: String,
}

/// Every benchmark name and alias, lower-cased, to `(its key, its scale)`.
pub fn benchmarks(builtin: &str, document: &Node) -> BTreeMap<String, (String, String)> {
    let shipped = pact_doc::parse_yaml(builtin, camino::Utf8Path::new("models/catalog.yaml")).ok();
    let mut out = BTreeMap::new();
    for layer in [shipped.as_ref(), document.get("models")]
        .into_iter()
        .flatten()
        .filter_map(|c| c.get("benchmarks").and_then(Node::as_map))
    {
        for (key, entry) in layer {
            let scale = entry
                .node
                .get("scale")
                .and_then(Node::as_str)
                .map_or("percent", str::trim)
                .to_string();
            let aliases = entry.node.get("also-known-as").map(crate::workflows::list);
            for name in std::iter::once(key.as_str())
                .chain(aliases.into_iter().flatten().filter_map(Node::as_str))
            {
                out.insert(name.trim().to_lowercase(), (key.clone(), scale.clone()));
            }
        }
    }
    out
}

/// What each of the suite's metrics is called: its `name:`, else the part of
/// its `uri:` after the colon, lower-cased — `MetricSpec.name`.
fn metric_names(document: &Node) -> Vec<(String, Span)> {
    let metrics = document.get("evals").and_then(|e| e.get("metrics"));
    metrics
        .and_then(Node::as_list)
        .into_iter()
        .flatten()
        .filter_map(|m| {
            let name = m
                .get("name")
                .and_then(Node::as_str)
                .map(str::to_string)
                .or_else(|| {
                    let uri = m.get("uri").and_then(Node::as_str).or_else(|| m.as_str())?;
                    Some(uri.split_once(':').map_or(uri, |(_, r)| r).to_string())
                })?;
            Some((name.trim().to_lowercase(), m.span.clone()))
        })
        .collect()
}

fn number(text: &str) -> Result<f64, String> {
    text.trim()
        .parse::<f64>()
        .ok()
        .filter(|v| v.is_finite())
        .ok_or_else(|| format!("`{}` is not a figure", text.trim()))
}

fn value(text: &str, unit: &str, at: &Span) -> Result<f64, String> {
    let text = text.trim();
    match unit {
        "percent" => number(text.strip_suffix('%').unwrap_or(text)),
        "fraction" => match text.strip_suffix('%') {
            Some(n) => Ok(number(n)? / 100.0),
            None => {
                let v = number(text)?;
                if v > 1.0 {
                    Err(format!(
                        "a share is out of one, so `{text}` cannot be one: write `{text}%` or `{}`",
                        v / 100.0
                    ))
                } else {
                    Ok(v)
                }
            }
        },
        "money" => {
            let parts: Vec<&str> = text.split_whitespace().collect();
            let [amount, currency] = parts.as_slice() else {
                return Err(format!(
                    "`{text}` is an amount with no currency: write it like `0.05 USD`"
                ));
            };
            if !currency.eq_ignore_ascii_case("USD") {
                return Err(format!(
                    "the catalogue prices every model in USD, so `{text}` cannot be compared with \
                     one: write it in USD"
                ));
            }
            number(amount)
        }
        "size" | "duration" => {
            let ty = if unit == "size" {
                Ty::Size
            } else {
                Ty::Duration
            };
            let node = Node::new(Value::Str(text.to_string()), at.clone());
            if pact_schema::coerce::check(&node, &ty).is_none() {
                return Err(if unit == "size" {
                    format!("`{text}` is not a size: write it like `32k` or `128000`")
                } else {
                    format!("`{text}` is not a length of time: write it like `500ms` or `2s`")
                });
            }
            Ok(0.0)
        }
        _ => Err(format!("no unit called {unit:?}")),
    }
}

/// One line read, or `(the rule, why)` it is not one. The same reading as
/// `selection.parse`; `spec/accept-when.yaml` holds the two to one table.
pub fn read(
    written: &str,
    benchmarks: &BTreeMap<String, (String, String)>,
    metrics: &BTreeSet<String>,
    at: &Span,
) -> Result<Read, (&'static str, String)> {
    const OPS: [&str; 6] = [">=", "<=", "==", ">", "<", "="];
    let not_one = || {
        (
            "loader/not-a-comparison",
            format!(
                "`{written}` is not a comparison: write a name, then `>`, `>=`, `<`, `<=` or `=`, \
                 then a figure — `mmlu.score > 50`"
            ),
        )
    };
    let at_op = written
        .char_indices()
        .find(|(_, c)| matches!(c, '>' | '<' | '='))
        .map(|(i, _)| i)
        .ok_or_else(not_one)?;
    let (name, rest) = written.split_at(at_op);
    let op = OPS
        .iter()
        .find(|o| rest.starts_with(**o))
        .ok_or_else(not_one)?;
    let figure = rest[op.len()..].trim();
    let name = name.trim();
    if name.is_empty() || figure.is_empty() {
        return Err(not_one());
    }
    let unit_error = |why: String| ("loader/a-comparison-in-the-wrong-unit", why);
    let whole = name.to_lowercase();
    let (head, part) = whole.split_once('.').unwrap_or((whole.as_str(), ""));
    if let Some((_, unit)) = FIGURES.iter().find(|(f, _)| *f == head) {
        if !part.is_empty() {
            return Err((
                "loader/a-part-a-measure-does-not-have",
                format!("`{head}` is one figure and has no `.{part}`"),
            ));
        }
        return Ok(Read {
            measure: head.to_string(),
            kind: "figure",
            part: String::new(),
            op: op.to_string(),
            value: value(figure, unit, at).map_err(unit_error)?,
            unit: unit.to_string(),
        });
    }
    if let Some((key, scale)) = benchmarks.get(&whole).or_else(|| benchmarks.get(head)) {
        let part = if benchmarks.contains_key(&whole) {
            ""
        } else {
            part
        };
        if !matches!(part, "" | "score") {
            return Err((
                "loader/a-part-a-measure-does-not-have",
                format!("a benchmark has a `.score` and nothing else, so not `.{part}`"),
            ));
        }
        return Ok(Read {
            measure: key.clone(),
            kind: "benchmark",
            part: "score".into(),
            op: op.to_string(),
            value: value(figure, scale, at).map_err(unit_error)?,
            unit: scale.clone(),
        });
    }
    if metrics.contains(head) {
        let part = if part.is_empty() { "score" } else { part };
        if !matches!(part, "score" | "pass-rate") {
            return Err((
                "loader/a-part-a-measure-does-not-have",
                format!("a metric has a `.score` (its mean) and a `.pass-rate`, so not `.{part}`"),
            ));
        }
        return Ok(Read {
            measure: head.to_string(),
            kind: "metric",
            part: part.to_string(),
            op: op.to_string(),
            value: value(figure, "fraction", at).map_err(unit_error)?,
            unit: "fraction".into(),
        });
    }
    let mut figures: Vec<&str> = FIGURES.iter().map(|(f, _)| *f).collect();
    figures.sort_unstable();
    Err((
        "loader/no-such-measure",
        format!(
            "nothing is called `{head}`: name a benchmark the catalogue declares, a metric of \
             your suite by its `name:`, or one of {}",
            figures.join(", ")
        ),
    ))
}

pub fn check(document: &Node, builtin: &str, diags: &mut Diagnostics) {
    let benchmarks = benchmarks(builtin, document);
    let named = metric_names(document);
    let mut metrics = BTreeSet::new();
    for (name, span) in &named {
        if !metrics.insert(name.clone()) {
            diags.push(Diagnostic::error(
                "loader/two-metrics-one-name",
                span.clone(),
                format!(
                    "Two of the suite's metrics are called '{name}', so an `accept-when:` line \
                     naming it could mean either."
                ),
                "Give each its own `name:`.",
            ));
        }
        if benchmarks.contains_key(name) || FIGURES.iter().any(|(f, _)| f == name) {
            diags.push(Diagnostic::error(
                "loader/a-metric-named-like-a-figure",
                span.clone(),
                format!(
                    "A metric of the suite is called '{name}', which is already the name of a \
                     benchmark or a figure every model has."
                ),
                "Give it a `name:` of its own.",
            ));
        }
    }
    let recorded = recorded(builtin, document, &benchmarks, diags);
    let has_cases = document
        .get("evals")
        .and_then(|e| e.get("cases"))
        .and_then(Node::as_map)
        .is_some_and(|m| !m.is_empty());
    for (agent, entry) in document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let Some(needs) = entry.node.get("needs") else {
            continue;
        };
        let scores: BTreeSet<String> = needs
            .get("scores")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
            .filter_map(|(k, _)| {
                benchmarks
                    .get(&k.trim().to_lowercase())
                    .map(|b| b.0.clone())
            })
            .collect();
        for line in needs
            .get("accept-when")
            .map(crate::workflows::list)
            .into_iter()
            .flatten()
        {
            let Some(written) = line.as_str() else {
                continue;
            };
            let read = match read(written, &benchmarks, &metrics, &line.span) {
                Ok(r) => r,
                Err((rule, why)) => {
                    diags.push(Diagnostic::error(
                        rule,
                        line.span.clone(),
                        format!("`{agent}` accepts a model when {why}."),
                        "Write one comparison per line — `mmlu.score > 50`, `refund-tone.score >= \
                         0.8`, `pass-rate >= 90%`, `cost < 0.05 USD`.",
                    ));
                    continue;
                }
            };
            let after = read.kind == "metric" || AFTER.contains(&read.measure.as_str());
            if after && !has_cases {
                diags.push(Diagnostic::error(
                    "loader/a-suite-figure-with-no-suite",
                    line.span.clone(),
                    format!(
                        "`{agent}` accepts a model when `{written}`, and that figure is what a \
                         model scores or spends on the suite — which has no cases to run."
                    ),
                    "Write cases under `evals:`, or name a figure the catalogue records instead.",
                ));
            }
            if read.kind == "benchmark" && scores.contains(&read.measure) {
                diags.push(Diagnostic::error(
                    "loader/a-benchmark-held-twice",
                    line.span.clone(),
                    format!(
                        "`{agent}` holds {} under `scores:` and again under `accept-when:` — two \
                         bars on one benchmark, which can disagree.",
                        read.measure
                    ),
                    "Keep one of them; `accept-when:` is the one that can name everything else too.",
                ));
            }
            if read.kind == "benchmark" && !recorded.contains(&read.measure) {
                diags.push(Diagnostic::warning(
                    "loader/a-benchmark-nobody-has-measured",
                    line.span.clone(),
                    format!(
                        "`{agent}` accepts a model when `{written}`, and no model in the \
                         catalogue has a {} score yet — so for now this line accepts none.",
                        read.measure
                    ),
                    format!(
                        "Record a figure for the models you would use, with where it came from \
                         (Bud Agent Flow: `budflow benchmark record --benchmark {}`), or take \
                         the line out.",
                        read.measure
                    ),
                ));
            }
        }
    }
}

/// Every benchmark some row of either catalogue has a score for, by its key —
/// refusing a workspace row's score under a name no benchmark has.
fn recorded(
    builtin: &str,
    document: &Node,
    benchmarks: &BTreeMap<String, (String, String)>,
    diags: &mut Diagnostics,
) -> BTreeSet<String> {
    let shipped = pact_doc::parse_yaml(builtin, camino::Utf8Path::new("models/catalog.yaml")).ok();
    let mut out = BTreeSet::new();
    for (own, layer) in [(false, shipped.as_ref()), (true, document.get("models"))] {
        let Some(rows) = layer.and_then(|c| c.get("models")).and_then(Node::as_map) else {
            continue;
        };
        for (model, row) in rows {
            for (name, figure) in row
                .node
                .get("benchmarks")
                .and_then(Node::as_map)
                .into_iter()
                .flatten()
            {
                match benchmarks.get(&name.trim().to_lowercase()) {
                    Some((key, _)) => {
                        out.insert(key.clone());
                    }
                    None if own => diags.push(Diagnostic::error(
                        "loader/a-score-for-no-benchmark",
                        figure.key_span.clone(),
                        format!(
                            "'{model}' records a score for '{name}', and no benchmark is called \
                             that — so nothing could ever compare with it."
                        ),
                        format!(
                            "Use the name the catalogue gives it (`mmlu`, `terminal-bench`, …), \
                             or declare '{name}' under `benchmarks:` in models/catalog.yaml."
                        ),
                    )),
                    None => {}
                }
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const VECTORS: &str = include_str!("../../../spec/accept-when.yaml");

    /// Every row of `spec/accept-when.yaml`, read the way the Python resolver
    /// is held to read it (`tests/test_an_accept_line_means_one_thing.py`).
    #[test]
    fn every_line_in_the_shared_table_is_read_as_it_says() {
        let table =
            pact_doc::parse_yaml(VECTORS, camino::Utf8Path::new("accept-when.yaml")).unwrap();
        let mut benchmarks = BTreeMap::new();
        for (name, scale) in table.get("benchmarks").and_then(Node::as_map).unwrap() {
            benchmarks.insert(
                name.clone(),
                (name.clone(), scale.node.as_str().unwrap().to_string()),
            );
        }
        let metrics: BTreeSet<String> = crate::workflows::list(table.get("metrics").unwrap())
            .into_iter()
            .filter_map(Node::as_str)
            .map(str::to_string)
            .collect();
        let at = Span::new("t", 1, 1, 0, 0);
        for row in table.get("lines").and_then(Node::as_list).unwrap() {
            let written = row.get("written").and_then(Node::as_str).unwrap();
            let got = read(written, &benchmarks, &metrics, &at).expect(written);
            let want = |k: &str| row.get(k).and_then(Node::as_str).unwrap_or("").to_string();
            assert_eq!(
                [
                    got.measure.clone(),
                    got.kind.to_string(),
                    got.part.clone(),
                    got.op.clone(),
                    got.unit.clone()
                ],
                [
                    want("measure"),
                    want("kind"),
                    want("part"),
                    want("op"),
                    want("unit")
                ],
                "{written}"
            );
            if !matches!(got.unit.as_str(), "size" | "duration") {
                let v: f64 = want("value").parse().unwrap();
                assert!(
                    (got.value - v).abs() < 1e-9,
                    "{written}: {} != {v}",
                    got.value
                );
            }
        }
        for row in table.get("not-lines").and_then(Node::as_list).unwrap() {
            let written = row.get("written").and_then(Node::as_str).unwrap();
            let rule = row.get("rule").and_then(Node::as_str).unwrap();
            assert_eq!(
                read(written, &benchmarks, &metrics, &at).unwrap_err().0,
                rule,
                "{written}"
            );
        }
    }
}
