//! End-to-end: a loop whose stages cannot be reached must be refused by the one
//! command a non-technical author actually runs.
//!
//! The hole this closes was found on a copy of `examples/refund-desk`. Editing
//! `loops/careful.yaml` so `starts-at: gather` read `starts-at: reply` left every
//! line in the file individually correct — real stage names, real tools, real
//! outcomes — and `pact check` printed *"OK — ... loaded cleanly (468
//! settings)"* and exited 0, while `gather` and `re-read`, the two stages that
//! file exists for, had become text that never runs.
//!
//! These tests drive the real binary against a real tree for the reason
//! `check_reports_real_mistakes.rs` gives: the thing being tested is the
//! experience, not the unit. The unit tests live beside the walk in
//! `pact-loader/src/reachability.rs`; what is being proved *here* is that the
//! author's own file reaches it — with nothing passed, no object built by hand,
//! and the same exit code a support lead sees.
//!
//! The fixture is written from scratch rather than copied out of
//! `examples/refund-desk`, so that a test about reachability cannot start
//! failing because somebody legitimately edited the worked example.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A three-stage loop of the same shape as the worked example's `careful`:
/// look things up, read the decision back, then reply.
const CAREFUL: &str = "\
description: Look things up, then read the decision back before replying.

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

/// Write a whole workspace whose only interesting content is one loop.
fn workspace(name: &str, loop_text: &str) -> String {
    // The directory name is printed inside every diagnostic, so it is kept free
    // of any word the plain-language test below refuses — a fixture path is a
    // silly reason for that test to go red or, worse, green.
    let dst = std::env::temp_dir().join(format!("pact-fixture-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    std::fs::create_dir_all(dst.join("loops")).unwrap();
    std::fs::write(
        dst.join("workspace.yaml"),
        "name: reachability-fixture\n\
         description: One agent and one loop, for a test about loops.\n\
         owner: nobody\n",
    )
    .unwrap();
    // `instructions:` is here because `agent.instructions` became
    // `required: yes` — an agent with none does nothing, so a workspace of them
    // must not load clean. The fixture used the inline spelling rather than an
    // `instructions.md` beside it only because it is one fewer file to write;
    // the two are the same setting.
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        "name: Desk\ndescription: Decides things.\n\
         instructions: Decide, then say what you decided.\nloop: careful\n",
    )
    .unwrap();
    std::fs::write(dst.join("loops/careful.yaml"), loop_text).unwrap();
    dst.to_string_lossy().into_owned()
}

fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

#[test]
fn a_loop_whose_every_stage_can_be_walked_to_still_loads_cleanly() {
    // The half that matters most: a correct loop must not be refused. A
    // reachability rule that reports a false positive costs an author their
    // trust in every other diagnostic the tool prints.
    let (ok, text) = check(&workspace("clean", CAREFUL));
    assert!(ok, "a correct loop must load:\n{text}");
    assert!(text.contains("loaded cleanly"), "{text}");
}

#[test]
fn a_stage_no_path_from_starts_at_ever_reaches_is_named_at_check_time() {
    // The exact edit that reproduced the hole, through the author's own file
    // and the author's own command. Nothing is constructed here — the loop is
    // read off the tree by the loader, which is the only thing that proves the
    // line the author typed reaches the rule.
    let root = workspace("unreachable", &CAREFUL.replace("starts-at: gather", "starts-at: reply"));
    let (ok, text) = check(&root);
    assert!(!ok, "an unreachable stage must be refused, not reported clean:\n{text}");

    assert!(text.contains("loops/careful.yaml:"), "must name the file and line: {text}");
    assert!(text.contains("gather") && text.contains("re-read"), "must name both stages: {text}");
    assert!(
        text.contains("Nothing in this loop ever sends the agent to"),
        "must say plainly why: {text}"
    );
    // Typeable, both ways out: start there, or route there.
    assert!(text.contains("`starts-at: gather`"), "the fix must be a line to type: {text}");
    assert!(text.contains("`answered: gather`"), "and the other line to type: {text}");
    assert!(text.contains("delete them"), "and the honest third option: {text}");
}

#[test]
fn two_stages_nothing_reaches_are_one_problem_to_fix_and_not_two() {
    // Same collapse `note_companions`/`report_companions` do for a repeated
    // companion complaint: the reader has one edit to make, so they get one
    // sentence and a pointer at the rest.
    let root = workspace("collapsed", &CAREFUL.replace("starts-at: gather", "starts-at: reply"));
    let (_, text) = check(&root);
    assert_eq!(
        text.matches("Nothing in this loop ever sends the agent to").count(),
        1,
        "the sentence must not be repeated per stage:\n{text}"
    );
    assert!(text.contains("is never reached either"), "the rest are related lines: {text}");
    assert!(text.contains("1 problem(s) found"), "and it counts as one problem: {text}");
}

#[test]
fn the_refusal_of_an_unreachable_stage_uses_no_words_a_non_coder_would_have_to_look_up() {
    let root = workspace("plain", &CAREFUL.replace("starts-at: gather", "starts-at: reply"));
    let (_, text) = check(&root);
    let lower = text.to_lowercase();
    for jargon in [
        "reachab", "graph", "node", "traversal", "unreachable", "orphan", "cycle", "vertex",
        "dead code",
    ] {
        assert!(!lower.contains(jargon), "diagnostic leaked '{jargon}':\n{text}");
    }
}
