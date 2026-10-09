//! A self file that would not parse is reported for the syntax, and for nothing
//! else (D13 / O7.3).
//!
//! A directory's **self file** — `agent.yaml`, `_index.yaml`, `workspace.yaml` —
//! supplies that directory's own settings. When it did not parse, the loader
//! handed the schema an EMPTY set of settings, which is the wrong end of the
//! question: an empty set says *"this folder was described, and the description
//! sets nothing"*, when the truth is *"nobody could read the description"*. So
//! the schema went looking for the required fields, found none, and said so.
//!
//! Measured on the worked example — one tab before `- zendesk` in
//! `agents/fraud-checker/agent.yaml`:
//!
//! ```text
//! error: An agent must have a 'description'.
//!   --> examples/refund-desk/agents/fraud-checker:1:1
//!   fix: Add a line: `description: ...`
//!
//! error: This file is not written correctly: tabs disallowed within this context
//!   --> examples/refund-desk/agents/fraud-checker/agent.yaml:4:2
//! ```
//!
//! Line 2 of that same file reads `description: Looks for signs that a refund
//! request is not genuine.` The author is told to add a line they can see on the
//! screen, and the fix, typed, gives them the setting twice. That does not read
//! as their mistake; it reads as the tool being broken. A duplicate key did the
//! same thing, from the other syntax error a hand-written YAML file produces.
//!
//! Both halves are asserted here: the phantom is gone, AND the syntax error
//! itself still arrives with its file, its line and its caret — a fix that
//! removed the second message by removing the first would be worse than the bug.
//!
//! These run the real binary against a real tree, for the reason the sibling
//! `an_unfinished_file_…` test does: the defect was in what an author is
//! *shown*, and only the whole pipeline produces that. Nothing is built in
//! memory; every case starts as bytes on disk, written by the test the way an
//! author's editor would write them.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example and overwrite files with exactly the bytes given,
/// returning the root. The example is otherwise clean — `pact check` on it is a
/// step of `scripts/test-all.sh` — so every problem the report holds afterwards
/// is one these bytes caused.
fn example_with(name: &str, files: &[(&str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-unparsable-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    for (file, body) in files {
        let p = dst.join(file);
        assert!(
            p.exists(),
            "fixture drifted: {file} is not in the worked example"
        );
        std::fs::write(&p, body).unwrap();
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

fn check(root: &str) -> String {
    let out = pact()
        .args(["check", root])
        .output()
        .expect("the binary runs");
    let text = String::from_utf8_lossy(&out.stdout).into_owned();
    assert!(
        !out.status.success(),
        "a file that will not parse must still be refused:\n{text}"
    );
    text
}

/// Every REFUSAL in the report, whole. Split on the headings the renderer
/// writes, so one entry is one problem — the unit the author counts — then keep
/// the errors. Warnings are left out on purpose: they are advice the worked
/// example is free to accumulate, and counting them would make these assertions
/// fail for a reason that has nothing to do with what they are about.
fn errors(rendered: &str) -> Vec<String> {
    let mut blocks: Vec<Vec<&str>> = Vec::new();
    for line in rendered.lines() {
        if ["error: ", "warning: ", "note: "]
            .iter()
            .any(|k| line.starts_with(k))
        {
            blocks.push(Vec::new());
        }
        if let Some(b) = blocks.last_mut() {
            b.push(line);
        }
    }
    blocks
        .into_iter()
        .filter(|b| b.first().is_some_and(|h| h.starts_with("error: ")))
        .map(|b| b.join("\n"))
        .collect()
}

/// The block reporting `rule`, or a failure quoting the whole report.
fn the_one_about<'a>(blocks: &'a [String], rule: &str, text: &str) -> &'a String {
    blocks.iter().find(|b| b.contains(rule)).unwrap_or_else(|| {
        panic!("the syntax mistake itself must still be reported ({rule}):\n{text}")
    })
}

/// What every syntax error owes its reader, checked in one place because both
/// cases owe the same thing: the file, the line, and the character it stopped
/// at. A fix that silenced the phantom by silencing this would be a worse bug
/// than the one it replaced.
fn points_at_the_line(block: &str, file: &str, line: u32) {
    assert!(block.contains(file), "it must name the file:\n{block}");
    assert!(
        block.contains(&format!("{file}:{line}:")),
        "and the line inside it:\n{block}"
    );
    assert!(
        block
            .lines()
            .any(|l| l.trim_start().starts_with(&format!("{line} |"))),
        "and echo that line back:\n{block}"
    );
    // The caret sits under the character the parser stopped at, so its distance
    // from the gutter is whatever that column is — the tab case puts it two
    // spaces along and the duplicate-key case one. Strip the gutter and the
    // padding, and ask only that something points.
    assert!(
        block.lines().any(|l| l
            .trim_start()
            .trim_start_matches('|')
            .trim_start()
            .starts_with('^')),
        "and put a caret under it:\n{block}"
    );
    assert!(
        block.lines().any(|l| l.trim_start().starts_with("fix: ")),
        "O7.3: and give something to do about it:\n{block}"
    );
}

/// The sentence that must not appear. Anything the schema calls absent is a
/// claim about settings nobody could read.
fn nothing_is_reported_missing(blocks: &[String], text: &str) {
    for b in blocks {
        assert!(
            !b.contains("schema/missing-field"),
            "a document nobody could read has no fields to be missing, and this one \
             names a line the author has already written:\n{b}\n\nwhole report:\n{text}"
        );
    }
}

#[test]
fn a_tab_in_a_self_file_is_reported_as_a_tab_and_not_as_a_missing_description() {
    // A tab is what an editor with tab indentation writes, and YAML forbids it.
    // The author's `description:` is on line 2 of this very file.
    let root = example_with(
        "tab",
        &[(
            "agents/fraud-checker/agent.yaml",
            "name: Fraud Checker\n\
             description: Looks for signs that a refund request is not genuine.\n\
             uses:\n\
             \t- zendesk\n",
        )],
    );
    let text = check(&root);
    let blocks = errors(&text);

    nothing_is_reported_missing(&blocks, &text);
    points_at_the_line(
        the_one_about(&blocks, "doc/yaml-syntax", &text),
        "agents/fraud-checker/agent.yaml",
        4,
    );
    assert_eq!(blocks.len(), 1, "one mistake is one message:\n{text}");

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_setting_written_twice_in_a_self_file_is_reported_once_and_not_also_as_absent() {
    // The other syntax error a hand-written file produces: an author edits a
    // line by copying it, and leaves both. It is absurd to be told the setting
    // is missing when the complaint is that it is there twice.
    let root = example_with(
        "dup",
        &[(
            "agents/fraud-checker/agent.yaml",
            "name: Fraud Checker\n\
             description: Looks for signs that a refund request is not genuine.\n\
             description: Looks again.\n\
             uses:\n  - zendesk\n",
        )],
    );
    let text = check(&root);
    let blocks = errors(&text);

    nothing_is_reported_missing(&blocks, &text);
    let dup = the_one_about(&blocks, "doc/duplicate-key", &text);
    points_at_the_line(dup, "agents/fraud-checker/agent.yaml", 3);
    assert!(
        dup.contains("first set here"),
        "and point at the other one too:\n{dup}"
    );
    assert_eq!(blocks.len(), 1, "one mistake is one message:\n{text}");

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_self_file_that_will_not_parse_does_not_hide_a_mistake_in_the_file_beside_it() {
    // The trap in the fix. Marking the folder "nothing is known here" is right
    // about the folder's OWN settings and wrong about everything the folder
    // holds: the entries beside a broken self file parsed perfectly, and their
    // problems are still true. Silencing them would trade the phantom for a
    // second run — fix the tab, discover a fresh error that could have been
    // shown in the same pass — and the loader's whole contract is that an author
    // sees every mistake at once.
    let root = example_with(
        "beside",
        &[
            (
                "workspace.yaml",
                "name: refund-desk\n\
                 workspace-id: 01J8ZK4Q7M2XN5V3B9C1D6F0AE\n\
                 owner:\n\
                 \tsupport-operations\n\
                 allow-egress: []\n",
            ),
            // A real, unrelated mistake: this agent has no description at all.
            (
                "agents/fraud-checker/agent.yaml",
                "name: Fraud Checker\nuses:\n  - zendesk\n",
            ),
        ],
    );
    let text = check(&root);
    let blocks = errors(&text);

    assert!(
        blocks
            .iter()
            .any(|b| b.contains("An agent must have a 'description'.")),
        "the mistake in the file next to the broken one is still true:\n{text}"
    );
    assert!(
        !blocks
            .iter()
            .any(|b| b.contains("A workspace must have a 'name'.")),
        "and the phantom is still gone — line 1 of workspace.yaml is `name: refund-desk`:\n{text}"
    );
    points_at_the_line(
        the_one_about(&blocks, "doc/yaml-syntax", &text),
        "workspace.yaml",
        4,
    );

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_self_file_that_parses_is_still_held_to_every_setting_it_owes() {
    // The guard on the guard. "Say nothing about what did not parse" must not
    // become "say nothing", or the fix would delete the check it is protecting:
    // the same file, missing the same setting, with no syntax error in it, is
    // still reported — and reported at the line the author can act on.
    let root = example_with(
        "still-checked",
        &[(
            "agents/fraud-checker/agent.yaml",
            "name: Fraud Checker\nuses:\n  - zendesk\n",
        )],
    );
    let text = check(&root);
    let blocks = errors(&text);

    let missing = the_one_about(&blocks, "schema/missing-field", &text);
    assert!(
        missing.contains("An agent must have a 'description'."),
        "a description that is genuinely absent is genuinely reported:\n{missing}"
    );
    assert!(
        missing
            .lines()
            .any(|l| l.trim_start().starts_with("fix: ") && l.contains("description:")),
        "O7.3: with a line to type:\n{missing}"
    );
    assert_eq!(blocks.len(), 1, "and still only the one:\n{text}");

    let _ = std::fs::remove_dir_all(&root);
}
