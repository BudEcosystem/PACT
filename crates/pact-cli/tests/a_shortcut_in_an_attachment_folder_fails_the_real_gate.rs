//! The exit code an author actually gets, from the binary that ships.
//!
//! `crates/pact-loader/tests/a_shortcut_inside_an_attachment_folder_is_refused_like_any_other.rs`
//! states its defect and its fix as `pact check` and `pact show` transcripts,
//! and every one of its assertions goes through
//! `Loader::with_policy(root, policy).load(...)` reading `Value::Payload.files`
//! and `Diagnostics::items()`. Nothing in this repository executed either
//! command over a payload shortcut — `grep -n 'Command\|CARGO_BIN_EXE' ` over
//! that file returns nothing, and the three `symlink-skipped` hits in
//! `crates/pact-cli/tests/discovery.rs` are all comments about ORDINARY-folder
//! links.
//!
//! That gap is not cosmetic, because the thing being sold is a **severity**,
//! and a severity is only visible from outside as an exit code. Mutating the
//! shared `symlink_skipped` helper from `Diagnostic::warning` to
//! `Diagnostic::note` left the whole `pact-loader` crate green — 204 lib tests
//! and every integration file, that 21-test file included — while the real gate
//! flipped:
//!
//! ```text
//! baseline: warning: '…/scripts/leak.txt' is a shortcut to somewhere else, so it was skipped.
//!           OK — ws loaded with 1 warning(s).                             EXIT=1
//! mutated:  note:    '…/scripts/leak.txt' is a shortcut to somewhere else, so it was skipped.
//!           OK — ws loaded cleanly (13 settings).                         EXIT=0
//! ```
//!
//! `--deny-warnings` counts warnings and nothing else. A library assertion that
//! two diagnostics have the same severity as each other cannot see that; this
//! file can.
//!
//! The named-pipe half is here for the same reason and one worse: it was green
//! from the shipped binary under no flags at all —
//!
//! ```text
//! $ mkfifo ws/skills/refund-policy/scripts/pipe.py
//! $ pact check ws --deny-warnings
//! OK — ws loaded cleanly (498 settings).                                  EXIT=0
//! $ pact show ws
//!   { "$file": "check_window.py", "contentType": "application/py", "sizeBytes": 235 },
//!   { "$file": "pipe.py",         "contentType": "application/py", "sizeBytes": 0 }
//! ```
//!
//! and `pact discover` gave two different `workspace-digest` values for the
//! tree with and without it, so the phantom is load-bearing on identity.
//!
//! # Mutations
//!
//! 1. `symlink_skipped` in `crates/pact-loader/src/lib.rs`:
//!    `Diagnostic::warning` → `Diagnostic::note`.
//!    **`a_payload_shortcut_fails_the_real_gate_under_deny_warnings` fails** on
//!    the exit code and on the `warning:` prefix.
//! 2. In `Loader::walk_payload`, drop the `Ok(m) if m.is_file()` arm so
//!    everything that is not a directory is carried as before.
//!    **`a_named_pipe_never_reaches_the_package_or_the_digest` fails** on all
//!    three of its assertions.
//! 3. In `Loader::load_path`, drop the `else if meta.is_file()` arm.
//!    **`a_named_pipe_at_the_top_of_an_ordinary_folder_does_not_hang_the_command`
//!    fails by timing out**, which is why it runs the child under a deadline
//!    and kills it rather than calling `output()`.

use std::io::Read;
use std::process::{Command, Stdio};

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A workspace with one skill whose `scripts/` holds one honest file.
struct Ws(std::path::PathBuf);

impl Ws {
    fn new(name: &str) -> Self {
        let base = std::env::temp_dir().join(format!(
            "pact-cli-payloadlink-{name}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&base);
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
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, body).unwrap();
        self
    }

    /// Returns false when the filesystem will not make a shortcut. Said out
    /// loud, because a skipped case must not read as a proved one.
    #[must_use]
    fn link(&self, rel: &str, target: &str) -> bool {
        let p = self.0.join(rel);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        #[cfg(unix)]
        let made = std::os::unix::fs::symlink(target, &p);
        #[cfg(not(unix))]
        let made: std::io::Result<()> = Err(std::io::Error::other("not unix"));
        if let Err(e) = made {
            eprintln!("SKIPPED (no shortcut on this filesystem, {rel}: {e}) — nothing proved");
            return false;
        }
        true
    }

    #[must_use]
    fn fifo(&self, rel: &str) -> bool {
        let p = self.0.join(rel);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        match Command::new("mkfifo").arg(&p).status() {
            Ok(s) if s.success() => true,
            other => {
                eprintln!(
                    "SKIPPED (no named pipe on this system, {rel}: {other:?}) — nothing proved"
                );
                false
            }
        }
    }

    fn path(&self) -> &str {
        self.0.to_str().unwrap()
    }
}

impl Drop for Ws {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// stdout, stderr and the exit code of one real command.
fn run(args: &[&str]) -> (String, String, i32) {
    let out = pact().args(args).output().expect("the binary runs");
    (
        String::from_utf8_lossy(&out.stdout).to_string(),
        String::from_utf8_lossy(&out.stderr).to_string(),
        out.status.code().unwrap_or(-1),
    )
}

#[test]
fn a_payload_shortcut_fails_the_real_gate_under_deny_warnings() {
    let ws = Ws::new("gate");
    if !ws.link("skills/refund-policy/scripts/leak.txt", "/etc/hostname") {
        return;
    }

    let (out, err, code) = run(&["check", ws.path(), "--deny-warnings"]);
    let said = format!("{out}{err}");

    // (a) The exit code. This is the whole guarantee, and it is the one thing a
    // library test cannot see.
    assert_ne!(
        code, 0,
        "a shortcut inside an attachment folder must fail `--deny-warnings`.\n{said}"
    );
    // (b) At WARNING severity, spelled out — the severity is what the flag
    // counts, and a note would print an almost identical line at exit 0.
    assert!(
        said.contains("warning:") && said.contains("is a shortcut to somewhere else"),
        "the line an author reads must be a `warning:`.\n{said}"
    );
    assert!(
        said.contains("rule: loader/symlink-skipped"),
        "and must name the rule.\n{said}"
    );
    // (c) And the link is not in the package the command prints.
    let (shown, _, _) = run(&["show", ws.path()]);
    assert!(
        !shown.contains("leak.txt"),
        "the shortcut must not reach the document `pact show` prints.\n{shown}"
    );
    assert!(
        shown.contains("check_window.py"),
        "while the honest script beside it still does.\n{shown}"
    );
}

#[test]
fn a_named_pipe_never_reaches_the_package_or_the_digest() {
    let ws = Ws::new("fifo");
    if !ws.fifo("skills/refund-policy/scripts/pipe.py") {
        return;
    }

    let (out, err, code) = run(&["check", ws.path(), "--deny-warnings"]);
    let said = format!("{out}{err}");
    assert_ne!(
        code, 0,
        "an entry that is not a file must fail `--deny-warnings` too — it used to \
         answer `OK — ws loaded cleanly (498 settings)` at exit 0.\n{said}"
    );
    assert!(
        said.contains("warning:") && said.contains("rule: loader/not-a-regular-file"),
        "the author must be told which entry was left out and why.\n{said}"
    );

    let (shown, _, _) = run(&["show", ws.path()]);
    assert!(
        !shown.contains("pipe.py"),
        "a named pipe is not a zero-byte file, and must not be in the document.\n{shown}"
    );

    // Load-bearing on identity: the phantom entry moved the workspace digest,
    // so a tree with one and a tree without one were two different workspaces.
    let clean = Ws::new("fifo-clean");
    let (a, _, _) = run(&["discover", ws.path()]);
    let (b, _, _) = run(&["discover", clean.path()]);
    let digest = |s: &str| {
        s.split("\"digest\"")
            .nth(1)
            .map(|t| t.split('"').nth(1).unwrap_or("").to_string())
    };
    assert_eq!(
        digest(&a),
        digest(&b),
        "the pipe must make no difference to what this workspace IS"
    );
    assert!(
        digest(&a).is_some(),
        "and there must be a digest to compare"
    );
}

#[test]
fn a_named_pipe_at_the_top_of_an_ordinary_folder_does_not_hang_the_command() {
    // `read_to_string` on a pipe nothing will ever write to does not return.
    // Measured before the fix: `timeout 20 pact check ws` → EXIT=124, no
    // output, 20s of wall clock. Run with a deadline and killed, because the
    // failure mode is a hang and `output()` would hang this test process too.
    //
    // The pipe's name clashes with nothing. It was `agents/keeper.yaml`, beside
    // the `agents/keeper/` folder, so two rules applied and the one reported
    // was whichever entry the filesystem listed second: green here, red on
    // GitHub's runner. The loader now reads folders sorted by name, which
    // made that clash report `loader/duplicate-field` every time.
    let ws = Ws::new("fifo-ordinary");
    if !ws.fifo("agents/stuck.yaml") {
        return;
    }

    let mut child = pact()
        .args(["check", ws.path()])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("the binary runs");

    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
    let status = loop {
        match child.try_wait().expect("the child can be waited on") {
            Some(s) => break Some(s),
            None if std::time::Instant::now() >= deadline => break None,
            None => std::thread::sleep(std::time::Duration::from_millis(50)),
        }
    };
    if status.is_none() {
        let _ = child.kill();
        let _ = child.wait();
        panic!(
            "`pact check` did not return within 20s — one named pipe in 'agents/' \
             stopped the whole checker, which is EXIT=124 to an author"
        );
    }

    let mut said = String::new();
    if let Some(mut e) = child.stderr.take() {
        let _ = e.read_to_string(&mut said);
    }
    if let Some(mut o) = child.stdout.take() {
        let _ = o.read_to_string(&mut said);
    }
    assert!(
        said.contains("loader/not-a-regular-file") && said.contains("stuck.yaml"),
        "and the entry it would not read is NAMED, like every other one.\n{said}"
    );
}
