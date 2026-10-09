//! There is no combinator key in any group (02W §2.6, §8, F1): every line of a
//! `when:` must hold, and "or" is two rules.
//!
//! A schema walk, so a combinator added anywhere — not only on `when-this` —
//! fails here, and a check that the loader refuses one written by an author.

use std::path::PathBuf;
use std::process::Command;

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

/// The words a condition language would use to join or turn round conditions.
const COMBINATORS: &[&str] = &[
    "or",
    "and",
    "not",
    "any",
    "all",
    "any-of",
    "all-of",
    "none-of",
    "one-of-these",
    "either",
    "neither",
    "unless",
    "except-when",
    "otherwise",
    "if",
];

#[test]
fn no_group_has_a_combinator_key() {
    let spec = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let mut in_groups = false;
    let mut found = Vec::new();
    for line in spec.lines() {
        if line.starts_with("groups:") {
            in_groups = true;
            continue;
        }
        if !in_groups || line.trim_start().starts_with('#') {
            continue;
        }
        // A field is a key six spaces in, under a group's `fields:`.
        if let Some(key) = line
            .strip_prefix("      ")
            .and_then(|l| l.strip_suffix(':'))
            && !key.starts_with(' ')
            && COMBINATORS.contains(&key)
        {
            found.push(key.to_string());
        }
    }
    assert!(
        found.is_empty(),
        "a combinator key in the schema: {found:?}"
    );
}

#[test]
fn a_condition_looks_at_one_thing_with_one_word() {
    // The whole of `when-this`: what it looks at, and the six words. A seventh
    // field here is a change to the one grammar every condition shares.
    let spec = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let start = spec
        .find("\n  when-this:\n")
        .expect("when-this is in the schema");
    let rest = &spec[start + 1..];
    let end = rest[3..]
        .find("\n  # ")
        .or_else(|| rest[3..].find("\n\n  "))
        .unwrap()
        + 3;
    let fields: Vec<&str> = rest[..end]
        .lines()
        .filter_map(|l| l.strip_prefix("      ").and_then(|l| l.strip_suffix(':')))
        .filter(|k| !k.starts_with(' ') && !k.starts_with('#'))
        .collect();
    assert_eq!(
        fields,
        [
            "tool",
            "value",
            "arg",
            "more-than",
            "less-than",
            "is",
            "is-one-of",
            "contains-any-of",
            "is-empty"
        ]
    );
}

#[test]
fn an_or_written_in_a_condition_is_refused_where_it_is_written() {
    let dst = std::env::temp_dir().join(format!("pact-or-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    let src = repo().join("tests/trees/an-invoice-case");
    copy(&src, &dst);
    let flow = dst.join("workflows/one-invoice.yaml");
    let text = std::fs::read_to_string(&flow).unwrap();
    let line = "{ value: steps.match.result, is: matched }";
    assert!(text.contains(line), "fixture drifted");
    std::fs::write(
        &flow,
        text.replacen(line, "{ value: steps.match.result, is: matched, or: { value: input.invoice.po, is-empty: yes } }", 1),
    )
    .unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let said = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success(), "{said}");
    assert!(
        said.contains("'or' is not something a condition can look at"),
        "{said}"
    );
    assert!(said.contains("rule: schema/unknown-field"), "{said}");
    let _ = std::fs::remove_dir_all(&dst);
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
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
