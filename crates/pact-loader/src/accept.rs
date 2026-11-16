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
//! | `loader/an-interval-out-of-order` | a workspace figure's `provenance.interval` has its `low` above its `high` |
//! | `loader/a-confidence-level-that-is-not-a-share` | an interval's `level` is not between zero and one (`95` for `0.95`) |
//! | `loader/more-cases-than-the-benchmark-has` | a figure's `sample-size` is above its `population` |
//! | `loader/an-interval-off-the-benchmark-scale` | a bound is below zero or above the top of the benchmark's `scale:` (100 for `percent`, 1 for `fraction`) |
//! | `loader/a-measurement-on-a-figure-nothing-samples` | `sample-size`, `population` or `interval` on a `reasoning:`, `context-window` or `first-words-within` figure |
//! | `loader/a-subset-figure-with-no-interval` (warning) | a figure taken on fewer cases than the benchmark has records no interval, so a line reads it as if it were the whole benchmark's |
//!
//! A benchmark figure's measurement (`provenance.sample-size`, `population`,
//! `interval`) changes what a line decides: `>`/`>=` hold only when `value:`
//! and `interval.low` hold, `<`/`<=` only when `value:` and `interval.high`
//! hold. The resolver drops a figure whose measurement is refused here, so a
//! line on it accepts no model.

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

/// The provenance fields that say how a figure was measured.
const MEASURED: [&str; 3] = ["sample-size", "population", "interval"];

/// The highest a figure can be on a benchmark `scale:`; the lowest is zero.
fn scale_top(scale: &str) -> Option<f64> {
    match scale {
        "percent" => Some(100.0),
        "fraction" => Some(1.0),
        _ => None,
    }
}

/// A number as YAML wrote it.
fn number_in(node: &Node) -> Option<f64> {
    match node.value {
        Value::Int(i) => Some(i as f64),
        Value::Float(f) => Some(f),
        _ => None,
    }
}

/// Refuse a measurement the resolver could not read on a workspace row's
/// benchmark figure (`selection.measurement_of`), where the author wrote it.
fn measurement(model: &str, name: &str, scale: &str, figure: &Node, diags: &mut Diagnostics) {
    let Some(provenance) = figure.get("provenance") else {
        return;
    };
    let count = |key: &str| match provenance.get(key).map(|n| &n.value) {
        Some(Value::Int(i)) => Some(*i),
        _ => None,
    };
    let (sample, population) = (count("sample-size"), count("population"));
    if let (Some(sample), Some(population)) = (sample, population)
        && sample > population
    {
        diags.push(Diagnostic::error(
            "loader/more-cases-than-the-benchmark-has",
            provenance
                .get("sample-size")
                .map_or(figure.span.clone(), |n| n.span.clone()),
            format!(
                "'{model}' says its {name} figure was taken on {sample} cases, and the \
                     benchmark has {population}."
            ),
            "Write the number of cases the figure was measured on as `sample-size:`, and the \
                 number the whole benchmark has as `population:`.",
        ));
    }
    let Some(interval) = provenance.get("interval") else {
        if let (Some(sample), Some(population)) = (sample, population)
            && sample < population
        {
            diags.push(Diagnostic::warning(
                "loader/a-subset-figure-with-no-interval",
                provenance
                    .get("sample-size")
                    .map_or(figure.span.clone(), |n| n.span.clone()),
                format!(
                    "'{model}' took its {name} figure on {sample} of {population} cases and \
                         records no interval, so a line reads it as if it were the whole \
                         benchmark's score."
                ),
                "Add `interval: {low, high, level}` from the measurement, so a line is held \
                     to how far the figure could be off.",
            ));
        }
        return;
    };
    let bound = |key: &str| interval.get(key).and_then(number_in);
    if let (Some(low), Some(high)) = (bound("low"), bound("high")) {
        if low > high {
            diags.push(Diagnostic::error(
                "loader/an-interval-out-of-order",
                interval.span.clone(),
                format!(
                    "'{model}' gives its {name} figure an interval from {low} to {high}, and the \
                     low end is above the high end."
                ),
                "Swap `low:` and `high:`.",
            ));
        }
        if let Some(top) = scale_top(scale)
            && (low < 0.0 || high > top)
        {
            diags.push(Diagnostic::error(
                "loader/an-interval-off-the-benchmark-scale",
                interval.span.clone(),
                format!(
                    "'{model}' gives its {name} figure an interval from {low} to {high}, and \
                         {name} is scored on the {scale} scale, from 0 to {top}."
                ),
                format!("Write both bounds on the benchmark's own scale, from 0 to {top}."),
            ));
        }
    }
    if let Some(level) = bound("level")
        && !(level > 0.0 && level < 1.0)
    {
        diags.push(Diagnostic::error(
            "loader/a-confidence-level-that-is-not-a-share",
            interval
                .get("level")
                .map_or(interval.span.clone(), |n| n.span.clone()),
            format!(
                "'{model}' gives its {name} interval a confidence level of {level}, and a \
                     level is a share between zero and one."
            ),
            "Write it as a share, like `0.95` for 95%.",
        ));
    }
}

/// Refuse a measurement on a workspace row's figure that is not a benchmark
/// score: a reasoning rung, a context window and a speed are not sampled.
fn unsampled(model: &str, row: &Node, diags: &mut Diagnostics) {
    let capabilities = row.get("capabilities");
    let speed = row.get("speed");
    for (field, figure) in [
        ("reasoning", row.get("reasoning")),
        (
            "context-window",
            capabilities.and_then(|c| c.get("context-window")),
        ),
        (
            "first-words-within",
            speed.and_then(|s| s.get("first-words-within")),
        ),
    ] {
        let Some(provenance) = figure
            .and_then(|f| f.get("provenance"))
            .and_then(Node::as_map)
        else {
            continue;
        };
        for (key, entry) in provenance {
            if MEASURED.contains(&key.as_str()) {
                diags.push(Diagnostic::error(
                    "loader/a-measurement-on-a-figure-nothing-samples",
                    entry.key_span.clone(),
                    format!(
                        "'{model}' says how its {field} was sampled (`{key}:`), and {field} is \
                         not taken on a sample of a benchmark's cases."
                    ),
                    format!(
                        "Take `{key}:` out; it belongs on a benchmark figure under `benchmarks:`."
                    ),
                ));
            }
        }
    }
}

/// Every benchmark some row of either catalogue has a score for, by its key —
/// refusing a workspace row's score under a name no benchmark has, and a
/// workspace figure's measurement the resolver could not read.
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
            if own {
                unsampled(model, &row.node, diags);
            }
            for (name, figure) in row
                .node
                .get("benchmarks")
                .and_then(Node::as_map)
                .into_iter()
                .flatten()
            {
                match benchmarks.get(&name.trim().to_lowercase()) {
                    Some((key, scale)) => {
                        out.insert(key.clone());
                        if own {
                            measurement(model, name, scale, &figure.node, diags);
                        }
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

    /// A workspace catalogue holding one row's figure, in the table's world,
    /// checked the way `pact check` checks it: what `recorded` reports.
    fn measured(table: &Node, row: &Node) -> Diagnostics {
        use serde_json::{Map as J, json};
        let mut provenance = J::new();
        provenance.insert("source".into(), json!("measured here"));
        for key in MEASURED {
            if let Some(field) = row.get(key) {
                provenance.insert(key.into(), field.to_json());
            }
        }
        let figure =
            json!({"value": row.get("value").unwrap().to_json(), "provenance": provenance});
        let model = match row.get("field").and_then(Node::as_str) {
            Some("context-window") => json!({"capabilities": {"context-window": figure}}),
            Some("first-words-within") => json!({"speed": {"first-words-within": figure}}),
            Some(other) => panic!("no figure called {other}"),
            None => {
                let on = row
                    .get("benchmark")
                    .and_then(Node::as_str)
                    .unwrap_or("mmlu");
                json!({"benchmarks": {on: figure}})
            }
        };
        let scales: J<String, serde_json::Value> = table
            .get("benchmarks")
            .and_then(Node::as_map)
            .unwrap()
            .iter()
            .map(|(name, scale)| (name.clone(), json!({"scale": scale.node.as_str().unwrap()})))
            .collect();
        let document = json!({"models": {"benchmarks": scales, "models": {"m": model}}});
        let document = pact_doc::parse_yaml(
            &document.to_string(),
            camino::Utf8Path::new("workspace.yaml"),
        )
        .unwrap();
        let mut diags = Diagnostics::new();
        recorded("", &document, &benchmarks("", &document), &mut diags);
        diags
    }

    /// The table's `figures:` are measurements the checker reads without an
    /// error, and its `not-measurements:` are refused with their `rule:`.
    #[test]
    fn every_measurement_in_the_shared_table_is_checked_as_it_says() {
        let table =
            pact_doc::parse_yaml(VECTORS, camino::Utf8Path::new("accept-when.yaml")).unwrap();
        let rules = |d: &Diagnostics, severity: pact_diag::Severity| -> Vec<&'static str> {
            d.items()
                .iter()
                .filter(|i| i.severity == severity)
                .map(|i| i.rule)
                .collect()
        };
        for row in table.get("figures").and_then(Node::as_list).unwrap() {
            let diags = measured(&table, row);
            let said = row
                .get("written")
                .map_or_else(|| format!("{:?}", row.get("scores")), |w| format!("{w:?}"));
            assert_eq!(
                rules(&diags, pact_diag::Severity::Error),
                Vec::<&str>::new(),
                "{said}"
            );
            let warns: Vec<&str> = row
                .get("warns")
                .and_then(Node::as_str)
                .into_iter()
                .collect();
            assert_eq!(rules(&diags, pact_diag::Severity::Warning), warns, "{said}");
        }
        for row in table
            .get("not-measurements")
            .and_then(Node::as_list)
            .unwrap()
        {
            let diags = measured(&table, row);
            let rule = row.get("rule").and_then(Node::as_str).unwrap();
            assert_eq!(
                rules(&diags, pact_diag::Severity::Error),
                vec![rule],
                "{rule}"
            );
        }
    }
}
