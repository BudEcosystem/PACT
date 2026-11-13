// What a part does to the world, computed and never declared — law 1 of
// `docs/97-PRIMITIVES.md`, ported from `crates/pact-loader/src/effects.rs`.
//
// The checker computes a part's effect once, for `pact discover` and for the
// exactly-once rules. A runtime needs the same answer at run time: a policy
// line `effect: spends` in a `when-this` gates a call by what the called
// action does, and a runtime that builds agents in code (no tree, so no
// `discover`) still has to say what each of them can do. A second reading
// that guesses differently from the checker is how a payment comes to be
// treated as a lookup, so this is the checker's own reading, function for
// function: `ofAction` is `of_action`, `effectOf` is `of`, `ofAgent` is
// `of_agent`, `ofSteps` and `ofStage` are `of_steps` and `of_stage`, and
// `effectIs` is `Effect::is`.
//
// One deliberate difference: a tick is read with `saidYes` (`yes-no.ts`),
// the five words `coerce.rs::yes_no` accepts, where `workflows.rs::said_yes`
// takes three (`yes`, `true`, `on`). A document saying `reads-only: y` is one
// the checker accepted as a tick, so it reads as a lookup here; the Rust
// reading of that line is the one to change.
//
// The words are the schema's own. An action *looks things up*
// (`reads-only: yes`), *changes* something it can undo (`undone-by:`), or
// *can't be undone* (a write with no `undone-by:`, and so is any action that
// says nothing). Moving money is a separate fact: a payment with a refund
// action is undoable and still moves money.

import { saidYes } from "./yes-no.ts";

/** How hard what a part does is to take back, least first. */
export const LEVELS = ["nothing", "reads", "writes", "cannot-be-undone"] as const;

/** One level: `writes` is a change with a way back written down. */
export type Level = (typeof LEVELS)[number];

/** A part's computed effect. */
export interface Effect {
  readonly level: Level;
  readonly movesMoney: boolean;
}

/** Nothing at all: a program, a skill, a set of documents. */
export const NOTHING: Effect = { level: "nothing", movesMoney: false };

/** The worse of two effects: a part is as bad as the worst thing it can reach. */
export function worse(a: Effect, b: Effect): Effect {
  const level = LEVELS.indexOf(a.level) >= LEVELS.indexOf(b.level) ? a.level : b.level;
  return { level, movesMoney: a.movesMoney || b.movesMoney };
}

/**
 * Whether `effect:` in a `when-this` holds of this part. `reads`, `writes`,
 * `spends` and `cannot-be-undone` each name the least the part must do;
 * `writes` holds of anything that changes something, undoable or not.
 */
export function effectIs(effect: Effect, word: string): boolean {
  switch (word.trim()) {
    case "reads":
      return effect.level === "reads";
    case "writes":
      return LEVELS.indexOf(effect.level) >= LEVELS.indexOf("writes");
    case "cannot-be-undone":
      return effect.level === "cannot-be-undone";
    case "spends":
      return effect.movesMoney;
    default:
      return false;
  }
}

/** What `pact discover` prints for a part. */
export function discovered(effect: Effect): { effect: Level; "moves-money": boolean } {
  return { effect: effect.level, "moves-money": effect.movesMoney };
}

type Block = { readonly [key: string]: unknown };

function block(value: unknown): Block | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Block) : undefined;
}

/** A value written as one item or as a list of them. */
function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : value === undefined ? [] : [value];
}

function entryIn(document: unknown, collection: string, name: string): Block | undefined {
  const entries = block(block(document)?.[collection]);
  return entries !== undefined && Object.hasOwn(entries, name) ? block(entries[name]) : undefined;
}

/** One tool action's effect, from its own lines. */
export function ofAction(action: unknown): Effect {
  const line = block(action) ?? {};
  const level: Level = saidYes(line["reads-only"])
    ? "reads"
    : line["undone-by"] !== undefined ? "writes" : "cannot-be-undone";
  return { level, movesMoney: saidYes(line["spends-money"]) };
}

/**
 * The effect of naming `target` anywhere a part may be asked: `<tool>/<action>`,
 * a whole tool (its worst action), an agent (what it uses and its team), a
 * workflow (its stages), a program, a skill or a set of documents (nothing).
 * `seen` ends a circle; a part already being followed adds nothing.
 */
export function effectOf(document: unknown, target: string, seen: Set<string> = new Set()): Effect {
  const name = target.trim();
  const slash = name.indexOf("/");
  if (slash >= 0) {
    const actions = block(entryIn(document, "tools", name.slice(0, slash))?.actions);
    const action = name.slice(slash + 1);
    return actions !== undefined && Object.hasOwn(actions, action) ? ofAction(actions[action]) : NOTHING;
  }
  const tool = entryIn(document, "tools", name);
  if (tool !== undefined) {
    return Object.values(block(tool.actions) ?? {}).reduce<Effect>((effect, action) => worse(effect, ofAction(action)), NOTHING);
  }
  if (seen.has(name)) return NOTHING;
  seen.add(name);
  const workflow = entryIn(document, "workflows", name);
  if (workflow !== undefined) {
    const steps = block(workflow.steps);
    return steps === undefined ? NOTHING : ofSteps(document, steps, seen);
  }
  const agent = entryIn(document, "agents", name);
  return agent === undefined ? NOTHING : ofAgent(document, agent, seen);
}

/** An agent: everything on `uses:` and everyone on `team:`. */
export function ofAgent(document: unknown, agent: unknown, seen: Set<string> = new Set()): Effect {
  const written = block(agent) ?? {};
  const used = list(written.uses).filter((item): item is string => typeof item === "string").map((item) => item.trim());
  const team = Object.keys(block(written.team) ?? {});
  return [...used, ...team].reduce<Effect>((effect, name) => worse(effect, effectOf(document, name, seen)), NOTHING);
}

/** Every stage of `steps`, nested ones included. */
export function ofSteps(document: unknown, steps: unknown, seen: Set<string> = new Set()): Effect {
  return Object.values(block(steps) ?? {}).reduce<Effect>((effect, stage) => {
    const fields = block(stage);
    return fields === undefined ? effect : worse(effect, ofStage(document, fields, seen));
  }, NOTHING);
}

/** One stage: what it calls or may call, and the stages inside it. */
export function ofStage(document: unknown, fields: unknown, seen: Set<string> = new Set()): Effect {
  const stage = block(fields) ?? {};
  const inner = block(stage.steps);
  let effect = inner === undefined ? NOTHING : ofSteps(document, inner, seen);
  const named: string[] = [];
  if (typeof stage.call === "string") named.push(stage.call);
  for (const field of ["may-call", "may-use"]) {
    for (const item of list(stage[field])) if (typeof item === "string") named.push(item);
  }
  // A stage's own `undone-by:` is how to take back what IT called, so what it
  // calls can be undone here even when the action alone says nothing.
  const undoneHere = Object.hasOwn(stage, "undone-by");
  for (const name of named) {
    let called = effectOf(document, name, seen);
    if (undoneHere && called.level === "cannot-be-undone") called = { ...called, level: "writes" };
    effect = worse(effect, called);
  }
  return effect;
}
