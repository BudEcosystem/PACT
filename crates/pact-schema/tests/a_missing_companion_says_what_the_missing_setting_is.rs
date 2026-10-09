//! A refusal that names a second setting has to say what that setting IS.
//!
//! `needed-when:` pairs two fields — *"`waits-for: enough-of-them` needs
//! `enough-is:`"* — and the refusal it produces quotes the second field's
//! description inside a sentence about the first:
//!
//! ```text
//! error: 'waits-for' says 'enough-of-them', and 'enough-is' is not set —
//!        so nothing says with `enough-of-them`.
//! error: 'does' says 'ask-someone', and 'asks' is not set —
//!        so nothing says for a stage that does `ask-someone`.
//! error: 'kind' says 'schedule', and 'every' is not set —
//!        so nothing says when to run — plain words like `weekday mornings at 9`.
//! ```
//!
//! All three shipped. The quoted string was the first clause of the partner's
//! `help:`, and a help is written for somebody scanning a list of settings, so
//! it opens with the CONDITION the setting applies under. Dropped into *"nothing
//! says …"* that condition is the value the reader already typed, handed back to
//! them as if it answered the question. The last one is worse than useless: it
//! hands back an example of the very line it is saying is absent.
//!
//! Two things fixed it and both are checked here.
//!
//! 1. `summary:` — a name for the setting, one noun phrase, read at
//!    `crates/pact-schema/src/lib.rs` where the sentence is built.
//! 2. The four helps whose first clause was a condition were rewritten to open
//!    with the thing, so the fallback used by the six pairs with no `summary:`
//!    is correct as well.
//!
//! **Everything here runs against the real `spec/schema.yaml`.** A `Field` built
//! in this file would prove `summary:` can be formatted into a sentence and say
//! nothing about whether the author's line reaches it — which is the failure
//! this project keeps shipping. The pairs are read off the specification too, so
//! an eleventh one cannot be added without somebody writing its sentence down
//! below and reading it.

use pact_diag::Diagnostics;
use pact_doc::{parse_yaml, Node};
use pact_schema::summary::first_clause;
use pact_schema::Schema;

/// The specification as it actually ships.
const SPEC: &str = include_str!("../../../spec/schema.yaml");

fn spec() -> Schema {
    let mut d = Diagnostics::new();
    let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
    assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
    s
}

/// One `needed-when:` pairing: the kind it is on, the field that carries it, the
/// value of that field which makes the pairing bite, and the field owed.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Pair {
    group: String,
    field: String,
    value: String,
    owed: String,
}

/// Every pairing in the specification, read off the file rather than listed.
fn pairs() -> Vec<Pair> {
    let doc = parse_yaml(SPEC, camino::Utf8Path::new("spec/schema.yaml")).expect("parses");
    let mut out = Vec::new();
    for (group, gentry) in doc.get("groups").and_then(Node::as_map).expect("groups:") {
        let Some(fields) = gentry.node.get("fields").and_then(Node::as_map) else { continue };
        for (field, fentry) in fields {
            let Some(when) = fentry.node.get("needed-when").and_then(Node::as_map) else {
                continue;
            };
            for (owed, ventry) in when {
                out.push(Pair {
                    group: group.clone(),
                    field: field.clone(),
                    value: ventry.node.as_str().expect("a value to match").trim().to_string(),
                    owed: owed.clone(),
                });
            }
        }
    }
    assert!(!out.is_empty(), "the specification has no `needed-when:` pairs — this test is blind");
    out
}

/// What an author is told when they write the line that owes a companion and
/// not the companion.
fn the_refusal(pair: &Pair) -> pact_diag::Diagnostic {
    // Quoted, so a value YAML would read as something other than text — `yes` on
    // `spends-money:` — still arrives as the word the author typed.
    let yaml = format!("{}: '{}'\n", pair.field, pair.value);
    let node = parse_yaml(&yaml, camino::Utf8Path::new("thing.yaml")).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source("thing.yaml", &yaml);
    spec().validate(&node, &pair.group, &mut d);
    d.items()
        .iter()
        .find(|i| i.rule == "schema/missing-companion" && i.message.contains(&pair.owed))
        .unwrap_or_else(|| {
            panic!(
                "`{}: {}` on {} owes `{}:` and nothing said so. What it did say:\n{}",
                pair.field,
                pair.value,
                pair.group,
                pair.owed,
                d.render()
            )
        })
        .clone()
}

/// The part of the sentence that comes from the other field: everything after
/// *"so nothing says "*, without the full stop.
fn what_nothing_says(message: &str) -> String {
    message
        .split_once("so nothing says ")
        .unwrap_or_else(|| panic!("the sentence changed shape and this test can no longer read it: {message}"))
        .1
        .trim_end_matches('.')
        .to_string()
}

/// Every pairing in the specification, with the phrase its refusal ends in.
///
/// A table rather than a rule, because "reads as English" is a judgement and the
/// point of writing it down is that a person made it. Adding a `needed-when:`
/// pair to `spec/schema.yaml` and not adding its sentence here fails
/// [`every_pairing_in_the_specification_has_a_sentence_somebody_has_read`], so
/// the judgement is made once per pair and cannot be skipped.
///
/// Read the right-hand column as *"…so nothing says X."* — that is the whole
/// test. Seven of these come from a `summary:`; the other three are the first
/// clause of the partner's own help, which already opens with the thing.
const SENTENCES: &[(&str, &str, &str)] = &[
    // The four `asks:` fields are one setting written in four places, so they
    // are named the same way in all four. Their help says "when the line above
    // says ask-a-person" — a direction for somebody reading the list, and the
    // author's own words handed back when a refusal quotes it.
    ("limits", "asks", "which question to put to them"),
    ("context-policy", "asks", "which question to put to them"),
    ("teamwork", "asks", "which question to put to them"),
    ("stage", "asks", "which question to put to them"),
    ("action", "same-request-key", "which argument makes two calls \"the same call\""),
    ("question", "escalates-to", "who it goes to next"),
    ("learning", "may-improve-on-its-own", "which safe changes it may make on its own"),
    // The help goes on to give an example of a cron line, and the sentence used
    // to give that example back as if it were the missing setting.
    ("port", "every", "when the clock should start a run"),
    // Was "with `enough-of-them`".
    ("teamwork", "enough-is", "how many good answers count as enough"),
    // Was "with `whoever-answers-in-time`".
    ("teamwork", "gives-up-after", "how long to wait before carrying on"),
    // A workflow's stage (02W §2.3): the line each `does:` cannot go without.
    ("stage", "call", "what this stage runs"),
    ("stage", "chooses-between", "which labels it can pick, and where each one leads"),
    ("stage", "over", "which list to go through"),
];

fn expected(pair: &Pair) -> Option<&'static str> {
    SENTENCES
        .iter()
        .find(|(g, f, _)| *g == pair.group && *f == pair.owed)
        .map(|(_, _, sentence)| *sentence)
}

/// The `summary:` and `help:` the specification carries for one field.
fn field_strings(group: &str, field: &str) -> (String, String) {
    let schema = spec();
    let g = schema.group(group).unwrap_or_else(|| panic!("no `{group}` kind"));
    let f = g
        .fields
        .iter()
        .find(|f| f.name == field)
        .unwrap_or_else(|| panic!("`{group}` has no `{field}` field"));
    (f.summary.clone(), f.help.clone())
}

#[test]
fn every_pairing_in_the_specification_ends_in_the_sentence_a_person_wrote_down() {
    // The guarantee, stated as the ten sentences an author can actually be
    // shown. Every one of them is produced by loading the shipped file, writing
    // one line, and reading what comes back.
    for pair in pairs() {
        let said = what_nothing_says(&the_refusal(&pair).message);
        let want = expected(&pair).unwrap_or_else(|| {
            panic!(
                "`{}.{}` owes `{}:` and no sentence for it is written down in this file",
                pair.group, pair.field, pair.owed
            )
        });
        assert_eq!(
            said, want,
            "`{}: {}` on {} now refuses with \"…so nothing says {said}.\" — read that sentence \
             aloud. If it is right, update this file; if it is not, the `summary:` or the `help:` \
             on `{}.{}` in spec/schema.yaml is what to change.",
            pair.field, pair.value, pair.group, pair.group, pair.owed
        );
    }
}

#[test]
fn every_pairing_in_the_specification_has_a_sentence_somebody_has_read() {
    // The half that makes the table above a guarantee rather than a snapshot.
    // Without it, an eleventh pair would be added, produce whatever its
    // partner's help happened to open with, and be tested by nothing.
    let missing: Vec<String> = pairs()
        .into_iter()
        .filter(|p| expected(p).is_none())
        .map(|p| format!("{}.{} owes {}", p.group, p.field, p.owed))
        .collect();
    assert!(
        missing.is_empty(),
        "these pairings in spec/schema.yaml have no sentence in SENTENCES above:\n  {}\nAdd each \
         one, with the words the refusal actually ends in, having read it as English first.",
        missing.join("\n  ")
    );
}

#[test]
fn the_settings_that_carry_a_summary_are_named_by_it_and_not_by_their_help() {
    // The reading line, proved from the author's side. Each of these has a
    // `summary:` that says something different from the first clause of its
    // `help:`, so the sentence can only be right if the specification's
    // `summary:` line is what reached it. Delete the `summary::quotable(other)`
    // call in `check_conditional_companions` and every assertion here fails.
    for pair in pairs() {
        let (summary, help) = field_strings(&pair.group, &pair.owed);
        if summary.is_empty() {
            continue;
        }
        let said = what_nothing_says(&the_refusal(&pair).message);
        assert_eq!(
            said, summary,
            "`{}.{}` carries `summary: {summary}` and the refusal says \"{said}\" instead",
            pair.group, pair.owed
        );
        assert_ne!(
            first_clause(&help),
            summary,
            "`{}.{}`'s summary and the first clause of its help say the same thing, so this test \
             cannot tell which one the sentence used. Make them differ or delete the `summary:`.",
            pair.group,
            pair.owed
        );
        assert_ne!(
            said,
            first_clause(&help),
            "`{}.{}` fell back to its help",
            pair.group,
            pair.owed
        );
    }
    let with_summary = pairs()
        .into_iter()
        .filter(|p| !field_strings(&p.group, &p.owed).0.is_empty())
        .count();
    assert_eq!(
        with_summary, 10,
        "seven of the ten pairings needed a `summary:` when this was written — `port.every`, \
         `teamwork.enough-is`, `teamwork.gives-up-after`, and the four `asks:` fields — and the \
         three a workflow's stage added (`call`, `chooses-between`, `over`) need one each. If \
         that count moved, the table above still holds; this line is here so a `summary:` \
         cannot be quietly deleted and replaced by a fallback that happens to read."
    );
}

#[test]
fn a_setting_with_no_summary_is_named_by_the_opening_of_its_own_help() {
    // The fallback, which is the case for six of the ten. It exists so that a
    // help already opening with the thing does not have to say it twice, and it
    // is only safe because `from_doc` refuses the specification where it would
    // not read — see `a_pairing_whose_partner_cannot_say_what_it_is_refuses_the_specification`.
    let pair = Pair {
        group: "question".into(),
        field: "if-nobody-answers".into(),
        value: "escalate".into(),
        owed: "escalates-to".into(),
    };
    let (summary, help) = field_strings(&pair.group, &pair.owed);
    assert!(summary.is_empty(), "`question.escalates-to` has gained a `summary:`; pick another field");
    assert_eq!(what_nothing_says(&the_refusal(&pair).message), first_clause(&help));
    assert_eq!(what_nothing_says(&the_refusal(&pair).message), "who it goes to next");
}

#[test]
fn a_pairing_whose_partner_cannot_say_what_it_is_refuses_the_specification() {
    // What the mechanism REFUSES, which is the difference between a wording fix
    // and a rule. The four broken sentences were not caught by any test; they
    // were caught by somebody reading a diagnostic. This makes the fifth one
    // fail at the moment it is written, in `pact check`, naming the line.
    let broken = "\
groups:
  teamwork:
    fields:
      waits-for:
        type: one-of
        choices: [everyone, enough-of-them]
        needed-when:
          enough-is: enough-of-them
        surface: S-TOPO
        tier: core
        help: how much of the team has to come back
      enough-is:
        type: integer
        surface: S-TOPO
        tier: core
        help: with `enough-of-them`, how many good answers count as enough
";
    let mut d = Diagnostics::new();
    pact_schema::from_doc::schema_from_yaml(broken, &mut d);
    let e = d
        .items()
        .iter()
        .find(|i| i.rule == "schema/companion-cannot-be-named")
        .unwrap_or_else(|| panic!("a partner that opens with a condition was accepted:\n{}", d.render()));
    assert!(
        e.message.contains("'with'"),
        "the refusal must name the word that broke the sentence: {}",
        e.message
    );
    assert!(
        e.message.contains("nothing says with `enough-of-them`"),
        "the refusal must show the sentence it would have produced: {}",
        e.message
    );
    assert!(e.fix.contains("summary:"), "the fix must be a line to type: {}", e.fix);
    assert!(
        e.fix.contains("spec/schema.yaml"),
        "the fix must name the file to type it in: {}",
        e.fix
    );
}

#[test]
fn the_specification_is_refused_when_a_partner_says_nothing_at_all() {
    // A `needed-when:` partner written in the short form — `enough-is: integer`
    // — carries no help, so the sentence would end *"so nothing says ."*. That
    // is the emptiest version of the same defect and it is worth its own arm,
    // because the opener check cannot see it.
    let broken = "\
groups:
  teamwork:
    fields:
      waits-for:
        type: text
        needed-when:
          enough-is: enough-of-them
        surface: S-TOPO
        tier: core
        help: how much of the team has to come back
      enough-is: integer
";
    let mut d = Diagnostics::new();
    pact_schema::from_doc::schema_from_yaml(broken, &mut d);
    let e = d
        .items()
        .iter()
        .find(|i| i.rule == "schema/companion-cannot-be-named")
        .unwrap_or_else(|| panic!("a partner with nothing to say was accepted:\n{}", d.render()));
    assert!(e.message.contains("empty"), "{}", e.message);
}

#[test]
fn no_refusal_in_the_shipped_specification_hands_back_the_line_the_author_already_wrote() {
    // The shape of all three original defects, checked directly rather than
    // through the table: the phrase must not be the condition, and must not
    // quote the value that caused the refusal.
    for pair in pairs() {
        let said = what_nothing_says(&the_refusal(&pair).message);
        assert!(
            !said.contains(&pair.value),
            "`{}: {}` on {} refuses with \"…so nothing says {said}.\", which repeats the value the \
             author just typed instead of naming what is missing",
            pair.field,
            pair.value,
            pair.group
        );
        // `when` is deliberately not on this list, and finding that out cost a
        // failing run: `when the clock should start a run` is a name and `when
        // the line above says ask-a-person` is a condition, and no list of first
        // words tells them apart. What separates them is the assertion above —
        // one repeats the author's own value and the other does not.
        for opener in ["for ", "with ", "so "] {
            assert!(
                !said.starts_with(opener),
                "`{}.{}` refuses with \"…so nothing says {said}.\" — that opens a condition, not a \
                 name for the setting",
                pair.group,
                pair.owed
            );
        }
        assert!(!said.contains('—') && !said.contains(';'), "an aside leaked into: {said}");
        assert!(said.split_whitespace().count() <= 16, "not a name, a paragraph: {said}");
    }
}

#[test]
fn the_refusal_still_offers_a_line_the_author_can_type() {
    // The half a reader acts on. The message was rewritten; the fix must not
    // have moved, and it still carries the FULL help — the name is for the
    // sentence, the explanation is for the person deciding what to write.
    for pair in pairs() {
        let e = the_refusal(&pair);
        assert!(
            e.fix.contains(&format!("`{}: ", pair.owed)),
            "`{}.{}`'s fix must be a line to type: {}",
            pair.group,
            pair.owed,
            e.fix
        );
        let (_, help) = field_strings(&pair.group, &pair.owed);
        let help = help.split_whitespace().collect::<Vec<_>>().join(" ");
        let fix = e.fix.split_whitespace().collect::<Vec<_>>().join(" ");
        assert!(
            fix.contains(&help),
            "`{}.{}`'s fix dropped the explanation the author needs to choose a value:\n{fix}",
            pair.group,
            pair.owed
        );
    }
}
