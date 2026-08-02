//! The first file an author has to create.
//!
//! A folder with no self file is a folder whose own settings have nowhere to
//! live. Every message about a setting it is missing therefore has to say
//! *which file to create*, and the only component that can answer that is this
//! one — [`policy::Policy::is_self_file`] accepts three spellings, and picking
//! between them is a convention, not a rule.
//!
//! # What was measured
//!
//! The tree a brand-new author makes first: one `agents/hello/agent.yaml`
//! holding `description: says hello`, and nothing else. `pact check` opened
//! with
//!
//! ```text
//! error: A workspace must have a 'name'.
//!   --> /tmp/hello:1:1
//!   fix: Add a line: `name: ...` — what this whole system is called
//! ```
//!
//! The arrow names a directory and gives it a line and a column. The fix names
//! a line but no file, because the file does not exist yet — so the very first
//! sentence PACT ever says to a non-coder (D13) cannot be acted on without
//! guessing, which is failure mode D28.1 arriving in the first ten seconds.
//!
//! `loader/not-a-pact-folder` already says the right sentence, and says it well
//! — *"Create `<path>/workspace.yaml` with one line — `name: …`"* — but only
//! for a folder that has no `agents/` in it. Add `agents/`, which is the first
//! thing anybody does, and the folder stops being not-a-PACT-folder and starts
//! being a workspace with a setting missing, which is the message above.
//!
//! # The rule
//!
//! Named after the reader rather than after the loader: *what would you call
//! the file you are about to make?*

use crate::policy::Policy;
use camino::{Utf8Path, Utf8PathBuf};

/// The file an author should create so that `dir` has somewhere to keep its own
/// settings. `root` is the tree being loaded, which decides the first rule.
///
/// Three answers, in the order the conventions rank:
///
/// 1. **the root of the tree → `workspace.yaml`.** Not merely the friendliest
///    spelling — the only one that works. `pact discover` looks for exactly
///    `workspace.yaml` or `workspace.yml` and nothing else, so a root named
///    after its directory would load and then be invisible to every command
///    that finds workspaces.
/// 2. **a folder inside a container named after a kind → `<kind>.yaml`.**
///    `agents/hello/` gets `agent.yaml`, which `policy.rs` records as the
///    spelling "a non-technical author writes without being taught anything".
///    The container is plural in every tree PACT ships, so the trailing `s`
///    comes off before the name is held against the known kinds.
/// 3. **anything else → `<folder-name>.yaml`,** the rule that always holds:
///    `is_self_file` accepts a file named after its own directory regardless of
///    what kind it is, so this answer is never wrong, only less familiar.
///
/// Every answer is checked back through [`Policy::is_self_file`] before it is
/// returned, so this function cannot name a file that the loader would then
/// read as an ordinary field. That check is what keeps rule 2 honest when
/// `kind_stems` changes underneath it.
pub fn to_start(root: &Utf8Path, policy: &Policy, dir: &Utf8Path) -> Utf8PathBuf {
    let dir_name = dir.file_name().unwrap_or_default();

    let named_after_the_folder = || dir.join(format!("{dir_name}.yaml"));

    // Rule 1. Compared on the path as given, because that is the path the
    // author typed and the one every message about this tree already quotes.
    if dir == root {
        return dir.join("workspace.yaml");
    }

    // Rule 2.
    if let Some(container) = dir.parent().and_then(Utf8Path::file_name) {
        let kind = container.strip_suffix('s').unwrap_or(container);
        if policy.is_self_file(dir_name, kind) {
            return dir.join(format!("{kind}.yaml"));
        }
    }

    // Rule 3.
    named_after_the_folder()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(s: &str) -> &Utf8Path {
        Utf8Path::new(s)
    }

    #[test]
    fn the_top_of_a_tree_is_always_told_to_start_workspace_yaml() {
        // Rule 1, and the reason it outranks rule 3: `pact discover` reads this
        // one name. `my-agents/my-agents.yaml` would load and be undiscoverable.
        let policy = Policy::default();
        assert_eq!(
            to_start(p("/tmp/my-agents"), &policy, p("/tmp/my-agents")),
            p("/tmp/my-agents/workspace.yaml")
        );
    }

    #[test]
    fn a_folder_inside_agents_is_told_to_start_the_file_it_would_be_taught() {
        let policy = Policy::default();
        assert_eq!(
            to_start(p("/w"), &policy, p("/w/agents/hello")),
            p("/w/agents/hello/agent.yaml")
        );
        assert_eq!(
            to_start(p("/w"), &policy, p("/w/skills/refund-policy")),
            p("/w/skills/refund-policy/skill.yaml")
        );
        assert_eq!(
            to_start(p("/w"), &policy, p("/w/ports/slack")),
            p("/w/ports/slack/port.yaml")
        );
    }

    #[test]
    fn a_folder_whose_container_names_no_kind_is_told_to_use_its_own_name() {
        // Rule 3, reached here by the crude de-pluralisation in rule 2:
        // `policies` minus its `s` is `policie`, which names no kind, so the
        // answer falls through to the folder's own name. `policy` IS a kind stem
        // now — `policies/refunds/policy.yaml` loads — so both spellings work
        // and this only decides which one an author who has neither is told to
        // create. What matters is the assertion below: whichever answer comes
        // out, the loader must read it as the folder's own file.
        let policy = Policy::default();
        let named = to_start(p("/w"), &policy, p("/w/policies/refunds"));
        assert_eq!(named, p("/w/policies/refunds/refunds.yaml"));
        assert!(
            policy.is_self_file("refunds", "refunds"),
            "the file named must be one the loader would read as the folder's own"
        );
        assert!(
            !policy.is_self_file("refunds", "policie"),
            "and stripping the container's 's' must not have produced one that is not"
        );
    }

    #[test]
    fn a_folder_under_tools_or_resources_is_told_the_file_named_after_the_kind() {
        // Rule 2, on the two containers that gained it this round. Before
        // `tool` and `resource` were kind stems, an empty `tools/weather/` was
        // told to create `weather.yaml` — correct, but not the spelling anybody
        // arrives at from `agents/<n>/agent.yaml`, and the author who guessed
        // `tool.yaml` instead was told to remove a filename.
        let policy = Policy::default();
        assert_eq!(to_start(p("/w"), &policy, p("/w/tools/weather")), p("/w/tools/weather/tool.yaml"));
        assert_eq!(
            to_start(p("/w"), &policy, p("/w/resources/payments-server")),
            p("/w/resources/payments-server/resource.yaml")
        );
    }

    #[test]
    fn every_answer_is_a_file_the_loader_would_read_as_the_folders_own() {
        // The property behind all three rules. If this ever fails, the fix text
        // is sending an author to create a file that becomes a stray setting
        // named after itself — a worse outcome than the message it replaced.
        let policy = Policy::default();
        let root = p("/w");
        for dir in [
            "/w",
            "/w/agents/hello",
            "/w/skills/refund-policy",
            "/w/ports/slack",
            "/w/policies/refunds",
            "/w/questions/is-this-ok",
            "/w/loops/triage",
            "/w/anything-at-all",
        ] {
            let dir = p(dir);
            let file = to_start(root, &policy, dir);
            let stem = file.file_stem().expect("a file was named");
            assert_eq!(file.parent(), Some(dir), "{dir} must be told to create the file in itself");
            assert!(
                policy.is_self_file(dir.file_name().unwrap_or_default(), stem),
                "{dir} was told to create {file}, which the loader would read as a field"
            );
        }
    }
}
