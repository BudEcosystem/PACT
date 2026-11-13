//! An agent that decides is given something to decide about.
//!
//! An agent on a `decide`'s rung is handed the workflow's input, the fields of
//! the item it is inside a `for each` of, and the stage's own `bind:` — a
//! later one winning — and of those only what it `accepts:`. The stage's
//! `says:` is the start of its `message`.
//!
//! Until `bind:` could be written on a `decide`, nothing an EARLIER STAGE
//! found could reach the agent; and nothing checked that the agent was given
//! anything at all, so a sorter that took a `message` in a workflow whose
//! input was `subject` and `text` loaded clean and sorted mail it was never
//! shown. Bud Agent Flow found six such trees of its own, and PACT's
//! `workflows-48-invoices` was a seventh.
//!
//! Over a copy of `tests/conformance/trees/triaged-defects/`, which loads
//! clean and is what `tests/conformance/workflows.json` replays.

use std::path::PathBuf;
use std::process::Command;

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/conformance/trees/triaged-defects/defects.pact"
    ))
}

const BOUND: &str = "decide with kind: triage.kind, summary: triage.summary";
const ASSIGNER: &str = "  takes kind: text, summary: text, urgency: text, optional\n";
const RUNG: &str = "      - { agent: assigner }\n";

/// `pact check --deny-warnings` on a copy of the tree with each `(from, to)`
/// edit made once: whether it loaded, and what it said.
fn check(name: &str, edits: &[(&str, &str)]) -> (bool, String) {
    let dir = std::env::temp_dir().join(format!("pact-deciding-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let mut text = std::fs::read_to_string(tree()).unwrap();
    for (from, to) in edits {
        assert!(text.contains(from), "fixture drifted: {from:?}");
        text = text.replacen(from, to, 1);
    }
    std::fs::write(dir.join("defects.pact"), text).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dir.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dir);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

fn refused(name: &str, edits: &[(&str, &str)], rule: &str) -> String {
    let (ok, text) = check(name, edits);
    assert!(!ok, "{name}: expected a refusal:\n{text}");
    assert!(
        text.contains(&format!("rule: {rule}")),
        "{name}: expected `{rule}`:\n{text}"
    );
    text
}

#[test]
fn a_decide_that_binds_what_an_earlier_stage_found_loads_clean() {
    let (ok, text) = check("as-written", &[]);
    assert!(ok, "{text}");
}

#[test]
fn an_agent_that_needs_what_nothing_gives_it_is_refused_and_told_what_is_on_offer() {
    // Without the `bind:`, `kind` still arrives (the workflow's input has
    // one) and `summary` — which only triage knows — never can.
    let text = refused(
        "needs-a-summary",
        &[(BOUND, "decide")],
        "loader/a-deciding-agent-given-nothing",
    );
    assert!(
        text.contains(
            "'assign' asks 'assigner' to decide, and 'assigner' needs 'summary', which nothing \
             here gives it (what is on offer here is `kind`, `report`, `secret`, `urgency`)."
        ),
        "{text}"
    );
    assert!(
        text.contains("so it would decide without it."),
        "{text}"
    );
    assert!(
        text.contains(
            "fix: Fill it under this stage's `bind:` — `summary: <binding>` — or, if 'assigner' \
             can decide without it, mark it `, optional` under its `accepts:`."
        ),
        "{text}"
    );
    // Told once, about the one input: `kind` and `urgency` arrive.
    assert_eq!(text.matches("a-deciding-agent-given-nothing").count(), 1, "{text}");
}

#[test]
fn an_agent_with_no_accepts_takes_a_message_and_is_refused_where_there_is_none() {
    let text = refused(
        "no-accepts",
        &[(BOUND, "decide"), (ASSIGNER, "")],
        "loader/a-deciding-agent-given-nothing",
    );
    assert!(
        text.contains(
            "'assigner' writes no `accepts:`, so it takes a `message` and nothing else — and \
             nothing here is called `message`"
        ),
        "{text}"
    );
    assert!(
        text.contains("It would pick a label having been shown nothing."),
        "{text}"
    );
    assert!(
        text.contains("hand it a message under this stage's `bind:` — `message: <binding>`"),
        "{text}"
    );
}

#[test]
fn a_says_on_the_stage_is_a_message_so_an_agent_with_no_accepts_is_given_one() {
    let (ok, text) = check(
        "says",
        &[
            (BOUND, "decide"),
            (ASSIGNER, ""),
            (RUNG, "      - { agent: assigner }\n    says: Pick the team for the defect.\n"),
        ],
    );
    assert!(ok, "{text}");
}

#[test]
fn an_agent_all_of_whose_inputs_are_optional_is_still_refused_when_none_can_arrive() {
    let text = refused(
        "all-optional",
        &[
            (BOUND, "decide"),
            (ASSIGNER, "  takes area: text, optional, part: text, optional\n"),
        ],
        "loader/a-deciding-agent-given-nothing",
    );
    assert!(
        text.contains(
            "'assign' asks 'assigner' to decide and gives it nothing: 'assigner' accepts \
             `area`, `part`, and what is on offer here is `kind`, `report`, `secret`, `urgency`."
        ),
        "{text}"
    );
}

#[test]
fn a_one_value_item_is_a_message_and_an_agent_that_calls_it_something_else_is_told() {
    // `shelver` takes a `note`. A list of texts has no fields: each text is a
    // `message`, unless the stage says where it goes.
    let text = refused(
        "note-unbound",
        &[("where = decide with note: item", "where = decide")],
        "loader/a-deciding-agent-given-nothing",
    );
    assert!(
        text.contains(
            "'where' asks 'shelver' to decide, and 'shelver' needs 'note', which nothing here \
             gives it (what is on offer here is `message`, `notes`)."
        ),
        "{text}"
    );
}

#[test]
fn a_bound_name_no_agent_on_a_rung_accepts_is_refused_and_the_nearest_offered() {
    let text = refused(
        "nobody-takes-it",
        &[(BOUND, "decide with kind: triage.kind, sumary: triage.summary")],
        "loader/a-call-that-does-not-fit",
    );
    assert!(
        text.contains(
            "'assign' gives `sumary:` to whoever decides ('assigner'), and it accepts no input \
             by that name, so nobody is given it."
        ),
        "{text}"
    );
    assert!(text.contains("fix: Change it to one of: `summary`"), "{text}");
}

#[test]
fn a_bound_value_is_held_to_the_shape_the_agent_takes() {
    let text = refused(
        "a-list-for-a-text",
        &[("where = decide with note: item", "where = decide with note: input.notes")],
        "loader/a-call-that-does-not-fit",
    );
    assert!(
        text.contains(
            "'where' fills `note:` of 'shelver' from 'input.notes', which is `list of text`, \
             and 'shelver' takes `text` there"
        ),
        "{text}"
    );
}

#[test]
fn a_bound_value_is_a_binding_read_where_the_stage_sits() {
    let text = refused(
        "to-nothing",
        &[(BOUND, "decide with kind: triage.kind, summary: triage.sumary")],
        "loader/a-binding-to-nothing",
    );
    assert!(text.contains("'assign' reads 'steps.triage.sumary'"), "{text}");
    // An item is read only inside a `for each`.
    refused(
        "an-item-outside",
        &[(BOUND, "decide with kind: triage.kind, summary: item")],
        "loader/an-item-outside-for-each",
    );
}

#[test]
fn a_bind_on_a_decide_no_agent_reads_is_refused() {
    let text = refused(
        "rules-only",
        &[(RUNG, "      - rules:\n          - choose: powerplant\n")],
        "loader/a-line-this-stage-never-reads",
    );
    assert!(
        text.contains(
            "'assign' writes `bind:`, which is what the agents that decide are given, and none \
             of its rungs asks an agent"
        ),
        "{text}"
    );
    assert!(
        text.contains("fix: Delete it, or add a rung that asks an agent — `- agent: <an agent>`."),
        "{text}"
    );
}

#[test]
fn a_value_hidden_from_the_ai_and_bound_for_the_agent_that_decides_is_warned_about() {
    let (_, text) = check(
        "hidden",
        &[
            (
                "  takes report: text, kind: text, urgency: text, secret: text\n",
                "  takes report: text, kind: text, urgency: text, secret: text\n  hides:\n    input.secret: [the-ai]\n",
            ),
            (BOUND, "decide with kind: triage.kind, summary: input.secret"),
        ],
    );
    assert!(
        text.contains("rule: loader/hidden-from-the-ai-but-handed-to-it"),
        "{text}"
    );
    assert!(
        text.contains("'assign' hands it to the agent 'assigner' as `summary`"),
        "{text}"
    );
}

// ─────────────────────────────────────────── a classifier reads no instruction

const SECOND_OPINION: &str = "  where = decide with message: input.note\n    by:\n      - rules:";
const SAYS_ONLY: &str =
    "  where = decide\n    says: Say which shelf this note goes on.\n    by:\n      - rules:";
const CHECKER: &str = "  description: Gives a second opinion on which shelf a note belongs on.\n";

#[test]
fn a_says_is_a_message_for_an_agent_that_reads_instructions() {
    let (ok, text) = check("says-for-a-reader", &[(SECOND_OPINION, SAYS_ONLY)]);
    assert!(ok, "{text}");
}

#[test]
fn a_says_is_nothing_to_a_classifier_so_one_given_only_that_is_refused() {
    // The same stage, and the second opinion is now a trained classifier: it
    // follows no instruction, so the `says:` is not something it is given.
    let text = refused(
        "says-for-a-classifier",
        &[
            (SECOND_OPINION, SAYS_ONLY),
            (
                CHECKER,
                "  description: Gives a second opinion on which shelf a note belongs on.\n  model: note-classifier\n",
            ),
        ],
        "loader/a-deciding-agent-given-nothing",
    );
    assert!(
        text.contains(
            "'where' asks 'checker' to decide, and 'checker' needs 'message', which nothing \
             here gives it (what is on offer here is `folder`, `note`)."
        ),
        "{text}"
    );
}

#[test]
fn a_rung_whose_agent_is_a_classifier_and_a_language_model_at_once_is_warned_about() {
    let (ok, text) = check(
        "two-kinds",
        &[(
            "  model: note-classifier\n  takes message: text\n",
            "  model: [note-classifier, qwen2.5-7b-instruct]\n  takes message: text\n  instructions: Say which shelf.\n",
        )],
    );
    assert!(!ok, "a warning fails `--deny-warnings`:\n{text}");
    assert!(
        text.contains("rule: loader/a-rung-with-two-kinds-of-reader"),
        "{text}"
    );
    assert!(
        text.contains(
            "'where' asks 'scorer' to decide, and 'scorer' runs on a trained classifier \
             ('note-classifier') and on a language model ('qwen2.5-7b-instruct'). A `model:` \
             list is tried in order only when a call fails, never because an answer was unsure"
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "fix: Make them two agents on two rungs: one on 'note-classifier' with \
             `if-unsure-below:`, then one on 'qwen2.5-7b-instruct' with `instructions:`."
        ),
        "{text}"
    );
}

#[test]
fn it_is_printed_back_as_it_was_written() {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["write", tree().parent().unwrap().to_str().unwrap()])
        .output()
        .expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        text.contains("  assign = decide with kind: triage.kind, summary: triage.summary\n"),
        "{text}"
    );
    assert!(text.contains("    where = decide with note: item\n"), "{text}");
}
