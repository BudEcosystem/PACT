//! **The one thing `redaction:` refuses.**
//!
//! Collapsing `redaction:`/`redactions:` into one field (R61) fixed a shape.
//! It did not, on its own, make the field do anything: what an author writes in
//! `redaction.yaml` was read by the checker, held to its sentence vocabulary,
//! and then consulted by nothing — the field existed, resolved, and refused
//! nothing. That is the exact failure the rest of this crate is written
//! against, so this module is the line that reads it.
//!
//! # The rule
//!
//! `25-ARCHITECTURE-DECISIONS.md` AD-88 already states it, and until this
//! module nothing implemented it:
//!
//! > `enabled: yes` + a non-local reflector + no redaction policy is a
//! > **load-time error**.
//!
//! AD-88 wrote the first condition as `enabled: yes`, which is the spelling
//! that value had at the time; the choice is named `applies-safe-changes-itself`
//! now, for what happens rather than for how keen it sounds. Same state.
//!
//! The three conditions, in the words an author actually types:
//!
//! 1. `learning.yaml` says `enabled: applies-safe-changes-itself` —
//!    improvements go live with nobody reading them first, so the improving
//!    cycle runs unattended;
//! 2. `workspace.yaml` says `allow-egress:` includes `reflector` — which is
//!    precisely the line that lets the model doing the improving live somewhere
//!    other than this machine (AD-88 rule 2: a non-local reflector binding is
//!    unusable without it);
//! 3. there is no `redaction.yaml`.
//!
//! §8.8 requirement 3 *mandates* that a learning cycle carry per-case failures
//! "with the error text", and failures are the customer's own words — the
//! ticket prose, the reason strings. So all three together are an export path
//! created by a default: the hardest content in the workspace leaves the box
//! with nothing anywhere saying what must be held back.
//!
//! # Why it is an error and not a warning
//!
//! `unnamed.rs` argues at length for warning rather than refusing, and the
//! argument is about a file written in the wrong ORDER — a policy that exists
//! before the agent that will name it. This is not that. Nothing is half
//! written here: every one of the three lines is deliberate, they are three
//! separate decisions by three plausible people, and the consequence of
//! guessing wrong is a customer's words on somebody else's machine. AD-88 says
//! load-time error, and a run that has already started is too late to say it.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;

/// The role in `allow-egress:` that lets the improving model live off this box.
const REFLECTOR: &str = "reflector";

/// The one `learning.enabled` choice where a change goes live with nobody
/// reading it first. `propose-only` puts every change in front of a person,
/// which is the review this rule would otherwise be duplicating, and `off`
/// never assembles a cycle at all.
const UNATTENDED: &str = "applies-safe-changes-itself";

/// Refuse a workspace that lets the improver talk outside the box while nothing
/// says what must never leave.
pub fn improving_with_nothing_held_back(document: &Node, diags: &mut Diagnostics) {
    if document.get("redaction").is_some() {
        return;
    }
    if document.get("learning").and_then(|l| l.get("enabled")).and_then(Node::as_str)
        != Some(UNATTENDED)
    {
        return;
    }
    let Some(roles) = document.get("allow-egress") else { return };
    let Some(entry) = roles
        .as_list()
        .and_then(|list| list.iter().find(|r| r.as_str() == Some(REFLECTOR)))
    else {
        return;
    };

    // Three ways out of the fix below, all three typeable, and the order is
    // deliberate: writing the file is the one that keeps the capability the
    // author asked for. A refusal that offers only "turn it off" is a refusal
    // that gets worked around.
    //
    // The second example line read `- the email address of a customer` for a
    // round, and that sentence no longer exists. `redaction.hide` and
    // `interceptor.rules` were two closed vocabularies for one act and were
    // merged into one (the `&the-hiding-sentences` anchor in
    // `spec/schema.yaml`); `the <name> of a customer` went with the merge,
    // because everything it could hide `anything that looks like <a thing>`
    // already hides and its `<name>` was open text nothing held it against
    // (`docs/50-NOT-COPIED.md` §6). So this refusal was telling a support lead
    // to type a line that the very next `pact check` refuses with
    // `schema/not-a-rule` — measured, in those words. A fix that does not
    // survive being followed is not a typeable fix, which is the whole standard
    // this diagnostic is written to, and it is why the test below holds every
    // sentence offered here against the shipped vocabulary rather than against
    // a copy of it.
    diags.push(Diagnostic::error(
        "loader/improving-with-nothing-held-back",
        entry.span.clone(),
        format!(
            "`allow-egress:` lets the model that improves this system live outside this box, \
             and `learning.yaml` says `enabled: {UNATTENDED}` — so it improves with nobody \
             reading the changes first, and the conversations it learns from are the ones \
             that went wrong, in the customer's own words. Nothing here says what must never \
             leave."
        ),
        "Write a file called `redaction.yaml` next to `workspace.yaml`, with a `hide:` line \
         under it saying what to keep in — for example:\n\
         \x20        hide:\n\
         \x20          - anything that looks like a card number\n\
         \x20          - anything that looks like an email address\n\
         Or write `enabled: propose-only` in `learning.yaml`, so every change comes to a person \
         first. Or take `reflector` out of `allow-egress:` in `workspace.yaml`, so the improving \
         stays on this machine."
            .to_string(),
    ));
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn check(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        improving_with_nothing_held_back(&node, &mut d);
        d
    }

    /// The three lines that together make the error, written out once so each
    /// test below can take one of them away.
    const ALL_THREE: &str = "\
allow-egress: [reflector]
learning:
  enabled: applies-safe-changes-itself
";

    #[test]
    fn a_system_that_improves_itself_off_this_machine_is_refused_without_a_redaction() {
        let d = check(ALL_THREE);
        let e = d.items().first().expect("all three lines together must be refused");
        assert_eq!(e.rule, "loader/improving-with-nothing-held-back");
        assert_eq!(e.severity, pact_diag::Severity::Error, "AD-88 says load-time error");
        assert!(e.fix.contains("redaction.yaml"), "name the file to write: {}", e.fix);
        assert!(e.fix.contains("hide:"), "name the line to put in it: {}", e.fix);
    }

    #[test]
    fn writing_the_redaction_file_is_what_clears_it() {
        // The whole point: this is the line that READS `redaction:`. A workspace
        // with the same three settings and a `redaction.yaml` beside them is
        // accepted, so the author's file is what changed the answer.
        let d = check(&format!("{ALL_THREE}redaction:\n  hide:\n    - anything that looks like a card number\n"));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_system_that_shows_every_change_to_a_person_first_is_left_alone() {
        // `propose-only` is the value the worked example ships and the one the
        // schema's own help calls "the normal answer". AD-88 names the other
        // one: a change nobody read is what makes the export path a default.
        let d = check("allow-egress: [reflector]\nlearning:\n  enabled: propose-only\n");
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn improving_on_this_machine_needs_no_redaction_to_load() {
        // Nothing leaves, so there is nothing to hold back. An air-gapped
        // workspace (D17) must not be made to write a file it has no use for.
        let d = check("allow-egress: []\nlearning:\n  enabled: applies-safe-changes-itself\n");
        assert!(d.is_empty(), "{}", d.render());
        let d = check("allow-egress: [llm]\nlearning:\n  enabled: applies-safe-changes-itself\n");
        assert!(d.is_empty(), "the improver is not the model doing the work: {}", d.render());
    }

    /// The specification as it actually ships, never one built in this file.
    ///
    /// A hand-written list of three sentences here would prove this test's own
    /// copy agrees with itself and say nothing about whether the words a support
    /// lead is told to type are words `pact check` accepts — which is the exact
    /// way the two hiding vocabularies drifted apart in the first place.
    fn spec() -> pact_schema::Schema {
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
        assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
        s
    }

    /// The `- …` lines the fix offers under its `hide:` example — the ones an
    /// author copies.
    fn the_lines_it_tells_you_to_type(fix: &str) -> Vec<String> {
        let mut out = Vec::new();
        let mut under_hide = false;
        for line in fix.lines() {
            let t = line.trim();
            if t == "hide:" {
                under_hide = true;
            } else if under_hide {
                match t.strip_prefix("- ") {
                    Some(sentence) => out.push(sentence.to_string()),
                    None => break,
                }
            }
        }
        out
    }

    #[test]
    fn every_sentence_this_refusal_offers_is_one_the_checker_then_accepts() {
        // The standard every diagnostic here is written to — name the file, the
        // line, what is wrong, and a fix that can be TYPED — with the last word
        // measured rather than asserted. Follow this fix exactly and the file you
        // wrote goes through the same `redaction.hide` check `pact check` runs.
        //
        // It did not, for a round. `redaction.hide` and `interceptor.rules` were
        // two closed vocabularies for one act; merging them (`&the-hiding-
        // sentences`) took `the <name> of a customer` out, and this fix went on
        // offering it — so the author's reward for doing as they were told was
        // `'the email address of a customer' is not a rule PACT knows how to
        // carry out`. Held against the shipped schema rather than a copy of the
        // sentences, because a copy is the failure, not the guard.
        let d = check(ALL_THREE);
        let e = d.items().first().expect("refused");
        let offered = the_lines_it_tells_you_to_type(&e.fix);
        assert!(!offered.is_empty(), "the fix must show lines to type:\n{}", e.fix);

        let written = format!(
            "description: What may never leave this workspace.\nhide:\n{}",
            offered.iter().map(|s| format!("  - {s}\n")).collect::<String>()
        );
        let node = parse_yaml(&written, camino::Utf8Path::new("redaction.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("redaction.yaml", &written);
        spec().validate(&node, "redaction", &mut d);
        assert!(
            !d.has_errors(),
            "a support lead who types what this refusal told them to type is refused \
             for it:\n{}\nthey were told:\n{}",
            d.render(),
            e.fix
        );
    }

    #[test]
    fn the_refusal_underlines_the_word_the_author_typed() {
        // `reflector` is the word somebody had to approve adding, so it is the
        // word to point at. A span on the whole file would make the message
        // true and the fix unfindable.
        let d = check(ALL_THREE);
        let e = d.items().first().expect("refused");
        assert_eq!(e.span.line, 1, "the `allow-egress:` line: {:?}", e.span);
    }
}
