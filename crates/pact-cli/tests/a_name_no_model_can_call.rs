//! The authored path for `loader/name-a-model-cannot-call` — the real binary,
//! the real worked example, nothing built in Rust that an author did not type.
//!
//! Measured on a copy of `examples/refund-desk` before the check existed, with
//! `tools/Get Weather.yaml` added (`description:`, `url:`, `method:`) and
//! `- Get Weather` appended to the agent's `uses:` list:
//!
//! ```text
//! $ pact check <copy>
//! OK — <copy> loaded cleanly (497 settings).
//! $ echo $?
//! 0
//! ```
//!
//! …and the same document, lowered through `AgentSpec.from_document`, offered
//! the model `{'name': 'Get Weather'}`. Every provider holds a callable name to
//! `^[a-zA-Z0-9_-]{1,64}$` and refuses the whole request when one does not
//! match, so that workspace's FIRST model call is a guaranteed failure — passed,
//! with a success message, by the only command decision D13's reader runs.
//!
//! Held from the CLI on purpose, and against the shipped example rather than a
//! fixture written here. A unit test that hands the checker a `Node` it built
//! itself proves the checker works and says nothing about whether the author's
//! file reaches it — which is the shape this project has shipped five rounds
//! running.

use std::path::{Path, PathBuf};
use std::process::Command;

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// A complete, valid tool document — everything the specification asks of one,
/// so the only thing wrong with the workspace is the NAME. A fixture that is
/// also missing a required field would let this file pass while the check it
/// exists for did nothing.
/// The address is host-resolved on purpose. This file is about what a tool may
/// be CALLED, and the worked example it is grafted onto writes
/// `allow-egress: []` — so an `https://` address here would make every test in
/// this file assert a workspace that breaks its own stated boundary, and the
/// failure would be reported as a naming problem. `host/weather` is the
/// convention the flagship already uses for `host/payments-mcp`.
const WEATHER: &str = "description: Tells you the weather.\n\
                       url: host/weather\n\
                       method: get\n";

fn example() -> PathBuf {
    repo().join("examples/refund-desk")
}

/// A copy of the worked example, ready to be broken in one specific way.
fn copy_of_the_example(name: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-callable-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&example(), &dst);
    dst
}

fn copy_dir(src: &Path, dst: &Path) {
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

/// Replace `from` with `to` in one file of the copy, refusing to pass quietly if
/// the example has moved underneath this test.
fn edit(root: &Path, file: &str, from: &str, to: &str) {
    let p = root.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    assert!(text.contains(from), "the worked example drifted: {from:?} not in {file}");
    std::fs::write(&p, text.replace(from, to)).unwrap();
}

/// Whole-word test, so "capital" does not read as "api" and "structural" does
/// not read as "struct". Borrowed from `deliberate_refusals.rs`, which holds the
/// refusal ledger to the same bar.
fn says_word(haystack: &str, word: &str) -> bool {
    let words: Vec<&str> =
        haystack.split(|c: char| !c.is_ascii_alphanumeric()).filter(|s| !s.is_empty()).collect();
    let wanted: Vec<&str> =
        word.split(|c: char| !c.is_ascii_alphanumeric()).filter(|s| !s.is_empty()).collect();
    words.windows(wanted.len().max(1)).any(|w| w == wanted)
}

/// Run `pact check` over `root` and return everything the author would see.
fn check(root: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

#[test]
fn a_tool_whose_file_name_has_a_space_in_it_is_refused_at_check_time() {
    let root = copy_of_the_example("tool-with-a-space");
    // Exactly the two lines an author types to add a tool: the file, and the
    // `uses:` line that puts it in front of the model.
    std::fs::write(root.join("tools/Get Weather.yaml"), WEATHER).unwrap();
    edit(root.as_path(), "agents/refund-desk/agent.yaml", "  - refund-policy", "  - refund-policy\n  - Get Weather");

    let (ok, said) = check(&root);

    assert!(!ok, "a name every provider refuses must not pass `pact check`:\n{said}");
    // By this mechanism and not by a neighbouring one. `pact check` grew several
    // loader walks this round and a test that only asks "was it refused" would
    // go on passing with this one deleted.
    assert!(
        said.contains("rule: loader/name-a-model-cannot-call"),
        "the name check must be what fired:\n{said}"
    );
    assert!(said.contains("'Get Weather'"), "name what is wrong:\n{said}");
    // The file and the line, which is the whole point of doing this in the
    // loader rather than at run time in another language.
    assert!(said.contains("Get Weather.yaml:"), "name the file and the line:\n{said}");
    // A typeable fix that spells the corrected name, in BOTH places the author
    // has to retype it. "Use a valid name" is a dead end for a reader who cannot
    // look the rule up.
    assert!(
        said.contains("Rename the file to `tools/get-weather.yaml`"),
        "spell the corrected file name:\n{said}"
    );
    assert!(
        said.contains("change the `uses:` line to `- get-weather`"),
        "spell the corrected `uses:` line:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_teammate_whose_folder_name_has_a_capital_letter_is_refused_at_check_time() {
    // The same fate by the same route: `ir.py` lowers `team:` keys exactly as it
    // lowers `tools:` keys, and `harness.py` puts both in the one list the model
    // chooses a name out of.
    let root = copy_of_the_example("teammate-with-a-capital");
    std::fs::rename(root.join("agents/fraud-checker"), root.join("agents/Fraud Checker")).unwrap();
    edit(root.as_path(), "agents/refund-desk/agent.yaml", "  fraud-checker: Looks", "  Fraud Checker: Looks");
    edit(root.as_path(), "agents/refund-desk/teamwork.yaml", "  fraud-checker: 40%", "  Fraud Checker: 40%");

    let (ok, said) = check(&root);

    assert!(!ok, "a teammate the model cannot name must be refused:\n{said}");
    assert!(
        said.contains("rule: loader/name-a-model-cannot-call"),
        "the name check must be what fired:\n{said}"
    );
    assert!(said.contains("'Fraud Checker'"), "name what is wrong:\n{said}");
    assert!(said.contains("capital letter"), "say why, in the author's own terms:\n{said}");
    assert!(said.contains("agent.yaml:"), "name the file and the line:\n{said}");
    assert!(
        said.contains("Rename the folder to `agents/fraud-checker`"),
        "an agent is a folder — say so, and spell it:\n{said}"
    );
    assert!(
        said.contains("change the `Fraud Checker:` line under `team:` to `fraud-checker:`"),
        "spell the corrected `team:` line:\n{said}"
    );
    // The sibling line on the same name. Renaming the teammate and leaving the
    // share behind hands the renamed member 0.0 of the pot, in silence —
    // `Pool.share_of` looks the share up by name.
    assert!(
        said.contains("teamwork.yaml:"),
        "the share written against the same name has to move with it:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn one_bad_name_produces_one_message_and_not_one_per_line_that_uses_it() {
    // Three lines name the teammate — the folder, `team:`, `shares:` — and it is
    // one mistake. The other locations arrive as notes on the one diagnostic,
    // which is how every other check in this loader reports a mistake written in
    // more than one place.
    let root = copy_of_the_example("said-once");
    std::fs::rename(root.join("agents/fraud-checker"), root.join("agents/Fraud Checker")).unwrap();
    edit(root.as_path(), "agents/refund-desk/agent.yaml", "  fraud-checker: Looks", "  Fraud Checker: Looks");
    edit(root.as_path(), "agents/refund-desk/teamwork.yaml", "  fraud-checker: 40%", "  Fraud Checker: 40%");

    let (_, said) = check(&root);
    assert_eq!(
        said.matches("rule: loader/name-a-model-cannot-call").count(),
        1,
        "one mistake gets one message:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_worked_example_still_loads_cleanly_with_the_name_check_in_force() {
    // A check that refuses correct documents is not a check. Every tool key and
    // every teammate key in the shipped example is already a name a model can
    // call, so nothing here may change.
    let root = copy_of_the_example("untouched");
    let (ok, said) = check(&root);
    assert!(ok, "the worked example must stay valid:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn nothing_the_name_check_says_assumes_programming_knowledge() {
    // The reader of decision D13 is a support lead. A message that says
    // "identifier", "regex" or "string" has told them nothing they can act on —
    // and the shape of the rule is the one thing here that invites exactly that
    // vocabulary, because the rule really is a regular expression.
    let root = copy_of_the_example("jargon");
    std::fs::write(root.join("tools/Get Weather.yaml"), WEATHER).unwrap();
    edit(root.as_path(), "agents/refund-desk/agent.yaml", "  - refund-policy", "  - refund-policy\n  - Get Weather");

    let (_, said) = check(&root);
    let text = said.to_lowercase();
    for word in [
        "regex", "regular expression", "identifier", "string", "ascii", "alphanumeric", "slug",
        "enum", "variant", "deserialize", "serde", "unwrap", "panic", "trait", "struct", "vec",
        "option", "hashmap", "stack trace", "api", "endpoint", "400",
    ] {
        assert!(
            !says_word(&text, word),
            "the diagnostic assumes programming knowledge ('{word}'):\n{said}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn retyping_what_the_fix_says_leaves_the_workspace_loading_cleanly() {
    // The property a fix cannot be allowed to get wrong. A corrected name that
    // is itself uncallable, or that collides with something, would send the
    // author round the same loop a second time — so the test does what the fix
    // says, literally, and asks the binary again.
    let root = copy_of_the_example("retyped");
    std::fs::write(root.join("tools/Get Weather.yaml"), WEATHER).unwrap();
    edit(root.as_path(), "agents/refund-desk/agent.yaml", "  - refund-policy", "  - refund-policy\n  - Get Weather");
    let (ok, said) = check(&root);
    assert!(!ok, "the mistake has to be there before the fix means anything:\n{said}");

    // Exactly the two things the fix names, and nothing else.
    std::fs::rename(root.join("tools/Get Weather.yaml"), root.join("tools/get-weather.yaml"))
        .unwrap();
    edit(root.as_path(), "agents/refund-desk/agent.yaml", "  - Get Weather", "  - get-weather");

    let (ok, said) = check(&root);
    assert!(ok, "doing what the fix says must end the problem, not move it:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}
