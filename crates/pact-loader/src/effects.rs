//! **What a part does to the world, computed and never declared** (law 1 of
//! `docs/97-PRIMITIVES.md`; `docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-2).
//!
//! The words are the schema's own (`action.undone-by`'s help): an action
//! *looks things up* (`reads-only: yes`), *changes* something it can undo
//! (`undone-by:`), or *can't be undone* (a write with no `undone-by:`, "and so
//! is any action that says nothing"). Moving money is a separate fact, because a
//! payment with a refund action is undoable and still moves money.
//!
//! An agent, a team, a workflow and a stage have no line for this, and that is
//! the law: their effect is the worst of everything they can reach, worked out
//! here. A workflow that pays money is never "read-only" because somebody
//! forgot to say otherwise; there is nothing to forget.
//!
//! Consumers: `pact discover` prints each agent's and workflow's effect, the
//! exactly-once rules (law 3) ask whether a repeated part can't be undone or
//! moves money, and `when-this.effect:` lets a policy gate on the class.

use std::collections::BTreeSet;

use pact_doc::{Map, Node};

use crate::workflows::{entry_in, list, said_yes};

/// How hard what a part does is to take back. Ordered: a part is as bad as the
/// worst thing it can reach.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Level {
    /// Nothing at all: a program, a skill, a set of documents.
    Nothing,
    /// Only looks things up.
    Reads,
    /// Changes something, and says how to change it back.
    Changes,
    /// Changes something with no way back written down.
    CannotBeUndone,
}

/// A part's computed effect.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Effect {
    pub level: Level,
    pub moves_money: bool,
}

impl Effect {
    pub const NOTHING: Effect = Effect {
        level: Level::Nothing,
        moves_money: false,
    };

    /// The worse of two.
    #[must_use]
    pub fn and(self, other: Effect) -> Effect {
        Effect {
            level: self.level.max(other.level),
            moves_money: self.moves_money || other.moves_money,
        }
    }

    /// The word printed and matched: `reads`, `writes`, `cannot-be-undone`
    /// (and `nothing`). Money is printed beside it, as its own fact.
    #[must_use]
    pub fn word(self) -> &'static str {
        match self.level {
            Level::Nothing => "nothing",
            Level::Reads => "reads",
            Level::Changes => "writes",
            Level::CannotBeUndone => "cannot-be-undone",
        }
    }

    /// Whether `effect:` in a `when-this` holds of this part: `reads`, `writes`,
    /// `spends` and `cannot-be-undone` each name the least the part must do.
    /// `writes` holds of anything that changes something, undoable or not.
    #[must_use]
    pub fn is(self, word: &str) -> bool {
        match word.trim() {
            "reads" => self.level == Level::Reads,
            "writes" => self.level >= Level::Changes,
            "cannot-be-undone" => self.level == Level::CannotBeUndone,
            "spends" => self.moves_money,
            _ => false,
        }
    }
}

/// One tool action's effect, from its own lines.
#[must_use]
pub fn of_action(action: &Node) -> Effect {
    let money = action.get("spends-money").is_some_and(said_yes);
    let level = if action.get("reads-only").is_some_and(said_yes) {
        Level::Reads
    } else if action.get("undone-by").is_some() {
        Level::Changes
    } else {
        Level::CannotBeUndone
    };
    Effect {
        level,
        moves_money: money,
    }
}

/// The effect of naming `target` anywhere a part may be asked: `<tool>/<action>`,
/// a whole tool (its worst action), an agent (what it uses and its team), a
/// workflow (its stages), a program, a skill or a set of documents (nothing).
/// `seen` ends a circle; a part already being followed adds nothing.
#[must_use]
pub fn of(document: &Node, target: &str, seen: &mut BTreeSet<String>) -> Effect {
    let target = target.trim();
    if let Some((tool, action)) = target.split_once('/') {
        return entry_in(document, "tools", tool)
            .and_then(|t| t.get("actions"))
            .and_then(|a| a.get(action))
            .map_or(Effect::NOTHING, of_action);
    }
    if let Some(tool) = entry_in(document, "tools", target) {
        return tool
            .get("actions")
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
            .fold(Effect::NOTHING, |e, (_, a)| e.and(of_action(&a.node)));
    }
    if !seen.insert(target.to_string()) {
        return Effect::NOTHING;
    }
    if let Some(workflow) = entry_in(document, "workflows", target) {
        return workflow
            .get("steps")
            .and_then(Node::as_map)
            .map_or(Effect::NOTHING, |s| of_steps(document, s, seen));
    }
    if let Some(agent) = entry_in(document, "agents", target) {
        return of_agent(document, agent, seen);
    }
    Effect::NOTHING
}

/// An agent: everything on `uses:`, everyone on `team:`, and every interface
/// a plugin it is loaded with implements. The last is law 1 for code PACT
/// never reads: the plugin is in the agent's runtime whether or not the agent
/// names the interface, so the agent is never reported lighter than it.
#[must_use]
pub fn of_agent(document: &Node, agent: &Node, seen: &mut BTreeSet<String>) -> Effect {
    let used: Vec<String> = agent
        .get("uses")
        .map(list)
        .unwrap_or_default()
        .into_iter()
        .filter_map(Node::as_str)
        .map(|s| s.trim().to_string())
        .chain(
            agent
                .get("team")
                .and_then(Node::as_map)
                .into_iter()
                .flat_map(|m| m.keys().cloned()),
        )
        .chain(
            crate::plugins::interfaces_loaded_for(document, agent)
                .into_iter()
                .map(str::to_string),
        )
        .collect();
    used.iter()
        .fold(Effect::NOTHING, |e, n| e.and(of(document, n, seen)))
}

/// Every stage of `steps`, nested ones included.
#[must_use]
pub fn of_steps(document: &Node, steps: &Map, seen: &mut BTreeSet<String>) -> Effect {
    steps.values().fold(Effect::NOTHING, |e, entry| {
        entry
            .node
            .as_map()
            .map_or(e, |fields| e.and(of_stage(document, fields, seen)))
    })
}

/// One stage: what it calls or may call, and the stages inside it.
#[must_use]
pub fn of_stage(document: &Node, fields: &Map, seen: &mut BTreeSet<String>) -> Effect {
    let mut effect = fields
        .get("steps")
        .and_then(|e| e.node.as_map())
        .map_or(Effect::NOTHING, |inner| of_steps(document, inner, seen));
    let mut named: Vec<&str> = fields
        .get("call")
        .and_then(|e| e.node.as_str())
        .into_iter()
        .collect();
    if let Some(may) = fields.get("may-call") {
        named.extend(list(&may.node).into_iter().filter_map(Node::as_str));
    }
    if let Some(may) = fields.get("may-use") {
        named.extend(list(&may.node).into_iter().filter_map(Node::as_str));
    }
    // A stage's own `undone-by:` is how to take back what IT called, so what it
    // calls can be undone here even when the action alone says nothing.
    let undone_here = fields.contains_key("undone-by");
    for n in named {
        let mut called = of(document, n, seen);
        if undone_here && called.level == Level::CannotBeUndone {
            called.level = Level::Changes;
        }
        effect = effect.and(called);
    }
    effect
}

/// What `pact discover` prints for a part: `{"effect": <word>, "moves-money": bool}`.
#[must_use]
pub fn to_json(effect: Effect) -> serde_json::Value {
    serde_json::json!({
        "effect": effect.word(),
        "moves-money": effect.moves_money,
    })
}
