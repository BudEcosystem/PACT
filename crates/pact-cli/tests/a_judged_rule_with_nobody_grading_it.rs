//! Port parity: what the runtime decides from the document alone, `pact check`
//! decides too.
//!
//! `judged:` is a rule settled by reading the answer, and which model reads it
//! is `graded-by:`. Write the rule, leave the grader out, and the Python
//! runtime reaches `providers.py`'s judge-is-`None` arm and reports the rule on
//! `RunResult.unenforced` — *"nothing was grading this run, so it was not
//! measured"*. `pact check` printed **"OK — loaded cleanly"**.
//!
//! Everything needed to decide it is in the two documents. Deciding it at run
//! time, in a language the author does not run, in a process they never start,
//! is the split this closes: the author who never runs the suite is exactly the
//! author who believes the rule is being enforced.
//!
//! Driven against the real worked example with one line removed, for the reason
//! `a_judge_that_is_the_model_under_test.rs` gives: what is proved is that the
//! shipped tree's own lines reach the rule.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// A copy of the worked example with its `graded-by:` line taken out.
fn without_the_grader(name: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-nograder-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let suite = dst.join("evals/suite.yaml");
    let written = std::fs::read_to_string(&suite).expect("the worked example has a suite");
    let kept: Vec<&str> =
        written.lines().filter(|l| !l.trim_start().starts_with("graded-by:")).collect();
    assert!(
        kept.len() < written.lines().count(),
        "the worked example no longer writes `graded-by:` — this test asserts nothing"
    );
    std::fs::write(&suite, kept.join("\n") + "\n").unwrap();
    dst
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}

fn check(root: &std::path::Path) -> String {
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr))
}

#[test]
fn a_rule_decided_by_reading_the_answer_needs_somebody_to_read_it() {
    let root = without_the_grader("plain");
    let text = check(&root);
    assert!(
        text.contains("evals/judged-with-nobody-grading"),
        "a judged rule with no grader must be said at check time:\n{text}"
    );
    assert!(
        text.contains("measures everything except this"),
        "the message has to say what is lost, not that a field is absent:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_it_offers_is_the_line_the_worked_example_already_has() {
    // R24. The fix names `graded-by:` and a model id, and typing it has to
    // leave a tree that checks clean — which is exactly the shipped tree.
    let root = without_the_grader("typed");
    let told = check(&root);
    assert!(told.contains("Add `graded-by:`"), "{told}");

    let suite = root.join("evals/suite.yaml");
    let text = std::fs::read_to_string(&suite).unwrap();
    std::fs::write(&suite, format!("{text}graded-by: qwen2.5-14b-instruct\n")).unwrap();

    let after = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    let seen = check(&root);
    assert!(
        after.status.success() && !seen.contains("evals/judged-with-nobody-grading"),
        "typing the fix has to finish the job:\n{seen}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_shipped_example_gains_no_diagnostic_from_this() {
    // The phase gate. The worked example writes both halves, so this rule must
    // be invisible to it — a new check that fires on the flagship is a new
    // defect, not a new guarantee.
    let out = pact().args(["check", &example()]).output().expect("runs");
    let text = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert!(out.status.success(), "{text}");
    assert!(!text.contains("evals/judged-with-nobody-grading"), "{text}");
}

#[test]
fn it_is_a_warning_because_a_suite_is_written_before_it_is_wired() {
    // Same argument `available.rs` makes: a rule written before the grader is
    // the ordinary order of work. Failing the build on it teaches people to
    // reach for the flag that turns checking off.
    let root = without_the_grader("warns");
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    assert!(
        out.status.success(),
        "a half-wired suite must still check:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let _ = std::fs::remove_dir_all(&root);
}

/// A copy of the worked example whose metric loses its provider prefix.
fn metric_without_its_provider(name: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-nouri-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let suite = dst.join("evals/suite.yaml");
    let written = std::fs::read_to_string(&suite).unwrap();
    assert!(
        written.contains("uri: pact:at_most_words"),
        "the worked example no longer writes a prefixed metric — this test asserts nothing"
    );
    std::fs::write(&suite, written.replace("uri: pact:at_most_words", "uri: at_most_words"))
        .unwrap();
    dst
}

#[test]
fn a_metric_that_does_not_say_who_scores_it_is_refused_at_check_time() {
    // `providers.py` decides this from the document and decides it at RUN time,
    // in a language the author does not run. `pact check` printed "OK — loaded
    // cleanly" over a metric that could never be measured.
    let root = metric_without_its_provider("plain");
    let text = check(&root);
    assert!(
        text.contains("evals/metric-without-a-provider"),
        "a metric with no provider must be refused at check time:\n{text}"
    );
    assert!(
        text.contains("does not say who provides that score"),
        "the two ports have to refuse it in the same words:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_two_ports_refuse_a_providerless_metric_in_the_same_words() {
    // One vocabulary. A checker and a runtime that refuse one thing two ways
    // teach an author they are two products, and the fix they can act on is
    // whichever they happened to read.
    //
    // Both sides are compared with their string-literal seams removed, because
    // `providers.py` writes the sentence across three adjacent f-strings and a
    // line break is not a difference in wording.
    let root = metric_without_its_provider("words");
    let told = seamless(&check(&root));
    let python = seamless(
        &std::fs::read_to_string(format!(
            "{}/../../adapters/python/src/pact_adapters/providers.py",
            env!("CARGO_MANIFEST_DIR")
        ))
        .expect("the runtime's own wording"),
    );
    // The DIAGNOSIS and the FIX have to be the same words. The tense does not:
    // the runtime says "so nothing measured it" because it has just finished not
    // measuring it, and the checker says "so nothing would measure it" because
    // nothing has run yet. Demanding one tense for both would make one of them
    // lie about when it is speaking, and this test exists to keep the words an
    // author acts on identical — not to erase the difference between a warning
    // and a post-mortem.
    for phrase in [
        "does not say who provides that score",
        "put the provider in front of it with a colon",
        "for one that needs nothing installed",
    ] {
        let phrase = phrase.to_lowercase();
        assert!(
            python.to_lowercase().contains(&phrase),
            "the runtime no longer says {phrase:?}"
        );
        assert!(
            told.to_lowercase().contains(&phrase),
            "the checker does not say {phrase:?}:\n{told}"
        );
    }
    for (side, text) in [("the runtime", &python), ("the checker", &told)] {
        assert!(
            text.contains("so nothing measured it") || text.contains("so nothing would measure it"),
            "{side} no longer says what is lost"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

/// The same text with adjacent string-literal seams and line wrapping removed.
///
/// `"…that " f"score…"` and `"…that score…"` are one sentence written twice, and
/// a test that cannot see that is a test about formatting. The scan removes the
/// whole seam — closing quote, the wrap, the `f` prefix, opening quote — rather
/// than stripping quotes and leaving `fscore` behind.
fn seamless(text: &str) -> String {
    let c: Vec<char> = text.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    while i < c.len() {
        if c[i] == '"' {
            let mut j = i + 1;
            while j < c.len() && c[j].is_whitespace() {
                j += 1;
            }
            if j < c.len() && c[j] == 'f' {
                j += 1;
            }
            if j < c.len() && c[j] == '"' {
                i = j + 1;
                continue;
            }
            i += 1;
            continue;
        }
        out.push(c[i]);
        i += 1;
    }
    out.split_whitespace().collect::<Vec<_>>().join(" ")
}

#[test]
fn whether_this_machine_has_the_provider_is_left_to_the_machine() {
    // The half that is NOT a fact about the document. Whether `deepeval:` is
    // installed differs per machine, and a portable folder that loads here and
    // is refused there is the thing the format exists to prevent. So a
    // well-formed uri naming a provider this build may not have must still pass.
    let dst = std::env::temp_dir()
        .join(format!("pact-provider-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let suite = dst.join("evals/suite.yaml");
    let written = std::fs::read_to_string(&suite).unwrap();
    std::fs::write(
        &suite,
        written.replace("uri: pact:at_most_words", "uri: deepeval:faithfulness"),
    )
    .unwrap();
    let out = pact().args(["check", dst.to_str().unwrap()]).output().expect("runs");
    assert!(
        out.status.success(),
        "a provider this build may not have is not a fact about the folder:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let _ = std::fs::remove_dir_all(&dst);
}
