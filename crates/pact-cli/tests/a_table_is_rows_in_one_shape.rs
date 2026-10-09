//! A value table is a list of rows, each in the one named shape `rows-are:`
//! gives (02W §2.12), held where it is written; and what a run reads by name —
//! `workspace.calendar:`, a port's `per-row-of:`, a `values.<name>` binding —
//! stays in the document for the run to read, while every other figure is put
//! in place and removed as before. Over #16's tree
//! (`tests/trees/workflows-16-trial-booking/`) with a calendar of holidays.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
}

const TREE: &str = "tests/trees/workflows-16-trial-booking";
const HOLIDAYS: &str = "values/holidays.yaml";
const TABLE: &str = "description: The days the centre is closed.
shape: table
rows-are: holiday
value:
  - { day: 2026-12-25, name: Christmas Day }
  - { day: 2027-01-01, name: New Year's Day }
";

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

/// `verb` on #16 with a calendar named, the table written as `table`, and each
/// `(file, from, to)` edit made.
fn run(name: &str, verb: &str, table: &str, edits: &[(&str, &str, &str)]) -> (bool, String) {
    static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let n = N.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dst = std::env::temp_dir().join(format!("pact-table-{name}-{n}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&repo().join(TREE), &dst);
    std::fs::write(dst.join(HOLIDAYS), table).unwrap();
    let calendar = [
        (
            "workspace.yaml",
            "time-zone: America/Chicago\n",
            "time-zone: America/Chicago\ncalendar: holidays\n",
        ),
        (
            "workspace.yaml",
            "shapes:\n",
            "shapes:\n  holiday:\n    day: date\n    name: text\n",
        ),
    ];
    for (file, from, to) in calendar.iter().chain(edits) {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    let out = pact()
        .args([verb, dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    let mut said = String::from_utf8_lossy(&out.stdout).into_owned();
    said.push_str(&String::from_utf8_lossy(&out.stderr));
    (out.status.success(), said)
}

/// Every message and fix reads as one sentence: no run of spaces inside it,
/// which a lost `\` line continuation in a literal leaves behind.
fn reads_as_english(text: &str) {
    for line in text.lines().map(str::trim_start) {
        if ["error:", "warning:", "note:", "fix:"]
            .iter()
            .any(|p| line.starts_with(p))
        {
            assert!(!line.contains("  "), "two spaces in a row: {line}");
        }
    }
}

#[test]
fn a_calendar_of_holidays_loads_and_stays_for_a_run_to_read() {
    let (ok, text) = run("clean", "check", TABLE, &[]);
    assert!(ok, "{text}");
    let (ok, shown) = run("show", "show", TABLE, &[]);
    assert!(ok, "{shown}");
    let json = &shown[shown.find('{').unwrap()..=shown.rfind('}').unwrap()];
    let doc: serde_json::Value = serde_json::from_str(json).expect("pact show prints JSON");
    assert_eq!(doc["calendar"], "holidays");
    assert_eq!(
        doc["values"]["holidays"]["value"][0]["name"],
        "Christmas Day"
    );
    // A figure a binding reads stays too, as resolved; nothing else is kept.
    assert_eq!(doc["values"]["trial-pipeline"]["value"], "Free trial");
    assert_eq!(doc["values"].as_object().unwrap().len(), 4, "{json}");
}

#[test]
fn every_row_is_held_to_its_shape() {
    for (name, row, says) in [
        (
            "date",
            "{ day: 2026-13-45x, name: Christmas Day }",
            "`day:` is not a date",
        ),
        (
            "part",
            "{ day: 2026-12-25, name: Christmas Day, open: no }",
            "'holiday' has no part called that",
        ),
        ("missing", "{ name: Christmas Day }", "has no `day:`"),
    ] {
        let table = TABLE.replacen("{ day: 2026-12-25, name: Christmas Day }", row, 1);
        let (ok, text) = run(name, "check", &table, &[]);
        assert!(!ok, "[{name}] {text}");
        assert!(
            text.contains("loader/a-table-that-is-not-one"),
            "[{name}] {text}"
        );
        assert!(text.contains(says), "[{name}] {text}");
        reads_as_english(&text);
    }
}

#[test]
fn a_table_says_what_its_rows_are_and_only_a_table_does() {
    let (ok, text) = run(
        "no-rows-are",
        "check",
        &TABLE.replace("rows-are: holiday\n", ""),
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("is a table and does not say what its rows are"),
        "{text}"
    );
    reads_as_english(&text);
    let (ok, text) = run(
        "rows-on-a-figure",
        "check",
        TABLE,
        &[(
            "values/lead-stage.yaml",
            "shape: text\n",
            "shape: text\nrows-are: holiday\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("says what its rows are, and it is not a table"),
        "{text}"
    );
}

#[test]
fn a_calendar_names_a_table_of_days() {
    let (ok, text) = run(
        "not-a-table",
        "check",
        TABLE,
        &[(
            "workspace.yaml",
            "calendar: holidays",
            "calendar: lead-stage",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("`calendar: lead-stage` reads a table, and 'lead-stage' is not one"),
        "{text}"
    );
    reads_as_english(&text);
    let undated = TABLE
        .replace("day: 2026-12-25", "when: 2026-12-25")
        .replace("day: 2027-01-01", "when: 2027-01-01");
    let (ok, text) = run(
        "undated",
        "check",
        &undated,
        &[("workspace.yaml", "    day: date\n", "    when: text\n")],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("have no part that is a date"), "{text}");
    reads_as_english(&text);
}

#[test]
fn a_binding_to_a_value_names_one_the_workspace_has() {
    let (ok, text) = run(
        "typo",
        "check",
        TABLE,
        &[(
            "workflows/trial-booking.yaml",
            "values.trial-pipeline",
            "values.trial-pipline",
        )],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/a-binding-to-nothing"), "{text}");
    assert!(
        text.contains("`values.trial-pipeline`"),
        "the nearest is offered:\n{text}"
    );
}

#[test]
fn one_run_per_row_is_a_timers_line() {
    let (ok, text) = run(
        "per-row",
        "check",
        TABLE,
        &[(
            "ports/trial-booked.yaml",
            "kind: event\n",
            "kind: event\nper-row-of: holidays\n",
        )],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("loader/a-timer-that-cannot-fire"), "{text}");
}
