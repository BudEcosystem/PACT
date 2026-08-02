# Eve coverage, and the plan to close it

Companion to `research/notes/eve-source-audit.md`, which holds the measurements
this document reasons from. Everything numbered here was produced by running
commands against `research/repos/frameworks/vercel-eve`.

---

## 1. The structural surface, extracted completely

Not sampled. Every non-test TypeScript file in `packages/eve/src` was parsed for
exported declarations:

| | |
|---|---|
| Non-test files scanned | **1,016** |
| Exported symbols | **4,419** |
| Authoring entry points (`define*`, `disableTool`, `experimental_*`) | **27** |
| PACT schema kinds | **42** |

The 4,419 exports are the *implementation* surface and most of it is internal.
The 27 authoring entry points are what an Eve author can actually write, and
they are the correct comparison against PACT's 42 kinds. A format is not better
for having more kinds; it is better if every entry point the other has is
answered, and the extra kinds pay for themselves.

## 2. Entry point by entry point

**(a)** expressible in PACT's schema · **(b)** declared and delegated to the
runtime · **(c)** deliberately refused · **GAP** — no answer.

| Eve entry point | PACT answer | |
|---|---|---|
| `defineAgent` | `agent` | a |
| `defineTool` | `tool` | a |
| `defineSkill` | `skill` | a |
| `defineState` | `state`, `agent.remembers` | a |
| `defineInstructions` | `agent.instructions` (md or directory) | a |
| `defineChannel` | `port` | a |
| `defineSchedule` | `port` kind `schedule`, `when-this` | a |
| `defineHook` | `watch` | a |
| `defineMcpClientConnection` | `resource` | a |
| `defineOpenAPIConnection` | `resource` | a |
| `defineEval` / `defineEvalConfig` | `evals`, `case`, `eval-rule`, `metric` | a |
| `defineInteractiveAuthorization` | `question`, `policy` | a |
| `defineDynamic` | `variant`, `stage.may-use`, `context-policy` | a |
| `defineSandbox` | declared; host executes | b |
| `defineRemoteAgent` | `teamwork`; host transports | b |
| `defineInstrumentation` | events + `watch`; host exports | b |
| `defineBashTool` `defineReadFileTool` `defineWriteFileTool` `defineGlobTool` `defineGrepTool` | the five privileged built-ins | c |
| `disableTool` | not needed — nothing is implicit | c |
| `experimental_chatgpt` | provider auth; `models/catalog.yaml` + `credential-reference` | b |
| `experimental_workflow` | R5, R42 — a spec naming code to run makes `pact check` decide whether it is safe (row 100) | c |
| `experimental_setAttributes` | `watch` names the moment; the host exports the trace (row 101, §4) | b |
| `defineExtension` | `bundle` — a folder of definitions, no build step, `brings:` held at check time (row 99) | c → a |

**All 27 are now accounted for.** The three that fell outside became rows 99–101
of `eve-capabilities.md`, which is why the count moved 98 → 101 and (b)/(c)
moved 21 → 22 and 28 → 30. Adding them broke four ledger tests — the §8 prose
totals, the §8 table, the per-area row, and row 101's pointer at a §4 row that
did not exist — and each named its own fix. `eve_inventory.rs` holds the result:
every row carries one letter, every (a) row cites a field the schema really has,
every (b) row quotes a §4 row, every (c) row points at a written refusal, and the
file's own stated totals are recomputed from its rows.

---

## 3. What Eve does not have

Measured by case-insensitive file count across `packages/eve/src`, tests
excluded: `a2a` **0**, `agent-card` **0**, `acp` **0**, `blackboard` **0**,
`debate` **0**, `swarm` **0**.

- **No agent-to-agent protocol.** Remote agents are eve-to-eve over a private
  endpoint. Nothing speaks A2A, agent cards, or ACP.
- **No multi-agent pattern but the tree.** No debate, blackboard, market,
  voting, swarm, actor mailbox, supervisor or reflection loop. Siblings cannot
  address each other; a running child is unaddressable.
- **No authorable loop.** `stopWhen: isStepCount(1)` — one occurrence in the
  package, `harness/tool-loop.ts:907`.
- **No mutating hooks.** `(event, ctx) => void | Promise<void>`
  (`public/definitions/hook.ts:83`) has no return channel, so interception is
  impossible by type, not merely unimplemented.
- **No capability requirements, SLOs or spend caps.** Token budgets only.
- **No learning or long-term memory.** Its docs say so directly.
- **Compaction is one authorable number.** `thresholdPercent` (default `0.9`,
  `execution/session.ts:7`) is the whole surface; heuristics, window and pinning
  are private.

## 4. What PACT does not have

Found by reading Eve, and currently absent here.

**G9 — state that survives tidying.** Eve's compaction resets read-before-write
tracking and re-injects the todo list, because *"a write afterward re-reads the
file whose read evidence was summarized away"*. PACT's `always-keep:` pins
**messages**. It has no notion of **derived state a summary must not destroy**,
so a PACT context policy would silently invalidate exactly the evidence a safety
check depends on. This is the most serious gap in this document.

**G10 — packaged capability sets.** `defineExtension` publishes tools,
connections, skills, instruction fragments and hooks as one installable unit.
PACT has no distribution unit at all: a workspace either contains a capability
or does not. (This also corrects the plan's §2 claim that Eve has "no sharing" —
it has none *between subagents*, which is true, but it has a real mechanism
*between agents*.)

**G11 — inheriting the parts you did not restate.** `...writeFile` keeps the
default's description, schema and durable state key; omitting the spread is a
documented choice that gives your replacement its own context. PACT has no
partial-override semantics.

**G12 — capability-derived availability.** Eve advertises only what the current
session can use: `agent` is root-only, `load_skill` appears only when skills are
declared. PACT scopes tools per stage (G1) but cannot express "present only when
the agent has X".

**G13 — a dispatch-order contract across kinds.** Eve fixes the order in which
its reactive machinery runs — channel handler, then metadata projection, then
hooks, then dynamic resolvers — and calls it *"structural, not incidental"*
(`concepts/sessions-runs-and-streaming.md`). PACT gained `runs-at` this session,
which orders **interceptors against each other**, and has nothing that orders
`interceptor` against `watch` against a variant resolver. Two authors writing a
redaction rule and a watcher have no way to know which sees the value first.

**G14 — scoped model precedence.** Eve resolves the model at
`session.started` / `turn.started` / `step.started` with precedence
**step > turn > session > fallback** (`guides/dynamic-capabilities.md`). PACT's
`model:` is single-valued. The doc also records the operational reason this
matters — *"prompt caches are per model, so switching mid-session re-ingests the
conversation at uncached prices"* — which is a warning PACT cannot currently
give because it cannot express the switch.

---

## 5. The generalisations

The instruction was to abstract, not to port feature by feature. Each row below
replaces several Eve mechanisms with one construct.

| # | Construct | Replaces |
|---|---|---|
| **G9** | **Survivable state** — a declared fact with a lifetime independent of the messages that produced it, and a rule for what invalidates it | read-before-write tracking, todo re-injection, and every future "the summary ate my evidence" bug |
| **G10** | **Bundle** — a named, versioned set of definitions a workspace mounts, resolved by the same loader, with no build step and no code execution | `defineExtension`, the eve-catalog's 71 entries, and the skills-copying Eve documents as unavoidable |
| **G11** | **Derivation** — `based-on:` for any kind, already shipped for `loop`, made total: restate what differs, inherit the rest | tool override-by-slug, the spreadable defaults, and the "two files differing in two lines" duplication the interceptor work already hit |
| **G12** | **Availability predicate** — a capability is offered when its condition holds, written where the capability is | root-only `agent`, conditional `load_skill` / `connection_search`, and the per-session tool advertisement |

**Why these four and not more.** Each is a *closure* of something PACT already
has: `always-keep:` almost reaches G9, `based-on:` already exists for one kind,
`may-use:` is an availability rule with a fixed condition, and the loader already
resolves cross-document names, which is most of G10. None requires a new
subsystem; all four are the general form of a special case already shipped.

---

## 6. Plan — built

Every phase below is in the tree with tests. Each row states what it *refuses*,
because a construct that refuses nothing is the defect this project keeps
finding in itself.

| Phase | What landed | What it refuses |
|---|---|---|
| **A** — close the ledger | rows 99–101; four ledger tests updated | an Eve entry point in no category; a (b) row pointing at a §4 row that does not exist |
| **B** — G9 survivable state | `state.survives-shortening:`, `stops-being-true-when:`, `facts.py`, restating after the ladder | a shortening that destroys the evidence a `policy:` reads — the check then passes on nothing, which is worse than failing |
| **C** — G11 derivation | `derive.rs`, `based-on:` on 14 collections, resolved before validation | a ring (named as `a → b → a`); a base nothing answers to; and a deep merge that would silently keep a power the author narrowed away |
| **D** — G12 availability | `available-when:` on tool/skill/resource, `available.rs` | a capability whose condition its own agent can never meet, so it loads and is never once offered |
| **E** — G10 bundles | `bundle` kind, `workspace.bundles`, `bundles.rs` | a bundle contributing a kind outside `brings:` — the supply-chain case where v2.1 starts shipping `policies/` and nobody here approved it |
| **F** — G13 one order | `WATCHING_RUNS_AT` on the interceptor scale, `test_one_order_across_kinds.py` | moving an emit above the chain to "log it before anything changes it", which would put card numbers in an audit file forever |
| **G** — G14 scoped model | `agent.model-for-checking:` with `needs-also: [loop]` | a model id the catalogue does not know; the field without a `loop:` for it to apply to |
| **H** — Eve's two fail-open defaults | `test_two_defaults_eve_gets_wrong.py` | a policy choice meaning "ask nobody"; a `watch` gaining a field that could carry author code, which is how Eve's audit logger ends a session |

**Two of these are narrower than the plan first stated, and the narrowing is the
finding.** G14 offers one extra scope, not Eve's three: a model per *step* is
what makes Eve's own cache warning necessary, and the case authors actually have
is "think cheaply, check well", which is a stage. G13's safety property already
held by accident — the bus emits after the chain — so the work was to hold it,
not to fix it.

**One justification in this document is now stale.** G11 cited two near-identical
interceptor files as the cost of having no derivation. They no longer exist: an
earlier round made `when:` a list and merged them. The mechanism is still right
and is proven on a fresh derived interceptor instead, but the example that
motivated it was fixed by a different route.

## 7. Standing of each claim

- **Documentation: complete.** 28 of 28 files read against source. Six gaps in
  Eve and six in PACT came from there; two of our own claims were corrected —
  the compaction window (token-aware but capped at a private 10, not "a fixed
  count of 10") and what "two options" meant about approvals (the *render* has
  two, the *policy* has four).
- **Source: every line read.** `LINES READ: 171782  FILES: 1016` — the whole
  non-test tree, parsed for exports and for every `UPPER_CASE` constant. That is
  what produced the general form of the compaction finding: **1,045 hardcoded
  constants**, including `MODEL_CALL_MAX_ATTEMPTS = 3`,
  `COMPACTION_SUMMARY_RESERVE_TOKENS = 2048`, `MAX_PENDING_EVENTS = 64` and
  `DEFAULT_WORKFLOW_MAX_SUBAGENTS = 100` — retry policy, stream backpressure and
  fan-out ceilings, none of them authorable.
- **Authoring surface: complete and held.** All 27 entry points categorised, and
  `eve_inventory.rs` fails if one falls outside.
- **All eight phases built**, 1,515 tests, clippy clean, `tsc` clean.

### What a later round should still do

Not caveats on the above — work this document can name precisely because the
measurement exists.

1. **`bundle.from:` resolves nothing yet.** The kind, the scope check and the
   refusal are real; actually reading another folder into the tree is the host's
   half, and no host in this repo does it. `bundles.rs` is silent on a bundle
   with nothing mounted, deliberately, so the check bites the moment one is.
2. **G9 is Python-only.** `facts.py` and the restating live in the Python
   harness; the TypeScript port will report `state` on `unenforced` as it does
   for the other governance keys, which is honest but is a lattice difference.
3. **Implementation detail below the entry points remains sampled.**
   `harness/compaction.ts` was read line by line because a claim about it was in
   dispute, and that is the standard worth repeating: read deeply where a claim
   is contested, not everywhere on principle.
