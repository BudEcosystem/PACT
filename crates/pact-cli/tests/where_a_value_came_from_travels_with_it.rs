//! The static half of law 7 of `docs/97-PRIMITIVES.md` (`docs/98` WP-6): what a
//! reader of the tree can see about where a value came from is held.
//!
//! Driven against `tests/trees/workflows-79-supervisor`, whose `read` repeat
//! remembers `notes` from `steps.specialists.notes` — an `each` whose calls go
//! to specialist agents chosen from a `may-call:` list.

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
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/workflows-79-supervisor");
    let dst = std::env::temp_dir().join(format!("pact-origins-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    dst
}

fn edit(tree: &Path, file: &str, from: &str, to: &str) {
    let path = tree.join(file);
    let text = std::fs::read_to_string(&path).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {file} has no {from:?}"
    );
    std::fs::write(&path, text.replacen(from, to, 1)).unwrap();
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

const FLOW: &str = "workflows/first-read.yaml";
const NOTES: &str = "        comes-from: steps.specialists.notes\n";

#[test]
fn the_tree_as_shipped_loads() {
    let (ok, said) = check(&tree("as-shipped"));
    assert!(ok, "{said}");
}

#[test]
fn notes_a_teammate_wrote_may_not_be_kept_by_a_fact_that_refuses_teammates() {
    let t = tree("teammate");
    edit(
        &t,
        FLOW,
        NOTES,
        &format!("{NOTES}        never-from: [a teammate]\n"),
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/written-from-a-source-it-refuses"),
        "{said}"
    );
    assert!(said.contains("a teammate"), "{said}");
}

#[test]
fn a_fact_that_refuses_some_other_source_is_not_bothered() {
    let t = tree("other-source");
    edit(
        &t,
        FLOW,
        NOTES,
        &format!("{NOTES}        never-from: [tool output]\n"),
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

#[test]
fn a_value_hidden_from_the_ai_may_not_be_handed_to_an_agent() {
    let t = tree("hidden");
    edit(
        &t,
        FLOW,
        "kept-for: 365 days",
        "hides:\n  steps.redact.file: [the-ai]\nkept-for: 365 days",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/hidden-from-the-ai-but-handed-to-it"),
        "{said}"
    );
}

#[test]
fn a_value_hidden_from_the_logs_may_still_be_read_by_the_ai() {
    let t = tree("logs");
    edit(
        &t,
        FLOW,
        "kept-for: 365 days",
        "hides:\n  steps.redact.file: [logs]\nkept-for: 365 days",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

const CATALOGUE: &str = "models:\n  models:\n    tenant-model:\n      description: A model in the university's own tenant.\n      served-by:\n        region: REGION\n";

#[test]
fn a_model_served_outside_the_region_is_refused() {
    let t = tree("region");
    let ws = t.join("workspace.yaml");
    let mut text = std::fs::read_to_string(&ws).unwrap();
    text.push_str(&CATALOGUE.replace("REGION", "us-east"));
    std::fs::write(&ws, text).unwrap();
    let card = t.join("agents/card-writer/agent.yaml");
    let mut text = std::fs::read_to_string(&card).unwrap();
    text.push_str("model:\n  - tenant-model\n");
    std::fs::write(&card, text).unwrap();
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-model-outside-the-region"),
        "{said}"
    );
    assert!(said.contains("'us-east'"), "{said}");
}

#[test]
fn a_model_served_inside_it_is_fine() {
    let t = tree("in-region");
    let ws = t.join("workspace.yaml");
    let mut text = std::fs::read_to_string(&ws).unwrap();
    text.push_str(&CATALOGUE.replace("REGION", "university-tenant-region"));
    std::fs::write(&ws, text).unwrap();
    let card = t.join("agents/card-writer/agent.yaml");
    let mut text = std::fs::read_to_string(&card).unwrap();
    text.push_str("model:\n  - tenant-model\n");
    std::fs::write(&card, text).unwrap();
    let (_, said) = check(&t);
    assert!(!said.contains("a-model-outside-the-region"), "{said}");
}
