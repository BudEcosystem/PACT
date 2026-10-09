//! A failed item is kept, not dropped (02W §2.7, §2.10, §8), the loader's half.
//!
//! What happens after a stage has failed every attempt is one record,
//! `if-it-fails:` (F2), and its choices take the lines they need: `carry-on`
//! the answer to go on with, `use-a-backup` what to call instead, with the
//! stage's own `bind:`. A ceiling's `when-it-runs-out:` that needs one of those
//! lines takes it from the same record. Over #48's tree
//! (`tests/trees/workflows-48-invoices/`), whose `each` keeps every item with
//! `if-someone-fails: carry-on`; what a run does with them is the runtime's half.

use std::path::{Path, PathBuf};
use std::process::Command;

const FLOW: &str = "workflows/ap-inbox.yaml";
const READ: &str = "        bind: { file: item.file }\n";

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/workflows-48-invoices"
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

/// `pact check` over a copy with `edits` (file, text, replacement) applied and
/// `extra` files written: (loaded, what it printed).
fn check(label: &str, edits: &[(&str, &str, &str)], extra: &[(&str, &str)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-kept-{label}-{}", std::process::id()));
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
    for (file, text) in extra {
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

const UNREAD: (&str, &str) = (
    "values/unread-invoice.yaml",
    "description: What an invoice nobody could read is carried on as.\nshape: text\nvalue: unread\n",
);

fn plan(lines: &str) -> String {
    format!("{READ}        if-it-fails:\n{lines}")
}

#[test]
fn every_item_is_kept_when_one_fails_and_the_tree_says_so() {
    let (ok, text) = check("as-written", &[], &[]);
    assert!(ok, "{text}");
    let flow = std::fs::read_to_string(tree().join(FLOW)).unwrap();
    assert!(flow.contains("      if-someone-fails: carry-on"), "{flow}");
}

/// #48's `vendor` stage, whose failure plan asks the vendor-master queue.
const VENDOR: (&str, &str) = (
    "workflows/one-invoice.yaml",
    "      after-that: ask-a-person       # the vendor-master queue creates it, then resumes here\n      asks: create-the-vendor\n",
);

const NET_30: (&str, &str) = (
    "values/net-30.yaml",
    "description: The payment terms a vendor nobody found is given.\nshape: text\nvalue: net 30\n",
);

/// `vendor` carrying on with `payment-terms` read from `from`.
fn vendor_carries_on(label: &str, from: &str) -> (bool, String) {
    check(
        label,
        &[(
            VENDOR.0,
            VENDOR.1,
            &format!(
                "      after-that: carry-on\n      carry-on-with: {{ payment-terms: {from} }}\n"
            ),
        )],
        &[NET_30],
    )
}

#[test]
fn carrying_on_with_what_the_stage_answers_loads() {
    let (ok, text) = vendor_carries_on("carry-on", "values.net-30");
    assert!(ok, "{text}");
}

#[test]
fn what_a_stage_carries_on_with_is_a_binding_to_something() {
    for (label, from, said) in [
        (
            "carry-on-nowhere",
            "steps.nowhere.at-all",
            "'vendor' reads 'steps.nowhere.at-all', and this workflow has no stage called 'nowhere'",
        ),
        (
            "carry-on-no-input",
            "input.nothing-like-this",
            "'vendor' reads 'input.nothing-like-this', and the workflow 'one-invoice' accepts no \
             'nothing-like-this'",
        ),
        (
            "carry-on-no-value",
            "values.net-60",
            "`values.net-60` names no value",
        ),
    ] {
        let (ok, text) = vendor_carries_on(label, from);
        assert!(!ok, "{from}: {text}");
        assert!(text.contains(said), "{from}: {text}");
        assert!(
            text.contains("rule: loader/a-binding-to-nothing"),
            "{from}: {text}"
        );
    }
}

#[test]
fn what_a_stage_carries_on_with_is_in_the_shape_of_its_answer() {
    let (ok, text) = check(
        "carry-on-shape",
        &[(
            FLOW,
            READ,
            &plan(
                "          after-that: carry-on\n          carry-on-with: { invoice: values.unread-invoice }\n",
            ),
        )],
        &[UNREAD],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'read' fills `invoice:` of the answer of 'invoice-reader' from \
             'values.unread-invoice', which is `text`, and the answer of 'invoice-reader' has \
             `invoice-data` there"
        ),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/a-call-that-does-not-fit"),
        "{text}"
    );
}

#[test]
fn carrying_on_with_nothing_is_refused() {
    let (ok, text) = check(
        "carry-on-bare",
        &[(FLOW, READ, &plan("          after-that: carry-on\n"))],
        &[],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("rule: schema/missing-companion"), "{text}");
    assert!(text.contains("'carry-on-with'"), "{text}");
}

#[test]
fn carrying_on_with_a_field_the_stage_never_answers_is_refused() {
    let (ok, text) = check(
        "carry-on-wrong",
        &[(
            FLOW,
            READ,
            &plan(
                "          after-that: carry-on\n          carry-on-with: { invoices: values.unread-invoice }\n",
            ),
        )],
        &[UNREAD],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'read' carries on with `invoices`, and 'invoice-reader' does not answer with \
             `invoices`"
        ),
        "{text}"
    );
    assert!(
        text.contains("Use one of the fields 'invoice-reader' answers with: `invoice`."),
        "{text}"
    );
    assert!(text.contains("rule: loader/a-binding-to-nothing"), "{text}");
}

const BACKUP_READER: (&str, &str) = (
    "agents/backup-reader/agent.yaml",
    "description: Reads an invoice another way.\ninstructions: Read the invoice.\naccepts:\n  file: file\nanswers-with:\n  invoice: invoice-data\n",
);

#[test]
fn a_backup_is_called_with_the_stages_own_bind() {
    let (ok, text) = check(
        "backup",
        &[(
            FLOW,
            READ,
            &plan("          after-that: use-a-backup\n          backup: backup-reader\n"),
        )],
        &[BACKUP_READER],
    );
    assert!(ok, "{text}");
    let (ok, text) = check(
        "backup-unfit",
        &[(
            FLOW,
            READ,
            &plan("          after-that: use-a-backup\n          backup: netsuite/get-vendor\n"),
        )],
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'read' falls back on 'netsuite/get-vendor' and leaves its inputs 'tax-id', 'name' \
             empty, so 'netsuite/get-vendor' would run without them."
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "'read' fills `file:` of 'netsuite/get-vendor', and 'netsuite/get-vendor' takes no \
             input by that name."
        ),
        "{text}"
    );
    assert_eq!(
        text.matches("rule: loader/a-call-that-does-not-fit")
            .count(),
        2,
        "{text}"
    );
    let (ok, text) = check(
        "backup-missing",
        &[(
            FLOW,
            READ,
            &plan("          after-that: use-a-backup\n          backup: spare-reader\n"),
        )],
        &[],
    );
    assert!(!ok && text.contains("rule: loader/no-such-name"), "{text}");
}

#[test]
fn a_backup_is_held_to_the_stages_bind_as_a_call_is() {
    // The same `bind:` written as a direct call to the backup is refused the
    // same two ways: a shape that does not fit, and an input it does not take.
    let by_number = (
        "tools/netsuite.yaml",
        "  find-po-and-receipts:\n",
        "  find-vendor-by-number:\n    description: Find a vendor by its tax number.\n    \
         reads-only: yes\n    takes:\n      tax-id: whole number\n    answers-with:\n      \
         id: text\n      payment-terms: text\n  find-po-and-receipts:\n",
    );
    let (ok, text) = check(
        "backup-shape",
        &[
            by_number,
            (
                VENDOR.0,
                VENDOR.1,
                "      after-that: use-a-backup\n      backup: netsuite/find-vendor-by-number\n",
            ),
        ],
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'vendor' fills `tax-id:` of 'netsuite/find-vendor-by-number' from \
             'input.invoice.vendor-tax-id', which is `text`, and \
             'netsuite/find-vendor-by-number' takes `whole number` there"
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "'vendor' fills `name:` of 'netsuite/find-vendor-by-number', and \
             'netsuite/find-vendor-by-number' takes no input by that name."
        ),
        "{text}"
    );
    assert_eq!(
        text.matches("rule: loader/a-call-that-does-not-fit")
            .count(),
        2,
        "{text}"
    );
}

#[test]
fn running_out_takes_its_companion_from_the_stages_failure_plan() {
    let ceiling = "      when-it-runs-out: ask-a-person\n      asks: too-many-attachments\n";
    let (ok, text) = check(
        "runs-out-bare",
        &[(FLOW, ceiling, "      when-it-runs-out: use-a-backup\n")],
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'when-it-runs-out' says 'use-a-backup', and 'each-attachment' has no \
             `if-it-fails.backup:` — so nothing says what to call instead."
        ),
        "{text}"
    );
    assert!(text.contains("rule: schema/missing-companion"), "{text}");
    let (ok, text) = check(
        "runs-out-undo",
        &[(
            FLOW,
            ceiling,
            "      when-it-runs-out: undo\n    if-it-fails:\n      after-that: undo\n      undo: each-attachment\n",
        )],
        &[],
    );
    assert!(ok, "{text}");
}

#[test]
fn a_workflows_own_ceiling_has_no_stage_to_take_a_backup_from() {
    let (ok, text) = check(
        "own-backup",
        &[(
            "workflows/one-invoice.yaml",
            "  when-it-runs-out: ask-a-person\n  asks: invoice-is-stuck\n",
            "  when-it-runs-out: use-a-backup\n",
        )],
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'when-it-runs-out' on the workflow 'one-invoice' says 'use-a-backup', and only a \
             stage has an `if-it-fails:`"
        ),
        "{text}"
    );
}
