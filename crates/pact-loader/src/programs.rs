//! Nothing here can run that program.
//!
//! # Why this exists
//!
//! A program declares the `engine:` it is written for; a sandbox declares the
//! `engines:` it can host. Both are closed lists and the schema holds each of
//! them against its own — and it cannot hold them against EACH OTHER, because
//! that is a fact about two documents. So a workspace could carry a program in
//! one language and a locked room that cannot run it, and the only way to find
//! out was the first call.
//!
//! That is the "loads and does nothing" failure with the worst possible timing:
//! the author has written a tool, an action, a program, a sandbox and a consent
//! question, every one of them individually correct, and the arrangement can
//! never work.
//!
//! # What it checks
//!
//! For every action naming a program, the sandbox its tool `connect:`s to must
//! host that program's engine. The refusal names the program, the engine it
//! needs, and what the sandbox actually hosts.
//!
//! It deliberately does NOT check that a program is reachable from some tool —
//! `unnamed.rs` already says that about every kind, in the same words, and a
//! second sentence about it here would be two places to keep one rule.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;

/// The engines a resource says it can host.
fn hosted_by(resource: &Node) -> Vec<String> {
    match resource.get("engines").map(|n| &n.value) {
        Some(pact_doc::Value::List(items)) => {
            items.iter().filter_map(|i| i.as_str().map(str::to_owned)).collect()
        }
        // A single value where a list belongs is accepted everywhere else in
        // this format (FR-1.4.7).
        Some(pact_doc::Value::Str(one)) => vec![one.clone()],
        _ => Vec::new(),
    }
}

/// Only a pure program may be named straight from `uses:`.
///
/// The short door exists because a pure program works from what it is given and
/// touches nothing: there is no act for an approval rule to be about, and
/// nothing an `inspects:` line could usefully look at. A program that may read
/// the outside world, or answer differently the second time, is exactly the kind
/// of call the governance vocabulary exists for — so it keeps its tool, where
/// `needs-a-person:`, `spends-money:` and `same-request-key:` can be written.
/// Letting it in through `uses:` would make the shortcut the way round the gate.
fn only_pure_programs_are_used_directly(root: &Node, diags: &mut Diagnostics) {
    let Some(agents) = root.get("agents").and_then(Node::as_map) else { return };
    let programs = root.get("programs").and_then(Node::as_map);
    for (agent_name, agent) in agents {
        let Some(uses) = agent.node.get("uses") else { continue };
        let named: Vec<(&str, &Node)> = match &uses.value {
            pact_doc::Value::List(items) => {
                items.iter().filter_map(|i| i.as_str().map(|s| (s, i))).collect()
            }
            pact_doc::Value::Str(one) => vec![(one.as_str(), uses)],
            _ => continue,
        };
        for (name, at) in named {
            let Some(program) = programs.and_then(|p| p.get(name)) else { continue };
            let how = program.node.get("determinism").and_then(Node::as_str).unwrap_or("");
            if how == "pure" {
                continue;
            }
            diags.push(Diagnostic::error(
                "loader/only-a-pure-program-is-used-directly",
                at.span.clone(),
                format!(
                    "'{agent_name}' names the program '{name}' directly, and '{name}' says it \
                     is `{how}` rather than `pure` — so it may look at something outside what \
                     it was given, and a call like that is one somebody may need to approve."
                ),
                format!(
                    "Reach it through a tool instead: give the tool a `connect:` to a locked \
                     room and an action with `program: {name}`, where you can write \
                     `needs-a-person:` beside it. Or mark '{name}' `determinism: pure` if it \
                     really does work only from what it is given."
                ),
            ));
        }
    }
}

/// A projection must be pure, for a reason the short door does not share.
///
/// `projects-with:` decides what the model is TOLD. A projection that could read
/// the outside world, or answer differently the second time, would make the
/// conversation unreproducible — and the trace is what the portability claim is
/// measured on, so two runs of one document have to agree about what the model
/// read. That is a stronger requirement than the one on `uses:`, where purity
/// buys the absence of anything to govern; here it buys determinism itself.
fn only_pure_programs_project(root: &Node, diags: &mut Diagnostics) {
    let Some(tools) = root.get("tools").and_then(Node::as_map) else { return };
    let programs = root.get("programs").and_then(Node::as_map);
    for (tool_name, tool) in tools {
        let Some(actions) = tool.node.get("actions").and_then(Node::as_map) else { continue };
        for (action_name, action) in actions {
            let Some(named) = action.node.get("projects-with").and_then(Node::as_str) else {
                continue;
            };
            let Some(program) = programs.and_then(|p| p.get(named)) else { continue };
            let how = program.node.get("determinism").and_then(Node::as_str).unwrap_or("");
            if how == "pure" {
                continue;
            }
            let at = action
                .node
                .get("projects-with")
                .map_or_else(|| action.key_span.clone(), |n| n.span.clone());
            diags.push(Diagnostic::error(
                "loader/only-a-pure-program-projects",
                at,
                format!(
                    "'{tool_name}/{action_name}' shortens what it answers with using \
                     '{named}', and '{named}' says it is `{how}` rather than `pure` — so what \
                     the model is told could be different the second time the same thing \
                     happens."
                ),
                format!(
                    "Mark '{named}' `determinism: pure`, or shorten this answer with a \
                     program that works only from what it is given."
                ),
            ));
        }
    }
}

/// Refuse an arrangement where nothing can run the program that was named.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    only_pure_programs_are_used_directly(root, diags);
    only_pure_programs_project(root, diags);
    let Some(tools) = root.get("tools").and_then(Node::as_map) else { return };
    let programs = root.get("programs").and_then(Node::as_map);
    let resources = root.get("resources").and_then(Node::as_map);

    for (tool_name, tool) in tools {
        let Some(actions) = tool.node.get("actions").and_then(Node::as_map) else { continue };
        // Which locked room this tool reaches. A tool reaches ONE place
        // (`reach.rs`), so there is one answer or none.
        let reaches = tool.node.get("connect").and_then(Node::as_str);

        for (action_name, action) in actions {
            let Some(named) = action.node.get("program").and_then(Node::as_str) else {
                continue;
            };
            // Whether the program EXISTS is `names: programs`, held by the
            // schema where the author wrote it. This pass only asks whether the
            // arrangement can work.
            let Some(program) = programs.and_then(|p| p.get(named)) else { continue };
            let Some(engine) = program.node.get("engine").and_then(Node::as_str) else {
                continue;
            };

            let at = action.node.get("program").map_or_else(
                || action.key_span.clone(),
                |n| n.span.clone(),
            );

            let Some(server) = reaches else {
                diags.push(Diagnostic::error(
                    "loader/nothing-here-can-run-that-program",
                    at,
                    format!(
                        "'{tool_name}/{action_name}' runs the program '{named}', and \
                         '{tool_name}' does not reach a locked room to run it in."
                    ),
                    format!(
                        "Add `connect: <name>` on `tools/{tool_name}.yaml`, naming a resource \
                         whose `resource-kind:` is `sandbox`."
                    ),
                ));
                continue;
            };

            let Some(resource) = resources.and_then(|r| r.get(server)) else { continue };
            let kind = resource.node.get("resource-kind").and_then(Node::as_str);
            if kind != Some("sandbox") {
                diags.push(Diagnostic::error(
                    "loader/nothing-here-can-run-that-program",
                    at,
                    format!(
                        "'{tool_name}/{action_name}' runs the program '{named}', and \
                         '{tool_name}' reaches '{server}', which is {}.",
                        match kind {
                            Some(k) => format!("a {k}"),
                            None => "not a locked room".to_string(),
                        }
                    ),
                    "Point `connect:` at a resource whose `resource-kind:` is `sandbox`. A \
                     program runs in a locked room and nowhere else."
                        .to_string(),
                ));
                continue;
            }

            let hosts = hosted_by(&resource.node);
            if !hosts.iter().any(|h| h == engine) {
                diags.push(Diagnostic::error(
                    "loader/nothing-here-can-run-that-program",
                    at,
                    format!(
                        "'{named}' is written for `{engine}`, and '{server}' — the locked room \
                         '{tool_name}' reaches — {}.",
                        if hosts.is_empty() {
                            "says nothing about what it can run".to_string()
                        } else {
                            format!("runs only {}", hosts.join(", "))
                        }
                    ),
                    format!(
                        "Add `{engine}` under `engines:` in `resources/{server}.yaml`, or write \
                         '{named}' for one of the kinds that room already runs."
                    ),
                ));
            }
        }
    }
}
