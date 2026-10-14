//! End-to-end: a workflow's stage runs once a run and keeps what it did under its
//! name, so `pact check` refuses a line that leads back to a stage the run has
//! already been through (`pact-loader/src/workflows.rs`,
//! `loader/a-route-back-to-an-earlier-stage`). Before, such a tree loaded, and the
//! second visit was answered with the first visit's answer, so the run went round
//! for ever at full speed (found by Bud Agent Flow's corpus case #94, whose
//! declined diff went back to its dry run). Driven against the shipped
//! `a-workflow-that-calls-and-answers` tree, with a decide that can go back.

use std::process::Command;

fn with_reply_routed(to: &str, tag: &str) -> std::path::PathBuf {
    let src = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/trees/a-workflow-that-calls-and-answers");
    let dst = std::env::temp_dir().join(format!("pact-back-{tag}-{}", std::process::id()));
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
    let routed = text.replace(
        "      answered: reply\n  reply:\n",
        &format!(
            "      answered: again\n  again:\n    does: decide\n    \
             chooses-between: {{ lost: {to}, other: reply }}\n    by:\n      - rules:\n          \
             - when: [{{ value: steps.look.status, is: lost }}]\n            choose: lost\n          \
             - choose: other\n  reply:\n"
        ),
    );
    std::fs::write(&flow, routed).unwrap();
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
fn a_decide_that_goes_on_loads_clean() {
    let (ok, said) = check(&with_reply_routed("reply", "on"));
    assert!(ok, "{said}");
    assert!(!said.contains("a-route-back"), "{said}");
}

#[test]
fn a_decide_that_goes_back_is_refused_where_the_line_is_written() {
    let (ok, said) = check(&with_reply_routed("look", "back"));
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-route-back-to-an-earlier-stage"),
        "{said}"
    );
    assert!(said.contains("'again' goes back to 'look'"), "{said}");
    assert!(said.contains("inside a `repeat`"), "{said}");
}
