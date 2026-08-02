//! **Where a tool reaches, checked where the author is.**
//!
//! A `tool` reaches one place, named on one of three lines: `connect:` for a
//! server in `resources:`, `url:` for an address, `says:` for a model.
//!
//! `runs-as:` used to sit in front of those three as a word with four choices,
//! and it was read by nothing anywhere — not the loader, not an adapter, and not
//! the worked example, which has never written it. Two of the four (`prompt`,
//! `built-in`) named ways of running that nothing in this distribution carries
//! out, so a tool written either way was offered to the model and answered
//! `error: no tool named ...` on the first call, with no diagnostic at check
//! time and nothing on the run's own list of what it could not enforce. It is
//! deleted (R60); the question is asked here, of the lines that carry it.
//!
//! Everything below goes through the AUTHORED path — the shipped worked example,
//! one line edited, the real binary run over the real tree — because that is the
//! only path that can tell whether the author's line reaches anything. A test
//! that builds the document inline proves the check works and says nothing about
//! whether `pact check` runs it.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply one edit, return the temp root.
///
/// The same helper `authoring_surface.rs` uses, and for the same reason: the
/// fixture has to be the tree an author is handed, so a drift in the example is
/// a failure here rather than a test that quietly stops being about anything.
fn broken(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-reach-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    assert!(text.contains(from), "fixture drifted: {from:?} not in {file}");
    std::fs::write(&p, text.replace(from, to)).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
    }
}

/// What `pact check <root>` printed, both streams, and whether it refused.
fn checked(root: &str) -> (String, bool) {
    let out = pact().arg("check").arg(root).output().expect("pact runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (text, out.status.success())
}

#[test]
fn the_shipped_example_says_where_every_one_of_its_tools_reaches() {
    // The half that matters most, and the half a check like this usually gets
    // wrong: a correct tree must still load. Both of the example's tools name a
    // server, so nothing here has anything to say about them.
    let (said, ok) = checked(&example());
    assert!(ok, "the worked example must still load cleanly:\n{said}");
    assert!(!said.contains("reaches"), "nothing to say about a correct tree:\n{said}");
}

#[test]
fn a_tool_with_no_line_saying_where_it_reaches_is_refused_before_anything_runs() {
    // Reproduced before this check existed: this exact edit printed
    // "OK — … loaded cleanly (491 settings)." and exited 0, and a run then
    // answered every refund with `error: no tool named 'payments'`.
    let root = broken("nowhere", "tools/payments.yaml", "connect: payments-server", "");
    let (said, ok) = checked(&root);
    assert!(!ok, "a tool that can never run must not load cleanly:\n{said}");
    assert!(said.contains("tools/payments.yaml"), "the file is named:\n{said}");
    assert!(
        said.contains("no `connect:`, no `url:` and no `says:`"),
        "which of the three are present is what the author has to know:\n{said}"
    );
    assert!(
        said.contains("error: no tool named 'payments'"),
        "the sentence names what the author would otherwise meet only at run time:\n{said}"
    );
    // The fix has to be a line that can be typed, not a description of one.
    for typeable in ["connect: ", "url: ", "method: post", "says: "] {
        assert!(said.contains(typeable), "the fix must offer {typeable:?}:\n{said}");
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_tool_naming_two_places_to_reach_is_refused_and_both_lines_are_shown() {
    // Which one a runtime uses was decided by nothing written down anywhere, so
    // two runtimes reading one folder could legitimately do different things —
    // the one thing a portable artifact may not permit.
    let root = broken(
        "two",
        "tools/payments.yaml",
        "connect: payments-server",
        "connect: payments-server\nurl: host/payments-api\nmethod: post",
    );
    let (said, ok) = checked(&root);
    assert!(!ok, "two ways to reach is an unanswered question, not a setting:\n{said}");
    assert!(said.contains("tools/payments.yaml"), "the file is named:\n{said}");
    assert!(said.contains("`connect:` and `url:`"), "both are named:\n{said}");
    assert!(said.contains("already set here"), "the first line is shown beside the second:\n{said}");
    assert!(said.contains("Delete `url:`"), "a typeable fix:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_tool_calling_an_address_with_nothing_saying_which_kind_of_call_is_refused() {
    // The one obligation `runs-as:` really carried, moved onto the field that
    // carries it. `needed-when: {url: web-request}` demanded `url:` when a word
    // said `web-request`; nothing ever demanded `method:` at all, so an address
    // with no kind of call beside it loaded clean.
    let root = broken(
        "no-method",
        "tools/payments.yaml",
        "connect: payments-server",
        "url: host/payments-api",
    );
    let (said, ok) = checked(&root);
    assert!(!ok, "an address with no kind of call cannot be made:\n{said}");
    assert!(said.contains("'url' is set, but 'method' is not."), "{said}");
    assert!(said.contains("get, post, put, patch, delete"), "the choices are offered:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_word_that_used_to_stand_in_front_of_the_three_is_no_longer_a_setting() {
    // The deletion itself, on the authored path. While `runs-as:` was in the
    // specification this line loaded clean and did nothing whatever; now it is a
    // setting the `tool` kind has not got, reported where it was typed with the
    // settings that do exist. If the field ever comes back, this fails.
    let root = broken(
        "runs-as",
        "tools/payments.yaml",
        "connect: payments-server",
        "runs-as: connected-system\nconnect: payments-server",
    );
    let (said, ok) = checked(&root);
    assert!(!ok, "a setting the specification has not got must be refused:\n{said}");
    assert!(said.contains("runs-as"), "the word the author typed is quoted back:\n{said}");
    assert!(said.contains("tools/payments.yaml"), "the file is named:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_tool_that_puts_its_question_to_a_model_needs_no_server_at_all() {
    // The check counts to one, not to "has a `connect:`". A tool whose whole
    // implementation is a wording sent to a model is a complete tool, and
    // refusing it would make `says:` a field that cannot be used on its own —
    // which is the shape the deleted word left `prompt` in.
    let root = broken(
        "says",
        "tools/payments.yaml",
        "connect: payments-server",
        "says: Decide whether this refund is within policy.",
    );
    let (said, ok) = checked(&root);
    assert!(ok, "one way to reach is enough, whichever one it is:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}
