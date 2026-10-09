//! The spanned document tree.
//!
//! Every node remembers where it came from. That is not a debugging nicety —
//! decision D2 makes the file tree the native, authoritative form of a PACT
//! agent, so a node's provenance *is* part of its identity: it is how the
//! loader reports ambiguity, how the validator points at a mistake, and how a
//! learning cycle writes an edit back to the right file (thesis T6).

use indexmap::IndexMap;
use pact_diag::Span;
use std::fmt;

/// A reference to a file whose bytes are deliberately **not** inlined into the
/// document — images, audio, video, archives, model weights.
///
/// The Expansion Rule turns directories into fields, which would otherwise
/// invite slurping a 2 GB video into the IR. Binary payloads therefore become
/// references carrying enough metadata to resolve, cache, and digest them.
#[derive(Debug, Clone, PartialEq)]
pub struct FileRef {
    /// Path relative to the workspace root, always forward-slashed.
    pub path: String,
    /// Best-effort media type derived from the extension.
    pub content_type: String,
    pub size_bytes: u64,
    /// sha256 of the file's contents, in lower-case hex.
    ///
    /// EXP-8 asked for this from the start and it was not built, so two trees
    /// holding the same filenames at the same sizes and completely different
    /// bytes had the same `workspace-digest`: signing a tree said nothing about
    /// the scripts inside it, and a reviewer who had read a body could not say
    /// later that it was still the body they read.
    ///
    /// The BYTES never enter the document — that is what keeps reading a tree
    /// from being an act of loading it. What is recorded is a fingerprint of
    /// them, and an unreadable file carries an empty one rather than a guess.
    pub digest: String,
}

/// A directory carried through verbatim as a set of files, rather than
/// expanded into fields.
///
/// The Expansion Rule ("a directory is a field") is not universal: some
/// directories are **payloads**, not structure. A sandbox workspace seeded with
/// `setup.py` and `data.csv`, or a folder of images, must keep its filenames —
/// and expanding `setup.py` into a field called `setup` would silently discard
/// the extension, which is exactly the kind of quiet loss thesis T7 forbids.
///
/// Paths are relative to the payload root and always forward-slashed, so the
/// same tree yields the same document on every platform.
#[derive(Debug, Clone, PartialEq)]
pub struct Payload {
    pub root: String,
    pub files: Vec<FileRef>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    List(Vec<Node>),
    Map(Map),
    File(FileRef),
    Payload(Payload),
}

impl Value {
    /// A stable, human-readable type name used in diagnostics. These words are
    /// chosen for a non-technical reader (D13): "a list", "some text" — not
    /// "Vec<Node>" or "scalar".
    pub fn kind_name(&self) -> &'static str {
        match self {
            Value::Null => "nothing",
            Value::Bool(_) => "yes/no",
            Value::Int(_) => "a whole number",
            Value::Float(_) => "a number",
            Value::Str(_) => "some text",
            Value::List(_) => "a list",
            Value::Map(_) => "a set of settings",
            Value::File(_) => "a file",
            Value::Payload(_) => "a folder of files",
        }
    }
}

/// One key/value pair in a mapping. The key carries its own span so a
/// diagnostic can underline the *key* ("this setting does not exist") rather
/// than the value.
#[derive(Debug, Clone, PartialEq)]
pub struct Entry {
    pub key_span: Span,
    pub node: Node,
}

/// An insertion-ordered mapping.
///
/// Order is preserved because the tree round-trips back to files (D18: four
/// surfaces write these documents, and diffs must stay meaningful). Order is
/// *not* semantically significant for named fields; it only controls
/// serialisation.
pub type Map = IndexMap<String, Entry>;

#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub value: Value,
    pub span: Span,
}

impl Node {
    pub fn new(value: Value, span: Span) -> Self {
        Self { value, span }
    }

    pub fn null(span: Span) -> Self {
        Self::new(Value::Null, span)
    }

    pub fn str(s: impl Into<String>, span: Span) -> Self {
        Self::new(Value::Str(s.into()), span)
    }

    pub fn map(map: Map, span: Span) -> Self {
        Self::new(Value::Map(map), span)
    }

    pub fn list(items: Vec<Node>, span: Span) -> Self {
        Self::new(Value::List(items), span)
    }

    pub fn as_map(&self) -> Option<&Map> {
        match &self.value {
            Value::Map(m) => Some(m),
            _ => None,
        }
    }

    pub fn as_map_mut(&mut self) -> Option<&mut Map> {
        match &mut self.value {
            Value::Map(m) => Some(m),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match &self.value {
            Value::Str(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_list(&self) -> Option<&[Node]> {
        match &self.value {
            Value::List(l) => Some(l),
            _ => None,
        }
    }

    /// Look up a direct child by key.
    pub fn get(&self, key: &str) -> Option<&Node> {
        self.as_map().and_then(|m| m.get(key)).map(|e| &e.node)
    }

    /// Insert or replace a child, keeping insertion order for new keys.
    pub fn insert(&mut self, key: impl Into<String>, key_span: Span, node: Node) {
        if let Value::Map(m) = &mut self.value {
            m.insert(key.into(), Entry { key_span, node });
        }
    }

    /// Total node count, used to bound pathological inputs and to report size.
    pub fn node_count(&self) -> usize {
        1 + match &self.value {
            Value::List(items) => items.iter().map(Node::node_count).sum::<usize>(),
            Value::Map(m) => m.values().map(|e| e.node.node_count()).sum::<usize>(),
            _ => 0,
        }
    }

    /// How many bytes of *text* the tree holds: every piece of writing in it,
    /// plus the setting names it is filed under.
    ///
    /// Counting settings is not the same as counting size. One setting can hold
    /// a megabyte of text, so a limit expressed only in settings says nothing
    /// about how much memory a copy of this tree needs — which is the question
    /// a `&name`/`*name` shortcut actually asks. Numbers, yes/no and nothing
    /// are all fixed-width and cost nothing worth counting.
    pub fn text_bytes(&self) -> usize {
        match &self.value {
            Value::Str(s) => s.len(),
            Value::List(items) => items.iter().map(Node::text_bytes).sum(),
            Value::Map(m) => m.iter().map(|(k, e)| k.len() + e.node.text_bytes()).sum(),
            Value::File(f) => f.path.len() + f.content_type.len() + f.digest.len(),
            Value::Payload(p) => {
                p.root.len()
                    + p.files
                        .iter()
                        .map(|f| f.path.len() + f.content_type.len())
                        .sum::<usize>()
            }
            _ => 0,
        }
    }

    /// Depth of the tree, used to enforce a nesting limit.
    pub fn depth(&self) -> usize {
        1 + match &self.value {
            Value::List(items) => items.iter().map(Node::depth).max().unwrap_or(0),
            Value::Map(m) => m.values().map(|e| e.node.depth()).max().unwrap_or(0),
            _ => 0,
        }
    }

    /// Convert to plain JSON, dropping spans. This is the shape written to
    /// `canonical.json` — a **derived** artifact (D2), never the source of truth.
    pub fn to_json(&self) -> serde_json::Value {
        use serde_json::Value as J;
        match &self.value {
            Value::Null => J::Null,
            Value::Bool(b) => J::Bool(*b),
            Value::Int(i) => J::Number((*i).into()),
            // `from_f64` returns nothing for infinity and not-a-number, and the
            // `J::Null` here is what that used to come out as. It was reachable
            // from a FILE: `x-threshold: 1e999` parsed to infinity, so a value
            // the author had typed left through this arm as nothing at all,
            // with no problem reported anywhere. That is fixed where it was
            // caused — `yaml::resolve_scalar` no longer reads a number it
            // cannot hold as a number — so no authored document can reach this
            // arm any more. It stays because `Value::Float` is a public field
            // on a public type and nothing here can promise what a caller
            // builds by hand; falling back is better than a panic in a
            // checker.
            Value::Float(f) => serde_json::Number::from_f64(*f).map_or(J::Null, J::Number),
            Value::Str(s) => J::String(s.clone()),
            Value::List(items) => J::Array(items.iter().map(Node::to_json).collect()),
            Value::Map(m) => J::Object(
                m.iter()
                    .map(|(k, e)| (k.clone(), e.node.to_json()))
                    .collect(),
            ),
            Value::File(f) => file_ref_json(f),
            Value::Payload(p) => {
                let mut o = serde_json::Map::new();
                o.insert("$payload".into(), J::String(p.root.clone()));
                o.insert(
                    "files".into(),
                    J::Array(p.files.iter().map(file_ref_json).collect()),
                );
                J::Object(o)
            }
        }
    }
}

fn file_ref_json(f: &FileRef) -> serde_json::Value {
    let mut o = serde_json::Map::new();
    o.insert("$file".into(), serde_json::Value::String(f.path.clone()));
    o.insert(
        "contentType".into(),
        serde_json::Value::String(f.content_type.clone()),
    );
    o.insert(
        "sizeBytes".into(),
        serde_json::Value::Number(f.size_bytes.into()),
    );
    if !f.digest.is_empty() {
        o.insert("digest".into(), serde_json::Value::String(f.digest.clone()));
    }
    serde_json::Value::Object(o)
}

impl fmt::Display for Node {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_json())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sp() -> Span {
        Span::whole_file("t.yaml")
    }

    #[test]
    fn kind_names_are_plain_language() {
        // D13: a non-coder reads these. No type jargon may leak into diagnostics.
        for (v, expected) in [
            (Value::Null, "nothing"),
            (Value::Bool(true), "yes/no"),
            (Value::Str(String::new()), "some text"),
            (Value::List(vec![]), "a list"),
            (Value::Map(Map::new()), "a set of settings"),
        ] {
            assert_eq!(v.kind_name(), expected);
            assert!(
                !expected.contains(['<', '>', ':']),
                "kind name '{expected}' looks like a type name"
            );
        }
    }

    #[test]
    fn depth_and_count_traverse_both_containers() {
        let leaf = Node::str("x", sp());
        let inner = Node::list(vec![leaf.clone(), leaf.clone()], sp());
        let mut m = Map::new();
        m.insert(
            "a".into(),
            Entry {
                key_span: sp(),
                node: inner,
            },
        );
        let root = Node::map(m, sp());

        assert_eq!(root.depth(), 3); // map -> list -> str
        assert_eq!(root.node_count(), 4); // map + list + 2 strings
    }

    #[test]
    fn to_json_emits_file_refs_as_references_not_bytes() {
        let n = Node::new(
            Value::File(FileRef {
                path: "assets/logo.png".into(),
                content_type: "image/png".into(),
                size_bytes: 2048,
                digest: "b".repeat(64),
            }),
            sp(),
        );
        let j = n.to_json();
        assert_eq!(j["$file"], "assets/logo.png");
        assert_eq!(j["sizeBytes"], 2048);
        // The fingerprint of the contents, and never the contents.
        assert_eq!(j["digest"], "b".repeat(64));
        assert!(
            j.get("data").is_none(),
            "binary payloads must never be inlined"
        );
    }

    #[test]
    fn map_preserves_insertion_order_for_stable_diffs() {
        let mut root = Node::map(Map::new(), sp());
        for k in ["zebra", "apple", "mango"] {
            root.insert(k, sp(), Node::str(k, sp()));
        }
        let keys: Vec<_> = root.as_map().unwrap().keys().map(String::as_str).collect();
        assert_eq!(
            keys,
            vec!["zebra", "apple", "mango"],
            "D18: diffs must stay meaningful"
        );
    }
}
