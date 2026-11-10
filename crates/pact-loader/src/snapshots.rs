//! **What a server says it offers, recorded, and held to what this tree
//! decides about it** (96 §E).
//!
//! A tool that connects to an MCP server used to carry two things in one list:
//! which actions the agent may call, which is a decision, and what each one
//! takes, which is a fact the server already publishes. The decision stays
//! written by a person. The fact can now come from the server — recorded by
//! `pact-sync` into the resource's `published:` block
//! (`schemas-from: the-snapshot`), or read live each time it connects
//! (`schemas-from: the-server`).
//!
//! What the recording buys is that `pact check`, offline, can hold every line
//! a decision rests on to argument names the server really publishes. Before
//! it, `inspects: [amount]` on a server whose argument is `amount_cents` loaded
//! clean, and the approval rule over 200 USD then looked at an argument no call
//! ever carried — found at connect time, on a machine, with a customer waiting.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/schemas-from-a-tool-with-no-server` | `schemas-from:` other than `this-file` on a tool that does not connect to an MCP server or a remote agent |
//! | `loader/takes-written-twice` | `schemas-from: the-snapshot` or `the-server`, and an action writes `takes:` or `answers-with:` as well |
//! | `loader/a-snapshot-nobody-took` | `schemas-from: the-snapshot` on a server with no `published:` |
//! | `loader/an-action-the-server-does-not-publish` | the recorded server has no tool by the name an action calls |
//! | `loader/an-argument-the-server-does-not-take` | an argument a decision rests on — in `takes:`, `inspects:`, `same-request-key:`, `bind:` or `passes:` — is not one the recorded tool takes |
//! | `loader/an-argument-nothing-gives` | the recorded tool requires an argument that no line here supplies |
//! | `loader/unlisted-actions-nobody-can-describe` | `unlisted-actions: each-call-asks-a-person` with nothing to read their arguments from |
//! | `loader/two-pins-on-one-server` | a resource with `published:` and the older `tool-snapshot-digest:` both |
//! | `loader/a-change-to-nothing-recorded` | `if-it-changes:` on a server with no `published:` to compare with |
//! | `loader/declared-lighter-than-the-server-says` | an action says `reads-only: yes` and the server's recorded `hints:` say it is destructive or not read-only (law 1, warning) |

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;
use std::collections::BTreeSet;

const SERVERS: [&str; 2] = ["mcp-server", "a2a-agent"];

fn word<'a>(node: &'a Node, field: &str) -> Option<&'a str> {
    node.get(field).and_then(Node::as_str).map(str::trim)
}

fn at(node: &Node, field: &str, or: &Span) -> Span {
    node.as_map()
        .and_then(|m| m.get(field))
        .map(|e| e.key_span.clone().merge(&e.node.span))
        .unwrap_or_else(|| or.clone())
}

pub fn check(document: &Node, diags: &mut Diagnostics) {
    let resources = document.get("resources").and_then(Node::as_map);
    for (name, entry) in resources.into_iter().flatten() {
        let node = &entry.node;
        let published = node.get("published").is_some();
        if published && node.get("tool-snapshot-digest").is_some() {
            diags.push(Diagnostic::error(
                "loader/two-pins-on-one-server",
                at(node, "tool-snapshot-digest", &entry.key_span),
                format!(
                    "'{name}' is pinned twice — by `published:`, which `pact-sync` \
                     recorded, and by `tool-snapshot-digest:` — and the two can disagree."
                ),
                "Take out the three `tool-snapshot-*` lines: `published:` carries its own \
                 digest and the date it was taken.",
            ));
        }
        if !published && node.get("if-it-changes").is_some() {
            diags.push(Diagnostic::error(
                "loader/a-change-to-nothing-recorded",
                at(node, "if-it-changes", &entry.key_span),
                format!(
                    "'{name}' says what to do when the server changes, and nothing records \
                     what it said before, so there is nothing to compare with."
                ),
                format!("Run `pact-sync {name}` to record it, or take the line out."),
            ));
        }
    }
    let Some(tools) = document.get("tools").and_then(Node::as_map) else {
        return;
    };
    for (name, entry) in tools {
        let tool = &entry.node;
        let from = word(tool, "schemas-from").unwrap_or("this-file");
        let server = word(tool, "connect").and_then(|c| Some((c, resources?.get(c)?)));
        let serves = server.is_some_and(|(_, r)| {
            word(&r.node, "resource-kind").is_some_and(|k| SERVERS.contains(&k))
        });
        if from != "this-file" && !serves {
            diags.push(Diagnostic::error(
                "loader/schemas-from-a-tool-with-no-server",
                at(tool, "schemas-from", &entry.key_span),
                format!(
                    "'{name}' takes its arguments from {}, and it does not connect to an MCP \
                     server or a remote agent — nothing publishes them.",
                    if from == "the-server" {
                        "the server"
                    } else {
                        "a recorded snapshot"
                    }
                ),
                "Take the `schemas-from:` line out and write each action's `takes:`.",
            ));
            continue;
        }
        if word(tool, "unlisted-actions") == Some("each-call-asks-a-person") && from == "this-file"
        {
            diags.push(Diagnostic::error(
                "loader/unlisted-actions-nobody-can-describe",
                at(tool, "unlisted-actions", &entry.key_span),
                format!(
                    "'{name}' offers the actions it does not list, and takes every action's \
                     arguments from this file — which says nothing about an action it does \
                     not list."
                ),
                "Write `schemas-from: the-snapshot` (or `the-server`) beside it.",
            ));
        }
        let implementation = tool.get("implements").is_some();
        let actions = tool.get("actions").and_then(Node::as_map);
        if from != "this-file" && !implementation {
            for (action, line) in actions.into_iter().flatten() {
                for field in ["takes", "answers-with"] {
                    if line.node.get(field).is_some() {
                        diags.push(Diagnostic::error(
                            "loader/takes-written-twice",
                            at(&line.node, field, &line.key_span),
                            format!(
                                "'{name}/{action}' writes `{field}:`, and '{name}' takes that \
                                 from {} — two lists of the same arguments, which can disagree.",
                                if from == "the-server" {
                                    "the server"
                                } else {
                                    "the snapshot"
                                }
                            ),
                            format!(
                                "Take `{field}:` out; the server's own list is what is sent. \
                                 Or write `schemas-from: this-file` to keep writing it here."
                            ),
                        ));
                    }
                }
            }
        }
        let Some((server_name, resource)) = server else {
            continue;
        };
        let recorded = resource.node.get("published");
        if from == "the-snapshot" && recorded.is_none() {
            diags.push(Diagnostic::error(
                "loader/a-snapshot-nobody-took",
                at(tool, "schemas-from", &entry.key_span),
                format!(
                    "'{name}' sends what the snapshot of '{server_name}' recorded, and nobody \
                     has recorded one."
                ),
                format!(
                    "Run `pact-sync {server_name}`, review what it writes into \
                     `resources/{server_name}.yaml`, and commit it."
                ),
            ));
            continue;
        }
        let Some(published) = recorded.and_then(|p| p.get("tools")).and_then(Node::as_map) else {
            continue;
        };
        for (action, line) in actions.into_iter().flatten() {
            let calls = word(&line.node, "calls").unwrap_or(action);
            let Some(server_tool) = published.get(calls) else {
                let offered: Vec<&str> = published.keys().map(String::as_str).collect();
                diags.push(Diagnostic::error(
                    "loader/an-action-the-server-does-not-publish",
                    at(&line.node, "calls", &line.key_span),
                    format!(
                        "'{name}/{action}' calls '{calls}', and '{server_name}' publishes no \
                         tool by that name — as of its snapshot."
                    ),
                    format!(
                        "Write `calls:` naming one it does publish: {}. If the server has \
                         changed since, run `pact-sync {server_name}`.",
                        offered.join(", ")
                    ),
                ));
                continue;
            };
            arguments(
                name,
                action,
                &line.node,
                &server_tool.node,
                server_name,
                diags,
            );
            lighter_than_the_server_says(
                name,
                action,
                &line.node,
                &server_tool.node,
                server_name,
                diags,
            );
        }
    }
}

/// Law 1 (`docs/98` WP-2): an action's effect is never lighter than what it
/// does. The one place a second opinion is written down is the server's own
/// `hints:`, recorded by `pact-sync`. The schema says those are "never trusted
/// to decide anything, because the server wrote it", and nothing here decides
/// on them: the author's `reads-only: yes` still stands. What this says is that
/// the two disagree in the dangerous direction, and an action marked as only
/// looking things up skips every protection a write gets — an approval rule
/// keyed on writes, the exactly-once claim, the undo plan.
fn lighter_than_the_server_says(
    tool: &str,
    action: &str,
    line: &Node,
    server_tool: &Node,
    server_name: &str,
    diags: &mut Diagnostics,
) {
    if !line
        .get("reads-only")
        .is_some_and(crate::teams::said_yes_node)
    {
        return;
    }
    let Some(hints) = server_tool.get("hints") else {
        return;
    };
    let flag = |k: &str| hints.get(k).map(crate::teams::said_yes_node);
    let destructive = flag("destructiveHint") == Some(true);
    let not_read_only = flag("readOnlyHint") == Some(false);
    if !destructive && !not_read_only {
        return;
    }
    let what = if destructive {
        "`destructiveHint: true`"
    } else {
        "`readOnlyHint: false`"
    };
    diags.push(Diagnostic::warning(
        "loader/declared-lighter-than-the-server-says",
        at(line, "reads-only", &line.span),
        format!(
            "'{tool}/{action}' says `reads-only: yes`, and '{server_name}' publishes it with \
             {what}. Marked as only looking things up, it gets none of what a write gets: no \
             approval rule keyed on writes reaches it, no exactly-once claim is required, and \
             no undo plan is asked for."
        ),
        format!(
            "If it does change something, take out `reads-only: yes`. If the server's hint is \
             wrong, keep the line and say why in a comment beside it, and tell whoever runs \
             '{server_name}'."
        ),
    ));
}

/// Every argument a decision rests on is one the recorded tool takes, and
/// every argument it requires is supplied by something here.
fn arguments(
    tool: &str,
    action: &str,
    line: &Node,
    published: &Node,
    server: &str,
    diags: &mut Diagnostics,
) {
    let schema = published.get("takes");
    let Some(properties) = schema
        .and_then(|s| s.get("properties"))
        .and_then(Node::as_map)
    else {
        return;
    };
    let takes: BTreeSet<&str> = properties.keys().map(String::as_str).collect();
    let passes: Vec<(&str, &str)> = line
        .get("passes")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .filter_map(|(k, e)| Some((k.as_str(), e.node.as_str()?.trim())))
        .collect();
    // What the server calls an argument this tree calls `ours`.
    let theirs = |ours: &str| -> String {
        passes
            .iter()
            .find(|(_, v)| *v == ours)
            .map_or(ours, |(k, _)| *k)
            .to_string()
    };
    let mut named: Vec<(String, &'static str, Span)> = Vec::new();
    for (key, entry) in line
        .get("takes")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        named.push((theirs(key), "takes", entry.key_span.clone()));
    }
    for item in line
        .get("inspects")
        .map(crate::workflows::list)
        .into_iter()
        .flatten()
    {
        if let Some(a) = item.as_str() {
            named.push((theirs(a.trim()), "inspects", item.span.clone()));
        }
    }
    if let Some(key) = line.get("same-request-key")
        && let Some(a) = key.as_str()
    {
        named.push((theirs(a.trim()), "same-request-key", key.span.clone()));
    }
    for (key, entry) in line
        .get("bind")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        named.push((theirs(key), "bind", entry.key_span.clone()));
    }
    for (key, entry) in line
        .get("passes")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        named.push((key.clone(), "passes", entry.key_span.clone()));
    }
    let mut supplied: BTreeSet<String> = BTreeSet::new();
    for (argument, field, span) in named {
        if takes.contains(argument.as_str()) {
            supplied.insert(argument);
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/an-argument-the-server-does-not-take",
            span,
            format!(
                "'{tool}/{action}' names '{argument}' in `{field}:`, and the tool '{server}' \
                 recorded takes no argument called that — anything resting on it would look at \
                 a value no call ever carries."
            ),
            format!(
                "Use one of the arguments it takes: {}. When this tree calls it something \
                 else, say so with `passes:`.",
                takes.iter().copied().collect::<Vec<_>>().join(", ")
            ),
        ));
    }
    // Only where this file lists the arguments. With the snapshot or the
    // server as the source, the model is offered the server's own list and so
    // supplies what it requires itself.
    if line.get("takes").is_none() {
        return;
    }
    for required in schema
        .and_then(|s| s.get("required"))
        .map(crate::workflows::list)
        .into_iter()
        .flatten()
        .filter_map(Node::as_str)
    {
        if supplied.contains(required) {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/an-argument-nothing-gives",
            line.span.clone(),
            format!(
                "The tool '{server}' recorded for '{tool}/{action}' needs '{required}', and \
                 nothing here gives it — not `takes:`, not `bind:`."
            ),
            format!(
                "Add '{required}' to `takes:` (or to `bind:`, when the surrounding system knows \
                 it), or let the server say what it takes with `schemas-from: the-snapshot`."
            ),
        ));
    }
}
