//! What `pact check` says about a name that is real, but written on the wrong line.
//!
//! `names:` asks one question — is this a key of that map? — and for a round it
//! gave the same answer however wrong the line was: *there is no such entry, add
//! a file `<dir>/<name>.yaml`*. That answer is right for a name nobody has
//! written yet and actively harmful for a name the workspace already has under a
//! different kind, because following it produces a second copy of a document the
//! author is looking at, under a kind nothing reads it as. Both copies then load
//! and nothing anywhere says which one is read.
//!
//! The case that found it is the one the worked example exists to demonstrate.
//! `agent.uses:` draws from `names: [tools, skills]` and `stage.may-use:` draws
//! from `names: [tools, agents]`, so the two lists overlap on tools and disagree
//! on both other sets. The refund desk lists a skill on its `uses:` line, and the
//! `re-read` stage of `loops/careful.yaml` — whose whole purpose is to read a
//! refund decision back against that written policy while being denied the
//! payment tool — could not name it.
//!
//! Two separate things follow, held separately below:
//!
//! 1. **The asymmetry is a specification bug and closes with one YAML edit.**
//!    `the_asymmetry_closes_with_one_line_of_specification_and_no_rust` proves
//!    the edit is sufficient by applying it to a copy of the specification and
//!    loading the tree that needs it.
//! 2. **The diagnostic must never instruct the duplicate**, whichever way (1) is
//!    settled — because `may-use:`/`skills:` is one pairing out of dozens the
//!    same code produces a sentence for, and nobody will be looking at the next
//!    one. Held against a copy of the specification pinned to the state that
//!    produced the bug, so settling (1) cannot quietly retire it.
//!
//! Everything here drives the real binary over a real tree. A unit test on the
//! sentence builder would pass while `pact check` printed something else.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

/// Where one field's `names:` VALUE begins and ends in the specification text.
///
/// Pinned to the field's SHAPE (`<field>:` then `type: list of text` then
/// `names:`) and not to the value, so a test that fixes the value in place does
/// not break the moment the value is deliberately changed — which is exactly
/// what this round asks an integrator to do. If the shape moves, this fails
/// loudly and says so, which is the right outcome: the pin would otherwise be
/// silently editing something else.
///
/// The three lines are NOT required to be adjacent. The specification's own
/// convention is to write the reason a `names:` line exists as a comment between
/// the type and the line itself — `agent.model` has done so since `names:
/// pact:models` landed, and `stage.may-use` does since the asymmetry this file is
/// about was closed. A pin that reads the reason for a rule as the rule ending is
/// a pin that punishes explaining yourself, and this one did: it turned all six
/// tests here red on the very edit they exist to ask for.
fn names_span(spec: &str, group: &str, field: &str) -> (usize, usize) {
    const NAMES: &str = "        names: ";
    // Scoped to the GROUP it belongs to. `may-use:` is written by two kinds now
    // — a stage of a loop and a variant of an agent — and searching the whole
    // file found whichever came first in it, so this test silently rewrote a
    // field it is not about and then asserted about the one it is.
    let from = spec
        .find(&format!("\n  {group}:\n"))
        .unwrap_or_else(|| no_such_shape(field));
    let head = format!("      {field}:\n");
    let mut at = spec[from..].find(&head).unwrap_or_else(|| no_such_shape(field)) + from + head.len();
    let mut typed = false;
    loop {
        let eol = spec[at..].find('\n').map(|i| i + at).unwrap_or(spec.len());
        let line = &spec[at..eol];
        if line == "        type: list of text" {
            typed = true;
        } else if typed && line.starts_with(NAMES) {
            return (at + NAMES.len(), eol);
        } else if !line.starts_with("        #") {
            no_such_shape(field);
        }
        at = eol + 1;
    }
}

fn no_such_shape(field: &str) -> ! {
    panic!(
        "spec/schema.yaml no longer has `{field}:` as a list of text with a `names:` \
         line under it, so this test cannot pin what it is about. \
         fix: update `names_span` in tests/a_name_the_workspace_already_has.rs"
    )
}

/// Rewrite the `names:` line of one field of the shipped specification.
fn set_names(spec: &str, group: &str, field: &str, to: &str) -> String {
    let (from, to_eol) = names_span(spec, group, field);
    format!("{}{to}{}", &spec[..from], &spec[to_eol..])
}

/// A workspace of our own, with its own copy of the specification beside it.
///
/// The copy is reached through `$PACT_SPEC` and `--unsafe-spec`, which is the
/// only route there is. `pact check` used to walk UP from the tree looking for
/// `spec/schema.yaml`, and this file used to rely on that — a sibling `spec/`
/// directory was all it took. That walk was the governance partition: an edited
/// specification in ANY ancestor directory silently rewrote the blast-radius
/// class of every field under it, and nothing in the output ever said which
/// specification had been used. It is gone (LOAD-13), so asking "what would this
/// diagnostic say under a specification that says *this*?" now has to be asked
/// out loud — which is the point.
fn workspace(
    name: &str,
    names: &[(&str, &str, &str)],
    tree_edits: &[(&str, &str, &str)],
) -> PathBuf {
    let root = std::env::temp_dir().join(format!("pact-elsewhere-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(root.join("spec")).unwrap();
    copy(&repo().join("examples/refund-desk"), &root.join("rd"));

    let mut spec = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    for (group, field, value) in names {
        spec = set_names(&spec, group, field, value);
    }
    std::fs::write(root.join("spec/schema.yaml"), spec).unwrap();

    for (file, from, to) in tree_edits {
        let p = root.join("rd").join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(text.contains(from), "the example drifted: {from:?} is no longer in {file}");
        std::fs::write(&p, text.replace(from, to)).unwrap();
    }
    root.join("rd")
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
    }
}

fn checked(path: &Path) -> (bool, String) {
    let spec = path.parent().unwrap().join("spec/schema.yaml");
    let out = pact()
        .args(["check", "--unsafe-spec", path.to_str().unwrap()])
        .env("PACT_SPEC", &spec)
        .output()
        .expect("pact runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

/// The `may-use:` list of the stage that re-reads the decision, with the written
/// refund policy added — the line an author writes when they want that stage to
/// consult the policy and touch nothing else.
const NARROWS_TO_THE_SKILL: (&str, &str, &str) = (
    "loops/careful.yaml",
    "    may-use:\n      - zendesk\n",
    "    may-use:\n      - zendesk\n      - refund-policy\n",
);

/// The specification as it was when this bug was found: an agent may use a
/// skill, a stage of its loop may not name one.
const THE_ASYMMETRY: [(&str, &str, &str); 2] =
    [("agent", "uses", "[tools, skills]"), ("stage", "may-use", "[tools, agents]")];

#[test]
fn a_stage_that_narrows_to_a_skill_is_understood_rather_than_told_to_make_a_tool() {
    // The whole defect in one assertion. `skills/refund-policy/SKILL.md` exists,
    // the refund desk lists `refund-policy` on its own `uses:` line, and the
    // author was told to create `tools/refund-policy.yaml`. Following that leaves
    // two documents describing one refund policy, one of them read by nothing,
    // and no diagnostic anywhere saying which is which.
    let root = workspace("understood", &THE_ASYMMETRY, &[NARROWS_TO_THE_SKILL]);
    let (ok, text) = checked(&root);
    assert!(!ok, "under this specification the line is still refused:\n{text}");

    assert!(
        text.contains("this workspace has that under `skills:`"),
        "the checker must recognise that the name IS a skill:\n{text}"
    );
    assert!(
        !text.contains("or add a file `tools/refund-policy.yaml`"),
        "the fix still instructs a duplicate under the wrong kind:\n{text}"
    );
    assert!(
        text.contains("Do not add a file `tools/refund-policy.yaml`"),
        "refusing the old advice has to be said out loud — an author who has been \
         given it once will reach for it again:\n{text}"
    );
    // And the half a list of choices cannot give them: where a skill IS named.
    assert!(
        text.contains("`uses:` is the line that names one"),
        "the diagnostic must say which line accepts the name they wrote:\n{text}"
    );
    let _ = std::fs::remove_dir_all(root.parent().unwrap());
}

#[test]
fn the_line_that_may_name_a_kind_is_read_from_the_specification_and_not_from_the_checker() {
    // The same tree under a specification in which NOTHING names a skill. If
    // `uses:` were written down in Rust the sentence would not move, and the next
    // author would be sent to a line that cannot hold their name. Invariant F-1:
    // no capability-affecting literal buried in the core.
    //
    // This also pins the distinction that this module's own first version got
    // wrong. WHERE the name lives is a fact about the tree and must survive a
    // specification that refers to nothing; WHICH LINE may name one is a fact
    // about the specification and may honestly be "none".
    let root = workspace(
        "derived",
        // All three, because "nothing in this specification names a skill" has to
        // be true of the whole file — `variant.may-use:` names one too now, and
        // leaving it would have the checker honestly offer a line that this
        // rewritten specification really does have.
        &[
            ("agent", "uses", "[tools]"),
            ("stage", "may-use", "[tools, agents]"),
            ("variant", "may-use", "[tools]"),
        ],
        &[NARROWS_TO_THE_SKILL],
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "the line is still refused under this specification:\n{text}");
    assert!(
        text.contains("this workspace has that under `skills:`"),
        "where the name lives is a fact about the tree and does not move:\n{text}"
    );
    assert!(
        !text.contains("is the line that names one"),
        "no field in this specification names a skill, so offering one would be advice \
         that cannot be followed:\n{text}"
    );
    let _ = std::fs::remove_dir_all(root.parent().unwrap());
}

#[test]
fn a_name_the_workspace_has_nowhere_is_still_told_which_file_to_create() {
    // The other half, and the reason this is a narrowing rather than a
    // replacement: for a name that genuinely does not exist, "add a file" is the
    // correct instruction and the only one that gets the author unstuck.
    let root = workspace(
        "nowhere",
        &THE_ASYMMETRY,
        &[("loops/careful.yaml", "      - zendesk\n", "      - stripe\n")],
    );
    let (ok, text) = checked(&root);
    assert!(!ok, "a tool nobody declared must still be caught:\n{text}");
    assert!(
        text.contains("there is no such entry in `tools:` or `agents:`"),
        "for a genuinely new name the old sentence is the true one:\n{text}"
    );
    assert!(
        text.contains("or add a file `tools/stripe.yaml`"),
        "the file to create is what gets this author unstuck:\n{text}"
    );
    let _ = std::fs::remove_dir_all(root.parent().unwrap());
}

#[test]
fn the_asymmetry_closes_with_one_line_of_specification_and_no_rust() {
    // A stage's `may-use:` exists to NARROW what its agent already has. An agent
    // has what its `uses:` line gives it, so `may-use:` must be able to draw from
    // every set `uses:` draws from — otherwise there is a thing an agent may use
    // that no stage of its loop can mention, which is not a narrowing but a hole.
    //
    // This is the evidence for that edit rather than an assertion about which
    // state `spec/schema.yaml` is in, because the specification is a shared file
    // and the edit belongs to whoever integrates this round. What is proved here
    // is the part that would otherwise be taken on trust: the edit is one line,
    // it needs no Rust, and it is sufficient — the tree that could not be written
    // before loads cleanly after, with the rest of the specification untouched.
    let root = workspace(
        "closed",
        &[("agent", "uses", "[tools, skills]"), ("stage", "may-use", "[tools, skills, agents]")],
        &[NARROWS_TO_THE_SKILL],
    );
    let (ok, text) = checked(&root);
    assert!(
        ok,
        "with `may-use:` drawing from the same sets as `uses:`, a stage narrowing to \
         the written refund policy has to load:\n{text}"
    );
    let _ = std::fs::remove_dir_all(root.parent().unwrap());
}

#[test]
fn the_specification_this_binary_ships_lets_a_stage_narrow_to_a_skill() {
    // The integration signal, and the only test here that can fail while
    // everything it is about is correct. `spec/schema.yaml` has one writer per
    // round; until the line above lands on `stage.may-use`, the shipped binary
    // still tells an author to copy their refund policy into `tools/`, and every
    // other test in this file has proved that against a patched copy.
    //
    // One line, and it is the line `the_asymmetry_closes_with_one_line_of_
    // specification_and_no_rust` above has already loaded a real tree with.
    let text = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let agent_may = names_line(&text, "agent", "uses");
    let stage_may = names_line(&text, "stage", "may-use");
    let missing: Vec<&str> = agent_may
        .iter()
        .filter(|k| !stage_may.contains(*k))
        .copied()
        .collect();
    assert!(
        missing.is_empty(),
        "an agent may use {agent_may:?} and a stage of its loop may only narrow to \
         {stage_may:?}, so {missing:?} is a kind the agent has that no stage can name. \
         fix: in spec/schema.yaml, under `stage:` → `fields:` → `may-use:`, write \
         `names: [tools, skills, agents]`"
    );
}

/// The kinds one field's `names:` line covers, read out of the specification
/// text by the same pin `set_names` uses.
fn names_line<'a>(spec: &'a str, group: &str, field: &str) -> Vec<&'a str> {
    let (from, eol) = names_span(spec, group, field);
    spec[from..eol]
        .trim()
        .trim_start_matches('[')
        .trim_end_matches(']')
        .split(',')
        .map(str::trim)
        .collect()
}

#[test]
fn narrowing_to_a_kind_a_line_cannot_hold_never_ends_in_two_copies_of_one_document() {
    // The guarantee stated without reference to skills, because the pairing that
    // found it is not the pairing that will find the next one. Every kind this
    // workspace keeps documents under is written on a line that cannot hold it,
    // and no resulting fix may say "make a file" — that instruction is only ever
    // right for a name the workspace does not already have.
    //
    // `then: answered:` is the line used because it can hold exactly one kind
    // (its own loop's stages) and therefore collides with every other.
    for kind in ["tools", "agents", "skills", "policies", "questions", "loops", "resources"] {
        let name = first_entry_of(kind);
        let root = workspace(
            &format!("copies-{kind}"),
            &THE_ASYMMETRY,
            &[("loops/careful.yaml", "      answered: reply\n", &format!("      answered: {name}\n"))],
        );
        let (ok, text) = checked(&root);
        assert!(!ok, "[{kind}] routing a stage at a {kind} entry must be caught:\n{text}");
        assert!(
            text.contains(&format!("this workspace has that under `{kind}:`")),
            "[{kind}] the author is not told where their name actually lives:\n{text}"
        );
        assert!(
            !text.contains(&format!("add a file `{kind}/{name}.yaml`")),
            "[{kind}] the author is told to copy a document they already have:\n{text}"
        );
        let _ = std::fs::remove_dir_all(root.parent().unwrap());
    }
}

/// One name the worked example really keeps under `kind`, read from the tree so
/// this file holds no list of its own to drift.
fn first_entry_of(kind: &str) -> String {
    let out = pact()
        .args(["show", repo().join("examples/refund-desk").to_str().unwrap()])
        .output()
        .expect("pact show runs");
    let doc: serde_json::Value = serde_json::from_slice(&out.stdout).expect("show prints json");
    let map = doc.get(kind).and_then(|m| m.as_object()).unwrap_or_else(|| {
        panic!("the worked example keeps nothing under `{kind}:`, so this case proves nothing")
    });
    map.keys().next().expect("at least one entry").clone()
}

/// A workflow is called and run by name, as an agent and a program are (02W
/// §2.3 `call:`), so a name two of them share is refused at the workflow:
/// `call: sorter` and a run of `sorter` could not tell which one was meant.
#[test]
fn a_workflow_may_not_take_a_name_an_agent_already_has() {
    let dst = every_shape("agent-clash");
    std::fs::write(
        dst.join("workflows/sorter.yaml"),
        "description: Sorts.\nstarts-at: go\nsteps:\n  go:\n    does: call\n    call: ledger/read-invoice\n",
    )
    .unwrap();
    let (ok, text) = loaded(&dst);
    assert!(!ok, "{text}");
    assert!(text.contains("rule: loader/a-name-the-workspace-already-has"), "{text}");
    assert!(text.contains("'sorter' is an agent and a workflow"), "{text}");
    assert!(text.contains("the workflow to `sorter-flow`"), "{text}");
    // Told once, at the workflow — not again at the stage that calls it.
    assert_eq!(text.matches("a-name-the-workspace-already-has").count(), 1, "{text}");
}

/// A program a workflow shares its name with is refused the same way, at the
/// workflow.
#[test]
fn a_workflow_may_not_take_a_name_a_program_already_has() {
    let dst = every_shape("program-clash");
    write_program(&dst, "recheck");
    let (ok, text) = loaded(&dst);
    assert!(!ok, "{text}");
    assert!(text.contains("rule: loader/a-name-the-workspace-already-has"), "{text}");
    assert!(text.contains("'recheck' is a program and a workflow"), "{text}");
    assert!(text.contains("workflows/recheck.yaml"), "told at the workflow:\n{text}");
    assert_eq!(text.matches("a-name-the-workspace-already-has").count(), 1, "{text}");
}

/// No workflow is involved, so the clash is told where it bites: at the
/// `call:` that could mean the agent or the program.
#[test]
fn a_call_to_a_name_an_agent_and_a_program_share_is_refused_at_the_call() {
    let dst = every_shape("call-clash");
    write_program(&dst, "sorter");
    let (ok, text) = loaded(&dst);
    assert!(!ok, "{text}");
    assert!(text.contains("rule: loader/a-name-the-workspace-already-has"), "{text}");
    assert!(text.contains("'sorter' is an agent and a program"), "{text}");
    assert!(text.contains("workflows/invoices.yaml"), "told at the call:\n{text}");
}

/// `pact check` with the shipped specification.
fn loaded(root: &Path) -> (bool, String) {
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

/// A copy of `tests/trees/a-workflow-of-every-shape`.
fn every_shape(name: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-name-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_tree(&repo().join("tests/trees/a-workflow-of-every-shape"), &dst);
    dst
}

/// A program `name`, declared as `tests/trees/a-desk-with-a-program` declares one.
fn write_program(root: &Path, name: &str) {
    let src = repo().join("tests/trees/a-desk-with-a-program/programs/check-window");
    copy_tree(&src, &root.join("programs").join(name));
}

fn copy_tree(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_tree(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}
