# DeepEval Feature Surface — Exhaustive Inventory (research stream: `deepeval-surface`)

**Purpose.** Size acceptance criterion **AC-4.1** ("A published coverage matrix enumerates every
DeepEval metric and shows its config-only expression") honestly, from source.

**Corpus.** `/home/bud/ditto/agent-inter-op/research/repos/eval/deepeval`
- commit `6cf2e02d5e2f357683b5bcd177d808a755a2a49f`, dated `2026-07-22 21:45:55 +0800`
- `deepeval/_version.py:1` → `__version__: str = "4.1.3"`
- `pyproject.toml:3` → `version = "4.1.3"`

**Path convention in this document.** All `file:line` citations are relative to
`/home/bud/ditto/agent-inter-op/research/repos/eval/deepeval/` unless stated otherwise.
So `deepeval/metrics/g_eval/g_eval.py:46` means
`/home/bud/ditto/agent-inter-op/research/repos/eval/deepeval/deepeval/metrics/g_eval/g_eval.py:46`.

**Method.** Constructor signatures, defaults, `_required_params` / `_required_test_case_params`
class variables and base-class attributes were extracted mechanically by walking the Python AST of
every `.py` file under `deepeval/` (script: scratchpad `extract.py`, walks `ast.ClassDef` nodes whose
bases contain `Metric`, prints `__init__` signature with defaults `ast.unparse`d). Every scoring
behaviour, validation rule and network call cited below was then read in source. Nothing here comes
from the docs site or from memory. **DeepEval is not installed in this environment** (verified:
`python3 -c "import deepeval"` → `ModuleNotFoundError`), so nothing was executed against the real
library; the one place I needed runtime confirmation (`_maybe_jsonify` drop behaviour) I confirmed by
re-executing the *verbatim copied* function body against stand-in objects (§6.3).

---

## 0. Executive answer to AC-4.1

| Question | Answer |
|---|---|
| How many metric classes are there? | **56 total.** `deepeval/metrics/__init__.py:71-136` lists 53 `__all__` entries = 3 base classes + `DeepAcyclicGraph` + **49 metric classes** (counted mechanically). Plus `CitationFaithfulnessMetric` (community, `deepeval/metrics/community/__init__.py:1-7`) = **50 first-party**, plus 6 legacy RAGAS wrappers in `deepeval/metrics/ragas.py` = **56**. The AST walk over `deepeval/` independently found exactly these 56 `*Metric`/`GEval` classes. |
| How many are expressible **purely in YAML/JSON** with a thin provider? | **51 of 56** with zero code from the author, *given* the four provider-side shims in §7.2. |
| How many need code **from the author** today? | **0 metrics**, but **3 constructor parameter types** (`expected_schema`, `available_tools`, `dag`) and **1 whole subsystem** (component/span-level evals) require provider-side machinery that does not exist in DeepEval. |
| Does DeepEval ship **any** YAML/JSON eval-suite format? | **No.** Verified: `grep -rn "import yaml\|yaml.safe_load\|\.yaml\b" --include=*.py deepeval/` returns **zero hits**; there is no config-file schema and the CLI (`deepeval/cli/main.py`) is entirely `set-<provider>` env-var commands plus `view`/`gate`/`update-settings`/`set-debug`. The only declarative artefacts are (a) CSV/JSON/JSONL golden loaders, (b) `DeepAcyclicGraph.to_dict/from_dict`, (c) remote `metric_collection` / `GEval.pull()` (network). **PACT must author the config schema itself; there is nothing to adopt wholesale.** |
| Does the pipeline run air-gapped? | **Only with explicit opt-outs.** Import of `deepeval.telemetry` unconditionally initialises Sentry + PostHog and probes `www.google.com:80` unless `DEEPEVAL_TELEMETRY_OPT_OUT` is set (§8). |
| Biggest surprise (positive) | **`DAGMetric` has a complete, tested JSON round-trip** (`deepeval/metrics/dag/serialization/serialization.py`). The hardest custom metric in DeepEval is already a declarative document. |
| Biggest surprise (negative) | **Red-teaming is gone.** `deepeval/red_teaming/` contains only a README pointing at the separate `deepteam` package. There are **no attack generators, no jailbreak suites, no adversarial synthesis** in DeepEval 4.1.3. "Full DeepEval feature parity" for red-team therefore buys almost nothing (§5.6). |

---

## 1. The test-case data model (what metrics consume)

### 1.1 `LLMTestCase` — single-turn

`deepeval/test_case/llm_test_case.py:344-422`. Pydantic model, `extra="ignore"`.

| Field | Type | Default | Notes |
|---|---|---|---|
| `input` | `str` | **required** | Only required field. Must be `str` (`:493-495`). |
| `actual_output` | `Optional[str]` | `None` | Empty string is rejected as "missing" for metrics requiring it (`deepeval/metrics/utils.py:356-363`). |
| `expected_output` | `Optional[str]` | `None` | |
| `context` | `Optional[List[str]]` | `None` | Ground truth. Used only by `HallucinationMetric`. |
| `retrieval_context` | `Optional[List[Union[str, RetrievedContextData]]]` | `None` | `RetrievedContextData{context, source}` serialises to `"{source}: {context}"` (`:335-341`). |
| `metadata` | `Optional[Dict]` | `None` | alias `additionalMetadata` (deprecated accessor `:424-440`). |
| `tools_called` | `Optional[List[ToolCall]]` | `None` | |
| `expected_tools` | `Optional[List[ToolCall]]` | `None` | |
| `comments` | `Optional[str]` | `None` | |
| `token_cost` | `Optional[float]` | `None` | **Carried but no metric consumes it.** |
| `completion_time` | `Optional[float]` | `None` | **Carried but no metric consumes it.** |
| `multimodal` | `bool` | `False` | Auto-detected from `[DEEPEVAL:IMAGE:<id>]` / `[DEEPEVAL:PDF:<id>]` placeholders (`:442-478`). |
| `name`, `tags` | `Optional[str]`, `Optional[List[str]]` | `None` | |
| `mcp_servers` | `Optional[List[MCPServer]]` | `None` | |
| `mcp_tools_called` / `mcp_resources_called` / `mcp_prompts_called` | lists of `MCPToolCall`/`MCPResourceCall`/`MCPPromptCall` | `None` | **Results must be real `mcp.types.CallToolResult` / `ReadResourceResult` / `GetPromptResult` objects** (`:548-584`). |
| `custom_column_key_values` | `Optional[Dict[str,str]]` | `None` | |
| `_trace_dict` (private) | `Optional[Dict]` | `None` | The hook trace-based metrics read (§5.4). |

`SingleTurnParams` enum (`:179-192`): `input, actual_output, expected_output, context, retrieval_context,
metadata, tags, tools_called, expected_tools, mcp_servers, mcp_tools_called, mcp_resources_called,
mcp_prompts_called`. `LLMTestCaseParams` is a deprecated alias (`:195-204`).

`ToolCall` (`:247-257`): `name: str`, `type: ToolCallType{FUNCTION|MCP}`, `description`, `reasoning`,
`output: Any`, `input_parameters: Dict[str,Any]`. Equality is `(name, input_parameters, output)`
(`:259-266`) — **`description` and `reasoning` are ignored in comparisons.**

`MLLMImage` (`:39-176`): either `url` (local path / `file://` / `http(s)://`) or
`dataBase64`+`mimeType`. Local files are read and base64-encoded at construction (`:90-93`);
remote URLs are **not** fetched (`:86` sets `dataBase64 = None`). PDFs are supported
(`mimeType == "application/pdf"` → `[DEEPEVAL:PDF:...]`, `:102-104`). **Images are embedded into
strings as opaque placeholders**, which is how a single `str` field carries multimodal content.

### 1.2 `ConversationalTestCase` — multi-turn

`deepeval/test_case/conversational_test_case.py:190-222`.

| Field | Type | Default |
|---|---|---|
| `turns` | `List[Turn]` | **required, non-empty** (`:290-291`) |
| `scenario`, `context`, `name`, `user_description`, `expected_outcome`, `chatbot_role`, `metadata`, `comments`, `tags`, `mcp_servers`, `multimodal` | all optional | |

`Turn` (`:59-81`): `role: Literal["user","assistant"]` (**hard-coded two roles — no `system`, no
`tool` role**), `content: str`, `user_id`, `retrieval_context`, `tools_called`,
`mcp_tools_called`/`mcp_resources_called`/`mcp_prompts_called`, `metadata`.

`MultiTurnParams` enum (`:30-44`): `role, content, metadata, tags, scenario, expected_outcome,
context, user_description, retrieval_context, chatbot_role, tools_called, mcp_tools_called,
mcp_resources_called, mcp_prompts_called`. `TurnParams` is a deprecated alias (`:47-56`).

### 1.3 `ArenaTestCase` — comparison

`deepeval/test_case/arena_test_case.py:19-43`. `contestants: List[Contestant]`, where
`Contestant{name, test_case: LLMTestCase, hyperparameters}`. Validated: names unique, **all
contestants must share identical `input` and identical `expected_output`** (`:29-39`).

### 1.4 `Golden` / `ConversationalGolden` — dataset rows

`deepeval/dataset/golden.py:9-46` and `:120-146`. A `Golden` is an `LLMTestCase` minus
`token_cost`/`completion_time`/`mcp_*`, plus `source_file`. `ConversationalGolden` carries
`scenario` (required), `expected_outcome`, `user_description`, `turns`, `context`.
`Golden.additional_metadata` is the field name here (not `metadata`) — a real asymmetry with
`LLMTestCase.metadata`.

---

## 2. Base-class semantics shared by every metric

`deepeval/metrics/base_metric.py`.

| Attribute | Class default | Source |
|---|---|---|
| `threshold` | (no default at base; every subclass defaults it) | `:46` |
| `async_mode` | `True` | `:53` |
| `verbose_mode` | `True` at base, **but every concrete `__init__` defaults it to `False`** | `:54` |
| `include_reason` | `False` at base, **but every concrete `__init__` defaults it to `True`** | `:55` |
| `strict_mode` | `False` | `:52` |
| `requires_trace` | `False` | `:62` |
| `score`, `reason`, `success`, `error`, `evaluation_cost`, `input_tokens`, `output_tokens`, `verbose_logs`, `skipped`, `score_breakdown` | result slots | `:47-60` |

Three base classes: `BaseMetric` (single-turn, `:44`), `BaseConversationalMetric` (`:108`),
`BaseArenaMetric` (`:174`, returns a **winner string**, not a score, and has **no threshold**).

**Universal `strict_mode` semantics** (verified in every constructor):
`self.threshold = 1 if strict_mode else threshold`, and in `_calculate_score`
`return 0 if self.strict_mode and score < self.threshold else score`
(e.g. `deepeval/metrics/answer_relevancy/answer_relevancy.py:296-307`). I.e. strict mode
**binarises**: pass ⇒ keep score, fail ⇒ 0.

**Missing-parameter handling** (`deepeval/metrics/utils.py:365-383`): a `None` required param raises
`MissingTestCaseParamsError`; `ErrorConfig.skip_on_missing_params` converts this to a *skip*.
Empty-string `actual_output` is treated as missing (`:356-363`).

**Prompt templates are data, not code.** All judge prompts live in
`deepeval/templates/metrics/templates.json` (178 KB, 51 top-level class keys) and are rendered
through Jinja2 by `resolve_template()` (`deepeval/templates/resolver.py:184-216`), keyed by
`(class_name, method)` where `method` is one of 55 enumerated names (`:16-66`).
**Negative finding:** the registry loads only the packaged bundle via
`resources.files("deepeval.templates")` (`deepeval/templates/resolver.py:100-111`). There is
**no public override/extension hook** — you cannot point DeepEval at your own prompt bundle without
monkeypatching `_registry._base_templates` or replacing the installed file. `clear_metric_template_cache()`
(`:139-140`) is the only related public API. The `deepeval/metrics/README.md:14-18` describes a
`metric_templates/community/templates.<language>.json` translation layer, but **no `community/`
directory ships in this build** (only `templates/metrics/templates.json` and `templates/metrics/fragments/`).

---

## 3. THE COMPLETE METRIC INVENTORY

Legend for **Config-only?**
- **YES** — every constructor arg is a scalar / string / list-of-strings; direct YAML mapping.
- **YES\*** — needs one provider-side shim (named in the last column) but **zero author code**.
- **YES†** — config-only but only because PACT owns the harness and must synthesise a structure
  DeepEval expects (trace dict, arena contestants).
- **NO** — cannot be expressed without author-supplied Python.

Legend for **Judge?**: `LLM` = calls the evaluation model; `DET` = fully deterministic;
`LLM?` = deterministic unless an optional arg is supplied.

### 3.1 Deterministic / non-LLM metrics (2)

| Metric | File:line (class / `__init__`) | Constructor params & defaults | Required test-case fields | Judge? | Async | Config-only? | Notes / minimal declarative construct |
|---|---|---|---|---|---|---|---|
| `ExactMatchMetric` | `metrics/exact_match/exact_match.py:12` / `:19` | `threshold=1`, `verbose_mode=False` | `input`, `actual_output`, `expected_output` | DET | `a_measure` delegates to sync (`:92-102`) | **YES** | `.strip()`-compared equality; sets `precision=recall=f1=score` (`:47-56`). |
| `PatternMatchMetric` | `metrics/pattern_match/pattern_match.py:13` / `:19` | `pattern: str` **(required)**, `ignore_case=False`, `threshold=1.0`, `verbose_mode=False` | `input`, `actual_output` | DET | delegates to sync | **YES** | ⚠ **Uses `re.fullmatch`, not `search`** (`:60`). Bad regex raises at construction (`:31-34`). |

### 3.2 Custom / composable metrics (5)

| Metric | File:line | Constructor params & defaults | Required fields | Judge? | Config-only? | Minimal declarative construct |
|---|---|---|---|---|---|---|
| `GEval` | `metrics/g_eval/g_eval.py:45` / `:46` | `name: str` **(req)**, `evaluation_params: List[SingleTurnParams]=None`, `criteria: str=None`, `evaluation_steps: List[str]=None`, `rubric: List[Rubric]=None`, `model=None`, `threshold=0.5`, `top_logprobs=20`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | whichever `evaluation_params` names | LLM | **YES\*** | `evaluation_params` → list of enum *string values*. `rubric` → list of `{score_range: [a,b], expected_outcome: str}`; ranges must be 0–10 and non-overlapping (`metrics/g_eval/utils.py:39-50`, `:210-230`). Exactly one of `criteria`/`evaluation_steps` required (`:189-207`). Empty `evaluation_params` list raises (`g_eval.py:61-62`). Shim: map YAML dicts → `Rubric(...)`. |
| `ConversationalGEval` | `metrics/conversational_g_eval/conversational_g_eval.py:43` / `:44` | same shape but `evaluation_params: List[MultiTurnParams]` | conversational turns | LLM | **YES\*** | Same shim. Note: **no `include_reason`, no `window_size`** — evaluates the whole conversation. |
| `ArenaGEval` | `metrics/arena_g_eval/arena_g_eval.py:35` / `:36` | `name` **(req)**, `evaluation_params: List[SingleTurnParams]` **(req)**, `criteria=None`, `evaluation_steps=None`, `model=None`, `async_mode=True`, `verbose_mode=False` | all contestants' cases | LLM | **YES†** | **No threshold, no score** — `measure()` returns a winner name string (`:114`); `success` is hard-set `True` (`:105`). Contestant names are **masked with dummy names before judging** and un-masked afterwards (`metrics/arena_g_eval/utils.py:94-129`) — a built-in name-bias mitigation worth copying. PACT construct: `compare: { candidates: [...], criteria: ... }`; harness builds `ArenaTestCase`. |
| `DAGMetric` | `metrics/dag/dag.py:23` / `:25` | `name` **(req)**, `dag: DeepAcyclicGraph` **(req)**, `model=None`, `threshold=0.5`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | **derived** from node `evaluation_params` via `extract_required_params` (`metrics/dag/utils.py:104-134`) | LLM | **YES\*** | The graph has a **complete JSON form** — see §4. Shim: `DeepAcyclicGraph.from_dict(doc, multiturn=False)`. |
| `ConversationalDAGMetric` | `metrics/conversational_dag/conversational_dag.py:22` / `:24` | same, `dag` built from `Conversational*` nodes | derived | LLM | **YES\*** | `DeepAcyclicGraph.from_dict(doc, multiturn=True)`. Nodes additionally accept `turn_window: Tuple[int,int]` (`metrics/conversational_dag/nodes.py:179,263,365`). |

### 3.3 RAG metrics (5)

| Metric | File:line | Constructor params & defaults | Required fields | Judge? | Config-only? |
|---|---|---|---|---|---|
| `AnswerRelevancyMetric` | `metrics/answer_relevancy/answer_relevancy.py:26` / `:32` | `threshold=0.5`, `model=None`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | `input`, `actual_output` | LLM | **YES** |
| `FaithfulnessMetric` | `metrics/faithfulness/faithfulness.py:51` / `:58` | + `truths_extraction_limit: Optional[int]=None`, `penalize_ambiguous_claims=False` | `input`, `actual_output`, `retrieval_context` | LLM | **YES** |
| `ContextualPrecisionMetric` | `metrics/contextual_precision/contextual_precision.py:45` / `:52` | standard six | `input`, `retrieval_context`, `expected_output` | LLM | **YES** |
| `ContextualRecallMetric` | `metrics/contextual_recall/contextual_recall.py:57` / `:65` | standard six | `input`, `retrieval_context`, `expected_output` | LLM | **YES** |
| `ContextualRelevancyMetric` | `metrics/contextual_relevancy/contextual_relevancy.py:59` / `:65` | standard six | `input`, `retrieval_context` | LLM | **YES** |

*"standard six" = `threshold=0.5, model=None, include_reason=True, async_mode=True, strict_mode=False, verbose_mode=False`.*

### 3.4 Content-quality metrics (4)

| Metric | File:line | Constructor params & defaults | Required fields | Judge? | Config-only? |
|---|---|---|---|---|---|
| `HallucinationMetric` | `metrics/hallucination/hallucination.py:25` / `:32` | standard six | `input`, `actual_output`, **`context`** (not `retrieval_context`) | LLM | **YES** |
| `BiasMetric` | `metrics/bias/bias.py:26` / `:32` | standard six | `input`, `actual_output` | LLM | **YES** |
| `ToxicityMetric` | `metrics/toxicity/toxicity.py:26` / `:33` | standard six | `input`, `actual_output` | LLM | **YES** |
| `SummarizationMetric` | `metrics/summarization/summarization.py:36` / `:43` | `threshold=0.5`, **`n: int = 5`**, `model=None`, **`assessment_questions: Optional[List[str]]=None`**, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False`, `truths_extraction_limit=None` | `input`, `actual_output` | LLM | **YES** (`assessment_questions` is a YAML string list) |

### 3.5 Safety / compliance metrics (6)

| Metric | File:line | Constructor params & defaults | Required fields | Judge? | Config-only? |
|---|---|---|---|---|---|
| `PIILeakageMetric` | `metrics/pii_leakage/pii_leakage.py:26` / `:32` | standard six | `input`, `actual_output` | LLM | **YES** |
| `NonAdviceMetric` | `metrics/non_advice/non_advice.py:29` / `:35` | **`advice_types: List[str]` (req)** + standard six | `input`, `actual_output` | LLM | **YES** |
| `MisuseMetric` | `metrics/misuse/misuse.py:26` / `:32` | **`domain: str` (req)** + standard six | `input`, `actual_output` | LLM | **YES** |
| `RoleViolationMetric` | `metrics/role_violation/role_violation.py:26` / `:32` | `threshold=0.5`, **`role: str = None`** (positional #2), + rest | `input`, `actual_output` | LLM | **YES** |
| `ToolPermissionMetric` | `metrics/tool_permission/tool_permission.py:12` / `:34` | `allowed_tools: Optional[List[str]]=None`, `denied_tools: Optional[List[str]]=None`, `threshold=1.0`, `include_reason=True`, `strict_mode=False`, `verbose_mode=False` | **`tools_called` only** | **DET** | **YES** — at least one list required (`:43-48`); deny wins over allow; score = fraction authorised; `1.0` when no tools called; `async_mode` forced `False` (`:60`). **This is the ideal template for PACT's deterministic policy gates.** |
| `RoleAdherenceMetric` | `metrics/role_adherence/role_adherence.py:22` / `:25` | standard six | conversational `role`,`content` **+ `chatbot_role` on the test case** (`:78`) | LLM | **YES** |

### 3.6 Agentic metrics (7 + 2 task-specific tool metrics)

| Metric | File:line | Constructor params & defaults | Required fields | Judge? | Trace? | Config-only? |
|---|---|---|---|---|---|---|
| `TaskCompletionMetric` | `metrics/task_completion/task_completion.py:25` / `:32` | `threshold=0.5`, **`task: Optional[str]=None`**, + rest | `input`, `actual_output` | LLM | **`requires_trace=True`** (`:55`) | **YES†** — reads `test_case._trace_dict` if present, else falls back to a deprecated input/output/tools prompt (`:185-200`). |
| `PlanAdherenceMetric` | `metrics/plan_adherence/plan_adherence.py:26` / `:33` | standard six | `input`, `actual_output` | LLM | **yes** (`:49`) | **YES†** |
| `PlanQualityMetric` | `metrics/plan_quality/plan_quality.py:26` / `:33` | standard six | `input`, `actual_output` | LLM | **yes** (`:49`) | **YES†** |
| `StepEfficiencyMetric` | `metrics/step_efficiency/step_efficiency.py:18` / `:25` | standard six | `input`, `actual_output` | LLM | **yes** (`:41`) | **YES†** |
| `AgentLoopDetectionMetric` | `metrics/agent_loop_detection/agent_loop_detection.py:65` / `:119` | `threshold=0.5`, `repetition_threshold=3`, `similarity_threshold=0.85`, `check_tool_repetition=True`, `check_reasoning_stagnation=True`, `check_call_graph_cycles=True`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | `input`, `actual_output` | **DET** (`:92-98` docstring; `self.model=None` at `:138`) | **yes** (`:145`) | **YES†** — three weighted sub-signals: identical `(name,args)` repetition; bigram-Jaccard + `difflib.SequenceMatcher` stagnation on consecutive LLM spans; DFS cycle detection on `type:name:input_hash` labels. **Deterministic *and* trace-based** — exactly the shape AC-4.5 wants. |
| `ArgumentCorrectnessMetric` | `metrics/argument_correctness/argument_correctness.py:26` / `:32` | standard six | `input`, **`tools_called`** | LLM | no | **YES** |
| `ToolCorrectnessMetric` | `metrics/tool_correctness/tool_correctness.py:24` / `:32` | **`available_tools: List[ToolCall]=None`**, `threshold=0.5`, **`evaluation_params: List[ToolCallParams]=[]`**, `model=None`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False`, `should_exact_match=False`, `should_consider_ordering=False` | `input`, `tools_called`, `expected_tools` | **LLM?** — deterministic unless `available_tools` is supplied, which triggers an LLM "tool selection" pass (`:92-99`) and `score = min(calling, selection)` (`:104`) | no | **YES\*** — `available_tools` must be `ToolCall` objects; `evaluation_params` ∈ `{input_parameters, output}` (`test_case/llm_test_case.py:207-209`). |
| `ToolUseMetric` | `metrics/tool_use/tool_use.py:29` / `:36` | **`available_tools: List[ToolCall]` (required, positional)** + standard six | conversational `role`,`content` | LLM | no | **YES\*** |
| `TopicAdherenceMetric` | `metrics/topic_adherence/topic_adherence.py:24` / `:31` | **`relevant_topics: List[str]` (req)** + standard six | conversational `role`,`content` | LLM | no | **YES** |
| `GoalAccuracyMetric` | `metrics/goal_accuracy/goal_accuracy.py:25` / `:32` | standard six | conversational `role`,`content` | LLM | no | **YES** |

### 3.7 Conversational (multi-turn) metrics (6 + 3 above)

| Metric | File:line | Extra params | Required fields | Judge? | Config-only? |
|---|---|---|---|---|---|
| `TurnRelevancyMetric` | `metrics/turn_relevancy/turn_relevancy.py:27` / `:30` | `window_size=10`, `template_class: Optional[str]=None` | `role`,`content` | LLM | **YES** (`template_class` is an escape hatch — see §7.4) |
| `TurnFaithfulnessMetric` | `metrics/turn_faithfulness/turn_faithfulness.py:41` / `:48` | `truths_extraction_limit=None`, `penalize_ambiguous_claims=False`, `window_size=10` | `role`,`content`,`retrieval_context` | LLM | **YES** |
| `TurnContextualPrecisionMetric` | `metrics/turn_contextual_precision/turn_contextual_precision.py:48` / `:56` | `window_size=10` | `role`,`content`,`retrieval_context`,**`expected_outcome`** | LLM | **YES** |
| `TurnContextualRecallMetric` | `metrics/turn_contextual_recall/turn_contextual_recall.py:57` / `:65` | `window_size=10` | `role`,`content`,`retrieval_context`,**`expected_outcome`** | LLM | **YES** |
| `TurnContextualRelevancyMetric` | `metrics/turn_contextual_relevancy/turn_contextual_relevancy.py:60` / `:67` | `window_size=10` | `role`,`content`,`retrieval_context` | LLM | **YES** |
| `ConversationCompletenessMetric` | `metrics/conversation_completeness/conversation_completeness.py:26` / `:29` | **`window_size=3`** (note: different default) | `role`,`content` | LLM | **YES** |
| `KnowledgeRetentionMetric` | `metrics/knowledge_retention/knowledge_retention.py:23` / `:26` | standard six | `role`,`content` | LLM | **YES** |

Windowing: `get_turns_in_sliding_window(unit_interactions, window_size)` produces overlapping windows;
one verdict per window; score is the mean (`metrics/turn_relevancy/turn_relevancy.py:86-96`).

### 3.8 MCP metrics (3)

| Metric | File:line | Params | Required fields | Judge? | Config-only? |
|---|---|---|---|---|---|
| `MCPUseMetric` | `metrics/mcp_use_metric/mcp_use_metric.py:26` / `:33` | standard six | `input`, `actual_output`, **`mcp_servers`** | LLM | **YES\*** — `MCPServer{server_name, transport∈{stdio,sse,streamable-http}, available_tools, available_resources, available_prompts}` (`test_case/mcp.py:22-28`). `available_*` accept **plain dicts** as well as `mcp.types` objects (`:38-49`), so YAML works. |
| `MCPTaskCompletionMetric` | `metrics/mcp/mcp_task_completion.py:25` / `:31` | standard six | conversational `role`,`content` **+ non-empty `mcp_servers`** (`:81-82`) | LLM | **YES\*** |
| `MultiTurnMCPUseMetric` | `metrics/mcp/multi_turn_mcp_use_metric.py:28` / `:34` | standard six | conversational `role`,`content` (+ MCP turn data) | LLM | **YES\*** |

⚠ **`MCPToolCall.result` etc. must be genuine `mcp.types.CallToolResult` / `ReadResourceResult` /
`GetPromptResult` instances** — validated by `isinstance` (`test_case/llm_test_case.py:548-584`,
`test_case/conversational_test_case.py:157-185`). A YAML author cannot produce these; the PACT
harness must construct them from the MCP transport it already drives.

### 3.9 Multimodal metrics (5)

All five are `BaseMetric` subclasses reading `[DEEPEVAL:IMAGE:...]` placeholders in `input` /
`actual_output`. **Image counts are hard-coded per metric** in the `check_llm_test_case_params(...,
input_image_count, actual_output_image_count, ...)` call.

| Metric | File:line | Params | Image contract | Config-only? |
|---|---|---|---|---|
| `TextToImageMetric` | `metrics/multimodal_metrics/text_to_image/text_to_image.py:29` / `:30` | `model=None`, `threshold=0.5`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | **0 input images, exactly 1 output image** (`:51-59`) | **YES** |
| `ImageEditingMetric` | `.../image_editing/image_editing.py:24` / `:31` | same | **exactly 1 in, 1 out** (`:53-58`) | **YES** |
| `ImageCoherenceMetric` | `.../image_coherence/image_coherence.py:24` / `:30` | + `max_context_size: Optional[int]=None` | free-form | **YES** |
| `ImageHelpfulnessMetric` | `.../image_helpfulness/image_helpfulness.py:24` / `:31` | + `max_context_size` | free-form | **YES** |
| `ImageReferenceMetric` | `.../image_reference/image_reference.py:24` / `:31` | + `max_context_size` | free-form | **YES** |

⚠ **No `include_reason` on any multimodal metric.** ⚠ **No audio, no video, no computer-use metric
exists anywhere in DeepEval.** The only non-text modalities are image and PDF. This is a hard gap
against **D16 (all four modalities in v1)** — see §9.

**Multimodal judge gating** (`metrics/utils.py:314-331`): if the test case is multimodal, the judge
model must return `supports_multimodal() == True` or the metric raises. `LocalModel.supports_multimodal`
exists (`models/llms/local_model.py:203`), so an OpenAI-compatible local VLM can serve as judge —
important for D17.

### 3.10 Community metric (1, not in `__all__`)

| Metric | File:line | Params | Required fields |
|---|---|---|---|
| `CitationFaithfulnessMetric` | `metrics/community/citation_faithfulness/citation_faithfulness.py:23` / `:50` | `threshold=1.0`, `model=None`, `include_reason=True`, `async_mode=True`, `strict_mode=False`, `verbose_mode=False` | `input`, `actual_output`, `retrieval_context` |

### 3.11 Legacy RAGAS wrappers (6, not in `__all__`, `deepeval/metrics/ragas.py`)

`RAGASContextualPrecisionMetric` (`:38`/`:41`), `RAGASContextualRecallMetric` (`:119`/`:122`),
`RAGASContextualEntitiesRecall` (`:192`/`:195`), `RAGASAnswerRelevancyMetric` (`:342`/`:345`),
`RAGASFaithfulnessMetric` (`:424`/`:425`), `RagasMetric` (composite mean of the five, `:496`/`:499`).

All default to **`model="gpt-3.5-turbo"`** and require `langchain_core` (`:12-27`) + `ragas` +
HuggingFace `datasets` (`:521-531`). `RagasMetric.__init__` takes an `embeddings: Embeddings` object
→ **code required**. **Recommendation: do not expose these in PACT.** Use a first-class `ragas:`
provider instead (D6 already allows this).

### 3.12 Other task-specific metrics (2)

| Metric | File:line | Params | Required fields | Config-only? |
|---|---|---|---|---|
| `PromptAlignmentMetric` | `metrics/prompt_alignment/prompt_alignment.py:27` / `:34` | **`prompt_instructions: List[str]` (req)** + standard six | `input`, `actual_output` | **YES** |
| `JsonCorrectnessMetric` | `metrics/json_correctness/json_correctness.py:24` / `:30` | **`expected_schema: BaseModel` (req, positional)**, `model=None`, `threshold=0.5`, `async_mode=True`, `include_reason=True`, **`strict_mode=True`** (only metric defaulting strict on), `verbose_mode=False` | `input`, `actual_output` | **YES\*** — score is binary `1/0` from `expected_schema.model_validate_json(actual_output)` (`:85-92`). The object must implement **`model_validate_json()`** (`:87,137`) and **`model_json_schema()`** (`:168,193`). See §7.2 shim. |

---

## 4. `DAGMetric` — the one construct DeepEval already made declarative

This is the single most consequential discovery for AC-4.1.

### 4.1 Node algebra

`deepeval/metrics/dag/nodes.py`:

| Node | Fields | Rules |
|---|---|---|
| `TaskNode` (`:141`) | `instructions: str`, `output_label: str`, `children: List[BaseNode]`, `evaluation_params: Optional[List[SingleTurnParams]]`, `label: Optional[str]` | children may not be `VerdictNode` (`:168-171`); must have `evaluation_params` or a parent (`:180-183`). LLM produces free text under `output_label`. |
| `BinaryJudgementNode` (`:225`) | `criteria: str`, `children: List[VerdictNode]`, `evaluation_params`, `label` | **exactly 2 children, one `verdict=True`, one `verdict=False`** (`:252-268`). |
| `NonBinaryJudgementNode` (`:314`) | `criteria: str`, `children: List[VerdictNode]`, `evaluation_params`, `label` | ≥1 child, all string verdicts, unique; builds a `Literal[...]` pydantic schema at validate time (`:341-365`) → **constrained decoding for free**. |
| `VerdictNode` (`:50`) | `verdict: Union[str,bool]`, `score: Optional[int]`, `child: Optional[Union[BaseNode, GEval, BaseMetric]]` | **XOR: exactly one of `score`/`child`** (`:58-66`); `0 ≤ score ≤ 10` (`:67-68`). |

`DeepAcyclicGraph` (`metrics/dag/graph.py:38-84`): multiple roots allowed **unless** a judgement node
is a root (`:52-58`); cycle detection during construction (`:69-70`); single/multi-turn nodes may not
be mixed (`:19-23`). Conversational variants add `turn_window: Optional[Tuple[int,int]]`.

**Composability:** a `VerdictNode.child` may be *any* `BaseMetric` — so the DAG is a decision tree
whose leaves can be full metrics (e.g. "if the answer cites a source → run `FaithfulnessMetric`").
This is a genuinely powerful, and genuinely declarative, metric combinator.

### 4.2 The JSON document format

`deepeval/metrics/dag/serialization/serialization.py:1-27` (docstring) and `:70-175`:

```json
{
  "nodes": {
    "<uuid>": {
      "type": "TaskNode" | "BinaryJudgementNode" | "NonBinaryJudgementNode" | "VerdictNode",
      "instructions": "...", "output_label": "...",      // TaskNode
      "criteria": "...",                                  // judgement nodes
      "label": "...",
      "evaluation_params": ["input", "actual_output"],    // enum *values*, not names
      "turn_window": [0, 5],                              // multiturn only
      "children": ["<uuid>", ...],
      "verdict": true | "some-string",                    // VerdictNode
      "score": 10,                                        // XOR with "child"
      "child": { "type": "node",   "ref": "<uuid>" }
             | { "type": "geval",  "name": "...", "criteria": "...", ... }
             | { "type": "metric", "metric_class": "FaithfulnessMetric", "kwargs": {...} }
    }
  }
}
```

- `NodeType` / `ChildType` enums: `serialization/types.py:1-13`.
- Class registry (single-turn ↔ conversational): `serialization/registry.py:19-38`.
- **Roots are inferred** as nodes never referenced as a child (`:123-129`).
- **Mode (`multiturn`) is NOT in the document** — the caller supplies it
  (`graph.py:117-131`, docstring `serialization.py:9-11`). *PACT must carry this out-of-band.*
- `metric_class` is resolved by `getattr(importlib.import_module("deepeval.metrics"), name)`
  (`:513-519`) — i.e. **any metric in `__all__` is nameable from JSON**.
- DAG shape is preserved including **shared sub-graphs** (a node referenced from two verdicts
  rebuilds as the *same Python object* — asserted in `tests/test_metrics/test_dag_serialization.py:220`).
- Round-trip is covered by 21 tests (`tests/test_metrics/test_dag_serialization.py`, incl. multiturn
  `:241`, `turn_window` `:265`, cycle rejection `:350`, unknown-metric rejection `:323`).

### 4.3 What the JSON form silently loses ⚠

`_maybe_jsonify` (`serialization/serialization.py:354-383`) returns `_SKIP` for anything that is not
`None`/`bool`/`int`/`float`/`str`/`list`/`tuple`/`dict`/`Enum`, and skipped keys are **dropped
without warning** (`:310-312`, `:331-334`).

I copied that function verbatim and executed it against stand-ins:

| Value | Result |
|---|---|
| `[Rubric(...), Rubric(...)]` (GEval rubric) | **`_SKIP` → dropped** |
| `[ToolCall(...)]` (`available_tools`) | **`_SKIP` → dropped** |
| a class object (`expected_schema`) | **`_SKIP` → dropped** |
| `(0, 4)` tuple | `[0, 4]` (kept) |

**Consequences:**
1. `dag_to_dict` on a DAG whose leaf is a `GEval` **with a rubric** silently produces a document that
   rebuilds a *rubric-less* GEval — a different metric with a different score range
   (`get_score_range` returns `(0,10)` when rubric is `None`, `metrics/g_eval/utils.py:400-403`).
2. Same for `ToolCorrectnessMetric(available_tools=...)` and `JsonCorrectnessMetric(expected_schema=...)`
   as DAG leaves.
3. `model` (a `DeepEvalBaseLLM` instance) is also dropped — acceptable, since PACT binds models.

**This is a silent-loss path and violates T7/AC-7.1 if PACT reuses `dag_to_dict` for export.**
PACT must own serialisation (author YAML → DAG), never round-trip through `dag_to_dict`, **or** must
diff the document against the live object and fail closed.

---

## 5. Non-metric surfaces

### 5.1 Evaluation entry points

`deepeval/evaluate/evaluate.py`:
- `assert_test(test_case=None, metrics=None, golden=None, run_async=True)` (`:67`) — pytest integration.
- `evaluate(test_cases, metrics=None, metric_collection=None, hyperparameters=None, identifier=None,
  official=False, _skip_reset=False, async_config=AsyncConfig(), display_config=DisplayConfig(),
  cache_config=CacheConfig(), error_config=ErrorConfig())` (`:158`).
- `compare(test_cases: List[ArenaTestCase], metric: ArenaGEval, name="compare()", ...)`
  (`deepeval/evaluate/compare.py:43`).

Config dataclasses (`deepeval/evaluate/configs.py`):
- `AsyncConfig(run_async=True, throttle_value=0, max_concurrent=20)` (`:8-17`)
- `DisplayConfig(show_indicator=True, print_results=True, verbose_mode=None,
  display_option=TestRunResultDisplay.ALL, results_folder=None, results_subfolder=None,
  truncate_passing_cases=True, inspect_after_run=True, file_type=None, file_output_dir=None)` (`:21-35`)
- `CacheConfig(write_cache=True, use_cache=False)` (`:39-41`)
- `ErrorConfig(ignore_errors=False, skip_on_missing_params=False)` (`:45-47`)

**All four are pure scalars — 100 % config-expressible.** `metric_collection: str` pulls metric
definitions from Confident AI (network) and must be **banned in air-gapped profiles**.

**Critical structural point:** `evaluate()` takes test cases whose `actual_output` is *already filled*.
DeepEval never runs your agent. `EvaluationDataset.evals_iterator(...)` (`deepeval/dataset/dataset.py:1513`)
yields `Golden`s inside a traced loop so you can call your app — **but the call is your Python code**.
For PACT this is a feature, not a problem: PACT owns the harness (D12), so PACT supplies the loop and
the author supplies nothing.

### 5.2 Aggregation & reporting

`deepeval/evaluate/utils.py:394-515`: only **average score** and **pass rate** per metric.
`deepeval/evaluate/console_report.py:234-240`, `:382-388`.

**Negative finding — verified by exhaustive grep:** DeepEval has **no** confidence intervals,
**no** standard error, **no** bootstrap, **no** epochs/repeats, **no** score reducers. The only
`bootstrap` hits in the package are the MIPROv2 demonstration bootstrapper and prompt-cache
bootstrapping — unrelated. See §9.3 for what `inspect_ai` offers instead.

### 5.3 Datasets & goldens — the one genuinely declarative surface

`deepeval/dataset/dataset.py` loaders (all local files, no network):
- `add_test_cases_from_csv_file(...)` (`:255`) — ~13 column-name params + delimiters.
- `add_test_cases_from_json_file(...)` (`:407`).
- `add_goldens_from_csv_file(...)` (`:487`) — 20 params, includes conversational columns
  (`scenario`, `turns`, `expected_outcome`, `user_description`).
- `add_goldens_from_json_file(...)` (`:672`), `add_goldens_from_jsonl_file(...)` (`:755`).
- `save_as(file_type: Literal["json","csv","jsonl"], directory, file_name=None, include_test_cases=False)` (`:1167`).

Network-only: `push` (`:887`), `pull` (`:925`), `create_version` (`:1012`), `get_versions` (`:1033`),
`queue` (`:1043`), `delete` (`:1081`).

**PACT should adopt the golden field set verbatim and skip the column-mapping parameters entirely** —
PACT's own CSV/JSONL reader can require canonical column names, which is simpler for a non-programmer.

### 5.4 Tracing (`@observe`) — how trace-based metrics get data

`deepeval/tracing/tracing.py:1316`:
```
observe(func=None, *, metrics=None, metric_collection=None,
        type: Optional[Union[Literal["agent","llm","retriever","tool"], str]]=None, ...)
```
Span types (`deepeval/tracing/types.py`): `BaseSpan` (`:87`) with
`uuid, status, children, trace_uuid, parent_uuid, start_time, end_time, name, metadata, input, output,
error, llm_test_case, metrics, metric_collection, integration, retrieval_context, context,
expected_output, tools_called, expected_tools`; specialisations `AgentSpan{available_tools,
agent_handoffs}` (`:128`), `LlmSpan{model, provider, prompt, input_token_count, output_token_count,
cost_per_input_token, cost_per_output_token, token_intervals, prompt_alias/version/label/commit_hash}`
(`:134`), `RetrieverSpan{embedder, top_k, chunk_size}` (`:171`), `ToolSpan{name, description}` (`:177`).
`Trace` (`:182`) adds `tags, thread_id, user_id, test_case_id, test_run_id, turn_id, environment`.

Imperative context API (`deepeval/tracing/context.py`): `update_current_span` (`:64`),
`update_current_trace` (`:120`), `update_llm_span` (`:190`), `update_agent_span` (`:223`),
`update_tool_span` (`:244`), `update_retriever_span` (`:261`), plus `next_*_span` variants
(`:357-560`) for pre-declaring the next span's attributes.

`TraceManager.configure(mask: Optional[Callable], environment, sampling_rate, confident_api_key,
anthropic_client, openai_client, tracing_enabled)` (`tracing/tracing.py:249`) — **`mask` is a callable
⇒ redaction is code-only in DeepEval.**

**Design consequence for PACT.** Component/span-level evals in DeepEval require
`@observe(metrics=[...])` decorators on the author's functions — irreducibly code.
**Because PACT owns the loop (D12), PACT's harness emits the spans and can attach metrics from a
YAML selector.** This turns DeepEval's most code-bound feature into a config-only one *only if PACT
runs the agent*. This is a strong independent argument for harness lowering.

`LlmSpan.token_intervals: Dict[float,str]` (`types.py:143`) is a per-token timestamp map — the raw
material for TTFT/TPOT SLOs (O4.2) — but **no DeepEval metric consumes it**. PACT must compute SLO
predicates itself.

### 5.5 Synthesizer (golden generation)

`deepeval/synthesizer/synthesizer.py:118`:
```
Synthesizer(model=None, async_mode=True, max_concurrent=100,
            filtration_config=None, evolution_config=None, styling_config=None,
            conversational_styling_config=None, cost_tracking=False)
```
Configs (`deepeval/synthesizer/config.py`), **all pure scalars ⇒ fully config-expressible**:
- `FiltrationConfig(synthetic_input_quality_threshold=0.5, max_quality_retries=3, critic_model=None)` (`:11`)
- `EvolutionConfig(num_evolutions=1, evolutions={7 Evolution enum → 1/7 each})` (`:21`)
- `StylingConfig(scenario, task, input_format, expected_output_format)` (`:37`)
- `ConversationalStylingConfig(scenario_context, conversational_task, participant_roles, scenario_format, expected_outcome_format)` (`:45`)
- `ContextConstructionConfig(embedder, critic_model, encoding, max_contexts_per_document=3,
  min_contexts_per_document=1, max_context_length=3, min_context_length=1, chunk_size=1024,
  chunk_overlap=0, context_quality_threshold=0.5, context_similarity_threshold=0.0, max_retries=3,
  allow_cross_file_contexts=False, target_files_per_context=None, max_files_per_context=3)` (`:54`)

`Evolution` enum (`synthesizer/types.py:4-12`): `Reasoning, Multi-context, Concretizing, Constrained,
Comparative, Hypothetical, In-Breadth`. `PromptEvolution` (`:14-21`) drops `Multi-context`.

Generation entry points: `generate_goldens_from_docs` (`:422`), `..._from_contexts` (`:672`),
`..._from_scratch` (`:1271`), `..._from_goldens` (`:1379`), plus `generate_conversational_goldens_*`
(`:2055`, `:2301`, `:2882`, `:3176`), each with an `a_` async twin. `save_as(json|csv|jsonl)` (`:1885`).

**Verdict: 100 % config-only.** This directly serves D19 on-ramp 4 (builder-agent generated,
human-approved).

### 5.6 Red teaming — **absent**

`deepeval/red_teaming/README.md` is the entire module:
> "# The Red Teaming module is now in DeepTeam for deepeval-v3.0 onwards
>  Please go to https://github.com/confident-ai/deepteam to get the latest version."

There is no `deepteam` clone in the local corpus. **"DeepEval parity" for red-team = the six
safety *judges* in §3.5 and nothing else.** No attack generation, no jailbreak templates, no
multi-turn adversarial escalation, no vulnerability taxonomy.

### 5.7 Guardrails — **absent**

Exhaustive grep for `guardrail` across `deepeval/` returns only three files, none of which is a
guardrails implementation: `telemetry.py:22` (a `Feature.GUARDRAIL = "guardrail"` telemetry enum
value — vestigial), `openai_agents/callback_handler.py`, `openai_agents/extractors.py`.
**There is no runtime guardrail/input-output-filter subsystem in DeepEval 4.1.3.**

### 5.8 Conversation simulator

`deepeval/simulator/conversation_simulator.py:46`:
```
ConversationSimulator(model_callback: Callable[[str], str],          # ← CODE
                      simulation_graph: Optional[SimulationNode]=None,
                      stopping_controller: Callable=expected_outcome_controller,  # ← CODE
                      simulator_model=None, max_concurrent=5, async_mode=True,
                      language="English", controller=_MISSING)
```
`simulate(conversational_goldens, max_user_simulations=10, on_simulation_complete: Optional[Callable])` (`:98`).

**Two required callables ⇒ code today.** In PACT the `model_callback` is *the agent under test*
(the harness supplies it) and the `stopping_controller` should be a declarative predicate
(`stop_when: expected_outcome_reached | max_turns | judge(criteria)`).

### 5.9 Prompt optimizer (embedded GEPA/MIPROv2/COPRO/SIMBA)

`deepeval/optimizer/prompt_optimizer.py:52`:
```
PromptOptimizer(model_callback: ModelCallback,          # Callable[[Prompt, Golden], str] ← CODE
                metrics: List[BaseMetric],
                optimizer_model=None,
                algorithm: Union[GEPA, MIPROV2, COPRO, SIMBA] = GEPA(),
                async_config=AsyncConfig(), display_config=DisplayConfig())
optimize(prompt: Prompt, goldens) / a_optimize(...)      (:86, :107)
```
Algorithms, all scalar-configured:
- `GEPA(iterations=5, minibatch_size=8, pareto_size=3, random_seed=None, patience=3,
  tie_breaker=TieBreaker.PREFER_CHILD, aggregate_instances=mean_of_all,
  reflection_model='gpt-4o-mini', mutation_model='gpt-4o', scorer=None)`
  (`optimizer/algorithms/gepa/gepa.py:59`)
- `MIPROV2(num_trials=30, num_candidates=10, max_bootstrapped_demonstrations=4,
  max_labeled_demonstrations=4, num_demonstration_sets=5, minibatch_size=25,
  minibatch_full_eval_steps=10, random_state=None)` (`optimizer/algorithms/miprov2/miprov2.py:44`)
- `COPRO(depth=4, breadth=7, minibatch_size=25, random_state=None)` (`optimizer/algorithms/copro/copro.py:34`)
- `SIMBA(iterations=8, minibatch_size=15, num_candidates=4, num_samples=3,
  minibatch_full_eval_steps=4, random_state=None)` (`optimizer/algorithms/simba/simba.py:37`)

`BaseAlgorithm` ABI (`optimizer/algorithms/base.py:10-27`):
`execute(prompt, goldens)` / `a_execute(prompt, goldens)` with `name, optimizer_model, scorer`.
`OptimizationReport{optimization_id, best_id, accepted_iterations, pareto_scores, parents,
prompt_configurations}` (`optimizer/types.py:103`). Pareto selection + tie-breaking in
`optimizer/policies.py:30-198` (`TieBreaker{prefer_root, prefer_child, random}` `:172`).

⚠ **The optimizer only rewrites a `Prompt`.** `ModelCallback = Callable[[Prompt, Golden], str]`
(`optimizer/types.py`) and `PromptConfiguration.prompts: Dict[ModuleId, Prompt]` (`:27-33`), with
`SINGLE_MODULE_ID = '__module__'` in every algorithm. It cannot change tools, decomposition, loop,
or topology. **This does not satisfy T4/D22** — PACT's optimizer ABI must be strictly larger. But
`OptimizationReport` (Pareto frontier + parent lineage + accepted-iteration deltas) is a good shape
for PACT's optimisation ledger, and `defaults are all scalars ⇒ config-only`.

### 5.10 Benchmarks

`deepeval/benchmarks/__init__.py:1-36` — 17 harnesses: `BigBenchHard, MMLU, HellaSwag, DROP,
TruthfulQA, HumanEval, SQuAD, GSM8K, MathQA, LogiQA, BoolQ, ARC, BBQ, LAMBADA, Winogrande,
EquityMedQA, IFEval`. `DeepEvalBaseBenchmark.__init__` imports HuggingFace `datasets`
(`benchmarks/base_benchmark.py:17-18`) ⇒ **network unless the HF cache is pre-warmed.**
For **O3.2 / AC-3.3** (benchmark figures with provenance) this is a *producer* of figures, not a
catalogue — PACT still needs its own catalogue schema.

### 5.11 Human annotation

`deepeval/annotation/annotation.py:6-40`: `send_annotation(rating, trace_uuid|span_uuid|thread_id,
expected_output, expected_outcome, explanation, user_id, type)`; `AnnotationType{THUMBS_RATING,
FIVE_STAR_RATING}` (`annotation/api.py:5-8`); exactly one of the three ids required (`:22-38`).
**Network-only — posts to Confident AI.** D19 on-ramp 3 ("mark conversations good/bad in a review
queue") therefore has **no offline implementation in DeepEval**; PACT must build it.

### 5.12 Models

`deepeval/models/__init__.py:6-20` — 13 LLM classes: `GPTModel, AzureOpenAIModel, LocalModel,
OllamaModel, AnthropicModel, GeminiModel, AmazonBedrockModel, LiteLLMModel, KimiModel, GrokModel,
DeepSeekModel, PortkeyModel, OpenRouterModel`; 4 embedders: `OpenAIEmbeddingModel,
AzureOpenAIEmbeddingModel, LocalEmbeddingModel, OllamaEmbeddingModel`.

`initialize_model()` (`metrics/utils.py:659-699`) resolves `model=None` by probing settings in a
fixed order and **falls back to `GPTModel` (OpenAI) as the last resort** (`:697-698`).
⚠ **A metric with `model=None` in an air-gapped deployment will silently target OpenAI unless
`DEEPEVAL_...LOCAL_MODEL`/Ollama settings are configured.** PACT must always bind the judge
explicitly.

---

## 6. What is *not* config-expressible today, precisely

| # | Construct | Why | Severity |
|---|---|---|---|
| 6.1 | `JsonCorrectnessMetric.expected_schema: BaseModel` | needs a live object with `model_validate_json()` + `model_json_schema()` (`metrics/json_correctness/json_correctness.py:87,137,168,193`) | shim, §7.2 |
| 6.2 | `ToolCorrectnessMetric.available_tools` / `ToolUseMetric.available_tools`: `List[ToolCall]` | pydantic objects | shim (trivial: `ToolCall(**dict)`) |
| 6.3 | `GEval.rubric: List[Rubric]` | pydantic objects | shim (trivial) |
| 6.4 | `DAGMetric.dag: DeepAcyclicGraph` | object graph — **but `from_dict` exists** (§4.2) | solved upstream |
| 6.5 | `mcp_tools_called[].result` must be `mcp.types.CallToolResult` | `isinstance` check (`test_case/llm_test_case.py:548-558`) | harness-produced |
| 6.6 | Trace-based metrics need `LLMTestCase._trace_dict` | private attr populated by `@observe` machinery | harness-produced |
| 6.7 | Component/span-level evals | `@observe(metrics=[...])` decorators | harness-produced |
| 6.8 | `TraceManager.configure(mask=Callable)` | redaction is a callable | **needs PACT-native declarative redaction** (AC-4.4) |
| 6.9 | `ConversationSimulator.model_callback` / `stopping_controller` | callables | harness + declarative stop predicate |
| 6.10 | `PromptOptimizer.model_callback` | callable | harness |
| 6.11 | `RagasMetric.embeddings: Embeddings` | LangChain object | do not expose |
| 6.12 | A truly novel metric | `BaseMetric` subclass | F-2 `ref:` escape; report as `code` fidelity |

**Result: zero DeepEval metrics require author code.** All twelve items are provider/harness
concerns. AC-4.2 ("no eval in the reference suite requires the author to write code") is
**achievable at 100 %** for DeepEval-expressible checks, *provided PACT implements §7.2*.

---

## 7. Proposed minimal declarative constructs for PACT

### 7.1 The metric descriptor (one shape for all 51 config-expressible metrics)

```yaml
# evals/suite.yaml
metrics:
  - uri: deepeval:faithfulness          # provider:metric — E-4 registry key
    threshold: 0.8
    judge: models/judge-local           # $ref into the model catalogue; NEVER omit (see §5.12)
    strict: false
    explain: true                       # → include_reason
    with:                               # provider-specific constructor extras
      truths_extraction_limit: 5
      penalize_ambiguous_claims: true
```
Rules the descriptor must encode, derived from source:
- `strict: true` ⇒ threshold forced to `1` **and** score binarised to `0` on failure (§2).
- `window: 10` maps to `window_size`; note **`deepeval:conversation_completeness` defaults to 3**,
  every other turn metric to 10 — PACT must not normalise this silently, or it changes scores.
- `explain` defaults **true** in every concrete metric but **false** on `BaseMetric` — pin it.
- Multimodal metrics reject `explain` (no such parameter) — validator must say so by name (O7.3).

### 7.2 The four provider shims PACT must write (Python side, once)

| Shim | Contract |
|---|---|
| **S1 — Rubric** | `List[{score_range: [int,int], expected_outcome: str}] → List[Rubric]`. Validate 0–10 and non-overlap **in PACT**, so the error names the YAML line, not a pydantic trace. |
| **S2 — ToolCall** | `List[{name, type?, description?, input_parameters?, output?}] → List[ToolCall]`. Better: **`available_tools: from-agent`**, resolving to the agent's declared tool set so the eval cannot drift from the spec. |
| **S3 — JSON Schema → schema object** | Accept inline JSON Schema or `$ref: contract/io.yaml#/output`. Build an object exposing `model_validate_json(str)` (raising `pydantic.ValidationError`) and `model_json_schema()`. `pydantic.create_model` or a 20-line wrapper over `jsonschema` both satisfy the two call sites. This is the **only non-trivial shim**. |
| **S4 — DAG document** | PACT YAML → the §4.2 `{"nodes": {...}}` document → `DeepAcyclicGraph.from_dict(doc, multiturn=<bool>)`. **Adopt DeepEval's node vocabulary verbatim** (`TaskNode`/`BinaryJudgementNode`/`NonBinaryJudgementNode`/`VerdictNode`, `evaluation_params` as enum *values*, verdict `score` XOR `child`) so the two documents are the same document. Add PACT-only sugar (`label`-based refs instead of uuids; `multiturn` carried in the envelope). **Never round-trip through `dag_to_dict` (§4.3).** |

### 7.3 Selector syntax for trace/component evals (the construct DeepEval lacks)

```yaml
metrics:
  - uri: deepeval:answer_relevancy
    on: trace                        # whole run  (default)
  - uri: deepeval:tool_correctness
    on: span
    where: { type: tool, name: search_docs }
  - uri: deepeval:agent_loop_detection
    on: trace
```
PACT's harness owns span emission (§5.4), so `on:`/`where:` replaces `@observe(metrics=[...])`
entirely. This is the single highest-leverage addition: it converts DeepEval's most code-bound
feature into config, and it is only possible **because** of D12.

### 7.4 Do not expose these

- `template_class` on `TurnRelevancyMetric` (`metrics/turn_relevancy/turn_relevancy.py:39`) — an
  undocumented prompt-borrowing hook; leaks DeepEval class names into PACT.
- `_include_g_eval_suffix` / `_include_dag_suffix` — affect only the display name.
- `metric_collection`, `GEval.pull()/upload()`, `DAGMetric.pull()/upload()` (`metrics/dag/dag.py:150-201`),
  `EvaluationDataset.push/pull`, `send_annotation` — all network.
- The six `RAGAS*` wrappers (§3.11).

---

## 8. Air-gap analysis (D17 / AC-7.3)

| Path | Air-gapped? | Evidence / required action |
|---|---|---|
| Metric execution with a local judge | ✅ | `LocalModel`, `OllamaModel` are "native models" (`metrics/utils.py:706-726`); `LocalModel.supports_multimodal` exists (`models/llms/local_model.py:203`). |
| **Telemetry on import** | ❌ **by default** | `deepeval/telemetry.py:113-127`: unless `DEEPEVAL_TELEMETRY_OPT_OUT`, `sentry_sdk.init(dsn=…ingest.sentry.io…)` and `Posthog(host="https://us.i.posthog.com")` run at import. `blocked_by_firewall()` opens a socket to `www.google.com:80` (`:41-46`); `get_anonymous_public_ip()` GETs `https://api.ipify.org` (`:49-56`); `posthog.capture(...)` appears at 12 call sites (`:215`–`:426`). Settings keys: `DEEPEVAL_TELEMETRY_OPT_OUT` (`deepeval/config/settings.py:767`) and `ERROR_REPORTING` (`:785`). **Mandatory: `DEEPEVAL_TELEMETRY_OPT_OUT=1` + `ERROR_REPORTING=0` in every PACT profile.** |
| `model=None` fallback | ⚠ | Falls through to `GPTModel` (OpenAI) (`metrics/utils.py:697-698`). **PACT must always bind a judge explicitly.** |
| `metric_collection=` / `GEval.pull()` / `DAGMetric.pull()` | ❌ | Confident AI HTTP. Ban in `strict`/`airgapped` profiles. |
| `EvaluationDataset.push/pull/queue/create_version` | ❌ | Same. Local CSV/JSON/JSONL loaders are the offline path (§5.3). |
| `send_annotation` | ❌ | Same. |
| Benchmarks | ⚠ | HuggingFace `datasets` import (`benchmarks/base_benchmark.py:17`); needs a pre-warmed `HF_HOME`. |
| Synthesizer / simulator / optimizer | ✅ | Local models + local documents only. |
| DAG JSON round-trip | ✅ | Pure local (`serialization/serialization.py`). |
| Prompt templates | ✅ | Bundled `templates/metrics/templates.json`. |

---

## 9. What DeepEval LACKS — gaps found in ragas, promptfoo, inspect_ai

### 9.1 promptfoo — the deterministic-assertion library DeepEval simply does not have

`/home/bud/ditto/agent-inter-op/research/repos/eval/promptfoo/src/types/index.ts:595-661` defines
**66 base assertion types**, each usable directly from YAML, plus `not-` negation of every one
(`:677-679`) and three special types `select-best | human | max-score` (`:673-675`).

DeepEval has **2** deterministic metrics (`ExactMatch`, `PatternMatch`) plus `ToolPermission`.
promptfoo assertion types with **no DeepEval equivalent**:

| Family | Types missing from DeepEval |
|---|---|
| String/containment | `contains`, `contains-all`, `contains-any`, `icontains`, `icontains-all`, `icontains-any`, `starts-with`, `equals`, `word-count` |
| Structural validation | `is-json`, `contains-json`, `is-xml`, `contains-xml`, `is-html`, `contains-html`, `is-sql`, `contains-sql`, `is-valid-function-call`, `is-valid-openai-function-call`, `is-valid-openai-tools-call` |
| Text-similarity (classical NLP) | `bleu`, `gleu`, `meteor`, `rouge-n`, `levenshtein`, `similar`, `similar:cosine`, `similar:dot`, `similar:euclidean` |
| Model behaviour | `finish-reason`, `is-refusal`, `perplexity`, `perplexity-score`, `moderation`, `classifier` (HF classifier), `guardrails` |
| **Operational / SLO** | **`latency`**, **`cost`** — DeepEval carries `token_cost` and `completion_time` on `LLMTestCase` but **no metric reads them** (§1.1) |
| **Agent trajectory** | `trajectory:goal-success`, `trajectory:tool-args-match`, `trajectory:step-count`, `trajectory:tool-sequence`, `trajectory:tool-used`, `skill-used`, `tool-call-f1`, `agent-rubric` |
| **Trace assertions** | `trace-error-spans`, `trace-span-count`, `trace-span-duration` |
| Aggregation | `select-best` (cross-variant), `max-score`, `assert-set` with `weight` + `threshold` (`:696-703`) |
| Escape hatches | `javascript`, `python`, `ruby`, `webhook` |

The **`Assertion` schema itself** (`:708-739`) is the best-designed declarative unit in the corpus and
PACT should copy its shape: `{type, value, config, threshold, weight, provider, rubricPrompt, metric,
transform, contextTransform}`. Two ideas are load-bearing:
- **`weight`** — weighted aggregation of many assertions into one test verdict. DeepEval has no
  weighting at all; every metric is an independent pass/fail.
- **`metric`** — tag an assertion into a named roll-up metric. Lets ten assertions feed one
  contract-level score.
- **`transform` / `contextTransform`** — normalise output before asserting (DeepEval has nothing).

### 9.2 ragas — RAG/agent metrics DeepEval lacks

`/home/bud/ditto/agent-inter-op/research/repos/eval/ragas/src/ragas/metrics/collections/__init__.py:51-95`.

Missing from DeepEval:
- **Reference-based answer scoring:** `AnswerCorrectness`, `FactualCorrectness`, `SemanticSimilarity`,
  `AnswerAccuracy`.
- **Non-LLM / ID-based retrieval metrics:** `NonLLMContextRecall`, `NonLLMContextPrecisionWithReference`,
  `IDBasedContextRecall`, `IDBasedContextPrecision`
  (`ragas/src/ragas/metrics/_context_precision.py`, `_context_recall.py`) — **deterministic retrieval
  scoring against document IDs**, which is exactly the AC-4.5 "decide it without a judge" case for RAG.
  DeepEval's five RAG metrics are **all LLM-judged**.
- **Robustness:** `NoiseSensitivity`.
- **Grounded-citation:** `QuotedSpansAlignment` (`ragas/src/ragas/metrics/quoted_spans.py`).
- **Classical text metrics:** `BleuScore`, `RougeScore`, `CHRFScore`, `NonLLMStringSimilarity`
  (with `DistanceMeasure`), `StringPresence`, `ExactMatch`.
- **Rubric metrics as first-class:** `DomainSpecificRubrics`, `InstanceSpecificRubrics`
  (per-*sample* rubrics — DeepEval's G-Eval rubric is per-*metric* only).
- **Structured-data equivalence:** `SQLSemanticEquivalence`, `DataCompyScore`.
- **`FaithfulnesswithHHEM`** — a local NLI cross-encoder faithfulness scorer
  (`ragas/src/ragas/metrics/_faithfulness.py`), i.e. **faithfulness with no LLM judge at all**.
- **Metric output types as a first-class concept:** `DiscreteMetric` / `NumericMetric` /
  `RankingMetric` + decorators (`ragas/src/ragas/metrics/discrete.py`, `numeric.py`, `ranking.py`).
  DeepEval hard-codes "float in [0,1] + threshold" for everything except `ArenaGEval`.

### 9.3 inspect_ai — the statistical/experimental machinery DeepEval lacks entirely

`/home/bud/ditto/agent-inter-op/research/repos/eval/inspect_ai/src/inspect_ai/scorer/__init__.py:1-100`.

| Capability | inspect_ai | DeepEval |
|---|---|---|
| **Repeat a sample N times and reduce** | `mode_score`, `mean_score`, `median_score`, `max_score`, `at_least(k, value)`, `pass_at(k)`, `pass_k(k)` (`scorer/_reducer/reducer.py:13-215`) | **none** |
| **Uncertainty on the aggregate** | `stderr(to_float, cluster=None)`, `bootstrap_stderr(num_samples=1000)`, `std`, `var` (`scorer/_metrics/std.py:16-204`) — including **clustered stderr** | **none** (mean + pass rate only) |
| **Grouped/stratified reporting** | `grouped(metric, group_key, all='samples'|'groups', ...)` (`scorer/_metrics/grouped.py:15`) | **none** |
| **Categorical outcomes** | `categorical`, `frequency` (`scorer/_metrics/categorical.py`) | **none** |
| **Combine scorers** | `multi_scorer(scorers, reducer)` (`scorer/_multi.py:19`) | only via DAG leaves |
| **Judge ensembling** | `model_graded_qa(model=list[str|Model], ...)` — a *list* of grader models (`scorer/_model.py:87`) | single `model` |
| **Partial credit + grade pattern** | `partial_credit`, `grade_pattern`, `include_history` on `model_graded_qa/fact` (`scorer/_model.py:29,87`) | none |
| **Prompt-injection hardening in the grader** | `neutralize_structural_delimiters(text)` (`scorer/_model.py:367`) | none |
| Answer extraction | `answer(pattern: 'letter'|'word'|'line')` (`scorer/_answer.py:36`), `pattern(pattern, ignore_case, match_all)` (`scorer/_pattern.py:56`), `match(location='begin'|'end'|'any'|'exact', numeric=…)` (`scorer/_match.py:9`), `includes` (`:46`), `choice` (`scorer/_choice.py:45`) | `ExactMatch`, `PatternMatch` (fullmatch only) |
| Classification | `f1(answer_fn, stop_words)`, `exact()` (`scorer/_classification.py:15,44`) | none |
| Perplexity | `perplexity`, `target_perplexity`, `perplexity_per_seq/token` | none |

**The `stderr` + `pass_at(k)` gap is the most consequential.** AC-2.2 ("within a declared ε of the
reference adapter") and AC-3.1 ("≥ 95 % of reference eval score") are **statistical claims**. With
mean-only aggregation and n=1 sampling you cannot say whether a 3-point delta is real. inspect_ai's
`stderr`/`bootstrap_stderr`/`pass_at` are the missing instrument.

---

## 10. Design implications for PACT (actionable)

1. **Define PACT's own eval document.** DeepEval has no config format; there is nothing to adopt.
   Sole exception: **copy the DAG node document verbatim** (§4.2) so PACT ↔ DeepEval DAG is an
   identity mapping.
2. **Ship the four shims (§7.2) in the DeepEval provider process.** Only S3 (JSON Schema →
   `model_validate_json`/`model_json_schema` object) is non-trivial. With them, **51/56 metrics are
   config-only and 0 require author code**.
3. **Never round-trip a metric through `dag_to_dict`.** It silently drops `rubric`, `available_tools`
   and `expected_schema` (§4.3, verified). PACT's canonical form must be the source; if export is
   needed, diff and fail closed (T7).
4. **Add `on:` / `where:` selectors for span-level metrics (§7.3).** This is the only way to make
   component-level evaluation no-code, and it is only available to a system that owns the loop (D12).
5. **Fill the deterministic-assertion gap before shipping.** DeepEval offers 3 non-LLM checks;
   promptfoo offers ~30. AC-4.5 ("a suite that can be fully decided deterministically never invokes
   a judge") is **unreachable on DeepEval alone**. Implement a native `pact:` assertion family
   (contains/starts-with/is-json/json-schema/regex/levenshtein/rouge/bleu/latency/cost/
   tool-sequence/tool-args-match/step-count/trace-span-count) — these are ~200 lines of Rust in the
   core, need no model, and run offline.
6. **Adopt promptfoo's `weight` + `metric` roll-up.** DeepEval treats every metric as an independent
   pass/fail; a contract needs a weighted verdict. Add `weight:` and `rollup:` to the PACT metric
   descriptor.
7. **Adopt inspect_ai's repeats + reducers + stderr.** Add `repeats: N` and
   `reduce: mean|median|mode|max|at_least(k)|pass_at(k)` per case, and report
   `mean ± stderr` (bootstrap for small n). Make ε in AC-2.2 / AC-3.1 comparisons against the
   interval, not the point estimate.
8. **SLO metrics are PACT's job, not DeepEval's.** `LLMTestCase.token_cost` / `completion_time`
   and `LlmSpan.token_intervals` exist but **no DeepEval metric reads them** (§1.1, §5.4).
   Implement `pact:latency_p95`, `pact:ttft`, `pact:tpot`, `pact:cost` natively over PACT's own
   spans (O4.2 / AC-3.6).
9. **Redaction must be declarative.** DeepEval's only hook is `TraceManager.configure(mask=Callable)`.
   AC-4.4 (promote failing traces "preserving redaction policy") requires a PACT-native
   `policies/redaction.yaml` (JSONPath/field-name/regex rules) applied before any trace becomes a
   golden.
10. **Do not claim red-team or guardrail parity.** Both subsystems are absent from DeepEval 4.1.3
    (§5.6, §5.7). The coverage matrix must say so; "DeepEval parity" for safety = six judge metrics.
11. **Modality parity is a PACT obligation, not a DeepEval inheritance.** DeepEval covers image + PDF
    only. **No audio, no video, no computer-use metric exists.** D16 requires all four; PACT must
    author `pact:` metrics for audio (WER/latency/TTFT-to-first-audio) and computer-use
    (task success, action-sequence match, screenshot-grounded judge) itself.
12. **Pin the judge in every profile; forbid `model: null`.** `initialize_model` silently falls back
    to OpenAI (`metrics/utils.py:697-698`), which would break air-gapped runs late and confusingly.
13. **Bake `DEEPEVAL_TELEMETRY_OPT_OUT=1` and `ERROR_REPORTING=0` into the provider bootstrap** and
    assert them in a startup check, so AC-7.3 is enforced, not hoped for.
14. **PACT's optimizer ABI must be strictly larger than DeepEval's.** DeepEval's optimizes a single
    `Prompt` (`optimizer/types.py`, `SINGLE_MODULE_ID='__module__'`), which cannot satisfy D22
    (tools, structure, topology). Reuse the *report* shape (`OptimizationReport`: Pareto scores,
    parents, accepted iterations) for the learning ledger.
15. **Reuse the synthesizer wholesale.** All five of its config dataclasses are pure scalars (§5.5) —
    it is the single largest piece of DeepEval that is already 100 % config-only, and it directly
    implements D19 on-ramp 4.
16. **Adopt `ArenaGEval`'s contestant-name masking as a default judge-hardening rule** for *all* PACT
    comparison evals (`metrics/arena_g_eval/utils.py:94-129`); it costs nothing and removes a known
    bias (R4).
17. **Normalise the two `window_size` defaults explicitly** (3 for conversation-completeness, 10 for
    everything else). If PACT picks one default it changes scores versus DeepEval and breaks D27.

---

## 11. Open questions

1. Does `deepteam` (the red-team successor) have a declarative surface worth mirroring? **It is not
   in the local corpus** — cannot be answered offline.
2. Does the TypeScript port (`typescript/`) expose the same metric set? Not audited in this pass; it
   matters for TS adapters (Vercel AI SDK, Claude Agent SDK TS).
3. Is there a supported way to override `templates.json` per-deployment (for localisation or
   judge-hardening) short of monkeypatching `_registry._base_templates`? Source says no; worth one
   upstream issue before PACT commits to forking prompts.
4. `ToolCorrectnessMetric._calculate_score` interaction between `should_exact_match`,
   `should_consider_ordering` and `evaluation_params` was not read line-by-line; the exact scoring
   formula should be pinned before PACT documents its semantics.
5. Whether `LLMTestCase.multimodal` auto-detection is stable across `MLLMImage` instances created in
   a *different process* — the placeholder registry `_MLLM_IMAGE_REGISTRY`
   (`test_case/llm_test_case.py:31`) is **process-global in-memory**, and
   `MLLMImage.parse_multimodal_string` reconstructs a *new* `MLLMImage(url=img_id)` on a miss
   (`:161-162`). This looks fragile for a provider-subprocess architecture and needs a test.
