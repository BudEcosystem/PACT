//! **One field for one idea, and something that reads it.**
//!
//! The workspace used to carry two settings for what must never leave it:
//! `redactions:` was a map that could hold several sets of rules, and
//! `redaction:` was a piece of text naming exactly one of them. Two fields for
//! one idea is bad enough on its own; this pair could not be made to work at
//! all.
//!
//! * A second file in `redactions/` was **unbindable by construction** — one
//!   name, one binding — and the warning written for exactly that case
//!   (`unnamed.rs`) told the author *"Add a line: `redaction: staff-data` in
//!   workspace.yaml"*. Typing it REPLACES the name already there, so following
//!   the advice switched the first set of rules off in silence.
//! * The obvious repair was refused too. Measured on the shipped example,
//!   `redaction: [customer-data, staff-data]` printed *"'redaction' should be
//!   some text, but it is a list"* — a true sentence about a shape the format
//!   should never have offered.
//!
//! It is now ONE field of the workspace, `type: group:redaction`, written as
//! `redaction.yaml` beside `workspace.yaml`. That is the shape `learning:`
//! already has: the file IS the setting, so there is nothing to bind, nothing to
//! misspell, and no second file to leave dangling.
//!
//! # And the half that matters more
//!
//! A collapsed field that nothing reads is still a field that nothing reads.
//! Before this round, `redaction.yaml` was checked sentence by sentence and then
//! consulted by no source file in either language — an author could write it,
//! delete it, or fill it with anything the vocabulary allows, and no outcome
//! anywhere changed. So the last two tests here drive the AUTHORED path: they
//! take the shipped example, change the two lines that let the improving cycle
//! run unattended against a model outside this box, and show that whether
//! `redaction.yaml` is on disk is what decides between *"loaded cleanly"* and a
//! refusal. That is AD-88 rule 4, which the architecture has stated for a round
//! and nothing implemented.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../examples/refund-desk"
    ))
}

/// A throwaway copy of the worked example, so every test here starts from the
/// tree an author is actually shown rather than from a fixture built inline.
struct Copy(PathBuf);

impl Copy {
    fn of_the_worked_example(name: &str) -> Self {
        let dst =
            std::env::temp_dir().join(format!("pact-redaction-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dst);
        copy_tree(&example(), &dst);
        Self(dst)
    }

    /// Replace one string in one file, refusing to pass quietly if the fixture
    /// has drifted — a test that edits nothing proves nothing.
    fn edit(&self, file: &str, from: &str, to: &str) -> &Self {
        let p = self.0.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} is not in {file}"
        );
        std::fs::write(&p, text.replace(from, to)).unwrap();
        self
    }

    fn write(&self, file: &str, text: &str) -> &Self {
        let p = self.0.join(file);
        if let Some(dir) = p.parent() {
            std::fs::create_dir_all(dir).unwrap();
        }
        std::fs::write(&p, text).unwrap();
        self
    }

    fn remove(&self, file: &str) -> &Self {
        let p = self.0.join(file);
        assert!(
            p.exists(),
            "fixture drifted: {file} is not in the worked example"
        );
        std::fs::remove_file(&p).unwrap();
        self
    }

    /// What `pact check` prints, and whether it accepted the tree.
    fn checked(&self) -> (bool, String) {
        let out = pact()
            .args(["check", self.0.to_str().unwrap()])
            .output()
            .expect("runs");
        let mut text = String::from_utf8_lossy(&out.stdout).into_owned();
        text.push_str(&String::from_utf8_lossy(&out.stderr));
        (out.status.success(), text)
    }
}

impl Drop for Copy {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn copy_tree(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_tree(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}

#[test]
fn the_worked_example_says_what_must_never_leave_in_one_file_that_nothing_points_at() {
    // The shape claim, checked against the tree rather than against the schema:
    // `redaction.yaml` sits at the top of the workspace, `workspace.yaml` carries
    // no line naming it, and the tree loads. If a binding line ever comes back,
    // this fails.
    let root = example();
    assert!(
        root.join("redaction.yaml").is_file(),
        "redaction.yaml is the spelling"
    );
    assert!(
        !root.join("redactions").exists(),
        "the `redactions/` folder is gone with the field"
    );

    let workspace = std::fs::read_to_string(root.join("workspace.yaml")).unwrap();
    let binding: Vec<&str> = workspace
        .lines()
        .filter(|l| !l.trim_start().starts_with('#') && l.contains("redaction"))
        .collect();
    assert!(
        binding.is_empty(),
        "workspace.yaml still names the redaction on a setting line: {binding:?} — the file is \
         the setting, the way `learning.yaml` is"
    );

    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stdout)
    );
}

#[test]
fn the_rules_in_that_file_reach_the_document_a_runtime_reads() {
    // `pact show` is the door every adapter reads through (R54). A collapsed
    // field that loads and does not appear there would be the same defect one
    // hop along.
    let out = pact()
        .args(["show", example().to_str().unwrap()])
        .output()
        .unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    let doc: serde_json::Value =
        serde_json::from_str(&text).expect("`pact show` prints a document");
    let hide = doc
        .get("redaction")
        .and_then(|r| r.get("hide"))
        .and_then(|h| h.as_array())
        .expect("the document carries `redaction.hide`");
    assert!(
        hide.iter()
            .any(|s| s.as_str() == Some("anything that looks like a card number")),
        "the sentences the author wrote must be the ones the document carries: {hide:?}"
    );
}

#[test]
fn the_old_two_field_spelling_is_refused_and_the_message_names_the_field_that_survived() {
    // What an author with last round's tree types. `redaction:` is a block now,
    // so the name it used to hold is the wrong shape, and `redactions:` is not a
    // setting a workspace has at all. Both have to be said out loud with a fix
    // that can be typed — silently ignoring either would leave a workspace whose
    // rules are on disk and out of the document.
    let c = Copy::of_the_worked_example("old-spelling");
    c.write(
        "redactions/customer-data.yaml",
        "hide:\n  - anything that looks like a card number\n",
    )
    .remove("redaction.yaml")
    .edit(
        "workspace.yaml",
        "# fact about the system rather than about one agent.",
        "# fact about the system rather than about one agent.\nredaction: customer-data",
    );

    let (ok, said) = c.checked();
    assert!(!ok, "the two-field spelling must be refused:\n{said}");
    assert!(
        said.contains("'redactions' is not something a workspace can have"),
        "say that the map is gone:\n{said}"
    );
    assert!(
        said.contains("Did you mean 'redaction'?"),
        "name the field that survived:\n{said}"
    );
    assert!(
        said.contains("set of redaction settings") && said.contains("hide:"),
        "say what shape the surviving field wants, and name a line to type:\n{said}"
    );
}

#[test]
fn a_second_set_of_rules_can_no_longer_be_written_where_nothing_can_bind_it() {
    // The defect itself. Two files in `redactions/` used to load, one of them
    // bound and one of them not, and the advice for the unbound one was a line
    // that switched the bound one off. There is now no shape in which a second
    // set can be written at all: the folder is not a setting, and a `redaction:`
    // holding two named blocks is refused by name.
    //
    // Written whole rather than edited line by line: the sentences inside
    // `redaction.yaml` are a vocabulary that other work moves, and a fixture
    // pinned to their exact wording fails for a reason that has nothing to do
    // with what this test is about.
    let c = Copy::of_the_worked_example("second-set");
    c.write(
        "redaction.yaml",
        "customer-data:\n  hide:\n    - anything that looks like a card number\n\
         staff-data:\n  hide:\n    - anything that looks like an email address\n",
    );

    let (ok, said) = c.checked();
    assert!(
        !ok,
        "a second named set must be refused, not half-read:\n{said}"
    );
    assert!(
        said.contains("customer-data") || said.contains("staff-data"),
        "name the block that cannot be there:\n{said}"
    );
    assert!(
        said.contains("  fix: "),
        "a refusal without a fix is not one:\n{said}"
    );
}

#[test]
fn a_redaction_file_that_holds_nothing_back_is_refused_rather_than_counted_as_one() {
    // `hide:` is required for one reason: the next test treats the presence of
    // this file as the answer to "does this workspace say what must never
    // leave?". A file carrying only a `description:` would answer yes and hold
    // nothing back, which is the loads-and-does-nothing failure arriving through
    // the field meant to close it.
    let c = Copy::of_the_worked_example("empty-redaction");
    c.write("redaction.yaml", "description: Something, eventually.\n");

    let (ok, said) = c.checked();
    assert!(
        !ok,
        "a redaction that hides nothing must be refused:\n{said}"
    );
    assert!(
        said.contains("must have a 'hide'"),
        "name the missing line:\n{said}"
    );
}

#[test]
fn improving_this_system_off_this_machine_is_refused_when_no_file_says_what_to_hold_back() {
    // THE AUTHORED PATH. Nothing is constructed here: the tree is the shipped
    // example, the only edits are the two lines an author would type to turn
    // unattended improvement on and let the improving model live somewhere else,
    // and the question the check asks is whether `redaction.yaml` is on disk.
    //
    // AD-88 rule 4. §8.8 requirement 3 makes a learning cycle carry per-case
    // failures "with the error text", and failures are the customer's own words,
    // so these three settings together are an export path created by a default.
    let c = Copy::of_the_worked_example("improving-unheld");
    c.edit(
        "learning.yaml",
        "enabled: propose-only",
        "enabled: applies-safe-changes-itself",
    )
    .edit(
        "workspace.yaml",
        "allow-egress: []",
        "allow-egress: [reflector]",
    )
    .remove("redaction.yaml");

    let (ok, said) = c.checked();
    assert!(
        !ok,
        "the customer's words must not leave with nothing held back:\n{said}"
    );
    assert!(
        said.contains("loader/improving-with-nothing-held-back"),
        "the refusal must be this rule and not an accident of some other check:\n{said}"
    );
    assert!(
        said.contains("redaction.yaml"),
        "name the file to write:\n{said}"
    );
    assert!(
        said.contains("propose-only") && said.contains("allow-egress"),
        "offer the other two lines that also settle it — an author who wants the improving \
         cycle must not be left with one way out:\n{said}"
    );
}

#[test]
fn putting_the_file_back_is_what_makes_that_same_tree_load() {
    // The other half, and the one that proves the author's file is READ rather
    // than merely present in the schema: the identical three settings, with
    // `redaction.yaml` left where the example ships it, load cleanly. Delete the
    // call to `improving_with_nothing_held_back` in `pact-cli/src/main.rs` and
    // the test above goes green while this one stays green — which is how the
    // pair says "this line, and nothing else, is what reads the field".
    let c = Copy::of_the_worked_example("improving-held");
    c.edit(
        "learning.yaml",
        "enabled: propose-only",
        "enabled: applies-safe-changes-itself",
    )
    .edit(
        "workspace.yaml",
        "allow-egress: []",
        "allow-egress: [reflector]",
    );

    let (ok, said) = c.checked();
    assert!(
        ok,
        "a workspace that says what must never leave must load:\n{said}"
    );
    assert!(
        !said.contains("improving-with-nothing-held-back"),
        "and must not be told otherwise:\n{said}"
    );
}
