// The PACT harness, ported to TypeScript.
//
// This is a deliberate duplication, not an accident. Decision D12 says PACT owns
// the loop; the Vercel AI SDK runs on a different runtime from the Python
// targets, so the loop has to exist there too. The conformance suite then checks
// that the two ports agree — which is a far stronger claim than one
// implementation agreeing with itself, because a divergence here would be a
// genuine specification ambiguity rather than a coding slip.
//
// That applies to STOPPING as much as to stepping (G2). A port that agreed about
// every step and then ended the run on a different rule would have agreed about
// nothing that matters, so the ceilings and their three actions are read here
// from the author's own field names too.
//
// And it applies to the SHAPE of the stepping (G1). A port that took the same
// number of steps through a different set of stages would be running a different
// agent: `may-use:` decides which tools a step can reach and `says:` decides
// what it is told, so a second port that ignored them would agree about the
// trace of a one-stage loop and about nothing an author had actually written.
// AC-5.3's bar is the stage path, which is why it is the second mechanism
// carried here rather than the fifth.

import {
  type Action, type Limits, type Meter, type Reached,
  ceilings, limitsFrom, limitsNotRead, newMeter, reached, sentence, stepCeiling,
  stepsAtMost, unmeterable, ceilingsNothingCanReach,
} from "./limits.ts";
import {
  type Does, type Loop, type Phase, DONE, LoopError, OUTCOMES,
  checkAgainst, instruction, resolve, route, skillsOffered, stageToRun, systemFor,
  toolsOffered,
} from "./loops.ts";
import { saidYes } from "./yes-no.ts";

export type ToolCall = { name: string; args: Record<string, unknown> };
export type Turn = { text: string; toolCalls?: ToolCall[] };
export type Step = {
  index: number;
  text: string;
  tools: ToolCall[];
  results: string[];
};

export interface Transport {
  name: string;
  lattice(): Record<string, string>;
  modelCall(
    system: string,
    history: Array<Record<string, unknown>>,
    tools: Array<Record<string, unknown>>,
  ): Promise<[string, ToolCall[]]>;
  // Optional: what the last model call cost. Absent on a transport that cannot
  // say — a scripted model has no price and no tokeniser — and what cannot be
  // measured is reported as unenforced rather than guessed at.
  usage?(): [number, number];
  // Optional: whether the catalogue publishes a PRICE for the bound model, which
  // is a different question from whether tokens can be counted. A locally-served
  // row may publish a window and no `cost:` block — the air-gapped case — and
  // running the two together cost `tokens-at-most` its enforcement in the Python
  // port before `Limits.unmeterable` was split.
  //
  // Absent means `false` — a transport that never said it can price its calls is
  // not taken to have. It used to mean "the same as `usage`", and that is B6:
  // a transport with a `usage()` and no catalogue row was taken to price its
  // calls, so an author's spend cap was reported as enforced against a money
  // meter that never left zero.
  pricesMoney?: boolean;
}

// One written procedure, in the author's own field names — this is the shape
// `pact show` emits, and a port that renamed it would be reading a translation
// rather than the document.
export type SkillSpec = {
  name: string;
  description?: string;
  "use-when"?: string;
  "do-not-use-when"?: string;
  "if-unsure"?: string;
  content?: string;
};

// One set of documents an agent looks things up in (A7). The author's own field
// names, like `SkillSpec` above and for the same reason.
//
// A SEPARATE type from `SkillSpec`, and the reason is about reviewing rather
// than plumbing: somebody who has read a skill has read every word the model
// will see, and `passages-at-most: 5` means nobody knows at check time which
// five. A skill is determinate and this is not.
export type KnowledgeSpec = {
  name: string;
  description?: string;
  // `must-cite: yes` — an answer with no source is not an answer, and a set the
  // run could not consult FAILS THE TURN rather than being answered from what
  // the model already knew.
  "must-cite"?: boolean | string;
  "passages-at-most"?: number;
  "looked-up-by"?: string;
  "split-by"?: string;
};

export type AgentSpec = {
  name: string;
  instructions: string;
  tools: { name: string; description: string }[];
  // Written procedures the agent may consult. A stage of a loop may narrow to
  // one, and until this field existed `may-use: [refund-policy]` — a skill the
  // agent's own `uses:` line lists — aborted the run here with *"which this
  // agent does not have. It has: payments, zendesk."*, which was false.
  //
  // It carried NAMES for a round, in both ports, and the consequence was that
  // no skill reached any model anywhere: the agent whose only capability is a
  // written policy was sent its own five-line instructions and nothing else.
  skills?: SkillSpec[];
  // Sets of documents the agent may look things up in. PACT retrieves nothing
  // itself — a runtime that does already exists — so what this carries is what
  // that runtime is told and what a reviewer can read.
  //
  // Ported in the same change as the Python side, because the two halves of one
  // guarantee living in one port is exactly the divergence the conformance
  // driver exists to catch: the Python run refused a `must-cite:` corpus it
  // could not read, and this one answered.
  knowledge?: KnowledgeSpec[];
  // What the agent hands back when it is done, as the author wrote it. Read by
  // nothing in EITHER port for a round, while `tier: core` and present in the
  // worked example — so every scripted answer in the eval suite hand-writes
  // the format the document already specified.
  answersWith?: Record<string, string>;
  // How that shape is put to the model. Empty means the author left it out,
  // and PACT picks `prompted` — the one mode every target can honour and the
  // only one that needs nothing off this machine.
  answersWithMode?: string;
  // Teammates, by name, with what each is for.
  team?: Record<string, string>;
  // Absent means `ir.DEFAULT_STEPS`. A bound is never absent — but this port
  // read it off an unvalidated JSON payload, so a caller who omitted it got a
  // raw `TypeError` out of `limits.ts` rather than the default Python uses.
  maxSteps?: number;
  // The author's `limits:` block, in their own spelling.
  limits?: Record<string, unknown>;
  // The agent's own `loop:` line — a name in `loops:`, or `pact:loop/<shape>`.
  // Absent means `pact:loop/standard`, which is what the harness did before
  // loops were readable at all.
  loop?: string;
  // The workspace's `loops:` block, exactly as loaded. Handed over whole rather
  // than pre-selected, so this port makes the same choice from the same two
  // facts the Python one has.
  loops?: Record<string, unknown>;
  // Lines this port reads and does not carry out. Carried so they can be
  // REPORTED — see `notDoneHere`. A field absent here is a field the author did
  // not write; a field present and unhonoured is one they are told about.
  interceptors?: string[];
  contextPolicy?: string;
  policy?: string;
  teamwork?: Record<string, unknown>;
  // Four more the property covered in words and not in fact. Measured on one
  // document carrying all of them: Python named
  // `first-reply-within, per-word-under, settings.max-tokens, settings.thinking`
  // and this port named nothing at all, because a key no field declares vanishes
  // in `JSON.parse`. A smaller port that cannot say what it is smaller by is the
  // T7 breach `notDoneHere` exists to prevent.
  settings?: Record<string, unknown>;
  slo?: Record<string, unknown>;
  model?: string;
  watches?: string[];
};

//: Every key an `AgentSpec` declares. The conformance driver takes its payload
//: off the command line and casts it, so this is the only place a misspelt or
//: unported field can be caught — see `run-trace.ts`.
export const AGENT_SPEC_FIELDS = [
  "name", "instructions", "tools", "skills", "team", "maxSteps", "limits",
  "loop", "loops", "interceptors", "contextPolicy", "policy", "teamwork",
  "settings", "slo", "model", "watches", "answersWith", "answersWithMode",
  "knowledge",
] as const;

//: Used when the payload carried no `maxSteps`. The same number `ir.py` uses,
//: for the same reason: an unbounded loop is Eve's behaviour, and its
//: consequence is a run that stops only once a token budget is gone.
export const DEFAULT_STEPS = 8;

/** Keys in a payload that no `AgentSpec` field declares.
 *
 *  Exported and called from `run` — not only from the conformance driver, where
 *  this check used to live alone. §7.28 said this port *"refuses to start"* on an
 *  undeclared key, and that was true of `run-trace.ts` and of nothing else: a
 *  library consumer calling `run()` got the silent cast, so an authored setting
 *  this port has not ported was neither honoured nor reported. The T7 breach
 *  `notDoneHere` exists to prevent, arriving through the front door. */
export class SpecError extends Error {}

export function undeclaredIn(payload: object): string[] {
  const declared = AGENT_SPEC_FIELDS as readonly string[];
  return Object.keys(payload).filter((k) => !declared.includes(k)).sort();
}

//: The answer `answers-with-mode:` gets when the author left it out, and the
//: ones this port cannot deliver. Same two choices as `harness.py`: `prompted`
//: is the only mode all seven targets can honour and the only one that needs
//: nothing off this machine (D17).
//:
//: There was an `ANSWER_MODES` here listing all four spellings, the twin of a
//: table in `harness.py` that this round deleted. Neither port read either one —
//: `spec/schema.yaml`'s `choices:` block is what decides which words load, and a
//: second copy of it with no gate depending on it is the shape that goes stale
//: quietly. `adapters/python/tests/test_a_table_nothing_reads_is_not_a_source_of_truth.py`
//: is the check that found it; there is no TypeScript twin of that check yet,
//: which is why this note says what happened rather than leaving the next reader
//: to wonder where the list went.
export const CHOSEN_ANSWER_MODE = "prompted";
export const MODES_NOTHING_HERE_DELIVERS = ["native-json-schema", "tool"] as const;

export type RunResult = {
  output: string;
  steps: Step[];
  halted: string;
  stoppedBy: Reached | null;
  unmetered: string[];
  // Authored lines this port cannot carry out, in words. `unmetered` says
  // *nobody could count this*; this says *the line is read correctly and this
  // runtime does not do it*, which is the same distinction `harness.py` draws.
  //
  // It did not exist here, so a spec carrying `interceptors:` ran with none of
  // them and said nothing: measured on the worked example's own three, a card
  // number reached `payments` twice and `stop-runaway-refunds` did nothing,
  // while Python halted `stopped-by-rule` on the second refund with the card
  // masked. Silence about that is the T7 breach.
  unenforced: string[];
  // Sets of documents this run could not consult, each a sentence naming the
  // entry, what it means for the answer, and a line to type (A7).
  //
  // A FIFTH channel and not a fifth use of `unenforced`, which is the same
  // distinction `harness.py` draws and for the same reason: *the rule could not
  // be evaluated* sends the reader to the rule, *the corpus was never read*
  // sends them to whoever runs the thing. Every sentence on `unenforced` invites
  // an edit to the author's own document, and there is nothing here to edit —
  // the document is right and the runtime is smaller.
  //
  // It did not exist here, so `must-cite: yes` was refused in the same words as
  // the reference port and a corpus WITHOUT it ran, answered out of the model's
  // own memory, and said nothing: measured on `examples/answers-from-documents`
  // with `must-cite: no`, both ports answered *"25 days."* and only one of them
  // said where that came from. A fifth channel living in one port only is the
  // T7 breach, on the port whose whole justification is that it says what it is
  // smaller by.
  unretrieved: string[];
  // Which stage of the authored loop ran at each step, in order. Deliberately
  // NOT part of the trace: the trace is the cross-runtime contract seven
  // transports are held to byte-for-byte, and folding the path into it would
  // change what "the same trace" means. The path is how you see that the loop
  // document did something.
  phases: string[];
  // What a person would be shown when a ceiling's action is `ask-a-person`.
  // Beside `output` rather than inside it, because `output` is what the run
  // produced and the two ports are compared on it byte-for-byte.
  waitingWords?: string;
};

//: What this port reads and does not carry out — **the `AgentSpec`'s own
//: top-level keys, and only those**.
//:
//: Each entry names the author's own field and says plainly what does not
//: happen, because a runtime that silently ignores a governance line is worse
//: than one that refuses the document — the author reads `pact check`, sees OK,
//: and believes the rule is holding. Measured before this existed, on the worked
//: example's own three interceptors: a card number reached `payments` twice and
//: the second refund went through, while Python masked the card and halted
//: `stopped-by-rule`.
//:
//: NOT the whole report, and the name is not a promise that it is. This function
//: composes EIGHT of the ten §7.28 list-B rows that reach `unenforced` (plus the
//: `team:` line, which is a list-A key reported for a different reason). The
//: other two rows are appended by `run()`, beside the call, and for two different
//: reasons:
//:
//:  * a loop stage's `asks:` — written INSIDE something this function is handed
//:    raw. `spec.loops` arrives as the workspace's block and which loop the agent
//:    runs is `spec.loop`, so no stage exists until `run()` has resolved the two.
//:  * `answers-with-mode:` — readable off the `AgentSpec`, but the line depends on
//:    the mode CHOSEN for the turn (`spec.answersWithMode || CHOSEN_ANSWER_MODE`)
//:    and on whether an `answers-with:` shape was written at all, so it is a fact
//:    about the run and not about the field.
//:
//: Anything added here must be readable off the `AgentSpec` alone AND decided by
//: the field alone; anything else belongs beside that call. The distinction is
//: worth keeping: a function handed one document should not be able to answer
//: questions about a second one it was never handed.
export function notDoneHere(spec: AgentSpec): string[] {
  const out: string[] = [];
  if ((spec.interceptors ?? []).length > 0) {
    out.push(
      `interceptors: ${(spec.interceptors ?? []).join(", ")} — read and not run on this ` +
        `runtime, so nothing is hidden, stopped or sent elsewhere. The Python ` +
        `harness carries these out; this port has no chain.`,
    );
  }
  if (spec.contextPolicy) {
    out.push(
      `context-policy: ${spec.contextPolicy} — read and not applied here, so a ` +
        `conversation that outgrows the model is sent whole rather than tidied.`,
    );
  }
  if (spec.policy) {
    out.push(
      `policy: ${spec.policy} — read and not applied here, so nothing stops to ask ` +
        `a person before a call this port makes.`,
    );
  }
  // `Object.keys(...).length`, NOT truthiness: `teamwork: {}` is an object, and
  // an object is truthy, so a payload carrying an empty block reported a rule
  // that had not been written as one this port could not apply. A false
  // "not applied" is worse than silence — it tells the author their file contains
  // something it does not, and it is the same `or`-versus-`is None` mistake the
  // reference port made with `chain` and `teamwork` themselves, in the one
  // language where an empty container is truthy.
  if (Object.keys(spec.teamwork ?? {}).length > 0) {
    out.push(
      `teamwork: read and not applied here — this port has no delegation, so ` +
        `waiting, ordering and the budget split are all the caller's.`,
    );
  }
  // `team:` alone, separately from `teamwork:`. Teammates ARE offered to the
  // model here (they were not, for a round — the model was handed
  // `error: no tool named 'policy-checker'` for the one thing its instructions
  // told it to do), but nothing in this port can run one, so a call to a
  // teammate is refused and said so rather than parked.
  if (Object.keys(spec.team ?? {}).length > 0) {
    out.push(
      `team: ${Object.keys(spec.team ?? {}).sort().join(", ")} — offered to the ` +
        `model here and not runnable on this runtime, so asking one comes back ` +
        `as an error instead of parking. The Python harness suspends the run.`,
    );
  }
  for (const key of Object.keys(spec.settings ?? {})) {
    out.push(
      `settings.${key}: read and not passed to the model on this runtime, so ` +
        `the model is asked to behave however its own default says.`,
    );
  }
  for (const key of Object.keys(spec.slo ?? {})) {
    out.push(`${key}: a latency promise nothing on this runtime measures.`);
  }
  if (spec.model) {
    out.push(
      `model: ${spec.model} — read and not bound here; this port runs whatever ` +
        `model the transport was constructed with.`,
    );
  }
  if ((spec.watches ?? []).length > 0) {
    out.push(
      `watch: ${(spec.watches ?? []).join(", ")} — read and not written here, so ` +
        `nothing on this runtime records what the run did.`,
    );
  }
  return out;
}

//: The sets of documents this port could not look anything up in — which is all
//: of them, because it retrieves nothing at all.
//:
//: A SIBLING of `notDoneHere` rather than a row inside it, because the two lists
//: go to two different people. `notDoneHere` is read by the author of the
//: document: every line on it is a line they wrote and can take out. This is read
//: by whoever chose the runtime — the corpus is declared correctly, nothing in
//: the file needs editing, and the only remedy is to run the agent somewhere that
//: can read the documents. Filing it under `unenforced` would send the ticket to
//: the person who cannot act on it, and would put ONE fact in TWO channels across
//: the two ports, since `harness.py` has carried `unretrieved` since A7.
//:
//: The sentence before `fix:` is `harness.py`'s, word for word, and the
//: conformance driver compares the two over several corpus names, not one. The
//: quotes around the name are TYPED on both sides and must stay typed: the
//: reference port built them with `repr` for a round, which spells
//: `'staff-handbook'` and `"bob's-handbook"`, and `pact check` loads both names —
//: so the two ports agreed on every shipped tree and disagreed on the first
//: apostrophe anybody wrote. Only the remedy differs, and it has to:
//: the reference port takes a `retrieved_by` from a host that retrieves, so
//: *"run this where a retrieval runtime serves ..."* is true there and would be
//: false here — `run()` has nowhere to hand one in, so a machine with an index
//: changes nothing about this port.
export function neverLookedIn(spec: AgentSpec): string[] {
  return (spec.knowledge ?? []).map(
    (k) =>
      `'${k.name}' is a set of documents and nothing in this run looked anything ` +
      `up in it, so the answer comes from what the model already knew. fix: ` +
      `nothing on this runtime can look anything up, so run this agent on the ` +
      `reference port with a retrieval runtime serving ` +
      `\`knowledge/${k.name}/documents/\`, or take \`${k.name}\` off this agent's ` +
      `\`uses:\` line.`,
  );
}

export async function run(
  spec: AgentSpec,
  transport: Transport,
  userInput: string,
  toolImpls: Record<string, (a: Record<string, unknown>) => string> = {},
  clock: () => number = () => Date.now() / 1000,
): Promise<RunResult> {
  // Refused HERE and not only in the conformance driver. §7.28 claimed this port
  // "refuses to start" on a field it does not know, and that was true of
  // `run-trace.ts` alone — a library consumer got the silent cast instead. Four
  // parts, like every other diagnostic, because a person who cannot write code
  // has to be able to act on it.
  const strange = undeclaredIn(spec);
  if (strange.length > 0) {
    throw new SpecError(
      `this port does not know the field(s) ${strange.join(", ")}. ` +
        `It reads: ${AGENT_SPEC_FIELDS.join(", ")}. ` +
        `Fix: remove them from the payload, or port them and add each to ` +
        `AGENT_SPEC_FIELDS — a field that arrives and is silently dropped is ` +
        `neither honoured nor reported.`,
    );
  }
  // A7. Every declared set, named before anything else happens. PACT retrieves
  // nothing and this port has nowhere to be handed a retrieval either, so a set
  // of documents nobody looked in is the ordinary state — and it must not be the
  // silent one, because the agent then answers from what the model already knew
  // and the answer reads exactly like one that was grounded.
  //
  // Filled HERE, above the refusal below, so a turn that ends `no-sources` still
  // carries the cause beside the outcome. The reference port does the same, in
  // the same order.
  const unretrieved = neverLookedIn(spec);
  // `must-cite: yes` says an answer with no source is not an answer, and
  // this port retrieves nothing — so every declared set is one the run could not
  // consult. Answering anyway produces an answer from what the model already
  // knew, citing a document it never opened: the worst outcome available and the
  // one that looks most like success.
  //
  // Decided BEFORE a single model call, because paying for an answer that cannot
  // be given is the other thing that would look like working. The Python side
  // does the same, in the same place, and the conformance driver compares them —
  // this half existed only there for as long as it took to notice.
  //
  // `saidYes`, not `=== "yes"`. This line held its own two-word list against the
  // checker's five, so `must-cite: enabled` — a line `pact check` prints `OK`
  // for — answered out of the model's memory here and refused the turn in the
  // reference port, on a field §7.28 lists as carried out identically. See
  // `yes-no.ts` for the measurement and for why the driver never caught it.
  const ungrounded = (spec.knowledge ?? [])
    .filter((k) => saidYes(k["must-cite"]))
    .map((k) => `'${k.name}'`);
  // KNOWN AND SCOPED OUT, recorded in §7.28 rather than only here: this return
  // carries `unenforced: []`, so a document that declares a `must-cite:` corpus
  // AND an `interceptors:`, a `policy:` or an asking stage reports none of them.
  // The reader is told the truth about why the turn ended — nothing was read —
  // and nothing about the ten governance lines that also did not happen. It
  // predates the `asks:` row (`git show HEAD:adapters/typescript/src/harness.ts`
  // has the same empty list on this path). Not closed here because `unretrieved`
  // is what this ending is about and widening it is a change to a sentence two
  // ports agree on word for word; §7.28 list B names the gap instead.
  if (ungrounded.length > 0) {
    const named = ungrounded.length === 1
      ? ungrounded[0]
      : `${ungrounded.slice(0, -1).join(", ")} and ${ungrounded[ungrounded.length - 1]}`;
    return {
      output:
        `I could not read ${named}, and I am only allowed to answer from what is ` +
        `in there — so I have nothing to answer from.`,
      steps: [],
      halted: "no-sources",
      stoppedBy: null,
      unmetered: [],
      unenforced: [],
      unretrieved,
      phases: [],
    };
  }

  const written = spec.limits ?? {};
  const limits: Limits = limitsFrom(written);
  // One ceiling, one place: the step bound is `maxSteps`, which the caller may
  // already have resolved, and `steps-at-most` when the block carries one.
  // No branch on `spec.limits`: an absent block is an empty one, and an absent
  // `maxSteps` is the same default `ir.py` uses rather than `undefined` reaching
  // `limits.ts` as a raw `TypeError`.
  const maxSteps = stepsAtMost(written, spec.maxSteps ?? DEFAULT_STEPS);

  // The shape of the thinking, from the author's own `loop:` line (G1).
  const loop: Loop = resolve(spec.loops, spec.loop ?? "");

  const toolDefs = [
    ...spec.tools.map((t) => ({
      name: t.name,
      description: t.description,
      parameters: {},
    })),
    // Every teammate is offered, whether or not this port can run them — word
    // for word what `harness.py` does, and it was missing here. Measured on the
    // shipped example, whose `instructions.md` says *"Ask **policy-checker**"*:
    // Python offered four names and suspended; this port offered two and handed
    // the model `error: no tool named 'policy-checker'`, then answered
    // "Approved." A model that is never told a teammate exists can never ask
    // for one.
    ...Object.entries(spec.team ?? {}).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(
      ([m, brief]) => ({
        name: m,
        description: `ask ${m} for help: ${brief}`.replace(/: $/, ""),
        parameters: {},
      }),
    ),
  ];
  const toolNames = toolDefs.map((d) => d.name);
  const skills = (spec.skills ?? []).slice().sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0
  );
  // Everything a stage may name: the agent's tools, its teammates, and the
  // written procedures it may consult. All three, because `may-use:` NARROWS
  // what the agent already has — anything it may use that no stage can mention
  // is a hole rather than a narrowing.
  const reachable = [...toolNames, ...skills.map((s) => s.name)];
  // A stage may only narrow what the agent already has. Checked once, before the
  // first model call, so a typo in a rarely-taken branch fails at the start of
  // the run instead of forty steps in.
  checkAgainst(loop, reachable);

  const history: Array<Record<string, unknown>> = [
    { role: "user", content: userInput },
  ];
  const steps: Step[] = [];
  const phases: string[] = [];
  const visits: Record<string, number> = {};
  let phaseName = loop.startsAt;
  const meter: Meter = newMeter(clock());
  // The two questions, asked separately. A transport that counts tokens but whose
  // model the catalogue prices at nothing keeps `tokens-at-most` and loses only
  // the money cap — which is the distinction the one-boolean version could not
  // draw.
  //
  // An undeclared `pricesMoney` is `false`, which is the same default
  // `harness.py`'s `getattr(transport, "prices_money", False)` uses and has to
  // be: two ports answering one author's `cost-per-request-under:` differently
  // is the defect the cross-port suite exists to catch. It used to be
  // `countsTokens` in both, and that is B6 — a transport with a `usage()` and no
  // way to be priced was taken to price its calls, so an author was told their
  // spend cap was enforced against a meter that read zero for the life of the
  // workspace. Every transport in either port now declares it; the default is
  // what the NEXT one gets before anybody has thought about it, and the safe
  // answer to "can this be priced?" from something that never said is no.
  const countsTokens = typeof transport.usage === "function";
  const pricesMoney =
    typeof transport.pricesMoney === "boolean" ? transport.pricesMoney : false;
  // And, through the same door, a spend cap that is not a figure any spend can
  // be at or above — `NaN USD`, `inf USD`. `ceilings()` has already refused to
  // build the row; without this line it would be refused in SILENCE, which is
  // the same T7 breach one step further on and is what both ports did.
  // Not a channel of its own: `unmetered`'s wording is *"cannot promise"*, which
  // is exactly what is true of a cap nothing can reach. Argued at
  // `limits.ceilingsNothingCanReach`; pinned from the Python suite by
  // `test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py`, which
  // drives this port through `run-trace.ts`.
  const unmetered = [
    ...unmeterable(limits, countsTokens, pricesMoney),
    ...ceilingsNothingCanReach(limits),
  ];
  // Everything the author wrote that this port reads correctly and does not do.
  // Named one field at a time, with the sentence a person can act on, because
  // "this runtime is smaller" is not something a reader can check against their
  // own file.
  const unenforced = notDoneHere(spec);
  // The one line `notDoneHere` cannot see, appended where it can be: a stage's
  // `asks:`. It names WHICH question a person is put, which is a governance line
  // and not a wording choice — and it was parsed by `loops.ts` into `Phase.asks`
  // and read by nothing here, in silence, because `notDoneHere` is handed an
  // `AgentSpec` whose `loops:` is still the workspace's raw block. By this point
  // `resolve` has run, so the stages exist and each one that names a question can
  // say that nobody here is put it.
  //
  // Reported for every such stage the loop declares, reached or not, exactly as
  // `interceptors:` is reported whether or not one would have fired: the reader
  // is being told what their document does not do on this runtime, which is a
  // fact about the document.
  //
  // Sorted by stage name so two runs of one document say the same thing in the
  // same order — `loop.steps` is insertion-ordered from the payload, and a report
  // that reorders itself is a report a reader cannot diff.
  //
  // `limits.asks` is a DIFFERENT line — the question put when a ceiling runs out
  // — and is reported below under its own `limits.` prefix.
  //
  // Written in the CONDITIONAL — *"a run that reaches that stage"* — because the
  // line is reported for the document and not for the path taken, and the branch
  // that never entered the stage would be told, in the indicative, that the run
  // stopped somewhere it did not go. A report that states something this run did
  // not do is the same defect as one that omits something it did.
  for (const stage of Object.keys(loop.steps).sort()) {
    const phase = loop.steps[stage];
    if (phase.does !== "ask-someone") continue;
    if (!phase.asks) {
      // The shape that most needs the line and had none: a stage that stops to
      // ask a person and names no question. `spec/schema.yaml` refuses the
      // document (`needs: asks: ask-someone`), so a CLI-loaded tree cannot get
      // here — but `run()` is a library entry point too, and a hand-built payload
      // reached it and suspended with `unenforced: []`. This port does not run
      // the checker, so its report may not depend on one having been run.
      unenforced.push(
        `asks: (none named) — stage '${stage}' stops to ask a person and names no ` +
          `question, so a run that reaches it stops there with nothing to put to ` +
          `anybody. fix: add an \`asks:\` line naming a question under ` +
          `\`questions/\` — \`pact check\` refuses the stage without one, and this ` +
          `port does not run \`pact check\`.`,
      );
      continue;
    }
    unenforced.push(
      `asks: ${phase.asks} — the question stage '${stage}' puts to a person, ` +
        `read here and put to nobody. This port has no durable suspension, so a ` +
        `run that reaches that stage stops there carrying no question, no audience ` +
        `and no deadline. The Python harness parks the run and puts the question ` +
        `you named, with the shape of the answer it will take.`,
    );
  }
  // Keys inside `limits:` this port does not read. They were dropped in silence —
  // `feel`, `first-reply-within`, `per-word-under`, `measured-at` and `asks` — and
  // §7.28 accounted for them under `slo.*`, a row that could never fire because
  // `pact show` nests them inside `limits:` and nothing ever arrives under `slo:`.
  for (const key of limitsNotRead(spec.limits ?? {})) {
    unenforced.push(
      `limits.${key} — read and not applied on this runtime, so it holds nothing ` +
        `on this run. The Python harness carries the latency promises to a report ` +
        `and \`asks:\` to the person being interrupted; neither happens here.`,
    );
  }
  // Which way the author's `answers-with:` is put to the model. Both ports pick
  // `prompted` when the line is absent, and both REPORT the two modes that
  // constrain the answer at the provider rather than serving prose and calling
  // it done — a run that quietly downgraded would be the silent degradation T7
  // forbids, and would make the two ports disagree about the same document.
  const answerMode = spec.answersWithMode || CHOSEN_ANSWER_MODE;
  const shapeToAskFor = answerMode === CHOSEN_ANSWER_MODE ? (spec.answersWith ?? {}) : {};
  if (
    Object.keys(spec.answersWith ?? {}).length > 0 &&
    (MODES_NOTHING_HERE_DELIVERS as readonly string[]).includes(answerMode)
  ) {
    unenforced.push(
      `answers-with-mode: ${answerMode} — the answer was not constrained at the ` +
        `model, because no transport here can do that. The shape you wrote under ` +
        `\`answers-with:\` held nothing on this run. fix: write ` +
        `\`answers-with-mode: ${CHOSEN_ANSWER_MODE}\`, which asks for the same shape ` +
        `in the instructions and works on every target.`,
    );
  }

  // An outcome the author routed nowhere. The run ends carrying the message
  // `route` composed — which names the stage, the outcome and the line to add —
  // and the steps already taken stay on the result, because a run that got eight
  // steps in before meeting a missing `then:` should still show those eight.
  const whereNext = (phase: Phase, outcome: string): string | RunResult => {
    try {
      return route(loop, phase, outcome);
    } catch (e) {
      if (e instanceof LoopError) {
        return {
          output: e.message, steps, halted: "loop-error",
          stoppedBy: null, unmetered, unenforced, unretrieved, phases,
        };
      }
      throw e;
    }
  };

  const ranOut = async (r: Reached, at: number): Promise<RunResult> => {
    const base = {
      steps, halted: r.ceiling.halted, stoppedBy: r, unmetered, unenforced, unretrieved, phases,
    };
    if (r.action === "answer-with-what-it-has") {
      // One closing call with NO tools offered, so the model has to answer from
      // what it already has. Outside the budget on purpose: charging for all the
      // work and then withholding the answer helps nobody.
      const [text] = await transport.modelCall(spec.instructions, history, []);
      steps.push({ index: at, text, tools: [], results: [] });
      return { ...base, output: text };
    }
    // `ask-a-person` cannot be answered inside one process here, so this port
    // reports the wait rather than pretending to resolve it. Python carries the
    // durable suspension.
    //
    // `halted` is `suspended`, matching `harness.py`. The comment here used to
    // claim "both agree on the ceiling and on the words" and they agreed on
    // neither: measured across four ceilings and three actions,
    // `stop-and-say-so` and `answer-with-what-it-has` agreed exactly and
    // `ask-a-person` never did — Node reported `halted='step-limit'` with
    // *"Waiting for a person: ..."*, Python `halted='suspended'` with the text
    // it already had. A run that has stopped to ask somebody is in the same
    // state in both, or "the same trace" means less than it says.
    // ...and only for `ask-a-person`. The other two actions end the run, and
    // they already agreed with Python exactly.
    if (r.action === "ask-a-person") {
      // `output` is part of the compared contract, and the two ports disagreed
      // on it: Python leaves `result.output` as the model's last text and puts
      // the person-facing wording on `Suspension.in_words`, so a run that parked
      // returned "still working" there and *"Waiting for a person: ..."* here.
      // The words a person reads are Python's alone (the README says so), so
      // this port carries them beside the result rather than in place of it.
      return {
        ...base,
        halted: "suspended",
        output: steps.length ? steps[steps.length - 1].text : "",
        waitingWords: sentence(r),
      };
    }
    return { ...base, output: sentence(r) };
  };

  for (let i = 0; i < maxSteps; i++) {
    meter.steps = i;
    const early = reached(limits, meter, clock());
    if (early) return ranOut(early, i);

    // Which stage runs now. A stage that has used up its `at-most` is routed
    // past here rather than after the fact, so it never spends a model call
    // discovering that it was not allowed to run.
    const [phase, gaveUp] = stageToRun(loop, phaseName, visits);
    if (phase === null) {
      return {
        output: steps.length ? steps[steps.length - 1].text : "",
        steps, halted: gaveUp ? "stage-limit" : "final",
        stoppedBy: null, unmetered, unenforced, unretrieved, phases,
      };
    }
    phaseName = phase.name;
    phases.push(phaseName);

    // A stage that asks a person makes no model call at all. Python carries the
    // durable suspension — the record, the deadline, the shape of the answer —
    // and this port has none of that, so it reports the wait rather than
    // pretending to resolve it. Both ports agree on the stage the run stopped
    // in and on the path that got there; the words a person reads are Python's
    // alone, and the README says so.
    if (phase.does === "ask-someone") {
      return {
        output: "", steps, halted: "suspended",
        stoppedBy: null, unmetered, unenforced, unretrieved, phases,
      };
    }

    // What exists in this stage. Eve resolves the tool set once per run, which
    // is why a planning step there can see the payment tool; here it is the
    // stage's own line.
    const offered = new Set(toolsOffered(phase, reachable));
    const stepTools = toolDefs.filter((d) => offered.has(d.name));
    const readable = new Set(skillsOffered(phase, skills.map((s) => s.name)));
    const stepSkills = skills.filter((s) => readable.has(s.name));

    const [text, calls] = await transport.modelCall(
      systemFor(
        spec.instructions,
        phase,
        stepSkills,
        // Same rule as the reference port: the shape is asked for in the
        // prompt when the mode is the one PACT picks, and reported rather
        // than silently downgraded when it is not.
        shapeToAskFor,
      ),
      history,
      stepTools,
    );
    if (transport.usage) {
      const [tokens, money] = transport.usage();
      meter.tokens += tokens;
      meter.money += money;
      const spent = reached(limits, meter, clock());
      if (spent) return ranOut(spent, i);
    }

    // A call to something this stage does not offer is refused, and the refusal
    // is handed back to the model. Dropping it silently would lose an action the
    // model really took (T7); running it would make `may-use:` advisory. The two
    // refusals stay distinguishable because they call for opposite fixes: a name
    // to correct, or a `may-use:` line to widen.
    const have = new Set(toolNames);
    const refused: Record<string, string> = {};
    for (const c of calls) {
      if (!offered.has(c.name)) {
        refused[c.name] = have.has(c.name)
          ? `error: '${c.name}' is not available in the '${phaseName}' stage`
          : `error: no tool named '${c.name}'`;
      }
    }

    if (calls.length === 0) {
      visits[phaseName] = (visits[phaseName] ?? 0) + 1;
      const nxt = whereNext(phase, "answered");
      if (typeof nxt !== "string") return nxt;
      steps.push({ index: i, text, tools: [], results: [] });
      if (nxt === DONE) {
        return {
          output: text, steps, halted: "final",
          stoppedBy: null, unmetered, unenforced, unretrieved, phases,
        };
      }
      // A stage that finished its say on the way somewhere else. Those words go
      // into the conversation as a step, not as the turn's reply.
      history.push({ role: "assistant", content: text });
      phaseName = nxt;
      continue;
    }

    // Before each call, not after the batch: a ceiling that lets the 41st
    // through because it arrived with the 40th is a suggestion, not a ceiling.
    const ran: ToolCall[] = [];
    const results: string[] = [];
    let outOfCalls: Reached | null = null;
    for (const c of calls) {
      // A refused call costs nothing and is recorded, so it is decided before
      // the ceiling is consulted — the same order Python takes.
      if (c.name in refused) {
        results.push(refused[c.name]);
        ran.push(c);
        continue;
      }
      outOfCalls = reached(limits, meter, clock());
      if (outOfCalls) break;
      // Own property only: a model asking for `constructor` must reach the
      // `no tool named` refusal, not `Object.prototype.constructor`.
      const fn = Object.hasOwn(toolImpls, c.name) ? toolImpls[c.name] : undefined;
      meter.toolCalls += 1;
      results.push(fn ? fn(c.args) : `error: no tool named '${c.name}'`);
      ran.push(c);
    }

    steps.push({ index: i, text, tools: ran, results });
    history.push({
      role: "assistant",
      content: text,
      tool_calls: ran.map((c) => c.name),
    });
    ran.forEach((c, j) =>
      history.push({ role: "tool", name: c.name, content: results[j] }),
    );

    if (outOfCalls) {
      meter.steps = i + 1;
      return ranOut(outOfCalls, i);
    }

    visits[phaseName] = (visits[phaseName] ?? 0) + 1;

    // An `answer` stage answers; that is the whole of what it is for. Any call
    // it made was refused above and is recorded, so nothing is lost by reading
    // the stage the way the author wrote it.
    const outcome = phase.does === "answer" ? "answered" : "used-a-tool";
    const nxt = whereNext(phase, outcome);
    if (typeof nxt !== "string") return nxt;
    if (nxt === DONE) {
      return {
        output: text, steps, halted: "final",
        stoppedBy: null, unmetered, unenforced, unretrieved, phases,
      };
    }
    phaseName = nxt;
  }

  meter.steps = maxSteps;
  return ranOut(
    { ceiling: stepCeiling(maxSteps), at: maxSteps, action: limits.whenItRunsOut },
    maxSteps,
  );
}

export { type Action, type Limits, ceilings };
export { type Does, type Loop, type Phase, DONE, OUTCOMES, instruction, toolsOffered };
