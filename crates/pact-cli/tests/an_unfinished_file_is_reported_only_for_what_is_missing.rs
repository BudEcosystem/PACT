//! A file an author has not started yet must be reported as *not started*, and
//! as nothing else (D13 / O7.3).
//!
//! Leaving a placeholder is how work-in-progress looks: someone creates
//! `agents/fraud-checker/agent.yaml`, types `# TODO`, and comes back to it. That
//! file used to produce **two** errors, and the second named a setting that does
//! not appear anywhere in it:
//!
//! ```text
//! error: An agent must have a 'description'.
//! error: 'content' is not something an agent can have.
//!   fix: Remove it, or use one of: name, description, instructions, …
//! ```
//!
//! The word `content` is the loader's own name for the body of a prose file. An
//! empty document has no body, but it was folded into one anyway, so the author
//! was told to remove a line that is not in their file — in a file whose entire
//! text is `# TODO`, where they can see it is not there. One unfinished file
//! must get one message, and that message must be about what is missing.
//!
//! These run the real binary against a real tree for the reason the sibling
//! caret test does: the defect was in what an author is *shown*, and only the
//! whole pipeline produces that.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example and overwrite one file with `body`, returning the
/// root. Nothing else is passed in and nothing is constructed in memory: the
/// author's own tree is what reaches the loader.
fn example_with(name: &str, file: &str, body: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-unfinished-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    assert!(p.exists(), "fixture drifted: {file} is not in the worked example");
    std::fs::write(&p, body).unwrap();
    dst.to_string_lossy().into_owned()
}

/// Copy the worked example, then rewrite one of its self files under a
/// different extension — the author who writes their agent in markdown rather
/// than YAML. `from` is deleted so the folder still has exactly one file
/// describing itself; otherwise the tree would be refused for having two, and
/// the report under test would never be reached.
fn example_with_self_file_rewritten_as(name: &str, from: &str, to: &str, body: &str) -> String {
    let root = example_with(name, from, "");
    let dir = std::path::Path::new(&root);
    std::fs::remove_file(dir.join(from)).unwrap();
    std::fs::write(dir.join(to), body).unwrap();
    root
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
    let out = pact().args(["check", root]).output().expect("the binary runs");
    let text = String::from_utf8_lossy(&out.stdout).into_owned();
    assert!(!out.status.success(), "an unfinished file must still be refused:\n{text}");
    text
}

/// Every problem the report attributes to `file`, whole. Split on the `error:`
/// and `warning:` headings the renderer writes, so one entry is one problem.
fn problems_in(rendered: &str, file: &str) -> Vec<String> {
    let mut blocks: Vec<Vec<&str>> = Vec::new();
    for line in rendered.lines() {
        if ["error: ", "warning: ", "note: "].iter().any(|k| line.starts_with(k)) {
            blocks.push(Vec::new());
        }
        if let Some(b) = blocks.last_mut() {
            b.push(line);
        }
    }
    blocks
        .into_iter()
        .map(|b| b.join("\n"))
        .filter(|b| b.contains(file))
        .collect()
}

/// The one thing every one of these fixtures must be told, and the one thing it
/// must not be told: the missing field is named, and the body field the author
/// never typed is never mentioned.
fn only_what_is_missing(text: &str, file: &str, must_name: &str) {
    let mine = problems_in(text, file);
    assert!(!mine.is_empty(), "an unfinished file must be reported at all:\n{text}");
    assert!(
        mine.iter().any(|b| b.contains(must_name)),
        "the report has to say what is missing ({must_name}):\n{}",
        mine.join("\n\n")
    );
    for block in &mine {
        assert!(
            !block.contains("'content'"),
            "the author never wrote 'content' — it is the loader's own word for the body \
             of a prose file, and an empty file has no body:\n{block}"
        );
        assert!(
            !block.contains("Remove it"),
            "nothing can be removed from a file that is empty; a fix has to be typeable:\n{block}"
        );
    }
}

#[test]
fn a_file_holding_only_a_note_to_self_is_reported_only_as_unfinished() {
    let root = example_with("todo", "agents/fraud-checker/agent.yaml", "# TODO\n");
    let text = check(&root);
    only_what_is_missing(&text, "agents/fraud-checker/agent.yaml", "'description'");
    assert_eq!(
        problems_in(&text, "agents/fraud-checker/agent.yaml").len(),
        1,
        "one unfinished file is one message:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_file_with_nothing_in_it_at_all_is_reported_only_as_unfinished() {
    // A zero-byte file is what `touch` and "New File" in an editor produce, so
    // it is the first state every file passes through.
    let root = example_with("empty", "agents/fraud-checker/agent.yaml", "");
    let text = check(&root);
    only_what_is_missing(&text, "agents/fraud-checker/agent.yaml", "'description'");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_unfinished_file_written_as_markdown_is_reported_only_as_unfinished() {
    // The same unfinished agent, saved as `.md` instead of `.yaml` — which the
    // authoring guide invites, since a self file may be either. Emptiness
    // arrives differently down that path: an absent YAML document is nothing,
    // while an empty markdown document is a body with no words in it, so the
    // fold this file exists to prevent survived under the other extension.
    //
    // Measured on the worked example with `agents/fraud-checker/agent.yaml`
    // replaced by an empty `agent.md`:
    //
    //     error: An agent must have a 'description'.
    //     error: 'content' is not something an agent can have.
    //       fix: Remove it, or use one of: name, description, instructions, …
    //
    // — the identical invented setting, in a file of zero bytes, reached by
    // renaming the file rather than by writing anything different.
    let root = example_with_self_file_rewritten_as(
        "md",
        "agents/fraud-checker/agent.yaml",
        "agents/fraud-checker/agent.md",
        "",
    );
    let text = check(&root);
    only_what_is_missing(&text, "agents/fraud-checker/agent.md", "'description'");
    assert_eq!(
        problems_in(&text, "agents/fraud-checker/agent.md").len(),
        1,
        "one unfinished file is one message, whichever extension it is saved under:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_unfinished_workspace_file_is_reported_only_as_unfinished() {
    // The same fold applied at the root, where a beginner's very first file is.
    let root = example_with("ws", "workspace.yaml", "# TODO\n");
    let text = check(&root);
    only_what_is_missing(&text, "workspace.yaml", "'name'");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_self_file_that_is_neither_settings_nor_prose_is_told_what_it_should_be() {
    // The fold is gone, so what replaces it has to say something true. A file
    // that IS holding something must not be silently dropped (T7): the author
    // wrote it, and is owed a message about what they wrote rather than about a
    // setting name invented for it.
    let root = example_with("alist", "agents/fraud-checker/agent.yaml", "- one\n- two\n");
    let text = check(&root);
    let mine = problems_in(&text, "agents/fraud-checker/agent.yaml");
    let named = mine
        .iter()
        .find(|b| b.contains("loader/self-file-not-settings"))
        .unwrap_or_else(|| panic!("a file that is not settings must be named as such:\n{text}"));
    assert!(named.contains("agent.yaml"), "it must name the file:\n{named}");
    assert!(named.contains("a list"), "and say what it is instead:\n{named}");
    assert!(
        named.lines().any(|l| l.trim_start().starts_with("fix: ") && l.contains("description:")),
        "O7.3: and give a line the author can type:\n{named}"
    );
    for block in &mine {
        assert!(!block.contains("'content'"), "still no invented setting name:\n{block}");
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_procedure_written_as_plain_prose_is_not_mistaken_for_an_unfinished_file() {
    // The other side of the same branch, and the reason it cannot simply be
    // deleted: a `SKILL.md` with no settings at the top IS its procedure, and
    // that prose is the skill's body. It must go on being read as one — not
    // dropped as if the file were empty, and not reported as the wrong shape.
    // That the prose actually ARRIVES is checked where the document can be
    // inspected, in `pact-loader/tests/a_self_file_contributes_only_what_it_holds`;
    // `pact show` refuses to print a tree that has any problem, and a skill
    // written as bare prose is missing its description by construction.
    let root = example_with(
        "prose",
        "skills/refund-policy/SKILL.md",
        "Check the order date, then decide.\n",
    );
    let text = check(&root);
    let mine = problems_in(&text, "skills/refund-policy/SKILL.md");
    assert_eq!(mine.len(), 1, "only the description is missing:\n{text}");
    assert!(mine[0].contains("'description'"), "and that is what it says:\n{}", mine[0]);
    assert!(
        !mine[0].contains("self-file-not-settings"),
        "prose is a shape a self file is allowed to be:\n{}",
        mine[0]
    );
    let _ = std::fs::remove_dir_all(&root);
}
