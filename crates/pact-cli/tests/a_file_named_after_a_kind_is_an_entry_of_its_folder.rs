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

/// The names of `collection` in the tree at `root`, as `pact show` reads it.
fn names_in(collection: &str, root: &Path) -> Vec<String> {
    let (ok, text) = pact(&["check", "--deny-warnings"], root);
    assert!(ok, "the tree must check:\n{text}");
    let (ok, shown) = pact(&["show"], root);
    assert!(ok, "{shown}");
    let doc: serde_json::Value = serde_json::from_str(&shown).unwrap();
    doc[collection]
        .as_object()
        .unwrap_or_else(|| panic!("no {collection} in {shown}"))
        .keys()
        .cloned()
        .collect()
}

const PLAIN_AGENT: &str = "description: Answers product questions.\n\
                           instructions: Look the product up before you answer.\n";

const TWO_WATCHES: &str = "first:\n  \
                             description: Records every tool call.\n  \
                             when: step.tool.completed\n  \
                             writes-to: first.jsonl\n\
                           second:\n  \
                             description: Records every tool call again.\n  \
                             when: step.tool.completed\n  \
                             writes-to: second.jsonl\n";

/// A collection folder's own self file (FR-1.1.3) still holds several entries.
/// `watch/watch.yaml` is named after its folder (and after the kind the
/// collection holds), so it is the folder's settings: two watches, not one
/// watch called `watch`.
///
/// Mutation: drop the `<dirname>.*` and own-kind exemptions in
/// `kindfiles::give_back_its_name`, and the tree is refused ('first' is not
/// something a watch can have).
#[test]
fn watch_watch_yaml_is_the_folders_own_file_holding_two_watches() {
    let root = written(
        "watch",
        &[
            ("workspace.yaml", WORKSPACE),
            ("agents/desk/agent.yaml", PLAIN_AGENT),
            ("watch/watch.yaml", TWO_WATCHES),
        ],
    );
    let names = names_in("watch", &root);
    let _ = std::fs::remove_dir_all(&root);
    assert_eq!(names, ["first", "second"]);
}

/// `tools/tool.yaml` is named after the kind `tools/` holds, so it is the
/// folder's own file too: two tools, not one tool called `tool`.
///
/// Mutation: drop the own-kind exemption in `kindfiles::give_back_its_name`
/// and the tree is refused.
#[test]
fn tools_tool_yaml_is_the_folders_own_file_holding_two_tools() {
    let tool = |name: &str| {
        format!(
            "{name}:\n  description: The {name} this shop has.\n  connect: products-server\n  \
             actions:\n    find:\n      description: One by its code.\n      reads-only: yes\n      \
             takes:\n        code: text\n"
        )
    };
    let root = written(
        "own-kind",
        &[
            ("workspace.yaml", WORKSPACE),
            (
                "agents/desk/agent.yaml",
                &AGENT.replace("[catalog]", "[products, orders]"),
            ),
            (
                "tools/tool.yaml",
                &format!("{}{}", tool("products"), tool("orders")),
            ),
            ("resources/products-server.yaml", SERVER),
        ],
    );
    let names = names_in("tools", &root);
    let _ = std::fs::remove_dir_all(&root);
    assert_eq!(names, ["products", "orders"]);
}
