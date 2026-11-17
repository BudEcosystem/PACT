//! **Declared detectors and the three new condition words** (`docs/98` WP-12).
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/effect-of-no-call` | `effect:` on a condition that looks at a value; it is about the call a `tool:` line names |
//! | `loader/a-value-word-on-a-call` | `in-share:` or `looks-like:` on a condition that looks at a call (`tool:`); both read a value |
//! | `loader/looks-like-nothing-known` | `looks-like:` names neither a built-in recogniser nor one of `detectors:` |
//! | `loader/looks-like-outside-the-dialect` | a `detectors:` entry's `looks-like:` pattern is outside the detector dialect ([`crate::dialect`]) |
//!
//! Where a hiding SENTENCE names a detector, the schema's sentence check
//! resolves it (`pact-schema`, the `<a thing>` hole). This holds the condition
//! words, which are fields rather than sentences, wherever a `when-this` is
//! written — an approval rule, a routing rule, `until:`, `only-when:`,
//! `admitted-when:`, `undo-where:`.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Node, Value};

/// The five things every rule can recognise, as the hiding sentences list them.
pub(crate) const BUILT_IN: &[&str] = &[
    "card number",
    "bank account",
    "email address",
    "phone number",
    "social security number",
];

/// Every rule, over the loaded document.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    let declared: Vec<String> = root
        .get("detectors")
        .and_then(Node::as_map)
        .map(|m| m.keys().cloned().collect())
        .unwrap_or_default();
    walk(root, &declared, diags);
    if let Some(detectors) = root.get("detectors").and_then(Node::as_map) {
        for (name, entry) in detectors {
            patterns_of(name, &entry.node, diags);
        }
    }
}

/// Hold one declared detector's `looks-like:` lines to the dialect: each line
/// on its own, so the message points at it, and then the lines joined as every
/// runtime joins them, which only a group name written in two lines fails.
fn patterns_of(name: &str, detector: &Node, diags: &mut Diagnostics) {
    let Some(written) = detector.get("looks-like") else {
        return;
    };
    let lines: Vec<&Node> = match written.as_list() {
        Some(items) => items.iter().collect(),
        None => vec![written],
    };
    let mut texts = Vec::new();
    for line in lines {
        let Some(text) = line.as_str() else {
            continue;
        };
        if let Some(outside) = crate::dialect::outside(text) {
            diags.push(outside_the_dialect(name, text, &outside, line.span.clone()));
            return;
        }
        texts.push(text);
    }
    let joined = crate::dialect::joined(&texts);
    if let Some(outside) = crate::dialect::outside(&joined) {
        diags.push(outside_the_dialect(name, &joined, &outside, written.span.clone()));
    }
}

fn outside_the_dialect(
    name: &str,
    pattern: &str,
    outside: &crate::dialect::Outside,
    span: pact_diag::Span,
) -> Diagnostic {
    Diagnostic::error(
        "loader/looks-like-outside-the-dialect",
        span,
        format!(
            "The detector '{name}' looks like `{pattern}`, which writes {} (at character {}). \
             Python and the Rust regex crate would not detect the same values with it.",
            outside.reason,
            outside.at + 1
        ),
        "Write the pattern in the detector dialect: literals, `.`, `^`, `$`, `\\b`, `\\d \\w \\s` \
         and their capitals, `[...]`, `(?:...)`, `(?P<name>...)`, `(?i:...)`, alternation and \
         `* + ? {n} {n,} {n,m}` (spec/schema.yaml, `detectors`)."
            .to_string(),
    )
}

fn walk(node: &Node, declared: &[String], diags: &mut Diagnostics) {
    match &node.value {
        Value::Map(map) => {
            let tool = map.contains_key("tool");
            let value = map.contains_key("value");
            if let Some(e) = map.get("effect")
                && value
                && !tool
            {
                diags.push(Diagnostic::error(
                    "loader/effect-of-no-call",
                    e.key_span.clone(),
                    "`effect:` says what a CALL does, and this condition looks at a value \
                     (`value:`), which does nothing."
                        .to_string(),
                    "Use `effect:` in an approval rule, beside `tool:` — `{ tool: payments, \
                     effect: spends }`."
                        .to_string(),
                ));
            }
            for word in ["in-share", "looks-like"] {
                if let Some(e) = map.get(word)
                    && tool
                {
                    diags.push(Diagnostic::error(
                        "loader/a-value-word-on-a-call",
                        e.key_span.clone(),
                        format!(
                            "`{word}:` reads a value, and this condition looks at a call \
                             (`tool:`)."
                        ),
                        format!(
                            "Look at the value with `value:` — `{{ value: input.<name>, {word}: \
                             ... }}` — in a routing rule, an `until:` or a port's `only-when:`."
                        ),
                    ));
                }
            }
            if let Some(e) = map.get("looks-like")
                && (value || tool)
                && let Some(named) = e.node.as_str().map(str::trim)
                && !BUILT_IN.contains(&named)
                && !declared.iter().any(|d| d == named)
            {
                let mut offered: Vec<String> = BUILT_IN.iter().map(|s| (*s).to_string()).collect();
                offered.extend(declared.iter().cloned());
                diags.push(Diagnostic::error(
                    "loader/looks-like-nothing-known",
                    e.node.span.clone(),
                    format!("Nothing here knows what '{named}' looks like."),
                    format!(
                        "Use one of: {} — or declare it under `detectors:` in workspace.yaml \
                         with the patterns it looks like.",
                        offered.join(", ")
                    ),
                ));
            }
            for (_, e) in map {
                walk(&e.node, declared, diags);
            }
        }
        Value::List(items) => {
            for item in items {
                walk(item, declared, diags);
            }
        }
        _ => {}
    }
}
