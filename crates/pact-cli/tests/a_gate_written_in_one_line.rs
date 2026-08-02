//! **`pact waits` lists a gate written the short way** — and the field that
//! writes it reads like something a support lead could have typed.
//!
//! §9.4 G14 obliges a conforming runtime to walk `pact waits`, hold a timer per
//! entry, and perform the timeout action when nobody comes back. A gate that
//! stops a call and is absent from that list is a run that parks and is never
//! looked at again — Eve's behaviour, with extra fields. So the one-line gate is
//! either on this list, in this shape, or it is a smaller feature wearing the
//! same name.
//!
//! Everything here runs the real binary against `tests/trees/one-line-gate/`,
//! a workspace whose whole approval surface is one line in one file: no
//! `questions/` folder, no `policies/` folder, no rule.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> String {
    format!("{}/../../tests/trees/one-line-gate", env!("CARGO_MANIFEST_DIR"))
}

fn run(verb: &str) -> (bool, String, String) {
    let out = pact().args([verb, &tree()]).output().expect("runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

#[test]
fn a_workspace_whose_only_gate_is_one_line_loads_cleanly() {
    let (ok, out, err) = run("check");
    assert!(ok, "the short form must be a valid thing to write:\n{out}{err}");
    assert!(out.contains("loaded cleanly"), "and warned about nothing: {out}{err}");
}

#[test]
fn pact_waits_lists_the_gate_written_the_short_way() {
    // The claim, at the surface a runtime author actually reads.
    let (ok, out, err) = run("waits");
    assert!(ok, "{err}");
    let json: serde_json::Value = serde_json::from_str(&out).expect("waits emits JSON");
    let waits = json["waits"].as_array().expect("a list of waits");
    assert_eq!(waits.len(), 1, "one line, one wait: {out}");

    let w = &waits[0];
    assert_eq!(w["reason"], "needs-approval", "{out}");
    assert_eq!(w["agent"], "desk");
    // Everything a scheduler is given to act on. A wait short of any of these is
    // one it cannot time, cannot address, or cannot end.
    assert_eq!(w["answer-within"], "30m");
    assert_eq!(w["deadline-ms"], 1_800_000);
    assert_eq!(w["if-nobody-answers"], "stop-and-say-so");
    assert_eq!(w["asked-of"][0], "whoever-is-running-this");
    // And where the author wrote it — the tool's own file, not a policy's.
    let at = w["declared-at"].as_str().unwrap();
    assert!(at.contains("tools/payments.yaml"), "{at}");
}

#[test]
fn a_scheduler_told_only_to_wait_is_never_told_to_approve() {
    // WAIT-4 at the command line. There has to be no spelling of yes reachable
    // from the short form, or the shorthand is a way to buy a gate that opens
    // itself after half an hour.
    let (_, out, _) = run("waits");
    let json: serde_json::Value = serde_json::from_str(&out).unwrap();
    for w in json["waits"].as_array().unwrap() {
        let action = w["if-nobody-answers"].as_str().unwrap_or("");
        assert!(
            ["stop-and-say-so", "decline", "escalate"].contains(&action),
            "a runtime would do {action:?} when nobody answers"
        );
    }
}

#[test]
fn the_short_gate_costs_one_line_where_the_long_one_costs_three_files() {
    // The measurement the item is about, made against the trees rather than
    // asserted in prose. The long form is a question file, a policy file and a
    // rule inside it; the short form is one line, and the tree proves it by
    // having neither folder on disk.
    let root = std::path::PathBuf::from(tree());
    assert!(!root.join("questions").exists(), "the short form writes no question file");
    assert!(!root.join("policies").exists(), "and no policy file");

    let tool = std::fs::read_to_string(root.join("tools/payments.yaml")).unwrap();
    let gate: Vec<&str> =
        tool.lines().filter(|l| l.trim_start().starts_with("needs-a-person:")).collect();
    assert_eq!(gate.len(), 1, "the whole gate is one line: {gate:?}");
    assert_eq!(gate[0].trim(), "needs-a-person: yes");
}

#[test]
fn the_help_for_the_short_gate_reads_like_something_a_support_lead_could_have_written() {
    // The schema is data and its help is the only documentation an author ever
    // gets. A field carrying jargon, or missing its governance columns, fails
    // the same bar every other field is held to — and this one is read on the
    // day somebody is deciding whether money can move unattended.
    let spec = std::fs::read_to_string(format!(
        "{}/../../spec/schema.yaml",
        env!("CARGO_MANIFEST_DIR")
    ))
    .expect("the specification is a file");
    let doc = pact_doc::parse_yaml(&spec, camino::Utf8Path::new("spec/schema.yaml"))
        .expect("the specification parses");
    let field = doc
        .get("groups")
        .and_then(|g| g.get("action"))
        .and_then(|a| a.get("fields"))
        .and_then(|f| f.get("needs-a-person"))
        .expect(
            "`action.needs-a-person` is not in spec/schema.yaml — apply the field block from \
             this task's needs_wiring. Without it the loader refuses the line and the one-line \
             gate cannot be written at all.",
        );

    for column in ["surface", "tier", "help"] {
        assert!(
            field.get(column).and_then(pact_doc::Node::as_str).is_some(),
            "`needs-a-person` has no `{column}:`, so it is classified by omission"
        );
    }
    assert_eq!(field.get("type").and_then(pact_doc::Node::as_str), Some("yes-no"));

    let help = field.get("help").and_then(pact_doc::Node::as_str).unwrap().to_lowercase();
    for jargon in [
        "boolean", "predicate", "null", "enum", "schema", "validate", "desugar", "field",
        "string", "namespace", "identifier", "invariant", "callback", "hook",
    ] {
        assert!(!help.contains(jargon), "the help leaked '{jargon}':\n{help}");
    }
    // What it must actually say. A support lead reading this has to learn the
    // three things the shorthand decided on their behalf, or the gate is
    // something that happened to them rather than something they wrote.
    assert!(help.contains("yes"), "it has to say what to write:\n{help}");
    for promise in ["thirty minutes", "stops", "silence is never a yes"] {
        assert!(help.contains(promise), "the help never mentions '{promise}':\n{help}");
    }
    assert!(
        help.contains("`policies/`") || help.contains("policies/"),
        "and it has to point at the longer form for anything this cannot say:\n{help}"
    );
}
