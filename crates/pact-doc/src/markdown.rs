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
//!
//! Those two are the whole of it, and the second one is wider than it looks: a
//! `---`/`---` pair with nothing between it (or nothing but comments) is **not
//! front matter**, so such a file is simply text as well. Everything else — a
//! fence holding a list, a stray sentence, a number — is refused rather than
//! folded, because there is no field in it for the prose and no reading of it
//! that keeps both halves. See [`Markdown::into_node`].

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

/// What one markdown file works out to: the value it contributes, and the one
/// report it owes.
///
/// The third field exists because the answer to *"the front matter is not
/// settings"* is not the same in the two places a markdown file can sit, and a
/// bare `Node` cannot say which happened. In a **field** slot —
/// `agents/desk/instructions.md` — the slot asked for text and the prose is
/// text, so the prose is handed over. As a folder's **self file** —
/// `agents/desk/agent.md` — the file's job was to supply that folder's
/// settings, and it supplied none; folding its prose under the body field
/// invents a setting the author never typed, which is the pile-on
/// `pact_loader`'s `fields_of_self_file` exists to prevent. The caller knows
/// which position it is reading and decides; see `pact_loader::Loader::read_file`.
#[derive(Debug, Clone)]
pub struct Folded {
    /// The value this file contributes.
    pub node: Node,
    /// The one thing the author has to be told about this file, if anything.
    pub report: Option<Diagnostic>,
    /// The front matter could not be used: nothing between the `---` lines
    /// reached [`Folded::node`], which carries the prose alone.
    pub front_matter_refused: bool,
}

impl Folded {
    fn plain(node: Node) -> Self {
        Self { node, report: None, front_matter_refused: false }
    }

    fn reported(node: Node, report: Diagnostic) -> Self {
        Self { node, report: Some(report), front_matter_refused: false }
    }
}

impl Markdown {
    /// Fold the body into the front matter under `body_field`, producing a
    /// single node. If there is no front matter, the result is plain text.
    ///
    /// Four answers, and T7 (*no silent loss anywhere*) is what decides between
    /// them — for **both** halves of the file, which is the trap here. Reporting
    /// the loss of one half while quietly dropping the other passes any test that
    /// only knows about one of them:
    ///
    /// | what the fences hold | the answer |
    /// |---|---|
    /// | settings, and the body field is not among them | fold: both halves arrive |
    /// | settings, and the body field IS among them | refuse — the same setting is written twice and only one can be kept |
    /// | nothing at all (empty, or comments only) | not front matter: the file is simply its text |
    /// | anything else | refuse, keep the prose, and say what was above the line |
    pub fn into_node(self, body_field: &str) -> Folded {
        let Some(mut fm) = self.front_matter else {
            return Folded::plain(Node::str(self.body, self.body_span));
        };

        // A `---`/`---` pair with nothing between it — or nothing but comments,
        // or nothing but blank lines — IS NOT FRONT MATTER, and refusing it
        // refused files that lose nothing at all. The dichotomy this module
        // opens with is the rule: with front matter the file is settings-then-
        // prose, without it the file is simply text. `Value::Null` is what
        // `parse_yaml_at` returns for a fence pair holding no document, so
        // there is nothing above the line to lose and the whole file is its
        // text. `pact_loader::holds_no_document` draws exactly this line one
        // crate up, for exactly this reason.
        //
        // It is also the shape real files are written in: of the nine markdown
        // files in this repository's vendored corpus whose front matter is not
        // a set of settings and whose body is not blank, six are this one —
        // five pydantic-ai `.github/workflows/shared/*.md` whose fences hold
        // only `#` comments, and opencode's own `empty-frontmatter.md`
        // fixture. Refusing them would have been PACT refusing to read the
        // file that every other tool reads.
        if matches!(fm.value, Value::Null) {
            return Folded::plain(Node::str(self.body, self.body_span));
        }

        let body_is_blank = self.body.trim().is_empty();
        let existing = fm.as_map().and_then(|m| m.get(body_field)).map(|e| e.node.span.clone());

        match (existing, body_is_blank) {
            (Some(prior), false) => {
                // An ERROR, and it was a warning. The warning's own
                // justification was that "both values are still in front of the
                // author", which is true of the FILE and false of the DOCUMENT:
                // measured on a copy of the shipped worked example with
                // `content: Ask for the receipt.` added to
                // `skills/refund-policy/SKILL.md`, `pact check` printed one
                // warning and exited 0, `pact show` exited 0, and the sentence
                // below the fence — `NEVER approve a refund over 100 USD.` —
                // appeared nowhere in what it printed. That is the identical
                // author-visible outcome this file's other arm exists to
                // prevent: authored words absent from the document while the
                // checker says the workspace is fine.
                //
                // One field written twice in one file is the same mistake as
                // one field written in two files, which `pact_loader` has
                // refused all along — `loader/ambiguous-field`, whose comment
                // reads "Refuse rather than pick (T7)". The front-matter value
                // still wins in the node so the rest of the report is about a
                // document with a body, but nothing runs until the author
                // deletes one of the two.
                let d = Diagnostic::error(
                    "doc/body-and-field",
                    self.body_span.clone(),
                    format!(
                        "This file sets '{body_field}' at the top and also has text below \
                         the '---' line, so the same setting is written twice and only one \
                         of them can be kept."
                    ),
                    format!(
                        "Keep only one. Either delete the '{body_field}:' line at the top, \
                         or delete the text below."
                    ),
                )
                .with_related(prior, "also set here");
                Folded::reported(fm, d)
            }
            (_, true) => Folded::plain(fm),
            (None, false) => {
                if let Value::Map(m) = &mut fm.value {
                    m.insert(
                        body_field.to_string(),
                        Entry {
                            key_span: self.body_span.clone(),
                            node: Node::str(self.body, self.body_span),
                        },
                    );
                    Folded::plain(fm)
                } else {
                    // Only a set of settings has a field to fold prose into.
                    // This arm used to be the `if` with no `else`, so a file
                    // whose fence held a stray horizontal rule or a list lost
                    // its entire body without a word — `pact check` said the
                    // workspace was clean while the sentence that capped a
                    // refund was gone.
                    //
                    // WHICH HALF IS KEPT. The prose. The author fenced the top
                    // of the file off as settings and it holds no settings, so
                    // there is nothing there this format can read; the rest of
                    // the file is what the slot asked for, and handing it over
                    // costs the author ONE message instead of two. Measured on
                    // a one-agent workspace whose `instructions.md` opened with
                    // a two-item list: returning the parsed fence instead
                    // planted a list in a slot that takes text, and `pact
                    // check` printed `'instructions' should be some text, but
                    // it is a list` beside this report — one mistake told
                    // twice, which CHK-12 forbids.
                    //
                    // An ERROR, not a warning: the words between the `---`
                    // lines are gone from the document, and a discard of
                    // something the author wrote is not a thing to mention in
                    // passing. The spans say the same thing the sentence does —
                    // the caret is under what was refused, the note is on the
                    // text that was kept — so the message and the underline
                    // cannot drift apart.
                    let name = fm.span.file.file_name().unwrap_or("this file").to_string();
                    let kind = fm.value.kind_name();
                    let d = Diagnostic::error(
                        "doc/front-matter-not-settings",
                        fm.span.clone(),
                        format!(
                            "The part of '{name}' between the '---' lines is {kind} \
                             instead of a set of settings, so none of it could be read \
                             and none of it reached the document."
                        ),
                        format!(
                            "Delete both '---' lines, so the whole of '{name}' is \
                             just its text. If the top really is meant to be \
                             settings, write one per line between the '---' lines, \
                             like `description: what this is`."
                        ),
                    )
                    .with_related(
                        self.body_span.clone(),
                        format!("the text below the line was read as the whole of '{name}'"),
                    );
                    Folded {
                        node: Node::str(self.body, self.body_span),
                        report: Some(d),
                        front_matter_refused: true,
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

    // The span starts at the first line of the body THAT HAS WORDS ON IT, not
    // at the byte after the closing fence. Convention puts a blank line there —
    // this module's own header draws it that way, and the shipped
    // `examples/refund-desk/skills/refund-policy/SKILL.md` is written that way —
    // and a span whose first line is blank renders as a caret under nothing:
    //
    // ```text
    // error: … has text below the '---' line …
    //   --> …/instructions.md:4:1
    //   |
    // 4 |
    //   | ^
    // ```
    //
    // Measured on the repository's own vendored real-world file,
    // `research/repos/filedef/opencode/…/empty-frontmatter.md`, copied verbatim
    // into a workspace. Only the layout with no blank line after the fence — the
    // one no editor produces and every fixture in the test file used —
    // underlined the sentence. The BODY STRING is untouched: leading whitespace
    // is content (an indented first line is a code block), so this moves where
    // the reader is pointed and nothing else.
    let body_byte = open_len + body_offset + first_line_with_words(body);
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

/// Byte offset, within `body`, of the start of the first line holding anything
/// other than whitespace. Zero when the body is blank — there is no better line
/// to point at than the first one.
fn first_line_with_words(body: &str) -> usize {
    match body.find(|c: char| !c.is_whitespace()) {
        None => 0,
        Some(i) => body[..i].rfind('\n').map_or(0, |nl| nl + 1),
    }
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
        let f = md.into_node("instructions");
        assert!(f.report.is_none());
        assert!(!f.front_matter_refused);
        assert_eq!(f.node.as_str().unwrap().trim(), "You review pull requests.\nBe concise.");
    }

    #[test]
    fn front_matter_and_body_combine() {
        let md = p("---\ndescription: Reviews PRs\n---\nYou review pull requests.\n");
        let f = md.into_node("instructions");
        assert!(f.report.is_none());
        assert_eq!(f.node.get("description").unwrap().as_str(), Some("Reviews PRs"));
        assert_eq!(
            f.node.get("instructions").unwrap().as_str().unwrap().trim(),
            "You review pull requests."
        );
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
    fn the_body_span_skips_the_blank_line_the_convention_puts_after_the_fence() {
        // The layout every editor and this module's own header produce. The
        // caret goes under the words, not under the empty line above them, and
        // the body string still holds that newline because leading whitespace is
        // content.
        let md = p("---\nname: a\n---\n\nHello body\n");
        assert_eq!(md.body_span.line, 5, "the words are on line 5");
        assert!(md.body.ends_with("Hello body"));
    }

    #[test]
    fn setting_the_body_field_twice_is_refused_rather_than_silently_picked() {
        let md = p("---\ninstructions: from the top\n---\nfrom the bottom\n");
        let f = md.into_node("instructions");
        let d = f.report.expect("T7: conflicts are reported, never silently resolved");
        assert_eq!(d.rule, "doc/body-and-field");
        // One of the two authored values does not reach the document, so this is
        // a refusal, not a remark: `pact check` exited 0 on it for as long as it
        // was a warning.
        assert_eq!(d.severity, pact_diag::Severity::Error);
        assert_eq!(f.node.get("instructions").unwrap().as_str(), Some("from the top"));
    }

    #[test]
    fn empty_body_after_front_matter_is_not_a_conflict() {
        let md = p("---\ninstructions: only here\n---\n\n   \n");
        let f = md.into_node("instructions");
        assert!(f.report.is_none());
    }

    #[test]
    fn a_fence_pair_holding_nothing_is_not_front_matter_at_all() {
        // Six of the nine real-world files in the vendored corpus with non-map
        // front matter are this shape, opencode's `empty-frontmatter.md` among
        // them. Nothing is above the line, so nothing can be lost by reading the
        // file as what it is: text.
        for md in ["---\n---\n\nContent\n", "---\n# just a comment\n---\n\nContent\n"] {
            let f = p(md).into_node("instructions");
            assert!(f.report.is_none(), "nothing is lost here: {:?}", f.report.map(|d| d.message));
            assert!(!f.front_matter_refused);
            assert_eq!(f.node.as_str().unwrap().trim(), "Content");
        }
    }

    #[test]
    fn front_matter_that_is_not_settings_keeps_the_prose_and_says_what_it_refused() {
        let f = p("---\n- a\n- b\n---\nthe sentence\n").into_node("instructions");
        let d = f.report.expect("a discard is reported");
        assert_eq!(d.rule, "doc/front-matter-not-settings");
        assert_eq!(d.severity, pact_diag::Severity::Error);
        assert!(f.front_matter_refused);
        // The prose is what the slot asked for, so it is what survives.
        assert_eq!(f.node.as_str().unwrap().trim(), "the sentence");
        // The caret is under what was refused (line 2, the first line between
        // the fences), the note on what was kept (line 5, the prose) — the same
        // thing the sentence says.
        assert_eq!(d.span.line, 2, "{}", d.message);
        assert_eq!(d.related[0].span.line, 5);
        assert!(d.message.contains("a list"), "the kind, in words: {}", d.message);
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
