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
//! Three drifts are held, and they are three different mistakes:
//!
//! * a ninth key declared on `AgentSpec` — the claim silently widens, or the key
//!   is neither honoured nor documented;
//! * §7.28 putting a key on the wrong side of its own bound;
//! * the README sentence outgrowing §7.28's list A, which is the original defect
//!   in its purest form.
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
/// reason — so `notDoneHere` can name it on `RunResult.unenforced` — so each is
/// held twice: §7.28 list B must still name it (here), and the port must still
/// report it at run time (`test_the_subset_the_second_port_runs.py`).
const REPORTED: &[(&str, &str)] = &[
    ("interceptors", "interceptors:"),
    ("contextPolicy", "context-policy:"),
    ("policy", "policy:"),
    ("teamwork", "teamwork:"),
    ("settings", "settings.*"),
    ("slo", "slo.*"),
    ("model", "model:"),
    ("watches", "watch/"),
    ("answersWithMode", "answers-with-mode:"),
];

/// How §7.28 and README.md write a key: in backticks, as the author would type
/// it. Comparing on the backticked form rather than the bare one is what stops a
/// row being satisfied by the word appearing in a neighbouring sentence.
fn as_written(spelling: &str) -> String {
    format!("`{spelling}`")
}

/// Every string inside the first `[...]` after `needle`.
fn quoted_list(text: &str, needle: &str) -> Vec<String> {
    let from = text.find(needle).unwrap_or_else(|| panic!("{needle} is gone from {HARNESS}"));
    let open = text[from..].find('[').expect("a list literal") + from;
    let close = text[open..].find(']').expect("a closed list literal") + open;
    text[open..close].split('"').skip(1).step_by(2).map(str::to_string).collect()
}

/// §7.28, from its heading to the next one.
fn subsection() -> String {
    let doc = read(ARCH);
    // Written on one line in the file; matched on its first eight words so a
    // reflow does not break the test for a reason no reader would recognise.
    let head = SUBSECTION.split_whitespace().take(4).collect::<Vec<_>>().join(" ");
    let at = doc.find(&head).unwrap_or_else(|| {
        panic!(
            "{ARCH} has no §7.28.\n  fix: add the subsection `{SUBSECTION}` — README.md links \
             to it, so without it the front page's scope note points at nothing."
        )
    });
    let rest = &doc[at..];
    let end = rest[1..].find("\n### ").map(|i| i + 1).unwrap_or(rest.len());
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
    let end = rest[1..]
        .find("\n**")
        .map(|i| i + 1)
        .unwrap_or(rest.len());
    rest[..end].to_string()
}

#[test]
fn every_key_the_typescript_port_declares_is_either_covered_or_declared_unenforced() {
    // The drift that widens the claim in silence. `AGENT_SPEC_FIELDS` is the one
    // place a field reaches this port at all — `run-trace.ts` refuses a payload
    // key it does not list — so a ninth key arriving there and nowhere else is a
    // key that is neither run, nor reported, nor written down.
    let declared = quoted_list(&read(HARNESS), "AGENT_SPEC_FIELDS");
    assert!(declared.len() > 5, "AGENT_SPEC_FIELDS did not parse: {declared:?}");

    let known: Vec<&str> = COVERED
        .iter()
        .chain(REPORTED)
        .map(|(f, _)| *f)
        .chain(IDENTITY.iter().copied())
        .collect();
    let extra: Vec<&String> = declared.iter().filter(|d| !known.contains(&d.as_str())).collect();
    assert!(
        extra.is_empty(),
        "{HARNESS} declares {:?}, which §7.28 of {ARCH} does not account for.\n  \
         fix: add a row for each to §7.28 list A (the byte-identical claim covers it) or \
         list B (this port reports it on `unenforced`), then add it to COVERED or REPORTED \
         in this file with the spelling an author would type.",
        extra
    );

    let gone: Vec<&str> = known.iter().copied().filter(|k| !declared.contains(&k.to_string())).collect();
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
        if !covered.contains(&written) {
            wrong.push(format!(
                "list A has no row naming {written} (for `{field}`)\n    fix: add a row \
                 `| {written} | what it decides in both ports | the test that holds it |`"
            ));
        }
    }
    for (field, spelling) in REPORTED {
        let written = as_written(spelling);
        if !reported.contains(&written) {
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
    let claim_at = readme.find("byte-identical").expect("checked above");
    let scope = &readme[claim_at..readme.len().min(claim_at + 900)];
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

    // The subsection has to be there and has to carry all three lists. `part`
    // panics with the fix if it is not.
    for letter in ['A', 'B', 'C'] {
        assert!(!part(letter).is_empty());
    }
}
