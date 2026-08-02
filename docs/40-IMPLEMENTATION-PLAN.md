# PACT — Implementation Plan

**Date:** 2026-07-26. **Status:** Live. Milestone 0 is complete and running.
**Reads with:** `00-THESIS.md` (why), `01-DECISIONS.md` (28 binding decisions),
`research/notes/*.md` (14 source-grounded studies), `25-ARCHITECTURE-DECISIONS.md`
(the ADR, produced by the `pact-architecture` workflow).

**Sequencing principle.** Decision **D20** sets the first demo: *a non-technical
author builds a multi-agent system*. That outranks the portability demo, so the
authoring surface is built to completion before the first adapter is written.
Every milestone below ends in a gate that is a *test*, not a judgement.

---

## 0. Where this already is

Milestone 0 landed during the design phase, because the loader is the one
component whose design is fully determined by D2 and could not wait.

| Component | State | Evidence |
|---|---|---|
| `pact-diag` | Done | Four-part diagnostics; a fix is **required by constructor signature**, so an unactionable error is unconstructable |
| `pact-doc` | Done | Span-preserving YAML/JSON/Markdown; Norway problem avoided by type-directed resolution |
| `pact-loader` | Done | The Expansion Rule, with ambiguity refused, deterministic ordering, payload directories, cycle/symlink guards |
| `pact-schema` | Done | Schema **loaded as data** from `spec/schema.yaml`; did-you-mean; author-friendly coercion (`30s`, `0.05 USD`, `90%`, `> 80`) |
| `pact-cli` | `check` + `show` | Never executes author code; validation can never be silently skipped |
| `examples/refund-desk` | Done | Supervisor + 2 specialists + MCP tools + evals + learning, **100% YAML/Markdown** |

**91 tests, clippy clean.** Including a test that fails the build if any
non-YAML/Markdown file appears in the example — D14 enforced mechanically rather
than by intention.

---

## 1. Milestones

Each milestone is independently useful. None is a prerequisite for *starting*
the next, only for finishing it.

### M1 — The authoring surface is complete (the D20 demo)

**Goal:** a non-technical author can write, check, and understand a multi-agent
system, and every mistake they can make produces an actionable message.

| # | Work | Gate |
|---|---|---|
| M1.1 | Freeze the vocabulary from the ADR into `spec/schema.yaml` | Example revalidates; every field has one-line `help` |
| M1.2 | `pact explain <agent>` — render the effective document with per-field provenance (which file each value came from) | Provenance shown for every field, including inherited ones |
| M1.3 | Composition operator with a published merge algebra (`replace \| append \| prepend \| merge \| remove`) | Eve's "copy the markdown into each subagent" problem has a one-line answer |
| M1.4 | Reference resolution (`uses:` → tools/skills) with unresolved-reference diagnostics | Referencing a missing tool names it and lists what exists |
| M1.5 | `.pactignore`; fail-closed on unrecognised files in typed directories | A stray `tools/notes.txt` is reported, never silently skipped |
| M1.6 | `pact new` templates (single agent, supervisor+specialists, pipeline) | Each template checks clean on creation |
| **Gate** | **AC-1.5 moderated user test**: a person who cannot write a function builds a 3-agent system with evals, unaided, with only `pact check` for help | Pass/fail recorded verbatim, including every place they got stuck |

> M1.6's templates matter more than they look. The evidence is unambiguous that
> fork-and-tweak dominates real usage (GPT Store: 3M built, 95% never shared;
> Dust.tt's flywheel runs on templates). Authoring from scratch is the demo;
> forking is the product.

### M2 — Canonical IR, digest, and the round trip

**Goal:** a derived, stable, addressable form — without it ever becoming the
source of truth (D2).

| # | Work | Gate |
|---|---|---|
| M2.1 | `pact-ir`: canonical JSON with fixed key ordering and normalised scalars | Same tree → identical bytes on Linux/macOS/Windows |
| M2.2 | Tree digest (hash the **tree**, not the derived file — Eve's `sourceGraphHash` hashes artifacts, which is the wrong direction) | Digest changes iff a semantic input changes; whitespace and comments do not move it |
| M2.3 | `explode` (document → tree), inverse of the loader | **AC-1.2**: property test over 100 generated specs, `explode(collapse(X)) ≡ X` |
| M2.4 | `pact.lock` format: agent × variant × model × adapter × runtime + verdict | Lockfile round-trips; a stale lock is detected by digest |
| **Gate** | Deleting `.pact/` changes nothing but speed | Timed run with and without the cache; identical output |

### M3 — Evals, config-only (the oracle)

**Goal:** the eval suite becomes a real oracle, authorable five ways (D19),
runnable offline (D17).

Research sized this precisely: **56 DeepEval metrics, zero requiring author
code, 51 pure-config given four provider shims** (`research/notes/deepeval-surface.md`).

| # | Work | Gate |
|---|---|---|
| M3.1 | Eval document model; the five on-ramps **desugar into one form**, not five subsystems | Each on-ramp produces the same IR for the same check |
| M3.2 | Provider ABI + DeepEval provider (Python sidecar) | Metric declared by URI (`deepeval:faithfulness`) executes |
| M3.3 | The four shims: Rubric, ToolCall, JSON-Schema→schema object, DAG document | **AC-4.1** coverage matrix published: 51/56 config-only, 5 explained |
| M3.4 | Structural assertions as YAML predicates — `calledTool`, `toolOrder`, `maxToolCalls`, `usedNoTools`, `calledSubagent`, `loadedSkill`, `eventOrder`, `noFailedActions` | These are a genuine gap in DeepEval; adopt Eve's set wholesale |
| M3.5 | `on:` / `where:` selectors for trace and span-level evals | Replaces DeepEval's `@observe(metrics=[...])` decorator entirely — possible *only* because of D12 |
| M3.6 | Gate/soft/`atLeast` severity; `--strict` promotion | A soft miss is visible and non-fatal; a gate miss exits non-zero |
| M3.7 | Mock/replay model in core | **AC-7.3**: full suite runs with no network, telemetry opt-out set |
| M3.8 | SLO assertions with percentile semantics and minimum sample sizes | An SLO claim on 3 samples is refused, not reported |
| **Gate** | **AC-4.2**: no eval in the reference suite requires author code | Grep the suite for code refs; must be zero |

### M4 — Adapters: Pydantic AI, then LangGraph

**Goal:** the same folder runs on two frameworks with genuinely different
execution semantics, and scores the same.

Research verdict (`research/notes/semantics-pydantic-langgraph.md`): harness
lowering on Pydantic AI is *"clean and low-risk"* via `direct.model_request`; on
LangGraph via `langgraph.func.entrypoint`/`task` it is *"implementable and
actually better than native."* Eve independently validates the approach
(`stopWhen: isStepCount(1)`). **D12 is de-risked before a line is written.**

| # | Work | Gate |
|---|---|---|
| M4.1 | Adapter ABI + capability lattice (`native \| emulated \| degraded \| unsupported` per feature) | An adapter that lies about support fails CTS |
| M4.2 | Harness loop: the PACT-owned step machine | Loop is data (M6), not a constant |
| M4.3 | Pydantic AI adapter (harness lowering) | Golden agents run |
| M4.4 | LangGraph adapter (harness lowering via functional API) | Golden agents run |
| M4.5 | Conformance Test Suite, levels L0–L4 | ≥12 golden agents; Eve's `e2e/fixtures/` (23 entries) mined for cases |
| M4.6 | Fidelity report per compile | Every `degraded`/`unsupported` declared **before** execution |
| **Gate** | **AC-2.2 / D27**: same folder, both adapters, eval scores within declared ε | Published per-feature fidelity table; **AC-2.3**: adapters run from `canonical.json` alone |

> **Deliberate risk note.** M4.4 targets `langgraph.func`, a younger API surface
> than `StateGraph`. That is risk R2 (adapter rot) taken knowingly, because it
> is also the cleanest harness seam. Mitigation: adapters are out-of-tree and
> CTS-gated, so drift fails loudly rather than mis-executing.

### M5 — Model portability (the resolver)

**Goal:** author for a frontier model, run on a small one — proven or honestly
refused, with a recommendation either way (D11).

**The evidence sets the claim, and it is narrower than the brief's framing.**
Against a *hand-written* frontier strategy an optimised small model reaches
98.4% / 113.8% / 103.4%; against an *optimised* frontier strategy, 70.3% /
94.3% / 82.7%, and the gap between equally-optimised tiers does not close
(`research/notes/model-portability.md`). **The optimiser is a rising tide, not a
leveller.** M5 must ship the honest claim or it ships a lie.

| # | Work | Gate |
|---|---|---|
| M5.1 | `models/catalog.yaml`: capabilities, benchmarks, SLO characteristics, cost — **provenance required per figure** | An unprovenanced figure cannot satisfy a predicate in `strict` mode |
| M5.2 | Predicate evaluation (`reasoning >= careful && MMLU > 80`) as a **pre-filter only** | Predicates never substitute for an eval verdict |
| M5.3 | Variant selection | Authored variant chosen by target tier |
| M5.4 | Optimizer ABI + GEPA-class reference implementation | Frozen held-out split locked *before* optimisation; rejected-candidate buffer retained |
| M5.5 | **Optimiser model is a separate binding, defaulting to the strongest available** (AC-3.1b) | A config that collapses the two bindings is refused |
| M5.6 | Fail-then-recommend: search the catalogue, rank by cost, report the cheapest passing model | **D11** output format exactly as specified |
| M5.7 | Portability Report per (agent × model × adapter) | Baseline named in every report; hand-written vs optimised never conflated |
| **Gate** | **AC-3.1**: ≥95% of the *hand-written* frontier score on a designated small model, **or** a FAIL report naming the failing metrics | Both outcomes pass the gate; a silent pass fails it |

### M6 — Topology and loops as data

| # | Work | Gate |
|---|---|---|
| M6.1 | Topology IR: node kinds `{agent, router, aggregator, judge, human, tool}`, edge kinds `{delegate, handoff, broadcast, pipe, vote, subscribe}` | **Directory nesting must not imply an edge** — topology is a separate document |
| M6.2 | Declared shared state ("blackboard") as a resource | Eve proves "state is never shared" blocks 3 of the 8 patterns |
| M6.3 | Loop IR over `perceive/plan/act/observe/reflect/halt` | **AC-5.2**: ReAct, Plan-Execute, Reflexion, ToT, self-consistency, CodeAct all expressible |
| M6.4 | Interceptors: typed `(state) → state \| halt \| redirect`, separate from observe-only hooks | Hooks that can only observe cannot implement a loop |
| **Gate** | **AC-5.1**: 8 patterns × ≥3 adapters via CTS; **AC-5.3**: a config-only loop change moves a measured eval score | A decorative loop fails this |

### M7 — Learning, with governance

| # | Work | Gate |
|---|---|---|
| M7.1 | Trace ledger → eval case promotion, with redaction policy | **AC-4.4**: one command, redaction preserved |
| M7.2 | Delta-only edits to instructions and skills — never whole-file rewrites | Context-collapse guard; edits land as reviewable diffs |
| M7.3 | **Blast-radius classifier** over spec diffs (D23) — conservative and explainable | Every classification cites the rule that produced it |
| M7.4 | Sandboxed self-authored tools with test honing and a signing path (D22) | No tool reaches the registry unsigned |
| M7.5 | Topology self-modification: archive, lineage, rollback, depth limit, inherited budget | Runaway structurally impossible, not merely discouraged |
| M7.6 | Rejected-candidate buffer as negative evidence | **AC-5.5**: a rejected candidate demonstrably shapes the next cycle |
| **Gate** | **AC-5.4**: a learning cycle produces a signed, versioned, revertible **diff to a spec file**; no learned state exists outside version control | |

> **The literature makes M7.3 the load-bearing piece, not M7.2.** Model-authored
> skills *lose* 8–11 pp against no-skill, and ungated libraries fall **below**
> baseline. Learning without a gate is worse than no learning. The classifier
> and the held-out gate are the feature; the edit is the easy part.

### M8 — Ecosystem integration

| # | Work | Gate |
|---|---|---|
| M8.1 | `bud.dev/v1 → pact.dev/v1` converter (D3) | The existing manifest corpus converts; PACT proven a strict superset |
| M8.2 | Native discovery contract for `gaia-ai-runtime` | **AC-6.1**: runtime lists every agent with correct capabilities, **no build step** |
| M8.3 | Export: Bud `AgentRecord`, A2A Agent Card, OSSA — each with a loss report | **AC-6.3**: consistent with the existing `ExportReport` shape |
| M8.4 | Importers: Pydantic AI (incl. its `AgentSpec`), Goose recipes/custom agents/skills, LangGraph/LangChain | **AC-2.4**: zero silent drops across the fixture set |
| M8.5 | OTel `gen_ai` span emission | Traces feed evals, learning, and SLO verification from one stream |
| **Gate** | **AC-6.4**: a Goose recipe, custom agent, and skill each import and re-export with no CTS behaviour change | |

---

## 2. Parallelisation

```
M1 authoring ──────────────┬─→ M3 evals ─────────┬─→ M5 model portability
                           │                     │
M2 IR / digest ────────────┼─→ M4 adapters ──────┤
                           │                     │
                           └─→ M6 topology+loops ┴─→ M7 learning
                                                       │
M8 ecosystem ──────────────────────────────────────────┘  (starts any time)
```

M1 and M2 are the only hard prerequisites. M8 can start immediately and should,
because it is the fastest source of real specs to test against — the existing
Bud/Goose corpus is a free fixture set.

---

## 3. Risk register (live)

| Risk | Status | Mitigation in the plan |
|---|---|---|
| **The no-code ceiling (D14) is not reachable** | **Highest.** Unproven until M1's gate | AC-1.5 is a moderated user test with an operational definition, not self-assessment. Failing it is a finding, not an embarrassment |
| Harness lowering costs quality (F-4) | **Reduced** — two independent source verdicts plus Eve's precedent | M4 ships the continuous native-vs-harness benchmark from day one |
| Model-portability claim overstated | **Contained** — the honest baseline is now written into AC-3.1 | M5.7 requires the baseline in every report |
| Expansion Rule breaks on hard cases | **Partly resolved** — payload directories shipped and tested | Remaining: skill packages, channel `[param]` segments. Property test in M2.3 |
| Adapter rot (R2) | Accepted | Out-of-tree, CTS-gated, feature-pinned IR |
| Learning becomes an attack surface | Designed for | M7.3 classifier + signed provenance + held-out gate; no tool-output→skill writes |
| Spec sprawl | Watched | Conformance levels let an adapter certify at L2; `x-` extensions absorb the long tail |
| Duplicating AgentZero | Bounded by D24/D25 | Registry/routing/tenancy stay adapter-shaped seams |

---

## 4. What would falsify the whole approach

Stated up front so it is recognisable rather than rationalised:

1. **M1's user test fails badly** — not "they needed one hint", but "they could
   not do it." Then the Contract/Strategy split is too abstract for the audience,
   and the answer is a builder agent as the *primary* surface with files as
   output, not as the authoring interface.
2. **CTS shows irreducible per-adapter divergence** beyond ε on ordinary agents.
   Then "full portability" is false and the honest product is portability with a
   named, per-feature fidelity table — still useful, but a different claim.
3. **The optimiser cannot clear AC-3.1 on any reference agent.** Then model
   portability reduces to capability filtering plus honest reporting — which is
   still worth shipping, and is still more than anyone offers today.

None of these are fatal to the project. All of them are fatal to a *claim*, and
the plan is structured so each claim fails loudly and early rather than
quietly at scale.
