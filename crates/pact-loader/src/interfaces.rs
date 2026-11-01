//! **One tool, procedure or set of documents that stands for several** (96 §B1).
//!
//! An interface is the CONTRACT half of a capability — `tools/email.yaml`
//! says what an email tool may be asked, in which words, and what needs a
//! person — and every entry that `implements:` it is a STRATEGY: Gmail for one
//! customer, Outlook for the next, chosen per run by `chosen-by:`. An agent,
//! a policy and an eval are written against the interface, so the policy
//! about `email/send-message` holds whichever provider is picked.
//!
//! That only stays true if an implementation can say HOW it reaches its
//! server and nothing else. One that restated `takes:`, or said a call needs
//! no person where the interface said it does, would make the contract hold
//! for whichever provider happened not to restate it — so those lines are
//! refused here, and the one direction that is safe, asking a person MORE,
//! is allowed.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/implements-what-is-not-an-interface` | `implements:` names an entry that does not say `interface: yes` |
//! | `loader/an-interface-that-implements` | one entry is both |
//! | `loader/chosen-by-without-a-choice` | `chosen-by:` on an entry that is not an interface |
//! | `loader/chosen-by-what` | `chosen-by:` is neither `the-host` nor `run-inputs.<name>` |
//! | `loader/chosen-by-an-input-the-agent-lacks` | an agent using the interface has no such run input, or it is not a `one of` |
//! | `loader/a-choice-that-implements-nothing` | a choice in that `one of` is not an implementation |
//! | `loader/an-interface-that-does-the-work` | an interface tool writes `connect:`, `url:` or `says:`; an interface procedure has a body; an interface set of documents has documents |
//! | `loader/an-interface-with-no-actions` | an interface tool lists no actions |
//! | `loader/an-implementation-missing-an-action` | an implementation lacks one of the interface's actions |
//! | `loader/an-action-the-interface-does-not-have` | an implementation adds one |
//! | `loader/an-implementation-restates-the-interface` | an implementation's action writes what only the interface may say |
//! | `loader/passes-an-argument-the-interface-does-not-take` | a `passes:` line names an argument the interface's action does not take |
//! | `loader/an-interface-nothing-implements` (warning) | an interface with no implementation, so a run that reaches it has nothing to use |
//! | `loader/the-interface-and-one-of-its-own` (warning) | an agent `uses:` both the interface and one of its implementations |

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;
use std::collections::BTreeMap;

/// The three kinds an interface can be written for, and the line that is the
/// kind's own BODY — what an implementation has and an interface may not.
const KINDS: [(&str, &[&str], &str); 3] = [
    ("tools", &["connect", "url", "says"], "tool"),
    ("skills", &["content"], "procedure"),
    ("knowledge", &["documents"], "set of documents"),
];

/// What an implementation's action may write. Everything else is the
/// interface's to say. `needs-a-person` is here because `yes` only ever asks
/// more; `no` against an interface's `yes` is refused below.
const AN_IMPLEMENTATION_MAY_SAY: [&str; 9] = [
    "description",
    "calls",
    "passes",
    "bind",
    "program",
    "projects-with",
    "status-check",
    "undone-by",
    "needs-a-person",
];

fn yes(node: &Node, field: &str) -> bool {
    node.get(field).is_some_and(crate::workflows::said_yes)
}

fn text<'a>(node: &'a Node, field: &str) -> Option<&'a str> {
    node.get(field).and_then(Node::as_str).map(str::trim)
}

fn at(node: &Node, field: &str, or: &Span) -> Span {
    node.as_map()
        .and_then(|m| m.get(field))
        .map(|e| e.key_span.clone().merge(&e.node.span))
        .unwrap_or_else(|| or.clone())
}

pub fn check(document: &Node, diags: &mut Diagnostics) {
    for (collection, body, noun) in KINDS {
        let Some(entries) = document.get(collection).and_then(Node::as_map) else {
            continue;
        };
        let mut implementations: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for (name, entry) in entries {
            let node = &entry.node;
            let interface = yes(node, "interface");
            if let Some(of) = text(node, "implements") {
                if interface {
                    diags.push(Diagnostic::error(
                        "loader/an-interface-that-implements",
                        at(node, "implements", &entry.key_span),
                        format!(
                            "'{name}' says it is an interface and that it implements '{of}'. \
                             An interface describes what several have in common; it is never \
                             one of them."
                        ),
                        "Take out `interface: yes`, or take out `implements:`.",
                    ));
                }
                match entries.get(of) {
                    Some(target) if yes(&target.node, "interface") => {
                        implementations.entry(of).or_default().push(name);
                    }
                    Some(_) => diags.push(Diagnostic::error(
                        "loader/implements-what-is-not-an-interface",
                        at(node, "implements", &entry.key_span),
                        format!(
                            "'{name}' implements '{of}', and '{of}' is a {noun} in its own \
                             right, not an interface — so there is nothing for '{name}' to \
                             stand in for."
                        ),
                        format!(
                            "Write `interface: yes` in '{of}' if it describes what several \
                             {collection} have in common, or take the `implements:` line out."
                        ),
                    )),
                    // Not there at all: `schema/no-such-name` is already saying so.
                    None => {}
                }
            }
            if node.get("chosen-by").is_some() && !interface {
                diags.push(Diagnostic::error(
                    "loader/chosen-by-without-a-choice",
                    at(node, "chosen-by", &entry.key_span),
                    format!(
                        "'{name}' says who chooses which one does the work, and it is not an \
                         interface — there is only ever '{name}'."
                    ),
                    "Take the `chosen-by:` line out, or write `interface: yes` here.",
                ));
            }
            if interface {
                for field in body {
                    if node.get(field).is_some_and(|n| !blank(n)) {
                        diags.push(Diagnostic::error(
                            "loader/an-interface-that-does-the-work",
                            at(node, field, &entry.key_span),
                            format!(
                                "'{name}' is an interface, and it writes `{field}:` — which is \
                                 the part each {noun} that implements it supplies for itself."
                            ),
                            format!(
                                "Move `{field}:` into the {collection} that say `implements: \
                                 {name}`, or take out `interface: yes`."
                            ),
                        ));
                    }
                }
            }
        }
        for (name, entry) in entries {
            if !yes(&entry.node, "interface") {
                continue;
            }
            let found = implementations
                .get(name.as_str())
                .cloned()
                .unwrap_or_default();
            if found.is_empty() {
                diags.push(Diagnostic::warning(
                    "loader/an-interface-nothing-implements",
                    entry.key_span.clone(),
                    format!(
                        "'{name}' is an interface and nothing implements it, so a run that \
                         reaches it has no {noun} to use."
                    ),
                    format!(
                        "Add a {noun} that says `implements: {name}`. A template may leave \
                         this to the copies made from it."
                    ),
                ));
            }
            chosen_by(document, collection, name, &entry.node, &found, diags);
            if collection == "tools" {
                actions(entries, name, &entry.node, &entry.key_span, &found, diags);
            }
        }
        both_used(document, collection, &implementations, diags);
    }
}

fn blank(n: &Node) -> bool {
    match &n.value {
        pact_doc::Value::Str(s) => s.trim().is_empty(),
        pact_doc::Value::Null => true,
        pact_doc::Value::Map(m) => m.is_empty(),
        pact_doc::Value::List(l) => l.is_empty(),
        _ => false,
    }
}

/// `chosen-by:` names who picks, and a run input it names has to be a
/// closed choice of implementations on every agent that uses the interface.
fn chosen_by(
    document: &Node,
    collection: &str,
    name: &str,
    interface: &Node,
    found: &[&str],
    diags: &mut Diagnostics,
) {
    let Some(written) = text(interface, "chosen-by") else {
        return;
    };
    let span = at(interface, "chosen-by", &interface.span);
    if written == "the-host" {
        return;
    }
    let Some(input) = written.strip_prefix("run-inputs.") else {
        diags.push(Diagnostic::error(
            "loader/chosen-by-what",
            span,
            format!("'{name}' is chosen by '{written}', and nothing is called that."),
            "Write `chosen-by: the-host`, or `chosen-by: run-inputs.<name>` naming a run input \
             of the agents that use it.",
        ));
        return;
    };
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        return;
    };
    for (agent, entry) in agents {
        let uses = entry
            .node
            .get("uses")
            .map(crate::workflows::list)
            .unwrap_or_default();
        if !uses.iter().any(|u| u.as_str().map(str::trim) == Some(name)) {
            continue;
        }
        let shape = entry
            .node
            .get("run-inputs")
            .and_then(|r| r.get(input))
            .and_then(Node::as_str)
            .map(str::trim);
        let choices: Option<Vec<&str>> = shape
            .and_then(|s| s.strip_suffix(", optional").or(Some(s)))
            .and_then(|s| s.strip_prefix("one of "))
            .map(|rest| {
                rest.split(',')
                    .map(str::trim)
                    .filter(|c| !c.is_empty())
                    .collect()
            });
        let Some(choices) = choices else {
            diags.push(Diagnostic::error(
                "loader/chosen-by-an-input-the-agent-lacks",
                entry.key_span.clone(),
                format!(
                    "'{agent}' uses '{name}', which is chosen by `run-inputs.{input}`, and \
                     '{agent}' has no run input '{input}' written as a choice between the \
                     {collection} that implement it."
                ),
                format!(
                    "Add `{input}: one of {}` under `run-inputs:` in '{agent}'.",
                    if found.is_empty() {
                        "<a>, <b>".to_string()
                    } else {
                        found.join(", ")
                    }
                ),
            ));
            continue;
        };
        for choice in choices {
            if !found.contains(&choice) {
                diags.push(Diagnostic::error(
                    "loader/a-choice-that-implements-nothing",
                    entry.key_span.clone(),
                    format!(
                        "'{agent}' may be given `{input}: {choice}`, and nothing called \
                         '{choice}' implements '{name}' — a run given it would have nothing \
                         to use."
                    ),
                    if found.is_empty() {
                        format!("Add a {collection} entry '{choice}' with `implements: {name}`.")
                    } else {
                        format!(
                            "The choices that implement '{name}' are: {}.",
                            found.join(", ")
                        )
                    },
                ));
            }
        }
    }
}

/// An implementation offers exactly the interface's actions and says only how
/// each one reaches its own server.
fn actions(
    tools: &pact_doc::Map,
    name: &str,
    interface: &Node,
    key_span: &Span,
    found: &[&str],
    diags: &mut Diagnostics,
) {
    let wanted = interface.get("actions").and_then(Node::as_map);
    if wanted.is_none_or(|m| m.is_empty()) {
        diags.push(Diagnostic::error(
            "loader/an-interface-with-no-actions",
            key_span.clone(),
            format!(
                "'{name}' is an interface and lists no actions, so there is nothing an agent \
                 using it could ever be offered."
            ),
            "List the actions every tool that implements it has to offer, under `actions:`.",
        ));
        return;
    }
    let Some(wanted) = wanted else { return };
    for implementation in found {
        let Some(entry) = tools.get(*implementation) else {
            continue;
        };
        let offered = entry.node.get("actions").and_then(Node::as_map);
        for (action, contract) in wanted {
            let Some(own) = offered.and_then(|o| o.get(action)) else {
                diags.push(Diagnostic::error(
                    "loader/an-implementation-missing-an-action",
                    entry.key_span.clone(),
                    format!(
                        "'{implementation}' implements '{name}', and has no '{action}' — an \
                         agent using '{name}' would be offered it and the call would reach \
                         nothing."
                    ),
                    format!(
                        "Add `{action}:` under `actions:` in '{implementation}', with `calls:` \
                         naming what its server calls it."
                    ),
                ));
                continue;
            };
            restated(implementation, name, action, &contract.node, own, diags);
        }
        for (action, own) in offered.into_iter().flatten() {
            if !wanted.contains_key(action) {
                diags.push(Diagnostic::error(
                    "loader/an-action-the-interface-does-not-have",
                    own.key_span.clone(),
                    format!(
                        "'{implementation}' implements '{name}' and adds '{action}', which \
                         '{name}' does not have — an agent using '{name}' is never offered it, \
                         and nobody reviewed what it may do."
                    ),
                    format!(
                        "Add '{action}' to '{name}' so every implementation offers it, or make \
                         a separate tool for it."
                    ),
                ));
            }
        }
    }
}

fn restated(
    implementation: &str,
    interface: &str,
    action: &str,
    contract: &Node,
    own: &pact_doc::Entry,
    diags: &mut Diagnostics,
) {
    let Some(lines) = own.node.as_map() else {
        return;
    };
    for (field, line) in lines {
        let allowed = AN_IMPLEMENTATION_MAY_SAY.contains(&field.as_str());
        let loosens = field == "needs-a-person"
            && !crate::workflows::said_yes(&line.node)
            && contract
                .get("needs-a-person")
                .is_some_and(crate::workflows::said_yes);
        if allowed && !loosens {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/an-implementation-restates-the-interface",
            line.key_span.clone().merge(&line.node.span),
            if loosens {
                format!(
                    "'{implementation}/{action}' says it needs no person, and '{interface}' \
                     says every '{action}' does. An implementation may ask more of a person \
                     than its interface, never less."
                )
            } else {
                format!(
                    "'{implementation}/{action}' writes `{field}:`, which is '{interface}''s to \
                     say: it is what every implementation shares, so an agent, a policy and a \
                     check written against '{interface}' mean the same thing whichever one runs."
                )
            },
            if loosens {
                "Take the line out — the interface's `needs-a-person: yes` already holds here."
                    .to_string()
            } else {
                format!(
                    "Take `{field}:` out of '{implementation}', and write it on '{interface}' \
                     if it should hold for all of them. Use `passes:` when the server calls an \
                     argument something else."
                )
            },
        ));
    }
    let takes = contract.get("takes").and_then(Node::as_map);
    for (_, passed) in own
        .node
        .get("passes")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let Some(argument) = passed.node.as_str().map(str::trim) else {
            continue;
        };
        if takes.is_some_and(|t| t.contains_key(argument)) {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/passes-an-argument-the-interface-does-not-take",
            passed.node.span.clone(),
            format!(
                "'{implementation}/{action}' passes on '{argument}', and '{interface}/{action}' \
                 takes no argument called that."
            ),
            format!(
                "Write one of the arguments '{interface}/{action}' takes: {}.",
                takes
                    .map(|t| t.keys().cloned().collect::<Vec<_>>().join(", "))
                    .unwrap_or_else(|| "(it takes none)".into())
            ),
        ));
    }
}

/// An agent that names an interface and one of its implementations is offered
/// the same capability twice under two names.
fn both_used(
    document: &Node,
    collection: &str,
    implementations: &BTreeMap<&str, Vec<&str>>,
    diags: &mut Diagnostics,
) {
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        return;
    };
    for (agent, entry) in agents {
        let uses: Vec<&str> = entry
            .node
            .get("uses")
            .map(crate::workflows::list)
            .into_iter()
            .flatten()
            .filter_map(Node::as_str)
            .map(str::trim)
            .collect();
        for (interface, theirs) in implementations {
            if !uses.contains(interface) {
                continue;
            }
            for own in theirs.iter().filter(|o| uses.contains(o)) {
                diags.push(Diagnostic::warning(
                    "loader/the-interface-and-one-of-its-own",
                    at(&entry.node, "uses", &entry.key_span),
                    format!(
                        "'{agent}' uses both '{interface}' and '{own}', which implements it, so \
                         the model is offered the same {collection} twice under two names."
                    ),
                    format!(
                        "Keep '{interface}' to let each run choose, or keep '{own}' to pin it — \
                         not both."
                    ),
                ));
            }
        }
    }
}

/// Put each interface's own lines into every entry that implements it.
///
/// After [`check`] has refused an implementation that restates the contract,
/// this writes the contract in: every action an implementation offers carries
/// its interface's `takes:`, `answers-with:` and every governing line, with the
/// implementation's own `calls:`, `passes:` and the rest laid on top — so the
/// approval rules, the same-request-key checks and every runtime below this
/// read an implementation exactly as if it had been written out longhand,
/// which is the promise `derive.rs` makes for `based-on:`. The routing words a
/// model chooses by (`description:`, `use-when:` and the rest) are the
/// interface's wherever the implementation wrote none, because a model offered
/// `email` is choosing an email tool, not Gmail.
pub fn inherit(document: &mut Node) {
    for (collection, _, _) in KINDS {
        let Some(entries) = document.get(collection).and_then(Node::as_map) else {
            continue;
        };
        let contracts: BTreeMap<String, Node> = entries
            .iter()
            .filter(|(_, e)| yes(&e.node, "interface"))
            .map(|(k, e)| (k.clone(), e.node.clone()))
            .collect();
        let Some(entries) = document
            .as_map_mut()
            .and_then(|m| m.get_mut(collection))
            .and_then(|e| e.node.as_map_mut())
        else {
            continue;
        };
        for (_, entry) in entries.iter_mut() {
            let Some(of) = text(&entry.node, "implements").map(str::to_string) else {
                continue;
            };
            let Some(contract) = contracts.get(&of) else {
                continue;
            };
            let Some(own) = entry.node.as_map_mut() else {
                continue;
            };
            for field in [
                "description",
                "category",
                "use-when",
                "do-not-use-when",
                "if-unsure",
                "available-when",
            ] {
                if own.contains_key(field) {
                    continue;
                }
                if let Some(line) = contract.as_map().and_then(|m| m.get(field)) {
                    own.insert(field.to_string(), line.clone());
                }
            }
            let Some(wanted) = contract.get("actions").and_then(Node::as_map) else {
                continue;
            };
            let Some(actions) = own.get_mut("actions").and_then(|e| e.node.as_map_mut()) else {
                continue;
            };
            for (action, written) in actions.iter_mut() {
                let Some(base) = wanted.get(action).and_then(|e| e.node.as_map()) else {
                    continue;
                };
                let Some(lines) = written.node.as_map_mut() else {
                    continue;
                };
                for (field, line) in base {
                    // The implementation's own line wins only where it may
                    // say anything at all; `check` has refused the rest.
                    if !lines.contains_key(field) {
                        lines.insert(field.clone(), line.clone());
                    }
                }
            }
        }
    }
}
