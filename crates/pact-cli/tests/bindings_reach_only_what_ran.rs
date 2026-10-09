//! A workflow's bindings reach only what ran (02W §3 WF-4 to WF-7, WF-9, WF-39,
//! §8 `bindings_reach_only_what_ran`).
//!
//! WF-4: a binding that names nothing is refused, with the nearest three names
//! offered. WF-5: a binding to a stage some path reaches the reader without
//! passing is refused, and the message names the path — unless the input it
//! fills is `, optional`, the escape 02W §2.15 gives. WF-6: a binding to a
//! stage that runs after the reader. WF-7: `item.` outside an `each`. WF-9: a
//! target picked from a binding with no `may-call:`. WF-39: a call that leaves
//! a required input empty, names one its target does not take, or binds a
//! value of another shape.
//!
//! The fixture is #60's interconnection case (02W §5.5), the stages its
//! bindings read, in `tests/trees/an-interconnection-case/`. It loads clean;
//! every test drives the real binary over a mutated copy, and the third of 02W
//! §3's printed examples prints as the design shows it.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree(name: &str) -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/trees")).join(name)
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

const CASE: &str = "an-interconnection-case";
const FLOW: &str = "workflows/interconnection.yaml";
const DRAFTER: &str = "agents/contract-drafter/agent.yaml";

/// A copy of the tree `from` with `edits` applied (file, text to find, its
/// replacement).
fn edited(from: &str, name: &str, edits: &[(&str, &str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-bindings-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(from), &dst);
    for (file, find, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(find),
            "fixture drifted: {find:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(find, to, 1)).unwrap();
    }
    dst
}

fn check(root: &Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

/// Refused, by `rule`, and nothing else is.
fn refused(root: &Path, rule: &str) -> String {
    let (ok, text) = check(root);
    assert!(!ok, "{text}");
    assert!(text.contains(&format!("rule: {rule}")), "{text}");
    assert_eq!(
        text.matches("rule: ").count(),
        1,
        "one mistake, one message:\n{text}"
    );
    text
}

#[test]
fn the_case_loads_clean_with_its_optional_inputs() {
    let (ok, text) = check(&tree(CASE));
    assert!(ok, "{text}");
}

#[test]
fn a_binding_to_a_stage_off_one_path_prints_as_the_design_shows_it() {
    let root = edited(
        CASE,
        "not-optional",
        &[(
            DRAFTER,
            "engineer-upgrade: text, optional",
            "engineer-upgrade: text",
        )],
    );
    let text = refused(&root, "loader/a-binding-to-a-stage-that-may-not-have-run");
    assert!(
        text.contains(
            "error: 'contract' reads 'steps.engineer.upgrade', but on the path through \
             'fast-track' the stage 'engineer' never runs."
        ),
        "{text}"
    );
    assert!(
        text.contains("engineer-upgrade: steps.engineer.upgrade"),
        "{text}"
    );
    assert!(
        text.contains(&format!("| {}^^^^^^^^^^^^^^^^^^^^^^", " ".repeat(24))),
        "the caret is under the binding:\n{text}"
    );
    assert!(
        text.contains(
            "fix: Mark that input `engineer-upgrade: text, optional` on 'contract-drafter', \
             or read it from a stage every path passes."
        ),
        "{text}"
    );
}

#[test]
fn a_binding_that_is_not_an_input_has_no_escape() {
    // `over:`, `call:` and `until:` fill no input, so nothing can be optional.
    let root = edited(
        CASE,
        "no-escape",
        &[(
            FLOW,
            "    bind: { agreement: steps.contract.terms }",
            "    bind: { agreement: steps.contract.terms }\n    version: steps.engineer.because",
        )],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-binding-to-a-stage-that-may-not-have-run"),
        "{text}"
    );
    assert!(
        text.contains("fix: Read it from a stage every path passes."),
        "{text}"
    );
}

#[test]
fn a_binding_to_a_stage_that_is_not_there_offers_the_nearest_three() {
    let root = edited(
        CASE,
        "no-stage",
        &[(FLOW, "steps.engineer.upgrade", "steps.enginer.upgrade")],
    );
    let text = refused(&root, "loader/a-binding-to-nothing");
    assert!(
        text.contains("'contract' reads 'steps.enginer.upgrade', and this workflow has no stage called 'enginer' there."),
        "{text}"
    );
    assert!(
        text.contains("fix: Use one of the names offered: `steps.engineer`,"),
        "{text}"
    );
}

#[test]
fn a_field_a_stage_does_not_answer_with_is_nothing() {
    let root = edited(
        CASE,
        "no-field",
        &[(
            FLOW,
            "steps.gather.existing-der\n",
            "steps.gather.existing\n",
        )],
    );
    let text = refused(&root, "loader/a-binding-to-nothing");
    assert!(
        text.contains("'gather' answers with no 'existing'"),
        "{text}"
    );
    assert!(text.contains("`steps.gather.existing-der`"), "{text}");
}

#[test]
fn an_input_the_workflow_does_not_accept_is_nothing() {
    let root = edited(
        CASE,
        "no-input",
        &[(
            FLOW,
            "bind: { site: input.site }",
            "bind: { site: input.sight }",
        )],
    );
    let text = refused(&root, "loader/a-binding-to-nothing");
    assert!(
        text.contains("the workflow 'interconnection' accepts no 'sight'"),
        "{text}"
    );
    assert!(text.contains("`input.site`"), "{text}");
}

#[test]
fn a_binding_that_starts_nowhere_is_nothing() {
    let root = edited(
        CASE,
        "no-root",
        &[(
            FLOW,
            "bind: { site: input.site }",
            "bind: { site: inputs.site }",
        )],
    );
    let text = refused(&root, "loader/a-binding-to-nothing");
    assert!(
        text.contains("'inputs' is not where a binding starts"),
        "{text}"
    );
    assert!(text.contains("`input.`"), "{text}");
}

#[test]
fn a_shown_value_that_names_nothing_is_refused_where_it_is_written() {
    let root = edited(
        CASE,
        "no-shown",
        &[(
            FLOW,
            "shows: [steps.screen.summary,",
            "shows: [steps.screens.summary,",
        )],
    );
    let text = refused(&root, "loader/a-binding-to-nothing");
    assert!(
        text.contains("The workflow 'interconnection' reads 'steps.screens.summary'"),
        "{text}"
    );
}

#[test]
fn a_binding_to_a_stage_that_runs_later_is_from_later() {
    let root = edited(
        CASE,
        "later",
        &[(
            FLOW,
            "size-kw-ac: input.size-kw-ac }\n    then: { answered: screen }",
            "size-kw-ac: steps.screen.summary }\n    then: { answered: screen }",
        )],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(text.contains("rule: loader/a-binding-from-later"), "{text}");
    assert!(
        text.contains("'power-flow' reads 'steps.screen.summary', and 'screen' runs after it, so there is nothing there yet."),
        "{text}"
    );
    assert!(
        text.contains("fix: Read it from a stage that runs before 'power-flow'."),
        "{text}"
    );
}

#[test]
fn an_item_outside_an_each_is_refused() {
    let root = edited(
        CASE,
        "item",
        &[(
            FLOW,
            "bind: { site: input.site }",
            "bind: { site: item.site }",
        )],
    );
    let text = refused(&root, "loader/an-item-outside-for-each");
    assert!(
        text.contains("'gather' is not inside an `each`, so there is no current item."),
        "{text}"
    );
}

#[test]
fn a_stage_inside_an_each_is_read_only_inside_it() {
    let root = edited(
        "a-workflow-of-every-shape",
        "inside",
        &[(
            "workflows/invoices.yaml",
            "invoice: input.received-on",
            "invoice: steps.read.vendor",
        )],
    );
    let text = refused(&root, "loader/a-binding-to-nothing");
    assert!(
        text.contains("'read' is inside 'each-attachment'"),
        "{text}"
    );
    assert!(text.contains("`steps.each-attachment.<field>`"), "{text}");
}

#[test]
fn a_target_picked_from_a_binding_lists_what_it_may_be() {
    let root = edited(
        CASE,
        "picked",
        &[(
            FLOW,
            "    call: completeness-checker\n",
            "    call: input.site\n",
        )],
    );
    let text = refused(&root, "loader/a-target-picked-from-nowhere");
    assert!(
        text.contains("fix: List every target it may be under `may-call:`"),
        "{text}"
    );
}

#[test]
fn a_call_that_leaves_an_input_empty_does_not_fit() {
    let root = edited(
        CASE,
        "empty",
        &[(FLOW, "    bind: { site: input.site }\n", "")],
    );
    let text = refused(&root, "loader/a-call-that-does-not-fit");
    assert!(
        text.contains("'gather' calls 'feeder-lookup' and leaves its input 'site' empty"),
        "{text}"
    );
    assert!(text.contains("`site: input.site`"), "{text}");
}

#[test]
fn a_call_that_binds_the_wrong_shape_does_not_fit() {
    let root = edited(
        CASE,
        "shape",
        &[(
            FLOW,
            "der-on-feeder: steps.gather.existing-der\n    then: { answered: route }",
            "der-on-feeder: steps.gather.feeder\n    then: { answered: route }",
        )],
    );
    let text = refused(&root, "loader/a-call-that-does-not-fit");
    assert!(
        text.contains("'screen' fills `der-on-feeder:` of 'screener' from 'steps.gather.feeder', which is `text`, and 'screener' takes `number` there"),
        "{text}"
    );
}

#[test]
fn a_call_that_fills_an_input_its_target_does_not_take_does_not_fit() {
    let root = edited(
        CASE,
        "extra",
        &[(
            FLOW,
            "bind: { site: input.site }",
            "bind: { site: input.site, zone: input.site }",
        )],
    );
    let text = refused(&root, "loader/a-call-that-does-not-fit");
    assert!(
        text.contains("'feeder-lookup' takes no input by that name"),
        "{text}"
    );
}

#[test]
fn a_named_shape_is_read_part_by_part() {
    let root = edited(
        CASE,
        "part",
        &[(
            FLOW,
            "bind: { agreement: steps.contract.terms }",
            "bind: { agreement: steps.contract.terms.signer }",
        )],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("the shape 'agreement-terms' has no part 'signer'"),
        "{text}"
    );
    assert!(text.contains("`signers`"), "{text}");
}

#[test]
fn a_shape_made_of_itself_is_refused() {
    let root = edited(
        CASE,
        "itself",
        &[(
            "workspace.yaml",
            "    upgrade: text, optional\n",
            "    upgrade: text, optional\n    earlier: agreement-terms, optional\n",
        )],
    );
    let text = refused(&root, "loader/a-shape-made-of-itself");
    assert!(
        text.contains("The shape 'agreement-terms' is made of itself"),
        "{text}"
    );
}
