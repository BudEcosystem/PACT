# Research corpus — index

14 source-grounded studies, **~15,750 lines**, produced by the
`pact-architecture` workflow against a local corpus of **140 repositories
(~15 GB)** cloned 2026-07-25, plus 53 prior papers in
`/home/bud/ditto/gaia-ai-runtime/research/papers/`, plus a targeted web sweep.

**Rules of evidence used throughout:** every claim cites `file:line` or an exact
URL; source is read in preference to READMEs; verified claims are distinguished
from inferences; negative findings ("X cannot express Y") count as results.
Each stream's blocking and major claims were then re-checked by a separate
adversarial agent instructed to refute them.

---

## The findings that changed the design

Ordered by how much they moved the work, not by topic.

| # | Finding | Note | Consequence |
|---|---|---|---|
| 1 | **Agent scaffolding is net *negative* on small models.** At Qwen2.5-1.5B over 13 benchmarks: LangChain 32.81, AutoGen 33.57, smolagents 27.81 — all below the **raw model at 34.28**. The sign flips around 32B. | `web-frontier.md` §3.1 | The harness is a *strategy variable*, not a constant. CTS must gate harness-vs-**raw**, not just harness-vs-native (FR-4.1.12/13) |
| 2 | **The residual gap between equally-optimised model tiers does not close**, and sometimes widens (GEPA 7.80→11.51; MASS 4.41→4.49). | `model-portability.md` §1.3 | AC-3.1 rewritten: the claim holds against a *hand-written* frontier baseline (98–114%), not an *optimised* one (70–94%). The optimiser is a rising tide, not a leveller |
| 3 | **The optimiser must not run on the weak model.** ACE gain by reflector size: +17.1 (671B) → +7.6 (120B) → **+2.4** (70B). TextGrad on small executors is frequently destructive (−24.0 pp cells). | `model-portability.md` §C5 | New AC-3.1b: optimiser model is a **separate binding**, defaulting to the strongest available |
| 4 | **DeepEval parity is 51/56, not 100%.** Zero metrics need *author* code, but the six legacy RAGAS wrappers hard-import `ragas` + HF `datasets` and need a LangChain embeddings object — excluded by design, replaced by a first-class `ragas:` provider. Five provider shims required. DeepEval ships **no** YAML format. | `deepeval-surface.md`, R2-X10 | PACT authors the eval schema; nothing to adopt wholesale. Red-teaming has moved out to `deepteam`; telemetry needs an explicit opt-out for air-gap |
| 5 | **Harness lowering (D12) is implementable.** Pydantic AI via `direct.model_request` is "clean and low-risk"; LangGraph via `langgraph.func` is "actually *better* than native". Eve independently does the same (`stopWhen: isStepCount(1)`). | `semantics-pydantic-langgraph.md`, `eve-teardown.md` G3 | The thesis's most load-bearing bet, de-risked before implementation |
| 6 | **Eve's "filesystem-native" is compile-time, not runtime.** The runtime never reads the authored tree; it loads generated ESM. The compiler *executes author code* at build time. | `eve-teardown.md` S1–S3 | D2 is a genuinely different architecture, not a refinement. Also why `pact check` must never execute author code |
| 7 | **Self-evolution: 17 of 25 MLAS attack-surface cells have no effective defence.** Gradual blueprint erosion is invisible to per-diff review. | `web-frontier.md` §4 | D23's classifier operates on the wrong unit — it must also measure **cumulative drift against a frozen baseline**, and safety invariants must sit *outside* the optimiser's search space |
| 8 | **Two competitors already ship a declarative agent spec**: Oracle's Open Agent Specification (v26.1.2, 6 adapters) and Pydantic AI's own `AgentSpec` — the latter with an explicitly identical audience ("letting non-developers configure agents"). | `web-frontier.md` §1, `semantics-pydantic-langgraph.md` A(j) | PACT is not first-mover. Neither carries **evals in the portable artifact** — which is why T2, not the topology IR, is the differentiator |
| 9 | **OpenAI deprecated Evals, Agent Builder and Reusable Prompts together** (2026-06-03, shutdown 2026-11-30), pointing Evals users at Promptfoo. | `web-frontier.md` §2.1 | Three hosted authoring patterns died at once — the strongest external evidence for files-as-source-of-truth (D18/NG4) and for config-only evals |
| 10 | **MCP `2026-07-28` is a breaking revision**: stateless, no `initialize` handshake or sessions; Sampling/Roots/Logging/DCR deprecated; server-initiated requests replaced by MRTR `input_required`. | `web-frontier.md` §5 | The tool edge, HITL/elicitation IR and sandbox-roots model must target the new shape, not the corpus's `2025-11-25` |
| 11a | **Judge hardening is mostly a myth.** Measured, CoT prompting and majority voting *raise* worst-case false-positive rate on the larger judge (66.8→50.9 / 90.9→97.0) and both metrics on the smaller (12.6→40.4 / 31.0→91.3). Question-removal is recommended by its own authors for math tasks only. | `learning-governance.md`, R2-X11 |
| 11 | **Ungated skill libraries score *below* the no-skill baseline**, and model-authored skills lose 8–11 pp. | `model-portability.md` §2, `learning-governance.md` | The gate is the feature, not the edit. Library governance (dedup, exposure caps, retirement) is mandatory |
| 12 | **Directories that are payloads, not fields.** A sandbox workspace expanded by the Expansion Rule would turn `setup.py` into a field named `setup` and silently drop the extension. | `eve-teardown.md` OQ2 | Found a real bug in the loader; `Value::Payload` shipped and tested |

---

## The notes

| Note | Lines | Covers |
|---|---|---|
| [`semantics-pydantic-langgraph.md`](semantics-pydantic-langgraph.md) | 1211 | The two prototype adapters across nine semantic dimensions; the harness-lowering verdict for D12; Pydantic AI's existing `AgentSpec` |
| [`semantics-others.md`](semantics-others.md) | 1590 | AutoGen, OpenAI Agents, Claude Agent SDK, Anthropic SDK, Vercel AI SDK; the cross-framework divergence matrix a single IR must reconcile |
| [`orchestration-loops.md`](orchestration-loops.md) | 1457 | Multi-agent topologies and loop patterns as data; the minimal closed node/edge set; durability primitives |
| [`slo-observability.md`](slo-observability.md) | 1484 | TTFT/TPOT/E2E/cost definitions for *agents* rather than single calls; percentile semantics; the trace schema |
| [`filesystem-prior-art.md`](filesystem-prior-art.md) | 1219 | prompty, dotprompt, Genkit, Goose, Agent Skills, Dify; the verdict on whether the Expansion Rule is sound |
| [`config-nocode.md`](config-nocode.md) | 1158 | CUE/KCL/Pkl/CEL/OPA/OAM; what makes declarative config usable by a non-coder; error-message design |
| [`protocols-interop.md`](protocols-interop.md) | 1075 | MCP, A2A, ACP, OASF, AG-UI, OTel `gen_ai`, CloudEvents; the exact mapping surface and what has no home |
| [`bud-integration.md`](bud-integration.md) | 1071 | Full `bud.dev/v1` field inventory for the D3 superset proof; the native-discovery contract; migration risks |
| [`multimodal-computeruse.md`](multimodal-computeruse.md) | 1048 | Content-type model across all 7 frameworks; sandboxing and approval gates; how a non-coder writes a screenshot or voice eval |
| [`learning-governance.md`](learning-governance.md) | 919 | Artifacts a learning cycle may write; the blast-radius classifier rules; self-authored tools; poisoning defences |
| [`eve-teardown.md`](eve-teardown.md) | 902 | Line-by-line teardown of the closest prior art: loader, slots, harness, subagents, evals; 15 structural limits and 17 ideas worth keeping |
| [`eve-capabilities.md`](eve-capabilities.md) | — | **The numbered capability inventory the acceptance clause counts.** 98 rows re-enumerated from `packages/eve` and `packages/eve-catalog`, each with the Eve file and symbol it was read from and its letter — (a) expressible in the schema, (b) declared and delegated, (c) refused or deferred. 51 / 22 / 25, none outside. Held by `crates/pact-cli/tests/eve_inventory.rs`, which fails on a row with two letters or none, a source path that no longer exists, a (c) row pointing at a ledger entry that was renamed, or a header that has drifted from its own rows |
| [`model-portability.md`](model-portability.md) | 876 | The empirical basis for T4: measured transfer, mechanism ranking with failure conditions, the honest ceiling, the optimiser ABI |
| [`deepeval-surface.md`](deepeval-surface.md) | 873 | All 56 metrics enumerated from source; config-expressibility per metric; the 4 shims; air-gap analysis |
| [`web-frontier.md`](web-frontier.md) | 867 | What the local corpus does not contain: Oracle Agent Spec, the 2026 deprecations, MCP's breaking revision, new small-model evidence, self-evolution security |
| [`gap-r2-3.md`](gap-r2-3.md) | — | **Round-2 gap 3 — effect size for `propose-only` learning (H37).** Corpus sweep confirming no system records a human accept/reject over a machine-proposed spec diff; three external production measurements of exactly that (Google ICSE-SEIP '24 **63.6%** reviewer accept and **4.9%→7.5%** end-to-end when a human gate was *added* at a *lower* model precision; Copilot ~30%; Poly et al. 46.2–96.2% override as the fatigue bound); the binomial arithmetic that closes H37's falsifier; and two shipped defects — an unbounded review queue and a bet that could not be falsified because rejections were not recorded. Applied in §8.7a (QUEUE-1..7), §11.10, §13.15.3, §14.1 |
| [`gap-r1-3.md`](gap-r1-3.md) | — | **Round-1 gap 3 — the per-metric ε distribution.** A measured same-agent null band (tau-bench, 1,980 replicate rows, deterministic grader); five ε classes read out of grader source with pre-measurement quantisation floors; the coverage collapse that makes suite-level n meaningless; four prior-art negatives. Applied in §10.1/§10.2/§6.9-E |

---

## How to use this

- **Designing a subsystem** — read its note in full before proposing anything.
  Each ends with actionable design implications, and several contain complete
  inventories (every DeepEval metric, every `bud.dev/v1` field) that would be
  expensive to reconstruct.
- **Checking a claim** — every finding cites `file:line`. The corpus is at
  `research/repos/`, still on disk. Follow the citation rather than trusting the
  summary.
- **Open questions** — most notes end with one. They are honest gaps, not
  rhetorical, and several are cheap experiments worth running.
