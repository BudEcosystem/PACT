//! `key-names:` — the cross-reference check, reaching the KEYS of a map.
//!
//! `names:` has resolved a field's VALUE since R6, and every reference typo a
//! non-coder makes on one — `loop: carefull`, `asks: keep-goin`, `then:
//! {answered: repl}` — is caught where the author is. A field typed `map of ...`
//! has author-chosen keys, and those keys were held against nothing at all. Two
//! of them are references and nothing else:
//!
//!   * `agent.team` — whose own help says *"Give each one a folder under
//!     `agents/`"*. `team: {polcy-checker: ...}` loaded clean, and the misspelt
//!     member was then offered to the model as somebody it could ask.
//!   * `teamwork.shares` — the same names again, one line further down. A
//!     misspelt key gave the real member a slice of 0.0 while the typo held 60%
//!     of the pot.
//!
//! Both were measured on a copy of `examples/refund-desk` before this existed:
//! `pact check` said *"OK — loaded cleanly (468 settings)"* and exited 0.
//!
//! The schema here is a miniature of the real one — a workspace holding agents,
//! an agent holding a team, a teamwork block holding shares — so the resolution
//! walk under test is the walk the real document takes, root map and enclosing
//! block alike.

use camino::Utf8Path;
use pact_diag::Diagnostics;
use pact_doc::parse_yaml;
use pact_schema::from_doc::schema_from_yaml;

/// A workspace whose agents have teams, written the way the specification is.
const SPEC: &str = r#"
groups:
  workspace:
    fields:
      name:
        type: text
        help: what this whole system is called
      agents:
        type: map of group:agent
        help: the agents that make up this system
  agent:
    fields:
      description:
        type: text
        help: one line a colleague would understand
      team:
        type: map of text
        key-names: agents
        help: who helps with this work, and what each of them is for
      teamwork:
        type: group:teamwork
        help: how it waits for the team, and how what it may spend is shared out
  teamwork:
    fields:
      divides-the-budget:
        type: one-of
        choices: [evenly, by-share, as-needed]
        help: how the money gets shared out among the team
      shares:
        type: map of percent
        key-names: ^team
        help: with by-share, how much of the budget each member gets
"#;

fn check(doc: &str) -> Diagnostics {
    let mut spec_problems = Diagnostics::new();
    let schema = schema_from_yaml(SPEC, &mut spec_problems);
    assert!(!spec_problems.has_errors(), "{}", spec_problems.render());

    let node = parse_yaml(doc, Utf8Path::new("workspace.yaml")).expect("the document parses");
    let mut d = Diagnostics::new();
    d.add_source("workspace.yaml", doc);
    schema.validate(&node, "workspace", &mut d);
    d.sort();
    d
}

/// The worked example's shape: a desk, two helpers, a 60/40 split.
fn desk(team: &str, shares: &str) -> String {
    format!(
        "name: refund-desk\n\
         agents:\n\
         \x20 policy-checker:\n    description: Checks the written refund policy.\n\
         \x20 fraud-checker:\n    description: Looks for signs it is not genuine.\n\
         \x20 refund-desk:\n\
         \x20   description: Decides whether a refund is approved.\n\
         \x20   team:\n{team}\
         \x20   teamwork:\n      divides-the-budget: by-share\n      shares:\n{shares}"
    )
}

const REAL_TEAM: &str = "      policy-checker: Checks the request against our written refund policy.\n\
                         \x20     fraud-checker: Looks for signs the request is not genuine.\n";
const REAL_SHARES: &str = "        policy-checker: 60%\n        fraud-checker: 40%\n";

#[test]
fn the_worked_shape_with_every_name_spelt_right_is_accepted() {
    // The mechanism has to cost nothing when the author got it right, or it is
    // not a check, it is an obstacle.
    let d = check(&desk(REAL_TEAM, REAL_SHARES));
    assert!(!d.has_errors(), "{}", d.render());
}

#[test]
fn a_teammate_whose_name_has_no_agent_folder_is_refused_at_check_time() {
    let d = check(&desk(
        "      polcy-checker: Checks the request against our written refund policy.\n\
         \x20     fraud-checker: Looks for signs the request is not genuine.\n",
        "        polcy-checker: 60%\n        fraud-checker: 40%\n",
    ));
    let e = d
        .items()
        .iter()
        .find(|x| x.rule == "schema/no-such-name" && x.message.contains("'team'"))
        .unwrap_or_else(|| panic!("a teammate with no agent must be refused:\n{}", d.render()));

    assert!(
        e.message.contains("polcy-checker"),
        "name what is wrong: {}",
        e.message
    );
    assert!(
        e.message.contains("`agents:`"),
        "name where it was looked for: {}",
        e.message
    );
    // The fix has to be typeable: the names that do exist, and the file to make
    // if this one is genuinely new. "No such agent" without the list is a dead
    // end for a reader who cannot grep the tree.
    assert!(
        e.fix.contains("policy-checker"),
        "offer what does exist: {}",
        e.fix
    );
    assert!(
        e.fix.contains("fraud-checker"),
        "offer all of them: {}",
        e.fix
    );
    // In the shape the kind really takes. `agents/<name>.yaml` was one answer and
    // `team:`'s own help ("Give each one a folder under `agents/`") was another.
    assert!(
        e.fix.contains("agents/polcy-checker/agent.yaml"),
        "offer the file to add, in the shape the help promises: {}",
        e.fix
    );
}

#[test]
fn a_share_written_against_a_misspelt_teammate_is_refused_at_check_time() {
    // The team is spelt right and only the share is wrong, which is the shape
    // that costs money: `Pool.share_of` looks the real member up, finds nothing,
    // and hands them 0.0 while the typo holds 60%.
    let d = check(&desk(
        REAL_TEAM,
        "        polcy-checker: 60%\n        fraud-checker: 40%\n",
    ));
    let e = d
        .items()
        .iter()
        .find(|x| x.rule == "schema/no-such-name" && x.message.contains("'shares'"))
        .unwrap_or_else(|| panic!("a share for nobody must be refused:\n{}", d.render()));

    assert!(e.message.contains("polcy-checker"), "{}", e.message);
    assert!(
        e.message.contains("`team:`"),
        "the team is where a share is looked up: {}",
        e.message
    );
    assert!(
        e.fix.contains("policy-checker"),
        "offer what does exist: {}",
        e.fix
    );
    // A `^` map is a block in the document already open, so the instruction is
    // to add a line to it rather than to create a file.
    assert!(
        e.fix.contains("add a `polcy-checker:` entry under `team:`"),
        "{}",
        e.fix
    );
}

#[test]
fn a_share_for_an_agent_who_is_not_on_this_team_is_refused_too() {
    // Not a typo at all, and the same silent loss: `refund-desk` is a real agent
    // in the workspace, it is nobody's teammate here, and 40% of the pot would
    // be set aside for somebody who is never asked.
    let d = check(&desk(
        REAL_TEAM,
        "        policy-checker: 60%\n        refund-desk: 40%\n",
    ));
    let e = d
        .items()
        .iter()
        .find(|x| x.rule == "schema/no-such-name" && x.message.contains("refund-desk"))
        .unwrap_or_else(|| {
            panic!(
                "a share for a non-teammate must be refused:\n{}",
                d.render()
            )
        });
    assert!(
        e.fix.contains("fraud-checker"),
        "offer who is actually on the team: {}",
        e.fix
    );
}

#[test]
fn the_caret_lands_on_the_key_and_not_on_the_value_beside_it() {
    // The author wrote `polcy-checker: 60%`. The 60% is not what is wrong with
    // it, and underlining the value sends them to fix the wrong half of a line
    // they are already staring at.
    let doc = desk(
        REAL_TEAM,
        "        polcy-checker: 60%\n        fraud-checker: 40%\n",
    );
    let d = check(&doc);
    let e = d
        .items()
        .iter()
        .find(|x| x.rule == "schema/no-such-name" && x.message.contains("'shares'"))
        .expect("refused");

    let line = doc
        .lines()
        .nth(e.span.line - 1)
        .expect("the span names a real line");
    assert!(
        line.contains("polcy-checker"),
        "the caret is on line {}: {line:?}",
        e.span.line
    );
    // And on the key's own column, not on the column the percentage starts at.
    let key_at = line.find("polcy-checker").expect("the key is on that line") + 1;
    assert_eq!(
        e.span.col, key_at,
        "the caret must sit under the key: {line:?}"
    );
}

#[test]
fn every_line_the_author_has_to_edit_gets_its_own_message_and_no_line_gets_two() {
    // Two wrong names, two lines, two messages — an author fixes them in one
    // pass rather than one per run. And never two messages on one line, which
    // is one mistake said twice.
    let d = check(&desk(
        REAL_TEAM,
        "        polcy-checker: 60%\n        frad-checker: 40%\n",
    ));
    let refusals: Vec<_> = d
        .items()
        .iter()
        .filter(|x| x.rule == "schema/no-such-name")
        .collect();
    assert_eq!(
        refusals.len(),
        2,
        "both wrong names must be caught in one pass:\n{}",
        d.render()
    );
    let lines: Vec<usize> = refusals.iter().map(|x| x.span.line).collect();
    assert_ne!(lines[0], lines[1], "{}", d.render());
}

#[test]
fn a_share_is_held_against_the_team_that_was_written_so_one_slip_is_one_message() {
    // The commonest shape of this mistake is one name typed wrong twice: once
    // under `team:`, once under `shares:`. Because a share resolves against the
    // team beside it rather than against the whole workspace, the pair is
    // consistent and only the line that decides who is on the team is reported.
    //
    // That is the right end to start from — the share is only wrong BECAUSE the
    // team is — and correcting it brings the share back into range on the next
    // run. The alternative, two messages for one decision, sends the author to
    // fix a line that is doing exactly what they told it to.
    let d = check(&desk(
        "      polcy-checker: Checks the request against our written refund policy.\n\
         \x20     fraud-checker: Looks for signs the request is not genuine.\n",
        "        polcy-checker: 60%\n        fraud-checker: 40%\n",
    ));
    let refusals: Vec<_> = d
        .items()
        .iter()
        .filter(|x| x.rule == "schema/no-such-name")
        .collect();
    assert_eq!(refusals.len(), 1, "the root cause, once:\n{}", d.render());
    assert!(
        refusals[0].message.contains("'team'"),
        "{}",
        refusals[0].message
    );
    assert!(
        refusals[0].message.contains("`agents:`"),
        "{}",
        refusals[0].message
    );
}

#[test]
fn a_map_the_specification_asks_nothing_of_is_left_alone() {
    // `accepts:`, `answers-with:`, `run-inputs:` and the rest are maps whose
    // keys the author invents. A check that fired on every map would refuse all
    // of them, so the mechanism has to cost exactly nothing where it is not
    // asked for.
    const OPEN: &str = r#"
groups:
  agent:
    fields:
      accepts:
        type: map of text
        help: what you can send it
"#;
    let mut spec_problems = Diagnostics::new();
    let schema = schema_from_yaml(OPEN, &mut spec_problems);
    assert!(!spec_problems.has_errors(), "{}", spec_problems.render());

    let doc = "accepts:\n  message: text\n  photos: list of images\n";
    let node = parse_yaml(doc, Utf8Path::new("agent.yaml")).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source("agent.yaml", doc);
    schema.validate(&node, "agent", &mut d);
    assert!(!d.has_errors(), "{}", d.render());
}

#[test]
fn a_key_check_on_a_field_with_no_keys_is_refused_as_a_mistake_in_the_specification() {
    // A constraint that can never fire is the "loads and does nothing" failure
    // this whole file exists to end, one level up: it would sit in the
    // specification reading as a check while nothing checked anything.
    const WRONG: &str = r#"
groups:
  agent:
    fields:
      loop:
        type: text
        key-names: loops
        help: how this agent thinks
"#;
    let mut d = Diagnostics::new();
    schema_from_yaml(WRONG, &mut d);
    let e = d
        .items()
        .iter()
        .find(|x| x.rule == "schema/key-names-without-keys")
        .unwrap_or_else(|| panic!("an inert constraint must be reported:\n{}", d.render()));
    assert!(e.message.contains("'loop'"), "{}", e.message);
    assert!(
        e.fix.contains("map of"),
        "the fix must say what would make it fire: {}",
        e.fix
    );
}

#[test]
fn the_names_a_key_may_take_read_without_programming_knowledge() {
    // Same bar as every other diagnostic: the person reading this is the support
    // lead of decision D13, and every word of it has to be one they use.
    let d = check(&desk(
        "      polcy-checker: Checks the written refund policy.\n",
        "        polcy-checker: 100%\n",
    ));
    assert!(d.has_errors(), "{}", d.render());
    let text = d.render().to_lowercase();
    for jargon in [
        "enum",
        "variant",
        "deserialize",
        "key-value",
        "hashmap",
        "vec<",
        "option<",
    ] {
        assert!(
            !text.contains(jargon),
            "diagnostic leaked '{jargon}':\n{}",
            d.render()
        );
    }
    for item in d.items() {
        assert!(!item.fix.trim().is_empty(), "{} had no fix", item.rule);
    }
}
