//! **A stage no path from `starts-at:` ever arrives at — and a loop no path
//! ever leaves.**
//!
//! §7.6 rule 7 already states this shape for the graph half of PACT — *"a
//! `join` with `waits-for: everyone` is reachable from every member of its
//! group"* — and the loop half had no equivalent. This is that rule for loops.
//!
//! # The hole this closes
//!
//! Everything else about an authored loop is checked. A `then:` target that
//! names no stage is caught by `names: ^steps` (*"'answered' names 'reread',
//! and there is no such entry in `steps:`"*); a `may-use:` naming a tool the
//! agent has not got is caught the same way; `at-most: 0` is caught by
//! `at-least: 1` as `schema/below-the-floor`. All three are one *value* being
//! wrong, which is what a schema can see.
//!
//! Reachability is not a property of any one value. Change
//! `examples/refund-desk/loops/careful.yaml` so `starts-at: gather` reads
//! `starts-at: reply` and every line in that file is still individually
//! correct: `reply` is a real stage, every `then:` names a real stage, every
//! tool exists. `pact check` said *"OK — loaded cleanly (468 settings)"* and
//! exited 0. But `gather` and `re-read` — the two stages the loop exists for,
//! and the subject of its own twenty-five-line header comment — had become dead
//! text that never runs, and the author was told nothing. That is the "loads and
//! does nothing" failure this project keeps having to close by hand.
//!
//! # The second hole: a loop the run can never leave
//!
//! The walk below seeds `done` as already-reached (it is the finish line, not a
//! stage), so it can say which stages the run gets *to* and never whether the
//! run gets *out*. Nobody was asking the backward question, and the same file
//! answers it wrongly just as quietly. Measured on the same copy of
//! `examples/refund-desk`: change the last two lines of `careful.yaml`'s
//! `reply` stage from `answered: done` to `answered: reply` and `pact check`
//! printed *"OK — loaded cleanly (492 settings)"* and exited 0. Every line is
//! individually correct — `reply` is a real stage and `answered:` is a real
//! outcome — and the run then writes the refund decision, goes round again
//! instead of handing it over, and keeps going until a ceiling in `limits:`
//! ends it. Measured on that tree, same question, same scripted model: **4
//! model calls become 12**, which is the whole of the example's
//! `steps-at-most: 12`, and every one after the fourth re-answers a question
//! already answered. What comes back is `stopped_by` rather than an ending —
//! under the example's own `when-it-runs-out: ask-a-person` a person is
//! interrupted about a decision that was made eight steps earlier, and under
//! the default `stop-and-say-so` `harness._ran_out` replaces the decision with
//! *"Stopped before finishing: this run reached the limit you set with
//! `steps-at-most` (12 of 12 steps)."* The answer was written, paid for three
//! times over, and thrown away.
//!
//! Two things count as a way out, and the second is why this is not the
//! one-line check it looks like:
//!
//! - a `then:` line whose value is `done`, from any of the three outcomes;
//! - **a stage with no `answered:` line at all**, because `Loop.route`'s
//!   documented fallback is that *"an agent that has produced its answer and
//!   has no further instruction is done, not broken"*. Such a stage ends the
//!   run without the word `done` appearing anywhere in the file, and counting
//!   only the literal would refuse loops that finish perfectly well.
//!
//! What is *not* a way out: an interceptor. `may: halt` stops a run
//! (`result.halted = "stopped-by-rule"`) and a `redirect` goes to a stage —
//! `_sent_to` resolves through `Loop.phase`, which does not know `done` — so
//! neither of them can finish a loop, and a loop that leans on one still hands
//! back a stop rather than an answer.
//!
//! The refusal this costs, stated rather than hidden: a loop meant to run until
//! the budget stops it can no longer be written by leaving the exit out. It is
//! written with `at-most:` and `too-many-times: done`, which is the same fix
//! `_stage_to_run` already prints at run time when spent stages lead only to
//! each other — *"point one stage's `then:` at `done`"*. One shape, said in one
//! way, and said before the budget is spent rather than after.
//!
//! # What the walk follows
//!
//! Every value under a stage's `then:` whose outcome that stage's `does:` can
//! end in, and a `decide`'s `chooses-between:` labels (`workflows::successors`).
//! Which outcomes a `does:` ends in is one table, `workflows::outcomes` (02W
//! §2.4), which WF-3 also holds the author to: in an agent's loop, the shipped
//! outcomes; in a workflow, `answered` for a `call`, `each` or `together`, and
//! so on. A line for an outcome that cannot happen leads nowhere a run can go,
//! so it reaches nothing (and WF-3 says so where it is written). A key under
//! `then:` that is not an outcome at all is reported by the unknown-field check
//! against the schema's `outcome` group.
//!
//! **The documented fallbacks add no target.** `answered` with nowhere to go
//! finishes; `too-many-times` with nowhere to go *"goes wherever `answered:`
//! goes"* (the schema's own words under `then:`, and
//! `harness._stage_to_run`'s `phase.then.get("too-many-times") or
//! loop.route(phase, "answered")`), which is a target already written down;
//! `used-a-tool` with nowhere to go stops the run. So the set of successors a
//! run can actually take is exactly the set of values written under the
//! outcomes it can end in, and honouring the fallbacks is what taking all of
//! them *does*.
//!
//! # What it deliberately stays quiet about
//!
//! One mistake gets one message. Where the loop already contains a mistake that
//! makes its graph meaningless — a `then:` naming no stage, a `starts-at:`
//! naming no stage — this says nothing at all and leaves it to the reference
//! check that reports it at the line the author typed. `report::check_deadline`
//! makes the same call for the same reason: a second diagnostic saying the same
//! thing in other words is two things to fix for one edit, and here the second
//! one would be actively misleading — *"nothing sends the agent to 'reply'"* is
//! a strange thing to read when you have just misspelled `reply` in a `then:`.
//!
//! A loop with `based-on:` is skipped too, and that is a real limitation stated
//! rather than hidden: the stages it inherits are not in this document (they are
//! resolved by `Loop.from_mapping` on the executing side), so a walk here would
//! be a walk over half a graph and would report stages as unreachable that the
//! ready-made shape reaches perfectly well. A false refusal is worse than the
//! hole.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;
use std::collections::BTreeSet;

/// The finish line, not a stage. The schema writes it as `or-one-of: [done]` on
/// each outcome, and `pact_adapters.loops.DONE` is the same string on the
/// executing side; a stage may not be called this.
const DONE: &str = "done";

/// Where `nobody-answered:` may go besides a stage: stopping, which is no stage.
const STOP: &str = "stop-and-say-so";

/// The outcome that ends a run when it is not routed, and the one that happens
/// only when a stage has run its `at-most:` times. Both are facts about how a
/// run behaves rather than entries in a vocabulary — see `finishes`, which is
/// the only place either of them is read.
const ANSWERED: &str = "answered";
const TOO_MANY: &str = "too-many-times";

/// Report every stage of every authored loop that no path from `starts-at:`
/// reaches.
///
/// Takes the loaded document and nothing else — no second pass over the
/// filesystem, no author code — for the reason `LoadReport::of` gives.
pub fn every_stage_is_reachable(document: &Node, diags: &mut Diagnostics) {
    for (name, entry) in document.get("loops").and_then(Node::as_map).into_iter().flatten() {
        one_loop(name, &entry.node, diags);
    }
    // A workflow is a stage loop that belongs to no agent (02W §1), so the same
    // walk holds it — and the inside of each of its `each`, `repeat` and
    // `together` stages, which is a stage loop of its own.
    for (name, entry) in document.get("workflows").and_then(Node::as_map).into_iter().flatten() {
        let Some(steps) = entry.node.get("steps").and_then(Node::as_map) else { continue };
        if let Some(start) = entry.node.get("starts-at").and_then(Node::as_str).map(str::trim) {
            unreached(&format!("the workflow '{name}'"), "the run", start, steps, true, diags);
        }
        insides(steps, diags);
    }
}

/// The inside of every `each`, `repeat` and `together` among `steps`.
fn insides(steps: &pact_doc::Map, diags: &mut Diagnostics) {
    for (stage, entry) in steps {
        let does = entry.node.get("does").and_then(Node::as_str).map(str::trim);
        let Some(does @ ("each" | "repeat" | "together")) = does else { continue };
        let Some(inner) = entry.node.get("steps").and_then(Node::as_map) else {
            diags.push(Diagnostic::error(
                "loader/loop-with-nothing-in-it",
                entry.key_span.clone(),
                format!("'{stage}' does `{does}` and has no `steps:`, so there is nothing inside it to run."),
                format!(
                    "Add a `steps:` block under '{stage}' naming what happens inside it{}.",
                    if does == "together" { "" } else { ", and a `starts-at:` saying which runs first" }
                ),
            ));
            continue;
        };
        // Every inside stage of a `together` starts at once.
        if does != "together" {
            match entry.node.get("starts-at").and_then(Node::as_str).map(str::trim) {
                Some(start) if !start.is_empty() => {
                    unreached(&format!("'{stage}'"), "the run", start, inner, true, diags);
                }
                _ => diags.push(Diagnostic::error(
                    "loader/loop-with-no-first-stage",
                    entry.key_span.clone(),
                    format!("'{stage}' does not say which of its own stages runs first."),
                    format!(
                        "Add a line `starts-at: {}` under '{stage}'. Its stages are: {}.",
                        inner.keys().next().map(String::as_str).unwrap_or("work"),
                        inner.keys().map(String::as_str).collect::<Vec<_>>().join(", ")
                    ),
                )),
            }
        }
        insides(inner, diags);
    }
}

fn one_loop(name: &str, shape: &Node, diags: &mut Diagnostics) {
    // Half a graph is not a graph — see the module note.
    if shape.get("based-on").and_then(Node::as_str).is_some_and(|s| !s.trim().is_empty()) {
        return;
    }
    let Some(steps) = shape.get("steps").and_then(Node::as_map) else {
        // A loop that is neither a ready-made shape nor a set of stages has
        // nothing to run at all. `loops.py` refuses it — *"loop 'mine' has no
        // stages, so there is nothing to run"* — and `pact check` printed
        // "loaded cleanly", so the author's own tool said the file was fine and
        // the run died elsewhere.
        diags.push(Diagnostic::error(
            "loader/loop-with-nothing-in-it",
            shape.span.start_of_block(),
            format!(
                "The loop '{name}' has no stages and does not start from a ready-made \
                 shape, so there is nothing for the agent to do."
            ),
            "Add a line `based-on: pact:loop/standard` to start from a shape PACT ships, \
             or a `steps:` block naming the stages and a `starts-at:` saying which runs \
             first."
                .to_string(),
        ));
        return;
    };
    let start = shape.get("starts-at").and_then(Node::as_str).map(str::trim).unwrap_or("");
    if start.is_empty() {
        // Which stage runs first is not something PACT may guess: the stages are
        // a map, and picking the first written one would make reordering a file
        // change behaviour. `loops.py` refuses it with the same fix line.
        let first = steps.keys().next().map(String::as_str).unwrap_or("work");
        diags.push(Diagnostic::error(
            "loader/loop-with-no-first-stage",
            shape.span.start_of_block(),
            format!("The loop '{name}' does not say which stage runs first."),
            format!(
                "Add a line `starts-at: {first}`. The stages here are: {}.",
                steps.keys().map(String::as_str).collect::<Vec<_>>().join(", ")
            ),
        ));
        return;
    }
    if unreached("this loop", "the agent", start, steps, false, diags) {
        // Every stage runs. Now the other question, which the walk that just
        // finished cannot answer by walking any further forward: is there a way
        // out of here at all.
        no_way_to_finish(name, steps, diags);
    }
}

/// Report every stage of `steps` no path from `start` reaches, in one
/// diagnostic. True when every stage is reached (and the walk meant something).
///
/// `what` names the stages' owner in the sentence (`this loop`, `the workflow
/// 'trial-booking'`) and `who` what moves through them (`the agent`, `the run`).
/// `in_workflow` says which outcomes a stage can end in (02W §2.4): a line under
/// `then:` for an outcome that never happens leads nowhere a run can go.
fn unreached(
    what: &str,
    who: &str,
    start: &str,
    steps: &pact_doc::Map,
    in_workflow: bool,
    diags: &mut Diagnostics,
) -> bool {
    if !steps.contains_key(start) || !walkable(steps) {
        return false;
    }

    // `done` is seeded as already-reached so that it is never walked into and
    // never reported: it is the finish line, and a stage misnamed after it is a
    // different mistake with a different message.
    let mut reached: BTreeSet<&str> = BTreeSet::from([DONE, start]);
    let mut frontier: Vec<&str> = vec![start];
    while let Some(name) = frontier.pop() {
        let Some(stage) = steps.get(name) else { continue };
        // Every target is a real stage, `done` or `stop-and-say-so` —
        // `walkable` said so above.
        for target in crate::workflows::successors(&stage.node, in_workflow) {
            if reached.insert(target) {
                frontier.push(target);
            }
        }
    }

    let missed: Vec<(&String, &Span)> = steps
        .iter()
        .filter(|(name, _)| !reached.contains(name.as_str()))
        .map(|(name, entry)| (name, &entry.key_span))
        .collect();
    let Some(((first, first_at), rest)) = missed.split_first() else {
        return true;
    };

    // All of them in one diagnostic, anchored at the first, exactly as
    // `report_companions` collapses one missing companion asked for by four
    // settings into one problem to fix. Four copies of this sentence would be
    // four things to read and one thing to change.
    let one = rest.is_empty();
    let mut d = Diagnostic::error(
        "loader/stage-nothing-reaches",
        (*first_at).clone(),
        format!(
            "Nothing in {what} ever sends {who} to {}, so {}.",
            or_list(&missed),
            if one {
                "that stage never runs and everything written in it is dead text"
            } else {
                "those stages never run and everything written in them is dead text"
            }
        ),
        // Two ways in and one way out, all three typeable. The second says
        // *point* a line rather than *add* one, because `{start}` may already
        // have written the outcome being named and a fix that produces a
        // duplicate key is not a fix.
        format!(
            "Write `starts-at: {first}` to begin there — or send {who} there from a \
             stage that does run, by pointing one of the lines under `{start}`'s `then:` \
             at it, like `answered: {first}`. {}",
            if one {
                "If it is not wanted any more, delete it."
            } else {
                "If they are not wanted any more, delete them."
            }
        ),
    );
    for (name, at) in rest {
        d = d.with_related((*at).clone(), format!("'{name}' is never reached either"));
    }
    diags.push(d);
    false
}

/// Report a loop whose stages all run and which none of them ever leaves.
///
/// Called only when every stage is reachable, which is not tidiness: a `done`
/// written inside a stage nothing reaches is not a way out, so a walk that
/// counted it would call a dead loop finishable. Reporting both at once was the
/// other option and it is worse — the author has one shape to fix, and the two
/// messages would argue about it: *"nothing sends the agent to 'gather'"* wants
/// an arrow added, and this one wants an arrow pointed at `done`. Fix the
/// arrows, run `pact check` again, and this asks its question of the loop that
/// was meant. `walkable` and `report::check_deadline` make the same call.
fn no_way_to_finish(name: &str, steps: &pact_doc::Map, diags: &mut Diagnostics) {
    if steps.values().any(|stage| finishes(&stage.node)) {
        return;
    }
    // Which `then:` block to underline. The stage that gives the answer, if the
    // loop has one: `does: answer` is the stage whose whole job is the reply, so
    // it is where `answered: done` belongs and the first place somebody looking
    // for a missing ending will look. Failing that the last stage written, for
    // the reason a chain reads top to bottom — the end of it is at the bottom.
    let answering = steps
        .iter()
        .rev()
        .find(|(_, s)| s.node.get("does").and_then(Node::as_str).map(str::trim) == Some("answer"));
    let Some((choice, entry)) = answering.or_else(|| steps.iter().next_back()) else {
        // No stages at all is `loop-with-nothing-in-it`, said above.
        return;
    };

    // The one `done` in this file that may not be a mistake but a
    // misunderstanding: `too-many-times: done` on a stage with no `at-most:`.
    // Told "no stage sends the agent to `done`" while looking at a line that
    // says `done`, an author would decide the tool is broken — so when that
    // shape is here, the fix explains it instead of repeating itself.
    let stranded = steps
        .iter()
        .find(|(_, s)| routes_to_done(&s.node, TOO_MANY) && s.node.get("at-most").is_none())
        .map(|(n, _)| n);

    // Every stage here has an `answered:` line and none of them says `done` —
    // that is exactly what `finishes` returning false for all of them means. So
    // there is one line per stage to offer, and "change one of these" is a fix
    // and not a search.
    let mut d = Diagnostic::error(
        "loader/loop-that-never-finishes",
        answered_line(&entry.node).unwrap_or(&entry.key_span).clone(),
        format!(
            // Every claim here is measured on the worked example with this edit
            // applied: 4 model calls became 12, and all three `when-it-runs-out:`
            // actions returned `stopped_by` — so "ran out rather than finished"
            // is true whichever one the author wrote, while "the answer is
            // thrown away" would have been true of only two of them.
            "Nothing in the loop '{name}' ever finishes: no stage sends the agent to \
             `done`. Once it has written the answer it goes round again instead of \
             handing it over, until it reaches one of the ceilings in `limits:` — so \
             the same answer is paid for over and over, and what comes back says the \
             run ran out rather than that it finished."
        ),
        // "Change", not "add": each of these stages has already written the line
        // being named, and a fix that produces a second `answered:` under the
        // same `then:` is not a fix.
        //
        // The second sentence is the escape hatch for the one thing this rule
        // refuses that somebody may have meant — a loop that goes round until it
        // has had enough. It is the same pair `_stage_to_run` already offers at
        // run time ("raise one of those `at-most:` numbers, or point one stage's
        // `then:` at `done`"), said before the budget is spent instead of after.
        // The third is two edits and says so: a new stage nothing points at is
        // the mistake reported directly above this one.
        format!(
            "Change one of these lines to `done` — under `{choice}` it would read \
             `answered: done`. {} Or add a stage that ends, and point one of these \
             lines at it.",
            match stranded {
                Some(s) => format!(
                    "`{s}` already sends `too-many-times:` to `done`, and that only \
                     happens once a stage has run its `at-most:` times — so add a line \
                     like `at-most: 3` to `{s}` and it will end there."
                ),
                None =>
                    "To go round a fixed number of times first, put a line like \
                     `at-most: 3` on a stage and send its `too-many-times:` to `done`."
                        .to_string(),
            }
        ),
    );
    for (other, at) in steps.iter().filter(|(n, _)| n.as_str() != choice.as_str()) {
        d = d.with_related(
            answered_line(&at.node).unwrap_or(&at.key_span).clone(),
            format!("'{other}' does not finish either"),
        );
    }
    diags.push(d);
}

/// Can the run end at this stage?
///
/// The first arm is the one that is not written in the file. `Loop.route`
/// treats `answered` with nowhere to go as the end — *"an agent that has
/// produced its answer and has no further instruction is done, not broken"* —
/// so a stage with no `answered:` line finishes the run without the word `done`
/// appearing anywhere near it. Reading only the literal would refuse loops that
/// end perfectly well, and a false refusal is worse than the hole.
///
/// `used-a-tool` with nowhere to go is deliberately not an ending: it stops the
/// run carrying the message `Loop.route` composed, which is a mistake being
/// reported and not a job being finished.
///
/// The two outcome names below are the exception to this module's rule about
/// naming outcomes (see the note on the walk), and it is worth saying why they
/// have to be here. The walk needs no vocabulary because a *target* is a target
/// whichever line points at it. These two are not about targets: they are the
/// two facts the executing side holds about outcomes — that `answered` ends a
/// run by default (`Loop.route`) and that `too-many-times` is produced only by
/// reaching `at-most:` (`harness._stage_to_run`, and the schema's own help:
/// *"which only happens when `at-most` is reached"*). Neither is derivable from
/// the vocabulary, and leaving the second one out let `too-many-times: done` on
/// a stage with no `at-most:` pass as an ending nothing can arrive at.
fn finishes(stage: &Node) -> bool {
    let Some(then) = stage.get("then").and_then(Node::as_map) else { return true };
    if !then.contains_key(ANSWERED) {
        return true;
    }
    then.iter().any(|(outcome, to)| {
        to.node.as_str().map(str::trim) == Some(DONE)
            && (outcome != TOO_MANY || stage.get("at-most").is_some())
    })
}

/// Does this stage's `then:` send this outcome to the finish line?
fn routes_to_done(stage: &Node, outcome: &str) -> bool {
    stage.get("then").and_then(|t| t.get(outcome)).and_then(Node::as_str).map(str::trim)
        == Some(DONE)
}

/// The `answered:` line inside a stage, to underline the line a person edits
/// rather than the block it sits in.
fn answered_line(stage: &Node) -> Option<&Span> {
    let then = stage.as_map()?.get("then")?;
    Some(&then.node.as_map()?.get(ANSWERED)?.key_span)
}

/// Is this loop written soundly enough that a walk over it means anything?
///
/// Every `false` here is a mistake somebody else already reports at the line the
/// author typed: a stage that is not a set of settings, or a `then:` that is not
/// one line per outcome (`schema/wrong-shape`); an outcome naming a stage that
/// is not there (`schema/no-such-name`, *"'answered' names 'reread', and there
/// is no such entry in `steps:`"*). Walking anyway would produce a second
/// message for the same edit, and it would be the confusing one — see the
/// module note.
fn walkable(steps: &pact_doc::Map) -> bool {
    for stage in steps.values() {
        let Some(fields) = stage.node.as_map() else { return false };
        // A workflow's decision routes by label, and `heard:` by port, one
        // level down (02W §2.3, §2.4).
        for key in ["then", "chooses-between"] {
            let Some(block) = fields.get(key) else { continue };
            let Some(routes) = block.node.as_map() else { return false };
            for outcome in routes.values() {
                let targets: Vec<&Node> = match outcome.node.as_map() {
                    Some(heard) if key == "then" => heard.values().map(|e| &e.node).collect(),
                    _ => vec![&outcome.node],
                };
                for t in targets {
                    let Some(target) = t.as_str().map(str::trim) else { return false };
                    if target != DONE && target != STOP && !steps.contains_key(target) {
                        return false;
                    }
                }
            }
        }
    }
    true
}

/// `'a'`, `'a' or 'b'`, `'a', 'b' or 'c'` — a list a person reads out loud.
fn or_list(names: &[(&String, &Span)]) -> String {
    let quoted: Vec<String> = names.iter().map(|(n, _)| format!("'{n}'")).collect();
    match quoted.split_last() {
        None => String::new(),
        Some((last, [])) => last.clone(),
        Some((last, front)) => format!("{} or {last}", front.join(", ")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn check(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("loops.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        every_stage_is_reachable(&node, &mut d);
        d
    }

    fn only(d: &Diagnostics) -> &Diagnostic {
        assert_eq!(d.items().len(), 1, "one mistake gets one message:\n{}", d.render());
        &d.items()[0]
    }

    /// The worked example's own shape, with the one edit that reproduced the
    /// hole, written out here so the test does not depend on a shared directory.
    const CAREFUL: &str = "
loops:
  careful:
    starts-at: gather
    steps:
      gather:
        does: use-tools
        then:
          used-a-tool: gather
          answered: re-read
      re-read:
        does: check-its-work
        at-most: 2
        then:
          used-a-tool: re-read
          answered: reply
      reply:
        does: answer
        then:
          answered: done
";

    #[test]
    fn a_loop_every_stage_of_which_can_be_walked_to_is_left_alone() {
        let d = check(CAREFUL);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_stage_no_path_from_starts_at_ever_reaches_is_named_at_check_time() {
        // The reproduction: every line is individually correct, `reply` is a
        // real stage, and the two stages the loop exists for never run.
        let d = check(&CAREFUL.replace("starts-at: gather", "starts-at: reply"));
        let e = only(&d);
        assert_eq!(e.rule, "loader/stage-nothing-reaches");
        assert!(e.message.contains("gather") && e.message.contains("re-read"), "{}", e.message);
        assert!(
            e.message.contains("never sends the agent") || e.message.contains("ever sends the agent"),
            "it has to say plainly that nothing goes there: {}",
            e.message
        );
    }

    #[test]
    fn several_unreachable_stages_are_one_diagnostic_and_not_one_each() {
        // `note_companions`/`report_companions` collapse a repeated companion
        // complaint the same way: one thing to change is one thing to read.
        let d = check(&CAREFUL.replace("starts-at: gather", "starts-at: reply"));
        let e = only(&d);
        assert_eq!(e.related.len(), 1, "the second one is a related line, not a second problem");
        assert!(e.related[0].message.contains("re-read"), "{:?}", e.related);
    }

    #[test]
    fn the_caret_lands_on_the_unreachable_stages_own_name() {
        let text = CAREFUL.replace("starts-at: gather", "starts-at: reply");
        let d = check(&text);
        let e = only(&d);
        // `gather:` is the key of the first stage; the span must underline it
        // rather than the whole loop or the whole file.
        let line = text.lines().nth(e.span.line.saturating_sub(1)).unwrap_or("");
        assert!(line.trim_start().starts_with("gather:"), "underlined {line:?}");
    }

    #[test]
    fn the_fix_is_two_lines_the_author_can_literally_type() {
        let d = check(&CAREFUL.replace("starts-at: gather", "starts-at: reply"));
        let e = only(&d);
        assert!(e.fix.contains("`starts-at: gather`"), "{}", e.fix);
        assert!(e.fix.contains("`answered: gather`"), "{}", e.fix);
        assert!(e.fix.contains("delete them"), "and the other honest answer: {}", e.fix);
    }

    #[test]
    fn a_stage_reachable_only_through_too_many_times_is_not_called_unreachable() {
        // `at-most:` reached is its own outcome and it routes, so following it
        // is not optional. Getting this wrong would refuse a correct loop.
        let d = check(
            "
loops:
  careful:
    starts-at: work
    steps:
      work:
        does: use-tools
        at-most: 3
        then:
          used-a-tool: work
          answered: done
          too-many-times: give-up
      give-up:
        does: answer
        then:
          answered: done
",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_then_that_names_no_stage_is_left_to_the_reference_check() {
        // Two messages for one typo, and the second would be the confusing one:
        // "nothing sends the agent to 'reply'" is a strange thing to read when
        // you have just misspelled `reply`.
        let d = check(&CAREFUL.replace("answered: reply", "answered: replyy"));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_then_written_as_a_list_is_left_to_the_shape_check() {
        // `then:` as a list of one-item maps is an ordinary YAML slip. It costs
        // this loop its arrows, so a walk here would call correct stages
        // unreachable on top of the message the author is already getting.
        let d = check(
            "
loops:
  careful:
    starts-at: gather
    steps:
      gather:
        does: use-tools
        then:
          - answered: reply
      reply:
        does: answer
        then:
          answered: done
",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_starts_at_that_names_no_stage_is_left_to_the_reference_check() {
        let d = check(&CAREFUL.replace("starts-at: gather", "starts-at: gathr"));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_shape_that_starts_from_a_ready_made_one_is_not_walked_over_half_a_graph() {
        // `based-on:` brings stages this document does not contain, so a walk
        // here would report the author's own additions as unreachable.
        let d = check(
            "
loops:
  mine:
    based-on: pact:loop/standard
    steps:
      review:
        does: check-its-work
        then:
          answered: done
",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_stage_misnamed_after_the_finish_line_is_not_reported_as_unreachable() {
        // `done` is the finish line, so a stage called that never runs — but
        // that is a different mistake with its own message (`Loop.from_mapping`
        // names it), and saying "nothing sends the agent to 'done'" would send
        // the author looking for a `then:` line to add.
        let d = check(
            "
loops:
  odd:
    starts-at: work
    steps:
      work:
        does: use-tools
        then:
          answered: done
      done:
        does: answer
        then:
          answered: done
",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_workspace_with_no_loops_is_not_walked_at_all() {
        let d = check("agents:\n  desk:\n    name: Desk\n");
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_loop_with_no_stages_and_no_ready_made_shape_is_refused_here_and_not_at_run_time() {
        // `loops.py` refused this and `pact check` said "loaded cleanly", so the
        // author's own tool called the file fine and the run died elsewhere.
        let d = check("loops:\n  mine:\n    description: does nothing\n");
        let e = only(&d);
        assert_eq!(e.rule, "loader/loop-with-nothing-in-it");
        assert!(e.fix.contains("based-on: pact:loop/standard"), "{}", e.fix);
        assert!(e.fix.contains("starts-at:"), "{}", e.fix);
    }

    #[test]
    fn a_loop_no_path_of_which_reaches_done_is_refused_before_it_burns_a_budget() {
        // The measured reproduction, on the worked example's own shape: the last
        // two lines of `reply` read `answered: reply` instead of `answered:
        // done`. Every line is individually correct, `pact check` printed "OK —
        // loaded cleanly (492 settings)", and the run wrote the refund decision
        // and then spent the rest of the budget refusing to hand it over.
        let text = CAREFUL.replace("answered: done", "answered: reply");
        let d = check(&text);
        let e = only(&d);
        assert_eq!(e.rule, "loader/loop-that-never-finishes");
        assert!(e.message.contains("'careful'"), "it must name the loop: {}", e.message);
        assert!(e.message.contains("`done`"), "and the word that is missing: {}", e.message);
        // What it costs, in the terms the author cares about — not "no terminal
        // state". The answer exists; it is the handing over that never happens.
        assert!(
            e.message.contains("goes round again") && e.message.contains("`limits:`"),
            "it must say what actually happens: {}",
            e.message
        );
        assert!(
            e.message.contains("paid for over and over")
                && e.message.contains("ran out rather than that it finished"),
            "and what is lost: {}",
            e.message
        );
    }

    #[test]
    fn the_fix_for_a_loop_that_cannot_end_is_a_line_the_author_changes_not_one_they_add() {
        // Every stage in a loop this rule fires on has already written an
        // `answered:` line — that is what makes it unable to end — so a fix
        // saying "add `answered: done`" would produce a second `answered:` under
        // the same `then:`, which is a YAML error rather than a fix.
        let d = check(&CAREFUL.replace("answered: done", "answered: reply"));
        let e = only(&d);
        assert!(e.fix.starts_with("Change one of these lines to `done`"), "{}", e.fix);
        assert!(e.fix.contains("`answered: done`"), "the line has to be typeable: {}", e.fix);
        // Pointed at the stage that gives the answer, which is where an ending
        // belongs and where somebody looking for the missing one would look.
        assert!(e.fix.contains("under `reply`"), "{}", e.fix);
        // And the escape hatch for the one shape this rule refuses that somebody
        // may have meant: go round a bounded number of times, then stop.
        assert!(e.fix.contains("`at-most: 3`"), "{}", e.fix);
        assert!(e.fix.contains("`too-many-times:`"), "{}", e.fix);
    }

    #[test]
    fn the_caret_lands_on_the_line_that_should_have_said_done() {
        let text = CAREFUL.replace("answered: done", "answered: reply");
        let d = check(&text);
        let e = only(&d);
        let lines: Vec<&str> = text.lines().collect();
        let at = e.span.line.saturating_sub(1);
        assert_eq!(lines[at].trim(), "answered: reply", "underlined {:?}", lines[at]);
        // And the one inside `reply`, not the identical line inside `re-read`:
        // both read `answered: reply` after this edit, and only one of them is
        // the ending that is missing.
        let reply = lines.iter().position(|l| l.trim() == "reply:").expect("the stage is there");
        assert!(at > reply, "underlined the copy in an earlier stage: line {}", e.span.line);
    }

    #[test]
    fn every_other_line_that_could_have_said_done_is_offered_beside_it() {
        // "Change one of these lines" is only a fix if the author can see which
        // lines. Same collapse as the unreachable-stage message: one problem,
        // one sentence, and a pointer at each of the others.
        let d = check(&CAREFUL.replace("answered: done", "answered: reply"));
        let e = only(&d);
        assert_eq!(e.related.len(), 2, "one per other stage: {:?}", e.related);
        let said: Vec<&str> = e.related.iter().map(|r| r.message.as_str()).collect();
        assert!(said.iter().any(|m| m.contains("'gather'")), "{said:?}");
        assert!(said.iter().any(|m| m.contains("'re-read'")), "{said:?}");
    }

    #[test]
    fn a_stage_that_writes_no_answered_line_ends_the_run_so_the_loop_is_left_alone() {
        // `Loop.route`: "an agent that has produced its answer and has no
        // further instruction is done, not broken". This loop never writes the
        // word `done` and ends perfectly well, so reading the literal alone
        // would refuse a correct file — the worst thing this module can do.
        let d = check(
            "
loops:
  quiet:
    starts-at: work
    steps:
      work:
        does: use-tools
        then:
          used-a-tool: work
      reply:
        does: answer
",
        );
        // `reply` is unreachable and gets its own message; what must NOT be here
        // is a claim that this loop cannot end.
        assert!(
            !d.render().contains("loop-that-never-finishes"),
            "a loop that ends by answering was refused:\n{}",
            d.render()
        );
    }

    #[test]
    fn a_loop_that_can_only_finish_by_running_out_of_turns_is_left_alone() {
        // `too-many-times: done` is a real ending — `_stage_to_run` routes a
        // spent stage down that line before it is entered — so counting only
        // `answered: done` would refuse a bounded loop that stops exactly when
        // the author said it should.
        let d = check(
            "
loops:
  bounded:
    starts-at: work
    steps:
      work:
        does: use-tools
        at-most: 3
        then:
          used-a-tool: work
          answered: work
          too-many-times: done
",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn one_stage_that_sends_itself_back_to_itself_is_refused_the_same_way() {
        // The smallest shape of the same mistake, and the commonest one to write
        // by hand: a single stage whose every outcome is itself.
        let d = check(
            "
loops:
  forever:
    starts-at: work
    steps:
      work:
        does: use-tools
        then:
          used-a-tool: work
          answered: work
",
        );
        let e = only(&d);
        assert_eq!(e.rule, "loader/loop-that-never-finishes");
        assert!(e.related.is_empty(), "one stage, nothing else to offer: {:?}", e.related);
        assert!(e.fix.contains("under `work`"), "{}", e.fix);
    }

    #[test]
    fn a_done_behind_a_too_many_times_on_a_stage_with_no_at_most_is_not_an_ending() {
        // The same shape under a different spelling, and the one that would have
        // slipped through a check that only looked for the word `done`:
        // `too-many-times` is produced by reaching `at-most:` and by nothing
        // else, so with no `at-most:` line this outcome never happens and the
        // `done` beside it is a finish nothing can arrive at.
        let d = check(
            "
loops:
  hopeful:
    starts-at: work
    steps:
      work:
        does: use-tools
        then:
          used-a-tool: work
          answered: work
          too-many-times: done
",
        );
        let e = only(&d);
        assert_eq!(e.rule, "loader/loop-that-never-finishes");
        // And it is told what it is looking at, because an author reading "no
        // stage sends the agent to `done`" while looking at a line that says
        // `done` would conclude the tool is broken.
        assert!(
            e.fix.contains("`work` already sends `too-many-times:` to `done`"),
            "the fix has to explain the line the author is looking at: {}",
            e.fix
        );
        assert!(e.fix.contains("add a line like `at-most: 3` to `work`"), "{}", e.fix);
    }

    #[test]
    fn a_done_written_in_a_stage_nothing_reaches_is_told_about_as_the_dead_stage_it_is() {
        // Both things are true here — `finish` never runs, and no stage the run
        // can get to ends — and they are one edit. Saying both would have the
        // two messages arguing about it: one wants an arrow added, the other
        // wants an arrow pointed at `done`. The dead stage is reported, and this
        // asks its question again next time, of the loop that was meant.
        let d = check(
            "
loops:
  stranded:
    starts-at: work
    steps:
      work:
        does: use-tools
        then:
          used-a-tool: work
          answered: work
      finish:
        does: answer
        then:
          answered: done
",
        );
        let e = only(&d);
        assert_eq!(e.rule, "loader/stage-nothing-reaches");
    }

    #[test]
    fn a_loop_that_never_says_which_stage_runs_first_is_refused_with_a_stage_to_type() {
        let d = check(&CAREFUL.replace("    starts-at: gather\n", ""));
        let e = only(&d);
        assert_eq!(e.rule, "loader/loop-with-no-first-stage");
        assert!(e.fix.contains("`starts-at: gather`"), "the fix must be typeable: {}", e.fix);
    }
}
