//! Loader policy: the small set of choices that are *conventions* rather than
//! *rules*, isolated so they can be changed without touching the Expansion Rule
//! itself (invariant F-1: no capability-affecting literal buried in the core).

use camino::Utf8Path;

/// Files that are documentation or tooling residue rather than specification.
/// Treating `README.md` as a field called `README` would be technically
/// consistent and practically absurd, so these are skipped.
const NON_SPEC_STEMS: &[&str] =
    &["readme", "license", "licence", "notice", "changelog", "contributing", "codeowners"];

/// Extensions parsed as structured documents.
const STRUCTURED: &[&str] = &["yaml", "yml", "json"];

/// Extensions read as prose.
const PROSE: &[&str] = &["md", "markdown"];

/// Extensions read as plain text values.
const PLAIN_TEXT: &[&str] = &["txt"];

/// Directory names never descended into.
const SKIP_DIRS: &[&str] =
    &["node_modules", "target", "__pycache__", "venv", ".venv", "dist", "build"];

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
            max_text_bytes: 4 * 1024 * 1024,
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
                "workspace", "agent", "skill", "suite", "catalog",
                // Added with the port/loop/context-policy kinds. A file named
                // after WHAT IT IS describes its folder, so
                // `ports/slack/port.yaml` is the port rather than a field
                // called `port` inside it.
                "port", "schedule", "loop", "interceptor", "context-policy", "state",
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
                "tool", "policy", "resource",
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
            payload_dirs: ["workspace", "assets", "references", "scripts", "documents"]
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
    pub fn is_ignored(&self, name: &str, is_dir: bool) -> bool {
        if name.starts_with('.') {
            return true;
        }
        if is_dir {
            return SKIP_DIRS.contains(&name);
        }
        let stem = name.rsplit_once('.').map_or(name, |(s, _)| s);
        NON_SPEC_STEMS.contains(&stem.to_ascii_lowercase().as_str())
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
    let digits_end = stem.find(|c: char| !c.is_ascii_digit()).unwrap_or(stem.len());
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
        assert_eq!(split_ordinal("2024"), (None, "2024"), "a bare number is a name");
        // The separator must be '-' or '_', so a name like `3d-model` is a
        // name, not step 3 of something called "d-model".
        assert_eq!(split_ordinal("3d-model"), (None, "3d-model"));
        assert_eq!(split_ordinal("01"), (None, "01"));
        assert_eq!(split_ordinal("01-"), (None, "01-"));
        assert_eq!(split_ordinal("v2-agent"), (None, "v2-agent"), "must start with digits");
    }

    #[test]
    fn documentation_files_are_not_fields() {
        let p = Policy::default();
        assert!(p.is_ignored("README.md", false));
        assert!(p.is_ignored("LICENSE", false));
        assert!(p.is_ignored(".hidden.yaml", false));
        assert!(p.is_ignored("node_modules", true));
        assert!(!p.is_ignored("instructions.md", false));
        assert!(!p.is_ignored("tools", true));
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
        assert!(!p.is_self_file("refund-desk", "learning"), "the same, for `learning.yaml`");
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

/// Patterns from a `.pactignore` file: one glob-ish pattern per line, `#` for
/// comments. Deliberately simple — `*` matches within a name, `/` is not
/// special, and there is no negation. An author who needs more than this is
/// solving the wrong problem.
#[derive(Debug, Clone, Default)]
pub struct Ignore {
    patterns: Vec<String>,
}

impl Ignore {
    /// Read `.pactignore` from a directory. Absent file means no patterns.
    pub fn load(dir: &Utf8Path) -> Self {
        let text = std::fs::read_to_string(dir.join(".pactignore")).unwrap_or_default();
        Self::parse(&text)
    }

    pub fn parse(text: &str) -> Self {
        Self {
            patterns: text
                .lines()
                .map(|l| l.split('#').next().unwrap_or("").trim().to_string())
                .filter(|l| !l.is_empty())
                .collect(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.patterns.is_empty()
    }

    pub fn matches(&self, name: &str) -> bool {
        self.patterns.iter().any(|p| glob_match(p, name))
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
}
