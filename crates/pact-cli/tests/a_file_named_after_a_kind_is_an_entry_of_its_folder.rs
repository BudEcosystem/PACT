//! A file named after a kind, directly in a collection's folder, is an entry of
//! that collection.
//!
//! `agent.yaml`, `catalog.yaml`, `tool.yaml` and the other kind names describe
//! the folder they sit in: `agents/desk/agent.yaml` is the agent `desk`, and
//! `models/catalog.yaml` is the workspace's `models:`. Read the same way,
//! `tools/catalog.yaml` described `tools/` itself, so its `description:`,
//! `connect:` and `actions:` became three tools and the tool `catalog` did not
//! exist (found by a corpus scenario that named its product catalogue
//! `tools/catalog.yaml` and had to rename it).

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact(args: &[&str], root: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .arg(root)
        .output()
        .expect("runs");
    (
        out.status.success(),
        format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    )
}

fn written(name: &str, files: &[(&str, &str)]) -> PathBuf {
    let root = std::env::temp_dir().join(format!("pact-kind-file-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    for (rel, text) in files {
        let p = root.join(rel);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    }
    root
}

const WORKSPACE: &str = "name: shop\nallow-egress: []\n";
const AGENT: &str = "description: Answers product questions.\n\
                     instructions: Look the product up before you answer.\n\
                     uses: [catalog]\n";
const CATALOG: &str = "description: The products this shop sells.\n\
                       connect: products-server\n\
                       actions:\n  \
                         find:\n    \
                           description: One product by its code.\n    \
                           reads-only: yes\n    \
                           takes:\n      \
                             code: text\n";
const SERVER: &str = "resource-kind: mcp-server\nendpoint: host/products\n";

/// Mutation: drop `kindfiles::read_as_entries` from `validate`, and the tree is
/// refused — `uses:` names `catalog`, which is not a tool, and `description`,
/// `connect` and `actions` are.
#[test]
fn tools_catalog_yaml_is_the_tool_called_catalog() {
    let root = written(
        "tool",
        &[
            ("workspace.yaml", WORKSPACE),
            ("agents/desk/agent.yaml", AGENT),
            ("tools/catalog.yaml", CATALOG),
            ("resources/products-server.yaml", SERVER),
        ],
    );
    let (ok, text) = pact(&["check", "--deny-warnings"], &root);
    assert!(
        ok,
        "tools/catalog.yaml must be read as the tool `catalog`:\n{text}"
    );
    let (ok, shown) = pact(&["show"], &root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(ok, "{shown}");
    let doc: serde_json::Value = serde_json::from_str(&shown).unwrap();
    let tools = doc["tools"].as_object().unwrap();
    assert_eq!(tools.keys().collect::<Vec<_>>(), ["catalog"], "{shown}");
    assert_eq!(tools["catalog"]["connect"], "products-server");
    assert!(tools["catalog"]["actions"]["find"].is_object(), "{shown}");
}

/// The same file in a bundle's `contributes/tools/` is the bundle's tool
/// `catalog`, not three.
#[test]
fn a_bundle_contributing_tools_catalog_yaml_contributes_one_tool() {
    let root = written(
        "bundle",
        &[
            ("workspace.yaml", WORKSPACE),
            (
                "agents/desk/agent.yaml",
                &AGENT.replace("[catalog]", "[orders]"),
            ),
            (
                "tools/orders.yaml",
                &CATALOG.replace("products-server", "orders-server"),
            ),
            ("resources/orders-server.yaml", SERVER),
            (
                "bundles/shop-kit/shop-kit.yaml",
                "description: The shop's catalogue.\nversion: \"0.1\"\nfrom: bundles/shop-kit\nbrings: [tools]\n",
            ),
            ("bundles/shop-kit/contributes/tools/catalog.yaml", CATALOG),
        ],
    );
    let (ok, shown) = pact(&["show"], &root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(ok, "{shown}");
    let doc: serde_json::Value = serde_json::from_str(&shown).unwrap();
    let brought = doc["bundles"]["shop-kit"]["contributes"]["tools"]
        .as_object()
        .unwrap();
    assert_eq!(brought.keys().collect::<Vec<_>>(), ["catalog"], "{shown}");
}

/// What the kind names are for is unchanged: a folder's own file still
/// describes it: `tools/orders/tool.yaml` is the tool `orders`.
#[test]
fn a_kind_named_file_still_describes_the_entry_folder_it_sits_in() {
    let root = written(
        "unchanged",
        &[
            ("workspace.yaml", WORKSPACE),
            (
                "agents/desk/agent.yaml",
                &AGENT.replace("[catalog]", "[orders]"),
            ),
            (
                "tools/orders/tool.yaml",
                &CATALOG.replace("products-server", "orders-server"),
            ),
            ("resources/orders-server.yaml", SERVER),
        ],
    );
    let (ok, shown) = pact(&["show"], &root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(ok, "{shown}");
    let doc: serde_json::Value = serde_json::from_str(&shown).unwrap();
    assert_eq!(
        doc["tools"].as_object().unwrap().keys().collect::<Vec<_>>(),
        ["orders"]
    );
    assert!(doc["agents"]["desk"].is_object());
}
