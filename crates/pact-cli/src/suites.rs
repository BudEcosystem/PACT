//! Which suites of checks this workspace has, and every way an author may point
//! at one.
//!
//! `agents/refund-desk/agent.yaml` carries `evals: /evals/suite.yaml` — the one
//! authored cross-reference in the worked example that was written as a PATH
//! rather than as a name. Every other one on that page resolves: `policy:`,
//! `loop:`, `context-policy:`, `interceptors:` and `uses:` all go through
//! `names:` and refuse a typo with the list of what does exist. This one
//! resolved against nothing at all. Measured before this file existed: changing
//! the line to `evals: /evals/suit.yaml` — a file that is not there — printed
//! `OK — examples/refund-desk loaded cleanly (468 settings).` and exited 0. The
//! agent then had no checks, which is the exact opposite of what the author
//! wrote the line to guarantee, and the only tool a D13 reader runs said the
//! tree was fine.
//!
//! # Why this is not a second kind of reference
//!
//! The obvious repair is a path checker beside the name checker: does the file
//! exist, does it parse, is it a suite. That would leave two ways to point at
//! one suite and two vocabularies of diagnostic for one mistake.
//!
//! Decision D2 makes the tree the document, so there is a cheaper answer: **a
//! path into the tree is the address of a node in the document.**
//! `evals/suite.yaml` is the self file of `evals/` (LOAD-5), so it loaded into
//! the node `evals` — which means `/evals/suite.yaml` and `evals` are two
//! spellings of one address, not two mechanisms. Both are put in the set below,
//! the field says `names: pact:evals`, and the existing `schema/no-such-name`
//! check holds the author's line against them. A spelling that names no suite is
//! refused by the same code, with the same shape of message, as a `policy:` that
//! names no policy.
//!
//! The path spelling is read off the suite's own span rather than assumed, so
//! `evals/evals.yaml` and `evals/_index.yaml` — the other two spellings LOAD-5
//! allows for the same document — are each offered as the path that is really
//! there, and never as a path that is not.

use camino::Utf8Path;
use pact_doc::Node;
use pact_schema::Known;
use std::collections::BTreeSet;

/// The document address a suite of checks lives at. One per workspace: the
/// schema gives `evals:` as a single set of settings, not a map of them, so
/// `evals/` is the whole workspace's suite.
const SUITE_KEY: &str = "evals";

/// Every spelling of "the checks this workspace has", for `names: pact:evals`.
///
/// Empty when the workspace has none. That is deliberate and it is the case
/// worth getting right: an agent that points at checks in a workspace with no
/// checks in it is the failure this whole file is about, and the fix it gets
/// names the file to write rather than a list of nothing.
pub fn known_here(root: Option<&Node>) -> Known {
    let mut names = BTreeSet::new();
    if let Some(node) = root
        .and_then(|r| r.get(SUITE_KEY))
        .filter(|n| n.as_map().is_some())
    {
        // The name: the address of the node the suite loaded into. This is the
        // spelling every other reference on the page uses.
        names.insert(SUITE_KEY.to_string());
        // The path: where that node actually came from, so a leading-slash line
        // keeps working and keeps meaning the same thing.
        names.insert(path_spelling(&node.span.file, SUITE_KEY));
    }
    Known {
        label: "this workspace's checks".to_string(),
        add: format!(
            "write one in `{SUITE_KEY}/suite.yaml` (a `when:` and an `expect:` for each \
             case) and point this line at it"
        ),
        names,
    }
}

/// The leading-slash path an author would write for a node at the top of the
/// tree, taken from the file that node came from.
///
/// Derived from the file's own tail rather than by subtracting the workspace
/// root, because the root arrives as whatever was typed on the command line
/// (`.`, `examples/refund-desk`, an absolute path) and a subtraction that fails
/// would refuse the one line in the worked example that is correct.
///
/// Two shapes, which are the two shapes the Expansion Rule can produce for a
/// field at the top of the tree:
///
/// - a folder — `evals/suite.yaml` → `/evals/suite.yaml`;
/// - a file — `evals.yaml` → `/evals.yaml`.
fn path_spelling(file: &Utf8Path, key: &str) -> String {
    let name = file.file_name().unwrap_or(key);
    match file.parent().and_then(Utf8Path::file_name) {
        Some(parent) if parent == key => format!("/{key}/{name}"),
        _ => format!("/{name}"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_diag::Span;
    use pact_doc::{Map, Value};

    fn suite_at(file: &str) -> Node {
        let mut root = Map::new();
        root.insert(
            SUITE_KEY.to_string(),
            pact_doc::Entry {
                key_span: Span::whole_file(file),
                node: Node::new(Value::Map(Map::new()), Span::whole_file(file)),
            },
        );
        Node::new(Value::Map(root), Span::whole_file("workspace.yaml"))
    }

    #[test]
    fn a_workspace_with_a_suite_offers_both_the_name_and_the_path_that_is_really_there() {
        let known = known_here(Some(&suite_at("examples/refund-desk/evals/suite.yaml")));
        assert!(known.names.contains("evals"), "the name spelling: {:?}", known.names);
        assert!(
            known.names.contains("/evals/suite.yaml"),
            "the path spelling: {:?}",
            known.names
        );
        assert_eq!(known.names.len(), 2, "two spellings of one address, not more");
    }

    #[test]
    fn the_path_offered_is_the_file_that_exists_and_never_one_that_does_not() {
        // LOAD-5 makes `suite.yaml`, `evals.yaml` and `_index.yaml` one
        // document. Whichever the author wrote is the path they must be told to
        // write, so this is read off the span rather than assumed.
        for (real, expect) in [
            ("ws/evals/evals.yaml", "/evals/evals.yaml"),
            ("ws/evals/_index.yaml", "/evals/_index.yaml"),
            ("ws/evals.yaml", "/evals.yaml"),
        ] {
            let known = known_here(Some(&suite_at(real)));
            assert!(known.names.contains(expect), "{real} should offer {expect}: {:?}", known.names);
            assert!(
                !known.names.contains("/evals/suite.yaml"),
                "{real} must not offer a file that is not there: {:?}",
                known.names
            );
        }
    }

    #[test]
    fn a_workspace_with_no_checks_offers_the_file_to_write_rather_than_a_list_of_nothing() {
        let known = known_here(None);
        assert!(known.names.is_empty());
        assert!(known.add.contains("`evals/suite.yaml`"), "{}", known.add);
        assert!(known.add.contains("when:") && known.add.contains("expect:"), "{}", known.add);
    }

    #[test]
    fn the_command_line_spelling_of_the_workspace_root_cannot_change_the_answer() {
        // `pact check .`, `pact check examples/refund-desk` and an absolute path
        // all load the same tree, so all three must accept the same line.
        for root in ["./evals/suite.yaml", "evals/suite.yaml", "/home/x/ws/evals/suite.yaml"] {
            let known = known_here(Some(&suite_at(root)));
            assert!(
                known.names.contains("/evals/suite.yaml"),
                "{root} gave {:?}",
                known.names
            );
        }
    }
}
