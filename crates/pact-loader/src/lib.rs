//! **The Expansion Rule** — the normative tree→document loader.
//!
//! > *A directory is a field; a field may be a directory.*
//!
//! This one rule replaces the fixed slot table that filesystem-first frameworks
//! (Vercel Eve and its peers) hard-code. It is what makes the authoring surface
//! simultaneously trivial for a beginner and unbounded for an expert: a
//! five-line `agent.yaml` and a hundred-file tree are the *same document*,
//! and any future field gets its directory form for free (invariant E-3).
//!
//! Decision D2 elevates this from convenience to semantics: the tree is the
//! **native, authoritative** form of a PACT agent, so this algorithm is part of
//! the specification, not an implementation detail.
//!
//! # The algorithm
//!
//! Loading a path yields one [`Node`]:
//!
//! - a **file** becomes its parsed value (YAML/JSON → a tree, Markdown → prose
//!   or front matter + prose, other → a [file reference](pact_doc::FileRef));
//! - a **directory** becomes a set of settings, one per entry, keyed by the
//!   entry's name with its extension and any ordinal prefix removed.
//!
//! A directory may contain a **self file** (`_index.yaml`, or a file named
//! after the directory) supplying the directory's *own* fields. Sibling entries
//! then contribute additional fields.
//!
//! # What is deliberately an error
//!
//! Every ambiguity is refused rather than resolved by precedence (thesis T7 —
//! there is no silent loss anywhere). Defining `instructions` both in
//! `agent.yaml` and as `instructions.md` is a mistake the author wants to know
//! about; picking a winner would hide it.
//!
//! # Ordering
//!
//! Filesystem read order is not stable across platforms, so it is never used.
//! Entries sort by ordinal prefix first (`01-fetch.yaml` before
//! `02-summarise.yaml`), then by name. The resulting document — and therefore
//! its digest — is reproducible on any machine.

pub mod approvals;
pub mod available;
pub mod bundles;
pub mod callable;
pub mod currency;
pub mod derive;
pub mod firstfile;
pub mod money;
pub mod policy;
pub mod ports;
pub mod reach;
pub mod reachability;
pub mod redaction;
pub mod report;
pub mod review;
pub mod teams;
pub mod teamwork;
pub mod unnamed;

use camino::{Utf8Path, Utf8PathBuf};
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Entry, FileRef, Map, Node, Payload, Value, parse_markdown, parse_yaml};
use policy::{FileKind, Ignore, Policy, split_ordinal};
use std::collections::HashMap;

/// Maximum directory nesting. Far above any real spec tree; exists so a
/// symlink loop or a pathological tree fails fast with a clear message.
const MAX_DIR_DEPTH: usize = 32;

pub struct Loader {
    root: Utf8PathBuf,
    policy: Policy,
}

/// One classified directory entry, before loading.
#[derive(Clone)]
struct Candidate {
    key: String,
    ordinal: Option<u32>,
    path: Utf8PathBuf,
    /// Span identifying the file itself, for diagnostics about the *name*.
    span: Span,
}

impl Loader {
    pub fn new(root: impl Into<Utf8PathBuf>) -> Self {
        Self { root: root.into(), policy: Policy::default() }
    }

    pub fn with_policy(root: impl Into<Utf8PathBuf>, policy: Policy) -> Self {
        Self { root: root.into(), policy }
    }

    pub fn policy(&self) -> &Policy {
        &self.policy
    }

    /// Load a file or directory into a single document node.
    ///
    /// Returns `None` only when nothing loadable was found; recoverable
    /// problems are reported through `diags` and the load continues, so an
    /// author sees every mistake in one pass rather than one per run.
    pub fn load(&self, path: &Utf8Path, diags: &mut Diagnostics) -> Option<Node> {
        let mut stack = Vec::new();
        self.load_path(path, diags, &mut stack)
    }

    fn load_path(
        &self,
        path: &Utf8Path,
        diags: &mut Diagnostics,
        stack: &mut Vec<Utf8PathBuf>,
    ) -> Option<Node> {
        let meta = match std::fs::symlink_metadata(path) {
            Ok(m) => m,
            Err(e) => {
                diags.push(Diagnostic::error(
                    "loader/unreadable",
                    Span::whole_file(path),
                    format!("Could not read '{path}': {e}"),
                    "Check the name is spelled correctly and that you have permission to read it.",
                ));
                return None;
            }
        };

        if meta.file_type().is_symlink() && !self.policy.follow_symlinks {
            diags.push(Diagnostic::warning(
                "loader/symlink-skipped",
                Span::whole_file(path),
                format!("'{path}' is a shortcut to somewhere else, so it was skipped."),
                "Move or copy the real file into this folder. Shortcuts are ignored because they \
                 can point outside the project.",
            ));
            return None;
        }

        if meta.is_dir() { self.load_dir(path, diags, stack) } else { self.load_file(path, diags) }
    }

    fn load_file(&self, path: &Utf8Path, diags: &mut Diagnostics) -> Option<Node> {
        let kind = self.policy.file_kind(path);
        let size = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);

        if kind == FileKind::Opaque {
            return Some(Node::new(
                Value::File(FileRef {
                    path: self.relative(path),
                    content_type: self.policy.content_type(path),
                    size_bytes: size,
                }),
                Span::whole_file(path),
            ));
        }

        if size > self.policy.max_text_bytes {
            let mb = self.policy.max_text_bytes / (1024 * 1024);
            diags.push(Diagnostic::error(
                "loader/file-too-large",
                Span::whole_file(path),
                format!("'{path}' is too big to load (limit is {mb} MB)."),
                "Split it into several smaller files in a folder of the same name. \
                 Every file in that folder becomes one setting.",
            ));
            return None;
        }

        let text = match std::fs::read_to_string(path) {
            Ok(t) => t,
            // Raw Rust/OS error text used to reach the reader with a fix about a
            // different problem: a Latin-1 file said *"stream did not contain
            // valid UTF-8"* and was told to rename its extension, and a file with
            // no read permission got the same advice. Split on the kind, and do
            // not interpolate `{e}` — nobody outside this process wrote it.
            Err(e) => {
                let (what, fix) = match e.kind() {
                    std::io::ErrorKind::InvalidData => (
                        format!("'{path}' is not saved as plain UTF-8 text."),
                        "Re-save it from your editor choosing UTF-8 (in most editors: \
                         File → Save As → Encoding: UTF-8). If it is an image, sound or \
                         other non-text file, give it its proper file extension instead."
                            .to_string(),
                    ),
                    std::io::ErrorKind::PermissionDenied => (
                        format!("'{path}' cannot be opened."),
                        "Check that you have permission to read it.".to_string(),
                    ),
                    _ => (
                        format!("'{path}' could not be read."),
                        "If this is an image, sound or other non-text file, give it its \
                         proper file extension so it is treated as an attachment."
                            .to_string(),
                    ),
                };
                diags.push(Diagnostic::error(
                    "loader/unreadable",
                    Span::whole_file(path),
                    what,
                    fix,
                ));
                return None;
            }
        };
        // A UTF-8 BOM is what Windows Notepad and Excel write — the D13 author's
        // editor — and it is invisible in the echoed source line, so a file that
        // began with one produced `error: '\u{feff}description' is not something
        // a port can have. fix: Did you mean 'description'?`: the same word
        // twice, and a fix nobody can type. Absorbed the way a trailing newline
        // is. Three bytes, so every span after it still lands.
        let text = text.strip_prefix('\u{feff}').map(str::to_string).unwrap_or(text);
        diags.add_source(path, text.clone());

        match kind {
            FileKind::PlainText => Some(Node::str(text.clone(), whole(path, &text))),
            FileKind::Structured => match parse_yaml(&text, path) {
                Ok(n) => Some(n),
                Err(d) => {
                    diags.push(*d);
                    None
                }
            },
            FileKind::Prose => match parse_markdown(&text, path) {
                Ok(md) => {
                    let (node, warn) = md.into_node(&self.policy.body_field);
                    if let Some(w) = warn {
                        diags.push(w);
                    }
                    Some(node)
                }
                Err(d) => {
                    diags.push(*d);
                    None
                }
            },
            FileKind::Opaque => unreachable!("handled above"),
        }
    }

    fn load_dir(
        &self,
        dir: &Utf8Path,
        diags: &mut Diagnostics,
        stack: &mut Vec<Utf8PathBuf>,
    ) -> Option<Node> {
        if stack.len() >= MAX_DIR_DEPTH {
            diags.push(Diagnostic::error(
                "loader/too-deep",
                Span::whole_file(dir),
                format!("Folders are nested more than {MAX_DIR_DEPTH} levels deep at '{dir}'."),
                "Flatten the structure. This usually means a folder links back into itself.",
            ));
            return None;
        }

        // Cycle detection on resolved paths, which catches symlink loops even
        // when following is enabled.
        let real = std::fs::canonicalize(dir)
            .ok()
            .and_then(|p| Utf8PathBuf::from_path_buf(p).ok())
            .unwrap_or_else(|| dir.to_owned());
        if stack.contains(&real) {
            diags.push(Diagnostic::error(
                "loader/cycle",
                Span::whole_file(dir),
                format!("'{dir}' contains itself, so loading would never finish."),
                "Remove the shortcut that points back to a folder further up the tree.",
            ));
            return None;
        }
        stack.push(real);

        // A payload directory is a file set, not structure. Expanding it would
        // turn `setup.py` into a field called `setup` and quietly lose the
        // extension — the kind of silent loss T7 forbids.
        if self.policy.is_payload_dir(dir) {
            let node = self.load_payload(dir, diags);
            stack.pop();
            return Some(node);
        }

        let dir_name = dir.file_name().unwrap_or_default().to_string();
        let (candidates, self_file) = self.classify(dir, &dir_name, diags);

        // Start from the self file's fields, if there is one.
        let mut base = match &self_file {
            Some(sf) => match self.load_file(&sf.path, diags) {
                Some(n) => self.fields_of_self_file(n, sf, diags),
                // A SELF FILE that would not parse is the same case as the
                // sibling file below, and used to be handled as if it were the
                // opposite one: an empty set of settings, which reads as "this
                // folder was described, and the description says nothing".
                //
                // So one tab in `agents/fraud-checker/agent.yaml` produced two
                // errors — `tabs disallowed within this context` at line 4, and
                // *"An agent must have a 'description'."* against the folder —
                // while line 2 of that very file reads `description: Looks for
                // signs that a refund request is not genuine.` The author is
                // told to add a line they can see on the screen; that reads as
                // the tool being broken, not as their mistake. A duplicate key
                // did the same. Both measured on the worked example.
                //
                // Nothing is known about a document nobody could read, so
                // nothing is said about it: it has no fields, and therefore no
                // fields to be missing. The syntax error itself, with its file,
                // line and caret, is the one message — and it is the only one
                // whose fix, typed, leaves a correct file.
                None => unloaded(&Span::whole_file(dir)),
            },
            // No self file at all: this folder's own settings have nowhere to
            // be written, so the span says so and carries the file an author
            // would create. Without it, every report of a setting this folder
            // owes came out as `--> <folder>:1:1` with the fix *"Add a line"* —
            // a line, a column and a line-to-add, all about a file that is not
            // there. See `firstfile`.
            None => Node::map(
                Map::new(),
                Span::in_folder(dir, firstfile::to_start(&self.root, &self.policy, dir)),
            ),
        };

        for cand in candidates {
            // A field defined by the self file AND by a sibling entry is
            // ambiguous. Refuse rather than pick (T7).
            if let Some(existing) = base.as_map().and_then(|m| m.get(&cand.key)) {
                let prior = existing.key_span.clone();
                let self_name = self_file
                    .as_ref()
                    .map_or_else(|| "the file above".to_string(), |s| s.path.to_string());
                diags.push(
                    Diagnostic::error(
                        "loader/ambiguous-field",
                        cand.span.clone(),
                        format!(
                            "'{}' is set in two places: here, and inside {}.",
                            cand.key, self_name
                        ),
                        format!(
                            "Keep only one. Either delete '{}' from {}, or delete this file.",
                            cand.key, self_name
                        ),
                    )
                    .with_related(prior, "also set here"),
                );
                continue;
            }

            match self.load_path(&cand.path, diags, stack) {
                Some(node) => base.insert(cand.key, cand.span, node),
                // A file that would not parse still CONTRIBUTES ITS NAME.
                //
                // Dropping the key with the value turned one ordinary YAML typo
                // into four diagnostics: the real one, plus three saying
                // *"'question' names 'is-this-ok', and there is no such entry in
                // 'questions:'"* with a fix reading *"or add a file
                // 'questions/is-this-ok.yaml'"* — a file open in front of the
                // author, whose creation would be a second copy of a document
                // the workspace already has, which is precisely the harm
                // `elsewhere.rs` exists to prevent, reached by a route it cannot
                // see. One mistake must get one message.
                //
                // The placeholder is an EMPTY map rather than the parsed
                // fragment: nothing is known about the document's contents, so
                // nothing about them is checked, and required-field complaints
                // about a file that did not parse would be the same pile-on in
                // another form. `unloaded` records that, so the schema knows to
                // stay quiet about what is inside.
                None => {
                    base.insert(cand.key.clone(), cand.span.clone(), unloaded(&cand.span));
                }
            }
        }

        stack.pop();
        Some(base)
    }

    /// What a self file contributes to the folder it describes.
    ///
    /// A self file's job is to supply the folder's own settings, so a set of
    /// settings is the ordinary case. The other three are all about *not
    /// inventing a field the author never typed*:
    ///
    /// - **nothing at all** — an empty file, or one holding only a comment, or
    ///   one holding only blank lines — contributes nothing. It used to be
    ///   folded into the body field, so `# TODO` in `agent.yaml` reported
    ///   *"'content' is not something an agent can have"* with the fix *"Remove
    ///   it, or use one of: name, description, …"*, beside the one true report
    ///   that the description is missing. There is no `content` line to remove,
    ///   and the author was sent to look for one in a file whose entire text is
    ///   `# TODO`. Contributing nothing leaves only the report that is true.
    ///
    ///   **Emptiness does not arrive in one shape.** An empty YAML document
    ///   arrives as nothing; an empty *markdown* document arrives as an empty
    ///   body, because prose has no "absent" form — a file of zero bytes is a
    ///   body with no words in it. Catching only the first left the second
    ///   printing that same invented `content` report: measured on the worked
    ///   example with `agents/fraud-checker/agent.yaml` renamed to `agent.md`
    ///   and emptied. So the question asked here is "did the author write a
    ///   document?", once, rather than "is this null?" once and "is this an
    ///   empty string?" never. `parse_markdown` already draws exactly this line
    ///   for the file's *other* half — a blank body under front matter
    ///   contributes no body field — and this is that rule where there is no
    ///   front matter to write it under.
    /// - **prose** — a bare `SKILL.md` body — becomes the body field, which is
    ///   the documented way to write a procedure.
    /// - **anything else** is neither settings nor prose. It is named and
    ///   pointed at rather than dropped (T7), because the author did write
    ///   something and is owed a message about what they wrote.
    fn fields_of_self_file(&self, n: Node, sf: &Candidate, diags: &mut Diagnostics) -> Node {
        if holds_no_document(&n) {
            return Node::map(Map::new(), n.span);
        }
        match n.value {
            Value::Map(m) => Node::map(m, n.span),
            Value::Str(_) => {
                let mut m = Map::new();
                m.insert(
                    self.policy.body_field.clone(),
                    Entry { key_span: n.span.clone(), node: n.clone() },
                );
                Node::map(m, n.span)
            }
            ref other => {
                let name = sf.path.file_name().unwrap_or_default().to_string();
                diags.push(Diagnostic::error(
                    "loader/self-file-not-settings",
                    n.span.clone(),
                    format!(
                        "'{name}' should be a set of settings, but it is {}.",
                        other.kind_name()
                    ),
                    format!(
                        "Write one setting per line, like `description: what this is`. \
                         '{name}' gives this folder its own settings, so everything in it \
                         needs a name in front of it."
                    ),
                ));
                Node::map(Map::new(), n.span)
            }
        }
    }

    /// Collect a payload directory's files verbatim, recursively.
    ///
    /// Filenames and extensions are preserved exactly; only dotfiles and the
    /// marker itself are skipped. Results are sorted by path so the document —
    /// and its digest — are reproducible.
    fn load_payload(&self, dir: &Utf8Path, diags: &mut Diagnostics) -> Node {
        let mut files = Vec::new();
        self.walk_payload(dir, dir, &mut files, diags, 0);
        files.sort_by(|a, b| a.path.cmp(&b.path));
        Node::new(
            Value::Payload(Payload { root: self.relative(dir), files }),
            Span::whole_file(dir),
        )
    }

    fn walk_payload(
        &self,
        root: &Utf8Path,
        dir: &Utf8Path,
        out: &mut Vec<FileRef>,
        diags: &mut Diagnostics,
        depth: usize,
    ) {
        if depth >= MAX_DIR_DEPTH {
            diags.push(Diagnostic::error(
                "loader/too-deep",
                Span::whole_file(dir),
                format!("Folders inside '{root}' are nested too deeply."),
                "Flatten the folder structure inside this attachment folder.",
            ));
            return;
        }
        let Ok(read) = std::fs::read_dir(dir) else {
            diags.push(Diagnostic::error(
                "loader/unreadable",
                Span::whole_file(dir),
                format!("Could not open folder '{dir}'."),
                "Check the folder exists and that you have permission to open it.",
            ));
            return;
        };
        for entry in read.flatten() {
            let Ok(name) = entry.file_name().into_string() else { continue };
            if name.starts_with('.') {
                continue;
            }
            let path = dir.join(&name);
            let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);
            if is_dir {
                self.walk_payload(root, &path, out, diags, depth + 1);
            } else {
                out.push(FileRef {
                    path: path
                        .strip_prefix(root)
                        .map(|p| p.as_str().replace('\\', "/"))
                        .unwrap_or_else(|_| name.clone()),
                    content_type: self.policy.content_type(&path),
                    size_bytes: entry.metadata().map(|m| m.len()).unwrap_or(0),
                });
            }
        }
    }

    /// Enumerate a directory into ordered, collision-checked candidates.
    fn classify(
        &self,
        dir: &Utf8Path,
        dir_name: &str,
        diags: &mut Diagnostics,
    ) -> (Vec<Candidate>, Option<Candidate>) {
        let read = match std::fs::read_dir(dir) {
            Ok(r) => r,
            Err(e) => {
                diags.push(Diagnostic::error(
                    "loader/unreadable",
                    Span::whole_file(dir),
                    format!("Could not open folder '{dir}': {e}"),
                    "Check the folder exists and that you have permission to open it.",
                ));
                return (Vec::new(), None);
            }
        };

        // Author-declared exclusions for this directory (FR-1.1.9). Explicit,
        // so a skipped file is a stated intent rather than a silent surprise.
        let ignore = Ignore::load(dir);

        let mut candidates: Vec<Candidate> = Vec::new();
        let mut self_file: Option<Candidate> = None;

        for entry in read.flatten() {
            let Ok(name) = entry.file_name().into_string() else { continue };
            let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);
            if self.policy.is_ignored(&name, is_dir) || ignore.matches(&name) {
                continue;
            }

            let path = dir.join(&name);
            let stem = if is_dir {
                name.as_str()
            } else {
                name.rsplit_once('.').map_or(name.as_str(), |(s, _)| s)
            };
            let (ordinal, key) = split_ordinal(stem);
            let span = Span::whole_file(&path);

            if !is_dir && self.policy.is_self_file(dir_name, key) {
                if let Some(prior) = &self_file {
                    diags.push(
                        Diagnostic::error(
                            "loader/two-self-files",
                            span,
                            format!(
                                "This folder has two files describing itself: '{}' and '{}'.",
                                prior.path.file_name().unwrap_or_default(),
                                name
                            ),
                            "Keep only one of them.",
                        )
                        .with_related(prior.span.clone(), "the other one"),
                    );
                    continue;
                }
                self_file = Some(Candidate { key: key.to_string(), ordinal, path, span });
                continue;
            }

            candidates.push(Candidate { key: key.to_string(), ordinal, path, span });
        }

        // E9 — key identity is `NFC ∘ lowercase`. Case folding alone is not
        // enough: on Linux, `café.md` written in NFC and in NFD are two
        // distinct directory entries, and macOS stores NFD, so a tree authored
        // on one platform must not silently gain or lose a field on another
        // (invariant P-5).
        let mut seen: HashMap<String, usize> = HashMap::new();
        let mut keep: Vec<usize> = Vec::with_capacity(candidates.len());
        for (i, cand) in candidates.iter().enumerate() {
            let folded = fold_key(&cand.key);
            match seen.get(&folded) {
                Some(&first) => {
                    diags.push(
                        Diagnostic::error(
                            "loader/duplicate-field",
                            cand.span.clone(),
                            format!(
                                "'{}' and '{}' would both become the setting '{}'.",
                                candidates[first].path.file_name().unwrap_or_default(),
                                cand.path.file_name().unwrap_or_default(),
                                cand.key
                            ),
                            "Rename one of them. Two files can't describe the same setting, \
                             and names that differ only by capitalisation clash on some computers.",
                        )
                        .with_related(candidates[first].span.clone(), "the other one"),
                    );
                }
                None => {
                    seen.insert(folded, i);
                    keep.push(i);
                }
            }
        }

        let mut ordered: Vec<Candidate> = keep.into_iter().map(|i| candidates[i].clone()).collect();

        // Deterministic order: ordinals first (ascending), then everything else
        // by name. Never filesystem order.
        // E4 — order is carried in-band or not at all. Two entries claiming the
        // same position is an authoring mistake with no correct answer, so it is
        // reported rather than broken by name.
        let mut by_ordinal: HashMap<u32, usize> = HashMap::new();
        for (i, c) in ordered.iter().enumerate() {
            if let Some(n) = c.ordinal
                && let Some(&first) = by_ordinal.get(&n)
            {
                diags.push(
                    Diagnostic::error(
                        "loader/duplicate-order",
                        c.span.clone(),
                        format!(
                            "'{}' and '{}' are both numbered {n}, so their order is undecided.",
                            ordered[first].path.file_name().unwrap_or_default(),
                            c.path.file_name().unwrap_or_default()
                        ),
                        "Renumber one of them. The number at the front of the filename decides \
                         what runs first.",
                    )
                    .with_related(ordered[first].span.clone(), "the other one"),
                );
            } else if let Some(n) = c.ordinal {
                by_ordinal.insert(n, i);
            }
        }

        ordered.sort_by(|a, b| match (a.ordinal, b.ordinal) {
            (Some(x), Some(y)) => x.cmp(&y).then_with(|| a.key.cmp(&b.key)),
            (Some(_), None) => std::cmp::Ordering::Less,
            (None, Some(_)) => std::cmp::Ordering::Greater,
            (None, None) => a.key.cmp(&b.key),
        });

        (ordered, self_file)
    }

    fn relative(&self, path: &Utf8Path) -> String {
        path.strip_prefix(&self.root).unwrap_or(path).as_str().replace('\\', "/")
    }
}

/// Did the author write a document in this file at all?
///
/// True for the two ways a file can parse to nothing: a YAML/JSON document that
/// is absent (an empty file, or one holding only comments), and a markdown
/// document whose whole text is whitespace. They are the same state on disk and
/// the same state to the author — a file they have not started — so they are one
/// question here rather than two arms that only one of them ever reaches.
fn holds_no_document(n: &Node) -> bool {
    match &n.value {
        Value::Null => true,
        Value::Str(s) => s.trim().is_empty(),
        _ => false,
    }
}

/// A stand-in for a file that could not be read, so that every reference to it
/// still resolves and the author is told about their one mistake once.
///
/// It carries [`pact_doc::UNLOADED`], which the schema reads as "say nothing
/// about what is inside this" — otherwise a file with an unclosed bracket would
/// also be told it is missing every required field it certainly contains.
fn unloaded(at: &Span) -> Node {
    let mut m = Map::new();
    m.insert(
        pact_doc::UNLOADED.to_string(),
        Entry { key_span: at.clone(), node: Node::str("yes", at.clone()) },
    );
    Node::map(m, at.clone())
}

/// E9 — the identity a directory entry is compared under: Unicode NFC, then
/// ASCII-insensitive case folding.
fn fold_key(key: &str) -> String {
    use unicode_normalization::UnicodeNormalization;
    key.nfc().collect::<String>().to_lowercase()
}

fn whole(path: &Utf8Path, text: &str) -> Span {
    Span::new(path, 1, 1, 0, text.len())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU32, Ordering as AtomicOrdering};

    static COUNTER: AtomicU32 = AtomicU32::new(0);

    struct Tree(Utf8PathBuf);

    impl Tree {
        fn new(name: &str) -> Self {
            let n = COUNTER.fetch_add(1, AtomicOrdering::SeqCst);
            let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
                .join(format!("pact-loader-{name}-{}-{n}", std::process::id()));
            let _ = fs::remove_dir_all(&base);
            fs::create_dir_all(&base).unwrap();
            Self(base)
        }
        fn file(&self, rel: &str, body: &str) -> &Self {
            let p = self.0.join(rel);
            fs::create_dir_all(p.parent().unwrap()).unwrap();
            fs::write(p, body).unwrap();
            self
        }
        fn dir(&self, rel: &str) -> &Self {
            fs::create_dir_all(self.0.join(rel)).unwrap();
            self
        }
        fn load(&self) -> (Option<Node>, Diagnostics) {
            let mut d = Diagnostics::new();
            let path = self.0.clone();
            let n = Loader::new(path.clone()).load(&path, &mut d);
            d.sort();
            (n, d)
        }
    }

    impl Drop for Tree {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn one_file_and_a_full_tree_produce_the_same_document() {
        // AC-1.4: the beginner's single file and the expert's tree must load
        // identically. This is the Expansion Rule's whole point.
        let flat = Tree::new("flat");
        flat.file(
            "_index.yaml",
            "name: refund-desk\ndescription: Handles refunds\ninstructions: Be kind and precise.\n",
        );

        let tree = Tree::new("tree");
        tree.file("_index.yaml", "name: refund-desk\ndescription: Handles refunds\n")
            // WITH the trailing newline, because every editor writes one and the
            // version of this fixture without it is why the divergence survived.
            .file("instructions.md", "Be kind and precise.\n");

        let (a, da) = flat.load();
        let (b, db) = tree.load();
        assert!(!da.has_errors() && !db.has_errors(), "{}{}", da.render(), db.render());

        // NOT normalised. This used to `.trim()` both sides before comparing, and
        // that is where the format's central claim went to hide: the fixture below
        // is written in Rust without a trailing newline, so the trim was a no-op
        // here and load-bearing for every real file. `pact_doc::prose` takes the
        // POSIX newline off at LOAD, which is the only place the two forms can be
        // made the same document.
        assert_eq!(
            a.unwrap().to_json(),
            b.unwrap().to_json(),
            "a field and its file form must load identically, byte for byte"
        );
    }

    #[test]
    fn a_directory_becomes_a_field_containing_its_entries() {
        let t = Tree::new("dirfield");
        t.file("_index.yaml", "name: desk\n")
            .file("agents/triage.yaml", "description: sorts tickets\n")
            .file("agents/refund.yaml", "description: issues refunds\n");

        let (node, d) = t.load();
        assert!(!d.has_errors(), "{}", d.render());
        let node = node.unwrap();
        let agents = node.get("agents").unwrap();
        assert_eq!(agents.as_map().unwrap().len(), 2);
        assert_eq!(
            agents.get("triage").unwrap().get("description").unwrap().as_str(),
            Some("sorts tickets")
        );
    }

    #[test]
    fn defining_a_field_twice_is_refused_not_resolved() {
        // T7: no silent loss. Precedence would hide a real authoring mistake.
        let t = Tree::new("ambiguous");
        t.file("_index.yaml", "name: desk\ninstructions: from yaml\n")
            .file("instructions.md", "from markdown");

        let (_, d) = t.load();
        assert!(d.has_errors());
        let e = d.items().iter().find(|x| x.rule == "loader/ambiguous-field").expect("reported");
        assert!(e.message.contains("instructions"));
        assert_eq!(e.related.len(), 1, "must point at the other definition");
    }

    #[test]
    fn ordinal_prefixes_give_stable_ordering() {
        let t = Tree::new("ordinals");
        t.file("steps/02-summarise.yaml", "do: summarise\n")
            .file("steps/01-fetch.yaml", "do: fetch\n")
            .file("steps/10-report.yaml", "do: report\n");

        let (node, d) = t.load();
        assert!(!d.has_errors(), "{}", d.render());
        let root = node.unwrap();
        let steps = root.get("steps").unwrap();
        let keys: Vec<_> = steps.as_map().unwrap().keys().map(String::as_str).collect();
        assert_eq!(keys, vec!["fetch", "summarise", "report"], "10 must sort after 2, not before");
    }

    #[test]
    fn unordered_entries_sort_by_name_not_by_filesystem() {
        let t = Tree::new("stable");
        for n in ["zulu", "alpha", "mike"] {
            t.file(&format!("tools/{n}.yaml"), "kind: mcp\n");
        }
        let (node, _) = t.load();
        let root = node.unwrap();
        let keys: Vec<_> =
            root.get("tools").unwrap().as_map().unwrap().keys().map(String::as_str).collect();
        assert_eq!(keys, vec!["alpha", "mike", "zulu"], "digests must be reproducible");
    }

    #[test]
    fn names_clashing_only_by_case_are_refused() {
        let t = Tree::new("case");
        t.file("tools/Search.yaml", "a: 1\n").file("tools/search.yaml", "b: 2\n");
        let (_, d) = t.load();
        // On a case-insensitive filesystem the second write replaces the first,
        // so only assert the rule fires where both files can coexist.
        let both_exist = fs::read_dir(t.0.join("tools")).unwrap().count() == 2;
        if both_exist {
            assert!(
                d.items().iter().any(|x| x.rule == "loader/duplicate-field"),
                "a tree authored on Linux must not break on macOS"
            );
        }
    }

    #[test]
    fn extension_does_not_change_the_field_name() {
        let t = Tree::new("ext");
        t.file("tools/search.yaml", "kind: mcp\n").file("tools/search.json", "{}");
        let (_, d) = t.load();
        assert!(d.items().iter().any(|x| x.rule == "loader/duplicate-field"));
    }

    #[test]
    fn documentation_files_are_not_loaded_as_fields() {
        let t = Tree::new("docs");
        t.file("_index.yaml", "name: desk\n")
            .file("README.md", "# Notes for humans")
            .file(".hidden.yaml", "secret: 1\n");
        let (node, d) = t.load();
        assert!(!d.has_errors(), "{}", d.render());
        let node = node.unwrap();
        assert!(node.get("README").is_none());
        assert!(node.get("hidden").is_none());
    }

    #[test]
    fn binary_payloads_become_references_never_content() {
        // D16: vision/audio are first class, but a 2 GB video must not be inlined.
        let t = Tree::new("binary");
        t.file("_index.yaml", "name: desk\n").file("logo.png", "\u{89}PNG fake bytes");
        let (node, d) = t.load();
        assert!(!d.has_errors(), "{}", d.render());
        let j = node.unwrap().to_json();
        assert_eq!(j["logo"]["contentType"], "image/png");
        assert!(j["logo"]["$file"].as_str().unwrap().ends_with("logo.png"));
    }

    #[test]
    fn a_directory_named_after_itself_supplies_its_own_fields() {
        let t = Tree::new("selfname");
        t.file("refund-desk/refund-desk.yaml", "name: refund-desk\n")
            .file("refund-desk/instructions.md", "Be precise.");
        let (node, d) = t.load();
        assert!(!d.has_errors(), "{}", d.render());
        let root = node.unwrap();
        let desk = root.get("refund-desk").unwrap();
        assert_eq!(desk.get("name").unwrap().as_str(), Some("refund-desk"));
        assert_eq!(desk.get("instructions").unwrap().as_str().unwrap().trim(), "Be precise.");
    }

    #[test]
    fn two_self_files_are_refused() {
        let t = Tree::new("twoself");
        t.dir("desk");
        t.file("desk/_index.yaml", "a: 1\n").file("desk/desk.yaml", "b: 2\n");
        let (_, d) = t.load();
        assert!(d.items().iter().any(|x| x.rule == "loader/two-self-files"));
    }

    #[test]
    fn a_bad_file_does_not_stop_the_rest_of_the_load() {
        // One mistake must not hide the others: the author should see them all.
        let t = Tree::new("resilient");
        t.file("_index.yaml", "name: desk\n")
            .file("tools/good.yaml", "kind: mcp\n")
            .file("tools/broken.yaml", "kind: [unclosed\n");
        let (node, d) = t.load();
        assert!(d.has_errors());
        let node = node.unwrap();
        assert!(node.get("tools").unwrap().get("good").is_some(), "good entries still load");
    }

    #[test]
    fn every_diagnostic_the_loader_emits_has_an_actionable_fix() {
        // O7.3, checked across several of the loader's failure paths at once.
        let t = Tree::new("fixes");
        t.file("_index.yaml", "name: desk\ninstructions: x\n")
            .file("instructions.md", "y")
            .file("tools/search.yaml", "a: 1\n")
            .file("tools/search.json", "{}")
            .file("tools/bad.yaml", "k: [\n");
        let (_, d) = t.load();
        assert!(d.error_count() >= 3, "expected several distinct problems: {}", d.render());
        for item in d.items() {
            assert!(!item.fix.trim().is_empty(), "rule {} gave no fix", item.rule);
            assert!(!item.message.trim().is_empty(), "rule {} gave no message", item.rule);
        }
    }

    #[test]
    fn a_payload_directory_keeps_filenames_and_extensions() {
        // The Expansion Rule is not universal: a sandbox workspace is a file
        // set. Turning `setup.py` into a field named `setup` would silently
        // drop the extension, which T7 forbids.
        let t = Tree::new("payload");
        t.file("_index.yaml", "name: desk\n")
            .file("workspace/setup.py", "print('hi')\n")
            .file("workspace/data/cases.csv", "a,b\n1,2\n")
            .file("workspace/notes.md", "# not a field\n");

        let (node, d) = t.load();
        assert!(!d.has_errors(), "{}", d.render());
        let j = node.unwrap().to_json();
        let ws = &j["workspace"];
        assert!(ws["$payload"].is_string(), "must be a payload, not expanded fields");
        let paths: Vec<&str> =
            ws["files"].as_array().unwrap().iter().map(|f| f["$file"].as_str().unwrap()).collect();
        assert_eq!(paths, vec!["data/cases.csv", "notes.md", "setup.py"], "sorted, verbatim");
        assert!(ws.get("setup").is_none(), "payload contents must not become fields");
    }

    #[test]
    fn any_directory_can_opt_into_payload_treatment() {
        let t = Tree::new("marker");
        t.file("_index.yaml", "name: desk\n")
            .file("fixtures/.pactpayload", "")
            .file("fixtures/golden.json", "{}")
            .file("fixtures/input.txt", "hello");

        let (node, d) = t.load();
        assert!(!d.has_errors(), "{}", d.render());
        let j = node.unwrap().to_json();
        let paths: Vec<&str> = j["fixtures"]["files"]
            .as_array()
            .unwrap()
            .iter()
            .map(|f| f["$file"].as_str().unwrap())
            .collect();
        assert_eq!(paths, vec!["golden.json", "input.txt"]);
        assert!(!paths.contains(&".pactpayload"), "the marker itself is not content");
    }

    #[test]
    fn an_ordinary_directory_is_still_expanded_into_fields() {
        // Guard against payload treatment leaking into normal structure.
        let t = Tree::new("notpayload");
        t.file("tools/search.yaml", "kind: mcp\n");
        let (node, _) = t.load();
        let root = node.unwrap();
        assert!(root.get("tools").unwrap().get("search").is_some());
    }

    #[test]
    fn two_entries_claiming_the_same_position_are_refused() {
        // E4: there is no correct way to break this tie, so it is reported.
        let t = Tree::new("ordtie");
        t.file("steps/01-fetch.yaml", "do: fetch\n").file("steps/01-verify.yaml", "do: verify\n");
        let (_, d) = t.load();
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/duplicate-order")
            .expect("a tie in ordering must be reported");
        assert!(e.message.contains("numbered 1"));
        assert_eq!(e.related.len(), 1, "must name the other file too");
    }

    #[test]
    fn unicode_forms_of_the_same_name_are_one_key() {
        // E9: macOS stores NFD, Linux stores whatever was written. Without NFC
        // folding, the same tree gains or loses a field when it changes machine.
        let t = Tree::new("nfc");
        t.file("tools/caf\u{e9}.yaml", "a: 1\n")       // café, NFC
            .file("tools/cafe\u{301}.yaml", "b: 2\n"); // café, NFD
        let (_, d) = t.load();
        let both_on_disk = fs::read_dir(t.0.join("tools")).map(|r| r.count()).unwrap_or(0) == 2;
        if both_on_disk {
            assert!(
                d.items().iter().any(|x| x.rule == "loader/duplicate-field"),
                "NFC and NFD spellings must collide: {}",
                d.render()
            );
        }
    }

    #[test]
    fn nested_directories_expand_recursively() {
        let t = Tree::new("nested");
        t.file("_index.yaml", "name: desk\n")
            .file("agents/refund/_index.yaml", "description: refunds\n")
            .file("agents/refund/instructions.md", "Refund carefully.")
            .file("agents/refund/tools/stripe.yaml", "kind: mcp\n");
        let (node, d) = t.load();
        assert!(!d.has_errors(), "{}", d.render());
        let root = node.unwrap();
        let stripe = root
            .get("agents")
            .and_then(|n| n.get("refund"))
            .and_then(|n| n.get("tools"))
            .and_then(|n| n.get("stripe"))
            .expect("deep expansion works at any depth");
        assert_eq!(stripe.get("kind").unwrap().as_str(), Some("mcp"));
    }
}
