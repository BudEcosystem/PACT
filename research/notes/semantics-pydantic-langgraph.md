# Semantics audit: Pydantic AI vs LangGraph (source-level)

**Stream:** `semantics-pydantic-langgraph`
**Revision:** 2 — 2026-08-07. Supersedes revision 1 (2026-07-26).
**Purpose:** Determine whether PACT Decision **D12** (harness lowering — PACT owns loop
semantics, frameworks are model/tool transports) is implementable against the two
prototype adapters (D5, D7), and enumerate every semantic divergence PACT's IR must
either express or honestly report as lossy.

## 0. Provenance

| Repo | Path | HEAD | Version |
|---|---|---|---|
| pydantic-ai | `research/repos/frameworks/pydantic-ai` | `ed0f40c0e5061722f7d9f579ed7efff1b74e3ea5` (2026-07-25) | `pydantic-ai-slim` and `pydantic-graph` both use `uv-dynamic-versioning` from git tags — **no static version string** (`pydantic_graph/pyproject.toml:4-15`). Cite the SHA. |
| langgraph | `research/repos/frameworks/langgraph` | `30c4d58db86455128e42ddec96b1ba53c553ba22` (2026-07-25) | `libs/langgraph/pyproject.toml:8` → `1.2.9` |
| langchain | `research/repos/frameworks/langchain` | same corpus | `libs/langchain_v1` → `1.3.14`; `libs/core` → `1.5.1` |

Paths are relative to those repo roots. **[V]** = read in source this session.
**[V1]** = read in source in revision 1 and structurally re-confirmed here but not
line-by-line re-read. **[I]** = inference.

Nothing was executed. No agent was run, no test invoked.

### 0.1 Corrections to revision 1

Revision 1 is wrong or materially incomplete on five points. They are corrected inline
and summarised here because each one changes a design conclusion:

| # | Revision 1 said | Truth | Consequence |
|---|---|---|---|
| X1 | "pydantic-ai cannot express supervisor/swarm/debate topologies natively; PACT's topology IR has nothing to map onto" | **`pydantic_graph` was rewritten** and now ships `Fork(is_map=)`, `Join(reducer, initial)`, `Decision`, `Step`, fork-stacks, sibling cancellation and five built-in reducers (`pydantic_graph/__init__.py:11-36`, `node.py:60-77`, `graph_builder.py:1366-1405`, `decision.py:41-46`) | PACT **does** have a native topology lowering target on the pydantic-ai side. This materially improves the pydantic-ai adapter's lattice for G-2/O5.1. |
| X2 | "Checkpointing: none in the core" (implying `pydantic_graph.persistence` still exists) | `pydantic_graph` has **no persistence module at all** in this commit — `grep -rn persistence pydantic_graph/` returns nothing. The old `FileStatePersistence`/`FullStatePersistence` API is gone. | The negative finding is *stronger*, not weaker. Nothing in pydantic-ai's dependency tree persists a run. |
| X3 | "LangGraph/LangChain has no runtime capability metadata; profiles are in a separate package" | `langchain_core.language_models.model_profile.ModelProfile` is **in core** (`model_profile.py:13`), surfaced as `BaseChatModel.profile` (`chat_models.py:366`), resolved by `_resolve_model_profile` (`:386`), and **vendored offline** into each partner package (`libs/partners/*/data/_profiles.py`, ~12.1k lines total, sourced from models.dev) | LangChain has a *better capability catalogue* than pydantic-ai; pydantic-ai has a *better protocol-adaptation profile*. They are complementary, and PACT needs both axes (see §F.14). |
| X4 | "Durable-exec wraps `Agent`, not `Model`" | Every durable backend ships a `WrapperModel` subclass: `TemporalModel` (`durable_exec/temporal/_model.py:54`), `PrefectModel` (`prefect/_model.py:38`), `DBOSModel` (`dbos/_model.py:22`). `TemporalModel.__init__` accepts `agent: AbstractAgent \| None = None` (`:66`) — constructible **without** an Agent. | pydantic-ai durability *is* reachable in harness mode, but only through a private module (`_model` is not in `durable_exec/temporal/__init__.py:32-41`). Flag as unsupported-API risk, not as impossible. |
| X5 | "LangGraph fabricates `'Sorry, need more steps…'` on budget exhaustion" | That fabrication exists **only** in the deprecated `langgraph.prebuilt.chat_agent_executor` (`:620`, `:684-692`, `:711-716`). `langchain.agents.create_agent` has no such path — `grep -rn "need more steps" libs/langchain_v1/` is empty; the modern path raises `GraphRecursionError` (`pregel/main.py:3011`, `errors.py:67`). | The honesty hazard is real but confined to the deprecated target PACT must not use anyway (§E6). Keep the `on_budget_exhausted` field (§F.8) — but the justification is now "importers may encounter it", not "the live target does it". |

---

# PART A — PYDANTIC AI

## A(a) The agent loop: exact control flow of one run

### A(a).1 The engine underneath: `pydantic_graph` is now a parallel-control-flow graph **[V]**

This is the single biggest change since revision 1 and it must be read first, because it
changes what "the agent loop" *is*.

`pydantic_graph` exports (`pydantic_graph/__init__.py:11-36`):

```
BaseNode, End, GraphRunContext, Edge
GraphBuilder, Graph, GraphRun, GraphTask, GraphTaskRequest, EndMarker, ErrorMarker, JoinItem
Step, StepContext, StepNode, StartNode, EndNode, Fork, Decision
Join, JoinNode, ReducerContext, ReducerFunction, ReduceFirstValue,
reduce_dict_update, reduce_list_append, reduce_list_extend, reduce_null, reduce_sum
```

Key facts:

- **`Fork`** (`node.py:60-77`) has `is_map: bool` — *"If True, `InputT` must be
  `Sequence[OutputT]` and each element is sent to a separate branch. If False, the same
  data is sent to all branches."* Plus `downstream_join_id` for the empty-iterable case.
  **This is map-reduce and broadcast, natively.**
- **`Join`** (`graph_builder.py:1366-1405`) takes a `reducer` plus `initial` or
  `initial_factory`, and `preferred_parent_fork: 'farthest' | 'closest'`. Built-in
  reducers cover append/extend/dict-update/sum/first-value. `ReduceFirstValue` +
  `_cancel_sibling_tasks` (`graph_builder.py:1096`) is a **race/first-wins** primitive.
- **`Decision`** (`decision.py:41-46`) — *"evaluates conditions and routes execution to
  different branches based on the input data type or custom matching logic."* Builder
  helpers `decision()`, `match()`, `match_node()` (`graph_builder.py:1531`, `:1543`, `:1565`).
- **Execution is superstep-shaped.** `GraphRun.__anext__` returns
  `EndMarker[OutputT] | Sequence[GraphTask]` (`graph_builder.py:544-562`) — a *sequence*
  of tasks per step, i.e. a fan-out set, exactly like a Pregel superstep.
- **The run is externally drivable and overridable.** `GraphRun.next(value=...)`
  (`graph_builder.py:564-583`) sends a value into the generator; `GraphRun.override_next(value)`
  (`:586-598`) *"allows the graph to continue after an `End` or error"* and accepts either
  new `GraphTaskRequest`s or an `EndMarker`. `Graph.iter(...)` (`:313-361`) is the public
  step-by-step entry point.
- **There is no persistence.** No `persistence` module, no `snapshot`, no checkpoint —
  verified by exhaustive grep over `pydantic_graph/`.

> **Design consequence.** PACT's topology IR (`Fork`/`Join`/`Decision`/`Step`) has an
> almost 1:1 native target in `pydantic_graph`, published as its own distribution
> (`pydantic-graph`, `pydantic_graph/pyproject.toml:14`). That is a *better* native
> lowering target for topology than `Agent` is, and it is independent of the Agent class.
> **[I]** PACT should treat `pydantic-graph` and `pydantic-ai` as two separate lowering
> surfaces in the same adapter.

### A(a).2 The agent graph itself **[V]**

`build_agent_graph` — `_agent_graph.py:2281-2310`. Four registered node types plus the
start edge:

```
START → UserPromptNode → ModelRequestNode ⇄ CallToolsNode → End(FinalResult)
                                                 │
                              SetFinalResult ────┘   (streaming-only immediate end)
```

`g.build(validate_graph_structure=False)` at `:2310` — the agent graph deliberately opts
out of the builder's structural validation.

Node classes: `UserPromptNode` `:453`, `ModelRequestNode` `:1011`, `CallToolsNode` `:1673`,
`SetFinalResult` `:2088`. All subclass `AgentNode` `:429`.

### A(a).3 Step-by-step, one run **[V]/[V1]**

1. **`UserPromptNode.run`** (`:453`+). Copies history through `_clean_message_history`
   (`:2676`), which composes `_drop_orphaned_tool_results` (`:2484`),
   `_repair_dangling_tool_calls` (`:2529`) and `_merge_consecutive_messages` (`:2614`).
   Routing decisions, in order: deferred results present → jump straight to
   `CallToolsNode`; last message is a `ModelRequest` and no new prompt → pop and re-send;
   last message is a suspended `ModelResponse` → `ModelRequestNode(_resume_suspended=...)`;
   last message has pending tool calls and no new prompt → `CallToolsNode`; else build a
   fresh `ModelRequest`. A new user prompt on top of unprocessed tool calls, or on a
   suspended response, raises `UserError`. **[V1]**
   Note `:557` — this path calls `for_run_step(run_step=ctx.state.run_step + 1)` itself. **[V]**

2. **`ModelRequestNode._prepare_request`** — the step boundary. `ctx.state.run_step += 1`
   at **`_agent_graph.py:1358`** **[V]** is the canonical step counter.
   `tool_manager.for_run_step(run_context)` at `:1376`, with an in-source note that it is
   *"a no-op for the same step"* if `UserPromptNode` already called it (`:1374-1375`). **[V]**
   Then `_get_instructions` (`:695`), `_prepare_request_parameters` (`:716`),
   the `before_model_request` capability hook, and `usage_limits.check_before_request`.

3. **`ModelRequestNode._make_request`** — wraps the call in
   `root_capability.wrap_model_request(...)`; a `ModelRetry` from any hook becomes a new
   `ModelRequestNode` carrying a `RetryPromptPart`. Returns `CallToolsNode(response)`. **[V1]**

4. **`CallToolsNode._run_stream`** (`:1673`+) — decision order inside one response:
   suspended → `UserError`; empty/thinking-only with `finish_reason=='length'` →
   `UnexpectedModelBehavior`; `content_filter` → `ContentFilterError`; `allows_none` → valid
   final result; else synthesise a `RetryPromptPart`. Then partition parts into
   text / tool_calls / files, ignoring `ThinkingPart`. **Tool calls beat text by default**;
   under `end_strategy='early'` a *schema-validated* text or image output pre-empts plain
   function tool calls. **[V1]**

5. **Termination** is `End(FinalResult)` from `_handle_final_result`, which appends a
   trailing `ModelRequest` carrying the tool returns so the history stays re-usable. **[V1]**

### A(a).4 Termination conditions, enumerated

| Condition | Source | Status |
|---|---|---|
| Output tool call succeeds | `_tool_execution.py` → `output_final_result` | [V1] |
| Text validates against the output schema | `_agent_graph.py` `CallToolsNode` | [V1] |
| Image output validates | same | [V1] |
| Empty/thinking-only response and `output_schema.allows_none` | same | [V1] |
| Unresolved deferred calls + `DeferredToolRequests` in the output type | `_deferred.py:27-41`, `_output.py` | [V] |
| `UsageLimits.request_limit` exceeded (**default 50**) | `usage.py:302`, raise at `:341-343` | **[V]** |
| `tool_calls_limit` / `input_tokens_limit` / `output_tokens_limit` / `total_tokens_limit` | `usage.py:304-310`, checks `:346-372` | **[V]** |
| `max_output_retries` exceeded → `UnexpectedModelBehavior` | `_agent_graph.py:353` `consume_output_retry` | **[V]** |
| Per-tool `max_retries` exceeded → `UnexpectedModelBehavior` | `tool_manager.py:185-195` (`_check_max_retries`) | **[V]** |

> **There is no "max steps" concept.** The only step-count bound is
> `UsageLimits.request_limit`, default **50** (`usage.py:302`), and every token limit is
> `None` by default (`usage.py:306-310`). **[V]**

## A(b) State model

`GraphAgentState` — `_agent_graph.py:291-330`. **[V]** Fields, verified verbatim:

| Field | Line | Note |
|---|---|---|
| `message_history: list[ModelMessage]` | `:294` | **the real state** |
| `usage: RunUsage` | `:295` | |
| `output_retries_used: int` | `:296` | |
| `run_step: int` | `:297` | |
| `run_id: str` (uuid7) | `:298` | *"Unlike `conversation_id`, this is never inherited from `message_history`"* (`:300-302`) |
| `conversation_id: str` (uuid7) | `:304` | *"Resolved from the `conversation_id` argument …, the most recent `conversation_id` on `message_history`, or a freshly generated UUID7"* (`:305-308`) |
| `metadata: dict \| None` | `:311` | |
| `last_max_tokens` | `:312` | error messages only |
| `last_model_request_parameters` | `:314` | OTel span attributes only |
| `pending_messages` | `:317` | `enqueue()` queue |
| `event_stream_buffer` | `:319` | *"shared by reference into every `RunContext`"* |
| `mcp_tool_defs_cache` | `:327` | per-run, for durable replay |

**The state is the message list.** There is no arbitrary key/value state. Application state
travels in `deps`, which is neither persisted nor serialised.

- **Serialisation:** `ModelMessagesTypeAdapter.dump_json` — `run.py:170` (`AgentRun.all_messages_json`),
  `:185` (`new_messages_json`), `:540` (`AgentRunResult.all_messages_json`). **[V]**
- **Checkpointing:** none, anywhere in the dependency tree. `pydantic_graph` has no
  persistence module (§0.1 X2). Durability is opt-in and lives in
  `pydantic_ai/durable_exec/{temporal,dbos,prefect}` (§A(i).3).
- **Resume:** three mechanisms, all *history-shaped*: `message_history=` +
  `deferred_tool_results=`; history ending in a `ModelRequest` with no prompt; history
  ending in a suspended `ModelResponse`. **[V1]**
- **Addressability:** **partial.** Messages carry `run_id` / `conversation_id` /
  `tool_call_id`. `AgentRun.ctx` (`run.py:117-122`) exposes the live `GraphRunContext`;
  `AgentRun.next(node)` (`run.py:328-403`) lets a caller drive node-by-node; the underlying
  `GraphRun.override_next` (`graph_builder.py:586`) can redirect after an `End` or error.
  But nodes are in-memory Python dataclasses. There is no checkpoint id, no
  `get_state_history`, no `update_state(as_node=)`.

> **Negative finding, hardened:** pydantic-ai cannot express "resume at step N after
> process death" at all. Core resume is **conversation resume**, not **execution resume**.
> The only route to execution resume is to place the whole run inside Temporal/DBOS/Prefect.
> **[V]**

## A(c) Tool protocol

### Declaration & schema derivation **[V]**

`ToolDefinition` (`tools.py:544`+) — the wire object. Fields at the offsets listed
(offsets relative to `:544`): `name` (+7), `parameters_json_schema` (+10),
`description` (+13), `outer_typed_dict_key` (+16), `strict` (+22), `sequential` (+34),
`kind` (+44), `metadata` (+55), `timeout` (+61), `defer_loading` (+68), `unless_native` (+91),
`with_native` (+106).

**Schema-first declaration exists and is the adapter's hook:**
`Tool.from_schema(function, name, description, json_schema, takes_ctx, sequential, args_validator)`
(`tools.py:438-493`) installs `SchemaValidator(any_schema())` so validation is skipped and
the JSON Schema is purely the wire contract. **[V1]** This is how a PACT adapter registers a
YAML-declared tool.

Toolsets are the composition unit: `AbstractToolset` (`toolsets/abstract.py:76`) with
`get_tools(ctx)` and `call_tool(name, args, ctx, tool)`; combinators `.filtered()`,
`.prefixed()`, `.prepared()`, `.renamed()`, `.approval_required()`, `.defer_loading()`,
`.include_return_schemas()`. **[V1]**

### Parallel calls, barriers, ordering **[V]**

`_segment_by_barriers(indices, is_barrier)` — **`_tool_execution.py:89-108`**, docstring
verbatim: *"Each barrier index becomes a single-element segment; consecutive non-barrier
indices form a parallel segment. Segments run in order, so a barrier completes before later
tools start and starts only after earlier tools finish."*

A tool with `ToolDefinition.sequential=True` is a barrier. Run-scoped mode selector:
`ToolManager.parallel_execution_mode(mode='parallel')` classmethod contextmanager —
**`tool_manager.py:102`** **[V]**, with modes `parallel` (completion-order events),
`parallel_ordered_events` (emission-order events), `sequential` (every call its own
barrier). **Result ordering is always emission order regardless of event order.** **[V1]**

### `end_strategy` — three loop semantics wearing one flag **[V]**

`process_tool_calls` docstring, **`_tool_execution.py:122-153`**, verbatim:

- **`'early'`** — *"output tools run sequentially in emission order and stop at the first
  success; function tools run **only if every output tool failed** … Once an output
  succeeds, all function tools are stubbed as not executed."*
- **`'graceful'` (default)** — *"tools run in the order the model emitted them — function
  tools that precede an output tool complete before it runs. Output tools run sequentially
  and stop at the first success; subsequent output tools are skipped (their side effects
  don't run)."*
- **`'exhaustive'`** — *"every tool runs in parallel; the first valid output by emission
  order becomes the final result while the rest still execute."*
- **Retry-wins invariant** — *"Under `'graceful'`/`'exhaustive'` … if any function/unknown
  tool produces a `RetryPromptPart`, `final_result` is suppressed so the model addresses
  the retries on the next round. Output-tool retries don't trigger this … Retry-wins
  doesn't apply when `final_result` was passed in by `Agent.run_stream` … or under `'early'`."*
- Dispatch: `_ExhaustiveProcessor` / `_EarlyProcessor` / `_GracefulProcessor` at `:156-165`.

**This is a 3 × 2 behavioural space that changes which tools actually execute.** It is not
cosmetic; ignoring it makes an import lossy in a way that changes side effects.

### Errors & retries **[V]**

- Retry budget is **per tool name**, on `RunContext.retries`; `_check_max_retries`
  (`tool_manager.py:185-195`) raises `UnexpectedModelBehavior` at
  `retries.get(name,0) >= max_retries`.
- **`ToolManager.default_max_retries: int = 1`** (`tool_manager.py:97`) — the default
  per-tool budget is **one** retry. **[V]**
- **The count resets on success**: `for_run_step` (`:117-143`) drops names in
  `succeeded_tools` (`:126`) and increments names in `failed_tools` (`:131`). `failed_tools`
  is written at `:373` and `:436`. **[V]**
- A separate **output** budget (`max_output_retries`) is consumed by
  `consume_output_retry` (`_agent_graph.py:353`). **[V]**
- Semantics: `ModelRetry` in a tool → `RetryPromptPart` back to the model;
  `ToolFailed` → `ToolReturnPart(outcome='failed')`, terminal, no retry. **[V1]**

### Approval **[V1]**

`AbstractToolset.approval_required(predicate)` → `ApprovalRequiredToolset`. At execution
time `exceptions.ApprovalRequired` is collected as `deferred_calls['unapproved']` and
`exceptions.CallDeferred` as `deferred_calls['external']`.

## A(d) Structured output

`OutputSchema.build` — **`_output.py:458`** **[V]** resolves `output_type` into one of six
classes: `AutoOutputSchema` `:632`, `TextOutputSchema` `:662`, `ImageOutputSchema` `:683`,
`StructuredTextOutputSchema` `:693` (abstract), `NativeOutputSchema` `:731`,
`PromptedOutputSchema` `:738`, `ToolOutputSchema` `:745`. **[V]**

Output modes: `auto | text | image | native | prompted | tool`.

- **`tool`** — schema exposed as an output tool; the model "submits" by calling it.
- **`native`** — provider-native structured output.
- **`prompted`** — JSON Schema injected into instructions via
  `StructuredTextOutputSchema.build_instructions` (`_output.py:717`). **[V]**
- **`auto`** — resolved at request time by `ModelRequestParameters.with_default_output_mode`
  (`models/__init__.py:175-184`), which the model's profile drives. Note the in-source
  invariant: *"`output_mode='tool'` implies `allow_text_output=False`, while `'native'` and
  `'prompted'` imply `allow_text_output=True`"* — **the two fields are updated atomically**
  (`:175-183`). **[V]**

**Enforcement is validate-then-retry, not constrained decoding.** A `ValidationError` or
`ModelRetry` becomes a `ToolRetryError` carrying a `RetryPromptPart`, consuming the output
retry budget. `ToolDefinition.strict` is a *vendor* flag passed through; **PACT cannot
assume grammar-constrained decoding from pydantic-ai.** **[V1]**

This matters for the thesis: §7.3's "constrained decoding, +34.4 pp" mechanism is
**substrate-bound and not reachable through this framework's abstraction**. PACT must model
it as a model/provider capability, never as an agent-level guarantee.

## A(e) Streaming: event types and ordering **[V]**

Types (`messages.py`): `PartStartEvent` `:3313`, `PartDeltaEvent` `:3342`,
`PartEndEvent` `:3358`, `FinalResultEvent` `:3383`, union `ModelResponseStreamEvent` `:3396`;
`FunctionToolCallEvent` `:3455`, `FunctionToolResultEvent` `:3490`,
`DeferredToolRequestsEvent` `:3520`, union `HandleResponseEvent` `:3569`; top union
`AgentStreamEvent` `:3580`.

**Ordering guarantees, verified in `models/__init__.py:791-890`:**

1. `StreamedResponse.__aiter__` (`:791`) composes three generators:
   `iterator_with_part_end(iterator_with_final_event(self._get_event_iterator()))`
   plus a cancel guard (`:886`). **[V]**
2. `iterator_with_final_event` (`:801-815`): on the first event that matches the output
   schema it yields the event, **then** yields `FinalResultEvent`, **then `break`s** and
   re-drains the remainder (`:812-815`). **So `FinalResultEvent` is not last — it is emitted
   at the point of match.** **[V]**
3. `iterator_with_part_end` (`:817-852`): `PartEndEvent` is synthesised only when the part
   `isinstance(part, TextPart | ThinkingPart | BaseToolCallPart)` — *"Parts other than these
   3 don't have deltas, so don't need an end part"* (`:827-830`). **[V]**
4. Adjacency: `PartEndEvent.next_part_kind` is set from the following `PartStartEvent`
   (`:838-842`), and `PartStartEvent.previous_part_kind` from the preceding one (`:854-857`
   region). **No other framework in this corpus hands the UI part adjacency.** **[V]**
5. `_get_final_result_event` at `:1620-1632` is the matcher. **[V]**
6. Parts stream as their **typed subclasses from the first `PartStartEvent`**, because
   `ModelResponsePartsManager` receives `model_request_parameters` and promotes via
   `ToolDefinition.tool_kind` (`:783-789`). **[V]**

`Agent.run_stream_events()` — **`agent/abstract.py:1167`** **[V]** flattens all of this into
one `AsyncIterator[AgentStreamEvent | AgentRunResultEvent]`.

> **This is the richest event model in the corpus and should be the template for PACT's own
> canonical stream** (see §F.9).

## A(f) HITL / interrupt semantics

Pydantic AI has **no interrupt**. It has **deferred tools**, which is strictly cleaner for a
portable spec. **[V]**

- `DeferredToolRequests` — `_deferred.py:27`, fields `calls: list[ToolCallPart]` (`:37`),
  `approvals: list[ToolCallPart]` (`:39`), `metadata: dict[str, dict]` (`:41`). **[V]**
- `DeferredToolResults` — `_deferred.py:155`, fields `calls: dict[str, DeferredToolCallResult|Any]`
  (`:163`), `approvals: dict[str, bool | DeferredToolApprovalResult]` (`:165`),
  `metadata` (`:169`). **[V]**
- `ToolApproved` — `_deferred.py:100`, **with `override_args: dict[str,Any] | None` at `:103`**:
  a human can *edit the arguments* before execution. `ToolDenied(message=...)` at `:110-113`. **[V]**
- A run whose output type includes `DeferredToolRequests` **ends normally** with that payload.
- Resume: `agent.run(message_history=..., deferred_tool_results=...)` →
  `UserPromptNode` jumps straight to `CallToolsNode` with already-executed calls marked
  `'skip'`. **[V1]**
- **Nothing re-executes.** This is *exactly-once* semantics for tool side effects across an
  approval boundary.

> **This is the single most important semantic asymmetry in the audit.** See §C6 and §E1.

## A(g) Memory & context management

There is **no memory subsystem**. Context management is a function over the message list:
`HistoryProcessor = (messages) -> messages | (ctx, messages) -> messages`, installed as the
`ProcessHistory` capability. The processed history must be non-empty and must still end in a
`ModelRequest`. Provider-side compaction exists as `Model.compact_messages`
(`NotImplementedError` by default). Long-term memory is absent; mem0/letta/zep would be
plain toolsets. **[V1]**

Tool-context discipline **is** first class: `ToolDefinition.defer_loading` +
the `ToolSearch` capability + `_tool_search.py` implement hierarchical tool discovery —
the exact mechanism `SYNTHESIS.md`'s hierarchical-routing finding calls for. **[V1]**

## A(h) Multi-agent

**At the `Agent` level there is no multi-agent construct.** The documented levels are:
single agent; **delegation** (call `other_agent.run(..., usage=ctx.usage)` inside a
`@agent.tool`); **programmatic hand-off**; `pydantic_graph` for control flow; "deep agents"
as a recipe. What crosses a delegation boundary is the **prompt string** and the **usage
object** (by reference, so `RunUsage` accumulates). **Message history does not cross.** **[V1]**

**But** — §A(a).1 — `pydantic_graph` *is* the multi-agent substrate, and it is real:
`Fork(is_map=True)` gives map-reduce/fan-out; `Join(reduce_list_append, initial=[])` gives
gather; `Join(ReduceFirstValue, ...)` + `_cancel_sibling_tasks` gives race/first-wins;
`Decision` + `match()` gives supervisor routing. **[V]**

> **Corrected finding:** PACT's topology IR maps onto `pydantic_graph`, not onto `Agent`.
> Supervisor / pipeline / map-reduce / race are all expressible; **blackboard and
> market/auction are not**, because there is no shared mutable channel space — the only
> cross-branch data flow is through a `Join` reducer. Those two of AC-5.1's eight patterns
> are `emulated` on this adapter. **[I]**

## A(i) Model abstraction

### A(i).1 The ABC **[V1]/[V]**

`Model(ABC)` — `models/__init__.py:261`+. `StreamedResponse(ABC)` at `:760`.

| Member | Line | Required? |
|---|---|---|
| `request(messages, model_settings, model_request_parameters) -> ModelResponse` | `:309` | **abstract** |
| `request_stream(...) -> AsyncGen[StreamedResponse]` | `:346` | optional |
| `count_tokens(...)` | `:322` | optional |
| `compact_messages(...)` | `:332` | optional |
| `cancel_suspended_response`, `continuation_delay` | `:361-376` | optional |
| `customize_request_parameters` | `:378` | applies `profile['json_schema_transformer']` |
| `prepare_request` | `:399` | merges settings, resolves `auto` output mode, resolves `thinking` |
| `model_name`, `system`, `profile` | `:605`, `:697`, `:656` | abstract / property |

### A(i).2 `ModelRequestParameters` — the wire contract **[V]**

`models/__init__.py:133-186`. Verified fields:

```
function_tools: list[ToolDefinition]          :136
native_tools:   list[AbstractNativeTool]      :137
output_mode:    OutputMode = 'text'           :139
output_object:  OutputObjectDefinition|None   :140
output_tools:   list[ToolDefinition]          :141
prompted_output_template: str|Literal[False]|None  :142
allow_text_output:  bool = True               :143
allow_image_output: bool = False              :144
instruction_parts:  list[InstructionPart]|None :146   (static vs dynamic; drives cache boundaries)
thinking:           ThinkingLevel|None        :158
```

plus `tool_defs` (`:166`), `prompted_output_instructions` (`:170`),
`with_default_output_mode` (`:175`).

**This one object carries everything PACT needs to control the wire.** It is the closest
existing thing to PACT's request IR. Copy it (§F.2).

### A(i).3 Capabilities are declared by `ModelProfile` — protocol-shaped, not capability-shaped **[V]**

`pydantic_ai/profiles/__init__.py`, per-vendor modules for amazon, anthropic, cohere,
deepseek, google, grok, groq, harmony, meta, mistral, moonshotai, openai, qwen, zai.
Fields (line numbers in `profiles/__init__.py`):

```
supports_tools                                   :48
supports_tool_return_schema                      :51
supports_json_schema_output                      :58
supports_json_object_output                      :65
supports_image_output                            :72
supports_inline_system_prompts                   :75
default_structured_output_mode                   :83
prompted_output_template                         :86
native_output_requires_schema_in_instructions    :89
json_schema_transformer                          :92
supports_thinking                                :95
thinking_always_enabled                          :101
thinking_tags                                    :108
ignore_streamed_leading_whitespace               :111
supported_native_tools                           :120
```

`infer_model_profile(model: str) -> ModelProfile` — **`models/__init__.py:1247`** **[V]**
resolves a profile **without constructing a provider**: a genuinely offline lookup.
`infer_model(...)` at `:1280`. **[V]**

> **Critical observation.** This profile answers *"how do I talk to this model"* — schema
> transformer, default output mode, thinking tags, inline system prompts. It does **not**
> answer *"what can this model do"* — no context window, no modality flags, no benchmark
> scores. That axis lives in LangChain (§B(i).2). **PACT needs both and they are disjoint.**

### A(i).4 Durability wrappers are `Model` wrappers **[V]** (corrects revision 1)

- `TemporalModel(WrapperModel)` — `durable_exec/temporal/_model.py:54`. Constructor `:55-67`
  takes `model, activity_name_prefix, activity_config, deps_type, run_context_type,
  event_stream_handler, models, provider_factory, agent=None`. It builds three Temporal
  activities: `{prefix}__model_request` (`:92-108`), `{prefix}__model_request_stream`
  (`:110-134`), `{prefix}__model_cancel_suspended_response` (`:140-148`), exposed via
  `temporal_activities` (`:150-152`).
- `PrefectModel(WrapperModel)` — `durable_exec/prefect/_model.py:38`.
- `DBOSModel(WrapperModel)` — `durable_exec/dbos/_model.py:22`.
- **None of these are exported.** `durable_exec/temporal/__init__.py:32-41` exports
  `TemporalAgent, TemporalDurability, PydanticAIPlugin, LogfirePlugin, AgentPlugin,
  TemporalRunContext, TemporalWrapperToolset, PydanticAIWorkflow` — **not `TemporalModel`**.

> A PACT harness *can* run its own loop inside a Temporal workflow and use `TemporalModel`
> as the model transport, giving pydantic-ai kill-and-resume. But it depends on a private
> module, so this is an **unsupported-API risk**, not a supported path. Record it in the
> lattice as `emulated (private API)` rather than `native`. **[V]/[I]**

## A(j) `AgentSpec` — pydantic-ai already ships a YAML agent spec **[V1]**

`pydantic_ai/agent/spec.py` (376 lines) defines `AgentSpec(BaseModel)` with `$schema`,
`model`, `name`, `description`, `instructions`, `deps_schema`, `output_schema`,
`model_settings`, `retries`, `end_strategy`, `tool_timeout`, `metadata`,
`capabilities: list[CapabilitySpec]`. Loaders `from_file` / `from_text` / `from_dict`;
writer `to_file` emits a sibling JSON Schema and a `# yaml-language-server: $schema=` header.
`Agent.from_spec` and `Agent.iter(spec=...)` consume it. Documented audience
(`docs/agent-spec.md:3-9`): *"Letting non-developers (prompt engineers, domain experts)
configure agents."* — **the same audience as PACT's D13, from PACT's highest-priority target
framework.**

Serialisable capability registry `CAPABILITY_TYPES` (`capabilities/__init__.py:72-94`):
`NativeTool, RaiseContentFilterError, ImageGeneration, IncludeToolReturnSchemas,
Instrumentation, MCP, PrefixTools, PrepareTools, ProcessHistory, ReinjectSystemPrompt,
SetToolMetadata, Thinking, ToolSearch, Toolset, WebFetch, WebSearch, XSearch`.
MCP servers are declarable in YAML: `MCP.from_spec(url, native, local, id,
authorization_token, headers, allowed_tools, description, defer_loading)`.

**What it cannot express** (and therefore where PACT's win must come from): no `tools:`
field, no evals, no SLOs, no capability *requirements*, no variants, no topology, no
learning, no directory expansion; `ProcessHistory` is explicitly **not** spec-serialisable
(`capabilities/process_history.py:41-42`, `get_serialization_name -> None`).

## A(k) The capability hook surface **[V]**

`capabilities/abstract.py` declares **28 named lifecycle hooks** across 7 phases
(`before_/after_/wrap_/on_*_error` for run, node_run, model_request, tool_validate,
tool_execute, output_validate, output_process), plus `wrap_run_event_stream`:

```
before_run :459   after_run :465   wrap_run :474   on_run_error :495
before_node_run :519  after_node_run :528  wrap_node_run :538  on_node_run_error :569
wrap_run_event_stream :592
before_model_request :610  after_model_request :618  wrap_model_request :633  on_model_request_error :648
before_tool_validate :673  after_tool_validate :688  wrap_tool_validate :703  on_tool_validate_error :715
before_tool_execute :740   after_tool_execute :755   wrap_tool_execute :771   on_tool_execute_error :783
before_output_validate :817 after_output_validate :842 wrap_output_validate :866 on_output_validate_error :882
before_output_process :902  after_output_process :921  wrap_output_process :935  on_output_process_error :954
```

This is a *better-factored* hook model than LangChain's middleware (which has 8 hooks,
§B(a).3). PACT's own hook IR should follow this shape — the `before/after/wrap/on_error`
quadruple per phase — because it is the only one that lets a hook both observe and replace.

---

# PART B — LANGGRAPH

## B(0) Where the agent actually lives now **[V1]**

`langgraph.prebuilt.create_react_agent` is **deprecated** —
`libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py:274-276` carries
`@deprecated(..., category=LangGraphDeprecatedSinceV10)`, docstring at `:311-318` redirects
to `create_agent` from the `langchain` package. `AgentState`, `AgentStatePydantic`,
`AgentStateWithStructuredResponse` are deprecated too.

**Consequence for PACT:** native lowering targets `langchain.agents.create_agent`
(`libs/langchain_v1/langchain/agents/factory.py:740-808`, four overloads); harness lowering
targets `langgraph.func.entrypoint`/`task` or a hand-built `StateGraph`. Targeting
`langgraph.prebuilt` would be adapter rot on day one.

## B(a) The agent loop

### B(a).1 The engine: Pregel BSP supersteps **[V]**

`PregelLoop.tick()` — `libs/langgraph/langgraph/pregel/_loop.py:599-681`. One superstep,
verified in order:

1. `if self.step > self.stop: self.status = "out_of_steps"; return False` (`:607-609`).
2. `prepare_next_tasks(checkpoint, pending_writes, nodes, channels, managed, config, step,
   stop, for_execution=True, ...)` (`:612-631`).
3. Emit `checkpoints` debug output (`:634-650`).
4. `if not self.tasks: self.status = "done"; return False` (`:653-655`).
5. Drain requested → `self.status = "draining"; return False` (`:657-659`).
6. Replay: `if not self.is_replaying and self.checkpoint_pending_writes:` →
   `_reapply_writes_to_succeeded_nodes(self.tasks)` and `_resume_error_handlers_if_applicable()`
   (`:661-664`).
7. `interrupt_before` → `self.status = "interrupt_before"; raise GraphInterrupt()` (`:666-671`).
8. Emit `tasks`; replay cached writes (`:673-680`).

`after_tick()` — `:683-726`:
9. `apply_writes(...)` — **channel updates become visible only here** (`:686-698`).
10. Emit `values` if the output keys changed (`:700-709`).
11. `self.is_replaying = False` (`:716`) — *"only replay (re-execute) done tasks on the first tick"*.
12. `self._put_checkpoint({"source": "loop"})` (`:718`).
13. `interrupt_after` → `raise GraphInterrupt()` (`:720-724`).

The driver loop is `Pregel.stream` — `pregel/main.py:2964-2986`, with the invariant stated
verbatim at `:2959-2963`: *"Channel updates from step N are only visible in step N+1;
channels are guaranteed to be immutable for the duration of the step, with channel updates
applied only at the transition between steps."*

```python
while loop.tick():
    for task in loop.match_cached_writes(): loop.output_writes(task.id, task.writes, cached=True)
    for _ in runner.tick([t for t in loop.tasks.values() if not t.writes],
                         timeout=self.step_timeout, get_waiter=get_waiter,
                         schedule_task=loop.accept_push):
        yield from _output(...)
    loop.after_tick()
    emit_graph_lifecycle_events(loop)
    if durability_ == "sync": loop._put_checkpoint_fut.result()
```

Exhaustion is **honest**: `if loop.status == "out_of_steps": raise GraphRecursionError(msg)`
(`main.py:3001-3011`; async twin at `:3492`). `GraphRecursionError(RecursionError)` at
`errors.py:67`. **[V]**

`self.stop = self.step + config["recursion_limit"] + 1`; `DEFAULT_RECURSION_LIMIT = 25`
(`langchain/libs/core/langchain_core/runnables/config.py:171`). **[V1]**

### B(a).2 The agent graph on top (`langchain.agents.create_agent`) **[V]**

`factory.py`. Nodes: `model`, `tools`, plus one node **per middleware hook** —
`{m.name}.before_agent`, `.before_model`, `.after_model`, `.after_agent`. Edges wired with
`add_conditional_edges`; helpers `_make_model_to_tools_edge` `:1840`,
`_make_model_to_model_edge` `:1894`, `_make_tools_to_model_edge` `:1921`,
`_add_middleware_edge` `:1957`, `_resolve_jump` `:1804`.

The model node: `model_node(state, runtime)` `:1433`, which builds a `ModelRequest{model,
tools, system_message, response_format, messages, tool_choice, state, runtime}`
(`middleware/types.py:86`) and calls the composed `wrap_model_call` handler.
`_execute_model_sync(request)` `:1406` does `_get_bound_model(request)` `:1272` →
`model_.invoke(messages)` → `_handle_model_output(...)` `:1168`. It returns `list[Command]`
via `_build_commands` `:193`.

### B(a).3 Middleware: the native extension point **[V]**

`AgentMiddleware` — `middleware/types.py:383`. **Eight hooks** (each with an `a`-prefixed
async twin):

```
before_agent :419 / abefore_agent :430
before_model :443 / abefore_model :454
after_model  :467 / aafter_model  :478
wrap_model_call :491 / awrap_model_call :586
after_agent :638 / aafter_agent :649
wrap_tool_call :662 / awrap_tool_call :744
```

plus `JumpTo = Literal["tools","model","end"]` (`:66`) and
`jump_to: NotRequired[Annotated[JumpTo|None, EphemeralValue, PrivateStateAttr]]` (`:351`).
`can_jump_to` is declared per-hook (`:869`, `:933`, …) so the factory can wire the
conditional edges statically.

21 middleware modules ship in-box: `context_editing, file_search, human_in_the_loop,
model_call_limit, model_fallback, model_retry, pii, provider_tool_search, shell_tool,
summarization, todo, tool_call_limit, tool_emulator, tool_error, tool_retry, tool_selection`
plus internals `_execution, _redaction, _retry, types`.

> **This is the LangChain-side answer to pydantic-ai's capability hooks, and it is weaker:
> 8 hooks vs 28, no `on_*_error` phase, and no wrap around output validation.** But it has
> something pydantic-ai lacks: `JumpTo` — a hook can *redirect the graph*.

## B(b) State model **[V]/[V1]**

**The state is a set of typed, reducer-merged channels.** `Checkpoint` TypedDict
(`libs/checkpoint/langgraph/checkpoint/base/__init__.py:92-123`): `v, id, ts,
channel_values, channel_versions, versions_seen, updated_channels`.
`CheckpointMetadata` (`:38-86`): `source ∈ {input, loop, update, fork}`, `step`,
`parents: dict[ns, checkpoint_id]`, `run_id`, `counters_since_delta_snapshot`.

Channels (`libs/langgraph/langgraph/channels/`), semantics read from source **[V]**:

| Channel | Class:line | Semantics (verbatim docstring) |
|---|---|---|
| `LastValue` | `last_value.py:20` | *"Stores the last value received, can receive at most one value per step."* |
| `LastValueAfterFinish` | `last_value.py:81` | *"…only made available after finish()."* |
| `BinaryOperatorAggregate` | `binop.py:65` | *"Stores the result of applying a binary operator to the current value and each new value."* — the user-supplied reducer channel |
| `Topic` | `topic.py:23` | *"A configurable PubSub Topic"* — accumulating list |
| `EphemeralValue` | `ephemeral_value.py:15` | *"Stores the value received in the step immediately preceding, clears after."* |
| `NamedBarrierValue` | `named_barrier_value.py:13` | *"waits until all named values are received before making the value available"* |
| `NamedBarrierValueAfterFinish` | `named_barrier_value.py:84` | same + finish gate |
| `UntrackedValue` | `untracked_value.py:15` | *"Stores the last value received, **never checkpointed**"* |
| `AnyValue` | `any_value.py:15` | *"assumes that if multiple values are received, they are all equal"* |
| `DeltaChannel` | `delta.py:25` (beta) | *"Reducer channel that stores only a sentinel in checkpoint blobs"* |

`binop.py` also carries `_get_overwrite(value)` (`:32`) and `_reducers_equal` (`:55`) —
i.e. a write can carry an **overwrite marker** that bypasses the reducer. **[V]**

**Durability** — `Durability = Literal["sync","async","exit"]` (`types.py:87`).
`sync` persists before the next step starts; `async` (default) persists while the next step
runs; `exit` persists only on exit. **[V1]**

**Resume** — three addressable mechanisms: `invoke(None, config)` with a `thread_id`;
`Command(resume=...)` (`types.py:759`); **time travel** via an explicit `checkpoint_id`,
which drops cached `RESUME` writes so `interrupt()` re-fires and writes a
`{"source":"fork"}` checkpoint. **[V1]**

**State is fully addressable:** `get_state`, `get_state_history`,
`update_state(config, values, as_node, task_id)`, `bulk_update_state`;
`StateSnapshot` (`types.py:643`) = `values, next, config, metadata, created_at,
parent_config, tasks, interrupts`. **[V]**

> **This is LangGraph's decisive advantage and PACT's hardest portability problem.**
> Pydantic AI has no analogue of `update_state(..., as_node=...)` and no checkpoint id.

## B(c) Tool protocol **[V1]/[V]**

- Declaration: `langchain_core.tools.BaseTool` (`libs/core/langchain_core/tools/base.py:427`)
  with `args_schema`, `response_format: Literal["content","content_and_artifact"]`,
  `tool_call_schema`, `invoke`/`ainvoke`, `_run`/`_arun`.
- Binding: `BaseChatModel.bind_tools(tools, tool_choice=..., **kwargs) -> Runnable`
  (`libs/core/.../chat_models.py:2338-2355`) — **abstract, `raise NotImplementedError`**.
  Tool calling is *not* guaranteed by the `BaseChatModel` contract.
- Execution: `ToolNode` (`libs/prebuilt/langgraph/prebuilt/tool_node.py:622`).
  - Parallel: `executor.map(self._run_one, ...)` (sync) / `asyncio.gather(*coros)` (async).
    **All calls in a step run in parallel; there is no barrier concept.**
  - Ordering: `_combine_tool_outputs` preserves input order.
  - Errors: `handle_tool_errors: bool | str | Callable | type[Exception] | tuple[...]`.
    Handled → `ToolMessage(status="error")`; unhandled → propagates and kills the task.
  - **No per-tool retry budget.** Retries are node-level `RetryPolicy` (`types.py:416`,
    a `NamedTuple`: `initial_interval=0.5, backoff_factor=2.0, max_interval=128.0,
    max_attempts=3, jitter=True, retry_on=default_retry_on`) — *transport* retry.
    Model-corrective retry is middleware (`tool_retry.py`, `model_retry.py`).
  - A tool may return a `Command` to redirect the graph;
    `Command(graph=Command.PARENT, goto=[Send(...)])` from multiple tools merges into one
    parent command. **This is LangGraph's handoff primitive.**
  - `CachePolicy` at `types.py:519` — node-level caching, which pydantic-ai lacks entirely.
- Injection: `InjectedState`, `InjectedStore`, `ToolRuntime` — tools can read graph state
  and the long-term store.

## B(d) Structured output **[V1]**

`ToolStrategy(schema, handle_errors=...)`, `ProviderStrategy`, `AutoStrategy` in
`langchain/agents/structured_output.py`; resolution by `_supports_provider_strategy`
(`factory.py:528`) / `_is_openai_compatible_model` (`:576`); parsing in
`_handle_model_output` (`:1168`).

**Failure behaviour** — `_handle_structured_output_error` (`factory.py:596-624`):
`False` → raise `StructuredOutputValidationError`; `True` → append a `ToolMessage` with
`STRUCTURED_OUTPUT_ERROR_TEMPLATE` and loop; `str` → that string; `type[Exception]`/tuple →
retry only for those; callable → its return value. Multiple structured tool calls in one
response → `MultipleStructuredOutputsError`.

**There is no retry *budget*.** Structured-output correction loops are bounded only by
`recursion_limit`. PACT's `max_output_retries` has no native counterpart; it must be
harness-enforced or approximated by `ModelCallLimitMiddleware`.

## B(e) Streaming **[V]/[V1]**

`StreamMode = Literal["values","updates","checkpoints","tasks","debug","messages","custom"]`
(`types.py:120-134`); `StreamWriter = Callable[[Any], None]` (`types.py:136`);
`get_stream_writer()` (`config.py:126`).

**Ordering guarantees:**
- Across supersteps: totally ordered (BSP), by construction of `while loop.tick()`.
- **Within** a superstep: parallel tasks emit in completion order; no defined per-node order.
- `stream_mode="messages"` (token streaming) is delivered by a **LangChain callback
  handler** — `StreamMessagesHandler(BaseCallbackHandler, _StreamingCallbackHandler)`
  (`pregel/_messages.py:49-50`) — an out-of-band side channel on `on_llm_new_token`, not an
  ordered element of the graph event stream. **[V1]**
- The only total order is the mux sequence number. `ProtocolEvent` (`stream/_types.py:28-41`)
  carries `seq: NotRequired[int]` with the docstring *"Consumers that need a total order
  across root events should use `seq`, not `params.timestamp` (which is wall-clock and not
  monotonic)"*, and `_ProtocolEventParams` (`:14-25`) repeats the warning. **[V]**

> **Negative finding, confirmed:** LangGraph provides **no part-start/delta/end framing**,
> no `PartEndEvent` equivalent, and no adjacency hints. A PACT event stream defined at
> pydantic-ai's granularity **cannot** be reconstructed from LangGraph's `updates`/
> `messages` streams in *native* lowering. In *harness* lowering PACT synthesises the
> framing itself from `BaseChatModel.astream` chunks, which is fine. **[V]**

## B(f) HITL / interrupt semantics **[V]**

`interrupt(value)` — `types.py:811-934`.

- `idx = scratchpad.interrupt_counter()` (`:913`) — **interrupts bind to resume values
  positionally, by call order within the task.** Docstring `:822-828`: *"If a node contains
  multiple `interrupt` calls, LangGraph matches resume values to interrupts based on their
  order in the node. This list of resume values is scoped to the specific task executing the
  node and is not shared across tasks."*
- `PregelScratchpad` (`_internal/_scratchpad.py:8-19`) holds `step, stop, call_counter,
  interrupt_counter, get_null_resume, resume, subgraph_counter` — **three positional
  counters.** **[V]**
- Requires a checkpointer (`types.py:830-831`).

**The critical sentence, verbatim (`types.py:824`):**

> *"The graph resumes from the start of the node, **re-executing** all logic."*

So HITL in LangGraph is **at-least-once for anything the node did before the interrupt.**

`create_agent` works around this structurally by putting approval in a *separate*
`after_model` middleware node that runs *before* the `tools` node, so tools have not
executed yet. Decisions are typed (`middleware/human_in_the_loop.py`):
`DecisionType = Literal["approve","edit","reject","respond"]` (`:51`);
`ApproveDecision` `:77`, `EditDecision` `:84` (with `edited_action: Action` `:90` — *"a
human reviewer can edit the tool name and args"*), `RejectDecision` `:97` (with a `message`
sent to the model), `RespondDecision` `:111` (synthesises a result *on behalf of the tool*).
`ReviewConfig.allowed_decisions: list[DecisionType]` `:60`; `InterruptOnConfig` `:146`. **[V]**

`interrupt_before` / `interrupt_after` are the coarser mechanism — node-name lists checked
in `tick()`/`after_tick()` (`_loop.py:666-671`, `:720-724`). **[V]**

## B(g) Memory & context management **[V1]**

- Short-term: the checkpointed state, plus the `add_messages` reducer with
  `REMOVE_ALL_MESSAGES` and `RemoveMessage` handling.
- Long-term: `BaseStore` reached via `Runtime.store`, injected into tools via
  `InjectedStore` / `ToolRuntime.store`.
- Context-engineering middlewares ship in-box (see §B(a).3).

> **A real capability asymmetry: LangGraph ships a long-term store and context-management
> middlewares; pydantic-ai ships neither.** PACT's memory IR will be `native` on LangGraph
> and `emulated` on pydantic-ai.

## B(h) Multi-agent: what crosses the boundary **[V1]/[V]**

1. **Subgraph as a node.** A compiled graph is a `Runnable`. State crossing is by
   **channel-name overlap**. Namespacing by `CONFIG_KEY_CHECKPOINT_NS`; the parent's
   checkpoint `metadata["parents"]` maps `ns -> checkpoint_id`. The parent propagates
   `CONFIG_KEY_RESUMING` and `CONFIG_KEY_REPLAY_STATE` to subgraphs.
2. **`Send(node, arg)`** (`types.py:664`) — map-reduce; the sent `arg` **can be a completely
   different shape from graph state**.
3. **`Command(graph=..., update=..., goto=..., resume=...)`** (`types.py:759`);
   `Command.PARENT = "__parent__"` (`:808`) escapes one level. A tool returning a `Command`
   is the swarm/handoff primitive.

Blackboard is expressible (a shared `Topic` or `BinaryOperatorAggregate` channel);
market/auction is expressible (channels + `Send` fan-out + a reducer that picks a winner).
**LangGraph covers all eight of AC-5.1's patterns; pydantic_graph covers six.** **[I]**

## B(i) Model abstraction

### B(i).1 The ABC **[V1]**

`BaseChatModel(BaseLanguageModel[AIMessage], ABC)` —
`libs/core/langchain_core/language_models/chat_models.py:272`.

| Member | Line | Contract |
|---|---|---|
| `invoke` / `ainvoke` | `:463`, `:490` | required (via `_generate`) |
| `stream` / `astream` | `:715`, `:842` | falls back to non-streaming if `_stream` absent |
| `_generate` | `:2181` | the real abstract |
| `_stream` | `:2227` | optional |
| `bind_tools` | `:2338-2355` | **`raise NotImplementedError`** |
| `with_structured_output` | `:2357` | default implementation exists |

### B(i).2 `ModelProfile` — capability-shaped, offline, vendored **[V]** (corrects revision 1)

`langchain_core.language_models.model_profile.ModelProfile(TypedDict, total=False)` —
`libs/core/langchain_core/language_models/model_profile.py:13`. Docstring: *"Description of
a chat model's capabilities, exposed via `model.profile`. Data is sourced from
[models.dev], augmented with additional fields, and generated by the `langchain-model-profiles`
package."* Marked **beta**; `__pydantic_config__ = ConfigDict(extra="allow")` (`:30`).

Full field list, verified:

```
metadata:   name, status, release_date, last_updated, open_weights
input:      max_input_tokens, text_inputs, image_inputs, image_url_inputs, pdf_inputs,
            audio_inputs, video_inputs, image_tool_message, pdf_tool_message
output:     max_output_tokens, reasoning_output, reasoning_effort_levels,
            reasoning_effort_default, text_outputs, image_outputs, audio_outputs, video_outputs
tools:      tool_calling, tool_choice, tool_call_streaming
structured: structured_output
other:      attachment, temperature
ModelProfileRegistry = dict[str, ModelProfile]      (:152)
```

Surfaced on the model: `profile: ModelProfile | None = Field(default=None, exclude=True)`
(`chat_models.py:366`), populated by `_set_model_profile` (`:406`) from
`_resolve_model_profile` (`:386`), with `_warn_unknown_profile_keys` (`:426`) warning on a
version mismatch between `langchain-core` and the provider package.

**The data is vendored offline into each partner package** — `libs/partners/*/data/_profiles.py`:

| Package | Lines |
|---|---|
| openrouter | 7624 |
| openai | 1720 |
| huggingface | 1134 |
| mistralai | 629 |
| anthropic | 469 |
| fireworks | 413 |
| groq | 330 |
| xai | 230 |
| deepseek | 105 |
| perplexity | 99 |

~12,750 lines of generated capability data, no network required at runtime.
`langchain_model_profiles` (`libs/model-profiles/`) is only the *generator* CLI; `_summary.py`
enumerates the field labels for PR diffs.

> **This is the best offline model-capability catalogue in the entire 141-repo corpus for
> D8/D17 purposes, and it is exactly the vocabulary D16 needs** (`image_inputs`,
> `audio_inputs`, `video_inputs`, `pdf_inputs`, `image_outputs`, `audio_outputs`).
> It has **no benchmark scores and no cost data** — PACT still owns those.
> Caveat: unlike `infer_model_profile`, reading it requires *constructing the chat model
> object* (or importing the partner package's `_profiles.py` directly, which is private). **[V]/[I]**

---

# PART C — DIVERGENCE MATRIX

Legend: **≡** same semantics · **≈** expressible with adapter work · **✗** genuinely
divergent, PACT must pick one and report.

| # | Concern | Pydantic AI | LangGraph / `create_agent` | Verdict |
|---|---|---|---|---|
| C1 | Unit of execution | `GraphRun` step yielding `Sequence[GraphTask]` (`graph_builder.py:544`) | Pregel **superstep** over channels (`_loop.py:599`) | **≈ (revised — both are superstep-shaped)** |
| C2 | Step counter | `state.run_step` (`_agent_graph.py:1358`), bound by `request_limit=50` | `loop.step`, bound by `recursion_limit=25` | ✗ (different units, 2× different default) |
| C3 | State | message list only (`_agent_graph.py:294`) | arbitrary reducer-merged channels (10 kinds) | ✗ |
| C4 | State addressability | none (in-memory nodes) | `get_state` / `get_state_history` / `update_state(as_node=)` / `checkpoint_id` time travel | ✗ |
| C5 | Persistence | **none anywhere** (`pydantic_graph` has no persistence module) | `BaseCheckpointSaver`, `durability ∈ {sync,async,exit}` | ✗ |
| C6 | HITL primitive | **deferred tools**, exactly-once, nothing re-runs | **`interrupt()`**, node re-executes from start (`types.py:824`) | ✗ **fatal-if-ignored** |
| C7 | HITL decision vocabulary | approve / deny(`message`) / `override_args` (`_deferred.py:100-113`) | approve / edit / reject / respond (`human_in_the_loop.py:51`) | ≈ — but LangGraph's `respond` (answer *as* the tool) has **no pydantic-ai equivalent** |
| C8 | Tool parallelism | parallel with `sequential=True` **barriers** + 3 event-order modes (`_tool_execution.py:89`, `tool_manager.py:102`) | always fully parallel | ✗ (LangGraph cannot express a barrier) |
| C9 | Tool retry | **per-tool-name budget, default 1, reset on success** (`tool_manager.py:97`, `:117-143`, `:185`) | node `RetryPolicy` (transport, `max_attempts=3`) + optional middleware | ✗ |
| C10 | Tool error → model | `ModelRetry`→`RetryPromptPart`; `ToolFailed` terminal | `handle_tool_errors` → `ToolMessage(status="error")` | ≈ |
| C11 | Output modes | `auto/text/image/native/prompted/tool` | `ToolStrategy/ProviderStrategy/AutoStrategy` | ≈ (no `prompted`, no `image` output) |
| C12 | Output retry budget | `max_output_retries` (`_agent_graph.py:353`) | none; bounded by `recursion_limit` | ✗ |
| C13 | Text-vs-tool arbitration | 3 `end_strategy` values + retry-wins + "only schema-validated text may pre-empt" | implicit: tool calls always win | ✗ |
| C14 | Stream framing | `PartStart/Delta/End` + `FinalResultEvent` + adjacency (`messages.py:3313-3396`) | `values/updates/messages/custom/…`; token stream is a **callback side channel** | ✗ |
| C15 | Stream total order | single ordered `AgentStreamEvent` iterator | `ProtocolEvent.seq` only (`stream/_types.py:28-41`) | ✗ |
| C16 | Multi-agent / topology | `pydantic_graph` **`Fork(is_map)` / `Join(reducer)` / `Decision`** (no shared channels) | `Send`, subgraph, `Command(graph=PARENT)`, shared channels | **≈ (revised)** — 6/8 patterns vs 8/8 |
| C17 | Long-term memory | none | `BaseStore` via `Runtime.store` | ✗ |
| C18 | Context management | `HistoryProcessor` fn (not spec-serialisable) | summarization / context-editing / PII middlewares | ≈ |
| C19 | Model **protocol** metadata | **`ModelProfile`** (json_schema_transformer, default output mode, thinking tags) — offline via `infer_model_profile` (`models/__init__.py:1247`) | none | ✗ (pydantic-ai only) |
| C20 | Model **capability** metadata | none (no context window, no modality flags) | **`ModelProfile`** (`model_profile.py:13`) + ~12.7k lines vendored offline | ✗ (LangChain only) |
| C21 | Tool calling guaranteed by model ABC | no (`Model.request` is the only behavioural abstract) | no (`bind_tools` raises `NotImplementedError`) | ≡ (both must gate on a catalogue) |
| C22 | Declarative YAML form | **`AgentSpec` exists** (`agent/spec.py`), MCP declarable | none in core | ✗ |
| C23 | Hook surface | **28 hooks**, `before/after/wrap/on_error` × 7 phases (`capabilities/abstract.py:459-954`) | **8 hooks** + `JumpTo` redirect (`middleware/types.py:66`, `:419-793`) | ✗ (pydantic-ai richer; LangChain can redirect) |
| C24 | Node result caching | none | `CachePolicy` (`types.py:519`), `@task(cache_policy=)` | ✗ |
| C25 | Budget-exhaustion honesty | raises `UsageLimitExceeded` | `create_agent`: raises `GraphRecursionError`. **Deprecated prebuilt fabricates an answer** (`chat_agent_executor.py:684-692`) | ≡ on the live path; ✗ on the import path |

---

# PART D — HARNESS MODE: is D12 implementable?

**Yes, for both. The pydantic-ai path is clean and supported. The LangGraph path is clean
but imposes a hard determinism obligation on how PACT writes its loop.**

## D.1 Pydantic AI in harness mode

### Model transport — exact entry points **[V]**

| Purpose | API | Location |
|---|---|---|
| Resolve a model string → `Model` | `pydantic_ai.models.infer_model(name)` | `models/__init__.py:1280` |
| Resolve protocol profile offline, **no provider constructed** | `pydantic_ai.models.infer_model_profile(name)` | `models/__init__.py:1247` |
| One non-streamed call | `pydantic_ai.direct.model_request(model, messages, *, model_settings, model_request_parameters, instrument)` | `direct.py:55` |
| Sync variant | `pydantic_ai.direct.model_request_sync(...)` | `direct.py:108` |
| One streamed call | `pydantic_ai.direct.model_request_stream(...)` | `direct.py:164` |
| Sync streamed | `pydantic_ai.direct.model_request_stream_sync(...)` | `direct.py:227` |
| Raw ABC | `Model.request(messages, model_settings, model_request_parameters)` | `models/__init__.py:309` |
| Raw streaming ABC | `Model.request_stream(messages, settings, params, run_context)` | `models/__init__.py:346` |
| Durable model call (private) | `durable_exec.temporal._model.TemporalModel` / `prefect._model.PrefectModel` / `dbos._model.DBOSModel` | `:54` / `:38` / `:22` |

`direct.py:1-7` states the contract exactly: *"Methods for making imperative requests to
language models with minimal abstraction. These methods allow you to make requests to LLMs
where the only abstraction is input and output schema translation… thin wrappers around
`Model` implementations."* **[V]** `model_request` (`:99-105`) is literally
`_prepare_model(...)` then `model_instance.request(list(messages), model_settings, mrp)`.

`instrument=` (`direct.py:61`) means **OTel/Logfire instrumentation survives harness mode**.

**Everything PACT needs to control the wire is `ModelRequestParameters`** (§A(i).2).
PACT builds it; the `Model` subclass translates it to the provider wire and back to a
canonical `ModelResponse`. *That is exactly the "framework as transport" contract D12 asks for.*

### Tool transport — exact entry points **[V1]**

| Purpose | API | Location |
|---|---|---|
| Declare a tool from JSON Schema + dispatcher | `pydantic_ai.tools.Tool.from_schema(function, name, description, json_schema, takes_ctx=, sequential=, args_validator=)` | `tools.py:438-493` |
| Implement a whole toolset | subclass `pydantic_ai.toolsets.AbstractToolset` (`get_tools`, `call_tool`) | `toolsets/abstract.py:165-182` |
| MCP | `pydantic_ai.mcp.MCPToolset`, or declaratively `capabilities.MCP.from_spec(url, ...)` | `capabilities/mcp.py:216-231` |

**[I]** For harness mode it is cleaner **not** to use pydantic-ai toolsets at all: PACT owns
tool dispatch and uses `ToolDefinition` purely as a wire-format DTO fed into
`ModelRequestParameters.function_tools`. `AbstractToolset.get_tools/call_tool` require a
`RunContext` PACT would have to fabricate; `ToolDefinition` requires nothing.

### Topology transport — the new option **[V]**

| Purpose | API | Location |
|---|---|---|
| Build a typed parallel graph | `pydantic_graph.GraphBuilder(...)`, `.step()`, `.node()`, `.decision()`, `.match()`, `.join(reducer, initial=)`, `.edge_from().to()`, `.add()` | `graph_builder.py:1139`, `:1239`, `:1531`, `:1543`, `:1366`, `:1518`, `:1408` |
| Fan out / map-reduce | `Fork(is_map=True)` | `node.py:60-77` |
| Gather / race | `Join(reduce_list_append \| ReduceFirstValue \| reduce_sum \| reduce_dict_update, initial=)` | `join.py`, exports `__init__.py:23-33` |
| Drive step-by-step | `async with graph.iter(state=, deps=, inputs=) as run:` then `await run.next(...)` | `graph_builder.py:313`, `:564` |
| Redirect after End/error | `run.override_next([GraphTaskRequest…] \| EndMarker(v))` | `graph_builder.py:586` |
| Drive the *agent* graph node-by-node | `AgentRun.next(node)`; `AgentRun.ctx`; `AgentRun.next_node` | `run.py:328`, `:117`, `:125` |

### What PACT must reimplement

Everything in `_agent_graph.py` (2702 lines): history cleaning + dangling-tool-call repair
(`:2484`, `:2529`, `:2614`, `:2676`), the four-node state machine, `end_strategy`
(`_tool_execution.py:122-165`), the two retry budgets, deferred-tool batching, the streaming
part-framing (`models/__init__.py:791-890`) and `FinalResultEvent` detection (`:1620`).

Roughly **6,500 lines of pydantic-ai's ~15k core** is loop semantics PACT takes over. That
is the real cost of D12 and it should be stated in the implementation plan.

### Residual loss in harness mode on pydantic-ai

| Lost | Why | Severity |
|---|---|---|
| The 28-hook capability stack (`capabilities/abstract.py:459-954`) | hooks hang off the agent graph, not off `Model` | medium — PACT gets its own hook model; copy the shape (§F.20) |
| `InstrumentedModel` OTel spans | **recoverable** — `direct(instrument=)` (`direct.py:61`) | none |
| Durable-exec | reachable only via private `_model` modules | medium — declare `emulated (private API)` |
| `AgentSpec` YAML round-trip | it constructs an `Agent` | medium — PACT is the spec; import it (§F.15) |
| `ToolSearch` / `defer_loading` hierarchical tool routing | capability-bound | medium — PACT must reimplement, and it is the mechanism SYNTHESIS.md F-series wants |

**Verdict: pydantic-ai harness lowering is clean and low-risk.** `direct.model_request` is a
first-class, documented, supported API whose *entire stated purpose* is this use case.

### Why *not* `AbstractAgent` **[V]**

`AbstractAgent` declares **13 abstract members** (`agent/abstract.py:244, 250, 259, 265, 271,
277, 283, 289, 300, 1387, 1507, 1668, 1672`): nine properties, `iter` (`:1388`), `override`
(`:1508`), `__aenter__`/`__aexit__`. `iter` is the only execution method — `run`, `run_sync`,
`run_stream`, `run_stream_events` are all implemented on top of it (`:363`, `:557`, `:754`,
`:1167`). But `iter` must return an `AgentRun`, whose `_graph_run` is typed
`GraphRun[GraphAgentState, GraphAgentDeps[AgentDepsT, Any], FinalResult[OutputDataT]]`
(`run.py:97-99`).

> **A PACT harness cannot implement `AbstractAgent` without constructing pydantic-ai's own
> graph state objects.** "A PACT agent that *is* a pydantic-ai `Agent`" is not on offer.
> "A PACT loop that *uses* pydantic-ai models, tools and graphs" is.

## D.2 LangGraph in harness mode

Two viable shapes; **prefer (B)**.

### (A) Bare transports, no LangGraph at all **[V1]**

| Purpose | API | Location |
|---|---|---|
| Resolve model | `langchain.chat_models.init_chat_model(...)` | `libs/langchain_v1/langchain/chat_models/__init__.py:7` |
| Read capabilities | `model.profile` (`ModelProfile`) | `chat_models.py:366` |
| Bind tools | `BaseChatModel.bind_tools(tools, tool_choice=...)` | `chat_models.py:2338` |
| Call | `.invoke(messages)` / `.ainvoke(messages)` | `:463`, `:490` |
| Stream | `.stream(...)` / `.astream(...)` | `:715`, `:842` |
| Structured | `.with_structured_output(schema, include_raw=)` | `:2357` |
| Tools | `BaseTool.ainvoke({...})` | `tools/base.py:741` |

Pure transport, **zero** LangGraph semantics — no checkpointing, no interrupt, no store.
Satisfies D12's letter but throws away the one thing LangGraph is uniquely good at.

### (B) **Recommended:** PACT loop inside `@entrypoint`, model/tool calls as `@task` **[V]**

| Purpose | API | Location |
|---|---|---|
| Wrap PACT's loop as a durable, checkpointed, resumable unit | `@langgraph.func.entrypoint(checkpointer=, store=, cache=, cache_policy=, retry_policy=, context_schema=, timeout=)` | `func/__init__.py:262`, `__call__` `:516-620` |
| Memoised, retried, cached unit of work | `@langgraph.func.task(name=, retry_policy=, cache_policy=, timeout=)` | `func/__init__.py:110-251` |
| Pause for a human | `langgraph.types.interrupt(value)` | `types.py:811` |
| Resume | `graph.invoke(Command(resume=...), config)` | `types.py:759` |
| Carry state across invocations | `previous:` parameter + `entrypoint.final(value=, save=)` | `func/__init__.py:279-290`, `:476-504` |
| Emit PACT's own events | `get_stream_writer()` + `stream_mode="custom"` | `config.py:126`, `types.py:136` |
| Inspect / edit state | `graph.get_state(config)`, `graph.update_state(...)` | `pregel/main.py:1392`, `:2515` |

`entrypoint.__call__` (`func/__init__.py:559-609`) builds a **single-node Pregel graph** with
exactly three channels — `START: EphemeralValue(input_type)`, `END: LastValue(output_type)`,
`PREVIOUS: LastValue(save_type)` — and `stream_eager=True`. **[V]** That is the whole trick:
PACT's loop is one node; PACT's model and tool calls are `@task`s.

**Three hard constraints, all verified:**

1. **The memoisation is positional.** `_call` (`pregel/_runner.py:700-760`) takes the ordinal
   from `scratchpad.call_counter()` (`:722-724`) and, if the resulting task already has
   writes, returns the recorded `RETURN`/`ERROR` **without re-executing** (`:745-757`).
   `interrupt()` binds the same way via `interrupt_counter()` (`types.py:913`).

   > **Therefore PACT's harness loop body must be deterministic in the *sequence of `@task`
   > invocations* given the same replayed results.** Any nondeterminism — dict/set iteration
   > order, `random`, wall-clock branching, an `asyncio.gather` whose completion order
   > changes which task is created next — **silently mis-binds memoised results**. This is a
   > hard, non-negotiable constraint on how PACT writes its loop and it must be a documented
   > conformance requirement.

2. **Generators are forbidden.** `entrypoint.__call__:525-529` raises
   `NotImplementedError("Generators are not supported in the Functional API")` for both
   `isgeneratorfunction` and `isasyncgenfunction`. **[V]** PACT's loop is naturally an async
   generator (it streams events). It must be restructured as a plain coroutine that pushes
   events through `get_stream_writer()`.

3. **Strict msgpack serde may apply.** `func/__init__.py:610-619` builds a
   `_serde.build_serde_allowlist(schemas=[input_type, output_type, save_type, context_schema],
   channels=graph.channels)` and applies it to the checkpointer when
   `_serde.STRICT_MSGPACK_ENABLED` (`_internal/_serde.py:24-29`). **[V]** PACT's carried state
   must be declared in the entrypoint's type annotations or it will not survive a checkpoint.

### Residual loss in harness mode on LangGraph

| Lost | Why | Severity |
|---|---|---|
| `stream_mode="updates"` per-node granularity | there is only one node | low — PACT emits its own via `StreamWriter` / `stream_mode="custom"` |
| Graph visualisation / Studio node view | one node | low, cosmetic |
| `interrupt_before` / `interrupt_after` by node name | no named nodes | low — PACT calls `interrupt()` explicitly |
| Per-node `RetryPolicy` | replaced by per-`@task` `retry_policy` | none |
| Middleware ecosystem (21 modules) | they are `AgentMiddleware`, bound to `create_agent` | medium — PACT reimplements summarization/PII/context-editing, or exposes them as `code` escapes |

**Verdict: LangGraph harness lowering is implementable and is *better for fidelity* than
native lowering**, at the cost of a determinism obligation, a no-generators restructure, and
the loss of node-level observability.

## D.3 Answer to the assignment's precise question

> **Which of these can PACT drive in harness mode, and what is the exact API entry point?**

| Capability | Pydantic AI entry point | LangGraph / LangChain entry point | Harness-drivable? |
|---|---|---|---|
| (a) Loop / step boundaries / termination | **PACT owns.** Transport: `direct.model_request` (`direct.py:55`) | **PACT owns.** Transport: `BaseChatModel.invoke` after `bind_tools` (`chat_models.py:463`, `:2338`) | **Yes, both** |
| (a′) Loop bound | PACT owns; native equivalent `UsageLimits.request_limit` (`usage.py:302`) | PACT owns; native `recursion_limit` (`config.py:171`) | **Yes, both** |
| (b) State persistence / resume | **No.** Nothing in the tree persists. Private `TemporalModel` (`durable_exec/temporal/_model.py:54`) gives durable *calls*, not durable *loop* | **Yes.** `@entrypoint(checkpointer=…)` (`func/__init__.py:262`); `get_state`/`update_state` (`main.py:1392`, `:2515`) | **LangGraph yes; pydantic-ai no** |
| (c) Tool schema on the wire | `ModelRequestParameters.function_tools: list[ToolDefinition]` (`models/__init__.py:136`); `Tool.from_schema` (`tools.py:438`) | `bind_tools(tools=[...])` (`chat_models.py:2338`) | **Yes, both** |
| (c′) Tool execution | PACT's own; optionally `AbstractToolset.call_tool` (`toolsets/abstract.py:170`) | PACT's own; optionally `BaseTool.ainvoke` (`tools/base.py:741`) | **Yes, both** |
| (c″) Parallel + barriers + retries | **PACT owns entirely** | **PACT owns entirely** | **Yes, both** |
| (d) Structured output | `ModelRequestParameters.output_mode / output_object / output_tools / prompted_output_template` (`models/__init__.py:139-142`) | `.with_structured_output(schema)` (`chat_models.py:2357`), or a PACT-built tool | **Yes, both** — but **grammar-constrained decoding is not reachable through either abstraction** |
| (e) Streaming events | `direct.model_request_stream` (`direct.py:164`) → `StreamedResponse.__aiter__` (`models/__init__.py:791`) gives part framing **for free** | `BaseChatModel.astream` (`chat_models.py:842`) gives raw chunks; PACT must **synthesise** part framing | **Yes, both — asymmetric effort** |
| (f) HITL pause/resume | *No framework support needed.* PACT returns a `DeferredToolRequests`-shaped payload and is re-entered with `DeferredToolResults` (`_deferred.py:27`, `:155`) | `langgraph.types.interrupt(value)` inside the `@entrypoint` body, with every side effect inside a `@task` (`types.py:811`, `_runner.py:745`) | **Yes, both — with different re-execution semantics (C6/E1)** |
| (g) Long-term memory | none | `Runtime.store` / `BaseStore` | **LangGraph yes; pydantic-ai no** |
| (g′) Context management | `HistoryProcessor` shape only; PACT owns | 21 middlewares, not reachable outside `create_agent`; PACT owns | **PACT owns on both** |
| (h) Topology / multi-agent | `pydantic_graph.GraphBuilder` + `Fork`/`Join`/`Decision` (`graph_builder.py:1139`, `node.py:60`, `join.py`) — **or PACT owns it** | `StateGraph` + `Send` + `Command(graph=PARENT)` — **or PACT owns it** | **Yes, both; PACT owning it is simpler and portable** |
| (i) Model binding | `infer_model` (`:1280`); protocol capabilities via `infer_model_profile` (`:1247`) **offline, provider-free** | `init_chat_model`; capability metadata via `model.profile` (`chat_models.py:366`) + vendored `_profiles.py` | **Yes, both — complementary metadata (C19/C20)** |

**D12 verdict: implementable.** The two entry points that carry the whole design are
`pydantic_ai.direct.model_request` / `model_request_stream` (`direct.py:55`, `:164`) and
`BaseChatModel.bind_tools(...).ainvoke/.astream` (`chat_models.py:2338`, `:490`, `:842`).
Both are stable, documented, minimal-abstraction surfaces. Neither requires constructing the
framework's agent object.

---

# PART E — WHAT RESISTS (brutal section)

## E1. The HITL semantics are not reconcilable; PACT must choose and report

Pydantic AI: deferred results, **nothing re-runs**. LangGraph: `interrupt()` **re-runs the
node from the top** (`types.py:824`, verbatim).

PACT cannot have both. It should pick pydantic-ai's exactly-once semantics, because
at-least-once tool side effects are indefensible in a spec that admits `computer_use` (D16).
On LangGraph the harness must then guarantee that **every side-effecting operation is inside
its own `@task`** (memoised at `_runner.py:745-757`) and that the loop body above the
interrupt is pure. **That is a codegen obligation, not a runtime one, and the CTS must check
it.**

If PACT ever supports *native* lowering onto a hand-written LangGraph node containing
`interrupt()`, the lattice entry for HITL must be `degraded`, with the report stating
"tool side effects before the approval point may re-execute."

**Second-order problem revision 1 missed:** LangGraph's `RespondDecision`
(`human_in_the_loop.py:111-120`) lets a human answer *on behalf of the tool*. Pydantic AI's
`DeferredToolResults.calls` accepts `ToolReturn | ToolFailed | ModelRetry | RetryPromptPart`
(`_deferred.py:163`), which covers it — **but the reverse is not true**: pydantic-ai's
`ToolApproved.override_args` (`_deferred.py:103`) and LangGraph's `EditDecision.edited_action`
(`:90`) differ in that LangGraph's can edit **the tool name as well as the args**
(*"a human reviewer can edit the tool name and args"*, `:93`). PACT's approval IR must
therefore carry `override_tool: str | None` **and** `override_args: object | None`, or the
LangGraph import is lossy.

## E2. `sequential=True` tool barriers have no LangGraph expression

`_segment_by_barriers` (`_tool_execution.py:89-108`) is real and load-bearing. `ToolNode`
runs everything in parallel. In harness mode PACT implements barriers itself — fine. In
**native** LangGraph lowering it is `unsupported`, full stop. Do not pretend otherwise.

## E3. `end_strategy` is three loop semantics wearing one flag

`'early' | 'graceful' | 'exhaustive'` (`_tool_execution.py:122-153`) plus retry-wins plus
"only schema-validated text may pre-empt tools". This changes *which tools execute* and
*which output wins*. If PACT does not model it, importing a real pydantic-ai agent is lossy
in a way that changes side effects. **PACT's loop IR needs a first-class `output_arbitration`
policy with at least these three values.**

## E4. LangGraph's state model is strictly more expressive and PACT will not capture it

Ten channel kinds with user-supplied reducers, `_get_overwrite` markers that bypass the
reducer (`binop.py:32`), `Send` with off-schema payloads (`types.py:664`),
`Command(graph=PARENT)` (`:808`), `update_state(as_node=)` (`main.py:2515`), time-travel
forks, `DeltaChannel` sentinels, `UntrackedValue` (never checkpointed).

Under D15 ("translate or nothing"), a PACT importer over a real LangGraph app will **reject**
a large fraction of real-world LangGraph codebases rather than wrap them. That is the correct
call, but it must be said out loud and budgeted for in D10's "migration tool" positioning.
The honest framing: **PACT's LangGraph importer is a `create_agent`-shaped importer, not a
`StateGraph`-shaped one.**

## E5. Streaming fidelity is asymmetric and PACT's event model will over-promise on LangGraph

Pydantic AI gives part-level framing with adjacency hints (`messages.py:3313-3396`,
`models/__init__.py:817-852`); LangGraph gives an out-of-band callback token stream
(`pregel/_messages.py:49`) with only a mux `seq` (`stream/_types.py:28-41`). PACT's canonical
event stream should be defined at pydantic-ai's granularity — it is the richer one and
voice/TTFT (D16) needs it — so in **harness** mode PACT synthesises the framing from
`astream` chunks (fine), and in **native** LangGraph mode the streaming lattice entry is
`degraded`.

**Extra hazard:** because `iterator_with_final_event` **breaks and re-drains**
(`models/__init__.py:812-815`), `FinalResultEvent` is *mid-stream*, not terminal. Any PACT
consumer that treats "final result" as end-of-stream will truncate. Spell this out.

## E6. `create_react_agent` is deprecated; the adapter target moved packages

`chat_agent_executor.py:274-276`, `:311-318`. Native lowering must target
`langchain.agents.create_agent` (`langchain` 1.3.14) and harness lowering must target
`langgraph.func` (`langgraph` 1.2.9) — **two packages on two release cadences**, both
recorded in `pact.lock`. This is R2 (adapter rot) manifesting **before the first adapter is
written**, and it is direct evidence for "harness lowering is the conformance floor":
`langgraph.func.entrypoint`/`task` and `BaseChatModel.invoke` are far more stable surfaces
than any agent factory.

## E7. Pydantic AI already ships a competing YAML spec — and it just got a topology engine too

`agent/spec.py` + `capabilities/__init__.py:72-94` + the rewritten `pydantic_graph`. The gap
between "pydantic-ai + AgentSpec + pydantic_graph" and PACT is now **narrower than revision 1
assumed**: they have a YAML agent spec, a serialisable capability registry, declarable MCP,
*and* a Fork/Join/Decision topology library.

**What they still cannot do, and what PACT's entire value proposition must therefore rest on:**
evals in the artifact, SLOs, capability *requirements*, variants, model portability, learning,
the directory expansion, and cross-framework portability. **If PACT's differentiation is
described as "declarative agents + topology", it is now describing something Pydantic already
ships.** Update the positioning in `00-THESIS.md` §1.3 accordingly.

## E8. Default loop bounds differ by 2× and are in different units

`request_limit=50` counted in **model requests** (`usage.py:302`) vs `recursion_limit=25`
counted in **supersteps** (`config.py:171`). In `create_agent` one PACT step costs **≥ 2
supersteps** (model node + tools node, plus one node per middleware hook), so a 25-superstep
budget is roughly a **10-step agent** once two middlewares are installed. Publish the
conversion in the lattice or CTS runs will fail for reasons unrelated to fidelity.

## E9. Neither framework guarantees tool calling at the model ABC level

`Model.request` is pydantic-ai's only behavioural abstract (`models/__init__.py:309`);
`BaseChatModel.bind_tools` raises `NotImplementedError` (`chat_models.py:2355`). "This model
can call tools" is a **catalogue fact** in both, never an **interface fact**. PACT's
capability predicate language (O3.1) is therefore load-bearing for *correctness*, not merely
for planning: without it, PACT cannot know a binding will work before it runs.

## E10. The two model-metadata schemas are disjoint, and neither is sufficient

- pydantic-ai `ModelProfile` (`profiles/__init__.py:48-120`) = **how to talk to it**.
  Offline and provider-free via `infer_model_profile` (`models/__init__.py:1247`).
- LangChain `ModelProfile` (`model_profile.py:13-150`) = **what it can do**. Offline via
  ~12.7k vendored lines, but requires the partner package and (officially) a constructed
  model object.
- **Neither has benchmark scores, cost, or SLO characteristics.** AC-3.2's
  `MMLU > 80 && SWE-Verified > 40` has **no upstream source in either framework**. PACT's
  `models/catalog.yaml` must own that axis entirely, and D8's "optional pluggable providers"
  cannot be deferred — they are the only route to those figures.

## E11. Harness mode inherits pydantic-ai's message-cleaning semantics, or it breaks providers

`_clean_message_history` (`_agent_graph.py:2676`) composes orphan-result dropping (`:2484`),
dangling-tool-call repair (`:2529`) and consecutive-message merging (`:2614`). These are not
cosmetic — providers reject histories with dangling tool calls. If PACT owns the loop, **PACT
owns this repair logic**, and getting it wrong produces provider-specific 400s that look like
adapter bugs. Budget for it explicitly; it is ~230 lines of subtle code that revision 1
listed as a one-line footnote.

## E12. `Model.request` receives `ModelRequestParameters` PACT must construct correctly, and the two output fields are coupled

`with_default_output_mode` (`models/__init__.py:175-183`) documents the invariant:
*"`output_mode='tool'` implies `allow_text_output=False`, while `'native'` and `'prompted'`
imply `allow_text_output=True`. This ensures the two fields stay in sync."* A PACT harness
that sets `output_mode` without updating `allow_text_output` will produce a model that is
allowed to answer in text when the spec says it must call the output tool. **This is a silent
correctness bug and belongs in the CTS.**

---

# PART F — DESIGN IMPLICATIONS FOR PACT (actionable)

1. **Define the harness contract as exactly two verbs.** `model_call(messages, params) ->
   response` and `tool_call(name, args) -> result`. Adapter authors implement only those.
   Reference bindings: `pydantic_ai.direct.model_request` / `model_request_stream`
   (`direct.py:55`, `:164`); `BaseChatModel.bind_tools(...).ainvoke/.astream`
   (`chat_models.py:2338`, `:490`, `:842`).

2. **Make `ModelRequestParameters` the shape of PACT's wire-request IR** — copy
   `models/__init__.py:133-186` field-for-field (`function_tools`, `native_tools`,
   `output_mode`, `output_object`, `output_tools`, `prompted_output_template`,
   `allow_text_output`, `allow_image_output`, `instruction_parts`, `thinking`) and add D16
   modality fields. **Encode the `output_mode`/`allow_text_output` coupling as a schema
   invariant, not a convention** (§E12).

3. **Adopt pydantic-ai's deferred-tool model as PACT's normative HITL semantics** and forbid
   re-execution. Spec text: *"a tool that has produced a result MUST NOT be re-invoked when a
   run is resumed."* Enforce on LangGraph by requiring every side-effecting step to be its own
   `@task` (memoised at `_runner.py:745-757`). Add a CTS case that kills the process
   mid-approval and asserts each tool ran exactly once.

4. **Make the approval IR carry `override_tool` as well as `override_args`,** and include a
   `respond_as_tool` decision. Pydantic AI supplies args-override only
   (`_deferred.py:103`); LangGraph's `EditDecision` can rewrite the tool name (`:90-93`) and
   `RespondDecision` answers on the tool's behalf (`:111-120`). Anything narrower loses data
   on a LangGraph import.

5. **Require determinism of the harness loop body under replay, and say so normatively.**
   `@task` and `interrupt()` bind by ordinal (`_scratchpad.py:8-19`, `_runner.py:722-724`,
   `types.py:913`). PACT's loop IR must be evaluable with no uncontrolled nondeterminism: no
   set/dict-iteration-order-dependent dispatch, no wall-clock branching, and parallel fan-out
   must fix task-creation order before awaiting. **Make this a conformance level, not a
   footnote.**

6. **Specify PACT's loop as a coroutine + event sink, never as a generator.**
   `langgraph.func` rejects generator entrypoints outright (`func/__init__.py:525-529`).
   The portable shape is `async def loop(state, emit: Callable[[Event], None]) -> Result`,
   which maps onto `get_stream_writer()` (`config.py:126`) on LangGraph and onto a plain
   callback on pydantic-ai.

7. **Add `output_arbitration` to the loop IR with values `early | graceful | exhaustive`,
   defaulting to `graceful`,** plus `retry_wins: bool` and
   `text_may_preempt_tools: never | schema_validated_only`. Anything less loses
   `_tool_execution.py:122-153` on import.

8. **Add `sequential: bool` (barrier) to the tool IR** (`ToolDefinition.sequential`,
   `tools.py:544+34`) and a run-scoped
   `parallel_execution_mode: parallel | parallel_ordered_events | sequential`
   (`tool_manager.py:102`). Declare it `unsupported` in any native LangGraph lattice entry.

9. **Split the retry budget into two named budgets: `tool_retries` (per tool name) and
   `output_retries` (per run).** Specify the reset rule — **per-tool count resets on success**
   (`tool_manager.py:117-143`) — because it is observable behaviour. Set the PACT default to
   pydantic-ai's (`default_max_retries = 1`, `tool_manager.py:97`) and document that
   LangGraph's `RetryPolicy(max_attempts=3)` is a *transport* retry that composes with, not
   substitutes for, this budget.

10. **Specify `on_budget_exhausted: fail | truncate | summarise`, default `fail`,** and add
    a lattice rule: any adapter that fabricates a terminal answer on budget exhaustion
    (`chat_agent_executor.py:684-692`) reports `degraded`. Also specify **budget units**:
    `steps` (PACT), mapped to `request_limit` on pydantic-ai and to
    `recursion_limit / supersteps_per_step` on LangGraph, with the conversion published
    (§E8).

11. **Define PACT's stream event vocabulary as a superset of `AgentStreamEvent`**
    (`messages.py:3580`): `part_start / part_delta / part_end / final_result / tool_call /
    tool_result / deferred_requests / deferred_results / enqueued`, with
    `previous_part_kind` / `next_part_kind` adjacency (`messages.py:3313`, `:3358`) and the
    rule *"`part_end` is emitted only for delta-bearing part kinds"*
    (`models/__init__.py:827-830`). **Normatively state that `final_result` is emitted at the
    point of match, not at stream end** (`:801-815`), and that consumers must keep reading.

12. **Carry two distinct identifiers in the IR and in every event: `run_id` and
    `conversation_id`,** with pydantic-ai's exact resolution rule — `run_id` is *never*
    inherited from history; `conversation_id` is inherited from the most recent message if
    present (`_agent_graph.py:298-308`, verbatim). This is the cheapest thing PACT can copy
    that both frameworks and the Bud run ledger need.

13. **Model PACT state as `messages + named channels`, not one or the other.** Messages are
    the portable core (both frameworks agree); named channels with declared reducers are
    required to import anything real from LangGraph. Make the reducer set a **closed
    no-code vocabulary** derived from what both sides actually ship:
    `last | last_after_finish | append | extend | merge | sum | max | first | topic |
    barrier | ephemeral | untracked`, mapping onto `LastValue`/`LastValueAfterFinish`/
    `Topic`/`BinaryOperatorAggregate`/`NamedBarrierValue`/`EphemeralValue`/`UntrackedValue`
    (`channels/*.py`) and onto `reduce_list_append`/`reduce_list_extend`/`reduce_dict_update`/
    `reduce_sum`/`ReduceFirstValue` (`pydantic_graph/__init__.py:23-33`). Arbitrary reducers
    become `code`-typed escapes (F-2/F-3). **D14 requires the closed set to be the default.**
    Also model the **overwrite marker** (`binop.py:32`) or LangGraph writes that bypass the
    reducer are silently mis-imported.

14. **Split the model catalogue into two declared axes, because the frameworks do.**
    - **Protocol axis** (how to talk to it): seed from `pydantic_ai.profiles`
      (`profiles/__init__.py:48-120`) via `infer_model_profile` (`models/__init__.py:1247`) —
      a provider-free, offline lookup. Fields: `default_structured_output_mode`,
      `json_schema_transformer`, `supports_json_schema_output`, `supports_thinking`,
      `thinking_tags`, `supports_inline_system_prompts`, `supported_native_tools`.
    - **Capability axis** (what it can do): seed from LangChain's `ModelProfile`
      (`model_profile.py:13-150`) and the ~12.7k vendored lines in `libs/partners/*/data/_profiles.py`.
      Fields: `max_input_tokens`, `max_output_tokens`, `{text,image,audio,video,pdf}_inputs`,
      `{text,image,audio,video}_outputs`, `tool_calling`, `tool_choice`,
      `tool_call_streaming`, `structured_output`, `reasoning_output`,
      `reasoning_effort_levels`, `temperature`, `open_weights`, `status`.
    - **Benchmark/cost/SLO axis: PACT owns it outright.** Neither framework has it (§E10).
      Record provenance as `source: langchain-model-profiles @ <sha> (models.dev)` and
      `source: pydantic-ai profiles @ <sha>` per field, satisfying AC-3.3.
    D16's modality vocabulary should be **exactly LangChain's field names**, because a
    generated, maintained, offline dataset already populates them.

15. **Treat `pydantic_ai.agent.spec.AgentSpec` as a first-class import source and a superset
    target.** PACT must (a) import `AgentSpec` YAML losslessly-or-reported, (b) optionally
    emit it for the single-agent native fast path, and (c) enumerate what PACT adds that it
    lacks — `tools`, `evals`, `slo`, `capabilities_required`, `variants`, `topology`,
    `memory`, `loop`, `learning`. Add a fixture asserting round-trip
    `AgentSpec → PACT → AgentSpec` with a guaranteed report entry for `ProcessHistory`
    (`capabilities/process_history.py:41-42`, `get_serialization_name -> None`).

16. **Declare MCP the only no-code tool mechanism in v1.** pydantic-ai reaches MCP
    declaratively via `capabilities.MCP.from_spec(url, ...)` (`capabilities/mcp.py:216-231`);
    LangGraph via a `BaseTool` list. Everything else (`Tool.from_schema` needs a callable)
    is codegen *inside the adapter*, which is acceptable under D14 only because the **author**
    never writes it.

17. **Pin the LangGraph adapter to `langgraph.func` + `langchain_core` model/tool ABCs, never
    to an agent factory,** and record **both** package versions in `pact.lock`
    (`langgraph` 1.2.9, `langchain` 1.3.14, `langchain-core` 1.5.1). `create_react_agent` is
    already deprecated (`chat_agent_executor.py:274-276`).

18. **Make durable-run state addressable in the IR from day one**: `thread_id`,
    `checkpoint_id`, `parent_checkpoint_id`, `step`, `source ∈ {input, loop, update, fork}`
    (`checkpoint/base:38-60`), plus a `StateSnapshot`-shaped read model
    (`values, next, tasks, interrupts, parent`, `types.py:643`). **Pydantic AI cannot supply
    any of these**, so its lattice entry for AC-2.6 kill-and-resume is `emulated` (PACT
    persists its own checkpoint) — say so explicitly rather than claiming L4.

19. **Specify three durability levels matching LangGraph's** — `sync | async | exit`
    (`types.py:87`) — because they are the observable difference between "resumable after
    kill" and "not". Default `async`; **require `sync` for any run declaring `computer_use`
    or an approval gate** (D16 + E1 together).

20. **Model PACT's hook IR on pydantic-ai's quadruple, and add LangChain's redirect.**
    `before_X / after_X / wrap_X / on_X_error` per phase (`capabilities/abstract.py:459-954`,
    28 hooks) is strictly better factored than LangChain's 8, but LangChain's
    `JumpTo = Literal["tools","model","end"]` (`middleware/types.py:66`) is the one thing
    pydantic-ai's hooks cannot do. PACT's hook return type should be
    `Continue | Replace(value) | JumpTo(target)`.

21. **Own the message-repair algorithm and specify it normatively.** `_clean_message_history`
    (`_agent_graph.py:2676`) + orphan dropping (`:2484`) + dangling-call repair (`:2529`) +
    consecutive merging (`:2614`) are provider-compatibility requirements, not niceties
    (§E11). Write them as spec text with a conformance fixture per repair.

22. **Map PACT's topology IR onto `pydantic_graph`, not onto `Agent`, for pydantic-ai native
    lowering.** `Fork(is_map=True)` → map/scatter; `Join(reduce_list_append, initial=[])` →
    gather; `Join(ReduceFirstValue, ...)` → race; `Decision` + `match()` → supervisor routing
    (`node.py:60`, `graph_builder.py:1366`, `:1531`, `:1543`). Declare **blackboard** and
    **market/auction** `emulated` on this adapter — there is no shared mutable channel space,
    only reducers at joins.

23. **Write the CTS HITL case first.** It discriminates every divergence in this audit at
    once: approval mid-parallel-tool-batch, process kill, resume; assert (i) exactly-once tool
    execution, (ii) `override_args` *and* `override_tool` honoured, (iii) resulting message
    history byte-identical modulo timestamps across both adapters. **If it passes on both,
    D12 is proven; if it does not, nothing else matters.**

24. **Update `00-THESIS.md` §1.3.** The competitive gap narrowed: pydantic-ai now ships a YAML
    agent spec *and* a Fork/Join/Decision topology engine. PACT's differentiation is the
    contract (evals + SLOs + capability requirements), variants/model portability, learning,
    and the tree — **not** "declarative agents with topology", which is now table stakes at
    the highest-priority target framework.

---

# PART G — Honesty ledger

**Verified this session ([V]):** `pydantic_graph` module inventory, exports, `Fork`, `Join`
builder signature, `Decision`, `GraphRun.__anext__` / `next` / `override_next`, `Graph.iter`;
`build_agent_graph`; `GraphAgentState` verbatim; `run_step` increment sites; `direct.py`
function offsets and `model_request` body; `ModelRequestParameters` verbatim +
`with_default_output_mode` invariant; `StreamedResponse.__aiter__` composition,
`iterator_with_final_event`, `iterator_with_part_end`, `_get_final_result_event`;
`messages.py` event class/union offsets; `ToolDefinition` field offsets; `usage.py`
`UsageLimits` fields and checks; `tool_manager.py` `default_max_retries`,
`parallel_execution_mode`, `for_run_step` reset, `_check_max_retries`; `_tool_execution.py`
`_segment_by_barriers` + `process_tool_calls` docstring; `_output.py` schema class offsets;
`_deferred.py` shapes; `capabilities/abstract.py` hook offsets; `agent/abstract.py`
abstractmethod offsets; `durable_exec/*/_model.py` classes and `temporal/__init__.py:32-41`
exports; `profiles/__init__.py` field offsets; `infer_model_profile` / `infer_model` offsets.
LangGraph: `PregelLoop.tick`/`after_tick` full body, `Pregel.stream` driver + recursion-limit
raise, `errors.py:67`, `_runner.py:_call` memoisation, `_scratchpad.py`, `types.py:824`
interrupt docstring + `interrupt_counter`, all ten channel docstrings, `stream/_types.py`
seq warning, `func/__init__.py` `entrypoint.__call__` body incl. generator rejection and
serde allowlist, `config.py:126`. LangChain: `model_profile.py` full field list,
`chat_models.py:366/386/406/426`, partner `_profiles.py` line counts, `factory.py` symbol
offsets, `middleware/types.py` hook offsets, `human_in_the_loop.py` decision types,
21-module middleware listing, absence of "need more steps" in `langchain_v1`.

**Carried from revision 1 without line-by-line re-read ([V1]):** the `UserPromptNode` routing
branch offsets; `CallToolsNode._run_stream` decision-order offsets; `Tool.from_schema` body;
`AbstractToolset` combinator offsets; `_clean_message_history` component behaviour;
`chat_agent_executor.py` deprecation offsets; `tool_node.py` offsets; `structured_output.py`
offsets; `pregel/_messages.py:49`; `checkpoint/base` TypedDict offsets; `Send`/`Command`
bodies; `capabilities/mcp.py:216-231`; `agent/spec.py` field list. These were structurally
re-confirmed (files exist, symbols present) but I did not re-read every cited line.

**Not verified at all:**
- I executed nothing. No agent was run, no test invoked, no timing measured. Every behavioural
  claim is read from source.
- I did not read `pydantic_graph/paths.py`, `parent_forks.py`, or `step.py` in full — the
  Fork/Join semantics above come from `node.py`, `join.py`, `__init__.py` exports and the
  `graph_builder` signatures. The claim "sibling cancellation gives race semantics" is **[I]**
  from `_cancel_sibling_tasks` (`graph_builder.py:1096`) + `ReduceFirstValue`, not from
  reading the cancellation body.
- I did not read the `durable_exec` `_agent.py` / `_workflow.py` bodies, so "PACT can run its
  own loop inside a Temporal workflow using `TemporalModel`" is **[I]** from the constructor
  signature and the activity definitions, not from a working example.
- I did not open the vendored `_profiles.py` data files; the line counts are from `wc -l` and
  the field list from `model_profile.py`. Whether every partner populates every field is
  unverified.
- I did not read `_tool_search.py` (25 KB) or the `toolsets/` implementations.
- I did not read the JS/TS sides (`vercel-ai`, `claude-agent-sdk-ts`), out of scope for this
  stream but required for D4's TypeScript adapters.
- **Version caveat:** both `pydantic-ai-slim` and `pydantic-graph` derive their version from
  git tags via `uv-dynamic-versioning`. There is no release number to cite — only the SHA.
  Any PACT lockfile entry for these must record the SHA, not a semver range.
