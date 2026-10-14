//! `steps.<stage>.decided-by` (and `.label`, `.outcome`, `.answered-by`,
//! `.ended`, `.rounds`, `.run`) reads what every stage has besides its answer
//! (02W §2.0), so a callee that answers with a field of one of those names can
//! never have that field read (`pact-loader/src/bindings.rs`,
//! `loader/an-answer-field-a-stage-word-hides`). Before, the binding loaded and
//! read the call stage's own, empty `decided-by` (found by Bud Agent Flow's
//! corpus case #102, whose regional rating workflow answered `decided-by`).

use std::path::PathBuf;
use std::process::Command;

const WORKSPACE: &str = "name: rated\nworkspace-id: 01JEQ8Z3M4N5P6Q7R8S9T0WF02\n\
description: A rating made in a workflow of its own.\nowner: platform\nallow-egress: []\n";
const RATE: &str = "description: Rates a customer.\naccepts:\n  customer: text\nanswers-with:\n  \
rating: text\n  FIELD: text\nstarts-at: reply\nsteps:\n  reply:\n    does: answer\n    bind:\n      \
rating: input.customer\n      FIELD: input.customer\n";
const ASSESS: &str = "description: Says how a customer was rated.\naccepts:\n  customer: text\n\
answers-with:\n  who: text\nstarts-at: rate\nsteps:\n  rate:\n    does: call\n    call: rate\n    \
bind:\n      customer: input.customer\n    then:\n      answered: reply\n  reply:\n    \
does: answer\n    bind:\n      who: steps.rate.FIELD\n";

fn check(field: &str) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-hides-{field}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    for (file, text) in [
        ("workspace.yaml", WORKSPACE.to_string()),
        ("workflows/rate.yaml", RATE.replace("FIELD", field)),
        ("workflows/assess.yaml", ASSESS.replace("FIELD", field)),
    ] {
        let p: PathBuf = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    }
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(&dst)
        .output()
        .unwrap();
    let _ = std::fs::remove_dir_all(&dst);
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

#[test]
fn a_field_with_a_name_of_its_own_is_read() {
    let (ok, said) = check("rated-by");
    assert!(ok, "{said}");
    assert!(!said.contains("a-stage-word-hides"), "{said}");
}

#[test]
fn a_field_a_stage_word_hides_is_refused_where_it_is_read() {
    let (ok, said) = check("decided-by");
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/an-answer-field-a-stage-word-hides"),
        "{said}"
    );
    assert!(said.contains("assess.yaml:18"), "{said}");
    assert!(said.contains("Rename 'decided-by'"), "{said}");
}
