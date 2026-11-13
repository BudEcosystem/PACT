//! Statements: the steps of a workflow, written in the order they run.
//!
//! A workflow in the document is a set of named stages, each saying where to
//! go next. Written out that way it is exact and it reads like wiring. Here
//! the same thing is written as a short program:
//!
//! ```text
//! workflow deliver
//!   takes brief: text
//!   gives result: text
//!
//!   research = call researcher with brief: input.brief
//!   plan = call planner with brief: input.brief, findings: research.findings
//!   make = call builder with plan: plan.plan
//!   answer with result: make.result
//! ```
//!
//! | Statement | Becomes |
//! |---|---|
//! | `<name> = <statement>` | the stage `<name>`; without it the stage is named from what it does |
//! | `call <target> [with <input>: <binding>, …]` | `does: call`, `call:`, `bind:` |
//! | `for each item in <binding>` + body | `does: each`, `over:`, and the body as its `steps:` |
//! | `repeat [at most <n> times]` + body | `does: repeat`, `at-most:`, and the body as its `steps:` |
//! | `together` + body | `does: together`; every statement in the body starts at once |
//! | `decide` + `if <label>` lines | `does: decide`, `chooses-between:` |
//! | `decide with kind: triage.kind` | the same, and `bind:` — what the agents that decide are given |
//! | `answer [with <field>: <binding>, …]` | `does: answer`, `bind:` |
//! | `stop <binding>` | `does: stop`, `stops:` |
//! | `ask <question>` | `does: ask-someone`, `asks:` |
//! | `think` · `use tools` · `check its work` · `run code` | `does:` that |
//!
//! **Order is the wiring.** A statement goes on to the one written after it
//! (`then: { answered: <next> }`), and the first one is where the body starts
//! (`starts-at:`). An `answer` goes nowhere. Under `decide`, the statements
//! beneath each `if` are stages beside the decision, and the last of them
//! goes on to whatever is written after the `decide`.
//!
//! **A name is a variable.** `plan = call planner …` names the stage `plan`,
//! and `plan.findings` anywhere after it is `steps.plan.findings`. A path that
//! starts with one of the words a binding starts with — `input`, `item`,
//! `remembers`, `values`, `steps` and the rest — is left as written.
//!
//! Settings go beneath a statement, as they go beneath anything: `at-most:`,
//! `if-it-fails:`, `limits:`. A `then:` written there is kept, and where it
//! says `answered:` the order written here does not.

use super::*;
use crate::bound;

/// The openings a statement can have, for a refusal's fix.
pub(super) const OPENINGS: &[&str] = &[
    "call", "for each", "repeat", "together", "decide", "answer", "stop", "ask", "think",
    "use tools", "check its work", "run code",
];

/// The stages that are one word and nothing else.
const PLAIN: &[(&str, &str)] = &[
    ("think", "think"),
    ("use tools", "use-tools"),
    ("check its work", "check-its-work"),
    ("run code", "run-code"),
];

/// Where a stage goes when it has finished.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Ends {
    /// On to the statement written after it.
    Goes,
    /// Nowhere: it is the answer.
    Answers,
    /// Wherever the decision says; what is written after it is where its
    /// branches come back together.
    Decides,
}

pub(super) struct Step {
    name: String,
    at: Span,
    fields: Map,
    ends: Ends,
    /// Under a `decide`: the statements beneath each `if`, which are stages
    /// beside the decision and not inside it.
    branches: Vec<Vec<Step>>,
}

/// What a line turned out to be.
enum Line2 {
    Step(Box<Step>),
    /// It was a statement and it was wrong; the problem is already reported.
    Refused,
    NotOne,
}

impl<'a> Reader<'a> {
    /// A body whose statements are steps: a workflow's, a loop's, or the
    /// inside of a `for each`, a `repeat` or a `together`.
    pub(super) fn flow_body(&mut self, range: Range<usize>, kind: Kind, in_turn: bool) -> Map {
        let (mut map, steps) = self.flow_parts(range, kind);
        self.arrange(steps, in_turn, &mut map);
        map
    }

    /// The settings of a body and its statements, in the order written.
    fn flow_parts(&mut self, range: Range<usize>, kind: Kind) -> (Map, Vec<Step>) {
        let mut map = Map::new();
        let mut steps = Vec::new();
        for (first, rest) in self.items(range) {
            let l = self.lines[first];
            if setting_key(l.text).is_none() {
                self.lines[first].text = uncommented(l.text);
                match self.statement(first, rest.clone()) {
                    Line2::Step(step) => {
                        steps.push(*step);
                        continue;
                    }
                    Line2::Refused => continue,
                    Line2::NotOne => {}
                }
            }
            self.item(first, rest, kind, &mut map);
        }
        (map, steps)
    }

    /// Put the statements of one body in the document: `steps:`, each going
    /// on to the next, and `starts-at:` the first.
    fn arrange(&mut self, steps: Vec<Step>, in_turn: bool, map: &mut Map) {
        let Some(first) = steps.first() else { return };
        let (name, span) = (first.name.clone(), first.at.clone());
        let mut placed = Map::new();
        self.place(steps, None, in_turn, &mut placed);
        self.put(map, "steps".to_string(), span.clone(), Node::map(placed, span.clone()));
        if in_turn && !map.contains_key("starts-at") {
            map.insert(
                "starts-at".to_string(),
                Entry {
                    key_span: span.clone(),
                    node: s(name, &span),
                },
            );
        }
    }

    fn place(&mut self, steps: Vec<Step>, join: Option<String>, in_turn: bool, placed: &mut Map) {
        let names: Vec<String> = steps.iter().map(|s| s.name.clone()).collect();
        for (i, mut step) in steps.into_iter().enumerate() {
            let next = if in_turn {
                names.get(i + 1).cloned().or_else(|| join.clone())
            } else {
                None
            };
            match step.ends {
                Ends::Goes => {
                    let said = step
                        .fields
                        .get("then")
                        .and_then(|e| e.node.as_map())
                        .is_some_and(|t| t.contains_key("answered"));
                    if let Some(next) = next.filter(|_| !said) {
                        let span = step.at.clone();
                        let then = map_of(vec![("answered", s(next, &span))], &span);
                        self.put(&mut step.fields, "then".to_string(), span, then);
                    }
                }
                Ends::Answers => {}
                Ends::Decides => {
                    for branch in std::mem::take(&mut step.branches) {
                        self.place(branch, next.clone(), true, placed);
                    }
                }
            }
            if let Some(prior) = placed.get(&step.name) {
                let prior = prior.key_span.clone();
                self.diags.push(
                    Diagnostic::error(
                        "lang/said-twice",
                        step.at,
                        format!("Two steps here are both called '{}'.", step.name),
                        format!(
                            "Give one of them a name of its own: `<name> = …`. A step with no \
                             name is called after what it does, which is how these two came to \
                             share '{}'.",
                            step.name
                        ),
                    )
                    .with_related(prior, "the other one"),
                );
                continue;
            }
            let span = step.at.clone();
            placed.insert(
                step.name,
                Entry {
                    key_span: span.clone(),
                    node: Node::map(step.fields, span),
                },
            );
        }
    }

    /// Read one statement, with everything beneath it.
    fn statement(&mut self, first: usize, rest: Range<usize>) -> Line2 {
        let l = self.lines[first];
        let t = l.text;
        let (named, at) = match t.find(" = ") {
            Some(n) if bare_word(&t[..n]) => (Some((t[..n].to_string(), self.at(&l, 0, n))), n + 3),
            _ => (None, 0),
        };
        let said = &t[at..];
        let whole = self.whole(&l);
        let mut fields = Map::new();
        let does = |me: &mut Self, fields: &mut Map, what: &str, at: &Span| {
            me.put(fields, "does".to_string(), at.clone(), s(what, at));
        };
        let mut ends = Ends::Goes;
        let mut branches = Vec::new();
        let default: String;

        if let Some(n) = after(said, "call ") {
            let (target, with) = match said[n..].find(" with ") {
                Some(w) => (said[n..n + w].trim(), Some(at + n + w + 6)),
                None => (said[n..].trim(), None),
            };
            if target.is_empty() {
                self.error(
                    "lang/not-a-line",
                    whole,
                    "This `call` does not say what it calls.".to_string(),
                    "Write `call <an agent, a workflow, a program or a tool/action>`.".to_string(),
                );
                return Line2::Refused;
            }
            does(self, &mut fields, "call", &whole);
            let ts = self.at(&l, at + n, target.len());
            self.put(&mut fields, "call".to_string(), ts.clone(), s(target, &ts));
            if let Some(with) = with {
                match self.binds(&l, with) {
                    Some(node) => self.put(&mut fields, "bind".to_string(), whole.clone(), node),
                    None => return Line2::Refused,
                }
            }
            self.beneath(rest, &mut fields);
            default = slug(target);
        } else if said == "answer" || said.starts_with("answer with ") {
            does(self, &mut fields, "answer", &whole);
            if said != "answer" {
                match self.binds(&l, at + "answer with ".len()) {
                    Some(node) => self.put(&mut fields, "bind".to_string(), whole.clone(), node),
                    None => return Line2::Refused,
                }
            }
            self.beneath(rest, &mut fields);
            ends = Ends::Answers;
            default = "answer".to_string();
        } else if let Some(n) = after(said, "for each ") {
            let Some(list) = said[n..].strip_prefix("item in ").map(str::trim).filter(|b| !b.is_empty())
            else {
                self.error(
                    "lang/not-a-line",
                    whole,
                    "A `for each` says which list it goes through.".to_string(),
                    "Write `for each item in <the list>` — `for each item in input.documents`. \
                     Inside it, one item's parts are read as `item.<part>`."
                        .to_string(),
                );
                return Line2::Refused;
            };
            does(self, &mut fields, "each", &whole);
            let ls = self.at(&l, t.len() - list.len(), list.len());
            self.put(&mut fields, "over".to_string(), ls.clone(), s(bound(list), &ls));
            let inner = self.flow_body(rest, Kind::Stage, true);
            self.merge(&mut fields, inner);
            default = "each".to_string();
        } else if said == "repeat" || said.starts_with("repeat ") {
            does(self, &mut fields, "repeat", &whole);
            if said != "repeat" {
                let count = said
                    .strip_prefix("repeat at most ")
                    .and_then(|r| r.strip_suffix(" times").or_else(|| r.strip_suffix(" time")))
                    .map(str::trim)
                    .filter(|c| !c.is_empty());
                let Some(count) = count else {
                    self.error(
                        "lang/not-a-line",
                        whole,
                        "A `repeat` says how many rounds at most.".to_string(),
                        "Write `repeat at most 4 times`. What ends it sooner goes beneath, as \
                         `until:`."
                            .to_string(),
                    );
                    return Line2::Refused;
                };
                let cs = self.at(&l, at + "repeat at most ".len(), count.len());
                let node = self.scalar(count, &cs);
                self.put(&mut fields, "at-most".to_string(), cs, node);
            }
            let inner = self.flow_body(rest, Kind::Stage, true);
            self.merge(&mut fields, inner);
            default = "repeat".to_string();
        } else if said == "together" {
            does(self, &mut fields, "together", &whole);
            let inner = self.flow_body(rest, Kind::Stage, false);
            self.merge(&mut fields, inner);
            default = "together".to_string();
        } else if said == "decide" || said.starts_with("decide with ") {
            does(self, &mut fields, "decide", &whole);
            // What the agents that decide are given besides the workflow's
            // input and the item: `decide with kind: triage.kind`, the same
            // `with` a `call` has.
            if said != "decide" {
                match self.binds(&l, at + "decide with ".len()) {
                    Some(node) => self.put(&mut fields, "bind".to_string(), whole.clone(), node),
                    None => return Line2::Refused,
                }
            }
            branches = self.decision(rest, &whole, &mut fields);
            ends = Ends::Decides;
            default = "decide".to_string();
        } else if let Some(n) = after(said, "stop ") {
            let what = said[n..].trim();
            does(self, &mut fields, "stop", &whole);
            let ws = self.at(&l, at + n, what.len());
            self.put(&mut fields, "stops".to_string(), ws.clone(), s(bound(what), &ws));
            self.beneath(rest, &mut fields);
            default = "stop".to_string();
        } else if let Some(n) = after(said, "ask ") {
            let question = said[n..].trim();
            does(self, &mut fields, "ask-someone", &whole);
            let qs = self.at(&l, at + n, question.len());
            self.put(&mut fields, "asks".to_string(), qs.clone(), s(question, &qs));
            self.beneath(rest, &mut fields);
            default = slug(said);
        } else if let Some((_, word)) = PLAIN.iter().find(|(words, _)| *words == said) {
            does(self, &mut fields, word, &whole);
            self.beneath(rest, &mut fields);
            default = (*word).to_string();
        } else if named.is_some() {
            self.error(
                "lang/not-a-line",
                whole,
                "This names a step and does not say what the step does.".to_string(),
                format!("After the `=`, write a statement starting with one of: {}.", OPENINGS.join(", ")),
            );
            return Line2::Refused;
        } else {
            return Line2::NotOne;
        }

        let (name, at) = named.unwrap_or((default, whole));
        Line2::Step(Box::new(Step {
            name,
            at,
            fields,
            ends,
            branches,
        }))
    }

    /// The settings beneath a statement that has no statements inside it.
    fn beneath(&mut self, rest: Range<usize>, fields: &mut Map) {
        let more = self.body(rest, Kind::Plain);
        self.merge(fields, more);
    }

    fn merge(&mut self, fields: &mut Map, more: Map) {
        for (k, e) in more {
            self.put(fields, k, e.key_span, e.node);
        }
    }

    /// What is beneath a `decide`: its settings, and an `if` for each label.
    /// `if <label>: <stage>` points at a stage; `if <label>` with statements
    /// beneath is those statements, and the label leads to the first.
    fn decision(&mut self, rest: Range<usize>, whole: &Span, fields: &mut Map) -> Vec<Vec<Step>> {
        let mut choices = Map::new();
        let mut branches = Vec::new();
        for (first, under) in self.items(rest) {
            let l = self.lines[first];
            if setting_key(l.text).is_some() {
                self.setting(first, under, fields);
                continue;
            }
            self.lines[first].text = uncommented(l.text);
            let l = self.lines[first];
            let Some(n) = after(l.text, "if ") else {
                self.item(first, under, Kind::Decision, fields);
                continue;
            };
            let said = &l.text[n..];
            let (label, target) = match said.split_once(':') {
                Some((label, target)) => (label.trim(), Some(target.trim())),
                None => (said.trim(), None),
            };
            let ls = self.at(&l, n, label.len().max(1));
            if !bare_word(label) {
                self.error(
                    "lang/not-a-line",
                    ls,
                    "An `if` names one of the labels the decision can pick.".to_string(),
                    "Write `if <label>` with the steps for it beneath, or `if <label>: <step>` \
                     to go to a step written elsewhere. `done` ends the run."
                        .to_string(),
                );
                continue;
            }
            let leads_to = match target {
                Some(target) if !target.is_empty() => {
                    if self.significant(&under) {
                        let span = self.whole(&self.lines[under.start]);
                        self.error(
                            "lang/nothing-goes-under-this",
                            span,
                            format!("This `if` already says where '{label}' leads: to '{target}'."),
                            format!(
                                "Take `: {target}` off the line above to write its steps here, \
                                 or take these lines out."
                            ),
                        );
                    }
                    target.to_string()
                }
                _ => {
                    let (settings, steps) = self.flow_parts(under, Kind::Stage);
                    if let Some((key, e)) = settings.iter().next() {
                        self.error(
                            "lang/not-a-line",
                            e.key_span.clone(),
                            format!("'{key}' is a setting, and beneath an `if` there is no step for it to be a setting of."),
                            "Indent it under the step it belongs to.".to_string(),
                        );
                    }
                    let Some(first) = steps.first() else {
                        self.error(
                            "lang/not-a-line",
                            ls,
                            format!("Nothing is written for '{label}' to do."),
                            format!(
                                "Write its steps beneath this line, or `if {label}: done` to end \
                                 the run there."
                            ),
                        );
                        continue;
                    };
                    let name = first.name.clone();
                    branches.push(steps);
                    name
                }
            };
            self.put(&mut choices, label.to_string(), ls.clone(), s(leads_to, &ls));
        }
        if !choices.is_empty() {
            self.put(
                fields,
                "chooses-between".to_string(),
                whole.clone(),
                Node::map(choices, whole.clone()),
            );
        }
        branches
    }

    /// `brief: input.brief, findings: research.findings` — what a call is
    /// given, or what an answer hands back. Each is a path; one that starts
    /// with a step's name is that step's answer.
    fn binds(&mut self, l: &Line, at: usize) -> Option<Node> {
        let mut m = Map::new();
        let mut from = at;
        for piece in l.text[at..].split(',') {
            let here = from;
            from += piece.len() + 1;
            let lead = piece.len() - piece.trim_start().len();
            let said = piece.trim();
            let Some((key, value)) = said.split_once(':').map(|(k, v)| (k.trim(), v.trim())) else {
                let span = self.at(l, here + lead, said.len().max(1));
                self.error(
                    "lang/not-a-line",
                    span,
                    "Each thing given here needs its name and where it comes from.".to_string(),
                    "Write `<input>: <where from>`, with commas between them — `brief: \
                     input.brief, findings: research.findings`."
                        .to_string(),
                );
                return None;
            };
            let ks = self.at(l, here + lead, key.len().max(1));
            if key.is_empty() || value.is_empty() {
                self.error(
                    "lang/not-a-line",
                    ks,
                    "This is missing its name, or where it comes from.".to_string(),
                    "Write `<input>: <where from>` — `brief: input.brief`.".to_string(),
                );
                return None;
            }
            let value_at = here + piece.rfind(value).unwrap_or(lead);
            let vs = self.at(l, value_at, value.len());
            self.put(&mut m, key.to_string(), ks, s(bound(value), &vs));
        }
        Some(Node::map(m, self.whole(l)))
    }
}
