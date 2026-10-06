//! **P0 — the net that goes up before the wire.**
//!
//! `docs/41-IMPLEMENTATION-PLAN-PROGRAMS.md` adds nine phases of new capability
//! to a format whose whole claim is that what you were handed is what runs. The
//! risk that carries is not that a new field breaks — a new field has its own
//! tests — it is that a tree nobody touched starts meaning something else.
//! Every phase is additive by intent; this file is what makes "by intent" a
//! measurement.
//!
//! Two properties, one per test:
//!
//!   1. **Every shipped tree loads to the same document, byte for byte.** The
//!      golden is `pact show`'s own output, which is the door every adapter in
//!      this repository reads through (`50-NOT-COPIED.md` R54), so a change
//!      invisible here is invisible to all seven targets.
//!   2. **The specification only ever grows.** Every field the schema had keeps
//!      its type, its `surface:`, its `tier:` and its `required:`. Additions are
//!      free and are not blessed; a rename, a retype, a re-tier or a deletion is
//!      a failure that names the field.
//!
//! The second one is the one that matters most, and it is worth saying why it is
//! a subset test rather than an equality test. `surface:` is what the governance
//! zone and the blast-radius class are looked up in (§8.2, §8.3), and `tier:` is
//! what makes D14's no-code badge checkable. A phase that quietly re-annotated
//! `policy` from `S-EXEC` to `S-GEN` would move a money-moving field out of
//! GOVERNED and into the zone a learning cycle may rewrite unattended — the
//! exact exploit `spec/schema.yaml`'s own header records for the discovered-spec
//! path (R40). Holding the old annotations rather than the old *list* means the
//! plan can add all it likes and can never soften what is already there.
//!
//! Blessing: `PACT_BLESS=1 cargo test -p pact-cli --test nothing_that_already_works_changes`.
//! Re-blessing is a deliberate act and shows up in review as a changed golden.

use std::collections::BTreeMap;
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()
}

fn golden_dir() -> std::path::PathBuf {
    repo().join("tests/golden")
}

fn blessing() -> bool {
    std::env::var("PACT_BLESS").is_ok_and(|v| v == "1")
}

/// Every workspace this repository ships, found rather than listed.
///
/// Same question `pact discover` asks and the same one the `--deny-warnings`
/// census asks: a tree is what holds a `workspace.yaml`. A list would be a scope
/// somebody has to remember to extend, and the phase that forgets is the phase
/// that regresses something unwatched.
fn shipped_trees() -> Vec<std::path::PathBuf> {
    let mut out = Vec::new();
    let mut stack = vec![repo().join("examples")];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else { continue };
        for e in entries.flatten() {
            let p = e.path();
            if !p.is_dir() || p.file_name().unwrap().to_string_lossy().starts_with('.') {
                continue;
            }
            if p.join("workspace.yaml").exists() {
                out.push(p);
            } else {
                stack.push(p);
            }
        }
    }
    out.sort();
    out
}

fn slug(tree: &std::path::Path) -> String {
    tree.strip_prefix(repo().join("examples"))
        .unwrap_or(tree)
        .to_string_lossy()
        .replace(['/', '\\'], "-")
}

/// The document every adapter is handed, pinned per shipped tree.
///
/// `show` and not `check`: a check that still exits 0 says nothing about whether
/// the document underneath it changed shape, and the document is what runs.
#[test]
fn every_shipped_tree_loads_to_the_same_document() {
    let trees = shipped_trees();
    assert!(trees.len() >= 9, "only {} shipped trees found — the census shrank", trees.len());
    std::fs::create_dir_all(golden_dir().join("show")).unwrap();

    let mut drifted = Vec::new();
    for tree in &trees {
        let out = pact().args(["show", tree.to_str().unwrap()]).output().expect("runs");
        assert!(
            out.status.success(),
            "{} does not even load:\n{}",
            tree.display(),
            String::from_utf8_lossy(&out.stderr)
        );
        let now = String::from_utf8_lossy(&out.stdout).into_owned();
        let path = golden_dir().join("show").join(format!("{}.json", slug(tree)));

        if blessing() || !path.exists() {
            std::fs::write(&path, &now).unwrap();
            continue;
        }
        let was = std::fs::read_to_string(&path).unwrap();
        if was != now {
            drifted.push(format!(
                "{}\n  golden {} bytes, now {} bytes\n  first difference at byte {}",
                tree.display(),
                was.len(),
                now.len(),
                was.bytes().zip(now.bytes()).position(|(a, b)| a != b).unwrap_or(was.len().min(now.len()))
            ));
        }
    }
    assert!(
        drifted.is_empty(),
        "{} shipped tree(s) now load to a different document.\n\n{}\n\nIf this change is \
         intended, look at it first: this is the file every adapter reads. Re-bless with \
         PACT_BLESS=1 and let the diff be reviewed.",
        drifted.len(),
        drifted.join("\n\n")
    );
}

/// The surfaces whose fields DECIDE something at run time: what is governed, and
/// what is enforced. A field on one of these is held from the day it is added.
const GOVERNS: [&str; 2] = ["S-GOV", "S-EXEC"];

/// `<group>.<field>` → the four attributes that decide what it MEANS.
///
/// Read out of the YAML rather than off `Schema`, because `surface:` and
/// `tier:` never reach the `Field` struct — `governance_is_complete` reads them
/// the same way, from the same document, for the same reason.
fn field_inventory() -> BTreeMap<String, String> {
    let text = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let doc = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml")).unwrap();
    let mut out = BTreeMap::new();
    let Some(groups) = doc.get("groups").and_then(pact_doc::Node::as_map) else { return out };
    for (kind, entry) in groups {
        let Some(fields) = entry.node.get("fields").and_then(pact_doc::Node::as_map) else {
            continue;
        };
        for (name, f) in fields {
            let at = |k: &str| {
                f.node.get(k).and_then(pact_doc::Node::as_str).unwrap_or("-").to_owned()
            };
            let required = match f.node.get("required").and_then(pact_doc::Node::as_str) {
                Some("yes" | "true") => "required",
                _ => "optional",
            };
            out.insert(
                format!("{kind}.{name}"),
                format!("{} | {} | {} | {}", at("type"), at("surface"), at("tier"), required),
            );
        }
    }
    out
}

/// The specification grows; it never softens.
///
/// Most additions need no blessing — that is the whole point of a subset test,
/// and it is what lets nine phases add fields without a golden churning under
/// them. What fails is a field that USED to be there and now is not, or one
/// whose type, governance surface, tier or requiredness moved.
///
/// One kind of addition does need it: a field on a surface that DECIDES
/// something (`S-GOV`, `S-EXEC`). A subset test holds only what is in the file,
/// so a governance field added and never blessed was held to nothing: moving
/// `agent.checked-by` from `S-GOV` to `S-GEN`, which takes it out of the zone a
/// person must approve changes in, passed every test. Such a field is in the
/// file from the day it exists, or this fails and says to put it there.
#[test]
fn the_specification_only_ever_grows() {
    let now = field_inventory();
    assert!(now.len() > 250, "only {} fields parsed — the reader broke, not the schema", now.len());
    let path = golden_dir().join("schema-fields.txt");
    std::fs::create_dir_all(golden_dir()).unwrap();

    if blessing() || !path.exists() {
        let text: String = now.iter().map(|(k, v)| format!("{k}\t{v}\n")).collect();
        std::fs::write(&path, text).unwrap();
        return;
    }

    let was = std::fs::read_to_string(&path).unwrap();
    let mut gone = Vec::new();
    let mut moved = Vec::new();
    for line in was.lines().filter(|l| !l.trim().is_empty()) {
        let (key, attrs) = line.split_once('\t').expect("golden is <key>\\t<attrs>");
        match now.get(key) {
            None => gone.push(key.to_owned()),
            Some(current) if current != attrs => {
                moved.push(format!("{key}\n    was: {attrs}\n    now: {current}"));
            }
            Some(_) => {}
        }
    }
    let held: std::collections::BTreeSet<&str> =
        was.lines().filter_map(|l| l.split_once('\t')).map(|(key, _)| key).collect();
    let unheld: Vec<String> = now
        .iter()
        .filter(|(key, attrs)| {
            !held.contains(key.as_str())
                && GOVERNS.iter().any(|surface| attrs.contains(&format!("| {surface} |")))
        })
        .map(|(key, attrs)| format!("{key}\t{attrs}"))
        .collect();
    assert!(
        unheld.is_empty(),
        "{} field(s) on a surface that decides something are in the specification and \
         not in {}, so nothing holds their surface where it is:\n  {}\n\n\
         Look at each surface and tier, then re-bless with PACT_BLESS=1.",
        unheld.len(),
        path.display(),
        unheld.join("\n  ")
    );
    assert!(
        gone.is_empty() && moved.is_empty(),
        "the specification did not only grow.\n\n\
         {} field(s) gone: {}\n\n\
         {} field(s) whose meaning moved:\n{}\n\n\
         Adding fields is free and needs no blessing. Removing one, retyping it, or \
         changing its `surface:` or `tier:` changes what an existing tree means — \
         `surface:` decides the governance zone and the blast-radius class, and `tier:` \
         decides the no-code badge.",
        gone.len(),
        if gone.is_empty() { "-".into() } else { gone.join(", ") },
        moved.len(),
        if moved.is_empty() { "  -".into() } else { moved.join("\n") }
    );
}

/// Reading a tree stays an act of reading, whatever the tree holds.
///
/// The purity rule (R5, FR-1.5.6) is the one every phase of the programs plan
/// leans on: a workspace may CARRY a program, and checking it must still open
/// nothing and start nothing. Today the strongest available statement of that
/// from outside the process is that a tree carrying a body which would be
/// catastrophic to execute is checked with no effect — so the body is a script
/// that would write a file, and the assertion is that the file is not there
/// afterwards.
///
/// It is written now, at P0, rather than with the `program` kind at P6,
/// deliberately: a purity test that arrives with the feature it guards has
/// nothing to say about the state before it.
#[test]
fn checking_a_tree_that_carries_a_body_runs_nothing() {
    let dst = std::env::temp_dir().join(format!("pact-purity-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&repo().join("examples/refund-desk"), &dst);

    // A payload folder is where a body lives today (`skills/<n>/scripts/`) and
    // where one will live under `programs/` tomorrow. The walker records its
    // name, its type and its size, and never its contents.
    let canary = dst.join("canary-was-executed");
    let scripts = dst.join("skills/refund-policy/scripts");
    std::fs::create_dir_all(&scripts).unwrap();
    std::fs::write(
        scripts.join("hostile.py"),
        format!("open({:?}, 'w').write('executed')\n", canary.to_str().unwrap()),
    )
    .unwrap();
    std::fs::write(
        scripts.join("hostile.sh"),
        format!("#!/bin/sh\necho executed > {:?}\n", canary.to_str().unwrap()),
    )
    .unwrap();

    for verb in ["check", "show", "waits", "discover"] {
        let out = pact().args([verb, dst.to_str().unwrap()]).output().expect("runs");
        assert!(
            !canary.exists(),
            "`pact {verb}` executed a body it was only ever supposed to record.\n{}",
            String::from_utf8_lossy(&out.stdout)
        );
    }
    let _ = std::fs::remove_dir_all(&dst);
}

fn copy_dir(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}
