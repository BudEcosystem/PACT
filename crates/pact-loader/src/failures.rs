//! **What happens after a failure, how a write is undone, and where silence may
//! never lead** (02W §2.7, §2.10, §2.12, §3).
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/silence-reaches-a-gated-step` | WF-20 | a `nobody-answered` exit of a wait a person answers reaches, before another wait a person answers, a stage guarded by a policy rule or `needs-a-person`, or a stage making a write (the same `<tool>/<action>`, agent or workflow) the wait's `answered` exit also makes |
//! | `loader/cannot-be-undone-and-nobody-asked` *(note)* | WF-25 | a workflow stage calls a tool's write that has no `undone-by:` and no *Ask before* |
//! | `loader/an-undo-that-does-not-fit` | WF-26 | an `undone-by:` (an action's, a stage's, a workflow's) names a read, or an undo whose inputs the write's inputs and answer cannot fill |
//! | `loader/a-status-check-that-does-not-fit` | new | an action's `status-check:` names a write, or a read whose inputs the call's own cannot fill |
//! | `loader/a-check-nothing-can-run` | WF-34 | a workflow has a `judged:` check and its evals name no `graded-by:` model |
//! | `loader/a-line-this-stage-never-reads` | WF-3 | `undo-where:` when `undo:` names a stage that is not an `each` |
//! | `schema/missing-companion` | §2.10 | a workflow's `when-it-runs-out:` says `use-a-backup`, `wait-for-a-new-version` or `undo` with no companion under the stage's `if-it-fails:` |
//! | `loader/no-such-name` | shipped | an `undone-by:`, `status-check:` or `backup:` names nothing here |
//!
//! How the stage's `bind:` fits its `backup:`, and what `carry-on-with:` reads
//! and stands in for, are bindings, held in `bindings.rs` (WF-4 to WF-7, WF-39).
//!
//! **Silence never approves** (WAIT-4, R13, R50). A wait only the clock and
//! events answer has no gate, so its one exit may lead anywhere. A wait a person
//! answers may not, by its silence, do what its yes would have done: make a
//! write the `answered` exit also makes, by whichever stage (*Changes* or
//! *Can't be undone*: the undo of a write runs only on a failure plan, never by
//! itself), or reach a stage whose call a person must allow first. The walk
//! stays in the `steps:` the wait is written in, goes on through every exit of
//! a wait only the clock or events answer (it is no gate), and stops at the next
//! wait a person answers, at `done` and at `stop-and-say-so`.

use crate::bindings::{self, Shapes};
use crate::conditions::{self, Position};
use crate::waits;
use crate::workflows::{self, Kind, Resolved};
use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Entry, Map, Node};
use pact_schema::Schema;
use pact_schema::shape::Line;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

/// The `when-it-runs-out:` choices whose companion line is the stage's
/// `if-it-fails:` one (02W §2.10), with what that line says.
const COMPANIONS: [(&str, &str, &str); 3] = [
    ("use-a-backup", "backup", "what to call instead"),
    (
        "wait-for-a-new-version",
        "new-version-of",
        "whose new version to wait for",
    ),
    ("undo", "undo", "which stage's work to undo"),
];

/// Where a path ends: the finish line, and the stop.
const ENDS: [&str; 2] = ["done", "stop-and-say-so"];

/// Every check on failure plans, undo and silence, over the loaded document.
pub fn check(document: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let shapes = Shapes::of(document, schema);
    actions(document, &shapes, diags);
    let policies = document.get("policies").and_then(Node::as_map);
    for (name, entry) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let w = &entry.node;
        let flow = Flow {
            document,
            shapes: &shapes,
            name,
            workflow: w,
            guards: crate::money::guarded_by(w, policies).unwrap_or_default(),
        };
        if let Some(undo) = w.as_map().and_then(|m| m.get("undone-by")) {
            let gives = Gives {
                inputs: lines(&shapes, w.get("accepts")),
                answers: lines(&shapes, w.get("answers-with")),
            };
            undone_by(&flow, &format!("the workflow '{name}'"), Some(&gives), undo, diags);
        }
        flow.own_limits(diags);
        if let Some(steps) = w.get("steps").and_then(Node::as_map) {
            flow.stages(steps, diags);
        }
        flow.judged(diags);
    }
}

// ─────────────────────────────────────────────────────────────────── actions

/// An action's own `undone-by:` and `status-check:`.
fn actions(document: &Node, shapes: &Shapes, diags: &mut Diagnostics) {
    let flow = Flow {
        document,
        shapes,
        name: "",
        workflow: document,
        guards: BTreeSet::new(),
    };
    for (tool, t) in document
        .get("tools")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        for (action, a) in t
            .node
            .get("actions")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            let Some(fields) = a.node.as_map() else {
                continue;
            };
            let gives = Gives {
                inputs: lines(shapes, a.node.get("takes")),
                answers: lines(shapes, a.node.get("answers-with")),
            };
            let who = format!("`{tool}/{action}`");
            if let Some(undo) = fields.get("undone-by") {
                undone_by(&flow, &who, Some(&gives), undo, diags);
            }
            if let Some(asked) = fields.get("status-check") {
                status_check(&flow, &who, &gives, asked, diags);
            }
        }
    }
}

/// What a write hands its undo: its inputs and its answer, each line read.
struct Gives {
    inputs: Vec<(String, Option<Line>)>,
    answers: Vec<(String, Option<Line>)>,
}

impl Gives {
    /// Whether an input `name`, in the shape `want`, is filled from these.
    fn fills(&self, shapes: &Shapes, name: &str, want: Option<&Line>) -> bool {
        self.inputs
            .iter()
            .chain(&self.answers)
            .filter(|(n, _)| n == name)
            .any(|(_, have)| match (have, want) {
                (Some(h), Some(w)) => shapes.fits(&h.shape, &w.shape),
                _ => true,
            })
    }

    /// "`a`, `b` (its inputs) and `c` (its answer)".
    fn said(&self) -> String {
        let names = |l: &[(String, Option<Line>)]| {
            l.iter()
                .map(|(n, _)| format!("`{n}`"))
                .collect::<Vec<_>>()
                .join(", ")
        };
        match (self.inputs.is_empty(), self.answers.is_empty()) {
            (true, true) => "nothing".to_string(),
            (false, true) => format!("{} (its inputs)", names(&self.inputs)),
            (true, false) => format!("{} (its answer)", names(&self.answers)),
            (false, false) => format!(
                "{} (its inputs) and {} (its answer)",
                names(&self.inputs),
                names(&self.answers)
            ),
        }
    }
}

/// A map of answer-shape lines, each read.
fn lines(shapes: &Shapes, map: Option<&Node>) -> Vec<(String, Option<Line>)> {
    map.and_then(Node::as_map)
        .into_iter()
        .flatten()
        .map(|(k, e)| (k.clone(), shapes.line(&e.node)))
        .collect()
}

/// The inputs of `target` that must be filled: every one not `, optional`.
fn required(document: &Node, shapes: &Shapes, target: &str) -> Option<Vec<(String, Option<Line>)>> {
    Some(
        bindings::inputs_of(document, shapes, target)?
            .into_iter()
            .filter(|(_, line, _)| !line.as_ref().is_some_and(|l| l.optional))
            .map(|(n, line, _)| (n, line))
            .collect(),
    )
}

/// A sentence's first word with its capital letter.
fn capital(s: &str) -> String {
    let mut c = s.chars();
    c.next()
        .map(|f| f.to_uppercase().chain(c).collect())
        .unwrap_or_default()
}

fn quoted(names: &[String]) -> String {
    names
        .iter()
        .map(|n| format!("`{n}`"))
        .collect::<Vec<_>>()
        .join(", ")
}

/// A name a line resolves (`<tool>/<action>`, an agent, a program, a workflow),
/// or the diagnostic that says it does not. `allowed` are the kinds this line
/// may name, and `what` says so in words.
fn resolves(
    document: &Node,
    said: &str,
    entry: &Entry,
    allowed: &[Kind],
    sentence: &dyn Fn(&str) -> String,
    what: &str,
    diags: &mut Diagnostics,
) -> bool {
    let at = entry.node.span.clone();
    match workflows::resolve(document, said) {
        Resolved::One(kind) if allowed.contains(&kind) => true,
        Resolved::One(kind) => {
            diags.push(Diagnostic::error(
                "loader/no-such-name",
                at,
                format!("{}, which is {}, and {what}.", sentence(said), kind.a()),
                format!("Name {what}."),
            ));
            false
        }
        // A workflow sharing its name is told once, at the workflow.
        Resolved::Several(found) if found.contains(&Kind::Workflow) => false,
        Resolved::Several(found) => {
            diags.push(workflows::two_things(said, &found, at));
            false
        }
        Resolved::Nothing(fix) => {
            diags.push(Diagnostic::error(
                "loader/no-such-name",
                at,
                format!(
                    "{}, and this workspace has nothing by that name.",
                    sentence(said)
                ),
                fix,
            ));
            false
        }
    }
}

/// An `undone-by:` names a tool's action or a workflow (`loader/no-such-name`)
/// that writes, and whose inputs the write's inputs and answer fill (WF-26).
fn undone_by(flow: &Flow, who: &str, gives: Option<&Gives>, undo: &Entry, diags: &mut Diagnostics) {
    let Some(said) = undo.node.as_str().map(str::trim) else {
        return;
    };
    let sentence = |s: &str| format!("{} is undone by '{s}'", capital(who));
    if !resolves(
        flow.document,
        said,
        undo,
        &[Kind::Action, Kind::Workflow],
        &sentence,
        "an undo is a tool's action or a workflow",
        diags,
    ) {
        return;
    }
    let given = gives.map_or("what it was given and answered".to_string(), Gives::said);
    if !workflows::writes(flow.document, said, &mut BTreeSet::new()) {
        diags.push(Diagnostic::error(
            "loader/an-undo-that-does-not-fit",
            undo.node.span.clone(),
            format!(
                "{} is undone by '{said}', which only reads — so undoing it would put nothing \
                 back.",
                capital(who)
            ),
            format!(
                "Name a write that reverses it, whose `takes:` is filled from {given}."
            ),
        ));
        return;
    }
    let (Some(gives), Some(takes)) = (gives, required(flow.document, flow.shapes, said)) else {
        return;
    };
    let unfilled: Vec<String> = takes
        .iter()
        .filter(|(n, line)| !gives.fills(flow.shapes, n, line.as_ref()))
        .map(|(n, _)| n.clone())
        .collect();
    if unfilled.is_empty() {
        return;
    }
    let all: Vec<String> = takes.iter().map(|(n, _)| n.clone()).collect();
    diags.push(Diagnostic::error(
        "loader/an-undo-that-does-not-fit",
        undo.node.span.clone(),
        format!(
            "{} is undone by '{said}', which takes {}, and an undo is given only what the write \
             was given and answered — so it could not be called.",
            capital(who),
            quoted(&unfilled)
        ),
        format!(
            "Name a write whose `takes:` fits: '{said}' takes {}, and {who} gives {given}.",
            quoted(&all)
        ),
    ));
}

/// An action's `status-check:` names a tool's action that only reads, and
/// whose inputs the action's own fill.
fn status_check(flow: &Flow, who: &str, gives: &Gives, asked: &Entry, diags: &mut Diagnostics) {
    let Some(said) = asked.node.as_str().map(str::trim) else {
        return;
    };
    let sentence = |s: &str| format!("{who} is checked by '{s}'");
    if !resolves(
        flow.document,
        said,
        asked,
        &[Kind::Action],
        &sentence,
        "a status check is a tool's action",
        diags,
    ) {
        return;
    }
    if workflows::writes(flow.document, said, &mut BTreeSet::new()) {
        diags.push(Diagnostic::error(
            "loader/a-status-check-that-does-not-fit",
            asked.node.span.clone(),
            format!(
                "{who} is checked by '{said}', which does not say `reads-only: yes` — so asking \
                 it whether the work already happened could do work of its own."
            ),
            format!(
                "Name an action that only looks things up, or write `reads-only: yes` under \
                 '{said}' if that is all it does."
            ),
        ));
        return;
    }
    let inputs = Gives {
        inputs: gives.inputs.clone(),
        answers: Vec::new(),
    };
    let Some(takes) = required(flow.document, flow.shapes, said) else {
        return;
    };
    let unfilled: Vec<String> = takes
        .iter()
        .filter(|(n, line)| !inputs.fills(flow.shapes, n, line.as_ref()))
        .map(|(n, _)| n.clone())
        .collect();
    if unfilled.is_empty() {
        return;
    }
    diags.push(Diagnostic::error(
        "loader/a-status-check-that-does-not-fit",
        asked.node.span.clone(),
        format!(
            "{who} is checked by '{said}', which takes {}, and a status check is given only the \
             call's own inputs — so it could not be asked.",
            quoted(&unfilled)
        ),
        format!(
            "Name a read whose `takes:` is filled from {}.",
            inputs.said()
        ),
    ));
}

// ─────────────────────────────────────────────────────────────────── workflows

/// One workflow, with what its checks read.
struct Flow<'a> {
    document: &'a Node,
    shapes: &'a Shapes<'a>,
    name: &'a str,
    workflow: &'a Node,
    /// Every `<tool>` and `<tool>/<action>` a rule in its policy names.
    guards: BTreeSet<String>,
}

/// What a silent exit reached that only a yes may reach.
enum Reached {
    /// A write the `answered` exit also makes: the call that makes it.
    Write(String),
    /// A stage whose call a person must allow first: the call, and why.
    Guarded(String, String),
}

impl<'a> Flow<'a> {
    /// Every stage of one `steps:`, and of every `steps:` inside it.
    fn stages(&self, steps: &'a Map, diags: &mut Diagnostics) {
        for (stage, entry) in steps {
            let Some(fields) = entry.node.as_map() else {
                continue;
            };
            let does = workflows::does(&entry.node).unwrap_or("");
            if let Some(undo) = fields.get("undone-by") {
                let gives = self.gives(fields);
                undone_by(self, &format!("'{stage}'"), gives.as_ref(), undo, diags);
            }
            if let Some(plan) = fields.get("if-it-fails").and_then(|e| e.node.as_map()) {
                self.plan(steps, stage, plan, diags);
            }
            self.companions(stage, fields, diags);
            match does {
                "call" => self.cannot_be_undone(stage, fields, diags),
                "ask-someone" => self.silence(steps, stage, &entry.node, diags),
                _ => {}
            }
            if let Some(inner) = fields.get("steps").and_then(|e| e.node.as_map()) {
                self.stages(inner, diags);
            }
        }
    }

    /// What a `call` stage hands an undo: its target's inputs (or its own
    /// `bind:`) and its target's answer.
    fn gives(&self, fields: &Map) -> Option<Gives> {
        let target = fields.get("call")?.node.as_str()?.trim();
        let inputs = match bindings::inputs_of(self.document, self.shapes, target) {
            Some(inputs) => inputs.into_iter().map(|(n, l, _)| (n, l)).collect(),
            None => bound(fields)
                .into_iter()
                .map(|n| (n.to_string(), None))
                .collect(),
        };
        Some(Gives {
            inputs,
            answers: bindings::answers_of(self.document, self.shapes, target).unwrap_or_default(),
        })
    }

    /// A stage's `if-it-fails:`: what its backup names, and what it undoes.
    /// How the stage's `bind:` fits the backup, and what `carry-on-with:`
    /// reads, are bindings (`bindings.rs`).
    fn plan(&self, steps: &Map, stage: &str, plan: &Map, diags: &mut Diagnostics) {
        if let Some(backup) = plan.get("backup") {
            self.backup(stage, backup, diags);
        }
        let Some(lines) = plan.get("undo-where") else {
            return;
        };
        for when in workflows::list(&lines.node) {
            conditions::line(when, Position::Elsewhere, None, &|_| None, diags);
        }
        let undone = plan
            .get("undo")
            .and_then(|e| e.node.as_str())
            .map(str::trim);
        let Some((undone, its)) = undone.and_then(|u| steps.get(u).map(|e| (u, &e.node))) else {
            return;
        };
        let does = workflows::does(its).unwrap_or("");
        if does != "each" {
            diags.push(Diagnostic::error(
                "loader/a-line-this-stage-never-reads",
                lines.key_span.clone(),
                format!(
                    "'{stage}' writes `undo-where:`, and '{undone}' does `{does}`, not `each` — \
                     so there are no items to choose among, and nothing reads this line."
                ),
                "Delete `undo-where:`, or point `undo:` at a stage that does `each`.".to_string(),
            ));
        }
    }

    /// `backup:` names a tool's action, an agent, a program or a workflow.
    fn backup(&self, stage: &str, backup: &Entry, diags: &mut Diagnostics) {
        let Some(said) = backup.node.as_str().map(str::trim) else {
            return;
        };
        let sentence = |s: &str| format!("'{stage}' falls back on '{s}'");
        let every = [Kind::Action, Kind::Agent, Kind::Program, Kind::Workflow];
        resolves(
            self.document,
            said,
            backup,
            &every,
            &sentence,
            "a backup is a tool's action, an agent, a program or a workflow",
            diags,
        );
    }

    /// 02W §2.10: a stage's `when-it-runs-out:` that needs a companion line
    /// takes it from the stage's `if-it-fails:`.
    fn companions(&self, stage: &str, fields: &Map, diags: &mut Diagnostics) {
        let Some(chose) = fields
            .get("limits")
            .and_then(|l| l.node.as_map())
            .and_then(|l| l.get("when-it-runs-out"))
        else {
            return;
        };
        let Some((choice, line, what)) = COMPANIONS
            .iter()
            .find(|(c, _, _)| chose.node.as_str().map(str::trim) == Some(c))
        else {
            return;
        };
        let plan = fields.get("if-it-fails").and_then(|e| e.node.as_map());
        if plan.is_some_and(|p| p.contains_key(*line)) {
            return;
        }
        diags.push(Diagnostic::error(
            "schema/missing-companion",
            workflows::entry_span(chose),
            format!(
                "'when-it-runs-out' says '{choice}', and '{stage}' has no `if-it-fails.{line}:` \
                 — so nothing says {what}."
            ),
            format!(
                "Add a line under '{stage}''s `if-it-fails:`: `{line}: <{}>` — {what}.",
                if *line == "backup" {
                    "what to call"
                } else {
                    "a name"
                }
            ),
        ));
    }

    /// A workflow's own `limits:`: no stage is there to take a backup or a
    /// version from. `undo` there undoes what the run did, newest first.
    fn own_limits(&self, diags: &mut Diagnostics) {
        let Some(chose) = self
            .workflow
            .get("limits")
            .and_then(Node::as_map)
            .and_then(|l| l.get("when-it-runs-out"))
        else {
            return;
        };
        let Some((choice, line, what)) = COMPANIONS
            .iter()
            .filter(|(c, _, _)| *c != "undo")
            .find(|(c, _, _)| chose.node.as_str().map(str::trim) == Some(c))
        else {
            return;
        };
        diags.push(Diagnostic::error(
            "schema/missing-companion",
            workflows::entry_span(chose),
            format!(
                "'when-it-runs-out' on the workflow '{}' says '{choice}', and only a stage has an \
                 `if-it-fails:` to take `{line}:` from — so nothing says {what}.",
                self.name
            ),
            "Write this limit on the stage it bounds, with the line under that stage's \
             `if-it-fails:` — or choose `stop-and-say-so`, `ask-a-person`, `carry-on` or `undo` \
             here."
                .to_string(),
        ));
    }

    /// Why a call needs a person's yes before it runs, if it does: its own
    /// `needs-a-person: yes`, or a rule in this workflow's policy naming it.
    fn guard_of(&self, target: &str) -> Option<String> {
        let (tool, action) = target.split_once('/')?;
        let node = workflows::entry_in(self.document, "tools", tool)?
            .get("actions")?
            .get(action)?;
        if crate::approvals::asked_for(node) {
            return Some("says `needs-a-person: yes`".to_string());
        }
        (self.guards.contains(target) || self.guards.contains(tool))
            .then(|| "a rule in this workflow's policy asks a person about".to_string())
    }

    /// The first call a stage makes (or a stage inside it makes, before any
    /// wait) that needs a person's yes: the stage, the call, and why.
    fn guarded_inside(&self, stage: &str, node: &'a Node) -> Option<(String, String, String)> {
        for said in calls(node) {
            if let Some(why) = self.guard_of(said) {
                return Some((stage.to_string(), said.to_string(), why));
            }
        }
        let body = node.get("steps").and_then(Node::as_map)?;
        let starts: Vec<&str> = match node.get("starts-at").and_then(Node::as_str) {
            Some(s) if workflows::does(node) != Some("together") => vec![s.trim()],
            _ => body.keys().map(String::as_str).collect(),
        };
        for start in starts {
            for name in reach(body, start, &|n| self.a_person_answers(n)) {
                if let Some(found) = body
                    .get(name)
                    .and_then(|e| self.guarded_inside(name, &e.node))
                {
                    return Some(found);
                }
            }
        }
        None
    }

    /// WF-25: a call to a tool's write with no undo and no *Ask before*.
    fn cannot_be_undone(&self, stage: &str, fields: &Map, diags: &mut Diagnostics) {
        let Some(call) = fields.get("call") else {
            return;
        };
        let Some(target) = call.node.as_str().map(str::trim) else {
            return;
        };
        let Some((tool, action)) = target.split_once('/') else {
            return;
        };
        if fields.contains_key("undone-by")
            || !workflows::action_writes(self.document, tool, action)
            || self.guard_of(target).is_some()
        {
            return;
        }
        let undoable = workflows::entry_in(self.document, "tools", tool)
            .and_then(|t| t.get("actions"))
            .and_then(|a| a.get(action))
            .is_some_and(|a| a.get("undone-by").is_some());
        if undoable {
            return;
        }
        diags.push(Diagnostic::note(
            "loader/cannot-be-undone-and-nobody-asked",
            call.node.span.clone(),
            format!(
                "'{stage}' calls `{target}`, which cannot be undone, and nobody is asked before \
                 it runs."
            ),
            format!(
                "Nothing to do if that is meant (a reminder text message). Otherwise ask first: \
                 write `needs-a-person: yes` under `{action}` in `tools/{tool}.yaml`, or a rule \
                 naming `{target}` in the workflow's `policy:`."
            ),
        ));
    }

    /// WF-20: where silence goes from a wait a person answers.
    fn silence(&self, steps: &'a Map, wait: &str, node: &Node, diags: &mut Diagnostics) {
        if !self.a_person_answers(node) {
            return;
        }
        let Some(then) = node.get("then").and_then(Node::as_map) else {
            return;
        };
        let Some(quiet) = then.get("nobody-answered") else {
            return;
        };
        let Some(to) = quiet.node.as_str().map(str::trim) else {
            return;
        };
        let yes = self.yes_of(steps, node);
        let made = self.writes_on(steps, &yes);
        let Some((path, reached)) = self.first_reached(steps, to, &made) else {
            return;
        };
        let here = path.last().cloned().unwrap_or_default();
        let through = if path.len() > 1 {
            format!(
                " (through {})",
                path[..path.len() - 1]
                    .iter()
                    .map(|s| format!("'{s}'"))
                    .collect::<Vec<_>>()
                    .join(" → ")
            )
        } else {
            String::new()
        };
        let message = match reached {
            Reached::Write(_) if yes.contains(here.as_str()) => format!(
                "'{here}' can be reached when nobody answered '{wait}'{through}, and '{here}' is \
                 what a yes would have done — so silence would act as a yes."
            ),
            Reached::Write(target) => format!(
                "'{here}' can be reached when nobody answered '{wait}'{through}, and it makes \
                 `{target}`, the write a yes would have made — so silence would act as a yes."
            ),
            Reached::Guarded(target, why) => format!(
                "'{here}' can be reached when nobody answered '{wait}'{through}, and it calls \
                 `{target}`, which {why} — so silence would stand where a yes must."
            ),
        };
        let fix = match self.somewhere_quiet(steps, wait, to, &yes, &made) {
            Some(other) => format!(
                "Send this exit somewhere that asks again or only tells someone — \
                 `nobody-answered: {other}` — or to `stop-and-say-so`."
            ),
            None => "Send this exit somewhere that asks again or only tells someone, or to \
                     `stop-and-say-so`."
                .to_string(),
        };
        diags.push(Diagnostic::error(
            "loader/silence-reaches-a-gated-step",
            quiet.key_span.clone(),
            message,
            fix,
        ));
    }

    /// Every stage of `steps` a yes leads to: what the wait's `answered:` exit
    /// reaches. At a later wait a person answers, only its own yes goes on (its
    /// silence or its no is not what this yes would have done); a wait only the
    /// clock and events answer goes on by every exit.
    fn yes_of(&self, steps: &'a Map, wait: &'a Node) -> BTreeSet<&'a str> {
        let mut out = BTreeSet::new();
        let Some(answered) = wait
            .get("then")
            .and_then(|t| t.get("answered"))
            .and_then(Node::as_str)
            .map(str::trim)
        else {
            return out;
        };
        let mut queue = VecDeque::from([answered]);
        while let Some(here) = queue.pop_front() {
            let Some((name, entry)) = steps.get_key_value(here) else {
                continue;
            };
            if !out.insert(name.as_str()) {
                continue;
            }
            let node = &entry.node;
            let next = if self.a_person_answers(node) {
                node.get("then")
                    .and_then(|t| t.get("answered"))
                    .and_then(Node::as_str)
                    .map(str::trim)
                    .into_iter()
                    .collect()
            } else {
                workflows::successors(node, true)
            };
            queue.extend(next.into_iter().filter(|n| !ENDS.contains(n)));
        }
        out
    }

    /// Whether a stage is a wait some person, group or contact answers.
    fn a_person_answers(&self, node: &Node) -> bool {
        workflows::does(node) == Some("ask-someone")
            && node
                .get("asks")
                .and_then(Node::as_str)
                .and_then(|asks| waits::question_of(self.document, self.workflow, asks.trim()))
                .is_some_and(|q| {
                    waits::answerers(self.document, q)
                        .iter()
                        .any(|(_, a)| a.reads())
                })
    }

    /// Every write the stages `on` make ([`Flow::writes_made`]).
    fn writes_on(&self, steps: &Map, on: &BTreeSet<&str>) -> BTreeSet<String> {
        on.iter()
            .filter_map(|s| steps.get(*s))
            .flat_map(|e| self.writes_made(&e.node))
            .collect()
    }

    /// The writes a stage makes, by what it calls: each `<tool>/<action>`,
    /// agent or workflow it (or a stage inside it) calls or may call that
    /// writes. Two stages calling the same write do the same thing.
    fn writes_made(&self, node: &Node) -> BTreeSet<String> {
        let mut out: BTreeSet<String> = calls(node)
            .into_iter()
            .filter(|t| workflows::writes(self.document, t, &mut BTreeSet::new()))
            .map(str::to_string)
            .collect();
        for e in node
            .get("steps")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            out.extend(self.writes_made(&e.1.node));
        }
        out
    }

    /// The first stage a silent exit to `from` reaches that only a yes may
    /// reach, with the way there: one guarded, or one making a write in
    /// `made` (what the yes makes). The walk goes on through every exit of a
    /// wait only the clock or events answer, and stops at one a person does.
    fn first_reached(
        &self,
        steps: &'a Map,
        from: &'a str,
        made: &BTreeSet<String>,
    ) -> Option<(Vec<String>, Reached)> {
        let mut came_from: BTreeMap<&str, &str> = BTreeMap::new();
        let mut seen: BTreeSet<&str> = BTreeSet::from([from]);
        let mut queue = VecDeque::from([from]);
        while let Some(here) = queue.pop_front() {
            let Some(node) = steps.get(here).map(|e| &e.node) else {
                continue;
            };
            if self.a_person_answers(node) {
                continue;
            }
            let path = || {
                let mut p = vec![here.to_string()];
                let mut at = here;
                while let Some(before) = came_from.get(at) {
                    p.push(before.to_string());
                    at = before;
                }
                p.reverse();
                p
            };
            if let Some((inner, target, why)) = self.guarded_inside(here, node) {
                let mut p = path();
                if inner != here {
                    p.push(inner);
                }
                return Some((p, Reached::Guarded(target, why)));
            }
            if let Some(write) = self.writes_made(node).intersection(made).next() {
                return Some((path(), Reached::Write(write.clone())));
            }
            for next in workflows::successors(node, true) {
                if !ENDS.contains(&next) && steps.contains_key(next) && seen.insert(next) {
                    came_from.insert(next, here);
                    queue.push_back(next);
                }
            }
        }
        None
    }

    /// A stage silence could go to instead: where another wait here sends its
    /// silence, else another wait (it asks again), when nothing a yes needs is
    /// reached from it.
    fn somewhere_quiet(
        &self,
        steps: &'a Map,
        wait: &str,
        to: &str,
        yes: &BTreeSet<&str>,
        made: &BTreeSet<String>,
    ) -> Option<&'a str> {
        let waits = || {
            steps
                .iter()
                .filter(|(n, e)| n.as_str() != wait && workflows::does(&e.node) == Some("ask-someone"))
        };
        let quiet = waits().filter_map(|(_, e)| {
            e.node
                .get("then")
                .and_then(|t| t.get("nobody-answered"))
                .and_then(Node::as_str)
                .map(str::trim)
        });
        let asking = waits().map(|(n, _)| n.as_str());
        let candidates: Vec<&'a str> = quiet.chain(asking).collect();
        candidates.into_iter().find(|c| {
            *c != to
                && !ENDS.contains(c)
                && steps.contains_key(*c)
                && !yes.contains(c)
                && self.first_reached(steps, c, made).is_none()
        })
    }

    /// WF-34: a `judged:` check in this workflow, and no `graded-by:` model on
    /// the checks it names.
    fn judged(&self, diags: &mut Diagnostics) {
        let named = self.workflow.get("evals").and_then(Node::as_str);
        let suite = named.and_then(|_| self.document.get("evals"));
        if suite.is_some_and(|s| s.get("graded-by").is_some()) {
            return;
        }
        let why = match named {
            None => format!(
                "the workflow '{}' names no `evals:`, so no `graded-by:` model is there to read \
                 the answer",
                self.name
            ),
            Some(_) => "the checks this workflow names have no `graded-by:` model".to_string(),
        };
        let fix = "Name the judge — `graded-by: <a model>` in `evals/suite.yaml`, with the \
                   workflow's `evals:` pointing at it — or check with a rule that needs no \
                   reader, such as `must-contain:`."
            .to_string();
        for (stage, node) in waits::every_stage(self.workflow) {
            for rule in node
                .get("checked-by")
                .and_then(Node::as_list)
                .into_iter()
                .flatten()
            {
                if let Some(judged) = rule.as_map().and_then(|r| r.get("judged")) {
                    diags.push(Diagnostic::error(
                        "loader/a-check-nothing-can-run",
                        judged.key_span.clone(),
                        format!(
                            "'{stage}' is checked by a judged rule, and nothing can grade it: \
                             {why}."
                        ),
                        fix.clone(),
                    ));
                }
            }
        }
        let suite_judges = suite
            .and_then(|s| s.get("rules"))
            .and_then(Node::as_list)
            .is_some_and(|rules| rules.iter().any(|r| r.get("judged").is_some()));
        if let (true, Some(evals)) = (
            suite_judges,
            self.workflow.as_map().and_then(|m| m.get("evals")),
        ) {
            diags.push(Diagnostic::error(
                "loader/a-check-nothing-can-run",
                evals.node.span.clone(),
                format!(
                    "The workflow '{}' is held to checks with a judged rule, and they name no \
                     `graded-by:` model — so nothing can grade it.",
                    self.name
                ),
                fix,
            ));
        }
    }
}

/// The names a stage's `call:` and `may-call:` write.
fn calls(node: &Node) -> Vec<&str> {
    let mut out: Vec<&str> = node
        .get("call")
        .and_then(Node::as_str)
        .map(str::trim)
        .into_iter()
        .collect();
    if let Some(may) = node.get("may-call") {
        out.extend(
            workflows::list(may)
                .into_iter()
                .filter_map(Node::as_str)
                .map(str::trim),
        );
    }
    out
}

/// The inputs a stage's `bind:` fills, a dotted key (`fills.first-name`) by
/// the input it is part of.
fn bound(fields: &Map) -> Vec<&str> {
    let mut out: Vec<&str> = fields
        .get("bind")
        .and_then(|e| e.node.as_map())
        .into_iter()
        .flat_map(|m| m.keys())
        .map(|k| k.split('.').next().unwrap_or(k))
        .collect();
    out.dedup();
    out
}

/// The stages of `steps` reached from `from`, in the order a walk finds them;
/// the walk ends at a stage `stops` says (which is itself left out).
fn reach<'m>(steps: &'m Map, from: &str, stops: &dyn Fn(&Node) -> bool) -> Vec<&'m str> {
    let Some((start, _)) = steps.get_key_value(from) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    let mut seen: BTreeSet<&str> = BTreeSet::from([start.as_str()]);
    let mut queue = VecDeque::from([start.as_str()]);
    while let Some(here) = queue.pop_front() {
        let Some(node) = steps.get(here).map(|e| &e.node) else {
            continue;
        };
        if stops(node) {
            continue;
        }
        out.push(here);
        for next in workflows::successors(node, true) {
            if let Some((name, _)) = steps.get_key_value(next)
                && !ENDS.contains(&next)
                && seen.insert(name.as_str())
            {
                queue.push_back(name.as_str());
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn doc(text: &str) -> Node {
        parse_yaml(text, camino::Utf8Path::new("failures-test.yaml")).expect("parses")
    }

    #[test]
    fn a_walk_from_a_stage_stops_at_a_wait_and_at_the_ends() {
        let d = doc(
            "a:\n  does: call\n  then: {answered: b}\nb:\n  does: ask-someone\n  then: {answered: c}\n\
             c:\n  does: call\n  then: {answered: done}\n",
        );
        let steps = d.as_map().expect("a map");
        let waits = |n: &Node| workflows::does(n) == Some("ask-someone");
        assert_eq!(reach(steps, "a", &waits), vec!["a"]);
        assert_eq!(reach(steps, "a", &|_| false), vec!["a", "b", "c"]);
        assert!(reach(steps, "nowhere", &|_| false).is_empty());
    }

    #[test]
    fn a_dotted_binding_fills_the_input_it_is_part_of() {
        let d = doc("bind:\n  to: x\n  fills.a: y\n  fills.b: z\n");
        assert_eq!(bound(d.as_map().expect("a map")), vec!["to", "fills"]);
    }
}
