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
    if top.get(COLLECTION).is_none() {
        // The overwhelmingly common case, and it must cost nothing: a tree that
        // writes no values is not walked at all, so P1 cannot change the meaning
        // of a document that never opted in. \
        return;
    }

    let figures = match figures_of(top, diags) {
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

    top.shift_remove(COLLECTION);
}

/// The figures, with each `{use:}` inside them already resolved.
///
/// `None` means the definitions themselves are broken and every use site should
/// be left alone rather than told about a value that was never the problem.
fn figures_of(top: &pact_doc::Map, diags: &mut Diagnostics) -> Option<BTreeMap<String, Node>> {
    let defs = top.get(COLLECTION)?.node.as_map()?;
    let mut out: BTreeMap<String, Node> = BTreeMap::new();
    let mut broken = false;

    for (name, entry) in defs {
        let mut seen: Vec<String> = Vec::new();
        match figure(defs, name, &entry.key_span, &mut seen) {
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
        let inner = figure(defs, &target, &held.span, seen)?;
        Node { value: inner.value, span: held.span.clone() }
    } else {
        held.clone()
    };
    seen.pop();

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
