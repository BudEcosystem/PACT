//! The tree `pact check` says an agent lives in is a tree `pact discover` finds,
//! and the instruction it gives an author who has no tree yet is one that works
//! when they follow it literally.
//!
//! # What was measured
//!
//! One question — *is this folder a workspace?* — was answered in three places,
//! and the answers were not the same. `discover::walk` reads
//! `workspace.yaml`/`workspace.yml` and nothing else, and that is the answer the
//! runtime uses. `enclosing_workspace` also accepted a folder for holding an
//! `agents/` directory, with no self file in it at all.
//!
//! So this tree — the shape an author lands in the moment they make
//! `agents/hello/` before writing `workspace.yaml`:
//!
//! ```text
//! bare/agents/hello/agent.yaml   name: Hello
//!                                description: A hello agent.
//!                                instructions: Say hi.
//! ```
//!
//! was described two different ways by two commands over the same folder:
//!
//! ```text
//! $ pact check bare
//! error: A workspace must have a 'name'.                              (exit 1)
//!
//! $ pact discover bare
//! []                                                                 (exit 0)
//!
//! $ pact check bare/agents/hello
//! OK — bare/agents/hello loaded cleanly, checked inside bare so its tools and
//! policies could be found.                                           (exit 0)
//! ```
//!
//! The last one is the defect. The agent was checked *in the context of a
//! workspace that does not exist* — and `check_in_context` prints only what is
//! wrong inside the folder the reader named, so the *"A workspace must have a
//! 'name'"* that `pact check bare` prints at the root was filtered out on the
//! way. An author working the way the tool tells them to — check the agent you
//! are editing — was told their agent was fine, inside a workspace no runtime
//! can find, by the same binary that refuses the folder above it.
//!
//! Routing that shape to `not_a_workspace` then produced three more, all of them
//! measured here before they were fixed:
//!
//! ```text
//! $ pact check X/agents/proj/m          # an agent TWO levels under agents/
//! fix: Create `X/workspace.yaml` … This agent is already in the right place;
//! nothing here has to move.                                          (exit 0)
//! # …and after creating exactly that file: 3 errors, `pact discover X` → []
//! # The agent did have to move. The message said it did not.
//!
//! $ pact check bare/agents/empty        # an empty folder inside a real tree
//! fix: Create `bare/agents/empty/workspace.yaml` …
//! # A second tree, three folders deep inside the author's own.
//!
//! $ cd bare/agents/hello && pact check .
//! fix: Create `./workspace.yaml` … Then move this agent into a folder beside
//! it: `./agents/<a short name for it>/agent.yaml`.
//! # The same agent in the same tree, two contradictory instructions, chosen by
//! # how the path happened to be typed.
//! ```
//!
//! …and one more, which is the original defect reached a different way: a
//! workspace whose own `workspace.yaml` has a problem is skipped whole by
//! `pact discover`, and the agent inside it was still told it was fine.
//!
//! ```text
//! $ printf 'name: Probe\nbogus_field: 1\n' > broke/workspace.yaml
//! $ pact discover broke              skipping broke: 1 problem(s) / []
//! $ pact check broke/agents/hello
//! OK — broke/agents/hello loaded cleanly, checked inside broke …      (exit 0)
//! ```
//!
//! # What is asserted
//!
//! Three claims, all through the binary, over the same trees:
//!
//! 1. **Agreement.** The folder `pact check` resolves an agent into is a folder
//!    `pact discover` publishes when pointed at it; where it resolves the agent
//!    into nothing, the reader is told nothing can run rather than `OK`. Held
//!    over a table of nine shapes.
//! 2. **Agreement at the root.** `pact check <root>` says `loaded cleanly` only
//!    for a root discovery publishes. One direction only, on purpose: the
//!    converse is false and rightly so — a workspace with its skills written and
//!    no agent yet is published by discovery AND warned about by the checker,
//!    which is the half-built state
//!    `a_workspace_with_no_agents_in_it_yet_is_still_a_workspace.rs` exists for.
//! 3. **The advice works.** Every fix the "no workspace here" messages give is
//!    read back out of the rendered message and PERFORMED mechanically — create
//!    the file it names, move the agent if and only if it says to — and the
//!    resulting tree must load and publish its agent. Nothing about the wording
//!    is trusted; a message that says "nothing has to move" to somebody whose
//!    agent does have to move fails on the tree it leaves behind.
//!
//! # Mutations
//!
//! Each was applied to `crates/pact-cli/src/main.rs`, rebuilt, and the whole
//! `pact-cli` suite run.
//!
//! **A** — restore `holds_self_file(dir, &WORKSPACE_SELF_FILES) ||
//! dir.join("agents").is_dir()` as the body of `looks_like_a_workspace_root`,
//! moving the `agents/` arm back out of `is_a_workspace` into the shared
//! predicate. Without it,
//! `an_agents_folder_with_no_self_file_is_not_a_workspace_around_the_agent` and
//! `every_root_a_check_names_is_a_root_discovery_finds` fail — the first on
//! `pact check bare/agents/hello` printing `OK … checked inside`, the second on
//! `bare` being named as a root `pact discover bare` answers `[]` for.
//!
//! **B** — make `not_a_workspace` always take the "move it" arm, so every agent
//! with no workspace around it gets the flat shape's wording. Only
//! `an_agents_folder_with_no_self_file_is_not_a_workspace_around_the_agent`
//! fails, on the fix naming `bare/agents/hello/workspace.yaml` and asking for a
//! move — the advice that builds a second tree inside the author's own.
//!
//! **C** — restore `the_agent_is_where_the_loader_looks` to the ancestor-NAME
//! search it was (`folder.ancestors().find(|a| a.file_name() == Some("agents"))
//! .and_then(Utf8Path::parent)`, used as the whole test). Without it,
//! `an_agent_buried_below_the_agents_folder_is_told_to_move`,
//! `an_agent_file_dropped_into_the_agents_folder_itself_is_told_to_move` and
//! `every_fix_these_messages_give_produces_a_tree_that_loads` fail — the last on
//! the followed tree still refusing to load, which is the whole point of the
//! sentence being wrong.
//!
//! **D** — restore `holding_folder` to `if path.is_dir() { path.clone() } else
//! { path.parent()… }` with no `canonicalize_utf8`. Without it,
//! `the_advice_is_the_same_however_the_path_was_typed` fails on `.` and on a
//! bare `agent.yaml` getting the move sentence the absolute path does not.
//!
//! **E** — compute `start` in `not_a_workspace` from `folder` instead of
//! `tree_the_folder_belongs_to(&folder)`. Without it,
//! `an_empty_folder_inside_a_tree_is_told_where_the_workspace_really_goes`
//! fails on the fix naming `bare/agents/empty/workspace.yaml`.
//!
//! **F** — delete the `elsewhere > 0` block in `check_in_context`. Without it,
//! `an_agent_whose_workspace_cannot_load_is_not_told_it_loaded_cleanly` fails on
//! the `OK — … checked inside` for a tree `pact discover` returns `[]` for, and
//! the `broke` row of `every_root_a_check_names_is_a_root_discovery_finds` fails
//! with it.
//!
//! **G** — drop `deny_warnings` from `check_in_context`'s exit code. Without it,
//! `a_warning_inside_a_workspace_is_a_refusal_when_the_reader_asked_for_one`
//! fails at exit 0.
//!
//! A further mutation, measured and recorded rather than fixed: narrowing
//! `WORKSPACE_SELF_FILES` to `["workspace.yaml"]` fails only
//! `a_workspace_spelt_yml_is_one_tree_to_both_commands` — the tables stay GREEN,
//! because both commands read that one list and a narrowed list moves them
//! together. That is the point of the shared predicate and it is also the limit
//! of these tables: they can only catch the two answers DIVERGING, so each
//! spelling is asserted by name beside them. Re-inlining the two file names into
//! `discover::walk` would likewise pass everything here. See the note on
//! `looks_like_a_workspace_root`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A fresh directory of its own, named after the shape built in it.
fn tree(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("pact-one-answer-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    // The message `check` prints names the CANONICAL root, so the tree the test
    // compares against has to be canonical too or every comparison fails on a
    // symlinked temp directory rather than on the claim.
    std::fs::canonicalize(&dir).unwrap()
}

fn write(root: &std::path::Path, rel: &str, body: &str) {
    let p = root.join(rel);
    std::fs::create_dir_all(p.parent().unwrap()).unwrap();
    std::fs::write(p, body).unwrap();
}

/// Everything a command printed, both streams, and whether it refused.
fn run(args: &[&str]) -> (bool, String) {
    let out = pact().args(args).output().expect("the binary runs");
    let mut text = String::from_utf8_lossy(&out.stdout).into_owned();
    text.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), text)
}

/// ...and the same, from a working directory of the caller's choosing, because
/// *how the path was typed* is one of the things under test.
fn run_from(cwd: &std::path::Path, args: &[&str]) -> (bool, String) {
    let out = pact()
        .args(args)
        .current_dir(cwd)
        .output()
        .expect("the binary runs");
    let mut text = String::from_utf8_lossy(&out.stdout).into_owned();
    text.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), text)
}

fn check(path: &std::path::Path) -> (bool, String) {
    run(&["check", path.to_str().unwrap()])
}

fn discover(path: &std::path::Path) -> String {
    run(&["discover", path.to_str().unwrap()]).1
}

/// The folder `check` said it loaded the agent inside, if it said so.
fn checked_inside(rendered: &str) -> Option<String> {
    let (_, after) = rendered.split_once("checked inside ")?;
    let (root, _) = after.split_once(" so its tools")?;
    Some(root.to_string())
}

/// Whether `pact discover` pointed AT this folder PUBLISHES it — not merely
/// recognises it. A workspace it names in `skipping <root>: N problem(s)` and
/// then leaves out of the inventory is one no runtime receives, so it does not
/// count here and the difference is exactly where the interesting inputs live.
fn discovery_publishes(dir: &str) -> bool {
    discover(std::path::Path::new(dir)).contains(&format!("\"root\": \"{dir}\""))
}

/// The `fix:` line of the first problem printed, whatever the problem was.
fn fix_line(rendered: &str) -> String {
    rendered
        .lines()
        .find_map(|l| l.trim_start().strip_prefix("fix: "))
        .unwrap_or_else(|| panic!("O7.3: every problem carries a fix:\n{rendered}"))
        .to_string()
}

/// The name inside the first pair of backticks after `word`.
fn backticked_after(text: &str, word: &str) -> Option<String> {
    let (_, after) = text.split_once(word)?;
    let (_, opened) = after.split_once('`')?;
    let (name, _) = opened.split_once('`')?;
    Some(name.to_string())
}

const AGENT: &str = "name: Hello\ndescription: A hello agent.\ninstructions: Say hi.\n";

/// Every shape in the table, built fresh, with the agent inside it.
///
/// Back come the tree root — what a runtime is pointed at — and the path a
/// reader would type to check the one agent they are editing.
fn shape(name: &str, who: &str) -> (std::path::PathBuf, std::path::PathBuf) {
    // `who` keeps two tests building the same shape out of each other's way, so
    // the suite's own parallelism cannot delete a tree mid-run.
    let root = tree(&format!("{name}-{who}"));
    match name {
        "yaml" => {
            write(&root, "workspace.yaml", "name: Probe\n");
            write(&root, "agents/hello/agent.yaml", AGENT);
        }
        "yml" => {
            write(&root, "workspace.yml", "name: Probe\n");
            write(&root, "agents/hello/agent.yaml", AGENT);
        }
        // A workspace whose own self file has a problem in it. Discovery skips
        // the whole tree, so nothing in it can run however clean the agent is.
        "broke" => {
            write(&root, "workspace.yaml", "name: Probe\nbogus_field: 1\n");
            write(&root, "agents/hello/agent.yaml", AGENT);
        }
        "bare" => write(&root, "agents/hello/agent.yaml", AGENT),
        // Two levels under `agents/`, which the Expansion Rule does not read.
        "deep" => write(&root, "agents/proj/m/agent.yaml", AGENT),
        // Dropped straight into `agents/` — measured: the loader answers "This
        // should be a set of agent settings, but it is some text" for that file,
        // so it is not the flat form and it is not the folder form either.
        "in-agents" => write(&root, "agents/agent.yaml", AGENT),
        // ...and the flat form that IS read: `agents/<name>.yaml`.
        "flat-file" => write(&root, "agents/desk.yaml", AGENT),
        "lone" => write(&root, "agent.yaml", AGENT),
        "empty" => {}
        "nested" => {
            write(&root, "workspace.yaml", "name: Outer\n");
            write(&root, "inner/workspace.yaml", "name: Inner\n");
            write(&root, "inner/agents/hello/agent.yaml", AGENT);
        }
        other => panic!("no shape named {other}"),
    }
    let agent = match name {
        "nested" => root.join("inner/agents/hello"),
        "bare" | "yaml" | "yml" | "broke" => root.join("agents/hello"),
        "deep" => root.join("agents/proj/m"),
        "in-agents" => root.join("agents"),
        "flat-file" => root.join("agents/desk.yaml"),
        _ => root.clone(),
    };
    (root, agent)
}

/// THE DEFECT. An `agents/` folder is not a workspace to a runtime, so it must
/// not be one to the checker either.
#[test]
fn an_agents_folder_with_no_self_file_is_not_a_workspace_around_the_agent() {
    let (root, agent) = shape("bare", "one");

    let found = discover(&root);
    assert!(
        found.trim() == "[]",
        "`pact discover` finds no workspace in a folder with no `workspace.yaml` \
         in it — that is the contract this test holds `check` to. It printed:\n{found}"
    );

    let (_, text) = check(&agent);
    assert!(
        text.contains("loader/nothing-can-run-this"),
        "checking the agent must say nothing can find it, because nothing can: \
         `pact discover` over the same tree answered `[]`. It printed:\n{text}"
    );
    assert!(
        checked_inside(&text).is_none(),
        "…and it must not claim to have checked the agent inside a workspace that \
         `pact discover` does not find. It printed:\n{text}"
    );
    // ...and the file it names is the one at the TOP of the tree the author has
    // already laid out, not one inside the agent's own folder. The generic
    // wording — make the workspace beside this folder, then move the agent into
    // an `agents/` under it — would have told somebody whose agent is already at
    // `<tree>/agents/hello/agent.yaml` to build a second tree inside their own,
    // and a reader who cannot write code has no way to see that is wrong.
    let root = root.to_str().unwrap();
    assert!(
        text.contains(&format!("Create `{root}/workspace.yaml`")),
        "the fix names the self file at the top of the tree the agent is already \
         inside. It printed:\n{text}"
    );
    assert!(
        !text.contains("move this agent"),
        "…and does not ask for a move, because this agent is already where a \
         runtime would look for it. It printed:\n{text}"
    );
}

/// The ordinary shape, and the one every example ships: nothing about the fix
/// may cost an agent the workspace it really is inside.
#[test]
fn a_workspace_around_an_agent_is_one_tree_to_both_commands() {
    let (root, agent) = shape("yaml", "one");
    let expected = root.to_str().unwrap();

    assert!(
        discovery_publishes(expected),
        "`pact discover` finds the workspace. It printed:\n{}",
        discover(&root)
    );
    let (ok, text) = check(&agent);
    assert!(
        ok,
        "checking an agent inside a workspace is clean. It printed:\n{text}"
    );
    assert_eq!(
        checked_inside(&text).as_deref(),
        Some(expected),
        "…inside the workspace that is really around it. It printed:\n{text}"
    );
}

/// The other spelling of the self file, which walking up could not see at all
/// before the two answers were joined.
#[test]
fn a_workspace_spelt_yml_is_one_tree_to_both_commands() {
    let (root, agent) = shape("yml", "one");
    let expected = root.to_str().unwrap();

    assert!(
        discovery_publishes(expected),
        "`workspace.yml` is a workspace to the runtime. It printed:\n{}",
        discover(&root)
    );
    let (ok, text) = check(&agent);
    assert!(
        ok,
        "…so an agent inside one is not told there is no workspace around it. It \
         printed:\n{text}"
    );
    assert_eq!(
        checked_inside(&text).as_deref(),
        Some(expected),
        "…and the tree it is checked inside is that same folder. It printed:\n{text}"
    );
}

/// MUST STAY GREEN — the first of the two shapes `not_a_workspace` exists for.
#[test]
fn a_lone_agent_with_no_workspace_around_it_is_still_told_so() {
    let (root, agent) = shape("lone", "one");
    let (_, text) = check(&agent);
    assert!(
        text.contains("loader/nothing-can-run-this"),
        "a lone `agent.yaml` is one file away from working and is told which \
         file. It printed:\n{text}"
    );
    assert!(
        text.contains("has an agent in it and no workspace around it"),
        "…in the words written for that shape. It printed:\n{text}"
    );
    // The flat shape is the one the move sentence was written for, and it keeps
    // it: this agent is NOT already inside an `agents/` folder, so making the
    // workspace beside it is only half the job.
    assert!(
        text.contains("move this agent into a folder beside it"),
        "a flat `agent.yaml` does have to move, and is told so. It \
         printed:\n{text}"
    );
    assert_eq!(discover(&root).trim(), "[]", "and no runtime finds it");
}

/// MUST STAY GREEN — the second shape, where telling the reader to add
/// `description:` to a file that does not exist would help nobody.
#[test]
fn an_empty_folder_is_still_not_a_pact_folder() {
    let (root, agent) = shape("empty", "one");
    let (ok, text) = check(&agent);
    assert!(!ok, "an empty folder is refused. It printed:\n{text}");
    assert!(
        text.contains("loader/not-a-pact-folder"),
        "…as not a PACT folder, which is the shape it really is. It \
         printed:\n{text}"
    );
    assert_eq!(discover(&root).trim(), "[]", "and no runtime finds it");
}

/// An agent TWO levels under `agents/`, which the Expansion Rule does not read.
///
/// The reason "is any ancestor called `agents`" is not the question: it is true
/// of every folder at every depth below one, so this agent was told *"already in
/// the right place; nothing here has to move"* and `pact check` exited 0, while
/// creating exactly the file named left a tree with three errors in it.
#[test]
fn an_agent_buried_below_the_agents_folder_is_told_to_move() {
    let (root, agent) = shape("deep", "one");
    let (_, text) = check(&agent);
    assert!(
        text.contains("loader/nothing-can-run-this"),
        "nothing can find an agent two folders below `agents/`. It printed:\n{text}"
    );
    assert!(
        !text.contains("nothing here has to move"),
        "this agent is NOT where the loader looks — `<tree>/agents/<name>/agent.yaml` \
         is, and this is a level below it — so it must not be told it can stay. It \
         printed:\n{text}"
    );
    let root = root.to_str().unwrap();
    assert!(
        text.contains(&format!("Create `{root}/workspace.yaml`")),
        "the workspace still belongs at the top of the tree the `agents/` folder \
         is in, not beside the agent. It printed:\n{text}"
    );
    assert!(
        text.contains(&format!("`{root}/agents/<a short name for it>/agent.yaml`")),
        "…and where it has to move to is a folder beside that file, named in full. \
         It printed:\n{text}"
    );
}

/// An `agent.yaml` dropped straight into `agents/` — a beginner's shape, and
/// neither of the two the Expansion Rule reads.
#[test]
fn an_agent_file_dropped_into_the_agents_folder_itself_is_told_to_move() {
    let (root, agent) = shape("in-agents", "one");
    let (_, text) = check(&agent);
    assert!(
        !text.contains("nothing here has to move"),
        "`agents/agent.yaml` is not a place the loader reads an agent from — \
         measured, it answers `This should be a set of agent settings, but it is \
         some text` — so its author must not be told to leave it there. It \
         printed:\n{text}"
    );
    let root = root.to_str().unwrap();
    assert!(
        text.contains(&format!("Create `{root}/workspace.yaml`")),
        "the workspace goes at the top of the tree the `agents/` folder is in. It \
         printed:\n{text}"
    );
}

/// The flat form that IS read — `agents/<name>.yaml` — stays put, so the rule
/// above is the Expansion Rule's and not merely "folders good, files bad".
#[test]
fn a_flat_agent_file_named_after_itself_is_already_in_the_right_place() {
    let (root, agent) = shape("flat-file", "one");
    let (_, text) = check(&agent);
    assert!(
        text.contains("nothing here has to move"),
        "`agents/desk.yaml` is one of the two shapes the Expansion Rule reads, so \
         the only thing missing is the workspace above it. It printed:\n{text}"
    );
    let root = root.to_str().unwrap();
    assert!(
        text.contains(&format!("Create `{root}/workspace.yaml`")),
        "…which is the file it is told to make. It printed:\n{text}"
    );
}

/// The same agent, the same tree, four ways of typing the path — one answer.
#[test]
fn the_advice_is_the_same_however_the_path_was_typed() {
    let (root, agent) = shape("bare", "typed");

    let absolute = check(&agent).1;
    let relative = run_from(&root, &["check", "agents/hello"]).1;
    let dot = run_from(&agent, &["check", "."]).1;
    let bare_file = run_from(&agent, &["check", "agent.yaml"]).1;
    let sideways = run_from(&agent, &["check", "../hello"]).1;

    let expected = fix_line(&absolute);
    for (how, text) in [
        ("a relative path from the tree root", &relative),
        ("`.` from inside the agent's own folder", &dot),
        ("the file name alone", &bare_file),
        ("a path that goes up and comes back", &sideways),
    ] {
        assert_eq!(
            fix_line(text),
            expected,
            "the same agent in the same tree, checked as {how}, was given \
             different instructions from the ones the absolute path gets. \
             Absolute printed:\n{absolute}\n…and {how} printed:\n{text}"
        );
    }
    // ...and specifically NOT the instruction that builds a second tree inside
    // the author's own, which is what `.` used to get.
    assert!(
        !dot.contains("move this agent"),
        "checking the folder you are standing in is the most ordinary invocation \
         there is, and it was the one that told an author to move an agent that \
         is already in the right place. It printed:\n{dot}"
    );
}

/// An empty folder INSIDE a tree is told where the workspace really goes.
///
/// The error arm was left computing that from the folder it was handed while the
/// warning arm worked it out from the `agents/` directory above, so one command
/// answered "where does the workspace go" two ways depending on whether the
/// folder happened to have an agent in it.
#[test]
fn an_empty_folder_inside_a_tree_is_told_where_the_workspace_really_goes() {
    let root = tree("empty-inside");
    write(&root, "agents/hello/agent.yaml", AGENT);
    std::fs::create_dir_all(root.join("agents/empty")).unwrap();

    let (ok, text) = check(&root.join("agents/empty"));
    assert!(
        !ok,
        "a folder with nothing in it is still refused. It printed:\n{text}"
    );
    let root = root.to_str().unwrap();
    assert!(
        text.contains(&format!("Create `{root}/workspace.yaml`")),
        "the workspace belongs at the top of the tree this folder is inside. It \
         printed:\n{text}"
    );
    assert!(
        !text.contains(&format!("Create `{root}/agents/empty/workspace.yaml`")),
        "…and not three folders down inside it, which is a second tree. It \
         printed:\n{text}"
    );
}

/// A workspace whose own document will not load takes its agents down with it,
/// and the author of one of those agents has to be told.
#[test]
fn an_agent_whose_workspace_cannot_load_is_not_told_it_loaded_cleanly() {
    let (root, agent) = shape("broke", "one");
    let listed = discover(&root);
    assert!(
        listed.contains(&format!("skipping {}", root.display())),
        "the premise: `pact discover` refuses a workspace it cannot load whole, \
         and says which. It printed:\n{listed}"
    );
    assert!(
        !discovery_publishes(root.to_str().unwrap()),
        "…and publishes nothing for it, so this root reaches no runtime. It \
         printed:\n{listed}"
    );

    let (_, text) = check(&agent);
    assert!(
        !text.contains("loaded cleanly"),
        "the agent's own folder is clean, but nothing in this tree can run, and \
         `loaded cleanly` is what an author reads as done. It printed:\n{text}"
    );
    assert!(
        text.contains("loader/the-workspace-around-it-is-broken"),
        "…so the tree around it is what they are told about. It printed:\n{text}"
    );
    let root = root.to_str().unwrap();
    assert!(
        fix_line(&text).contains(&format!("pact check {root}")),
        "…and the one command that prints those problems is named in full, \
         because this message deliberately does not reprint them. It \
         printed:\n{text}"
    );
}

/// `--deny-warnings` is a decision the reader makes per run, and it was read on
/// only one of the two paths `pact check` can take.
#[test]
fn a_warning_inside_a_workspace_is_a_refusal_when_the_reader_asked_for_one() {
    let (_, agent) = shape("broke", "deny");
    let (ok, text) = check(&agent);
    assert!(
        ok,
        "a problem in somebody else's file is a warning here, not a refusal:\n{text}"
    );

    let (ok, text) = run(&["check", agent.to_str().unwrap(), "--deny-warnings"]);
    assert!(
        !ok,
        "`--deny-warnings` means treat a warning as a refusal, and checking an \
         agent inside a workspace is the invocation the tool tells authors to \
         use. It printed:\n{text}"
    );
}

/// A workspace inside a workspace, and the divergence asserted rather than
/// routed around.
///
/// Walking up stops at the NEAREST self file, and that folder is one discovery
/// publishes when pointed at it. Pointed at the OUTER folder, discovery finds
/// nothing at all — `discover::walk` stops at the first self file, because a
/// workspace is not nested inside another one. That is a real divergence and it
/// is left standing on purpose: the loader's own answer is that nesting is not a
/// shape (*"'inner' is not something a workspace can have"*), and both root
/// checks say so. What must not happen is the tool going quiet about it.
#[test]
fn an_agent_in_a_nested_workspace_is_checked_inside_the_nearest_one() {
    let (root, agent) = shape("nested", "one");
    let inner = root.join("inner");
    let expected = inner.to_str().unwrap();

    let (_, text) = check(&agent);
    assert_eq!(
        checked_inside(&text).as_deref(),
        Some(expected),
        "the agent is checked inside the workspace it is actually in. It \
         printed:\n{text}"
    );
    assert!(
        discovery_publishes(expected),
        "…and a runtime pointed at that folder receives it. It printed:\n{}",
        discover(&inner)
    );

    // THE DIVERGENCE, named. A runtime pointed at the outer folder receives
    // nothing — neither the outer tree nor the inner one.
    let outer = discover(&root);
    assert!(
        !outer.contains(&format!("\"root\": \"{expected}\"")),
        "recorded, not wished away: pointing discovery at the outer tree does not \
         reach the inner one. If this ever starts passing, the walk has changed \
         and this test is what should be read first. It printed:\n{outer}"
    );

    // ...and what keeps that from being silent: the loader refuses the nesting
    // itself, from both roots, naming the folder.
    for at in [&root, &inner] {
        let (ok, text) = check(at);
        assert!(
            !ok && text.contains("'inner' is not something a workspace can have"),
            "nesting is not a shape PACT has, and `pact check {}` has to be the \
             thing that says so — otherwise the divergence above is a silent \
             one. It printed:\n{text}",
            at.display()
        );
    }
}

/// THE RULE, over every shape at once: `check` never names a root that
/// `discover` does not publish, and never leaves the reader with a success
/// message for an agent in a tree discovery returns nothing for.
#[test]
fn every_root_a_check_names_is_a_root_discovery_finds() {
    for name in [
        "yaml",
        "yml",
        "bare",
        "deep",
        "in-agents",
        "flat-file",
        "lone",
        "empty",
        "nested",
        "broke",
    ] {
        let (_, agent) = shape(name, "table");
        let (_, text) = check(&agent);

        if let Some(root) = checked_inside(&text) {
            assert!(
                discovery_publishes(&root),
                "shape `{name}`: `pact check` said the agent was checked inside \
                 `{root}`, and `pact discover {root}` publishes no workspace \
                 there. One question, two answers. check printed:\n{text}\ndiscover \
                 printed:\n{}",
                discover(std::path::Path::new(&root))
            );
        } else {
            assert!(
                text.contains("loader/nothing-can-run-this")
                    || text.contains("loader/not-a-pact-folder")
                    || text.contains("loader/the-workspace-around-it-is-broken"),
                "shape `{name}`: no workspace was found around the agent, so the \
                 reader has to be told nothing here can run rather than left with \
                 a success message. It printed:\n{text}"
            );
        }
    }
}

/// …and the same rule asked at the ROOT, which the table above never types.
///
/// One direction only. `loaded cleanly` implies discovery publishes the root;
/// the converse is deliberately false, because a workspace with its skills
/// written and no agent in it yet is published AND warned about — the half-built
/// state `a_workspace_with_no_agents_in_it_yet_is_still_a_workspace.rs` holds
/// open. The `agents/`-with-no-self-file shape is where the checker says MORE
/// than discovery does, on purpose: `pact discover` answers `[]` and says
/// nothing, while `pact check` names the missing file.
#[test]
fn a_root_the_checker_calls_clean_is_a_root_discovery_publishes() {
    for name in [
        "yaml",
        "yml",
        "bare",
        "deep",
        "in-agents",
        "flat-file",
        "lone",
        "empty",
        "nested",
        "broke",
    ] {
        let (root, _) = shape(name, "roots");
        let (_, text) = check(&root);
        if text.contains("loaded cleanly") {
            assert!(
                discovery_publishes(root.to_str().unwrap()),
                "shape `{name}`: `pact check` called this root clean and \
                 `pact discover` publishes nothing for it. check printed:\n{text}\n\
                 discover printed:\n{}",
                discover(&root)
            );
        }
    }

    // The deliberate divergence, spelt out rather than left implied.
    let (root, _) = shape("bare", "roots-bare");
    let (ok, text) = check(&root);
    let named = root.to_str().unwrap();
    assert!(
        !ok && text.contains(&format!("Create `{named}/workspace.yaml`")),
        "pointed at the tree itself, the checker says which file is missing — \
         which is more than `pact discover` says, and is the whole reason the \
         `agents/` answer still lives in `is_a_workspace`. It printed:\n{text}"
    );
    assert_eq!(
        discover(&root).trim(),
        "[]",
        "…while discovery just answers nothing, as it must."
    );
}

/// THE ADVICE, PERFORMED. Every fix these messages give is read back out of the
/// rendered output and carried out mechanically — create the file it names, move
/// the agent if and only if it says to — and the tree that comes out has to
/// load and publish its agent.
///
/// Nothing about the wording is trusted here. A message that tells somebody
/// their agent need not move when it does fails on the tree it leaves behind,
/// which is the only test of an instruction a non-technical reader can be given
/// (D13): they will do exactly what it says, and exactly what it says has to
/// work.
#[test]
fn every_fix_these_messages_give_produces_a_tree_that_loads() {
    for name in ["bare", "deep", "in-agents", "flat-file", "lone"] {
        let (root, agent) = shape(name, "followed");
        let (_, text) = check(&agent);
        let fix = fix_line(&text);

        // 1. Create the file it names, with the line it says to put in it.
        let make = backticked_after(&fix, "Create ")
            .unwrap_or_else(|| panic!("shape `{name}`: the fix names no file:\n{text}"));
        assert!(
            fix.contains("`name: ...`"),
            "shape `{name}`: …and says what to put in it:\n{text}"
        );
        std::fs::write(&make, "name: Probe\n").unwrap();

        // 2. Move the agent, if and only if it was told to.
        if let Some(dest) = backticked_after(&fix, "move this agent into a folder beside it: ") {
            let dest = dest.replace("<a short name for it>", "moved");
            let from = if agent.is_dir() {
                // Whatever agent self file is in there; the shapes above all use
                // `agent.yaml`, and reading it off disk keeps this honest if one
                // of them stops.
                agent.join("agent.yaml")
            } else {
                agent.clone()
            };
            let dest = std::path::PathBuf::from(&dest);
            std::fs::create_dir_all(dest.parent().unwrap()).unwrap();
            std::fs::rename(&from, &dest).unwrap();
            // "Move" means the old place is gone, so the folders it left behind
            // go with it — an empty `agents/proj/m/` left standing is not what
            // anybody means by moving a file out of it.
            let mut spent = from.parent().map(std::path::Path::to_path_buf);
            while let Some(d) = spent {
                if d == root || std::fs::remove_dir(&d).is_err() {
                    break;
                }
                spent = d.parent().map(std::path::Path::to_path_buf);
            }
        } else {
            assert!(
                fix.contains("nothing here has to move"),
                "shape `{name}`: a fix either says where the agent goes or says it \
                 stays. This one said neither:\n{text}"
            );
        }

        // 3. …and now the tree loads, and a runtime receives the agent.
        let (ok, after) = check(&root);
        assert!(
            ok,
            "shape `{name}`: the tree left behind by following this message \
             exactly still will not load. The message was:\n{fix}\n…and checking \
             the tree it produced printed:\n{after}"
        );
        let listed = discover(&root);
        assert!(
            listed.contains("\"id\": \"pact:"),
            "shape `{name}`: …and `pact discover` still publishes no agent from \
             it, which is what the message promised would change. The message \
             was:\n{fix}\n…and discovery printed:\n{listed}"
        );
    }
}
