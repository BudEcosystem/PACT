# PACT — Functional Requirements

**Date:** 2026-07-26. **Status:** Baseline.
**Traceability:** every requirement cites the decision (`D*`), thesis claim
(`T*`), invariant (`P/E/G/F-*`), acceptance criterion (`AC-*`), or research note
that makes it necessary. A requirement with no upstream justification is a
feature nobody asked for and must be deleted.

**Reading key.**
**MUST** — conformance depends on it. **SHOULD** — expected; deviation must be
recorded in the fidelity report. **MAY** — optional.
`▣` = implemented and tested today · `◐` = partially implemented · `☐` = not started.

---

## 1. Authoring surface

### 1.1 The Expansion Rule

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-1.1.1** | A directory MUST load as a set of fields, one per entry, keyed by the entry name with extension and ordinal prefix removed. | T5, D2 | ▣ |
| **FR-1.1.2** | A field MUST be writable either inline or as a directory entry, and both forms MUST produce the identical document. | T5, AC-1.4 | ▣ |
| **FR-1.1.3** | A directory MAY contain a *self file* (`_index.*`, `<dirname>.*`, or a kind name such as `agent.*`) supplying the directory's own fields. | D13 usability | ▣ |
| **FR-1.1.4** | Defining the same field twice MUST be an error naming both locations. Precedence MUST NOT be used to resolve it. | T7 | ▣ |
| **FR-1.1.5** | Entry order MUST be deterministic: ordinal prefixes ascending, then byte-order by name. Filesystem read order MUST NOT be observable. `localeCompare`-style collation MUST NOT be used. | O1.2, `eve-teardown.md` L15 | ▣ |
| **FR-1.1.6** | Names differing only by case MUST be an error, so a tree authored on Linux loads identically on macOS and Windows. | P-5 | ▣ |
| **FR-1.1.7** | A *payload directory* (a verbatim file set — sandbox workspace, assets) MUST preserve filenames and extensions and MUST NOT expand into fields. | T7, `eve-teardown.md` OQ2 | ▣ |
| **FR-1.1.8** | Non-text payloads MUST become references carrying path, media type and size. Bytes MUST NOT be inlined. | D16 | ▣ |
| **FR-1.1.9** | An unrecognised file inside a typed directory MUST be reported, never silently skipped. `.pactignore` MUST provide the explicit opt-out. | `eve-teardown.md` §10.6 | ◐ (`.pactignore` done; typed-directory reporting pending schema) |
| **FR-1.1.10** | Symlinks MUST NOT be followed by default; cycles MUST be detected and reported. | supply-chain, D17 | ▣ |
| **FR-1.1.11** | `explode` (document → tree) MUST be the inverse of the loader: `explode(collapse(X)) ≡ X`. | AC-1.2 | ☐ |

### 1.2 Progressive disclosure

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-1.2.1** | A valid agent MUST be expressible as one file of ≤5 lines containing no code. | O7.1 | ▣ |
| **FR-1.2.2** | A complete multi-agent system with tools, evals, SLOs and learning MUST be expressible in YAML/Markdown alone. | **D14** | ▣ |
| **FR-1.2.3** | Every capability in the core MUST have a no-code expression. "Write code for that" is not an acceptable answer for any core feature. | D14 | ◐ |
| **FR-1.2.4** | Identity MUST derive from path; authoring a redundant `name` MUST NOT be required. A stable `id` MAY be declared where durable identity is needed. | `eve-teardown.md` G1, §10.18 | ◐ |
| **FR-1.2.5** | Templates for the common shapes (single agent, supervisor + specialists, pipeline) MUST ship, because fork-and-tweak dominates real usage. | `platform-vision`, GPT-Store evidence | ☐ |

### 1.3 Diagnostics

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-1.3.1** | Every diagnostic MUST carry **where** (file:line:col), **what** (plain language), **why** (stable rule id) and **how** (a typeable fix). | O7.3, D13 | ▣ |
| **FR-1.3.2** | It MUST be structurally impossible to construct a diagnostic without a fix. | O7.3 | ▣ |
| **FR-1.3.3** | Diagnostics MUST NOT contain programmer jargon (type names, `enum`, `deserialize`, stack traces). | D13 | ▣ |
| **FR-1.3.4** | An unknown field MUST produce a "did you mean" suggestion when a near match exists, and MUST stay silent rather than suggest a bad match. | D13 | ▣ |
| **FR-1.3.5** | All problems in a tree MUST be reported in a single pass. One error MUST NOT mask the rest. | D13 | ▣ |
| **FR-1.3.6** | Diagnostic ordering MUST be deterministic. | testability | ▣ |
| **FR-1.3.7** | Rule ids MUST be stable across releases so they can be documented, suppressed, and asserted in tests. | governance | ▣ |

### 1.4 Values and types

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-1.4.1** | Plain scalars MUST resolve by the YAML 1.2 core schema only. `yes`/`no`/`on`/`off` MUST NOT be booleans at parse time (the "Norway problem"). | D13 | ▣ |
| **FR-1.4.2** | Coercion MUST be type-directed: `yes` becomes a boolean only where a boolean is expected. | FR-1.4.1 | ▣ |
| **FR-1.4.3** | Leading-zero values (`01234`) MUST stay text. | data integrity | ▣ |
| **FR-1.4.4** | Durations (`2s`, `1m30s`), money (`0.05 USD`), percentages (`90%`) and thresholds (`> 80`) MUST be authorable in their natural form. | D13, brief | ▣ |
| **FR-1.4.5** | Money MUST retain its currency; currencies MUST NOT be converted or defaulted. | correctness | ▣ |
| **FR-1.4.6** | Ambiguous forms (a bare `90` for a percentage) MUST be refused, not guessed — guessing silently moves a pass threshold. | T7 | ▣ |
| **FR-1.4.7** | A single value MAY be accepted where a list is expected. | D13 ergonomics | ▣ |
| **FR-1.4.8** | `x-`-prefixed fields MUST round-trip untouched. | E-2, P-3 | ▣ |

### 1.5 The specification itself

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-1.5.1** | The schema MUST be data, loaded by the same loader. Adding a field MUST NOT require recompiling the core. | E-3, F-1 | ▣ |
| **FR-1.5.2** | Every field MUST carry one line of plain-language help. | D13 | ▣ |
| **FR-1.5.3** | Fields MUST support aliases, so importers map foreign vocabularies without loss. | P-3 | ▣ |
| **FR-1.5.4** | A malformed specification MUST be reported and MUST NOT be treated as "no checks". | T7 | ▣ |
| **FR-1.5.5** | Validation MUST NOT be silently skipped when no workspace specification is found; a built-in copy MUST be used and its source reported. | T7 | ▣ |
| **FR-1.5.6** | Validation MUST NOT execute author code. | D17, D23 | ▣ |

---

## 2. The contract

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-2.1.1** | An agent MUST be able to declare **capability requirements** (reasoning depth, tool calling, vision, audio, computer use, long context, code interpreter, web search/scrape). | T1, D16 | ◐ |
| **FR-2.1.2** | Requirements MUST be usable as a **pre-filter only**. They MUST NOT substitute for an eval verdict. | T2, `model-portability.md` | ☐ |
| **FR-2.1.3** | Benchmark predicates (`MMLU > 80 && SWE-Verified > 40`) MUST be authorable. | brief | ◐ |
| **FR-2.1.4** | SLOs MUST be declarable: TTFT, TPOT, end-to-end, cost, throughput — with percentile semantics. | brief, O4.2 | ◐ |
| **FR-2.1.5** | SLO assertions MUST declare a percentile and MUST be refused below a minimum sample size. | `slo-observability.md` | ☐ |
| **FR-2.1.6** | SLOs MUST be modality-aware — voice interactivity budgets differ from batch. | D16 | ☐ |
| **FR-2.1.7** | I/O contracts MUST be content-typed (text, image, audio, video, binary, stream, tool result), not string-typed. | G-1, D16 | ☐ |
| **FR-2.1.8** | An author MUST be able to pin an exact model, disabling substitution; the pin MUST be recorded in the lockfile. | AC-3.4 | ☐ |
| **FR-2.1.9** | Policy MUST be declarable: approval gates, redaction, autonomy level, data handling. | T1, D23 | ◐ |

---

## 3. Evaluation

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-3.1.1** | Evals MUST be authorable entirely in config. No eval expressible in DeepEval may require author code. | G4, AC-4.2 | ☐ |
| **FR-3.1.2** | Five on-ramps MUST desugar into **one** document model: examples, plain-language rules, captured-from-usage, builder-agent-generated, expert JSON/YAML upload. | **D19** | ☐ |
| **FR-3.1.3** | Metrics MUST be declared by URI (`deepeval:faithfulness`) against a pluggable provider registry. | D6, E-4 | ▣ (`evals.metrics:` in `spec/schema.yaml`; read by `evals.metrics_of`, run by `evals.check`) |
| **FR-3.1.4** | **51 of DeepEval's 56** metrics MUST be pure-config given five provider shims. The six legacy `deepeval/metrics/ragas.py` wrappers are **excluded by design** — they require a `langchain_core` embeddings object and hard-import `ragas` + HF `datasets` — and are replaced by a first-class `ragas:` provider under D6. | AC-4.1, `deepeval-surface.md`, R2-X10 | ▣ (every metric the installed release exports bar the RAGAS wrappers — 47 of 47 on DeepEval 4.1.3; the count is not pinned, the property is) |
| **FR-3.1.5** | Provider-specific defaults MUST NOT be silently normalised (e.g. `conversation_completeness` defaults to a window of 3, others to 10) — normalising changes scores. | `deepeval-surface.md` §7.1 | ◐ (`with:` is passed through unchanged and a setting the score does not take is reported; nothing yet reads a per-metric default table) |
| **FR-3.1.6** | Structural assertions MUST be expressible as predicates: tool called/not called, tool order, tool count, subagent called, skill loaded, event order, no failed actions. | `eve-teardown.md` G10 | ☐ |
| **FR-3.1.7** | Assertions MUST carry severity: gate, soft, or soft-with-threshold; `--strict` MUST promote soft misses to failures. | `eve-teardown.md` G11 | ☐ |
| **FR-3.1.8** | Deterministic checkers MUST run before LLM judges; a fully decidable suite MUST NOT invoke a judge. | AC-4.5 | ☐ |
| **FR-3.1.9** | The judge model MUST be declarable and MUST NOT default to the agent under test. | judge-hardening, `2507.08794` | ☐ |
| **FR-3.1.10** | Evals MUST run against any adapter and against a remote agent with no eval-file changes. | AC-4.3 | ☐ |
| **FR-3.1.11** | Trace and span-level evals MUST be selectable declaratively (`on:` / `where:`). | `deepeval-surface.md` §7.3 | ☐ |
| **FR-3.1.12** | Failing production traces MUST be promotable to eval cases in one command, preserving redaction. | AC-4.4 | ☐ |
| **FR-3.1.13** | Redaction MUST be declarative, not a callable. | `deepeval-surface.md` §6.8 | ☐ |
| **FR-3.1.14** | A mock/replay model MUST ship in the core for deterministic offline runs. | D17, `eve-teardown.md` G9 | ☐ |
| **FR-3.1.15** | The full eval pipeline MUST run air-gapped, with third-party telemetry disabled by default. | **D17**, AC-7.3 | ☐ |

---

## 4. Framework portability

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-4.1.1** | Every adapter MUST implement harness lowering — framework as model/tool transport, PACT owning the loop. | **D12**, T3 | ☐ |
| **FR-4.1.2** | Native lowering MAY be used per feature, only where CTS proves equivalence. | T3 | ☐ |
| **FR-4.1.3** | Adapters MUST consume `canonical.json` only and MUST NOT read author files. | P-1, AC-2.3 | ☐ |
| **FR-4.1.4** | Each adapter MUST publish a capability lattice: `native \| emulated \| degraded \| unsupported` per IR feature. | P-2 | ☐ |
| **FR-4.1.5** | Any `degraded` or `unsupported` feature MUST be reported **before** execution. | T7, AC-2.2 | ☐ |
| **FR-4.1.6** | Adding a new adapter MUST require zero core changes, proven in CI by an out-of-tree adapter. | **E-1**, AC-2.5 | ☐ |
| **FR-4.1.7** | Import MUST be lossless-or-reported; unmapped constructs MUST be preserved in `x-` blocks, never dropped. | P-3, AC-2.4 | ☐ |
| **FR-4.1.8** | Opaque wrapping of a framework app MUST NOT be supported. | **D15** | n/a |
| **FR-4.1.9** | Runtime overhead versus native framework use MUST be continuously benchmarked; harness underperformance is a tracked defect. | F-4, D26 | ☐ |
| **FR-4.1.12** | The CTS MUST gate **harness-vs-raw-model**, not only harness-vs-native. At small model sizes agent scaffolding is measurably *net negative* (LangChain 32.81, AutoGen 33.57, smolagents 27.81 vs raw 34.28 at Qwen2.5-1.5B over 13 benchmarks). | T3-corollary, `web-frontier.md` §3.1 | ☐ |
| **FR-4.1.13** | The **harness itself MUST be a per-tier strategy variable**: the resolver MUST be able to select reduced scaffolding for a weak executor, up to and including a bare model call. | T3-corollary | ☐ |
| **FR-4.1.14** | The MCP integration MUST target the `2026-07-28` shape — stateless, no `initialize` handshake or sessions, MRTR `input_required` retry in place of server-initiated requests — not the `2025-11-25` shape in the corpus. Sampling, Roots, Logging and DCR are deprecated. | `web-frontier.md` §5 | ☐ |
| **FR-4.1.15** | Native lowering for Pydantic AI SHOULD be **spec-to-spec** (PACT document → `AgentSpec`), not code generation. | `web-frontier.md` §6.1 | ☐ |
| **FR-4.1.16** | PACT MUST own variant selection. LangGraph's equivalent ("Assistants") is hosted-only and absent from OSS LangGraph, so it cannot supply variants under D17. | `web-frontier.md` §6.3 | ☐ |
| **FR-4.1.10** | Durable semantics — session/turn/step, park, resume, recursive cancel, child budget capped by parent — MUST be IR concepts, mapped by adapters. | P-5, `eve-teardown.md` G4/G12 | ☐ |
| **FR-4.1.11** | Durable history MUST NOT carry binary payloads; attachments MUST be content-addressed references hydrated per call. | D16, `eve-teardown.md` G13 | ☐ |

---

## 5. Model portability

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-5.1.1** | The model catalogue MUST be local-first and fully functional offline; network feeds are optional providers that populate it. | **D8, D17** | ☐ |
| **FR-5.1.2** | Every benchmark figure MUST carry provenance (source, date, harness, contamination note). Unprovenanced figures MUST NOT satisfy a predicate in `strict` mode. | AC-3.3 | ☐ |
| **FR-5.1.3** | Multiple strategy **variants** MUST be authorable per agent and selected by target. | T1, T4 | ☐ |
| **FR-5.1.4** | The resolver MUST emit a lockfile: agent × variant × model × adapter × runtime × tools, plus a verdict. | O3.3 | ☐ |
| **FR-5.1.5** | Binding a model outside the authored tier MUST require an eval verdict. | P-4 | ☐ |
| **FR-5.1.6** | On failure the resolver MUST refuse to bind, then search the catalogue and **recommend the cheapest passing model**. | **D11** | ☐ |
| **FR-5.1.7** | The **optimiser model MUST be a separate binding** from the execution model and MUST default to the strongest available, never the target. | **AC-3.1b**, `model-portability.md` C5 | ☐ |
| **FR-5.1.8** | Optimisation MUST lock a held-out split before it begins and MUST retain a rejected-candidate buffer. | AC-3.5, R6 | ☐ |
| **FR-5.1.9** | Optimisation MUST tune text and skills before topology; decomposition MUST NOT be applied below the capability-gap threshold where it causes negative drag. | MASS, skill-scaling-laws Eq. 4 | ☐ |
| **FR-5.1.10** | Every Portability Report MUST name its baseline (hand-written vs optimised frontier). Conflating them MUST be impossible. | **AC-3.1** | ☐ |
| **FR-5.1.11** | Per-agent exposure of tools/skills MUST be capped and curated, with full-text descriptions inside the exposed set. | in-repo benches 1–2 | ☐ |
| **FR-5.1.12** | Capability routing MUST be hierarchical (family/server → member), never flat top-k. | in-repo bench 2 | ☐ |

---

## 6. Orchestration, loops, learning

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-6.1.1** | Topology MUST be a separate document; directory nesting MUST NOT imply an edge. | G-2, `eve-teardown.md` §10.8 | ☐ |
| **FR-6.1.2** | ≥8 patterns MUST be expressible: supervisor, hierarchical, pipeline, map-reduce, swarm/handoff, debate, blackboard, market/auction. | AC-5.1 | ☐ |
| **FR-6.1.3** | Shared state ("blackboard") MUST be declarable as a resource. | AC-5.1 | ☐ |
| **FR-6.1.4** | The agent loop MUST be authored data over `perceive/plan/act/observe/reflect/halt`. | G-3 | ☐ |
| **FR-6.1.5** | ≥6 loop patterns MUST be expressible: ReAct, Plan-Execute, Reflexion, Tree-of-Thought, self-consistency, CodeAct. | AC-5.2 | ☐ |
| **FR-6.1.6** | Interceptors that can mutate state MUST exist, typed and declared, separate from observe-only hooks. | `eve-teardown.md` §10.10 | ☐ |
| **FR-6.1.7** | Any agent MUST be usable as a node in any topology, and any topology MUST be exposable as an agent. | G-4 | ☐ |
| **FR-6.2.1** | Learning MUST emit reviewable source — diffable spec files, never opaque state. | **T6** | ☐ |
| **FR-6.2.2** | Instruction and skill edits MUST be deltas, never whole-file rewrites. | ACE/context-collapse | ☐ |
| **FR-6.2.3** | A **blast-radius classifier** MUST classify every spec diff as low-risk (auto) or high-risk (human), conservatively and explainably. | **D23** | ☐ |
| **FR-6.2.3a** | The classifier MUST **also operate on cumulative drift against a frozen baseline**, not only on individual diffs. Gradual blueprint erosion is invisible to per-diff review; 17 of 25 MLAS attack-surface cells have no effective defence. | `web-frontier.md` §4 | ☐ |
| **FR-6.2.3b** | Safety invariants MUST live **outside the optimiser's search space** — structurally unreachable by self-modification, not merely weighted against. | `web-frontier.md` §4.4 | ☐ |
| **FR-6.2.4** | A change MUST be kept only if it improves a frozen held-out eval split. | D9, AC-5.4 | ☐ |
| **FR-6.2.5** | Self-authored tools MUST be sandboxed, test-honed, signed and registered. | D22 | ☐ |
| **FR-6.2.6** | Topology self-modification MUST carry archive, lineage, rollback, depth limits and inherited budgets. | D22 | ☐ |
| **FR-6.2.7** | Tool output MUST NOT write directly to skills or memory. | ASI06, MINJA | ☐ |
| **FR-6.2.8** | Rejected candidates MUST be retained as negative evidence for the next cycle. | AC-5.5 | ☐ |
| **FR-6.2.9** | Skill libraries MUST be governed — deduplication, exposure caps, retirement — because ungated libraries score **below** the no-skill baseline. | library-drift, SkillsBench | ☐ |

---

## 7. Ecosystem

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-7.1.1** | PACT MUST be a strict superset of `bud.dev/v1`, with a mechanical converter. | **D3** | ☐ |
| **FR-7.1.2** | `gaia-ai-runtime` MUST be able to discover and run a PACT tree **with no build step**. | **D2**, AC-6.1 | ☐ |
| **FR-7.1.3** | Export to Bud `AgentRecord`, A2A Agent Card and OSSA MUST each emit a loss report. | AC-6.3 | ☐ |
| **FR-7.1.4** | Importers MUST exist for Pydantic AI (including its `AgentSpec`), Goose recipes/custom agents/skills, and LangGraph/LangChain. | **D-estate** | ☐ |
| **FR-7.1.5** | Traces MUST be emitted using OTel `gen_ai` semantic conventions. | `slo-observability.md` | ☐ |
| **FR-7.1.6** | Registry, capability routing at scale, and multi-tenancy MUST remain adapter-shaped seams, not built here. | **D24, D25** | n/a |

---

## 8. Cross-cutting

| ID | Requirement | Source | State |
|---|---|---|---|
| **FR-8.1.1** | No lossy operation anywhere may proceed silently; each MUST emit a report entry and be fail-closed by default. | **T7**, AC-7.1 | ◐ |
| **FR-8.1.2** | `allowLoss` MUST be explicit and recorded in the lockfile. | T7 | ☐ |
| **FR-8.1.3** | Every default MUST resolve from a profile; the core MUST contain no capability-affecting literal. | **F-1**, AC-7.2 | ◐ |
| **FR-8.1.4** | The full pipeline MUST run offline with no network dependency in the core. | **D17**, AC-7.3 | ◐ |
| **FR-8.1.5** | Loading MUST be deterministic and reproducible across platforms. | O1.2 | ▣ |
| **FR-8.1.6** | Shadowing and precedence decisions MUST be reported, never silent. | T7, `eve-teardown.md` §10.17 | ☐ |
| **FR-8.1.7** | Any declarative node MAY be replaced by a typed, declared code reference; its portability MUST then be reported as `unsupported` unless the target hosts that language. | F-2, F-3 | ☐ |

---

## 9. Coverage summary

| Area | Requirements | Implemented | Partial | Not started |
|---|---|---|---|---|
| 1 Authoring surface | 37 | 32 | 3 | 2 |
| 2 Contract | 9 | 0 | 4 | 5 |
| 3 Evaluation | 15 | 0 | 0 | 15 |
| 4 Framework portability | 16 | 0 | 0 | 15 (+1 n/a) |
| 5 Model portability | 12 | 0 | 0 | 12 |
| 6 Orchestration/loops/learning | 18 | 0 | 0 | 18 |
| 7 Ecosystem | 6 | 0 | 0 | 5 (+1 n/a) |
| 8 Cross-cutting | 7 | 1 | 3 | 3 |
| **Total** | **120** | **33** | **10** | **75 (+2 n/a)** |

Recomputed from the rows above rather than kept by hand. The table used to
disagree with the document it summarises in three directions at once — a stated
total of 113 against 120 rows, a Requirements column summing to 107, and a
Not-started column summing to 68 against a stated 74 — and `README.md` repeated
the 107 twice. A summary nobody recomputes is exactly what §8.3 of
`50-NOT-COPIED.md` names as the way a figure comes to be derivable from nothing.

The authoring surface is deliberately far ahead of everything else: decision
**D20** makes it the first demo, and **D14** makes it the constraint every later
area must satisfy. Building evals or adapters against a surface that cannot be
authored by its intended user would be building on sand.
