//! End-to-end: the underline `pact check` prints must mark the thing the
//! sentence above it names (D13 / O7.3).
//!
//! These run the real binary against a real tree, because the defect they lock
//! down was invisible to unit tests: every part of the diagnostic was correct
//! on its own, and the *rendering* pointed somewhere else. What a non-coder
//! judges PACT by is this output, so this is where it has to be checked.
//!
//! Before this was fixed, deleting the `description:` line from the worked
//! example's fraud-checker printed:
//!
//! ```text
//! 1 | name: Fraud Checker
//!   |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
//! ```
//!
//! — 80 carets from column 5 under a 19-character line, most of them under
//! nothing, and all of them under the one line in the file that was correct.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply `edits` as (file, from, to), return the root.
fn broken(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-caret-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not found in {file}"
        );
        std::fs::write(&p, text.replace(from, to)).unwrap();
    }
    dst.to_string_lossy().into_owned()
}

/// Delete the line beginning `prefix` from a file in the copied tree. This is
/// how an author creates a missing field — not by writing something wrong, but
/// by not writing anything — and it is done by prefix so that rewording the
/// example's sentences cannot quietly turn this test into a no-op.
fn delete_line(root: &str, file: &str, prefix: &str) {
    let p = std::path::Path::new(root).join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    let kept: Vec<&str> = text.lines().filter(|l| !l.starts_with(prefix)).collect();
    assert!(
        kept.len() < text.lines().count(),
        "fixture drifted: no {prefix:?} line in {file}"
    );
    std::fs::write(&p, format!("{}\n", kept.join("\n"))).unwrap();
}

/// Blank the value on the line beginning `prefix`, keeping the name and the
/// colon, and return the line number it is now on. This is the *other* way an
/// author leaves a field unset — not by deleting the line but by half-writing
/// it — and it is done by prefix for the same reason [`delete_line`] is.
fn empty_the_value_on(root: &str, file: &str, prefix: &str) -> usize {
    let p = std::path::Path::new(root).join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    let mut at = None;
    let kept: Vec<String> = text
        .lines()
        .enumerate()
        .map(|(i, l)| {
            if at.is_none() && l.starts_with(prefix) {
                at = Some(i + 1);
                prefix.to_string()
            } else {
                l.to_string()
            }
        })
        .collect();
    let at = at.unwrap_or_else(|| panic!("fixture drifted: no {prefix:?} line in {file}"));
    std::fs::write(&p, format!("{}\n", kept.join("\n"))).unwrap();
    at
}

/// Move the line beginning `prefix` to the very bottom of the file, with its
/// value blanked, and return the line number it lands on.
fn empty_the_value_and_put_it_last(root: &str, file: &str, prefix: &str) -> usize {
    delete_line(root, file, prefix);
    let p = std::path::Path::new(root).join(file);
    let mut text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    if !text.ends_with('\n') {
        text.push('\n');
    }
    text.push_str(prefix);
    text.push('\n');
    let at = text.lines().count();
    std::fs::write(&p, text).unwrap();
    at
}

/// Where a block begins: the first line of a file that is a setting rather than
/// a comment or a blank, as (line number, the text of it). This is the line a
/// report about a MISSING setting borrows its position from, and it is read off
/// the copied file rather than written down here so that adding a comment to the
/// worked example cannot turn the assertion below into a lie about line 2.
fn first_setting_line(root: &str, file: &str) -> (usize, String) {
    let p = std::path::Path::new(root).join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    text.lines()
        .enumerate()
        .find(|(_, l)| !l.trim().is_empty() && !l.trim_start().starts_with('#'))
        .map(|(i, l)| (i + 1, l.to_string()))
        .unwrap_or_else(|| panic!("{file} has no settings in it at all"))
}

/// Write a new file into the copied tree, making its folders on the way. This
/// is how an author writes a document as a FOLDER instead of a file — one
/// setting per file — which is the shape where a report about a missing line has
/// no text of the author's to quote at all.
fn write_file(root: &str, file: &str, text: &str) {
    let p = std::path::Path::new(root).join(file);
    std::fs::create_dir_all(p.parent().expect("a file has a folder")).unwrap();
    std::fs::write(&p, text).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
}

fn copy_dir(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}

fn check(root: &str) -> String {
    let out = pact()
        .args(["check", root])
        .output()
        .expect("the binary runs");
    let text = String::from_utf8_lossy(&out.stdout).into_owned();
    assert!(
        !out.status.success(),
        "these fixtures must be refused:\n{text}"
    );
    text
}

/// One underline in the rendered output: the source line it sits under, how far
/// in it starts, and how many carets it draws — all counted in characters,
/// which is what the reader sees, rather than bytes.
struct Underline {
    source_line: String,
    indent: usize,
    carets: usize,
}

/// Every reported problem carrying `rule`, each whole. Found by rule id and not
/// by its wording, because the wording is meant to be rewritten as it gets
/// clearer and a test that pins it would make every improvement look like a
/// break.
fn problems_about(rendered: &str, rule: &str) -> Vec<String> {
    let mut found = Vec::new();
    let mut block: Vec<&str> = Vec::new();
    for line in rendered.lines() {
        if ["error: ", "warning: ", "note: "]
            .iter()
            .any(|k| line.starts_with(k))
        {
            block.clear();
        }
        block.push(line);
        if line.trim_start() == format!("rule: {rule}") {
            found.push(block.join("\n"));
            block.clear();
        }
    }
    found
}

/// The first reported problem carrying `rule`, whole.
fn problem_about(rendered: &str, rule: &str) -> String {
    problems_about(rendered, rule)
        .into_iter()
        .next()
        .unwrap_or_else(|| panic!("nothing was reported under {rule}:\n{rendered}"))
}

/// The source lines one reported problem quotes, with the gutter stripped.
///
/// A quoted line is the one row of the excerpt carrying a line NUMBER in its
/// gutter. The `  | ^^^` row under it does not, and neither does the bare `  |`
/// that opens the excerpt, so neither is counted as a line of the author's file.
fn quoted_source_lines(block: &str) -> Vec<String> {
    block
        .lines()
        .filter_map(|row| row.split_once(" | "))
        .filter(|(gutter, _)| gutter.trim().parse::<u32>().is_ok())
        .map(|(_, text)| text.to_string())
        .collect()
}

/// Every underline in a `pact check` report. The gutter (`3 | `) is stripped
/// from both rows; `split_once` takes the first ` | `, which is always the
/// gutter, so a source line containing ` | ` itself survives intact.
fn underlines(rendered: &str) -> Vec<Underline> {
    let lines: Vec<&str> = rendered.lines().collect();
    let mut found = Vec::new();
    for (i, row) in lines.iter().enumerate() {
        let after_gutter = match row.split_once(" | ") {
            Some((_, r)) => r,
            None => continue,
        };
        if after_gutter.is_empty() || !after_gutter.chars().all(|c| c == '^' || c == ' ') {
            continue;
        }
        let carets = after_gutter.chars().filter(|c| *c == '^').count();
        if carets == 0 {
            continue;
        }
        let source_line = lines[i - 1].split_once(" | ").map_or("", |(_, r)| r);
        found.push(Underline {
            source_line: source_line.to_string(),
            indent: after_gutter.chars().count() - carets,
            carets,
        });
    }
    found
}

#[test]
fn a_caret_never_runs_past_the_end_of_the_line_it_underlines() {
    // Several real mistakes at once, so the check is over whatever underlines
    // the report actually draws rather than one hand-picked one. The last is
    // the one that used to overrun: indenting a description into a block gives
    // the diagnostic a span covering *both* lines of it, and only the first is
    // on screen. It drew 80 carets from column 7 under a 60-character line.
    let root = broken(
        "overrun",
        &[
            (
                "agents/refund-desk/needs.yaml",
                "reasoning: careful",
                "reasoning: brilliant",
            ),
            (
                "agents/refund-desk/limits.yaml",
                "finishes-within: 30s",
                "finishes-within: soon",
            ),
            // A `text` field written as a block whose entries are NOT all prose.
            // The all-prose case is now the "split it up when it gets long" form
            // both READMEs promise and is accepted, so the fixture that produces
            // a multi-line span had to become one that is still a mistake — a
            // nested block under a field that holds words.
            (
                "agents/fraud-checker/agent.yaml",
                "description: Looks for signs that a refund request is not genuine.",
                "description:\n  what:\n    long: Looks for signs that a refund request is \
                 not genuine\n  when: whenever a customer asks for their money back",
            ),
        ],
    );
    let text = check(&root);
    let drawn = underlines(&text);
    assert!(
        drawn.len() >= 3,
        "expected an underline per mistake, got {}:\n{text}",
        drawn.len()
    );

    for u in &drawn {
        let len = u.source_line.chars().count();
        // `len + 1` and not `len`: a caret one column past the last character
        // is how "something is missing at the end of this line" points, and it
        // is still on the line. Anything beyond that is in the margin.
        assert!(
            u.indent + u.carets <= len + 1,
            "an underline of {} carets starting at column {} runs off a {len}-character line:\n\
             {}\n{}{}\nfull report:\n{text}",
            u.carets,
            u.indent + 1,
            u.source_line,
            " ".repeat(u.indent),
            "^".repeat(u.carets),
        );
        assert!(
            u.carets >= 1,
            "an empty underline points at nothing:\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_missing_field_does_not_point_the_caret_at_an_unrelated_value() {
    // Deleting a required line is the commonest mistake there is, and the
    // block's span begins at the first value in it — so the report used to
    // underline `name: Fraud Checker` to say `description` was absent, marking
    // the one line that was right.
    let root = broken("missing", &[]);
    delete_line(&root, "agents/fraud-checker/agent.yaml", "description:");
    let text = check(&root);

    let block = problem_about(&text, "schema/missing-field");
    assert!(
        block.contains("'description'"),
        "it must name the line that is absent:\n{block}"
    );
    assert!(
        !block.contains('^'),
        "a line that was never written has nothing to underline:\n{block}"
    );
    assert!(
        !block.contains("Fraud Checker") || block.contains("1 | name: Fraud Checker"),
        "the value may be shown as context, never marked:\n{block}"
    );
    assert!(
        block.contains("agents/fraud-checker/agent.yaml:1:1"),
        "it still has to say which file and where the block starts:\n{block}"
    );
    let fix = block
        .lines()
        .find(|l| l.trim_start().starts_with("fix: "))
        .unwrap_or_else(|| panic!("O7.3: every diagnostic owes a fix:\n{block}"));
    assert!(
        fix.contains("description:"),
        "and it still has to give the line the author can type:\n{fix}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_missing_line_is_reported_without_quoting_a_line_that_is_not_the_one_missing() {
    // The test above says the report must not MARK a correct line. This says it
    // must not QUOTE one either, which is the same claim one step quieter: a
    // reader who is told something is wrong and then shown a single line of
    // their file reads the two as one sentence, and the sentence says "this
    // line". Only an underline can say otherwise, and a line the author never
    // wrote has nothing to put one under.
    //
    // Both measured shapes are in one tree, because the fix has to hold for
    // both and each failed differently:
    //
    // (a) A FILE. `agents/refund-desk/agent.yaml` opens with a comment, so its
    //     block begins on line 2 and the report opened the gutter at
    //     `agent.yaml:2:1` and printed
    //
    //         2 | name: Refund Desk
    //
    //     with no caret, then went straight to `fix:`. Line 2 is `name:`, which
    //     has nothing to do with the absent `description` — so the one line of
    //     the file the reader was shown was a line that was already right.
    //
    // (b) A FOLDER. `tools/weather/` written one-setting-per-file IS the tool,
    //     so the report names a directory. There is no text of the author's to
    //     quote at all, and there never can be.
    //
    // The third edit is the guard against fixing this by never quoting
    // anything: a wrong VALUE still has to be quoted and marked.
    let root = broken(
        "missing-quotes-nothing",
        &[(
            "agents/refund-desk/needs.yaml",
            "reasoning: careful",
            "reasoning: brilliant",
        )],
    );
    delete_line(&root, "agents/refund-desk/agent.yaml", "description:");
    write_file(
        &root,
        "tools/weather/actions.yaml",
        "forecast:\n  description: Look up the forecast.\n  takes:\n    city: text\n  \
         reads-only: yes\n",
    );
    // Host-resolved: this test is about where the caret lands, and the tree it
    // builds on says `allow-egress: []`.
    write_file(&root, "tools/weather/url.txt", "host/forecast");
    write_file(&root, "tools/weather/method.txt", "get");
    let text = check(&root);

    let blocks = problems_about(&text, "schema/missing-field");
    let in_a_file = blocks
        .iter()
        .find(|b| b.contains("agents/refund-desk/agent.yaml"))
        .unwrap_or_else(|| panic!("(a) a file with a required line deleted:\n{text}"));
    // Matched on the arrow ENDING at the folder. It used to read `tools/weather:`,
    // because a folder was given a line and a column like a file — and a reader
    // sent to line 1 column 1 of a directory opens whatever they can find. A
    // folder has no lines, so the arrow now stops at the name.
    let in_a_folder = blocks
        .iter()
        .find(|b| {
            b.lines()
                .any(|l| l.trim_start().starts_with("--> ") && l.ends_with("tools/weather"))
        })
        .unwrap_or_else(|| panic!("(b) a folder with no description in it:\n{text}"));

    for block in [in_a_file, in_a_folder] {
        assert!(
            quoted_source_lines(block).is_empty(),
            "a line the author never wrote cannot be underlined, so no line of theirs \
             may be quoted under a sentence about it:\n{block}"
        );
        assert!(
            !block.contains('^'),
            "and nothing may be marked either:\n{block}"
        );
        // What is left still has to be the four parts every diagnostic owes.
        assert!(
            block.contains("'description'"),
            "it must name the line that is absent:\n{block}"
        );
        let fix = block
            .lines()
            .find(|l| l.trim_start().starts_with("fix: "))
            .unwrap_or_else(|| panic!("O7.3: every diagnostic owes a fix:\n{block}"));
        assert!(
            fix.contains("description:"),
            "and give the line to type:\n{fix}"
        );
    }
    let (begins_at, already_right) = first_setting_line(&root, "agents/refund-desk/agent.yaml");
    assert!(
        in_a_file.contains(&format!("agents/refund-desk/agent.yaml:{begins_at}:1")),
        "it still has to say which file, and which line the block begins on:\n{in_a_file}"
    );
    assert!(
        !in_a_file.contains(already_right.trim()),
        "line {begins_at} — `{}` — is the line the report used to quote, and it is a line \
         that was already right:\n{in_a_file}",
        already_right.trim()
    );

    // And the guard: a value that IS written and IS wrong is still quoted, and
    // still marked. Without this the whole report could go silent and pass.
    let wrong_value = underlines(&text)
        .into_iter()
        .find(|u| u.source_line.contains("brilliant"))
        .unwrap_or_else(|| panic!("a wrong value must still be quoted and marked:\n{text}"));
    assert_eq!(
        wrong_value.indent,
        "reasoning: ".chars().count(),
        "under the value:\n{text}"
    );
    assert_eq!(
        wrong_value.carets,
        "brilliant".chars().count(),
        "as wide as it:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_setting_whose_value_was_never_written_is_marked_on_its_own_line() {
    // Typing the name and then not the value is the commonest way to leave a
    // file half-done, and it was reported against somebody else's line.
    // Blanking `description:` in the worked example's Slack port printed
    //
    //     error: 'description' should be some text, but it is nothing.
    //       --> slack.yaml:2:1
    //     2 | kind: conversation
    //       | ^
    //
    // — one caret under the line BELOW the mistake, which was entirely correct,
    // while the line actually named was not on screen at all. An unwritten
    // value occupies no characters and so has no position; the name beside it
    // does, and that is the only thing the reader can be shown.
    let root = broken("empty-value", &[]);
    let at = empty_the_value_on(&root, "ports/slack.yaml", "description:");
    let text = check(&root);

    let block = problem_about(&text, "schema/wrong-type");
    assert!(
        block.contains(&format!("slack.yaml:{at}:1")),
        "the report must name the line the author left empty, not the one after it:\n{block}"
    );
    let u = underlines(&text)
        .into_iter()
        .find(|u| u.source_line.starts_with("description:"))
        .unwrap_or_else(|| panic!("the half-written line must be the one underlined:\n{text}"));
    assert_eq!(u.indent, 0, "the underline starts at the name");
    assert_eq!(
        u.carets,
        "description".chars().count(),
        "and is as wide as it:\n{text}"
    );
    assert!(
        !underlines(&text)
            .iter()
            .any(|u| u.source_line.starts_with("kind:")),
        "no correct line may be marked to report a different line's mistake:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_setting_left_empty_at_the_bottom_of_a_file_is_still_shown() {
    // The same mistake on the last line was worse than misdirected: it pointed
    // one line PAST the end of the file, so there was no line to quote and the
    // report printed no excerpt at all — a location the author cannot open to,
    // under a sentence about a file they are looking at.
    let root = broken("empty-value-last", &[]);
    let at = empty_the_value_and_put_it_last(&root, "ports/slack.yaml", "description:");
    let text = check(&root);

    let block = problem_about(&text, "schema/wrong-type");
    assert!(
        block.contains(&format!("slack.yaml:{at}:1")),
        "line {at} is the last line there is; anything past it is nowhere:\n{block}"
    );
    assert!(
        block.contains(&format!("{at} | description:")),
        "a line inside the file has to be quoted, not just numbered:\n{block}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_caret_under_an_accented_word_is_as_wide_as_the_word() {
    // Bytes are not columns. `café` is 5 bytes and 4 characters, so a
    // byte-counted underline overhangs it and starts naming whatever follows.
    // The trailing comment is what makes the difference visible: without it the
    // end-of-line clamp would hide the miscount.
    let root = broken(
        "accents",
        &[(
            "agents/refund-desk/needs.yaml",
            "reasoning: careful",
            "reasoning: café  # not one of the allowed words",
        )],
    );
    let text = check(&root);
    let u = underlines(&text)
        .into_iter()
        .find(|u| u.source_line.contains("café"))
        .unwrap_or_else(|| panic!("the bad word must be underlined:\n{text}"));

    assert_eq!(
        u.indent,
        "reasoning: ".chars().count(),
        "the underline starts at the value"
    );
    assert_eq!(
        u.carets,
        "café".chars().count(),
        "four characters, not five bytes:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}
