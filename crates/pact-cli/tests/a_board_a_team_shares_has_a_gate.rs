//! The team store (`docs/98` WP-8): a fact the lead shares with its team, and
//! the gate every write passes through. Driven against `examples/patterns/swarm`,
//! whose dispatcher has three solvers on its team.

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

fn tree(name: &str, board: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/patterns/swarm");
    let dst = std::env::temp_dir().join(format!("pact-board-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    let lead = dst.join("agents/dispatcher/agent.yaml");
    let mut text = std::fs::read_to_string(&lead).unwrap();
    text.push_str(board);
    std::fs::write(&lead, text).unwrap();
    dst
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

const BOARD: &str = "remembers:\n  findings:\n    description: what each solver found\n    lasts: one-conversation\n    shared-with: the-team\n    shaped-like:\n      claim: text\n      status: one of open, solved\n    admitted-when:\n      - { value: entry.status, is-one-of: [open, solved] }\n";

#[test]
fn a_board_with_a_gate_loads() {
    let (ok, said) = check(&tree("plain", BOARD));
    assert!(ok, "{said}");
}

#[test]
fn a_judge_that_answers_yes_or_no_loads() {
    let t = tree("judge", &format!("{BOARD}    admitted-by: solver-a\n"));
    let judge = t.join("agents/solver-a/agent.yaml");
    let mut text = std::fs::read_to_string(&judge).unwrap();
    text.push_str("answers-with:\n  admit: yes or no\n  because: text\n");
    std::fs::write(&judge, text).unwrap();
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

#[test]
fn a_judge_that_cannot_say_yes_is_refused() {
    let (ok, said) = check(&tree(
        "mute-judge",
        &format!("{BOARD}    admitted-by: solver-a\n"),
    ));
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/an-admitter-that-cannot-say-yes"),
        "{said}"
    );
}

#[test]
fn an_admission_line_may_only_read_the_entry() {
    let bad = BOARD.replace("value: entry.status", "value: entry.mood");
    let (ok, said) = check(&tree("no-part", &bad));
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/admitted-when-reads-no-part"),
        "{said}"
    );
    assert!(
        said.contains("`entry.claim`"),
        "the fix names the parts: {said}"
    );
}

#[test]
fn a_board_with_no_team_is_refused() {
    let t = tree("no-team", BOARD);
    let lead = t.join("agents/dispatcher/agent.yaml");
    let text = std::fs::read_to_string(&lead).unwrap();
    let start = text.find("team:\n").unwrap();
    let end = text.find("teamwork:").unwrap();
    let without = format!("{}{}", &text[..start], &text[end..]);
    let without = without.replace(
        "teamwork:\n  waits-for: the-first-good-answer\n  starts: all-at-once\n  divides-the-budget: evenly\n  if-someone-fails: carry-on\n",
        "",
    );
    std::fs::write(&lead, without).unwrap();
    let (_, said) = check(&t);
    assert!(said.contains("rule: loader/shared-with-no-team"), "{said}");
}

#[test]
fn admission_on_a_fact_nobody_shares_is_never_read() {
    let own = BOARD.replace("    shared-with: the-team\n", "");
    let (ok, said) = check(&tree("unshared", &own));
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/admission-on-memory-nobody-shares"),
        "{said}"
    );
}

#[test]
fn sharing_the_workspaces_memory_means_nothing() {
    let t = tree("workspace", "");
    let ws = t.join("workspace.yaml");
    let mut text = std::fs::read_to_string(&ws).unwrap();
    text.push_str("remembers:\n  notes:\n    description: notes\n    lasts: forever\n    shared-with: the-team\n");
    std::fs::write(&ws, text).unwrap();
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/shared-where-it-means-nothing"),
        "{said}"
    );
}
