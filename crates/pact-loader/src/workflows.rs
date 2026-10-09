//! **Workflows: stage loops that belong to no agent** (02W §1, §3).
//!
//! A workflow is built from the groups PACT already ships, so most of what can
//! be wrong with one is already caught where the schema checks a value. What is
//! left here is what no single value can say:
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/a-workflow-with-a-mind-of-its-own` | WF-1 | a workflow writes `model:`, `instructions:`, `loop:`, `team:` or `uses:` |
//! | `loader/a-stage-a-workflow-cannot-have` | WF-2 | a workflow stage does `think`, `use-tools`, `check-its-work` or `run-code` |
//! | `loader/a-stage-an-agent-cannot-have` | — | an agent's loop does `call`, `decide`, `each`, `repeat` or `together` (WF-2 turned round), or one of its stages writes a line or an outcome only a workflow's stage reads |
//! | `loader/a-line-this-stage-never-reads` | WF-3 | a line written beside a `does:` it does not belong to, an outcome under `then:` its `does:` never ends in (02W §2.4), or `items-at-most:` anywhere but an `each`'s own `limits:` |
//! | `loader/workflows-that-call-each-other` | WF-8 | the workflow call graph has a circle |
//! | `loader/for-each-with-no-ceiling` | WF-10 | an `each` with no `limits.items-at-most` |
//! | `loader/items-told-apart-by-position` | WF-11 | an `each` whose body writes and has no `identified-by:` |
//! | `loader/repeat-with-no-bottom` | WF-12 | a `repeat` with no `at-most:` |
//! | `loader/a-version-of-something-that-has-none` | WF-35 | `version:` on a call that is not to a workflow |
//! | `loader/forget-after-is-now-kept-for` | WF-37 | `forget-after:` on remembered state (a warning, for one release) |
//! | `loader/a-path-that-answers-nothing` | WF-38 | `answers-with:` is declared and a path ends with no `answer` stage |
//! | `loader/no-such-name` | shipped | a `call:`, `may-call:` or `undone-by:` names nothing here |
//! | `loader/a-name-the-workspace-already-has` | new | a workflow shares its name with an agent or a program, or a `call:` could mean two of them |
//!
//! A stage reached through `steps:` is one stage whatever holds it, so the
//! walk below is the one walk for an agent's loop, a workflow, and the inside
//! of an `each`, a `repeat` or a `together`. Reachability (`loader/stage-nothing-
//! reaches`) is `reachability.rs`'s, over the same stages.

use crate::bindings::is_binding;
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node, Value};
use std::collections::{BTreeMap, BTreeSet};

/// The `does:` values only an agent's own loop has: they think.
const AGENT_ONLY: &[&str] = &["think", "use-tools", "check-its-work", "run-code"];
/// The `does:` values only a workflow has.
const WORKFLOW_ONLY: &[&str] = &["call", "decide", "each", "repeat", "together"];
/// What a workflow may not write, because it has no mind of its own (WF-1).
const A_MIND: &[&str] = &["model", "instructions", "loop", "team", "uses"];
/// The lines a stage reads only beside particular `does:` values (WF-3), from
/// 02W §2.3's help for each. A line not listed here is read whatever the stage
/// does (`says:`, `limits:`, `then:`, ...).
const BELONGS_WITH: &[(&str, &[&str])] = &[
    ("call", &["call"]),
    ("may-call", &["call"]),
    ("bind", &["call"]),
    ("waits-for-result", &["call"]),
    ("version", &["call"]),
    ("chooses-between", &["decide"]),
    ("over", &["each"]),
    ("identified-by", &["each"]),
    ("ordered-by", &["each"]),
    ("teamwork", &["each"]),
    ("combines-by", &["each", "together"]),
    ("steps", &["each", "repeat", "together"]),
    ("starts-at", &["each", "repeat"]),
    ("until", &["repeat"]),
    ("remembers", &["repeat"]),
];

/// The lines only a workflow's runtime reads, whatever its stage does. An
/// agent's loop runs inside one model run, which reads none of them, so in a
/// loop they would be a ceiling, a check or an undo nobody keeps.
const WORKFLOW_LINES: &[&str] = &["limits", "checked-by", "checks-at-most", "undone-by"];

/// The outcomes an agent's loop has ended in since before workflows (the
/// shipped `outcome` group), whatever its stage does.
const LOOP_OUTCOMES: &[&str] = &[
    "used-a-tool",
    "answered",
    "too-many-times",
    "decided-by",
    "may-go-to",
];

/// What a stage can end in, by `does` (02W §2.4). A workflow's `decide` goes
/// where its `chooses-between:` labels say and an `answer` ends the run (or the
/// item, or the round), so neither has a `then:`.
fn outcomes(in_workflow: bool, does: &str) -> &'static [&'static str] {
    if !in_workflow {
        return LOOP_OUTCOMES;
    }
    match does {
        "call" | "each" | "together" => &["answered"],
        "repeat" => &["answered", "too-many-times"],
        "ask-someone" => &["answered", "declined", "nobody-answered", "heard"],
        "decide" | "answer" => &[],
        // A thinking stage, refused in a workflow by WF-2 and told once there.
        _ => LOOP_OUTCOMES,
    }
}

/// What an `each`'s `teamwork:` may not say: these belong to a named team.
const TEAM_ONLY: &[&str] = &["starts", "shares", "may-start"];

/// Every workflow check, over the loaded document.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    if let Some(loops) = document.get("loops").and_then(Node::as_map) {
        for (name, entry) in loops {
            if let Some(steps) = entry.node.get("steps").and_then(Node::as_map) {
                stages(document, &Scope::Loop(name), steps, diags);
            }
        }
    }
    for (name, entry) in document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        no_items_here(&format!("The agent '{name}'"), &entry.node, diags);
    }
    let workflows = document.get("workflows").and_then(Node::as_map);
    for (name, entry) in workflows.into_iter().flatten() {
        let w = &entry.node;
        a_mind_of_its_own(name, w, diags);
        no_items_here(&format!("The workflow '{name}'"), w, diags);
        if let Some(steps) = w.get("steps").and_then(Node::as_map) {
            stages(document, &Scope::Workflow, steps, diags);
            answers_on_every_path(name, w, steps, diags);
        }
        if let Some(undo) = w.as_map().and_then(|m| m.get("undone-by")) {
            undo_names_something(document, name, undo, diags);
        }
    }
    calls_go_round(document, diags);
    one_name_one_thing(document, diags);
    forget_after_is_now_kept_for(document, diags);
}

/// Drop the schema's `unknown-field` where WF-1 has said the same thing about the
/// same line in its own words: one mistake gets one message.
pub fn told_once(diags: &mut Diagnostics) {
    let said: Vec<Span> = diags
        .items()
        .iter()
        .filter(|d| d.rule == "loader/a-workflow-with-a-mind-of-its-own")
        .map(|d| d.span.clone())
        .collect();
    diags.retain(|d| !(d.rule == "schema/unknown-field" && said.contains(&d.span)));
}

/// Whose stages these are, for the words a diagnostic uses.
enum Scope<'a> {
    Loop(&'a str),
    Workflow,
}

impl Scope<'_> {
    fn in_workflow(&self) -> bool {
        matches!(self, Scope::Workflow)
    }
}

/// WF-1.
fn a_mind_of_its_own(name: &str, w: &Node, diags: &mut Diagnostics) {
    let Some(map) = w.as_map() else { return };
    for (key, entry) in map {
        if !A_MIND.contains(&key.as_str()) {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/a-workflow-with-a-mind-of-its-own",
            entry.key_span.clone(),
            format!(
                "The workflow '{name}' writes `{key}:`, and a workflow has no mind of its own: \
                 it calls agents, tools, programs and other workflows, and an agent is what \
                 has {}.",
                match key.as_str() {
                    "model" => "a model",
                    "instructions" => "instructions",
                    "loop" => "a loop",
                    "team" => "a team",
                    _ => "tools to use",
                }
            ),
            format!(
                "Move `{key}:` to an agent and call that agent from a stage: `does: call` and \
                 `call: <the agent>`."
            ),
        ));
    }
}

/// WF-2 both ways round, WF-3, WF-10, WF-11, WF-12, WF-35 and the call targets,
/// over every stage of one `steps:` and of every `steps:` inside it.
fn stages(document: &Node, scope: &Scope, steps: &Map, diags: &mut Diagnostics) {
    for (stage, entry) in steps {
        let Some(fields) = entry.node.as_map() else {
            continue;
        };
        let Some(does_entry) = fields.get("does") else {
            continue;
        };
        let Some(does) = does_entry.node.as_str().map(str::trim) else {
            continue;
        };
        let does_span = entry_span(does_entry);
        match scope {
            Scope::Workflow if AGENT_ONLY.contains(&does) => diags.push(Diagnostic::error(
                "loader/a-stage-a-workflow-cannot-have",
                does_span.clone(),
                format!(
                    "'{stage}' does `{does}`, and a workflow does no thinking of its own: \
                     thinking and using tools happen inside an agent it calls."
                ),
                "Call an agent that does it: `does: call` and `call: <the agent>`.".to_string(),
            )),
            Scope::Loop(name) if WORKFLOW_ONLY.contains(&does) => diags.push(Diagnostic::error(
                "loader/a-stage-an-agent-cannot-have",
                does_span.clone(),
                format!(
                    "'{stage}' in the loop '{name}' does `{does}`, which a workflow's stage \
                     does: an agent's own loop thinks, uses tools, checks its work, asks and \
                     answers."
                ),
                format!(
                    "Write this stage in a workflow under `workflows/` that calls the agent, or \
                     change `does:` to one of: {}, ask-someone, answer.",
                    AGENT_ONLY.join(", ")
                ),
            )),
            _ => {}
        }
        never_read(scope, stage, does, fields, diags);
        if !scope.in_workflow() {
            continue;
        }
        if does != "each" {
            no_items_here(
                &format!("'{stage}', which does `{does}`,"),
                &entry.node,
                diags,
            );
        }
        if let Some(undo) = fields.get("undone-by") {
            undo_names_something(document, stage, undo, diags);
        }
        match does {
            "call" => calls(document, stage, fields, diags),
            "each" => each(document, stage, fields, &does_span, diags),
            "repeat" if !fields.contains_key("at-most") => diags.push(Diagnostic::error(
                "loader/repeat-with-no-bottom",
                does_span.clone(),
                format!(
                    "'{stage}' repeats with no bottom: nothing says how many rounds it may run, \
                     so a round whose `until:` never holds runs for ever."
                ),
                "Add `at-most:` — `at-most: 5`. \"Forever\" is a schedule plus memory.".to_string(),
            )),
            _ => {}
        }
        if let Some(inner) = fields.get("steps").and_then(|e| e.node.as_map()) {
            stages(document, scope, inner, diags);
        }
    }
}

/// WF-3: a line written beside a `does:` it does not belong to, and an outcome
/// its `does:` never ends in. In an agent's loop, every line and outcome only a
/// workflow's stage reads.
fn never_read(scope: &Scope, stage: &str, does: &str, fields: &Map, diags: &mut Diagnostics) {
    if let Scope::Loop(name) = scope {
        return only_a_workflow_reads(name, stage, does, fields, diags);
    }
    outcomes_it_never_ends_in(stage, does, fields, diags);
    for (key, entry) in fields {
        let Some((_, with)) = BELONGS_WITH.iter().find(|(k, _)| k == key) else {
            continue;
        };
        if with.contains(&does) {
            continue;
        }
        let belongs = with
            .iter()
            .map(|d| format!("`{d}`"))
            .collect::<Vec<_>>()
            .join(" or ");
        diags.push(Diagnostic::error(
            "loader/a-line-this-stage-never-reads",
            entry.key_span.clone(),
            format!(
                "'{stage}' does `{does}` and writes `{key}:`, which only a stage that does \
                 {belongs} reads, so nothing ever reads this line."
            ),
            format!("Delete it, or change `does:` to `{}`.", with[0]),
        ));
    }
    if does != "each" {
        return;
    }
    let Some(teamwork) = fields.get("teamwork").and_then(|e| e.node.as_map()) else {
        return;
    };
    for (key, entry) in teamwork {
        if TEAM_ONLY.contains(&key.as_str()) {
            diags.push(Diagnostic::error(
                "loader/a-line-this-stage-never-reads",
                entry.key_span.clone(),
                format!(
                    "'{stage}' writes `teamwork.{key}:`, which belongs to a named team, so an \
                     `each` never reads it."
                ),
                "Delete it. An `each` says how its items are waited for with `waits-for`, \
                 `gives-up-after`, `if-someone-fails` and `divides-the-budget`."
                    .to_string(),
            ));
        }
    }
}

/// An agent's loop: a line or an outcome only a workflow's stage reads. A stage
/// whose `does:` is a workflow's is told once, at its `does:`.
fn only_a_workflow_reads(
    loop_name: &str,
    stage: &str,
    does: &str,
    fields: &Map,
    diags: &mut Diagnostics,
) {
    if WORKFLOW_ONLY.contains(&does) {
        return;
    }
    let lines = fields.iter().filter(|(key, _)| {
        WORKFLOW_LINES.contains(&key.as_str()) || BELONGS_WITH.iter().any(|(k, _)| k == key)
    });
    let then = fields.get("then").and_then(|e| e.node.as_map());
    let ends = then
        .into_iter()
        .flatten()
        .filter(|(key, _)| !LOOP_OUTCOMES.contains(&key.as_str()));
    for (entry, said) in lines
        .map(|(k, e)| (e, format!("`{k}:`")))
        .chain(ends.map(|(k, e)| (e, format!("`then.{k}:`"))))
    {
        diags.push(Diagnostic::error(
            "loader/a-stage-an-agent-cannot-have",
            entry.key_span.clone(),
            format!(
                "'{stage}' in the loop '{loop_name}' writes {said}, which only a workflow's stage \
                 reads: an agent's loop runs inside one model run, so nothing would keep this line."
            ),
            "Delete it, or write this stage in a workflow under `workflows/` that calls the agent."
                .to_string(),
        ));
    }
}

/// WF-3 for `then:` (02W §2.4): an outcome this stage's `does:` never ends in.
fn outcomes_it_never_ends_in(stage: &str, does: &str, fields: &Map, diags: &mut Diagnostics) {
    let Some(then) = fields.get("then") else {
        return;
    };
    let can = outcomes(true, does);
    if can.is_empty() {
        let (goes, fix) = if does == "decide" {
            (
                "goes where its `chooses-between:` labels say",
                "Delete `then:` and name where each label goes under `chooses-between:`.",
            )
        } else {
            (
                "ends the run, or the item or round it is in",
                "Delete `then:`; to go on after it, make it a stage that does `call` instead.",
            )
        };
        diags.push(Diagnostic::error(
            "loader/a-line-this-stage-never-reads",
            then.key_span.clone(),
            format!("'{stage}' does `{does}` and writes `then:`, and a `{does}` {goes}, so nothing ever reads it."),
            fix.to_string(),
        ));
        return;
    }
    for (key, entry) in then.node.as_map().into_iter().flatten() {
        if can.contains(&key.as_str()) {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/a-line-this-stage-never-reads",
            entry.key_span.clone(),
            format!(
                "'{stage}' does `{does}` and writes `then.{key}:`, and a `{does}` ends only in {}, \
                 so this never happens and nothing ever reads it.",
                can.iter()
                    .map(|o| format!("`{o}`"))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            "Delete it.".to_string(),
        ));
    }
}

/// `items-at-most:` is read on an `each`'s own `limits:` and nowhere else.
fn no_items_here(who: &str, node: &Node, diags: &mut Diagnostics) {
    let Some(items) = node
        .get("limits")
        .and_then(Node::as_map)
        .and_then(|l| l.get("items-at-most"))
    else {
        return;
    };
    diags.push(Diagnostic::error(
        "loader/a-line-this-stage-never-reads",
        items.key_span.clone(),
        format!(
            "{who} writes `limits.items-at-most:`, which only a stage that does `each` reads, so \
             it is a ceiling on nothing."
        ),
        "Move it under the `limits:` of the `each` stage that goes through the list, or delete it."
            .to_string(),
    ));
}

/// A `call` stage: its targets name something (`loader/no-such-name`), and a
/// `version:` is only on a call to a workflow (WF-35).
fn calls(document: &Node, stage: &str, fields: &Map, diags: &mut Diagnostics) {
    let mut targets: Vec<(String, Span)> = Vec::new();
    if let Some(call) = fields.get("call")
        && let Some(said) = call.node.as_str().map(str::trim)
        && !is_binding(said)
    {
        targets.push((said.to_string(), call.node.span.clone()));
    }
    if let Some(may) = fields.get("may-call") {
        for item in list(&may.node) {
            if let Some(said) = item.as_str() {
                targets.push((said.trim().to_string(), item.span.clone()));
            }
        }
    }
    let mut kinds = Vec::new();
    for (target, span) in &targets {
        match resolve(document, target) {
            Resolved::One(kind) => kinds.push((target.clone(), kind)),
            // A workflow sharing its name is told once, at the workflow.
            Resolved::Several(found) if found.contains(&Kind::Workflow) => {}
            Resolved::Several(found) => diags.push(two_things(target, &found, span.clone())),
            Resolved::Nothing(fix) => diags.push(Diagnostic::error(
                "loader/no-such-name",
                span.clone(),
                format!("'{stage}' calls '{target}', and this workspace has nothing by that name."),
                fix,
            )),
        }
    }
    let Some(version) = fields.get("version") else {
        return;
    };
    if let Some((target, kind)) = kinds.iter().find(|(_, k)| *k != Kind::Workflow) {
        let written = version.node.as_str().unwrap_or("").trim();
        diags.push(Diagnostic::error(
            "loader/a-version-of-something-that-has-none",
            entry_span(version),
            format!(
                "'{stage}' asks for version '{written}' of '{target}', which is {}, and only a \
                 workflow has versions.",
                kind.a()
            ),
            "Delete `version:`.".to_string(),
        ));
    }
}

/// An `each`: its ceiling (WF-10) and, when its body writes, what makes an item
/// itself (WF-11).
fn each(document: &Node, stage: &str, fields: &Map, does: &Span, diags: &mut Diagnostics) {
    let ceiling = fields
        .get("limits")
        .and_then(|e| e.node.as_map())
        .is_some_and(|l| l.contains_key("items-at-most"));
    if !ceiling {
        // The binding's last word says what the items are: `input.attachments`
        // goes through attachments.
        let over = fields
            .get("over")
            .and_then(|e| e.node.as_str())
            .unwrap_or("");
        let items = over
            .rsplit('.')
            .next()
            .filter(|w| !w.trim().is_empty())
            .unwrap_or("items");
        diags.push(Diagnostic::error(
            "loader/for-each-with-no-ceiling",
            does.clone(),
            format!(
                "'{stage}' goes through a list with no ceiling, so five thousand {} start five \
                 thousand runs.",
                items.trim()
            ),
            "Add under `limits:` the most it should take and what happens past that — \
             `items-at-most: 20` and `when-it-runs-out: ask-a-person`."
                .to_string(),
        ));
    }
    if fields.contains_key("identified-by") {
        return;
    }
    let Some(body) = fields.get("steps").and_then(|e| e.node.as_map()) else {
        return;
    };
    if let Some(write) = first_write(document, body, &mut BTreeSet::new()) {
        diags.push(Diagnostic::error(
            "loader/items-told-apart-by-position",
            does.clone(),
            format!(
                "'{stage}' writes for each item ('{write}' does) and does not say what makes \
                     an item that item, so a retry after the list changes order could write for \
                     the wrong item, or twice."
            ),
            format!(
                "Name the fields that make an item itself, under '{stage}' — \
                     `identified-by: [content-hash]`."
            ),
        ));
    }
}

/// The first stage in `steps` (or anything it calls) that writes: a call to a
/// tool action that is not `reads-only: yes`, to an agent that uses one, or to a
/// workflow that writes.
fn first_write(document: &Node, steps: &Map, seen: &mut BTreeSet<String>) -> Option<String> {
    for (stage, entry) in steps {
        let fields = entry.node.as_map()?;
        if let Some(inner) = fields.get("steps").and_then(|e| e.node.as_map())
            && let Some(found) = first_write(document, inner, seen)
        {
            return Some(found);
        }
        let mut said: Vec<&str> = fields
            .get("call")
            .and_then(|e| e.node.as_str())
            .into_iter()
            .collect();
        if let Some(may) = fields.get("may-call") {
            said.extend(list(&may.node).into_iter().filter_map(Node::as_str));
        }
        if said.into_iter().any(|t| writes(document, t.trim(), seen)) {
            return Some(stage.clone());
        }
    }
    None
}

/// Whether calling `target` can write: a tool's action that is not `reads-only:
/// yes`; a workflow whose stages write; an agent that uses a tool that writes,
/// or uses or has on its `team:` an agent or a workflow that writes. `seen`
/// holds every agent and workflow already followed, so a circle ends.
fn writes(document: &Node, target: &str, seen: &mut BTreeSet<String>) -> bool {
    if let Some((tool, action)) = target.split_once('/') {
        return action_writes(document, tool, action);
    }
    if let Some(tool) = entry_in(document, "tools", target) {
        return tool
            .get("actions")
            .and_then(Node::as_map)
            .is_some_and(|actions| actions.keys().any(|a| action_writes(document, target, a)));
    }
    let workflow = entry_in(document, "workflows", target);
    let agent = entry_in(document, "agents", target);
    if (workflow.is_none() && agent.is_none()) || !seen.insert(target.to_string()) {
        return false;
    }
    if let Some(w) = workflow
        && w.get("steps")
            .and_then(Node::as_map)
            .is_some_and(|steps| first_write(document, steps, seen).is_some())
    {
        return true;
    }
    let Some(agent) = agent else { return false };
    let uses = agent.get("uses").map(list).unwrap_or_default();
    let team = agent
        .get("team")
        .and_then(Node::as_map)
        .into_iter()
        .flat_map(|m| m.keys());
    let reached: Vec<String> = uses
        .into_iter()
        .filter_map(Node::as_str)
        .map(|n| n.trim().to_string())
        .chain(team.cloned())
        .collect();
    reached.iter().any(|n| writes(document, n, seen))
}

fn action_writes(document: &Node, tool: &str, action: &str) -> bool {
    entry_in(document, "tools", tool)
        .and_then(|t| t.get("actions"))
        .and_then(|a| a.get(action))
        .is_some_and(|a| !a.get("reads-only").is_some_and(said_yes))
}

/// WF-38: with `answers-with:` declared, every way to the end passes an `answer`
/// stage. A run ends at `done`, or where a stage that answered has nowhere to
/// go (the shipped rule); an `answer` stage ends it with the answer.
fn answers_on_every_path(name: &str, w: &Node, steps: &Map, diags: &mut Diagnostics) {
    if w.get("answers-with")
        .and_then(Node::as_map)
        .is_none_or(|m| m.is_empty())
    {
        return;
    }
    let Some(start) = w.get("starts-at").and_then(Node::as_str).map(str::trim) else {
        return;
    };
    let mut came_from: BTreeMap<&str, &str> = BTreeMap::new();
    let mut frontier = vec![start];
    let mut seen: BTreeSet<&str> = BTreeSet::from([start]);
    while let Some(here) = frontier.pop() {
        let Some(stage) = steps.get(here).map(|e| &e.node) else {
            continue;
        };
        if does(stage) == Some("answer") {
            continue;
        }
        if let Some(at) = ends_here(stage) {
            let mut path = vec![here];
            while let Some(before) = came_from.get(path[path.len() - 1]) {
                path.push(before);
            }
            path.reverse();
            let path = path
                .iter()
                .map(|s| format!("'{s}'"))
                .collect::<Vec<_>>()
                .join(" → ");
            diags.push(Diagnostic::error(
                "loader/a-path-that-answers-nothing",
                at,
                format!(
                    "The workflow '{name}' answers with {}, and the path {path} reaches the end \
                     with no `answer` stage, so whoever waits on this run gets nothing back.",
                    w.get("answers-with")
                        .and_then(Node::as_map)
                        .map(|m| m
                            .keys()
                            .map(|k| format!("`{k}`"))
                            .collect::<Vec<_>>()
                            .join(", "))
                        .unwrap_or_default()
                ),
                format!(
                    "Add a stage that does `answer` on that path and send '{here}' there instead \
                     of to the end."
                ),
            ));
            return;
        }
        for next in successors(stage, true) {
            if next != "done" && steps.contains_key(next) && seen.insert(next) {
                came_from.insert(next, here);
                frontier.push(next);
            }
        }
    }
}

/// Where a stage ends the run, if it can: the line that sends it to `done`, or
/// the stage itself when it answers and has nowhere to go. Only outcomes its
/// `does:` can end in count (02W §2.4).
fn ends_here(stage: &Node) -> Option<Span> {
    let kind = does(stage)?;
    if kind == "decide" {
        let labels = stage.as_map()?.get("chooses-between")?.node.as_map()?;
        return labels
            .values()
            .find(|e| e.node.as_str().map(str::trim) == Some("done"))
            .map(|e| e.node.span.clone());
    }
    let routed = routes(stage, true);
    if !routed.iter().any(|(outcome, _)| *outcome == "answered") {
        return Some(stage.span.start_of_block());
    }
    routed.into_iter().find_map(|(_, to)| match &to.value {
        Value::Str(s) if s.trim() == "done" => Some(to.span.clone()),
        Value::Map(heard) => heard
            .values()
            .find(|h| h.node.as_str().map(str::trim) == Some("done"))
            .map(|h| h.node.span.clone()),
        _ => None,
    })
}

/// The lines under a stage's `then:` whose outcome its `does:` can end in
/// (02W §2.4 in a workflow; the shipped outcomes in an agent's loop). A stage
/// with no `does:` is left to the schema, and every line of it is followed.
fn routes(stage: &Node, in_workflow: bool) -> Vec<(&str, &Node)> {
    let can = does(stage).map(|d| outcomes(in_workflow, d));
    stage
        .get("then")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .filter(|(outcome, _)| can.is_none_or(|c| c.contains(&outcome.as_str())))
        .map(|(outcome, e)| (outcome.as_str(), &e.node))
        .collect()
}

/// Every stage this one can go to next: the values under the `then:` lines it
/// can end in (and `heard:`), and under a `decide`'s `chooses-between:`.
pub(crate) fn successors(stage: &Node, in_workflow: bool) -> Vec<&str> {
    next_stages(stage, in_workflow)
        .into_iter()
        .map(|(_, to)| to)
        .collect()
}

/// [`successors`], each with the word that leads there: the outcome
/// (`answered`), the port a `heard:` names, or the `decide`'s label.
pub(crate) fn next_stages(stage: &Node, in_workflow: bool) -> Vec<(&str, &str)> {
    let mut to: Vec<(&str, &Node)> = routes(stage, in_workflow);
    if does(stage).is_none_or(|d| d == "decide") {
        to.extend(
            stage
                .get("chooses-between")
                .and_then(Node::as_map)
                .into_iter()
                .flat_map(|m| m.iter().map(|(k, e)| (k.as_str(), &e.node))),
        );
    }
    let mut out = Vec::new();
    for (word, node) in to {
        match &node.value {
            Value::Str(s) => out.push((word, s.trim())),
            Value::Map(m) => out.extend(
                m.iter()
                    .filter_map(|(k, e)| e.node.as_str().map(|s| (k.as_str(), s.trim()))),
            ),
            _ => {}
        }
    }
    out
}

/// WF-8: a circle in which workflow calls workflow.
fn calls_go_round(document: &Node, diags: &mut Diagnostics) {
    let Some(workflows) = document.get("workflows").and_then(Node::as_map) else {
        return;
    };
    let mut edges: BTreeMap<&str, Vec<(&str, Span)>> = BTreeMap::new();
    for (name, entry) in workflows {
        let mut out = Vec::new();
        if let Some(steps) = entry.node.get("steps").and_then(Node::as_map) {
            called_workflows(workflows, steps, &mut out);
        }
        edges.insert(name.as_str(), out);
    }
    let mut reported: BTreeSet<Vec<&str>> = BTreeSet::new();
    for start in edges.keys().copied() {
        let mut path = vec![start];
        if let Some((circle, at)) = circle_from(&edges, &mut path) {
            let mut key = circle.clone();
            key.sort();
            if !reported.insert(key) {
                continue;
            }
            let said = circle
                .iter()
                .map(|w| format!("'{w}'"))
                .collect::<Vec<_>>()
                .join(" calls ");
            diags.push(Diagnostic::error(
                "loader/workflows-that-call-each-other",
                at,
                format!(
                    "{said} calls '{}' again, so one run can start itself without end.",
                    circle[0]
                ),
                "Break the circle; a workflow that must come back is a `repeat`.".to_string(),
            ));
        }
    }
}

fn called_workflows<'a>(workflows: &Map, steps: &'a Map, out: &mut Vec<(&'a str, Span)>) {
    for entry in steps.values() {
        let Some(fields) = entry.node.as_map() else {
            continue;
        };
        let mut said: Vec<&Node> = fields.get("call").map(|e| &e.node).into_iter().collect();
        if let Some(may) = fields.get("may-call") {
            said.extend(list(&may.node));
        }
        for n in said {
            if let Some(name) = n.as_str().map(str::trim)
                && workflows.contains_key(name)
            {
                out.push((name, n.span.clone()));
            }
        }
        if let Some(inner) = fields.get("steps").and_then(|e| e.node.as_map()) {
            called_workflows(workflows, inner, out);
        }
    }
}

/// The first circle back to `path[0]`, with the line in the last workflow that
/// closes it.
fn circle_from<'a>(
    edges: &BTreeMap<&'a str, Vec<(&'a str, Span)>>,
    path: &mut Vec<&'a str>,
) -> Option<(Vec<&'a str>, Span)> {
    let here = *path.last()?;
    for (next, at) in edges.get(here).into_iter().flatten() {
        if *next == path[0] {
            return Some((path.clone(), at.clone()));
        }
        if path.contains(next) {
            continue;
        }
        path.push(next);
        if let Some(found) = circle_from(edges, path) {
            return Some(found);
        }
        path.pop();
    }
    None
}

/// A name a workflow shares with an agent or a program: `call:` and `run` could
/// not tell which one is meant.
fn one_name_one_thing(document: &Node, diags: &mut Diagnostics) {
    let Some(workflows) = document.get("workflows").and_then(Node::as_map) else {
        return;
    };
    for (name, entry) in workflows {
        let also: Vec<Kind> = [Kind::Agent, Kind::Program]
            .into_iter()
            .filter(|k| entry_in(document, k.collection(), name).is_some())
            .collect();
        if also.is_empty() {
            continue;
        }
        let mut found = also;
        found.push(Kind::Workflow);
        diags.push(two_things(name, &found, entry.key_span.clone()));
    }
}

fn two_things(name: &str, found: &[Kind], at: Span) -> Diagnostic {
    let things = found
        .iter()
        .map(|k| k.a())
        .collect::<Vec<_>>()
        .join(" and ");
    Diagnostic::error(
        "loader/a-name-the-workspace-already-has",
        at,
        format!(
            "'{name}' is {things}, so whatever runs or calls '{name}' cannot tell which one is \
             meant."
        ),
        format!(
            "Rename one of them — the workflow to `{name}-flow`, say — and change what names it."
        ),
    )
}

/// `undone-by:` on a workflow names a tool's action or a workflow.
fn undo_names_something(
    document: &Node,
    name: &str,
    undo: &pact_doc::Entry,
    diags: &mut Diagnostics,
) {
    let Some(said) = undo.node.as_str().map(str::trim) else {
        return;
    };
    match resolve(document, said) {
        Resolved::One(Kind::Action | Kind::Workflow) => {}
        Resolved::One(kind) => diags.push(Diagnostic::error(
            "loader/no-such-name",
            undo.node.span.clone(),
            format!(
                "'{name}' is undone by '{said}', which is {}, and an undo is a tool's action \
                 or a workflow.",
                kind.a()
            ),
            "Name a `<tool>/<action>` that undoes it, or a workflow.".to_string(),
        )),
        Resolved::Several(found) if found.contains(&Kind::Workflow) => {}
        Resolved::Several(found) => diags.push(two_things(said, &found, undo.node.span.clone())),
        Resolved::Nothing(fix) => diags.push(Diagnostic::error(
            "loader/no-such-name",
            undo.node.span.clone(),
            format!("'{name}' is undone by '{said}', and this workspace has nothing by that name."),
            fix,
        )),
    }
}

/// WF-37: `forget-after:` under any `remembers:` (an agent's, a port's, a
/// workflow's, a repeat's, the workspace's).
fn forget_after_is_now_kept_for(node: &Node, diags: &mut Diagnostics) {
    match &node.value {
        Value::Map(map) => {
            for (key, entry) in map {
                if key == "remembers" {
                    for fact in entry.node.as_map().into_iter().flat_map(|m| m.values()) {
                        if let Some(old) = fact.node.as_map().and_then(|f| f.get("forget-after")) {
                            diags.push(Diagnostic::warning(
                                "loader/forget-after-is-now-kept-for",
                                old.key_span.clone(),
                                "`forget-after:` is now called `kept-for:`, and this name is read \
                                 for one more release only."
                                    .to_string(),
                                "Rename it `kept-for:`; the value is unchanged.".to_string(),
                            ));
                        }
                    }
                }
                forget_after_is_now_kept_for(&entry.node, diags);
            }
        }
        Value::List(items) => items
            .iter()
            .for_each(|i| forget_after_is_now_kept_for(i, diags)),
        _ => {}
    }
}

/// What a `call:` target is.
#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) enum Kind {
    Action,
    Agent,
    Program,
    Workflow,
}

impl Kind {
    pub(crate) fn a(self) -> &'static str {
        match self {
            Kind::Action => "a tool's action",
            Kind::Agent => "an agent",
            Kind::Program => "a program",
            Kind::Workflow => "a workflow",
        }
    }

    pub(crate) fn collection(self) -> &'static str {
        match self {
            Kind::Action => "tools",
            Kind::Agent => "agents",
            Kind::Program => "programs",
            Kind::Workflow => "workflows",
        }
    }
}

pub(crate) enum Resolved {
    One(Kind),
    Several(Vec<Kind>),
    /// The fix to give.
    Nothing(String),
}

/// `<tool>/<action>`, an agent, a program or a workflow.
pub(crate) fn resolve(document: &Node, target: &str) -> Resolved {
    if let Some((tool, action)) = target.split_once('/') {
        let Some(t) = entry_in(document, "tools", tool) else {
            return Resolved::Nothing(offer("tools", document, &format!("`tools/{tool}.yaml`")));
        };
        let actions = t.get("actions").and_then(Node::as_map);
        if actions.is_some_and(|a| a.contains_key(action)) {
            return Resolved::One(Kind::Action);
        }
        let known: Vec<String> = actions
            .into_iter()
            .flat_map(|a| a.keys())
            .map(|a| format!("`{tool}/{a}`"))
            .collect();
        return Resolved::Nothing(if known.is_empty() {
            format!("The tool '{tool}' has no actions yet. Add `{action}:` under its `actions:`.")
        } else {
            format!(
                "Change it to one of: {} — or add `{action}:` under the tool's `actions:`.",
                known.join(", ")
            )
        });
    }
    let found: Vec<Kind> = [Kind::Agent, Kind::Program, Kind::Workflow]
        .into_iter()
        .filter(|k| entry_in(document, k.collection(), target).is_some())
        .collect();
    match found.as_slice() {
        [one] => Resolved::One(*one),
        [] => Resolved::Nothing(offer(
            "",
            document,
            &format!("`agents/{target}/agent.yaml` or `workflows/{target}.yaml`"),
        )),
        _ => Resolved::Several(found),
    }
}

/// "Change it to one of: ... — or add a file ...", from what is there.
fn offer(only: &str, document: &Node, file: &str) -> String {
    let mut known: Vec<String> = Vec::new();
    for collection in ["agents", "programs", "workflows", "tools"] {
        if !only.is_empty() && collection != only {
            continue;
        }
        for (name, entry) in document
            .get(collection)
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            if collection != "tools" {
                known.push(format!("`{name}`"));
                continue;
            }
            for action in entry
                .node
                .get("actions")
                .and_then(Node::as_map)
                .into_iter()
                .flat_map(|a| a.keys())
            {
                known.push(format!("`{name}/{action}`"));
            }
        }
    }
    if known.is_empty() {
        format!("Nothing is declared there yet. Add a file {file}.")
    } else {
        format!(
            "Change it to one of: {} — or add a file {file}.",
            known.join(", ")
        )
    }
}

pub(crate) fn entry_in<'a>(document: &'a Node, collection: &str, name: &str) -> Option<&'a Node> {
    document.get(collection)?.get(name)
}

pub(crate) fn does(stage: &Node) -> Option<&str> {
    stage.get("does").and_then(Node::as_str).map(str::trim)
}

/// A value written as one item or as a list of them.
pub(crate) fn list(node: &Node) -> Vec<&Node> {
    match node.as_list() {
        Some(items) => items.iter().collect(),
        None => vec![node],
    }
}

/// The key and its value: `does: each`, underlined whole.
fn entry_span(entry: &pact_doc::Entry) -> Span {
    entry.key_span.clone().merge(&entry.node.span)
}

fn said_yes(n: &Node) -> bool {
    match &n.value {
        Value::Bool(b) => *b,
        Value::Str(s) => matches!(s.trim(), "yes" | "true" | "on"),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn doc(text: &str) -> Node {
        parse_yaml(text, camino::Utf8Path::new("workflows-test.yaml")).expect("parses")
    }

    fn rules(text: &str) -> Vec<&'static str> {
        let mut d = Diagnostics::new();
        check(&doc(text), &mut d);
        d.items().iter().map(|x| x.rule).collect()
    }

    #[test]
    fn a_stage_goes_on_through_its_outcomes_its_labels_and_the_ports_it_hears() {
        let stage = doc(
            "then:\n  answered: a\n  heard:\n    fee: b\n  nobody-answered: stop-and-say-so\n\
             chooses-between:\n  yes: c\n  no: done\n",
        );
        assert_eq!(
            successors(&stage, true),
            vec!["a", "b", "stop-and-say-so", "c", "done"]
        );
    }

    #[test]
    fn a_stage_goes_on_only_through_the_outcomes_its_does_has() {
        let decide = doc("does: decide\nchooses-between:\n  yes: c\nthen:\n  answered: a\n");
        assert_eq!(successors(&decide, true), vec!["c"]);
        let call = doc("does: call\nthen:\n  answered: a\n  declined: b\n  used-a-tool: c\n");
        assert_eq!(successors(&call, true), vec!["a"]);
        assert_eq!(
            successors(&doc("does: answer\nthen:\n  answered: a\n"), true),
            Vec::<&str>::new()
        );
        // An agent's loop keeps the outcomes it has always had, and no workflow's.
        let think = doc("does: think\nthen:\n  used-a-tool: a\n  answered: b\n  declined: c\n");
        assert_eq!(successors(&think, false), vec!["a", "b"]);
    }

    #[test]
    fn a_call_written_as_a_binding_is_not_a_name() {
        assert!(is_binding("steps.pick.runbook") && is_binding("input.flow") && is_binding("item"));
        assert!(!is_binding("orders/look-up") && !is_binding("sorter") && !is_binding("stepsx.a"));
    }

    #[test]
    fn a_line_belongs_with_the_does_its_help_names() {
        let base = "workflows:\n  w:\n    description: d\n    starts-at: a\n    steps:\n      a:\n";
        assert_eq!(
            rules(&format!(
                "{base}        does: answer\n        over: input.x\n"
            )),
            vec!["loader/a-line-this-stage-never-reads"]
        );
        assert!(rules(&format!(
            "{base}        does: each\n        over: input.x\n        limits:\n          items-at-most: 2\n"
        ))
        .is_empty());
    }

    #[test]
    fn the_schemas_unknown_field_gives_way_to_the_workflows_own_words() {
        let mut d = Diagnostics::new();
        let at = Span::new("w.yaml", 2, 1, 10, 15);
        d.push(Diagnostic::error(
            "schema/unknown-field",
            at.clone(),
            "m",
            "f",
        ));
        d.push(Diagnostic::error(
            "loader/a-workflow-with-a-mind-of-its-own",
            at,
            "m",
            "f",
        ));
        d.push(Diagnostic::error(
            "schema/unknown-field",
            Span::new("w.yaml", 9, 1, 90, 95),
            "m",
            "f",
        ));
        told_once(&mut d);
        let left: Vec<&str> = d.items().iter().map(|x| x.rule).collect();
        assert_eq!(
            left,
            vec![
                "loader/a-workflow-with-a-mind-of-its-own",
                "schema/unknown-field"
            ]
        );
    }
}
