//! **P8 wave 2 — memory is readable and writable from the format.**
//!
//! `remembers:` has been the closest thing PACT has to a variable since it
//! landed: declared, lifetime-scoped, and write-guarded by `never-from:`. What
//! it could not do is take part in a call. A tool argument could be bound from
//! `run-inputs.<name>` — something the surrounding system supplied for this run —
//! and from nothing else, so a fact the conversation had ESTABLISHED could only
//! reach a tool by the model retyping it, which is exactly the value you least
//! want the model choosing.
//!
//! Two lines close it, in opposite directions:
//!
//!   * `bind: { account: remembers.verified-account }` — the argument is filled
//!     from what the run remembers. The model cannot see it, name it or change
//!     it, which is the whole of what `bind:` is for.
//!   * `remember-as: last-order-seen` — what the action answered is kept under a
//!     name the author declared.
//!
//! **The write-back is guarded by a line that already existed.** `never-from:`
//! names the sources that may never write to a state, `tool output` first among
//! them, and its own help says why: letting a tool result become remembered
//! instruction is how a single poisoned page becomes permanent. So
//! `remember-as:` naming a state that refuses tool output is refused where the
//! author wrote it — the guard keeps its teeth by default, and relaxing it is
//! one visible line in the state's own file rather than an argument nobody has.
//!
//! Together they are a variable a run can read and write, and still not one it
//! can branch on: F4's refusal stands, because nothing here is a condition.
//!
//! Fixture: `tests/trees/a-desk-that-remembers/`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> String {
    format!("{}/../../tests/trees/a-desk-that-remembers", env!("CARGO_MANIFEST_DIR"))
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
    let dst = std::env::temp_dir().join(format!("pact-remem-{name}-{}", std::process::id()));
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

/// Both directions load, and this is the positive control for every refusal.
#[test]
fn a_desk_may_read_and_write_what_it_remembers() {
    let (code, out, err) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(code, Some(0), "this is the shape the feature is FOR:\n{out}{err}");
}

/// The old binding still works exactly as it did.
///
/// `remembers.` is a SECOND source, not a replacement — the worked example binds
/// from `run-inputs.` and must go on doing so.
#[test]
fn binding_from_a_run_input_is_untouched() {
    let example = format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"));
    let (code, out, err) = run(&["check", &example, "--deny-warnings"]);
    assert_eq!(code, Some(0), "{out}{err}");
}

/// A binding from a fact the agent does not remember is refused, with what it does.
#[test]
fn binding_from_a_fact_nothing_remembers_is_refused() {
    let dst = broken(
        "no-such-fact",
        &[("tools/orders.yaml", "remembers.verified-account", "remembers.verified-acount")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/no-such-remembered-fact"), "{said}");
    assert!(said.contains("verified-account"), "name the one that is there:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// A namespace that is neither is still refused by shape, and now offers both.
#[test]
fn a_binding_from_no_namespace_at_all_is_still_refused() {
    let dst = broken("nonamespace", &[("tools/orders.yaml", "remembers.verified-account", "whatever.i.like")]);
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/not-a-binding"), "{said}");
    // The SENTENCE names both namespaces, because both are legal wherever a
    // binding is written.
    assert!(said.contains("`run-inputs:`"), "{said}");
    assert!(said.contains("`remembers:`"), "{said}");
    // The FIX names what this tree actually has, and nothing it has not — a fix
    // offering `run-inputs.<something>` to a desk that supplies none would be a
    // line the author cannot type.
    assert!(said.contains("`remembers.verified-account`"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// Writing a tool's answer into a state that refuses tool output is refused.
///
/// The guard already existed and had nothing that could trip it: `never-from:`
/// named the sources that may never write, and no line in the format was a
/// write. `remember-as:` is that line, so the guard now bites where the author
/// can see it — and it bites by DEFAULT, which is the half that matters.
#[test]
fn writing_a_tools_answer_where_tool_output_may_never_go_is_refused() {
    let dst = broken(
        "poisoned",
        &[("tools/orders.yaml", "remember-as: last-order-seen", "remember-as: verified-account")],
    );
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/a-tool-may-not-write-there"), "{said}");
    assert!(said.contains("verified-account"), "name the fact:\n{said}");
    assert!(said.contains("never-from"), "and the line that says so:\n{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// Relaxing the guard is one visible line, and then it is allowed.
///
/// The refusal above must be the author's own decision to reverse — otherwise it
/// is a wall rather than a guard, and the next person works around it.
#[test]
fn taking_the_guard_off_is_one_line_and_then_it_is_allowed() {
    let dst = broken(
        "relaxed",
        &[
            ("agents/desk/agent.yaml", "    never-from:\n      - tool output\n", ""),
            ("tools/orders.yaml", "remember-as: last-order-seen", "remember-as: verified-account"),
        ],
    );
    let (code, out, err) = run(&["check", &dst, "--deny-warnings"]);
    assert_eq!(code, Some(0), "the author may decide this:\n{out}{err}");
    let _ = std::fs::remove_dir_all(&dst);
}

/// Keeping an answer under a name nothing declares is refused.
#[test]
fn remembering_something_under_a_name_nothing_declares_is_refused() {
    let dst = broken("noname", &[("tools/orders.yaml", "remember-as: last-order-seen", "remember-as: last-order-scene")]);
    let (code, out, err) = run(&["check", &dst]);
    let said = format!("{out}{err}");
    assert_eq!(code, Some(1), "{said}");
    assert!(said.contains("loader/no-such-remembered-fact"), "{said}");
    assert!(said.contains("last-order-seen"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}
