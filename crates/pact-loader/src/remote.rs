//! **A tool that reaches an agent somewhere else, over A2A** (N1).
//!
//! `resource-kind: a2a-agent` is a remote agent: an `endpoint:`, a credential
//! by reference, a consent question and a pinned card, the same lines an MCP
//! server writes. A tool reaches it with `connect:`, and that tool's `actions:`
//! are the skills of the remote agent's card the model may ask, each by the
//! skill's id. Two shapes of such a tool load clean and cannot work, so both
//! are refused here, where the author is:
//!
//! * **No skill at all.** A tool with no `actions:` is offered to the model as
//!   nothing it can call, and a remote agent asked for nothing is a connection
//!   that is opened (and consented to) for no reason.
//! * **An action that says `answers-with:`.** What a remote agent sends back is
//!   words it wrote: it reaches the model fenced off as text nobody here
//!   reviewed (`mcp_bridge.quarantined`), never as values a run acts on. A line
//!   promising values would be the "loads and does nothing" failure, and worse,
//!   an invitation to let a stranger's words fill the fields a condition reads.
//!
//! Which skills the card really lists is not knowable here: the card is the
//! remote agent's, read when the run first calls it, and held there to what
//! this tree declares (`pact_adapters.a2a_bridge.check_card`).

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;

/// The `resource-kind:` of an agent reached over A2A.
pub const A2A_AGENT: &str = "a2a-agent";

/// Refuse every tool reaching a remote agent that asks it for no skill, or
/// promises values from one.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let Some(tools) = document.get("tools").and_then(Node::as_map) else {
        return;
    };
    let resources = document.get("resources").and_then(Node::as_map);
    for (name, entry) in tools {
        let Some(fields) = entry.node.as_map() else {
            continue;
        };
        let Some(server) = fields.get("connect").and_then(|c| c.node.as_str()) else {
            continue;
        };
        let remote = resources
            .and_then(|r| r.get(server.trim()))
            .and_then(|r| r.node.get("resource-kind"))
            .and_then(Node::as_str)
            .is_some_and(|k| k.trim() == A2A_AGENT);
        if !remote {
            continue;
        }
        let actions = fields.get("actions").and_then(|a| a.node.as_map());
        let Some(actions) = actions.filter(|a| !a.is_empty()) else {
            diags.push(Diagnostic::error(
                "loader/a-remote-agent-asked-for-no-skill",
                entry.key_span.clone(),
                format!(
                    "'{name}' reaches '{server}', an agent reached over A2A, and names no skill \
                     of it to ask — so the model is offered a tool that can do nothing, over a \
                     connection opened for nothing."
                ),
                format!(
                    "Add `actions:` to `tools/{name}.yaml`, one entry per skill of '{server}' \
                     the model may ask, each named by the skill's id on its card."
                ),
            ));
            continue;
        };
        for (action, a) in actions {
            let Some(said) = a.node.get("answers-with") else {
                continue;
            };
            let at = a
                .node
                .as_map()
                .and_then(|m| m.get("answers-with"))
                .map_or_else(
                    || said.span.clone(),
                    |e| e.key_span.clone().merge(&e.node.span),
                );
            diags.push(Diagnostic::error(
                "loader/a-remote-agent-answers-in-words",
                at,
                format!(
                    "'{name}/{action}' says what it answers with, and '{server}' is an agent \
                     reached over A2A: what comes back is words that agent wrote, read as text \
                     nobody here reviewed and never as values."
                ),
                format!(
                    "Delete `answers-with:` from '{name}/{action}'. To work with values, hand the \
                     reply to an agent or a program that reads it and says `answers-with:` itself."
                ),
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    const WORKSPACE: &str = "
resources:
  booker:
    resource-kind: a2a-agent
    endpoint: host/booker
tools:
  bookings:
    description: The booking agent.
    connect: booker
    actions:
      book-slot:
        description: Book one slot.
        takes:
          request: text
";

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("workspace.yaml", text);
        check(&node, &mut d);
        d
    }

    fn rules(d: &Diagnostics) -> Vec<String> {
        d.items().iter().map(|x| x.rule.to_string()).collect()
    }

    #[test]
    fn a_tool_that_asks_a_remote_agent_for_a_skill_in_words_is_left_alone() {
        let d = check_text(WORKSPACE);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_tool_that_asks_a_remote_agent_for_nothing_is_refused() {
        let text = WORKSPACE.split("    actions:").next().unwrap().to_string();
        let d = check_text(&text);
        assert_eq!(
            rules(&d),
            ["loader/a-remote-agent-asked-for-no-skill"],
            "{}",
            d.render()
        );
    }

    #[test]
    fn a_skill_of_a_remote_agent_that_promises_values_is_refused() {
        let text = format!("{WORKSPACE}        answers-with:\n          slot: text\n");
        let d = check_text(&text);
        assert_eq!(
            rules(&d),
            ["loader/a-remote-agent-answers-in-words"],
            "{}",
            d.render()
        );
    }

    #[test]
    fn the_same_lines_on_an_mcp_server_are_not_this_rules_to_judge() {
        let text = format!("{WORKSPACE}        answers-with:\n          slot: text\n")
            .replace("a2a-agent", "mcp-server");
        assert!(check_text(&text).is_empty());
    }
}
