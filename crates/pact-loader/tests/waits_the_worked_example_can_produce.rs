//! The list a scheduler wakes for, checked against the documents that produce it.
//!
//! §9.4 G14 says a conforming runtime must read every outstanding wait's
//! deadline and act on the timeout action the question names, without the person
//! coming back. `LoadReport::waits` is what it reads. These tests exist to keep
//! that list **derived** — every assertion below is either against the worked
//! example's own YAML or against a copy of it with one line edited, so a report
//! that drifted into a hand-maintained copy of the tree would fail here rather
//! than quietly go stale.
//!
//! The failure they are really guarding against: an authoring field that is
//! resolved and then read by nobody. `answer-within:` was exactly that until
//! this list existed — `Suspension.expired(now)` is called on one path, when a
//! caller re-enters the run with an answer, so a run nobody came back to waited
//! forever with a deadline written in the file.

use camino::Utf8PathBuf;
use pact_diag::Diagnostics;
use pact_doc::Node;
use pact_loader::Loader;
use pact_loader::report::LoadReport;

fn example() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples/refund-desk")
}

fn read(root: &Utf8PathBuf) -> (Node, LoadReport, Diagnostics) {
    let mut d = Diagnostics::new();
    let node = Loader::new(root.clone()).load(root, &mut d).expect("the example loads");
    let report = LoadReport::of(&node, &mut d);
    d.sort();
    (node, report, d)
}

/// The question an author wrote, straight out of the tree.
fn question<'a>(doc: &'a Node, name: &str) -> &'a Node {
    doc.get("questions")
        .and_then(|q| q.get(name))
        .unwrap_or_else(|| panic!("the example has no question called {name}"))
}

#[test]
fn every_question_the_worked_example_writes_is_a_wait_the_report_names() {
    // The `questions/` folder holds four files. A question no line can reach is
    // a page of wording nothing will ever show, which is the same defect in the
    // author's document that a resolved-but-unread field is in the code — so
    // this is asserted over the folder rather than over a list written here.
    let (doc, report, _) = read(&example());
    let folder = doc.get("questions").and_then(Node::as_map).expect("questions/ became a field");
    let written: Vec<&str> = folder.keys().map(String::as_str).collect();
    assert!(written.len() >= 4, "the worked example writes four questions: {written:?}");

    for name in &written {
        assert!(
            report.waits.iter().any(|w| w.question == *name),
            "questions/{name}.yaml can never be asked — no line in the tree names it. \
             The report lists: {:?}",
            report.waits.iter().map(|w| w.question.as_str()).collect::<Vec<_>>()
        );
    }
}

#[test]
fn every_wait_carries_the_deadline_its_own_question_declares() {
    // Derived, not copied: the expected value is read out of the same YAML the
    // report read, so editing `answer-within:` in the file moves both sides.
    let (doc, report, _) = read(&example());
    assert!(!report.waits.is_empty());

    for wait in &report.waits {
        let q = question(&doc, &wait.question);
        let written = q.get("answer-within").and_then(Node::as_str).unwrap_or("").trim();
        assert_eq!(
            wait.answer_within, written,
            "{} reports a deadline the question does not write",
            wait.question
        );
        assert!(
            wait.deadline_ms.is_some(),
            "{} writes `answer-within: {written}` and the report made no time of it",
            wait.question
        );
        assert_eq!(
            wait.if_nobody_answers,
            q.get("if-nobody-answers").and_then(Node::as_str).unwrap_or("").trim(),
            "{} reports a different timeout action from the one in its file",
            wait.question
        );
    }
}

#[test]
fn the_deadlines_a_scheduler_would_set_are_the_ones_the_files_write() {
    // The test above proves the report and the files agree on the *words*. This
    // one proves they agree on the *time*, by reading the minutes back a
    // different way — a report that parsed `4h` as four milliseconds would
    // otherwise agree with itself all the way through.
    let (doc, report, _) = read(&example());
    for wait in report.wake_ups() {
        let written = question(&doc, &wait.question)
            .get("answer-within")
            .and_then(Node::as_str)
            .unwrap_or("")
            .trim()
            .to_string();
        let expected = plainly(&written).unwrap_or_else(|| {
            panic!("{} writes `answer-within: {written}`, which this test cannot read back \
                    a second way — check the report's arithmetic by hand", wait.question)
        });
        assert_eq!(wait.deadline_ms, Some(expected), "{} is timed wrongly", wait.question);
    }

    // And the questions the example ships today are on the list by name, so a
    // tree that lost one fails here instead of passing an empty loop.
    let awake: Vec<&str> = report.wake_ups().map(|w| w.question.as_str()).collect();
    for shipped in ["is-this-ok", "how-much-to-refund", "keep-going", "too-long-to-send"] {
        assert!(awake.contains(&shipped), "{shipped} is not on the scheduler's list: {awake:?}");
    }
}

#[test]
fn the_report_names_the_line_that_can_stop_the_run() {
    // A person told "this run is waiting" has to be able to open the file that
    // decided it would. A wait naming only its question would send them to the
    // wording and not to the rule.
    let (_, report, _) = read(&example());
    let at = |q: &str| -> Vec<String> {
        report
            .waits
            .iter()
            .filter(|w| w.question == q)
            .map(|w| {
                let at = &w.declared_at;
                format!("{}:{}", at.file.file_name().unwrap_or(""), at.line)
            })
            .collect()
    };
    assert!(at("keep-going").contains(&"limits.yaml:18".to_string()), "{:?}", at("keep-going"));
    // The teamwork park asks its OWN question now, not the approvals one:
    // `is-this-ok` shows the amount and order number of the CALL being approved,
    // and a teammate who could not answer is not a call, so both lines were
    // dropped in silence and the person saw the wording and nothing else.
    assert!(
        at("carry-on-without-a-check").contains(&"teamwork.yaml:30".to_string()),
        "{:?}",
        at("carry-on-without-a-check")
    );
    assert!(
        at("too-long-to-send").contains(&"long-threads.yaml:60".to_string()),
        "{:?}",
        at("too-long-to-send")
    );
    assert!(
        at("how-much-to-refund").contains(&"approvals.yaml:33".to_string()),
        "{:?}",
        at("how-much-to-refund")
    );
}

#[test]
fn a_policy_with_three_rules_produces_three_waits_and_not_only_the_first() {
    // `policies/approvals.yaml` can park on any of its three rules. The
    // executing side keeps one rule per reason because a running wait has one
    // deadline; a scheduler told only about the first would hold no timer for
    // the 4h one, and a run parked on it would never be looked at again.
    let (_, report, _) = read(&example());
    let from_the_policy: Vec<&str> = report
        .waits
        .iter()
        .filter(|w| {
            w.declared_at.file.file_name() == Some("approvals.yaml")
                && w.agent == "refund-desk"
        })
        .map(|w| w.question.as_str())
        .collect();
    assert_eq!(from_the_policy, vec!["is-this-ok", "how-much-to-refund", "is-this-ok"]);

    // And the policy says `applies-to: every-agent`, so all three agents carry
    // it. It used to bind per-agent and opt-in, so `fraud-checker` — which uses
    // `zendesk`, and the third rule gates `zendesk/reply` — had no gate at all
    // and `pact waits` listed seven waits every one of which said
    // `"agent": "refund-desk"`.
    let agents: std::collections::BTreeSet<&str> = report
        .waits
        .iter()
        .filter(|w| w.declared_at.file.file_name() == Some("approvals.yaml"))
        .map(|w| w.agent.as_str())
        .collect();
    assert_eq!(
        agents.into_iter().collect::<Vec<_>>(),
        vec!["fraud-checker", "policy-checker", "refund-desk"]
    );
}

#[test]
fn the_report_says_who_may_answer_and_who_it_goes_to_next() {
    // A runtime told only to escalate has nobody to escalate to, and would have
    // to guess. Both lines travel, or the timeout action is unperformable.
    let (_, report, _) = read(&example());
    for wait in &report.waits {
        assert!(!wait.asked_of.is_empty(), "{} names nobody who can answer", wait.question);
        if wait.if_nobody_answers == "escalate" {
            assert!(
                !wait.escalates_to.is_empty(),
                "{} escalates to nobody, so the runtime cannot perform it",
                wait.question
            );
        }
    }
    let escalating: Vec<&str> = report
        .waits
        .iter()
        .filter(|w| w.if_nobody_answers == "escalate")
        .flat_map(|w| w.escalates_to.iter().map(String::as_str))
        .collect();
    assert!(escalating.contains(&"support-manager"), "{escalating:?}");
}

#[test]
fn nothing_in_the_list_lets_a_timeout_approve() {
    // WAIT-4, checked on the surface a scheduler actually reads. A runtime that
    // performs exactly what this field says can never turn "ask a person" into
    // "wait a while, then do it", because there is no spelling of yes here.
    let (_, report, _) = read(&example());
    for wait in &report.waits {
        assert!(
            ["stop-and-say-so", "decline", "escalate"].contains(&wait.if_nobody_answers.as_str()),
            "{} would have a runtime do {:?} when nobody answers",
            wait.question,
            wait.if_nobody_answers
        );
    }
}

#[test]
fn a_question_whose_deadline_is_removed_drops_out_of_the_list() {
    // The point of the whole entry. If the report were a hand-written copy of
    // the tree this would pass unchanged; because it is read from the documents,
    // deleting one line takes two waits off the scheduler's list and says so.
    let copy = copy_of_the_example("no-deadline");
    let file = copy.join("questions/is-this-ok.yaml");
    let text = std::fs::read_to_string(&file).unwrap();
    assert!(text.contains("answer-within: 30m"), "the line this test deletes must exist");
    std::fs::write(&file, text.replace("answer-within: 30m\n", "")).unwrap();

    let (_, report, diags) = read(&copy);

    let awake: Vec<&str> = report.wake_ups().map(|w| w.question.as_str()).collect();
    assert!(
        !awake.contains(&"is-this-ok"),
        "a wait with no deadline has no moment for a scheduler to wake at: {awake:?}"
    );
    for still_timed in ["keep-going", "too-long-to-send", "how-much-to-refund"] {
        assert!(awake.contains(&still_timed), "{still_timed} lost its deadline too: {awake:?}");
    }
    assert!(
        report.waits.iter().any(|w| w.question == "is-this-ok" && !w.wakes()),
        "the wait is still real — it just never ends"
    );

    // And the author is told, where they are, that they have written an
    // instruction nothing can carry out.
    let warn = diags
        .items()
        .iter()
        .find(|d| d.rule == "loader/wait-with-no-deadline")
        .expect("a timeout action nothing can reach must be reported");
    assert_eq!(warn.span.file.file_name(), Some("is-this-ok.yaml"));
    assert!(warn.span.line > 1, "a diagnostic has to name the line, not just the file");
    assert!(warn.message.contains("is-this-ok") && warn.message.contains("escalate"));
    assert!(warn.fix.contains("answer-within: 30m"), "the fix has to be typeable: {}", warn.fix);

    let _ = std::fs::remove_dir_all(&copy);
}

#[test]
fn the_connection_wait_is_found_through_the_tool_that_reaches_the_server() {
    // `uses:` names TOOLS — the schema says `names: [tools, skills]` — so a
    // resource is not writable there at all, and a report that looked one up
    // under a name from `uses:` found one only when a tool and a server happened
    // to be spelled the same. The worked example spelled both `payments`, so the
    // coincidence held and nothing noticed.
    //
    // Reproduced here by renaming the TOOL and nothing else. The server, its
    // `asks-to-connect:` and the question are untouched, and the run still parks
    // for that consent — so the wait has to still be on the scheduler's list. It
    // was not: renaming the tool alone removed `may-we-connect` from the report
    // entirely, which is a run parked for an hour on a wait no timer is held for.
    let copy = copy_of_the_example("renamed-tool");
    std::fs::rename(copy.join("tools/payments.yaml"), copy.join("tools/refunds.yaml")).unwrap();

    let agent = copy.join("agents/refund-desk/agent.yaml");
    let text = std::fs::read_to_string(&agent).unwrap();
    std::fs::write(&agent, text.replace("  - payments\n", "  - refunds\n")).unwrap();
    for (file, from, to) in [
        ("policies/approvals.yaml", "payments/issue-refund", "refunds/issue-refund"),
        ("evals/suite.yaml", "payments/", "refunds/"),
        ("evals/cases/01-clear-approve.yaml", "payments/", "refunds/"),
        ("loops/careful.yaml", "- payments", "- refunds"),
    ] {
        let p = copy.join(file);
        let was = std::fs::read_to_string(&p).unwrap();
        std::fs::write(&p, was.replace(from, to)).unwrap();
    }

    let (_, report, _) = read(&copy);
    let asked: Vec<&str> = report
        .waits
        .iter()
        .filter(|w| w.reason == "needs-permission")
        .map(|w| w.question.as_str())
        .collect();
    assert_eq!(
        asked,
        vec!["may-we-connect"],
        "the tool was renamed and the connection consent fell off the list: {:?}",
        report.waits.iter().map(|w| (w.reason, w.question.as_str())).collect::<Vec<_>>()
    );

    let _ = std::fs::remove_dir_all(&copy);
}

#[test]
fn a_shows_line_naming_something_the_park_cannot_supply_is_reported() {
    // The same defect `shown.py` landed to fix, one letter away. `shows:
    // [spent-so-far, steps-taken]` was a line the author wrote that reached
    // nobody; `shows: [spent-so-fa]` still is, because `Question.about_call`
    // filters with `if k in args` and an unrecognised name simply vanishes — at
    // check time and again at run time, with nothing anywhere saying so.
    let copy = copy_of_the_example("bad-shows");
    let file = copy.join("questions/keep-going.yaml");
    let text = std::fs::read_to_string(&file).unwrap();
    assert!(text.contains("- spent-so-far"), "the line this test mistypes must exist");
    std::fs::write(&file, text.replace("- spent-so-far", "- spent-so-fa")).unwrap();

    let (_, _, diags) = read(&copy);
    let warn = diags
        .items()
        .iter()
        .find(|d| d.rule == "loader/shows-nothing-can-supply")
        .unwrap_or_else(|| panic!("a value nobody can show must be said out loud:\n{}", diags.render()));
    assert_eq!(warn.span.file.file_name(), Some("keep-going.yaml"));
    assert!(warn.message.contains("spent-so-fa"), "{}", warn.message);
    assert!(warn.fix.contains("spent-so-far"), "the fix has to be typeable: {}", warn.fix);

    let _ = std::fs::remove_dir_all(&copy);
}

#[test]
fn a_shows_line_naming_an_argument_of_the_action_being_approved_is_left_alone() {
    // The other half, and the reason the check is not a flat list. `is-this-ok`
    // is put about a pending `payments` call, so `shows: [amount, order-number]`
    // names that call's own arguments. There IS a list for those now — the
    // action's own `takes:`, read by `report::what_the_rule_is_about`, which is
    // what closed the two money parks — but it is the author's list and not a
    // table kept in Rust, and a park that has none is still exempt. Refusing
    // `order-number` because it is not in a table here would be worse than the
    // silence the test above closes.
    // (`what_an_approver_is_shown_at_the_two_money_parks.rs` is where the
    // closing is proved; this stays as the floor.)
    let (_, _, diags) = read(&example());
    assert!(
        !diags.items().iter().any(|d| d.rule == "loader/shows-nothing-can-supply"),
        "the worked example's own `shows:` lines are all legitimate:\n{}",
        diags.render()
    );
}

#[test]
fn the_list_is_the_same_two_machines_running_it_twice() {
    // A scheduler provisions from this. A report whose order depended on a
    // dictionary's iteration would give two runtimes two different lists.
    let (_, a, _) = read(&example());
    let (_, b, _) = read(&example());
    assert_eq!(a, b);
    assert_eq!(a.to_json(), b.to_json(), "and the same as data, for a runtime that is not Rust");
}

// ─────────────────────────────────────────────────────────────────────── helpers

/// `30m`, `4h`, `45s` — the one-unit spellings, read the obvious way.
///
/// Deliberately a second, dumber reader than the one the report uses. `None`
/// for anything compound, so a spelling this cannot check fails loudly rather
/// than being waved through.
fn plainly(written: &str) -> Option<u64> {
    let (digits, unit) = written.split_at(written.find(|c: char| !c.is_ascii_digit())?);
    let n: u64 = digits.parse().ok()?;
    match unit.trim() {
        "s" => Some(n * 1000),
        "m" => Some(n * 60 * 1000),
        "h" => Some(n * 60 * 60 * 1000),
        _ => None,
    }
}

/// A throwaway copy of the worked example, so a test may edit one line of it.
fn copy_of_the_example(why: &str) -> Utf8PathBuf {
    let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
        .join(format!("pact-waits-{why}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    copy_tree(&example(), &base);
    base
}

fn copy_tree(from: &Utf8PathBuf, to: &Utf8PathBuf) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap().flatten() {
        let name = entry.file_name().into_string().unwrap();
        let src = from.join(&name);
        let dst = to.join(&name);
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&src, &dst);
        } else {
            std::fs::copy(&src, &dst).unwrap();
        }
    }
}

#[test]
fn the_json_says_which_waits_a_scheduler_can_time() {
    // `Wait::wakes` and `LoadReport::wake_ups` were the only two functions in this
    // crate with no caller outside a test, and the reason was in the projection:
    // `to_json` handed a runtime every wait and no way to tell which of them has a
    // moment to wake at. A consumer complying with §9.4 G14 had to reimplement the
    // rule — and could reimplement it differently, which is the whole hazard a
    // published report exists to remove.
    let (_doc, report, _d) = read(&example());
    let json = report.to_json();

    let waits = json["waits"].as_array().expect("waits is a list");
    assert!(!waits.is_empty(), "the example must produce waits, or this proves nothing");
    for w in waits {
        assert!(
            w["wakes"].is_boolean(),
            "every wait must say whether a scheduler can time it: {w:#}"
        );
    }

    // The filtered list is exactly the waits that said yes — one derivation, not
    // two that can drift.
    let named: Vec<&str> = json["wake-ups"].as_array().unwrap()
        .iter().map(|v| v.as_str().unwrap()).collect();
    let expected: Vec<&str> = waits.iter()
        .filter(|w| w["wakes"] == true)
        .map(|w| w["question"].as_str().unwrap())
        .collect();
    assert_eq!(named, expected, "the two views of one rule disagree");
    assert_eq!(named.len(), report.wake_ups().count(), "and neither matches the source");
}
