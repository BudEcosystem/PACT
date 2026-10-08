//! A file named after a kind, inside a collection's folder, is an entry of
//! that collection.
//!
//! The loader reads `agent.yaml`, `catalog.yaml`, `tool.yaml` and the other
//! names in [`Policy::kind_stems`](crate::policy::Policy) as the file that
//! describes the folder it sits in, so `agents/desk/agent.yaml` is the agent
//! `desk` and `models/catalog.yaml` is the workspace's `models:`. The loader
//! does not know which folders are collections, so the same rule read
//! `tools/catalog.yaml` as the settings of `tools/` itself: its `description:`,
//! `connect:` and `actions:` became three tools, and the tool `catalog` the
//! author wrote did not exist. Measured on a copy of `examples/refund-desk`
//! with `tools/zendesk.yaml` renamed: three `schema/no-such-name` errors and a
//! warning that `description` is a tool nothing names.
//!
//! The specification knows which folders are collections (a workspace field
//! typed `map of group:<kind>`), so this pass, run before anything else reads
//! the document, gives such a file back its name: the settings it carried
//! become ONE entry named after the file, as any other file in that folder is.
//! `tools/catalog.yaml` is the tool `catalog`.

use pact_doc::{Map, Node};
use pact_schema::Schema;

use crate::policy::Policy;

/// Give every kind-named file in a collection's folder back its name, in the
/// workspace and in what each bundle contributes.
pub fn read_as_entries(root: &mut Node, schema: &Schema) {
    let collections = crate::derive::collections(schema);
    let stems = Policy::default().kind_stems;
    in_collections(root, &collections, &stems);
    let Some(bundles) = root.as_map_mut().and_then(|m| m.get_mut("bundles")) else {
        return;
    };
    for bundle in bundles
        .node
        .as_map_mut()
        .into_iter()
        .flat_map(|m| m.values_mut())
    {
        if let Some(contributes) = bundle
            .node
            .as_map_mut()
            .and_then(|m| m.get_mut("contributes"))
        {
            in_collections(&mut contributes.node, &collections, &stems);
        }
    }
}

fn in_collections(holder: &mut Node, collections: &[String], stems: &[String]) {
    let Some(map) = holder.as_map_mut() else {
        return;
    };
    for kind in collections {
        if let Some(entry) = map.get_mut(kind) {
            give_back_its_name(kind, &mut entry.node, stems);
        }
    }
}

/// When `collection` was built from a file named after a kind that sits
/// directly in the collection's own folder, move that file's settings into
/// one entry named after the file.
fn give_back_its_name(kind: &str, collection: &mut Node, stems: &[String]) {
    let file = collection.span.file.clone();
    let (Some(stem), Some(folder)) = (file.file_stem(), file.parent().and_then(|p| p.file_name()))
    else {
        return;
    };
    if !folder.eq_ignore_ascii_case(kind) || !stems.iter().any(|s| s.eq_ignore_ascii_case(stem)) {
        return;
    }
    let stem = stem.to_string();
    let span = collection.span.clone();
    let Some(entries) = collection.as_map_mut() else {
        return;
    };
    let mine: Vec<String> = entries
        .iter()
        .filter(|(_, e)| e.key_span.file == file)
        .map(|(k, _)| k.clone())
        .collect();
    if mine.is_empty() {
        return;
    }
    let mut settings = Map::new();
    for key in mine {
        if let Some(e) = entries.shift_remove(&key) {
            settings.insert(key, e);
        }
    }
    entries.insert(
        stem,
        pact_doc::Entry {
            key_span: span.clone(),
            node: Node::map(settings, span),
        },
    );
}
