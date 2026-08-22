//! `expects:` / `with:` — a base that takes arguments.
//!
//! # Why this exists
//!
//! `based-on:` lets one document inherit another's fields, and that is enough
//! when the two really are the same document with a difference *restated*. It is
//! not enough when the difference is the whole point: two desks with two spend
//! caps, two guards over two tools, two questions with two deadlines. The worked
//! example carried the proof — two interceptor files differing in two lines and
//! holding the same `may:`, the same `applies-to:` and the same two sentences.
//!
//! `expects:` turns a base into a function. It declares typed parameters; a
//! caller supplies them under `with:`; the loader fills the holes and hands the
//! finished document to everything downstream.
//!
//! # The three rules that keep it decidable
//!
//! **1. Holes fill VALUES. Never keys, never structure.** A pattern may say what
//! a setting *is*; it may not invent a setting. This is not a style rule — §8.2
//! computes a governance zone per field and the blast-radius classifier reads it,
//! so a template that could manufacture a field could manufacture one the
//! classifier has never seen, and an unclassified field is LOAD-13's whole
//! subject. Because holes only ever land in values, the governance surface of
//! everything a pattern makes is exactly the governance surface of the pattern.
//!
//! **2. Every parameter is declared, and shape-checked.** An argument nobody
//! declared is refused with the ones that are; a parameter nobody filled is
//! refused naming it; an argument that is not what its parameter says it is is
//! refused where it was written. A hole the pattern never declared is refused at
//! the pattern, because otherwise it survives into every document the pattern
//! makes as literal text that reads like a mistake nobody can find.
//!
//! **3. A pattern is not a document.** Its body carries holes, so it is not
//! something that could be run, offered, published or validated. Once every
//! caller has been filled in it is removed from the tree — the same move
//! `based-on:` and `values:` make, and for the same reason: a tree that used a
//! pattern and a tree that wrote every document out longhand are *the same
//! document*, so the digest of one means something about the other.
//!
//! That last rule is what separates a pattern from an abstract base. `base: yes`
//! says *this is an agent, and an abstract one* — it stays, it is validated with
//! the required-field exemption, and it is refused everywhere something could be
//! put to work. `expects:` says *this is a way of making one*, and there is
//! nothing to exempt because there is nothing left to check.

use std::collections::{BTreeMap, BTreeSet};

use pact_diag::{Diagnostic, Span};
use pact_doc::{Map, Node, Value};

/// The key a base declares its parameters under.
pub(crate) const EXPECTS: &str = "expects";
/// The key a caller supplies them under.
pub(crate) const WITH: &str = "with";

/// Whether this entry is a pattern — something to make documents with, rather
/// than a document.
pub(crate) fn is_a_pattern(node: &Node) -> bool {
    node.get(EXPECTS).and_then(Node::as_map).is_some()
}

/// The parameter names a pattern declares.
pub(crate) fn parameters(node: &Node) -> BTreeSet<String> {
    node.get(EXPECTS)
        .and_then(Node::as_map)
        .map(|m| m.keys().cloned().collect())
        .unwrap_or_default()
}

/// Read one scalar as the text a hole inside a sentence is filled with.
///
/// Structure has no rendering here on purpose: putting a set of settings inside
/// a sentence has no meaning anybody could predict, so it is refused at the
/// argument rather than producing something that reads like a mistake.
fn as_text(node: &Node) -> Option<String> {
    Some(match &node.value {
        Value::Str(s) => s.clone(),
        Value::Int(i) => i.to_string(),
        Value::Float(f) => f.to_string(),
        Value::Bool(b) => (if *b { "yes" } else { "no" }).to_string(),
        _ => return None,
    })
}

/// Every `<hole>` in a string, in the order they appear.
///
/// Deliberately narrow: a hole is `<` then a kebab-case name then `>`, with no
/// spaces. Prose that reads `if x < 5` is not a hole and never becomes one, and
/// neither is a comparison, an arrow, or a piece of XML somebody quoted.
fn holes_in(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] != b'<' {
            i += 1;
            continue;
        }
        // `<<name>>` is a LITERAL angle bracket and never a hole. Prose is full
        // of them the moment anybody writes an XML-ish prompt tag —
        // `<thinking>`, `<answer>` — and in a pattern that made the whole
        // document refuse, with a fix line that said to declare it, which would
        // have substituted the tag away.
        if bytes.get(i + 1) == Some(&b'<') {
            i = skip_escaped(bytes, i);
            continue;
        }
        let start = i + 1;
        let mut j = start;
        while j < bytes.len() && (bytes[j].is_ascii_lowercase() || bytes[j].is_ascii_digit() || bytes[j] == b'-') {
            j += 1;
        }
        if j > start && j < bytes.len() && bytes[j] == b'>' && bytes[start].is_ascii_alphanumeric() {
            out.push(text[start..j].to_owned());
            i = j + 1;
        } else {
            i += 1;
        }
    }
    out
}

/// Step past a `<<...>>` escape, returning the index after it.
fn skip_escaped(bytes: &[u8], at: usize) -> usize {
    let mut j = at + 2;
    while j + 1 < bytes.len() {
        if bytes[j] == b'>' && bytes[j + 1] == b'>' {
            return j + 2;
        }
        j += 1;
    }
    at + 2
}

/// Turn every `<<name>>` into `<name>`, once the holes are filled.
///
/// Last, so an escape can never become a hole: by the time this runs there is
/// nothing left that reads `<...>` as anything.
fn unescape(text: &str) -> String {
    if !text.contains("<<") {
        return text.to_owned();
    }
    text.replace("<<", "\u{1}").replace(">>", "\u{2}")
        .replace('\u{1}', "<").replace('\u{2}', ">")
}

/// Every hole anywhere in a document, so a pattern can be held to its own
/// declarations.
pub(crate) fn holes_of(node: &Node, into: &mut BTreeSet<String>) {
    match &node.value {
        Value::Str(s) => into.extend(holes_in(s)),
        Value::Map(m) => {
            for (key, entry) in m {
                // A hole in a KEY is refused rather than filled (rule 1), and it
                // is collected here so the refusal can name it. \
                into.extend(holes_in(key));
                holes_of(&entry.node, into);
            }
        }
        Value::List(items) => {
            for item in items {
                holes_of(item, into);
            }
        }
        _ => {}
    }
}

/// Whether any key anywhere in this document carries a hole.
pub(crate) fn a_key_with_a_hole(node: &Node) -> Option<String> {
    match &node.value {
        Value::Map(m) => {
            for (key, entry) in m {
                if !holes_in(key).is_empty() {
                    return Some(key.clone());
                }
                if let Some(found) = a_key_with_a_hole(&entry.node) {
                    return Some(found);
                }
            }
            None
        }
        Value::List(items) => items.iter().find_map(a_key_with_a_hole),
        _ => None,
    }
}

/// The arguments a caller supplied, held against what the pattern declares.
pub(crate) fn arguments(
    kind: &str,
    name: &str,
    base_name: &str,
    pattern: &Node,
    caller: &Node,
) -> Result<BTreeMap<String, Node>, Box<Diagnostic>> {
    let declared = pattern.get(EXPECTS).and_then(Node::as_map);
    let supplied = caller.get(WITH).and_then(Node::as_map);

    let Some(declared) = declared else {
        // Not a pattern. `with:` on an ordinary base has nothing to fill, and
        // saying so beats letting the schema call `with` an unknown field on a
        // document whose real mistake is that its base takes no arguments. \
        if supplied.is_some() {
            return Err(Box::new(Diagnostic::error(
                "loader/arguments-with-no-pattern",
                caller.get(WITH).map_or_else(|| caller.span.clone(), |n| n.span.clone()),
                format!(
                    "'{name}' supplies arguments, and '{base_name}' takes none — it has no \
                     `expects:` line, so there is nothing for them to fill."
                ),
                format!(
                    "Remove the `with:` block, or add `expects:` to `{base_name}` naming what \
                     it takes."
                ),
            )));
        }
        return Ok(BTreeMap::new());
    };

    let mut out: BTreeMap<String, Node> = BTreeMap::new();
    let empty = Map::new();
    let supplied_map = supplied.unwrap_or(&empty);

    // An argument nobody declared. Named with the ones that are, because the
    // commonest case by far is a misspelling and the list is the fix.
    for (given, entry) in supplied_map {
        if !declared.contains_key(given.as_str()) {
            let mut names: Vec<String> = declared.keys().map(|k| format!("`{k}`")).collect();
            names.sort();
            return Err(Box::new(Diagnostic::error(
                "loader/a-pattern-takes-only-what-it-expects",
                entry.key_span.clone(),
                format!("'{base_name}' does not take an argument called '{given}'."),
                format!("It takes: {}. Change the name, or add it to `expects:`.", names.join(", ")),
            )));
        }
    }

    // Rule 1 holds against the CALLER, not only against the pattern. `fill`
    // splices an argument's value in whole where a value is exactly one hole, so
    // a Map argument would land where a Map was never written — and the
    // governance surface of what a pattern makes would be decided by whoever
    // called it, which is the property this rule exists to deny (LOAD-13).
    //
    // A hole inside an argument is refused for the mirror reason: a caller
    // writes figures, not templates. The one exception is a pattern FORWARDING
    // its own parameter — `with: {domain: <domain>}` on an entry that itself
    // declares `domain` — which is how a chain of patterns passes a value down,
    // and is checkable because the caller's own declarations are right here.
    let forwards = parameters(caller);
    for (given, entry) in supplied_map {
        if as_text(&entry.node).is_none() {
            return Err(Box::new(Diagnostic::error(
                "loader/an-argument-is-a-figure-not-a-block",
                entry.node.span.clone(),
                format!(
                    "'{given}' here is a set of settings, and an argument to a pattern is a \
                     figure — a pattern may say what a setting IS, and never what settings \
                     there are."
                ),
                format!(
                    "Write a single figure for `{given}:`. To change the shape of what \
                     '{base_name}' makes, edit the pattern itself."
                ),
            )));
        }
        if let Some(text) = entry.node.as_str() {
            let loose: Vec<String> =
                holes_in(text).into_iter().filter(|h| !forwards.contains(h)).collect();
            if !loose.is_empty() {
                return Err(Box::new(Diagnostic::error(
                    "loader/an-argument-is-not-a-pattern",
                    entry.node.span.clone(),
                    format!(
                        "'{given}' here carries {}, and an argument is a figure rather than \
                         something with holes left in it.",
                        loose.iter().map(|h| format!("`<{h}>`")).collect::<Vec<_>>().join(", ")
                    ),
                    "Write the words out. A hole is only passed on when this entry declares it \
                     under its own `expects:` — that is how one pattern hands a figure down to \
                     another."
                        .to_string(),
                )));
            }
        }
    }

    for (want, spec) in declared {
        let Some(given) = supplied_map.get(want.as_str()) else {
            let what = spec
                .node
                .get("help")
                .and_then(Node::as_str)
                .map(|h| format!(" — {h}"))
                .unwrap_or_default();
            return Err(Box::new(Diagnostic::error(
                "loader/a-pattern-needs-what-it-expects",
                caller.get(WITH).map_or_else(|| caller.span.clone(), |n| n.span.clone()),
                format!(
                    "'{name}' is based on the pattern '{base_name}', which needs an argument \
                     called '{want}'{what}, and nothing supplies one."
                ),
                format!("Add a line under `with:`: `{want}: ...`."),
            )));
        };

        // The declared shape, held where the argument was written. Same
        // vocabulary a shared figure declares, for the same reason: a claim
        // nothing holds is decoration. \
        // A word this format does not know turned the check OFF in silence —
        // the same defect `values.rs` was fixed for, and worse here, because a
        // pattern's declaration is inherited by every caller.
        if let Some(written) = spec.node.get("shape").and_then(Node::as_str)
            && crate::values::ty_of(written).is_none()
        {
            return Err(Box::new(Diagnostic::error(
                "loader/not-a-shape-a-figure-can-have",
                spec.node.get("shape").map_or_else(
                    || spec.key_span.clone(),
                    |n| n.span.clone(),
                ),
                format!(
                    "'{base_name}' says '{want}' is `{written}`, and that is not a kind of \
                     figure this format knows."
                ),
                format!("Use one of: {}.", crate::values::SHAPES.join(", ")),
            )));
        }
        if let Some(ty) = spec.node.get("shape").and_then(Node::as_str).and_then(crate::values::ty_of)
            && pact_schema::coerce::check(&given.node, &ty).is_none()
        {
            return Err(Box::new(Diagnostic::error(
                "loader/an-argument-is-not-its-shape",
                given.node.span.clone(),
                format!(
                    "'{base_name}' says '{want}' is {}, and this is not one.",
                    ty.describe()
                ),
                format!("Write {} here, or change `shape:` on the pattern.", ty.describe()),
            )));
        }
        let _ = kind;
        out.insert(want.clone(), given.node.clone());
    }
    Ok(out)
}

/// Fill every declared hole in a document.
///
/// Two fillings, and the difference matters. A value that is *exactly* one hole
/// becomes the argument itself, so a whole number stays a whole number and an
/// amount of money keeps its currency. A hole *inside* a sentence is text put
/// into text, which is the only thing it could be.
pub(crate) fn fill(node: &mut Node, args: &BTreeMap<String, Node>) {
    match &mut node.value {
        Value::Str(text) => {
            let trimmed = text.trim();
            if let Some(name) = trimmed
                .strip_prefix('<')
                .and_then(|r| r.strip_suffix('>'))
                .filter(|n| !n.is_empty() && holes_in(trimmed).len() == 1)
                && let Some(arg) = args.get(name)
            {
                let keep = node.span.clone();
                *node = Node::new(arg.value.clone(), keep);
                return;
            }
            let mut out = text.clone();
            for (name, arg) in args {
                let hole = format!("<{name}>");
                if out.contains(&hole)
                    && let Some(rendered) = as_text(arg)
                {
                    out = out.replace(&hole, &rendered);
                }
            }
            *text = unescape(&out);
        }
        Value::Map(m) => {
            for (_, entry) in m.iter_mut() {
                fill(&mut entry.node, args);
            }
        }
        Value::List(items) => {
            for item in items.iter_mut() {
                fill(item, args);
            }
        }
        _ => {}
    }
}

/// A pattern whose body carries a hole it never declared.
///
/// Refused at the pattern, because the alternative is that the hole survives
/// into every document the pattern makes as literal text — the "loads and does
/// nothing" failure, one level up and multiplied by the number of callers.
pub(crate) fn holes_match_declarations(
    name: &str,
    pattern: &Node,
) -> Result<(), Box<Diagnostic>> {
    if let Some(key) = a_key_with_a_hole(pattern) {
        return Err(Box::new(Diagnostic::error(
            "loader/a-hole-nothing-fills",
            pattern.span.clone(),
            format!(
                "'{name}' puts a hole in the name of a setting (`{key}`), and a pattern may \
                 say what a setting is but never invent one."
            ),
            "Write the setting's real name, and put the hole in its value.".to_string(),
        )));
    }

    let declared = parameters(pattern);
    let mut found: BTreeSet<String> = BTreeSet::new();
    // The declarations themselves are not part of the body.
    if let Some(map) = pattern.as_map() {
        for (key, entry) in map {
            if key == EXPECTS {
                continue;
            }
            holes_of(&entry.node, &mut found);
        }
    }
    let loose: Vec<String> = found.difference(&declared).cloned().collect();
    if loose.is_empty() {
        return Ok(());
    }
    let named = loose.iter().map(|h| format!("`<{h}>`")).collect::<Vec<_>>().join(", ");
    Err(Box::new(Diagnostic::error(
        "loader/a-hole-nothing-fills",
        pattern.span.clone(),
        format!(
            "'{name}' carries {named}, and nothing under `expects:` fills {}.",
            if loose.len() == 1 { "it" } else { "them" }
        ),
        format!(
            "Add {} under `expects:`, or write the words out.",
            loose.iter().map(|h| format!("`{h}:`")).collect::<Vec<_>>().join(" and ")
        ),
    )))
}

/// The span to hang a "nothing uses this pattern" warning on.
pub(crate) fn where_it_is(entry_key_span: &Span) -> Span {
    entry_key_span.clone()
}
