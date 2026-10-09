//! **Bindings and shapes in a workflow** (02W §2.0, §2.11, §2.15, §3).
//!
//! A binding is a path, never an expression (02W §2.0): `input.<field>`,
//! `steps.<stage>.<field>`, `item.<field>`, `latest-update.<field>`,
//! `remembers.<name>`, `run-inputs.<name>`, `values.<name>`, `used.<ceiling>`.
//! What no single value can say about one is held here:
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/a-binding-to-nothing` | WF-4 | a binding names no stage, field, input, memory or start |
//! | `loader/a-binding-to-a-stage-that-may-not-have-run` | WF-5 | some path reaches the reading stage (or, for `comes-from:` and `until:`, the end of the round) without passing the named one, and the input it fills is not `, optional` |
//! | `loader/a-binding-from-later` | WF-6 | the stage reads one that runs after it (in a repeat, later in the round) |
//! | `loader/an-item-outside-for-each` | WF-7 | `item.` outside an `each` body |
//! | `loader/a-target-picked-from-nowhere` | WF-9 | `call:` is a binding with no `may-call:` |
//! | `loader/remembered-from-nowhere` | WF-13 | a repeat's `remembers:` entry has no `comes-from:`, or one that reads outside the round |
//! | `loader/until-that-cannot-change` | WF-14 | `until:`'s `value:` lines read nothing the round writes (an `until:` of `tool:` lines only asks its tool each round) |
//! | `loader/a-call-that-does-not-fit` | WF-39 | a call's `bind:` leaves a required input (or a required part of one filled part by part, `fills.first-name`) of its target empty, names one it does not take or a part its shape does not have, or binds the wrong shape |
//! | `loader/a-shape-made-of-itself` | new | a shape under `workspace.shapes` is, through its parts, made of itself |
//! | `loader/a-line-this-stage-never-reads` | WF-3 | `comes-from:`, `combines-by:` or `lasts: one-run` on memory that is not a repeat's, or `kept-per:` on an agent's or a port's |
//!
//! **What a stage may read** (WF-5, WF-6) is a question about the paths
//! through its own `steps:`: a stage the reading stage cannot reach without
//! passing is one every path has run (it dominates the reader). A stage inside
//! an `each`, a `repeat` or a `together` is read only inside it; from inside,
//! an outer stage is judged from the stage that holds the body. A `together`'s
//! stages all start at once, so none of them has run when a sibling starts.
//!
//! **Shapes** are read by `pact_schema::shape`, the one reader the schema's
//! `schema/not-an-answer-shape` uses too, so a line means the same thing to the
//! check that admits it and to the rule that fits a binding to it.
//!
//! `values.<name>` is not resolved here: `values:` is put in place and removed
//! before any check reads the tree (`values.rs`), and a value table read when
//! a stage starts is the value-table work that follows.

use crate::workflows::{self, Kind, Resolved};
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Entry, Map, Node, Value};
use pact_schema::shape::{self, Line, Shape};
use pact_schema::{Schema, suggest};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

/// Where a binding starts (02W §2.0).
const ROOTS: &[&str] = &[
    "input",
    "steps",
    "item",
    "latest-update",
    "remembers",
    "run-inputs",
    "values",
    "used",
];

/// What every stage has besides its answer (02W §2.0's `steps.` row).
const STAGE_FIELDS: &[&str] = &[
    "outcome",
    "label",
    "decided-by",
    "answered-by",
    "ended",
    "rounds",
    "run",
];

/// What the host supplies to every workflow run (02W §2.0's `run-inputs.` row).
const HOST_INPUTS: &[&str] = &["requester", "asked-in"];

/// Whether `said` is written as a binding: one of the start words, alone or
/// followed by a dot.
pub(crate) fn is_binding(said: &str) -> bool {
    let said = said.trim();
    said.split_once('.')
        .is_some_and(|(root, _)| ROOTS.contains(&root))
        || ROOTS.contains(&said)
}

/// Every binding and shape check, over the loaded document.
pub fn check(document: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let shapes = Shapes::of(document, schema);
    shapes.go_round(diags);
    memory_lines(document, diags);
    for (name, entry) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let Some(steps) = entry.node.get("steps").and_then(Node::as_map) else {
            continue;
        };
        let flow = Flow {
            document,
            shapes: &shapes,
            node: &entry.node,
            name,
        };
        let start = entry.node.get("starts-at").and_then(Node::as_str);
        let mut frames = vec![Frame {
            steps,
            start: start.map(str::trim),
            holder: None,
        }];
        flow.stages(&mut frames, diags);
        flow.anywhere(&entry.node, diags);
    }
}

// ─────────────────────────────────────────────────────────────────── shapes

/// The answer-shape vocabulary and the workspace's named shapes.
struct Shapes<'a> {
    vocabulary: Vec<(String, Vec<String>)>,
    named: Vec<&'a str>,
    parts: BTreeMap<&'a str, &'a Map>,
    declared_at: BTreeMap<&'a str, Span>,
}

impl<'a> Shapes<'a> {
    fn of(document: &'a Node, schema: &Schema) -> Self {
        let map = document.get("shapes").and_then(Node::as_map);
        let mut parts = BTreeMap::new();
        let mut declared_at = BTreeMap::new();
        for (name, entry) in map.into_iter().flatten() {
            if let Some(m) = entry.node.as_map() {
                parts.insert(name.as_str(), m);
            }
            declared_at.insert(name.as_str(), entry.key_span.clone());
        }
        Shapes {
            vocabulary: shape::vocabulary(schema),
            named: parts.keys().copied().collect(),
            parts,
            declared_at,
        }
    }

    /// A written line, or `None` when it is no shape (the schema says so).
    fn line(&self, node: &Node) -> Option<Line> {
        shape::parse(node.as_str()?, &self.vocabulary, &self.named).ok()
    }

    /// A named shape's parts, each read.
    fn parts_of(&self, name: &str) -> Option<Vec<(String, Line)>> {
        let map = self.parts.get(name)?;
        Some(
            map.iter()
                .filter_map(|(k, e)| self.line(&e.node).map(|l| (k.clone(), l)))
                .collect(),
        )
    }

    fn fits(&self, have: &Shape, want: &Shape) -> bool {
        have.fits(want, &|n| self.parts_of(n))
    }

    /// `loader/a-shape-made-of-itself`: a named shape that, through its parts,
    /// is made of itself. A shape is a fixed set of parts, so every reader (the
    /// model's schema, a person's form, a tool's arguments) can be built from
    /// it once, with no end to find.
    fn go_round(&self, diags: &mut Diagnostics) {
        let mut told: BTreeSet<Vec<&str>> = BTreeSet::new();
        for start in self.named.iter().copied() {
            let mut path = vec![start];
            if let Some(circle) = self.circle_from(&mut path) {
                let mut key = circle.clone();
                key.sort();
                if !told.insert(key) {
                    continue;
                }
                let said = circle
                    .iter()
                    .map(|s| format!("'{s}'"))
                    .collect::<Vec<_>>()
                    .join(" has a part that is ");
                diags.push(Diagnostic::error(
                    "loader/a-shape-made-of-itself",
                    self.declared_at[start].clone(),
                    format!(
                        "The shape '{start}' is made of itself: {said}, which is '{start}' again, \
                         and a shape is a fixed set of parts, never one that holds itself."
                    ),
                    "Give one of those parts a shape that does not lead back — `text`, or a \
                     shape of its own."
                        .to_string(),
                ));
            }
        }
    }

    fn circle_from(&self, path: &mut Vec<&'a str>) -> Option<Vec<&'a str>> {
        let here = *path.last()?;
        for (_, line) in self.parts_of(here).unwrap_or_default() {
            let Some(next) = named_in(&line.shape) else {
                continue;
            };
            let Some(next) = self.named.iter().copied().find(|n| *n == next) else {
                continue;
            };
            if next == path[0] {
                return Some(path.clone());
            }
            if path.contains(&next) {
                continue;
            }
            path.push(next);
            if let Some(found) = self.circle_from(path) {
                return Some(found);
            }
            path.pop();
        }
        None
    }
}

/// The named shape a line is built on, if any.
fn named_in(shape: &Shape) -> Option<&str> {
    match shape {
        Shape::Named(n) => Some(n),
        Shape::ListOf(inner) => named_in(inner),
        _ => None,
    }
}

// ─────────────────────────────────────────────────────────────────── memory

/// `comes-from:`, `combines-by:` and `lasts: one-run` are read only on a
/// repeat's `remembers:`, and `kept-per:` only where a run has an `input`.
fn memory_lines(document: &Node, diags: &mut Diagnostics) {
    let mut holders: Vec<(String, &Node, bool)> = Vec::new();
    if let Some(m) = document.get("remembers") {
        holders.push(("the workspace".to_string(), m, true));
    }
    for (kind, collection, has_input) in [
        ("workflow", "workflows", true),
        ("agent", "agents", false),
        ("port", "ports", false),
    ] {
        for (name, entry) in document
            .get(collection)
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            if let Some(m) = entry.node.get("remembers") {
                holders.push((format!("the {kind} '{name}'"), m, has_input));
            }
        }
    }
    for (who, remembers, has_input) in holders {
        for (fact, entry) in remembers.as_map().into_iter().flatten() {
            let Some(lines) = entry.node.as_map() else {
                continue;
            };
            for key in ["comes-from", "combines-by"] {
                if let Some(line) = lines.get(key) {
                    diags.push(Diagnostic::error(
                        "loader/a-line-this-stage-never-reads",
                        line.key_span.clone(),
                        format!(
                            "'{fact}', which {who} remembers, writes `{key}:`, and only a \
                             repeat's `remembers:` reads it, at the end of each round — so \
                             nothing ever reads this line."
                        ),
                        "Delete it, or remember this under the `remembers:` of the `repeat` whose \
                         rounds carry it."
                            .to_string(),
                    ));
                }
            }
            if let Some(lasts) = lines.get("lasts")
                && lasts.node.as_str().map(str::trim) == Some("one-run")
            {
                diags.push(Diagnostic::error(
                    "loader/a-line-this-stage-never-reads",
                    lasts.node.span.clone(),
                    format!(
                        "'{fact}', which {who} remembers, lasts `one-run`: a value a repeat \
                         carries between its rounds, and only a repeat's `remembers:` has rounds."
                    ),
                    "Write how long it lasts here — `one-conversation` or `forever` — or \
                     remember it under the repeat's `remembers:`."
                        .to_string(),
                ));
            }
            if !has_input && let Some(per) = lines.get("kept-per") {
                diags.push(Diagnostic::error(
                    "loader/a-line-this-stage-never-reads",
                    per.key_span.clone(),
                    format!(
                        "'{fact}', which {who} remembers, writes `kept-per:`, which keeps one \
                         value per field of a workflow run's `input`, and {who} has no `input`."
                    ),
                    "Delete it, or keep this under a workflow's or the workspace's `remembers:`."
                        .to_string(),
                ));
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────── a flow

/// One `steps:` the walk is inside: the workflow's own, or a stage's body.
struct Frame<'a> {
    steps: &'a Map,
    /// The first stage; `None` on a `together`, where every stage starts at once.
    start: Option<&'a str>,
    /// The stage whose body this is.
    holder: Option<(&'a str, &'a Node)>,
}

impl Frame<'_> {
    fn kind(&self) -> &str {
        self.holder
            .and_then(|(_, n)| workflows::does(n))
            .unwrap_or("workflow")
    }
}

struct Flow<'a> {
    document: &'a Node,
    shapes: &'a Shapes<'a>,
    node: &'a Node,
    name: &'a str,
}

/// How a binding is read.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Reading {
    /// By the stage named, where it sits in the innermost frame.
    At,
    /// When a round ends (`until:`, `comes-from:`): every stage of the round
    /// is there to read, and an outer one is judged from the repeat.
    RoundEnd,
    /// Somewhere a stage's position does not apply (a workflow's `hides:`, a
    /// question's `shows:`, a moment's `at:`): only that it names something.
    NamesOnly,
}

/// What a `bind:` key fills on its target.
enum Fill {
    /// The input's (or its part's) line, read, and as written.
    Line(Option<Line>, String),
    /// The target takes no input by that name.
    NotTaken,
    /// `whole` (a named shape, or a shape with no parts) has no part `part`.
    NoPart {
        whole: String,
        part: String,
        shape: String,
        parts: Vec<String>,
    },
}

/// A `bind:` key with each dotted part trimmed.
fn dotted(key: &str) -> String {
    key.split('.').map(str::trim).collect::<Vec<_>>().join(".")
}

/// What a binding fills, for the `, optional` escape and WF-39.
struct Filling<'b> {
    input: &'b str,
    line: Option<Line>,
    written: Option<String>,
    target: &'b str,
}

impl<'a> Flow<'a> {
    fn stages(&self, frames: &mut Vec<Frame<'a>>, diags: &mut Diagnostics) {
        let steps = frames.last().expect("a frame").steps;
        for (stage, entry) in steps {
            let Some(fields) = entry.node.as_map() else {
                continue;
            };
            let does = workflows::does(&entry.node).unwrap_or("");
            if does == "call" {
                self.call(frames, stage, fields, diags);
            }
            if let Some(over) = fields.get("over") {
                self.read(frames, stage, &over.node, None, Reading::At, diags);
            }
            let mut found = Vec::new();
            for (key, e) in fields {
                match key.as_str() {
                    "bind" | "steps" => {}
                    "at" | "in-time-zone" => found.push(&e.node),
                    _ => moments(&e.node, &mut found),
                }
            }
            for n in found
                .into_iter()
                .filter(|n| n.as_str().is_some_and(is_binding))
            {
                self.read(frames, stage, n, None, Reading::NamesOnly, diags);
            }
            let Some(body) = fields.get("steps").and_then(|e| e.node.as_map()) else {
                continue;
            };
            frames.push(Frame {
                steps: body,
                start: if does == "together" {
                    None
                } else {
                    fields
                        .get("starts-at")
                        .and_then(|e| e.node.as_str())
                        .map(str::trim)
                },
                holder: Some((stage.as_str(), &entry.node)),
            });
            if does == "repeat" {
                self.repeat(frames, stage, fields, body, diags);
            }
            self.stages(frames, diags);
            frames.pop();
        }
    }

    /// A `call` stage: what it calls (WF-9), what it binds (WF-4 to WF-7 for
    /// each value), and whether the binding fits the target (WF-39).
    fn call(&self, frames: &[Frame<'a>], stage: &str, fields: &Map, diags: &mut Diagnostics) {
        let call = fields.get("call");
        let said = call.and_then(|c| c.node.as_str()).map(str::trim);
        if let (Some(call), Some(said)) = (call, said)
            && is_binding(said)
        {
            if !fields.contains_key("may-call") {
                diags.push(Diagnostic::error(
                    "loader/a-target-picked-from-nowhere",
                    call.node.span.clone(),
                    format!(
                        "'{stage}' calls whatever '{said}' turns out to be, and nothing lists \
                         what that may be, so a value nobody approved would choose what runs."
                    ),
                    "List every target it may be under `may-call:` — `may-call: [<one>, \
                     <another>]`."
                        .to_string(),
                ));
            }
            self.read(frames, stage, &call.node, None, Reading::At, diags);
        }
        if let Some(version) = fields.get("version")
            && version.node.as_str().is_some_and(is_binding)
        {
            self.read(frames, stage, &version.node, None, Reading::At, diags);
        }
        let target = said.filter(|s| !is_binding(s));
        let inputs = target.and_then(|t| self.inputs_of(t));
        let bind = fields.get("bind").and_then(|e| e.node.as_map());
        for (key, value) in bind.into_iter().flatten() {
            let line = match inputs.as_ref().map(|i| self.fill_of(i, key)) {
                Some(Fill::Line(l, w)) => Some((l, w)),
                _ => None,
            };
            let filling = target.map(|t| Filling {
                input: key.trim(),
                line: line.as_ref().and_then(|(l, _)| l.clone()),
                written: line.as_ref().map(|(_, w)| w.clone()),
                target: t,
            });
            self.read(
                frames,
                stage,
                &value.node,
                filling.as_ref(),
                Reading::At,
                diags,
            );
        }
        if let (Some(target), Some(inputs)) = (target, inputs) {
            self.fits(frames, stage, target, &inputs, call, bind, diags);
        }
    }

    /// WF-39: a call's `bind:` against what its target takes.
    #[allow(clippy::too_many_arguments)]
    fn fits(
        &self,
        frames: &[Frame<'a>],
        stage: &str,
        target: &str,
        inputs: &[(String, Option<Line>, String)],
        call: Option<&Entry>,
        bind: Option<&Map>,
        diags: &mut Diagnostics,
    ) {
        let bound: BTreeSet<String> = bind.into_iter().flatten().map(|(k, _)| dotted(k)).collect();
        let names: Vec<&str> = inputs.iter().map(|(k, _, _)| k.as_str()).collect();
        for (key, entry) in bind.into_iter().flatten() {
            let input = key.split('.').next().unwrap_or(key).trim();
            let at = key_span(bind, key).unwrap_or_else(|| entry.node.span.clone());
            let key = dotted(key);
            let (line, written) = match self.fill_of(inputs, &key) {
                Fill::Line(line, written) => (line, written),
                Fill::NotTaken => {
                    diags.push(Diagnostic::error(
                        "loader/a-call-that-does-not-fit",
                        at,
                        format!(
                            "'{stage}' fills `{input}:` of '{target}', and '{target}' takes no \
                             input by that name."
                        ),
                        if names.is_empty() {
                            format!("Delete it: '{target}' takes no inputs.")
                        } else {
                            format!(
                                "Change it to one of: {} — or delete it.",
                                offered(input, &names)
                            )
                        },
                    ));
                    continue;
                }
                Fill::NoPart {
                    whole,
                    part,
                    shape,
                    parts,
                } => {
                    let parts: Vec<&str> = parts.iter().map(String::as_str).collect();
                    diags.push(Diagnostic::error(
                        "loader/a-call-that-does-not-fit",
                        at,
                        if parts.is_empty() {
                            format!(
                                "'{stage}' fills `{key}:` of '{target}', and `{whole}` is \
                                 `{shape}`, which has no parts."
                            )
                        } else {
                            format!(
                                "'{stage}' fills `{key}:` of '{target}', and `{whole}` is the \
                                 shape '{shape}', which has no part '{part}'."
                            )
                        },
                        if parts.is_empty() {
                            format!("Fill `{whole}:` whole — `{whole}: <binding>`.")
                        } else {
                            format!(
                                "Change it to one of: {} — or delete it.",
                                suggest::nearest(&part, &parts, 3)
                                    .iter()
                                    .map(|p| format!("`{whole}.{p}`"))
                                    .collect::<Vec<_>>()
                                    .join(", ")
                            )
                        },
                    ));
                    continue;
                }
            };
            let (Some(want), Some((have, have_written))) =
                (line, self.shape_of(frames, &entry.node))
            else {
                continue;
            };
            let input = key.as_str();
            if self.shapes.fits(&have.shape, &want.shape) {
                continue;
            }
            let read = entry.node.as_str().unwrap_or("").trim();
            diags.push(Diagnostic::error(
                "loader/a-call-that-does-not-fit",
                entry.node.span.clone(),
                format!(
                    "'{stage}' fills `{input}:` of '{target}' from '{read}', which is \
                     `{have_written}`, and '{target}' takes `{written}` there, so the value \
                     could not be read as what it is given for."
                ),
                format!(
                    "Bind a value that is `{}` here, or change what '{target}' takes.",
                    want.shape.written()
                ),
            ));
        }
        let empty: Vec<String> = inputs
            .iter()
            .flat_map(|(k, line, _)| self.unfilled(k.clone(), line.as_ref(), &bound))
            .collect();
        if empty.is_empty() {
            return;
        }
        let Some(at) = call.map(|c| c.node.span.clone()) else {
            return;
        };
        let listed = empty
            .iter()
            .map(|k| format!("'{k}'"))
            .collect::<Vec<_>>()
            .join(", ");
        let accepts = self.node.get("accepts").and_then(Node::as_map);
        let example = empty
            .iter()
            .map(|k| {
                if accepts.is_some_and(|a| a.contains_key(k.as_str())) {
                    format!("`{k}: input.{k}`")
                } else {
                    format!("`{k}: <binding>`")
                }
            })
            .collect::<Vec<_>>()
            .join(", ");
        diags.push(Diagnostic::error(
            "loader/a-call-that-does-not-fit",
            at,
            format!(
                "'{stage}' calls '{target}' and leaves {} {listed} empty, so '{target}' would \
                 run without {}.",
                if empty.len() == 1 {
                    "its input"
                } else {
                    "its inputs"
                },
                if empty.len() == 1 { "it" } else { "them" },
            ),
            format!(
                "Fill {} under `bind:` — {example} — or, if '{target}' can do without {}, mark \
                 {} `, optional` there.",
                if empty.len() == 1 { "it" } else { "each" },
                if empty.len() == 1 { "it" } else { "one" },
                if empty.len() == 1 { "it" } else { "that one" },
            ),
        ));
    }

    /// A `repeat`: what it remembers comes from inside the round (WF-13), and
    /// its `until:` reads something the round writes (WF-14).
    fn repeat(
        &self,
        frames: &[Frame<'a>],
        stage: &str,
        fields: &'a Map,
        body: &'a Map,
        diags: &mut Diagnostics,
    ) {
        let remembered = fields.get("remembers").and_then(|e| e.node.as_map());
        for (name, entry) in remembered.into_iter().flatten() {
            let Some(from) = entry.node.as_map().and_then(|m| m.get("comes-from")) else {
                diags.push(Diagnostic::error(
                    "loader/remembered-from-nowhere",
                    entry.key_span.clone(),
                    format!(
                        "'{stage}' remembers '{name}' between rounds and does not say where it \
                         comes from, so nothing is ever added to it."
                    ),
                    format!(
                        "Point `comes-from:` at a stage inside the round — `comes-from: \
                         steps.{}.<field>`.",
                        first_stage(fields, body)
                    ),
                ));
                continue;
            };
            let said = from.node.as_str().unwrap_or("").trim();
            let inside = said
                .strip_prefix("steps.")
                .and_then(|r| r.split('.').next())
                .is_some_and(|s| holds(body, s));
            if !inside {
                diags.push(Diagnostic::error(
                    "loader/remembered-from-nowhere",
                    from.node.span.clone(),
                    format!(
                        "'{stage}' remembers '{name}' from '{said}', which is not a stage inside \
                         the round, so the value would be the same every round."
                    ),
                    format!(
                        "Point `comes-from:` at a stage inside the round — `comes-from: \
                         steps.{}.<field>`.",
                        first_stage(fields, body)
                    ),
                ));
                continue;
            }
            self.read(frames, stage, &from.node, None, Reading::RoundEnd, diags);
        }
        let Some(until) = fields.get("until") else {
            return;
        };
        let values = values_in(&until.node);
        let mut changes = false;
        let hears = hears_in(body);
        for value in values.iter().copied() {
            self.read(frames, stage, value, None, Reading::RoundEnd, diags);
            let said = value.as_str().unwrap_or("").trim();
            let (root, rest) = said.split_once('.').unwrap_or((said, ""));
            let first = rest.split('.').next().unwrap_or("");
            changes |= match root {
                "steps" => holds(body, first),
                "remembers" => remembered.is_some_and(|m| m.contains_key(first)),
                "latest-update" => hears,
                _ => false,
            };
        }
        // An `until:` of `tool:` lines only asks a tool each round, which may
        // answer differently; WF-14 reads what a line's `value:` names.
        if !changes && !values.is_empty() {
            diags.push(Diagnostic::error(
                "loader/until-that-cannot-change",
                until.key_span.clone(),
                format!(
                    "'{stage}' repeats until something holds, and its `until:` reads nothing the \
                     round writes — no stage inside it, nothing it remembers, no event it hears \
                     — so what it reads is the same after every round."
                ),
                format!(
                    "Read a stage inside the round or a remembered value — `value: \
                     steps.{}.<field>` or `value: remembers.<name>`.",
                    first_stage(fields, body)
                ),
            ));
        }
    }

    /// The names-only pass over the lines of a workflow that are not a
    /// stage's `bind:`, `over:`, `call:` or `until:`.
    fn anywhere(&self, node: &'a Node, diags: &mut Diagnostics) {
        let mut found: Vec<&'a Node> = Vec::new();
        for (key, entry) in node.as_map().into_iter().flatten() {
            match key.as_str() {
                "hides" => {
                    for (written, e) in entry.node.as_map().into_iter().flatten() {
                        if is_binding(written) {
                            self.names(written, &e.key_span, diags);
                        }
                    }
                }
                "data-stays-in" => found.push(&entry.node),
                "questions" => {
                    for (_, q) in entry.node.as_map().into_iter().flatten() {
                        if let Some(shows) = q.node.get("shows") {
                            found.extend(workflows::list(shows));
                        }
                        moments(&q.node, &mut found);
                    }
                }
                // A stage's moments are read by the stage walk, as the stage's.
                "steps" => {}
                _ => moments(&entry.node, &mut found),
            }
        }
        for n in found {
            if let Some(written) = n.as_str().filter(|s| is_binding(s)) {
                self.names(written, &n.span, diags);
            }
        }
    }

    /// WF-4 alone, for a line no stage's position belongs to.
    fn names(&self, written: &str, at: &Span, diags: &mut Diagnostics) {
        let node = Node::new(Value::Str(written.to_string()), at.clone());
        self.read(&[], "", &node, None, Reading::NamesOnly, diags);
    }

    // ────────────────────────────────────────────────────────── one binding

    /// Every rule a binding answers to, for the binding in `node`, read by
    /// `stage` in the innermost of `frames`.
    fn read(
        &self,
        frames: &[Frame<'a>],
        stage: &str,
        node: &Node,
        filling: Option<&Filling>,
        reading: Reading,
        diags: &mut Diagnostics,
    ) {
        let Some(written) = node.as_str().map(str::trim) else {
            return;
        };
        let mut path = written.split('.').map(str::trim);
        let root = path.next().unwrap_or("");
        let rest: Vec<&str> = path.collect();
        let first = rest.first().copied();
        let who = if stage.is_empty() {
            format!("The workflow '{}'", self.name)
        } else {
            format!("'{stage}'")
        };
        let nothing = |why: String, fix: String| {
            Diagnostic::error(
                "loader/a-binding-to-nothing",
                node.span.clone(),
                format!("{who} reads '{written}', and {why}."),
                fix,
            )
        };
        match root {
            "input" => {
                let Some(field) = first else { return };
                let accepts = self.node.get("accepts").and_then(Node::as_map);
                match accepts.and_then(|a| a.get(field)) {
                    Some(entry) => self.deeper(&who, written, &entry.node, &rest[1..], node, diags),
                    None => diags.push(nothing(
                        format!("the workflow '{}' accepts no '{field}'", self.name),
                        offer_or_add(field, accepts, "input", "under the workflow's `accepts:`"),
                    )),
                }
            }
            "steps" => {
                let Some(target) = first else {
                    return diags.push(nothing(
                        "it names no stage".to_string(),
                        "Write the stage and the field — `steps.<stage>.<field>`.".to_string(),
                    ));
                };
                self.stage_read(
                    frames,
                    stage,
                    node,
                    written,
                    target,
                    &rest[1..],
                    filling,
                    reading,
                    diags,
                );
            }
            "item" => {
                let inside = frames.iter().rev().find(|f| f.kind() == "each");
                match (inside, reading) {
                    (None, Reading::At | Reading::RoundEnd) => {
                        diags.push(self.outside_each(stage, written, node))
                    }
                    (Some(each), _) => {
                        let over = each
                            .holder
                            .and_then(|(_, n)| n.get("over"))
                            .and_then(|o| self.shape_of_path(frames, o));
                        if let (
                            Some(field),
                            Some(Line {
                                shape: Shape::ListOf(inner),
                                ..
                            }),
                        ) = (first, over)
                            && let Shape::Named(name) = inner.as_ref()
                        {
                            self.part(&who, written, name, field, &rest[1..], node, diags);
                        }
                    }
                    _ => {}
                }
            }
            "remembers" => {
                let Some(name) = first else { return };
                let mut known: Vec<&str> = Vec::new();
                for holder in [self.document, self.node] {
                    if let Some(m) = holder.get("remembers").and_then(Node::as_map) {
                        known.extend(m.keys().map(String::as_str));
                    }
                }
                let repeats: Vec<&Node> = if reading == Reading::NamesOnly {
                    every_stage(self.node)
                } else {
                    frames
                        .iter()
                        .filter_map(|f| f.holder.map(|(_, n)| n))
                        .collect()
                };
                for n in repeats {
                    if let Some(m) = n.get("remembers").and_then(Node::as_map) {
                        known.extend(m.keys().map(String::as_str));
                    }
                }
                if !known.contains(&name) {
                    diags.push(nothing(
                        format!("nothing here remembers '{name}'"),
                        if known.is_empty() {
                            format!(
                                "Add `{name}:` under `remembers:` — the workflow's, the \
                                 workspace's, or a repeat's."
                            )
                        } else {
                            format!(
                                "Use one of the names offered: {}.",
                                offered_as("remembers", name, &known)
                            )
                        },
                    ));
                }
            }
            "run-inputs" => {
                if let Some(name) = first
                    && !HOST_INPUTS.contains(&name)
                {
                    diags.push(nothing(
                        format!(
                            "a workflow's host supplies only {}",
                            HOST_INPUTS
                                .iter()
                                .map(|h| format!("`run-inputs.{h}`"))
                                .collect::<Vec<_>>()
                                .join(" and ")
                        ),
                        format!(
                            "Use one of the names offered: {}.",
                            offered_as("run-inputs", name, HOST_INPUTS)
                        ),
                    ));
                }
            }
            "used" if reading != Reading::RoundEnd => diags.push(nothing(
                "`used.` is read only in a condition, where a limit's share is compared"
                    .to_string(),
                "Move it into an `until:` line, or read another value here.".to_string(),
            )),
            "latest-update" | "values" | "used" => {}
            _ => diags.push(nothing(
                format!("'{root}' is not where a binding starts"),
                format!(
                    "Start it with one of the names offered: {} — the others are {}.",
                    suggest::nearest(root, ROOTS, 3)
                        .iter()
                        .map(|r| format!("`{r}.`"))
                        .collect::<Vec<_>>()
                        .join(", "),
                    ROOTS
                        .iter()
                        .filter(|r| !suggest::nearest(root, ROOTS, 3).contains(r))
                        .map(|r| format!("`{r}.`"))
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            )),
        }
    }

    fn outside_each(&self, stage: &str, written: &str, node: &Node) -> Diagnostic {
        let each = every_stage_named(self.node)
            .into_iter()
            .find(|(_, n)| workflows::does(n) == Some("each"))
            .map(|(name, _)| name);
        Diagnostic::error(
            "loader/an-item-outside-for-each",
            node.span.clone(),
            format!(
                "'{stage}' reads '{written}', and '{stage}' is not inside an `each`, so there \
                 is no current item."
            ),
            format!(
                "Move the stage inside the `each`, or read `steps.{}.<field>`.",
                each.unwrap_or("<each>")
            ),
        )
    }

    /// `steps.<target>.<rest>`, read by `stage`.
    #[allow(clippy::too_many_arguments)]
    fn stage_read(
        &self,
        frames: &[Frame<'a>],
        stage: &str,
        node: &Node,
        written: &str,
        target: &str,
        rest: &[&str],
        filling: Option<&Filling>,
        reading: Reading,
        diags: &mut Diagnostics,
    ) {
        let who = if stage.is_empty() {
            format!("The workflow '{}'", self.name)
        } else {
            format!("'{stage}'")
        };
        let found = if reading == Reading::NamesOnly {
            every_stage_named(self.node)
                .into_iter()
                .find(|(n, _)| *n == target)
                .map(|(_, n)| (usize::MAX, n))
        } else {
            frames
                .iter()
                .enumerate()
                .rev()
                .find_map(|(i, f)| f.steps.get(target).map(|e| (i, &e.node)))
        };
        let Some((depth, target_node)) = found else {
            let elsewhere = every_stage_named(self.node)
                .into_iter()
                .find(|(n, _)| *n == target)
                .map(|(_, _)| holder_of(self.node, target));
            let d = match elsewhere {
                Some(Some(holder)) => Diagnostic::error(
                    "loader/a-binding-to-nothing",
                    node.span.clone(),
                    format!(
                        "{who} reads '{written}', and '{target}' is inside '{holder}': a stage \
                         inside an `each`, a `repeat` or a `together` is read only inside it."
                    ),
                    format!(
                        "Read what '{holder}' combined or remembered — `steps.{holder}.<field>` \
                         — or move {who} inside '{holder}'."
                    ),
                ),
                _ => {
                    let visible: Vec<&str> = frames
                        .iter()
                        .flat_map(|f| f.steps.keys().map(String::as_str))
                        .chain(if reading == Reading::NamesOnly {
                            every_stage_named(self.node)
                                .into_iter()
                                .map(|(n, _)| n)
                                .collect::<Vec<_>>()
                        } else {
                            Vec::new()
                        })
                        .collect();
                    Diagnostic::error(
                        "loader/a-binding-to-nothing",
                        node.span.clone(),
                        format!(
                            "{who} reads '{written}', and this workflow has no stage called \
                             '{target}' there."
                        ),
                        format!(
                            "Use one of the names offered: {}.",
                            offered_as("steps", target, &visible)
                        ),
                    )
                }
            };
            return diags.push(d);
        };
        if let Some(field) = rest.first().copied()
            && !STAGE_FIELDS.contains(&field)
            && let Some(answers) = self.answer_of(target_node)
        {
            match answers.iter().find(|(k, _)| k == field) {
                None => {
                    let names: Vec<&str> = answers
                        .iter()
                        .map(|(k, _)| k.as_str())
                        .chain(STAGE_FIELDS.iter().copied())
                        .collect();
                    return diags.push(Diagnostic::error(
                        "loader/a-binding-to-nothing",
                        node.span.clone(),
                        format!(
                            "{who} reads '{written}', and '{target}' answers with no '{field}'."
                        ),
                        format!(
                            "Use one of the names offered: {}.",
                            offered_as(&format!("steps.{target}"), field, &names)
                        ),
                    ));
                }
                Some((
                    _,
                    Some(Line {
                        shape: Shape::Named(name),
                        ..
                    }),
                )) => {
                    self.part(
                        &who,
                        written,
                        name,
                        rest.get(1).copied().unwrap_or(""),
                        &rest[2.min(rest.len())..],
                        node,
                        diags,
                    );
                }
                _ => {}
            }
        }
        if reading == Reading::NamesOnly {
            return;
        }
        // Where the reader sits in the frame that holds the target.
        let innermost = frames.len() - 1;
        let frame = &frames[depth];
        if depth == innermost && reading == Reading::RoundEnd {
            return self.at_round_end(frame, &who, written, target, node, diags);
        }
        let here: Option<&str> = if depth == innermost {
            Some(stage)
        } else {
            frames[depth + 1].holder.map(|(n, _)| n)
        };
        let Some(here) = here else { return };
        let in_round = frame.kind() == "repeat";
        let later = |extra: String| {
            Diagnostic::error(
                "loader/a-binding-from-later",
                node.span.clone(),
                format!(
                    "{who} reads '{written}', and '{target}' runs after it{extra}, so there is \
                     nothing there yet."
                ),
                if in_round {
                    format!(
                        "Name it under the repeat's `remembers:` with `comes-from: {written}`, and \
                         read `remembers.<name>` here."
                    )
                } else {
                    format!("Read it from a stage that runs before '{here}'.")
                },
            )
        };
        if target == here {
            let extra = if depth == innermost {
                String::new()
            } else {
                format!(": it ends only when everything inside '{here}' has")
            };
            return diags.push(later(extra));
        }
        let optional = filling.is_some_and(|f| f.line.as_ref().is_some_and(|l| l.optional));
        if frame.start.is_none() {
            if optional {
                return;
            }
            let holder = frame.holder.map_or("", |(n, _)| n);
            return diags.push(Diagnostic::error(
                "loader/a-binding-to-a-stage-that-may-not-have-run",
                node.span.clone(),
                format!(
                    "{who} reads '{written}', but '{target}' runs side by side with '{here}' in \
                     '{holder}', so it may not have finished."
                ),
                self.optional_fix(filling, "read it from a stage before"),
            ));
        }
        let graph = Graph::of(frame);
        let Some(around) = graph.path_avoiding(here, target) else {
            return;
        };
        if graph.reaches(here, target) && !graph.reaches(target, here) {
            let extra = if in_round {
                format!(
                    ", later in the round of '{}'",
                    frame.holder.map_or("", |(n, _)| n)
                )
            } else {
                String::new()
            };
            return diags.push(later(extra));
        }
        if around.is_empty() {
            // `here` is the first stage and `target` comes round to it again:
            // the first time `here` runs, nothing has.
            return diags.push(later(format!(
                ": '{here}' is the first stage, so the first time it runs '{target}' has not"
            )));
        }
        if optional {
            return;
        }
        let through = graph.through(&around, target);
        diags.push(Diagnostic::error(
            "loader/a-binding-to-a-stage-that-may-not-have-run",
            node.span.clone(),
            format!(
                "{who} reads '{written}', but on the path through '{through}' the stage \
                 '{target}' never runs."
            ),
            self.optional_fix(filling, "read it from a stage every path passes"),
        ));
    }

    /// WF-5 when a round ends (`until:`, `comes-from:`): every way a round can
    /// end must have passed `target`. `comes-from:` and `until:` fill no input,
    /// so there is no `, optional` escape.
    fn at_round_end(
        &self,
        frame: &Frame<'a>,
        who: &str,
        written: &str,
        target: &str,
        node: &Node,
        diags: &mut Diagnostics,
    ) {
        if frame.start.is_none() {
            return;
        }
        let graph = Graph::of(frame);
        let Some(around) = graph.path_avoiding(END, target) else {
            return;
        };
        let through = graph.through(&around, target);
        diags.push(Diagnostic::error(
            "loader/a-binding-to-a-stage-that-may-not-have-run",
            node.span.clone(),
            format!(
                "{who} reads '{written}' when a round ends, but a round can end on the path \
                 through '{through}' without running '{target}'."
            ),
            format!(
                "Read it from a stage every round passes, or send the path through '{through}' \
                 by '{target}' before the round ends."
            ),
        ));
    }

    fn optional_fix(&self, filling: Option<&Filling>, otherwise: &str) -> String {
        match filling {
            Some(f) => {
                let shape = f
                    .written
                    .as_deref()
                    .map(|w| w.trim().to_string())
                    .unwrap_or_else(|| "text".to_string());
                format!(
                    "Mark that input `{}: {shape}, optional` on '{}', or {otherwise}.",
                    f.input, f.target
                )
            }
            None => {
                let mut s = otherwise.to_string();
                if let Some(first) = s.get_mut(0..1) {
                    first.make_ascii_uppercase();
                }
                format!("{s}.")
            }
        }
    }

    /// The part `field` of the named shape `name`, and deeper.
    #[allow(clippy::too_many_arguments)]
    fn part(
        &self,
        who: &str,
        written: &str,
        name: &str,
        field: &str,
        rest: &[&str],
        node: &Node,
        diags: &mut Diagnostics,
    ) {
        if field.is_empty() {
            return;
        }
        let Some(parts) = self.shapes.parts.get(name) else {
            return;
        };
        match parts.get(field) {
            Some(entry) => self.deeper(who, written, &entry.node, rest, node, diags),
            None => diags.push(Diagnostic::error(
                "loader/a-binding-to-nothing",
                node.span.clone(),
                format!("{who} reads '{written}', and the shape '{name}' has no part '{field}'."),
                format!(
                    "Use one of the names offered: {}.",
                    suggest::nearest(
                        field,
                        &parts.keys().map(String::as_str).collect::<Vec<_>>(),
                        3
                    )
                    .iter()
                    .map(|p| format!("`{p}`"))
                    .collect::<Vec<_>>()
                    .join(", ")
                ),
            )),
        }
    }

    /// Past a field whose line is `line`: its parts, when it is a named shape.
    fn deeper(
        &self,
        who: &str,
        written: &str,
        line: &Node,
        rest: &[&str],
        node: &Node,
        diags: &mut Diagnostics,
    ) {
        let Some(field) = rest.first() else { return };
        if let Some(Line {
            shape: Shape::Named(name),
            ..
        }) = self.shapes.line(line)
        {
            self.part(who, written, &name, field, &rest[1..], node, diags);
        }
    }

    // ───────────────────────────────────────────────────── what things hold

    /// The line a `bind:` key fills: an input's, or, written with dots
    /// (`fills.first-name`, 02W §2.3), a part of its named shape.
    fn fill_of(&self, inputs: &[(String, Option<Line>, String)], key: &str) -> Fill {
        let mut path = key.split('.').map(str::trim);
        let input = path.next().unwrap_or("");
        let Some((_, line, written)) = inputs.iter().find(|(k, _, _)| k == input) else {
            return Fill::NotTaken;
        };
        let (mut line, mut written, mut whole) = (line.clone(), written.clone(), input.to_string());
        for part in path {
            let Some(l) = &line else {
                return Fill::Line(None, String::new());
            };
            let Shape::Named(name) = &l.shape else {
                return Fill::NoPart {
                    whole,
                    part: part.to_string(),
                    shape: l.shape.written(),
                    parts: Vec::new(),
                };
            };
            let Some(parts) = self.shapes.parts.get(name.as_str()) else {
                return Fill::Line(None, String::new());
            };
            let Some(entry) = parts.get(part) else {
                return Fill::NoPart {
                    whole,
                    part: part.to_string(),
                    shape: name.clone(),
                    parts: parts.keys().cloned().collect(),
                };
            };
            line = self.shapes.line(&entry.node);
            written = entry.node.as_str().unwrap_or("").to_string();
            whole = format!("{whole}.{part}");
        }
        Fill::Line(line, written)
    }

    /// What of `path` (an input, or a part of one) `bound` leaves empty: the
    /// path itself, or, when keys with dots fill some of its parts, each
    /// required part they leave out.
    fn unfilled(&self, path: String, line: Option<&Line>, bound: &BTreeSet<String>) -> Vec<String> {
        if bound.contains(&path) || line.is_some_and(|l| l.optional) {
            return Vec::new();
        }
        let below = format!("{path}.");
        if !bound.iter().any(|k| k.starts_with(&below)) {
            return vec![path];
        }
        let Some(Line {
            shape: Shape::Named(name),
            ..
        }) = line
        else {
            return Vec::new();
        };
        self.shapes
            .parts_of(name)
            .unwrap_or_default()
            .iter()
            .flat_map(|(part, l)| self.unfilled(format!("{path}.{part}"), Some(l), bound))
            .collect()
    }

    /// What a call target takes, each line read: `(input, its line, as written)`.
    /// `None` when the target says nothing about what it takes.
    fn inputs_of(&self, target: &str) -> Option<Vec<(String, Option<Line>, String)>> {
        let (map, bound): (&Map, BTreeSet<&str>) = match workflows::resolve(self.document, target) {
            Resolved::One(Kind::Action) => {
                let (tool, action) = target.split_once('/')?;
                let a = workflows::entry_in(self.document, "tools", tool)?
                    .get("actions")?
                    .get(action)?;
                let bound = a
                    .get("bind")
                    .and_then(Node::as_map)
                    .map(|m| m.keys().map(String::as_str).collect())
                    .unwrap_or_default();
                (a.get("takes")?.as_map()?, bound)
            }
            Resolved::One(kind @ (Kind::Agent | Kind::Workflow)) => (
                workflows::entry_in(self.document, kind.collection(), target)?
                    .get("accepts")?
                    .as_map()?,
                BTreeSet::new(),
            ),
            Resolved::One(Kind::Program) => (
                workflows::entry_in(self.document, "programs", target)?
                    .get("takes")?
                    .as_map()?,
                BTreeSet::new(),
            ),
            _ => return None,
        };
        Some(
            map.iter()
                .filter(|(k, _)| !bound.contains(k.as_str()))
                .map(|(k, e)| {
                    (
                        k.clone(),
                        self.shapes.line(&e.node),
                        e.node.as_str().unwrap_or("").to_string(),
                    )
                })
                .collect(),
        )
    }

    /// What a stage answers with, by field: `None` when that cannot be known
    /// here (a call to a binding, an agent answering in words, an `each`).
    fn answer_of(&self, stage: &Node) -> Option<Vec<(String, Option<Line>)>> {
        let read = |m: &Map| {
            m.iter()
                .map(|(k, e)| (k.clone(), self.shapes.line(&e.node)))
                .collect()
        };
        match workflows::does(stage)? {
            "call" => {
                let target = stage.get("call")?.as_str()?.trim();
                let answers = match workflows::resolve(self.document, target) {
                    Resolved::One(Kind::Action) => {
                        let (tool, action) = target.split_once('/')?;
                        workflows::entry_in(self.document, "tools", tool)?
                            .get("actions")?
                            .get(action)?
                            .get("answers-with")?
                    }
                    Resolved::One(kind) => {
                        workflows::entry_in(self.document, kind.collection(), target)?
                            .get("answers-with")?
                    }
                    _ => return None,
                };
                Some(read(answers.as_map()?))
            }
            "ask-someone" => {
                let asks = stage.get("asks")?.as_str()?.trim();
                let q = self
                    .node
                    .get("questions")
                    .and_then(|q| q.get(asks))
                    .or_else(|| self.document.get("questions").and_then(|q| q.get(asks)))?;
                Some(read(q.get("answer")?.as_map()?))
            }
            "repeat" => Some(
                stage
                    .get("remembers")
                    .and_then(Node::as_map)
                    .map(|m| m.keys().map(|k| (k.clone(), None)).collect())
                    .unwrap_or_default(),
            ),
            "decide" => Some(Vec::new()),
            _ => None,
        }
    }

    /// The shape of the value a binding reads, with the line as written, when
    /// that is known here.
    fn shape_of(&self, frames: &[Frame<'a>], node: &Node) -> Option<(Line, String)> {
        let line = self.shape_of_path(frames, node)?;
        let written = line.shape.written();
        Some((line, written))
    }

    fn shape_of_path(&self, frames: &[Frame<'a>], node: &Node) -> Option<Line> {
        let written = node.as_str()?.trim();
        let mut path = written.split('.').map(str::trim);
        let root = path.next()?;
        let rest: Vec<&str> = path.collect();
        let (mut line, rest) = match root {
            "input" => {
                let field = rest.first()?;
                (
                    self.shapes.line(self.node.get("accepts")?.get(field)?)?,
                    &rest[1..],
                )
            }
            "steps" => {
                let (target, field) = (rest.first()?, rest.get(1)?);
                let stage = frames.iter().rev().find_map(|f| f.steps.get(*target))?;
                let answers = self.answer_of(&stage.node)?;
                (
                    answers.into_iter().find(|(k, _)| k == field)?.1?,
                    &rest[2..],
                )
            }
            _ => return None,
        };
        for field in rest {
            let Shape::Named(name) = &line.shape else {
                return None;
            };
            let (_, next) = self
                .shapes
                .parts_of(name)?
                .into_iter()
                .find(|(k, _)| k == field)?;
            line = next;
        }
        Some(line)
    }
}

// ─────────────────────────────────────────────────────────────────── graphs

/// Where a run of a `steps:` leaves it: an outcome to `done`, to nothing, or
/// past the block. No stage can be called this (a stage's name is a word).
const END: &str = "\u{0}end";

/// One `steps:` as a graph: each stage, where it can go next, and by which
/// word. A stage that can leave the block has an edge to [`END`].
struct Graph<'a> {
    starts: Vec<&'a str>,
    next: BTreeMap<&'a str, Vec<(&'a str, &'a str)>>,
    decides: BTreeSet<&'a str>,
}

impl<'a> Graph<'a> {
    fn of(frame: &Frame<'a>) -> Self {
        let mut next = BTreeMap::new();
        let mut decides = BTreeSet::new();
        for (name, entry) in frame.steps {
            if workflows::does(&entry.node) == Some("decide") {
                decides.insert(name.as_str());
            }
            let all = workflows::next_stages(&entry.node, true);
            let mut to: Vec<(&str, &str)> = Vec::new();
            for (word, s) in &all {
                if frame.steps.contains_key(*s) {
                    to.push((word, s));
                } else {
                    to.push((word, END));
                }
            }
            if all.is_empty() {
                to.push(("", END));
            }
            next.insert(name.as_str(), to);
        }
        let starts = match frame.start {
            Some(s) => frame
                .steps
                .keys()
                .map(String::as_str)
                .filter(|k| *k == s)
                .collect(),
            None => frame.steps.keys().map(String::as_str).collect(),
        };
        Graph {
            starts,
            next,
            decides,
        }
    }

    fn reaches(&self, from: &str, to: &str) -> bool {
        let mut seen: BTreeSet<&str> = BTreeSet::new();
        let mut queue: VecDeque<&str> = self
            .next
            .get(from)
            .into_iter()
            .flatten()
            .map(|(_, s)| *s)
            .collect();
        while let Some(here) = queue.pop_front() {
            if here == to {
                return true;
            }
            if seen.insert(here) {
                queue.extend(self.next.get(here).into_iter().flatten().map(|(_, s)| *s));
            }
        }
        false
    }

    /// A path from the start to `to` that never passes `avoid`, as the edges
    /// it takes (`from`, word, `to`); `None` when every path passes it.
    fn path_avoiding(&self, to: &str, avoid: &str) -> Option<Vec<(&'a str, &'a str, &'a str)>> {
        let mut came: BTreeMap<&str, Option<(&'a str, &'a str)>> = BTreeMap::new();
        let mut queue: VecDeque<&'a str> = VecDeque::new();
        for s in &self.starts {
            if *s != avoid {
                came.insert(s, None);
                queue.push_back(s);
            }
        }
        while let Some(here) = queue.pop_front() {
            if here == to {
                let mut path = Vec::new();
                let mut at = here;
                while let Some(Some((from, word))) = came.get(at) {
                    path.push((*from, *word, at));
                    at = from;
                }
                path.reverse();
                return Some(path);
            }
            for (word, next) in self.next.get(here).into_iter().flatten() {
                if *next != avoid && !came.contains_key(next) {
                    came.insert(next, Some((here, word)));
                    queue.push_back(next);
                }
            }
        }
        None
    }

    /// The step on `path` that leaves `missed` behind: the first edge after
    /// which `missed` can no longer be reached. A decision's label names it;
    /// any other edge, the stage it leads to.
    fn through(&self, path: &[(&'a str, &'a str, &'a str)], missed: &str) -> String {
        for (from, word, to) in path {
            if self.reaches(from, missed) && !self.reaches(to, missed) {
                return if self.decides.contains(from) || (*to == END && !word.is_empty()) {
                    (*word).to_string()
                } else if *to == END {
                    (*from).to_string()
                } else {
                    (*to).to_string()
                };
            }
        }
        path.last().map_or(String::new(), |(from, _, to)| {
            if *to == END { *from } else { *to }.to_string()
        })
    }
}

// ─────────────────────────────────────────────────────────────────── helpers

/// Whether `stage` is anywhere inside `steps` (at any depth).
fn holds(steps: &Map, stage: &str) -> bool {
    steps.iter().any(|(name, e)| {
        name == stage
            || e.node
                .get("steps")
                .and_then(Node::as_map)
                .is_some_and(|inner| holds(inner, stage))
    })
}

/// Whether some stage inside `steps` hears an event (`then.heard:`).
fn hears_in(steps: &Map) -> bool {
    steps.values().any(|e| {
        e.node.get("then").and_then(|t| t.get("heard")).is_some()
            || e.node
                .get("steps")
                .and_then(Node::as_map)
                .is_some_and(hears_in)
    })
}

/// The first stage of a body, for a fix to name.
fn first_stage<'m>(fields: &'m Map, body: &'m Map) -> &'m str {
    fields
        .get("starts-at")
        .and_then(|e| e.node.as_str())
        .map(str::trim)
        .or_else(|| body.keys().next().map(String::as_str))
        .unwrap_or("<stage>")
}

/// Every `value:` an `until:` reads, written directly or as `{value: ...}`
/// beside a comparison.
fn values_in(node: &Node) -> Vec<&Node> {
    let mut out = Vec::new();
    for entry in workflows::list(node) {
        for (key, e) in entry.as_map().into_iter().flatten() {
            if key == "value" {
                out.push(&e.node);
            } else if let Some(v) = e.node.get("value") {
                out.push(v);
            }
        }
    }
    out
}

/// Every moment's `at:` and `in-time-zone:` written as text, below `node`.
fn moments<'n>(node: &'n Node, found: &mut Vec<&'n Node>) {
    match &node.value {
        Value::Map(m) => {
            for (key, e) in m {
                if matches!(key.as_str(), "at" | "in-time-zone") && e.node.as_str().is_some() {
                    found.push(&e.node);
                } else if key != "steps" {
                    moments(&e.node, found);
                }
            }
        }
        Value::List(items) => items.iter().for_each(|i| moments(i, found)),
        _ => {}
    }
}

fn every_stage(workflow: &Node) -> Vec<&Node> {
    every_stage_named(workflow)
        .into_iter()
        .map(|(_, n)| n)
        .collect()
}

/// Every stage of a workflow, at any depth, with its name.
fn every_stage_named(workflow: &Node) -> Vec<(&str, &Node)> {
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

/// The stage whose body holds `stage` directly, if it is not a top stage.
fn holder_of<'n>(workflow: &'n Node, stage: &str) -> Option<&'n str> {
    every_stage_named(workflow)
        .into_iter()
        .find_map(|(name, n)| {
            n.get("steps")
                .and_then(Node::as_map)
                .is_some_and(|inner| inner.contains_key(stage))
                .then_some(name)
        })
}

fn key_span(bind: Option<&Map>, key: &str) -> Option<Span> {
    bind.and_then(|b| b.get(key)).map(|e| e.key_span.clone())
}

/// `` `a`, `b`, `c` ``: the nearest three of `names` to `typed`.
fn offered(typed: &str, names: &[&str]) -> String {
    suggest::nearest(typed, names, 3)
        .iter()
        .map(|n| format!("`{n}`"))
        .collect::<Vec<_>>()
        .join(", ")
}

/// The nearest three, each written as a binding under `prefix`.
fn offered_as(prefix: &str, typed: &str, names: &[&str]) -> String {
    let mut unique: Vec<&str> = names.to_vec();
    unique.sort();
    unique.dedup();
    if unique.is_empty() {
        return "nothing is declared there yet".to_string();
    }
    suggest::nearest(typed, &unique, 3)
        .iter()
        .map(|n| format!("`{prefix}.{n}`"))
        .collect::<Vec<_>>()
        .join(", ")
}

fn offer_or_add(field: &str, map: Option<&Map>, prefix: &str, place: &str) -> String {
    let names: Vec<&str> = map
        .into_iter()
        .flat_map(|m| m.keys().map(String::as_str))
        .collect();
    if names.is_empty() {
        format!("Add `{field}: text` {place}.")
    } else {
        format!(
            "Use one of the names offered: {} — or add `{field}:` {place}.",
            offered_as(prefix, field, &names)
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn schema() -> Schema {
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        pact_schema::from_doc::schema_from_yaml(SPEC, &mut d)
    }

    fn rules(text: &str) -> Vec<(&'static str, String)> {
        let doc = parse_yaml(text, camino::Utf8Path::new("bindings-test.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        check(&doc, &schema(), &mut d);
        d.items()
            .iter()
            .map(|x| (x.rule, x.message.clone()))
            .collect()
    }

    const FLOW: &str = "\
tools:
  t:
    actions:
      read:
        takes: { id: text }
        answers-with: { total: money, when: date }
      post:
        takes: { id: text, note: 'text, optional', on: date }
workflows:
  w:
    description: d
    accepts: { id: text, on: date }
    starts-at: a
    steps:
      a:
        does: call
        call: t/read
        bind: { id: input.id }
        then: { answered: pick }
      pick:
        does: decide
        chooses-between: { yes: b, no: c }
      b:
        does: call
        call: t/read
        bind: { id: input.id }
        then: { answered: c }
      c:
        does: call
        call: t/post
        bind: { id: input.id, on: steps.a.when }
";

    #[test]
    fn a_flow_whose_bindings_all_reach_what_ran_is_left_alone() {
        assert!(rules(FLOW).is_empty(), "{:?}", rules(FLOW));
    }

    #[test]
    fn a_binding_to_a_stage_off_one_path_names_that_path() {
        let found = rules(&FLOW.replace("on: steps.a.when", "on: steps.b.when"));
        assert_eq!(found.len(), 1, "{found:?}");
        assert_eq!(
            found[0].0,
            "loader/a-binding-to-a-stage-that-may-not-have-run"
        );
        assert!(
            found[0].1.contains("on the path through 'no'"),
            "{}",
            found[0].1
        );
    }

    #[test]
    fn an_optional_input_may_be_filled_from_a_stage_that_may_not_have_run() {
        let text = FLOW.replace(
            "on: steps.a.when }",
            "on: steps.a.when, note: steps.b.total }",
        );
        assert!(rules(&text).is_empty(), "{:?}", rules(&text));
    }

    #[test]
    fn a_name_that_is_nothing_offers_the_nearest() {
        let found = rules(&FLOW.replace("on: steps.a.when", "on: steps.aa.when"));
        assert_eq!(found[0].0, "loader/a-binding-to-nothing", "{found:?}");
        let found = rules(&FLOW.replace("on: steps.a.when", "on: steps.a.wen"));
        assert_eq!(found[0].0, "loader/a-binding-to-nothing", "{found:?}");
        let found = rules(&FLOW.replace("{ id: input.id, on:", "{ id: input.idd, on:"));
        assert!(found.iter().any(|(r, m)| *r == "loader/a-binding-to-nothing" && m.contains("accepts no 'idd'")), "{found:?}");
    }

    #[test]
    fn a_call_that_does_not_fit_its_target_is_refused() {
        let found = rules(&FLOW.replace(
            "bind: { id: input.id, on: steps.a.when }",
            "bind: { on: steps.a.total }",
        ));
        let fit: Vec<_> = found
            .iter()
            .filter(|(r, _)| *r == "loader/a-call-that-does-not-fit")
            .collect();
        assert_eq!(fit.len(), 2, "{found:?}");
        assert!(
            fit.iter()
                .any(|(_, m)| m.contains("leaves its input 'id' empty")),
            "{fit:?}"
        );
        assert!(
            fit.iter().any(|(_, m)| m.contains("which is `money`")),
            "{fit:?}"
        );
    }

    const ROUND: &str = "\
tools:
  t:
    actions:
      read:
        takes: { id: text }
        answers-with: { total: number }
workflows:
  w:
    description: d
    accepts: { id: text, ids: list of text }
    starts-at: r
    steps:
      r:
        does: repeat
        at-most: 3
        remembers:
          seen: { description: d, lasts: one-run, comes-from: steps.b.total }
        until: [UNTIL]
        starts-at: a
        steps:
          a:
            does: call
            call: t/read
            bind: { id: BIND }
            then: { answered: b }
          b:
            does: call
            call: t/read
            bind: { id: input.id }
";

    fn round(until: &str, bind: &str) -> Vec<(&'static str, String)> {
        rules(&ROUND.replace("UNTIL", until).replace("BIND", bind))
    }

    #[test]
    fn an_until_that_reads_the_round_or_its_memory_can_change() {
        assert!(round("{ value: steps.b.total }", "input.id").is_empty());
        assert!(round("{ value: remembers.seen }", "input.id").is_empty());
        let still = round("{ value: input.id }", "input.id");
        assert_eq!(still.len(), 1, "{still:?}");
        assert_eq!(still[0].0, "loader/until-that-cannot-change");
        // An event heard in the round changes `latest-update`; none is heard here.
        assert_eq!(
            round("{ value: latest-update.status }", "input.id")[0].0,
            "loader/until-that-cannot-change"
        );
        assert_eq!(
            round("{ value: steps.c.total }", "input.id")[0].0,
            "loader/a-binding-to-nothing"
        );
    }

    #[test]
    fn a_stage_read_from_later_in_the_round_is_from_later() {
        let found = round("{ value: steps.b.total }", "steps.b.total");
        assert_eq!(found.len(), 1, "{found:?}");
        assert_eq!(found[0].0, "loader/a-binding-from-later");
        assert!(
            found[0].1.contains("later in the round of 'r'"),
            "{}",
            found[0].1
        );
    }

    #[test]
    fn a_stage_reading_the_repeat_it_is_inside_reads_from_later() {
        let found = round("{ value: steps.b.total }", "steps.r.seen");
        assert_eq!(found[0].0, "loader/a-binding-from-later", "{found:?}");
    }

    #[test]
    fn a_used_share_is_read_only_in_a_condition() {
        assert!(
            round("{ value: used.cost-per-run-under }", "input.id")
                .iter()
                .all(|(r, _)| *r == "loader/until-that-cannot-change")
        );
        assert_eq!(
            round("{ value: steps.b.total }", "used.cost-per-run-under")[0].0,
            "loader/a-binding-to-nothing"
        );
    }

    const BRANCHES: &str = "\
tools:
  t:
    actions:
      read:
        takes: { id: text }
        answers-with: { total: number }
workflows:
  w:
    description: d
    accepts: { ids: list of text }
    starts-at: each
    steps:
      each:
        does: each
        over: input.ids
        starts-at: both
        steps:
          both:
            does: together
            steps:
              a:
                does: call
                call: t/read
                bind: { id: item }
              b:
                does: call
                call: t/read
                bind: { id: BIND }
";

    #[test]
    fn an_item_is_read_anywhere_inside_its_each() {
        assert!(
            rules(&BRANCHES.replace("BIND", "item")).is_empty(),
            "{:?}",
            rules(&BRANCHES.replace("BIND", "item"))
        );
    }

    #[test]
    fn a_stage_side_by_side_may_not_have_finished() {
        let found = rules(&BRANCHES.replace("BIND", "steps.a.total"));
        assert_eq!(found.len(), 1, "{found:?}");
        assert_eq!(
            found[0].0,
            "loader/a-binding-to-a-stage-that-may-not-have-run"
        );
        assert!(
            found[0].1.contains("runs side by side with 'b' in 'both'"),
            "{}",
            found[0].1
        );
    }

    #[test]
    fn a_call_to_a_binding_needs_its_may_call() {
        let text = FLOW.replace("        call: t/read\n        bind: { id: input.id }\n        then: { answered: pick }", "        call: input.id\n        then: { answered: pick }");
        let found = rules(&text);
        assert_eq!(
            found.iter().map(|(r, _)| *r).collect::<Vec<_>>(),
            vec!["loader/a-target-picked-from-nowhere"],
            "{found:?}"
        );
        let listed = text.replace(
            "        call: input.id\n",
            "        call: input.id\n        may-call: [t/read]\n",
        );
        assert!(rules(&listed).is_empty(), "{:?}", rules(&listed));
    }

    #[test]
    fn what_a_round_reads_at_its_end_every_way_out_of_the_round_has_run() {
        let text = ROUND
            .replace("UNTIL", "{ value: remembers.seen }")
            .replace("BIND", "input.id")
            .replace(
                "            then: { answered: b }\n",
                "            then: { answered: pick }\n          pick:\n            does: decide\n            chooses-between: { yes: b, no: done }\n",
            );
        let found = rules(&text);
        assert_eq!(found.len(), 1, "{found:?}");
        assert_eq!(
            found[0].0,
            "loader/a-binding-to-a-stage-that-may-not-have-run"
        );
        assert!(
            found[0].1.contains(
                "'r' reads 'steps.b.total' when a round ends, but a round can end on the path \
                 through 'no' without running 'b'."
            ),
            "{}",
            found[0].1
        );
        // The same round, read from a stage every way out passes, is left alone.
        let fine = text.replace("comes-from: steps.b.total", "comes-from: steps.a.total");
        assert!(rules(&fine).is_empty(), "{:?}", rules(&fine));
    }

    #[test]
    fn an_until_of_tool_lines_only_is_left_to_the_tool() {
        assert!(round("{ tool: t/read }", "input.id").is_empty());
    }

    #[test]
    fn the_first_stage_reading_one_that_comes_round_to_it_reads_from_later() {
        let text = FLOW
            .replace(
                "        bind: { id: input.id }\n        then: { answered: pick }",
                "        bind: { id: steps.b.total }\n        then: { answered: pick }",
            )
            .replace(
                "        then: { answered: c }\n",
                "        then: { answered: a }\n",
            )
            .replace("total: money, when: date", "total: text, when: date");
        let found = rules(&text);
        assert_eq!(found.len(), 1, "{found:?}");
        assert_eq!(found[0].0, "loader/a-binding-from-later");
        assert!(
            found[0].1.contains(
                "'a' reads 'steps.b.total', and 'b' runs after it: 'a' is the first stage, so \
                 the first time it runs 'b' has not"
            ),
            "{}",
            found[0].1
        );
    }

    const PARTS: &str = "\
shapes:
  form: { first-name: text, last-name: text, middle: 'text, optional' }
tools:
  t:
    actions:
      fill:
        takes: { fills: form }
workflows:
  w:
    description: d
    accepts: { id: text, n: number }
    starts-at: a
    steps:
      a:
        does: call
        call: t/fill
        bind: BIND
";

    fn parts(bind: &str) -> Vec<(&'static str, String)> {
        rules(&PARTS.replace("BIND", bind))
    }

    #[test]
    fn a_call_may_fill_an_input_part_by_part() {
        let fine = parts("{ fills.first-name: input.id, fills.last-name: input.id }");
        assert!(fine.is_empty(), "{fine:?}");
    }

    #[test]
    fn a_part_the_shape_does_not_have_is_refused_and_the_nearest_offered() {
        let found = parts("{ fills.frist-name: input.id, fills.last-name: input.id }");
        let fit: Vec<_> = found
            .iter()
            .filter(|(r, _)| *r == "loader/a-call-that-does-not-fit")
            .collect();
        assert_eq!(fit.len(), 2, "{found:?}");
        assert!(
            fit.iter().any(|(_, m)| m.contains(
                "fills `fills.frist-name:` of 't/fill', and `fills` is the shape 'form', which \
                 has no part 'frist-name'."
            )),
            "{fit:?}"
        );
        // The misspelt part leaves the real one empty.
        assert!(
            fit.iter()
                .any(|(_, m)| m.contains("leaves its input 'fills.first-name' empty")),
            "{fit:?}"
        );
    }

    #[test]
    fn filling_some_parts_leaves_the_others_empty() {
        let found = parts("{ fills.first-name: input.id }");
        assert_eq!(found.len(), 1, "{found:?}");
        assert!(
            found[0]
                .1
                .contains("leaves its input 'fills.last-name' empty"),
            "{}",
            found[0].1
        );
    }

    #[test]
    fn a_part_is_filled_in_its_own_shape() {
        let found = parts("{ fills.first-name: input.id, fills.last-name: input.n }");
        assert_eq!(
            found.len(),
            0,
            "a number fits text by the auto-map rung: {found:?}"
        );
        let text = PARTS
            .replace("last-name: text", "last-name: number")
            .replace(
                "BIND",
                "{ fills.first-name: input.id, fills.last-name: input.id }",
            );
        let found = rules(&text);
        assert_eq!(found.len(), 1, "{found:?}");
        assert!(
            found[0]
                .1
                .contains("fills `fills.last-name:` of 't/fill' from 'input.id', which is `text`"),
            "{}",
            found[0].1
        );
    }

    #[test]
    fn a_part_of_a_shape_with_no_parts_is_refused() {
        let text = PARTS
            .replace("takes: { fills: form }", "takes: { fills: text }")
            .replace("BIND", "{ fills.first-name: input.id }");
        let found = rules(&text);
        assert!(
            found
                .iter()
                .any(|(_, m)| m.contains("and `fills` is `text`, which has no parts")),
            "{found:?}"
        );
    }

    #[test]
    fn an_input_called_at_is_a_binding_once_and_a_nested_moment_is_read() {
        let text = PARTS
            .replace("takes: { fills: form }", "takes: { id: text, at: text }")
            .replace("BIND", "{ id: input.id, at: steps.zz.name }");
        let found = rules(&text);
        assert_eq!(found.len(), 1, "{found:?}");
        assert!(
            found[0].1.starts_with("'a' reads 'steps.zz.name'"),
            "{}",
            found[0].1
        );
        let nested = "\
workflows:
  w:
    description: d
    accepts: { ids: list of text }
    starts-at: e
    steps:
      e:
        does: each
        over: input.ids
        starts-at: x
        steps:
          x:
            does: ask-someone
            asks: q
            waits-for: { at: input.whenn }
";
        let found = rules(nested);
        assert!(
            found
                .iter()
                .any(|(r, m)| *r == "loader/a-binding-to-nothing"
                    && m.starts_with("'x' reads 'input.whenn'")),
            "{found:?}"
        );
    }

    #[test]
    fn a_shape_made_of_itself_is_refused_once() {
        let found = rules("shapes:\n  a: { b: list of b }\n  b: { a: 'a, optional' }\n");
        assert_eq!(
            found
                .iter()
                .filter(|(r, _)| *r == "loader/a-shape-made-of-itself")
                .count(),
            1,
            "{found:?}"
        );
    }

    #[test]
    fn a_line_only_a_repeat_reads_is_refused_on_an_agents_memory() {
        let found = rules(
            "agents:\n  a:\n    remembers:\n      n:\n        lasts: one-run\n        comes-from: steps.x.y\n        kept-per: id\n",
        );
        assert_eq!(found.len(), 3, "{found:?}");
        assert!(
            found
                .iter()
                .all(|(r, _)| *r == "loader/a-line-this-stage-never-reads")
        );
    }
}
