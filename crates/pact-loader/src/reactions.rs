//! **Topics, events and reactions** (`docs/99-THE-PACT-LANGUAGE.md` §3): what
//! the work is about, what can happen while it is done, and what to do then.
//!
//! | Rule | Severity | Fires when |
//! |---|---|---|
//! | `loader/a-signal-says-one-thing` | error | an event, a reaction or a `listens-for:` line names no signal, or more than one |
//! | `loader/a-narrowing-with-nothing-to-narrow` | error | `when-this:` or `more-than:` beside `topic:` or `judged:`, `when-this:` at a moment that is not about a call, or a `when-this:` line that looks at a value instead of a call |
//! | `loader/a-signal-names-no-such-call` | error | a `when-this:` line names a tool, or an action of one, the workspace does not have |
//! | `loader/a-judge-reads-words` | error | `judged: yes` at a moment that carries no words |
//! | `loader/a-guess-cannot-stop` | error | `stop:` on a signal that can be a guess — a judgement, or a topic the agent or a judge notices |
//! | `loader/a-step-does-one-thing` | error | a `then:` step with no verb, or with two |
//! | `loader/asks-only-itself` | error | a reaction an agent names does nothing except consult or tell that same agent |
//! | `loader/a-topic-nothing-carries` | warning | a topic noticed only by tags that no tool, action or set of documents carries |
//! | `loader/a-tag-nobody-reads` | error | something is tagged with a topic whose `noticed-by:` leaves out `tags` |
//!
//! A reaction, event or topic that nothing names is `unnamed.rs`'s
//! `loader/nothing-points-at-it`, with the rest of the documents nothing names.
//!
//! # Why a guess may advise and may not stop
//!
//! Three things can say the work has turned to a subject: a tag on the tool
//! about to be used, the agent saying so, and a second model reading the step.
//! The first is exact. The other two can miss, and a rule that sometimes does
//! not run is worse than no rule when its author believes it is a guard. So a
//! guess may add advice — a reminder, another agent's answer — and the things
//! that END or HOLD work are written on something exact: a moment, a tag, or
//! an approval policy.
//!
//! # What is held at run time instead
//!
//! Two laws are about a run and cannot be read off a tree
//! (`pact_adapters.reactions`): a reaction being carried out does not fire
//! again beneath itself, and what a consulted agent costs is spent from the
//! limits of the run that woke it.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node};

use crate::conditions::{self, Position};
use crate::teams::says_yes;
use crate::workflows::list;

/// The moments that are about one call, where `when-this:` has a call to read.
const ABOUT_A_CALL: &[&str] = &["step.tool.before", "step.tool.completed"];

/// The moments that carry words a judge can read.
const CARRY_WORDS: &[&str] = &["turn.run.started", "step.message.after"];

/// The four things a `then:` step can do.
const VERBS: &[&str] = &["remind", "consult", "tell", "stop"];

/// What a signal is, once it has been found to be one thing.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Signal<'a> {
    Moment,
    Topic(&'a str),
    Judged,
}

/// Every rule, over the loaded document.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    let topics = root.get("topics").and_then(Node::as_map);
    let events = root.get("events").and_then(Node::as_map);
    let tools = root.get("tools").and_then(Node::as_map);

    let mut signals: std::collections::BTreeMap<&str, Option<Signal>> = Default::default();
    for (name, entry) in events.into_iter().flatten() {
        let found = signal(&format!("the event '{name}'"), &entry.node, tools, false, diags);
        signals.insert(name.as_str(), found);
    }

    for (name, entry) in root
        .get("reactions")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let what = format!("the reaction '{name}'");
        let found = match entry.node.get("event").and_then(Node::as_str) {
            Some(named) => {
                an_event_and_nothing_else(&what, &entry.node, diags);
                signals.get(named.trim()).copied().flatten()
            }
            None => signal(&what, &entry.node, tools, true, diags),
        };
        steps(name, &entry.node, found, topics, diags);
    }

    let agents = root.get("agents").and_then(Node::as_map);
    for (agent, entry) in agents.into_iter().flatten() {
        for line in entry.node.get("listens-for").map(list).unwrap_or_default() {
            one_of_two(agent, line, diags);
        }
        for named in entry.node.get("reactions").map(list).unwrap_or_default() {
            only_itself(root, agent, named, diags);
        }
    }

    tags(root, topics, diags);
}

/// What one event or reaction waits for — refusing it when it is written as no
/// signal, as two, or with a narrowing that has nothing to narrow.
fn signal<'a>(
    what: &str,
    node: &'a Node,
    tools: Option<&Map>,
    may_say_on: bool,
    diags: &mut Diagnostics,
) -> Option<Signal<'a>> {
    let at = node.get("at");
    let topic = node.get("topic");
    let judged = node.get("judged").filter(|n| says_yes(Some(n)));
    let narrowing: Vec<(&str, &Node)> = ["when-this", "more-than"]
        .into_iter()
        .filter_map(|k| node.get(k).map(|n| (k, n)))
        .collect();

    let found = match (judged, topic, at) {
        (Some(_), None, _) => Signal::Judged,
        (None, Some(t), None) => Signal::Topic(t.as_str().unwrap_or_default().trim()),
        (None, None, Some(_)) => Signal::Moment,
        (None, None, None) => {
            let ways = if may_say_on {
                "`event:` naming an event, or one of `at:`, `topic:` and `judged: yes` here"
            } else {
                "one of `at:`, `topic:` and `judged: yes`"
            };
            diags.push(Diagnostic::error(
                "loader/a-signal-says-one-thing",
                node.span.clone(),
                format!("{} does not say what it waits for, so it never happens.", cap(what)),
                format!("Add {ways}."),
            ));
            return None;
        }
        _ => {
            let second = topic.or(at).map_or_else(|| node.span.clone(), |n| n.span.clone());
            diags.push(Diagnostic::error(
                "loader/a-signal-says-one-thing",
                second,
                format!(
                    "{} waits for two different things at once — a topic, and a moment or a \
                     judgement — and nothing says whether it needs either or both.",
                    cap(what)
                ),
                "Keep one. For both, write two and give them the same `then:`.",
            ));
            return None;
        }
    };

    match found {
        Signal::Moment => {
            let moment = at.and_then(Node::as_str).unwrap_or_default().trim();
            if let Some(lines) = node.get("when-this") {
                if ABOUT_A_CALL.contains(&moment) {
                    for line in list(lines) {
                        a_call(what, line, tools, diags);
                    }
                } else {
                    diags.push(Diagnostic::error(
                        "loader/a-narrowing-with-nothing-to-narrow",
                        lines.span.clone(),
                        format!(
                            "{} says which calls it is about (`when-this:`), and `{moment}` \
                             is not a moment that is about a call.",
                            cap(what)
                        ),
                        format!(
                            "Write `at: step.tool.before` (a tool is about to be called) or \
                             `at: step.tool.completed` (one has answered) — or take \
                             `when-this:` out to mean every `{moment}`."
                        ),
                    ));
                }
            }
        }
        Signal::Topic(_) | Signal::Judged => {
            for (key, n) in &narrowing {
                let beside = if found == Signal::Judged { "judged: yes" } else { "topic:" };
                diags.push(Diagnostic::error(
                    "loader/a-narrowing-with-nothing-to-narrow",
                    n.span.clone(),
                    format!(
                        "{} writes `{key}:` beside `{beside}`, and `{key}:` narrows a moment \
                         — there is no moment here for it to narrow.",
                        cap(what)
                    ),
                    format!("Take `{key}:` out, or wait for a moment instead: `at: step.tool.before`."),
                ));
            }
            if found == Signal::Judged
                && let Some(at) = at
                && !CARRY_WORDS.contains(&at.as_str().unwrap_or_default().trim())
            {
                diags.push(Diagnostic::error(
                    "loader/a-judge-reads-words",
                    at.span.clone(),
                    format!(
                        "{} is judged at `{}`, and a judge reads words — that moment carries \
                         none.",
                        cap(what),
                        at.as_str().unwrap_or_default().trim()
                    ),
                    "Write `at: step.message.after` to read what the agent wrote in a step \
                     (what you get if you leave `at:` out), or `at: turn.run.started` to read \
                     what the customer wrote.",
                ));
            }
        }
    }
    Some(found)
}

/// A reaction that names an event says nothing else about what it waits for.
fn an_event_and_nothing_else(what: &str, node: &Node, diags: &mut Diagnostics) {
    for key in ["at", "topic", "judged", "when-this", "more-than"] {
        if let Some(n) = node.get(key) {
            diags.push(Diagnostic::error(
                "loader/a-signal-says-one-thing",
                n.span.clone(),
                format!(
                    "{} names the event it waits for (`event:`) and also writes `{key}:`, so two \
                     places say what it waits for.",
                    cap(what)
                ),
                format!("Take `{key}:` out, or take `event:` out and say it all here."),
            ));
        }
    }
}

/// One `when-this:` line of a signal: it looks at a call, and the call exists.
fn a_call(what: &str, line: &Node, tools: Option<&Map>, diags: &mut Diagnostics) {
    let Some(written) = line.get("tool").and_then(Node::as_str).map(str::trim) else {
        diags.push(Diagnostic::error(
            "loader/a-narrowing-with-nothing-to-narrow",
            line.span.clone(),
            format!(
                "{} is about a call, and this line does not name one — it has no `tool:`.",
                cap(what)
            ),
            "Write `tool: <tool>` for every action of a tool, or `tool: <tool>/<action>` for \
             one, with `arg:` for an argument to compare.",
        ));
        return;
    };
    let (tool, action) = written.split_once('/').map_or((written, ""), |(t, a)| (t.trim(), a.trim()));
    let known: Vec<&str> = tools.map(|m| m.keys().map(String::as_str).collect()).unwrap_or_default();
    let span = line.get("tool").map_or_else(|| line.span.clone(), |n| n.span.clone());
    let Some(found) = tools.and_then(|m| m.get(tool)) else {
        diags.push(Diagnostic::error(
            "loader/a-signal-names-no-such-call",
            span,
            format!(
                "{} is about calls to '{tool}', and this workspace has no tool by that name \
                 — so it never happens.",
                cap(what)
            ),
            match pact_schema::suggest::closest(tool, &known) {
                Some(near) => format!("Did you mean `{near}`?"),
                None if known.is_empty() => "Add the tool under `tools:` first.".to_string(),
                None => format!("The tools here are: {}.", known.join(", ")),
            },
        ));
        return;
    };
    let actions: Vec<&str> = found
        .node
        .get("actions")
        .and_then(Node::as_map)
        .map(|m| m.keys().map(String::as_str).collect())
        .unwrap_or_default();
    if !action.is_empty() && !actions.contains(&action) {
        diags.push(Diagnostic::error(
            "loader/a-signal-names-no-such-call",
            span,
            format!(
                "{} is about '{action}' on '{tool}', and '{tool}' has no action by that \
                 name — so it never happens.",
                cap(what)
            ),
            match pact_schema::suggest::closest(action, &actions) {
                Some(near) => format!("Did you mean `{tool}/{near}`?"),
                None if actions.is_empty() => {
                    format!("Write `tool: {tool}` to mean every call to it.")
                }
                None => format!("The actions of '{tool}' are: {}.", actions.join(", ")),
            },
        ));
        return;
    }
    // The comparison itself — a figure of the right shape, one comparing word —
    // is the one condition grammar's to hold, read as it is for an approval
    // rule: a signal, like a gate, has only the call.
    conditions::line(line, Position::Policy, None, &|_| None, diags);
}

/// A reaction's `then:` — each step one verb, and no `stop:` on a guess.
fn steps(
    name: &str,
    node: &Node,
    found: Option<Signal>,
    topics: Option<&Map>,
    diags: &mut Diagnostics,
) {
    let a_guess = match found {
        Some(Signal::Judged) => Some("it is judged, and a judge can be wrong".to_string()),
        Some(Signal::Topic(t)) => guessed_by(topics, t).map(|who| {
            format!("the topic '{t}' is noticed by {who}, which can miss")
        }),
        _ => None,
    };
    for step in node.get("then").map(list).unwrap_or_default() {
        let Some(map) = step.as_map() else { continue };
        let said: Vec<&str> = VERBS.iter().copied().filter(|v| map.contains_key(*v)).collect();
        if said.len() != 1 {
            diags.push(Diagnostic::error(
                "loader/a-step-does-one-thing",
                step.span.clone(),
                if said.is_empty() {
                    format!("This step of the reaction '{name}' does not say what to do.")
                } else {
                    format!(
                        "This step of the reaction '{name}' says {} at once, and the order \
                         they happen in is the order of the list.",
                        said.iter().map(|v| format!("`{v}:`")).collect::<Vec<_>>().join(" and ")
                    )
                },
                "Write one of `remind:`, `consult:`, `tell:` and `stop:` on each line, with a \
                 `- ` in front.",
            ));
            continue;
        }
        if said[0] == "stop"
            && let Some(why) = &a_guess
        {
            diags.push(Diagnostic::error(
                "loader/a-guess-cannot-stop",
                step.span.clone(),
                format!(
                    "The reaction '{name}' stops the run on a guess — {why}. A run that is \
                     stopped only when a guess is right is not guarded."
                ),
                "Stop on something exact: a tagged tool (`noticed-by: [tags]`), or a moment \
                 with `at:`. On a guess, `remind:` or `consult:` instead.",
            ));
        }
    }
}

/// Who notices this topic by guessing, in words — `None` when only tags do.
fn guessed_by(topics: Option<&Map>, topic: &str) -> Option<&'static str> {
    let noticed = topics?.get(topic)?.node.get("noticed-by")?;
    let words: Vec<&str> = list(noticed).into_iter().filter_map(Node::as_str).map(str::trim).collect();
    match (words.contains(&"the-agent"), words.contains(&"a-judge")) {
        (true, true) => Some("the agent and by a judge"),
        (true, false) => Some("the agent"),
        (false, true) => Some("a judge"),
        (false, false) => None,
    }
}

/// A `listens-for:` line names a topic or an event — one of the two.
fn one_of_two(agent: &str, line: &Node, diags: &mut Diagnostics) {
    let (topic, event) = (line.get("topic"), line.get("event"));
    let message = match (topic, event) {
        (Some(_), Some(_)) => format!(
            "'{agent}' listens for a topic and an event on one line, and nothing says \
             whether it wants either or both."
        ),
        (None, None) => format!(
            "'{agent}' listens for nothing on this line — it names no `topic:` and no `event:`."
        ),
        _ => return,
    };
    diags.push(Diagnostic::error(
        "loader/a-signal-says-one-thing",
        line.span.clone(),
        message,
        "Write one of `topic:` and `event:` on each line. To hear both, write two lines.",
    ));
}

/// A reaction an agent names that does nothing except wake that same agent.
fn only_itself(root: &Node, agent: &str, named: &Node, diags: &mut Diagnostics) {
    let Some(reaction) = named
        .as_str()
        .and_then(|n| root.get("reactions")?.get(n.trim()))
    else {
        return;
    };
    let then = reaction.get("then").map(list).unwrap_or_default();
    if then.is_empty() {
        return;
    }
    let all_to_itself = then.iter().all(|step| {
        ["consult", "tell"]
            .iter()
            .any(|v| step.get(v).and_then(Node::as_str).map(str::trim) == Some(agent))
    });
    if all_to_itself {
        diags.push(Diagnostic::error(
            "loader/asks-only-itself",
            named.span.clone(),
            format!(
                "'{agent}' names the reaction '{}', and all that reaction does is consult or \
                 tell '{agent}' — an agent is never woken by its own work, so here it does \
                 nothing.",
                named.as_str().unwrap_or_default().trim()
            ),
            format!(
                "Take it off '{agent}' and list it on the agents whose work '{agent}' should \
                 hear about — or write `listens-for:` on '{agent}' instead."
            ),
        ));
    }
}

/// Tags and the topics they name: a topic only tags can raise has a tag
/// somewhere, and a tag is on a topic that reads tags.
fn tags(root: &Node, topics: Option<&Map>, diags: &mut Diagnostics) {
    let mut carried: std::collections::BTreeSet<&str> = Default::default();
    let mut written: Vec<(&str, Span)> = Vec::new();
    for collection in ["tools", "knowledge"] {
        for (_, entry) in root.get(collection).and_then(Node::as_map).into_iter().flatten() {
            let mut holders = vec![&entry.node];
            if let Some(actions) = entry.node.get("actions").and_then(Node::as_map) {
                holders.extend(actions.values().map(|e| &e.node));
            }
            for holder in holders {
                for tag in holder.get("topics").map(list).unwrap_or_default() {
                    if let Some(t) = tag.as_str().map(str::trim) {
                        carried.insert(t);
                        written.push((t, tag.span.clone()));
                    }
                }
            }
        }
    }
    for (name, entry) in topics.into_iter().flatten() {
        let noticed: Vec<&str> = entry
            .node
            .get("noticed-by")
            .map(list)
            .unwrap_or_default()
            .into_iter()
            .filter_map(Node::as_str)
            .map(str::trim)
            .collect();
        let reads_tags = noticed.is_empty() || noticed.contains(&"tags");
        if reads_tags && noticed.len() <= 1 && !carried.contains(name.as_str()) {
            diags.push(Diagnostic::warning(
                "loader/a-topic-nothing-carries",
                entry.key_span.clone(),
                format!(
                    "The topic '{name}' is noticed by tags, and no tool, action or set of \
                     documents is tagged with it — so the work never turns to it."
                ),
                format!(
                    "Add `topics: [{name}]` to the tools this subject is about — or add \
                     `noticed-by: [tags, the-agent]` so the agent can say so itself."
                ),
            ));
        }
        if !reads_tags {
            for (tagged, span) in written.iter().filter(|(t, _)| *t == name.as_str()) {
                diags.push(Diagnostic::error(
                    "loader/a-tag-nobody-reads",
                    span.clone(),
                    format!(
                        "This is tagged '{tagged}', and that topic's `noticed-by:` leaves \
                         out `tags` — so the tag is read by nothing."
                    ),
                    format!("Add `tags` to the `noticed-by:` of the topic '{tagged}', or take the tag off."),
                ));
            }
        }
    }
}

fn cap(s: &str) -> String {
    let mut c = s.chars();
    match c.next() {
        Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        None => String::new(),
    }
}
