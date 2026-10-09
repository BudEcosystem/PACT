//! End-to-end: a model that grades its own answers is said out loud by the one
//! command a non-technical author actually runs.
//!
//! `graded-by:`'s own help says *"Point it at a different model from the one
//! doing the work"* — and for a round nothing compared the two. A workspace could
//! pin `model:` on its agent, write the same id under `graded-by:` in
//! `evals/suite.yaml`, and `pact check` printed *"OK — … loaded cleanly"* over a
//! score the model had given itself. A promise in help text that nothing keeps
//! is the silent degradation T7 names, and this is the last place it can be
//! caught before a number is quoted at somebody.
//!
//! The tests drive the real binary against the **real worked example**, edited by
//! one line, for the reason `money_that_moves_with_nobody_asked.rs` does the
//! same: what is proved is that the author's own two lines reach the rule, with
//! nothing built by hand. A fixture written from scratch would prove the walk
//! works and say nothing about whether the shipped tree's lines arrive.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// What the shipped suite's `graded-by:` says. Written out so that an edit to
/// the worked example fails this test loudly rather than leaving it asserting
/// nothing.
const GRADER: &str = "qwen2.5-14b-instruct";

/// A copy of the worked example whose agent is pinned to `model`.
///
/// The example pins nothing, which is exactly the case this rule stays quiet
/// about — so the one line these tests add is the line an author writes when
/// they DO choose.
fn pinned_to(name: &str, model: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-judge-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);

    let suite = dst.join("evals/suite.yaml");
    let written = std::fs::read_to_string(&suite).expect("the worked example has a suite");
    assert!(
        written.contains(&format!("graded-by: {GRADER}")),
        "fixture drifted: the suite's `graded-by:` is not {GRADER}"
    );

    let p = dst.join("agents/refund-desk/agent.yaml");
    let text = std::fs::read_to_string(&p).expect("the worked example has an agent file");
    assert!(
        !text.contains("\nmodel:"),
        "fixture drifted: the example already pins a model"
    );
    std::fs::write(&p, format!("{text}\nmodel: {model}\n")).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
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

fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

/// Just the paragraph about the judge, out of everything `check` printed.
fn about_the_judge(text: &str) -> String {
    text.split("\n\n")
        .filter(|p| p.contains("loader/judge-is-the-model-under-test"))
        .collect::<Vec<_>>()
        .join("\n\n")
}

#[test]
fn the_worked_example_pins_no_model_so_nothing_is_said_about_its_judge() {
    // The half that matters most: a correct workspace must not be warned. A
    // false positive on the flagship example costs an author their trust in
    // every other line the tool prints — and this one has a specific way of
    // going wrong, since an agent that pins nothing runs on the catalogue's
    // `default:`, which a stricter rule would have compared and reported.
    // Pinning nothing is not choosing, so there is nothing to compare and
    // nothing an author could type.
    let (ok, text) = check(&example());
    assert!(ok, "the worked example must load:\n{text}");
    assert!(
        !text.contains("judge-is-the-model-under-test"),
        "the example pins no model; nothing may be said:\n{text}"
    );
    assert!(text.contains("loaded cleanly"), "{text}");
}

#[test]
fn an_agent_graded_by_the_model_it_runs_on_is_warned_about_at_check_time() {
    let (_, text) = check(&pinned_to("same", GRADER));
    let said = about_the_judge(&text);
    assert!(
        !said.is_empty(),
        "a self-graded suite must be said out loud:\n{text}"
    );

    // Where: the agent's own `model:` line, which is the line most workspaces
    // will change — and the message names the other one, so a reader who wants
    // to move the judge instead knows where it is.
    assert!(
        said.contains("agent.yaml:"),
        "must name the file and line: {said}"
    );
    // What: in plain words, naming the agent, both settings, and the consequence.
    assert!(said.contains("`refund-desk` runs on"), "{said}");
    assert!(said.contains(&format!("`graded-by: {GRADER}`")), "{said}");
    assert!(said.contains("marks its own homework"), "{said}");
    // How: two lines the author can type, one per direction.
    assert!(said.contains("`models/catalog.yaml`"), "typeable: {said}");
    assert!(
        said.contains("write a different `model:`"),
        "typeable: {said}"
    );
}

#[test]
fn two_spellings_of_one_model_are_still_one_model() {
    // `qwen2.5:14b-instruct` is what the runtime calls the row the suite names
    // `qwen2.5-14b-instruct`, and `models/catalog.yaml` publishes both under
    // `also-known-as:`. A check that compared the strings would pass exactly the
    // workspace it exists for, and the author would never learn.
    let (_, text) = check(&pinned_to("alias", "\"qwen2.5:14b-instruct\""));
    let said = about_the_judge(&text);
    assert!(
        !said.is_empty(),
        "an alias of the grader is the grader:\n{text}"
    );
    assert!(said.contains("qwen2.5:14b-instruct"), "{said}");
}

#[test]
fn a_different_model_from_the_grader_is_not_warned_about() {
    // The control. A rule that fired on every pinned model would pass every
    // assertion above and be useless.
    let (ok, text) = check(&pinned_to("different", "llama3.2-1b-instruct"));
    assert!(ok, "{text}");
    assert!(
        about_the_judge(&text).is_empty(),
        "a different model is the whole point of the setting:\n{text}"
    );
}

#[test]
fn grading_yourself_is_a_warning_because_one_machine_may_have_one_model() {
    // Not an error, and the reason is D17. An air-gapped box serving a single
    // set of weights has nothing else to point `graded-by:` at, and refusing to
    // load would leave that workspace with no judge at all — which is worse than
    // a judge somebody has been warned about. What it may never be is silent.
    let (ok, text) = check(&pinned_to("warning-not-error", GRADER));
    let said = about_the_judge(&text);
    assert!(said.starts_with("warning:"), "not an error: {said}");
    assert!(
        ok,
        "a self-graded suite must still load, and exit 0:\n{text}"
    );
    assert!(
        text.contains("loaded with"),
        "counted as a warning, not a problem: {text}"
    );
}

#[test]
fn the_warning_about_the_judge_uses_no_words_a_non_coder_would_have_to_look_up() {
    let (_, text) = check(&pinned_to("plain", GRADER));
    let said = about_the_judge(&text).to_lowercase();
    assert!(!said.is_empty());
    for jargon in [
        "boolean",
        "predicate",
        "null",
        "field type",
        "schema",
        "validate",
        "traversal",
        "cross-document",
        "identifier",
        "namespace",
        "resolve",
        "invariant",
        "enum",
        "alias",
        "llm",
        "inference",
    ] {
        assert!(
            !said.contains(jargon),
            "the sentence leaked '{jargon}':\n{said}"
        );
    }
}
