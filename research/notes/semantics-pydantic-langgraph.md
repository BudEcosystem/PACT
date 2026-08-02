# Semantics audit: Pydantic AI vs LangGraph (source-level)

**Stream:** `semantics-pydantic-langgraph`
**Date:** 2026-07-26
**Purpose:** Determine whether PACT Decision **D12** (harness lowering — PACT owns loop
semantics, frameworks are model/tool transports) is implementable against the two
prototype adapters, and enumerate every semantic divergence that PACT's IR must either
express or honestly report as lossy.

## 0. Provenance of every claim below

| Repo | Path | HEAD | Version |
|---|---|---|---|
| pydantic-ai | `/home/bud/ditto/agent-inter-op/research/repos/frameworks/pydantic-ai` | `ed0f40c0e5061722f7d9f579ed7efff1b74e3ea5` (2026-07-25) | `pydantic-ai-slim`, version is `uv-dynamic-versioning` from git (no static version string) — `pydantic_ai_slim/pyproject.toml:5-13` |
| langgraph | `/home/bud/ditto/agent-inter-op/research/repos/frameworks/langgraph` | `30c4d58db86455128e42ddec96b1ba53c553ba22` (2026-07-25) | `libs/langgraph/pyproject.toml:6` → `1.2.9` |
| langchain (needed: `create_agent` moved here) | `/home/bud/ditto/agent-inter-op/research/repos/frameworks/langchain` | same corpus | `libs/langchain_v1/pyproject.toml:24` → `1.3.14`; `libs/core/pyproject.toml:24` → `1.5.1` |

All line references are `path:line` relative to those repo roots. Everything marked
**[V]** was read in source. Everything marked **[I]** is an inference I am drawing from
what I read and did not execute.

---

# PART A — PYDANTIC AI

## A(a) The agent loop: exact control flow of one run

Pydantic AI's loop **is** a `pydantic_graph` state machine with exactly four node types,
built in `_agent_graph.py:2281-2310` (`build_agent_graph`):

```
START → UserPromptNode → ModelRequestNode ⇄ CallToolsNode → End(FinalResult)
                              ↑                    │
                              └────────────────────┘
                         (SetFinalResult is a 5th node, used only by
                          the streaming path to end immediately)
```

`_agent_graph.py:2301-2309` registers `UserPromptNode`, `ModelRequestNode`,
`CallToolsNode`, `SetFinalResult`; `build_agent_graph` is called with
`validate_graph_structure=False` (`:2310`).

### Step-by-step, one run

1. **`UserPromptNode.run`** — `_agent_graph.py:475-610`. **[V]**
   - Copies `ctx.state.message_history` through `_clean_message_history` (`:490`) — this
     merges consecutive same-role messages, drops orphaned tool results and repairs
     dangling tool calls (`_agent_graph.py:2484`, `:2529`, `:2614`, `:2676`).
   - If `deferred_tool_results` were supplied, it **skips `ModelRequestNode` entirely**
     and jumps to `CallToolsNode` (`:495-496`, `:651-657`). This is the HITL/deferred
     resume path.
   - If the history's last message is a `ModelRequest` and no new prompt was given, it
     *pops* that request and re-sends it (`:516-539`) — "resume without prompt".
   - If the last message is a `ModelResponse` with `state == 'suspended'` (provider
     paused the turn — Anthropic `pause_turn`, OpenAI background mode) it routes to
     `ModelRequestNode(_resume_suspended=...)` (`:541-552`).
   - If the last message is a `ModelResponse` with pending `tool_calls` and no new
     prompt, it goes **straight to `CallToolsNode`** (`:562-566`).
   - Otherwise it builds a `ModelRequest` from system prompts (only on the first turn,
     `:600-601`) plus the `UserPromptPart` (`:603-604`).
   - **Error, not merge:** a new user prompt on top of unprocessed tool calls raises
     `UserError` (`:586-588`). A new prompt on a suspended response raises `UserError`
     (`:575-578`).

2. **`ModelRequestNode._prepare_request`** — `_agent_graph.py:1338-1489`. **[V]** This is
   the step boundary. Ordered side-effects:
   - `self.request.timestamp = now_utc()`, appended to history (`:1353-1356`).
   - `ctx.state.run_step += 1` (`:1358`) ← **the canonical step counter**.
   - `_select_model(ctx)` (`:1360`, impl `:2099-2121`) — a per-step model selector hook.
   - `tool_manager.for_run_step(run_context)` (`:1376`) — resolves dynamic toolsets,
     raises on tool-name conflicts, and carries retry counters forward.
   - `_get_instructions` (`:1379`), sorted and joined into `request.instructions`
     (`:1381-1382`).
   - `_prepare_request_parameters` (`:1388`, impl `:716-780`) builds
     `ModelRequestParameters{function_tools, native_tools, output_mode, output_tools,
     output_object, prompted_output_template, allow_text_output, allow_image_output,
     instruction_parts}`.
   - `before_model_request` capability hook may *replace* model, messages, settings and
     parameters (`:1402-1410`). Post-conditions are enforced: processed history must be
     non-empty (`:1412-1413`) and must end in a `ModelRequest` (`:1415-1416`).
   - `usage_limits.check_before_request(usage)` (`:1487`).

3. **`ModelRequestNode._make_request`** — `_agent_graph.py:1263-1336`. Wraps the model
   call in `root_capability.wrap_model_request(...)` (`:1313-1317`); a `ModelRetry`
   raised by any hook is converted into a new `ModelRequestNode` carrying a
   `RetryPromptPart` (`:1654-1667`). `usage.requests += 1` at `:1334`. Returns
   `CallToolsNode(response)` via `_finish_handling` (`:1591-1617`).

4. **`CallToolsNode._run_stream`** — `_agent_graph.py:1720-1885`. **[V]** Decision order
   inside one response:
   - Suspended response → `UserError` (`:1729-1738`).
   - Empty or thinking-only response: `finish_reason == 'length'` →
     `UnexpectedModelBehavior` (`:1749-1752`); `content_filter` → `ContentFilterError`
     (`:1755-1768`); if the schema `allows_none`, that's a valid final result
     (`:1774-1791`); otherwise fall through to a synthesised `RetryPromptPart`.
   - Partition parts into `text`, `tool_calls`, `files`, ignoring `ThinkingPart`,
     resetting accumulated text on a `NativeToolCallPart` (`:1803-1824`).
   - **Tool calls win over text by default** (`:1842-1846`). Exception: under
     `end_strategy='early'`, a schema-validated text or image output pre-empts *plain
     function* tool calls (`:1843`, `:1904-1924`).
   - No tool calls → image output → text output → else synthesise a retry prompt naming
     the legal alternatives (`:1855-1873`).
   - `ToolRetryError` consumes one unit of the **output** retry budget
     (`consume_output_retry`, `:353-370`) and produces the next `ModelRequestNode`
     (`:1874-1876`).

5. **Termination** happens only via `End(FinalResult)` from `_handle_final_result`
   (`_agent_graph.py:2062-2082`), which appends a trailing `ModelRequest` carrying the
   tool returns so the history is re-usable.

### Termination conditions, enumerated **[V]**

| Condition | Source |
|---|---|
| Output tool call succeeds | `_tool_execution.py:177-178` → `output_final_result` |
| Text validates against the output schema | `_agent_graph.py:1861-1864` |
| Image output validates | `_agent_graph.py:1855-1858` |
| Empty/thinking-only response and `output_schema.allows_none` | `_agent_graph.py:1774-1791` |
| Deferred tool calls remain unresolved and `DeferredToolRequests` is in the output type | `_output.py:476-480`, `_tool_execution.py:823+` |
| `UsageLimits.request_limit` (default **50**) exceeded | `usage.py:302`, `:339-343` |
| `max_output_retries` exceeded → `UnexpectedModelBehavior` | `_agent_graph.py:367-370` |
| Per-tool `max_retries` exceeded → `UnexpectedModelBehavior` | `tool_manager.py:185-195` |
| `tool_calls_limit`, token limits | `usage.py:304-311` |

> **There is no "max steps" concept.** The only step-count bound is
> `UsageLimits.request_limit` (default 50, `usage.py:302`). **[V]**

## A(b) State model

`GraphAgentState` (`_agent_graph.py:290-370`) is the *entire* run state. Fields **[V]**:

| Field | Line | Note |
|---|---|---|
| `message_history: list[ModelMessage]` | `:294` | the real state |
| `usage: RunUsage` | `:295` | |
| `output_retries_used: int` | `:296` | |
| `run_step: int` | `:297` | |
| `run_id: str` (uuid7) | `:298` | never inherited from history |
| `conversation_id: str` (uuid7) | `:304` | inherited from history if present |
| `metadata: dict \| None` | `:311` | |
| `last_max_tokens`, `last_model_request_parameters` | `:312-314` | error messages / OTel only |
| `pending_messages` | `:316` | `enqueue()` queue |
| `event_stream_buffer` | `:319` | shared by reference into every `RunContext` |
| `mcp_tool_defs_cache` | `:327` | per-run, rebuilt identically on durable replay |

**The state is the message list.** There is no arbitrary key/value state. Application
state travels in `deps` (`GraphAgentDeps.user_deps`, `:377`), which is **not persisted**
and **not serialised**.

- **Serialisation:** `ModelMessagesTypeAdapter.dump_json` (`run.py:170`, `:185`) — the
  message history round-trips as JSON. `AgentRunResult.all_messages_json` at
  `run.py:540`.
- **Checkpointing:** none in the core. Durability is provided by opt-in capabilities
  under `pydantic_ai/durable_exec/{temporal,dbos,prefect}` (dir listing confirmed;
  `durable_exec/AGENTS.md:1-11` states these must "preserve run context, dependencies,
  message history, retries, model/profile selection, and toolset lifecycle across durable
  boundaries").
- **Resume:** three distinct mechanisms, all *history-shaped*, not checkpoint-shaped:
  1. `message_history=` + `deferred_tool_results=` (`agent/__init__.py:991-992`).
  2. `message_history` ending in a `ModelRequest` and no prompt (resume-without-prompt,
     `_agent_graph.py:516-525`).
  3. `message_history` ending in a suspended `ModelResponse` (provider continuation,
     `_agent_graph.py:541-552`, `_prepare_resume_request` `:1491-1589`).
- **Addressability:** **partial.** You can address *messages* (they carry `run_id`,
  `conversation_id`, `tool_call_id`) but there is no addressable "node state" or
  "checkpoint id". `AgentRun.ctx` (`run.py:117-122`) exposes the live
  `GraphRunContext[GraphAgentState, GraphAgentDeps]`, and `AgentRun.next(node)`
  (`run.py:328`) lets a caller *drive* the graph node-by-node — but the node objects are
  in-memory Python dataclasses, not serialisable checkpoints.

> **Negative finding:** pydantic-ai cannot express "resume at superstep N of a
> long-running graph after process death" without a durable-execution capability. Core
> resume is *conversation resume*, not *execution resume*. **[V]**

## A(c) Tool protocol

### Declaration & schema derivation

- `ToolDefinition` (`tools.py:544-663`) is the wire object: `name`,
  `parameters_json_schema`, `description`, `outer_typed_dict_key`, `strict`,
  `sequential`, `kind` (`function|output|external|unapproved`), `metadata`, `timeout`,
  `defer_loading`, `unless_native`, `with_native`. **[V]**
- Schema derivation from Python signatures: `_function_schema.py` (18.6 KB) +
  `function_signature.py`. **Schema-first** declaration exists:
  `Tool.from_schema(function, name, description, json_schema, takes_ctx, sequential,
  args_validator)` (`tools.py:438-493`) — it installs `SchemaValidator(any_schema())`
  (`:478`) so schema validation is *skipped*; the JSON Schema is used purely as the
  wire contract. **This is the hook a PACT adapter uses to register a YAML-declared
  tool.** **[V]**
- Toolsets are the composition unit: `AbstractToolset` (`toolsets/abstract.py:76`) with
  `get_tools(ctx) -> dict[str, ToolsetTool]` (`:165-168`) and
  `call_tool(name, args, ctx, tool)` (`:170-182`). Combinators as methods:
  `.filtered()`, `.prefixed()`, `.prepared()`, `.renamed()`, `.approval_required()`,
  `.defer_loading()`, `.include_return_schemas()` (`:196-260`). Lifecycle: `for_run`
  (`:108`), `for_run_step` (`:117`), `__aenter__/__aexit__` (`:126-142`),
  `get_instructions` (`:144-163`).

### Parallel calls, ordering, barriers **[V]**

`_tool_execution.py:592-719` (`_call_tools`):

- Calls are segmented by "barrier" tools: `_segment_by_barriers` (`:89-108`). A tool with
  `ToolDefinition.sequential=True` (`tools.py:577-585`) becomes a single-element segment;
  contiguous non-barrier calls form one parallel segment.
- Within a parallel segment: `asyncio.create_task` per call (`:669-672`) then either
  - `parallel` (default) — `asyncio.wait(FIRST_COMPLETED)`, events yielded in
    *completion* order (`:682-694`), or
  - `parallel_ordered_events` — `ALL_COMPLETED` then events in *emission* order
    (`:675-680`), or
  - `sequential` — every call is its own barrier (`:651`, `:658`).
  Mode is run-scoped via `ToolManager.parallel_execution_mode(mode)` contextmanager
  (`tool_manager.py:102`).
- **Result ordering is always emission order regardless of event ordering**: results are
  collected into `tool_parts_by_index` and appended sorted (`:710-711`).
- On any exception, sibling tasks are cancelled and drained (`:695-704`); partial results
  still land in `output_parts` (`finally`, `:705-711`) and are captured as a
  `ModelRequest(state='interrupted')` (`_agent_graph.py:1944-1958`).

### `end_strategy` — three distinct loop semantics **[V]**

Documented in `_tool_execution.py:122-153` and dispatched at `:158-165`:

- `'early'` (`_EarlyProcessor`, `:913`): output tools run sequentially, stop at first
  success; function tools run **only if every output tool failed**.
- `'graceful'` (default, `_GracefulProcessor`, `:941`): emission order; function tools
  before an output tool complete first; output tools stop at first success.
- `'exhaustive'` (`_ExhaustiveProcessor`, `:970`): everything runs in parallel; first
  valid output by emission order wins while the rest still execute.
- **Retry-wins invariant** (`:142-147`): under graceful/exhaustive, if any function tool
  produced a `RetryPromptPart`, the final result is *suppressed* so the model addresses
  the retries next round. Not applied under `'early'` or when the result came from
  `run_stream`.

### Errors & retries **[V]**

- `ModelRetry` raised in a tool → `RetryPromptPart` back to the model
  (`_tool_execution.py:546-552`).
- `ToolFailed` → `ToolReturnPart(outcome='failed')`, terminal, no retry (`:538-545`).
- Retry budget is **per tool name**, counted on `RunContext.retries`
  (`tool_manager.py:185-195`). Crucially the count is **reset when the tool succeeds**:
  `for_run_step` drops names in `succeeded_tools` and increments names in `failed_tools`
  (`tool_manager.py:123-135`).
- A separate **output** budget (`max_output_retries`) is consumed by output-tool
  failures, text-validation failures and non-actionable responses
  (`_agent_graph.py:353-370`).
- Exception taxonomy: `exceptions.py:43-402` — `ModelRetry`, `ToolFailed`,
  `CallDeferred`, `ApprovalRequired`, `SkipModelRequest`, `SkipToolValidation`,
  `SkipToolExecution`, `UserError`, `UndrainedPendingMessagesError`, `AgentRunError`,
  `SuspendedResponseExpired`, `UsageLimitExceeded`, `ConcurrencyLimitExceeded`,
  `UnexpectedModelBehavior`, `ContentFilterError`, `ModelAPIError`, `ModelHTTPError`,
  `FallbackExceptionGroup`, `ToolRetryError`, `ToolFailedError`, `IncompleteToolCall`.

### Approval **[V]**

`ApprovalRequiredToolset` (`toolsets/approval_required.py`, constructed by
`AbstractToolset.approval_required(predicate)`, `toolsets/abstract.py:231-241`). At
execution time, a tool raising `exceptions.ApprovalRequired` is collected as
`deferred_calls['unapproved']` (`_tool_execution.py:626-628`), and
`exceptions.CallDeferred` as `deferred_calls['external']` (`:623-625`).

## A(d) Structured output — how it is enforced

`OutputSchema.build` (`_output.py:457-628`) resolves the author's `output_type` into one
of six schema classes: `AutoOutputSchema` (`:632`), `TextOutputSchema` (`:662`),
`ImageOutputSchema` (`:683`), `NativeOutputSchema` (`:731`), `PromptedOutputSchema`
(`:738`), `ToolOutputSchema` (`:745`). **[V]**

Four **output modes** (`OutputSchema.mode`): `auto`, `text`, `image`, `native`,
`prompted`, `tool`.

- **`tool`** — the schema is exposed as an output *tool*; the model "submits" by calling
  it. Built by `OutputToolset.build` (`_output.py:565`).
- **`native`** — provider-native JSON-schema / structured-output mode.
- **`prompted`** — the JSON Schema is injected into instructions via
  `StructuredTextOutputSchema.build_instructions` (`_output.py:716-728`); the template
  gets `{schema}` appended if absent (`:725-726`).
- **`auto`** — deferred; `Model.prepare_request` resolves it from the model profile:
  `params.with_default_output_mode(self.profile.get('default_structured_output_mode',
  'tool'))` (`models/__init__.py:435`, helper at `:175-184`).

**Enforcement is validate-then-retry, not constrained decoding at the PACT level.**
`ObjectOutputProcessor.validate` calls the pydantic core validator
(`_output.py:940-949`); a `ValidationError` or `ModelRetry` becomes a `ToolRetryError`
carrying a `RetryPromptPart` (`_output.py:121-129`), consuming the output retry budget.
`strict` (`tools.py:565-575`) is a *vendor* flag (OpenAI/Anthropic) passed through; PACT
cannot assume grammar-constrained decoding from pydantic-ai alone.

**Failure behaviour, precisely:**
- Multiple output types → union processor with an envelope model (`UnionOutputProcessor`,
  `_output.py:1074`; envelope at `:1064-1071`).
- `str` plus structured is legal → `ToolOutputSchema(text_processor=...)`
  (`_output.py:579-586`).
- Under `end_strategy='early'`, **only** schema-validated text (i.e.
  `BaseObjectOutputProcessor`) may pre-empt tool calls — plain `str`/`TextOutput` may not,
  because a preamble would silently cancel tools (`_agent_graph.py:1983-1989`). This is a
  genuinely subtle semantic PACT must reproduce or report.

## A(e) Streaming: event types and ordering

Types (`messages.py:3306-3583`) **[V]**:

```
ModelResponseStreamEvent = PartStartEvent | PartDeltaEvent | PartEndEvent | FinalResultEvent   (:3396)
HandleResponseEvent      = FunctionToolCallEvent | FunctionToolResultEvent
                         | OutputToolCallEvent  | OutputToolResultEvent
                         | DeferredToolRequestsEvent | DeferredToolResultsEvent               (:3569)
AgentStreamEvent         = ModelResponseStreamEvent | EnqueuedMessagesEvent | HandleResponseEvent (:3580)
```

**Ordering guarantees actually implemented** (`models/__init__.py:791-853`):

1. `PartStartEvent(index=i)` then zero+ `PartDeltaEvent(index=i)` then `PartEndEvent(index=i)`.
   `PartEndEvent` is synthesised by `iterator_with_part_end` (`:817-852`) and is emitted
   only for `TextPart | ThinkingPart | BaseToolCallPart` (`:828-830`) — other part kinds
   have no deltas and get **no end event**. **[V]**
2. `PartStartEvent` carries `previous_part_kind` and `PartEndEvent` carries
   `next_part_kind` (`messages.py:3326-3333`, `:3367-3374`) — the framework hands the UI
   the adjacency it needs, which no other framework in this corpus does.
3. `FinalResultEvent` is emitted **immediately after** the event that first matched the
   output schema, then the loop `break`s and re-drains the remainder
   (`models/__init__.py:800-815`). So `FinalResultEvent` is *not* last.
4. "If multiple `PartStartEvent`s are received with the same index, the new one should
   fully replace the old one" (`messages.py:3316-3317`).
5. Run-level events (`EnqueuedMessagesEvent`) are interleaved by draining a shared buffer
   *before each pull* on the model stream (`result.py:384-402`).
6. Tool events for a step come from `CallToolsNode._run_stream`, after the model stream
   for that step is exhausted — so within a step: model events, then tool events.

`Agent.run_stream_events()` (`agent/abstract.py:1216`) flattens this into a single
`AsyncIterator[AgentStreamEvent | AgentRunResultEvent]`. **This is the closest thing in
the corpus to a canonical PACT event stream and should be the model for PACT's own.**

## A(f) HITL / interrupt semantics

Pydantic AI has **no interrupt**. It has **deferred tools**, which is a strictly cleaner
model for a portable spec. **[V]**

- Two deferred kinds, both `ToolDefinition.kind`: `'external'` (result produced outside
  the run) and `'unapproved'` (needs human approval) — `tools.py:592-596`.
- A run whose output type includes `DeferredToolRequests` ends *normally* with a
  `DeferredToolRequests{calls, approvals, metadata}` payload (`_deferred.py:26-96`).
- The caller resolves them into `DeferredToolResults{calls, approvals, metadata}`
  (`_deferred.py:154-197`), where an approval is `True|False|ToolApproved(override_args)|
  ToolDenied(message)` and a call result is `ToolReturn|ToolFailed|ModelRetry|
  RetryPromptPart` (`:140-151`).
- Resume: `agent.run(message_history=..., deferred_tool_results=...)`
  (`agent/__init__.py:991-992`) → `UserPromptNode._handle_deferred_tool_results`
  (`_agent_graph.py:612-657`) which **jumps straight to `CallToolsNode`** with
  `tool_call_results` populated, marking already-executed calls `'skip'` (`:642-649`).
- **`ToolApproved.override_args`** (`_deferred.py:103-104`) lets a human *edit* the args
  before execution — validated through `_validate_approved_call`
  (`_tool_execution.py:466-480`).
- **Nothing re-executes.** Tools that already ran in the interrupted step are marked
  `'skip'`; only the deferred ones run. This is *exactly-once* semantics for tool side
  effects across an approval boundary.

> **This is the single most important semantic asymmetry in this audit.** See §C.

## A(g) Memory & context management

There is **no memory subsystem**. Context management is a function over the message list:

- `HistoryProcessor = (messages) -> messages` or `(ctx, messages) -> messages`, sync or
  async (`_history_processor.py:11-26`). Installed as the `ProcessHistory` capability
  which mutates `request_context.messages` in `before_model_request`
  (`capabilities/process_history.py:31-37`).
- The processed history must still end in a `ModelRequest` (`_agent_graph.py:1415-1416`)
  and be non-empty (`:1412-1413`).
- Provider-side compaction: `Model.compact_messages` (`models/__init__.py:332-344`) —
  `NotImplementedError` by default, overridden by OpenAI Responses; there is a
  `CompactionPart` message part handled at `_agent_graph.py:1820-1829`.
- Long-term memory: not present. `mem0`/`letta`/`zep` would be plain toolsets.
- Tool-context discipline **is** first class: `defer_loading` +
  `ToolSearch` capability + `_tool_search.py` (25.5 KB) implement hierarchical tool
  discovery — the exact mechanism SYNTHESIS.md's hierarchical-routing finding calls for.
  `ToolDefinition.defer_loading` carries a documented dual meaning (user intent vs current
  visibility) — `tools.py:611-632`, flagged in-source as tech debt.

## A(h) Multi-agent

**There is no multi-agent construct.** `docs/multi-agent-applications.md:3-10` enumerates
five levels, of which the framework only provides primitives:

1. single agent;
2. **delegation** — call `other_agent.run(..., usage=ctx.usage)` inside a `@agent.tool`
   (`docs/multi-agent-applications.md:38-47`);
3. **programmatic hand-off** — application code calls the next agent (`:179`);
4. `pydantic_graph` for control flow (`:334`);
5. "deep agents" — a composition recipe, not an API (`:338-352`).

What crosses the boundary in (2): the **prompt string** and the **usage object** only.
`RunUsage` accumulates because it is passed by reference (`usage=ctx.usage`). Message
history does **not** cross; the sub-agent gets a fresh run. Hand-off "without coming back"
is achieved with an *output function* (`docs/multi-agent-applications.md:16`).

> **Negative finding:** pydantic-ai cannot express supervisor/swarm/debate/blackboard
> topologies natively. PACT's topology IR has **nothing to map onto** on this adapter and
> must be realised in harness code. **[V]**

## A(i) Model abstraction

`Model(ABC)` — `models/__init__.py:261-...`. Surface **[V]**:

| Member | Line | Required? |
|---|---|---|
| `request(messages, model_settings, model_request_parameters) -> ModelResponse` | `:309-320` | **abstract** |
| `request_stream(messages, settings, params, run_context) -> AsyncGen[StreamedResponse]` | `:346-359` | optional (raises `NotImplementedError`) |
| `count_tokens(...) -> RequestUsage` | `:322-330` | optional |
| `compact_messages(...)` | `:332-344` | optional |
| `cancel_suspended_response`, `continuation_delay` | `:361-376` | optional |
| `customize_request_parameters` | `:378-397` | applies `profile['json_schema_transformer']` |
| `prepare_request` | `:399-...` | merges settings, resolves `auto` output mode, dedupes native tools, resolves `thinking` |
| `model_name`, `system`, `profile` | `:605`, `:697`, `:656` | abstract / property |
| `prepare_messages` | called at `_agent_graph.py:1465` | per-profile wire fixups |

**Capabilities are declared by `ModelProfile`** (`profiles/`), read via `self.profile`:
`default_structured_output_mode`, `supports_thinking`, `thinking_always_enabled`,
`native_output_requires_schema_in_instructions`, `json_schema_transformer`,
`supported_native_tools`, plus provider-specific flags. `infer_model_profile(model_str)`
(`models/__init__.py:1247`) returns a profile **without constructing a provider** — i.e.
**a capability catalogue lookup that works offline**. That is directly usable by PACT's
resolver (D8/D17).

Assumed of any model: only `request()` plus the `model_name` / `system` identity
properties are `@abstractmethod` (`:309`, `:605`, `:697`); **everything behavioural is
optional and profile-gated** — streaming, token counting, compaction, tool calling,
structured-output mode, vision, thinking. `models/CLAUDE.md` states the house rule:
unsupported **settings** are silently ignored, unsupported **features** raise.

## A(j) BONUS — pydantic-ai already has a YAML agent spec

**This is a material finding for D3/D14 that was not in the brief.** **[V]**

`pydantic_ai/agent/spec.py:33-49` defines `AgentSpec(BaseModel)` with fields:
`$schema`, `model`, `name`, `description`, `instructions`, `deps_schema`,
`output_schema`, `model_settings`, `retries`, `end_strategy`, `tool_timeout`,
`metadata`, `capabilities: list[CapabilitySpec]`.

- Loaders: `AgentSpec.from_file(path, fmt)` (`:52-69`), `from_text` (`:71-98`),
  `from_dict` (`:100-110`); writer `to_file` emits a sibling JSON Schema and a
  `# yaml-language-server: $schema=` header (`:112-161`, `:30`).
- `Agent.from_spec` (`agent/__init__.py:573`, overloads at `:599`, `:625`) and
  `Agent.iter(spec=...)` (`agent/__init__.py:1006`, resolution at `_resolve_spec`
  `:1848`) — spec values are *additive at run time* (`:1113-1157`).
- Documented intent, verbatim (`docs/agent-spec.md:3-9`): *"One line to load, no Python
  agent construction code required… Letting non-developers (prompt engineers, domain
  experts) configure agents."* **This is the same audience as PACT's D13, from the
  framework PACT names as its highest-priority target.** It validates the direction and
  raises the bar: PACT's authoring surface must be visibly better than a flat
  `agent.yaml`, and the win has to come from the things `AgentSpec` cannot do —
  tools, evals, SLOs, variants, topology, learning, and the Expansion Rule.
- Serialisable capability registry `CAPABILITY_TYPES` (`capabilities/__init__.py:72-94`):
  `NativeTool, RaiseContentFilterError, ImageGeneration, IncludeToolReturnSchemas,
  Instrumentation, MCP, PrefixTools, PrepareTools, ProcessHistory, ReinjectSystemPrompt,
  SetToolMetadata, Thinking, ToolSearch, Toolset, WebFetch, WebSearch, XSearch`.
- **MCP servers are declarable in YAML**: `MCP.from_spec(url, native, local, id,
  authorization_token, headers, allowed_tools, description, defer_loading)`
  (`capabilities/mcp.py:216-231`).

**Gaps in `AgentSpec` that PACT must fill** (these are the reasons it is not already the
answer): no `tools:` field at all (tools arrive only via capabilities); no evals; no SLOs;
no variants; no topology; no capability *requirements*; no learning; no expansion to a
directory tree; `ProcessHistory` is explicitly **not** spec-serialisable
(`capabilities/process_history.py:41-42`: `get_serialization_name -> None`, "takes a
callable").

---

# PART B — LANGGRAPH

## B(0) Where the agent actually lives now

`langgraph.prebuilt.create_react_agent` is **deprecated**:
`libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py:274-276` carries
`@deprecated(..., category=LangGraphDeprecatedSinceV10)` and the docstring at `:311-318`
says "deprecated in favor of `create_agent` from the `langchain` package, which provides
an equivalent agent factory with a flexible middleware system." `AgentState`,
`AgentStatePydantic`, `AgentStateWithStructuredResponse` are all deprecated too
(`:53-114`). **[V]**

**Consequence for PACT:** the LangGraph adapter's *native* lowering target is
`langchain.agents.create_agent` (`libs/langchain_v1/langchain/agents/factory.py:740+`,
langchain 1.3.14), and the *harness* target is `langgraph.func.entrypoint` / `task` or a
hand-built `StateGraph`. Targeting `langgraph.prebuilt` would be adapter rot on day one.

## B(a) The agent loop

### The engine: Pregel BSP supersteps

`PregelLoop.tick()` — `libs/langgraph/langgraph/pregel/_loop.py:599-681`. One superstep:

1. `if self.step > self.stop: status="out_of_steps"; return False` (`:607-609`).
   `self.stop = self.step + config["recursion_limit"] + 1` (`:1701`, `:1961`);
   `DEFAULT_RECURSION_LIMIT = 25` (`langchain/libs/core/langchain_core/runnables/config.py:171`).
2. `prepare_next_tasks(...)` from the checkpoint + channel versions (`:612-629`).
3. No tasks → `status="done"` (`:653-655`).
4. Drain requested → `status="draining"` (`:657-659`).
5. Replay: re-apply successful writes from `checkpoint_pending_writes` to in-memory tasks
   (`:662-663`, impl `:736-749`), and schedule error handlers for tasks that failed in a
   prior run (`:664`, impl `:751-816`).
6. `interrupt_before` check → raise `GraphInterrupt` (`:667-671`).

`after_tick()` — `:683-726`:
7. `apply_writes(...)` — **channel updates become visible only here** (`:692-698`).
8. Emit `values` if the output keys changed (`:700-707`).
9. `_put_checkpoint({"source": "loop"})` (`:718`).
10. `interrupt_after` check → `GraphInterrupt` (`:720-724`).

The driver loop is `Pregel.stream` — `pregel/main.py:2964-2988`:

```python
while loop.tick():
    for task in loop.match_cached_writes(): loop.output_writes(task.id, task.writes, cached=True)
    for _ in runner.tick([t for t in loop.tasks.values() if not t.writes],
                         timeout=self.step_timeout, get_waiter=get_waiter,
                         schedule_task=loop.accept_push):
        yield from _output(...)
    loop.after_tick()
    if durability_ == "sync": loop._put_checkpoint_fut.result()
```

Explicit invariant in-source (`main.py:2959-2963`): *"Channel updates from step N are only
visible in step N+1; channels are guaranteed to be immutable for the duration of the
step."*

### The agent graph on top (langchain `create_agent`)

`factory.py:1502-1682`. Nodes: `model` (`:1502`), `tools` (`:1506`), plus one node **per
middleware hook** — `{m.name}.before_agent`, `.before_model`, `.after_model`,
`.after_agent` (`:1527`, `:1548`, `:1569`, `:1588`). Edges are wired with
`add_conditional_edges` for the model→tools and tools→model decisions
(`:1632`, `:1656`, `:1669`; helpers `_make_model_to_tools_edge` `:1840`,
`_make_tools_to_model_edge` `:1921`).

The model node itself: `model_node` (`:1433-1451`) builds a `ModelRequest{model, tools,
system_message, response_format, messages, tool_choice, state, runtime}` and calls
`wrap_model_call_handler(request, _execute_model_sync)` (`:1450`). `_execute_model_sync`
(`:1406-1431`) does `_get_bound_model(request)` → `model_.invoke(messages)` →
`_handle_model_output(...)`. It returns `list[Command]` (`_build_commands`, `:193-232`).

**Termination:** `should_continue`-equivalent lives in `_make_model_to_tools_edge`; in the
deprecated prebuilt it is explicit (`chat_agent_executor.py:831-859`): no `tool_calls` →
`post_model_hook` / `generate_structured_response` / `END`; else `v2` fans out one
`Send("tools", ToolCallWithContext(...))` per tool call (`:849-859`).

`_are_more_steps_needed` (`chat_agent_executor.py:620-634`) is the "we're about to hit the
recursion limit" guard: it replaces the response with `"Sorry, need more steps to process
this request."` when `remaining_steps < 2` and there are tool calls. **PACT must treat
this as a degraded terminal state, not a success.**

## B(b) State model

**The state is a set of typed, reducer-merged channels.** `Checkpoint` TypedDict
(`libs/checkpoint/langgraph/checkpoint/base/__init__.py:92-123`): `v`, `id`, `ts`,
`channel_values`, `channel_versions`, `versions_seen`, `updated_channels`. **[V]**

`CheckpointMetadata` (`:38-86`): `source ∈ {input, loop, update, fork}`, `step`,
`parents: dict[ns, checkpoint_id]`, `run_id`, `counters_since_delta_snapshot`.

Channel types (`libs/langgraph/langgraph/channels/`): `LastValue`, `BinaryOperatorAggregate`
(binop), `Topic`, `EphemeralValue`, `NamedBarrierValue`, `UntrackedValue`, `AnyValue`,
`DeltaChannel` (beta). `BaseChannel` requires `checkpoint()` / `from_checkpoint()`
(`channels/base.py:48-64`).

**Checkpointing / durability** — `Durability = Literal["sync","async","exit"]`
(`types.py:87`), documented at `pregel/main.py:3870-3872`:
- `sync` — persisted before the next step starts;
- `async` (default) — persisted while the next step executes;
- `exit` — persisted only when the graph exits.

**Resume** — three distinct, addressable mechanisms **[V]**:
1. `graph.invoke(None, config)` with `thread_id` — resume after interrupt
   (`_loop.py:861-872`).
2. `Command(resume=...)` — supply values for pending `interrupt()` calls
   (`types.py:758-808`, mapped at `_loop.py:903-931`). If **multiple** interrupts are
   pending, a bare value raises `RuntimeError` — you must key by interrupt id
   (`_loop.py:916-920`).
3. **Time travel** — pass an explicit `checkpoint_id`; `_first` detects it
   (`_loop.py:878-896`), drops cached `RESUME` writes so `interrupt()` re-fires
   (`:897-900`), and writes a `{"source":"fork"}` checkpoint so the replay branches
   (`:960-971`).

**State is fully addressable.** `get_state(config)` (`main.py:1392`),
`get_state_history(config)` (`:1480`), `update_state(config, values, as_node, task_id)`
(`:2515-2526`), `bulk_update_state` (`:1590`). `StateSnapshot` (`types.py:643-661`) =
`values, next, config, metadata, created_at, parent_config, tasks, interrupts`.

> **This is LangGraph's decisive advantage and PACT's hardest portability problem.**
> Pydantic AI has no analogue of `update_state(..., as_node=...)`.

## B(c) Tool protocol

- Declaration: `langchain_core.tools.BaseTool` (`libs/core/langchain_core/tools/base.py:427`)
  with `args_schema: ArgsSchema | None` (`:477`), `response_format:
  Literal["content","content_and_artifact"]` (`:541`), `tool_call_schema` (`:671`),
  `invoke`/`ainvoke` (`:731`, `:741`), `_run`/`_arun` (`:877`, `:887`). Schema derivation
  is via pydantic from the signature, or an explicit `args_schema`.
- Binding: `BaseChatModel.bind_tools(tools, tool_choice=..., **kwargs) ->
  Runnable[LanguageModelInput, AIMessage]` (`libs/core/.../chat_models.py:2338-2355`)
  — **abstract, `raise NotImplementedError`** in the base class, so *tool calling is not
  guaranteed by the `BaseChatModel` contract*; it is a per-integration capability.
- Execution: `ToolNode` (`libs/prebuilt/langgraph/prebuilt/tool_node.py:622`).
  - Parallel: `executor.map(self._run_one, ...)` (sync, `:821-824`) /
    `asyncio.gather(*coros)` (async, `:855-858`). **All calls in a step run in parallel;
    there is no barrier/sequential concept.** **[V]**
  - Ordering: `_combine_tool_outputs` (`:862-...`) preserves input order.
  - Errors: `handle_tool_errors` accepts `bool | str | Callable | type[Exception] |
    tuple[type[Exception],...]`, default `_default_handle_tool_errors` (`:383`, ctor
    `:743-775`, dispatch `:987-1006` and `:1058-1061`). A handled error becomes a
    `ToolMessage(status="error")`; an unhandled one propagates and kills the task.
  - **There is no per-tool retry budget.** Retries are a *node-level* `RetryPolicy`
    (`types.py:416-436`: `initial_interval=0.5, backoff_factor=2.0, max_interval=128.0,
    max_attempts=3, jitter=True, retry_on=default_retry_on`) — i.e. transport-level retry,
    not model-corrective retry. Model-corrective retry is middleware
    (`agents/middleware/tool_retry.py`, `model_retry.py`).
  - A tool may return a `Command` to redirect the graph (`tool_node.py:889-912`), and
    `Command(graph=Command.PARENT, goto=[Send(...)])` from multiple tools is merged into
    one parent command (`:896-910`). **This is LangGraph's handoff primitive.**
- Injection: `InjectedState`, `InjectedStore`, `ToolRuntime` (`tool_node.py:802-817`) —
  tools can read graph state and the long-term store.

## B(d) Structured output

`langchain.agents.structured_output` (`factory.py` consumer):

- `ToolStrategy(schema, handle_errors=...)` (`structured_output.py:196-242`) — the schema
  becomes a tool; parsing in `_handle_model_output` (`factory.py:1196-1268`).
- `ProviderStrategy` (`:262`) — provider-native structured output; parsed by
  `ProviderStrategyBinding.parse(output)` (`factory.py:1181-1193`).
- `AutoStrategy` (`:448`) — resolved by `_supports_provider_strategy` (`factory.py:528`)
  / `_is_openai_compatible_model` (`:576`).

**Failure behaviour** (`_handle_structured_output_error`, `factory.py:596-624`):
`handle_errors=False` → raise `StructuredOutputValidationError`; `True` → append a
`ToolMessage` with `STRUCTURED_OUTPUT_ERROR_TEMPLATE` and loop again; `str` → that string;
`type[Exception]`/`tuple` → retry only for those types; callable → its return value.
Multiple structured tool calls in one response → `MultipleStructuredOutputsError`
(`factory.py:1208-1227`).

**There is no retry *budget*.** Structured-output correction loops are bounded only by
`recursion_limit` (25 supersteps). **[V]** PACT's `max_output_retries` has no native
counterpart; it must be enforced by harness or by a `ModelCallLimitMiddleware`
(`agents/middleware/model_call_limit.py` exists).

## B(e) Streaming

`StreamMode = Literal["values","updates","checkpoints","tasks","debug","messages","custom"]`
(`types.py:120-134`). Payload shapes are typed: `ValuesStreamPart` (`:262`),
`UpdatesStreamPart` (`:274`), `MessagesStreamPart` (`:286`), `CustomStreamPart` (`:299`),
`CheckpointStreamPart` (`:310`), `TasksStreamPart` (`:318`), `DebugStreamPart` (`:333`).

**Ordering guarantees** **[V]**:
- Across supersteps: totally ordered (BSP).
- **Within** a superstep: parallel tasks emit in completion order; there is no defined
  per-node order.
- `stream_mode="messages"` (token streaming) is delivered by a **LangChain callback
  handler**, `StreamMessagesHandler(BaseCallbackHandler, _StreamingCallbackHandler)`
  (`pregel/_messages.py:49-50`) — i.e. it is an out-of-band side channel hooked to
  `on_llm_new_token`, *not* an ordered element of the graph event stream.
- The only total order is the mux sequence number: `ProtocolEvent.seq`, with the explicit
  warning "Consumers that need a total order across root events should use `seq`, not
  `params.timestamp` (which is wall-clock and not monotonic)"
  (`stream/_types.py:28-41`, `:14-25`).

> **Negative finding:** LangGraph does **not** provide part-start/delta/end framing.
> There is no `PartEndEvent` equivalent and no `previous_part_kind`/`next_part_kind`
> adjacency. A PACT event stream defined at pydantic-ai's granularity cannot be
> reconstructed from LangGraph's `updates`/`messages` streams alone. **[V]**

## B(f) HITL / interrupt semantics

`interrupt(value)` — `types.py:811-934`. Mechanics **[V]**:
- Reads `PregelScratchpad` from config (`:910-913`); `idx = scratchpad.interrupt_counter()`
  — **interrupts are matched to resume values positionally, by call order within the
  task** (`:911-918`, docstring `:826-828`).
- If no resume value is available, raises `GraphInterrupt((Interrupt.from_ns(value, ns),))`
  (`:927-934`). `Interrupt = {value, id}` where `id = xxh3_128_hexdigest(ns)`
  (`types.py:534-578`).
- Requires a checkpointer (`:830-831`; `Command(resume=...)` without one raises
  `RuntimeError`, `_loop.py:905-908`).

**The critical sentence, verbatim** (`types.py:824`):

> "The graph resumes from the start of the node, **re-executing** all logic."

So HITL in LangGraph is **at-least-once for anything the node did before the interrupt**.
`create_agent` works around this by putting approval in a *separate* `after_model` node
(`factory.py:1569`) that runs *before* the `tools` node, so tools have not executed yet
(`agents/middleware/human_in_the_loop.py:384-...`, `_create_action_and_config` at `:263`).
Decisions are typed:
`approve | edit | reject | respond` (`human_in_the_loop.py:77-133`, `ReviewConfig
.allowed_decisions` `:60`, `InterruptOnConfig` `:146-214`). `respond` synthesises a
success `ToolMessage` on behalf of the tool (`:334-341`); `reject` synthesises an error
`ToolMessage` (`:327-333`).

`interrupt_before` / `interrupt_after` are the other, coarser mechanism — node-name lists
checked in `tick()`/`after_tick()` (`_loop.py:667-671`, `:720-724`).

## B(g) Memory & context management

- Short-term: the checkpointed state, and `add_messages` reducer
  (`graph/message.py:61`), with `REMOVE_ALL_MESSAGES = "__remove_all__"` (`:38`) and
  `RemoveMessage` handling (`:209`).
- Long-term: `BaseStore` reached via `Runtime.store`
  (`runtime.py:16-23` exports `Runtime`; the field is declared at `runtime.py:203`
  and read at `:115`, `:172`; store resolution for a run at `main.py:2594-2597`),
  injected into tools via `InjectedStore` / `ToolRuntime.store`
  (`tool_node.py:806-816`).
- Context engineering middlewares ship in-box:
  `agents/middleware/summarization.py`, `context_editing.py`, `pii.py`,
  `tool_selection.py`, `model_call_limit.py`, `tool_call_limit.py`,
  `todo.py`, `file_search.py`, `provider_tool_search.py`.

> **This is a real capability asymmetry: LangGraph ships a long-term store and
> context-management middlewares; pydantic-ai ships neither.** PACT's memory IR will be
> `native` on LangGraph and `emulated` on pydantic-ai.

## B(h) Multi-agent: what crosses the boundary

Three mechanisms **[V]**:

1. **Subgraph as a node.** A compiled graph is a `Runnable`, so `add_node("x", subgraph)`
   works. State crossing is by **channel-name overlap**: the parent passes the keys the
   subgraph's input schema declares, and merges back the keys it writes. Namespacing is
   by `CONFIG_KEY_CHECKPOINT_NS` (`_loop.py:886`), and the parent's checkpoint
   `metadata["parents"]` maps `ns -> checkpoint_id` (`checkpoint/base:56-60`). The parent
   propagates `CONFIG_KEY_RESUMING` and `CONFIG_KEY_REPLAY_STATE` to subgraphs
   (`_loop.py:1036-1074`).
2. **`Send(node, arg)`** (`types.py:664-752`) — map-reduce; the sent `arg` **can be a
   completely different shape from graph state** (`:669-676`). This is how `create_agent
   v2` fans out tool calls (`chat_agent_executor.py:849-859`).
3. **`Command(graph=..., update=..., goto=..., resume=...)`** (`types.py:758-808`).
   `Command.PARENT = "__parent__"` (`:808`) escapes one level. A tool returning a
   `Command` is the swarm/handoff primitive (`tool_node.py:889-912`).

`langchain/agents/_subagent_transformer.py` exists for subagent streaming.

## B(i) Model abstraction

`BaseChatModel(BaseLanguageModel[AIMessage], ABC)` —
`libs/core/langchain_core/language_models/chat_models.py:272`.

| Member | Line | Contract |
|---|---|---|
| `invoke` / `ainvoke` | `:463`, `:490` | required (via `_generate`) |
| `stream` / `astream` | `:715`, `:842` | falls back to non-streaming if `_stream` absent |
| `_generate` | `:2181` | the real abstract |
| `_stream` | `:2227` | optional |
| `bind_tools` | `:2338-2355` | **`raise NotImplementedError`** — not part of the base contract |
| `with_structured_output` | `:2357-...` | default implementation exists |

Model selection: `langchain.chat_models.init_chat_model` (`chat_models/__init__.py:7`).
Capability metadata lives in the separate `langchain-profiles` package
(`libs/model-profiles`, generated data under each partner's `data/`) — **not** in the core
model object. **[I]** For PACT's offline catalogue (D8/D17) this means the LangGraph
adapter must ship its own capability table or vendor `langchain-profiles` data; there is
no `Model.profile` equivalent to read at runtime the way pydantic-ai has.

---

# PART C — DIVERGENCE MATRIX

Legend: **≡** same semantics · **≈** expressible with adapter work · **✗** genuinely
divergent, PACT must pick one and report.

| # | Concern | Pydantic AI | LangGraph / `create_agent` | Verdict |
|---|---|---|---|---|
| C1 | Unit of execution | graph node (`UserPrompt/ModelRequest/CallTools`) | Pregel **superstep** over channels | ✗ |
| C2 | Step counter | `state.run_step` (`_agent_graph.py:1358`) | `loop.step`, bounded by `recursion_limit=25` | ✗ |
| C3 | State | message list only (`GraphAgentState:294`) | arbitrary reducer-merged channels (`Checkpoint:104`) | ✗ |
| C4 | State addressability | none (in-memory nodes) | `get_state` / `update_state(as_node=)` / `checkpoint_id` time travel | ✗ |
| C5 | Persistence | none in core; opt-in durable capabilities | `BaseCheckpointSaver`, `durability ∈ {sync,async,exit}` | ✗ |
| C6 | HITL primitive | **deferred tools**, exactly-once, no re-execution (`_deferred.py`) | **`interrupt()`**, node re-executes from start (`types.py:824`) | ✗ **fatal-if-ignored** |
| C7 | HITL edit-args | `ToolApproved(override_args=)` (`_deferred.py:103`) | `EditDecision` (`human_in_the_loop.py:84`) | ≈ |
| C8 | Tool parallelism | parallel with `sequential=True` **barriers** + 3 event-order modes (`_tool_execution.py:89-108`, `:649-651`) | always fully parallel (`tool_node.py:821`, `:855`) | ✗ (LangGraph cannot express a barrier) |
| C9 | Tool retry | **per-tool-name budget**, reset on success (`tool_manager.py:123-135`, `:185-195`) | node `RetryPolicy` (transport) + optional middleware | ✗ |
| C10 | Tool error → model | `ModelRetry`→`RetryPromptPart`; `ToolFailed` terminal | `handle_tool_errors` → `ToolMessage(status="error")` | ≈ |
| C11 | Output modes | `auto/text/image/native/prompted/tool` (`_output.py:449-451`) | `ToolStrategy/ProviderStrategy/AutoStrategy` | ≈ (no `prompted`, no `image` output) |
| C12 | Output retry budget | `max_output_retries` (`_agent_graph.py:367`) | none; bounded by `recursion_limit` | ✗ |
| C13 | Text-vs-tool precedence | 3 `end_strategy` values with a documented retry-wins rule | implicit: tool calls always win | ✗ |
| C14 | Stream framing | `PartStart/Delta/End` + `FinalResultEvent` + adjacency hints | `values/updates/messages/custom/...`; token stream is a **callback side channel** (`_messages.py:49`) | ✗ |
| C15 | Stream total order | single ordered `AgentStreamEvent` iterator (`result.py:384-402`) | `ProtocolEvent.seq` only (`stream/_types.py:28-41`) | ✗ |
| C16 | Multi-agent | delegation-by-tool only; nothing crosses but prompt + `usage` | `Send`, subgraph, `Command(graph=PARENT)`, shared channels | ✗ |
| C17 | Long-term memory | none | `BaseStore` via `Runtime.store` | ✗ |
| C18 | Context management | `HistoryProcessor` fn (not spec-serialisable) | summarization/context-editing/PII middlewares | ≈ |
| C19 | Model capability metadata | `ModelProfile`, offline via `infer_model_profile` (`models/__init__.py:1247`) | external `langchain-profiles` package | ✗ |
| C20 | Tool calling guaranteed by model ABC | no (`Model.request` only), profile-gated | no (`bind_tools` raises `NotImplementedError`, `chat_models.py:2355`) | ≡ (both must gate) |
| C21 | Declarative YAML form | **`AgentSpec` exists** (`agent/spec.py:33`), MCP declarable | none in core | ✗ |
| C22 | Loop bound default | `request_limit=50` (`usage.py:302`) | `recursion_limit=25` (`config.py:171`) | ✗ |
| C23 | Degraded terminal state | raises `UsageLimitExceeded` | may inject `"Sorry, need more steps…"` as the answer (`chat_agent_executor.py:684-692`) | ✗ |

---

# PART D — HARNESS MODE: is D12 implementable?

**Yes, for both, but by different mechanisms and with different residual losses.**

## D.1 Pydantic AI in harness mode

### Model transport — exact entry points **[V]**

| Purpose | API | Location |
|---|---|---|
| Resolve a model string offline → `Model` | `pydantic_ai.models.infer_model(name)` | `models/__init__.py:1280-1282` |
| Resolve capabilities without a provider | `pydantic_ai.models.infer_model_profile(name)` | `models/__init__.py:1247` |
| One non-streamed call | `pydantic_ai.direct.model_request(model, messages, *, model_settings, model_request_parameters, instrument)` | `direct.py:55-105` |
| Sync variant | `pydantic_ai.direct.model_request_sync(...)` | `direct.py:108-161` |
| One streamed call | `pydantic_ai.direct.model_request_stream(...)` | `direct.py:164` |
| Sync streamed | `pydantic_ai.direct.model_request_stream_sync(...)` | `direct.py:227` |
| Raw ABC (bypassing `direct`) | `Model.request(messages, model_settings, model_request_parameters)` | `models/__init__.py:309-320` |
| Raw streaming ABC | `Model.request_stream(messages, settings, params, run_context)` | `models/__init__.py:346-359` |

`direct.py:1-7` states the contract exactly: *"methods for making imperative requests to
language models with minimal abstraction… thin wrappers around `Model` implementations."*
`model_request` at `:99-105` is literally `_prepare_model(...)` then
`model_instance.request(list(messages), model_settings, mrp)`.

**Everything PACT needs to control the wire is in `ModelRequestParameters`**
(`models/__init__.py:132-186`): `function_tools`, `native_tools`, `output_mode`,
`output_object`, `output_tools`, `prompted_output_template`, `allow_text_output`,
`allow_image_output`, `instruction_parts`, `thinking`. PACT builds this itself; the
`Model` subclass translates it to the provider wire and back to a canonical
`ModelResponse`. **That is exactly the "framework as transport" contract D12 asks for.**

### Tool transport — exact entry points **[V]**

| Purpose | API | Location |
|---|---|---|
| Declare a tool from JSON Schema + a dispatcher callable | `pydantic_ai.tools.Tool.from_schema(function, name, description, json_schema, takes_ctx=, sequential=, args_validator=)` | `tools.py:438-493` |
| Implement a whole toolset | subclass `pydantic_ai.toolsets.AbstractToolset`: `get_tools(ctx)`, `call_tool(name, args, ctx, tool)` | `toolsets/abstract.py:165-182` |
| MCP | `pydantic_ai.mcp.MCPToolset`, or declaratively `capabilities.MCP.from_spec(url, ...)` | `capabilities/mcp.py:216-231` |

Note: `AbstractToolset.get_tools` / `call_tool` take a `RunContext`
(`_run_context.py`) which PACT would have to fabricate. **[I]** For harness mode it is
cleaner to *not* use pydantic-ai toolsets at all: PACT owns tool dispatch and only uses
`ToolDefinition` as a wire-format DTO to hand to `ModelRequestParameters.function_tools`.

### What PACT must reimplement (the loop it takes over)

Everything in `_agent_graph.py` — approximately: history cleaning (`:2676`), dangling
tool-call repair (`:2529`), the four-node state machine, `end_strategy`
(`_tool_execution.py:158-165`), retry budgets, deferred-tool batching
(`_tool_execution.py:769-908`), the streaming part-framing (`models/__init__.py:791-853`)
and the `FinalResultEvent` detection (`_get_final_result_event`).

### Residual loss in harness mode on pydantic-ai

| Lost | Why | Severity |
|---|---|---|
| Capability hook stack (`before/after/wrap_model_request`, `wrap_tool_execute`, …, 40+ hooks at `capabilities/abstract.py:459-1005`) | they hang off the agent graph, not off `Model` | medium — PACT gets its own hook model instead |
| `InstrumentedModel` OTel spans | `direct` accepts `instrument=` (`direct.py:61`) so **this one is recoverable** | none |
| Durable-exec wrappers (Temporal/DBOS/Prefect) | they wrap `Agent`, not `Model` | high if PACT wants durability *from pydantic-ai*; low if PACT owns durability |
| `AgentSpec` YAML round-trip | it constructs an `Agent` | medium — PACT is the spec |

**Verdict: pydantic-ai harness lowering is clean and low-risk.** `direct.model_request` is
a first-class, documented, supported API whose entire stated purpose is this use case.

### Why *not* `AbstractAgent` **[V]**

`AbstractAgent.iter` is the only abstract execution method (`agent/abstract.py:1387-1388`);
`run`, `run_sync`, `run_stream`, `run_stream_events` are all implemented on top of it. But
`iter` must return an `AgentRun`, and `AgentRun._graph_run` is typed
`GraphRun[GraphAgentState, GraphAgentDeps[AgentDepsT, Any], FinalResult[OutputDataT]]`
(`run.py:96-98`). **A PACT harness cannot implement `AbstractAgent` without constructing
pydantic-ai's own graph state objects.** So "PACT agent that *is* a pydantic-ai Agent" is
not on offer; "PACT loop that *uses* pydantic-ai models and tools" is.

## D.2 LangGraph in harness mode

Two viable shapes; **prefer (B)**.

### (A) Bare transports, no LangGraph at all

| Purpose | API | Location |
|---|---|---|
| Resolve model | `langchain.chat_models.init_chat_model(...)` | `libs/langchain_v1/langchain/chat_models/__init__.py:7` |
| Bind tools | `BaseChatModel.bind_tools(tools, tool_choice=...) -> Runnable` | `libs/core/.../chat_models.py:2338` |
| Call | `.invoke(messages)` / `.ainvoke(messages)` | `:463`, `:490` |
| Stream | `.stream(...)` / `.astream(...)` | `:715`, `:842` |
| Structured | `.with_structured_output(schema, include_raw=)` | `:2357` |
| Tools | `BaseTool.ainvoke({...})` | `libs/core/langchain_core/tools/base.py:741` |

This gives PACT a pure transport and **zero** LangGraph semantics — no checkpointing, no
interrupt, no store. It satisfies D12's letter but throws away the one thing LangGraph is
uniquely good at.

### (B) **Recommended:** PACT loop inside `@entrypoint`, model/tool calls as `@task`

| Purpose | API | Location |
|---|---|---|
| Wrap PACT's loop as a durable, checkpointed, resumable unit | `@langgraph.func.entrypoint(checkpointer=, store=, cache=, retry_policy=, context_schema=)` | `libs/langgraph/langgraph/func/__init__.py:262`, `__call__` at `:516-620` |
| Memoised, retried, cached unit of work | `@langgraph.func.task(name=, retry_policy=, cache_policy=, timeout=)` | `func/__init__.py:132-251` |
| Pause for a human | `langgraph.types.interrupt(value)` | `types.py:811-934` |
| Resume | `graph.invoke(Command(resume=...), config)` | `types.py:758-808` |
| Carry state across invocations | `previous:` parameter + `entrypoint.final(value=, save=)` | `func/__init__.py:279-290`, `:476-504` |
| Inspect / edit state | `graph.get_state(config)`, `graph.update_state(...)` | `pregel/main.py:1392`, `:2515` |

`entrypoint.__call__` (`func/__init__.py:576-609`) builds a **single-node Pregel graph**
with channels `START: EphemeralValue`, `END: LastValue`, `PREVIOUS: LastValue`. That is
the whole trick: PACT's loop is one node; PACT's model calls and tool calls are `@task`s.

**The constraint that makes or breaks this** **[V]**: `@task` results are memoised
**positionally**. `_call` (`pregel/_runner.py:700-760`) obtains the ordinal from
`scratchpad.call_counter()` (`:720-724`) and, if the resulting task already has writes,
returns the recorded `RETURN`/`ERROR` value without re-executing (`:745-756`).
`PregelScratchpad` (`_internal/_scratchpad.py:8-19`) holds `call_counter`,
`interrupt_counter`, `subgraph_counter` — all positional.

> **Therefore: PACT's harness loop body, when lowered onto LangGraph's functional API,
> must be deterministic in the *sequence of `@task` invocations* given the same replayed
> results.** Any nondeterminism (dict iteration order, `random`, wall-clock branching,
> concurrent `asyncio.gather` whose completion order changes which task is created next)
> silently mis-binds memoised results. This is a hard, non-negotiable constraint on how
> PACT writes its loop, and it must be a documented conformance requirement.

Same applies to `interrupt()`: resume values bind by call ordinal within the task
(`types.py:911-918`).

### Residual loss in harness mode on LangGraph

| Lost | Why | Severity |
|---|---|---|
| `stream_mode="updates"` per-node granularity | there is only one node | low — PACT emits its own events via `StreamWriter` / `stream_mode="custom"` (`types.py:136-139`) |
| Graph visualisation / Studio node view | one node | low, cosmetic |
| Superstep-level parallelism across PACT nodes | PACT parallelises with `@task` futures instead | none |
| `interrupt_before` / `interrupt_after` by node name | no named nodes | low — PACT calls `interrupt()` explicitly |
| Per-node `RetryPolicy` | replaced by per-`@task` `retry_policy` | none |

**Verdict: LangGraph harness lowering is implementable and actually *better* than native
lowering for fidelity**, at the cost of a determinism obligation and losing node-level
observability.

## D.3 Answer to the assignment's precise question

> **Which of these can PACT drive in harness mode, and what is the exact API entry point?**

| Capability | Pydantic AI entry point | LangGraph entry point | Harness-drivable? |
|---|---|---|---|
| Model call (non-stream) | `pydantic_ai.direct.model_request` — `direct.py:55` | `BaseChatModel.invoke` after `bind_tools` — `chat_models.py:463`, `:2338` | **Yes, both** |
| Model call (stream) | `pydantic_ai.direct.model_request_stream` — `direct.py:164` | `BaseChatModel.astream` — `chat_models.py:842` | **Yes, both** (framing differs, see C14) |
| Tool schema on the wire | `ModelRequestParameters.function_tools: list[ToolDefinition]` — `models/__init__.py:136` | `bind_tools(tools=[...])` — `chat_models.py:2338` | **Yes, both** |
| Tool execution | PACT's own; optionally `AbstractToolset.call_tool` — `toolsets/abstract.py:170` | PACT's own; optionally `BaseTool.ainvoke` — `tools/base.py:741` | **Yes, both** |
| Structured output | `ModelRequestParameters.output_mode/output_object/output_tools` — `models/__init__.py:139-142` | `with_structured_output` — `chat_models.py:2357`, or PACT-built tool | **Yes, both** |
| Loop / termination | PACT owns | PACT owns | **Yes, both** |
| Retry budgets | PACT owns | PACT owns | **Yes, both** |
| HITL pause/resume | *no framework support needed* — PACT returns a `DeferredToolRequests`-shaped payload and is re-entered with results | `langgraph.types.interrupt` inside `@task`/`@entrypoint` — `types.py:811` | **Yes, both — but with different re-execution semantics (C6)** |
| Durability / kill-and-resume | **NOT harness-drivable via `direct`.** Requires the durable-exec capabilities that wrap `Agent`, or PACT's own runtime | `@entrypoint(checkpointer=...)` — `func/__init__.py:262` | **LangGraph yes; pydantic-ai no** |
| Long-term memory store | none | `Runtime.store` / `BaseStore` — `runtime.py`, `main.py:2594-2597` | **LangGraph yes; pydantic-ai no** |
| Model capability lookup (offline) | `infer_model_profile` — `models/__init__.py:1247` | none in core (`langchain-profiles` is a separate package) | **pydantic-ai yes; LangGraph no** |

---

# PART E — WHAT RESISTS (brutal section)

## E1. The HITL semantics are not reconcilable; PACT must choose and report

Pydantic AI: deferred results, **nothing re-runs** (`_tool_execution.py:249-274` marks
already-settled calls `'skip'`).
LangGraph: `interrupt()` **re-runs the node from the top** (`types.py:824`).

PACT cannot have both. If PACT picks pydantic-ai's semantics (exactly-once) — which it
should, because at-least-once tool side effects are indefensible in a spec that admits
`computer_use` (D16) — then on LangGraph the harness must ensure every side-effecting
operation is inside its own `@task` (so it is memoised on replay) and that the loop body
above the interrupt is pure. **That is a codegen obligation, not a runtime one, and it
must be checked by the CTS.**

If PACT ever supports *native* lowering onto a hand-written LangGraph node containing
`interrupt()`, the lattice entry for HITL must be `degraded`, with the report stating "tool
side effects before the approval point may re-execute."

## E2. `sequential=True` tool barriers have no LangGraph expression

`_segment_by_barriers` (`_tool_execution.py:89-108`) is a real, load-bearing feature —
"tools emitted before it complete first, it runs alone, tools after it start only once it
finishes." `ToolNode` runs everything in parallel (`tool_node.py:821`, `:855`). In harness
mode PACT implements barriers itself, so this is fine; in **native** LangGraph lowering it
is `unsupported`, full stop. Do not pretend otherwise.

## E3. `end_strategy` is three loop semantics wearing one flag

`'early' | 'graceful' | 'exhaustive'` (`_tool_execution.py:122-153`) plus the retry-wins
rule plus the "only schema-validated text may pre-empt tools" rule
(`_agent_graph.py:1983-1989`). This is a 3×2×2 behavioural space that *changes which tools
execute and which output wins*. If PACT does not model it, importing a real pydantic-ai
agent is lossy in a way that changes side effects. **PACT's loop IR must have a first-class
`output_arbitration` policy with at least these three values.**

## E4. LangGraph's state model is strictly more expressive and PACT will not capture it

Arbitrary channels with user-supplied reducers (`channels/binop.py`,
`graph/message.py:61`), `Send` with off-schema payloads (`types.py:669-676`),
`Command(graph=PARENT)` (`types.py:808`), `update_state(as_node=)` (`main.py:2515`),
time-travel forks (`_loop.py:960-971`), `DeltaChannel` snapshots
(`checkpoint/base:63-86`). A PACT importer over a real LangGraph app will produce an
`ImportReport` with many entries, and D15 ("translate or nothing") means those apps are
**rejected**, not wrapped. That is the correct call under D15 but it needs to be said out
loud: **the LangGraph importer will refuse a large fraction of real-world LangGraph
codebases.** Budget for that in D10's "migration tool" positioning.

## E5. Streaming fidelity is asymmetric and PACT's event model will over-promise on LangGraph

Pydantic AI gives part-level framing with adjacency hints
(`messages.py:3326-3333`, `:3367-3374`); LangGraph gives an out-of-band callback token
stream (`pregel/_messages.py:49`) with only a mux `seq` for ordering
(`stream/_types.py:28-41`). If PACT's canonical event stream is defined at pydantic-ai's
granularity — which it should be, since it is the richer one and voice/TTFT (D16) needs it
— then in **harness** mode PACT synthesises the framing itself from
`BaseChatModel.astream` chunks (fine), but in **native** mode the LangGraph lattice entry
for streaming is `degraded`.

## E6. `create_react_agent` is deprecated; the adapter target moved packages

`chat_agent_executor.py:274-276`, `:311-318`. The LangGraph adapter must target
`langchain.agents.create_agent` (`langchain` 1.3.14) for native lowering and
`langgraph.func` (`langgraph` 1.2.9) for harness lowering. This is R2 (adapter rot)
manifesting **before the first adapter is written**, and is direct evidence for the
"harness lowering is the conformance floor" thesis: `langgraph.func.entrypoint`/`task` and
`BaseChatModel.invoke` are far more stable surfaces than any agent factory.

## E7. Pydantic AI already ships a competing YAML spec

`agent/spec.py:33-49` + `capabilities/__init__.py:72-94`. It is narrower than PACT (no
tools field, no evals, no SLOs, no topology, no variants) but it is real, schema-generating
(`model_json_schema_with_capabilities`, `spec.py:171-226`), and it can declare MCP servers
(`capabilities/mcp.py:216`). Two consequences:
(i) PACT's pydantic-ai adapter has an unusually short native-lowering path for the
single-agent slice — emit an `AgentSpec` dict and call `Agent.from_spec`;
(ii) PACT must be able to **import** `AgentSpec` files, and the `ProcessHistory` capability
(`process_history.py:41-42`, `get_serialization_name() -> None`) is a guaranteed
`ImportReport` entry because it is not spec-serialisable *in pydantic-ai itself*.

## E8. Default loop bounds differ by 2× and one of them lies

`request_limit=50` (`usage.py:302`) vs `recursion_limit=25`
(`langchain_core/runnables/config.py:171`), and LangGraph's prebuilt agent will *fabricate
an answer* (`"Sorry, need more steps to process this request."`,
`chat_agent_executor.py:684-692`) rather than fail. Under T7 (structural honesty) PACT must
never map a budget-exhaustion to a successful terminal output. **PACT's loop IR needs an
explicit `on_budget_exhausted: fail | truncate | summarise` and the default must be
`fail`.**

## E9. Neither framework guarantees tool calling at the model ABC level

`Model.request` is the only *behavioural* abstract method in pydantic-ai
(`models/__init__.py:309`; `model_name`/`system` at `:605`/`:697` are identity only);
`BaseChatModel.bind_tools` raises `NotImplementedError` (`chat_models.py:2355`). So
"this model can call tools" is a *catalogue* fact in both, not an *interface* fact. PACT's
capability predicate language (O3.1) is therefore load-bearing for correctness, not just
for planning: without it, PACT cannot know a binding will work before it runs.

## E10. Offline capability metadata exists on only one side

`infer_model_profile(model: str) -> ModelProfile` (`models/__init__.py:1247-1255`)
resolves capabilities **without constructing a provider** — a genuinely offline lookup, and
exactly what D8/D17 need. LangGraph/LangChain has no runtime equivalent; profiles are in a
separate generated package. PACT's `models/catalog.yaml` must be authoritative, and the
pydantic-ai profile table is the best available *seed* for it.

---

# PART F — DESIGN IMPLICATIONS FOR PACT (actionable)

1. **Define the harness contract as exactly two verbs.** `model_call(messages, params) ->
   response` and `tool_call(name, args) -> result`. Adapter authors implement only those.
   Reference bindings: `pydantic_ai.direct.model_request` / `model_request_stream`
   (`direct.py:55`, `:164`); `BaseChatModel.bind_tools(...).ainvoke/.astream`
   (`chat_models.py:2338`, `:490`, `:842`).

2. **Make `ModelRequestParameters` the shape of PACT's wire-request IR.** It is the only
   object in either framework that already carries function tools + native tools + output
   mode + output object + output tools + prompted template + `allow_text_output` +
   `allow_image_output` + instruction parts + thinking, all in one place
   (`models/__init__.py:132-163`). Copy it, add modality fields for D16.

3. **Adopt pydantic-ai's deferred-tool model as PACT's normative HITL semantics** and
   forbid re-execution. Spec text: "a tool that has produced a result MUST NOT be
   re-invoked when a run is resumed." Enforce on LangGraph by requiring every side-effecting
   step to be its own `@task` (memoised at `_runner.py:745-756`), and add a CTS case that
   kills the process mid-approval and asserts each tool ran exactly once.

4. **Require determinism of the harness loop body under replay, and say so normatively.**
   `@task`/`interrupt()` bind by ordinal (`_internal/_scratchpad.py:13-19`,
   `_runner.py:720-724`, `types.py:911-918`). PACT's loop IR must be evaluable with no
   uncontrolled nondeterminism: no set/dict-iteration-order-dependent dispatch, no
   wall-clock branching, and parallel fan-out must fix the task-creation order before
   awaiting.

5. **Add `output_arbitration` to the loop IR with values `early | graceful | exhaustive`,
   defaulting to `graceful`,** plus a boolean `retry_wins` and a
   `text_may_preempt_tools: never | schema_validated_only`. Anything less loses
   `_tool_execution.py:122-153` and `_agent_graph.py:1983-1989` on import.

6. **Add `sequential: bool` (barrier) to the tool IR** — `ToolDefinition.sequential`,
   `tools.py:577-585` — and a run-scoped `parallel_execution_mode: parallel |
   parallel_ordered_events | sequential` (`tool_manager.py:102`). Declare it `unsupported`
   in any native LangGraph lattice.

7. **Split the retry budget into two named budgets in the IR: `tool_retries` (per tool
   name) and `output_retries` (per run).** Pydantic AI has exactly this split
   (`AgentRetries`, `agent/abstract.py:94`; enforcement at `tool_manager.py:185` and
   `_agent_graph.py:353`). LangGraph has neither, so both are harness-enforced there.
   Also specify the reset rule: per-tool count resets on success
   (`tool_manager.py:123-135`) — it is observable behaviour.

8. **Specify `on_budget_exhausted: fail | truncate | summarise`, default `fail`,** and make
   any adapter that fabricates a terminal answer on budget exhaustion
   (`chat_agent_executor.py:684-692`) report `degraded`.

9. **Define PACT's stream event vocabulary as a superset of
   `AgentStreamEvent`** (`messages.py:3580`): `part_start / part_delta / part_end /
   final_result / tool_call / tool_result / deferred_requests / deferred_results / enqueued`,
   with `previous_part_kind` / `next_part_kind` adjacency (`messages.py:3326`, `:3367`) and
   the rule "`part_end` is only emitted for delta-bearing part kinds"
   (`models/__init__.py:828-830`). Note in the spec that `final_result` is emitted at the
   point of match, not at stream end (`models/__init__.py:800-810`).

10. **Carry two distinct identifiers in the IR and in every event: `run_id` and
    `conversation_id`,** with pydantic-ai's exact resolution rule — `run_id` is never
    inherited from history, `conversation_id` is inherited if present
    (`_agent_graph.py:298-310`, `resolve_run_id` `:256`, `resolve_conversation_id` `:229`).
    This is the cheapest thing PACT can copy that both frameworks and the Bud run ledger
    need.

11. **Model PACT state as `messages + named channels`, not one or the other.** Messages are
    the portable core (both frameworks agree); named channels with declared reducers are
    required to import anything real from LangGraph (`checkpoint/base:104-120`,
    `channels/`). Mark channel reducers as `code`-typed escapes (F-2/F-3) unless they are
    drawn from a closed set (`append`, `last`, `max`, `union`, `topic`) that has a no-code
    YAML form — D14 requires the closed set to be the default.

12. **Make durable-run state addressable in the IR from day one**: `thread_id`,
    `checkpoint_id`, `parent_checkpoint_id`, `step`, `source ∈ {input, loop, update, fork}`
    (`checkpoint/base:38-60`), plus a `StateSnapshot`-shaped read model
    (`values, next, tasks, interrupts, parent`, `types.py:643-661`). Pydantic AI cannot
    supply these, so the pydantic-ai lattice entry for AC-2.6 kill-and-resume is
    `emulated` (PACT persists its own message-history checkpoint) — say so explicitly
    rather than claiming L4.

13. **Specify three durability levels matching LangGraph's** — `sync | async | exit`
    (`types.py:87`, `main.py:3870-3872`) — because they are the observable difference
    between "resumable after kill" and "not". Default `async`; require `sync` for any run
    declaring `computer_use` or an approval gate.

14. **Ship an offline model-capability seed derived from `pydantic_ai.profiles`.**
    `infer_model_profile` (`models/__init__.py:1247`) is a provider-free lookup; harvest
    its table into `models/catalog.yaml` at build time so D17 (air-gapped) holds without a
    network call, and record provenance = "pydantic-ai profiles @ <sha>".

15. **Treat `pydantic_ai.agent.spec.AgentSpec` as a first-class import source and a
    superset target.** PACT must (a) import `AgentSpec` YAML losslessly-or-reported, (b)
    emit it for the single-agent native-lowering fast path, and (c) enumerate the fields
    PACT adds that it lacks — `tools`, `evals`, `slo`, `capabilities_required`, `variants`,
    `topology`, `memory`, `loop`, `learning`. Add a fixture asserting round-trip
    `AgentSpec → PACT → AgentSpec` with an explicit report entry for `ProcessHistory`
    (`process_history.py:41-42`).

16. **Declare MCP the only no-code tool mechanism in v1.** Both frameworks reach MCP
    declaratively-or-nearly: pydantic-ai via `capabilities.MCP.from_spec(url, ...)`
    (`capabilities/mcp.py:216-231`), LangGraph via a `BaseTool` list. Everything else
    (`Tool.from_schema` needs a callable, `tools.py:440`) is codegen inside the adapter,
    which is acceptable under D14 only because the *author* never writes it.

17. **Pin the LangGraph adapter to `langgraph.func` + `langchain_core` model/tool ABCs, not
    to any agent factory.** `create_react_agent` is already deprecated
    (`chat_agent_executor.py:274-276`) and `create_agent` lives in a different package with
    a different release cadence (`langchain` 1.3.14 vs `langgraph` 1.2.9). Record both
    versions in `pact.lock`.

18. **Add a `loop_bound` field with explicit units and require adapters to map it.**
    Pydantic AI: `UsageLimits.request_limit` (default 50, `usage.py:302`). LangGraph:
    `recursion_limit` (default 25, `config.py:171`) counted in *supersteps*, not model
    calls — a PACT harness step ≈ 1 superstep only in shape (B); in native lowering one
    PACT step costs ≥ 2 supersteps. Publish the conversion in the lattice or CTS runs will
    fail for reasons unrelated to fidelity.

19. **Make "long-term memory" an optional IR feature with an explicit lattice entry.**
    LangGraph has `BaseStore` via `Runtime.store` (`main.py:2594-2597`); pydantic-ai has
    nothing. Do not invent a memory abstraction in the core — expose a `memory:` resource
    kind (G-5) whose default provider is a PACT-owned store, and let the LangGraph adapter
    bind it to `BaseStore` natively.

20. **Write the CTS HITL case first.** It is the single test that discriminates every
    divergence in this audit at once: approval mid-parallel-tool-batch, process kill,
    resume, assert (i) exactly-once tool execution, (ii) `override_args` honoured,
    (iii) resulting message history byte-identical modulo timestamps across both adapters.
    If that passes on both, D12 is proven; if it does not, nothing else matters.

---

# PART G — Things I did NOT verify (honesty ledger)

- I did not execute anything. No test was run; no agent was invoked. All behaviour claims
  are read from source.
- I did not read every LangGraph channel implementation (`binop.py`, `topic.py`,
  `named_barrier_value.py`, `delta.py`) — I read `base.py` and the `Checkpoint` TypedDict
  and inferred reducer semantics from `add_messages` and `apply_writes` call sites. **[I]**
- I did not read `pydantic_graph`'s `GraphRun`/`GraphBuilder` internals; I read how
  `_agent_graph` uses them.
- I did not audit `durable_exec/{temporal,dbos,prefect}` implementations, only the
  directory listing and `durable_exec/AGENTS.md`. The claim "durable-exec wraps `Agent`
  not `Model`" is inferred from the presence of `_agent.py` + `_model.py` + `_toolset.py`
  in each and from `AGENTS.md:5`. **[I]**
- I did not verify `langchain-profiles` contents (the package lives at
  `libs/model-profiles` in the langchain repo; I read `CLAUDE.md`'s description of the
  CLI, not the data). **[I]**
- I did not read the JS/TS sides (`sdk-js`, `vercel-ai`), which are out of scope for this
  stream but matter for D4's TypeScript adapters.
- Version note: `pydantic-ai-slim` has **no static version string** — it is derived from
  git tags via `uv-dynamic-versioning` (`pydantic_ai_slim/pyproject.toml:5-13`), so I can
  cite only the commit SHA, not a release number.
