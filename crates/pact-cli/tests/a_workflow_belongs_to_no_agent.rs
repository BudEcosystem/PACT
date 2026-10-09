//! A workflow is a stage loop that belongs to no agent (02W §1, §8).
//!
//! It calls agents, tools, programs and other workflows, and it has no mind of
//! its own: `model:`, `instructions:`, `loop:`, `team:` and `uses:` are refused
//! on it (WF-1), and so are the four stages that think (WF-2). The other way
//! round, an agent's own loop may not write a workflow's stages, nor a line or
//! an outcome only a workflow's stage reads. A stage is held to the outcomes
//! its `does:` has (02W §2.4), and `items-at-most:` to an `each`.
//!
//! Every test drives the real binary over a copy of
//! `tests/trees/a-workflow-that-calls-and-answers/`, the smallest workflow there
//! is: one call to a tool's action, then the answer.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/a-workflow-that-calls-and-answers"
    ))
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

/// A copy of the tree with `edits` applied (file, text to find, its
/// replacement), and any extra files written.
fn edited(name: &str, edits: &[(&str, &str, &str)], extra: &[(&str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-workflow-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    for (file, text) in extra {
        let p = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
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

const FLOW: &str = "workflows/order-status.yaml";

#[test]
fn the_smallest_workflow_loads_clean_and_is_in_the_document_every_adapter_reads() {
    let (ok, text) = check(&tree());
    assert!(ok, "a call and an answer is a whole workflow:\n{text}");
    // A tree of workflows alone has something to run.
    assert!(!text.contains("nothing-can-run-this"), "{text}");
    let out = pact()
        .args(["show", tree().to_str().unwrap()])
        .output()
        .unwrap();
    let doc: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(
        doc["workflows"]["order-status"]["steps"]["look"]["call"],
        "orders/look-up"
    );
    assert_eq!(doc["workflows"]["order-status"]["starts-at"], "look");
}

#[test]
fn the_trees_digest_moves_when_a_workflow_does() {
    let digest = |root: &Path| {
        let out = pact()
            .args(["discover", root.to_str().unwrap()])
            .output()
            .unwrap();
        let found: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
        let one = if found.is_array() {
            found[0].clone()
        } else {
            found
        };
        one["digest"].as_str().unwrap().to_owned()
    };
    let reworded = edited(
        "digest",
        &[(
            FLOW,
            "Looks up an order and says where it is.",
            "Says where an order is.",
        )],
        &[],
    );
    assert_ne!(
        digest(&tree()),
        digest(&reworded),
        "a workflow is part of what the tree is"
    );
}

#[test]
fn a_workflow_that_writes_a_mind_of_its_own_is_told_to_call_an_agent_once_per_line() {
    for (key, line) in [
        ("model", "model: deepseek-chat\n"),
        ("instructions", "instructions: Be helpful.\n"),
        ("loop", "loop: pact:loop/standard\n"),
        ("team", "team:\n  helper: Helps.\n"),
        ("uses", "uses: [orders]\n"),
    ] {
        let root = edited(
            &format!("mind-{key}"),
            &[(FLOW, "accepts:\n", &format!("{line}accepts:\n"))],
            &[],
        );
        let (ok, text) = check(&root);
        assert!(!ok, "`{key}:` on a workflow must be refused:\n{text}");
        assert!(
            text.contains("rule: loader/a-workflow-with-a-mind-of-its-own"),
            "{text}"
        );
        assert!(text.contains(&format!("writes `{key}:`")), "{text}");
        assert!(
            text.contains("`does: call` and `call: <the agent>`"),
            "{text}"
        );
        // One mistake, one message: not also "not something a workflow can have".
        assert!(
            !text.contains("schema/unknown-field"),
            "{key} was told twice:\n{text}"
        );
        assert_eq!(text.matches("error:").count(), 1, "{text}");
    }
}

#[test]
fn a_stage_that_thinks_is_refused_in_a_workflow() {
    for does in ["think", "use-tools", "check-its-work", "run-code"] {
        let root = edited(
            &format!("thinks-{does}"),
            &[(
                FLOW,
                "  reply:\n    does: answer\n",
                &format!("  reply:\n    does: {does}\n"),
            )],
            &[],
        );
        let (ok, text) = check(&root);
        assert!(!ok, "`does: {does}` in a workflow must be refused:\n{text}");
        assert!(
            text.contains("rule: loader/a-stage-a-workflow-cannot-have"),
            "{text}"
        );
        assert!(text.contains(&format!("'reply' does `{does}`")), "{text}");
        assert!(text.contains("Call an agent that does it"), "{text}");
    }
}

#[test]
fn an_agents_loop_may_not_write_a_workflows_stage() {
    let root = edited(
        "agent-loop",
        &[],
        &[
            (
                "agents/desk/agent.yaml",
                "description: Answers.\ninstructions: Answer.\nloop: mine\n",
            ),
            (
                "loops/mine.yaml",
                "description: One stage.\nstarts-at: go\nsteps:\n  go:\n    does: each\n    over: input.x\n",
            ),
        ],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-stage-an-agent-cannot-have"),
        "{text}"
    );
    assert!(
        text.contains("'go' in the loop 'mine' does `each`"),
        "{text}"
    );
}

#[test]
fn a_call_to_something_that_is_not_here_names_what_is() {
    let root = edited(
        "no-such",
        &[(FLOW, "call: orders/look-up", "call: orders/lookup")],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(text.contains("rule: loader/no-such-name"), "{text}");
    assert!(
        text.contains("Change it to one of: `orders/look-up`"),
        "{text}"
    );
    let root = edited(
        "no-such-agent",
        &[(FLOW, "call: orders/look-up", "call: helper")],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(
        !ok && text.contains("'look' calls 'helper', and this workspace has nothing by that name"),
        "{text}"
    );
}

/// An agent's loop runs inside one model run, which reads no line only a
/// workflow's runtime reads, so each is refused where it is written: a ceiling,
/// a check or an undo the author wrote is never silently missing.
#[test]
fn an_agents_loop_may_not_write_a_line_only_a_workflow_reads() {
    for (key, said, lines) in [
        (
            "limits",
            "`limits:`",
            "    limits:\n      items-at-most: 3\n      when-it-runs-out: stop-and-say-so\n",
        ),
        (
            "checked-by",
            "`checked-by:`",
            "    checked-by:\n      - must-contain: [order]\n",
        ),
        (
            "checks-at-most",
            "`checks-at-most:`",
            "    checks-at-most: 2\n",
        ),
        (
            "undone-by",
            "`undone-by:`",
            "    undone-by: orders/look-up\n",
        ),
        ("over", "`over:`", "    over: input.x\n"),
        (
            "declined",
            "`then.declined:`",
            "    then:\n      answered: done\n      declined: done\n",
        ),
        (
            "heard",
            "`then.heard:`",
            "    then:\n      answered: done\n      heard:\n        fee: done\n",
        ),
    ] {
        let root = edited(
            &format!("agent-line-{key}"),
            &[],
            &[
                (
                    "agents/desk/agent.yaml",
                    "description: Answers.\ninstructions: Answer.\nloop: mine\n",
                ),
                (
                    "loops/mine.yaml",
                    &format!(
                        "description: One stage.\nstarts-at: go\nsteps:\n  go:\n    does: think\n{lines}"
                    ),
                ),
            ],
        );
        let (ok, text) = check(&root);
        assert!(!ok, "`{key}` in an agent's loop must be refused:\n{text}");
        assert!(
            text.contains("rule: loader/a-stage-an-agent-cannot-have"),
            "[{key}] {text}"
        );
        assert!(
            text.contains(&format!("'go' in the loop 'mine' writes {said}")),
            "[{key}] {text}"
        );
        assert!(
            text.contains("write this stage in a workflow under `workflows/`"),
            "[{key}] {text}"
        );
    }
}

/// A stage ends only in the outcomes its `does:` has (02W §2.4). A line for
/// any other is refused, and leads nowhere: a stage only it reaches is a stage
/// nothing reaches, and a `done` under it ends no path.
#[test]
fn a_stage_is_held_to_the_outcomes_its_does_has() {
    let extra = "  spare:\n    does: answer\n";
    for (name, from, to, said) in [
        (
            "answer-then",
            "  reply:\n    does: answer\n",
            "  reply:\n    does: answer\n    then:\n      answered: spare\n",
            "'reply' does `answer` and writes `then:`",
        ),
        (
            "call-declined",
            "      answered: reply\n",
            "      answered: reply\n      declined: spare\n",
            "'look' does `call` and writes `then.declined:`",
        ),
        (
            "call-used-a-tool",
            "      answered: reply\n",
            "      answered: reply\n      used-a-tool: spare\n",
            "'look' does `call` and writes `then.used-a-tool:`",
        ),
        (
            "call-nobody",
            "      answered: reply\n",
            "      answered: reply\n      nobody-answered: spare\n",
            "'look' does `call` and writes `then.nobody-answered:`",
        ),
    ] {
        let root = edited(name, &[(FLOW, from, &format!("{to}{extra}"))], &[]);
        let (ok, text) = check(&root);
        assert!(!ok, "[{name}] {text}");
        assert!(
            text.contains("rule: loader/a-line-this-stage-never-reads"),
            "[{name}] {text}"
        );
        assert!(text.contains(said), "[{name}] {text}");
        // The line leads nowhere, so the stage only it reaches runs never.
        assert!(
            text.contains("rule: loader/stage-nothing-reaches") && text.contains("'spare'"),
            "[{name}] a stage only an impossible outcome reaches is unreachable:\n{text}"
        );
    }
}

#[test]
fn a_decide_has_no_then() {
    let root = edited(
        "decide-then",
        &[(
            FLOW,
            "    then:\n      answered: reply\n  reply:\n",
            "    then:\n      answered: pick\n  pick:\n    does: decide\n    chooses-between:\n      \
             known: reply\n    then:\n      answered: spare\n  spare:\n    does: answer\n  reply:\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(
        text.contains("'pick' does `decide` and writes `then:`"),
        "{text}"
    );
    assert!(
        text.contains("Delete `then:` and name where each label goes"),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/stage-nothing-reaches") && text.contains("'spare'"),
        "a `decide`'s `then:` reaches nothing:\n{text}"
    );
}

/// A `done` under an outcome a stage never ends in ends no path, so WF-38 does
/// not fire for it: only the WF-3 line does.
#[test]
fn an_outcome_that_cannot_happen_ends_no_path() {
    let root = edited(
        "declined-done",
        &[(
            FLOW,
            "      answered: reply\n",
            "      answered: reply\n      declined: done\n",
        )],
        &[],
    );
    let (ok, text) = check(&root);
    assert!(!ok, "{text}");
    assert!(text.contains("then.declined:"), "{text}");
    assert!(!text.contains("a-path-that-answers-nothing"), "{text}");
}

/// `items-at-most:` is a ceiling on an `each`'s items and is read nowhere else:
/// on an agent, a workflow or another stage it is refused, with the fix that
/// moves it.
#[test]
fn items_at_most_is_read_only_on_an_each() {
    let ceiling = "  items-at-most: 3\n  when-it-runs-out: stop-and-say-so\n";
    let refused = |root: PathBuf, said: &str| {
        let (ok, text) = check(&root);
        assert!(!ok, "{text}");
        assert!(
            text.contains("rule: loader/a-line-this-stage-never-reads"),
            "{text}"
        );
        assert!(text.contains(said), "{text}");
        assert!(
            text.contains("Move it under the `limits:` of the `each` stage"),
            "{text}"
        );
    };
    let on_workflow = format!("limits:\n{ceiling}accepts:\n");
    refused(
        edited("on-a-workflow", &[(FLOW, "accepts:\n", &on_workflow)], &[]),
        "The workflow 'order-status' writes `limits.items-at-most:`",
    );
    let on_call = format!(
        "    call: orders/look-up\n    limits:\n{}",
        ceiling.replace("  ", "      ")
    );
    refused(
        edited(
            "on-a-call",
            &[(FLOW, "    call: orders/look-up\n", &on_call)],
            &[],
        ),
        "'look', which does `call`, writes `limits.items-at-most:`",
    );
    let agent = format!("description: Answers.\ninstructions: Answer.\nlimits:\n{ceiling}");
    refused(
        edited("on-an-agent", &[], &[("agents/desk/agent.yaml", &agent)]),
        "The agent 'desk' writes `limits.items-at-most:`",
    );
}
