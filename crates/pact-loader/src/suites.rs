//! **Tests over recorded runs: what a suite says about the runs it is a score
//! of** (02W §2.13, §3 WF-34's program half).
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/a-line-this-suite-never-reads` | §2.13 | `from-the-last:` on a suite whose `population:` is not `past-runs`, or `sample:` or `reviewed-by:` on one whose `population:` is not `sampled-frame` |
//! | `loader/slices-by-what-no-run-is-given` | §2.13 | a `sliced-by:` field that no workflow held to these checks (`evals:`) `accepts:` |
//! | `loader/every-is-not-a-time` | shipped | `runs-every:` is not a line a clock can keep, read by the grammar a port's `every:` is (`schedules.rs`) |
//! | `loader/only-a-pure-program-grades` | §2.13, WF-34 | a rule's `program:` (in `evals:`, a case's `must-also:`, or any `checked-by:`) names a program that is not `determinism: pure` |
//!
//! A sample with no share or nobody to review it is the schema's own
//! `needed-when:` on `population:` (`schema/missing-companion`), and a
//! `program:` this workspace lacks is `names: programs` (`schema/no-such-name`):
//! WF-34's program half is that line, said where the author wrote the name,
//! and the purity rule here. A `judged:` rule with no grader stays
//! `failures.rs`'s.

use crate::schedules;
use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node};
use pact_schema::{Schema, Ty};

/// The group every rule shape is written in.
const EVAL_RULE: &str = "eval-rule";

/// The lines only one population reads, and the population that reads them.
const READ_ONLY_BY: [(&str, &str); 3] = [
    ("from-the-last", "past-runs"),
    ("sample", "sampled-frame"),
    ("reviewed-by", "sampled-frame"),
];

/// Every check on a suite's population, slices, schedule and graders.
pub fn check(document: &Node, schema: &Schema, diags: &mut Diagnostics) {
    if let Some(suite) = document.get("evals").and_then(Node::as_map) {
        population_lines(suite, diags);
        slices(document, suite, diags);
        schedule(suite, diags);
    }
    let mut rules = Vec::new();
    rules_in(document, "workspace", schema, 0, &mut rules);
    for rule in rules {
        pure_grader(document, rule, diags);
    }
}

/// `from-the-last:`, `sample:` and `reviewed-by:` beside the population that
/// reads them, and nowhere else.
fn population_lines(suite: &Map, diags: &mut Diagnostics) {
    let population = suite
        .get("population")
        .and_then(|e| e.node.as_str())
        .unwrap_or("")
        .trim();
    for (line, reader) in READ_ONLY_BY {
        let Some(entry) = suite.get(line) else {
            continue;
        };
        if population == reader {
            continue;
        }
        diags.push(Diagnostic::error(
            "loader/a-line-this-suite-never-reads",
            entry.key_span.clone(),
            format!(
                "`{line}:` is read only when `population:` is `{reader}`, and these checks say \
                 `population: {population}` — so this line would load and change nothing."
            ),
            format!("Write `population: {reader}`, or take `{line}:` out."),
        ));
    }
}

/// Each `sliced-by:` field is one a run is given: an `accepts:` field of a
/// workflow held to these checks. A suite only agents name is left alone, since
/// an agent's run is given whatever its eval cases' `with:` say.
fn slices(document: &Node, suite: &Map, diags: &mut Diagnostics) {
    let Some(sliced) = suite.get("sliced-by").and_then(|e| e.node.as_list()) else {
        return;
    };
    let held: Vec<(&str, &Node)> = document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .filter(|(_, w)| w.node.get("evals").is_some())
        .map(|(name, w)| (name.as_str(), &w.node))
        .collect();
    if held.is_empty() {
        return;
    }
    for field in sliced {
        let Some(name) = field.as_str().map(str::trim) else {
            continue;
        };
        let given = held.iter().any(|(_, w)| {
            w.get("accepts")
                .and_then(Node::as_map)
                .is_some_and(|a| a.get(name).is_some())
        });
        if given {
            continue;
        }
        let flows: Vec<String> = held.iter().map(|(n, _)| format!("'{n}'")).collect();
        let accepted: Vec<String> = held
            .iter()
            .filter_map(|(_, w)| w.get("accepts").and_then(Node::as_map))
            .flat_map(|a| a.iter().map(|(k, _)| format!("`{k}`")))
            .collect();
        diags.push(Diagnostic::error(
            "loader/slices-by-what-no-run-is-given",
            field.span.clone(),
            format!(
                "`sliced-by:` breaks the scores down by `{name}`, and no workflow held to these \
                 checks ({}) accepts a `{name}` — so every run would fall in one group with \
                 nothing in it.",
                flows.join(", ")
            ),
            if accepted.is_empty() {
                "Slice by a field the workflow's `accepts:` lists, or take this line out."
                    .to_string()
            } else {
                format!(
                    "Slice by one of the fields a run is given: {}.",
                    accepted.join(", ")
                )
            },
        ));
    }
}

/// `runs-every:` is read, and refused, as a port's `every:` is.
fn schedule(suite: &Map, diags: &mut Diagnostics) {
    if let Some(entry) = suite.get("runs-every") {
        schedules::refuse_unless_a_time(
            entry,
            "runs-every",
            "",
            "to run these checks",
            "Whatever serves this workspace would refuse to keep its clock.",
            diags,
        );
    }
}

/// A rule's `program:` is a pure program: a grade is replayed from what was
/// recorded, and a grader that answers differently the second time would make
/// a replayed verdict a new one. Whether the program exists is `names:`'s.
fn pure_grader(document: &Node, rule: &Node, diags: &mut Diagnostics) {
    let Some(entry) = rule.as_map().and_then(|m| m.get("program")) else {
        return;
    };
    let Some(name) = entry.node.as_str().map(str::trim) else {
        return;
    };
    let Some(program) = document
        .get("programs")
        .and_then(Node::as_map)
        .and_then(|p| p.get(name))
    else {
        return;
    };
    let how = program
        .node
        .get("determinism")
        .and_then(Node::as_str)
        .unwrap_or("")
        .trim();
    if how == "pure" {
        return;
    }
    diags.push(Diagnostic::error(
        "loader/only-a-pure-program-grades",
        entry.node.span.clone(),
        format!(
            "This rule is graded by the program '{name}', and '{name}' says it is `{how}` \
             rather than `pure` — so a recorded run graded again could get another verdict."
        ),
        format!(
            "Mark '{name}' `determinism: pure` if it works only from what it is given, or check \
             with a rule that needs no program, such as `library:` or `must-contain:`."
        ),
    ));
}

/// Every rule written in this document, wherever the schema puts a list of
/// them (`evals.rules`, a case's `must-also:`, an agent's or a stage's
/// `checked-by:`), found by walking the schema's own groups, so a field added
/// with `list of group:eval-rule` joins this check by existing.
fn rules_in<'a>(
    node: &'a Node,
    group: &str,
    schema: &Schema,
    depth: usize,
    out: &mut Vec<&'a Node>,
) {
    if depth > 12 {
        return;
    }
    let (Some(g), Some(map)) = (schema.group(group), node.as_map()) else {
        return;
    };
    for field in &g.fields {
        let Some(entry) = map.get(field.name.as_str()) else {
            continue;
        };
        let inner = match &field.ty {
            Ty::Group(kind) => {
                rules_in(&entry.node, kind, schema, depth + 1, out);
                continue;
            }
            Ty::MapOf(inner) | Ty::ListOf(inner) => inner.as_ref(),
            _ => continue,
        };
        let Ty::Group(kind) = inner else { continue };
        let children: Vec<&Node> = match &entry.node.value {
            pact_doc::Value::Map(m) => m.iter().map(|(_, c)| &c.node).collect(),
            pact_doc::Value::List(l) => l.iter().collect(),
            _ => Vec::new(),
        };
        for child in children {
            if kind == EVAL_RULE {
                out.push(child);
            } else {
                rules_in(child, kind, schema, depth + 1, out);
            }
        }
    }
}
