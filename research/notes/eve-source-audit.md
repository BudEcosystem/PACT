# Eve, read at source — audit log

**Purpose.** `eve-teardown.md` is a structural teardown and `eve-capabilities.md`
is a numbered inventory. Neither records *how much of the source was actually
opened*, so neither can be checked for coverage, and a claim in them cannot be
told apart from a claim about them. This file is the third thing: a measured
audit that states its own coverage, cites file and line for every claim, and
records where the earlier analysis was imprecise.

Everything below was produced by running commands against
`research/repos/frameworks/vercel-eve` on disk. Nothing here is recalled.

---

## 1. What Eve actually is, measured

| | |
|---|---|
| TypeScript in `packages/eve/src` | **323,142 lines** across **1,597 files** |
| — non-test | **171,782** |
| — test | **151,360** (0.88 test lines per source line) |
| Whole repo, `.ts` + `.tsx`, excluding `node_modules` | **379,895** |
| Packages | `eve`, `eve-catalog` |
| Markdown documentation files | **106** |

**The plan's "171,782 lines" is correct and means non-test TypeScript under
`packages/eve/src`.** Recording the definition matters: the same tree is 323,142
lines if you count its tests and 379,895 if you count the whole repo, and a
comparison against PACT that silently switched definitions would be worthless.

### Module map

| Module | Lines | Files | What it is |
|---|---:|---:|---|
| `public` | 52,097 | 241 | the authoring surface — `define*`, channels, hooks |
| `internal` | 51,111 | 284 | shared implementation |
| `cli` | 45,659 | 160 | CLI and the dev TUI |
| `execution` | 37,966 | 183 | session/turn/step execution |
| `setup` | 34,663 | 183 | scaffolding and onboarding |
| `harness` | 33,210 | 103 | the model loop, compaction, approvals |
| `runtime` | 18,734 | 129 | durability, workflow |
| `evals` | 9,565 | 55 | eval runner |
| `discover` | 7,580 | 28 | project discovery |
| `compiler` | 6,041 | 31 | the compiled manifest |
| `client` | 5,933 | 30 | typed client |
| `context` | 4,895 | 33 | **dependency injection**, not compaction |
| `channel` | 4,319 | 36 | channel plumbing |
| `shared` | 4,288 | 62 | utilities |
| `protocol` | 2,131 | 6 | the event/message protocol |
| `services` | 1,949 | 14 | **Vercel dev-client auth** — not agent surface |
| `source-change` | 1,156 | 8 | source watching |
| `react` / `vue` / `svelte` | 1,809 | 9 | framework bindings |
| `sandbox` | 35 | 1 | sandbox entry |

Two of these were assumed rather than checked by the earlier analysis and are
**not** what their names suggest:

- **`context/` is dependency injection**, not context management. Its largest
  files are `dynamic-tool-lifecycle.ts` (402), `dynamic-skill-lifecycle.ts`
  (243), `dynamic-model-lifecycle.ts` (148). Compaction is not here.
- **`services/` is Vercel dev-client authentication** —
  `services/dev-client/vercel-auth-error.ts` (195), `request-headers.ts` (148),
  `credential-gate.ts` (95). It has no agent-facing surface, which is why no
  prior note cites it. Its absence from the inventory is correct.

### Coverage of the prior analysis

Measured by testing whether each of the 1,597 source paths (or its basename)
appears anywhere in `eve-teardown.md`, `eve-capabilities.md`,
`docs/50-NOT-COPIED.md`, `docs/20-ARCHITECTURE-DRAFT.md` or the plan:

> **251 of 1,597 files cited — 15%.**

Thinnest against the areas the goal named: `context/` 3 of 33, `channel/` 8 of
36, `harness/` 16 of 103, `execution/` 18 of 183, `cli/` 9 of 160, `setup/` 14
of 183, `services/` 0 of 14.

This number is not itself a defect — a capability inventory does not need to
cite every file, and `cli/`, `setup/` and `services/` are largely not agent
surface. It is recorded so that any claim of completeness has to argue against
a number instead of an impression.

---

## 2. Claims verified at source

Each row was checked by reading the cited line, not by search alone.

### 2.1 The loop is a constant

`harness/tool-loop.ts:907` — `stopWhen: isStepCount(1)`.

**One occurrence in the package.** `isStepCount` is imported once
(`tool-loop.ts:8`) and used once. There is no other `stopWhen` anywhere in
`packages/eve/src`. The continue-decision is not authorable, and the file that
holds it is 2,547 lines.

### 2.2 Hooks are observe-only — by type, not by convention

`public/definitions/hook.ts:83`:

```ts
export type StreamEventHook<TEvent> = (event: TEvent, ctx: HookContext) => void | Promise<void>;
```

The return type is `void | Promise<void>`. **There is no channel through which a
hook could return a changed event, veto a step, or rewrite a prompt** — the
observe-only property is enforced by the signature, so no amount of authoring
discipline can produce interception. This is stronger evidence than the earlier
note's assertion that hooks "are observe-only": it cannot be otherwise.

### 2.3 Exactly 28 hook events, and the list is closed

`public/definitions/hook.ts:17–48` defines `HookEventMap` as a `readonly`
interface of exactly 28 members:

```
action.result · actions.requested · authorization.completed ·
authorization.required · compaction.completed · compaction.requested ·
input.requested · message.appended · message.completed · message.received ·
reasoning.appended · reasoning.completed · result.completed ·
session.completed · session.failed · session.started · session.waiting ·
step.completed · step.failed · step.started · subagent.called ·
subagent.completed · subagent.event · subagent.started · turn.cancelled ·
turn.completed · turn.failed · turn.started
```

`HookEventType = keyof HookEventMap` (line 49), so the vocabulary is closed at
the type level: an author cannot name an event Eve does not already publish.

### 2.4 Whole feature families are absent

Case-insensitive file counts across `packages/eve/src`, excluding tests:

| Term | Files |
|---|---:|
| `a2a` | **0** |
| `agent-card` | **0** |
| `acp` | **0** |
| `blackboard` | **0** |
| `debate` | **0** |
| `swarm` | **0** |
| `handoff` | 15 |
| `mcp` | 34 |
| `compact` | 56 |
| `trigger` | 61 |
| `schedule` | 67 |
| `hook` | 196 |
| `channel` | 298 |

The six zeroes confirm the earlier analysis's central gap claim by measurement:
**no agent-to-agent protocol, and no multi-agent pattern beyond the delegation
tree.**

---

## 3. Corrections to the earlier analysis

### 3.1 The compaction window is token-aware, and capped

**The plan says** Eve's recent window is "a fixed count of 10" and proposes
replacing it with something "token- or predicate-based".

**What the code does.** `harness/compaction.ts:413` `selectRecentWindowSize`
walks the history backwards and keeps a message only while it fits:

```ts
const maxKeep = Math.min(config.recentWindowSize, Math.max(messages.length - 1, 0));
const reserve = resolveCompactionSummaryReserve(config);
...
  if (recentTokens + messageTokens + reserve > config.threshold) break;
```

So the selection **is** token-aware, and it reserves room for the summary
itself (`resolveCompactionSummaryReserve`, line 440:
`min(2048, max(64, threshold/4))`).

**But** `maxKeep` caps it at `config.recentWindowSize`, and that value comes
from `DEFAULT_COMPACTION_RECENT_WINDOW_SIZE = 10` at `execution/session.ts:6` —
a module-private constant with no authoring surface.

**The accurate claim** is therefore `min(10, whatever fits)`: a model with a
large context window still cannot retain an eleventh recent message, and no
author can raise the number. That is a real limitation, and a narrower one than
the plan stated. PACT's G3 justification should say this rather than "a fixed
count of 10", which is wrong about the mechanism while right about the ceiling.

### 3.2 `COMPACTION_HEURISTICS` has one element — confirmed

`harness/compaction.ts:122`:

```ts
const COMPACTION_HEURISTICS: readonly CompactionHeuristic[] = [toolResultCapHeuristic];
```

Module-private, one entry, no authoring surface. The earlier claim stands
exactly as written.

---

## 4. The documentation, read against the source

**Corpus.** 106 markdown files repo-wide; the authored documentation set is
`docs/` — **28 files, 4,404 lines**, in four groups: `concepts/` (5),
`guides/` (9 + 2 deployment), `patterns/` (4), `reference/` (3), plus 4 at the
root.

The useful question is not what the docs say but **whether they are true of the
code**, so each claim below was checked against the file that implements it.
This is the same method §3.1 used, and it is the method that found the window
discrepancy.

### 4.1 Claims checked, and they hold

| Doc claim | Source | Verdict |
|---|---|---|
| `thresholdPercent` "0.9 by default" (`concepts/default-harness.md`) | `execution/session.ts:7` `DEFAULT_COMPACTION_THRESHOLD_PERCENT = 0.9` | **true** |
| "There is no per-tool hook to configure" for compaction | no hook surface in `harness/compaction.ts` | **true** |
| A `disableTool()` filename that matches nothing "fails instead of silently doing nothing, so a typo surfaces at build time" | exact-name resolution | **true**, and it is one of Eve's best ideas |

### 4.2 What the docs reveal that the inventory understated

**Compaction is partly tunable, and the earlier note read as though it were
not.** `compaction: { thresholdPercent: 0.75 }` is authorable in `agent.ts`. So
Eve gives the author the **trigger**, as a percentage of the context window —
and nothing else: not which heuristics run, not what is pinned, not how much is
kept. The honest statement of the gap is "one authorable number, and the rest is
private", which is narrower and more defensible than "one compaction algorithm".

**Compaction carries framework tool state across the summary.**
`concepts/default-harness.md`: it "resets read-before-write tracking (so a write
afterward re-reads the file whose read evidence was summarized away) and
re-injects the active todo list". This is a genuinely good behaviour with a
clear rationale — a summary that silently destroys the evidence a safety check
depends on would make the check unsound. PACT's context policy has no equivalent
concept of *state that must survive tidying*, and `always-keep:` pins messages,
not tool state. **This is a real gap in PACT, found in Eve's docs rather than in
its source.**

**The built-in tool count reconciles.** The docs list **12** built-ins (`bash`,
`read_file`, `write_file`, `glob`, `grep`, `web_fetch`, `web_search`, `todo`,
`ask_question`, `agent`, `load_skill`, `connection_search`); `eve/tools/defaults`
exports **9**; and the "**5** hardcoded built-in tools" PACT refuses in
`50-NOT-COPIED.md` are precisely the shell-and-file group the doc names as a
set — `bash`, `read_file`, `write_file`, `glob`, `grep`. Three numbers, three
scopes, no contradiction. Worth recording because a reader meeting 5, 9 and 12
in three documents would reasonably suspect one of them is wrong.

**`experimental_workflow` is loop engineering by model-authored code.** The
model orchestrates the agent's own subagents "from model-authored JavaScript,
all as one durable step", root-only, `maxSubagents` default 100. This is Eve's
answer to the problem G1 solves with an authored loop document. The divergence
is deliberate on PACT's side and already recorded: R5 and R42 refuse exactly
this shape, because a spec that names code to run makes `pact check` decide
whether that code is safe. Eve accepts that trade; PACT refuses it. **Neither is
a defect — but `50-NOT-COPIED.md` should name `experimental_workflow` as the
thing being refused**, and currently names only "Vercel Workflow coupling".

### 4.2a The rest of the corpus — all 28 files read

Findings that change PACT's position, one line each, cited to the doc.

**Eve's own statements of its gaps** — these are Eve's words, not inference:

- *"eve does not have a tenant-aware memory subsystem."* — `patterns/multi-tenant-memory.md`. The documented answer is auth + dynamic instructions + your own tools + your own database.
- *"Do not use `defineState` for long-term memory."* — same file.
- *"Authored eve schedules are static files discovered at build time."* — `patterns/dynamic-scheduling.md`. Dynamic scheduling is a one-minute cron dispatcher over rows in a store you build, with an atomic lease you implement.
- *"eve does not maintain a durable FIFO queue of user messages for a session."* — `concepts/execution-model-and-durability.md`. Bursts require *"your own per-session queue in the channel or app layer"*.
- *"There is no per-tool hook to configure"* for compaction — `concepts/default-harness.md`.

**Two safety defaults that fail open**, both material:

- **Approval defaults to none.** *"By default, omitted `approval` behaves like `never()`, so tool calls may execute without human approval"* — `tools/human-in-the-loop.md`. A tool is unguarded unless the author remembers to guard it.
- **A thrown hook kills the turn.** *"A thrown handler propagates … and surfaces as `turn.failed`. If a hook subscribed to a failure-cascade event also throws, it escalates to `session.failed`"* — `guides/hooks.md`. An audit-logging hook can end the session it was only meant to observe.

**Idempotency is the author's problem, and approval is the only lever.**
`concepts/execution-model-and-durability.md`: *"A step interrupted mid-execution
re-runs, so make non-idempotent side effects like charges or emails idempotent,
or gate them with approval."* `tools/human-in-the-loop.md` repeats it: *"Skipping
approval on scheduled turns means any non-idempotent side effect will re-fire if
a step replays, so pair this pattern with idempotency keys or `once()`."*
**PACT's `same-request-key:` is the declarative answer to exactly this**, and
this is the evidence that the problem is real rather than invented.

**A structural ordering guarantee PACT lacks.**
`concepts/sessions-runs-and-streaming.md` fixes a four-step dispatch order —
channel handler → metadata projection → hooks → dynamic resolvers — and says
*"The order is structural, not incidental."* (`guides/hooks.md` states the same
sequence as three steps, folding emit and projection; a minor internal
inconsistency in Eve's own docs.) PACT orders interceptors against each other
(`runs-at`, added this session) but has no contract for the order of *different
kinds* of reactive machinery.

**Dynamic-model precedence, and why it matters commercially.**
`guides/dynamic-capabilities.md`: resolvers run at `session.started`,
`turn.started` or `step.started`, precedence **step > turn > session > fallback**
— and *"prompt caches are per model, so switching mid-session re-ingests the
conversation at uncached prices."* PACT's `model:` pin is single-valued; it has
no scoped precedence and no warning about the cache cost of switching.

**Prompt-injection posture.** `patterns/multi-tenant-memory.md` instructs
*"Never accept a tenant or user id from the model"* and *"Treat memory values as
user-provided facts, never as system instructions."* This is authoring advice,
enforced by nothing. PACT has no construct for *this content is data, not
instruction* either — a shared gap, not a PACT deficit.

**Where Eve and PACT already agree.** `concepts/security-model.md`: *"Authored
markdown is data … The code-capable engines (`---js` / `---javascript`, which
would `eval()` the frontmatter body the moment the file is parsed) are
disabled."* Eve refuses executable frontmatter for the same reason PACT does
(R5/R42). The divergence is narrower than the plan implies: Eve still runs
`instructions.ts` at **build time** into the compiled manifest, and
`experimental_workflow` executes **model-authored** JavaScript. PACT refuses both
of those; it does not refuse something Eve permits universally.

**Auth fails closed** (`concepts/security-model.md`): routes 401 by default and
admitting anonymous callers *"takes an explicit `none()`"*. Good, and matched by
PACT's egress posture.

### 4.2b A correction to our own claim about approvals

The plan says Eve defines approval *"structurally as exactly two options named
approve/deny"*. `tools/human-in-the-loop.md` shows the **policy** return type is
richer: `"user-approval" | "not-applicable" | "approved" | "denied"`, with
`{ type, reason }` when the model should be told why, plus boolean back-compat.

The accurate claim is narrower: what the **person** is offered is a two-option
render (approve/deny buttons), while the **policy** an author writes has four
outcomes. PACT's advantage is therefore not "more than two outcomes" — it is
that PACT's outcomes are schema-carrying and authorable in YAML, where Eve's are
a TypeScript union returned by code. G7's justification should say that instead.

### 4.3 Ideas of Eve's that PACT should be measured against

Three, all from the docs rather than the source, all currently better in Eve:

1. **Exact-name resolution failing loudly** — a `disableTool()` for a
   non-existent slug is a build error. PACT reached the same standard for
   cross-document references only in this session's `names:` work.
2. **Override-by-slug with a spreadable default** — `...writeFile` keeps the
   description, schema and durable state key; dropping the spread is a
   documented, deliberate choice. PACT has no notion of *inheriting the parts of
   a definition you did not restate*.
3. **The harness advertises only the tools available to the current session** —
   availability is computed per session (`agent` root-only, `load_skill` only
   when skills are declared). PACT computes stage-scoped tools (G1) but has no
   equivalent for *capability-derived* availability.

---

## 5. Coverage

**Documentation: complete.** All 28 files of `docs/` (4,404 lines) have been
read and their load-bearing claims recorded in §4. Six gaps in Eve and two in
PACT were found there, and two of our own claims were corrected (§3.1, §4.2b).

**Source: the authoring surface is complete; the implementation is sampled.**
Every non-test file (1,016) was parsed for exported declarations, giving all
**4,419 exports** and all **27 authoring entry points** — see
`docs/60-EVE-COVERAGE-AND-PLAN.md` §2, where each of the 27 is assigned a
category. That is completeness at the level the comparison needs: an entry point
is what an Eve author can write, and PACT must answer each one.

Below that level, coverage is partial and deliberately so. `harness/compaction.ts`
was read line by line because a doc claim about it was in question (§3.1); the
same treatment has not been applied to `internal/` (284 files), `execution/`
(183) or `channel/` (36). What that would buy is *implementation* detail behind
entry points already categorised — worth doing when a specific claim is in
doubt, as compaction was, and not otherwise. Reading 171,782 lines to re-derive
a categorisation the export surface already fixes would be motion, not evidence.

`setup/` (183) and `cli/` (160) are tooling, not agent surface; `services/` (14)
is Vercel dev-client auth. None affects what PACT must express.
