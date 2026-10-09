//! A judged check has a judge (02W §3 WF-34).
//!
//! A `judged:` rule is put to the model `graded-by:` names. In a workflow, a
//! stage checked by one, or a workflow held to checks with one, needs that
//! model on the checks the workflow names; with none, nothing can run the
//! check, and it is refused before anything runs. Over #79's tree
//! (`tests/trees/workflows-79-supervisor/`). (The other half of WF-34, a
//! `program:` check, arrives with the checks that run programs.)

use std::path::{Path, PathBuf};
use std::process::Command;

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/workflows-79-supervisor"
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

fn check(label: &str, edits: &[(&str, &str, &str)], extra: &[(&str, &str)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-judged-{label}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(text.contains(from), "fixture drifted: {from:?} not in {file}");
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    for (file, text) in extra {
        let p = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    }
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

const FLOW: &str = "workflows/first-read.yaml";
const CARD: &str = "      notes: steps.read.notes\n    then: { answered: save }\n";
const JUDGED: &str = "      notes: steps.read.notes\n    checked-by:\n      - judged: Every rating cites its evidence.\n    then: { answered: save }\n";
const SUITE: &str = "description: The first read's checks.\npopulation: authored-enumeration\ngraded-by: qwen2.5-14b-instruct\n";

#[test]
fn a_judged_check_with_no_evals_is_refused() {
    let (ok, text) = check("no-evals", &[(FLOW, CARD, JUDGED)], &[]);
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'card' is checked by a judged rule, and nothing can grade it: the workflow \
             'first-read' names no `evals:`"
        ),
        "{text}"
    );
    assert!(text.contains("rule: loader/a-check-nothing-can-run"), "{text}");
}

#[test]
fn a_judged_check_whose_evals_have_no_grader_is_refused() {
    let (ok, text) = check(
        "no-grader",
        &[
            (FLOW, CARD, JUDGED),
            (FLOW, "kept-for:", "evals: evals\nkept-for:"),
        ],
        &[(
            "evals/suite.yaml",
            "description: The first read's checks.\npopulation: authored-enumeration\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("the checks this workflow names have no `graded-by:` model"),
        "{text}"
    );
}

#[test]
fn a_judged_check_with_a_judge_loads() {
    let (ok, text) = check(
        "graded",
        &[
            (FLOW, CARD, JUDGED),
            (FLOW, "kept-for:", "evals: evals\nkept-for:"),
            ("workspace.yaml", "allow-egress: [tools]", "allow-egress: [tools, llm]"),
        ],
        &[("evals/suite.yaml", SUITE)],
    );
    assert!(!text.contains("loader/a-check-nothing-can-run"), "{text}");
    assert!(ok, "{text}");
}
