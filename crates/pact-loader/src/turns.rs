//! **A conversation written down** (96 §D): an agent's `turns:`, a variant's,
//! and an eval case's.
//!
//! Five speakers and one order rule, because those are what survives every
//! provider's chat format. Anthropic and Gemini take standing instructions
//! once, ahead of the conversation, and OpenAI takes them anywhere; a `system`
//! turn written after somebody has spoken is therefore one that two of the
//! three can only carry by moving it, and a moved instruction is a different
//! conversation. So it is refused here rather than moved in silence.
//!
//! A tool call in an example is the other thing providers agree on and authors
//! get wrong: every call is answered, by the very next turn, or the request is
//! refused by the provider (Anthropic) or the model learns that calls go
//! unanswered (everyone else).
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/a-standing-instruction-in-the-middle` | a `system` or `developer` turn after a turn from anybody else |
//! | `loader/a-turn-that-says-nothing` | a turn with nothing in it: no `says:` (or `attaches:`, or `calls:`), or a `tool` turn with no `answer:` |
//! | `loader/a-line-this-speaker-cannot-write` | `calls:` on a turn that is not the agent's, `answer:` on one that is not a tool's, `says:` on a tool's |
//! | `loader/a-call-nobody-answers` | an `agent` turn that `calls:` something is not followed by a `tool` turn |
//! | `loader/an-answer-nobody-asked-for` | a `tool` turn that does not follow an `agent` turn that `calls:` something |
//! | `loader/a-call-to-something-it-cannot-use` | `calls:` names a tool the agent does not use, or an action that tool does not have |
//! | `loader/an-attachment-that-is-not-there` | `attaches:` names something the agent (or the case) does not have |
//! | `loader/a-case-that-ends-with-the-agent` | an eval case's last turn is not the person's or a tool's — there is no next reply to grade |

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;

/// The answer shapes that can travel as an attachment.
const MEDIA: &[&str] = &[
    "images",
    "a picture",
    "pictures",
    "an image",
    "list of images",
    "audio",
    "a recording",
    "a voice message",
    "list of audio",
    "documents",
    "a pdf",
    "list of documents",
    "video",
    "a video",
    "a clip",
    "list of videos",
    "file",
    "a file",
    "an attachment",
    "list of files",
];

/// Where a written conversation sits, which decides what its lines may name.
enum Owner<'a> {
    /// An agent (or one of its variants): calls are held to its `uses:`,
    /// attachments to its media `run-inputs:`.
    Agent { name: &'a str, node: &'a Node },
    /// An eval case: attachments are its own `with:` names, and the last turn
    /// is what the graded reply answers.
    Case { name: &'a str, node: &'a Node },
}

pub fn check(document: &Node, diags: &mut Diagnostics) {
    for (name, entry) in document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let owner = Owner::Agent {
            name,
            node: &entry.node,
        };
        if let Some(turns) = entry.node.get("turns") {
            conversation(document, &owner, turns, diags);
        }
        for (_, variant) in entry
            .node
            .get("variants")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            if let Some(turns) = variant.node.get("turns") {
                conversation(document, &owner, turns, diags);
            }
        }
    }
    for (name, entry) in document
        .get("evals")
        .and_then(|e| e.get("cases"))
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        if let Some(turns) = entry.node.get("turns") {
            let owner = Owner::Case {
                name,
                node: &entry.node,
            };
            conversation(document, &owner, turns, diags);
        }
    }
}

fn word<'a>(turn: &'a Node, field: &str) -> Option<&'a str> {
    turn.get(field).and_then(Node::as_str).map(str::trim)
}

fn at(turn: &Node, field: &str) -> Span {
    turn.as_map()
        .and_then(|m| m.get(field))
        .map(|e| e.key_span.clone().merge(&e.node.span))
        .unwrap_or_else(|| turn.span.clone())
}

fn conversation(document: &Node, owner: &Owner, written: &Node, diags: &mut Diagnostics) {
    let Some(turns) = written.as_list() else {
        return;
    };
    let who = match owner {
        Owner::Agent { name, .. } => format!("'{name}'"),
        Owner::Case { name, .. } => format!("the case '{name}'"),
    };
    let mut spoken = false;
    for (i, turn) in turns.iter().enumerate() {
        if turn.as_map().is_none() {
            continue;
        }
        let Some(from) = word(turn, "from") else {
            continue;
        };
        let standing = matches!(from, "system" | "developer");
        if standing && spoken {
            diags.push(Diagnostic::error(
                "loader/a-standing-instruction-in-the-middle",
                at(turn, "from"),
                format!(
                    "Turn {} of {who} is from `{from}` and comes after somebody has spoken. \
                     Standing instructions come first: two of the three ways a provider \
                     carries them cannot put one in the middle without moving it.",
                    i + 1
                ),
                "Move this turn to the start, or put its words in `instructions:`.",
            ));
        }
        spoken |= !standing;
        lines_for(turn, from, i, &who, diags);
        let calls = word(turn, "calls");
        if let Some(call) = calls
            && from == "agent"
        {
            {
                if let Owner::Agent { name, node } = owner {
                    reachable(document, name, node, turn, call, diags);
                }
                let answered = turns
                    .get(i + 1)
                    .and_then(|next| word(next, "from"))
                    .is_some_and(|f| f == "tool");
                if !answered {
                    diags.push(Diagnostic::error(
                        "loader/a-call-nobody-answers",
                        at(turn, "calls"),
                        format!(
                            "Turn {} of {who} calls `{call}`, and the turn after it is not \
                             what the tool handed back — a provider refuses a call with no \
                             answer, and a model shown one learns that calls go unanswered.",
                            i + 1
                        ),
                        "Add a turn straight after it with `from: tool` and `answer:` saying \
                         what came back.",
                    ));
                }
            }
        }
        if from == "tool" {
            let asked = i
                .checked_sub(1)
                .and_then(|p| turns.get(p))
                .is_some_and(|prev| {
                    word(prev, "from") == Some("agent") && prev.get("calls").is_some()
                });
            if !asked {
                diags.push(Diagnostic::error(
                    "loader/an-answer-nobody-asked-for",
                    at(turn, "from"),
                    format!(
                        "Turn {} of {who} is what a tool handed back, and the turn before it \
                         is not the agent calling one.",
                        i + 1
                    ),
                    "Put an `agent` turn with `calls: <tool>/<action>` straight before it.",
                ));
            }
        }
        attachments(owner, turn, i, &who, diags);
    }
    if let Owner::Case { .. } = owner {
        let last = turns.iter().rev().find_map(|t| word(t, "from"));
        if let Some(from) = last.filter(|f| !matches!(*f, "user" | "tool")) {
            diags.push(Diagnostic::error(
                "loader/a-case-that-ends-with-the-agent",
                turns
                    .last()
                    .map_or_else(|| written.span.clone(), |t| t.span.clone()),
                format!(
                    "The last turn of {who} is from `{from}`, so there is no next reply from the \
                     agent for `expect:` to be about."
                ),
                "End the conversation with the person's turn (or a tool's), and say what the \
                 agent should reply in `expect:`.",
            ));
        }
    }
}

fn lines_for(turn: &Node, from: &str, i: usize, who: &str, diags: &mut Diagnostics) {
    let has = |f: &str| turn.get(f).is_some();
    let wrong = |field: &str, why: &str, diags: &mut Diagnostics| {
        diags.push(Diagnostic::error(
            "loader/a-line-this-speaker-cannot-write",
            at(turn, field),
            format!(
                "Turn {} of {who} is from `{from}` and writes `{field}:`, which {why}.",
                i + 1
            ),
            format!("Take `{field}:` out of this turn."),
        ));
    };
    if has("calls") && from != "agent" {
        wrong(
            "calls",
            "only the agent's turn can — it is the agent that calls tools",
            diags,
        );
    }
    if has("answer") && from != "tool" {
        wrong(
            "answer",
            "only a tool's turn has — it is what a tool handed back",
            diags,
        );
    }
    if has("says") && from == "tool" {
        wrong(
            "says",
            "a tool's turn does not have — write what came back as `answer:`",
            diags,
        );
    }
    let empty = if from == "tool" {
        !has("answer")
    } else {
        !has("says") && !has("attaches") && !has("calls")
    };
    if empty {
        diags.push(Diagnostic::error(
            "loader/a-turn-that-says-nothing",
            turn.span.clone(),
            format!(
                "Turn {} of {who} is from `{from}` and has nothing in it.",
                i + 1
            ),
            if from == "tool" {
                "Write what the tool handed back as `answer:`."
            } else {
                "Write what is said as `says:`, or take the turn out."
            },
        ));
    }
}

fn reachable(
    document: &Node,
    agent: &str,
    node: &Node,
    turn: &Node,
    call: &str,
    diags: &mut Diagnostics,
) {
    let (tool, action) = call.split_once('/').unwrap_or((call, ""));
    let uses: Vec<&str> = node
        .get("uses")
        .map(crate::workflows::list)
        .into_iter()
        .flatten()
        .filter_map(Node::as_str)
        .map(str::trim)
        .collect();
    let refuse = |message: String, fix: String, diags: &mut Diagnostics| {
        diags.push(Diagnostic::error(
            "loader/a-call-to-something-it-cannot-use",
            at(turn, "calls"),
            message,
            fix,
        ));
    };
    if !uses.contains(&tool) {
        refuse(
            format!(
                "'{agent}' is shown calling `{call}`, and '{tool}' is not one of the things it \
                 uses — the example teaches a call it can never make."
            ),
            format!(
                "Add '{tool}' to `uses:`, or call one of: {}.",
                uses.join(", ")
            ),
            diags,
        );
        return;
    }
    let actions = document
        .get("tools")
        .and_then(|t| t.get(tool))
        .and_then(|t| t.get("actions"))
        .and_then(Node::as_map);
    if let Some(actions) = actions
        && !actions.contains_key(action)
    {
        let have: Vec<String> = actions.keys().map(|a| format!("{tool}/{a}")).collect();
        refuse(
            format!("'{agent}' is shown calling `{call}`, and '{tool}' has no such action."),
            format!("Call one of: {}.", have.join(", ")),
            diags,
        );
    }
}

fn attachments(owner: &Owner, turn: &Node, i: usize, who: &str, diags: &mut Diagnostics) {
    for item in turn
        .get("attaches")
        .map(crate::workflows::list)
        .into_iter()
        .flatten()
    {
        let Some(written) = item.as_str().map(str::trim) else {
            continue;
        };
        let (fits, fix) = match owner {
            Owner::Agent { node, .. } => {
                let name = written.strip_prefix("run-inputs.");
                let shape = name.and_then(|n| {
                    node.get("run-inputs")
                        .and_then(|r| r.get(n))
                        .and_then(Node::as_str)
                });
                let media: Vec<String> = node
                    .get("run-inputs")
                    .and_then(Node::as_map)
                    .into_iter()
                    .flatten()
                    .filter(|(_, e)| e.node.as_str().is_some_and(is_media))
                    .map(|(k, _)| format!("run-inputs.{k}"))
                    .collect();
                (
                    shape.is_some_and(is_media),
                    if media.is_empty() {
                        "Add a run input of a kind that can be attached — `photo: images` — \
                         under `run-inputs:`, and attach it as `run-inputs.photo`."
                            .to_string()
                    } else {
                        format!("Attach one of: {}.", media.join(", "))
                    },
                )
            }
            Owner::Case { node, .. } => {
                let with = node.get("with").and_then(Node::as_map);
                let names: Vec<&str> = with
                    .into_iter()
                    .flatten()
                    .map(|(k, _)| k.as_str())
                    .collect();
                (
                    names.contains(&written),
                    if names.is_empty() {
                        "Put the file under the case's `with:`, and attach it by that name."
                            .to_string()
                    } else {
                        format!("Attach one of the case's own: {}.", names.join(", "))
                    },
                )
            }
        };
        if !fits {
            diags.push(Diagnostic::error(
                "loader/an-attachment-that-is-not-there",
                item.span.clone(),
                format!(
                    "Turn {} of {who} attaches '{written}', which is not a picture, recording, \
                     document or file it has.",
                    i + 1
                ),
                fix,
            ));
        }
    }
}

fn is_media(shape: &str) -> bool {
    let s = shape.trim().to_ascii_lowercase();
    let s = s.strip_suffix(", optional").unwrap_or(&s).trim();
    MEDIA.contains(&s)
}
