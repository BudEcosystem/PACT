//! An entry skipped because its name COLLIDES WITH A CONVENTION — a tool's, or
//! a project's — is either loaded or reported. It is never silently absent.
//!
//! The qualifier is load-bearing and was added after the claim was measured
//! against the tree rather than read. One skip decided by a name is still
//! silent and is **not** covered here: a name that is not valid UTF-8, dropped
//! by a bare `continue` at `crates/pact-loader/src/lib.rs:897` before any of
//! this file's rules are consulted. See "Consciously not covered" below for the
//! measurement.
//!
//! `Policy::is_ignored` refuses to descend into seven directory names —
//! `node_modules`, `target`, `__pycache__`, `venv`, `.venv`, `dist`, `build` —
//! and its one production caller answered with a bare `continue`. So an author
//! who calls their agent "build" loses it, and is told the workspace is clean.
//! Measured on a two-agent workspace holding nothing but
//! `agents/build/agent.yaml` and `agents/keeper/agent.yaml`:
//!
//! ```text
//! $ pact check <ws>
//! OK — <ws> loaded cleanly (8 settings).
//!
//! $ pact show <ws>
//! {
//!   "name": "repro",
//!   "description": "Reproducing B2.",
//!   "agents": {
//!     "keeper": {
//!       "name": "Keeper",
//!       "description": "Keeps things.",
//!       "instructions": "Keep things."
//!     }
//!   }
//! }
//! ```
//!
//! "build" is gone. Not renamed, not reported, not mentioned — gone, with a
//! green tick over it. That is thesis T7 ("no silent loss anywhere") broken in
//! the quietest possible way, and it happens at any depth and to any kind:
//! agents, tools, skills, questions, ports.
//!
//! The same `continue` swallowed a second, narrower case, measured on a
//! workspace holding a perfectly good `tools/license.yaml` that an agent's
//! `uses:` names:
//!
//! ```text
//! error: 'uses' names 'license', and there is no such entry in `tools:`,
//!        `skills:` or `knowledge:`.
//!   fix: Nothing is declared there yet. Add a file `tools/license.yaml`
//! ```
//!
//! — the author told to write the file they are looking at, with no message
//! anywhere naming the file that was thrown away.
//!
//! # The distinction this file pins
//!
//! **Only a name a person could have meant speaks.** That one criterion decides
//! every case here, and getting it wrong in either direction is a bug this file
//! is meant to catch.
//!
//! - A FOLDER speaks when its name is an ordinary English noun —
//!   `build`, `dist`, `target`. Behind one of those there might really be an
//!   agent. It stays SILENT when no author has ever typed it: `node_modules`,
//!   `__pycache__`, `venv`. Nothing of the author's can be behind those, so the
//!   line could only ever be noise — and the noise was measured, at five
//!   `__pycache__` warnings on this repository's own Python adapter and
//!   `--deny-warnings` at exit 1 on any tree where anybody had run `npm
//!   install` or `python -m venv venv`.
//! - A FILE speaks when a documentation stem is in the form settings are
//!   written in (`license.yaml` — nobody writes a readme as a YAML document),
//!   or when a documentation stem is anywhere BELOW the top of the workspace
//!   (`agents/keeper/notice.md` — a file somebody wrote inside a folder of
//!   settings). It stays silent for `README.md`, `LICENSE` and `CHANGELOG.md`
//!   **at the top of the workspace**, which is where those names mean what they
//!   say and where every real project has them.
//!
//! Dotfiles stay silent because they are tooling's own business. A
//! `.pactignore` match does NOT stay silent — see
//! `a_line_the_author_wrote_is_a_deletion_and_says_so` — but it is a NOTE, so
//! it neither reads as a mistake nor fails `--deny-warnings`. The control tests
//! below are what stop a later change from widening any of these into noise, or
//! narrowing one back into silence.
//!
//! # Consciously not covered
//!
//! - A `node_modules` inside a **payload** directory (`references/`,
//!   `documents/`, …). Payloads walk `Loader::walk_payload`, which never calls
//!   `is_ignored` — so no name is ever a reason to skip anything there, the
//!   folder is already IN the document, and there is nothing silent to report.
//!   That is the part that keeps this gap honest, and it is still true. The
//!   sentence that used to follow it — "carries every non-dotfile verbatim" —
//!   is not: `walk_payload` now reads an inherited `.pactignore` and refuses
//!   anything that is not an ordinary file or a folder (a shortcut, a named
//!   pipe, a socket), each with its own record. See
//!   `a_shortcut_inside_an_attachment_folder_is_refused_like_any_other`. None
//!   of the three is a NAME rule, which is why this gap is unchanged.
//! - `.venv` in the skip lists is unreachable: the `starts_with('.')` test
//!   fires first, so it is skipped as a dotfile and stays silent. That is
//!   tracked separately as D5 and is deliberately unchanged here. `venv`
//!   without the dot now gets the same silence for the same reason, which is
//!   pinned in `policy::tests`.
//! - **EXP-10 is only half met.** A `.pactignore` entry now produces a record
//!   naming the entry and the pattern, which is what EXP-11 and FR-8.1.1 ask
//!   for. The other two halves of EXP-10 — `.pactignore` as a typed IR node in
//!   `canonical.json`, and inside `workspace-digest` — are not done, and
//!   `LoadReport` cannot yet carry the line EXP-10 actually specifies
//!   (`report.rs` LOAD-14 reserves the slot). The record is a diagnostic in the
//!   meantime.
//! - **A name that is not valid UTF-8 is still dropped in silence**, and this
//!   is the one hole that contradicts the headline above rather than qualifying
//!   it. `crates/pact-loader/src/lib.rs:897` (`classify`) and `:769`
//!   (`walk_payload`) both do `let Ok(name) = entry.file_name().into_string()
//!   else { continue };` with no `Diagnostics` touched. Measured on a workspace
//!   holding `agents/keeper/` beside a Latin-1 `agents/caf\xe9-agent/agent.yaml`
//!   — what a zip from Windows or macOS, or a `LANG=C` shell, produces:
//!
//!   ```text
//!   $ pact check <ws> --deny-warnings
//!   OK — <ws> loaded cleanly (8 settings).
//!   EXIT=0
//!   $ pact show <ws>          # agents: keeper only, stderr 0 bytes
//!   ```
//!
//!   That is B2's own reproduction, one skip-reason over. The payload half is
//!   worse in kind: a `references/` folder holding `good.txt` and a Latin-1
//!   `r\xe9sum\xe9.txt` loads "cleanly" with a `files:` manifest naming
//!   `good.txt` alone, so a filename's ENCODING silently moves a digest the
//!   loader promises is reproducible on any machine. Not fixed here because it
//!   is a different seam — an encoding boundary in three walkers, needing its
//!   own rule id and a `#[cfg(unix)]` fixture — and not a name-collision
//!   policy. Recorded in `docs/remediation/B2-skipdirs-silent-delete.md`
//!   under "What remains open".
//! - **The document still does not hold a skipped FOLDER.** A
//!   `pact_doc::UNLOADED` marker there turns the warning into `error: 'dist' is
//!   not something a workspace can have` for every repository that keeps its
//!   build output beside its workspace — measured, and strictly worse than the
//!   silence it replaces. A skipped FILE below the top of the workspace DOES
//!   get the marker, because a name in `tools:` is referenced and a folder name
//!   is not; see `a_setting_named_like_a_readme_is_not_just_deleted`.
//!
//! # Mutations
//!
//! **1. The diagnostic.** In `Loader::classify`
//! (`crates/pact-loader/src/lib.rs`), replace the whole `match reason` with the
//! bare `continue` the code used to have. Without it,
//! `a_folder_a_tool_would_have_named_is_not_just_deleted`,
//! `it_speaks_at_any_depth`, `every_name_a_tool_claims_is_reported_not_deleted`,
//! `a_setting_named_like_a_readme_is_not_just_deleted` and
//! `writing_inside_the_tree_is_not_just_deleted` all fail, and every other test
//! in the workspace stays green — including the controls below, and including
//! `policy::tests`, which pins the reasons at the seam and cannot see whether
//! anybody says them out loud.
//!
//! **2. The wording.** Replace the warning's sentence with `"'{dir}' had
//! something skipped, because some folders normally hold files a tool wrote
//! rather than anything you did."` — the same rule, the same span, no name. It
//! has to go red, and the reason it nearly did not is worth keeping: the
//! workspace path is interpolated into every message, so with the tree named
//! `pact-skipdir-build-…` (as it was), `d.message.contains("build")` was true of
//! ANY message mentioning ANY path in that tree, and this mutation left
//! `a_folder_a_tool_would_have_named_is_not_just_deleted` GREEN. Every assertion
//! about a message now goes through `Tree::tidy`, which takes the workspace path
//! out first, and the trees are named so that no label contains a name under
//! test. Measured after that change: the same mutation fails
//! `a_folder_a_tool_would_have_named_is_not_just_deleted`,
//! `every_name_a_tool_claims_is_reported_not_deleted` and
//! `it_speaks_at_any_depth`. **It leaves all three CLI tests green** — see the
//! module doc of
//! `crates/pact-cli/tests/a_folder_the_checker_skips_is_named_on_the_way_past.rs`
//! for why, and for what the sentence-level claim is therefore held by.
//!
//! **3. The split.** Move `node_modules`, `__pycache__` and `venv` back onto
//! `SPEAKING_SKIP_DIRS`. `a_folder_only_a_tool_ever_makes_is_skipped_without_a_word`
//! fails; nothing else does, which is the whole reason it exists. Before it,
//! the suite had silence controls for documentation files and for dotfiles and
//! none for a folder, so the noise regression could be — and was — reintroduced
//! with a green suite. The shipped-examples gate cannot see it either:
//!
//! ```text
//! $ find examples -type d \( -name __pycache__ -o -name node_modules \
//!       -o -name target -o -name venv -o -name dist -o -name build \) | wc -l
//! 0
//! ```
//!
//! **4. The place.** Make `Policy::is_ignored` answer `Ignored::Documentation`
//! for a prose documentation stem at every depth, as it did for a release.
//! `writing_inside_the_tree_is_not_just_deleted` fails and
//! `a_readme_is_still_skipped_without_a_word` — which now places its files only
//! where a project's own writing actually lives — stays green.
//!
//! **5. The suppression record.** Restore the bare `continue` on a
//! `.pactignore` match. `a_line_the_author_wrote_is_a_deletion_and_says_so`
//! fails; `saying_you_meant_it_stops_the_warning_and_does_not_double_report`
//! stays green, because silencing the two skip rules is exactly what the line
//! is for and is not what was wrong with it.

use camino::Utf8PathBuf;
use pact_diag::{Diagnostics, Severity};
use pact_doc::Node;
use pact_loader::Loader;
use std::fs;
use std::sync::atomic::{AtomicU32, Ordering};

static COUNTER: AtomicU32 = AtomicU32::new(0);

/// The two rules this file is about.
const FOLDER: &str = "loader/folder-skipped-by-name";
const FILE: &str = "loader/file-skipped-by-name";

/// The rule a `.pactignore` line answers with, and the one it must not.
const IGNORED_ON_PURPOSE: &str = "loader/ignored-on-purpose";

/// Every folder name that is skipped AND said out loud. Read from the policy
/// module itself, so a name moved between the two lists without a thought about
/// the message is a red test rather than a new silent deletion.
use pact_loader::policy::{SPEAKING_SKIP_DIRS, TOOL_ONLY_DIRS};

struct Tree(Utf8PathBuf);

impl Tree {
    /// `label` must not contain any name under test: the workspace path is
    /// interpolated into every message, so a tree called `…-build-…` would make
    /// `message.contains("build")` true whatever the message said. `tidy` below
    /// takes the path out again, and this is the belt to its braces.
    fn new(label: &str) -> Self {
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
            .join(format!("pact-skipped-{label}-{}-{n}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();
        fs::write(
            base.join("workspace.yaml"),
            "name: desk-ws\ndescription: A workspace.\n",
        )
        .unwrap();
        let t = Self(base);
        t.agent("keeper", "Keeper");
        t
    }

    /// One perfectly ordinary agent, so every tree here has something that
    /// loads and the assertions below are about the entry under test alone.
    fn agent(&self, dir: &str, display: &str) -> &Self {
        self.file(
            &format!("agents/{dir}/agent.yaml"),
            &format!("name: {display}\ndescription: Does a thing.\ninstructions: Do the thing.\n"),
        )
    }

    fn file(&self, rel: &str, body: &str) -> &Self {
        let p = self.0.join(rel);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, body).unwrap();
        self
    }

    fn load(&self) -> (Node, Diagnostics) {
        let mut d = Diagnostics::new();
        let n = Loader::new(self.0.clone())
            .load(&self.0, &mut d)
            .expect("the tree loads");
        d.sort();
        (n, d)
    }

    /// The same sentence with the workspace's own path taken out of it.
    ///
    /// Every assertion about a message goes through this. The path a message
    /// quotes ends in the entry that was skipped, so a message that names the
    /// entry still names it afterwards — but a message that names only the
    /// FOLDER ABOVE it no longer accidentally passes on the temp directory's
    /// name. Only what the loader chose to say survives.
    fn tidy(&self, s: &str) -> String {
        s.replace(self.0.as_str(), "<ws>")
    }

    /// The claim, as an effect on the real document: `needle` reached the
    /// document, or some diagnostic names the entry it was written in. Never
    /// neither.
    fn loaded_or_reported(&self, document: &str, diags: &Diagnostics, needle: &str, entry: &str) {
        let reached = document.contains(needle);
        let reported = diags
            .items()
            .iter()
            .any(|d| self.tidy(&d.message).contains(entry));
        assert!(
            reached || reported,
            "'{entry}' is neither in the document nor in any diagnostic.\n\
             document: {document}\n\
             diagnostics:\n{}",
            self.tidy(&diags.render())
        );
    }
}

impl Drop for Tree {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn a_folder_a_tool_would_have_named_is_not_just_deleted() {
    // The reproduction, exactly. An agent whose job is running builds, in the
    // folder a person would name it.
    let t = Tree::new("first");
    t.file(
        "agents/build/agent.yaml",
        "name: Build Agent\ndescription: Runs builds.\ninstructions: Build things.\n",
    );

    let (node, diags) = t.load();
    let document = node.to_json().to_string();

    // The other agent is untouched — this is a tree that otherwise works.
    assert!(
        document.contains("Keeper"),
        "the control agent vanished too: {document}"
    );

    t.loaded_or_reported(&document, &diags, "Runs builds.", "build");

    // It was skipped, so it has to have been reported. The rule id first.
    let d = diags
        .items()
        .iter()
        .find(|d| d.rule == FOLDER)
        .unwrap_or_else(|| panic!("no '{FOLDER}' diagnostic:\n{}", t.tidy(&diags.render())));

    // A warning, not an error: the tree still loads, and refusing every
    // workspace that happens to contain a `target/` would be worse than the
    // silence it replaces.
    assert_eq!(
        d.severity,
        Severity::Warning,
        "skipping a folder is a warning, not an error.\n{}",
        t.tidy(&diags.render())
    );

    // It has to name the entry, or the reader cannot find it. Asserted with the
    // workspace path taken out, so the temp directory cannot answer for the
    // message — see `Tree::tidy`.
    let said = t.tidy(&d.message);
    assert!(
        said.contains("build"),
        "the message must name the folder that was skipped: {said:?}\n{}",
        t.tidy(&diags.render())
    );
    // And it must point at the folder itself, not at the folder above it.
    assert!(
        said.contains("<ws>/agents/build"),
        "the message must quote the whole path of the skipped folder: {said:?}"
    );
    assert!(
        d.span.file.as_str().ends_with("build"),
        "the diagnostic must point at the folder that was skipped, not '{}'.\n{}",
        d.span.file,
        t.tidy(&diags.render())
    );

    // The fix, asserted separately from the rule id, and typeable by someone
    // who does not write code: the two things they can actually do about it.
    assert!(
        d.fix.contains(".pactignore"),
        "the fix must say how to mean it deliberately: {:?}",
        d.fix
    );
    assert!(
        d.fix.contains("rename") || d.fix.contains("Rename"),
        "the fix must say how to keep the folder: {:?}",
        d.fix
    );
}

#[test]
fn every_name_a_tool_claims_is_reported_not_deleted() {
    // Not just `build`. Every name on the SPEAKING list, through a real tree,
    // because the unit test beside the lists cannot tell whether the caller
    // says anything — a caller that warned about `build` and `dist` alone would
    // leave it green. The silent list has its own control below, and the two
    // together are what stop the line moving in either direction unnoticed.
    for name in SPEAKING_SKIP_DIRS {
        let t = Tree::new("each-name");
        t.file(
            &format!("agents/{name}/agent.yaml"),
            "name: A\ndescription: Runs the thing.\ninstructions: Run it.\n",
        );

        let (node, diags) = t.load();
        let document = node.to_json().to_string();
        t.loaded_or_reported(&document, &diags, "Runs the thing.", name);

        let said = diags
            .items()
            .iter()
            .find(|d| d.rule == FOLDER)
            .map(|d| t.tidy(&d.message))
            .unwrap_or_else(|| {
                panic!(
                    "'{name}' was skipped with no '{FOLDER}':\n{}",
                    t.tidy(&diags.render())
                )
            });
        assert!(
            said.contains(name),
            "the message for '{name}' does not name it: {said:?}"
        );
    }
}

#[test]
fn it_speaks_at_any_depth() {
    // Not just at the top. The skip lists are consulted for every directory the
    // Expansion Rule expands, so the loss happens wherever a person nests one.
    let t = Tree::new("deeper");
    t.file(
        "agents/keeper/tools/dist/tool.yaml",
        "description: Ships the thing.\nconnect: https://example.invalid/ship\n",
    );

    let (node, diags) = t.load();
    let document = node.to_json().to_string();
    t.loaded_or_reported(&document, &diags, "Ships the thing.", "dist");

    assert!(
        diags
            .items()
            .iter()
            .any(|d| d.rule == FOLDER && t.tidy(&d.message).contains("dist")),
        "a 'dist' folder three levels down went unreported:\n{}",
        t.tidy(&diags.render())
    );
}

#[test]
fn a_setting_named_like_a_readme_is_not_just_deleted() {
    // The narrower half of the same silence. `tools/license.yaml` is a tool
    // called `license` — nobody writes a licence as a YAML document — and it
    // was dropped so completely that the only message the author got was one
    // telling them to create the file they had written.
    let t = Tree::new("settings-file");
    t.file(
        "tools/license.yaml",
        "description: Prints the licence terms.\n",
    );

    let (node, diags) = t.load();
    let document = node.to_json().to_string();
    t.loaded_or_reported(&document, &diags, "Prints the licence terms.", "license");

    let d = diags
        .items()
        .iter()
        .find(|d| d.rule == FILE)
        .unwrap_or_else(|| panic!("no '{FILE}' diagnostic:\n{}", t.tidy(&diags.render())));
    assert_eq!(
        d.severity,
        Severity::Warning,
        "the tree still loads, so this is a warning"
    );

    let said = t.tidy(&d.message);
    assert!(
        said.contains("license"),
        "the message must name the file: {said:?}"
    );
    assert!(
        said.contains("<ws>/tools/license.yaml"),
        "the message must quote the whole path of the skipped file: {said:?}"
    );
    // Both ways out, and both typeable: rename it, or save it as prose.
    assert!(
        d.fix.contains("rename") || d.fix.contains("Rename"),
        "the fix must say how to keep the setting: {:?}",
        d.fix
    );
    assert!(
        d.fix.contains("license.md"),
        "the fix must say what to do if it really is documentation: {:?}",
        d.fix
    );
    // The third way out, which this rule's `fix:` did not name for a release
    // while the module doc of `pact-loader` claimed both rules did. It is the
    // right answer for a genuine `notice.json` an author wants left out, and it
    // was the one the author could not find.
    assert!(
        d.fix.contains(".pactignore"),
        "the fix must say how to mean it deliberately: {:?}",
        d.fix
    );

    // CHK-12, one mistake one message. The file is skipped, so its NAME is
    // contributed as the `pact_doc::UNLOADED` placeholder an unreadable file
    // already becomes — otherwise every `uses: [license]` in the tree dangles
    // and the author is told to create the file they are looking at.
    assert!(
        document.contains("license"),
        "the name has to resolve, or the warning above arrives underneath an \
         error telling the author to write this very file: {document}"
    );
}

#[test]
fn a_readme_is_still_skipped_without_a_word() {
    // The control that pins the distinction — and it pins it only where it
    // holds. `README.md` AT THE TOP OF THE WORKSPACE genuinely is not a setting,
    // every real project has one, and warning about it would put a line of
    // noise on every honest tree.
    //
    // Every file here is at the top on purpose. The version of this test that
    // shipped with B2 also placed `agents/keeper/LICENSE`, which made it assert
    // that a documentation stem is silent EVERYWHERE — and the design generalised
    // "silent for a project README" into "silent for an authored prose setting"
    // on the strength of it. That case has moved to
    // `writing_inside_the_tree_is_not_just_deleted`, where it now has to speak.
    let t = Tree::new("prose");
    t.file("README.md", "# The desk\n\nHow to use this workspace.\n")
        .file("LICENSE", "MIT\n")
        .file("CONTRIBUTING.md", "Open a pull request.\n")
        .file("notice.txt", "Third-party notices.\n")
        .file("CHANGELOG.md", "## 0.1\n");

    let (_node, diags) = t.load();
    assert!(
        diags.items().is_empty(),
        "documentation files at the top of a workspace must be skipped in \
         silence, but the loader said:\n{}",
        t.tidy(&diags.render())
    );
}

#[test]
fn writing_inside_the_tree_is_not_just_deleted() {
    // B2 verbatim, one file-kind over — and the half the first fix left open.
    //
    // Four sibling `.md` files of identical shape in ONE ordinary folder. Before
    // this, exactly one of them was answered: `escalation.md` became a field and
    // the checker named it, while `notice.md`, `changelog.md` and
    // `contributing.md` — same folder, same extension, same author, same
    // afternoon — took no part in the document and produced no error, no warning
    // and no mention. `pact show` on the same tree had no trace of any of the
    // three.
    //
    // `escalation.md` is the control, and it is here rather than in a test of
    // its own because it is what makes the other three a CONTRADICTION rather
    // than a policy: a loader that answers for one file in a folder and not for
    // its neighbour is not being quiet, it is being inconsistent.
    let t = Tree::new("writing-below");
    for stem in ["escalation", "notice", "changelog", "contributing"] {
        t.file(
            &format!("agents/keeper/handover/{stem}.md"),
            "Hand off after 14 days to the duty manager.\n",
        );
    }

    let (node, diags) = t.load();
    let document = node.to_json().to_string();

    // The control reached the document. If it did not, this tree is broken for
    // some other reason and the three assertions below prove nothing.
    assert!(
        document.contains("escalation"),
        "the control file did not load, so this test is not measuring what it \
         says it measures: {document}"
    );

    for stem in ["notice", "changelog", "contributing"] {
        t.loaded_or_reported(&document, &diags, stem, stem);
        let d = diags
            .items()
            .iter()
            .find(|d| d.rule == FILE && t.tidy(&d.message).contains(stem))
            .unwrap_or_else(|| {
                panic!(
                    "'{stem}.md' was skipped with no '{FILE}':\n{}",
                    t.tidy(&diags.render())
                )
            });
        assert_eq!(
            d.severity,
            Severity::Warning,
            "the tree still loads, so this is a warning"
        );
        let said = t.tidy(&d.message);
        assert!(
            said.contains(&format!("<ws>/agents/keeper/handover/{stem}.md")),
            "the message must quote the whole path of the skipped file: {said:?}"
        );
        // And the way out has to be typeable. "Save it as `notice.md`" is not,
        // because it already IS `notice.md`.
        assert!(
            d.fix.contains(".pactignore"),
            "the fix must say how to mean it deliberately: {:?}",
            d.fix
        );
        assert!(
            d.fix.contains("top of the workspace"),
            "the fix must say where this name does mean writing about the \
             project: {:?}",
            d.fix
        );
    }
}

#[test]
fn a_folder_only_a_tool_ever_makes_is_skipped_without_a_word() {
    // The control this suite did not have, and whose absence is why the noise
    // shipped. There were silence controls for documentation files and for
    // dotfiles and none at all for a folder, so a workspace that merely
    // CONTAINED the output of `npm install`, `cargo build` or `python -m venv
    // venv` newly failed `--deny-warnings` at exit 1 — with advice ("rename it
    // to something else") that is meaningless for `node_modules` and
    // destructive for `venv` — and the whole suite stayed green.
    //
    // The shipped-examples gate cannot see this either: no example tree holds
    // any of these names, so `the_examples_stay_clean_under_deny_warnings`
    // measures nothing about them.
    // WRITTEN OUT, not read from `TOOL_ONLY_DIRS`. Measured: with the list
    // driving the loop, the mutation that puts these three names back on the
    // speaking list empties `TOOL_ONLY_DIRS`, the loop runs zero times, and this
    // test passes with nothing built and nothing asserted. A control that reads
    // the thing it is controlling is not a control.
    const MADE_BY_A_TOOL: &[&str] = &["node_modules", "__pycache__", "venv"];
    let t = Tree::new("tool-made");
    for name in MADE_BY_A_TOOL {
        t.file(&format!("{name}/x.txt"), "written by a tool\n");
        t.file(&format!("agents/keeper/{name}/y.txt"), "and again\n");
    }

    // And the list is still the list: a name added to `TOOL_ONLY_DIRS` without
    // being added here would be a new silence nothing measures.
    for name in TOOL_ONLY_DIRS {
        assert!(
            MADE_BY_A_TOOL.contains(name),
            "'{name}' was made silent and this control was not told about it"
        );
    }

    let (_node, diags) = t.load();
    assert!(
        diags.items().is_empty(),
        "a folder no author ever names must be skipped in silence — a warning \
         there can never rescue anything, because there is never anything \
         behind it. The loader said:\n{}",
        t.tidy(&diags.render())
    );
}

#[test]
fn a_dotfile_is_still_skipped_without_a_word() {
    // The second control. Dotfiles are tooling's own business and the author
    // did not write them as settings. This also covers `.venv`, which reaches
    // the dot test before it ever reaches `SKIP_DIRS` (D5) and must therefore
    // stay silent for now.
    let t = Tree::new("hidden");
    t.file(".gitignore", "target\n")
        .file(".venv/pyvenv.cfg", "home = /usr\n");

    let (_node, diags) = t.load();
    assert!(
        diags.items().is_empty(),
        "hidden entries must be skipped in silence, but the loader said:\n{}",
        t.tidy(&diags.render())
    );
}

#[test]
fn saying_you_meant_it_stops_the_warning_and_does_not_double_report() {
    // The fix the diagnostic tells the reader to type, and what it must and
    // must not do. A `.pactignore` entry is a stated intent, so the two
    // skipped-by-name rules go quiet — it is the way to SILENCE the warning,
    // not a second way to earn one alongside it.
    //
    // What it must NOT do is vanish, and that half is
    // `a_line_the_author_wrote_is_a_deletion_and_says_so` below. This test
    // asserted `diags.items().is_empty()` when B2 shipped, which made the
    // repair for EXP-10 a red test.
    let t = Tree::new("meant-it");
    t.file("agents/.pactignore", "build\n")
        .file(
            "agents/build/agent.yaml",
            "name: Build Agent\ndescription: Runs builds.\ninstructions: Build things.\n",
        )
        .file(".pactignore", "license.yaml\n")
        .file("license.yaml", "description: not a setting after all\n");

    let (_node, diags) = t.load();
    assert!(
        !diags
            .items()
            .iter()
            .any(|d| d.rule == FOLDER || d.rule == FILE),
        "an entry the author listed in '.pactignore' must not ALSO be told off \
         for the name it has:\n{}",
        t.tidy(&diags.render())
    );
    // Nothing that reads as a mistake, and nothing that fails the gate.
    assert!(
        !diags.items().iter().any(|d| d.severity != Severity::Note),
        "a '.pactignore' entry is what the author asked for, so nothing above a \
         note may be said about it:\n{}",
        t.tidy(&diags.render())
    );
}

#[test]
fn a_line_the_author_wrote_is_a_deletion_and_says_so() {
    // EXP-10, EXP-11 and FR-8.1.1. `.pactignore` was the loader's one remaining
    // unreported deletion, and B2 moved it to the front of the loop, made it the
    // remedy printed under the new warning, and shipped the first test in the
    // repository that REQUIRED its silence.
    //
    // Measured then, on this tree: `pact check` printed *"loaded cleanly"* at
    // exit 0 and `pact show` printed a document the whole agent is simply not
    // in — which `docs/20-ARCHITECTURE-R5.md` §EXP-10 names verbatim as "a
    // deletion operator the blast-radius classifier cannot see".
    //
    // So it is reported, and the record names both halves EXP-10 asks for: the
    // ENTRY and the PATTERN. A note rather than a warning, because the author
    // asked for it and `--deny-warnings` counts warnings — the record has to be
    // visible without turning an intended suppression into a gate failure.
    let t = Tree::new("said-so");
    t.file("agents/.pactignore", "ghost\n").file(
        "agents/ghost/agent.yaml",
        "name: Ghost\ndescription: Does the payments.\ninstructions: Pay.\n",
    );

    let (node, diags) = t.load();
    let document = node.to_json().to_string();
    assert!(
        !document.contains("Does the payments."),
        "the entry is supposed to be gone from the document: {document}"
    );

    let d = diags
        .items()
        .iter()
        .find(|d| d.rule == IGNORED_ON_PURPOSE)
        .unwrap_or_else(|| {
            panic!(
                "an agent left the document and nothing said so — no \
                 '{IGNORED_ON_PURPOSE}':\n{}",
                t.tidy(&diags.render())
            )
        });
    assert_eq!(
        d.severity,
        Severity::Note,
        "the author asked for this, so it must not read as a mistake and must \
         not fail --deny-warnings"
    );
    let said = t.tidy(&d.message);
    assert!(
        said.contains("<ws>/agents/ghost"),
        "the record must name the ENTRY that was suppressed: {said:?}"
    );
    assert!(
        said.contains("ghost") && said.contains(".pactignore"),
        "the record must name the PATTERN and the file it was written in: {said:?}"
    );
}

#[test]
fn one_line_at_the_top_answers_for_the_whole_tree() {
    // The escape hatch the warning advertises has to be usable, and for the two
    // names guaranteed to recur it was not: `Ignore::load` read the
    // `.pactignore` of one directory and nothing merged a parent's patterns, so
    // silencing `node_modules` cost one file per occurrence and the gate stayed
    // red until every one had been written. Measured on a realistic JavaScript
    // layout — `node_modules` at the top and under three packages — a single
    // line in the workspace's own `.pactignore` left four of the five still
    // warning.
    //
    // `dist` is used here rather than `node_modules` because `dist` is on the
    // SPEAKING list, so an inheritance failure shows up as a warning rather
    // than as nothing at all.
    let t = Tree::new("one-line");
    t.file(".pactignore", "dist\n")
        .file("dist/out.txt", "built\n")
        .file("agents/keeper/dist/out.txt", "built\n")
        .file("agents/keeper/tools/shipper/dist/out.txt", "built\n");

    let (_node, diags) = t.load();
    assert!(
        !diags.items().iter().any(|d| d.rule == FOLDER),
        "one line at the top of the workspace must answer for every folder \
         under it, the way the only file of this shape anybody has met does:\n{}",
        t.tidy(&diags.render())
    );
    // And every one of the three is still accounted for, three levels apart.
    assert_eq!(
        diags
            .items()
            .iter()
            .filter(|d| d.rule == IGNORED_ON_PURPOSE)
            .count(),
        3,
        "inheriting the line must not cost the record of what it removed:\n{}",
        t.tidy(&diags.render())
    );
}
