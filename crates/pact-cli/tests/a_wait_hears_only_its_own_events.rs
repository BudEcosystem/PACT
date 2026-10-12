//! **A wait hears only its own events** (N193, FIX-06).
//!
//! An event a port hands to an open run is heard by the first wait that
//! listens for that port. Inside an `each`, every item's wait listens for the
//! same port, so an acknowledgement meant for one custodian could be heard by
//! another's wait. A question's `only-when:` says which events its wait hears,
//! in the one condition grammar: each line looks at what the event brought,
//! `event.<field>`, and compares it with a figure or a value the wait can read
//! (`is: {value: item.custodian-id}`). Held by `arrivals.rs`.
//!
//! Fixture: `tests/trees/workflows-60-interconnection/` (its
//! `wait-for-inspection` listens for `inspection-recorded`, which brings
//! `application-id` and `inspection-result`), copied and edited. Every test
//! drives the real binary over a real tree.

use std::path::{Path, PathBuf};
use std::process::Command;

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/workflows-60-interconnection"
    ))
}

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

const FLOW: &str = "workflows/interconnection.yaml";
const ASKED: &str = "    asked-of: [inspection-recorded]\n";

/// A copy of the tree whose `wait-for-inspection` writes `lines` beside its
/// `asked-of:` (with `asked_of` in its place when given).
fn edited(name: &str, asked_of: &str, lines: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-hears-only-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    let p = dst.join(FLOW);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains(ASKED),
        "fixture drifted: {ASKED:?} not in {FLOW}"
    );
    std::fs::write(&p, text.replacen(ASKED, &format!("{asked_of}{lines}"), 1)).unwrap();
    dst
}

fn check(root: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    let said = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.success(), said)
}

#[test]
fn a_wait_that_hears_only_the_events_of_its_own_case_loads_clean() {
    let root = edited(
        "clean",
        ASKED,
        "    only-when:\n      - { value: event.application-id, is: { value: input.application-id } }\n      \
         - { value: event.inspection-result, is-one-of: [pass, fail] }\n",
    );
    let (ok, said) = check(&root);
    assert!(ok, "{said}");
}

#[test]
fn a_line_that_looks_at_anything_but_the_event_is_refused() {
    let root = edited(
        "not-the-event",
        ASKED,
        "    only-when:\n      - { value: input.application-id, is: A-1 }\n",
    );
    let (ok, said) = check(&root);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/compared-in-the-wrong-shape"),
        "{said}"
    );
    assert!(
        said.contains(
            "looks at 'input.application-id', and a wait's `only-when:` says which events it hears"
        ),
        "{said}"
    );
    assert!(said.contains("fix: Write `value: event.<field>`"), "{said}");
}

#[test]
fn a_field_the_event_does_not_bring_is_refused_with_the_ones_it_does() {
    let root = edited(
        "no-field",
        ASKED,
        "    only-when:\n      - { value: event.custodian-id, is: { value: input.application-id } }\n",
    );
    let (ok, said) = check(&root);
    assert!(!ok, "{said}");
    assert!(said.contains("rule: loader/a-binding-to-nothing"), "{said}");
    assert!(
        said.contains(
            "'wait-for-inspection' hears only the events where 'event.custodian-id' holds, and \
             nothing that arrives at 'inspection-recorded' has a field 'custodian-id'."
        ),
        "{said}"
    );
    assert!(
        said.contains(
            "fix: Use one of the fields listed: `event.application-id`, `event.inspection-result`."
        ),
        "{said}"
    );
}

#[test]
fn a_comparison_in_another_shape_than_the_field_is_refused() {
    let root = edited(
        "wrong-shape",
        ASKED,
        "    only-when:\n      - { value: event.inspection-result, more-than: 200 USD }\n",
    );
    let (ok, said) = check(&root);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/compared-in-the-wrong-shape"),
        "{said}"
    );
}

#[test]
fn only_when_on_a_wait_no_port_answers_is_refused() {
    let root = edited(
        "no-port",
        "    asked-of: [the-clock]\n",
        "    only-when:\n      - { value: event.application-id, is: A-1 }\n",
    );
    let (ok, said) = check(&root);
    assert!(!ok, "{said}");
    assert!(
        said.contains("rule: loader/a-line-this-stage-never-reads"),
        "{said}"
    );
    assert!(
        said.contains("'wait-for-inspection' hears only the events its `only-when:` lets through, and it is asked of no port"),
        "{said}"
    );
}
