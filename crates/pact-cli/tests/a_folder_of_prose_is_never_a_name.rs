//! A folder of prose is a way of writing TEXT. It is never a way of writing a
//! NAME.
//!
//! The Expansion Rule says a directory is a field, and for three fields that is
//! the whole point: `agents/<name>/instructions.md`, a variant's override, and
//! a skill's `SKILL.md` body are the same thing as the line, written where
//! there is room for it. So a map of prose under those has to be accepted.
//!
//! It was accepted under EVERY `type: text` field, because the arm was gated on
//! the type alone. Twenty-two fields carry both `type: text` and `names:` —
//! `agent.loop`, `agent.policy`, `tool.connect`, `evals.graded-by` and the rest
//! — and under each of them a map skipped name resolution entirely. Measured:
//!
//! ```text
//! loop: carefull            error: 'loop' names 'carefull', and there is no
//!                                  such entry in `loops:`
//! loop: {banana: purple}    OK — loaded cleanly
//! ```
//!
//! The typo an author makes is caught. The typo that happens to look like a
//! block is not. One missing predicate turned off a check that was already
//! written, and it turned it off on the twenty-two fields where a wrong name is
//! a rule that does not exist.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn spec() -> pact_schema::Schema {
    const SPEC: &str = include_str!("../../../spec/schema.yaml");
    let mut d = pact_diag::Diagnostics::new();
    let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
    assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
    s
}

/// A one-agent workspace with `line` added to the agent.
fn tree(name: &str, line: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-folder-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Probe\ndescription: A probe workspace.\n")
        .unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        format!("name: Desk\ndescription: Answers questions.\ninstructions: Answer plainly.\n{line}\n"),
    )
    .unwrap();
    dst
}

fn check(root: &std::path::Path) -> String {
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr))
}

#[test]
fn a_field_that_resolves_a_name_refuses_a_folder_of_prose() {
    // Parameterised over every field that carries both, computed rather than
    // listed — a field gaining `names:` later must be covered without anybody
    // remembering to add it here.
    let schema = spec();
    let mut both: Vec<String> = Vec::new();
    for group in schema.groups() {
        for f in &group.fields {
            if matches!(f.ty, pact_schema::Ty::Text) && !f.names.is_empty() {
                both.push(format!("{}.{}", group.name, f.name));
            }
        }
    }
    assert!(
        both.len() > 15,
        "only {} fields resolve a name from text — the sweep is not covering them: {both:?}",
        both.len()
    );

    // Four of them an agent can carry, driven end to end through the binary.
    // `model:` was the fourth until it became `list of text` (02P A2); a block
    // there is still refused, as a list written as a map, and
    // `a_model_list_is_a_fallback_chain.rs` holds its names.
    for field in ["loop", "policy", "context-policy", "model-for-checking"] {
        let root = tree(field, &format!("{field}: {{banana: purple}}"));
        let text = check(&root);
        assert!(
            text.contains("should be some text, but it is a set of settings"),
            "`{field}: {{banana: purple}}` has to be refused, not resolved against nothing:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn no_field_both_takes_a_folder_and_resolves_a_name() {
    // The invariant behind the attribute. A field that means "these words" and
    // a field that means "the thing called this" are different questions, and
    // one field cannot be both without the folder form silently becoming a way
    // to write a name nothing checks.
    let schema = spec();
    let mut wrong: Vec<String> = Vec::new();
    for group in schema.groups() {
        for f in &group.fields {
            if f.may_be_a_folder && !f.names.is_empty() {
                wrong.push(format!("{}.{}", group.name, f.name));
            }
        }
    }
    assert!(
        wrong.is_empty(),
        "these fields say a folder of prose is acceptable AND that the value names \
         something: {wrong:?}"
    );
}

#[test]
fn the_three_fields_the_expansion_rule_exists_for_still_take_a_folder() {
    // The other direction, and the one that matters most: the flagship writes
    // its instructions in a file beside `agent.yaml`, and a tightened gate that
    // broke that would break the Expansion Rule itself.
    let schema = spec();
    let mut folders: Vec<String> = Vec::new();
    for group in schema.groups() {
        for f in &group.fields {
            if f.may_be_a_folder {
                folders.push(format!("{}.{}", group.name, f.name));
            }
        }
    }
    folders.sort();
    assert_eq!(
        folders,
        vec!["agent.instructions", "skill.content", "variant.instructions"],
        "the fields that may be written as a folder have changed"
    );
}

#[test]
fn instructions_written_as_a_folder_of_files_still_loads() {
    let dst = std::env::temp_dir().join(format!("pact-folderform-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk/instructions")).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Probe\ndescription: A probe workspace.\n")
        .unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        "name: Desk\ndescription: Answers questions.\n",
    )
    .unwrap();
    std::fs::write(dst.join("agents/desk/instructions/01-tone.md"), "Answer plainly.\n").unwrap();
    std::fs::write(dst.join("agents/desk/instructions/02-length.md"), "Be brief.\n").unwrap();

    let out = pact().args(["check", dst.to_str().unwrap()]).output().expect("runs");
    assert!(
        out.status.success(),
        "a folder of numbered files is one document in paragraphs:\n{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    let _ = std::fs::remove_dir_all(&dst);
}
