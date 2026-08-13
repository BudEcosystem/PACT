//! Text written below the `---` line of a markdown file reaches the document,
//! and anything the fences held that could not be read is reported. Neither half
//! of the file is ever silently dropped.
//!
//! A file that opens with `---` is *a set of settings, then prose*. When the part
//! above the closing `---` is not a set of settings — a stray sentence, a
//! bulleted list, a number — the loader had nowhere to put the prose, and put it
//! nowhere. Measured on a two-agent workspace whose `instructions.md` was
//!
//! ```text
//! ---
//! Be brief.
//! ---
//! You are a careful refund desk. NEVER approve a refund over 100 USD.
//! ```
//!
//! ```text
//! $ pact check <ws>
//! OK — <ws> loaded cleanly (8 settings).
//!
//! $ pact show <ws>
//!       "name": "Desk",
//!       "description": "A desk.",
//!       "instructions": "Be brief."
//! ```
//!
//! The refund limit — the one line in the file that exists to stop money going
//! out of the door — is gone, and the checker says the workspace is clean. That
//! is T7 ("no silent loss anywhere") and AC-7.1 broken in the quietest possible
//! way.
//!
//! **WHICH HALF SURVIVES IS ASSERTED, NOT LEFT OPEN, AND THAT IS WHAT MAKES THIS
//! FILE BITE.** The first repair reported the loss and kept the *front matter*,
//! so the sentence was still missing from the document — a green test above a
//! document with a hole in it. The prose is what the slot asked for, so the prose
//! is what arrives; what the fences held is what is refused, in a message that
//! says so. An earlier version of this file asserted only the disjunction *"in
//! the document OR in a diagnostic"* about the sentence alone and never looked at
//! the other half, and under that assertion the opposite repair — fold the body
//! into a fresh map and drop the author's front matter without a word — passed
//! all six tests while `pact check` called the workspace clean.
//!
//! The fuzzer that is meant to catch exactly this class of loss —
//! `adapters/python/tests/test_nothing_vanishes_between_the_file_and_the_document.py`
//! — mutates YAML documents, so a markdown body under a malformed fence is
//! outside its reach by construction. It cannot generate this input at all.
//!
//! These write real files and load them with the real [`Loader`], so what is
//! asserted is what an author's tree actually becomes. What an author is *shown*
//! — the exit status, and one mistake counted once through the whole pipeline —
//! is asserted at the shipped door, in
//! `crates/pact-cli/tests/a_fence_that_is_not_settings_is_one_mistake_told_once.rs`.
//!
//! ## Mutations
//!
//! Each was applied ALONE to a copy of this tree and every test below was run
//! against it, then reverted (source checksum compared before and after). Where a
//! test outside this file also goes red it is named, because that is what makes
//! the pair of them a net rather than two holes.
//!
//! | mutation | what fails here |
//! |---|---|
//! | **The original bug** — in `Markdown::into_node`, drop the diagnostic and end the non-map arm with `Folded::plain(fm)`, the code exactly as it stood | `nothing_the_author_wrote_in_a_markdown_file_vanishes`, `a_self_file_…_invents_no_setting` (+ 4 in `a_fence_that_is_not_settings…`, 1 in `an_unfinished_file…`, 1 in `markdown.rs`) |
//! | **Keep the front matter instead of the prose** — `Folded { node: fm, … }`, the first landed repair: the report is emitted, so an assertion phrased *"reported OR reached"* cannot see it | `nothing_the_author_wrote_in_a_markdown_file_vanishes` (+ `a_list_above_the_line_of_a_field_file_is_told_once`, which goes to two messages) |
//! | **Fold anyway, keeping neither** — build a fresh `Map`, insert the body under `body_field`, return it with no diagnostic. This is the obvious alternative repair, and it passed all six tests of the version of this file that asserted only the disjunction | `nothing_the_author_wrote_in_a_markdown_file_vanishes` on the FRONT-MATTER half, `a_self_file_…_invents_no_setting` |
//! | **Print the kind as a discriminant** — `format!("{:?}", std::mem::discriminant(&fm.value))` for `fm.value.kind_name()`, which is what a build in this tree actually printed at one point (`… is Discriminant(4) instead of a set of settings`) | `nothing_the_author_wrote_in_a_markdown_file_vanishes` (+ all four loss cases at the shipped door) |
//! | **Swap the two spans** so the caret lands on the prose and the note on the fences | `nothing_the_author_wrote_in_a_markdown_file_vanishes` |
//! | **Warn instead of refuse** — `Diagnostic::warning` | `nothing_the_author_wrote_in_a_markdown_file_vanishes` (+ every exit-status assertion at the shipped door) |
//! | **Refuse the empty fence pair** — drop the `Value::Null` arm | `a_fence_pair_holding_nothing_loses_nothing_and_says_nothing` |
//! | **Point the body span at the byte after the fence** — drop `first_line_with_words`, so the caret and the note land on the blank line the convention puts there | `nothing_the_author_wrote_in_a_markdown_file_vanishes` |
//! | **Turn `doc/body-and-field` back into a warning** | `the_body_and_field_conflict_is_refused_once_and_the_discard_is_pinned` |
//! | **Delete the `Position::SelfFile` arm of `Loader::read_file`** (the one mutation in `pact-loader` rather than `pact-doc`) | `a_self_file_whose_fences_are_not_settings_invents_no_setting_to_hold_its_prose` (+ 2 at the shipped door, + `a_markdown_self_file_whose_fences_are_not_settings_names_no_invented_setting`) |

use camino::Utf8PathBuf;
use pact_diag::{Diagnostics, Severity};
use pact_doc::Node;
use pact_loader::Loader;
use std::fs;
use std::sync::atomic::{AtomicU32, Ordering};

static COUNTER: AtomicU32 = AtomicU32::new(0);

/// The line that must never vanish. It is a safety instruction, so "it was only
/// dropped, nothing was corrupted" is not a defence.
const SENTENCE: &str = "NEVER approve a refund over 100 USD";

/// The other half of the file, written into the front matter. Distinct from
/// [`SENTENCE`] on purpose: a repair that keeps one half and loses the other
/// passes any test that only knows about one string.
const TOP: &str = "keep every receipt";

/// The rule this file is about.
const RULE: &str = "doc/front-matter-not-settings";

struct Tree(Utf8PathBuf);

impl Tree {
    fn at(name: &str) -> Utf8PathBuf {
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
            .join(format!("pact-vanish-{name}-{}-{n}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(base.join("agents/desk")).unwrap();
        fs::write(
            base.join("_index.yaml"),
            "name: desk-ws\ndescription: A workspace.\n",
        )
        .unwrap();
        base
    }

    /// A one-agent workspace whose `instructions.md` — a FIELD of the agent — is
    /// exactly `md`.
    fn with_instructions(name: &str, md: &str) -> Self {
        let base = Self::at(name);
        fs::write(
            base.join("agents/desk/agent.yaml"),
            "name: Desk\ndescription: A desk.\n",
        )
        .unwrap();
        fs::write(base.join("agents/desk/instructions.md"), md).unwrap();
        Self(base)
    }

    /// The same workspace where the markdown file is the agent's SELF file: it is
    /// supposed to supply the folder's own settings, not to fill one field.
    fn with_agent_md(name: &str, md: &str) -> Self {
        let base = Self::at(name);
        fs::write(base.join("agents/desk/agent.md"), md).unwrap();
        Self(base)
    }

    fn load(&self) -> (Node, Diagnostics) {
        let mut d = Diagnostics::new();
        let n = Loader::new(self.0.clone())
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

/// One authored file, and what the two halves of it must come to.
struct Case {
    name: &'static str,
    md: String,
    /// A word the author wrote BETWEEN the fences, which is either in the
    /// document or refused out loud.
    top: &'static str,
    /// How the report must describe what was above the line, in the words
    /// `Value::kind_name` gives a non-coder. `None` where the fences hold real
    /// settings and there must be no report at all.
    kind: Option<&'static str>,
}

/// The claim, asserted as an effect on the real document.
///
/// 1. The prose ALWAYS arrives. It is what the slot asked for and it is the half
///    that was being lost.
/// 2. Whatever the fences held either arrives too, or is refused in a message
///    that names the file and says what it turned out to be.
/// 3. One mistake, one message (CHK-12): a refusal is the ONLY thing said about
///    the tree.
fn nothing_vanished(case: &Case) {
    let t = Tree::with_instructions(case.name, &case.md);
    let (node, diags) = t.load();
    let document = node.to_json().to_string();
    let rendered = diags.render();

    assert!(
        document.contains(SENTENCE),
        "{}: the sentence the author wrote below the '---' line is not in the document.\n\
         document: {document}\n{rendered}",
        case.name
    );

    let reported: Vec<_> = diags.items().iter().filter(|d| d.rule == RULE).collect();
    let top = case.top;

    let Some(kind) = case.kind else {
        // The ordinary shape. Both halves are in the document and nothing is
        // said about the file at all.
        assert!(
            document.contains(top),
            "{}: settings above the line still arrive.\ndocument: {document}\n{rendered}",
            case.name
        );
        assert!(diags.is_empty(), "{}: nothing to complain about here.\n{rendered}", case.name);
        return;
    };

    if document.contains(top) {
        // A future reading that finds a home for both halves is a better answer
        // than a refusal, and it is allowed to arrive without editing this test.
        return;
    }

    assert_eq!(
        reported.len(),
        1,
        "{}: '{top}' is not in the document, so it was dropped, and a drop is reported \
         exactly once.\ndocument: {document}\n{rendered}",
        case.name
    );
    assert_eq!(
        diags.items().len(),
        1,
        "{}: CHK-12 — one mistake gets one message, and this tree has one mistake.\n{rendered}",
        case.name
    );

    let d = reported[0];
    assert_eq!(
        d.severity,
        Severity::Error,
        "{}: dropping content is an error, not a warning — a warning leaves `pact check` \
         exiting 0 over a document with a hole in it.\n{rendered}",
        case.name
    );
    assert!(
        d.span.file.as_str().ends_with("instructions.md"),
        "{}: the diagnostic must point at the file, not '{}'.\n{rendered}",
        case.name,
        d.span.file
    );
    assert!(
        d.message.contains("instructions.md"),
        "{}: the message must name the file: {:?}\n{rendered}",
        case.name,
        d.message
    );

    // What the top of the file turned out to be, in the words a non-coder reads.
    // `pact_doc::value` pins that those words are plain language; this pins that
    // this message is where they come out, because a build in this tree once
    // printed `Discriminant(4)` here and no test objected.
    assert!(
        d.message.contains(kind),
        "{}: the message must say the top is {kind}: {:?}\n{rendered}",
        case.name,
        d.message
    );

    // WHERE THE CARET GOES. Under what was refused — line 2 in every fixture
    // here, the first line inside the fences — with a note on the prose that was
    // kept. The message and the underline say the same thing, so neither can
    // drift without the other.
    assert_eq!(
        d.span.line, 2,
        "{}: the caret belongs under what was refused, on line 2.\n{rendered}",
        case.name
    );
    let note = d
        .related
        .first()
        .unwrap_or_else(|| panic!("{}: the prose that was kept is pointed at too\n{rendered}", case.name));
    let sentence_line = line_of(&case.md, SENTENCE);
    assert_eq!(
        note.span.line, sentence_line,
        "{}: the note belongs on the line the kept text starts on ({sentence_line}), and a \
         caret under a blank line is a caret under nothing.\n{rendered}",
        case.name
    );

    // O7.3: and it has to be something a non-coder can type.
    assert!(
        d.fix.contains("---"),
        "{}: the fix must tell the author what to do about the '---' lines: {:?}",
        case.name,
        d.fix
    );
    assert!(
        d.fix.contains("description:"),
        "{}: the fix must show a settings line the author can copy: {:?}",
        case.name,
        d.fix
    );
}

/// 1-based line number of the line `needle` starts on.
fn line_of(text: &str, needle: &str) -> usize {
    let at = text.find(needle).expect("the fixture contains it");
    1 + text[..at].matches('\n').count()
}

/// Every fixture is written in the layout an editor produces — a blank line after
/// the closing fence, which is how this module's own header and the shipped
/// `SKILL.md` are written. The old fixtures all omitted it, and that was the only
/// layout in which the caret happened to land on words.
fn cases() -> Vec<Case> {
    // The leading newline is the blank line the convention puts between the
    // closing fence and the prose.
    let body = format!("\nYou are a careful refund desk. {SENTENCE}.\n");
    vec![
        Case {
            name: "scalar",
            md: format!("---\nBe brief, and {TOP}\n---\n{body}"),
            top: TOP,
            kind: Some("some text"),
        },
        Case {
            // The same file saved by an editor that puts no blank line there.
            // Both layouts, because one of them was all the test used to see.
            name: "scalar-tight",
            md: format!("---\nBe brief, and {TOP}\n---\nYou are a careful refund desk. {SENTENCE}.\n"),
            top: TOP,
            kind: Some("some text"),
        },
        Case {
            name: "list",
            md: format!("---\n- {TOP}\n- log every refund\n---\n{body}"),
            top: TOP,
            kind: Some("a list"),
        },
        Case {
            // A bare figure is neither settings nor prose either, and it exercises
            // a third kind word. `4242` and not `100`, because the sentence itself
            // says 100 and a marker that appears twice proves nothing.
            name: "number",
            md: format!("---\n4242\n---\n{body}"),
            top: "4242",
            kind: Some("a whole number"),
        },
        Case {
            name: "real-settings",
            md: format!("---\ndescription: The desk that will {TOP}\n---\n{body}"),
            top: TOP,
            kind: None,
        },
    ]
}

#[test]
fn nothing_the_author_wrote_in_a_markdown_file_vanishes() {
    for case in cases() {
        nothing_vanished(&case);
    }
}

#[test]
fn a_fence_pair_holding_nothing_loses_nothing_and_says_nothing() {
    // `---` / `---` with nothing between the lines is not front matter: there is
    // nothing above the line to lose, so the file is simply its text and PACT has
    // nothing to say about it. Refusing it refused files that lose nothing — and
    // this is the shape real files are written in. Of the nine markdown files in
    // this repository's vendored research corpus whose front matter is not a set
    // of settings and whose body is not blank, six are this one: opencode's own
    // `empty-frontmatter.md` test fixture, and five pydantic-ai
    // `.github/workflows/shared/*.md` whose fences hold nothing but `#` comments.
    for (name, md) in [
        // Byte-for-byte the opencode fixture at
        // research/repos/filedef/opencode/packages/opencode/test/config/fixtures/empty-frontmatter.md
        // with this file's own sentence as the body.
        ("opencode-shape", format!("---\n---\n\nYou are a careful refund desk. {SENTENCE}.\n")),
        (
            "comments-only",
            format!("---\n# {TOP}, and log every refund\n---\n\nYou are a careful refund desk. {SENTENCE}.\n"),
        ),
    ] {
        let t = Tree::with_instructions(name, &md);
        let (node, diags) = t.load();
        assert!(
            node.to_json().to_string().contains(SENTENCE),
            "{name}: the body is the whole of a file with no front matter.\n{}",
            diags.render()
        );
        assert!(diags.is_empty(), "{name}: this file is not a mistake.\n{}", diags.render());
    }
}

#[test]
fn a_self_file_whose_fences_are_not_settings_invents_no_setting_to_hold_its_prose() {
    // The same file in the other position. `agents/desk/agent.md` was supposed to
    // supply the folder's own settings and supplied none, so it contributes
    // nothing — the answer a self file that would not parse already gets
    // (`pact_loader`'s `load_dir`). Folding its prose in instead put it under
    // `content`, and the author was then told *"'content' is not something an
    // agent can have — fix: Remove it"* about a word they never typed. Measured
    // through the real binary before this: four errors for one mistake.
    let t = Tree::with_agent_md(
        "selffile",
        &format!("---\n- {TOP}\n---\n\nYou are a careful refund desk. {SENTENCE}.\n"),
    );
    let (node, diags) = t.load();
    let desk = node
        .get("agents")
        .and_then(|a| a.get("desk"))
        .unwrap_or_else(|| panic!("the folder is still a field: {}", node.to_json()));
    assert!(
        desk.get("content").is_none(),
        "no setting is invented to hold the prose: {}",
        desk.to_json()
    );
    assert!(
        desk.get(pact_doc::UNLOADED).is_some(),
        "the folder is marked as one whose settings could not be read, so the schema adds \
         nothing to the pile: {}",
        desk.to_json()
    );
    let reported: Vec<_> = diags.items().iter().filter(|d| d.rule == RULE).collect();
    assert_eq!(reported.len(), 1, "and the one mistake is reported once:\n{}", diags.render());
    assert_eq!(
        diags.items().len(),
        1,
        "CHK-12 — and it is the only thing said:\n{}",
        diags.render()
    );
}

#[test]
fn an_unfinished_file_with_no_text_below_the_fences_is_left_alone() {
    // A file whose body is blank is a file the author has not finished, not a
    // mistake. Nothing was dropped, so there is nothing to report — including
    // when what is above it is not settings either. The POSITIVE half matters as
    // much: what the author did write is still in the document, so this case
    // fails if the quiet arm starts eating whole files rather than merely staying
    // silent.
    for (case, md, must_survive) in [
        ("blank-scalar", "---\nBe brief.\n---\n\n   \n", Some("Be brief.")),
        ("blank-empty", "---\n---\n\n", None),
    ] {
        let t = Tree::with_instructions(case, md);
        let (node, diags) = t.load();
        assert!(
            diags.items().iter().all(|d| d.rule != RULE),
            "{case}: an unfinished file must stay silent.\n{}",
            diags.render()
        );
        let instructions = node
            .get("agents")
            .and_then(|a| a.get("desk"))
            .and_then(|d| d.get("instructions"))
            .unwrap_or_else(|| panic!("{case}: the file still contributes its field: {}", node.to_json()));
        if let Some(words) = must_survive {
            assert!(
                instructions.to_json().to_string().contains(words),
                "{case}: what the author did write is still there: {}",
                instructions.to_json()
            );
        }
    }
}

#[test]
fn the_body_and_field_conflict_is_refused_once_and_the_discard_is_pinned() {
    // The neighbouring rule covers the case where the author wrote the body field
    // twice: once at the top, once as prose. BOTH VALUES ARE STILL IN THE FILE and
    // exactly ONE OF THEM IS IN THE DOCUMENT — the comment here used to read
    // "both values survive here — nothing was dropped", which was false of the
    // document, and the rule was a warning, so `pact check` exited 0 over it.
    // Measured on a copy of the shipped worked example with `content: Ask for the
    // receipt.` added to `skills/refund-policy/SKILL.md`: one warning, exit 0,
    // and `pact show` printed a skill with no trace of the sentence below the
    // fence. That is this file's own defect, twenty lines away.
    //
    // So: refused (not remarked on), once, and which value the document keeps is
    // asserted rather than assumed.
    let t = Tree::with_instructions(
        "conflict",
        &format!("---\ncontent: from the top\n---\n\n{SENTENCE}.\n"),
    );
    let (node, diags) = t.load();
    let conflicts: Vec<_> =
        diags.items().iter().filter(|d| d.rule == "doc/body-and-field").collect();
    assert_eq!(conflicts.len(), 1, "expected exactly one conflict report.\n{}", diags.render());
    assert_eq!(
        conflicts[0].severity,
        Severity::Error,
        "one of the two authored values does not reach the document, so nothing runs until \
         the author says which one they meant.\n{}",
        diags.render()
    );
    assert!(
        diags.items().iter().all(|d| d.rule != RULE),
        "the other rule must not double-fire on it.\n{}",
        diags.render()
    );

    let document = node.to_json().to_string();
    assert!(
        document.contains("from the top"),
        "the explicit setting is the one that is kept: {document}"
    );
    assert!(
        !document.contains(SENTENCE),
        "and the prose is NOT in the document — a deliberate, pinned discard, not an \
         accident hidden behind the word 'survive': {document}"
    );
}
