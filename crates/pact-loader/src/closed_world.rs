//! **Whatever is not granted is refused** (law 4 of `docs/97-PRIMITIVES.md`,
//! `docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-1).
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/a-program-may-pick-a-stage-not-listed` | a loop stage's `decided-by:` program can answer with a stage that is not on its `may-go-to:` list |
//! | `loader/a-stage-may-use-what-the-agent-cannot` | a loop stage's `may-use:`, or a variant's, names something the agent that runs the loop neither `uses:` nor has on its `team:` |
//!
//! # Why these two are the checker's job
//!
//! Both were held only at run time. `decided-by:` was refused by the harness
//! when the program named a stage off its list, on the turn that happened;
//! `may-use:` by `Loop.check_against` before the first model call. That is a
//! guard, and a guard is the second line. The first is that the document cannot
//! say it: a program that answers `next: text` *can* name any stage, so the
//! closed list beside it is a hope rather than a fact, and a stage that may use
//! a tool its agent was never given is a permission written in the wrong place.
//!
//! The decision rule is law 6's other half as well: a decision the checker has
//! to reason about must be a pick from a closed `one of`, and a pure program
//! answering free text is not one.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use pact_schema::Schema;
use pact_schema::shape::{self, Shape};

/// Both rules, over the loaded document.
pub fn check(root: &Node, schema: &Schema, diags: &mut Diagnostics) {
    a_program_picks_only_what_it_may(root, schema, diags);
    a_stage_narrows_only_what_the_agent_has(root, diags);
}

/// `decided-by: <program>` beside `may-go-to: [...]`: the program's answer has
/// to be a `one of` whose every choice is on the list (or `done`).
fn a_program_picks_only_what_it_may(root: &Node, schema: &Schema, diags: &mut Diagnostics) {
    let Some(loops) = root.get("loops").and_then(Node::as_map) else {
        return;
    };
    let programs = root.get("programs").and_then(Node::as_map);
    let vocabulary = shape::vocabulary(schema);
    let named: Vec<&str> = root
        .get("shapes")
        .and_then(Node::as_map)
        .map(|m| m.keys().map(String::as_str).collect())
        .unwrap_or_default();
    for (loop_name, shape_entry) in loops {
        let Some(steps) = shape_entry.node.get("steps").and_then(Node::as_map) else {
            continue;
        };
        for (stage_name, stage) in steps {
            let Some(then) = stage.node.get("then") else {
                continue;
            };
            let Some(decider) = then.get("decided-by") else {
                continue;
            };
            let Some(program_name) = decider.as_str().map(str::trim) else {
                continue;
            };
            // `may-go-to:` missing is `schema/missing-companion`; a program the
            // workspace lacks is `schema/no-such-name`. Both are said where they
            // are typed, so nothing is added here.
            let Some(listed) = then.get("may-go-to").and_then(Node::as_list) else {
                continue;
            };
            let Some(program) = programs.and_then(|p| p.get(program_name)) else {
                continue;
            };
            let allowed: Vec<&str> = listed
                .iter()
                .filter_map(Node::as_str)
                .map(str::trim)
                .chain(["done"])
                .collect();
            let answers = program.node.get("answers-with").and_then(Node::as_map);
            let lines: Vec<(&String, Vec<String>)> = answers
                .into_iter()
                .flatten()
                .filter_map(|(field, e)| {
                    let written = e.node.as_str()?;
                    match shape::parse(written, &vocabulary, &named).ok()?.shape {
                        Shape::OneOf(choices) => Some((field, choices)),
                        _ => None,
                    }
                })
                .collect();
            let want = listed
                .iter()
                .filter_map(Node::as_str)
                .map(str::trim)
                .collect::<Vec<_>>()
                .join(", ");
            let at = decider.span.clone();
            match lines.as_slice() {
                [] => diags.push(Diagnostic::error(
                    "loader/a-program-may-pick-a-stage-not-listed",
                    at,
                    format!(
                        "'{loop_name}/{stage_name}' lets '{program_name}' say where the run \
                         goes next, and '{program_name}' answers with no `one of` line — so it \
                         can name any stage, and the `may-go-to:` list beside it is a hope \
                         rather than something this tree can be checked against."
                    ),
                    format!(
                        "Give '{program_name}' one answer line that is the choice itself: \
                         `next: one of {want}`."
                    ),
                )),
                [(field, choices)] => {
                    let off: Vec<&String> = choices
                        .iter()
                        .filter(|c| !allowed.contains(&c.as_str()))
                        .collect();
                    if !off.is_empty() {
                        let off_list = off
                            .iter()
                            .map(|c| format!("'{c}'"))
                            .collect::<Vec<_>>()
                            .join(", ");
                        diags.push(Diagnostic::error(
                            "loader/a-program-may-pick-a-stage-not-listed",
                            at,
                            format!(
                                "'{loop_name}/{stage_name}' lets '{program_name}' pick the \
                                 next stage, and its `{field}` may answer {off_list}, which \
                                 `may-go-to:` does not list."
                            ),
                            format!(
                                "Add {off_list} to `may-go-to:`, or take them out of \
                                 '{program_name}'s `{field}: one of ...` line."
                            ),
                        ));
                    }
                }
                _ => diags.push(Diagnostic::error(
                    "loader/a-program-may-pick-a-stage-not-listed",
                    at,
                    format!(
                        "'{loop_name}/{stage_name}' lets '{program_name}' pick the next stage, \
                         and '{program_name}' answers with more than one `one of` line, so \
                         which of them is the stage cannot be read from this tree."
                    ),
                    format!(
                        "Keep one `one of` line in '{program_name}'s `answers-with:`, naming \
                         stages from: {want}."
                    ),
                )),
            }
        }
    }
}

/// A loop stage's `may-use:` — and a variant's — only narrows: every name has
/// to be one the agent running it already `uses:` or has on its `team:`.
///
/// The agent side is what `Loop.check_against` holds at run time
/// (`adapters/python/src/pact_adapters/harness.py:1045`: the tools the agent
/// uses, its team, its skills). A loop is named by an agent's `loop:` line, so
/// the check is per agent: the same loop may be fine for one and not another.
fn a_stage_narrows_only_what_the_agent_has(root: &Node, diags: &mut Diagnostics) {
    let Some(agents) = root.get("agents").and_then(Node::as_map) else {
        return;
    };
    let loops = root.get("loops").and_then(Node::as_map);
    for (agent_name, agent) in agents {
        let has: Vec<&str> = list_of(agent.node.get("uses"))
            .into_iter()
            .chain(
                agent
                    .node
                    .get("team")
                    .and_then(Node::as_map)
                    .into_iter()
                    .flat_map(|m| m.keys().map(String::as_str)),
            )
            .collect();
        // A base agent is never put to work, and one with no `uses:` and no
        // team has nothing to narrow; a `may-use:` there is its own mistake.
        if crate::teams::says_yes(agent.node.get("base")) {
            continue;
        }
        if let Some(variants) = agent.node.get("variants").and_then(Node::as_map) {
            for (variant_name, variant) in variants {
                refuse_wider(
                    &format!("the variant '{variant_name}' of '{agent_name}'"),
                    agent_name,
                    variant.node.get("may-use"),
                    &has,
                    diags,
                );
            }
        }
        let Some(loop_name) = agent.node.get("loop").and_then(Node::as_str) else {
            continue;
        };
        let Some(steps) = loops
            .and_then(|l| l.get(loop_name.trim()))
            .and_then(|l| l.node.get("steps"))
            .and_then(Node::as_map)
        else {
            continue;
        };
        for (stage_name, stage) in steps {
            refuse_wider(
                &format!("'{loop_name}/{stage_name}', run by '{agent_name}',"),
                agent_name,
                stage.node.get("may-use"),
                &has,
                diags,
            );
        }
    }
}

fn refuse_wider(
    who: &str,
    agent_name: &str,
    may_use: Option<&Node>,
    has: &[&str],
    diags: &mut Diagnostics,
) {
    let Some(listed) = may_use.and_then(Node::as_list) else {
        return;
    };
    for wanted in listed {
        let Some(name) = wanted.as_str().map(str::trim) else {
            continue;
        };
        if has.contains(&name) {
            continue;
        }
        let it_has = if has.is_empty() {
            "nothing on `uses:` and no team".to_string()
        } else {
            has.join(", ")
        };
        diags.push(Diagnostic::error(
            "loader/a-stage-may-use-what-the-agent-cannot",
            wanted.span.clone(),
            format!(
                "{who} may use '{name}', which '{agent_name}' does not have. A `may-use:` \
                 line only narrows what the agent was given; it cannot add to it. \
                 '{agent_name}' has: {it_has}."
            ),
            format!("Add '{name}' to '{agent_name}'s `uses:`, or take it out of this `may-use:`."),
        ));
    }
}

fn list_of(node: Option<&Node>) -> Vec<&str> {
    node.and_then(Node::as_list)
        .into_iter()
        .flatten()
        .filter_map(Node::as_str)
        .map(str::trim)
        .collect()
}
