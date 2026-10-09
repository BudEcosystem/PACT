//! **The arithmetic of `teamwork.shares`, checked where the person who typed it
//! is.**
//!
//! Two rules govern a by-share budget split, and both were already real —
//! `adapters/python/src/pact_adapters/delegation.py` refuses a teammate with no
//! share and a list of shares adding up to more than the pot. But it refuses
//! them from `Teamwork.from_document`, which runs when a RUN starts: in another
//! language, in a process decision D13's author never starts. Editing
//! `examples/refund-desk` so `shares:` read `policy-checker: 60%` and
//! `fraud-checker: 90%` — 150% of one pot — printed
//! `OK — … loaded cleanly (468 settings).` and exited 0.
//!
//! The schema's own help for `shares` promises percentages *"adding up to 100%
//! or less"*, so until this module the specification stated a rule that nothing
//! the author runs held anyone to. `BadTeamwork`'s own docstring claims it is
//! *"raised at load time, not mid-run"* and names the reason — *"an author …
//! should hear about it before a customer is waiting"* — which was true of the
//! intent and not of the reach.
//!
//! Eve is no help here and could not be: it splits a parent's token budget
//! **evenly** across children and gives an author no way to say otherwise, so it
//! has no shares to get wrong. This is PACT's own surface creating its own
//! mistake, which makes the diagnostic PACT's own debt — the same argument
//! `a_ceiling_with_no_declared_action_is_refused_and_the_choices_are_offered`
//! makes about `when-it-runs-out`.
//!
//! # Under 100% is deliberately legal
//!
//! `Pool.share_of` computes `total * share`, so shares adding up to 90% mean the
//! team may spend nine tenths of the pot and the last tenth is never spent.
//! That is a coherent thing to want — a reserve held back from the team — and it
//! is what the field's help already promises. Only OVER-allocation is refused,
//! and [`shares_add_up`]'s fix says so out loud, because an author who has just
//! been told "100% or less" and lands on 90% needs to know they have not made a
//! second mistake nobody mentioned.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Entry, Map, Node};

/// Floating-point slack when comparing a total against the whole pot.
///
/// The same constant, for the same reason, as `delegation.py`'s `_EPS`: refusing
/// a list that is over by 1e-15 would be arithmetic noise reported to a person
/// as a policy breach. `33.33% × 3` is what an author actually types.
const EPS: f64 = 1e-9;

/// The word under `divides-the-budget:` that makes `shares:` mean anything.
const BY_SHARE: &str = "by-share";

/// Refuse a `shares:` list that can never do what it says.
///
/// Takes the loaded document and nothing else — no second pass over the
/// filesystem, no author code — the same purity `LoadReport::of` keeps.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        // A single-agent tree: the agent IS the root, so there is no `agents:`
        // level to walk. `pact check` decides the same way (`root.get("agents")`).
        // "This agent" and not a quoted name, because a single-agent tree is the
        // whole thing the reader is looking at and has nothing to be told apart
        // from.
        check_one("This agent", document, diags);
        return;
    };
    for (name, agent) in agents {
        check_one(&format!("'{name}'"), &agent.node, diags);
    }
}

/// `agent_name` arrives already written the way it goes on the screen — quoted
/// in a workspace, plain in a single-agent tree — so no message below has to
/// know which kind of tree it is in.
fn check_one(agent_name: &str, agent: &Node, diags: &mut Diagnostics) {
    let Some(teamwork) = agent.get("teamwork") else {
        return;
    };
    enough_is_reachable(agent_name, agent, teamwork, diags);
    may_start_is_bounded(agent_name, agent, teamwork, diags);
    let Some(shares) = teamwork.get("shares") else {
        // No `shares:` at all is only a mistake when something divides by them.
        if divides_by_share(teamwork) {
            missing_shares_block(agent_name, agent, teamwork, diags);
        }
        return;
    };
    let Some(written) = shares.as_map() else {
        return;
    };

    if !divides_by_share(teamwork) {
        shares_nothing_divides(agent_name, teamwork, shares, diags);
        return;
    }

    // Where a diagnostic about the whole list points: the `shares:` key itself,
    // which is the line the author would edit. Not the first entry under it —
    // "these add up to 150%" is about the block, not about `policy-checker`.
    let block = key_span(teamwork, "shares").unwrap_or_else(|| shares.span.clone());

    let members = team_of(agent);
    // Only when the team is known. With no `team:` line every share is a name
    // nobody is, and one diagnostic per share would be a pile-on about a
    // different mistake — an agent whose teamwork has nobody to do it.
    let strangers = !members.is_empty() && shares_name_the_team(&members, written, diags);

    // A share written against a name that is not on the team is a MISSPELLING
    // until proved otherwise, and a misspelling is ONE mistake. `polcy-checker:
    // 60%` leaves `policy-checker` with no share, so both rules see it — but the
    // sentence worth reading is the one above, whose fix is the spelling to
    // CHANGE. "There is no share for policy-checker, add `policy-checker: 40%`"
    // offers a line to ADD, which is the wrong edit and the wrong number.
    //
    // Same argument `loader/wait-with-no-deadline` makes when it reports once
    // however many lines put the question: two things to fix for one edit is how
    // an author learns to run the command twice.
    if !strangers {
        everyone_has_a_share(agent_name, &members, &block, written, diags);
    }
    shares_add_up(agent_name, &block, written, diags);
}

// ─────────────────────────────────────────────────────────── a bar that can be met

/// `enough-is:` set higher than the number of people who could ever answer.
///
/// `delegation.py`'s `Teamwork.check` refuses this — *"That can never be met"* —
/// and it refuses it when a RUN starts, which is after the customer is already
/// waiting. The schema can say `enough-is:` is a whole number of at least one
/// and cannot count the team, so this is the half only the loader can do.
///
/// Silent with no `team:` line at all, for the reason `everyone_has_a_share` is:
/// an agent whose teamwork has nobody to do it is a different mistake, and one
/// mistake gets one message.
fn enough_is_reachable(agent_name: &str, agent: &Node, teamwork: &Node, diags: &mut Diagnostics) {
    if teamwork
        .get("waits-for")
        .and_then(Node::as_str)
        .map(str::trim)
        != Some("enough-of-them")
    {
        return;
    }
    let Some(wanted) = teamwork
        .get("enough-is")
        .and_then(Node::as_str)
        .and_then(|s| s.trim().parse::<i64>().ok())
    else {
        return; // absent is the schema's `needed-when:`; not a number is its type check
    };
    let members = team_of(agent);
    if members.is_empty() || wanted <= members.len() as i64 {
        return;
    }
    diags.push(Diagnostic::error(
        "loader/enough-is-more-than-the-team",
        key_span(teamwork, "enough-is").unwrap_or_else(|| teamwork.span.clone()),
        format!(
            "{agent_name} waits for {wanted} good answers and has {} on its team, so that \
             can never be met and the run would wait for ever.",
            members.len()
        ),
        format!(
            "Write `enough-is: {}` or fewer, or add more people under `team:`.",
            members.len()
        ),
    ));
}

// ────────────────────────────────────────────── run-time composition is bounded

/// `may-start:` without both of the ceilings that bound it (02P §8.1, 02W
/// WF-33).
///
/// R16 is narrowed, not reopened: an agent may bring others in while it runs
/// only within declared limits. The schema can say `starts-at-most:` is a whole
/// number and cannot say that one group's line needs two lines of ANOTHER group,
/// so this is the half only the loader can do. Read after `based-on:` is
/// resolved, so a ceiling an agent inherits counts as written.
fn may_start_is_bounded(agent_name: &str, agent: &Node, teamwork: &Node, diags: &mut Diagnostics) {
    let Some(written) = teamwork.get("may-start") else {
        return;
    };
    if written.as_list().is_some_and(<[Node]>::is_empty) {
        return; // `may-start: []` brings nobody in
    }
    let limits = agent.get("limits");
    let missing: Vec<&str> = ["starts-at-most", "nests-at-most"]
        .into_iter()
        .filter(|field| limits.and_then(|l| l.get(field)).is_none())
        .collect();
    if missing.is_empty() {
        return;
    }
    let lines = missing
        .iter()
        .map(|m| format!("`{m}:`"))
        .collect::<Vec<_>>()
        .join(" and ");
    diags.push(Diagnostic::error(
        "loader/may-start-without-its-bounds",
        key_span(teamwork, "may-start").unwrap_or_else(|| teamwork.span.clone()),
        format!(
            "{agent_name} may bring agents in while it runs (`may-start:`), and nothing says \
             how many or how deep: {lines} missing under `limits:`."
        ),
        "Add under `limits:` the lines `starts-at-most: 20` and `nests-at-most: 2` (Bud's \
         builder's figures), each with the `when-it-runs-out:` a ceiling needs."
            .to_string(),
    ));
}

// ───────────────────────────────────────────────────────── every teammate named

/// `divides-the-budget: by-share` with a teammate nobody gave a share to.
///
/// `delegation.py:382` is the run-time half —
/// `missing = [m for m in members if m not in self.shares]` — and it raises, so
/// this is a refusal and not a warning: the run would not have started.
fn everyone_has_a_share(
    agent_name: &str,
    members: &[String],
    block: &Span,
    written: &Map,
    diags: &mut Diagnostics,
) {
    let missing: Vec<&String> = members
        .iter()
        .filter(|m| !written.contains_key(*m))
        .collect();
    if missing.is_empty() {
        return;
    }

    // What is left of the pot, split between the people with no line yet.
    // Rounded DOWN, so applying this fix can never produce the over-100% list
    // the rule below would then refuse — a fix that creates the next error is
    // not a fix.
    let left = 1.0 - written_total(written).unwrap_or(0.0);
    let each = if left > 0.0 {
        (left * 100.0 / missing.len() as f64).floor()
    } else {
        0.0
    };
    let lines: Vec<String> = missing
        .iter()
        .map(|m| {
            if each >= 1.0 {
                format!("`{m}: {each:.0}%`")
            } else {
                format!("`{m}: 40%`")
            }
        })
        .collect();
    let fix = if each >= 1.0 {
        format!("Add a line under `shares:`: {}.", lines.join(" and "))
    } else {
        format!(
            "Add a line under `shares:`: {} — and lower the shares already there, \
             so the whole list adds up to 100% or less.",
            lines.join(" and ")
        )
    };

    let named = missing
        .iter()
        .map(|m| format!("'{m}'"))
        .collect::<Vec<_>>()
        .join(" and ");
    let are = if missing.len() == 1 {
        "is on"
    } else {
        "are on"
    };
    diags.push(Diagnostic::error(
        "loader/teammate-with-no-share",
        block.clone(),
        format!(
            "{agent_name} shares its budget out by share, and {named} {are} its team \
             with no share here. Everyone on the team needs a line under `shares:`, so \
             this is refused before anything runs."
        ),
        fix,
    ));
}

/// `divides-the-budget: by-share` and no `shares:` block anywhere.
///
/// Split out from the rule above because the diagnostic has nowhere to point
/// yet — there is no `shares:` line to underline, so it underlines the line that
/// asked for one.
fn missing_shares_block(agent_name: &str, agent: &Node, teamwork: &Node, diags: &mut Diagnostics) {
    let members = team_of(agent);
    let each = if members.is_empty() {
        0.0
    } else {
        (100.0 / members.len() as f64).floor()
    };
    let lines: Vec<String> = members
        .iter()
        .map(|m| format!("  {m}: {each:.0}%"))
        .collect();
    let fix = if lines.is_empty() {
        "Write `divides-the-budget: evenly` instead, or add a `shares:` block giving \
         each teammate a percentage."
            .to_string()
    } else {
        format!(
            "Add these lines under `teamwork`:\n         shares:\n         {}",
            lines.join("\n         ")
        )
    };
    diags.push(Diagnostic::error(
        "loader/teammate-with-no-share",
        key_span(teamwork, "divides-the-budget").unwrap_or_else(|| teamwork.span.clone()),
        format!(
            "{agent_name} says to share its budget out by share, and never says what \
             the shares are. Nobody on the team would get anything, so this is refused \
             before anything runs."
        ),
        fix,
    ));
}

// ─────────────────────────────────────────────────────────── the names are real

/// A share for somebody who is not on the team. Returns whether any was found.
///
/// The line that costs money: `Pool.share_of` is only ever asked about members,
/// so a stranger's share is read by nobody — while `sum(self.shares.values())`
/// at `delegation.py:389` counts it. `polcy-checker: 60%` therefore hands the
/// real `policy-checker` a slice of 0.0 and leaves the typo holding the majority
/// of a pot nothing will ever draw from.
///
/// There is a general form of this rule — `key-names: ^team` on
/// `teamwork.shares` in the specification, which holds a map's KEYS against a
/// named set the way `names:` already holds a value. It is built and deliberately
/// not switched on, because the two say the same thing about the same line and
/// one typo may only produce one message;
/// `crates/pact-cli/tests/a_teammate_who_is_not_an_agent.rs`'s
/// `only_one_thing_refuses_a_share_written_for_a_stranger` is what holds exactly
/// one of them in force. This one ships because it can name the team in the
/// message and offer the folder in the fix.
fn shares_name_the_team(members: &[String], written: &Map, diags: &mut Diagnostics) -> bool {
    let team = members
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>()
        .join(", ");
    let mut found = false;
    for (name, entry) in written {
        if members.iter().any(|m| m == name) {
            continue;
        }
        found = true;
        diags.push(Diagnostic::error(
            "loader/share-for-someone-not-on-the-team",
            entry.key_span.clone(),
            format!(
                "'{name}' has a share of the budget and is not on this agent's team, so \
                 nothing ever gives it that money — and the share is taken out of the pot \
                 all the same. The team is: {team}."
            ),
            format!(
                "Change '{name}' to one of those names. To make '{name}' a real teammate \
                 instead, give it a line under `team:` in `agent.yaml` and a folder under \
                 `agents/`. Or delete the line."
            ),
        ));
    }
    found
}

// ───────────────────────────────────────────────────────────── the sum holds up

/// Shares adding up to more than there is.
///
/// `delegation.py:389-392` is the run-time half, and its message is the one this
/// generalises: *"the shares under teamwork add up to N%, which is more than
/// there is."* Here the names are in hand, so the fix can be the scaled-down
/// list rather than an instruction to work one out.
fn shares_add_up(agent_name: &str, block: &Span, written: &Map, diags: &mut Diagnostics) {
    // A share that is not a percentage at all has already been reported by the
    // schema, with the line to type (`Write it like `90%`.`). Adding "they add
    // up to 60%" on top would be a second message for one mistake, about a total
    // computed from a number the author has not finished writing.
    let Some(total) = written_total(written) else {
        return;
    };
    if total <= 1.0 + EPS {
        return;
    }

    // The same list, scaled to fit, rounded DOWN so the suggestion is never
    // itself over. Offered only for a team small enough to print; past that the
    // line would be longer than the file.
    let scaled: Vec<String> = written
        .iter()
        .filter_map(|(name, e)| {
            percent(&e.node).map(|p| format!("`{name}: {:.0}%`", (p / total * 100.0).floor()))
        })
        .collect();
    let example = if scaled.len() <= 4 && scaled.len() == written.len() {
        format!(" — for example {}", scaled.join(" and "))
    } else {
        String::new()
    };

    diags.push(Diagnostic::error(
        "loader/shares-add-up-to-more-than-the-pot",
        block.clone(),
        format!(
            "{agent_name} has shares that add up to {}%, and there is only 100% to share \
             out. This is refused before anything runs.",
            round(total * 100.0)
        ),
        format!(
            "Change them so they add up to 100% or less{example}. Less than 100% is \
             allowed and means what you would expect: the team may spend that much of \
             the budget and the rest is never spent."
        ),
    ));
}

// ──────────────────────────────────────────────────── shares nothing looks at

/// `shares:` written beside a `divides-the-budget:` that never reads them.
///
/// A warning and not a refusal, because the tree runs — it just does not do what
/// the author wrote. `Pool.share_of` consults `self.shares` only under
/// `by-share`; under `evenly` and `as-needed` the block is decoration, which is
/// the same silent-loss shape `loader/shows-nothing-can-supply` reports about a
/// `shows:` name no park can supply.
fn shares_nothing_divides(
    agent_name: &str,
    teamwork: &Node,
    shares: &Node,
    diags: &mut Diagnostics,
) {
    let how = teamwork
        .get("divides-the-budget")
        .and_then(Node::as_str)
        .map(str::trim)
        .unwrap_or("")
        .to_string();
    let (said, means) = if how.is_empty() {
        (
            "does not say how it divides its budget, so it divides it evenly".to_string(),
            "evenly".to_string(),
        )
    } else {
        (format!("says `divides-the-budget: {how}`"), how.clone())
    };
    let mut d = Diagnostic::warning(
        "loader/shares-nothing-divides-by",
        key_span(teamwork, "shares").unwrap_or_else(|| shares.span.clone()),
        format!(
            "{agent_name} {said}, and `{means}` never looks at `shares:` — so these \
             percentages are read by nobody and the budget is split some other way."
        ),
        format!(
            "Write `divides-the-budget: {BY_SHARE}` if you meant these percentages to \
             be used, or delete the `shares:` lines."
        ),
    );
    if let Some(at) = key_span(teamwork, "divides-the-budget") {
        d = d.with_related(at, "this is the line that decides");
    }
    diags.push(d);
}

// ──────────────────────────────────────────────────────────────────── reading

fn divides_by_share(teamwork: &Node) -> bool {
    teamwork
        .get("divides-the-budget")
        .and_then(Node::as_str)
        .map(str::trim)
        == Some(BY_SHARE)
}

/// The names under `team:`, in the order the author wrote them.
fn team_of(agent: &Node) -> Vec<String> {
    agent
        .get("team")
        .and_then(Node::as_map)
        .map(|m| m.keys().cloned().collect())
        .unwrap_or_default()
}

/// The whole list added up, or `None` when any line is not a percentage.
///
/// `None` rather than "skip that one": a total computed from a list with an
/// unreadable entry in it is a number nobody wrote, and putting it in front of a
/// person as *"they add up to 60%"* would be worse than saying nothing.
fn written_total(written: &Map) -> Option<f64> {
    let mut total = 0.0;
    for entry in written.values() {
        total += percent(&entry.node)?;
    }
    Some(total)
}

/// `60%`, `0.6` — read through the schema's own percentage reader.
///
/// Not a second implementation, for the reason `report::milliseconds` gives
/// about durations: two readers of one written form drift, and the drift is
/// invisible until it changes an answer.
fn percent(node: &Node) -> Option<f64> {
    match pact_schema::coerce::check(node, &pact_schema::Ty::Percent) {
        Some(pact_schema::coerce::Coerced::Percent(p)) => Some(p),
        _ => None,
    }
}

/// A total a person would recognise: `150`, not `150.00000000000003`.
///
/// Whole percent where the sum lands on one, one decimal place otherwise —
/// `33.4%` is a real total an author can arrive at and rounding it to `33` would
/// print a number that does not match their file.
fn round(pct: f64) -> String {
    let whole = (pct * 10.0).round() / 10.0;
    if (whole - whole.round()).abs() < 0.05 {
        format!("{:.0}", whole.round())
    } else {
        format!("{whole:.1}")
    }
}

/// The span of a key, so a diagnostic underlines the setting rather than the
/// whole file.
fn key_span(node: &Node, field: &str) -> Option<Span> {
    node.as_map()
        .and_then(|m: &Map| m.get(field))
        .map(|e: &Entry| e.key_span.clone())
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn doc(text: &str) -> Node {
        parse_yaml(text, camino::Utf8Path::new("teamwork.yaml")).expect("parses")
    }

    fn run(text: &str) -> Diagnostics {
        let mut d = Diagnostics::new();
        check(&doc(text), &mut d);
        d
    }

    fn only(d: &Diagnostics, rule: &str) {
        assert_eq!(
            d.items().len(),
            1,
            "expected one message and got: {}",
            d.render()
        );
        assert_eq!(d.items()[0].rule, rule, "{}", d.render());
    }

    const TWO_MEMBERS: &str = "
agents:
  refund-desk:
    team:
      policy-checker: Checks the policy.
      fraud-checker: Looks for fraud.
    teamwork:
      divides-the-budget: by-share
      shares:
";

    const STARTS: &str = "
agents:
  orchestrator:
    teamwork:
      may-start: [catalogue, narrowed-new]
";

    #[test]
    fn may_start_without_its_bounds_is_refused_and_names_both_lines() {
        let d = run(STARTS);
        only(&d, "loader/may-start-without-its-bounds");
        let e = &d.items()[0];
        assert!(
            e.message.contains("`starts-at-most:` and `nests-at-most:`"),
            "{}",
            e.message
        );
        assert!(e.fix.contains("starts-at-most: 20"), "{}", e.fix);
    }

    #[test]
    fn may_start_with_one_bound_names_only_the_one_missing() {
        let d = run(&format!("{STARTS}    limits:\n      starts-at-most: 20\n"));
        only(&d, "loader/may-start-without-its-bounds");
        let e = &d.items()[0];
        assert!(
            e.message.contains("`nests-at-most:` missing"),
            "{}",
            e.message
        );
        assert!(
            !e.message.contains("`starts-at-most:` and"),
            "{}",
            e.message
        );
    }

    #[test]
    fn may_start_with_both_bounds_or_with_nobody_listed_is_left_alone() {
        let bounded =
            format!("{STARTS}    limits:\n      starts-at-most: 20\n      nests-at-most: 2\n");
        assert!(run(&bounded).is_empty(), "{}", run(&bounded).render());
        let nobody = "agents:\n  a:\n    teamwork:\n      may-start: []\n";
        assert!(run(nobody).is_empty(), "{}", run(nobody).render());
    }

    #[test]
    fn the_total_that_was_written_is_stated_and_the_fix_is_the_same_list_scaled_to_fit() {
        let d = run(&format!(
            "{TWO_MEMBERS}        policy-checker: 60%\n        fraud-checker: 90%\n"
        ));
        only(&d, "loader/shares-add-up-to-more-than-the-pot");
        let e = &d.items()[0];
        assert!(
            e.message.contains("150%"),
            "the total that was written: {}",
            e.message
        );
        assert!(e.message.contains("only 100%"), "{}", e.message);
        assert!(
            e.fix.contains("`policy-checker: 40%`"),
            "scaled to fit: {}",
            e.fix
        );
        assert!(e.fix.contains("`fraud-checker: 60%`"), "{}", e.fix);
    }

    #[test]
    fn a_teammate_with_no_share_is_named_and_offered_what_is_left_of_the_pot() {
        let d = run(&format!("{TWO_MEMBERS}        policy-checker: 60%\n"));
        only(&d, "loader/teammate-with-no-share");
        let e = &d.items()[0];
        assert!(e.message.contains("'fraud-checker'"), "{}", e.message);
        assert!(
            e.fix.contains("`fraud-checker: 40%`"),
            "the rest of the pot: {}",
            e.fix
        );
    }

    #[test]
    fn shares_adding_up_to_less_than_the_pot_are_left_alone() {
        // Under-allocation is a reserve held back, not a mistake: `Pool.share_of`
        // multiplies, so 90% of the pot is what the team may spend.
        let d = run(&format!(
            "{TWO_MEMBERS}        policy-checker: 50%\n        fraud-checker: 40%\n"
        ));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn the_fix_for_an_over_allocated_list_says_that_under_is_allowed() {
        // The author has just been told "100% or less" and will land somewhere
        // under it. Leaving them to wonder whether that is a second mistake is
        // how a correct file gets edited back into a wrong one.
        let d = run(&format!(
            "{TWO_MEMBERS}        policy-checker: 60%\n        fraud-checker: 90%\n"
        ));
        assert!(
            d.items()[0].fix.contains("Less than 100% is allowed"),
            "{}",
            d.items()[0].fix
        );
    }

    #[test]
    fn a_share_for_somebody_not_on_the_team_is_named_as_money_nobody_gets() {
        let d = run(&format!(
            "{TWO_MEMBERS}        policy-checker: 60%\n        fraud-checker: 30%\n        \
             billing-checker: 10%\n"
        ));
        only(&d, "loader/share-for-someone-not-on-the-team");
        let e = &d.items()[0];
        assert!(e.message.contains("'billing-checker'"), "{}", e.message);
        assert!(
            e.message.contains("policy-checker, fraud-checker"),
            "names the team: {}",
            e.message
        );
        assert!(e.fix.contains("delete the line"), "{}", e.fix);
    }

    #[test]
    fn a_misspelt_share_name_is_one_mistake_and_gets_one_message() {
        // `polcy-checker: 60%` leaves `policy-checker` with no share, so both
        // rules see it. The useful sentence is the one about the NAME, whose fix
        // is the spelling to change; "there is no share for policy-checker, add
        // `policy-checker: 40%`" offers a line to add, which is the wrong edit.
        let d = run(&format!(
            "{TWO_MEMBERS}        polcy-checker: 60%\n        fraud-checker: 40%\n"
        ));
        only(&d, "loader/share-for-someone-not-on-the-team");
        assert!(
            d.items()[0].message.contains("'polcy-checker'"),
            "{}",
            d.items()[0].message
        );
    }

    #[test]
    fn shares_written_where_nothing_divides_by_them_are_a_warning_not_a_refusal() {
        let d = run("
agents:
  refund-desk:
    team:
      policy-checker: Checks the policy.
    teamwork:
      divides-the-budget: evenly
      shares:
        policy-checker: 100%
");
        only(&d, "loader/shares-nothing-divides-by");
        assert!(!d.has_errors(), "the tree still runs: {}", d.render());
        assert!(
            d.items()[0].fix.contains("divides-the-budget: by-share"),
            "{}",
            d.items()[0].fix
        );
        assert_eq!(
            d.items()[0].related.len(),
            1,
            "must point at the line that decides"
        );
    }

    #[test]
    fn by_share_with_no_shares_at_all_offers_the_block_to_type() {
        let d = run("
agents:
  refund-desk:
    team:
      policy-checker: Checks the policy.
      fraud-checker: Looks for fraud.
    teamwork:
      divides-the-budget: by-share
");
        only(&d, "loader/teammate-with-no-share");
        let fix = &d.items()[0].fix;
        assert!(fix.contains("shares:"), "{fix}");
        assert!(fix.contains("policy-checker: 50%"), "{fix}");
        assert!(fix.contains("fraud-checker: 50%"), "{fix}");
    }

    #[test]
    fn a_share_that_is_not_a_percentage_is_left_to_the_one_message_that_names_it() {
        // `policy-checker: 60` is already reported by the schema, with the line
        // to type. A total worked out from a number the author has not finished
        // writing would be a second message for one mistake.
        let d = run(&format!(
            "{TWO_MEMBERS}        policy-checker: 60\n        fraud-checker: 90%\n"
        ));
        assert!(
            !d.items()
                .iter()
                .any(|x| x.rule == "loader/shares-add-up-to-more-than-the-pot"),
            "{}",
            d.render()
        );
    }

    #[test]
    fn a_team_with_no_teamwork_block_is_not_a_mistake() {
        let d = run("
agents:
  refund-desk:
    team:
      policy-checker: Checks the policy.
");
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_rounding_total_is_printed_as_the_author_would_recognise_it() {
        // Three thirds. Refusing 100.00000000000001% would be arithmetic noise
        // reported to a person as a policy breach.
        let d = run("
agents:
  desk:
    team:
      a: one
      b: two
      c: three
    teamwork:
      divides-the-budget: by-share
      shares:
        a: 33.34%
        b: 33.33%
        c: 33.33%
");
        assert!(d.is_empty(), "{}", d.render());
        assert_eq!(round(150.000000001), "150");
        assert_eq!(round(133.4), "133.4");
    }

    #[test]
    fn a_single_agent_tree_is_checked_too() {
        // `pact check` treats a tree with no `agents:` as one agent, and a
        // teamwork mistake in it is the same mistake.
        let d = run("
team:
  policy-checker: Checks the policy.
  fraud-checker: Looks for fraud.
teamwork:
  divides-the-budget: by-share
  shares:
    policy-checker: 70%
    fraud-checker: 70%
");
        only(&d, "loader/shares-add-up-to-more-than-the-pot");
    }

    #[test]
    fn every_message_names_the_file_and_line_and_offers_something_to_type() {
        // O7.3 across every rule here at once.
        let mut d = run(&format!(
            "{TWO_MEMBERS}        policy-checker: 90%\n        fraud-checker: 90%\n"
        ));
        check(
            &doc("
agents:
  desk:
    team:
      a: one
    teamwork:
      divides-the-budget: evenly
      shares:
        a: 100%
"),
            &mut d,
        );
        check(
            &doc("
agents:
  desk:
    team:
      a: one
    teamwork:
      divides-the-budget: by-share
"),
            &mut d,
        );
        check(
            &doc(&format!(
                "{TWO_MEMBERS}        policy-checker: 60%\n        fraud-checker: 30%\n        \
                 billing-checker: 10%\n"
            )),
            &mut d,
        );
        assert_eq!(d.items().len(), 4, "{}", d.render());
        for item in d.items() {
            assert!(
                !item.fix.trim().is_empty(),
                "rule {} gave no fix",
                item.rule
            );
            assert!(item.span.line >= 1, "rule {} points nowhere", item.rule);
            assert!(
                item.fix.contains('`'),
                "rule {} offers nothing to type: {}",
                item.rule,
                item.fix
            );
        }
    }
}
