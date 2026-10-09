//! The tool that refuses a misspelt field must not accept a misspelt option.
//!
//! PACT's whole argument to a non-technical author is that nothing they type is
//! quietly ignored: a field name one letter wrong is refused by exact name and
//! answered with the nearest real one. Two places did not hold to that, and both
//! were in the very first thing anybody runs.
//!
//! * `pact --help` printed no usage. The positional filter in `run()` dropped
//!   every argument starting with a dash *before* the command was matched, so
//!   `--help` arrived as no arguments at all and became `check .`. From a
//!   repository root that walk descends into other checkouts and does not come
//!   back, so the first command a new author types looked like a hang. `pact -h`
//!   worked, which is why it went unnoticed.
//! * Every option except `--quiet` was discarded in silence.
//!   `pact check --quite <path>` printed the summary it had just been asked to
//!   suppress and never mentioned the typo.
//!
//! These run the real binary, because the thing under test is what a person
//! types at a terminal — not a parser reachable from Rust.

use std::collections::BTreeSet;
use std::process::{Command, Output, Stdio};

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn repo() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

fn out(o: &Output) -> (String, String) {
    (
        String::from_utf8_lossy(&o.stdout).into_owned(),
        String::from_utf8_lossy(&o.stderr).into_owned(),
    )
}

/// A directory `check` would certainly complain about, so "it printed the usage"
/// can be told apart from "it loaded something and happened to be quiet".
fn a_place_with_a_broken_agent_in_it(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("pact-cli-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("agent.yaml"), "nmae: something\n").unwrap();
    dir
}

/// Run, but fail rather than block if the command does not come back.
///
/// A plain `output()` would turn the defect this file exists for — `pact --help`
/// loading the current directory instead of printing — into a hanging test run
/// rather than a failing assertion.
fn within(secs: u64, mut cmd: Command) -> Output {
    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("the binary runs");
    let start = std::time::Instant::now();
    while child
        .try_wait()
        .expect("can ask whether it finished")
        .is_none()
    {
        assert!(
            start.elapsed() < std::time::Duration::from_secs(secs),
            "still running after {secs}s — it is loading a tree instead of answering"
        );
        std::thread::sleep(std::time::Duration::from_millis(20));
    }
    child.wait_with_output().expect("collects what it printed")
}

#[test]
fn every_spelling_of_help_prints_the_usage_and_runs_nothing() {
    let cwd = a_place_with_a_broken_agent_in_it("help-spellings");
    for spelling in ["help", "-h", "--help"] {
        let mut cmd = pact();
        cmd.arg(spelling).current_dir(&cwd);
        let o = within(20, cmd);
        let (stdout, stderr) = out(&o);

        assert_eq!(
            o.status.code(),
            Some(0),
            "`pact {spelling}` must succeed:\n{stdout}{stderr}"
        );
        assert!(
            stdout.contains("USAGE:"),
            "`pact {spelling}` printed no usage:\n{stdout}{stderr}"
        );
        assert!(
            stdout.contains("pact check"),
            "`pact {spelling}` must list the commands:\n{stdout}"
        );
        // The load that must not have happened. `nmae` is only reachable by
        // reading the directory this ran in.
        for evidence_of_a_load in ["nmae", "error:", "problem(s)", "loaded cleanly"] {
            assert!(
                !stdout.contains(evidence_of_a_load) && !stderr.contains(evidence_of_a_load),
                "`pact {spelling}` loaded the current directory instead of answering \
                 ({evidence_of_a_load:?}):\n{stdout}{stderr}"
            );
        }
    }
}

#[test]
fn asking_for_help_in_a_directory_full_of_checkouts_comes_back_at_once() {
    // The reported symptom, held under test where it actually bit: run from the
    // repository root, `check .` descends into `research/repos` and does not
    // return inside two minutes. Help must not depend on what is on disk at all.
    let mut cmd = pact();
    cmd.arg("--help").current_dir(repo());
    let o = within(20, cmd);
    let (stdout, _) = out(&o);
    assert_eq!(o.status.code(), Some(0));
    assert!(stdout.contains("USAGE:"), "{stdout}");
}

#[test]
fn help_answers_even_when_a_command_was_asked_for_first() {
    // `pact check --help` is what somebody types when they want to know what
    // `check` takes. Answering it by checking the current directory is the same
    // defect wearing a different sleeve.
    let cwd = a_place_with_a_broken_agent_in_it("check-help");
    let mut cmd = pact();
    cmd.args(["check", "--help"]).current_dir(&cwd);
    let o = within(20, cmd);
    let (stdout, stderr) = out(&o);
    assert_eq!(o.status.code(), Some(0), "{stdout}{stderr}");
    assert!(stdout.contains("USAGE:"), "{stdout}");
    assert!(
        !stdout.contains("nmae"),
        "it checked the directory anyway:\n{stdout}"
    );
}

#[test]
fn an_agent_that_happens_to_be_called_help_is_still_reachable() {
    // The cost of recognising `help` anywhere on the line would be that
    // `pact card help .` can never ask for an agent named `help`. So the bare
    // word counts only in first position, and this is the test that says so.
    let o = pact()
        .args(["card", "help", &example()])
        .output()
        .expect("runs");
    let (stdout, stderr) = out(&o);
    assert!(
        !stdout.contains("USAGE:"),
        "`card help` was swallowed by the usage:\n{stdout}"
    );
    assert!(
        stderr.contains("no agent named 'help'"),
        "it should have gone looking for the agent:\n{stderr}"
    );
}

#[test]
fn a_misspelt_flag_is_refused_rather_than_ignored() {
    // Verified before the fix: this printed
    // "OK — examples/refund-desk loaded cleanly (468 settings)." and exited 0 —
    // non-quiet, having been asked for quiet, with no mention of the typo.
    let o = pact()
        .args(["check", "--quite", &example()])
        .output()
        .expect("runs");
    let (stdout, stderr) = out(&o);

    assert_ne!(
        o.status.code(),
        Some(0),
        "a command nobody can act on must not report success"
    );
    assert!(
        stdout.is_empty(),
        "nothing was understood, so nothing may go to stdout:\n{stdout}"
    );
    assert!(
        stderr.contains("--quite"),
        "the refusal must quote what was typed:\n{stderr}"
    );
    assert!(
        stderr.contains("Did you mean `--quiet`?"),
        "no nearest real option offered:\n{stderr}"
    );
    assert!(
        stderr.contains("cli/unknown-option"),
        "no rule id to look up:\n{stderr}"
    );
}

#[test]
fn a_refused_option_is_answered_with_the_whole_line_ready_to_type() {
    // O7.3: the fix has to be typeable. "Use --quiet" is advice; the corrected
    // command is something a reader can paste.
    let o = pact()
        .args(["check", "--quite", &example()])
        .output()
        .expect("runs");
    let (_, stderr) = out(&o);
    let wanted = format!("pact check --quiet {}", example());
    assert!(
        stderr.contains(&wanted),
        "the corrected command is not there:\n{stderr}"
    );
}

#[test]
fn the_refusal_marks_the_word_that_was_wrong() {
    // Same shape as every other PACT diagnostic — where, what, why, how — with
    // the command line standing in for the file, because that is where the
    // mistake is. The caret matters when several options are on the line.
    let o = pact()
        .args(["check", "--quite", &example()])
        .output()
        .expect("runs");
    let (_, stderr) = out(&o);
    assert!(
        stderr.contains("the command line:1:12"),
        "no position given:\n{stderr}"
    );
    assert!(
        stderr.contains("1 | pact check --quite "),
        "the typed line is not shown:\n{stderr}"
    );
    assert!(
        stderr.contains("^^^^^^^"),
        "the wrong word is not marked:\n{stderr}"
    );
}

#[test]
fn every_unrecognised_option_is_named_not_only_the_first() {
    // `check` reports every problem in a tree at once for a reason: a reader who
    // fixes one thing and is then told about the next learns to run the command
    // twice. The command line gets the same treatment.
    let o = pact()
        .args(["check", "--quite", "--verbse", &example()])
        .output()
        .expect("runs");
    let (_, stderr) = out(&o);
    assert!(stderr.contains("--quite"), "{stderr}");
    assert!(
        stderr.contains("--verbse"),
        "the second mistake went unmentioned:\n{stderr}"
    );
}

#[test]
fn an_option_nothing_like_a_real_one_still_names_the_options_that_exist() {
    // A wrong guess is worse than none, so nothing is suggested here. That makes
    // naming the real options compulsory — otherwise the reader is told they are
    // wrong and given no way to find out what right looks like.
    let o = pact()
        .args(["check", "--verbose", &example()])
        .output()
        .expect("runs");
    let (_, stderr) = out(&o);
    assert!(
        !stderr.contains("Did you mean"),
        "nothing is close enough to suggest:\n{stderr}"
    );
    assert!(
        stderr.contains("`--quiet`"),
        "the real options are not named:\n{stderr}"
    );
    let wanted = format!("pact check {}", example());
    assert!(
        stderr.contains(&wanted),
        "the corrected command is not there:\n{stderr}"
    );
}

#[test]
fn a_single_dash_typo_is_refused_instead_of_being_read_as_a_folder() {
    // Before this, only `--` was treated as an option marker, so `-q` fell
    // through to the path slot and the reader was told "'-q' does not exist" —
    // sending them to look for a missing folder instead of at the word they
    // mistyped.
    let o = pact()
        .args(["check", "-q", &example()])
        .output()
        .expect("runs");
    let (_, stderr) = out(&o);
    assert!(
        stderr.contains("`-q` is not something `pact` takes"),
        "{stderr}"
    );
    assert!(
        !stderr.contains("does not exist"),
        "it is not a missing folder:\n{stderr}"
    );
}

#[test]
fn the_option_that_does_exist_still_does_what_it_says() {
    // The guard on the fix itself: refusing the near-misses must not disturb the
    // one real option. Compared against the same command without it rather than
    // against fixed text, so this keeps working whatever state the example is in.
    let loud = pact().args(["check", &example()]).output().expect("runs");
    let quiet = pact()
        .args(["check", "--quiet", &example()])
        .output()
        .expect("runs");
    assert_eq!(
        loud.status.code(),
        quiet.status.code(),
        "the option must not change the verdict"
    );

    let (loud_out, _) = out(&loud);
    let (quiet_out, _) = out(&quiet);
    assert!(
        loud_out.contains("OK —") || loud_out.contains("problem(s)"),
        "without --quiet there must be a summary:\n{loud_out}"
    );
    assert!(
        !quiet_out.contains("OK —") && !quiet_out.contains("problem(s)"),
        "--quiet must still suppress the summary:\n{quiet_out}"
    );
}

/// The options the usage advertises, read out of the running binary.
fn options_the_usage_advertises() -> BTreeSet<String> {
    let o = pact().arg("help").output().expect("runs");
    let (stdout, _) = out(&o);
    let block = stdout
        .split("OPTIONS:")
        .nth(1)
        .expect("the usage must have an OPTIONS: section");
    block
        .split_whitespace()
        .filter(|w| w.starts_with("--"))
        .map(|w| {
            w.trim_matches(|c: char| !c.is_ascii_alphanumeric() && c != '-')
                .to_string()
        })
        .collect()
}

#[test]
fn every_option_the_usage_advertises_is_one_the_parser_accepts() {
    // Documentation and behaviour drift apart silently in both directions, and
    // the direction that hurts is an option a reader can see and cannot use.
    let advertised = options_the_usage_advertises();
    assert!(
        !advertised.is_empty(),
        "no options found in the usage at all"
    );
    for option in &advertised {
        let o = pact()
            .args(["check", option, &example()])
            .output()
            .expect("runs");
        let (_, stderr) = out(&o);
        assert!(
            !stderr.contains("cli/unknown-option"),
            "the usage offers `{option}` and the parser refuses it:\n{stderr}"
        );
    }
}

#[test]
fn the_options_a_refusal_names_are_exactly_the_ones_the_usage_advertises() {
    // The other direction, which no amount of reading the usage would catch: an
    // option that works but is documented nowhere. The refusal names the whole
    // set the parser enforces, so comparing it against the usage closes the loop
    // through the binary rather than through a list a test also has to be told.
    let o = pact()
        .args(["check", "--verbose", &example()])
        .output()
        .expect("runs");
    let (_, stderr) = out(&o);
    let named: BTreeSet<String> = stderr
        .split('`')
        .skip(1)
        .step_by(2)
        .filter(|w| w.starts_with("--") && *w != "--verbose")
        .map(str::to_string)
        .collect();
    assert_eq!(
        named,
        options_the_usage_advertises(),
        "what the refusal offers and what the usage documents have drifted apart"
    );
}

#[test]
fn the_refusal_reads_without_programming_knowledge() {
    // Same bar as the schema's help text and the loader's diagnostics (D13). The
    // person most likely to mistype an option is the one least able to read an
    // explanation written for the person who wrote the parser.
    const JARGON: &[&str] = &[
        "flag",
        "flags",
        "argv",
        "arg",
        "args",
        "argument",
        "parser",
        "parse",
        "cli",
        "unwrap",
        "enum",
        "struct",
        "stdout",
        "stderr",
        "string",
        "token",
        "positional",
        "invalid",
        "unrecognized",
        "unrecognised",
    ];
    let o = pact()
        .args(["check", "--verbose", &example()])
        .output()
        .expect("runs");
    let (_, stderr) = out(&o);
    let said = stderr.to_lowercase();
    // Only the sentences a reader is meant to act on. The rule id is a lookup
    // key, the echoed line is their own words quoted back, and a folder name is
    // never prose — `crates/pact-cli` is where they ran it, not a word this
    // message chose.
    let prose: String = said
        .lines()
        .filter(|l| l.starts_with("error:") || l.trim_start().starts_with("fix:"))
        .flat_map(str::split_whitespace)
        .filter(|w| !w.contains('/'))
        .collect::<Vec<_>>()
        .join(" ");
    for word in JARGON {
        let says_it = prose
            .split(|c: char| !c.is_ascii_alphanumeric())
            .any(|t| t == *word);
        assert!(!says_it, "'{word}' assumes programming knowledge:\n{prose}");
    }
}

#[test]
fn typing_just_pact_answers_at_once_and_says_what_the_commands_are() {
    // The first thing a new author types. It used to mean `check .`, and from a
    // repository root holding other checkouts that walk does not return —
    // measured at four minutes and still going, descending into
    // `research/repos` — so the first command anybody types looked like a hang.
    // A reader who typed nothing has asked what the commands are.
    //
    // `within` rather than a bare run: a regression here is a HANG, and a test
    // that hangs tells you nothing about which change caused it.
    let mut cmd = pact();
    cmd.current_dir(repo());
    let out = within(20, cmd);
    let said = String::from_utf8_lossy(&out.stdout);
    assert!(out.status.success(), "{said}");
    assert!(
        said.contains("USAGE:"),
        "it has to say what the commands are:\n{said}"
    );
    for verb in ["check", "show", "waits", "discover", "card"] {
        assert!(
            said.contains(verb),
            "`{verb}` missing from the usage:\n{said}"
        );
    }
}
