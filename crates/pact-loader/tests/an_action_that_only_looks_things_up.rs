//! **`reads-only:` — the field beside the one-line gate that nothing read.**
//!
//! F17 wired `needs-a-person:` on the `action` block. Counting the seven fields
//! sitting beside it on that same block found one, and only one, that no
//! component anywhere reads: `reads-only:`. It is written twice in the shipped
//! worked example (`tools/payments.yaml`, `tools/zendesk.yaml`) and once in
//! `tests/trees/one-line-gate/tools/payments.yaml`, and until this file existed
//! every one of those lines was decoration — the author's statement that an
//! action is safe, reaching nothing that could act on it.
//!
//! That is the defect this project keeps shipping, one line away from the field
//! the item was about. So `reads-only:` now REFUSES something: an action cannot
//! say it only looks things up and also say it moves money. The two lines pull
//! the rest of the file in opposite directions — `spends-money:` forces a
//! same-request key and makes `loader/money-moves-with-nobody-asked` fire, while
//! `reads-only:` is the author's own statement that nobody needs to be asked —
//! so whichever a reader believes decides whether a person stands in front of
//! the money.
//!
//! Everything here goes through the loader's `check`, on documents that hold
//! only the author's lines. Nothing constructs a diagnostic.

use camino::Utf8Path;
use pact_diag::Diagnostics;
use pact_doc::parse_yaml;

fn problems(text: &str) -> Diagnostics {
    let node = parse_yaml(text, Utf8Path::new("tools/payments.yaml")).expect("parses");
    let mut d = Diagnostics::new();
    d.add_source("tools/payments.yaml", text);
    pact_loader::money::check(&node, &mut d);
    d
}

fn rules(d: &Diagnostics) -> Vec<&'static str> {
    d.items().iter().map(|i| i.rule).collect()
}

/// One tool, one agent, and the two lines under test written out in full so a
/// test can delete either of them.
const BOTH: &str = "
agents:
  desk:
    description: Refunds a customer.
    uses: [payments]
tools:
  payments:
    description: Where refunds are issued.
    actions:
      issue-refund:
        description: Send money back to the customer.
        takes:
          order-number: text
          amount: money
        reads-only: yes
        spends-money: yes
        same-request-key: order-number
        needs-a-person: yes
";

#[test]
fn an_action_cannot_say_it_only_looks_things_up_and_also_say_it_moves_money() {
    // The whole claim. Both lines are legal on their own and the schema accepts
    // each of them, because `needed-when:` holds one field against another field
    // of the same document and neither of these says anything about the other.
    // Nothing had ever held them against each other.
    let d = problems(BOTH);
    assert!(
        rules(&d).contains(&"loader/looks-things-up-and-spends"),
        "an action saying both things loaded clean:\n{}",
        d.render()
    );
    assert!(
        d.error_count() >= 1,
        "it has to be a refusal, not a note:\n{}",
        d.render()
    );
}

#[test]
fn deleting_the_reads_only_line_is_what_makes_that_same_action_load() {
    // The negative control, and the only thing that proves the AUTHOR's line is
    // what produces the refusal. Same document, one line removed.
    let without = BOTH.replace("        reads-only: yes\n", "");
    assert_ne!(without, BOTH, "the line this test deletes must exist");
    let d = problems(&without);
    assert!(
        !rules(&d).contains(&"loader/looks-things-up-and-spends"),
        "the refusal survived the line that causes it:\n{}",
        d.render()
    );
}

#[test]
fn deleting_the_spends_money_line_instead_also_makes_it_load() {
    // The other half of the same control. The refusal is about the PAIR, so
    // either deletion clears it — which is exactly what the fix offers, in that
    // order, and a fix that does not work is worse than no fix.
    let without = BOTH.replace("        spends-money: yes\n", "");
    let d = problems(&without);
    assert!(
        !rules(&d).contains(&"loader/looks-things-up-and-spends"),
        "deleting the money line left the contradiction behind:\n{}",
        d.render()
    );
}

#[test]
fn the_message_names_the_action_the_two_lines_and_a_fix_a_support_lead_can_type() {
    // D13's bar. The reader cannot write code, so the sentence has to name what
    // is wrong and the fix has to be something they can type into the file they
    // already have open.
    let d = problems(BOTH);
    let found = d
        .items()
        .iter()
        .find(|i| i.rule == "loader/looks-things-up-and-spends")
        .expect("the refusal exists");

    for named in ["issue-refund", "payments", "reads-only", "spends-money"] {
        assert!(
            found.message.contains(named),
            "the sentence never says '{named}': {}",
            found.message
        );
    }
    assert!(
        found.fix.contains("Delete `reads-only: yes`")
            && found.fix.contains("Delete `spends-money: yes`"),
        "both ways out have to be typeable: {}",
        found.fix
    );
    for jargon in [
        "boolean",
        "predicate",
        "null",
        "enum",
        "schema",
        "field",
        "invariant",
    ] {
        assert!(
            !found.message.to_lowercase().contains(jargon),
            "the sentence leaked '{jargon}': {}",
            found.message
        );
    }
    // And it points at the OTHER line as well, so the author does not have to
    // hunt for the half of the contradiction the caret is not under.
    assert!(
        found
            .related
            .iter()
            .any(|r| r.message.contains("moves money")),
        "the second line is never pointed at: {:?}",
        found.related
    );
}

#[test]
fn the_word_the_author_typed_is_the_word_the_message_quotes_back() {
    // `yes`, `y`, `true`, `on` and `enabled` are all a yes to the validator, so
    // all five have to be a yes here — a tick the checker does not recognise is
    // a contradiction it reports as fine. And quoting `yes` back at somebody who
    // wrote `enabled` sends them looking for a line they have not got, which is
    // the bar `authoring_surface.rs` already holds the loop diagnostics to.
    for spelling in ["enabled", "on", "y", "true"] {
        let text = BOTH.replace("reads-only: yes", &format!("reads-only: {spelling}"));
        let d = problems(&text);
        let found = d
            .items()
            .iter()
            .find(|i| i.rule == "loader/looks-things-up-and-spends")
            .unwrap_or_else(|| {
                panic!(
                    "`reads-only: {spelling}` was not read as a yes:\n{}",
                    d.render()
                )
            });
        assert!(
            found.message.contains(&format!("reads-only: {spelling}")),
            "written `{spelling}`, quoted back as something else: {}",
            found.message
        );
    }
}

#[test]
fn a_lookup_that_needs_a_person_is_left_alone_because_that_is_a_real_thing_to_want() {
    // Reading a customer's card details may very well need somebody's say-so.
    // The refusal is about `reads-only:` against `spends-money:` and nothing
    // else — widening it to `needs-a-person:` would make a legitimate gate
    // unwritable, which is the wrong ceiling every time.
    let text = "
agents:
  desk:
    description: Looks orders up.
    uses: [payments]
tools:
  payments:
    description: Where orders are looked up.
    actions:
      look-up-order:
        description: Find an order by its number.
        takes:
          order-number: text
        reads-only: yes
        needs-a-person: yes
";
    let d = problems(text);
    assert!(
        !rules(&d).contains(&"loader/looks-things-up-and-spends"),
        "a gated lookup was refused:\n{}",
        d.render()
    );
}

#[test]
fn a_tool_no_agent_uses_yet_is_still_told_about_its_own_contradiction() {
    // The warning this check sits beside asks "can an agent get to this money?",
    // which is a fact about `uses:`, so a tool nobody uses is not walked at all.
    // This asks "does this action describe itself twice, differently?", which is
    // a fact about the lines in front of the author — and a tool nobody uses yet
    // is exactly the tool being written right now.
    let orphan = BOTH.replace("    uses: [payments]", "    uses: []");
    let d = problems(&orphan);
    assert!(
        rules(&d).contains(&"loader/looks-things-up-and-spends"),
        "the tool being written this minute is the one told nothing:\n{}",
        d.render()
    );
}

#[test]
fn the_shipped_trees_write_reads_only_and_are_refused_by_none_of_this() {
    // A false positive on the shapes PACT itself ships costs an author their
    // trust in every other line the tool prints. Both trees write `reads-only:`
    // — on lookups, beside actions that move money — and neither may be touched.
    let here = Utf8Path::new(env!("CARGO_MANIFEST_DIR"));
    for tree in [
        "../../examples/refund-desk/tools",
        "../../tests/trees/one-line-gate/tools",
    ] {
        let dir = here.join(tree);
        let mut seen = 0;
        for file in std::fs::read_dir(dir.as_std_path())
            .expect("the tree is there")
            .flatten()
        {
            let path = file.path();
            if path.extension().and_then(|e| e.to_str()) != Some("yaml") {
                continue;
            }
            let text = std::fs::read_to_string(&path).expect("readable");
            if !text.contains("reads-only:") {
                continue;
            }
            seen += 1;
            // The tool file alone, wrapped so it is one entry of `tools:`, which
            // is the shape `check` walks. Loading the whole workspace here would
            // drag in every other rule in the loader.
            let wrapped = format!(
                "tools:\n  payments:\n{}",
                text.lines()
                    .map(|l| format!("    {l}"))
                    .collect::<Vec<_>>()
                    .join("\n")
            );
            let d = problems(&wrapped);
            assert!(
                !rules(&d).contains(&"loader/looks-things-up-and-spends"),
                "{} is refused by this check:\n{}",
                path.display(),
                d.render()
            );
        }
        assert!(
            seen > 0,
            "{dir} was supposed to write `reads-only:` and does not"
        );
    }
}
