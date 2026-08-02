//! Canonical form and content digest.
//!
//! The digest addresses a *document*, and is what lockfiles, caches, signatures
//! and provenance records refer to. Two properties make it useful:
//!
//! 1. **It is stable under meaningless change.** Reordering fields, reflowing
//!    whitespace, adding a comment, or moving a field between a file and its
//!    directory form must not move the digest — because none of those change
//!    what the agent does.
//! 2. **It moves under every meaningful change.** Any change to a value, a list
//!    order, or the set of fields must produce a different digest.
//!
//! Field order is therefore normalised away (map keys sort) while list order is
//! preserved, because a list's order is authored intent — pipeline steps are
//! ordered, an agent's fields are not.
//!
//! Note the direction: the digest is computed over the **document**, which is
//! derived from the tree. Hashing build artifacts instead — the mistake Eve's
//! `sourceGraphHash` makes — makes the digest depend on the compiler's
//! behaviour rather than the author's intent.

use crate::value::{Node, Value};
use sha2::{Digest, Sha256};
use std::fmt::Write as _;

/// Serialise to the canonical string form used for digesting.
///
/// This is JSON-shaped with sorted object keys and no insignificant
/// whitespace — close to RFC 8785 (JCS), with PACT's file and payload
/// references written as their reference objects rather than their contents.
pub fn canonical_string(node: &Node) -> String {
    let mut out = String::new();
    write_node(&mut out, node);
    out
}

/// The content digest of a document: `sha256:` followed by lowercase hex.
pub fn digest(node: &Node) -> String {
    let mut hasher = Sha256::new();
    hasher.update(canonical_string(node).as_bytes());
    format!("sha256:{:x}", hasher.finalize())
}

fn write_node(out: &mut String, node: &Node) {
    match &node.value {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Int(i) => {
            let _ = write!(out, "{i}");
        }
        // Floats are written with the shortest representation that round-trips,
        // so 1.0 and 1.00 in the source agree.
        Value::Float(f) => {
            if f.is_finite() {
                let _ = write!(out, "{f}");
            } else {
                out.push_str("null");
            }
        }
        Value::Str(s) => write_string(out, s),
        Value::List(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_node(out, item);
            }
            out.push(']');
        }
        Value::Map(map) => {
            // Sorted: field order is serialisation, not meaning.
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            out.push('{');
            for (i, k) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_string(out, k);
                out.push(':');
                write_node(out, &map[*k].node);
            }
            out.push('}');
        }
        Value::File(f) => {
            out.push_str("{\"$file\":");
            write_string(out, &f.path);
            out.push_str(",\"contentType\":");
            write_string(out, &f.content_type);
            let _ = write!(out, ",\"sizeBytes\":{}}}", f.size_bytes);
        }
        Value::Payload(p) => {
            out.push_str("{\"$payload\":");
            write_string(out, &p.root);
            out.push_str(",\"files\":[");
            // Payload file order is not authored, so it is normalised.
            let mut files: Vec<_> = p.files.iter().collect();
            files.sort_by(|a, b| a.path.cmp(&b.path));
            for (i, f) in files.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                out.push_str("{\"$file\":");
                write_string(out, &f.path);
                out.push_str(",\"contentType\":");
                write_string(out, &f.content_type);
                let _ = write!(out, ",\"sizeBytes\":{}}}", f.size_bytes);
            }
            out.push_str("]}");
        }
    }
}

fn write_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parse_yaml;
    use camino::Utf8Path;

    fn doc(y: &str) -> Node {
        parse_yaml(y, Utf8Path::new("t.yaml")).unwrap()
    }

    #[test]
    fn field_order_does_not_move_the_digest() {
        let a = doc("name: X\ndescription: Y\nmodel: fast\n");
        let b = doc("model: fast\nname: X\ndescription: Y\n");
        assert_eq!(digest(&a), digest(&b), "field order is serialisation, not meaning");
    }

    #[test]
    fn list_order_does_move_the_digest() {
        let a = doc("steps: [fetch, summarise]\n");
        let b = doc("steps: [summarise, fetch]\n");
        assert_ne!(digest(&a), digest(&b), "a pipeline's order is authored intent");
    }

    #[test]
    fn comments_and_whitespace_do_not_move_the_digest() {
        let a = doc("name: X\n# a note for humans\ndescription: Y\n");
        let b = doc("name:    X\ndescription:  Y\n\n");
        assert_eq!(digest(&a), digest(&b));
    }

    #[test]
    fn any_value_change_moves_the_digest() {
        let base = doc("name: X\nlimit: 30\n");
        for changed in ["name: Y\nlimit: 30\n", "name: X\nlimit: 31\n", "name: X\n"] {
            assert_ne!(digest(&base), digest(&doc(changed)), "changed: {changed}");
        }
    }

    #[test]
    fn the_digest_is_stable_across_runs() {
        let d = doc("name: X\nnested:\n  a: 1\n  b: [1, 2]\n");
        assert_eq!(digest(&d), digest(&d));
        assert!(digest(&d).starts_with("sha256:"));
        assert_eq!(digest(&d).len(), 7 + 64);
    }

    #[test]
    fn quoted_and_plain_forms_of_the_same_text_agree() {
        assert_eq!(digest(&doc("a: hello\n")), digest(&doc("a: \"hello\"\n")));
    }

    #[test]
    fn text_is_escaped_so_punctuation_cannot_forge_a_collision() {
        // Without escaping, `a": 1, "b` would smuggle structure into the digest.
        let a = doc("a: 'x\": 1, \"y'\n");
        let b = doc("a: x\nb: 1\ny: ''\n");
        assert_ne!(digest(&a), digest(&b));
        assert!(canonical_string(&a).contains("\\\""));
    }

    #[test]
    fn numbers_that_mean_the_same_thing_agree() {
        assert_eq!(digest(&doc("a: 1.0\n")), digest(&doc("a: 1.00\n")));
    }
}
