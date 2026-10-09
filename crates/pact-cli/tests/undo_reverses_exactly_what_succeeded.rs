//! Undo reverses exactly what succeeded (02W §2.12, §3 WF-26, §8), the
//! loader's half.
//!
//! A write says how it is undone (`undone-by:` on its action, its stage or its
//! workflow), and the undo is given only what the write was given and what it
//! answered (D10: not the value read before it). So the loader holds that an
//! undo is itself a write, and that every input it takes is one of those, by
//! name and in a shape that fits. A `status-check:` is a read the call's own
//! inputs fill. Over #60's tree (`tests/trees/workflows-60-interconnection/`),
//! where a cancellation undoes the payment link, the capacity reservation and
//! the envelope, newest first; running that undo is the runtime's half.

use std::path::{Path, PathBuf};
use std::process::Command;

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/workflows-60-interconnection"
    ))
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

fn check(label: &str, edits: &[(&str, &str, &str)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-undo-{label}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
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

#[test]
fn every_write_a_cancellation_reverses_has_an_undo_that_fits() {
    let (ok, text) = check("as-written", &[]);
    assert!(ok, "{text}");
    // The four writes the design's cancellation undoes are Changes: none is
    // noted as a write that cannot be undone.
    for stage in ["fee", "reserve", "envelope", "meter"] {
        assert!(!text.contains(&format!("note: '{stage}' calls")), "{text}");
    }
}

#[test]
fn an_undo_that_only_reads_is_refused() {
    let (ok, text) = check(
        "a-read",
        &[(
            "tools/docusign.yaml",
            "    undone-by: docusign/void-envelope\n",
            "    undone-by: cyme/run-power-flow\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "`docusign/send-envelope` is undone by 'cyme/run-power-flow', which only reads — so \
             undoing it would put nothing back."
        ),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/an-undo-that-does-not-fit"),
        "{text}"
    );
}

#[test]
fn an_undo_whose_inputs_the_write_cannot_fill_is_refused_and_both_are_shown() {
    let (ok, text) = check(
        "unfit",
        &[(
            "tools/docusign.yaml",
            "    takes: { envelope-id: text }\n",
            "    takes: { envelope-ref: text }\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "`docusign/send-envelope` is undone by 'docusign/void-envelope', which takes \
             `envelope-ref`, and an undo is given only what the write was given and answered"
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "fix: Name a write whose `takes:` fits: 'docusign/void-envelope' takes \
             `envelope-ref`, and `docusign/send-envelope` gives `agreement`, `signers` (its \
             inputs) and `envelope-id` (its answer)."
        ),
        "{text}"
    );
    // The same name in another shape does not fit either.
    let (ok, text) = check(
        "unfit-shape",
        &[(
            "tools/docusign.yaml",
            "    takes: { envelope-id: text }\n",
            "    takes: { envelope-id: money }\n",
        )],
    );
    assert!(
        !ok && text.contains("rule: loader/an-undo-that-does-not-fit"),
        "{text}"
    );
}

#[test]
fn an_undo_names_something_that_is_there() {
    let (ok, text) = check(
        "nothing",
        &[(
            "tools/sap.yaml",
            "    undone-by: sap/cancel-order\n",
            "    undone-by: sap/cancel\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "`sap/create-meter-exchange-order` is undone by 'sap/cancel', and this workspace has \
             nothing by that name."
        ),
        "{text}"
    );
    assert!(text.contains("rule: loader/no-such-name"), "{text}");
}

#[test]
fn a_stage_may_name_its_own_undo_and_it_is_held_the_same_way() {
    let reserve = "    call: reserve-feeder-capacity    # keyed by feeder, below\n";
    let (ok, text) = check(
        "stage-undo",
        &[(
            "workflows/interconnection.yaml",
            reserve,
            &format!("{reserve}    undone-by: powerclerk/release-capacity\n"),
        )],
    );
    assert!(ok, "{text}");
    let (ok, text) = check(
        "stage-undo-unfit",
        &[(
            "workflows/interconnection.yaml",
            reserve,
            &format!("{reserve}    undone-by: docusign/void-envelope\n"),
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("'reserve' is undone by 'docusign/void-envelope', which takes `envelope-id`"),
        "{text}"
    );
}

#[test]
fn a_status_check_is_a_read_the_calls_own_inputs_fill() {
    let at = "    undone-by: powerclerk/release-capacity\n";
    let read = "  find-reservation:\n    description: Find the reservation an application holds.\n    reads-only: yes\n    takes: { application-id: text }\n    answers-with: { reservation-id: text }\n";
    let (ok, text) = check(
        "status",
        &[
            (
                "tools/powerclerk.yaml",
                at,
                &format!("{at}    status-check: powerclerk/find-reservation\n"),
            ),
            (
                "tools/powerclerk.yaml",
                "  release-capacity:\n",
                &format!("{read}  release-capacity:\n"),
            ),
        ],
    );
    assert!(ok, "{text}");
    let (ok, text) = check(
        "status-writes",
        &[(
            "tools/powerclerk.yaml",
            at,
            &format!("{at}    status-check: powerclerk/withdraw-application\n"),
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "`powerclerk/reserve-capacity` is checked by 'powerclerk/withdraw-application', which \
             does not say `reads-only: yes`"
        ),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/a-status-check-that-does-not-fit"),
        "{text}"
    );
    let (ok, text) = check(
        "status-unfit",
        &[(
            "tools/sap.yaml",
            "    undone-by: sap/cancel-order\n",
            "    undone-by: sap/cancel-order\n    status-check: cyme/run-power-flow\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "`sap/create-meter-exchange-order` is checked by 'cyme/run-power-flow', which takes \
             `feeder`, `size-kw-ac`, and a status check is given only the call's own inputs"
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "fix: Name a read whose `takes:` is filled from `account`, `site` (its inputs)."
        ),
        "{text}"
    );
}

#[test]
fn a_failure_plan_undoes_a_stage_and_chooses_items_only_on_an_each() {
    let envelope =
        "    bind: { agreement: steps.contract.agreement, signers: steps.contract.signers }\n";
    let (ok, text) = check(
        "plan-undo",
        &[(
            "workflows/interconnection.yaml",
            envelope,
            &format!("{envelope}    if-it-fails:\n      after-that: undo\n      undo: reserve\n"),
        )],
    );
    assert!(ok, "{text}");
    let (ok, text) = check(
        "plan-undo-where",
        &[(
            "workflows/interconnection.yaml",
            envelope,
            &format!(
                "{envelope}    if-it-fails:\n      after-that: undo\n      undo: reserve\n      \
                 undo-where: [{{ value: input.has-battery, is: yes }}]\n"
            ),
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("'envelope' writes `undo-where:`, and 'reserve' does `call`, not `each`"),
        "{text}"
    );
    let (ok, text) = check(
        "plan-undo-nothing",
        &[(
            "workflows/interconnection.yaml",
            envelope,
            &format!("{envelope}    if-it-fails:\n      after-that: undo\n      undo: reserv\n"),
        )],
    );
    assert!(!ok && text.contains("reserv"), "{text}");
}
