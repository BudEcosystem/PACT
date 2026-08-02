# Compared to Vercel Eve

Eve is the closest prior art and the system PACT was measured against. This page
is deliberately even-handed: it includes where Eve is **better**, because a
comparison that only flatters one side is not a comparison.

## How this was measured

Not from memory. Every claim below came from running commands against
`vercel-eve` on disk:

| | |
|---|---|
| Source read | **171,782 lines**, 1,016 non-test files — all of it |
| Exports extracted | **4,419** |
| Authoring entry points | **27** |
| Documentation read | **28 of 28** files, against the source |
| Hardcoded constants found | **1,045** |

All 27 entry points are categorised in the ledger, and a test fails if one falls
outside.

## Where PACT is ahead

| | Eve | PACT |
|---|---|---|
| **The loop** | `stopWhen: isStepCount(1)` — one occurrence, not authorable | a `loop:` document with stages, routing and per-stage tool scoping |
| **Interception** | impossible *by type*: `(event, ctx) => void` has no return channel | `interceptor` may hide values, stop the run or redirect |
| **A2A** | `a2a`, `agent-card`, `acp` — **0 files** | `pact card` emits an Agent Card |
| **Ceilings** | token budget only | steps, wall-clock, tool calls, tokens, spend — each with an author-chosen action |
| **Exactly-once** | *"make side effects idempotent, or gate them with approval"* — the author's problem | `same-request-key:` |
| **Long-term memory** | *"eve does not have a tenant-aware memory subsystem"* | `remembers:` with lifetime, shape and `never-from:` |
| **Learning** | none | proposals gated on a held-out eval split |
| **Compaction control** | one number (`thresholdPercent`, default 0.9) | ordered strategies, per-part rules, pinning, a separate summariser model |
| **Portability** | the AI SDK | seven targets, two runtimes, byte-identical traces |

Two of Eve's own documents state its gaps directly: *"Do not use `defineState`
for long-term memory"* and *"Authored eve schedules are static files discovered
at build time."*

## Where Eve is better

Stated plainly, because these are real.

**It is a product; PACT is a specification with adapters.** Eve has a dev TUI,
a setup flow, a typed client, React/Vue/Svelte hooks, and a 71-entry integration
catalogue. If you want to ship an agent on Vercel this afternoon, that gap is the
whole story.

**Extensions actually work.** `defineExtension` packages tools, connections,
skills and hooks as an installable unit. PACT's `bundle` kind exists and its
scope check is enforced, but **mounting one is not implemented** — see
[Gaps](gaps.md).

**Durable sessions are native.** Eve's turns run as durable workflows with
checkpointing across restarts and redeploys, on real infrastructure. PACT
declares durability and delegates it; only one of seven adapters has it natively.

**Some ideas we adopted.** Exact-name resolution that fails loudly on a typo,
path-derived identity, and progressive disclosure of skills are Eve's, and PACT
is better for copying them.

## Two claims of ours that were wrong

Recorded because a project that cannot correct itself in public should not be
trusted about anything else.

- **"Eve's compaction window is a fixed count of 10."** Wrong about the
  mechanism. `selectRecentWindowSize` is token-aware — it keeps messages while
  they fit under `threshold − reserve`. But it is capped by a private
  `DEFAULT_COMPACTION_RECENT_WINDOW_SIZE = 10`. The true claim is
  `min(10, what fits)`.
- **"Eve defines approval as exactly two options."** The *render* the person
  sees has two. The *policy* an author writes has four outcomes. PACT's real
  advantage is that its outcomes are schema-carrying YAML rather than a
  TypeScript union returned by code.

## The one number worth remembering

Eve's **1,045 hardcoded constants** include `MODEL_CALL_MAX_ATTEMPTS = 3`,
`COMPACTION_SUMMARY_RESERVE_TOKENS = 2048`, `MAX_PENDING_EVENTS = 64` and
`DEFAULT_WORKFLOW_MAX_SUBAGENTS = 100`. Retry policy, stream backpressure and
fan-out ceilings — none of them authorable.

That is the difference in one line. Not that Eve is badly built — it is very
well built — but that its decisions live in its source, and PACT's live in yours.
