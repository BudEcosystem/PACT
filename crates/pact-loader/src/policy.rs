//! Loader policy: the small set of choices that are *conventions* rather than
//! *rules*, isolated so they can be changed without touching the Expansion Rule
//! itself (invariant F-1: no capability-affecting literal buried in the core).

use camino::{Utf8Path, Utf8PathBuf};

/// Files that are documentation or tooling residue rather than specification.
/// Treating `README.md` as a field called `README` would be technically
/// consistent and practically absurd, so these are skipped.
///
/// The stem is only half the question — see [`Ignored::Documentation`] and
/// [`Ignored::SettingsNamedLikeDocumentation`]. `README.md` is documentation on
/// any reading; `tools/license.yaml` is a tool called `license` written in the
/// one form documentation is never written in.
const NON_SPEC_STEMS: &[&str] = &[
    "readme",
    "license",
    "licence",
    "notice",
    "changelog",
    "contributing",
    "codeowners",
];

/// Extensions parsed as structured documents.
const STRUCTURED: &[&str] = &["yaml", "yml", "json"];

/// Extensions read as prose.
const PROSE: &[&str] = &["md", "markdown"];

/// Extensions read as plain text values.
const PLAIN_TEXT: &[&str] = &["txt"];

/// Directory names never descended into, and TOLD ABOUT — every name here earns
/// the [`Ignored::ToolingFolder`] warning, because every name here is **also an
/// ordinary English noun an author could have meant**: an agent that runs
/// builds, a tool that ships a distribution, a skill about picking a target.
/// Behind one of these there might really be something somebody wrote, so the
/// warning can rescue it; that is the whole justification for the line of
/// output. Names that could never be authored are on [`TOOL_ONLY_DIRS`].
///
/// **Nothing beginning with a dot belongs on this list.** [`Policy::is_ignored`]
/// answers the leading-dot question first and returns [`Ignored::Hidden`], which
/// is SILENT, so a dotted name written here would be unreachable — a line that
/// reads like a rule and decides nothing. `.venv` sat here for a release doing
/// exactly that (D5).
///
/// Held by `no_folder_this_list_skips_is_one_the_dot_rule_answers_first` below.
pub const SPEAKING_SKIP_DIRS: &[&str] = &["dist", "build", "target"];

/// Directory names never descended into, and **never mentioned** — the ones no
/// author has ever typed on purpose.
///
/// This list exists because the warning [`SPEAKING_SKIP_DIRS`] earns is only
/// defensible where a real setting could be behind the name. Behind
/// `__pycache__` there never is one, so the message can never rescue anything
/// and can only ever be noise — and the noise is not free. Measured on this
/// repository's own Python adapter, with every one of these names speaking:
///
/// ```text
/// $ pact check adapters/python 2>&1 | grep -c loader/folder-skipped-by-name
/// 5
/// ```
///
/// — five lines, none of which names anything anybody wrote, and `pact check
/// --deny-warnings` at exit 1 on a tree whose only sin is that Python imported
/// its own tools once. The same run on a workspace where somebody had typed
/// `python -m venv venv` printed three.
///
/// That is verbatim the harm the `.venv` reasoning rejects — recorded at
/// `no_folder_this_list_skips_is_one_the_dot_rule_answers_first` below, where
/// `.venv` was deleted from the old list rather than promoted, because a
/// warning on it "would put a warning on every workspace an author had ever run
/// `python -m venv .venv` in". The argument does not become weaker when the dot
/// is left off, and for a release it was not applied: `python -m venv
/// venv` is the same command with the other conventional argument, and the fix
/// printed under the warning — *"rename it to something else"* — breaks the
/// virtual environment either way. `.venv` is answered by the dot rule;
/// `venv`, `node_modules` and `__pycache__` are answered here.
///
/// The two lists are a split of one former `SKIP_DIRS`, and the criterion is
/// stated once, above: *could an author have meant this name?* Held by
/// `a_name_only_a_tool_writes_is_told_apart_from_a_name_a_person_might_write`
/// below, and at the level of what the loader actually SAYS by
/// `a_folder_only_a_tool_ever_makes_is_skipped_without_a_word` in
/// `tests/an_agent_in_a_folder_named_build_is_never_silently_gone.rs`.
pub const TOOL_ONLY_DIRS: &[&str] = &["node_modules", "__pycache__", "venv"];

/// Why an entry takes no part in the document.
///
/// This used to be a bare `bool`, and the one caller answered it with a bare
/// `continue`. That is fine for two of these reasons and quietly wrong for the
/// other two: an author whose agent runs builds writes `agents/build/`, and the
/// whole agent disappeared with `pact check` reporting a clean load (thesis T7 —
/// no silent loss anywhere). Telling them requires knowing *which* reason
/// applied, because the whole decision is which reasons are worth a word:
///
/// - [`Ignored::Hidden`], [`Ignored::ToolArtifact`] and
///   [`Ignored::Documentation`] are silent. Every real workspace has a
///   `README.md` at the top and a `.gitignore`, half of them have a
///   `node_modules/`, none of the three was ever a setting, and a line about
///   each on every run is noise that teaches an author to stop reading the
///   output.
/// - [`Ignored::ToolingFolder`], [`Ignored::SettingsNamedLikeDocumentation`]
///   and [`Ignored::DocumentationInsideTheTree`] speak. `build`, `dist`,
///   `target` and `license` are ordinary English words, so the collision with a
///   tool's or a project's convention is the loader's accident rather than the
///   author's, and the author is the only one who knows which they meant.
///
/// **The criterion is the same one in all three speaking cases: could the
/// author have meant it?** It is asked of a folder by its NAME
/// ([`SPEAKING_SKIP_DIRS`] against [`TOOL_ONLY_DIRS`]) and of a file by its name
/// AND ITS PLACE:
///
/// - a documentation stem in the form settings are written in — `license.yaml`,
///   `notice.json` — is a collision at any depth, because nobody writes a
///   readme as a YAML document;
/// - a documentation stem written as prose is documentation **at the top of the
///   workspace**, where `README.md`, `CHANGELOG.md` and `CONTRIBUTING.md` are
///   what those names mean and always have been;
/// - the same stem written as prose **anywhere below the top** is the same
///   accident `agents/build/` is. `agents/keeper/settings/notice.md` is a file
///   somebody wrote inside a folder of settings, and for a release it took no
///   part in the document and produced no diagnostic — B2 verbatim, one
///   file-kind over. Measured on four sibling `.md` files of identical shape in
///   one ordinary folder: `escalation.md` became a field and was named,
///   `notice.md`, `changelog.md` and `contributing.md` produced no error, no
///   warning and no mention, and `pact show` had no trace of any of them.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Ignored {
    /// The name begins with a dot: tooling's own business, not a setting.
    Hidden,
    /// A directory a tool made and no author ever names ([`TOOL_ONLY_DIRS`]).
    /// Skipped like [`Ignored::ToolingFolder`] and, unlike it, in silence:
    /// there can be nothing of the author's behind `node_modules`, so a line
    /// about it can only ever be noise.
    ToolArtifact,
    /// A directory whose name is one that build and packaging tools fill in
    /// themselves ([`SPEAKING_SKIP_DIRS`]) *and* one an author could have meant.
    /// Descending into one would pull thousands of files nobody wrote into the
    /// document; skipping it in silence would lose an agent called `build`.
    ToolingFolder,
    /// A file that is documentation rather than specification: a
    /// [`NON_SPEC_STEMS`] stem written as prose, plain text or no extension at
    /// all, **at the top of the workspace** — `README.md`, `LICENSE`,
    /// `CHANGELOG.md`.
    Documentation,
    /// The same stem, the same prose form, **below the top of the workspace**.
    ///
    /// `agents/keeper/notice.md` is not a project's notice file; it is a file
    /// inside a folder of settings whose name happens to collide with one. The
    /// author is the only one who knows which they meant, so it is skipped and
    /// said out loud — the same answer `agents/build/` gets, for the same
    /// reason.
    DocumentationInsideTheTree,
    /// A file with a [`NON_SPEC_STEMS`] stem written as a *structured* document
    /// — `tools/license.yaml`, `notice.json`.
    ///
    /// The same skip as [`Ignored::Documentation`] and a different answer,
    /// because this one is almost certainly a setting. Measured before this
    /// variant existed, on a workspace holding a perfectly good
    /// `tools/license.yaml` named under an agent's `uses:`:
    ///
    /// ```text
    /// error: 'uses' names 'license', and there is no such entry in `tools:`,
    ///        `skills:` or `knowledge:`.
    ///   fix: Nothing is declared there yet. Add a file `tools/license.yaml`
    /// ```
    ///
    /// — the author told to write the file they had already written, because
    /// the loader discarded it without a word.
    SettingsNamedLikeDocumentation,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FileKind {
    /// YAML or JSON — parsed into a value tree.
    Structured,
    /// Markdown — front matter plus prose.
    Prose,
    /// Plain text — the whole file is a string value.
    PlainText,
    /// Anything else — referenced, never inlined.
    Opaque,
}

/// Marker file that declares its containing directory to be a payload.
pub(crate) const PAYLOAD_MARKER: &str = ".pactpayload";

#[derive(Debug, Clone)]
pub struct Policy {
    /// Largest text file that will be read into the document, in bytes.
    /// Beyond this the author is told to split the file — silently truncating
    /// or OOMing are both unacceptable.
    pub max_text_bytes: u64,
    /// Field name that a prose file's body lands in when the file also has
    /// front matter. Without front matter the file *is* the value.
    pub body_field: String,
    /// Follow symbolic links. Off by default: a spec tree is a supply-chain
    /// surface, and a link can point anywhere.
    pub follow_symlinks: bool,
    /// Filename stems that name *what a thing is* and therefore describe the
    /// directory containing them (see [`Policy::is_self_file`]). This is the
    /// closed set of PACT document kinds.
    pub kind_stems: Vec<String>,
    /// Directory names that are file sets rather than structure. Their contents
    /// are carried verbatim, preserving filenames and extensions.
    ///
    /// Kept deliberately short. A directory becoming a payload is a meaningful
    /// change in how it is read, so beyond these two well-established names an
    /// author must say so explicitly with a [`PAYLOAD_MARKER`] file.
    pub payload_dirs: Vec<String>,
}

impl Default for Policy {
    fn default() -> Self {
        Self {
            // ONE constant, not a second `4 * 1024 * 1024` that happens to
            // match. This figure and `pact_doc::yaml::MAX_TEXT` are the same
            // answer to the same question — how much writing one document may
            // hold — asked at two moments: here of the file on disk, there of
            // what the file works out to once every `*name` has been copied in.
            // Written out separately they were free to drift, and the direction
            // of the drift decides which of two differently-worded refusals an
            // author gets for one file. See `pact_doc::yaml::MAX_TEXT` for why
            // both are still needed and which one an alias-free file always
            // meets first.
            max_text_bytes: pact_doc::yaml::MAX_TEXT as u64,
            body_field: "content".to_string(),
            follow_symlinks: false,
            // Only the stems where a kind's root file is named after the KIND
            // rather than after its directory:
            //     <ws>/workspace.yaml        agents/<n>/agent.yaml
            //     skills/<n>/SKILL.md        evals/suite.yaml
            //     models/catalog.yaml
            //
            // Everything else is named after the thing (`policies/refunds.yaml`,
            // `resources/payments.yaml`, `graphs/triage.yaml`) and is matched by
            // the directory-name rule, or is a FIELD of the enclosing document
            // and must not be a self file at all — `learning.yaml` at the
            // workspace root is the workspace's `learning:` field, and listing
            // it here made every workspace report two self files.
            //
            // `team`, `variant`, `workflow` and `contract` are gone with the
            // kinds themselves (X5, X15).
            kind_stems: [
                "workspace",
                "agent",
                "skill",
                "suite",
                "catalog",
                // Added with the port/loop/context-policy kinds. A file named
                // after WHAT IT IS describes its folder, so
                // `ports/slack/port.yaml` is the port rather than a field
                // called `port` inside it.
                "port",
                "schedule",
                "loop",
                "interceptor",
                "context-policy",
                "state",
                // The OBSERVE half of the event lattice. Here for the same
                // reason `interceptor` is: `watch/slow-tools/watch.yaml` IS the
                // watch, not a field called `watch` sitting inside it. Without
                // it the folder spelling of a watch is the one thing the
                // Expansion Rule refuses, and `diagnostics.SELF_FILES` — which
                // this function's docstring says it mirrors — would send an
                // author to a file the loader never read.
                "watch",
                // A question put to a person. Same rule: `questions/keep-going/
                // question.yaml` IS the question, not a field called `question`
                // sitting inside it.
                "question",
                // Three kinds that predate this list and were never added to
                // it — the same omission `watch` and `question` were fixed for,
                // one round later. Measured before the fix: delete
                // `tools/weather.yaml`, write `tools/weather/tool.yaml` holding
                // the same three lines, and `pact check` answered
                //
                //     error: 'tool' is not something a tool can have.
                //       --> tools/weather/tool.yaml:1:1
                //       fix: Remove it, or use one of: description, connect, …
                //
                // of a file whose name is the ONE thing the author cannot
                // remove — plus *"A tool must have a 'description'"* with the
                // arrow on the DIRECTORY and no excerpt, because the settings
                // had landed a level down in a field called `tool`.
                // `policies/approvals/policy.yaml` and
                // `resources/payments-server/resource.yaml` failed the same
                // way, the second suggesting *"Did you mean 'resource-kind'?"*.
                //
                // Nothing distinguished them from `port` or `question`. They
                // were simply the kinds that already existed when this list was
                // first written, so the folder spelling the Expansion Rule
                // accepts everywhere else was the one spelling it refused here,
                // and the refusal named a fix that cannot be typed.
                "tool",
                "policy",
                "resource",
                // A program's root file is `programs/<name>/program.yaml`, named
                // after the kind, so the folder is the thing and the file
                // describes it — the shape `agent` and `skill` already have.
                "program",
                // `redaction` is deliberately NOT here, and the reason is the
                // `learning.yaml` sentence above rather than an oversight.
                // `agent.policy` is a NAME (`policy: approvals`), so the cost of
                // the stem is the one this module's docstring already accepts
                // and `loop` and `context-policy` already pay: that one field
                // has to be typed in the self file. `workspace.redaction` is a
                // whole GROUP, and `redaction.yaml` beside `workspace.yaml` is
                // not one author's stylistic choice — it is the spelling the
                // schema's own help gives, the spelling `redaction.rs` tells an
                // author to create, and the spelling the worked example ships.
                // Measured with "redaction" added to this list:
                //
                //     error: This folder has two files describing itself:
                //     'workspace.yaml' and 'redaction.yaml'.
                //       --> examples/refund-desk/redaction.yaml:1:1
                //       fix: Keep only one of them.
                //
                // — advice that deletes either the workspace or everything the
                // workspace may never let out. The folder spelling of a
                // redaction needs nothing from this list anyway: there is one
                // per workspace, so its folder is `redaction/` and
                // `redaction/redaction.yaml` is already a self file by the
                // directory-name rule.
            ]
            .iter()
            .map(|s| (*s).to_string())
            .collect(),
            // Package payloads. `references/`, `scripts/` and `assets/` are the
            // Agent Skills convention; their contents are files a skill points
            // at, not settings, so extensions and names are preserved verbatim.
            // `documents` joins the list that was already `references/` and
            // `scripts/`: a set of documents is kept as FILES, digested, typed
            // and sized by the same walker, so a table stays a table and
            // deleting a document moves the digest. That is the whole reason
            // `knowledge.documents` is not a glob — there is no path type in
            // this language, and a glob's file ORDER is load-bearing for a
            // digest the loader promises is reproducible on any machine.
            // `body` is a program's own files (P6), carried the way `scripts`
            // is: by name, media type, size and fingerprint, never opened. It is
            // a payload directory for exactly the reason the other five are —
            // expanding `check-window.wasm` into a field called `check-window`
            // would silently discard the extension, which is the quiet loss T7
            // forbids.
            payload_dirs: [
                "workspace",
                "assets",
                "references",
                "scripts",
                "documents",
                "body",
            ]
            .iter()
            .map(|s| (*s).to_string())
            .collect(),
        }
    }
}

impl Policy {
    pub fn file_kind(&self, path: &Utf8Path) -> FileKind {
        let ext = path.extension().unwrap_or_default().to_ascii_lowercase();
        if STRUCTURED.contains(&ext.as_str()) {
            FileKind::Structured
        } else if PROSE.contains(&ext.as_str()) {
            FileKind::Prose
        } else if PLAIN_TEXT.contains(&ext.as_str()) {
            FileKind::PlainText
        } else {
            FileKind::Opaque
        }
    }

    /// Should this directory entry take part in the document at all?
    ///
    /// `None` means yes. `Some(reason)` means no, and says why so the caller
    /// can decide whether the author needs to hear about it — see [`Ignored`].
    /// A pure function of the name and of one bit about where it sits:
    /// `at_workspace_root` says whether the folder holding this entry is the
    /// top of the tree being loaded. Nothing here touches the filesystem, so
    /// the answer is the same on every machine and the digest stays
    /// reproducible.
    ///
    /// The place bit exists for prose only, and only because `README.md` means
    /// two different things in two places — see
    /// [`Ignored::DocumentationInsideTheTree`]. A folder's answer does not
    /// depend on it, and neither does a structured file's.
    pub fn is_ignored(&self, name: &str, is_dir: bool, at_workspace_root: bool) -> Option<Ignored> {
        if name.starts_with('.') {
            return Some(Ignored::Hidden);
        }
        if is_dir {
            if SPEAKING_SKIP_DIRS.contains(&name) {
                return Some(Ignored::ToolingFolder);
            }
            return TOOL_ONLY_DIRS
                .contains(&name)
                .then_some(Ignored::ToolArtifact);
        }
        let (stem, ext) = name.rsplit_once('.').map_or((name, ""), |(s, e)| (s, e));
        if !NON_SPEC_STEMS.contains(&stem.to_ascii_lowercase().as_str()) {
            return None;
        }
        // A readme is never written as `readme.yaml`, so a documentation stem
        // in the form settings are written in is a collision rather than a
        // document — and the author is the only one who can say which.
        if STRUCTURED.contains(&ext.to_ascii_lowercase().as_str()) {
            return Some(Ignored::SettingsNamedLikeDocumentation);
        }
        // Prose. At the top of the workspace this is the project's own writing
        // and always has been. One folder down it is a file inside a folder of
        // settings, and the collision is the loader's accident rather than the
        // author's.
        if at_workspace_root {
            return Some(Ignored::Documentation);
        }
        Some(Ignored::DocumentationInsideTheTree)
    }

    /// Is this entry the directory's *self file* — the one providing the
    /// directory's own fields rather than a field named after itself?
    ///
    /// Three spellings are accepted, because each reads naturally to a
    /// different author:
    ///
    /// - `_index.yaml` — explicit, familiar to anyone who has seen a static
    ///   site generator;
    /// - `refund-desk/refund-desk.yaml` — named after the directory;
    /// - `refund-desk/agent.yaml` — named after *what the thing is*.
    ///
    /// The third matters most for decision D13. `agents/refund-desk/agent.yaml`
    /// is what a non-technical author writes without being taught anything;
    /// `_index` is programmer vocabulary. Eve reached the same conclusion with
    /// `agent.ts`, and that ergonomic choice is worth keeping.
    ///
    /// The cost is that a field genuinely named `agent` cannot be written as
    /// `agent.yaml` inside a directory — it must go in the self file. That is a
    /// narrow, teachable limitation, and [`Policy::kind_stems`] can be narrowed
    /// by an embedder that does not want it.
    pub fn is_self_file(&self, dir_name: &str, stem: &str) -> bool {
        stem == "_index"
            || stem.eq_ignore_ascii_case(dir_name)
            || self.kind_stems.iter().any(|k| k.eq_ignore_ascii_case(stem))
    }

    /// Is this directory a payload (a verbatim file set) rather than structure?
    ///
    /// True when its name is a well-known payload name, or when it contains a
    /// [`PAYLOAD_MARKER`] file. The marker is the general escape hatch, so any
    /// directory can opt in without extending this list.
    pub fn is_payload_dir(&self, dir: &Utf8Path) -> bool {
        let name = dir.file_name().unwrap_or_default();
        if self.payload_dirs.iter().any(|d| d == name) {
            return true;
        }
        dir.join(PAYLOAD_MARKER).exists()
    }

    /// Best-effort media type for an opaque payload.
    pub fn content_type(&self, path: &Utf8Path) -> String {
        let ext = path.extension().unwrap_or_default().to_ascii_lowercase();
        match ext.as_str() {
            "png" => "image/png",
            "jpg" | "jpeg" => "image/jpeg",
            "gif" => "image/gif",
            "webp" => "image/webp",
            "svg" => "image/svg+xml",
            "pdf" => "application/pdf",
            "wav" => "audio/wav",
            "mp3" => "audio/mpeg",
            "m4a" => "audio/mp4",
            "ogg" => "audio/ogg",
            "mp4" => "video/mp4",
            "webm" => "video/webm",
            "csv" => "text/csv",
            "jsonl" | "ndjson" => "application/x-ndjson",
            "parquet" => "application/vnd.apache.parquet",
            "zip" => "application/zip",
            "" => "application/octet-stream",
            other => return format!("application/{other}"),
        }
        .to_string()
    }
}

/// Split a filename stem into an optional ordinal prefix and the field key.
///
/// `01-fetch` → `(Some(1), "fetch")`; `fetch` → `(None, "fetch")`.
///
/// Ordinals exist because some fields are genuinely ordered (pipeline steps),
/// and filesystem read order is not stable across platforms. Encoding order in
/// the name keeps the tree self-describing and the digest reproducible.
pub fn split_ordinal(stem: &str) -> (Option<u32>, &str) {
    let digits_end = stem
        .find(|c: char| !c.is_ascii_digit())
        .unwrap_or(stem.len());
    if digits_end == 0 || digits_end == stem.len() {
        return (None, stem);
    }
    let sep = stem.as_bytes()[digits_end];
    if sep != b'-' && sep != b'_' {
        return (None, stem);
    }
    let rest = &stem[digits_end + 1..];
    if rest.is_empty() {
        return (None, stem);
    }
    match stem[..digits_end].parse::<u32>() {
        Ok(n) => (Some(n), rest),
        Err(_) => (None, stem),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ordinals_are_split_only_when_well_formed() {
        assert_eq!(split_ordinal("01-fetch"), (Some(1), "fetch"));
        assert_eq!(split_ordinal("10_summarise"), (Some(10), "summarise"));
        assert_eq!(split_ordinal("fetch"), (None, "fetch"));
        assert_eq!(
            split_ordinal("2024"),
            (None, "2024"),
            "a bare number is a name"
        );
        // The separator must be '-' or '_', so a name like `3d-model` is a
        // name, not step 3 of something called "d-model".
        assert_eq!(split_ordinal("3d-model"), (None, "3d-model"));
        assert_eq!(split_ordinal("01"), (None, "01"));
        assert_eq!(split_ordinal("01-"), (None, "01-"));
        assert_eq!(
            split_ordinal("v2-agent"),
            (None, "v2-agent"),
            "must start with digits"
        );
    }

    #[test]
    fn documentation_files_are_not_fields() {
        let p = Policy::default();
        // Each answer now carries its reason, because only one of the three is
        // said out loud and the caller has no other way to tell them apart.
        assert_eq!(
            p.is_ignored("README.md", false, true),
            Some(Ignored::Documentation)
        );
        assert_eq!(
            p.is_ignored("LICENSE", false, true),
            Some(Ignored::Documentation)
        );
        // Same stem, and a different answer: `.yaml` is the form settings are
        // written in and the form no readme is ever written in.
        assert_eq!(
            p.is_ignored("license.yaml", false, true),
            Some(Ignored::SettingsNamedLikeDocumentation)
        );
        assert_eq!(
            p.is_ignored(".hidden.yaml", false, true),
            Some(Ignored::Hidden)
        );
        assert_eq!(
            p.is_ignored("node_modules", true, true),
            Some(Ignored::ToolArtifact)
        );
        assert_eq!(p.is_ignored("instructions.md", false, false), None);
        assert_eq!(p.is_ignored("tools", true, true), None);
    }

    #[test]
    fn every_folder_a_tool_claims_is_told_apart_from_a_readme() {
        let p = Policy::default();
        // The lists themselves, rather than a copy of them, so adding a name
        // without thinking about the message is a red test rather than a new
        // silent deletion — and so this can never quietly fall out of step with
        // what the loader actually skips.
        for name in SPEAKING_SKIP_DIRS {
            assert_eq!(
                p.is_ignored(name, true, true),
                Some(Ignored::ToolingFolder),
                "'{name}' is skipped, and the author has to be told"
            );
        }
        for name in TOOL_ONLY_DIRS {
            assert_eq!(
                p.is_ignored(name, true, true),
                Some(Ignored::ToolArtifact),
                "'{name}' is skipped, and saying so on every run is noise"
            );
        }
        // A FILE called `build` is not a folder a tool fills in; it is a
        // setting called `build`, and nothing about it is skipped.
        assert_eq!(p.is_ignored("build", false, true), None);
        assert_eq!(p.is_ignored("build.yaml", false, true), None);
    }

    /// The split, stated as the property that justifies it rather than as a
    /// second copy of the two lists.
    ///
    /// A name that SPEAKS costs a line of output on every tree that holds one,
    /// and the only thing that buys is the chance that something the author
    /// wrote is behind it. So a speaking name has to be one an author could
    /// have typed, and a silent name has to be one no author ever would. The
    /// two populations were one list for a release, and the consequence was
    /// `pact check --deny-warnings` at exit 1 on any workspace where anybody
    /// had ever run `npm install`, `cargo build` or `python -m venv venv` —
    /// with advice, *"rename it to something else"*, that is meaningless for
    /// `node_modules` and destructive for `venv`.
    #[test]
    fn a_name_only_a_tool_writes_is_told_apart_from_a_name_a_person_might_write() {
        // Every speaking name is a word. Nothing here is a punctuation-and-
        // underscore token or a package manager's private vocabulary.
        for name in SPEAKING_SKIP_DIRS {
            assert!(
                name.chars().all(|c| c.is_ascii_lowercase()),
                "'{name}' speaks, so it has to be a name a person could have \
                 typed on purpose — and a person does not type underscores or \
                 digits into a folder name they meant"
            );
        }
        // And no name is on both lists, which is the failure that would make
        // the answer depend on the order the two are consulted in.
        for name in TOOL_ONLY_DIRS {
            assert!(
                !SPEAKING_SKIP_DIRS.contains(name),
                "'{name}' is on both lists"
            );
        }
    }

    /// The `.md` half of the same question, and the one that was wrong for a
    /// release: a documentation STEM is only documentation where documentation
    /// lives.
    #[test]
    fn a_prose_file_named_like_documentation_is_documentation_only_at_the_top() {
        let p = Policy::default();
        for name in ["README.md", "notice.md", "CHANGELOG.md", "contributing.md"] {
            assert_eq!(
                p.is_ignored(name, false, true),
                Some(Ignored::Documentation),
                "'{name}' at the top of a workspace is the project's own writing"
            );
            assert_eq!(
                p.is_ignored(name, false, false),
                Some(Ignored::DocumentationInsideTheTree),
                "'{name}' inside the tree is a file somebody wrote in a folder \
                 of settings, and losing it in silence is B2 one file-kind over"
            );
        }
        // The two answers that do NOT depend on where the file sits: a
        // structured document is a collision wherever it is, and a name that is
        // not a documentation stem at all is a setting wherever it is.
        for at_root in [true, false] {
            assert_eq!(
                p.is_ignored("license.yaml", false, at_root),
                Some(Ignored::SettingsNamedLikeDocumentation)
            );
            assert_eq!(p.is_ignored("escalation.md", false, at_root), None);
        }
    }

    /// D5. `.venv` sat in [`SKIP_DIRS`] for a release and could never match:
    /// the leading-dot test answers first with [`Ignored::Hidden`], which is
    /// silent, so the entry read like a rule and decided nothing.
    ///
    /// It is gone, and the assertions here are what keep it gone. The first
    /// says the answer for a dotted folder is silence and is the one that was
    /// deliberate; the second says no future name may be added to either list
    /// that the dot rule would swallow the same way. Together with the loops
    /// above — which read the lists themselves — a dotted entry added here is a
    /// red test in two places rather than a line nobody notices.
    ///
    /// The third assertion is the one that was missing for a release. The
    /// reason `.venv` is silent has nothing to do with the dot: it is that a
    /// warning there fails `--deny-warnings` on every workspace anyone ran
    /// `python -m venv` in, and tells them to rename a folder that breaks when
    /// renamed. `venv` sat on the speaking list with the identical property.
    #[test]
    fn no_folder_this_list_skips_is_one_the_dot_rule_answers_first() {
        let p = Policy::default();
        assert_eq!(
            p.is_ignored(".venv", true, true),
            Some(Ignored::Hidden),
            "a virtual environment is hidden, and hidden is silent: warning about \
             it would fail --deny-warnings on every workspace anyone ran \
             `python -m venv .venv` in, and tell them to rename it"
        );
        for name in SPEAKING_SKIP_DIRS.iter().chain(TOOL_ONLY_DIRS) {
            assert!(
                !name.starts_with('.'),
                "'{name}' is on a skip list and begins with a dot, so `is_ignored` \
                 answers `Hidden` before the list is ever consulted and the entry \
                 can never match. Either take it out, or move the dot test after \
                 the list and accept that every dotted folder now gets a warning."
            );
        }
        // The other spelling of the same command, which must get the same
        // silence for the same reason.
        assert_eq!(
            p.is_ignored("venv", true, true),
            Some(Ignored::ToolArtifact),
            "`python -m venv venv` is `python -m venv .venv` with the other \
             conventional argument. Whatever answer one gets, the other gets."
        );
    }

    #[test]
    fn a_documentation_stem_is_read_by_its_extension() {
        let p = Policy::default();
        // Written as prose or as nothing in particular: documentation, silent.
        for name in [
            "README.md",
            "readme.markdown",
            "LICENSE",
            "licence.txt",
            "NOTICE",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "CODEOWNERS",
        ] {
            assert_eq!(
                p.is_ignored(name, false, true),
                Some(Ignored::Documentation),
                "'{name}' is documentation, and saying so on every run is noise"
            );
        }
        // Written as a structured document: a setting, and its loss is worth a
        // word. Every stem, so adding one to `NON_SPEC_STEMS` without thinking
        // about the message is a red test rather than a new silent deletion.
        for stem in [
            "readme",
            "license",
            "licence",
            "notice",
            "changelog",
            "contributing",
            "codeowners",
        ] {
            for ext in ["yaml", "yml", "json", "YAML"] {
                assert_eq!(
                    p.is_ignored(&format!("{stem}.{ext}"), false, true),
                    Some(Ignored::SettingsNamedLikeDocumentation),
                    "'{stem}.{ext}' is far more likely to be a setting than a document"
                );
            }
        }
        // A DIRECTORY called `license` is expanded like any other: the stem
        // rule is about files, and `tools/license/tool.yaml` is a tool.
        assert_eq!(p.is_ignored("license", true, true), None);
    }

    #[test]
    fn self_file_accepts_both_conventions() {
        let p = Policy::default();
        assert!(p.is_self_file("refund-desk", "_index"));
        assert!(p.is_self_file("refund-desk", "refund-desk"));
        // D13: this is the spelling a non-technical author reaches for.
        assert!(p.is_self_file("refund-desk", "agent"));
        // `evals/suite.yaml` is the primary spelling of the EvalSuite root
        // file; LOAD-5 makes it, `evals.yaml` and `_index.yaml` one document.
        assert!(p.is_self_file("evals", "suite"));
        assert!(p.is_self_file("evals", "evals"));
        // `team` is no longer a kind (X5): multi-agent is the `team:` FIELD on
        // an Agent, or a Graph.
        assert!(!p.is_self_file("research-team", "team"));
        assert!(!p.is_self_file("refund-desk", "instructions"));
        assert!(!p.is_self_file("refund-desk", "needs"));
    }

    #[test]
    fn the_four_oldest_kinds_spell_a_folder_the_way_every_other_kind_does() {
        let p = Policy::default();
        // Three that used to be refused. `tools/weather/tool.yaml` printed
        // *"'tool' is not something a tool can have. fix: Remove it"* of a
        // filename, which is the one word in that message an author cannot
        // remove.
        assert!(p.is_self_file("weather", "tool"));
        assert!(p.is_self_file("approvals", "policy"));
        assert!(p.is_self_file("payments-server", "resource"));

        // And the fourth, which needs nothing from `kind_stems`: there is one
        // redaction per workspace, so its folder is `redaction/` and the file
        // inside it matches the folder's own name.
        assert!(p.is_self_file("redaction", "redaction"));

        // The reason it must stay out of the list. `redaction.yaml` sits beside
        // `workspace.yaml` — the spelling the schema's help gives and the worked
        // example ships — so a stem for it would make the workspace root a
        // folder with two files describing itself, exactly as `learning` did.
        // This is the assertion that turns "somebody adds the obvious fourth
        // entry" into a red unit test rather than a broken worked example.
        assert!(
            !p.is_self_file("refund-desk", "redaction"),
            "`redaction.yaml` at the top of a workspace is the workspace's \
             `redaction:` setting, not a second file describing the workspace"
        );
        assert!(
            !p.is_self_file("refund-desk", "learning"),
            "the same, for `learning.yaml`"
        );
    }

    #[test]
    fn file_kinds_cover_all_four_modalities() {
        let p = Policy::default();
        assert_eq!(p.file_kind(Utf8Path::new("a.yaml")), FileKind::Structured);
        assert_eq!(p.file_kind(Utf8Path::new("a.MD")), FileKind::Prose);
        assert_eq!(p.file_kind(Utf8Path::new("a.txt")), FileKind::PlainText);
        // D16: vision/audio/video payloads must be referenced, not inlined.
        for f in ["a.png", "a.wav", "a.mp4", "a.pdf"] {
            assert_eq!(p.file_kind(Utf8Path::new(f)), FileKind::Opaque);
        }
        assert_eq!(p.content_type(Utf8Path::new("a.png")), "image/png");
        assert_eq!(p.content_type(Utf8Path::new("a.wav")), "audio/wav");
    }
}

/// One line of a `.pactignore`, and the file it was written in.
///
/// The file is carried because a suppression has to be reportable — EXP-10 asks
/// for "a LoadReport line naming the entry AND the pattern", and with
/// [`Ignore::inherited`] the pattern may have been written several folders up
/// from the entry it removes. A message that said only *"a `.pactignore` line"*
/// would send the reader to the wrong folder.
#[derive(Debug, Clone)]
pub struct Pattern {
    /// The line as the author typed it, comment and surrounding space removed.
    pub text: String,
    /// The `.pactignore` file it came from.
    pub from: Utf8PathBuf,
}

/// Patterns from the `.pactignore` files covering one directory: one glob-ish
/// pattern per line, `#` for comments. Deliberately simple — `*` matches within
/// a name, `/` is not special, and there is no negation. An author who needs
/// more than this is solving the wrong problem.
#[derive(Debug, Clone, Default)]
pub struct Ignore {
    patterns: Vec<Pattern>,
    /// The `.pactignore` files that were there and were not read, because they
    /// were not regular files. See [`Ignore::load`].
    skipped: Vec<Utf8PathBuf>,
}

impl Ignore {
    /// Read `.pactignore` from one directory alone. Absent file means no
    /// patterns.
    ///
    /// Only a REGULAR file is opened, and the check is `symlink_metadata` so the
    /// link itself is what is asked about. Both halves were holes.
    ///
    /// `mkfifo .pactignore` made every verb that reads a tree — `check`, `show`,
    /// `waits`, `discover`, `card` — block for ever with no output at all,
    /// because `read_to_string` on a pipe with no writer never returns. That is
    /// R5's promise broken from the other side: reading a stranger's tree does
    /// not run their code, and it also has to END. The loader already knows this
    /// hazard and raises `loader/not-a-regular-file` for a pipe, socket or device
    /// the payload walk finds — but this file is opened at every directory from
    /// the root down, before either walk can see it.
    ///
    /// And `.pactignore -> /etc/passwd` loaded cleanly, with that file's lines
    /// becoming this tree's ignore patterns and its text quoted back in the
    /// `loader/ignored-on-purpose` message. [`Ignore::inherited`] already says
    /// nothing above the tree may reach into it; a shortcut walked round the
    /// rule.
    ///
    /// A skipped file leaves no patterns, which is the same state as no file at
    /// all: the entries it would have hidden are reported instead of silently
    /// dropped, and being told about a file you meant to ignore is the harmless
    /// direction. What it is NOT is silent — see [`Ignore::skipped`].
    pub fn load(dir: &Utf8Path) -> Self {
        Self::load_within(dir, None)
    }

    /// The same, told where the tree it is loading begins.
    ///
    /// `root` is what makes a shortcut answerable. A link is followed when it
    /// lands on a regular file INSIDE the tree — a `.pactignore` that is a
    /// shortcut to a shared list one folder along is an ordinary thing to write,
    /// and refusing every link stopped such a workspace ignoring anything while
    /// telling it, untruthfully, that the link pointed at "something that is not
    /// a file". A link that leaves the tree is refused, which is the rule
    /// [`Ignore::inherited`] already states: nothing above the tree may reach
    /// into it.
    pub fn load_within(dir: &Utf8Path, root: Option<&Utf8Path>) -> Self {
        let at = dir.join(".pactignore");
        let Ok(meta) = std::fs::symlink_metadata(&at) else {
            return Self::default();
        };
        if meta.file_type().is_symlink() {
            let inside = std::fs::canonicalize(&at).ok().and_then(|target| {
                let target = Utf8PathBuf::from_path_buf(target).ok()?;
                let base = root.and_then(|r| {
                    std::fs::canonicalize(r)
                        .ok()
                        .and_then(|c| Utf8PathBuf::from_path_buf(c).ok())
                })?;
                let ok = target.starts_with(&base) && target.is_file();
                Some(ok)
            });
            if inside != Some(true) {
                return Self {
                    patterns: Vec::new(),
                    skipped: vec![at],
                };
            }
        } else if !meta.is_file() {
            return Self {
                patterns: Vec::new(),
                skipped: vec![at],
            };
        }
        let text = std::fs::read_to_string(&at).unwrap_or_default();
        Self::parse_from(&text, &at)
    }

    /// Every `.pactignore` that was found and not read, with where it was.
    ///
    /// Carried rather than reported here because this type has no diagnostics to
    /// report into — it is read from two walks, both of which have one, and both
    /// of which say the same sentence about a file of the wrong shape anywhere
    /// else in the tree.
    pub fn skipped(&self) -> &[Utf8PathBuf] {
        &self.skipped
    }

    /// Read every `.pactignore` from `root` down to `dir` inclusive.
    ///
    /// This is what the loader uses, and the reason is what an author expects
    /// from the only file of this shape they have ever seen. Measured on a
    /// realistic JavaScript layout — `node_modules/` at the top and under three
    /// packages — with the per-directory rule: a single `node_modules` line in
    /// the workspace's own `.pactignore` left four of the five folders still
    /// warning, so silencing a name guaranteed to recur cost one `.pactignore`
    /// per occurrence and the `--deny-warnings` gate stayed red until every one
    /// of them had been written.
    ///
    /// Outer files come first, so [`Ignore::matching`] reports the outermost
    /// line that answers — which is the one an author would delete to bring the
    /// entry back.
    ///
    /// `dir` outside `root` reads `dir` alone: nothing above the tree being
    /// loaded may reach into it.
    pub fn inherited(root: &Utf8Path, dir: &Utf8Path) -> Self {
        let Ok(rel) = dir.strip_prefix(root) else {
            return Self::load_within(dir, None);
        };
        let mut at = root.to_path_buf();
        let mut all = Self::load_within(&at, Some(root));
        for part in rel.components() {
            at = at.join(part.as_str());
            let here = Self::load_within(&at, Some(root));
            all.patterns.extend(here.patterns);
            all.skipped.extend(here.skipped);
        }
        all
    }

    pub fn parse(text: &str) -> Self {
        Self::parse_from(text, Utf8Path::new(".pactignore"))
    }

    pub fn parse_from(text: &str, from: &Utf8Path) -> Self {
        Self {
            patterns: text
                .lines()
                .map(|l| l.split('#').next().unwrap_or("").trim().to_string())
                .filter(|l| !l.is_empty())
                .map(|text| Pattern {
                    text,
                    from: from.to_path_buf(),
                })
                .collect(),
            skipped: Vec::new(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.patterns.is_empty()
    }

    pub fn matches(&self, name: &str) -> bool {
        self.matching(name).is_some()
    }

    /// The first pattern that answers for `name`, with the file it was written
    /// in — so the skip can be reported instead of being a bare `continue`.
    pub fn matching(&self, name: &str) -> Option<&Pattern> {
        self.patterns.iter().find(|p| glob_match(&p.text, name))
    }
}

/// `*` matches any run of characters; everything else is literal.
fn glob_match(pattern: &str, name: &str) -> bool {
    let parts: Vec<&str> = pattern.split('*').collect();
    if parts.len() == 1 {
        return pattern == name;
    }
    let mut pos = 0usize;
    for (i, part) in parts.iter().enumerate() {
        if part.is_empty() {
            continue;
        }
        match name[pos..].find(part) {
            Some(found) => {
                // A leading literal must match at the very start.
                if i == 0 && found != 0 {
                    return false;
                }
                pos += found + part.len();
            }
            None => return false,
        }
    }
    // A trailing literal must reach the end.
    match parts.last() {
        Some(last) if !last.is_empty() => name.ends_with(last),
        _ => true,
    }
}

#[cfg(test)]
mod ignore_tests {
    use super::*;

    #[test]
    fn parses_comments_and_blank_lines_away() {
        let ig = Ignore::parse("# notes\n\n*.tmp\n  scratch  # inline\n");
        assert!(ig.matches("build.tmp"));
        assert!(ig.matches("scratch"));
        assert!(!ig.matches("agent.yaml"));
    }

    #[test]
    fn globs_match_where_expected_and_not_where_not() {
        assert!(glob_match("*.tmp", "a.tmp"));
        assert!(glob_match("draft-*", "draft-notes.md"));
        assert!(glob_match("*", "anything"));
        assert!(glob_match("exact.yaml", "exact.yaml"));
        assert!(!glob_match("*.tmp", "a.tmpx"));
        assert!(!glob_match("draft-*", "final-draft-notes.md"));
        assert!(!glob_match("exact.yaml", "exact.yml"));
    }

    #[test]
    fn an_empty_ignore_file_excludes_nothing() {
        assert!(Ignore::parse("").is_empty());
        assert!(!Ignore::parse("").matches("anything.yaml"));
    }

    /// A pattern has to be reportable, which means knowing which line answered
    /// and which file it was written in. EXP-10 asks for the entry AND the
    /// pattern; with [`Ignore::inherited`] the pattern can be several folders
    /// above the entry it removes, so naming only the entry would send the
    /// reader to the wrong `.pactignore`.
    #[test]
    fn a_match_says_which_line_answered_and_where_it_was_written() {
        let ig = Ignore::parse_from("*.tmp\nscratch\n", Utf8Path::new("ws/.pactignore"));
        let m = ig.matching("build.tmp").expect("it matches");
        assert_eq!(m.text, "*.tmp");
        assert_eq!(m.from, Utf8PathBuf::from("ws/.pactignore"));
        assert!(ig.matching("agent.yaml").is_none());
    }

    /// Outer files first, so the line a reader is sent to is the outermost one
    /// that answers — the one they would delete to bring the entry back.
    #[test]
    fn an_inherited_set_reports_the_outermost_line_that_answers() {
        let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
            .join(format!("pact-ignore-chain-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(base.join("packages/api")).unwrap();
        std::fs::write(base.join(".pactignore"), "node_modules\n").unwrap();
        std::fs::write(base.join("packages/api/.pactignore"), "node_modules\n").unwrap();

        let deep = Ignore::inherited(&base, &base.join("packages/api"));
        let m = deep
            .matching("node_modules")
            .expect("the parent's line covers it");
        assert_eq!(
            m.from,
            base.join(".pactignore"),
            "the outermost line that answers is the one to name"
        );

        // A folder with no `.pactignore` of its own is still covered.
        let middle = Ignore::inherited(&base, &base.join("packages"));
        assert!(middle.matches("node_modules"));

        // Nothing above the tree being loaded reaches into it.
        let alone = Ignore::inherited(&base.join("packages"), &base.join("packages/api"));
        assert!(alone.matches("node_modules"), "its own file still counts");
        let _ = std::fs::remove_dir_all(&base);
    }
}
