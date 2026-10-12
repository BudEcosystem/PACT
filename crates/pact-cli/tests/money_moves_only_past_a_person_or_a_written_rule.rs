//! Money moves only past a person or a written rule (02W §3 WF-23, WF-24, §4
//! F1, §8), over #48's invoice run (`tests/trees/workflows-48-invoices/`).
//!
//! As printed, the approval matrix `tiers` decides by written rules a
//! controller owns, so the payment `pay` is reached only past a rule that chose
//! that path or a budget owner's yes. 02W §8's mutation swaps the `tiers` rung
//! for an agent rung: a path a model picked then reaches the money with nobody
//! asked, and the load is refused (WF-23, an error here; from the start it is a
//! warning, as it is on an agent), and once the payment cannot be undone, a
//! model's choice would do what nobody can take back (WF-24, an error, in place
//! of WF-25's note). A wait a person answers on that path, or `needs-a-person:` on the
//! action, puts a person in front of it again. A call to another workflow is
//! judged by that workflow's own checks.

use std::path::{Path, PathBuf};
use std::process::Command;

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

const FLOW: &str = "workflows/one-invoice.yaml";
const BILLS: &str = "tools/bill-com.yaml";
const PICKER: &str = "agents/approval-picker/agent.yaml";

/// The written matrix, as #48 prints it.
const MATRIX: &str = "    by:
      - rules:
          - when:
              - { value: input.invoice.total, less-than: 5000 USD }
              - { value: steps.match.result, is: matched }
            choose: auto
          - when: [{ value: input.invoice.total, less-than: 50000 USD }]
            choose: owner
          - choose: owner-then-controller
";

/// The same choice left to an agent.
const PICKED: &str = "    by:
      - agent: approval-picker
";

const AN_AGENT: &str = "description: Picks how many approvals an invoice needs.
instructions: Say which approvals this invoice needs.
answers-with:
  tier: one of auto, owner, owner-then-controller
";

const CAN_BE_UNDONE: &str = "    undone-by: bill-com/cancel-payment\n";

/// `pact check` on a copy of #48 with each edit made once, and each `(file,
/// text)` written: whether it loaded (warnings allowed), and what it said.
fn check(name: &str, edits: &[(&str, &str, &str)], files: &[(&str, &str)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-money-paths-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join("tests/trees/workflows-48-invoices"), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(text.contains(from), "fixture drifted: {from:?}");
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    for (file, text) in files {
        let p = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    }
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

/// The tree with `tiers` decided by an agent.
fn picked(name: &str, more: &[(&str, &str, &str)]) -> (bool, String) {
    let mut edits = vec![(FLOW, MATRIX, PICKED)];
    edits.extend_from_slice(more);
    check(name, &edits, &[(PICKER, AN_AGENT)])
}

const WF23: &str = "rule: loader/money-moves-with-nobody-asked";
const WF24: &str = "rule: loader/a-model-chose-what-cannot-be-undone";

#[test]
fn a_written_matrix_moves_money_past_a_rule_or_a_person() {
    let (ok, text) = check("as-printed", &[], &[]);
    assert!(ok && !text.contains("warning:"), "{text}");
    assert!(!text.contains(WF23) && !text.contains(WF24), "{text}");
}

#[test]
fn a_path_a_model_picked_reaches_the_money_with_nobody_asked() {
    let (ok, text) = picked("picked", &[]);
    assert!(
        !ok,
        "a model chose the path, so the load is refused:\n{text}"
    );
    assert!(text.contains(WF23), "{text}");
    assert!(
        text.contains(
            "error: 'pay' calls `bill-com/schedule-payment`, which moves money, and the path to it may \
             be picked by the agent 'approval-picker' at 'tiers' with nobody answering yes and no \
             written rule choosing it — so money moves without anybody being asked."
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "fix: Write `needs-a-person: yes` under `schedule-payment` in `tools/bill-com.yaml`"
        ),
        "{text}"
    );
    // The payment can be undone, so a model's choice is not refused outright.
    assert!(!text.contains(WF24), "{text}");
}

#[test]
fn a_model_chose_a_payment_that_cannot_be_undone() {
    let (ok, text) = picked("cannot-undo", &[(BILLS, CAN_BE_UNDONE, "")]);
    assert!(!ok, "{text}");
    assert!(text.contains(WF24), "{text}");
    // One message for the call: not also WF-25's "nothing to do if meant".
    assert!(
        !text.contains(
            "'pay' calls `bill-com/schedule-payment`, which cannot be undone, and nobody is asked"
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "'pay' calls `bill-com/schedule-payment`, which cannot be undone, and the path to it \
             may be picked by the agent 'approval-picker' at 'tiers', with nobody answering yes \
             between — so a model's choice would do what nobody can take back."
        ),
        "{text}"
    );
    assert!(
        text.contains("fix: Ask a person before the write: a wait between 'tiers' and 'pay'"),
        "{text}"
    );
}

#[test]
fn a_wait_a_person_answers_on_the_path_puts_a_person_in_front_of_the_money() {
    let (ok, text) = picked(
        "a-wait",
        &[
            (BILLS, CAN_BE_UNDONE, ""),
            (FLOW, "{ auto: post,", "{ auto: owner-approves,"),
        ],
    );
    assert!(!text.contains(WF23) && !text.contains(WF24), "{text}");
    assert!(ok && !text.contains("warning:"), "{text}");
}

#[test]
fn needs_a_person_on_the_action_puts_a_person_in_front_of_the_money() {
    let (_, text) = picked(
        "needs-a-person",
        &[(BILLS, CAN_BE_UNDONE, "    needs-a-person: yes\n")],
    );
    assert!(!text.contains(WF23) && !text.contains(WF24), "{text}");
}

#[test]
fn a_person_rung_beside_the_agent_does_not_stop_the_agent_choosing() {
    // When the agent is sure, nobody else is asked.
    let (_, text) = picked(
        "agent-then-person",
        &[(
            FLOW,
            PICKED,
            "    by:\n      - agent: approval-picker\n      - asks: budget-owner-approves\n",
        )],
    );
    assert!(text.contains(WF23), "{text}");
}

#[test]
fn money_reached_from_the_start_with_nobody_asked_is_said() {
    // The invoice run's first stage leads straight to the payment.
    let (_, text) = check(
        "from-the-start",
        &[(
            FLOW,
            "    then: { answered: po }\n",
            "    then: { answered: pay }\n",
        )],
        &[],
    );
    // A warning, as it is on an agent: a workspace may mean an ungated spend.
    assert!(
        text.contains(
            "warning: 'pay' calls `bill-com/schedule-payment`, which moves money, and a path from the start \
             reaches it with nobody answering yes and no written rule choosing it"
        ),
        "{text}"
    );
}
