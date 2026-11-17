//! **A copied catalogue row that has fallen behind** the distribution's.
//!
//! A workspace row replaces the distribution's row of the same name whole, so
//! a figure is never two sources mixed. Recording one benchmark figure for a
//! shipped model therefore copies the shipped row first (`benchmarks.record`),
//! and the copy keeps the price, the window and the serving it was copied with.
//! When the distribution later corrects that row, the workspace goes on binding
//! against the old facts with nothing said. `copied-from.digest` records which
//! version of the row was copied; this compares it with the row the
//! distribution ships now and warns, naming the fields that now differ.
//!
//! The digest is `sha256:` and the hex SHA-256 of the row's JSON as `pact show`
//! prints it, with every mapping's keys sorted and no spaces. The Python writer
//! digests the JSON `pact show` gave it, so neither runtime reads YAML numbers
//! for itself; `spec/copied-rows.yaml` holds both to the same digests.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/a-copied-row-behind-the-distribution` (warning) | a workspace row's `copied-from.digest` is not the digest of the distribution's row of that name as shipped now, or the distribution no longer has that row |

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

/// The digest `copied-from.digest` records for a distribution row.
pub fn digest(row: &Node) -> String {
    let text = serde_json::to_string(&sorted(row.to_json())).unwrap_or_default();
    format!("sha256:{:x}", Sha256::digest(text.as_bytes()))
}

/// `value` with every object's keys in sorted order. `serde_json` keeps
/// insertion order here (`preserve_order`), so the order is rebuilt by hand.
fn sorted(value: Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut entries: Vec<(String, Value)> = map.into_iter().collect();
            entries.sort_by(|a, b| a.0.cmp(&b.0));
            Value::Object(
                entries
                    .into_iter()
                    .map(|(k, v)| (k, sorted(v)))
                    .collect::<Map<_, _>>(),
            )
        }
        Value::Array(items) => Value::Array(items.into_iter().map(sorted).collect()),
        other => other,
    }
}

/// The distribution's row a workspace row of this name copied: the row of that
/// key, or the one that lists it under `also-known-as:`.
fn shipped_row<'a>(shipped: &'a Node, name: &str) -> Option<&'a Node> {
    let rows = shipped.get("models").and_then(Node::as_map)?;
    rows.iter().find_map(|(key, row)| {
        let aliases = row
            .node
            .get("also-known-as")
            .and_then(Node::as_list)
            .unwrap_or(&[]);
        (key == name || aliases.iter().any(|a| a.as_str() == Some(name))).then_some(&row.node)
    })
}

/// Warn on every workspace row whose `copied-from.digest` no longer matches the
/// distribution's row it was copied from.
pub fn check(document: &Node, builtin: &str, diags: &mut Diagnostics) {
    let Some(rows) = document
        .get("models")
        .and_then(|c| c.get("models"))
        .and_then(Node::as_map)
    else {
        return;
    };
    let Ok(shipped) = pact_doc::parse_yaml(builtin, camino::Utf8Path::new("models/catalog.yaml"))
    else {
        return;
    };
    for (model, row) in rows {
        let Some(copied) = row.node.get("copied-from").and_then(|c| c.get("digest")) else {
            continue;
        };
        let recorded = copied.as_str().unwrap_or("").trim();
        let Some(now) = shipped_row(&shipped, model) else {
            diags.push(Diagnostic::warning(
                "loader/a-copied-row-behind-the-distribution",
                copied.span.clone(),
                format!(
                    "'{model}' was copied from the distribution's row of that name, and the \
                     distribution no longer has one, so nothing here keeps its figures current."
                ),
                format!(
                    "Check the row's figures against their sources, then take `copied-from:` out \
                     of '{model}' so it reads as a row of your own."
                ),
            ));
            continue;
        };
        if digest(now) == recorded {
            continue;
        }
        let differ = differing(&row.node, now);
        diags.push(Diagnostic::warning(
            "loader/a-copied-row-behind-the-distribution",
            copied.span.clone(),
            format!(
                "'{model}' is a copy of the distribution's row, and that row has changed since it \
                 was copied: {} now differ{}.",
                if differ.is_empty() {
                    "no field of the copy".to_string()
                } else {
                    differ.join(", ")
                },
                if differ.len() == 1 { "s" } else { "" }
            ),
            format!(
                "Compare each with the distribution's row, keep what you changed on purpose, take \
                 the rest from it, and write `copied-from: {{digest: {}}}`.",
                digest(now)
            ),
        ));
    }
}

/// The top-level fields where the workspace row and the distribution's row
/// now disagree, sorted; `copied-from` is the copy's own.
fn differing(copy: &Node, shipped: &Node) -> Vec<String> {
    let (copy, shipped) = (copy.to_json(), shipped.to_json());
    let empty = Map::new();
    let (copy, shipped) = (
        copy.as_object().unwrap_or(&empty),
        shipped.as_object().unwrap_or(&empty),
    );
    let mut keys: Vec<&String> = copy
        .keys()
        .chain(shipped.keys())
        .filter(|k| *k != "copied-from")
        .collect();
    keys.sort();
    keys.dedup();
    keys.into_iter()
        .filter(|k| {
            copy.get(*k).map(|v| sorted(v.clone())) != shipped.get(*k).map(|v| sorted(v.clone()))
        })
        .map(|k| format!("`{k}`"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    const VECTORS: &str = include_str!("../../../spec/copied-rows.yaml");

    fn table() -> Node {
        pact_doc::parse_yaml(VECTORS, camino::Utf8Path::new("spec/copied-rows.yaml")).unwrap()
    }

    #[test]
    fn every_row_in_the_shared_table_digests_as_it_says() {
        for case in table().get("digests").and_then(Node::as_list).unwrap() {
            let want = case.get("digest").and_then(Node::as_str).unwrap();
            assert_eq!(
                digest(case.get("row").unwrap()),
                want,
                "{}",
                case.get("because").unwrap()
            );
        }
    }

    fn checked(workspace: &str, shipped: &str) -> Diagnostics {
        let doc = pact_doc::parse_yaml(workspace, camino::Utf8Path::new("workspace.yaml")).unwrap();
        let mut diags = Diagnostics::new();
        check(&doc, shipped, &mut diags);
        diags
    }

    #[test]
    fn a_copy_of_the_current_row_is_quiet_and_a_stale_one_names_what_differs() {
        let shipped = "models:\n  m:\n    tier: small\n    also-known-as: [m-alias]\n    cost: {input-per-mtok: 0.10 USD, output-per-mtok: 0.40 USD}\n";
        let row = pact_doc::parse_yaml(shipped, camino::Utf8Path::new("c.yaml")).unwrap();
        let current = digest(row.get("models").and_then(|m| m.get("m")).unwrap());
        let copy = |digest: &str, cost: &str| {
            format!(
                "models:\n  models:\n    m:\n      tier: small\n      also-known-as: [m-alias]\n      cost: {cost}\n      benchmarks: {{mmlu: {{value: \"80\"}}}}\n      copied-from: {{digest: \"{digest}\"}}\n"
            )
        };
        let quiet = checked(
            &copy(
                &current,
                "{input-per-mtok: 0.10 USD, output-per-mtok: 0.40 USD}",
            ),
            shipped,
        );
        assert!(quiet.is_empty(), "{:?}", quiet.items());

        let moved = "models:\n  m:\n    tier: small\n    also-known-as: [m-alias]\n    cost: {input-per-mtok: 0.08 USD, output-per-mtok: 0.40 USD}\n";
        let stale = checked(
            &copy(
                &current,
                "{input-per-mtok: 0.10 USD, output-per-mtok: 0.40 USD}",
            ),
            moved,
        );
        let [warning] = stale.items() else {
            panic!("{:?}", stale.items())
        };
        assert_eq!(warning.rule, "loader/a-copied-row-behind-the-distribution");
        assert!(
            warning.message.contains("`benchmarks`, `cost` now differ"),
            "{}",
            warning.message
        );

        let by_alias = format!(
            "models:\n  models:\n    m-alias:\n      tier: small\n      also-known-as: [m-alias]\n      cost: {{input-per-mtok: 0.10 USD, output-per-mtok: 0.40 USD}}\n      copied-from: {{digest: \"{current}\"}}\n"
        );
        assert!(checked(&by_alias, shipped).is_empty());

        let gone = checked(&copy(&current, "{}"), "models:\n  other: {tier: small}\n");
        assert_eq!(gone.items().len(), 1);
        assert!(gone.items()[0].message.contains("no longer has one"));
    }

    #[test]
    fn a_row_without_copied_from_is_not_judged() {
        let ws = "models:\n  models:\n    m: {tier: frontier}\n";
        assert!(checked(ws, "models:\n  m: {tier: small}\n").is_empty());
    }
}
