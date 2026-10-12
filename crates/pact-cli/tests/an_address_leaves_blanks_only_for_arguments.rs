//! End-to-end: a `url:` may leave `{name}` blanks for each call to fill, and
//! `pact check` refuses one that no argument of the tool's actions fills
//! (`pact-loader/src/blanks.rs`). Driven against the shipped `one-line-gate`
//! tree, whose `payments` tool calls `host/payments` with an `order-number`.

use std::process::Command;

fn with_address(name: &str, address: &str) -> std::path::PathBuf {
    let src =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/one-line-gate");
    let dst = std::env::temp_dir().join(format!("pact-blanks-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    for entry in [
        "workspace.yaml",
        "agents/desk/agent.yaml",
        "agents/desk/instructions.md",
        "tools/payments.yaml",
    ] {
        let to = dst.join(entry);
        std::fs::create_dir_all(to.parent().unwrap()).unwrap();
        std::fs::copy(src.join(entry), &to).unwrap();
    }
    let tool = dst.join("tools/payments.yaml");
    let text = std::fs::read_to_string(&tool).unwrap();
    assert!(
        text.contains("url: host/payments\n"),
        "the shipped tool changed"
    );
    std::fs::write(
        &tool,
        text.replace("url: host/payments\n", &format!("url: {address}\n")),
    )
    .unwrap();
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
fn a_blank_every_action_fills_loads_clean() {
    let tree = with_address("filled", "host/payments/{order-number}");
    let (ok, said) = check(&tree);
    assert!(ok, "{said}");
    assert!(!said.contains("a-blank-in-the-address"), "{said}");
}

#[test]
fn a_blank_no_argument_fills_is_refused_where_the_address_is_written() {
    let tree = with_address("unfilled", "host/payments/{order-id}");
    let (ok, said) = check(&tree);
    assert!(!ok, "{said}");
    assert!(
        said.contains("loader/a-blank-in-the-address-nothing-fills"),
        "{said}"
    );
    assert!(said.contains("`{order-id}`"), "{said}");
    assert!(said.contains("payments.yaml"), "{said}");
}
