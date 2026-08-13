//! **A markdown file whose `---` fences hold something that is not settings, at
//! the shipped door.**
//!
//! The loader-level guard for this is
//! `crates/pact-loader/tests/a_sentence_below_the_settings_never_just_disappears.rs`,
//! and it asserts what the document becomes. It cannot assert the sentence the
//! issue is actually about — *"`pact check` said the workspace was fine"* — because
//! it calls `Loader::load` directly and never sees an exit status. That claim was
//! held by no assertion anywhere in this repository:
//!
//! ```text
//! $ grep -rn "front-matter-not-settings" --include=*.rs --include=*.py --include=*.ts .
//! crates/pact-doc/src/markdown.rs                      (the source)
//! crates/pact-loader/tests/a_sentence_below_…rs        (the test's own RULE const)
//! ```
//!
//! — two hits, before this file existed, and neither of them a process.
//!
//! What the seam hid was a real regression. Measured on a one-agent workspace
//! whose `agents/desk/agent.md` was `---` / `- a` / `- b` / `---` / the sentence,
//! against the binary built from the first repair:
//!
//! ```text
//! error: 'agent.md' should be a set of settings, but it is a list.   loader/self-file-not-settings
//! error: An agent must have a 'description'.                         schema/missing-field
//! error: An agent must have 'instructions'.                          schema/missing-field
//! error: 'agent.md' has text below the '---' line, …                 doc/front-matter-not-settings
//! 4 problem(s) found. Nothing was run.
//! ```
//!
//! One mistake, four messages — the first and the last are the same mistake told
//! twice, which `pact_loader`'s own comment forbids (CHK-12). With the same file
//! written with a *sentence* above the line instead of a list it was worse: the
//! author of `agent.md` was told *"'content' is not something an agent can have —
//! fix: Remove it, or use one of: name, description, …"*, about a word they never
//! typed, which is precisely what
//! `an_unfinished_file_is_reported_only_for_what_is_missing.rs` exists to kill and
//! could not see, because every fixture in it is YAML.
//!
//! Every test here runs the real binary over a copy of the **shipped** worked
//! example with one file rewritten, for the reason `a_timer_that_can_never_fire.rs`
//! does: the claim is about what an author is shown and what the process returns,
//! and only the whole pipeline produces those.
//!
//! Mutation, in `crates/pact-doc/src/markdown.rs`: make the refusing arm of
//! `Markdown::into_node` return the parsed fence (`Folded { node: fm, … }`)
//! instead of the prose, and the field-file cases below go to two `error:` lines
//! for one mistake (`'instructions' should be some text, but it is a list`
//! arrives beside the refusal). Delete the `Position::SelfFile` arm of
//! `Loader::read_file` and both self-file cases go to four `error:` lines —
//! measured: `doc/front-matter-not-settings`, two `schema/missing-field`, and
//! `schema/unknown-field` for the invented `'content'`. Treat `Value::Null` front matter as a loss again and
//! `a_fence_pair_holding_nothing_still_loads_clean` fails on the shape six of the
//! nine real-world files in this repository's corpus are written in.

use std::process::Command;

/// The line that must never quietly vanish, and the fence layout every editor
/// writes — a blank line after the closing `---`.
const SENTENCE: &str = "You are a careful refund desk. NEVER approve a refund over 100 USD.";

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
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

/// Copy the shipped example and overwrite one file that is already in it.
fn example_with(name: &str, file: &str, body: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-fence-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    assert!(p.exists(), "fixture drifted: {file} is not in the worked example");
    std::fs::write(&p, body).unwrap();
    dst.to_string_lossy().into_owned()
}

/// Copy the shipped example and rewrite an agent's self file as markdown — the
/// author who writes their agent in markdown rather than YAML, which the
/// authoring guide invites. `agent.yaml` is deleted so the folder still has
/// exactly one file describing itself.
fn example_with_agent_md(name: &str, body: &str) -> String {
    let root = example_with(name, "agents/fraud-checker/agent.yaml", "");
    let dir = std::path::Path::new(&root);
    std::fs::remove_file(dir.join("agents/fraud-checker/agent.yaml")).unwrap();
    std::fs::write(dir.join("agents/fraud-checker/agent.md"), body).unwrap();
    root
}

fn run(cmd: &str, root: &str) -> (bool, String) {
    let out = pact().args([cmd, root]).output().expect("the binary runs");
    let mut text = String::from_utf8_lossy(&out.stdout).into_owned();
    text.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), text)
}

/// Every `error:`/`warning:` block the report writes, one entry per problem.
fn problems(rendered: &str) -> Vec<String> {
    let mut blocks: Vec<Vec<&str>> = Vec::new();
    for line in rendered.lines() {
        if ["error: ", "warning: "].iter().any(|k| line.starts_with(k)) {
            blocks.push(Vec::new());
        }
        if let Some(b) = blocks.last_mut() {
            b.push(line);
        }
    }
    blocks.into_iter().map(|b| b.join("\n")).collect()
}

/// The whole claim about one authored file, through the shipped door.
///
/// * every command that would act on the tree refuses, and says so in its status;
/// * the rule id is printed, so the report is traceable;
/// * the fence mistake is told exactly ONCE, and it is the only thing said about
///   the file;
/// * no setting the author never typed is named, and no fix asks them to remove
///   a line that is not in their file.
fn one_mistake_told_once(root: &str, file: &str, kind: &str) {
    let (ok, text) = run("check", root);
    assert!(!ok, "a file with nowhere to put its settings must be refused:\n{text}");
    assert!(
        text.contains("doc/front-matter-not-settings"),
        "the rule id has to be in the report:\n{text}"
    );

    let mine: Vec<String> = problems(&text).into_iter().filter(|b| b.contains(file)).collect();
    assert_eq!(
        mine.len(),
        1,
        "one mistake, one message (CHK-12) — got {} about {file}:\n{text}",
        mine.len()
    );
    let block = &mine[0];
    assert!(block.contains(kind), "and it says what the fences held ({kind}):\n{block}");
    assert!(
        block.contains("Delete both '---' lines"),
        "and gives a fix a non-coder can carry out:\n{block}"
    );
    assert!(
        !block.contains("'content'"),
        "'content' is the loader's own word for the body of a prose file; the author never \
         typed it:\n{block}"
    );
    assert!(!block.contains("Remove it"), "nothing in their file is named 'content':\n{block}");

    // Nothing acts on a tree that has been refused, and each door says so in the
    // one way a script can read.
    for cmd in ["show", "waits", "card"] {
        let (ok, text) = run(cmd, root);
        assert!(!ok, "`pact {cmd}` must refuse the same tree, not print a document:\n{text}");
    }
}

#[test]
fn a_stray_sentence_above_the_line_of_a_field_file_is_told_once() {
    let root = example_with(
        "field-scalar",
        "agents/fraud-checker/instructions.md",
        &format!("---\nBe brief.\n---\n\n{SENTENCE}\n"),
    );
    one_mistake_told_once(&root, "instructions.md", "some text");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_list_above_the_line_of_a_field_file_is_told_once() {
    // The shape that used to arrive as TWO errors: the refusal, plus
    // `'instructions' should be some text, but it is a list` from the schema,
    // because the parsed fence was planted in the slot the prose was meant for.
    let root = example_with(
        "field-list",
        "agents/fraud-checker/instructions.md",
        &format!("---\n- a\n- b\n---\n\n{SENTENCE}\n"),
    );
    one_mistake_told_once(&root, "instructions.md", "a list");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_stray_sentence_above_the_line_of_a_self_file_is_told_once() {
    // The shape that used to arrive as FOUR errors, one of them naming a setting
    // the author never wrote.
    let root = example_with_agent_md("self-scalar", &format!("---\nBe brief.\n---\n\n{SENTENCE}\n"));
    one_mistake_told_once(&root, "agent.md", "some text");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_list_above_the_line_of_a_self_file_is_told_once() {
    let root = example_with_agent_md("self-list", &format!("---\n- a\n- b\n---\n\n{SENTENCE}\n"));
    one_mistake_told_once(&root, "agent.md", "a list");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_fence_pair_holding_nothing_still_loads_clean() {
    // `---` / `---` is not front matter, so the file is simply its text and there
    // is nothing to refuse. This is the shape six of the nine non-map-front-matter
    // markdown files in this repository's vendored corpus are written in —
    // opencode's own `empty-frontmatter.md` fixture and five pydantic-ai
    // `.github/workflows/shared/*.md` whose fences hold only `#` comments.
    for (name, md) in [
        ("empty-fences", format!("---\n---\n\n{SENTENCE}\n")),
        ("comment-fences", format!("---\n# a note to myself\n---\n\n{SENTENCE}\n")),
    ] {
        let root = example_with(name, "agents/fraud-checker/instructions.md", &md);
        let (ok, text) = run("check", &root);
        assert!(ok, "{name}: nothing is lost here, so nothing is refused:\n{text}");
        // And the words arrive: the one door that prints the document agrees.
        let (ok, doc) = run("show", &root);
        assert!(ok, "{name}: `pact show` prints a tree with no problems:\n{doc}");
        assert!(
            doc.contains("NEVER approve a refund over 100 USD"),
            "{name}: the body of the file is in the document:\n{doc}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn the_shipped_example_is_untouched_by_all_of_this() {
    // Every fixture above is one file away from this, so if this stops loading the
    // measurements above are about something other than the worked example.
    let (ok, text) = run("check", &example());
    assert!(ok, "the shipped example must still load cleanly:\n{text}");
}
