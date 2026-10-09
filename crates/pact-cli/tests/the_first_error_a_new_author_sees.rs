//! The very first sentence PACT ever says to somebody has to be typeable
//! without guessing (D13, O7.3).
//!
//! # What was measured
//!
//! The smallest tree a person makes on their first attempt: a folder, an
//! `agents/hello/` inside it, and one `agent.yaml` holding `description: says
//! hello`. Nothing else — because `workspace.yaml` is a file you only know to
//! write once somebody has told you about it. `pact check` opened with
//!
//! ```text
//! error: A workspace must have a 'name'.
//!   --> /tmp/hello:1:1
//!   fix: Add a line: `name: ...` — what this whole system is called
//! ```
//!
//! Three things are wrong with that, and all three land on the same reader at
//! the same moment:
//!
//! 1. the arrow names a **directory** and gives it a line and a column, so
//!    whatever the reader opens, it is not the thing the message means;
//! 2. no excerpt prints, because there is nothing to quote — correct, and it
//!    leaves the arrow as the only clue about where;
//! 3. `Add a line` does not say **to which file**, and cannot, because the file
//!    does not exist yet. That is the whole difficulty: the answer is *make a
//!    file*, and "add a line" is not a sentence that can carry it.
//!
//! `loader/not-a-pact-folder` already says exactly the right thing — *"Create
//! `<path>/workspace.yaml` with one line — `name: …`"* — but only for a folder
//! with no `agents/` in it. Making `agents/` is the first thing anybody does,
//! and it moves them out of that message and into this one.
//!
//! These run the real binary against a real tree, for the reason the sibling
//! caret and unfinished-file tests do: the defect is in what an author is
//! *shown*, and only the whole pipeline produces that.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A fresh empty directory of its own, named after the test using it so the
/// tests can run in parallel.
fn tree(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("pact-first-error-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn write(root: &std::path::Path, rel: &str, body: &str) {
    let p = root.join(rel);
    std::fs::create_dir_all(p.parent().unwrap()).unwrap();
    std::fs::write(p, body).unwrap();
}

/// What `pact check` prints, and whether it refused.
fn check(root: &std::path::Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

/// The report split into one block per problem, in the order printed.
fn problems(rendered: &str) -> Vec<String> {
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
    blocks.into_iter().map(|b| b.join("\n")).collect()
}

fn fix_line(block: &str) -> String {
    block
        .lines()
        .find_map(|l| l.trim_start().strip_prefix("fix: "))
        .unwrap_or_else(|| panic!("O7.3: every problem carries a fix:\n{block}"))
        .to_string()
}

/// The text between the n-th pair of backticks in `s`.
fn quoted(s: &str, n: usize) -> String {
    let parts: Vec<&str> = s.split('`').collect();
    assert!(
        parts.len() > n * 2,
        "expected at least {} quoted things in: {s}",
        n + 1
    );
    parts[n * 2 + 1].to_string()
}

/// The tree at the top of this file: one agent, and nothing a beginner would
/// not have written.
fn the_first_tree_anybody_makes(name: &str) -> std::path::PathBuf {
    let root = tree(name);
    write(
        &root,
        "agents/hello/agent.yaml",
        "description: says hello\n",
    );
    root
}

#[test]
fn the_first_error_a_brand_new_author_sees_names_a_file_they_can_create() {
    let root = the_first_tree_anybody_makes("names-a-file");
    let (ok, text) = check(&root);
    assert!(
        !ok,
        "a workspace with no name must still be refused:\n{text}"
    );

    let first = problems(&text)
        .first()
        .cloned()
        .expect("something was reported");
    assert!(
        first.contains("must have a 'name'"),
        "the missing name is still the first thing said:\n{text}"
    );

    let fix = fix_line(&first);
    assert!(
        fix.contains("workspace.yaml"),
        "the fix has to name the file to put the line in, and there is only one \
         name `pact discover` reads:\n{first}"
    );
    assert!(
        fix.starts_with("Create "),
        "a file that does not exist cannot be added to — the verb is what tells \
         the reader to make one:\n{first}"
    );
    // The path has to be complete. `Create \`workspace.yaml\`` is ambiguous the
    // moment a tree has more than one folder in it, and this one already does.
    let named = quoted(&fix, 0);
    assert_eq!(
        std::path::Path::new(&named),
        root.join("workspace.yaml"),
        "the fix must name where the file goes, not only what it is called:\n{first}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn nothing_in_the_report_gives_a_line_and_column_inside_a_folder() {
    // The arrow is the only thing left pointing anywhere once the excerpt is
    // correctly withheld, so it has to be true. A folder has no line 1.
    let root = the_first_tree_anybody_makes("no-line-in-a-folder");
    let (_, text) = check(&root);
    let where_at: Vec<&str> = text
        .lines()
        .filter_map(|l| l.trim_start().strip_prefix("--> "))
        .collect();
    assert!(!where_at.is_empty(), "every problem says where:\n{text}");
    for place in where_at {
        let named = place.rsplitn(3, ':').last().unwrap_or(place);
        assert!(
            !std::path::Path::new(named).is_dir() || place == named,
            "'{place}' gives a line and a column in a folder:\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn typing_the_fix_exactly_as_it_is_written_clears_the_error() {
    // The guarantee the wording exists for, and the only way to hold it that
    // does not restate the wording: DO what the sentence says — create the file
    // it names, put in it the line it quotes — and the problem is gone. Nothing
    // here knows the words `workspace.yaml` or `name`; both are read out of the
    // report, so this fails the moment the fix stops being followable.
    //
    // The agent is finished, so the workspace's name is the ONLY thing wrong and
    // typing the fix has to leave a tree that runs. Otherwise "the error is
    // gone" could be true while the author is no nearer to anything working.
    let root = tree("typing-the-fix");
    write(
        &root,
        "agents/hello/agent.yaml",
        "description: says hello\ninstructions: Greet the customer by name.\n",
    );
    let (ok, before) = check(&root);
    assert!(!ok, "the missing name is the one problem:\n{before}");
    let reported = problems(&before);
    assert_eq!(reported.len(), 1, "one mistake, one message:\n{before}");
    let fix = fix_line(&reported[0]);

    let file = quoted(&fix, 0);
    let line = quoted(&fix, 1); // `name: ...`
    let setting = line.split(':').next().expect("the line names a setting");
    std::fs::write(&file, format!("{setting}: Hello Desk\n")).expect("the file named can be made");

    let (ok, after) = check(&root);
    assert!(
        ok && !after.contains("must have a 'name'"),
        "the fix was typed exactly as written, so the tree has to be accepted now:\n\
         fix was: {fix}\nafter:\n{after}"
    );
    // And the tree is now a workspace the rest of the toolchain can see. This is
    // what rules out the other spellings the loader would also have accepted:
    // `hello/hello.yaml` loads and `pact discover` never finds it.
    let listed = pact()
        .args(["discover", root.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let listed = String::from_utf8_lossy(&listed.stdout).into_owned();
    assert!(
        listed.contains("Hello Desk"),
        "following the fix has to leave a workspace `pact discover` finds:\n{listed}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_folder_shaped_agent_with_no_file_of_its_own_is_told_which_file_to_start() {
    // The same shape one level down, and the reason the answer is computed
    // rather than hard-coded to `workspace.yaml`: an agent written as a folder
    // of parts — the Expansion Rule's whole point — has no file holding its own
    // settings either, so `description` has nowhere to go. The file to make
    // there is `agent.yaml`, which `policy.rs` records as the spelling a
    // non-technical author reaches for without being taught anything.
    let root = tree("folder-shaped-agent");
    write(&root, "workspace.yaml", "name: Hello Desk\n");
    write(
        &root,
        "agents/hello/instructions.md",
        "Say hello politely.\n",
    );
    let (ok, text) = check(&root);
    assert!(
        !ok,
        "an agent with no description must still be refused:\n{text}"
    );

    let mine = problems(&text)
        .into_iter()
        .find(|b| b.contains("must have a 'description'"))
        .unwrap_or_else(|| panic!("the missing description must be reported:\n{text}"));
    let fix = fix_line(&mine);
    assert!(
        fix.starts_with("Create "),
        "there is no file to add a line to:\n{mine}"
    );
    assert_eq!(
        std::path::Path::new(&quoted(&fix, 0)),
        root.join("agents/hello/agent.yaml"),
        "the file to make is the agent's own, in the agent's own folder:\n{mine}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_setting_missing_from_a_file_that_does_exist_is_still_told_to_add_a_line() {
    // The other side of the branch, and the one that must not drift: when there
    // IS a file, "create it" would be wrong and confusing. `workspace.yaml`
    // exists here and says nothing, which is what a half-written file looks
    // like on the way to being finished.
    let root = tree("file-that-exists");
    write(&root, "workspace.yaml", "# TODO\n");
    write(
        &root,
        "agents/hello/agent.yaml",
        "description: says hello\n",
    );
    let (ok, text) = check(&root);
    assert!(!ok, "an unnamed workspace is still refused:\n{text}");

    let mine = problems(&text)
        .into_iter()
        .find(|b| b.contains("must have a 'name'"))
        .unwrap_or_else(|| panic!("the missing name must be reported:\n{text}"));
    assert!(
        fix_line(&mine).starts_with("Add a line:"),
        "the file is right there — telling the author to create it would send \
         them to make a second copy of the one they have open:\n{mine}"
    );
    assert!(
        mine.contains("workspace.yaml:"),
        "and a real file gets a real line and column:\n{mine}"
    );
    let _ = std::fs::remove_dir_all(&root);
}
