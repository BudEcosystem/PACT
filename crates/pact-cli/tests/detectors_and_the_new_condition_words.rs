//! `docs/98` WP-12: detectors an author declares, and the condition words
//! `effect:`, `in-share:` and `looks-like:`.

use std::path::{Path, PathBuf};
use std::process::Command;

fn copy(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}

fn desk(name: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/refund-desk");
    let dst = std::env::temp_dir().join(format!("pact-detect-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    dst
}

fn write(tree: &Path, file: &str, text: &str) {
    let path = tree.join(file);
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(path, text).unwrap();
}

fn append(tree: &Path, file: &str, text: &str) {
    let path = tree.join(file);
    let mut was = std::fs::read_to_string(&path).unwrap();
    was.push_str(text);
    std::fs::write(path, was).unwrap();
}

fn check(tree: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(tree)
        .output()
        .unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

const DETECTOR: &str = "detectors:\n  order reference:\n    description: An order reference.\n    looks-like:\n      - ORD-[0-9]{8}\n    examples:\n      - ORD-12345678\n";

#[test]
fn a_redaction_may_name_a_declared_detector() {
    let t = desk("declared");
    append(&t, "workspace.yaml", DETECTOR);
    append(
        &t,
        "redaction.yaml",
        "  - replace anything that looks like an order reference with \"[ref]\"\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

#[test]
fn a_thing_nobody_declared_is_still_refused() {
    let t = desk("undeclared");
    append(
        &t,
        "redaction.yaml",
        "  - replace anything that looks like an order reference with \"[ref]\"\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
}

#[test]
fn an_approval_rule_may_gate_on_what_a_call_does() {
    let t = desk("effect");
    append(
        &t,
        "policies/approvals.yaml",
        "  - when:\n      - { tool: payments, effect: spends }\n    because: every payment action, whatever it is called\n    question: is-this-ok\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

#[test]
fn effect_on_a_value_is_refused() {
    let t = desk("effect-value");
    write(
        &t,
        "ports/odd.yaml",
        "description: An odd port.\nkind: inbound-call\nanswers: refund-desk\nonly-when:\n  - { value: input.message, effect: spends }\nwho-can-reach-it: [anyone]\n",
    );
    let (_, said) = check(&t);
    assert!(said.contains("rule: loader/effect-of-no-call"), "{said}");
}

#[test]
fn a_value_word_on_a_call_is_refused() {
    let t = desk("share-call");
    append(
        &t,
        "policies/approvals.yaml",
        "  - when:\n      - { tool: payments, in-share: 5% }\n    because: a sample\n    question: is-this-ok\n",
    );
    let (_, said) = check(&t);
    assert!(
        said.contains("rule: loader/a-value-word-on-a-call"),
        "{said}"
    );
}

#[test]
fn looks_like_must_name_something_known() {
    let t = desk("looks-like");
    write(
        &t,
        "ports/odd.yaml",
        "description: An odd port.\nkind: inbound-call\nanswers: refund-desk\nonly-when:\n  - { value: input.message, looks-like: shoe size }\nwho-can-reach-it: [anyone]\n",
    );
    let (_, said) = check(&t);
    assert!(
        said.contains("rule: loader/looks-like-nothing-known"),
        "{said}"
    );

    let t = desk("looks-like-ok");
    append(&t, "workspace.yaml", DETECTOR);
    write(
        &t,
        "ports/odd.yaml",
        "description: An odd port.\nkind: inbound-call\nanswers: refund-desk\nonly-when:\n  - { value: input.message, looks-like: order reference }\nwho-can-reach-it: [anyone]\n",
    );
    let (_, said) = check(&t);
    assert!(!said.contains("looks-like-nothing-known"), "{said}");
}
