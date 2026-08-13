//! **A team that has no bottom.**
//!
//! An agent may not name itself under `team:`, and two agents may not name each
//! other. Measured before this existed: `team: {helper: I ask myself.}` inside
//! `agents/helper/agent.yaml` printed *"OK — loaded cleanly (11 settings)"*, and
//! `a → b → a` printed the same. The `schema/no-such-name` diagnostic actively
//! invited it — with a misspelt key it offered the agent itself as one of the
//! valid teammates to change to.
//!
//! Eve forbids recursion structurally: `agent` is root-only and copies created
//! by it cannot call `agent`, so *"eve rejects it instead of starting another
//! child session"*. PACT's team is a general graph on purpose — a supervisor and
//! two specialists is the shape D20 exists for — so the structural answer is not
//! available and the check is. A cycle is not a smaller version of delegation:
//! `delegate_by_running` builds a transport per member and asks it, so a run that
//! reaches one spends the whole budget discovering it, on the request a customer
//! is waiting on.
//!
//! # Why the whole cycle is named
//!
//! An author looking at `a → b → a` cannot tell from either file alone that
//! anything is wrong: each names one teammate, which is ordinary. So the message
//! is the loop, written out in the order the run would take it, and the fix names
//! the one line to delete.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use std::collections::BTreeMap;

/// Refuse a `team:` that comes back to where it started.
pub fn no_team_calls_itself(document: &Node, diags: &mut Diagnostics) {
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        return;
    };
    // Who each agent names, and where the line is. `BTreeMap` so a workspace
    // with two cycles reports them in the same order on every machine.
    let mut names: BTreeMap<&str, Vec<(&str, pact_diag::Span)>> = BTreeMap::new();
    for (who, agent) in agents {
        let members = agent
            .node
            .get("team")
            .and_then(Node::as_map)
            .map(|m| {
                m.iter()
                    .filter(|(name, _)| agents.contains_key(name.as_str()))
                    .map(|(name, e)| (name.as_str(), e.key_span.clone()))
                    .collect()
            })
            .unwrap_or_default();
        names.insert(who.as_str(), members);
    }

    // One report per cycle, not one per member of it: `a → b → a` is one mistake.
    let mut reported: std::collections::BTreeSet<&str> = Default::default();
    for start in names.keys().copied() {
        if reported.contains(start) {
            continue;
        }
        let Some(path) = walk(&names, start) else { continue };
        // The one grant the ban leaves room for: a circle where EVERY member
        // has written its own bottom (`limits.asks-itself-at-most:`). One
        // missing figure and the refusal stands — naming who. Members of a
        // permitted circle are NOT marked reported: a second, unbudgeted
        // circle through the same agents is its own mistake.
        let unbudgeted: Vec<&str> = path
            .iter()
            .copied()
            .filter(|m| !has_budget(agents, m))
            .collect();
        if unbudgeted.is_empty() {
            continue;
        }
        for member in &path {
            reported.insert(member);
        }
        // The last hop is the line to delete: it is the one that closes the loop.
        let last = *path.last().expect("a cycle has at least one member");
        let span = names
            .get(last)
            .and_then(|edges| edges.iter().find(|(to, _)| *to == start).map(|(_, s)| s.clone()))
            .or_else(|| spans(&names, &path).into_iter().next_back())
            .expect("the closing edge was written somewhere");
        let last = &names
            .get(last)
            .and_then(|edges| edges.iter().find(|(to, _)| *to == start).map(|(to, _)| *to))
            .unwrap_or(start);
        let loop_ = path
            .iter()
            .map(|m| format!("'{m}'"))
            .collect::<Vec<_>>()
            .join(" asks ");
        let itself = path.len() == 1;
        diags.push(Diagnostic::error(
            "loader/team-that-has-no-bottom",
            span,
            if itself {
                format!(
                    "'{start}' has itself on its own team, so asking for help would ask \
                     itself, for ever."
                )
            } else {
                format!(
                    "{loop_} asks '{start}' — a team that comes back to where it started, \
                     so one request would go round it until the budget ran out."
                )
            },
            {
                let missing = unbudgeted
                    .iter()
                    .map(|m| format!("'{m}'"))
                    .collect::<Vec<_>>()
                    .join(", ");
                format!(
                    "Delete the `{last}:` line under `team:` — or write `asks-itself-at-most:` \
                     under `limits:` on {missing}, so the going round has a bottom. A circle is \
                     allowed only when every agent on it says how many times it may be put to work."
                )
            },
        ));
    }
}

/// Refuse a line that names a base — something to build on, not to run.
///
/// `base: yes` says nothing can run the agent, and three lines could promise
/// that something will: a `team:` entry, a port's `answers:`, and a stage's
/// `may-use:`. Each is refused where the author wrote it, because leaving any
/// one open makes the field's own help — "it never runs" — a lie through that
/// door: a port routes real traffic, and a stage offers the model a teammate
/// it may pick.
pub fn no_base_on_a_team(document: &Node, diags: &mut Diagnostics) {
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        return;
    };
    let is_base = |name: &str| agents.get(name).is_some_and(|a| says_yes(a.node.get("base")));

    for (_, agent) in agents {
        let Some(team) = agent.node.get("team").and_then(Node::as_map) else {
            continue;
        };
        for (member, entry) in team {
            if is_base(member.as_str()) {
                diags.push(Diagnostic::error(
                    "loader/a-teammate-that-is-only-a-base",
                    entry.key_span.clone(),
                    format!(
                        "'{member}' is a base — `base: yes` says nothing can run it, so it \
                         cannot be on a team."
                    ),
                    format!(
                        "Make a real agent `based-on: {member}` and name that one here, or \
                         delete the `{member}:` line under `team:`."
                    ),
                ));
            }
        }
    }

    // The ingress door: a port's `answers:` is which agent handles what
    // arrives, so a base here is a promise the outside world will reach
    // something that never runs.
    for (port, entry) in document.get("ports").and_then(Node::as_map).into_iter().flatten() {
        let Some(answers) = entry.node.get("answers") else {
            continue;
        };
        let Some(name) = answers.as_str() else {
            continue;
        };
        if is_base(name) {
            diags.push(Diagnostic::error(
                "loader/a-port-answered-by-a-base",
                answers.span.clone(),
                format!(
                    "'{port}' is answered by '{name}', which is a base — a port answered \
                     by something that never runs."
                ),
                format!(
                    "Make a real agent `based-on: {name}` and write that one on `answers:`, \
                     or point this port at an agent that runs."
                ),
            ));
        }
    }

    // The routing door: a stage's `may-use:` narrows what the agent may draw
    // on, and one of its vocabularies is `agents`. Offering a base there is
    // offering help that can never come.
    for (_, loop_) in document.get("loops").and_then(Node::as_map).into_iter().flatten() {
        for (_, stage) in loop_.node.get("steps").and_then(Node::as_map).into_iter().flatten() {
            let Some(may_use) = stage.node.get("may-use") else {
                continue;
            };
            let pact_doc::Value::List(items) = &may_use.value else {
                continue;
            };
            for item in items {
                let Some(name) = item.as_str() else {
                    continue;
                };
                if is_base(name) {
                    diags.push(Diagnostic::error(
                        "loader/a-stage-that-may-use-a-base",
                        item.span.clone(),
                        format!(
                            "'{name}' is a base — `base: yes` says nothing can run it, so no \
                             stage may use it."
                        ),
                        format!(
                            "Make a real agent `based-on: {name}` and name that one here, or \
                             take '{name}' off `may-use:`."
                        ),
                    ));
                }
            }
        }
    }
}

/// Whether this node answers yes, in any spelling an author writes it.
fn says_yes(n: Option<&Node>) -> bool {
    n.is_some_and(|n| match &n.value {
        pact_doc::Value::Bool(b) => *b,
        pact_doc::Value::Str(s) => matches!(s.trim(), "yes" | "true" | "on"),
        _ => false,
    })
}

/// Whether this agent wrote (or inherited — derive runs first) the figure
/// that gives a circle a bottom.
fn has_budget(agents: &pact_doc::Map, who: &str) -> bool {
    agents
        .get(who)
        .and_then(|e| e.node.get("limits"))
        .and_then(|l| l.get("asks-itself-at-most"))
        .is_some()
}

/// The cycle reachable from `start` that comes back to `start`, in order.
///
/// EVERY edge, not the first. Taking only the first meant `refund-desk` — whose
/// team is `policy-checker` then `fraud-checker` — was walked into
/// `policy-checker`, which names nobody, and the walk gave up before ever
/// reaching the `fraud-checker → refund-desk` edge that closes the loop. A check
/// that finds a cycle only when it happens to be on the first branch is a check
/// that reports whichever cycle the author's file ordering allowed.
fn walk<'a>(
    names: &BTreeMap<&'a str, Vec<(&'a str, pact_diag::Span)>>,
    start: &'a str,
) -> Option<Vec<&'a str>> {
    let mut path = vec![start];
    let mut on_path: std::collections::BTreeSet<&str> = [start].into_iter().collect();
    if descend(names, start, start, &mut path, &mut on_path) { Some(path) } else { None }
}

/// Depth-first from `here`, looking for a way back to `start`.
///
/// `path` holds the route taken so far and is left holding the cycle when this
/// returns true; a branch that leads nowhere is unwound, so a false answer costs
/// nothing.
fn descend<'a>(
    names: &BTreeMap<&'a str, Vec<(&'a str, pact_diag::Span)>>,
    here: &'a str,
    start: &'a str,
    path: &mut Vec<&'a str>,
    on_path: &mut std::collections::BTreeSet<&'a str>,
) -> bool {
    for (next, _) in names.get(here).into_iter().flatten() {
        if *next == start {
            return true;
        }
        // A loop that does NOT include `start` is reported from its own starting
        // point, so following it here would be two messages for one mistake.
        if !on_path.insert(next) {
            continue;
        }
        path.push(next);
        if descend(names, next, start, path, on_path) {
            return true;
        }
        path.pop();
    }
    false
}

/// The line each hop of the cycle was written on.
fn spans<'a>(
    names: &BTreeMap<&'a str, Vec<(&'a str, pact_diag::Span)>>,
    path: &[&'a str],
) -> Vec<pact_diag::Span> {
    path.iter()
        .filter_map(|who| names.get(who).and_then(|m| m.first()).map(|(_, s)| s.clone()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn check(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("w.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        no_team_calls_itself(&node, &mut d);
        d
    }

    #[test]
    fn an_agent_that_names_itself_as_a_teammate_is_refused() {
        let d = check("agents:\n  helper:\n    team:\n      helper: I ask myself.\n");
        let e = d.items().first().expect("a team with no bottom must be refused");
        assert_eq!(e.rule, "loader/team-that-has-no-bottom");
        assert!(e.message.contains("itself"), "{}", e.message);
        assert!(e.fix.contains("`helper:`"), "the line to delete: {}", e.fix);
    }

    #[test]
    fn two_agents_that_name_each_other_are_refused_once_and_the_loop_is_written_out() {
        let d = check(
            "agents:\n  a:\n    team:\n      b: helps\n  b:\n    team:\n      a: helps\n",
        );
        assert_eq!(d.items().len(), 1, "one loop is one mistake:\n{}", d.render());
        assert!(d.items()[0].message.contains("'a' asks 'b' asks 'a'"), "{}", d.items()[0].message);
    }

    #[test]
    fn an_ordinary_supervisor_and_two_specialists_is_left_alone() {
        let d = check(
            "agents:\n  desk:\n    team:\n      policy: checks policy\n      fraud: checks fraud\n\
             \n  policy:\n    description: x\n  fraud:\n    description: y\n",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn an_agent_with_a_budget_may_name_itself() {
        let d = check(
            "agents:\n  helper:\n    team:\n      helper: takes another look\n    limits:\n\
             \x20     asks-itself-at-most: 2\n      when-it-runs-out: stop-and-say-so\n",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_ring_where_every_agent_carries_a_budget_is_allowed() {
        let d = check(
            "agents:\n  a:\n    team:\n      b: helps\n    limits:\n\
             \x20     asks-itself-at-most: 2\n      when-it-runs-out: stop-and-say-so\n\
             \x20 b:\n    team:\n      a: helps\n    limits:\n\
             \x20     asks-itself-at-most: 2\n      when-it-runs-out: stop-and-say-so\n",
        );
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_ring_where_one_agent_has_no_budget_is_refused_naming_who() {
        let d = check(
            "agents:\n  a:\n    team:\n      b: helps\n    limits:\n\
             \x20     asks-itself-at-most: 2\n      when-it-runs-out: stop-and-say-so\n\
             \x20 b:\n    team:\n      a: helps\n",
        );
        assert_eq!(d.items().len(), 1, "one missing figure is one mistake:\n{}", d.render());
        let e = &d.items()[0];
        assert_eq!(e.rule, "loader/team-that-has-no-bottom");
        assert!(e.fix.contains("asks-itself-at-most"), "{}", e.fix);
        assert!(e.fix.contains("'b'"), "the refusal names who is missing: {}", e.fix);
        assert!(!e.fix.contains("'a',"), "the budgeted member is not blamed: {}", e.fix);
    }

    #[test]
    fn a_teammate_with_no_agent_behind_it_is_left_to_the_reference_check() {
        // `key-names: agents` already reports it at the line the author typed,
        // and a second message would be two things to fix for one mistake.
        let d = check("agents:\n  a:\n    team:\n      nobody: helps\n");
        assert!(d.is_empty(), "{}", d.render());
    }

    fn base_check(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("w.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        no_base_on_a_team(&node, &mut d);
        d
    }

    #[test]
    fn a_teammate_that_is_only_a_base_is_refused() {
        let d = base_check(
            "agents:\n  desk:\n    team:\n      pattern: helps\n  pattern:\n    base: yes\n\
             \x20   description: a shape\n",
        );
        assert_eq!(d.items().len(), 1, "one base on one team is one mistake:\n{}", d.render());
        let e = &d.items()[0];
        assert_eq!(e.rule, "loader/a-teammate-that-is-only-a-base");
        assert!(e.fix.contains("based-on: pattern"), "{}", e.fix);
    }

    #[test]
    fn a_base_nobody_names_is_left_alone() {
        let d = base_check("agents:\n  pattern:\n    base: yes\n    description: a shape\n");
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_port_answered_by_a_base_is_refused() {
        let d = base_check(
            "agents:\n  pattern:\n    base: yes\n    description: a shape\nports:\n\
             \x20 front-door:\n    description: people write in\n    answers: pattern\n",
        );
        assert_eq!(d.items().len(), 1, "{}", d.render());
        let e = &d.items()[0];
        assert_eq!(e.rule, "loader/a-port-answered-by-a-base");
        assert!(e.message.contains("never runs"), "{}", e.message);
        assert!(e.fix.contains("based-on: pattern"), "{}", e.fix);
    }

    #[test]
    fn a_stage_that_may_use_a_base_is_refused() {
        let d = base_check(
            "agents:\n  pattern:\n    base: yes\n    description: a shape\nloops:\n\
             \x20 careful:\n    steps:\n      work:\n        may-use:\n          - pattern\n",
        );
        assert_eq!(d.items().len(), 1, "{}", d.render());
        let e = &d.items()[0];
        assert_eq!(e.rule, "loader/a-stage-that-may-use-a-base");
        assert!(e.fix.contains("may-use"), "{}", e.fix);
    }
}
