//! A setting the workspace writes as its own file must not also be a kind stem.
//!
//! `redaction:` used to be two settings — `redactions:` held several groups of
//! rules and `redaction:` was one piece of text naming one of them, so the
//! second group was unbindable and the advice offered for it switched the first
//! one off (R61). Collapsing them left ONE `redaction:` setting of the
//! workspace, written as `redaction.yaml` beside `workspace.yaml` — the shape
//! `learning:` already has.
//!
//! That shape has a sharp edge, and `policy.rs` states it in a comment:
//!
//! > `learning.yaml` at the workspace root is the workspace's `learning:`
//! > field, and listing it here made every workspace report two self files.
//!
//! A comment is not a guard. Within one hour of the collapse landing, a
//! neighbouring change added `redaction` to [`Policy::kind_stems`] and the
//! shipped worked example stopped loading at all:
//!
//! ```text
//! error: This folder has two files describing itself: 'workspace.yaml' and 'redaction.yaml'.
//!   --> examples/refund-desk/redaction.yaml:1:1
//!   fix: Keep only one of them.
//!   rule: loader/two-self-files
//! ```
//!
//! — a refusal whose only typeable fix deletes either the workspace or the file
//! saying what may never leave it. It was reverted, and the same loss had
//! already happened once before with `learning`. Twice is a pattern, so this
//! file makes the rule executable.
//!
//! # Why it is derived rather than listed
//!
//! `the_folder_form_of_the_four_kinds_that_refused_it.rs` already pins the two
//! facts about `redaction` itself — that the flat spelling stays the workspace's
//! own setting, and that the folder spelling needs no stem. This file is
//! deliberately not a third copy of those. It asks the question one level up and
//! reads the answer out of `spec/schema.yaml`: **the schema is data, so the
//! guard reads the data.** `learning:`, `evals:` and `models:` are the same
//! shape and were covered by nothing, and any setting added in that shape later
//! is covered the day it is written.

use camino::{Utf8Path, Utf8PathBuf};
use pact_diag::Diagnostics;
use pact_loader::Loader;
use pact_loader::policy::Policy;

fn repo() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// Every setting of the `workspace` group that is a whole group rather than a
/// list of them — `redaction:`, `learning:`, `evals:`, `models:`. Those are
/// exactly the settings the Expansion Rule lets an author write as one file
/// named after the setting, sitting beside `workspace.yaml`.
///
/// `map of group:x` settings are deliberately excluded: `agents:` becomes a
/// FOLDER called `agents/` holding one file per agent, so the name that lands at
/// the workspace root is the plural container and never collides with a stem.
fn settings_a_workspace_writes_as_its_own_file() -> Vec<String> {
    let path = repo().join("spec/schema.yaml");
    let text = std::fs::read_to_string(&path).expect("spec/schema.yaml");
    let doc = pact_doc::parse_yaml(&text, Utf8Path::new("spec/schema.yaml"))
        .expect("the specification parses");
    let fields = doc
        .get("groups")
        .and_then(|g| g.get("workspace"))
        .and_then(|w| w.get("fields"))
        .and_then(pact_doc::Node::as_map)
        .expect("the schema has a `workspace` group with fields");

    let found: Vec<String> = fields
        .iter()
        .filter(|(_, entry)| {
            entry
                .node
                .get("type")
                .and_then(pact_doc::Node::as_str)
                .is_some_and(|t| t.starts_with("group:"))
        })
        .map(|(name, _)| name.clone())
        .collect();

    // A filter that silently matches nothing is how a guard like this dies: it
    // stays green for years while guarding an empty set. `redaction:` is the
    // setting this file exists for, so its absence means the schema moved and
    // the filter above did not follow it.
    assert!(
        found.iter().any(|f| f == "redaction"),
        "the filter found no `redaction:` setting on the workspace — it reads \
         `type: group:...`, so if the schema now spells it another way this test \
         is guarding nothing. Settings it did find: {found:?}"
    );
    found
}

#[test]
fn no_setting_a_workspace_writes_as_its_own_file_is_also_a_kind_stem() {
    let stems = Policy::default().kind_stems;
    for setting in settings_a_workspace_writes_as_its_own_file() {
        assert!(
            !stems.iter().any(|s| s.eq_ignore_ascii_case(&setting)),
            "`{setting}` is a setting of the workspace AND a kind stem in \
             `crates/pact-loader/src/policy.rs`. A workspace that writes it as \
             `{setting}.yaml` beside `workspace.yaml` — which is the spelling the \
             schema's own help gives — then has two files describing itself, and \
             the only fix `pact check` can offer is to delete one of them. Take \
             \"{setting}\" back out of `kind_stems`: the folder spelling needs \
             nothing from that list, because `{setting}/{setting}.yaml` is already \
             a self file by the directory-name rule."
        );
    }
}

#[test]
fn adding_one_of_those_names_to_the_kind_stems_stops_the_worked_example_loading() {
    // The measurement behind the rule, kept executable so the cost is a fact
    // rather than a claim in a comment. It is also what stops the test above
    // from being a matter of taste: if some later change lets a root file and a
    // kind stem coexist, this fails, and the guard can then be deleted honestly
    // — which is an answer a comment can never give.
    let root = repo().join("examples/refund-desk");

    let mut clean = Diagnostics::new();
    Loader::new(root.clone()).load(&root, &mut clean).expect("the worked example loads");
    assert!(
        !clean.items().iter().any(|d| d.rule == "loader/two-self-files"),
        "as shipped, the worked example has one self file:\n{}",
        clean.render()
    );

    let mut policy = Policy::default();
    policy.kind_stems.push("redaction".to_string());
    let mut broken = Diagnostics::new();
    Loader::with_policy(root.clone(), policy).load(&root, &mut broken);
    let two = broken
        .items()
        .iter()
        .find(|d| d.rule == "loader/two-self-files")
        .unwrap_or_else(|| {
            panic!(
                "adding `redaction` to the stems must break the example, or the rule \
                 above is guarding a danger that no longer exists:\n{}",
                broken.render()
            )
        });
    assert!(
        two.message.contains("redaction.yaml") && two.message.contains("workspace.yaml"),
        "and it breaks it by mistaking the setting for a second workspace: {}",
        two.message
    );
}
