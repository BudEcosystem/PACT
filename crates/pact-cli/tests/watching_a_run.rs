//! Watching a run is an author's power, not a host's `[R6 §7.13 gap (1)]`.
//!
//! `interceptors:` — the half of the event lattice that CHANGES things — has
//! been authorable in YAML for several rounds, and `pact check` holds its
//! `when:` to the three closed lists. The half that only LOOKS had no authoring
//! surface at all: `Bus.on(pattern, fn)` takes a Python callable, so watching a
//! run was a HOST capability. That is the wrong way round twice over —
//! observing is the strictly safer power, and it is the one D14 ("no capability
//! may require author code") could not reach.
//!
//! What these hold, that nothing else does:
//!
//! * the `watch/` document in the worked example loads, so the fixture §7.13
//!   names actually exists;
//! * a mistake in it is refused by the SAME tool, at the SAME line, with the
//!   SAME rule as the same mistake in an interceptor — the observe half is not
//!   a second-class citizen of the checker;
//! * the address vocabulary is written ONCE and pointed at, so the next thing
//!   that happens is one row rather than two;
//! * the safe half is offered to a beginner and the dangerous half is not,
//!   which is the entire argument for their being two kinds.
//!
//! The two edits this file was written against have landed: the `watch` group is
//! in `spec/schema.yaml`, and the worked example's document is at
//! `examples/refund-desk/watch/tool-calls.yaml` rather than behind the dot the
//! loader skips. The failure messages below still name which of the two would be
//! missing, so a change that removed either says so instead of failing on a
//! parse.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn example() -> String {
    repo().join("examples/refund-desk").to_string_lossy().into_owned()
}

/// Copy the example and apply one edit, returning the temp root.
fn broken(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-watch-{name}-{}", std::process::id()));
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

#[test]
fn the_worked_example_says_what_to_write_down_and_still_loads_cleanly() {
    // The fixture §7.13's gap (1) names, present and loading: "an authored
    // `watch:` document naming an address and a destination". Held here rather
    // than only in the adapter tests, because the first thing that has to be
    // true of an authoring surface is that `pact check` — the one tool D13's
    // reader runs — accepts a correct one.
    let out = pact().args(["check", &example()]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "the worked example does not load. If this says \"'watch' is not \
         something a workspace can have\", the `watch` group from this round's \
         needs_wiring has not been added to spec/schema.yaml yet:\n{text}"
    );

    let shown = pact().args(["show", &example()]).output().expect("runs");
    let doc: serde_json::Value = serde_json::from_slice(&shown.stdout).expect("`pact show` is JSON");
    let watch = &doc["watch"]["tool-calls"];
    assert_eq!(watch["when"], "step.tool.completed", "{doc:#}");
    assert_eq!(watch["writes-to"], "tool-calls.jsonl", "{doc:#}");
}

#[test]
fn a_watch_that_names_a_moment_that_does_not_exist_is_refused_where_the_author_typed_it() {
    // The mistake the schema's own help text used to invite: `turn.answer.after`
    // is not an address, and for a round `interceptor.when` was `type: text`, so
    // `pact check` said it was fine and the refusal happened later, in another
    // language, in a process the author never starts. `type: event-address`
    // closed that for the half that changes things; this holds it closed for the
    // half that watches.
    let root = broken("bad-address", "watch/tool-calls.yaml", "step.tool.completed", "turn.answer.after");
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(!out.status.success(), "a watch on a moment that does not exist must be refused:\n{text}");
    assert!(text.contains("watch/tool-calls.yaml:"), "must name the file and line:\n{text}");
    assert!(text.contains("  fix: "), "must offer a fix:\n{text}");
    // The fix names every word that IS a thing that happens, plus the author's
    // own escape — otherwise the author is refused and stuck.
    for thing in ["message", "reasoning", "tool", "approval", "compaction", "stage", "limit"] {
        assert!(text.contains(thing), "the fix must offer '{thing}':\n{text}");
    }
    assert!(text.contains("x-"), "the fix must mention the author's own prefix:\n{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_watch_on_a_well_formed_address_that_nothing_ever_reaches_is_refused_too() {
    // Well-formed is not the same as REACHED, and for a round only the first
    // question was asked. `session.tool.completed` is three good words in the
    // right order: `session` is a part, `tool` is a thing, `completed` is a
    // moment — so `pact check` printed "OK — loaded cleanly (468 settings)" and
    // exited 0, while `Watches.from_document` refused the identical file with
    // the file, the line and the three moments a tool really has. The author's
    // own tool said the file was fine and the record was silently never written,
    // which is the "loads and does nothing" failure `type: event-address` was
    // added to end, surviving one hop along.
    //
    // Closed with DATA, not a branch: `reaches:` sits beside `parts:` on the
    // field in `spec/schema.yaml`, so the next moment a run starts emitting is
    // one line of YAML in the same file as the vocabulary it is spelled from.
    let root = broken("unreachable", "watch/tool-calls.yaml", "step.tool.completed", "session.tool.completed");
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(!out.status.success(), "a watch nothing ever reaches must be refused:\n{text}");
    assert!(text.contains("watch/tool-calls.yaml:"), "must name the file and line:\n{text}");
    assert!(text.contains("rule: schema/nothing-happens-there"), "{text}");
    // The moments that same THING really has — a short list an author can act
    // on, not the whole lattice.
    assert!(
        text.contains("step.tool.cancelled, step.tool.completed, step.tool.started"),
        "the fix must offer the moments a tool really has:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_moments_a_watch_may_name_are_the_ones_the_harness_really_emits() {
    // The schema's `reaches:` list and `watches.py`'s `EMITTED` tuple are two
    // copies of one fact, and this is what keeps them one fact. They cannot be
    // folded into a single copy: an adapter is handed the loaded document and
    // never the specification (invariant P-1), so the executing side has to
    // carry its own — but a copy nothing compares is a copy that drifts, and the
    // drift would show up as `pact check` accepting an address the harness then
    // refuses, which is exactly the failure the `reaches:` list was added to end.
    let schema = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let doc = pact_doc::parse_yaml(&schema, camino::Utf8Path::new("spec/schema.yaml")).unwrap();
    let listed: Vec<String> = doc
        .get("groups")
        .and_then(|g| g.get("watch"))
        .and_then(|w| w.get("fields"))
        .and_then(|f| f.get("when"))
        .and_then(|w| w.get("reaches"))
        .and_then(pact_doc::Node::as_list)
        .expect("watch.when carries a `reaches:` list")
        .iter()
        .filter_map(|n| n.as_str().map(str::to_string))
        .collect();

    let python =
        std::fs::read_to_string(repo().join("adapters/python/src/pact_adapters/watches.py"))
            .unwrap();
    let block = python
        .split_once("EMITTED: tuple[str, ...] = (")
        .expect("watches.py declares EMITTED")
        .1
        .split_once(')')
        .unwrap()
        .0;
    let emitted: Vec<String> = block
        .split('"')
        .skip(1)
        .step_by(2)
        .map(str::to_string)
        .collect();

    assert!(!emitted.is_empty(), "nothing parsed out of watches.py — it changed shape");
    assert_eq!(
        listed, emitted,
        "the schema and the harness disagree about which moments a run reaches"
    );
}

#[test]
fn the_observe_half_is_checked_by_the_same_tool_and_the_same_rule_as_the_change_half() {
    // The whole claim of reusing `type: event-address` rather than writing a
    // second vocabulary: one mistake, one rule name, one shape of message,
    // whichever half of the lattice it was typed into. Two rules for one mistake
    // is how the two halves come to disagree about what an address is.
    let rule_of = |text: &str| -> String {
        // The rule of the first PROBLEM. It used to be the first `rule:` line of
        // any kind, which was the same thing until a NOTE could come first —
        // §8.3a rule 4 says, of a skill, how many written rules it holds, and
        // `skills/` sorts before `watch/`. A fact the author asked to be told is
        // not the mistake under test.
        let mut a_note = false;
        text.lines()
            .find_map(|l| {
                let t = l.trim();
                if t.starts_with("note: ") {
                    a_note = true;
                } else if t.starts_with("error: ") || t.starts_with("warning: ") {
                    a_note = false;
                }
                (!a_note).then(|| t.starts_with("rule: ").then(|| t.to_string())).flatten()
            })
            .unwrap_or_else(|| panic!("no rule named in:\n{text}"))
    };

    let watched = broken("same-rule-w", "watch/tool-calls.yaml", "step.tool.completed", "turn.answer.after");
    let a = pact().args(["check", &watched]).output().unwrap();
    let intercepted =
        broken("same-rule-i", "interceptors/redact-card-numbers.yaml", "step.message.before", "turn.answer.after");
    let b = pact().args(["check", &intercepted]).output().unwrap();

    let (a, b) = (String::from_utf8_lossy(&a.stdout), String::from_utf8_lossy(&b.stdout));
    assert_eq!(rule_of(&a), rule_of(&b), "one mistake, two rule names:\n{a}\n{b}");
    assert_eq!(rule_of(&a), "rule: schema/not-a-moment");
    let _ = std::fs::remove_dir_all(&watched);
    let _ = std::fs::remove_dir_all(&intercepted);
}

#[test]
fn the_address_vocabulary_is_written_once_and_the_watching_kind_points_at_it() {
    // The comment above `interceptor.when` is explicit: "The three closed lists
    // ARE the vocabulary — nothing anywhere else holds a copy." A second kind
    // binding to the same addresses is the first real chance to break that, and
    // a copy would mean the next thing that happens has to be added twice and
    // can be added in one place only.
    //
    // Held on the FILE and not on the loaded schema, because a YAML alias
    // resolves before anything downstream can tell the two apart — which is the
    // point, and also why nothing but the text can say whether somebody typed
    // the list out again.
    let schema = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    assert_eq!(
        schema.matches("part: [session, turn, step, action]").count(),
        1,
        "the address vocabulary is written more than once"
    );
    assert!(
        schema.matches("type: event-address").count() >= 2,
        "no second kind binds to an address, so the observe half has no surface"
    );
    assert!(
        schema.contains("parts: &the-address-vocabulary")
            && schema.contains("parts: *the-address-vocabulary"),
        "the second kind should point at the one copy, not carry its own"
    );
}

#[test]
fn watching_a_run_is_offered_to_a_beginner_and_changing_one_is_not() {
    // The reason these are two kinds and not one kind with an empty `may:`.
    //
    // A watch cannot hide a value, cannot stop the run and cannot send it
    // somewhere else, so there is nothing to review before somebody writes one
    // and every field of it is `tier: core`. An interceptor can do all three, so
    // the workspace field that carries them is `tier: expert`. Folded into one
    // kind, that distinction has nowhere to live — and turning a thing that
    // looks into a thing that changes would be one word added to a list.
    let text = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let doc = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml"))
        .expect("the specification parses");
    let groups = doc.get("groups").and_then(pact_doc::Node::as_map).expect("groups:");

    let fields_of = |group: &str| -> &pact_doc::Map {
        groups
            .get(group)
            .and_then(|g| g.node.get("fields"))
            .and_then(pact_doc::Node::as_map)
            .unwrap_or_else(|| panic!("no `{group}` group — apply the schema edit from needs_wiring"))
    };
    let says = |group: &str, field: &str, want: &str| -> String {
        fields_of(group)
            .get(field)
            .and_then(|f| f.node.get(want))
            .and_then(pact_doc::Node::as_str)
            .unwrap_or_else(|| panic!("{group}.{field} has no `{want}:`"))
            .to_string()
    };

    assert_eq!(says("workspace", "watch", "tier"), "core", "watching is the beginner's half");
    assert_eq!(says("workspace", "interceptors", "tier"), "expert", "changing things is not");

    let watch = fields_of("watch");
    assert!(watch.len() >= 3, "a watch needs a description, a moment and a destination");
    for name in watch.keys() {
        assert_eq!(says("watch", name, "tier"), "core", "watch.{name} is not a beginner's field");
        assert!(!says("watch", name, "help").trim().is_empty(), "watch.{name} has no help");
        assert!(!says("watch", name, "surface").trim().is_empty(), "watch.{name} has no surface");
    }
    // And there is no `may:` on it — the absence IS the guarantee. A watch with
    // a power list would be an interceptor, and the one word that turned it into
    // one would be typed into a document nobody thought needed reviewing.
    assert!(watch.get("may").is_none(), "a watch must have nothing it `may` do");
}
