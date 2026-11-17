//! **What a model needs of the machine that runs it**: a catalogue row's
//! `size:` (how many parameters) and `requires: {memory, accelerator}`.
//!
//! A runtime that knows its machine leaves out a model served on that machine
//! alone when the machine cannot hold it (`pact_adapters.machine.fits`). So a
//! figure written here has to read the same way in every runtime, and one that
//! does not read is refused where it is written rather than skipped where it is
//! used — a skipped memory figure would bind a model the machine cannot load.
//! `spec/hardware-fit.yaml` holds the readings; this reads its value sections.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/a-parameter-count-that-does-not-read` | a workspace row's `size.value` is not a count such as `7.6B`, `500M` or `8000000000`, nor `unknown` |
//! | `loader/a-memory-figure-that-does-not-read` | a workspace row's `requires.memory.value` is not an amount such as `4.7 GB` or `9 GiB`, nor `unknown` |

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;

/// `size.value` as a number of parameters: a number and an optional `K`, `M`,
/// `B` or `T` (either case), above zero. `None` when it does not read.
pub fn parameters(text: &str) -> Option<f64> {
    let text = text.trim();
    let (number, scale) = match text.chars().last()? {
        'k' | 'K' => (&text[..text.len() - 1], 1e3),
        'm' | 'M' => (&text[..text.len() - 1], 1e6),
        'b' | 'B' => (&text[..text.len() - 1], 1e9),
        't' | 'T' => (&text[..text.len() - 1], 1e12),
        _ => (text, 1.0),
    };
    let count = decimal(number.trim_end())? * scale;
    (count > 0.0).then_some(count)
}

/// `requires.memory.value` in bytes: a number, an optional space, and `KB`,
/// `MB`, `GB`, `TB` or `KiB`, `MiB`, `GiB`, `TiB`, above zero. A bare number
/// is refused — bytes and gigabytes differ by a factor nobody should guess.
pub fn bytes(text: &str) -> Option<u64> {
    let text = text.trim();
    let (number, unit) = text.split_at(text.find(|c: char| c.is_ascii_alphabetic())?);
    let scale: f64 = match unit {
        "KB" => 1e3,
        "MB" => 1e6,
        "GB" => 1e9,
        "TB" => 1e12,
        "KiB" => 1024f64,
        "MiB" => 1024f64.powi(2),
        "GiB" => 1024f64.powi(3),
        "TiB" => 1024f64.powi(4),
        _ => return None,
    };
    let amount = (decimal(number.trim_end())? * scale).round();
    (amount > 0.0).then_some(amount as u64)
}

/// Digits with an optional fraction (`7`, `7.6`); no sign, exponent or spaces
/// inside — the same `\d+(\.\d+)?` the Python reader matches.
fn decimal(text: &str) -> Option<f64> {
    let (whole, fraction) = text.split_once('.').unwrap_or((text, "0"));
    let digits = |s: &str| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit());
    (digits(whole) && digits(fraction))
        .then(|| text.parse().ok())
        .flatten()
}

/// Refuse a workspace row's `size:` or `requires.memory:` figure that does not
/// read. The distribution's rows are held to the same reading by a test.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let Some(rows) = document
        .get("models")
        .and_then(|c| c.get("models"))
        .and_then(Node::as_map)
    else {
        return;
    };
    for (model, row) in rows {
        figures(model, &row.node, diags);
    }
}

fn figures(model: &str, row: &Node, diags: &mut Diagnostics) {
    if let Some(value) = row.get("size").and_then(|f| f.get("value")) {
        let text = value
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| value.to_string());
        if text.trim() != "unknown" && parameters(&text).is_none() {
            diags.push(Diagnostic::error(
                "loader/a-parameter-count-that-does-not-read",
                value.span.clone(),
                format!(
                    "'{model}' gives its size as `{}`, which is not a count of parameters.",
                    text.trim()
                ),
                "Write it like `7.6B`, `405B`, `500M` or `8000000000`, or `unknown`.".to_string(),
            ));
        }
    }
    let memory = row
        .get("requires")
        .and_then(|r| r.get("memory"))
        .and_then(|f| f.get("value"));
    if let Some(value) = memory {
        let text = value
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| value.to_string());
        if text.trim() != "unknown" && bytes(&text).is_none() {
            diags.push(Diagnostic::error(
                "loader/a-memory-figure-that-does-not-read",
                value.span.clone(),
                format!(
                    "'{model}' says it needs `{}` of memory, which is not an amount of memory a \
                     runtime can hold a machine to.",
                    text.trim()
                ),
                "Write it with its unit, like `4.7 GB`, `9 GiB` or `800 MB`, or `unknown`."
                    .to_string(),
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const VECTORS: &str = include_str!("../../../spec/hardware-fit.yaml");
    const SHIPPED: &str = include_str!("../../../models/catalog.yaml");

    fn section(name: &str) -> Vec<Node> {
        let table =
            pact_doc::parse_yaml(VECTORS, camino::Utf8Path::new("spec/hardware-fit.yaml")).unwrap();
        table.get(name).and_then(Node::as_list).unwrap().to_vec()
    }

    fn text(row: &Node, key: &str) -> String {
        let value = row.get(key).unwrap();
        value
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| value.to_string())
    }

    #[test]
    fn every_size_and_memory_in_the_shared_table_reads_as_it_says() {
        for row in section("sizes") {
            let (written, reads) = (text(&row, "written"), text(&row, "reads"));
            let want = (reads != "unknown").then(|| reads.parse::<f64>().unwrap());
            let got = if written == "unknown" {
                None
            } else {
                parameters(&written)
            };
            assert_eq!(got, want, "size {written}");
        }
        for row in section("not-sizes") {
            assert_eq!(
                parameters(&text(&row, "written")),
                None,
                "{}",
                text(&row, "because")
            );
        }
        for row in section("memories") {
            let (written, reads) = (text(&row, "written"), text(&row, "reads"));
            let want = (reads != "unknown").then(|| reads.parse::<u64>().unwrap());
            let got = if written == "unknown" {
                None
            } else {
                bytes(&written)
            };
            assert_eq!(got, want, "memory {written}");
        }
        for row in section("not-memories") {
            assert_eq!(
                bytes(&text(&row, "written")),
                None,
                "{}",
                text(&row, "because")
            );
        }
    }

    fn checked(catalogue: &str) -> Diagnostics {
        let wrapped = format!(
            "models:\n{}",
            catalogue
                .lines()
                .map(|l| format!("  {l}\n"))
                .collect::<String>()
        );
        let doc = pact_doc::parse_yaml(&wrapped, camino::Utf8Path::new("workspace.yaml")).unwrap();
        let mut diags = Diagnostics::default();
        check(&doc, &mut diags);
        diags
    }

    #[test]
    fn a_figure_that_does_not_read_is_refused_where_it_is_written() {
        let diags = checked(
            "models:\n  m:\n    size: {value: 7.6 GB}\n    requires:\n      memory: {value: \"8\"}\n",
        );
        let rules: Vec<_> = diags.items().iter().map(|d| d.rule).collect();
        assert_eq!(
            rules,
            [
                "loader/a-parameter-count-that-does-not-read",
                "loader/a-memory-figure-that-does-not-read"
            ]
        );
        let fine = checked(
            "models:\n  m:\n    size: {value: 7.6B}\n    requires:\n      memory: {value: 4.7 GB}\n      accelerator: gpu\n  n:\n    size: {value: unknown}\n    requires:\n      memory: {value: unknown}\n",
        );
        assert!(fine.is_empty());
    }

    #[test]
    fn every_figure_the_distribution_ships_reads() {
        let doc = pact_doc::parse_yaml(
            &format!(
                "models:\n{}",
                SHIPPED
                    .lines()
                    .map(|l| format!("  {l}\n"))
                    .collect::<String>()
            ),
            camino::Utf8Path::new("w.yaml"),
        )
        .unwrap();
        let mut diags = Diagnostics::default();
        check(&doc, &mut diags);
        assert!(diags.is_empty(), "{:?}", diags.items());
    }
}
