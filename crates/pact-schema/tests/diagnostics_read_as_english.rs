//! The indefinite article in a diagnostic has to agree with the word after it.
//!
//! Two sentences in the validator are built from a name out of
//! `spec/schema.yaml`, and for six rounds both hard-coded the article:
//!
//! ```text
//! error: A agent needs a 'description'.
//! error: 'does' is not something a agent can have.
//! ```
//!
//! Five of the thirty-two group names begin with a vowel — `action`, `agent`,
//! `evals`, `interceptor`, `outcome` — so this fired on every occurrence, and
//! `agent` is the kind every workspace has. It is the **first sentence the D13
//! reader ever sees from the tool**, on the day they are already wrong about
//! something. "A agent" reads as carelessness at precisely the moment they are
//! deciding whether to trust what it tells them next.
//!
//! Two more shapes hid behind that one, both worse:
//!
//! - The *field* name in the same sentence takes an article too, so a question
//!   with no answer block was refused with *"A question needs a 'answer'."* —
//!   a defect §7 of the architecture draft names out loud and leaves open.
//! - `needs`, `evals`, `limits` and `settings` are plural, and `learning` and
//!   `teamwork` are uncountable. No spelling of an indefinite article works in
//!   front of any of them: `a evals` is not fixed by `an evals`. The worst of
//!   them read *"A needs needs a 'because'."*
//!
//! So the fix is not three corrected literals. It is one function that answers
//! "what article does this name take", used everywhere a name is dropped into a
//! sentence — and, because a plural subject takes no article, a verb that agrees
//! with `an agent` and with `evals` alike: `must have`, `can have`.
//!
//! Every check here runs against the **real `spec/schema.yaml`**, not a schema
//! built in this file. A hand-built `Group { name: "agent" }` would prove the
//! function works and say nothing about whether the specification's own names
//! reach it — and a group added to the schema tomorrow is a YAML edit that
//! nobody will remember to mirror here.

use pact_diag::Diagnostics;
use pact_doc::parse_yaml;
use pact_schema::from_doc::schema_from_yaml;
use pact_schema::Schema;

/// The specification as it actually ships — the same file `pact-cli` embeds.
const SPEC: &str = include_str!("../../../spec/schema.yaml");

fn spec() -> Schema {
    let mut d = Diagnostics::new();
    let s = schema_from_yaml(SPEC, &mut d);
    assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
    s
}

/// Every group the specification declares, in the order it declares them.
///
/// Read off the file rather than listed here, so a kind added later is held to
/// this bar without anybody editing this test.
fn group_names() -> Vec<String> {
    let node = parse_yaml(SPEC, camino::Utf8Path::new("spec/schema.yaml")).expect("parses");
    node.get("groups")
        .and_then(pact_doc::Node::as_map)
        .expect("the specification has groups")
        .keys()
        .cloned()
        .collect()
}

/// Validate a block against `group` and hand back what the author would be told.
///
/// The block carries one key that no kind has, which draws the unknown-field
/// sentence, and omits everything else, which draws one missing-field sentence
/// per required setting. Between them that is both sites, for every kind.
fn what_the_author_is_told(group: &str) -> Diagnostics {
    let yaml = "not-a-real-setting: x\n";
    let node = parse_yaml(yaml, camino::Utf8Path::new("thing.yaml")).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source("thing.yaml", yaml);
    spec().validate(&node, group, &mut d);
    d
}

fn messages(group: &str) -> Vec<String> {
    what_the_author_is_told(group)
        .items()
        .iter()
        .filter(|i| i.rule == "schema/missing-field" || i.rule == "schema/unknown-field")
        .map(|i| i.message.clone())
        .collect()
}

/// Each `a`/`an` in a sentence paired with the word it governs.
///
/// Quotes are stripped from the governed word because the sentences quote the
/// names they are talking about — `a 'description'` — and the article agrees
/// with the letter, not the punctuation.
fn articled_pairs(sentence: &str) -> Vec<(String, String)> {
    let words: Vec<&str> = sentence.split_whitespace().collect();
    words
        .windows(2)
        .filter_map(|pair| {
            let article = pair[0].trim_matches(|c: char| !c.is_alphanumeric()).to_lowercase();
            if article != "a" && article != "an" {
                return None;
            }
            let word = pair[1].trim_matches(|c: char| !c.is_alphanumeric() && c != '\'');
            Some((article, word.trim_matches('\'').to_lowercase()))
        })
        .collect()
}

/// A word no indefinite article may sit in front of. Plurals — never `'s`,
/// which is a possessive and singular — and the uncountable nouns the schema
/// uses as kind names.
fn takes_no_article(word: &str) -> bool {
    (word.ends_with('s') && !word.ends_with("ss") && !word.ends_with("'s"))
        || matches!(word, "learning" | "teamwork")
}

#[test]
fn a_group_name_starting_with_a_vowel_gets_the_right_article() {
    // The reported defect, on the kind every workspace has. Both sentences, in
    // the exact words the author is shown.
    let said = messages("agent");
    assert!(
        said.contains(&"An agent must have a 'description'.".to_string()),
        "the missing-field sentence still reads wrong: {said:?}"
    );
    assert!(
        said.contains(&"'not-a-real-setting' is not something an agent can have.".to_string()),
        "the unknown-field sentence still reads wrong: {said:?}"
    );
}

#[test]
fn every_vowel_initial_kind_in_the_shipped_specification_reads_correctly() {
    // `action`, `agent`, `evals`, `interceptor` and `outcome` today. Held
    // against the file rather than against this list, so the sixth one is
    // covered on the day it is written.
    for group in group_names() {
        for message in messages(&group) {
            for (article, word) in articled_pairs(&message) {
                let vowel = word.starts_with(['a', 'e', 'i', 'o', 'u']);
                assert_eq!(
                    article,
                    if vowel { "an" } else { "a" },
                    "'{group}' produces \"{message}\" — '{article} {word}' does not agree"
                );
            }
        }
    }
}

#[test]
fn a_plural_or_uncountable_kind_name_is_given_no_article_at_all() {
    // `an evals` is not a fix for `a evals`. The only spelling that works is
    // none, which is why the verbs around it had to become number-agnostic.
    for (group, expected) in [
        ("evals", "Evals must have a 'population'."),
        ("needs", "Needs must have a 'because'."),
        ("learning", "Learning must have an 'enabled'."),
        // `teamwork` has no required field to sample any more: `waits-for:`
        // stopped being one, because `agent.teamwork`'s own help says "Leave it
        // out and it waits for all of them" and demanding the line made an
        // author restate a default they already had. Its article is still
        // exercised, by the unknown-field sentence asserted below.
    ] {
        let said = messages(group);
        assert!(
            said.contains(&expected.to_string()),
            "'{group}' should say \"{expected}\", said: {said:?}"
        );
    }
    for (group, expected) in [
        ("evals", "'not-a-real-setting' is not something evals can have."),
        ("teamwork", "'not-a-real-setting' is not something teamwork can have."),
    ] {
        assert!(messages(group).contains(&expected.to_string()), "{:?}", messages(group));
    }
}

#[test]
fn nothing_in_the_shipped_specification_puts_an_article_before_a_plural() {
    // The sweep the two named tests above are samples of — including the
    // hand-written `describe:` sentences in `spec/schema.yaml`, which land in
    // the unknown-field message and are just as visible to the author.
    for group in group_names() {
        for message in messages(&group) {
            for (article, word) in articled_pairs(&message) {
                assert!(
                    !takes_no_article(&word),
                    "'{group}' produces \"{message}\" — nothing may be '{article} {word}'"
                );
            }
        }
    }
}

#[test]
fn a_vowel_initial_field_name_gets_the_right_article_too() {
    // The half the architecture draft names and leaves open: *"A question needs
    // a 'answer'."* Same sentence, same defect, second slot. `answer:`, `says:`
    // and `if-nobody-answers:` stopped being the schema's to require when a
    // question could be asked of the clock (02W §2.8: the loader requires them
    // where a person reads them), so the same two arms are walked on the
    // vowel-initial fields that are still required.
    for (group, expected) in [
        ("question", "A question must have an 'asked-of'."),
        ("reminder", "A reminder must have an 'at'."),
        // Vowel-initial *and* plural, so it takes no article at all.
        ("port", "A port must have 'answers'."),
        // And the ordinary case is untouched.
        ("question", "A question must have a 'description'."),
    ] {
        let said = messages(group);
        assert!(said.contains(&expected.to_string()), "expected \"{expected}\", got {said:?}");
    }
}

#[test]
fn the_fix_still_names_the_setting_and_stays_typeable() {
    // The message was rewritten; the half the author acts on must not have
    // moved. Every refusal still carries a line they can type (O7.3).
    let d = what_the_author_is_told("agent");
    let e = d
        .items()
        .iter()
        .find(|i| i.rule == "schema/missing-field" && i.message.contains("description"))
        .expect("an agent with no description is refused");
    assert!(e.fix.contains("description: ..."), "the fix must be typeable: {}", e.fix);
    assert!(!e.fix.trim().is_empty());
}
