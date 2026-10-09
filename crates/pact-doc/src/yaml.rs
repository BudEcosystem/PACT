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
///
/// All three are charged against what the document *expands to*, not against
/// what is written in it. A `&name` shortcut used by `*name` copies its whole
/// subtree in at every use, so a file whose text is well under every limit can
/// still work out to a tree that is over them — see [`Anchored`].
///
/// **Settings and text are counted separately because they are two different
/// ways to be too big, and each one is blind to the other.** Nine-way shortcuts
/// stacked eight deep are five million settings holding one byte each; one
/// shortcut naming 150 KB of text and used 25,000 times is 25,001 settings
/// holding 3.75 GB. Counting only settings lets the second past — measured, a
/// 414 KB file took the loader to 3,989,076 KB resident and then killed it:
///
/// ```text
/// memory allocation of 150000 bytes failed
/// Command terminated by signal 6
/// EXIT=134
/// ```
///
/// **All three are capability-affecting literals in the Rust core, which F-1
/// (`docs/00-THESIS.md:274`) and FR-8.1.3 (`docs/30-FRD.md:206`) forbid in so
/// many words**, and `docs/20-ARCHITECTURE-DRAFT.md:1762` fixes "the core" as
/// these crates. They are filed **DELIBERATE_AND_CLOSED** in the sense
/// `docs/remediation/C8-profiles.md` uses: what an author raising one of them
/// buys is the abort each was written to prevent, so there is nothing to gain
/// by making them settable and a remote-triggerable SIGABRT to lose. `MAX_TEXT`
/// is listed as unfiled at `C8-profiles.md:49`, and closing that is that
/// document's work item **D-4**, which is not implemented; the reasoning here
/// is what D-4 has to file, not a substitute for filing it. See
/// `docs/remediation/A3-yaml-alias-bomb.md` §7.
const MAX_DEPTH: usize = 64;
const MAX_NODES: usize = 200_000;
/// Four megabytes of writing in one file. The worked example's largest document
/// is under 20 KB, and a person does not hand-write four megabytes of settings.
///
/// **The same figure as `pact_loader::Policy::max_text_bytes`, and now the same
/// constant.** They were two independent `4 * 1024 * 1024` literals in two
/// crates, which is a drift waiting to happen — and the direction of the drift
/// decides which of two differently-worded refusals an author gets for the same
/// file. Public so the loader can read it rather than restate it.
///
/// The two are not redundant. The loader's is a **file size** asked of the
/// filesystem before a byte is read; this one is what a document **works out
/// to** after every `*name` has been copied in. Because charged text is never
/// more than the bytes present in the file, the loader's always fires first on
/// a file with no shortcut in it: `Ran::OutOfText`'s `written_out` wording is
/// therefore reachable only from a library caller handing `parse_yaml` a string
/// no loader would have passed it, or from a document a shortcut inflated.
/// Measured: a 4,194,404-byte agent file is refused as `loader/file-too-large`,
/// never `doc/too-large`.
pub const MAX_TEXT: usize = 4 * 1024 * 1024;
/// The same figure in the unit the author's file manager shows them.
const MAX_TEXT_MB: usize = MAX_TEXT / (1024 * 1024);

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

    Ok(builder
        .root
        .take()
        .unwrap_or_else(|| Node::null(Span::whole_file(file))))
}

/// One frame of the parse stack: a container being filled.
enum Frame {
    Seq {
        items: Vec<Node>,
        start: Marker,
        anchor: usize,
    },
    Map {
        map: Map,
        start: Marker,
        anchor: usize,
        pending_key: Option<(String, Span)>,
    },
}

/// A defined `&name` shortcut, and the only two places a copy of it can be
/// made.
///
/// Kept in a module of its own so that `node` can be **private**: the only ways
/// to obtain what a shortcut stands for are [`Anchored::kept`] and
/// [`Anchored::copy`], which are two countable points and nothing else. That is
/// not tidiness. Half of the size fix is *when* the copy is made — after the
/// limits have been consulted, never before — and that half is invisible from
/// outside the parser, because both orders produce the identical refusal. A
/// test can only see it by counting copies, and counting copies is only sound
/// if a copy cannot be made any other way.
///
/// **There are two copies per shortcut, not one, and for a round only one of
/// them was counted or charged.** `&name` keeps a copy *as it is defined*, so
/// that a later `*name` has something to copy from; `*name` then takes another.
/// A file whose shortcuts are defined inside one another pays the first cost
/// once per level and never reaches the second at all — sixty-two nested
/// `&name` definitions holding 190,000 words between them, with no `*name`
/// anywhere in the file, took `pact check` to 3,683,232 KB resident and was
/// killed by the operating system under `ulimit -v 1500000` (`memory allocation
/// of 1 bytes failed`, signal 6, EXIT=134) while every per-file limit said the
/// document was within budget. The same tree written without the `&name`s
/// peaked at 127,816 KB and survived the same cap. So both copies are counted
/// by `COPIES_MADE` and both are charged by [`Builder::afford`].
mod shortcut {
    use crate::value::Node;

    #[cfg(test)]
    thread_local! {
        /// Copies of a shortcut's contents made on this thread. Per thread
        /// because `cargo test` runs tests in parallel.
        pub(super) static COPIES_MADE: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
    }

    /// What one `&name` block costs, measured **without copying it**.
    ///
    /// Split out of [`Anchored`] so the price can be asked for before the
    /// decision to keep the block is taken. Every cost is measured **once**,
    /// while the block is the size the file says it is, because the
    /// alternative is to measure it by walking a copy — and the walk cannot
    /// happen until the copy exists, which is exactly the allocation the
    /// limits are there to prevent.
    #[derive(Clone, Copy)]
    pub(super) struct Priced {
        /// `node.node_count()`: how many settings this block holds, and
        /// therefore how many one `*name` use of it adds.
        pub(super) size: usize,
        /// `node.depth()`: how many levels of nesting one `*name` adds below
        /// the position it is written at.
        pub(super) depth: usize,
        /// `node.text_bytes()`: how much writing it holds. Not implied by
        /// `size` — a single setting can hold a megabyte.
        pub(super) text: usize,
    }

    impl Priced {
        pub(super) fn of(node: &Node) -> Self {
            Self {
                size: node.node_count(),
                depth: node.depth(),
                text: node.text_bytes(),
            }
        }
    }

    /// A `&name` shortcut that has been defined, together with what one `*name`
    /// use of it costs.
    pub(super) struct Anchored {
        node: Node,
        pub(super) priced: Priced,
    }

    impl Anchored {
        /// Make the copy that **defining** `&name` keeps. Every limit that
        /// stands between the document and this allocation must already have
        /// been consulted — `priced` is what it was charged against.
        pub(super) fn kept(node: &Node, priced: Priced) -> Self {
            #[cfg(test)]
            COPIES_MADE.with(|c| c.set(c.get() + 1));
            Self {
                node: node.clone(),
                priced,
            }
        }

        /// Make the copy that **using** `*name` takes. Same rule: every limit
        /// must already have been consulted.
        pub(super) fn copy(&self) -> Node {
            #[cfg(test)]
            COPIES_MADE.with(|c| c.set(c.get() + 1));
            self.node.clone()
        }
    }
}

use shortcut::{Anchored, Priced};

/// Which of the two size budgets a document ran out of.
///
/// They are separate diagnostics rather than one, because the two are fixed in
/// different ways: a document with too many settings is split up, a document
/// with too much writing in it has the writing moved out into files of its own.
#[derive(Clone, Copy)]
enum Ran {
    OutOfSettings,
    OutOfText,
}

impl Ran {
    /// What the author is told when the document went over while being read
    /// straight through — no shortcut involved, the file really is this big.
    fn written_out(self, span: Span) -> Diagnostic {
        match self {
            Ran::OutOfSettings => Diagnostic::error(
                "doc/too-large",
                span,
                format!("This file is too large to load (over {MAX_NODES} settings)."),
                "Split it into several files. Any setting can become its own file or folder.",
            ),
            Ran::OutOfText => Diagnostic::error(
                "doc/too-large",
                span,
                format!("This file holds too much writing to load (over {MAX_TEXT_MB} MB of it)."),
                "Move the long pieces of writing into files of their own beside this one, \
                 and name the file where the writing was.",
            ),
        }
    }

    /// ...and when **defining** a `&name` block is what tipped it over.
    ///
    /// Naming a block for reuse keeps a second copy of it, so a file can be
    /// over the limit without a single `*name` in it — and the two wordings
    /// either side of this one would both be false about such a file: nothing
    /// was copied in from elsewhere, and the file as written is half the size
    /// the limit is talking about. The author is looking at a `&name` they
    /// wrote and needs to be told that naming it is what costs.
    fn kept_for_reuse(self, span: Span) -> Diagnostic {
        match self {
            Ran::OutOfSettings => Diagnostic::error(
                "doc/too-large",
                span,
                format!(
                    "Naming this for reuse (`&name`) keeps a second copy of everything \
                     under it, which takes the file to over {MAX_NODES} settings."
                ),
                "Either write these values out where they are used, without naming them, \
                 or move them into a file of their own and name that file instead.",
            ),
            Ran::OutOfText => Diagnostic::error(
                "doc/too-large",
                span,
                format!(
                    "Naming this for reuse (`&name`) keeps a second copy of everything \
                     under it, which takes the file to over {MAX_TEXT_MB} MB of writing."
                ),
                "Either write these values out where they are used, without naming them, \
                 or move the long pieces of writing into files of their own beside this one.",
            ),
        }
    }

    /// ...and when one `*name` shortcut is what tipped it over. Same limits,
    /// but the author is looking at three words on a line and needs to be told
    /// that those three words stand for everything the shortcut holds.
    fn copied_in(self, span: Span) -> Diagnostic {
        match self {
            Ran::OutOfSettings => Diagnostic::error(
                "doc/too-large",
                span,
                format!(
                    "This shortcut (`*name`) copies in so much that the file works out \
                     to over {MAX_NODES} settings."
                ),
                "A shortcut that is written out of other shortcuts grows very fast — \
                 each one copies in everything the one before it holds. Write the values \
                 you need here out in full, or split them across several files.",
            ),
            Ran::OutOfText => Diagnostic::error(
                "doc/too-large",
                span,
                format!(
                    "This shortcut (`*name`) copies in so much writing that the file works \
                     out to over {MAX_TEXT_MB} MB of it."
                ),
                "Each use of a shortcut copies in the whole of what it stands for, so a \
                 few short lines can add up to a very large file. Write the values you \
                 need here out in full, or split them across several files.",
            ),
        }
    }
}

/// How much of the two budgets `*name` copies have already spent, and which
/// single copy spent the most of each.
///
/// Kept so that a refusal can name the line that is actually responsible.
/// Without it, a shortcut that ate 199,941 of the 200,000 settings and then an
/// ordinary `z5: 1` that took it over produced *"This file is too large to load
/// (over 200000 settings)"* with the caret under `z5: 1`, on a 738-byte,
/// 72-line file — measured. Both halves of that report are false: the file is
/// not large, and the line it points at is not what made it large.
#[derive(Default)]
struct CopiedIn {
    settings: usize,
    text: usize,
    /// The one `*name` that copied in the most settings, and where it is.
    widest: Option<(usize, Span)>,
    /// The one `*name` that copied in the most writing, and where it is.
    wordiest: Option<(usize, Span)>,
}

struct Builder<'a> {
    file: &'a Utf8Path,
    offset: Offset,
    text_len: usize,
    stack: Vec<Frame>,
    root: Option<Node>,
    anchors: std::collections::HashMap<usize, Anchored>,
    error: Option<Diagnostic>,
    nodes: usize,
    text: usize,
    copied_in: CopiedIn,
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
            text: 0,
            copied_in: CopiedIn::default(),
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
            Some(Frame::Map {
                pending_key: Some((_, key_span)),
                ..
            }) => Some(key_span.clone()),
            _ => None,
        }
    }

    /// Charge `settings` settings and `text` bytes of writing against the two
    /// size budgets, and say which one — if either — that went over.
    ///
    /// Always asked **before** what is being charged for is built. A budget
    /// consulted after the fact has already paid for the allocation it exists
    /// to prevent, which for an expanding `*name` means the process is killed
    /// by the operating system before any diagnostic can be printed.
    fn afford(&mut self, settings: usize, text: usize) -> Option<Ran> {
        self.nodes = self.nodes.saturating_add(settings);
        self.text = self.text.saturating_add(text);
        if self.nodes > MAX_NODES {
            return Some(Ran::OutOfSettings);
        }
        if self.text > MAX_TEXT {
            return Some(Ran::OutOfText);
        }
        None
    }

    /// Which line a refusal points at, and in whose words.
    ///
    /// `here` is the wording for the line the budget actually ran out on —
    /// [`Ran::written_out`] for an ordinary setting, [`Ran::kept_for_reuse`]
    /// for a `&name` definition. It is the right answer only when that line is
    /// also what the budget was spent on. When `*name` copies have paid for
    /// **most** of everything charged so far, the line that happens to be last
    /// is an innocent bystander: the report points at the widest copy instead,
    /// in the words that explain what a copy costs.
    ///
    /// More than half is the test, not "any", because one small honest `*name`
    /// in a file that really is too big must not be blamed for it — and not
    /// "all", because the shape that produced the false report had 59 settings
    /// of its 200,000 written out by hand.
    fn over_budget(&self, over: Ran, here: fn(Ran, Span) -> Diagnostic, span: Span) -> Diagnostic {
        let blame = match over {
            Ran::OutOfSettings if self.copied_in.settings * 2 > self.nodes => {
                self.copied_in.widest.as_ref()
            }
            Ran::OutOfText if self.copied_in.text * 2 > self.text => {
                self.copied_in.wordiest.as_ref()
            }
            _ => None,
        };
        match blame {
            Some((_, at)) => over.copied_in(at.clone()),
            None => here(over, span),
        }
    }

    /// Attach a completed node to its parent, or make it the root.
    fn emit(&mut self, node: Node, anchor: usize) {
        if self.error.is_some() {
            return;
        }
        // Only what this node holds *itself*: a list or a set of settings is
        // built out of children that were emitted, and charged, one at a time.
        let own_text = match &node.value {
            Value::Str(s) => s.len(),
            _ => 0,
        };
        if let Some(over) = self.afford(1, own_text) {
            let d = self.over_budget(over, Ran::written_out, node.span.clone());
            self.fail(d);
            return;
        }
        if anchor != 0 {
            // Defining `&name` is not free and used to be treated as if it
            // were. The block has just been charged one setting at a time as
            // it was read; keeping it for a later `*name` to copy from
            // allocates the whole of it a **second** time, and that second
            // allocation was charged against neither budget. Nested
            // definitions pay it once per level, which is how a file within
            // every per-file limit reached 3.6 GB with no `*name` in it.
            //
            // Charged before the copy is made, for the same reason the alias
            // arm is: a budget consulted afterwards has already paid for the
            // allocation it exists to refuse.
            let priced = Priced::of(&node);
            if let Some(over) = self.afford(priced.size, priced.text) {
                let d = self.over_budget(over, Ran::kept_for_reuse, node.span.clone());
                self.fail(d);
                return;
            }
            self.anchors.insert(anchor, Anchored::kept(&node, priced));
        }

        self.attach(node);
    }

    /// Put a node where the parse stack says it goes. Split out of `emit` so
    /// that an expanded `*name`, which has already been charged for its whole
    /// subtree, is not charged a second time for its root.
    fn attach(&mut self, node: Node) {
        match self.stack.last_mut() {
            None => self.root = Some(node),
            Some(Frame::Seq { items, .. }) => items.push(node),
            Some(Frame::Map {
                map, pending_key, ..
            }) => match pending_key.take() {
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
                self.push(
                    Frame::Seq {
                        items: Vec::new(),
                        start: mark,
                        anchor,
                    },
                    mark,
                );
            }
            Event::SequenceEnd => {
                if let Some(Frame::Seq {
                    items,
                    start,
                    anchor,
                }) = self.stack.pop()
                {
                    let span = self.container_span(start, mark);
                    self.emit(Node::list(items, span), anchor);
                }
            }

            Event::MappingStart(anchor, _) => {
                self.push(
                    Frame::Map {
                        map: Map::new(),
                        start: mark,
                        anchor,
                        pending_key: None,
                    },
                    mark,
                );
            }
            Event::MappingEnd => {
                if let Some(Frame::Map {
                    map,
                    start,
                    anchor,
                    pending_key,
                }) = self.stack.pop()
                {
                    if let Some((key, key_span)) = pending_key {
                        self.fail(Diagnostic::error(
                            "doc/missing-value",
                            key_span,
                            format!("'{key}' was named but never given a value."),
                            format!(
                                "Write a value after the colon, like `{key}: your value here`."
                            ),
                        ));
                        return;
                    }
                    let span = self.container_span(start, mark);
                    self.emit(Node::map(map, span), anchor);
                }
            }

            Event::Alias(id) => {
                // `*name` is the one event that does not cost what it looks
                // like it costs: it copies in a whole subtree, and that subtree
                // may itself have been built out of other `*name` copies. Eight
                // lines of nine-way shortcuts, each pointing at the one above,
                // work out to half a million settings.
                //
                // It used to be charged one, and charged *after* `.cloned()`,
                // so no limit could ever fire: the allocation the limits exist
                // to refuse had already been made, and `pact check` was killed
                // by the operating system with no diagnostic at all. Every
                // question is now asked first, off the sizes measured when the
                // shortcut was defined.
                //
                // **The order of the next three blocks is load-bearing.** They
                // read like validation, but every one of them stands between
                // the process and an allocation it may not survive. Moving the
                // copy above them costs one extra copy of the subtree being
                // refused — measured at 29% more peak memory (89,628 KB against
                // 69,620 KB) on the eight-line document this was found on — and
                // no test can see the difference from the outside, because both
                // orders produce the identical refusal. It is held instead by
                // `a_shortcut_too_big_to_copy_is_refused_without_first_copying_
                // _it`, which counts the copies `Anchored::copy` makes.
                let measured = self.anchors.get(&id).map(|a| a.priced);
                let span = self.span(mark, 1);
                let Some(Priced { size, depth, text }) = measured else {
                    self.fail(Diagnostic::error(
                        "doc/unknown-reference",
                        span,
                        "This refers to something (`*name`) that was never defined.",
                        "Define it earlier with `&name`, or write the value out directly here.",
                    ));
                    return;
                };
                if let Some(over) = self.afford(size, text) {
                    self.fail(over.copied_in(span));
                    return;
                }
                // `depth` counts the copied subtree's own outermost value as a
                // level, and so does `stack.len()` for the container this sits
                // in, so one of the two has to come off — otherwise `*name`
                // standing for a plain word is refused one level shallower than
                // writing that same word out, and the two stop being
                // interchangeable. Measured before this was subtracted: at 63
                // levels of nesting the literal loaded and the shortcut for it
                // was refused. `push` is the rule this has to agree with.
                if self.stack.len() + depth.saturating_sub(1) > MAX_DEPTH {
                    self.fail(Diagnostic::error(
                        "doc/too-deep",
                        span,
                        format!(
                            "This shortcut (`*name`) copies in settings that end up nested more \
                             than {MAX_DEPTH} levels deep here."
                        ),
                        "Write the values you need out in full where they are used, or move the \
                         inner settings into their own file or folder to flatten this out.",
                    ));
                    return;
                }
                // Recorded only once the copy is affordable, so the running
                // total is what was actually spent on shortcuts. `over_budget`
                // reads it to decide whether a later line that runs out is the
                // cause or the bystander.
                self.copied_in.settings += size;
                self.copied_in.text += text;
                if size > self.copied_in.widest.as_ref().map_or(0, |(n, _)| *n) {
                    self.copied_in.widest = Some((size, span.clone()));
                }
                if text > self.copied_in.wordiest.as_ref().map_or(0, |(n, _)| *n) {
                    self.copied_in.wordiest = Some((text, span.clone()));
                }
                let node = self.anchors[&id].copy();
                self.attach(node);
            }
        }
    }
}

impl Builder<'_> {
    fn container_span(&self, start: Marker, end: Marker) -> Span {
        let s = start.index() + self.offset.byte;
        let e = (end.index() + self.offset.byte).max(s + 1);
        Span::new(
            self.file,
            start.line() + self.offset.line,
            start.col() + 1,
            s,
            e,
        )
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
    // THE THIRD SPELLING ON THE SAME NUMBER LINE, and for one round it was the
    // one left open. A scalar that spells a WHOLE NUMBER the `f64` below would
    // not write back — `x-big: 99999999999999999999` — came back out of `pact
    // show` as `1e+20`, and `99999999999999999999`, `99999999999999999998` and
    // `100000000000000000000` — three documents an author would call three
    // different documents — all digested to `sha256:2aa9f0c9…`, one hash, which
    // is the same lockfile-cannot-tell-them-apart harm as the `1e999` case
    // below with the value rewritten instead of deleted.
    //
    // **The question is asked of the FIGURE, not of the spelling**, and for one
    // round it was asked of the spelling: the test was a run of ASCII digits
    // that `i64` could not parse, so one `.` walked straight past it and
    // `x-big: 99999999999999999999.0` published `sha256:2aa9f0c9…` again, the
    // byte-identical hash this paragraph calls the harm. Measured, with the
    // digits-only rule in place: `…9999.0`, `…9998.0` and `100000000000000000000.0`
    // were one hash. [`whole_number_past_holding`] asks instead whether the
    // figure survives the trip, which no spelling can dodge.
    //
    // The rule refuses nothing legitimate. `1.5` is not a whole number, `1e10`
    // is one this holds and writes back unchanged, and every whole number that
    // fits in an `i64` has already left at the line above. Only a figure whose
    // digits would come back as different digits reaches here, and it leaves as
    // what was written.
    if whole_number_past_holding(text) {
        return Value::Str(text.to_string());
    }
    // `is_finite` is the same argument as the leading zeros above, at the other
    // end of the number line. `"1e999".parse::<f64>()` does not fail — it
    // succeeds and hands back infinity, which is not a number any of the ways
    // out of this tree can write down. `to_json` wrote `null` for it and
    // `canonical` wrote `null` with it, so `x-threshold: 1e999` came out of
    // `pact show` as nothing at all AND digested identically to an author who
    // had written `x-threshold:` and meant it. A value the author typed
    // disappearing with no problem reported is exactly the corruption they
    // would never think to check for.
    //
    // A number this cannot hold is therefore not read as a number, and what
    // was written is kept exactly as written. That is lossless, which is what
    // an unknown `x-` field is promised (AC-1.3) — and the claim is made about
    // all three spellings a figure past holding comes in, `1e999` here,
    // `99999999999999999999` at the integer arm above, and `1e-999` at the
    // bottom end below, because a claim of losslessness that one spelling
    // falsifies is worse than no claim.
    //
    // WHICH IS A CLAIM ABOUT FIGURES THIS CANNOT HOLD, AND NOT A CLAIM THAT
    // EVERY DISTINCT LITERAL SURVIVES, because the second one is false and
    // stating it would be the thing the paragraph above forbids. A scalar this
    // CAN hold is read as the `f64` it parses to, and an `f64` is finite, so
    // distinct decimal literals do collapse onto one — measured, at the most
    // ordinary scale there is: `"0.1"` and `"0.1000000000000000055511151231257827"`
    // parse equal. That is ordinary float rounding, it is what `1e10` coming
    // back as `10000000000.0` already is, and refusing it means refusing every
    // number in the format.
    //
    // The line is drawn where the figure is GONE rather than rounded, and zero
    // is the only place that is categorically true. The nearest case on the
    // other side of it was measured rather than argued about: `x-tiny: 3e-324`,
    // `5e-324` and `7e-324` are three subnormals that all print `5e-324` and all
    // digest `sha256:1882cd2c…`, and they are left alone. Widening the rule to
    // `f == 0.0 || f.is_subnormal()` was the obvious way to catch them and is
    // wrong: `1e-310` IS subnormal (the smallest NORMAL `f64` is
    // `2.2250738585072014e-308`), and `x-tiny: 1e-310` and
    // `x-tiny: 1.0000000001e-310` already digest to `sha256:a65d376f…` and
    // `sha256:3add5576…` — two hashes, nothing lost — so that rule would refuse
    // figures this holds perfectly well while still leaving `0.1` open. It
    // would buy a bounded amount of precision at the cost of a false sentence,
    // which is the trade every arm in this file exists to refuse.
    //
    // So: **a figure that arrived as zero is kept as text; a figure that
    // arrived rounded is read as the number it rounded to.** The bound is
    // recorded here rather than left to be rediscovered, and the register keeps
    // the row.
    //
    // Where the specification does say a number is wanted, `coerce::number`
    // reads the text back and hands the figure to `Schema::check_ceiling`,
    // which refuses it at the author's own line as `schema/too-big-to-count` —
    // a line spelled the way a number is spelled, told what is wrong with it,
    // rather than told it is not a number and sent hunting for a typo that is
    // not there. `check_ceiling` has to read the TEXT and not only the figure
    // to do that for the integer spelling: `99999999999999999999` parses back
    // to a perfectly finite `1e20`, so `!n.is_finite()` cannot see it and
    // `whole_number_past_holding` is what does.
    //
    // `.inf` and `.nan` never reached here: the digit test below is what keeps
    // YAML's own words for these as the text they were written as.
    //
    // `underflowed_to_zero` is the SAME argument at the bottom of the same
    // scale, and it was left open for a round: `x-tiny: 1e-999` parses without
    // complaint and hands back `0.0`, so `pact show` printed `0.0` where the
    // author had written a figure, `pact check` said nothing, and that document
    // digested identically to one saying `x-tiny: 0`. A lockfile could not tell
    // the two apart, which is the same sentence the overflow fix above was
    // written to delete.
    if let Ok(f) = text.parse::<f64>()
        && f.is_finite()
        && !underflowed_to_zero(f, text)
        && text.chars().any(|c| c.is_ascii_digit())
    {
        return Value::Float(f);
    }

    Value::Str(text.to_string())
}

/// A scalar that came back as zero while the figure the author wrote is not
/// zero — the bottom end of the number line, where the parse succeeds and hands
/// back a number this CAN hold that is not the one on the page.
///
/// The test is deliberately narrow, and the two obvious wider ones were both
/// measured and rejected. *"Only accept a float that round-trips its own text"*
/// refuses `1e10`, which comes back as `10000000000.0` — the same number,
/// reformatted, and nobody would call that corrupted. *"Any text that parses to
/// zero"* refuses `0`, `0.0`, `-0.0` and `0e10`, which are zeros an author meant
/// and which lose nothing by being read as zero.
///
/// So: zero on the way out, and a figure other than zero in the SIGNIFICAND on
/// the way in. The exponent is not looked at, because the `10` of `0e10` is a
/// scale applied to a nothing and says nothing about what was meant, while the
/// `1` of `1e-999` is the whole of what the author wrote.
///
/// A THIRD widening was measured and rejected after the first two: *"zero or
/// subnormal"*, which would catch `3e-324`, `5e-324` and `7e-324` — three
/// literals that really do collapse onto one `f64` and one digest. It is
/// rejected because `1e-310` is subnormal too and loses nothing (`1e-310` and
/// `1.0000000001e-310` digest differently, measured), so the rule would refuse
/// figures held to full precision in order to catch a decade that is not
/// special: `"0.1"` and `"0.1000000000000000055511151231257827"` parse equal in
/// the NORMAL range and no rule short of refusing floats altogether catches
/// that. The line stays at "arrived as zero", where the figure is gone rather
/// than rounded; `resolve_scalar`'s own note records the boundary and the
/// digests.
fn underflowed_to_zero(f: f64, text: &str) -> bool {
    if f != 0.0 {
        return false;
    }
    let significand = text.split(['e', 'E']).next().unwrap_or(text);
    significand.chars().any(|c| c.is_ascii_digit() && c != '0')
}

/// The whole number `text` spells, as digits with no sign and no leading zeros
/// — or `None` when what it spells is not a whole number.
///
/// `1e10` spells `10000000000`, `2.50e1` spells `25`, and `99999999999999999999.0`
/// spells twenty nines. `1.5`, `1e-5` and `1.0000000000000000001` spell no whole
/// number at all and are `None`: a fraction is a different KIND of figure, not a
/// whole number that ran off an end, and every rule built on this one has to be
/// able to tell those two apart.
///
/// It is the author's TEXT that is read, digit by digit, because the `f64` is
/// the one thing that no longer says what was written — which is the whole
/// reason [`whole_number_past_holding`] exists.
pub fn whole_number_written(text: &str) -> Option<String> {
    let text = text.trim();
    let body = text.strip_prefix(['+', '-']).unwrap_or(text);
    let (mantissa, exponent) = match body.split_once(['e', 'E']) {
        Some((m, e)) => (m, e.parse::<i32>().ok()?),
        None => (body, 0),
    };
    let (int, frac) = mantissa.split_once('.').unwrap_or((mantissa, ""));
    if int.is_empty() && frac.is_empty() {
        return None;
    }
    if !int.bytes().chain(frac.bytes()).all(|b| b.is_ascii_digit()) {
        return None;
    }
    // Where the decimal point ends up once the exponent has moved it.
    let shift = exponent.checked_sub(i32::try_from(frac.len()).ok()?)?;
    let mut digits = format!("{int}{frac}");
    if shift < 0 {
        // The figure has a fractional part unless every digit the point moves
        // back past is a zero: `2.50e1` is 25, and `2.55e1` is not a whole
        // number.
        let cut = usize::try_from(-shift).ok()?;
        if cut > digits.len()
            || !digits.as_bytes()[digits.len() - cut..]
                .iter()
                .all(|b| *b == b'0')
        {
            return None;
        }
        digits.truncate(digits.len() - cut);
    } else {
        // Nothing this long is a figure any `f64` holds, and the guard is here
        // so that `1e2000000000` cannot ask for two gigabytes of zeros.
        if shift > 400 {
            return None;
        }
        digits.push_str(&"0".repeat(shift as usize));
    }
    let trimmed = digits.trim_start_matches('0');
    Some(if trimmed.is_empty() {
        "0".to_string()
    } else {
        trimmed.to_string()
    })
}

/// True when `text` spells a whole number and the `f64` it parses to would not
/// write that same whole number back.
///
/// **The question every arm of the number line here asks, asked of the figure
/// rather than of the spelling.** `99999999999999999999` parses to a perfectly
/// finite `1e20`, so no `is_finite` guard can see it; what gives it away is that
/// the double writes back `100000000000000000000`, which is not what was
/// written. `9223372036854775808` — `i64::MAX` plus one — writes back
/// `9223372036854776000`, twelve digits nobody typed.
///
/// **And it lets through everything that survives the trip.** `1e10` writes back
/// `10000000000` and `1e20` writes back `100000000000000000000`; both are the
/// figures on the page, reformatted, and reformatting is not corruption — it is
/// what `x-b: 1e10` coming out of `pact show` as `10000000000.0` already is.
/// `1.5` and `0.7` spell no whole number and are not this rule's business at
/// all: ordinary rounding near one is the business of every double there is, and
/// refusing it would mean refusing every number in the format (the reasoning is
/// set out at length beside [`underflowed_to_zero`]).
///
/// The earlier spelling of this rule was *"a run of ASCII digits that `i64`
/// cannot parse"*, and it was one character wide: `x-big: 99999999999999999999.0`
/// walked past it and three such documents published one hash again. A rule
/// about a figure cannot be written as a rule about how the figure is punctuated.
pub fn whole_number_past_holding(text: &str) -> bool {
    let Some(written) = whole_number_written(text) else {
        return false;
    };
    let Ok(f) = text.trim().parse::<f64>() else {
        return false;
    };
    // A figure that could not be read AT ALL is the `is_finite` arm's business
    // one screen up, and it keeps the text for its own reasons; answering here
    // as well would only mean two rules owning one line.
    if !f.is_finite() {
        return false;
    }
    written != format!("{}", f.abs())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::value::Value;
    use std::cell::Cell;

    fn parse(s: &str) -> Node {
        parse_yaml(s, Utf8Path::new("t.yaml")).expect("should parse")
    }

    /// How many copies of a shortcut's contents `f` made. See
    /// [`shortcut::Anchored::copy`], which is the only place one can be made.
    fn copies_made_by(f: impl FnOnce()) -> usize {
        let before = shortcut::COPIES_MADE.with(Cell::get);
        f();
        shortcut::COPIES_MADE.with(Cell::get) - before
    }

    #[test]
    fn spans_point_at_the_line_the_author_sees() {
        let n = parse("name: refund\ndescription: handles refunds\n");
        let desc = n.get("description").unwrap();
        assert_eq!(
            desc.span.line, 2,
            "line numbers must match the editor's gutter"
        );
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

    /// The far end of the same argument as `leading_zero_codes_stay_text`: a
    /// scalar this cannot hold as a number is kept as written rather than
    /// turned into a different value. Before this, `1e999` parsed to infinity
    /// and every way out of the tree wrote it as `null` — `to_json`, and
    /// `canonical` with it, so `x-threshold: 1e999` digested identically to
    /// `x-threshold:` and a lockfile could not tell the two apart.
    ///
    /// Mutation: drop `&& f.is_finite()` from the float arm of
    /// `resolve_scalar`. Without it this test reports `assertion left == right
    /// failed, left: None, right: Some("1e999")` — `None` because `as_str` has
    /// nothing to return from a `Float`. `leading_zero_codes_stay_text` and
    /// every other test in this module stay green.
    #[test]
    fn a_number_too_big_to_hold_stays_text() {
        let n = parse(concat!(
            "too-big: 1e999\n",
            "too-small: -1e999\n",
            "still-too-big: 1e400\n",
            "word: .inf\n",
            "not-a-number: .nan\n",
            "ordinary: 1.5\n",
            "exponent: 1e10\n",
            "fraction: 0.5\n",
        ));
        assert_eq!(n.get("too-big").unwrap().as_str(), Some("1e999"));
        assert_eq!(n.get("too-small").unwrap().as_str(), Some("-1e999"));
        assert_eq!(n.get("still-too-big").unwrap().as_str(), Some("1e400"));
        // YAML's own words for these were never numbers here: `resolve_scalar`
        // wants a digit before it reads a scalar as a number at all.
        assert_eq!(n.get("word").unwrap().as_str(), Some(".inf"));
        assert_eq!(n.get("not-a-number").unwrap().as_str(), Some(".nan"));
        // Nothing else moves.
        assert_eq!(n.get("ordinary").unwrap().value, Value::Float(1.5));
        assert_eq!(n.get("exponent").unwrap().value, Value::Float(1e10));
        assert_eq!(n.get("fraction").unwrap().value, Value::Float(0.5));
    }

    /// Two things the digest has to say, now that the value survives: the
    /// ordinary numbers hash exactly as they always did, and a number too big
    /// to hold no longer hashes the same as an empty setting.
    ///
    /// Mutation: the same one line. Without it this reports `assertion left !=
    /// right failed`, both sides
    /// `sha256:d57f757bbbd6a2bac4a867139ca33198446c87820edf5b3096e04aa29a0bbb3b`
    /// — which is the digest of `{"x-threshold":null}`, and the reason a
    /// lockfile could not tell the two documents apart. The `canonical_string`
    /// assertion above it passes either way: it is the guard that the ordinary
    /// numbers did not move, and they did not.
    #[test]
    fn a_number_too_big_to_hold_no_longer_digests_as_nothing() {
        assert_eq!(
            crate::canonical_string(&parse("a: 1.5\nb: 1e10\nc: 0.5\n")),
            r#"{"a":1.5,"b":10000000000,"c":0.5}"#,
            "the ordinary numbers must hash the way they always have"
        );
        assert_ne!(
            crate::digest(&parse("x-threshold: 1e999\n")),
            crate::digest(&parse("x-threshold:\n")),
            "a number and an empty setting are not the same document"
        );
        // The integer spelling, which no `is_finite` guard can see: all three of
        // these arrived as `1e20` and digested to one hash.
        assert_ne!(
            crate::digest(&parse("x-big: 99999999999999999999\n")),
            crate::digest(&parse("x-big: 99999999999999999998\n")),
            "two whole numbers one apart are two documents"
        );
        assert_ne!(
            crate::digest(&parse("x-big: 99999999999999999999\n")),
            crate::digest(&parse("x-big: 100000000000000000000\n")),
            "and so are these two"
        );
        // AND THE SAME THREE WITH A POINT ON THE END, which is where the rule
        // that keyed on a run of ASCII digits could not follow: measured with
        // that rule in place, these three published one hash,
        // `sha256:2aa9f0c9…` — the byte-identical figure this test's own note
        // calls the harm.
        assert_ne!(
            crate::digest(&parse("x-big: 99999999999999999999.0\n")),
            crate::digest(&parse("x-big: 99999999999999999998.0\n")),
            "a point on the end does not make two documents one document"
        );
        assert_ne!(
            crate::digest(&parse("x-big: 99999999999999999999.0\n")),
            crate::digest(&parse("x-big: 100000000000000000000.0\n")),
            "and neither does it here"
        );
    }

    #[test]
    fn a_whole_number_past_holding_keeps_its_digits() {
        // A double writing back digits nobody typed IS the machine saying it
        // cannot hold that figure: `99999999999999999999` comes back out of an
        // `f64` as `100000000000000000000`, and `9223372036854775808` as
        // `9223372036854776000`.
        //
        // **The last four spellings are the ones the digits-only rule could not
        // see**, and they are the same three figures with a point or an
        // exponent on them. Measured with that rule in place, every one of them
        // became a `Float` and lost its digits.
        for written in [
            "99999999999999999999",
            "9223372036854775808",
            "-9223372036854775809",
            "1234567890123456789012345678901234567890",
            "99999999999999999999.0",
            "9223372036854775808.0",
            "-99999999999999999999.00",
            "999999999999999999990e-1",
        ] {
            assert_eq!(
                parse(&format!("a: {written}\n")).get("a").unwrap().value,
                Value::Str(written.to_string()),
                "`{written}` cannot be held as a number and must keep its digits"
            );
        }
        // And the rule stops at the edge of what CAN be held, and reaches
        // nothing whose figure survives the trip — including the big round ones
        // an exponent spells, which write back exactly what was written.
        for (written, expected) in [
            ("9223372036854775807", Value::Int(i64::MAX)),
            ("-9223372036854775808", Value::Int(i64::MIN)),
            ("42", Value::Int(42)),
            ("1e10", Value::Float(1e10)),
            ("1.5", Value::Float(1.5)),
            ("0.7", Value::Float(0.7)),
            ("1e20", Value::Float(1e20)),
            ("10000000000000000000", Value::Float(1e19)),
            ("100000000000000000000.0", Value::Float(1e20)),
        ] {
            assert_eq!(
                parse(&format!("a: {written}\n")).get("a").unwrap().value,
                expected,
                "`{written}` is a number this can hold and must stay one"
            );
        }
    }

    /// The rule the two above are built on, asked directly, so that a change to
    /// it fails here first and in words rather than in a digest.
    #[test]
    fn a_whole_number_is_past_holding_when_it_writes_back_different_digits() {
        for written in [
            "99999999999999999999",
            "99999999999999999999.0",
            "9223372036854775808",
            "-9223372036854775809",
            "999999999999999999990e-1",
        ] {
            assert!(
                whole_number_past_holding(written),
                "`{written}` does not survive an f64"
            );
            assert!(
                whole_number_written(written).is_some(),
                "`{written}` spells a whole number"
            );
        }
        // `1.5e30` is on this side of the line and belongs there: it spells the
        // whole number 1500000000000000000000000000000 and an `f64` writes that
        // back digit for digit.
        for held in [
            "1e10",
            "1e20",
            "10000000000000000000",
            "42",
            "0",
            "-0.0e5",
            "1.5e30",
        ] {
            assert!(
                !whole_number_past_holding(held),
                "`{held}` survives an f64 exactly"
            );
        }
        // A figure that is not a whole number is not this rule's business, at
        // either scale: ordinary rounding near one is what every double does.
        for fraction in ["1.5", "0.7", "0.1000000000000000055511151231257827", "1e-5"] {
            assert!(
                whole_number_written(fraction).is_none(),
                "`{fraction}` is not a whole number"
            );
            assert!(
                !whole_number_past_holding(fraction),
                "`{fraction}` is not this rule's"
            );
        }
        // And a figure no double can hold at all belongs to the `is_finite`
        // arm, which keeps the text for its own reasons.
        assert!(
            !whole_number_past_holding("1e999"),
            "`1e999` is the other arm's"
        );
        assert_eq!(whole_number_written("2.50e1").as_deref(), Some("25"));
        assert_eq!(whole_number_written("2.55e1"), None);
        assert_eq!(whole_number_written("nan"), None);
    }

    #[test]
    fn duplicate_keys_are_an_error_with_both_locations() {
        let err = parse_yaml("model: a\nmodel: b\n", Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/duplicate-key");
        assert_eq!(err.span.line, 2);
        assert_eq!(
            err.related.len(),
            1,
            "must point at the first occurrence too"
        );
        assert_eq!(err.related[0].span.line, 1);
    }

    #[test]
    fn missing_value_is_reported_against_the_key() {
        let err = parse_yaml("agents:\n  a: 1\n  b:\n", Utf8Path::new("t.yaml"));
        // `b:` with nothing after it is a null value in YAML, which is legal.
        assert!(
            err.is_ok(),
            "an empty value is legal YAML and means 'nothing'"
        );
    }

    #[test]
    fn syntax_errors_explain_themselves_in_plain_language() {
        let err = parse_yaml("name: [unclosed\n", Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/yaml-syntax");
        assert!(err.fix.contains("indentation") || err.fix.contains("quote"));
        assert!(
            !err.message.contains("Token"),
            "parser jargon must not leak to the author"
        );
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
        assert_eq!(
            n.get("use").unwrap().get("model").unwrap().as_str(),
            Some("fast")
        );
    }

    /// The alias bomb, as small as it can be written: a nine-item list, then
    /// `levels` shortcuts each written out of nine copies of the one above it.
    /// Every level multiplies by nine, so `levels` of 5 is 597,871 settings in
    /// seven lines of text.
    fn alias_bomb(levels: usize) -> String {
        let mut s =
            String::from("n0: &n0 [\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\"]\n");
        for i in 1..=levels {
            let prev = i - 1;
            let refs = vec![format!("*n{prev}"); 9].join(",");
            s.push_str(&format!("n{i}: &n{i} [{refs}]\n"));
        }
        s
    }

    #[test]
    fn a_shortcut_that_copies_itself_wider_every_line_is_refused_by_the_size_limit() {
        // Measured before the fix, on a workspace holding the eight-level form
        // of this: `pact check` died with "memory allocation of 1368 bytes
        // failed" and exit 134 — the process killed outright, no diagnostic
        // printed. `*name` was charged one setting however much it expanded to,
        // and it was charged *after* the copy had already been made.
        //
        // Mutation: put the arm back as it was — `match
        // self.anchors.get(&id).cloned() { Some(node) => self.emit(node, 0), …
        // }`. This test then reports "called `unwrap_err()` on an `Ok` value",
        // because the five-level tree loads all 597,871 of its settings without
        // complaint.
        //
        // **M1 does not stop here, and the note that said it did was wrong: it
        // claimed "the other sixteen tests in this module stayed green" when
        // there were twenty-four others and four of them were red.**
        // Re-measured on this module as it now stands, `cargo test -p pact-doc
        // --lib` under M1 → `test result: FAILED. 42 passed; 6 failed`, the six
        // being this test (`span.col` 9 where 10 is asserted, because the
        // definition charge alone now runs the budget out one copy earlier),
        // `a_shortcut_that_stands_for_a_lot_of_writing_...` (`span.line` 1 where
        // 27 is asserted), `a_shortcut_that_copies_itself_deeper_every_line_...`
        // and `a_file_a_shortcut_filled_up_...` (both `unwrap_err()` on an `Ok`),
        // `a_shortcut_too_big_to_copy_is_refused_without_first_copying_it`, and
        // `the_size_limit_names_something_the_author_can_actually_do` (which
        // gets the definition wording where it asserts the copy wording). Six
        // of forty-eight. The two named as surviving do survive:
        // `anchors_and_aliases_resolve` and `unknown_alias_is_a_clear_error`
        // are green under it.
        let err = parse_yaml(&alias_bomb(5), Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/too-large");
        // Measured, not predicted, and re-measured after defining `&name` was
        // charged for the copy it keeps: n0..n4 cost 149,469 settings rather
        // than 74,732, because each of them is paid for twice — once as it is
        // read and once as it is kept. So the budget now runs out on the
        // *first* of n5's nine copies of n4, at line 6 column 10, where before
        // it lasted until the second copy at column 14.
        assert_eq!(
            err.span.line, 6,
            "point at the line whose shortcut went over"
        );
        assert_eq!(
            err.span.col, 10,
            "at the copy that went over, not at the start of the line"
        );
        assert!(
            err.message.contains("shortcut") && err.message.contains("200000 settings"),
            "say what went over and by what: {}",
            err.message
        );
    }

    /// The other shape of the same bomb: not many settings, but one setting
    /// holding a great deal of writing, named once and used over and over.
    /// `copies` uses of a `bytes`-long piece of writing.
    fn text_bomb(bytes: usize, copies: usize) -> String {
        let mut s = format!("g: &g \"{}\"\n", "z".repeat(bytes));
        for i in 0..copies {
            s.push_str(&format!("u{i}: *g\n"));
        }
        s
    }

    #[test]
    fn a_shortcut_that_stands_for_a_lot_of_writing_is_refused_by_the_size_limit() {
        // Counting settings is not counting size, and a limit that only counts
        // settings is blind to this document entirely: 25,001 settings, three
        // orders of magnitude under the limit, and 3.75 GB of writing. Measured
        // on a 413,946-byte workspace built exactly this way, `pact check` died
        // with "memory allocation of 150000 bytes failed", signal 6, exit 134,
        // at 3,989,076 KB resident — the same death the settings limit had just
        // been fixed to prevent, through the same `*name` copy, on a file a
        // third the size.
        //
        // Mutation (M2): charge the settings budget only — `self.afford(size,
        // 0)` in the alias arm, `self.afford(1, 0)` in `emit`, and
        // `self.afford(priced.size, 0)` where a definition is kept. This test
        // then reports "called `unwrap_err()` on an `Ok` value".
        //
        // **It is not the only one, and the note that said so was wrong.**
        // Measured on this module as it now stands, M2 gives `test result:
        // FAILED. 45 passed; 3 failed` — this test,
        // `the_size_limit_names_something_the_author_can_actually_do` (which
        // asserts the wording of the same refusal) and
        // `a_file_that_really_is_that_big_is_refused_in_its_own_words` (four
        // megabytes of writing with no shortcut in it at all, which is the
        // second budget's other half).
        let err = parse_yaml(&text_bomb(150_000, 60), Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/too-large");
        // Measured, not predicted — 29 was the guess, then 28, and it is now
        // 27. The piece of writing is charged where it is written AND again
        // for the copy `&g` keeps, which is 300,000 bytes before a single
        // `*g`; so the 26th copy is the one past 4 MB, and that copy is `u25`,
        // on line 27.
        assert_eq!(err.span.line, 27, "point at the copy that went over");
        assert!(
            err.message.contains("shortcut") && err.message.contains("4 MB"),
            "say what went over and by what: {}",
            err.message
        );
    }

    #[test]
    fn the_size_limit_names_something_the_author_can_actually_do() {
        let err = parse_yaml(&alias_bomb(5), Utf8Path::new("t.yaml")).unwrap_err();
        assert!(
            err.fix
                .contains("Write the values you need here out in full"),
            "{}",
            err.fix
        );
        assert!(
            err.fix.contains("split them across several files"),
            "{}",
            err.fix
        );

        // Both ways of being too big have to read as English, not just the one
        // that was fixed first.
        let big = parse_yaml(&text_bomb(150_000, 60), Utf8Path::new("t.yaml")).unwrap_err();
        assert!(
            big.fix
                .contains("Write the values you need here out in full"),
            "{}",
            big.fix
        );

        // The reader is a support lead, not a programmer.
        for d in [&err, &big] {
            let all = format!("{} {}", d.message, d.fix).to_lowercase();
            for jargon in [
                "alias", "anchor", "node", "yaml", "expand", "allocat", "recurs",
            ] {
                assert!(!all.contains(jargon), "diagnostic leaked '{jargon}': {all}");
            }
        }
    }

    #[test]
    fn a_file_that_really_is_that_big_is_refused_in_its_own_words() {
        // No shortcut anywhere: the writing is simply there, all four megabytes
        // of it. The advice has to be different — nothing is being copied in,
        // so "write the values out in full" would be nonsense — and it has to
        // name the thing the author can do, which is move the long pieces of
        // writing into files beside this one.
        let mut s = String::new();
        for i in 0..60 {
            s.push_str(&format!("p{i}: \"{}\"\n", "z".repeat(150_000)));
        }
        let err = parse_yaml(&s, Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/too-large");
        assert!(err.message.contains("too much writing"), "{}", err.message);
        assert!(
            err.fix.contains("files of their own beside this one"),
            "{}",
            err.fix
        );
        assert!(
            !err.message.contains("shortcut"),
            "no shortcut is involved: {}",
            err.message
        );
    }

    #[test]
    fn a_file_a_shortcut_filled_up_is_not_blamed_on_the_next_ordinary_line() {
        // The mirror of the test above, which existed in one direction only: it
        // asserted that a file with no shortcut in it is not told about
        // shortcuts, and nothing asserted the converse. So once a `*name` had
        // spent almost the whole budget, the next ordinary literal setting
        // tipped it over and got the no-shortcut-involved wording — *"This file
        // is too large to load (over 200000 settings). fix: Split it into
        // several files."* — with the caret under `z5: 1`, on a file of 738
        // bytes and 72 lines. Measured through `pact check` on the build this
        // was found in. A support lead handed that report has no path from the
        // message to the cause: the file is not large, and the line named is
        // three characters that cost one setting.
        //
        // Mutation (M6): in `emit`, call `over.written_out(node.span.clone())`
        // directly instead of going through `over_budget`. Measured: `test
        // result: FAILED. 47 passed; 1 failed` — this test alone, on the
        // assertion that the blamed line holds a `*n` — and `cargo test -p
        // pact-cli --test a_shortcut_that_copies_itself_cannot_bring_down_the_
        // checker` green at 7 passed. Nothing else in either suite looks at
        // which line a refusal points at when a shortcut paid for the budget,
        // which is why the false report survived a whole round of review.
        let mut doc = alias_bomb(3);
        for i in 0..24 {
            doc.push_str(&format!("a{i}: *n3\n"));
        }
        for i in 0..7 {
            doc.push_str(&format!("b{i}: *n2\n"));
        }
        for i in 0..5 {
            doc.push_str(&format!("c{i}: *n1\n"));
        }
        doc.push_str("d0: *n0\n");
        for i in 0..40 {
            doc.push_str(&format!("z{i}: 1\n"));
        }
        assert!(
            doc.len() < 1000,
            "a file this small must not be called too large: {}",
            doc.len()
        );

        let err = parse_yaml(&doc, Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/too-large");
        let blamed = doc
            .lines()
            .nth(err.span.line - 1)
            .expect("the caret lands inside the file");
        assert!(
            blamed.contains("*n"),
            "the caret is on an ordinary line the author cannot act on: `{blamed}`"
        );
        assert!(
            err.message.contains("shortcut"),
            "a shortcut paid for the budget and must be named: {}",
            err.message
        );
    }

    #[test]
    fn shortcuts_written_inside_one_another_are_refused_though_none_is_ever_used() {
        // Defining `&name` keeps a copy, and a definition written inside
        // another definition is therefore kept once per level. That cost was
        // charged against neither budget, so the whole class of document below
        // walked past every limit: measured through `pact check` on a file of
        // 62 nested definitions holding 190,000 words and NO `*name` anywhere,
        // peak resident memory was 3,683,232 KB and the answer was a schema
        // complaint about the field name; under `ulimit -v 1500000` it was
        // `memory allocation of 1 bytes failed`, signal 6, EXIT=134. The same
        // tree with the `&name`s removed peaked at 127,816 KB.
        //
        // No `*name` is the whole point. Every test that held the size fix
        // before this one went through `Event::Alias`, so none of them could
        // reach this document at all.
        //
        // Mutation (M5): drop the `afford` in `emit` that pays for the kept
        // copy. This test then reports "called `unwrap_err()` on an `Ok` value"
        // — the document loads, all 620,000 kept settings of it. Measured:
        // `test result: FAILED. 43 passed; 5 failed` here (this test,
        // `a_shortcut_too_big_to_copy_...`, `a_file_a_shortcut_filled_up_...`,
        // `a_shortcut_that_copies_itself_wider_every_line_...` and
        // `a_shortcut_that_stands_for_a_lot_of_writing_...`, the last two
        // because the second charge is what fixed the line and column they
        // assert), and `5 passed; 2 failed` in
        // `crates/pact-cli/tests/a_shortcut_that_copies_itself_cannot_bring_
        // down_the_checker.rs`.
        let leaves = vec!["\"x\""; 20_000].join(",");
        let mut nested = format!("[{leaves}]");
        for i in 0..30 {
            nested = format!("&n{i} [{nested}]");
        }
        let doc = format!("d: {nested}\n");
        assert!(
            !doc.contains('*'),
            "no shortcut is used anywhere in this document"
        );

        let err = parse_yaml(&doc, Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/too-large");
        assert!(
            err.message.contains("Naming this for reuse"),
            "say that naming it is what costs: {}",
            err.message
        );
        // The reader is a support lead, not a programmer — the same bar the two
        // wordings either side of this one are held to.
        let all = format!("{} {}", err.message, err.fix).to_lowercase();
        for jargon in [
            "alias", "anchor", "node", "yaml", "expand", "allocat", "recurs",
        ] {
            assert!(!all.contains(jargon), "diagnostic leaked '{jargon}': {all}");
        }
    }

    #[test]
    fn a_shortcut_too_big_to_copy_is_refused_without_first_copying_it() {
        // The limits have to be consulted *before* the copy is made, and no
        // assertion about a parse result can tell the difference: clone-first
        // and check-first produce the identical refusal, word for word.
        // Measured on the eight-line document this was found on, through the
        // real command: clone-first peaked at 89,628 KB against 69,620 KB — a
        // 29% regression the whole suite was blind to, so a later refactor
        // could quietly undo half the fix and every test would still pass.
        //
        // The one observable difference is whether the copy happened, so that
        // is what this counts. It is instrumentation rather than an outcome the
        // author could see, which is the trade being made knowingly: the
        // outcome the author sees is covered by the tests either side of this
        // one, and this covers the thing the operating system sees. The count
        // is sound because `Anchored::node` is private to its module — there is
        // no way to copy a shortcut that does not go through `Anchored::kept`
        // or `Anchored::copy`.
        //
        // **There are two copies per shortcut, and for a round this counted
        // one.** `&name` keeps a copy as it is defined; `*name` takes another.
        // Only the second went through `Anchored::copy`, so this test could not
        // see the first at all — which is why a file of nested `&name`
        // definitions and no `*name` anywhere went to 3.6 GB with the whole
        // suite green. The definition is now counted and charged too, and the
        // third block below is the case the old shape was structurally blind
        // to: it never reaches an `Event::Alias`.
        //
        // Mutation (M3): in the alias arm, hoist the copy above the two checks
        // — `let taken = self.anchors.get(&id).map(|a| (a.copy(), a.priced));`
        // — and attach it after them. Measured: `test result: FAILED. 47
        // passed; 1 failed`, this test alone, reporting `left: 2, right: 1` at
        // the "refused at the use" assertion; `cargo test -p pact-cli --test
        // a_shortcut_that_copies_itself_cannot_bring_down_the_checker` stays
        // green at 7 passed, which is the blindness this test exists to cover.
        //
        // Mutation (M8), the definition half: in `emit`, move
        // `self.anchors.insert(anchor, Anchored::kept(&node, priced));` above
        // the `afford` that pays for it. Measured: the same shape — `47 passed;
        // 1 failed`, this test alone, this time reporting 1 copy where 0 were
        // allowed at the "refused at the definition" assertion, and the CLI
        // file again green at 7 passed. `pact check` on the nested file prints
        // the identical refusal under M8, having already allocated the copy it
        // is refusing.

        // The control, so a counter that never counts cannot pass this: a
        // shortcut that fits is kept once and copied once.
        let honest_use = copies_made_by(|| {
            let n = parse_yaml("small: &s [1,2]\nuse: *s\n", Utf8Path::new("t.yaml"));
            assert!(n.is_ok(), "a two-item shortcut is not a bomb");
        });
        assert_eq!(
            honest_use, 2,
            "one copy kept where it is defined, one taken where it is used"
        );

        // Refused at the USE. The block fits, and fits again as the copy `&big`
        // keeps — 70,002 settings, then 70,001 more — so one `*big` is what
        // goes over. One copy exists at that point (the kept one) and the
        // second must never be asked for.
        let fits_once = vec!["\"x\""; 70_000].join(",");
        let refused_at_the_use = copies_made_by(|| {
            let doc = format!("big: &big [{fits_once}]\nuse: *big\n");
            let e = parse_yaml(&doc, Utf8Path::new("t.yaml")).unwrap_err();
            assert_eq!(e.rule, "doc/too-large", "one more copy is over the limit");
            assert!(
                e.message.contains("shortcut"),
                "the use is what went over: {}",
                e.message
            );
        });
        assert_eq!(
            refused_at_the_use, 1,
            "the copy was made and then refused — the memory had already been asked for, \
             which is the whole of what killed the loader"
        );

        // Refused at the DEFINITION, with no `*name` in the document at all.
        // 150,001 settings are inside the limit; keeping a second copy of them
        // is not, and nothing may be allocated to find that out.
        let items = vec!["\"x\""; 150_000].join(",");
        let refused_at_the_definition = copies_made_by(|| {
            let doc = format!("big: &big [{items}]\n");
            assert!(
                !doc.contains('*'),
                "this document uses no shortcut, it only defines one"
            );
            let e = parse_yaml(&doc, Utf8Path::new("t.yaml")).unwrap_err();
            assert_eq!(
                e.rule, "doc/too-large",
                "keeping the copy is over the limit"
            );
            assert!(
                e.message.contains("Naming this for reuse"),
                "say that naming it is what costs: {}",
                e.message
            );
        });
        assert_eq!(
            refused_at_the_definition, 0,
            "the copy a definition keeps was made before the budget was asked about it"
        );
    }

    #[test]
    fn a_shortcut_that_copies_itself_deeper_every_line_is_refused_by_the_nesting_limit() {
        // The same hole in the other limit, and the cheaper half to reach: this
        // document is under a hundred settings in total, so the size limit
        // never speaks — nesting is the only thing wrong with it. `push` is the
        // only place `MAX_DEPTH` was ever checked and an alias never reaches
        // it, so the whole tower loaded and the promised limit was a comment.
        //
        // Enforced rather than documented-as-unenforced because the depth was
        // already being measured: the same walk that prices a shortcut's size
        // prices its depth, so this costs nothing to check and closes the hole
        // for the caller downstream — `to_json`, `node_count` and the schema
        // walk are all recursive, and a tree the loader let past at ten
        // thousand levels would overflow one of their stacks instead.
        //
        // Mutation: the same restored arm. This test then reports "called
        // `unwrap_err()` on an `Ok` value" with the whole seventy-deep tree
        // printed out.
        let mut s = String::from("n0: &n0 [\"x\"]\n");
        for i in 1..=70 {
            s.push_str(&format!("n{i}: &n{i} [*n{}]\n", i - 1));
        }
        let err = parse_yaml(&s, Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/too-deep");
        assert!(err.message.contains("64 levels deep"), "{}", err.message);
        assert!(err.fix.contains("out in full"), "{}", err.fix);
    }

    #[test]
    fn a_shortcut_and_the_word_it_stands_for_are_refused_at_the_same_depth() {
        // `*name` and the value it names have to be interchangeable, or the
        // shortcut is not a shortcut. The nesting limit nearly broke that:
        // `depth` counts the copied value's own outermost level and so does
        // `stack.len()` for the container it lands in, so charging both refused
        // a shortcut for a plain word one level shallower than the word itself.
        // Measured before the subtraction, through the real command: at 63
        // levels the literal loaded and the shortcut for it was refused.
        //
        // Written as a sweep across the boundary rather than against a measured
        // number, because the claim is *the two agree*, not *they change at 64*.
        // The two assertions below stop it passing by agreeing on nothing.
        let mut refused_any = false;
        let mut loaded_any = false;
        for n in 60..=66 {
            let nest = |leaf: &str| format!("d: {}{leaf}{}\n", "[".repeat(n), "]".repeat(n));
            let literal = parse_yaml(&nest("\"x\""), Utf8Path::new("t.yaml"));
            let shortcut = parse_yaml(
                &format!("g: &g \"x\"\n{}", nest("*g")),
                Utf8Path::new("t.yaml"),
            );
            let refused =
                |r: &Result<Node, Box<Diagnostic>>| r.as_ref().err().map(|d| d.rule).unwrap_or("");
            assert_eq!(
                refused(&literal),
                refused(&shortcut),
                "at {n} levels the word and the shortcut for it were treated differently"
            );
            refused_any |= literal.is_err();
            loaded_any |= literal.is_ok();
        }
        assert!(
            refused_any && loaded_any,
            "the sweep never crossed the limit, so it proved nothing"
        );
    }

    #[test]
    fn a_shortcut_that_stands_for_one_word_still_costs_one_setting() {
        // The common, honest use of a shortcut, and the one the new accounting
        // must not make more expensive: `*name` for a scalar copies one setting
        // in and is charged one.
        let mut s = String::from("greeting: &g hello\n");
        for i in 0..5_000 {
            s.push_str(&format!("u{i}: *g\n"));
        }
        let n = parse_yaml(&s, Utf8Path::new("t.yaml")).expect("five thousand words is not a bomb");
        assert_eq!(n.get("u4999").unwrap().as_str(), Some("hello"));
    }

    #[test]
    fn unknown_alias_is_a_clear_error() {
        let err = parse_yaml("use: *nope\n", Utf8Path::new("t.yaml")).unwrap_err();
        assert_eq!(err.rule, "doc/unknown-reference");
    }

    #[test]
    fn offset_shifts_spans_for_embedded_fragments() {
        let n = parse_yaml_at(
            "name: x\n",
            Utf8Path::new("t.md"),
            Offset { line: 3, byte: 40 },
        )
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
        assert_eq!(
            desc.value,
            Value::Null,
            "nothing after the colon means nothing"
        );
        assert_eq!(
            desc.span.line, 1,
            "the line the author left empty, not the one after it"
        );
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
        assert!(
            desc.span.byte_end > desc.span.byte_start,
            "an empty span underlines nothing"
        );
    }

    #[test]
    fn an_empty_value_written_out_as_quotes_keeps_its_own_place() {
        // `""` is characters on the page, so the parser's own mark is right and
        // borrowing the name would be less precise, not more.
        let n = parse("description: \"\"\nkind: c\n");
        let desc = n.get("description").unwrap();
        assert_eq!(desc.value, Value::Str(String::new()));
        assert_eq!(desc.span.line, 1);
        assert_eq!(
            desc.span.col,
            "description: ".len() + 1,
            "at the quotes, not at the name"
        );
    }

    #[test]
    fn a_setting_name_left_empty_is_still_located_by_the_parser() {
        // The borrowed span comes from a *pending key*, so a name with no value
        // must not be mistaken for a value with no name. `{: 1}` has no name to
        // borrow, and asking for one would panic or point at the wrong entry.
        let n = parse("a:\nb: 1\n");
        assert_eq!(n.get("a").unwrap().span.line, 1);
        assert_eq!(
            n.get("b").unwrap().span.line,
            2,
            "the next setting is untouched"
        );
    }

    #[test]
    fn quoted_scalars_are_always_text() {
        let n = parse("a: \"true\"\nb: '42'\n");
        assert_eq!(n.get("a").unwrap().as_str(), Some("true"));
        assert_eq!(n.get("b").unwrap().as_str(), Some("42"));
    }
}
