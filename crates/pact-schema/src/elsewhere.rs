//! A name that is not where this line looks, but *is* somewhere in the tree.
//!
//! `names:` answers one question — "is this a key of that map?" — and when the
//! answer is no it used to say the same thing however wrong the line was: *there
//! is no such entry, add a file `<dir>/<name>.yaml`*. That sentence is right for
//! a name nobody has written yet. For a name the workspace ALREADY HAS, under a
//! different kind, it is worse than unhelpful: it tells the author to make a
//! second copy of a document they are looking at, under the wrong kind, and the
//! copy will then be the one nothing reads.
//!
//! The case that forced it is the one the worked example exists to demonstrate.
//! `agent.uses:` draws from `names: [tools, skills]`; `stage.may-use:` draws from
//! `names: [tools, agents]`. So a stage narrowing to the written refund policy —
//! a skill the agent already lists on its own `uses:` line — was told:
//!
//! ```text
//! error: 'may-use' names 'refund-policy', and there is no such entry in `tools:` or `agents:`.
//!   fix: Change it to one of: … — or add a file `tools/refund-policy.yaml`.
//! ```
//!
//! `skills/refund-policy/SKILL.md` was open in the next tab.
//!
//! Everything here is read out of the specification rather than written down in
//! Rust (invariant F-1). Which sections a name can be looked up in, and which
//! LINE names one, are both derived from the `names:` and `key-names:` the
//! schema itself carries — so widening `stage.may-use` to `[tools, skills,
//! agents]` is still a YAML edit, and this file quietly stops mentioning `uses:`
//! for stages the moment it does.
//!
//! **Scope, deliberately narrow.** Only the workspace's own top-level sections
//! are searched. The `pact:` namespaces the distribution supplies (the model
//! catalogue) are not: "this workspace has that under…" would be untrue of a
//! list no workspace wrote, and a sentence that is nearly right about where
//! something lives is the failure this module exists to end.

use std::collections::{BTreeMap, BTreeSet};

use indexmap::IndexMap;
use pact_doc::Node;

use crate::{Group, Ty};

/// Where a name really lives, and which line is allowed to name one.
///
/// Both are lists because both can honestly have more than one answer: a name
/// may be a tool *and* an agent, and a section may be nameable from several
/// fields (`tools:` is reachable from `uses:` and from `may-use:`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Elsewhere {
    /// The top-level sections of this workspace that do have the name.
    pub sections: Vec<String>,
    /// The fields whose `names:`/`key-names:` cover those sections — the lines
    /// an author may legitimately write the name on.
    pub named_on: Vec<String>,
}

/// The name, looked for everywhere this workspace could be keeping it.
///
/// `already` is the set of sections the failing field itself consulted, so a
/// section is never reported as a surprising home for a name that was just
/// looked for there. `field` is the line being checked, excluded from
/// `named_on` for the same reason: "write it on `may-use:` instead" is not
/// advice when `may-use:` is the line that refused it.
///
/// **Where it looks and where it looks it up are two different questions**, and
/// running them off one list was this module's own first bug. *Where the name
/// lives* is a fact about the tree: `skills/refund-policy/SKILL.md` is there
/// whether or not any field in the specification can point at a skill. *Which
/// line may name one* is a fact about the specification, and it can honestly be
/// "none". Deriving the search from the second made a workspace's own document
/// invisible the moment nothing referred to its kind, and the author was handed
/// back the "add a file" that started all this — caught by
/// `the_line_that_may_name_a_kind_is_read_from_the_specification_and_not_from_the_checker`.
pub fn find(
    groups: &IndexMap<String, Group>,
    root: &Node,
    root_group: &str,
    value: &str,
    already: &[&str],
    field: &str,
) -> Option<Elsewhere> {
    let map = root.as_map()?;
    let referable = referable(groups);

    let mut sections: Vec<String> = Vec::new();
    let mut named_on: BTreeSet<String> = BTreeSet::new();
    for section in kinds(groups, root_group) {
        if already.contains(&section) {
            continue;
        }
        let holds = map
            .get(section)
            .and_then(|e| e.node.as_map())
            .is_some_and(|m| m.contains_key(value));
        if !holds {
            continue;
        }
        sections.push(section.to_string());
        if let Some(fields) = referable.get(section) {
            named_on.extend(fields.iter().filter(|f| *f != field).cloned());
        }
    }

    if sections.is_empty() {
        return None;
    }
    Some(Elsewhere { sections, named_on: named_on.into_iter().collect() })
}

/// The sections of this document that hold named ENTRIES rather than settings.
///
/// `agents:`, `tools:`, `skills:` and the rest are maps whose keys the author
/// chose and whose values are documents; `evals:` and `learning:` are maps whose
/// keys are settings this specification named. Only the first kind can hold a
/// name somebody meant to write, and telling an author their loop is "under
/// `evals:`" because a metric happens to be spelled the same would be the same
/// species of wrong sentence this module exists to remove.
///
/// Read off the type, so a section added to `spec/schema.yaml` is searched
/// without anybody remembering to add it here.
fn kinds<'a>(groups: &'a IndexMap<String, Group>, root_group: &str) -> Vec<&'a str> {
    let Some(g) = groups.get(root_group) else { return Vec::new() };
    g.fields
        .iter()
        .filter(|f| matches!(&f.ty, Ty::MapOf(inner) if matches!(**inner, Ty::Group(_) | Ty::Anything)))
        .map(|f| f.name.as_str())
        .collect()
}

/// Every section some field can name an entry of, and the fields that can name
/// one.
///
/// Built from the schema on the failure path only. A `^` prefix is dropped
/// because it says where to *look* for the map, not what the map is called, and
/// a `pact:` prefix is skipped because those are not sections of a workspace at
/// all — see the module note.
fn referable(groups: &IndexMap<String, Group>) -> BTreeMap<String, Vec<String>> {
    let mut out: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for g in groups.values() {
        for f in &g.fields {
            for want in f.names.iter().chain(f.key_names.iter()) {
                if want.starts_with("pact:") {
                    continue;
                }
                let section = want.trim_start_matches('^').to_string();
                let fields = out.entry(section).or_default();
                if !fields.contains(&f.name) {
                    fields.push(f.name.clone());
                }
            }
        }
    }
    out
}

impl Elsewhere {
    /// The half of the sentence that says what is actually wrong.
    ///
    /// It states the true fact first — the workspace HAS this, here — because
    /// that is the thing the author can check with their own eyes, and only then
    /// the rule that makes the line wrong anyway.
    pub fn because(&self, field: &str, places: &str) -> String {
        format!(
            "and this workspace has that under {} — '{field}' can only name what is in {places}.",
            phrase(&self.sections)
        )
    }

    /// What to type. Three parts, in the order a reader needs them: the names
    /// that would work here, the line that would accept the one they wrote, and
    /// — only when the old advice would have been "make a file" — the explicit
    /// refusal of it.
    ///
    /// The refusal is spelled out rather than merely omitted. An author who has
    /// just been told the name is a skill will otherwise reach for the fix they
    /// were given last time, and a duplicated document is silent damage: both
    /// copies load, one of them is never read again, and nothing says which.
    pub fn fix(&self, choices: &str, add_a_file: Option<&str>) -> String {
        // An empty set of choices is not a choice. `Change it to one of: ` with
        // nothing after it instructs the reader to type nothing.
        let mut out = if choices.is_empty() {
            "Nothing else is declared there yet".to_string()
        } else {
            format!("Change it to one of: {choices}")
        };
        if !self.named_on.is_empty() {
            out.push_str(&format!(
                " — or, if you meant the {} entry, {} is the line that names one",
                phrase(&self.sections),
                phrase(&self.named_on),
            ));
        }
        out.push('.');
        if let Some(add) = add_a_file {
            out.push_str(&format!(
                " Do not {add}: that would be a second copy of a document this workspace \
                 already has, and only one of the two would be the one anybody edits."
            ));
        }
        out
    }
}

/// `["skills"]` → ``skills:``; `["uses", "may-use"]` → ``uses:` or `may-use:``.
fn phrase(items: &[String]) -> String {
    items.iter().map(|s| format!("`{s}:`")).collect::<Vec<_>>().join(" or ")
}
