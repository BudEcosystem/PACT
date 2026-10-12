//! **Deciding by models and people** (02W §2.5, §2.12 `model.kind`, §3, F1).
//!
//! A `decide` tries its rungs in order: written rules, then agents (a decision
//! model is an agent whose model has `kind: decision`), then a person. The
//! rules half of WF-15 and WF-16 is `conditions::decides`; this is the rest.
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/one-rung-one-way` | §2.5 | a rung writes none, or more than one, of `rules:`, `agent:` and `asks:` |
//! | `loader/a-rung-out-of-order` | §2.5 | a person rung (`asks:`) is not the last rung, or the first rung writes `if-it-disagrees:` (there is no rung before it) |
//! | `loader/a-label-with-nowhere-to-go` | WF-15 (agent and person half) | an agent rung's agent, or a person rung's question, answers with no single `one of` line, or with one whose labels differ from `chooses-between:` (an agent may add `not-sure`) |
//! | `loader/a-decide-that-can-run-out-of-rungs` | WF-16 (agent half) | the last rung is an agent that may pass the decision on: its `one of` line has `not-sure`, or it writes `if-unsure-below:` or `if-it-disagrees: go-on` |
//! | `loader/sure-only-a-decision-model-can-be` | WF-17 | `if-unsure-below:` on an agent none of whose models has `kind: decision` |
//!
//! And one thing the schema cannot know: an agent all of whose models are
//! decision models needs no `instructions:` (`model.kind`'s own help), so the
//! schema's `missing-field` for it is withdrawn ([`told_once`]).
//!
//! Which models are decision models is read from both catalogue layers, the
//! distribution's and the workspace's own `models/catalog.yaml` (a workspace
//! row wins), under each row's id and every alias.

use crate::bindings::Shapes;
use crate::{waits, workflows};
use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use pact_schema::Schema;
use pact_schema::shape::Shape;
use std::collections::{BTreeMap, BTreeSet};

/// The label an agent answers when it is not sure, passing the decision on.
pub const NOT_SURE: &str = "not-sure";

/// The three ways a rung decides.
const WAYS: [&str; 3] = ["rules", "agent", "asks"];

/// Every check on the agent and person rungs, over the loaded document.
/// `builtin` is the distribution's `models/catalog.yaml`, as text.
pub fn check(document: &Node, schema: &Schema, builtin: &str, diags: &mut Diagnostics) {
    let decision = decision_models(builtin, document);
    let shapes = Shapes::of(document, schema);
    for (_, entry) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        for (stage, node) in waits::every_stage(&entry.node) {
            if workflows::does(node) == Some("decide") {
                let at = Decide {
                    document,
                    workflow: &entry.node,
                    shapes: &shapes,
                    decision: &decision,
                    stage,
                    node,
                };
                at.rungs(diags);
            }
        }
    }
}

/// Withdraw the schema's `missing-field` for `instructions:` on an agent that
/// runs only on decision models: a classifier is given no words.
pub fn told_once(document: &Node, builtin: &str, diags: &mut Diagnostics) {
    let decision = decision_models(builtin, document);
    let quiet: Vec<_> = document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .filter(|(_, e)| decides_alone(&e.node, &decision))
        .map(|(_, e)| e.node.span.start_of_block())
        .collect();
    diags.retain(|d| {
        !(d.rule == "schema/missing-field"
            && d.message.contains("'instructions'")
            && quiet.contains(&d.span))
    });
}

/// Whether `agent` runs on decision models only, so needs no instructions.
pub fn decides_alone(agent: &Node, decision: &BTreeSet<String>) -> bool {
    let models = models_of(agent);
    !models.is_empty() && models.iter().all(|m| decision.contains(*m))
}

/// Every id (and alias) of a catalogue row with `kind: decision`, from the
/// distribution's catalogue and then the workspace's own rows, which win.
pub fn decision_models(builtin: &str, document: &Node) -> BTreeSet<String> {
    let mut kind: BTreeMap<String, bool> = BTreeMap::new();
    let path = camino::Utf8Path::new("models/catalog.yaml");
    let shipped = pact_doc::parse_yaml(builtin, path).ok();
    let layers = [shipped.as_ref(), document.get("models")];
    for rows in layers
        .into_iter()
        .flatten()
        .filter_map(|c| c.get("models").and_then(Node::as_map))
    {
        for (name, row) in rows {
            let decides =
                row.node.get("kind").and_then(Node::as_str).map(str::trim) == Some("decision");
            let aliases = row.node.get("also-known-as").map(workflows::list);
            for id in std::iter::once(name.as_str())
                .chain(aliases.into_iter().flatten().filter_map(Node::as_str))
            {
                kind.insert(id.trim().to_string(), decides);
            }
        }
    }
    kind.into_iter()
        .filter(|(_, d)| *d)
        .map(|(n, _)| n)
        .collect()
}

/// The models an agent names, in order (`model:` is one id or a fallback list).
fn models_of(agent: &Node) -> Vec<&str> {
    agent
        .get("model")
        .map(workflows::list)
        .unwrap_or_default()
        .into_iter()
        .filter_map(Node::as_str)
        .map(str::trim)
        .collect()
}

/// One `decide` stage, with what its checks read.
struct Decide<'a> {
    document: &'a Node,
    workflow: &'a Node,
    shapes: &'a Shapes<'a>,
    decision: &'a BTreeSet<String>,
    stage: &'a str,
    node: &'a Node,
}

/// The `one of` line a rung's agent or question answers with.
struct Picks<'a> {
    field: &'a str,
    choices: Vec<String>,
    at: &'a Node,
}

impl<'a> Decide<'a> {
    fn labels(&self) -> Vec<&'a str> {
        self.node
            .get("chooses-between")
            .and_then(Node::as_map)
            .map(|m| m.keys().map(String::as_str).collect())
            .unwrap_or_default()
    }

    fn rungs(&self, diags: &mut Diagnostics) {
        let Some(rungs) = self.node.get("by").and_then(Node::as_list) else {
            return;
        };
        let stage = self.stage;
        for (i, rung) in rungs.iter().enumerate() {
            let Some(map) = rung.as_map() else {
                continue;
            };
            let ways: Vec<&str> = WAYS.into_iter().filter(|w| map.contains_key(*w)).collect();
            match ways.as_slice() {
                [] => diags.push(Diagnostic::error(
                    "loader/one-rung-one-way",
                    rung.span.clone(),
                    format!(
                        "A rung of '{stage}' says no way of deciding — no `rules:`, `agent:` or \
                         `asks:` — so it decides nothing."
                    ),
                    "Write one of the three: `- rules: [...]`, `- agent: <an agent>` or \
                     `- asks: <a question>`."
                        .to_string(),
                )),
                [_] => {}
                [a, b, ..] => diags.push(Diagnostic::error(
                    "loader/one-rung-one-way",
                    rung.span.clone(),
                    format!(
                        "A rung of '{stage}' writes `{a}:` and `{b}:`, and a rung is one way of \
                         deciding — so nothing says which is tried first."
                    ),
                    format!(
                        "Split it into one rung each, in the order they are tried — `- {a}: ...` \
                         and then `- {b}: ...`."
                    ),
                )),
            }
            if let Some(asks) = map.get("asks").filter(|_| i + 1 < rungs.len()) {
                diags.push(Diagnostic::error(
                    "loader/a-rung-out-of-order",
                    asks.key_span.clone(),
                    format!(
                        "'{stage}' asks a person in a rung that is not its last, and a person \
                         always decides — so the rungs after it are never tried."
                    ),
                    "Move this rung to the end of `by:`, or delete the rungs after it.".to_string(),
                ));
            }
            if let Some(disagrees) = map.get("if-it-disagrees").filter(|_| i == 0) {
                diags.push(Diagnostic::error(
                    "loader/a-rung-out-of-order",
                    disagrees.key_span.clone(),
                    format!(
                        "The first rung of '{stage}' writes `if-it-disagrees:`, and there is no \
                         rung before it to disagree with."
                    ),
                    "Delete `if-it-disagrees:`, or move this rung after the one it is compared \
                     with."
                        .to_string(),
                ));
            }
            let last = i + 1 == rungs.len();
            if ways.len() == 1 {
                self.agent_rung(map, last, diags);
                self.person_rung(map, diags);
            }
        }
    }

    /// WF-15, WF-16 and WF-17 for a rung that asks an agent.
    fn agent_rung(&self, rung: &pact_doc::Map, last: bool, diags: &mut Diagnostics) {
        let Some(written) = rung.get("agent") else {
            return;
        };
        let Some(name) = written.node.as_str().map(str::trim) else {
            return;
        };
        // A name that is nothing is `names: agents`' to tell.
        let Some(agent) = workflows::entry_in(self.document, "agents", name) else {
            return;
        };
        let stage = self.stage;
        let who = format!("the agent '{name}'");
        let picks = self.picks(&who, agent.get("answers-with"), true, &written.node, diags);
        let unsure = rung.get("if-unsure-below");
        if let Some(unsure) = unsure
            && !models_of(agent).iter().any(|m| self.decision.contains(*m))
        {
            diags.push(Diagnostic::error(
                "loader/sure-only-a-decision-model-can-be",
                unsure.key_span.clone(),
                format!(
                    "'{stage}' passes the decision on when '{name}' is under {} sure, and \
                     '{name}' runs on a language model, which has no honest score — so the \
                     line can never be kept.",
                    unsure.node.as_str().map(str::trim).unwrap_or("a figure")
                ),
                format!(
                    "Delete `if-unsure-below:` and add `{NOT_SURE}` to the agent's `one of` line, \
                     so it says when it is unsure. Or run '{name}' on a decision model — a \
                     catalogue row with `kind: decision`."
                ),
            ));
        }
        let says_unsure = picks
            .as_ref()
            .is_some_and(|p| p.choices.iter().any(|c| c == NOT_SURE));
        let goes_on = rung
            .get("if-it-disagrees")
            .and_then(|d| d.node.as_str())
            .is_some_and(|d| d.trim() == "go-on");
        if last && (says_unsure || unsure.is_some() || goes_on) {
            let (why, case) = if says_unsure {
                (format!("which may answer `{NOT_SURE}`"), "it is unsure of")
            } else if unsure.is_some() {
                (
                    "which passes the decision on when it is unsure".to_string(),
                    "it is unsure of",
                )
            } else {
                (
                    "which passes the decision on when it disagrees with the rung before it"
                        .to_string(),
                    "they disagree on",
                )
            };
            diags.push(Diagnostic::error(
                "loader/a-decide-that-can-run-out-of-rungs",
                written.node.span.clone(),
                format!(
                    "'{stage}' ends with '{name}', {why} — so a case {case} is decided \
                     by nobody and the run stops there."
                ),
                "End with a person rung after it — `- asks: <a question>` — or with written \
                 rules that end in an \"otherwise\"."
                    .to_string(),
            ));
        }
    }

    /// WF-15 for the person rung: its question's answer names the labels.
    fn person_rung(&self, rung: &pact_doc::Map, diags: &mut Diagnostics) {
        let Some(written) = rung.get("asks") else {
            return;
        };
        let Some(name) = written.node.as_str().map(str::trim) else {
            return;
        };
        let Some(q) = waits::question_of(self.document, self.workflow, name) else {
            return;
        };
        let who = format!("the question '{name}'");
        self.picks(&who, q.get("answer"), false, &written.node, diags);
    }

    /// The one `one of` line of `answers`, held to the stage's labels (WF-15).
    /// `None` when there is none to hold, after saying so.
    fn picks(
        &self,
        who: &str,
        answers: Option<&'a Node>,
        may_be_unsure: bool,
        at: &Node,
        diags: &mut Diagnostics,
    ) -> Option<Picks<'a>> {
        let stage = self.stage;
        let labels = self.labels();
        let lines: Vec<Picks> = answers
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
            .filter_map(|(field, e)| match self.shapes.line(&e.node)?.shape {
                Shape::OneOf(choices) => Some(Picks {
                    field,
                    choices,
                    at: &e.node,
                }),
                _ => None,
            })
            .collect();
        let wanted = format!(
            "one of {}{}",
            labels.join(", "),
            if may_be_unsure {
                format!(" (and `{NOT_SURE}` to pass the decision on)")
            } else {
                String::new()
            }
        );
        let label = |s: &str| format!("'{s}'");
        if lines.len() != 1 {
            diags.push(Diagnostic::error(
                "loader/a-label-with-nowhere-to-go",
                at.span.clone(),
                format!(
                    "'{stage}' asks {who} to pick a label, and it answers with {} — so nothing \
                     it says is one label.",
                    if lines.is_empty() {
                        "no `one of` line".to_string()
                    } else {
                        format!("{} `one of` lines", lines.len())
                    }
                ),
                format!("Give it one answer line `label: {wanted}`."),
            ));
            return None;
        }
        let picks = lines.into_iter().next()?;
        let offered: BTreeSet<&str> = picks
            .choices
            .iter()
            .map(String::as_str)
            .filter(|c| !(may_be_unsure && *c == NOT_SURE))
            .collect();
        let chooses: BTreeSet<&str> = labels.iter().copied().collect();
        let extra: Vec<String> = offered.difference(&chooses).map(|s| label(s)).collect();
        let never: Vec<String> = chooses.difference(&offered).map(|s| label(s)).collect();
        if extra.is_empty() && never.is_empty() {
            return Some(picks);
        }
        let mut why = Vec::new();
        if !extra.is_empty() {
            why.push(format!(
                "{} {} nowhere to go",
                extra.join(", "),
                if extra.len() == 1 { "has" } else { "have" }
            ));
        }
        if !never.is_empty() {
            why.push(format!("{} is never picked", never.join(", ")));
        }
        diags.push(
            Diagnostic::error(
                "loader/a-label-with-nowhere-to-go",
                at.span.clone(),
                format!(
                    "'{stage}' asks {who}, which answers `{}: one of {}`, and '{stage}' chooses \
                     between {} — so {}.",
                    picks.field,
                    picks.choices.join(", "),
                    labels
                        .iter()
                        .map(|l| label(l))
                        .collect::<Vec<_>>()
                        .join(", "),
                    why.join(", and ")
                ),
                format!(
                    "Write `{}: {wanted}`, or change `chooses-between:` to the labels it picks.",
                    picks.field
                ),
            )
            .with_related(picks.at.span.clone(), "the answer line"),
        );
        Some(picks)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn doc(text: &str) -> Node {
        parse_yaml(text, camino::Utf8Path::new("deciding-test.yaml")).expect("parses")
    }

    #[test]
    fn a_workspace_row_decides_what_kind_a_model_is_under_every_name() {
        let builtin = "models:\n  sorter:\n    kind: decision\n  chat: {}\n";
        let d = doc("models:\n  models:\n    sorter: { kind: language }\n    \
             local-sorter: { kind: decision, also-known-as: [ls] }\n");
        let found = decision_models(builtin, &d);
        assert_eq!(
            found.into_iter().collect::<Vec<_>>(),
            vec!["local-sorter".to_string(), "ls".to_string()]
        );
    }

    #[test]
    fn only_an_agent_on_decision_models_alone_needs_no_instructions() {
        let decision: BTreeSet<String> = ["sorter".to_string()].into();
        assert!(decides_alone(&doc("model: sorter\n"), &decision));
        assert!(!decides_alone(&doc("model: [sorter, chat]\n"), &decision));
        assert!(!decides_alone(&doc("description: x\n"), &decision));
    }
}
