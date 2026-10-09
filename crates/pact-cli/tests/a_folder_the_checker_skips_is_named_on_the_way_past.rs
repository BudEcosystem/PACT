//! The command an author actually runs says a folder was dropped.
//!
//! `agents/build/agent.yaml` beside `agents/keeper/agent.yaml` is a whole agent
//! the loader will not read, because `build` is on the list of folder names
//! build tools fill in themselves. Measured before the fix, on exactly that
//! workspace:
//!
//! ```text
//! $ pact check <ws>
//! OK — <ws> loaded cleanly (8 settings).
//! EXIT=0
//! ```
//!
//! Nothing named the agent. Nothing named the folder. The word was *cleanly*.
//! Thesis T7 — no silent loss anywhere — with a green tick over it.
//!
//! This drives the real binary rather than `Loader::load`, because "the author
//! is told" is a claim about the command: the loader's own tests can watch a
//! `Diagnostics` fill up and still miss a command that never prints it, and
//! `show`, `discover` and `card` were exactly that case — all three rendered
//! diagnostics only when the load had ERRORS, so the skipped folder was
//! invisible through every one of them. `discover` is the one that mattered:
//! it hands `gaia-ai-runtime` an inventory missing an agent, at exit 0, with
//! empty stderr, and a `workspace-digest` computed over a document the agent is
//! not in. A human reading `show` might notice; a program indexing `discover`
//! cannot. All three now print warnings to stderr and leave stdout the JSON it
//! was, and `a_runtime_is_told_what_the_checker_was_told` below is what holds
//! that.
//!
//! # Mutations
//!
//! **1. The diagnostic.** In `Loader::classify`
//! (`crates/pact-loader/src/lib.rs`), replace the `match reason` with the bare
//! `continue` it used to be. Every test below goes red — `check` returns to
//! *"loaded cleanly"* at exit 0, and `--deny-warnings` returns to exit 0 with
//! it, which is the failure that matters: the gate this repository runs over
//! ten shipped examples cannot see a lost agent.
//!
//! **2. The wording, and what it does NOT catch here.** Replace the folder
//! warning's sentence with `"'{dir}' had something skipped, because some
//! folders normally hold files a tool wrote rather than anything you did."` —
//! the same rule, the same span, no name.
//!
//! ```text
//! $ cargo test -p pact-cli --test a_folder_the_checker_skips_is_named_on_the_way_past
//! test result: ok. 3 passed; 0 failed;
//! ```
//!
//! It left this whole file GREEN, and that is worth stating rather than
//! discovering. `said(&out)` is the rendered diagnostic, and a rendered
//! diagnostic carries an `--> <path>:1:1` arrow line under its sentence — so
//! `said.contains("agents/build")` is answered by the ARROW whatever the
//! sentence says. The same mutation fails three tests in
//! `crates/pact-loader/tests/an_agent_in_a_folder_named_build_is_never_silently_gone.rs`,
//! which asserts on `d.message` alone. The sentence-level claim is held THERE,
//! and only there — until `the_warning_line_itself_names_the_folder` below,
//! which reads the `warning:` line on its own and goes red under this mutation.
//!
//! **3. The second message.** Delete the `name_only` placeholder from the
//! `SettingsNamedLikeDocumentation` arm of `Loader::classify`.
//! `a_tool_written_as_license_yaml_is_not_answered_with_write_the_file_you_wrote`
//! goes red on its own name: the workspace prints the `schema/no-such-name`
//! error whose fix reads *"Add a file `tools/license.yaml`"* — of the file the
//! author has open — and the new warning arrives underneath it as the SECOND
//! message. That assertion is the one this file was missing when B2 shipped.

use std::path::PathBuf;
use std::process::{Command, Output};

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// Everything the command said, both channels, because which one a warning
/// leaves by is not what these tests are about.
fn said(out: &Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}

/// A workspace with one ordinary agent, plus whatever `extra` files the test
/// needs. Written as `(relative path, contents)` so the tree under test is
/// readable in the test that builds it.
fn workspace(name: &str, extra: &[(&str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-skipped-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/keeper")).unwrap();
    std::fs::write(
        dst.join("workspace.yaml"),
        "name: repro\ndescription: A workspace.\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("agents/keeper/agent.yaml"),
        "name: Keeper\ndescription: Keeps things.\ninstructions: Keep things.\n",
    )
    .unwrap();
    for (rel, body) in extra {
        let p = dst.join(rel);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, body).unwrap();
    }
    dst
}

const BUILD_AGENT: &str = "name: Build Agent\ndescription: Runs builds.\ninstructions: Build.\n";

#[test]
fn check_does_not_call_a_workspace_clean_when_it_dropped_an_agent() {
    let ws = workspace("clean", &[("agents/build/agent.yaml", BUILD_AGENT)]);
    let out = pact()
        .args(["check", ws.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let said = said(&out);

    // Still a warning: a workspace that happens to hold a `target/` must not
    // be refused outright, so the exit code stays 0 and the tree still loads.
    assert_eq!(
        out.status.code(),
        Some(0),
        "a skipped folder is not a refusal:\n{said}"
    );
    assert!(
        !said.contains("cleanly"),
        "the summary said the workspace loaded CLEANLY, having thrown an agent away:\n{said}"
    );
    assert!(
        said.contains("loader/folder-skipped-by-name"),
        "no rule named the skipped folder:\n{said}"
    );
    // The folder itself, by the path the author can type into an editor.
    assert!(
        said.contains("agents/build"),
        "the output must name the folder that was skipped:\n{said}"
    );
    assert!(
        said.contains(".pactignore"),
        "the output must say how to mean it deliberately:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&ws);
}

#[test]
fn the_gate_this_repository_runs_can_see_a_lost_agent() {
    // `--deny-warnings` is what the ten shipped examples are checked with. If a
    // dropped agent is not a warning, it is not a gate failure either, and the
    // loss ships.
    // `dist/` sits at the TOP of the workspace on purpose — see the doubled-
    // separator assertion below, which an agent one level down cannot reach.
    let ws = workspace(
        "gate",
        &[
            ("agents/build/agent.yaml", BUILD_AGENT),
            ("dist/output.txt", "written by a build tool\n"),
        ],
    );
    // With a trailing slash, which is the form the repository's own loop uses
    // (`examples/patterns/*/`).
    let arg = format!("{}/", ws.to_str().unwrap());
    let out = pact()
        .args(["check", &arg, "--deny-warnings"])
        .output()
        .expect("the binary runs");
    let said = said(&out);

    assert_eq!(
        out.status.code(),
        Some(1),
        "a lost agent must fail the gate:\n{said}"
    );
    // Both folders are named, so the gate failure is not one entry standing in
    // for the other.
    for entry in ["agents/build", "dist"] {
        assert!(
            said.contains(entry),
            "'{entry}' was skipped and the output does not name it:\n{said}"
        );
    }
    // The doubled separator, where it can actually occur. The message
    // interpolates the JOINED path; the pre-fix line interpolated
    // `'{dir}/{name}'`, and `dir` is the argument only for an entry at the TOP
    // of the workspace — one level down, `<root>/` has already been joined with
    // `agents` and no trailing slash survives. So this was asserted as
    // `!said.contains("//agents")` against a tree whose only skipped folder WAS
    // one level down, and it was vacuous: measured by restoring
    // `'{dir}/{name}'`, which left all ten tests in this file and in
    // `crates/pact-loader/tests/an_agent_in_a_folder_named_build_is_never_silently_gone.rs`
    // green, while `pact check <ws>/` printed `'<ws>//dist'` in the sentence
    // over `<ws>/dist` under the arrow.
    let doubled = format!("{}//", ws.to_str().unwrap());
    assert!(
        !said.contains(&doubled),
        "the path is printed twice over a slash:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&ws);
}

#[test]
fn a_tool_written_as_license_yaml_is_not_answered_with_write_the_file_you_wrote() {
    // The narrower silence, through the binary that produced the contradiction.
    // Before the fix this workspace printed one message: *"'uses' names
    // 'license', and there is no such entry in `tools:` … fix: Add a file
    // `tools/license.yaml`"* — of the file the author had just written.
    let ws = workspace(
        "license",
        &[
            (
                "tools/license.yaml",
                "description: Prints the licence terms.\n",
            ),
            (
                "agents/keeper/agent.yaml",
                "name: Keeper\ndescription: Keeps things.\ninstructions: Keep.\nuses:\n  - license\n",
            ),
        ],
    );
    let out = pact()
        .args(["check", ws.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let said = said(&out);

    assert!(
        said.contains("loader/file-skipped-by-name"),
        "the file the author wrote was thrown away without a word:\n{said}"
    );
    assert!(
        said.contains("tools/license.yaml"),
        "the output must name the file that was skipped:\n{said}"
    );
    assert!(
        said.contains("license.md"),
        "the output must say the other way out:\n{said}"
    );
    // The assertion this test's own NAME promises, and did not make. After the
    // warning landed the workspace printed TWO messages, and the first one was
    // still the error, still first, and still false about the author's tree:
    //
    //     error: 'uses' names 'license', and there is no such entry in `tools:`,
    //            `skills:` or `knowledge:`.
    //       fix: Nothing is declared there yet. Add a file `tools/license.yaml`,
    //            `skills/license/SKILL.md` or `knowledge/license.yaml`.
    //
    // CHK-12 — one mistake, one message — with the harm `elsewhere.rs` exists to
    // prevent reached by a route it cannot see. The skipped file now contributes
    // its NAME as the `pact_doc::UNLOADED` placeholder an unreadable file
    // already becomes, so the reference resolves and the warning is the message.
    assert!(
        !said.contains("Add a file"),
        "the author is told to create the file they are looking at:\n{said}"
    );
    // And exactly one message about it, so the placeholder has not simply
    // traded one false error for another.
    assert_eq!(
        out.status.code(),
        Some(0),
        "a skipped file is not a refusal:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&ws);
}

#[test]
fn the_warning_line_itself_names_the_folder() {
    // Mutation 2 in the module doc: a message that names only the parent folder
    // leaves every `contains` in this file green, because a rendered diagnostic
    // carries an `--> <path>` arrow line and the arrow answers for the path.
    //
    // So this one reads the `warning:` line ALONE. It is the only assertion in
    // this file that can tell a sentence naming the folder from a renderer that
    // happens to print the folder underneath one that does not.
    let ws = workspace("wording", &[("agents/build/agent.yaml", BUILD_AGENT)]);
    let out = pact()
        .args(["check", ws.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let said = said(&out);

    let warning_lines: Vec<&str> = said.lines().filter(|l| l.starts_with("warning:")).collect();
    assert!(
        warning_lines.iter().any(|l| l.contains("agents/build")),
        "no warning SENTENCE names the folder that was skipped — only the arrow \
         under it does, and an author reading the sentence is not told which \
         folder went:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&ws);
}

#[test]
fn a_runtime_is_told_what_the_checker_was_told() {
    // The half of B2 that survived its own fix. `check` named the skipped
    // folder; `show`, `discover` and `card` all gated their rendering on
    // `has_errors()`, so a warning reached none of them. Measured on this exact
    // tree before the repair:
    //
    //     $ pact discover <ws> 2>/tmp/d.err
    //     [ { "kind": "Inventory", "agents": [ {"id": "pact:keeper", …} ],
    //         "digest": "sha256:e07e1a87…" } ]
    //     EXIT=0 ; /tmp/d.err is EMPTY
    //
    // One agent, a digest over a document the other agent is missing from, and
    // nothing anywhere saying so. `gaia-ai-runtime` indexes that.
    let ws = workspace("runtime", &[("agents/build/agent.yaml", BUILD_AGENT)]);
    let out = pact()
        .args(["discover", ws.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let stdout = String::from_utf8_lossy(&out.stdout).to_string();
    let stderr = String::from_utf8_lossy(&out.stderr).to_string();

    // Still exit 0 and still valid JSON on stdout: a runtime that parses this
    // must not be able to tell the difference.
    assert_eq!(out.status.code(), Some(0), "stdout:\n{stdout}\n{stderr}");
    assert!(
        serde_json::from_str::<serde_json::Value>(&stdout).is_ok(),
        "stdout must stay machine-readable:\n{stdout}"
    );
    assert!(
        stderr.contains("loader/folder-skipped-by-name"),
        "the inventory is missing an agent and nothing said so. stderr:\n\
         {stderr:?}\nstdout:\n{stdout}"
    );
    assert!(
        stderr.contains("agents/build"),
        "the channel names no folder:\n{stderr}"
    );

    // `show` is the other one a person reads.
    let out = pact()
        .args(["show", ws.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let stderr = String::from_utf8_lossy(&out.stderr).to_string();
    assert!(
        stderr.contains("agents/build"),
        "`pact show` printed a document an agent is missing from and said \
         nothing:\n{stderr:?}"
    );
    let _ = std::fs::remove_dir_all(&ws);
}

#[test]
fn one_binary_gives_one_answer_about_which_folders_it_skips() {
    // `pact check` warned that `dist/`, `build/` and `venv/` "normally hold
    // files a tool wrote" and told the author to rename them, while
    // `pact discover` — in the same binary, on the same tree — walked straight
    // into all three and published the workspaces inside them to the runtime.
    // Measured, with an identical workspace under each of six names:
    //
    //     $ pact discover <t> | grep -oE '"WS-[a-z_]+"'
    //     "WS-build" "WS-dist" "WS-__pycache__" "WS-venv"
    //     EXIT=0
    //
    // The cause was a second, hardcoded skip list — `matches!(name.as_str(),
    // "target" | "node_modules")` in `discover.rs` — two names against the
    // loader's six, sitting outside the policy module that invariant F-1 and
    // AC-7.2 reserve for exactly this literal. There is one list now, and this
    // is what says so through the binary rather than through the types.
    let dst = std::env::temp_dir().join(format!("pact-onelist-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    let hidden = [
        "build",
        "dist",
        "target",
        "venv",
        "node_modules",
        "__pycache__",
    ];
    for name in hidden.iter().chain(["packages"].iter()) {
        let d = dst.join(name).join("ws");
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(
            d.join("workspace.yaml"),
            format!("name: WS-{name}\ndescription: A workspace.\n"),
        )
        .unwrap();
    }
    let out = pact()
        .args(["discover", dst.to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let stdout = String::from_utf8_lossy(&out.stdout).to_string();

    // The control: a folder neither list skips is still found, so a walk that
    // simply stopped working would not pass this.
    assert!(
        stdout.contains("WS-packages"),
        "discovery found nothing at all, so this test proves nothing:\n{stdout}"
    );
    for name in hidden {
        assert!(
            !stdout.contains(&format!("WS-{name}")),
            "`pact check` tells the author '{name}' is skipped, and `pact \
             discover` published the workspace inside it to the runtime:\n{stdout}"
        );
    }
    let _ = std::fs::remove_dir_all(&dst);
}
