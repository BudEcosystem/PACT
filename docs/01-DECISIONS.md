# PACT — Locked Decisions (Alignment Record)

**Date:** 2026-07-26. **Status:** Binding. Supersedes any conflicting statement in
`00-THESIS.md`; that document has been updated to match.

Every decision below was made explicitly by the project owner. Where a decision
narrows or overrides the thesis, the consequence is spelled out, because these are
the constraints all downstream design must satisfy.

---

## D1 — Identity & naming

| Item | Decision |
|---|---|
| Name | **PACT** — Portable Agent Contract & Topology |
| API version | `pact.dev/v1` |
| CLI | `pact` |
| Derived dir | `.pact/` |
| Status | Permanent and user-facing (not a placeholder) |

## D2 — The native representation is the filesystem

> **The truly native form of a PACT agent is the folder-and-file tree** — as in
> Vercel Eve. `gaia-ai-runtime` executes that tree **natively, without a
> compilation step**. Other frameworks are *conversion targets only*.

**Consequences (load-bearing):**
1. `canonical.json` is a **derived index/IR**, *not* the source of truth. It exists
   to serve adapters, caching, digests, and signing. Deleting it must be harmless.
2. The tree must be directly interpretable — no build artifact may be required to
   run. "Build" is an optimisation, never a prerequisite.
3. Therefore the **runtime reads the tree**, and the *loader* (tree → in-memory
   document) is a first-class, specified, testable component with a normative
   algorithm — not an implementation detail.
4. Round-tripping is `tree ⇄ document`, and the tree side is authoritative on
   conflict.

## D3 — Replaces `bud.dev/v1`

PACT becomes the single manifest format. The existing Bud Agent manifest is
migrated onto it. This is an accepted breaking change to a mature Rust codebase.

**Consequences:** a migration path (`bud.dev/v1 → pact.dev/v1`) with a mechanical
converter and a compatibility shim is a first-class deliverable, not an
afterthought. Everything the Bud manifest expresses today must be expressible in
PACT on day one — this is a hard superset requirement, verified by converting the
existing manifest corpus.

## D4 — Implementation

| Layer | Language |
|---|---|
| Core: loader, validator, canonicaliser, resolver, CLI, conformance runner | **Rust** (matches `bud-gaia`, `gaia-ai-runtime`) |
| Adapters | Out-of-tree, in the language each framework needs — **Python** (Pydantic AI, LangGraph, LangChain, AutoGen, OpenAI Agents), **TypeScript** (Vercel AI SDK, Claude Agent SDK TS) |
| Eval providers | Pluggable; **DeepEval first** (Python provider process) |

## D5 — Session deliverable

Docs **plus a working prototype**: schema, loader/validator, canonical IR, and two
adapters (**Pydantic AI** + **LangGraph**), with the first demo defined in D20.

## D6 — Eval engine

**Pluggable providers, DeepEval first.** Config declares metrics by URI
(`deepeval:faithfulness`); a provider layer executes them. Ragas, native, and
custom providers plug in later without spec change.

## D7 — Second adapter: LangGraph

Chosen for maximum semantic distance from Pydantic AI (checkpointed graph state
machine vs typed single run). If one folder drives both faithfully, two-level
lowering is proven rather than asserted.

## D8 — Model catalogue: hybrid

Local `models/catalog.yaml` is **authoritative and offline-capable**; Bud platform
and external feeds (Artificial Analysis, OpenRouter, HELM, model cards) are
**optional pluggable providers** that populate it. Required by D17 (air-gapped).

## D9 — Learning: fully specified, thin working slice

Complete design for optimizer ABI, variant synthesis, trace→eval promotion, and
review gates — **plus one real end-to-end run**: a small model fails an eval, the
optimizer rewrites the strategy, it passes.

## D10 — Design center (priority order)

1. **Authoring layer of the AI OS** — people creating new agents on Bud/Gaia.
2. **Open industry interop standard** — spec stays clean enough to open-source.
3. **Migration tool** — importers as a first-class on-ramp.

Work is sequenced so each stage is independently useful.

## D11 — Failure stance: fail, then recommend

When a requested model cannot meet the contract, the system **refuses to bind**,
then **searches the catalogue and recommends the cheapest model that does pass**:

```
PORTABILITY: FAIL for qwen3-4b
  answer_relevancy 0.61 < 0.80 required   (best of 14 candidate strategies)
RECOMMENDED: qwen3-14b — passes at 0.83, 3.1× cheaper than your current binding
```

**Consequence:** the Resolver is a **recommender**, not just a gate. Catalogue
search + cost ranking is core functionality, not a nice-to-have.

## D12 — Loop ownership: harness lowering, fidelity over idiom

PACT owns loop semantics; frameworks are model/tool transports. Accepted
trade-off: generated code looks less like hand-written LangGraph, and PACT owns
responsibility for loop quality (see `F-4`: harness underperforming native is a
tracked defect).

## D13 — "Normal person" = non-technical domain expert

A support lead, analyst, or ops manager. Can edit YAML/Markdown if shown how;
**cannot write code**. The system must be **no-code end-to-end**, with heavy
defaults and templates.

## D14 — No-code bar: the maximum, not the minimum

A non-technical domain expert must be able to build **a multi-agent system with
custom tools (via MCP), their own eval cases, SLO limits, and the learning loop
enabled — entirely in YAML/Markdown.**

**Consequence:** every feature must have a no-code expression. "Expert users write
code for this" is not an acceptable answer for *any* capability in the core.

## D15 — Migration: translate or nothing

**No opaque wrapping.** An existing framework app cannot be embedded as a black
box. Everything entering the system must be expressed in the IR, so every agent in
PACT is genuinely portable. Slower adoption is accepted in exchange for spec
purity.

## D16 — Modalities in v1: all four

Text + tool calling · **Vision** (images, documents, screenshots) · **Audio/voice**
(streaming, TTFT-sensitive) · **Computer use / browser automation** (sandboxing +
approval gates).

**Consequence:** I/O contracts are content-typed from day one; SLOs must be
modality-aware (voice TTFT ≠ batch E2E); the capability vocabulary must cover
`vision`, `audio_in/out`, `computer_use`, `web_scrape`, `code_interpreter`.

## D17 — Deployment targets: all four

On-prem/private cloud · **fully air-gapped** · public cloud/SaaS · local dev
machines and edge.

**Consequence (hard):** the entire pipeline — validate, resolve, build, eval,
optimise — must run **offline with zero network dependency**. Benchmark figures,
metric providers, and judge models must all have local paths. This makes D8's
local-first catalogue mandatory and forbids any core feature that requires a
hosted service.

## D18 — Author surfaces: all four, one substrate

Files in an editor · a UI that reads/writes the same files · conversation with a
builder agent · git/PR review with eval results attached.

**Consequence:** the file format is the API for all four. It must be simultaneously
hand-editable, machine-generatable, form-renderable, and diff-friendly. This is a
strong constraint on syntax: no significant ordering games, no ambiguity, stable
serialisation, human-meaningful diffs.

## D19 — Eval authoring: five on-ramps, one model

1. **Examples** — "when asked X, the answer should be like Y".
2. **Plain-language rules** — "must cite a source", "never promise a refund".
3. **Captured from real usage** — mark conversations good/bad in a review queue.
4. **Builder-agent generated**, human-approved.
5. **Expert upload** — JSON/YAML carrying **metrics and rubrics with the full
   capability surface DeepEval provides**.

**Consequence:** one underlying eval document model, with (1)–(4) as *sugar that
desugars into it* and (5) as the *full-fidelity form*. Not five subsystems.

## D20 — First demo (build target #1)

> **A non-technical author builds a multi-agent system** — only YAML and Markdown,
> producing a working supervisor plus specialists with evals.

This outranks the portability demo. The prototype is sequenced to reach this
first, then prove Pydantic AI ⇄ LangGraph parity on the same folder.

## D21 — Twelve-month definition of success

**Non-technical people shipping real agents.** Cost collapse, self-improvement,
and external spec adoption are valuable but subordinate.

## D22 — Learning scope: three of four

Agents may learn: **(a) instructions, prompts, and skills**; **(b) new tools they
author for themselves**; **(c) their own structure and topology**.
Facts/memory-only is *not* the ceiling.

**Consequence:** the learning subsystem needs sandboxed tool authoring with a
signing path, and a topology archive with lineage and rollback — the strongest
form of self-modification, so the governance in D23 is mandatory rather than
optional.

## D23 — Autonomy: blast-radius classification

**Auto-apply low-risk; human review for high-risk.** Wording/formatting changes
auto-apply; anything touching tools, permissions, or decision logic requires a
human.

**Consequence:** a normative **change-classification function** over spec diffs is
a core component. It must be conservative and explainable.

## D24 — Scale: minimal and adapter-based

Platform scale (thousands of agents, many tenants) is the eventual target, **but a
dedicated system already exists for it at `/home/bud/ditto/bud` (AgentZero)**.

> **PACT keeps registry, routing, multi-tenancy, and collective concerns MINIMAL
> and ADAPTER-BASED.** Expose clean seams; do not build the platform.

## D25 — AgentZero seam: independent for now

Design PACT without assuming AgentZero exists; integrate later. Avoid premature
coupling. (Combined with D24: leave *seams*, not *dependencies*.)

## D26 — Performance budget

**Small runtime overhead is acceptable if it buys fidelity** — a few percent
latency and no meaningful token increase. Tracked as a continuous benchmark
against native framework use.

## D27 — Fidelity bar

**Same eval scores within a declared small margin.** Wording and intermediate
steps may differ. This is the pass/fail rule of the Conformance Test Suite.

## D28 — Named failure modes (to be actively designed against)

1. **Too complex to actually use** — becomes another expert-only framework.
2. **Portability technically true but useless** — ports, but behaves worse
   everywhere, so nobody trusts it.
3. **Too slow or expensive** — the abstraction costs more than it saves.

Notably *not* named: "never escapes being a Bud-only format." External adoption is
desirable but is not a failure condition.

---

## Consolidated impact on the thesis

| Thesis element | Change from decisions |
|---|---|
| T1 Separation | Unchanged. |
| T2 Evals as oracle | **Strengthened** — D19 adds four no-code on-ramps plus full-fidelity expert upload; D13/D14 make no-code authoring mandatory for *every* feature. |
| T3 Two-level lowering | **Confirmed** (D12), with D27 as the pass/fail rule and D26 the cost ceiling. |
| T4 Model portability | **Extended** — D11 makes the Resolver a recommender, not only a gate. |
| T5 Expansion Rule | **Promoted to the centre** — D2 makes the tree the native form, so the loader is normative and the Expansion Rule is the execution model's own semantics, not authoring sugar. |
| T6 Learning emits source | **Strengthened** — D22 admits self-authored tools and topology change, so D23's blast-radius classifier and signed provenance become mandatory. |
| T7 Structural honesty | Unchanged; D11 adds the recommendation obligation. |
| NG1 "not a runtime" | **Revised.** D2 requires the tree to be natively executable and D12 gives PACT loop semantics. PACT is not a *server*, but it does own an execution model that `gaia-ai-runtime` implements. |
| NG4 "not a visual builder" | **Revised.** D18 admits a UI — but it reads and writes the same files, so files remain the source of truth. The prohibition was on the UI *being* the source of truth, and that stands. |
| Scale/registry ambitions | **Cut** per D24 — minimal, adapter-based seams only. |
