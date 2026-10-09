//! The acceptance clause says every one of Eve's 80 capabilities is either
//! expressible in the schema, declared and delegated to the runtime, or listed
//! in `docs/50-NOT-COPIED.md` with a reason — **no fourth category**.
//!
//! The first of those three is already held under test by `authoring_surface.rs`
//! (every field explains itself). The third is a prose document, and a prose
//! document is exactly the kind of artifact that decays into the fourth category
//! by accident: a row gets added with no reason, or with a reason that is the
//! refusal said twice, and nobody notices because nothing was checking.
//!
//! So the refusal ledger is held to the same bar the schema's `help:` text is:
//! it names a file the reader can open, it gives a reason that is a constraint
//! rather than a restatement, it says what to do instead, and it never answers a
//! capability with "write code for it" — which decision D14 rules out for every
//! capability in the core, refusals included.

use std::path::{Path, PathBuf};

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn page() -> String {
    let p = repo().join("docs/50-NOT-COPIED.md");
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

/// The rows of the refusal ledger in §5, each already split into its cells.
fn ledger() -> Vec<Vec<String>> {
    let text = page();
    let mut rows = Vec::new();
    let mut inside = false;
    for line in text.lines() {
        if line.starts_with("## 5.") {
            inside = true;
            continue;
        }
        if inside && line.starts_with("## ") {
            break;
        }
        if inside && line.starts_with("| R") {
            let cells: Vec<String> = line
                .trim_matches('|')
                .split('|')
                .map(|c| c.trim().to_string())
                .collect();
            rows.push(cells);
        }
    }
    rows
}

/// Whole-word test, so "structural" does not read as "struct".
fn says_word(haystack: &str, word: &str) -> bool {
    haystack
        .to_lowercase()
        .split(|c: char| !c.is_ascii_alphanumeric())
        .any(|t| t == word)
}

#[test]
fn the_specification_records_what_it_refuses() {
    let text = page();
    assert!(
        text.contains("accumulates everything"),
        "the page must open with the argument for its own existence"
    );
    // The four the design settled before the schema was written. Each is checked
    // by a detail from Eve's own source, so the section cannot survive as a
    // heading with the substance removed.
    for (what, evidence) in [
        ("built-in tools", "framework-tools"),
        ("durable execution", "Workflow SDK"),
        ("the developer console", "4,754"),
        ("running author code to check it", "Failed to execute the"),
    ] {
        assert!(
            text.contains(evidence),
            "the refusal of {what} has lost its evidence ({evidence:?})"
        );
    }
}

#[test]
fn every_up_front_refusal_says_what_eve_ships_why_pact_declines_and_what_to_do_instead() {
    // Two of the three are the honest part. A section with only "why PACT
    // declines" is an opinion; a section with only "what Eve ships" is a
    // comparison. The third — what to do instead — is the one D14 makes
    // compulsory: a refusal that leaves an author with nowhere to go has
    // removed a capability rather than generalised it.
    let text = page();
    let sections: Vec<&str> = text.split("\n### ").skip(1).collect();
    let up_front: Vec<&&str> = sections.iter().filter(|s| s.starts_with("1.")).collect();
    assert_eq!(
        up_front.len(),
        4,
        "§1 must carry exactly the four refusals the design took up front"
    );

    for s in up_front {
        let title = s.lines().next().unwrap_or("");
        for part in [
            "**What Eve ships.**",
            "**Why PACT declines.**",
            "**What to do instead.**",
        ] {
            assert!(s.contains(part), "§{title} is missing {part}");
        }
    }
}

#[test]
fn every_refusal_in_the_ledger_carries_a_reason_and_a_replacement() {
    let rows = ledger();
    assert!(
        rows.len() >= 12,
        "only {} refusals recorded — the ledger has gone stale",
        rows.len()
    );

    for row in &rows {
        assert_eq!(
            row.len(),
            5,
            "a ledger row is #, refusal, because, instead, where: {row:?}"
        );
        let id = &row[0];
        // A reason that fits in a handful of words is a label, not a reason.
        assert!(
            row[2].split_whitespace().count() >= 8,
            "{id}: the reason is too short to be one: {:?}",
            row[2]
        );
        assert!(
            !row[3].is_empty(),
            "{id}: nothing offered in place of what was refused"
        );
        assert!(
            !row[4].is_empty(),
            "{id}: no pointer to where the refusal is argued"
        );
    }
}

#[test]
fn no_refusal_is_explained_by_saying_it_was_not_needed() {
    // The whole point of the file. "We did not need it" restates the refusal and
    // tells a reader nothing about whether it should be revisited; a constraint
    // tells them exactly what would have to change first.
    const RESTATEMENTS: &[&str] = &[
        "did not need",
        "not needed",
        "no need",
        "out of scope",
        "not required",
        "unnecessary",
        "not a priority",
        "low priority",
        "nobody asked",
        "no one asked",
        "we chose not to",
    ];
    for row in ledger() {
        let because = row[2].to_lowercase();
        for phrase in RESTATEMENTS {
            assert!(
                !because.contains(phrase),
                "{}: {phrase:?} is a restatement, not a reason: {:?}",
                row[0],
                row[2]
            );
        }
    }
}

#[test]
fn no_capability_is_answered_with_experts_write_code_for_that() {
    // D14 makes this unacceptable for every capability in the core, and a
    // refusal is where the temptation is strongest: the behaviour is gone, so
    // pointing at a code escape looks like an answer. It is not one — the
    // author D13 describes cannot take it.
    const ESCAPES: &[&str] = &[
        "write code",
        "writes code",
        "write your own code",
        "requires code",
        "in typescript",
        "in python",
        "a small script",
    ];
    for row in ledger() {
        let instead = row[3].to_lowercase();
        for escape in ESCAPES {
            assert!(
                !instead.contains(escape),
                "{}: {escape:?} is not an answer a non-coder can take: {:?}",
                row[0],
                row[3]
            );
        }
    }
}

#[test]
fn every_ledger_row_points_at_something_that_exists() {
    // A pointer into a section that was renamed is how a document starts lying.
    let text = page();
    for row in ledger() {
        let id = &row[0];
        let target = &row[4];

        for reference in section_refs(target) {
            let heading = if reference.contains('.') {
                format!("### {reference} ")
            } else {
                format!("## {reference}. ")
            };
            assert!(
                text.contains(&heading),
                "{id} points at §{reference}, which is not a heading here"
            );
        }
        // "§2 (G5)" must land on a real row of the mechanism table.
        for mechanism in mechanism_refs(target) {
            assert!(
                text.contains(&format!("**{mechanism}**")),
                "{id} points at {mechanism}, which is not in the mechanism table"
            );
        }
        if target.contains("spec/schema.yaml") {
            assert!(
                repo().join("spec/schema.yaml").exists(),
                "{id} points at a specification file that is not there"
            );
        }
    }
}

fn section_refs(cell: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut rest = cell;
    while let Some(at) = rest.find('§') {
        rest = &rest['§'.len_utf8() + at..];
        let n: String = rest
            .chars()
            .take_while(|c| c.is_ascii_digit() || *c == '.')
            .collect();
        let n = n.trim_end_matches('.').to_string();
        if !n.is_empty() {
            out.push(n);
        }
    }
    out
}

fn mechanism_refs(cell: &str) -> Vec<String> {
    (1..=8)
        .map(|n| format!("G{n}"))
        .filter(|g| cell.contains(g.as_str()))
        .collect()
}

#[test]
fn the_reasons_read_without_programming_knowledge() {
    // Same bar as the schema's help text and the loader's diagnostics: a support
    // lead has to be able to read why a thing is absent, because they are the
    // person most likely to ask for it back.
    const JARGON: &[&str] = &[
        "enum",
        "enums",
        "serde",
        "deserialize",
        "deserialise",
        "unwrap",
        "trait",
        "traits",
        "struct",
        "structs",
        "stdout",
        "stderr",
        "regex",
        "async",
        "await",
        "mutex",
        "callback",
        "closure",
        "idempotent",
        "polymorphic",
        "nullable",
        "abi",
    ];
    for row in ledger() {
        for cell in [&row[2], &row[3]] {
            for word in JARGON {
                assert!(
                    !says_word(cell, word),
                    "{}: '{word}' assumes programming knowledge: {cell:?}",
                    row[0]
                );
            }
            for phrase in ["stack trace", "null pointer", "type error"] {
                assert!(
                    !cell.to_lowercase().contains(phrase),
                    "{}: '{phrase}' assumes programming knowledge: {cell:?}",
                    row[0]
                );
            }
        }
    }
}

#[test]
fn a_deferral_is_kept_apart_from_a_refusal() {
    // These decay into each other in both directions: a deferral quietly
    // becomes permanent, or a refusal gets reopened because someone read it as
    // a to-do. The file has to say which it is, and a deferral has to name what
    // would let it back in.
    let text = page();
    let deferred = text.split("## 6. Deferred").nth(1).expect("§6 must exist");
    let deferred = deferred.split("\n## ").next().unwrap_or(deferred);
    assert!(
        deferred.contains("25-ARCHITECTURE-DECISIONS.md"),
        "§6 must point at the list that holds the re-admission conditions"
    );
    for row in ledger() {
        assert!(
            !row[4].contains("§6"),
            "{}: a deferral must not be recorded as a refusal",
            row[0]
        );
    }
}

#[test]
fn the_three_categories_are_each_given_a_way_to_be_checked() {
    // This is the acceptance clause itself. It only means anything if a reader
    // can decide, for a capability in front of them, which of the three it is —
    // otherwise "no fourth category" is unfalsifiable.
    let text = page();
    assert!(
        text.contains("No fourth category"),
        "the clause the page serves must be quoted in it"
    );
    for artifact in [
        "spec/schema.yaml",                             // (a)
        "PACT DECLARES a port",                         // (b) — the schema saying so itself
        "crates/pact-cli/tests/deliberate_refusals.rs", // (c) — this file
    ] {
        assert!(
            text.contains(artifact),
            "no way given to check a category: {artifact} is not named"
        );
    }
}
