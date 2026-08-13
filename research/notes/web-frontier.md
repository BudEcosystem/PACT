# Research stream: web-frontier

> **This note contains two sweeps.**
> **PART I** (§0–§10) is the sweep of **2026-07-26**, preserved verbatim because `00-THESIS.md` and
> `research/notes/README.md` cite it by section number (notably §3.1, EffGen).
> **PART II** (§0-II, §10-RESOLVED, §11–§22) is the sweep of **2026-08-07**. It settles six of
> Part I's seven open questions, revises §8 (Eve's docs *did* move), sharpens §3.1 (the harness
> effect is non-monotonic in harness *completeness*, not only in model size), and overturns §1.6's
> conclusion that the name `PACT` is uncontested. **Read Part II's §0-II first.**

**Date of sweep:** 2026-07-26
**Scope:** things the local 141-repo corpus (cloned 2026-07-25) does **not** contain, or where
the web materially contradicts / extends it.
**Method:** WebSearch + WebFetch + `curl`. One repo was cloned because it was absent from the
corpus and is direct competitive prior art (`oracle/agent-spec`, see §1). Papers downloaded to
`/home/bud/ditto/agent-inter-op/research/papers/`.

**Evidence convention used throughout:**
`[V]` = verified by reading source / primary spec text / official docs page.
`[I]` = inference drawn by me from verified facts; labelled as such.
`[S]` = secondary source only (blog/news); flagged and treated as weak.

---

## 0. Executive summary — the seven things that actually change the design

| # | Finding | Where | Design consequence |
|---|---|---|---|
| F1 | **Oracle Agent Spec exists, is at v26.1.2/26.2.0.dev7, has 6 framework adapters, and is not in our corpus.** It is the closest thing to PACT that ships today. | §1 | PACT is no longer first-mover on "declarative framework-agnostic agent spec". Must position on the four axes Oracle *lacks*: filesystem-native form, portable evals, model-capability contracts, learning. |
| F2 | **Oracle Agent Spec's evaluation is NOT part of the portable artifact** (`Metric` is not a `Component`; zero eval types in the serialisation registry) and has exactly **two** built-in metrics. | §1.4 | Confirms T2 is the actual differentiator. Evals-in-the-contract is the moat, not the topology IR. |
| F3 | **At Qwen2.5-1.5B, LangChain (32.81), AutoGen (33.57) and smolagents (27.81) all score *below the raw model* (34.28) averaged over 13 benchmarks.** The sign flips by 32B. | §3.1 | Harness lowering is not neutral. PACT must treat *the harness itself* as a per-tier strategy variable and must CTS-gate harness-vs-raw, not only harness-vs-native. |
| F4 | **MCP `2026-07-28` ships in 2 days: Sampling, Roots, Logging and DCR all deprecated; `initialize` handshake and sessions removed; server-initiated requests replaced by the MRTR `input_required` retry pattern.** | §5 | PACT's tool edge, HITL/elicitation IR, and sandbox-roots model must target MRTR + stateless MCP, not the `2025-11-25` shape in our corpus. |
| F5 | **OpenAI deprecated its Evals platform, Agent Builder and Reusable Prompts on 2026-06-03 (shutdown 2026-11-30) and points Evals users at Promptfoo.** | §2.1 | Three hosted-agent-authoring patterns died at once. Strongest available evidence for D18/NG4 (files are the source of truth) and for config-only evals. Add Promptfoo as eval provider #2. |
| F6 | **Self-evolution security: 17 of 25 MLAS attack-surface cells have no effective defence; gradual blueprint erosion is invisible to per-diff review and requires lineage-level auditing.** | §4.2 | D23's blast-radius classifier operates on the wrong unit. It must also classify **cumulative drift against a frozen baseline**, and safety invariants must be *outside* the optimiser's search space. |
| F7 | **Pydantic AI already ships its own YAML/JSON `AgentSpec` (`Agent.from_file`), and LangGraph's variant mechanism ("Assistants") is hosted-only and explicitly absent from OSS LangGraph.** | §6.1, §6.3 | Native lowering for PyAI target #1 is *spec-to-spec*, not codegen. PACT must own variants because the OSS LangGraph substrate cannot supply them under D17 (air-gapped). |

---

## 1. Oracle "Open Agent Specification" (Agent Spec) — the competitor we did not have

**Status: NOT in the local corpus before this sweep.** I shallow-cloned it to
`/home/bud/ditto/agent-inter-op/research/repos/protocols/oracle-agent-spec` (24 MB).
All line references below are to that checkout.

### 1.1 Provenance and cadence

- Technical report: **arXiv 2510.04173** — <https://arxiv.org/html/2510.04173v3> `[V]`
- Repo: <https://github.com/oracle/agent-spec>; releases page
  <https://github.com/oracle/agent-spec/releases> `[V]`
- Release history `[V]`:

| Version | Date | Content |
|---|---|---|
| `25.4.1` | 2025-10-20 | Initial release: language spec + PyAgentSpec + first adapters |
| `26.1.0` | 2026-01-16 | Sensitive Fields; **Swarm** and **Manager-Workers** patterns; LangGraph + AutoGen adapters; structured generation; tool confirmation; `ParallelFlowNode`/`ParallelMapNode` |
| `26.1.2` | 2026-06-02 | WayFlow, **Microsoft Agent Framework** and **OpenAI Agents SDK** adapters; **Agent Spec Evaluation**; certificate validation and loading policies |
| `26.2.0.dev7` | HEAD as cloned 2026-07-26 (`VERSION`) | dev |

- AGNTCY OASF has added Open Agent Specification support:
  <https://outshift.cisco.com/blog/ai-ml/open-agent-specification-support-and-deployment-data> `[S]`
  (page body was not retrievable through WebFetch; headline only — treat as weak).

### 1.2 The complete serialisable surface

`pyagentspec/src/pyagentspec/_component_registry.py:90-163` — `BUILTIN_CLASS_MAP` is the
authoritative list of serialisable component types. 163 lines total; the map spans 90–163. `[V]`

Categories present:

- **Agentic:** `Agent`, `AgenticComponent`, `A2AAgent`, `OciAgent`, `RemoteAgent`,
  `SpecializedAgent`, `AgentSpecializationParameters`, `Swarm`, `ManagerWorkers`
- **Flow:** `Flow`, `Node`, `ControlFlowEdge`, `DataFlowEdge`
- **Nodes (15):** `agentnode`, `apinode`, `branchingnode`, `catchexceptionnode`, `endnode`,
  `flownode`, `inputmessagenode`, `llmnode`, `mapnode`, `outputmessagenode`,
  `parallelflownode`, `parallelmapnode`, `startnode`, `toolnode`
  (`pyagentspec/src/pyagentspec/flows/nodes/`) `[V]`
- **Tools:** `Tool`, `ToolBox`, `ServerTool`, `ClientTool`, `RemoteTool`, `BuiltinTool`,
  `MCPTool`, `MCPToolBox`, `MCPToolSpec`
- **MCP transports:** `StdioTransport`, `SSETransport`, `SSEmTLSTransport`,
  `StreamableHTTPTransport`, `StreamableHTTPmTLSTransport`, `RemoteTransport`
- **LLM:** `LlmConfig`, `OpenAiConfig`, `OpenAiCompatibleConfig`, `OciGenAiConfig`,
  `OllamaConfig`, `GeminiConfig`, `VllmConfig` (+ auth configs)
- **Datastores:** `Datastore`, `InMemoryCollectionDatastore`, `OracleDatabaseDatastore`,
  `PostgresDatabaseDatastore`
- **Transforms:** `MessageSummarizationTransform`, `ConversationSummarizationTransform`
- **Auth:** `OAuthConfig`, `OAuthClientConfig`

### 1.3 What Agent Spec **cannot** express (negative findings — all `[V]`)

| Missing | Evidence |
|---|---|
| **Any eval / metric / dataset type** | `grep -in "metric\|eval\|dataset" _component_registry.py` → zero hits |
| **Model capability requirements** | `llms/llmconfig.py` — `model_id: str` is required and literal. No capability, benchmark, tier, or predicate field anywhere in `LlmConfig`. |
| **SLOs** (TTFT/TPOT/E2E/cost/throughput) | absent from the registry entirely |
| **Policy / permissions / autonomy** | only `human_in_the_loop: bool` (`agent.py:56`) and per-tool confirmation |
| **Variants / strategy plurality** | closest is `SpecializedAgent` (`specialized_agent.py`), which is *additive only*: `additional_instructions`, `additional_tools`, `human_in_the_loop` override. It cannot express "a different decomposition for a weaker model". |
| **Learning / optimisation** | absent |
| **Filesystem / directory form** | `serialization/serializer.py` and `deserializer.py` expose `to_yaml`/`from_yaml` over a *single document string*. There is no tree loader, no path-as-identity. |
| **Extension escape hatch** | `serialization/deserializationcontext.py:214` — `raise ValueError(f"Unknown Agent Spec Component type {component_type}")`. Unknown types are rejected; there is no `x-` passthrough. (A plugin registry exists for *registered* custom components, which is not the same as round-tripping an unknown extension.) |
| **Executable code in the spec** | arXiv 2510.04173: "specification is limited to a comprehensive description of the tool… but does not contain any executable code" |
| **Topology count** | only **2** first-class topologies (`Swarm`, `ManagerWorkers`) + `MapNode`/`ParallelMapNode` (map-reduce) + `Flow` (pipeline) ≈ 4–5. PACT AC-5.1 targets ≥ 8. |

`Swarm` shape (`swarm.py:77-126`) `[V]`: `first_agent: AgenticComponent`,
`relationships: List[Tuple[AgenticComponent, AgenticComponent]]`,
`handoff: Union[bool, HandoffMode]` (`HandoffMode` enum at `swarm.py:22`).
`ManagerWorkers` shape (`managerworkers.py:20-64`) `[V]`: `group_manager: AgenticComponent`,
`workers: List[AgenticComponent]`.

### 1.4 Evaluation is Python-side, not portable — the key gap

`pyagentspec/src/pyagentspec/evaluation/metrics/metrics.py:25`:

```python
class Metric(ABC, Generic[MetricValueType]):
```

`Metric` inherits `ABC`, **not** `Component`. `grep -rn "Component" metrics/metrics.py
evaluator/evaluator.py` → zero hits. `[V]`

Built-in metric implementations — the entire set `[V]`:

- `metrics/implementations/string_based_metrics.py:15` — `ExactBinaryMatchMetric(Metric[bool])`
- `metrics/implementations/llm_as_a_judge_metrics.py:29` — `SemanticBinaryMatchMetric(LlmAsAJudgeMetric[bool])`

Everything else is user Python via `metrics/decorators.py` / `_function_metric.py`.
Wrappers exist for `ensemble_metric`, `repeat_metric`, `with_intermediate_metric`.

> **Conclusion:** Agent Spec ships a *harness* for evaluation, not an *eval contract*. Two agents
> claimed to be "the same spec" carry no shared correctness oracle. This is precisely the hole T2
> is designed to fill, and it is now empirically the state of the art in a shipping competitor.

### 1.5 Two mechanisms worth stealing

**(a) Per-component minimum-version inference with fail-closed downgrade.**
Every component implements `_infer_min_agentspec_version_from_configuration()` and
`_versioned_model_fields_to_exclude(version)`. Example, `agent.py:66-93` `[V]`:

```python
if agentspec_version < AgentSpecVersionEnum.v26_1_2:
    fields_to_exclude.add("transforms")
...
if self.transforms:
    current_object_min_version = max(current_object_min_version, AgentSpecVersionEnum.v26_1_2)
```

`serialization/serializationcontext.py:288-311` then **raises** rather than silently dropping:

```python
if chosen_version < min_agentspec_version:
    raise ValueError(f"Invalid agentspec_version: received agentspec_version={chosen_version} "
                     f"but the minimum allowed version is {min_agentspec_version} "
                     f"(lower bounded by component '{_min_component.name}')")
```

This is a working, shipped implementation of PACT's `E-2` ("unknown/newer features are rejected
loudly, never ignored") and of `AC-7.1` no-silent-loss on the *version* axis. Note it also
computes a **max** version, so a component can be bounded from both sides.

**(b) Version-pinned "RulePacks" for framework import/export.**
`adapters/openaiagents/flows/_rulepack_registry.py:15-22` `[V]`:

```python
class RulePack(Protocol):
    version: str
    def python_flow_to_ir(self, mod, *, strict: bool = True) -> Any: ...
    def ir_to_agentspec(self, ir, *, strict: bool = True) -> Any: ...
    def agentspec_to_ir(self, flow, *, strict: bool = True) -> Any: ...
    def codegen(self, ir, module_name: str | None = None) -> Any: ...
```

`resolve_rulepack()` reads `agents.version.__version__` from the installed SDK and selects the
matching pack (`_rulepack_registry.py:46-68`). The only pack shipped is `v0_3_3` and it is
**2,560 lines** (`ast_parser.py` 1,224, `codegen.py` 1,013, `__init__.py` 323) for *one version of
one framework*. `[V]`

Error taxonomy (`adapters/openaiagents/flows/errors.py:13-33`) `[V]`:
`FlowConversionError(code, message, details)` with subclasses
`UnsupportedPatternError`, `LossyMappingError`, `RulePackNotFoundError`.

> **Two consequences.** (i) The rulepack pattern is the right answer to R2 (adapter rot) — pin the
> adapter to the *framework SDK version*, not the framework. (ii) 2,560 lines/framework-version is
> the honest cost of D15 "translate or nothing" when the source is code. It also means Oracle
> already has `LossyMappingError` as a *hard error*, not a report — PACT's `ImportReport` +
> `allowLoss` is strictly better ergonomics for the same honesty.

### 1.6 Naming collision hazard `[V]`

At least four distinct things are now called some variant of "Agent Spec":

1. Oracle **Agent Spec** / Open Agent Specification (arXiv 2510.04173).
2. **AgentSPEX**, UIUC, arXiv 2604.13346 — "An Agent SPecification and EXecution Language".
3. **AgentSpec**, arXiv 2503.18666 — "Customizable Runtime Enforcement for Safe and Reliable LLM
   Agents" (a runtime policy DSL, unrelated).
4. `pydantic_ai.agent.AgentSpec` — Pydantic AI's own YAML spec model (§6.1).

Plus three protocols sharing the acronym **ACP** (Agent Client Protocol; Agent Communication
Protocol; and an earlier usage) — <https://blog.marcnuri.com/agent-client-protocol-acp-introduction> `[S]`.
PACT's distinct name is an asset; docs should explicitly disambiguate against (1)–(4).

---

## 2. Standards landscape 2026 — what shipped, what died, what stalled

### 2.1 The OpenAI triple deprecation (2026-06-03) — verified against the official tracker

Source: <https://developers.openai.com/api/docs/deprecations> `[V]`

| Product | Announced | Shutdown | Official migration |
|---|---|---|---|
| **Evals platform** (dashboard + API) | 2026-06-03 | 2026-11-30 (read-only 2026-10-31) | "Moving from OpenAI Evals to **Promptfoo**" |
| **Agent Builder** (visual canvas) | 2026-06-03 | 2026-11-30 | Agents SDK, or ChatGPT Workspace Agents. ChatKit survives. |
| **Reusable Prompts** (`v1/prompts`) | 2026-06-03 | 2026-11-30 | "Integrate prompt content directly into application code" |
| Assistants API | 2025-08-26 | 2026-08-26 | Responses + Conversations API |

This is the cleanest available prior-art autopsy, and it kills three patterns at once:

1. **Visual builder as source of truth** → dead (thesis NG4 confirmed, with a date).
2. **Hosted prompt registry** → dead; OpenAI's own advice is to move prompts *back into the
   repo*. Direct support for D2/D18.
3. **Hosted eval service** → dead; the vendor's own recommended replacement is an **open-source,
   YAML-config-first** evaluator (Promptfoo), which is already in our corpus at
   `research/repos/eval/promptfoo`.

### 2.2 What is alive

- **A2A** v1.0, April 2026, Linux Foundation, 150+ orgs `[S]`. Local corpus has `a2a-spec` at
  HEAD 2026-07-23 — current.
- **MCP** — dominant; see §5 for the imminent breaking revision.
- **AGNTCY / OASF** — Linux Foundation; Directory v1.1.0 / OASF SDK v1.0.3, 75+ companies `[S]`.
  Local corpus has `agntcy-oasf` and `agntcy-dir`.
- **Microsoft Agent Framework 1.0**, GA **2026-04-03**, merging Semantic Kernel + AutoGen `[S]`;
  **AutoGen is in maintenance mode** (bug fixes + critical security patches only).
  Corroborating primary-ish evidence: Oracle ships an `agent_framework` adapter
  (`pyagentspec/src/pyagentspec/adapters/agent_framework/`) `[V]`, i.e. a competitor has already
  retargeted from AutoGen to MAF.

### 2.3 Registry / discovery — a graveyard that validates D24

"State of Agent Discovery Q1 2026" — <https://global-chat.io/discovery-landscape> `[S]`:

- **15+ registries** tracked (Glama 14,274 agents; PulseMCP 11,800; mcp.so 18,695; official MCP
  Registry **87**; Kong, MuleSoft, Solo.io, Microsoft APM, AGNTCY…).
- **11 discovery protocols**: `agents.txt`, A2A, MCP, AWP, ACDP, ANP, `agents.md`, `SKILL.md`,
  ANS, ARDP, MCP Server Cards.
- **10+ competing IETF drafts.** Verified individual drafts `[V]` (datatracker URLs):
  - `draft-rehfeld-apix-core-04` — API Index (APIX)
  - `draft-mozley-aidiscovery-01` — AI Agent Discovery Problem Statement
  - `draft-cui-ai-agent-discovery-invocation-01`
  - `draft-drake-agent-identity-registry-03`
  - `draft-pro-adp-agent-discovery-00`
- **W3C Agent Identity Registry Protocol Community Group**, proposed 2026-04-22
  <https://www.w3.org/community/agent-identity/> `[V]`
- Report's own verdict: *"Zero interoperability… The 'DNS of agents' does not exist yet."*

Nothing here is marked *failed*; the failure mode is **fragmentation without convergence**.
Directly validates **D24**: do not build registry/discovery. Expose an adapter seam and let
AgentZero own it.

### 2.4 Governance timeline (affects when PACT's policy contract must be pluggable)

- **NIST AI Agent Standards Initiative** launched **2026-02-17**; CAISI RFI topic areas: threat
  identification, lifecycle security, cybersecurity framework gaps, security measurement,
  environmental controls. First substantive deliverables **not before late 2026** `[S]`.
- **CSA**: STAR for AI Catastrophic Risk Annex; CNA authorisation via MITRE; acquired the
  *Autonomous Action Runtime Management* spec and *Agentic Trust Framework*; 4-phase rollout
  **June 2026 → December 2027**, public registry entries only in Phase 4 (Jul–Dec 2027) `[S]`.

`[I]` Inference: no external policy/assurance schema will be stable enough to *bind* PACT's policy
contract before late 2027. PACT should define its own policy vocabulary and treat NIST/CSA/EU-AI-Act
mappings as **projections** (like the A2A card and OSSA projections), not as the internal model.

### 2.5 Also-rans found but not load-bearing

- **Open Agent Format (OAF)** v0.8.0, Jan 2026 — <https://openagentformat.com/> (host unreachable
  from this environment; description via search only `[S]`). Single `AGENTS.md` with YAML
  frontmatter + Markdown body, composing skills/packs/weblets/MCP servers/sub-agents. Strictly
  weaker than PACT: no evals, no models, no topology semantics.
- **Open Knowledge Format (OKF)**, Google Cloud, 2026-06-12 — an agent-*memory* interop format `[S]`.
  Worth a later look as a memory-projection target; not a competitor to PACT.

---

## 3. Small models, harnesses and optimisation transfer — the strongest new evidence

### 3.1 EffGen (arXiv 2602.00887, 2026-06-14) — downloaded to `papers/arxiv-2602.00887.pdf`

**Headline finding (Table 2, p.5, extracted verbatim from the PDF) `[V]`** — 13 benchmarks,
Qwen2.5-Instruct, column `Avg`:

| Model | Raw | LangChain | AutoGen | Smolagents | EffGen |
|---|---|---|---|---|---|
| Qwen2.5-1.5B | **34.28** | 32.81 | 33.57 | 27.81 | 47.44 |
| Qwen2.5-3B | 43.62 | 42.55 | 43.65 | 31.56 | 56.80 |
| Qwen2.5-7B | 50.77 | 49.99 | 51.72 | 48.19 | 63.07 |
| Qwen2.5-14B | 54.46 | 55.95 | 59.07 | 54.69 | 66.38 |
| Qwen2.5-32B | 58.32 | 61.03 | 64.99 | 63.85 | 70.97 |

Read the first row again: **at 1.5B, all three mainstream agent frameworks are worse than calling
the model with no framework at all.** The paper states it explicitly: *"47.44% average accuracy
compared to 34.28% for the next best baseline, which at this scale is the raw model itself (it
outperforms all three competing frameworks)"*. The gap closes monotonically: EffGen's advantage
over the best baseline is 13.2% at 1.5B, 13.2% at 3B, 11.4% at 7B, 7.3% at 14B, 6.0% at 32B.

**Second finding, abstract `[V]`:**
> *"prompt optimization and complexity routing have complementary scaling behavior: optimization
> benefits SLMs more (11.2% gain at 1.5B vs 2.4% at 32B), while routing benefits large models more
> (3.6% at 1.5B vs 7.9% at 32B)"*

Other reported mechanisms: prompt compression 57% average (up to 70–80%); task decomposition into
parallel/sequential subtasks by dependency; 5-factor complexity routing; unified short/long/vector
memory. Up to 18× speedup on small models. Conflict-of-interest note: one author at Google
DeepMind, which makes Gemma 3, one of the evaluated families.

Also visible in the extracted table `[V]`: **LongMemEval at 1.5B — raw 22.88, LangChain 15.34.**
Framework-supplied memory management actively destroys long-memory accuracy at small scale.

> **Why this matters more than anything else in this sweep.** PACT's F-4 invariant says "if
> harness lowering underperforms native framework use, that's a defect." This data says the harder
> question is *harness vs. no harness at all*, and that the answer is **model-tier-dependent with a
> sign flip somewhere between 7B and 14B**. A single PACT harness tuned on frontier models will
> plausibly make SLM agents worse. Conversely: harness quality is where 13 points of small-model
> accuracy live, which is a much bigger prize than framework portability.

### 3.2 SkCC (arXiv 2605.03353v4, 2026-06-03) — `papers/arxiv-2605.03353.pdf`

Abstract, verbatim `[V]`:
> *"LLM agents increasingly rely on reusable skills (e.g., SKILL.md)… yet these artifacts lack
> portability: agent frameworks are highly sensitive to prompt formatting, leading to a large
> performance variation for the same skill… S K CC centers on S K IR, a strongly-typed intermediate
> representation that decouples skill semantics from framework-specific formatting… reduces
> adaptation complexity from O(m × n) to O(m + n) across m skills and n frameworks… pass rate
> increases from **21.1% to 33.3% on Claude Code** and from **35.1% to 48.7% on Kimi CLI**…
> sub-10ms compilation latency, 94.8% proactive security trigger rate, and 10–46% runtime token
> savings."*

Repo: <https://github.com/Nexa-Language/Skill-Compiler>; site <https://skcc.nexa-lang.com/>.
Project initiated March 2026; compiler open-sourced 2026-04-03.

> **Consequence.** The industry default — Anthropic-style `SKILL.md`, copied verbatim across
> frameworks (and Eve's "copy the markdown under each `skills/`") — costs **~12–14 percentage
> points of pass rate**. PACT skills must be an IR that is *compiled* per target, not text that is
> *copied*. This is a second, independent argument for harness lowering, on the skill axis. It also
> gives PACT a concrete, measurable CTS metric: same skill, N targets, pass-rate spread.

### 3.3 CAAF (arXiv 2604.17025v3, 2026-05-04) — `papers/arxiv-2604.17025.pdf`

Verbatim from the introduction `[V]`:
> *"even when monolithic GPT-4o is given an explicit semantic hint to 'check for paradox,' it
> achieves only 90% accuracy on a controlled engineering task with known ground truth. When the
> hint is removed—the deployment-realistic condition—accuracy collapses to 0%. This demonstrates
> that apparent LLM reliability in safety-critical domains is often a prompt engineering artifact,
> not an architectural property."*

Three pillars: (1) Recursive Atomic Decomposition with physical context firewalls;
(2) **"Harness as an Asset"** — domain invariants formalised into machine-readable registries
enforced by a deterministic **Unified Assertion Interface (UAI)**; (3) Structured Semantic
Gradients with State Locking for monotonic non-regression.

Its "industrialization thesis" verbatim `[V]`:
> *"once domain invariants are formalized as an executable Harness, the Harness itself becomes a
> first-class enterprise asset that compounds in value as foundation models commoditize, and
> CAAF's ability to deliver its reliability on commodity-tier models makes fully self-hosted,
> on-premises deployment architecturally feasible for regulated sectors where cloud APIs are not
> an option."*

> This is PACT's Contract/Strategy split argued independently, from the safety-critical
> engineering side, with an explicit air-gap/on-prem motivation (D17). It also supplies the
> vocabulary PACT is missing: a **machine-readable invariant registry** + a **deterministic
> assertion interface** sitting *below* the eval suite. Evals are sampled and probabilistic;
> invariants are checked on every run. PACT currently has no such layer.

### 3.4 AgentSPEX (arXiv 2604.13346, 2026-04-14) — `papers/arxiv-2604.13346.pdf`

YAML executable agent spec from UIUC. Five stated features `[V]`:
1. YAML files are the executable specification.
2. **Unified submodule abstraction — "skills and agents are both represented as workflows and can
   be freely composed"**.
3. Explicit conversation-history management: user controls what context each step receives.
4. Agent Harness: tool access, sandboxed venv, checkpointing, trajectory logging, replay/resume.
5. Bidirectional visual editor with synchronised graph and workflow views.

Comparison table (Table 3, p.9) `[V]` — axes: Natural Language / Explicit Context / Visual Editor.
AutoGen ✗✗✗; DSPy ✗✗✗; CrewAI Partial ✗✗; LangGraph+LangFlow ✗✗✓; n8n ✗✗✓; ADL ✓✗✗;
PDL ✓ Partial ✗; AgentSPEX ✓✓✓.

**User study, §4.3 `[V]`:** n=23, Google Forms, AgentSPEX vs LangGraph implementations of the same
behaviour, rated on interpretability and adoption preference. Appendix D: *"Survey participants
generally all had prior programming experience, but had varied levels of experience building
agents."*

> **Negative finding for AC-1.5.** The only published user study on declarative-YAML agent
> authoring recruited **only participants with prior programming experience**. There is no
> published evidence that a non-programmer can author a multi-agent system in YAML. AC-1.5 is
> therefore *novel* — which is both a risk and PACT's most defensible research contribution. It
> also means AC-1.5's moderated session should be designed to be publishable (pre-registered task,
> operational non-programmer screen, control condition).

Also notable: AgentSPEX's **unified submodule abstraction** (skill ≡ agent ≡ workflow) is a
cleaner realisation of PACT's G-5 (construct-agnostic Resources) than anything else found.

### 3.5 Other downloaded, lower-priority

- `papers/arxiv-2512.15943.pdf` — SLMs for agentic tool calling via targeted fine-tuning.
- `papers/arxiv-2603.22386.pdf` — survey: *From Static Templates to Dynamic Runtime Graphs:
  Workflow Optimization for LLM Agents*.
- `papers/arxiv-2512.19769.pdf` — *A Declarative Language for Building And Orchestrating
  LLM-Powered Agent Workflows*.
- `papers/arxiv-2604.08224.pdf` — *Externalization in LLM Agents: A Unified Review of Memory,
  Skills, Protocols and Harness Engineering*.
- `papers/arxiv-2605.19633.pdf` — `optimize_anything`: A Universal API for Optimizing any Text
  Parameter (the GEPA-family universal optimizer ABI — read this before finalising O3.4).
- `papers/arxiv-2503.18666.pdf` — AgentSpec: customizable **runtime enforcement** DSL.
- `papers/arxiv-2602.17753.pdf` — *The 2025 AI Agent Index*: technical and safety features of
  deployed agentic systems.
- `papers/arxiv-2606.29537.pdf` — OSWorld 2.0 (see §7).
- `papers/arxiv-2607.07663.pdf`, `papers/arxiv-2602.05848.pdf` — recursive self-improvement survey;
  DARWIN.

GEPA itself: accepted at **ICLR 2026 (Oral)**, arXiv 2507.19457 `[S]` — outperforms GRPO by up to
20% with 35× fewer rollouts. This matches the in-repo SYNTHESIS figure; now has a venue.

---

## 4. Agent self-improvement safety — the finding that breaks D23 as currently specified

### 4.1 Source

*Safety in Self-Evolving LLM Agent Systems: Threats, Amplification, and Case Studies*,
arXiv **2606.23075v1**, 2026-06-22 (Zhejiang Univ. / Ant Group / Tsinghua / NTU / Fudan).
`papers/arxiv-2606.23075.pdf`, text dump at `papers/selfevo.txt`.

### 4.2 The MLAS matrix `[V]`

5 functional modules × 5 lifecycle stages = 25 cells:

- Modules: **Brain, Cognitive Resource, Execution, Self-Design, Collective**
- Stages: **Bootstrap, Propose, Evaluate, Commit, Serve**

Result: *"17 face critical threats for which no effective defense exists, 7 face high threats where
current defenses are insufficient, and only 1 admits partial mitigation, with the Self-Design
module uniformly critical due to the optimizer–optimizee collapse."*

Seven amplification effects: **generational accumulation, selective amplification, deceptive
evolution, Lamarckian propagation, capability ratchet, emergent unpredictability,
optimizer–optimizee collapse.**

Case study: OpenClaw (evolution-augmented) vs Hermes (evolution-native). Evolution-native design
*"activates 3.5× more attack surface cells and achieves a 100% attack persistence rate (40/40
payloads across all CIA+Privacy categories), while the co-located security scanner blocks only 2.5%
of attacks on the evolution pathway."* Hermes' scanner blocks 5/8 payloads on the normal path and
0 on the evolution path.

### 4.3 The two findings that hit PACT directly

**(a) Gradual blueprint erosion defeats per-diff review** (§6.4, `selfevo.txt:1710-1735`) `[V]`:

> *"Each generation may weaken a safety module by an amount that falls within any single-generation
> tolerance threshold; across ten generations the cumulative effect can constitute complete
> safety-module failure. This is the boiling-frog problem applied to architecture: no single
> transition is anomalous, but the trajectory is… A safety audit comparing generation t to
> generation t−1 will see nothing; the same audit comparing generation t to generation t−10 may
> find that no recognizable safety mechanism remains. Architectural drift therefore evades the
> entire family of point-in-time security audits, and demands evaluation methodology operating on
> the lineage rather than the individual."*

**D23 as written classifies a single spec diff.** It is exactly the audit this paragraph says is
blind. A run of ten "wording/formatting" auto-applied changes can dissolve a refusal policy while
every individual change classifies as low-risk.

**(b) Optimizer–optimizee collapse** (§6, `selfevo.txt:1563-1575`) `[V]`:

> *"The first is self-referentiality… A_t is itself a component of W_t, so the operator that
> performs evolution is itself subject to evolution. The second is structural mutability: any
> safety mechanism implemented as an architectural component (a guardrail node in the workflow
> graph, a verifier protocol, a sandboxed execution wrapper) is itself an optimizable target rather
> than a fixed substrate."*

And: *"Schmidhuber's formal-verification firewall has been replaced by a fitness function, an
artifact long known to admit specification gaming."* Under D22(c) — agents may learn their own
structure and topology — PACT's eval suite **is** that fitness function, and PACT's guardrails,
policies and eval cases are all spec files inside the same tree the optimizer edits.

Also relevant: *"Observation 5.3: Tool evolution exhibits a capability ratchet: capabilities are
monotonically increasing, effectively irreversible, and compound through composition. Once a
malicious tool passes Select and enters the persistent library, it propagates across the entire
evolutionary lineage without any natural mechanism for removal or deprecation."* — direct hit on
D22(b), self-authored tools. Neither case-study framework *"supports capability revocation or
version-controlled rollback"* (`selfevo.txt:2599`).

### 4.4 The paper's four defence principles `[V]` (`selfevo.txt:2784-2800`)

1. **Evolution-aware monitoring** — track safety properties across generations; longitudinal
   monitoring replaces point-in-time evaluation.
2. **Immutable safety invariants** — *"architecturally protected from evolutionary modification by
   implementing them outside the scope of the optimization process, analogous to hardware-enforced
   memory protection in operating systems."*
3. **Multi-generational audit trails** — every mutation/selection/reproduction produces a
   verifiable record enabling post-hoc attribution.
4. **Attack-surface-matched defence** — cover all injection channels simultaneously; partial
   coverage is routed around.

`[I]` My reading of the delta for PACT: PACT is unusually well placed on (3) — T6 already requires
learning to emit reviewable, signed source, which *is* a multi-generational audit trail if lineage
is recorded. PACT is weak on (1) and (2), and D22 makes (4) hard because self-authored tools open a
channel the rest of the system does not guard.

---

## 5. MCP `2026-07-28` — a breaking revision landing in two days

The local `research/repos/protocols/mcp-spec` (HEAD 2026-07-23) contains
`docs/specification/draft/` which **is** the `2026-07-28` revision. Blog corroboration:
<https://workos.com/blog/mcp-2026-spec-agent-authentication> `[S]`; everything below is read from
the local draft spec text `[V]`.

### 5.1 Deprecations (`docs/specification/draft/deprecated.mdx`) `[V]`

| Feature | SEP | Deprecated in | Migration | Earliest removal |
|---|---|---|---|---|
| **Roots** | SEP-2577 | `2026-07-28` | pass dirs/files via tool params, resource URIs, or server config | first revision on/after 2027-07-28 |
| **Sampling** | SEP-2577 | `2026-07-28` | integrate directly with LLM provider APIs | 2027-07-28+ |
| **Logging** | SEP-2577 | `2026-07-28` | `stderr` (stdio) or OpenTelemetry | 2027-07-28+ |
| **Dynamic Client Registration** | PR #2858 | `2026-07-28` | Client ID Metadata Documents (CIMD) | 2027-07-28+ |
| `includeContext: thisServer/allServers` | SEP-2596 | `2025-11-25` | omit or `"none"` | follows Sampling |
| HTTP+SSE transport | SEP-2596 | `2025-03-26` | Streamable HTTP | 3 months after SEP-2596 Final |

### 5.2 Major changes (`docs/specification/draft/changelog.mdx`) `[V]`

1. Protocol-level sessions and `Mcp-Session-Id` removed (SEP-2567). List endpoints no longer vary
   per connection. Cross-call state uses *"explicit, server-minted handles passed as ordinary tool
   arguments."*
2. **`initialize`/`notifications/initialized` handshake removed** (SEP-2575). Protocol version and
   client capabilities travel in `_meta` on every request
   (`io.modelcontextprotocol/protocolVersion`, `…/clientCapabilities`, `…/clientInfo`,
   `…/serverInfo`). Mismatch → `UnsupportedProtocolVersionError`.
3. `server/discover` RPC — servers **MUST** implement; advertises supported protocol versions,
   capabilities and identity.
4. `subscriptions/listen` replaces the HTTP GET endpoint and `resources/subscribe|unsubscribe`.
5. `ping`, `logging/setLevel`, `notifications/roots/list_changed` removed. Log level per-request
   via `io.modelcontextprotocol/logLevel` in `_meta`.
6. Tasks moved out of core into official extension `io.modelcontextprotocol/tasks`; polling via
   `tasks/get`, client input via `tasks/update`; `tasks/list` removed. **Breaking** for anyone on
   the `2025-11-25` experimental Tasks API.
7. **MRTR — Multi Round-Trip Requests** (SEP-2322). See §5.3.
8. All results carry required `resultType`: `"complete"` or `"input_required"`.
9. SSE resumability and `Last-Event-ID` redelivery removed. *"A broken response stream loses the
   in-flight request; clients MUST re-issue it as a new request with a new request ID."*

Minor changes worth noting `[V]`:
- `extensions` field added to `ClientCapabilities`/`ServerCapabilities`; formal extensions with
  reverse-DNS identifiers and independent versioning.
- OTel trace-context conventions for `_meta` (`traceparent`, `tracestate`, `baggage`) — SEP-414.
- Servers **SHOULD** return `tools/list` in deterministic order *"to enable client-side caching and
  improve LLM prompt cache hit rates."*
- New `CacheableResult` interface: `ttlMs` freshness hint + `cacheScope` (`"public"`/`"private"`)
  required on `tools/list`, `prompts/list`, `resources/list`, `resources/read`,
  `resources/templates/list` (SEP-2549).
- `inputSchema`/`outputSchema` loosened to **full JSON Schema 2020-12** with `$ref` resolution
  requirements and composition-keyword resource bounds (SEP-2106).
- Error-code allocation policy: `-32000..-32019` implementation-defined (grandfathered),
  `-32020..-32099` reserved for the MCP spec.

### 5.3 MRTR — the new HITL/elicitation shape (`basic/patterns/mrtr.mdx`) `[V]`

> *"Servers **MUST** send server-to-client requests (such as `roots/list`,
> `sampling/createMessage`, or `elicitation/create`) using the MRTR pattern. The previous pattern
> of server-initiated requests is no longer supported. This is a breaking change."*

Flow: client request → server returns `InputRequiredResult` (`resultType: "input_required"`) whose
`inputRequests` map (server-assigned keys → `ElicitRequest` / `CreateMessageRequest` /
`ListRootsRequest`) states what it needs → client gathers input → client **retries the original
request** with `inputResponses` → server returns final result.

Design intent, verbatim: *"without requiring a shared storage layer across server instances or
requiring stateful load balancing."*

`notifications/elicitation/complete` and `elicitationId` (both from `2025-11-25`) are removed;
servers that must correlate across retries *"encode their own identifier in `requestState`."*

> **Consequence for PACT.** MRTR is a *retry-with-accumulated-answers* protocol. That maps almost
> exactly onto PACT's P-5 (state/resume/cancellation as IR concepts) and gives PACT a ready-made,
> standards-blessed wire shape for approval gates and human input — one that is stateless and
> therefore works under durable execution, serverless, and air-gapped local runs identically.
> PACT's HITL IR should be *isomorphic to MRTR*, and adapters that lack it should emulate it.

### 5.4 Governance model worth copying `[V]`

The `2026-07-28` revision introduces a **feature lifecycle and deprecation policy** (SEP-2596)
with: a Deprecated state; an **earliest-removal** date (typically "first revision released on or
after +12 months"); a **derived registry page** (`deprecated.mdx`) that is explicitly *"a derived
view kept consistent with the per-feature deprecation notices and changelog entries, which are the
normative records"*; and a `## Removed` section that stays empty until something is actually
removed.

That is a complete, working answer to PACT's R8 (spec sprawl) and E-2, and it is battle-tested at
MCP's adoption scale.

---

## 6. Framework docs — features not (or barely) visible from the cloned source

### 6.1 Pydantic AI already has a declarative YAML agent spec `[V]`

Docs moved: `https://ai.pydantic.dev/` now 301s to `https://pydantic.dev/docs/ai/overview/`.
The feature is documented at `docs/agent-spec.md` in the local checkout (HEAD `ed0f40c`,
2026-07-25), which I read in full — 188 lines.

API: `Agent.from_file(path)`, `Agent.from_spec(dict|AgentSpec, **kwargs)`,
`AgentSpec.from_file`, `AgentSpec.to_file(path)` (also emits `agent_schema.json` for
YAML-language-server autocompletion).

`AgentSpec` fields, verbatim from the doc's reference table `[V]`:
`model` (str, **required**), `name`, `description`, `instructions` (str | list[str]),
`model_settings`, `capabilities` (list), `deps_schema` (JSON Schema),
`output_schema` (JSON Schema), `retries` (int | `AgentRetries`),
`end_strategy` (`'early'|'graceful'|'exhaustive'`), `tool_timeout`, `instrument`, `metadata`.

Merge semantics for `from_spec` kwargs `[V]`: scalars override; `instructions` merged (spec first);
`capabilities` merged (spec first); `model_settings` merged additively with kwargs winning;
`output_type` beats `output_schema`.

Templating: Handlebars-style `{{var}}` (`TemplateStr`), resolved against `deps`; strings containing
`{{` are auto-converted; validated against `deps_type`/`deps_schema` at construction.

Documented limitation, verbatim `[V]`:
> *"The model's response is not validated against the schema's `properties` or `required` fields —
> it is accepted as a plain dict. The schema serves as an instruction to the model, not a runtime
> validation constraint."*

What it cannot express `[V]`: no multi-agent/topology; no tools slot beyond the `capabilities`
plugin list; no evals; no SLOs; no policies; no variants; `model` is a literal required string with
no capability predicate; single file only, no directory form.

> **Consequences.** (1) PACT's *primary* adapter target already speaks YAML — native lowering for
> single agents is **spec-to-spec translation**, not codegen, which is far cheaper and far more
> reviewable than Oracle's 2,560-line rulepack approach. (2) PACT must be a demonstrable superset
> of this field list (add it to the D3 superset conformance corpus alongside `bud.dev/v1`).
> (3) `capabilities` is Pydantic AI's plugin ABI and is the seam through which PACT-specific
> constructs can be lowered natively.

Other Pydantic AI doc surfaces in the checkout that the online overview flags as first-class
and that deserve their own reading: `gateway.md`, `hooks.md`, `deferred-tools.md`,
`native-tools.md`, `extensibility.md`, `coding-agent-skills.md`, `durable_execution/`, `evals/`,
`ui/`, `capabilities/`. The overview page also names a **"Pydantic AI Harness"** — *"a capability
library featuring code execution, file access, and guardrails"* `[V, weak — overview prose]`.

### 6.2 AutoGen is in maintenance mode `[S, corroborated]`

Microsoft Agent Framework 1.0 GA'd **2026-04-03**, merging Semantic Kernel and AutoGen; RC was
2026-02-19. Microsoft positions MAF as *"the direct successor"* to both. AutoGen receives bug fixes
and critical security patches only.

Corroboration that is not a blog: Oracle ships `adapters/agent_framework/` alongside
`adapters/autogen/` as of 26.1.2 `[V]`.

> **Consequence.** PACT's G1 target list (which names AutoGen) is aiming at a frozen framework.
> Either retarget slot 4 to Microsoft Agent Framework, or keep AutoGen purely as an *import*
> on-ramp (D10.3 migration tool) and put export effort into MAF.

### 6.3 LangGraph "Assistants" are hosted-only `[V]`

<https://docs.langchain.com/langsmith/assistants>, verbatim:
> *"Assistants are a LangSmith Deployment concept. They are not available in the open source
> LangGraph library."*

Semantics: an assistant is a graph + a named configuration (prompt, model, tools, runtime params).
Every PATCH creates a new **version**; any version can be promoted; rollback = activate an older
version; A/B testing is supported. Caveat documented: updates require the **complete configuration
payload** — versions are created from scratch, not merged.

> **Consequence.** The one construct in the LangGraph ecosystem that matches PACT's `variants:` is
> unavailable offline, and D17 mandates air-gapped operation. PACT must own variant identity and
> versioning itself and lower variants into *distinct compiled graphs* on the OSS LangGraph
> substrate. Do **not** design the LangGraph adapter around Assistants. Conversely, "assistant =
> graph + config, versioned with promote/rollback" is a good shape to copy for `pact.lock`.

### 6.4 Claude Agent SDK `[S]`

Renamed from Claude Code SDK, Sept 2025. Skills are `SKILL.md` under `.claude/skills/`,
auto-discovered at startup, selected by the model, invoked through a `Skill` tool. **Plugins** are
self-contained directories bundling skills + subagents + hooks + MCP servers, and they *namespace*
their skills; `setting_sources` controls discovery from the settings hierarchy.

`[I]` The plugin/namespacing model is the closest existing analogue to a PACT "resource pack" and
is worth mirroring for D24's adapter-shaped registry seam: a signed directory that contributes
multiple resource kinds under one namespace.

### 6.5 OpenAI Agents SDK `[S]`

Hosted tools that run on OpenAI servers: web search, file search, code interpreter, image
generation, **tool search**. Realtime/voice agents on `gpt-realtime-2.1` with automatic
interruption detection, context management and guardrails. Computer use is *local only* —
you implement the `Computer` interface and pass it to `computerTool()`. An April 15 2026 overhaul
*"made MCP first-class and turned sub-agent handoffs into a runtime primitive."*

> `[I]` "Tool search" as a hosted primitive is independent corroboration of the in-repo finding
> that hierarchical/curated tool exposure beats a flat tool list. PACT's tool-exposure strategy
> field should have a `search` mode that can lower to this natively.

### 6.6 DeepEval: the docs are **behind** the source, and there is no config-only mode `[V]`

The assignment asked for doc features missing from source. The reverse is true.

Local `research/repos/eval/deepeval` HEAD `6cf2e02`, 2026-07-22. `deepeval/metrics/` contains
directories with **no counterpart in the docs metric index** at
<https://deepeval.com/docs/metrics-introduction>:
`agent_loop_detection`, `arena_g_eval`, `conversational_dag`, `exact_match`, `goal_accuracy`,
`mcp`, `mcp_use_metric`, `pattern_match`, `prompt_alignment`, `tool_permission`, `tool_use`,
`topic_adherence`, `turn_contextual_precision`, `turn_contextual_recall`,
`turn_contextual_relevancy`, `turn_faithfulness`, `turn_relevancy`.

Top-level modules present in source: `benchmarks`, `red_teaming`, `simulator`, `synthesizer`,
`optimizer`, `tracing`, `inspect`, `annotation`, `confident`, `guardrails`-adjacent
(`red_teaming`), `openai_agents`, `integrations`, `plugins`, `prompt`, `config`.

Config-only: <https://deepeval.com/docs/getting-started> `[V]` — *"The documentation does not
mention support for YAML or configuration-file-based evaluation without Python code. All quickstart
examples use Python test files."* CLI is `deepeval test run` over pytest files
(`deepeval/cli/` contains `auth`, `diagnose`, `generate`, `inspect`, `test`, `main`, `types`, and a
`dotenv_handler`; no YAML runner).

> **Consequences.** (a) O4.1's coverage matrix must be built from **the source tree**, not the docs
> site; the docs undercount by ~17 metric families. (b) There is no shortcut to D14/G4: the entire
> config→DeepEval binding layer is PACT's to build. (c) `deepeval/optimizer` and
> `deepeval/simulator` are unexpected and should be read before finalising O3.4 and D19.3
> (captured-from-usage on-ramp).

---

## 7. Modality reality check (D16)

**OSWorld 2.0**, arXiv **2606.29537**, dated **2026-07-15** on the PDF —
`papers/arxiv-2606.29537.pdf`, abstract verbatim `[V]`:

> *"108 long-horizon computer-use workflows… Each task represents a realistic end-to-end workflow
> that takes human users a median of about 1.6 hours to complete and requires an average of **318
> tool calls** with Claude Opus 4.7 using maximum thinking, compared with about 30 in OSWorld 1.0…
> Under our primary binary-completion metric at 500 steps, Claude Opus 4.8 with maximum thinking
> and batched tool calls scores best but still completes only **20.6% of tasks at a 54.8% partial
> score**; GPT-5.5 is far more token-efficient yet plateaus near **13%**… rather than stumbling on
> basic GUI control or coding, they lose track of constraints, miss information that arrives
> mid-task, **guess rather than ask the user**, and **skip verification**, struggling most when a
> task hinges on hidden state they must recover."*

Tasks *"include separate safety reports auditing safety-sensitive execution."*

> **Consequences for D16.** (1) A computer-use contract whose pass threshold is written like a
> text-agent's will be unsatisfiable — frontier is ~20%. (2) The named failure modes are precisely
> the ones a *declarative loop* fixes: "loses track of constraints" → invariant registry (§3.3);
> "guesses rather than asks" → mandatory elicitation step via MRTR (§5.3); "skips verification" →
> declarative verify node in the loop IR. This is the strongest available argument that G-3
> (loop-as-data) earns its complexity. (3) SLO vocabulary must accommodate step budgets in the
> hundreds and cost-per-task, not just TTFT/E2E. (4) Modality-specific *safety reports* are an
> established benchmark artifact; PACT's Portability Report should carry a computer-use safety
> section.

---

## 8. Vercel Eve — nothing newer online than in the corpus `[V]` (negative finding)

`research/repos/frameworks/vercel-eve` HEAD `05f3480`, 2026-07-25 ("Version Packages (#1176)").

I scraped every `/docs/*` link from `https://eve.dev/docs/introduction` (78 paths) and compared
against `docs/**/*.{md,mdx}` in the checkout (78 files). **The sets match 1:1.** Spot-fetched
`https://eve.dev/docs/reference/project-layout` and `https://eve.dev/docs/evals/overview` and
compared with the local files: same slot table, same API names. **Conclusion: eve.dev/docs
contains nothing the corpus lacks. Do not spend further web budget here.**

Two claims in `00-THESIS.md` §0 now have exact citations from `docs/reference/project-layout.md`:

- Fixed slot table, closed set — the table lists exactly: `agent.ts`, `instructions.md|ts|/`,
  `instrumentation.ts`, `channels/`, `connections/`, `hooks/`, `skills/`, `lib/`,
  `sandbox.ts | sandbox/sandbox.ts`, `sandbox/workspace/**`, `tools/`, `schedules/`, `subagents/`.
  Root-only: `instrumentation.ts`, `channels/`, `schedules/`. No user-defined slots documented.
- No inheritance — verbatim: *"A declared subagent inherits nothing from the root; it discovers its
  own slots."*
- Identity is path-derived: *"Identity comes from the path. You never write a `name` or `id` field
  on a `define*` call."* Root name comes from `package.json` `name`, falling back to the app-root
  directory name.
- Evals are code: `evals/` sits **beside** `agent/`, files are `.eval.ts` using `defineEval()`,
  with exactly one `evals.config.ts` per `evals/` root via `defineEvalConfig()`. Three assertion
  surfaces: scoped methods on `t`; deterministic `t.check()` with matchers from `eve/evals/expect`;
  LLM-judge via `t.judge.autoevals.*`. Eval ID is derived from path
  (`evals/weather/brooklyn-forecast.eval.ts` → `weather/brooklyn-forecast`).

`[I]` Eve's eval-ID-from-path is worth adopting: it makes eval identity stable across renames of
the underlying prose and gives trace-promotion a natural landing slot.

---

## 9. What I looked for and did **not** find (negative results)

1. **No 2026 agent-portability standard that carries evals.** Oracle Agent Spec, AgentSPEX, OAF,
   OASF, A2A, ACP — none makes the correctness oracle part of the portable artifact. PACT's T2 is
   unclaimed territory as of 2026-07-26.
2. **No standard with model-capability requirements.** Every format binds a literal model id.
   No competitor has anything resembling O3.1's predicate language.
3. **No published evidence that non-programmers can author agents declaratively.** The only user
   study (AgentSPEX, n=23) recruited programmers. AC-1.5 is novel.
4. **No "universal agent format" postmortem to autopsy.** The 2026 failures are *hosted-product*
   failures (OpenAI Evals / Agent Builder / Prompts), not format failures. The format-level failure
   mode is fragmentation-without-adoption (15+ registries, 11 protocols, 10+ IETF drafts, "zero
   interoperability"), not repudiation.
5. **No conformance test suite exists for any agent spec.** Oracle lists one under *upcoming
   features* in arXiv 2510.04173. PACT's CTS (O2.4) would be first.
6. **No filesystem-native portable spec.** Eve is filesystem-native but single-framework and
   TS-only; Oracle/AgentSPEX are document-native. The combination — filesystem-native **and**
   multi-framework — is unoccupied.
7. **eve.dev/docs has nothing newer than the corpus** (§8).
8. **DeepEval's docs have nothing the source lacks**; the source has ~17 metric families the docs
   omit (§6.6).

---

## 10. Open questions this sweep could not settle

1. Did AGNTCY's OASF adoption of Oracle Agent Spec change OASF's schema, and is OASF now a
   *packaging* wrapper around a *behavioural* spec? (The Outshift blog body was unretrievable; the
   local `agntcy-oasf` clone predates or postdates it — needs a diff against the OASF release
   notes.)
2. What exactly is the "Pydantic AI Harness" capability library, and does it overlap PACT's loop
   ownership (D12)? Only the overview prose was retrievable.
3. Does Microsoft Agent Framework 1.0 have a declarative/YAML agent surface? If it does, PACT has a
   second spec-to-spec native-lowering target and G1's slot 4 should be retargeted immediately.
4. Does the MCP `io.modelcontextprotocol/tasks` extension subsume PACT's durable-execution needs,
   or is it strictly weaker than Temporal/Workflow SDK semantics (P-5)?
5. Does `deepeval/optimizer` implement a GEPA-class loop, and if so does it satisfy the O3.5
   frozen-held-out protocol? Needs a source read.
6. Is there any published measurement of *harness-vs-raw* on a frontier model for the PACT loop
   patterns (ReAct, Plan-Execute, …)? EffGen measures frameworks, not loops.
7. `optimize_anything` (arXiv 2605.19633) claims a universal text-parameter optimisation API.
   Does its interface already satisfy PACT's E-5 optimizer ABI, and should PACT adopt it verbatim
   rather than inventing one?

---

## Appendix A — files added by this sweep

Repo (cloned because absent from corpus):
- `/home/bud/ditto/agent-inter-op/research/repos/protocols/oracle-agent-spec` (24 MB, `VERSION` = `26.2.0.dev7`)

Papers (`/home/bud/ditto/agent-inter-op/research/papers/`):
- `arxiv-2602.00887.pdf` — EffGen: Enabling SLMs as Capable Autonomous Agents
- `arxiv-2605.03353.pdf` — SkCC: Portable and Secure Skill Compilation for Cross-Framework LLM Agents
- `arxiv-2604.17025.pdf` — CAAF: Harness as an Asset
- `arxiv-2604.13346.pdf` — AgentSPEX
- `arxiv-2606.23075.pdf` — Safety in Self-Evolving LLM Agent Systems (+ `selfevo.txt` dump)
- `arxiv-2606.29537.pdf` — OSWorld 2.0
- `arxiv-2607.07663.pdf` — Recursive Self-Improvement in AI
- `arxiv-2602.05848.pdf` — DARWIN
- `arxiv-2512.15943.pdf` — SLMs for Efficient Agentic Tool Calling
- `arxiv-2512.19769.pdf` — A Declarative Language for LLM-Powered Agent Workflows
- `arxiv-2603.22386.pdf` — Static Templates → Dynamic Runtime Graphs (workflow-optimisation survey)
- `arxiv-2604.08224.pdf` — Externalization in LLM Agents (memory/skills/protocols/harness review)
- `arxiv-2605.19633.pdf` — optimize_anything
- `arxiv-2503.18666.pdf` — AgentSpec: runtime enforcement DSL
- `arxiv-2602.17753.pdf` — The 2025 AI Agent Index
- `agentspex.txt` — text dump of 2604.13346

## Appendix B — primary URLs cited

- <https://developers.openai.com/api/docs/deprecations>
- <https://docs.langchain.com/langsmith/assistants>
- <https://github.com/oracle/agent-spec/releases>
- <https://arxiv.org/html/2510.04173v3>
- <https://oracle.github.io/agent-spec/development/agentspec/index.html>
- <https://eve.dev/docs/introduction>, <https://eve.dev/docs/reference/project-layout>, <https://eve.dev/docs/evals/overview>
- <https://deepeval.com/docs/metrics-introduction>, <https://deepeval.com/docs/getting-started>
- <https://pydantic.dev/docs/ai/overview/> (301 from <https://ai.pydantic.dev/>)
- <https://www.w3.org/community/agent-identity/>
- <https://datatracker.ietf.org/doc/draft-rehfeld-apix-core/04/>, <https://datatracker.ietf.org/doc/draft-mozley-aidiscovery/>, <https://datatracker.ietf.org/doc/draft-cui-ai-agent-discovery-invocation/01/>, <https://datatracker.ietf.org/doc/draft-drake-agent-identity-registry/03/>
- <https://global-chat.io/discovery-landscape>
- <https://arxiv.org/abs/2602.00887>, <https://arxiv.org/abs/2605.03353>, <https://arxiv.org/abs/2606.29537>, <https://arxiv.org/pdf/2606.23075>, <https://arxiv.org/pdf/2604.17025>, <https://arxiv.org/pdf/2604.13346>
- <https://github.com/Nexa-Language/Skill-Compiler>
- <https://workos.com/blog/mcp-2026-spec-agent-authentication> (secondary; superseded by the local draft spec)

---
---

# PART II — Sweep 2

**Date of sweep:** 2026-08-07 (12 days after the corpus clone of 2026-07-25, 12 days after Sweep 1).
**Scope:** (a) settle the seven open questions of §10; (b) find what shipped or was published
*after* 2026-07-26; (c) the assignment's untouched targets — failed spec efforts, LF/W3C/IETF/CSA
work, framework hosted/beta features, DeepEval docs, Eve docs re-check.
**Everything in Part I is preserved verbatim** — `00-THESIS.md` §3.1 and the notes `README.md`
cite it by section number. Part II uses §11 onward.

**Same evidence convention:** `[V]` verified against source / primary spec / official docs /
the PDF itself · `[I]` my inference, labelled · `[S]` secondary source only.

---

## 10-RESOLVED — status of Sweep 1's open questions

| # | Question | Status | Where |
|---|---|---|---|
| OQ1 | Did OASF's Agent Spec adoption change the schema? Is OASF now a packaging wrapper around a behavioural spec? | **RESOLVED** — answered from the local `agntcy-oasf` checkout, not the unreachable blog. OASF has *both* an `agentspec` integration module and an `evaluation` core module. Neither carries behaviour. | §13 |
| OQ2 | What is the "Pydantic AI Harness"? Does it overlap D12? | **RESOLVED** — it is a real 24+-capability library, `pydantic_ai_harness`. It explicitly does **not** own the loop. No D12 conflict; it is the native-lowering surface. | §15 |
| OQ3 | Does Microsoft Agent Framework have a declarative/YAML agent surface? | **RESOLVED — yes, two of them**, and they are the strongest competitor found to date on *authoring*, and the weakest on *portability*. | §12 |
| OQ4 | Does MCP `tasks` subsume PACT's durable-execution needs? | **PARTIALLY** — Tasks shipped as an *extension*, not core, in the final `2026-07-28`. Still weaker than Temporal-class semantics. | §18.1 |
| OQ5 | Does `deepeval/optimizer` implement a GEPA-class loop? Does it satisfy O3.5? | **RESOLVED — yes to GEPA, emphatically no to O3.5.** Four verified defects. | §14 |
| OQ6 | Any published *harness-vs-raw* measurement for loop patterns? | **RESOLVED — yes, two**, and the result is worse than EffGen implied: the effect is **non-monotonic in harness completeness**, not only in model size. | §11.1, §11.2 |
| OQ7 | Should PACT adopt `optimize_anything` as its optimizer ABI? | **NOT SETTLED** — but a shipping alternative ABI was found in DeepEval and is *narrower* than PACT needs (prompts only). See §14.4. | §14 |

---

## 0-II. Executive summary — Sweep 2

| # | Finding | Where | Design consequence |
|---|---|---|---|
| **F8** | **The strongest independent validation of T4 yet published, with honest limits.** CMU, 2026-07-09: SLM agents match frontier at **90% lower cost** — but only 16/21 task-SLM pairs improved, only **7/21 closed the gap**, the best case recovers **89.4%** (not ≥95%), and an 8B model recovered **27.9%** with three tasks stuck at 0.0 → 0.0. Adaptation quality is governed by **task diversity, Spearman ρ = −0.96**. | §11.1 | AC-3.1's ≥95% bar is **not met by the best measurement in the literature**. Add a pre-flight **workflow-diversity predicate** computed offline from the eval set, and a **base-capability floor** below which the resolver refuses to spend optimiser budget. |
| **F9** | **Harness benefit is non-monotonic in harness *completeness*, not just model size.** At 2–3B, a *minimal* harness scores **below the raw model** in 2 of 3 models; the full `plan→execute→verify→recover` pipeline reaches TSR 0.952 / VTSR 1.000. Planning and recovery each contribute ~24.7% of the gain. "Scaffold collapse": LLaMA-3.2-3B raw abandons JSON under complex format demands (TSR 0.429, 7 violations). | §11.2 | **PACT must not ship a "light" harness mode.** `verify` and `recover` become *required* loop-node kinds whenever harness lowering is active on a small tier, and the CTS harness-vs-raw gate must also test the *partial* configuration. |
| **F10** | **Microsoft Agent Framework ships two declarative YAML surfaces** (`kind: Prompt` agents; `kind: Workflow` action lists) with ~28 action kinds, PowerFx expressions, HITL, MCP and HTTP actions. But: **the C# and Python YAML dialects are different languages** (trigger-based vs name-based; 4 actions C#-only), agent invocation is hard-bound to **Microsoft Foundry**, and there is a `GotoAction`. | §12 | The no-code competitor is real. PACT's differentiators narrow to: offline execution, evals-in-the-artifact, capability contracts, variants, learning, one dialect. **Add MAF YAML to the D3 superset conformance corpus.** Never introduce `goto`. |
| **F11** | **OASF's `evaluation` module is a *results record*, not an eval contract** — `overall_rating`, `quality/cost/security` scores, `publisher`, `created_at`, dataset **URLs**. No metric definition, no threshold, no rubric, no judge. And `agentspec_data.runtime_deps` is documented as *"locators for the **non-serializable** objects the Agent Spec config depends on (e.g. tool implementations)"*. | §13 | The competitor's own integration schema **admits in writing that its agent specs are not self-contained**. This is the single best citation for T2 and D15. It also means "OASF has evaluation" is not a counter-claim to T2 — quote the field list. |
| **F12** | **DeepEval ships GEPA/MIPROv2/COPRO/SIMBA — with four defects PACT would inherit.** Default Pareto **validation set = 3 examples**; **two-way split only, no test set**; `random_seed` defaults to `time.time_ns()` so **the split is non-reproducible**; and `reflection_model="gpt-4o-mini"`, `mutation_model="gpt-4o"` are **hardcoded hosted-OpenAI defaults**, with the *reflector* defaulting to the *smaller* model. | §14 | PACT must own the split protocol (O3.5) and the optimiser-model binding (AC-3.1b) — do **not** delegate either to the provider. Both are now demonstrated failures in shipping code, not hypotheticals. |
| **F13** | **Self-improving optimisers fabricate the failures they fix.** CMU, 2026-07-13: in **15/60** runs the proposer enabled a guardrail for a rule that provably never fires and cited a violation a byte-exact oracle refutes (**0/60** on featureless input). Root cause: the reward is *suppression of observed failures*, which answers "did the failure stop?" and never "was the fix warranted?" — in an **add-only** regime where nothing is removed. | §16.1 | PACT's held-out-improvement gate **cannot catch this**: an unwarranted guardrail does not lower held-out score. Add a **warrant obligation** — every learned diff must cite trace IDs and the deterministic assertion that failed, and promotion must *verify the cited failure exists*. Add a **retirement path**; add-only is the accumulation mechanism. |
| **F14** | **The experience→skill pipeline launders poison.** Tencent, 2026-08-04: safety detection **98.5% → 11.4%** when a poisoned trajectory is compiled into a skill; ASR 56.2% / 89.2%; **80.0% of skill-mediated attacks survive deletion of the source records**; some skills fire on benign queries. | §16.2 | T6's "emit reviewable source" is reviewed at the **11.4%-detection layer**. Scanning must run on the **originating trajectory**, and deleting/quarantining a trace must **cascade-retract every derived artifact**. Provenance edges become mandatory, not advisory. |
| **F15** | **Individually-benign learned experiences can be *adversarially composed* to break the safety boundary** — the attacker submits only benign tasks and never touches memory (2026-08-03). | §16.3 | Sharpens Sweep 1 §4.3(a) from *drift* to *attack*. D23's per-diff classifier is not merely blind to slow erosion; it is **defeatable by construction**. Blast-radius must be computed over the **set** of pending/applied diffs against a frozen baseline. |
| **F16** | **Equal eval scores hide 31.2× token differences between frameworks** (SEA-Eval), and *"success rate alone creates a capability illusion"*. Separately, CurveShift: *"newer models are usually run with newer agentic harnesses, so a gain on hard tasks cannot be assigned to the model or its scaffold."* | §17.1, §17.2 | **D27 (the CTS pass rule) is under-specified**: it names scores only, so a conforming adapter may be 31× more expensive. Make cost/token a **joint** pass condition with score. And the Portability Report must publish the **2×2** (model × harness), never a single delta. |
| **F17** | **"PACT" is now a heavily-contested name in this exact space.** *Private Access Control Tokens* (Cloudflare + Chrome + Edge + Firefox + Shopify, 2026-06-25, heading for standardisation) is an **AI-agent authentication protocol**. *PACT5 — Protocol for Agent Coordination and Trust* is a **multi-agent governance protocol**. Plus a third `pact` agent-payments repo. | §19 | Sweep 1 §1.6 concluded *"PACT's distinct name is an asset"*. **That conclusion is now false.** D1 marks the name permanent and user-facing; this needs an explicit decision, not silence. |
| **F18** | **Claude Agent SDK, verbatim: *"Skills must be created as filesystem artifacts. The SDK does not provide a programmatic API for registering Skills."*** And *"The `skills` option is a context filter, not a sandbox… their files remain on disk and are reachable through Read and Bash."* And SKILL.md `allowed-tools` *"does not apply when using Skills through the SDK"*. | §20.1 | Three concrete capability-lattice rows. Skill **exposure** lowers as `degraded` (filter, not isolation); skill **tool restriction** lowers as `unsupported`; and the adapter must **materialise** skills to a scratch tree — the one place where "no adapter reads author files" (P-1) meets a substrate that only reads files. |
| **F19** | **Every major vendor shipped a named, separable *harness* layer in 2026**: `pydantic_ai_harness` (24+ capabilities), LangChain **`deepagents`** (self-described "agent harness"), OpenAI's "model-native harness" + native sandbox, Eve `concepts/default-harness`, plus CAAF's "Harness as an Asset". | §11.4 | D12 is no longer a contrarian bet — **the industry converged on PACT's layering**. Reposition: PACT's harness is not competing with frameworks' loops, it is the same layer they all just built, *made portable and declarative*. Also: each vendor harness is a **native-lowering target**, not a thing to emulate. |
| **F20** | **Eve shipped ACP v1 over stdio (`eve acp`) and a UCP `.well-known` profile** after the corpus clone — a third and fourth interop edge beyond MCP (tools) and A2A (remote invocation): the **editor/client edge** and a **signed `.well-known` capability profile**. | §18.3 | Add **ACP** to the projection list (A2A card, OSSA, Bud `AgentRecord`). The `.well-known` + signing-keys shape is the right form for D24's minimal, adapter-shaped discovery seam. |
| **F21** | **Microsoft's industrial eval-curation paper rules out synthetic eval sets** for exactly the two reasons D19.4 assumes away: combinatorial blowup over ~30 typed capabilities, and phrasing-distribution mismatch. Its unit is the **capability signature**, and its curator *"only suggests evictions"*. | §17.3 | Constrain D19.4: builder-generated cases are **coverage scaffolding**, never the oracle. Adopt **capability-signature coverage** as the admission policy for trace→eval promotion (AC-4.4) — it is computable directly from PACT's IR — and make eviction **suggest-only**. |
| **F22** | **EvolveNet (2026-08-05): learned *program adaptations* are the unit that federates across data-local deployments** — *"independently modified programs cannot be averaged like model parameters and may conflict when composed"*, requiring **scope-typed, evidence-guided aggregation**. | §11.3 | This is exactly PACT's artifact (T6 emits diffs) and exactly PACT's air-gap problem (D17: traces cannot leave). Learned diffs must carry a **scope tag** + **evidence** so they can be merged across tenants without moving traces, and **merge conflict must be an error** — consistent with the Expansion Rule's disjoint-union stance (E-rules). |

---

## 11. The harness is now the industry's unit of engineering — and the measurements are sharper

Sweep 1 §3.1 (EffGen) established that agent frameworks score *below the raw model* at 1.5B and
that the sign flips near 32B. Two papers published since, plus a fifth vendor harness release,
change what follows from that.

### 11.1 CMU — *Better Harnesses, Smaller Models* (arXiv 2607.08938, 2026-07-09)

`papers/arxiv-2607.08938.pdf`. Yang, Zhao, Wu, Kästner — Carnegie Mellon University.
Code: <https://github.com/malusamayo/migration-analysis>. All figures read from the PDF `[V]`.

**Abstract, verbatim `[V]`:**
> *"Frontier LLM agents are automating many business tasks, but their high inference cost makes
> large-scale deployment unsustainable. Small language models (SLMs) offer a cheaper alternative,
> yet they typically fall short when swapped into a harness designed for a frontier LLM. We show
> that for many routine business tasks, SLM agents can match LLM performance at 90% lower cost,
> when paired with an adapted harness that can be automatically discovered by a meta agent. The key
> insight is that much of the task difficulty is shared across instances and can be lifted from the
> model into the harness via tailored instructions, tools, and orchestration loops."*

Those three nouns — **instructions, tools, and orchestration loops** — are PACT's Strategy axes,
named independently.

**Table II, verbatim (accuracy / cost-per-instance / latency), 7 business tasks `[V]`:**

| Model | Attn. | Budget | Stock | Anom. | Playwr. | Web. | Refact. | **Avg** |
|---|---|---|---|---|---|---|---|---|
| gemini-3.1-pro-preview | 96.5 | 97.3 | 86.7 | 98.9 | 85.7 | 76.7 | 86.1 | **89.7** |
| | $0.894 | $0.219 | $5.785 | $1.450 | $0.667 | $2.011 | $1.116 | **$1.735** |
| | 206s | 70s | 319s | 148s | 213s | 157s | 155s | **181s** |
| gemma-4-26b-a4b (raw) | 91.7 | 75.0 | 5.0 | 5.0 | 9.9 | 1.1 | 32.2 | **31.4** |
| **+ optimized harness** | 95.7 | 98.3 | 58.9 | 99.4 | 98.1 | 45.6 | 65.0 | **80.2** |
| | $0.027 | $0.017 | $0.089 | $0.033 | $0.021 | $0.165 | $0.147 | **$0.071** |
| | 215s | 33s | 177s | 61s | 85s | 206s | 171s | **135s** |
| qwen3-coder-30b-a3b (raw) | 23.7 | 61.0 | 9.4 | 1.1 | 31.4 | 1.1 | 60.6 | **26.9** |
| **+ optimized harness** | 73.7 | 79.3 | 96.7 | 93.9 | 93.6 | 24.4 | 62.2 | **74.8** |
| ministral-3-8b (raw) | 0.2 | 28.8 | 0.0 | 0.0 | 0.4 | 5.6 | 31.7 | **9.5** |
| **+ optimized harness** | 63.3 | 53.7 | **0.0** | **0.0** | 22.3 | **5.6** | 30.0 | **25.0** |

**The four numbers that matter to AC-3.1 `[V]`:**

1. Best case: gemma-4-26b-a4b recovers **80.2 / 89.7 = 89.4%** of frontier accuracy at
   **$0.071 / $1.735 = 4.1%** of cost and 135s vs 181s (**25% latency reduction**). The paper
   states *"recover 89% of LLM performance at 4% cost"*; the abstract says 89.7%.
2. **16 of 21 task-SLM pairs improved significantly; only 7 of 21 closed the gap.**
3. **At 8B, adaptation nearly fails**: 9.5 → 25.0 avg = **27.9%** of frontier, with Stock, Anomaly
   and Web unchanged (0.0 → 0.0, 0.0 → 0.0, 5.6 → 5.6). Verbatim: *"weaker SLMs struggle with the
   intrinsic task difficulty that cannot be offloaded to the harness."*
4. **Task diversity governs everything.** Verbatim: *"we observed a strong, statistically
   significant negative correlation (Spearman ρ = −0.96) between task diversity and optimized
   harness performance"*, plus a controlled experiment: *"optimized harnesses work worse with more
   diverse instances, dropping performance from 89.1% to 68.0%."* Diversity is measured as
   *"pairwise normalized Levenshtein distance"* over tool-use sequences across instances.

**Economics, verbatim `[V]`:** *"there is a one-time offline optimization cost per task ($20 in our
experiments)… the optimization cost is already recovered after 13 runs on average across tasks and
models."* Total optimisation budget for the study: $1,260.

**The failure-mode → adaptation-strategy table (Figure 2), transcribed `[V]`** — this is directly
implementable as PACT's Resolver diagnosis table:

| Failure mode (capability-indexed) | Recommended adaptations |
|---|---|
| **tool-use** — *"Fail to use the right tools"* | `A1·demonstrate`, `T1·wrap`, `T2·filter` |
| **instruction-following** — *"Fail to follow complex instructions"* | `A1·reinforce`, `L2·split`, `T1·enforce`, `L1·enforce` |
| **knowledge** — *"Lack of domain knowledge"* | `A1·externalize`, `T1·encode` |
| **long-context** — *"Degraded performance over long context"* | `A2·reveal`, `A2·compress`, `T1·reduce`, `L2·split` |
| **planning / reasoning** — *"Fail to create viable plans or replan"* | `A1·plan`, `T1·encode` |

Strategy groups, verbatim `[V]`:
- `A1` **Add contexts** — *"Demonstrate examples, reinforce instructions, externalize implicit knowledge, create plans"*
- `A2` **Manage contexts** — *"Reveal progressively, compress and summarize, prune observations, split into multi-agents"*
- `T1` **Create tools** — *"Wrap common sequences, enforce constraints, encode knowledge and planning"*
- `T2` **Manage tools** — *"Filter the tool set, adapt tool schema"*
- `L1` **Instrument code** — *"Create programmatic checks and procedures"*
- `L2` **Orchestrate agents** — *"Split tasks and roles; orchestrate agent flow"*

RQ4 result, verbatim `[V]`: *"Instruction-following and knowledge failures are the dominant failure
modes."* Note where those two land: `A1` (contexts) and `T1` (tools) — i.e. **the cheap,
depth-free mechanisms**, which corroborates the MASS ordering already in `00-THESIS.md` §7.3.

**Threats to validity the authors state `[V]`:** *"The agent runs and the optimization process are
highly stochastic, even with our mitigation of multiple repeated runs."* And: *"Because we use
closed-source frontier LLM APIs that are black-box and may evolve over time, exact replication of
the optimization may be difficult."*

> **Design consequences.**
> 1. **AC-3.1's ≥95% bar is above the best number in the published literature (89.4%).** Either the
>    threshold is restated as a *per-contract author choice* with 89% as the documented reference
>    point, or PACT ships a bar it cannot hit and the FAIL path becomes the normal path — which is
>    honest but must be *designed for*, not discovered.
> 2. **Add a pre-flight workflow-diversity predicate.** ρ = −0.96 means diversity of the eval set
>    predicts whether porting can work *at all*, and it is computable **offline, before any model
>    call**: normalised Levenshtein over the expected tool-call sequences of the eval cases. This is
>    D11 ("fail, then recommend") moved *earlier* — refuse or warn before spending optimiser budget,
>    not after. Cheapest high-value check found in this sweep.
> 3. **Add a base-capability floor.** The 8B row is a floor, not a slope. The capability-predicate
>    language (O3.1) should express *"do not attempt optimisation below tier X"* and the resolver
>    should report it as a distinct verdict from "optimised and failed".
> 4. **Put optimisation amortisation in the Portability Report.** "$20 one-time, recovered after 13
>    runs" is the number a non-technical author needs to decide, and PACT already has the cost model
>    (O3.2) to compute it.
> 5. **Adopt the 5×6 diagnosis table as the Resolver's strategy-selection policy**, keyed off the
>    failure taxonomy extracted from failing eval traces. It is published, cited, and maps 1:1 onto
>    PACT's IR fields (instructions/skills → A1/A2; tools → T1/T2; loop → L1; topology → L2).

### 11.2 *It's Not the Size: Harness Design Determines Operational Stability in SLMs* (arXiv 2605.12129, 2026-05-12)

`papers/arxiv-2605.12129.pdf`. Yong-eun Cho, KailosLab. Read from the PDF `[V]`.

Three harness conditions × three models (Gemma4 E2B, Qwen3.5:2B, LLaMA 3.2 3B) × 24 tasks.
Conditions: **model-only** (raw prompt) · **minimal-shell** (wrapper tags) ·
**4-stage pipeline** (`plan → execute → verify → recover`). Metrics: Task Success Rate (TSR) and
Valid TSR (VTSR); thresholds TSR ≥ 0.65, VTSR ≥ 0.80.

Verbatim findings `[V]`:
> *"The pipeline harness achieves TSR=0.952 and VTSR=1.000 on Gemma4 E2B (T1–T5, 21 tasks). A
> non-monotonic phenomenon—minimal-shell TSR < model-only TSR—is observed in two models. In LLaMA
> 3.2(3B) model-only, seven format violations yield TSR=0.429, revealing scaffold collapse: the
> model abandons JSON structure under complex format requirements without harness support. Ablation
> shows planning and recovery each contribute ~24.7% of total gain. VCR (Verification Catch Rate) =
> 0.625 across all pipeline runs."*

Contributions list, verbatim `[V]`, items 3–5:
> *"3) Evidence that the recovery mechanism is the primary contributor to pipeline gains, and
> classification of harness-fixable vs. unfixable failure modes. 4) Ablation showing the planning
> stage acts as a format anchor for quantitative constraints (e.g., character limits).
> 5) Introduction of scaffold collapse: under complex format requirements, LLaMA 3.2(3B) abandons
> JSON structure without harness support (TSR=0.429, 7 violations), showing harness format
> enforcement functions independently of content generation ability."*

> **Why this is more actionable than EffGen.** EffGen said *which framework* you pick matters and
> flips sign with scale. This says *how complete your harness is* matters and **flips sign within a
> single model**. A partial harness is worse than none; a complete one is transformative. Combined
> with §11.1's finding that verify/recover-shaped adaptations (`L1·enforce`) address the dominant
> failure mode, the conclusion is specific:
>
> - **PACT must not offer a "light"/"minimal" harness profile.** If harness lowering is on, the
>   lowered loop must include `verify` and `recover` nodes. Make them **required node kinds** in the
>   loop IR whenever the resolved tier is below the (measured) sign-flip, rather than optional
>   decorations an author can omit.
> - **The CTS harness-vs-raw gate (T3-corollary) must include the partial configuration.** Testing
>   only `full-harness vs raw` would have missed the entire finding. Three arms: raw · partial ·
>   full.
> - `VCR = 0.625` is a usable design number: a verification stage that catches ~62% of failures is
>   what buys the gain. PACT's verify node should therefore be **measured** (emit a catch rate into
>   the trace), which also gives the Portability Report a diagnostic when a port underperforms.
> - "Scaffold collapse" names a concrete D16/G-1 hazard: **format enforcement is a harness function
>   independent of model quality.** This is a second, independent argument for constrained decoding
>   being a *strategy* field (§7.3 mechanism 5), and for it having a harness-side fallback where the
>   substrate cannot do grammar-constrained generation.

### 11.3 EvolveNet — collaborative harness evolution (arXiv 2608.04968, 2026-08-05)

`papers/arxiv-2608.04968.pdf`. Nie, Zhang, Cai, Cheung, Tian, Han (HKBU / USTC / HKUST).
Code: <https://github.com/junnie00/EvolveNet>. Abstract read from PDF `[V]`.

Verbatim `[V]`:
> *"The capabilities of an LLM agent depend not only on its model but on the harness: the executable
> program that constructs context, invokes tools, verifies results, and recovers from failure.
> Recent work shows that evolving the harness yields persistent improvements without updating model
> weights. Existing approaches, however, assume that all execution experience can be routed to a
> single optimizer… Real agent ecosystems violate that assumption: users, organizations, and
> environments generate isolated streams of experience that cannot be pooled, so the experience most
> worth learning from is exactly the experience that cannot be directly centralized. We introduce
> EvolveNet, a paradigm of collaborative harness evolution that moves experience extraction to the
> data. A shared harness is broadcast to data-local agent deployments, each of which evolves it on
> its own workload. Only the resulting program adaptations are composed into an updated shared
> harness and redistributed… Because independently modified programs cannot be averaged like model
> parameters and may conflict when composed, EvolveNet introduces scope-typed, evidence-guided
> program aggregation. Across five settings spanning text-to-SQL, data-science coding, competitive
> programming, software engineering, and agentic workflows, EvolveNet improves the shared harness in
> all five, with the largest gains under heterogeneous workloads, and ablations attribute the
> improvement to composition of adaptations from different agents rather than to selecting among
> them."*

> **This is PACT's air-gap learning story, written down by someone else.**
> D17 forbids traces leaving the enclave; T6 makes the learned artifact a **diffable source file**;
> D9 wants a real learning loop. EvolveNet's insight is that the *diff* is precisely the unit that
> can federate when the *trace* cannot. Three concrete IR requirements follow, and none is currently
> specified:
> 1. **Every learned diff carries a scope tag** (`workspace | agent | variant | run`, which PACT
>    already has as its override scopes) so aggregation knows where a change is allowed to land.
> 2. **Every learned diff carries evidence** (the traces/metrics that justified it) so composition
>    is *evidence-guided* rather than last-writer-wins. This is the same field F13 demands for a
>    different reason — one field, two justifications.
> 3. **Composition conflict is an error, not a merge.** The paper's *"cannot be averaged… may
>    conflict"* is the identical stance the Expansion Rule already takes on document folding
>    (disjoint union, conflict is an error). Reusing that rule for diff composition keeps the system
>    to one merge semantics instead of two.
>
> `[I]` The ablation result — gains come from **composing** adaptations across agents, not selecting
> among them — argues against a naive "pick the best variant" learning loop and for a **merge**
> loop. That is a materially different design from what D9/O5.3 currently imply.

### 11.4 Five vendors shipped a named harness layer in 2026 `[V/S mixed]`

| Vendor | Artifact | Evidence |
|---|---|---|
| **Pydantic AI** | `pydantic_ai_harness` — *"the batteries for your Pydantic AI agent"*, 24+ capabilities, shipped as a separate package *"to enable faster iteration than core"*. **Explicitly does not own the loop**: *"The agent loop resides in Pydantic AI core."* | <https://pydantic.dev/docs/ai/harness/> `[V]` |
| **LangChain** | **`deepagents`** — self-described *"agent harness: a standalone library built on top of LangChain's agent building blocks and powered by the LangGraph runtime for durable execution, streaming, and human-in-the-loop"*. Middleware for history compression, tool-result offload, subagent context isolation, prompt caching. **Declarative subagent specs and declarative permission rules** over file/directory access. | <https://docs.langchain.com/oss/python/deepagents/overview> `[S, docs prose]`; releases updated 2026-06-30 |
| **OpenAI** | *"a model-native harness that lets agents work across files and tools on a computer, plus native sandbox execution"*; subagents and "code mode" announced as coming soon (2026-04-15 overhaul). | <https://openai.com/index/the-next-evolution-of-the-agents-sdk/> `[S]` |
| **Vercel Eve** | `/docs/concepts/default-harness` is a first-class concept page. | eve.dev sitemap `[V]` |
| **CAAF (research)** | *"Harness as an Asset"* — the harness as a first-class enterprise asset that *"compounds in value as foundation models commoditize"* (Sweep 1 §3.3). | `papers/arxiv-2604.17025.pdf` `[V]` |

**`deepagents` is not in the local corpus** — `research/repos/frameworks/langchain/libs/` contains
`core`, `langchain`, `langchain_v1`, `model-profiles`, `partners`, `standard-tests`,
`text-splitters` only `[V]`. It is a separate `langchain-ai/deepagents` repository.

> **Positioning consequence.** D12 ("PACT owns loop semantics; frameworks are transports") was
> written as a trade-off — *"generated code looks less like hand-written LangGraph."* That framing
> is now out of date: **LangGraph's own vendor ships a harness layer above LangGraph**, as does
> Pydantic AI, as does OpenAI, as does Eve. Idiomatic 2026 code for these frameworks *is* harness
> code. Two follow-ons:
> - The D26 performance objection to harness lowering weakens: PACT is not adding a layer, it is
>   *replacing* a layer the user would otherwise take from the vendor.
> - **Each vendor harness is a native-lowering target.** PACT's `skills:`, `memory:`,
>   `guardrails:`, `subagents:`, `planning`, `context-compression` and `sandbox` should lower onto
>   `pydantic_ai_harness.{Skills,Memory,Guardrails,Subagents,Planning,CodeMode,FileSystem}` and onto
>   `deepagents` middleware respectively, rather than being emulated. That is a large, cheap
>   fidelity win for the two prototype adapters (D5/D7) and it should be reflected in the capability
>   lattice as `native` rather than `emulated` for those features.

---

## 12. Microsoft Agent Framework has **two** declarative YAML surfaces (settles OQ3)

Both are official Microsoft Learn reference docs, `ms.date` 2026-05-22 and 2026-06-26, both
`updated_at: 2026-07-10` `[V]`.

### 12.1 Declarative **agents** — `kind: Prompt`

<https://learn.microsoft.com/en-us/agent-framework/agents/declarative> `[V]`

> *"Declarative agents allow you to define agent configuration using YAML or JSON files instead of
> writing programmatic code. This approach makes agents easier to define, modify, and share across
> teams."*

Python API: `agent-framework-declarative` package → `AgentFactory.create_agent_from_yaml(yaml, safe_mode=…)`
and `create_agent_from_yaml_path(path)`.
C# API: `Microsoft.Agents.AI.Declarative` → `ChatClientPromptAgentFactory.CreateFromYamlAsync(yaml)`.
Go: *"Go support for this feature is coming soon."*

Full documented example, verbatim `[V]`:

```yaml
kind: Prompt
name: DiagnosticAgent
displayName: Diagnostic Assistant
instructions: Specialized diagnostic and issue detection agent …
description: An agent that performs diagnostics on systems …
model:
  id: =Env.AZURE_OPENAI_MODEL
  connection:
    kind: remote
    endpoint: =Env.FOUNDRY_PROJECT_ENDPOINT
```

and the C# example additionally shows `model.options.{temperature,topP}` and an `outputSchema` with
`properties[].{type,required,description}` `[V]`.

Fields observed: `kind`, `name`, `displayName`, `description`, `instructions`, `model.id`,
`model.options`, `model.connection.{kind,endpoint}`, `outputSchema`.
**Not observed anywhere in the page: `tools`, evals, SLOs, capability requirements, variants,
memory, policy, topology.** The `=Env.X` prefix is the PowerFx expression escape.

### 12.2 Declarative **workflows** — `kind: Workflow`

<https://learn.microsoft.com/en-us/agent-framework/workflows/declarative> (8,196 words) `[V]`

Positioning, verbatim `[V]`: *"**Readable format**: YAML syntax is easy to understand, even for
non-developers"*, and a decision table naming *"Non-developers need to modify workflows →
Declarative"* against *"Complex custom logic → Programmatic"*.

**The two dialects are different languages `[V]`:**

| | C# | Python |
|---|---|---|
| Top-level | `kind: Workflow` + `trigger.{kind,id,actions}`; trigger kind typically `OnConversationStart` | `name` + `description` + `inputs` + `actions` |
| Inputs | *"C# declarative workflows do not use `Workflow.Inputs` or `Workflow.Outputs` namespaces. Input is received via `System.LastMessage` and output is sent via `SendActivity` actions."* | typed `inputs.<param>.{type,description}` |
| Conversation actions | 4 actions available | **not available** |

**28 action kinds (from the Actions Quick Reference table) `[V]`**, `✅/❌` = C#/Python:

`SetVariable` ✅✅ · `SetMultipleVariables` ✅✅ · `SetTextVariable` ✅✅ · `ResetVariable` ✅✅ ·
`ClearAllVariables` ✅✅ · `ParseValue` ✅✅ · `EditTableV2` ✅✅ · `If` ✅✅ · `ConditionGroup` ✅✅ ·
`Foreach` ✅✅ · `BreakLoop` ✅✅ · `ContinueLoop` ✅✅ · **`GotoAction`** ✅✅ · `SendActivity` ✅✅ ·
`InvokeAzureAgent` ✅✅ · `InvokeFunctionTool` ✅✅ · `InvokeMcpTool` ✅✅ · `HttpRequestAction` ✅✅ ·
`Question` ✅✅ · `RequestExternalInput` ✅✅ · `EndWorkflow` ✅✅ · `EndConversation` ✅✅ ·
`CreateConversation` ✅✅ · `AddConversationMessage` ✅❌ · `CopyConversationMessages` ✅❌ ·
`RetrieveConversationMessage` ✅❌ · `RetrieveConversationMessages` ✅❌

Expression language: PowerFx, values prefixed `=`. Namespaces `Local.*` and `System.*`
(`System.ConversationId`, `System.LastMessage`, `System.LastMessage.Text`). Functions documented:
`Concat`, `If`, `IsBlank`, `Upper`/`Lower`, `Find`, `MessageText`, `UserMessage`, `AgentMessage`.
Guard rails on the expression engine: `MaximumCallDepth = 50`, `MaximumExpressionLength = 10000` `[V]`.

Checkpointing/resume exists (`### Resuming from Checkpoints`, `### AOT and Trim-Aggressive
Checkpointing`, `#### Registering user-defined types`) `[V]`.

### 12.3 What it cannot do — all `[V]` from the same pages

| Missing / bound | Evidence |
|---|---|
| **Air-gapped operation** | Prerequisite, verbatim: *"A **Microsoft Foundry** project with at least one deployed agent."* The agent provider is `AzureAgentProvider(new Uri("https://your-project.api.azureml.ms"), new DefaultAzureCredential())`. `InvokeAzureAgent` is documented as *"Invokes a Foundry agent"* and takes `agent.name` = *"Name of the registered agent"*. There is no local/offline agent provider on the page. |
| **One dialect** | See §12.2 — C# and Python YAML are structurally different and differ in available actions. |
| **Evals / metrics / datasets** | Absent from both pages. |
| **SLOs, capability requirements, model predicates** | Absent. `model.id` is a literal (or an env expression). |
| **Variants / strategy plurality** | Absent. |
| **Learning / optimisation** | Absent. |
| **Filesystem/directory form** | Single YAML document loaded by path; no tree loader, no path-as-identity. |
| **Structured control flow** | Present, *plus* `GotoAction` — *"Jump to action by ID"*. |
| **Tool definition in YAML** | `InvokeFunctionTool` *"Invokes a function tool directly from the workflow"* — the function must be registered in host code. `connection.name` for hosted MCP is documented as *"not fully supported yet"*. |

> **Design consequences.**
> 1. **The no-code competitor is real and it is Microsoft.** D14's bar ("a non-technical domain
>    expert builds a multi-agent system entirely in YAML/Markdown") is now partially met by a
>    shipping product with better distribution. PACT's remaining, defensible differentiators are
>    exactly and only: **offline execution (D17)**, **evals in the portable artifact (T2)**,
>    **capability contracts + variants (T4)**, **learning (D22)**, **one dialect**, and
>    **filesystem-native tree (D2)**. Positioning that leads with "declarative multi-agent YAML" is
>    now a commodity claim.
> 2. **Add MAF YAML to the D3 superset corpus.** Sweep 1 added Pydantic AI `AgentSpec`; MAF's
>    `kind: Prompt` and `kind: Workflow` are the second and third external formats PACT should be
>    able to import losslessly-or-reported (P-3). Both are cheap: they are documents, not code, so
>    the importer is spec-to-spec — no 2,560-line rulepack (Sweep 1 §1.5b).
> 3. **`GotoAction` is the anti-pattern to name.** A no-code surface with unrestricted `goto` is
>    not analysable: you cannot compute reachability, blast radius, or a topology from it. PACT's
>    loop/topology IR should state explicitly that it has **no unrestricted jump**, and that its
>    control flow is a graph with typed edges (G-2/G-3), citing this as the failure to avoid. This
>    is also a concrete usability argument for D28 failure mode #1.
> 4. **The two-dialect split is a portability lesson with a name.** One vendor, one product, two
>    incompatible YAML dialects for the same concept, four actions available in only one of them.
>    That is what happens when the format is a serialisation of each runtime's object graph
>    (thesis §1.3, "Framework-native YAML"). PACT's answer — one document model, adapters below it
>    — is validated by a *within-vendor* counterexample, which is stronger evidence than a
>    cross-vendor one.
> 5. **`MaximumCallDepth = 50` / `MaximumExpressionLength = 10000` are worth copying.** PACT's
>    expression/predicate language (O3.1) needs equivalent hard bounds so that "config-only" cannot
>    become "config-only Turing tarpit". Add them as profile values (F-1), not literals.

---

## 13. OASF settles OQ1 — and hands PACT its best citation

Read from the **local checkout**, `research/repos/protocols/agntcy-oasf`, HEAD `e856537`,
2026-07-21 `[V]`. (The Outshift blog body remained unretrievable on a second attempt; it was not
needed.)

### 13.1 OASF has an `evaluation` module. It is a *results record*.

`schema/modules/core/evaluation.json` `[V]` — one attribute, `data → evaluation_data`.

`schema/objects/evaluation_data.json` `[V]`: `overall_rating` (optional), `overall_scores`
(optional), `referred_evaluations` (**required**).

`schema/objects/overall_scores.json` `[V]`: exactly three fields —
`quality_score`, `cost_score`, `security_score`, all "recommended".

`schema/objects/referred_evaluation.json` `[V]`: `datasets`, `publisher` (**required**),
`created_at` (**required**), `evaluation_report`; constraint `at_least_one: [datasets, evaluation_report]`.

`schema/objects/evaluation_report.json` `[V]`: `overall_scores`, `metrics`;
constraint `at_least_one: [overall_scores, metrics]`.

`schema/objects/metric.json` `[V]`: `name`, `type` (*"'counter', 'gauge', or 'histogram'"*),
`unit_of_measurement` (UCUM), `url`, `data_points` (referencing the **OpenTelemetry** metrics data
model).

`schema/objects/evaluation_dataset.json` `[V]`: `url` (**required**), `name` (**required**),
`version`, `metadata`.

**What is absent, verified by reading every one of those files `[V]`:** no metric *definition*, no
threshold, no pass/fail criterion, no rubric, no judge configuration, no assertion, no expected
output, no test case. `metric.type` is the OTel telemetry taxonomy (counter/gauge/histogram), not
an evaluation taxonomy.

> **Therefore: an OASF record tells you *that someone scored this agent*, and their name and the
> date. It does not let you re-run their evaluation, and it does not let two implementations agree
> on what "passing" means.** Datasets are `url`s — which is also air-gap-hostile (D17).
>
> This is the precise distinction PACT should use in positioning, because it survives the obvious
> objection *"but OASF/Oracle already have evaluation"*: **they have an evaluation *record*; PACT
> proposes an evaluation *contract*.** T2 is unclaimed on the axis that matters.

### 13.2 `agentspec_data` — the competitor's schema admits its specs are not self-contained

`schema/modules/integration/agentspec.json` `[V]`, `uid: 4`, referencing
<https://oracle.github.io/agent-spec/index.html>.

`schema/objects/agentspec_data.json` `[V]` — four attributes:

| Field | Requirement | Description, verbatim |
|---|---|---|
| `config` | required | *"Location of the Agent Spec config. E.g. path to config, github repo url etc."* |
| `deployment_options` | required | *"List of possible configuration to instantiate or consume the agent."* |
| `runtime_deps` | optional | ***"List of locators for the non-serializable objects the Agent Spec config depends on (e.g. tool implementations)."*** |
| `env_vars` | optional | *"List of environment variables to be set for the agent."* |

`schema/dictionary.json:376-380` `[V]` repeats the `runtime_deps` description verbatim and types it
`json_t[]`.

`schema/objects/agentspec_deployment_option.json` `[V]`: `name`, `protocol` (required, → `a2a` |
`responses_api`), `runtime_framework` (required).

> **This is the strongest single piece of evidence found in either sweep for D15 ("translate or
> nothing") and for T2.** Oracle Agent Spec is the closest shipping competitor, and the
> Linux-Foundation registry schema built to carry it has a **required** field for *where the spec
> file lives* and an explicit field for *the non-serialisable things it depends on, e.g. tool
> implementations*. The portable artifact is a **pointer plus a bag of out-of-band dependencies**.
> PACT's position — the tree is the artifact, tools are declared, nothing is a locator to code the
> receiver does not have — is exactly the gap this field names.
>
> `[I]` It also tells PACT something operational: an OASF projection (O6.2) is easy, because OASF
> is *expecting* a locator plus deployment options. PACT can fill `config` with the workspace
> coordinate and leave `runtime_deps` **empty** — and "empty `runtime_deps`" is a machine-checkable
> claim of self-containment worth surfacing in the export report.

### 13.3 The rest of the OASF record `[V]`

`schema/objects/record.json` — `name`, `version`, `schema_version`, `description`, `authors`,
`created_at`, `skills` (**required**), `domains`, `locators`, `modules`, `annotations`.
Module categories present in `schema/modules/`: `core/{core,evaluation,observability,language_model/*}`,
`integration/{acp_manifest,agentspec,mcp,a2a,integration}`.

---

## 14. DeepEval ships four optimizers — and four defects PACT must not inherit (settles OQ5)

Read from the **local source**, `research/repos/eval/deepeval`, HEAD `6cf2e02`, 2026-07-22. All `[V]`.

### 14.1 The surface

`deepeval/optimizer/prompt_optimizer.py:52-58`:

```python
class PromptOptimizer:
    def __init__(
        self,
        model_callback: ModelCallback,
        metrics: Union[List[BaseMetric], List[BaseConversationalMetric]],
        optimizer_model: Optional[Union[str, DeepEvalBaseLLM]] = None,
        algorithm: Union[GEPA, MIPROV2, COPRO, SIMBA] = GEPA(),
        ...
```

Algorithms shipped: `deepeval/optimizer/algorithms/{gepa,miprov2,copro,simba}/` — **GEPA is the
default**. Public API is `optimize(prompt, goldens) -> Prompt` / `a_optimize(...)`.

The algorithm ABI, `deepeval/optimizer/algorithms/base.py:11-30`:

```python
class BaseAlgorithm(ABC):
    name: str
    optimizer_model: DeepEvalBaseLLM
    scorer: BaseScorer
    @abstractmethod
    def execute(self, prompt: Prompt, goldens: ...) -> Tuple[Prompt, Dict]: ...
```

**Corroboration for AC-3.1b `[V]`:** `optimizer_model` is a **separate binding** from
`model_callback` (the model under evaluation). A shipping, widely-used tool already separates them,
which makes AC-3.1b conventional rather than novel — cite it when defending the requirement.

### 14.2 Four verified defects

`deepeval/optimizer/algorithms/gepa/gepa.py:88-119`:

```python
def __init__(
    self,
    iterations: int = 5,
    minibatch_size: int = 8,
    pareto_size: int = 3,
    random_seed: Optional[int] = None,
    patience: int = 3,
    tie_breaker: TieBreaker = TieBreaker.PREFER_CHILD,
    aggregate_instances: Aggregator = mean_of_all,
    reflection_model: Optional[DeepEvalBaseLLM] = "gpt-4o-mini",
    mutation_model: Optional[DeepEvalBaseLLM] = "gpt-4o",
    scorer: Optional[BaseScorer] = None,
) -> None:
    ...
    if random_seed is None:
        random_seed = time.time_ns()
```

| # | Defect | Evidence | Why it matters to PACT |
|---|---|---|---|
| D-1 | **Validation set defaults to 3 examples.** `pareto_size: int = 3`, docstring *"Size of the Pareto validation subset D_pareto. Default is 3."* | `gepa.py:74-75, 92` | A 3-item validation set cannot distinguish a real gain from noise. AC-3.5 requires a *frozen held-out split*; the reference implementation's default makes overfitting the expected outcome. |
| D-2 | **Two-way split only; there is no test set.** `d_feedback, d_pareto = split_goldens(goldens, self.pareto_size, …)`; `split_goldens` docstring: *"Split `goldens` into two disjoint parts"*. | `gepa.py:153-154, 327-328`; `optimizer/utils.py:35-55` | O3.5's protocol (*"test split untouched until the end"*, R6) is **not provided**. PACT must own the three-way split; the provider gives two. |
| D-3 | **The split is non-reproducible by default.** `random_seed = time.time_ns()` when `None`. | `gepa.py:116-118` | Two runs of "the same" optimisation validate on different data. PACT's lockfile/report must record the split seed, and PACT should pass an explicit seed always. |
| D-4 | **Hardcoded hosted-model defaults, with the reflector the *smaller* model.** `reflection_model="gpt-4o-mini"`, `mutation_model="gpt-4o"`. | `gepa.py:96-97` | (a) Fails outright under **D17** (air-gapped). (b) Inverts **AC-3.1b**: the in-repo ACE evidence is that reflective gain *collapses* with reflector strength (+17.1 at 671B → **+2.4** at 70B). Defaulting the reflector to a mini model is the exact failure AC-3.1b was written to prevent. |

### 14.3 What COPRO does differently `[V]`

`copro.py:47-78, 197-242`: `minibatch_size: int = 25`, `_sample_minibatch()` samples from the full
golden set each depth, and `score_pareto(best_batch_config, goldens)` scores the winner **on all
goldens** — i.e. COPRO validates on the same data it selects from. Also uses a `pareto_score_table`.

### 14.4 The optimizer ABI question (OQ7, still open)

DeepEval's ABI is `(Prompt, List[Golden]) -> (Prompt, report)`. PACT's E-5 needs
`(spec, evalSuite, budget) -> candidate spec + verdict`. **DeepEval's is strictly narrower on three
axes**: it optimises *a prompt* (not instructions + skills + tool exposure + decomposition + loop,
per T4), it has no *budget* parameter, and its return has no *verdict* — the caller gets the best
prompt whether or not it beat the baseline.

> `[I]` Consequence: DeepEval's optimizer is usable as **one** implementation behind PACT's ABI
> (bind PACT's instruction field to `Prompt`), but it cannot be the ABI. And PACT must wrap it to
> supply: the third split, an explicit seed, a local reflector/mutator binding, a budget, and a
> verdict. That wrapper is small and should be specified as part of O3.4's reference
> implementation, with the four defects above as its regression tests.

### 14.5 DeepEval still has no config-only mode `[V]`

Checked again on the official changelog <https://deepeval.com/changelog/changelog-2026>: 2026
brought DeepEval 4.0, tracing/OTel work, new model entries (`gpt-5.4`, `gpt-5.4-mini`,
`claude-opus-4-7`, Claude Opus/Sonnet 4.6), component-level evals with `results_folder`/
`results_subfolder`, conversation-simulator controller APIs (`proceed()`/`end()`), AgentCore and
OpenInference integrations, and a *"Cursor/skills-compatible `deepeval` skill"*.
**No YAML/config-only evaluation appears anywhere in the 2026 changelog.** Sweep 1 §6.6's
conclusion stands unchanged: the entire config→DeepEval binding layer is PACT's to build, and the
docs still undercount the source.

`[I]` One item is newly relevant to **D19.3** (capture-from-usage): the conversation simulator now
exposes a controller with `proceed()`/`end()` decisions and custom templates. That is the closest
existing thing to PACT's "review queue turns conversations into cases", and it is Python-side —
i.e. another shim, not an adoptable format.

---

## 15. The Pydantic AI Harness (settles OQ2)

<https://pydantic.dev/docs/ai/harness/> `[V]`

> *"the batteries for your Pydantic AI agent"* — an official capability library maintained by the
> Pydantic AI team, shipped as a separate package *"to enable faster iteration than core"*.
> **Loop ownership, verbatim: *"The agent loop resides in Pydantic AI core, which ships the agent
> loop, model providers, the capabilities/hooks abstraction."*** The Harness does **not** own the loop.

Capabilities named on the page (19 of the stated 24+) `[V]`, imported from `pydantic_ai_harness`:

| Group | Capabilities |
|---|---|
| Code / sandbox | `CodeMode` (*"wraps tools into a sandboxed `run_code` tool using Monty"*), `Shell` (*"subprocess command execution with allowlists/denylists"*), `DynamicWorkflow` (*"orchestrates sub-agents from model-written Python"*) |
| Files / media | `FileSystem` (*"sandboxed file access scoped to a root directory"*), `Media` (*"offloads large content to stores (disk, S3, MongoDB)"*) |
| Safety | `Guardrails` (*"validates input, tool calls, and output"*), `WarnOnCacheBusts`, `ToolOutputLimits` |
| Coordination | `Subagents`, `Advisor` |
| Other | `Skills`, `RepoContext`, `Memory`, `Planning`, `StepPersistence`, `ConversationSearch`, `BrowserUse`, `ExaSearch`, `StackOne` |

> **Design consequences — this is the single most useful adapter finding in the sweep.**
> 1. **No D12 conflict.** Loop stays in core; the Harness is a capability bundle. Harness lowering
>    for Pydantic AI can drive `direct.model_request` (already assessed *"clean and low-risk"* in
>    `semantics-pydantic-langgraph.md`) while *also* consuming Harness capabilities as native
>    implementations of PACT resources.
> 2. **`AgentSpec.capabilities` is the seam, and the Harness is what plugs into it.** Sweep 1 §6.1
>    inferred this; it is now concrete. PACT's `skills:`, `memory:`, `guardrails:`, `subagents:`,
>    `sandbox:` and `tools[].limits` lower to **named, maintained** capabilities rather than
>    adapter-local emulation → those lattice rows move from `emulated` to `native`.
> 3. **`Guardrails` validating *"input, tool calls, and output"*** is a three-point interception
>    model. PACT's policy contract should be expressible at the same three points, or the mapping
>    is lossy in one direction.
> 4. **`StepPersistence` + `Media` offload** cover two P-5/G-1 concerns (resume; large binary
>    payloads) that PACT would otherwise have to specify from scratch for this adapter.
> 5. `[I]` **`DynamicWorkflow` — *"orchestrates sub-agents from model-written Python"* — is a
>    D15/T7 hazard.** A PACT agent that imported such a construct would contain model-authored code
>    with no declarative form. It must import as an opaque code node reported `unsupported` (F-3),
>    and PACT must never *emit* it.
>
> **Re-verified and unchanged `[V]`:** `AgentSpec`'s reference field table still has no `tools`,
> no `toolsets`, no evals, no capability requirements, no topology — `model, name, description,
> instructions, model_settings, capabilities, deps_schema, output_schema, retries, end_strategy,
> tool_timeout, instrument, metadata` — and still carries the limitation *"The model's response is
> not validated against the schema's `properties` or required fields — it is accepted as a plain
> dict."* (<https://pydantic.dev/docs/ai/agent-spec/>)

---

## 16. Self-improvement safety, second wave — three attacks that hit PACT's design directly

Sweep 1 §4 found the MLAS matrix (17/25 cells undefended) and gradual blueprint erosion. Three
papers published since are more specific, and two of them break a PACT mechanism as currently
written.

### 16.1 *Phantom Guardrails* (arXiv 2607.13083, 2026-07-13) — **the held-out gate cannot catch this**

`papers/arxiv-2607.13083.pdf`. Wang, Qian, Lin, Xu (CMU) + Corespeed, Georgia Tech, independents.
Abstract read from PDF `[V]`.

Verbatim `[V]`:
> *"Self-improving AI agents are designed to learn from their mistakes. We show that they can also
> hallucinate mistakes that never happened. We study this failure mode in automated harness
> optimization, where an LLM-based proposer edits the scaffold around an agent, including prompts,
> parsers, filters, validators, and guardrails, to make observed failures disappear. But this
> process rarely asks a prior question: was there a real failure to fix? We introduce the
> Counterfactual Fabrication Lab, a deterministic micro-lab where the correct action is known in
> advance to be "do nothing." … The proposer behaves as expected when the violation is real and
> abstains on featureless legal input. Yet when the legal input contains a harmless pattern that
> resembles a familiar game rule, it invents a failure: **in 15/60 runs, versus 0/60 on featureless
> input**, it enables the nonexistent-rule guardrail and cites a violation the oracle refutes."*

The mechanism, verbatim from the introduction `[V]`:
> *"The reward in these loops is almost always the suppression of observed failures. It answers 'did
> the failure stop?' but never 'was the fix warranted?' A recent optimizer makes the asymmetry
> concrete: it accepts a proposed edit only when a self-preference score improves, with no separate
> test of whether the edit was warranted. The regime we study pushes this to its **add-only limit, a
> maintenance loop in which accepted edits persist and nothing is removed**."*

> **Why this breaks AC-5.4 as written.** PACT's learning gate is *"held-out eval improvement"*.
> A guardrail added for a failure class that never occurs **does not reduce held-out score** — it
> is inert on the held-out set. It therefore passes the gate, is signed, is versioned, and
> accumulates. Over generations this is precisely the Sweep 1 §4.3(a) erosion mechanism running in
> the *additive* direction: not "safety dissolves", but "scaffold accretes", with the same
> per-diff-blindness and the same D26/D28-#3 cost consequence.
>
> **Two additions to the learning IR, both cheap and both offline-checkable:**
> 1. **Warrant obligation.** Every learned diff MUST carry the evidence that motivated it —
>    trace IDs plus the specific assertion/metric that failed. Promotion MUST verify that the cited
>    failure *exists in the trace store* and that the cited assertion *actually failed*. A diff
>    whose warrant cannot be resolved is rejected. This is a deterministic check; no judge involved;
>    it works air-gapped. It is the same `evidence` field §11.3 requires for merge — one field,
>    two independent justifications.
> 2. **Retirement path.** The add-only regime is the accumulation mechanism, so the learning
>    subsystem needs a *removal* operator with its own gate: a periodic pass that proposes deleting
>    scaffold whose warrant traces no longer occur, gated on held-out non-regression. Without it,
>    D22 guarantees monotone growth, which is D28 failure mode #3 by construction.
>
> `[I]` Note the trigger condition: fabrication happened when *"the legal input contains a harmless
> pattern that resembles a familiar game rule"* — i.e. **near-miss inputs**, not random ones. PACT's
> eval suites will be full of near-misses by construction (that is what a good eval set is). The
> exposure is above baseline, not below.

### 16.2 *SkillJack* (arXiv 2608.03509, 2026-08-04) — skill extraction launders poison

`papers/arxiv-2608.03509.pdf`. Tencent AI-Infra-Guard.
Code: <https://github.com/Tencent/AI-Infra-Guard/research/skilljack>. Abstract read from PDF `[V]`.

Verbatim `[V]`:
> *"We uncover a new and more fundamental risk: poisoned experiences can be transformed by the agent
> itself into durable behavioral artifacts. … We identify three key properties of this
> transformation: **sanitization whitewashing**, where malicious intent is obscured during skill
> extraction; **cross-layer promotion**, where transient experiences become persistent capabilities;
> and **persistence isolation**, where the attack survives removal of its original source records.
> We evaluate SkillJack on two representative systems, SkillX and Anything2Skill, using a shared
> dataset of 150 trajectories across four policy-risk categories. Results show that skill extraction
> substantially reduces attack detectability: **in SkillX, safety detection drops from 98.5% for
> poisoned trajectories to 11.4% for extracted skills** … the implanted skills remain effective,
> achieving attack success rates of **56.2%** and **89.2%** on the two systems … Furthermore,
> **80.0% of skill-mediated attacks persist after deleting the original poisoned records**, and some
> skills unintentionally activate on benign queries. Our findings … motivate **provenance-aware
> skill lifecycle protection**."*

> **This is aimed squarely at T6 and D22(a)/(b).** T6's defence is *"learning emits reviewable
> source"* — but the measurement says the derived skill is the layer at which detection collapses
> to **11.4%**. Reviewing the emitted artifact is reviewing the laundered version.
>
> **Three requirements, none currently in the design:**
> 1. **Scan at the trajectory layer, not the artifact layer.** Any promotion of trace → skill/tool/
>    instruction must run its safety analysis on the **source trajectory** (98.5% detection) and
>    attach the verdict to the derived artifact. Reviewing only the diff is the failure mode.
> 2. **Cascade retraction.** Deleting or quarantining a trace MUST invalidate every artifact derived
>    from it. 80% persistence-after-deletion is a direct consequence of one-way provenance. PACT's
>    lineage already records *where an artifact came from*; it must also be **queryable in reverse**
>    and **enforced on delete**. This is a schema + CLI requirement (`pact retract <trace-id>`),
>    not a policy note.
> 3. **Provenance edges become mandatory.** A skill with no resolvable origin trace cannot be
>    promoted. Combined with §16.1's warrant obligation, PACT gets one rule that answers both:
>    *no learned artifact without resolvable, verifiable evidence.*
>
> Also note *"some skills unintentionally activate on benign queries"* — corroborating the in-repo
> finding (`model-portability.md`) that ungated skill libraries score **below** the no-skill
> baseline. The governance requirement (dedup, exposure caps, retirement) is now supported by a
> security argument as well as an accuracy one.

### 16.3 *Benign Alone, Harmful Together* / EvoBreak (arXiv 2608.01759, 2026-08-03)

`papers/arxiv-2608.01759.pdf`. Abstract read from PDF `[V]`.

Verbatim `[V]`:
> *"Self-evolving large language model agents improve their capabilities by distilling interaction
> trajectories into persistent experiences. Yet this mechanism introduces a new safety risk:
> **experiences that are benign in isolation may jointly weaken an agent's safety boundary when
> accumulated and reused across sessions**. Existing memory attacks typically require direct memory
> access or induce explicitly malicious records, limiting their stealthiness … We propose EvoBreak,
> an experience-conditioned sequential attack that operates through individually benign attack-stage
> tasks and induced experiences."*

Threat model, verbatim `[V]`: *"an adversary that can submit benign tasks and observe the
experiences distilled from its interactions, but cannot directly modify them. At the target stage,
the adversary issues a safety-sensitive query in a fresh session, where the preceding interaction
history is unavailable while the accumulated experiences persist."*

> **D23 is defeatable by construction, not merely blind to drift.** Sweep 1 §4.3(a) established
> that a per-diff classifier misses *gradual erosion*. This establishes that an *adversary who only
> has the ability to ask benign questions* can drive that erosion deliberately, in a system where
> each individual artifact passes review.
>
> **The unit of classification must change.** D23's *"change-classification function over spec
> diffs"* must be re-specified to operate on:
> - the **cumulative diff against a frozen baseline** (Sweep 1's conclusion), **and**
> - the **set of pending + recently-applied diffs jointly**, because the attack is a *composition*
>   of individually-low-risk changes.
>
> Concretely: run the classifier on `baseline → HEAD` and on `HEAD → HEAD + all pending`, not only
> on each diff; and hold safety invariants **outside** the optimiser's search space (the selfevo
> paper's principle 2, Sweep 1 §4.4), which for PACT means the policy contract must live in files
> the learning subsystem is structurally forbidden to write — an ACL on the tree, expressible in
> `workspace.yaml`, enforced by the loader.

---

## 17. Evaluation methodology — three results that change what the CTS must measure

### 17.1 SEA-Eval (arXiv 2604.08988v3) — equal scores, 31.2× cost

`papers/arxiv-2604.08988.pdf`. Fudan University. Abstract read from PDF `[V]`.

Verbatim `[V]`:
> *"Empirical evaluation reveals that, **under comparable success rates, token consumption differs
> by up to 31.2× between frameworks on individual tasks**, with divergent evolutionary trajectories
> emerging under sequential analysis—demonstrating that **success rate alone creates a capability
> illusion** and that the sequential convergence of T is the key criterion for distinguishing
> genuine evolution from pseudo-evolution."*

Design: *"through sequential task stream design, is designed to quantify evolutionary gain,
evolutionary stability, and implicit alignment convergence"*, with SR and T as primary metrics.

> **D27 is under-specified and this is the counterexample.** D27: *"Same eval scores within a
> declared small margin. This is the pass/fail rule of the Conformance Test Suite."* D26 separately
> asks for *"no meaningful token increase"* — but it is a *budget*, not a *gate*. A 31.2× token
> difference at equal accuracy is a conforming adapter under D27 and a catastrophe under D28-#3.
>
> **Make the CTS pass condition a conjunction:** score within ε **and** tokens/cost within a
> declared factor of the reference adapter. Report both in the Conformance Report. This is a
> one-line change to D27 with large consequences, and it is exactly the kind of thing that only
> shows up when someone measures it.
>
> **Second consequence, for learning (AC-5.4/5.5):** the paper's methodological claim is that
> *episodic* assessment cannot distinguish evolution from pseudo-evolution — you need a
> **sequential task stream**. PACT's learning gate is currently a single held-out comparison. Add a
> longitudinal arm: the same frozen stream replayed at generation *t* and *t−k*, which is also
> exactly the *"longitudinal monitoring replaces point-in-time evaluation"* defence principle from
> Sweep 1 §4.4. One mechanism satisfies both the safety requirement and the efficacy requirement.

### 17.2 CurveShift (arXiv 2608.00355, 2026-07-31) — the model/harness identification problem

`papers/arxiv-2608.00355.pdf`. Abstract read from PDF `[V]`.

Verbatim `[V]`:
> *"Isolating it is difficult on agentic benchmarks, because **newer models are usually run with
> newer agentic harnesses, so a gain on hard tasks cannot be assigned to the model or its
> scaffold**. We break the confound with LiveCodeBench, a public competitive programming benchmark
> that runs no agentic scaffold while pairing dated models with an exogenous difficulty ordering."*

Also verbatim `[V]`: *"most of the apparent shift in gains toward harder tasks does not reflect a
change in the shape of the difficulty-response curve… it is largely explained by ceiling effects
rather than a qualitative change in capability. This echoes how the choice of metric can make
claimed emergent abilities look like a property of the models themselves."* Residual effect after
control: *"about +0.40 logits… raising the hard-problem solve rate from roughly 18% to 25%"* for
models released after September 2024. Released artifact: LiveCodeBench Difficulty Panel,
66 dated models × 1,055 problems.

> **The Portability Report has this exact identification problem and currently reports a single
> delta.** PACT varies *both* model and strategy (which includes the harness) and then reports a
> score change. That number is not attributable. Two requirements:
> 1. **Report the 2×2, not the delta.** (reference model, reference strategy) · (reference model,
>    adapted strategy) · (target model, reference strategy) · (target model, adapted strategy). The
>    first three are cheap relative to the optimisation run and they are what makes the fourth
>    interpretable. This also gives the author the number they actually want — *"how much of the
>    recovery came from the optimiser vs. the model?"* — which is D11's recommendation logic.
> 2. **Stratify ε by difficulty.** The paper's point about ceiling effects applies directly to
>    `gap-r1-3.md`'s per-metric ε work: an aggregate score can be within ε while the hard stratum
>    has collapsed. Report ε bands per difficulty stratum where the eval set carries one.

### 17.3 Microsoft — *Who Belongs in the Eval Set?* (arXiv 2608.01004, 2026-08-02)

`papers/arxiv-2608.01004.pdf`. Sahu, Das, Mittal, Das (Microsoft + IIT Roorkee).
Applied to *"declarative agents with custom actions in Microsoft 365 Copilot"*. Read from PDF `[V]`.

Verbatim `[V]`:
> *"To the best of our knowledge, **no published industrial pipeline addresses this platform-side
> curation problem** — existing evaluation frameworks are customer-side, and benchmark-compression
> work treats benchmarks as fixed pools rather than streams of incoming sets."*

The governing philosophy, verbatim `[V]`:
> *"a healthy regression set is the **minimal collection of queries that captures the maximal spread
> of capability signatures** — distinct combinations of capabilities a query exercises together."*

Three components, verbatim `[V]`: *"a classifier producing per-(query, capability) verdicts via a
hybrid of deterministic specification-based extraction and large-language-model semantic inference;
an **Invocation Quality (IQ) rater** that scores how thoroughly a query exercises each capability,
so a new query sharing a signature with an existing entry can still be recognized as a better test
and displace it; and a consolidator that compares incoming queries against the regression set on
coverage and quality through a rule-based decision cascade, backed by a **conservative curator that
only suggests evictions**."* Per-query decisions: **admit, drop, swap, or human review**.

Why synthetic eval sets are ruled out, verbatim `[V]`:
> *"**Combinatorial blowup**: with ∼30 typed capabilities the joint configuration space is
> intractable, and uniform sampling produces configurations no real customer would ever build.
> **LLM non-determinism over realistic phrasings**: per-capability behavior is verified by unit and
> functional tests we run separately, but end-to-end agent behavior — multiple capabilities firing
> through an LLM under a real user's wording — is governed by how the LLM responds to actual
> customer phrasings, a distribution synthetic queries cannot reproduce."*

And the real constraint, verbatim `[V]`: *"**Hard eval-set ceiling.** The regression set is judged
by a large language model on every candidate release build and human-triaged on every regression
failure… Every admission competes for a finite slot bounded by release cadence. **Tenant-and-mock-
setup labor.** … Each admitted query therefore carries a provisioned tenant, synthetic connectors,
and mock data fixtures engineered to deterministically reproduce the expected 3P responses."*

> **Design consequences — this is the most directly transferable engineering in the sweep.**
> 1. **Adopt capability signatures as the admission policy for AC-4.4 (trace → eval promotion).**
>    PACT can compute a case's capability signature *for free and deterministically* from its IR —
>    which declared capabilities, tools and skills the trace exercised. That is a stronger position
>    than Microsoft's (they need an LLM classifier because their capability set is not declared in a
>    contract; PACT's is). The admission decision becomes `admit | drop | swap | human review` on
>    coverage + IQ, with **eviction suggest-only** — which is also D23's conservatism applied to the
>    eval set instead of the spec.
> 2. **Constrain D19.4 (builder-agent-generated evals).** Microsoft rules synthetic sets out for two
>    reasons that apply verbatim to PACT: combinatorial blowup over the declared capability
>    vocabulary, and phrasing-distribution mismatch. **Generated cases are coverage scaffolding;
>    real traces must dominate the oracle.** If the eval suite is majority-synthetic, T2's claim
>    that "the eval suite *is* the equivalence relation" is unfounded — the distribution is wrong.
>    This should be a *checked* property, not advice: report the synthetic/captured ratio in the
>    eval report.
> 3. **The eval suite needs a declared ceiling.** The binding constraint is not authoring effort
>    (R3's assumption) — it is per-case fixture labour and per-build judge cost. PACT's eval
>    document model should carry a budget (`maxCases`, or a cost ceiling) and the promotion pipeline
>    should respect it. This closes the same class of defect as `gap-r2-3.md`'s unbounded review
>    queue.
> 4. `[I]` The **IQ rater** concept — *how thoroughly* a case exercises a capability, so a better
>    case can displace an equivalent one — has no analogue in PACT and is worth one field. Without
>    it, a suite converges to "one case per signature" and stops improving.

---

## 18. Standards landscape — what changed since 2026-07-26

### 18.1 MCP `2026-07-28` shipped `[V for content via local draft; S for the release event]`

<https://blog.modelcontextprotocol.io/posts/2026-07-28/> `[S]` confirms the final release on
2026-07-28 after a 10-week validation window, with **all four Tier-1 SDKs (TypeScript, Python, Go,
C#) supporting it immediately and the Rust SDK in beta**. Sweep 1 §5 read the content from the
local draft spec and remains accurate. Two additions worth recording:

- **Header-based routing** `[S]`: *"Methods and tool names now travel in `Mcp-Method` and `Mcp-Name`
  HTTP headers, enabling gateway-level routing without JSON parsing."* Relevant to D24 — a PACT
  tool edge lowered onto MCP is now routable by a plain load balancer, which is what makes the
  "minimal, adapter-shaped" registry seam viable without PACT building routing.
- **Tasks is an extension, not core** `[V, Sweep 1 §5.2 item 6]`: `io.modelcontextprotocol/tasks`,
  alongside *"MCP Apps"* and *"Enterprise Managed Authorization (EMA)"* `[S]`.
  **OQ4 verdict:** the extension provides polling (`tasks/get`) and client input (`tasks/update`)
  but no durable-execution guarantees, no deterministic replay, no compensation. It is **strictly
  weaker than Temporal/Restate-class semantics** and cannot satisfy P-5 on its own. PACT should map
  *onto* it where a substrate offers only MCP, and declare that lowering `degraded`.
- The formal deprecation policy is confirmed as *"A twelve-month minimum window so you can plan
  upgrades instead of reacting to them"* `[S]` — Sweep 1 §5.4's recommendation to copy the model
  stands.

### 18.2 A2A `[S]`

v1.0 (March 2026) added **Signed Agent Cards** — *"each card includes a cryptographic signature
using the domain's public key, enabling receiving agents to verify the card was actually issued by
the claimed domain"*. **v1.0.1 (May 2026)** introduced an extension mechanism supporting *"new data,
requirements, RPC methods, and state machines"*, with four official example extensions:
**Secure Passport, Timestamp, Traceability, Agent Gateway Protocol**.
150+ organisations; Linux Foundation governance since 2025-06-23.

> `[I]` The A2A **extension** mechanism (state machines and RPC methods, not just data) is a better
> projection target than Sweep 1 assumed: PACT's contract fields that have no A2A card home (evals,
> SLOs, capability predicates) can be projected as a **named A2A extension** rather than dropped
> into the loss report. That converts a loss-report entry into a lossless projection, which is a
> strictly better outcome under T7. Worth one design spike against O6.2.

### 18.3 Vercel Eve — the docs **did** move (revises Sweep 1 §8) `[V]`

Sweep 1 concluded *"eve.dev/docs contains nothing the corpus lacks. Do not spend further web budget
here."* Twelve days later that is no longer true. Diffing `https://eve.dev/sitemap.md` against the
local checkout (HEAD `05f3480`, 2026-07-25, 83 doc files) `[V]`:

**New online, absent from the corpus:**
- `/docs/guides/acp` — **Agent Client Protocol v1 over stdio.** Verbatim: *"Agent Client Protocol
  (ACP) clients can launch an authored eve application as a local subprocess. eve serves stable ACP
  v1 over stdio while its normal development server remains the execution runtime."* CLI: `eve acp`,
  or `eve acp https://agent.example.com`. Transport: newline-delimited JSON-RPC. Documented
  non-support: *"a deployed ACP HTTP or WebSocket endpoint… ACP v2."* Zed integration config uses
  `agent_servers.<name>.{type,command,args,env}`.
- `/docs/guides/ucp` — **Universal Commerce Protocol** (<https://ucp.dev/>), *"an open standard for
  agentic commerce"*. Businesses *"declare support by serving a JSON profile from
  `/.well-known/ucp` containing spec versions, services, capabilities, payment handlers, and public
  keys for agent verification."* Fields named: `services[].endpoint`, `signing_keys`, a `ucp`
  response envelope. Profile must be HTTPS with no 3xx and `cache-control: public, max-age ≥ 60`.
- `/docs/channels/photon`, `/docs/install-integrations`, `/docs/installation`,
  `/docs/project-structure` (new, coexisting with `/docs/reference/project-layout`).
- Reorganised: `/docs/human-in-the-loop` (was `tools/human-in-the-loop`), `/docs/tools` (was
  `tools/overview`), `/docs/connections` (was `connections/overview`).

The integrations catalogue is now ~90 entries and includes eval vendors (`arize`, `braintrust`,
`hindsight`), tracing backends (`datadog`, `honeycomb`, `jaeger`, `sentry`, `posthog`) and memory
(`mem0`).

> **Design consequences.**
> 1. **Add ACP to PACT's projection list.** PACT currently names A2A cards and OSSA (O6.2). ACP is
>    the **editor/client edge** — the surface by which an authored agent becomes usable inside an
>    IDE. The corpus already has `protocols/agent-client-protocol`; the closest prior art has now
>    shipped it; and it is a stdio JSON-RPC surface, so it works **air-gapped** (unlike A2A over the
>    network). Under D18 ("files in an editor" is author surface #1) this is arguably the *most*
>    aligned projection PACT could offer.
> 2. **`/.well-known/<protocol>` + `signing_keys` is the shape for D24's discovery seam.** PACT
>    should not build a registry (D24), but it should be able to *emit* a signed, cacheable,
>    static capability profile that any registry can consume. That is a file, which fits D2 exactly,
>    and it is what both UCP and A2A signed cards converged on.
> 3. **Re-check `eve.dev` on every sweep.** The Sweep 1 "do not spend budget here" instruction was
>    wrong within two weeks. The `sitemap.md` diff is a ~1-minute check and should be standing.

### 18.4 Oracle Agent Spec — **no release since 26.1.2** `[V]`

<https://github.com/oracle/agent-spec/releases> lists 26.1.2 (2026-06-02), 26.1.0 (2026-01-16),
25.4.1 (2025-10-20) and nothing newer. The 26.1.2 notes claim *"Agent Spec Evaluation is now
available for framework-agnostic evaluation of agentic systems"* `[V]`.

> **Use this claim carefully — it is true and it is not a counter-example to T2.** Sweep 1 §1.4
> verified from source that `Metric` inherits `ABC`, not `Component`, and that there are exactly two
> built-in metrics. So Oracle ships a framework-agnostic evaluation **harness** whose metric
> definitions are Python and therefore **not part of the portable artifact**. Combined with §13.2's
> `runtime_deps` field, the summary is: *the runner is portable; the oracle is not.* That sentence
> is PACT's positioning against the closest competitor, and both halves are verified from source.

Also from 26.1.2, worth stealing `[V]`: *"LangGraph MCP remote transports now validate HTTPS
certificates by default"* and stdio transport *"blocked in loaders unless explicitly permitted"*;
`RetryPolicy`; **URL allow-lists** for `RemoteTool` and `ApiNode`. The loader-level transport block
and URL allow-list are exactly the shape PACT's policy contract needs for D16 (computer use) and
D17 (air-gap): *deny egress by default at the loader, allow-list in the policy file*.

### 18.5 Governance / regulatory `[S]`

- **EU AI Act full implementation: August 2026** — i.e. now. *"The first legally binding
  requirements applicable to high-risk agentic deployments."*
- **NIST**: AI Agent Standards Initiative launched 2026-02-17 (three pillars: industry-led
  standards, open-source protocol development, security-and-identity research). `NIST IR 8596`
  preliminary draft December 2025. **COSAiS** (SP 800-53 control overlays for AI agents) —
  concept paper Aug 2025, annotated outline Jan 2026, **overlays projected late 2026 → 2027**.
- **CSA**: AI Controls Matrix (AICM), MAESTRO threat modelling, agentic identity research; the
  four-phase rollout from Sweep 1 §2.4 (June 2026 → December 2027) is unchanged.

> Sweep 1's inference stands and strengthens: **no external policy/assurance schema will be stable
> enough to bind PACT's policy contract before 2027.** Define PACT's own vocabulary; treat
> NIST/CSA/EU-AI-Act as **projections**. But note the date: the EU AI Act obligations are live
> *now*, so the projection is no longer hypothetical for European users — the *audit trail* and
> *human oversight* fields are the ones to get right first, and PACT already has both (lineage,
> approval gates).

### 18.6 *Governance Gaps in Agent Interoperability Protocols* (arXiv 2606.31498, 2026-06-30)

`papers/arxiv-2606.31498.pdf`. Kang & Diponegoro, DoiT International. Read from PDF `[V]`.

Six-dimension governance taxonomy — **membership, deliberation, voting, dissent preservation,
human escalation, audit/replay** — applied to MCP v1.1, A2A v1.0.1, ACP, ANP and ERC-8004.

Verbatim `[V]`:
> *"The resulting gap matrix reveals that **voting and dissent preservation are universally absent
> across all five protocols**, deliberation is absent or at most partial, and no protocol encodes
> the full set of primitives required for governed agent communities. We distinguish extensible gaps
> (addressable through protocol extension mechanisms) from structural gaps (requiring a new
> architectural layer)… The analysis establishes that **agent community governance constitutes a
> missing architectural layer above current interoperability standards—not a missing feature within
> them**."*

> **Two uses.** (i) It is the citation for NG3 and for §1.3's table: MCP/A2A/ACP are transports and
> the gap is *structural*, not a feature request. (ii) **Dissent preservation is a primitive PACT
> could actually have and nobody does.** PACT's topology IR already includes debate and blackboard
> (AC-5.1). If a debate node's IR retains minority positions rather than only the resolved output,
> PACT can express something all five protocols provably cannot — and it costs one field in the
> node schema. `[I]` This is a cheap, defensible differentiator that also serves the audit
> requirement (EU AI Act, §18.5) and the learning-safety requirement (rejected candidates retained
> as negative evidence, AC-5.5) with the same mechanism.

### 18.7 Other competitors found

- **Swarm Skills** (arXiv 2605.10052v2, 2026-05-15), `papers/arxiv-2605.10052.pdf` `[V]`:
  *"a portable specification that extends the Anthropic Skills standard with multi-agent semantics…
  roles, workflows, execution bounds, and a built-in semantic structure for self-evolution"*,
  claiming *"zero-adapter cross-agent portability via progressive disclosure"*. Reference
  implementation: JiuwenSwarm. Self-evolution scores on **Effectiveness, Utilization, Freshness**.
  Critically, verbatim: *"eliminating the need for **human-in-the-loop oversight** during the
  refinement process."*
  > `[I]` A fourth entrant in PACT's exact space, weaker on every contract axis (no evals, no model
  > capability, no SLOs) — but it names two things PACT lacks vocabulary for: **execution bounds**
  > as a first-class skill field, and **Freshness** as a retirement signal (which is exactly the
  > retirement criterion §16.1 says PACT needs). Its explicit removal of human oversight is the
  > direct negation of D23 and makes it the cleanest available contrast case.
- **Open Agent Format (OAF)** v0.8.0, January 2026 — <https://openagentformat.com/> now reachable
  `[V, site prose]`. Single `AGENTS.md` with YAML frontmatter; required metadata `name`,
  `vendorKey`, `agentKey`, `version`, `slug`, `description`, `author`, `license`, `tags`. Composes
  skills, MCP servers, sub-agent delegation; semantic versioning; capability filtering for tool
  access. Design statement, verbatim: *"The directory structure and files define the agent - no
  hidden state or configuration."* Targets Claude Code, Goose, Deep Agents, Letta. Self-assessed
  adoption: *"most platforms haven't fully integrated OAF yet."* **No evals, no model selection, no
  topology, no capability requirements.**
  > Confirms Sweep 1 §2.5's assessment, and note the design statement is *the same statement PACT
  > makes* (D2). Two independent formats reached "the tree is the agent"; neither carries a
  > contract. **Filesystem-native is becoming table stakes; the contract is the differentiator.**

---

## 19. `PACT` is now a contested name (D1 risk)

Sweep 1 §1.6 catalogued four things called "Agent Spec" and concluded *"PACT's distinct name is an
asset."* Three collisions found this sweep make that conclusion false.

| Claimant | Expansion | Backing | Date | Domain |
|---|---|---|---|---|
| **PACT** | **Private Access Control Tokens** | **Cloudflare, Google (Chrome), Microsoft (Edge), Mozilla (Firefox), Shopify**; *"plan to develop the protocol and submit it for standardization"* | announced **2026-06-25** `[S]` | Distinguishing **user-backed AI agents** from malicious bots via anonymous tokens |
| **PACT5** | **Protocol for Agent Coordination and Trust** | pact5.io (host unreachable from this environment; description via search) | 2026 `[S]` | *"how agents coordinate, how authority is scoped and delegated, and how humans maintain control"* — **multi-agent governance** |
| **pact** | — | `github.com/P-A-C-T-Protocol/pact` | 2026 `[S]` | agent payments |

Source: <https://securityboulevard.com/2026/06/new-pact-protocol-could-help-sites-distinguish-user-backed-ai-agents-from-malicious-bots/> `[S]`
(a second search result gave 2026-06-22 rather than 06-25 for the announcement; treat the date as
±3 days).

> **This is a decision, not an observation.** D1 states the name is *"Permanent and user-facing (not
> a placeholder)"*. The strongest collision — Private Access Control Tokens — is (a) in the AI-agent
> space, (b) backed by all three major browser vendors plus Cloudflare, (c) heading for a standards
> body, and (d) six weeks old, so its search footprint is still growing. PACT5 collides on
> *semantics* as well as name: "coordination and trust" for multi-agent systems with human control
> is a description a reader could mistake for this project.
>
> Three options, in increasing cost: (1) keep `PACT` and always write it with the expansion
> *Portable Agent Contract & Topology* plus a disambiguation note in README and docs — cheap, and
> what the Agent-Spec collision already required; (2) keep the CLI `pact` but namespace the spec as
> `pact.dev/v1` and lead with the domain — already the plan, and `pact.dev` is the real
> differentiator if it is held; (3) rename. **The one thing not to do is nothing**, because D1
> currently records a conclusion (name is an asset) that the evidence no longer supports.
> `[I]` Recommendation: option (1)+(2), plus an explicit "Naming" section in the public README
> disambiguating against PACT (tokens), PACT5, Oracle Agent Spec, AgentSPEX, AgentSpec (runtime
> enforcement) and `pydantic_ai.AgentSpec`. Revisit if the Cloudflare proposal reaches an IETF WG.

---

## 20. Framework docs — adapter constraints not visible from source

### 20.1 Claude Agent SDK: Skills are filesystem-only, and exposure is not isolation `[V]`

<https://code.claude.com/docs/en/agent-sdk/skills> (301 from `docs.claude.com`, 307 from
`platform.claude.com`). All quotes verbatim.

> *"Unlike subagents (which can be defined programmatically), **Skills must be created as filesystem
> artifacts. The SDK does not provide a programmatic API for registering Skills.**"*

> *"The `skills` option is **a context filter, not a sandbox**. Unlisted Skills are hidden from the
> model and rejected by the Skill tool, but **their files remain on disk and are reachable through
> Read and Bash**."*

> *"The `allowed-tools` frontmatter field in SKILL.md is only supported when using Claude Code CLI
> directly. **It does not apply when using Skills through the SDK.**"*

Mechanics `[V]`: skills load from `~/.claude/skills/`, `<cwd>/.claude/skills/` and `.claude/skills/`
in any parent up to the repo root, governed by `settingSources` (TS) / `setting_sources` (Py) which
must include `'user'` or `'project'`; the `plugins` option loads skills *"from a specific path"*.
`skills` accepts `"all"`, a name list, or `[]`. Names must be exact — wildcards, empty names,
padded names, and names with parens/commas/control chars raise before the process starts. The
`init` system message carries a `skills` array listing **user-invocable skills only**
(`user-invocable: false` skills load but are omitted).

> **Three capability-lattice rows, and one architectural note.**
> | PACT feature | Claude Agent SDK lowering | Lattice |
> |---|---|---|
> | skill definition | must be **materialised to a scratch tree**; use the `plugins` option to point at a PACT-generated directory rather than polluting the user's `.claude/` | `native` (via materialisation) |
> | skill **exposure set** (a Strategy field; the in-repo finding is that curated exposure is worth real accuracy) | context filter only — files stay readable via `Read`/`Bash` | **`degraded`** — must be reported |
> | per-skill **tool restriction** | `allowed-tools` is ignored by the SDK | **`unsupported`** — must be reported; PACT must enforce it harness-side or refuse |
>
> **The architectural note matters for P-1.** AC-2.3 says *"No adapter reads author files; adapter
> tests pass with only `canonical.json` present."* That invariant is about *reading*. This substrate
> forces the adapter to **write** a derived tree. That is compatible — the tree is generated *from*
> `canonical.json`, not read from the author's source — but the invariant should say so explicitly,
> because "the adapter touches the filesystem" will otherwise read as a violation. Suggested
> wording: *adapters may materialise derived artifacts under `.pact/build/<adapter>/`; they may not
> read the author tree.*

### 20.2 OpenAI Agents SDK `[S]`

*"a model-native harness that lets agents work across files and tools on a computer, plus native
sandbox execution for running that work safely"*; **subagents** and **"code mode"** for Python and
TypeScript announced as *"still coming soon"*; *"works with more than 100 other LLMs through the
Chat Completions API"*. Deprecation status unchanged from Sweep 1 §2.1: Agent Builder shuts down
2026-11-30; **ChatKit survives** but *"needs a backend you control (the Advanced integration path)
once the OpenAI-hosted Agent Builder backend is gone"*.

> `[I]` The ChatKit outcome is the crispest statement of the pattern PACT is betting on: the **UI
> survives, the hosted backend dies, and the replacement is a backend you own defined by files in
> your repo.** That is D18/NG4 written as a migration guide by the vendor that killed its own
> canvas.

### 20.3 LangChain `deepagents` `[S]`

Standalone library, *"an agent harness"*, on LangChain building blocks + LangGraph runtime for
*"durable execution, streaming, human-in-the-loop"*. Middleware for history compression, tool-result
offload, subagent context isolation, prompt caching. **Declarative synchronous subagent specs** and
**declarative permission rules** controlling *"which files and directories the agent can read or
write"*. Releases page updated 2026-06-30. **Not in the local corpus** (see §11.4).

> **Action:** clone `langchain-ai/deepagents` before finalising the LangGraph adapter. Sweep 1
> concluded harness lowering via `langgraph.func` is *"actually better than native"*; `deepagents`
> is the vendor's own answer to the same question and its middleware set is a ready-made map for
> PACT's context-discipline fields (§7.3 mechanism 4). Its **declarative permission rules** are also
> the closest existing analogue to PACT's policy contract on the file-access axis.

---

## 21. Negative findings (Sweep 2)

1. **No agent specification has added evals-in-the-artifact.** Checked this sweep: Oracle Agent Spec
   (no release since 26.1.2; metrics still Python), OASF (results record only, §13.1), Microsoft
   Agent Framework (absent from both declarative surfaces, §12.3), OAF (absent), Swarm Skills
   (absent), Pydantic AI `AgentSpec` (absent, re-verified). **T2 remains unclaimed as of 2026-08-07.**
2. **No specification has model-capability requirements.** Every format still binds a literal model
   id (or an env expression, in MAF's case). O3.1 remains unclaimed.
3. **No conformance test suite exists for any agent spec.** Unchanged from Sweep 1 §9.5.
4. **DeepEval still has no YAML/config-only mode** — verified against the 2026 changelog, not just
   the docs index (§14.5).
5. **No published evidence that non-programmers can author agents declaratively.** Nothing found
   this sweep changes Sweep 1 §9.3. Note that Microsoft's declarative-workflow docs *assert* the
   claim (*"easy to understand, even for non-developers"*) without a study. AC-1.5 remains novel.
6. **`optimize_anything`'s suitability as the E-5 ABI is still unsettled** (OQ7 carried forward) —
   but a shipping alternative (DeepEval's) was found and is too narrow (§14.4).
7. **The Outshift/AGNTCY blog body remains unretrievable** through WebFetch after a second attempt;
   OQ1 was answered from the local schema instead, which is better evidence anyway.
8. **`pact5.io` was unreachable** from this environment (DNS timeout); §19's PACT5 description is
   secondary-source only.
9. **No 2026 "universal agent format" postmortem exists.** Same conclusion as Sweep 1 §9.4, now with
   more data points: the formats do not get repudiated, they get *ignored* (OAF's own
   *"most platforms haven't fully integrated OAF yet"*), while the *hosted products* get formally
   deprecated. The failure mode to design against is **irrelevance**, not rejection — which makes
   D28's list incomplete: "nobody adopts it" is a real failure mode even though D10/D28 rank
   external adoption as non-critical.

---

## 22. Open questions carried forward

1. `optimize_anything` (arXiv 2605.19633) vs PACT's E-5 ABI — unread. (Carried from Sweep 1 OQ7.)
2. Does `langchain-ai/deepagents`' middleware set map 1:1 onto PACT's context-discipline strategy
   fields? Needs a source read after cloning (§20.3).
3. Does the CMU harness optimiser (`malusamayo/migration-analysis`) hold out a test split, and what
   is its search space? If it optimises instructions + tools + loop jointly, it is the closest
   existing implementation of PACT's Resolver and should be read before O3.4 is finalised.
4. Can the **workflow-diversity metric** (normalised Levenshtein over tool-call sequences) be
   computed from PACT eval cases *without executing them*? If yes, F8's pre-flight predicate is
   nearly free; if it needs a trace, it costs one baseline run. This is a cheap experiment and it
   gates a design decision.
5. Does A2A v1.0.1's extension mechanism admit **non-invocation** payloads (an eval suite, an SLO
   block) or only protocol extensions? Determines whether O6.2 is lossless (§18.2).
6. What exactly does MAF's `safe_mode` parameter on `create_agent_from_yaml` control? The example
   passes `safe_mode=False` without explanation. If it gates expression evaluation, it is the
   nearest existing prior art for PACT's "config-only must not be a code-execution surface"
   requirement.
7. Is the Cloudflare PACT proposal on an IETF track yet, and under what name? Determines whether
   §19 option (1) or option (3) is required.
8. SEA-Eval's 31.2× token spread: which frameworks, on which tasks? The exact pair matters for
   setting the CTS cost bound in D27 (§17.1).

---

## Appendix A-II — files added by Sweep 2

Papers, all to `/home/bud/ditto/agent-inter-op/research/papers/`:

| File | Paper | Date |
|---|---|---|
| `arxiv-2607.08938.pdf` | *Better Harnesses, Smaller Models: Building 90% Cheaper Agents via Automated Harness Adaptation* (CMU) | 2026-07-09 |
| `arxiv-2605.12129.pdf` | *It's Not the Size: Harness Design Determines Operational Stability in Small Language Models* | 2026-05-12 |
| `arxiv-2608.04968.pdf` | *EvolveNet: Collaborative Harness Evolution for Agent Self-Improvement* | 2026-08-05 |
| `arxiv-2607.13083.pdf` | *Phantom Guardrails: When Self-Improving Agent Harnesses Fix Failures That Never Happened* (CMU) | 2026-07-13 |
| `arxiv-2608.03509.pdf` | *SkillJack: Persistent Skill Backdoors in Self-Evolving Agents* (Tencent) | 2026-08-04 |
| `arxiv-2608.01759.pdf` | *Benign Alone, Harmful Together: Exploiting Experience Composition in Self-Evolving LLM Agents* (EvoBreak) | 2026-08-03 |
| `arxiv-2604.08988.pdf` | *SEA-Eval: A Benchmark for Evaluating Self-Evolving Agents Beyond Episodic Assessment* (Fudan) | v3 2026-05-24 |
| `arxiv-2608.01004.pdf` | *Who Belongs in the Eval Set? A Capability-Taxonomy-Driven Pipeline…* (Microsoft) | 2026-08-02 |
| `arxiv-2606.31498.pdf` | *Governance Gaps in Agent Interoperability Protocols: What MCP, A2A, and ACP Cannot Express* | 2026-06-30 |
| `arxiv-2605.10052.pdf` | *Swarm Skills: A Portable, Self-Evolving Multi-Agent System Specification* | v2 2026-05-15 |
| `arxiv-2608.00355.pdf` | *CurveShift: Is Agent Progress Scalar? Separating Level from Shape* | 2026-07-31 |

No repositories cloned this sweep. **Recommended clone:** `langchain-ai/deepagents` (§20.3).

## Appendix B-II — primary URLs cited in Sweep 2

- <https://learn.microsoft.com/en-us/agent-framework/workflows/declarative>
- <https://learn.microsoft.com/en-us/agent-framework/agents/declarative>
- <https://pydantic.dev/docs/ai/harness/>
- <https://pydantic.dev/docs/ai/agent-spec/>
- <https://code.claude.com/docs/en/agent-sdk/skills> (via 301 `docs.claude.com` → 307 `platform.claude.com`)
- <https://docs.langchain.com/oss/python/deepagents/overview>
- <https://eve.dev/sitemap.md>, <https://eve.dev/docs/guides/acp>, <https://eve.dev/docs/guides/ucp>
- <https://ucp.dev/>
- <https://blog.modelcontextprotocol.io/posts/2026-07-28/>
- <https://github.com/oracle/agent-spec/releases>
- <https://deepeval.com/changelog/changelog-2026>
- <https://openagentformat.com/>
- <https://openai.com/index/the-next-evolution-of-the-agents-sdk/>
- <https://securityboulevard.com/2026/06/new-pact-protocol-could-help-sites-distinguish-user-backed-ai-agents-from-malicious-bots/>
- <https://arxiv.org/abs/2607.08938>, <https://arxiv.org/abs/2605.12129>, <https://arxiv.org/abs/2608.04968>, <https://arxiv.org/abs/2607.13083>, <https://arxiv.org/abs/2608.03509>, <https://arxiv.org/abs/2608.01759>, <https://arxiv.org/abs/2604.08988>, <https://arxiv.org/abs/2608.01004>, <https://arxiv.org/abs/2606.31498>, <https://arxiv.org/abs/2605.10052>, <https://arxiv.org/abs/2608.00355>
- <https://github.com/malusamayo/migration-analysis> (CMU harness optimiser)
- <https://github.com/junnie00/EvolveNet>
- <https://github.com/Tencent/AI-Infra-Guard/research/skilljack>

Local sources read (not URLs): `research/repos/protocols/agntcy-oasf/schema/**` (HEAD `e856537`,
2026-07-21), `research/repos/eval/deepeval/deepeval/optimizer/**` (HEAD `6cf2e02`, 2026-07-22),
`research/repos/frameworks/vercel-eve` (HEAD `05f3480`, 2026-07-25),
`research/repos/frameworks/langchain/libs/` (deepagents absent).
