//! **§8.3a rule 4: `pact check` says how many written rules each skill holds.**
//!
//! §8.3a's rules 1 and 2 are built: a numbered or bulleted line under a heading
//! in the closed set `# Policy | ## Policy | # Rules | ## Rules | # <name> policy`
//! is a NORMATIVE CLAUSE, and editing one needs a person however the edit is
//! made. Rule 4 is the half that makes those rules usable rather than merely
//! enforced:
//!
//! > `pact check` prints, per skill, how many clauses it classified as normative
//! > and under which heading, so the author can see the boundary and move it by
//! > editing a heading.
//!
//! Without it the boundary is invisible until somebody trips over it. An author
//! adds a rule under `## Notes` and it applies itself with nobody reading it;
//! another rewords `## Rules` to `## Working guidance` and every clause under it
//! stops being one. Both are correct behaviour and both are surprises, and the
//! remedy §8.3a names is not a warning — it is showing the author where the line
//! already falls.
//!
//! It is a NOTE, not a warning. Nothing is wrong with a skill that holds five
//! rules, or with one that holds none; the count is a fact about the document,
//! and a fact printed as a problem teaches an author to stop reading the output.
//!
//! # Why the parse is in two places, and what holds them together
//!
//! `learning.classify` reads the same structure on the other side of the wall,
//! to decide the class of a proposed EDIT. This reads it to SHOW the boundary.
//! Two purposes, one parse, and a second copy of a rule is exactly what this
//! project refuses everywhere else — so the two are held against each other on
//! the shipped body by `test_a_written_rule_needs_a_person_however_it_is_edited`
//! and by [`both_readings_of_the_shipped_policy_agree`] here, which asserts the
//! count this side prints is the number of clauses that side protects.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

fn run(args: &[&str]) -> (Option<i32>, String) {
    let out = pact().args(args).output().expect("runs");
    (
        out.status.code(),
        format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    )
}

/// The shipped policy holds five numbered rules under `## Rules`, and says so.
#[test]
fn a_skill_that_holds_written_rules_says_how_many_and_where() {
    let (code, said) = run(&["check", &example()]);
    assert_eq!(code, Some(0), "{said}");
    assert!(said.contains("refund-policy"), "name the skill:\n{said}");
    assert!(said.contains('5'), "and how many rules it holds:\n{said}");
    assert!(
        said.contains("## Rules"),
        "and under which heading, because that is the line the author moves:\n{said}"
    );
}

/// It is a note. A skill with rules in it is not a problem.
#[test]
fn saying_where_the_rules_are_is_not_a_warning() {
    let (code, said) = run(&["check", &example(), "--deny-warnings"]);
    assert_eq!(
        code,
        Some(0),
        "a fact about a document must not fail a pipeline:\n{said}"
    );
    assert!(!said.contains("warning:"), "{said}");
}

/// A workspace whose skills hold no written rules gains no line.
///
/// Additive inertness, and the reason the count is per-skill rather than a
/// summary: a tree with nothing to say says nothing.
#[test]
fn a_skill_with_no_written_rules_is_not_mentioned() {
    let tree = format!("{}/../../examples/answers-from-documents", env!("CARGO_MANIFEST_DIR"));
    let (code, said) = run(&["check", &tree, "--deny-warnings"]);
    assert_eq!(code, Some(0), "{said}");
    assert!(
        !said.contains("written rule"),
        "a workspace with no policy headings has no boundary to show:\n{said}"
    );
}

/// Moving the heading moves the boundary, and the note shows it moving.
///
/// This is what rule 4 is FOR. The author is told where the line falls, so the
/// edit that moves it is a decision rather than a discovery.
#[test]
fn rewording_the_heading_changes_what_the_note_says() {
    let dst = std::env::temp_dir().join(format!("pact-clauses-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    let skill = dst.join("skills/refund-policy/SKILL.md");
    let text = std::fs::read_to_string(&skill).unwrap();
    std::fs::write(&skill, text.replace("## Rules", "## Working guidance")).unwrap();

    let (code, said) = run(&["check", &dst.to_string_lossy()]);
    assert_eq!(code, Some(0), "{said}");
    assert!(
        !said.contains("## Rules"),
        "the heading is gone, so the clauses under it are not clauses:\n{said}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}

/// The two readings of one body agree about how many rules it holds.
///
/// `learning.classify` protects these lines and this prints them. A second copy
/// of a rule is what this project refuses everywhere else, so the two are held
/// against one another on the shipped policy: the number printed here is the
/// number of clauses that side will not let change without a person.
#[test]
fn both_readings_of_the_shipped_policy_agree() {
    let body = std::fs::read_to_string(format!(
        "{}/../../examples/refund-desk/skills/refund-policy/SKILL.md",
        env!("CARGO_MANIFEST_DIR")
    ))
    .expect("the shipped policy");
    // Counted the way the other side counts: a numbered or bulleted line under a
    // heading in the closed set, fences taken out first.
    let mut inside = false;
    let mut fenced = false;
    let mut clauses = 0usize;
    for line in body.lines() {
        let t = line.trim_start();
        if t.starts_with("```") || t.starts_with("~~~") {
            fenced = !fenced;
            continue;
        }
        if fenced {
            continue;
        }
        if t.starts_with('#') {
            let h = t.trim_start_matches('#').trim().to_ascii_lowercase();
            inside = h == "policy" || h == "rules" || h.ends_with(" policy");
            continue;
        }
        if inside
            && (t.starts_with("- ")
                || t.starts_with("* ")
                || t.chars().next().is_some_and(|c| c.is_ascii_digit()) && t.contains(". "))
        {
            clauses += 1;
        }
    }
    assert_eq!(clauses, 5, "the shipped policy holds five rules");

    let (_, said) = run(&["check", &example()]);
    assert!(
        said.contains(&format!("{clauses} written rule")),
        "the printed count must be the number the other side protects ({clauses}):\n{said}"
    );
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
