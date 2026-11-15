//! Law 3 of `docs/97-PRIMITIVES.md` (`docs/98` WP-4): a write that cannot be
//! undone, where a call can happen more than once, carries a claim — and the
//! claim's key is the same every time the same thing is attempted.
//!
//! Driven against `tests/trees/a-workflow-of-every-shape`, given one more ledger
//! action, `stamp`, that writes, cannot be undone, and has no key.

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

const STAMP: &str =
    "  stamp:\n    description: Stamp an invoice as seen.\n    takes:\n      invoice: text\n";

fn tree(name: &str) -> PathBuf {
    let src =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/a-workflow-of-every-shape");
    let dst = std::env::temp_dir().join(format!("pact-once-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    let ledger = dst.join("tools/ledger.yaml");
    let mut text = std::fs::read_to_string(&ledger).unwrap();
    text.push_str(STAMP);
    std::fs::write(&ledger, text).unwrap();
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

const FLOW: &str = "workflows/invoices.yaml";

/// The `repeat`'s one stage, calling `target` with `invoice` bound from `from`.
fn in_the_repeat(tree: &Path, target: &str, from: &str) {
    edit(
        tree,
        FLOW,
        "        call: recheck\n        bind:\n          invoice: input.attachments\n        waits-for-result: no\n        version: latest\n",
        &format!("        call: {target}\n        bind:\n          invoice: {from}\n"),
    );
}

#[test]
fn the_tree_with_one_more_action_still_loads() {
    let (ok, said) = check(&tree("as-given"));
    assert!(ok, "{said}");
}

#[test]
fn a_write_with_no_way_back_in_a_repeat_needs_a_claim() {
    let t = tree("repeat");
    in_the_repeat(&t, "ledger/stamp", "input.attachments");
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/repeated-with-no-claim"),
        "{said}"
    );
    assert!(said.contains("every round of 'check-twice'"), "{said}");
}

#[test]
fn a_key_on_the_action_is_the_claim() {
    let t = tree("keyed");
    // `stamp` is the last action in the file, so its key is the last line.
    let ledger = t.join("tools/ledger.yaml");
    let text = std::fs::read_to_string(&ledger).unwrap();
    std::fs::write(&ledger, format!("{text}    same-request-key: invoice\n")).unwrap();
    in_the_repeat(&t, "ledger/stamp", "input.attachments");
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
}

#[test]
fn an_undo_on_the_stage_is_a_way_back() {
    let t = tree("undo");
    in_the_repeat(&t, "ledger/stamp", "input.attachments");
    edit(
        &t,
        FLOW,
        "        call: ledger/stamp\n",
        "        call: ledger/stamp\n        undone-by: ledger/unpost\n",
    );
    let (_, said) = check(&t);
    assert!(!said.contains("loader/repeated-with-no-claim"), "{said}");
}

#[test]
fn once_is_fine_and_a_retry_is_not() {
    let t = tree("once");
    edit(
        &t,
        FLOW,
        "        call: ledger/read-invoice\n        bind:\n          invoice: item.content-hash\n",
        "        call: ledger/stamp\n        bind:\n          invoice: item.content-hash\n",
    );
    let (_, said) = check(&t);
    assert!(
        !said.contains("loader/repeated-with-no-claim"),
        "an each's items are different things: {said}"
    );

    let t = tree("retry");
    edit(
        &t,
        FLOW,
        "        call: ledger/read-invoice\n        bind:\n          invoice: item.content-hash\n",
        "        call: ledger/stamp\n        at-most: 3\n        bind:\n          invoice: item.content-hash\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(said.contains("loader/repeated-with-no-claim"), "{said}");
    assert!(said.contains("`at-most:` above 1"), "{said}");
}

#[test]
fn one_branch_of_a_together_is_one_call() {
    // `left` writes, `right` reads: two different calls, each made once.
    let t = tree("together-once");
    edit(
        &t,
        FLOW,
        "      left:\n        does: call\n        call: ledger/read-invoice\n",
        "      left:\n        does: call\n        call: ledger/stamp\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
    assert!(!said.contains("loader/repeated-with-no-claim"), "{said}");
}

#[test]
fn two_branches_calling_the_same_write_do_it_twice() {
    let t = tree("together-twice");
    edit(
        &t,
        FLOW,
        "      left:\n        does: call\n        call: ledger/read-invoice\n",
        "      left:\n        does: call\n        call: ledger/stamp\n",
    );
    edit(
        &t,
        FLOW,
        "      right:\n        does: call\n        call: ledger/read-invoice\n",
        "      right:\n        does: call\n        call: ledger/stamp\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(said.contains("loader/repeated-with-no-claim"), "{said}");
    assert!(
        said.contains("more than one branch of 'both' calls it"),
        "{said}"
    );
}

#[test]
fn a_together_inside_a_repeat_still_runs_every_round() {
    // The repeat's one stage becomes a together with one writing branch: no
    // branch repeats another, but the repeat runs the together again.
    let t = tree("together-in-repeat");
    edit(
        &t,
        FLOW,
        "      recheck:\n        does: call\n        call: recheck\n        bind:\n          invoice: input.attachments\n        waits-for-result: no\n        version: latest\n",
        "      recheck:\n        does: together\n        steps:\n          once:\n            does: call\n            call: ledger/stamp\n            bind:\n              invoice: input.attachments\n          look:\n            does: call\n            call: ledger/read-invoice\n            bind:\n              invoice: input.attachments\n",
    );
    let (ok, said) = check(&t);
    assert!(!ok, "{said}");
    assert!(said.contains("loader/repeated-with-no-claim"), "{said}");
    assert!(said.contains("every round of 'check-twice'"), "{said}");
}

#[test]
fn a_key_bound_from_the_round_itself_never_matches() {
    let t = tree("moving-key");
    // `ledger/post` is keyed on `invoice`; bound from the repeat's own stage,
    // it is a new key every round.
    edit(
        &t,
        FLOW,
        "        call: recheck\n        bind:\n          invoice: input.attachments\n        waits-for-result: no\n        version: latest\n",
        "        call: ledger/read-invoice\n        bind:\n          invoice: input.attachments\n        then:\n          answered: post\n      post:\n        does: call\n        call: ledger/post\n        bind:\n          invoice: steps.recheck.vendor\n",
    );
    let (ok, said) = check(&t);
    // A warning: the author wrote a claim; whether rounds aim at one thing is
    // theirs to say.
    assert!(ok, "{said}");
    assert!(
        said.contains("rule: loader/a-key-that-changes-every-attempt"),
        "{said}"
    );
    assert!(said.contains("warning:"), "{said}");
}

#[test]
fn a_round_may_keep_what_it_learned() {
    // `bud/remember` in a repeat is how a round leaves its memory for the next.
    let t = tree("remember");
    std::fs::write(
        t.join("tools/bud.yaml"),
        "description: The workspace's memory.\nactions:\n  remember:\n    description: Keep a value.\n    takes:\n      memory: text\n      value: text\n",
    )
    .unwrap();
    in_the_repeat(&t, "bud/remember", "input.attachments");
    let (_, said) = check(&t);
    assert!(!said.contains("loader/repeated-with-no-claim"), "{said}");
}

#[test]
fn a_claim_across_runs_needs_somewhere_to_be_kept() {
    let t = tree("across");
    edit(
        &t,
        "tools/ledger.yaml",
        "    same-request-key: invoice\n",
        "    same-request-key: invoice\n    same-request-key-across: the-team\n",
    );
    // Unwritten, `durability:` assumes nothing: no warning.
    let (_, said) = check(&t);
    assert!(!said.contains("a-claim-wider-than-what-keeps-it"), "{said}");
    edit(
        &t,
        "workspace.yaml",
        "allow-egress: []\n",
        "allow-egress: []\ndurability: none\n",
    );
    let (_, said) = check(&t);
    assert!(
        said.contains("rule: loader/a-claim-wider-than-what-keeps-it"),
        "{said}"
    );

    edit(
        &t,
        "workspace.yaml",
        "durability: none\n",
        "durability: checkpoint\n",
    );
    let (_, said) = check(&t);
    assert!(!said.contains("a-claim-wider-than-what-keeps-it"), "{said}");
}

#[test]
fn the_call_is_a_claim_for_a_write_with_no_business_key() {
    // A retried write the business gives no key: its place in the run is the claim.
    let t = tree("the-call");
    let ledger = t.join("tools/ledger.yaml");
    let text = std::fs::read_to_string(&ledger).unwrap();
    std::fs::write(&ledger, format!("{text}    same-request-key: the-call\n")).unwrap();
    edit(
        &t,
        FLOW,
        "        call: ledger/read-invoice\n        bind:\n          invoice: item.content-hash\n",
        "        call: ledger/stamp\n        at-most: 3\n        bind:\n          invoice: item.content-hash\n",
    );
    let (ok, said) = check(&t);
    assert!(ok, "{said}");
    assert!(!said.contains("loader/repeated-with-no-claim"), "{said}");
    assert!(!said.contains("loader/no-such-request-key"), "{said}");
}
