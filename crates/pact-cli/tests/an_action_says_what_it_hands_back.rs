//! 02P §3.2 A4: `answers-with:` on a tool's action, in the vocabulary an
//! agent's `answers-with:` uses, held to it at check time and carried by
//! `pact show` to every adapter.

use std::path::PathBuf;
use std::process::Command;

fn tree(name: &str, unit: &str) -> PathBuf {
    let root =
        std::env::temp_dir().join(format!("pact-action-answers-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    for folder in ["agents", "tools", "resources"] {
        std::fs::create_dir_all(root.join(folder)).unwrap();
    }
    std::fs::write(
        root.join("workspace.yaml"),
        "name: typed\nallow-egress: []\n",
    )
    .unwrap();
    std::fs::write(
        root.join("agents/ops.yaml"),
        "description: watches\ninstructions: Watch.\nuses: [datadog]\n",
    )
    .unwrap();
    std::fs::write(
        root.join("resources/datadog.yaml"),
        "resource-kind: mcp-server\nendpoint: host/datadog\n",
    )
    .unwrap();
    std::fs::write(
        root.join("tools/datadog.yaml"),
        format!(
            "description: metrics\nconnect: datadog\nactions:\n  query-metrics:\n    \
             reads-only: yes\n    takes:\n      query: text\n    answers-with:\n      \
             latest: number\n      unit: {unit}\n"
        ),
    )
    .unwrap();
    root
}

fn pact(args: &[&str], root: &std::path::Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .arg(root)
        .output()
        .unwrap();
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.success(), text)
}

#[test]
fn an_action_answer_in_the_vocabulary_loads_and_reaches_the_document() {
    let root = tree("ok", "one of ms, s");
    let (ok, text) = pact(&["check"], &root);
    assert!(ok, "{text}");
    let (_, shown) = pact(&["show"], &root);
    let doc: serde_json::Value = serde_json::from_str(&shown).unwrap();
    assert_eq!(
        doc["tools"]["datadog"]["actions"]["query-metrics"]["answers-with"],
        serde_json::json!({"latest": "number", "unit": "one of ms, s"})
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_action_answer_outside_the_vocabulary_is_refused() {
    let root = tree("bad", "a bananna");
    let (ok, text) = pact(&["check"], &root);
    assert!(!ok, "{text}");
    assert!(text.contains("rule: schema/not-an-answer-shape"), "{text}");
    assert!(text.contains("datadog.yaml:10"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}
