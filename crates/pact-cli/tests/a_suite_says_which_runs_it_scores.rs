//! A suite says which runs it is a score of (02W §2.13, §3 WF-34's program
//! half).
//!
//! `population: past-runs` replays real runs from `from-the-last:`, and
//! `sampled-frame` puts a `sample:` share of finished live runs in front of
//! `reviewed-by:`; `sliced-by:` breaks the scores down by what a run is given,
//! and `runs-every:` re-runs the checks on a port's clock. A rule may be graded
//! by a carried `pure` program or one of four ready-made checks. Each line that
//! could load and do nothing is refused before anything runs. Over #79's tree
//! (`tests/trees/workflows-79-supervisor/`), held to a suite of its own.

use std::path::{Path, PathBuf};
use std::process::Command;

fn tree() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/trees/workflows-79-supervisor"
    ))
}

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

const FLOW: &str = "workflows/first-read.yaml";
const ACCEPTS: &str = "accepts: { application-id: text, applied-for-aid: yes or no }\n";
const HELD: &str = "accepts: { application-id: text, applied-for-aid: yes or no }\nevals: evals\n";
const SUITE: &str = "evals/suite.yaml";
const SAMPLED: &str = "description: The first read's checks.
population: sampled-frame
sample: 5%
reviewed-by: [admissions-reader]
sliced-by: [applied-for-aid]
runs-every: nights at 2
rules:
  - library: numbers-come-from-the-source
  - program: grade
";
const PROGRAM: &str = "programs/grade/program.yaml";
const GRADER: &str = "description: Passes an answer that says something.
engine: python
determinism: pure
takes:
  answer: text
answers-with:
  verdict: text
fuel:
  runs-for-at-most: 2s
  when-it-runs-out: stop-and-say-so
";

/// `pact check` over the tree held to `suite`, with each `(file, from, to)`
/// edit made after; (whether it passed, what it printed).
fn check(label: &str, suite: &str, edits: &[(&str, &str, &str)]) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!("pact-suites-{label}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&tree(), &dst);
    let write = |file: &str, text: &str| {
        let p = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, text).unwrap();
    };
    write(SUITE, suite);
    write(PROGRAM, GRADER);
    write("programs/grade/body/main.py", "\"ok\"\n");
    let flow = std::fs::read_to_string(dst.join(FLOW)).unwrap();
    assert!(
        flow.contains(ACCEPTS),
        "fixture drifted: {ACCEPTS:?} not in {FLOW}"
    );
    write(FLOW, &flow.replacen(ACCEPTS, HELD, 1));
    for (file, from, to) in edits {
        let text = std::fs::read_to_string(dst.join(file)).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
        write(file, &text.replacen(from, to, 1));
    }
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dst.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

#[test]
fn a_sampled_suite_sliced_by_what_a_run_is_given_loads() {
    let (ok, text) = check("clean", SAMPLED, &[]);
    assert!(ok, "{text}");
    assert!(
        !text.contains("rule: loader/a-line-this-suite-never-reads"),
        "{text}"
    );
    let replayed = SAMPLED
        .replace("population: sampled-frame", "population: past-runs")
        .replace(
            "sample: 5%\nreviewed-by: [admissions-reader]\n",
            "from-the-last: 30 days\n",
        );
    let (ok, text) = check("past-runs", &replayed, &[]);
    assert!(ok, "{text}");
}

#[test]
fn a_sample_with_no_share_or_nobody_to_review_it_is_refused() {
    for (label, line) in [
        ("no-share", "sample: 5%\n"),
        ("no-reviewer", "reviewed-by: [admissions-reader]\n"),
    ] {
        let (ok, text) = check(label, &SAMPLED.replace(line, ""), &[]);
        assert!(!ok, "{text}");
        assert!(text.contains("rule: schema/missing-companion"), "{text}");
        assert!(text.contains("'population' says 'sampled-frame'"), "{text}");
    }
}

#[test]
fn a_line_only_another_population_reads_is_refused() {
    let authored = SAMPLED
        .replace(
            "population: sampled-frame",
            "population: authored-enumeration",
        )
        .replace(
            "runs-every: nights at 2\n",
            "runs-every: nights at 2\nfrom-the-last: 30 days\n",
        );
    let (ok, text) = check("never-read", &authored, &[]);
    assert!(!ok, "{text}");
    for line in ["from-the-last", "sample", "reviewed-by"] {
        assert!(
            text.contains(&format!("`{line}:` is read only when `population:`")),
            "{line}: {text}"
        );
    }
    assert!(
        text.contains("rule: loader/a-line-this-suite-never-reads"),
        "{text}"
    );
    assert!(
        text.contains("fix: Write `population: past-runs`, or take `from-the-last:` out."),
        "{text}"
    );
}

#[test]
fn a_slice_no_run_is_given_is_refused() {
    let (ok, text) = check(
        "slice",
        &SAMPLED.replace("[applied-for-aid]", "[region]"),
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("`sliced-by:` breaks the scores down by `region`, and no workflow held to these checks ('first-read') accepts a `region`"),
        "{text}"
    );
    assert!(
        text.contains("rule: loader/slices-by-what-no-run-is-given"),
        "{text}"
    );
    assert!(
        text.contains("`application-id`, `applied-for-aid`"),
        "{text}"
    );
}

#[test]
fn a_schedule_no_clock_can_keep_is_refused() {
    let (ok, text) = check(
        "every",
        &SAMPLED.replace("nights at 2", "every fortnight"),
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("`runs-every: every fortnight` is not a time PACT can read."),
        "{text}"
    );
    assert!(text.contains("rule: loader/every-is-not-a-time"), "{text}");
}

#[test]
fn a_grader_that_is_not_pure_is_refused_wherever_the_rule_is_written() {
    let (ok, text) = check(
        "impure-suite",
        SAMPLED,
        &[(
            PROGRAM,
            "determinism: pure",
            "determinism: nondeterministic",
        )],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("rule: loader/only-a-pure-program-grades"),
        "{text}"
    );
    // A stage's `checked-by:` is found by the schema's own groups, not a list.
    let (ok, text) = check(
        "impure-stage",
        &SAMPLED.replace("  - program: grade\n", ""),
        &[
            (PROGRAM, "determinism: pure", "determinism: deterministic"),
            (
                FLOW,
                "    then: { answered: save }\n",
                "    checked-by:\n      - program: grade\n    then: { answered: save }\n",
            ),
        ],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("'grade' says it is `deterministic` rather than `pure`"),
        "{text}"
    );
}

#[test]
fn a_grader_or_a_ready_made_check_this_workspace_lacks_is_refused() {
    // WF-34's program half: the program a check names is there.
    let (ok, text) = check(
        "missing",
        &SAMPLED.replace("program: grade", "program: graded"),
        &[],
    );
    assert!(!ok, "{text}");
    assert!(
        text.contains("'program' names 'graded', and there is no such entry in `programs:`."),
        "{text}"
    );
    let (ok, text) = check(
        "library",
        &SAMPLED.replace("numbers-come-from-the-source", "numbers-are-right"),
        &[],
    );
    assert!(!ok, "{text}");
    assert!(text.contains("numbers-come-from-the-source, quotes-are-word-for-word, cites-its-sources, only-goes-up"), "{text}");
}
