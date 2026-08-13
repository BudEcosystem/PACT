//! A twelve-line agent file used to kill `pact check` outright.
//!
//! YAML lets an author name a block once with `&name` and reuse it with
//! `*name`. Each `*name` copies the whole block in, and a block may itself be
//! written out of `*name` copies — so nine copies per line, six lines down,
//! is 597,871 settings from seven lines of text. `pact-doc/src/yaml.rs` had a
//! limit for exactly this (`MAX_NODES = 200_000`) but charged a `*name` **one**
//! setting however much it stood for, and charged it *after* `.cloned()` had
//! already made the copy. Neither half could work: the count never reached the
//! limit, and by the time it was consulted the memory had already been asked
//! for.
//!
//! Measured on this tree before the fix, with the address space capped so the
//! machine survived it — `( ulimit -v 4000000; pact check <ws> )`:
//!
//! ```text
//! memory allocation of 1368 bytes failed
//! note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
//! /bin/bash: line 23: 3819236 Aborted                 (core dumped) pact check <ws>
//! EXIT=134
//! ```
//!
//! Exit 134 is the process being killed by the operating system. No file name,
//! no line, no rule — and `gaia-ai-runtime` is specified to discover and load
//! trees it did not write, so this is a loader that any untrusted folder can
//! stop.
//!
//! This drives the real binary over a real workspace rather than calling
//! `parse_yaml`, because the reproduction *is* `pact check` dying: a library
//! test proves the parser refuses the document, not that the command survives
//! reaching it. The unit tests live beside the accounting in
//! `crates/pact-doc/src/yaml.rs`.
//!
//! Mutation **M1**: in `yaml.rs`, restore the original arm —
//! `Event::Alias(id) => match self.anchors.get(&id).map(|a| a.copy()) {
//! Some(node) => self.emit(node, 0), … }`, charging one per copy after the
//! clone. The failure is an ordinary assertion, not a corpse: measured on the
//! five-level tree these build, the mutated `pact check` grew to **411 MB in
//! 0.96 s**, loaded all 597,871 settings, and reported six
//! `schema/unknown-field` problems about `n0`…`n5` — no `doc/too-large`
//! anywhere.
//!
//! **How many tests M1 kills was written when this file had two of them and
//! never re-measured.** It said "both tests below then go red" and that every
//! other test in the suite stayed green; both halves are false, and the second
//! is false by five. Re-measured, M1 applied to the tree as it now stands:
//!
//! * `cargo test -p pact-cli --test
//!   a_shortcut_that_copies_itself_cannot_bring_down_the_checker` →
//!   `test result: FAILED. 4 passed; 3 failed`. Red:
//!   `check_refuses_a_shortcut_that_copies_itself_instead_of_being_killed_by_it`,
//!   `the_refusal_tells_a_non_coder_what_went_wrong_and_what_to_type`, and
//!   `check_refuses_a_shortcut_that_stands_for_a_wall_of_writing` — the last of
//!   those because M1 stops charging a copy's *writing* as well as its
//!   settings. Green: the worked example, and the three tests below that reach
//!   the accounting by another route (the two folder tests and the
//!   nested-definitions test, none of which M1 touches).
//! * `cargo test -p pact-doc --lib` → `test result: FAILED. 42 passed; 6
//!   failed`, not a clean suite. The six are listed at
//!   `crates/pact-doc/src/yaml.rs`, in
//!   `a_shortcut_that_copies_itself_wider_every_line_is_refused_by_the_size_limit`.
//!
//! The tests named as surviving do survive: `anchors_and_aliases_resolve` and
//! `unknown_alias_is_a_clear_error` are green under M1, as is the worked
//! example, whose `spec/schema.yaml` uses a shortcut of its own.
//!
//! ## The folder, which is the door the threat model above actually names
//!
//! For a round this file's claim was read as *the loader survives an untrusted
//! tree*, and what it held was *the loader survives one untrusted file*. Both
//! size budgets reset in `Builder::new`, once per file, so four hundred agent
//! files of 277 bytes each — every one of them inside `MAX_NODES`, 110,817
//! bytes on disk altogether — put `pact check` AND `pact discover` back at
//! `memory allocation of 1 bytes failed`, signal 6, `PEAK_KB=2998240`,
//! EXIT=134 under `ulimit -v 3000000`, on the build that had fixed every
//! single-file case. `status.code() == Some(1)` passed identically either way,
//! because the workspace every helper in this file built had exactly one agent
//! in it. `pact_loader` now carries a running total across the whole load
//! (`MAX_LOAD_SETTINGS`, `MAX_LOAD_TEXT`), and the two folder tests below are
//! what hold it.
//!
//! ## The second way to be too big
//!
//! Counting settings is not counting size, and the first fix counted only
//! settings — so a shortcut naming one long piece of writing walked straight
//! past it. 150 KB of text named `&g` and used 25,000 times is 25,001 settings,
//! three orders of magnitude under the settings limit, and 3.75 GB of writing.
//! Measured on a 413,946-byte workspace of exactly that shape, against the
//! build that had just fixed the settings count:
//!
//! ```text
//! memory allocation of 150000 bytes failed
//! Command terminated by signal 6
//! PEAK_KB=3989076
//! EXIT=134
//! ```
//!
//! Same file, once writing is counted too: `rule: doc/too-large`, exit 1,
//! `PEAK_KB=8896`, 0.17 s.
//!
//! Five levels, not the eight of the reproduction, on purpose. The refusal
//! lands in the same place either way — the budget runs out partway through the
//! fifth level, so the sixth, seventh and eighth lines are never read and the
//! measured peak is 69 MB regardless. What eight levels changes is only what
//! happens when the fix is *absent*: 5.3 million settings, several gigabytes,
//! on a machine other people are building on. The half of the claim those extra
//! lines would carry — that the command is never killed outright — is asserted
//! directly instead, by `status.code()`, which is `None` and not `Some(1)` for
//! any child that died of a signal.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A workspace whose one agent hides a shortcut that copies itself nine ways,
/// `levels` times over. `levels` of 5 works out to 597,871 settings — comfortably
/// past the 200,000 limit, and past it while only ~75,000 have been built, so
/// the refusal arrives long before the machine is under any strain. Measured
/// peak resident memory for this workspace: 69 MB, and the whole check returns
/// in well under a second.
fn workspace_with_a_bomb(name: &str, levels: usize) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-shortcut-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents")).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Bomb Range\n").unwrap();

    let mut agent = String::from("name: Desk\ndescription: probe\ninstructions: hi\n");
    agent.push_str("n0: &n0 [\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\"]\n");
    for i in 1..=levels {
        let refs = vec![format!("*n{}", i - 1); 9].join(",");
        agent.push_str(&format!("n{i}: &n{i} [{refs}]\n"));
    }
    std::fs::write(dst.join("agents").join("desk.yaml"), agent).unwrap();
    dst
}

/// A workspace whose one agent names a long piece of writing once and uses it
/// `copies` times over. 150 KB × 60 is 9 MB out of a 150 KB file — enough to be
/// well past the limit and refused, and small enough that the machine other
/// people are building on never notices, in either direction. The reproduction
/// itself used 25,000 copies and 3.75 GB, which is not a thing to leave in a
/// suite: the number that matters is that the limit is crossed, and 60 crosses
/// it.
fn workspace_with_a_wall_of_writing(name: &str, copies: usize) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-shortcut-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents")).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Bomb Range\n").unwrap();

    let mut agent = String::from("name: Desk\ndescription: probe\ninstructions: hi\n");
    agent.push_str(&format!("g: &g \"{}\"\n", "z".repeat(150_000)));
    for i in 0..copies {
        agent.push_str(&format!("u{i}: *g\n"));
    }
    std::fs::write(dst.join("agents").join("desk.yaml"), agent).unwrap();
    dst
}

#[test]
fn check_refuses_a_shortcut_that_stands_for_a_wall_of_writing() {
    // The same loader, the same `*name` copy, the same exit 134 — reached by
    // counting settings and finding nothing wrong, because every one of these
    // settings is a single word as far as a count is concerned and 150 KB of
    // writing as far as memory is concerned.
    //
    // Mutation (M2): in `pact-doc/src/yaml.rs`, charge the settings budget only
    // — `self.afford(size, 0)` in the alias arm, `self.afford(1, 0)` in `emit`,
    // and `self.afford(priced.size, 0)` where a definition is kept. Measured:
    // `test result: FAILED. 6 passed; 1 failed` — this test, on the missing
    // `doc/too-large`, and nothing else in this file, because every other bomb
    // here is made of settings rather than writing and the settings count still
    // catches those. `pact-doc --lib` under M2 is `45 passed; 3 failed`.
    let root = workspace_with_a_wall_of_writing("writing", 60);
    let done = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let out = String::from_utf8_lossy(&done.stdout).into_owned();
    let err = String::from_utf8_lossy(&done.stderr).into_owned();

    assert_eq!(
        done.status.code(),
        Some(1),
        "check must exit with a refusal, not be killed: {done:?}\n{out}{err}"
    );
    assert!(out.contains("rule: doc/too-large"), "{out}{err}");
    assert!(out.contains("copies in so much writing"), "{out}{err}");
    assert!(
        out.contains("over 4 MB"),
        "say what the limit is: {out}{err}"
    );
    // Line 30, where it was 31 before defining `&g` was charged for the copy it
    // keeps: 150 KB is now spent twice on line 4, so `u25` is the use that
    // crosses 4 MB rather than `u26`.
    assert!(
        out.contains("agents/desk.yaml:30:"),
        "must name file and line: {out}{err}"
    );
    assert!(out.contains("Nothing was run."), "{out}{err}");

    let _ = std::fs::remove_dir_all(&root);
}

/// A workspace of `agents` agents, each holding the same five-level shortcut.
/// Every file is 277 bytes and works out to 74,732 settings — well inside the
/// per-file budget of 200,000 — so nothing about any one of them is wrong, and
/// the only thing wrong with the folder is that there are a lot of them.
///
/// Twenty, where the reproduction used four hundred. The refusal lands in the
/// same place either way: the load-wide budget runs out on the fourteenth file,
/// so files fifteen to four hundred are never read and the measured peak is the
/// same. What the extra 380 change is only what happens when the fix is
/// *absent* — 30 million settings and three gigabytes, on a machine other
/// people are building on.
fn workspace_of_bombs(name: &str, agents: usize) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-shortcut-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(&dst).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Bomb Range\n").unwrap();

    // Every field carries the `x-` prefix an unknown extension field wears, so
    // the agent is otherwise VALID. Without that, the mutated build's answer is
    // a pile of `schema/unknown-field` complaints and both folder tests pass on
    // the wrong problem — measured: `discover_survives_the_same_folder_it_
    // cannot_load` stayed green under M7 until this line was written, because a
    // workspace `pact check` refuses is one `pact discover` skips for reasons
    // that have nothing to do with its size.
    let mut agent = String::from("name: Desk\ndescription: probe\ninstructions: hi\n");
    agent.push_str("x-n0: &n0 [\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\",\"x\"]\n");
    for i in 1..=4 {
        let refs = vec![format!("*n{}", i - 1); 9].join(",");
        agent.push_str(&format!("x-n{i}: &n{i} [{refs}]\n"));
    }
    for k in 0..agents {
        let dir = dst.join("agents").join(format!("a{k:03}"));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("agent.yaml"), &agent).unwrap();
    }
    dst
}

/// A workspace whose one agent defines `&name` blocks written inside one
/// another and never uses a single one of them. No `*name` appears anywhere, so
/// every test above is structurally blind to it: they all reach the parser
/// through `Event::Alias`, and this file never produces one.
fn workspace_with_nested_definitions(name: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-shortcut-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents")).unwrap();
    std::fs::write(dst.join("workspace.yaml"), "name: Bomb Range\n").unwrap();

    let leaves = vec!["\"x\""; 20_000].join(",");
    let mut nested = format!("[{leaves}]");
    for i in 0..30 {
        nested = format!("&n{i} [{nested}]");
    }
    let agent = format!("name: Desk\ndescription: probe\ninstructions: hi\nx-d: {nested}\n");
    assert!(
        !agent.contains('*'),
        "this file must use no shortcut, only define them"
    );
    std::fs::write(dst.join("agents").join("desk.yaml"), agent).unwrap();
    dst
}

#[test]
fn check_refuses_a_folder_of_shortcuts_instead_of_being_killed_by_it() {
    // The single-file case was closed and the folder was left open, and the
    // folder is the door the header's threat model names: `gaia-ai-runtime` is
    // specified to discover and load trees it did not write, and a tree is a
    // folder. Measured on the build that had fixed every single-file case,
    // 400 of these files under `ulimit -v 3000000`:
    //
    //     memory allocation of 1 bytes failed
    //     Command terminated by signal 6
    //     PEAK_KB=2998240 ELAPSED=4.05
    //     EXIT=134
    //
    // Mutation (M7): in `pact-loader/src/lib.rs`, make `Loader::affordable`
    // return `true` unconditionally. Measured: `test result: FAILED. 5 passed;
    // 2 failed` — this test and `discover_survives_the_same_folder_it_cannot_
    // load`, and nothing else in the file. `check_refuses_a_shortcut_that_
    // copies_itself_instead_of_being_killed_by_it` and the three other
    // single-file tests stay green under M7, which is exactly the blindness
    // being closed: every one of them builds a workspace with one agent in it.
    // `cargo test -p pact-doc --lib` is untouched by M7 — `48 passed` — because
    // no library test loads a folder at all.
    let root = workspace_of_bombs("folder", 20);
    let done = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let out = String::from_utf8_lossy(&done.stdout).into_owned();
    let err = String::from_utf8_lossy(&done.stderr).into_owned();

    assert_eq!(
        done.status.code(),
        Some(1),
        "check must exit with a refusal, not be killed: {done:?}\n{out}{err}"
    );
    assert!(out.contains("rule: loader/too-much-to-load"), "{out}{err}");
    assert!(
        out.contains("takes it over"),
        "name the file that crossed the line: {out}{err}"
    );
    // One mistake, one message — not one per remaining file, and not a page of
    // complaints about documents the loader stopped before reading.
    assert_eq!(
        out.matches("rule: ").count(),
        1,
        "one problem, once: {out}{err}"
    );
    assert!(out.contains("Nothing was run."), "{out}{err}");

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn discover_survives_the_same_folder_it_cannot_load() {
    // `pact discover` is the command D2 specifies for walking trees nobody
    // vouched for, so it is the worse half of the same door and was dying
    // identically: `memory allocation of 125 bytes failed`, signal 6,
    // `PEAK_KB=2998240`, EXIT=134 on the same folder.
    //
    // Its refusal is not `check`'s. `discover` reports what it found and skips
    // what it could not read, so the right answer here is exit 0, an empty
    // inventory, and a line on stderr naming the folder — not exit 1. What both
    // commands owe is the same and is what this asserts: an exit code at all.
    // `code()` is `None` for a child killed by a signal.
    //
    // Mutation (M7), the same one: this test then reports an inventory with one
    // workspace in it where `[]` was expected, because 1.5 million settings
    // load without complaint and `discover` publishes what loads.
    //
    // It only reports that because every field in the agent files carries the
    // `x-` prefix — measured, and the reason it does. With one ordinary unknown
    // field in them the mutated build's answer is `skipping …: 66 problem(s)`
    // and an empty inventory, which is what this test asserts, so it passed
    // under M7 while the folder it was written about still killed nothing but
    // the schema's patience.
    let root = workspace_of_bombs("discover-folder", 20);
    let done = pact()
        .args(["discover", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let out = String::from_utf8_lossy(&done.stdout).into_owned();
    let err = String::from_utf8_lossy(&done.stderr).into_owned();

    assert_eq!(
        done.status.code(),
        Some(0),
        "discover must answer, not be killed: {done:?}\n{out}{err}"
    );
    assert_eq!(
        out.trim(),
        "[]",
        "a folder that will not load publishes nothing: {out}{err}"
    );
    assert!(
        err.contains("skipping"),
        "and says so rather than staying silent: {out}{err}"
    );

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn check_refuses_shortcuts_written_inside_one_another_though_none_is_used() {
    // Defining `&name` keeps a copy of everything under it so a later `*name`
    // has something to copy from, and that copy was charged against neither
    // budget. A definition written inside another definition pays it once per
    // level, so a file inside every per-file limit — node count under
    // `MAX_NODES`, nesting under `MAX_DEPTH`, no `*name` anywhere — took
    // `pact check` to `PEAK_KB=3683232` in 4.10 s and answered with a schema
    // complaint about the field name. Under `ulimit -v 1500000`:
    //
    //     memory allocation of 1 bytes failed
    //     Command terminated by signal 6
    //     EXIT=134
    //
    // The same tree with the `&`s deleted peaked at 127,816 KB and survived the
    // same cap, which is what says the shortcuts are the cause. With the charge
    // in place this folder is refused at `PEAK_KB=93376` in 0.57 s.
    //
    // Mutation (M5): in `yaml.rs`'s `emit`, delete the `afford` that pays for
    // the kept copy. This test then reports a missing `doc/too-large` — the
    // file loads. Measured: `test result: FAILED. 5 passed; 2 failed` in this
    // file (this test and `check_refuses_a_shortcut_that_stands_for_a_wall_of_
    // writing`, whose 150 KB block is charged once instead of twice so the
    // refusal lands past the end of the file), and `43 passed; 5 failed` in
    // `pact-doc --lib`.
    let root = workspace_with_nested_definitions("nested-definitions");
    for cmd in ["check", "discover"] {
        let done = pact()
            .args([cmd, root.to_str().unwrap()])
            .output()
            .expect("runs");
        let out = String::from_utf8_lossy(&done.stdout).into_owned();
        let err = String::from_utf8_lossy(&done.stderr).into_owned();
        assert!(
            done.status.code().is_some(),
            "`pact {cmd}` was killed rather than answering: {done:?}\n{err}"
        );
        if cmd == "check" {
            assert_eq!(done.status.code(), Some(1), "{out}{err}");
            assert_eq!(out.matches("rule: doc/too-large").count(), 1, "{out}{err}");
            assert!(out.contains("Naming this for reuse"), "{out}{err}");
        } else {
            assert_eq!(done.status.code(), Some(0), "{out}{err}");
            assert_eq!(out.trim(), "[]", "{out}{err}");
        }
    }

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn check_refuses_a_shortcut_that_copies_itself_instead_of_being_killed_by_it() {
    // Mutation (M1), the restored arm in the header. Measured: this test
    // reports the missing sentence `This shortcut (`*name`) copies in so much`.
    // It is one of the three tests in this file M1 reds.
    //
    // **It reports that and not a missing `doc/too-large`, and the difference
    // is the whole reason the message assertion below exists.** Since defining
    // `&n5` is charged for the copy it keeps, the mutated build still refuses
    // this file, at the same line, under the same rule — in the words of the
    // definition rather than of the use. Rule and location alone stopped
    // telling the two accountings apart the moment the second charge landed,
    // and a test that asserts only those would have gone on passing while half
    // the fix was reverted.
    let root = workspace_with_a_bomb("refused", 5);
    let done = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let out = String::from_utf8_lossy(&done.stdout).into_owned();
    let err = String::from_utf8_lossy(&done.stderr).into_owned();

    // The whole point: an ordinary refusal, not a corpse. `code()` is `None`
    // when the child was killed by a signal, which is what exit 134 was.
    assert_eq!(
        done.status.code(),
        Some(1),
        "check must exit with a refusal, not be killed: {done:?}\n{out}{err}"
    );
    assert!(out.contains("rule: doc/too-large"), "{out}{err}");
    // In the shortcut's own words. Asserted here as well as in the readability
    // test below because without it this test survives M1: the charge that
    // defining `&n5` now pays refuses the same file at the same line, so the
    // rule and the location alone no longer tell the two accountings apart.
    assert!(
        out.contains("This shortcut (`*name`) copies in so much"),
        "{out}{err}"
    );
    // And it must say which file and which line, like every other refusal.
    assert!(
        out.contains("agents/desk.yaml:9:"),
        "must name file and line: {out}{err}"
    );
    assert!(out.contains("n5: &n5 ["), "must show the line: {out}{err}");
    assert!(out.contains("Nothing was run."), "{out}{err}");

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_refusal_tells_a_non_coder_what_went_wrong_and_what_to_type() {
    // Mutation (M1), the restored arm in the header. This test then reports the
    // missing sentence `This shortcut (`*name`) copies in so much` — there is no
    // refusal to read, because the mutated build loaded the bomb. That is the
    // second of the three tests in this file M1 reds. D13/D14: the reader
    // cannot write code, so "the checker printed nothing about it" is not a
    // lesser failure than a wrong message, it is the same one.
    let root = workspace_with_a_bomb("readable", 5);
    let done = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let out = String::from_utf8_lossy(&done.stdout).into_owned();
    let err = String::from_utf8_lossy(&done.stderr).into_owned();

    assert!(
        out.contains("This shortcut (`*name`) copies in so much"),
        "{out}{err}"
    );
    assert!(
        out.contains("over 200000 settings"),
        "say what the limit is: {out}{err}"
    );
    assert!(
        out.contains("Write the values you need here out in full"),
        "{out}{err}"
    );
    assert!(
        out.contains("split them across several files"),
        "{out}{err}"
    );
    // One problem, one sentence — a bomb must not print a page of them.
    assert_eq!(out.matches("rule: doc/too-large").count(), 1, "{out}{err}");

    // Only the sentences addressed to the author — the file name is `desk.yaml`
    // and the quoted source line is the author's own, so scanning the whole
    // report would be scanning the author's file for words they chose.
    let prose: String = out
        .lines()
        .filter(|l| l.starts_with("error: ") || l.trim_start().starts_with("fix: "))
        .collect::<Vec<_>>()
        .join("\n")
        .to_lowercase();
    for jargon in [
        "alias", "anchor", "allocat", "recurs", "node", "expand", "yaml",
    ] {
        assert!(
            !prose.contains(jargon),
            "diagnostic leaked '{jargon}':\n{prose}\n{out}{err}"
        );
    }

    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_shortcut_the_worked_example_relies_on_still_loads() {
    // `spec/schema.yaml` names an address vocabulary once with
    // `&the-address-vocabulary` and reuses it with `*the-address-vocabulary`.
    // A size limit that refused honest reuse would be a worse bug than the one
    // it fixed, so the shipped example is checked through the same command.
    //
    // Scoped to this rule rather than to a clean exit on purpose: the example is
    // shared, and a test about shortcuts has no business failing because
    // somebody is midway through editing something else.
    //
    // **What it exercises is the compiled-in specification, not the example
    // tree.** No YAML file under `examples/` defines or uses a shortcut —
    // `grep -rn '&[a-zA-Z_][a-zA-Z0-9_-]*\|: \*[a-zA-Z_]' --include=*.yaml
    // --include=*.yml examples/` returns nothing — so the honest-reuse surface
    // this test actually reaches is `BUILTIN_SPEC` —
    // `crates/pact-cli/src/main.rs`'s `include_str!("../../../spec/schema.yaml")`
    // — whose anchors are at `spec/schema.yaml:462`, `:3181` and `:3315`. The
    // test still belongs here: `pact check` cannot validate anything without
    // parsing that file through the same accounting, so a size fix that broke
    // honest reuse would take every command down with it.
    //
    // Mutation (M4): add 200,000 to the price of every kept block —
    // `size: node.node_count() + 200_000` in `Priced::of`. Measured: this test
    // reports `the worked example was refused` with
    //
    //     The specification itself has problems (the built-in specification):
    //     error: Naming this for reuse (`&name`) keeps a second copy of
    //            everything under it, which takes the file to over 200000
    //            settings.
    //       --> spec/schema.yaml:463:15
    //     error: cannot validate against a broken specification
    //
    // — the caret landing on the compiled-in specification, not on anything
    // under `examples/`, which is what says where the honest-reuse surface
    // really is. M4 takes most of the file down with it (`test result: FAILED.
    // 1 passed; 6 failed`, the survivor being `discover_survives_the_same_
    // folder_it_cannot_load`, which expects an empty inventory and gets one for
    // the wrong reason) because no command can validate anything at all. That
    // is the point of keeping this test: it is what says the limits are still
    // on the safe side of the specification every command has to parse first.
    let example = format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"));
    let done = pact().args(["check", &example]).output().expect("runs");
    let out = String::from_utf8_lossy(&done.stdout).into_owned();
    let err = String::from_utf8_lossy(&done.stderr).into_owned();

    assert_eq!(
        done.status.code(),
        Some(0),
        "the worked example was refused:\n{out}{err}"
    );
    assert!(!out.contains("doc/too-large"), "{out}{err}");
    assert!(!out.contains("doc/too-deep"), "{out}{err}");
}
