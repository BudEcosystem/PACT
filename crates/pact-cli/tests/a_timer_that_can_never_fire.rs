//! **A port that says it is a timer, or says nothing at all, held to it.**
//!
//! `port.kind:` was `required: yes` with four choices — `conversation`,
//! `schedule`, `inbound-call`, `event` — and only `schedule` did anything.
//! Measured on a copy of this repository's own worked example: change
//! `ports/weekly-review.yaml` from `kind: schedule` to `kind: event`, leave
//! `every: Friday at 4pm`, `says:` and `if-still-running: skip` exactly where
//! they are, and `pact check` printed
//!
//! ```text
//! OK — …/refund-desk loaded cleanly (492 settings).
//! ```
//!
//! and exited 0. The weekly summary would never have been written, and the first
//! person to know would have been whoever expected it on a Friday.
//!
//! Every test here runs the real binary over a copy of the **shipped** example
//! with one line edited. That is the whole point: a test that builds a port in
//! Rust proves the checker works on a document this file wrote, and says nothing
//! about whether the author's own line reaches it. The line that reads it is
//! `pact_loader::ports::kind_of`, called from `pact_loader::ports::check`, called
//! from `validate` in `main.rs` — and
//! `the_shipped_timer_still_loads_with_its_kind_line_deleted` fails if the
//! derivation arm inside `kind_of` is removed.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the shipped example and apply one edit, returning the temp root.
fn edited(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-timer-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    assert!(text.contains(from), "fixture drifted: {from:?} not in {file}");
    std::fs::write(&p, text.replace(from, to)).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() { copy(&s, &d) } else { std::fs::copy(&s, &d).map(|_| ()).unwrap() }
    }
}

/// Run `pact check` on a tree and give back what a reader would see.
fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().expect("the binary runs");
    (out.status.success(), String::from_utf8_lossy(&out.stdout).into_owned())
}

#[test]
fn the_worked_examples_own_timer_is_accepted_exactly_as_it_is_written() {
    // The half that matters most. A false refusal on the shipped tree costs an
    // author their trust in every other line the tool prints.
    let (ok, text) = check(&example());
    assert!(ok, "the shipped example must still load:\n{text}");
}

#[test]
fn changing_the_shipped_timers_kind_to_event_is_refused_and_names_the_line_to_change() {
    // The measured defect, on the exact file and the exact edit that produced
    // it. `- kind: schedule` is spelled out rather than replaced everywhere,
    // because this file also carries the word `schedule` in its own comment.
    let root = edited("event", "ports/weekly-review.yaml", "kind: schedule", "kind: event");
    let (ok, text) = check(&root);

    assert!(!ok, "a timer that can never fire must be refused:\n{text}");
    assert!(text.contains("weekly-review.yaml:"), "no file and line:\n{text}");
    assert!(text.contains("every:"), "the dead setting is not named:\n{text}");
    assert!(
        text.contains("Change `kind: event` to `kind: schedule`, or delete the `every:` line."),
        "the fix has to be two lines the author can type:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_shipped_timer_still_loads_with_its_kind_line_deleted() {
    // **The derivation, through the author's own file.** `every: Friday at 4pm`
    // is what makes this port a timer, so `kind: schedule` beside it is the
    // author saying twice what they said once — and saying it twice is what let
    // the two copies disagree in the test above.
    //
    // Before this round the same edit was refused: `kind:` was `required: yes`
    // and `pact check` said *"A port must have a 'kind'."* Delete the `every:`
    // arm of `ports::kind_of` and this fails again, because `says:` and
    // `if-still-running:` are then sitting on a port nothing calls a timer.
    let root = edited("derived", "ports/weekly-review.yaml", "kind: schedule\n", "");
    let (ok, text) = check(&root);

    assert!(ok, "a port with an `every:` line IS a timer and needs no `kind:`:\n{text}");
    assert!(text.contains("loaded cleanly"), "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_timer_with_no_line_saying_when_and_no_line_saying_it_is_one_is_refused() {
    // The other side of the derivation. With both `kind:` and `every:` gone,
    // `says:` is wording nobody will ever read and `if-still-running:` guards a
    // run that never starts. The fix cannot offer to change a `kind:` line,
    // because there is no longer one to change.
    let root = edited("no-when", "ports/weekly-review.yaml", "kind: schedule\nevery: Friday at 4pm\n", "");
    let (ok, text) = check(&root);

    assert!(!ok, "wording with no clock behind it must be refused:\n{text}");
    assert!(text.contains("weekly-review.yaml:"), "no file and line:\n{text}");
    assert!(text.contains("`every: Friday at 4pm`"), "the fix must name the line to add:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_shipped_timer_with_only_its_when_line_deleted_is_refused_too() {
    // The direction the schema owns, walked through the author's own file. A
    // port that keeps `kind: schedule` and loses `every:` is the same dead timer
    // read the other way round: it says it is the clock and never says when, so
    // the weekly summary is just as absent as it was under `kind: event`.
    //
    // `needed-when: {every: schedule}` in `spec/schema.yaml` is what refuses it,
    // and `a_missing_companion_says_what_the_missing_setting_is` already walks
    // every pairing the specification declares — but it does so on a document it
    // builds in Rust (`format!("{field}: '{value}'")`), which proves the
    // validator works and says nothing about whether the shipped
    // `ports/weekly-review.yaml` reaches it. This is that half. Take
    // `needed-when:` off `port.kind` and only this test notices.
    let root = edited("no-every", "ports/weekly-review.yaml", "every: Friday at 4pm\n", "");
    let (ok, text) = check(&root);

    assert!(!ok, "a port that says it is the clock and never says when must be refused:\n{text}");
    assert!(text.contains("weekly-review.yaml:"), "no file and line:\n{text}");
    assert!(text.contains("schedule"), "the sentence must quote what the port says it is:\n{text}");
    assert!(
        text.contains("`every: ...`"),
        "the fix has to be a line the author can type:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_words_a_timer_uses_are_refused_on_the_port_customers_talk_to() {
    // `says:` is what the clock asks the agent to do when nobody has spoken to
    // it. On the Slack port there is always somebody who has, so the line is
    // dead — and its own help now says so.
    let root = edited(
        "says-on-slack",
        "ports/slack.yaml",
        "kind: conversation",
        "kind: conversation\nsays: Summarise the week.",
    );
    let (ok, text) = check(&root);

    assert!(!ok, "a timer's wording on a conversation must be refused:\n{text}");
    assert!(text.contains("slack.yaml:"), "no file and line:\n{text}");
    assert!(
        text.contains("Change `kind: conversation` to `kind: schedule`, or delete the `says:` line."),
        "the fix has to be two lines the author can type:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_port_that_says_nothing_about_how_work_arrives_is_still_refused_and_offered_the_words() {
    // `kind:` stopped being required so a timer need not say it twice. This is
    // the half that had to be given back: where nothing derives it, it is still
    // owed. Slack has no `every:` line, so deleting its `kind:` leaves a
    // connection nothing knows how to open.
    let root = edited("no-kind", "ports/slack.yaml", "kind: conversation\n", "");
    let (ok, text) = check(&root);

    assert!(!ok, "a port with no kind at all must be refused:\n{text}");
    assert!(text.contains("slack.yaml:"), "no file and line:\n{text}");
    for choice in ["conversation", "schedule", "inbound-call", "event"] {
        assert!(text.contains(choice), "the fix must offer '{choice}':\n{text}");
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_specification_no_longer_demands_a_kind_and_still_offers_the_four_words() {
    // The schema half of this, read off the file that ships rather than
    // asserted about a schema this test built. `required: yes` coming back would
    // make `the_shipped_timer_still_loads_with_its_kind_line_deleted` fail too,
    // but it would fail with a sentence about a missing field and leave the
    // reader guessing which line reintroduced it; this one names it.
    let text = std::fs::read_to_string(format!(
        "{}/../../spec/schema.yaml",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    let doc = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml"))
        .expect("the specification parses");
    let kind = doc
        .get("groups")
        .and_then(|g| g.get("port"))
        .and_then(|p| p.get("fields"))
        .and_then(|f| f.get("kind"))
        .expect("`port` still has a `kind:` field");

    assert!(
        kind.get("required").is_none(),
        "`port.kind` is required again, so a timer has to say it is one twice"
    );
    let choices: Vec<&str> = kind
        .get("choices")
        .and_then(pact_doc::Node::as_list)
        .map(|l| l.iter().filter_map(pact_doc::Node::as_str).collect())
        .expect("`kind:` still offers a closed set of words");
    assert!(choices.contains(&"schedule"), "the word the clock derives to is gone: {choices:?}");
    for owed in ["help", "surface", "tier"] {
        assert!(kind.get(owed).is_some(), "`port.kind` lost its `{owed}:`");
    }
}

#[test]
fn every_refusal_here_reads_without_programming_knowledge_and_ends_in_a_fix() {
    // Same bar `authoring_surface.rs` holds every other diagnostic to. The
    // person who writes a schedule is a support lead, and these are the three
    // sentences they will meet.
    let cases: &[(&str, &str, &str, &str)] = &[
        ("jargon-event", "ports/weekly-review.yaml", "kind: schedule", "kind: event"),
        ("jargon-nowhen", "ports/weekly-review.yaml", "kind: schedule\nevery: Friday at 4pm\n", ""),
        ("jargon-nokind", "ports/slack.yaml", "kind: conversation\n", ""),
    ];
    for (name, file, from, to) in cases {
        let root = edited(name, file, from, to);
        let (ok, text) = check(&root);
        assert!(!ok, "[{name}] must be refused:\n{text}");
        assert!(text.contains("  fix: "), "[{name}] no fix offered:\n{text}");
        assert!(text.contains(".yaml:"), "[{name}] no file:line given:\n{text}");
        let lower = text.to_lowercase();
        for word in [
            "enum", "variant", "deserialize", "serde", "unwrap", "panic", "trait", "struct",
            "vec<", "option<", "stack trace", "null pointer", "schema validation failed",
        ] {
            assert!(!lower.contains(word), "[{name}] assumes programming knowledge ('{word}'):\n{text}");
        }
        let _ = std::fs::remove_dir_all(&root);
    }
}
