//! `= 80` has to mean the same thing here as it does in the resolver.
//!
//! An author writes one line — `needs: scores: MMLU: "= 80"` — and two pieces of
//! code decide it. This crate parses it (`coerce::threshold`) and answers it
//! (`Op::holds`); `adapters/python/src/pact_adapters/resolve.py` parses it again
//! (`_threshold`) and answers it again (`_HOLDS`). The Python file has carried a
//! comment for as long as it has existed saying it *"mirrors `Op::holds` in
//! `crates/pact-schema/src/coerce.rs`"* and that *"a difference between the two
//! is a model bound on a rule the checker read differently"*. It was not a
//! mirror:
//!
//! ```text
//! Op::holds     Op::Eq => (lhs - rhs).abs() < f64::EPSILON   ~0.00000000000000022
//! _HOLDS["="]   abs(have - want) < 1e-12                     ~0.000000000001
//! ```
//!
//! Four orders of magnitude apart, and neither figure was chosen for scores.
//! `f64::EPSILON` is the gap between 1 and the next number a double can hold; at
//! a score of 80 the gap is about 0.00000000000001, sixty-four times larger, so
//! nothing but a bit-for-bit 80 could ever be within an EPSILON of it. `= 80`
//! was an exact-bits test wearing a tolerance's clothes, while the resolver on
//! the other side of the wire was granting a slack of several hundred steps.
//!
//! Both now read `SCORE_TOLERANCE`, and both are held to `spec/comparisons.yaml`
//! — the same table, in the same words, checked from both languages. That file
//! carries the reasoning for the figure; the short version is that a billionth
//! is far larger than the noise of writing a number down and reading it back,
//! and far smaller than the two decimal places a benchmark is published to.
//!
//! The Python half is
//! `adapters/python/tests/test_a_comparison_means_the_same_thing_in_both_ports.py`,
//! which drives the same rows through `ModelEntry.satisfies` — the door a real
//! recommendation goes through. Neither file can be made to pass by editing one
//! port, which is the whole point of putting the table between them.
//!
//! Mutation: put `f64::EPSILON` back in `Op::Eq`. The `= 80` /
//! `79.999999999999` row goes red here, and every other test in the workspace
//! stays green — which is how the two ports spent a release disagreeing.
//! Setting `SCORE_TOLERANCE` to the resolver's old `1e-12` instead leaves that
//! row green and fails the `= 80` / `80.0000000001` row, which is the same
//! defect measured from the other side. Setting it to `1e-6` fails the
//! `80.00000001` row, which is what stops the tolerance being widened until it
//! starts calling `79.99` a score of 80.

use camino::Utf8Path;
use pact_doc::{Value, parse_yaml};
use pact_schema::Ty;
use pact_schema::coerce::{Coerced, SCORE_TOLERANCE, check};

/// The table both ports are held to.
fn table() -> pact_doc::Node {
    let path = Utf8Path::new(env!("CARGO_MANIFEST_DIR")).join("../../spec/comparisons.yaml");
    let text =
        std::fs::read_to_string(&path).expect("spec/comparisons.yaml is part of the repository");
    parse_yaml(&text, &path).expect("spec/comparisons.yaml parses")
}

fn text_at(node: &pact_doc::Node, key: &str) -> String {
    match &node
        .get(key)
        .unwrap_or_else(|| panic!("every row states '{key}'"))
        .value
    {
        Value::Str(s) => s.clone(),
        other => panic!("'{key}' is written as quoted text, not {other:?}"),
    }
}

/// A `Node` holding one scalar, which is what `check` takes.
fn scalar(written: &str) -> pact_doc::Node {
    let doc = parse_yaml(
        &format!("v: {}\n", serde_json::to_string(written).unwrap()),
        Utf8Path::new("comparison.yaml"),
    )
    .unwrap();
    doc.get("v").unwrap().clone()
}

#[test]
fn the_tolerance_is_the_one_the_specification_states() {
    let stated: f64 = text_at(&table(), "tolerance")
        .parse()
        .expect("`tolerance:` in spec/comparisons.yaml is a decimal figure");
    assert_eq!(
        SCORE_TOLERANCE, stated,
        "`Op::Eq` allows {SCORE_TOLERANCE:e} and spec/comparisons.yaml says {stated:e}. \
         The resolver reads that file too, so the two ports are now deciding `= 80` \
         differently and only one of them is wrong about it."
    );
}

#[test]
fn every_comparison_in_the_table_is_decided_the_way_the_table_says() {
    let doc = table();
    let rows = match &doc
        .get("cases")
        .expect("spec/comparisons.yaml states `cases:`")
        .value
    {
        Value::List(rows) => rows.clone(),
        other => panic!("`cases:` is a list, not {other:?}"),
    };
    assert!(
        rows.len() >= 10,
        "spec/comparisons.yaml carries {} rows; it had fourteen, and a table that \
         shrinks is a mirror that stopped being checked",
        rows.len()
    );

    for row in &rows {
        let written = text_at(row, "written");
        let published: f64 = text_at(row, "published")
            .parse()
            .expect("`published:` is a decimal figure in quotes");
        let expected = text_at(row, "holds") == "yes";
        let because = text_at(row, "because");

        let Some(Coerced::Threshold { op, value }) = check(&scalar(&written), &Ty::Threshold)
        else {
            panic!(
                "the checker cannot read '{written}' as a comparison at all, and \
                 spec/comparisons.yaml says an author may write it"
            );
        };
        let got = op.holds(published, value);
        assert_eq!(
            got, expected,
            "'{written}' against a published {published}: the checker says {got} and \
             spec/comparisons.yaml says {expected} — {because}"
        );
    }
}

/// And the other half of the agreement: the rows neither port may read.
///
/// `cases:` pins what the two must answer the same way. This pins what both must
/// REFUSE, and that is where they had come apart: this crate has always answered
/// `None` to a bare number — *"a bare number states no comparison"* — while
/// `resolve._threshold` read `MMLU: 80` as `> 80` under a docstring calling that
/// "what every author who wrote one meant".
///
/// Unreachable, so nothing went red: `pact check` refuses `MMLU: 80` at the
/// author's own line, and a document carrying one never reaches the resolver. An
/// unreachable disagreement is the kind that lasts, because the only thing that
/// would find it is a table like this one.
///
/// Closed by refusing in both rather than by writing the asymmetry down as
/// deliberate, because the guess is not obviously right. `< 5` is a real bar on a
/// latency or a hallucination rate, and there an assumed `>` binds exactly the
/// models the line was written to exclude, silently.
///
/// The `> inf` row is the one this table found in the OTHER direction:
/// `float("inf")` parses in Python, so the resolver read `> inf` as a threshold
/// no model could clear while this crate called it `schema/wrong-type`. Both
/// refuse it now, and `> 1e999` is deliberately NOT in the table — a figure past
/// the end of the number line is a different mistake from a word, and is carried
/// up so the ceiling can name it at the author's line.
///
/// Mutation: drop the `else { return None }` arm from `threshold`'s prefix match
/// so a bare number falls through to `rest.parse()`. The `80`, `0.8` and `80%`
/// rows go red here and the Python twin stays green — the original defect, from
/// the side that did not have it.
#[test]
fn nothing_the_table_calls_unreadable_is_read_as_a_comparison() {
    let doc = table();
    let rows = match &doc
        .get("not-comparisons")
        .expect("spec/comparisons.yaml states `not-comparisons:`")
        .value
    {
        Value::List(rows) => rows.clone(),
        other => panic!("`not-comparisons:` is a list, not {other:?}"),
    };
    assert!(
        rows.len() >= 5,
        "spec/comparisons.yaml carries {} unreadable rows; it had seven, and a \
         table that shrinks is a mirror that stopped being checked",
        rows.len()
    );

    for row in &rows {
        let written = text_at(row, "written");
        let because = text_at(row, "because");
        assert_eq!(
            check(&scalar(&written), &Ty::Threshold),
            None,
            "the checker read '{written}' as a comparison, and \
             spec/comparisons.yaml says neither port may — {because}"
        );
    }
}
