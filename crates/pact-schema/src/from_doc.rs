//! Reading a [`Schema`] out of a PACT document.
//!
//! This is what makes "the schema is data, not code" true rather than
//! aspirational: `spec/schema.yaml` is loaded by the *same loader* that reads an
//! agent, so the specification expands across files by the same Expansion Rule,
//! and adding a field to PACT is a YAML edit rather than a Rust change (E-3).
//!
//! It also means the schema is subject to its own guarantees — spans, plain
//! diagnostics, deterministic ordering — which is a useful forcing function: if
//! the format is awkward for describing PACT, it is awkward for describing
//! anything.

use crate::sentences::{Form, Forms};
use crate::{Field, Group, Schema, Ty};
use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;

impl Schema {
    /// Build a schema from a loaded `spec/schema.yaml` document.
    ///
    /// Problems are reported into `diags` and the offending group or field is
    /// skipped, so a mistake in the specification surfaces as a readable error
    /// rather than a panic or a silently missing check.
    pub(crate) fn from_node(doc: &Node, diags: &mut Diagnostics) -> Schema {
        let mut schema = Schema::new();
        let Some(groups) = doc.get("groups").and_then(Node::as_map) else {
            diags.push(Diagnostic::error(
                "schema/no-groups",
                doc.span.clone(),
                "The specification has no 'groups' section, so nothing can be checked.",
                "Add a 'groups:' section, or a 'groups/' folder with one file per kind.",
            ));
            return schema;
        };

        for (name, entry) in groups {
            let g = &entry.node;
            let mut group = Group {
                name: name.clone(),
                describe: g
                    .get("describe")
                    .and_then(|n| n.as_str())
                    .map(str::to_string)
                    .unwrap_or_default(),
                fields: Vec::new(),
            };

            let Some(fields) = g.get("fields").and_then(Node::as_map) else {
                diags.push(Diagnostic::error(
                    "schema/group-without-fields",
                    g.span.clone(),
                    format!("The '{name}' kind lists no settings."),
                    "Add a 'fields:' section listing what this kind can have.",
                ));
                continue;
            };

            for (fname, fentry) in fields {
                let f = &fentry.node;
                // A field may be written as just its type (`name: text`) or as a
                // block. The short form is what makes the schema readable.
                let (ty_node, help, required, aliases) = match f.as_str() {
                    Some(s) => (s.to_string(), String::new(), false, Vec::new()),
                    None => (
                        f.get("type").and_then(|n| n.as_str()).unwrap_or("anything").to_string(),
                        f.get("help").and_then(|n| n.as_str()).unwrap_or("").to_string(),
                        f.get("required").and_then(as_bool).unwrap_or(false),
                        names(f, "aliases"),
                    ),
                };
                // The NAME of the setting, for the refusals that quote this
                // field inside a sentence about a different one. Optional, and
                // owed only where the first clause of the help will not do —
                // which `check_companions_can_be_quoted` decides below rather
                // than leaving it to whoever writes the next pair.
                let summary =
                    f.get("summary").and_then(|n| n.as_str()).unwrap_or("").trim().to_string();
                // A field that makes another one necessary says so here, so the
                // pairing is data like everything else (see `Field::needs_also`).
                let needs_also = names(f, "needs-also");
                // And the pairings that hold only for one value of this field.
                // Written `needed-when: {enough-is: enough-of-them}` — the field
                // that becomes necessary, and the value of THIS field that makes
                // it so. See `Field::needed_when`.
                let needed_when: Vec<(String, String)> = f
                    .get("needed-when")
                    .and_then(Node::as_map)
                    .map(|m| {
                        m.iter()
                            .filter_map(|(want, entry)| {
                                Some((want.clone(), entry.node.as_str()?.trim().to_string()))
                            })
                            .collect()
                    })
                    .unwrap_or_default();
                // And, for a closed choice that describes a CONDITION, what has
                // to be reachable for each value to hold. Written
                // `satisfied-by: {this-agent-has-procedures: skills}` — the
                // value of this field, and what the agent must be able to get
                // to. Read exactly the way `needed-when:` is, because it is the
                // same shape: a fact keyed by one value of one field. See
                // `Field::satisfied_by` for the four wrong table rows it
                // replaces.
                let satisfied_by: Vec<(String, String)> = f
                    .get("satisfied-by")
                    .and_then(Node::as_map)
                    .map(|m| {
                        m.iter()
                            .filter_map(|(value, entry)| {
                                Some((value.clone(), entry.node.as_str()?.trim().to_string()))
                            })
                            .collect()
                    })
                    .unwrap_or_default();
                // Which maps this field's value has to name, what it may say
                // instead, and the floor under a number. All three are data for
                // the same reason `needs-also` is: the alternative is one Rust
                // branch per reference, and the next reference then costs a
                // recompile rather than a line of YAML (F-1).
                // Whether a folder of prose is a way of writing this text. See
                // `Field::may_be_a_folder` for the twenty-two fields the old
                // type-only gate was forgiving by accident.
                let may_be_a_folder = f.get("may-be-a-folder").and_then(as_bool).unwrap_or(false);
                // Whether this field's value can name somewhere outside the
                // workspace. See `Field::reaches_outside`.
                let reaches_outside =
                    f.get("reaches-outside").and_then(as_bool).unwrap_or(false);
                // Exactly one of these, whenever this field is set. See
                // `Field::needs_one_of` for the rule `needs-also:` could not
                // state and the author it refused.
                let needs_one_of = names(f, "needs-one-of");
                // Carries an amount of money when what it compares is one. See
                // `Field::may_be_money`.
                let may_be_money = f.get("may-be-money").and_then(as_bool).unwrap_or(false);
                let names_in = names(f, "names");
                // And which maps the KEYS of a `map of ...` have to name. Read
                // exactly the way `names:` is, and by the same helper, because
                // it is the same question one level over — `agent.team` and
                // `teamwork.shares` are both maps whose keys are agent names,
                // and both were held against nothing at all.
                let key_names = names(f, "key-names");
                let or_one_of = names(f, "or-one-of");
                let at_least = f.get("at-least").and_then(as_int);

                let choices: Vec<String> = f
                    .get("choices")
                    .and_then(Node::as_list)
                    .map(|l| l.iter().filter_map(|n| n.as_str().map(str::to_string)).collect())
                    .unwrap_or_default();

                // The three closed lists behind an event address, in the order
                // they are written. Data for the same reason `choices` is: the
                // subject list grew by one entry this round, and that must stay
                // a line of YAML rather than a recompile (F-1).
                let parts: Vec<(String, Vec<String>)> = f
                    .get("parts")
                    .and_then(Node::as_map)
                    .map(|m| {
                        m.iter()
                            .map(|(name, entry)| (name.clone(), words(&entry.node)))
                            .collect()
                    })
                    .unwrap_or_default();
                // And which of the addresses those lists can spell are moments
                // this field is actually bound to. Data for the same reason
                // again, and per field rather than global: a watch observes
                // thirty moments and an interceptor runs at five, so one list
                // could only be wrong for one of them.
                let reaches = names(f, "reaches");
                // The closed answer-shape vocabulary, written the same way
                // `parts:` is — one entry per shape, with every spelling that
                // means it. Data because the Python side's `_SPELLINGS` is data
                // too, and two hand-kept copies in two languages are two things
                // to forget.
                let shapes: Vec<(String, Vec<String>)> = f
                    .get("shapes")
                    .and_then(Node::as_map)
                    .map(|m| {
                        m.iter()
                            .map(|(name, entry)| (name.clone(), words(&entry.node)))
                            .collect()
                    })
                    .unwrap_or_default();

                match parse_ty(&ty_node, &choices, &parts, &reaches, &shapes) {
                    Some(ty) => {
                        // A constraint that can never fire is the "loads and
                        // does nothing" failure the rest of this file exists to
                        // end — the same shape as `type: text` on an address, or
                        // `one-of` with no `choices:`. `key-names:` resolves the
                        // KEYS of a map, so on a field that holds no named
                        // entries it is inert, and a specification that says a
                        // thing is checked while nothing checks it is worse than
                        // one that says nothing.
                        if !key_names.is_empty() && !holds_named_entries(&ty) {
                            diags.push(Diagnostic::error(
                                "schema/key-names-without-keys",
                                fentry.key_span.clone(),
                                format!(
                                    "'{fname}' says its entries have to be named somewhere, \
                                     and it does not hold named entries."
                                ),
                                format!(
                                    "Give it `type: map of ...`, or remove the `key-names:` \
                                     line — it is {} and has no keys to check. This is a \
                                     problem with the specification itself, not with your \
                                     file. Please report it.",
                                    ty.describe()
                                ),
                            ));
                        }
                        let mut field = Field::new(fname.clone(), ty, help);
                        field.required = required;
                        field.summary = summary;
                        field.aliases = aliases;
                        field.needs_also = needs_also;
                        field.needed_when = needed_when;
                        field.satisfied_by = satisfied_by;
                        field.may_be_a_folder = may_be_a_folder;
                        field.reaches_outside = reaches_outside;
                        field.needs_one_of = needs_one_of;
                        field.may_be_money = may_be_money;
                        field.names = names_in;
                        field.key_names = key_names;
                        field.or_one_of = or_one_of;
                        field.at_least = at_least;
                        field.forms = forms(f);
                        // The powers a kind FIXES, where a sibling `may:` would
                        // be a required list with one thing to say. Data for the
                        // same reason `needs-also` is — see `Field::always_may`
                        // for what it stops the shared sentence list handing to
                        // `redaction.hide`.
                        field.always_may = names(f, "always-may");
                        group.fields.push(field);
                    }
                    None => diags.push(Diagnostic::error(
                        "schema/unknown-type",
                        fentry.key_span.clone(),
                        format!("'{ty_node}' is not a kind of value PACT knows about."),
                        format!("Use one of: {}.", TYPE_NAMES.join(", ")),
                    )),
                }
            }

            // Held after the whole group is built, because a `needed-when:`
            // partner is routinely written BELOW the field that demands it —
            // `waits-for:` names `enough-is:` twelve lines further down.
            check_companions_can_be_quoted(&group, fields, diags);
            schema = schema.with(group);
        }

        // Held after every group is built, because a `satisfied-by:` target
        // names the `agent` group or a workspace collection, and neither exists
        // yet while the group that carries the attribute is being read.
        check_satisfiers_name_something_real(&schema, diags);
        schema
    }
}

/// Every `satisfied-by:` target is a field an agent really has, or a collection
/// an agent can really reach.
///
/// This is the direction that was missing. The table this attribute replaces was
/// Rust, so nothing held it against the schema, and two of its three rows named
/// `skills` and `resources` as fields of the `agent` group — which has neither.
/// The result was a warning that could not be satisfied and whose offered fix
/// was refused when typed. A name in the specification has to be checked by the
/// specification, or it is a comment.
fn check_satisfiers_name_something_real(schema: &Schema, diags: &mut Diagnostics) {
    let agent_fields: Vec<&str> = schema
        .group("agent")
        .map(|g| g.fields.iter().map(|f| f.name.as_str()).collect())
        .unwrap_or_default();
    let collections: Vec<&str> = schema
        .group("workspace")
        .map(|g| {
            g.fields
                .iter()
                .filter(|f| matches!(&f.ty, crate::Ty::MapOf(inner) if matches!(inner.as_ref(), crate::Ty::Group(_))))
                .map(|f| f.name.as_str())
                .collect()
        })
        .unwrap_or_default();

    for group in schema.groups() {
        for field in &group.fields {
            for (value, target) in &field.satisfied_by {
                let accepts = match &field.ty {
                    crate::Ty::OneOf(v) => v.iter().any(|c| c == value),
                    crate::Ty::ListOf(inner) => {
                        matches!(inner.as_ref(), crate::Ty::OneOf(v) if v.iter().any(|c| c == value))
                    }
                    _ => false,
                };
                if !accepts {
                    diags.push(Diagnostic::error(
                        "schema/satisfier-for-no-such-choice",
                        pact_diag::Span::whole_file(camino::Utf8Path::new("spec/schema.yaml")),
                        format!(
                            "'{}.{}' says what satisfies '{value}', and '{value}' is not one of \
                             the values it accepts.",
                            group.name, field.name
                        ),
                        "This is a problem with the specification itself, not with your file. \
                         Please report it.",
                    ));
                }
                if !agent_fields.contains(&target.as_str())
                    && !collections.contains(&target.as_str())
                {
                    diags.push(Diagnostic::error(
                        "schema/satisfier-names-nothing",
                        pact_diag::Span::whole_file(camino::Utf8Path::new("spec/schema.yaml")),
                        format!(
                            "'{}.{}' says '{value}' is satisfied by '{target}', and an agent has \
                             no '{target}' and can reach no such collection.",
                            group.name, field.name
                        ),
                        "This is a problem with the specification itself, not with your file. \
                         Please report it.",
                    ));
                }
            }
        }
    }
}

/// Every `needed-when:` partner must be able to say what it IS, in one phrase.
///
/// The sentence that pairing produces drops the partner's description inside a
/// refusal about a different field — *"'waits-for' says 'enough-of-them', and
/// 'enough-is' is not set — so nothing says X"* — and X came from the first
/// clause of the partner's `help:`. Four of the ten pairs in the shipped
/// specification opened their help with the CONDITION rather than the thing, so
/// X was *"with `enough-of-them`"*, *"for a stage that does `ask-someone`"*, and
/// the sentence meant nothing.
///
/// Rewriting those four helps fixes the four. This is what stops the fifth: the
/// specification does not LOAD if a pair is added whose partner can produce
/// neither a `summary:` nor a usable first clause, so `pact check` refuses at
/// once with the line to type. It is the same shape as
/// `schema/key-names-without-keys` above — a rule about the specification
/// itself, addressed to whoever is editing it — because the alternative is a
/// sentence that reads as nonsense to an author who cannot tell that the tool,
/// and not their file, is the thing that is wrong.
fn check_companions_can_be_quoted(group: &Group, fields: &pact_doc::Map, diags: &mut Diagnostics) {
    for field in &group.fields {
        for (want, _) in &field.needed_when {
            // A partner that does not exist is already `schema/unknown-companion`
            // where the author is; saying it twice here helps nobody.
            let Some(other) = group.fields.iter().find(|x| &x.name == want) else { continue };
            let quoted = crate::summary::quotable(other);
            let Some(why) = crate::summary::why_not_quotable(&quoted) else { continue };
            // Point at the PARTNER's line, not at the field that names it: the
            // partner is where the missing `summary:` has to be typed.
            let Some(at) = fields.get(want).or_else(|| fields.get(&field.name)) else { continue };
            let at = at.key_span.clone();
            diags.push(Diagnostic::error(
                "schema/companion-cannot-be-named",
                at,
                format!(
                    "'{}' asks for '{want}' when it says '{}', and '{want}' has nothing a refusal \
                     can call it: {why}.",
                    field.name,
                    field.needed_when.iter().find(|(w, _)| w == want).map_or("", |(_, v)| v.as_str()),
                ),
                format!(
                    "Add a line under `{want}:` in spec/schema.yaml naming the setting in one \
                     phrase — `summary: which question to put to them` — or start its `help:` with \
                     what it is instead of when it applies. This is a problem with the \
                     specification itself, not with your file. Please report it."
                ),
            ));
        }
    }
}

const TYPE_NAMES: &[&str] = &[
    "text", "yes-no", "number", "integer", "duration", "money", "percent", "threshold",
    "size", "file-name", "answer-shape", "one-of", "event-address", "anything",
    "list of <type>", "map of <type>", "group:<name>",
];

/// `text`, `list of text`, `map of text`, `group:agent`, `one-of`, `event-address`.
fn parse_ty(
    s: &str,
    choices: &[String],
    parts: &[(String, Vec<String>)],
    reaches: &[String],
    shapes: &[(String, Vec<String>)],
) -> Option<Ty> {
    let s = s.trim();
    if let Some(inner) = s.strip_prefix("list of ") {
        return Some(Ty::ListOf(Box::new(parse_ty(inner, choices, parts, reaches, shapes)?)));
    }
    if let Some(inner) = s.strip_prefix("map of ") {
        return Some(Ty::MapOf(Box::new(parse_ty(inner, choices, parts, reaches, shapes)?)));
    }
    if let Some(name) = s.strip_prefix("group:") {
        return Some(Ty::Group(name.trim().to_string()));
    }
    Some(match s {
        "text" => Ty::Text,
        "yes-no" | "yes/no" | "boolean" => Ty::YesNo,
        "number" => Ty::Number,
        "integer" | "whole number" => Ty::Integer,
        "duration" | "time" => Ty::Duration,
        "money" => Ty::Money,
        "percent" | "percentage" => Ty::Percent,
        "threshold" | "comparison" => Ty::Threshold,
        "size" => Ty::Size,
        "file-name" => Ty::FileName,
        // Refused with no `shapes:` for the same reason `one-of` is refused with
        // no `choices:`: a closed vocabulary with nothing in it accepts
        // everything, which is the `type: text` it replaces wearing a better name.
        "answer-shape" => {
            if shapes.is_empty() {
                return None;
            }
            Ty::AnswerShape(shapes.to_vec())
        }
        "one-of" => {
            if choices.is_empty() {
                return None;
            }
            Ty::OneOf(choices.to_vec())
        }
        // Refused rather than defaulted when `parts:` is missing, exactly as
        // `one-of` without `choices` is: an address type that checks nothing is
        // the `type: text` this replaces, wearing a better name.
        "event-address" => {
            if parts.is_empty() || parts.iter().any(|(_, words)| words.is_empty()) {
                return None;
            }
            Ty::EventAddress(parts.to_vec(), reaches.to_vec())
        }
        "anything" => Ty::Anything,
        _ => return None,
    })
}

/// Whether a value of this type has author-chosen keys for `key-names:` to
/// resolve. A list of maps counts, since the validator walks into it.
fn holds_named_entries(ty: &Ty) -> bool {
    match ty {
        Ty::MapOf(_) => true,
        Ty::ListOf(inner) => holds_named_entries(inner),
        _ => false,
    }
}

/// The words of one position of an address. A single word is accepted where a
/// list was expected, for the same reason `names` accepts one.
fn words(n: &Node) -> Vec<String> {
    match n.as_list() {
        Some(l) => l.iter().filter_map(|x| x.as_str().map(str::to_string)).collect(),
        None => n.as_str().map(str::to_string).into_iter().collect(),
    }
}

/// The closed sentence vocabulary of a field, if it has one.
///
/// Read as data rather than compiled in, so adding a fifth sentence to
/// `interceptor.rules` is a YAML edit beside the help text that describes it —
/// which is the only way the two can be kept from drifting.
fn forms(f: &Node) -> Option<Forms> {
    let block = f.get("forms")?;
    let one_of = block.get("one-of").and_then(Node::as_list)?;
    Some(Forms {
        declares: block.get("declares").and_then(|n| n.as_str()).unwrap_or("").to_string(),
        binds: block.get("binds").and_then(|n| n.as_str()).unwrap_or("").to_string(),
        // The two hole vocabularies, read the same way `parts:` is. Without them
        // a sentence from the right form with a made-up thing in it — or a
        // misspelt tool name — matched and was accepted.
        recognises: block
            .get("recognises")
            .and_then(Node::as_map)
            .map(|m| m.iter().map(|(k, e)| (k.clone(), words(&e.node))).collect())
            .unwrap_or_default(),
        resolve: block
            .get("resolve")
            .and_then(Node::as_map)
            .map(|m| {
                m.iter()
                    .filter_map(|(k, e)| Some((k.clone(), e.node.as_str()?.to_string())))
                    .collect()
            })
            .unwrap_or_default(),
        one_of: one_of
            .iter()
            .filter_map(|entry| {
                Some(Form {
                    say: entry.get("say").and_then(|n| n.as_str())?.to_string(),
                    needs: entry
                        .get("needs")
                        .and_then(|n| n.as_str())
                        .unwrap_or("")
                        .to_string(),
                    at: entry.get("at").map(words).unwrap_or_default(),
                    // Read like `required:` is, so `continues: yes` in the
                    // specification is the whole of adding this to the next
                    // sentence that carries on from another one.
                    continues: entry.get("continues").and_then(as_bool).unwrap_or(false),
                })
            })
            .collect(),
    })
}

/// A list-of-names field on a field definition. A single name is accepted where
/// a list was expected, for the same reason the validator accepts it in an
/// agent file: being strict there teaches the author nothing.
fn names(f: &Node, key: &str) -> Vec<String> {
    match f.get(key) {
        Some(n) => match n.as_list() {
            Some(l) => l.iter().filter_map(|n| n.as_str().map(str::to_string)).collect(),
            None => n.as_str().map(str::to_string).into_iter().collect(),
        },
        None => Vec::new(),
    }
}

fn as_int(n: &Node) -> Option<i64> {
    crate::coerce::check(n, &Ty::Integer).and_then(|c| match c {
        crate::coerce::Coerced::Integer(i) => Some(i),
        _ => None,
    })
}

/// The schema is authored by a human too, so `yes` works here as it does
/// everywhere else.
fn as_bool(n: &Node) -> Option<bool> {
    crate::coerce::check(n, &Ty::YesNo).and_then(|c| match c {
        crate::coerce::Coerced::YesNo(b) => Some(b),
        _ => None,
    })
}

/// Convenience for tests and the CLI: build a schema from YAML text.
pub fn schema_from_yaml(text: &str, diags: &mut Diagnostics) -> Schema {
    let path = camino::Utf8Path::new("spec/schema.yaml");
    diags.add_source(path, text);
    match pact_doc::parse_yaml(text, path) {
        Ok(node) => Schema::from_node(&node, diags),
        Err(d) => {
            diags.push(*d);
            Schema::new()
        }
    }
}


#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    const SPEC: &str = r#"
groups:
  agent:
    fields:
      name:
        type: text
        required: yes
        help: what to call this agent
      description:
        type: text
        required: yes
        aliases: [does]
        help: one line on what it does
      instructions: text
      reasoning:
        type: one-of
        choices: [simple, careful, expert]
        help: how much thinking it needs
      finishes-within: duration
      uses: list of text
      team: map of text
      limits: group:limits
  limits:
    fields:
      cost-per-request-under: money
      measured-at: text
"#;

    fn build() -> (Schema, Diagnostics) {
        let mut d = Diagnostics::new();
        let s = schema_from_yaml(SPEC, &mut d);
        (s, d)
    }

    #[test]
    fn a_schema_written_as_yaml_loads_without_rust_changes() {
        let (s, d) = build();
        assert!(!d.has_errors(), "{}", d.render());
        let agent = s.group("agent").expect("agent kind exists");
        assert_eq!(agent.fields.len(), 8);
        assert!(s.group("limits").is_some());
    }

    #[test]
    fn the_short_and_long_field_forms_mean_the_same_thing() {
        let (s, _) = build();
        let agent = s.group("agent").unwrap();
        let short = agent.fields.iter().find(|f| f.name == "instructions").unwrap();
        let long = agent.fields.iter().find(|f| f.name == "name").unwrap();
        assert_eq!(short.ty, Ty::Text);
        assert_eq!(long.ty, Ty::Text);
        assert!(!short.required);
        assert!(long.required);
    }

    #[test]
    fn nested_types_parse() {
        let (s, _) = build();
        let agent = s.group("agent").unwrap();
        let by = |n: &str| agent.fields.iter().find(|f| f.name == n).unwrap().ty.clone();
        assert_eq!(by("uses"), Ty::ListOf(Box::new(Ty::Text)));
        assert_eq!(by("team"), Ty::MapOf(Box::new(Ty::Text)));
        assert_eq!(by("limits"), Ty::Group("limits".into()));
        assert_eq!(by("finishes-within"), Ty::Duration);
        assert_eq!(
            by("reasoning"),
            Ty::OneOf(vec!["simple".into(), "careful".into(), "expert".into()])
        );
    }

    #[test]
    fn the_data_driven_schema_validates_a_real_document() {
        let (s, _) = build();
        let doc = parse_yaml(
            "name: Refund Desk\ndescription: Decides refunds\nreasoning: careful\n\
             finishes-within: 30s\nlimits:\n  cost-per-request-under: 0.05 USD\n  measured-at: p95\n",
            camino::Utf8Path::new("agent.yaml"),
        )
        .unwrap();
        let mut d = Diagnostics::new();
        s.validate(&doc, "agent", &mut d);
        assert!(!d.has_errors(), "{}", d.render());
    }

    #[test]
    fn a_mistake_in_the_specification_is_reported_not_panicked_on() {
        let mut d = Diagnostics::new();
        let s = schema_from_yaml("groups:\n  agent:\n    fields:\n      x: sparkles\n", &mut d);
        assert!(d.items().iter().any(|i| i.rule == "schema/unknown-type"));
        // The rest of the schema still builds, so one bad line does not blind
        // the whole validator.
        assert!(s.group("agent").is_some());
    }

    #[test]
    fn one_of_without_choices_is_rejected() {
        let mut d = Diagnostics::new();
        schema_from_yaml("groups:\n  a:\n    fields:\n      x:\n        type: one-of\n", &mut d);
        assert!(d.items().iter().any(|i| i.rule == "schema/unknown-type"));
    }
}
