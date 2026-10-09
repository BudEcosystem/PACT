//! **What arrives at a port, and which run it reaches** (02W §2.9, §3, §4 R23
//! and R44).
//!
//! A port answers an agent or a workflow. One that answers a workflow fills its
//! `accepts:` from what arrives (same-named fields, and `bind:` for the rest),
//! keys its runs by `same-conversation-when:`, and says what an arrival does
//! while a run with the same key is open, on any kind of port (R44 reopened).
//! An event reaches only a run of the workflow it answers whose key it carries
//! (R23 reopened for workflows). Held here:
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/an-event-the-wait-will-never-hear` | WF-19 | a stage's `heard:` names a port its question is not asked of, or one that does not answer this workflow, does not `join`, or does not share the key of the ports that start its runs; or a question a workflow asks waits for such a port |
//! | `loader/a-key-that-is-not-a-field` | WF-27 | on a port answering a workflow, a `same-conversation-when:` entry is not a field of what arrives |
//! | `loader/overlap-with-no-key` | WF-28 | `if-still-running:` other than `start` on a port that is not a timer and has no `same-conversation-when:` |
//! | `loader/a-port-that-cannot-start-a-run` *(note)* | WF-29 | a port answering a workflow cannot fill its required inputs, so it only joins open runs |
//! | `loader/a-time-with-no-zone` | WF-30 | a timer answering a workflow names a time of day, and neither `in-time-zone:` nor the workspace says which zone |
//! | `loader/a-binding-to-nothing` | WF-4 | a port's `bind:` or `only-when:` reads a field that does not arrive |
//! | `loader/a-call-that-does-not-fit` | WF-39 | a port's `bind:` fills an input its workflow does not take |
//! | `loader/a-workflow-only-spelling` | new | a port answering an agent writes what only a workflow's port reads (`accepts:`, `bind:`, `undo:`, `then-run:`), or `if-still-running: join` (an agent's conversation is joined by no other port: R23 stays refused there) |
//!
//! A port's `only-when:` is held by the one condition reader
//! (`conditions::line`), as an approval rule, a routing rule and an `until:` are.

use crate::bindings::Shapes;
use crate::conditions::{self, Kind, Position};
use crate::waits::{self, Answerer};
use crate::workflows;
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node};
use pact_schema::Schema;
use std::collections::BTreeSet;

/// The choice that hands an arrival to the open run with its key.
const JOIN: &str = "join";
/// The choice that begins another run anyway, the default off a timer.
const START: &str = "start";
/// Lines only a port answering a workflow reads.
const WORKFLOW_PORT_LINES: [&str; 4] = ["accepts", "bind", "undo", "then-run"];

/// One port, read.
struct Port<'a> {
    name: &'a str,
    node: &'a Node,
}

impl<'a> Port<'a> {
    fn text(&self, key: &str) -> Option<&'a str> {
        self.node.get(key).and_then(Node::as_str).map(str::trim)
    }

    fn key(&self) -> BTreeSet<String> {
        self.node
            .get("same-conversation-when")
            .map(workflows::list)
            .unwrap_or_default()
            .into_iter()
            .filter_map(|n| n.as_str().map(|s| s.trim().to_string()))
            .collect()
    }

    fn is_a_timer(&self) -> bool {
        crate::ports::kind_of(self.node).is_schedule()
    }

    fn overlap(&self) -> Option<&'a str> {
        self.text("if-still-running")
    }
}

/// Every port check, over the loaded document.
pub fn check(document: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let shapes = Shapes::of(document, schema);
    let ports = ports_of(document);
    for port in &ports {
        overlap_with_no_key(port, diags);
        let answers = port.text("answers").unwrap_or("");
        match workflows::entry_in(document, "workflows", answers) {
            Some(flow) => a_workflows_port(document, &shapes, port, answers, flow, diags),
            None => an_agents_port(port, diags),
        }
    }
    for (name, entry) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        heard(document, &shapes, &ports, name, &entry.node, diags);
    }
}

fn ports_of(document: &Node) -> Vec<Port<'_>> {
    document
        .get("ports")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .filter(|(_, e)| e.node.get(pact_doc::UNLOADED).is_none())
        .map(|(name, e)| Port {
            name,
            node: &e.node,
        })
        .collect()
}

fn key_span(node: &Node, key: &str) -> Option<Span> {
    node.as_map()
        .and_then(|m| m.get(key))
        .map(|e| e.key_span.clone())
}

fn listed(set: &BTreeSet<String>) -> String {
    set.iter()
        .map(|k| format!("`{k}`"))
        .collect::<Vec<_>>()
        .join(", ")
}

/// WF-28, on every port.
fn overlap_with_no_key(port: &Port, diags: &mut Diagnostics) {
    let Some(choice) = port.overlap() else { return };
    if choice == START || port.is_a_timer() || !port.key().is_empty() {
        return;
    }
    diags.push(Diagnostic::error(
        "loader/overlap-with-no-key",
        key_span(port.node, "if-still-running").unwrap_or_else(|| port.node.span.start_of_block()),
        format!(
            "'{}' says what an arrival does while a run of the same case is open \
             (`if-still-running: {choice}`), and nothing says what makes two arrivals the same \
             case, so every arrival is a case of its own and this never happens.",
            port.name
        ),
        "Say which field makes two arrivals the same case — `same-conversation-when: \
         [invitee-uri]`."
            .to_string(),
    ));
}

/// What a port answering an agent may not write.
fn an_agents_port(port: &Port, diags: &mut Diagnostics) {
    for line in WORKFLOW_PORT_LINES {
        if let Some(at) = key_span(port.node, line) {
            diags.push(Diagnostic::error(
                "loader/a-workflow-only-spelling",
                at,
                format!(
                    "'{}' answers an agent and writes `{line}:`, which only a port answering a \
                     workflow reads: it fills a workflow's inputs or ends one of its runs.",
                    port.name
                ),
                "Delete it, or have the port answer a workflow that calls the agent.".to_string(),
            ));
        }
    }
    if port.overlap() == Some(JOIN) {
        diags.push(Diagnostic::error(
            "loader/a-workflow-only-spelling",
            key_span(port.node, "if-still-running")
                .unwrap_or_else(|| port.node.span.start_of_block()),
            format!(
                "'{}' answers an agent and hands what arrives to the open run \
                 (`if-still-running: join`): an agent's conversation is reached by its own port \
                 only, so no other arrival joins it.",
                port.name
            ),
            "Write `queue`, `skip`, `cancel-previous`, `stop` or `start`, or have the port answer \
             a workflow whose wait hears it."
                .to_string(),
        ));
    }
}

/// What arrives at a port answering a workflow: its `accepts:` when written,
/// a `per-row-of:` table's row, or else the workflow's own `accepts:`.
fn arriving<'a>(document: &'a Node, port: &Port<'a>, flow: &'a Node) -> Option<&'a Map> {
    if let Some(m) = port.node.get("accepts").and_then(Node::as_map) {
        return Some(m);
    }
    if let Some(table) = port.text("per-row-of") {
        let shape = document
            .get("values")
            .and_then(|v| v.get(table))
            .and_then(|t| t.get("rows-are"))
            .and_then(Node::as_str)?;
        return document
            .get("shapes")
            .and_then(|s| s.get(shape.trim()))
            .and_then(Node::as_map);
    }
    if port.is_a_timer() {
        return None;
    }
    flow.get("accepts").and_then(Node::as_map)
}

/// The workflow's inputs a run cannot start without, in written order.
fn required<'a>(shapes: &Shapes, flow: &'a Node) -> Vec<&'a str> {
    flow.get("accepts")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .filter(|(_, e)| shapes.line(&e.node).is_none_or(|l| !l.optional))
        .map(|(k, _)| k.as_str())
        .collect()
}

/// Whether this port can start a run of `flow`: every required input is
/// filled from what arrives, by name or by `bind:`.
fn can_start(document: &Node, shapes: &Shapes, port: &Port, flow: &Node) -> bool {
    missing_inputs(document, shapes, port, flow).is_empty()
}

fn missing_inputs<'a>(
    document: &Node,
    shapes: &Shapes,
    port: &Port,
    flow: &'a Node,
) -> Vec<&'a str> {
    let came: BTreeSet<&str> = arriving(document, port, flow)
        .into_iter()
        .flatten()
        .map(|(k, _)| k.as_str())
        .collect();
    let bound: BTreeSet<&str> = port
        .node
        .get("bind")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .map(|(k, _)| k.as_str())
        .collect();
    required(shapes, flow)
        .into_iter()
        .filter(|i| !came.contains(i) && !bound.contains(i))
        .collect()
}

/// WF-27, WF-29, WF-30 for its clock, and what its `bind:` and `only-when:` read.
fn a_workflows_port(
    document: &Node,
    shapes: &Shapes,
    port: &Port,
    answers: &str,
    flow: &Node,
    diags: &mut Diagnostics,
) {
    let came = arriving(document, port, flow);
    let fields: Vec<&str> = came
        .into_iter()
        .flatten()
        .map(|(k, _)| k.as_str())
        .collect();
    if came.is_some() {
        for entry in port
            .node
            .get("same-conversation-when")
            .map(workflows::list)
            .unwrap_or_default()
        {
            let Some(said) = entry.as_str().map(str::trim) else {
                continue;
            };
            if fields.contains(&said) {
                continue;
            }
            diags.push(Diagnostic::error(
                "loader/a-key-that-is-not-a-field",
                entry.span.clone(),
                format!(
                    "'{}' tells two arrivals apart by '{said}', and what arrives there has no \
                     field called that, so no two arrivals could be found to be the same case.",
                    port.name
                ),
                format!(
                    "Use one of the fields listed: {}.",
                    fields
                        .iter()
                        .map(|f| format!("`{f}`"))
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            ));
        }
    }
    let inputs: Vec<&str> = flow
        .get("accepts")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .map(|(k, _)| k.as_str())
        .collect();
    for (key, e) in port
        .node
        .get("bind")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        if !inputs.contains(&key.as_str()) {
            diags.push(Diagnostic::error(
                "loader/a-call-that-does-not-fit",
                e.key_span.clone(),
                format!(
                    "'{}' fills `{key}` of the workflow '{answers}', and '{answers}' takes no \
                     input called that.",
                    port.name
                ),
                format!(
                    "Fill one of its inputs: {}.",
                    inputs
                        .iter()
                        .map(|i| format!("`{i}`"))
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            ));
        }
        arrived(port, &e.node, came, &fields, diags);
    }
    let kind = |n: &Node| -> Option<Kind> {
        let field = n.as_str()?.trim().strip_prefix("input.")?;
        let line = shapes.line(&came?.get(field)?.node)?;
        conditions::of_shape(&line.shape)
    };
    for when in port
        .node
        .get("only-when")
        .map(workflows::list)
        .unwrap_or_default()
    {
        if let Some(value) = when.get("value") {
            arrived(port, value, came, &fields, diags);
        }
        let left = when.get("value").and_then(kind);
        conditions::line(when, Position::Elsewhere, left, &kind, diags);
    }
    let missing = missing_inputs(document, shapes, port, flow);
    if !missing.is_empty() {
        diags.push(Diagnostic::note(
            "loader/a-port-that-cannot-start-a-run",
            key_span(port.node, "answers").unwrap_or_else(|| port.node.span.start_of_block()),
            format!(
                "'{}' cannot fill every input '{answers}' needs to start ({} arrive{} nowhere), \
                 so it only joins runs that are already open.",
                port.name,
                missing
                    .iter()
                    .map(|m| format!("`{m}`"))
                    .collect::<Vec<_>>()
                    .join(", "),
                if missing.len() == 1 { "s" } else { "" }
            ),
            "Nothing to do if that is meant: an arrival with no open run is recorded and dropped. \
             To start runs too, accept or `bind:` the inputs listed."
                .to_string(),
        ));
    }
    if port.is_a_timer()
        && port.text("in-time-zone").is_none()
        && document
            .get("time-zone")
            .and_then(Node::as_str)
            .is_none_or(|z| z.trim().is_empty())
        && let Some(every) = port.node.get("every")
        && let Some(line) = every.as_str()
        && crate::schedules::read(line).is_ok_and(|read| !read.starts_with("@every"))
    {
        diags.push(Diagnostic::error(
            "loader/a-time-with-no-zone",
            every.span.clone(),
            format!(
                "'{}' runs '{answers}' at a time of day (`every: {}`), and neither the port nor \
                 the workspace says which time zone that time is in.",
                port.name,
                line.trim()
            ),
            "Add `in-time-zone: America/Chicago` to the port, or `time-zone:` to `workspace.yaml`."
                .to_string(),
        ));
    }
}

/// WF-4 for what a port reads: `input.<a field that arrives>`.
fn arrived(
    port: &Port,
    value: &Node,
    came: Option<&Map>,
    fields: &[&str],
    diags: &mut Diagnostics,
) {
    let Some(said) = value.as_str().map(str::trim) else {
        return;
    };
    let Some(came) = came else { return };
    let field = said
        .strip_prefix("input.")
        .map(|f| f.split('.').next().unwrap_or(""));
    if field.is_some_and(|f| came.contains_key(f)) || said == "input" {
        return;
    }
    diags.push(Diagnostic::error(
        "loader/a-binding-to-nothing",
        value.span.clone(),
        format!(
            "'{}' reads `{said}`, and a port reads only what arrived at it — `input.<field>` — \
             {}.",
            port.name,
            match field {
                Some(f) => format!("and nothing called '{f}' arrives there"),
                None => "and this is not one of those".to_string(),
            }
        ),
        format!(
            "Use one of the fields that arrive: {}.",
            fields
                .iter()
                .map(|f| format!("`input.{f}`"))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    ));
}

/// WF-19: every port a workflow's wait listens to answers that workflow, joins
/// its open run, and carries the key its runs were started with.
fn heard(
    document: &Node,
    shapes: &Shapes,
    ports: &[Port],
    flow_name: &str,
    flow: &Node,
    diags: &mut Diagnostics,
) {
    let starters: Vec<&Port> = ports
        .iter()
        .filter(|p| p.text("answers") == Some(flow_name))
        .filter(|p| p.overlap() != Some(JOIN) && can_start(document, shapes, p, flow))
        .collect();
    let mut told: BTreeSet<(String, usize)> = BTreeSet::new();
    for (stage, node) in waits::every_stage(flow) {
        if workflows::does(node) != Some("ask-someone") {
            continue;
        }
        let asks = node
            .get("asks")
            .and_then(Node::as_str)
            .map(str::trim)
            .unwrap_or("");
        let question = waits::question_of(document, flow, asks);
        let asked: Vec<(&Node, Answerer)> = question
            .map(|q| waits::answerers(document, q))
            .unwrap_or_default();
        let mut listened: Vec<(&str, Span)> = asked
            .iter()
            .filter(|(_, a)| *a == Answerer::Port)
            .filter_map(|(n, _)| n.as_str().map(|s| (s.trim(), n.span.clone())))
            .collect();
        let heard = node
            .get("then")
            .and_then(|t| t.as_map())
            .and_then(|t| t.get("heard"));
        for (port, e) in heard.and_then(|h| h.node.as_map()).into_iter().flatten() {
            if question.is_some() && !listened.iter().any(|(p, _)| p == port) {
                diags.push(Diagnostic::error(
                    "loader/an-event-the-wait-will-never-hear",
                    e.key_span.clone(),
                    format!(
                        "'{stage}' goes on when it hears '{port}', and its question '{asks}' is not \
                         asked of '{port}', so this wait never listens for it."
                    ),
                    format!("Add '{port}' to `asked-of:` in '{asks}'."),
                ));
                continue;
            }
            listened.push((port.as_str(), e.key_span.clone()));
        }
        for (port_name, at) in listened {
            if !told.insert((at.file.to_string(), at.byte_start)) {
                continue;
            }
            // A port the workspace lacks is the schema's (`key-names: ports`).
            let Some(port) = ports.iter().find(|p| p.name == port_name) else {
                continue;
            };
            let starter = starters.first();
            let why = if port.text("answers") != Some(flow_name) {
                Some(format!(
                    "answers '{}', not this workflow",
                    port.text("answers").unwrap_or("")
                ))
            } else if port.overlap() != Some(JOIN) {
                Some(format!(
                    "does not hand what arrives to the open run (`if-still-running: {}`)",
                    port.overlap().unwrap_or(START)
                ))
            } else {
                starters.iter().find(|s| s.key() != port.key()).map(|s| {
                    format!(
                        "tells its arrivals apart by [{}], and the run was started by '{}', \
                             keyed by [{}]",
                        listed(&port.key()),
                        s.name,
                        listed(&s.key())
                    )
                })
            };
            let Some(why) = why else { continue };
            let key = starter
                .map(|s| s.key().into_iter().collect::<Vec<_>>().join(", "))
                .unwrap_or_else(|| "<its key>".to_string());
            diags.push(Diagnostic::error(
                "loader/an-event-the-wait-will-never-hear",
                at,
                format!(
                    "'{stage}' waits to hear '{port_name}', and that port {why}, so the event never \
                     reaches this run."
                ),
                format!(
                    "Add `answers: {flow_name}`, `if-still-running: join` and \
                     `same-conversation-when: [{key}]` to '{port_name}'."
                ),
            ));
        }
    }
}
