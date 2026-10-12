//! **Money and writes that cannot be undone, on the paths a workflow takes**
//! (02W §3 WF-23 extended, WF-24, F1 reopened).
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/money-moves-with-nobody-asked` *(extended)* | WF-23 | a workflow stage calls an action with `spends-money: yes` that no policy rule and no `needs-a-person:` guards, and a path reaches it from the start (a warning, as on an agent), or from a `decide` an agent may choose for (an error: a model chose the path), with neither a wait a person answers nor a `decide` by written rules or a person on the way |
//! | `loader/a-model-chose-what-cannot-be-undone` | WF-24 | a stage calls an action that writes and cannot be undone (no `undone-by:` on it or on the stage) and nobody is asked first, and the nearest `decide` before it may be chosen by an agent, with no wait a person answers between. It takes the place of WF-25's note on that call |
//!
//! **The walk** is WF-20's (`failures::reach`), from a different start. It
//! goes from the workflow's first stage (WF-23's "nobody asked"), and from each
//! label of a `decide` with an agent rung (a path a model may have picked). It
//! stops at a `decide` (the nearest one is the one that chose; one by written
//! rules or a person is a written rule or a person) and at a wait a person
//! answers (where its silence may lead is WF-20's to hold). It goes into the
//! inside of an `each`, `repeat` or `together` and not back out of it, and
//! never into a called workflow: a call to a workflow is judged by that
//! workflow's own checks. The paths a model picked are walked first, so a call
//! both reach is told about as a model's choice.
//!
//! A `decide` with an agent rung counts as chosen by a model even beside a
//! person rung: when the agent is sure, nobody else is asked.

use crate::failures::{calls, cannot_be_undone_unasked, guard_of, reach, starts_of};
use crate::{money, waits, workflows};
use pact_diag::{Diagnostic, Diagnostics, Severity, Span};
use pact_doc::{Map, Node};
use std::collections::BTreeSet;

/// Where a walk started: the workflow's first stage, or a label a model may pick.
#[derive(Clone, Copy)]
enum Origin<'a> {
    Start,
    /// The `decide`, and the agent on its rung.
    Picked(&'a str, &'a str),
}

/// Every money call and every write that cannot be undone, on every path.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let policies = document.get("policies").and_then(Node::as_map);
    for (_, entry) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let w = &entry.node;
        let Some(steps) = w.get("steps").and_then(Node::as_map) else {
            continue;
        };
        let mut walk = Walk {
            document,
            workflow: w,
            guards: money::guarded_by(w, policies).unwrap_or_default(),
            said: BTreeSet::new(),
            diags,
        };
        walk.decides(steps);
        for start in starts_of(w, steps) {
            walk.from(steps, start, Origin::Start);
        }
    }
}

/// The agent a `decide` may let choose: its first agent rung's.
fn agent_of(decide: &Node) -> Option<&str> {
    workflows::list(decide.get("by")?)
        .into_iter()
        .find_map(|r| r.get("agent").and_then(Node::as_str).map(str::trim))
}

/// What a diagnostic is about, to tell it once.
fn key(at: &Span, rule: &'static str) -> (String, usize, &'static str) {
    (at.file.to_string(), at.byte_start, rule)
}

struct Walk<'a, 'd> {
    document: &'a Node,
    workflow: &'a Node,
    guards: BTreeSet<String>,
    /// Each `call:` already told about, by where it is and the rule.
    said: BTreeSet<(String, usize, &'static str)>,
    diags: &'d mut Diagnostics,
}

impl<'a> Walk<'a, '_> {
    /// A walk from every label of every `decide` an agent may choose for, in
    /// `steps` and in every `steps:` inside it.
    fn decides(&mut self, steps: &'a Map) {
        for (name, e) in steps {
            if workflows::does(&e.node) == Some("decide")
                && let Some(agent) = agent_of(&e.node)
            {
                let labels = e.node.get("chooses-between").and_then(Node::as_map);
                for (_, to) in labels.into_iter().flatten() {
                    if let Some(to) = to.node.as_str() {
                        self.from(steps, to.trim(), Origin::Picked(name, agent));
                    }
                }
            }
            if let Some(inner) = e.node.get("steps").and_then(Node::as_map) {
                self.decides(inner);
            }
        }
    }

    /// Every stage of `steps` reached from `start` before a `decide` or a
    /// wait a person answers, and every stage inside them.
    fn from(&mut self, steps: &'a Map, start: &str, origin: Origin<'a>) {
        let (document, workflow) = (self.document, self.workflow);
        let stops = |n: &Node| {
            workflows::does(n) == Some("decide") || waits::a_person_answers(document, workflow, n)
        };
        for name in reach(steps, start, &stops) {
            let Some(node) = steps.get(name).map(|e| &e.node) else {
                continue;
            };
            self.calls_of(name, node, origin);
            if let Some(body) = node.get("steps").and_then(Node::as_map) {
                for inner in starts_of(node, body) {
                    self.from(body, inner, origin);
                }
            }
        }
    }

    /// WF-23 and WF-24 for the calls one stage makes.
    fn calls_of(&mut self, stage: &str, node: &Node, origin: Origin) {
        let Some(at) = node.get("call").map(|c| c.span.clone()) else {
            return;
        };
        for target in calls(node) {
            let Some((tool, action)) = target.split_once('/') else {
                continue;
            };
            let Some(spec) = workflows::entry_in(self.document, "tools", tool)
                .and_then(|t| t.get("actions"))
                .and_then(|a| a.get(action))
            else {
                continue;
            };
            if guard_of(self.document, &self.guards, target).is_some() {
                continue;
            }
            // From the start, as on an agent, a workspace may mean an ungated
            // spend; a path a model picked may not move money unasked (F1).
            let (path, severity) = match origin {
                Origin::Start => (
                    "a path from the start reaches it".to_string(),
                    Severity::Warning,
                ),
                Origin::Picked(decide, agent) => (
                    format!("the path to it may be picked by the agent '{agent}' at '{decide}'"),
                    Severity::Error,
                ),
            };
            if money::moves_money(spec).is_some()
                && self
                    .said
                    .insert(key(&at, "loader/money-moves-with-nobody-asked"))
            {
                self.diags.push(Diagnostic::new(
                    severity,
                    "loader/money-moves-with-nobody-asked",
                    at.clone(),
                    format!(
                        "'{stage}' calls `{target}`, which moves money, and {path} with nobody \
                         answering yes and no written rule choosing it — so money moves \
                         without anybody being asked."
                    ),
                    format!(
                        "Write `needs-a-person: yes` under `{action}` in `tools/{tool}.yaml`, or \
                         a rule naming `{target}` in the workflow's `policy:` with the figure \
                         under which nobody is asked — or put a wait a person answers on that \
                         path."
                    ),
                ));
            }
            let Origin::Picked(decide, agent) = origin else {
                continue;
            };
            if cannot_be_undone_unasked(self.document, &self.guards, node, target)
                && self
                    .said
                    .insert(key(&at, "loader/a-model-chose-what-cannot-be-undone"))
            {
                self.diags.push(Diagnostic::error(
                    "loader/a-model-chose-what-cannot-be-undone",
                    at.clone(),
                    format!(
                        "'{stage}' calls `{target}`, which cannot be undone, and the path to it \
                         may be picked by the agent '{agent}' at '{decide}', with nobody \
                         answering yes between — so a model's choice would do what nobody can \
                         take back."
                    ),
                    format!(
                        "Ask a person before the write: a wait between '{decide}' and \
                         '{stage}', or `needs-a-person: yes` under `{action}` in \
                         `tools/{tool}.yaml`. Or let '{decide}' decide by written rules and a \
                         person only."
                    ),
                ));
                // WF-25's note says there may be nothing to do; here there is.
                self.diags.retain(|d| {
                    !(d.rule == "loader/cannot-be-undone-and-nobody-asked" && d.span == at)
                });
            }
        }
    }
}
