//! 02W §7.2, "Templates": a copy records `based-on: <template>@<version>`.
//! The loader accepts the version, builds the copy from the pattern named
//! before the `@`, and records the version on the load report (`pact waits`'
//! `substitutions`), where a runtime finds every copy made from an older
//! version of a template. Nothing of it reaches the document `pact show`
//! prints: a copy and the same copy with no version are one document, one
//! digest. A bare `@` is refused, naming the fix. Over
//! `tests/trees/two-desks-one-pattern/`, whose desks `refunds` and `returns`
//! are both made from `desk-pattern`.
//!
//! And `pact discover` says, per workflow, which workflows its doc-digest
//! keeps (`reaches`) and what it leaves out (`left-out`), so a runtime
//! comparing two versions of what a run relies on compares exactly what the
//! digest covers (#16's tree).

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

const DESKS: &str = "tests/trees/two-desks-one-pattern";
const REFUNDS: &str = "agents/refunds/agent.yaml";

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

/// The two desks with `refunds`' `based-on:` written as `to`.
fn desks(name: &str, to: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-copy-version-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(DESKS), &dst);
    let p = dst.join(REFUNDS);
    let text = std::fs::read_to_string(&p).unwrap();
    assert!(
        text.contains("based-on: desk-pattern\n"),
        "fixture drifted: {text}"
    );
    std::fs::write(
        &p,
        text.replacen("based-on: desk-pattern\n", &format!("based-on: {to}\n"), 1),
    )
    .unwrap();
    dst
}

fn run(args: &[&str]) -> (Option<i32>, String, String) {
    let out = pact().args(args).output().expect("pact runs");
    (
        out.status.code(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

#[test]
fn the_version_is_on_the_report_and_never_in_the_document() {
    let versioned = desks("versioned", "desk-pattern@1.2");
    let plain = desks("plain", "desk-pattern");
    let at = versioned.to_str().unwrap();

    let (code, _, err) = run(&["check", at]);
    assert_eq!(code, Some(0), "a versioned copy loads:\n{err}");

    let (code, waits, err) = run(&["waits", at]);
    assert_eq!(code, Some(0), "{waits}{err}");
    let report: serde_json::Value = serde_json::from_str(&waits).expect("waits emits JSON");
    let built: Vec<&serde_json::Value> = report["substitutions"]
        .as_array()
        .expect("the report carries them")
        .iter()
        .filter(|s| s["kind"] == "pattern")
        .collect();
    assert_eq!(
        built.len(),
        2,
        "both desks are made from the pattern:\n{waits}"
    );
    let refunds = built
        .iter()
        .find(|s| s["at"].as_str().is_some_and(|a| a.ends_with(REFUNDS)))
        .expect("refunds' substitution");
    assert_eq!(
        refunds["name"], "desk-pattern",
        "the name before the `@`:\n{waits}"
    );
    assert_eq!(refunds["version"], "1.2", "{waits}");
    let returns = built
        .iter()
        .find(|s| {
            s["at"]
                .as_str()
                .is_some_and(|a| a.ends_with("agents/returns/agent.yaml"))
        })
        .expect("returns' substitution");
    assert!(
        returns.get("version").is_none(),
        "returns names no version:\n{waits}"
    );

    let (_, shown, _) = run(&["show", at]);
    let (_, longhand, _) = run(&["show", plain.to_str().unwrap()]);
    assert!(
        !shown.contains("1.2"),
        "the version is not in the document:\n{shown}"
    );
    assert_eq!(shown, longhand, "a versioned copy is the same document");
    let digest = |root: &Path| {
        let (_, out, _) = run(&["discover", root.to_str().unwrap()]);
        let inv: serde_json::Value = serde_json::from_str(&out).unwrap();
        inv[0]["digest"].as_str().unwrap().to_string()
    };
    assert_eq!(digest(&versioned), digest(&plain), "and the same digest");
}

#[test]
fn an_at_with_no_version_is_refused() {
    let tree = desks("bare-at", "desk-pattern@");
    let (code, out, err) = run(&["check", tree.to_str().unwrap()]);
    let err = out + &err;
    assert_eq!(code, Some(1), "{err}");
    assert!(err.contains("loader/based-on-names-no-version"), "{err}");
    assert!(
        err.contains("'refunds' is based on 'desk-pattern@'"),
        "{err}"
    );
    assert!(err.contains("names no version"), "{err}");
    assert!(
        err.contains("fix: Write the template's version after the `@`"),
        "{err}"
    );
}

#[test]
fn a_version_of_a_pattern_nothing_has_is_no_such_name() {
    let tree = desks("unknown", "desk-patern@1.2");
    let (code, out, err) = run(&["check", tree.to_str().unwrap()]);
    let err = out + &err;
    assert_eq!(code, Some(1), "{err}");
    assert!(err.contains("loader/no-such-name"), "{err}");
    assert!(
        err.contains("based on 'desk-patern'"),
        "the name, without the version:\n{err}"
    );
}

#[test]
fn discover_says_which_workflows_each_doc_digest_keeps() {
    let tree = repo().join("tests/trees/workflows-16-trial-booking");
    let (code, out, err) = run(&["discover", tree.to_str().unwrap()]);
    assert_eq!(code, Some(0), "{err}");
    let inv: serde_json::Value = serde_json::from_str(&out).unwrap();
    let reaches = |name: &str| -> Vec<String> {
        inv[0]["workflows"]
            .as_array()
            .unwrap()
            .iter()
            .find(|w| w["name"] == name)
            .and_then(|w| w["reaches"].as_array())
            .unwrap_or_else(|| panic!("{name} has its reaches:\n{out}"))
            .iter()
            .map(|v| v.as_str().unwrap().to_string())
            .collect()
    };
    assert_eq!(
        reaches("trial-booking"),
        ["parent-contact", "trial-booking"]
    );
    assert_eq!(reaches("parent-contact"), ["parent-contact"]);
    // And what each doc-digest leaves out, as the keys down to it: the
    // workflow it never reaches and the ports that answer that one.
    let left_out = |name: &str| -> serde_json::Value {
        inv[0]["workflows"]
            .as_array()
            .unwrap()
            .iter()
            .find(|w| w["name"] == name)
            .map(|w| w["left-out"].clone())
            .unwrap_or_else(|| panic!("{name} has its left-out:\n{out}"))
    };
    assert_eq!(
        left_out("parent-contact"),
        serde_json::json!([
            ["workflows", "trial-booking"],
            ["ports", "trial-booked"],
            ["ports", "trial-cancelled"]
        ])
    );
    assert_eq!(left_out("trial-booking"), serde_json::json!([]));
}
