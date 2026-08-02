//! `allow-egress:` offers six roles. Until this file existed, five of them were
//! read by nothing.
//!
//! Measured before these tests: every check in the repository asked the same
//! question — `"llm" in allow-egress:` — so `allow-egress: [judge]` behaved in
//! every respect exactly like `allow-egress: []`, and `stt`, `tts`, `embedder`
//! and `reflector` were four words a workspace could write that changed nothing
//! at all. That is a per-role gate that is really one boolean, and it is worse
//! than a boolean: `judge` in particular *reads* as permission to send text off
//! the box to a grader, while the refusal it produced told the author to add
//! `llm`, which grants every other model role at the same time. The only
//! typeable fix the tool offered was to over-grant.
//!
//! What is held here is the property a single boolean cannot have: **the same
//! workspace admits one binding and refuses another, because of which role each
//! one plays.** Every test drives the real binary over a copy of the worked
//! example, so what is under test is the author's own line reaching the check —
//! not an object this file built.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply `edits` as (file, from, to), return the root.
fn edited(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-roles-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(text.contains(from), "fixture drifted: {from:?} not found in {file}");
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

fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().unwrap();
    let said = String::from_utf8_lossy(&out.stdout).to_string()
        + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

const WORKSPACE: &str = "workspace.yaml";
const LEARNING: &str = "learning.yaml";
const AGENT: &str = "agents/refund-desk/agent.yaml";
const SUITE: &str = "evals/suite.yaml";
const POLICY: &str = "context-policies/long-threads.yaml";

/// A row `models/catalog.yaml` serves over somebody's API and nowhere else.
const HOSTED: &str = "claude-opus-5";

#[test]
fn a_workspace_that_lets_the_reflector_out_does_not_thereby_let_the_agent_out() {
    // The worked example's own `learning.yaml` writes two roles on two lines —
    // `execution: { role: llm }` and `reflection: { role: reflector }` — and the
    // schema's help for `role:` promises those words are "the same words
    // `allow-egress:` uses, so the two lines can be read against each other".
    // Nothing read them against each other: both were gated on `llm`, so a team
    // that approved the improver talking to a hosted service got a workspace
    // where it still could not, and the only advice was to approve everything.
    //
    // One grant, two bindings, two different answers. That is the whole claim.
    let allowed = edited(
        "reflector-allowed",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [reflector]"),
            (LEARNING, "reflection: { role: reflector }",
             &format!("reflection: {{ role: reflector, model: {HOSTED} }}")),
        ],
    );
    let (ok, said) = check(&allowed);
    assert!(ok, "the role the workspace granted must be the role that loads:\n{said}");

    let refused = edited(
        "reflector-does-not-cover-the-agent",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [reflector]"),
            (LEARNING, "execution:  { role: llm }",
             &format!("execution:  {{ role: llm, model: {HOSTED} }}")),
        ],
    );
    let (ok, said) = check(&refused);
    assert!(!ok, "one grant must not admit every role:\n{said}");
    assert!(said.contains(HOSTED), "name what is wrong:\n{said}");
    // R56: quote the line the author wrote. The message hardcoded
    // `allow-egress: []` for a round, so a workspace saying otherwise was told
    // its own file says something it does not — and an author who opens the file
    // and sees different stops believing the checker.
    assert!(
        said.contains("allow-egress: [reflector]"),
        "quote the workspace's own line, as written:\n{said}"
    );
    assert!(
        said.contains("or add `llm` to `allow-egress:`"),
        "and ask for the role this binding actually needs:\n{said}"
    );
}

#[test]
fn the_grant_that_names_grading_admits_the_grader_and_nothing_else() {
    // AD-56 is why `judge` is a role of its own: the grader reads every eval
    // case, which is strictly more than the reflector ever sees. A team that
    // wants a hosted grader and nothing else hosted has one line to write —
    // and before this, writing it did nothing whatsoever.
    let allowed = edited(
        "judge-allowed",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [judge]"),
            (SUITE, "graded-by: qwen2.5-14b-instruct", &format!("graded-by: {HOSTED}")),
        ],
    );
    let (ok, said) = check(&allowed);
    assert!(ok, "`judge` must admit the model that grades:\n{said}");

    // And it stops there. The same one-word grant, over the model that writes
    // summaries — which sees the conversation rather than the eval cases, and is
    // a different decision a person has to make.
    let refused = edited(
        "judge-does-not-cover-the-summariser",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [judge]"),
            (POLICY, "summarised-by: qwen2.5-14b-instruct", &format!("summarised-by: {HOSTED}")),
        ],
    );
    let (ok, said) = check(&refused);
    assert!(!ok, "`judge` must not admit the summariser:\n{said}");
    assert!(
        said.contains("allow-egress: [judge]"),
        "quote the workspace's own line, as written:\n{said}"
    );
    assert!(
        said.contains("write `summarised-by: qwen2.5-7b-instruct`"),
        "the fix must be a line the author can type:\n{said}"
    );
}

#[test]
fn the_grant_that_names_the_numbers_admits_that_model_and_no_neighbouring_grant_does() {
    // `embedder` was the last of the six left with no test of its own. A gate
    // nothing measures is one edit away from going back to decoration with
    // every suite still green, which is the shape this whole file exists to
    // refuse — so the role that had no test is exactly the one that needed one.
    //
    // It is reachable from one line an author writes: a `role: embedder`
    // binding under `learning.models`, which is also the only place in the
    // schema any of the six words can be typed by hand.
    let allowed = edited(
        "embedder-allowed",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [embedder]"),
            (LEARNING, "reflection: { role: reflector }",
             &format!("vectors: {{ role: embedder, model: {HOSTED} }}")),
        ],
    );
    let (ok, said) = check(&allowed);
    assert!(ok, "`embedder` must admit the model that turns text into numbers:\n{said}");

    // And no neighbouring grant stands in for it. `judge` is the closest of the
    // six — both are model calls over words that are not the agent's own — and
    // if either word admitted the other, the list would be a boolean again for
    // the pair of them.
    let refused = edited(
        "embedder-not-covered-by-judge",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [judge]"),
            (LEARNING, "reflection: { role: reflector }",
             &format!("vectors: {{ role: embedder, model: {HOSTED} }}")),
        ],
    );
    let (ok, said) = check(&refused);
    assert!(!ok, "`judge` must not admit the embedder:\n{said}");
    // R56: quote the line the author wrote, not the one the message assumed.
    assert!(
        said.contains("allow-egress: [judge]"),
        "quote the workspace's own line, as written:\n{said}"
    );
    assert!(
        said.contains("add `embedder` or `llm` to `allow-egress:`"),
        "name the narrow grant first, and the broad one as the alternative:\n{said}"
    );
}

#[test]
fn a_refusal_asks_for_the_least_grant_that_would_work_and_never_for_all_of_them() {
    // The advice a checker gives is what an author types. For a round every
    // refusal said "add `llm`", whatever was refused — so following the tool's
    // own instructions turned an air-gapped workspace into one where the
    // grader, the summariser, the improver and the agent could all talk out,
    // because somebody wanted one of those four.
    let root = edited(
        "least-grant",
        &[(SUITE, "graded-by: qwen2.5-14b-instruct", &format!("graded-by: {HOSTED}"))],
    );
    let (ok, said) = check(&root);
    assert!(!ok, "a hosted grader under `allow-egress: []` must be refused:\n{said}");
    assert!(
        said.contains("add `judge` or `llm` to `allow-egress:`"),
        "name the narrow grant first, and the broad one as the alternative:\n{said}"
    );
}

#[test]
fn a_voice_recording_is_not_covered_by_permission_for_the_words() {
    // The new refusal, and the reason `stt` and `tts` are separate choices at
    // all. `allow-egress: [llm]` is a decision about a model call. It is not a
    // decision to post a recording of a customer speaking to somebody else's
    // API, and before this file the two were the same line: an agent that
    // `accepts:` a voice message, pinned to a hosted model, under
    // `allow-egress: [llm]`, printed "OK — loaded cleanly" and exited 0.
    //
    // D16 makes audio a first-class v1 modality. If a grant for words carried
    // speech with it, `stt` and `tts` would be exactly the decoration this
    // whole file exists to remove.
    let refused = edited(
        "voice-under-llm",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [llm]"),
            (AGENT, "policy: approvals", &format!("model: {HOSTED}\npolicy: approvals")),
            (AGENT, "  photos: list of images",
             "  photos: list of images\n  recording: a voice message"),
        ],
    );
    let (ok, said) = check(&refused);
    assert!(!ok, "the recording went out under a grant for the words:\n{said}");
    assert!(
        said.contains("accepts: recording: a voice message"),
        "quote the author's own line, so nobody has to go and verify it:\n{said}"
    );
    assert!(
        said.contains("allow-egress: [llm]"),
        "and quote the grant as written — saying it lists nothing would be false:\n{said}"
    );
    assert!(
        said.contains("add `stt` to `allow-egress:`"),
        "ask for the role that names speech:\n{said}"
    );

    // And the escape hatch is one line, which is the whole point of a per-role
    // list: the team decides about the recording separately from the words.
    let allowed = edited(
        "voice-with-stt",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [llm, stt]"),
            (AGENT, "policy: approvals", &format!("model: {HOSTED}\npolicy: approvals")),
            (AGENT, "  photos: list of images",
             "  photos: list of images\n  recording: a voice message"),
        ],
    );
    let (ok, said) = check(&allowed);
    assert!(ok, "a workspace that granted `stt` must load:\n{said}");
}

#[test]
fn the_speech_roles_gate_speech_wherever_the_author_wrote_it() {
    // `stt` and `tts` are reachable from two different lines and both have to
    // mean the same thing, or the roles are per-file rather than per-role.
    //
    // First: the one place an author can write any of the six by hand. A
    // `role: stt` binding in `learning.yaml` was gated on `llm` like everything
    // else, so `allow-egress: [llm]` — a decision about words — silently bound a
    // hosted transcriber.
    let learning = edited(
        "speech-in-learning",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [llm]"),
            (LEARNING, "reflection: { role: reflector }",
             &format!("transcribe: {{ role: stt, model: {HOSTED} }}")),
        ],
    );
    let (ok, said) = check(&learning);
    assert!(!ok, "a grant for the words bound a transcriber:\n{said}");
    assert!(
        said.contains("add `stt` to `allow-egress:`"),
        "ask for the role the author's own `role:` line names:\n{said}"
    );

    // Second: `needs: audio: yes` says only that this agent has to "hear or
    // speak". The author did not say which, so neither does the refusal —
    // demanding both would refuse a transcription agent for a reply it never
    // speaks.
    let needs = edited(
        "speech-in-needs",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [llm]"),
            (AGENT, "policy: approvals", &format!("model: {HOSTED}\npolicy: approvals")),
            ("agents/refund-desk/needs.yaml", "images: yes", "images: yes\naudio: yes"),
        ],
    );
    let (ok, said) = check(&needs);
    assert!(!ok, "`needs: audio: yes` went out under a grant for the words:\n{said}");
    assert!(said.contains("needs: audio: yes"), "quote the author's line:\n{said}");
    assert!(
        said.contains("add `stt` or `tts` to `allow-egress:`"),
        "either grant answers the sentence the author wrote:\n{said}"
    );
}

#[test]
fn the_worked_example_still_loads_and_still_refuses_everything_it_did_before() {
    // The floor. `examples/refund-desk` says `allow-egress: []` and pins no
    // model anywhere, so nothing in it reaches for the network and nothing here
    // may change that. Six roles are only worth having if the empty list still
    // means what it said.
    let (ok, said) = check(&example());
    assert!(ok, "the worked example must load:\n{said}");

    for (name, file, from, to, field) in [
        ("plain-model", AGENT, "policy: approvals",
         "model: claude-opus-5\npolicy: approvals", "model"),
        ("plain-summariser", POLICY, "summarised-by: qwen2.5-14b-instruct",
         "summarised-by: claude-opus-5", "summarised-by"),
        ("plain-grader", SUITE, "graded-by: qwen2.5-14b-instruct",
         "graded-by: claude-opus-5", "graded-by"),
    ] {
        let root = edited(name, &[(file, from, to)]);
        let (ok, said) = check(&root);
        assert!(!ok, "{field} must still be refused under `allow-egress: []`:\n{said}");
        assert!(said.contains("allow-egress: []"), "quote the line as written:\n{said}");
        assert!(
            said.contains(&format!("write `{field}: qwen2.5-7b-instruct`")),
            "the fix must still be a line the author can type:\n{said}"
        );
    }
}
