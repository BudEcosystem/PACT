//! **A review nothing ever runs.**
//!
//! `learning.review:` is a `tier: core`, `S-GOV` setting with four choices, and
//! for a round it changed nothing anywhere. MEASURED before this module:
//! `grep -rn nothing-runs-the-review crates adapters` returned nothing, and the
//! shipped worked example — `review: weekly` in `learning.yaml` — printed
//! *"OK — examples/refund-desk loaded cleanly (…)"* and exited 0 whether or not
//! anything in the workspace could reach a Friday.
//!
//! The field's own help text is what makes this a promise rather than a
//! preference:
//!
//! > *how often proposed changes are shown to the team. Whatever runs your
//! > agents has to put this on somebody's calendar — a `port` with
//! > `kind: schedule` is how you write that down here.*
//!
//! So the file already names the mechanism. What it did not do is check that the
//! mechanism is there. `review: weekly` beside a workspace with no timer in it
//! means the improvements pile up and the first person to notice is whoever
//! wondered, some months later, why nothing had come to review — which is the
//! same shape as the dead timer `ports.rs` refuses, one level up: a promise
//! about the clock in a workspace the clock never reaches.
//!
//! # Why a warning and not an error
//!
//! `ports.rs` refuses, because nothing intends a timer that cannot fire. This
//! warns, for the reason `unnamed.rs` gives: it is a file written in the wrong
//! ORDER. `learning.yaml` and `ports/weekly-review.yaml` are two files by two
//! people, and writing the learning policy first — before anybody has decided
//! which agent summarises the week — is an ordinary way to get here. An error
//! would stop a half-written tree from loading at all; a warning says the thing
//! that is true and lets the work continue.
//!
//! # What counts as "there is a timer"
//!
//! Whatever [`crate::ports::kind_of`] calls a schedule, and nothing narrower. A
//! port carrying `every:` **is** a timer whether or not it says `kind:` —
//! `ports.rs` made that derivation normative so an author need not say it twice
//! — and a check here that looked for the literal words `kind: schedule` would
//! tell somebody who wrote a perfectly good `every: Friday at 4pm` that they had
//! no clock. One derivation, read from one place.
//!
//! # Why `review: manual` is left alone
//!
//! It is the one choice that does not name an interval. `daily`, `weekly` and
//! `monthly` are all statements about a clock; `manual` says out loud that a
//! person starts it, so there is no clock owed and nothing to be missing. That
//! also makes it the second fix below — a line an author can type that makes the
//! file true, rather than one that takes the capability away.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;

/// The `review:` answer that promises no clock: a person starts it by hand.
///
/// Read as "this one, and every other choice is an interval". Written this way
/// round on purpose — listing `daily`, `weekly`, `monthly` here would be a
/// second copy of the schema's `choices:` line, and a fifth interval added to
/// `spec/schema.yaml` would silently stop being checked.
const BY_HAND: &str = "manual";

/// The `learning.enabled:` answer where no improvement is ever proposed, so
/// there is nothing for a review to look at.
const OFF: &str = "off";

/// Say so when a workspace promises a review on a clock and has no clock.
///
/// Takes the loaded document and the specification. The specification is here
/// for one question — is the word written on `enabled:` one the schema offers? —
/// because a misspelling is already refused by name at the line the author
/// typed, and a second message about it here would offer a fix for a mistake
/// they did not make. Same argument `ports.rs` makes about a misspelt `kind:`.
pub fn check(document: &Node, schema: &pact_schema::Schema, diags: &mut Diagnostics) {
    let Some(learning) = document.get("learning") else { return };
    let Some(map) = learning.as_map() else { return };
    let Some(entry) = map.get("review") else { return };
    let Some(said) = entry.node.as_str().map(str::trim) else { return };
    if said.is_empty() || said.eq_ignore_ascii_case(BY_HAND) {
        return;
    }

    // Learning switched off proposes nothing, so there is nothing for a review
    // to be shown. Checked the same way `redaction.rs` checks it and against the
    // same word, so the two cannot come to disagree about what "off" is.
    let enabled = map.get("enabled").and_then(|e| e.node.as_str()).map(str::trim);
    if enabled.is_some_and(|w| w.eq_ignore_ascii_case(OFF)) {
        return;
    }
    // A word the specification does not offer is a typo, and `schema/not-one-of`
    // has already said so at the line the author typed, listing every choice. A
    // sentence here as well would be two messages about one mistake.
    let choices = words_the_specification_offers(schema, "learning", "enabled");
    if let Some(word) = enabled
        && !choices.is_empty()
        && !choices.iter().any(|c| c.eq_ignore_ascii_case(word))
    {
        return;
    }

    if has_a_timer(document) {
        return;
    }

    // The whole setting, key and value, because the sentence quotes the whole
    // setting back.
    let at = entry.key_span.clone().merge(&entry.node.span);
    diags.push(Diagnostic::warning(
        "loader/nothing-runs-the-review",
        at,
        // The interval is quoted back rather than turned into a phrase — `every
        // {said}` reads *"every weekly"*, which is the kind of sentence that
        // tells a reader the message was assembled rather than written.
        format!(
            "`review: {said}` says how often the team is shown what this system \
             wants to change about itself, and nothing in this workspace ever \
             starts that review — there is no port here that runs on a clock. The \
             proposals will pile up and nobody will be told."
        ),
        "Add a file `ports/weekly-review.yaml` with these lines in it:\n\
         \x20        description: Show the team what the agent wants to change.\n\
         \x20        kind: schedule\n\
         \x20        every: Friday at 4pm\n\
         \x20        answers: <the agent that writes the summary>\n\
         \x20        says: What has been proposed since last week?\n\
         Or write `review: manual` in `learning.yaml`, which says out loud that a \
         person starts the review by hand."
            .to_string(),
    ));
}

/// Whether anything under `ports/` runs on a clock.
///
/// **This is the line that reads the author's `ports/` folder.** Delete it and
/// the worked example — which ships `ports/weekly-review.yaml` beside
/// `review: weekly` — is warned about a timer it has.
fn has_a_timer(document: &Node) -> bool {
    let Some(ports) = document.get("ports").and_then(Node::as_map) else { return false };
    ports.iter().any(|(_, entry)| {
        // A file that did not parse says nothing about what is inside it, so it
        // is not counted as a timer and not counted as proof there is none —
        // `ports.rs` skips it for the same reason. Erring towards "no timer"
        // here would be a second message about an unclosed bracket.
        entry.node.get(pact_doc::UNLOADED).is_some()
            || crate::ports::kind_of(&entry.node).is_schedule()
    })
}

/// The words one `one-of:` field accepts, in the order the specification writes
/// them. Read off `spec/schema.yaml` through the schema the CLI already built,
/// never listed here — the same reader `ports.rs` uses, asked about a different
/// field.
fn words_the_specification_offers(
    schema: &pact_schema::Schema,
    group: &str,
    field: &str,
) -> Vec<String> {
    schema
        .group(group)
        .and_then(|g| g.fields.iter().find(|f| f.name == field))
        .map(|f| match &f.ty {
            pact_schema::Ty::OneOf(words) => words.clone(),
            _ => Vec::new(),
        })
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    /// The shape of the worked example: a learning policy that promises a weekly
    /// review, and a port that runs on a Friday.
    const WORKSPACE: &str = "
learning:
  enabled: propose-only
  review: weekly
ports:
  slack:
    description: Where customers reach us.
    kind: conversation
    through: slack
    answers: refund-desk
  weekly-review:
    description: Summarise the week's refund decisions.
    kind: schedule
    every: Friday at 4pm
    answers: refund-desk
    says: Summarise this week's refund decisions.
";

    /// The specification as it actually ships, not one built in this file — the
    /// argument `ports.rs` makes at the same place: a hand-built group would
    /// prove the reader works and say nothing about the real `choices:` line.
    fn spec() -> pact_schema::Schema {
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
        assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
        s
    }

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("workspace.yaml", text);
        check(&node, &spec(), &mut d);
        d
    }

    fn only(d: &Diagnostics) -> &Diagnostic {
        assert_eq!(d.items().len(), 1, "expected exactly one problem:\n{}", d.render());
        &d.items()[0]
    }

    #[test]
    fn a_workspace_that_promises_a_weekly_review_and_has_no_clock_is_told_so() {
        // The measured defect: `review: weekly` with nothing that can reach a
        // Friday printed one line of "loaded cleanly" and exited 0.
        let d = check_text(&WORKSPACE.replace("    kind: schedule\n", "").replace(
            "    every: Friday at 4pm\n",
            "",
        ));
        let e = only(&d);
        assert_eq!(e.rule, "loader/nothing-runs-the-review");
        assert_eq!(e.severity, pact_diag::Severity::Warning, "a half-written tree still loads");
        assert!(e.message.contains("review: weekly"), "quote the line: {}", e.message);
        assert!(e.message.contains("runs on a clock"), "say what is missing: {}", e.message);
    }

    #[test]
    fn the_fix_spells_out_the_port_file_to_create_and_the_lines_to_put_in_it() {
        // D13: a message with nowhere to go is not a diagnostic. Naming the file
        // and every line it needs is the difference between "somebody has to
        // schedule this" and something a support lead can type.
        let d = check_text(&WORKSPACE.replace("  weekly-review:\n", "  x-unused:\n").replace(
            "    kind: schedule\n",
            "    kind: conversation\n",
        ));
        let e = only(&d);
        assert!(e.fix.contains("ports/weekly-review.yaml"), "name the file: {}", e.fix);
        assert!(e.fix.contains("kind: schedule"), "name the line: {}", e.fix);
        assert!(e.fix.contains("every: Friday at 4pm"), "name the line: {}", e.fix);
        assert!(e.fix.contains("review: manual"), "offer the other way out: {}", e.fix);
    }

    #[test]
    fn a_workspace_with_a_timer_in_it_is_left_alone() {
        // The half that matters most, and the line that READS `ports/`: the
        // worked example's own shape must not be warned about.
        assert!(check_text(WORKSPACE).is_empty(), "{}", check_text(WORKSPACE).render());
    }

    #[test]
    fn a_timer_written_without_the_word_schedule_still_counts_as_one() {
        // `ports.rs` made `every:` on its own enough to be a timer, so an author
        // who took the advice and wrote one line instead of two must not be told
        // they have no clock.
        let d = check_text(&WORKSPACE.replace("    kind: schedule\n", ""));
        assert!(d.is_empty(), "`every:` is what makes a port a timer:\n{}", d.render());
    }

    #[test]
    fn saying_a_person_starts_the_review_by_hand_needs_no_clock() {
        // `manual` is the one choice that names no interval, so nothing is owed
        // and nothing is missing.
        let text = WORKSPACE
            .replace("    kind: schedule\n", "")
            .replace("    every: Friday at 4pm\n", "")
            .replace("review: weekly", "review: manual");
        assert!(check_text(&text).is_empty(), "{}", check_text(&text).render());
    }

    #[test]
    fn a_workspace_that_never_improves_itself_is_owed_no_review() {
        // `enabled: off` proposes nothing, so there is nothing for a review to
        // be shown and no clock to be missing.
        let text = WORKSPACE
            .replace("    kind: schedule\n", "")
            .replace("    every: Friday at 4pm\n", "")
            .replace("enabled: propose-only", "enabled: off");
        assert!(check_text(&text).is_empty(), "{}", check_text(&text).render());
    }

    #[test]
    fn a_workspace_with_no_learning_file_at_all_is_not_walked() {
        assert!(check_text("ports:\n  slack:\n    kind: conversation\n").is_empty());
        assert!(check_text("learning:\n  enabled: propose-only\n").is_empty());
    }

    #[test]
    fn a_misspelt_enabled_is_reported_once_by_the_check_that_knows_the_spelling() {
        // `enabled: propose only` is one typo. The schema refuses it at the line
        // the author typed and lists every word that works; a second sentence
        // here would send them to write a port file over a spelling mistake.
        let text = WORKSPACE
            .replace("    kind: schedule\n", "")
            .replace("    every: Friday at 4pm\n", "")
            .replace("enabled: propose-only", "enabled: propose only");
        assert!(check_text(&text).is_empty(), "one mistake gets one message:\n{}", check_text(&text).render());
    }

    #[test]
    fn a_port_file_that_did_not_parse_is_not_counted_as_proof_there_is_no_clock() {
        // One unclosed bracket already has a message. Telling the author their
        // review has no timer, when the file that would have been the timer is
        // the one nobody could read, is a second thing to fix for a fact nobody
        // knows.
        let text = format!(
            "learning:\n  enabled: propose-only\n  review: weekly\nports:\n  weekly-review:\n    {}: yes\n",
            pact_doc::UNLOADED
        );
        assert!(check_text(&text).is_empty(), "{}", check_text(&text).render());
    }

    #[test]
    fn the_words_this_check_compares_against_are_the_words_the_specification_declares() {
        // Not a list repeated here. `manual` and `off` are the two words this
        // module reads as "nothing is owed", and if either is renamed in
        // `spec/schema.yaml` this fails rather than silently starting to warn
        // about every workspace in the world.
        let intervals = words_the_specification_offers(&spec(), "learning", "review");
        assert!(
            intervals.iter().any(|w| w == BY_HAND),
            "'{BY_HAND}' is what this module reads as 'a person starts it', and the \
             specification no longer offers it: {intervals:?}"
        );
        assert!(intervals.len() >= 2, "`review:` offers no interval to promise: {intervals:?}");

        let states = words_the_specification_offers(&spec(), "learning", "enabled");
        assert!(
            states.iter().any(|w| w == OFF),
            "'{OFF}' is what this module reads as 'nothing is proposed', and the \
             specification no longer offers it: {states:?}"
        );
    }

    #[test]
    fn the_underline_covers_the_setting_the_sentence_quotes() {
        let text = WORKSPACE
            .replace("    kind: schedule\n", "")
            .replace("    every: Friday at 4pm\n", "");
        let rendered = check_text(&text).render();
        assert!(rendered.contains("  review: weekly"), "the line is shown:\n{rendered}");
        assert!(
            rendered.contains(&"^".repeat("review: weekly".len())),
            "the whole setting is underlined:\n{rendered}"
        );
    }
}
