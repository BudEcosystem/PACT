//! One digest for the kinds this round added — `loop`, `port`,
//! `context-policy` — however they were written down.
//!
//! There is already a digest-equality test, in
//! `example_refund_desk.rs::the_flat_and_expanded_forms_have_the_same_digest`,
//! and this is deliberately not an extension of it. That one moves a FIELD
//! between a file and the document above it: `instructions:` against
//! `instructions.md`, `needs:` against `needs.yaml`. What it proves is that a
//! prose field and its file are one artifact.
//!
//! This proves the claim one level up: that a whole KIND of document gains
//! nothing from where it was written. A `careful:` entry under `loops:` in
//! `workspace.yaml`, a file `loops/careful.yaml`, and a folder
//! `loops/careful/` with `loop.yaml` inside it are three spellings of one
//! setting, and they hash the same. That is what makes a `loops/` folder a
//! CONVENIENCE rather than a second dialect — if the forms could differ, an
//! author would have to know which one their lockfile, their cache and their
//! signature actually meant, and the folder would be a fork of the format
//! wearing a directory name.
//!
//! Worth holding separately because the failure mode is different too. A prose
//! field breaks by whitespace. A new kind breaks by never arriving: nothing in
//! the loader knows the words `ports`, `loops` or `context-policies`, so a kind
//! that fell out of the document entirely would still make every form agree —
//! two empty documents hash alike. Hence
//! [`assert_the_new_kinds_really_arrived`], and hence the third test.

use camino::{Utf8Path, Utf8PathBuf};
use pact_diag::Diagnostics;
use pact_doc::Node;
use pact_loader::Loader;

// ── The settings, written once ───────────────────────────────────────────────
//
// Each kind's body is a single constant, so the flat form and the folder forms
// are provably the SAME WORDS in a different place. Writing them out twice by
// hand would let a stray typo fail this test for a reason that has nothing to
// do with the Expansion Rule, which is the one thing it is here to check.

/// The workspace's own settings. These never move, so a difference in the
/// digest can only have come from the three kinds below.
const ROOT: &str = "\
name: refund-desk
description: The refund decision system for the customer support team.
";

/// A port has to answer *some* agent, and a root with no `agents:` is read as
/// an agent rather than a workspace — so the smallest honest tree has one.
const AGENT: &str = "\
name: Refund Desk
description: Decides refunds for the customer support team.
instructions: Read the ticket, check the policy, then answer.
";

const PORT_SLACK: &str = "\
description: Where customers reach us, in Slack.
kind: conversation
through: slack
answers: refund-desk
same-conversation-when:
  - they are in the same thread
who-can-reach-it:
  - people in our Slack workspace
";

const PORT_EMAIL: &str = "\
description: Refund requests that arrive by email.
kind: inbound-call
through: helpdesk
answers: refund-desk
same-conversation-when:
  - they are replies to the same email
";

/// A folded scalar on purpose: prose is where re-indenting a block of YAML into
/// a nested map would go wrong if it were going to, and every real loop file in
/// the repo is written this way.
const LOOP_HEAD: &str = "\
description: >
  Look things up, then read the decision back against the written refund
  policy before the customer sees it.
starts-at: gather
";

const STAGE_GATHER: &str = "\
does: use-tools
then:
  used-a-tool: gather
  answered: re-read
";

const STAGE_RE_READ: &str = "\
does: check-its-work
says: Say which rule allows this decision, or which rule it breaks.
at-most: 2
then:
  used-a-tool: re-read
  answered: reply
";

const STAGE_REPLY: &str = "\
does: answer
then:
  answered: done
";

const STAGES: [(&str, &str); 3] = [
    ("gather", STAGE_GATHER),
    ("re-read", STAGE_RE_READ),
    ("reply", STAGE_REPLY),
];

const CONTEXT_POLICY: &str = "\
description: Keeps a long back-and-forth inside what the model can hold.
when-full: 85%
always-keep:
  - the refund policy
  - anything a person approved or declined
then:
  - what: shorten-long-results
    applies-to: anything a tool returned earlier
    down-to: 2000 characters
  - what: summarise-older
    applies-to: everything before the last few messages
summarised-by: models/summariser
if-it-still-does-not-fit: stop
";

// ── Building the three forms ─────────────────────────────────────────────────

/// Shift a block of settings sideways. Relative indentation is all YAML reads,
/// so the same text is the same document at any depth — which is the whole
/// reason a file's contents can become a map entry unchanged.
fn indent(body: &str, spaces: usize) -> String {
    let pad = " ".repeat(spaces);
    let mut out = String::new();
    for line in body.lines() {
        if !line.trim().is_empty() {
            out.push_str(&pad);
            out.push_str(line);
        }
        out.push('\n');
    }
    out
}

/// `[(name, body)]` → the `name:` / body map an author would type.
fn entries(of: &[(&str, &str)]) -> String {
    of.iter()
        .map(|(name, body)| format!("{name}:\n{}", indent(body, 2)))
        .collect()
}

/// The loop's stages folded back into one document, for the two forms that do
/// not give each stage its own file.
fn loop_careful() -> String {
    format!("{LOOP_HEAD}steps:\n{}", indent(&entries(&STAGES), 2))
}

/// **Flat.** Everything in `workspace.yaml`, which is what somebody writes
/// before they have heard of any of this.
fn build_flat(root: &Utf8Path) {
    let ports = entries(&[("slack", PORT_SLACK), ("email", PORT_EMAIL)]);
    let loops = entries(&[("careful", loop_careful().as_str())]);
    let policies = entries(&[("long-threads", CONTEXT_POLICY)]);
    put(
        &root.join("workspace.yaml"),
        &format!(
            "{ROOT}ports:\n{}loops:\n{}context-policies:\n{}",
            indent(&ports, 2),
            indent(&loops, 2),
            indent(&policies, 2)
        ),
    );
    put(&root.join("agents/refund-desk/agent.yaml"), AGENT);
}

/// **A folder per kind.** One file per entry — the form the worked example
/// uses, and the one the plan's Phase 5 shipped.
fn build_folders(root: &Utf8Path) {
    put(&root.join("workspace.yaml"), ROOT);
    put(&root.join("agents/refund-desk/agent.yaml"), AGENT);
    put(&root.join("ports/slack.yaml"), PORT_SLACK);
    put(&root.join("ports/email.yaml"), PORT_EMAIL);
    put(&root.join("loops/careful.yaml"), &loop_careful());
    put(
        &root.join("context-policies/long-threads.yaml"),
        CONTEXT_POLICY,
    );
}

/// **A folder per entry, too.** `ports/slack/port.yaml` and
/// `loops/careful/loop.yaml` are self files: named after WHAT THE THING IS, so
/// they describe the folder rather than becoming a field called `port` inside
/// it. That is the only reason `port`, `loop` and `context-policy` were added
/// to `kind_stems` this round, and this is the form that exercises it — plus
/// one more turn of the same crank, `steps/` as a folder of stages.
fn build_folders_of_folders(root: &Utf8Path) {
    put(&root.join("workspace.yaml"), ROOT);
    put(&root.join("agents/refund-desk/agent.yaml"), AGENT);
    put(&root.join("ports/slack/port.yaml"), PORT_SLACK);
    put(&root.join("ports/email/port.yaml"), PORT_EMAIL);
    put(&root.join("loops/careful/loop.yaml"), LOOP_HEAD);
    for (name, body) in STAGES {
        put(&root.join(format!("loops/careful/steps/{name}.yaml")), body);
    }
    put(
        &root.join("context-policies/long-threads/context-policy.yaml"),
        CONTEXT_POLICY,
    );
}

// ── Plumbing ─────────────────────────────────────────────────────────────────

fn put(path: &Utf8Path, body: &str) {
    std::fs::create_dir_all(path.parent().expect("a file has a parent")).unwrap();
    std::fs::write(path, body).unwrap();
}

/// A working directory of our own. Keyed on the process id the way the digest
/// test in `example_refund_desk.rs` is, and on the test's name as well: the
/// tests in one binary share a process, and cargo runs them at the same time.
fn workdir(name: &str) -> Utf8PathBuf {
    let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string()).join(format!(
        "pact-new-kind-digest-{}-{name}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&base);
    std::fs::create_dir_all(&base).unwrap();
    base
}

/// Load, and refuse to carry on if the tree did not load cleanly. A digest
/// taken from a tree that half-failed compares two accidents, not two forms.
fn load(root: &Utf8Path) -> Node {
    let mut d = Diagnostics::new();
    let n = Loader::new(root.to_owned())
        .load(root, &mut d)
        .expect("the tree loads");
    assert!(!d.has_errors(), "{}", d.render());
    assert_eq!(d.warning_count(), 0, "{}", d.render());
    n
}

/// One authored value from deep inside each of the three kinds.
///
/// Without this the equality below is worth nothing: if a folder were dropped
/// on the way in, every form would agree, because two documents that are both
/// missing the same thing hash alike. So the test says what it expects to find
/// before it says the forms agree.
fn assert_the_new_kinds_really_arrived(doc: &Node, form: &str) {
    let ports = doc.get("ports").and_then(Node::as_map).unwrap_or_else(|| {
        panic!("{form}: `ports` is not in the document at all, so nothing below means anything")
    });
    let mut names: Vec<&str> = ports.keys().map(String::as_str).collect();
    names.sort_unstable();
    assert_eq!(names, ["email", "slack"], "{form}: both ports");
    assert_eq!(
        ports
            .get("slack")
            .map(|e| &e.node)
            .and_then(|s| s.get("kind"))
            .and_then(Node::as_str),
        Some("conversation"),
        "{form}: a port's settings, not just its name"
    );

    let re_read = doc
        .get("loops")
        .and_then(|l| l.get("careful"))
        .and_then(|c| c.get("steps"))
        .and_then(|s| s.get("re-read"))
        .unwrap_or_else(|| panic!("{form}: the loop's `re-read` stage"));
    assert_eq!(
        re_read.get("does").and_then(Node::as_str),
        Some("check-its-work"),
        "{form}"
    );
    // The same `2`, reached through four map keys in one form and through three
    // directories in another. A number that survives both journeys unchanged is
    // a digest taken over the settings rather than over the shape of the tree.
    assert_eq!(
        re_read
            .get("at-most")
            .map(pact_doc::canonical_string)
            .as_deref(),
        Some("2"),
        "{form}: the stage's own ceiling"
    );

    assert_eq!(
        doc.get("context-policies")
            .and_then(|c| c.get("long-threads"))
            .and_then(|p| p.get("when-full"))
            .and_then(Node::as_str),
        Some("85%"),
        "{form}: the context policy's trigger"
    );
}

// ── The guarantees ───────────────────────────────────────────────────────────

#[test]
fn a_loop_a_port_and_a_context_policy_are_one_artifact_whether_written_flat_or_as_folders() {
    // The property the existing digest test holds for a prose field, held here
    // for three whole KINDS of document. `example_refund_desk.rs` proves that
    // `instructions:` and `instructions.md` are one artifact — a field and its
    // file. This proves that a `loops:` map and a `loops/` folder are one
    // artifact, which is the claim that lets the folder be a convenience
    // instead of a second dialect an author has to choose between.
    //
    // If this fails, the Expansion Rule has stopped being an equivalence for
    // the kinds added this round, and the `loops/` folder in the worked example
    // is a different document from the same settings typed inline.
    let base = workdir("flat-vs-folders");
    let (flat, folders) = (base.join("flat"), base.join("folders"));
    build_flat(&flat);
    build_folders(&folders);

    let (a, b) = (load(&flat), load(&folders));
    assert_the_new_kinds_really_arrived(&a, "flat");
    assert_the_new_kinds_really_arrived(&b, "folders");

    assert_eq!(
        pact_doc::digest(&a),
        pact_doc::digest(&b),
        "a kind and its folder must be the same artifact, or a lockfile means \
         two different things depending on how the author felt that day"
    );
    // Left behind on failure, on purpose: the two trees are the evidence.
    let _ = std::fs::remove_dir_all(&base);
}

#[test]
fn an_entry_given_a_folder_of_its_own_is_still_that_same_artifact() {
    // The third spelling, and the one that needs `kind_stems`:
    // `ports/slack/port.yaml`, `loops/careful/loop.yaml`,
    // `context-policies/long-threads/context-policy.yaml`, and the loop's
    // stages one per file under `steps/`.
    //
    // Stated separately from the test above because it is a separate promise.
    // The first says a folder of files equals a map. This says an author who
    // keeps going — because a port grew a `remembers:` worth its own file —
    // never crosses a line where the document changes identity. There is no
    // depth at which expanding stops being free.
    let base = workdir("folders-of-folders");
    let (flat, deep) = (base.join("flat"), base.join("deep"));
    build_flat(&flat);
    build_folders_of_folders(&deep);

    let (a, b) = (load(&flat), load(&deep));
    assert_the_new_kinds_really_arrived(&a, "flat");
    assert_the_new_kinds_really_arrived(&b, "folders of folders");

    assert_eq!(
        pact_doc::digest(&a),
        pact_doc::digest(&b),
        "expanding one more level must stay free, or `kind_stems` has lost \
         `port`, `loop` or `context-policy`"
    );
    let _ = std::fs::remove_dir_all(&base);
}

#[test]
fn changing_one_setting_inside_a_folder_still_moves_the_digest() {
    // What stops the two tests above from being satisfied by a loader that
    // ignores these folders wholesale. Equality is only worth having if the
    // contents were ever in there: change `at-most: 2` to `at-most: 3` in a
    // stage that lives four directories down, and the workspace must hash
    // differently, because it is now a workspace that checks its own work one
    // more time.
    let base = workdir("sensitivity");
    let (before, after) = (base.join("before"), base.join("after"));
    build_folders_of_folders(&before);
    build_folders_of_folders(&after);
    put(
        &after.join("loops/careful/steps/re-read.yaml"),
        &STAGE_RE_READ.replace("at-most: 2", "at-most: 3"),
    );

    assert_ne!(
        pact_doc::digest(&load(&before)),
        pact_doc::digest(&load(&after)),
        "a setting written in a folder must reach the digest, or the two \
         equalities above are the equality of two documents that lost it"
    );
    let _ = std::fs::remove_dir_all(&base);
}
