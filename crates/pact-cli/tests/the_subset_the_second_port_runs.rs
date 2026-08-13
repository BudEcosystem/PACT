//! The front page claims one folder runs over seven targets and produces
//! *"byte-identical traces, tool sequences and model-call counts"*. Six of those
//! targets are the Python harness; the seventh is a separate port in another
//! language, and it is smaller. §7.23 of `docs/20-ARCHITECTURE-DRAFT.md` records
//! how that port was made to *report* what it is smaller by — `RunResult.unenforced`,
//! one authored key at a time — and the claim about it stayed unbounded anyway. A
//! reader met one sentence about seven runtimes and, eight keys further into
//! `adapters/typescript/src/harness.ts`, a `notDoneHere` list that contradicts it.
//!
//! §7.28 states the bound as three closed lists. This file is what stops those
//! lists from being prose that decays: the same job `deliberate_refusals.rs` does
//! for `50-NOT-COPIED.md` and `the_worked_example_readme_matches_the_tree.rs` does
//! for the example's map. `pact check` never reads a document about the code, so
//! without a test a document about the code says whatever it likes.
//!
//! Five drifts are held, and they are five different mistakes:
//!
//! * a ninth key declared on `AgentSpec` — the claim silently widens, or the key
//!   is neither honoured nor documented;
//! * §7.28 putting a key on the wrong side of its own bound;
//! * the README sentence outgrowing §7.28's list A, which is the original defect
//!   in its purest form;
//! * the README sentence losing a piece of list B — for a round it named only
//!   `unenforced`, and the documents under `knowledge/` were excluded from the
//!   claim by §7.28 and included by the front page, which is the same defect one
//!   hop on. A reader compares their own folder against the front page;
//! * a row of list B that is not a top-level field going unheld — `asks:` is
//!   written inside `loops:`, `loops:` is in list A, and for a round §7.28 named
//!   the line only in a closing paragraph admitting it was read by nothing. A
//!   stated hole is still a hole, and `REPORTED_INSIDE` is what stops the next
//!   one being stated instead of closed.
//!
//! The fourth was measured and had no test at all: only list A was held against
//! README, so the clause naming `knowledge/` and `unretrieved` could be deleted
//! whole and the suite stayed green. Both halves of the new check were mutated
//! and both bite:
//!
//! ```text
//! $ # README.md: ", nor the documents under `knowledge/` … `unretrieved` …" deleted
//! the note never says `unretrieved`, which §7.28 list B reports 1 row(s) on
//!
//! $ # README.md: "the ten governance keys" → "the nine governance keys"
//! the note says `unenforced` and not how many keys are on it (ten)
//! ```
//!
//! The fifth arrived with a false pass of its own, worth recording because it is
//! the same shape as the one above. The first version of its check asked whether
//! list B *contained* the string `` `asks:` ``, and deleting the row outright left
//! all three tests green — the paragraph above the table says *"the tenth — a loop
//! stage's `asks:`"*, and that satisfied it. A sentence about a row is not a row:
//! the row carries the mechanism letter and the reason. `named_by_a_row` is the
//! fix, and it is now what every positive check in this file uses:
//!
//! ```text
//! $ # docs/20-ARCHITECTURE-DRAFT.md: the `| `asks:` … |` row deleted from list B
//! list B has no row naming `asks:`, which is written inside a key list A covers
//! ```
//!
//! Nothing here executes either port. Agreement between the two is the
//! conformance suite's job (`test_portability.py`, `test_termination.py`), and
//! whether list B still describes what the run REPORTS is
//! `adapters/python/tests/test_the_subset_the_second_port_runs.py`, which runs
//! the port and reads `unenforced` off it. That half deliberately does not live
//! here: a source-level grep for `spec.<field>` inside `notDoneHere` passes on a
//! branch that has been deleted, because the field is still named in the
//! neighbouring message — measured, with `if (spec.model)` replaced by
//! `if (false)`, and it went green. This file holds the documents; that one holds
//! the behaviour.

use std::path::{Path, PathBuf};

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn read(rel: &str) -> String {
    let p = repo().join(rel);
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

const HARNESS: &str = "adapters/typescript/src/harness.ts";
const ARCH: &str = "docs/20-ARCHITECTURE-DRAFT.md";
const SUBSECTION: &str = "### 7.28 What \"byte-identical across all seven targets\" covers, \
                          and what it does not";

/// The keys the byte-identical claim COVERS: both ports read them from the
/// author's own field names and the trace turns on them.
///
/// Each pair is `(the field on `AgentSpec`, how an author spells it)`. The
/// spelling is written here rather than derived because the two sides genuinely
/// have two vocabularies — `maxSteps` is `steps-at-most` inside the `limits:`
/// block, `loops` is the workspace's `loops/` folder reached through the agent's
/// `loop:` line — and a reader who cannot write code is owed the line they would
/// open, not the identifier a port happens to use. Several fields may share one
/// spelling, which is why §7.28's list A has six rows for eight fields.
const COVERED: &[(&str, &str)] = &[
    ("instructions", "instructions:"),
    ("tools", "tools:"),
    ("skills", "skills:"),
    ("team", "team:"),
    ("maxSteps", "limits:"),
    ("limits", "limits:"),
    ("loop", "loop:"),
    ("loops", "loop:"),
    ("answersWith", "answers-with:"),
    // A7. In list A and not list B: both ports refuse a `must-cite:` corpus they
    // could not read, before a model call, in the same words. The Python side
    // had it alone for as long as it took the conformance driver to notice —
    // and the driver only noticed once the payload started carrying the key,
    // which is the other half of what this file is for.
    ("knowledge", "knowledge:"),
];

/// Declared, and no row anywhere, because nothing about the run turns on it.
/// `name:` is who the agent is; two agents differing only in it produce the same
/// trace over the same script. It is separated out rather than filed under
/// COVERED so that neither §7.28 nor the README has to carry a row whose "what
/// it decides" cell would read *"nothing"*.
const IDENTITY: &[&str] = &["name"];

/// The keys the claim does NOT cover. Each is declared on `AgentSpec` for one
/// reason — so the run can name it — so each is held twice: §7.28 list B must
/// still name it (here), and the port must still report it at run time
/// (`test_the_subset_the_second_port_runs.py`).
///
/// Nine of the ten rows in THIS table are named on `RunResult.unenforced`, and
/// `REPORTED_INSIDE` below adds a tenth to that channel — which is why the front
/// page counts ten and this table has ten rows for a different reason. The
/// remaining row here, `knowledge/`,
/// is named on `RunResult.unretrieved` — the fifth honesty channel, which is a
/// fifth for the reason `never_reached` is not `unmetered`: *the rule could not
/// be evaluated* sends the reader to the rule, *the corpus was never read* sends
/// them to whoever runs the thing. WHICH channel a row lands on is not held
/// here, because nothing here executes the port; it is held by
/// `adapters/python/tests/test_a_corpus_the_second_port_never_looked_in_is_not_silent.py`,
/// which runs both ports over one corpus and compares the sentence.
///
/// `knowledge/` is spelt with the folder and `knowledge:` with the colon on
/// purpose, and they are two different rows about one key — the same shape as
/// `team:` in list A against `teamwork:` here. The colon is the declaration,
/// whose `must-cite:` half both ports carry out identically; the folder is the
/// documents, which this port cannot open. Spelling them alike would make one of
/// the two rows unwritable, since list A and list B may not name the same string.
///
/// The third column is the CHANNEL the run reports the row on, and it is here so
/// the README has something to be held against. A channel with several rows is
/// written on the front page as a count — *"the ten governance keys the
/// TypeScript port reports on `unenforced`"* — and a channel with one row is
/// written by naming it, because *"the one key on `unretrieved`"* tells a reader
/// nothing they can look for. `README_CHANNELS` turns that into an assertion.
const REPORTED: &[(&str, &str, &str)] = &[
    ("interceptors", "interceptors:", "unenforced"),
    ("contextPolicy", "context-policy:", "unenforced"),
    ("policy", "policy:", "unenforced"),
    ("teamwork", "teamwork:", "unenforced"),
    ("settings", "settings.*", "unenforced"),
    ("slo", "slo.*", "unenforced"),
    ("model", "model:", "unenforced"),
    ("watches", "watch/", "unenforced"),
    ("answersWithMode", "answers-with-mode:", "unenforced"),
    // A7, the other key on both sides of the bound. `must-cite:` is list A — the
    // turn is refused before a model call in the same words — and the documents
    // are here, because nothing on this port looks anything up in them. Measured
    // before the row existed: `examples/answers-from-documents` with
    // `must-cite: no` answered *"25 days."* on both ports, and only the reference
    // one said the handbook had never been opened.
    //
    // On `unretrieved` and not `unenforced`, because the recipients differ:
    // every sentence on `unenforced` invites an edit to the author's own file,
    // and there is nothing in a correctly-written `knowledge:` block to edit —
    // the only person who can act is whoever chose the runtime.
    ("knowledge", "knowledge/", "unretrieved"),
];

/// Rows of list B whose key is NOT a top-level `AgentSpec` field, because the
/// author writes it INSIDE one that list A covers.
///
/// One row so far: a loop stage's `asks:`. The workspace's `loops:` block arrives
/// whole — that is list A's `loop:` row, and the stage path really is
/// byte-identical — and inside it a `does: ask-someone` stage names WHICH
/// question a person is put. `loops.ts` parses it into `Phase.asks`; this port
/// has no durable suspension to put a question into, so the line is read and
/// nobody is asked it.
///
/// Held apart from `REPORTED` for exactly one reason: the first test cross-checks
/// `REPORTED` against `AGENT_SPEC_FIELDS`, and `asks` is not a field there and
/// must not become one — a top-level `asks:` is not a thing an author can write.
/// Everything else about the row is identical and is checked identically: §7.28
/// list B must name it, list A must not, and README's count for the channel
/// includes it. What the RUN says is
/// `adapters/python/tests/test_the_subset_the_second_port_runs.py`, which drives
/// a loop with such a stage through `run-trace.ts` and reads `unenforced`.
///
/// For a round this row was not a row: §7.28 ended with a paragraph stating the
/// hole instead — *"read by nothing, and `notDoneHere` cannot name it"* — which
/// is a governance line dropped in silence written down rather than fixed. The
/// close was three lines at `notDoneHere`'s caller, where the resolved loop is
/// already in scope.
const REPORTED_INSIDE: &[(&str, &str)] = &[("asks:", "unenforced")];

/// English for a small count, because the front page writes the number in words
/// — *"the ten governance keys the TypeScript port reports on `unenforced`"* —
/// and a reader comparing their folder against the claim is reading a sentence,
/// not a table.
fn word_for(n: usize) -> String {
    const WORDS: &[&str] = &[
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve",
    ];
    WORDS
        .get(n)
        .map(|w| w.to_string())
        .unwrap_or_else(|| n.to_string())
}

/// The channels list B routes to, each with how many rows it carries, in the
/// order they first appear above.
fn channels() -> Vec<(&'static str, usize)> {
    let mut out: Vec<(&str, usize)> = Vec::new();
    // Both tables, because the front page counts REPORTS and not fields. A row
    // written inside a loop is one more line the reader gets back from a run.
    let all = REPORTED
        .iter()
        .map(|(_, _, c)| *c)
        .chain(REPORTED_INSIDE.iter().map(|(_, c)| *c));
    for channel in all {
        match out.iter_mut().find(|(c, _)| *c == channel) {
            Some((_, n)) => *n += 1,
            None => out.push((channel, 1)),
        }
    }
    out
}

/// How §7.28 and README.md write a key: in backticks, as the author would type
/// it. Comparing on the backticked form rather than the bare one is what stops a
/// row being satisfied by the word appearing in a neighbouring sentence.
fn as_written(spelling: &str) -> String {
    format!("`{spelling}`")
}

/// Whether one of list A's or list B's TABLE ROWS names the key — not merely
/// whether the letters appear somewhere in the part.
///
/// Measured, on the first version of this check: deleting the `asks:` row from
/// list B outright left all three tests green, because the paragraph above the
/// table says *"the tenth — a loop stage's `asks:`"* and a plain `contains` over
/// the whole part found it there. A sentence about a row is not a row: the row
/// carries the mechanism letter and the reason the port is smaller, and a reader
/// sent to the list to find out why their line does nothing needs those two
/// cells, not a mention in passing.
///
/// A row is a line beginning `|`, which is how every list in §7.28 is written.
fn named_by_a_row(part: &str, written: &str) -> bool {
    part.lines()
        .filter(|l| l.trim_start().starts_with('|'))
        .any(|l| l.contains(written))
}

/// Every string inside the first `[...]` after `needle`.
fn quoted_list(text: &str, needle: &str) -> Vec<String> {
    let from = text
        .find(needle)
        .unwrap_or_else(|| panic!("{needle} is gone from {HARNESS}"));
    let open = text[from..].find('[').expect("a list literal") + from;
    let close = text[open..].find(']').expect("a closed list literal") + open;
    text[open..close]
        .split('"')
        .skip(1)
        .step_by(2)
        .map(str::to_string)
        .collect()
}

/// §7.28, from its heading to the next one.
fn subsection() -> String {
    let doc = read(ARCH);
    // Written on one line in the file; matched on its first eight words so a
    // reflow does not break the test for a reason no reader would recognise.
    let head = SUBSECTION
        .split_whitespace()
        .take(4)
        .collect::<Vec<_>>()
        .join(" ");
    let at = doc.find(&head).unwrap_or_else(|| {
        panic!(
            "{ARCH} has no §7.28.\n  fix: add the subsection `{SUBSECTION}` — README.md links \
             to it, so without it the front page's scope note points at nothing."
        )
    });
    let rest = &doc[at..];
    let end = rest[1..]
        .find("\n### ")
        .map(|i| i + 1)
        .unwrap_or(rest.len());
    rest[..end].to_string()
}

/// The `**A — …**`, `**B — …**` or `**C — …**` part of §7.28.
fn part(letter: char) -> String {
    let text = subsection();
    let open = format!("**{letter} — ");
    let at = text.find(&open).unwrap_or_else(|| {
        panic!("§7.28 has lost its `{open}…` list — the three lists are what makes it a bound")
    });
    let rest = &text[at..];
    let end = rest[1..].find("\n**").map(|i| i + 1).unwrap_or(rest.len());
    rest[..end].to_string()
}

#[test]
fn every_key_the_typescript_port_declares_is_either_covered_or_declared_unenforced() {
    // The drift that widens the claim in silence. `AGENT_SPEC_FIELDS` is the one
    // place a field reaches this port at all — `run-trace.ts` refuses a payload
    // key it does not list — so a ninth key arriving there and nowhere else is a
    // key that is neither run, nor reported, nor written down.
    let declared = quoted_list(&read(HARNESS), "AGENT_SPEC_FIELDS");
    assert!(
        declared.len() > 5,
        "AGENT_SPEC_FIELDS did not parse: {declared:?}"
    );

    let known: Vec<&str> = COVERED
        .iter()
        .map(|(f, _)| *f)
        .chain(REPORTED.iter().map(|(f, _, _)| *f))
        .chain(IDENTITY.iter().copied())
        .collect();
    let extra: Vec<&String> = declared
        .iter()
        .filter(|d| !known.contains(&d.as_str()))
        .collect();
    assert!(
        extra.is_empty(),
        "{HARNESS} declares {:?}, which §7.28 of {ARCH} does not account for.\n  \
         fix: add a row for each to §7.28 list A (the byte-identical claim covers it) or \
         list B (this port reports it on `unenforced`), then add it to COVERED or REPORTED \
         in this file with the spelling an author would type.",
        extra
    );

    let gone: Vec<&str> = known
        .iter()
        .copied()
        .filter(|k| !declared.contains(&k.to_string()))
        .collect();
    assert!(
        gone.is_empty(),
        "§7.28 of {ARCH} describes {:?}, and {HARNESS} no longer declares them.\n  \
         fix: delete the row from §7.28 and the entry from this file — a bound that names \
         a field the port has never heard of tells a reader less than no bound at all.",
        gone
    );
}

#[test]
fn the_subsection_that_bounds_the_claim_names_every_key_on_the_right_side_of_it() {
    // Both directions of the same drift, held against the two lists rather than
    // against the whole subsection — a key named in the prose of list C while
    // sitting in `notDoneHere` would otherwise pass by accident.
    let covered = part('A');
    let reported = part('B');
    let mut wrong = Vec::new();

    for (field, spelling) in COVERED {
        let written = as_written(spelling);
        if !named_by_a_row(&covered, &written) {
            wrong.push(format!(
                "list A has no row naming {written} (for `{field}`)\n    fix: add a row \
                 `| {written} | what it decides in both ports | the test that holds it |`"
            ));
        }
    }
    for (field, spelling, _) in REPORTED {
        let written = as_written(spelling);
        if !named_by_a_row(&reported, &written) {
            wrong.push(format!(
                "list B has no row naming {written} (for `{field}`)\n    fix: add a row \
                 `| {written} | the mechanism letter | why it is absent here |`"
            ));
        }
        // `team:` is the one key on both sides — offered here, not runnable here
        // — and it is in COVERED under that spelling, not this one. Any REPORTED
        // spelling turning up in list A means a key was carried out and the
        // section was not moved with it.
        if covered.contains(&written) {
            wrong.push(format!(
                "{written} is in list A, and this port reports it as unenforced\n    fix: \
                 move the row to list B, or delete the `notDoneHere` branch because the port \
                 now does it"
            ));
        }
    }
    // The rows written INSIDE a key list A covers. Both directions again, and the
    // second one bites harder here than anywhere else in the file: `asks:` lives
    // inside `loops:`, and `loops:` is in list A, so a reader who found `asks:`
    // named up there would conclude the question is put to somebody on both
    // ports. It is put on one.
    for (spelling, _) in REPORTED_INSIDE {
        let written = as_written(spelling);
        if !named_by_a_row(&reported, &written) {
            wrong.push(format!(
                "list B has no row naming {written}, which is written inside a key list A \
                 covers\n    fix: add a row `| {written} … | the mechanism letter | why it is \
                 absent here |` — a line the run REPORTS and the bound does not mention is a \
                 bound that undercounts what this port is smaller by"
            ));
        }
        if covered.contains(&written) {
            wrong.push(format!(
                "{written} is in list A, and this port reports it as unenforced\n    fix: \
                 list A is the byte-identical claim; leave the row in list B, or delete the \
                 report at `notDoneHere`'s caller because the port now does it"
            ));
        }
    }
    assert!(
        wrong.is_empty(),
        "§7.28 of {ARCH} does not describe {HARNESS}:\n  {}",
        wrong.join("\n  ")
    );
}

#[test]
fn the_front_page_claim_names_its_own_scope_and_points_at_the_section_that_states_it() {
    // The original defect: README.md:80-82 asserted byte-identical traces over
    // seven targets with no qualification at all, while the seventh honours a
    // strict subset. A reader who greps the claim has to land on its bound.
    let readme = read("README.md");
    assert!(
        readme.contains("byte-identical"),
        "README.md no longer makes the byte-identical claim — delete this test with it"
    );
    assert!(
        readme.contains("docs/20-ARCHITECTURE-DRAFT.md") && readme.contains("§7.28"),
        "README.md makes the byte-identical claim and does not send the reader to its scope.\n  \
         fix: after the claim, add a sentence naming the keys it covers and linking \
         `[§7.28 …](docs/20-ARCHITECTURE-DRAFT.md)`."
    );

    // And the sentence has to list what list A lists. A scope note that says
    // "bounded" without saying "bounded to what" is the same defect one hop on.
    //
    // Read with the line breaks flattened, because the paragraph is hard-wrapped
    // and *"the ten governance keys the TypeScript port reports on\n`unenforced`"*
    // is one phrase to every reader of it.
    let claim_at = readme.find("byte-identical").expect("checked above");
    let window = &readme[claim_at..readme.len().min(claim_at + 900)];
    let scope = window.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut unnamed = Vec::new();
    for (_, spelling) in COVERED {
        let written = as_written(spelling);
        if !scope.contains(&written) && !unnamed.contains(&written) {
            unnamed.push(written);
        }
    }
    assert!(
        unnamed.is_empty(),
        "README.md's scope note omits {unnamed:?}, which §7.28 list A says the claim covers.\n  \
         fix: name every one of them in the sentence beside the claim — a reader comparing \
         their own folder against the claim reads the front page, not the architecture."
    );

    // And it has to say where the EXCLUDED half is reported. List B routes to two
    // channels, not one — ten rows to `unenforced` and `knowledge/` to
    // `unretrieved` — and for a round the front page named only the first, which
    // told a reader the documents under `knowledge/` were inside the claim while
    // §7.28 said they were outside it. This clause was the one of the four
    // artifacts nothing held: it could be deleted and the whole suite stayed
    // green.
    //
    // A channel carrying several rows is checked on its COUNT, because that is
    // how the sentence writes it and because an eleventh governance key landing
    // on `unenforced` has to move the front page too. A channel carrying one row is
    // checked on the row's own spelling, because "the one key on `unretrieved`"
    // is not something a reader can go and look at.
    let plain: Vec<String> = scope
        .split(|c: char| !c.is_alphanumeric())
        .map(str::to_lowercase)
        .collect();
    let mut silent = Vec::new();
    for (channel, rows) in channels() {
        let named = as_written(channel);
        if !scope.contains(&named) {
            silent.push(format!(
                "the note never says {named}, which §7.28 list B reports {rows} row(s) on\n    \
                 fix: name the channel in the sentence beside the claim — a reader told what \
                 is excluded and not where the run says so has to go looking for it"
            ));
            continue;
        }
        if rows > 1 {
            let count = word_for(rows);
            if !plain.contains(&count) {
                silent.push(format!(
                    "the note says {named} and not how many keys are on it ({count})\n    \
                     fix: write `the {count} governance keys … on {named}` — the count moved \
                     when list B did, and a front page that undercounts the exclusions \
                     overstates the claim"
                ));
            }
        } else {
            let (_, spelling, _) = REPORTED
                .iter()
                .find(|(_, _, c)| *c == channel)
                .expect("counted above");
            let written = as_written(spelling);
            if !scope.contains(&written) {
                silent.push(format!(
                    "the note says {named} and never says {written}, the only row on it\n    \
                     fix: name it — one row is too few to write as a count, and a channel \
                     with nothing named on it reads as a footnote rather than an exclusion"
                ));
            }
        }
    }
    assert!(
        silent.is_empty(),
        "README.md's scope note does not account for §7.28 list B:\n  {}",
        silent.join("\n  ")
    );

    // And the count has to say what it is a count OF. Measured on a real run
    // through `run-trace.ts`: a document carrying `team:`, an asking stage and
    // two unread `limits:` keys came back with FOUR lines on `unenforced`, none
    // of them a tenth of anything — `team:` (which is inside the claim), the
    // `asks:` line, and one `limits.<key>` line each. A front page that says
    // *"the ten governance keys the TypeScript port reports on `unenforced`"*
    // and stops there is exact about a number and wrong about the channel, and a
    // reader counting lines off their own run finds a fifth and concludes the
    // bound has drifted.
    //
    // Read over a WIDER window than the checks above, deliberately: those hold
    // the claim's own sentence and widening their window would make them easier
    // to satisfy, which is the wrong direction. This one is a separate sentence
    // that follows the link, so it gets its own reach and none of theirs.
    let after = &readme[claim_at..readme.len().min(claim_at + 1600)];
    let note = after.split_whitespace().collect::<Vec<_>>().join(" ");
    for owed in ["`limits.`", "`team:`"] {
        assert!(
            note.contains(owed),
            "README.md counts the excluded keys on `unenforced` and never says {owed}, which \
             a real run also puts on that channel.\n  \
             fix: after the link to §7.28, say that the ten counts the EXCLUDED KEYS and not \
             the lines a run prints — `team:` is inside the claim and reported anyway, and \
             every `limits:` key this port does not read gets a line under its own `limits.` \
             prefix. An exact number attached to the wrong noun is a claim that fails the \
             first reader who checks it."
        );
    }

    // The subsection has to be there and has to carry all three lists. `part`
    // panics with the fix if it is not.
    for letter in ['A', 'B', 'C'] {
        assert!(!part(letter).is_empty());
    }
}
