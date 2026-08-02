// The loop, as an authored document rather than a constant (G1, D12) — ported
// to TypeScript.
//
// This exists twice for the reason `limits.ts` exists twice, and it is the same
// reason `harness.ts` does: a specification that only one implementation has
// ever read is indistinguishable from that implementation's behaviour. The
// stages are read here from the AUTHOR'S OWN field names — `starts-at`,
// `steps`, `does`, `then`, `may-use`, `at-most`, `says` — not from a payload the
// Python side pre-digested, so this port has to understand what `may-use:` means
// for itself. Where the two disagree, PACT is ambiguous.
//
// Eve, which runs on this runtime, has none of it. `stopWhen: isStepCount(1)` is
// the only stop condition in 171,782 lines and whether to go round again is one
// hardcoded boolean, so there is no such thing there as a step that sees fewer
// tools: a planning step reads the same tool list, and the same system prompt,
// as the step that issues the refund.
//
// **The rule that keeps this honest** (stated in `loops.py` and enforced across
// both ports): executing `pact:loop/standard` must produce exactly the trace
// this harness produced before loops existed. That is why `SAYS["use-tools"]` is
// the empty string and why a `use-tools` stage that narrows nothing offers
// everything — the default shape adds no words and takes no tools away.

export class LoopError extends Error {
  // An authoring mistake in a loop document. Raised rather than absorbed: a loop
  // that names a stage which does not exist has no defensible fallback, and
  // picking one would hide the typo (T7). Every message names the loop, the
  // stage, what is wrong and a line to type — word for word what `loops.py`
  // says, because two ports that refuse the same file and explain it
  // differently have still diverged for whoever has to fix it.
  constructor(message: string) {
    super(message);
    this.name = "LoopError";
  }
}

/** What happens in one stage. Closed — it mirrors `phase.does` in the
 *  specification, which is where the list is actually maintained. */
export type Does =
  | "think"
  | "use-tools"
  | "check-its-work"
  | "ask-someone"
  | "answer";

//: In definition order, because the diagnostics quote it in that order.
export const DOES: readonly Does[] = [
  "think", "use-tools", "check-its-work", "ask-someone", "answer",
];

/** The finish line. Reserved: a stage may not be called this. */
export const DONE = "done";

/** Everything a stage can end in. Closed: a predicate language here would be a
 *  fourth dialect for a support lead to learn (D14), and anything finer belongs
 *  in an interceptor. */
export const OUTCOMES = ["used-a-tool", "answered", "too-many-times"] as const;

/** The built-in wording for each kind of stage, appended to the agent's own
 *  instructions for that stage only. `use-tools` adds nothing at all, which is
 *  what makes `pact:loop/standard` byte-identical to having no loop. An author
 *  overrides any of these with `says:`. */
export const SAYS: Record<Does, string> = {
  "think": "Say what you plan to do, and why. Do not do any of it yet.",
  "use-tools": "",
  "check-its-work":
    "Look back at what you just said and check it against your " +
    "instructions. If something is wrong, say what is wrong. If it is " +
    "right, say so.",
  "answer": "Give your final answer now.",
  "ask-someone": "",
};

//: Stages that offer every tool the agent has when they name none. Every other
//: kind of stage offers nothing unless it names something — that asymmetry is
//: the whole reason a `think` stage thinks instead of reaching for the first
//: tool it recognises.
const OFFERS_EVERYTHING: readonly Does[] = ["use-tools"];

export type Phase = {
  name: string;
  does: Does;
  then: Record<string, string>;
  says: string;
  mayUse: string[] | null;
  atMost: number | null;
  // For a `does: ask-someone` stage, the question it puts to a person, by name.
  // Carried so the two ports agree about what the document said; this port has
  // no durable suspension to put it into (see `harness.ts`).
  asks: string;
};

export type Loop = {
  name: string;
  startsAt: string;
  steps: Record<string, Phase>;
  description: string;
};

/** The extra wording for this stage, authored or built in. */
export function instruction(p: Phase): string {
  return p.says || SAYS[p.does];
}

/** Which of the agent's tools exist in this stage.
 *
 *  Narrowing tools per stage is the cheapest accuracy win there is on a smaller
 *  model, and it is the thing Eve cannot express: its tool set is resolved once
 *  per run, so a planning step sees the payment tool. */
export function toolsOffered(p: Phase, available: readonly string[]): string[] {
  if (p.mayUse === null) {
    return OFFERS_EVERYTHING.includes(p.does) ? [...available] : [];
  }
  const keep = new Set(p.mayUse);
  return available.filter((t) => keep.has(t));
}

/** Which of the agent's written procedures this stage may read.
 *
 *  `OFFERS_EVERYTHING` deliberately does NOT apply. Withholding a tool from a
 *  `think` stage is the point; withholding the written procedure from the same
 *  stage would make it think without the rules it was told to follow. So a stage
 *  that names nothing reads every procedure the agent has, and only an explicit
 *  `may-use:` narrows it. Word for word `Phase.skills_offered` in Python. */
export function skillsOffered(p: Phase, available: readonly string[]): string[] {
  if (p.mayUse === null) return [...available];
  const keep = new Set(p.mayUse);
  return available.filter((s) => keep.has(s));
}

/** One written procedure as the model reads it — `ir.SkillSpec.in_words`. */
export function skillInWords(s: {
  name: string;
  description?: string;
  "use-when"?: string;
  "do-not-use-when"?: string;
  "if-unsure"?: string;
  content?: string;
}): string {
  const out = [`### ${s.name}`];
  if (s.description) out.push(s.description);
  if (s["use-when"]) out.push(`Use this when: ${s["use-when"]}`);
  if (s["do-not-use-when"]) out.push(`Do not use this when: ${s["do-not-use-when"]}`);
  if (s["if-unsure"]) out.push(`If you are unsure: ${s["if-unsure"]}`);
  if (s.content) out.push(s.content);
  return out.join("\n\n");
}

/** The system text for one stage.
 *
 *  The agent's own instructions stay first and unchanged: a stage adds to what
 *  the agent is, it does not replace it. Then the written procedures this stage
 *  may read, last and under a heading of their own — `harness._system_for`. */
export function answerShapeInWords(shape: Readonly<Record<string, string>>): string {
  const lines = Object.entries(shape)
    .map(([name, says]) => `- ${name}: ${says}`)
    .join("\n");
  return (
    "## What your answer must contain\n\n" +
    "End your reply with each of these, one per line, using exactly these " +
    "names:\n\n" +
    lines
  );
}

export function systemFor(
  instructions: string,
  p: Phase,
  skills: readonly Parameters<typeof skillInWords>[0][] = [],
  answersWith: Readonly<Record<string, string>> = {},
): string {
  const stage = instruction(p);
  const parts = [instructions, stage].filter((x) => x);
  if (skills.length > 0) {
    parts.push(
      "## The written procedures you follow\n\n" +
        "These are the rules of this work. Follow them exactly, and quote " +
        "them when they decide something.\n\n" +
        skills.map(skillInWords).join("\n\n"),
    );
  }
  // Last, after the procedures — `harness._answer_shape_in_words` explains why,
  // and the two must agree word for word or `test_portability.py` fails: the
  // reference port and this one send the same system text or they are not the
  // same agent.
  if (Object.keys(answersWith).length > 0) parts.push(answerShapeInWords(answersWith));
  return parts.join("\n\n");
}

export function phaseOf(l: Loop, name: string): Phase {
  const found = Object.hasOwn(l.steps, name) ? l.steps[name] : undefined;
  if (found === undefined) {
    throw new LoopError(
      `loop ${q(l.name)} has no stage called ${q(name)}. ` +
        `Its stages are: ${sorted(Object.keys(l.steps)).join(", ")}. ` +
        `Fix: change the name to one of those, or add a ` +
        `\`${name}:\` stage under \`steps:\`.`,
    );
  }
  return found;
}

/** Where a stage goes next, given how it ended.
 *
 *  `answered` with nowhere to go means finished — the one outcome with an
 *  unarguable terminal reading. `used-a-tool` with nowhere to go stops the run
 *  and says which line to add, because silently finishing there would hide a
 *  typo in `then:`. */
export function route(l: Loop, phase: Phase, outcome: string): string {
  const target = phase.then[outcome];
  if (target !== undefined) return target;
  if (outcome === "answered") return DONE;
  throw new LoopError(
    `stage ${q(phase.name)} of loop ${q(l.name)} ended with ` +
      `${q(outcome)} and does not say where to go. ` +
      `Fix: add a line under that stage's \`then:\` — ` +
      `\`${outcome}: ${DONE}\` to finish there, or the name of another stage.`,
  );
}

/** Every stage must name tools the agent actually has.
 *
 *  Checked before the first model call rather than when the stage is first
 *  entered, so a typo in a rarely-taken branch fails at the start of the run
 *  instead of forty steps in. */
export function checkAgainst(l: Loop, toolNames: readonly string[]): void {
  const have = new Set(toolNames);
  for (const phase of Object.values(l.steps)) {
    for (const wanted of phase.mayUse ?? []) {
      if (!have.has(wanted)) {
        throw new LoopError(
          `stage ${q(phase.name)} of loop ${q(l.name)} may use ` +
            `${q(wanted)}, which this agent does not have. ` +
            `It has: ${sorted([...have]).join(", ") || "no tools"}. ` +
            `Fix: add \`${wanted}\` to the agent's \`uses:\` list, or ` +
            `remove it from \`may-use:\` in that stage.`,
        );
      }
    }
  }
}

/** Which stage runs now — or why none does.
 *
 *  A stage whose `at-most` is already spent is routed *past* here rather than
 *  entered and then refused: entering it would spend a model call to discover a
 *  limit the author had already declared. Routing follows the stage's own
 *  `then: too-many-times:` line, falling back to `answered:` for a stage that
 *  wrote no `too-many-times:` — which is what `careful.yaml` relies on.
 *
 *  Returns `[phase, null]` for the stage to run, `[null, null]` when the loop
 *  has reached `done`, and `[null, why]` when every route out is also spent. */
export function stageToRun(
  l: Loop,
  name: string,
  visits: Record<string, number>,
): [Phase | null, string | null] {
  const seen: string[] = [];
  while (name !== DONE) {
    const phase = phaseOf(l, name);
    if (phase.atMost === null || (visits[name] ?? 0) < phase.atMost) {
      return [phase, null];
    }
    if (seen.includes(name)) {
      const ring = [...seen.slice(seen.indexOf(name)), name];
      return [
        null,
        `every stage in ${ring.join(" → ")} has used up its \`at-most\`, ` +
          `and they lead only to each other. ` +
          `Fix: raise one of those \`at-most:\` numbers, or point one ` +
          `stage's \`then:\` at \`done\`.`,
      ];
    }
    seen.push(name);
    name = phase.then["too-many-times"] || route(l, phase, "answered");
  }
  return [null, null];
}

// ------------------------------------------------------------- from the file

/** Build a loop from the document shape — `steps`, `starts-at`, `based-on`.
 *
 *  This is the only path in, and the shipped shapes take it too. A library shape
 *  that loaded through privileged code would not be a shape an author can fork,
 *  which is exactly the objection to Eve's compiled manifest. */
export function loopFrom(name: string, raw: unknown): Loop {
  if (!isMapping(raw)) {
    throw new LoopError(
      `loop ${q(name)} should be a set of settings, not ` +
        `${kindOf(raw)}. Fix: write it as \`starts-at:\` and ` +
        `\`steps:\` lines.`,
    );
  }

  const base = raw["based-on"];
  let stepsRaw: Record<string, unknown> = {};
  let startsAt = "";
  let description = "";
  if (typeof base === "string" && base.trim()) {
    const parent = fromLibrary(base.trim(), name);
    for (const p of Object.values(parent.steps)) stepsRaw[p.name] = phaseToMapping(p);
    startsAt = parent.startsAt;
    description = parent.description;
  }

  // A stage written here replaces the ready-made one of the same name outright.
  // Merging field-by-field would mean an author who deletes `may-use:` from
  // their copy still gets the inherited one, which is the kind of invisible
  // inheritance the Expansion Rule exists to avoid.
  const written = raw["steps"];
  if (written !== undefined && written !== null && !isMapping(written)) {
    throw new LoopError(
      `loop ${q(name)} writes its stages as ${kindOf(written)} ` +
        `and they should be a set of settings — one named stage per ` +
        `line. Fix: write \`steps:\` with a \`<name>:\` line under it for ` +
        `each stage, not a list.`,
    );
  }
  for (const [key, value] of Object.entries(isMapping(written) ? written : {})) {
    stepsRaw[key] = value;
  }

  startsAt = String(raw["starts-at"] || startsAt || "").trim();
  description = String(raw["description"] || description || "").trim();

  if (Object.keys(stepsRaw).length === 0) {
    throw new LoopError(
      `loop ${q(name)} has no stages, so there is nothing to run. ` +
        `Fix: add a \`steps:\` section, or point at a ready-made shape ` +
        `with \`based-on: ${STANDARD}\`.`,
    );
  }

  // No prototype, so `constructor`, `toString` and every other inherited
  // property is simply not there. A stage named one of them used to pass
  // validation through the chain and then crash with a raw TypeError —
  // `Cannot read properties of undefined` — where `loops.py` produces the
  // diagnostic naming the stage and listing the real ones.
  const steps: Record<string, Phase> = Object.create(null);
  for (const [key, value] of Object.entries(stepsRaw)) {
    steps[key] = readPhase(name, key, value);
  }

  if (Object.hasOwn(steps, DONE)) {
    throw new LoopError(
      `loop ${q(name)} has a stage called ${q(DONE)}, which is the name ` +
        `of the finish line. Fix: rename that stage to something else.`,
    );
  }

  if (!startsAt) {
    throw new LoopError(
      `loop ${q(name)} does not say which stage runs first. ` +
        `Fix: add a line \`starts-at: ${sorted(Object.keys(steps))[0]}\`.`,
    );
  }
  if (!Object.hasOwn(steps, startsAt)) {
    throw new LoopError(
      `loop ${q(name)} starts at ${q(startsAt)}, but it has no stage ` +
        `called that. Its stages are: ${sorted(Object.keys(steps)).join(", ")}. ` +
        `Fix: change \`starts-at:\` to one of those.`,
    );
  }

  for (const phase of Object.values(steps)) {
    for (const [outcome, target] of Object.entries(phase.then)) {
      if (!(OUTCOMES as readonly string[]).includes(outcome)) {
        throw new LoopError(
          `stage ${q(phase.name)} of loop ${q(name)} routes on ` +
            `${q(outcome)}, which is not something a stage can end ` +
            `in. Fix: use one of: ${OUTCOMES.join(", ")}.`,
        );
      }
      if (target !== DONE && !Object.hasOwn(steps, target)) {
        throw new LoopError(
          `stage ${q(phase.name)} of loop ${q(name)} sends ` +
            `${q(outcome)} to ${q(target)}, which is not a stage. ` +
            `Its stages are: ${sorted(Object.keys(steps)).join(", ")}, plus ` +
            `${q(DONE)} to finish. Fix: change it to one of those.`,
        );
      }
    }
  }

  return { name, startsAt, steps, description };
}

/** Resolve `pact:loop/<name>` against the shapes PACT ships. */
export function fromLibrary(ref: string, askedBy = ""): Loop {
  const key = ref.trim();
  const shape = Object.hasOwn(LIBRARY, key) ? LIBRARY[key] : undefined;
  if (shape === undefined) {
    const where = askedBy ? ` (asked for by loop ${q(askedBy)})` : "";
    throw new LoopError(
      `there is no ready-made shape called ${q(key)}${where}. ` +
        `PACT ships: ${sorted(Object.keys(LIBRARY)).join(", ")}. ` +
        `Fix: use one of those, or write your own in \`loops/\` and ` +
        `name it there.`,
    );
  }
  return loopFrom(key, shape);
}

/** Find the loop an agent named: a shipped shape, or one in this workspace.
 *
 *  Takes the workspace's whole `loops:` block rather than a pre-selected
 *  document, so this port makes the same choice the Python one does from the
 *  same two facts — the agent's `loop:` line and what the workspace declares. */
export function resolve(
  loops: Record<string, unknown> | undefined,
  ref: string,
): Loop {
  const key = (ref || "").trim();
  if (!key) return fromLibrary(STANDARD);
  if (key.startsWith("pact:loop/")) return fromLibrary(key);
  const declared = loops ?? {};
  if (Object.hasOwn(declared, key)) return loopFrom(key, declared[key]);
  const known = sorted(Object.keys(declared)).join(", ") || "none";
  throw new LoopError(
    `no loop called ${q(key)}. This workspace declares: ${known}. ` +
      `Fix: write \`loop: ${STANDARD}\`, or add a file ` +
      `\`loops/${key}.yaml\` describing the stages.`,
  );
}

function readPhase(loopName: string, key: string, raw: unknown): Phase {
  if (!isMapping(raw)) {
    throw new LoopError(
      `stage ${q(key)} of loop ${q(loopName)} should be a set of settings. ` +
        `Fix: write it as \`does: use-tools\` and, under it, \`then:\`.`,
    );
  }
  const doesRaw = String(raw["does"] || "").trim();
  if (!(DOES as readonly string[]).includes(doesRaw)) {
    throw new LoopError(
      `stage ${q(key)} of loop ${q(loopName)} says it does ${q(doesRaw)}, ` +
        `which is not something a stage can do. ` +
        `Fix: use one of: ${DOES.join(", ")}.`,
    );
  }
  const does = doesRaw as Does;

  // The same three ordinary YAML slips `loops.py` names — `then:` as a list of
  // one-item maps, `steps:` as a list, and `at-most: two` — reach a diagnostic
  // here too rather than a language-level type error. A host reading the tree
  // natively (D2) is the one who meets them.
  const thenRaw = raw["then"];
  if (thenRaw !== undefined && thenRaw !== null && !isMapping(thenRaw)) {
    throw new LoopError(
      `stage ${q(key)} of loop ${q(loopName)} says where to go next as ` +
        `${kindOf(thenRaw)}, and it should be one line per outcome. ` +
        `Fix: write \`then:\` with \`answered: done\` lines under it, one per ` +
        `outcome — not a list.`,
    );
  }
  const then: Record<string, string> = {};
  for (const [k, v] of Object.entries(isMapping(thenRaw) ? thenRaw : {})) {
    then[String(k)] = String(v);
  }

  let mayUseRaw = raw["may-use"];
  if (typeof mayUseRaw === "string") mayUseRaw = [mayUseRaw];
  const mayUse =
    mayUseRaw === undefined || mayUseRaw === null
      ? null
      : (mayUseRaw as unknown[]).map((x) => String(x));

  const atMostRaw = raw["at-most"];
  let atMost: number | null = null;
  if (atMostRaw !== undefined && atMostRaw !== null) {
    const parsed = Number.parseInt(String(atMostRaw).trim(), 10);
    if (Number.isNaN(parsed) || !/^[+-]?\d+$/.test(String(atMostRaw).trim())) {
      throw new LoopError(
        `stage ${q(key)} of loop ${q(loopName)} may run at most ` +
          `${pyRepr(atMostRaw)} times, which is not a number. ` +
          `Fix: write \`at-most: 2\`.`,
      );
    }
    atMost = parsed;
  }
  if (atMost !== null && atMost < 1) {
    throw new LoopError(
      `stage ${q(key)} of loop ${q(loopName)} may run at most ` +
        `${atMost} times, which means never. ` +
        `Fix: write \`at-most: 1\` or more, or remove the line.`,
    );
  }

  return {
    name: key,
    does,
    then,
    says: String(raw["says"] || "").trim(),
    mayUse,
    atMost,
    asks: String(raw["asks"] || "").trim(),
  };
}

/** Turn a stage back into document shape, so `based-on` inherits data. */
function phaseToMapping(p: Phase): Record<string, unknown> {
  const out: Record<string, unknown> = { does: p.does, then: { ...p.then } };
  if (p.says) out["says"] = p.says;
  if (p.mayUse !== null) out["may-use"] = [...p.mayUse];
  if (p.atMost !== null) out["at-most"] = p.atMost;
  if (p.asks) out["asks"] = p.asks;
  return out;
}

// Python's `repr` of a stage name, so a message composed here is the message
// composed there. A diagnostic that reads differently in the two runtimes is a
// second thing to keep in step with the first.
function q(s: string): string {
  return `'${s}'`;
}

function sorted(names: readonly string[]): string[] {
  return [...names].sort();
}

// What Python's `repr` would print for a value that came out of YAML, so a
// message about a bad `at-most:` reads the same in both runtimes.
function pyRepr(v: unknown): string {
  if (typeof v === "string") return q(v);
  if (typeof v === "boolean") return v ? "True" : "False";
  return String(v);
}

function isMapping(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

// The word Python's `type(x).__name__` would produce for the same YAML value,
// for the same reason `q` exists: the two ports name the mistake identically.
function kindOf(v: unknown): string {
  if (v === null || v === undefined) return "NoneType";
  if (Array.isArray(v)) return "list";
  if (typeof v === "string") return "str";
  if (typeof v === "boolean") return "bool";
  if (typeof v === "number") return Number.isInteger(v) ? "int" : "float";
  return "dict";
}

export const STANDARD = "pact:loop/standard";
export const PLAN_THEN_DO = "pact:loop/plan-then-do";
// AC-5.2's other four. CodeAct — the sixth name in that criterion — is
// deliberately absent: it means the agent writes code as its action, which is
// `runs-as: code`, refused in `docs/50-NOT-COPIED.md` because a spec naming code
// to run makes `pact check` decide whether that code is safe.
export const REACT = "pact:loop/react";
export const REFLEXION = "pact:loop/reflexion";
export const TREE_OF_THOUGHT = "pact:loop/tree-of-thought";
export const ANSWER_MORE_THAN_ONCE = "pact:loop/answer-more-than-once";

//: The shapes PACT ships, mirroring `spec/loops/*.yaml` and `loops.py::LIBRARY`
//: in meaning. They live here as data and go through `loopFrom` like anything an
//: author writes, so there is no privileged path a fork could not take.
export const LIBRARY: Record<string, Record<string, unknown>> = {
  [STANDARD]: {
    description:
      "Work until the job is done: use a tool, look at what came back, " +
      "and use another one if it is still needed. Answer when there is " +
      "nothing left to check. This is what an agent does when nobody " +
      "says otherwise.",
    "starts-at": "work",
    steps: {
      work: {
        does: "use-tools",
        then: { "used-a-tool": "work", answered: "done" },
      },
    },
  },
  [PLAN_THEN_DO]: {
    description:
      "Think first, then act. The first stage has no tools at all, so " +
      "the agent has to say what it plans to do before it can do " +
      "anything.",
    "starts-at": "plan",
    steps: {
      plan: {
        does: "think",
        says: "Say what you plan to do, in order, and why. Do not do any of it yet.",
        then: { "used-a-tool": "do", answered: "do" },
      },
      do: {
        does: "use-tools",
        then: { "used-a-tool": "do", answered: "done" },
      },
    },
  },
  [REACT]: {
    description:
      "Say what you know, what is missing, and the one thing you will do " +
      "next \u2014 then do that one thing, and say it again. The reasoning " +
      "is written down at every step instead of happening inside the tool " +
      "call.",
    "starts-at": "reason",
    steps: {
      reason: {
        does: "think",
        says:
          "Say what you have found out so far, what you still do not " +
          "know, and the one thing you will do next. One step only " +
          "\u2014 not a plan for the rest of the job.",
        "at-most": 6,
        then: { "used-a-tool": "act", answered: "act", "too-many-times": "reply" },
      },
      act: {
        does: "use-tools",
        then: { "used-a-tool": "reason", answered: "reply" },
      },
      reply: { does: "answer", then: { answered: "done" } },
    },
  },
  [REFLEXION]: {
    description:
      "Do the work, write down what is wrong with what you did, then do " +
      "it again with that criticism in front of you. At most two rounds, " +
      "then answer.",
    "starts-at": "attempt",
    steps: {
      attempt: {
        does: "use-tools",
        then: { "used-a-tool": "attempt", answered: "critique" },
      },
      critique: {
        does: "check-its-work",
        says:
          "Say what is wrong with the answer you just gave: what it " +
          "missed, what it assumed without checking, and what you " +
          "would do differently. Do not rewrite the answer here " +
          "\u2014 only say what is wrong with it.",
        "at-most": 2,
        then: {
          "used-a-tool": "critique",
          answered: "revise",
          "too-many-times": "reply",
        },
      },
      revise: {
        does: "use-tools",
        says:
          "Do the work again with the criticism you just wrote in " +
          "front of you. Fix what you said was wrong rather than " +
          "defending it.",
        then: { "used-a-tool": "revise", answered: "critique" },
      },
      reply: { does: "answer", then: { answered: "done" } },
    },
  },
  [TREE_OF_THOUGHT]: {
    description:
      "Write down three different ways this could be approached, say " +
      "what would go wrong with each, then carry out the one that " +
      "survives. The branches are written down and pruned in the " +
      "transcript, not executed and compared.",
    "starts-at": "propose",
    steps: {
      propose: {
        does: "think",
        says:
          "Write down three different ways this could be approached. " +
          "Number them. Do not choose between them and do not start " +
          "any of them.",
        then: { "used-a-tool": "judge", answered: "judge" },
      },
      judge: {
        does: "check-its-work",
        says:
          "Take each of the three in turn and say what would go wrong " +
          "with it. Then say which one survives best, and why the " +
          "other two do not.",
        "at-most": 2,
        then: {
          "used-a-tool": "judge",
          answered: "follow",
          "too-many-times": "follow",
        },
      },
      follow: {
        does: "use-tools",
        says:
          "Carry out the approach you chose. If it fails in the way " +
          "you predicted it might, say so rather than switching to " +
          "another one silently.",
        then: { "used-a-tool": "follow", answered: "done" },
      },
    },
  },
  [ANSWER_MORE_THAN_ONCE]: {
    description:
      "Work the whole question through three times, starting again from " +
      "the question each time, then say which answer you are standing " +
      "behind and whether the attempts disagreed. The attempts share a " +
      "conversation, so they are not independent samples.",
    "starts-at": "attempt",
    steps: {
      attempt: {
        does: "think",
        says:
          "Work the whole question through from the beginning and " +
          "give your answer. Start from the question itself, not from " +
          "anything you have already said.",
        "at-most": 3,
        then: {
          "used-a-tool": "attempt",
          answered: "attempt",
          "too-many-times": "settle",
        },
      },
      settle: {
        does: "answer",
        says:
          "You have worked this through more than once. Say which " +
          "answer you are giving. If the attempts disagreed, say that " +
          "they disagreed and which one you are standing behind " +
          "\u2014 do not present it as though it were settled.",
        then: { answered: "done" },
      },
    },
  },
};
