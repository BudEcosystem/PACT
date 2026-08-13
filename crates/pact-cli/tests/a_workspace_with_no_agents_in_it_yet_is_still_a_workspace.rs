//! A folder that HAS a `workspace.yaml` is never told it has no `workspace.yaml`.
//!
//! # What was measured
//!
//! A tree built bottom-up — the skills first, the agents that use them not
//! written yet — which is a perfectly ordinary authoring order:
//!
//! ```text
//! ws/workspace.yaml            name: probe
//! ws/skills/policy/skill.yaml  description: A policy.
//! ```
//!
//! `pact check ws` answered:
//!
//! ```text
//! error: 'ws' is not a PACT folder — there is no `workspace.yaml` in it and no
//! `agents/` folder either.
//!   --> ws
//!   fix: Create `ws/workspace.yaml` and put one line in it: `name: ...` — what
//!   this whole system is called. Or point the command at the folder that
//!   already has one.
//!   rule: loader/not-a-pact-folder
//! ```
//!
//! `ws/workspace.yaml` exists and already says `name: probe`. The tool is
//! telling the author to create a file that is open in front of them, and
//! describing their own tree wrongly — R56: *a message that quotes a line the
//! author did not write is a message they stop believing*, and this is a
//! message that describes a file the author DID write as absent.
//!
//! The cause was that `agents:` was used as the test for *is this a workspace*,
//! so a workspace whose only collection is `skills:` (or `tools:`, `ports:`,
//! `questions:` …) was classified as a lone AGENT, found no workspace around
//! itself, and was refused for not being the thing it is.
//!
//! What this file asserts is the CONTRADICTION and not the rule id: a message
//! saying a file is absent while that file exists is the defect, and it would
//! still be the defect under a different id or different wording.
//!
//! # The mirror, which the first attempt at the fix got wrong
//!
//! Widening *what is a workspace* to *holds a collection only a workspace can
//! hold* walked straight into the same defect one shape along. Measured on a
//! flat agent that was not finished yet — `m/agent.yaml` holding `name:` and
//! `description:` and no `instructions:` yet, with a `knowledge/` folder beside
//! it:
//!
//! ```text
//! warning: 'm' is a workspace with no agents in it, so there is nothing here to
//! run …
//!   fix: Create `m/agents/<a short name for it>/agent.yaml` …
//! ```
//!
//! — said at a folder whose `agent.yaml` is the only settings file in it, and
//! the `An agent must have 'instructions'` that told this author what was
//! actually missing had disappeared, because `agent.yaml` was being held against
//! the WORKSPACE group where `name:` and `description:` are both legal. So the
//! agent self file is now read off the disk in the same breath as the workspace
//! self file, and both spellings of both are read, and neither question is
//! decided by which optional lines the author has finished typing.
//!
//! # Mutations
//!
//! Each of these was applied to `crates/pact-cli/src/main.rs`, rebuilt, and the
//! whole `pact-cli` suite run:
//!
//! * **A** — restore `let kind = if root.get("agents").is_some() { "workspace" }
//!   else { "agent" };` in place of the call to `is_a_workspace`. Without it,
//!   `..._is_not_told_it_has_no_workspace_file`,
//!   `the_skill_in_a_workspace_with_no_agents_is_still_read_as_a_skill`,
//!   `nothing_can_run_a_workspace_with_no_agents_and_that_is_what_is_said` and
//!   `a_workspace_whose_self_file_is_spelt_yml_is_still_a_workspace` fail, and
//!   the rest stay green — which is what says the change is a widening rather
//!   than a swap.
//! * **B** — drop the `AGENT_SELF_FILES` arm of `is_a_workspace`. Only
//!   `an_unfinished_lone_agent_beside_a_tools_folder_is_still_an_agent` fails;
//!   before it existed, the whole crate stayed green while a half-written
//!   `agent.yaml` was called an agent-less workspace.
//! * **C** — narrow `WORKSPACE_SELF_FILES` to `["workspace.yaml"]`. Only
//!   `a_workspace_whose_self_file_is_spelt_yml_is_still_a_workspace` and
//!   `an_agent_inside_a_yml_workspace_is_not_told_it_has_no_workspace` fail;
//!   before they existed, all 57 suites in the crate passed while a folder
//!   holding `workspace.yml` was told there is no `workspace.yaml` in it.
//! * **D** — restore `d.join("workspace.yaml").exists() || d.join("agents")
//!   .is_dir()` inside `enclosing_workspace` in place of the shared
//!   `looks_like_a_workspace_root`. Only
//!   `an_agent_inside_a_yml_workspace_is_not_told_it_has_no_workspace` fails.
//! * **E** — delete the early return `validate` takes when a folder holds both
//!   self files. Only `a_folder_that_says_it_is_both_is_told_that_and_nothing_else`
//!   fails, on the guessed group's complaint about the other file's lines.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A fresh directory of its own, named after the test using it.
fn tree(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("pact-no-agents-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn write(root: &std::path::Path, rel: &str, body: &str) {
    let p = root.join(rel);
    std::fs::create_dir_all(p.parent().unwrap()).unwrap();
    std::fs::write(p, body).unwrap();
}

/// Everything `pact check` printed, both streams, and whether it refused.
fn check(root: &std::path::Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let mut text = String::from_utf8_lossy(&out.stdout).into_owned();
    text.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), text)
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

/// The tree at the top of this file: a named workspace, one skill, no agents.
fn skills_before_any_agent(name: &str) -> std::path::PathBuf {
    let root = tree(name);
    write(&root, "workspace.yaml", "name: probe\n");
    write(
        &root,
        "skills/policy/skill.yaml",
        "description: A policy.\n",
    );
    std::fs::create_dir_all(root.join("skills/policy/scripts")).unwrap();
    root
}

/// Every name `text` says is not there, read out of the message rather than
/// known here, so this keeps working when the wording changes.
///
/// Every backticked name after the word `no` counts, not just the first in a
/// sentence: the message this file exists about makes the claim TWICE — *"there
/// is no `workspace.yaml` in it and no `agents/` folder either"* — and a helper
/// that only saw the clause-initial *"there is no `"* missed the second half of
/// the very message it was written against. A trailing `/` comes off, because
/// `agents/` and `agents` are the same folder.
fn files_called_absent(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    for line in text.lines() {
        let mut rest = line;
        while let Some((_, after)) = rest.split_once("no `") {
            let Some((named, tail)) = after.split_once('`') else {
                break;
            };
            out.push(named.trim_end_matches('/').to_string());
            rest = tail;
        }
    }
    out
}

/// Nothing in this report may say a file is missing while it is sitting in
/// `root`. THE contradiction, asserted the same way everywhere it matters.
fn nothing_here_is_called_absent(root: &std::path::Path, text: &str) {
    for named in files_called_absent(text) {
        let claimed = root.join(&named);
        assert!(
            !claimed.exists(),
            "the report says there is no `{named}` in this folder, and `{}` is right \
             there holding `{}`:\n{text}",
            claimed.display(),
            std::fs::read_to_string(&claimed).unwrap_or_default().trim(),
        );
    }
}

/// ...and no fix may send the author off to create a file they already have.
fn no_fix_says_make_what_is_already_there(root: &std::path::Path, text: &str) {
    for block in problems(text) {
        let fix = fix_line(&block);
        for name in ["workspace.yaml", "workspace.yml", "agent.yaml", "agent.yml"] {
            let already = root.join(name);
            assert!(
                !(fix.contains(&format!("Create `{}`", already.display())) && already.exists()),
                "this fix sends the author to make a second copy of the file they have \
                 open:\n{block}"
            );
        }
    }
}

#[test]
fn a_workspace_whose_only_collection_is_skills_is_not_told_it_has_no_workspace_file() {
    let root = skills_before_any_agent("skills-only");
    let (_, text) = check(&root);

    // THE CONTRADICTION. Not "the rule id is absent" — a message that says a
    // file is not there while it is there is wrong whatever it is called.
    nothing_here_is_called_absent(&root, &text);

    // And the rule that carried it, so the reason is named as well as the effect.
    assert!(
        !text.contains("loader/not-a-pact-folder"),
        "a folder with a `workspace.yaml` in it IS a PACT folder:\n{text}"
    );
    // Nothing may tell the author to create the file they already have.
    no_fix_says_make_what_is_already_there(&root, &text);
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_workspace_whose_self_file_is_spelt_yml_is_still_a_workspace() {
    // `discover::walk` reads `workspace.yaml` AND `workspace.yml`, and this is
    // the claim that the checker reads the same two. It takes a folder with
    // NOTHING else in it — no `skills/`, no `agents/` — because any collection
    // beside it would answer the question a second way and the spelling would
    // stop being what is under test. Measured with the second spelling dropped:
    // `error: 'probeD' is not a PACT folder — there is no `workspace.yaml` in it`
    // while `probeD/workspace.yml` sat there holding `name: probe`.
    let root = tree("yml-only");
    write(&root, "workspace.yml", "name: probe\n");
    let (ok, text) = check(&root);
    nothing_here_is_called_absent(&root, &text);
    no_fix_says_make_what_is_already_there(&root, &text);
    assert!(
        !text.contains("loader/not-a-pact-folder"),
        "`workspace.yml` is one of the two names a runtime looks for, so a folder \
         holding one IS a PACT folder:\n{text}"
    );
    assert!(
        ok,
        "a workspace with its name in it and nothing to run is a warning:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_agent_inside_a_yml_workspace_is_not_told_it_has_no_workspace() {
    // The same spelling, asked by the other function that used to answer this
    // question on its own. Walking UP from a document has to find the same
    // workspaces walking DOWN does, or an author gets told the tree they are
    // standing in does not exist. Measured before the two were joined:
    // `warning: '…/skills/policy/skill.yaml' has an agent in it and no workspace
    // around it` and `fix: Create `…/skills/policy/workspace.yaml``, one level
    // below a `workspace.yml`.
    let root = tree("yml-inside");
    write(&root, "workspace.yml", "name: probe\n");
    write(
        &root,
        "skills/policy/skill.yaml",
        "description: A policy.\n",
    );
    let (ok, text) = check(&root.join("skills/policy/skill.yaml"));
    assert!(
        !text.contains("no workspace around it"),
        "the workspace is one folder up, holding `name: probe`:\n{text}"
    );
    no_fix_says_make_what_is_already_there(&root, &text);
    assert!(
        ok,
        "a skill inside a workspace that says nothing wrong is not a problem:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_skill_in_a_workspace_with_no_agents_is_still_read_as_a_skill() {
    // The half that misclassification hid. Being refused as "not a PACT folder"
    // meant nothing in the tree was validated at all, so this asserts the tree
    // is actually LOADED as a workspace: a mistake inside the skill is found.
    // Without it, the test above would pass on a build that silently accepted
    // every tree without looking at it.
    let root = tree("skill-is-read");
    write(&root, "workspace.yaml", "name: probe\n");
    write(
        &root,
        "skills/policy/skill.yaml",
        "descriptoin: A policy.\n",
    );
    let (ok, text) = check(&root);
    assert!(
        !ok && text.contains("descriptoin"),
        "the misspelt setting inside the skill has to be reported, which can only \
         happen if this folder was read as the workspace it is:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn nothing_can_run_a_workspace_with_no_agents_and_that_is_what_is_said() {
    // A workspace with no agents loads — it is a workspace, and half-built is a
    // real state on the way to a finished one. It is still worth saying that
    // nothing in it can run yet, for exactly the reason the mirror-image case
    // is said: `pact discover` finds it and lists nothing, and `pact card` has
    // nothing to publish. A warning and not an error, because refusing it would
    // refuse the ordinary bottom-up authoring order.
    let root = skills_before_any_agent("nothing-runs");
    let (ok, text) = check(&root);
    assert!(
        ok,
        "a half-built workspace is not a broken one — it must not be refused:\n{text}"
    );

    let mine = problems(&text)
        .into_iter()
        .find(|b| b.contains("loader/nothing-can-run-this"))
        .unwrap_or_else(|| panic!("a workspace with no agents has nothing that runs:\n{text}"));
    assert!(
        mine.starts_with("warning: "),
        "half-built is not broken:\n{mine}"
    );
    assert!(
        fix_line(&mine).contains("agents/"),
        "the fix has to name where an agent goes:\n{mine}"
    );

    // And the sentence names two other commands, so those two commands are RUN
    // rather than taken on trust. A message that says what a sibling command
    // does, checked by nothing, is one refactor away from being the thing this
    // whole file is about.
    let out = pact()
        .args(["discover", root.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let listed: serde_json::Value =
        serde_json::from_slice(&out.stdout).expect("`pact discover` prints an inventory");
    let found = listed.as_array().expect("an inventory per workspace");
    assert_eq!(
        found.len(),
        1,
        "`pact discover` has to FIND this workspace — that half of the sentence \
         matters as much as the other:\n{listed:#}"
    );
    assert_eq!(
        found[0]["agents"].as_array().map(Vec::len),
        Some(0),
        "the warning says `pact discover` lists no agents here:\n{listed:#}"
    );

    let card = pact()
        .args(["card", "anything", root.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    assert!(
        !card.status.success(),
        "the warning says `pact card` has nothing to publish:\n{}{}",
        String::from_utf8_lossy(&card.stdout),
        String::from_utf8_lossy(&card.stderr),
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_empty_folder_is_still_not_a_pact_folder() {
    // The first shape the refusal exists for, kept green: nothing here says
    // this is a PACT tree, and the honest answer is that it is not one.
    let root = tree("empty");
    let (ok, text) = check(&root);
    assert!(
        !ok,
        "an empty folder is not something a runtime can load:\n{text}"
    );
    assert!(
        text.contains("loader/not-a-pact-folder"),
        "an empty folder is the case this rule is for:\n{text}"
    );
    assert!(
        fix_line(&problems(&text)[0]).starts_with("Create "),
        "there is no file here to add a line to:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_unfinished_lone_agent_with_nothing_beside_it_is_still_an_agent() {
    // `an_unfinished_lone_agent_beside_a_tools_folder_is_still_an_agent` below
    // asks this question with a `tools/` folder in the tree, and the folder is
    // what carried it: `looks_like_a_workspace_root` fires, `is_a_workspace`
    // answers, and `not_a_workspace` is never reached. Take the folder away and
    // the same unfinished `agent.yaml` fell through to `not_a_workspace`, which
    // was asking a DIFFERENT question — has this document got `description:` or
    // `instructions:` on it — and answered:
    //
    // ```text
    // error: 'm' is not a PACT folder — there is no `workspace.yaml` in it and
    // no `agents/` folder either.
    // ```
    //
    // said at a folder holding `agent.yaml`, with the `An agent must have a
    // 'description'` that names the missing line swallowed by the early return
    // that message takes. Which shape a folder is, is now asked the same way in
    // both places: by the file's NAME first, which does not depend on how far
    // through typing it the author has got.
    let root = tree("unfinished-alone");
    write(&root, "agent.yaml", "name: Desk\n");
    let (ok, text) = check(&root);
    assert!(!ok, "an agent with two lines missing is refused:\n{text}");

    assert!(
        !text.contains("loader/not-a-pact-folder"),
        "a folder with an `agent.yaml` in it is not a folder with nothing in it:\n{text}"
    );
    nothing_here_is_called_absent(&root, &text);
    no_fix_says_make_what_is_already_there(&root, &text);
    assert!(
        text.contains("has an agent in it and no workspace around it"),
        "the words have to say which of the two shapes this is:\n{text}"
    );
    // And the messages the early return used to swallow.
    assert!(
        text.contains("An agent must have a 'description'"),
        "the author has to be told which line is missing:\n{text}"
    );
    assert!(
        text.contains("An agent must have 'instructions'"),
        "and the other one:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_lone_agent_with_no_workspace_around_it_is_still_told_nothing_can_find_it() {
    // The second shape, kept green: an agent one file away from working.
    let root = tree("lone-agent");
    write(
        &root,
        "agent.yaml",
        "name: Desk\ndescription: A desk.\ninstructions: Do it.\n",
    );
    let (ok, text) = check(&root);
    assert!(ok, "a lone agent is a warning, not a refusal:\n{text}");

    let mine = problems(&text)
        .into_iter()
        .find(|b| b.contains("loader/nothing-can-run-this"))
        .unwrap_or_else(|| panic!("nothing can find a lone agent, and that is the point:\n{text}"));
    assert!(
        mine.contains("has an agent in it and no workspace around it"),
        "this folder holds an agent, not a workspace, and the words have to say which:\n{mine}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_lone_agent_that_happens_to_have_a_tools_folder_is_still_a_lone_agent() {
    // The edge that widening "what is a workspace" walks straight into. A flat
    // `agent.yaml` beside a `tools/` folder holds a collection only a workspace
    // can hold AND a setting only an agent can have, and it is an agent: reading
    // it the other way answered *"'instructions' is not something a workspace
    // can have"* about the one line that makes it an agent at all.
    let root = tree("agent-with-tools");
    write(
        &root,
        "agent.yaml",
        "name: Desk\ndescription: A desk.\ninstructions: Do it.\n",
    );
    write(
        &root,
        "tools/weather.yaml",
        "description: Looks up the weather.\n",
    );
    let (_, text) = check(&root);
    assert!(
        text.contains("has an agent in it and no workspace around it"),
        "this folder's own settings are an agent's, so it is an agent:\n{text}"
    );
    assert!(
        !text.contains("not something a workspace can have"),
        "`instructions:` is what makes this an agent — it cannot be the reason it \
         is a broken workspace:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_unfinished_lone_agent_beside_a_tools_folder_is_still_an_agent() {
    // The same shape one line EARLIER, which is the shape that matters: the
    // author has not written `instructions:` yet, so nothing in the document
    // says "agent" and only the file's own name does. Deciding from the settings
    // alone read this as a workspace, said *"is a workspace with no agents in
    // it"* at a folder holding `agent.yaml`, and dropped the one error that told
    // this author what was missing.
    let root = tree("unfinished-agent");
    write(&root, "agent.yaml", "name: Desk\ndescription: A desk.\n");
    write(
        &root,
        "tools/weather.yaml",
        "description: Looks up the weather.\n",
    );
    let (_, text) = check(&root);

    // The contradiction, in its mirror form: `agent.yaml` is in this folder.
    assert!(
        !text.contains("is a workspace with no agents in it"),
        "this folder's `agent.yaml` is the agent, and it is right there:\n{text}"
    );
    nothing_here_is_called_absent(&root, &text);
    no_fix_says_make_what_is_already_there(&root, &text);

    // And the message the misreading swallowed: held against the workspace
    // group, `name:` and `description:` are both legal and nothing was left to
    // report, so an unfinished agent looked finished.
    assert!(
        text.contains("An agent must have 'instructions'"),
        "an agent with no `instructions:` has to be told which line is missing:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_folder_that_says_it_is_both_is_told_that_and_nothing_else() {
    // A folder holding `workspace.yaml` AND `agent.yaml` has not said what it
    // is, and whichever one gets guessed, every line of the other comes back as
    // a setting that kind cannot have. Measured before this was settled:
    // `error: 'instructions' is not something a workspace can have  -->
    // both/agent.yaml:3:1` printed beside `loader/two-self-files` — an error
    // about the line that makes `agent.yaml` an agent, in a folder where the
    // mistake is the second file and not what is written in it.
    let root = tree("two-self-files");
    write(&root, "workspace.yaml", "name: W\n");
    write(
        &root,
        "agent.yaml",
        "name: A\ndescription: A desk.\ninstructions: Do it.\n",
    );
    let (ok, text) = check(&root);
    assert!(
        !ok,
        "a folder that has not said what it is cannot be loaded:\n{text}"
    );
    assert!(
        text.contains("loader/two-self-files"),
        "the one thing wrong here is the second self file:\n{text}"
    );
    assert_eq!(
        problems(&text).len(),
        1,
        "one mistake gets one message — the rest is what guessing produced:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_first_tree_anybody_makes_is_still_a_workspace_missing_its_name() {
    // The tree with an `agents/` folder and no `workspace.yaml` — the first one
    // a person builds — must stay classified as a workspace. Reading the self
    // file as the ONLY marker would have moved it into the lone-agent branch and
    // told this author their tree has no `agents/` folder, which is the same
    // contradiction one level along.
    let root = tree("first-tree");
    write(
        &root,
        "agents/hello/agent.yaml",
        "description: says hello\n",
    );
    let (ok, text) = check(&root);
    assert!(!ok, "a workspace with no name is still refused:\n{text}");
    assert!(
        text.contains("must have a 'name'"),
        "this is a workspace one line short, not a folder that is not a workspace:\n{text}"
    );
    nothing_here_is_called_absent(&root, &text);
    let _ = std::fs::remove_dir_all(&root);
}
