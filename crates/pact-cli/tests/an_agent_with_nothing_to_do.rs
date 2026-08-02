//! An agent with no instructions does nothing, and must be refused rather than
//! reported clean.
//!
//! Measured before this landed: deleting `agents/<name>/instructions.md` from
//! `examples/refund-desk` gave *"OK — … loaded cleanly (481 settings)"* and exit
//! 0, once per agent. A workspace of three agents, not one of which would say a
//! word, passed the one command a non-technical author runs to find out whether
//! their system works.
//!
//! `description:` — one line for a colleague — was `required: yes` the whole
//! time, so the check refused a system whose paperwork was thin and accepted one
//! that was empty. That is backwards, and it is the shape D28.2 names: portable,
//! validating, and useless.
//!
//! `discover` already knew. It publishes `"runnable": <has instructions>` and
//! printed `false`, which is the tool holding the answer and declining to say it
//! at the moment the author asked.
//!
//! Everything here drives the real binary against a real tree, and every fixture
//! is the **worked example with one file removed**. Constructing an agent in
//! Rust and asserting it has no instructions would prove the struct works and
//! say nothing about whether the `required: yes` line in `spec/schema.yaml`
//! reaches the file the author wrote — the failure this project has shipped five
//! rounds running.
//!
//! ## The half `required: yes` did not cover
//!
//! `required:` asks whether the line is there. It never asks whether anything
//! was written on it, so the refusal above arrived one keystroke wide. Measured
//! after it landed: `truncate -s 0` on the same three `instructions.md` files
//! printed *"OK — … loaded cleanly (490 settings)"* and exit 0, and `pact show`
//! handed the tree to an adapter. `rm` was refused; emptying the file — which is
//! what an author does when they mean to start the wording over — was not.
//!
//! The repair is not a rule about `instructions`. `spec/schema.yaml` already had
//! one arm saying a REQUIRED LIST written empty is a hole
//! (`schema/nothing-written-here`); text had no such arm. The second half of
//! this file drives the same three spellings through it, and checks the rule is
//! the specification's `required:` doing the work rather than the field's name —
//! blanking a required line that is not `instructions` is refused identically,
//! and blanking one that is not required stays legal.

use std::path::Path;
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// A private copy of the worked example, so a test that deletes a file cannot
/// damage the tree every other test reads.
fn copy_of_the_example(name: &str) -> std::path::PathBuf {
    let dst =
        std::env::temp_dir().join(format!("pact-nothing-to-do-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(Path::new(&example()), &dst);
    dst
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
    }
}

/// What `pact check` says, and whether it agreed to load the tree.
fn check(root: &Path) -> (bool, String) {
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("the binary runs");
    let mut text = String::from_utf8_lossy(&out.stdout).into_owned();
    text.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), text)
}

#[test]
fn the_worked_example_as_it_ships_still_loads_cleanly() {
    // The half that matters most, and the one a new required setting is most
    // likely to break: the template every author starts from must still pass.
    // A required field that refuses the project's own example is not a stricter
    // check, it is a broken one.
    let (ok, text) = check(Path::new(&example()));
    assert!(ok, "the worked example must load:\n{text}");
    assert!(text.contains("loaded cleanly"), "{text}");
}

#[test]
fn deleting_an_agents_instructions_file_is_refused_instead_of_reported_clean() {
    // The exact edit that reproduced the hole, through the author's own tree and
    // the author's own command. `instructions.md` — the FOLDER spelling — is
    // deleted, because that is the spelling the worked example uses and the one
    // an author who splits a long instruction ends up with.
    let root = copy_of_the_example("folder-form");
    std::fs::remove_file(root.join("agents/fraud-checker/instructions.md")).unwrap();

    let (ok, text) = check(&root);
    assert!(!ok, "an agent that would do nothing must be refused:\n{text}");
    assert!(text.contains("An agent must have 'instructions'."), "must say what is wrong:\n{text}");
    assert!(
        text.contains("agents/fraud-checker/agent.yaml:"),
        "must name the file and the line:\n{text}"
    );
    assert!(text.contains("schema/missing-field"), "reported as a missing setting:\n{text}");
    assert!(text.contains("Nothing was run."), "and nothing runs on a refused tree:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_instructions_line_in_agent_yaml_satisfies_it_with_no_second_file() {
    // The other spelling, and the reason the fix has to name both. An author who
    // keeps the words inline has already done the thing being asked for, so the
    // requirement must be satisfied by the line as well as by the file —
    // otherwise `required: yes` would force every workspace to carry a file it
    // does not need.
    let root = copy_of_the_example("inline-form");
    let agent = root.join("agents/fraud-checker/agent.yaml");
    std::fs::remove_file(root.join("agents/fraud-checker/instructions.md")).unwrap();
    let text = std::fs::read_to_string(&agent).unwrap();
    std::fs::write(
        &agent,
        format!("{text}instructions: Look for signs the order is not genuine, and say which.\n"),
    )
    .unwrap();

    let (ok, said) = check(&root);
    assert!(ok, "the inline spelling must satisfy it on its own:\n{said}");
    assert!(said.contains("loaded cleanly"), "{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_long_instruction_split_across_a_folder_also_satisfies_it() {
    // The third spelling — `agents/<name>/instructions/01-….md` — which the
    // headline rule of both READMEs promises and which arrives as the same
    // setting. A required field that accepted only the two flat forms would
    // punish the author for taking the READMEs' own advice about splitting a
    // long instruction up.
    let root = copy_of_the_example("split-form");
    let dir = root.join("agents/fraud-checker/instructions");
    std::fs::remove_file(root.join("agents/fraud-checker/instructions.md")).unwrap();
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("01-what-to-look-for.md"), "Look for signs the order is not genuine.\n")
        .unwrap();
    std::fs::write(dir.join("02-what-to-say.md"), "Say which signs you found, and how strong.\n")
        .unwrap();

    let (ok, said) = check(&root);
    assert!(ok, "an instruction split across files must satisfy it:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_names_both_of_the_places_the_words_are_allowed_to_go() {
    // The defect this guards against is narrower than the missing check, and
    // worse for the reader: a required setting whose fix names one of two valid
    // forms sends an author who keeps their words in `instructions.md` into
    // `agent.yaml` to repair a file that was never wrong. Both spellings, in the
    // one sentence the author acts on.
    let root = copy_of_the_example("fix-text");
    std::fs::remove_file(root.join("agents/policy-checker/instructions.md")).unwrap();
    let (_, text) = check(&root);

    let fix = text
        .lines()
        .find(|l| l.trim_start().starts_with("fix:"))
        .unwrap_or_else(|| panic!("the refusal carries no fix line:\n{text}"));
    assert!(fix.contains("instructions: ..."), "the inline line to type:\n{fix}");
    assert!(fix.contains("agent.yaml"), "and the file that line goes in:\n{fix}");
    assert!(fix.contains("instructions.md"), "and the file spelling:\n{fix}");
    assert!(
        fix.contains("agents/<name>/instructions.md"),
        "named as a path, so it can be created without guessing where:\n{fix}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_refusal_uses_no_word_a_non_coder_would_have_to_look_up() {
    let root = copy_of_the_example("plain-words");
    std::fs::remove_file(root.join("agents/policy-checker/instructions.md")).unwrap();
    let (_, text) = check(&root);
    let lower = text.to_lowercase();
    for jargon in [
        "schema", "field", "validation", "required attribute", "null", "none", "key error",
        "manifest", "parse",
    ] {
        // The rule name is the one place a machine-readable identifier belongs,
        // so it is taken out before the sentence is read for jargon.
        let prose: String = lower.lines().filter(|l| !l.trim_start().starts_with("rule:")).collect();
        assert!(!prose.contains(jargon), "the refusal leaked '{jargon}':\n{text}");
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_report_about_a_missing_instruction_quotes_no_line_it_cannot_underline() {
    // The renderer's rule, checked on the newest setting to use it. Absence has
    // no position, so quoting the one line of the file that happened to be
    // nearby would say "this line is wrong" about a line that is right. What is
    // left is the file, the line the block starts on, and the line to type.
    let root = copy_of_the_example("no-caret");
    std::fs::remove_file(root.join("agents/fraud-checker/instructions.md")).unwrap();
    let (_, text) = check(&root);

    let quoted = text.lines().filter(|l| l.contains(" | ")).count();
    assert_eq!(quoted, 0, "a missing setting must not single out a line that is correct:\n{text}");
    assert!(!text.contains('^'), "and nothing is underlined either:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn three_agents_with_nothing_to_do_are_three_problems_and_never_a_clean_load() {
    // The measurement that started this, repeated as an assertion: all three
    // `instructions.md` files gone. Before, that was three clean loads; the
    // count is checked as well as the refusal, because a rule that fires once
    // and stops would leave two of the three agents unreported and the author
    // fixing them one round-trip at a time.
    let root = copy_of_the_example("all-three");
    for who in ["refund-desk", "policy-checker", "fraud-checker"] {
        std::fs::remove_file(root.join(format!("agents/{who}/instructions.md"))).unwrap();
    }
    let (ok, text) = check(&root);
    assert!(!ok, "three agents that would do nothing must not load clean:\n{text}");
    assert_eq!(
        text.matches("An agent must have 'instructions'.").count(),
        3,
        "each agent is named, not just the first:\n{text}"
    );
    for who in ["refund-desk", "policy-checker", "fraud-checker"] {
        assert!(text.contains(&format!("agents/{who}/agent.yaml:")), "{who} unnamed:\n{text}");
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn nothing_pact_discover_publishes_can_be_an_agent_that_would_do_nothing() {
    // The refusal has to hold at the seam a runtime reads, not only at the
    // command an author types. `discover` publishes `"runnable"` per agent and
    // used to publish `false` — an inventory openly listing agents that cannot
    // run. With the setting required, a tree carrying one is refused before it
    // is indexed at all.
    let root = copy_of_the_example("discover");
    std::fs::remove_file(root.join("agents/fraud-checker/instructions.md")).unwrap();
    let out = pact().args(["discover", root.to_str().unwrap()]).output().expect("runs");
    let shown = String::from_utf8_lossy(&out.stdout);
    let said = String::from_utf8_lossy(&out.stderr);
    assert!(!shown.contains("\"runnable\": false"), "an unrunnable agent was published:\n{shown}");
    assert!(!shown.contains("fraud-checker"), "the tree was indexed anyway:\n{shown}");
    assert!(said.contains("skipping"), "and the reader is told why it is absent:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_agent_that_would_do_nothing_never_reaches_an_adapter() {
    // `pact show` is the only door an adapter comes through — decision P-1, and
    // `ir.py` reads its output and nothing else. So the refusal is checked
    // there too: if `show` printed the document anyway, the harness would run an
    // agent with an empty instruction and the check would have refused nothing
    // that matters.
    let root = copy_of_the_example("show");
    std::fs::remove_file(root.join("agents/fraud-checker/instructions.md")).unwrap();
    let out = pact().args(["show", root.to_str().unwrap()]).output().expect("runs");
    assert!(
        !out.status.success(),
        "`show` handed an adapter an agent with no instructions:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    assert!(
        String::from_utf8_lossy(&out.stderr).contains("An agent must have 'instructions'."),
        "and it must say why, in the same words `check` uses"
    );
    let _ = std::fs::remove_dir_all(&root);
}

/// Replace a file's contents in a private copy of the example.
fn overwrite(root: &Path, at: &str, text: &str) {
    std::fs::write(root.join(at), text).unwrap();
}

#[test]
fn emptying_an_instructions_file_is_refused_the_same_way_deleting_it_is() {
    // The measurement that reopened this: `truncate -s 0` where the round
    // before had used `rm`. An empty file and an absent one leave the agent with
    // exactly the same nothing to do, so they have to be the same answer — and
    // for one round they were "3 problems" and "loaded cleanly".
    let root = copy_of_the_example("emptied");
    overwrite(&root, "agents/fraud-checker/instructions.md", "");

    let (ok, text) = check(&root);
    assert!(!ok, "an emptied instruction must be refused:\n{text}");
    assert!(
        text.contains("'instructions' is here with nothing in it"),
        "must say what is wrong:\n{text}"
    );
    assert!(
        text.contains("agents/fraud-checker/instructions.md:"),
        "and name the file the author emptied, not the one beside it:\n{text}"
    );
    assert!(text.contains("Nothing was run."), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_instruction_holding_only_a_blank_line_is_refused_like_an_empty_one() {
    // What an editor writes when a file is saved with everything deleted: one
    // newline. Judged on the trimmed text, because a trailing newline is not a
    // sentence and an author cannot see the difference on screen.
    let root = copy_of_the_example("blank-line");
    overwrite(&root, "agents/fraud-checker/instructions.md", "\n   \n\n");
    let (ok, text) = check(&root);
    assert!(!ok, "a file holding only whitespace must be refused:\n{text}");
    assert!(text.contains("'instructions' is here with nothing in it"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_instructions_line_written_as_an_empty_quote_is_refused_too() {
    // The inline spelling of the same nothing. It has to be refused wherever the
    // words are allowed to go, or the fix for one spelling is a route around the
    // check for the other.
    let root = copy_of_the_example("empty-quote");
    let agent = root.join("agents/fraud-checker/agent.yaml");
    std::fs::remove_file(root.join("agents/fraud-checker/instructions.md")).unwrap();
    let was = std::fs::read_to_string(&agent).unwrap();
    std::fs::write(&agent, format!("{was}instructions: \"\"\n")).unwrap();

    let (ok, text) = check(&root);
    assert!(!ok, "an empty instructions line must be refused:\n{text}");
    assert!(text.contains("'instructions' is here with nothing in it"), "{text}");
    assert!(text.contains("agents/fraud-checker/agent.yaml:"), "named where it is:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_for_an_emptied_instruction_still_names_both_places_the_words_may_go() {
    // The reason the help text names both spellings is that BOTH refusals quote
    // it. An author who emptied `instructions.md` and is told only about
    // `agent.yaml` goes to the wrong file, which is the same wrong turn the
    // missing-line fix was written to avoid.
    let root = copy_of_the_example("emptied-fix");
    overwrite(&root, "agents/policy-checker/instructions.md", "");
    let (_, text) = check(&root);

    let fix = text
        .lines()
        .find(|l| l.trim_start().starts_with("fix: Write what it should say"))
        .unwrap_or_else(|| panic!("the refusal carries no fix line:\n{text}"));
    assert!(fix.contains("agent.yaml"), "{fix}");
    assert!(fix.contains("agents/<name>/instructions.md"), "{fix}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn three_emptied_instruction_files_are_three_problems_and_never_a_clean_load() {
    // The measurement verbatim. This is the sentence the round before could
    // print about `rm` and could not print about `truncate`.
    let root = copy_of_the_example("all-three-emptied");
    for who in ["refund-desk", "policy-checker", "fraud-checker"] {
        overwrite(&root, &format!("agents/{who}/instructions.md"), "");
    }
    let (ok, text) = check(&root);
    assert!(!ok, "three emptied instructions must not load clean:\n{text}");
    assert_eq!(
        text.matches("'instructions' is here with nothing in it").count(),
        3,
        "each emptied file is named, not just the first:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_agent_whose_instruction_was_emptied_never_reaches_an_adapter() {
    // Same door, same reason as the deleted-file case: `pact show` is the only
    // way a document reaches `ir.py`, so a refusal that stops at `check` would
    // still let the harness run an agent with an empty instruction.
    let root = copy_of_the_example("emptied-show");
    overwrite(&root, "agents/fraud-checker/instructions.md", "");
    let out = pact().args(["show", root.to_str().unwrap()]).output().expect("runs");
    assert!(!out.status.success(), "`show` handed an adapter an empty instruction");
    assert!(
        String::from_utf8_lossy(&out.stderr).contains("'instructions' is here with nothing in it"),
        "and it must say why, in the same words `check` uses"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn blanking_a_required_line_that_is_not_instructions_is_refused_identically() {
    // The rule is `required:` in `spec/schema.yaml`, not the word
    // `instructions` in any Rust. `description:` is the other required line on
    // the same block, so emptying it must draw the same sentence — if it did
    // not, this would be a special case wearing a general rule's name, and the
    // next required setting somebody adds would silently not be covered.
    let root = copy_of_the_example("blank-description");
    let agent = root.join("agents/fraud-checker/agent.yaml");
    let was = std::fs::read_to_string(&agent).unwrap();
    let blanked: String = was
        .lines()
        .map(|l| if l.starts_with("description:") { "description: \"\"" } else { l })
        .collect::<Vec<_>>()
        .join("\n");
    std::fs::write(&agent, format!("{blanked}\n")).unwrap();

    let (ok, text) = check(&root);
    assert!(!ok, "an emptied description must be refused too:\n{text}");
    assert!(
        text.contains("'description' is here with nothing in it"),
        "the same sentence, about the other required line:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_line_that_is_not_required_may_still_be_left_blank() {
    // The other side of the same claim, and the one that stops this becoming a
    // rule about blankness in general. `name:` is deliberately not required —
    // the folder is the identity — so an author who leaves it empty has written
    // a placeholder, not a hole, and must not be stopped.
    let root = copy_of_the_example("blank-optional");
    let agent = root.join("agents/fraud-checker/agent.yaml");
    let was = std::fs::read_to_string(&agent).unwrap();
    let blanked: String = was
        .lines()
        .map(|l| if l.starts_with("name:") { "name: \"\"" } else { l })
        .collect::<Vec<_>>()
        .join("\n");
    assert!(blanked.contains("name: \"\""), "the fixture has no `name:` line to blank");
    std::fs::write(&agent, format!("{blanked}\n")).unwrap();

    let (ok, text) = check(&root);
    assert!(ok, "a setting nothing requires may be left blank:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_specification_is_what_makes_this_refusal_happen_and_not_any_rust_here() {
    // The claim E-3 makes — the schema is data — held against this setting
    // specifically. If `agent.instructions` ever loses `required: yes`, the
    // eight tests above go quiet rather than red in an obvious place, so the
    // line they all depend on is asserted where it lives.
    //
    // Read off the shipped file rather than a copy, for the reason
    // `diagnostics_read_as_english.rs` gives: a schema built in this file would
    // prove the checker works and say nothing about the specification.
    let text =
        std::fs::read_to_string(format!("{}/../../spec/schema.yaml", env!("CARGO_MANIFEST_DIR")))
            .unwrap();
    let doc = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml")).unwrap();
    let f = doc
        .get("groups")
        .and_then(|g| g.get("agent"))
        .and_then(|a| a.get("fields"))
        .and_then(|f| f.get("instructions"))
        .expect("`agent.instructions` is in the specification");

    assert_eq!(
        f.get("required").and_then(pact_doc::Node::as_str).map(str::trim),
        Some("yes"),
        "`agent.instructions` stopped being required, so a workspace of agents \
         that will do nothing loads clean again"
    );
    // The three the specification owes every setting. Checked here as well as in
    // `authoring_surface.rs` because the help text is the whole content of the
    // fix an author is offered, and a required setting with thin help is a
    // refusal with no way out.
    for want in ["help", "surface", "tier"] {
        assert!(
            f.get(want).and_then(pact_doc::Node::as_str).is_some_and(|s| !s.trim().is_empty()),
            "`agent.instructions` has no `{want}:`"
        );
    }
}
