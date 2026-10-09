//! Diagnostics for PACT.
//!
//! Design constraint (decision D13): the reader of these messages is a
//! **non-technical domain expert** who cannot write code. Every diagnostic
//! therefore carries four things, and the renderer refuses to omit any of them:
//!
//! 1. **where** — file, line, column (a [`Span`]);
//! 2. **what** — a plain-language statement of the problem;
//! 3. **why** — the rule that was violated, by stable id;
//! 4. **how** — a concrete fix the reader can type.
//!
//! Objective O7.3 is enforced structurally: [`Diagnostic::new`] requires a fix,
//! so it is impossible to construct a diagnostic that leaves the reader stuck.

use camino::{Utf8Path, Utf8PathBuf};
use std::fmt;

/// A byte-and-line addressed region of a source file.
///
/// Lines and columns are 1-based (what an editor shows); `byte_start`/`byte_end`
/// are 0-based offsets into the file's UTF-8 bytes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Span {
    pub file: Utf8PathBuf,
    pub line: usize,
    pub col: usize,
    pub byte_start: usize,
    pub byte_end: usize,
    /// Set only when `file` names a **folder that holds no file able to carry
    /// its own settings**: the file an author would have to create there first.
    ///
    /// A folder has no lines, so `line` and `col` are a fiction for it, and
    /// every fix phrased as *"add a line"* is advice about a file that is not
    /// there. Measured on the first tree a brand-new author makes — one
    /// `agents/hello/agent.yaml` and nothing else — `pact check` opened with
    ///
    /// ```text
    /// error: A workspace must have a 'name'.
    ///   --> /tmp/hello:1:1
    ///   fix: Add a line: `name: ...` — what this whole system is called
    /// ```
    ///
    /// naming a line and column in a directory, quoting nothing, and leaving
    /// the reader to guess which file the line goes in. It goes in a file that
    /// does not exist yet, which is the one thing the message could not say.
    /// Carrying the answer on the span is what lets the sentence say *create
    /// this file* instead — see [`Span::in_folder`].
    pub file_to_start: Option<Utf8PathBuf>,
}

impl Span {
    pub fn new(
        file: impl Into<Utf8PathBuf>,
        line: usize,
        col: usize,
        byte_start: usize,
        byte_end: usize,
    ) -> Self {
        Self {
            file: file.into(),
            line,
            col,
            byte_start,
            byte_end,
            file_to_start: None,
        }
    }

    /// A span identifying a whole file, used when the problem is the file's
    /// existence, name, or absence rather than its content.
    pub fn whole_file(file: impl Into<Utf8PathBuf>) -> Self {
        Self {
            file: file.into(),
            line: 1,
            col: 1,
            byte_start: 0,
            byte_end: 0,
            file_to_start: None,
        }
    }

    /// A span identifying a **folder** whose settings have nowhere to be
    /// written, plus `file_to_start` — the file an author would create in it.
    ///
    /// The loader builds one of these for every directory it expands that has
    /// no self file, because that is exactly the shape whose missing settings
    /// cannot be typed anywhere yet.
    pub fn in_folder(dir: impl Into<Utf8PathBuf>, file_to_start: impl Into<Utf8PathBuf>) -> Self {
        Self {
            file: dir.into(),
            line: 1,
            col: 1,
            byte_start: 0,
            byte_end: 0,
            file_to_start: Some(file_to_start.into()),
        }
    }

    /// Does this span name a folder rather than a file?
    pub(crate) fn is_folder(&self) -> bool {
        self.file_to_start.is_some()
    }

    /// The place a **missing** thing belongs: the start of the block that owes
    /// it, with no width.
    ///
    /// Absence has no position, so a diagnostic about something the author did
    /// not write has to borrow one. Borrowing the span of a value that *is*
    /// written puts the underline under an unrelated line and tells the reader
    /// that line is wrong — `pact check` did exactly that, underlining
    /// `name: Fraud Checker` to report a missing `description`. This borrows
    /// only the beginning of the block: same line, column 1, zero width.
    ///
    /// Zero width is what [`Diagnostics::render_one`] reads as *"this is a
    /// place, not a thing"*, and a place is reported with no excerpt at all —
    /// no underline, and no quoted line either. Quoting the block's first line
    /// under a sentence about a line that is not there was the same mistake one
    /// step quieter: the reader still saw a line singled out, still correct.
    ///
    /// `byte_start` is kept as it was so [`Diagnostics::sort`] still files the
    /// diagnostic where the block sits in the document.
    #[must_use]
    pub fn start_of_block(&self) -> Span {
        Span {
            file: self.file.clone(),
            line: self.line,
            col: 1,
            byte_start: self.byte_start,
            byte_end: self.byte_start,
            // Carried, because this is the constructor every missing-setting
            // report goes through, and a block with no file to put a line in is
            // precisely a block that owes a line.
            file_to_start: self.file_to_start.clone(),
        }
    }

    /// Widen this span to also cover `other`. Spans in different files do not
    /// merge; the receiver wins, because a diagnostic anchors to one place.
    #[must_use]
    pub fn merge(mut self, other: &Span) -> Span {
        if self.file == other.file {
            if other.byte_start < self.byte_start {
                self.byte_start = other.byte_start;
                self.line = other.line;
                self.col = other.col;
            }
            self.byte_end = self.byte_end.max(other.byte_end);
        }
        self
    }
}

impl fmt::Display for Span {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // A folder has no first line, so it is not given one. `--> /tmp/hello:1:1`
        // told a first-time author to look at line 1 column 1 of a directory;
        // whatever they opened, it was not the thing the message meant.
        if self.is_folder() {
            return write!(f, "{}", self.file);
        }
        write!(f, "{}:{}:{}", self.file, self.line, self.col)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Severity {
    /// The document cannot be loaded or is not valid. Nothing will run.
    Error,
    /// The document loads, but something is probably not what the author meant.
    Warning,
    /// Neutral information the author should know (e.g. a default was applied).
    Note,
}

impl Severity {
    fn label(self) -> &'static str {
        match self {
            Severity::Error => "error",
            Severity::Warning => "warning",
            Severity::Note => "note",
        }
    }
}

/// An additional location that helps explain a diagnostic — for example, the
/// *other* file involved in an ambiguity.
#[derive(Debug, Clone)]
pub struct Related {
    pub span: Span,
    pub message: String,
}

/// A single problem, in the four-part form described at the module level.
#[derive(Debug, Clone)]
pub struct Diagnostic {
    pub severity: Severity,
    /// Stable machine-readable rule id, e.g. `loader/ambiguous-field`.
    /// Stable across releases so it can be linked to documentation and
    /// suppressed or asserted in tests.
    pub rule: &'static str,
    /// Plain-language statement of the problem. No jargon, no type names.
    pub message: String,
    pub span: Span,
    /// Concrete, typeable fix. Required — see module docs.
    pub fix: String,
    pub related: Vec<Related>,
}

impl Diagnostic {
    /// Construct a diagnostic. `fix` is mandatory by signature: a reader who
    /// cannot write code must always be told what to do next.
    pub fn new(
        severity: Severity,
        rule: &'static str,
        span: Span,
        message: impl Into<String>,
        fix: impl Into<String>,
    ) -> Self {
        Self {
            severity,
            rule,
            span,
            message: message.into(),
            fix: fix.into(),
            related: Vec::new(),
        }
    }

    pub fn error(
        rule: &'static str,
        span: Span,
        message: impl Into<String>,
        fix: impl Into<String>,
    ) -> Self {
        Self::new(Severity::Error, rule, span, message, fix)
    }

    pub fn warning(
        rule: &'static str,
        span: Span,
        message: impl Into<String>,
        fix: impl Into<String>,
    ) -> Self {
        Self::new(Severity::Warning, rule, span, message, fix)
    }

    /// Neutral information: something happened that the reader is entitled to
    /// know about and that is not a mistake.
    ///
    /// Its whole point is that it does NOT fail `--deny-warnings`
    /// ([`Diagnostics::warning_count`] counts warnings alone), so a lossy
    /// operation the author asked for can still be reported — which is what
    /// EXP-11 and FR-8.1.1 require of every one of them.
    pub fn note(
        rule: &'static str,
        span: Span,
        message: impl Into<String>,
        fix: impl Into<String>,
    ) -> Self {
        Self::new(Severity::Note, rule, span, message, fix)
    }

    #[must_use]
    pub fn with_related(mut self, span: Span, message: impl Into<String>) -> Self {
        self.related.push(Related {
            span,
            message: message.into(),
        });
        self
    }
}

/// A collection of diagnostics plus the source text needed to render them.
///
/// Sources are registered as they are read so the renderer can show the
/// offending line. A diagnostic whose file was never registered still renders,
/// just without the source excerpt.
#[derive(Debug, Default)]
pub struct Diagnostics {
    items: Vec<Diagnostic>,
    sources: Vec<(Utf8PathBuf, String)>,
}

impl Diagnostics {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn push(&mut self, d: Diagnostic) {
        self.items.push(d);
    }

    pub fn extend(&mut self, other: impl IntoIterator<Item = Diagnostic>) {
        self.items.extend(other);
    }

    /// Register a file's text so diagnostics in it can show a source excerpt.
    pub fn add_source(&mut self, path: impl Into<Utf8PathBuf>, text: impl Into<String>) {
        let path = path.into();
        if !self.sources.iter().any(|(p, _)| *p == path) {
            self.sources.push((path, text.into()));
        }
    }

    /// The registered text of `path`, for a check that has to point INSIDE a
    /// value: a value's span is the whole value, and where a word sits in a
    /// folded or quoted one can only be read off the file.
    pub fn source_of(&self, path: &Utf8Path) -> Option<&str> {
        self.sources
            .iter()
            .find(|(p, _)| p == path)
            .map(|(_, t)| t.as_str())
    }

    /// Take another collection's registered file texts.
    ///
    /// For the one caller that filters a whole workspace's diagnostics down to
    /// the agent somebody asked about: the kept diagnostics point at files whose
    /// text was read during the whole-tree load, and without it every one of them
    /// would render with no source excerpt — the caret pointing at nothing.
    pub fn borrow_sources_from(&mut self, other: &Diagnostics) {
        for (path, text) in &other.sources {
            self.add_source(path.clone(), text.clone());
        }
    }

    pub fn items(&self) -> &[Diagnostic] {
        &self.items
    }

    /// Keep only the diagnostics `keep` says yes to — for a check that says in
    /// its own words what another check already said about the same line.
    pub fn retain(&mut self, keep: impl FnMut(&Diagnostic) -> bool) {
        self.items.retain(keep);
    }

    pub fn has_errors(&self) -> bool {
        self.items.iter().any(|d| d.severity == Severity::Error)
    }

    pub fn error_count(&self) -> usize {
        self.items
            .iter()
            .filter(|d| d.severity == Severity::Error)
            .count()
    }

    pub fn warning_count(&self) -> usize {
        self.items
            .iter()
            .filter(|d| d.severity == Severity::Warning)
            .count()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    /// Sort into reading order: by file, then position. Deterministic output
    /// matters because these are compared in tests and reviewed in diffs.
    pub fn sort(&mut self) {
        self.items.sort_by(|a, b| {
            a.span
                .file
                .cmp(&b.span.file)
                .then(a.span.byte_start.cmp(&b.span.byte_start))
                .then(a.rule.cmp(b.rule))
        });
    }

    /// Render every diagnostic for a terminal reader.
    pub fn render(&self) -> String {
        self.items
            .iter()
            .map(|d| self.render_one(d))
            .collect::<Vec<_>>()
            .join("\n")
    }

    fn render_one(&self, d: &Diagnostic) -> String {
        let mut out = String::new();
        out.push_str(&format!("{}: {}\n", d.severity.label(), d.message));
        out.push_str(&format!("  --> {}\n", d.span));

        // The quoted line and its underline are one thing, and neither is
        // printed without the other.
        //
        // Quoting a line without marking anything on it is the report naming a
        // line. The reader has been told something is wrong and then shown one
        // line of their file; they read those as one sentence, and the sentence
        // says "this line". For a missing setting that line is never the
        // problem — `pact check` printed
        //
        // ```text
        //   --> agents/refund-desk/agent.yaml:2:1
        //   |
        // 2 | name: Refund Desk
        //   fix: Add a line: `description: ...`
        // ```
        //
        // to report an absent `description`, quoting the one line in the file
        // that was right and marking nothing on it. There is nothing on that
        // line to mark, because absence has no position, so the excerpt goes
        // with the underline: what is left names the file, the line the block
        // starts on, and the line to type.
        // A folder is never registered as a source, so this guard is belt and
        // braces — but a folder called `agent.yaml` is a legal folder, and the
        // one thing worse than no excerpt is an excerpt from somewhere else.
        if !d.span.is_folder()
            && let Some(text) = self.source_of(&d.span.file)
            && let Some(line) = text.lines().nth(d.span.line.saturating_sub(1))
        {
            // A caret starts under the column the diagnostic names, but never
            // further right than one past the last character: an underline
            // floating in the margin points at nothing at all.
            let line_chars = line.chars().count();
            let start_col = d.span.col.clamp(1, line_chars + 1);
            if let Some(width) = caret_width(text, &d.span, line_chars, start_col) {
                let gutter = d.span.line.to_string();
                let pad = " ".repeat(gutter.len());
                let caret_pad = " ".repeat(start_col - 1);
                out.push_str(&format!("{pad} |\n"));
                out.push_str(&format!("{gutter} | {line}\n"));
                out.push_str(&format!("{pad} | {caret_pad}{}\n", "^".repeat(width)));
            }
        }

        for r in &d.related {
            out.push_str(&format!("  note: {} ({})\n", r.message, r.span));
        }

        out.push_str(&format!("  fix: {}\n", d.fix));
        out.push_str(&format!("  rule: {}\n", d.rule));
        out
    }
}

/// The longest underline the renderer will draw, so that a span covering a
/// large document cannot fill the terminal with carets.
const MAX_CARETS: usize = 80;

/// How many carets to draw under the one line being shown, or `None` when there
/// is nothing on that line to underline — in which case the line is not shown
/// either, because a quoted line is how a report says "here".
///
/// Two failures are being prevented, both seen in real `pact check` output:
///
/// 1. **The span is wider than the line.** A `schema/missing-field` span covers
///    the whole document node, so its byte length ran to the 80-caret clamp
///    under a 19-character line — most of the underline pointed at empty space.
///    Only one line is on screen, so the underline stops where that line does,
///    whatever else the span covers.
/// 2. **Bytes are not columns.** The old width was a byte count, so a line
///    holding `café` or any CJK text got an underline wider than the text it
///    marked, sliding it off the thing it names.
fn caret_width(text: &str, span: &Span, line_chars: usize, start_col: usize) -> Option<usize> {
    let end = span.byte_end.min(text.len());
    if end <= span.byte_start {
        // Zero width means the span marks a *place*, not a thing: a line the
        // author never wrote, or a whole file. Underlining a character that is
        // there would claim that character is the problem — and so, one step
        // quieter, would quoting the line it sits on.
        return None;
    }
    // What is left of the printed line once the caret has been indented to its
    // column. One caret is the floor — a span that ends past the line's end
    // still has to point somewhere.
    let room = (line_chars + 1)
        .saturating_sub(start_col)
        .clamp(1, MAX_CARETS);
    let covered = text
        .get(span.byte_start..end)
        // Offsets that do not land on character boundaries cannot be measured;
        // underlining the rest of the line is the widest honest answer.
        .map_or(room, |s| s.chars().take(room).count());
    Some(covered.clamp(1, room))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn span() -> Span {
        Span::new("agents/refund/agent.yaml", 3, 5, 30, 34)
    }

    /// The `^^^^` row of a rendered diagnostic, as (leading spaces, carets),
    /// measured in characters and with the `N | ` gutter removed.
    fn caret_row(rendered: &str) -> Option<(usize, usize)> {
        let row = rendered.lines().find(|l| l.contains('^'))?;
        let after_gutter = row.split_once(" | ").map_or(row, |(_, r)| r);
        let carets = after_gutter.chars().filter(|c| *c == '^').count();
        Some((after_gutter.chars().count() - carets, carets))
    }

    #[test]
    fn every_diagnostic_carries_a_fix() {
        let d = Diagnostic::error(
            "loader/test",
            span(),
            "something is wrong",
            "do this instead",
        );
        assert!(
            !d.fix.is_empty(),
            "O7.3: a diagnostic without a fix must be unconstructable"
        );
    }

    #[test]
    fn render_includes_where_what_why_and_how() {
        let mut diags = Diagnostics::new();
        diags.add_source(
            "agents/refund/agent.yaml",
            "name: refund\ndesc: x\n    bad: y\n",
        );
        diags.push(Diagnostic::error(
            "loader/unknown-field",
            span(),
            "'desk' is not something an agent can have.",
            "Did you mean 'description'? Change line 3 to 'description:'.",
        ));
        let out = diags.render();
        assert!(out.contains("agents/refund/agent.yaml:3:5"), "where");
        assert!(out.contains("not something an agent can have"), "what");
        assert!(out.contains("loader/unknown-field"), "why");
        assert!(out.contains("Did you mean 'description'"), "how");
    }

    #[test]
    fn a_caret_never_runs_past_the_end_of_the_line_it_underlines() {
        // The span of a whole document node covers every line of the file. Only
        // one line is printed, so an underline as wide as the span points
        // mostly at empty space — `pact check` drew 80 carets from column 5
        // under a 19-character line before this was clamped.
        let text = "name: Fraud Checker\nuses:\n  - zendesk\n";
        let mut diags = Diagnostics::new();
        diags.add_source("agents/fraud-checker/agent.yaml", text);
        diags.push(Diagnostic::error(
            "schema/whole-document",
            Span::new("agents/fraud-checker/agent.yaml", 1, 5, 4, text.len()),
            "the span covers the whole file",
            "shorten the underline",
        ));
        let (indent, carets) = caret_row(&diags.render()).expect("an underline was drawn");
        assert_eq!(
            indent, 4,
            "the caret starts under the column the diagnostic names"
        );
        assert_eq!(
            indent + carets,
            "name: Fraud Checker".chars().count(),
            "the underline has to stop where the printed line stops"
        );
    }

    #[test]
    fn a_caret_is_as_wide_as_the_characters_it_marks_not_the_bytes() {
        // `café` is 5 bytes and 4 characters. Measuring bytes made the
        // underline overhang the word, so it named the space after it too.
        let text = "name: café and more text after it\n";
        let mut diags = Diagnostics::new();
        diags.add_source("a.yaml", text);
        diags.push(Diagnostic::error(
            "schema/wrong-value",
            Span::new("a.yaml", 1, 7, 6, 11),
            "this value is not allowed",
            "use one of: tea, coffee",
        ));
        let (indent, carets) = caret_row(&diags.render()).expect("an underline was drawn");
        assert_eq!(
            (indent, carets),
            (6, 4),
            "four characters marked, not five bytes"
        );
    }

    #[test]
    fn a_span_that_marks_a_place_rather_than_a_thing_quotes_no_line_and_draws_no_caret() {
        // What a missing line and a whole file have in common: there is nothing
        // in the text to underline, so an underline would be a lie about some
        // character that is there.
        //
        // The line used to be printed anyway, as context for where the missing
        // line goes. That was the same lie one step quieter. `pact check`
        // reported an absent `description` by quoting `name: Refund Desk` and
        // marking nothing on it, and a reader who is told something is wrong
        // and then shown one line of their file reads those as one sentence.
        // So the excerpt travels with the underline: no underline, no excerpt.
        let mut diags = Diagnostics::new();
        diags.add_source("agents/hello/agent.yaml", "name: Hello\n");
        diags.push(Diagnostic::error(
            "schema/missing-field",
            Span::new("agents/hello/agent.yaml", 1, 7, 6, 11).start_of_block(),
            "An agent must have a 'description'.",
            "Add a line: `description: ...`",
        ));
        let out = diags.render();
        assert!(
            caret_row(&out).is_none(),
            "nothing to underline, so no underline:\n{out}"
        );
        assert!(
            !out.contains("name: Hello"),
            "and so no line is singled out either:\n{out}"
        );
        assert!(
            out.contains("agents/hello/agent.yaml:1:1"),
            "still says where:\n{out}"
        );
        assert!(
            out.contains("Add a line: `description: ...`"),
            "still says what to type:\n{out}"
        );
    }

    #[test]
    fn a_place_that_is_a_folder_is_never_given_a_line_and_a_column() {
        // The sibling rule to the one above, at the other end of the same
        // problem. Absence has no position; a FOLDER has no line either, and
        // `--> /tmp/hello:1:1` was the first thing `pact check` ever said to
        // somebody whose tree had no `workspace.yaml` in it yet. There is no
        // line 1 of a directory to go and look at.
        let mut diags = Diagnostics::new();
        // Registered deliberately: a folder may share a name with a file, and
        // an excerpt borrowed from one to describe the other would be worse
        // than none.
        diags.add_source("/tmp/hello", "name: not this file\n");
        diags.push(Diagnostic::error(
            "schema/missing-field",
            Span::in_folder("/tmp/hello", "/tmp/hello/workspace.yaml").start_of_block(),
            "A workspace must have a 'name'.",
            "Create `/tmp/hello/workspace.yaml` and put one line in it: `name: ...`",
        ));
        let out = diags.render();
        assert!(
            out.contains("--> /tmp/hello\n"),
            "the folder is named, and only named:\n{out}"
        );
        assert!(
            !out.contains("/tmp/hello:1:1"),
            "a folder has no line 1:\n{out}"
        );
        assert!(
            !out.contains("not this file"),
            "and nothing of it is quoted:\n{out}"
        );
        assert!(
            out.contains("Create `/tmp/hello/workspace.yaml`"),
            "the file to make is what replaces the position:\n{out}"
        );
    }

    #[test]
    fn a_report_never_quotes_a_line_it_does_not_underline() {
        // The rule behind the test above, checked over every shape of span at
        // once rather than the one that produced the complaint: a value with a
        // width, a block start with none, a whole file, and a span whose line is
        // past the end of the text. Whatever a caller hands the renderer, a
        // quoted `N | ` row is always followed by a `  | ^^^` row — which is the
        // renderer's whole promise, that the line it shows is the line it means.
        let text = "name: Hello\ndescription: Says hello.\n";
        let mut diags = Diagnostics::new();
        diags.add_source("a.yaml", text);
        diags.push(Diagnostic::error(
            "schema/wrong-value",
            Span::new("a.yaml", 1, 7, 6, 11),
            "a value with a width",
            "f",
        ));
        diags.push(Diagnostic::error(
            "schema/missing-field",
            Span::new("a.yaml", 2, 14, 25, 36).start_of_block(),
            "a block that owes a line",
            "f",
        ));
        diags.push(Diagnostic::error(
            "loader/unreadable",
            Span::whole_file("a.yaml"),
            "a file",
            "f",
        ));
        diags.push(Diagnostic::error(
            "loader/past-the-end",
            Span::new("a.yaml", 99, 1, 0, 0),
            "a line that is not there",
            "f",
        ));

        let rendered = diags.render();
        let rows: Vec<&str> = rendered.lines().collect();
        let quoted: Vec<usize> = rows
            .iter()
            .enumerate()
            .filter(|(_, r)| {
                r.split_once(" | ")
                    .is_some_and(|(g, _)| g.trim().parse::<u32>().is_ok())
            })
            .map(|(i, _)| i)
            .collect();
        assert_eq!(
            quoted.len(),
            1,
            "only the span with a width may quote a line:\n{rendered}"
        );
        for i in quoted {
            let under = rows.get(i + 1).copied().unwrap_or("");
            assert!(
                under.contains('^'),
                "line {} is quoted with nothing marked on it:\n{rendered}",
                rows[i]
            );
        }
    }

    #[test]
    fn errors_and_warnings_are_counted_separately() {
        let mut diags = Diagnostics::new();
        diags.push(Diagnostic::error("a", span(), "m", "f"));
        diags.push(Diagnostic::warning("b", span(), "m", "f"));
        assert_eq!(diags.error_count(), 1);
        assert_eq!(diags.warning_count(), 1);
        assert!(diags.has_errors());
    }

    #[test]
    fn sort_is_deterministic_by_file_then_position() {
        let mut diags = Diagnostics::new();
        diags.push(Diagnostic::error(
            "z",
            Span::new("b.yaml", 1, 1, 10, 11),
            "m",
            "f",
        ));
        diags.push(Diagnostic::error(
            "y",
            Span::new("a.yaml", 5, 1, 50, 51),
            "m",
            "f",
        ));
        diags.push(Diagnostic::error(
            "x",
            Span::new("a.yaml", 1, 1, 0, 1),
            "m",
            "f",
        ));
        diags.sort();
        let order: Vec<_> = diags.items().iter().map(|d| d.span.file.as_str()).collect();
        assert_eq!(order, vec!["a.yaml", "a.yaml", "b.yaml"]);
        assert_eq!(diags.items()[0].span.byte_start, 0);
    }

    #[test]
    fn merge_widens_within_one_file_and_ignores_other_files() {
        let a = Span::new("a.yaml", 5, 2, 40, 45);
        let earlier = Span::new("a.yaml", 1, 1, 0, 3);
        let merged = a.clone().merge(&earlier);
        assert_eq!(merged.byte_start, 0);
        assert_eq!(merged.byte_end, 45);
        assert_eq!(merged.line, 1);

        let other_file = Span::new("b.yaml", 1, 1, 0, 3);
        assert_eq!(a.clone().merge(&other_file), a);
    }
}
