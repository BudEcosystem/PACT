//! 02P §3.2 A2: `model:` may be an ordered list, tried in order when a call
//! fails.
//!
//! The list lives in the document, and not only in a gateway, so that every
//! fallback is held to the same lines a single pinned model is. A sovereign
//! workspace that falls back to an off-box model has to be refused at check
//! time, at the entry that leaves, or the fallback is the hole in the wall.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree(name: &str, model: &str) -> PathBuf {
    let root = std::env::temp_dir().join(format!("pact-model-list-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(root.join("agents")).unwrap();
    std::fs::write(
        root.join("workspace.yaml"),
        "name: fallback\nallow-egress: []\n",
    )
    .unwrap();
    std::fs::write(
        root.join("agents/desk.yaml"),
        format!("description: answers\ninstructions: Answer.\nmodel: {model}\n"),
    )
    .unwrap();
    root
}

fn run(args: &[&str], root: &Path) -> (bool, String) {
    let out = pact().args(args).arg(root).output().expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.success(), text)
}

#[test]
fn a_list_of_served_models_loads_and_keeps_its_order() {
    let root = tree("ok", "[qwen2.5-14b-instruct, qwen2.5-7b-instruct]");
    let (ok, text) = run(&["check"], &root);
    assert!(ok, "{text}");
    let (_, shown) = run(&["show"], &root);
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("json");
    assert_eq!(
        doc["agents"]["desk"]["model"],
        serde_json::json!(["qwen2.5-14b-instruct", "qwen2.5-7b-instruct"])
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn one_model_written_alone_still_means_one_model() {
    let root = tree("one", "qwen2.5-7b-instruct");
    let (ok, text) = run(&["check"], &root);
    assert!(ok, "{text}");
    let (_, shown) = run(&["show"], &root);
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("json");
    assert_eq!(doc["agents"]["desk"]["model"], "qwen2.5-7b-instruct");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_fallback_that_leaves_the_box_is_refused_at_that_entry() {
    let root = tree("egress", "[qwen2.5-14b-instruct, claude-opus-5]");
    let (ok, text) = run(&["check"], &root);
    assert!(!ok, "a fallback off the box must not load:\n{text}");
    assert!(text.contains("rule: loader/leaves-the-box"), "{text}");
    assert!(text.contains("`model: claude-opus-5`"), "{text}");
    // Underlined at the second entry, which is the one to change.
    assert!(text.contains("desk.yaml:3:31"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_misspelt_fallback_is_refused_like_a_misspelt_model() {
    let root = tree("typo", "[qwen2.5-14b-instruct, qwen2.5-7b-instrukt]");
    let (ok, text) = run(&["check"], &root);
    assert!(!ok, "{text}");
    assert!(text.contains("rule: schema/no-such-name"), "{text}");
    assert!(text.contains("qwen2.5-7b-instrukt"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn discovery_names_the_model_a_run_starts_on_and_the_whole_chain() {
    let root = tree("discover", "[qwen2.5-14b-instruct, qwen2.5-7b-instruct]");
    let (ok, text) = run(&["discover"], &root);
    assert!(ok, "{text}");
    let inventory: serde_json::Value = serde_json::from_str(&text).expect("json");
    let agent = &inventory[0]["agents"][0];
    assert_eq!(agent["model"], "qwen2.5-14b-instruct");
    assert_eq!(
        agent["models"],
        serde_json::json!(["qwen2.5-14b-instruct", "qwen2.5-7b-instruct"])
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_fallback_that_is_the_grader_is_said_like_a_pinned_one() {
    // The worked example grades with `qwen2.5-14b-instruct`; a desk that may
    // fall back to it would have some of its answers marked by their author.
    let src = PathBuf::from(format!(
        "{}/../../examples/refund-desk",
        env!("CARGO_MANIFEST_DIR")
    ));
    let root = std::env::temp_dir().join(format!("pact-model-list-grader-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    copy(&src, &root);
    let agent = root.join("agents/refund-desk/agent.yaml");
    let written = std::fs::read_to_string(&agent).unwrap();
    std::fs::write(
        &agent,
        format!("{written}\nmodel: [qwen2.5-vl-7b-instruct, qwen2.5-14b-instruct]\n"),
    )
    .unwrap();
    let (_, text) = run(&["check"], &root);
    assert!(
        text.contains("loader/judge-is-the-model-under-test"),
        "{text}"
    );
    assert!(text.contains("runs on `qwen2.5-14b-instruct`"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}
