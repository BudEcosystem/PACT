//! One group, one name — in every sentence of one report.
//!
//! `spec/schema.yaml` lets a group carry a `describe:` line: the plain-language
//! phrase a diagnostic uses in place of the group's own key. Only ONE of the
//! three sentences that name a group ever read it. Measured on a copy of
//! `examples/refund-desk`, with `auth: { by-reference: ... }` in
//! `resources/zendesk-server.yaml` changed to a key the schema has never heard
//! of:
//!
//! ```text
//! error: A credential-reference must have a 'by-reference'.
//! error: 'vault-path' is not something a credential reference can have.
//! ```
//!
//! Two sentences about one line, calling one thing two things — and the first
//! of them shows the author `credential-reference`, which is a key in the
//! specification's own YAML and a word they have never seen. The same shape was
//! measured for `when-this` (*"When-this must have a 'tool'."* beside *"…not
//! something an approval rule can watch for"*) and for `call-order` (*"A
//! call-order must have a 'first'."* beside *"…not something a call-order rule
//! can have"*), where the leak is subtler and worse: `a call-order` is not a
//! word the author has never seen, it is a word they have seen meaning
//! something one syllable longer.
//!
//! Every check here runs against the **real `spec/schema.yaml`** — the same
//! bytes `pact-cli` embeds — and never against a `Group` built in this file. A
//! hand-built group would prove the helper works and say nothing about whether
//! the specification's own `describe:` lines reach it, which is the failure
//! this project keeps shipping: a field resolved from the document and read by
//! nobody. A group given a `describe:` tomorrow is a YAML edit, and it is held
//! to this bar on the day it is written without anybody editing this test.

use pact_diag::Diagnostics;
use pact_doc::parse_yaml;
use pact_schema::from_doc::schema_from_yaml;
use pact_schema::Schema;

/// The specification as it actually ships.
const SPEC: &str = include_str!("../../../spec/schema.yaml");

/// A key no kind has, so every block below draws the unknown-field sentence.
const STRANGER: &str = "not-a-real-setting";

fn spec() -> Schema {
    let mut d = Diagnostics::new();
    let s = schema_from_yaml(SPEC, &mut d);
    assert!(!d.has_errors(), "the shipped specification does not load:\n{}", d.render());
    s
}

/// Every group the specification declares, read off the file rather than listed
/// here, so a kind added later is covered without anybody editing this test.
fn group_names() -> Vec<String> {
    let node = parse_yaml(SPEC, camino::Utf8Path::new("spec/schema.yaml")).expect("parses");
    node.get("groups")
        .and_then(pact_doc::Node::as_map)
        .expect("the specification has groups")
        .keys()
        .cloned()
        .collect()
}

fn validated(yaml: &str, group: &str) -> Diagnostics {
    let node = parse_yaml(yaml, camino::Utf8Path::new("thing.yaml")).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source("thing.yaml", yaml);
    spec().validate(&node, group, &mut d);
    d
}

/// The three sentences a report can use to name one group, as the author sees
/// them.
///
/// Two documents, because the third sentence needs a block that is not a block
/// at all. `settings` draws the unknown-field sentence (a key nothing knows)
/// and one missing-field sentence per required setting; `wrong_shape` draws the
/// one that fires when the whole thing is a line of text.
struct Said {
    /// What follows *"'not-a-real-setting' is not "*, minus the full stop.
    unknown: Option<String>,
    /// What precedes *" must have "* — the subject of the sentence.
    subject: Option<String>,
    /// What sits between *"a set of "* and *" settings"*.
    shape: Option<String>,
    /// Every fix the two documents produced, verbatim.
    fixes: Vec<String>,
}

fn said_about(group: &str) -> Said {
    let settings = validated(&format!("{STRANGER}: x\n"), group);
    let wrong_shape = validated("a line of text where a block belongs\n", group);

    let find = |d: &Diagnostics, rule: &str| -> Option<String> {
        d.items().iter().find(|i| i.rule == rule).map(|i| i.message.clone())
    };

    let unknown = find(&settings, "schema/unknown-field").and_then(|m| {
        m.strip_prefix(&format!("'{STRANGER}' is not "))
            .map(|rest| rest.trim_end_matches('.').to_string())
    });
    let subject =
        find(&settings, "schema/missing-field").and_then(|m| m.split(" must have ").next().map(str::to_string));
    let shape = find(&wrong_shape, "schema/wrong-shape").and_then(|m| {
        let after = m.split_once("a set of ")?.1;
        after.split_once(" settings").map(|(noun, _)| noun.to_string())
    });

    let fixes = settings
        .items()
        .iter()
        .chain(wrong_shape.items().iter())
        .map(|i| i.fix.clone())
        .collect();

    Said { unknown, subject, shape, fixes }
}

/// A subject with its indefinite article taken off: `A credential reference` →
/// `credential reference`.
fn bare(subject: &str) -> String {
    let lower = subject.to_lowercase();
    for article in ["an ", "a ", "the "] {
        if let Some(rest) = lower.strip_prefix(article) {
            return rest.to_string();
        }
    }
    lower
}

#[test]
fn the_measured_report_calls_a_credential_reference_the_same_thing_three_times() {
    // The reported defect, in the exact words the author is shown. `auth:` on
    // an MCP server holds one of these, and it is the block a support lead
    // touches on their first day connecting a real system.
    let said = said_about("credential-reference");
    assert_eq!(
        said.unknown.as_deref(),
        Some("something a credential reference can have"),
        "the sentence that already honoured `describe:` must not move"
    );
    assert_eq!(
        said.subject.as_deref(),
        Some("A credential reference"),
        "the missing-setting sentence still shows the author a key out of the specification"
    );
    assert_eq!(
        said.shape.as_deref(),
        Some("credential reference"),
        "the wrong-shape sentence still shows the author a key out of the specification"
    );
}

#[test]
fn a_call_order_is_not_called_a_call_order_rule_in_one_sentence_and_a_call_order_in_the_next() {
    // The subtler half of the same defect. `credential-reference` leaks a word
    // the author has never seen; `call-order` leaks a word they HAVE seen,
    // meaning a slightly different thing — which is harder to notice and just
    // as much a second name for one group.
    let said = said_about("call-order");
    assert_eq!(said.unknown.as_deref(), Some("something a call-order rule can have"));
    assert_eq!(said.subject.as_deref(), Some("A call-order rule"));
    assert_eq!(said.shape.as_deref(), Some("call-order rule"));
}

#[test]
fn no_group_in_the_shipped_specification_is_given_two_names_by_one_report() {
    // The sweep the two named tests above are samples of. Every group, both
    // documents, held against each other rather than against a list written
    // here.
    for group in group_names() {
        let said = said_about(&group);
        let Some(unknown) = said.unknown.as_deref() else {
            panic!("'{group}' says nothing about a setting it has never heard of");
        };
        let Some(shape) = said.shape.as_deref() else {
            panic!("'{group}' says nothing about a block that is a line of text");
        };
        if let Some(subject) = said.subject.as_deref() {
            assert_eq!(
                bare(subject),
                shape,
                "'{group}' is \"{subject}\" when a setting is missing and \"{shape}\" when the \
                 block is the wrong shape"
            );
        }
        // ...and the sentence that already read `describe:` names it the same
        // way. Whole words, so `call-order` does not pass by sitting inside
        // `call-order rule`.
        assert!(
            unknown.split_whitespace().collect::<Vec<_>>().windows(shape.split_whitespace().count())
                .any(|w| w.join(" ") == shape),
            "'{group}' is \"{shape}\" in two sentences and \"{unknown}\" in the third"
        );
    }
}

#[test]
fn a_group_the_specification_describes_as_something_x_can_have_is_called_x_everywhere() {
    // The check that catches a name which is a PREFIX of the right one.
    // *"A call-order must have a 'first'."* passes every test above except this
    // one: `call-order` really does appear in `something a call-order rule can
    // have`, as the first two thirds of the noun. Demanding the verb come
    // straight after pins the whole noun phrase.
    for group in group_names() {
        let said = said_about(&group);
        let Some(unknown) = said.unknown.as_deref() else { continue };
        if !unknown.starts_with("something ") {
            // `outcome:` describes itself the other way round — *"an outcome a
            // stage can end in"* — where the group is the LEAD noun and `can`
            // belongs to the stage. Nothing is owed by that shape here.
            continue;
        }
        for name in [said.subject.as_deref().map(bare), said.shape.map(|s| bare(&s))]
            .into_iter()
            .flatten()
        {
            let full = unknown.split_once(" can ").map(|(owner, _)| bare(owner.trim_start_matches("something").trim()));
            assert_eq!(
                Some(name.clone()),
                full,
                "the specification says a {group} is \"{unknown}\", and a report calls it \
                 \"{name}\""
            );
        }
    }
}

#[test]
fn no_fix_ends_in_a_blank_line() {
    // Measured in the same report: the missing-setting fix quotes the field's
    // own `help:`, and a folded YAML scalar ends in a newline — so the author
    // was shown a blank line between the line they can type and the rule name
    // under it. Every other site that quotes `help:` already trims it; this one
    // was the exception.
    for group in group_names() {
        for fix in said_about(&group).fixes {
            assert_eq!(
                fix.trim_end(),
                fix,
                "a fix for '{group}' ends in blank space, which prints an empty line \
                 before `rule:`: {fix:?}"
            );
        }
    }
}
