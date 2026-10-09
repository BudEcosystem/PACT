//! **P4 (checking half) — a name nothing can be handed to.**
//!
//! The `agent` answer shape lets a field hold the NAME of one of this
//! workspace's agents, so the surrounding system can say *which* agent should
//! take a piece of work. The recursion fuel (`limits.asks-itself-at-most:`)
//! bounds how many times one request may put an agent to work.
//!
//! Those two shipped together and were not joined. Joining them needs a rule,
//! because `teams.rs` legalises a delegation circle only over the STATIC `team:`
//! graph — a cycle is legal iff every agent on it writes its own figure — and an
//! agent named at run time is on no such graph. So the obligation moves from the
//! circle to the agent that can be named:
//!
//! > An agent may be put to work BY VALUE only if it writes its own
//! > `limits.asks-itself-at-most:` figure.
//!
//! The run-time half of that lives in the harness, where the value is. What the
//! CHECKER can say — before anything runs, where the author is — is the case
//! that can never work: a workspace that asks to be handed an agent's name and
//! holds no agent that could be handed over. That is a capability that loads and
//! does nothing, which is the failure this format refuses everywhere else.
//!
//! Fixture: `tests/trees/handing-work-to-a-named-agent/`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> String {
    format!(
        "{}/../../tests/trees/handing-work-to-a-named-agent",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn run(args: &[&str]) -> (Option<i32>, String, String) {
    let out = pact().args(args).output().expect("runs");
    (
        out.status.code(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

fn broken(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-handover-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&tree()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not found in {file}"
        );
        std::fs::write(&p, text.replace(from, to)).unwrap();
    }
    dst.to_string_lossy().into_owned()
}

fn copy_dir(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}

/// The positive control, and it comes first on purpose.
///
/// A workspace that asks for an agent by name AND holds one that may be handed
/// over is exactly right, and says nothing. Every refusal below is meaningless
/// unless this passes.
#[test]
fn a_workspace_that_can_answer_the_question_it_asks_says_nothing() {
    let (code, out, err) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(
        code,
        Some(0),
        "this is the shape the feature is FOR:\n{out}{err}"
    );
}

/// A name nothing can be handed to.
///
/// Take the figure off the only agent that had one, and the dispatcher's
/// `takes-this-one: agent` becomes a line that can never be satisfied by
/// anything in this tree — the run-time rule would refuse every name it was
/// given. That is worth saying before the run rather than during it.
#[test]
fn asking_for_an_agent_no_agent_here_could_be_is_said_out_loud() {
    let dst = broken(
        "no-bottom",
        &[("agents/worker/agent.yaml", "  asks-itself-at-most: 2\n", "")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(0), "a half-written tree still loads:\n{said}");
    assert!(
        said.contains("loader/a-name-nothing-can-be-handed-to"),
        "{said}"
    );
    assert!(
        said.contains("takes-this-one"),
        "name the line that asks:\n{said}"
    );
    assert!(
        said.contains("asks-itself-at-most"),
        "and the line that would make an agent handable:\n{said}"
    );

    let (strict, _, _) = run(&["check", &dst, "--deny-warnings"]);
    assert_eq!(
        strict,
        Some(1),
        "and it has teeth for whoever asks for them"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// An abstract base is never what a name is handed to.
///
/// `base: yes` says the agent never runs — `pact discover` leaves it out,
/// `pact card` has nothing to publish, no `team:` may name it, no port may be
/// answered by it, and no stage may use it. A value naming one at run time
/// would be a sixth door into the same promise, so a base does not count as an
/// agent that could be handed work: a workspace whose only budgeted agent is a
/// base still cannot answer the question it asks.
#[test]
fn a_base_is_not_an_agent_a_name_can_be_handed_to() {
    let dst = broken(
        "base-only",
        &[
            // The `team:` line goes too: a base named as a teammate is already
            // refused by its own door, and this test is about the OTHER one.
            (
                "agents/dispatcher/agent.yaml",
                "team:\n  worker: does the work when nobody was named for this request.\n",
                "",
            ),
            (
                "agents/worker/agent.yaml",
                "description: Does the work.",
                "base: yes\ndescription: Does the work.",
            ),
        ],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert!(
        said.contains("loader/a-name-nothing-can-be-handed-to"),
        "a base carrying the figure is still not something that runs:\n{said}"
    );
    assert_eq!(code, Some(0), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A workspace that never asks for an agent by name is never told about it.
///
/// Additive inertness for the checking half: the warning exists only where the
/// author opted into the shape.
#[test]
fn a_workspace_that_asks_for_no_such_name_is_never_told_about_it() {
    let dst = broken(
        "no-shape",
        &[(
            "agents/dispatcher/agent.yaml",
            "run-inputs:\n  takes-this-one: agent\n",
            "",
        )],
    );
    let (code, out, err) = run(&["check", &dst, "--deny-warnings"]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(0), "{said}");
    assert!(!said.contains("a-name-nothing-can-be-handed-to"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}
