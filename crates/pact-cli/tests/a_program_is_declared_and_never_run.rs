//! **P6 — a program is a declaration, and checking one runs nothing.**
//!
//! Until now the only exact logic a PACT agent could reach was a server
//! somebody had to deploy. A skill could CARRY a script — `skills/<n>/scripts/`
//! — and PACT recorded that it was there and nothing else: a person ran it, by
//! hand, out of process. So the worked example's refund window is six lines of
//! date arithmetic that the model works out in its head, and gets wrong often
//! enough to matter.
//!
//! A `program` is that script, declared: what it takes, what it answers with,
//! what engine runs it, whether it is deterministic, and what it may spend. The
//! body is a folder of files beside it, recorded by name, media type, size and
//! fingerprint — and never opened.
//!
//! **Nothing here executes anything, and that is the whole point of the shape.**
//! R42 refused `runs-as: code` because it "would make `pact check` the thing
//! that decides whether a script is safe". That reason is answered rather than
//! outvoted: the checker validates the DECLARATION — that the shapes resolve,
//! that the fuel is written, that the engine is one the named sandbox hosts —
//! and decides nothing about safety. Safety belongs to the executor, which is a
//! `resource` the host supplies and a person consents to, exactly as an MCP
//! server is.
//!
//! R58 deleted `sandbox` from `resource-kind:` because it "had no field in this
//! kind that only they would use", and said each of the three would return "with
//! the fields it needs". It returns here with two: `engines:` and `asks-to-run:`.
//!
//! Fixture: `tests/trees/a-desk-with-a-program/`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> String {
    format!("{}/../../tests/trees/a-desk-with-a-program", env!("CARGO_MANIFEST_DIR"))
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
    let dst = std::env::temp_dir().join(format!("pact-prog-{name}-{}", std::process::id()));
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

/// The whole shape loads, and it is the positive control for every refusal below.
#[test]
fn a_desk_that_carries_a_program_loads_clean() {
    let (code, out, err) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(code, Some(0), "this is the shape the feature is FOR:\n{out}{err}");
}

/// The body is carried by name, type, size and fingerprint — never by contents.
#[test]
fn the_body_is_carried_as_files_and_not_as_settings() {
    let (_, shown, _) = run(&["show", &tree()]);
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("JSON");
    let body = &doc["programs"]["check-window"]["body"];
    let files = body["files"].as_array().expect("a body is a folder of files");
    let wasm = files
        .iter()
        .find(|f| f["$file"].as_str() == Some("check-window.wasm"))
        .expect("the body is carried");
    assert!(wasm["digest"].as_str().is_some_and(|d| d.len() == 64), "fingerprinted:\n{shown}");
    assert!(wasm["sizeBytes"].is_number(), "{shown}");
    // And the bytes are nowhere in the document.
    assert!(
        !shown.contains("a placeholder for the compiled program"),
        "a body's CONTENTS must never reach the document:\n{shown}"
    );
}

/// Checking a workspace that carries a program still runs nothing.
///
/// R5's rule, at the one moment it would be most tempting to break: the body is
/// right there and the declaration says what runs it. Four verbs, a body that
/// would write a file if anything ever executed it, and the file is not there.
#[test]
fn checking_a_program_does_not_run_it() {
    let dst = broken("purity", &[]);
    let canary = std::path::Path::new(&dst).join("canary-was-executed");
    let body = std::path::Path::new(&dst).join("programs/check-window/body");
    std::fs::write(
        body.join("hostile.py"),
        format!("open({:?}, 'w').write('executed')\n", canary.to_str().unwrap()),
    )
    .unwrap();
    for verb in ["check", "show", "waits", "discover"] {
        let _ = run(&[verb, &dst]);
        assert!(!canary.exists(), "`pact {verb}` ran a program it was only asked to read");
    }
    let _ = std::fs::remove_dir_all(&dst);
}

/// An action naming a program that is not there is refused, with the ones that are.
#[test]
fn an_action_naming_no_such_program_is_refused() {
    let dst = broken("no-such", &[("tools/refund-window.yaml", "program: check-window", "program: check-windo")]);
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("schema/no-such-name"), "{said}");
    assert!(said.contains("check-window"), "name the one that is there:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A sandbox that does not host the engine is refused before anything runs.
///
/// The author has written a program in one language and a locked room that
/// cannot run it. Nothing about that is discoverable at run time except as a
/// failure, so it is said here.
#[test]
fn a_sandbox_that_cannot_host_the_engine_is_refused() {
    let dst = broken("wrong-engine", &[("resources/local-sandbox.yaml", "  - wasm", "  - typescript")]);
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/nothing-here-can-run-that-program"), "{said}");
    assert!(said.contains("wasm"), "name the engine it needs:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A ceiling with no action is refused, exactly as every other ceiling is.
///
/// `when-it-runs-out:` is the one decision `limits:` refuses to guess, and a
/// program's fuel is a ceiling like any other — stopping silently, asking a
/// person and answering anyway are three different governance decisions.
#[test]
fn fuel_with_no_action_is_refused() {
    let dst = broken("no-action", &[("programs/check-window/program.yaml", "  when-it-runs-out: stop-and-say-so\n", "")]);
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("schema/missing-companion"), "{said}");
    assert!(said.contains("when-it-runs-out"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A program nothing calls is said out loud.
#[test]
fn a_program_nothing_calls_is_said_out_loud() {
    let dst = broken("unused", &[("tools/refund-window.yaml", "    program: check-window\n", "")]);
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(0), "a half-written tree still loads:\n{said}");
    assert!(said.contains("loader/nothing-points-at-it"), "{said}");
    assert!(said.contains("check-window"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// The consent question a sandbox names is a real wait a runtime can walk.
#[test]
fn the_consent_to_run_reaches_the_list_of_waits() {
    let (code, waits, err) = run(&["waits", &tree()]);
    assert_eq!(code, Some(0), "{waits}{err}");
    assert!(waits.contains("may-we-run"), "a runtime is obliged to walk this list:\n{waits}");
}
