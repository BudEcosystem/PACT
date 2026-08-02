//! `available-when:` — a capability offered only once its condition holds (G12).
//!
//! Eve computes this and cannot express it. Its harness offers `agent` only in
//! the root session, `load_skill` only when the agent declares skills,
//! `connection_search` only when it declares connections, and `ask_question`
//! only when the session can reach a person
//! (`docs/concepts/default-harness.md`, which says the set "depends on the
//! agent and session"). Four conditions, hardcoded, none writable — so the fifth
//! condition, whatever a particular author needs, has nowhere to go.
//!
//! # What this file holds
//!
//! The schema says the condition is one of a closed list. It cannot say whether
//! the agent that names the capability actually satisfies it, because that is a
//! fact about a different document. **A capability whose condition can never
//! hold is worse than a missing one**: it loads, it reads as configured, and it
//! is silently never offered — so an author debugging "why did the model never
//! call this" has nothing to go on. That is what is refused here.
//!
//! It is a warning rather than an error on purpose. A workspace under
//! construction legitimately has an agent with no teammates yet and a tool that
//! will need them; failing the build on a half-written tree teaches people to
//! reach for the flag that turns checking off.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use pact_schema::{Schema, Ty};
use std::collections::{BTreeMap, BTreeSet};

/// Which workspace collection holds which kind — `tools` -> `tool`.
///
/// Computed from the workspace's own fields rather than written down: a
/// collection is any workspace field typed `map of group:<kind>`. The list this
/// replaces was three rows of hand-written pairs, two of which named a field the
/// `agent` group does not have.
fn collections(schema: &Schema) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    let Some(workspace) = schema.group("workspace") else { return out };
    for f in &workspace.fields {
        if let Ty::MapOf(inner) = &f.ty
            && let Ty::Group(kind) = inner.as_ref()
        {
            out.insert(f.name.clone(), kind.clone());
        }
    }
    out
}

/// Every collection this agent can get to something in, following the schema's
/// own `names:` edges as far as they go.
///
/// One walk, because there is one question. `uses:` reaches a tool or a skill
/// directly; a resource is reached only through a tool's `connect:`; a question
/// only through `limits.asks`, a group nested inside the agent. A table of
/// direct pairs could express the first and never the other two, which is why
/// the row for `resources` named a field that does not exist.
fn collections_the_agent_reaches(
    top: &pact_doc::Map,
    schema: &Schema,
    agent: &Node,
) -> BTreeSet<String> {
    let cols = collections(schema);
    let mut reached: BTreeSet<String> = BTreeSet::new();
    let mut seen: BTreeSet<(String, String)> = BTreeSet::new();
    let mut queue: Vec<(String, Node)> = vec![("agent".to_owned(), agent.clone())];

    while let Some((kind, node)) = queue.pop() {
        let Some(group) = schema.group(&kind) else { continue };
        let Some(here) = node.as_map() else { continue };
        for field in &group.fields {
            let Some(entry) = here.get(&field.name) else { continue };
            // A block of settings nested in this one — `agent.limits` holds
            // `asks:`, and that is the only path from an agent to a question.
            if let Ty::Group(inner) = &field.ty {
                queue.push((inner.clone(), entry.node.clone()));
            }
            for target in &field.names {
                // `^steps` is a sibling inside one document and `pact:models` is
                // supplied by the build; neither is a workspace collection.
                if target.starts_with('^') || target.contains(':') {
                    continue;
                }
                let Some(kind_of) = cols.get(target) else { continue };
                let Some(defs) = top.get(target).and_then(|e| e.node.as_map()) else { continue };
                for name in written_names(&entry.node) {
                    let Some(def) = defs.get(&name) else { continue };
                    reached.insert(target.clone());
                    if seen.insert((target.clone(), name.clone())) {
                        queue.push((kind_of.clone(), def.node.clone()));
                    }
                }
            }
        }
    }
    reached
}

/// Every capability an agent names must be one its own declarations can reach.
pub fn nothing_waits_on_a_condition_that_cannot_hold(
    root: &Node,
    schema: &Schema,
    diags: &mut Diagnostics,
) {
    let Some(top) = root.as_map() else { return };
    let Some(agents) = top.get("agents").and_then(|e| e.node.as_map()) else { return };
    let cols = collections(schema);

    for (agent_name, agent) in agents.iter() {
        let Some(a) = agent.node.as_map() else { continue };
        let reaches = collections_the_agent_reaches(top, schema, &agent.node);

        for (collection, kind) in &cols {
            let Some(group) = schema.group(kind) else { continue };
            let Some(field) = group.fields.iter().find(|f| f.name == "available-when") else {
                continue;
            };
            if !reaches.contains(collection) {
                continue;
            }
            let Some(defs) = top.get(collection).and_then(|e| e.node.as_map()) else { continue };
            for (used, def_entry) in defs.iter() {
                let Some(def) = def_entry.node.as_map() else { continue };
                let Some(cond) = def.get("available-when").and_then(|e| e.node.as_str()) else {
                    continue;
                };
                let cond = cond.trim();
                let Some((_, target)) =
                    field.satisfied_by.iter().find(|(value, _)| value == cond)
                else {
                    continue; // `always`, or a value the schema has already refused
                };
                if is_satisfied(a, &reaches, target) {
                    continue;
                }
                // The two shapes a target can have, and the fix has to name the
                // one an author can actually type. R24: a warning whose fix is
                // refused when typed is worse than no warning, and that is what
                // this printed for two of its three conditions.
                let (says, fix) = if schema
                    .group("agent")
                    .is_some_and(|g| g.fields.iter().any(|f| f.name == *target))
                {
                    (
                        format!("declares no `{target}:`"),
                        format!("Add `{target}:` to '{agent_name}'"),
                    )
                } else {
                    (
                        format!("cannot get to anything under `{target}:`"),
                        format!(
                            "Give '{agent_name}' something from `{target}:` — for a skill or a \
                             tool that is a name on its `uses:` line"
                        ),
                    )
                };
                diags.push(Diagnostic::warning(
                    "loader/never-offered",
                    def.get("available-when")
                        .map(|e| e.node.span.clone())
                        .unwrap_or_else(|| agent.node.span.clone()),
                    format!(
                        "'{agent_name}' can reach '{used}', which is only offered when \
                         `{cond}` — and '{agent_name}' {says}. The model is never shown it."
                    ),
                    format!(
                        "{fix}, or take '{used}' off its list, or remove the `available-when:` \
                         line from '{used}' if it should always be offered."
                    ),
                ));
            }
        }
    }
}

/// A target names either a field the agent itself has, or a collection it has
/// to be able to reach. One question asked two ways round, not two mechanisms.
fn is_satisfied(agent: &pact_doc::Map, reaches: &BTreeSet<String>, target: &str) -> bool {
    has_something_under(agent, target) || reaches.contains(target)
}

fn written_names(node: &Node) -> Vec<String> {
    match &node.value {
        pact_doc::Value::List(items) => {
            items.iter().filter_map(|n| n.as_str().map(str::trim).map(str::to_owned)).collect()
        }
        pact_doc::Value::Map(m) => m.keys().cloned().collect(),
        pact_doc::Value::Str(s) => vec![s.trim().to_owned()],
        _ => Vec::new(),
    }
}

fn has_something_under(agent: &pact_doc::Map, field: &str) -> bool {
    match agent.get(field).map(|e| &e.node.value) {
        Some(pact_doc::Value::List(items)) => !items.is_empty(),
        Some(pact_doc::Value::Map(m)) => !m.is_empty(),
        Some(pact_doc::Value::Str(s)) => !s.trim().is_empty(),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_diag::Span;
    use pact_doc::{Entry, Map, Value};

    fn span() -> Span {
        Span::whole_file(camino::Utf8Path::new("available-test.yaml"))
    }

    fn e(node: Node) -> Entry {
        Entry { key_span: span(), node }
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

    /// The shipped specification, which is where `satisfied-by:` now lives.
    ///
    /// These tests used to need no schema, and that was the defect: the table
    /// they exercised was three rows of Rust that nothing held against the
    /// `agent` group, so two of them could name a field no agent has and every
    /// test here still passed.
    fn spec() -> Schema {
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
        assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
        s
    }

    fn tree(agent: Node, tools: Node) -> Node {
        map(vec![
            ("agents", map(vec![("desk", agent)])),
            ("tools", tools),
        ])
    }

    #[test]
    fn a_capability_whose_condition_the_agent_cannot_meet_is_named() {
        let root = tree(
            map(vec![("uses", list(&["hand-over"]))]),
            map(vec![(
                "hand-over",
                map(vec![("available-when", s("this-agent-has-helpers"))]),
            )]),
        );
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        let w = d.items().first().expect("must warn");
        assert_eq!(w.rule, "loader/never-offered");
        assert!(w.message.contains("never shown it"), "{}", w.message);
        assert!(w.fix.contains("`team:`"), "the fix names the field: {}", w.fix);
    }

    #[test]
    fn the_same_capability_is_silent_once_the_agent_has_what_it_needs() {
        let root = tree(
            map(vec![
                ("uses", list(&["hand-over"])),
                ("team", map(vec![("checker", s("checks things"))])),
            ]),
            map(vec![(
                "hand-over",
                map(vec![("available-when", s("this-agent-has-helpers"))]),
            )]),
        );
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        assert_eq!(d.items().len(), 0, "{:?}", d.items().first().map(|x| &x.message));
    }

    #[test]
    fn a_capability_with_no_condition_is_never_questioned() {
        let root = tree(
            map(vec![("uses", list(&["payments"]))]),
            map(vec![("payments", map(vec![("description", s("pays"))]))]),
        );
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        assert_eq!(d.items().len(), 0);
    }

    #[test]
    fn an_empty_team_counts_as_no_team_rather_than_as_one() {
        // `team: {}` is how a half-written agent looks, and it is exactly the
        // case where the model would be offered a tool that cannot work.
        let root = tree(
            map(vec![("uses", list(&["hand-over"])), ("team", map(vec![]))]),
            map(vec![(
                "hand-over",
                map(vec![("available-when", s("this-agent-has-helpers"))]),
            )]),
        );
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        assert_eq!(d.items().len(), 1);
    }

    #[test]
    fn it_warns_rather_than_errors_so_a_half_written_tree_still_checks() {
        let root = tree(
            map(vec![("uses", list(&["hand-over"]))]),
            map(vec![(
                "hand-over",
                map(vec![("available-when", s("this-agent-has-helpers"))]),
            )]),
        );
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        assert!(!d.has_errors(), "a tree under construction must still check");
    }

    /// A general tree, so a test can put entries in any collection.
    fn workspace(pairs: Vec<(&str, Node)>) -> Node {
        map(pairs)
    }

    #[test]
    fn a_skill_whose_condition_cannot_hold_is_named_too() {
        // The iteration read `("skills", "knows")` and no agent has `knows:`,
        // so a skill's `available-when:` was never looked at. Every assertion in
        // this file passed while one of the three kinds that carries the field
        // was not checked at all.
        let root = workspace(vec![
            ("agents", map(vec![("desk", map(vec![("uses", list(&["refunds"]))]))])),
            (
                "skills",
                map(vec![("refunds", map(vec![("available-when", s("this-agent-has-helpers"))]))]),
            ),
        ]);
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        let w = d.items().first().expect("a skill's condition must be checked");
        assert_eq!(w.rule, "loader/never-offered");
        assert!(w.message.contains("refunds"), "{}", w.message);
    }

    #[test]
    fn the_fix_a_never_offered_warning_offers_is_a_line_an_agent_can_have() {
        // R24, and the reason this whole attribute exists. The table said
        // `this-agent-has-procedures` was satisfied by a field called `skills`,
        // so the warning told the author to "Add `skills:`" — and typing that
        // gave `error: 'skills' is not something an agent can have`. Every
        // target now has to be a field the agent group really has, or a
        // collection the agent can really reach.
        let schema = spec();
        let agent_fields: Vec<&str> =
            schema.group("agent").unwrap().fields.iter().map(|f| f.name.as_str()).collect();
        let sat = schema
            .group("tool")
            .unwrap()
            .fields
            .iter()
            .find(|f| f.name == "available-when")
            .expect("tools carry the condition")
            .satisfied_by
            .clone();
        assert!(!sat.is_empty(), "the conditions must say what satisfies them");
        for (condition, target) in sat {
            let is_agent_field = agent_fields.contains(&target.as_str());
            let is_collection = collections(&schema).contains_key(&target);
            assert!(
                is_agent_field || is_collection,
                "`{condition}` is satisfied by `{target}`, which is neither a field an \
                 agent can have nor a collection it can reach — so the fix this warning \
                 offers is refused when typed"
            );
        }
    }

    #[test]
    fn a_resource_an_agent_reaches_only_through_a_tool_satisfies_the_condition() {
        // Nothing an agent writes names a resource: the only edge is a tool's
        // `connect:`. A table of direct (collection, agent-field) pairs cannot
        // say this, which is why its row named `resources` as a field of the
        // agent group and the condition could never hold.
        let root = workspace(vec![
            ("agents", map(vec![("desk", map(vec![("uses", list(&["search", "lookup"]))]))])),
            (
                "tools",
                map(vec![
                    ("search", map(vec![("connect", s("company-wiki"))])),
                    ("lookup", map(vec![("available-when", s("this-agent-has-connections"))])),
                ]),
            ),
            ("resources", map(vec![("company-wiki", map(vec![("description", s("the wiki"))]))])),
        ]);
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        assert_eq!(
            d.items().len(),
            0,
            "the agent reaches a resource through `search`: {:?}",
            d.items().first().map(|x| &x.message)
        );
    }

    #[test]
    fn an_agent_with_no_connection_at_all_is_still_told() {
        let root = workspace(vec![
            ("agents", map(vec![("desk", map(vec![("uses", list(&["lookup"]))]))])),
            (
                "tools",
                map(vec![("lookup", map(vec![("available-when", s("this-agent-has-connections"))]))]),
            ),
        ]);
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        let w = d.items().first().expect("must warn");
        assert_eq!(w.rule, "loader/never-offered");
        assert!(w.fix.contains("resources"), "the fix names what is missing: {}", w.fix);
    }

    #[test]
    fn a_condition_about_asking_a_person_is_checked_rather_than_skipped() {
        // `a-person-can-be-asked` is one of the five choices and had no row in
        // the table, so it fell through the `continue` marked "a value the
        // schema has already refused" — which the schema does not refuse. A
        // legal value that no check can see is R24's defect inside the check
        // that exists to catch it.
        let root = workspace(vec![
            ("agents", map(vec![("desk", map(vec![("uses", list(&["escalate"]))]))])),
            (
                "tools",
                map(vec![("escalate", map(vec![("available-when", s("a-person-can-be-asked"))]))]),
            ),
        ]);
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        assert_eq!(d.items().len(), 1, "an unaskable person must be reported");
        assert_eq!(d.items()[0].rule, "loader/never-offered");
    }

    #[test]
    fn an_agent_that_can_reach_a_question_satisfies_it() {
        let root = workspace(vec![
            (
                "agents",
                map(vec![(
                    "desk",
                    map(vec![
                        ("uses", list(&["escalate"])),
                        ("limits", map(vec![("asks", s("is-this-ok"))])),
                    ]),
                )]),
            ),
            (
                "tools",
                map(vec![("escalate", map(vec![("available-when", s("a-person-can-be-asked"))]))]),
            ),
            ("questions", map(vec![("is-this-ok", map(vec![("asks", s("ok?"))]))])),
        ]);
        let mut d = Diagnostics::new();
        nothing_waits_on_a_condition_that_cannot_hold(&root, &spec(), &mut d);
        assert_eq!(
            d.items().len(),
            0,
            "the agent reaches a question through `limits.asks`: {:?}",
            d.items().first().map(|x| &x.message)
        );
    }
}
