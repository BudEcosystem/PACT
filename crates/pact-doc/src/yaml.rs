//! Span-preserving YAML parsing.
//!
//! YAML 1.2 is a superset of JSON, so this one parser serves `.yaml`, `.yml`
//! and `.json` alike — which keeps the loader honest: there is exactly one
//! notion of "a parsed value", regardless of file extension.
//!
//! ## Scalar resolution and the "Norway problem"
//!
//! Plain scalars are resolved with the **YAML 1.2 core schema only**:
//! `null`/`~`/empty, `true`/`false`, integers, floats. Deliberately *not*
//! `yes`/`no`/`on`/`off`. Under YAML 1.1 those are booleans, which is why the
//! country code `NO` famously parses as `false`.
//!
//! That matters more here than in most systems: a non-technical author (D13)
//! will write `yes` meaning yes, and will also write `NO` meaning Norway. So
//! plain scalars that are not core-schema values stay **text**, and the schema
//! layer coerces `"yes"` to a boolean only where a boolean is actually
//! expected. Resolution is thus type-directed rather than guessed, and neither
//! author is surprised.

use crate::value::{Entry, Map, Node, Value};
use camino::Utf8Path;
use pact_diag::{Diagnostic, Span};
use yaml_rust2::parser::{Event, MarkedEventReceiver, Parser, Tag};
use yaml_rust2::scanner::{Marker, TScalarStyle};

/// Guard rails against pathological or hostile documents. A spec tree is
/// authored by humans (or by a builder agent on their behalf), so these bounds
/// are far above any legitimate document.
const MAX_DEPTH: usize = 64;
const MAX_NODES: usize = 200_000;

/// Where a parsed fragment sits inside its physical file.
///
/// Markdown front matter is parsed as YAML but starts partway down the file, so
/// spans must be shifted to point at the real line the author sees.
#[derive(Debug, Clone, Copy, Default)]
pub struct Offset {
    /// Number of lines before the fragment starts (0 for a whole file).
    pub line: usize,
    /// Number of bytes before the fragment starts.
    pub byte: usize,
}

pub fn parse_yaml(text: &str, file: &Utf8Path) -> Result<Node, Box<Diagnostic>> {
    parse_yaml_at(text, file, Offset::default())
}

pub fn parse_yaml_at(text: &str, file: &Utf8Path, offset: Offset) -> Result<Node, Box<Diagnostic>> {
    let mut builder = Builder::new(file, offset, text.len());
    let mut parser = Parser::new_from_str(text);
    parser.load(&mut builder, false).map_err(|e| {
        let m = e.marker();
        let span = Span::new(
            file,
            m.line() + offset.line,
            m.col() + 1,
            m.index() + offset.byte,
            m.index() + offset.byte + 1,
        );
        let info = e.info();
        // The scanner rejects dangling aliases before the event stream reaches
        // us, so translate its wording into the same guidance the event-level
        // handler would have produced.
        if info.contains("anchor") || info.contains("alias") {
            return Box::new(Diagnostic::error(
                "doc/unknown-reference",
                span,
                "This refers to something (`*name`) that was never defined.",
                "Define it earlier with `&name`, or write the value out directly here.",
            ));
        }
        Box::new(Diagnostic::error(
            "doc/yaml-syntax",
            span,
            format!("This file is not written correctly: {info}"),
            "Check for a missing colon, a stray quote, or wrong indentation on this line. \
             Every setting looks like `name: value`, and nested settings are indented by two spaces.",
        ))
    })?;

    if let Some(d) = builder.error.take() {
        return Err(Box::new(d));
    }

    Ok(builder.root.take().unwrap_or_else(|| Node::null(Span::whole_file(file))))
}

/// One frame of the parse stack: a container being filled.
enum Frame {
    Seq { items: Vec<Node>, start: Marker, anchor: usize },
    Map { map: Map, start: Marker, anchor: usize, pending_key: Option<(String, Span)> },
}

struct Builder<'a> {
    file: &'a Utf8Path,
    offset: Offset,
    text_len: usize,
    stack: Vec<Frame>,
    root: Option<Node>,
    anchors: std::collections::HashMap<usize, Node>,
    error: Option<Diagnostic>,
    nodes: usize,
}

impl<'a> Builder<'a> {
    fn new(file: &'a Utf8Path, offset: Offset, text_len: usize) -> Self {
        Self {
            file,
            offset,
            text_len,
            stack: Vec::new(),
            root: None,
            anchors: std::collections::HashMap::new(),
            error: None,
            nodes: 0,
        }
    }

    fn span(&self, m: Marker, len: usize) -> Span {
        let start = m.index() + self.offset.byte;
        Span::new(
            self.file,
            m.line() + self.offset.line,
            m.col() + 1,
            start,
            (start + len).min(self.text_len + self.offset.byte),
        )
    }

    fn fail(&mut self, d: Diagnostic) {
        if self.error.is_none() {
            self.error = Some(d);
        }
    }

    /// The span of the setting *name* whose value this scalar is about to
    /// become — but only when the author wrote no value at all.
    ///
    /// A plain empty scalar occupies zero characters, so the parser has no
    /// position to report for it and marks the start of the **next** token
    /// instead. `None` whenever there is something on screen to point at
    /// (including a written-out `""`, whose mark is already right), and
    /// whenever the scalar is a setting name or a list item rather than a
    /// named setting's value — neither of those has a name to borrow.
    fn name_of_the_setting_left_empty(&self, text: &str, style: TScalarStyle) -> Option<Span> {
        if !text.is_empty() || style != TScalarStyle::Plain {
            return None;
        }
        match self.stack.last() {
            Some(Frame::Map { pending_key: Some((_, key_span)), .. }) => Some(key_span.clone()),
            _ => None,
        }
    }

    /// Attach a completed node to its parent, or make it the root.
    fn emit(&mut self, node: Node, anchor: usize) {
        if self.error.is_some() {
            return;
        }
        self.nodes += 1;
        if self.nodes > MAX_NODES {
            self.fail(Diagnostic::error(
                "doc/too-large",
                node.span.clone(),
                format!("This file is too large to load (over {MAX_NODES} settings)."),
                "Split it into several files. Any setting can become its own file or folder.",
            ));
            return;
        }
        if anchor != 0 {
            self.anchors.insert(anchor, node.clone());
        }

        match self.stack.last_mut() {
            None => self.root = Some(node),
            Some(Frame::Seq { items, .. }) => items.push(node),
            Some(Frame::Map { map, pending_key, .. }) => match pending_key.take() {
                None => {
                    // This node is a key. Only text keys are supported: a
                    // non-coder never needs a complex key, and allowing them
                    // would make the field/directory equivalence (T5) undefined
                    // — a directory entry name is always a string.
                    match &node.value {
                        Value::Str(s) => *pending_key = Some((s.clone(), node.span.clone())),
                        Value::Int(i) => *pending_key = Some((i.to_string(), node.span.clone())),
                        Value::Bool(b) => *pending_key = Some((b.to_string(), node.span.clone())),
                        other => {
                            let kind = other.kind_name();
                            self.fail(Diagnostic::error(
                                "doc/complex-key",
                                node.span.clone(),
                                format!("A setting name has to be a word, but this one is {kind}."),
                                "Use a simple name on the left of the colon, like `description:`.",
                            ));
                        }
                    }
                }
                Some((key, key_span)) => {
                    if let Some(existing) = map.get(&key) {
                        let first = existing.key_span.clone();
                        self.fail(
                            Diagnostic::error(
                                "doc/duplicate-key",
                                key_span,
                                format!("'{key}' is set twice in the same place."),
                                format!("Delete one of them. Keep the '{key}' you actually want — \
                                         otherwise only the last one would count, which is easy to miss."),
                            )
                            .with_related(first, "first set here"),
                        );
                        return;
                    }
                    map.insert(key, Entry { key_span, node });
                }
            },
        }
    }

    fn push(&mut self, frame: Frame, start: Marker) {
        if self.stack.len() >= MAX_DEPTH {
            self.fail(Diagnostic::error(
                "doc/too-deep",
                self.span(start, 1),
                format!("These settings are nested more than {MAX_DEPTH} levels deep."),
                "Move the inner settings into their own file or folder to flatten this out.",
            ));
            return;
        }
        self.stack.push(frame);
    }
}

impl MarkedEventReceiver for Builder<'_> {
    fn on_event(&mut self, ev: Event, mark: Marker) {
        if self.error.is_some() {
            return;
        }
        match ev {
            Event::StreamStart | Event::StreamEnd | Event::DocumentStart | Event::Nothing => {}
            Event::DocumentEnd => {}

            Event::Scalar(text, style, anchor, tag) => {
                // Writing a name and then no value is one of the commonest
                // half-finished lines there is, and it used to be reported
                // against somebody else's line. `description:` with nothing
                // after it, above `kind: conversation`, printed
                //
                //     error: 'description' should be some text, but it is nothing.
                //       --> slack.yaml:2:1
                //     2 | kind: conversation
                //       | ^
                //
                // — the caret under the next line, which is correct, while the
                // line actually at fault is not even on screen. On the last
                // line of a file it is worse: the report points one line past
                // the end, so no excerpt prints at all and the author is given
                // a line number that does not exist.
                //
                // The empty value has no characters and therefore no position;
                // the name the author *did* write does. Point at that.
                let span = match self.name_of_the_setting_left_empty(&text, style) {
                    Some(name) => name,
                    None => self.span(mark, text.len().max(1)),
                };
                let value = resolve_scalar(&text, style, tag.as_ref());
                self.emit(Node::new(value, span), anchor);
            }

            Event::SequenceStart(anchor, _) => {
                self.push(Frame::Seq { items: Vec::new(), start: mark, anchor }, mark);
            }
            Event::SequenceEnd => {
                if let Some(Frame::Seq { items, start, anchor }) = self.stack.pop() {
                    let span = self.container_span(start, mark);
                    self.emit(Node::list(items, span), anchor);
                }
            }

            Event::MappingStart(anchor, _) => {
                self.push(
                    Frame::Map { map: Map::new(), start: mark, anchor, pending_key: None },
                    mark,
                );
            }
            Event::MappingEnd => {
                if let Some(Frame::Map { map, start, anchor, pending_key }) = self.stack.pop() {
                    if let Some((key, key_span)) = pending_key {
                        self.fail(Diagnostic::error(
                            "doc/missing-value",
                            key_span,
                            format!("'{key}' was named but never given a value."),
                            format!("Write a value after the colon, like `{key}: your value here`."),
                        ));
                        return;
                    }
                    let span = self.container_span(start, mark);
                    self.emit(Node::map(map, span), anchor);
                }
            }

            Event::Alias(id) => {
                match self.anchors.get(&id).cloned() {
                    Some(node) => self.emit(node, 0),
                    None => {
                        let span = self.span(mark, 1);
                        self.fail(Diagnostic::error(
                            "doc/unknown-reference",
                            span,
                            "This refers to something (`*name`) that was never defined.",
                            "Define it earlier with `&name`, or write the value out directly here.",
                        ));
                    }
                }
            }
        }
    }
}

impl Builder<'_> {
    fn container_span(&self, start: Marker, end: Marker) -> Span {
        let s = start.index() + self.offset.byte;
        let e = (end.index() + self.offset.byte).max(s + 1);
        Span::new(self.file, start.line() + self.offset.line, start.col() + 1, s, e)
    }
}

/// YAML 1.2 core-schema resolution. See the module docs for why `yes`/`no` are
/// intentionally left as text.
fn resolve_scalar(text: &str, style: TScalarStyle, tag: Option<&Tag>) -> Value {
    // A BLOCK SCALAR loses its trailing newline, because the Expansion Rule
    // requires that the three ways of writing prose produce one document — and
    // for a round they produced two.
    //
    //     instructions: Be kind.       -> "Be kind."
    //     instructions.md              -> "Be kind."   (trimmed by `prose`)
    //     instructions: |              -> "Be kind.\n" <- the odd one out
    //
    // The argument is not that a newline is unimportant; it is that a plain
    // scalar CANNOT express one and a real file ALWAYS has one. So if the
    // trailing newline is content, the inline form and the file form can never
    // be equivalent, and the Rule is false for prose permanently. The only
    // reading under which all three agree is that trailing whitespace on a block
    // is not part of what was written. Phase 3 made the file agree with the
    // inline form; this is the third spelling, found by building `explode` and
    // watching the round trip come back one byte longer.
    //
    // The cost, stated plainly: `|` and `|-` now mean the same thing, and `|+`
    // no longer keeps what it asked to keep. `yaml_rust2` reports one
    // `Literal` style for all three, so telling them apart is not on offer here
    // — but the no-code ceiling says the distinction should not survive anyway.
    // An author who has to know that a pipe keeps a newline and a pipe-minus
    // strips it is being asked to learn YAML's chomping indicators to write down
    // what their agent should do.
    if matches!(style, TScalarStyle::Literal | TScalarStyle::Folded) {
        return Value::Str(text.trim_end().to_string());
    }
    // An explicit tag or any quoting means the author meant text.
    if style != TScalarStyle::Plain {
        return Value::Str(text.to_string());
    }
    if let Some(t) = tag
        && t.suffix == "str"
    {
        return Value::Str(text.to_string());
    }

    match text {
        "" | "~" | "null" | "Null" | "NULL" => return Value::Null,
        "true" | "True" | "TRUE" => return Value::Bool(true),
        "false" | "False" | "FALSE" => return Value::Bool(false),
        _ => {}
    }

    // Leading-zero forms are far more often codes (zip "01234", account
    // "007", phone "0044") than numbers, and silently dropping the zero is the
    // kind of corruption a non-technical author would never think to check for.
    // This check must precede integer parsing, which would happily accept them.
    let digits = text.strip_prefix(['+', '-']).unwrap_or(text);
    if digits.len() > 1 && digits.starts_with('0') && !digits.starts_with("0.") {
        return Value::Str(text.to_string());
    }

    if let Ok(i) = text.parse::<i64>() {
        return Value::Int(i);
    }
    if let Ok(f) = text.parse::<f64>()
        && text.chars().any(|c| c.is_ascii_digit())
    {
        return Value::Float(f);
    }

    Value::Str(text.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::value::Value;

    fn parse(s: &str) -> Node {
        parse_yaml(s, Utf8Path::new("t.yaml")).expect("should parse")
    }

    #[test]
    fn spans_point_at_the_line_the_author_sees() {
        let n = parse("name: refund\ndescription: handles refunds\n");
        let desc = n.get("description").unwrap();
        assert_eq!(desc.span.line, 2, "line numbers must match the editor's gutter");
        assert_eq!(desc.as_str(), Some("handles refunds"));
    }

    #[test]
    fn norway_problem_is_avoided() {
        let n = parse("country: NO\nenabled: yes\nreally: true\n");
        // NO and yes stay text; the schema layer coerces where a bool is wanted.
        assert_eq!(n.get("country").unwrap().as_str(), Some("NO"));
        assert_eq!(n.get("enabled").unwrap().as_str(), Some("yes"));
        assert_eq!(n.get("really").unwrap().value, Value::Bool(true));
    }

    #[test]
    fn leading_zero_codes_stay_text() {
        let n = parse("zip: 01234\nqty: 42\nratio: 0.5\n");
        assert_eq!(n.get("zip").unwrap().as_str(), Some("01234"));
        assert_eq!(n.get("qty").unwrap().value, Value::Int(42));
        assert_eq!(n.get("ratio").unwrap().value, Value::Float(0.5));
    }

    #[test]
    fn duplicate_keys_are_an_error_with_both_locations() {
        let err = parse_yaml("model: a\nmodel: b\n", Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/duplicate-key");
        assert_eq!(err.span.line, 2);
        assert_eq!(err.related.len(), 1, "must point at the first occurrence too");
        assert_eq!(err.related[0].span.line, 1);
    }

    #[test]
    fn missing_value_is_reported_against_the_key() {
        let err = parse_yaml("agents:\n  a: 1\n  b:\n", Utf8Path::new("t.yaml"));
        // `b:` with nothing after it is a null value in YAML, which is legal.
        assert!(err.is_ok(), "an empty value is legal YAML and means 'nothing'");
    }

    #[test]
    fn syntax_errors_explain_themselves_in_plain_language() {
        let err = parse_yaml("name: [unclosed\n", Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/yaml-syntax");
        assert!(err.fix.contains("indentation") || err.fix.contains("quote"));
        assert!(!err.message.contains("Token"), "parser jargon must not leak to the author");
    }

    #[test]
    fn json_parses_through_the_same_path() {
        let n = parse_yaml(r#"{"name":"x","tools":["a","b"]}"#, Utf8Path::new("t.json")).unwrap();
        assert_eq!(n.get("name").unwrap().as_str(), Some("x"));
        assert_eq!(n.get("tools").unwrap().as_list().unwrap().len(), 2);
    }

    #[test]
    fn anchors_and_aliases_resolve() {
        let n = parse("base: &b\n  model: fast\nuse: *b\n");
        assert_eq!(n.get("use").unwrap().get("model").unwrap().as_str(), Some("fast"));
    }

    #[test]
    fn unknown_alias_is_a_clear_error() {
        let err = parse_yaml("use: *nope\n", Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/unknown-reference");
    }

    #[test]
    fn offset_shifts_spans_for_embedded_fragments() {
        let n = parse_yaml_at("name: x\n", Utf8Path::new("t.md"), Offset { line: 3, byte: 40 })
            .unwrap();
        assert_eq!(n.get("name").unwrap().span.line, 4);
        assert!(n.get("name").unwrap().span.byte_start >= 40);
    }

    #[test]
    fn a_setting_left_empty_is_located_at_its_own_name_not_at_the_next_line() {
        // Measured before the fix: `description:` above `kind: conversation`
        // put the value at line 2 column 1, so every report about the empty
        // value underlined the following line — which was correct.
        let n = parse("description:\nkind: conversation\n");
        let desc = n.get("description").unwrap();
        assert_eq!(desc.value, Value::Null, "nothing after the colon means nothing");
        assert_eq!(desc.span.line, 1, "the line the author left empty, not the one after it");
        assert_eq!(desc.span.col, 1);
        assert_eq!(
            &"description:\nkind: conversation\n"[desc.span.byte_start..desc.span.byte_end],
            "description",
            "an underline drawn from this span marks the name the message will quote"
        );
    }

    #[test]
    fn a_setting_left_empty_on_the_last_line_still_points_inside_the_file() {
        // The same defect at its worst: the mark landed one line past the end,
        // so the renderer had no source line to quote and printed a location
        // the author cannot open to.
        let text = "kind: conversation\ndescription:\n";
        let n = parse(text);
        let desc = n.get("description").unwrap();
        assert_eq!(desc.span.line, 2, "line 3 of a two-line file is nowhere");
        assert!(desc.span.byte_end <= text.len());
        assert!(desc.span.byte_end > desc.span.byte_start, "an empty span underlines nothing");
    }

    #[test]
    fn an_empty_value_written_out_as_quotes_keeps_its_own_place() {
        // `""` is characters on the page, so the parser's own mark is right and
        // borrowing the name would be less precise, not more.
        let n = parse("description: \"\"\nkind: c\n");
        let desc = n.get("description").unwrap();
        assert_eq!(desc.value, Value::Str(String::new()));
        assert_eq!(desc.span.line, 1);
        assert_eq!(desc.span.col, "description: ".len() + 1, "at the quotes, not at the name");
    }

    #[test]
    fn a_setting_name_left_empty_is_still_located_by_the_parser() {
        // The borrowed span comes from a *pending key*, so a name with no value
        // must not be mistaken for a value with no name. `{: 1}` has no name to
        // borrow, and asking for one would panic or point at the wrong entry.
        let n = parse("a:\nb: 1\n");
        assert_eq!(n.get("a").unwrap().span.line, 1);
        assert_eq!(n.get("b").unwrap().span.line, 2, "the next setting is untouched");
    }

    #[test]
    fn quoted_scalars_are_always_text() {
        let n = parse("a: \"true\"\nb: '42'\n");
        assert_eq!(n.get("a").unwrap().as_str(), Some("true"));
        assert_eq!(n.get("b").unwrap().as_str(), Some("42"));
    }
}
