//! The worked example's own shape of thinking (G1), held under test.
//!
//! `examples/refund-desk/loops/careful.yaml` is the first loop in this repo
//! written by an author rather than shipped in `spec/loops/`. That makes it the
//! only evidence that "the loop is data" is true for somebody who is not us —
//! and evidence nobody checks decays, so the checks are here.
//!
//! **What these are, exactly.** They are repo-level guards on THIS example, run
//! by `cargo test`. They are not author-facing checks and they were wrongly
//! described as such for one round: this note claimed to catch typos "at
//! `pact check`, where the person who typed them is", and it did not — a fork
//! of `careful.yaml` into somebody else's workspace got none of it.
//!
//! The author-facing half now exists and is held next door, in
//! `crates/pact-cli/tests/authoring_surface.rs`: the schema carries `names:` on
//! every field whose value is a reference, so `loop: carefull`,
//! `starts-at: gathr`, `then: {answered: repl}`, `at-most: 0` and
//! `then: {finished: …}` are all refused by `pact check` with the file, the
//! line, the names that do exist and a line to type.
//!
//! What is left here is what a generic reference check cannot express, because
//! it is a property of this example rather than of the format: that the stage
//! which doubts a refund cannot also issue one, that a self-routing stage says
//! how many times, and that the shape the file argues for at length is a shape
//! something actually uses.

use camino::Utf8PathBuf;
use pact_diag::Diagnostics;
use pact_doc::{Map, Node};
use pact_loader::Loader;

fn example() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples/refund-desk")
}

fn load() -> (Node, Diagnostics) {
    let root = example();
    let mut d = Diagnostics::new();
    let n = Loader::new(root.clone()).load(&root, &mut d).expect("example loads");
    d.sort();
    (n, d)
}

fn careful(doc: &Node) -> &Node {
    doc.get("loops")
        .expect("loops/ became a `loops:` field, the way context-policies/ does")
        .get("careful")
        .expect("loops/careful.yaml became the `careful` entry")
}

/// The finish line, spelled the way `loops.py` spells it.
const DONE: &str = "done";

fn steps_of(shape: &Node) -> &Map {
    shape.get("steps").and_then(Node::as_map).expect("the loop has `steps:`")
}

fn stage_names(shape: &Node) -> Vec<&str> {
    steps_of(shape).keys().map(String::as_str).collect()
}

#[test]
fn a_folder_of_loops_becomes_the_loops_field_without_anything_being_registered() {
    // The whole claim of the Expansion Rule in one assertion: nothing in the
    // loader knows the word `careful`. A directory name became a top-level key
    // and a filename became the entry inside it, exactly as `context-policies/`
    // did, and the mechanism cost no Rust change at all (invariant E-3).
    let (doc, _) = load();
    let shape = careful(&doc);
    assert_eq!(shape.get("starts-at").and_then(Node::as_str), Some("gather"));
    assert!(
        shape.get("description").and_then(Node::as_str).is_some_and(|s| !s.trim().is_empty()),
        "a shape with no description is one nobody can choose between"
    );
    assert_eq!(stage_names(shape).len(), 3, "gather, re-read, reply");
}

#[test]
fn the_example_still_loads_with_no_errors_and_no_warnings_now_that_it_has_a_loop() {
    // Stated separately from the same assertion in `example_refund_desk.rs`,
    // because the reason differs: there it guards the example, here it guards
    // the claim that a new KIND of document can be added to a workspace without
    // that workspace becoming noisier to load.
    let (_, d) = load();
    assert!(!d.has_errors(), "{}", d.render());
    assert_eq!(d.warning_count(), 0, "{}", d.render());
}

#[test]
fn every_stage_the_loop_routes_to_is_a_stage_that_exists() {
    // The typo that costs most: `answered: repl`. It loads, it validates, and
    // it stops the run dead the first time that branch is taken — which may be
    // long after the author has stopped looking at it.
    let (doc, _) = load();
    let shape = careful(&doc);
    let stages = stage_names(shape);

    let starts_at = shape.get("starts-at").and_then(Node::as_str).unwrap_or_default();
    assert!(
        stages.contains(&starts_at),
        "the loop starts at {starts_at:?}, which is not one of its stages: {stages:?}"
    );

    for (name, stage) in steps_of(shape) {
        let then = stage
            .node
            .get("then")
            .and_then(Node::as_map)
            .unwrap_or_else(|| panic!("stage {name:?} says nothing about where to go next"));
        for (outcome, target) in then {
            let target = target.node.as_str().unwrap_or_default();
            assert!(
                target == DONE || stages.contains(&target),
                "stage {name:?} sends {outcome:?} to {target:?}, which is neither a \
                 stage of this loop ({stages:?}) nor {DONE:?}"
            );
        }
    }
}

#[test]
fn a_stage_only_ends_in_one_of_the_three_outcomes_a_stage_can_end_in() {
    // The vocabulary is closed on purpose (see the module note in loops.py): a
    // fourth outcome would be a fourth dialect of condition for a support lead
    // to learn. A loop that invented one would load fine here and fail at run
    // time, in the other language.
    const OUTCOMES: &[&str] = &["used-a-tool", "answered", "too-many-times"];

    let (doc, _) = load();
    for (name, stage) in steps_of(careful(&doc)) {
        let then = stage.node.get("then").and_then(Node::as_map).unwrap();
        for outcome in then.keys() {
            assert!(
                OUTCOMES.contains(&outcome.as_str()),
                "stage {name:?} routes on {outcome:?}; a stage can only end in one of \
                 {OUTCOMES:?}"
            );
        }
    }
}

#[test]
fn a_stage_may_only_narrow_the_tools_the_agent_already_has() {
    // `Loop.check_against` refuses this before the first model call, in Python.
    // Here it is refused before the run is ever started, against the same two
    // sources that function uses: the agent's `uses:` filtered to things that
    // are actually tools, plus the names of its teammates.
    //
    // `uses:` draws from THREE sections and a stage narrows what the agent
    // already has, so all three count: tools, teammates, and written procedures.
    // The skill half is the one this file got wrong when it was written, in the
    // opposite direction from the way it is wrong now: `refund-policy` was
    // excluded here because a skill "never reaches the tool set", which was true
    // — no skill reached any model at all. It does now, as text in the system
    // message, and naming it on `may-use:` says *read this and touch nothing*.
    let (doc, _) = load();
    let desk = doc.get("agents").and_then(|a| a.get("refund-desk")).expect("the refund desk");

    let uses: Vec<&str> = desk
        .get("uses")
        .and_then(Node::as_list)
        .expect("the agent says what it uses")
        .iter()
        .filter_map(Node::as_str)
        .collect();
    let tools = doc.get("tools").and_then(Node::as_map).expect("tools/");
    let team = desk.get("team").and_then(Node::as_map).expect("team:");

    let skills = doc.get("skills").and_then(Node::as_map);
    let mut offerable: Vec<&str> = uses
        .iter()
        .copied()
        .filter(|u| tools.contains_key(*u) || skills.is_some_and(|s| s.contains_key(*u)))
        .collect();
    offerable.extend(team.keys().map(String::as_str));

    for (name, stage) in steps_of(careful(&doc)) {
        for wanted in stage.node.get("may-use").and_then(Node::as_list).unwrap_or(&[]) {
            let wanted = wanted.as_str().unwrap_or_default();
            assert!(
                offerable.contains(&wanted),
                "stage {name:?} may use {wanted:?}, which this agent cannot offer. \
                 It can offer: {offerable:?}. \
                 fix: add `{wanted}` to the agent's `uses:` list as a tool or a skill, or remove it \
                 from `may-use:` in that stage"
            );
        }
    }
}

#[test]
fn the_stage_that_checks_a_refund_cannot_be_the_stage_that_issues_one() {
    // This is the domain reason the shape exists, so it is the property worth
    // holding rather than the file's shape. A `check-its-work` stage able to
    // reach `payments` is a stage able to spend money while it is still
    // deciding whether spending it is allowed — and the mistake would be one
    // added word in a list, invisible in review.
    //
    // Written as "whatever checks may not spend" rather than "re-read may not
    // use payments", so renaming the stage does not quietly retire the check.
    let (doc, _) = load();
    let mut checked = 0;
    for (name, stage) in steps_of(careful(&doc)) {
        if stage.node.get("does").and_then(Node::as_str) != Some("check-its-work") {
            continue;
        }
        checked += 1;
        let may_use = stage.node.get("may-use").and_then(Node::as_list).unwrap_or_else(|| {
            panic!(
                "stage {name:?} checks the work but names no tools. A stage that names \
                 none and is not `use-tools` is given none, which is safe — but say it \
                 out loud, because the next reader cannot tell the two apart"
            )
        });
        let names: Vec<&str> = may_use.iter().filter_map(Node::as_str).collect();
        assert!(
            !names.contains(&"payments"),
            "stage {name:?} checks a refund decision and can also issue one: {names:?}"
        );
    }
    assert_eq!(checked, 1, "the point of `careful` is the one stage that re-reads the decision");
}

#[test]
fn a_stage_that_can_send_itself_back_to_itself_says_how_many_times() {
    // Without `at-most:`, `used-a-tool: re-read` is a stage that re-enters
    // itself for as long as the model keeps calling a tool. The run-wide
    // `steps-at-most: 12` would stop it eventually, but stopping on the global
    // ceiling reports "ran out of budget" for what is really "checked its own
    // work eleven times" — two things an operator must not be shown alike (T7).
    //
    // `use-tools` is exempt: going round again IS that stage, and `careful`'s
    // `gather` is bounded by the agent's own `steps-at-most`.
    let (doc, _) = load();
    for (name, stage) in steps_of(careful(&doc)) {
        let sends_to_itself = stage
            .node
            .get("then")
            .and_then(Node::as_map)
            .is_some_and(|t| t.values().any(|v| v.node.as_str() == Some(name.as_str())));
        let is_plain_work = stage.node.get("does").and_then(Node::as_str) == Some("use-tools");
        if sends_to_itself && !is_plain_work {
            assert!(
                stage.node.get("at-most").is_some(),
                "stage {name:?} can send itself back to itself and never says how often"
            );
        }
    }
}

#[test]
fn an_agents_loop_line_names_a_shape_this_workspace_actually_declares() {
    // `loop: carefull`, `loop: Careful` and `loop: careful.yaml` are three ways
    // to write a line that used to load, validate, and then fail at run time in
    // another language with the agent already in front of a customer. That is
    // now refused by `pact check` for any workspace, through `names: loops` in
    // the schema — held by
    // `authoring_surface.rs::a_reference_to_something_this_workspace_does_not_have_is_caught_where_the_author_is`.
    //
    // This one stays because it is cheaper and it is about the example: it runs
    // over every agent, so the second agent to adopt a shape is covered by the
    // guard the first one arrived with.
    let (doc, _) = load();
    let shipped: Vec<&str> = doc
        .get("loops")
        .and_then(Node::as_map)
        .map(|m| m.keys().map(String::as_str).collect())
        .unwrap_or_default();

    let agents = doc.get("agents").and_then(Node::as_map).expect("agents/");
    for (who, agent) in agents {
        let Some(named) = agent.node.get("loop").and_then(Node::as_str) else { continue };
        assert!(
            named.starts_with("pact:loop/") || shipped.contains(&named),
            "agent {who:?} thinks in a shape called {named:?}, which this workspace \
             does not have. It declares: {shipped:?}. \
             fix: change that `loop:` line to one of those, or add a file \
             `loops/{named}.yaml` describing the stages"
        );
    }
}

#[test]
fn the_refund_desk_actually_names_the_shape_it_thinks_in() {
    // A shape nothing points at is a document, not a decision. `careful` costs
    // two extra model turns on every request and the file argues for them at
    // length; that argument is only worth reading if something is paying it.
    // This is the line that keeps the worked example a worked example rather
    // than a folder of valid YAML.
    let (doc, _) = load();
    let named = doc
        .get("agents")
        .and_then(|a| a.get("refund-desk"))
        .and_then(|d| d.get("loop"))
        .and_then(Node::as_str);
    assert_eq!(
        named,
        Some("careful"),
        "the worked example ships a shape of thinking that nothing uses. \
         fix: add `loop: careful` to agents/refund-desk/agent.yaml"
    );
}
