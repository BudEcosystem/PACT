//! What a diagnostic is allowed to quote when it names another setting.
//!
//! One sentence in the validator drops a *second* field's description inside a
//! first field's refusal:
//!
//! ```text
//! error: 'waits-for' says 'enough-of-them', and 'enough-is' is not set —
//!        so nothing says with `enough-of-them`.
//! ```
//!
//! That is the whole defect. `help:` is written to be READ — it opens with the
//! condition under which the setting applies, because that is what a person
//! scanning a list of settings needs first — and the diagnostic needs a NAME for
//! the setting, which is a different string. Taking the first clause of the help
//! and hoping is what produced *"so nothing says with `enough-of-them`"*,
//! *"so nothing says for a stage that does `ask-someone`"*, and
//! *"so nothing says when to run — plain words like `weekday mornings at 9`"*.
//!
//! So the specification says both. `summary:` is the name — one noun phrase,
//! quotable — and `help:` is the explanation. Where a field has no `summary:`,
//! the first clause of its help is used, because most helps do open with the
//! thing and a second string per field would be a second thing to forget.
//!
//! The part that makes it more than a wording fix is [`why_not_quotable`]:
//! `from_doc` runs it over every `needed-when:` partner when the specification
//! LOADS, so a `summary:` is not something the next author may quietly omit. A
//! pair whose partner can produce neither a summary nor a usable first clause
//! **refuses the specification itself**, with the line to type. Without that,
//! this file is one more decoration: the sentence would be correct today and
//! rot on the next pair added, which is exactly how the four broken ones got in.
//!
//! Eve has no equivalent to check — its diagnostics artifact carries structured
//! codes and lets the consumer render them, so nobody there ever had to make one
//! English sentence out of two authored strings.

use crate::Field;

/// What the missing-companion sentence quotes for `field`: its `summary:` if it
/// has one, and otherwise the first clause of its `help:`.
///
/// The fallback is deliberate rather than a transitional measure. Six of the ten
/// `needed-when:` partners in the shipped specification open their help with the
/// thing the setting is — *"which question to put to them…"*, *"who it goes to
/// next…"* — and asking those six to repeat themselves in a `summary:` line is
/// two strings to keep in step for no gain. [`why_not_quotable`] is what decides
/// which case a field is in, at load time, so nobody has to judge it by eye.
pub fn quotable(field: &Field) -> String {
    let summary = field.summary.trim();
    if summary.is_empty() {
        first_clause(&field.help)
    } else {
        one_line(summary)
    }
}

/// The first clause of a field's help.
///
/// Breaks at any clause boundary, not only `.` and `,`. It used to take those
/// two alone, and `port.every`'s help — *"when to run — plain words like
/// `weekday mornings at 9`, or a cron line…"* — carried its example across the
/// dash into the diagnostic. A dash, a colon and a semicolon all end a clause in
/// the same way a comma does; treating them as ordinary letters was the whole
/// reason that one sentence read as it did.
pub fn first_clause(help: &str) -> String {
    let one_line = one_line(help);
    match one_line.find(BOUNDARY) {
        Some(i) => one_line[..i].trim_end().to_string(),
        None => one_line,
    }
}

/// The characters that end a clause. `—` and `–` are here because the schema is
/// written by people who use them, and `first_clause` is the only reader.
const BOUNDARY: &[char] = &['.', ',', ';', ':', '—', '–'];

fn one_line(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// A name for a setting is at most this many words. The longest one the shipped
/// specification produces is thirteen — *"which question to put to them when the
/// line above says ask-a-person"* — and the cap is over it rather than at it so
/// that a slightly longer honest clause is not made to write a `summary:` for
/// the sake of two words. Past this the sentence stops being a refusal somebody
/// can read and becomes a paragraph inside one.
const MOST_WORDS: usize = 16;

/// Openers a noun phrase cannot have.
///
/// The sentence being built is *"…so nothing says X."*, so X has to be something
/// that can follow `says`: a name (*"the deadline"*), or a question word
/// (*"which question to put to them"*, *"how long to wait"*, *"whether it moves
/// money"*). Every word below starts a *condition* or a *remark* instead —
/// *"with `enough-of-them`"*, *"for a stage that does `ask-someone`"*, *"These
/// change how it words things"* — and no spelling of the surrounding sentence
/// rescues it.
///
/// Question words are deliberately absent: `when to run` is a fine thing to say
/// nothing says, and `when the line above says ask-a-person` is not, and no list
/// of first words can tell those apart. What catches the second is the word cap
/// above and the clause boundaries in [`first_clause`], both of which are about
/// LENGTH rather than grammar — which is the honest tool for it.
const NEVER_OPENS_A_NAME: &[&str] = &[
    "for", "with", "without", "in", "on", "at", "by", "from", "as", "and", "but", "or", "so",
    "because", "unless", "until", "since", "while", "once", "after", "before", "during", "though",
    "although", "if", "this", "these", "those", "it", "they", "plus", "also",
];

/// Why this text cannot be dropped into *"…so nothing says X."*, in the words
/// the specification's author needs — or `None` if it can.
///
/// Returns the reason rather than a bool because the caller is a diagnostic and
/// "it is wrong" is not something anybody can act on.
pub fn why_not_quotable(text: &str) -> Option<String> {
    let text = one_line(text);
    if text.is_empty() {
        return Some("it is empty, so the sentence would stop after 'nothing says'".to_string());
    }
    let first = text
        .split_whitespace()
        .next()
        .unwrap_or_default()
        .trim_matches(|c: char| !c.is_alphanumeric())
        .to_lowercase();
    if NEVER_OPENS_A_NAME.contains(&first.as_str()) {
        return Some(format!(
            "it opens with '{first}', which starts a condition rather than a name — the sentence \
             would read \"nothing says {text}\""
        ));
    }
    let words = text.split_whitespace().count();
    if words > MOST_WORDS {
        return Some(format!(
            "it is {words} words, and a name for a setting is at most {MOST_WORDS} — the sentence \
             would read \"nothing says {text}\""
        ));
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_first_clause_stops_at_a_dash_as_it_does_at_a_comma() {
        // The `port.every` case, which is why the boundary set grew. A dash ends
        // a clause; reading past it dragged an example into a refusal.
        assert_eq!(
            first_clause("when to run — plain words like `weekday mornings at 9`, or a cron line"),
            "when to run"
        );
        assert_eq!(
            first_clause("who it goes to next, when the line above says escalate"),
            "who it goes to next"
        );
        assert_eq!(
            first_clause("how long they have. Once that time is up"),
            "how long they have"
        );
    }

    #[test]
    fn help_written_across_several_lines_becomes_one_line() {
        // The schema folds every help with `>`, so the string arrives with
        // newlines in it and a diagnostic must not.
        assert_eq!(
            first_clause("who it\n  goes to\n  next. And then"),
            "who it goes to next"
        );
    }

    #[test]
    fn a_condition_is_refused_as_a_name_for_a_setting() {
        for opener in [
            "with `enough-of-them`, how many good answers count as enough",
            "for a stage that does `ask-someone`, which question to put to them",
            "These change how it words things",
        ] {
            let clause = first_clause(opener);
            assert!(
                why_not_quotable(&clause).is_some(),
                "\"{clause}\" reads as a condition and was accepted as a name"
            );
        }
    }

    #[test]
    fn a_question_word_is_a_perfectly_good_name_for_a_setting() {
        for good in [
            "which question to put to them",
            "how long to wait before carrying on",
            "whether it moves money",
            "who it goes to next",
            "when the clock should start a run",
            "the deadline for an answer",
        ] {
            assert_eq!(
                why_not_quotable(good),
                None,
                "\"{good}\" should be quotable"
            );
        }
    }

    #[test]
    fn a_paragraph_is_refused_even_when_it_opens_correctly() {
        let long = "which of the many settings on this kind the person answering is expected to \
                    read before they decide anything at all";
        assert!(
            why_not_quotable(long).is_some(),
            "a paragraph is not a name"
        );
    }

    #[test]
    fn the_reason_a_name_is_refused_is_something_a_person_can_act_on() {
        let why = why_not_quotable("with `enough-of-them`").expect("refused");
        assert!(
            why.contains("'with'"),
            "must name the word that broke it: {why}"
        );
        assert!(
            why.contains("nothing says with"),
            "must show the sentence it would make: {why}"
        );
    }
}
