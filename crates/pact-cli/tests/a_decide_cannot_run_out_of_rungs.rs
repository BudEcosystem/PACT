//! A `decide` cannot run out of rungs (02W §3 WF-15, WF-16, §8): the rules
//! half, over #48's routing and tiers (`tests/trees/an-invoice-case/`).
//!
//! A decision by written rules always chooses: its last rung ends with an
//! "otherwise" (a rule with no `when:`), so a case none of the rules fits still
//! has a label, and every label a rule picks is one the stage can go to. The
//! agent and person rungs (and WF-17) come with deciding by models and people.

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

fn check_edited(name: &str, from: &str, to: &str) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-rungs-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join("tests/trees/an-invoice-case"), &dst);
    let p = dst.join(FLOW);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(text.contains(from), "fixture drifted: {from:?}");
    std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dst.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

const OTHERWISE: &str = "          - choose: owner\n";

#[test]
fn rules_with_no_otherwise_are_refused() {
    let (ok, text) = check_edited(
        "no-otherwise",
        OTHERWISE,
        "          - when: [{ value: input.invoice.total, less-than: 50000 USD }]\n            choose: owner\n",
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-decide-that-can-run-out-of-rungs"),
        "{text}"
    );
    assert!(
        text.contains(
            "'tiers' ends with written rules, and every one of them has a `when:` — so a case \
             none of them fits is decided by nobody and the run stops there."
        ),
        "{text}"
    );
    assert!(
        text.contains(
            "fix: End with an \"otherwise\" rule — a last rule with no `when:`, `- choose: auto`"
        ),
        "{text}"
    );
}

#[test]
fn a_decide_with_no_rung_is_refused() {
    let flow =
        std::fs::read_to_string(repo().join("tests/trees/an-invoice-case").join(FLOW)).unwrap();
    let start = flow.find("  tiers:\n").unwrap();
    let by = start + flow[start..].find("    by:\n").unwrap();
    let end = by + flow[by..].find("\n\n").unwrap() + 1;
    let (ok, text) = check_edited("no-rung-at-all", &flow[by..end], "");
    assert!(!ok, "{text}");
    assert!(
        text.contains("'tiers' decides with no rung at all, so nothing ever picks a label."),
        "{text}"
    );
    assert!(
        text.contains("fix: Add `by:` with written rules that end in an \"otherwise\""),
        "{text}"
    );
}

#[test]
fn a_label_with_nowhere_to_go_is_refused_and_the_nearest_offered() {
    let (ok, text) = check_edited(
        "label",
        "            choose: auto\n",
        "            choose: autp\n",
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/a-label-with-nowhere-to-go"),
        "{text}"
    );
    assert!(
        text.contains(
            "A rule of 'tiers' chooses 'autp', and 'tiers' chooses between 'auto', 'owner' — so \
             when this rule holds, the run has nowhere to go."
        ),
        "{text}"
    );
    assert!(
        text.contains("fix: Choose one of the labels offered: `auto`, `owner`"),
        "{text}"
    );
}

#[test]
fn an_otherwise_may_be_written_with_an_empty_when() {
    let (ok, text) = check_edited(
        "empty-when",
        OTHERWISE,
        "          - when: []\n            choose: owner\n",
    );
    assert!(ok, "{text}");
}

#[test]
fn the_tree_decides_every_case_and_loads_clean() {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args([
            "check",
            repo().join("tests/trees/an-invoice-case").to_str().unwrap(),
            "--deny-warnings",
        ])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stdout)
    );
}
