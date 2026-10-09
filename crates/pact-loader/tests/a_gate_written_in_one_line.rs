//! **One line gates one action, and the guarantee is not smaller for it.**
//!
//! Gating one action used to cost three files and thirteen lines: a question in
//! `questions/`, a policy file in `policies/`, and a rule inside it naming
//! `<tool>/<action>`. Eve charges one file and two lines for the same gate, and
//! a measured first-time author needed four rounds of diagnostics — and four
//! concepts they had not met — before their first gate held. That was the one
//! surface where this format was harder to author in than the system it has to
//! beat, which makes it a defect rather than a trade.
//!
//! `needs-a-person: yes` is the short spelling, and everything below is about
//! the same claim from a different side: **it desugars, it does not simplify.**
//! The rule it becomes is the rule the author would have typed; the question it
//! puts is a file in `spec/questions/` with the same `asked-of:`,
//! `answer-within:` and `if-nobody-answers:` a written question carries; and the
//! wait it makes reaches `pact waits` — the list §9.4 G14 obliges a runtime to
//! walk — indistinguishable from a wait written the long way.
//!
//! Every assertion here is against a tree ON DISK, loaded by the real loader,
//! with nothing constructed by hand. `tests/trees/one-line-gate/` has no
//! `questions/` folder and no `policies/` folder at all, so a report that had
//! learned to produce this wait some other way could not pass.

use camino::Utf8PathBuf;
use pact_diag::Diagnostics;
use pact_doc::Node;
use pact_loader::Loader;
use pact_loader::approvals;
use pact_loader::report::{LoadReport, NEEDS_APPROVAL};

fn tree() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/one-line-gate")
}

fn worked_example() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples/refund-desk")
}

/// The tree, the list of waits it can produce, and everything `pact check`
/// would say about it.
///
/// The two checks are run here rather than only the report, because this item
/// spans both: `LoadReport` is what puts a short gate on the scheduler's list,
/// `approvals::check` is what tells an author their short line is overruled, and
/// `money::check` is the sibling that used to report the gated action as ungated.
/// A test reading only one of the three could pass with the other two wrong.
fn read(root: &Utf8PathBuf) -> (Node, LoadReport, Diagnostics) {
    let mut d = Diagnostics::new();
    let node = Loader::new(root.clone())
        .load(root, &mut d)
        .expect("the tree loads");
    let report = LoadReport::of(&node, &mut d);
    approvals::check(&node, &mut d);
    pact_loader::money::check(&node, &mut d);
    d.sort();
    (node, report, d)
}

// ───────────────────────────── the author's line, reaching the list a runtime walks

#[test]
fn one_line_in_a_tool_file_produces_a_wait_with_no_question_and_no_policy_anywhere() {
    // The whole item, in one assertion. The tree writes `needs-a-person: yes`
    // and nothing else — no `questions/`, no `policies/`, no rule — and a person
    // is still asked before the refund.
    let (doc, report, diags) = read(&tree());
    assert!(
        doc.get("questions").is_none(),
        "the point of the short form is that there is no question file to write"
    );
    assert!(doc.get("policies").is_none(), "and no policy file either");

    let asked: Vec<&str> = report
        .waits
        .iter()
        .filter(|w| w.reason == NEEDS_APPROVAL)
        .map(|w| w.question.as_str())
        .collect();
    assert_eq!(
        asked,
        vec![approvals::SHIPPED_QUESTION],
        "a gate written the short way is not on the list a scheduler walks: {:?}",
        report
            .waits
            .iter()
            .map(|w| (w.reason, w.question.as_str()))
            .collect::<Vec<_>>()
    );
    assert!(
        diags.is_empty(),
        "and a correct tree is warned about nothing:\n{}",
        diags.render()
    );
}

#[test]
fn the_wait_a_short_gate_makes_carries_the_same_deadline_and_audience_a_written_one_would() {
    // "Nothing about the guarantee weakens, only the typing" is either true here
    // or nowhere: these four fields are all a runtime is given to act on, and a
    // wait missing any of them is one that parks and is never looked at again.
    let (_, report, _) = read(&tree());
    let wait = report
        .waits
        .iter()
        .find(|w| w.reason == NEEDS_APPROVAL)
        .expect("the gate");

    assert_eq!(wait.answer_within, "30m", "the wait has to end somewhere");
    assert_eq!(
        wait.deadline_ms,
        Some(30 * 60 * 1000),
        "not thirty times shorter"
    );
    assert!(wait.wakes(), "a scheduler has a moment to wake at");
    assert!(
        !wait.asked_of.is_empty(),
        "a wait nobody can answer runs its deadline down and decides by itself"
    );
    assert_eq!(wait.asked_of, vec!["whoever-is-running-this"]);
    assert_eq!(wait.if_nobody_answers, "stop-and-say-so");
    assert_eq!(wait.agent, "desk", "a wait belongs to the run of one agent");
}

#[test]
fn nothing_on_the_short_path_lets_a_timeout_approve() {
    // WAIT-4, checked on the surface a scheduler reads, for the spelling that
    // did not exist when the rule was written. A shorthand whose timeout action
    // could be an approval would be a way to buy a gate that opens itself.
    let (_, report, _) = read(&tree());
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
fn the_wait_points_at_the_line_the_author_really_typed() {
    // A person told "this run is waiting" has to be able to open the file that
    // decided it would, and for a short gate that file is the TOOL's, not a
    // policy's. The expected line is read out of the file rather than written
    // here, so moving the line moves both sides.
    let (_, report, _) = read(&tree());
    let wait = report
        .waits
        .iter()
        .find(|w| w.reason == NEEDS_APPROVAL)
        .expect("the gate");
    let file = tree().join("tools/payments.yaml");
    let text = std::fs::read_to_string(&file).expect("the tool file is on disk");
    let expected = text
        .lines()
        .position(|l| l.trim_start().starts_with("needs-a-person:"))
        .expect("the line this test is about must exist")
        + 1;

    assert_eq!(wait.declared_at.file.file_name(), Some("payments.yaml"));
    assert_eq!(
        wait.declared_at.line, expected,
        "the wait points somewhere other than the line that made it"
    );
}

#[test]
fn deleting_the_one_line_takes_the_gate_off_the_list_and_the_money_warning_comes_back() {
    // The negative control, and the only thing that proves the AUTHOR's line is
    // what produces the wait rather than something in here. One line out of one
    // file, and the tree goes from "a person is asked" to "money moves with
    // nobody asked" — which is the sentence `money.rs` puts, so both halves of
    // the wiring are measured by one edit.
    let copy = copy_of("deleted");
    let file = copy.join("tools/payments.yaml");
    let text = std::fs::read_to_string(&file).unwrap();
    assert!(
        text.contains("needs-a-person: yes"),
        "the line this test deletes must exist"
    );
    std::fs::write(&file, text.replace("    needs-a-person: yes\n", "")).unwrap();

    let (_, report, diags) = read(&copy);
    assert!(
        report.waits.is_empty(),
        "the gate outlived the line that wrote it: {:?}",
        report
            .waits
            .iter()
            .map(|w| w.question.as_str())
            .collect::<Vec<_>>()
    );
    let warn = diags
        .items()
        .iter()
        .find(|d| d.rule == "loader/money-moves-with-nobody-asked")
        .unwrap_or_else(|| {
            panic!(
                "an ungated spend must be said out loud:\n{}",
                diags.render()
            )
        });
    assert!(
        warn.message
            .contains("money moves without anybody being asked"),
        "{}",
        warn.message
    );

    let _ = std::fs::remove_dir_all(&copy);
}

#[test]
fn an_action_that_moves_money_and_asks_a_person_in_one_line_is_not_reported_as_ungated() {
    // The sibling check, which is where a wired field usually leaves a hole. The
    // warning about money reads the POLICY, and an action gated by its own file
    // has no policy — so before this it told the author that money moved with
    // nobody asked, about the action whose own line says a person is asked, and
    // the fix it offered was to write out the long form of what they had
    // already written.
    let (_, _, diags) = read(&tree());
    assert!(
        !diags
            .items()
            .iter()
            .any(|d| d.rule == "loader/money-moves-with-nobody-asked"),
        "an action gated in one line was reported as ungated:\n{}",
        diags.render()
    );
}

#[test]
fn the_read_only_action_beside_it_is_not_gated_by_its_neighbours_line() {
    // `needs-a-person:` is a line on one ACTION, and the desugared rule names
    // `<tool>/<action>` for exactly that reason. A shorthand that gated the
    // whole tool would stop the read-only lookup nobody wrote a line about,
    // which is the spelling `pact check` refuses in the long form as
    // `loader/rule-names-no-action`.
    let (doc, _, _) = read(&tree());
    let expanded = approvals::desugared(&doc);
    let named: Vec<String> = expanded.iter().map(approvals::Desugared::named).collect();
    assert_eq!(named, vec!["payments/issue-refund"]);
    assert_eq!(
        expanded[0].shows,
        vec!["order-number", "amount"],
        "the values a person sees"
    );
    assert!(
        expanded[0]
            .because
            .contains("Send money back to the customer"),
        "the person is shown what the action does, in the action's own words: {}",
        expanded[0].because
    );
}

// ─────────────────────────────────── the expert path still wins, and says so

#[test]
fn a_rule_about_the_same_action_wins_and_the_author_is_told_where_they_overlap() {
    // The worked example gates `payments/issue-refund` the long way, with two
    // rules and two questions. Adding the short line to the same action must
    // change nothing about what happens — the rule says who is asked, how long
    // they have and what shape the answer takes, and none of that can be
    // overruled by somebody else's one-liner — and the author has to be told,
    // because a line that decides nothing is exactly the defect this project
    // keeps shipping.
    let (_, before, _) = read(&worked_example());

    let copy = copy_of_the_example("both");
    let file = copy.join("tools/payments.yaml");
    let text = std::fs::read_to_string(&file).unwrap();
    assert!(text.contains("    inspects: [amount]"), "fixture drifted");
    std::fs::write(
        &file,
        text.replace(
            "    inspects: [amount]",
            "    needs-a-person: yes\n    inspects: [amount]",
        ),
    )
    .unwrap();
    let (_, after, diags) = read(&copy);

    assert_eq!(
        after.waits.len(),
        before.waits.len(),
        "the short line added a second wait beside a written rule, so one call \
         would put two screens in front of one person"
    );
    let warn = diags
        .items()
        .iter()
        .find(|d| d.rule == "loader/asked-for-twice")
        .unwrap_or_else(|| {
            panic!(
                "a line that decides nothing must be said out loud:\n{}",
                diags.render()
            )
        });
    assert_eq!(
        warn.severity,
        pact_diag::Severity::Warning,
        "both lines are legitimate"
    );
    assert!(warn.message.contains("issue-refund") && warn.message.contains("payments"));
    assert!(
        warn.fix.contains("Delete `needs-a-person: yes`"),
        "the fix has to be typeable: {}",
        warn.fix
    );

    let _ = std::fs::remove_dir_all(&copy);
}

// ─────────────────────────────────────────── the question PACT ships is a question

#[test]
fn the_question_pact_ships_would_pass_every_check_a_written_one_has_to() {
    // A default nobody holds to the rules is how a shorthand comes to be a
    // weaker gate without anybody deciding it should be. So the shipped file is
    // held to the four rules `report.rs` holds an author's question to: it says
    // something, it says what an answer looks like, somebody can answer it, and
    // its deadline can be read.
    let shipped = approvals::shipped_question();
    let says = shipped
        .get("says")
        .and_then(Node::as_str)
        .unwrap_or("")
        .trim();
    assert!(!says.is_empty(), "a park with nothing to read is a hang");
    assert!(
        !says.contains("pact:question"),
        "the person reads wording, not the name of a file: {says}"
    );

    let answer = shipped
        .get("answer")
        .and_then(Node::as_map)
        .expect("it says what an answer is");
    assert!(
        answer
            .values()
            .any(|e| e.node.as_str() == Some("yes or no")),
        "a gate with no yes-or-no in it cannot be refused"
    );

    let asked_of = shipped
        .get("asked-of")
        .and_then(Node::as_list)
        .unwrap_or_default();
    assert!(
        !asked_of.is_empty(),
        "naming nobody means nobody can answer"
    );

    assert_eq!(
        shipped.get("answer-within").and_then(Node::as_str),
        Some("30m")
    );
    let timeout = shipped
        .get("if-nobody-answers")
        .and_then(Node::as_str)
        .unwrap_or("");
    assert!(
        ["stop-and-say-so", "decline"].contains(&timeout),
        "silence is never a yes: {timeout}"
    );
    assert!(
        shipped.get("escalates-to").is_none(),
        "there is nobody here to escalate to, so it must not claim to"
    );
}

#[test]
fn the_shipped_question_is_read_from_the_file_an_author_can_open() {
    // Not a literal in Rust. A wording change in `spec/questions/is-this-ok.yaml`
    // has to reach the binary, or the file is documentation of something else.
    let text = std::fs::read_to_string(
        Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../spec/questions/is-this-ok.yaml"),
    )
    .expect("the shipped question is a file on disk");
    let says = approvals::shipped_question()
        .get("says")
        .and_then(Node::as_str)
        .unwrap();
    assert!(
        text.contains(says),
        "the compiled copy and the file disagree about the wording"
    );
}

// ─────────────────────────────────────────────────────────────────────── helpers

fn copy_of(why: &str) -> Utf8PathBuf {
    let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
        .join(format!("pact-one-line-{why}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    copy_tree(&tree(), &base);
    base
}

fn copy_of_the_example(why: &str) -> Utf8PathBuf {
    let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
        .join(format!("pact-one-line-{why}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&base);
    copy_tree(&worked_example(), &base);
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
