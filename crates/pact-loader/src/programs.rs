//! Nothing here can run that program.
//!
//! # Why this exists
//!
//! A program declares the `engine:` it is written for; a sandbox declares the
//! `engines:` it can host. Both are closed lists and the schema holds each of
//! them against its own — and it cannot hold them against EACH OTHER, because
//! that is a fact about two documents. So a workspace could carry a program in
//! one language and a locked room that cannot run it, and the only way to find
//! out was the first call.
//!
//! That is the "loads and does nothing" failure with the worst possible timing:
//! the author has written a tool, an action, a program, a sandbox and a consent
//! question, every one of them individually correct, and the arrangement can
//! never work.
//!
//! # What it checks
//!
//! For every action naming a program, the sandbox its tool `connect:`s to must
//! host that program's engine. The refusal names the program, the engine it
//! needs, and what the sandbox actually hosts.
//!
//! **And for every OTHER way of reaching a program, the same question against
//! the whole workspace.** P8 opened seven more doors to a carried body — `uses:`,
//! `projects-with:`, `checked-by:`, `decided-by:`, a metric's `program:`
//! address, a rewriting interceptor sentence — and none of them has a tool, so
//! none of them has a `connect:` line to follow. The question is still
//! answerable: the workspace declares its rooms, and if not one of them runs
//! this kind of program then nothing here can. Measured before this existed: a
//! workspace whose only room runs `wasm`, carrying a `python` program its agent
//! named directly, printed *"loaded cleanly"* — the exact arrangement this file
//! was written to remove, arriving through a door it did not watch.
//!
//! A workspace that declares NO room is left alone, and that is a decision
//! rather than an oversight: PACT declares a locked room and whatever runs your
//! agents supplies it, so a tree with no `resources/` is not broken — it is one
//! whose room comes from the host, which is the seam P7 shipped and the shape
//! `tests/trees/a-desk-that-uses-a-program` demonstrates.
//!
//! # Purity, where the document says purity
//!
//! Four lines in `spec/schema.yaml` say the program they name is refused unless
//! it is `pure`, and each says it for its own reason: `uses:` because a pure
//! program has no act for an approval rule to be about; `projects-with:` because
//! what the model is told has to be the same twice; `decided-by:` because where
//! a run goes next has to be the same twice; and the two rewriting sentences
//! because that is the whole argument for giving `change-the-answer` back to
//! authors after R24 took it away.
//!
//! `checked-by:` and a metric's `program:` address are deliberately NOT held to
//! it. Neither line claims it, and neither wants it: a check on an answer may
//! reasonably hold an account number against a ledger, and a grader that reads a
//! stored rubric is an ordinary grader. A restriction the document never asked
//! for costs an author a capability and buys nobody anything.
//!
//! It deliberately does NOT check that a program is reachable from some tool —
//! `unnamed.rs` already says that about every kind, in the same words, and a
//! second sentence about it here would be two places to keep one rule.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;
use pact_schema::{Schema, Ty};

/// The engines a resource says it can host.
fn hosted_by(resource: &Node) -> Vec<String> {
    match resource.get("engines").map(|n| &n.value) {
        Some(pact_doc::Value::List(items)) => items
            .iter()
            .filter_map(|i| i.as_str().map(str::to_owned))
            .collect(),
        // A single value where a list belongs is accepted everywhere else in
        // this format (FR-1.4.7).
        Some(pact_doc::Value::Str(one)) => vec![one.clone()],
        _ => Vec::new(),
    }
}

/// Only a pure program may be named straight from `uses:`.
///
/// The short door exists because a pure program works from what it is given and
/// touches nothing: there is no act for an approval rule to be about, and
/// nothing an `inspects:` line could usefully look at. A program that may read
/// the outside world, or answer differently the second time, is exactly the kind
/// of call the governance vocabulary exists for — so it keeps its tool, where
/// `needs-a-person:`, `spends-money:` and `same-request-key:` can be written.
/// Letting it in through `uses:` would make the shortcut the way round the gate.
fn only_pure_programs_are_used_directly(root: &Node, diags: &mut Diagnostics) {
    let Some(agents) = root.get("agents").and_then(Node::as_map) else {
        return;
    };
    let programs = root.get("programs").and_then(Node::as_map);
    for (agent_name, agent) in agents {
        let Some(uses) = agent.node.get("uses") else {
            continue;
        };
        let named: Vec<(&str, &Node)> = match &uses.value {
            pact_doc::Value::List(items) => items
                .iter()
                .filter_map(|i| i.as_str().map(|s| (s, i)))
                .collect(),
            pact_doc::Value::Str(one) => vec![(one.as_str(), uses)],
            _ => continue,
        };
        for (name, at) in named {
            let Some(program) = programs.and_then(|p| p.get(name)) else {
                continue;
            };
            let how = program
                .node
                .get("determinism")
                .and_then(Node::as_str)
                .unwrap_or("");
            if how == "pure" {
                continue;
            }
            diags.push(Diagnostic::error(
                "loader/only-a-pure-program-is-used-directly",
                at.span.clone(),
                format!(
                    "'{agent_name}' names the program '{name}' directly, and '{name}' says it \
                     is `{how}` rather than `pure` — so it may look at something outside what \
                     it was given, and a call like that is one somebody may need to approve."
                ),
                format!(
                    "Reach it through a tool instead: give the tool a `connect:` to a locked \
                     room and an action with `program: {name}`, where you can write \
                     `needs-a-person:` beside it. Or mark '{name}' `determinism: pure` if it \
                     really does work only from what it is given."
                ),
            ));
        }
    }
}

/// A projection must be pure, for a reason the short door does not share.
///
/// `projects-with:` decides what the model is TOLD. A projection that could read
/// the outside world, or answer differently the second time, would make the
/// conversation unreproducible — and the trace is what the portability claim is
/// measured on, so two runs of one document have to agree about what the model
/// read. That is a stronger requirement than the one on `uses:`, where purity
/// buys the absence of anything to govern; here it buys determinism itself.
fn only_pure_programs_project(root: &Node, diags: &mut Diagnostics) {
    let Some(tools) = root.get("tools").and_then(Node::as_map) else {
        return;
    };
    let programs = root.get("programs").and_then(Node::as_map);
    for (tool_name, tool) in tools {
        let Some(actions) = tool.node.get("actions").and_then(Node::as_map) else {
            continue;
        };
        for (action_name, action) in actions {
            let Some(named) = action.node.get("projects-with").and_then(Node::as_str) else {
                continue;
            };
            let Some(program) = programs.and_then(|p| p.get(named)) else {
                continue;
            };
            let how = program
                .node
                .get("determinism")
                .and_then(Node::as_str)
                .unwrap_or("");
            if how == "pure" {
                continue;
            }
            let at = action
                .node
                .get("projects-with")
                .map_or_else(|| action.key_span.clone(), |n| n.span.clone());
            diags.push(Diagnostic::error(
                "loader/only-a-pure-program-projects",
                at,
                format!(
                    "'{tool_name}/{action_name}' shortens what it answers with using \
                     '{named}', and '{named}' says it is `{how}` rather than `pure` — so what \
                     the model is told could be different the second time the same thing \
                     happens."
                ),
                format!(
                    "Mark '{named}' `determinism: pure`, or shorten this answer with a \
                     program that works only from what it is given."
                ),
            ));
        }
    }
}

/// A router must be pure, because a path through a loop has to be the same twice.
///
/// `decided-by:` is the escape §5.5 lists as `router`: the three outcomes beside
/// it know what KIND of thing happened and never what was said, so a stage that
/// wants to look again *because of the words it just produced* has nowhere else
/// to put that. The schema prices the escape at `tier: expert` and says the
/// program it names is "refused unless it is `pure`".
///
/// The reason is the trace. Two runs of one document that take different paths,
/// for a reason no line in the document records, cannot be compared — and
/// comparing them is what the portability claim is measured on. It is the same
/// argument `projects-with:` makes about what the model READS, one level up: this
/// one is about where the run GOES.
fn only_pure_programs_decide(root: &Node, diags: &mut Diagnostics) {
    let Some(loops) = root.get("loops").and_then(Node::as_map) else {
        return;
    };
    let programs = root.get("programs").and_then(Node::as_map);
    for (loop_name, shape) in loops {
        let Some(steps) = shape.node.get("steps").and_then(Node::as_map) else {
            continue;
        };
        for (stage_name, stage) in steps {
            let Some(then) = stage.node.get("then") else {
                continue;
            };
            let Some(named) = then.get("decided-by").and_then(Node::as_str) else {
                continue;
            };
            let Some(program) = programs.and_then(|p| p.get(named)) else {
                continue;
            };
            let how = program
                .node
                .get("determinism")
                .and_then(Node::as_str)
                .unwrap_or("");
            if how == "pure" {
                continue;
            }
            let at = then
                .get("decided-by")
                .map_or_else(|| stage.key_span.clone(), |n| n.span.clone());
            diags.push(Diagnostic::error(
                "loader/only-a-pure-program-decides",
                at,
                format!(
                    "'{loop_name}/{stage_name}' lets '{named}' say where the run goes next, \
                     and '{named}' says it is `{how}` rather than `pure` — so the same \
                     request could take a different path the second time, for a reason no \
                     line in this tree records."
                ),
                format!(
                    "Mark '{named}' `determinism: pure`, or route this stage with the \
                     `used-a-tool:`, `answered:` and `too-many-times:` lines beside it, \
                     which say where to go from what KIND of thing happened."
                ),
            ));
        }
    }
}

/// A rewriting sentence must name a pure program, and this is the one that
/// matters most.
///
/// R24 took `change-the-answer` and `change-the-request` off `may:` and was
/// right to: no sentence could carry them out, so declaring either got the rule
/// refused by the next check down. §6 recorded them host-only with the condition
/// that would let them back — a sentence somebody actually wants — and noted the
/// worry, that a mid-run rewrite "is not reviewable in a way `instructions:` and
/// a stage's `says:` are".
///
/// §8.5 withdrew half of R24 on one argument: a carried program answers that
/// worry rather than dodging it, because it is "a file in the folder,
/// fingerprinted, declared with what it takes and answers with, and refused
/// unless it is `pure` — so what the rewrite does is as readable as the
/// instructions it sits beside, and the same twice".
///
/// Every clause of that was true except the last one, which nothing enforced. A
/// `nondeterministic` rewriter loaded cleanly, and with it the withdrawal's
/// whole argument was untrue of the file that had just been accepted.
fn only_pure_programs_rewrite(root: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let programs = root.get("programs").and_then(Node::as_map);
    for named in schema.names_in_sentences(root) {
        if named.collection != PROGRAMS {
            continue;
        }
        let Some(program) = programs.and_then(|p| p.get(named.name.as_str())) else {
            continue;
        };
        let how = program
            .node
            .get("determinism")
            .and_then(Node::as_str)
            .unwrap_or("");
        if how == "pure" {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/only-a-pure-program-rewrites",
            named.at.clone(),
            format!(
                "'{}' says it is `{}` rather than `pure`, and this rule hands it what is \
                 about to be said: \"{}\". A rewrite has to be readable and the same twice, \
                 which is the whole reason a rule is allowed to make one at all.",
                named.name, how, named.said
            ),
            format!(
                "Mark '{}' `determinism: pure`, or take this sentence out and say the same \
                 thing in the agent's `instructions:`, where a person can read it.",
                named.name
            ),
        ));
    }
}

/// The collection a program lives in, as `names:` spells it.
const PROGRAMS: &str = "programs";

/// One place this document reaches a carried program.
struct Reach {
    /// The program's name, as the author wrote it.
    name: String,
    /// Every collection the field could have been naming, in the order the
    /// specification lists them.
    ///
    /// `uses:` names four — tools, skills, knowledge, programs — and resolution
    /// takes the first that has the key. Without this, a workspace with a tool
    /// and a program of the same name had `uses: tidy` counted as a program
    /// reach when it is a tool: the sort of quiet mis-reading that only shows up
    /// as a warning that did not appear.
    collections: Vec<String>,
    /// Kept for the refusal a future reach-level check would print. Nothing
    /// reads it since the workspace-wide engine rule was withdrawn above.
    #[allow(dead_code)]
    at: Span,
    /// Where it was written, in the author's words — "'desk' names it in `uses:`".
    how: String,
}

/// Does anything here need a locked room that has no `connect:` to point at it?
///
/// `unnamed.rs` counts a resource as named by `connect:` on a tool or `through:`
/// on a port, and both of those are lines on a tool or a port. A `does:
/// run-code` stage names no program and no tool; a program reached by `uses:`,
/// `decided-by:`, `checked-by:` or a rewriting sentence has no tool either. All
/// of them need a room and none of them can write the line that would say so.
///
/// Measured before this existed: obeying the `run-code` refusal's own printed fix
/// — "add a file under `resources/` whose `resource-kind:` is `sandbox`" —
/// produced `warning: 'py-room' is a connected system that nothing here names`,
/// and `--deny-warnings` still failed. A fix that draws a warning is not a fix.
pub fn a_room_is_needed_with_no_tool_to_name_it(root: &Node, schema: &Schema) -> bool {
    if let Some(loops) = root.get("loops").and_then(Node::as_map) {
        for (_, shape) in loops {
            let Some(steps) = shape.node.get("steps").and_then(Node::as_map) else {
                continue;
            };
            if steps
                .iter()
                .any(|(_, st)| st.node.get("does").and_then(Node::as_str) == Some(RUN_CODE))
            {
                return true;
            }
        }
    }
    let Some(programs) = root.get("programs").and_then(Node::as_map) else {
        return false;
    };
    let mut found = Vec::new();
    reaches(root, "workspace", schema, "", 0, &mut found);
    if found.iter().any(|r| {
        !r.how.ends_with("in `program:`")
            && programs.get(r.name.as_str()).is_some()
            && names_a_program(root, r)
    }) {
        return true;
    }
    schema
        .names_in_sentences(root)
        .iter()
        .any(|n| n.collection == PROGRAMS && programs.get(n.name.as_str()).is_some())
}

/// Does this reach really name a PROGRAM, and not something listed before it?
///
/// A field naming several collections resolves against the first that has the
/// key, so `uses: tidy` in a workspace holding both `tools: {tidy}` and
/// `programs: {tidy}` is the tool. Reading it as a program was harmless in itself
/// and wrong in a way nothing would show: a room excused from
/// `nothing-points-at-it` because of a reach that is not one.
fn names_a_program(root: &Node, reach: &Reach) -> bool {
    for collection in &reach.collections {
        if collection == PROGRAMS {
            return true;
        }
        if root
            .get(collection)
            .and_then(Node::as_map)
            .is_some_and(|m| m.get(reach.name.as_str()).is_some())
        {
            return false;
        }
    }
    true
}

/// Every place this document names a carried program, found from the schema.
///
/// By walking the specification's own `names:` declarations rather than keeping
/// a list of the seven fields that reach a program today. A field added to
/// `spec/schema.yaml` with `names: programs` joins this check by existing, which
/// is the rule `currency.rs`, `available.rs` and `handover.rs` are all written
/// to — and the rule this file broke, by watching one door and letting P8 cut
/// six more.
fn reaches(
    node: &Node,
    group: &str,
    schema: &Schema,
    trail: &str,
    depth: usize,
    out: &mut Vec<Reach>,
) {
    if depth > 12 {
        return;
    }
    let Some(g) = schema.group(group) else { return };
    let Some(map) = node.as_map() else { return };
    for field in &g.fields {
        let Some(entry) = map.get(field.name.as_str()) else {
            continue;
        };
        if field.names.iter().any(|n| n == PROGRAMS) {
            let items: Vec<&Node> = match &entry.node.value {
                pact_doc::Value::List(l) => l.iter().collect(),
                _ => vec![&entry.node],
            };
            for item in items {
                let Some(name) = item.as_str() else { continue };
                out.push(Reach {
                    name: name.trim().to_string(),
                    collections: field.names.clone(),
                    at: item.span.clone(),
                    how: format!("'{trail}' names it in `{}:`", field.name),
                });
            }
        }
        match &field.ty {
            Ty::Group(kind) => reaches(&entry.node, kind, schema, trail, depth + 1, out),
            Ty::MapOf(inner) | Ty::ListOf(inner) => {
                if let Ty::Group(kind) = inner.as_ref() {
                    match &entry.node.value {
                        pact_doc::Value::Map(m) => {
                            for (key, child) in m {
                                let below = if trail.is_empty() {
                                    key.clone()
                                } else {
                                    format!("{trail}/{key}")
                                };
                                reaches(&child.node, kind, schema, &below, depth + 1, out);
                            }
                        }
                        pact_doc::Value::List(l) => {
                            for child in l {
                                reaches(child, kind, schema, trail, depth + 1, out);
                            }
                        }
                        _ => {}
                    }
                }
            }
            _ => {}
        }
    }
}

/// Every room this workspace declares, and what each says it can run.
fn rooms(root: &Node) -> Vec<(String, Vec<String>)> {
    let Some(resources) = root.get("resources").and_then(Node::as_map) else {
        return Vec::new();
    };
    resources
        .iter()
        .filter(|(_, r)| r.node.get("resource-kind").and_then(Node::as_str) == Some("sandbox"))
        .map(|(name, r)| (name.clone(), hosted_by(&r.node)))
        .collect()
}

/// WITHDRAWN: the workspace-wide engine check, and why it is not here.
///
/// It existed for one round and asked: if the workspace declares ANY sandbox,
/// does some declared sandbox host the engine of every program reached without a
/// tool? The trigger was `rooms(root).is_empty()`.
///
/// The rule read one declared room as a claim about every room, and no line in
/// any tree ever says "these are all the rooms there are". The tell is that the
/// same tree with NO rooms was accepted in silence: a workspace could not be
/// wrong until it declared something, and then it was wrong about things it had
/// not mentioned.
///
/// Measured on the shipped tree this module's header cites. Take
/// `a-desk-that-uses-a-program` — a `wasm` program named straight from `uses:`,
/// no `resources/`, clean — and add one self-contained `python` capability
/// beside it, with its own room, program and tool. Nothing about the `wasm`
/// arrangement changes, and it was refused.
///
/// Every way out was worse than the problem. Writing `wasm` into the python
/// room's `engines:` passes and is a false statement about a room the tree does
/// not own — the T7 shape, a declared control that is no longer true. Adding a
/// real `wasm` room clears the error and draws `nothing-points-at-it`, because a
/// `uses:`-reached program has no `connect:` to write, so `--deny-warnings`
/// still fails. And it collided with the rule one function down: a `run-code`
/// stage is refused with a fix saying "add a sandbox", and obeying that fix
/// refused the `uses:` program beside it. That tree had no clean state.
///
/// What survives is the question a tree can actually answer, and it is the one
/// P6 always asked: a program reached THROUGH A TOOL is held against the room
/// that tool `connect:`s to, in both directions, because that pairing is written
/// down. Where no pairing exists the room comes from the host — P7's seam —
/// whether the tree declares nought rooms or nine.
///
/// `spec/schema.yaml`'s `engines:` sentence was narrowed in the same change to
/// say what is really checked, rather than being left as a promise about every
/// reach that only one reach keeps.
///
/// Held by `a_room_declared_for_one_purpose_does_not_retract_the_seam_for_another`
/// and `a_code_stage_and_a_directly_used_program_can_live_in_one_tree`.
/// A stage that writes code, in a workspace with nowhere to run it.
///
/// `docs/27` states it as a rule — a `does: run-code` stage is "legal only when
/// the agent's workspace declares a sandbox resource" — and the adapter test's
/// own header repeats it. Nothing in the loader had ever heard of `run-code`;
/// the only thing holding the rule was a halt at run time, which is a true
/// sentence arriving in the wrong place.
///
/// This is the ONE reach where the absence of a room is refused rather than
/// passed over, and the difference is what the line names. Every other reach
/// names a program the AUTHOR wrote, and P7's seam says the room for it may
/// reasonably come from the host — `a-desk-that-uses-a-program` depends on
/// exactly that. A `run-code` stage names nothing at all: there is no program
/// document, no engine, no fuel, and nothing for a host to match against. In a
/// workspace with no room it is a stage that can never be anything but the halt.
fn a_stage_that_writes_code_has_a_room(root: &Node, diags: &mut Diagnostics) {
    if !rooms(root).is_empty() {
        return;
    }
    let Some(loops) = root.get("loops").and_then(Node::as_map) else {
        return;
    };
    for (loop_name, shape) in loops {
        let Some(steps) = shape.node.get("steps").and_then(Node::as_map) else {
            continue;
        };
        for (stage_name, stage) in steps {
            if stage.node.get("does").and_then(Node::as_str) != Some(RUN_CODE) {
                continue;
            }
            let at = stage
                .node
                .get("does")
                .map_or_else(|| stage.key_span.clone(), |n| n.span.clone());
            diags.push(Diagnostic::error(
                "loader/nothing-here-can-run-that-program",
                at,
                format!(
                    "'{loop_name}/{stage_name}' writes code to be run, and this \
                     workspace declares no locked room to run it in — so the stage can \
                     only ever stop and say so."
                ),
                "Add a file under `resources/` whose `resource-kind:` is `sandbox`, \
                 with an `engines:` line saying what it can run. A stage that writes \
                 code names no program, so there is nothing for whoever runs your \
                 agents to match a room against — the room has to be in the tree."
                    .to_string(),
            ));
        }
    }
}

/// The stage kind that writes its own code, as `phase.does` spells it.
const RUN_CODE: &str = "run-code";

/// What a block of `answers-with:` lines says: each name with its shape as
/// written, spaces and case aside.
fn hands_back(owner: &Node) -> Option<std::collections::BTreeMap<String, String>> {
    let lines = owner.get("answers-with")?.as_map()?;
    Some(
        lines
            .iter()
            .map(|(name, shape)| {
                let written = shape
                    .node
                    .as_str()
                    .map_or_else(|| shape.node.to_json().to_string(), str::to_string);
                (
                    name.clone(),
                    written
                        .split_whitespace()
                        .collect::<Vec<_>>()
                        .join(" ")
                        .to_lowercase(),
                )
            })
            .collect(),
    )
}

/// An action that runs a program hands back what the program hands back.
///
/// Both may say so (`answers-with:`, 02P A4), and nothing compared them: an
/// action promising `verdict: text` over a program that answers `verdict: one
/// of inside, outside` loaded cleanly, and a host holding the result to one of
/// the two refused what the other allowed. The program is what runs, so its
/// word is the answer; the action may leave the block out, or say the same.
fn hands_back_what_its_program_does(
    tool: &str,
    action_name: &str,
    action: &Node,
    named: &str,
    program: &Node,
) -> Option<Diagnostic> {
    let said = hands_back(action)?;
    let runs = hands_back(program).unwrap_or_default();
    if said == runs {
        return None;
    }
    let differs: Vec<String> = said
        .keys()
        .chain(runs.keys())
        .collect::<std::collections::BTreeSet<_>>()
        .into_iter()
        .filter(|k| said.get(*k) != runs.get(*k))
        .map(|k| format!("`{k}`"))
        .collect();
    Some(Diagnostic::error(
        "loader/an-action-and-its-program-hand-back-different-things",
        action
            .get("answers-with")
            .map_or_else(|| action.span.clone(), |n| n.span.start_of_block()),
        format!(
            "'{tool}/{action_name}' runs the program '{named}', and the two `answers-with:` \
             blocks disagree about {}{}.",
            differs.join(", "),
            if runs.is_empty() {
                format!(" — '{named}' says nothing about what it hands back")
            } else {
                String::new()
            }
        ),
        format!(
            "Delete `answers-with:` from '{tool}/{action_name}' (the program's is what a \
             result is held to), or make the two say the same, line for line."
        ),
    ))
}

/// Refuse an arrangement where nothing can run the program that was named.
pub fn check(root: &Node, schema: &Schema, diags: &mut Diagnostics) {
    a_stage_that_writes_code_has_a_room(root, diags);
    only_pure_programs_are_used_directly(root, diags);
    only_pure_programs_project(root, diags);
    only_pure_programs_decide(root, diags);
    only_pure_programs_rewrite(root, schema, diags);
    let Some(tools) = root.get("tools").and_then(Node::as_map) else {
        return;
    };
    let programs = root.get("programs").and_then(Node::as_map);
    let resources = root.get("resources").and_then(Node::as_map);

    for (tool_name, tool) in tools {
        let Some(actions) = tool.node.get("actions").and_then(Node::as_map) else {
            continue;
        };
        // Which locked room this tool reaches. A tool reaches ONE place
        // (`reach.rs`), so there is one answer or none.
        let reaches = tool.node.get("connect").and_then(Node::as_str);

        for (action_name, action) in actions {
            let Some(named) = action.node.get("program").and_then(Node::as_str) else {
                continue;
            };
            // Whether the program EXISTS is `names: programs`, held by the
            // schema where the author wrote it. This pass only asks whether the
            // arrangement can work.
            let Some(program) = programs.and_then(|p| p.get(named)) else {
                continue;
            };
            if let Some(d) = hands_back_what_its_program_does(
                tool_name,
                action_name,
                &action.node,
                named,
                &program.node,
            ) {
                diags.push(d);
            }
            let Some(engine) = program.node.get("engine").and_then(Node::as_str) else {
                continue;
            };

            let at = action
                .node
                .get("program")
                .map_or_else(|| action.key_span.clone(), |n| n.span.clone());

            let Some(server) = reaches else {
                diags.push(Diagnostic::error(
                    "loader/nothing-here-can-run-that-program",
                    at,
                    format!(
                        "'{tool_name}/{action_name}' runs the program '{named}', and \
                         '{tool_name}' does not reach a locked room to run it in."
                    ),
                    format!(
                        "Add `connect: <name>` on `tools/{tool_name}.yaml`, naming a resource \
                         whose `resource-kind:` is `sandbox`."
                    ),
                ));
                continue;
            };

            let Some(resource) = resources.and_then(|r| r.get(server)) else {
                continue;
            };
            let kind = resource.node.get("resource-kind").and_then(Node::as_str);
            if kind != Some("sandbox") {
                diags.push(Diagnostic::error(
                    "loader/nothing-here-can-run-that-program",
                    at,
                    format!(
                        "'{tool_name}/{action_name}' runs the program '{named}', and \
                         '{tool_name}' reaches '{server}', which is {}.",
                        match kind {
                            Some(k) => format!("a {k}"),
                            None => "not a locked room".to_string(),
                        }
                    ),
                    "Point `connect:` at a resource whose `resource-kind:` is `sandbox`. A \
                     program runs in a locked room and nowhere else."
                        .to_string(),
                ));
                continue;
            }

            let hosts = hosted_by(&resource.node);
            if !hosts.iter().any(|h| h == engine) {
                diags.push(Diagnostic::error(
                    "loader/nothing-here-can-run-that-program",
                    at,
                    format!(
                        "'{named}' is written for `{engine}`, and '{server}' — the locked room \
                         '{tool_name}' reaches — {}.",
                        if hosts.is_empty() {
                            "says nothing about what it can run".to_string()
                        } else {
                            format!("runs only {}", hosts.join(", "))
                        }
                    ),
                    format!(
                        "Add `{engine}` under `engines:` in `resources/{server}.yaml`, or write \
                         '{named}' for one of the kinds that room already runs."
                    ),
                ));
            }
        }
    }
}
