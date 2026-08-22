//! **Every way of reaching a carried program is held to the rules that reach claims.**
//!
//! P6 put a program behind a tool, and `programs.rs` asked two questions of that
//! arrangement: is there a locked room, and can that room run this kind of
//! program. P8 then opened seven more doors to the same body — `uses:`,
//! `projects-with:`, `checked-by:`, `decided-by:`, a metric's `program:` address,
//! a rewriting interceptor sentence, and `does: run-code` — and only the first
//! two of those inherited a rule.
//!
//! Two promises were left written and unkept.
//!
//! **Purity.** `spec/schema.yaml` says of `decided-by:` that the program it
//! names is "refused unless it is `pure`", and says the same thing of the two
//! rewriting sentences — where it is the whole argument for giving
//! `change-the-answer` and `change-the-request` back to authors after R24 took
//! them away. Neither was enforced anywhere. A `nondeterministic` router loaded
//! cleanly, which is a run whose path through the loop is not the same twice; a
//! `nondeterministic` rewriter loaded cleanly, which is the mid-run change to
//! the words that §6 recorded as the reason to refuse the power in the first
//! place.
//!
//! **The engine.** `resource.engines:` says it "is checked in both directions: a
//! program whose engine no sandbox here hosts is refused", and its own help
//! promises that refusal comes "when the file is read, rather than on the first
//! call". It came on the first call for every reach but one. A workspace whose
//! only room runs `wasm`, carrying a `python` program that `uses:` names, is the
//! exact "loads and does nothing" arrangement `programs.rs` exists to remove.
//!
//! # What is deliberately NOT required here
//!
//! `checked-by:` and a metric's `program:` address are not held to purity, and
//! that is a decision rather than an omission: neither line claims it. A check on
//! an answer may want to look something up — an account number held against a
//! ledger is the shape the field's own help describes — and a grader that reads a
//! stored rubric is an ordinary grader. Purity is required where the *document*
//! says it is required, and nowhere else, because a restriction nothing asked for
//! costs an author a capability and buys nobody anything.
//!
//! Fixture: `tests/trees/a-desk-whose-program-decides/`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> String {
    format!("{}/../../tests/trees/a-desk-whose-program-decides", env!("CARGO_MANIFEST_DIR"))
}

fn run(args: &[&str]) -> (Option<i32>, String) {
    let out = pact().args(args).output().expect("runs");
    (
        out.status.code(),
        format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    )
}

/// A copy of the fixture with some lines changed, so the original is never edited.
fn broken(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-reach-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&tree()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(text.contains(from), "fixture drifted: {from:?} not found in {file}");
        std::fs::write(&p, text.replace(from, to)).unwrap();
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

/// The positive control every refusal below depends on.
///
/// One tree, three doors to a carried program: a tool's action, a `decided-by:`
/// line, and a rewriting interceptor sentence. All three are correct, so it must
/// load with nothing to say.
#[test]
fn a_tree_that_reaches_a_program_three_ways_loads_clean() {
    let (code, said) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(code, Some(0), "this is the shape the doors are FOR:\n{said}");
}

/// A program named only inside a sentence is a program something names.
///
/// `nothing-points-at-it` asks "does any line name this?" by looking at whole
/// string values, and a rewriting rule is one prose sentence with the name
/// inside it. So the one authoring path §8.5 gives for `change-the-answer` drew
/// a warning saying the program "never takes effect" — about a reference that
/// resolves, in a repository whose shipped standard is `--deny-warnings` clean.
#[test]
fn a_program_named_only_in_a_rewriting_sentence_is_not_reported_as_unreached() {
    let (_, said) = run(&["check", &tree()]);
    assert!(
        !said.contains("nothing-points-at-it"),
        "the sentence names it, and the resolver agrees — it resolves:\n{said}"
    );
}

/// Where the run goes next has to be the same twice.
#[test]
fn a_program_that_decides_where_the_run_goes_must_be_pure() {
    for word in ["deterministic", "nondeterministic"] {
        let dst = broken(
            &format!("router-{word}"),
            &[(
                "programs/pick-next/program.yaml",
                "determinism: pure",
                &format!("determinism: {word}"),
            )],
        );
        let (code, said) = run(&["check", &dst]);
        assert_eq!(code, Some(1), "`{word}` must not route a loop:\n{said}");
        assert!(said.contains("loader/only-a-pure-program-decides"), "{said}");
        assert!(said.contains("pick-next"), "name the program:\n{said}");
        assert!(said.contains("pure"), "and say what to write instead:\n{said}");
        let _ = std::fs::remove_dir_all(&dst);
    }
}

/// A rewrite has to be as readable as the instructions it sits beside.
///
/// This is the sentence R24's withdrawal rests on. If the program behind it may
/// answer differently the second time, the withdrawal's whole argument — "what
/// the rewrite does is as readable as the instructions it sits beside, and the
/// same twice" — is untrue of the file that was accepted.
#[test]
fn a_program_that_rewrites_what_is_said_must_be_pure() {
    for word in ["deterministic", "nondeterministic"] {
        let dst = broken(
            &format!("rewriter-{word}"),
            &[(
                "programs/house-style/program.yaml",
                "determinism: pure",
                &format!("determinism: {word}"),
            )],
        );
        let (code, said) = run(&["check", &dst]);
        assert_eq!(code, Some(1), "`{word}` must not rewrite an answer:\n{said}");
        assert!(said.contains("loader/only-a-pure-program-rewrites"), "{said}");
        assert!(said.contains("house-style"), "name the program:\n{said}");
        let _ = std::fs::remove_dir_all(&dst);
    }
}

/// A program no room here can run, reached without a tool.
///
/// The tool path has asked this since P6, by following that tool's `connect:`.
/// A `decided-by:` line has no tool and so no `connect:`, and the question is
/// still answerable: the workspace declares its rooms, and if not one of them
/// runs this kind of program then nothing here can.
#[test]
fn a_program_no_room_here_can_run_is_refused_however_it_is_reached() {
    for (name, file) in [
        ("router", "programs/pick-next/program.yaml"),
        ("rewriter", "programs/house-style/program.yaml"),
    ] {
        let dst = broken(&format!("engine-{name}"), &[(file, "engine: wasm", "engine: python")]);
        let (code, said) = run(&["check", &dst]);
        assert_eq!(code, Some(1), "a {name} nothing can run must be said out loud:\n{said}");
        assert!(said.contains("loader/nothing-here-can-run-that-program"), "{said}");
        assert!(said.contains("python"), "say what it needs:\n{said}");
        assert!(said.contains("local-sandbox"), "and which room was asked:\n{said}");
        let _ = std::fs::remove_dir_all(&dst);
    }
}

/// The same question, asked of the short door.
///
/// `uses:` was the reach the engine promise was measured to miss: a workspace
/// whose room runs `wasm` only, carrying a `python` program the agent names
/// directly, printed "loaded cleanly".
#[test]
fn a_program_an_agent_names_directly_must_be_one_a_room_here_runs() {
    let dst = broken(
        "engine-uses",
        &[
            ("programs/pick-next/program.yaml", "engine: wasm", "engine: typescript"),
            ("agents/desk/agent.yaml", "  - refund-window\n", "  - refund-window\n  - pick-next\n"),
        ],
    );
    let (code, said) = run(&["check", &dst]);
    assert_eq!(code, Some(1), "the short door asks the same question:\n{said}");
    assert!(said.contains("loader/nothing-here-can-run-that-program"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A workspace that declares no room at all is left alone.
///
/// This is the seam P7 shipped: PACT declares a locked room and whatever runs
/// your agents supplies it, so a tree with no `resources/` is not a broken tree
/// — it is one whose room comes from the host. The honest report about it
/// already exists where the run is, and refusing here would break the shipped
/// tree that demonstrates the shortcut.
#[test]
fn a_workspace_with_no_room_at_all_is_not_refused_for_it() {
    let no_room =
        format!("{}/../../tests/trees/a-desk-that-uses-a-program", env!("CARGO_MANIFEST_DIR"));
    let (code, said) = run(&["check", &no_room, "--deny-warnings"]);
    assert_eq!(code, Some(0), "the host supplies the room for this one:\n{said}");
}

/// The positive control, again, after all the mutations above.
#[test]
fn the_fixture_itself_was_never_edited() {
    let (code, said) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(code, Some(0), "the refusals prove nothing unless this still passes:\n{said}");
}

/// A stage that writes code needs somewhere to run it, said before the run.
///
/// `docs/27` states it as a rule — a `does: run-code` stage is "legal only when
/// the agent's workspace declares a sandbox resource" — and the adapter test's
/// own header repeats it: "it requires a sandbox at check time — a `does:
/// run-code` stage in a workspace with no locked room is refused before anything
/// runs, rather than discovered on the first step."
///
/// Nothing in the loader had ever heard of `run-code`. The only thing holding
/// the rule was a halt at run time, which is a true sentence arriving in the
/// wrong place: the author is gone, a customer is waiting, and the file it is
/// about loaded cleanly.
///
/// This is the one reach where the absence of a room is refused rather than
/// passed over. Every other reach names a program the author WROTE, and the room
/// for it may reasonably come from the host; a `run-code` stage names nothing at
/// all, so a workspace with no room is a stage that can never be anything but
/// the halt.
#[test]
fn a_stage_that_writes_code_needs_a_room_declared_to_run_it() {
    let dst = broken(
        "run-code-no-room",
        &[(
            "loops/works-it-out.yaml",
            "  think-again:\n    does: check-its-work",
            "  think-again:\n    does: run-code",
        )],
    );
    // The room this tree does declare, taken away — the stage stays.
    std::fs::remove_dir_all(std::path::Path::new(&dst).join("resources")).unwrap();
    // And the program that needed it, so the refusal under test is the only one.
    std::fs::remove_dir_all(std::path::Path::new(&dst).join("programs")).unwrap();
    let (code, said) = run(&["check", &dst]);
    assert_eq!(code, Some(1), "a stage that can only ever halt is not a stage:\n{said}");
    assert!(said.contains("loader/nothing-here-can-run-that-program"), "{said}");
    assert!(said.contains("run-code") || said.contains("writes code"), "{said}");
    assert!(said.contains("sandbox"), "and say what to add:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// The same stage, with a room, loads.
#[test]
fn a_stage_that_writes_code_loads_where_a_room_is_declared() {
    let dst = broken(
        "run-code-with-room",
        &[(
            "loops/works-it-out.yaml",
            "  think-again:\n    does: check-its-work",
            "  think-again:\n    does: run-code",
        )],
    );
    let (code, said) = run(&["check", &dst]);
    assert_eq!(code, Some(0), "the refusal above proves nothing unless this passes:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// The one thing that makes the `no-code` badge mean anything about programs.
///
/// `workspace.programs`' own comment states the D14 bargain: "no core capability
/// may REQUIRE a program, a workspace that carries one simply does not earn the
/// `no-code` badge, and deleting `programs/` must leave a working agent."
///
/// The badge is not a computed artifact and does not need to be. What makes the
/// sentence true is the TIER: every door into a carried program is `tier:
/// expert`, so the author D13 describes — who builds everything in YAML and
/// Markdown — never meets one, and every capability a program reaches has a
/// plain-words way to do the same thing written beside it. That is checkable,
/// and it was checked by nothing: `governance_is_complete` asks that every field
/// HAS a tier and never which tier this one has.
///
/// `description` is the exception and is core in every group in the
/// specification — it is the line you write first whatever you are writing, and
/// a group nobody core-tier reaches cannot be entered through it.
///
/// Mutation: change `workspace.programs`' tier to `core`. Red, naming the field.
#[test]
fn every_door_into_a_carried_program_is_priced_as_an_expert_one() {
    let text =
        std::fs::read_to_string(format!("{}/../../spec/schema.yaml", env!("CARGO_MANIFEST_DIR")))
            .expect("the specification is there");
    let doc = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml"))
        .expect("the specification parses");
    let groups = doc.get("groups").and_then(pact_doc::Node::as_map).expect("groups:");

    let tier = |group: &str, field: &str| -> String {
        groups
            .get(group)
            .and_then(|g| g.node.get("fields"))
            .and_then(pact_doc::Node::as_map)
            .and_then(|f| f.get(field))
            .and_then(|f| f.node.get("tier"))
            .and_then(pact_doc::Node::as_str)
            .unwrap_or_else(|| panic!("the specification declares `{group}.{field}` with a tier"))
            .to_owned()
    };

    // The door itself, and the room a program runs in.
    for (group, field) in [
        ("workspace", "programs"),
        ("resource", "engines"),
        ("resource", "asks-to-run"),
    ] {
        assert_eq!(
            tier(group, field),
            "expert",
            "`{group}.{field}` is a door into a carried program, and a core-tier door \
             is one the author D13 describes is expected to walk through"
        );
    }

    // And everything a program itself is made of, `description:` aside.
    for group in ["program", "program-fuel"] {
        let fields = groups
            .get(group)
            .and_then(|g| g.node.get("fields"))
            .and_then(pact_doc::Node::as_map)
            .unwrap_or_else(|| panic!("the specification declares the `{group}` kind"));
        for (name, _) in fields {
            if name == "description" {
                continue;
            }
            assert_eq!(
                tier(group, name),
                "expert",
                "`{group}.{name}` is part of writing a program, and it is priced as core"
            );
        }
    }
}
