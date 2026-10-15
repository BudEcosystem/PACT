//! **Code the model writes, held to what it may call** (02P §8.1, 02W §2.16).
//!
//! R16, narrowed: a `run-code` stage's code may call, as functions, the tools,
//! teammates and workflows its `may-use:` names. Code cannot stop and wait —
//! the room has no way to hold a call open for a person and come back — so
//! one rule and one tidy-up live here:
//!
//! | Rule | ID | Fires when |
//! |---|---|---|
//! | `loader/code-calls-what-can-wait` | WF-33, second case | a `run-code` stage's `may-use:` names an agent, a workflow or a program that can stop and wait |
//! | `loader/a-line-this-stage-never-reads` | WF-3 | `fuel:` beside a stage that runs no code (a loop's other stages, any workflow stage) |
//!
//! `fuel:` itself is required on `run-code` by the schema (`needed-when:` on
//! `stage.does`, A3), and WF-33's first case (`may-start:` without its two
//! ceilings) is `teamwork.rs`'s.
//!
//! **What "can wait" means** is read off the document and nothing else, and it
//! errs towards waiting: a call refused here that would never have waited is a
//! line to move; a call let through that waits is a run that fails. An agent
//! can wait when anything it is written with can put a run on hold — every
//! wait `pact waits` lists for it (`report::asking_lines`: an approval, a
//! consent, a budget or a tidying park, a stage that asks someone), any other
//! `ask-a-person` or `ask-someone` it or its loop writes, `may-start:` (an
//! agent it brings in is anyone), its memory held for review (`learning.yaml`),
//! a program it reaches whose fuel asks a person, a teammate or a workflow that
//! can wait, and an agent reached over A2A (which may ask back). A workflow can
//! wait when it parks itself (a stage that asks someone, a failure plan that
//! asks or undoes, a back-off, a new version waited for), waits its turn
//! (`at-once-at-most:`), is answered through a port, calls or asks an agent,
//! calls an action a person must approve, or calls a workflow that can wait —
//! the same reading Bud Agent Flow makes before running one inline. A program
//! (or a tool whose action runs one) can wait when its fuel asks a person. And
//! any teammate can wait for the agent whose `teamwork:` says
//! `if-someone-fails: ask-a-person`: a member that fails parks its caller.

use std::collections::BTreeSet;

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node};

use crate::workflows::{Kind, Resolved, does, resolve};

/// The stage kind that writes its own code, as `phase.does` spells it.
const RUN_CODE: &str = "run-code";
/// The lines of a workflow that can put its run on hold (02W §2.7-§2.9).
const WORKFLOW_PARKS: &[&str] = &["asks", "undo", "gives-up-after", "new-version-of"];
/// The values that hand a run to a person, or undo what it did.
const PARKING_WORDS: &[&str] = &["ask-a-person", "ask-someone", "undo"];
/// `learning.yaml`'s settings that hold a model's own changes for a person.
const REVIEWED: &[&str] = &["propose-only", "applies-safe-changes-itself"];

/// Hold every `run-code` stage's `may-use:` to callees that never wait, and say
/// where a `fuel:` line is never read.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    for (loop_name, shape) in document
        .get("loops")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let Some(steps) = shape.node.get("steps").and_then(Node::as_map) else {
            continue;
        };
        let asks_about_failures = asks_about_failures(document, loop_name);
        for (stage, entry) in steps {
            let did = does(&entry.node).unwrap_or("");
            if did != RUN_CODE {
                fuel_never_read(
                    &format!("'{loop_name}/{stage}' does `{did}`"),
                    &entry.node,
                    diags,
                );
                continue;
            }
            for named in entry.node.get("may-use").map(names).unwrap_or_default() {
                let Some(name) = named.as_str().map(str::trim) else {
                    continue;
                };
                let caller = asks_about_failures
                    .iter()
                    .find(|(_, team)| team.contains(&name));
                let why = caller
                    .map(|(agent, _)| {
                        format!(
                            "'{agent}', whose loop this is, asks a person when a teammate fails \
                             (`teamwork: if-someone-fails: ask-a-person`)"
                        )
                    })
                    .or_else(|| waits(document, name, &mut BTreeSet::new()));
                if let Some(why) = why {
                    diags.push(code_calls_what_can_wait(
                        loop_name, stage, name, &why, named,
                    ));
                }
            }
        }
    }
    for (flow, entry) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        for (stage, node) in crate::waits::every_stage(&entry.node) {
            if does(node) != Some(RUN_CODE) {
                // A workflow's `run-code` is WF-2's to refuse; one mistake, one message.
                fuel_never_read(
                    &format!("'{flow}/{stage}', a workflow's stage,"),
                    node,
                    diags,
                );
            }
        }
    }
}

/// Each agent whose loop is `loop_name` and whose `teamwork:` asks a person when
/// a teammate fails, with its team: a member that fails parks its caller.
fn asks_about_failures<'d>(document: &'d Node, loop_name: &str) -> Vec<(&'d str, Vec<&'d str>)> {
    document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .filter(|(_, a)| {
            a.node.get("loop").and_then(Node::as_str).map(str::trim) == Some(loop_name)
        })
        .filter(|(_, a)| {
            a.node
                .get("teamwork")
                .and_then(|t| t.get("if-someone-fails"))
                .and_then(Node::as_str)
                .is_some_and(|w| w.trim() == "ask-a-person")
        })
        .map(|(name, a)| {
            let team = a
                .node
                .get("team")
                .and_then(Node::as_map)
                .into_iter()
                .flatten();
            (name.as_str(), team.map(|(m, _)| m.as_str()).collect())
        })
        .collect()
}

fn code_calls_what_can_wait(
    loop_name: &str,
    stage: &str,
    name: &str,
    why: &str,
    at: &Node,
) -> Diagnostic {
    Diagnostic::error(
        "loader/code-calls-what-can-wait",
        at.span.clone(),
        format!(
            "'{loop_name}/{stage}' runs code that may call '{name}', and '{name}' can stop \
             and wait: {why}. Code cannot stop and wait for anyone, so the call would fail \
             inside it instead."
        ),
        format!(
            "Take '{name}' out of this stage's `may-use:` and let the model call it from a \
             stage of its own turn (`does: use-tools`), where a call that waits is held for \
             the person; or take away what makes '{name}' wait."
        ),
    )
}

fn fuel_never_read(what: &str, stage: &Node, diags: &mut Diagnostics) {
    let Some(entry) = stage.as_map().and_then(|m: &Map| m.get("fuel")) else {
        return;
    };
    diags.push(Diagnostic::error(
        "loader/a-line-this-stage-never-reads",
        entry.key_span.clone(),
        format!(
            "{what} and writes `fuel:`, which only a stage that does `run-code` reads, so \
             nothing ever reads this line."
        ),
        "Delete it. `fuel:` says how long and how much the code a `run-code` stage writes \
         may run, and this stage runs no code."
            .to_string(),
    ));
}

/// Why a run of `name` (an agent, a workflow, a program or a tool running one
/// whose fuel asks a person, or a tool reaching an agent over A2A) can stop and
/// wait, or `None` when it never can or is none of those.
/// `seen` stops a circle, which is another rule's to refuse.
fn waits(document: &Node, name: &str, seen: &mut BTreeSet<String>) -> Option<String> {
    if !seen.insert(name.to_string()) {
        return None;
    }
    if let Some(agent) = entry(document, "agents", name) {
        return agent_waits(document, agent, seen);
    }
    if let Some(flow) = entry(document, "workflows", name) {
        return workflow_waits(document, name, flow, seen);
    }
    if let Some(program) = asks_for_more_fuel(document, name) {
        return Some(format!(
            "its program '{program}' asks a person when it runs out of fuel"
        ));
    }
    let server = entry(document, "tools", name)?
        .get("connect")?
        .as_str()?
        .trim();
    let kind = entry(document, "resources", server)?
        .get("resource-kind")?
        .as_str()?;
    (kind.trim() == crate::remote::A2A_AGENT)
        .then(|| format!("it is an agent reached over A2A ('{server}'), which may ask back"))
}

fn agent_waits(document: &Node, agent: &Node, seen: &mut BTreeSet<String>) -> Option<String> {
    if let Some((reason, question, ..)) = crate::report::asking_lines(document, agent).first() {
        return Some(format!("it can stop to ask '{question}' ({reason})"));
    }
    let own = [Some(agent), named_in(document, "loops", agent, "loop")];
    let context = named_in(document, "context-policies", agent, "context-policy");
    if own
        .iter()
        .chain([&context])
        .flatten()
        .any(|n| parks(n, &[]))
    {
        return Some("it can hand its run to a person (`ask-a-person` or `ask-someone`)".into());
    }
    if agent
        .get("teamwork")
        .and_then(|t| t.get("may-start"))
        .and_then(Node::as_list)
        .is_some_and(|l| !l.is_empty())
    {
        return Some(
            "it may bring agents in while it runs (`may-start:`), and any of them may wait".into(),
        );
    }
    if (agent.get("remembers").is_some() || document.get("remembers").is_some())
        && document
            .get("learning")
            .and_then(|l| l.get("enabled"))
            .and_then(Node::as_str)
            .is_some_and(|e| REVIEWED.contains(&e.trim()))
    {
        return Some("what it remembers is held for a person's review (`learning.yaml`)".into());
    }
    for member in agent
        .get("team")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .map(|(m, _)| m)
    {
        if let Some(why) = waits(document, member, seen) {
            return Some(format!("its teammate '{member}' can wait, because {why}"));
        }
    }
    for used in agent.get("uses").map(names).unwrap_or_default() {
        let Some(used) = used.as_str().map(str::trim) else {
            continue;
        };
        if entry(document, "agents", used).is_none()
            && let Some(why) = waits(document, used, seen)
        {
            return Some(format!("it uses '{used}', and {why}"));
        }
    }
    None
}

fn workflow_waits(
    document: &Node,
    name: &str,
    flow: &Node,
    seen: &mut BTreeSet<String>,
) -> Option<String> {
    if parks(flow, WORKFLOW_PARKS) {
        return Some("it has a stage that can put its run on hold for a person or a time".into());
    }
    if flow
        .get("limits")
        .and_then(|l| l.get("at-once-at-most"))
        .is_some()
    {
        return Some("a run of it may wait its turn (`at-once-at-most:`)".into());
    }
    let door = document
        .get("ports")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .find(|(_, p)| p.node.get("answers").and_then(Node::as_str).map(str::trim) == Some(name));
    if let Some((port, _)) = door {
        return Some(format!("a call to it goes through the port '{port}'"));
    }
    for (stage, node) in crate::waits::every_stage(flow) {
        if node
            .get("by")
            .map(names)
            .unwrap_or_default()
            .iter()
            .any(|r| r.get("agent").is_some())
        {
            return Some(format!("its stage '{stage}' asks an agent to decide"));
        }
        let mut targets: Vec<&str> = node
            .get("call")
            .and_then(Node::as_str)
            .into_iter()
            .collect();
        targets.extend(
            node.get("may-call")
                .map(names)
                .unwrap_or_default()
                .iter()
                .filter_map(|n| n.as_str()),
        );
        for target in targets.into_iter().map(str::trim) {
            if let Some(why) = a_call_waits(document, target, seen) {
                return Some(format!("its stage '{stage}' calls '{target}', and {why}"));
            }
        }
    }
    None
}

/// Why a workflow's call of `target` can wait: any agent (its run is a model's,
/// and may wait), an action a person must approve, or a workflow that can wait.
fn a_call_waits(document: &Node, target: &str, seen: &mut BTreeSet<String>) -> Option<String> {
    match resolve(document, target) {
        Resolved::One(Kind::Agent) => Some("an agent's run can wait".into()),
        Resolved::One(Kind::Workflow) => waits(document, target, seen),
        Resolved::One(Kind::Program) => asks_for_more_fuel(document, target)
            .map(|_| "its fuel asks a person when it runs out".into()),
        Resolved::One(Kind::Action) => {
            let (tool, action) = target.split_once('/')?;
            let entry = entry(document, "tools", tool)?;
            let asked = entry
                .get("actions")
                .and_then(|a| a.get(action))
                .is_some_and(crate::approvals::asked_for)
                || ruled_on(document, target)
                || entry
                    .get("connect")
                    .and_then(Node::as_str)
                    .and_then(|s| self::entry(document, "resources", s.trim()))
                    .is_some_and(|r| {
                        r.get("asks-to-connect").is_some() || r.get("asks-to-run").is_some()
                    });
            asked.then(|| "a person may have to say yes first".into())
        }
        _ => None,
    }
}

/// Whether an approval rule of any policy names `<tool>/<action>`.
fn ruled_on(document: &Node, target: &str) -> bool {
    let policies = document
        .get("policies")
        .and_then(Node::as_map)
        .into_iter()
        .flatten();
    policies
        .flat_map(|(_, p)| p.node.get("ask-a-person").map(names).unwrap_or_default())
        .flat_map(|rule| rule.get("when").map(names).unwrap_or_default())
        .any(|when| when.get("tool").and_then(Node::as_str).map(str::trim) == Some(target))
}

/// The program `used` reaches (itself, or one a room's action runs) whose fuel
/// asks a person when it runs out.
fn asks_for_more_fuel<'d>(document: &'d Node, used: &'d str) -> Option<&'d str> {
    let mut programs: Vec<&str> = vec![used];
    if let Some(actions) = entry(document, "tools", used)
        .and_then(|t| t.get("actions"))
        .and_then(Node::as_map)
    {
        programs.extend(
            actions
                .values()
                .filter_map(|a| a.node.get("program")?.as_str())
                .map(str::trim),
        );
    }
    programs.into_iter().find(|p| {
        entry(document, "programs", p)
            .and_then(|p| p.get("fuel"))
            .and_then(|f| f.get("when-it-runs-out"))
            .and_then(Node::as_str)
            .is_some_and(|w| w.trim() == "ask-a-person")
    })
}

/// Whether `node` writes a line that parks a run: one of `keys`, or a value
/// that hands the run to a person, at any depth.
fn parks(node: &Node, keys: &[&str]) -> bool {
    if let Some(text) = node.as_str() {
        return PARKING_WORDS.contains(&text.trim());
    }
    if let Some(items) = node.as_list() {
        return items.iter().any(|n| parks(n, keys));
    }
    node.as_map()
        .into_iter()
        .flatten()
        .any(|(k, e)| keys.contains(&k.as_str()) || parks(&e.node, keys))
}

fn entry<'d>(document: &'d Node, collection: &str, name: &str) -> Option<&'d Node> {
    document.get(collection)?.get(name)
}

fn named_in<'d>(
    document: &'d Node,
    collection: &str,
    owner: &Node,
    field: &str,
) -> Option<&'d Node> {
    entry(document, collection, owner.get(field)?.as_str()?.trim())
}

/// A list's items, or the one item a single-item spelling writes.
fn names(node: &Node) -> Vec<&Node> {
    node.as_list()
        .map_or_else(|| vec![node], |l| l.iter().collect())
}
