//! A workflow pattern may read a value table whose name is one of its holes —
//! `over: values.<panel>`, filled `with: {panel: reviewers}` — and the table
//! each workflow made from it names is the one a run reads (02W §2.12, the
//! *Ask a panel* and *Debate* templates). Value tables are resolved before
//! `based-on:` is (a table read by name stays in the document, every other
//! figure is put in place and removed), so the read is followed through the
//! workflows that fill the hole: before this, the pattern's own line was
//! refused as "`values.<panel>` names no value" and the table the filled
//! workflow reads was dropped as a figure nothing uses.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

const WORKSPACE: &str = "name: panels
description: Two panels made from one pattern.
owner: tests
allow-egress: []
shapes:
  seat:
    seat: text
    member: agent
";

const PATTERN: &str = "expects:
  panel:
    shape: text
    help: the value table naming who sits on the panel
description: Asks each seat of <panel> the question and keeps every answer.
accepts:
  question: text
answers-with:
  answers: list of text
starts-at: ask
steps:
  ask:
    does: each
    over: values.<panel>
    identified-by: [seat]
    limits:
      items-at-most: 5
      when-it-runs-out: stop-and-say-so
    combines-by:
      answer: keep-all
    starts-at: one
    steps:
      one:
        does: call
        call: member
        bind:
          question: input.question
          seat: item.seat
    then:
      answered: reply
  reply:
    does: answer
    bind:
      answers: steps.ask.answer
";

const MEMBER: &str = "description: Answers from one seat.
instructions: Answer from the seat you are given.
accepts:
  question: text
  seat: text
answers-with:
  answer: text
";

fn table(seats: &[&str]) -> String {
    let rows: String = seats
        .iter()
        .map(|s| format!("  - {{ seat: {s}, member: member }}\n"))
        .collect();
    format!("description: Who sits on this panel.\nshape: table\nrows-are: seat\nvalue:\n{rows}")
}

/// A tree with the pattern, the given workflow files and tables, written fresh.
fn tree(name: &str, flows: &[(&str, &str)], tables: &[(&str, &[&str])]) -> PathBuf {
    tree_of(PATTERN, name, flows, tables)
}

/// The same pattern with its holes and table name written differently: the
/// `expects:` block and the name `over:` reads (`values.<team>-seats`).
fn pattern_reading(expects: &str, over: &str) -> String {
    let declared = "expects:\n  panel:\n    shape: text\n    help: the value table naming who sits on the panel\n";
    PATTERN
        .replacen(declared, expects, 1)
        .replace("of <panel> the question", "the question")
        .replace("values.<panel>", over)
}

fn tree_of(
    pattern: &str,
    name: &str,
    flows: &[(&str, &str)],
    tables: &[(&str, &[&str])],
) -> PathBuf {
    static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let n = N.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dst = std::env::temp_dir().join(format!("pact-panel-{name}-{n}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    let write = |rel: &str, text: &str| {
        let p = dst.join(rel);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    };
    write("workspace.yaml", WORKSPACE);
    write("workflows/ask-a-panel.yaml", pattern);
    write("agents/member/agent.yaml", MEMBER);
    for (flow, text) in flows {
        write(&format!("workflows/{flow}.yaml"), text);
    }
    for (name, seats) in tables {
        write(&format!("values/{name}.yaml"), &table(seats));
    }
    dst
}

/// `pact check` on the tree, with warnings refused when `strict`.
fn check(root: &Path, strict: bool) -> (bool, String) {
    let mut args = vec!["check", root.to_str().unwrap()];
    if strict {
        args.insert(1, "--deny-warnings");
    }
    let out = pact().args(args).output().expect("runs");
    let mut said = String::from_utf8_lossy(&out.stdout).into_owned();
    said.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), said)
}

fn shown(root: &Path) -> serde_json::Value {
    let out = pact()
        .args(["show", root.to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(&out.stdout).expect("JSON")
}

#[test]
fn each_workflow_made_from_the_pattern_reads_the_table_it_names() {
    let root = tree(
        "two",
        &[
            (
                "risk",
                "based-on: ask-a-panel\nwith:\n  panel: risk-seats\n",
            ),
            (
                "style",
                "based-on: ask-a-panel\nwith:\n  panel: style-seats\n",
            ),
        ],
        &[
            ("risk-seats", &["optimist", "skeptic"]),
            ("style-seats", &["editor"]),
        ],
    );
    let (ok, said) = check(&root, true);
    assert!(
        ok,
        "a hole in a table's name is filled by each workflow:\n{said}"
    );
    let doc = shown(&root);
    assert_eq!(
        doc["workflows"]["risk"]["steps"]["ask"]["over"],
        "values.risk-seats"
    );
    assert_eq!(
        doc["workflows"]["style"]["steps"]["ask"]["over"],
        "values.style-seats"
    );
    assert!(
        doc["workflows"].get("ask-a-panel").is_none(),
        "the pattern is gone"
    );
    // Both tables are read by name, so both stay in the document for a run.
    let kept = doc["values"]
        .as_object()
        .expect("the tables a run reads stay");
    assert_eq!(kept["risk-seats"]["value"].as_array().unwrap().len(), 2);
    assert_eq!(kept["style-seats"]["value"].as_array().unwrap().len(), 1);
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_table_the_caller_names_and_nobody_wrote_is_refused_where_the_caller_named_it() {
    let root = tree(
        "missing",
        &[("risk", "based-on: ask-a-panel\nwith:\n  panel: risk-seat\n")],
        &[("risk-seats", &["optimist"])],
    );
    let (ok, said) = check(&root, true);
    assert!(!ok, "{said}");
    assert!(said.contains("loader/a-binding-to-nothing"), "{said}");
    assert!(
        said.contains("`values.risk-seat` names no value"),
        "the message names what the caller wrote:\n{said}"
    );
    assert!(
        said.contains("workflows/risk.yaml"),
        "the caret is on the caller's line:\n{said}"
    );
    assert!(
        said.contains("`values.risk-seats`"),
        "and the fix offers the nearest:\n{said}"
    );
    assert!(
        !said.contains("ask-a-panel.yaml"),
        "the pattern's own line is not the mistake:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_pattern_built_on_the_pattern_forwards_the_hole_to_its_own_caller() {
    let middle = "based-on: ask-a-panel\nexpects:\n  seats:\n    shape: text\n    help: the table\n\
                  with:\n  panel: <seats>\n";
    let root = tree(
        "forwarded",
        &[
            ("panel-of-two", middle),
            (
                "risk",
                "based-on: panel-of-two\nwith:\n  seats: risk-seats\n",
            ),
        ],
        &[("risk-seats", &["optimist", "skeptic"])],
    );
    // The middle pattern restates `expects:`, which PACT warns about on purpose.
    let (ok, said) = check(&root, false);
    assert!(ok, "{said}");
    let doc = shown(&root);
    assert_eq!(
        doc["workflows"]["risk"]["steps"]["ask"]["over"],
        "values.risk-seats"
    );
    assert!(
        doc["values"]["risk-seats"].is_object(),
        "the table is kept for the run"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_hole_inside_a_longer_table_name_is_filled_as_the_pattern_fills_it() {
    let pattern = pattern_reading(
        "expects:\n  team:\n    shape: text\n    help: the team whose seats sit\n",
        "values.<team>-seats",
    );
    let root = tree_of(
        &pattern,
        "inside",
        &[("risk", "based-on: ask-a-panel\nwith:\n  team: risk\n")],
        &[("risk-seats", &["optimist", "skeptic"])],
    );
    let (ok, said) = check(&root, true);
    assert!(
        ok,
        "`values.<team>-seats` with team risk reads risk-seats:\n{said}"
    );
    let doc = shown(&root);
    assert_eq!(
        doc["workflows"]["risk"]["steps"]["ask"]["over"],
        "values.risk-seats"
    );
    assert_eq!(
        doc["values"]["risk-seats"]["value"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
    // And a name the filled text does not match is refused at the caller.
    let wrong = tree_of(
        &pattern,
        "inside-wrong",
        &[("risk", "based-on: ask-a-panel\nwith:\n  team: risky\n")],
        &[("risk-seats", &["optimist"])],
    );
    let (ok, said) = check(&wrong, true);
    assert!(!ok, "{said}");
    assert!(
        said.contains("`values.risky-seats` names no value"),
        "{said}"
    );
    assert!(said.contains("workflows/risk.yaml"), "{said}");
    let _ = std::fs::remove_dir_all(&root);
    let _ = std::fs::remove_dir_all(&wrong);
}

#[test]
fn two_holes_in_a_table_name_are_both_filled() {
    let pattern = pattern_reading(
        "expects:\n  team:\n    shape: text\n    help: the team\n  \
         size:\n    shape: text\n    help: which of its panels\n",
        "values.<team>-<size>",
    );
    let root = tree_of(
        &pattern,
        "two-holes",
        &[
            (
                "risk",
                "based-on: ask-a-panel\nwith:\n  team: risk\n  size: small\n",
            ),
            (
                "style",
                "based-on: ask-a-panel\nwith:\n  team: style\n  size: large\n",
            ),
        ],
        &[
            ("risk-small", &["optimist"]),
            ("style-large", &["editor", "proofreader", "designer"]),
        ],
    );
    let (ok, said) = check(&root, true);
    assert!(ok, "both holes are filled by each caller:\n{said}");
    let doc = shown(&root);
    assert_eq!(
        doc["workflows"]["risk"]["steps"]["ask"]["over"],
        "values.risk-small"
    );
    assert_eq!(
        doc["workflows"]["style"]["steps"]["ask"]["over"],
        "values.style-large"
    );
    assert_eq!(
        doc["values"]["style-large"]["value"]
            .as_array()
            .unwrap()
            .len(),
        3
    );
    let _ = std::fs::remove_dir_all(&root);
}
