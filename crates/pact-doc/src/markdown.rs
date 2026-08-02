//! Markdown with optional YAML front matter.
//!
//! Markdown is the format a non-technical author is most likely to be
//! comfortable in (D13), so it is a first-class carrier of PACT values, not a
//! documentation afterthought. Two shapes are recognised:
//!
//! ```text
//! ---                     |  Just write the text.
//! description: Reviews PRs|
//! ---                     |  (no front matter at all)
//!                         |
//! You review pull requests|
//! ```
//!
//! With front matter, the file is **a set of settings** whose prose becomes the
//! body field. Without it, the file is simply **text**. The loader decides which
//! field the body lands in, because that depends on the slot the file occupies
//! — `instructions.md` means something different from `skills/triage.md`.

use crate::value::{Entry, Node, Value};
use crate::yaml::{Offset, parse_yaml_at};
use camino::Utf8Path;
use pact_diag::{Diagnostic, Span};

#[derive(Debug, Clone)]
pub struct Markdown {
    /// Parsed front matter, if the file opened with a `---` fence.
    pub front_matter: Option<Node>,
    pub body: String,
    pub body_span: Span,
}

impl Markdown {
    /// Fold the body into the front matter under `body_field`, producing a
    /// single node. If there is no front matter, the result is plain text.
    ///
    /// An explicit front-matter key always wins over the prose body, and the
    /// conflict is reported rather than silently resolved (thesis T7).
    pub fn into_node(self, body_field: &str) -> (Node, Option<Diagnostic>) {
        match self.front_matter {
            None => (Node::str(self.body, self.body_span), None),
            Some(mut fm) => {
                let body_is_blank = self.body.trim().is_empty();
                let existing = fm.as_map().and_then(|m| m.get(body_field)).map(|e| e.node.span.clone());

                match (existing, body_is_blank) {
                    (Some(prior), false) => {
                        let d = Diagnostic::warning(
                            "doc/body-and-field",
                            self.body_span.clone(),
                            format!(
                                "This file sets '{body_field}' at the top and also has text below the '---' line."
                            ),
                            format!(
                                "Keep only one. Either delete the '{body_field}:' line at the top, \
                                 or delete the text below."
                            ),
                        )
                        .with_related(prior, "also set here");
                        (fm, Some(d))
                    }
                    (_, true) => (fm, None),
                    (None, false) => {
                        if let Value::Map(m) = &mut fm.value {
                            m.insert(
                                body_field.to_string(),
                                Entry {
                                    key_span: self.body_span.clone(),
                                    node: Node::str(self.body, self.body_span),
                                },
                            );
                        }
                        (fm, None)
                    }
                }
            }
        }
    }
}

/// Parse a markdown file, extracting front matter if present.
pub fn parse_markdown(text: &str, file: &Utf8Path) -> Result<Markdown, Box<Diagnostic>> {
    let Some(rest) = strip_open_fence(text) else {
        return Ok(Markdown {
            front_matter: None,
            body: prose(text),
            body_span: whole(text, file),
        });
    };

    let open_len = text.len() - rest.len();
    let Some((fm_text, body, body_offset)) = split_at_close_fence(rest) else {
        return Err(Box::new(Diagnostic::error(
            "doc/unterminated-front-matter",
            Span::new(file, 1, 1, 0, 3),
            "This file starts with '---' but never has a closing '---' line.",
            "Add a line containing only '---' after the settings at the top of the file. \
             Everything after it is treated as the file's text.",
        )));
    };

    // Front matter starts on line 2 (after the opening fence) at byte `open_len`.
    let fm = parse_yaml_at(fm_text, file, Offset { line: 1, byte: open_len })?;

    let body_byte = open_len + body_offset;
    let body_line = 1 + text[..body_byte].lines().count();

    Ok(Markdown {
        front_matter: Some(fm),
        body: prose(body),
        body_span: Span::new(
            file,
            body_line,
            1,
            body_byte,
            text.len(),
        ),
    })
}

/// One prose body, with the file convention taken off the end.
///
/// **This is the Expansion Rule's central claim, and a trailing newline broke
/// it.** `instructions: Be kind.` written inline gives `"Be kind."`; the same
/// words in `instructions.md`, saved by any editor that ends a file with a
/// newline, gave `"Be kind.\n"`. Two different documents, two different digests,
/// from the two forms the format promises are the same one — measured on a
/// two-file workspace, not reasoned about.
///
/// The equivalence test in `pact-loader` normalised with `.trim()` before
/// comparing, so it could not see this: its fixture was written in Rust without a
/// trailing newline, which no real file has. Normalising in the test moved the
/// problem into the one place nobody looks.
///
/// `trim_end` only. Leading whitespace is content — an indented first line is a
/// code block in Markdown — and the POSIX newline is at the end.
fn prose(text: &str) -> String {
    text.trim_end().to_string()
}

fn whole(text: &str, file: &Utf8Path) -> Span {
    Span::new(file, 1, 1, 0, text.len())
}

/// Accept `---` on the very first line, tolerating a UTF-8 BOM and CRLF.
fn strip_open_fence(text: &str) -> Option<&str> {
    let t = text.strip_prefix('\u{feff}').unwrap_or(text);
    let rest = t.strip_prefix("---")?;
    match rest.strip_prefix("\r\n").or_else(|| rest.strip_prefix('\n')) {
        Some(r) => Some(r),
        // A bare `---` with nothing after it is an empty document, not front matter.
        None if rest.trim().is_empty() => Some(""),
        None => None,
    }
}

/// Split front matter from body at the first line that is exactly `---`.
/// Returns `(front_matter, body, byte offset of body within `rest`)`.
fn split_at_close_fence(rest: &str) -> Option<(&str, &str, usize)> {
    let mut idx = 0usize;
    for line in rest.split_inclusive('\n') {
        let trimmed = line.trim_end_matches(['\r', '\n']);
        if trimmed == "---" || trimmed == "..." {
            let fm = &rest[..idx];
            let after = idx + line.len();
            return Some((fm, &rest[after..], after));
        }
        idx += line.len();
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(s: &str) -> Markdown {
        parse_markdown(s, Utf8Path::new("t.md")).expect("parses")
    }

    #[test]
    fn plain_markdown_is_just_text() {
        let md = p("You review pull requests.\nBe concise.\n");
        assert!(md.front_matter.is_none());
        let (node, warn) = md.into_node("instructions");
        assert!(warn.is_none());
        assert_eq!(node.as_str().unwrap().trim(), "You review pull requests.\nBe concise.");
    }

    #[test]
    fn front_matter_and_body_combine() {
        let md = p("---\ndescription: Reviews PRs\n---\nYou review pull requests.\n");
        let (node, warn) = md.into_node("instructions");
        assert!(warn.is_none());
        assert_eq!(node.get("description").unwrap().as_str(), Some("Reviews PRs"));
        assert_eq!(node.get("instructions").unwrap().as_str().unwrap().trim(), "You review pull requests.");
    }

    #[test]
    fn front_matter_spans_point_at_real_line_numbers() {
        let md = p("---\nname: a\ndescription: b\n---\nbody\n");
        let fm = md.front_matter.unwrap();
        // `description` is physically on line 3 of the file.
        assert_eq!(fm.get("description").unwrap().span.line, 3);
    }

    #[test]
    fn body_span_points_past_the_closing_fence() {
        let md = p("---\nname: a\n---\nHello body\n");
        assert_eq!(md.body.trim(), "Hello body");
        assert_eq!(md.body_span.line, 4);
    }

    #[test]
    fn setting_the_body_field_twice_warns_rather_than_silently_picking() {
        let md = p("---\ninstructions: from the top\n---\nfrom the bottom\n");
        let (node, warn) = md.into_node("instructions");
        let warn = warn.expect("T7: conflicts are reported, never silently resolved");
        assert_eq!(warn.rule, "doc/body-and-field");
        assert_eq!(node.get("instructions").unwrap().as_str(), Some("from the top"));
    }

    #[test]
    fn empty_body_after_front_matter_is_not_a_conflict() {
        let md = p("---\ninstructions: only here\n---\n\n   \n");
        let (_, warn) = md.into_node("instructions");
        assert!(warn.is_none());
    }

    #[test]
    fn unterminated_front_matter_is_a_clear_error() {
        let err = parse_markdown("---\nname: a\nno closing fence\n", Utf8Path::new("t.md"))
            .unwrap_err();
        assert_eq!(err.rule, "doc/unterminated-front-matter");
        assert!(err.fix.contains("---"));
    }

    #[test]
    fn crlf_and_bom_are_tolerated() {
        let md = p("\u{feff}---\r\nname: a\r\n---\r\nbody text\r\n");
        assert!(md.front_matter.is_some());
        assert_eq!(md.body.trim(), "body text");
    }

    #[test]
    fn a_horizontal_rule_later_in_the_body_does_not_split() {
        let md = p("---\nname: a\n---\nintro\n\n---\n\nmore\n");
        // The first closing fence wins; the later `---` is ordinary markdown.
        assert!(md.body.contains("intro"));
        assert!(md.body.contains("more"));
    }
}
