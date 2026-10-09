//! The authored path for `key-names:` — the real binary, the real
//! specification, the real worked example.
//!
//! Measured on a copy of `examples/refund-desk` before the mechanism existed,
//! with `agents/refund-desk/agent.yaml` changed from `policy-checker:` to
//! `polcy-checker:` and `agents/refund-desk/teamwork.yaml` changed from
//! `policy-checker: 60%` to `polcy-checker: 60%`:
//!
//! ```text
//! $ pact check <copy>
//! OK — <copy> loaded cleanly (468 settings).
//! $ echo $?
//! 0
//! ```
//!
//! What happened instead of a diagnostic: `harness.py` offered `polcy-checker`
//! to the model as somebody it could ask, and gated it
//! `waiting-for-another-agent` because no such agent exists — so the run parks
//! for an answer that never comes. And `Pool.share_of` (`delegation.py`) looked
//! up the real `policy-checker`, found nothing, and handed them 0.0 while the
//! typo held 60% of the pot. Both are the failure class `names:` was added to
//! end, arriving at run time, in another language, in a process the support lead
//! of decision D13 never starts.
//!
//! Held from the CLI on purpose. `pact check` is the only tool that reader runs,
//! so a refusal that does not arrive here does not arrive — and a unit test that
//! builds its own schema proves the mechanism works while saying nothing about
//! whether the author's line reaches it.

use std::path::{Path, PathBuf};
use std::process::Command;

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn example() -> PathBuf {
    repo().join("examples/refund-desk")
}

/// The line this round could not land itself: `spec/schema.yaml` has one writer
/// per round and it was not this one.
///
/// Once it is in the shipped specification this returns the file untouched, so
/// the guarantees below go on being held against what really ships rather than
/// against a copy nobody uses.
const TEAM_KEYS: (&str, &str) = (
    "      team:\n        type: map of text\n",
    "        key-names: agents\n",
);

/// The same line for `teamwork.shares` — applied only when nothing else already
/// refuses that name. See `only_one_thing_refuses_a_share_written_for_a_stranger`.
const SHARE_KEYS: (&str, &str) = (
    "      shares:\n        type: map of percent\n",
    "        key-names: ^team\n",
);

/// Whether a hand-written check in the loader already holds `shares:` to the
/// team beside it. Read from the source rather than assumed, because the two
/// constructs were built in the same round and either could be the one that
/// ships — what must never happen is both.
fn the_loader_already_holds_shares_to_the_team() -> bool {
    std::fs::read_to_string(repo().join("crates/pact-loader/src/teamwork.rs"))
        .unwrap_or_default()
        .contains("loader/share-for-someone-not-on-the-team")
}

fn specification() -> PathBuf {
    let shipped = repo().join("spec/schema.yaml");
    let text = std::fs::read_to_string(&shipped).expect("the specification is readable");

    let mut wanted: Vec<(&str, &str)> = vec![TEAM_KEYS];
    if !the_loader_already_holds_shares_to_the_team() {
        wanted.push(SHARE_KEYS);
    }

    let mut amended = text;
    let mut changed = false;
    for (anchor, line) in wanted {
        let block = format!("{anchor}{line}");
        if amended.contains(&block) {
            continue;
        }
        assert_eq!(
            amended.matches(anchor).count(),
            1,
            "the specification moved under this test: {anchor:?} is no longer written once"
        );
        amended = amended.replace(anchor, &block);
        changed = true;
    }
    if !changed {
        return shipped;
    }
    let to = std::env::temp_dir().join(format!("pact-key-names-spec-{}.yaml", std::process::id()));
    std::fs::write(&to, amended).unwrap();
    to
}

/// A copy of the worked example with `edits` applied, as (file, from, to).
fn copy_of_the_example(name: &str, edits: &[(&str, &str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-key-names-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&example(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(
            text.contains(from),
            "the worked example drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replace(from, to)).unwrap();
    }
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

/// Run `pact check` over `root` against the specification, and return
/// everything the author would see.
fn check(root: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .env("PACT_SPEC", specification())
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

#[test]
fn a_teammate_whose_name_has_no_agent_folder_is_refused_at_check_time() {
    // `agent.team`'s own help says "Give each one a folder under `agents/`".
    // A teammate with no folder is exactly the mistake that help warns about,
    // and until now nothing anywhere caught it.
    let root = copy_of_the_example(
        "no-such-teammate",
        &[(
            "agents/refund-desk/agent.yaml",
            "  policy-checker: Checks",
            "  polcy-checker: Checks",
        )],
    );
    let (ok, said) = check(&root);

    assert!(!ok, "a teammate with no agent must be refused:\n{said}");
    // By this mechanism and not by a neighbouring one: `pact check` grew several
    // teamwork rules this round, and a test that only asks "was it refused"
    // would go on passing with `key-names:` deleted.
    assert!(
        said.contains("rule: schema/no-such-name"),
        "the key check must be what fired:\n{said}"
    );
    assert!(
        said.contains("polcy-checker"),
        "name what is wrong:\n{said}"
    );
    assert!(
        said.contains("agent.yaml:"),
        "name the file and the line:\n{said}"
    );
    // The fix has to be typeable, and it has to name what does exist — "no such
    // agent" without the list is a dead end for a reader who cannot grep a tree.
    assert!(said.contains("  fix: "), "no fix offered:\n{said}");
    assert!(
        said.contains("policy-checker"),
        "offer the spelling that works:\n{said}"
    );
    assert!(
        said.contains("fraud-checker"),
        "offer every name that works:\n{said}"
    );
    // And the shape the kind really takes. The fix used to say
    // `agents/polcy-checker.yaml` — the flat form — while `team:`'s own help says
    // *"Give each one a folder under `agents/`"*, so one question had two
    // answers. The template is per kind now: a tool is one file, a skill is a
    // folder with a `SKILL.md`, an agent is a folder with an `agent.yaml`.
    assert!(
        said.contains("agents/polcy-checker/agent.yaml"),
        "offer where a genuinely new teammate goes, in the shape the help promises:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_share_written_against_a_misspelt_teammate_is_refused_at_check_time() {
    // The line that costs money. `divides-the-budget: by-share` with
    // `polcy-checker: 60%` gives the real member a slice of 0.0 and leaves the
    // typo holding the majority of the pot.
    //
    // Stated as the guarantee and not as the mechanism, because two things can
    // hold it and only one of them may — see the test below. What must be true
    // either way is that the author is told, here, in words they can act on.
    let root = copy_of_the_example(
        "share-for-nobody",
        &[(
            "agents/refund-desk/teamwork.yaml",
            "  policy-checker: 60%",
            "  polcy-checker: 60%",
        )],
    );
    let (ok, said) = check(&root);

    assert!(
        !ok,
        "a share for somebody who is not on the team must be refused:\n{said}"
    );
    assert!(
        said.contains("polcy-checker"),
        "name what is wrong:\n{said}"
    );
    assert!(
        said.contains("teamwork.yaml:"),
        "name the file and the line:\n{said}"
    );
    assert!(said.contains("  fix: "), "no fix offered:\n{said}");
    assert!(
        said.contains("policy-checker"),
        "offer the spelling that works:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn only_one_thing_refuses_a_share_written_for_a_stranger() {
    // Two constructs can hold the line above, and this round grew both of them
    // at once: `key-names: ^team` on `teamwork.shares` here, and
    // `shares_name_the_team` in `crates/pact-loader/src/teamwork.rs` there. They
    // say the same thing about the same line, so having both means one typo
    // produces two messages — which is the "one mistake said twice" this
    // codebase refuses everywhere else (see `loader/wait-with-no-deadline`,
    // reported once however many lines put the question).
    //
    // The loader's is the richer message and it ships. So the `key-names:` line
    // for `shares:` is built, held under test in
    // `crates/pact-schema/tests/a_map_key_is_a_name_like_any_other.rs`, and
    // deliberately NOT applied — and this is what stops the two from being
    // switched on together by a later edit that only looks at one of them.
    let spec = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let loader = std::fs::read_to_string(repo().join("crates/pact-loader/src/teamwork.rs"))
        .unwrap_or_default();

    let schema_owns_it = spec.contains(&format!("{}{}", SHARE_KEYS.0, SHARE_KEYS.1));
    let loader_owns_it = loader.contains("loader/share-for-someone-not-on-the-team");

    assert!(
        schema_owns_it || loader_owns_it,
        "nothing refuses a share written for somebody who is not on the team. Either add \
         `{}` under `shares:` in spec/schema.yaml, or restore `shares_name_the_team` in \
         crates/pact-loader/src/teamwork.rs.",
        SHARE_KEYS.1.trim()
    );
    assert!(
        !(schema_owns_it && loader_owns_it),
        "two things now refuse a share written for a stranger, so one typo produces two \
         messages. Keep one: either delete `{}` from `shares:` in spec/schema.yaml, or \
         delete `shares_name_the_team` (and its call in `check_one`, and its test) from \
         crates/pact-loader/src/teamwork.rs.",
        SHARE_KEYS.1.trim()
    );
}

#[test]
fn the_worked_example_still_loads_cleanly_with_both_key_checks_in_force() {
    // A check that refuses correct documents is not a check. Every name under
    // `team:` is an agent in this workspace and every name under `shares:` is on
    // that team, so nothing here may change.
    let root = copy_of_the_example("untouched", &[]);
    let (ok, said) = check(&root);
    assert!(ok, "the worked example must stay valid:\n{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn nothing_a_key_check_says_assumes_programming_knowledge() {
    let root = copy_of_the_example(
        "jargon",
        &[(
            "agents/refund-desk/teamwork.yaml",
            "  policy-checker: 60%",
            "  polcy-checker: 60%",
        )],
    );
    let (_, said) = check(&root);
    let text = said.to_lowercase();
    for word in [
        "enum",
        "variant",
        "deserialize",
        "serde",
        "unwrap",
        "panic",
        "trait",
        "struct",
        "vec<",
        "option<",
        "key-value",
        "hashmap",
        "stack trace",
        "null pointer",
    ] {
        assert!(
            !text.contains(word),
            "diagnostic assumes programming knowledge ('{word}'):\n{said}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_specification_this_binary_ships_asks_for_the_key_check_on_a_team() {
    // The one thing the round that built the mechanism could not do for itself.
    // `spec/schema.yaml` has a single writer per round, so the line that puts
    // the mechanism to work is handed over rather than applied — and this is
    // what makes the handover visible instead of a note in a report.
    //
    // Without it `key-names:` is a capability nothing uses. It would pass every
    // test above, because every test above amends the specification itself, and
    // it would refuse nothing in any workspace anybody actually has. That is the
    // shape this project has shipped five rounds running: a field added,
    // resolved, and read by nobody.
    //
    // Only `agent.team` is demanded here. `teamwork.shares` is the same line
    // over a set that something else already holds — see
    // `only_one_thing_refuses_a_share_written_for_a_stranger`.
    let text = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let (anchor, line) = TEAM_KEYS;
    assert!(
        text.contains(&format!("{anchor}{line}")),
        "`key-names:` is built and reaches nothing a workspace has. spec/schema.yaml still \
         owes one line — insert `{}` so the block reads:\n\n{anchor}{line}",
        line.trim()
    );
}
