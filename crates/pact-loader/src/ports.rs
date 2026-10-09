//! **A timer that can never fire, accepted in silence.**
//!
//! `port.kind:` was `required: yes` with four choices — `conversation`,
//! `schedule`, `inbound-call`, `event` — and exactly one of them did anything.
//! Measured on a copy of the worked example: change `ports/weekly-review.yaml`
//! from `kind: schedule` to `kind: event`, leave `every: Friday at 4pm`, `says:`
//! and `if-still-running: skip` exactly where they are, and `pact check` printed
//! *"OK — … loaded cleanly (492 settings)."* and exited 0. Three settings that
//! only a timer can carry, on a port that says it is not one, and nothing said a
//! word. The weekly summary would never have been written and the first person
//! to notice would have been whoever expected it on a Friday.
//!
//! Two things were wrong and only one of them is about `event`.
//!
//! # 1. `kind:` was asked for where the document already answers it
//!
//! A port carrying `every:` **is** a schedule. Nothing else it could be has an
//! `every:` line, so demanding `kind: schedule` beside it asked the author to
//! say twice what they had already said once — and, as every same-setting-twice
//! shape in this format does, it let the two copies disagree. So `kind:` is no
//! longer required: it is derived from `every:` where `every:` is there, and
//! written by the author for the cases nothing can derive (a conversation, a
//! system calling in, an event from elsewhere all look alike to this file).
//!
//! `kind:` stays **writable** on a timer too. Somebody who prefers to say it out
//! loud may, and `kind: schedule` beside `every:` agrees with the derivation and
//! is left alone.
//!
//! # 2. Settings that only work on a timer were accepted anywhere
//!
//! `every:`, `says:`, `in-time-zone:`, `if-missed:` and `per-row-of:` are the
//! clock's settings. Their own help text says *"on a timer"* and nothing held
//! them to it. On a port that is not a timer each one is a line the author
//! wrote, reviewed and believes in, that nothing will ever read.
//!
//! `if-still-running:` was one of them, and is not any more (02W §4, R44
//! reopened): every port can start a run about a case that is already open, and
//! its `same-conversation-when:` says which overlap counts, so the six choices
//! are read on every kind of port (`arrivals.rs` holds the key it needs).
//!
//! # Why the schema cannot state it
//!
//! The same shape `money.rs` and `approvals.rs` argue, one step smaller.
//! `needed-when:` runs in one direction only — *this field holding this value
//! makes that field necessary* — which is how `kind: schedule` already demands
//! `every:`. The question here is the other direction: does this field being
//! written make some **other** field's value wrong? Nothing a field can say
//! about itself reaches that, and the answer also depends on whether `kind:` was
//! written at all, which no single field can see.
//!
//! # An error, not a warning
//!
//! `money.rs` warns because an ungated spend can be genuinely intended. Nothing
//! intends a timer that cannot fire. There is no reading of `kind: event` beside
//! `every: Friday at 4pm` under which the author gets what the file says, so
//! this refuses.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;

/// The settings only a timer can carry, in the order they read in a file and in
/// the specification.
///
/// `every:` is first because it is the one that makes a port a timer, so it is
/// the line the fix offers to delete and the line the caret lands on.
const ONLY_A_TIMER: [&str; 5] = ["every", "says", "in-time-zone", "if-missed", "per-row-of"];

/// The word `kind:` uses for the clock. One place, so the derivation, the
/// comparison and the fix can never drift apart.
const SCHEDULE: &str = "schedule";

/// What kind of port this is, and how that was decided.
///
/// The three arms are three different things to say to an author, which is why
/// this is not an `Option<&str>`: a port that says it is an `event` and a port
/// that says nothing at all are wrong in different ways and get different fixes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Kind {
    /// The author wrote `kind:`. Their own spelling, and the whole setting's
    /// position so a diagnostic can point back at it.
    Written(String, Span),
    /// Nothing was written, and `every:` says this is the clock.
    DerivedSchedule,
    /// Nothing was written and nothing here derives it.
    Unsaid,
}

impl Kind {
    /// Is this port the clock — however that was decided?
    pub fn is_schedule(&self) -> bool {
        match self {
            Kind::Written(w, _) => w.eq_ignore_ascii_case(SCHEDULE),
            Kind::DerivedSchedule => true,
            Kind::Unsaid => false,
        }
    }
}

/// What kind of port this is: what the author wrote, or what the document
/// already says.
///
/// **This is the derivation.** `every:` present and `kind:` absent is a
/// schedule, and that answer is what lets `says:` and `if-still-running:` stand
/// beside it without a `kind:` line. Delete the `every:` arm below and the
/// worked example's own `ports/weekly-review.yaml`, with its `kind:` line taken
/// out, is refused.
pub fn kind_of(port: &Node) -> Kind {
    let map = port.as_map();
    if let Some(entry) = map.and_then(|m| m.get("kind"))
        && let Some(written) = entry.node.as_str().map(str::trim)
        && !written.is_empty()
    {
        return Kind::Written(
            written.to_string(),
            entry.key_span.clone().merge(&entry.node.span),
        );
    }
    // A port carrying `every:` IS a schedule. Nothing else has an `every:` line,
    // so there is nothing to be ambiguous about and nothing for the author to
    // repeat.
    match map.and_then(|m| m.get("every")) {
        Some(_) => Kind::DerivedSchedule,
        None => Kind::Unsaid,
    }
}

/// Refuse every port that carries the clock's settings without being the clock,
/// and every port that says nothing about how work arrives at all.
///
/// Takes the loaded document and the specification, and nothing else. The
/// specification is here so that the words `kind:` accepts are READ rather than
/// repeated: a fifth arrival added to `spec/schema.yaml` is a YAML edit, and a
/// list of them copied into this file would be the second copy that goes stale
/// (the same-setting-twice mistake this whole module is about, made by the
/// checker instead of the author).
pub fn check(document: &Node, schema: &pact_schema::Schema, diags: &mut Diagnostics) {
    let Some(ports) = document.get("ports").and_then(Node::as_map) else {
        return;
    };
    let choices = kinds_the_specification_offers(schema);

    for (name, entry) in ports {
        let port = &entry.node;
        // A file that did not parse says nothing about what is inside it, so
        // nothing about what is inside it is checked. `pact_doc::UNLOADED` is
        // the loader's placeholder and the schema reads it the same way; without
        // this, one unclosed bracket in a port would also be told it has not
        // said how work arrives.
        if port.get(pact_doc::UNLOADED).is_some() {
            continue;
        }
        let kind = kind_of(port);
        if kind.is_schedule() {
            continue;
        }
        // A `kind:` that is not one of the words at all is a misspelling, and
        // `schema/not-one-of` already reports it at the line the author typed
        // with every choice listed. Saying "…and this port says `kind: evnt`"
        // beside it would be a second message about one mistake, offering a fix
        // that is not the one to make. `money.rs` stays quiet about a misspelt
        // policy name for exactly this reason.
        if let Kind::Written(word, _) = &kind
            && !choices.is_empty()
            && !choices.iter().any(|c| c.eq_ignore_ascii_case(word))
        {
            continue;
        }

        // Every timer-only setting this port carries, in reading order. All of
        // them are named in one sentence rather than one diagnostic each: the
        // edit that fixes them is a single line, and three messages about one
        // edit is the pile-on `money.rs` collapses for the same reason.
        let written: Vec<(&str, &Span)> = ONLY_A_TIMER
            .iter()
            .filter_map(|f| port.as_map()?.get(*f).map(|e| (*f, &e.key_span)))
            .collect();

        let Some((lead, lead_at)) = written.first().copied() else {
            // No timer settings, and nothing says what this port is. Before
            // this, `kind:` was `required: yes` and the schema said so; the
            // derivation above is what took that away, so this is the half of
            // it that has to be given back — otherwise a port with no `kind:`
            // and no `every:` is a connection nothing knows how to open,
            // printed as clean.
            if kind == Kind::Unsaid {
                diags.push(Diagnostic::error(
                    "loader/nothing-says-how-work-arrives",
                    port.span.start_of_block(),
                    format!("Nothing in the port '{name}' says how work arrives at it."),
                    format!(
                        "Add a line: `kind: {}`{}. A port with an `every:` line is a \
                         timer already and needs no `kind:` line.",
                        choices.first().map(String::as_str).unwrap_or("..."),
                        if choices.len() > 1 {
                            format!(" — the choices are {}", choices.join(", "))
                        } else {
                            String::new()
                        }
                    ),
                ));
            }
            continue;
        };

        // The whole setting is underlined, key and value, because the sentence
        // quotes the whole setting.
        let at = lead_at.clone().merge(
            &port
                .as_map()
                .and_then(|m| m.get(lead))
                .map(|e| e.node.span.clone())
                .unwrap_or_else(|| lead_at.clone()),
        );

        let dead = and_list(&written.iter().map(|(f, _)| *f).collect::<Vec<_>>());
        let only_one = written.len() == 1;

        diags.push(match &kind {
            Kind::Written(word, kind_at) => {
                let fix = if only_one {
                    // The wording the fix has to have: two things to type, both
                    // of them a line already in front of the author.
                    format!(
                        "Change `kind: {word}` to `kind: {SCHEDULE}`, or delete the `{lead}:` line."
                    )
                } else {
                    format!(
                        "Change `kind: {word}` to `kind: {SCHEDULE}`, or delete the `{lead}:` \
                         line. {} only work on a timer too, so {} with it.",
                        and_list(&written.iter().skip(1).map(|(f, _)| *f).collect::<Vec<_>>()),
                        if written.len() == 2 {
                            "it goes"
                        } else {
                            "they go"
                        }
                    )
                };
                Diagnostic::error(
                    "loader/a-timer-that-cannot-fire",
                    at,
                    format!(
                        "{dead} only mean{} anything on a timer, and this port says \
                         `kind: {word}`, so the clock will never run it.",
                        if only_one { "s" } else { "" }
                    ),
                    fix,
                )
                .with_related(kind_at.clone(), "this says it is not a timer")
            }
            // `every:` would have derived it, so reaching here means `every:` is
            // not written: the author has said what the timer should do and
            // never said when. Telling them to change a `kind:` line they have
            // not got would be a fix nobody can type.
            _ => Diagnostic::error(
                "loader/a-timer-that-cannot-fire",
                at,
                format!(
                    "{dead} only mean{} anything on a timer, and nothing in the port \
                     '{name}' says it is one.",
                    if only_one { "s" } else { "" }
                ),
                format!(
                    "Add a line saying when to run — `every: Friday at 4pm` — which is \
                     what makes a port a timer. Or delete {dead}.",
                ),
            ),
        });
    }
}

/// The words `kind:` accepts, in the order the specification writes them.
///
/// Read off `spec/schema.yaml` through the schema the CLI already built, never
/// listed here. Both places this is used would otherwise be a copy of the
/// `choices:` line: the fix that offers an author the words, and the guard that
/// keeps quiet about a word the schema is already refusing.
fn kinds_the_specification_offers(schema: &pact_schema::Schema) -> Vec<String> {
    schema
        .group("port")
        .and_then(|g| g.fields.iter().find(|f| f.name == "kind"))
        .map(|f| match &f.ty {
            pact_schema::Ty::OneOf(words) => words.clone(),
            _ => Vec::new(),
        })
        .unwrap_or_default()
}

/// `` `a` ``, `` `a` and `b` ``, `` `a`, `b` and `c` `` — a list the way a
/// sentence carries one, each name in backticks the way every other name in
/// these diagnostics is.
fn and_list(names: &[&str]) -> String {
    let quoted: Vec<String> = names.iter().map(|n| format!("`{n}:`")).collect();
    match quoted.split_last() {
        None => String::new(),
        Some((last, [])) => last.clone(),
        Some((last, rest)) => format!("{} and {last}", rest.join(", ")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    /// The shape of the worked example's own `ports/` folder: one conversation,
    /// one system calling in, one timer.
    const WORKSPACE: &str = "
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
    if-still-running: skip
";

    /// The specification as it actually ships, not one built in this file.
    ///
    /// A hand-built `Group { name: "port" }` would prove the reader works and
    /// say nothing about whether the real `choices:` line reaches it — the same
    /// argument `diagnostics_read_as_english.rs` makes at the top of its file.
    fn spec() -> pact_schema::Schema {
        const SPEC: &str = include_str!("../../../spec/schema.yaml");
        let mut d = Diagnostics::new();
        let s = pact_schema::from_doc::schema_from_yaml(SPEC, &mut d);
        assert!(
            !d.has_errors(),
            "the shipped specification does not load:\n{}",
            d.render()
        );
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
        assert_eq!(
            d.items().len(),
            1,
            "expected exactly one problem:\n{}",
            d.render()
        );
        &d.items()[0]
    }

    #[test]
    fn a_timer_written_the_way_the_worked_example_writes_one_is_left_alone() {
        // The half that matters most: a correct tree must not be warned about.
        assert!(
            check_text(WORKSPACE).is_empty(),
            "{}",
            check_text(WORKSPACE).render()
        );
    }

    #[test]
    fn a_port_carrying_every_is_a_timer_whether_or_not_it_says_so() {
        // The derivation, on the smallest document that shows it: the `kind:`
        // line is gone and `every:`, `says:` and `if-still-running:` are all
        // still fine, because the document already answered what kind it is.
        let d = check_text(&WORKSPACE.replace("    kind: schedule\n", ""));
        assert!(
            d.is_empty(),
            "`every:` is what makes it a timer:\n{}",
            d.render()
        );
    }

    #[test]
    fn the_clocks_settings_on_a_port_that_says_it_is_something_else_are_refused() {
        // The measured defect, in one line: `kind: event` beside `every: Friday
        // at 4pm` loaded cleanly and the weekly summary would never have run.
        let d = check_text(&WORKSPACE.replace("kind: schedule", "kind: event"));
        let e = only(&d);
        assert_eq!(e.rule, "loader/a-timer-that-cannot-fire");
        assert_eq!(
            e.severity,
            pact_diag::Severity::Error,
            "nothing intends a dead timer"
        );
        assert!(
            e.message.contains("the clock will never run it"),
            "{}",
            e.message
        );
        assert!(
            e.fix.starts_with(
                "Change `kind: event` to `kind: schedule`, or delete the `every:` line."
            ),
            "the fix has to be two lines the author can type: {}",
            e.fix
        );
    }

    #[test]
    fn one_wrong_kind_is_one_message_and_it_names_every_line_that_stops_working() {
        // Three dead settings, one edit that fixes them. Three diagnostics would
        // be three things to read for one thing to do, and an author who deletes
        // only the line the caret is under gets told off again next run.
        let text = WORKSPACE
            .replace("kind: schedule", "kind: inbound-call")
            .replace(
                "    if-still-running: skip\n",
                "    if-still-running: skip\n    if-missed: skip\n",
            );
        let d = check_text(&text);
        let e = only(&d);
        for field in ["every:", "says:", "if-missed:"] {
            assert!(
                e.message.contains(field),
                "{field} is not named: {}",
                e.message
            );
        }
        assert!(
            e.fix
                .contains("`says:` and `if-missed:` only work on a timer too"),
            "{}",
            e.fix
        );
        assert_eq!(
            e.related.len(),
            1,
            "the `kind:` line is the other half of the story"
        );
    }

    #[test]
    fn what_an_arrival_does_while_a_run_is_open_is_read_on_every_kind_of_port() {
        // R44 reopened (02W §4): `if-still-running:` on a port that is not a
        // timer used to be one of the clock's dead lines. It is read on every
        // kind now, so it is no part of a timer that cannot fire.
        let text = WORKSPACE.replace(
            "    through: slack\n",
            "    through: slack\n    if-still-running: queue\n",
        );
        let d = check_text(&text);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn saying_what_a_timer_should_do_without_saying_when_is_refused() {
        // `says:` with no `every:` and no `kind:`: nothing derives a timer, so
        // the wording reaches nobody. The fix cannot mention changing a `kind:`
        // line, because there is not one to change.
        let text = WORKSPACE
            .replace("    kind: schedule\n", "")
            .replace("    every: Friday at 4pm\n", "");
        let said = check_text(&text);
        let e = only(&said);
        assert_eq!(e.rule, "loader/a-timer-that-cannot-fire");
        assert!(
            e.message
                .contains("nothing in the port 'weekly-review' says it is one"),
            "{}",
            e.message
        );
        assert!(
            e.fix.contains("`every: Friday at 4pm`"),
            "the fix names the line to add: {}",
            e.fix
        );
        assert!(
            !e.fix.contains("Change `kind:"),
            "there is no `kind:` line to change: {}",
            e.fix
        );
    }

    #[test]
    fn a_port_that_says_nothing_about_how_work_arrives_is_refused_with_the_choices() {
        // `kind:` stopped being required so that a timer need not say it twice.
        // This is the other half of that: where nothing derives it, it is still
        // owed, and the message offers all four words.
        let said = check_text(&WORKSPACE.replace("    kind: conversation\n", ""));
        let e = only(&said);
        assert_eq!(e.rule, "loader/nothing-says-how-work-arrives");
        assert!(e.message.contains("'slack'"), "{}", e.message);
        for choice in ["conversation", "schedule", "inbound-call", "event"] {
            assert!(
                e.fix.contains(choice),
                "the fix must offer '{choice}': {}",
                e.fix
            );
        }
    }

    #[test]
    fn writing_kind_schedule_beside_every_agrees_with_the_derivation_and_is_left_alone() {
        // Deriving a value must not make writing it an error. The worked example
        // writes both, and so may anybody who prefers to say it out loud.
        assert!(check_text(WORKSPACE).is_empty());
        let spelled = WORKSPACE.replace("kind: schedule", "kind: Schedule");
        assert!(
            check_text(&spelled).is_empty(),
            "the word is the word, whatever its case"
        );
    }

    #[test]
    fn the_underline_covers_the_setting_the_sentence_quotes() {
        let d = check_text(&WORKSPACE.replace("kind: schedule", "kind: event"));
        let rendered = d.render();
        assert!(
            rendered.contains("    every: Friday at 4pm"),
            "the line is shown:\n{rendered}"
        );
        assert!(
            rendered.contains(&"^".repeat("every: Friday at 4pm".len())),
            "the whole setting is underlined:\n{rendered}"
        );
    }

    #[test]
    fn a_port_file_that_did_not_parse_is_not_told_it_has_said_nothing() {
        // One mistake gets one message. The unclosed bracket is already
        // reported; adding "nothing says how work arrives" would be a second
        // thing to fix for a file whose contents nobody has read.
        let text = format!("ports:\n  slack:\n    {}: yes\n", pact_doc::UNLOADED);
        assert!(
            check_text(&text).is_empty(),
            "{}",
            check_text(&text).render()
        );
    }

    #[test]
    fn a_workspace_with_no_ports_at_all_is_not_walked() {
        assert!(check_text("agents:\n  desk:\n    description: x\n").is_empty());
    }

    #[test]
    fn the_words_this_check_offers_are_the_words_the_specification_declares() {
        // Not a list repeated here. If a fifth arrival is added to
        // `spec/schema.yaml` it appears in the fix with no Rust change, and the
        // word this file calls the clock has to stay one of them or the
        // derivation is naming something that no longer exists.
        let words = kinds_the_specification_offers(&spec());
        assert!(
            words.len() >= 2,
            "the specification offers no choices for `kind:`: {words:?}"
        );
        assert!(
            words.iter().any(|w| w == SCHEDULE),
            "'{SCHEDULE}' is what this module derives from an `every:` line, and the \
             specification no longer offers it: {words:?}"
        );
    }

    #[test]
    fn a_misspelt_kind_is_reported_once_by_the_check_that_knows_the_spelling() {
        // `kind: evnt` is one typo. The schema refuses it at the line the author
        // typed and lists every word that works; a second sentence here would
        // offer `kind: schedule` to somebody who meant `event`.
        let d = check_text(&WORKSPACE.replace("kind: schedule", "kind: evnt"));
        assert!(
            d.is_empty(),
            "one mistake gets one message:\n{}",
            d.render()
        );
    }
}
