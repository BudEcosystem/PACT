//! `evals:` on an agent must name checks that exist.
//!
//! Measured before this existed, on the worked example and nothing else:
//! changing `agents/refund-desk/agent.yaml`'s `evals: /evals/suite.yaml` to
//! `evals: /evals/suit.yaml` — a file that is not there — printed
//! `OK — examples/refund-desk loaded cleanly (468 settings).` and exited 0. The
//! agent then had no checks at all, which is the exact opposite of what the
//! author wrote the line to guarantee, and `pact check` — the only tool D13's
//! reader runs — said the tree was fine.
//!
//! Every other cross-reference on that same page already resolved: `policy:`,
//! `loop:`, `context-policy:`, `interceptors:` and `uses:` each produce
//! `schema/no-such-name` with the list of what does exist. This one was the
//! exception because it was written as a PATH, and `names:` resolves names.
//!
//! These run the real binary against a real tree, changing exactly one authored
//! line, because the thing under test is whether the author's line reaches the
//! checker — not whether the checker works when handed the right value.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn example() -> std::path::PathBuf {
    repo().join("examples/refund-desk")
}

/// The line `agent.evals` needs in `spec/schema.yaml` for this to bite, exactly
/// as it is written in the integration note.
const HOLDS_EVALS: &str = "names: pact:evals";

/// The specification to check against: the one this repository ships, with the
/// `names: pact:evals` line added if it is not there yet.
///
/// `spec/schema.yaml` has one writer per round and it is not this one, so the
/// line arrives with the integrator. Patching a copy here rather than skipping
/// the tests means the mechanism is exercised against the REAL schema and the
/// REAL worked example on both sides of that hand-off: once the line lands, the
/// replacement below finds it already present and does nothing.
fn spec_for(test: &str) -> std::path::PathBuf {
    let src = repo().join("spec/schema.yaml");
    let text = std::fs::read_to_string(&src).expect("the specification is readable");
    let patched = if text.contains(HOLDS_EVALS) {
        text
    } else {
        let anchor = "      evals:\n        type: text\n";
        assert!(
            text.contains(anchor),
            "the `agent.evals` field moved; update this fixture"
        );
        text.replacen(anchor, &format!("{anchor}        {HOLDS_EVALS}\n"), 1)
    };
    let dst = std::env::temp_dir().join(format!(
        "pact-spec-{test}-{}-{}.yaml",
        std::process::id(),
        test.len()
    ));
    std::fs::write(&dst, patched).unwrap();
    dst
}

/// Copy the worked example, apply `edits` as (file, from, to), return the root.
fn worked_example_with(test: &str, edits: &[(&str, &str, &str)]) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-evals-{test}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&example(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not found in {file}"
        );
        std::fs::write(&p, text.replace(from, to)).unwrap();
    }
    dst
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

/// Run `pact check` over `root` against the specification for `test`.
fn check(test: &str, root: &std::path::Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .env("PACT_SPEC", spec_for(test))
        .output()
        .expect("the binary runs");
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

#[test]
fn an_evals_line_pointing_at_a_file_that_is_not_there_is_refused_at_check_time() {
    let root = worked_example_with(
        "missing",
        &[(
            "agents/refund-desk/agent.yaml",
            "evals: /evals/suite.yaml",
            "evals: /evals/suit.yaml",
        )],
    );
    let (ok, text) = check("missing", &root);
    assert!(
        !ok,
        "a suite that is not there must stop the check:\n{text}"
    );
    assert!(text.contains("schema/no-such-name"), "{text}");
    assert!(
        text.contains("/evals/suit.yaml"),
        "must quote what the author wrote: {text}"
    );
    // And the alternative offered has to be the suite this tree really has, not
    // a general complaint. That value can only have come from reading the tree,
    // so this is also what fails if the checker stops reading it.
    assert!(
        text.contains("/evals/suite.yaml"),
        "must offer the suite that is there: {text}"
    );
}

#[test]
fn the_refusal_names_the_file_the_line_and_a_suite_that_does_exist() {
    // O7.3's four parts, on the one diagnostic this round adds: where, what,
    // why, and something to type. The last is the half a "no such suite"
    // message cannot leave out for a reader who cannot grep the tree.
    let root = worked_example_with(
        "four-parts",
        &[(
            "agents/refund-desk/agent.yaml",
            "evals: /evals/suite.yaml",
            "evals: /evals/suit.yaml",
        )],
    );
    let (_, text) = check("four-parts", &root);
    // The line is READ from the tree rather than written down here: pinning `29`
    // made this test fail the next time somebody added a comment to
    // `agent.yaml`, which is a change with no bearing on what is being asserted.
    let agent = std::fs::read_to_string(root.join("agents/refund-desk/agent.yaml")).unwrap();
    let line = agent
        .lines()
        .position(|l| l.starts_with("evals:"))
        .expect("the example still has an `evals:` line")
        + 1;
    assert!(
        text.contains(&format!("agents/refund-desk/agent.yaml:{line}:8")),
        "file, line and column: {text}"
    );
    assert!(
        text.contains("^^^"),
        "the caret must sit under the value: {text}"
    );
    assert!(
        text.contains("Change it to one of: /evals/suite.yaml, evals"),
        "the fix must name the suites that DO exist: {text}"
    );
    assert!(
        text.contains("write one in `evals/suite.yaml`"),
        "and what to do if the suite is genuinely new: {text}"
    );
}

#[test]
fn the_worked_example_is_still_accepted_exactly_as_it_is_written() {
    // The guard on the other side: a check that refuses a typo is worthless if
    // it also refuses the line the example ships.
    let (ok, text) = check("unchanged", &example());
    assert!(ok, "the worked example must stay valid:\n{text}");
}

#[test]
fn the_name_spelling_means_the_same_suite_as_the_path_spelling() {
    // The path is an alias, not a second mechanism: `evals/suite.yaml` is the
    // self file of `evals/`, so it loaded into the node `evals`, and both
    // spellings are one address (D2 — the tree is the document).
    let root = worked_example_with(
        "by-name",
        &[(
            "agents/refund-desk/agent.yaml",
            "evals: /evals/suite.yaml",
            "evals: evals",
        )],
    );
    let (ok, text) = check("by-name", &root);
    assert!(ok, "the name spelling must be accepted too:\n{text}");
}

#[test]
fn an_evals_line_pointing_at_a_file_that_is_not_a_suite_is_refused() {
    // The path spelling made every file in the tree look like a possible
    // answer. Only the ones that loaded as checks are.
    let root = worked_example_with(
        "not-a-suite",
        &[(
            "agents/refund-desk/agent.yaml",
            "evals: /evals/suite.yaml",
            "evals: /policies/approvals.yaml",
        )],
    );
    let (ok, text) = check("not-a-suite", &root);
    assert!(!ok, "a policy is not a suite of checks:\n{text}");
    assert!(text.contains("schema/no-such-name"), "{text}");
    assert!(
        text.contains("/evals/suite.yaml"),
        "must offer the one that is: {text}"
    );
}

#[test]
fn naming_a_setting_inside_the_suite_is_not_naming_the_suite() {
    // Why the set of suites is supplied by the checker rather than resolved as
    // a map in the document: `evals:` is a set of settings, not a map of
    // suites, so a plain `names: evals` would have accepted its own field
    // names — `cases`, `rules`, `must-pass` — as if each were a suite.
    for inside in ["cases", "rules", "must-pass"] {
        let root = worked_example_with(
            "inside",
            &[(
                "agents/refund-desk/agent.yaml",
                "evals: /evals/suite.yaml",
                &format!("evals: {inside}"),
            )],
        );
        let (ok, text) = check("inside", &root);
        assert!(
            !ok,
            "'{inside}' is a setting inside the suite, not a suite:\n{text}"
        );
        assert!(
            text.contains("Change it to one of: /evals/suite.yaml, evals"),
            "and the two spellings that ARE the suite must be offered: {text}"
        );
    }
}

#[test]
fn deleting_the_only_suite_refuses_the_agent_that_points_at_it() {
    // The failure this round is about, from the other end. Before it, removing
    // every check in the workspace left `evals: /evals/suite.yaml` pointing at
    // nothing and `pact check` still said the tree was fine.
    let root = worked_example_with("no-suite", &[]);
    std::fs::remove_dir_all(root.join("evals")).unwrap();
    let (ok, text) = check("no-suite", &root);
    assert!(
        !ok,
        "an agent's checks cannot be deleted out from under it silently:\n{text}"
    );
    // And it must say so as a SENTENCE, not as a list of one phrase. The fix
    // used to read ``Change it to one of: nothing is declared yet — or write one
    // in `evals/suite.yaml` ``, which instructs the reader to type the words
    // "nothing is declared yet". A fix has to be typeable, and an empty set of
    // choices is not one.
    assert!(
        text.contains("Nothing is declared there yet."),
        "and the message must say the workspace has none: {text}"
    );
    assert!(
        !text.contains("Change it to one of:"),
        "a list of nothing is not a choice — it tells the reader to type a phrase: {text}"
    );
    assert!(
        text.to_lowercase()
            .contains("write one in `evals/suite.yaml`"),
        "with the file to write: {text}"
    );
}

#[test]
fn the_specification_ships_the_line_that_holds_evals_to_a_real_suite() {
    // The integration signal, and the only test here that can fail while the
    // mechanism is correct. `spec/schema.yaml` has one writer per round; until
    // `names: pact:evals` lands on `agent.evals`, every check above runs
    // against a patched copy and the shipped `pact` binary still accepts a
    // typo. Fix by adding one line — see the integration note.
    let text = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    // The AGENT's `evals:`, which holds a name. The workspace's `evals:` earlier
    // in the file holds the suite itself, and is a different field.
    let field = text
        .split("      evals:\n        type: text\n")
        .nth(1)
        .expect("the `agent.evals` field exists and is text");
    let block: String = field
        .lines()
        .take_while(|l| l.starts_with("        "))
        .collect::<Vec<_>>()
        .join("\n");
    assert!(
        block.contains(HOLDS_EVALS),
        "add `{HOLDS_EVALS}` under `agent.evals` in spec/schema.yaml. Without it \
         `evals: /evals/suit.yaml` loads clean and the agent has no checks. Got:\n{block}"
    );
}
