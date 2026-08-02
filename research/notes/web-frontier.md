# Research stream: web-frontier

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
