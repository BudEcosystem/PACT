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
//! # What is deliberately a warning
//!
//! An entry the loader will not read, but whose absence does not make the rest
//! of the tree wrong, is a warning naming the entry rather than a refusal.
//! There are four, and they are listed here because this repository has no
//! rule catalogue and an embedder reading only the source would otherwise find
//! them one crash report at a time:
//!
//! - `loader/symlink-skipped` — a shortcut, wherever in the tree it is found
//!   (see [`symlink_skipped`]);
//! - `loader/not-a-regular-file` — an entry that is neither an ordinary file
//!   nor a folder: a named pipe, a unix socket, a device node, or (with
//!   `follow_symlinks: true`) a shortcut whose target is a folder. Wherever in
//!   the tree it is found, the same as the rule above. See
//!   [`not_a_regular_file`];
//! - `loader/folder-skipped-by-name` — a folder whose name is one build and
//!   packaging tools fill in themselves AND one an author could have meant
//!   (`build`, `dist`, `target`). A folder no author ever names —
//!   `node_modules`, `__pycache__`, `venv` — is skipped in silence, because
//!   there can be nothing of theirs behind it and the line could only ever be
//!   noise. See [`policy::TOOL_ONLY_DIRS`] for what the noise measured.
//! - `loader/file-skipped-by-name` — a file whose name reads as writing about
//!   the project but which is not where writing about the project lives:
//!   `tools/license.yaml` (a documentation stem in the form settings are
//!   written in, at any depth) or `agents/keeper/notice.md` (the same stem as
//!   prose, anywhere below the top of the workspace). At the TOP, `README.md`
//!   and its siblings are documentation and are skipped in silence.
//!
//! Both name-collision rules are what a `.pactignore` line silences, and both
//! now say so in their `fix:` — the file rule's did not, while this paragraph
//! claimed it did. Neither is reachable from [`Loader::walk_payload`]: an
//! attachment folder carries its contents by name, so nothing there is skipped
//! for looking like a build folder or like documentation, and there is nothing
//! to report. `.pactignore` is read in both places and INHERITED down the tree
//! in both, so the escape hatch works wherever an entry sits — including on
//! the two rules an attachment folder *can* raise,
//! `loader/symlink-skipped` and `loader/not-a-regular-file`.
//!
//! # What is deliberately a note
//!
//! - `loader/ignored-on-purpose` — an entry a `.pactignore` line removed,
//!   naming the entry, the line and the file the line was written in.
//!
//! A note rather than a warning because the author asked for it and
//! `--deny-warnings` counts warnings; reported at all because it is a
//! **deletion**, and EXP-10 (`docs/20-ARCHITECTURE-R5.md`), EXP-11 and FR-8.1.1
//! (`docs/30-FRD.md`) all require that no lossy operation proceed in silence.
//! EXP-10 asks for it as a `LoadReport` line; [`report::LoadReport`] cannot yet
//! carry one (LOAD-14 reserves the slot), so the record is a diagnostic, and
//! the two other halves of EXP-10 — `.pactignore` as a typed IR node in
//! `canonical.json`, and inside `workspace-digest` — are **still unmet**. That
//! is the honest state: the suppression is now visible, and it is not yet
//! governed.
//!
//! **And it now reaches further than it did.** Giving
//! [`Loader::walk_payload`] the escape hatch it needed for
//! `loader/symlink-skipped` also made `.pactignore` able to remove ORDINARY
//! CONTENT from an attachment folder — a knowledge corpus's `documents/`, a
//! skill's `scripts/` — which it could not do before. Measured on
//! `examples/answers-from-documents` with one line `leave.md` in
//! `knowledge/staff-handbook/documents/.pactignore`: `pact check
//! --deny-warnings` printed the note, said *"loaded cleanly (21 settings)"* and
//! exited 0, while `pact discover` moved the workspace digest from
//! `sha256:17393f6f…` to `sha256:bf3b29ab…`. That is EXP-10's shape exactly —
//! a deletion the blast-radius classifier cannot see — now with a wider reach,
//! and BET H12's requirement that a change class be invariant under
//! typed↔payload reclassification is what the unmet `canonical.json` and
//! `workspace-digest` halves above would have to satisfy. The suppression is
//! spoken (`a_pactignore_line_takes_an_ordinary_file_out_of_an_attachment_folder_and_says_so`
//! holds the note); it is still not governed. `docs/remediation/C7-bundle-mounting.md`
//! cites this pass as a containment guarantee and inherits the same limit.
//!
//! # Where a skipped entry is still not heard
//!
//! `pact check` and `pact waits` render every diagnostic. `pact show`,
//! `pact discover` and `pact card` render them only when the load has ERRORS
//! (`crates/pact-cli/src/main.rs`), so a warning about a skipped folder reaches
//! stdout through none of the three. `discover` is the one that matters:
//! `gaia-ai-runtime` indexes its inventory, and a human reading `show` might
//! notice an agent missing where a program cannot. All three now print
//! warnings and notes to **stderr**, leaving stdout the machine-readable JSON
//! it was.
//!
//! What is still not done is putting the skipped entry in the DOCUMENT for a
//! skipped FOLDER. A [`pact_doc::UNLOADED`] marker there turns the warning into
//! `error: 'dist' is not something a workspace can have` for every repository
//! that keeps its build output beside its workspace — measured, and strictly
//! worse than the silence it replaces. For a skipped FILE below the top of the
//! workspace the same marker is right and is used: see the
//! `SettingsNamedLikeDocumentation` arm of [`Loader::classify`].
//!
//! # Ordering
//!
//! Filesystem read order is not stable across platforms, so it is never used.
//! Entries sort by ordinal prefix first (`01-fetch.yaml` before
//! `02-summarise.yaml`), then by name. The resulting document — and therefore
//! its digest — is reproducible on any machine.

pub mod approvals;
pub mod bindings;
pub mod available;
pub mod bundles;
pub mod callable;
pub mod conditions;
pub mod currency;
pub mod derive;
pub mod firstfile;
pub mod handover;
pub mod holes;
pub mod kindfiles;
pub mod money;
pub mod policy;
pub mod ports;
pub mod clauses;
pub mod programs;
pub mod reach;
pub mod reachability;
pub mod redaction;
pub mod report;
pub mod schedules;
pub mod review;
pub mod teams;
pub mod teamwork;
pub mod templates;
pub mod unnamed;
pub mod values;
pub mod workflows;

use camino::{Utf8Path, Utf8PathBuf};
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Entry, FileRef, Map, Node, Payload, Value, parse_markdown, parse_yaml};
use policy::{FileKind, Ignore, Ignored, Policy, split_ordinal};
use std::collections::HashMap;

/// Maximum directory nesting. Far above any real spec tree; exists so a
/// symlink loop or a pathological tree fails fast with a clear message.
const MAX_DIR_DEPTH: usize = 32;

/// What a whole load may add up to, across every file in the tree.
///
/// `pact_doc::yaml` bounds **one document**, and for a round that was read as
/// bounding the loader. It is not the same claim, and the difference is a
/// folder: four hundred agent files of 277 bytes each — every one of them well
/// inside `MAX_NODES`, 110,817 bytes on disk in total — took `pact check` and
/// `pact discover` alike to 2,998,240 KB resident and then to `memory
/// allocation of 1 bytes failed`, signal 6, EXIT=134 under `ulimit -v
/// 3000000`. Both budgets reset in `Builder::new`, so nothing counted the
/// second file against the first, and `gaia-ai-runtime` is specified to
/// discover and load trees it did not write.
///
/// Charged **after** each file is loaded rather than before, because what a
/// file costs is not known until it is read. That leaves the load at most one
/// file over the line, which is why the per-file budgets have to stay: they are
/// what makes "one file" a bounded amount.
///
/// The figures are measured, not chosen. On this machine `pact check` costs
/// ~320 bytes of peak resident memory per setting — 400 files × 500 settings
/// (~200,000) peaked at 72,128 KB, ~1,000,000 at 322,236 KB and ~2,000,000 at
/// 638,728 KB — and ~3.2 bytes per byte of writing, 50 MB of prose peaking at
/// 159,920 KB. So the pair below is a ceiling around 500 MB, five times the
/// per-file settings budget and sixteen times the per-file writing budget.
///
/// **Both are capability-affecting literals in the Rust core, which F-1 and
/// FR-8.1.3 forbid, and both are filed DELIBERATE_AND_CLOSED**: an author who
/// raised them would be buying back the abort above, which is not a capability
/// anybody wants. See `docs/remediation/A3-yaml-alias-bomb.md` §7 and
/// `docs/remediation/C8-profiles.md` D-4.
const MAX_LOAD_SETTINGS: usize = 1_000_000;
const MAX_LOAD_TEXT: usize = 64 * 1024 * 1024;
/// The same figure in the unit the author's file manager shows them.
const MAX_LOAD_TEXT_MB: usize = MAX_LOAD_TEXT / (1024 * 1024);

pub struct Loader {
    root: Utf8PathBuf,
    policy: Policy,
    /// Settings and writing this load has taken in so far, and whether it has
    /// already said it will take no more. `Cell` rather than `&mut self`
    /// because the walk is recursive, single-threaded, and hands `&self` down
    /// through five call sites that have nothing to do with counting.
    loaded_settings: std::cell::Cell<usize>,
    loaded_text: std::cell::Cell<usize>,
    /// Payload bytes read to fingerprint them, across the whole load. See
    /// [`charged`].
    fingerprinted: std::cell::Cell<u64>,
    stopped: std::cell::Cell<bool>,
}

/// Which of the two jobs a file is being read for.
///
/// It matters for exactly one thing, and only for markdown: a file whose front
/// matter is not a set of settings. A field file still holds the text its slot
/// asked for; a self file was supposed to supply settings and supplied none. See
/// the `FileKind::Prose` arm of [`Loader::read_file`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Position {
    /// A file whose name is a FIELD of the folder above it —
    /// `agents/desk/instructions.md` is that agent's `instructions`.
    Field,
    /// The file that gives its own folder its settings — `agent.md`,
    /// `SKILL.md`, `workspace.yaml`.
    SelfFile,
}

/// One classified directory entry, before loading.
#[derive(Clone)]
struct Candidate {
    key: String,
    ordinal: Option<u32>,
    path: Utf8PathBuf,
    /// Span identifying the file itself, for diagnostics about the *name*.
    span: Span,
    /// Contribute the NAME and nothing else — [`unloaded`], without opening the
    /// file. CHK-12's mechanism, reached by the other route that ends in a file
    /// whose contents the loader will not read: see the
    /// [`Ignored::SettingsNamedLikeDocumentation`](policy::Ignored::SettingsNamedLikeDocumentation)
    /// arm of [`Loader::classify`].
    name_only: bool,
}


/// A file's contents, as a fingerprint and never as content.
///
/// EXP-8 asks for this and it was not built, so a body could be swapped for
/// another body of the same length and nothing in the document moved — which
/// makes signing a tree a statement about its filenames rather than about what
/// is in them. It matters more the moment a body is something a runtime will
/// execute.
///
/// Read in fixed-size chunks rather than into a `String`, for two reasons: a
/// payload is arbitrary bytes and need not be UTF-8 at all, and a large asset
/// must not be held in memory to be described. A file that cannot be read
/// carries an EMPTY fingerprint rather than a guess — the walk already reports
/// unreadable entries, and a made-up digest would be worse than none, because
/// the whole value of the field is that it can be compared.
/// The most of one payload file this reader will read to describe it.
///
/// Fingerprinting a payload was free when the walk only asked the filesystem for
/// each entry's size: the cost was the NUMBER of files. Reading every byte made
/// it the SIZE of them, and nothing bounded it — `MAX_LOAD_TEXT` is charged from
/// `load_file`, and neither fingerprint call passes through there. A tree can
/// state a size independently of what it occupies, so a 48 KiB directory could
/// cost a reviewer minutes. Measured on `examples/answers-from-documents` with
/// one sparse file planted in it, release build: 0.006 s before, 1.05 s at 512
/// MB, 8.65 s at 4 GiB, the tree 48 KiB on disk throughout.
///
/// The same figure as `MAX_LOAD_TEXT`, and deliberately: a payload file is the
/// one thing this loader reads that is not held in memory afterwards, so the
/// ceiling is about the reader's TIME rather than their memory — but two limits
/// where one will do is two numbers to explain, and this one is already the
/// answer to "how much of somebody else's file will PACT read".
const MAX_FINGERPRINT_BYTES: u64 = MAX_LOAD_TEXT as u64;

/// Whether this file is small enough to describe by its contents.
///
/// Split out from [`fingerprint`] so the two call sites can say the same
/// sentence about the file they skipped, from the size they already had in hand.
fn too_big_to_fingerprint(size: u64) -> bool {
    size > MAX_FINGERPRINT_BYTES
}

/// Whether everything read so far, plus this, is more than the ceiling.
///
/// The per-file test above was the whole of it for a round, and the budget it
/// says it mirrors is a RUNNING TOTAL: `loaded_text` accumulates across the load
/// and `MAX_LOAD_TEXT` is compared against the sum. So a thousand files of 64 MB
/// each was 64 GB of reading with nothing to stop it — the same hole the per-file
/// ceiling was written to close, one level up from where it was closed.
fn charged(spent: &std::cell::Cell<u64>, size: u64) -> bool {
    let after = spent.get().saturating_add(size);
    spent.set(after);
    after > MAX_FINGERPRINT_BYTES
}

/// A file described by name and size, because reading it is not worth a
/// reviewer's afternoon.
fn too_big_to_describe(path: &Utf8Path, size: u64, alone: bool) -> Diagnostic {
    let why = if alone {
        format!(
            "it is {} MB on its own, which is more than the {MAX_LOAD_TEXT_MB} MB this \
             reader will spend on one file",
            size / (1024 * 1024)
        )
    } else {
        format!(
            "everything read to describe this tree already adds up to the \
             {MAX_LOAD_TEXT_MB} MB this reader will spend on one"
        )
    };
    Diagnostic::warning(
        "loader/too-big-to-fingerprint",
        Span::whole_file(path),
        format!("'{path}' is carried by name and size with no fingerprint, because {why}."),
        "Nothing is wrong with the tree; it just cannot be pinned by content. Split \
         the file, or keep it somewhere a `url:` points at, if two copies of this \
         workspace have to be provably the same."
            .to_string(),
    )
}

fn fingerprint(path: &Utf8Path) -> String {
    use sha2::{Digest, Sha256};
    let Ok(file) = std::fs::File::open(path) else { return String::new() };
    let mut reader = std::io::BufReader::new(file);
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 64 * 1024];
    loop {
        match std::io::Read::read(&mut reader, &mut buf) {
            Ok(0) => break,
            Ok(n) => hasher.update(&buf[..n]),
            Err(_) => return String::new(),
        }
    }
    format!("{:x}", hasher.finalize())
}

impl Loader {
    pub fn new(root: impl Into<Utf8PathBuf>) -> Self {
        Self::with_policy(root, Policy::default())
    }

    pub fn with_policy(root: impl Into<Utf8PathBuf>, policy: Policy) -> Self {
        Self {
            root: root.into(),
            policy,
            loaded_settings: std::cell::Cell::new(0),
            loaded_text: std::cell::Cell::new(0),
            fingerprinted: std::cell::Cell::new(0),
            stopped: std::cell::Cell::new(false),
        }
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
        // One `Loader` is one load's worth of budget, whichever way it is
        // reached — a second `load()` on the same loader starts again rather
        // than inheriting a total nobody asked it to carry.
        self.loaded_settings.set(0);
        self.loaded_text.set(0);
        self.stopped.set(false);
        let mut stack = Vec::new();
        self.load_path(path, diags, &mut stack)
    }

    /// Charge one loaded file against the budget for the whole load.
    ///
    /// `false` means the load is over and has said so — **once**. Everything
    /// after it is refused in silence rather than repeating the same sentence
    /// for the remaining files, which on the reproduction that found this would
    /// have been 386 copies of it. One mistake gets one message; the entries
    /// that follow become the `unloaded` placeholder every unreadable file
    /// already becomes, which is what stops the schema inventing complaints
    /// about documents nobody read.
    fn affordable(&self, node: &Node, path: &Utf8Path, diags: &mut Diagnostics) -> bool {
        self.loaded_settings
            .set(self.loaded_settings.get().saturating_add(node.node_count()));
        self.loaded_text
            .set(self.loaded_text.get().saturating_add(node.text_bytes()));

        let over = if self.loaded_settings.get() > MAX_LOAD_SETTINGS {
            Some((
                format!(
                    "Everything loaded so far adds up to more than {MAX_LOAD_SETTINGS} settings, \
                     and '{path}' takes it over."
                ),
                "Split this into several smaller folders and check them one at a time, or \
                 remove what is not needed. A folder this big usually has something in it \
                 by mistake."
                    .to_string(),
            ))
        } else if self.loaded_text.get() > MAX_LOAD_TEXT {
            Some((
                format!(
                    "Everything loaded so far adds up to more than {MAX_LOAD_TEXT_MB} MB of \
                     writing, and '{path}' takes it over."
                ),
                "Split this into several smaller folders and check them one at a time, or \
                 keep the long pieces of writing somewhere outside this folder."
                    .to_string(),
            ))
        } else {
            None
        };

        match over {
            None => true,
            Some((message, fix)) => {
                self.stopped.set(true);
                diags.push(Diagnostic::error(
                    "loader/too-much-to-load",
                    Span::whole_file(path),
                    message,
                    fix,
                ));
                false
            }
        }
    }

    fn load_path(
        &self,
        path: &Utf8Path,
        diags: &mut Diagnostics,
        stack: &mut Vec<Utf8PathBuf>,
    ) -> Option<Node> {
        if self.stopped.get() {
            return None;
        }
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
            diags.push(symlink_skipped(path));
            return None;
        }

        // `symlink_metadata` answered about the LINK, so with following on it
        // has just said `is_dir() == false` about a link to a folder and
        // `is_file() == false` about a link to a file. Ask again, of what the
        // link names, so the three-way question below is asked of the thing
        // that will actually be opened.
        let meta = if meta.file_type().is_symlink() {
            match std::fs::metadata(path) {
                Ok(m) => m,
                Err(e) => {
                    diags.push(Diagnostic::error(
                        "loader/unreadable",
                        Span::whole_file(path),
                        format!("Could not read '{path}': {e}"),
                        "Check the name is spelled correctly and that you have permission \
                         to read it.",
                    ));
                    return None;
                }
            }
        } else {
            meta
        };

        // The third question, asked here for the same reason
        // [`Loader::walk_payload`] asks it: "not a directory" is not the same
        // claim as "a file". `mkfifo agents/keeper.yaml` sent `pact check`
        // into `read_to_string` on a pipe nothing would ever write to —
        // measured, `timeout 20 pact check ws` returned EXIT=124 with no
        // output at all, the whole checker stopped by one entry in a folder it
        // was handed. A warning and the name, which is what every other entry
        // the loader will not read already gets.
        if meta.is_dir() {
            self.load_dir(path, diags, stack)
        } else if meta.is_file() {
            self.load_file(path, Position::Field, diags)
        } else {
            diags.push(not_a_regular_file(path, false, false));
            None
        }
    }

    /// Read one file, and charge what it turned out to hold against the load.
    ///
    /// Every kind goes through here — settings, prose and plain text alike —
    /// because all three are held in memory for the life of the load and the
    /// budget is about memory, not about YAML.
    ///
    /// An attachment folder does not pass through here, and it used to be
    /// because it "carries file *names*, never contents" — true when that was
    /// written and false from the day payload digests landed, which read every
    /// byte of every payload file to describe it. It has its own ceiling now:
    /// see [`MAX_FINGERPRINT_BYTES`], which bounds the reader's time the way this
    /// budget bounds their memory.
    fn load_file(
        &self,
        path: &Utf8Path,
        position: Position,
        diags: &mut Diagnostics,
    ) -> Option<Node> {
        if self.stopped.get() {
            return None;
        }
        let node = self.read_file(path, position, diags)?;
        if !self.affordable(&node, path, diags) {
            return None;
        }
        Some(node)
    }

    fn read_file(
        &self,
        path: &Utf8Path,
        position: Position,
        diags: &mut Diagnostics,
    ) -> Option<Node> {
        let kind = self.policy.file_kind(path);
        let size = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);

        if kind == FileKind::Opaque {
            // This arm returns BEFORE the `max_text_bytes` guard below, so it was
            // the second way past every byte budget the loader has.
            let digest = if too_big_to_fingerprint(size)
                || charged(&self.fingerprinted, size)
            {
                diags.push(too_big_to_describe(path, size, too_big_to_fingerprint(size)));
                String::new()
            } else {
                fingerprint(path)
            };
            return Some(Node::new(
                Value::File(FileRef {
                    path: self.relative(path),
                    content_type: self.policy.content_type(path),
                    size_bytes: size,
                    digest,
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
        let text = text
            .strip_prefix('\u{feff}')
            .map(str::to_string)
            .unwrap_or(text);
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
                    let folded = md.into_node(&self.policy.body_field);
                    if let Some(w) = folded.report {
                        diags.push(w);
                    }
                    // Front matter that is not settings is refused, and what
                    // that costs depends on where the file sits.
                    //
                    // In a FIELD slot the prose is handed on: `instructions.md`
                    // was asked for text and text is what it holds, so the
                    // author's sentence reaches the document and the one report
                    // is about the fence they wrote.
                    //
                    // A SELF FILE was asked for this folder's SETTINGS and
                    // supplied none, so it is the case two arms down in
                    // `load_dir` — a self file nobody could read — and gets the
                    // same answer: a placeholder, so the schema says nothing
                    // about a document that did not come out. Folding the prose
                    // in instead put it under `content`, and the author of
                    // `agents/desk/agent.md` was then told *"'content' is not
                    // something an agent can have — fix: Remove it"* about a
                    // word they never typed, beside the report about the fence
                    // they did. Measured: four errors for one mistake, which is
                    // CHK-12 exactly backwards.
                    if folded.front_matter_refused && position == Position::SelfFile {
                        return None;
                    }
                    Some(folded.node)
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
            Some(sf) => match self.load_file(&sf.path, Position::SelfFile, diags) {
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

            // A skipped-by-name file contributes its NAME and nothing else, the
            // way an unreadable one does. It is not opened: the whole point of
            // skipping it is that the loader will not read it.
            if cand.name_only {
                base.insert(cand.key.clone(), cand.span.clone(), unloaded(&cand.span));
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
                    Entry {
                        key_span: n.span.clone(),
                        node: n.clone(),
                    },
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
    /// Filenames and extensions are preserved exactly. Four things are left
    /// out: anything a `.pactignore` covering it names, dotfiles (which
    /// includes the marker itself), shortcuts — see [`symlink_skipped`] — and
    /// anything that is neither a folder nor an ordinary file, see
    /// [`not_a_regular_file`]. Results are sorted by path so the document —
    /// and its digest — are reproducible.
    fn load_payload(&self, dir: &Utf8Path, diags: &mut Diagnostics) -> Node {
        let mut files = Vec::new();
        self.walk_payload(dir, dir, &mut files, diags, 0);
        files.sort_by(|a, b| a.path.cmp(&b.path));
        Node::new(
            Value::Payload(Payload {
                root: self.relative(dir),
                files,
            }),
            Span::whole_file(dir),
        )
    }

    /// Say which `.pactignore` files were found and not read.
    ///
    /// [`Ignore::load`] refuses to open anything that is not a regular file, and
    /// the reason it cannot say so itself is that it has no diagnostics to say it
    /// into. Said HERE, in the same words the two walks already use for a file of
    /// the wrong shape anywhere else, so an author who wrote one and wonders why
    /// nothing is ignored is told rather than left to work it out.
    ///
    /// Once per file, however many walks find it.
    ///
    /// The ignore list is INHERITED, so every directory from the root down asks
    /// for the same `.pactignore` and a skipped one is found again at each level,
    /// by both walks. The first version of this said `Diagnostics` folds
    /// identical entries; it does not. Measured on a six-directory tree: NINE
    /// copies of one sentence about one file — one thing to fix, rendered as a
    /// wall, on a diagnostic whose whole job is to be noticed.
    ///
    /// Deduplicated against what has already been said rather than by threading a
    /// seen-set through two unrelated walks: the list is short, the comparison is
    /// the file's own span, and a check that reads the report it is writing
    /// cannot fall out of step with it.
    fn say_which_ignore_files_were_skipped(&self, ignore: &Ignore, diags: &mut Diagnostics) {
        for at in ignore.skipped() {
            if diags
                .items()
                .iter()
                .any(|d| d.rule == "loader/not-a-regular-file" && d.span.file == *at)
            {
                continue;
            }
            let link = std::fs::symlink_metadata(at).map(|m| m.file_type().is_symlink());
            diags.push(not_a_regular_file(at, link.unwrap_or(false), false));
        }
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

        // The same author-declared exclusions [`Loader::classify`] reads, in the
        // same order: asked FIRST, answering on its own.
        //
        // Without this an attachment folder had no escape hatch at all. A
        // `.pactignore` line silences a skip at the top of an ordinary folder,
        // so an author who moved the same entry into `scripts/` found the
        // warning below unsuppressable and `--deny-warnings` unpassable — the
        // asymmetry this whole function was being repaired for, in its other
        // half. Measured on the worked example: `scripts/handy.md` with
        // `handy.md` in `scripts/.pactignore` still warned, while the identical
        // pair one folder up loaded cleanly.
        //
        // INHERITED, for the reason given at the same line in
        // [`Loader::classify`]: a `.pactignore` that governed only the folder
        // it sits in is not the file every author has already met. Per-directory
        // (`Ignore::load(dir)`) re-creates the very asymmetry above one folder
        // up — measured, with one line `leak.yaml` in the workspace root's
        // `.pactignore` and the same link in `agents/` and in
        // `skills/refund-policy/scripts/`: the ordinary one answered
        // `loader/ignored-on-purpose`, the payload one still answered
        // `loader/symlink-skipped` and `--deny-warnings` still exited 1.
        // `a_pactignore_line_written_at_the_workspace_root_reaches_down_into_an_attachment_folder`
        // is what holds this; a fixture writing the line BESIDE the entry
        // passes under either implementation, which is why nothing noticed.
        let ignore = Ignore::inherited(&self.root, dir);
        self.say_which_ignore_files_were_skipped(&ignore, diags);

        for entry in read.flatten() {
            let Ok(name) = entry.file_name().into_string() else {
                continue;
            };
            let path = dir.join(&name);

            // Asked FIRST, and answering on its own — the order
            // [`Loader::classify`] asks these two in, so that the same pair of
            // files one folder apart produces the same record. When the dotfile
            // skip ran first, a root `.pactignore` line saying `.env` produced
            // the EXP-10 deletion note for `agents/keeper/.env` and nothing at
            // all for `skills/refund-policy/scripts/.env`: same pattern, same
            // workspace, one folder apart, one of the two silent.
            if let Some(pattern) = ignore.matching(&name) {
                diags.push(Diagnostic::note(
                    "loader/ignored-on-purpose",
                    Span::whole_file(&path),
                    format!(
                        "'{path}' takes no part in this workspace, because '{}' \
                         has a line saying '{}'.",
                        self.relative(&pattern.from),
                        pattern.text
                    ),
                    format!(
                        "Nothing to do — that line is what leaves it out. To bring it \
                         back, take '{}' out of '{}'.",
                        pattern.text,
                        self.relative(&pattern.from)
                    ),
                ));
                continue;
            }

            // Dotfiles, which is what `Policy::is_ignored` answers first for an
            // ordinary folder — including the `.pactpayload` marker and the
            // `.pactignore` read above. In silence, there too: every real tree
            // has some, none of them was ever content.
            if name.starts_with('.') {
                continue;
            }

            // What this entry IS, asked of the ENTRY rather than of anything it
            // points at. Three questions, in this order: is it a shortcut, is it
            // a folder, is it an ordinary file. Every one of the three has to be
            // asked; the first two alone let a FIFO through.
            let Ok(file_type) = entry.file_type() else {
                diags.push(unreadable_entry(&path));
                continue;
            };

            // The refusal `load_path` makes at :329, made here too.
            //
            // This walk carries its folder VERBATIM, so a shortcut here put a
            // path, a content type and a size for a file outside the workspace
            // straight into the document and its digest — and said nothing,
            // because the ordinary-folder rule was written in only one place.
            // Measured on the worked example with `leak.txt -> /etc/hostname`
            // in `skills/refund-policy/scripts/`: `pact check --deny-warnings`
            // answered *"OK — ws loaded cleanly (498 settings)"* while
            // `pact show` listed `/etc/hostname` by size. The same link one
            // folder up was refused. A skill's `scripts/` and a knowledge
            // corpus's `documents/` are exactly where a link would be planted.
            //
            // `DirEntry::file_type` does not follow, so this sees the LINK
            // rather than what it points at — the same question
            // `symlink_metadata` asks at :316.
            let is_link = file_type.is_symlink();
            if is_link && !self.policy.follow_symlinks {
                diags.push(symlink_skipped(&path));
                continue;
            }

            // Asked of the ENTRY, never of a link's target, so this walk
            // descends only into real directories — which cannot contain
            // themselves, so it always finishes.
            //
            // Resolving the target here instead reads better and hangs: with
            // following on, two shortcuts in one attachment folder both naming
            // their own folder (`a -> .`, `b -> .`) make the walk enumerate
            // 2^32 paths. `MAX_DIR_DEPTH` bounds depth, not breadth, and the
            // `loader/cycle` guard belongs to [`Loader::load_dir`] and its
            // ancestor stack — this walk has neither. Measured: the tree above
            // never returned, and terminated in under a millisecond as soon as
            // the question was asked of the entry again. A followed link to a
            // FOLDER is therefore not walked into — and it is not carried as a
            // file either, see below.
            if file_type.is_dir() {
                self.walk_payload(root, &path, out, diags, depth + 1);
                continue;
            }

            // The third question, and the one two rounds of this fix forgot to
            // ask. Everything that was not a directory used to be pushed as a
            // `FileRef`, so a FIFO or a unix socket dropped into `scripts/`
            // entered the document — and the workspace digest — as a plausible
            // zero-byte sibling of the real script, with no diagnostic, under
            // default policy, from the shipped binary. Measured on the worked
            // example with `mkfifo skills/refund-policy/scripts/pipe.py`:
            // `pact check --deny-warnings` answered *"OK — ws loaded cleanly
            // (498 settings)"*, EXIT=0, while `pact show` listed `pipe.py`
            // beside the real `check_window.py` at `"sizeBytes": 0`, and the
            // two workspaces' digests differed. A runtime that opens it blocks
            // for ever.
            //
            // `metadata` rather than `entry.metadata` on the followed-link
            // path, because neither `DirEntry::file_type` nor
            // `DirEntry::metadata` traverses: a followed link asked the wrong
            // one is sized as the length of the PATH it holds (34 bytes for
            // `../../../elsewhere/tools/helper.py`) rather than of the 83-byte
            // file it names, and a followed link to a FOLDER answers
            // `is_dir() == false` and was carried as a 12,288-byte
            // `application/octet-stream` "file" nothing can open.
            let target = if is_link {
                std::fs::metadata(&path)
            } else {
                entry.metadata()
            };
            let size_bytes = match target {
                Ok(m) if m.is_file() => m.len(),
                // A folder reached through a link, a FIFO, a socket, a device.
                Ok(m) => {
                    diags.push(not_a_regular_file(&path, is_link, m.is_dir()));
                    continue;
                }
                // With following on, a link with nothing on the other end. The
                // size used to become a zero and the entry was carried anyway,
                // where the identical link one folder up raised
                // `loader/unreadable`. It raises it here now too.
                Err(_) => {
                    diags.push(unreadable_entry(&path));
                    continue;
                }
            };

            // The size was already in hand from `metadata` on the line above,
            // and went unused: a file that says it is 8 GiB was read to the end
            // to be described.
            let digest = if too_big_to_fingerprint(size_bytes)
                || charged(&self.fingerprinted, size_bytes)
            {
                diags.push(too_big_to_describe(
                    &path, size_bytes, too_big_to_fingerprint(size_bytes),
                ));
                String::new()
            } else {
                fingerprint(&path)
            };
            out.push(FileRef {
                path: path
                    .strip_prefix(root)
                    .map(|p| p.as_str().replace('\\', "/"))
                    .unwrap_or_else(|_| name.clone()),
                content_type: self.policy.content_type(&path),
                size_bytes,
                digest,
            });
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

        // Author-declared exclusions covering this directory (FR-1.1.9).
        // Explicit, so a skipped file is a stated intent rather than a silent
        // surprise — and INHERITED, because a `.pactignore` that governs only
        // the folder it sits in is not the file every author has already met.
        // See [`Ignore::inherited`] for the measurement.
        let ignore = Ignore::inherited(&self.root, dir);
        self.say_which_ignore_files_were_skipped(&ignore, diags);

        // Is this the top of the tree being loaded? Only `README.md` and its
        // siblings care — see [`policy::Ignored::DocumentationInsideTheTree`].
        // Compared with any trailing slash taken off, because the repository's
        // own gate loop passes `examples/patterns/*/` and a workspace whose
        // root is written with a slash is the same workspace.
        let at_root = dir.as_str().trim_end_matches('/') == self.root.as_str().trim_end_matches('/');

        let mut candidates: Vec<Candidate> = Vec::new();
        let mut self_file: Option<Candidate> = None;

        for entry in read.flatten() {
            let Ok(name) = entry.file_name().into_string() else {
                continue;
            };
            let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);

            let path = dir.join(&name);

            // `.pactignore` is asked FIRST, and answers on its own. Asking it
            // first is what makes it the way to SILENCE the warning below
            // rather than a second way to earn one alongside it.
            //
            // It does not answer in SILENCE. A pattern the author wrote is a
            // stated intent, but it is still a deletion, and for a release it
            // was the loader's one remaining unreported one: a two-line
            // `agents/.pactignore` took a whole agent out of the document at
            // exit 0 with `pact check` printing *"loaded cleanly"* and
            // `pact show` printing a tree the agent is simply not in. EXP-10
            // (`docs/20-ARCHITECTURE-R5.md`) names that verbatim as "a deletion
            // operator the blast-radius classifier cannot see" and requires
            // that "every entry it suppresses produces a LoadReport line naming
            // the entry and the pattern"; EXP-11 and FR-8.1.1 say the same
            // thing about every lossy operation there is.
            //
            // A NOTE rather than a warning, because the author asked for this
            // and `--deny-warnings` counts warnings: the record has to be
            // visible without turning an intended suppression into a gate
            // failure. It names the pattern and the file the pattern was
            // written in, which with an inherited `.pactignore` is not the
            // folder the entry sits in. See `report.rs` LOAD-14 for where this
            // belongs once `LoadReport` can carry more than waits.
            if let Some(pattern) = ignore.matching(&name) {
                diags.push(Diagnostic::note(
                    "loader/ignored-on-purpose",
                    Span::whole_file(&path),
                    format!(
                        "'{path}' takes no part in this workspace, because '{}' \
                         has a line saying '{}'.",
                        self.relative(&pattern.from),
                        pattern.text
                    ),
                    format!(
                        "Nothing to do — that line is what leaves it out. To bring it \
                         back, take '{}' out of '{}'.",
                        pattern.text,
                        self.relative(&pattern.from)
                    ),
                ));
                continue;
            }

            if let Some(reason) = self.policy.is_ignored(&name, is_dir, at_root) {
                // Three of the five reasons are skipped without a word: a
                // dotfile, a folder only a tool ever makes, and the project's
                // own writing at the top of the workspace. Every real tree has
                // some of each, none of them was ever a setting, and a line
                // about each on every run is noise that teaches an author to
                // stop reading the output.
                //
                // The other two are NAME COLLISIONS rather than documents.
                // `build`, `dist`, `target` and `license` are ordinary English
                // words, so an author naming an agent after the work it does
                // lost the whole agent here and was told the load was clean.
                //
                // The path is the JOINED one in the sentence as well as in the
                // span: `'{dir}/{name}'` printed `…/ws//dist` when the workspace
                // was given with a trailing slash — which is how this repo's own
                // gate loop passes `examples/patterns/*/` — so the message and
                // the arrow under it disagreed about the name of the folder.
                match reason {
                    Ignored::ToolingFolder => diags.push(Diagnostic::warning(
                        "loader/folder-skipped-by-name",
                        Span::whole_file(&path),
                        format!(
                            "'{path}' was skipped, because folders called '{name}' \
                             normally hold files a tool wrote rather than anything you did."
                        ),
                        format!(
                            "If this folder is part of what you are building, rename it to \
                             something else. If you meant to leave it out, put a line saying \
                             '{name}' in a file called '.pactignore' — at the top of the \
                             workspace, or in any folder above this one — and it will be \
                             skipped on purpose."
                        ),
                    )),
                    // Both file reasons, because both are the same sentence
                    // about the same collision and differ only in what the
                    // author can do about it. `license.yaml` can be saved as
                    // prose; `notice.md` already IS prose, and the way to keep
                    // it as writing about the project is to move it to the top
                    // of the workspace where that name means that.
                    Ignored::SettingsNamedLikeDocumentation
                    | Ignored::DocumentationInsideTheTree => {
                        let stem = name.rsplit_once('.').map_or(name.as_str(), |(s, _)| s);
                        let keep_it_as_writing = if reason == Ignored::DocumentationInsideTheTree {
                            format!(
                                "If it really is writing about the project, move it to the \
                                 top of the workspace, where '{stem}' means that."
                            )
                        } else {
                            format!(
                                "If it really is writing about the project, save it as \
                                 '{stem}.md' at the top of the workspace."
                            )
                        };
                        diags.push(Diagnostic::warning(
                            "loader/file-skipped-by-name",
                            Span::whole_file(&path),
                            format!(
                                "'{path}' was skipped, because a file called '{stem}' \
                                 is read as writing about this project rather than as \
                                 part of it."
                            ),
                            format!(
                                "If it holds settings, rename it — readme, license, licence, \
                                 notice, changelog, contributing and codeowners are all read \
                                 as writing about the project. {keep_it_as_writing} If you \
                                 meant to leave it out, put a line saying '{name}' in a file \
                                 called '.pactignore' — at the top of the workspace, or in any \
                                 folder above this one."
                            ),
                        ));
                        // CHK-12, one mistake one message. The warning above is
                        // the message; without this line it was the SECOND one,
                        // and the first was still wrong. Measured on the CLI
                        // test's own fixture — `tools/license.yaml` named by an
                        // agent's `uses:` — after the warning landed beside it:
                        //
                        //     error: 'uses' names 'license', and there is no such
                        //            entry in `tools:`, `skills:` or `knowledge:`.
                        //       fix: Nothing is declared there yet. Add a file
                        //            `tools/license.yaml` …
                        //
                        // — of the file the author is looking at, printed FIRST
                        // and as the error, exactly the harm CHK-12 exists to
                        // stop. Contributing the NAME and nothing else is the
                        // mechanism CHK-12 already uses for a file that will not
                        // parse: the reference resolves, and `pact_doc::UNLOADED`
                        // tells the schema to say nothing about contents nobody
                        // read.
                        //
                        // Two conditions, both measured rather than assumed.
                        //
                        // Not at the TOP of the workspace: a workspace's own
                        // fields are a closed set, so a placeholder there is a
                        // guaranteed `'license' is not something a workspace
                        // can have` — the same trade the folder rule refuses in
                        // the module doc above.
                        //
                        // And only for the STRUCTURED variant. A placeholder
                        // buys something only where a name is referenced, and
                        // `uses:`, `policy:` and their kind name tools, skills,
                        // knowledge and policies — all written as structured
                        // documents. Nothing references a `notice.md`, so there
                        // it buys nothing and costs a second message: measured
                        // on four sibling `.md` files in `agents/keeper/
                        // settings/`, the placeholder turned one warning per
                        // file into a warning AND `error: 'changelog' is not
                        // something settings can have` per file — CHK-12 broken
                        // by the repair for CHK-12.
                        if !at_root && reason == Ignored::SettingsNamedLikeDocumentation {
                            let (ordinal, key) = split_ordinal(stem);
                            let span = Span::whole_file(&path);
                            candidates.push(Candidate {
                                key: key.to_string(),
                                ordinal,
                                path,
                                span,
                                name_only: true,
                            });
                        }
                    }
                    Ignored::Hidden | Ignored::ToolArtifact | Ignored::Documentation => {}
                }
                continue;
            }

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
                self_file = Some(Candidate {
                    key: key.to_string(),
                    ordinal,
                    path,
                    span,
                    name_only: false,
                });
                continue;
            }

            candidates.push(Candidate {
                key: key.to_string(),
                ordinal,
                path,
                span,
                name_only: false,
            });
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
        path.strip_prefix(&self.root)
            .unwrap_or(path)
            .as_str()
            .replace('\\', "/")
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
        Entry {
            key_span: at.clone(),
            node: Node::str("yes", at.clone()),
        },
    );
    Node::map(m, at.clone())
}

/// The one refusal for a shortcut, wherever in the tree it is found.
///
/// A spec tree is a supply-chain surface and a link can point anywhere, so the
/// answer is the same at the top of an ordinary folder ([`Loader::load_path`])
/// and inside an attachment folder ([`Loader::walk_payload`]). It lives here
/// because it used to be written in only one of those two places, and an author
/// who moved a shortcut into `scripts/` got the opposite answer with no message
/// at all — see the test of the same name in `tests/`.
///
/// A link is refused for BEING a link, not for where it points. A relative
/// shortcut resolving safely inside the workspace is refused too: "shortcuts are
/// not followed" is a rule an author can hold in their head, and a
/// resolve-and-compare would answer differently depending on where the workspace
/// happens to be checked out.
fn symlink_skipped(path: &Utf8Path) -> Diagnostic {
    Diagnostic::warning(
        "loader/symlink-skipped",
        Span::whole_file(path),
        format!("'{path}' is a shortcut to somewhere else, so it was skipped."),
        "Move or copy the real file into this folder. Shortcuts are ignored because they \
         can point outside the project.",
    )
}

/// An entry that is neither an ordinary file nor a folder.
///
/// A named pipe, a unix socket, a device node — or, with
/// `follow_symlinks: true`, a shortcut whose target is a folder. None of them
/// is something a workspace can carry: a payload entry is a file the runtime
/// will open, and there is nothing to open here. Recording one anyway is the
/// same silent loss `loader/symlink-skipped` exists to close, one question
/// further down: `pact show` listed `mkfifo`'d `pipe.py` at `"sizeBytes": 0`
/// beside the real 235-byte `check_window.py`, the workspace digest moved, and
/// `pact check --deny-warnings` said *"loaded cleanly"* and exited 0.
///
/// A warning, matching [`symlink_skipped`]: the entry is left out and named,
/// and the rest of the tree is not made wrong by its absence.
fn not_a_regular_file(path: &Utf8Path, through_a_shortcut: bool, target_is_dir: bool) -> Diagnostic {
    let what = match (through_a_shortcut, target_is_dir) {
        (true, true) => "is a shortcut to a folder, so it was skipped",
        (true, false) => "is a shortcut to something that is not a file, so it was skipped",
        (false, _) => "is not an ordinary file, so it was skipped",
    };
    Diagnostic::warning(
        "loader/not-a-regular-file",
        Span::whole_file(path),
        format!("'{path}' {what}."),
        "Only ordinary files and folders are read. Replace it with the real file, or take \
         it out of this folder.",
    )
}

/// An entry the filesystem would not answer about at all.
///
/// The same `loader/unreadable` [`Loader::load_path`] raises one folder up, so
/// a dangling shortcut inside an attachment folder is answered the way the
/// identical dangling shortcut beside it is, instead of becoming a zero-byte
/// entry in the document.
fn unreadable_entry(path: &Utf8Path) -> Diagnostic {
    Diagnostic::error(
        "loader/unreadable",
        Span::whole_file(path),
        format!("'{path}' could not be read."),
        "Check the name is spelled correctly and that you have permission to read it.",
    )
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
        tree.file(
            "_index.yaml",
            "name: refund-desk\ndescription: Handles refunds\n",
        )
        // WITH the trailing newline, because every editor writes one and the
        // version of this fixture without it is why the divergence survived.
        .file("instructions.md", "Be kind and precise.\n");

        let (a, da) = flat.load();
        let (b, db) = tree.load();
        assert!(
            !da.has_errors() && !db.has_errors(),
            "{}{}",
            da.render(),
            db.render()
        );

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
            agents
                .get("triage")
                .unwrap()
                .get("description")
                .unwrap()
                .as_str(),
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
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "loader/ambiguous-field")
            .expect("reported");
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
        assert_eq!(
            keys,
            vec!["fetch", "summarise", "report"],
            "10 must sort after 2, not before"
        );
    }

    #[test]
    fn unordered_entries_sort_by_name_not_by_filesystem() {
        let t = Tree::new("stable");
        for n in ["zulu", "alpha", "mike"] {
            t.file(&format!("tools/{n}.yaml"), "kind: mcp\n");
        }
        let (node, _) = t.load();
        let root = node.unwrap();
        let keys: Vec<_> = root
            .get("tools")
            .unwrap()
            .as_map()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        assert_eq!(
            keys,
            vec!["alpha", "mike", "zulu"],
            "digests must be reproducible"
        );
    }

    #[test]
    fn names_clashing_only_by_case_are_refused() {
        let t = Tree::new("case");
        t.file("tools/Search.yaml", "a: 1\n")
            .file("tools/search.yaml", "b: 2\n");
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
        t.file("tools/search.yaml", "kind: mcp\n")
            .file("tools/search.json", "{}");
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
        t.file("_index.yaml", "name: desk\n")
            .file("logo.png", "\u{89}PNG fake bytes");
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
        assert_eq!(
            desk.get("instructions").unwrap().as_str().unwrap().trim(),
            "Be precise."
        );
    }

    #[test]
    fn two_self_files_are_refused() {
        let t = Tree::new("twoself");
        t.dir("desk");
        t.file("desk/_index.yaml", "a: 1\n")
            .file("desk/desk.yaml", "b: 2\n");
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
        assert!(
            node.get("tools").unwrap().get("good").is_some(),
            "good entries still load"
        );
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
        assert!(
            d.error_count() >= 3,
            "expected several distinct problems: {}",
            d.render()
        );
        for item in d.items() {
            assert!(
                !item.fix.trim().is_empty(),
                "rule {} gave no fix",
                item.rule
            );
            assert!(
                !item.message.trim().is_empty(),
                "rule {} gave no message",
                item.rule
            );
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
        assert!(
            ws["$payload"].is_string(),
            "must be a payload, not expanded fields"
        );
        let paths: Vec<&str> = ws["files"]
            .as_array()
            .unwrap()
            .iter()
            .map(|f| f["$file"].as_str().unwrap())
            .collect();
        assert_eq!(
            paths,
            vec!["data/cases.csv", "notes.md", "setup.py"],
            "sorted, verbatim"
        );
        assert!(
            ws.get("setup").is_none(),
            "payload contents must not become fields"
        );
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
        assert!(
            !paths.contains(&".pactpayload"),
            "the marker itself is not content"
        );
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
        t.file("steps/01-fetch.yaml", "do: fetch\n")
            .file("steps/01-verify.yaml", "do: verify\n");
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
        t.file("tools/caf\u{e9}.yaml", "a: 1\n") // café, NFC
            .file("tools/cafe\u{301}.yaml", "b: 2\n"); // café, NFD
        let (_, d) = t.load();
        let both_on_disk = fs::read_dir(t.0.join("tools"))
            .map(|r| r.count())
            .unwrap_or(0)
            == 2;
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
