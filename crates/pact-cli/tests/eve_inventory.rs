//! The acceptance clause is a count: *every one of Eve's 80 capabilities is
//! either (a) expressible in PACT's schema, (b) a runtime concern the spec
//! declares and delegates, or (c) listed in `50-NOT-COPIED.md` with a reason.
//! **No fourth category.**
//!
//! `deliberate_refusals.rs` holds the (c) column to a bar — a reason that is a
//! constraint, a replacement a non-coder can take. What it cannot do is count.
//! It checks the *shape* of the refusals that were written down and has no way
//! to notice a capability nobody wrote down at all, which is precisely what the
//! fourth category is: not a bad row, an absent one.
//!
//! So the inventory itself is the artifact under test. `eve-capabilities.md`
//! numbers every capability read out of Eve's tree, names the file and symbol it
//! came from, and gives it one letter. This file fails when:
//!
//! * a row carries two letters or none — the fourth category, arriving as an
//!   editing accident rather than a decision;
//! * a row cites a source path that is no longer in the corpus, which is how an
//!   inventory starts describing a framework that has moved on;
//! * a (c) row points at a ledger row or a deferral that was renamed away;
//! * a ledger row `50-NOT-COPIED.md` §8.2 counts is pointed at by no inventory
//!   row — the same defect from the other end, an argument written down for a
//!   capability that has dropped out of the count;
//! * the rows and the file's own summary line disagree, so the number quoted in
//!   `50-NOT-COPIED.md` §8 stops being derivable from anything;
//! * any cell of `50-NOT-COPIED.md` §8.2 — thirteen rows of four numbers, one
//!   per area — disagrees with the rows that produce it. The four header totals
//!   are the four numbers that survive this drift: move a row between areas and
//!   they still add up.
//!
//! It reads the same way `deliberate_refusals.rs` does — parse the Markdown
//! table, walk the cells — because both documents are read by people first and
//! the table has to stay a table.

use std::path::{Path, PathBuf};

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn inventory() -> String {
    let p = repo().join("research/notes/eve-capabilities.md");
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

fn refusals() -> String {
    let p = repo().join("docs/50-NOT-COPIED.md");
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

/// One inventory row, already split into the cells the file documents:
/// number, capability, where it was read from, the letter, where it lands —
/// plus the area it sits in, which the file carries as the `## <n>. <Area>`
/// heading above it rather than as a sixth column.
struct Row {
    number: u32,
    capability: String,
    read_from: String,
    letter: String,
    lands: String,
    /// The numbered section this row is under: `Authoring`, `Model`, `Tools`…
    ///
    /// `50-NOT-COPIED.md` §8.2 states a whole grid per area — rows, (a), (b),
    /// (c) — and nothing recomputed it, so a row that changed area or letter
    /// left that table wrong while the four header totals still added up. The
    /// area is what makes the grid derivable, and it did **not** need a new
    /// column: the file already puts every row under exactly one numbered
    /// heading, so the heading is the column.
    area: String,
}

/// Every numbered row of the inventory, in file order.
///
/// A row is a table line whose first cell is a bare number — which is exactly
/// what the file's own format promises and what the header table (`| | Means |
/// Where the row points |`) is not, so the legend never parses as data.
fn rows() -> Vec<Row> {
    let text = inventory();
    let mut area: Option<String> = None;
    let mut out = Vec::new();
    for line in text.lines() {
        // `## 3. Tools` opens an area; `## How to read the letter` closes the
        // one before it, so a numbered row that drifted out of every area
        // section is reported rather than inherited from whatever came last.
        if let Some(rest) = line.strip_prefix("## ") {
            area = numbered_heading(rest);
            continue;
        }
        let Some(cells) = table_cells(line) else { continue };
        if cells.len() != 5 {
            continue;
        }
        let Ok(number) = cells[0].parse::<u32>() else { continue };
        let area = area.clone().unwrap_or_else(|| {
            panic!(
                "row {} ({}) is not under any `## <n>. <Area>` heading. Every row belongs to one \
                 area, because `docs/50-NOT-COPIED.md` §8.2 states a count per area and this file \
                 is what that count is derived from.",
                number, cells[1]
            )
        });
        out.push(Row {
            number,
            capability: cells[1].clone(),
            read_from: cells[2].clone(),
            letter: cells[3].clone(),
            lands: cells[4].clone(),
            area,
        });
    }
    out
}

/// `3. Tools` → `Tools`; `How to read the letter` → `None`.
fn numbered_heading(rest: &str) -> Option<String> {
    let (n, name) = rest.split_once(". ")?;
    if n.is_empty() || !n.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    Some(name.trim().to_string())
}

/// A Markdown table line, split into its cells, or `None` if the line is not one.
fn table_cells(line: &str) -> Option<Vec<String>> {
    Some(
        line.trim()
            .strip_prefix('|')?
            .strip_suffix('|')?
            .split('|')
            .map(|c| c.trim().to_string())
            .collect(),
    )
}

/// The first backticked span of a cell — the Eve path, by the file's convention
/// of writing `` `path` : `symbol` ``.
fn first_code_span(cell: &str) -> Option<&str> {
    let rest = cell.split_once('`')?.1;
    rest.split_once('`').map(|(inner, _)| inner)
}

/// `**Count:** 98 rows — 51 (a), 22 (b), 25 (c).` read back as four numbers.
fn header_totals() -> (usize, usize, usize, usize) {
    let text = inventory();
    let line = text
        .lines()
        .find(|l| l.starts_with("**Count:**"))
        .expect("the file must open with a **Count:** line stating its own totals");
    let numbers: Vec<usize> = line
        .split(|c: char| !c.is_ascii_digit())
        .filter(|s| !s.is_empty())
        .map(|s| s.parse().expect("a count is a number"))
        .collect();
    assert_eq!(
        numbers.len(),
        4,
        "the **Count:** line must state four numbers — total, (a), (b), (c) — and states {}: {line:?}",
        numbers.len()
    );
    (numbers[0], numbers[1], numbers[2], numbers[3])
}

#[test]
fn every_capability_in_the_inventory_carries_exactly_one_of_the_three_letters() {
    // This is the clause itself. A row with two letters is a capability nobody
    // decided about, written down as if somebody had; a row with none is the
    // fourth category with the name left off. Both are the same defect and the
    // message has to name the row, because in ninety-eight rows "somewhere" is
    // not a finding.
    let rows = rows();
    assert!(!rows.is_empty(), "no numbered rows parsed — the inventory table has changed shape");

    for row in &rows {
        assert!(
            matches!(row.letter.as_str(), "a" | "b" | "c"),
            "row {} ({}) is lettered {:?} — a capability is expressible (a), declared and delegated (b), \
             or refused (c), and exactly one of them. Anything else is the fourth category.",
            row.number,
            row.capability,
            row.letter
        );
    }
}

#[test]
fn the_rows_are_numbered_from_one_with_no_gaps() {
    // An inventory people cite by number ("row 45") stops working the moment a
    // deletion leaves a hole or a merge duplicates an index, and it fails
    // silently — the prose keeps reading fine.
    for (i, row) in rows().iter().enumerate() {
        let expected = i as u32 + 1;
        assert_eq!(
            row.number, expected,
            "row {} of the file is numbered {} — numbering must run 1..n so a reference to a row \
             still means the row it meant",
            expected, row.number
        );
    }
}

#[test]
fn every_row_names_the_eve_file_and_the_symbol_it_was_read_from() {
    // A row with no source is not a row. The previous inventory could not be
    // checked against anything, which is exactly how 22 capabilities ended up
    // counted in one document and openable in none. This runs everywhere,
    // including on a machine that has never cloned the corpus, because the
    // citation's shape is a property of the file rather than of the disk.
    for row in rows() {
        let read_from = &row.read_from;
        let path = first_code_span(read_from).unwrap_or_else(|| {
            panic!(
                "row {} ({}) cites no source. Write it as `path` : `symbol` — a row with no source \
                 is an assertion, which is the thing this file exists to replace.",
                row.number, row.capability
            )
        });
        assert!(
            path.starts_with("packages/") || path.starts_with("apps/") || path.starts_with("docs/") || path.starts_with("skills/"),
            "row {} ({}) reads from {path:?}, which is not a path inside Eve's tree. Paths are \
             written relative to research/repos/frameworks/vercel-eve so they can be opened.",
            row.number,
            row.capability
        );
        assert!(
            read_from.matches('`').count() >= 4,
            "row {} ({}) names a file but no symbol: {read_from:?}. The symbol is what makes the \
             citation checkable — a file alone points at hundreds of lines.",
            row.number,
            row.capability
        );
    }
}

#[test]
fn every_cited_eve_path_is_still_in_the_corpus_that_was_read() {
    // The corpus is 15 GB and deliberately not committed (`.gitignore`), so this
    // is the one check that cannot run everywhere. It runs where the corpus is,
    // and says out loud when it did not, rather than passing quietly — a skip
    // reported as a pass is how a stale citation survives a green suite.
    let corpus = repo().join("research/repos/frameworks/vercel-eve");
    if !corpus.is_dir() {
        println!(
            "SKIPPED: the Eve corpus is not at {}. Row paths were checked for shape but not \
             resolved. Clone the corpus to check them for real.",
            corpus.display()
        );
        return;
    }

    for row in rows() {
        let path = first_code_span(&row.read_from).expect("shape is held by the test above");
        assert!(
            corpus.join(path).exists(),
            "row {} ({}) reads from {path:?}, which is not in the corpus. Either the path moved and \
             the row needs the new one, or the capability is gone and the row should say so.",
            row.number,
            row.capability
        );
    }
}

#[test]
fn every_refused_row_points_at_a_refusal_that_is_actually_written_down() {
    // (c) means "listed in 50-NOT-COPIED.md with a reason". A row that says (c)
    // and points at a ledger row that was renamed away has quietly become the
    // fourth category while still looking accounted for — the failure mode this
    // whole pair of files is built against.
    //
    // This walks one way only, and says so: it asks whether the id a row names
    // EXISTS, which is silent about a ledger row nobody names. The other way is
    // `every_refusal_the_per_area_table_counts_is_one_an_inventory_row_points_at`.
    let ledger = ledger_ids();
    assert!(ledger.len() >= 12, "only {} ledger rows found — §5 has gone stale", ledger.len());

    let has_deferrals = refusals().contains("## 6. Deferred");
    assert!(has_deferrals, "§6 must exist for a (c) row to be able to point at a deferral");

    for row in rows() {
        if row.letter != "c" {
            continue;
        }
        let ledger_refs: Vec<String> = ledger.iter().filter(|id| names_ledger_row(&row.lands, id)).cloned().collect();
        let deferred = row.lands.contains("§6");
        assert!(
            !ledger_refs.is_empty() || deferred,
            "row {} ({}) is refused but points nowhere. A (c) row names the §5 ledger row that argues \
             it, or §6 when it is deferred rather than refused: {:?}",
            row.number,
            row.capability,
            row.lands
        );
        for id in ledger_refs {
            assert!(
                ledger.contains(&id),
                "row {} ({}) points at {id}, which is not a row of the ledger",
                row.number,
                row.capability
            );
        }
    }
}

/// Every `<group>.<field>` written in backticks inside a cell.
///
/// The inventory's own legend says an (a) row points at "the schema group and
/// field, in `spec/schema.yaml`", and that is the convention this reads. A
/// backticked span with no dot is a bare field name or a command and is left to
/// the checks that own those.
fn cited_fields(cell: &str) -> Vec<(String, String)> {
    let mut out = Vec::new();
    for span in code_spans(cell) {
        let Some((group, field)) = span.split_once('.') else { continue };
        let field = field.trim().trim_end_matches(':');
        if group.contains(' ') || field.contains(' ') || field.is_empty() {
            continue;
        }
        if group.starts_with("pact") || group.contains('/') {
            continue;
        }
        out.push((group.trim().to_string(), field.to_string()));
    }
    out
}

/// Every backticked span of a cell, in order.
fn code_spans(cell: &str) -> Vec<&str> {
    cell.split('`').skip(1).step_by(2).collect()
}

/// The specification, as `group -> fields`, read the way a person reads it.
///
/// Deliberately a line scan rather than a YAML parse: this test's job is to say
/// which *group* is missing which *field*, and the schema's own shape — two
/// levels of two-space indentation under `groups:` and `fields:` — makes that a
/// four-line function. Pulling in a parser to answer it would make the failure
/// message harder to write, not easier.
fn schema_groups() -> Vec<(String, Vec<String>)> {
    let text = std::fs::read_to_string(repo().join("spec/schema.yaml")).expect("spec/schema.yaml");
    let mut groups: Vec<(String, Vec<String>)> = Vec::new();
    let mut in_fields = false;
    for line in text.lines() {
        let trimmed = line.trim_end();
        if trimmed.starts_with("  ") && !trimmed.starts_with("   ") && trimmed.ends_with(':') {
            groups.push((trimmed.trim().trim_end_matches(':').to_string(), Vec::new()));
            in_fields = false;
        } else if trimmed.trim() == "fields:" {
            in_fields = true;
        } else if in_fields
            && trimmed.starts_with("      ")
            && !trimmed.starts_with("       ")
            && trimmed.ends_with(':')
            && let Some((_, fields)) = groups.last_mut()
        {
            fields.push(trimmed.trim().trim_end_matches(':').to_string());
        }
    }
    groups
}

/// The verbs `crates/pact-cli/src/main.rs` actually dispatches.
fn cli_verbs() -> Vec<String> {
    let text =
        std::fs::read_to_string(repo().join("crates/pact-cli/src/main.rs")).expect("main.rs");
    let Some(body) = text.split_once("    match cmd {").map(|(_, rest)| rest) else {
        panic!("main.rs no longer dispatches with `match cmd {{`; this test reads that")
    };
    let body = body.split("\n}").next().unwrap_or(body);
    let mut verbs = Vec::new();
    for line in body.lines() {
        let line = line.trim();
        if !line.contains("=>") {
            continue;
        }
        for span in line.split('"').skip(1).step_by(2) {
            if !span.starts_with('-') && !span.is_empty() {
                verbs.push(span.to_string());
            }
        }
    }
    verbs
}

#[test]
fn every_expressible_row_names_a_field_the_schema_actually_has() {
    // (a) carries fifty of the ninety-eight rows and was the one letter held by
    // nothing. `every_refused_row_points_at_a_refusal_that_is_actually_written
    // _down` resolves (c) against the ledger; (a) resolved against a reader's
    // goodwill, and two rows pointed at `interceptor.on` — a field the schema
    // does not have, because the schema landed with `when` and the inventory
    // kept the word the plan proposed. An (a) row pointing at a phantom field is
    // the fourth category wearing a letter.
    let groups = schema_groups();
    let verbs = cli_verbs();
    for row in rows() {
        if row.letter != "a" {
            continue;
        }
        // The row has to cite SOMETHING this test can resolve. For thirteen of
        // the fifty (a) rows `cited_fields` returned nothing at all — a cell
        // reading "the `settings` group" or "the files are the API for every
        // surface (D18)" — so the loop below had no body to run and the row was
        // held by nobody. Measured: a fabricated row citing `nothing` passed.
        // The sibling (b) check already had this guard; (a) did not.
        let cited = cited_fields(&row.lands);
        let names_a_command = code_spans(&row.lands)
            .iter()
            .any(|s| s.strip_prefix("pact ").is_some_and(|v| verbs.contains(&v.to_string())));
        assert!(
            !cited.is_empty() || names_a_command,
            "row {} ({}) is expressible and points at no field and no command: {:?}. \
             An (a) row means an author can write it, so say WHERE — `group.field`, or a \
             `pact <verb>` that ships.",
            row.number,
            row.capability,
            row.lands
        );
        for (group, field) in cited {
            let Some((_, fields)) = groups.iter().find(|(g, _)| *g == group) else {
                panic!(
                    "row {} ({}) points at `{group}.{field}`, and `spec/schema.yaml` has no \
                     `{group}` group at all. An (a) row means an author can write it, so the \
                     field has to exist.",
                    row.number, row.capability
                )
            };
            assert!(
                fields.contains(&field),
                "row {} ({}) points at `{group}.{field}`, and a `{group}` has: {}. \
                 Point the row at the field that shipped, or add the field.",
                row.number,
                row.capability,
                fields.join(", ")
            );
        }
    }
}

#[test]
fn every_expressible_row_that_names_a_command_names_one_that_exists() {
    // The legend's own carve-out: a tooling row is (a) when PACT ships the
    // capability as a command rather than a field. That made `pact init` and
    // `pact tools list` into accounted-for capabilities on the strength of two
    // help strings, and neither verb has ever been written. A promised verb is
    // an absent capability with a letter on it, which is exactly the fourth
    // category this file exists to catch.
    let verbs = cli_verbs();
    assert!(
        verbs.iter().any(|v| v == "check"),
        "no verbs parsed out of main.rs — the dispatch has changed shape and this test is blind"
    );
    for row in rows() {
        for span in code_spans(&row.lands) {
            let Some(verb) = span.strip_prefix("pact ") else { continue };
            let verb = verb.split_whitespace().next().unwrap_or("");
            assert!(
                verbs.iter().any(|v| v == verb),
                "row {} ({}) says `pact {verb}`, and the binary dispatches only: {}. \
                 Either the verb ships, or the row points at what does.",
                row.number,
                row.capability,
                verbs.join(", ")
            );
        }
    }
}

#[test]
fn every_delegated_row_names_a_row_of_section_four() {
    // (b) means "the spec declares it and the host does it", and the legend says
    // the row points at "the row of `50-NOT-COPIED.md` §4 that says so". Nothing
    // checked that the row was there. Row 46 pointed at a §4 row about remote
    // agents that has never existed, on the strength of `port.answers:` — which
    // names a LOCAL agent handling what arrived, since a port is entirely
    // inbound. A (b) row whose §4 row is missing is a capability delegated to
    // nobody.
    let body = section_four();
    assert!(
        body.contains("the host supplies"),
        "§4's table has moved; this test reads the section between `## 4.` and the next heading"
    );
    for row in rows() {
        if row.letter != "b" {
            continue;
        }
        let phrase = plainly(row.lands.trim_start_matches('§').trim_start_matches('4'));
        assert!(
            !phrase.is_empty(),
            "row {} ({}) is delegated and says only {:?}. Name the §4 row that says the host \
             does it.",
            row.number,
            row.capability,
            row.lands
        );
        assert!(
            body.contains(&phrase),
            "row {} ({}) points at §4 with {:?}, and no row of §4 says that. Either quote the \
             row that is there, or add the row.",
            row.number,
            row.capability,
            row.lands
        );
    }
}

/// §4's rows, flattened and plainly spelled, for the check above.
fn section_four() -> String {
    let text = refusals();
    let mut out = String::new();
    let mut inside = false;
    for line in text.lines() {
        if line.starts_with("## 4.") {
            inside = true;
            continue;
        }
        if inside && line.starts_with("## ") {
            break;
        }
        if inside {
            out.push_str(&plainly(line));
            out.push(' ');
        }
    }
    out
}

/// Lowercase, letters and digits only, single-spaced.
///
/// So that a cell writing "durable sessions turns and steps" matches a §4 row
/// writing "Durable sessions, turns and steps", and `` `remembers:` `` matches
/// `remembers:`. The alternative is exact quoting, which would make the check
/// about punctuation rather than about whether the row is there.
fn plainly(s: &str) -> String {
    let mut out = String::new();
    let mut space = true;
    for c in s.chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c.to_ascii_lowercase());
            space = false;
        } else if !space {
            out.push(' ');
            space = true;
        }
    }
    out.trim().to_string()
}

/// The ids of §5's ledger rows, read only from §5 — the same window
/// `deliberate_refusals.rs::ledger` uses, so a table elsewhere in the document
/// whose first cell happens to start with `R` is not mistaken for a refusal.
fn ledger_ids() -> Vec<String> {
    let text = refusals();
    let mut ids = Vec::new();
    let mut inside = false;
    for line in text.lines() {
        if line.starts_with("## 5.") {
            inside = true;
            continue;
        }
        if inside && line.starts_with("## ") {
            break;
        }
        if inside
            && let Some(rest) = line.strip_prefix("| R")
            && let Some(id) = rest.split('|').next()
        {
            ids.push(format!("R{}", id.trim()));
        }
    }
    ids
}

/// Every `R<n>` a cell names, longest digit run taken whole so `R16` never
/// yields `R1`, in the order they are written and without repeats.
fn ledger_ids_named(cell: &str) -> Vec<String> {
    let chars: Vec<char> = cell.chars().collect();
    let mut out: Vec<String> = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == 'R' {
            let mut j = i + 1;
            while j < chars.len() && chars[j].is_ascii_digit() {
                j += 1;
            }
            if j > i + 1 {
                let id: String = chars[i..j].iter().collect();
                if !out.contains(&id) {
                    out.push(id);
                }
                i = j;
                continue;
            }
        }
        i += 1;
    }
    out
}

/// Where a (c) row sends the reader: the ledger rows it names, plus `§6` when
/// it is deferred rather than refused. §8.2's own (c) column is written in the
/// same two notations, which is what makes the two sides comparable.
fn refusals_named(cell: &str) -> Vec<String> {
    let mut out = ledger_ids_named(cell);
    if cell.contains("§6") {
        out.push("§6".to_string());
    }
    out.sort();
    out
}

/// One row of `50-NOT-COPIED.md` §8.2 — the per-area grid — with the line it is
/// on, because a diagnostic about a table of thirteen rows has to say which.
struct AreaRow {
    area: String,
    line: usize,
    rows: usize,
    a: usize,
    b: usize,
    /// The whole (c) cell: a count, then the refusals it falls to.
    c_cell: String,
}

/// §8.2's table, as rows. The `**Total**` row is one of them — it is a cell of
/// the table and drifts like any other.
fn per_area_table() -> Vec<AreaRow> {
    let text = refusals();
    let mut out = Vec::new();
    let mut inside = false;
    for (n, line) in text.lines().enumerate() {
        if line.starts_with("### 8.2") {
            inside = true;
            continue;
        }
        if inside && (line.starts_with("## ") || line.starts_with("### ")) {
            break;
        }
        if !inside {
            continue;
        }
        let Some(cells) = table_cells(line) else { continue };
        if cells.len() != 5 {
            continue;
        }
        let area = unbold(&cells[0]);
        // The header (`Area | rows | …`) and the rule (`--- | --- | …`) are the
        // two lines of a Markdown table that are not data.
        if area == "Area" || area.starts_with("---") {
            continue;
        }
        let Some(rows) = leading_count(&cells[1]) else { continue };
        let (Some(a), Some(b)) = (leading_count(&cells[2]), leading_count(&cells[3])) else {
            continue;
        };
        out.push(AreaRow { area, line: n + 1, rows, a, b, c_cell: cells[4].clone() });
    }
    assert!(
        out.len() >= 5,
        "only {} rows parsed out of §8.2 — the per-area table has changed shape and this test is \
         blind, which is worse than the drift it was written for",
        out.len()
    );
    out
}

/// `**28**` → `28`; `3 — five separate kinds of pause (R12)` → `3`.
fn leading_count(cell: &str) -> Option<usize> {
    let cell = unbold(cell);
    let digits: String = cell.chars().take_while(char::is_ascii_digit).collect();
    digits.parse().ok()
}

fn unbold(cell: &str) -> String {
    cell.trim().trim_matches('*').trim().to_string()
}

/// Two area names are the same area when they read the same to a person.
///
/// §8.2 writes `Developer experience, catalogue, templates` and the inventory
/// heads the same section `Developer experience, catalogue and templates`. That
/// is one area written by two hands, not two areas, and holding the table to
/// punctuation would make this test about commas instead of about counts — the
/// same argument `plainly` already makes for §4.
fn same_area(a: &str, b: &str) -> bool {
    let strip = |s: &str| {
        plainly(s)
            .split(' ')
            .filter(|w| *w != "and")
            .collect::<Vec<_>>()
            .join(" ")
    };
    strip(a) == strip(b)
}

/// Whether a cell names a specific ledger row, without `R1` matching `R16`.
fn names_ledger_row(cell: &str, id: &str) -> bool {
    let mut rest = cell;
    while let Some(at) = rest.find(id) {
        let after = &rest[at + id.len()..];
        if !after.chars().next().is_some_and(|c| c.is_ascii_digit()) {
            return true;
        }
        rest = &rest[at + id.len()..];
    }
    false
}

#[test]
fn the_file_cannot_drift_from_the_summary_it_states_about_itself() {
    // §8 of 50-NOT-COPIED.md quotes this file's numbers, and a reader who checks
    // one document against the other has to land somewhere true. The header is
    // the only part anybody reads, so the header is what gets stale — a row
    // added without touching it makes both documents wrong at once.
    let (total, a, b, c) = header_totals();
    let rows = rows();

    assert_eq!(
        rows.len(),
        total,
        "the **Count:** line says {total} rows and the file has {}. Update the line, or the number \
         quoted in 50-NOT-COPIED.md §8 stops being derivable from anything.",
        rows.len()
    );

    for (letter, stated) in [("a", a), ("b", b), ("c", c)] {
        let found = rows.iter().filter(|r| r.letter == letter).count();
        assert_eq!(
            found, stated,
            "the **Count:** line says {stated} rows lettered ({letter}) and there are {found}. \
             The per-letter totals are what make 'no fourth category' a sum rather than a claim."
        );
    }
    assert_eq!(a + b + c, total, "the three letters must add up to the total: {a} + {b} + {c} != {total}");
}

#[test]
fn every_cell_of_the_per_area_table_is_recomputed_from_the_inventorys_own_rows() {
    // The four header totals were the only numbers anybody recomputed, and they
    // are the four that survive the drift this test is for: move a row from
    // Tools to Runtime, or change one row's letter and fix the header, and every
    // total still adds up while `50-NOT-COPIED.md` §8.2 — thirteen rows of four
    // numbers each — is quietly wrong. §8.2 is the table a reader uses to find
    // WHERE the refusals fall, so a wrong cell there sends them to the wrong
    // area of a ninety-eight row inventory.
    let stated = per_area_table();
    let rows = rows();

    // The areas themselves, both ways. An area section added to the inventory
    // and not to §8.2 is a whole block of capabilities the count never sees.
    for area in &stated {
        if same_area(&area.area, "Total") {
            continue;
        }
        assert!(
            rows.iter().any(|r| same_area(&r.area, &area.area)),
            "docs/50-NOT-COPIED.md line {}: §8.2 has a row for the area {:?} and \
             research/notes/eve-capabilities.md has no `## <n>. {}` section. Either the section \
             was renamed — write the new name in this row — or the row goes.",
            area.line,
            area.area,
            area.area
        );
    }
    for row in &rows {
        assert!(
            stated.iter().any(|s| same_area(&s.area, &row.area)),
            "research/notes/eve-capabilities.md row {} is under `## …. {}`, and docs/50-NOT-COPIED.md \
             §8.2 has no row for that area. Add one:  | {} | … | … | … | … |",
            row.number,
            row.area,
            row.area
        );
    }

    // Then every cell of every row, against the rows that produce it.
    for area in &stated {
        let mine: Vec<&Row> = if same_area(&area.area, "Total") {
            rows.iter().collect()
        } else {
            rows.iter().filter(|r| same_area(&r.area, &area.area)).collect()
        };
        let count = |letter: &str| mine.iter().filter(|r| r.letter == letter).count();
        let (n, a, b, c) = (mine.len(), count("a"), count("b"), count("c"));

        for (column, said, real) in
            [("rows", area.rows, n), ("(a)", area.a, a), ("(b)", area.b, b)]
        {
            assert_eq!(
                said, real,
                "docs/50-NOT-COPIED.md line {}: §8.2's `{}` row says {said} in the `{column}` \
                 column and research/notes/eve-capabilities.md has {real}. \
                 The whole row, recomputed, is:  | {} | {n} | {a} | {b} | {c} — … |",
                area.line, area.area, area.area
            );
        }
        let said_c = leading_count(&area.c_cell).unwrap_or_else(|| {
            panic!(
                "docs/50-NOT-COPIED.md line {}: §8.2's `{}` row starts its (c) cell with {:?}, and \
                 the cell must open with the count so the row can be read as four numbers. \
                 Write:  | {} | {n} | {a} | {b} | {c} — … |",
                area.line, area.area, area.c_cell, area.area
            )
        });
        assert_eq!(
            said_c, c,
            "docs/50-NOT-COPIED.md line {}: §8.2's `{}` row says {said_c} in the `(c)` column and \
             research/notes/eve-capabilities.md has {c}. \
             The whole row, recomputed, is:  | {} | {n} | {a} | {b} | {c} — … |",
            area.line, area.area, area.area
        );
    }
}

#[test]
fn every_refusal_the_per_area_table_counts_is_one_an_inventory_row_points_at() {
    // The reverse of `every_refused_row_points_at_a_refusal_that_is_actually
    // _written_down`, which only ever walked one way: it checks that a (c) row's
    // ledger id EXISTS, so an id nobody points at is invisible to it. A refusal
    // nothing points at is a refusal for a capability nobody counted — the
    // fourth category arriving from the other end, as an argument written down
    // for a power that has dropped out of the inventory.
    //
    // The set of ledger rows that argue an EVE capability is not guessed at:
    // §8.2's (c) column is where this pair of documents states it, one area at a
    // time. §5 also holds refusals PACT took on its own account — R40's schema
    // discovery, R59's second learning switch — which no inventory row can point
    // at because they are not Eve's, and §8.2's own surplus paragraph says so.
    // Scoping to §8.2's cells is therefore the derivation rather than a list
    // that would go stale the next time §5 grows.
    let ledger = ledger_ids();
    let rows = rows();
    for area in per_area_table() {
        if same_area(&area.area, "Total") {
            continue;
        }
        let stated = refusals_named(&area.c_cell);
        let mut found: Vec<String> = Vec::new();
        for row in rows.iter().filter(|r| r.letter == "c" && same_area(&r.area, &area.area)) {
            for id in refusals_named(&row.lands) {
                if !found.contains(&id) {
                    found.push(id);
                }
            }
        }
        found.sort();

        for id in &stated {
            if id != "§6" {
                assert!(
                    ledger.contains(id),
                    "docs/50-NOT-COPIED.md line {}: §8.2's `{}` row counts {id} among its refusals \
                     and §5 has no such row. Point the cell at the ledger row that argues it.",
                    area.line,
                    area.area
                );
            }
            assert!(
                found.contains(id),
                "docs/50-NOT-COPIED.md line {}: §8.2's `{}` row counts {id} among its refusals and \
                 no {} row of research/notes/eve-capabilities.md points at it. A refusal nothing \
                 points at is a refusal for a capability nobody counted. \
                 That area's (c) rows point at: {}. Either a row's letter or its landing changed — \
                 fix the cell — or {id} argues something Eve does not ship, in which case it belongs \
                 in §8.2's surplus paragraph and not in this cell.",
                area.line,
                area.area,
                area.area,
                if found.is_empty() { "nothing".to_string() } else { found.join(", ") }
            );
        }
        for id in &found {
            assert!(
                stated.contains(id),
                "research/notes/eve-capabilities.md has a {} row lettered (c) that points at {id}, \
                 and docs/50-NOT-COPIED.md line {}, §8.2's `{}` row, does not name it: {:?}. \
                 §8.2 is where a reader looks up which refusal an area falls to, so add {id} to \
                 that cell.",
                area.area,
                area.line,
                area.area,
                area.c_cell
            );
        }
    }
}

#[test]
fn the_totals_section_eight_quotes_in_prose_are_the_inventorys_own_totals() {
    // §8 states the same four numbers three times — once in a sentence people
    // quote, once in a table, once per area in §8.2 — and each of the three is
    // read by a different reader. Two of them were derived from nothing.
    let rows = rows();
    let (total, a, b, c) = (
        rows.len(),
        rows.iter().filter(|r| r.letter == "a").count(),
        rows.iter().filter(|r| r.letter == "b").count(),
        rows.iter().filter(|r| r.letter == "c").count(),
    );
    let doc = refusals();

    // The sentence, which runs over two lines of the blockquote.
    let claim: String = doc
        .lines()
        .skip_while(|l| !l.contains("capabilities are enumerated"))
        .take(2)
        .collect::<Vec<_>>()
        .join(" ");
    assert!(
        !claim.is_empty(),
        "docs/50-NOT-COPIED.md §8 must state its count in a sentence — the line reading \
         `<n> capabilities are enumerated and <n> are accounted for` — because that is the \
         sentence people quote"
    );
    let quoted: Vec<usize> = claim
        .split(|ch: char| !ch.is_ascii_digit())
        .filter(|s| !s.is_empty())
        .map(|s| s.parse().expect("a count is a number"))
        .collect();
    assert_eq!(
        quoted,
        vec![total, total, a, b, c],
        "docs/50-NOT-COPIED.md §8 says {quoted:?} and research/notes/eve-capabilities.md has \
         {total} rows — {a} (a), {b} (b), {c} (c). Write: \
         `**{total} capabilities are enumerated and {total} are accounted for — {a} expressible, \
         {b} declared and delegated, {c} refused or deferred, none outside.**`"
    );

    // And the table under it, which states them a second time. Read only from
    // §8 proper — §8.2's grid is four columns wide in places too, and it is held
    // by the test above, to a stricter rule.
    let mut inside = false;
    let mut checked = 0;
    for (n, line) in doc.lines().enumerate() {
        if line.starts_with("## 8.") {
            inside = true;
            continue;
        }
        if inside && (line.starts_with("### ") || line.starts_with("## ")) {
            break;
        }
        if !inside {
            continue;
        }
        let Some(cells) = table_cells(line) else { continue };
        if cells.len() != 4 {
            continue;
        }
        let (label, said) = (unbold(&cells[0]), unbold(&cells[1]));
        let want = match (label.as_str(), said.as_str()) {
            ("(a)", _) => a,
            ("(b)", _) => b,
            ("(c)", _) => c,
            ("", "Total") => total,
            _ => continue,
        };
        let Some(got) = leading_count(&cells[2]) else { continue };
        checked += 1;
        assert_eq!(
            got, want,
            "docs/50-NOT-COPIED.md line {}: the §8 table says {got} for {}, and \
             research/notes/eve-capabilities.md has {want}. The four numbers are {total} rows — \
             {a} (a), {b} (b), {c} (c).",
            n + 1,
            if label.is_empty() { said.as_str() } else { label.as_str() }
        );
    }
    assert_eq!(
        checked, 4,
        "§8's table states one row per letter and a total, and {checked} were found. The table has \
         changed shape and this test is blind, which is how the number got quoted in two documents \
         and derivable from neither."
    );
}

#[test]
fn the_inventory_and_the_refusal_ledger_name_each_other() {
    // Two documents that only point one way decay in the direction nobody
    // reads. §8 has to send a reader to the inventory, and the inventory has to
    // say which test holds it, or the next person to change one of them has no
    // way of knowing the other exists.
    let inv = inventory();
    let doc = refusals();

    assert!(
        inv.contains("crates/pact-cli/tests/eve_inventory.rs"),
        "the inventory must name the test that holds it"
    );
    assert!(
        inv.contains("docs/50-NOT-COPIED.md"),
        "the inventory must name the document its (c) rows point into"
    );
    assert!(
        doc.contains("research/notes/eve-capabilities.md"),
        "50-NOT-COPIED.md must send a reader to the inventory the count is derived from"
    );
    assert!(
        doc.contains("crates/pact-cli/tests/eve_inventory.rs"),
        "50-NOT-COPIED.md must name the test that keeps the count honest, the way §7 names one for \
         each of the three categories"
    );
}
