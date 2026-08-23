//! Where the written rules in a skill begin, and how many there are (§8.3a).
//!
//! # Why this exists
//!
//! §8.3a's observation is that the surface annotation was attached to the FIELD,
//! and one field holds both explanatory prose and the rules the model treats as
//! authority: *"An identical sentence in `policies/approvals.yaml` is
//! `S-EXEC`/CLASS-4; in a `SKILL.md` body it was CLASS-1."*
//!
//! Its rules 1 and 2 put a floor under those lines, and the executing side holds
//! it: a numbered or bulleted line under a heading in the closed set is a
//! NORMATIVE CLAUSE, and editing one needs a person however the edit is made.
//!
//! Rule 4 is the half that makes the floor usable rather than merely enforced:
//!
//! > `pact check` prints, per skill, how many clauses it classified as normative
//! > and under which heading, so the author can see the boundary and move it by
//! > editing a heading.
//!
//! Without it the boundary is invisible until somebody trips over it. A rule
//! written under `## Notes` applies itself with nobody reading it; a heading
//! reworded from `## Rules` to `## Working guidance` takes every clause under it
//! out of the zone. Both are correct and both are surprises, and the remedy is
//! not a warning — it is showing the author where the line already falls.
//!
//! # A note, not a warning
//!
//! Nothing is wrong with a skill that holds five rules, or with one that holds
//! none. The count is a FACT about the document, and a fact printed as a problem
//! teaches an author to stop reading the output — which is the thing this
//! project can least afford, since every other line of it is one they must read.
//!
//! # The parse, and why it is the same one
//!
//! `learning.classify` reads this structure on the other side of the wall to
//! decide the class of a proposed EDIT; this reads it to SHOW the boundary. Two
//! purposes, one rule, and a second copy of a rule is what this project refuses
//! everywhere else — so `both_readings_of_the_shipped_policy_agree` holds the
//! number printed here against the number of clauses that side protects.
//!
//! Fences are taken out before anything is read. A `#` is a comment in half the
//! languages an author is likely to paste and a hyphen starts a list in YAML, so
//! a sample would otherwise both end the region and add rules to it.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;

/// Whether this heading line is one that makes what follows it a rule.
///
/// `# Policy`, `## Policy`, `# Rules`, `## Rules` and `# <name> policy`, at any
/// depth: an author who nests their rules one level further down has not stopped
/// writing rules. Matched on the whole line, so `## Rules of thumb` is not one —
/// the closed set is closed, and widening it by substring would make `## Notes`
/// normative the day somebody wrote `## Notes on policy`.
fn makes_rules(line: &str) -> bool {
    let t = line.trim_start().trim_start_matches('#').trim().to_ascii_lowercase();
    t == "policy" || t == "rules" || t.ends_with(" policy")
}

/// A numbered or bulleted line — what §8.3a rule 1 calls a clause.
fn is_a_clause(line: &str) -> bool {
    let t = line.trim_start();
    if t.starts_with("- ") || t.starts_with("* ") || t.starts_with("+ ") {
        return true;
    }
    let digits: String = t.chars().take_while(char::is_ascii_digit).collect();
    !digits.is_empty()
        && t[digits.len()..].starts_with(['.', ')'])
        && t[digits.len() + 1..].starts_with(' ')
}

/// How many written rules this body holds, and under which heading.
///
/// The heading reported is the LAST one that opened a region containing a
/// clause, because that is the line an author edits to move the boundary. A body
/// with rules under two such headings reports the one they would look at first.
fn rules_in(body: &str) -> Option<(usize, String)> {
    let mut inside: Option<String> = None;
    let mut fenced = false;
    let mut found = 0usize;
    let mut under = String::new();
    for line in body.lines() {
        let t = line.trim_start();
        if t.starts_with("```") || t.starts_with("~~~") {
            fenced = !fenced;
            continue;
        }
        if fenced {
            continue;
        }
        if t.starts_with('#') {
            inside = if makes_rules(t) { Some(t.trim().to_string()) } else { None };
            continue;
        }
        if let Some(heading) = &inside
            && is_a_clause(t)
        {
            found += 1;
            if under.is_empty() {
                under = heading.clone();
            }
        }
    }
    (found > 0).then_some((found, under))
}

/// Say, per skill, where its written rules are.
pub fn say_where_the_rules_are(root: &Node, diags: &mut Diagnostics) {
    let Some(skills) = root.get("skills").and_then(Node::as_map) else { return };
    for (name, skill) in skills {
        let Some(body) = skill.node.get("content").and_then(Node::as_str) else { continue };
        let Some((how_many, under)) = rules_in(body) else { continue };
        diags.push(Diagnostic::note(
            "loader/where-the-rules-are",
            skill.key_span.clone(),
            format!(
                "'{name}' holds {how_many} written rule{} under `{under}` — lines a person \
                 has to approve before they change, whoever or whatever proposes it.",
                if how_many == 1 { "" } else { "s" }
            ),
            format!(
                "Nothing to do. Move a rule out from under `{under}`, or reword that \
                 heading, and it stops being one — which is how you move this boundary."
            ),
        ));
    }
}
