//! Reading a `.pact` file into a document.
//!
//! # What a line can be
//!
//! | Line | Recognised by | Becomes |
//! |---|---|---|
//! | a header | starts at the left margin | a block: `agent desk`, `tool payments`, `workspace "Name"`, `when …` |
//! | a setting | `key:` then a space or the end of the line | that field, read by the YAML reader with everything indented beneath it |
//! | a sentence | one of the openings below, for the kind of block it is in | the field or fields the table gives |
//! | a text block | one bare word, with lines indented beneath it | that field, holding the lines as written |
//!
//! # The sentences
//!
//! | In | Sentence | Becomes |
//! |---|---|---|
//! | agent | `takes <field>: <shape>, …` | `accepts:` |
//! | agent | `gives <field>: <shape>, …` | `answers-with:` |
//! | agent | `uses <name>, …` | `uses:` |
//! | agent | `asks <agent>: <what for>` | one line of `team:` |
//! | agent | `at most <n> steps` · `tool calls` · `tokens` | `limits.steps-at-most:` · `tool-calls-at-most:` · `tokens-at-most:` |
//! | agent | `spends under <money> a request` | `limits.cost-per-request-under:` |
//! | agent | `when it runs out: <what>` | `limits.when-it-runs-out:` |
//! | agent | `remembers <name>` + body | one entry of `remembers:` |
//! | agent | `listens for topic <t>: asked first` · `told after` | one line of `listens-for:` |
//! | agent, top | `when <signal>` + body | a reaction; in an agent, one that agent names |
//! | tool, knowledge | `about <topic>, …` | `topics:` |
//! | policy | `before <tool>/<action>[, when <arg> is more than <x>]: ask <question>, because <why>` | one `ask-a-person:` rule |
//! | reaction, event | `when <signal>` | the signal's fields |
//! | reaction | `remind it: <text>` · `consult <agent>` · `tell <agent>` · `stop and say: <text>` | one step of `then:` |
//! | reaction | `called <name>` · `every time` | its name · `fires: every-time` |
//! | workflow, program | `takes …` · `gives …` | `accepts:` (a program's `takes:`) · `answers-with:` |
//! | workflow, loop | a statement: `call`, `for each`, `repeat`, `together`, `decide`, `answer`, … | one stage of `steps:`, in the order written (`read/flow.rs`) |
//! | any block | `based on <name> [with <name>: <value>, …]` | `based-on:`, and `with:` for what the base `expects:` |
//! | top | `let <name> = <figure>` | one entry of `values:` |
//!
//! Signals, after `when`: `the agent is about to call <tool>`, `the agent has
//! called <tool> more than <n> times`, `<tool> has answered`, `the agent has
//! taken more than <n> steps`, `a turn starts`, `the agent is about to ask a
//! teammate`, `the agent has written a step`, `the work touches <topic>`, `it
//! looks like <description>`, `<event> happens`.
//!
//! A header or a sentence may end in a comment — a space, `#`, and anything
//! after it — as a setting may. Inside a text block a `#` is text.
//!
//! # What is refused here
//!
//! Only what makes a line unreadable: a line that is none of the four, a
//! header nobody knows, a block or a setting written twice, a margin that does
//! not line up. Whether the document that comes out is a valid workspace is
//! `pact check`'s to say, with the rules it already has.

use std::ops::Range;

use camino::{Utf8Path, Utf8PathBuf};
use pact_diag::{Diagnostic, Span};
use pact_doc::{Entry, Map, Node, Offset, Value, parse_yaml_at};

use crate::{COLLECTIONS, SINGLES, collection_of, slug};

mod flow;

/// What reading a file produced: always a document, and whatever was wrong.
pub struct Parsed {
    pub node: Node,
    pub diagnostics: Vec<Diagnostic>,
}

/// Read one `.pact` file.
pub fn read(text: &str, file: &Utf8Path) -> Parsed {
    let mut reader = Reader::new(text, file);
    reader.top();
    let side = std::mem::take(&mut reader.side);
    for (id, span, node) in side {
        reader.add_root("reactions", id, span, node);
    }
    let end = text.len();
    let root = std::mem::take(&mut reader.root);
    Parsed {
        node: Node::map(root, Span::new(file, 1, 1, 0, end.max(1))),
        diagnostics: reader.diags,
    }
}

#[derive(Clone, Copy)]
struct Line<'a> {
    /// 1-based.
    no: usize,
    /// Byte offset of the start of the line in the file.
    start: usize,
    /// Byte offset of the end of the line, before its line break.
    end: usize,
    /// Byte offset of the first character of `text` in the file.
    text_at: usize,
    /// How many spaces it is indented by.
    indent: usize,
    /// The line with its margin and trailing white space removed.
    text: &'a str,
}

impl Line<'_> {
    fn quiet(&self) -> bool {
        self.text.is_empty() || self.text.starts_with('#')
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Agent,
    /// A tool or a set of documents: something that can be `about` a topic.
    Tagged,
    Policy,
    Reaction,
    /// A named signal: it can say `when …`, and nothing a reaction does.
    Event,
    /// A workflow or a loop: its statements are its steps (`read/flow.rs`).
    Flow,
    /// The inside of a `for each`, a `repeat` or a `together`: statements, and
    /// the settings of the stage they are inside.
    Stage,
    /// Beneath a `decide`: its settings, and an `if` for each label.
    Decision,
    Program,
    Plain,
}

impl Kind {
    fn of(word: &str) -> Kind {
        match word {
            "agent" => Kind::Agent,
            "tool" | "knowledge" => Kind::Tagged,
            "policy" => Kind::Policy,
            "reaction" => Kind::Reaction,
            "event" => Kind::Event,
            "workflow" | "loop" => Kind::Flow,
            "program" => Kind::Program,
            _ => Kind::Plain,
        }
    }

    /// The sentence openings this kind of block knows, for a refusal's fix.
    fn sentences(self) -> &'static [&'static str] {
        match self {
            Kind::Agent => &[
                "takes", "gives", "uses", "asks", "at most", "spends under", "when it runs out:",
                "remembers", "listens for", "when",
            ],
            Kind::Tagged => &["about"],
            Kind::Policy => &["before"],
            Kind::Reaction => &[
                "when", "remind it:", "consult", "tell", "stop and say:", "called", "every time",
            ],
            Kind::Event => &["when"],
            Kind::Flow => &[
                "takes", "gives", "call", "for each", "repeat", "together", "decide", "answer",
                "stop", "ask", "think", "use tools", "check its work", "run code",
            ],
            Kind::Stage => flow::OPENINGS,
            Kind::Decision => &["if"],
            Kind::Program => &["takes", "gives"],
            Kind::Plain => &[],
        }
    }
}

struct Reader<'a> {
    file: Utf8PathBuf,
    text: &'a str,
    lines: Vec<Line<'a>>,
    diags: Vec<Diagnostic>,
    root: Map,
    /// Reactions written inside an agent's block, to be filed under
    /// `reactions:` once the whole file is read.
    side: Vec<(String, Span, Node)>,
    /// `called <name>`, for the reaction block being read.
    called: Option<(String, Span)>,
    /// The description a `when` sentence gives a reaction that writes none.
    described: Option<(String, Span)>,
}

fn s(text: impl Into<String>, span: &Span) -> Node {
    Node::str(text, span.clone())
}

fn map_of(entries: Vec<(&str, Node)>, span: &Span) -> Node {
    let mut m = Map::new();
    for (k, node) in entries {
        m.insert(
            k.to_string(),
            Entry {
                key_span: span.clone(),
                node,
            },
        );
    }
    Node::map(m, span.clone())
}

/// The length of the key at the start of a setting line — `key:` followed by a
/// space or the end of the line — or `None` when the line is not a setting.
fn setting_key(text: &str) -> Option<usize> {
    let end = if text.starts_with('"') {
        quoted_len(text)?
    } else if let Some(rest) = text.strip_prefix('\'') {
        rest.find('\'')? + 2
    } else {
        let n = text
            .char_indices()
            .find(|(_, c)| !(c.is_alphanumeric() || matches!(c, '_' | '-' | '.' | '/')))
            .map_or(text.len(), |(i, _)| i);
        if n == 0 || text.starts_with('-') {
            return None;
        }
        n
    };
    let after = &text[end..];
    (after == ":" || after.starts_with(": ")).then_some(end)
}

/// The length of the double-quoted text `text` starts with, quotes included.
fn quoted_len(text: &str) -> Option<usize> {
    let rest = text.strip_prefix('"')?;
    let mut escaped = false;
    for (i, c) in rest.char_indices() {
        match c {
            _ if escaped => escaped = false,
            '\\' => escaped = true,
            '"' => return Some(i + 2),
            _ => {}
        }
    }
    None
}

/// A header or a sentence without the comment after it: ` #` and everything
/// to its right, as in YAML — unless the `#` is inside double quotes.
fn uncommented(text: &str) -> &str {
    let mut quoted = false;
    let mut before = ' ';
    for (i, c) in text.char_indices() {
        match c {
            '"' if before != '\\' => quoted = !quoted,
            '#' if !quoted && before == ' ' && i > 0 => return text[..i].trim_end(),
            _ => {}
        }
        before = c;
    }
    text
}

fn bare_word(text: &str) -> bool {
    !text.is_empty() && text.chars().all(|c| c.is_alphanumeric() || matches!(c, '_' | '-'))
}

fn capitalised(text: &str) -> String {
    let mut c = text.chars();
    match c.next() {
        Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        None => String::new(),
    }
}

/// The description a reaction has when it writes none: the sentence it was
/// written as. A judgement's is the thing judged, because that sentence is
/// the question the judge answers.
pub(crate) fn default_description(signal: &str, judged: Option<&str>) -> String {
    let text = match judged {
        Some(what) => capitalised(what.trim()),
        None => format!("When {}", signal.trim()),
    };
    if text.ends_with(['.', '?', '!']) { text } else { format!("{text}.") }
}

impl<'a> Reader<'a> {
    fn new(text: &'a str, file: &Utf8Path) -> Self {
        let mut lines = Vec::new();
        let mut diags = Vec::new();
        let mut start = 0;
        let mut told_about_tabs = false;
        for (i, raw) in text.split('\n').enumerate() {
            let raw_len = raw.len();
            let raw = raw.strip_suffix('\r').unwrap_or(raw);
            let margin: &str = &raw[..raw.len() - raw.trim_start().len()];
            if margin.contains('\t') && !raw.trim().is_empty() && !told_about_tabs {
                told_about_tabs = true;
                diags.push(Diagnostic::error(
                    "lang/a-tab-in-the-margin",
                    Span::new(file, i + 1, 1, start, start + margin.len().max(1)),
                    "This line is indented with a tab, and how far a tab reaches depends on \
                     the editor showing it — so what is inside what cannot be told.",
                    "Indent with spaces: two for each level.",
                ));
            }
            lines.push(Line {
                no: i + 1,
                start,
                end: start + raw.len(),
                text_at: start + margin.len(),
                indent: margin.chars().map(|c| if c == '\t' { 2 } else { 1 }).sum(),
                text: raw.trim(),
            });
            start += raw_len + 1;
        }
        Reader {
            file: file.to_owned(),
            text,
            lines,
            diags,
            root: Map::new(),
            side: Vec::new(),
            called: None,
            described: None,
        }
    }

    /// The span of `len` bytes of a line's text, starting `from` bytes in.
    fn at(&self, l: &Line, from: usize, len: usize) -> Span {
        let byte = l.text_at + from;
        let col = l.indent + l.text[..from.min(l.text.len())].chars().count() + 1;
        Span::new(&self.file, l.no, col, byte, byte + len.max(1))
    }

    fn whole(&self, l: &Line) -> Span {
        self.at(l, 0, l.text.len())
    }

    fn error(&mut self, rule: &'static str, span: Span, message: String, fix: String) {
        self.diags.push(Diagnostic::error(rule, span, message, fix));
    }

    // ── the top of the file ────────────────────────────────────────────────

    fn top(&mut self) {
        let n = self.lines.len();
        let mut i = 0;
        while i < n {
            let l = self.lines[i];
            if l.quiet() {
                i += 1;
                continue;
            }
            let mut j = i + 1;
            while j < n && (self.lines[j].quiet() || self.lines[j].indent > 0) {
                j += 1;
            }
            if l.indent > 0 {
                let span = self.whole(&l);
                self.error(
                    "lang/a-line-in-no-block",
                    span,
                    "This line is indented, and nothing above it starts a block for it to be \
                     inside."
                        .to_string(),
                    "Start a block at the left margin first — `workspace \"Its name\"`, \
                     `agent <name>`, `tool <name>` — and indent this under it."
                        .to_string(),
                );
            } else {
                self.header(i, i + 1..j);
            }
            i = j;
        }
    }

    fn header(&mut self, i: usize, body: Range<usize>) {
        self.lines[i].text = uncommented(self.lines[i].text);
        let l = self.lines[i];
        let (word, rest_at) = match l.text.find(' ') {
            Some(n) => (&l.text[..n], n + 1),
            None => (l.text, l.text.len()),
        };
        let block = self.whole(&l);
        if word == "workspace" {
            let name = l.text[rest_at..].trim();
            let name_span = self.at(&l, rest_at, l.text.len() - rest_at);
            let name = self.unquoted(name, &name_span);
            if !name.is_empty() {
                let node = s(name, &name_span);
                self.put_root("name".to_string(), name_span, node);
            }
            let settings = self.body(body, Kind::Plain);
            for (k, e) in settings {
                self.put_root(k, e.key_span, e.node);
            }
            return;
        }
        if word == "let" {
            self.let_line(&l, rest_at, body);
            return;
        }
        if word == "when" {
            if let Some((id, span, node)) = self.when(i, rest_at, body, true) {
                self.add_root("reactions", id, span, node);
            }
            return;
        }
        if SINGLES.contains(&word) && rest_at >= l.text.len() {
            let settings = self.body(body, Kind::Plain);
            self.put_root(word.to_string(), block.clone(), Node::map(settings, block));
            return;
        }
        let Some(collection) = collection_of(word) else {
            self.unknown_header(&l, word);
            return;
        };
        let Some((id, id_span, next)) = self.name(&l, rest_at) else {
            self.error(
                "lang/a-block-with-no-name",
                block,
                format!("This `{word}` block does not say which {word} it is."),
                format!("Write its name after the word: `{word} <name>`."),
            );
            return;
        };
        let shown = self.name(&l, next);
        let kind = Kind::of(word);
        let saved = (self.called.take(), self.described.take());
        let mut settings = self.body(body, kind);
        if matches!(kind, Kind::Reaction | Kind::Event) {
            if let Some((_, span)) = self.called.take() {
                self.error(
                    "lang/said-twice",
                    span,
                    format!("This is already named '{id}', on the line that starts it."),
                    "Take this line out.".to_string(),
                );
            }
            if let Some((text, span)) = self.described.take()
                && !settings.contains_key("description")
            {
                settings.insert(
                    "description".to_string(),
                    Entry {
                        key_span: span.clone(),
                        node: s(text, &span),
                    },
                );
            }
        }
        (self.called, self.described) = saved;
        if let Some((shown, shown_span, _)) = shown {
            if word == "agent" {
                let node = s(shown, &shown_span);
                self.put(&mut settings, "name".to_string(), shown_span, node);
            } else {
                self.error(
                    "lang/a-second-name",
                    shown_span,
                    format!(
                        "A `{word}` has one name, and this line gives two. Only an agent has \
                         a second name for people to read."
                    ),
                    format!("Write `{word} {id}` and nothing after it."),
                );
            }
        }
        self.add_root(collection, id, id_span, Node::map(settings, block));
    }

    /// `let refund-limit = 200 USD` — a figure with a name: one entry of
    /// `values:`, used wherever it belongs as `{use: refund-limit}` in a
    /// setting or `values.refund-limit` in a binding.
    fn let_line(&mut self, l: &Line, at: usize, body: Range<usize>) {
        let said = &l.text[at.min(l.text.len())..];
        let whole = self.whole(l);
        let split = said
            .split_once(" = ")
            .map(|(n, f)| (n.trim(), f.trim()))
            .filter(|(n, f)| bare_word(n) && !f.is_empty());
        let Some((name, figure)) = split else {
            self.error(
                "lang/not-a-line",
                whole,
                "A `let` line gives a figure a name.".to_string(),
                "Write `let <name> = <figure>` — `let refund-limit = 200 USD`.".to_string(),
            );
            return;
        };
        if self.significant(&body) {
            let under = self.whole(&self.lines[body.start]);
            self.error(
                "lang/nothing-goes-under-this",
                under,
                "Nothing goes under a `let` line.".to_string(),
                format!(
                    "To say more about a figure — what it is, what kind — write a `value {name}` \
                     block, with `value:` and `description:` beneath it."
                ),
            );
        }
        let ns = self.at(l, at + said.find(name).unwrap_or(0), name.len());
        let fs = self.at(l, l.text.len() - figure.len(), figure.len());
        let parsed = parse_yaml_at(&format!("v: {figure}"), &self.file, Offset::default())
            .ok()
            .and_then(|n| n.get("v").map(|v| v.value.clone()));
        if matches!(parsed, Some(Value::Map(_) | Value::List(_))) {
            self.error(
                "lang/not-a-line",
                fs,
                "A `let` line holds one figure, and this is a list or a set of settings.".to_string(),
                format!("Write a `value {name}` block, with `value:` beneath it."),
            );
            return;
        }
        let node = self.scalar(figure, &fs);
        self.add_root("values", name.to_string(), ns, map_of(vec![("value", node)], &whole));
    }

    fn unknown_header(&mut self, l: &Line, word: &str) {
        let span = self.at(l, 0, word.len());
        if setting_key(l.text).is_some() {
            self.error(
                "lang/a-setting-in-no-block",
                span,
                "This is a setting, and it is at the left margin — so nothing says what it is a \
                 setting OF."
                    .to_string(),
                "Indent it under the block it belongs to. A setting of the whole workspace goes \
                 under a `workspace \"Its name\"` line."
                    .to_string(),
            );
            return;
        }
        let mut words: Vec<&str> = COLLECTIONS.iter().map(|(w, _)| *w).collect();
        words.extend(SINGLES);
        words.extend(["workspace", "when", "let"]);
        let fix = match pact_schema::suggest::closest(word, &words) {
            Some(near) => format!("Did you mean `{near}`?"),
            None => format!("A block starts with one of: {}.", words.join(", ")),
        };
        self.error(
            "lang/no-such-block",
            span,
            format!("'{word}' does not start any kind of block."),
            fix,
        );
    }

    /// One name on a header line, bare or in double quotes, starting `from`
    /// bytes in: the name, where it is, and where the next thing starts.
    fn name(&mut self, l: &Line, from: usize) -> Option<(String, Span, usize)> {
        let rest = l.text.get(from..)?;
        let skipped = rest.len() - rest.trim_start().len();
        let rest = rest.trim_start();
        let from = from + skipped;
        if rest.is_empty() {
            return None;
        }
        if rest.starts_with('"') {
            let len = quoted_len(rest).unwrap_or(rest.len());
            let span = self.at(l, from, len);
            let text = self.unquoted(&rest[..len], &span);
            return Some((text, span, from + len));
        }
        let len = rest.find(' ').unwrap_or(rest.len());
        Some((rest[..len].to_string(), self.at(l, from, len), from + len))
    }

    /// Text that may be in double quotes, without them.
    fn unquoted(&mut self, text: &str, span: &Span) -> String {
        if !text.starts_with('"') {
            return text.to_string();
        }
        match serde_json::from_str::<String>(text) {
            Ok(inner) => inner,
            Err(_) => {
                self.error(
                    "lang/a-quote-left-open",
                    span.clone(),
                    "This starts with a double quote and does not end with one.".to_string(),
                    "Close the quote, or take the opening one out.".to_string(),
                );
                text.trim_matches('"').to_string()
            }
        }
    }

    // ── putting things in the document ─────────────────────────────────────

    /// Set `key` in `map`. Two sets of settings under one key become one; the
    /// same setting twice is refused.
    fn put(&mut self, map: &mut Map, key: String, key_span: Span, node: Node) {
        let Some(existing) = map.get_mut(&key) else {
            map.insert(key, Entry { key_span, node });
            return;
        };
        match (&mut existing.node.value, node.value) {
            (Value::Map(_), Value::Map(new)) => {
                for (k, e) in new {
                    if let Value::Map(have) = &mut existing.node.value {
                        let mut inner = std::mem::take(have);
                        self.put(&mut inner, k, e.key_span, e.node);
                        *have = inner;
                    }
                }
            }
            _ => {
                let prior = existing.key_span.clone();
                self.diags.push(
                    Diagnostic::error(
                        "lang/said-twice",
                        key_span,
                        format!("'{key}' is set twice."),
                        "Keep one of them.",
                    )
                    .with_related(prior, "also set here"),
                );
            }
        }
    }

    fn put_root(&mut self, key: String, key_span: Span, node: Node) {
        let mut root = std::mem::take(&mut self.root);
        self.put(&mut root, key, key_span, node);
        self.root = root;
    }

    /// File one entry of a collection, refusing a second of the same name.
    fn add_root(&mut self, collection: &str, id: String, id_span: Span, node: Node) {
        let mut root = std::mem::take(&mut self.root);
        let holder = root.entry(collection.to_string()).or_insert_with(|| Entry {
            key_span: id_span.clone(),
            node: Node::map(Map::new(), id_span.clone()),
        });
        match holder.node.as_map_mut() {
            Some(entries) => {
                if let Some(prior) = entries.get(&id) {
                    let prior = prior.key_span.clone();
                    self.diags.push(
                        Diagnostic::error(
                            "lang/said-twice",
                            id_span,
                            format!("'{id}' is written twice under `{collection}`."),
                            "Keep one block, or give one of them another name.",
                        )
                        .with_related(prior, "also written here"),
                    );
                } else {
                    entries.insert(
                        id,
                        Entry {
                            key_span: id_span,
                            node,
                        },
                    );
                }
            }
            None => self.diags.push(Diagnostic::error(
                "lang/said-twice",
                id_span,
                format!(
                    "`{collection}` is written as one setting of the workspace, and also as a \
                     block of its own."
                ),
                "Keep the blocks and take the setting out of the `workspace` block.",
            )),
        }
        self.root = root;
    }

    fn add(&mut self, map: &mut Map, field: &str, key: String, key_span: Span, node: Node) {
        let mut one = Map::new();
        one.insert(key, Entry { key_span: key_span.clone(), node });
        self.put(map, field.to_string(), key_span.clone(), Node::map(one, key_span));
    }

    /// Add one line to a list that sentences build a line at a time — the
    /// steps of a reaction, the things an agent listens for.
    fn push(&mut self, map: &mut Map, field: &str, node: Node) {
        if let Some(Value::List(have)) = map.get_mut(field).map(|e| &mut e.node.value) {
            have.push(node);
            return;
        }
        let span = node.span.clone();
        self.put(map, field.to_string(), span.clone(), Node::list(vec![node], span));
    }

    // ── a block's body ─────────────────────────────────────────────────────

    fn body(&mut self, range: Range<usize>, kind: Kind) -> Map {
        if kind == Kind::Flow {
            return self.flow_body(range, kind, true);
        }
        let mut map = Map::new();
        for (first, rest) in self.items(range) {
            self.item(first, rest, kind, &mut map);
        }
        map
    }

    /// The lines of a body that start something, each with the lines beneath it.
    fn items(&mut self, range: Range<usize>) -> Vec<(usize, Range<usize>)> {
        let Some(base) = range
            .clone()
            .map(|k| self.lines[k])
            .find(|l| !l.quiet())
            .map(|l| l.indent)
        else {
            return Vec::new();
        };
        let mut out = Vec::new();
        let mut k = range.start;
        while k < range.end {
            let l = self.lines[k];
            if l.quiet() {
                k += 1;
                continue;
            }
            if l.indent < base {
                let span = self.whole(&l);
                self.error(
                    "lang/does-not-line-up",
                    span,
                    format!(
                        "This line is indented by {} and the lines above it by {base}, so it is \
                         not clear what it is inside.",
                        l.indent
                    ),
                    format!("Indent it by {base} spaces to sit beside them."),
                );
            }
            let first = k;
            let a_setting = setting_key(l.text).is_some();
            k += 1;
            while k < range.end {
                let m = self.lines[k];
                let dash = m.text == "-" || m.text.starts_with("- ");
                if m.quiet() || m.indent > l.indent || (a_setting && m.indent == l.indent && dash) {
                    k += 1;
                } else {
                    break;
                }
            }
            out.push((first, first + 1..k));
        }
        out
    }

    fn significant(&self, range: &Range<usize>) -> bool {
        range.clone().any(|k| !self.lines[k].quiet())
    }

    fn item(&mut self, first: usize, rest: Range<usize>, kind: Kind, map: &mut Map) {
        let l = self.lines[first];
        if setting_key(l.text).is_some() {
            self.setting(first, rest, map);
            return;
        }
        // Not a setting, so not YAML's to read: the comment after it is taken
        // off here, the way YAML takes one off a setting.
        self.lines[first].text = uncommented(l.text);
        let l = self.lines[first];
        // `based on <name>` — what this starts from, restating only what
        // differs. The one sentence every kind of block knows, because
        // `based-on:` is resolved before anything knows what kind it is.
        if let Some(at) = after(l.text, "based on ") {
            let said = &l.text[at..];
            // `with <name>: <value>, …` fills what the base left open
            // (`expects:`), as `with:` does.
            let (name, with) = match said.find(" with ") {
                Some(n) => (said[..n].trim(), Some(at + n + " with ".len())),
                None => (said.trim(), None),
            };
            if !name.is_empty() {
                let span = self.at(&l, at, name.len());
                if self.significant(&rest) {
                    let under = self.whole(&self.lines[rest.start]);
                    self.error(
                        "lang/nothing-goes-under-this",
                        under,
                        "Nothing goes under a line that says what this is based on.".to_string(),
                        "Move this line out to sit beside the one above it.".to_string(),
                    );
                }
                let name = self.unquoted(name, &span);
                self.put(map, "based-on".to_string(), self.whole(&l), s(name, &span));
                if let Some(with) = with
                    && let Some(node) = self.given(&l, with)
                {
                    self.put(map, "with".to_string(), self.whole(&l), node);
                }
                return;
            }
        }
        if self.sentence(first, rest.clone(), kind, map) {
            return;
        }
        if bare_word(l.text) && self.significant(&rest) {
            let span = self.whole(&l);
            let text = self.text_block(&l, rest);
            self.put(map, l.text.to_string(), span.clone(), s(text, &span));
            return;
        }
        let span = self.whole(&l);
        let opening = kind.sentences();
        let word = l.text.split(' ').next().unwrap_or_default();
        let fix = if bare_word(l.text) {
            format!(
                "For a setting, write `{}: <value>`. For several lines of text, indent them \
                 under this line.",
                l.text
            )
        } else if opening.is_empty() {
            "Write it as a setting: `name: value`.".to_string()
        } else {
            match pact_schema::suggest::closest(word, opening) {
                Some(near) if near != word => format!("Did you mean a line starting `{near}`?"),
                _ => format!(
                    "Write a setting — `name: value` — or a sentence starting with one of: {}.",
                    opening.join(", ")
                ),
            }
        };
        self.error(
            "lang/not-a-line",
            span,
            "This line is not a setting, and not a sentence this kind of block knows.".to_string(),
            fix,
        );
    }

    /// A setting and everything beneath it, handed to the YAML reader as it
    /// stands — so anything YAML can say, a setting can.
    fn setting(&mut self, first: usize, rest: Range<usize>, map: &mut Map) {
        let l = self.lines[first];
        let last = rest
            .clone()
            .rev()
            .find(|k| !self.lines[*k].quiet())
            .unwrap_or(first);
        let chunk = &self.text[l.start..self.lines[last].end];
        let offset = Offset {
            line: l.no - 1,
            byte: l.start,
        };
        match parse_yaml_at(chunk, &self.file, offset) {
            Ok(node) => match node.value {
                Value::Map(settings) => {
                    for (k, e) in settings {
                        self.put(map, k, e.key_span, e.node);
                    }
                }
                _ => {
                    let span = self.whole(&l);
                    self.error(
                        "lang/not-a-line",
                        span,
                        "This reads as a setting, and it is not one.".to_string(),
                        "Write `name: value`.".to_string(),
                    );
                }
            },
            Err(d) => self.diags.push(*d),
        }
    }

    /// The lines under a bare word, as the text they are: their common margin
    /// removed, blank lines kept, and nothing after the last line.
    fn text_block(&self, head: &Line, rest: Range<usize>) -> String {
        let inside: Vec<Line> = rest.map(|k| self.lines[k]).collect();
        let margin = inside
            .iter()
            .filter(|l| !l.text.is_empty() && l.indent > head.indent)
            .map(|l| l.indent)
            .min()
            .unwrap_or(0);
        let mut out: Vec<String> = Vec::new();
        for l in &inside {
            if l.text.is_empty() {
                out.push(String::new());
            } else if l.indent >= margin {
                out.push(format!("{}{}", " ".repeat(l.indent - margin), l.text));
            }
        }
        out.join("\n").trim_end().to_string()
    }

    // ── sentences ──────────────────────────────────────────────────────────

    /// Read one sentence into `map`. `false` when the line is not one this
    /// kind of block knows.
    fn sentence(&mut self, first: usize, rest: Range<usize>, kind: Kind, map: &mut Map) -> bool {
        let l = self.lines[first];
        let t = l.text;
        let span = self.whole(&l);
        let lone = |me: &mut Self, what: &str| {
            if me.significant(&rest) {
                let under = me.lines[rest.clone().find(|k| !me.lines[*k].quiet()).unwrap_or(first)];
                let span = me.whole(&under);
                me.error(
                    "lang/nothing-goes-under-this",
                    span,
                    format!("Nothing goes under a line that says {what}."),
                    "Move this line out to sit beside the one above it.".to_string(),
                );
            }
        };
        match kind {
            Kind::Agent => {
                if let Some(at) = after(t, "takes ") {
                    lone(self, "what an agent takes");
                    if let Some(node) = self.shapes(&l, at) {
                        self.put(map, "accepts".into(), span, node);
                    }
                } else if let Some(at) = after(t, "gives ") {
                    lone(self, "what an agent gives");
                    if let Some(node) = self.shapes(&l, at) {
                        self.put(map, "answers-with".into(), span, node);
                    }
                } else if let Some(at) = after(t, "uses ") {
                    lone(self, "what an agent uses");
                    let node = self.names(&l, at);
                    self.put(map, "uses".into(), span, node);
                } else if let Some(at) = after(t, "asks ") {
                    lone(self, "who an agent asks");
                    self.asks(&l, at, map);
                } else if let Some(at) = after(t, "at most ") {
                    lone(self, "a limit");
                    self.at_most(&l, at, map);
                } else if let Some(at) = after(t, "spends under ") {
                    lone(self, "a limit");
                    let Some(money) = t[at..].strip_suffix(" a request") else {
                        self.error(
                            "lang/not-a-line",
                            span,
                            "A spending limit says what it is a limit FOR.".to_string(),
                            "Write `spends under 0.50 USD a request`.".to_string(),
                        );
                        return true;
                    };
                    let vs = self.at(&l, at, money.len());
                    self.add(map, "limits", "cost-per-request-under".into(), vs.clone(), s(money.trim(), &vs));
                } else if let Some(at) = after(t, "when it runs out:") {
                    lone(self, "a limit");
                    let what = t[at..].trim();
                    let vs = self.at(&l, at, t.len() - at);
                    self.add(map, "limits", "when-it-runs-out".into(), vs.clone(), s(what.replace(' ', "-"), &vs));
                } else if let Some(at) = after(t, "remembers ") {
                    let Some((id, id_span, _)) = self.name(&l, at) else { return true };
                    let settings = self.body(rest, Kind::Plain);
                    self.add(map, "remembers", id, id_span, Node::map(settings, span));
                } else if let Some(at) = after(t, "listens for ") {
                    lone(self, "what an agent listens for");
                    self.listens(&l, at, map);
                } else if let Some(at) = after(t, "when ") {
                    if let Some((id, id_span, node)) = self.when(first, at, rest, false) {
                        self.push(map, "reactions", s(id.clone(), &id_span));
                        self.side.push((id, id_span, node));
                    }
                } else {
                    return false;
                }
                true
            }
            Kind::Tagged => {
                let Some(at) = after(t, "about ") else { return false };
                lone(self, "what something is about");
                let node = self.names(&l, at);
                self.put(map, "topics".into(), span, node);
                true
            }
            Kind::Policy => {
                let Some(at) = after(t, "before ") else { return false };
                lone(self, "when to ask a person");
                self.before(&l, at, map);
                true
            }
            Kind::Reaction => {
                if let Some(at) = after(t, "when ") {
                    lone(self, "what a reaction waits for");
                    if let Some((fields, described)) = self.signal(&l, at) {
                        for (k, node) in fields {
                            self.put(map, k.to_string(), span.clone(), node);
                        }
                        self.described = Some((described, span));
                    }
                } else if let Some(at) = after(t, "remind it:") {
                    lone(self, "what to remind an agent of");
                    let vs = self.at(&l, at, t.len() - at);
                    let step = map_of(vec![("remind", s(t[at..].trim(), &vs))], &span);
                    self.push(map, "then", step);
                } else if let Some(at) = after(t, "stop and say:") {
                    lone(self, "what a run stops with");
                    let vs = self.at(&l, at, t.len() - at);
                    let step = map_of(vec![("stop", s(t[at..].trim(), &vs))], &span);
                    self.push(map, "then", step);
                } else if let Some(at) = after(t, "consult ") {
                    lone(self, "who to ask");
                    let vs = self.at(&l, at, t.len() - at);
                    let step = map_of(vec![("consult", s(t[at..].trim(), &vs))], &span);
                    self.push(map, "then", step);
                } else if let Some(at) = after(t, "tell ") {
                    lone(self, "who to tell");
                    let vs = self.at(&l, at, t.len() - at);
                    let step = map_of(vec![("tell", s(t[at..].trim(), &vs))], &span);
                    self.push(map, "then", step);
                } else if let Some(at) = after(t, "called ") {
                    lone(self, "what a reaction is called");
                    let vs = self.at(&l, at, t.len() - at);
                    let name = self.unquoted(t[at..].trim(), &vs);
                    if let Some((_, prior)) = &self.called {
                        let prior = prior.clone();
                        self.diags.push(
                            Diagnostic::error(
                                "lang/said-twice",
                                vs,
                                "This reaction is named twice.",
                                "Keep one `called` line.",
                            )
                            .with_related(prior, "also named here"),
                        );
                    } else {
                        self.called = Some((name, vs));
                    }
                } else if t == "every time" {
                    lone(self, "how often");
                    self.put(map, "fires".into(), span.clone(), s("every-time", &span));
                } else {
                    return false;
                }
                true
            }
            Kind::Event => {
                let Some(at) = after(t, "when ") else { return false };
                lone(self, "what an event is");
                if let Some((fields, described)) = self.signal(&l, at) {
                    for (k, node) in fields {
                        self.put(map, k.to_string(), span.clone(), node);
                    }
                    self.described = Some((described, span));
                }
                true
            }
            Kind::Flow | Kind::Program => {
                // A workflow is started with what it `accepts:`; a program is
                // handed what it `takes:`. Both hand back `answers-with:`.
                let taken = if kind == Kind::Flow { "accepts" } else { "takes" };
                if let Some(at) = after(t, "takes ") {
                    lone(self, "what this takes");
                    if let Some(node) = self.shapes(&l, at) {
                        self.put(map, taken.into(), span, node);
                    }
                } else if let Some(at) = after(t, "gives ") {
                    lone(self, "what this gives");
                    if let Some(node) = self.shapes(&l, at) {
                        self.put(map, "answers-with".into(), span, node);
                    }
                } else {
                    return false;
                }
                true
            }
            Kind::Stage | Kind::Decision | Kind::Plain => false,
        }
    }

    /// `message: text, photos: list of images` — a comma ends a line only
    /// where a new `name:` follows it, so `one of approved, declined` stays
    /// one shape.
    fn shapes(&mut self, l: &Line, at: usize) -> Option<Node> {
        let rest = &l.text[at..];
        let mut pairs: Vec<(String, Span, String, Span)> = Vec::new();
        let mut from = 0;
        for piece in rest.split(", ") {
            let here = at + from;
            from += piece.len() + 2;
            let named = piece.find(':').filter(|n| {
                bare_word(piece[..*n].trim()) && (piece[*n + 1..].starts_with(' ') || piece.len() == *n + 1)
            });
            match (named, pairs.last_mut()) {
                (Some(n), _) => {
                    let lead = piece.len() - piece.trim_start().len();
                    pairs.push((
                        piece[..n].trim().to_string(),
                        self.at(l, here + lead, n - lead),
                        piece[n + 1..].trim().to_string(),
                        self.at(l, here + n + 1, piece.len() - n - 1),
                    ));
                }
                (None, Some(last)) => {
                    last.2.push_str(", ");
                    last.2.push_str(piece.trim_end());
                }
                (None, None) => {
                    let span = self.at(l, here, piece.len());
                    self.error(
                        "lang/not-a-line",
                        span,
                        "Each thing here needs a name and what shape it is.".to_string(),
                        "Write `name: shape`, with commas between them — `message: text, \
                         photos: list of images`."
                            .to_string(),
                    );
                    return None;
                }
            }
        }
        let mut m = Map::new();
        for (k, ks, v, vs) in pairs {
            if v.is_empty() {
                self.error(
                    "lang/not-a-line",
                    ks,
                    format!("'{k}' does not say what shape it is."),
                    format!("Write `{k}: text`, or whichever shape it is."),
                );
                return None;
            }
            let node = s(v, &vs);
            self.put(&mut m, k, ks, node);
        }
        Some(Node::map(m, self.whole(l)))
    }

    /// `domain: refunds, daily-cap: 0.05 USD` — names with a figure each, read
    /// as the figures they are. A comma ends one only where a new `name:`
    /// follows it.
    fn given(&mut self, l: &Line, at: usize) -> Option<Node> {
        let rest = &l.text[at..];
        let mut pairs: Vec<(String, Span, String, usize)> = Vec::new();
        let mut from = 0;
        for piece in rest.split(", ") {
            let here = at + from;
            from += piece.len() + 2;
            let named = piece.find(':').filter(|n| {
                bare_word(piece[..*n].trim()) && (piece[*n + 1..].starts_with(' ') || piece.len() == *n + 1)
            });
            match (named, pairs.last_mut()) {
                (Some(n), _) => {
                    let lead = piece.len() - piece.trim_start().len();
                    pairs.push((
                        piece[..n].trim().to_string(),
                        self.at(l, here + lead, n - lead),
                        piece[n + 1..].trim().to_string(),
                        here + n + 1,
                    ));
                }
                (None, Some(last)) => {
                    last.2.push_str(", ");
                    last.2.push_str(piece.trim_end());
                }
                (None, None) => {
                    let span = self.at(l, here, piece.len().max(1));
                    self.error(
                        "lang/not-a-line",
                        span,
                        "Each thing given here needs its name.".to_string(),
                        "Write `<name>: <value>`, with commas between them — `domain: refunds, \
                         daily-cap: 0.05 USD`."
                            .to_string(),
                    );
                    return None;
                }
            }
        }
        let mut m = Map::new();
        for (k, ks, v, v_at) in pairs {
            if v.is_empty() {
                self.error(
                    "lang/not-a-line",
                    ks,
                    format!("'{k}' is given nothing."),
                    format!("Write `{k}: <value>`."),
                );
                return None;
            }
            let vs = self.at(l, v_at, v.len());
            let node = self.scalar(&v, &vs);
            self.put(&mut m, k, ks, node);
        }
        Some(Node::map(m, self.whole(l)))
    }

    /// `zendesk, payments` — a list of names.
    fn names(&mut self, l: &Line, at: usize) -> Node {
        let mut items = Vec::new();
        let mut from = at;
        for piece in l.text[at..].split(',') {
            let lead = piece.len() - piece.trim_start().len();
            let name = piece.trim();
            let span = self.at(l, from + lead, name.len());
            from += piece.len() + 1;
            if name.is_empty() {
                self.error(
                    "lang/not-a-line",
                    span,
                    "There is a comma here with no name beside it.".to_string(),
                    "Take the comma out, or write the name it was for.".to_string(),
                );
                continue;
            }
            items.push(s(name, &span));
        }
        Node::list(items, self.whole(l))
    }

    fn asks(&mut self, l: &Line, at: usize, map: &mut Map) {
        let rest = &l.text[at..];
        let Some(n) = rest.find(": ") else {
            let span = self.whole(l);
            self.error(
                "lang/not-a-line",
                span,
                "This says who is asked and not what for — and that sentence is how the agent \
                 knows when to ask them."
                    .to_string(),
                format!("Write `asks {}: <what they are for>`.", rest.trim_end_matches(':').trim()),
            );
            return;
        };
        let (who, what) = (rest[..n].trim(), rest[n + 2..].trim());
        let who_span = self.at(l, at, n);
        let what_span = self.at(l, at + n + 2, rest.len() - n - 2);
        self.add(map, "team", who.to_string(), who_span, s(what, &what_span));
    }

    fn at_most(&mut self, l: &Line, at: usize, map: &mut Map) {
        let rest = &l.text[at..];
        let (figure, unit) = rest.split_once(' ').unwrap_or((rest, ""));
        let field = match unit.trim() {
            "steps" | "step" => Some("steps-at-most"),
            "tool calls" | "tool call" => Some("tool-calls-at-most"),
            "tokens" | "token" => Some("tokens-at-most"),
            _ => None,
        };
        let span = self.at(l, at, figure.len());
        match (figure.parse::<i64>(), field) {
            (Ok(n), Some(field)) => {
                self.add(map, "limits", field.to_string(), span.clone(), Node::new(Value::Int(n), span));
            }
            _ => {
                let span = self.whole(l);
                self.error(
                    "lang/not-a-line",
                    span,
                    "A limit is a whole number of something.".to_string(),
                    "Write `at most 8 steps`, `at most 20 tool calls` or `at most 50000 tokens`. \
                     Any other limit is a setting under `limits:`."
                        .to_string(),
                );
            }
        }
    }

    fn listens(&mut self, l: &Line, at: usize, map: &mut Map) {
        let rest = &l.text[at..];
        let parsed = (|| {
            let (what, how) = rest.split_once(": ")?;
            let (kind, name) = what.trim().split_once(' ')?;
            let how = match how.trim() {
                "asked first" => "asked-first",
                "told after" => "told-after",
                _ => return None,
            };
            matches!(kind, "topic" | "event").then_some((kind, name.trim(), how))
        })();
        let span = self.whole(l);
        let Some((kind, name, how)) = parsed else {
            self.error(
                "lang/not-a-line",
                span,
                "This does not say what is listened for, or how.".to_string(),
                "Write `listens for topic <name>: asked first` or `listens for event <name>: \
                 told after`."
                    .to_string(),
            );
            return;
        };
        let line = map_of(vec![(kind, s(name, &span)), ("how", s(how, &span))], &span);
        self.push(map, "listens-for", line);
    }

    /// `before payments/issue-refund, when amount is more than 200 USD: ask
    /// is-this-ok, because a refund over 200 USD is a management decision`
    fn before(&mut self, l: &Line, at: usize, map: &mut Map) {
        let rest = &l.text[at..];
        let span = self.whole(l);
        let parsed = (|| {
            let (call, ask) = rest.split_once(": ask ")?;
            let (question, because) = ask.split_once(", because ")?;
            let (tool, compared) = match call.split_once(", when ") {
                Some((tool, compared)) => (tool.trim(), Some(compared.trim())),
                None => (call.trim(), None),
            };
            if tool.is_empty() || tool.contains(' ') || question.trim().is_empty() {
                return None;
            }
            let mut atom = vec![("tool", s(tool, &span))];
            if let Some(compared) = compared {
                let (arg, word, figure) = [
                    (" is more than ", "more-than"),
                    (" is less than ", "less-than"),
                    (" is ", "is"),
                ]
                .iter()
                .find_map(|(sep, word)| {
                    compared.split_once(sep).map(|(a, f)| (a.trim(), *word, f.trim()))
                })?;
                if arg.is_empty() || arg.contains(' ') || figure.is_empty() {
                    return None;
                }
                atom.push(("arg", s(arg, &span)));
                atom.push((word, self.scalar(figure, &span)));
            }
            Some(map_of(
                vec![
                    ("when", Node::list(vec![map_of(atom, &span)], span.clone())),
                    ("because", s(because.trim(), &span)),
                    ("question", s(question.trim(), &span)),
                ],
                &span,
            ))
        })();
        match parsed {
            Some(rule) => self.push(map, "ask-a-person", rule),
            None => self.error(
                "lang/not-a-line",
                span,
                "This does not say which call a person is asked about, which question they are \
                 asked, and why."
                    .to_string(),
                "Write `before <tool>/<action>: ask <question>, because <why>` — and after the \
                 action, `, when <argument> is more than <figure>` to ask only above a figure."
                    .to_string(),
            ),
        }
    }

    /// A figure written in a sentence, read the way a setting's value is — so
    /// `80` is a number and `200 USD` is text, in both ways of writing.
    /// A figure in a sentence: read as YAML reads a value, so `8` is a number
    /// and `0.50 USD` is text. `{use: <name>}` is a figure too — the one
    /// `values:` holds under that name, put there by the loader.
    fn scalar(&self, text: &str, span: &Span) -> Node {
        let value = parse_yaml_at(&format!("v: {text}"), &self.file, Offset::default())
            .ok()
            .and_then(|n| n.get("v").map(|v| v.value.clone()));
        if let Some(Value::Map(m)) = &value
            && m.len() == 1
            && let Some(name) = m.get("use").and_then(|e| e.node.as_str())
        {
            return map_of(vec![("use", s(name, span))], span);
        }
        let value = value
            .filter(|v| !matches!(v, Value::Map(_) | Value::List(_)))
            .unwrap_or_else(|| Value::Str(text.to_string()));
        Node::new(value, span.clone())
    }

    /// A reaction written as `when <signal>` and what is indented under it:
    /// its name, where that is written, and the reaction.
    fn when(
        &mut self,
        first: usize,
        at: usize,
        rest: Range<usize>,
        everyone: bool,
    ) -> Option<(String, Span, Node)> {
        let l = self.lines[first];
        let span = self.whole(&l);
        let saved = (self.called.take(), self.described.take());
        let signal = self.signal(&l, at);
        let mut map = Map::new();
        if let Some((fields, _)) = &signal {
            for (k, node) in fields {
                map.insert(
                    k.to_string(),
                    Entry {
                        key_span: span.clone(),
                        node: node.clone(),
                    },
                );
            }
        }
        let body = self.body(rest, Kind::Reaction);
        for (k, e) in body {
            self.put(&mut map, k, e.key_span, e.node);
        }
        if let Some((_, described)) = &signal
            && !map.contains_key("description")
        {
            map.insert(
                "description".to_string(),
                Entry {
                    key_span: span.clone(),
                    node: s(described.clone(), &span),
                },
            );
        }
        if everyone && !map.contains_key("applies-to") {
            map.insert(
                "applies-to".to_string(),
                Entry {
                    key_span: span.clone(),
                    node: s("every-agent", &span),
                },
            );
        }
        let called = self.called.take();
        (self.called, self.described) = saved;
        signal.as_ref()?;
        let sentence_span = self.at(&l, at, l.text.len() - at);
        let (id, id_span) = called.unwrap_or_else(|| (slug(&l.text[at..]), sentence_span));
        Some((id, id_span, Node::map(map, span)))
    }

    /// What comes after `when`: the fields it stands for, and the description
    /// the reaction has if it writes none of its own.
    fn signal(&mut self, l: &Line, at: usize) -> Option<(Vec<(&'static str, Node)>, String)> {
        let text = l.text[at..].trim();
        let span = self.at(l, at, l.text.len() - at);
        let a_call = |tool: &str| {
            Node::list(vec![map_of(vec![("tool", s(tool, &span))], &span)], span.clone())
        };
        let a_name = |n: &str| !n.is_empty() && !n.contains(' ');
        let count = |n: &str| n.parse::<i64>().ok().filter(|n| *n >= 1);
        let fields: Option<Vec<(&'static str, Node)>> = (|| {
            if let Some(tool) = text.strip_prefix("the agent is about to call ") {
                return a_name(tool).then(|| {
                    vec![("at", s("step.tool.before", &span)), ("when-this", a_call(tool))]
                });
            }
            if let Some(rest) = text.strip_prefix("the agent has called ") {
                let (tool, tail) = rest.split_once(" more than ")?;
                let n = tail.strip_suffix(" times").or_else(|| tail.strip_suffix(" time"))?;
                if !a_name(tool) {
                    return None;
                }
                return count(n).map(|n| {
                    vec![
                        ("at", s("step.tool.before", &span)),
                        ("when-this", a_call(tool)),
                        ("more-than", Node::new(Value::Int(n), span.clone())),
                    ]
                });
            }
            if let Some(tool) = text.strip_suffix(" has answered") {
                return a_name(tool).then(|| {
                    vec![("at", s("step.tool.completed", &span)), ("when-this", a_call(tool))]
                });
            }
            if let Some(rest) = text.strip_prefix("the agent has taken more than ") {
                let n = rest.strip_suffix(" steps").or_else(|| rest.strip_suffix(" step"))?;
                return count(n).map(|n| {
                    vec![
                        ("at", s("step.run.started", &span)),
                        ("more-than", Node::new(Value::Int(n), span.clone())),
                    ]
                });
            }
            match text {
                "a turn starts" => return Some(vec![("at", s("turn.run.started", &span))]),
                "the agent is about to ask a teammate" => {
                    return Some(vec![("at", s("step.delegate.before", &span))]);
                }
                "the agent has written a step" => {
                    return Some(vec![("at", s("step.message.after", &span))]);
                }
                _ => {}
            }
            if let Some(topic) = text.strip_prefix("the work touches ") {
                return a_name(topic).then(|| vec![("topic", s(topic, &span))]);
            }
            if let Some(what) = text.strip_prefix("it looks like ") {
                return (!what.trim().is_empty()).then(|| vec![("judged", s("yes", &span))]);
            }
            if let Some(event) = text.strip_suffix(" happens") {
                return a_name(event).then(|| vec![("event", s(event, &span))]);
            }
            None
        })();
        let Some(fields) = fields else {
            self.error(
                "lang/not-a-signal",
                span,
                "This does not say when, in words this language knows.".to_string(),
                "After `when`, write one of: `the agent is about to call <tool>`, `the agent has \
                 called <tool> more than <n> times`, `<tool> has answered`, `the agent has taken \
                 more than <n> steps`, `a turn starts`, `the agent is about to ask a teammate`, \
                 `the agent has written a step`, `the work touches <topic>`, `it looks like \
                 <what>`, or `<event> happens`. Anything else is a `reaction <name>` block with \
                 `at:` and `when-this:` settings."
                    .to_string(),
            );
            return None;
        };
        let described = default_description(text, text.strip_prefix("it looks like "));
        Some((fields, described))
    }
}

/// Where the rest of the line starts, when it starts with `opening`.
fn after(text: &str, opening: &str) -> Option<usize> {
    text.starts_with(opening).then_some(opening.len())
}
