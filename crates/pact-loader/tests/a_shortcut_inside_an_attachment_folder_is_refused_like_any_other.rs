//! A shortcut — and anything else that is not a file — is refused wherever it
//! sits, including inside `scripts/`, `documents/` and every other attachment
//! folder.
//!
//! `Loader::load_path` refuses a shortcut and says so, because (its own words)
//! a spec tree is a supply-chain surface and a link can point anywhere. The
//! walker that collects an ATTACHMENT folder — `scripts/`, `references/`,
//! `assets/`, `documents/`, `workspace/`, or any folder holding a
//! `.pactpayload` marker — never asked the question at all, so the same link
//! was quietly carried into the package.
//!
//! Measured on the shipped worked example, copied aside, with two shortcuts
//! added to `skills/refund-policy/scripts/` — `leak.txt -> /etc/hostname` and
//! `leakdir -> /etc`:
//!
//! ```text
//! $ pact check ws --deny-warnings
//! OK — ws loaded cleanly (498 settings).
//!
//! $ pact show ws
//!       "scripts": {
//!         "$payload": "skills/refund-policy/scripts",
//!         "files": [
//!           { "$file": "check_window.py", "contentType": "application/py",
//!             "sizeBytes": 235 },
//!           { "$file": "leak.txt", "contentType": "application/txt",
//!             "sizeBytes": 13 },
//!           { "$file": "leakdir", "contentType": "application/octet-stream",
//!             "sizeBytes": 4 }
//!         ]
//!       }
//! ```
//!
//! A path, a content type and a size for `/etc/hostname` and for `/etc`, in the
//! document, in its digest, under a green tick with warnings denied. Put the
//! identical link at the top of an ordinary folder and it is refused — this is
//! the whole of what that prints, not only the part this file is about:
//!
//! ```text
//! $ pact check ws
//! warning: 'ws/leak-at-top.yaml' is a shortcut to somewhere else, so it was
//!          skipped.
//!   --> ws/leak-at-top.yaml:1:1
//!   fix: Move or copy the real file into this folder. Shortcuts are ignored
//!        because they can point outside the project.
//!   rule: loader/symlink-skipped
//!
//! error: 'leak-at-top' is not something a workspace can have.
//!   --> ws/leak-at-top.yaml:1:1
//!   fix: Remove it, or use one of: name, pact-version, workspace-id, …
//!   rule: schema/unknown-field
//! 1 problem(s) and 1 warning(s) found in ws.
//! ```
//!
//! That asymmetry is the defect. One folder away, the same link, and one of the
//! two answers is nothing at all.
//!
//! The second line is deliberately NOT copied into attachment folders. An entry
//! at the top of an ordinary folder is a candidate SETTING, so a name nothing
//! recognises is an error about the name and the shortcut is only how the file
//! came to be unreadable. An attachment folder has no settings in it and no
//! vocabulary to be outside of — every name in it is legal — so a shortcut
//! there earns the warning and nothing more. What this file pins is that both
//! folders raise the same `loader/symlink-skipped`, with the same severity, the
//! same sentence and the same fix, and that neither carries the link.
//!
//! # The second half: "not a directory" is not "a file"
//!
//! Two rounds of this fix taught the walker to ask *is this a shortcut* and
//! *is this a folder*, and never *is this a file*. Everything that was not a
//! directory was pushed into the document. Measured on the shipped worked
//! example, from the shipped binary, with no flags:
//!
//! ```text
//! $ mkfifo ws/skills/refund-policy/scripts/pipe.py
//! $ pact check ws --deny-warnings
//! OK — ws loaded cleanly (498 settings).                              # EXIT=0
//!
//! $ pact show ws
//!   { "$file": "check_window.py", "contentType": "application/py", "sizeBytes": 235 },
//!   { "$file": "pipe.py",         "contentType": "application/py", "sizeBytes": 0 }
//! ```
//!
//! A plausible sibling of the real script, at a size that is a lie, inside the
//! workspace digest, under a green tick with warnings denied — the same
//! sentence and the same exit code this file's own header quotes as the
//! defect. And the same entry at the top of an ORDINARY folder did not answer
//! differently-but-safely, it HUNG: `mkfifo ws/agents/keeper.yaml; timeout 20
//! pact check ws` returned EXIT=124 with no output, because `read_to_string`
//! on a pipe nothing will ever write to does not return. Both halves are one
//! repair, `loader/not-a-regular-file`, asked in both walkers.
//!
//! # Decisions this file pins
//!
//! - **A link is refused by being a link, not by where it points.** A relative
//!   shortcut whose target sits safely inside the workspace is refused too.
//!   `load_path` has always refused every link regardless of target, and one
//!   rule an author can state in a sentence — *"shortcuts are not followed"* —
//!   is worth more than a resolve-and-compare that answers differently
//!   depending on where the workspace happens to be checked out.
//! - **A link to a FOLDER needs its own arm.** `DirEntry::file_type` does not
//!   follow, so a link to a directory answers `is_dir() == false` and was
//!   recorded as a single opaque file (`leakdir`, 4 bytes, above) rather than
//!   being refused.
//! - **One rule, one message.** The refusal is the SAME `loader/symlink-skipped`
//!   with the same sentence and the same fix, so moving a link into `scripts/`
//!   does not change what the author is told.
//! - **The escape hatch has to move with the rule, and it has to be
//!   INHERITED.** A `.pactignore` line silences an entry at the top of an
//!   ordinary folder; the payload walker never read one, so the new warning
//!   arrived with no way to answer it and no way to pass `--deny-warnings`. A
//!   per-directory read (`Ignore::load(dir)`) is not enough: it re-creates the
//!   identical asymmetry one folder up. Measured with one line `leak.yaml` in
//!   the workspace ROOT's `.pactignore` and the same link in `agents/` and in
//!   `skills/refund-policy/scripts/` — the ordinary one answered
//!   `loader/ignored-on-purpose` and the payload one still answered
//!   `loader/symlink-skipped`, `--deny-warnings` EXIT=1. It reads
//!   `Ignore::inherited` now, asked in the same order as `Loader::classify`
//!   asks it — BEFORE the dotfile skip, which is the order that makes a root
//!   line saying `.env` produce the EXP-10 deletion note for
//!   `scripts/.env` as it always has for `agents/keeper/.env`.
//! - **`follow_symlinks: true` still follows, in both places** — a link to a
//!   FILE is read, at the top of an ordinary folder and inside an attachment
//!   folder alike, at the size of the file it names.
//! - **Following is not a hole.** A followed link with nothing on the other end
//!   raises `loader/unreadable` rather than becoming a zero-byte entry; a
//!   followed link to a FOLDER raises `loader/not-a-regular-file` rather than
//!   becoming a 12,288-byte `application/octet-stream` "file". Both of those
//!   were silent, and both are reachable only through `Loader::with_policy` —
//!   which is exactly what an embedder such as `gaia-ai-runtime` uses, so they
//!   are a public-API hole rather than a shipped-binary one.
//!
//! # What following does NOT do, and why
//!
//! With `follow_symlinks: true` a link to a FOLDER inside an attachment folder
//! is not walked into. It is not carried as a file either — it is refused with
//! `loader/not-a-regular-file` and named.
//!
//! Not walking into it is a deliberate limit, not an oversight. Resolving the
//! target to decide `is_dir` reads better and does not terminate: two shortcuts
//! in one attachment folder both naming their own folder (`a -> .`, `b -> .`)
//! make the walk enumerate 2^32 paths. `MAX_DIR_DEPTH` bounds depth, not
//! breadth, and `loader/cycle` is **not** a guard here — it lives in
//! `Loader::load_dir` and works off the ancestor `stack` that `walk_payload`
//! does not have and is not given. Measured: that tree never returned; asking
//! the question of the directory ENTRY instead, so the walk descends only into
//! real directories (which cannot contain themselves), it finishes in 453µs.
//! `a_folder_that_holds_a_shortcut_to_itself_still_finishes` holds this, and it
//! is written so the ONE-shortcut case is asserted first: that one does stop, on
//! `loader/too-deep` after carrying 32 nested copies of the folder, so the wrong
//! version is an ordinary red in milliseconds rather than a suite that hangs.
//!
//! An earlier version of that test asserted the followed self-link WAS in the
//! file list — pinning a defect as correct, since the entry named a directory
//! and nothing that opened it could get anything but `EISDIR`. It now asserts
//! that the entry is refused and named, which is what the walk should have been
//! doing.
//!
//! # Where this is held from the real door
//!
//! Everything below drives `Loader::with_policy(...).load(...)` and reads
//! `Value::Payload.files`. The transcripts above are `pact check` and
//! `pact show`, and a library assertion cannot see the exit code an author
//! gets. `crates/pact-cli/tests/a_shortcut_in_an_attachment_folder_fails_the_real_gate.rs`
//! runs the shipped binary over a payload symlink and over a `mkfifo`'d entry
//! and asserts the non-zero exit under `--deny-warnings` — the guarantee this
//! file's `the_shipped_worked_examples_hold_no_shortcuts` justifies itself with
//! and could not itself prove.
//!
//! # Mutations, all eleven run
//!
//! Each was applied to `crates/pact-loader/src/lib.rs`, the two files re-run,
//! and the source restored (md5 checked back to
//! `8865e17dda8fbbc0e0d8b0ebb736a8d3`). The counts below are the ones the runs
//! printed, not the ones the edits were expected to print.
//!
//! In `Loader::walk_payload`:
//!
//! 1. Delete the `if is_link && !self.policy.follow_symlinks { … continue }`
//!    block. **`13 passed; 8 failed`** — `…to_a_file…`, `…to_a_folder…`,
//!    `…inside_the_attachment_folder…`, `…stays_inside_the_workspace…`,
//!    `…marked_as_an_attachment_folder…`, `…the_same_way_wherever_it_sits`,
//!    `the_severity_an_author_meets_is_a_warning_not_a_note` and
//!    `a_folder_that_holds_a_shortcut_to_itself_still_finishes`.
//! 2. Decide `is_dir` by resolving the link's TARGET —
//!    `if is_link { std::fs::metadata(&path)…is_dir() } else { file_type.is_dir() }`.
//!    **`19 passed; 2 failed`**: `a_folder_that_holds_a_shortcut_to_itself_still_finishes`
//!    (in 0.01s, on `loader/too-deep` and 32 nested copies) and
//!    `a_followed_shortcut_to_a_folder_is_refused_rather_than_carried`.
//! 3. Replace the `loader/ignored-on-purpose` note with a bare `continue`, so
//!    the payload skip is silent again. **`17 passed; 4 failed`**: the three
//!    `a_pactignore_line_*` tests and
//!    `a_dotfile_a_pactignore_line_names_is_reported_in_both_walkers`.
//! 4. `Ignore::inherited(&self.root, dir)` → `Ignore::load(dir)`, the
//!    non-inheriting read the first version of this fix shipped.
//!    **`18 passed; 3 failed`**:
//!    `a_pactignore_line_written_at_the_workspace_root_reaches_down_into_an_attachment_folder`,
//!    `a_pactignore_line_reaches_below_the_top_of_an_attachment_folder` and
//!    `a_dotfile_a_pactignore_line_names_is_reported_in_both_walkers`. Note
//!    that `a_pactignore_line_silences_a_shortcut_…_as_it_does_anywhere_else`
//!    stays GREEN under this, which is exactly why the line-beside-the-entry
//!    fixture could not tell the two implementations apart.
//! 5. Move `if name.starts_with('.') { continue; }` back ABOVE the
//!    `ignore.matching` block. **`20 passed; 1 failed`**:
//!    `a_dotfile_a_pactignore_line_names_is_reported_in_both_walkers` — the
//!    ordinary folder speaks and the attachment folder does not.
//! 6. Size a followed link with `entry.metadata()`, which does not traverse.
//!    **`19 passed; 2 failed`**:
//!    `following_shortcuts_when_asked_still_reaches_what_they_point_at` (the
//!    link path's length instead of the file's) and
//!    `a_followed_shortcut_to_nothing_is_reported_rather_than_sized_zero`.
//! 7. Drop the `Ok(m) if m.is_file()` arm, carrying everything that is not a
//!    directory as before. **`18 passed; 3 failed`**:
//!    `a_named_pipe_in_an_attachment_folder_is_not_carried_as_a_zero_byte_file`,
//!    `a_followed_shortcut_to_a_folder_is_refused_rather_than_carried` and
//!    `a_folder_that_holds_a_shortcut_to_itself_still_finishes` — plus
//!    `a_named_pipe_never_reaches_the_package_or_the_digest` in `pact-cli`.
//! 8. Turn the `Err(_) => { diags.push(unreadable_entry(&path)); continue }`
//!    arm back into a zero with the entry carried. **`20 passed; 1 failed`**:
//!    `a_followed_shortcut_to_nothing_is_reported_rather_than_sized_zero`.
//!
//! And in `Loader::load_path`:
//!
//! 9. Drop `&& !self.policy.follow_symlinks`, so the top of an ordinary folder
//!    refuses every link unconditionally. **`20 passed; 1 failed`**:
//!    `following_a_shortcut_at_the_top_of_an_ordinary_folder_still_reads_it`.
//! 10. Drop the `else if meta.is_file()` arm, sending everything that is not a
//!     directory to `load_file`. **`20 passed; 1 failed`**:
//!     `a_named_pipe_at_the_top_of_an_ordinary_folder_does_not_stop_the_loader`,
//!     and it failed **by TIMING OUT** — `finished in 20.00s` against 0.01s for
//!     every other run in this list. That is why it loads on a worker thread
//!     with a deadline rather than calling the loader on the test thread.
//!
//! And in `symlink_skipped`:
//!
//! 11. `Diagnostic::warning` → `Diagnostic::note`. **`16 passed; 5 failed`**
//!     here — the four `refused()` callers plus
//!     `the_severity_an_author_meets_is_a_warning_not_a_note` — and
//!     `a_payload_shortcut_fails_the_real_gate_under_deny_warnings` in
//!     `pact-cli`. Before the literal-severity assertion and that CLI file
//!     existed, this edit left the whole `pact-loader` crate green while the
//!     real `pact check --deny-warnings` flipped from EXIT=1 to EXIT=0.

use camino::{Utf8Path, Utf8PathBuf};
use pact_diag::{Diagnostics, Severity};
use pact_doc::{Node, Value};
use pact_loader::{Loader, policy::Policy};
use std::fs;
use std::io::Write;
use std::sync::atomic::{AtomicU32, Ordering};

static COUNTER: AtomicU32 = AtomicU32::new(0);

/// The one rule. There is not a second one for attachment folders.
const RULE: &str = "loader/symlink-skipped";

/// The rule for everything that is neither a folder nor an ordinary file.
const NOT_A_FILE: &str = "loader/not-a-regular-file";

/// The rule an author's `.pactignore` line produces when it removes something.
const IGNORED: &str = "loader/ignored-on-purpose";

/// Say something the default `cargo test` run actually shows.
///
/// `println!` and `eprintln!` are captured by the test harness and thrown away
/// for a test that passes, so a run that SKIPPED every meaningful case would
/// read as a clean pass. Writing to the process's own stderr goes around the
/// capture, which is the whole point: a skip has to be legible without anyone
/// having remembered to pass `--nocapture`.
fn announce(line: &str) {
    if let Ok(mut f) = fs::OpenOptions::new().write(true).open("/dev/stderr") {
        let _ = writeln!(f, "{line}");
    }
    eprintln!("{line}");
}

struct Tree(Utf8PathBuf);

impl Tree {
    /// A workspace with one skill, whose `scripts/` holds one honest file. The
    /// shortcut under test is added by each test on top of that.
    fn new(name: &str) -> Self {
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string()).join(
            format!("pact-payloadlink-{name}-{}-{n}", std::process::id()),
        );
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();
        let t = Self(base);
        t.file(
            "workspace.yaml",
            "name: desk-ws\ndescription: A workspace.\n",
        );
        t.file(
            "agents/keeper/agent.yaml",
            "name: Keeper\ndescription: Keeps things.\ninstructions: Keep things.\n",
        );
        t.file(
            "skills/refund-policy/SKILL.md",
            "---\ndescription: How refunds go.\n---\nCheck.\n",
        );
        t.file(
            "skills/refund-policy/scripts/check_window.py",
            "print('ok')\n",
        );
        t
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

    /// Make a shortcut at `rel` pointing at `target`.
    ///
    /// Returns false when the filesystem will not make one at all — a CI image
    /// on FAT/exFAT, or Windows without developer mode. The caller reports the
    /// skip in words rather than failing: a machine that cannot create a
    /// shortcut cannot be harmed by one either. The reason is written straight
    /// to stderr by [`announce`], so a skipped run cannot be mistaken for a
    /// clean one.
    #[must_use]
    fn link(&self, rel: &str, target: &str) -> bool {
        let p = self.0.join(rel);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        #[cfg(unix)]
        let made = std::os::unix::fs::symlink(target, &p);
        #[cfg(not(unix))]
        let made: std::io::Result<()> = Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "not unix",
        ));
        match made {
            Ok(()) => true,
            Err(e) => {
                announce(&format!(
                    "SKIPPED (this filesystem will not create a shortcut, \
                     {rel} -> {target}: {e}) — nothing in this file was proved"
                ));
                false
            }
        }
    }

    /// Make a NAMED PIPE at `rel` — an entry that is neither a folder nor an
    /// ordinary file, and the cheapest one a test can create.
    ///
    /// Shelled out to `mkfifo(1)` rather than linked against `libc`, because
    /// this crate has no `libc` dependency and adding one to make a test
    /// fixture is a supply-chain cost for a fixture. Returns false when the
    /// tool or the filesystem will not produce one, and says so out loud
    /// through [`announce`] for the same reason [`Tree::link`] does: a skipped
    /// run must not read as a clean one.
    #[must_use]
    fn fifo(&self, rel: &str) -> bool {
        let p = self.0.join(rel);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        let made = std::process::Command::new("mkfifo")
            .arg(p.as_str())
            .status();
        let ok = matches!(&made, Ok(s) if s.success());
        if !ok {
            announce(&format!(
                "SKIPPED (this system will not create a named pipe at {rel}: {made:?}) \
                 — nothing in this test was proved"
            ));
        }
        ok
    }

    fn load(&self) -> (Node, Diagnostics) {
        self.load_with(Policy::default())
    }

    fn load_with(&self, policy: Policy) -> (Node, Diagnostics) {
        let mut d = Diagnostics::new();
        let n = Loader::with_policy(self.0.clone(), policy)
            .load(&self.0, &mut d)
            .expect("the tree loads");
        d.sort();
        (n, d)
    }
}

impl Drop for Tree {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

/// Every file an attachment folder carries, by name, in the order the document
/// holds them.
fn payload_files(document: &Node, path: &[&str]) -> Vec<String> {
    let mut node = document;
    for step in path {
        node = node
            .get(step)
            .unwrap_or_else(|| panic!("the document has no '{step}' at {path:?}"));
    }
    match &node.value {
        Value::Payload(p) => p.files.iter().map(|f| f.path.clone()).collect(),
        other => panic!("{path:?} should be an attachment folder, it is {other:?}"),
    }
}

/// Every file the skill's `scripts/` attachment folder carries, by name.
fn script_files(document: &Node) -> Vec<String> {
    payload_files(document, &["skills", "refund-policy", "scripts"])
}

/// One entry of the skill's `scripts/` folder, WHOLE — so what the document
/// says about it (its content type, its size) can be asserted, not only that
/// its name is in a list.
fn payload_file(document: &Node, name: &str) -> pact_doc::FileRef {
    let node = document
        .get("skills")
        .and_then(|s| s.get("refund-policy"))
        .and_then(|s| s.get("scripts"))
        .expect("the document has a scripts folder");
    match &node.value {
        Value::Payload(p) => p
            .files
            .iter()
            .find(|f| f.path == name)
            .unwrap_or_else(|| {
                panic!(
                    "'{name}' is not in the package: {:?}",
                    p.files.iter().map(|f| &f.path).collect::<Vec<_>>()
                )
            })
            .clone(),
        other => panic!("scripts should be an attachment folder, it is {other:?}"),
    }
}

/// The claim, in one place: `name` is not in the package, and the author was
/// told why by the one rule.
fn refused(document: &Node, diags: &Diagnostics, name: &str) {
    let files = script_files(document);
    assert!(
        !files
            .iter()
            .any(|f| f == name || f.ends_with(&format!("/{name}"))),
        "'{name}' was carried into the package.\nfiles: {files:?}\ndiagnostics:\n{}",
        diags.render()
    );
    let spoken = diags
        .items()
        .iter()
        .find(|d| d.rule == RULE && d.message.contains(name));
    assert!(
        spoken.is_some(),
        "nothing said '{name}' was skipped, so it vanished in silence.\n\
         files: {files:?}\ndiagnostics:\n{}",
        diags.render()
    );
    assert_eq!(
        spoken.unwrap().fix,
        "Move or copy the real file into this folder. Shortcuts are ignored because they \
         can point outside the project.",
        "the fix an author is handed must be the one the rule has always given"
    );
    // The LITERAL severity, not "the same as the other one". The only severity
    // assertion this file used to make compared two Diagnostics that both came
    // out of the same `symlink_skipped()` call, so it was a tautology: the
    // helper could be downgraded to `Diagnostic::note` with the entire loader
    // crate still green, while the real `pact check --deny-warnings` flipped
    // from EXIT=1 to EXIT=0. That severity IS the gate.
    assert_eq!(
        spoken.unwrap().severity,
        Severity::Warning,
        "a skipped shortcut must be a WARNING — it is what makes `--deny-warnings` \
         refuse the workspace, and a note would let it through"
    );
}

/// The claim for an entry that is not a file: not in the package, and named.
fn refused_as_not_a_file(document: &Node, diags: &Diagnostics, name: &str) {
    let files = script_files(document);
    assert!(
        !files
            .iter()
            .any(|f| f == name || f.ends_with(&format!("/{name}"))),
        "'{name}' was carried into the package.\nfiles: {files:?}\ndiagnostics:\n{}",
        diags.render()
    );
    let spoken = diags
        .items()
        .iter()
        .find(|d| d.rule == NOT_A_FILE && d.message.contains(name));
    assert!(
        spoken.is_some(),
        "nothing said '{name}' was skipped, so it vanished in silence.\n\
         files: {files:?}\ndiagnostics:\n{}",
        diags.render()
    );
    assert_eq!(
        spoken.unwrap().severity,
        Severity::Warning,
        "same reason as the shortcut rule: the severity is what `--deny-warnings` reads"
    );
}

#[test]
fn a_shortcut_to_a_file_is_not_carried_into_the_package() {
    let t = Tree::new("file");
    if !t.link("skills/refund-policy/scripts/leak.txt", "/etc/hostname") {
        return;
    }
    let (doc, d) = t.load();
    refused(&doc, &d, "leak.txt");
    assert!(
        script_files(&doc).contains(&"check_window.py".to_string()),
        "the honest script beside it must still be carried.\nfiles: {:?}",
        script_files(&doc)
    );
}

#[test]
fn a_shortcut_to_a_folder_is_refused_too() {
    // The arm that is easy to miss: a link to a directory reports
    // `is_dir() == false` on the link itself, so it was recorded as one
    // opaque FILE rather than descended into.
    let t = Tree::new("folder");
    if !t.link("skills/refund-policy/scripts/leakdir", "/etc") {
        return;
    }
    let (doc, d) = t.load();
    refused(&doc, &d, "leakdir");
    let files = script_files(&doc);
    assert!(
        !files.iter().any(|f| f.starts_with("leakdir/")),
        "nothing from inside the linked folder may be carried either.\nfiles: {files:?}"
    );
}

#[test]
fn a_shortcut_in_a_folder_inside_the_attachment_folder_is_refused() {
    // The walker recurses, so the check has to hold at every depth, not only
    // at the top of the attachment folder.
    let t = Tree::new("nested");
    t.file(
        "skills/refund-policy/scripts/helpers/real.py",
        "print('real')\n",
    );
    if !t.link(
        "skills/refund-policy/scripts/helpers/leak.txt",
        "/etc/hostname",
    ) {
        return;
    }
    let (doc, d) = t.load();
    refused(&doc, &d, "leak.txt");
    let files = script_files(&doc);
    assert!(
        files.contains(&"helpers/real.py".to_string()),
        "the real file in the same nested folder must still be carried.\nfiles: {files:?}"
    );
}

#[test]
fn a_shortcut_that_stays_inside_the_workspace_is_refused_the_same_way() {
    // The stated decision: refused by BEING a link, not by where it points.
    // This one resolves to a file two folders up, safely inside the tree.
    let t = Tree::new("relative");
    if !t.link("skills/refund-policy/scripts/nearby.md", "../SKILL.md") {
        return;
    }
    let (doc, d) = t.load();
    refused(&doc, &d, "nearby.md");
}

#[test]
fn a_shortcut_in_a_folder_marked_as_an_attachment_folder_is_refused() {
    // An attachment folder is not only one of the five known names. Any folder
    // holding a `.pactpayload` marker is one, and it reaches the same walker,
    // so the refusal has to arrive there by the same route.
    let t = Tree::new("marker");
    t.file("resources/handbook/.pactpayload", "");
    t.file("resources/handbook/page.md", "# Page\n");
    if !t.link("resources/handbook/leak.txt", "/etc/hostname") {
        return;
    }
    let (doc, d) = t.load();

    let files = payload_files(&doc, &["resources", "handbook"]);
    assert_eq!(
        files,
        vec!["page.md".to_string()],
        "only the real page may be carried out of a marked folder.\ndiagnostics:\n{}",
        d.render()
    );
    let spoken = d
        .items()
        .iter()
        .find(|x| x.rule == RULE && x.message.contains("leak.txt"));
    assert!(
        spoken.is_some(),
        "a marked attachment folder must refuse a shortcut out loud too.\n{}",
        d.render()
    );
}

#[test]
fn the_same_shortcut_is_answered_the_same_way_wherever_it_sits() {
    // The asymmetry this file exists for. One link at the top of an ordinary
    // folder, one inside an attachment folder, same target — and the author
    // must be told the same thing about both, word for word.
    let ordinary = Tree::new("ordinary");
    if !ordinary.link("policies/leak.yaml", "/etc/hostname") {
        return;
    }
    let payload = Tree::new("payload");
    if !payload.link("skills/refund-policy/scripts/leak.yaml", "/etc/hostname") {
        return;
    }

    let (_, a) = ordinary.load();
    let (_, b) = payload.load();
    let one = a
        .items()
        .iter()
        .find(|d| d.rule == RULE)
        .expect("the ordinary folder refuses it");
    let two = b
        .items()
        .iter()
        .find(|d| d.rule == RULE)
        .unwrap_or_else(|| {
            panic!(
                "the attachment folder said nothing.\ndiagnostics:\n{}",
                b.render()
            )
        });

    assert_eq!(
        one.severity, two.severity,
        "the same rule cannot change severity by folder"
    );
    // The sentence, with the one thing that legitimately differs — the path it
    // names — taken off the front of both. Both halves must actually name a
    // path, or this would be comparing two empty strings and passing.
    let sentence = |m: &str| {
        m.rsplit_once("' ")
            .unwrap_or_else(|| panic!("the message must name the path it is about: {m}"))
            .1
            .to_string()
    };
    assert_eq!(
        sentence(&one.message),
        "is a shortcut to somewhere else, so it was skipped.",
        "the sentence being compared has to be the real one: {}",
        one.message
    );
    assert_eq!(
        sentence(&one.message),
        sentence(&two.message),
        "the same rule must say the same sentence in both folders.\n\
         ordinary: {}\npayload:  {}",
        one.message,
        two.message
    );
    assert_eq!(
        one.fix, two.fix,
        "the same rule must give the same fix in both folders"
    );
}

#[test]
fn the_severity_an_author_meets_is_a_warning_not_a_note() {
    // The severity is the whole guarantee, and nothing held it.
    //
    // `the_same_shortcut_is_answered_the_same_way_wherever_it_sits` compared
    // `one.severity` with `two.severity` — two Diagnostics both produced by the
    // same `symlink_skipped()` call, so it is a tautology that cannot fail.
    // Downgrading that one helper from `Diagnostic::warning` to
    // `Diagnostic::note` left the entire pact-loader crate green — 204 lib
    // tests and every integration file — while the real shipped gate flipped:
    //
    //   baseline: warning: '…/scripts/leak.txt' is a shortcut … EXIT=1
    //   mutated:  note:    '…/scripts/leak.txt' is a shortcut … EXIT=0
    //
    // `--deny-warnings` counts warnings. A note is not counted, so the whole
    // fix becomes a line of output nobody's CI reads.
    let t = Tree::new("severity");
    if !t.link("skills/refund-policy/scripts/leak.txt", "/etc/hostname") {
        return;
    }
    let (_, d) = t.load();
    let spoken = d
        .items()
        .iter()
        .find(|x| x.rule == RULE)
        .unwrap_or_else(|| panic!("nothing said it was skipped.\n{}", d.render()));
    assert_eq!(
        spoken.severity,
        Severity::Warning,
        "a skipped shortcut is a WARNING. `--deny-warnings` counts warnings and \
         nothing else, so at any lower severity a workspace carrying a shortcut \
         passes the release gate."
    );
}

#[test]
fn a_pactignore_line_silences_a_shortcut_in_an_attachment_folder_as_it_does_anywhere_else() {
    // The escape hatch, which has to move with the rule. `.pactignore` is what
    // the loader offers an author who meant it; a warning with no way to answer
    // it is a `--deny-warnings` gate nobody can pass.
    //
    // The line sits BESIDE the entry here, which is the easy case. The two
    // tests after this one are the ones that bite: this fixture passes
    // identically whether the walker reads `Ignore::load(dir)` or
    // `Ignore::inherited(&self.root, dir)`, so on its own it cannot tell a
    // working escape hatch from one that only works in the folder it is
    // written in.
    let ordinary = Tree::new("ignored-ordinary");
    ordinary.file("policies/.pactignore", "leak.yaml\n");
    if !ordinary.link("policies/leak.yaml", "/etc/hostname") {
        return;
    }
    let payload = Tree::new("ignored-payload");
    payload.file("skills/refund-policy/scripts/.pactignore", "leak.yaml\n");
    if !payload.link("skills/refund-policy/scripts/leak.yaml", "/etc/hostname") {
        return;
    }

    let (_, a) = ordinary.load();
    assert!(
        !a.items().iter().any(|x| x.rule == RULE),
        "an ordinary folder has always let a .pactignore line answer this.\n{}",
        a.render()
    );

    let (doc, b) = payload.load();
    assert!(
        !b.items().iter().any(|x| x.rule == RULE),
        "an attachment folder must let the same line answer it.\n{}",
        b.render()
    );
    let files = script_files(&doc);
    assert_eq!(
        files,
        vec!["check_window.py".to_string()],
        "silencing it must not mean carrying it after all.\nfiles: {files:?}"
    );
}

#[test]
fn a_pactignore_line_written_at_the_workspace_root_reaches_down_into_an_attachment_folder() {
    // The placement that separates a working escape hatch from a decorative
    // one. `.pactignore` is the file every author has already met, and the file
    // they have met is INHERITED: they write it once, at the top, and it
    // governs the tree.
    //
    // With the per-directory read the walker had, this is what a workspace
    // answered — one root line, the same link in an ordinary folder and in an
    // attachment folder:
    //
    //   note:    'ws/agents/leak.yaml' takes no part in this workspace …
    //   warning: 'ws/skills/refund-policy/scripts/leak.yaml' is a shortcut … skipped.
    //   OK — ws loaded with 1 warning(s).                              EXIT=1
    //
    // The unsuppressable `--deny-warnings` this whole fix exists to remove, put
    // back one folder up by the fix's own escape hatch.
    let t = Tree::new("ignored-from-root");
    t.file(".pactignore", "leak.yaml\n");
    if !t.link("agents/leak.yaml", "/etc/hostname") {
        return;
    }
    if !t.link("skills/refund-policy/scripts/leak.yaml", "/etc/hostname") {
        return;
    }

    let (doc, d) = t.load();
    assert!(
        !d.items().iter().any(|x| x.rule == RULE),
        "one line at the top of the workspace must answer for BOTH folders.\n{}",
        d.render()
    );
    let files = script_files(&doc);
    assert_eq!(
        files,
        vec!["check_window.py".to_string()],
        "the ignored link must not be carried after all.\nfiles: {files:?}"
    );

    // And the suppression is SPOKEN, in the attachment folder as in the
    // ordinary one. `.pactignore` is a deletion operator (EXP-10), so a
    // suppression nobody can see is the silent loss this file exists to close,
    // reached by the escape hatch instead of by the walk.
    let spoken: Vec<&str> = d
        .items()
        .iter()
        .filter(|x| x.rule == IGNORED)
        .map(|x| x.message.as_str())
        .collect();
    assert!(
        spoken.iter().any(|m| m.contains("agents/leak.yaml")),
        "the ordinary folder must name what the line removed.\n{}",
        d.render()
    );
    assert!(
        spoken
            .iter()
            .any(|m| m.contains("scripts/leak.yaml") && m.contains("leak.yaml")),
        "the attachment folder must name what the line removed too.\n{}",
        d.render()
    );
    assert!(
        spoken.iter().all(|m| m.contains(".pactignore")),
        "the record must name the FILE the line was written in, which with an \
         inherited .pactignore is not the folder the entry sits in.\n{}",
        d.render()
    );
}

#[test]
fn a_pactignore_line_reaches_below_the_top_of_an_attachment_folder() {
    // The other half of "inherited": down the tree, not only into it. An
    // attachment folder's OWN `.pactignore` has to govern its subfolders, or an
    // author who writes one at the top of `scripts/` finds it stops working one
    // directory in — which is the same surprise, one level smaller.
    //
    // With the per-directory read the walker re-ran `Ignore::load(dir)` at each
    // recursion level, so `scripts/.pactignore` covered `scripts/` and nothing
    // below it: `scripts/leak.yaml` was noted and `scripts/helpers/leak.yaml`
    // still warned, from one line.
    let t = Tree::new("ignored-nested");
    t.file("skills/refund-policy/scripts/.pactignore", "leak.yaml\n");
    t.file(
        "skills/refund-policy/scripts/helpers/real.py",
        "print('real')\n",
    );
    if !t.link("skills/refund-policy/scripts/leak.yaml", "/etc/hostname") {
        return;
    }
    if !t.link(
        "skills/refund-policy/scripts/helpers/leak.yaml",
        "/etc/hostname",
    ) {
        return;
    }

    let (doc, d) = t.load();
    assert!(
        !d.items().iter().any(|x| x.rule == RULE),
        "a line at the top of the attachment folder must cover its subfolders too.\n{}",
        d.render()
    );
    let mut files = script_files(&doc);
    files.sort();
    assert_eq!(
        files,
        vec!["check_window.py".to_string(), "helpers/real.py".to_string()],
        "the real files stay, both links go.\nfiles: {files:?}"
    );
    assert!(
        d.items()
            .iter()
            .any(|x| x.rule == IGNORED && x.message.contains("helpers/leak.yaml")),
        "the nested entry the line removed must be named.\n{}",
        d.render()
    );
}

#[test]
fn a_pactignore_line_takes_an_ordinary_file_out_of_an_attachment_folder_and_says_so() {
    // The rider this fix carries, stated as a test rather than left implicit.
    //
    // Giving the payload walker `.pactignore` did not only give it an escape
    // hatch for shortcuts — it made `.pactignore` able to delete ORDINARY
    // CONTENT from an attachment folder, which it could not do before. A
    // knowledge corpus's `documents/` is a knowledge corpus; a line removing a
    // document from it moves the workspace digest. Measured on
    // `examples/answers-from-documents` with `leave.md` in
    // `knowledge/staff-handbook/documents/.pactignore`: `pact check
    // --deny-warnings` said "loaded cleanly (21 settings)" at EXIT=0 while
    // `pact discover` moved the digest from `sha256:17393f6f…` to
    // `sha256:bf3b29ab…`.
    //
    // EXP-10's two governance halves (`.pactignore` as a typed IR node in
    // `canonical.json`, and inside `workspace-digest`) are unmet, and the
    // module header says so. What IS met is that the deletion is not silent,
    // and this is what holds that: the note must be PRESENT and must name the
    // entry, the pattern and the file the pattern was written in. Asserting
    // only that `loader/symlink-skipped` is ABSENT — which is all the test
    // above did — leaves the whole note deletable with the crate green.
    let t = Tree::new("ignored-content");
    t.file("skills/refund-policy/scripts/.pactignore", "secret.py\n");
    t.file(
        "skills/refund-policy/scripts/secret.py",
        "print('secret')\n",
    );

    let (doc, d) = t.load();
    let files = script_files(&doc);
    assert_eq!(
        files,
        vec!["check_window.py".to_string()],
        "the line takes the file out of the package.\nfiles: {files:?}"
    );
    let spoken = d
        .items()
        .iter()
        .find(|x| x.rule == IGNORED && x.message.contains("secret.py"))
        .unwrap_or_else(|| {
            panic!(
                "a document left out of the package is a DELETION, and EXP-10 requires \
                 it be named. Nothing was said.\n{}",
                d.render()
            )
        });
    assert!(
        spoken.message.contains("secret.py") && spoken.message.contains(".pactignore"),
        "the record names the entry and the file the line was written in: {}",
        spoken.message
    );
    assert_eq!(
        spoken.severity,
        Severity::Note,
        "a note, not a warning — the author asked for this and `--deny-warnings` \
         counts warnings, so a warning would make an intended suppression a gate failure"
    );
}

#[test]
fn a_dotfile_a_pactignore_line_names_is_reported_in_both_walkers() {
    // The two walkers have to ask the dotfile question and the `.pactignore`
    // question in the SAME ORDER, or the same pattern produces the EXP-10
    // deletion record on one side and nothing at all on the other.
    //
    // `Loader::classify` asks `.pactignore` first (lib.rs) and the dotfile skip
    // second, inside `Policy::is_ignored`. `walk_payload` asked them the other
    // way round, so measured on one workspace with a root `.pactignore` holding
    // `.env` and a `.env` in each of `agents/keeper/` and
    // `skills/refund-policy/scripts/`, the ordinary one produced the note and
    // the attachment one produced nothing — one folder apart, same pattern.
    let t = Tree::new("dot-order");
    t.file(".pactignore", ".env\n");
    t.file("agents/keeper/.env", "A=1\n");
    t.file("skills/refund-policy/scripts/.env", "A=1\n");

    let (doc, d) = t.load();
    let named: Vec<&str> = d
        .items()
        .iter()
        .filter(|x| x.rule == IGNORED)
        .map(|x| x.message.as_str())
        .collect();
    assert!(
        named.iter().any(|m| m.contains("agents/keeper/.env")),
        "the ordinary folder has always reported this.\n{}",
        d.render()
    );
    assert!(
        named.iter().any(|m| m.contains("scripts/.env")),
        "the attachment folder must report it too — same pattern, same workspace, \
         one folder apart.\n{}",
        d.render()
    );
    // Suppressed, not carried: the order change must not turn a dotfile into
    // payload content.
    assert_eq!(
        script_files(&doc),
        vec!["check_window.py".to_string()],
        "a dotfile is still not carried into the package"
    );
}

#[test]
fn following_shortcuts_when_asked_still_reaches_what_they_point_at() {
    // The escape hatch stays open on the payload side. An author who sets
    // `follow_symlinks` gets the file the shortcut names, read as itself.
    let t = Tree::new("follow");
    t.file("elsewhere/tools/helper.py", "print('helper')\n");
    if !t.link(
        "skills/refund-policy/scripts/linked.py",
        "../../../elsewhere/tools/helper.py",
    ) {
        return;
    }

    let policy = Policy {
        follow_symlinks: true,
        ..Policy::default()
    };
    let (doc, d) = t.load_with(policy);
    let files = script_files(&doc);
    assert!(
        files.contains(&"linked.py".to_string()),
        "with following on, the linked file must be carried.\nfiles: {files:?}\n{}",
        d.render()
    );
    assert!(
        !d.items().iter().any(|x| x.rule == RULE),
        "nothing may be reported as skipped when following is on.\n{}",
        d.render()
    );

    // …and carried HONESTLY. `DirEntry::metadata` does not traverse a link, so
    // asking it here sizes the entry as the length of the PATH the link holds
    // rather than of the file it names — 34 bytes for
    // `../../../elsewhere/tools/helper.py` against a 16-byte target here, a
    // number that goes into the document and into the workspace digest. This
    // file had no size assertion at all, so that whole traversal could be
    // reverted with the entire loader crate green.
    let body = std::fs::read(t.0.join("elsewhere/tools/helper.py")).unwrap();
    let carried = payload_file(&doc, "linked.py");
    assert_eq!(
        carried.size_bytes,
        body.len() as u64,
        "the size recorded must be the file's, not the link path's ({} bytes)",
        "../../../elsewhere/tools/helper.py".len()
    );
}

#[test]
fn a_followed_shortcut_to_nothing_is_reported_rather_than_sized_zero() {
    // With following on, a link with nothing on the other end used to become a
    // phantom entry: the size lookup failed, `unwrap_or(0)` turned the failure
    // into a zero, and the document carried `gone.py` at 0 bytes with NO
    // diagnostic — while the identical dangling link at the top of an ordinary
    // folder raised `loader/unreadable`. Reachable only through
    // `Loader::with_policy`, which is exactly what an embedder uses.
    let t = Tree::new("dangle-follow");
    if !t.link("skills/refund-policy/scripts/gone.py", "./no-such-file.py") {
        return;
    }
    let policy = Policy {
        follow_symlinks: true,
        ..Policy::default()
    };
    let (doc, d) = t.load_with(policy);
    let files = script_files(&doc);
    assert!(
        !files.contains(&"gone.py".to_string()),
        "a link to nothing is not a zero-byte file.\nfiles: {files:?}\n{}",
        d.render()
    );
    assert!(
        d.items()
            .iter()
            .any(|x| x.rule == "loader/unreadable" && x.message.contains("gone.py")),
        "the same rule the top of an ordinary folder raises must be raised here.\n{}",
        d.render()
    );
}

#[test]
fn a_followed_shortcut_to_a_folder_is_refused_rather_than_carried() {
    // `DirEntry::file_type` does not follow, so a link to a directory answers
    // `is_dir() == false`. With following on it therefore fell through to the
    // file arm and was carried as a `FileRef` — measured at 12,288 bytes,
    // `application/octet-stream`, with no diagnostic. Nothing can open that: a
    // runtime that tries gets EISDIR, and the size is an inode's.
    //
    // It is still NOT walked into — that is what makes the walk terminate, and
    // `a_folder_that_holds_a_shortcut_to_itself_still_finishes` holds it.
    let t = Tree::new("dirlink-follow");
    t.file("elsewhere/tools/helper.py", "print('helper')\n");
    if !t.link(
        "skills/refund-policy/scripts/toolsdir",
        "../../../elsewhere/tools",
    ) {
        return;
    }
    let policy = Policy {
        follow_symlinks: true,
        ..Policy::default()
    };
    let (doc, d) = t.load_with(policy);
    refused_as_not_a_file(&doc, &d, "toolsdir");
    let files = script_files(&doc);
    assert!(
        !files.iter().any(|f| f.starts_with("toolsdir/")),
        "and nothing from inside it is carried either.\nfiles: {files:?}"
    );
}

#[test]
fn a_named_pipe_in_an_attachment_folder_is_not_carried_as_a_zero_byte_file() {
    // The third question. The walker asked "is it a shortcut?" and "is it a
    // folder?" and never "is it a file?", so a named pipe entered the document
    // as a plausible zero-byte sibling of the real script — under DEFAULT
    // policy, from the shipped binary, with `--deny-warnings` green. The
    // entries are load-bearing on workspace identity: `pact discover` gave two
    // different digests for the two trees.
    let t = Tree::new("fifo-payload");
    if !t.fifo("skills/refund-policy/scripts/pipe.py") {
        return;
    }
    let (doc, d) = t.load();
    refused_as_not_a_file(&doc, &d, "pipe.py");
    assert!(
        script_files(&doc).contains(&"check_window.py".to_string()),
        "the honest script beside it must still be carried.\nfiles: {:?}",
        script_files(&doc)
    );
}

#[test]
fn a_named_pipe_at_the_top_of_an_ordinary_folder_does_not_stop_the_loader() {
    // The same class, one folder up, and there it did not answer
    // differently-but-safely — it HUNG. `load_path` asked `is_dir()` and sent
    // everything else to `read_file`, which calls `read_to_string` on a pipe
    // nothing will ever write to. Measured on the shipped binary:
    // `timeout 20 pact check ws` returned EXIT=124, no output, 20s of wall
    // clock, the whole checker stopped by one entry in a folder it was handed.
    //
    // Loaded on a worker thread with a deadline, because the failure mode of
    // the bug this pins is a HANG: called directly, the wrong version does not
    // fail this test, it stops the whole suite.
    //
    // The pipe's name clashes with nothing: `agents/keeper.yaml` beside the
    // tree's `agents/keeper/` is also `loader/duplicate-field`, which the
    // loader (reading folders by name) reports instead.
    let t = Tree::new("fifo-ordinary");
    if !t.fifo("agents/stuck.yaml") {
        return;
    }
    let root = t.0.clone();
    let (tx, rx) = std::sync::mpsc::channel();
    let worker = std::thread::spawn(move || {
        let mut d = Diagnostics::new();
        let n = Loader::new(root.clone()).load(&root, &mut d);
        let _ = tx.send((n.is_some(), d.render()));
    });
    let answered = rx.recv_timeout(std::time::Duration::from_secs(20));
    let (loaded, rendered) = answered.unwrap_or_else(|_| {
        // The thread is parked in `read` on a pipe and will never return, so it
        // is deliberately leaked rather than joined. The assertion is the point.
        panic!(
            "loading did not return within 20s — one named pipe in 'agents/' \
             stopped the loader, exactly as `timeout 20 pact check` measured EXIT=124"
        )
    });
    drop(worker);
    assert!(loaded, "the rest of the workspace still loads.\n{rendered}");
    assert!(
        rendered.contains(NOT_A_FILE) && rendered.contains("stuck.yaml"),
        "and the entry it would not read is NAMED, like every other one.\n{rendered}"
    );
}

#[test]
fn following_a_shortcut_at_the_top_of_an_ordinary_folder_still_reads_it() {
    // The other half of "in both places", which nothing in this repository
    // held: `load_path` is where following was already honoured, and the
    // shared refusal now sits behind the same flag on both sides of it. If
    // the flag is ever dropped from that side, an embedder who asked for
    // following silently stops getting whole agents.
    let t = Tree::new("follow-ordinary");
    t.file(
        "elsewhere/mirror.yaml",
        "name: Mirror\ndescription: Mirrors things.\ninstructions: Mirror things.\n",
    );
    if !t.link("agents/mirror.yaml", "../elsewhere/mirror.yaml") {
        return;
    }

    let policy = Policy {
        follow_symlinks: true,
        ..Policy::default()
    };
    let (doc, d) = t.load_with(policy);
    assert!(
        !d.items().iter().any(|x| x.rule == RULE),
        "nothing may be reported as skipped when following is on.\n{}",
        d.render()
    );
    let named = doc
        .get("agents")
        .and_then(|a| a.get("mirror"))
        .and_then(|m| m.get("name"))
        .unwrap_or_else(|| {
            panic!(
                "the linked agent never reached the document.\n{}",
                d.render()
            )
        });
    assert_eq!(
        named.as_str(),
        Some("Mirror"),
        "the linked agent must be read as itself, not as a shortcut"
    );
}

#[test]
fn a_folder_that_holds_a_shortcut_to_itself_still_finishes() {
    // The guard on the fix itself, in two steps, deliberately in this order.
    //
    // ONE shortcut naming its own folder is the cheap, loud version: deciding
    // `is_dir` by resolving the link's TARGET makes the walk descend through
    // its own folder 32 times over and stop on `loader/too-deep`, carrying 32
    // copies of every file in it. That is a fast, ordinary assertion failure,
    // and it is first so that the wrong version is caught before the next step
    // can hang a suite.
    //
    // TWO of them is the real regression, and it does not stop at all: 2^32
    // paths to enumerate. `MAX_DIR_DEPTH` bounds depth, not breadth, and
    // `loader/cycle` does not reach here — it is `load_dir`'s guard and works
    // off an ancestor stack `walk_payload` has never had. Asking the directory
    // ENTRY instead, so only real directories are descended into and real
    // directories cannot contain themselves, both are a few hundred
    // microseconds.
    //
    // Both settings of the flag, because refusing shortcuts is what saves the
    // first case and only the second ever had the hole.
    //
    // The file list is the SAME under both settings, and that is the point of
    // this version. An earlier one asserted that with following on the entry
    // `a` WAS in the list — pinning a defect as correct: `a` is a link to a
    // DIRECTORY, so the entry claimed a content type and a size for a folder
    // inode and nothing that opened it could get anything but EISDIR. It is now
    // refused with `loader/not-a-regular-file` and named, which is what the
    // walk should always have done. Not walked into either way, which is what
    // makes this finish at all.
    let expected = || -> Vec<String> { vec!["check_window.py".to_string()] };

    for follow in [false, true] {
        let one = Tree::new(if follow {
            "loop1-follow"
        } else {
            "loop1-refuse"
        });
        if !one.link("skills/refund-policy/scripts/a", ".") {
            return;
        }
        let policy = Policy {
            follow_symlinks: follow,
            ..Policy::default()
        };
        let (doc, d) = one.load_with(policy.clone());
        assert_eq!(
            script_files(&doc),
            expected(),
            "a folder holding a shortcut to itself must be collected once, and the \
             shortcut carried neither as a file nor as a folder (following {follow}).\n{}",
            d.render()
        );
        assert!(
            !d.items().iter().any(|x| x.rule == "loader/too-deep"),
            "nothing is nested here, so reaching the depth limit means the walk \
             went round a shortcut (following {follow}).\n{}",
            d.render()
        );
        // Left out is not the same as unmentioned: whichever rule answers, the
        // entry is NAMED. With following off that is `loader/symlink-skipped`;
        // with it on, `loader/not-a-regular-file`.
        let rule = if follow { NOT_A_FILE } else { RULE };
        assert!(
            d.items()
                .iter()
                .any(|x| x.rule == rule && x.message.contains("scripts/a")),
            "the shortcut must be named by {rule} (following {follow}).\n{}",
            d.render()
        );

        let two = Tree::new(if follow {
            "loop2-follow"
        } else {
            "loop2-refuse"
        });
        if !two.link("skills/refund-policy/scripts/a", ".") {
            return;
        }
        if !two.link("skills/refund-policy/scripts/b", ".") {
            return;
        }
        let started = std::time::Instant::now();
        let (doc, d) = two.load_with(policy);
        assert!(
            started.elapsed() < std::time::Duration::from_secs(20),
            "loading took {:?} with following {follow} — the walk is not bounded",
            started.elapsed()
        );
        assert_eq!(
            script_files(&doc),
            expected(),
            "two shortcuts to the same folder must not multiply its contents \
             (following {follow}).\n{}",
            d.render()
        );
    }
}

#[test]
fn an_ordinary_attachment_folder_says_nothing_about_shortcuts() {
    // Control. Every honest workspace has attachment folders, and a word about
    // shortcuts on a folder that has none is the noise that teaches an author
    // to stop reading the output.
    let t = Tree::new("clean");
    t.file(
        "skills/refund-policy/scripts/helpers/also_real.py",
        "print('also')\n",
    );
    t.dir("skills/refund-policy/scripts/empty");
    let (doc, d) = t.load();
    assert!(
        !d.items().iter().any(|x| x.rule == RULE),
        "a folder with no shortcuts in it must stay silent.\n{}",
        d.render()
    );
    let files = script_files(&doc);
    assert_eq!(
        files,
        vec![
            "check_window.py".to_string(),
            "helpers/also_real.py".to_string()
        ],
        "every real file must still be carried, in path order"
    );
}

#[test]
fn the_shipped_worked_examples_hold_no_shortcuts() {
    // Control, and the blast radius stated as a test: the fix turns a shortcut
    // in an attachment folder into a WARNING, and the release gate runs
    // `--deny-warnings` over every shipped example. If one ever grows a
    // shortcut, this says so here rather than in the gate.
    let root = Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples");
    let mut found = Vec::new();
    walk(&root, &mut found);
    assert!(
        found.is_empty(),
        "a shipped example contains a shortcut: {found:?}"
    );

    fn walk(dir: &Utf8Path, found: &mut Vec<String>) {
        let Ok(read) = fs::read_dir(dir) else { return };
        for e in read.flatten() {
            let Ok(name) = e.file_name().into_string() else {
                continue;
            };
            let p = dir.join(&name);
            match e.file_type() {
                Ok(t) if t.is_symlink() => found.push(p.to_string()),
                Ok(t) if t.is_dir() => walk(&p, found),
                _ => {}
            }
        }
    }
}
