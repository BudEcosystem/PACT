# PACT — A Thesis for the Portable Agent Contract

> **Name — confirmed.** `PACT` = **P**ortable **A**gent **C**ontract & **T**opology.
> `pact.dev/v1`, CLI `pact`, derived dir `.pact/`. PACT **replaces** the existing
> `bud.dev/v1` Agent manifest and must be a strict superset of it.
>
> ⚠️ **Read `01-DECISIONS.md` alongside this document.** 28 decisions were locked
> on 2026-07-26. Where they conflict with this thesis, they win. The material
> revisions are marked **[D-revised]** inline below.

**Document status:** Thesis + Goals + Objectives + Acceptance Criteria.
**Date:** 2026-07-25.
**Position in the series:** `00` of the `agent-inter-op` design set. Successor
documents: `10-RESEARCH-*`, `20-ARCHITECTURE`, `30-FRD`, `40-IMPLEMENTATION-PLAN`.

**Prior art this builds on, in-repo:**
`/home/bud/ditto/gaia-ai-runtime/bud-agentic-runtime/` (registry, portability,
declarative dev, run ledger, A2A/OSSA facades) and
`/home/bud/ditto/gaia-ai-runtime/research/` (53 papers, 3 live microbenchmarks,
`SYNTHESIS.md` F1–F6). This thesis does not restate those; it names where it
consumes them.

---

## 0. Executive summary

Every attempt to make AI agents portable has failed the same way: it modelled an
agent as a **program** and tried to translate the program. Programs do not
translate, because each framework's agent abstraction encodes a different
execution semantics — LangGraph's checkpointed state machine, AutoGen's
conversational actor mailbox, Pydantic AI's typed dependency-injected run,
OpenAI Agents' handoff-and-guardrail loop, the Vercel AI SDK's streaming step
loop. Any format that is the *intersection* of these is too weak to express a
real agent. Any format that is the *union* is unimplementable.

This thesis proposes a different decomposition. **An agent is not a program. An
agent is a contract about behaviour, plus a plural space of strategies for
satisfying it, plus a substrate that executes one chosen strategy.**

- The **Contract** — what must be true of the agent's behaviour (capabilities
  required, evals it must pass, SLOs it must meet, I/O schemas, policies it must
  obey) — is fully portable. It is the invariant under *both* framework-porting
  and model-porting.
- The **Strategy** — instructions, topology, tool wiring, loop structure, memory
  layout — is *not* portable in the naive sense, and should not be. It is
  **plural**: many strategies satisfy one contract. A strategy is *selected* (or
  *synthesised*) for a given target.
- The **Substrate** — framework × runtime × model × cloud — receives one
  resolved strategy through an adapter.

From this decomposition three results follow, and they are the whole thesis:

1. **Framework portability becomes a compiler problem with a verification
   obligation.** A canonical IR lowers to each framework by one of two
   strategies — *native lowering* (use the framework's own agent abstraction;
   idiomatic, possibly lossy) or *harness lowering* (use the framework only as a
   model/tool transport and run PACT's own loop semantics on top; always
   faithful). Fidelity is never asserted; it is **measured** by a Conformance
   Test Suite and reported per feature.

2. **Model portability becomes a search problem with an empirical oracle.**
   "Run my GPT-5.5 agent on an SLM without losing accuracy" is not a
   translation request — it is a request to *find a different strategy that
   satisfies the same contract on a weaker executor*. The developer-authored
   eval suite is the oracle. Variant selection tries authored alternatives;
   the optimizer (GEPA/SkillOpt-class, already validated in-repo at
   0% → 81.2% held-out on one gated edit) *synthesises* new ones. If nothing
   passes, the system says so — a **Portability Report**, never a silent
   degradation.

3. **The filesystem becomes the authoring interface via one rule, not fifty
   special cases.** Vercel's Eve proved that path-as-identity works. Its limits
   are structural: a fixed slot table, TypeScript-only escape hatches, a fixed
   harness loop, no inheritance, no orchestration topologies, no model
   abstraction, and code-based evals. PACT replaces the slot table with **the
   Expansion Rule**: *any field of a document may be written as a directory, and
   any directory is exactly a field.* The filesystem is a serialisation of the
   canonical document — nothing more, nothing less. A beginner writes one file.
   An expert explodes it into a tree. Both produce the identical IR. New
   features get their directory form for free, which is what makes the system
   extensible without touching the core.

The closest correct analogy is not LLVM and not Kubernetes. It is **the cost-based
query planner**. SQL is portable across engines not because engines are alike,
but because SQL declares *what*, the planner chooses *how* against statistics
and a cost model, and the result is verified by the semantics of relational
algebra. PACT declares the agent's *what*; the Resolver plans the *how* against a
model/runtime capability catalogue and an SLO cost model; and — because agent
semantics are probabilistic rather than algebraic — **evals replace relational
algebra as the correctness oracle.** That substitution is the load-bearing idea
of this document.

---

## 1. The problem, stated precisely

### 1.1 What "portable" is being asked for

Six distinct portability axes are conflated in normal usage. They have different
difficulty and different solutions, and any credible design must address them
separately.

| # | Axis | Question | Hardness |
|---|---|---|---|
| A1 | **Framework** | Can this agent run on LangGraph *and* Pydantic AI *and* AutoGen? | Structural: differing execution semantics |
| A2 | **Model** | Can this agent run on GPT-5.5 *and* a 7B SLM? | Behavioural: differing capability, not differing API |
| A3 | **Runtime** | Local process, Bud/Goose, serverless, durable-execution engine, K8s? | Operational: state, resume, concurrency |
| A4 | **Modality** | Text, vision, audio, video, embodied, computer-use? | Representational: I/O contracts |
| A5 | **Topology** | Single agent, supervisor tree, swarm, graph, debate, custom loop? | Compositional |
| A6 | **Cloud / Provider** | Any inference provider, any tool provider, any store? | Mostly plumbing (gateways solve much of it) |

The industry has a partial answer for A6 (LiteLLM, gateways) and a protocol answer
for parts of A1 (MCP for tools, A2A for agent-to-agent *invocation*). **Nobody has
an answer for A1 at the definition level, and nobody has any answer for A2.**
A2A makes a remote agent *callable*; it does not make an agent *portable* — it is
an RPC boundary, not a specification. This is the gap PACT targets.

### 1.2 The Portability Trilemma

> For a *statically declared* agent definition, you may have at most two of:
> **(i)** full behavioural fidelity, **(ii)** any framework, **(iii)** any model.

- Choose (i)+(ii): pin the model. This is what a careful LangGraph→Pydantic AI
  port does today. Works; doesn't scale to SLMs.
- Choose (i)+(iii): pin the framework. This is what DSPy does — excellent model
  portability, single ecosystem.
- Choose (ii)+(iii): give up fidelity. This is what every "universal agent YAML"
  proposal has silently done. It is why they are not used.

**Resolution.** The trilemma binds only under *static* declaration. Make the
third axis **empirical** rather than declared: do not *assert* fidelity, *measure*
it. Then the artifact is not "an agent that runs everywhere" but "an agent plus a
machine-checkable claim about where it runs and how well." That is both honest and
strictly more useful, because it converts an unfalsifiable marketing claim into a
CI gate.

This single move — **fidelity is a measured property, not a declared one** — is
what makes the rest of the design possible.

### 1.3 Why existing candidates do not solve it

| Candidate | What it gets right | Why it is not sufficient |
|---|---|---|
| **A2A / Agent Cards** | Discovery + invocation of remote agents; identity, skills, security schemes | Describes an *endpoint*, not a *definition*. You cannot re-materialise the agent elsewhere from its card. No eval, no capability requirements, no strategy. |
| **MCP** | Tool/resource/prompt interop; broad adoption | Solves the *tool* edge only. Says nothing about agent definition, loop, orchestration, or model requirements. Necessary, not sufficient. |
| **OSSA / OASF (AGNTCY)** | Portable packaging/deployment manifest; registry-shaped | Packaging metadata, not behavioural semantics. In-repo mapping already yields a *loss report* for anything Goose-native — that loss is the whole problem, not an aside. |
| **Vercel Eve** | Filesystem-as-interface; path-as-identity; durable execution; evals in-tree | Single-agent; TS-only; fixed harness; no inheritance ("copy the markdown under each `skills/`"); no topologies; no model abstraction; code-based evals; one runtime. |
| **DSPy / GEPA** | *The* correct mechanism for model portability (optimise the program, not the prompt) | Python framework, not a spec. Does not address A1/A3/A5. But it is the right **engine** to embed. |
| **LiteLLM / gateways** | A6, and the API-shape half of A2 | Normalises the *call*, not the *capability*. A 7B model behind an OpenAI-shaped API is still a 7B model. |
| **Framework-native YAML** (Dify, Langflow, CrewAI YAML) | Low-code authoring | Each is a serialisation of *one* runtime's object graph. That is the definition of non-portable. |
| **Oracle "Open Agent Specification"** (v26.1.2, 6 framework adapters) — *the closest shipping thing to PACT; found only by web search, absent from the 141-repo corpus* | A real declarative, framework-agnostic agent spec with working adapters. PACT is **not** first-mover here, and any positioning that assumes otherwise is wrong. | **Evaluation is not part of the portable artifact** — `Metric` is not a serialisable component, and there are exactly two built-in metrics. No filesystem-native form, no model-capability contract, no learning. This is the strongest external confirmation that **T2 (evals-in-the-contract) is the actual differentiator**, not the topology IR — every serious competitor has a topology IR. |
| **Pydantic AI `AgentSpec`** (`pydantic_ai/agent/spec.py:33-49`) — *found during source review, and the sharpest comparison available* | A real YAML agent spec, from PACT's highest-priority target framework, with an explicitly identical audience: *"Letting non-developers (prompt engineers, domain experts) configure agents"* (`docs/agent-spec.md:3-9`). Serialisable capability registry; MCP servers declarable in YAML. | It is one flat file for one framework. No `tools:` field at all; no evals, no SLOs, no capability *requirements*, no variants, no topology, no learning, no directory expansion; `ProcessHistory` is explicitly non-serialisable. **This raises PACT's bar rather than lowering it:** the win must come from exactly the things `AgentSpec` cannot express, or PACT is a worse version of something that already ships. |

**Conclusion.** The missing artifact is a *behaviour-contract-carrying, strategy-plural,
empirically-verified* agent specification. Everything above is either a transport,
a package, or a runtime dump.

---

## 2. Thesis

> **T1 — Separation.** An agent decomposes into Contract (portable, invariant),
> Strategy (plural, target-selected), and Substrate (adapter-projected). Portability
> is a property of the Contract; fidelity is a property of a (Strategy, Substrate)
> pair, and it is measured, never assumed.

> **T2 — The eval suite is the portability mechanism, not a testing afterthought.**
> Because agent semantics are probabilistic, the only sound equivalence relation
> between two realisations of an agent is *behavioural agreement on a specified
> distribution of tasks*. The developer's eval suite **is** that specification.
> It follows that evals must be (a) authorable by non-programmers, hence
> **config-only**; (b) complete enough to be a real oracle, hence **full DeepEval
> feature parity**; and (c) first-class inputs to *resolution*, not just to CI.

> **T3 — Two-level lowering makes "full portability" achievable rather than
> aspirational.** Every adapter must implement *harness lowering* (framework as
> model/tool transport, PACT loop semantics on top) — this is always faithful and
> is the conformance floor. *Native lowering* (map onto the framework's own agent
> abstraction) is an optimisation, adopted per-feature only where the CTS proves
> it equivalent. This inverts the industry's usual approach and is why prior
> "universal formats" were lossy: they only ever attempted native lowering.
>
> **T3-corollary — the harness is itself a strategy variable, not a constant.**
> Measured on 13 benchmarks at Qwen2.5-1.5B, LangChain (32.81), AutoGen (33.57)
> and smolagents (27.81) all score **below the raw model** (34.28); the sign only
> flips around 32B (`research/notes/web-frontier.md` §3.1, EffGen arXiv
> 2602.00887). Agent scaffolding is *net negative* on small models. So the
> conformance suite must gate **harness-vs-raw**, not merely harness-vs-native,
> and the resolver must be able to select *less* scaffolding for a weak executor.
> This is the sharpest available warning against D28's failure mode #2 —
> portability that is technically true and practically worse.

> **T4 — Model portability is variant selection followed by strategy synthesis,
> gated by evals.** Rank-order: (1) an authored variant for the target tier;
> (2) an optimizer-synthesised variant (GEPA/SkillOpt over instructions, skills,
> tool exposure, decomposition, loop); (3) an honest FAIL. Prior in-repo results
> establish this is not speculative: hierarchical capability routing recovers
> full accuracy at ~15% of tokens, and a single gated skill edit moved held-out
> accuracy 0% → 81.2%.

> **T5 — Typed Expansion makes the filesystem a complete, extensible authoring
> surface.** *A directory is a field; a field may be a directory.* One rule
> replaces Eve's fixed slot table, delivers progressive disclosure (one file →
> full tree) without a second concept, and grants every future feature a
> filesystem form for free. This is the concrete mechanism behind the
> Extensibility and Generisability pillars.
>
> **[Amended by research.]** The unqualified slogan is *not a well-defined
> function* and must be retired from normative text. Six shipping systems that
> implement "directory → field" disagree on ordering, on file-vs-directory
> precedence, and on name collisions — mutually incompatibly, so a reader cannot
> predict a value without knowing which implementation ran
> (`filesystem-prior-art.md`). The rule becomes total only as **Typed
> Expansion**: expansion form is declared **per field by the schema**
> (`dir | payload | none`), the fold is **disjoint union** (conflict is an error,
> never last-wins or concatenation), and ordered collections carry order
> **in-band** (`NN-name.ext`, ties are an error). The slogan survives as the
> authoring *intuition*; the eleven rules E1–E11 are the specification.

> **T6 — Learning must emit source, not weights.** Every artifact produced by
> optimisation, reflection, or trace-mining is written back as a diffable spec
> file under provenance and review gates. An agent that learns must remain an
> agent you can read, review, sign, fork, and port. Opaque adaptation is
> incompatible with portability *and* with the governance the enterprise
> literature says is the #3 killer of agent programs.

> **T7 — Honesty is a feature, and it is enforced structurally.** Every lossy
> operation — cross-framework export, model downgrade, capability emulation,
> policy relaxation — emits a machine-readable report and is *fail-closed* by
> default. `allowLoss` must be explicit and is recorded in the lockfile. There is
> no silent degradation anywhere in the system.

---

## 3. Design pillars → architectural invariants

The four pillars the brief names are treated as *falsifiable invariants*, each
with an enforcement mechanism and a test. A pillar without a test is a slogan.

### 3.1 Portability

| Invariant | Enforcement | Test |
|---|---|---|
| **P-1** The canonical IR is the only source of truth; no adapter may read author files directly. | Adapters consume `canonical.json` only; author-file access is not on the adapter API. | Adapter unit tests run against synthetic IR with no source tree present. |
| **P-2** Every adapter implements harness lowering. Native lowering is opt-in per feature and must pass CTS-equivalence. | Adapter capability lattice declares `native \| emulated \| degraded \| unsupported` per IR feature. | CTS: golden agents × all adapters × shared eval suite, within ε. |
| **P-3** Import is lossless-or-reported. | `import` emits an `ImportReport`; unmapped constructs are preserved in `x-` extension blocks, never dropped. | Round-trip property test: `import → export` on framework-native fixtures. |
| **P-4** Model swap never silently degrades. | Resolver requires an eval verdict before binding a model outside the authored tier. | Resolution refuses to produce a lockfile without a verdict or explicit `--allow-unverified`. |
| **P-5** Runtime-neutrality: state, resume, and cancellation are IR concepts. | Durable-execution semantics declared in IR; adapters map to Temporal/Workflow/Bud-ledger/in-proc. | Kill-and-resume conformance test per runtime. |

### 3.2 Extensibility

| Invariant | Enforcement | Test |
|---|---|---|
| **E-1** A new framework requires **zero** core changes. | Adapters are out-of-tree packages implementing a stable ABI + capability lattice. | CI builds an adapter from an external repo and runs CTS. |
| **E-2** A new IR feature is additive and versioned. | Feature-gated IR: unknown features are *rejected loudly* by old adapters, never ignored. | Compatibility matrix test with pinned old adapter + new IR. |
| **E-3** New authoring surface is free. | The Expansion Rule: no per-slot code. | Adding a field to the schema automatically yields its directory form (property test). |
| **E-4** New eval metrics plug in without code. | Metric registry keyed by URI; DeepEval/Ragas/custom providers register metric descriptors. | Config-only metric addition test. |
| **E-5** New optimizers plug in. | Optimizer ABI: `(spec, evalSuite, budget) → candidate spec + verdict`. | Two optimizers (GEPA-class, random-search baseline) satisfy the same ABI. |

### 3.3 Generisability

| Invariant | Enforcement | Test |
|---|---|---|
| **G-1** Modality-agnostic. | I/O contracts are content-typed (`text`, `image`, `audio`, `video`, `binary`, `stream`, `tool-result`) with schema, not `string`. | Vision + audio golden agents in the CTS. |
| **G-2** Topology-agnostic. | Orchestration is a graph IR with a small closed set of node/edge kinds sufficient for supervisor, swarm, pipeline, debate, map-reduce, blackboard, market/auction. | Each pattern realised as a fixture and CTS-verified across adapters. |
| **G-3** Loop-agnostic ("loop engineering"). | The agent loop is *authored data*: a declarative state machine over `perceive/plan/act/observe/reflect/halt` with a code escape. | ReAct, Plan-Execute, Reflexion, Tree-of-Thought, self-consistency, CodeAct all expressible without adapter changes. |
| **G-4** Complexity-agnostic. | Recursive composition: any agent may be a node in any topology; any topology may be exposed as an agent. | Depth/breadth stress fixture; no depth special-cases in the IR. |
| **G-5** Construct-agnostic. | Tools, skills, memory, retrievers, guardrails, hooks, channels, schedules, sandboxes are all **Resources** under one registration/scoping model. | Adding a resource kind requires no orchestration change. |

### 3.4 Flexibility

| Invariant | Enforcement | Test |
|---|---|---|
| **F-1** No hardcoded defaults that cap capability. | Every default is a value in a *profile*, overridable at workspace/agent/variant/run scope. | "Zero-magic" audit: grep the core for literals; all must resolve from profile. |
| **F-2** Escape hatches everywhere, in any language. | Any declarative node may be replaced by a `ref:` to code (Python/TS/WASM/HTTP/MCP). Escapes are *typed* and *declared*, so they remain analysable. | Each escape kind exercised in CTS with fidelity accounting. |
| **F-3** Declarative-first, never declarative-only. | The IR admits opaque code nodes; portability of an opaque node is reported as `unsupported` unless the target hosts the same language. | Mixed-language fixture with an honest report. |
| **F-4** The spec cannot force a worse agent. | If PACT's harness lowering measurably underperforms native framework use on the CTS, that is a **defect**, tracked as a fidelity regression. | Continuous benchmark: harness vs native on identical evals. |

---

## 4. Goals

### 4.1 Primary goals (G-series)

- **G1 — Author once, run on any of the seven named substrates.** Pydantic AI
  (highest priority), LangGraph, LangChain, AutoGen, OpenAI Agents SDK, Anthropic
  Claude Agent SDK, Vercel AI/Agent SDK — plus Bud/Goose as the first-class
  execution home.
- **G2 — Author once, run on any model tier**, with fidelity established by the
  author's own evals and, where required, an optimizer that adapts the strategy
  to the weaker executor.
- **G3 — Filesystem-native authoring** that a non-programmer can use and a
  senior agent engineer does not outgrow.
- **G4 — Config-only evaluation with complete DeepEval feature parity**, plus
  SLO predicates, capability predicates, and benchmark-score predicates.
- **G5 — First-class multi-agent orchestration, custom loop engineering, and
  agent learning** as portable, declarative constructs.
- **G6 — Automatic discovery and execution by `gaia-ai-runtime`**, using the
  skills, tools, and models it already has; consumable by `bud-gaia`.
- **G7 — Structural honesty:** every lossy operation is reported, gated, and
  recorded.

### 4.2 Non-goals (explicit, to keep the core small)

- **NG1 — Not a server. [D-revised]** PACT is a specification, a loader, a
  resolver, a lowering compiler, and a conformance suite. It *does* own an
  execution model — the folder tree is natively executable (D2) and PACT owns
  loop semantics (D12) — but it does not ship the hosting, scheduling, or
  serving layer. That is `gaia-ai-runtime`.
- **NG2 — Not a model gateway.** It *consumes* one (LiteLLM/Bud/Gateway) for A6.
- **NG3 — Not a replacement for MCP or A2A.** MCP is the tool edge; A2A is the
  remote-invocation edge. PACT is the definition layer and emits/consumes both.
- **NG4 — Not a UI-first system. [D-revised]** A UI *is* expected (D18) — but it
  reads and writes the same files, so the tree stays the source of truth. The
  OpenAI Agent Builder deprecation (Jun 2026) and GPT-Store attrition are
  evidence against the canvas *being* the artifact, not against having one.
- **NG5 — No universal semantics by fiat.** Where frameworks genuinely disagree,
  PACT picks one semantics, implements it faithfully via harness lowering, and
  *reports* the divergence — it does not pretend the disagreement away.
- **NG6 — Not a platform. [D-added]** Registry, capability routing at scale,
  multi-tenancy, and agent-collective economics are explicitly out of scope
  (D24). PACT exposes adapter-shaped seams; AgentZero (`/home/bud/ditto/bud`)
  owns that problem, and PACT stays independent of it (D25).
- **NG7 — No opaque wrapping. [D-added]** An existing framework app may not be
  embedded as a black box (D15). Translate or nothing.

---

## 5. Objectives (measurable)

Numbered `O*` and traced to acceptance criteria in §6.

**Specification**
- **O1.1** A versioned schema (`pact.dev/v1`) for: Agent, Team/Topology, Tool,
  Skill, Memory, Loop, Eval, Policy, Profile, Model, Workspace, Variant, Trace.
- **O1.2** A canonical IR (`canonical.json`) that is the sole adapter input, with
  a stable digest for lockfiles, signing, and caching.
- **O1.3** The Expansion Rule proven bidirectional: `explode(collapse(X)) ≡ X`.
- **O1.4** An extension mechanism (`x-` namespaces) that survives round-trips.

**Portability**
- **O2.1** Adapters for the 7 named frameworks + Bud/Goose, each with a published
  capability lattice.
- **O2.2** Harness lowering implemented for 100% of adapters.
- **O2.3** Importers for the same 7, emitting `ImportReport`.
- **O2.4** A Conformance Test Suite with ≥ 5 conformance levels (L0 discovery →
  L4 operational).

**Model portability**
- **O3.1** A capability/benchmark predicate language: `reasoning >= strong && MMLU > 80 && SWE-Verified > 40 && context >= 128k`.
- **O3.2** A model catalogue schema carrying capabilities, benchmark scores, SLO
  characteristics, and cost, with provenance per figure.
- **O3.3** A Resolver producing a lockfile: (agent, variant, model, adapter,
  runtime, tools) + verdict.
- **O3.4** An optimizer ABI, with a GEPA/SkillOpt-class reference implementation.
- **O3.5** A Portability Report: per (agent × model × adapter) verdict with score
  deltas.

**Evaluation**
- **O4.1** Config-only expression of every DeepEval metric, tracked by an explicit
  coverage matrix with a stated parity target.
- **O4.2** Config-only SLO assertions (TTFT, TPOT, E2E latency, cost, throughput)
  with percentile semantics.
- **O4.3** Dataset authoring from YAML/CSV/JSONL + trace promotion.
- **O4.4** Deterministic-first grading (programmatic checkers before LLM judges),
  with judge-hardening defaults grounded in the in-repo finding that a single
  token can drive some judges to high false-positive rates.

**Orchestration, loops, learning**
- **O5.1** Topology IR covering ≥ 8 named multi-agent patterns.
- **O5.2** Loop IR covering ≥ 6 named loop patterns, composable and portable.
- **O5.3** Learning IR: trace → eval promotion, delta-only instruction/skill
  updates, review-gated signed publication.

**Ecosystem integration**
- **O6.1** Bidirectional mapping to Bud `AgentRecord` / registry coordinates.
- **O6.2** Emission of A2A Agent Cards and OSSA manifests with loss reports.
- **O6.3** Auto-discovery contract for `gaia-ai-runtime` (what it scans, what it
  is guaranteed, how it binds skills/tools/models it already owns).

**Usability**
- **O7.1** Minimum viable agent: **one file, ≤ 5 lines, no code.**
- **O7.2** Minimum viable multi-agent system: **≤ 3 files, no code.**
- **O7.3** Every error message names the file, the line, the rule violated, and
  the fix.

---

## 6. Acceptance criteria

Each is binary and mechanically checkable. `AC-x.y` maps to objectives above.

### 6.1 Specification & authoring

- **AC-1.1** A valid agent exists that is a single file of ≤ 5 lines containing no
  code, and it runs on ≥ 3 adapters.
- **AC-1.2′** *(revised — the original was unachievable)* For every document whose
  field keys lie in the **portable key alphabet**
  (`^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$`, ≤64 bytes, NFC, excluding Windows
  reserved device names and names ending in `.` or space),
  `load(explode(D)) ≡ D` up to canonicalisation. For any key outside it,
  `explode` MUST fail loudly naming the offending field and MUST NOT emit a tree.

  **`explode` cannot be total, and the asymmetry is deliberate.** Keys arriving
  from imports and `x-` blocks are legal *inside* a document but are not always
  legal *as filenames*. Therefore: **a document is always representable as a
  single file; it is not always representable as a tree.** Claiming otherwise
  would require either mangling keys (silent loss — forbidden by T7) or
  restricting what can be imported (breaking P-3).
- **AC-1.3** An unknown top-level field is rejected with a fix suggestion; an
  unknown `x-` field round-trips untouched through import → IR → export.
- **AC-1.4** Two authors, one writing a single file and one writing a full tree,
  produce byte-identical `canonical.json` for the same logical agent.
- **AC-1.5** A non-programmer (defined operationally: cannot write a Python
  function) authors a 3-agent supervisor system with evals, using only YAML/Markdown,
  in a moderated session, without reading adapter documentation.

### 6.2 Framework portability

- **AC-2.1** For each of the 7 target frameworks, a golden agent set (≥ 12 agents
  covering single/tool/structured-output/multi-agent/HITL/streaming/memory/loop
  variants) compiles and executes.
- **AC-2.2** For every (golden agent × adapter) pair, the shared eval suite passes
  with score within a declared ε of the reference adapter, **or** the adapter
  declares the relevant feature `degraded`/`unsupported` in its lattice *and* the
  Conformance Report says so before execution.
- **AC-2.3** No adapter reads author files; adapter tests pass with only
  `canonical.json` present.
- **AC-2.4** Framework-native fixtures (real agents taken from each framework's
  own examples) import with an `ImportReport`; every unmapped construct appears
  in the report — measured coverage: **zero silent drops** across the fixture set.
- **AC-2.5** Adding a *new* adapter (an 8th framework) requires no modification to
  any core package. Proven in CI by building an adapter that lives in a separate
  repository.
- **AC-2.6** Kill-and-resume: for every adapter claiming L4, a run interrupted
  mid-tool-call resumes to the same terminal state.

### 6.3 Model portability

- **AC-3.1** *(revised against measured evidence — see `research/notes/model-portability.md`)*
  A reference agent **hand-authored** against a frontier model achieves ≥ 95% of
  that agent's eval score on a designated small model after variant resolution
  and optimisation — **or** the system emits a FAIL report naming the failing
  metrics. Both outcomes are acceptable; a *silent* pass is not.

  **The baseline is load-bearing and must be stated whenever the claim is made.**
  Across the three suites that optimise both tiers, an optimised small model
  reaches **98.4% / 113.8% / 103.4%** of the *hand-written* frontier strategy
  (SkillOpt 6-bench, MASS 8-bench, GEPA 6-bench) — but only **70.3% / 94.3% /
  82.7%** of the *optimised* frontier strategy. The residual gap between two
  equally-optimised tiers does not close and sometimes widens (GEPA 7.80 → 11.51;
  MASS 4.41 → 4.49; ReasoningBank 6.2 → 4.5 is the only narrowing).
  **The optimiser is a rising tide, not a leveller.** PACT's honest claim is
  therefore: *"recovers the accuracy you actually had"*, never *"matches a
  frontier model."* Marketing the latter would be false.

- **AC-3.1b** The **optimiser model is a separate binding from the execution
  model**, and defaults to the strongest available model — never to the target.
  Evidence: reflective-optimisation gain collapses with reflector strength
  (ACE: +17.1 at 671B → +7.6 at 120B → +2.4 at 70B); TextGrad driven by a weak
  model is frequently *destructive* (−24.0, −15.3, −11.8 pp cells); and a skill
  *imported* from a stronger model beat one re-optimised on the target
  (SkillOpt 4a). A spec that lets these two bindings collapse into one has a
  silent failure mode.
- **AC-3.2** The predicate language evaluates `MMLU > 80 && SWE-Verified > 40`
  against the model catalogue and filters candidates before any eval is run.
- **AC-3.3** Every benchmark figure in the catalogue carries provenance (source,
  date, harness, contamination note). A figure without provenance cannot satisfy
  a predicate in `strict` mode.
- **AC-3.4** Pinning a specific model (`model: exactly openai/gpt-5.5`) disables
  substitution entirely, and the lockfile records the pin.
- **AC-3.5** The optimizer improves at least one reference agent's small-model
  eval score by a declared margin over the un-optimised baseline, with a frozen
  held-out split and the split locked before optimisation begins.
- **AC-3.6** SLO predicates (TTFT/TPOT/E2E/cost) are enforced at resolve time
  against catalogue estimates *and* at run time against measurements; violation
  produces a typed, actionable failure.

### 6.4 Evaluation

- **AC-4.1** A published coverage matrix enumerates every DeepEval metric and
  shows its config-only expression. The stated parity target is met, and any
  metric not expressible is listed with a reason and a workaround.
- **AC-4.2** No eval in the reference suite requires the author to write code.
  Code-based custom metrics remain *possible* (F-2) but never *necessary* for a
  DeepEval-expressible check.
- **AC-4.3** Evals run identically against any adapter, and against a *remote*
  agent (A2A/HTTP) with no eval-file changes.
- **AC-4.4** Failing production traces are promotable to eval cases with one
  command, preserving redaction policy.
- **AC-4.5** Deterministic checkers run before LLM judges; a suite that can be
  fully decided deterministically never invokes a judge.

### 6.5 Orchestration, loops, learning

- **AC-5.1** ≥ 8 orchestration patterns (supervisor, hierarchical, sequential
  pipeline, parallel map-reduce, swarm/handoff, debate, blackboard, market/auction)
  each expressible declaratively and each passing CTS on ≥ 3 adapters.
- **AC-5.2** ≥ 6 loop patterns (ReAct, Plan-and-Execute, Reflexion, Tree-of-Thought,
  self-consistency, CodeAct) expressible as data, portable, and CTS-verified.
- **AC-5.3** A custom loop authored purely in config changes measured agent
  behaviour on an eval, demonstrating the loop is genuinely executed and not
  decorative.
- **AC-5.4** A learning cycle produces a **diff to a spec file**, gated by
  held-out eval improvement, signed, versioned, and revertible. No learned state
  exists outside version-controllable artifacts.
- **AC-5.5** A rejected learning candidate is retained as negative evidence and
  demonstrably influences the next cycle.

### 6.6 Ecosystem integration

- **AC-6.1** `gaia-ai-runtime` discovers a PACT workspace with no per-agent
  registration step and lists every agent with correct capabilities.
- **AC-6.2** A PACT agent binds to skills/tools/models already owned by the
  runtime, without duplicating them into the spec.
- **AC-6.3** Export to Bud `AgentRecord`, A2A Agent Card, and OSSA each produce a
  loss report consistent with the in-repo `ExportReport` shape.
- **AC-6.4** A Bud/Goose recipe, custom agent, and skill each import into PACT and
  re-export without behavioural change on the CTS.

### 6.7 System-level

- **AC-7.1** No silent loss anywhere: a fuzzer that mutates specs and pipes them
  through import/resolve/export finds no path where a semantic element vanishes
  without a report entry.
- **AC-7.2** All defaults resolve from profiles; a core audit finds no
  capability-affecting literal.
- **AC-7.3** The full pipeline (`validate → resolve → build → eval → report`) runs
  offline against a local model, with no network dependency in the core.

---

## 7. System write-up

### 7.1 The layered model

```
┌─────────────────────────────────────────────────────────────────────────┐
│ L5  AUTHORING SURFACE      filesystem tree · one rule (Expansion Rule)  │
│                            YAML / Markdown / optional code escapes       │
├─────────────────────────────────────────────────────────────────────────┤
│ L4  CANONICAL IR           canonical.json · digest-addressed · versioned │
│                            Contract | Strategy-space | Resources | Graph │
├─────────────────────────────────────────────────────────────────────────┤
│ L3  RESOLVER (planner)     capability predicates → candidate targets     │
│                            variant selection → optimisation → verdict    │
│                            emits pact.lock + Portability Report          │
├─────────────────────────────────────────────────────────────────────────┤
│ L2  LOWERING               native lowering | harness lowering            │
│                            per-feature fidelity accounting               │
├─────────────────────────────────────────────────────────────────────────┤
│ L1  ADAPTERS               pydantic-ai · langgraph · langchain · autogen │
│                            openai-agents · claude-agent-sdk · vercel-ai  │
│                            bud/goose · (out-of-tree: anything)           │
├─────────────────────────────────────────────────────────────────────────┤
│ L0  SUBSTRATE              models · tools (MCP) · runtimes · clouds      │
└─────────────────────────────────────────────────────────────────────────┘
        ⇅ orthogonal: CONFORMANCE (CTS) · OBSERVABILITY (traces) · GOVERNANCE
```

### 7.2 The Contract / Strategy / Substrate split, concretely

**Contract** (portable, invariant, is what "the agent is"):
- **Identity** — name, namespace, version, owner, description.
- **Interface** — input/output schemas, modalities, streaming semantics.
- **Capability requirements** — what an executor must be able to do
  (`reasoning`, `tool_calling: parallel`, `structured_output: json_schema`,
  `long_context >= 128k`, `code_interpreter`, `web_search`, `web_scrape`,
  `vision`, `audio`, `computer_use`, …).
- **Quality contract** — the eval suite + pass thresholds.
- **Operational contract** — SLOs (TTFT/TPOT/E2E/cost/throughput), budget caps,
  concurrency.
- **Policy contract** — permissions, approval gates, data-handling, redaction,
  autonomy level.

**Strategy** (plural, selected per target):
- instructions / system prompt
- decomposition & topology (one agent vs supervisor + 3 specialists)
- loop program
- tool exposure set and descriptions (in-repo: full-text descriptions inside a
  *curated* exposed set; hierarchical routing over a flat top-k)
- skill exposure and ordering
- memory strategy
- retry/verification strategy (self-consistency, verifier passes)
- model parameters

**Substrate** (adapter-projected): framework, runtime, model, tool providers, cloud.

The Contract is what gets registered, discovered, signed, and searched. The
Strategy space is what gets optimised. The Substrate is what gets locked.

### 7.3 Why "same output on a smaller model" is achievable

The naive assumption is that a smaller model simply produces worse output for the
same prompt — true, and irrelevant. The correct framing is that *the strategy was
tuned (usually implicitly) to a strong executor*, and a weaker executor needs a
different strategy. The mechanisms, in the order the Resolver applies them:

1. **Decomposition.** Replace one hard step with several easy steps. Weak models
   fail at composition, not at each component.
2. **Externalisation.** Move reasoning the model is bad at into tools it can call
   (calculator, code interpreter, retriever, verifier, validator).
3. **Procedural specification.** Replace "figure it out" with an explicit
   procedure (a skill). This is exactly the in-repo bench-3 result: one gated
   skill edit, 0% → 81.2% held-out.
4. **Context discipline.** Curate exposed tools/skills; hierarchical routing
   restores accuracy at a fraction of the tokens. Weak models degrade faster
   with context bloat than strong ones, so this matters *more* on SLMs.
5. **Constrained decoding.** Grammar/JSON-schema-constrained generation removes an
   entire class of small-model failures.
6. **Verification loops.** Cheap generate-and-check beats expensive one-shot when
   the checker is programmatic.
7. **Ensembling.** Self-consistency / best-of-N with a programmatic selector; an
   SLM at N=5 can be cheaper *and* better than one frontier call.
8. **Optimisation.** GEPA-class reflective prompt evolution against the eval suite
   — the in-repo synthesis cites ~10–20% gains over RL at ~35× fewer rollouts.

None of this is new research; all of it is unavailable to authors today because
no specification lets you *declare the goal* and *hold the strategy plural*. That
is precisely the gap.

**Measured effect sizes, and where each mechanism fails** (from
`research/notes/model-portability.md`; the failure column is the part that must
survive into the design):

| Mechanism | Best measured gain on a weak executor | Fails when |
|---|---|---|
| Procedural specification (trained skills) | **+50.7 pp** (Qwen3.5-4B ALFWorld 30.6→81.3) | Model-*authored* skills lose 8–11 pp; ungated libraries fall **below** no-skill; >4 skills halves the gain; "comprehensive" prose gives +0.7 vs +21.5 |
| Reflective prompt evolution (GEPA/ACE) | +29.3 pp single-benchmark | Gain scales with the **reflector's** strength; optimiser hyperparameters do **not** transfer across tiers |
| Context discipline / hierarchical routing | routing 71.3%→91.7%, hijack 22.4%→4.1% | Buys **tokens, not accuracy**, on small catalogues; a confusion gap survives perfect retrieval |
| Constrained decoding | +34.4 pp (BFCL, claude-3-haiku) | **Substrate-bound**: regex/CFG unavailable on hosted OpenAI/Anthropic APIs; schema constraint can *degrade* quality and blocks chain-of-thought |
| Verification loops | Enables everything else | Judges below ~70% accuracy stop helping and then hurt |
| Decomposition / topology | +2.99 pp (MASS); +17.2% (AgentSquare) | **Depth is priced super-multiplicatively**: `Acc(N,K) ≈ (a − b ln N)^{γK}`, `γ = 6.7b + 1.09 > 1`, so a `K`-step pipeline scores *below* `K` independent draws — and worse as the executor weakens (`γ` grows with routing fragility `b`). Tight step-coupling costs **−7.2%** downstream when the upstream artifact is wrong (loose: +2.8%; crossover at `κ* ≈ 0.28`), and mid-chain steps are the fragile ones. See `20-ARCHITECTURE-DRAFT.md` §13.5 `[R6]` |
| Ensembling / self-consistency | +2.9 pp | Multiplies cost by *k* for single-digit gain; useless when the model is *consistently* wrong |
| Model routing | 85% cost cut claimed | **Not a portability mechanism at all** — it decides which queries still need the strong model. Under D17 (air-gapped, SLM-only) it contributes **zero**. |

Two consequences are structural, not advisory. **Ordering matters**: text/skills
before topology (MASS), because every extra step is priced super-multiplicatively
(`γ > 1`) and the price rises as the executor weakens — so the cheap, depth-free
mechanisms must be exhausted first. And **the optimiser must not run on the target model**
(AC-3.1b) — the one failure mode that would make the whole loop quietly worse.

**And the honest part:** for some contracts, no strategy on a 7B model passes.
The system's job is then to say so with evidence. `PORTABILITY: FAIL — metric
`answer_relevancy` 0.61 < 0.80 required; best of 14 candidate strategies.` That
report is more valuable than a silent 61%.

### 7.4 The filesystem surface (sketch, elaborated in `20-ARCHITECTURE`)

```text
my-system/
├── workspace.yaml                # members, registries, defaults, profiles
├── pact.lock                     # resolved bindings + verdicts (generated)
│
├── agents/
│   └── researcher/
│       ├── agent.yaml            # the ONLY required file
│       ├── instructions.md       # ← expansion of `instructions:`
│       ├── contract/             # ← expansion of `contract:`
│       │   ├── capabilities.yaml
│       │   ├── slo.yaml
│       │   └── io.yaml
│       ├── variants/             # ← expansion of `variants:`
│       │   ├── frontier.yaml
│       │   └── small.yaml
│       ├── tools/                # ← expansion of `tools:`
│       ├── skills/               # ← expansion of `skills:`
│       ├── memory/
│       ├── loop.yaml             # ← loop engineering
│       └── subagents/
│
├── teams/
│   └── research-desk/team.yaml   # topology graph
│
├── evals/
│   ├── suite.yaml                # config-only; DeepEval-complete
│   ├── datasets/
│   └── cases/
│
├── models/catalog.yaml           # capabilities + benchmarks + SLO + cost
├── profiles/                     # target profiles (tiers, runtimes, clouds)
├── policies/
└── .pact/                        # generated: canonical.json, reports, traces
```

The rule that makes this tractable: **every directory above is the expanded form
of a field in the file above it.** `agent.yaml` alone is a complete agent. Each
directory is an optional, mechanical unfolding. There is no slot table to learn
and no per-slot loader to maintain.

### 7.5 What `gaia-ai-runtime` gets

A PACT workspace is *discoverable without registration*. The runtime scans for
`workspace.yaml` / `agent.yaml`, reads `canonical.json` (or builds it), and gets:
- capability tags for its registry index and A2A card projection,
- declared tool/skill/model requirements it can satisfy from what it already owns,
- an eval suite it can run as a scheduled Bud agent (the missing `Eval` manifest
  kind named in the in-repo gap analysis),
- SLO/budget objects for the runner's budget enforcement,
- an autonomy level for the Ladder,
- lineage/provenance fields for the run ledger and signing pipeline.

PACT is deliberately shaped to *fill* the in-repo gaps (Eval manifest kind,
registry versioning consumers, feedback events, workflow-v2 expressiveness)
rather than to duplicate what the runtime already implements.

---

## 8. Risks and how the design answers them

| # | Risk | Answer |
|---|---|---|
| R1 | **Lowest-common-denominator collapse** — the spec becomes too weak to be useful. | Harness lowering: the IR is *not* bounded by the weakest framework, because any adapter can always execute PACT semantics directly. |
| R2 | **Adapter rot** — frameworks move faster than adapters. | Adapters are out-of-tree, versioned, and CTS-gated. A stale adapter fails conformance loudly rather than silently mis-executing. Pinned IR feature-gates make breakage explicit. |
| R3 | **Eval authoring burden** — nobody writes evals. | Evals are generated at authoring time (Foundry pattern) and promoted from failing traces automatically. The floor is "a handful"; the brief itself sets that expectation. |
| R4 | **Judge unreliability** — LLM judges are gameable. | Deterministic-first ordering; judge diversity; never the authoring model as sole judge; the in-repo one-token-fool finding is treated as a design constraint, not trivia. |
| R5 | **Benchmark predicates are misleading** (contamination, harness variance). | Provenance-required figures; predicates are a *pre-filter* only; evals are the oracle. `strict` mode refuses unprovenanced figures. |
| R6 | **Optimizer overfits.** | Frozen held-out split locked before optimisation; test split untouched until the end; rejected-candidate buffer; the exact protocol validated in-repo. |
| R7 | **Learning becomes an attack surface** (skill/memory poisoning). | Learning emits reviewable source under signed, provenance-gated promotion; no tool-output→skill direct writes. This mirrors the in-repo trust spine. |
| R8 | **Spec sprawl** — the format grows until nobody can implement it. | Small closed core + `x-` extensions + conformance levels. An adapter may certify at L2 and remain useful. |
| R9 | **"Normal person" claim is aspirational.** | AC-1.5 is a moderated user test with an operational definition, not a self-assessment. |
| R10 | **Duplicating `gaia-ai-runtime`.** | NG1: PACT is not a runtime. Integration contract is an explicit objective (O6) and the design targets the runtime's *named gaps*. |

---

## 9. What must be proven next (feeds the research workflow)

This thesis makes claims that must be validated against source, not assumed. The
research/critique workflow (`docs/50-WORKFLOW.md`) is charged with:

1. **Semantic gap audit** — read each of the 7 frameworks' agent loop, state
   model, tool protocol, streaming, HITL, and memory *in source*, and produce a
   feature-by-feature divergence matrix. Harness lowering is only credible if the
   divergences are enumerated.
2. **DeepEval surface enumeration** — every metric, parameter, and mode, read from
   source, to size the config-only parity claim honestly.
3. **Expansion Rule stress test** — find the constructs where field↔directory
   equivalence breaks (ordering, duplicate keys, binary payloads, cyclic refs).
4. **Model-portability evidence review** — beyond the in-repo corpus: current
   literature on small-model agentic capability, decomposition, constrained
   decoding, and prompt optimisation transfer across model scales.
5. **Prior-art autopsy** — why every previous universal agent format failed,
   read from their repos and issue trackers, not from their READMEs.
6. **Brutal critique** — an adversarial pass whose explicit goal is to find the
   design's fatal flaw, followed by reflection and revision.

Nothing in §7 should survive into `20-ARCHITECTURE` unmodified unless it survives
that process.

---

## 10. One-paragraph statement

> Agents are not portable today because the industry models them as programs and
> tries to translate the program. PACT models an agent as a **contract about
> behaviour** plus a **plural space of strategies** for satisfying it, and treats
> fidelity as a **measured** property rather than a declared one. Framework
> portability becomes a compiler problem with two lowering strategies — one
> idiomatic, one always-faithful — verified by a conformance suite. Model
> portability becomes a planning-and-search problem whose oracle is the
> developer's own config-only eval suite, so an agent written for a frontier model
> can be re-strategised onto a small one and *proven* to still work, or honestly
> reported as unable to. The authoring surface is the filesystem, governed by a
> single rule — a directory is a field — so a beginner writes one file, an expert
> writes a tree, and both compile to the same IR. And because every learned
> improvement is written back as reviewable source, an agent that grows is still
> an agent you can read, sign, fork, and port.
