//! `allow-egress:` governs the whole boundary, not just the models (B9).
//!
//! The field's own help promises *"which parts of this system are allowed to
//! talk to something outside this box. Empty means nothing is."* Its six choices
//! were all MODEL roles, because a model was the only reacher anything checked.
//!
//! Measured, under `allow-egress: []`:
//!
//! ```text
//! tool.url: https://vendor.example.com/upload + method: post + an upload action
//!   → OK — loaded cleanly (19 settings)
//! ```
//!
//! That door needs no resource file at all — one tool document, and the
//! workspace's whole stated boundary is silent. It is the door an attacker
//! writes.
//!
//! One setting and not two: a sibling hostname allow-list would be R61 (*"two
//! settings for what must never leave a workspace"*) and R20 (a name only the
//! host can resolve) at the same time. So `tools` is a seventh PART of the
//! system on the field that already promises the boundary.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn spec() -> pact_schema::Schema {
    const SPEC: &str = include_str!("../../../spec/schema.yaml");
    let mut d = pact_diag::Diagnostics::new();
    let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
    assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
    s
}

/// A one-tool workspace whose egress line and address are as given.
fn reaching(name: &str, egress: &str, address: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-egress-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    std::fs::create_dir_all(dst.join("tools")).unwrap();
    std::fs::write(
        dst.join("workspace.yaml"),
        format!("name: Probe\ndescription: A probe workspace.\nallow-egress: {egress}\n"),
    )
    .unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        "name: Desk\ndescription: Uploads things.\ninstructions: Upload it.\nuses: [vendor]\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("tools/vendor.yaml"),
        format!(
            "description: A vendor upload endpoint.\nurl: {address}\nmethod: post\n\
             actions:\n  upload:\n    description: Sends the file.\n"
        ),
    )
    .unwrap();
    dst
}

fn check(root: &std::path::Path) -> String {
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr))
}

#[test]
fn a_tool_that_reaches_the_internet_is_refused_when_nothing_may_leave() {
    let root = reaching("closed", "[]", "https://vendor.example.com/upload");
    let text = check(&root);
    assert!(
        text.contains("loader/reaches-outside-the-box"),
        "the door that needs no resource file must be refused:\n{text}"
    );
    assert!(text.contains("vendor.example.com"), "the message names the address:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn an_address_the_host_resolves_is_not_something_leaving_the_box() {
    // `host/payments-mcp` in the worked example has no scheme. Refusing it would
    // make `allow-egress: []` mean "no tools at all" rather than "nothing
    // leaves", and the flagship would stop loading.
    let root = reaching("hostrel", "[]", "host/vendor-upload");
    let out = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    assert!(
        out.status.success(),
        "a name the runtime looks up is not egress:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_it_offers_leaves_a_tree_that_checks_clean() {
    // R24, both halves of the fix.
    let root = reaching("typed", "[]", "https://vendor.example.com/upload");
    let told = check(&root);
    assert!(told.contains("Add `tools` to `allow-egress:`"), "{told}");

    let allowed = reaching("allowed", "[tools]", "https://vendor.example.com/upload");
    let a = pact().args(["check", allowed.to_str().unwrap()]).output().expect("runs");
    assert!(a.status.success(), "{}", String::from_utf8_lossy(&a.stdout));

    let rewritten = reaching("rewritten", "[]", "host/vendor-upload");
    let b = pact().args(["check", rewritten.to_str().unwrap()]).output().expect("runs");
    assert!(b.status.success(), "{}", String::from_utf8_lossy(&b.stdout));

    for p in [root, allowed, rewritten] {
        let _ = std::fs::remove_dir_all(&p);
    }
}

#[test]
fn a_workspace_that_drew_no_boundary_is_not_given_one() {
    // No `allow-egress:` line at all means this author has not decided.
    // Inventing a boundary would refuse trees that never opted in.
    let dst = std::env::temp_dir().join(format!("pact-egress-none-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    std::fs::create_dir_all(dst.join("tools")).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Probe\ndescription: A probe.\n").unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        "name: Desk\ndescription: Uploads.\ninstructions: Upload it.\nuses: [vendor]\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("tools/vendor.yaml"),
        "description: A vendor endpoint.\nurl: https://vendor.example.com/upload\n\
         method: post\nactions:\n  upload:\n    description: Sends it.\n",
    )
    .unwrap();
    let out = pact().args(["check", dst.to_str().unwrap()]).output().expect("runs");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stdout));
    let _ = std::fs::remove_dir_all(&dst);
}

#[test]
fn which_fields_carry_an_outbound_address_is_data_and_not_a_list_in_rust() {
    // The regression guard the design owes. A hand-written set of field names
    // in the checker is B15 in a new file — four such tables shipped, and six
    // of their names were wrong. The schema says which fields reach outside,
    // and this asserts the set is non-empty and covers the three doors.
    let schema = spec();
    let mut marked: Vec<String> = Vec::new();
    for g in schema.groups() {
        for f in &g.fields {
            if f.reaches_outside {
                marked.push(format!("{}.{}", g.name, f.name));
            }
        }
    }
    marked.sort();
    assert_eq!(
        marked,
        vec!["resource.endpoint", "served-by.endpoint", "tool.url"],
        "the set of outbound-address fields has changed — if that is intended, the \
         change belongs in `spec/schema.yaml` and this line moves with it"
    );
}

#[test]
fn the_shipped_example_does_not_move() {
    // `examples/refund-desk` writes `host/payments-mcp`, which has no scheme.
    let path = format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"));
    let out = pact().args(["check", &path]).output().expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(out.status.success(), "{text}");
    assert!(!text.contains("loader/reaches-outside-the-box"), "{text}");
}
