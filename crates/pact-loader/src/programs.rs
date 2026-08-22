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

/// Refuse an arrangement where nothing can run the program that was named.
pub fn check(root: &Node, diags: &mut Diagnostics) {
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
