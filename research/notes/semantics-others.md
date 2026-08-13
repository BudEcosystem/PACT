# PACT research stream: `semantics-others`

**Deep SOURCE audit of AutoGen, OpenAI Agents SDK (Python), Claude Agent SDK (Python),
Anthropic SDK (Python) and the Vercel AI SDK across nine semantic dimensions; the
divergence matrix a single IR must reconcile; and the exact harness-lowering seam
in each SDK.**

Date: 2026-08-07. Status: evidence-linked, re-verified against source.
Supersedes the 2026-07-26 draft of this note — **every claim below was re-read from
source in this pass**, not inherited. Where the earlier draft was right I say so and
give the citation; where this pass found something the earlier draft did not have,
it is marked **[NEW]**.

---

## 0. Method, scope and provenance

### 0.1 What was read

Source only, from the local corpus at
`/home/bud/ditto/agent-inter-op/research/repos/frameworks/`. Every claim cites
`file:line` against these exact checkouts. Paths in citations are relative to each
repo root unless otherwise stated.

| Repo | Commit | Commit date | Version read |
|---|---|---|---|
| `autogen` | `027ecf0` | 2026-04-06 | `autogen-core` / `autogen-agentchat` **0.7.5** |
| `openai-agents-python` | `c1b4237` | 2026-07-25 | **0.18.3** (`pyproject.toml`) |
| `claude-agent-sdk-python` | `f8b9ec9` | 2026-07-25 | **0.2.128** (`pyproject.toml`) |
| `anthropic-sdk-python` | `60c64fb` | 2026-07-24 | **0.120.0** (`pyproject.toml`) |
| `vercel-ai` | `eb16508` | 2026-07-25 | `ai@7.0.37`, `@ai-sdk/harness@1.0.43` |
| `pydantic-ai` (cross-check) | `ed0f40c` | 2026-07-25 | — |
| `langgraph` (cross-check) | `30c4d58` | 2026-07-25 | — |

The checkouts are byte-identical to the 2026-07-26 pass, so nothing here is
"the framework changed". Differences from the earlier draft are differences of
*reading*.

### 0.2 The nine dimensions

loop · state · tools · structured output · streaming · HITL · memory ·
multi-agent · model binding. Plus the tenth question the brief asks explicitly:
**what is the exact lowest-level API in each SDK that PACT can drive as a pure
model/tool transport?**

### 0.3 Reading convention

- **[V]** verified by reading the executing code path.
- **[D]** verified from a source docstring or type annotation only.
- **[I]** my inference. Always marked. Never load-bearing on its own.

### 0.4 The one-line answer to the brief

Four of the five frameworks have a clean harness-lowering seam. **The Claude Agent
SDK has none, and that is a blocking finding** (§3.10). The single largest
semantic divergence in the set is not tools or streaming — it is that **three of
the five frameworks default to a loop that never shows the model its own tool
results** (§7.1), which means PACT cannot inherit any framework's default and must
declare its own.

---

## 1. AutoGen (`microsoft/autogen`, 0.7.5)

### 1.0 Framing: the repo is frozen

`README.md:14` carries a `status-maintenance mode` badge linking to
`github.com/microsoft/agent-framework`. `README.md:19-24`:

> **⚠️ Maintenance Mode**
> AutoGen is now in maintenance mode. It will not receive new features or
> enhancements and is community managed going forward.
> New users should start with [Microsoft Agent Framework]…

The HEAD commit (`027ecf0`, 2026-04-06) is *"Update maintenance mode banner in
readme (#7521)"* — the repo has been frozen ~4 months while the other four moved
daily. **[V]**

**Consequence for PACT.** AutoGen is a **legacy import target**, not a live export
target. The adapter roadmap should treat it as an on-ramp (D10 #3, "migration
tool") and should *not* spend fidelity budget chasing native lowering.

### 1.1 Loop — the sharpest divergence in the whole study

AutoGen has two loops at two layers and they are not the same abstraction.

**Layer 1 — `autogen-core` actor runtime.** `AgentRuntime`
(`python/packages/autogen-core/src/autogen_core/_agent_runtime.py`) exposes
`send_message` (RPC-shaped) and `publish_message` (pub/sub over topics). There is
no agent loop here at all; loop semantics are whatever a message handler does.

**Layer 2 — `autogen-agentchat` `AssistantAgent`.** The default is **not** a ReAct
loop:

- `agents/_assistant_agent.py:739` — `max_tool_iterations: int = 1` (constructor).
- `agents/_assistant_agent.py:85` — same default on the serialisable config:
  `max_tool_iterations: int = Field(default=1, ge=1)`.
- `agents/_assistant_agent.py:1149` — `for loop_iteration in range(max_tool_iterations):`
- `agents/_assistant_agent.py:1151-1175` — if the model returned a plain string, yield
  the response and `return`. This is the only "model decided it was done" exit.
- `agents/_assistant_agent.py:1258-1259` — on the last iteration, `break` out to the
  summary/reflection step **without another model call**.
- `agents/_assistant_agent.py:1302-1324` — after the loop, either
  `_reflect_on_tool_use_flow` (one more model call) or `_summarize_tool_use`
  (**no** model call; the formatted tool-result string becomes the agent's answer).
- `agents/_assistant_agent.py:842-848` — `reflect_on_tool_use` defaults to `True`
  **only if** `output_content_type` is set, else `False`.

**[V] So the default AutoGen agent is: one model call → execute tools → return the
tool result string as the final answer, with the model never seeing the tool
output.** This is a genuinely different agent than every reader expects.

Two more loop properties worth recording:

- **Tool calls execute in parallel, unconditionally.**
  `agents/_assistant_agent.py:1200` — `results = await asyncio.gather(*[...])`.
  There is no sequential mode and no concurrency limit. **[V]**
- **Handoff short-circuits the loop.** `agents/_assistant_agent.py:1245-1254` — after
  tool execution, a handoff check runs and `return`s immediately.

**Termination at the team layer** is the best declarative surface AutoGen has:
`base/_termination.py` defines `TerminationCondition` with `__and__`/`__or__`, and
`conditions/_terminations.py` ships 12 serialisable conditions —
`StopMessageTermination:24`, `MaxMessageTermination:62`, `TextMentionTermination:111`,
`FunctionalTermination:158`, `TokenUsageTermination:235`, `HandoffTermination:313`,
`TimeoutTermination:358`, `ExternalTermination:404`, `SourceMatchTermination:463`,
`TextMessageTermination:513`, `FunctionCallTermination:559`, plus And/Or. **[V]**
Each has a `*Config` pydantic model and is a `Component`, so it round-trips —
except `FunctionalTermination:158`, which has no `Config` class and therefore does
not serialise.

**PACT takeaway.** The termination-condition algebra is worth *stealing wholesale*
for the loop IR's `halt:` field. It is the only place in the corpus where loop
termination is already a composable, serialisable predicate rather than an integer.

### 1.2 State

`agents/_assistant_agent.py:1630-1639`:

```python
async def save_state(self) -> Mapping[str, Any]:
    model_context_state = await self._model_context.save_state()
    return AssistantAgentState(llm_context=model_context_state).model_dump()
```

**[V] `save_state` persists the model context (the message list) and nothing else.**
Not the loop iteration counter, not pending tool calls, not partial tool results.
`load_state:1635-1639` restores only that.

**Consequence:** AutoGen **cannot satisfy AC-2.6** (kill-and-resume mid-tool-call).
A run interrupted between "model requested tool" and "tool returned" resumes as if
the tool had never been requested. This is not a gap in the adapter — it is a gap
in AutoGen. Any AutoGen adapter must declare `durable_resume: unsupported` in its
capability lattice.

### 1.3 Tools — and a real lossy step inside AutoGen

Tools are exposed through a `Workbench`
(`autogen-core/src/autogen_core/tools/_workbench.py:78`), an ABC with
`list_tools() -> List[ToolSchema]` (`:96`) and `call_tool(...) -> ToolResult` (`:107`).

`ToolResult` (`_workbench.py:39-52`) carries `result: List[ResultContent]`, where
`ResultContent = TextResultContent | ImageResultContent` (`_workbench.py:14-36`).
**So the Workbench layer supports image tool results.**

But `AssistantAgent._execute_tool_call` flattens it:

- `agents/_assistant_agent.py:1609` — `content=tool_result.to_text()`
- `_workbench.py:55` — `def to_text(self, replace_image: str | None = None) -> str:`
- `_workbench.py:70-74` —
  ```python
  elif isinstance(content, ImageResultContent):
      if replace_image is not None:
          parts.append(replace_image)
      else:
          parts.append(f"[Image: {content.content.to_base64()}]")
  ```

**[V] A tool that returns an image is delivered to the model as the literal string
`"[Image: <base64…>]"`.** It is never an image content block. `AssistantAgent`
never passes `replace_image`, so the base64 blob goes into the prompt as text.

This is because the model-message type cannot hold it either:
`autogen-core/src/autogen_core/models/_types.py:59` — `FunctionExecutionResult.content: str`.

**Consequence: AutoGen's general agent path cannot do computer use or any
screenshot-returning tool** (D16). AutoGen *does* ship a vision web agent
(`autogen-ext/.../agents/web_surfer/_multimodal_web_surfer.py`), but it is a bespoke
`BaseChatAgent` that handles images itself and bypasses `AssistantAgent` entirely.
**[V]** The capability exists in the framework; it does not exist on the portable path.

### 1.4 Structured output

`output_content_type: type[BaseModel] | None`, validated at
`agents/_assistant_agent.py:1153-1154` via `output_content_type.model_validate_json(...)`.
Delivery is via the model client's `json_output` parameter
(`models/_model_client.py:218`), which is `Optional[bool | type[BaseModel]]` —
a *tri-state*: `None` (off), `bool` (JSON mode), or a model class (structured
output). **[V]**

Setting `output_content_type` also flips `reflect_on_tool_use` to `True`
(`:842-844`), silently changing loop semantics. **[V]** A structured-output agent
and a plain agent in AutoGen do not run the same loop.

### 1.5 Streaming

Two levels, and the lower one is impoverished.

**Model level.** `models/_model_client.py:241-251`:

```python
def create_stream(...) -> AsyncGenerator[Union[str, CreateResult], None]
```

**[V] The abstract model stream yields bare `str` text chunks and terminates with a
`CreateResult`.** There is no typed event, no tool-call-argument delta, no
start/end lifecycle, no id. Confirmed against the concrete OpenAI client:
`autogen-ext/src/autogen_ext/models/openai/_openai_client.py` yields only
`reasoning_content` (`:962`, `:968`), `choice.delta.content` (`:974`) and the final
`result` (`:1080`).

**Agent level.** `on_messages_stream` yields typed `BaseAgentEvent` objects
(`ToolCallRequestEvent:1183`, `ToolCallExecutionEvent:1235`, `ThoughtEvent:1286`)
and finally a `Response`. Richer, but agent-shaped, not model-shaped.

**Consequence:** a PACT harness driving `ChatCompletionClient.create_stream` cannot
stream tool-call arguments as they are generated. Any PACT feature that depends on
partial tool arguments (progressive UI, `onInputDelta`-style hooks, early
validation) must be declared `unsupported` on the AutoGen adapter.

### 1.6 HITL — and a serialisation hole

`UserProxyAgent` takes an `input_func` callback
(`agents/_user_proxy_agent.py:169`) and awaits it inline (`:191-197`,
`:226`). It is a **blocking callback**, not an interrupt-and-resume.

And it does not survive serialisation:

- `agents/_user_proxy_agent.py:244-245` —
  ```python
  # TODO: Add ability to serialie input_func
  return UserProxyAgentConfig(name=self.name, description=self.description, input_func=None)
  ```
- `agents/_user_proxy_agent.py:249` — `_from_config` reconstructs with `input_func=None`.

**[V] A `UserProxyAgent` round-tripped through AutoGen's own declarative config
loses its human.** It silently degrades to the default console `input()`.

This matters beyond AutoGen: it is the clearest existing proof that *"declarative
config" without a declarative HITL model is a lie*, and it is exactly the failure
PACT must avoid — HITL has to be a **declared channel with a typed contract**, not
a function pointer.

### 1.7 Memory

`autogen-core/src/autogen_core/memory/_base_memory.py:60` — `Memory` ABC with three
abstract operations: `update_context(...)` (`:77-78`), `query(...)` (`:93-94`),
`add(...)` (`:113-114`).

`update_context` is the distinctive one: memory **mutates the model context in
place before the model call**. This is a *context-injection* memory model, not a
retrieval-tool model. **[V]**

`MemoryMimeType` (`:13-20`) covers `TEXT`, `JSON`, `MARKDOWN`, `IMAGE`, `BINARY` —
**AutoGen's memory is more modality-capable than its tool results** (§1.3), which
is internally inconsistent.

### 1.8 Multi-agent — the richest in the set

Four team types, all under `teams/_group_chat/`:

- `_round_robin_group_chat.py` — fixed rotation.
- `_selector_group_chat.py` — LLM picks the next speaker.
  `SelectorGroupChatManager.__init__:66-98` takes `model_client`, `selector_prompt`,
  `allow_repeated_speaker`, `selector_func`, `max_selector_attempts`,
  `candidate_func`, `model_client_streaming`. `selector_func`/`candidate_func` are
  Python callables (`:163-186`) — **not serialisable**.
- `_swarm_group_chat.py` — handoff-driven. `select_speaker:82-98` walks the thread
  backwards for the most recent `HandoffMessage` and routes to `message.target`.
- `_graph/_digraph_group_chat.py` — `GraphFlow`, a real DAG-with-cycles executor.

`GraphFlow` is the most PACT-relevant construct in AutoGen:

- `DiGraphEdge` (`_digraph_group_chat.py:25-98`) has
  `condition: Union[str, Callable[[BaseChatMessage], bool], None]` (`:39`).
- `:47` — `condition_function: Callable[...] | None = Field(default=None, exclude=True)`,
  and `:69-79` moves a callable condition out of `condition` into
  `condition_function` **specifically so the model serialises**. A callable edge
  condition is silently dropped from the serialised graph. **[V]**
- `:48` `activation_group: str`, `:58` `activation_condition: Literal["all","any"]`,
  `:112` node-level `activation: Literal["all","any"]` — join semantics as data.
- `:151` cycle validation requires every cycle to contain at least one conditional
  edge.

**PACT takeaway.** AutoGen independently arrived at exactly the join-semantics
vocabulary PACT's topology IR needs (`all`/`any` activation, activation groups,
conditional edges, cycle-must-have-an-exit). Adopt the vocabulary; do **not** adopt
the callable escape, which is precisely the thing that breaks portability.

**Handoff conflict resolution is lossy.** `_check_and_handle_handoff:1347-1362` —
if the model emits multiple handoff calls, only the first is executed and a
`warnings.warn` is issued advising "Disable parallel tool calls in the model client
to avoid this warning." **[V]** PACT must *decide* this semantics rather than
inherit it (see §7.8).

### 1.9 Model binding

`ChatCompletionClient` is a `ComponentBase`, so a model client serialises to a
`ComponentModel` (`_component_config.py:18-39`: `provider`, `component_type`,
`version`, `component_version`, `description`, `label`, `config`).

Capability declaration is `ModelInfo` (`models/_model_client.py:164-182`), a
TypedDict with exactly six keys: `vision`, `function_calling`, `json_output`,
`family`, `structured_output`, `multiple_system_messages`. `validate_model_info:185-207`
enforces the first four and warns on `structured_output`.

`ModelFamily` (`models/_model_client.py:16-95`) is a **hardcoded enum of ~30 named
model families** plus `"unknown"`, with `is_claude`/`is_gemini`/`is_openai`/
`is_llama`/`is_mistral` predicates. **[V]**

**PACT takeaway (negative).** This is the anti-pattern D8 and O3.2 exist to avoid:
capability as a six-key boolean bag, and model identity as a hardcoded enum that
must be edited to add a model. It is also *evidence that the six keys are not
enough* — there is no `audio`, no `computer_use`, no context length, no cost, no
benchmark, no provenance. PACT's catalogue must be data, not an enum.

### 1.10 Harness-lowering seam — **CLEAN**

```
autogen_core.models.ChatCompletionClient.create(
    messages: Sequence[LLMMessage],
    *, tools: Sequence[Tool | ToolSchema] = [],
    tool_choice: Tool | Literal["auto","required","none"] = "auto",
    json_output: Optional[bool | type[BaseModel]] = None,
    extra_create_args: Mapping[str, Any] = {},
    cancellation_token: Optional[CancellationToken] = None,
) -> CreateResult
```
`autogen-core/src/autogen_core/models/_model_client.py:211-239`, streaming twin at
`:241-269`.

This is a **pure model transport**: messages + tools + tool_choice in, content or
function calls out. No agent concepts leak in. It is the cleanest seam of the five
by that criterion.

**But it is a lossy transport**, and the losses are structural, not incidental:

| Loss | Evidence |
|---|---|
| Assistant turn cannot hold text **and** tool calls | `models/_types.py:44` `content: Union[str, List[FunctionCall]]`; the `thought` field at `:47` exists to work around it |
| Tool results are text-only | `models/_types.py:59` `FunctionExecutionResult.content: str` |
| User content is text + images only — no audio, no video, no documents | `models/_types.py:32` `content: Union[str, List[Union[str, Image]]]` |
| Images are PNG/JPEG only | `_image.py:51` `re.match(r"data:image/(?:png\|jpeg);base64,", uri)` |
| Streaming has no tool-call deltas | `models/_model_client.py:251` yields `Union[str, CreateResult]` |

**Verdict: harness lowering onto AutoGen works for text+tools and for vision *input*,
and is `unsupported` for audio, documents, computer use, and partial-tool-argument
streaming.** Those must be lattice entries, not surprises.

---

## 2. OpenAI Agents SDK — Python (0.18.3)

### 2.1 Loop

`run.py:789` — `while True:` inside `AgentRunner._run_...`. Turn accounting at
`run.py:1100-1125`: `current_turn += 1`, and if `max_turns is not None and
current_turn > max_turns`, raise `MaxTurnsExceeded`. The default is
`DEFAULT_MAX_TURNS` (`run.py:210`), defined as **10** at `run_config.py:43`.

The loop is a proper **state machine over four next-steps**
(`run_internal/run_steps.py:155-175`):

- `NextStepHandoff(new_agent)` — swap the running agent.
- `NextStepFinalOutput(output)` — done.
- `NextStepRunAgain()` — call the model again.
- `NextStepInterruption(interruptions: list[ToolApprovalItem])` — **pause**.

**[V] This is the only one of the five frameworks whose loop is an explicit,
named, serialisable step algebra.** It is the closest existing thing to PACT's
`perceive/plan/act/observe/halt` loop IR, and PACT's four core step kinds should be
checked against these four for coverage.

Loop exit is also author-controllable without code:
`agent.py:347-348` — `tool_use_behavior: Literal["run_llm_again","stop_on_first_tool"]
| StopAtTools | ToolsToFinalOutputFunction`, where `StopAtTools` is
`{"stop_at_tool_names": [...]}` (`agent.py:134-135`). Three of the four forms are
declarative. **[V]**

### 2.2 State — **the strongest serialisable-state story in the corpus** [NEW]

`run_state.py` is **3,819 lines** dedicated to one thing: a JSON-serialisable
snapshot of a run.

- `run_state.py:153` — `CURRENT_SCHEMA_VERSION = "1.13"`.
- `run_state.py:155-176` — `SCHEMA_VERSION_SUMMARIES`, a mandatory one-line changelog
  per version, enforced by module-level `raise AssertionError` at `:179-191` if a
  version lacks a summary.
- `run_state.py:146-152` — the written schema policy, including
  *"Forward compatibility is intentionally fail-fast (older SDKs reject newer or
  unsupported versions)."*
- `run_state.py:212-311` — 25 persisted fields, including `_current_turn`,
  `_model_responses`, `_generated_items`, `_session_items`, `_current_step`,
  `_last_processed_response`, `_tool_use_tracker_snapshot`, `_trace_state`,
  `_sandbox`.
- `run_state.py:728` `to_json`, `:1105` `from_string`, `:1146` `from_json`.

**[V] This directly validates three PACT design choices**, and one of them is
a choice PACT has not yet made explicitly:

1. **Versioned run state with a mandatory human-readable changelog** and
   **fail-fast forward incompatibility**. E-2 says "unknown features are rejected
   loudly by old adapters, never ignored" — OpenAI shipped exactly that discipline
   for state, with a machine-enforced changelog. PACT should copy the enforcement
   mechanism (`:179-191`), not just the policy.
2. **The pause boundary is the interruption, and it is part of the state**
   (`_current_step: NextStepInterruption | None`, `:286`).
3. **[NEW] Agent definitions are deliberately *not* in the snapshot.**
   `run_state.py:2714` — `agent_map = _build_agent_map(initial_agent)`; `:2724` —
   `raise UserError(f"Agent {current_agent_name} not found in agent map")`.
   Deserialisation requires a *live* starting agent object; only names are stored.

Point 3 is the important one for PACT. It means the durable artifact splits cleanly
into **(definitions | run state)** — and PACT already owns definitions
deterministically (the tree → IR). So PACT's resume contract should be:
*the lockfile digest identifies the definitions; the run snapshot references it by
digest and stores only run-scoped data.* That is strictly better than what any
framework does, and it costs nothing because the framework already refuses to
serialise definitions.

Context serialisation is explicitly best-effort (`run_state.py:219-224`):
mapping contexts round-trip; custom contexts need a serializer/deserializer; when
neither is available the snapshot is still written but emits warnings. **[D]** PACT
should not permit that third case — under T7 it is silent loss.

### 2.3 Tools — 13 kinds, and a hosted/local split that constrains harness lowering

`tool.py:1455-1469`:

```
Tool = FunctionTool | FileSearchTool | WebSearchTool | ComputerTool[Any]
     | HostedMCPTool | CustomTool | ShellTool | ApplyPatchTool | LocalShellTool
     | ImageGenerationTool | CodeInterpreterTool | ToolSearchTool
     | ProgrammaticToolCallingTool
```

`ProcessedResponse` (`run_internal/run_steps.py:117-131`) buckets a model response
into `handoffs`, `functions`, `computer_actions`, `local_shell_calls`,
`shell_calls`, `apply_patch_calls`, `custom_tool_calls`, `mcp_approval_requests`,
`function_tools_not_found`, `interruptions`.

**The load-bearing comment is at `run_internal/run_steps.py:135`:**

> `# Handoffs, functions and computer actions need local processing`
> `# Hosted tools have already run, so there's nothing to do.`

**[V] Hosted tools (`WebSearchTool`, `FileSearchTool`, `CodeInterpreterTool`,
`ImageGenerationTool`, `HostedMCPTool`) execute server-side inside the model
provider and are already complete when the response arrives.**

**This is a first-order constraint on T3/D12.** Harness lowering says "PACT owns
loop semantics; frameworks are transports." That is true *only for
client-executed tools*. For a hosted tool, the provider has already run a
mini-loop (call → execute → incorporate) that PACT never sees and cannot
intercept, gate, approve, budget, or trace at the step level.

PACT must therefore introduce a **tool execution-locus** attribute —
`execution: client | provider | remote` — as a first-class, *required* field in the
tool IR, and the conformance suite must report loop-ownership per tool, not per
agent. An agent whose tools are all provider-executed is not meaningfully "run by
PACT's loop" no matter what the adapter claims.

**Tool results are content-typed** (`tool.py:193-268`):
`ToolOutputText` (`:193`), `ToolOutputImage` (`:207`, with `image_url` or `file_id`
plus `detail`), `ToolOutputFileContent` (`:236`, with `file_data`/`file_url`/`file_id`
plus `filename`). **[V]** Strictly richer than AutoGen (§1.3).

### 2.4 Structured output — two portability traps

`agent_output.py:53` `AgentOutputSchema`, with `strict_json_schema: bool = True`
by default (`:76`, `__init__` signature at `:78`).

**Trap 1 — non-object outputs are silently wrapped.**
`agent_output.py:14` — `_WRAPPER_DICT_KEY = "response"`; `:66-68` — `_is_wrapped`
*"Whether the output type is wrapped in a dictionary. This is generally done if the
base output type cannot be represented as a JSON Schema object."* So an author
declaring `output_type=list[str]` gets a wire schema of
`{"response": [...]}`. **[V]** A PACT contract that declares an array output will
produce a *different observable JSON shape* on this adapter than on one that
supports root-level arrays.

**Trap 2 — strict mode rewrites the author's schema.** `strict_schema.py`:

- `:88-89` — `if typ == "object" and "additionalProperties" not in json_schema:
  json_schema["additionalProperties"] = False`
- `:92-99` — if `additionalProperties` is present and not `False`, `raise UserError`.
- `:109` — `json_schema["required"] = list(properties.keys())` — **every property
  becomes required**, so optional fields are not expressible.
- `:135` — *"oneOf is not supported by OpenAI's structured outputs in nested contexts"*.

**[V] An output schema that is perfectly legal in PACT and in Pydantic AI can be
rejected outright, or silently have all its optional fields made required, on this
adapter.** This is a schema-portability problem, not a model-portability problem,
and it is invisible unless PACT checks for it.

### 2.5 Streaming — deliberately un-normalised

`stream_events.py:61`:

```python
StreamEvent = RawResponsesStreamEvent | RunItemStreamEvent | AgentUpdatedStreamEvent
```

- `RawResponsesStreamEvent` (`:11-21`) — *"these are 'raw' events, i.e. they are
  directly passed through from the LLM"*, typed `TResponseStreamEvent`, which
  `items.py:82` aliases to `openai.types.responses.ResponseStreamEvent`.
- `RunItemStreamEvent` (`:24-47`) — 10 semantic names, including
  `"handoff_occured"` with a source comment at `:31-32`:
  *"This is misspelled, but we can't change it because that would be a breaking change"*.
- `AgentUpdatedStreamEvent` (`:52-58`).

**[V] The SDK's streaming surface is the OpenAI Responses wire format plus a thin
semantic layer.** There is no provider-neutral event vocabulary. A non-OpenAI model
plugged in here must *emit OpenAI Responses stream events*.

### 2.6 HITL — approval as an interruption, resumed from a snapshot

`NextStepInterruption` (`run_internal/run_steps.py:171-175`) carries
`interruptions: list[ToolApprovalItem]`. `RunState.get_interruptions()`
(`run_state.py:356-363`), `RunState.approve(approval_item, always_approve=False)`
(`:365`), `RunState.reject(...)` (`:371`). Schema `1.6` note (`run_state.py:163`):
*"Persists explicit approval rejection messages across resume flows."*

**[V] This is durable, out-of-process HITL**: serialise → human decides
asynchronously → deserialise → resume. It is the model PACT should adopt.

### 2.7 Memory — sessions as a four-method protocol

`memory/session.py:14` — `Session` `Protocol` with `get_items(limit)` (`:24`),
`add_items(items)` (`:36`), `pop_item()` (`:44`), `clear_session()` (`:52`).
`SessionABC:57` is the ABC twin. Implementations: `sqlite_session.py`,
`openai_conversations_session.py`, `openai_responses_compaction_session.py`.

**[V] This is conversation *history*, not semantic memory.** There is no
`query`/`search` operation and no relevance concept — the opposite of AutoGen's
`Memory.query` (§1.7). Two frameworks, two irreconcilable meanings of the word
"memory". See §7.7.

### 2.8 Multi-agent — handoffs + agents-as-tools

`agent.py:305` — `handoffs: list[Agent[Any] | Handoff[TContext, Any]]`. A handoff
*replaces* the running agent (`NextStepHandoff.new_agent`), so control does not
return. Plus `agent.as_tool(...)` (`agent.py:558-559` shows its
`is_enabled`/`on_stream` parameters), which *does* return.

Guardrails are a separate, four-way policy surface: `input_guardrails` and
`output_guardrails` on the agent (`agent.py:324-329`), plus
`tool_input_guardrail_results` and `tool_output_guardrail_results` threaded through
`SingleStepResult` (`run_internal/run_steps.py:196-200`).

**[V] Four guardrail attachment points (agent-in, agent-out, tool-in, tool-out) is
the finest-grained policy surface in the set.** PACT's policy IR needs all four
attachment points or it cannot import this losslessly (P-3).

### 2.9 Model binding

`models/interface.py` — `Model` ABC (`get_response`, `stream_response`) and
`ModelProvider` ABC (`get_model(model_name) -> Model`). `agent.py:311` —
`model: str | Model | None`; `agent.py:318` — `model_settings: ModelSettings`.
`models/multi_provider.py` routes prefixed names.

There is no capability declaration on `Model` at all — no `ModelInfo` equivalent.
Capability mismatches surface as runtime API errors. **[V]**

### 2.10 Harness-lowering seam — **USABLE BUT LEAKY**

```
agents.models.interface.Model.get_response(
    system_instructions: str | None,
    input: str | list[TResponseInputItem],
    model_settings: ModelSettings,
    tools: list[Tool],
    output_schema: AgentOutputSchemaBase | None,
    handoffs: list[Handoff],
    tracing: ModelTracing,
    *, previous_response_id, conversation_id, prompt,
) -> ModelResponse
```
`models/interface.py` (`get_response`, `stream_response` immediately below).

Two leaks, both consequential:

1. **`handoffs: list[Handoff]` is a parameter of the *model* call.** An agent-level
   orchestration concept is baked into the transport signature. PACT driving this
   seam must either pass `[]` (losing native handoff rendering, which on OpenAI
   models is emitted as tool definitions) or synthesise `Handoff` objects for its
   own topology — i.e. the seam is not topology-neutral.
2. **The wire format is OpenAI Responses.** `items.py:76,79,82` alias
   `TResponseInputItem`/`TResponseOutputItem`/`TResponseStreamEvent` to
   `openai.types.responses.*`. PACT's canonical message IR must be *translated into
   OpenAI Responses items* for this adapter, and the fidelity of that translation is
   the fidelity of the adapter.

**Verdict: harness lowering works, but this adapter costs a full message-format
translation layer that the AutoGen and Vercel adapters do not.** Budget for it.

---

## 3. Claude Agent SDK — Python (0.2.128)

### 3.0 Framing: this is a CLI client, not an agent framework

Total source: 11,298 lines across 24 files. The largest are `types.py` (2,230),
`_internal/sessions.py` (1,925), `_internal/transport/subprocess_cli.py` (1,069)
and `_internal/query.py` (1,034). There is no model client, no message-construction
layer, no loop.

`_internal/transport/subprocess_cli.py:459-663` builds a command line:

- `:463` — `cmd = [self._cli_path, "--output-format", "stream-json", "--verbose"]`
- `:663` — `cmd.extend(["--input-format", "stream-json"])`
- and ~40 flags in between: `--system-prompt` (`:466,468`), `--tools` (`:483,485,488`),
  `--allowedTools` (`:495`), `--max-turns` (`:498`), `--max-budget-usd` (`:501`),
  `--disallowedTools` (`:504`), `--model` (`:510`), `--permission-mode` (`:524`),
  `--resume` (`:536`), `--mcp-config` (`:579`), `--json-schema` (`:659`).

The `Transport` ABC (`_internal/transport/__init__.py`) is `connect` / `write(data: str)` /
`read_messages() -> AsyncIterator[dict]` / `close` / `is_ready` / `end_input`.
Its own docstring: *"This is a low-level transport interface that handles raw I/O
with the Claude process or service."*

**[V] The lowest abstraction the SDK exposes is "write a JSON line to a
subprocess".** The agent loop lives inside the `claude` CLI binary, which is not in
this repo and is not open source.

### 3.1 Loop

Not present in the SDK. Controlled only by flags: `--max-turns`
(`subprocess_cli.py:498`), `--max-budget-usd` (`:501`), `--task-budget` (`:507`),
`--effort` (`:648`), `--thinking` / `--max-thinking-tokens` (`:632-641`).

### 3.2 State

Session-oriented and CLI-owned: `--continue` (`:527`), `--resume=<id>` (`:536`),
`--session-id=` (`:542`), `--fork-session` (`:591`), `--session-mirror` (`:594`).
`_internal/session_resume.py` (536 lines) and `_internal/sessions.py` (1,925 lines)
manage local mirrors of the CLI's transcript.

**[V]** Resume works, but the resumable unit is *the CLI's session*, opaque to the
SDK. There is no step-level state object comparable to `RunState`.

### 3.3 Tools

Three sources: CLI built-ins selected by `--tools`/`--allowedTools`/`--disallowedTools`;
MCP servers via `--mcp-config` (`:579`); and in-process SDK tools —
`SdkMcpTool` (`__init__.py:161`), the `@tool` decorator (`:171`), and
`create_sdk_mcp_server(name, version, tools)` (`:312`), which returns
`McpSdkServerConfig(type="sdk", name=name, instance=server)` (`:525`).

**[V] In-process tools are exposed to the CLI as an MCP server.** So even
locally-defined Python tools travel over MCP. That is architecturally clean and
maps directly onto PACT's MCP-first tool edge (D14) — but it also means PACT
cannot intercept a tool call before MCP dispatch.

### 3.4 Structured output

`ClaudeAgentOptions.output_format` (`types.py:2077-2081`), shape
`{"type": "json_schema", "schema": {...}}`, lowered to `--json-schema <json>`
(`subprocess_cli.py:650-659`). `types.py:1239` — `structured_output: Any = None` on
the result message. **[V]** Same wire shape as the Anthropic beta
`BetaJSONOutputFormatParam` (§4.4) — a real point of convergence.

### 3.5 Streaming

`include_partial_messages: bool = False` (`types.py:1963`) → `--include-partial-messages`
(`subprocess_cli.py:582`); `--include-hook-events` (`:585`) surfaces hook events as
`HookEventMessage` (`types.py:1318`). Messages arrive as parsed JSON dicts from the
subprocess and are converted in `_internal/message_parser.py` (363 lines). **[V]**

### 3.6 HITL — the richest *policy* model, the weakest *loop* control

`can_use_tool: CanUseTool | None` (`types.py:1929`), signature
`(str, dict[str, Any], ToolPermissionContext) -> Awaitable[PermissionResult]`
(`types.py:254-256`). Results:

- `PermissionResultAllow` (`:235-240`, `updated_input` at `:239`) — with `updated_input: dict | None` and
  `updated_permissions: list[PermissionUpdate] | None`. **The callback can rewrite
  the tool's arguments.**
- `PermissionResultDeny` (`:244-249`) — with `interrupt: bool = False`.

`PermissionUpdate` (`types.py:122`) supports `addRules`, `replaceRules`,
`removeRules`, `setMode`, `addDirectories`, `removeDirectories`, with
`PermissionBehavior = "allow" | "deny" | "ask"` (`types.py:110`) and destinations
`userSettings | projectSettings | localSettings | session` (`types.py:106`).
**[V]** This is a full
runtime-mutable permission system — nothing else in the corpus has one.

Ten hook events (`types.py:260-273`): `PreToolUse`, `PostToolUse`,
`PostToolUseFailure`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `PreCompact`,
`Notification`, `SubagentStart`, `PermissionRequest`.

**And a documented footgun**: `types.py:1696-1750` — `_warn_if_can_use_tool_shadowed`
warns that `can_use_tool` *will not be invoked* when `permission_mode` is
`bypassPermissions`, or for tools pre-approved by `allowed_tools` or by settings
files. **[V]** The human gate is silently bypassable by configuration. PACT's
approval-gate IR must make precedence explicit and must fail closed (T7).

Both `can_use_tool` and `hooks` are **synchronous in-process callbacks**, so like
AutoGen (§1.6) this is blocking HITL, not durable HITL.

### 3.7 Memory

`AgentDefinition.memory: Literal["user","project","local"] | None` (`types.py:95`)
— a location selector, not a memory API. CLI-owned. **[V]**

### 3.8 Multi-agent

`ClaudeAgentOptions.agents: dict[str, AgentDefinition] | None` (`types.py:1981`).
`AgentDefinition` (`types.py:84-102`) is itself a small declarative agent spec:
`description`, `prompt`, `tools`, `disallowedTools`, `model`, `skills`, `memory`,
`mcpServers`, `initialPrompt`, `maxTurns`, `background`, `effort`, `permissionMode`.

**[V] This is a genuine competitor-adjacent declarative agent format**, and it is
worth naming alongside Pydantic AI's `AgentSpec` and Oracle's Open Agent Spec in
`00-THESIS.md` §1.3. What it *lacks* is exactly PACT's thesis: no evals, no SLOs,
no capability requirements, no variants, no topology, no I/O schema, and no way to
express anything other than "the parent model may invoke this subagent via the Task
tool."

Subagent invocation is model-driven only; there is no supervisor, no graph, no
handoff. Attribution across parallel subagents is via `agent_id` on tool-lifecycle
hooks (`types.py:283-300`, `_SubagentContextMixin`).

### 3.9 Model binding

`--model` (`subprocess_cli.py:510`) and `--fallback-model` (`:513`). Model aliases
`"sonnet" | "opus" | "haiku" | "inherit"` or a full ID (`types.py:92-93` — the source
comment and field on `AgentDefinition.model`). Anthropic models only. No capability declaration. **[V]**

### 3.10 Harness-lowering seam — **NONE. BLOCKING.**

There is no API in this SDK that accepts a message list and returns a model
response. The entry points are `query(prompt=...)` (`query.py:11-16`) and
`ClaudeSDKClient`. `query`'s prompt parameter is `str | AsyncIterable[dict]` where
each dict is documented (`query.py:46-53`) as:

```python
{"type": "user", "message": {"role": "user", "content": "..."},
 "parent_tool_use_id": None, "session_id": "..."}
```

**[V] Only *user* messages can be injected.** PACT cannot replay an assistant turn
or a tool result into the conversation, so it cannot drive the loop step-by-step
even by degenerate means (the `max_turns=1` + replay trick that works on Vercel and
Anthropic). The decision *"call the model again"* is made inside a closed-source
binary.

**What PACT *can* control:** tool availability (`--tools`/`--allowedTools`),
tool-call approval and argument rewriting (`can_use_tool`), observation
(10 hook events), termination bounds (`--max-turns`, `--max-budget-usd`), the
system prompt, structured output, and the model. That is a large and useful
surface — but it is *policy over someone else's loop*, which is precisely what D12
says PACT must not depend on.

**Independent corroboration.** [NEW] Vercel reached the same conclusion in shipping
code. `packages/harness/src/v1/harness-v1.ts:8-19` describes `HarnessV1` as
*"the integration point for one third-party coding-agent runtime (Claude Code,
Codex, …)"*, and `packages/harness-claude-code/` implements it by spawning the CLI
in a sandbox and talking to it over a WebSocket bridge (`package.json` dependency
`"ws": "^8.21.0"`; `src/claude-code-harness.ts` spawn path exercised throughout
`src/claude-code-harness.test.ts:128-136`). **A competitor with every incentive to
integrate Claude Code natively concluded it can only be wrapped.**

**The decision this forces.** D15 forbids opaque wrapping; D12 requires PACT to own
loop semantics. Both cannot hold for this target. The three honest options:

- **(a) Drop the Claude Agent SDK as an adapter target**, and reach Claude models
  through the Anthropic SDK instead (§4.10), which has a perfect seam. G1 names
  "Anthropic Claude Agent SDK" as a target substrate, so this is a **change to G1**
  and needs an explicit decision.
- **(b) Keep it as an *import-only* target.** `AgentDefinition` (§3.8) and the
  CLI flag surface translate into PACT IR cleanly; PACT then *executes* on the
  Anthropic SDK. This satisfies D15 (translate, don't wrap) and D10 #3.
- **(c) Carve a named exception to D15** for "runtime-hosted agents", exported as
  an A2A endpoint rather than a lowering target — i.e. treat Claude Code as a
  *remote agent PACT can call*, not an agent PACT can *be*.

**Recommendation: (b) as the default, with (c) available as an explicit,
lockfile-recorded escape.** (b) preserves both decisions intact. (c) is honest but
must never be silent — it is exactly the `allowLoss` shape T7 already defines.

---

## 4. Anthropic SDK — Python (0.120.0)

### 4.0 Framing: no longer "just an HTTP client" [NEW]

`src/anthropic/lib/tools/` is 4,995 lines and contains a real agentic loop
(`_beta_runner.py`, 713), a server-driven session tool worker
(`_beta_session_runner.py`, 991), a memory tool (`_beta_builtin_memory_tool.py`, 910),
an agent toolset (`agent_toolset.py`, 842), MCP support (`mcp.py`, 448) and skills
(`_skills.py`, 249). The earlier characterisation of this SDK as a pure transport
understates it.

### 4.1 Loop — `BetaToolRunner`

`lib/tools/_beta_runner.py:272-304`:

```python
def __run__(self) -> Iterator[RunnerItemT]:
    while not self._should_stop():
        with self._handle_request() as item:
            yield item
            message = self._get_last_message()
            ...
        self._iteration_count += 1
        if message.stop_reason == "refusal":
            return
        if not self._check_and_compact():
            response = self.generate_tool_call_response()
            if response is None:
                return
            if not self._messages_modified:
                self.append_messages(message, response)
        self._messages_modified = False
        self._cached_tool_call_response = None
```

Termination: no `tool_use` blocks (`:296-298`), `max_iterations` reached
(`:125-128`), or `stop_reason == "refusal"` (`:289-291`, with a source comment
explaining that executing a refused turn's tool calls *"would fire side effects the
model never confirmed"*). **[V]**

Three properties that diverge from the others:

- **`max_iterations: int | None = None` — the default is unbounded**
  (`_beta_runner.py:74`, `:92`). No default turn cap at all.
- **Tools execute sequentially**: `_generate_tool_call_response:342` —
  `for tool_use in tool_use_blocks:` … `:364` `result = tool.call(tool_use.input)`.
  Contrast AutoGen's unconditional `asyncio.gather` (§1.1). **[V]**
- **Tool exceptions never propagate.** `:366-384` — both `ToolError` and bare
  `Exception` are converted to `{"type":"tool_result", ..., "is_error": True}`.
  The model always sees the failure; the caller never does.

**The loop is externally steerable** — `set_messages_params` (`:96-109`) and
`append_messages` (`:111-123`) mutate the next request between iterations, and
`__next__`/`__anext__` (`:175`, `:464`) let a caller drive it one step at a time.
**[V]** This is a genuine *middle* lowering option: not native, not full harness.

### 4.2 State

No run-state object. State is the `messages` list in `self._params`
(`_beta_runner.py:78-81`), which is plain JSON-serialisable API params.

**[I] This is actually the best durability substrate of the five**, because there
is nothing framework-specific to serialise — the conversation *is* the API request.
PACT can snapshot and resume by persisting its own IR and re-deriving the params.
Marked as inference because I did not find a resume helper in source; the claim is
about what is *possible*, not what ships.

Server-side compaction exists as `edits=[{'type': 'compact_20260112'}]`
(`_beta_runner.py:161-168`, in the deprecation warning for the older client-side
`compaction_control`).

### 4.3 Tools

`tool_registry(tools)` (`_beta_runner.py:77`), dispatch in `_tool_dispatch.py`.
Tools are `BetaRunnableTool` / `BetaAsyncRunnableTool` (`_beta_functions.py`).
Mid-conversation `tool_removal` / `tool_addition` blocks are honoured via
`_available_tool_names()` (`_beta_runner.py:130-138`), whose docstring is precise
and worth quoting:

> *"Removal is only a hint to the model, which can still emit a `tool_use` for a
> withdrawn tool; a name absent from this set routes that call down the same
> unknown-tool path as a tool that was never declared."*

**[V] Dynamic tool exposure is a declared concept here.** PACT's "tool exposure set"
strategy variable (§7.2 of the thesis) has a real precedent, and the precedent is
explicit that removal is advisory — PACT must specify the same thing rather than
implying tools can be revoked.

**Tool results are richly typed.** `types/beta/beta_tool_result_block_param.py`:

```python
Content = Union[BetaTextBlockParam, BetaImageBlockParam,
                BetaSearchResultBlockParam, BetaRequestDocumentBlockParam,
                BetaToolReferenceBlockParam]
```

**[V]** Text, image, search-result, document, tool-reference. Tied with Vercel for
the richest tool-result content model, and far ahead of AutoGen's `str`.

### 4.4 Structured output

`output_format: Optional[BetaJSONOutputFormatParam]`
(`types/beta/message_create_params.py:199`), where
`BetaJSONOutputFormatParam` is `{schema: Dict[str, object], type: Literal["json_schema"]}`
(`types/beta/beta_json_output_format_param.py`).

The typed helper layer adds `ParseMessageCreateParamsBase.output_format: type[ResponseFormatT]`
(`types/beta/message_create_params.py:391-392`) and surfaces
`ParsedBetaMessage.parsed_output` (`types/beta/parsed_beta_message.py:74`) and
`ParsedBetaTextBlock.parsed_output` (`:36-37`).

**[V] There is no `response_format` anywhere in `src/anthropic/`** — a repo-wide
grep returns nothing. The OpenAI-shaped name does not exist here; the shape is
`output_format` + `json_schema`. **PACT's IR must not name this field after either
vendor.**

Note `message_create_params.py:164` — the *"appended-assistant form is not
available for requests with `output_format` set"*, i.e. structured output disables
assistant-prefill. **[D]** A real cross-feature interaction PACT should record.

### 4.5 Streaming

`lib/streaming/_beta_messages.py:343-428` accumulates the Anthropic event stream:
`message_start` (`:343`), `message_delta` (`:345`), `message_stop` (`:347`),
`content_block_start` (`:351`), `content_block_delta` (`:353`),
`content_block_stop` (`:421`). Delta subtypes handled: `text_delta` (`:358`),
`input_json_delta` (`:367`, for `tool_use` and `mcp_tool_use`), citations (`:378`),
`thinking` (`:388`), `signature` (`:398`), `compaction_delta` (`:407`).

**Content blocks are addressed by integer `event.index`** (`:356`, `:422`).
**[V]** Vercel addresses by string `id`; OpenAI Responses uses
`item_id` + `output_index` + `content_index`. Three incompatible addressing schemes
for the same concept — see §7.5.

### 4.6 HITL — exists, but only server-side [NEW]

`lib/tools/_beta_runner.py` has **no** approval or permission concept — grep for
`approval|permission|confirm` in `lib/tools/*.py` returns hits only in
`_beta_session_runner.py` and unrelated filesystem-permission comments.

`_beta_session_runner.py:1-16` (module docstring):

> *"`SessionToolRunner` attaches to a managed-agents session's event stream …
> dispatches every `agent.tool_use` and `agent.custom_tool_use` event against a
> local tool registry, posts the matching result event back … A call the server
> gated behind user confirmation (`evaluated_permission` `ask`, e.g. an
> `always_ask` tool) is held until its `user.tool_confirmation` event arrives —
> executed on `allow`, never executed on `deny`."*

And `:85-86`:

> *"`agent.mcp_tool_use` is intentionally absent — MCP tools run server-side and
> the runner never sees a result to post for them."*

**[V] In the managed-agents mode the loop runs on Anthropic's servers and the SDK
is a local tool *worker*.** This is a full inversion of harness lowering, and it is
**incompatible with D17 (air-gapped)**. PACT must bind to `messages.create`/
`tool_runner`, never to sessions, and the adapter must refuse managed-agents
configuration in air-gapped profiles rather than degrade to it.

### 4.7 Memory

`lib/tools/_beta_builtin_memory_tool.py` (910 lines) implements a filesystem-backed
memory *tool* — memory as something the model calls, not something the harness
injects. **[V]** A third distinct meaning of "memory" in the corpus (§7.7).

### 4.8 Multi-agent

Nothing in the core SDK. `agent_toolset.py` (842 lines) provides a bundled tool set,
not orchestration. Multi-agent exists only in the server-side managed-agents
product surfaced through `types/beta/sessions/`. **[V]**

### 4.9 Model binding

`model` is a string in the request params. No capability declaration, no model
registry, no provider abstraction inside the SDK — though `lib/bedrock`,
`lib/vertex`, `lib/aws`, `lib/google_cloud` and `lib/foundry.py` provide alternate
transports for the same API shape. **[V]**

### 4.10 Harness-lowering seam — **THE CLEANEST OF THE FIVE**

```
client.messages.create(model=..., messages=[...], tools=[...], max_tokens=...)
client.beta.messages.create(..., output_format={"type":"json_schema","schema":{...}})
```

Pure HTTP-shaped model transport. No agent semantics, no framework types, no
handoffs, no output-schema rewriting. Multimodal on both the input side and the
tool-result side (§4.3). Works against any Anthropic-API-compatible endpoint, so it
is air-gap-viable (D17) given a local gateway.

Plus a **second, higher seam**: `client.beta.messages.tool_runner(...)` returning a
`BetaToolRunner` that PACT can drive one iteration at a time via `__next__`
(`_beta_runner.py:175`) while rewriting the next request through
`set_messages_params` (`:96`). **[V]**

**Verdict: this is the reference implementation for what a harness-lowering seam
should look like, and PACT should evaluate adapters against it.** The Vercel
`LanguageModelV4` seam (§5.10) is its equal on normalisation and its superior on
provider breadth.

---

## 5. Vercel AI SDK (`ai@7.0.37`)

### 5.1 Loop — and an internal contradiction [NEW]

`generate-text/generate-text.ts:797` opens a `do { … }` block; the exit condition
is at `:1365-1375`:

```ts
} while (
  ((clientToolCalls.length > 0 &&
    clientToolOutputs.length + deniedToolApprovalResponses.length ===
      clientToolCalls.length) ||
    pendingDeferredToolCalls.size > 0) &&
  !(await isStopConditionMet({ stopConditions, steps }))
);
```

The default is `generate-text.ts:240` — **`stopWhen = isStepCount(1)`**, and
`stop-condition.ts` defines `isStepCount(n)` as `({steps}) => steps.length === stepCount`.

**[V] `generateText`/`streamText` default to a single step: one model call, tools
execute, stop — the model never sees its own tool results.** Functionally identical
to AutoGen's `max_tool_iterations=1` (§1.1), reached by a completely different
mechanism.

But the `Agent` class disagrees with its own SDK:

- `agent/tool-loop-agent.ts:132` — `stopWhen: this.settings.stopWhen ?? isStepCount(20)`
- `agent/tool-loop-agent-settings.ts:88` — `@default isStepCount(20)`
- `agent/tool-loop-agent.ts:37` — *"A stop condition is met (default stop condition is isStepCount(20))"*

**[V] Two different loop defaults inside one SDK: 1 for the function API, 20 for the
Agent class.** If a single SDK cannot keep its own default consistent, PACT
inheriting "the framework default" is not a coherent policy.

`stop-condition.ts` documents four natural terminations besides `stopWhen`:
finish reason other than `tool-calls`; a tool without an `execute` function is
called; a tool call needs approval; a stop condition returns true. The middle two
are the HITL/deferred seam.

Stop conditions are composable (`generate-text.ts:562` `asArray(stopWhen)`,
`stop-condition.ts` `isStopConditionMet` = `.some(...)`) but are **functions**, not
data. `isStepCount`, `isLoopFinished` and `hasToolCall` are the only built-ins.
Compare AutoGen's 12 serialisable conditions (§1.1) — AutoGen is more declarative
here, Vercel more composable.

### 5.2 State

No run-state object and no checkpointer. State is `messages` + `steps`, both plain
data. Resume is by reconstructing the message array — including approval responses
carried as message parts (§5.6). **[V]**

### 5.3 Tools — the richest tool descriptor in the corpus

`packages/provider-utils/src/types/tool.ts`. Fields on a tool:
`title` (`:66`), `providerOptions` (`:73`), `metadata` (`:84`),
`inputSchema` (`:93`), `contextSchema` (`:100`), `needsApproval` (`:107`),
`onInputStart` (`:118`), `onInputDelta` (`:126`), `onInputAvailable` (`:136`),
`toModelOutput` (`:149`), `description` (`:189`), `strict` (`:203`),
`inputExamples` (`:209`).

Three tool kinds, discriminated: `type?: undefined | 'function'` (`:226`),
`type: 'dynamic'` (`:240`), `type: 'provider'` (`:251`, with
`id: \`${string}.${string}\`` at `:256`). Plus `isProviderExecuted: false | true`
(`:283`, `:303`) and `supportsDeferredResults?: boolean` (`:318`).

Two of these have no analogue anywhere else and both matter to PACT:

- **`toModelOutput`** (`:149`) — an author-supplied transform from the tool's return
  value to the content the *model* sees, returning a `ToolResultOutput`. This
  cleanly separates "what the tool returns to the program" from "what the model is
  shown". PACT's tool IR should have this as a declarative field (a template or a
  projection), because it is the single highest-leverage no-code knob for
  small-model portability — §7.3 of the thesis calls this "context discipline", and
  this is where it is actually applied.
- **`inputExamples`** (`:209`) — few-shot examples attached to the tool definition.
  Again a strategy variable that belongs in the IR.

`needsApproval` may be a static status or a runtime function
(`tool-approval-configuration.ts:14-34`), with statuses `'not-applicable'`,
`'user-approval'` and others.

### 5.4 Structured output

`generate-object/generate-object.ts:94-97` — four output strategies:
`'object'`, `'array'`, `'enum'`, `'no-schema'`. Plus
`experimental_repairText` (`:99`) and `inject-json-instruction.ts` for the prompted
fallback. **[V]** Second-richest after Pydantic AI's seven `OutputMode` values (§6.1).

### 5.5 Streaming — the best normalised event vocabulary

`packages/provider/src/language-model/v4/language-model-v4-stream-part.ts`:
`stream-start` (`:30`), `text-start`/`text-delta`/`text-end` (`:17,22,28`),
`reasoning-start`/`reasoning-delta`/`reasoning-end` (`:35,40,46`),
`tool-input-start`/`tool-input-delta`/`tool-input-end` (`:53,62,68`),
`response-metadata` (`:90`), `finish` (`:94`), `raw` (`:102`), `error` (`:108`),
plus the content parts.

**[V] ~18 part kinds with explicit start/delta/end lifecycles, each carrying a
string `id`.** This is the only *provider-neutral* streaming vocabulary in the
corpus — the others are either vendor wire formats (OpenAI Agents §2.5, Anthropic
§4.5) or text-only (AutoGen §1.5).

`LanguageModelV4Content` (`language-model-v4-content.ts`) unions nine content kinds:
text, reasoning, custom, reasoning-file, file, **tool-approval-request**, source,
tool-call, tool-result.

**PACT takeaway.** Adopt this vocabulary as the basis of PACT's streaming IR. It is
a superset of what the other four can emit, it is already provider-neutral, it has
been implemented against ~60 providers in this repo, and it has explicit
start/delta/end framing (which OpenAI's format has and Anthropic's does not, and
which PACT needs for TTFT/TPOT SLO measurement — see `slo-observability.md`).

### 5.6 HITL — approvals carried in the message history

`generate-text/tool-approval-response-output.ts`:

```ts
export type ToolApprovalResponseOutput<TOOLS extends ToolSet> = {
  type: 'tool-approval-response';
  approvalId: string;
  toolCall: TypedToolCall<TOOLS>;
  approved: boolean;
  reason?: string;
  providerExecuted?: boolean;
};
```

And `language-model-v4-prompt.ts:260` carries `type: 'tool-approval-response'` as a
**prompt content part**, with `tool-approval-request` a **model output content
kind** (`language-model-v4-content.ts`).

**[V] Approval is part of the conversation, not part of a side-channel snapshot.**
Resume = append the approval response part to `messages` and call again. Stateless,
serialisable, and requires no framework-specific state object.

This is the third HITL architecture in the set, and it is the one that composes
best with D2 (the tree is the source of truth, no build artifact required):
message-carried approvals need no checkpointer and no runtime.

### 5.7 Memory

**None.** A grep for `memory` across `packages/ai/src` returns three hits, all
about RAM usage (e.g. `agent/tool-loop-agent-settings.ts:261` —
*"Disabling inclusion can help reduce memory usage when processing"*). **[V]**

### 5.8 Multi-agent

**None.** A grep for `handoff|subagent|sub-agent|supervisor` across
`packages/ai/src` returns nothing outside tests. **[V]**

`Agent` is a single tool loop. The separate `@ai-sdk/workflow` package
(`packages/workflow/src/workflow-agent.ts`) provides a `WorkflowAgent`, but that is
durable-execution plumbing, not a topology model.

**Consequence:** the Vercel adapter must *build* multi-agent from scratch out of
PACT primitives. That is an argument **for** harness lowering, not against it — but
it means the Vercel adapter's topology fidelity is entirely PACT's own code, so
CTS coverage for §AC-5.1 patterns on this adapter is testing PACT, not testing
Vercel.

### 5.9 Model binding

`LanguageModelV4` (below) with `provider`, `modelId`, `specificationVersion: 'v4'`
and `supportedUrls: Record<string, RegExp[]>` — a per-media-type declaration of
which URLs the provider can ingest natively rather than downloading.
**[V]** That last one is a genuinely good idea nobody else has and it is directly
relevant to D16 + D17: it tells the harness whether a document/image URL must be
fetched locally (air-gap-relevant) or can be passed through.

Versions `v2`, `v3`, `v4` coexist in `packages/provider/src/language-model/`, i.e.
the provider spec is explicitly versioned and multiple versions ship simultaneously —
the same discipline as OpenAI's `RunState` schema versions (§2.2) and what E-2
asks of PACT.

### 5.10 Harness-lowering seam — **BEST-IN-CLASS**

```ts
type LanguageModelV4 = {
  readonly specificationVersion: 'v4';
  readonly provider: string;
  readonly modelId: string;
  supportedUrls: PromiseLike<Record<string, RegExp[]>> | Record<string, RegExp[]>;
  doGenerate(options: LanguageModelV4CallOptions): PromiseLike<LanguageModelV4GenerateResult>;
  doStream(options: LanguageModelV4CallOptions): PromiseLike<LanguageModelV4StreamResult>;
};
```
`packages/provider/src/language-model/v4/language-model-v4.ts`.

Two methods. No agent concepts. Fully normalised content and stream vocabularies.
~60 provider packages in this repo implement it. The `doGenerate`/`doStream` naming
carries a source comment: *"'do' prefix to prevent accidental direct usage of the
method by the user"* — i.e. it is explicitly the low-level seam.

### 5.11 `HarnessV1` — the anti-pattern PACT is defined against [NEW]

`packages/harness/src/v1/harness-v1.ts:8-19`:

> *"Versioned specification for a harness adapter — the integration point for one
> third-party coding-agent runtime (Claude Code, Codex, …). Modelled after
> `LanguageModelV4`: a tagged spec version, a small set of descriptive fields, and
> one entry-point method (`doStart`) that yields a session. **There is intentionally
> no static "capabilities" object** — optional features are signalled by the presence
> or absence of optional methods on the prompt-control handle. Adapters that cannot
> satisfy a request … throw `HarnessCapabilityUnsupportedError` from the method that
> needs the capability."*

Shipped adapters: `harness-claude-code`, `harness-codex`, `harness-deepagents`,
`harness-opencode`, `harness-pi`.

Fields: `builtinTools` (a `ToolSet` of the wrapped runtime's native tools),
`supportsBuiltinToolApprovals`, `supportsBuiltinToolFiltering`,
`lifecycleStateSchema` (opaque adapter-defined resume state),
`getBootstrap`, `doStart({resumeFrom, continueFrom})`.
`harness-v1-permission-mode.ts`: `'allow-reads' | 'allow-edits' | 'allow-all'`.
`harness-v1-stream-part.ts` adds agent-runtime events absent from
`LanguageModelV4`: `file-change` (`:99`), `compaction` (`:110`), `finish-step` (`:79`).

**Three findings for PACT, in descending importance:**

1. **This is exactly what D15 forbids**, shipped by a serious vendor. The loop lives
   in the wrapped runtime; `builtinTools` is a declaration of *someone else's* tools;
   `lifecycleStateSchema` is opaque resume state PACT could never validate. It is
   the concrete artifact of the "opaque wrapping" road not taken, and it is useful
   to cite in `00-THESIS.md` §1.3 as the alternative design.
2. **Vercel chose runtime capability failure over static capability declaration**,
   deliberately and with a written rationale. PACT's P-2 capability lattice takes
   the opposite position. That is defensible — a static lattice is what makes the
   Conformance Report available *before* execution (AC-2.2) — but the note should
   record that a competitor considered and rejected it, and that the cost PACT is
   accepting is lattice maintenance drift.
3. **`file-change` and `compaction` are real agent-runtime events with no home in
   any model-level IR.** PACT's trace/stream IR needs an extension point for
   runtime-level events, or it will lose them on import from any coding-agent
   source.

---

## 6. Cross-check: Pydantic AI and LangGraph (only what the matrix needs)

### 6.1 Pydantic AI

**Seam.** `pydantic_ai_slim/pydantic_ai/direct.py:55` —
`async def model_request(model, messages, *, model_settings, model_request_parameters, instrument) -> ModelResponse`,
with `model_request_sync:108`, `model_request_stream:164`,
`model_request_stream_sync:227`. Underneath, `models/__init__.py:261` `Model` ABC
with `request` (`:309-310`) and `request_stream` (`:347`).

**[V] Confirmed: a first-class, publicly documented, four-variant low-level model
API.** This is the best *ergonomics* of any seam in the corpus — it is the only one
where the framework authors have deliberately exposed "call a model without an
agent" as a supported public API rather than an internal ABC.

**Structured output is the richest.** `pydantic_ai/output.py:42`:

```python
OutputMode = Literal['text', 'tool', 'native', 'prompted', 'tool_or_text', 'image', 'auto']
StructuredOutputMode = Literal['tool', 'native', 'prompted']   # :48
```

**[V] Seven output modes, including `image` output and an `auto` that selects per
model profile.** Nobody else distinguishes *how* structured output is obtained
(native constrained decoding vs a forced tool vs prompting). This is precisely the
distinction PACT needs, because §7.3 of the thesis lists constrained decoding as
a portability mechanism that is **substrate-bound** — the mode is a *strategy*
variable that must be re-selected per model, and Pydantic AI is the only framework
that already models it as one.

`ModelRequestParameters` (`models/__init__.py:133-165`) also separates
`function_tools` from `native_tools` from `output_tools`, and carries
`allow_text_output`, `allow_image_output`, `instruction_parts` (with a
static/dynamic split *"so models that support granular caching … place cache
boundaries at the static/dynamic instruction boundary"*, `:145-151`) and a resolved
`thinking` level (`:157-163`).

**[V] The static/dynamic instruction split is a cache-optimisation primitive PACT
should adopt** — it costs nothing in the IR (instructions already decompose into
parts under the Expansion Rule) and it is the difference between a cacheable and an
uncacheable prompt on Anthropic and Bedrock, which feeds directly into the D26
performance budget and AC-3.6 cost SLOs.

### 6.2 LangGraph

**Seam.** `libs/langgraph/langgraph/func/__init__.py:262` — `class entrypoint`,
with `checkpointer` (`:439`, `:467`), `task` (`:110`), `entrypoint.final` (`:476`)
and `interrupt` used inside the function body (`:324`, `:351`). Durability is
declared by attaching a checkpointer; HITL is `interrupt()` + `Command(resume=...)`.

**[V] Confirmed.** The functional API lets PACT write its own loop as a plain
Python function and get checkpointing, resume and interrupt for free — which is why
the earlier pass called LangGraph harness lowering *"better than native"*. I concur
on the evidence: `entrypoint(checkpointer=...)` is the only construct in the corpus
that gives PACT durable execution without PACT implementing it.

---

## 7. THE DIVERGENCE MATRIX

Read as: *where do these frameworks disagree in ways a single IR must reconcile?*
Each section ends with the reconciliation PACT must specify. "PACT must decide"
means there is no defensible default to inherit.

### 7.1 Dimension 1 — Loop

| Framework | Default turn budget | Does the model see its own tool results by default? | Termination model |
|---|---|---|---|
| AutoGen | `max_tool_iterations = 1` (`_assistant_agent.py:739,85`) | **No** — `_summarize_tool_use` returns the tool string (`:1317-1324`) | 12 serialisable conditions + And/Or (`conditions/_terminations.py`) |
| OpenAI Agents | `max_turns = 10` (`run.py:210`) | **Yes** | 4-way `NextStep` algebra (`run_steps.py:155-175`) + `tool_use_behavior` (`agent.py:347`) |
| Claude Agent SDK | CLI-owned (`--max-turns`, `subprocess_cli.py:498`) | Yes (inside the CLI) | Opaque |
| Anthropic SDK | `max_iterations = None` — **unbounded** (`_beta_runner.py:74`) | **Yes** | no tool_use / max_iterations / refusal (`_beta_runner.py:289-298`) |
| Vercel `generateText` | `stopWhen = isStepCount(1)` (`generate-text.ts:240`) | **No** | composable `StopCondition` functions |
| Vercel `Agent` | `isStepCount(20)` (`tool-loop-agent.ts:132`) | **Yes** | same |
| Pydantic AI | (cross-check) run-scoped | Yes | — |
| LangGraph | (cross-check) graph-scoped | n/a | graph edges |

**Three incompatible defaults — 1, 10, 20, unbounded — and three frameworks where
the default agent never reasons over its tool output.** Vercel contradicts itself
inside one package.

Two further disagreements at the same level:

- **Tool-call concurrency.** AutoGen: parallel, unconditional
  (`_assistant_agent.py:1200` `asyncio.gather`). Anthropic: sequential, unconditional
  (`_beta_runner.py:342` `for` loop). Neither exposes a choice.
- **Tool error disposition.** Anthropic swallows every exception into an
  `is_error` tool_result (`_beta_runner.py:366-384`). OpenAI Agents has a
  configurable `failure_error_function` (`tool.py:147`). AutoGen returns
  `content=f"Error: {e}"` (`_assistant_agent.py:1551-1556`).

**PACT must decide, and must not default silently.** Recommendations:
1. `loop.max_iterations` is **required** in the IR — no default. A missing value is
   a validation error naming the file and line (O7.3). Inheriting any framework's
   default reproduces that framework's surprise.
2. `loop.tool_results_visible_to_model: true` is the PACT default, because it is
   what authors mean by "agent", and the three frameworks that default otherwise
   are all defaulting to a *non-agent*. Deviating must be explicit.
3. `tools.concurrency: parallel | sequential | <int>` is an IR field. Adapters that
   cannot honour it declare `degraded` — AutoGen cannot do sequential, Anthropic
   cannot do parallel.
4. `tools.on_error: to_model | fail_run | <handler-ref>` is an IR field, defaulting
   to `to_model`.
5. Adopt AutoGen's **termination-condition algebra** as the shape of `loop.halt:`
   (composable, serialisable predicates), not an integer.

### 7.2 Dimension 2 — State and resume

| Framework | Serialisable run state | Granularity | Resume mid-tool-call |
|---|---|---|---|
| AutoGen | message context only (`_assistant_agent.py:1630-1639`) | conversation | **No** |
| OpenAI Agents | `RunState`, `$schemaVersion` `"1.13"`, 25 fields (`run_state.py:153,212-311`) | step + approvals | **Yes** |
| Claude Agent SDK | CLI session (`--resume`, `--fork-session`) | opaque session | Unknown/opaque |
| Anthropic SDK | none (params are the state) | conversation | **[I]** possible, not shipped |
| Vercel | none (messages are the state) | conversation + approval parts | via message replay |
| LangGraph | checkpointer (`func/__init__.py:439`) | super-step | **Yes** |

**Two frameworks give durable step-level resume (OpenAI Agents, LangGraph); two
give message-level replay (Anthropic, Vercel); one gives neither (AutoGen); one is
opaque (Claude).**

**Reconciliation.** PACT's durability IR needs **two levels, declared per agent**:
`durability: none | conversation | step`. AC-2.6 ("resume to the same terminal
state") can only be claimed at `step`, and only on adapters that have it. The
capability lattice must carry it. Critically, PACT should adopt OpenAI's split
(§2.2 point 3): **definitions are identified by lockfile digest and never
serialised into the run snapshot**; only run-scoped data is persisted. That is a
strictly better contract than any framework's and PACT gets it for free.

Also adopt OpenAI's **machine-enforced schema changelog** (`run_state.py:179-191`
raises at import time if a version lacks a summary) for PACT's own state and IR
versions. E-2 currently states the policy; this is the mechanism.

### 7.3 Dimension 3 — Tools

| Framework | Tool kinds | Tool-result content | Execution locus declared? | Dynamic exposure |
|---|---|---|---|---|
| AutoGen | Workbench tools + handoff tools | **`str` only** (`models/_types.py:59`) | No | No |
| OpenAI Agents | **13** (`tool.py:1455-1469`) | text / image / file (`tool.py:193-268`) | Implicitly (hosted vs local, `run_steps.py:135`) | `is_enabled` |
| Claude Agent SDK | CLI builtins + MCP + SDK-MCP | MCP content | No | `--allowedTools` |
| Anthropic SDK | runnable tools + server tools | text/image/search-result/document/tool-reference | Partially (`_beta_session_runner.py:85-86`) | **Yes**, advisory (`_beta_runner.py:130-138`) |
| Vercel | 3 (`function`/`dynamic`/`provider`) + `isProviderExecuted` | text/json/content(text,file,custom)/error/denied (`language-model-v4-prompt.ts:293-402`) | **Yes, explicitly** | `activeTools`, `prepareStep` |

**Three disagreements a single IR must reconcile:**

1. **Tool-result content type.** `str` (AutoGen) vs five content kinds (Anthropic,
   Vercel). This is not cosmetic: it is the difference between computer use working
   and not working (§1.3).
2. **Execution locus.** Vercel declares it (`isProviderExecuted`), OpenAI implies it
   (`run_steps.py:135`), the rest ignore it. **This is the single most important
   missing concept**, because it bounds what harness lowering can mean at all.
3. **Result projection.** Only Vercel has `toModelOutput` (`tool.ts:149`) — a
   declared transform from tool return value to model-visible content.

**Reconciliation.** PACT's tool IR requires, as *mandatory* fields:
- `execution: client | provider | remote` — required, no default. Adapters must
  reject an agent whose tool execution locus they cannot honour.
- `result_content: [text|image|audio|document|json|binary]` — content-typed per G-1.
- `to_model:` — a declarative projection (template/JSONPath/`ref:`) from result to
  model-visible content, defaulting to identity. This is the no-code expression of
  "context discipline" and it is a strategy variable the optimiser can search.
- `concurrency`, `on_error` per §7.1.
- Optional `input_examples:` (Vercel `tool.ts:209`) — also an optimiser target.

And the **Conformance Report must report loop ownership per tool**, not per agent:
an agent whose tools are all provider-executed is not running PACT's loop in any
meaningful sense, whatever the adapter's lattice says.

### 7.4 Dimension 4 — Structured output

| Framework | Mechanism | Modes | Schema mangling |
|---|---|---|---|
| AutoGen | `json_output: bool \| type[BaseModel]` (`_model_client.py:218`) | 3 (off/json/structured) | none; but flips `reflect_on_tool_use` (`:842-844`) |
| OpenAI Agents | `output_type` → `AgentOutputSchema` | strict / non-strict | **Yes** — wraps non-objects in `{"response":…}` (`agent_output.py:14`); forces `additionalProperties:false` and **all-required** (`strict_schema.py:88,109`); rejects nested `oneOf` (`:135`) |
| Claude Agent SDK | `--json-schema` (`subprocess_cli.py:659`) | 1 | unknown (CLI) |
| Anthropic SDK | `output_format: {type:"json_schema", schema}` (`message_create_params.py:199`) | 1 | none; disables assistant-prefill (`:164`) |
| Vercel | `generateObject` | 4: object/array/enum/no-schema (`generate-object.ts:94-97`) | none; `experimental_repairText` (`:99`) |
| Pydantic AI | `output_mode` | **7** incl. `image`, `auto` (`output.py:42`) | none |

**The reconciliation problem is not the field name — it is that the same declared
schema produces different wire schemas and different agent behaviour per target.**

**PACT must specify:**
1. **`output.mode: auto | native | tool | prompted`**, adopting Pydantic AI's
   taxonomy (`output.py:48`). `auto` resolves against the model catalogue at resolve
   time. This makes constrained decoding — a substrate-bound mechanism per thesis
   §7.3 — an explicit, re-selectable strategy variable rather than a hidden one.
2. **A schema-portability pre-flight in `pact resolve`.** Before binding, check the
   author's output schema against the target's structured-output profile
   (root type must be object? optional fields allowed? `oneOf` allowed? `additionalProperties` allowed?).
   Violations are a **resolve-time FAIL with a recommendation** (D11), not a
   runtime surprise. This is cheap, fully offline (D17), and catches a class of bug
   nothing else in the ecosystem catches.
3. **Never silently wrap.** If a target cannot express a root-level array, that is
   a reported loss (T7), not an invisible `{"response": …}`.
4. Record the cross-feature interaction: on Anthropic, structured output disables
   assistant-prefill; on AutoGen, it changes the loop.

### 7.5 Dimension 5 — Streaming

| Framework | Vocabulary | Normalised? | Block addressing | Tool-arg deltas |
|---|---|---|---|---|
| AutoGen | `str \| CreateResult` (`_model_client.py:251`) | n/a (text only) | none | **No** |
| OpenAI Agents | OpenAI Responses events + 10 run-item names (`stream_events.py`) | **No** — raw passthrough (`:11-21`) | `item_id`+`output_index`+`content_index` | Yes |
| Claude Agent SDK | CLI `stream-json` + partial messages (`subprocess_cli.py:582`) | No | n/a | Yes |
| Anthropic SDK | 6 event types + 7 delta subtypes (`lib/streaming/_beta_messages.py:343-428`) | vendor-shaped | integer `event.index` | Yes (`input_json_delta`, `:367`) |
| Vercel | ~18 parts, start/delta/end, string `id` (`language-model-v4-stream-part.ts`) | **Yes, provider-neutral** | string `id` | Yes (`tool-input-*`) |

**Three incompatible addressing schemes for "which content block is this delta
for": integer index, string id, and a triple.** Any IR that streams must pick one
and specify the mapping in both directions for every adapter.

**Reconciliation.** Adopt the **Vercel `LanguageModelV4` stream-part vocabulary**
as PACT's streaming IR, with string `id` addressing:
- It is the only provider-neutral one, already implemented against ~60 providers.
- Its start/delta/end framing is what TTFT/TPOT measurement needs (AC-4.2/AC-3.6).
- Mapping Anthropic's integer index → string id is mechanical; mapping OpenAI's
  triple → string id is mechanical; mapping AutoGen's `str` chunks is a *lossy
  degrade* that the lattice must declare (`tool_arg_streaming: unsupported`).
- Extend it with the two agent-runtime events `HarnessV1` needed and
  `LanguageModelV4` lacks — `file-change` and `compaction`
  (`harness-v1-stream-part.ts:99,110`) — or PACT loses them on import.

### 7.6 Dimension 6 — HITL

**Four architecturally distinct models. This is the widest divergence in the set
after the loop.**

| Framework | Mechanism | Durable? | Can rewrite tool input? | Serialisable declaration? |
|---|---|---|---|---|
| AutoGen | `input_func` callback (`_user_proxy_agent.py:169`) | **No** (blocking) | No | **No** — `input_func=None` on round-trip (`:244-245,249`) |
| OpenAI Agents | `NextStepInterruption` + `RunState.approve/reject` (`run_steps.py:171`, `run_state.py:365,371`) | **Yes** | No | via RunState |
| Claude Agent SDK | `can_use_tool` → `PermissionResultAllow(updated_input=…)` (`types.py:235-240`) | No (blocking) | **Yes** | No (callback); but `permission_mode` + rules are data |
| Anthropic SDK | none locally; server-side `user.tool_confirmation` (`_beta_session_runner.py:9-11`) | server-side | No | n/a |
| Vercel | `tool-approval-request`/`-response` **as message parts** (`language-model-v4-prompt.ts:260`) | **Yes**, statelessly | No | **Yes** — it is data |
| LangGraph | `interrupt()` + checkpointer | **Yes** | via `Command(resume=…)` | No (code) |

Plus the Claude SDK's **runtime-mutable permission rules** (`PermissionUpdate`:
addRules/replaceRules/removeRules/setMode/addDirectories/removeDirectories across
four destinations, `types.py:106-133`), which nothing else has, and its documented
**shadowing footgun** (`types.py:1696-1750`): `can_use_tool` is silently skipped
under `bypassPermissions` or for pre-allowed tools.

**Reconciliation — this is where PACT should be opinionated, because the best
answer is clear:**

1. **Adopt Vercel's message-carried approval model as the IR's normative form.**
   An approval request and its response are *content parts in the conversation*.
   Consequences: HITL is serialisable by construction; it needs no checkpointer, no
   runtime and no framework state object; it works on the four frameworks that have
   no durable state; and it satisfies D2 (the tree is the source of truth, nothing
   external required).
2. **Approval gates are declared on the tool, not written as a callback** —
   `approval: never | always | <predicate>` in the tool IR, per D14 (no-code).
   AutoGen's `input_func=None` round-trip hole (§1.6) is the proof that callbacks
   are not a portable HITL model.
3. **Argument rewriting must be in the IR** (`updated_input`, Claude SDK
   `types.py:239`) — a human approving "with edits" is a real workflow that only
   one framework supports and that PACT must not lose on import (P-3).
4. **Precedence must be explicit and fail-closed.** The Claude shadowing warning is
   a genuine security bug shape: a configured allow-rule silently disabling a human
   gate. PACT's policy IR must define a total precedence order over
   (mode, allow-rules, per-tool approval, run-scoped override) and must **fail
   closed** — if any layer says "ask", the answer is "ask" (T7).
5. **Blocking-callback HITL is a `degraded` lattice entry, not a supported mode.**

### 7.7 Dimension 7 — Memory: the word means four different things

| Framework | What "memory" is | Operations |
|---|---|---|
| AutoGen | **context injection** — mutates the model context pre-call | `update_context`, `query`, `add` (`memory/_base_memory.py:77,93,113`) |
| OpenAI Agents | **conversation history store** | `get_items`, `add_items`, `pop_item`, `clear_session` (`memory/session.py:24,36,44,52`) |
| Anthropic SDK | **a tool the model calls** (`_beta_builtin_memory_tool.py`, 910 lines) | tool invocations |
| Claude Agent SDK | **a location** — `Literal["user","project","local"]` (`types.py:95`) | n/a |
| Vercel | **absent** | — |

**[V] Five frameworks, four incompatible meanings, one of which is "nothing".**
Only AutoGen's has a relevance/query notion; only OpenAI's has ordered history
semantics with `pop`; only Anthropic's is model-driven.

**Reconciliation.** PACT must **not** ship a field called `memory:` with a single
meaning — it is the most overloaded word in the domain and D13's non-technical
author will guess wrong. Split it into three orthogonal, separately-declared
constructs:

- `history:` — the conversation record. Ordered, with retention/compaction policy.
  Maps to OpenAI `Session`, Vercel `messages`, AutoGen `model_context`.
- `recall:` — retrieval injected into context before a call, with a declared
  relevance strategy and a **budget**. Maps to AutoGen `Memory.update_context`.
- `notes:` — a store the *model* reads and writes through tools. Maps to
  Anthropic's memory tool and Claude's `memory` location.

Each is independently portable and independently `unsupported`-able. Collapsing
them is how a spec becomes unimplementable, and it is also how an author gets a
different agent on every adapter.

### 7.8 Dimension 8 — Multi-agent

| Framework | Constructs | Control returns? | Serialisable? |
|---|---|---|---|
| AutoGen | RoundRobin, Selector, Swarm, **GraphFlow** (DAG + cycles) | Swarm: no; Graph: per edge | **Mostly** — but callable edge conditions are dropped (`_digraph_group_chat.py:47,69-79`) and `selector_func`/`candidate_func` are code (`_selector_group_chat.py:163-186`) |
| OpenAI Agents | handoffs + agent-as-tool | handoff: **no**; as-tool: yes | handoff targets are agent objects |
| Claude Agent SDK | `agents: dict[str, AgentDefinition]` (`types.py:1981,84-102`) | subagent returns | **Yes** — fully declarative |
| Anthropic SDK | **none** in-SDK | — | — |
| Vercel | **none** (`packages/ai/src`) | — | — |
| LangGraph | graph | per edge | code |

**[V] Two of the five target frameworks have no multi-agent construct at all.**
D20's first demo — a non-technical author builds a supervisor plus specialists —
is therefore **entirely PACT's own implementation** on the Vercel and Anthropic
adapters. That is the correct outcome under D12, but it must be stated: CTS
topology results on those adapters test PACT's harness, not the framework.

The one genuinely reusable design is AutoGen's `GraphFlow` join semantics:
`activation: "all" | "any"` on nodes (`_digraph_group_chat.py:112`),
`activation_group` + `activation_condition` on edges (`:48,58`), and the rule that
every cycle must contain at least one conditional edge (`:151`).

**Handoff conflict semantics diverge and must be decided:** AutoGen executes only
the first of multiple handoff calls and warns (`_assistant_agent.py:1347-1362`);
OpenAI Agents resolves to a single `NextStepHandoff`. PACT must specify — recommend
**error, not silent first-wins**, consistent with the Expansion Rule's
disjoint-union stance (E-rules: "conflict is an error, never last-wins").

### 7.9 Dimension 9 — Model binding and capability

| Framework | Capability declaration | Model identity |
|---|---|---|
| AutoGen | `ModelInfo` — **6 boolean-ish keys** (`_model_client.py:164-182`) | `ModelFamily` **hardcoded enum**, ~30 values (`:16-95`) |
| OpenAI Agents | **none** on `Model` | string + `MultiProvider` prefixes |
| Claude Agent SDK | none | `--model`, aliases `sonnet/opus/haiku/inherit` |
| Anthropic SDK | none | string |
| Vercel | `supportedUrls` per media type; spec version `v2/v3/v4` | `provider` + `modelId` |
| Pydantic AI | model profiles drive `output_mode: auto` | `KnownModelName \| str` |

**[V] No framework in the set declares context length, cost, latency, benchmark
scores, audio capability, or computer-use capability.** AutoGen comes closest with
six keys and pays for it with a hardcoded enum that must be edited to add a model.

**Reconciliation.** This is a clean win for PACT rather than a reconciliation
problem: **the model catalogue (O3.2) has no competitor in the corpus.** The
findings that shape it:
- Capability must be **data, never an enum** — AutoGen's `ModelFamily` is the
  anti-pattern, and `family` is doing double duty as identity *and* capability.
- Adopt Vercel's `supportedUrls` idea as a catalogue field: which media types the
  binding can ingest by URL vs must have inlined. It is directly load-bearing for
  D17 (air-gapped: nothing may be fetched) and D16 (documents/images).
- The six AutoGen keys are the *floor*, not the ceiling: PACT needs at minimum
  `vision`, `audio_in`, `audio_out`, `computer_use`, `function_calling`,
  `parallel_tool_calls`, `structured_output: {native|tool|prompted}`,
  `context_window`, `max_output`, plus benchmarks with provenance (AC-3.3).

### 7.10 Modality coverage (D16) — three of five fail

| Modality | AutoGen | OpenAI Agents | Claude SDK | Anthropic SDK | Vercel |
|---|---|---|---|---|---|
| Text + tools | Yes | Yes | Yes | Yes | Yes |
| Vision **in** | Yes, PNG/JPEG only (`_image.py:51`) | Yes | Yes | Yes | Yes (`file` content) |
| Vision **out** (tool→model) | **No** — flattened to `"[Image: b64]"` (`_workbench.py:70-74`) | Yes (`ToolOutputImage`, `tool.py:207`) | via MCP | Yes (`BetaImageBlockParam`) | Yes (`content` output) |
| Documents | **No** | Yes (`ToolOutputFileContent`, `tool.py:236`) | via MCP | Yes (`BetaRequestDocumentBlockParam`) | Yes (`file`, incl. `application/pdf` in `supportedUrls`) |
| Audio / voice | **No** — no `audio` in `autogen-core`; only a video-surfer *tool* in `autogen-ext` | **Yes** — `voice/` + `realtime/` packages | **No** | **No** — `audio` appears only in `lib/tools/mcp.py` passthrough | **Yes** — `generate-speech/`, `transcribe/`, `realtime/` |
| Computer use | **No** on the portable path (§1.3); bespoke `MultimodalWebSurfer` only | **Yes** — `ComputerTool` (`tool.py:761`) | via CLI builtins | via tools | via provider tools |

**[V] Only OpenAI Agents and Vercel can express all four D16 modalities. AutoGen
can express one and a half.**

**Consequence for the CTS.** AC-2.1 requires a golden agent set covering the
modalities on all seven adapters. That is not achievable and should not be
attempted. The honest form is: **the golden set is partitioned by modality, and
the conformance level an adapter can reach is bounded by its modality support**,
declared in the lattice before execution (AC-2.2's second clause). PACT should
publish a modality × adapter matrix as a first-class artifact, because it is the
single most useful thing an adopter needs before choosing a target.

---

## 8. Harness-lowering seam table (the brief's explicit question)

| Framework | Exact lowest-level API | Neutral? | Verdict |
|---|---|---|---|
| **AutoGen** | `autogen_core.models.ChatCompletionClient.create(messages, *, tools, tool_choice, json_output, extra_create_args, cancellation_token) -> CreateResult` and `.create_stream(...) -> AsyncGenerator[str \| CreateResult]` — `autogen-core/src/autogen_core/models/_model_client.py:211-269` | **Yes** — no agent concepts | **USABLE, LOSSY.** Text+tools+vision-in only. No audio, no documents, no image tool-results, no tool-arg streaming, no text+tool-calls in one turn |
| **OpenAI Agents** | `agents.models.interface.Model.get_response(system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, *, previous_response_id, conversation_id, prompt) -> ModelResponse` and `.stream_response(...)` — `src/agents/models/interface.py` | **No** — takes `handoffs`; I/O is OpenAI Responses format (`items.py:76,79,82`) | **USABLE, LEAKY.** Costs a full message-format translation layer; topology leaks into the transport signature |
| **Claude Agent SDK** | *none* — lowest is `Transport.write(data: str)` to a subprocess (`_internal/transport/__init__.py`); `query(prompt=...)` accepts **user messages only** (`query.py:46-53`) | n/a | **NONE — BLOCKING** (§3.10). Loop is in a closed-source binary. Corroborated by Vercel's `harness-claude-code` wrapping rather than translating |
| **Anthropic SDK** | `client.messages.create(...)` / `client.beta.messages.create(..., output_format=…)`; plus steerable `client.beta.messages.tool_runner(...)` → `BetaToolRunner.__next__` (`lib/tools/_beta_runner.py:175`) with `set_messages_params` (`:96`) | **Yes** | **BEST-IN-CLASS (Python).** Fully multimodal both directions; two seams (pure transport + steerable loop); air-gap-viable |
| **Vercel AI SDK** | `LanguageModelV4.doGenerate(options)` / `.doStream(options)` — `packages/provider/src/language-model/v4/language-model-v4.ts` | **Yes** — fully normalised | **BEST-IN-CLASS (TS).** Provider-neutral content + stream vocabularies; ~60 implementations; explicitly the intended low-level seam |
| Pydantic AI *(cross-check)* | `pydantic_ai.direct.model_request` / `_sync` / `_stream` / `_stream_sync` — `pydantic_ai_slim/pydantic_ai/direct.py:55,108,164,227` | Yes | **CLEAN.** The only publicly-documented, four-variant "call a model without an agent" API in the corpus |
| LangGraph *(cross-check)* | `langgraph.func.entrypoint(checkpointer=…)` + `task` + `interrupt` — `libs/langgraph/langgraph/func/__init__.py:110,262,439` | Yes | **BETTER THAN NATIVE.** The only construct that gives PACT durable execution + resume + interrupt without implementing them |

**Summary: 6 of 7 target frameworks have a clean or usable harness-lowering seam.
One does not, and no amount of adapter engineering fixes it.**

---

## 9. Blocking and near-blocking findings

**B1 — BLOCKING. The Claude Agent SDK has no harness-lowering seam.** §3.10.
There is no API accepting a message list and returning a model response; `query`
accepts user messages only (`query.py:46-53`); the loop is in a closed-source
binary. D12 (PACT owns loop semantics) and D15 (translate or nothing) cannot both
hold for this target. **Requires an explicit decision** — recommended: import-only
target, execute on the Anthropic SDK (§3.10 option (b)). Corroborated by Vercel's
`harness-claude-code` choosing to wrap rather than translate.

**B2 — BLOCKING for D16. AutoGen cannot return an image to the model.**
`_assistant_agent.py:1609` calls `tool_result.to_text()`, which renders an image as
the literal string `f"[Image: {base64}]"` (`_workbench.py:70-74`), and
`FunctionExecutionResult.content` is `str` (`models/_types.py:59`). Computer use and
any screenshot-returning tool are impossible on AutoGen's portable path.

**B3 — BLOCKING for D17. Anthropic managed-agents sessions run the loop
server-side.** `_beta_session_runner.py:1-16`; MCP tools run server-side and never
surface (`:85-86`). The adapter must refuse this mode in air-gapped profiles rather
than silently degrade.

**B4 — NEAR-BLOCKING. Harness lowering does not bound provider-executed tools.**
`run_internal/run_steps.py:135` — *"Hosted tools have already run, so there's
nothing to do."* PACT's loop cannot gate, approve, budget or trace a tool the
provider already executed. Requires a mandatory `execution:` field in the tool IR
and per-tool loop-ownership reporting in the Conformance Report (§7.3).

**B5 — NEAR-BLOCKING. Three of five frameworks default to a loop where the model
never sees its own tool results.** AutoGen `max_tool_iterations=1`
(`_assistant_agent.py:739`); Vercel `generateText` `stopWhen=isStepCount(1)`
(`generate-text.ts:240`); and Vercel contradicts itself with `isStepCount(20)` on
`Agent` (`tool-loop-agent.ts:132`). There is no framework default PACT can inherit.

**B6 — MAJOR. OpenAI strict-mode rewrites author schemas.**
`strict_schema.py:109` forces every property to be required; `:88-99` forces
`additionalProperties: false` or errors; `:135` rejects nested `oneOf`;
`agent_output.py:14` silently wraps non-object outputs in `{"response": …}`. The
same PACT contract produces a different observable output shape per adapter unless
a resolve-time schema pre-flight is added.

**B7 — MAJOR. AutoGen cannot resume mid-tool-call.** `save_state` persists only the
model context (`_assistant_agent.py:1630-1639`). AC-2.6 is unachievable on that
adapter; it must declare `durable_resume: unsupported`.

**B8 — MAJOR. Human-gate bypass by configuration.**
`claude-agent-sdk-python/src/claude_agent_sdk/types.py:1696-1750` warns that
`can_use_tool` is **not invoked** under `bypassPermissions` or for tools allowed by
`allowed_tools` or settings files. A configured allow-rule silently disables a human
approval gate. PACT's policy IR needs a total, fail-closed precedence order.

**B9 — MAJOR. "Memory" has four incompatible meanings across five frameworks**
(§7.7), one of which is "does not exist". A single `memory:` field would produce a
different agent on every adapter and would mislead the D13 non-technical author.

**B10 — MAJOR. Callback-shaped constructs are not serialisable, and the frameworks
know it.** AutoGen's `UserProxyAgent._to_config` returns `input_func=None` with a
`# TODO: Add ability to serialie input_func` (`_user_proxy_agent.py:244-245`);
`DiGraphEdge` moves callables into an `exclude=True` field so the model serialises
(`_digraph_group_chat.py:47,69-79`); `SelectorGroupChat`'s `selector_func` is code.
Every one of these is a place where a "declarative" config silently loses
behaviour — the exact failure mode D14 and T7 exist to prevent.

**B11 — MODERATE. Two of five target frameworks have no multi-agent construct at
all** (Anthropic SDK, Vercel AI SDK — §7.8). D20's supervisor demo is entirely
PACT's own code on those adapters.

**B12 — MODERATE. Three incompatible stream-block addressing schemes** — integer
index (Anthropic `_beta_messages.py:356`), string id (Vercel), triple
(OpenAI Responses). Any streaming IR must pick one and specify bidirectional
mappings, with AutoGen declared `unsupported` for tool-arg deltas.

**B13 — MODERATE. AutoGen is frozen** (`README.md:14,19-24`, HEAD 2026-04-06).
Treat as a legacy import target; do not spend native-lowering budget on it.

---

## 10. Design implications for PACT (actionable)

Each is written as something a spec author can implement.

**DI-1. `loop.max_iterations` is a required IR field with no default.**
A missing value is a validation error naming file, line, rule and fix (O7.3).
Rationale: the corpus offers 1, 10, 20 and unbounded, and one SDK contradicts
itself (B5). Silence is the one thing PACT must not inherit.

**DI-2. `loop.tool_results_visible_to_model` defaults to `true`, and deviation is
explicit.** Three frameworks default to a non-agent (B5). PACT's default must match
what the D13 author means by "agent".

**DI-3. Adopt AutoGen's termination-condition algebra as the shape of `loop.halt:`.**
Composable, serialisable predicates (`conditions/_terminations.py`, 12 conditions +
And/Or) rather than an integer. Exclude the callable form (`FunctionalTermination`
has no `Config` and does not serialise) and provide a typed `ref:` escape instead
(F-2).

**DI-4. Add `execution: client | provider | remote` as a REQUIRED field on every
tool.** No default. Adapters reject agents whose execution locus they cannot honour.
Rationale: B4 — harness lowering is only faithful for client-executed tools.

**DI-5. The Conformance Report reports loop ownership per tool, not per agent.**
An agent whose tools are all provider-executed is not running PACT's loop, and the
report must say so before execution (AC-2.2).

**DI-6. Content-type tool results: `[text|image|audio|document|json|binary]`.**
Adapters that flatten to text declare `degraded` with the specific loss named.
Rationale: B2 — AutoGen renders images as `"[Image: b64]"`, which silently breaks
computer use.

**DI-7. Add a declarative `to_model:` projection on tools** (template / JSONPath /
`ref:`), defaulting to identity, modelled on Vercel's `toModelOutput`
(`tool.ts:149`). This is the no-code expression of "context discipline" from thesis
§7.3 and it is a first-class optimiser search target. Add `input_examples:`
(`tool.ts:209`) for the same reason.

**DI-8. Add `tools.concurrency: parallel | sequential | <int>` and
`tools.on_error: to_model | fail_run | <ref>`.** AutoGen is parallel-only
(`_assistant_agent.py:1200`), Anthropic sequential-only (`_beta_runner.py:342`);
neither exposes a choice, so both become lattice entries.

**DI-9. Adopt Pydantic AI's `output.mode: auto | native | tool | prompted`**
(`output.py:48`). Constrained decoding is substrate-bound (thesis §7.3), so *how*
structured output is obtained must be a re-selectable strategy variable, not an
implementation detail.

**DI-10. Add a resolve-time schema-portability pre-flight.** Before binding, check
the author's output schema against the target's structured-output profile
(root-type restrictions, optional fields, `oneOf`, `additionalProperties`) and emit
a **FAIL + recommendation** (D11). Rationale: B6. Fully offline (D17), cheap, and
catches a class of bug no other tool catches.

**DI-11. Never silently wrap or mangle an author schema.** If a target cannot
express a root-level array, that is a reported loss (T7), not an invisible
`{"response": …}` (`agent_output.py:14`).

**DI-12. Adopt the Vercel `LanguageModelV4` stream-part vocabulary as PACT's
streaming IR**, with string-`id` block addressing, and extend it with `file-change`
and `compaction` from `HarnessV1` (`harness-v1-stream-part.ts:99,110`). Specify
bidirectional mappings to Anthropic's integer index and OpenAI's triple; declare
AutoGen `unsupported` for tool-argument deltas.

**DI-13. Adopt Vercel's message-carried approval model as the normative HITL form.**
`tool-approval-request` (model output content) and `tool-approval-response`
(prompt content part) — `language-model-v4-prompt.ts:260`. Consequences: HITL is
serialisable by construction, needs no checkpointer or runtime, works on the four
frameworks with no durable state, and satisfies D2.

**DI-14. Approval gates are declared on the tool** (`approval: never | always |
<predicate>`), never written as a callback. Rationale: B10 — AutoGen's
`input_func=None` round-trip hole is the proof.

**DI-15. Carry human argument-rewriting in the IR** (`updated_input`, Claude SDK
`types.py:239`). One framework supports "approve with edits"; P-3 forbids dropping
it on import.

**DI-16. Define a total, fail-closed precedence order over approval layers**
(mode → allow-rules → per-tool approval → run override). If any layer says "ask",
the answer is "ask". Rationale: B8.

**DI-17. Split `memory:` into `history:`, `recall:` and `notes:`.** Rationale: B9 —
four incompatible meanings across five frameworks. Each is independently portable
and independently `unsupported`-able; collapsing them guarantees a different agent
per adapter.

**DI-18. Declare durability as `durability: none | conversation | step`.**
AC-2.6 may only be claimed at `step`, and only on adapters that have it
(OpenAI Agents, LangGraph). AutoGen declares `unsupported` (B7).

**DI-19. Split the run snapshot: definitions by lockfile digest, run-scoped data
only.** OpenAI Agents already refuses to serialise agent definitions
(`run_state.py:2714,2724` require a live starting agent), and PACT derives
definitions deterministically from the tree. This yields a strictly better resume
contract than any framework's, for free.

**DI-20. Adopt OpenAI's machine-enforced schema changelog for PACT's IR and state
versions.** `run_state.py:179-191` raises at import time if a shipped version lacks
a one-line summary; `:146-152` documents fail-fast forward incompatibility. E-2
states this as policy; this is the mechanism that makes it true.

**DI-21. Adopt AutoGen's `GraphFlow` join vocabulary for the topology IR** —
node `activation: all | any` (`_digraph_group_chat.py:112`), edge
`activation_group` + `activation_condition` (`:48,58`), and the rule that every
cycle must contain at least one conditional edge (`:151`). Reject the callable
edge condition, which is dropped on serialisation (`:47,69-79`).

**DI-22. Specify multiple-handoff conflict as an ERROR, not first-wins.**
AutoGen executes the first and warns (`_assistant_agent.py:1347-1362`). Consistent
with the Expansion Rule's disjoint-union stance: conflict is an error, never
last-wins.

**DI-23. Model capability is data, never an enum.** AutoGen's `ModelFamily`
(`_model_client.py:16-95`) is the anti-pattern and conflates identity with
capability. The catalogue's minimum key set exceeds AutoGen's six by
`audio_in`/`audio_out`/`computer_use`/`parallel_tool_calls`/`context_window`/
`max_output`/`structured_output: {native|tool|prompted}` plus provenanced benchmarks
(AC-3.3).

**DI-24. Add `supported_urls` (per media type) to the model catalogue**, modelled on
`LanguageModelV4.supportedUrls`. It determines whether a document/image URL must be
inlined locally — directly load-bearing for D17 (air-gapped: nothing may be fetched).

**DI-25. Publish a modality × adapter matrix as a first-class artifact, and
partition the golden set by modality.** Only 2 of 5 frameworks support all four D16
modalities (§7.10); AC-2.1 as written is unachievable and should be restated as
modality-partitioned with the lattice bounding the reachable conformance level.

**DI-26. Adopt Pydantic AI's static/dynamic instruction split**
(`models/__init__.py:145-151`). Instructions already decompose into parts under the
Expansion Rule, so this costs nothing in the IR and is the difference between a
cacheable and an uncacheable prompt on Anthropic and Bedrock — feeding D26's
performance budget and AC-3.6's cost SLOs.

**DI-27. Add an extension point for agent-runtime events in the trace IR.**
`file-change` and `compaction` (`harness-v1-stream-part.ts:99,110`) have no home in
any model-level IR and will be lost on import from any coding-agent source (P-3).

**DI-28. Record `HarnessV1` in `00-THESIS.md` §1.3 as the shipped alternative
design.** Vercel's `packages/harness/` is the concrete artifact of the
opaque-wrapping road D15 rejects, and its explicit refusal of a static capabilities
object (`harness-v1.ts:14-19`) is a considered counter-position to P-2 that the
thesis should acknowledge rather than ignore.

**DI-29. Dynamic tool exposure is advisory and must be specified as such.**
Anthropic's `_available_tool_names` docstring (`_beta_runner.py:130-138`) is
explicit that removal is a hint the model can ignore. PACT's "tool exposure set"
strategy variable must say the same, and route calls to withdrawn tools down the
unknown-tool path rather than pretending revocation is enforceable.

---

## 11. Open questions this stream could not close

**OQ1. Does the `claude` CLI expose an undocumented single-turn or
message-injection mode?** The binary is not in the corpus. If `--max-turns 1`
combined with some form of transcript injection allowed PACT to drive the loop,
B1 would downgrade from blocking to lossy. `--resume`/`--fork-session`
(`subprocess_cli.py:536,591`) hint that transcript state is addressable, but
`query`'s documented input is user messages only (`query.py:46-53`). Cheap
experiment: run the CLI with `--resume` against a hand-edited transcript and see
whether an injected assistant/tool_result turn is accepted.

**OQ2. What is the real cost of the OpenAI Responses translation layer?**
§2.10 says the OpenAI Agents adapter needs full bidirectional translation between
PACT's message IR and OpenAI Responses items. Unmeasured. Given D26's "few percent
latency, no meaningful token increase" budget, this should be benchmarked before
the adapter is committed to.

**OQ3. Does `BetaToolRunner`'s steerability actually give a third lowering mode?**
`set_messages_params` (`_beta_runner.py:96`) + `__next__` (`:175`) suggest PACT
could keep the framework's loop while owning every decision inside it. That would
be cheaper than full harness lowering and more faithful than native. Nobody has
tried it; it is a one-day spike and it would matter for every SDK that has a
similar shape.

**OQ4. Is Vercel's rejection of a static capabilities object right?**
`harness-v1.ts:14-19` argues for runtime `HarnessCapabilityUnsupportedError` over
declaration. PACT's P-2 lattice takes the opposite view, and the cost PACT accepts
is lattice drift — a lattice that claims `native` for a feature the adapter has
since broken. There is no mechanism in the current design that *detects* drift
other than the CTS itself. Worth asking whether the lattice should be
**generated from CTS results** rather than hand-declared.

**OQ5. How does `tool_use_behavior` interact with PACT's loop IR?**
OpenAI Agents' `StopAtTools` / `stop_on_first_tool` (`agent.py:347-348`) is a
declarative early-exit that overlaps with `loop.halt:` but is scoped to tools
rather than messages. Whether these unify into one predicate language or must stay
separate was not resolved here and belongs with `orchestration-loops.md`.

**OQ6. Which of the three HITL architectures survives contact with a real
non-technical author?** DI-13 recommends Vercel's message-carried model on
architectural grounds (serialisable, runtime-free). Whether a D13 author can
actually operate an approval queue built that way is an AC-1.5-shaped question and
belongs in `pact-dx-personas`, not here.
