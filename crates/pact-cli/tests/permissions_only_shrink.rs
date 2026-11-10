//! Law 5 of `docs/97-PRIMITIVES.md` (`docs/98` WP-5): an allowance handed on is
//! never wider than the one it came from.
//!
//! Driven against `tests/trees/an-agent-built-on-another`, whose `refunds` is
//! `based-on: desk-pattern` (a spend cap and a stop rule).

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

fn tree(name: &str) -> PathBuf {
    let src =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/an-agent-built-on-another");
    let dst = std::env::temp_dir().join(format!("pact-shrink-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    dst
}

fn append(tree: &Path, file: &str, text: &str) {
    let path = tree.join(file);
    let mut was = std::fs::read_to_string(&path).unwrap();
    was.push_str(text);
    std::fs::write(&path, was).unwrap();
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

const REFUNDS: &str = "agents/refunds/agent.yaml";

#[test]
fn the_tree_as_shipped_loads() {
    let (ok, said) = check(&tree("as-shipped"));
    assert!(ok, "{said}");
}

#[test]
fn a_copy_may_not_restate_what_its_template_locks_below() {
    let t = tree("locked");
    append(
        &t,
        "workspace.yaml",
        "owners:\n  agents.desk-pattern.limits:\n    owned-by: finance\n    locked: here-and-below\n",
    );
    append(
        &t,
        REFUNDS,
        "limits:\n  cost-per-request-under: 0.02 USD\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-locked-part-changed-below"),
        "{said}"
    );
    assert!(said.contains("'finance'"), "{said}");
}

#[test]
fn a_lock_only_here_does_not_reach_a_copy() {
    let t = tree("here");
    append(
        &t,
        "workspace.yaml",
        "owners:\n  agents.desk-pattern.limits:\n    owned-by: finance\n    locked: here\n",
    );
    append(
        &t,
        REFUNDS,
        "limits:\n  cost-per-request-under: 0.02 USD\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

#[test]
fn a_whole_entry_locked_below_keeps_every_setting_it_carries() {
    let t = tree("whole");
    append(
        &t,
        "workspace.yaml",
        "owners:\n  agents/desk-pattern:\n    owned-by: finance\n    locked: here-and-below\n",
    );
    // `instructions:` is the copy's own work, and the base has none: allowed.
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
    // `limits:` is the base's, and locked with it.
    append(
        &t,
        REFUNDS,
        "limits:\n  cost-per-request-under: 0.01 USD\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-locked-part-changed-below"),
        "{said}"
    );
    assert!(said.contains("`limits:`"), "{said}");
}

#[test]
fn a_copy_that_raises_a_ceiling_is_told() {
    let t = tree("wider");
    append(
        &t,
        REFUNDS,
        "limits:\n  cost-per-request-under: 0.50 USD\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (_, said) = check(&t);
    assert!(
        said.contains("rule: loader/a-copy-wider-than-its-template"),
        "{said}"
    );
    assert!(said.contains("0.05 USD"), "{said}");
}

#[test]
fn a_copy_that_lowers_a_ceiling_is_the_point() {
    let t = tree("narrower");
    append(
        &t,
        REFUNDS,
        "limits:\n  cost-per-request-under: 0.01 USD\n  when-it-runs-out: stop-and-say-so\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
    assert!(!said.contains("a-copy-wider-than-its-template"), "{said}");
}

#[test]
fn a_helper_may_not_spend_more_than_the_one_it_works_for() {
    let t = tree("helper");
    // `drafter` asks `checker`; give the drafter a pot and the checker more.
    let drafter = t.join("agents/drafter/agent.yaml");
    let text = std::fs::read_to_string(&drafter).unwrap();
    std::fs::write(
        &drafter,
        text.replacen(
            "limits:\n",
            "limits:\n  cost-per-request-under: 0.10 USD\n",
            1,
        ),
    )
    .unwrap();
    let checker = t.join("agents/checker/agent.yaml");
    let text = std::fs::read_to_string(&checker).unwrap();
    std::fs::write(
        &checker,
        text.replacen(
            "limits:\n",
            "limits:\n  cost-per-request-under: 0.25 USD\n",
            1,
        ),
    )
    .unwrap();
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-helper-allowed-more-than-its-caller"),
        "{said}"
    );
}

#[test]
fn a_budget_handed_in_must_come_from_something_the_run_is_given() {
    let t = tree("budget");
    let refunds = t.join("agents/refunds/agent.yaml");
    let mut text = std::fs::read_to_string(&refunds).unwrap();
    text.push_str("run-inputs:\n  budget: money\nlimits:\n  cost-per-request-under: 0.05 USD\n  cost-per-request-from: run-inputs.budget\n  when-it-runs-out: stop-and-say-so\n");
    std::fs::write(&refunds, &text).unwrap();
    let (ok, said) = check(&t);
    assert!(ok, "{said}");

    std::fs::write(
        &refunds,
        text.replace("run-inputs.budget\n", "run-inputs.wallet\n"),
    )
    .unwrap();
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-budget-from-nowhere"),
        "{said}"
    );
    assert!(said.contains("`run-inputs.budget`"), "{said}");
}
