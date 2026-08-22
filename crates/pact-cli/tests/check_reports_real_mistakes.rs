//! End-to-end: the mistakes a non-technical author actually makes must produce
//! diagnostics they can act on (D13 / O7.3).
//!
//! These run the real binary against a real tree, because the thing being
//! tested is the experience, not the unit.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the example, apply `edits` as (file, from, to), return the temp root.
fn broken(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-cli-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
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

#[test]
fn the_worked_example_passes_cleanly() {
    let out = pact().args(["check", &example()]).output().expect("runs");
    assert!(
        out.status.success(),
        "the example must stay valid:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
}

#[test]
fn a_typo_in_a_field_name_suggests_the_right_one() {
    let root = broken("typo", &[("workspace.yaml", "description:", "descriptoin:")]);
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success(), "must fail");
    assert!(text.contains("Did you mean 'description'?"), "{text}");
    assert!(text.contains("workspace.yaml:"), "must name the line: {text}");
}

#[test]
fn wrong_value_types_are_reported_per_file_with_a_typeable_fix() {
    let root = broken(
        "types",
        &[
            ("agents/refund-desk/limits.yaml", "finishes-within: 30s", "finishes-within: soon"),
            (
                "agents/refund-desk/limits.yaml",
                "cost-per-request-under: 0.05 USD",
                "cost-per-request-under: 0.05",
            ),
            ("agents/refund-desk/needs.yaml", "reasoning: careful", "reasoning: brilliant"),
        ],
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success());

    // Every one is found in a single pass — an author fixes them all at once.
    assert!(text.contains("Write it like `2s`"), "{text}");
    assert!(text.contains("Write it like `0.05 USD`"), "{text}");
    assert!(text.contains("Change it to one of: simple, steady, careful, deep"), "{text}");

    // Nested files are reached: the error is attributed to the file that has it,
    // not to the workspace root.
    assert!(text.contains("limits.yaml:"), "{text}");
    assert!(text.contains("needs.yaml:"), "{text}");
}

#[test]
fn a_join_policy_written_with_the_wrong_words_lists_the_right_ones() {
    // The mistakes a non-coder makes on `teamwork.yaml` are the ones this
    // catches: an invented word for how long to wait, and a share written as a
    // bare number because "60" looks like a percentage.
    let root = broken(
        "teamwork",
        &[
            ("agents/refund-desk/teamwork.yaml", "waits-for: everyone", "waits-for: all-of-them"),
            ("agents/refund-desk/teamwork.yaml", "policy-checker: 60%", "policy-checker: 60"),
        ],
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success(), "{text}");
    assert!(text.contains("teamwork.yaml:"), "must name the file and line: {text}");
    assert!(
        text.contains("Change it to one of: everyone, anyone, enough-of-them"),
        "must list the words that work: {text}"
    );
    // The fix names the RANGE too. Both spellings of a percentage are held to
    // `0%..=100%` now — the `%` one was not, so `must-pass: -50%` loaded clean
    // and turned a six-of-six failing suite into a PASS.
    assert!(text.contains("Write it like `90%`"), "{text}");
    assert!(text.contains("between `0%` and `100%`"), "the range has to be named: {text}");
}

#[test]
fn validation_is_never_silently_skipped() {
    // A tree outside any workspace still gets checked, against the built-in
    // specification. Skipping here is how a broken tree reports itself as fine.
    let root = broken("nospec", &[("workspace.yaml", "description:", "descriptoin:")]);
    let out = pact().args(["check", &root]).output().unwrap();
    assert!(
        !out.status.success(),
        "a tree with no local spec/ must still be validated:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
}

#[test]
fn diagnostics_stay_free_of_programmer_jargon() {
    let root = broken(
        "jargon",
        &[("agents/refund-desk/needs.yaml", "reasoning: careful", "reasoning: brilliant")],
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout).to_lowercase();
    for word in ["enum", "variant", "deserialize", "unwrap", "panic", "vec<", "option<", "trait"] {
        assert!(!text.contains(word), "diagnostic leaked '{word}':\n{text}");
    }
}

#[test]
fn an_interceptor_the_adapter_would_refuse_is_refused_here_first() {
    // The whole point of `pact check`: it is the only tool decision D13's author
    // runs, so a rule the thing that executes it will not accept has to be
    // refused HERE, not later, in another language, in a process they never
    // start. All three of these loaded cleanly for a round.
    let root = broken(
        "interceptors",
        // (a) an address that is not one. Written as an entry of `when:`'s list
        //     since a rule may name several moments — the refusal has to name
        //     the entry that is wrong wherever in the list it sits, not only a
        //     `when:` line with one address on it.
        &[("interceptors/redact-card-numbers.yaml", "- step.message.before", "- banana")],
    );
    std::fs::write(
        std::path::Path::new(&root).join("interceptors/probe.yaml"),
        // (b) free prose, which is what an author writes when nobody has told
        //     them there is a vocabulary; and (c) a real sentence bound where
        //     nothing carries it out.
        "description: Rules nothing can carry out.\n\
         when: turn.message.after\n\
         may:\n  - send-elsewhere\n\
         rules:\n\
         \x20 - if the customer seems angry, escalate to a manager\n\
         \x20 - if payments is called more than 1 time in one run, go to the re-read stage instead\n",
    )
    .unwrap();
    let agent = std::path::Path::new(&root).join("agents/refund-desk/agent.yaml");
    let text = std::fs::read_to_string(&agent).unwrap();
    std::fs::write(&agent, text.replace("  - stop-runaway-refunds", "  - stop-runaway-refunds\n  - probe")).unwrap();

    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success(), "{text}");

    // (a) the address, named position by position.
    assert!(text.contains("'when' should say when it runs, and 'banana' does not"), "{text}");
    assert!(text.contains("`<part>.<thing>.<moment>`"), "{text}");
    // (b) the sentence, with the ones that work printed under it.
    assert!(
        text.contains("is not a rule PACT knows how to carry out"),
        "free prose must be refused: {text}"
    );
    assert!(
        text.contains("replace anything that looks like <a thing> with \"<text>\""),
        "the forms an author may type must be offered verbatim: {text}"
    );
    // (c) the moment, for a power that only works at one.
    assert!(text.contains("Change `when:` to one of: step.tool.before"), "{text}");
}

#[test]
fn a_power_the_rules_do_not_use_is_refused_naming_what_they_need() {
    // WHAT THIS USED TO TEST, and why it changed. It asserted that
    // `change-the-request` was not a choice `interceptor.may` offers at all,
    // because "no sentence in the closed vocabulary rewrites" — true when it was
    // written and false since two rewriting sentences landed (P8 wave 6,
    // `50-NOT-COPIED.md` §8.5). The premise went stale rather than being wrong,
    // which is exactly R29's shape, so the test moves to the property that
    // survives instead of being deleted.
    //
    // That property is the one R24 really states: `may:` and the rules have to
    // AGREE. Declaring a rewrite power beside rules that only hide is still
    // refused — and the refusal now names what those rules actually need, which
    // is the more useful half and was never available while the choice did not
    // exist.
    let root = broken(
        "power-the-rules-do-not-use",
        &[("interceptors/redact-card-numbers.yaml", "  - hide-values", "  - change-the-request")],
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success(), "{text}");
    assert!(text.contains("schema/rule-without-the-power"), "{text}");
    assert!(text.contains("hide values"), "name what the rules need: {text}");
    assert!(text.contains("`- hide-values`"), "and the line to type: {text}");
}

/// And the other direction: a rewrite power WITH a rewriting sentence loads.
///
/// The positive control for the refusal above, and the thing §8.5's withdrawal
/// actually claims — without it, "still refused" would be indistinguishable from
/// "never possible".
#[test]
fn a_rewrite_power_beside_a_rewriting_sentence_is_accepted() {
    // A NEW rule rather than an edit to the card-number one, and the difference
    // is the point: that rule hides, is bound at `step.message.before` and
    // `step.tool.before`, and `change-the-answer` works at neither. Bolting a
    // rewrite onto it drew three correct refusals — the power reaches nothing at
    // those moments, the sentence can be carried out at neither, and its own two
    // hiding rules still need `hide-values`. Every one of those is the checker
    // being right, so the fixture is what was wrong.
    let root = broken("rewrite-with-sentence", &[]);
    let at = std::path::Path::new(&root);
    std::fs::create_dir_all(at.join("programs/house-style/body")).unwrap();
    std::fs::write(at.join("programs/house-style/body/house-style.wasm"), b"placeholder").unwrap();
    std::fs::write(
        at.join("programs/house-style/program.yaml"),
        "description: Puts an answer into this desk's own words.\n\
         engine: wasm\n\
         determinism: pure\n\
         takes:\n  content: text\n\
         answers-with:\n  content: text\n\
         fuel:\n  instructions-at-most: 1m\n  when-it-runs-out: stop-and-say-so\n",
    )
    .unwrap();
    std::fs::write(
        at.join("interceptors/in-house-style.yaml"),
        "description: Says everything the way this desk says it.\n\
         when: turn.message.after\n\
         may:\n  - change-the-answer\n\
         rules:\n  - replace the answer with what house-style returns\n",
    )
    .unwrap();
    let agent = at.join("agents/refund-desk/agent.yaml");
    let text = std::fs::read_to_string(&agent).unwrap();
    std::fs::write(
        &agent,
        text.replace("  - stop-runaway-refunds", "  - stop-runaway-refunds\n  - in-house-style"),
    )
    .unwrap();

    let out = pact().args(["check", &root]).output().unwrap();
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(out.status.success(), "a rewrite backed by a program is writable now:\n{said}");
}

#[test]
fn a_wait_whose_deadline_was_never_written_is_reported_by_the_tool_the_author_runs() {
    // The mechanism was real and unreachable. `LoadReport::of` is the only thing
    // that emits `loader/wait-with-no-deadline`, and for a round it was called
    // from exactly one place in the repository — its own test file. So this
    // exact edit produced `OK — loaded cleanly (467 settings)` and exit 0, while
    // the same tree handed to a Rust caller produced the warning, the line and
    // the fix. D13's reader runs `pact check` and nothing else.
    //
    // Held from the CLI deliberately: the loader test cannot catch it, because
    // the loader test IS the caller that was keeping it alive.
    let root = broken(
        "no-deadline",
        &[("questions/is-this-ok.yaml", "answer-within: 30m\n", "")],
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(text.contains("rule: loader/wait-with-no-deadline"), "{text}");
    assert!(text.contains("questions/is-this-ok.yaml:"), "must name the line: {text}");
    assert!(text.contains("answer-within: 30m"), "the fix has to be typeable: {text}");
    // A warning, not an error: WAIT-8 says waiting forever is what you get when
    // you write nothing, so the tree still loads and the run still runs.
    assert!(out.status.success(), "{text}");
    // And once, however many lines put that question. `policies/approvals.yaml`
    // names `is-this-ok` twice and `teamwork.yaml` a third time; three copies of
    // one warning is three things to fix for one edit.
    assert_eq!(
        text.matches("rule: loader/wait-with-no-deadline").count(),
        1,
        "one mistake, one message: {text}"
    );
}

#[test]
fn a_shows_line_no_park_can_supply_is_reported_by_the_tool_the_author_runs() {
    // One letter, and `shows: [spent-so-far]` goes back to being a line the
    // author wrote that reaches nobody — `Question.about_call` filters with
    // `if k in args`, so the name simply vanishes and the person deciding
    // whether to keep spending sees `steps-taken` and nothing else.
    let root = broken("bad-shows", &[("questions/keep-going.yaml", "- spent-so-far", "- spent-so-fa")]);
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(text.contains("rule: loader/shows-nothing-can-supply"), "{text}");
    assert!(text.contains("questions/keep-going.yaml:"), "must name the line: {text}");
    assert!(text.contains("spent-so-far, steps-taken"), "must list what does work: {text}");
}

#[test]
fn the_list_a_scheduler_must_walk_can_be_obtained_without_writing_rust() {
    // §9.4 G14 obliges a runtime to time every outstanding wait and perform the
    // question's `if-nobody-answers:` when the clock runs out, and it names
    // `LoadReport.waits` as the list to comply against. That list was a Rust
    // type and nothing else — no command, no file, no JSON field — so a runtime
    // in any other language had no way to obtain the thing it was obliged to
    // walk. `to_json`'s own doc comment says it exists "for a runtime that is
    // not written in Rust"; this is the hop that makes that sentence true.
    let out = pact().args(["waits", &example()]).output().expect("runs");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let v: serde_json::Value = serde_json::from_slice(&out.stdout).expect("`pact waits` is JSON");
    let waits = v["waits"].as_array().expect("a list of waits");

    // Every reason the worked example can stop for, under the spelling the
    // durable record parks under — a scheduler keying a wakeup off a different
    // word would send it to a key nothing is waiting on.
    let reasons: Vec<&str> = waits.iter().filter_map(|w| w["reason"].as_str()).collect();
    for reason in ["out-of-budget", "needs-approval", "needs-permission", "context-too-long"] {
        assert!(reasons.contains(&reason), "no {reason} wait in {reasons:?}");
    }
    // And the three things a timer needs: how long, what to do, and who to reach.
    for w in waits {
        assert!(w["deadline-ms"].as_u64().is_some(), "{w} has no moment to wake at");
        assert!(!w["if-nobody-answers"].as_str().unwrap_or("").is_empty(), "{w}");
        assert!(!w["asked-of"].as_array().map(Vec::is_empty).unwrap_or(true), "{w}");
    }
}

#[test]
fn show_prints_the_loaded_document() {
    let out = pact().args(["show", &example()]).output().unwrap();
    assert!(out.status.success());
    let v: serde_json::Value =
        serde_json::from_slice(&out.stdout).expect("show emits valid JSON");
    assert!(v["agents"]["refund-desk"]["instructions"].is_string());
}
