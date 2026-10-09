//! A bundle contributes only what it said it would (G10).
//!
//! Eve's `defineExtension` packages tools, connections, skills, instruction
//! fragments and hooks as one installable npm unit — its one real sharing
//! mechanism. Mounting one runs a build, and through `instructions.ts` that
//! build executes author code, which R5 and R42 refuse. A PACT bundle is a
//! folder of definitions the same loader reads, so the cost of mounting one is
//! reading files.
//!
//! # The rule this file holds
//!
//! `brings:` is a declaration of scope, and a declaration nobody checks is a
//! comment. The hazard is specific and it is a supply-chain one: a workspace
//! mounts `@acme/crm` for its tools, version 2.1 quietly starts shipping an
//! `interceptors/` folder, and now a third party's rule can stop the run or
//! redirect it. Nothing in the workspace changed, nobody approved anything, and
//! the diff that did it is in somebody else's repository.
//!
//! So a bundle contributing a kind outside its `brings:` is an **error**, not a
//! warning: unlike a half-written tree, there is no legitimate in-progress state
//! where this is what the author meant.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use pact_schema::{Schema, Ty};

/// Every kind a bundle could contribute — read from the schema, not restated.
///
/// This was eight names in Rust, and `bundle.brings`'s `choices:` were eight
/// names in YAML, and they agreed with each other and with nothing else: both
/// said `watches`, and the workspace collection is `watch`. Two copies of one
/// mistake read as confirmation, which is the whole argument for having one.
///
/// The cost was not a refused `brings: [watches]`. It was the `continue` below:
/// a kind absent from the list was skipped in SILENCE, so `brings:` governed a
/// spelling no tree can produce while `agents:`, `ports:`, `context-policies:`,
/// `bundles:` and the real `watch:` passed unchecked — and a bundle that quietly
/// adds an agent adds something that can act.
fn contributable(schema: &Schema) -> Vec<String> {
    schema
        .group("bundle")
        .and_then(|g| g.fields.iter().find(|f| f.name == "brings"))
        .map(|f| match &f.ty {
            Ty::ListOf(inner) => match inner.as_ref() {
                Ty::OneOf(v) => v.clone(),
                _ => Vec::new(),
            },
            Ty::OneOf(v) => v.clone(),
            _ => Vec::new(),
        })
        .unwrap_or_default()
}

/// Which kinds carry a power a workspace should have to opt into by name.
///
/// Reported specially because "your bundle also brought approval rules" is a
/// different sentence from "your bundle also brought a tool": one changes what
/// the agent can do, the other changes what is allowed to stop it.
const GOVERNING: &[&str] = &["policies", "interceptors", "questions"];

/// Hold every mounted bundle against what it said it brings.
pub fn a_bundle_brings_only_what_it_said(root: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let Some(top) = root.as_map() else { return };
    let contributable = contributable(schema);
    let Some(bundles) = top.get("bundles").and_then(|e| e.node.as_map()) else {
        return;
    };

    for (name, entry) in bundles.iter() {
        let Some(b) = entry.node.as_map() else {
            continue;
        };
        let allowed = declared(b);
        let Some(brought) = b.get("contributes").and_then(|e| e.node.as_map()) else {
            // NOTHING MOUNTED, and until this arm said so the author heard
            // nothing at all. `from:` is `required: yes` and no pass in this
            // loader resolves it — so a workspace could declare three bundles,
            // load cleanly, and contain not one definition from any of them.
            // That is the defect this project produces most: a line that
            // validates and does nothing.
            //
            // A WARNING and not an error. The field's own help says `from:` may
            // be *"a path inside this workspace, or a name your platform team
            // publishes"*, and the second kind is resolved by a host that knows
            // its registry. Refusing outright would break the case the field was
            // written for; saying nothing misleads the case it was not.
            let where_from = b
                .get("from")
                .and_then(|e| e.node.as_str())
                .unwrap_or("(nowhere)")
                .to_string();
            diags.push(Diagnostic::warning(
                "loader/bundle-not-mounted",
                entry.key_span.clone(),
                format!(
                    "the bundle '{name}' names `from: {where_from}` and nothing here \
                     mounted it, so none of its definitions are in this workspace."
                ),
                format!(
                    "Nothing to type if the system running this resolves '{name}' \
                     itself. Otherwise copy what it defines into this tree — a \
                     bundle is a folder of the same documents, so mounting one \
                     costs reading files and nothing else."
                ),
            ));
            continue;
        };

        // A pattern a bundle contributes is held to its own declarations, as a
        // pattern in a workspace is (`derive::resolve`): it is a way of making a
        // document, so a hole is right in it and a hole nothing declares is not.
        for (kind, documents) in brought {
            let Some(documents) = documents.node.as_map() else { continue };
            for (doc, written) in documents {
                if crate::templates::is_a_pattern(&written.node)
                    && let Err(d) = crate::templates::holes_match_declarations(
                        &format!("{kind}/{doc}"),
                        &written.node,
                    )
                {
                    diags.push(*d);
                }
            }
        }

        for kind in brought.keys() {
            if !contributable.iter().any(|c| c == kind) {
                // NOT skipped. This `continue` used to be unconditional for
                // anything off an eight-name list, which is how `agents:` — the
                // one contribution that adds something able to act — passed
                // through a check whose whole purpose is to hold a bundle to
                // what it declared.
                //
                // Now the list is every collection a workspace can hold, so a
                // kind that is not on it is not an unlisted collection: it is
                // not a kind of document PACT has. Saying so is the difference
                // between a bundle that brings nothing and a bundle whose
                // contribution nobody reads.
                let span = brought
                    .get(kind)
                    .map(|e| e.node.span.clone())
                    .unwrap_or_else(|| entry.node.span.clone());
                diags.push(Diagnostic::error(
                    "loader/bundle-brings-an-unknown-kind",
                    span,
                    format!(
                        "the bundle '{name}' contributes `{kind}:`, and there is no such kind \
                         of document. Nothing here reads it."
                    ),
                    format!(
                        "Take `{kind}:` out of what '{name}' contributes, or take it up with \
                         whoever publishes '{name}'. What a bundle may contribute is: {}.",
                        contributable.join(", ")
                    ),
                ));
                continue;
            }
            if allowed.iter().any(|a| a == kind) {
                continue;
            }
            let span = brought
                .get(kind)
                .map(|e| e.node.span.clone())
                .unwrap_or_else(|| entry.node.span.clone());
            let extra = if GOVERNING.contains(&kind.as_str()) {
                format!(
                    " `{kind}` can change or stop what a run does, so a bundle supplying it is a \
                     decision somebody here has to make."
                )
            } else {
                String::new()
            };
            diags.push(Diagnostic::error(
                "loader/bundle-brings-more-than-it-said",
                span,
                format!(
                    "the bundle '{name}' contributes `{kind}:`, which is not in its `brings:` \
                     line.{extra}"
                ),
                format!(
                    "Add `{kind}` to `brings:` on '{name}' if you want it, or take it up with \
                     whoever publishes '{name}'. Until then nothing it defines under `{kind}:` is \
                     used."
                ),
            ));
        }
    }
}

fn declared(bundle: &pact_doc::Map) -> Vec<String> {
    match bundle.get("brings").map(|e| &e.node.value) {
        Some(pact_doc::Value::List(items)) => items
            .iter()
            .filter_map(|n| n.as_str().map(str::to_owned))
            .collect(),
        Some(pact_doc::Value::Str(s)) => vec![s.clone()],
        _ => Vec::new(),
    }
}

#[cfg(test)]
mod tests {

    /// The shipped specification, which is where `brings:` states its kinds.
    fn spec() -> Schema {
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
        assert!(
            !d.has_errors(),
            "the shipped specification does not load:\n{}",
            d.render()
        );
        s
    }
    use super::*;
    use pact_diag::Span;
    use pact_doc::{Entry, Map, Value};

    fn span() -> Span {
        Span::whole_file(camino::Utf8Path::new("bundle-test.yaml"))
    }

    fn e(node: Node) -> Entry {
        Entry {
            key_span: span(),
            node,
        }
    }

    fn s(v: &str) -> Node {
        Node::new(Value::Str(v.to_owned()), span())
    }

    fn list(vs: &[&str]) -> Node {
        Node::new(Value::List(vs.iter().map(|v| s(v)).collect()), span())
    }

    fn map(pairs: Vec<(&str, Node)>) -> Node {
        let mut m = Map::new();
        for (k, v) in pairs {
            m.insert(k.to_owned(), e(v));
        }
        Node::new(Value::Map(m), span())
    }

    fn tree(brings: &[&str], contributes: Vec<(&str, Node)>) -> Node {
        map(vec![(
            "bundles",
            map(vec![(
                "acme-crm",
                map(vec![
                    ("brings", list(brings)),
                    ("contributes", map(contributes)),
                ]),
            )]),
        )])
    }

    #[test]
    fn a_bundle_that_brings_what_it_said_is_silent() {
        let root = tree(
            &["tools", "skills"],
            vec![("tools", map(vec![("search", s("x"))]))],
        );
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&root, &spec(), &mut d);
        assert_eq!(d.items().len(), 0);
    }

    /// Superseded as the only witness by
    /// `tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs::
    /// a_folder_a_bundle_never_said_it_would_bring_is_refused_from_a_real_tree`,
    /// which reaches this branch by creating
    /// `bundles/customer-lookup/contributes/policies/` on disk — which is how
    /// the supply-chain case actually happens. Kept: it pins the wording.
    #[test]
    fn a_bundle_that_starts_shipping_approval_rules_is_refused() {
        // The supply-chain case: version 2.1 adds `policies/` and nothing in
        // this workspace changed.
        let root = tree(&["tools"], vec![("policies", map(vec![("gate", s("x"))]))]);
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&root, &spec(), &mut d);
        let x = d.items().first().expect("must refuse");
        assert_eq!(x.rule, "loader/bundle-brings-more-than-it-said");
        assert!(
            x.message.contains("change or stop what a run does"),
            "{}",
            x.message
        );
    }

    #[test]
    fn it_is_an_error_because_there_is_no_half_written_state_that_looks_like_this() {
        let root = tree(&["tools"], vec![("interceptors", map(vec![("r", s("x"))]))]);
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&root, &spec(), &mut d);
        assert!(d.has_errors());
    }

    /// The negative half of the governance sentence: `tools` is not on
    /// `GOVERNING`, so no *"can change or stop what a run does"* is added. The
    /// positive half is folder-witnessed in
    /// `tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs::
    /// a_folder_a_bundle_never_said_it_would_bring_is_refused_from_a_real_tree`;
    /// this stays hand-built because the pair is what makes either meaningful
    /// and a tree cannot hold both cases at once without two bundles.
    #[test]
    fn an_ordinary_extra_kind_is_refused_without_the_governance_sentence() {
        let root = tree(&["skills"], vec![("tools", map(vec![("t", s("x"))]))]);
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&root, &spec(), &mut d);
        let x = d.items().first().expect("must refuse");
        assert!(!x.message.contains("change or stop"), "{}", x.message);
        assert!(x.fix.contains("Add `tools` to `brings:`"), "{}", x.fix);
    }

    #[test]
    fn a_bundle_with_nothing_mounted_yet_is_not_accused_of_anything() {
        let root = map(vec![(
            "bundles",
            map(vec![("acme-crm", map(vec![("brings", list(&["tools"]))]))]),
        )]);
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&root, &spec(), &mut d);
        // NOT ACCUSED — no `brings:` violation, which is what this test is about.
        // It used to assert `len() == 0`, which conflated *not accused* with
        // *told nothing*: an unmounted bundle now gets an informational warning
        // saying none of its definitions are in the workspace, because before
        // that the author heard nothing at all about a `from:` line no pass in
        // this loader resolves.
        assert!(!d.has_errors(), "{}", d.render());
        assert!(
            !d.items()
                .iter()
                .any(|x| x.rule == "loader/bundle-brings-more-than-it-said"),
            "{}",
            d.render()
        );
    }

    /// A bundle that declares `brings:` and contributes `contributes:`.
    fn mounted(from: &str, brings: &[&str], contributes: &[&str]) -> Node {
        map(vec![(
            "bundles",
            map(vec![(
                "acme-crm",
                map(vec![
                    ("brings", list(brings)),
                    ("from", s(from)),
                    (
                        "contributes",
                        map(contributes.iter().map(|k| (*k, map(vec![]))).collect()),
                    ),
                ]),
            )]),
        )])
    }

    /// A bundle with no `contributes:` is one nothing mounted.
    fn unmounted(from: &str) -> Node {
        map(vec![(
            "bundles",
            map(vec![(
                "acme-crm",
                map(vec![("brings", list(&["tools"])), ("from", s(from))]),
            )]),
        )])
    }

    /// Superseded as the only witness by
    /// `tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs::
    /// the_bundle_whose_folder_is_not_here_is_named_and_so_is_where_it_said_to_look`,
    /// which asserts the same words against `tests/trees/what-a-bundle-brings/`
    /// read off disk by the real loader. Kept, because it runs in microseconds
    /// and pins the wording where the wording is written.
    #[test]
    fn a_bundle_nothing_mounted_is_said_out_loud() {
        // `from:` is `required: yes` and no pass in this loader resolves it, so
        // a workspace could declare three bundles, load cleanly, and contain not
        // one definition from any of them. The author heard nothing.
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&unmounted("/platform/tools"), &spec(), &mut d);
        let said = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/bundle-not-mounted")
            .expect("an unmounted bundle must be reported");
        assert!(said.message.contains("acme-crm"), "{}", said.message);
        assert!(said.message.contains("/platform/tools"), "{}", said.message);
        assert!(
            said.message
                .contains("none of its definitions are in this workspace"),
            "{}",
            said.message
        );
    }

    /// Superseded as the only witness by
    /// `tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs::
    /// a_name_a_platform_team_publishes_is_a_warning_and_never_a_refusal`, which
    /// makes the claim against a tree writing BOTH kinds of `from:` — a path in
    /// the workspace and a registry name — which is the case this argument is
    /// about and which one hand-built bundle cannot show.
    #[test]
    fn an_unmounted_bundle_is_a_warning_and_not_a_refusal() {
        // The field's own help says `from:` may be "a path inside this
        // workspace, or a name your platform team publishes" — and the second
        // kind is resolved by a host that knows its registry. Refusing outright
        // would break the case the field was written for.
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&unmounted("acme/crm"), &spec(), &mut d);
        assert!(!d.has_errors(), "{}", d.render());
        assert_eq!(d.items().len(), 1, "{}", d.render());
    }

    /// Superseded as the only witness by
    /// `tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs::
    /// the_bundle_whose_folder_is_here_is_not_told_it_is_missing`, which puts a
    /// mounted and an unmounted bundle in ONE tree — so a check that had learned
    /// to warn about every `bundles:` entry, or about none, fails there and
    /// passes here.
    #[test]
    fn a_bundle_that_did_mount_is_not_told_it_did_not() {
        // The scope check is what runs once the contents are in the tree, and
        // this warning must not fire alongside it — an author who mounted a
        // bundle correctly being told it was not mounted is worse than silence.
        let root = tree(&["tools"], vec![("tools", map(vec![("search", s("x"))]))]);
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&root, &spec(), &mut d);
        assert!(
            !d.items()
                .iter()
                .any(|x| x.rule == "loader/bundle-not-mounted"),
            "{}",
            d.render()
        );
    }

    #[test]
    fn what_a_bundle_may_bring_is_what_a_workspace_can_hold() {
        // `brings:` and this file each carried eight hand-written names, and
        // they agreed with each other and with nothing else — both said
        // `watches`, and the workspace collection is `watch`. Two copies of one
        // mistake read as confirmation.
        //
        // The cost was the silent `continue`: a kind absent from the list was
        // skipped rather than refused, so `brings:` governed a spelling no tree
        // can produce and was blind to `agents:` — the one kind whose arrival
        // adds something that can act.
        //
        // Mutation: drop `agents` from the `choices:` in `spec/schema.yaml`.
        let schema = spec();
        let workspace = schema.group("workspace").expect("a workspace kind");
        let collections: Vec<&str> = workspace
            .fields
            .iter()
            // A map of named entries: documents (`map of group:<kind>`) or named
            // shapes (`map of map of answer-shape`, 02W §2.1).
            .filter(|f| matches!(&f.ty, Ty::MapOf(inner) if matches!(inner.as_ref(), Ty::Group(_) | Ty::MapOf(_))))
            .map(|f| f.name.as_str())
            .collect();
        let mut brings = contributable(&schema);
        brings.sort();
        let mut want: Vec<String> = collections.iter().map(|s| (*s).to_owned()).collect();
        want.sort();
        assert_eq!(
            brings, want,
            "`bundle.brings` and the workspace's own collections have drifted apart"
        );
    }

    /// Superseded as the only witness by
    /// `tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs::
    /// a_folder_naming_no_kind_of_document_pact_has_is_refused_from_a_real_tree`.
    /// This map holds the key `gizmos` because the test typed it; there the key
    /// exists only because the loader turned a directory name into one, so if
    /// the loader ever started filtering directory names on the way in, this
    /// test would keep passing over a branch nothing could reach.
    #[test]
    fn a_contributed_kind_the_schema_does_not_know_is_refused_and_not_skipped() {
        // The silent `continue`. A bundle contributing something PACT has no
        // kind for used to pass in total silence, because the check only looked
        // at an eight-name list and skipped everything else — so the louder the
        // mistake, the quieter the checker.
        //
        // Mutation: turn the new arm back into a bare `continue`.
        let root = mounted("acme/crm", &["tools"], &["tools", "gizmos"]);
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&root, &spec(), &mut d);
        let hit = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/bundle-brings-an-unknown-kind")
            .expect("an unknown kind must be refused rather than skipped");
        assert!(hit.message.contains("gizmos"), "{}", hit.message);
        assert!(
            hit.fix.contains("tools"),
            "the fix lists what is allowed: {}",
            hit.fix
        );
    }

    /// The `agents` case specifically. The *rule* is superseded as a
    /// folder-witnessed claim by
    /// `tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs::
    /// a_folder_a_bundle_never_said_it_would_bring_is_refused_from_a_real_tree`
    /// (which uses `policies/`); this one stays the only witness that the kind
    /// the check was once blind to is among the kinds it now refuses, and that
    /// is worth a hand-built map rather than a second copy of the tree.
    #[test]
    fn a_bundle_that_quietly_starts_supplying_an_agent_is_refused() {
        // `agents` was absent from both eight-name lists, so this — the
        // contribution that adds something which can act on its own — was the
        // one the check was blind to.
        let root = mounted("acme/crm", &["tools"], &["tools", "agents"]);
        let mut d = Diagnostics::new();
        a_bundle_brings_only_what_it_said(&root, &spec(), &mut d);
        let hit = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/bundle-brings-more-than-it-said")
            .expect("an undeclared agent must be refused");
        assert!(hit.message.contains("agents"), "{}", hit.message);
    }
}
