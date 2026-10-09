//! **A document nothing points at.**
//!
//! A fully-written approval policy that no agent names loads cleanly and gates
//! nothing. Measured: `policies/approvals.yaml` plus `questions/is-this-ok.yaml`,
//! with `policy: approvals` left off `agent.yaml`, printed *"OK — loaded cleanly
//! (29 settings)"*. The same for a question nothing asks, a tool no `uses:` line
//! lists, an interceptor nobody attaches, and a loop nobody points at.
//!
//! Forgetting the one-line pointer is the commonest way to author a gate that
//! does not exist, and PACT's whole `names:` machinery runs in the other
//! direction only: it asks *does this name resolve?* and never *does anything
//! name this?*
//!
//! # A warning, not an error
//!
//! The tree runs. An unattached policy is a real file with real rules in it, and
//! plenty of legitimate reasons exist for one to be there mid-edit — a rule
//! being written before the agent that will use it, a question shared by a
//! workspace that has just lost its second agent. Refusing would make the
//! ordinary act of writing a file in the wrong order into an error.
//!
//! What it may never be is SILENT, because the failure it produces is the
//! dangerous direction: the author believes the gate exists.
//!
//! # What is deliberately not warned about
//!
//! `skills:` and `agents:` are absent from the list. A skill nothing lists is a
//! written procedure somebody may be about to attach and reads perfectly well on
//! its own; an agent nothing names is the ordinary shape of a top-level agent,
//! which nothing is supposed to point at. `watch:` too — the schema's own
//! argument for keeping it workspace-scoped is that nobody names a watch.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use pact_schema::Schema;
use std::collections::BTreeSet;

/// One kind, and every line that can name one.
struct Kind {
    /// The workspace section holding the documents.
    section: &'static str,
    /// What one of them is, in a sentence.
    what: &'static str,
    /// The line an author writes to attach one, for the fix.
    attach: &'static str,
}

const KINDS: &[Kind] = &[
    Kind {
        section: "policies",
        what: "approval policy",
        attach: "`policy: {}` on an agent",
    },
    Kind {
        section: "questions",
        what: "question",
        attach: "`asks: {}` under `limits:`, `teamwork:` or a context policy, or `question: {}` in a policy rule",
    },
    Kind { section: "tools", what: "tool", attach: "`uses:` with `- {}` under it, on an agent" },
    Kind {
        section: "interceptors",
        what: "rule that may change what happens",
        attach: "`interceptors:` with `- {}` under it, on an agent — or `applies-to: every-agent` in the rule itself",
    },
    Kind { section: "loops", what: "shape of thinking", attach: "`loop: {}` on an agent" },
    Kind {
        section: "context-policies",
        what: "set of tidying rules",
        attach: "`context-policy: {}` on an agent",
    },
    // `redactions` is gone from this list, with the section itself (R61). It was
    // the one entry whose advice made things worse: `redaction:` bound exactly
    // one name, so the SECOND file in `redactions/` was unbindable by
    // construction and the warning for it said *"Add a line: `redaction:
    // staff-data` in workspace.yaml"* — a line that REPLACES the name already
    // there and switches the first set of rules off in silence. The repair was
    // the shape, not the wording: one `redaction:` field of the workspace,
    // written as `redaction.yaml` beside `workspace.yaml`, which nothing points
    // at and nothing can fail to point at.
    // Not one of the three deliberate omissions above — just missing. Measured:
    // changing one tool's `connect:` to a different, valid server left
    // `payments-server` — the file carrying `asks-to-connect: may-we-connect` —
    // named by nobody, `pact check` printed "OK — loaded cleanly", and `pact
    // waits` silently lost the whole `needs-permission` entry: a human consent
    // gate on money, gone, from the list §9.4 G14 obliges a runtime to walk.
    Kind {
        section: "programs",
        what: "carried program",
        attach: "`program: {}` on a tool's action",
    },
    Kind {
        section: "resources",
        what: "connected system",
        attach: "`connect: {}` on a tool, or `through: {}` on a port",
    },
];

/// The collections deliberately NOT warned about, each with the reason.
///
/// Written down rather than left as an absence, because an absence and a
/// decision look identical in a table and only one of them should survive
/// review. Every workspace collection something can name is either in [`KINDS`]
/// or here, and `every_collection_a_line_can_name_is_warned_about_or_excused`
/// holds the pair against the schema — so a collection added to
/// `spec/schema.yaml` cannot slip past this check by nobody noticing.
///
/// This is the half the four loader tables were missing. Two of them named
/// fields no group has, and nothing failed, because a name in Rust was held
/// against nothing at all.
/// Read by `every_collection_a_line_can_name_is_warned_about_or_excused`, and by
/// anybody deciding whether to add a `Kind` row. It is a record of decisions,
/// so it is present in every build and not only under `cfg(test)`.
#[cfg_attr(not(test), allow(dead_code))]
const OMITTED: &[(&str, &str)] = &[
    (
        "skills",
        "a written procedure somebody may be about to attach, which reads perfectly \
         well on its own",
    ),
    (
        "knowledge",
        "a set of documents somebody may be about to attach, on the same reading as a \
         skill: the files are there and nobody is misled about a guarantee that is not",
    ),
    ("agents", "the ordinary shape of a top-level agent, which nothing is supposed to point at"),
    (
        "ports",
        "a way in, named by whatever is outside the workspace rather than by anything \
         inside it",
    ),
    ("bundles", "mounted by `from:`, not named by a line elsewhere in the tree"),
    (
        "workflows",
        "the ordinary shape of a top-level flow, started by a port or a caller rather \
         than by a line inside the workspace, as an agent is",
    ),
    (
        "values",
        "a figure nothing reads is told by `values.rs` (`loader/nothing-uses-this-value`), \
         the one pass that sees it before it is put in place",
    ),
    (
        "watch",
        "workspace-scoped on purpose — the schema's own argument for keeping it there \
         is that nobody names a watch",
    ),
];

/// Warn about a document in the tree that nothing anywhere names.
pub fn nothing_points_at_it(document: &Node, schema: &Schema, diags: &mut Diagnostics) {
    // Every string anywhere in the tree, once. Crude on purpose: asking "does
    // any line name this?" is a different question from "is this name valid
    // here?", and enumerating the twenty-odd fields that can name one of these
    // would be a list to keep in step with the schema — which is the copy F-1
    // forbids. A false NEGATIVE here (a name mentioned in a comment-like text
    // field) costs nothing; a false positive would tell an author to attach
    // something already attached.
    let mut mentioned: BTreeSet<&str> = BTreeSet::new();
    collect(document, &mut mentioned);
    // And the names that are inside a sentence rather than being one.
    //
    // A rewriting interceptor rule is one prose string — `replace the answer
    // with what house-style returns` — so the walk above inserts the whole line
    // and never the name in the middle of it. That produced exactly the false
    // positive the paragraph above rules out: the ONE authoring path §8.5 gives
    // for `change-the-answer` drew a warning saying its program "never takes
    // effect", about a reference the resolver follows and refuses when it is
    // absent. Two checks disagreed about one line.
    //
    // The repair is not to split every string on whitespace — that would make
    // any word of any `description:` count as a mention and silence this check
    // wherever a name happens to appear in prose. It is to read the same holes
    // the resolver reads, from the same parse.
    let in_sentences = schema.names_in_sentences(document);
    let in_sentences: BTreeSet<&str> =
        in_sentences.iter().map(|n| n.name.trim()).collect();
    // Whether anything here needs a locked room and has no line to name one
    // with. Asked once, because it is a fact about the whole workspace.
    let room_wanted = crate::programs::a_room_is_needed_with_no_tool_to_name_it(document, schema);

    for kind in KINDS {
        let Some(entries) = document.get(kind.section).and_then(Node::as_map) else { continue };
        for (name, entry) in entries {
            if mentioned.contains(name.as_str())
                || in_sentences.contains(name.as_str())
                || attaches_itself(&entry.node)
                || a_room_nothing_can_point_at(kind.section, &entry.node, room_wanted)
            {
                continue;
            }
            diags.push(Diagnostic::warning(
                "loader/nothing-points-at-it",
                entry.key_span.clone(),
                format!(
                    "'{name}' is a {} that nothing here names, so it never takes effect — \
                     the file loads, and no run ever reads it.",
                    kind.what
                ),
                format!("Add a line: {}. Or delete the file.", kind.attach.replace("{}", name)),
            ));
        }
    }
}

/// A locked room in a workspace whose need for one cannot write `connect:`.
///
/// The `resources` row's advice is *"`connect:` on a tool, or `through:` on a
/// port"*, and both are lines on a tool or a port. A `does: run-code` stage names
/// no tool; a program reached by `uses:`, `decided-by:`, `checked-by:` or a
/// rewriting sentence names no tool either. Each needs a room, and none of them
/// can write the line this warning asks for.
///
/// Measured: obeying the `run-code` refusal's own printed fix drew
/// `nothing-points-at-it` on the very file it told the author to add, and
/// `--deny-warnings` still failed. A fix that produces a warning is not a fix,
/// and telling an author to write a line that does not exist is worse than
/// saying nothing.
///
/// Narrow on purpose. Only a `resource-kind: sandbox` is excused, and only in a
/// workspace that really has such a need — every other kind of connected system,
/// and every sandbox in a tree whose programs all go through tools, is warned
/// about exactly as before.
fn a_room_nothing_can_point_at(section: &str, node: &Node, wanted: bool) -> bool {
    wanted
        && section == "resources"
        && node.get("resource-kind").and_then(Node::as_str) == Some("sandbox")
}

/// A document that says, on its own line, that it applies to everything.
///
/// `interceptor.applies-to: every-agent` is the one shape of attachment that is
/// written on the DOCUMENT rather than on the thing that names it — because a
/// rule that must cover every agent is a property of the rule, and an agent that
/// could opt out by deleting a line is the agent that leaks.
fn attaches_itself(node: &Node) -> bool {
    node.get("applies-to").and_then(Node::as_str).map(str::trim) == Some("every-agent")
}

/// Every string value in the document, borrowed.
///
/// Values only. A KEY is the name of the document itself, so counting keys would
/// make every entry name itself and the check would never fire.
fn collect<'a>(node: &'a Node, out: &mut BTreeSet<&'a str>) {
    match &node.value {
        pact_doc::Value::Str(s) => {
            out.insert(s.trim());
            // `/evals/suite.yaml` and `payments/issue-refund` both carry a name
            // inside a path, and a rule naming `zendesk/reply` is a line that
            // names `zendesk`.
            for part in s.trim().split('/') {
                out.insert(part.trim());
            }
            // And an address written as who provides it, a colon, then what it
            // is: `program:house-style`, `deepeval:faithfulness`,
            // `pact:loop/standard`. A suite grading every case with
            // `uri: program:house-style` was told that program "never takes
            // effect", because the whole address was registered and the name
            // inside it never was.
            //
            // The same bounded decomposition the `/` split is, and for the same
            // reason: these are syntactic forms with a part that IS a name, not
            // an excuse to split every string on every space — which would let
            // any word of any `description:` silence this check.
            for part in s.trim().split(':') {
                out.insert(part.trim());
            }
        }
        pact_doc::Value::List(items) => {
            for item in items {
                collect(item, out);
            }
        }
        pact_doc::Value::Map(m) => {
            for entry in m.values() {
                collect(&entry.node, out);
            }
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    /// The shipped specification, so a sentence in a test reads the same
    /// vocabulary an author's file does.
    fn spec() -> Schema {
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        let schema = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
        assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
        schema
    }

    fn check(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("w.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        nothing_points_at_it(&node, &spec(), &mut d);
        d
    }

    #[test]
    fn a_policy_no_agent_points_at_is_a_gate_that_does_not_exist() {
        let d = check(
            "agents:\n  desk:\n    description: x\npolicies:\n  approvals:\n    ask-a-person: []\n",
        );
        let e = d.items().first().expect("an unattached gate must be said out loud");
        assert_eq!(e.rule, "loader/nothing-points-at-it");
        assert!(e.message.contains("approvals"), "{}", e.message);
        assert!(e.fix.contains("`policy: approvals`"), "the line to type: {}", e.fix);
        assert_eq!(e.severity, pact_diag::Severity::Warning, "the tree still runs");
    }

    #[test]
    fn a_policy_an_agent_does_point_at_is_left_alone() {
        let d = check(
            "agents:\n  desk:\n    policy: approvals\npolicies:\n  approvals:\n    ask-a-person: []\n",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_tool_reached_through_an_action_name_counts_as_named() {
        // `zendesk/reply` in an approval rule names `zendesk`.
        let d = check(
            "agents:\n  desk:\n    description: x\ntools:\n  zendesk:\n    description: y\n\
             policies:\n  p:\n    ask-a-person:\n      - when:\n          - { tool: zendesk/reply }\n",
        );
        let named: Vec<&str> = d.items().iter().map(|i| i.message.as_str()).collect();
        assert!(!named.iter().any(|m| m.contains("'zendesk'")), "{named:?}");
    }

    #[test]
    fn a_skill_nothing_lists_is_not_warned_about() {
        // A written procedure reads perfectly well on its own, and warning would
        // make writing one before the agent that uses it an error-shaped event.
        let d = check("agents:\n  desk:\n    description: x\nskills:\n  refund-policy: {}\n");
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn every_collection_a_line_can_name_is_warned_about_or_excused() {
        // The B15 property, for the last of the four tables. `KINDS` carries
        // prose a schema cannot generate — what one of these IS, and the line
        // an author types to attach one — so it stays written down. What must
        // not stay written down is the SET: a collection something can name and
        // this file has never heard of is exactly the shape the other three
        // tables shipped, where two rows named fields no group has and nothing
        // failed because a name in Rust was held against nothing.
        //
        // Mutation: delete the `resources` entry from `KINDS`. It has an
        // inbound edge (`tool.connect`) and no excuse, so this turns red.
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        let schema = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
        assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());

        let workspace = schema.group("workspace").expect("a workspace kind");
        let collections: BTreeSet<&str> = workspace
            .fields
            .iter()
            .filter(|f| {
                matches!(&f.ty, pact_schema::Ty::MapOf(inner)
                    if matches!(inner.as_ref(), pact_schema::Ty::Group(_)))
            })
            .map(|f| f.name.as_str())
            .collect();

        // A collection something can name: some field of some kind resolves
        // into it. One with no inbound edge at all cannot be pointed at, so
        // "nothing points at it" is not a thing that can be said about it.
        let mut nameable: BTreeSet<&str> = BTreeSet::new();
        for group in schema.groups() {
            for field in &group.fields {
                for target in &field.names {
                    if let Some(c) = collections.get(target.as_str()) {
                        nameable.insert(c);
                    }
                }
            }
        }

        let known: BTreeSet<&str> = KINDS
            .iter()
            .map(|k| k.section)
            .chain(OMITTED.iter().map(|(s, _)| *s))
            .collect();
        let unaccounted: Vec<&str> = nameable.difference(&known).copied().collect();
        assert!(
            unaccounted.is_empty(),
            "{unaccounted:?} can be named by a line in the tree and this file neither \
             warns about them nor says why not. Add a `Kind` row, or an `OMITTED` entry \
             with the reason."
        );

        // And the other direction: an excuse for something that is not a
        // collection is an excuse nothing needs, which is how a table starts
        // carrying names that mean nothing.
        for (section, reason) in OMITTED {
            assert!(
                collections.contains(section),
                "`{section}` is excused from this check and is not a workspace collection"
            );
            assert!(reason.len() > 20, "`{section}` is excused with no real reason");
        }
        for kind in KINDS {
            assert!(
                collections.contains(kind.section),
                "`{}` is checked and is not a workspace collection",
                kind.section
            );
        }
    }
}
