//! End-to-end: `done` is where a route ends, so `pact check` refuses a stage named
//! `done`, which no line could ever send anything to
//! (`pact-loader/src/workflows.rs`, `loader/a-stage-named-done`). Driven against
//! the shipped `a-workflow-that-calls-and-answers` tree, with its answer stage
//! renamed.

use std::process::Command;

fn with_answer_stage_named(name: &str) -> std::path::PathBuf {
    let src = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/trees/a-workflow-that-calls-and-answers");
    let dst = std::env::temp_dir().join(format!("pact-done-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    for entry in [
        "workspace.yaml",
        "workflows/order-status.yaml",
        "resources/order-server.yaml",
        "tools/orders.yaml",
    ] {
        let to = dst.join(entry);
        std::fs::create_dir_all(to.parent().unwrap()).unwrap();
        std::fs::copy(src.join(entry), &to).unwrap();
    }
    let flow = dst.join("workflows/order-status.yaml");
    let text = std::fs::read_to_string(&flow).unwrap();
    assert!(
        text.contains("      answered: reply\n  reply:\n"),
        "the shipped workflow changed"
    );
    let renamed = text.replace(
        "      answered: reply\n  reply:\n",
        &format!("      answered: {name}\n  {name}:\n"),
    );
    std::fs::write(&flow, renamed).unwrap();
    dst
}

fn check(tree: &std::path::Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(tree)
        .output()
        .unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

#[test]
fn a_stage_with_another_name_loads_clean() {
    let (ok, said) = check(&with_answer_stage_named("finish"));
    assert!(ok, "{said}");
    assert!(!said.contains("a-stage-named-done"), "{said}");
}

#[test]
fn a_stage_named_done_is_refused_where_its_name_is_written() {
    let (ok, said) = check(&with_answer_stage_named("done"));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/a-stage-named-done"), "{said}");
    assert!(said.contains("order-status.yaml:14"), "{said}");
    assert!(said.contains("Give the stage another name"), "{said}");
}
