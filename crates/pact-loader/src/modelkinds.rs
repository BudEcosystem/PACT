//! **A model of the wrong kind** (96 §A2), and the catalogue reader the voice
//! checks share.
//!
//! The catalogue now holds six kinds of model — `language`, `decision`,
//! `embedding`, `transcription`, `speech`, `reranking` — and they compute
//! different functions. `names: pact:models` says a line names a model and
//! could not say which sort, so `model: nomic-embed-text` and `embedded-by:
//! qwen2.5-7b-instruct` both resolved: to a model that cannot do what the line
//! calls it for, found out on the first call, in another language.
//!
//! Which kinds a line takes is data — `model-kind:` beside `names:
//! pact:models` in `spec/schema.yaml` — so this module holds no list of
//! fields. It walks the document the way `egress.rs` does, from the group the
//! root is into the groups its fields declare, and stops where the
//! specification stops (`anything`), so a `model:` key inside a metric's
//! open `with:` block is not mistaken for a binding.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/the-wrong-kind-of-model` | a line with `model-kind:` names a catalogue row of another kind |
//!
//! A row that writes no `kind:` is a language model, which is what the
//! field's own help has always said. An id in no catalogue is not judged
//! here: `schema/no-such-name` is already refusing it at the same line.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use pact_schema::{Group, Schema, Ty};
use std::collections::BTreeMap;

/// What both catalogue layers say about one model, under every name it has.
#[derive(Debug, Clone, Default)]
pub struct Row {
    /// The row's own key, which is the name a fix should offer.
    pub name: String,
    pub kind: String,
    pub voices: Vec<String>,
    pub languages: Vec<String>,
    pub sessions: Vec<String>,
    /// `settings:` keys the model takes no notice of (96 §B5), always, and
    /// while it thinks; and whether it thinks when `thinking:` says nothing.
    pub ignores: Vec<String>,
    pub ignores_while_thinking: Vec<String>,
    pub thinks_unless_told: bool,
}

/// Every model in the distribution's catalogue and the workspace's own, by id
/// and by alias. A workspace row replaces a shipped one of the same name.
pub fn catalogue(builtin: &str, document: &Node) -> BTreeMap<String, Row> {
    let mut out = BTreeMap::new();
    let shipped = pact_doc::parse_yaml(builtin, camino::Utf8Path::new("models/catalog.yaml")).ok();
    for rows in [shipped.as_ref(), document.get("models")]
        .into_iter()
        .flatten()
        .filter_map(|c| c.get("models").and_then(Node::as_map))
    {
        for (name, entry) in rows {
            let row = &entry.node;
            let can = row.get("capabilities");
            let words = |n: Option<&Node>| -> Vec<String> {
                n.map(crate::workflows::list)
                    .into_iter()
                    .flatten()
                    .filter_map(Node::as_str)
                    .map(|s| s.trim().to_string())
                    .collect()
            };
            let found = Row {
                name: name.clone(),
                kind: row
                    .get("kind")
                    .and_then(Node::as_str)
                    .map_or("language", str::trim)
                    .to_string(),
                voices: words(can.and_then(|c| c.get("voices"))),
                languages: words(can.and_then(|c| c.get("languages"))),
                sessions: words(can.and_then(|c| c.get("sessions"))),
                ignores: words(can.and_then(|c| c.get("ignores"))),
                ignores_while_thinking: words(can.and_then(|c| c.get("ignores-while-thinking"))),
                thinks_unless_told: can
                    .and_then(|c| c.get("thinks-unless-told"))
                    .is_some_and(crate::workflows::said_yes),
            };
            for id in std::iter::once(name.clone()).chain(words(row.get("also-known-as"))) {
                out.insert(id.trim().to_string(), found.clone());
            }
        }
    }
    out
}

/// What a model of each kind does, for the sentence that says it cannot.
fn does(kind: &str) -> &'static str {
    match kind {
        "language" => "reads and writes",
        "decision" => "answers a label and a score",
        "embedding" => "turns text into numbers for looking things up",
        "transcription" => "turns speech into words",
        "speech" => "turns words into speech",
        "reranking" => "puts passages in order",
        _ => "does something else",
    }
}

pub fn check(document: &Node, schema: &Schema, builtin: &str, diags: &mut Diagnostics) {
    let rows = catalogue(builtin, document);
    if let Some(workspace) = schema.group("workspace") {
        walk(document, workspace, schema, &rows, diags);
    }
}

fn walk(
    node: &Node,
    group: &Group,
    schema: &Schema,
    rows: &BTreeMap<String, Row>,
    diags: &mut Diagnostics,
) {
    let Some(map) = node.as_map() else { return };
    for field in &group.fields {
        let Some(entry) = map.get(&field.name) else {
            continue;
        };
        if field.names.iter().any(|n| n == "pact:models") {
            if !field.model_kind.is_empty() {
                for id in crate::workflows::list(&entry.node) {
                    held(id, &group.name, &field.name, &field.model_kind, rows, diags);
                }
            }
            continue;
        }
        descend(&entry.node, &field.ty, schema, rows, diags);
    }
}

fn descend(
    node: &Node,
    ty: &Ty,
    schema: &Schema,
    rows: &BTreeMap<String, Row>,
    diags: &mut Diagnostics,
) {
    match ty {
        Ty::Group(name) => {
            if let Some(group) = schema.group(name) {
                walk(node, group, schema, rows, diags);
            }
        }
        Ty::ListOf(inner) => {
            for item in node.as_list().into_iter().flatten() {
                descend(item, inner, schema, rows, diags);
            }
        }
        Ty::MapOf(inner) => {
            for (_, entry) in node.as_map().into_iter().flatten() {
                descend(&entry.node, inner, schema, rows, diags);
            }
        }
        _ => {}
    }
}

fn held(
    id: &Node,
    group: &str,
    field: &str,
    kinds: &[String],
    rows: &BTreeMap<String, Row>,
    diags: &mut Diagnostics,
) {
    let Some(written) = id.as_str().map(str::trim) else {
        return;
    };
    let Some(row) = rows.get(written) else { return };
    if kinds.contains(&row.kind) {
        return;
    }
    let wanted = kinds.join(" or ");
    let mut offered: Vec<&str> = rows
        .values()
        .filter(|r| kinds.contains(&r.kind))
        .map(|r| r.name.as_str())
        .collect();
    offered.sort_unstable();
    offered.dedup();
    let fix = if offered.is_empty() {
        format!(
            "No model in the catalogue is a {wanted} model yet. Add one to \
             `models/catalog.yaml` with `kind: {}`, or take this line out and let PACT pick.",
            kinds[0]
        )
    } else {
        format!("Name a {wanted} model instead: {}.", offered.join(", "))
    };
    diags.push(Diagnostic::error(
        "loader/the-wrong-kind-of-model",
        id.span.clone(),
        format!(
            "'{field}' on a {group} needs a model that {}, and '{written}' is a {} model — it \
             {}.",
            kinds
                .iter()
                .map(|k| does(k))
                .collect::<Vec<_>>()
                .join(" or "),
            row.kind,
            does(&row.kind)
        ),
        fix,
    ));
}

#[cfg(test)]
mod tests {
    use super::*;

    fn doc(text: &str) -> Node {
        pact_doc::parse_yaml(text, camino::Utf8Path::new("test.yaml")).expect("parses")
    }

    #[test]
    fn a_row_with_no_kind_is_a_language_model_under_every_name() {
        let builtin = "models:\n  chat: {also-known-as: [c]}\n  vec: {kind: embedding}\n";
        let rows = catalogue(builtin, &doc("name: w\n"));
        assert_eq!(rows["chat"].kind, "language");
        assert_eq!(rows["c"].name, "chat");
        assert_eq!(rows["vec"].kind, "embedding");
    }

    #[test]
    fn a_workspace_row_replaces_a_shipped_one() {
        let builtin = "models:\n  m: {kind: embedding}\n";
        let rows = catalogue(builtin, &doc("models:\n  models:\n    m: {kind: speech}\n"));
        assert_eq!(rows["m"].kind, "speech");
    }
}
