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
use pact_schema::Ty;

/// The workspace field holding the figures.
const COLLECTION: &str = "values";
/// The one key a use site carries.
const USE: &str = "use";

/// Resolve every `{use: <name>}` in the document, in place, then drop `values:`.
pub fn resolve(root: &mut Node, diags: &mut Diagnostics) {
    let Some(top) = root.as_map_mut() else { return };
    if top.get(COLLECTION).is_none() {
        // The overwhelmingly common case, and it must cost nothing: a tree that
        // writes no values is not walked at all, so P1 cannot change the meaning
        // of a document that never opted in.
        return;
    }

    let figures = match figures_of(top, diags) {
        Some(f) => f,
        None => {
            // The definitions could not be read. Every use site would then draw
            // a second, misleading refusal naming a value that was never the
            // problem — `derive.rs` makes the same call for the same reason.
            top.shift_remove(COLLECTION);
            return;
        }
    };

    let mut used: BTreeSet<String> = BTreeSet::new();
    for (key, entry) in top.iter_mut() {
        if key == COLLECTION {
            continue;
        }
        substitute(&mut entry.node, &figures, &mut used, diags);
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
        // span is the line that referred to it, which is the line to change.
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
    let Some(held) = definition.get("value") else {
        // `value:` is `required: yes`; the schema says so where the author is.
        return Ok(definition.clone());
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

/// The scalar vocabulary a value may declare, as the author spells it.
///
/// Deliberately the SETTING types and not the answer shapes: a value stands
/// where a setting stands, and no answer is ever a length of time. The list is
/// the schema's own `choices:` on `value.shape`, and a word outside it never
/// reaches here — the schema refuses it first.
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

fn substitute(
    node: &mut Node,
    figures: &BTreeMap<String, Node>,
    used: &mut BTreeSet<String>,
    diags: &mut Diagnostics,
) {
    if looks_like_a_use(node) {
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

    match &mut node.value {
        Value::Map(map) => {
            for (_, entry) in map.iter_mut() {
                substitute(&mut entry.node, figures, used, diags);
            }
        }
        Value::List(items) => {
            for item in items.iter_mut() {
                substitute(item, figures, used, diags);
            }
        }
        _ => {}
    }
}
