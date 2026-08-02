//! `interceptor.when` names MOMENTS, plural — held from the tool the author runs.
//!
//! The field held one address for a round, so a rule that had to run at two
//! moments had to be written twice, and the worked example shipped the proof.
//! Measured on the tree as it stood:
//!
//! ```text
//! $ diff examples/refund-desk/interceptors/redact-card-numbers.yaml \
//!        examples/refund-desk/interceptors/redact-card-numbers-in-tool-calls.yaml
//! ```
//!
//! differed in exactly two settings, `description:` and `when:`. Same
//! `applies-to:`, same `may:`, the same two sentences copied out word for word.
//! A card number that came back out of a Zendesk ticket and went into a
//! `payments` argument is a different MOMENT, not a different rule.
//!
//! Every test here runs the real binary against a real tree, because the thing
//! being held is what `pact check` tells the person who typed it. Each message
//! below has a twin in `adapters/python/tests/test_one_rule_at_several_moments.
//! py`: the two halves are in different languages and an author must not be able
//! to tell which one refused them.

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

/// Copy the worked example and write one extra interceptor into it, attached to
/// the desk. Returns the temp root.
fn with_rule(name: &str, body: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-moments-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&example(), &dst);
    std::fs::write(dst.join(format!("interceptors/{name}.yaml")), body).unwrap();
    let agent = dst.join("agents/refund-desk/agent.yaml");
    let text = std::fs::read_to_string(&agent).unwrap();
    assert!(text.contains("  - stop-runaway-refunds"), "fixture drifted: {agent:?}");
    std::fs::write(
        &agent,
        text.replace("  - stop-runaway-refunds", &format!("  - stop-runaway-refunds\n  - {name}")),
    )
    .unwrap();
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

fn checking(root: &std::path::Path) -> String {
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    String::from_utf8_lossy(&out.stdout).into_owned()
}

#[test]
fn the_worked_example_holds_one_card_number_rule_and_names_two_moments_on_it() {
    // Both halves, because either alone would be a lie. A tree with one file and
    // one moment passes a test that counts files while leaving `payments`
    // unprotected; a tree with two files covers both moments and is the
    // duplication this change removes.
    let dir = example().join("interceptors");
    let mut files: Vec<String> = std::fs::read_dir(&dir)
        .unwrap()
        .flatten()
        .map(|e| e.file_name().to_string_lossy().into_owned())
        .collect();
    files.sort();
    assert_eq!(
        files,
        vec!["redact-card-numbers.yaml", "stop-runaway-refunds.yaml"],
        "one rule about card numbers, not one per moment"
    );

    let text = std::fs::read_to_string(dir.join("redact-card-numbers.yaml")).unwrap();
    assert!(text.contains("- step.message.before"), "{text}");
    assert!(text.contains("- step.tool.before"), "{text}");
    // The comment the deleted file carried is the ARGUMENT for the second
    // moment, and losing it would leave the second line unexplained.
    assert!(
        text.contains("came back out") || text.contains("read out of Zendesk"),
        "the reason the tool-call moment is needed must survive the merge:\n{text}"
    );
}

#[test]
fn a_moment_that_is_not_one_is_refused_wherever_in_the_list_it_sits() {
    // A list checked only at its head quietly accepts a typo on every line after
    // the first — and the line after the first is exactly where a rule's second
    // moment lives.
    for (name, from, to) in [
        ("head", "- step.message.before", "- step.banana.before"),
        ("tail", "- step.tool.before\n", "- step.banana.before\n"),
    ] {
        let dst =
            std::env::temp_dir().join(format!("pact-moments-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dst);
        copy_dir(&example(), &dst);
        let p = dst.join("interceptors/redact-card-numbers.yaml");
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(text.contains(from), "fixture drifted: {from:?}");
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();

        let said = checking(&dst);
        assert!(
            said.contains("'banana' is not a thing PACT knows about"),
            "the {name} of the list must be checked too:\n{said}"
        );
        assert!(said.contains("redact-card-numbers.yaml:"), "must name the file and line:\n{said}");
        assert!(said.contains("Change it to one of: message, reasoning, tool"), "{said}");
        let _ = std::fs::remove_dir_all(&dst);
    }
}

#[test]
fn a_rule_no_named_moment_can_carry_out_is_still_refused_when_when_is_a_list() {
    // The refusal a list must not lose, and the one it very nearly did. The
    // schema reads `when:` to decide whether a sentence can be carried out, and
    // it read it with `as_str()` — which answers nothing for a list. An empty
    // answer means "bound anywhere", so writing a second moment would have been
    // a way past this check entirely: `stop and say "…"` counts tool calls out
    // of a payload only `step.tool.before` supplies, and bound elsewhere it
    // loads, answers "no" forever, and every refund after the first goes through.
    let root = with_rule(
        "wrong-moments",
        "description: Counts refunds where nothing is counting them.\n\
         when:\n\
         \x20 - step.message.before\n\
         \x20 - turn.message.after\n\
         may:\n\
         \x20 - stop-the-run\n\
         rules:\n\
         \x20 - if payments is called more than 1 time in one run, stop and say \"twice\"\n",
    );
    let said = checking(&root);
    assert!(said.contains("rule: schema/rule-at-the-wrong-moment"), "{said}");
    // Both moments named, so the author can see which lines are the problem
    // rather than being told the file is wrong somewhere.
    assert!(
        said.contains("`step.message.before`, `turn.message.after`"),
        "the refusal must name every moment the rule was bound to:\n{said}"
    );
    assert!(said.contains("Change `when:` to one of: step.tool.before"), "{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_sentence_one_of_the_named_moments_can_carry_out_is_accepted() {
    // The composition the list exists for: redact at two moments and count tool
    // calls at the one that knows the tool. Demanding that EVERY named moment
    // carry EVERY sentence would refuse this and send the author straight back
    // to two files, which is what this change removes.
    let root = with_rule(
        "both-at-once",
        "description: Hides at two moments and counts at one.\n\
         when:\n\
         \x20 - step.message.before\n\
         \x20 - step.tool.before\n\
         may:\n\
         \x20 - hide-values\n\
         \x20 - stop-the-run\n\
         rules:\n\
         \x20 - replace anything that looks like a phone number with \"[gone]\"\n\
         \x20 - if payments is called more than 1 time in one run, stop and say \"twice\"\n",
    );
    let said = checking(&root);
    assert!(said.contains("loaded cleanly"), "{said}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn one_moment_written_on_the_when_line_with_no_dash_still_loads() {
    // Nobody has to learn a list to write their first interceptor.
    // `interceptors/stop-runaway-refunds.yaml` still says `when: step.tool.before`
    // on one line, and it is the one-element list it means.
    let text =
        std::fs::read_to_string(example().join("interceptors/stop-runaway-refunds.yaml")).unwrap();
    assert!(text.contains("\nwhen: step.tool.before\n"), "{text}");
    // And a bare address that nothing reaches is still refused, so the scalar
    // spelling is not a way round the reachability check either.
    let root = with_rule(
        "bare-and-wrong",
        "description: One moment, and the wrong one.\n\
         when: session.tool.before\n\
         may:\n\
         \x20 - hide-values\n\
         rules:\n\
         \x20 - replace anything that looks like a phone number with \"[gone]\"\n",
    );
    let said = checking(&root);
    assert!(said.contains("rule: schema/nothing-happens-there"), "{said}");
    // The wording says "no rule is handed the run at X" and not "nothing in a
    // run ever reaches X", because the second is false wherever a WATCH binds
    // at an address an interceptor may not — `step.tool.completed` was exactly
    // that until it joined this field's `reaches:` list, and the message told
    // an author their address did not exist while another field in the same
    // tree accepted it.
    assert!(
        said.contains("no rule is handed the run at 'session.tool.before'"),
        "{said}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_list_of_moments_with_nothing_in_it_is_refused_rather_than_bound_to_nothing() {
    // The hole a list opens if nothing closes it, and it is opened by this very
    // change. `required:` asks only whether the line is there, which was the
    // whole answer while `when:` was one address — `when:` with nothing after it
    // is a missing value and was already refused. As a list, `when: []`
    // satisfied `required:` and bound the rule to no moment at all, so every
    // sentence in the file loaded and did nothing, silently. Measured before the
    // check below existed: `OK — loaded cleanly (480 settings)`, exit 0, on a
    // worked example whose card-number rule protected nothing.
    let dst = std::env::temp_dir().join(format!("pact-moments-empty-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&example(), &dst);
    let p = dst.join("interceptors/redact-card-numbers.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    let from = "when:\n  - step.message.before\n  - step.tool.before\n";
    assert!(text.contains(from), "fixture drifted:\n{text}");
    std::fs::write(&p, text.replace(from, "when: []\n")).unwrap();

    let said = checking(&dst);
    assert!(said.contains("rule: schema/nothing-written-here"), "{said}");
    assert!(
        said.contains("'when' is here with nothing in it, so it says nothing at all"),
        "{said}"
    );
    // And the address it offers is one a run really arrives at. Built out of the
    // first word of each position it read `session.message.requested` — three
    // good words in the right order that nothing ever emits — so an author who
    // typed the fix met `schema/nothing-happens-there` on the next run.
    assert!(
        said.contains("Write at least one line under it: `- step.message.before`"),
        "the fix must be an address that is really reached:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn the_moments_a_rule_may_name_are_the_ones_the_harness_really_hands_it() {
    // The schema's `reaches:` list under `interceptor.when` and `interceptors.py`'s
    // `WIRED` table are two copies of one fact, and this is what keeps them one
    // fact. They cannot be folded into a single copy — an adapter is handed the
    // loaded document and never the specification (invariant P-1) — but a copy
    // nothing compares is a copy that drifts, and the drift shows up as
    // `pact check` accepting a moment the harness then refuses, in another
    // language, in a process the author never starts.
    //
    // The observe half has had this test since `watch.when` gained its list
    // (`watching_a_run.rs`). The change half had none, which is the half where a
    // moment nobody reaches means a card number is not hidden.
    let schema = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let doc = pact_doc::parse_yaml(&schema, camino::Utf8Path::new("spec/schema.yaml")).unwrap();
    let mut listed: Vec<String> = doc
        .get("groups")
        .and_then(|g| g.get("interceptor"))
        .and_then(|w| w.get("fields"))
        .and_then(|f| f.get("when"))
        .and_then(|w| w.get("reaches"))
        .and_then(pact_doc::Node::as_list)
        .expect("interceptor.when carries a `reaches:` list")
        .iter()
        .filter_map(|n| n.as_str().map(str::to_string))
        .collect();

    let python = std::fs::read_to_string(
        repo().join("adapters/python/src/pact_adapters/interceptors.py"),
    )
    .unwrap();
    let block = python
        .split_once("WIRED: Mapping[str, Carries] = {")
        .expect("interceptors.py declares WIRED")
        .1
        .split_once("\n}")
        .unwrap()
        .0;
    let mut wired: Vec<String> =
        block.split('"').skip(1).step_by(2).map(str::to_string).collect();

    listed.sort();
    wired.sort();
    assert!(!wired.is_empty(), "nothing parsed out of WIRED — it changed shape");
    assert_eq!(
        listed, wired,
        "the schema and the harness disagree about which moments hand a rule the run"
    );
}
