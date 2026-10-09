//! `{use: <name>}` — one figure, written once, wherever it belongs.
//!
//! # Why this exists
//!
//! The worked example's approval threshold is written three times: `more-than:
//! 200 USD` in the gate, `200` inside the runaway-refund sentence, and again in
//! an eval case. Nothing in the format holds the three together, so a tree that
//! has had two of the three edits has a gate and a test that disagree about what
//! the business rule is — and `pact check` says nothing, because each line is
//! individually correct. That is the one class of mistake this format cannot
//! catch by reading a line, because the mistake is *between* lines.
//!
//! # What it does, exactly
//!
//! A workspace's `values:` holds named figures. Anywhere a scalar belongs, the
//! author may write the one-key map `{use: <name>}` instead, and this pass puts
//! the figure there.
//!
//! It runs **before** `derive::resolve` and long before the schema, and both of
//! those orderings are load-bearing:
//!
//! * before derivation, so a base and everything derived from it read the same
//!   figure — a value used inside a base has already become the figure by the
//!   time the base is copied, so there is no second resolution pass and no way
//!   for the two to disagree;
//! * before the schema, so a figure that lands where it does not belong is the
//!   ordinary [`schema/wrong-type`], reported at the line the author wrote
//!   `{use:}` on. Substitution is not an escape from validation; it is a step
//!   that happens before it.
//!
//! # And then it is gone
//!
//! `values:` is removed from the document once resolved — exactly what
//! `based-on:` does, for exactly the reason `derive.rs` gives. A tree that used
//! a value and a tree that wrote the figure out longhand are **the same
//! document**: same shape, same digest, same `pact show`. Nothing below the
//! loader — no adapter, no second port, no runtime, no `canonical.json`
//! consumer — ever learns that values exist. That is what makes this feature
//! free at every layer except the one an author types into.
//!
//! # Except what a run reads by name
//!
//! A value read by its name rather than put in place — `workspace.calendar:`,
//! a port's `per-row-of:`, a workflow's `values.<name>` binding (02W §2.0,
//! §2.12) — is read when a stage starts, so it stays: those entries, and only
//! those, are kept under `values:` for the schema to hold and a run to read.
//! A tree that reads nothing by name is the same document it always was. A
//! `shape: table` value is a list of rows in the named shape `rows-are:` gives,
//! each row held to it here, and a name read as a table must be one
//! (`loader/a-table-that-is-not-one`); a calendar's rows have a `date` part.
//!
//! # What it deliberately is not
//!
//! Not a variable. Nothing reads one back, nothing writes one during a run, and
//! there is no way to compute with one. After this pass there is no value in the
//! document at all — only the figure — so nothing downstream can branch on one,
//! and the arguments `docs/remediation/F1` and `F4` settle stay settled by
//! construction rather than by a rule somebody has to remember.

use std::collections::{BTreeMap, BTreeSet};

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Node, Value};
use pact_schema::{Schema, Ty};

/// The workspace field holding the figures.
const COLLECTION: &str = "values";
/// The one collection a figure may not reach.
///
/// `models:` is distribution data, and it is the one thing BOTH ports read
/// DIRECTLY rather than through the loaded document — `resolve.py` opens
/// `<workspace>/models/catalog.yaml` off disk with its own reader, because the
/// override layer is applied row by row (D8, §4.2). A figure written there would
/// be substituted here, making `pact check` pass, and not there, where the model
/// is actually bound. The whole claim of this pass is that a tree using figures
/// and a tree written longhand are one document for everything downstream, and
/// this is the one key where that would be false.
const READ_DIRECTLY: &str = "models";
/// The one key a use site carries.
const USE: &str = "use";

/// Whether a figure may stand where this type belongs.
///
/// SCALARS ONLY, and the exclusion is the point. `Ty::Anything` is the
/// specification saying *these keys are the author's own, read them verbatim* —
/// `case.with:`, `case.expect:`, `metric.with:`, `knowledge.documents:` and
/// `state.starts-as:` are all typed that way, and `metric.with:`'s own help is
/// the sharpest statement of the contract: "written exactly as its own
/// documentation names them. Nothing is renamed and nothing is filled in for
/// you". A word an author used as a key is not a reference because this feature
/// exists.
fn a_figure_can_stand_here(ty: &Ty) -> bool {
    matches!(
        ty,
        Ty::Text
            | Ty::YesNo
            | Ty::Number
            | Ty::Integer
            | Ty::Duration
            | Ty::Money
            | Ty::Percent
            | Ty::Threshold
            | Ty::Size
            | Ty::FileName
            | Ty::AnswerShape(_)
            | Ty::CombineRule(_)
            | Ty::Moment
            | Ty::Comparand
            | Ty::OneOf(_)
            | Ty::EventAddress(_, _)
    )
}

/// Resolve every `{use: <name>}` in the document, in place, then drop `values:`.
pub fn resolve(
    root: &mut Node,
    schema: &Schema,
    diags: &mut Diagnostics,
    recorded: &mut Vec<crate::report::Substitution>,
) {
    let Some(top) = root.as_map_mut() else { return };
    let by_name = read_by_name(top);
    if top.get(COLLECTION).is_none() {
        // The overwhelmingly common case, and it must cost nothing: a tree that
        // writes no values is not walked at all, so P1 cannot change the meaning
        // of a document that never opted in. A binding to a value is the one
        // thing to say: there is none for it to name. \
        no_such_value(&by_name, &BTreeMap::new(), diags);
        return;
    }

    let rows = Rows::of(top, schema);
    let figures = match figures_of(top, &rows, diags) {
        Some(f) => f,
        None => {
            // The definitions could not be read. Every use site would then draw
            // a second, misleading refusal naming a value that was never the
            // problem — `derive.rs` makes the same call for the same reason. \
            top.shift_remove(COLLECTION);
            return;
        }
    };

    // A TYPED walk from the workspace down, so a `{use:}` is only ever read as
    // one where the specification says a scalar belongs. Walking untyped meant
    // any map carrying the word `use` was a reference wherever it sat, which
    // hijacked the author's own data in every `anything`-typed slot — refusing
    // it when the name matched no figure, and silently REPLACING it when it did.
    let mut used: BTreeSet<String> = BTreeSet::new();
    let workspace = schema.group("workspace").cloned();
    for (key, entry) in top.iter_mut() {
        if key == COLLECTION {
            continue;
        }
        if key == READ_DIRECTLY {
            refuse_under_the_catalogue(&entry.node, diags, 0);
            continue;
        }
        let ty = workspace
            .as_ref()
            .and_then(|g| g.fields.iter().find(|f| f.name == *key || f.aliases.contains(key)))
            .map(|f| f.ty.clone());
        // A key the specification does not know is left alone: `x-` blocks
        // round-trip untouched (AD-14), and an unknown field is the schema's
        // refusal to make, not this pass's. \
        if let Some(ty) = ty {
            substitute(
                &mut entry.node, &ty, schema, &figures, &mut used, diags, recorded, 0,
            );
        }
    }

    // What a run reads by name: a binding to nothing is refused, a name read as
    // a table must be one, and every such value that holds is kept.
    no_such_value(&by_name, &figures, diags);
    let mut kept: BTreeSet<String> = BTreeSet::new();
    if let Some(defs) = top.get(COLLECTION).and_then(|e| e.node.as_map()) {
        for read in &by_name {
            let (Some(entry), Some(_)) = (defs.get(&read.name), figures.get(&read.name)) else {
                continue;
            };
            used.insert(read.name.clone());
            if read.via != Via::Binding && !a_table_where_one_is_read(read, entry, &rows, diags) {
                continue;
            }
            kept.insert(read.name.clone());
        }
    }

    // A figure nothing reads. The generic `nothing-points-at-it` check cannot
    // say this: by the time it runs every `{use:}` has become a figure and the
    // reference is gone, so the pass that did the substituting is the only thing
    // that ever knows.
    if let Some(defs) = top.get(COLLECTION).and_then(|e| e.node.as_map()) {
        for (name, entry) in defs {
            if used.contains(name.as_str()) {
                continue;
            }
            diags.push(Diagnostic::warning(
                "loader/nothing-uses-this-value",
                entry.key_span.clone(),
                format!(
                    "'{name}' is a figure nothing here uses, so changing it changes \
                     nothing — the file loads, and no line reads it."
                ),
                format!(
                    "Write `{{use: {name}}}` where the figure belongs, or delete it."
                ),
            ));
        }
    }

    match top.get_mut(COLLECTION).and_then(|e| e.node.as_map_mut()) {
        Some(defs) if !kept.is_empty() => {
            defs.retain(|name, _| kept.contains(name));
            for (name, entry) in defs.iter_mut() {
                // The figure as resolved, so a kept value read by a run is the
                // same figure a `{use:}` of it would have put in place.
                if let (Some(map), Some(figure)) = (entry.node.as_map_mut(), figures.get(name))
                    && let Some(held) = map.get_mut("value")
                {
                    held.node = figure.clone();
                }
            }
        }
        _ => {
            top.shift_remove(COLLECTION);
        }
    }
}

/// How a run reads a value by its name.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Via {
    /// `workspace.calendar:`, a table of days off.
    Calendar,
    /// A port's `per-row-of:`, a table with one run per row.
    PerRow,
    /// `values.<name>` in a workflow.
    Binding,
}

/// One place a value is read by its name.
struct ReadByName {
    name: String,
    at: pact_diag::Span,
    via: Via,
}

/// Every place this tree reads a value by name rather than through `{use:}`.
fn read_by_name(top: &pact_doc::Map) -> Vec<ReadByName> {
    let mut out = Vec::new();
    if let Some(e) = top.get("calendar")
        && let Some(name) = e.node.as_str()
    {
        out.push(ReadByName {
            name: name.trim().to_string(),
            at: e.node.span.clone(),
            via: Via::Calendar,
        });
    }
    for (_, port) in top
        .get("ports")
        .and_then(|e| e.node.as_map())
        .into_iter()
        .flatten()
    {
        if let Some(n) = port.node.get("per-row-of")
            && let Some(name) = n.as_str()
        {
            out.push(ReadByName {
                name: name.trim().to_string(),
                at: n.span.clone(),
                via: Via::PerRow,
            });
        }
    }
    fn walk(node: &Node, out: &mut Vec<ReadByName>, depth: usize) {
        if depth > 32 {
            return;
        }
        match &node.value {
            Value::Str(s) => {
                let s = s.trim();
                if let Some(rest) = s.strip_prefix("values.")
                    && !s.contains(char::is_whitespace)
                {
                    let name = rest.split('.').next().unwrap_or("").to_string();
                    out.push(ReadByName {
                        name,
                        at: node.span.clone(),
                        via: Via::Binding,
                    });
                }
            }
            Value::Map(m) => m.values().for_each(|e| walk(&e.node, out, depth + 1)),
            Value::List(items) => items.iter().for_each(|i| walk(i, out, depth + 1)),
            _ => {}
        }
    }
    if let Some(e) = top.get("workflows") {
        walk(&e.node, &mut out, 0);
    }
    out
}

/// WF-4 for `values.<name>`: a binding to a value this workspace does not have.
fn no_such_value(read: &[ReadByName], figures: &BTreeMap<String, Node>, diags: &mut Diagnostics) {
    let names: Vec<&str> = figures.keys().map(String::as_str).collect();
    for r in read
        .iter()
        .filter(|r| r.via == Via::Binding && !figures.contains_key(&r.name))
    {
        diags.push(Diagnostic::error(
            "loader/a-binding-to-nothing",
            r.at.clone(),
            format!(
                "`values.{}` names no value: this workspace has no figure called '{}'.",
                r.name, r.name
            ),
            if names.is_empty() {
                format!("Write it in `values/{}.yaml`.", r.name)
            } else {
                format!(
                    "Use one of the names offered: {} — or write it in `values/{}.yaml`.",
                    pact_schema::suggest::nearest(&r.name, &names, 3)
                        .iter()
                        .map(|n| format!("`values.{n}`"))
                        .collect::<Vec<_>>()
                        .join(", "),
                    r.name
                )
            },
        ));
    }
}

/// A name read as a table (`calendar:`, `per-row-of:`) names one, and a
/// calendar's rows say which day each is.
fn a_table_where_one_is_read(
    read: &ReadByName,
    entry: &pact_doc::Entry,
    rows: &Rows,
    diags: &mut Diagnostics,
) -> bool {
    let line = if read.via == Via::Calendar {
        "calendar"
    } else {
        "per-row-of"
    };
    let name = &read.name;
    if entry
        .node
        .get("shape")
        .and_then(Node::as_str)
        .map(str::trim)
        != Some(TABLE)
    {
        diags.push(
            Diagnostic::error(
                "loader/a-table-that-is-not-one",
                read.at.clone(),
                format!("`{line}: {name}` reads a table, and '{name}' is not one: it has no `shape: table`."),
                format!(
                    "Make '{name}' a table — `shape: table`, `rows-are: <a shape>` and one row per                      line under `value:` — or name a table here."
                ),
            )
            .with_related(entry.key_span.clone(), "this is the value it names"),
        );
        return false;
    }
    if read.via == Via::Calendar {
        let shape = entry
            .node
            .get("rows-are")
            .and_then(Node::as_str)
            .map(str::trim)
            .unwrap_or("");
        let dated = rows
            .parts
            .get(shape)
            .is_some_and(|parts| parts.iter().any(|(_, l)| rows.plain(l) == Some("date")));
        if !dated {
            diags.push(Diagnostic::error(
                "loader/a-table-that-is-not-one",
                read.at.clone(),
                format!(
                    "`calendar: {name}` lists the days off that `business-days` skips, and the                      rows of '{name}' ('{shape}') have no part that is a date, so no row says                      which day it is."
                ),
                format!("Give '{shape}' a part in shape `date` — `day: date`."),
            ));
            return false;
        }
    }
    true
}

/// The named shapes a table's rows may be, read as `bindings.rs` reads them.
struct Rows {
    vocabulary: Vec<(String, Vec<String>)>,
    /// Each named shape's parts, as written.
    parts: BTreeMap<String, Vec<(String, String)>>,
}

impl Rows {
    fn of(top: &pact_doc::Map, schema: &Schema) -> Rows {
        let mut parts = BTreeMap::new();
        for (name, e) in top
            .get("shapes")
            .and_then(|e| e.node.as_map())
            .into_iter()
            .flatten()
        {
            let lines = e
                .node
                .as_map()
                .into_iter()
                .flatten()
                .filter_map(|(k, v)| v.node.as_str().map(|s| (k.clone(), s.to_string())))
                .collect();
            parts.insert(name.clone(), lines);
        }
        Rows {
            vocabulary: pact_schema::shape::vocabulary(schema),
            parts,
        }
    }

    fn line(&self, written: &str) -> Option<pact_schema::shape::Line> {
        let named: Vec<&str> = self.parts.keys().map(String::as_str).collect();
        pact_schema::shape::parse(written, &self.vocabulary, &named).ok()
    }

    /// The vocabulary's name for a plain line (`date`, `money`), else `None`.
    fn plain(&self, written: &str) -> Option<&'static str> {
        match self.line(written)?.shape {
            pact_schema::shape::Shape::Plain(n) => [
                "text",
                "yes-or-no",
                "money",
                "number",
                "whole-number",
                "date",
                "time",
                "date-and-time",
            ]
            .into_iter()
            .find(|w| *w == n),
            _ => None,
        }
    }

    /// Why `cell` does not fit `written`, or `None` when it does (or when
    /// nothing here can tell).
    fn misfit(&self, cell: &Node, written: &str) -> Option<String> {
        use pact_schema::shape::Shape;
        let line = self.line(written)?;
        let ty = match &line.shape {
            Shape::OneOf(choices) => {
                let said = match &cell.value {
                    Value::Str(s) => s.trim().to_string(),
                    _ => return Some(format!("is not one of {}", choices.join(", "))),
                };
                return (!choices.iter().any(|c| c.eq_ignore_ascii_case(&said)))
                    .then(|| format!("is not one of {}", choices.join(", ")));
            }
            Shape::Plain(n) => n.as_str(),
            _ => return None,
        };
        let text = cell.as_str().map(str::trim).unwrap_or("");
        let fits = match ty {
            "number" => pact_schema::coerce::check(cell, &Ty::Number).is_some(),
            "whole-number" => pact_schema::coerce::check(cell, &Ty::Integer).is_some(),
            "money" => pact_schema::coerce::check(cell, &Ty::Money).is_some(),
            "yes-or-no" => pact_schema::coerce::check(cell, &Ty::YesNo).is_some(),
            "date" => crate::conditions::looks_like_a_date(text) && text.len() == 10,
            "time" => crate::conditions::looks_like_a_time(text),
            "date-and-time" => crate::conditions::looks_like_a_date(text),
            _ => true,
        };
        (!fits).then(|| {
            format!(
                "is not {}",
                match ty {
                    "number" => "a number",
                    "whole-number" => "a whole number",
                    "money" => "an amount of money, like `200 USD`",
                    "yes-or-no" => "yes or no",
                    "date" => "a date, like `2026-12-25`",
                    "time" => "a time of day, like `14:30`",
                    _ => "a date and time, like `2026-12-25T14:30:00-06:00`",
                }
            )
        })
    }
}

/// The word `value.shape` uses for a list of rows.
const TABLE: &str = "table";

/// A table's rows, each held to its `rows-are:` shape: every required part
/// there, no part the shape lacks, each cell in its part's shape.
fn table(name: &str, definition: &Node, held: &Node, rows: &Rows) -> Result<(), Box<Diagnostic>> {
    let wrong = |at: pact_diag::Span, message: String, fix: String| {
        Err(Box::new(Diagnostic::error(
            "loader/a-table-that-is-not-one",
            at,
            message,
            fix,
        )))
    };
    let Some(shape) = definition
        .get("rows-are")
        .and_then(Node::as_str)
        .map(str::trim)
    else {
        return wrong(
            definition.span.start_of_block(),
            format!("'{name}' is a table and does not say what its rows are."),
            "Add a line: `rows-are: <a shape>` — one of the names under `shapes:` in              `workspace.yaml`."
                .to_string(),
        );
    };
    // A name `shapes:` lacks is the schema's `names: shapes` to refuse.
    let Some(parts) = rows.parts.get(shape) else {
        return Ok(());
    };
    let Some(items) = held.as_list() else {
        return wrong(
            held.span.clone(),
            format!("'{name}' is a table, and its `value:` is not a list of rows."),
            format!("Write one row per line under `value:`, each with the parts of '{shape}'."),
        );
    };
    for row in items {
        let Some(cells) = row.as_map() else {
            return wrong(
                row.span.clone(),
                format!("A row of '{name}' is not a row: a row has the parts of '{shape}'."),
                format!(
                    "Write the row as its parts — `{{{}}}`.",
                    parts
                        .iter()
                        .map(|(p, _)| format!("{p}: ..."))
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            );
        };
        for (key, cell) in cells {
            let Some((_, written)) = parts.iter().find(|(p, _)| p == key) else {
                return wrong(
                    cell.key_span.clone(),
                    format!(
                        "A row of '{name}' has `{key}:`, and '{shape}' has no part called that."
                    ),
                    format!(
                        "Use the parts of '{shape}': {}.",
                        parts
                            .iter()
                            .map(|(p, _)| format!("`{p}`"))
                            .collect::<Vec<_>>()
                            .join(", ")
                    ),
                );
            };
            if let Some(why) = rows.misfit(&cell.node, written) {
                return wrong(
                    cell.node.span.clone(),
                    format!(
                        "In a row of '{name}', `{key}:` {why}, and '{shape}' says it is `{written}`."
                    ),
                    format!("Write `{key}:` as `{written}`, or change the part in '{shape}'."),
                );
            }
        }
        for (part, written) in parts {
            let optional = rows.line(written).is_some_and(|l| l.optional);
            if !optional && !cells.contains_key(part) {
                return wrong(
                    row.span.start_of_block(),
                    format!(
                        "A row of '{name}' has no `{part}:`, and every row of '{shape}' has one."
                    ),
                    format!(
                        "Add `{part}:` to the row, or mark it `{written}, optional` in '{shape}'."
                    ),
                );
            }
        }
    }
    Ok(())
}

/// The figures, with each `{use:}` inside them already resolved.
///
/// `None` means the definitions themselves are broken and every use site should
/// be left alone rather than told about a value that was never the problem.
fn figures_of(
    top: &pact_doc::Map,
    rows: &Rows,
    diags: &mut Diagnostics,
) -> Option<BTreeMap<String, Node>> {
    let defs = top.get(COLLECTION)?.node.as_map()?;
    let mut out: BTreeMap<String, Node> = BTreeMap::new();
    let mut broken = false;

    for (name, entry) in defs {
        let mut seen: Vec<String> = Vec::new();
        match figure(defs, name, &entry.key_span, &mut seen, rows) {
            Ok(node) => {
                out.insert(name.clone(), node);
            }
            Err(d) => {
                diags.push(*d);
                broken = true;
            }
        }
    }
    if broken { None } else { Some(out) }
}

/// One figure, with its own `{use:}` chain followed and its declared shape held.
fn figure(
    defs: &pact_doc::Map,
    name: &str,
    at: &pact_diag::Span,
    seen: &mut Vec<String>,
    rows: &Rows,
) -> Result<Node, Box<Diagnostic>> {
    let Some(entry) = defs.get(name) else {
        // Reached when one figure is built from another that is not there. The
        // span is the line that referred to it, which is the line to change. \
        return Err(Box::new(Diagnostic::error(
            "loader/no-such-value",
            at.clone(),
            format!("'{name}' is not a figure this workspace has."),
            format!("Write it in `values/{name}.yaml`, or use one that is there."),
        )));
    };
    let definition = &entry.node;
    if definition.as_map().is_none() {
        return Ok(definition.clone());
    }
    // `value.value` is `required: yes` in the specification and the requirement
    // could never fire: `values:` is removed before the schema sees it, so the
    // whole group's annotations were decoration (R41 — an unvalidated group is
    // an unclassified group). The two checks the group really makes are made
    // here instead, at the definition, which is where the wrong line is.
    let Some(held) = definition.get("value") else {
        return Err(Box::new(Diagnostic::error(
            "loader/a-figure-with-nothing-in-it",
            entry.key_span.clone(),
            format!("'{name}' is a figure with no figure in it."),
            format!(
                "Add a line: `value: ...` under `{name}:` — the figure itself, written the way \
                 you would write it where it is used."
            ),
        )));
    };

    // A circle has no bottom. Written out with arrows, the way `derive.rs`
    // writes a `based-on:` ring, so the reader can see which line to cut.
    if seen.iter().any(|s| s == name) {
        let mut ring = seen.clone();
        ring.push(name.to_owned());
        let from = ring.iter().position(|s| s == name).unwrap_or(0);
        return Err(Box::new(Diagnostic::error(
            "loader/a-value-built-from-itself",
            held.span.clone(),
            format!(
                "these figures are built from each other and so none of them has a \
                 value: {}.",
                ring[from..].join(" → ")
            ),
            format!(
                "Write a figure on one of them instead of `{{use: ...}}` — `{}` is the \
                 one to start with.",
                ring[from]
            ),
        )));
    }
    seen.push(name.to_owned());

    let resolved = if let Some(target) = names_a_value(held) {
        let inner = figure(defs, &target, &held.span, seen, rows)?;
        Node { value: inner.value, span: held.span.clone() }
    } else {
        held.clone()
    };
    seen.pop();

    if definition.get("shape").and_then(Node::as_str).map(str::trim) == Some(TABLE) {
        table(name, definition, &resolved, rows)?;
        return Ok(resolved);
    }
    if let Some(rows_are) = definition.as_map().and_then(|m| m.get("rows-are")) {
        return Err(Box::new(Diagnostic::error(
            "loader/a-table-that-is-not-one",
            rows_are.key_span.clone(),
            format!("'{name}' says what its rows are, and it is not a table."),
            format!("Add `shape: table` under `{name}:`, or delete `rows-are:`."),
        )));
    }
    // The declared shape, held against the figure. Optional to write; a claim
    // once written, and a claim nothing holds is decoration.
    // A word this format does not know turned the check OFF in silence, which
    // is worse than having no check: the author wrote a claim and was told
    // nothing about it.
    if let Some(written) = definition.get("shape").and_then(Node::as_str)
        && ty_of(written).is_none()
    {
        return Err(Box::new(Diagnostic::error(
            "loader/not-a-shape-a-figure-can-have",
            definition.get("shape").map_or_else(|| entry.key_span.clone(), |n| n.span.clone()),
            format!("'{written}' is not a kind of figure this format knows."),
            format!("Use one of: {}.", SHAPES.join(", ")),
        )));
    }
    if let Some(ty) = definition.get("shape").and_then(Node::as_str).and_then(ty_of)
        && pact_schema::coerce::check(&resolved, &ty).is_none()
    {
            return Err(Box::new(Diagnostic::error(
            "loader/value-is-not-its-shape",
            resolved.span.clone(),
            format!("'{name}' says it is {}, and its figure is not one.", ty.describe()),
            format!(
                "Write a figure that is {}, or change `shape:` to what this really is.",
                ty.describe()
            ),
        )));
    }
    Ok(resolved)
}

/// The words `value.shape` accepts, and what each one means.
///
/// Deliberately the SETTING types and not the answer shapes: a value stands
/// where a setting stands, and no answer is ever a length of time.
///
/// The specification carries the same list as `value.shape`'s `choices:`, and
/// this is not a second copy that can drift from it — the collection is removed
/// before the schema could hold anything against it, so THIS is where the
/// vocabulary is enforced, and a test holds the two equal.
pub(crate) const SHAPES: &[&str] = &[
    "text",
    "yes-or-no",
    "number",
    "whole-number",
    "duration",
    "money",
    "percent",
    "size",
    "table",
];

pub(crate) fn ty_of(shape: &str) -> Option<Ty> {
    Some(match shape {
        "text" => Ty::Text,
        "yes-or-no" => Ty::YesNo,
        "number" => Ty::Number,
        "whole-number" => Ty::Integer,
        "duration" => Ty::Duration,
        "money" => Ty::Money,
        "percent" => Ty::Percent,
        "size" => Ty::Size,
        _ => return None,
    })
}

/// The name a `{use: <name>}` node carries, if it is one.
///
/// A use site is exactly one key. Two keys is either a typo or somebody
/// expecting a value to take settings, and both are better met at the line than
/// by loading a set of settings where a figure belongs.
fn names_a_value(node: &Node) -> Option<String> {
    node.get(USE).and_then(Node::as_str).map(str::to_owned)
}

/// Whether this node is a use site at all — including the malformed ones, so
/// they are refused rather than walked past as an ordinary map.
fn looks_like_a_use(node: &Node) -> bool {
    node.as_map().is_some() && node.get(USE).is_some()
}

/// A figure written where the catalogue is read directly, refused by name.
fn refuse_under_the_catalogue(node: &Node, diags: &mut Diagnostics, depth: usize) {
    if depth > 16 {
        return;
    }
    if let Some(name) = names_a_value(node) {
        diags.push(Diagnostic::error(
            "loader/a-figure-cannot-reach-the-catalogue",
            node.span.clone(),
            format!(
                "'{name}' is a figure, and a figure cannot stand inside `models:` — the model \
                 catalogue is read straight off disk by whatever runs your agents, so a figure \
                 here would be filled in when the tree is checked and not when a model is \
                 bound."
            ),
            "Write the id itself here. A figure is for the lines an agent writes, not for the \
             catalogue."
                .to_string(),
        ));
        return;
    }
    match &node.value {
        Value::Map(map) => {
            for (_, entry) in map {
                refuse_under_the_catalogue(&entry.node, diags, depth + 1);
            }
        }
        Value::List(items) => {
            for item in items {
                refuse_under_the_catalogue(item, diags, depth + 1);
            }
        }
        _ => {}
    }
}

#[allow(clippy::too_many_arguments)]
fn substitute(
    node: &mut Node,
    ty: &Ty,
    schema: &Schema,
    figures: &BTreeMap<String, Node>,
    used: &mut BTreeSet<String>,
    diags: &mut Diagnostics,
    recorded: &mut Vec<crate::report::Substitution>,
    depth: usize,
) {
    // The specification is shallow and acyclic; the cap is a backstop against a
    // group that names itself, not a design.
    if depth > 16 {
        return;
    }
    // A figure written where one cannot stand. The verbatim rule and the
    // never-quietly-ignored rule pull opposite ways and both are right, and what
    // separates them is whether the name is a figure this workspace HAS: `{use:
    // the winter catalogue}` names nothing and is plainly an author's own key,
    // while `{use: spend-cap}` names a figure and was written by somebody who
    // meant it. Said, and still not substituted — the slot's contract holds.
    if looks_like_a_use(node)
        && !a_figure_can_stand_here(ty)
        && let Some(name) = names_a_value(node)
        && figures.contains_key(&name)
    {
        diags.push(Diagnostic::warning(
            "loader/a-figure-cannot-stand-here",
            node.span.clone(),
            format!(
                "'{name}' is a figure, and this line is read exactly as you wrote it — so the \
                 figure is not put here and `{{use: {name}}}` is what gets used."
            ),
            "Write the figure itself here. A figure stands where a single setting does, \
             and this line holds whatever you type."
                .to_string(),
        ));
        return;
    }
    if looks_like_a_use(node) && a_figure_can_stand_here(ty) {
        let map = node.as_map().expect("checked");
        let keys: Vec<String> = map.keys().cloned().collect();
        if keys.len() != 1 {
            let extra: Vec<String> =
                keys.iter().filter(|k| k.as_str() != USE).map(|k| format!("`{k}`")).collect();
            diags.push(Diagnostic::error(
                "loader/a-use-carries-only-a-name",
                node.span.clone(),
                format!(
                    "a `{{use: ...}}` is the name of a figure and nothing else, and this \
                     one also carries {}.",
                    extra.join(", ")
                ),
                "Leave just `{use: <name>}` here, and put anything else on the figure \
                 itself in `values/`."
                    .to_string(),
            ));
            return;
        }
        let Some(name) = names_a_value(node) else {
            diags.push(Diagnostic::error(
                "loader/a-use-carries-only-a-name",
                node.span.clone(),
                "a `{use: ...}` names a figure, and this one does not name anything."
                    .to_string(),
                "Write the name of a figure from `values/` — `{use: <name>}`.".to_string(),
            ));
            return;
        };
        match figures.get(&name) {
            Some(figure) => {
                recorded.push(crate::report::Substitution {
                    kind: "figure",
                    name: name.clone(),
                    // The USE SITE's file, which is where a reviewer would open
                    // it — the definition is one lookup away and the same for
                    // every use.
                    at: node.span.file.to_string(),
                });
                used.insert(name);
                // The USE SITE's span is kept, not the definition's. Whatever
                // this figure turns out to be wrong for, the line to change is
                // the one that asked for it here.
                *node = Node { value: figure.value.clone(), span: node.span.clone() };
            }
            None => {
                let mut there: Vec<String> =
                    figures.keys().map(|k| format!("`{k}`")).collect();
                there.sort();
                diags.push(Diagnostic::error(
                    "loader/no-such-value",
                    node.span.clone(),
                    format!("'{name}' is not a figure this workspace has."),
                    if there.is_empty() {
                        format!("Write it in `values/{name}.yaml`.")
                    } else {
                        format!(
                            "Write it in `values/{name}.yaml`, or use one of: {}.",
                            there.join(", ")
                        )
                    },
                ));
            }
        }
        return;
    }

    // Otherwise walk INTO it, guided by the type. `Ty::Anything` is deliberately
    // absent from every arm below: nothing under it is ever descended into, so
    // an author's own keys are read exactly as written.
    match (&mut node.value, ty) {
        (Value::Map(map), Ty::Group(kind)) => {
            let Some(group) = schema.group(kind).cloned() else { return };
            for (key, entry) in map.iter_mut() {
                // A pattern's arguments. `with:` is not a field of any group —
                // it is stripped before the schema sees it, like `based-on:` —
                // so a typed walk would step straight past it and a figure
                // handed to a pattern would never be filled in. Each argument is
                // a scalar slot: `an-argument-is-a-figure-not-a-block` is what
                // makes that true rather than assumed. \
                // A PATTERN's arguments — and only in a kind that has no
                // field of its own by that name. `with` is not a reserved word:
                // `case.with:` and `metric.with:` are real fields typed
                // `anything`, which is the specification saying *these keys are
                // the author's, read them verbatim*. Keying on the word alone
                // reached into both, and an eval case's own data came out
                // rewritten into a figure with nothing said — the untyped-walk
                // defect this pass was just fixed for, arriving again through
                // the fix for something else.
                if key == crate::templates::WITH
                    && !group
                        .fields
                        .iter()
                        .any(|f| f.name == *key || f.aliases.contains(key))
                {
                    if let Some(args) = entry.node.as_map_mut() {
                        for (_, arg) in args.iter_mut() {
                            substitute(
                                &mut arg.node, &Ty::Text, schema, figures, used, diags,
                                recorded, depth + 1,
                            );
                        }
                    }
                    continue;
                }
                let Some(field) =
                    group.fields.iter().find(|f| f.name == *key || f.aliases.contains(key))
                else {
                    continue;
                };
                substitute(
                    &mut entry.node, &field.ty, schema, figures, used, diags, recorded,
                    depth + 1,
                );
            }
        }
        (Value::Map(map), Ty::MapOf(inner)) => {
            for (_, entry) in map.iter_mut() {
                substitute(
                    &mut entry.node, inner, schema, figures, used, diags, recorded, depth + 1,
                );
            }
        }
        (Value::List(items), Ty::ListOf(inner)) => {
            for item in items.iter_mut() {
                substitute(
                    item, inner, schema, figures, used, diags, recorded, depth + 1,
                );
            }
        }
        // A single value where a list belongs is accepted everywhere else in
        // this format (FR-1.4.7), so a figure may stand there too.
        (_, Ty::ListOf(inner)) => {
            substitute(
                node, inner, schema, figures, used, diags, recorded, depth + 1,
            );
        }
        _ => {}
    }
}
