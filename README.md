# PACT — Portable Agent Contract & Topology

A specification for AI agents that is **portable across frameworks and across
model sizes**, whose native form is **a folder of YAML and Markdown**, and whose
portability claims are **measured rather than asserted**.

```bash
cargo run -p pact-cli -- check examples/refund-desk
```

```
OK — examples/refund-desk loaded cleanly (498 settings).
```

That example is a supervisor agent, two specialists, MCP tools, a written
policy, an eval suite and a learning policy — **and no code you have to write**. The one Python file in the tree is a
six-line helper the refund policy carries as a payload; nothing in PACT
requires it, and deleting it leaves a working agent.

---

## The idea in one paragraph

Agents are not portable today because the industry models them as **programs**
and tries to translate the program. Programs do not translate: LangGraph's
checkpointed state machine, AutoGen's actor mailbox and Pydantic AI's typed run
encode genuinely different semantics. PACT models an agent instead as a
**contract about behaviour** (what it must achieve — capabilities, evals, SLOs,
policy) plus a **plural space of strategies** for satisfying it (instructions,
topology, tools, loop). The contract is portable and invariant. The strategy is
*selected* for a target. And because agent behaviour is probabilistic, fidelity
is not declared — it is **measured against the author's own eval suite**, which
becomes the correctness oracle for framework portability, model substitution,
and self-improvement alike.

The closest correct analogy is a **cost-based query planner**: SQL declares
*what*, the planner chooses *how* against statistics and a cost model. PACT
declares the agent's *what*; the resolver plans the *how* against a model
catalogue and an SLO cost model; and evals replace relational algebra as the
correctness oracle.

---

## The one rule that makes the filesystem work

> **A directory is a field; a field may be a directory.**

```
agents/refund-desk/agent.yaml          agents/refund-desk/agent.yaml
  name: Refund Desk           ≡          name: Refund Desk
  instructions: Be precise.            agents/refund-desk/instructions.md
                                         Be precise.
```

Both produce the identical document. A beginner writes one file; an expert
writes a tree; nobody learns a slot table. Any future field gets its directory
form for free — which is what makes the format extensible without touching the
core.

Vercel's Eve proved path-as-identity works, but hard-codes an 18-case slot
table, allows escape hatches only in TypeScript, and — decisively — **its
runtime never reads the authored tree**; it loads generated ESM produced by a
build step that *executes author code*. PACT's tree is executable as-is.

---

## Status

| | |
|---|---|
| **Design** | Thesis, 28 binding decisions, FRD (120 requirements), implementation plan — complete |
| **Research** | 14 source-grounded studies, ~15,750 lines, over 140 repos (~15 GB) + 57 papers |
| **Code** | Loader, diagnostics, schema engine, CLI, harness, resolver, evals, SLO — **3188 tests (1095 Rust + 2093 adapter), clippy clean, TypeScript type-checked** |
| **Adapters** | **All 7 named targets**, proven against one shared conformance suite |

### What works today

```bash
./scripts/test-all.sh          # 3188 tests, Rust + 7 adapters, fully offline
```

**Framework portability is proven, not asserted.** One folder — loaded by the
Rust CLI — executes over **all seven targets** and produces *byte-identical
traces, tool sequences and model-call counts*. That claim is bounded and the
bound is written down: it covers `instructions:`, `tools:`, `skills:`,
`knowledge:`, `team:`, `answers-with:`, the `loop:` and the `limits:` ceilings,
and **not** the ten governance keys the TypeScript port reports on
`unenforced` — nine written at the top of the agent's own file, plus the `asks:`
line on a loop stage that stops to ask a person, which stops both ports in the
same stage and is put to somebody only by the Python one — nor the documents
under `knowledge/`, which nothing on that port
can look anything up in and which it names on `unretrieved` for every set an
answer did not come from — see
[§7.28 *What "byte-identical across all seven targets" covers, and what it does not*](docs/20-ARCHITECTURE-DRAFT.md).
That ten counts the *excluded keys*, not the lines a run prints: the same channel
also carries `team:` — which **is** inside the claim, since the names are offered
to the model, and says only that asking one comes back as an error here — and one
line per `limits:` key this port does not read, each under its own `limits.`
prefix.
Each takes the framework's *lowest* seam, so none of them gets to own the loop:

| Target | Seam taken |
|---|---|
| Pydantic AI | `direct.model_request` — below `Agent` |
| LangGraph | `func.entrypoint` / `task` — the functional API, not `StateGraph` |
| LangChain | `BaseChatModel` — below chains, AgentExecutor and LCEL |
| AutoGen | `ChatCompletionClient` — below `AssistantAgent` and group chat |
| OpenAI Agents | `models.interface.Model` — below `Runner`, handoffs and guardrails |
| Anthropic | `messages` content blocks — explicitly *not* the hosted session loop |
| Vercel AI SDK | a `LanguageModelV2` provider with `stopWhen: stepCountIs(1)` |

The Vercel target runs in **Node**, so its harness is a second, independent port
of the same specification — and it agrees with the Python one on the loop, the
ceilings and the stage routing. That is cross-*runtime* agreement, which is a
stronger claim than one implementation agreeing with itself.

It is a smaller port and it **says which parts it is smaller by**. A spec
carrying `interceptors:`, `context-policy:`, `policy:` or `teamwork:` runs there
without them and comes back with each of those named on `unenforced` — because a
runtime that silently drops a governance line is worse than one that refuses the
document. It also has no durable resume, and publishes
`durable_resume: unsupported` rather than leaving that to be discovered.

Each publishes a capability lattice, and the lattice records real differences
rather than flattering uniformity:

```
              model_cal | tool_call | text_with | parallel_ | streaming | durable_r | connected
reference     native    | native    | native    | native    | unsupport | unsupport | unsupport
pydantic-ai   native    | native    | native    | native    | emulated  | unsupport | native
langgraph     native    | emulated  | native    | emulated  | emulated  | native    | unsupport
langchain     native    | native    | native    | native    | emulated  | unsupport | unsupport
autogen       native    | native    | emulated  | native    | emulated  | unsupport | unsupport
openai-agents native    | native    | native    | native    | emulated  | unsupport | unsupport
anthropic     native    | native    | native    | native    | emulated  | unsupport | unsupport
vercel-ai     native    | native    | native    | native    | emulated  | unsupport | unsupport
```

Seven rows for seven targets, plus `reference` — the framework-free control arm,
which is not a target. `vercel-ai` was missing from this table for a round, so
the instrument meant to declare what each target cannot do was silent about the
one target that runs in another language.

LangGraph is the only target with native durable resume. AutoGen cannot carry an
assistant sentence *and* tool calls in one result — its text rides in `thought`,
so the value survives and the difference is declared instead of hidden.

`connected` is `connected_tools`, truncated like the other headings: whether a
tool's `connect:` line reaches the system it names. Pydantic AI is the only
target that can — `mcp_bridge` turns a `connect:` into that runtime's own client
— and every other target binds a model and nothing else, so a `connect:` tool
reaches the model as a name and the call comes back `error: no tool named …`.
Declared here rather than discovered there.

**The HITL kill test passes on all six Python targets.** The Vercel target has
no durable resume and declares `durable_resume: unsupported`, so it is not in
that suite — counting the framework-free control arm as the seventh made "all
seven" a sentence about six. Request approval mid-parallel-tool-batch,
serialise the paused state, drop every object, resume in a fresh transport —
each tool executes exactly once, the decision is honoured, and the resulting
history is identical across frameworks. The architecture named this the one
fixture that decides everything: *"if it passes on both adapters, D12 is proven."*

**Model portability is measured, and `--choose-model` is the door onto it.** The
resolver filters the catalogue on `needs:`, runs the author's eval cases against
each candidate strategy, refuses when none passes, and names the cheapest that
would. It has a shipped caller: `scoring.py:1005` calls `resolve()`, behind the
`--choose-model` flag its own usage text advertises, so a user can now ask both
*"does model X pass?"* and *"which model should I use?"*. That closes A2 in
[the gap register](docs/70-PRODUCTION-GAP-REGISTER.md), and the report below is
the shape that command prints. The transcript itself is still produced by the
test suite rather than pasted from a run, because it needs a machine serving
those models; what is shown is the renderer's own output.

```
PORTABILITY: PASS for claude-haiku-4-5  (agent Refund Desk, strategy decomposed)
  measured against: the hand-authored frontier strategy
  score 100% vs bar 70%

PORTABILITY: FAIL for llama3.2-1b-instruct  (agent Refund Desk, strategy authored)
  measured against: the hand-authored frontier strategy
  score 0% vs bar 70%
  llama3.2-1b-instruct thinks at the 'simple' rung and this needs at least 'steady'
RECOMMENDED: claude-haiku-4-5 — passes at 100% using the 'decomposed' strategy, at 0.001/1k tokens
```

A mid-tier model fails on the authored strategy and passes on a decomposed one —
the contract never changes, only the strategy. A model that cannot meet the
contract is refused, and the cheapest one that *does* pass is named.

**Those are real ids and real prices.** The candidates and the price list come
from `models/catalog.yaml`, which ships with the distribution and is read from
disk with no network call. For a round they were three invented models with
invented prices, held in one test, so the cheapest-passing claim was about
nothing anyone could serve. The requirements come from the agent's own `needs:`
block, and a workspace whose `allow-egress:` is empty is never offered a model it
would have to reach over a network — it is told which line to change instead.

**Evals are config only, and the whole DeepEval surface is reachable.** Every
metric the installed DeepEval exports — 47 of them here — is named by URI under
`evals.metrics:`, with no import, no subclass and no callable anywhere on the
author's path:

```yaml
metrics:
  - uri: deepeval:faithfulness
    threshold: 0.8
```

Deterministic `pact:` scores run first, so a fully decidable suite never invokes
a model — which is what lets the suite run air-gapped. The judge is the one the
author already named in `graded-by:`, resolved through `models/catalog.yaml` and
refused by the same `allow-egress:` walk as every other model binding; there is
no default and no fallback, because a metric graded by a model nobody wrote down
is the air-gap quietly ending. DeepEval defaults its own judge to GPT and demands
an API key *at construction time*, so a score PACT cannot grade is reported with
a line to type rather than reaching for a network. The six legacy RAGAS wrappers
are excluded deliberately: they hard-import `ragas` and HuggingFace `datasets`,
so they belong behind a `ragas:` provider — and an author who writes one is told
that in a sentence naming the file, the line and what to type instead.

**Cost and step ceilings stop a run; latency promises are reported.** The
ceilings in `limits:` — steps, tool calls, wall-clock, tokens, spend — are
enforced mid-run by `Limits.reached`, each with the author's own
`when-it-runs-out:` action. The *latency* half (`first-reply-within`,
`per-word-under`, `feel:`) is measured and reported, not enforced: `slo.py` says
so in its own first line, *"This module reports; it does not stop a run."*

This paragraph used to claim both halves stopped a run, via a typed `SloBreach`.
That construct was deleted — nothing in `src/` ever built one, so one ceiling
appeared to have two enforcers — and the paragraph outlived the code by several
rounds. TTFT is still measured at the first *token* rather than the first step,
because an agent whose first act is a tool call has not replied yet; and a
percentile over too few samples still returns `UNDECIDED` rather than a number
that reads like evidence.

Introduce a mistake and you get told exactly what to do about it:

```
error: 'measured-at' should be one of: p50, p90, p95, p99, mean, max, but it is some text.
  --> agents/refund-desk/limits.yaml:9:14
  |
9 | measured-at: usually
  |              ^^^^^^^
  fix: Change it to one of: p50, p90, p95, p99, mean, max.
  rule: schema/wrong-type
```

Every diagnostic carries **where, what, why, and how** — a fix is required by
the constructor's signature, so an unactionable error cannot be built. The
intended reader cannot write code, so a message they cannot act on is a defect.

Not everything a check has to say is a complaint. A **note** says something true
about a document that is not wrong with it, and `--deny-warnings` stays green
for one — a fact printed as a problem teaches an author to stop reading the
output, which is the one thing this format cannot afford:

```
note: 'refund-policy' holds 5 written rules under `## Rules` — lines a person
  has to approve before they change, whoever or whatever proposes it.
  fix: Nothing to do. Move a rule out from under `## Rules`, or reword that
  heading, and it stops being one — which is how you move this boundary.
```

---

## The object model, and exact logic

Two things an author reaches for once a workspace stops being one desk: *"these
five desks are the same shape"* and *"this bit must be exactly right, not
approximately right."* Both are authored in YAML, and both resolve to nothing —
which is the point.

**One shape, several desks.** `expects:` declares the holes; `with:` fills them;
`based-on:` inherits by shallow merge; `base: yes` marks a shape nothing runs.
Together they are inheritance, encapsulation and polymorphism, written the way
the rest of the format is written.

```yaml
# agents/desk-pattern/agent.yaml — a pattern, not a desk
expects:
  domain:    { shape: text,  help: what this desk answers questions about }
  daily-cap: { shape: money, help: the most one request may cost }
description: A desk that answers questions about <domain>.
limits:
  cost-per-request-under: <daily-cap>

# agents/refunds/agent.yaml — one of the desks
based-on: desk-pattern
with:  { domain: refunds, daily-cap: 0.05 USD }
```

**The pattern is resolved and removed.** A tree written this way and one written
out longhand are not similar — they are the same document, down to the digest.
Both shipped fixtures prove it, and you can run this yourself:

```bash
pact discover tests/trees/two-desks-one-pattern  # sha256:554f1ac71be9a23f…
pact discover tests/trees/two-desks-longhand     # sha256:554f1ac71be9a23f…
```

`values:` does the same for a single figure — a spend cap written once and used
in three files digests identically to the same cap typed three times
(`one-figure-in-three-places` against `one-figure-longhand`). Nothing below the
loader ever learns these features exist, which is what keeps every downstream
claim — portability, digests, conformance — true of trees that use them.

Because both are erased, `pact waits` records **where each one landed**, since
by then the reference is gone and nothing else could say.

**Exact logic, when getting it right matters more than reading it.** A carried
program is a file in the folder with a declared engine, a determinism promise
and a fuel ceiling. It runs in a locked room the host supplies, and a person
consents before it runs at all:

```bash
pact waits tests/trees/a-desk-with-a-program
# waits: [('may-we-run', 'needs-permission')]
```

Seven lines reach one: a tool's `program:`, an agent's `uses:`, an action's
`projects-with:`, a question's `checked-by:`, a stage's `decided-by:`, an eval's
`uri: program:<name>`, and a rewriting interceptor sentence. Each is held to the
rules its own line claims — a router and a rewriter must be `pure`, because
where a run goes and what it says have to be the same twice; a checker and a
grader are deliberately not, because looking something up is what they are for.

A stage may also write its own code and have the room run it (`does: run-code`,
the sixth of FR-6.1.5's loop patterns). The snippet lands in the transcript
verbatim, holds no structural authority, and is refused at check time in a
workspace that declares no room. What the model wrote is what the room runs;
what the transcript shows is what the hiding rules left, and the run says so
when those differ.

**All of it is `tier: expert`.** No core capability requires a program, deleting
`programs/` leaves a working agent, and a workspace that carries one simply does
not earn the `no-code` badge — held by a test over the specification's own tiers
rather than by anybody remembering.

**And memory is a variable the format can name.** `bind: remembers.<name>` reads
what the conversation established into an argument the model never sees;
`remember-as:` writes a tool's answer back. `never-from: tool output` is what
stops one filling the other.

---

## Documents

| | |
|---|---|
| [`docs/00-THESIS.md`](docs/00-THESIS.md) | The argument, goals, objectives, acceptance criteria |
| [`docs/01-DECISIONS.md`](docs/01-DECISIONS.md) | 28 binding decisions — **read this before proposing anything** |
| [`docs/30-FRD.md`](docs/30-FRD.md) | 120 functional requirements, each traced to its justification |
| [`docs/40-IMPLEMENTATION-PLAN.md`](docs/40-IMPLEMENTATION-PLAN.md) | Milestones M0–M8, gates, risks, and what would falsify the approach |
| [`docs/50-NOT-COPIED.md`](docs/50-NOT-COPIED.md) | The refusal ledger — what was deliberately not copied from prior art, and what would bring each back |
| [`docs/70-PRODUCTION-GAP-REGISTER.md`](docs/70-PRODUCTION-GAP-REGISTER.md) | Every gap between what is claimed and what is built, with its measurement |
| [`research/notes/README.md`](research/notes/README.md) | Index of the research, with the 12 findings that changed the design |
| [`.claude/workflows/pact-architecture.js`](.claude/workflows/pact-architecture.js) | The research → critique → reflect workflow that produced it |

---

## Layout

```
crates/            Rust core
  pact-diag/       diagnostics — a fix is mandatory by construction
  pact-doc/        span-preserving YAML / JSON / Markdown
  pact-loader/     the Expansion Rule (tree → document), and every check a
                   document needs that a schema cannot make
  pact-schema/     validation; the schema is data, not code
  pact-cli/        `pact check`, `pact show`, `pact waits`, `pact discover`,
                   `pact card` — never executes author code
adapters/python/   the reference harness, six framework transports, the
                   resolver, evals, learning and the port boundary
adapters/typescript/ the second, independent port — Node, and smaller on
                   purpose; it says which parts it is smaller by
spec/schema.yaml   the specification, written in PACT
spec/loops/        the six loop shapes, authored the way anybody's are
examples/          the worked no-code multi-agent example, and eight
                   orchestration patterns
tests/trees/       small fixtures, each the smallest tree that shows one thing
research/          14 studies + the 140-repo corpus (gitignored)
docs/              thesis, decisions, FRD, plan, refusal ledger, gap register
```

---

## Five things worth knowing

**Fidelity is measured, not declared.** Every adapter publishes a capability
lattice (`native | emulated | degraded | unsupported`) and any degradation is
reported *before* execution. There is no silent loss anywhere in the system.

**Failure is honest, and useful.** When a model cannot meet a contract, PACT
refuses to bind — then searches the catalogue and recommends the cheapest model
that *does* pass.

**The model-portability claim is bounded by evidence.** An optimised small model
reaches 98–114% of a *hand-written* frontier strategy, but only 70–94% of an
*optimised* one, and the gap between equally-optimised tiers does not close. The
honest claim is *"recovers the accuracy you actually had"* — never *"matches a
frontier model."*

**Scaffolding can hurt.** At Qwen2.5-1.5B, LangChain, AutoGen and smolagents all
score *below the raw model* across 13 benchmarks. So the harness is treated as a
per-tier strategy variable, and conformance gates harness-vs-**raw**, not only
harness-vs-native.

**Learning emits source.** Every self-improvement is a signed, reviewable,
revertible diff to a spec file. An agent that grows is still an agent you can
read, fork, and port. A written rule under a `## Rules` heading in a skill needs
a person however the edit is made — added, removed, reworded, or moved by
renaming the heading over it — and `pact check` shows the author where that
boundary falls rather than leaving them to trip over it.

**Convenience erases itself.** Patterns, inherited shapes and shared figures all
resolve and disappear before anything downstream reads the tree, so a workspace
that uses them digests identically to one written out longhand. Every claim this
project makes about portability, digests and conformance therefore covers trees
that use them, without one line of special-casing anywhere below the loader.

---

## Naming

`PACT` and `pact.dev/v1` supersede `bud.dev/v1`. Consumed natively by
[`gaia-ai-runtime`](../gaia-ai-runtime); deliberately independent of
[AgentZero](../bud), which owns agent-collective routing and scale.
