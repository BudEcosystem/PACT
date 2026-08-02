# PACT research stream: `semantics-others`

**Deep SOURCE audit of AutoGen, OpenAI Agents SDK (Python), Claude Agent SDK (Python),
Anthropic SDK (Python), and the Vercel AI SDK — across nine semantic dimensions,
plus a divergence matrix against Pydantic AI and LangGraph, plus the harness-lowering
seam per SDK.**

Date: 2026-07-26. Author: research subagent. Status: evidence-linked draft for
`10-RESEARCH-*`.

---

## 0. Method, scope, and provenance

### 0.1 What was read

Source only, from the local corpus at
`/home/bud/ditto/agent-inter-op/research/repos/frameworks/`. Every claim below cites
`file:line` against these exact checkouts. Where I read a docstring rather than
executable code, I say so — docstrings are still *source*, but they are a weaker
witness than the code path, and I mark the difference.

| Repo | Commit | Date | Version read |
|---|---|---|---|
| `autogen` | `027ecf0` | 2026-04-06 | `autogen-core` / `autogen-agentchat` 0.4.x line |
| `openai-agents-python` | `c1b4237` | 2026-07-25 | `0.18.3` (`pyproject.toml:` version) |
| `claude-agent-sdk-python` | `f8b9ec9` | 2026-07-25 | `0.2.128`; bundles CLI `2.1.220` |
| `anthropic-sdk-python` | `60c64fb` | 2026-07-24 | `0.120.0` |
| `vercel-ai` | `eb16508` | 2026-07-25 | `ai@7.0.37`, `@ai-sdk/harness@1.0.43` |
| `pydantic-ai` (cross-check) | `ed0f40c` | 2026-07-25 | — |
| `langgraph` (cross-check) | `30c4d58` | 2026-07-25 | — |

### 0.2 The nine dimensions

loop · state · tools · structured output · streaming · HITL · memory · multi-agent ·
model binding. Plus a tenth question the brief asks explicitly: **what is the exact
lowest-level API in each SDK that PACT can drive as a pure model/tool transport?**

### 0.3 Reading convention

- **[V]** = verified by reading the executing code path.
- **[D]** = verified from a source docstring/type annotation only (no execution path read).
- **[I]** = my inference from the two above. Always marked.

---

## 1. AutoGen (`microsoft/autogen`)

### 1.0 Framing finding: the repo is in maintenance mode

`README.md:14` carries a `status-maintenance mode` badge, and `README.md:19-24` states:

> `> **⚠️ Maintenance Mode**`
> `> AutoGen is now in maintenance mode. It will not receive new features or enhancements and is community managed going forward.`
> `> New users should start with [Microsoft Agent Framework]...`

`README.md:216` further restricts contributions to "bug fixes, security patches, and
documentation improvements." The most recent commit on the checkout (`027ecf0`,
2026-04-06) is literally *"Update maintenance mode banner in readme (#7521)"* — i.e.
the repo has been frozen for ~3.5 months while the other four moved daily.

**[V]** This is a first-order input to PACT's adapter roadmap: AutoGen is a *legacy
import target*, not a live export target. See §7.1.

### 1.1 Loop

AutoGen has **two** loops at two layers, and they are not the same abstraction.

**Layer 1 — `autogen-core` actor runtime.** `AgentRuntime`
(`python/packages/autogen-core/src/autogen_core/_agent_runtime.py:22,50`) exposes
`send_message` (direct, RPC-shaped) and `publish_message` (pub/sub over topics). There
is no "agent loop" here at all — it is a message-passing substrate with subscriptions
(`add_subscription`, `:268`). Loop semantics are whatever the agent's message handlers
do.

**Layer 2 — `autogen-agentchat` `AssistantAgent`.** This is the ReAct-ish agent, and
its default is *not* a ReAct loop:

- `agents/_assistant_agent.py:739` — `max_tool_iterations: int = 1`.
- `agents/_assistant_agent.py:1149` — `for loop_iteration in range(max_tool_iterations):`
- `agents/_assistant_agent.py:1252-1256` — on the last iteration it `break`s to the
  summary/reflection step rather than calling the model again.
- `agents/_assistant_agent.py:1305-1317` — after the loop it either runs
  `_reflect_on_tool_use_flow` (one more model call) or `_summarize_tool_use`
  (**no** model call — the tool result string becomes the agent's answer).
- `agents/_assistant_agent.py:738` — `reflect_on_tool_use: bool | None = None`, and per
  `:143-144` **[D]** it defaults to `False` unless `output_content_type` is set.

**[V]** So the *default* AutoGen agent is: one model call → execute tools → return the
formatted tool result as the response, **without the model ever seeing the tool
output**. Every other framework in this study defaults to "loop until the model stops
calling tools." This is the single largest loop-semantics divergence in the set.

Termination at the team layer is a composable predicate algebra:
`base/_termination.py:15` `TerminationCondition`, with `__and__`/`__or__` at `:79,:83`,
and 12 concrete conditions in `conditions/_terminations.py` (`StopMessageTermination`,
`MaxMessageTermination`, `TextMentionTermination`, `FunctionalTermination`,
`TokenUsageTermination`, `HandoffTermination`, `TimeoutTermination`,
`ExternalTermination`, `SourceMatchTermination`, `TextMessageTermination`,
`FunctionCallTermination`, plus And/Or). **[V]** This is the *best* declarative
stop-condition vocabulary of the seven frameworks and is a good source for PACT's
`loop.halt` predicate set.

### 1.2 State

- Per-agent: `base/_chat_agent.py:82,87` — `save_state()`/`load_state()` returning
  `Mapping[str, Any]`.
- Typed state models: `state/_states.py` — `AssistantAgentState`, `TeamState`,
  `BaseGroupChatManagerState` (`message_thread`, `current_turn`),
  `RoundRobinManagerState.next_speaker_index`, `SelectorManagerState.previous_speaker`,
  `SwarmManagerState.current_speaker`, `MagenticOneOrchestratorState`
  (`task/facts/plan/n_rounds/n_stalls`), `SocietyOfMindAgentState`. Each carries
  `type` + `version: str = "1.0.0"` (`state/_states.py:6-10`).
- **Blocking limitation:** `teams/_group_chat/_base_group_chat.py:773-776`:
  > `.. caution:: When calling save_state on a team while it is running, the state may
  > not be consistent and may result in an unexpected state. It is recommended to call
  > this method when the team is not running or after it is stopped.`

  and `load_state` refuses outright while running
  (`_base_group_chat.py:808-809` — `raise RuntimeError("The team cannot be loaded while it is running.")`).

**[V]** AutoGen therefore has **no mid-run checkpoint**. `pause()`/`resume()` exist
(`_base_group_chat.py:657,703`) but they are in-process signals, not durable snapshots.
PACT's `AC-2.6` (kill-and-resume to the same terminal state) cannot be satisfied by
native lowering onto AutoGen.

### 1.3 Tools

- Core tool ABC in `autogen_core/tools`; `ChatCompletionClient.create` takes
  `tools: Sequence[Tool | ToolSchema]` (`models/_model_client.py:216`).
- `Workbench` abstraction wraps tool collections (used by `AssistantAgent._call_llm`).
- **Tool results are strings.** `models/_types.py:56-69`:
  ```python
  class FunctionExecutionResult(BaseModel):
      content: str
      name: str
      call_id: str
      is_error: bool | None = None
  ```
  **[V]** There is no image/file/structured tool-result channel. MCP tool results
  carrying `image` or `audio` content blocks, Anthropic `tool_result` blocks containing
  images, OpenAI Agents' `ToolOutputImage`/`ToolOutputFileContent`, and Vercel's
  `ToolResultOutput` `content` variant with `type: 'file'` are all **inexpressible**.
- Parallel tool execution: `agents/_assistant_agent.py:1200-1211` — `asyncio.gather`
  over all calls, unbounded. No concurrency cap knob. **[V]**

### 1.4 Structured output

`ChatCompletionClient.create(json_output: Optional[bool | type[BaseModel]])`
(`models/_model_client.py:217`). At the agent layer, `output_content_type` produces a
`StructuredMessage[T]` (`messages.py:178`) and forces `reflect_on_tool_use=True`
(`agents/_assistant_agent.py:143` **[D]**).

Capability declaration: `ModelInfo` (`models/_model_client.py:164-182`) distinguishes
`json_output` ("JSON mode", `:174-176`) from `structured_output` ("This is different to json_output", `:179-180`), plus
`vision`, `function_calling`, `family`, `multiple_system_messages`. `validate_model_info`
(`:185`) hard-requires `vision/function_calling/json_output/family`.

**[V]** `ModelInfo` is the closest thing in the corpus to PACT's capability vocabulary,
and it is *declared per client instance*, not looked up from a catalogue — i.e. AutoGen
already accepts that capability is a first-class, author-declared property. Useful
precedent for `contract.capabilities`.

### 1.5 Streaming

`ChatCompletionClient.create_stream(...) -> AsyncGenerator[Union[str, CreateResult], None]`
(`models/_model_client.py:242,254`): **plain `str` chunks, terminated by one
`CreateResult`.**

**[V]** There is *no* structured delta stream at the model seam: no tool-call argument
deltas, no reasoning deltas, no content-block start/end, no ids. The agent layer
re-wraps text chunks as `ModelClientStreamingChunkEvent` (`messages.py:529`) and emits
coarse-grained events for everything else: `ToolCallRequestEvent` (`:445`),
`ToolCallExecutionEvent` (`:490`), `ThoughtEvent` (`:545`), `MemoryQueryEvent` (`:517`),
`UserInputRequestedEvent` (`:502`), `SelectSpeakerEvent` (`:559`).

Consequence: **you cannot stream tool arguments incrementally through AutoGen**, and a
PACT IR that models `tool-input-delta` (Vercel) or `response.function_call_arguments.delta`
(OpenAI) has no AutoGen projection. Harness lowering can bypass this only if it also
bypasses `ChatCompletionClient` — which is the transport. Marked `degraded` at best.

### 1.6 HITL

`UserProxyAgent` (`agents/_user_proxy_agent.py:37`) takes `input_func: InputFuncType`
(`:16-18`, sync `Callable[[str], str]` or async `Callable[[str, CancellationToken|None], Awaitable[str]]`)
and **blocks inside the run** waiting for it (`_get_input`, `:186`).

Two hard consequences:
1. `_to_config` explicitly cannot serialize the callback —
   `agents/_user_proxy_agent.py:244-245`:
   ```python
   # TODO: Add ability to serialie input_func
   return UserProxyAgentConfig(name=self.name, description=self.description, input_func=None)
   ```
   Round-tripping a HITL agent through AutoGen's own config format **silently loses the
   human**. **[V]**
2. Combined with §1.2, an approval gate cannot be represented as a durable suspend/resume.
   AutoGen HITL is a live callback only.

There is `_intervention.py` in core (interception handlers on the runtime), which can
drop/modify messages, but it is likewise a live in-process callback, not a resumable state.

### 1.7 Memory

`autogen_core/memory/_base_memory.py:60` — `Memory` ABC with `update_context`,
`query`, `add`, `clear`, `close`. `MemoryContent` (`:26`) is typed by `MemoryMimeType`
(`:13`). Separately, context-window management is `ChatCompletionContext`
(`model_context/_chat_completion_context.py:10`) with concrete
`Unbounded` / `Buffered` / `HeadAndTail` / `TokenLimited` variants, each with
`save_state`/`load_state` (`:66,69`).

**[V]** AutoGen is the only framework in this set that cleanly *separates* long-term
memory (`Memory`) from context-window policy (`ChatCompletionContext`). PACT should copy
this split: `memory:` (retrieval) and `context:` (windowing/compaction) are different
fields with different lifecycles.

### 1.8 Multi-agent

Five built-in topologies in `teams/__init__.py`:
`RoundRobinGroupChat`, `SelectorGroupChat` (LLM picks next speaker),
`Swarm` (handoff-driven), `MagenticOneGroupChat` (ledger/plan orchestrator),
`GraphFlow` + `DiGraph`/`DiGraphBuilder`/`DiGraphNode`/`DiGraphEdge`.

`DiGraphEdge` (`teams/_group_chat/_graph/_digraph_group_chat.py:25`) is the most
declarative topology object in the corpus:
- `condition: Union[str, Callable[[BaseChatMessage], bool], None]` (`:39`) — string ⇒
  substring match on last message; callable ⇒ arbitrary predicate.
- `activation_group: str` (`:48`) and `activation_condition: Literal["all","any"]` (`:58`)
  — i.e. join semantics for fan-in.

**Silent-loss precedent (important for AC-7.1).**
`_digraph_group_chat.py:69-76`:
```python
def _validate_condition(self) -> "DiGraphEdge":
    # Store callable in a separate field and set condition to None for serialization
    if callable(self.condition):
        self.condition_function = self.condition
        # For serialization purposes, we'll set the condition to None
        object.__setattr__(self, "condition", None)
```
with `condition_function: ... = Field(default=None, exclude=True)` (`:47`).
**[V]** A callable edge condition is *silently dropped* on serialize — the exported graph
is a different graph, with no warning. This is exactly the failure mode PACT's `T7` is
designed against, and it is a real, citable instance in a shipped framework.

Handoff semantics: `AssistantAgent` docstring `agents/_assistant_agent.py:171` **[D]** —
"If multiple handoffs are detected, only the first handoff is executed." Enforced at
`_check_and_handle_handoff` (`:1245-1253`), which `return`s immediately after the first.

### 1.9 Model binding

`ChatCompletionClient` is a `ComponentBase` — bound by construction, serialized via
`ComponentModel` (`_component_config.py:18-39`): `{provider, component_type, version,
component_version, description, label, config}`.

`provider` is a **Python import path**, computed from the class
(`_component_config.py:157` `_type_to_provider_str(self.__class__)`), and `load_component`
does `importlib.import_module(module_path)` + `getattr` (`:272-273`), gated by an
allow-list of namespaces (`:258-269`, default `autogen_core|autogen_agentchat|autogen_ext|
autogen_studio|autogenstudio`, extensible via `AUTOGEN_ALLOWED_PROVIDER_NAMESPACES`).
`dump_component` raises on local classes (`:165-166`).

**[V]** AutoGen's declarative format is therefore *a serialisation of a Python object
graph*, exactly as `00-THESIS.md §1.3` characterises framework-native YAML. Import into
PACT is a translation, never an embed (consistent with D15).

### 1.10 Harness-lowering seam — AutoGen

**Seam: `autogen_core.models.ChatCompletionClient`**
(`python/packages/autogen-core/src/autogen_core/models/_model_client.py:209`), specifically
`create()` (`:212`) and `create_stream()` (`:242`).

- Input: `Sequence[LLMMessage]` where `LLMMessage = SystemMessage | UserMessage |
  AssistantMessage | FunctionExecutionResultMessage` (`models/_types.py:80`).
- Tools: `Sequence[Tool | ToolSchema]`, `tool_choice: Tool | "auto"|"required"|"none"`.
- Structured: `json_output: bool | type[BaseModel]`.
- Capability self-report: `model_info` (`:292`), `count_tokens`/`remaining_tokens`
  (`:281,284`).

**Verdict: the seam exists and is clean, but it is lossy in three ways PACT must
account for.**
1. `AssistantMessage.content: Union[str, List[FunctionCall]]` (`_types.py:43`) — text and
   tool calls **cannot coexist** in one assistant message. Anthropic and OpenAI both emit
   interleaved text+tool_use. AutoGen's escape hatch is the side-channel
   `thought: str | None` (`_types.py:47`), documented as "additional text content besides
   function calls." Round-tripping interleaved content through AutoGen re-orders it.
2. `UserMessage.content: Union[str, List[Union[str, Image]]]` (`_types.py:32`) — text and
   image only. **No audio, no video, no document/PDF part.** D16's audio and document
   modalities are inexpressible at this seam.
3. `create_stream` yields bare `str` (§1.5) — no structured deltas.

So: AutoGen harness lowering is **possible but `degraded`** on modality (2/4 of D16),
on interleaving, and on stream granularity. PACT must declare these in the capability
lattice rather than pretend.

---

## 2. OpenAI Agents SDK — Python (`openai/openai-agents-python` 0.18.3)

### 2.1 Loop

Entry: `Runner.run` → `AgentRunner.run` (`src/agents/run.py:455`). The loop is
`while True:` at `run.py:789`, with `current_turn += 1` at `:1100` and
`MaxTurnsExceeded` at `:1101-1125` (interestingly, `max_turns` exceeded is *recoverable*
via `error_handlers` — `resolve_run_error_handler_result` at `:1117`, which can
synthesize a final output instead of raising).

Each turn produces a `SingleStepResult` whose `next_step` is a 4-way sum
(`run_internal/run_steps.py:156-175`):

```
NextStepHandoff(new_agent) | NextStepFinalOutput(output) | NextStepRunAgain() | NextStepInterruption(interruptions)
```

Loop-exit policy is `Agent.tool_use_behavior` (`agent.py:347-366`), resolved in
`run_internal/turn_resolution.py:678-697`:
- `"run_llm_again"` (default) — tool results go back to the model.
- `"stop_on_first_tool"` — first tool output *is* the final output.
- `StopAtTools{stop_at_tool_names}` — stop when a named tool is called.
- `ToolsToFinalOutputFunction` — arbitrary callable returning `ToolsToFinalOutputResult`
  (`agent.py:74-80`).

`reset_tool_choice: bool = True` (`agent.py:369`) — after a tool call the SDK resets
`tool_choice` to prevent infinite forced-tool loops. **[V]** This is an *implicit loop
mutation* nobody else does; PACT must model it explicitly or the port changes behaviour.

Guardrails are part of the loop, not decoration: input guardrails run only on turn ≤ 1
(`run.py:1221`), and can run in parallel with the first model call
(`run.py:1270` — `parallel_results, turn_result = await asyncio.gather(run_input_guardrails(...), model_task)`),
with cancellation of the model task on tripwire (`run.py:1283-1286`).

### 2.2 State

`RunState` (`src/agents/run_state.py:212`) is a **serialisable, versioned run snapshot**:
- `CURRENT_SCHEMA_VERSION = "1.13"` (`run_state.py:153`), with a
  `SCHEMA_VERSION_SUMMARIES` table asserted complete at import time (`:179-190`).
- `to_json()` emits `"$schemaVersion"` (`:787`); `to_string()`/`from_string()` at
  `:1047,1105`; version rejection at `:2694-2710` with a feature-specific gate
  ("Programmatic Tool Calling requires schema version …").
- The run entry point accepts it directly: `AgentRunner.run(input: str | list[TResponseInputItem] | RunState[TContext])`
  (`run.py:458`), branching on `isinstance(input, RunState)` at `:474`.

**[V]** This is the strongest *portable-ish* resume story of the five: a single JSON blob,
schema-versioned, accepted as run input. But it is an **opaque SDK-internal snapshot** —
3,819 lines of serialisation logic — not a message list. It cannot be authored, diffed, or
regenerated from PACT's IR; PACT can only pass it through.

There is a second, orthogonal state channel: OpenAI **server-managed conversation**
(`conversation_id` / `previous_response_id` / `auto_previous_response_id`), tracked by
`OpenAIServerConversationTracker` (`run.py:1195-1206`). When enabled, local session
persistence is disabled (`run.py:1211` — `session_persistence_enabled = session is not None
and server_conversation_tracker is None`). **[V]** So OpenAI Agents has *three* mutually
constraining history models (local `Session`, server conversation, `RunState`), validated
against each other by `validate_session_conversation_settings` (`run.py:487,517`).

### 2.3 Tools

`tool.py` defines an unusually large closed set of tool kinds:
`FunctionTool` (`:384`), `FileSearchTool` (`:692`), `WebSearchTool` (`:718`),
`ComputerTool` (`:761`), `HostedMCPTool` (`:1006`), `CodeInterpreterTool` (`:1037`),
`ImageGenerationTool` (`:1059`), `LocalShellTool` (`:1086`), `ShellTool` (`:1282`),
`ApplyPatchTool` (`:1337`), `CustomTool`, `ProgrammaticToolCallingTool`.

`FunctionTool` fields worth copying into PACT (`tool.py:389-470`):
- `params_json_schema` + `strict_json_schema: bool = True`
- `is_enabled: bool | Callable[[RunContextWrapper, AgentBase], MaybeAwaitable[bool]]` (`:415`)
  — **dynamic per-run tool exposure**, which is precisely the "curated exposed set"
  strategy lever `00-THESIS.md §7.2` names.
- `tool_input_guardrails` / `tool_output_guardrails` (`:423,426`)
- `needs_approval: bool | Callable[[ctx, params, call_id], Awaitable[bool]]` (`:429`)
- `timeout_seconds` + `timeout_behavior: "error_as_result"|"raise_exception"` (`:441,444`)
- `defer_loading: bool` (`:453`) — hide the definition until tool-search loads it
  (context-budget lever)
- `output_json_schema` (`:464`) — declared tool *output* schema
- `allowed_callers` (`:461`) — which caller may invoke this tool

`ShellTool` has a full sandbox/network policy vocabulary
(`ShellToolContainerNetworkPolicyAllowlist` `:1146`, `...Disabled` `:1154`,
`ShellToolLocalEnvironment` `:1166`, `ShellToolContainerAutoEnvironment` `:1173`) and
skills (`ShellToolLocalSkill` `:1101`, `ShellToolSkillReference` `:1109`,
`ShellToolInlineSkill` `:1125`).

Concurrency: tools run via `asyncio.gather` (`run_internal/tool_execution.py:1828,1944`)
with an optional cap `RunConfig.tool_execution.max_function_tool_concurrency`
(`run_config.py:109`, applied at `tool_execution.py:1507`). **[V]** OpenAI Agents is the
only one of the five with a *declarative* tool-concurrency cap.

### 2.4 Structured output

`Agent.output_type: type[Any] | AgentOutputSchemaBase | None` (`agent.py:334`).
`AgentOutputSchemaBase` (`agent_output.py:16`) is an ABC with `is_plain_text`,
`name`, `json_schema`, `is_strict_json_schema`, `validate_json`.

**[V]** Structured output is a property of the **agent's final output only** — there is no
per-step or per-branch output schema, and no notion of "structured output mode"
(tool-based vs native vs prompted). Compare Pydantic AI, which makes the *mode* explicit
(§6.4). Validation occurs when the run resolves a final output; the loop does not
re-prompt on validation failure at this layer.

### 2.5 Streaming

`StreamEvent = RawResponsesStreamEvent | RunItemStreamEvent | AgentUpdatedStreamEvent`
(`stream_events.py:61`).

- `RawResponsesStreamEvent.data: TResponseStreamEvent` (`stream_events.py:16`), and
  `TResponseStreamEvent = ResponseStreamEvent` from `openai.types.responses`
  (`items.py:82`). **The raw stream is the OpenAI Responses API wire format, verbatim.**
- `RunItemStreamEvent.name` is a closed 10-member literal (`stream_events.py:29-42`):
  `message_output_created, handoff_requested, handoff_occured` *(sic — the misspelling is
  frozen for compatibility, per the inline comment at `:32`)*, `tool_called`,
  `tool_search_called`, `tool_search_output_created`, `tool_output`,
  `reasoning_item_created`, `mcp_approval_requested`, `mcp_approval_response`,
  `mcp_list_tools`.
- `AgentUpdatedStreamEvent.new_agent` (`:55`) — handoff visible in the stream.

**[V]** This is a *two-layer* stream: a provider-shaped raw layer plus an SDK-shaped
semantic layer. PACT's stream IR must be the semantic layer, with the raw layer carried
as an opaque `x-` passthrough — otherwise the IR inherits the OpenAI Responses wire
format, which is exactly the coupling `NG5` forbids.

### 2.6 HITL

Best-in-class among the five, and structurally distinct from everyone else:
- `FunctionTool.needs_approval` (`tool.py:429`), plus `ShellTool.needs_approval` (`:1287`)
  and `ApplyPatchTool.needs_approval` (`:1342`).
- When approval is required the turn resolves to `NextStepInterruption(interruptions:
  list[ToolApprovalItem])` (`run_steps.py:171-176`), the run *returns* with
  `RunResult.interruptions`, and the caller resolves them on the state:
  `RunState.approve(approval_item, always_approve=False)` (`run_state.py:365`) and
  `RunState.reject(...)` (`run_state.py:371`).
- Resume = `Runner.run(agent, run_state)`.
- `RunConfig.tool_execution.pre_approval_tool_input_guardrails` (`run_config.py:116`)
  controls whether input guardrails run *before* the approval pause.

**[V]** Approval state lives in `RunState`, not in the message list. That is a genuine
semantic difference from Vercel (§5.6), and the two cannot be trivially unified.

### 2.7 Memory

`Session` protocol (`memory/session.py:14`): `get_items(limit)`, `add_items`, `pop_item`,
`clear_session`, plus `session_id` and `session_settings`. Implementations:
`SQLiteSession` (`memory/sqlite_session.py`), `OpenAIConversationsSession`
(server-side), `OpenAIResponsesCompactionSession`.

Compaction is an *optional protocol extension*:
`OpenAIResponsesCompactionAwareSession.run_compaction(args)` (`memory/session.py:132-137`)
with `OpenAIResponsesCompactionArgs{response_id, compaction_mode:
"previous_response_id"|"input"|"auto", store, force}` (`:107-128`), detected structurally
by `is_openai_responses_compaction_aware_session` (`:140`).

**[V]** Session is *transcript storage only*. There is no retrieval memory, no semantic
memory, no memory kinds. Any "memory" beyond conversation history must be a tool.

### 2.8 Multi-agent

Two mechanisms, deliberately distinguished (`agent.py:575-580` **[D]**):
1. **Handoff** — `Handoff` (`handoffs/__init__.py:98`) is materialised as a *tool* with
   `tool_name`, `tool_description`, `input_json_schema`, `on_invoke_handoff`. Control
   transfers; the next agent receives the conversation history, subject to
   `HandoffInputFilter: Callable[[HandoffInputData], MaybeAwaitable[HandoffInputData]]`
   (`handoffs/__init__.py:90`). `HandoffInputData` (`:42-88`) carries `input_history`,
   `pre_handoff_items`, `new_items`, `run_context`, `input_items`.
   There is also `RunConfig.nest_handoff_history: bool` (`run_config.py:326`) and
   `handoff_history_mapper` (`:335`) — i.e. handoffs can *rewrite history* into a nested
   summary. **[V]** This is a topology feature disguised as a history filter, and a real
   IR hazard: `SingleStepResult.original_input` is documented as "May be mutated by
   handoff input filters" (`run_steps.py:179-182`).
2. **Agent-as-tool** — `Agent.as_tool(...)` (`agent.py:550`) returns a `FunctionTool`,
   with `custom_output_extractor`, `on_stream` (nested run streaming),
   `run_config`, `max_turns`, `hooks`, `session`, `needs_approval`, `parameters`
   (structured tool input), `input_builder`, `include_input_schema`.

**[V]** There is no supervisor/graph/team object. Topology is expressed *only* as
handoff edges + agent-as-tool nesting. Debate, blackboard, market/auction (AC-5.1) have
no native form.

### 2.9 Model binding

- `Agent.model: str | Model | None` (`agent.py:311`); `RunConfig.model` (`run_config.py:305`)
  overrides.
- `RunConfig.model_provider: ModelProvider = field(default_factory=MultiProvider)`
  (`run_config.py:310`).
- `MultiProvider` routes on a name **prefix** (`models/multi_provider.py:61-72`):
  `openai/` (or bare) → `OpenAIProvider`; `litellm/` → LitellmProvider;
  `any-llm/` → AnyLLMProvider. Custom prefixes via `MultiProviderMap.add_provider` (`:42`).
  `MultiProviderOpenAIPrefixMode = Literal["alias","model_id"]` (`:13`) exists purely to
  disambiguate `openai/gpt-4.1` (route-vs-literal).

**[V]** Prefix-routed model strings are the closest analogue to a PACT model URI. Worth
noting that PACT's `model:` field must be *unambiguous* about this alias-vs-literal
question, which the SDK had to retrofit an enum for.

### 2.10 Harness-lowering seam — OpenAI Agents

**Seam: `agents.models.interface.Model`** (`src/agents/models/interface.py:37`):

```python
async def get_response(self, system_instructions, input, model_settings, tools,
                       output_schema, handoffs, tracing, *, previous_response_id,
                       conversation_id, prompt) -> ModelResponse            # :61
def stream_response(...) -> AsyncIterator[TResponseStreamEvent]              # :96
```
plus `ModelProvider.get_model(model_name) -> Model` (`:138`).

Concrete implementations to imitate: `OpenAIResponsesModel`
(`models/openai_responses.py:409`), `OpenAIChatCompletionsModel`
(`models/openai_chatcompletions.py:51`), with the message translation in
`models/chatcmpl_converter.py` (910 lines).

**Verdict: a real seam, with one important caveat.** It is *not* a pure model transport:
`get_response` accepts SDK-native `Tool`, `Handoff`, and `AgentOutputSchemaBase` objects,
and it speaks the **OpenAI Responses item format** on both sides
(`TResponseInputItem = ResponseInputItemParam`, `TResponseOutputItem = ResponseOutputItem`,
`TResponseStreamEvent = ResponseStreamEvent` — `items.py:76,79,82`).

Two implications:
1. To use openai-agents purely as a transport, PACT must **emit OpenAI Responses items**.
   That is a translation cost, not a blocker.
2. `handoffs` are passed *to the model* as a first-class argument, i.e. the SDK expects
   handoff-as-tool synthesis to happen below the seam. PACT harness lowering should pass
   `handoffs=[]` and synthesize handoff tools itself, so PACT owns the routing semantics
   (D12). **[I]** — I did not find a code path that forbids this, but I also did not test it.

There is also a *lower* seam if the model layer is too coupled: the SDK's dependency
`openai` client itself. But then you are no longer using openai-agents at all, which
would violate the point of the adapter.

---

## 3. Claude Agent SDK — Python (`anthropics/claude-agent-sdk-python` 0.2.128)

### 3.0 Framing finding: this SDK is a CLI client, not an agent framework

`_internal/transport/subprocess_cli.py:463`:
```python
cmd = [self._cli_path, "--output-format", "stream-json", "--verbose"]
```
`:663` adds `--input-format stream-json`. `_find_cli` (`:150`) searches `shutil.which("claude")`
(`:159`) and a fixed list of install paths (`:194-199`), preferring a **bundled binary**
`_bundled/claude` (`:236-247`). `_cli_version.py:3` — `__cli_version__ = "2.1.220"`.

**[V] The agent loop, the built-in tools (Bash/Read/Edit/…), context compaction, subagent
spawning, permission evaluation, and model calling all live inside the closed-source
`claude` binary.** The Python package is a control-protocol client.

### 3.1 Loop

Not observable in this repo. Loop configuration is expressed as CLI options:
`ClaudeAgentOptions.max_turns` (`types.py:1834`), `max_budget_usd` (`:1840`),
`permission_mode` (`:1810`), `thinking` (`:2048`), `effort` (`:2061`),
`task_budget` (`:2119`). Loop *outcome* is reported via
`ResultMessage.terminal_reason` (`types.py:1249-1257`) with values like `"completed"`,
`"max_turns"`, `"aborted_streaming"`, `"aborted_tools"`, and `num_turns` (`:1232`).

**[V]** PACT cannot own the loop here (D12 violated by construction).

### 3.2 State

Sessions are the state model, and they are *files on disk plus an optional mirror*:
- `resume: str | None` (session id), `continue_conversation`, `fork_session`,
  `session_id` (`types.py:1820-1832`).
- `session_store: SessionStore | None` (`types.py:2092`) — "every transcript line written
  locally is also passed to `session_store.append()`, and `resume` can materialize from
  the store when the local file is absent." With `session_store_flush:
  "batched"|"eager"` (`:2100`) and `load_timeout_ms: int = 60_000` (`:2110`).
- Session manipulation helpers exported at `__init__.py:29-52`: `fork_session`,
  `rename_session`, `tag_session`, `delete_session`, `import_session_to_store`,
  `list_sessions`, `get_session_messages`, `get_subagent_messages`, `list_subagents`,
  `fold_session_summary`, plus `InMemorySessionStore` and a
  `testing/session_store_conformance.py` suite.
- `enable_file_checkpointing: bool` (`types.py:2084`) + `ClaudeSDKClient.rewind_files`
  (`client.py:374`) — **filesystem** rollback to a user message, not conversation rollback.

**[V]** This is the only SDK of the five with first-class *session forking* and a
pluggable durable transcript store with a published conformance suite. That is a strong
model for PACT's run ledger, and worth mining independently of the adapter question.

### 3.3 Tools

Three disjoint tool populations:
1. **Built-in CLI tools** — selected by name: `tools: list[str] | ToolsPreset | None`
   (`types.py:1763`), narrowed by `allowed_tools` (`:1774`) / `disallowed_tools` (`:1847`).
   Their implementations are in the binary.
2. **MCP servers** — `mcp_servers: dict[str, McpServerConfig] | str | Path`
   (`types.py:1796`) where `McpServerConfig = McpStdio|McpSSE|McpHttp|McpSdkServerConfig`
   (`types.py:637`).
3. **In-process SDK tools** — `@tool(name, description, input_schema, annotations)`
   (`__init__.py:171`) + `create_sdk_mcp_server(...)` → `McpSdkServerConfig(type="sdk",
   name=..., instance=server)` (`__init__.py:525`). These are **MCP tools in-process**;
   the model sees them under MCP naming.

Tool handler contract (`__init__.py:213-216` **[D]**): async, single dict arg, returns
`{"content": [...], "is_error"?: bool}` — i.e. MCP `CallToolResult` shape, so image/audio
tool results *are* expressible here (unlike AutoGen).

### 3.4 Structured output

`ClaudeAgentOptions.output_format: dict[str, Any] | None` (`types.py:2076`) —
"Matches the Messages API structure, e.g. `{"type": "json_schema", "schema": {...}}`".
Result surfaces as `ResultMessage.structured_output: Any` (`types.py:1237`).

**[V]** Schema-only, no Python type binding, no validation in the SDK, no repair loop.

### 3.5 Streaming

Default granularity is **whole messages**: `AssistantMessage`, `UserMessage`,
`SystemMessage`, `ResultMessage` (`types.py:1351-1358`).
Token-level streaming is opt-in: `include_partial_messages: bool = False`
(`types.py:1963`), which emits `StreamEvent{uuid, session_id, event: dict[str, Any],
parent_tool_use_id}` (`types.py:1261-1266`) where `event` is documented as
"The raw Anthropic API stream event" (`:1265`).

Also `include_hook_events: bool` (`types.py:1969`) surfacing `HookEventMessage` (`:1318`).

**[V]** Streaming here is *raw provider events wrapped in an envelope* — no SDK-level
semantic delta vocabulary. Same shape as OpenAI Agents' raw layer, without the semantic
layer.

### 3.6 HITL

Three distinct mechanisms, all live callbacks over the control protocol:
1. `can_use_tool: CanUseTool | None` (`types.py:1929`) — invoked only when the CLI's
   permission rules evaluate to *ask*. Explicitly documented as **not** invoked when
   `allowed_tools`/`permission_mode`/settings already allow the call (`:1933-1936`), and a
   `CanUseToolShadowedWarning` is raised when the configuration visibly shadows it (`:1937`).
2. `hooks: dict[HookEvent, list[HookMatcher]]` (`types.py:1947`) — `PreToolUse`,
   `PostToolUse`, `PostToolUseFailure`, `PreCompact`, `Notification`, `PermissionRequest`,
   `Stop`, … Critically, `types.py:1953-1957` **[D]**: "multiple matchers registered on the
   same event are dispatched **concurrently** by the CLI — … Design each hook to be
   independent; do not rely on one completing before another starts." **[V]** Hook
   *ordering is not defined*. PACT's guardrail/hook IR assumes ordering; that assumption
   does not survive here.
3. `PreToolUse` returning `permissionDecision: "defer"` → run stops and
   `ResultMessage.deferred_tool_use: DeferredToolUse{id, name, input}`
   (`types.py:1187-1197,1242`). This is the only *suspend-and-report* path, and it is
   coarse (one deferred call, whole-run stop).

Runtime controls on the live client: `interrupt()` (`client.py:317`),
`set_permission_mode(mode)` (`:323`), `set_model(model)` (`:350`),
`stop_task(task_id)` (`:454`).

### 3.7 Memory

- Session transcripts (§3.2) are the conversation memory.
- `AgentDefinition.memory: Literal["user","project","local"] | None` (`types.py:95`) —
  a scope selector for the CLI's own memory (CLAUDE.md-family), not a store interface.
- Context accounting is queryable: `get_context_usage()` (`client.py:510`) →
  `ContextUsageResponse` / `ContextUsageCategory`.
- Compaction is a *hook event* (`PreCompactHookInput`), not a configurable policy.

**[V]** No pluggable memory backend, no retrieval interface.

### 3.8 Multi-agent

`agents: dict[str, AgentDefinition] | None` (`types.py:1981`), where `AgentDefinition`
(`types.py:84-102`) is:
```
description, prompt, tools?, disallowedTools?, model?, skills?, memory?,
mcpServers?, initialPrompt?, maxTurns?, background?, effort?, permissionMode?
```
Subagents are invoked by the model through the built-in Agent/Task tool; the SDK can read
their transcripts (`get_subagent_messages`, `list_subagents` — `__init__.py:46,51`).
`task_progress` / `task_notification` message subtypes and `stop_task` (`client.py:454`)
give background-task control.

**[V]** Topology is **supervisor-with-subagents, depth-1, model-driven**. There is no
edge/graph vocabulary, no explicit routing, no swarm, no debate.

### 3.9 Model binding

`ClaudeAgentOptions.model: str | None` (`types.py:1854`) — model *alias or id* string.
`fallback_model: str | None` (`:1860`). Per-subagent `AgentDefinition.model` accepts
`"sonnet"|"opus"|"haiku"|"inherit"` or a full id (`types.py:92-93`).
Runtime switch: `ClaudeSDKClient.set_model()` (`client.py:350`).

**[V]** No model object, no base-URL parameter, no provider abstraction. Redirection is
only possible out-of-band through `env: dict[str,str]` (`types.py:1903`) — i.e. setting
`ANTHROPIC_BASE_URL`-style variables on the subprocess. **[I]** I did not find any code
in this repo that reads such a variable; it would be consumed by the binary.

### 3.10 Harness-lowering seam — Claude Agent SDK: **NONE. This is a blocking finding.**

There is exactly one abstraction below the client: `Transport`
(`_internal/transport/__init__.py:9`) with `connect()`, `write(data: str)`,
`read_messages() -> AsyncIterator[dict]`, `close()`, `is_ready()`. Its own docstring
(`:11-14`) says:

> `WARNING: This internal API is exposed for custom transport implementations (e.g.
> remote Claude Code connections). The Claude Code team may change or remove this
> abstract class in any future release.`

Implementing `Transport` does **not** give you a model/tool transport — it makes you
responsible for *speaking the Claude Code control protocol*: `SDKControlRequest`
subtypes `initialize`, `interrupt`, `can_use_tool`, `hook_callback`, `mcp_message`,
`set_permission_mode`, `rewind_files`, `mcp_reconnect`, `mcp_toggle`, `stop_task`
(`types.py:2130-2226`), plus the full `stream-json` message grammar. In other words:
**to harness-lower onto this SDK you would have to reimplement Claude Code.**

Consequences for PACT:
1. `AC-2.2` / `P-2` ("every adapter implements harness lowering") **cannot be satisfied**
   for `claude-agent-sdk` as such.
2. `D17` (fully air-gapped) is at best conditional: the pipeline depends on a bundled
   proprietary binary (`_bundled/claude`, version pinned at `_cli_version.py:3`) plus an
   Anthropic-API-compatible endpoint.
3. `D15` ("translate or nothing — no opaque wrapping") is directly in tension with
   targeting this SDK at all: any adapter here is, by construction, opaque wrapping of a
   binary.

**Recommended resolution (see §7.2): retarget the "Anthropic" adapter from
`claude-agent-sdk` to `anthropic-sdk-python`, which does expose a real seam (§4.10), and
reclassify `claude-agent-sdk` as a *session-level host*, not a lowering target.**

Vercel independently reached the same conclusion and named the category — see §5.10.

---

## 4. Anthropic SDK — Python (`anthropics/anthropic-sdk-python` 0.120.0)

This is a provider SDK, but 0.120.0 ships three distinct agentic layers, and they have
*different* semantics. All three matter.

### 4.1 Loop

**(a) Messages tool runner** — `client.beta.messages.tool_runner(...)`
(`src/anthropic/resources/beta/messages/messages.py:1433` sync / `:3450` async).
The loop is `BaseSyncToolRunner.__run__` (`lib/tools/_beta_runner.py:272`):

```python
while not self._should_stop():                    # :272
    with self._handle_request() as item: ...      # one messages.parse / messages.stream
    self._iteration_count += 1                    # :285
    if message.stop_reason == "refusal": return   # :290-292
    if not self._check_and_compact():             # :295
        response = self.generate_tool_call_response()
        if response is None: return               # :297-299  (no tool_use ⇒ done)
        if not self._messages_modified:
            self.append_messages(message, response)
```
`_should_stop` is *only* `max_iterations` (`:125-129`); there is no stop-condition
vocabulary.

Notable: a **refusal stop_reason is terminal** and its `tool_use` blocks are deliberately
*not* executed (`:288-292`, with the rationale in the comment: "executing their tool_use
blocks would fire side effects the model never confirmed"). **[V]** No other framework in
this set models refusal as a distinct terminal condition. PACT's loop IR should.

**(b) Managed-agents session runner** — `SessionToolRunner`
(`lib/tools/_beta_session_runner.py:353`). Here the loop runs **server-side**; the client
subscribes to the session event stream, dispatches `agent.tool_use` /
`agent.custom_tool_use` events against a local registry, posts back
`user.tool_result` / `user.custom_tool_result`, and stops after `max_idle` seconds of
`stop_reason == "end_turn"` (`:917` `_idle_watchdog`). Module docstring `:1-15`.

**(c) Managed Agents resource** — `client.beta.agents.create(...)` with
`AgentCreateParams` (`types/beta/agent_create_params.py:23`), a *server-hosted agent
definition*. See §4.8.

### 4.2 State

- Messages runner: state is **the message list**, held in `self._params["messages"]`,
  mutable from outside via `append_messages` (`_beta_runner.py:111`) and
  `set_messages_params` (`:96`, accepts a mutator function). Fully transparent, fully
  serialisable, no opaque snapshot.
- Session runner: state is server-side; the client `_reconcile`s against the events-list
  endpoint on reconnect (`_beta_session_runner.py:553`).
- Context management is declared, not implemented client-side:
  `context_management: BetaContextManagementConfigParam` and
  `compaction_control: CompactionControl` (`lib/tools/_beta_compaction_control.py`),
  with `_check_and_compact` at `_beta_runner.py:188` (sync) / `:477` (async).

**[V]** The Messages tool runner has the **most portable state model of all seven
frameworks**: nothing exists outside the message array. This is the model PACT should
adopt as its canonical run state, with adapters projecting into their own snapshots.

### 4.3 Tools

- `beta_tool(func)` / `@beta_tool` and async variants (`lib/tools/_beta_functions.py`),
  producing `BetaRunnableTool` / `BetaAsyncRunnableTool`.
- Raw `BetaToolUnionParam` definitions can be mixed in; an unmatched tool name produces a
  `UserWarning` and an `is_error` tool_result telling you to handle it manually
  (`_beta_runner.py:355-366`). **[V]** The runner degrades loudly, not silently — good
  precedent.
- Mid-conversation tool mutation: `BetaRequestToolAdditionBlockParam` /
  `BetaRequestToolRemovalBlockParam` are content blocks
  (`types/beta/beta_content_block_param.py:57-58`), and the runner computes the live set
  via `_available_tool_names` (`_beta_runner.py:130-140`), noting that removal is "only a
  hint to the model." **[V]** Dynamic tool exposure is expressed *in the transcript* here,
  not as a callback. That is an important third option alongside OpenAI's `is_enabled`
  callback and Vercel's `activeTools`.
- MCP: `lib/tools/mcp.py` (client-side) and `mcp_servers: Iterable[BetaRequestMCPServerURLDefinitionParam]`
  (server-side connector) in the `tool_runner` signature.
- Reference "agent toolset": `beta_agent_toolset_20260401` → bash/read/write/edit/glob/grep
  (`lib/tools/agent_toolset.py:1-32`), with an explicit trust model: file tools confine to
  `workdir` symlink-aware; `bash` is unrestricted and "should run inside" a sandbox (`:30-32`).
  Also an explicit resource-leak warning: the Messages tool runner never calls `close`, so
  handing it the stateful `bash` tool "leaks the bash subprocess (one orphaned shell per
  run)" (`agent_toolset.py:20-28`). **[V]**

**Tool concurrency: strictly sequential.** `_generate_tool_call_response` iterates
`for tool_use in tool_use_blocks:` at `_beta_runner.py:342` (sync) and `:651` (async) — the
async path `await`s each tool in turn, with no `gather`. **[V]** A model that emits four
parallel tool calls has them executed serially. This is a *measurable* latency divergence
from OpenAI Agents (`asyncio.gather`, `tool_execution.py:1828`) and Vercel
(`Promise.all`, `generate-text.ts:1515`).

### 4.4 Structured output

`output_format: Optional[type[ResponseFormatT]]` on `tool_runner` and `messages.parse`,
lowered to `output_config.format = BetaJSONOutputFormatParam{type:"json_schema", schema}`
(`types/beta/beta_json_output_format_param.py:11-15`,
`types/beta/beta_output_config_param.py:18-22`). Parsing happens in
`lib/_parse/_response.py:16-34` — `parse_text` uses a pydantic `TypeAdapter` and attaches
`parsed_output` onto text blocks.

`BetaOutputConfigParam` also carries `effort: "low"|"medium"|"high"|"xhigh"|"max"` and
`task_budget` — i.e. **output config and reasoning-effort/budget share one object**.
**[I]** PACT should keep them separate; conflating them is a provider artifact.

### 4.5 Streaming

`lib/streaming/_beta_types.py` defines a semantic event layer on top of raw SSE:
`ParsedBetaTextEvent` (`:21`), `BetaCitationEvent` (`:34`), `BetaThinkingEvent` (`:44`),
`BetaSignatureEvent` (`:54`), `BetaInputJsonEvent` (`:61`), `BetaCompactionEvent` (`:78`),
plus parsed `content_block_stop` / `message_stop` (`:88,94`).

**[V]** Tool-input streaming exists (`BetaInputJsonEvent`), citations stream as first-class
events, and *compaction is a stream event* — a lifecycle signal no other SDK surfaces
in-band.

### 4.6 HITL

- **Messages tool runner: none.** The loop executes every tool call it can resolve. Any
  approval gate must be implemented by the caller inside the tool function or by driving
  the iterator manually (`generate_tool_call_response()` is public — `_beta_runner.py:316`
  — so a caller *can* interpose). **[V]** But there is no declarative approval concept.
- **Session runner: server-mediated.** A call whose `evaluated_permission` is `ask` is
  held until a `user.tool_confirmation` event arrives — executed on `allow`, never on
  `deny` (`_beta_session_runner.py:8-11` **[D]**; enforced at `_note_confirmation` `:722`,
  `_apply_verdict` `:734`, `_resolve_denied` `:756`).

### 4.7 Memory

- `anthropic/tools/memory.py` + `lib/tools/_beta_builtin_memory_tool.py` (910 lines) —
  the Anthropic **memory tool** (a file-backed memory directory the model manipulates
  through tool calls).
- `lib/sessions/_accumulate.py` — event-stream → message accumulation.
- Context/compaction as above (§4.2).

**[V]** Memory here is a *tool*, not a framework subsystem. That is a legitimate design
choice PACT should be able to express: `memory:` may lower to a tool.

### 4.8 Multi-agent

Server-side only, via Managed Agents. `AgentCreateParams`
(`types/beta/agent_create_params.py:23-70`): `model` (string or `model_config` object),
`name`, `description`, `mcp_servers` (max 20), `metadata`, `multiagent`, `skills`,
`system`, `tools` (max 128 across all toolsets).

`BetaManagedAgentsMultiagentParams` (`types/beta/beta_managed_agents_multiagent_params.py:13-30`):
```
type: Literal["coordinator"]
agents: 1–20 entries — agent id | {"type":"agent","id","version"} | {"type":"self"}
```
with the constraint, verbatim (`:22-28`): referenced agents "must not themselves have
`multiagent` set (**depth limit 1**)"; at most one `self`.

**[V]** Two findings:
1. Anthropic's Managed Agents API is itself a *competing agent-definition format* with
   model, system, tools, skills, MCP servers, versioning (`beta/agents/versions.py`), and a
   topology field. PACT must be able to **project onto it** (an export target alongside
   A2A/OSSA), and its field set is a good superset check for `contract`+`strategy`.
2. **Depth limit 1** directly contradicts PACT `G-4` (recursive composition, "any topology
   may be exposed as an agent"). Any PACT topology deeper than supervisor→specialist is
   `unsupported` on this substrate and must be reported, not flattened silently.

### 4.9 Model binding

`model: ModelParam` per request (`tool_runner` signature). `fallbacks:
BetaFallbacksParam` and `fallback_credit_token` are request-level parameters — i.e.
**model fallback is a provider feature here**, not an SDK loop feature. Also
`service_tier: "auto"|"standard_only"`, `speed: "standard"|"fast"`, `inference_geo`.

**[V]** `inference_geo`, `service_tier`, and `speed` are exactly the kind of
substrate-level SLO knobs `D16`/`O4.2` need a home for. PACT's `substrate`/`profile`
should have a place for provider routing hints that are neither capability nor cost.

### 4.10 Harness-lowering seam — Anthropic SDK

**Seam (best): `client.beta.messages.create/stream/parse`** — the Messages API itself.
Concretely, for a PACT harness, the pair to drive is:
- `client.beta.messages.parse(**params)` (used at `_beta_runner.py:701`), and
- `client.beta.messages.stream(**params)` (used at `_beta_runner.py:710`).

This is a **pure model transport**: messages in, content blocks out, tools as JSON
schemas, `tool_choice`, `output_config.format` for structured output, `thinking` config,
`context_management`. PACT owns the loop entirely.

**Second seam (if you want the SDK's loop): `BaseToolRunner`** — `set_messages_params`
(`:96`), `append_messages` (`:111`), `generate_tool_call_response` (`:316`) are all public
and the runner is an iterator, so a PACT harness *can* drive it step-by-step and interpose
approvals/guardrails between steps. **[I]** Plausible from the API shape; not exercised.

**Verdict: cleanest seam of the five.** No SDK-native tool/handoff/output objects leak into
it — everything is JSON-schema and wire types.

**Modality caveat.** `BetaContentBlockParam`
(`types/beta/beta_content_block_param.py:36-61`) admits text, image, document (PDF),
search-result, thinking, tool-use/result, server-tool results, MCP blocks, container
upload, compaction, mid-conversation system, tool addition/removal, fallback. A grep of
`src/anthropic/types/beta/` for `audio|speech|voice|video` returns **nothing**. **[V]**
Anthropic has **no audio input modality**. D16's audio/voice modality cannot be lowered
natively here; it must become STT→text→TTS with the speech models supplied by another
provider. PACT's capability lattice must express that as `emulated`, and the SLO model must
account for the added TTFT.

---

## 5. Vercel AI SDK (`vercel/ai`, `ai@7.0.37`)

### 5.1 Loop

`ToolLoopAgent` (`packages/ai/src/agent/tool-loop-agent.ts:38`) delegates to
`generateText` / `streamText`. Its class docstring (`:28-37`) states the loop continues
until:
- a finish reason other than `tool-calls`, **or**
- a tool that is invoked has no `execute` function, **or**
- a tool call needs approval, **or**
- a stop condition is met (default `isStepCount(20)`).

The actual continue-predicate is `generate-text.ts:1365-1374`:
```ts
} while (
  ((clientToolCalls.length > 0 &&
    clientToolOutputs.length + deniedToolApprovalResponses.length === clientToolCalls.length)
   || pendingDeferredToolCalls.size > 0) &&
  !(await isStopConditionMet({ stopConditions, steps }))
);
```
**[V]** Note the loop does **not** test `finishReason` directly — it tests "were there
client tool calls, and did every one of them resolve to an output or a denial?" A tool
without `execute`, or one awaiting approval, leaves the counts unequal and exits the loop.
This is a materially different termination rule from every other framework and is the
mechanism behind both HITL and "client-side tools."

Stop conditions are composable data: `StopCondition` (`stop-condition.ts:14-19`),
`isStepCount(n)` (`:27`), `isLoopFinished()` (`:37`), `hasToolCall(...names)` (`:47`),
`isStopConditionMet` = OR over the array (`:64-76`).

**`prepareStep` is the loop-engineering hook** (`prepare-step.ts:33-93`): per-step it
receives `{steps, stepNumber, model, instructions, initialInstructions, messages,
initialMessages, responseMessages, toolsContext, runtimeContext, sandbox}` and may return
overrides for `model`, `toolChoice`, `activeTools`, `toolOrder`, `instructions`,
`messages`, `toolsContext`, `runtimeContext`, `sandbox`, `providerOptions`
(`prepare-step.ts:100-176`). Overrides for `instructions` and `messages` **carry forward**
to later steps (`:126,133`).

**[V]** `prepareStep` alone can express model-switching mid-loop, tool-set narrowing,
history rewriting, and per-step system prompts — i.e. most of PACT's loop IR, as a
callback. It is the single best *native lowering target* for `loop.yaml` in the corpus.

### 5.2 State

State is **the message array plus `steps`**. `StepResult` accumulates per step;
`responseMessages` accumulate into `messagesForNextStep` (`generate-text.ts:1349-1350`).
There is no opaque snapshot object.

Durability is a *separate package*: `@ai-sdk/workflow`'s `WorkflowAgent`
(`packages/workflow/src/workflow-agent.ts:1185` **[D]** — "A class for building durable AI
agents within workflows"), which reimplements the step loop against the same primitives
imported from `ai/internal` (`workflow-agent.ts:38-46`: `collectToolApprovals`,
`convertToLanguageModelPrompt`, `standardizePrompt`, `validateApprovedToolApprovals`, …).

**[V]** Durability is *not* in the agent abstraction — it is a parallel implementation.
That is a real risk for PACT's `P-5`: choosing `ToolLoopAgent` vs `WorkflowAgent` changes
which code path runs, and they can diverge (the repo has
`workflow-agent-compat.test.ts` precisely to police this).

Context pruning is a pure function over messages: `pruneMessages({messages, reasoning:
'all'|'before-last-message'|'none', toolCalls: 'all'|'before-last-message'|
'before-last-N-messages'|'none'| [{type, tools?}], emptyMessages: 'keep'|'remove'})`
(`packages/ai/src/generate-text/prune-messages.ts:17-34`).
**[V]** This is the most *declarative* context-management policy in the corpus and maps
almost 1:1 onto a PACT `context:` block. Recommend adopting the vocabulary.

### 5.3 Tools

`Tool` (`packages/provider-utils/src/types/tool.ts:328`), built from `BaseTool` (`:56`):
`inputSchema` (`:93`), `outputSchema`/`execute` (mutually shaped by `ToolOutputProperties`
`:18-50` — **if you omit `execute` you must declare `outputSchema`**), `contextSchema`
(`:99`), `description` (static or `(options:{context}) => string`, `:189-193`),
`providerOptions` (`:73`), `metadata` (not sent to the model, `:82`),
`toModelOutput` (`:149`), `onInputStart`/`onInputDelta`/`onInputAvailable` (`:118,126,136`),
and tool kinds `type?: 'function' | 'dynamic' | 'provider'` (`:226,240,251`).

`ToolResultOutput` (`packages/provider-utils/src/types/content-part.ts:247-340`):
`text | json | execution-denied{reason} | error-text | error-json | content[]`, where
`content[]` items are `text` or `file{data: FileData, mediaType}` with `FileData` =
`{type:'data'} | {type:'url'} | {type:'reference'} | {type:'text'}` (`:322-330`).

**[V]** This is the richest tool-result content model of the five: typed errors, an
explicit `execution-denied` variant, and multimodal file results with IANA media types
and provider references (uploaded files).

Concurrency: `Promise.all` over tool calls (`generate-text.ts:1515-1518`), unbounded.

Repair and refinement: `repairToolCall: ToolCallRepairFunction`
(`tool-loop-agent-settings.ts:145`) and `experimental_refineToolInput: ToolInputRefinement`
(`:160`). **[V]** Tool-call repair as a first-class loop concept exists only here and (in
a different form) in Pydantic AI's retry/`ModelRetry`.

### 5.4 Structured output

`Output` interface (`packages/ai/src/generate-text/output.ts:21-56`):
`name`, `responseFormat`, `parseCompleteOutput`, `parsePartialOutput`,
`createElementStreamTransform`. Built-ins: `text()` (`:65`), `object()` (`:92`),
`array()` (`:196`), `choice()` (`:384`), `json()` (`:523`).

**[V]** `Output` is a *pluggable* structured-output strategy with **partial parsing** —
`parsePartialOutput` + `parsePartialJson` gives streaming structured output, and
`array()` + `createElementStreamTransform` gives element-at-a-time streaming. Nothing else
in the corpus streams partial structured output. `choice()` (constrained enum output) is a
directly useful primitive for PACT's small-model story (`00-THESIS.md §7.3 item 5`).

### 5.5 Streaming

Three stacked layers:
1. **Provider layer** — `LanguageModelV4StreamPart`
   (`packages/provider/src/language-model/v4/language-model-v4-stream-part.ts:14-110`):
   `text-start|text-delta|text-end`, `reasoning-start|delta|end`,
   `tool-input-start|tool-input-delta|tool-input-end`, `tool-approval-request`,
   `tool-call`, `tool-result`, custom content, file, reasoning-file, source,
   `stream-start{warnings}`, `response-metadata`, `finish{usage,finishReason}`,
   `raw{rawValue}` (opt-in via `includeRawChunks`), `error`.
2. **Core layer** — `streamText` step events, `smoothStream`, `StreamTextTransform`.
3. **UI layer** — `packages/ai/src/ui/`: `ui-message-stream`, `process-ui-message-stream`,
   chat transports (`http-chat-transport.ts`, `direct-chat-transport.ts`,
   `text-stream-chat-transport.ts`), and resume predicates
   (`last-assistant-message-is-complete-with-tool-calls.ts`,
   `last-assistant-message-is-complete-with-approval-responses.ts`).

**[V]** Layer 1 is the best candidate for PACT's canonical stream IR: it is
provider-neutral, id-correlated (every part carries a block `id`), covers reasoning and
tool-input deltas, and keeps raw provider bytes in an explicitly-opt-in `raw` variant
rather than as the substrate.

### 5.6 HITL

**Approvals are message content, not run state.** This is the key architectural difference.

- Request: `LanguageModelV4ToolApprovalRequest{type:'tool-approval-request', approvalId,
  toolCallId, providerMetadata}`
  (`packages/provider/src/language-model/v4/language-model-v4-tool-approval-request.ts:9-27`)
  — a stream part *and* implicitly a content part.
- Response: `LanguageModelV4ToolApprovalResponsePart{type:'tool-approval-response',
  approvalId, approved: boolean, reason?}`, (`language-model-v4-prompt.ts:259-282`), allowed **only in a `role:'tool'` message**
  (`language-model-v4-prompt.ts:44-49`).
- Policy: `ToolApprovalConfiguration`
  (`packages/ai/src/generate-text/tool-approval-configuration.ts:111-127`) — either one
  generic function over `{toolCall, tools, toolsContext, runtimeContext, messages}` or a
  per-tool map to `ToolApprovalStatus` = `'not-applicable'|'approved'|'denied'|
  'user-approval'` (or object form with `reason`) (`:25-34`).
- Denial produces a tool result of `{type:'execution-denied', reason}` (§5.3), so the model
  *sees* the denial.
- Tamper-resistance is explicit: `tool-approval-signature.ts`,
  `validate-tool-approvals.ts`, and the comment at `generate-text.ts:363` about "preventing
  client-forged approvals."
- The per-tool `Tool.needsApproval` is **deprecated** in favour of the call-level config
  (`tool.ts:103-107`).

**[V]** Because approval state lives in the transcript, resume is "append a message and
call again" — no snapshot, no checkpointer, no session id. **This is the model PACT should
adopt**, because it is the only one that survives the Expansion Rule (T5): a transcript is
data an author can read, diff, and hand-write; a `RunState` blob is not.

### 5.7 Memory

**None.** There is no memory abstraction in `packages/ai/src`. Conversation state is the
caller's message array; the only built-in policy is `pruneMessages` (§5.2). Persistence is
the app's job (the `ui` package's chat transports assume a server holds messages).

**[V]** Negative finding: a PACT `memory:` block has *no* native lowering on Vercel and must
always be realised as harness-side machinery or as tools.

### 5.8 Multi-agent

**None.** `grep -rl "handoff|Handoff|subagent|Subagent" packages/ai/src --include=*.ts`
(excluding tests) returns **no files**. `packages/ai/src/agent/index.ts` exports only
`Agent`, `ToolLoopAgent`, settings types, and UI-stream helpers — **no `asTool` helper**.

**[V]** Multi-agent on Vercel is: wrap an `Agent` in `tool({inputSchema, execute})` by hand.
Every topology in `AC-5.1` must therefore be synthesised by PACT's harness. Native lowering
of topology is `unsupported` for this adapter, full stop.

(There is a coordinator-ish shape in `packages/workflow`, but it is workflow orchestration,
not agent topology.)

### 5.9 Model binding

`LanguageModel = string | LanguageModelV2|V3|V4` (`packages/ai/src/types/language-model.ts`).
Resolution: `resolveLanguageModel` (`packages/ai/src/model/resolve-model.ts:29-43`):
```ts
if (typeof model === 'string') return getGlobalProvider().languageModel(model);
```
and `getGlobalProvider()` (`:181-184`):
```ts
const provider = globalThis.AI_SDK_DEFAULT_PROVIDER ?? gateway;
```
i.e. **a bare model-id string resolves against Vercel's hosted AI Gateway by default**
(`packages/ai/src/global.ts` documents this: "If not set, the default provider is the
Vercel AI gateway provider").

**[V] Air-gap consequence (D17):** a PACT/Vercel adapter must *never* pass a model id
string without first setting `globalThis.AI_SDK_DEFAULT_PROVIDER`, or it will attempt a
network call to `gateway.ai.vercel.sh`. This should be an assertion in the adapter, and a
line item in the offline conformance test (`AC-7.3`).

Middleware: `wrapLanguageModel` + `defaultSettingsMiddleware`, `extractReasoningMiddleware`,
`extractJsonMiddleware`, `simulateStreamingMiddleware`, `addToolInputExamplesMiddleware`
(`packages/ai/src/middleware/`). **[V]** `simulateStreamingMiddleware` is a capability
*shim* — it makes a non-streaming model satisfy a streaming contract. That is exactly the
"emulated" tier of PACT's capability lattice, implemented as a decorator. Strongly worth
copying as a pattern.

### 5.10 Harness-lowering seam — Vercel AI SDK, and the `HarnessV1` precedent

**Seam: `LanguageModelV4`** (`packages/provider/src/language-model/v4/language-model-v4.ts:8-59`; `doGenerate` `:46`, `doStream` `:58`):
```ts
readonly specificationVersion: 'v4';
readonly provider: string;
readonly modelId: string;
supportedUrls: PromiseLike<Record<string, RegExp[]>> | Record<string, RegExp[]>;
doGenerate(options: LanguageModelV4CallOptions): PromiseLike<LanguageModelV4GenerateResult>;   // :46
doStream(options: LanguageModelV4CallOptions): PromiseLike<LanguageModelV4StreamResult>;       // :58
```
`LanguageModelV4CallOptions` (`language-model-v4-call-options.ts:8-138`) carries
`prompt`, sampling params, `responseFormat: {type:'text'} | {type:'json', schema?, name?, description?}`,
`tools`, `toolChoice`, `includeRawChunks`, `abortSignal`, `headers`,
`reasoning: 'provider-default'|'none'|'minimal'|'low'|'medium'|'high'|'xhigh'`,
`providerOptions`.

`LanguageModelV4Prompt` (`language-model-v4-prompt.ts:18-58`) is a normalized four-role
message list with `user: (text|file)[]`, `assistant: (text|file|custom|reasoning|
reasoning-file|tool-call|tool-result)[]`, `tool: (tool-result|tool-approval-response)[]`,
and files are `{data: bytes|base64|url, mediaType: IANA}` — i.e. **all four D16 modalities
are representable at this seam**, since `mediaType` is open.

**Verdict: the best-designed seam in the corpus**, and the natural template for PACT's own
model-transport interface. Also note `supportedUrls` — a declarative statement of which
media URLs the provider ingests natively vs which the SDK must download. PACT's capability
lattice should have exactly this.

**The `HarnessV1` precedent (directly load-bearing for §3.10 and for D15).**
`@ai-sdk/harness@1.0.43` defines a *second, peer* specification for driving opaque
coding-agent runtimes: `HarnessV1`
(`packages/harness/src/v1/harness-v1.ts:21-92`), whose docstring (`:8-19`) says:

> `Versioned specification for a harness adapter — the integration point for one
> third-party coding-agent runtime (Claude Code, Codex, …). Modelled after
> LanguageModelV4: a tagged spec version, a small set of descriptive fields, and one
> entry-point method (doStart) that yields a session.`

Fields: `harnessId`, `builtinTools: ToolSet`, `supportsBuiltinToolApprovals?`,
`supportsBuiltinToolFiltering?`, `lifecycleStateSchema?`, `getBootstrap?`,
`doStart(options) -> HarnessV1Session`. Capability negotiation is by *method presence* and
by throwing `HarnessCapabilityUnsupportedError` (`:16-19`).
`HarnessV1StreamPart` (`packages/harness/src/v1/harness-v1-stream-part.ts:28-92`)
deliberately **reuses `LanguageModelV4ToolCall`/`ToolResult`/`ToolApprovalRequest`/`Usage`/
`FinishReason` verbatim** (`:18-25`) so a harness session can be piped into AI SDK
consumers, and renames provider metadata to `harnessMetadata` "because a harness is a peer
to a provider, not a kind of provider" (`:22-26`).

Concrete adapters exist: `packages/harness-claude-code` (dev-dependency
`@anthropic-ai/claude-agent-sdk@0.3.213`), `harness-codex`, `harness-opencode`,
`harness-deepagents`, `harness-pi`.

**[V]** Vercel independently hit the same wall PACT hits at §3.10 and solved it by adding a
*third* lowering tier below "native" and "harness": an **opaque-runtime session tier**,
with capability discovery by throwing. This is strong external validation of PACT's
two-level lowering thesis (T3) *and* evidence that two levels are not enough.

---

## 6. Cross-check: Pydantic AI and LangGraph (only what the matrix needs)

Verified directly, so the matrix rows are evidence-backed rather than recalled.

### 6.1 Pydantic AI seam

`pydantic_ai.models.Model` (`pydantic_ai_slim/pydantic_ai/models/__init__.py:261`):
```python
async def request(self, messages: list[ModelMessage], model_settings: ModelSettings | None,
                  model_request_parameters: ModelRequestParameters) -> ModelResponse    # :310
async def request_stream(..., run_context=None) -> AsyncGenerator[StreamedResponse]     # :347
def customize_request_parameters(self, mrp) -> ModelRequestParameters                   # :378
async def count_tokens(...)                                                             # :322
async def compact_messages(self, request_context, *, instructions=None)                 # :331
async def cancel_suspended_response(self, response)                                     # :359
def continuation_delay(self, response) -> float | None                                  # :366
```
**[V]** Framework-neutral message vocabulary (`ModelMessage`, not provider wire types) —
the only seam besides `LanguageModelV4` that is *not* provider-shaped.

`ModelRequestParameters` (`:133-163`) is uniquely expressive on structured output:
`function_tools`, `native_tools`, `output_mode: OutputMode`, `output_object`,
`output_tools`, `prompted_output_template`, `allow_text_output`, `allow_image_output`,
`instruction_parts: list[InstructionPart]` (with static/dynamic provenance for cache
boundary placement — `:150-158`), `thinking: ThinkingLevel | None`.

**[V]** Pydantic AI is the only framework that makes the **structured-output *mode*** a
declared, portable request parameter (native / tool / prompted / text), and the only one
that carries **instruction provenance** for prompt-cache boundary placement. Both belong
in PACT.

Also uniquely: `cancel_suspended_response` / `continuation_delay` (`:359,366`) model
*server-side suspended turns* (Anthropic `pause_turn`, OpenAI background mode) as a loop
concept. No other framework has this.

### 6.2 LangGraph

`langgraph.types.interrupt(value)` (`libs/langgraph/langgraph/types.py:811`),
`Interrupt` (`:535`), `Command` (`:759`, `Generic[N], ToolOutputMixin`). Prebuilt agent at
`libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py`, with `interrupt.py`,
`tool_node.py`, `tool_validator.py`, `_tool_call_stream.py`. Model seam is LangChain's
`BaseChatModel`.

**[V]** LangGraph's HITL is *state-graph* scoped (thread + checkpointer), and its resume
token is `Command(resume=...)` — a third distinct HITL model, matching neither OpenAI's
`RunState` nor Vercel's message parts.

---

## 7. THE DIVERGENCE MATRIX

Legend: **✓** native/first-class · **~** partial or awkward · **✗** absent ·
**[srv]** delegated to a server · **[bin]** delegated to a closed binary.

### 7.0 Dimension 1 — Loop

| | AutoGen | OpenAI Agents | Claude Agent SDK | Anthropic SDK | Vercel AI | Pydantic AI | LangGraph |
|---|---|---|---|---|---|---|---|
| Default loop | **1 tool round** (`max_tool_iterations=1`) | ReAct until final output | opaque **[bin]** | while tool_use present | until no unresolved client tool call | ReAct | user-authored graph |
| Loop unit | "tool iteration" | "turn" | "turn" (CLI-defined) | "iteration" | "step" | "node run" | "superstep" |
| Bound | `max_tool_iterations` | `max_turns` (+recoverable handler) | `max_turns`, `max_budget_usd` | `max_iterations` | `stopWhen` (default `isStepCount(20)`) | `usage_limits` | `recursion_limit` |
| Declarative stop vocabulary | **✓ 12 conditions + and/or** | ~ (`tool_use_behavior` 4-way) | ✗ | ✗ (count only) | ✓ (`StopCondition` array) | ~ | ✓ (graph edges) |
| Per-step reconfiguration | ✗ | ~ (`is_enabled` callbacks) | ✗ | ✓ (`set_messages_params`) | **✓✓ `prepareStep`** | ~ | ✓ (node code) |
| Model-visible tool results by default | **✗** (`reflect_on_tool_use=False`) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Refusal is terminal | ✗ | ✗ | ~ | **✓** | ✗ | ✗ | ✗ |
| Server-suspended turn modelled | ✗ | ~ (background) | ✗ | ~ | ✗ | **✓** | ✗ |

**Irreconcilable pair:** AutoGen's "tool result *is* the answer" default vs everyone else's
"model sees tool result." A single IR default must pick one (pick: model sees results) and
mark AutoGen's alternative as an explicit `loop.tool_result_disposition: return|reflect`
field, otherwise import from AutoGen silently changes behaviour.

### 7.1 Dimension 2 — State / resume

| | AutoGen | OpenAI Agents | Claude Agent SDK | Anthropic SDK | Vercel AI | Pydantic AI | LangGraph |
|---|---|---|---|---|---|---|---|
| Canonical run state | typed per-component dicts | **opaque `RunState` JSON**, `$schemaVersion 1.13` | session file / store **[bin]** | **the message array** | **the message array** | message history | checkpointed graph state |
| Mid-run snapshot | **✗ (unsafe)** | ✓ | ~ (`defer` only) | ✓ (trivially) | ✓ (trivially) | ✓ | ✓ |
| Resume input | n/a | `Runner.run(agent, run_state)` | `resume=<session-id>` | re-call with messages | re-call with messages | re-call | `Command(resume=)` |
| Fork | ✗ | ✗ | **✓ `fork_session`** | ~ (copy messages) | ~ | ~ | ✓ (checkpoint id) |
| Versioned state schema | `version: "1.0.0"` per model | **✓ + refusal to load unknown** | ~ | n/a | n/a | n/a | ~ |
| Durable execution | ✗ | ✗ | **[bin]** | **[srv]** (sessions) | separate `WorkflowAgent` | ✗ (DBOS integration exists out of tree) | ✓ checkpointer |

**Irreconcilable triple:** *opaque snapshot* (OpenAI) vs *transcript-only* (Anthropic,
Vercel, Pydantic AI) vs *graph checkpoint* (LangGraph). PACT must pick **transcript-only**
as canonical and treat the other two as adapter-private projections, because only the
transcript is authorable/diffable (D18) and only it satisfies T5.

### 7.2 Dimension 3 — Tools

| | AutoGen | OpenAI Agents | Claude Agent SDK | Anthropic SDK | Vercel AI | Pydantic AI |
|---|---|---|---|---|---|---|
| Tool-result payloads | **`str` only** | text/image/file | MCP content blocks | text + blocks | **text/json/error/denied/file** | rich |
| Parallel tool execution | ✓ unbounded | ✓ **with cap** | **[bin]** | **✗ sequential** | ✓ unbounded | ✓ |
| Dynamic exposure | ✗ | ✓ `is_enabled(ctx, agent)` | `allowed/disallowed_tools` | **in-transcript add/remove blocks** | `activeTools`, `toolOrder`, `prepareStep` | toolsets |
| Per-tool timeout | ✗ | ✓ + `timeout_behavior` | ✗ | ✗ | ✓ (`TimeoutConfiguration`) | ~ |
| Declared tool *output* schema | ✗ | ✓ `output_json_schema` | ✗ | ~ | ✓ `outputSchema` (**required** when no `execute`) | ✓ |
| Tool-call repair | ✗ | ~ (retry) | ✗ | ✗ | ✓ `repairToolCall` + `refineToolInput` | ✓ `ModelRetry` |
| Per-tool guardrails | ✗ | **✓ in/out** | hooks (**unordered**) | ✗ | ✗ | ✗ |
| Sandbox as tool config | ✗ | ✓ `ShellTool` net/fs policy | ✓ `SandboxSettings` | ~ (`agent_toolset` trust note) | `experimental_sandbox` | ~ |

**Three incompatible dynamic-exposure mechanisms**: callback (OpenAI, Vercel), transcript
blocks (Anthropic), static lists (Claude SDK). PACT should express exposure *declaratively*
(a predicate over run context) and lower it to whichever mechanism the target has —
reporting `degraded` for AutoGen, which has none.

### 7.3 Dimension 4 — Structured output

| | AutoGen | OpenAI Agents | Claude Agent SDK | Anthropic SDK | Vercel AI | Pydantic AI |
|---|---|---|---|---|---|---|
| Where | agent `output_content_type` | agent `output_type` (final only) | `output_format` dict | `output_config.format` | `Output` plugin | `output_type` + **mode** |
| Mode selectable (native/tool/prompted/text) | ✗ | ✗ | ✗ | ✗ | ~ (`responseFormat` only) | **✓ `OutputMode`** |
| Partial/streaming parse | ✗ | ✗ | ✗ | ✗ | **✓ `parsePartialOutput`** | ✓ |
| Element streaming (arrays) | ✗ | ✗ | ✗ | ✗ | **✓** | ~ |
| Constrained choice primitive | ✗ | ✗ | ✗ | ✗ | **✓ `choice()`** | ~ |
| Capability declared on model | **✓ `ModelInfo.structured_output` vs `json_output`** | ✗ | ✗ | ✗ | ~ | ✓ (profiles) |

### 7.4 Dimension 5 — Streaming

| | AutoGen | OpenAI Agents | Claude Agent SDK | Anthropic SDK | Vercel AI |
|---|---|---|---|---|---|
| Model-seam granularity | **`str` chunks + final `CreateResult`** | OpenAI Responses events verbatim | raw Anthropic events in envelope (opt-in) | typed semantic events | **normalized `LanguageModelV4StreamPart`** |
| Tool-arg deltas | **✗** | ✓ (provider) | ✓ (raw) | ✓ `BetaInputJsonEvent` | ✓ `tool-input-delta` |
| Reasoning deltas | ~ (`ThoughtEvent`, whole) | ✓ (provider) | ✓ (raw) | ✓ `BetaThinkingEvent` | ✓ `reasoning-delta` |
| Block ids for correlation | ✗ | ✓ (provider) | ✓ | ✓ | ✓ |
| Semantic run-level events | ✓ (10 event classes) | ✓ (10-name literal) | message-level | ✗ | ✓ (step/UI layers) |
| Raw passthrough opt-in | n/a | always-on raw layer | `include_partial_messages` | raw SSE available | **`includeRawChunks`** |

### 7.5 Dimension 6 — HITL

| | Mechanism | Suspends? | Resume token | Serialisable? | Model sees denial? |
|---|---|---|---|---|---|
| AutoGen | `UserProxyAgent.input_func` blocking callback | ✗ | n/a | **✗ (`input_func` dropped)** | as a chat message |
| OpenAI Agents | `needs_approval` → `NextStepInterruption` | ✓ | `RunState` blob + `approve`/`reject` | ✓ (opaque) | ✓ (rejection tool output) |
| Claude Agent SDK | `can_use_tool` / hooks / `defer` | only `defer` | session id | ✗ (callbacks) | ✓ |
| Anthropic (messages) | **none** | ✗ | n/a | n/a | n/a |
| Anthropic (sessions) | server `evaluated_permission: ask` | ✓ **[srv]** | event id | **[srv]** | ✓ |
| Vercel AI | `toolApproval` config → approval request/response **content parts** | ✓ | **a message** | **✓ (plain data)** | ✓ `execution-denied{reason}` |
| Pydantic AI | deferred toolsets / approval | ✓ | message history | ✓ | ✓ |
| LangGraph | `interrupt()` + checkpointer | ✓ | `Command(resume=)` + thread id | ✓ (checkpoint) | depends |

**This is the sharpest divergence in the study.** Four incompatible resume tokens:
a blob, a message, a graph command, a session id. Only *a message* is authorable.

### 7.6 Dimension 7 — Memory

| | Conversation store | Retrieval memory | Context-window policy | Compaction |
|---|---|---|---|---|
| AutoGen | via `ChatCompletionContext` | **✓ `Memory` ABC** | **✓ 4 policies, stateful** | via context policy |
| OpenAI Agents | ✓ `Session` protocol | ✗ | ✗ | ✓ optional session protocol ext. |
| Claude Agent SDK | ✓ sessions + `SessionStore` + **fork** | ✗ (CLAUDE.md scopes) | **[bin]** | **[bin]** (`PreCompact` hook) |
| Anthropic SDK | ~ (caller's array) / **[srv]** sessions | ✓ **as a tool** (memory tool) | `context_management` param | `compaction_control` + stream event |
| Vercel AI | **✗** | **✗** | ✓ `pruneMessages` (pure fn) | ✗ |
| Pydantic AI | message history | ✗ (toolsets) | ~ | `compact_messages` on `Model` |
| LangGraph | checkpointer + store | ✓ `BaseStore` | ~ | ~ |

**Only AutoGen and LangGraph have a memory *interface*.** PACT's `memory:` block has no
native lowering on 3 of 7 targets; it must be a harness-side construct that can *optionally*
lower to a native interface.

### 7.7 Dimension 8 — Multi-agent

| | Native topology objects | Max depth | Serialisable topology | Routing decided by |
|---|---|---|---|---|
| AutoGen | **5** (RoundRobin, Selector, Swarm, MagenticOne, **GraphFlow/DiGraph**) | unbounded (SocietyOfMind nests) | ✓ **but callable edge conditions silently dropped** | code / LLM selector / graph edges |
| OpenAI Agents | handoff (tool) + `as_tool` | unbounded via nesting | ~ (code) | model (tool call) |
| Claude Agent SDK | `agents:` subagent roster | **1** | ✓ (`AgentDefinition` dicts) | model (Agent tool) |
| Anthropic (managed) | `multiagent{type:"coordinator", agents[1..20]}` | **1 (hard)** | ✓ **[srv]** | model |
| Vercel AI | **none** | n/a | n/a | n/a |
| Pydantic AI | agent-as-tool / delegation | unbounded | ~ | model |
| LangGraph | the graph itself | unbounded | ✓ (graph def) | edges / conditional edges |

**PACT `AC-5.1` (8 patterns × ≥3 adapters) is only reachable through harness lowering.**
Native topology exists in only 2 of 7, one of which is frozen and one of which drops
conditions on serialize.

### 7.8 Dimension 9 — Model binding

| | Binding shape | Provider routing | Fallback | Air-gap default | Capability self-report |
|---|---|---|---|---|---|
| AutoGen | `ChatCompletionClient` instance | via `ComponentModel.provider` (**python import path**) | ✗ | ✓ (explicit client) | **✓ `ModelInfo`** |
| OpenAI Agents | `str \| Model` | **prefix map** (`openai/`, `litellm/`, `any-llm/`) | ~ (retry advice) | ✓ | ✗ |
| Claude Agent SDK | `str` alias/id | ✗ | ✓ `fallback_model` | **✗ (binary + env only)** | ✗ |
| Anthropic SDK | `model: str` per request | ✗ | ✓ `fallbacks` param **[srv]** | ✓ (base_url) | ~ (`beta_capability_support`) |
| Vercel AI | `string \| LanguageModelV*` | **global provider; defaults to hosted gateway** | ~ (middleware) | **✗ by default** | `supportedUrls` + warnings |
| Pydantic AI | `str \| Model` + profiles | provider classes | ~ | ✓ | ✓ (model profiles) |

### 7.9 Modality coverage (D16)

| | Text+tools | Vision (image) | Documents/PDF | Audio in | Audio out / voice | Computer use |
|---|---|---|---|---|---|---|
| AutoGen | ✓ | ✓ (`Image`) | **✗** | **✗** | **✗** | via ext tools |
| OpenAI Agents | ✓ | ✓ | ✓ | **separate `RealtimeAgent`/`VoicePipeline`** | separate | ✓ `ComputerTool` |
| Claude Agent SDK | ✓ | ✓ | ✓ | ✗ | ✗ | via built-in tools |
| Anthropic SDK | ✓ | ✓ | ✓ (`document`) | **✗ (no audio types at all)** | ✗ | ✓ (computer tool) |
| Vercel AI | ✓ | ✓ | ✓ | ✓ (`mediaType` open) | separate `realtime-session` | ✓ (provider tools) |

**The voice finding is structural, not incidental.** `RealtimeAgent`
(`openai-agents-python/src/agents/realtime/agent.py:28-40`) documents, verbatim, that it
does **not** support `model`, `modelSettings`, `outputType`, or `toolUseBehavior` —
"outputType is not supported, as RealtimeAgents do not support structured outputs." Its
model interface is a different ABC entirely (`realtime/model.py:151` `RealtimeModel` with
`connect/add_listener/send_event/close`). Vercel likewise puts realtime in a separate
subsystem (`packages/ai/src/realtime/realtime-session.ts`).

**[V]** In every framework that has voice, voice is a *disjoint agent abstraction*, not a
modality flag. PACT cannot model audio as "just another content type" and expect native
lowering.

---

## 8. Harness-lowering seam table (the brief's explicit question)

| SDK | Lowest-level model/tool transport | Verdict |
|---|---|---|
| **AutoGen** | `autogen_core.models.ChatCompletionClient.create()` / `.create_stream()` — `_model_client.py:212,242` | **Exists, `degraded`.** No text+tool interleave (`_types.py:43`), no audio/doc parts (`_types.py:32`), string-only tool results (`_types.py:59`), text-only stream (`_model_client.py:254`). |
| **OpenAI Agents** | `agents.models.interface.Model.get_response()` / `.stream_response()` — `models/interface.py:61,96`; provider via `ModelProvider.get_model()` `:138` | **Exists, coupled.** Speaks OpenAI Responses wire types (`items.py:76,79,82`) and accepts SDK `Tool`/`Handoff`/`AgentOutputSchemaBase`. Workable; costs a translation layer. |
| **Claude Agent SDK** | *(none)* — only `Transport` (`_internal/transport/__init__.py:9`), which is the Claude Code control protocol, not a model API | **BLOCKING. No seam.** Loop, tools, compaction, subagents live in the `claude` binary (`subprocess_cli.py:463`, `_cli_version.py:3`). Harness lowering would mean reimplementing Claude Code. |
| **Anthropic SDK** | `client.beta.messages.parse()` / `.stream()` (as driven at `_beta_runner.py:701,710`); optionally step-drive `BaseToolRunner` via `set_messages_params`/`append_messages`/`generate_tool_call_response` (`:96,111,316`) | **Cleanest seam.** Pure wire types, no SDK objects. Only gap: no audio content block anywhere in `types/beta/`. |
| **Vercel AI SDK** | `LanguageModelV4.doGenerate()` / `.doStream()` — `packages/provider/src/language-model/v4/language-model-v4.ts:46,58` | **Best-designed seam.** Normalized prompt with open `mediaType`, normalized tools, normalized stream parts, `providerOptions` escape, `supportedUrls` capability declaration. |
| *(cross-check)* Pydantic AI | `Model.request()` / `.request_stream()` — `models/__init__.py:310,347` | Framework-neutral messages; richest request-parameter object (`ModelRequestParameters:133`). |
| *(cross-check)* LangGraph | LangChain `BaseChatModel` | Standard; not audited here. |

---

## 9. Blocking and near-blocking findings

**B1 — `claude-agent-sdk` has no harness-lowering seam.** (§3.10)
Violates `P-2`/`AC-2.2` outright, strains `D17` (proprietary bundled binary), and is in
direct tension with `D15` (no opaque wrapping). *Any* PACT adapter for this SDK is an
opaque wrapper by construction.

**B2 — AutoGen cannot satisfy kill-and-resume.** (§1.2)
`save_state` during a run is documented-unsafe (`_base_group_chat.py:773-776`) and
`load_state` refuses while running (`:808-809`). `AC-2.6` unreachable natively.

**B3 — AutoGen is frozen.** (§1.0) Maintenance mode since ≥2026-04; no new features;
successor named. Building an export adapter targets a dead runtime.

**B4 — Four incompatible HITL resume tokens.** (§7.5) blob / message / graph-command /
session-id. Without a decision, `AC-2.2` fails on any HITL golden agent.

**B5 — No native multi-agent on Vercel; depth-1 caps on Anthropic managed agents and
Claude subagents.** (§7.7) `AC-5.1` and `G-4` are harness-only.

**B6 — Audio is a disjoint abstraction everywhere, and absent from Anthropic entirely.**
(§7.9) `D16`'s "all four modalities in v1" cannot mean "one agent kind with a modality
flag."

**B7 — Vercel resolves bare model-id strings against a hosted gateway by default.**
(§5.9, `resolve-model.ts:181-184`) Silent network dependency; breaks `AC-7.3` unless the
adapter asserts `AI_SDK_DEFAULT_PROVIDER`.

**B8 — Serialization holes are real and shipped.** AutoGen drops callable graph-edge
conditions on dump (`_digraph_group_chat.py:69-76`), drops `input_func` on
`UserProxyAgent` export (`_user_proxy_agent.py:244-245`), and documents
`tool_call_summary_formatter` as ignored by config
(`_assistant_agent.py:158-160,233`). Import from AutoGen must therefore treat *absence* as
suspicious, not as "no such feature."

---

## 10. Design implications for PACT (actionable)

Ordered by how much they change the spec.

1. **Canonical run state = the transcript.** Adopt Anthropic/Vercel/Pydantic-AI semantics:
   everything needed to resume a PACT run is a list of typed messages plus a small
   scalar cursor. `RunState`-style blobs (OpenAI) and checkpoints (LangGraph) become
   adapter-private projections computed *from* the transcript, never the source of truth.
   Rationale: only the transcript is diffable, hand-editable, and Expansion-Rule-compatible
   (T5, D18).

2. **HITL = two message part kinds, not a control-flow feature.** Standardise
   `tool-approval-request{approvalId, toolCallId, reason?}` and
   `tool-approval-response{approvalId, approved, reason?}` as PACT content parts, copying
   `LanguageModelV4ToolApprovalRequest`/`...ResponsePart` exactly. Add a
   `tool-output/execution-denied{reason}` result variant so the model observes denials.
   Lower to `RunState.approve/reject` (OpenAI), `Command(resume=)` (LangGraph),
   `can_use_tool` (Claude SDK), and report `unsupported` for AutoGen and the Anthropic
   Messages runner.

3. **Adopt `LanguageModelV4` as the shape of PACT's model-transport ABI.** Specifically:
   four-role normalized prompt; user/assistant content parts with an **open IANA
   `mediaType`**; `tool-*` deltas with block ids; `responseFormat` as a first-class request
   field; `providerOptions` as the typed escape hatch; and a `supportedUrls`-equivalent so
   the resolver knows which media the substrate ingests natively vs which PACT must fetch.

4. **Make the structured-output *mode* a declared field, not an inference.**
   Copy `ModelRequestParameters.output_mode` (`pydantic-ai .../models/__init__.py:135-139`):
   `text | native_json_schema | tool | prompted`, plus `allow_text_output`,
   `prompted_output_template`. Without it, PACT cannot express "this small model needs
   prompted JSON with a repair loop, the frontier model uses native schema" — which is a
   core T4 strategy lever.

5. **Add `loop.tool_result_disposition: reflect | return` with default `reflect`.**
   This is the only way to import AutoGen's default agent without silently changing
   behaviour (§7.0), and it is independently useful (it *is* `stop_on_first_tool`).

6. **Add a third lowering tier: `session lowering`.** Native / harness / **session**.
   Model it on `HarnessV1` (`packages/harness/src/v1/harness-v1.ts:21-92`): a versioned
   spec with `builtinTools`, boolean capability flags, `lifecycleStateSchema`, one
   `doStart() -> Session` entry point, and capability negotiation by *throwing a typed
   error*. This is where `claude-agent-sdk` (and Codex/OpenCode/Goose) legitimately live.
   **This requires an explicit amendment to D15**: session lowering *is* opaque wrapping,
   and the honest move is to name the tier, restrict it (a session-lowered agent is
   `portability: session-only` in its lattice and cannot be a node in a PACT topology
   unless its transcript is exportable), rather than to pretend `claude-agent-sdk` can be
   translated.

7. **Split `memory:` from `context:`.** Copy AutoGen's separation
   (`Memory` ABC vs `ChatCompletionContext`). `context:` should use Vercel's
   `pruneMessages` vocabulary directly — `reasoning: all|before-last-message|none`,
   `toolCalls: all|before-last-N-messages|none|[{type,tools}]`,
   `emptyMessages: keep|remove` — plus a `compaction:` sub-block (threshold, mode,
   `force`) modelled on `OpenAIResponsesCompactionArgs` and Anthropic
   `compaction_control`. `memory:` is retrieval and MUST be lowerable to *a tool* (the
   Anthropic pattern) because 3 of 7 targets have no memory interface.

8. **Declare tool-execution concurrency in the IR.** `tools.concurrency: {max: N | unbounded,
   order: parallel | sequential}`. Anthropic executes sequentially
   (`_beta_runner.py:342,651`), OpenAI has a cap (`run_config.py:109`), Vercel and AutoGen
   are unbounded. Latency-sensitive SLOs (`O4.2`) are not portable unless this is declared.

9. **Tool results are content-typed, not strings.** Adopt Vercel's `ToolResultOutput`
   union verbatim: `text | json | error-text | error-json | execution-denied{reason} |
   content[{text|file{data,mediaType}}]`. Mark AutoGen `degraded` on this axis
   (`_types.py:59` — `content: str`) and emit a loss report on export.

10. **Model voice/realtime as a distinct `loop.kind: realtime`, not a modality flag.**
    Evidence: `realtime/agent.py:28-40` (no model, no model settings, no output type, no
    tool-use behaviour) and `realtime/model.py:151` (a different model ABC). PACT should
    define `RealtimeContract` sharing identity/capabilities/policy with `AgentContract`
    but with its own loop, event vocabulary, and SLOs (TTFT/barge-in), and should refuse to
    compile a `realtime` agent onto a substrate whose realtime seam is absent.

11. **Capability lattice needs an `emulated` tier with a named shim.** Vercel's
    `simulateStreamingMiddleware` (`packages/ai/src/middleware/`) is the pattern: a
    decorator that makes a non-streaming model satisfy a streaming contract. PACT should
    ship the same idea as first-class: `capability: streaming → emulated by
    pact:shim/simulate-streaming`, recorded in the lockfile so the Portability Report can
    say *how* a capability was satisfied.

12. **Adopt `ModelInfo`-style declared capabilities in the catalogue, and keep
    `json_output` distinct from `structured_output`.** AutoGen already found this
    distinction necessary (`_model_client.py:174-180`), and `validate_model_info` (`:185`)
    hard-fails on omission. PACT's `models/catalog.yaml` should require
    `{vision, function_calling, json_output, structured_output, family, context_window}` and
    fail closed, per `AC-3.3`.

13. **Reserve provider routing hints in the profile.** `inference_geo`, `service_tier`,
    `speed`, `fallbacks` (Anthropic `tool_runner` params) and `previous_response_id` /
    `conversation_id` (OpenAI) are neither capability nor cost — they are substrate routing.
    Give them a home (`profile.routing:`) or they will leak into `x-` blocks on every export.

14. **Import from AutoGen must be *pessimistic*.** Because AutoGen silently drops callable
    edge conditions, `input_func`, and `tool_call_summary_formatter`
    (§9/B8), the PACT importer must flag any AutoGen `DiGraphEdge` with
    `condition: null` and any `UserProxyAgent` with `input_func: null` as
    `ImportReport.suspected_loss`, not as clean. Absence in AutoGen's serialisation is not
    evidence of absence in the agent.

15. **The Vercel adapter must assert an offline provider.** Before any `generateText`
    call, the adapter sets `globalThis.AI_SDK_DEFAULT_PROVIDER` from the resolved PACT
    substrate and fails loudly if a bare string model id would otherwise reach
    `gateway` (`resolve-model.ts:181-184`). Add this to the `AC-7.3` offline test.

16. **Reprioritise adapters.** On this evidence the seven-framework list should be
    re-cut as: **tier 1 (real seams, live repos)** Pydantic AI, Vercel AI SDK, Anthropic
    SDK, OpenAI Agents SDK, LangGraph; **tier 2 (import-only)** AutoGen, LangChain;
    **tier 3 (session lowering)** Claude Agent SDK. Note this *swaps* the Anthropic
    representative from `claude-agent-sdk` to `anthropic-sdk-python`, which is the only
    change that makes `P-2` satisfiable across the whole set.

17. **Steal these three primitives outright** because nothing in PACT's current design
    covers them and each is cheap:
    - **Refusal as a terminal loop condition** (`_beta_runner.py:288-292`) — a distinct
      `halt.reason: refusal`, since executing a refused turn's tool calls is a correctness
      *and* safety bug.
    - **Instruction provenance for cache boundaries**
      (`pydantic-ai .../models/__init__.py:150-158`, `instruction_parts` with
      static/dynamic marks) — static vs dynamic instruction split is exactly what PACT's
      `instructions.md` + variant overlay produces for free, and it is worth ~cache-hit
      money at runtime.
    - **`defer_loading` / tool-search** (`openai-agents .../tool.py:453`) — hide tool
      definitions until searched. A direct implementation of `00-THESIS.md §7.3 item 4`
      (context discipline), already shipping.

---

## 11. Open questions this stream could not close

1. Does OpenAI Agents' `Model.get_response` tolerate `handoffs=[]` while PACT synthesises
   handoff tools itself? Shape suggests yes; **not exercised**. Needs a spike.
2. Can `BaseToolRunner` (Anthropic) be step-driven from outside to interpose approvals,
   given `generate_tool_call_response()` is public and cached? Shape suggests yes;
   **not exercised**.
3. Is there any supported way to point the bundled `claude` binary at a non-Anthropic,
   on-prem endpoint? Nothing in `claude-agent-sdk-python` reads such a variable; it would
   be the binary's behaviour. **Unknown from this corpus.**
4. What is the actual conformance cost of AutoGen's text/tool-call disjunction
   (`_types.py:43`)? I can show it is inexpressible; I have not measured whether it changes
   eval scores. Needs a CTS fixture with an interleaved-content golden agent.
5. `@ai-sdk/workflow`'s `WorkflowAgent` vs `ToolLoopAgent` — how far have they diverged?
   The repo carries `workflow-agent-compat.test.ts` to police it, which implies drift is
   expected. Relevant to `P-5`.
6. LangChain (the 7th target) was not audited here; its `BaseChatModel` seam is assumed,
   not verified.
