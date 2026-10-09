//! **P8 — a program an agent may use without wrapping it in a tool.**
//!
//! P6 made a program reachable through a tool's action, which is right whenever
//! the call needs governing: `needs-a-person:`, `spends-money:`,
//! `same-request-key:`, `bind:` and `inspects:` all apply to it unchanged, so
//! the whole approval algebra composes with programs for free.
//!
//! For a pure calculation that is ceremony. Working out whether a date is inside
//! a window needs a tool file, a `connect:` line, an action, and a resource —
//! four files to reach six lines of arithmetic that cannot touch anything.
//!
//! So `uses:` names a program directly, and the program is offered to the model
//! as itself: its `takes:` is the argument list, its `answers-with:` the result.
//!
//! **The rule that makes the shortcut safe is `determinism: pure`.** A pure
//! program works only from what it is given — it observes nothing and changes
//! nothing — so there is no act for an approval gate to be about, and nothing an
//! `inspects:` line could usefully look at. Anything else keeps its tool: a
//! program that may read the outside world, or answer differently the second
//! time, is exactly the kind of call the governance vocabulary exists for, and
//! letting it in through the short door would be the shortcut quietly becoming
//! the way round the gate.
//!
//! Fixture: `tests/trees/a-desk-that-uses-a-program/`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> String {
    format!(
        "{}/../../tests/trees/a-desk-that-uses-a-program",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn run(args: &[&str]) -> (Option<i32>, String, String) {
    let out = pact().args(args).output().expect("runs");
    (
        out.status.code(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

fn broken(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-use-prog-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&tree()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not found in {file}"
        );
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

/// An agent names a program the way it names a tool, and the tree is four files
/// shorter for it.
#[test]
fn an_agent_may_name_a_pure_program_in_uses() {
    let (code, out, err) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(
        code,
        Some(0),
        "this is the shape the shortcut is FOR:\n{out}{err}"
    );
}

/// A program that is not pure keeps its tool.
///
/// The shortcut exists because a pure program has nothing for a gate to be
/// about. Take that away and the same line is a way round the governance
/// vocabulary — a call that may read the outside world or answer differently
/// twice, reached with no action, no `reads-only:`, and nowhere to write
/// `needs-a-person:`.
#[test]
fn a_program_that_is_not_pure_may_not_be_named_directly() {
    for word in ["deterministic", "nondeterministic"] {
        let dst = broken(
            &format!("impure-{word}"),
            &[(
                "programs/check-window/program.yaml",
                "determinism: pure",
                &format!("determinism: {word}"),
            )],
        );
        let (code, out, err) = run(&["check", &dst]);
        let said = format!("{out}{err}");
        assert_eq!(
            code,
            Some(1),
            "`{word}` must not take the short door:\n{said}"
        );
        assert!(
            said.contains("loader/only-a-pure-program-is-used-directly"),
            "{said}"
        );
        assert!(said.contains("check-window"), "name it:\n{said}");
        assert!(
            said.contains("actions:") || said.contains("action"),
            "and say what to do instead — wrap it in a tool:\n{said}"
        );
        let _ = std::fs::remove_dir_all(&dst);
    }
}

/// The positive control: the same tree, pure, loads clean.
#[test]
fn the_same_tree_left_pure_loads_clean() {
    let (code, out, err) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(
        code,
        Some(0),
        "the refusals above prove nothing unless this passes:\n{out}{err}"
    );
}

/// A program named in `uses:` is a program something points at.
///
/// `nothing-points-at-it` warns about a definition nothing reaches, and `uses:`
/// is now one of the ways of reaching one — so a directly-used program must not
/// draw that warning.
#[test]
fn a_program_named_in_uses_is_not_reported_as_unreached() {
    let (_, out, err) = run(&["check", &tree()]);
    let said = format!("{out}{err}");
    assert!(!said.contains("nothing-points-at-it"), "{said}");
}

/// A name in `uses:` that is nothing at all is still refused, and the message
/// now offers programs among the places it looked.
#[test]
fn a_name_that_is_nothing_is_still_refused() {
    let dst = broken(
        "nonesuch",
        &[("agents/desk/agent.yaml", "- check-window", "- check-windo")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("schema/no-such-name"), "{said}");
    assert!(
        said.contains("programs"),
        "programs is one of the places it looked:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}
