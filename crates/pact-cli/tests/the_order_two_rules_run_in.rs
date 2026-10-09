//! Which of two rules at one moment goes first, and who decides it.
//!
//! `Chain.from_document` in the Python adapter built its workspace-wide rules
//! with `sorted(declared.items())` — the FILENAMES — three lines under its own
//! comment saying *"Order matters: the chain threads each change into the next,
//! and a redaction that runs after a guard has read the value has redacted
//! nothing"*. Measured: adding `aaa-hide.yaml` put it first in the chain and
//! renaming the same file `zzz-hide.yaml` moved it after the card rule. What a
//! workspace was safe against changed on a rename, and no field an author could
//! write said otherwise — the "significant ordering game" D18 forbids by name.
//!
//! The behaviour is in `adapters/python/src/pact_adapters/interceptors.py`
//! (`Chain.add` sorts on `Interceptor.order`). What this file holds is the half
//! that lives in the specification, because the specification is where an
//! author finds out the field exists:
//!
//! * `interceptor.runs-at` is offered at all — without it the loader refuses the
//!   line and the author's number reaches nothing;
//! * it is a whole number with a floor, so `runs-at: 0` is caught by `pact
//!   check` rather than by the adapter, in the author's own editor;
//! * it is `tier: expert`, because ordering rules against each other is not a
//!   thing a first-time author should be shown;
//! * and its help is readable by someone who cannot write code — it says which
//!   way the numbers go and what must come first, in words, with no type names.
//!
//! The schema edit these are written against is a `spec/schema.yaml` change, and
//! that file has one writer per round. Until it lands, every assertion here
//! names it.

fn repo() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// One setting as the words it is written with, whatever shape it parses to.
///
/// `Node::as_str` alone is not enough, and the case that proves it is the one
/// this file is about: `at-least: 1` parses to a **whole number**
/// (`Value::Int`), so asking for it as words gives nothing back, and a check
/// written on `as_str` would report a setting that is right there as missing —
/// sending whoever read that message to re-edit a specification that already
/// carries it. A setting that exists and a setting that is absent must not look
/// the same to a test whose whole job is to tell them apart.
fn written(node: &pact_doc::Node, want: &str) -> String {
    match &node.value {
        pact_doc::Value::Str(s) => s.clone(),
        pact_doc::Value::Int(n) => n.to_string(),
        other => panic!(
            "`interceptor.runs-at`'s `{want}:` is {}, which nothing here can read as \
             one thing to compare",
            other.kind_name()
        ),
    }
}

/// One setting of `interceptor.runs-at`, or a message saying which edit is missing.
fn says(want: &str) -> String {
    let text = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    let doc = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml"))
        .expect("the specification parses");
    let node = doc
        .get("groups")
        .and_then(pact_doc::Node::as_map)
        .and_then(|g| g.get("interceptor"))
        .and_then(|g| g.node.get("fields"))
        .and_then(pact_doc::Node::as_map)
        .and_then(|f| f.get("runs-at"))
        .unwrap_or_else(|| {
            panic!(
                "`interceptor.runs-at` is not in spec/schema.yaml — apply the field \
                 block from this task's needs_wiring. Without it the loader refuses \
                 the line, so the number an author writes reaches nothing."
            )
        })
        .node
        .get(want)
        .unwrap_or_else(|| panic!("`interceptor.runs-at` has no `{want}:`"))
        .clone();
    written(&node, want)
}

#[test]
fn a_floor_written_as_a_number_is_read_as_one_rather_than_reported_missing() {
    // The one check in this file that does not need the schema edit, and the
    // reason it exists: every other assertion here reads a setting whose value
    // is words, so `as_str` covered all of them and `at-least: 1` — the only
    // number — silently did not. A test that cannot tell "the floor is absent"
    // from "the floor is 1" would have failed the correct integration and told
    // the reader to go and add a line that was already there.
    let text = "at-least: 1\ntier: expert\n";
    let doc = pact_doc::parse_yaml(text, camino::Utf8Path::new("<in this test>")).unwrap();
    assert_eq!(
        doc.get("at-least").and_then(pact_doc::Node::as_str),
        None,
        "a whole number is not words — this is what the old reading tripped over"
    );
    assert_eq!(written(doc.get("at-least").unwrap(), "at-least"), "1");
    assert_eq!(written(doc.get("tier").unwrap(), "tier"), "expert");
}

#[test]
fn the_order_rules_run_in_is_a_number_an_author_writes_and_not_a_filename() {
    assert_eq!(
        says("type"),
        "integer",
        "an order is a number, so a word in it is a mistake"
    );
    // The floor, so `runs-at: 0` is caught in the author's editor rather than in
    // another language in a process they never start. The adapter refuses it
    // too — an adapter is handed a document (invariant P-1) that may never have
    // met the checker — but that refusal arrives far too late to be the first
    // one.
    assert_eq!(
        says("at-least"),
        "1",
        "the earliest a rule can run is the first"
    );
}

#[test]
fn ordering_rules_against_each_other_is_not_offered_to_a_first_time_author() {
    // The same argument `watching_a_run.rs` makes for the two kinds: the safe
    // thing is a beginner's and the sharp thing is not. Every other field of an
    // interceptor is `tier: core` because you cannot write the rule without it.
    // This one you can leave out entirely — `interceptors.order_for` puts hiding
    // in front of everything else on its own — so showing it to somebody writing
    // their first rule is asking them to decide something they have no way to
    // have an opinion about yet.
    assert_eq!(says("tier"), "expert");
    assert!(
        !says("surface").trim().is_empty(),
        "every field declares a surface"
    );
}

#[test]
fn the_help_tells_a_non_coder_which_way_the_numbers_go_and_what_must_come_first() {
    let help = says("help").to_lowercase();
    assert!(
        help.contains("lower numbers run first"),
        "the help must say which direction the numbers go, in those words: {help}"
    );
    assert!(
        help.contains("hides") && help.contains("before"),
        "the help must say that hiding a value runs before anything that reads it: {help}"
    );
    // D13's author cannot write code, so a help text that reads like a type
    // signature teaches nothing.
    //
    // Whole words, not substrings: `int` is inside `into` and `point`, and a
    // check that fails on those teaches the next author to write worse English
    // to get past it.
    let words: Vec<&str> = help
        .split(|c: char| !c.is_ascii_alphanumeric())
        .filter(|w| !w.is_empty())
        .collect();
    for jargon in [
        "integer", "int", "u32", "sort", "sorted", "key", "field", "string", "null",
    ] {
        assert!(
            !words.contains(&jargon),
            "`{jargon}` is jargon a support lead does not read: {help}"
        );
    }
}
