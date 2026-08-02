//! One mistake must produce one message, and the message's fix must be a line
//! that leaves the file CORRECT once it is typed.
//!
//! The defect this pins down: misspelling a required setting produced two
//! errors. `desription:` in `agents/refund-desk/agent.yaml` drew
//!
//! ```text
//! error: An agent must have a 'description'.
//!   fix: Add a line: `description: ...`
//! error: 'desription' is not something an agent can have.
//!   fix: Did you mean 'description'?
//! ```
//!
//! and the first one sorts first, so the advice a D13 author acts on is the one
//! that adds a second key beside the misspelt one. They followed the tool and
//! ended up with a worse file than they started with — the exact opposite of
//! what O7.3 promises when it says every refusal carries a line you can type.
//! Measured across twelve typos on the worked example: eight produced the pair.
//!
//! Run against the real binary on a real copy of the worked example, because
//! the thing under test is what the author is shown, not what a validator
//! returns to a caller.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// A private copy of the worked example with `edits` applied, as (file, from, to).
///
/// Named per test so two of these can run at once — `cargo test` is threaded,
/// and a shared directory would make the failures depend on the schedule.
fn copy_with(name: &str, edits: &[(&str, &str, &str)]) -> std::path::PathBuf {
    let dst =
        std::env::temp_dir().join(format!("pact-one-typo-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(text.contains(from), "fixture drifted: {from:?} is not in {file}");
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    dst
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

/// Everything `pact check` printed about a tree.
fn check(root: &std::path::Path) -> String {
    let o = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
    String::from_utf8_lossy(&o.stdout).into_owned()
}

/// The rule name of each problem the author was shown, in the order shown.
///
/// Counted off the rendered output rather than off a `Diagnostics` value: one
/// rendered block is one thing the reader has to deal with, and that is the
/// quantity this file is about.
fn problems(text: &str) -> Vec<String> {
    text.lines()
        .filter_map(|l| l.trim().strip_prefix("rule: ").map(str::to_string))
        .collect()
}

#[test]
fn misspelling_a_required_setting_is_one_message_and_not_also_a_complaint_that_it_is_missing() {
    let root = copy_with("top-level", &[("agents/refund-desk/agent.yaml", "description:", "desription:")]);
    let text = check(&root);
    assert_eq!(
        problems(&text),
        vec!["schema/unknown-field"],
        "one misspelt line must be one problem, not two:\n{text}"
    );
    assert!(text.contains("Did you mean 'description'?"), "{text}");
    // The half that used to arrive first and do the damage.
    assert!(
        !text.contains("must have a 'description'"),
        "the file has a description — it is spelt wrong, which is a different \
         thing from absent, and saying both invites the author to add a second \
         one:\n{text}"
    );
}

#[test]
fn misspelling_a_required_setting_inside_a_nested_block_is_one_message_too() {
    // `auth:` is a `credential-reference` written inline on one line, so both
    // messages landed on the SAME line — which made the pair even harder to read
    // than the top-level case, and is why the fix belongs in `check_group`
    // rather than at the root.
    let root = copy_with("nested", &[("resources/zendesk-server.yaml", "by-reference:", "byref:")]);
    let text = check(&root);
    assert_eq!(
        problems(&text),
        vec!["schema/unknown-field"],
        "a nested block must behave like the top level:\n{text}"
    );
    assert!(text.contains("Did you mean 'by-reference'?"), "{text}");
    assert!(!text.contains("must have a 'by-reference'"), "{text}");
}

#[test]
fn typing_the_fix_the_one_message_gives_leaves_a_tree_that_checks_clean() {
    // The guarantee behind the count. A message that is merely SINGLE could still
    // be useless; what matters is that doing exactly what it says finishes the
    // job. So the fix is applied literally — rename the misspelt key to the name
    // the message offered — and the tree is checked again.
    for (name, file, wrong, right) in [
        ("typed-top-level", "agents/refund-desk/agent.yaml", "desription:", "description:"),
        ("typed-nested", "resources/zendesk-server.yaml", "byref:", "by-reference:"),
    ] {
        let root = copy_with(name, &[(file, right, wrong)]);
        let told = check(&root);
        assert!(told.contains(&format!("Did you mean '{}'?", right.trim_end_matches(':'))), "{told}");

        // The author types what they were told, and nothing else.
        let p = root.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        std::fs::write(&p, text.replacen(wrong, right, 1)).unwrap();

        let after = pact().args(["check", root.to_str().unwrap()]).output().expect("runs");
        assert!(
            after.status.success(),
            "following the fix has to finish the job, not open the next problem:\n{}",
            String::from_utf8_lossy(&after.stdout)
        );
    }
}

#[test]
fn a_required_setting_that_is_genuinely_absent_is_still_reported() {
    // The other side of the trade. Suppressing the missing-field message
    // whenever ANY unknown key is present would be a worse bug than the one
    // being fixed, so the suppression is tied to the specific name suggested:
    // here nothing is misspelt, the line is simply gone.
    let root = copy_with(
        "absent",
        &[(
            "agents/refund-desk/agent.yaml",
            "description: Decides whether a customer's refund request should be approved.",
            "",
        )],
    );
    let text = check(&root);
    assert!(
        text.contains("must have a 'description'"),
        "an absent required setting must still be named:\n{text}"
    );
    assert!(text.contains("Add a line: `description: ...`"), "{text}");
}

#[test]
fn a_typo_pointing_at_one_setting_does_not_silence_a_different_one_that_is_missing() {
    // Two different mistakes in one block are two messages. `instuctions:` is a
    // misspelling of `instructions:`, which this agent already supplies from
    // `instructions.md` beside it and which has nothing to do with
    // `description:` — so the missing description must still be reported,
    // and the suppression must not have been a blanket "this block has unknown
    // keys in it, say nothing else".
    let root = copy_with(
        "two-mistakes",
        &[(
            "agents/refund-desk/agent.yaml",
            "description: Decides whether a customer's refund request should be approved.",
            "instuctions: Decide whether a refund should be approved.",
        )],
    );
    let text = check(&root);
    let shown = problems(&text);
    assert!(
        shown.contains(&"schema/unknown-field".to_string())
            && shown.contains(&"schema/missing-field".to_string()),
        "two unrelated mistakes are two messages, got {shown:?}:\n{text}"
    );
    assert!(text.contains("Did you mean 'instructions'?"), "{text}");
    assert!(text.contains("must have a 'description'"), "{text}");
}

/// Every misspelling the checker offers a name for, across the whole worked
/// example — not the two this file started with.
///
/// The guarantee is one sentence: **doing exactly what the fix says finishes the
/// job.** Two cases proved it for two keys; this proves it for every key the
/// flagship writes, which is the only version of the claim worth making. A fix
/// line is the entire interface a D13 author has with a mistake, and a fix that
/// is refused when typed is worse than silence — they now have two problems and
/// no reason to trust the next message.
///
/// It found one. `loader/never-offered` told an author to "Add `skills:`" to an
/// agent, and `skills` is not something an agent can have, so typing the fix
/// produced `schema/unknown-field`. That is fixed where it belonged — in the
/// specification, which now states what satisfies each condition and is held to
/// naming something an agent really has.
///
/// **Mutation:** make any `fix:` line offer a name the schema does not carry.
#[test]
fn every_fix_that_names_a_setting_leaves_a_tree_that_checks_clean() {
    let root = copy_with("sweep-base", &[]);
    let keys = keys_written_under(&root);
    assert!(
        keys.len() > 40,
        "only {} keys found — the sweep is not covering the example",
        keys.len()
    );

    let mut checked = 0usize;
    let mut broken: Vec<String> = Vec::new();
    for (file, line_no, key) in keys {
        let typo = drop_a_letter(&key);
        if typo == key {
            continue;
        }
        let dst = copy_with(&format!("sweep-{}-{}", sanitise(&file), line_no), &[]);
        rewrite_key(&dst, &file, line_no, &key, &typo);

        let told = check(&dst);
        let Some(suggested) = did_you_mean(&told) else {
            // Not an unknown-field case: a map key an author chooses, or a name
            // resolved against another document, which get their own sentence.
            let _ = std::fs::remove_dir_all(&dst);
            continue;
        };
        rewrite_key(&dst, &file, line_no, &typo, &suggested);
        let after = pact().args(["check", dst.to_str().unwrap()]).output().expect("runs");
        if !after.status.success() {
            broken.push(format!(
                "{file}:{}: typed `{suggested}` as told and got:\n{}",
                line_no + 1,
                String::from_utf8_lossy(&after.stdout)
            ));
        }
        checked += 1;
        let _ = std::fs::remove_dir_all(&dst);
    }
    let _ = std::fs::remove_dir_all(&root);

    assert!(
        checked > 30,
        "only {checked} fixes were offered across the example — the sweep stopped working"
    );
    assert!(
        broken.is_empty(),
        "{} fix line(s) did not leave a tree that checks clean:\n\n{}",
        broken.len(),
        broken.join("\n\n")
    );
}

/// A realistic typo: one letter gone from the middle.
fn drop_a_letter(key: &str) -> String {
    if key.len() > 4 {
        format!("{}{}", &key[..2], &key[3..])
    } else {
        key.to_owned()
    }
}

fn sanitise(file: &str) -> String {
    file.chars().map(|c| if c.is_ascii_alphanumeric() { c } else { '-' }).collect()
}

fn did_you_mean(text: &str) -> Option<String> {
    let at = text.find("Did you mean '")? + "Did you mean '".len();
    let rest = &text[at..];
    Some(rest[..rest.find('\'')?].to_owned())
}

/// Every `key:` written anywhere in the tree, once per line.
fn keys_written_under(root: &std::path::Path) -> Vec<(String, usize, String)> {
    let mut out = Vec::new();
    let mut seen = std::collections::BTreeSet::new();
    let mut files: Vec<std::path::PathBuf> = Vec::new();
    collect_yaml(root, &mut files);
    files.sort();
    for p in files {
        let rel = p.strip_prefix(root).unwrap().to_string_lossy().to_string();
        let Ok(text) = std::fs::read_to_string(&p) else { continue };
        for (i, line) in text.lines().enumerate() {
            let t = line.trim_start();
            let Some(colon) = t.find(':') else { continue };
            let key = &t[..colon];
            if key.is_empty()
                || key.starts_with('#')
                || key.starts_with('-')
                || !key.chars().all(|c| c.is_ascii_lowercase() || c == '-')
                || key.len() < 5
            {
                continue;
            }
            if seen.insert(key.to_owned()) {
                out.push((rel.clone(), i, key.to_owned()));
            }
        }
    }
    out
}

fn collect_yaml(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
    for e in std::fs::read_dir(dir).unwrap().flatten() {
        let p = e.path();
        if p.is_dir() {
            collect_yaml(&p, out);
        } else if p.extension().is_some_and(|x| x == "yaml") {
            out.push(p);
        }
    }
}

fn rewrite_key(root: &std::path::Path, file: &str, line_no: usize, from: &str, to: &str) {
    let p = root.join(file);
    let text = std::fs::read_to_string(&p).unwrap();
    let mut lines: Vec<String> = text.lines().map(str::to_owned).collect();
    lines[line_no] = lines[line_no].replacen(&format!("{from}:"), &format!("{to}:"), 1);
    std::fs::write(&p, lines.join("\n") + "\n").unwrap();
}
