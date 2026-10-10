//! DUR-2 (02W §7.2): `pact discover` gives every workflow two digests. Its
//! `doc-digest` (what a waiting run is pinned to) moves when the workflow, a
//! workflow it reaches or anything else of the workspace its run relies on
//! changes, and stays put when only a workflow it never reaches changes; its
//! `contract-digest` (what callers rely on) moves only with `accepts:`,
//! `answers-with:`, `published-as:` and its ports' keys and overlap choices.
//! Over #16's tree (`tests/trees/workflows-16-trial-booking/`), where
//! `trial-booking` calls `parent-contact`, which calls nothing.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

const TREE: &str = "tests/trees/workflows-16-trial-booking";
const BOOKING: &str = "workflows/trial-booking.yaml";
const CONTACT: &str = "workflows/parent-contact.yaml";
const BOOKED: &str = "ports/trial-booked.yaml";

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

/// Per workflow, its (`doc-digest`, `contract-digest`), and the workspace's
/// own digest, of #16 with each edit made.
type Digests = (BTreeMap<String, (String, String)>, String);

fn digests(name: &str, edits: &[(&str, &str, &str)]) -> Digests {
    let dst = std::env::temp_dir().join(format!("pact-two-digests-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(TREE), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    let out = pact()
        .args(["discover", dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let inv: serde_json::Value = serde_json::from_slice(&out.stdout).expect("JSON");
    let ws = inv.as_array().and_then(|a| a.first()).unwrap_or_else(|| {
        panic!(
            "the edit is refused: {}",
            String::from_utf8_lossy(&out.stderr)
        )
    });
    let flows = ws["workflows"]
        .as_array()
        .expect("every workflow listed")
        .iter()
        .map(|w| {
            let field = |k: &str| w[k].as_str().expect(k).to_string();
            (
                field("name"),
                (field("doc-digest"), field("contract-digest")),
            )
        })
        .collect();
    (flows, ws["digest"].as_str().unwrap().to_string())
}

fn doc(d: &Digests, flow: &str) -> String {
    d.0[flow].0.clone()
}

fn contract(d: &Digests, flow: &str) -> String {
    d.0[flow].1.clone()
}

#[test]
fn every_workflow_has_both_digests_in_name_order() {
    let d = digests("listed", &[]);
    assert_eq!(
        d.0.keys().collect::<Vec<_>>(),
        ["parent-contact", "trial-booking"]
    );
    for (doc, contract) in d.0.values() {
        assert!(doc.starts_with("sha256:") && contract.starts_with("sha256:"));
    }
    assert_ne!(doc(&d, "trial-booking"), doc(&d, "parent-contact"));
    assert_eq!(
        d,
        digests("again", &[]),
        "a digest is a pure function of the files"
    );
}

#[test]
fn rewording_a_workflow_moves_its_doc_digest_and_nobody_elses() {
    let plain = digests("plain", &[]);
    let reworded = digests(
        "reworded",
        &[(
            BOOKING,
            "text a reminder 24 hours",
            "send a reminder 24 hours",
        )],
    );
    assert_ne!(
        doc(&plain, "trial-booking"),
        doc(&reworded, "trial-booking")
    );
    assert_eq!(
        doc(&plain, "parent-contact"),
        doc(&reworded, "parent-contact"),
        "parent-contact never reaches trial-booking, so its runs resume after this edit"
    );
    for flow in ["trial-booking", "parent-contact"] {
        assert_eq!(contract(&plain, flow), contract(&reworded, flow));
    }
    assert_ne!(
        plain.1, reworded.1,
        "the workspace's own digest moves with any edit"
    );
}

#[test]
fn a_workspace_named_like_a_workflow_does_not_reach_it() {
    let named = [(
        "workspace.yaml",
        "name: tutoring-centre",
        "name: trial-booking",
    )];
    let plain = digests("named-plain", &named);
    let reworded = digests(
        "named-reworded",
        &[
            named[0],
            (
                BOOKING,
                "text a reminder 24 hours",
                "send a reminder 24 hours",
            ),
        ],
    );
    assert_eq!(
        doc(&plain, "parent-contact"),
        doc(&reworded, "parent-contact")
    );
}

#[test]
fn a_change_to_a_workflow_it_calls_moves_the_callers_doc_digest() {
    let plain = digests("callee-plain", &[]);
    let edited = digests(
        "callee-edited",
        &[(CONTACT, "    at-most: 3\n", "    at-most: 4\n")],
    );
    assert_ne!(
        doc(&plain, "parent-contact"),
        doc(&edited, "parent-contact")
    );
    assert_ne!(
        doc(&plain, "trial-booking"),
        doc(&edited, "trial-booking"),
        "trial-booking calls parent-contact, so its run relies on it"
    );
    assert_eq!(
        contract(&plain, "trial-booking"),
        contract(&edited, "trial-booking")
    );
}

#[test]
fn a_change_outside_every_workflow_moves_every_doc_digest() {
    let plain = digests("outside-plain", &[]);
    let edited = digests(
        "outside-edited",
        &[(
            "tools/tutor-roster.yaml",
            "description:",
            "description: (edited)",
        )],
    );
    for flow in ["trial-booking", "parent-contact"] {
        assert_ne!(doc(&plain, flow), doc(&edited, flow), "{flow}");
    }
}

#[test]
fn the_contract_digest_moves_with_what_callers_rely_on() {
    let plain = digests("contract-plain", &[]);
    let accepts = digests(
        "contract-accepts",
        &[(
            CONTACT,
            "phone: text }",
            "phone: text, notes: \"text, optional\" }",
        )],
    );
    assert_ne!(
        contract(&plain, "parent-contact"),
        contract(&accepts, "parent-contact")
    );
    assert_eq!(
        contract(&plain, "trial-booking"),
        contract(&accepts, "trial-booking")
    );
    let overlap = digests(
        "contract-overlap",
        &[(BOOKED, "if-still-running: skip", "if-still-running: queue")],
    );
    assert_ne!(
        contract(&plain, "trial-booking"),
        contract(&overlap, "trial-booking")
    );
    assert_eq!(
        doc(&plain, "parent-contact"),
        doc(&overlap, "parent-contact"),
        "a port is read for the workflow it answers, never for what that workflow reaches"
    );
}

#[test]
fn layout_and_comments_move_no_digest() {
    let plain = digests("layout-plain", &[]);
    let laid_out = digests(
        "layout-edited",
        &[
            (
                CONTACT,
                "starts-at: upsert\n",
                "# where it begins\nstarts-at:   upsert\n",
            ),
            (
                CONTACT,
                "answers-with: { contact-id: text }",
                "answers-with:\n  contact-id: text",
            ),
        ],
    );
    assert_eq!(plain, laid_out);
}
