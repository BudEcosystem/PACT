//! **A weekly review with nothing in the workspace that can reach a Friday.**
//!
//! `learning.review:` is `tier: core` and `S-GOV`, it has four choices, and for a
//! round it changed nothing anywhere. MEASURED before this file existed:
//! `grep -rn nothing-runs-the-review crates adapters` returned nothing, and
//! deleting `ports/weekly-review.yaml` from this repository's own worked example
//! — leaving `review: weekly` exactly where it is in `learning.yaml` — printed
//!
//! ```text
//! OK — …/refund-desk loaded cleanly (…) settings).
//! ```
//!
//! and exited 0. The field's own help text used to promise that `pact check`
//! said so; when it turned out not to, the PROMISE was deleted rather than kept.
//!
//! Every test here runs the real binary over a copy of the **shipped** example
//! with one file deleted or one line changed. That is the whole point: a test
//! that builds a document in Rust proves the checker works on something this file
//! wrote, and says nothing about whether the author's own `ports/` folder reaches
//! it. The line that reads that folder is `pact_loader::review::has_a_timer`,
//! called from `pact_loader::review::check`, called from `validate` in
//! `main.rs` — and `the_shipped_examples_own_timer_is_what_keeps_it_quiet` fails
//! if `has_a_timer` is made to return `false`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the shipped example into a temp root, untouched.
fn copied(name: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-review-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    dst
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
    }
}

/// Apply one edit to one file inside a copied tree.
fn edit(root: &std::path::Path, file: &str, from: &str, to: &str) {
    let p = root.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    assert!(text.contains(from), "fixture drifted: {from:?} not in {file}");
    std::fs::write(&p, text.replace(from, to)).unwrap();
}

/// Run `pact check` on a tree and give back what a reader would see.
fn check(root: &std::path::Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().expect("a utf-8 path")])
        .output()
        .expect("the binary runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

#[test]
fn the_shipped_examples_own_timer_is_what_keeps_it_quiet() {
    // The half that matters most, and the one that proves the author's `ports/`
    // folder is READ: the shipped tree has `review: weekly` in `learning.yaml`
    // AND `ports/weekly-review.yaml` beside it, and must load with nothing said.
    let (ok, text) = check(std::path::Path::new(&example()));
    assert!(ok, "the shipped example must still load:\n{text}");
    assert!(
        !text.contains("nothing-runs-the-review"),
        "the example has a timer and must not be warned about one:\n{text}"
    );
}

#[test]
fn deleting_the_timer_from_the_worked_example_is_what_makes_the_promise_empty() {
    // **The authored path, end to end.** Nothing is passed in and nothing is
    // built here: the same two files the author writes are on disk, one of them
    // is removed, and the answer changes. This is the exact edit that printed
    // "loaded cleanly" before this round.
    let root = copied("deleted");
    std::fs::remove_file(root.join("ports/weekly-review.yaml")).expect("the timer was there");
    let (ok, text) = check(&root);

    assert!(ok, "a half-written tree still loads — this is a warning:\n{text}");
    assert!(text.contains("nothing-runs-the-review"), "nothing was said:\n{text}");
    assert!(text.contains("learning.yaml:"), "no file and line:\n{text}");
    assert!(text.contains("review: weekly"), "the line is not quoted back:\n{text}");
    assert!(text.contains("warning"), "a warning is what a half-written tree gets:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_fix_names_the_port_file_to_create_and_every_line_to_put_in_it() {
    // D13: a message with nowhere to go is not a diagnostic. The person who owns
    // a weekly review is a support lead, and "somebody has to schedule this" is
    // not something they can type.
    let root = copied("fix");
    std::fs::remove_file(root.join("ports/weekly-review.yaml")).unwrap();
    let (_, text) = check(&root);

    assert!(text.contains("ports/weekly-review.yaml"), "name the file to create:\n{text}");
    for line in ["kind: schedule", "every: Friday at 4pm", "answers:", "says:"] {
        assert!(text.contains(line), "the fix must spell out `{line}`:\n{text}");
    }
    assert!(text.contains("review: manual"), "offer the other way out:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn writing_the_timer_back_without_the_word_schedule_clears_it_again() {
    // The derivation `ports.rs` made normative, held one level up: a port with an
    // `every:` line IS a timer, so an author who wrote one line rather than two
    // must not be told they have no clock. A check that looked for the literal
    // words `kind: schedule` would fail here.
    let root = copied("derived");
    edit(&root, "ports/weekly-review.yaml", "kind: schedule\n", "");
    let (ok, text) = check(&root);

    assert!(ok, "{text}");
    assert!(
        !text.contains("nothing-runs-the-review"),
        "`every: Friday at 4pm` is a clock:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn saying_a_person_starts_the_review_by_hand_is_a_line_that_makes_the_file_true() {
    // The second fix, typed. `manual` is the one `review:` answer that names no
    // interval, so nothing is owed — and offering it matters, because the other
    // fix is a whole new file and somebody who is not ready to write one needs a
    // way to say what is actually happening.
    let root = copied("manual");
    std::fs::remove_file(root.join("ports/weekly-review.yaml")).unwrap();
    edit(&root, "learning.yaml", "review: weekly", "review: manual");
    let (ok, text) = check(&root);

    assert!(ok, "{text}");
    assert!(!text.contains("nothing-runs-the-review"), "a person starts it:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_workspace_that_never_improves_itself_is_owed_no_review() {
    // `enabled: off` proposes nothing, so there is nothing for a review to show
    // and no clock to be missing. Through the author's own file, because the
    // whole point of the check is that two authored files decide it together.
    let root = copied("off");
    std::fs::remove_file(root.join("ports/weekly-review.yaml")).unwrap();
    edit(&root, "learning.yaml", "enabled: propose-only", "enabled: off");
    let (ok, text) = check(&root);

    assert!(ok, "{text}");
    assert!(!text.contains("nothing-runs-the-review"), "nothing is proposed:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_warning_reads_without_programming_knowledge_and_ends_in_a_fix() {
    // Same bar `authoring_surface.rs` holds every other diagnostic to. The reader
    // of this sentence is whoever was expecting the review.
    let root = copied("jargon");
    std::fs::remove_file(root.join("ports/weekly-review.yaml")).unwrap();
    let (_, text) = check(&root);

    assert!(text.contains("  fix: "), "no fix offered:\n{text}");
    assert!(text.contains(".yaml:"), "no file:line given:\n{text}");
    let lower = text.to_lowercase();
    for word in [
        "enum", "variant", "deserialize", "serde", "unwrap", "panic", "trait", "struct",
        "vec<", "option<", "stack trace", "null pointer", "schema validation failed",
        "cron", "callback", "async",
    ] {
        assert!(!lower.contains(word), "assumes programming knowledge ('{word}'):\n{text}");
    }
    let _ = std::fs::remove_dir_all(&root);
}
