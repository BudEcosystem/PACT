# DeepEval Feature Surface — Complete Source Inventory

**Research stream:** `deepeval-surface`
**Sizes:** AC-4.1 (published coverage matrix, every DeepEval metric, config-only expression),
AC-4.2 (no eval requires code), AC-4.5 (deterministic-first), O4.1–O4.4, E-4, D6, D14, D19.
**Date:** 2026-08-07.

**Source read:** `/home/bud/ditto/agent-inter-op/research/repos/eval/deepeval`
at commit `6cf2e02` ("Merge pull request #2930 …"), package version **4.1.3**
(`deepeval/_version.py:1`). All paths below are relative to that repo root unless
absolute. Cross-checks against `research/repos/eval/ragas`,
`research/repos/eval/promptfoo`, `research/repos/eval/inspect_ai`.

**Method.** Every metric class was extracted from source by AST
(`ClassDef` → `__init__` signature + defaults + `_required_params` class attribute),
not from docs. Score-direction and `strict_mode` semantics were read from the
`is_successful()` and `_calculate_score()` bodies, because **the constructor
signature does not reveal them**. Docs were used only to confirm that the source
inventory and the published inventory agree (they do — see §11).

---

## 0. Executive summary — the five things that change the PACT design

1. **DeepEval has no config format at all.** There is no YAML, no JSON, no TOML
   metric declaration anywhere in the package (`grep -rn "yaml" --include=*.py deepeval/`
   returns nothing). Every metric is a Python constructor call. The *only*
   serialisation surface in the entire metric layer is the DAG serializer
   (`deepeval/metrics/dag/serialization/serialization.py`), which happens to
   contain a **general metric descriptor**:
   `{"type": "metric", "metric_class": "<ClassName>", "kwargs": {...}}`
   (`serialization.py:23`, `:316-340`, `:507-534`). PACT should adopt exactly this
   shape as its normative metric descriptor, because it is (a) already implemented
   upstream, (b) already round-trip tested upstream, and (c) already the way
   DeepEval reconstructs a metric from data.
2. **47 of 49 exported metrics are expressible purely in config.** Only two need a
   non-JSON constructor argument: `DAGMetric`/`ConversationalDAGMetric` (`dag:`
   object — but there is an official JSON codec, so it *is* config-only) and
   `JsonCorrectnessMetric` (`expected_schema:` pydantic class — but only
   `.model_validate_json()` and `.model_json_schema()` are ever called, so a
   JSON-Schema block suffices). **Config-only parity at 100% is achievable**, which
   is a stronger claim than the thesis assumed.
3. **Five metrics require an execution trace, not a test case**
   (`TaskCompletion`, `PlanQuality`, `PlanAdherence`, `StepEfficiency`,
   `AgentLoopDetection` — all set `self.requires_trace = True`). They read
   `LLMTestCase._trace_dict`, a private attribute populated only by DeepEval's own
   `@observe` instrumentation. **The PACT harness must emit a DeepEval-shaped trace
   dict** or these five metrics — the entire agentic family — are unreachable. This
   is a hard requirement on the harness-lowering contract (D12/T3), not an eval
   detail.
4. **DeepEval has zero SLO / latency / cost / percentile assertions.**
   `LLMTestCase.token_cost` and `.completion_time` exist
   (`test_case/llm_test_case.py:385-394`) but **no metric consumes them** — they are
   only forwarded to the Confident AI API (`test_case/api.py:111-112`). O4.2 has no
   DeepEval ancestor; promptfoo is the correct model (§9).
5. **Two silent-correctness hazards must be neutralised in the PACT layer:**
   (a) score direction is per-metric and undeclared — four metrics are
   *lower-is-better* (`score <= threshold`) while the other 45 are
   *higher-is-better*; (b) `RoleViolationMetric` with `strict_mode=True`
   **always passes** (verified bug, §4.3). A non-technical author writing
   `threshold: 0.8` cannot know which direction it means. PACT must carry
   `direction` in its metric catalogue and normalise.

---

## 1. Inventory scope and counts

| Group | Count | Where |
|---|---|---|
| Exported metric classes (`deepeval.metrics.__all__` minus 3 base classes and `DeepAcyclicGraph`) | **49** | `deepeval/metrics/__init__.py:71-136` |
| Community metric (separate export path) | 1 (`CitationFaithfulnessMetric`) | `deepeval/metrics/community/__init__.py:1-7` |
| Legacy Ragas wrappers (present, **not** in `__all__`, require `langchain_core`) | 6 | `deepeval/metrics/ragas.py:38,119,192,342,424,496` |
| **Total metric classes in the Python package** | **56** | |
| Metric classes in the TypeScript package | 44 | `typescript/src/metrics/index.ts` |
| Benchmarks (separate subsystem) | 17 | `deepeval/benchmarks/__init__.py:19-37` |
| Base classes | 3 (`BaseMetric`, `BaseConversationalMetric`, `BaseArenaMetric`) | `deepeval/metrics/base_metric.py:44,108,174` |

**Red teaming is gone.** `deepeval/red_teaming/README.md` (whole file):
> "The Red Teaming module is now in DeepTeam for deepeval-v3.0 onwards.
> Please go to https://github.com/confident-ai/deepteam to get the latest version."

There is **no** red-team / attack-generation surface left in DeepEval 4.x. Any
PACT claim of "DeepEval parity including red teaming" would be false; red teaming
is a separate package (`deepteam`) and is **not in the 141-repo corpus**, so it
has not been read and must not be assumed.

**Guardrails are gone too.** No `guardrails` module exists anywhere under
`deepeval/` (`ls deepeval | grep -i guard` → empty;
`find . -iname "*guardrail*" -maxdepth 3` → empty). The only "guardrail" in the
eval corpus is promptfoo's `guardrails` assertion type
(`promptfoo/src/assertions/guardrails.ts`). PACT's policy/guardrail contract has
**no DeepEval ancestor** and must be designed from the policy side, not the eval side.

---

## 2. The test-case data model (what a metric can read)

### 2.1 `LLMTestCase` — single-turn (`deepeval/test_case/llm_test_case.py:344-422`)

| Field | Type | Notes |
|---|---|---|
| `input` | `str` **(only required field)** | line 347 |
| `actual_output` | `Optional[str]` | 348 |
| `expected_output` | `Optional[str]` | 353 |
| `context` | `Optional[List[str]]` | 358 — ground truth |
| `retrieval_context` | `Optional[List[str \| RetrievedContextData]]` | 361 — what RAG retrieved |
| `metadata` | `Optional[Dict]` | 366 (alias `additional_metadata`, deprecated) |
| `tools_called` | `Optional[List[ToolCall]]` | 372 |
| `expected_tools` | `Optional[List[ToolCall]]` | 380 |
| `comments` | `Optional[str]` | 377 |
| `token_cost` | `Optional[float]` | 385 — **no metric reads this** |
| `completion_time` | `Optional[float]` | 390 — **no metric reads this** |
| `multimodal` | `bool` (auto-detected) | 395, validator at 442-478 |
| `name`, `tags` | `Optional[str]`, `Optional[List[str]]` | 396-397 |
| `mcp_servers` | `Optional[List[MCPServer]]` | 398 |
| `mcp_tools_called` / `mcp_resources_called` / `mcp_prompts_called` | `Optional[List[MCP*Call]]` | 399-408 |
| `custom_column_key_values` | `Optional[Dict[str,str]]` | 409 |
| `_trace_dict` | `PrivateAttr(Optional[Dict])` | **416** — the trace hook |

`SingleTurnParams` enum (`llm_test_case.py:179-192`) — the addressable field set for
`GEval.evaluation_params` and every `_required_params`: `input`, `actual_output`,
`expected_output`, `context`, `retrieval_context`, `metadata`, `tags`,
`tools_called`, `expected_tools`, `mcp_servers`, `mcp_tools_called`,
`mcp_resources_called`, `mcp_prompts_called`.

`ToolCall` (`llm_test_case.py:247-257`): `name: str`, `type: FUNCTION|MCP`,
`description`, `reasoning`, `output: Any`, `input_parameters: Dict`. **Fully
JSON-expressible.**

### 2.2 Multimodal is now *in-band*, not a separate test case

There is no `MLLMTestCase` in 4.1.3. Images are `MLLMImage` dataclasses
(`llm_test_case.py:39-176`) that stringify to a sentinel
`[DEEPEVAL:IMAGE:<uuid>]` / `[DEEPEVAL:PDF:<uuid>]` (`:101-113`) embedded in any
string field, resolved through a module-global registry `_MLLM_IMAGE_REGISTRY`
(`:31`, `:88`). `LLMTestCase.multimodal` is auto-set by regex-scanning
`input`/`actual_output`/`expected_output`/`context`/`retrieval_context`
(`:442-478`).

`MLLMImage` accepts `url=` (local path, `file://`, or `http(s)://`) or
`dataBase64=`+`mimeType=`. **Local paths and base64 work fully offline**
(`:68-76` loads and b64-encodes from disk); only `http(s)://` URLs are deferred
(`:86` sets `dataBase64 = None`).

> **Design consequence.** A PACT eval case written in YAML can carry an image as a
> relative path in the case directory. The provider constructs `MLLMImage(url=…)`
> and substitutes the sentinel into the string field. This is *directly compatible*
> with the Expansion Rule: `input/` as a directory holding `text.md` + `figure.png`
> folds into one string with one sentinel. No new mechanism is needed. **But the
> registry is a module-global keyed by a fresh `uuid4` per construction
> (`:46`), so the sentinel is not stable across processes** — PACT must construct
> images in the same process that runs the metric, i.e. inside the provider, never
> serialise a sentinel into `canonical.json`.

### 2.3 `ConversationalTestCase` (`deepeval/test_case/conversational_test_case.py:190-222`)

`turns: List[Turn]` (required, non-empty — validator at `:290`), plus `scenario`,
`context`, `name`, `user_description`, `expected_outcome`, `chatbot_role`,
`metadata`, `comments`, `tags`, `mcp_servers`, `multimodal`.

`Turn` (`:59-81`): `role: Literal["user","assistant"]`, `content: str`, `user_id`,
`retrieval_context`, `tools_called`, `mcp_*_called`, `metadata`. All JSON.

`MultiTurnParams` (`:30-44`): `role`, `content`, `metadata`, `tags`, `scenario`,
`expected_outcome`, `context`, `user_description`, `retrieval_context`,
`chatbot_role`, `tools_called`, `mcp_tools_called`, `mcp_resources_called`,
`mcp_prompts_called`.

### 2.4 `ArenaTestCase` (`deepeval/test_case/arena_test_case.py:19-45`)

`contestants: List[Contestant]`, where `Contestant = {name, test_case: LLMTestCase,
hyperparameters}`. Post-init enforces unique names and **identical `input` and
`expected_output` across all contestants** (`:26-42`). Fully JSON-expressible.

---

## 3. THE COMPLETE METRIC TABLE

Legend for **Config-only?**
- **YES** — every constructor argument is a JSON scalar/list/dict; nothing to write.
- **YES\*** — config-only *given a PACT-side construct named in the last column*.
- **TRACE** — config-only, but requires the harness to supply an execution trace.

Legend for **Dir**: `↑` = higher is better (`score >= threshold`);
`↓` = lower is better (`score <= threshold`).
**Strict** = what `strict_mode=True` does to the threshold.

`async_mode` defaults to `True` on every LLM-judged metric. Metrics marked
*(det.)* invoke no LLM.

### 3.1 RAG metrics

| Metric | Required test-case fields | Required ctor args | Optional ctor args (defaults) | Dir | Strict | Config-only? | Evidence |
|---|---|---|---|---|---|---|---|
| `AnswerRelevancyMetric` | `input`, `actual_output` | — | `threshold=0.5`, `model=None`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | ↑ | thr→1 | **YES** | `metrics/answer_relevancy/answer_relevancy.py:26,32` |
| `FaithfulnessMetric` | `input`, `actual_output`, `retrieval_context` | — | + `truths_extraction_limit=None`, `penalize_ambiguous_claims=False` | ↑ | thr→1 | **YES** | `metrics/faithfulness/faithfulness.py:51,58` |
| `ContextualPrecisionMetric` | `input`, `retrieval_context`, `expected_output` | — | standard 6 | ↑ | thr→1 | **YES** | `metrics/contextual_precision/contextual_precision.py:45,52` |
| `ContextualRecallMetric` | `input`, `retrieval_context`, `expected_output` | — | standard 6 | ↑ | thr→1 | **YES** | `metrics/contextual_recall/contextual_recall.py:57,65` |
| `ContextualRelevancyMetric` | `input`, `retrieval_context` | — | standard 6 | ↑ | thr→1 | **YES** | `metrics/contextual_relevancy/contextual_relevancy.py:59,65` |
| `CitationFaithfulnessMetric` *(community)* | `input`, `actual_output`, `retrieval_context` | — | `threshold=1.0` + standard 5 | ↑ | thr→1 | **YES** | `metrics/community/citation_faithfulness/citation_faithfulness.py:23,50` |

"standard 6" = `threshold=0.5, model=None, include_reason=True, async_mode=True,
strict_mode=False, verbose_mode=False`.

### 3.2 Content-quality metrics

| Metric | Required fields | Required ctor | Optional | Dir | Strict | Config-only? | Evidence |
|---|---|---|---|---|---|---|---|
| `HallucinationMetric` | `input`, `actual_output`, **`context`** | — | standard 6 | **↓** | **thr→0** | **YES** | `metrics/hallucination/hallucination.py:25,32`; dir at `:258` |
| `SummarizationMetric` | `input`, `actual_output` | — | `threshold=0.5`, `n=5`, `model=None`, `assessment_questions=None`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False`, `truths_extraction_limit=None` | ↑ | thr→1 | **YES** | `metrics/summarization/summarization.py:36,43` |
| `BiasMetric` | `input`, `actual_output` | — | standard 6 | **↓** | **thr→0** | **YES** | `metrics/bias/bias.py:26,32`; dir at `:290` |
| `ToxicityMetric` | `input`, `actual_output` | — | standard 6 | **↓** | **thr→0** | **YES** | `metrics/toxicity/toxicity.py:26,33`; dir at `:287` |

### 3.3 Safety / compliance metrics

| Metric | Required fields | Required ctor | Optional | Dir | Strict | Config-only? | Evidence |
|---|---|---|---|---|---|---|---|
| `PIILeakageMetric` | `input`, `actual_output` | — | standard 6 | ↑ | thr→1 | **YES** | `metrics/pii_leakage/pii_leakage.py:26,32`; dir `:282` |
| `NonAdviceMetric` | `input`, `actual_output` | **`advice_types: List[str]`** (raises if empty, `:47-53`) | standard 6 | ↑ | thr→1 | **YES** | `metrics/non_advice/non_advice.py:29,35` |
| `MisuseMetric` | `input`, `actual_output` | **`domain: str`** | standard 6 | **↓** | **thr→0** | **YES** | `metrics/misuse/misuse.py:26,32`; dir `:285` |
| `RoleViolationMetric` | `input`, `actual_output` | **`role: str`** (declared `= None` but raises if `None`, `:43-46`) | standard 6 | ↑ | **thr→0 — BUG, §4.3** | **YES** | `metrics/role_violation/role_violation.py:26,32,47,295` |
| `ToolPermissionMetric` *(det.)* | `tools_called` | **`allowed_tools` or `denied_tools`** (raises if both `None`, `:43-48`) | `threshold=1.0`, `include_reason=True`, `strict_mode=False`, `verbose_mode=False` | ↑ | thr→1.0 | **YES** | `metrics/tool_permission/tool_permission.py:12,34` |
| `RoleAdherenceMetric` *(conversational)* | `role`, `content` turns + `chatbot_role` | — | standard 6 | ↑ | thr→1 | **YES** | `metrics/role_adherence/role_adherence.py:22,25` |

### 3.4 Task-specific metrics

| Metric | Required fields | Required ctor | Optional | Dir | Strict | Config-only? | Evidence |
|---|---|---|---|---|---|---|---|
| `ToolCorrectnessMetric` | `input`, `tools_called`, `expected_tools` | — | `available_tools=None`, `threshold=0.5`, `evaluation_params: List[ToolCallParams]=[]`, `model=None`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False`, `should_exact_match=False`, `should_consider_ordering=False` | ↑ | thr→1 | **YES** | `metrics/tool_correctness/tool_correctness.py:24,32` |
| `ArgumentCorrectnessMetric` | `input`, `tools_called` | — | standard 6 | ↑ | thr→1 | **YES** | `metrics/argument_correctness/argument_correctness.py:26,32` |
| `JsonCorrectnessMetric` | `input`, `actual_output` | **`expected_schema: BaseModel`** | `model=None`, `threshold=0.5`, `async_mode=True`, `include_reason=True`, **`strict_mode=True`**, `verbose_mode=False` | ↑ | thr→1 | **YES\*** | `metrics/json_correctness/json_correctness.py:24,30` |
| `PromptAlignmentMetric` | `input`, `actual_output` | **`prompt_instructions: List[str]`** | standard 6 | ↑ | thr→1 | **YES** | `metrics/prompt_alignment/prompt_alignment.py:27,34` |
| `KnowledgeRetentionMetric` *(conv.)* | turns | — | standard 6 | ↑ | thr→1 | **YES** | `metrics/knowledge_retention/knowledge_retention.py:23,26` |
| `ExactMatchMetric` *(det.)* | `input`, `actual_output`, `expected_output` | — | `threshold=1`, `verbose_mode=False` | ↑ | n/a | **YES** | `metrics/exact_match/exact_match.py:12,19` |
| `PatternMatchMetric` *(det.)* | `input`, `actual_output` | **`pattern: str`** (regex, compiled at init `:31-35`) | `ignore_case=False`, `threshold=1.0`, `verbose_mode=False` | ↑ | n/a | **YES** | `metrics/pattern_match/pattern_match.py:13,19` |

`JsonCorrectnessMetric` is **YES\*** only: `expected_schema` is used solely via
`.model_validate_json()` (`:87`, `:137`) and `.model_json_schema()` (`:168`, `:193`).
A PACT provider can build a pydantic model from an author-written JSON Schema at
load time; no author code needed.

`PatternMatchMetric` uses `fullmatch` (`:59`), **not** `search`. Authors writing
`pattern: "refund"` will get 0.0 on every non-trivial output. PACT must either
document this loudly or expose `mode: full|contains|search`.

### 3.5 Agentic metrics (all five trace-requiring ones live here)

| Metric | Required fields | Required ctor | Optional | Dir | Config-only? | Evidence |
|---|---|---|---|---|---|---|
| `TaskCompletionMetric` | `input`, `actual_output` **+ trace** | — | `threshold=0.5`, `task=None`, standard 5 | ↑ | **TRACE** | `metrics/task_completion/task_completion.py:25,32`; `self.requires_trace=True` at `:55`; reads `_trace_dict` at `:185-189` |
| `PlanAdherenceMetric` | `input`, `actual_output` **+ trace** | — | standard 6 | ↑ | **TRACE** | `metrics/plan_adherence/plan_adherence.py:26,33`; `:49`; `:173` |
| `PlanQualityMetric` | `input`, `actual_output` **+ trace** | — | standard 6 | ↑ | **TRACE** | `metrics/plan_quality/plan_quality.py:26,33`; `:49`; `:203` |
| `StepEfficiencyMetric` | `input`, `actual_output` **+ trace** | — | standard 6 | ↑ | **TRACE** | `metrics/step_efficiency/step_efficiency.py:18,25`; `:41`; `:149` |
| `AgentLoopDetectionMetric` *(det.)* | `input`, `actual_output` **+ trace** | — | `threshold=0.5`, `repetition_threshold=3`, `similarity_threshold=0.85`, `check_tool_repetition=True`, `check_reasoning_stagnation=True`, `check_call_graph_cycles=True`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | ↑ | **TRACE** | `metrics/agent_loop_detection/agent_loop_detection.py:65,119`; `:145`; `:213` |
| `TopicAdherenceMetric` *(conv.)* | turns | **`relevant_topics: List[str]`** | standard 6 | ↑ | **YES** | `metrics/topic_adherence/topic_adherence.py:24,31` |
| `ToolUseMetric` *(conv.)* | turns | **`available_tools: List[ToolCall]`** | standard 6 | ↑ | **YES** | `metrics/tool_use/tool_use.py:29,36` |
| `GoalAccuracyMetric` *(conv.)* | turns | — | standard 6 | ↑ | **YES** | `metrics/goal_accuracy/goal_accuracy.py:25,32` |

`AgentLoopDetectionMetric` is fully deterministic — the docstring is explicit
(`:93-99`: "Fully deterministic — no LLM / API key required… accepting a `model`
argument would be misleading"). It sets `self.model = None` but
`self.using_native_model = True` (`:138-139`), which is a lie the framework never
reads for this metric. Its three sub-signals: identical `(name, args)` tool-call
repetition; bigram-Jaccard ∪ `difflib.SequenceMatcher` similarity on consecutive
LLM-span outputs; DFS cycle detection on `type:name:input_hash` labels
(`:105-118`, `:280-421`).

### 3.6 Conversational (multi-turn) metrics

| Metric | Required `MultiTurnParams` | Required ctor | Extra optional | Dir | Config-only? | Evidence |
|---|---|---|---|---|---|---|
| `TurnRelevancyMetric` | `content`, `role` | — | `window_size=10`, `template_class=None` | ↑ | **YES** | `metrics/turn_relevancy/turn_relevancy.py:27,30` |
| `TurnFaithfulnessMetric` | `role`, `content`, `retrieval_context` | — | `truths_extraction_limit=None`, `penalize_ambiguous_claims=False`, `window_size=10` | ↑ | **YES** | `metrics/turn_faithfulness/turn_faithfulness.py:41,48` |
| `TurnContextualPrecisionMetric` | `role`, `content`, `retrieval_context`, `expected_outcome` | — | `window_size=10` | ↑ | **YES** | `metrics/turn_contextual_precision/turn_contextual_precision.py:48,56` |
| `TurnContextualRecallMetric` | `role`, `content`, `retrieval_context`, `expected_outcome` | — | `window_size=10` | ↑ | **YES** | `metrics/turn_contextual_recall/turn_contextual_recall.py:57,65` |
| `TurnContextualRelevancyMetric` | `role`, `content`, `retrieval_context` | — | `window_size=10` | ↑ | **YES** | `metrics/turn_contextual_relevancy/turn_contextual_relevancy.py:60,67` |
| `ConversationCompletenessMetric` | `content`, `role` | — | **`window_size=3`** | ↑ | **YES** | `metrics/conversation_completeness/conversation_completeness.py:26,29` |
| `KnowledgeRetentionMetric` | `content`, `role` | — | standard 6 | ↑ | **YES** | `metrics/knowledge_retention/knowledge_retention.py:23,26` |
| `RoleAdherenceMetric` | `content`, `role` | — | standard 6 | ↑ | **YES** | `metrics/role_adherence/role_adherence.py:22,25` |

Note `window_size` default is **10** for the five `Turn*` metrics but **3** for
`ConversationCompletenessMetric`. A PACT profile that sets one global
`window_size` default would silently change conversation-completeness behaviour.

### 3.7 MCP metrics

| Metric | Required fields | Required ctor | Dir | Config-only? | Evidence |
|---|---|---|---|---|---|
| `MCPUseMetric` *(single-turn)* | `input`, `actual_output`, **`mcp_servers`** | — | ↑ | **YES** | `metrics/mcp_use_metric/mcp_use_metric.py:26,33` |
| `MCPTaskCompletionMetric` *(conv.)* | `role`, `content` (+ `mcp_servers` on the case) | — | ↑ | **YES** | `metrics/mcp/mcp_task_completion.py:25,31` |
| `MultiTurnMCPUseMetric` *(conv.)* | `role`, `content` | — | ↑ | **YES** | `metrics/mcp/multi_turn_mcp_use_metric.py:28,34` |

`MCPServer` is a plain dataclass (`test_case/mcp.py:22-28`): `server_name`,
`transport: "stdio"|"sse"|"streamable-http"`, `available_tools`,
`available_resources`, `available_prompts`. Items may be **plain dicts**
(`validate_mcp_servers` at `:31-56` accepts `dict` unconditionally), so the whole
MCP declaration is YAML-writable without importing `mcp.types`. **This is exactly
what D14 needs** — a non-technical author declares MCP tools in YAML and gets MCP
evaluation for free.

`MCPToolCall.result`, `MCPResourceCall.result`, `MCPPromptCall.result` are typed
`object` in the model (`:8-20`) but the **test-case validators require real
`mcp.types.CallToolResult` / `ReadResourceResult` / `GetPromptResult` objects**
(`llm_test_case.py:547-584`, `conversational_test_case.py:140-187`). So *declaring
available* MCP tools is config-only; *recording what was called* is not — the
harness must produce those objects. Fine, because the harness is code.

### 3.8 Multimodal metrics

| Metric | Required fields | Image-count constraint | Optional | Config-only? | Evidence |
|---|---|---|---|---|---|
| `TextToImageMetric` | `input`, `actual_output` | input images **0**, output images **1** | `model=None`, `threshold=0.5`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | **YES** | `metrics/multimodal_metrics/text_to_image/text_to_image.py:29,30`; counts passed at `:50-58` |
| `ImageEditingMetric` | `input`, `actual_output` | input **1**, output **1** | same 5 | **YES** | `.../image_editing/image_editing.py:24,31`; `:52-60` |
| `ImageCoherenceMetric` | `input`, `actual_output` | unconstrained | same 5 + `max_context_size=None` | **YES** | `.../image_coherence/image_coherence.py:24,30` |
| `ImageHelpfulnessMetric` | `input`, `actual_output` | unconstrained | same 5 + `max_context_size=None` | **YES** | `.../image_helpfulness/image_helpfulness.py:24,31` |
| `ImageReferenceMetric` | `input`, `actual_output` | unconstrained | same 5 + `max_context_size=None` | **YES** | `.../image_reference/image_reference.py:24,31` |

**These are image-*generation* metrics, not vision-*understanding* metrics.**
There is no multimodal faithfulness or multimodal answer-relevancy in DeepEval.
Ragas has both (`MultiModalFaithfulness`, `MultiModalRelevance`) — see §8. D16
requires vision in v1; **the DeepEval multimodal family does not cover
vision-RAG**, and any coverage matrix must say so.

Image evaluation additionally requires the *judge* model to support multimodal
input, enforced at `metrics/utils.py:314-331`. `MULTIMODAL_SUPPORTED_MODELS`
(`metrics/utils.py:73-81`) whitelists GPT, Gemini, Ollama, AzureOpenAI, Kimi,
Anthropic, Grok. `LocalModel.supports_multimodal()` returns `True`
unconditionally (`models/llms/local_model.py:203-204`), so an air-gapped
OpenAI-compatible endpoint works; `OllamaModel` gates on a static table
(`models/llms/ollama_model.py:202-203`, table at `models/llms/constants.py:1107+`
— **static data, no network**).

### 3.9 Custom / structural metrics

| Metric | Required ctor | Optional | Config-only? | Evidence |
|---|---|---|---|---|
| `GEval` | `name: str`; **plus at least one of `criteria` / `evaluation_steps`**, and `evaluation_params` is required at measure-time (`ensure_required_params`, `g_eval.py:96-98`) | `evaluation_params=None`, `criteria=None`, `evaluation_steps=None`, `rubric: List[Rubric]=None`, `model=None`, `threshold=0.5`, `top_logprobs=20`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | **YES** | `metrics/g_eval/g_eval.py:45,46` |
| `ConversationalGEval` | `name: str` | `evaluation_params: List[MultiTurnParams]`, `criteria`, `evaluation_steps`, `model`, `threshold=0.5`, `top_logprobs=20`, `rubric`, `async_mode`, `strict_mode`, `verbose_mode` | **YES** | `metrics/conversational_g_eval/conversational_g_eval.py:43,44` |
| `ArenaGEval` | `name: str`, `evaluation_params: List[SingleTurnParams]` | `criteria`, `evaluation_steps`, `model`, `async_mode=True`, `verbose_mode=False` — **no `threshold`, no `strict_mode`** | **YES** | `metrics/arena_g_eval/arena_g_eval.py:35,36` |
| `DAGMetric` | `name: str`, `dag: DeepAcyclicGraph` | `model`, `threshold=0.5`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | **YES\*** (official JSON codec) | `metrics/dag/dag.py:23,25` |
| `ConversationalDAGMetric` | `name: str`, `dag: DeepAcyclicGraph` | same | **YES\*** | `metrics/conversational_dag/conversational_dag.py:22,24` |

`Rubric` (`metrics/g_eval/utils.py:34-50`): `score_range: Tuple[int,int]` (both
ends in `[0,10]`, start ≤ end — validated) and `expected_outcome: str`. Pure data.
The rubric determines the score range and G-Eval normalises
`(g_score - range[0]) / span` (`g_eval.py:71-72`, `:146-151`).

`GEval.upload()` (`:421`) and `GEval.pull()` (`:458`) hit the Confident AI API.
**Both are hosted-only and unavailable under D17.** PACT must never route metric
definitions through them.

### 3.10 Legacy Ragas wrappers (present but unexported)

| Class | Ctor | Notes |
|---|---|---|
| `RAGASContextualPrecisionMetric` | `threshold=0.3`, `model="gpt-3.5-turbo"`, `_track=True` | `metrics/ragas.py:38,41` |
| `RAGASContextualRecallMetric` | same | `:119,122` |
| `RAGASContextualEntitiesRecall` | same | `:192,195` |
| `RAGASAnswerRelevancyMetric` | + `embeddings=None` | `:342,345` |
| `RAGASFaithfulnessMetric` | same as first | `:424,425` |
| `RagasMetric` (composite) | `threshold=0.3`, `model`, `embeddings` | `:496,499` |

All require `langchain_core` (`ragas.py:12-27`, `_check_langchain_available`) and
default to a **hardcoded `gpt-3.5-turbo`** — a network dependency and a
capability-affecting literal. Under F-1/AC-7.2 these must not be exposed by PACT
without an explicit profile override, and under D17 they are unusable as shipped.

---

## 4. Cross-cutting semantics PACT must model explicitly

### 4.1 The `BaseMetric` contract (`deepeval/metrics/base_metric.py:44-105`)

Class-level attributes every metric carries: `threshold`, `score`,
`score_breakdown`, `reason`, `success`, `evaluation_model`, `strict_mode=False`,
`async_mode=True`, `verbose_mode=True`, `include_reason=False`, `error`,
`evaluation_cost`, `input_tokens`, `output_tokens`, `verbose_logs`,
`skipped=False`, **`requires_trace=False`**, `model`, `using_native_model`.
Abstract: `measure()`, `a_measure()`, `is_successful()`.

`__init_subclass__` auto-instruments every metric with `observe_methods(cls)`
(`:66-70`) — i.e. metrics themselves emit spans.

### 4.2 Score direction is per-metric and **not** in the public surface

Verified by reading `is_successful()` in all 56 classes. Exactly four are
`score <= threshold`:

| Metric | Comparison | Strict threshold | File:line |
|---|---|---|---|
| `BiasMetric` | `<=` | `0` | `bias/bias.py:290`, `:41` |
| `ToxicityMetric` | `<=` | `0` | `toxicity/toxicity.py:287`, `:42` |
| `HallucinationMetric` | `<=` | `0` | `hallucination/hallucination.py:258`, `:41` |
| `MisuseMetric` | `<=` | `0` | `misuse/misuse.py:285`, `:46` |

Everything else is `>=` with `strict → threshold = 1`.

There is **no attribute, no enum, and no method** exposing this. A generic caller
(and therefore any PACT provider) cannot ask a metric which way its threshold
points. **PACT's metric catalogue must carry `direction: higher_is_better |
lower_is_better` per metric URI**, and the author-facing form should normalise —
e.g. `max: 0.1` for lower-is-better, `min: 0.8` for higher-is-better — so a
non-technical author never has to know.

### 4.3 Verified bug: `RoleViolationMetric(strict_mode=True)` always passes

- `role_violation.py:47` — `self.threshold = 0 if strict_mode else threshold`
  (the *inverted-metric* convention).
- `role_violation.py:295` — `self.success = self.score >= self.threshold`
  (the *normal* convention).
- `role_violation.py:278-288` — `_calculate_score()` returns exactly `1.0`
  (no violation), `0.0` (violation), or `1` (no verdicts).

Therefore with `strict_mode=True`: `score >= 0` for every possible score →
**the gate never fires**. Every other inverted metric pairs `threshold=0` with
`<=`; every other normal metric pairs `threshold=1` with `>=`. This one crosses
the wires.

> **Design consequence.** This is exactly the failure mode T7 forbids: a policy
> gate that reports PASS while measuring a violation. PACT's provider layer must
> **compute pass/fail itself** from `(score, threshold, direction)` and must not
> delegate to `metric.is_successful()`. That also removes the dependency on 56
> independently-written comparison implementations.

### 4.4 Async

`async_mode=True` everywhere by default. `measure()` on LLM-judged metrics
internally spins an event loop and awaits `a_measure()`
(e.g. `g_eval.py:118-136`), wrapped in `asyncio.wait_for` with
`DEEPEVAL_PER_TASK_TIMEOUT_SECONDS` unless `DEEPEVAL_DISABLE_TIMEOUTS`
(`g_eval.py:126-136`). Deterministic metrics either ignore `async_mode`
(`ExactMatch`, `PatternMatch` — `a_measure` delegates to `measure`) or force it
off (`ToolPermissionMetric` sets `self.async_mode = False`, `:60`).

Suite-level concurrency is `AsyncConfig(run_async=True, throttle_value=0,
max_concurrent=20)` (`evaluate/configs.py:8-18`); `assert_test` overrides
`max_concurrent=100` (`evaluate/evaluate.py:82`).

### 4.5 Missing-parameter handling

`check_llm_test_case_params` (`metrics/utils.py:305-382`) raises
`MissingTestCaseParamsError` naming the missing fields. `ErrorConfig`
(`evaluate/configs.py:44-47`) exposes `ignore_errors=False`,
`skip_on_missing_params=False`. Note `actual_output=""` is treated as *missing*,
not as an empty answer (`:358-363`) — an agent that legitimately returns nothing
is scored as an error, not a failure. PACT should decide this explicitly rather
than inherit it.

### 4.6 Structured-output fallback (matters for SLM judges)

Every LLM-judged metric routes through `generate_with_schema_and_extract`
(`metrics/utils.py:495-521`): call `model.generate_with_schema(prompt, schema=…)`;
if the result is an instance of the schema use it, else `trimAndLoadJson` the
string. `DeepEvalBaseLLM.generate_with_schema` (`models/base_model.py:124-131`)
tries `generate(..., schema=…)` and falls back to plain `generate(...)` on
`TypeError`. So a judge with no structured-output support degrades to
JSON-in-text parsing — workable, but a known SLM failure mode.

### 4.7 G-Eval loses its log-prob weighting off OpenAI/Azure

`GEval._evaluate` (`g_eval.py:379-403`) calls
`self.model.generate_raw_response(prompt, top_logprobs=self.top_logprobs)` and
computes `calculate_weighted_summed_score(score, res)`. On `AttributeError` it
falls back to a plain integer score (`:402-407`).

`generate_raw_response` is implemented on **only four** model classes:
`openai_model.py:294`, `azure_model.py:341`, `litellm_model.py:153`,
`gateway_model.py:249`. It is **not** on `LocalModel`, `OllamaModel`,
`AnthropicModel`, `GeminiModel`, `AmazonBedrockModel`, `KimiModel`, `GrokModel`,
`DeepSeekModel`, `OpenRouterModel`, `PortkeyModel`, nor on the base class.

> **Design consequence.** Under D17 (air-gapped, `OllamaModel`/`LocalModel`
> judges), **G-Eval returns coarse integer scores, not the continuous
> logprob-weighted score.** Scores become steppier and less able to discriminate
> small deltas. That directly threatens AC-2.2 ("within a declared ε") and
> AC-3.1 ("≥ 95%") whenever G-Eval is the deciding metric. PACT must (a) record
> `logprob_weighted: true|false` in the eval report, (b) forbid ε-based
> conformance verdicts that rest on an unweighted G-Eval alone, and (c) prefer
> the DAG metric — whose leaves are binary/categorical judgements — for
> conformance gating on air-gapped judges.
>
> *Escape hatch that works offline:* `LiteLLMModel` implements
> `generate_raw_response` (`litellm_model.py:153`), and LiteLLM can front a local
> vLLM/Ollama server. So the weighting is recoverable **if** the local server
> returns logprobs. Not verified end-to-end here — marked as an open question.

### 4.8 There is no epoch / repetition / variance machinery

`evaluate()` runs each test case **once**. There is no `epochs` parameter, no
score reducer, no confidence interval, and no `stderr` anywhere in the package.
Compare `inspect_ai` (§10). Consequence for PACT: **AC-2.2's ε and AC-3.1's 95%
are not decidable from a single DeepEval run.** PACT must own repetition and
aggregation above the provider.

---

## 5. Aggregation, thresholds, and composition — what DeepEval cannot express

`evaluate()` signature (`evaluate/evaluate.py:158-178`): `test_cases`, `metrics`,
`metric_collection`, `hyperparameters`, `identifier`, `official`, plus four config
dataclasses. `validate_evaluate_inputs` (`evaluate/utils.py:303-311`) requires
**exactly one** of `metrics` / `metric_collection`.

Test-case success is a plain AND over metric successes
(`test_run/api.py:61-67`, `:81-86`: first metric sets it, any subsequent failure
latches it to `False`).

**Not expressible in DeepEval, at all:**

| Capability | DeepEval | promptfoo |
|---|---|---|
| Negate an assertion | ✗ | `not-<any of 66 types>` (`src/types/index.ts:677-680`) |
| Weight metrics within a case | ✗ | `weight` on every assertion (`:722`) |
| Group metrics with a group threshold | ✗ | `assert-set` with nested `assert`, `weight`, `threshold` (`:687-708`) |
| OR / any-of | ✗ | via `assert-set` + threshold |
| Tag a metric result into a named rollup | ✗ | `metric:` field (`:731`) |
| Pick the best of N candidate outputs | `compare()` + `ArenaGEval` only, code-driven | `select-best`, `max-score` assertion types (`:673`) |
| Transform the output before asserting | ✗ | `transform`, `contextTransform` (`:734-737`) — but these are JS/Python = code |

> **Design consequence.** PACT's eval document must own composition: `all`, `any`,
> `not`, `weight`, group `threshold`, and named metric rollups. None of it can be
> pushed down to DeepEval; the provider evaluates leaf metrics and PACT combines.
> This is also what makes D19's on-ramps (1)–(4) desugarable: "must cite a source"
> becomes `{all: [{metric: deepeval:faithfulness, min: 0.8}, {metric: pattern_match, …}]}`.

---

## 6. Datasets and goldens

`Golden` (`dataset/golden.py:9-43`): `input` (required), `actual_output`,
`expected_output`, `context`, `retrieval_context`, `additional_metadata`,
`comments`, `tools_called`, `expected_tools`, `source_file`, `name`,
`custom_column_key_values`, `multimodal`, `images_mapping`.
`ConversationalGolden` (`:117-146`): `scenario` (required), `expected_outcome`,
`user_description`, `context`, `additional_metadata`, `comments`, `name`,
`custom_column_key_values`, `turns`.

`EvaluationDataset` loaders — **all config-file-driven, all offline**:

| Method | Formats / knobs | Line |
|---|---|---|
| `add_goldens_from_csv_file` | per-column names + `context_col_delimiter="\|"`, `tools_called_col_delimiter=";"` … | `dataset/dataset.py:487` |
| `add_goldens_from_json_file` | per-key names, `encoding_type="utf-8"` | `:672` |
| `add_goldens_from_jsonl_file` | per-key names + delimiters + `custom_column_key_values` | `:755` |
| `add_test_cases_from_csv_file` / `..._json_file` | same shape for full test cases | `:255`, `:407` |
| `save_as(file_type: "json"\|"csv"\|"jsonl", directory, file_name, include_test_cases=False)` | export | `:1167` |
| `push` / `pull` / `create_version` / `get_versions` / `queue` / `delete` | **Confident AI hosted — unusable air-gapped** | `:887`, `:925`, `:1012`, `:1033`, `:1043`, `:1081` |
| `generate_goldens_from_docs` / `_contexts` / `_from_scratch` | delegate to `Synthesizer` | `:1094`, `:1125`, `:1148` |
| `evals_iterator(metrics, hyperparameters, identifier, *configs, run_otel=False)` | trace-scoped iteration; yields `Golden` | `:1513` |

Requires `pandas` for CSV (`:494-499`) — an optional dependency PACT must vendor
or avoid for air-gapped installs.

> **Design consequence.** AC-4.3 dataset authoring (YAML/CSV/JSONL) maps 1:1 onto
> the golden loaders, and `Golden`'s field set is a strict subset of `LLMTestCase`'s.
> PACT's `evals/datasets/*.{yaml,csv,jsonl}` can be lowered directly. **But
> DeepEval's loaders are column-name-parameterised, not schema-driven** — PACT
> should fix the column names in its own schema and pass them down, rather than
> exposing 20 `*_col_name` knobs to a non-technical author.

---

## 7. Synthesizer, simulator, tracing, optimizer, benchmarks, scorer

### 7.1 Synthesizer (`deepeval/synthesizer/`)

`Synthesizer.__init__` (`synthesizer.py:117-130`): `model=None`,
`async_mode=True`, `max_concurrent=100`, `filtration_config`, `evolution_config`,
`styling_config`, `conversational_styling_config`, `cost_tracking=False`.
All four config objects are **plain dataclasses of scalars** (`config.py`):

- `FiltrationConfig(synthetic_input_quality_threshold=0.5, max_quality_retries=3, critic_model=None)` — `config.py:12-20`
- `EvolutionConfig(num_evolutions=1, evolutions: Dict[Evolution,float] = 7 kinds at 1/7 each)` — `config.py:23-36`; `Evolution` = REASONING, MULTICONTEXT, CONCRETIZING, CONSTRAINED, COMPARATIVE, HYPOTHETICAL, IN_BREADTH (`types.py:4-12`)
- `StylingConfig(scenario, task, input_format, expected_output_format)` — `config.py:39-44`
- `ConversationalStylingConfig(scenario_context, conversational_task, participant_roles, scenario_format, expected_outcome_format)` — `config.py:47-53`
- `ContextConstructionConfig(embedder, critic_model, encoding, max_contexts_per_document=3, min_contexts_per_document=1, max_context_length=3, min_context_length=1, chunk_size=1024, chunk_overlap=0, context_quality_threshold=0.5, context_similarity_threshold=0.0, max_retries=3, allow_cross_file_contexts=False, target_files_per_context=None, max_files_per_context=3)` — `config.py:56-71`

Generation entry points: `generate_goldens_from_docs(document_paths, include_expected_output=True, max_goldens_per_context=2, context_construction_config)` (`:422`),
`generate_goldens_from_contexts` (`:672`), `generate_goldens_from_scratch` (`:1271`),
`generate_goldens_from_goldens` (`:1379`), plus the four `*_conversational_*`
variants (`:2055`, `:2301`, `:2882`, `:3176`).

**Verdict: 100% config-only.** Every argument is a scalar, a list of paths, or a
dataclass of scalars. This is the strongest candidate for D19 on-ramp (4)
("builder-agent generated, human-approved") and directly serves R3 (eval
authoring burden). Air-gapped: needs a local embedder and a local critic model,
both pluggable.

### 7.2 Conversation simulator — **the one genuinely code-shaped subsystem**

`ConversationSimulator.__init__` (`simulator/conversation_simulator.py:46-56`):
`model_callback: Callable[[str], str]` **(required)**, `simulation_graph:
Optional[SimulationNode]`, `stopping_controller: Callable = expected_outcome_controller`,
`simulator_model`, `max_concurrent=5`, `async_mode=True`, `language="English"`.

`SimulationNode(action: Callable[..., str|Turn], terminal=False, max_visits=None,
name=None)` with `add_node(child, when: str)` (`simulation_graph/node.py:30-64`).
The **edges are natural-language** (`when=` is an LLM-routed description) but the
**node actions are callables**.

> **Design consequence.** `model_callback` is *not* an author burden in PACT — the
> agent under test **is** the callback, supplied by the harness. `stopping_controller`
> has a usable default (`expected_outcome_controller`). Only `simulation_graph`
> needs a declarative replacement:
> ```yaml
> simulation:
>   max_turns: 10
>   graph:
>     - id: ask_refund
>       say: "I want a refund for order {order_id}"
>       next:
>         - when: "the agent asks for an order number"
>           goto: give_order
>         - when: "the agent refuses"
>           goto: escalate
>     - id: escalate
>       say: "Let me speak to a manager"
>       terminal: true
> ```
> `say:` is a template string → wrapped in a zero-arg action closure by the
> provider. `next[].when` maps straight onto `add_node(child, when=…)`.
> `max_visits` and `terminal` are already scalars. This is the *only* new
> declarative construct the simulator needs.

### 7.3 Tracing (`deepeval/tracing/`)

`SpanType` = `agent | llm | retriever | tool` (`tracing/types.py:37-41`).
`BaseSpan` (`:87-125`): `uuid`, `status`, `children: List[BaseSpan]`, `trace_uuid`,
`parent_uuid`, `start_time`, `end_time`, `name`, `metadata`, `input`, `output`,
`error`, `llm_test_case`, `metrics`, `metric_collection`, `integration`, plus
`retrieval_context`, `context`, `expected_output`, `tools_called`, `expected_tools`.
Subclasses add: `AgentSpan.available_tools/agent_handoffs` (`:128-131`);
`LlmSpan.model/provider/prompt/input_token_count/output_token_count/
cost_per_input_token/cost_per_output_token/token_intervals/prompt_*` (`:134-168`);
`RetrieverSpan.embedder/top_k/chunk_size` (`:171-174`); `ToolSpan.name/description`
(`:177-179`). `Trace` (`:182-235`) adds `tags`, `thread_id`, `user_id`,
`test_case_id`, `test_run_id`, `turn_id`.

`observe(_func=None, *, metrics=None, metric_collection=None,
type="agent"|"llm"|"retriever"|"tool"|str, ...)` (`tracing/tracing.py:1316-1327`) —
this is how **component-level (per-span) metrics** are attached.

> **Design consequence — two, both load-bearing.**
> 1. `LlmSpan.token_intervals: Dict[float, str]` (`:158`) is a per-token timing map.
>    Combined with `start_time`/`end_time` this is enough to compute **TTFT and
>    TPOT** — the two SLOs D16 makes mandatory for voice. DeepEval records them but
>    has no metric that asserts on them. **PACT's SLO predicates should be
>    evaluated over the same span tree**, so one instrumentation serves both evals
>    and SLOs.
> 2. `@observe(metrics=[…])` proves the design point that metrics attach to
>    *components*, not only to whole runs. PACT's topology/loop IR should allow
>    `metrics:` on any node, and the harness attaches them at span creation. This
>    is what makes G-4 (recursive composition) evaluable.

### 7.4 Prompt optimizer (`deepeval/optimizer/`)

`PromptOptimizer(model_callback, metrics, optimizer_model=None,
algorithm: GEPA|MIPROV2|COPRO|SIMBA = GEPA(), async_config, display_config)`
(`optimizer/prompt_optimizer.py:51-61`);
`optimize(prompt: Prompt, goldens) -> Prompt` (`:86-105`).

> **This independently corroborates AC-3.1b.** DeepEval keeps `optimizer_model`
> as a *separate binding* from `model_callback` (the system under test). PACT's
> requirement that the optimiser model never collapse into the execution model is
> not a PACT invention — the reference implementation already separates them.

Algorithm constants at `optimizer/algorithms/configs.py` are marked
"Internal … not exposed to users" (MIPROv2: 10 candidates, 20 trials, minibatch 25,
4 bootstrapped demos, 4 labeled demos, 5 demo sets). Under F-1 these are exactly
the kind of capability-affecting literals PACT must surface into a profile.

### 7.5 Benchmarks (`deepeval/benchmarks/__init__.py:19-37`)

17: `BigBenchHard`, `MMLU`, `HellaSwag`, `DROP`, `TruthfulQA`, `HumanEval`,
`SQuAD`, `GSM8K`, `MathQA`, `LogiQA`, `BoolQ`, `ARC`, `BBQ`, `LAMBADA`,
`Winogrande`, `EquityMedQA`, `IFEval`. These are dataset-downloading harnesses —
network-dependent, therefore **out of scope for the air-gapped core** (D17). They
feed O3.2 (catalogue benchmark figures) at *catalogue build* time, not at eval time.

### 7.6 `Scorer` — classic NLP scorers, *not* exposed as metrics

`deepeval/scorer/scorer.py`: `rouge_score` (:19), `sentence_bleu_score` (:52),
`exact_match_score` (:99), `quasi_exact_match_score` (:114),
`quasi_contains_score` (:120), `bert_score` (:129), `faithfulness_score` (:206),
`hallucination_score` (:240), `PII_score` (:267), `neural_toxic_score` (:273),
`answer_relevancy_score` (:312), `neural_bias_score` (:372),
`truth_identification_score` (:381), `pass_at_k` (:427), `squad_score` (:439).

**None of these is a `BaseMetric`.** ROUGE, BLEU, BERTScore, and pass@k are
*unavailable* as thresholded metrics in an eval suite — you cannot write
`deepeval:rouge` in a config because no such metric class exists. The neural
scorers (`detoxify_model.py`, `unbias_model.py`, `summac_model.py`,
`hallucination_model.py`, `answer_relevancy_model.py`) pull HuggingFace weights —
air-gapped only with a pre-seeded cache.

> **Design consequence.** PACT's `deepeval:` namespace must not silently expose
> `Scorer` functions as metrics; they need a separate provider
> (`native:rouge`, `native:bleu`, `native:bertscore`) or the coverage matrix will
> over-claim. Ragas *does* expose these as metrics (§8), so `ragas:` is a cheaper
> route than writing them.

---

## 8. What Ragas has that DeepEval lacks

Read from `research/repos/eval/ragas/src/ragas/metrics/__init__.py` (import block,
lines 3-98) and the named implementation files.

### 8.1 Genuine capability gaps

| Ragas metric | What it does | DeepEval equivalent | Evidence |
|---|---|---|---|
| `SemanticSimilarity` / `AnswerSimilarity` | **embedding cosine** vs reference | **none — DeepEval has no embedding-based metric at all** | `_answer_similarity.py` |
| `AnswerCorrectness` | claim-F1 vs reference **+** semantic similarity, weighted | none | `_answer_correctness.py` |
| `FactualCorrectness` | claim-level precision / recall / F1 vs reference | none | `_factual_correctness.py` |
| `NonLLMStringSimilarity` | Levenshtein / Hamming / Jaro / Jaro-Winkler | none (PatternMatch is regex `fullmatch` only) | `_string.py:62-80` |
| `StringPresence` | `reference in response` | **none** — DeepEval cannot express "output contains X" | `_string.py:38-58` |
| `RougeScore`, `BleuScore`, `ChrfScore` | as *metrics* with thresholds | only as `Scorer` functions, not metrics | `_rouge_score.py`, `_bleu_score.py`, `_chrf_score.py` |
| `IDBasedContextPrecision` / `IDBasedContextRecall` | **deterministic** retrieval eval on chunk IDs | none — all DeepEval contextual metrics are LLM-judged | `_context_precision.py:251-281`, `_context_recall.py` |
| `NonLLMContextPrecisionWithReference` / `NonLLMContextRecall` | deterministic string-distance retrieval eval | none | `_context_precision.py`, `_context_recall.py` |
| `NoiseSensitivity` | how often irrelevant retrieved chunks corrupt the answer | none | `_noise_sensitivity.py` |
| `ContextEntityRecall` | entity-level recall of retrieved context | only via the deprecated `RAGASContextualEntitiesRecall` wrapper | `_context_entities_recall.py` |
| `ContextUtilization` | precision **without** a reference answer | none | `_context_precision.py` |
| `LLMContextPrecisionWithoutReference` | reference-free context precision | none | `_context_precision.py` |
| `FaithfulnesswithHHEM` | **local NLI cross-encoder** (`vectara/hallucination_evaluation_model`), `device`, `batch_size` | none — every DeepEval faithfulness path needs a generative judge | `_faithfulness.py:218-234` |
| `InstanceRubrics` | **per-test-case rubric** carried on the sample (`rubrics: Dict[str,str]`) | none — `GEval.rubric` is fixed on the metric | `_instance_specific_rubrics.py:28-36,52` |
| `RubricsScore` | shared domain rubric, discrete output | `GEval(rubric=…)` partially | `_domain_specific_rubrics.py` |
| `MultiModalFaithfulness` / `MultiModalRelevance` | **vision-RAG** grounding | none — DeepEval multimodal is image-*generation* only | `_multi_modal_faithfulness.py`, `_multi_modal_relevance.py` |
| `LLMSQLEquivalence` | SQL semantic equivalence | none | `_sql_semantic_equivalence.py` |
| `DataCompyScore` | dataframe equivalence | none | `_datacompy_score.py` |
| `ToolCallF1` | F1 over tool calls | `ToolCorrectness` (exact/order flags), no F1 output | `_tool_call_f1.py` |
| `AnswerAccuracy` / `ContextRelevance` / `ResponseGroundedness` | NVIDIA dual-judge metrics | none | `_nv_metrics.py` |
| `AspectCritic`, `SimpleCriteriaScore` | binary / simple LLM criteria | covered by `GEval` | `_aspect_critic.py`, `_simple_criteria.py` |

### 8.2 The three that matter most for PACT

1. **`InstanceRubrics` — per-case rubric.** D19 on-ramp (1) is *"when asked X, the
   answer should be like Y"*. That is a per-case rubric. DeepEval **cannot express
   it**: `GEval.rubric` is bound to the metric, so a suite of 50 cases each with
   its own acceptance criterion needs 50 `GEval` instances. PACT must support
   `case.rubric` and either route to `ragas:instance_rubrics` or synthesise a
   per-case `GEval`. **This is the single largest authoring-ergonomics gap in the
   whole survey.**
2. **`FaithfulnesswithHHEM` — a local NLI judge.** Under D17 with a weak local
   generative judge, a 400M cross-encoder is both cheaper and more reliable than
   an SLM-as-judge. R4/AC-4.5 ("deterministic checkers before LLM judges") wants
   exactly this tier: *deterministic → small discriminative model → generative judge*.
   DeepEval has no such tier.
3. **Deterministic retrieval metrics (`IDBased*`, `NonLLM*`).** Every DeepEval
   contextual metric invokes a judge. For a RAG agent whose retriever emits chunk
   IDs, precision/recall are *arithmetic*. AC-4.5 says a suite fully decidable
   deterministically must never invoke a judge — with DeepEval alone that is
   impossible for RAG.

---

## 9. What promptfoo has that DeepEval lacks

Read from `research/repos/eval/promptfoo/src/types/index.ts:595-663`
(`BaseAssertionTypesSchema`, 66 types) and `src/assertions/*.ts`.

### 9.1 The assertion object — the correct shape for a config-only eval DSL

`AssertionSchema` (`src/types/index.ts:707-738`):
`type`, `value`, `config`, `threshold`, `weight`, `provider`, `rubricPrompt`,
`metric`, `transform`, `contextTransform`.
`AssertionSetSchema` (`:687-708`): `type: "assert-set"`, `assert: Assertion[]`,
`weight`, `metric`, `threshold`, `config`.
Negation is free: `NotPrefixedAssertionTypesSchema` derives `not-<T>` for **all 66
base types** (`:677-680`). Special types: `select-best`, `human`, `max-score` (`:673`).

### 9.2 Capabilities with no DeepEval counterpart

| Assertion | Why it matters to PACT | Evidence |
|---|---|---|
| `latency` (threshold in ms) | **O4.2 / AC-3.6.** DeepEval has nothing. | `src/assertions/latency.ts:3-27` |
| `cost` | budget caps as a gate | `src/assertions/cost.ts` |
| `perplexity`, `perplexity-score` | model-confidence gate | `src/assertions/perplexity.ts` |
| `trace-span-duration` with `{pattern, max, percentile}` | **percentile SLOs over the span tree** — precisely O4.2's "percentile semantics" | `src/assertions/traceSpanDuration.ts:5-20,64-` |
| `trace-span-count`, `trace-error-spans` | structural trace gates, deterministic | `src/assertions/traceSpanCount.ts`, `traceErrorSpans.ts` |
| `trajectory:goal-success`, `:tool-args-match`, `:step-count`, `:tool-sequence`, `:tool-used` | declarative agent-trajectory assertions; `:step-count` and `:tool-sequence` are deterministic where DeepEval's `StepEfficiency` is LLM-judged | `src/assertions/trajectory.ts` |
| `contains`, `contains-all`, `contains-any`, `icontains*`, `starts-with`, `word-count` | trivially authorable string gates; **DeepEval has none of these** | `src/assertions/contains.ts`, `startsWith.ts`, `wordCount.ts` |
| `is-json`, `contains-json`, `is-xml`, `contains-xml`, `is-html`, `contains-html`, `is-sql`, `contains-sql` | format gates, deterministic | `src/assertions/json.ts`, `xml.ts`, `html.ts`, `sql.ts` |
| `is-valid-function-call`, `is-valid-openai-tools-call` | tool-call schema validation | `src/assertions/functionToolCall.ts`, `openai.ts` |
| `finish-reason`, `is-refusal` | refusal / truncation detection | `finishReason.ts`, `refusal.ts` |
| `moderation`, `guardrails` | provider moderation + guardrail integration | `moderation.ts`, `guardrails.ts` |
| `levenshtein`, `similar:cosine|dot|euclidean` | string/embedding distance | `levenshtein.ts`, `similar.ts` |
| `bleu`, `gleu`, `meteor`, `rouge-n` | classic NLP metrics **as assertions** | `bleu.ts`, `gleu.ts`, `meteor.ts`, `rouge.ts` |
| `factuality`, `model-graded-closedqa`, `model-graded-factuality`, `classifier`, `llm-rubric`, `agent-rubric`, `search-rubric` | judge families | `factuality.ts`, `modelGradedClosedQa.ts`, `classifier.ts`, `llmRubric.ts`, `agentRubric.ts`, `searchRubric.ts` |
| `skill-used` | asserts a named skill fired | `src/assertions/skill.ts` |
| `select-best`, `max-score` | **config-only** arena/comparison; DeepEval needs `compare()` + `ArenaGEval` in Python | `src/types/index.ts:673` |

Code escapes (`javascript`, `python`, `ruby`, `webhook`, and the `transform` /
`contextTransform` fields) are promptfoo's F-2 equivalent. Note it took **three
languages plus a webhook** to cover the escape space — evidence for PACT's typed
`ref:` design rather than one blessed language.

> **Design consequence.** promptfoo's assertion object is the best available prior
> art for PACT's eval leaf. Adopt: `type`, `value`, `threshold`, `weight`,
> `metric` (rollup name), set composition, and `not-` negation. **Reject**
> `transform`/`contextTransform` as strings of JS — that is a code escape wearing
> a config costume and violates D14 if it becomes necessary rather than optional.

---

## 10. What inspect_ai has that DeepEval lacks

Read from `research/repos/eval/inspect_ai/src/inspect_ai/scorer/__init__.py`.

### 10.1 Score reducers over epochs — the missing statistical layer

`_reducer/reducer.py`: `mode_score` (:12), `mean_score` (:41), `median_score` (:63),
`at_least(k, value)` (:85), `pass_at(k, value)` (:119), `pass_k` (:164),
`max_score` (:203).
`pass_at` implements the Codex pass@k estimator with the correct
`1 - Π(1 - k/i)` correction and returns NaN when fewer than `k` scored epochs
survive (`:132-159`).

**DeepEval has none of this.** Each case runs once; there is no repetition, no
aggregation policy, no pass@k.

### 10.2 Uncertainty and grouped aggregation

`_metrics/std.py`: `bootstrap_stderr(num_samples=1000)` (:16-50),
`stderr(to_float, cluster=None)` (:53+) — **clustered** standard error included,
plus `std`, `var`. `_metrics/`: `accuracy`, `mean`, `grouped`, `categorical`,
`frequency`, `perplexity_per_seq`, `perplexity_per_token`.
Every built-in scorer declares its aggregate metrics up front, e.g.
`@scorer(metrics=[mean(), stderr()])` on `f1` and `exact`
(`_classification.py:14,42`).

> **Design consequence — this is the sharpest finding of the whole survey.**
> AC-2.2 requires eval scores "within a declared ε"; AC-3.1 requires "≥ 95% of the
> frontier score". **Neither claim is decidable without a standard error**, and
> DeepEval reports none. A 20-case suite with a 0.85 mean has a standard error
> around 0.08 — an ε of 0.05 is then meaningless noise. PACT must:
> (a) own `epochs:` and a reducer vocabulary (`mean | median | mode | max |
> at_least(k) | pass_at(k)`) above the provider;
> (b) report `stderr` (and `bootstrap_stderr` for small n) on every suite;
> (c) make the conformance verdict a **statistical** comparison, not a point
> comparison — otherwise AC-2.2 is a coin flip dressed as a gate.
> The reducer names above are a ready-made closed vocabulary; adopt them verbatim
> so PACT's `epochs`/`reducer` fields are recognisable to anyone who has used
> inspect.

### 10.3 Scorer families DeepEval lacks

`includes`, `match` (word-boundary/numeric-aware) (`_match.py`); `pattern` with
capture groups (`_pattern.py`); `answer(AnswerPattern)` for `ANSWER: X` extraction
(`_answer.py`); `choice` for MCQ (`_choice.py`); `math` for mathematical
equivalence (`_math.py`); `f1` / `exact` with normalisation and stop-words
(`_classification.py:16-57`); `perplexity`, `target_perplexity`;
`multi_scorer` for combining scorers under a reducer (`_multi.py`);
`model_graded_qa` / `model_graded_fact` with partial credit (`_model.py`);
`ScoreEdit` — an audit-trailed human correction to a score (`_metric.py`).

`ScoreEdit` deserves a note: it is the data structure behind human-in-the-loop
score revision with provenance. D19 on-ramp (3) ("mark conversations good/bad in a
review queue") needs exactly this, and neither DeepEval nor promptfoo (whose
`human` assertion is a UI affordance) models the *edit* as a first-class,
auditable object.

---

## 11. Python ↔ TypeScript divergence inside DeepEval

`typescript/src/metrics/index.ts` exports 44 metrics. Present in Python, **absent
in TypeScript**: `DAGMetric`, `ConversationalDAGMetric`, `DeepAcyclicGraph`,
`AgentLoopDetectionMetric`, `ToolPermissionMetric`, `CitationFaithfulnessMetric`.
So the two DAG metrics — the ones PACT most wants, because their leaves are
deterministic and their JSON codec already exists — **exist only in Python**.

Consistent with D4 (eval providers as a Python provider process), but it means a
future TS-native provider would be a *smaller* subset, and PACT's capability
lattice must express that.

Docs cross-check: `docs/content/docs/(rag)`, `(safety)`, `(multi-turn)`,
`(agentic)`, `(non-llm)`, `(custom)`, `(community)`, `(metrics-others)`, `(mcp)`
enumerate exactly the classes found in source — no metric is documented that does
not exist, and none exists that is undocumented. The published surface and the
source surface agree.

---

## 12. Air-gap audit (D17)

| Component | Offline? | Evidence |
|---|---|---|
| All 49 exported metrics with a local judge | **Yes** | `initialize_model` routes to `OllamaModel`/`LocalModel` via settings (`metrics/utils.py:659-703`) |
| G-Eval **logprob-weighted** scoring | **No** on Ollama/Local; yes via LiteLLM *if* the local server returns logprobs | `models/llms/*.py` — only 4 classes implement `generate_raw_response` |
| Model capability tables | **Yes** — static Python dicts | `models/llms/constants.py:1107+` |
| Dataset load/save (CSV/JSON/JSONL) | **Yes** (needs `pandas` for CSV) | `dataset/dataset.py:487,672,755,1167` |
| Dataset `push`/`pull`/versions/queue | **No** — Confident AI | `dataset/dataset.py:887-1092` |
| `evaluate(metric_collection=…)` | **No** — server-side metrics | `evaluate/utils.py:303-311` |
| `GEval.upload()` / `.pull()` | **No** | `metrics/g_eval/g_eval.py:421,458` |
| Synthesizer | **Yes** with a local embedder + critic | `synthesizer/config.py:56-71` |
| Conversation simulator | **Yes** | `simulator/conversation_simulator.py:46-56` |
| Tracing to Confident | **No**; but `_trace_dict` is in-process and local | `tracing/api.py` vs `evaluate/execute/agentic.py:372-407` |
| Benchmarks (17) | **No** — dataset downloads | `deepeval/benchmarks/` |
| `Scorer` neural models (detoxify, summac, unbias, …) | **No** without a pre-seeded HF cache | `models/detoxify_model.py`, `_summac_model.py`, `unbias_model.py` |
| Telemetry | Opt-out via `DEEPEVAL_TELEMETRY_OPT_OUT` | `config/settings.py:767` |

---

## 13. The PACT metric descriptor — concrete proposal

Adopt DeepEval's own DAG-child descriptor, generalised:

```yaml
# evals/suite.yaml  — the full-fidelity form (D19 on-ramp 5)
metrics:
  - uri: deepeval:faithfulness          # provider:metric
    min: 0.8                            # normalised threshold (direction-aware)
    args:                               # == the DAG serializer's "kwargs"
      truths_extraction_limit: 5
      penalize_ambiguous_claims: true
  - uri: deepeval:toxicity
    max: 0.1                            # lower-is-better rendered as `max:`
  - uri: deepeval:tool_permission
    args:
      allowed_tools: [search, calculator]
  - uri: deepeval:g_eval
    name: cites-a-source
    args:
      evaluation_params: [input, actual_output, retrieval_context]
      criteria: "The answer must cite at least one retrieved source."
      rubric:
        - {score_range: [0, 3], expected_outcome: "no citation"}
        - {score_range: [4, 10], expected_outcome: "cites a retrieved source"}
    min: 0.8
```

Rules that fall straight out of the source:

1. `args` maps 1:1 onto the constructor kwargs; the DAG serializer already proves
   round-tripping works for every JSON-valued kwarg
   (`serialization.py:316-340` serialise, `:507-534` reconstruct).
2. `min:` / `max:` replaces `threshold:` so direction is authored, not inherited.
   PACT computes `success` itself (§4.3).
3. `strict_mode` is **not exposed** to authors — it is a threshold shorthand with
   one broken implementation. `min: 1.0` / `max: 0.0` says the same thing safely.
4. Non-JSON kwargs get typed sub-blocks:
   - `dag:` → the `{"nodes": {...}}` document, passed to
     `DeepAcyclicGraph.from_dict` (`metrics/dag/graph.py:117-127`). Node kinds:
     `TaskNode`, `BinaryJudgementNode`, `NonBinaryJudgementNode`, `VerdictNode`
     (`dag/serialization/types.py:4-8`); verdict children are
     `{type: node|geval|metric}` (`:11-14`). Conversational variants add
     `turn_window: [start, end]` (`serialization.py:236-241`).
   - `schema:` (JSON Schema) → pydantic model for `JsonCorrectnessMetric`
     (only `.model_validate_json` / `.model_json_schema` are used).
   - `tools:` → `List[ToolCall]` for `ToolCorrectnessMetric.available_tools`
     and `ToolUseMetric.available_tools`.
   - `mcp_servers:` → `List[MCPServer]`; `available_*` may be plain dicts.
   - images → relative paths, materialised as `MLLMImage` **inside the provider**.
5. `requires_trace` is a property of the metric URI and must appear in PACT's
   catalogue, because a suite containing any of the five trace metrics changes
   what the harness must emit.

The Expansion Rule applies for free: `metrics/` as a directory of
`NN-name.yaml`, `criteria` as `criteria.md`, `dag` as `dag/` — no new mechanism.

---

## 14. Design implications, ranked

1. **The harness must emit a DeepEval-shaped trace.** `SpanType` ∈
   `{agent, llm, retriever, tool}`, nested `children`, `input`/`output` per span,
   `LlmSpan.token_intervals` for TTFT/TPOT. Without it, `TaskCompletion`,
   `PlanAdherence`, `PlanQuality`, `StepEfficiency`, `AgentLoopDetection` are
   unreachable and the "agentic metrics" row of the coverage matrix is empty.
2. **PACT owns pass/fail, epochs, reducers and standard error.** Do not delegate
   `is_successful()`; do not report a bare mean. Adopt inspect_ai's reducer names.
   AC-2.2's ε and AC-3.1's 95% are otherwise not decidable.
3. **Carry `direction` in the metric catalogue and author `min:`/`max:`.**
   Four metrics are inverted, one (`RoleViolation` + `strict_mode`) is
   affirmatively broken.
4. **Adopt the DAG JSON codec as the config-only path for compositional metrics.**
   It is upstream, tested, and its leaves are binary/categorical — which makes it
   the *right* metric for air-gapped conformance gating where G-Eval loses its
   logprob weighting.
5. **Do not claim red-team or guardrail parity.** Both left DeepEval in v3.0.
6. **Add three metric families DeepEval lacks**, or the no-code bar (D14) is not
   met: per-case rubrics (`ragas:instance_rubrics`-shaped), deterministic string
   and retrieval assertions (`contains`, `levenshtein`, ID-based context
   precision/recall), and SLO assertions (latency, cost, TTFT/TPOT,
   percentile span duration).
7. **Record `logprob_weighted` in every eval report.** A G-Eval score obtained
   without logprobs is a different measurement and must not be silently compared
   with one obtained with them (T7).
8. **The simulator needs one new declarative construct** (`simulation.graph` with
   `say`/`when`/`goto`/`terminal`/`max_visits`); everything else about it is
   already config, and `model_callback` is supplied by the harness, not the author.
9. **`deepeval:` must not expose `Scorer` functions.** ROUGE/BLEU/BERTScore/pass@k
   are not `BaseMetric`s; route them to `ragas:` or a `native:` provider or the
   coverage matrix over-claims.
10. **`PatternMatchMetric` uses `fullmatch`.** Either rename it in the PACT
    namespace or add an explicit `mode:` — a non-technical author writing
    `pattern: refund` will get a silent 0.0 on every case.

---

## 15. Open questions

1. Does LiteLLM fronting a local vLLM/Ollama server actually return `logprobs`,
   restoring G-Eval's weighted score air-gapped? `LiteLLMModel.generate_raw_response`
   exists (`litellm_model.py:153`) but the end-to-end path was **not** executed here.
2. Is the `deepteam` red-team package (not in the corpus) config-shaped? PACT's
   safety story depends on the answer, and it cannot be answered from this repo.
3. `_trace_dict` is a `PrivateAttr` populated by DeepEval-internal machinery — is
   there a supported way to set it from outside `@observe`? If not, the PACT
   provider must run the agent *inside* DeepEval's tracing context, which
   constrains the provider-process boundary.
4. `MLLMImage._id` is a fresh `uuid4` per construction, so image sentinels are
   process-local. Confirmed for construction; the multi-process provider design
   has not been tested against it.
5. Ragas's `SingleTurnSample` field names (`response`, `reference`,
   `retrieved_contexts`, `retrieved_context_ids`) differ from DeepEval's. A unified
   PACT case model must map to both; the mapping has not been enumerated here.
6. Do `ConversationalDAGMetric` `turn_window` semantics compose with
   `window_size` on the `Turn*` metrics, or are they independent windowing
   concepts that would confuse an author? Not investigated.
