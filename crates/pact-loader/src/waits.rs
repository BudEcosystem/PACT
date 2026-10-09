//! **Waits, reminders and time** (02W §2.8, §2.10, §3).
//!
//! A wait is still a `question` (WAIT-2): `asked-of:` gains `the-clock` and
//! this workspace's ports, so a workflow can wait for a person, a group, an
//! event or the clock with one construct (R12 reopened). What no single value
//! can say about one is held here:
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/nobody-can-answer` *(extended, CHK-7)* | WF-21 | a question a workflow asks names nobody; `the-clock` with no `answer-within:`; a question only the clock or events answer that asks for an `answer:`; a reminder or milestone with none or two of its four actions |
//! | `loader/a-question-with-nothing-to-say` | WF-22 | `asked-of:` names a person or a group and `says:` or `answer:` is missing |
//! | `loader/a-time-with-no-zone` | WF-30 | a moment read from a date (`at:`) or counted in business days, in a workflow, when neither the line nor the workspace names a zone |
//! | `loader/a-pause-for-something-that-does-not-wait` | WF-32 | `paused-during:` names a stage that does not `ask-someone` |
//! | `loader/asked-in-for-someone-who-chooses` | WF-36 | `asked-in:` on a question asked of a person, a role, a team, the clock or a port |
//! | `loader/an-agent-only-spelling` | WF-40 | in a workflow, `if-nobody-answers:` on a question it asks, or `when-it-runs-out: answer-with-what-it-has` |
//! | `loader/a-workflow-only-spelling` | new | what only a workflow reads, written where an agent reads it: a question no workflow asks that is asked of the clock or a port, or whose `answer-within:` is a moment; an agent's `finishes-within:` written as a moment, or a `when-it-runs-out:` choice only a workflow has |
//! | `loader/a-line-this-stage-never-reads` | WF-3 | an `ask-someone` stage's `then.answered`/`declined` when only the clock or events answer it, or `then.heard` when no port does; an agent's `limits:` line only a workflow reads |
//! | `loader/an-agent-only-spelling`, `loader/a-workflow-only-spelling` | N58 | a workspace question both an agent and a workflow ask, whichever way it is written: once, at `if-nobody-answers:` when written, else at the question |
//! | `schema/missing-field` | shipped | `if-nobody-answers:` missing on a question no workflow asks (the schema's `required: yes`, moved here) |
//!
//! **Who answers** is told by spelling alone, since people are the host's to
//! bind (`asked-of:` has no `names:`): `the-clock`; a port of this workspace;
//! `the-requester`; a binding (a person or an outside contact, known when the
//! run reads it); a name beginning with `#`, a channel; anything else a person,
//! a role or a team, reached the way they chose.
//!
//! **Which questions a workflow asks**: its own `questions:`, and every
//! workspace question an `asks:` inside it names (a stage's, or a limit's).
//! Every other workspace question is an agent's, and keeps the lines an
//! agent's runtime reads.

use crate::bindings::is_binding;
use crate::workflows;
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node, Value};
use std::collections::BTreeMap;

/// The answerer that is the clock: a time-only wait (02W §2.8).
pub(crate) const THE_CLOCK: &str = "the-clock";
/// The person who started the run, supplied by the host.
const THE_REQUESTER: &str = "the-requester";
/// A reminder's four actions; exactly one is written (WF-21).
const ACTIONS: [&str; 4] = ["nudges", "tells", "hands-over-to", "runs"];
/// `when-it-runs-out:` choices only a workflow has (02W §2.10).
pub(crate) const WORKFLOW_CHOICES: [&str; 5] = [
    "use-a-backup",
    "carry-on",
    "wait-for-a-new-version",
    "undo",
    "wait-its-turn",
];
/// The agents' way of carrying on, written `carry-on` in a workflow (WF-40).
const ANSWER_WITH_WHAT_IT_HAS: &str = "answer-with-what-it-has";
/// `limits:` lines only a workflow's runtime reads (02W §2.10).
const WORKFLOW_LIMIT_LINES: [&str; 4] = [
    "starts-from",
    "paused-during",
    "milestones",
    "at-once-at-most",
];

/// Who an `asked-of:` entry is, as far as the tree can tell.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Answerer {
    Clock,
    Port,
    Requester,
    Binding,
    Channel,
    Named,
}

impl Answerer {
    pub(crate) fn of(document: &Node, written: &str) -> Answerer {
        let w = written.trim();
        if w == THE_CLOCK {
            Answerer::Clock
        } else if document.get("ports").and_then(|p| p.get(w)).is_some() {
            Answerer::Port
        } else if w == THE_REQUESTER {
            Answerer::Requester
        } else if is_binding(w) {
            Answerer::Binding
        } else if w.starts_with('#') {
            Answerer::Channel
        } else {
            Answerer::Named
        }
    }

    /// A person, a group or an outside contact: somebody who reads wording.
    pub(crate) fn reads(self) -> bool {
        !matches!(self, Answerer::Clock | Answerer::Port)
    }
}

/// Every `asked-of:` entry of a question, with who each is.
pub(crate) fn answerers<'n>(document: &Node, q: &'n Node) -> Vec<(&'n Node, Answerer)> {
    q.get("asked-of")
        .map(workflows::list)
        .unwrap_or_default()
        .into_iter()
        .filter_map(|n| n.as_str().map(|s| (n, Answerer::of(document, s))))
        .collect()
}

/// The question a workflow's `asks:` names: its own first, then the workspace's.
pub(crate) fn question_of<'d>(
    document: &'d Node,
    workflow: &'d Node,
    name: &str,
) -> Option<&'d Node> {
    workflow
        .get("questions")
        .and_then(|q| q.get(name))
        .or_else(|| document.get("questions").and_then(|q| q.get(name)))
}

/// Every check on waits and time, over the loaded document.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let asked = asked_by_workflows(document);
    let agents_ask = asked_by_agents(document);
    let workflows_map = document.get("workflows").and_then(Node::as_map);
    for (flow, entry) in workflows_map.into_iter().flatten() {
        for (name, q) in entry
            .node
            .get("questions")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            a_workflows_question(document, name, &q.node, flow, true, diags);
        }
        limits_of_a_workflow(flow, &entry.node, diags);
        exits(document, &entry.node, diags);
    }
    for (name, q) in document
        .get("questions")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        match (asked.get(name.as_str()), agents_ask.get(name.as_str())) {
            (Some(flow), Some(agent)) => {
                asked_by_both(name, &q.node, flow, agent, diags);
                a_workflows_question(document, name, &q.node, flow, false, diags);
            }
            (Some(flow), None) => a_workflows_question(document, name, &q.node, flow, true, diags),
            (None, _) => an_agents_question(document, name, &q.node, diags),
        }
    }
    for (_, q) in every_question(document) {
        if !unloaded(q) {
            said_to_somebody(document, q, diags);
        }
    }
    for (agent, entry) in document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        limits_of_an_agent(agent, &entry.node, diags);
    }
    if document
        .get("time-zone")
        .and_then(Node::as_str)
        .is_none_or(|z| z.trim().is_empty())
    {
        no_zone(document, &asked, diags);
    }
}

/// Workspace questions an `asks:` inside a workflow names, with the first
/// workflow that asks each. A workflow's own question of the same name wins.
fn asked_by_workflows(document: &Node) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    for (flow, entry) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let own = entry.node.get("questions").and_then(Node::as_map);
        let mut names: Vec<&str> = Vec::new();
        if let Some(asks) = entry
            .node
            .get("limits")
            .and_then(|l| l.get("asks"))
            .and_then(Node::as_str)
        {
            names.push(asks);
        }
        for (_, stage) in every_stage(&entry.node) {
            for n in [
                stage.get("asks"),
                stage.get("limits").and_then(|l| l.get("asks")),
            ]
            .into_iter()
            .flatten()
            {
                if let Some(s) = n.as_str() {
                    names.push(s);
                }
            }
        }
        for name in names.into_iter().map(str::trim) {
            if !own.is_some_and(|o| o.contains_key(name)) {
                out.entry(name.to_string()).or_insert_with(|| flow.clone());
            }
        }
    }
    out
}

/// Workspace questions an agent's run can stop at (the lines `pact waits`
/// lists for it), with the first agent that asks each and where.
fn asked_by_agents(document: &Node) -> BTreeMap<String, (String, Span)> {
    let mut out = BTreeMap::new();
    for (agent, entry) in document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        for (_, question, span, _) in crate::report::asking_lines(document, &entry.node) {
            out.entry(question).or_insert_with(|| (agent.clone(), span));
        }
    }
    out
}

/// N58: a workspace question both an agent and a workflow ask. The agent's
/// runtime needs `if-nobody-answers:` and the workflow refuses it, so no way
/// of writing it serves both; whichever way it is written, it is refused once.
fn asked_by_both(
    name: &str,
    q: &Node,
    flow: &str,
    (agent, asked_at): &(String, Span),
    diags: &mut Diagnostics,
) {
    if unloaded(q) {
        return;
    }
    let both = format!("'{name}' is asked by the workflow '{flow}' and by the agent '{agent}'");
    let fix = format!(
        "Give each its own question: keep '{name}' for '{agent}', with `if-nobody-answers:`, \
         and write the one '{flow}' asks under its own `questions:`, without it — its stage's \
         `nobody-answered:` exit says what silence does."
    );
    let d = match key_span(q, "if-nobody-answers") {
        Some(at) => Diagnostic::error(
            "loader/an-agent-only-spelling",
            at,
            format!(
                "{both}, and says what to do when nobody answers with `if-nobody-answers:`, \
                 which the workflow refuses: in a workflow, silence goes where the asking \
                 stage's `nobody-answered:` exit says."
            ),
            fix,
        ),
        None => Diagnostic::error(
            "loader/a-workflow-only-spelling",
            q.span.start_of_block(),
            format!(
                "{both}, and has no `if-nobody-answers:`, as a workflow's question is written, \
                 so the agent's run would not know what to do when nobody answers."
            ),
            fix,
        ),
    };
    diags.push(d.with_related(asked_at.clone(), format!("'{agent}' asks '{name}' here")));
}

/// Every question in the tree: the workspace's and each workflow's own.
fn every_question(document: &Node) -> Vec<(&str, &Node)> {
    let mut out: Vec<(&str, &Node)> = Vec::new();
    for (name, q) in document
        .get("questions")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        out.push((name.as_str(), &q.node));
    }
    for (_, w) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        for (name, q) in w
            .node
            .get("questions")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            out.push((name.as_str(), &q.node));
        }
    }
    out
}

/// Every stage of a workflow, at any depth.
pub(crate) fn every_stage(workflow: &Node) -> Vec<(&str, &Node)> {
    fn walk<'n>(steps: &'n Map, out: &mut Vec<(&'n str, &'n Node)>) {
        for (name, e) in steps {
            out.push((name.as_str(), &e.node));
            if let Some(inner) = e.node.get("steps").and_then(Node::as_map) {
                walk(inner, out);
            }
        }
    }
    let mut out = Vec::new();
    if let Some(steps) = workflow.get("steps").and_then(Node::as_map) {
        walk(steps, &mut out);
    }
    out
}

/// A file that did not parse says nothing about what is in it.
fn unloaded(q: &Node) -> bool {
    q.get(pact_doc::UNLOADED).is_some()
}

/// Whether a line inside `q` is already told as a misspelt setting: its
/// absence is then that mistake said a second time.
fn misspelt_inside(q: &Node, diags: &Diagnostics) -> bool {
    diags.items().iter().any(|d| {
        d.rule == "schema/unknown-field"
            && d.span.file == q.span.file
            && d.span.byte_start >= q.span.byte_start
            && d.span.byte_end <= q.span.byte_end
    })
}

/// Push `d` unless the same rule already points at the same place.
fn push_once(diags: &mut Diagnostics, d: Diagnostic) {
    if !diags
        .items()
        .iter()
        .any(|x| x.rule == d.rule && x.span == d.span)
    {
        diags.push(d);
    }
}

fn key_span(node: &Node, key: &str) -> Option<Span> {
    node.as_map()
        .and_then(|m| m.get(key))
        .map(|e| e.key_span.clone())
}

/// A question a workflow asks: silence goes to the stage's `nobody-answered:`
/// exit, never to `if-nobody-answers:` (WF-40), and somebody is named (WF-21).
fn a_workflows_question(
    document: &Node,
    name: &str,
    q: &Node,
    flow: &str,
    only_a_workflow: bool,
    diags: &mut Diagnostics,
) {
    if unloaded(q) {
        return;
    }
    if only_a_workflow && let Some(at) = key_span(q, "if-nobody-answers") {
        diags.push(Diagnostic::error(
            "loader/an-agent-only-spelling",
            at,
            format!(
                "'{name}' is asked by the workflow '{flow}' and says what to do when nobody \
                 answers with `if-nobody-answers:`, which only an agent reads: in a workflow, \
                 silence goes where the asking stage's `nobody-answered:` exit says."
            ),
            "Delete `if-nobody-answers:` and write the stage's exit — `then: {nobody-answered: \
             <a stage>}`. A question an agent asks as well needs a question of its own."
                .to_string(),
        ));
    }
    if answerers(document, q).is_empty() && q.get("asked-of").is_some() {
        push_once(
            diags,
            Diagnostic::error(
                "loader/nobody-can-answer",
                key_span(q, "asked-of").unwrap_or_else(|| q.span.start_of_block()),
                format!(
                    "'{name}' names nobody to ask, so the run stops, nobody hears about it, and \
                     the deadline decides."
                ),
                "Write who answers — a team, `the-requester`, a port for an event, or \
                 `the-clock` with an `answer-within:` — like `asked-of: [ap-clerks]`."
                    .to_string(),
            ),
        );
    }
}

/// A question no workflow asks: an agent's, held to what an agent's runtime
/// reads — it says what silence does, and it waits only for people.
fn an_agents_question(document: &Node, name: &str, q: &Node, diags: &mut Diagnostics) {
    if unloaded(q) {
        return;
    }
    if q.get("if-nobody-answers").is_none() && !misspelt_inside(q, diags) {
        diags.push(Diagnostic::error(
            "schema/missing-field",
            q.span.start_of_block(),
            "A question must have an 'if-nobody-answers'.".to_string(),
            "Add a line: `if-nobody-answers: decline` — what to do when the time runs out: \
             `decline`, `escalate` or `stop-and-say-so`. A question only a workflow asks \
             leaves it out, and its stage's `nobody-answered:` exit says instead."
                .to_string(),
        ));
    }
    for (n, who) in answerers(document, q) {
        if matches!(who, Answerer::Clock | Answerer::Port) {
            let said = n.as_str().unwrap_or("").trim();
            diags.push(Diagnostic::error(
                "loader/a-workflow-only-spelling",
                n.span.clone(),
                format!(
                    "'{name}' is asked of '{said}', {}, and only a workflow waits for {}: no \
                     workflow asks '{name}', and an agent's run waits for people.",
                    if who == Answerer::Clock {
                        "the clock"
                    } else {
                        "a port, for an event"
                    },
                    if who == Answerer::Clock {
                        "the clock"
                    } else {
                        "events"
                    },
                ),
                "Ask the people who decide, or wait in a workflow that calls the agent — `does: \
                 ask-someone` with this question."
                    .to_string(),
            ));
        }
    }
    if let Some(within) = q.get("answer-within")
        && within.as_map().is_some()
    {
        diags.push(Diagnostic::error(
            "loader/a-workflow-only-spelling",
            within.span.clone(),
            format!(
                "'{name}' says when the time is up as a moment, and only a workflow reads one: no \
                 workflow asks '{name}', and an agent's wait is timed from when it was asked."
            ),
            "Write a length of time — `answer-within: 2 days` — or ask it from a workflow."
                .to_string(),
        ));
    }
}

/// WF-21, WF-22 and WF-36 on any question.
fn said_to_somebody(document: &Node, q: &Node, diags: &mut Diagnostics) {
    let name = question_name(document, q);
    let who = answerers(document, q);
    let people = who.iter().any(|(_, a)| a.reads());
    if people && !misspelt_inside(q, diags) {
        let missing: Vec<&str> = ["says", "answer"]
            .into_iter()
            .filter(|f| q.get(f).is_none())
            .collect();
        if !missing.is_empty() {
            let first = who
                .iter()
                .find(|(_, a)| a.reads())
                .and_then(|(n, _)| n.as_str())
                .unwrap_or("");
            diags.push(Diagnostic::error(
                "loader/a-question-with-nothing-to-say",
                q.span.start_of_block(),
                format!(
                    "'{name}' is asked of '{}', and it has no {}, so they would be asked nothing \
                     they could read or answer.",
                    first.trim(),
                    missing
                        .iter()
                        .map(|m| format!("`{m}:`"))
                        .collect::<Vec<_>>()
                        .join(" and "),
                ),
                "Write the words they read and the answer's shape — `says: May this be paid?` and \
                 `answer: {approved: yes or no}`."
                    .to_string(),
            ));
        }
    }
    if !people
        && !who.is_empty()
        && let Some(at) = key_span(q, "answer")
    {
        diags.push(Diagnostic::error(
            "loader/nobody-can-answer",
            at,
            format!(
                "'{name}' asks for an answer, and it is asked only of the clock and of \
                     events, which give none — so nothing can ever send it."
            ),
            "Delete `answer:` (and `says:`: the clock and events read no wording), or name \
                 who answers in `asked-of:`."
                .to_string(),
        ));
    }
    if who.iter().any(|(_, a)| *a == Answerer::Clock) && q.get("answer-within").is_none() {
        diags.push(Diagnostic::error(
            "loader/nobody-can-answer",
            key_span(q, "asked-of").unwrap_or_else(|| q.span.start_of_block()),
            format!(
                "'{name}' is asked of the clock and says no time, so the clock never answers and \
                 the wait lasts for ever."
            ),
            "Say when the clock answers — `answer-within: 24h`, or `answer-within: {at: \
             input.starts-at, before: 24h}`."
                .to_string(),
        ));
    }
    if let Some(at) = key_span(q, "asked-in")
        && let Some((n, a)) = who
            .iter()
            .find(|(_, a)| matches!(a, Answerer::Named | Answerer::Clock | Answerer::Port))
    {
        let said = n.as_str().unwrap_or("").trim();
        diags.push(Diagnostic::error(
            "loader/asked-in-for-someone-who-chooses",
            at,
            format!(
                "'{name}' says where it appears (`asked-in:`), and it is asked of '{said}', {}.",
                match a {
                    Answerer::Clock => "the clock, which reads nothing".to_string(),
                    Answerer::Port => "a port, which sends events and reads nothing".to_string(),
                    _ =>
                        "a person, a role or a team, who is reached the way they chose".to_string(),
                }
            ),
            "Delete it. People are reached the way they chose, and a team's place is set on the \
             team. `asked-in:` is for a channel (`\"#social-approvals\"`), `the-requester` or an \
             outside contact."
                .to_string(),
        ));
    }
    for reminder in q.get("reminds-at").map(workflows::list).unwrap_or_default() {
        one_action(&name, "reminder", reminder, diags);
    }
}

/// The name a question is filed under, for the words of a diagnostic.
fn question_name(document: &Node, q: &Node) -> String {
    every_question(document)
        .into_iter()
        .find(|(_, n)| n.span == q.span)
        .map(|(name, _)| name.to_string())
        .unwrap_or_default()
}

/// WF-21: a reminder or a milestone writes exactly one of its four actions.
fn one_action(owner: &str, what: &str, reminder: &Node, diags: &mut Diagnostics) {
    let Some(map) = reminder.as_map() else { return };
    let written: Vec<&str> = ACTIONS
        .into_iter()
        .filter(|a| match map.get(*a) {
            Some(e) if *a == "nudges" => {
                e.node.value == Value::Bool(true) || e.node.as_str() == Some("yes")
            }
            Some(_) => true,
            None => false,
        })
        .collect();
    if written.len() == 1 {
        return;
    }
    let message = if written.is_empty() {
        format!(
            "A {what} of '{owner}' does nothing when its time comes: it nudges nobody, tells \
             nobody, hands over to nobody and runs nothing."
        )
    } else {
        format!(
            "A {what} of '{owner}' does {} at once ({}), so nothing says which one its time is for.",
            if written.len() == 2 {
                "two things"
            } else {
                "several things"
            },
            written
                .iter()
                .map(|w| format!("`{w}:`"))
                .collect::<Vec<_>>()
                .join(", ")
        )
    };
    diags.push(Diagnostic::error(
        "loader/nobody-can-answer",
        reminder.span.clone(),
        message,
        "Write exactly one action: `nudges: yes`, `tells: [<people>]`, `hands-over-to: \
         [<people>]` or `runs: <a workflow>`. Two actions are two reminders at the same time."
            .to_string(),
    ));
}

/// An `ask-someone` stage ends only in what its question's answerers can give.
fn exits(document: &Node, workflow: &Node, diags: &mut Diagnostics) {
    for (stage, node) in every_stage(workflow) {
        if workflows::does(node) != Some("ask-someone") {
            continue;
        }
        let Some(asks) = node.get("asks").and_then(Node::as_str).map(str::trim) else {
            continue;
        };
        let Some(q) = question_of(document, workflow, asks) else {
            continue;
        };
        let who = answerers(document, q);
        if who.is_empty() {
            continue;
        }
        let people = who.iter().any(|(_, a)| a.reads());
        let ports = who.iter().any(|(_, a)| *a == Answerer::Port);
        let only = if who.iter().all(|(_, a)| *a == Answerer::Clock) {
            "only the clock"
        } else {
            "only the clock and events"
        };
        for (key, entry) in node
            .get("then")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            let never = match key.as_str() {
                "answered" | "declined" if !people => Some(format!(
                    "'{stage}' asks '{asks}', which {only} answer, so it never ends `{key}` and \
                     nothing reads this line."
                )),
                "heard" if !ports => Some(format!(
                    "'{stage}' asks '{asks}', which is asked of no port of this workspace, so no \
                     event is listened for and it never ends `heard`."
                )),
                _ => None,
            };
            if let Some(message) = never {
                diags.push(Diagnostic::error(
                    "loader/a-line-this-stage-never-reads",
                    entry.key_span.clone(),
                    message,
                    if key == "heard" {
                        format!("Delete it, or add the port to `asked-of:` in '{asks}'.")
                    } else {
                        "Delete it: a wait for the clock ends `nobody-answered` when the time \
                         comes, and an event ends it `heard`."
                            .to_string()
                    },
                ));
            }
        }
    }
}

/// WF-40 and WF-32 on a workflow's limits and its stages', and WF-21 on its
/// milestones.
fn limits_of_a_workflow(flow: &str, workflow: &Node, diags: &mut Diagnostics) {
    let mut every: Vec<(String, &Node)> = Vec::new();
    if let Some(l) = workflow.get("limits") {
        every.push((format!("The workflow '{flow}'"), l));
    }
    for (stage, node) in every_stage(workflow) {
        if let Some(l) = node.get("limits") {
            every.push((format!("'{stage}'"), l));
        }
    }
    for (who, limits) in every {
        if let Some(choice) = limits.get("when-it-runs-out")
            && choice.as_str().map(str::trim) == Some(ANSWER_WITH_WHAT_IT_HAS)
        {
            diags.push(Diagnostic::error(
                "loader/an-agent-only-spelling",
                choice.span.clone(),
                format!(
                    "{who} writes `when-it-runs-out: {ANSWER_WITH_WHAT_IT_HAS}`, an agent's \
                     spelling: a workflow has no answer of its own to give early."
                ),
                "Write `carry-on`: running out records the overrun and goes on with what is done."
                    .to_string(),
            ));
        }
        for paused in limits
            .get("paused-during")
            .map(workflows::list)
            .unwrap_or_default()
        {
            let Some(named) = paused.as_str().map(str::trim) else {
                continue;
            };
            let found = every_stage(workflow).into_iter().find(|(n, _)| *n == named);
            // A name that is no stage is the schema's `names: ^steps` to tell.
            let Some((_, stage)) = found else { continue };
            let does = workflows::does(stage).unwrap_or("");
            if does != "ask-someone" {
                diags.push(Diagnostic::error(
                    "loader/a-pause-for-something-that-does-not-wait",
                    paused.span.clone(),
                    format!(
                        "{who} stops its clock during '{named}', and '{named}' does `{does}`, \
                         which waits for nobody: only a wait's time can be left off a deadline."
                    ),
                    "Name a wait: a stage that does `ask-someone`.".to_string(),
                ));
            }
        }
        for milestone in limits
            .get("milestones")
            .map(workflows::list)
            .unwrap_or_default()
        {
            one_action(flow, "milestone", milestone, diags);
        }
    }
}

/// What only a workflow reads, on an agent's own `limits:`.
fn limits_of_an_agent(agent: &str, node: &Node, diags: &mut Diagnostics) {
    let Some(limits) = node.get("limits").and_then(Node::as_map) else {
        return;
    };
    for line in WORKFLOW_LIMIT_LINES {
        if let Some(e) = limits.get(line) {
            diags.push(Diagnostic::error(
                "loader/a-line-this-stage-never-reads",
                e.key_span.clone(),
                format!(
                    "The agent '{agent}' writes `limits.{line}:`, which only a workflow reads, so \
                     it holds nothing here."
                ),
                "Delete it, or put it on the workflow that calls the agent.".to_string(),
            ));
        }
    }
    if let Some(e) = limits.get("finishes-within")
        && e.node.as_map().is_some()
    {
        diags.push(Diagnostic::error(
            "loader/a-workflow-only-spelling",
            e.node.span.clone(),
            format!(
                "The agent '{agent}' writes `finishes-within:` as a moment, and only a workflow \
                 reads one: an agent's run is timed from when it starts."
            ),
            "Write a length of time — `finishes-within: 2 minutes`.".to_string(),
        ));
    }
    if let Some(e) = limits.get("when-it-runs-out")
        && let Some(choice) = e.node.as_str().map(str::trim)
        && WORKFLOW_CHOICES.contains(&choice)
    {
        diags.push(Diagnostic::error(
            "loader/a-workflow-only-spelling",
            e.node.span.clone(),
            format!(
                "The agent '{agent}' writes `when-it-runs-out: {choice}`, which only a workflow \
                 reads: an agent stops and says so, asks a person, or answers with what it has."
            ),
            "Write `stop-and-say-so`, `ask-a-person` or `answer-with-what-it-has`.".to_string(),
        ));
    }
}

/// WF-30: with no `time-zone:` on the workspace, every moment a workflow reads
/// from a date, or counts in business days, names its own zone.
fn no_zone(document: &Node, asked: &BTreeMap<String, String>, diags: &mut Diagnostics) {
    let mut found: Vec<&Node> = Vec::new();
    for (_, w) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        moments_of_a_workflow(&w.node, &mut found);
    }
    for (name, q) in document
        .get("questions")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        if asked.contains_key(name.as_str()) {
            moments_of_a_question(&q.node, &mut found);
        }
    }
    for moment in found {
        let Some(m) = moment.as_map() else { continue };
        let at = m.get("at").and_then(|e| e.node.as_str()).map(str::trim);
        let business = m
            .get("counted-in")
            .and_then(|e| e.node.as_str())
            .is_some_and(|c| c.trim() == "business-days");
        if m.contains_key("in-time-zone") || (at.is_none() && !business) {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/a-time-with-no-zone",
            moment.span.clone(),
            match at {
                Some(at) => format!(
                    "This moment is read from `{at}`, and neither the line nor the workspace says \
                     which time zone it is in, so when it comes cannot be told."
                ),
                None => "This moment counts business days, and neither the line nor the workspace \
                         says which time zone a day begins in."
                    .to_string(),
            },
            "Add `in-time-zone: America/Chicago` to the line, or `time-zone:` to `workspace.yaml`."
                .to_string(),
        ));
    }
}

/// The lines of a workflow whose schema type is `moment` (02W §2.0): its own
/// and each stage's `limits.finishes-within:` and milestones' `at:`, its
/// `kept-for:` and every `remembers:` entry's, and its own questions'. Only
/// these positions are read, so an input, a binding or an answer that happens
/// to be named `at` is never taken for one.
fn moments_of_a_workflow<'n>(workflow: &'n Node, found: &mut Vec<&'n Node>) {
    let stages = every_stage(workflow).into_iter().map(|(_, s)| s);
    for holder in std::iter::once(workflow).chain(stages) {
        if let Some(limits) = holder.get("limits") {
            found.extend(limits.get("finishes-within"));
            for milestone in limits
                .get("milestones")
                .map(workflows::list)
                .unwrap_or_default()
            {
                found.extend(milestone.get("at"));
            }
        }
        found.extend(holder.get("kept-for"));
        for (_, state) in holder
            .get("remembers")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            found.extend(state.node.get("kept-for"));
        }
    }
    for (_, q) in workflow
        .get("questions")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        moments_of_a_question(&q.node, found);
    }
}

/// A question's moments: `answer-within:` and each reminder's `at:`.
fn moments_of_a_question<'n>(q: &'n Node, found: &mut Vec<&'n Node>) {
    found.extend(q.get("answer-within"));
    for reminder in q.get("reminds-at").map(workflows::list).unwrap_or_default() {
        found.extend(reminder.get("at"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn rules(text: &str) -> Vec<(&'static str, String)> {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        check(&node, &mut d);
        d.items()
            .iter()
            .map(|x| (x.rule, x.message.clone()))
            .collect()
    }

    /// A long-running case's deadline (02W §5.5): business days from payment,
    /// paused while the customer holds things up.
    const CASE: &str = "
time-zone: America/Chicago
workflows:
  case:
    description: x
    limits:
      finishes-within: { after: 60 days, counted-in: business-days }
      starts-from: paid
      paused-during: [signed]
      milestones:
        - { at: { after: 50 days, counted-in: business-days }, tells: [program-manager] }
      when-it-runs-out: carry-on
    starts-at: paid
    steps:
      paid:
        does: call
        call: t/a
        then: { answered: signed }
      signed:
        does: ask-someone
        asks: wait-for-signatures
        then: { nobody-answered: done }
    questions:
      wait-for-signatures:
        description: x
        asked-of: [the-clock]
        answer-within: { at: input.due-on, after: 2 days }
";

    #[test]
    fn a_deadline_written_as_the_design_writes_it_is_left_alone() {
        assert_eq!(rules(CASE), vec![]);
    }

    #[test]
    fn a_time_read_from_a_date_needs_a_zone_somewhere() {
        let found = rules(&CASE.replace("time-zone: America/Chicago\n", ""));
        let zones: Vec<&String> = found
            .iter()
            .filter(|(r, _)| *r == "loader/a-time-with-no-zone")
            .map(|(_, m)| m)
            .collect();
        assert_eq!(zones.len(), 3, "{found:?}");
        assert!(
            zones.iter().any(|m| m.contains("read from `input.due-on`")),
            "{zones:?}"
        );
        assert!(
            zones.iter().any(|m| m.contains("counts business days")),
            "{zones:?}"
        );
        let zoned = CASE
            .replace("time-zone: America/Chicago\n", "")
            .replace(
                "counted-in: business-days }",
                "counted-in: business-days, in-time-zone: America/Denver }",
            )
            .replace(
                "after: 2 days }",
                "after: 2 days, in-time-zone: input.zone }",
            );
        assert_eq!(rules(&zoned), vec![], "a zone on the line will do");
    }

    #[test]
    fn only_a_moment_line_is_read_as_a_moment() {
        // An input, an answer, a binding and a remembered value each named `at`,
        // with no zone anywhere: none of them is a moment.
        let text = CASE.replace("time-zone: America/Chicago\n", "").replace(
            "    starts-at: paid\n",
            "    accepts: { at: text }\n    answers-with: { at: date and time }\n    \
             remembers:\n      seen: { shape: { at: text } }\n    starts-at: paid\n",
        );
        let text = text
            .replace("call: t/a\n", "call: t/a\n        bind: { at: input.at }\n")
            .replace(
                "asked-of: [the-clock]\n",
                "asked-of: [the-clock]\n        answer: { at: date }\n",
            );
        let zones: Vec<_> = rules(&text)
            .into_iter()
            .filter(|(r, _)| *r == "loader/a-time-with-no-zone")
            .collect();
        assert_eq!(zones.len(), 3, "only the three real moments: {zones:?}");
    }

    /// A workspace question an agent's limits ask and a workflow's stage asks.
    const SHARED: &str = "
agents:
  desk:
    description: x
    limits:
      cost-per-request-under: 1 USD
      when-it-runs-out: ask-a-person
      asks: is-this-ok
questions:
  is-this-ok:
    description: x
    asked-of: [ap-clerks]
    says: May this go on?
    answer: { approved: yes or no }
    if-nobody-answers: decline
workflows:
  flow:
    description: x
    starts-at: check
    steps:
      check:
        does: ask-someone
        asks: is-this-ok
        then: { nobody-answered: done }
";

    #[test]
    fn a_question_an_agent_and_a_workflow_both_ask_is_refused_either_way() {
        for (text, rule) in [
            (SHARED.to_string(), "loader/an-agent-only-spelling"),
            (
                SHARED.replace("    if-nobody-answers: decline\n", ""),
                "loader/a-workflow-only-spelling",
            ),
        ] {
            let node = parse_yaml(&text, camino::Utf8Path::new("workspace.yaml")).unwrap();
            let mut d = Diagnostics::new();
            check(&node, &mut d);
            assert_eq!(d.items().len(), 1, "{:?}", d.items());
            let one = &d.items()[0];
            assert_eq!(one.rule, rule);
            assert!(
                one.message
                    .contains("asked by the workflow 'flow' and by the agent 'desk'"),
                "{}",
                one.message
            );
            assert!(
                one.fix.starts_with("Give each its own question"),
                "{}",
                one.fix
            );
            assert_eq!(one.related.len(), 1, "points at the agent's line");
        }
        // Asked by the agent alone, it loads as it is.
        let alone = SHARED.split("workflows:").next().unwrap();
        assert_eq!(rules(alone), vec![]);
    }

    #[test]
    fn a_pause_names_a_wait() {
        let found = rules(&CASE.replace("paused-during: [signed]", "paused-during: [paid]"));
        assert_eq!(found.len(), 1, "{found:?}");
        assert_eq!(
            found[0].0,
            "loader/a-pause-for-something-that-does-not-wait"
        );
        assert!(
            found[0]
                .1
                .contains("'paid' does `call`, which waits for nobody"),
            "{}",
            found[0].1
        );
    }

    #[test]
    fn a_milestone_does_exactly_one_thing() {
        let found = rules(&CASE.replace(", tells: [program-manager] }", " }"));
        assert_eq!(found.len(), 1, "{found:?}");
        assert_eq!(found[0].0, "loader/nobody-can-answer");
        assert!(
            found[0].1.contains("A milestone of 'case' does nothing"),
            "{}",
            found[0].1
        );
    }

    /// An agent's limits, as the worked example writes them.
    const AGENT: &str = "
agents:
  desk:
    description: x
    limits:
      finishes-within: 2 minutes
      when-it-runs-out: stop-and-say-so
";

    #[test]
    fn what_only_a_workflow_reads_is_refused_on_an_agent() {
        assert_eq!(rules(AGENT), vec![]);
        for (from, to, rule, says) in [
            (
                "finishes-within: 2 minutes",
                "finishes-within: { after: 2 days, counted-in: business-days }",
                "loader/a-workflow-only-spelling",
                "as a moment",
            ),
            (
                "when-it-runs-out: stop-and-say-so",
                "when-it-runs-out: carry-on",
                "loader/a-workflow-only-spelling",
                "`when-it-runs-out: carry-on`, which only a workflow",
            ),
            (
                "when-it-runs-out: stop-and-say-so",
                "when-it-runs-out: stop-and-say-so\n      at-once-at-most: 2",
                "loader/a-line-this-stage-never-reads",
                "`limits.at-once-at-most:`",
            ),
        ] {
            let text = AGENT.replace(from, to);
            let found = rules(&text);
            assert_eq!(found.len(), 1, "{found:?}");
            assert_eq!(found[0].0, rule, "{found:?}");
            assert!(found[0].1.contains(says), "{}", found[0].1);
        }
    }

    #[test]
    fn who_answers_is_told_by_spelling() {
        let doc = parse_yaml(
            "ports:\n  fee-received:\n    description: x\n",
            camino::Utf8Path::new("w.yaml"),
        )
        .unwrap();
        for (written, who) in [
            ("the-clock", Answerer::Clock),
            ("fee-received", Answerer::Port),
            ("the-requester", Answerer::Requester),
            ("steps.po.budget-owner", Answerer::Binding),
            ("#social-approvals", Answerer::Channel),
            ("ap-clerks", Answerer::Named),
        ] {
            assert_eq!(Answerer::of(&doc, written), who, "{written}");
        }
    }
}
