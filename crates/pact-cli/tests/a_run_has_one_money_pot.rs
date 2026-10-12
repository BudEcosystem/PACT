//! A run has one money pot, and a ceiling says what it is counted across
//! (02W §2.10, §3 WF-31, R32), over #48's invoice run
//! (`tests/trees/workflows-48-invoices/`).
//!
//! `cost-per-request-under:` on a stage is that stage's share of the run's
//! figure, never a second pot: a share with no pot around it is refused, and
//! so are fixed shares that add up to more than their pot. `counted-per:` is
//! `run`, `connection`, `team`, or in a workflow a binding that names what the
//! workflow has; `resets-every:` needs it.

use std::path::{Path, PathBuf};
use std::process::Command;

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
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

const FLOW: &str = "workflows/one-invoice.yaml";
/// The run's own `limits:`, as printed.
const RUN: &str = "limits:\n  finishes-within: 7 days\n";
/// The first two stages, as printed.
const VENDOR: &str = "  vendor:\n    does: call\n";
const PO: &str = "  po:\n    does: call\n";

fn share(stage: &str, figure: &str) -> String {
    format!(
        "  {stage}:\n    does: call\n    limits:\n      cost-per-request-under: {figure}\n      \
         when-it-runs-out: stop-and-say-so\n"
    )
}

fn check(name: &str, edits: &[(&str, String)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-pots-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join("tests/trees/workflows-48-invoices"), &dst);
    let p = dst.join(FLOW);
    let mut text = std::fs::read_to_string(&p).unwrap();
    for (from, to) in edits {
        assert!(text.contains(from), "fixture drifted: {from:?}");
        text = text.replacen(from, to, 1);
    }
    std::fs::write(&p, text).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dst.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

fn pot(figure: &str) -> String {
    format!("{RUN}  cost-per-request-under: {figure}\n")
}

#[test]
fn a_stages_share_of_no_pot_is_refused() {
    let (ok, text) = check("no-pot", &[(VENDOR, share("vendor", "1.50 USD"))]);
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "'vendor' has a money ceiling, and the workflow 'one-invoice' has none — a stage's \
             figure is its share of the run's, never a second pot, so this is a share of nothing."
        ),
        "{text}"
    );
    assert!(
        text.contains("fix: Put the figure on the workflow — `cost-per-request-under:`"),
        "{text}"
    );
    assert!(text.contains("rule: loader/a-share-of-no-pot"), "{text}");
}

#[test]
fn shares_inside_their_pot_load() {
    let (ok, text) = check(
        "inside",
        &[
            (RUN, pot("3 USD")),
            (VENDOR, share("vendor", "1.50 USD")),
            (PO, share("po", "1.50 USD")),
        ],
    );
    assert!(ok, "{text}");
}

#[test]
fn shares_that_add_up_to_more_than_their_pot_are_refused() {
    let (ok, text) = check(
        "over",
        &[
            (RUN, pot("2 USD")),
            (VENDOR, share("vendor", "1.50 USD")),
            (PO, share("po", "1.25 USD")),
        ],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains(
            "The stages under the workflow 'one-invoice' give themselves 2.75 USD in all, more \
             than its own 2 USD — so they could not all spend their share."
        ),
        "{text}"
    );
}

#[test]
fn a_ceiling_is_counted_across_a_run_a_connection_a_team_or_a_binding() {
    for (said, ok) in [
        ("run", true),
        ("team", true),
        ("input.sender", true),
        ("customer", false),
    ] {
        let (loaded, text) = check(
            &format!("counted-{said}"),
            &[(
                RUN,
                format!("{RUN}  counted-per: {said}\n  resets-every: 1 day\n"),
            )],
        );
        assert_eq!(loaded, ok, "{said}:\n{text}");
        if !ok {
            assert!(
                text.contains(
                    "`counted-per: customer` names nothing a ceiling can be counted across."
                ),
                "{text}"
            );
            assert!(
                text.contains("rule: loader/counted-across-nothing"),
                "{text}"
            );
        }
    }
}

#[test]
fn a_binding_counted_across_names_what_the_workflow_has() {
    let (ok, text) = check(
        "counted-nothing",
        &[(RUN, format!("{RUN}  counted-per: input.sendr\n"))],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("rule: loader/a-binding-to-nothing"), "{text}");
}

#[test]
fn a_period_needs_something_counted_across_it() {
    let (ok, text) = check(
        "resets-alone",
        &[(RUN, format!("{RUN}  resets-every: 30 days\n"))],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("counted-per"), "{text}");
}
