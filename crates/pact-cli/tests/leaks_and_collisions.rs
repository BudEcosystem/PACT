//! `docs/98` WP-13: the lethal trifecta refused, two branches writing one place
//! pointed out, and a circuit breaker's two lines.

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

fn tree(src: &str, name: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join(src);
    let dst = std::env::temp_dir().join(format!("pact-leaks-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    dst
}

fn write(t: &Path, file: &str, text: &str) {
    let p = t.join(file);
    std::fs::create_dir_all(p.parent().unwrap()).unwrap();
    std::fs::write(p, text).unwrap();
}

fn edit(t: &Path, file: &str, from: &str, to: &str) {
    let p = t.join(file);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains(from),
        "fixture drifted: {file} has no {from:?}"
    );
    std::fs::write(p, text.replacen(from, to, 1)).unwrap();
}

fn check(t: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(t)
        .output()
        .unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

/// A small desk that reads customer records, reads the web, and sends email.
fn trifecta(name: &str, mail_needs_a_person: bool) -> PathBuf {
    let t = tree("examples/patterns/pipeline", name);
    write(
        &t,
        "resources/desk-server.yaml",
        "resource-kind: mcp-server\nendpoint: host/desk\ndescription: Where the desk's systems are reached.\n",
    );
    write(
        &t,
        "tools/crm.yaml",
        "description: Customer records.\nconnect: desk-server\ncarries: [private-data]\nactions:\n  look-up:\n    description: Look a customer up.\n    reads-only: yes\n    takes:\n      customer: text\n",
    );
    write(
        &t,
        "tools/web.yaml",
        "description: The open web.\nconnect: desk-server\ncarries: [untrusted-content]\nactions:\n  fetch:\n    description: Fetch a page.\n    reads-only: yes\n    takes:\n      url: text\n",
    );
    let person = if mail_needs_a_person {
        "    needs-a-person: yes\n"
    } else {
        ""
    };
    write(
        &t,
        "tools/mail.yaml",
        &format!(
            "description: Outgoing mail.\nconnect: desk-server\ncarries: [a-way-out]\nactions:\n  send:\n    description: Send an email.\n{person}    takes:\n      to: text\n      body: text\n"
        ),
    );
    write(
        &t,
        "agents/desk/agent.yaml",
        "description: Answers customers.\ninstructions: Answer the customer.\nuses: [crm, web, mail]\n",
    );
    t
}

#[test]
fn private_data_a_strangers_words_and_a_way_out_with_nobody_at_the_door_is_refused() {
    let (ok, said) = check(&trifecta("open", false));
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/three-things-that-make-a-leak"),
        "{said}"
    );
    assert!(said.contains("`mail/send`"), "{said}");
}

#[test]
fn a_person_at_the_way_out_closes_it() {
    let (_, said) = check(&trifecta("guarded", true));
    assert!(!said.contains("three-things-that-make-a-leak"), "{said}");
}

#[test]
fn two_of_the_three_is_not_a_leak() {
    let t = trifecta("two", false);
    edit(
        &t,
        "agents/desk/agent.yaml",
        "uses: [crm, web, mail]",
        "uses: [crm, mail]",
    );
    let (_, said) = check(&t);
    assert!(!said.contains("three-things-that-make-a-leak"), "{said}");
}

#[test]
fn two_branches_writing_one_place_are_pointed_out() {
    let t = tree("tests/trees/a-workflow-of-every-shape", "collide");
    let ledger = t.join("tools/ledger.yaml");
    let mut text = std::fs::read_to_string(&ledger).unwrap();
    text.push_str("  stamp:\n    description: Stamp.\n    writes: [the ledger]\n    undone-by: ledger/unpost\n    takes:\n      invoice: text\n");
    std::fs::write(&ledger, text).unwrap();
    edit(
        &t,
        "workflows/invoices.yaml",
        "      left:\n        does: call\n        call: ledger/read-invoice\n",
        "      left:\n        does: call\n        call: ledger/stamp\n",
    );
    edit(
        &t,
        "workflows/invoices.yaml",
        "      right:\n        does: call\n        call: ledger/read-invoice\n",
        "      right:\n        does: call\n        call: ledger/stamp\n",
    );
    let (_, said) = check(&t);
    assert!(
        said.contains("rule: loader/two-branches-write-the-same-place"),
        "{said}"
    );
    assert!(said.contains("'the ledger'"), "{said}");
}

#[test]
fn a_breaker_needs_both_its_lines() {
    let t = trifecta("breaker", true);
    edit(
        &t,
        "tools/web.yaml",
        "carries: [untrusted-content]\n",
        "carries: [untrusted-content]\nrests-after: 3\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(said.contains("schema/missing-companion"), "{said}");
    edit(
        &t,
        "tools/web.yaml",
        "rests-after: 3\n",
        "rests-after: 3\nrests-for: 5m\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}
