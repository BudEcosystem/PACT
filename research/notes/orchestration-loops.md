# Research stream: `orchestration-loops`

**Assignment:** design research for the PACT topology + loop-engineering IR
(objectives **O5.1** / **O5.2**, generisability invariants **G-2** / **G-3**,
acceptance criteria **AC-5.1** / **AC-5.2** / **AC-5.3**).

**Date:** 2026-07-26.
**Method:** source reading only. Every claim below carries `file:line`. Where I
reason beyond what I read, the paragraph is marked **[INFERENCE]**. Where a
construct is *absent* from the corpus, that is stated as a negative finding.

**Paths.** All repo paths are relative to
`/home/bud/ditto/agent-inter-op/research/repos/` unless absolute.

---

## 0. Executive summary of the result

1. **A closed set of 9 node kinds, 1 edge type with 4 orthogonal fields, and 7
   channel kinds is sufficient** for all eight named topologies and all six named
   loop patterns. Sketches for all fourteen are in §5 and §7. Two constructs are
   genuinely *not* expressible with anything in the corpus and require new
   primitives PACT must invent: an **any-of / quorum fan-in that survives cycles**
   (only AutoGen has a partial answer) and a **claimable work channel** (nothing
   in the corpus has one — LangGraph's `Topic` broadcasts to every reader).

2. **Topology and loop must be ONE construct with two authoring surfaces**, not
   two constructs. The strongest evidence is that Google ADK is *actively
   deprecating* its loop construct in favour of its graph construct
   (`frameworks2/google-adk-python/src/google/adk/agents/loop_agent.py:53-56`),
   and Bud already compiles Team strategies into Workflow graphs
   (`/home/bud/ditto/gaia-ai-runtime/bud-agentic-runtime/sdk-and-declarative-dev.md:936-940`).
   The single field that reconciles them is **`on_reentry: reset | accumulate |
   fork`** per node (§8).

3. **Every framework that shipped a "serializable" graph made its conditions
   non-serializable.** AutoGen excludes callable edge conditions from the model
   (`_digraph_group_chat.py:45`) and comments `selector_func` out of its own
   declarative config (`_selector_group_chat.py:355`). Mastra serializes only the
   *source text* of conditions (`types.ts:614-622`). CrewAI ships an inline-Python
   action that its own docstring says "is not sandboxed"
   (`flow_definition.py:527-530`). PACT must use **data predicates**, matching the
   rule Bud already enforces ("Conditions are data, not executable expressions",
   `sdk-and-declarative-dev.md:865`).

4. **Durability requires content-addressed step identity.** DBOS identifies steps
   by a positional counter (`dbos/_context.py:105,185`); Temporal and Restate use
   positional event/completion IDs. Because PACT specs are *rewritten by the
   optimiser* (D22, T6), positional identity invalidates every in-flight run on
   every learned edit. §9 specifies a content-addressed alternative.

5. **Two frameworks silently drop work on resume when the spec changed** —
   LangGraph logs a warning and discards unknown pushed nodes
   (`pregel/_algo.py:978`), ADK silently restarts a loop from the beginning when a
   sub-agent disappears (`agents/loop_agent.py:157`). Both violate PACT's T7.
   Resume must be **fail-closed against a pinned spec digest** (§9, R2).

6. **Six typed escape hatches are unavoidable** (§10), but each has a mandatory
   no-code default, so D14's "no-code is the ceiling" holds.

---

## 1. What each framework's orchestration IR actually is (source-read)

### 1.1 LangGraph — Pregel channels + super-steps

LangGraph is the only corpus framework whose orchestration is a *data-flow*
model rather than a control-flow model.

| Construct | Where | Note |
|---|---|---|
| `START` / `END` sentinels | `frameworks/langgraph/libs/langgraph/langgraph/constants.py:28,30` | `__end__`, `__start__` |
| `Send(node, arg, timeout)` | `.../langgraph/types.py:664-752` | dynamic fan-out packet; docstring names map-reduce as the use case (`types.py:702`) |
| `Command(graph, update, resume, goto)` | `.../types.py:758-808` | one object doing state update + resume + routing; `Command.PARENT` escapes to the parent graph (`types.py:808`) |
| `interrupt(value)` | `.../types.py:811-934` | raises `GraphInterrupt`; **"The graph resumes from the start of the node, re-executing all logic"** (`types.py:826-827`) |
| `Durability = "sync" \| "async" \| "exit"` | `.../types.py:87-93` | persist before next step / concurrently / on exit only |
| `RetryPolicy` | `.../types.py:416-435` | initial_interval, backoff_factor, max_interval, max_attempts, jitter, retry_on |
| `TimeoutPolicy` | `.../types.py:449-512` | **`run_timeout` (hard) vs `idle_timeout` (no-progress)**, `refresh_on: "auto" \| "heartbeat"` |
| `CachePolicy` | `.../types.py:518-527` | key_func + ttl |
| `BranchSpec(path, ends, input_schema)` | `.../graph/_branch.py:83-120` | conditional edges; `ends` is a `dict[Hashable, str]` label→node map, inferred from a `Literal[...]` return annotation when absent (`_branch.py:110-114`) |
| Channel kinds | `.../channels/` | see below |

**Channels (the state algebra):**

| Channel | File:line | Semantics |
|---|---|---|
| `LastValue` | `channels/last_value.py:20-21` | last write wins; **at most one write per step** |
| `LastValueAfterFinish` | `channels/last_value.py:81-85` | value only visible after `finish()`, then cleared |
| `BinaryOperatorAggregate` | `channels/binop.py:65-72` | fold a binary operator (e.g. `operator.add` → append) |
| `NamedBarrierValue` | `channels/named_barrier_value.py:13-14` | **waits until all named writers have written** |
| `NamedBarrierValueAfterFinish` | `channels/named_barrier_value.py:84-87` | barrier + finish gate |
| `Topic` | `channels/topic.py:23-33` | pub/sub; `accumulate: bool` controls whether values survive the step |
| `AnyValue` | `channels/any_value.py:15-17` | last value, assumes all writes equal |
| `EphemeralValue` | `channels/ephemeral_value.py:15-16` | visible for exactly one step |
| `UntrackedValue` | `channels/untracked_value.py:15-16` | **never checkpointed** |
| `Overwrite(value)` | `.../types.py:937-984` | bypass the reducer for one write; two `Overwrite`s in a step is an error |

**Triggering.** A node runs in super-step *N+1* iff some channel it subscribes to
has a version newer than the version that node has *seen*. The checkpoint carries
`channel_values`, `channel_versions`, and `versions_seen`
(`libs/checkpoint/langgraph/checkpoint/base/__init__.py:92-121`), and
`apply_writes` bumps `versions_seen[task][chan]` for each of the task's triggers
(`pregel/_algo.py:261-269`). This is a vector-clock, and it is *strictly more
general* than an edge-counting model because a node can be re-triggered by a
channel it did not have an incoming edge from.

**Negative finding — silent drop on resume.**
`pregel/_algo.py:978` —
`logger.warning(f"Ignoring unknown node name {packet.node} in pending sends")`.
If the graph changed between checkpoint and resume, pending `Send` packets aimed
at a removed node are *silently discarded*. There is no `SpecChanged` error class
(`langgraph/errors.py` defines `GraphBubbleUp`, `GraphDrained`,
`GraphRecursionError`, `InvalidUpdateError`, `GraphInterrupt`, `NodeInterrupt`,
`ParentCommand`, `EmptyInputError`, `TaskNotFound`, `NodeError`,
`NodeCancelledError`, `NodeTimeoutError` — nothing about spec drift).

**Negative finding — no claimable channel.** `Topic.get()` returns the whole list
to every reader (`channels/topic.py:87-92`); `update()` either clears-then-extends
(non-accumulating) or extends (accumulating) (`topic.py:77-85`). There is no
claim, lease, or at-most-once-delivery semantics anywhere in `channels/`.
Work-stealing (blackboard, market) therefore **cannot** be expressed with
LangGraph channels.

### 1.2 AutoGen — group chat managers + a DiGraph with activation groups

AutoGen ships five orchestration managers, all subclasses of
`BaseGroupChatManager`, differing only in `select_speaker`:

| Manager | File | Selection rule |
|---|---|---|
| RoundRobin | `frameworks/autogen/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_round_robin_group_chat.py` | index cycle |
| Selector | `.../_selector_group_chat.py:152-217` | LLM picks from a candidate list, with `allow_repeated_speaker`, `max_selector_attempts`, optional `selector_func`/`candidate_func` |
| Swarm | `.../_swarm_group_chat.py:81-97` | scan the thread backwards for the last `HandoffMessage`, speak as its `target` |
| GraphFlow | `.../_graph/_digraph_group_chat.py:306-...` | drain a ready-queue computed from edge activation |
| MagenticOne | `.../_magentic_one/_magentic_one_orchestrator.py:58-...` | ledger-driven planner (see §6.2) |

**`DiGraph` is the most complete declarative topology IR in the corpus.**

```
DiGraphEdge:                       _digraph_group_chat.py:25-95
  target: str
  condition: str | Callable | None       (:37-44)  # str ⇒ substring match on last message
  condition_function: Callable | None    (:45)     # Field(..., exclude=True) ⇒ NOT serialized
  activation_group: str                  (:46-56)  # defaults to target name
  activation_condition: "all" | "any"    (:57-64)
DiGraphNode:                       :98-110
  name, edges, activation: "all" | "any" (:110)
DiGraph:                           :113-...
  nodes: dict[str, DiGraphNode]
  default_start_node: str | None
```

Validation rules worth stealing verbatim:

- **A cycle must contain at least one conditional edge**, else
  `ValueError("Cycle detected without exit condition: ...")`
  (`_digraph_group_chat.py:149-205`, raise at `:184`).
- **A node may not mix conditional and unconditional outgoing edges**
  (`:221-226`).
- **All edges into the same `(target, activation_group)` must agree on
  `activation_condition`**, and the error names the conflicting source node
  (`:233-276`, raise at `:256`).
- **A cyclic graph requires a termination condition or a max-turn limit**
  (`:339-341`).
- `graph_validate` (`:207-231`) additionally rejects an empty graph (`:210`), a
  graph with no start node (`:213`), and a graph with no leaf node (`:216`).

Execution: `_remaining[target][group]` counts down on each satisfied incoming
edge for `"all"` groups; `_enqueued_any[target][group]` latches for `"any"`
groups (`update_message_thread`, `:392-425`). After a node speaks,
`_reset_triggered_activation_groups` (`:438-455`) restores the counters *only for
the groups that fired*, from a cached `_origin_remaining` (`:359`). **This is the
only correct multi-path fan-in under cycles that I found in the corpus.**

**Termination is a serializable boolean algebra.**
`autogen_agentchat/base/_termination.py:15-16` defines `TerminationCondition` as
`ABC, ComponentBase[BaseModel]`; `__and__`/`__or__` (`:79-83`) build
`AndTerminationCondition` (`:92`) / `OrTerminationCondition` (`:144`), each with
its own `Config` model. The leaf conditions
(`autogen_agentchat/conditions/_terminations.py`) are:

| Leaf | Line |
|---|---|
| `StopMessageTermination` | 24 |
| `MaxMessageTermination` | 62 |
| `TextMentionTermination` | 111 |
| `FunctionalTermination` (callable — **not** a `Component`) | 158 |
| `TokenUsageTermination` | 235 |
| `HandoffTermination` | 313 |
| `TimeoutTermination` | 358 |
| `ExternalTermination` | 404 |
| `SourceMatchTermination` | 463 |
| `TextMessageTermination` | 513 |
| `FunctionCallTermination` | 565 |

Ten of eleven are `Component[Config]` (serializable); only `FunctionalTermination`
is not. **This is the single best prior art for PACT's `halt:` predicate
algebra** — a closed leaf set plus and/or/not, all serializable.

**Negative finding — the declarative config drops the interesting part.**
`SelectorGroupChatConfig` (`_selector_group_chat.py:344-359`) contains a
literally commented-out line: `# selector_func: ComponentModel | None`. The
docstring at `:404` states "`selector_func` is not serializable and will be
ignored during serialization and deserialization process." AutoGen's own
serializable form cannot round-trip its own most-used feature.

### 1.3 CrewAI — two unrelated constructs, one stunted

`lib/crewai/src/crewai/process.py` is the entire "topology" vocabulary:

```python
class Process(str, Enum):
    sequential = "sequential"
    hierarchical = "hierarchical"
    # TODO: consensual = 'consensual'
```

That is the whole file. Two values and a TODO.

Separately, `lib/crewai/src/crewai/flow/flow_definition.py` (1023 lines) is a
genuinely good declarative flow IR — "a static declarative representation of a
Flow ... independent of the Python authoring layer that may have produced it and
of the engine that runs it" (`flow_definition.py:3-7`).

| Element | Line | Note |
|---|---|---|
| State: `dict` / `pydantic` / `json_schema` / `unknown` | 81, 98, 133, 160 | 4 discriminated state kinds |
| `FlowMethodDefinition` | 643 | the node |
| `.do: FlowActionDefinition` | 651 | the payload |
| `.start: bool \| Condition` | 655 | entry marker |
| `.listen: Condition` | 663 | trigger; `{"or": [...]}` / `{"and": [...]}` |
| `.router: bool` + `.emit: list[str]` | 668, 673 | output value *is* the next event name; declared label set |
| `.human_feedback` | 678 / def at 277 (`emit` at 289) | with its own `emit` outcomes; a method with `human_feedback.emit` is *canonicalised into a router* (`:689-697`) |
| `.persist` | 683 / def at 236 | per-method persistence override |
| Action kinds | 348, 375, 399, 465, 498, 513 | `code`, `tool`, `crew`, `agent`, `expression` (CEL), `script` (inline Python) |
| `each` composite | 583 | `in:` CEL expression → list, `do:` ordered steps, each with optional `if:` CEL |
| Condition algebra | `flow/dsl/_conditions.py:22,27` | `or_` / `and_` produce `{"type": ..., "conditions": [...]}` trees |
| Expression language | `flow/expressions.py:1` | **CEL** (`celpy`), with `${...}` template interpolation |

**Negative finding — the escape hatch is unsandboxed by design.**
`FlowScriptActionDefinition` (`flow_definition.py:513-536`), description string at
`:523-526`:
> "Trusted inline Python source. Values are available as state and outputs; they
> are not interpolated into the source. **This is not sandboxed.**"

PACT must not copy this shape (see §10).

**Negative finding — persistence degrades silently-ish.**
`FlowPersistenceDefinition._serialize_persistence` (`flow_definition.py:262-274`)
falls back to `{"ref": module:qualname}` and logs `"Persistence backend %s is not
fully serializable; preserved import reference only."` A `logger.warning` is not
a report; T7 requires a machine-readable loss entry.

### 1.4 Google ADK — a graph that is eating the agent shells

ADK has *two generations* in-tree, and the newer one is absorbing the older.

**Generation 1 — shell agents.** `SequentialAgent`, `ParallelAgent`, `LoopAgent`.
`LoopAgent` carries an explicit deprecation:

```
agents/loop_agent.py:53-56
@deprecated('LoopAgent is deprecated in favor of Workflow and will be removed in
 a future version. Workflow cannot yet be used as an LlmAgent sub-agent.')
```

`LoopAgent` semantics (`agents/loop_agent.py:75-131`): `max_iterations` optional
(`:75`); exits when a sub-agent event sets `actions.escalate` (`:116`); on each
iteration `ctx.reset_sub_agent_states(self.name)` (`:129`); resumable state is
`(current_sub_agent, times_looped)` (`:44-50`).

`ParallelAgent` gives each child an **isolated branch** —
`_BranchPath.create_sub_branch(invocation_context.branch, name=f"{agent}.{sub}")`
(`agents/parallel_agent.py:40-52`) — then merges child event streams through one
queue (`:54-98`).

**Generation 2 — `Workflow` + `Graph`.** `workflow/_graph.py`:

```
RouteValue = bool | int | str                       (_graph.py:36)
RoutingMap = dict[RouteValue, NodeLike | tuple[...]] (_graph.py:44)  # fan-out per label
Edge{from_node, to_node, route: RouteValue | list | None}  (_graph.py:58-77)
DEFAULT_ROUTE = "__DEFAULT__"                        (_graph.py:89)
Graph{nodes (inferred from edges), edges}            (_graph.py:94-131)
```

Routing resolution (`_graph.py:133-183`): untagged edges always fire; tagged
edges fire on label-set intersection; if no specific route matched, the
`__DEFAULT__` edge fires. **If routing edges exist and none matched, ADK logs a
warning and the branch ends** (`_graph.py:175-181`) — a third silent-drop site.

Node kinds (`workflow/`): `BaseNode` (`_base_node.py:36`), `Node`
(`_node.py:180`), `_ToolNode` (`_tool_node.py:38`), `JoinNode`
(`_join_node.py:41`), `FunctionNode` (`_function_node.py:131`), plus the
`ScheduleDynamicNode` protocol (`_schedule_dynamic_node.py:28`) for runtime-created
nodes.

`BaseNode` fields are close to what PACT needs per node:

| Field | Line | Meaning |
|---|---|---|
| `rerun_on_resume: bool` | `_base_node.py:54-59` | rerun from scratch vs complete immediately using the resume input |
| `wait_for_output: bool` | `_base_node.py:61-70` | node may run many times before producing output; **docstring warns this can deadlock and calls that "a user configuration error"** |
| `retry_config` | `_base_node.py:72` / `_retry_config.py:26-58` | max_attempts, initial_delay, max_delay, backoff_factor, jitter, exceptions |
| `timeout: float` | `_base_node.py:79-87` | integrates with retry |
| `input_schema` / `output_schema` / `state_schema` | `_base_node.py:90,99,112` | typed I/O and typed state, with `app:`/`user:`/`temp:` prefixed keys bypassing validation (`:119`) |
| `parallel_worker` / `max_parallel_workers` | `_node.py:181-182` | node-level concurrency |

`JoinNode` sets `_requires_all_predecessors = True` (`_join_node.py:44-46`) — an
all-of join only. **ADK has no any-of or quorum join.**

`ScheduleDynamicNode` documents exactly the three obligations a dynamic node
imposes (`_schedule_dynamic_node.py:34-42`): fresh execution, **deduplication
against event history**, and **rehydration on resume** — with `node_name` called
out as "a deterministic tracking name ... critical for matching events on
resume". This is the step-identity problem stated plainly by a framework author.

### 1.5 Mastra — a closed serializable step union, with a hole

`packages/core/src/workflows/types.ts:532-557` defines `StepFlowEntry` as a closed
union: `step`, `sleep`, `sleepUntil`, `parallel`, `conditional`, `loop`
(`loopType: 'dowhile' | 'dountil'`), `foreach` (`opts.concurrency: number |
ForeachConcurrencyResolver`).

`SerializedStepFlowEntry` (`types.ts:595-641`) mirrors it — but conditions become
`serializedConditions: { id: string; fn: string }[]` (`:620-627`) and the foreach
concurrency resolver becomes `fn?: string` — **"Source of the concurrency
resolver function, when one is used"** (`:639`). The serialized graph therefore
carries JavaScript source text, not a portable predicate. A non-JS runtime cannot
execute it.

Useful detail: the `ForeachConcurrencyResolver` doc (`types.ts:566-573`) explains
*why* a resolver rather than a mutable option — "Workflow graphs are built once
and shared across runs, so a resolver is the only safe way to vary concurrency
per run — mutating a shared options object races between concurrent runs **and
does not survive durable-engine replays**." PACT needs the same property: any
per-run varying value must be an expression over run input, never mutable config.

### 1.6 LlamaIndex Workflows — typed events + a collect algebra

Orchestration is by *event type*: a `@step` declares the event class it consumes
and the event classes it returns. The reflected IR
(`packages/llama-index-workflows/src/workflows/representation/types.py`) has node
kinds `step`, `event`, `external`, `resource`, `resource_config`, `generic`, and
a plain `WorkflowGraphEdge{source, target, label}`. Note that **events are nodes**
in this representation, i.e. a bipartite step/event graph — and
`filter_by_node_type` collapses one side into direct step→step edges
(`representation/types.py:181-...`). **[INFERENCE]** This bipartite form is the
right *rendering* for a UI, not the right *storage* form, because it doubles node
count and puts routing semantics on a node rather than an edge.

The valuable part is `collect.py` — a fan-in *cardinality* algebra:

```
Cardinality           collect.py:49
All()                 collect.py:59   fire once when the stream closes, with every event
Take(n)               collect.py:64-72
Collect(...)          collect.py:80
```

with a precisely-documented semantics block (`collect.py:24-43`), including:
`return []` opens and immediately closes an empty stream so joins fire with `[]`;
`return None` opens no stream so joins never fire; and **`ctx.send_event` cannot
add members to an open collection stream — a targeted send raises
`WorkflowRuntimeError`**. That last rule is the honest answer to "can an external
message join an in-flight fan-in?" — no, and saying so loudly is better than
racing.

HITL is `InputRequiredEvent` (`events.py:504`) → `HumanResponseEvent`
(`events.py:533`), i.e. a *typed request/response pair on the event stream*, plus
an `external` node kind in the IR. This is a cleaner factoring than LangGraph's
`interrupt()` exception, because the request payload has a declared schema.

### 1.7 Semantic Kernel — five named orchestrations, handoffs as a map

`python/semantic_kernel/agents/orchestration/` contains exactly:
`concurrent.py`, `sequential.py`, `group_chat.py`, `handoffs.py`, `magentic.py`.
`OrchestrationHandoffs` (`handoffs.py:57`) is a
`dict[str, AgentHandoffs]` — a source-agent → {target-agent: description} map,
built with `.add(source, target, description)` / `.add_many(...)`
(`handoffs.py:76,93`). The description is what the model sees when choosing a
handoff (the handoff targets become callable functions,
`_add_handoff_functions`, `handoffs.py:190`).

**Design point:** SK models handoff as *data on the graph* (an adjacency map with
natural-language descriptions), whereas AutoGen models it as *data on the message*
(`HandoffMessage.target`, `_swarm_group_chat.py:87-95`) and OpenAI Agents models
it as a tool. All three are the same edge; only SK's form is inspectable before
the run.

### 1.8 CAMEL — a blackboard, named `TaskChannel`

`camel/societies/workforce/task_channel.py`:

```
PacketStatus            :25-43   SENT | PROCESSING | RETURNED | ARCHIVED
Packet{task, publisher_id, assignee_id, status}   :45-83
TaskChannel             :85-...  hash map + status index + per-assignee deque + per-publisher deque
  post_task(task, publisher, assignee)            :203
  post_dependency(...)                            :215
  get_assigned_task_by_assignee(...)              :174  "Atomically get and claim a task"
  return_task / archive_task / remove_task        :228,242,260
  get_dependency_ids()                            :270
```

This is a blackboard with **explicit claim semantics** (`:174`, "Atomically get
and claim") and a lifecycle (`SENT → PROCESSING → RETURNED → ARCHIVED`, where
ARCHIVED means "the task is considered as a dependency", `:33-36`). No other
corpus framework has claim semantics. `workforce.py` adds a coordinator that
calls `_find_assignee` (`workforce.py:1908,1922`) and a
`FailureHandlingConfig` with a `RecoveryStrategy.REASSIGN` (`workforce.py:1899`).

### 1.9 MetaGPT — Tree-of-Thought as pure configuration

`metagpt/strategy/tot_schema.py` is 30 lines and is the entire ToT surface:

```python
class MethodSelect(Enum):  SAMPLE = "sample";  GREEDY = "greedy"
class Strategy(Enum):      BFS = "BFS";  DFS = "DFS";  MCTS = "MCTS"
class ThoughtSolverConfig(BaseModel):
    max_steps: int = 3            # depth
    method_select: str = GREEDY
    n_generate_sample: int = 5    # branching factor, per node
    n_select_sample: int = 3      # beam width, per path
    n_solution_sample: int = 5    # DFS only
    parser: BaseParser
    evaluator: BaseEvaluator
```

`BFSSolver` (`tot.py:126`), `DFSSolver` (`tot.py:180`), and — importantly —
`MCTSSolver.solve` raises `NotImplementedError` (`tot.py:230-232`).
**Negative finding: the one framework that declared MCTS never implemented it.**
PACT should ship `bfs|dfs|beam` and declare MCTS `unsupported`.

### 1.10 Others, briefly

- **Pydantic AI** hard-codes its loop as a four-node graph:
  `UserPromptNode` (`pydantic_ai_slim/pydantic_ai/_agent_graph.py:453`) →
  `ModelRequestNode` (`:1011`) → `CallToolsNode` (`:1673`) → `SetFinalResult`
  (`:2088`). There is **no declarative loop surface at all**. For PACT this is the
  clean case for harness lowering (D12): there is nothing native to map onto.
- **smolagents** `MultiStepAgent._run_stream` (`src/smolagents/agents.py:540-610`)
  is a ReAct loop with `planning_interval` re-planning (`:550-551`),
  `final_answer_checks` verifier predicates (`:588-590`), and — critically —
  `_handle_max_steps_reached` (`:625-640`) which, on budget exhaustion, runs
  `provide_final_answer` rather than aborting.
- **DSPy** ships loop patterns as modules: `ReAct.forward` with a
  `trajectory` dict (`dspy/predict/react.py:95-118`) and `truncate_trajectory` on
  context overflow (`:169-186`); `CodeAct(ReAct, ProgramOfThought)` with
  `generated_code`/`finished` output fields (`dspy/predict/code_act.py:15,65-66`)
  and a separate `extractor` (`:76`); `majority(...)`
  (`dspy/predict/aggregation.py:9-53`); `BestOfN(module, N, reward_fn, threshold,
  fail_count)` (`dspy/predict/best_of_n.py:7,40`); `Refine` (same signature,
  `dspy/predict/refine.py:41`) with an `OfferFeedback` signature that produces
  per-module textual `advice` (`refine.py:15,34`).
- **Reflexion (reference impl)** `memory/reflexion/programming_runs/reflexion.py:8-90`
  is two nested loops: outer `cur_pass < pass_at_k`, inner `cur_iter < max_iters`;
  each inner iteration is generate → *programmatic test execution* → self-reflect →
  regenerate with the reflection in context; reflections accumulate in a list
  (`:56-58`).
- **Vercel Eve** documents the runtime shape PACT is closest to:
  session / turn / **step = "a durable checkpoint inside a turn (one model call
  and the tool calls it makes)"**, and "A step interrupted mid-execution re-runs,
  so make non-idempotent side effects like charges or emails idempotent"
  (`frameworks/vercel-eve/docs/concepts/execution-model-and-durability.md`).
  Also: **no durable FIFO queue of user messages per session**, and "don't rely on
  concurrent sends to the same session behaving like a typical ordered chat queue"
  (same file). Its escape hatch for orchestration is model-authored JavaScript run
  as one durable step (`docs/concepts/default-harness.md`, "The opt-in `Workflow`
  tool", `experimental_workflow({ maxSubagents: 100 })`).

---

## 2. What Bud already has (the superset obligation, D3)

From `/home/bud/ditto/gaia-ai-runtime/bud-agentic-runtime/sdk-and-declarative-dev.md`:

| Bud construct | Line | PACT must express |
|---|---|---|
| `Workflow(strategy="sequential" \| "dag")` | 782-795 | graph with implied edges |
| `.step(agent, task, after, prompt, retry{maxRetries, backoffMs})` | 787-795 | `agent` node + retry |
| `.human_review(name, after, task)` | 802-806 | `human` node |
| `Workflow.graph(entrypoint, state, limits{maxTransitions, maxNodeExecutions, maxFanOut, maxConcurrency, maxSubgraphDepth})` | 819-830 | graph-level budgets |
| `foreach={"path": "/topics", "maxItems": 4, "concurrency": 2}` | 837 | `map` node |
| `output={"path": "/findings", "reducer": "append"}` | 838 | channel write + reducer |
| `.reduce(name, inputs, reducer="collect", output, next)` | 841-846 | `join` node |
| `next=[route("quality", when={"path": ..., "equals": True}), otherwise("map")]` | 850-853 | labelled edges + default edge |
| `.subgraph(name, workflow=...)` | 855 | `graph` node |
| `.command(name, update={...})` | 891-892 | `transform` node |
| `Command.resume_with(payload, update=<RFC 7396 patch>, goto=...)` | 897-901 | typed resume |
| Team strategies: `sequential, parallel, dag, debate, consensus, manager` | 936-940 | topology sugar |
| Native reducers `debate_argument_matrix`, `consensus_vote_tally` | 938-939 | named reducer registry |
| `manager` compiles to a manager Agent with workers as `tools.agents` | 943-947 | supervisor-as-agent-with-agent-tools |

Two rules Bud already enforces that PACT must keep:

- **"The fallback edge makes the cycle explicit, so Rust requires
  `maxTransitions`. Conditions are data, not executable expressions. All paths are
  JSON Pointers, and fan-out limits are part of the manifest rather than SDK
  runtime options."** (`:863-867`)
- **"Rust validates the command, applies review output, the RFC 7396 state patch,
  and routing in one cursor commit, and rejects routes that were not declared by
  the manifest."** (`:910-913`)

Both are stronger than anything in the OSS corpus and both survive into the
design below.

---

## 3. The proposed IR — nodes

**Design axiom.** Separate three things that every framework conflates:
*what runs* (node kind), *when it is allowed to run* (activation, on the edge),
and *what it may read and write* (channels). AutoGen puts activation on both the
node (`DiGraphNode.activation`) and the edge (`DiGraphEdge.activation_condition`)
and needs a validator to keep them consistent
(`_digraph_group_chat.py:232-276`); that validator is the tax for the conflation.

### 3.1 Closed node kinds (9)

| # | `kind` | Payload | Effects | Why it cannot be dropped |
|---|---|---|---|---|
| 1 | `agent` | ref to an Agent (which is itself a graph) | model + tools | the reason the system exists |
| 2 | `tool` | ref to a Resource (MCP / HTTP / skill / code-interpreter) | declared | a step that is not a model call |
| 3 | `map` | `over: <expr>`, `as: <var>`, `body: <node|graph ref>`, `concurrency`, `max_items`, `on_error` | body's | dynamic fan-out is not static fan-out; `Send` (LangGraph), `foreach` (Mastra/Bud), `for` (SWF), `each` (CrewAI) all exist independently |
| 4 | `join` | `mode`, `reducer`, `emit` | pure | fan-in is not the inverse of fan-out; it needs quorum and a reducer |
| 5 | `route` | `decide: predicate-tree \| model \| escape`, `emit: [labels]` | none | separates *deciding* from *doing*; makes the label set declarable and therefore checkable (`emit` in CrewAI `:671`, `RoutingMap` in ADK `:44`) |
| 6 | `transform` | `set:` / `patch:` (RFC 7396) / `expr:` over channels | pure | Bud `.command(...)`, SWF `set`, CrewAI `expression`; needed so a no-code author can move data without a tool |
| 7 | `human` | `request_schema`, `response_schema`, `prompt`, `emit: [outcomes]`, `timeout`, `on_timeout` | external | HITL is a first-class node in ADK (`external`), LlamaIndex (`external`), CrewAI (`human_feedback`), Bud (`.human_review`) |
| 8 | `graph` | ref to another graph/agent + `scope` | children's | G-4 recursive composition; Bud `.subgraph` |
| 9 | `escape` | typed code ref (§10) | declared | F-2/F-3 |

**Node-common fields** (all kinds), each with a named source:

```yaml
id:            <stable, content-addressable>      # step identity, §9 R1
role:          perceive|plan|act|observe|reflect|score|select|halt|null   # semantic tag only
on_reentry:    reset | accumulate | fork          # §8 — the loop/topology reconciler
effects:       pure | idempotent | at_least_once | at_most_once | external   # §9 R3
idempotency_key: <expr>                           # required when effects=at_most_once
retry:         {max_attempts, initial_delay, max_delay, backoff, jitter, on: <error filter>}   # ADK _retry_config.py:26-58 ∪ SWF retryPolicy:1684-1763
timeout:       {run: <dur>, idle: <dur>, refresh_on: auto|heartbeat}       # LangGraph types.py:465-479
cache:         {key: <expr>, ttl: <dur>}          # LangGraph types.py:518-527
input_schema / output_schema:  <schema ref>       # ADK _base_node.py:90,99
reads:  [<channel selector>]                      # explicit, see §3.3
writes: [<channel selector>]
budget: {tokens, cost, wallclock, tool_calls}     # SYNTHESIS F5.1 per-run budget objects
```

`role` deserves justification: it is *not* a kind, because a `plan` step may be an
`agent`, a `tool`, or an `escape`. It exists so that (a) traces align across
adapters, (b) the optimiser can target "the reflect prompt" without knowing the
graph shape (SYNTHESIS F3 treats every text field as trainable — it needs to know
*which* field), and (c) G-3's stated vocabulary
(`perceive/plan/act/observe/reflect/halt`) has a home without becoming a closed
node set. **[INFERENCE]** — no framework has this; it is a PACT invention
motivated by the optimiser requirement.

### 3.2 The single edge type

One edge type, four orthogonal fields. Every corpus "edge kind" is a projection
of this.

```yaml
edges:
  - from: <node id | START>
    to:   <node id | END>
    when: <Predicate>            | null    # data predicate over channels; null = unconditional
    route: <label | [labels] | DEFAULT>| null  # matches a label emitted by a `route` or `human` node
    join:  {group: <name>, mode: all | any | quorum(k) | first_ok | all_settled}
    carry: [<channel selector>]  | null    # what data flows; null = the graph's shared scope
```

Mapping to prior art:

| Field | Prior art |
|---|---|
| `when` | AutoGen `DiGraphEdge.condition` (`_digraph_group_chat.py:37`), CrewAI `if:` (`flow_definition.py:562-571`), SWF `taskBase.if` (`schema/workflow.yaml:188-191`), Bud `route(when={path, equals})` (`sdk:850`) |
| `route` | ADK `Edge.route` + `DEFAULT_ROUTE` (`_graph.py:69,89`), CrewAI `router`/`emit` (`:668,671`), Bud `route(...)`/`otherwise(...)` (`sdk:850-853`) |
| `join.group` / `join.mode` | AutoGen `activation_group` + `activation_condition` (`_digraph_group_chat.py:46-64`), LlamaIndex `Collect(All()/Take(n))` (`collect.py:59-72`), ADK `JoinNode._requires_all_predecessors` (all-only, `_join_node.py:44`) |
| `carry` | LangGraph `Send.arg` (`types.py:713-714`) carries a *different* state to the target; nothing else makes data flow explicit |

**Why `join` is on the edge and not the node.** LangGraph puts the barrier in a
*channel* (`NamedBarrierValue`), which means the barrier's membership is baked
into the channel's writer list and cannot vary per cycle iteration. AutoGen puts
it on the edge with an `activation_group`, which is exactly what lets the same
target node have two independent fan-ins (its cycle example: `A→B→C→B`,
`_digraph_group_chat.py:50-54`). Barrier-as-channel cannot express that;
barrier-as-edge-group can. Keep reducers on channels, keep quorum on edges.

**`join.mode` should be Restate's four, not two.** Restate's `CombinatorType`
(`runtime/restate/service-protocol/dev/restate/service/protocol.proto:110-122`)
is `FIRST_COMPLETED`, `ALL_COMPLETED`, `FIRST_SUCCEEDED_OR_ALL_FAILED`,
`ALL_SUCCEEDED_OR_FIRST_FAILED`. Adopting these names/semantics means a Restate
adapter is a direct mapping, and it forces the spec to answer "what happens when a
branch fails" *at authoring time* rather than at 3am. PACT mapping:
`any → FIRST_COMPLETED`, `all_settled → ALL_COMPLETED`,
`first_ok → FIRST_SUCCEEDED_OR_ALL_FAILED`, `all → ALL_SUCCEEDED_OR_FIRST_FAILED`,
plus `quorum(k)` (no Restate equivalent → emulated).

### 3.3 Closed channel kinds (7)

| # | `kind` | Reducer | Prior art |
|---|---|---|---|
| 1 | `last` | overwrite; **error on >1 writer per step** | LangGraph `LastValue` (`last_value.py:20-21`) |
| 2 | `append` | ordered concat | LangGraph `BinaryOperatorAggregate(operator.add)` (`binop.py:65`), Bud `reducer: "append"` (`sdk:838`) |
| 3 | `merge` | RFC 7396 merge-patch | Bud `Command(update=RFC 7396 patch)` (`sdk:910-911`) |
| 4 | `fold` | named op from a closed set: `sum,max,min,union,intersect,concat,argmax` | LangGraph binop generalised; Bud `consensus_vote_tally` / `debate_argument_matrix` (`sdk:938-939`) are two named folds already |
| 5 | `topic` | broadcast queue; `accumulate: bool` | LangGraph `Topic` (`topic.py:23-33`) |
| 6 | `queue` | **claimable** work queue; at-most-once delivery, `lease`, `nack`, `archive` | **Nothing in the corpus.** Closest is CAMEL `TaskChannel` (`task_channel.py:85-...`, "Atomically get and claim", `:174`) which is a bespoke class, not a declarable channel |
| 7 | `blob` | opaque, content-addressed, out-of-band payload (audio/video/screenshots) | D16 modality requirement; **[INFERENCE]** — no framework channel handles non-JSON payloads; LangGraph checkpoints go through a serde layer with no size story |

Channel-common fields:

```yaml
scope:     run | branch | agent | turn        # ADK branch isolation (parallel_agent.py:47-50);
                                              # ADK app:/user:/temp: prefixes (_base_node.py:119);
                                              # Eve "nothing crosses the boundary implicitly"
durable:   true | false                       # false ⇒ LangGraph UntrackedValue (untracked_value.py:16)
lifetime:  run | step                         # step ⇒ LangGraph EphemeralValue (ephemeral_value.py:16)
schema:    <schema ref>
redact:    [<pointer>]                        # policy contract; needed for AC-4.4 trace promotion
```

`channel.scope` is what makes ONE construct cover both topology state (a shared
blackboard at `scope: run`) and loop state (a trajectory at `scope: turn`). It is
the second half of the loop/topology unification argument in §8.

### 3.4 The predicate language

`when:` and `halt:` share one predicate algebra. Requirements, in order of
bindingness:

1. **Data, not code** — Bud already requires this (`sdk:865`).
2. **Air-gapped, offline, no eval() of a general language** (D17).
3. **Renderable as a form** (D18: "form-renderable").
4. **Serialisable and diffable** (D18).
5. **Decidable enough for static analysis** — PACT must be able to prove a cycle
   has an exit (AutoGen does this: `has_cycles_with_exit`,
   `_digraph_group_chat.py:146-190`).

Shape:

```yaml
# leaf forms
{ path: /decision/accepted, equals: true }        # Bud form, sdk:850
{ path: /score, gte: 0.8 }
{ channel: messages, contains_text: "APPROVE" }   # AutoGen TextMentionTermination (_terminations.py:111)
{ tool_called: finish }                           # AutoGen FunctionCallTermination (:565)
{ source_is: reviewer }                           # AutoGen SourceMatchTermination (:463)
{ metric: "deepeval:faithfulness", gte: 0.7 }     # ties predicates to the eval registry (O4.1)
{ budget_exhausted: tokens|cost|iterations|wallclock }   # AutoGen TokenUsageTermination (:235), MaxMessageTermination (:62)
{ handoff_to: "*" }                               # AutoGen HandoffTermination (:313)
{ external_signal: <name> }                       # AutoGen ExternalTermination (:404)
{ elapsed_gte: 30s }                              # AutoGen TimeoutTermination (:358)
# combinators
{ all: [ ... ] }   { any: [ ... ] }   { not: { ... } }
```

CEL (CrewAI's choice, `flow/expressions.py`) is rejected for `when:`/`halt:`
because a general expression language defeats requirements 3 and 5 and drags in a
parser dependency per adapter language. **[INFERENCE]** CEL is admissible for
`transform.expr` and `map.over` — where you genuinely need to *compute* a value —
behind a `x-expr-lang` declaration, but the control-flow predicates must stay in
the closed leaf algebra so the validator can reason about them.

---

## 4. Graph-level fields

```yaml
graph:
  entrypoint: <node id | [node ids]>            # Bud `entrypoint` (sdk:823); AutoGen default_start_node (:118)
  channels:   { ... }
  nodes:      [ ... ]
  edges:      [ ... ]
  halt:       <Predicate>                       # AutoGen termination algebra (base/_termination.py:79-83)
  budget:                                       # Bud limits (sdk:824-830)
    max_transitions: 8
    max_node_executions: 16
    max_fan_out: 4
    max_concurrency: 2
    max_depth: 2
    max_iterations: 12
    max_tokens: 200000
    max_cost_usd: 1.50
    max_wallclock: 15m
  on_budget_exhausted: fail | emit_best | goto <node>   # smolagents _handle_max_steps_reached (agents.py:625-640)
  stall:                                        # Magentic-One (_magentic_one_orchestrator.py:92,391-405)
    detector: no_channel_write | repeated_output | model_judged
    patience: 2
    decay_on_progress: true                     # leaky bucket, per :396-397
    on_stall: goto <node> | replan | fail
  durability: none | at_step | at_node | at_effect       # §9 R5
  concurrency: {max_parallel, isolation: branch | shared}
```

**Static validation obligations** (all lifted from source, all mechanically
checkable, all producing the D-style "file, line, rule, fix" error of O7.3):

| Rule | Source |
|---|---|
| Every cycle contains at least one edge with `when` or `route` | AutoGen `_digraph_group_chat.py:149-205` |
| A cyclic graph must declare `halt` or `budget.max_transitions` | AutoGen `:339-341`; Bud "Rust requires `maxTransitions`" (`sdk:863-864`) |
| A node's outgoing edges must not mix conditional and unconditional | AutoGen `:221-226` |
| All edges into `(target, join.group)` agree on `mode` | AutoGen `:233-276` |
| A `route` node's emitted labels ⊆ its declared `emit` set, and every declared label has ≥1 outgoing edge or a `DEFAULT` | ADK's unmatched-route warning (`_graph.py:175-181`) becomes a *validation error* |
| At least one start node and one terminal node | AutoGen `graph_validate` `:191-203` |
| A `join` node with `mode: all` must be reachable from every member of its group | ADK's deadlock warning (`_base_node.py:66-69`) becomes a validation error |
| Every `escape` declares `effects` and schemas | F-2 |
| `Command.goto` on resume ∈ declared routes | Bud (`sdk:912-913`) |

The last column is the point: **five of these nine rules exist as runtime warnings
or docstring warnings in the corpus. PACT should promote them to load-time
errors.** That is a concrete, cheap differentiator and directly serves D28's
"too complex to use" failure mode (the errors do the teaching).

---

## 5. Sufficiency proof — the eight topologies

Notation: `n(kind)` for a node, `→` for an edge. Full YAML omitted for length;
the shape is what matters.

### 5.1 Sequential pipeline

```yaml
nodes: [ a(agent), b(agent), c(agent) ]
edges: [ START→a, a→b, b→c, c→END ]
channels: { doc: {kind: last, scope: run} }
```
Sugar: `pattern: pipeline, members: [a,b,c]`. Matches Bud
`Workflow(strategy="sequential")` (`sdk:786`).

### 5.2 Parallel map-reduce

```yaml
channels:
  topics:   {kind: last,   scope: run}
  findings: {kind: append, scope: run}
nodes:
  - id: fan   kind: map    over: /topics  as: topic  body: worker  concurrency: 4  max_items: 8
  - id: worker kind: agent  writes: [findings]
  - id: reduce kind: join   mode: all  reducer: {fold: concat, into: /summary}
edges: [ START→fan, fan→reduce {join: {group: g, mode: all}}, reduce→END ]
```
Direct match to Bud `foreach` + `.reduce` (`sdk:837-846`) and to LangGraph's
`Send` map-reduce docstring (`types.py:696-707`).

### 5.3 Supervisor

Two legal encodings; **PACT must define one as canonical and the other as sugar**,
or `collapse/explode` (O1.3) will not be a bijection.

*(a) Supervisor-as-router (canonical):*
```yaml
nodes:
  - id: sup   kind: route  decide: {model: {select_from: [res, wri, cri], prompt_ref: supervisor.md}}
              emit: [res, wri, cri, done]
  - id: res   kind: agent
  - id: wri   kind: agent
  - id: cri   kind: agent
edges:
  - START→sup
  - sup→res {route: res}   - sup→wri {route: wri}   - sup→cri {route: cri}
  - sup→END {route: done}
  - res→sup  - wri→sup  - cri→sup      # on_reentry: accumulate on `sup`
halt: {any: [{route_emitted: done}, {budget_exhausted: iterations}]}
```

*(b) Supervisor-as-agent-with-agent-tools:* the supervisor is one `agent` node
whose `tools` include the specialists. This is exactly Bud's `strategy: manager`
compilation — "compiles a `strategy: manager` Team into the manager Agent that Bud
will run, with non-manager members exposed as declared `tools.agents` bindings"
(`sdk:943-947`) — and OpenAI Agents' agents-as-tools.

**Decision:** (a) is canonical because it is inspectable (the label set is
declared, the topology is a graph, the optimiser can rewrite the routing prompt as
a first-class field). (b) is a *lowering choice*, recorded in the lockfile, and is
often the better one on weak models because it removes a whole coordination hop
(SYNTHESIS F5.3 and the Anthropic 15×-tokens finding). Making (b) a lowering
rather than an IR alternative is what keeps the two forms from diverging.

### 5.4 Hierarchical

`graph` nodes, recursively. `n(graph)` whose target is itself a supervisor graph;
`budget.max_depth` bounds it (Bud `maxSubgraphDepth`, `sdk:829`). Channel
`scope: branch` isolates each subtree's working state (ADK
`_BranchPath.create_sub_branch`, `parallel_agent.py:47-50`), while
`scope: run` channels are the shared spine. No new construct — this is G-4.

### 5.5 Swarm / handoff

```yaml
channels: { thread: {kind: append, scope: run} }
nodes: [ triage(agent), billing(agent), tech(agent) ]
handoffs:                        # sugar, desugars to route-labelled edges
  triage: [billing, tech]
  billing: [triage]
  tech: [triage, billing]
halt: {any: [{handoff_to: "*human*"}, {tool_called: resolve}, {budget_exhausted: iterations}]}
```
Desugars to: each agent node gains `emit: [<targets>, __continue__]` and one edge
per target. Matches SK `OrchestrationHandoffs` (adjacency map + description,
`handoffs.py:57-119`) and AutoGen's `HandoffMessage.target` scan
(`_swarm_group_chat.py:81-97`). The `HandoffTermination` leaf
(`_terminations.py:313`) becomes the `{handoff_to: ...}` predicate.

### 5.6 Debate

```yaml
channels:
  arguments: {kind: append, scope: run}
  verdict:   {kind: last,   scope: run}
nodes:
  - id: round  kind: map   over: /debaters  as: d  body: speak  concurrency: 3
  - id: speak  kind: agent writes: [arguments]
  - id: matrix kind: join  mode: all  reducer: {fold: debate_argument_matrix, into: /matrix}
  - id: judge  kind: agent reads: [matrix]  writes: [verdict]
edges: [START→round, round→matrix {join:{group:r, mode: all}}, matrix→judge,
        judge→round {when: {path: /verdict/settled, equals: false}}, judge→END {when: {path: /verdict/settled, equals: true}}]
budget: {max_iterations: 3}
```
`debate_argument_matrix` is **already a Bud-native reducer** (`sdk:938-939`), so
this is a superset-preserving encoding, not an invention. Consensus is identical
with `consensus_vote_tally` and a `fold: argmax` selection.

### 5.7 Blackboard

```yaml
channels:
  board: {kind: queue, scope: run, lease: 60s}     # ← channel kind #6
  facts: {kind: append, scope: run}
nodes:
  - id: poster   kind: agent  writes: [board]
  - id: worker   kind: agent  reads: [board]  writes: [board, facts]   # claim/nack via queue semantics
  - id: monitor  kind: route  decide: {any: [{path: /facts, size_gte: 10}, {channel: board, empty: true}]}
edges: [START→poster, poster→worker, worker→monitor, monitor→worker {route: continue}, monitor→END {route: done}]
```
**This is the pattern that forces channel kind #6.** Without a claimable queue,
two workers reading a `topic` both see every item (LangGraph
`topic.py:87-92`) and duplicate the work. CAMEL solved it with a bespoke class
(`task_channel.py:174`, "Atomically get and claim") and a four-state lifecycle
(`:25-43`). PACT should lift exactly that: `queue` items carry
`{status: available|claimed|returned|archived, assignee, lease_expiry}`.

### 5.8 Market / auction

```yaml
channels:
  bids: {kind: append, scope: run, schema: bid.schema.json}
  award: {kind: last,  scope: run}
nodes:
  - id: crier   kind: transform  set: {/rfp: "${task}"}
  - id: bidding kind: map  over: /bidders  as: b  body: bid  concurrency: 8
  - id: bid     kind: agent  reads: [/rfp]  writes: [bids]        # output_schema = bid.schema.json
  - id: clear   kind: join  mode: quorum(3)  reducer: {fold: argmax, on: /bids/*/score, into: /award}
  - id: perform kind: agent  reads: [award]
edges: [START→crier, crier→bidding, bidding→clear {join:{group:a, mode: quorum(3)}},
        clear→perform, perform→END]
```

**Negative finding.** Nothing in the 141-repo corpus implements auction,
contract-net, or bidding. A repo-wide grep for
`auction|Auction|contract_net|ContractNet|bidding` across `frameworks/` and
`frameworks2/` returns two hits, both incidental prose
(`frameworks2/mastra/observability/mastra/src/client/proxy.ts:151` is a comment
about orphan spans; `frameworks2/crewai/lib/crewai/tests/test_crew.py:310` is a
test fixture string containing the word "auctioned"). Therefore:

- The encoding above is **inferred, not validated**. It is the highest-risk item
  in AC-5.1 (≥ 8 patterns × ≥ 3 adapters).
- It needs exactly two things the other seven do not: `join.mode: quorum(k)` (so
  the auction closes without waiting for slow bidders) and `fold: argmax` over a
  *typed* bid schema. Both are cheap; neither exists upstream.
- **Recommendation:** build the market fixture *first* in the CTS, because it is
  the only pattern with no reference implementation to check against.

### 5.9 Sufficiency table

| Pattern | node kinds used | edge fields used | channel kinds used | new primitive needed |
|---|---|---|---|---|
| Sequential pipeline | agent | — | last | — |
| Parallel map-reduce | map, agent, join | join.all | last, append | — |
| Supervisor | route, agent | route | append | — |
| Hierarchical | graph, route, agent | route | last(branch), append(run) | — |
| Swarm / handoff | agent | route | append | — |
| Debate | map, agent, join | join.all, when | append, last, fold | named fold registry |
| Blackboard | agent, route | route | **queue**, append | **claimable queue** |
| Market / auction | transform, map, agent, join | join.quorum | append, last, fold(argmax) | **quorum(k)**, argmax fold |

Nine node kinds, one edge type, seven channel kinds. Two genuinely new primitives.

---

## 6. Loops in the corpus, as data

### 6.1 What each loop actually varies

Reading the six named loops as *diffs from a common skeleton*:

| Loop | Graph shape | Distinguishing data |
|---|---|---|
| ReAct | `act → observe → act` cycle | `halt: {tool_called: finish}`; `budget.max_iterations`; trajectory channel `append` |
| Plan-and-Execute | `plan → map(steps) → join → verify → (plan\|END)` | replan edge `when: {path:/verify/ok, equals:false}` |
| Reflexion | outer `attempt` loop, inner `refine` loop | a `reflections` channel (`append`, `scope: run`) + a **programmatic** verifier node |
| Tree-of-Thought | `expand → score → select-topk → expand` cycle over a frontier channel | `search: {strategy, branch_factor, beam_width, depth, select}` |
| Self-consistency | *no graph change* | `sampling: {n, temperature}` + `select: {kind: majority, field}` |
| CodeAct | ReAct shape | `act` node's Resource is a code interpreter; extra terminal `extract` node |

Evidence for each:

- **ReAct** — DSPy `ReAct.forward` (`optim/dspy/dspy/predict/react.py:95-118`):
  `for idx in range(max_iters)` writing `thought_i / tool_name_i / tool_args_i /
  observation_i` into one `trajectory` dict, breaking on
  `pred.next_tool_name == "finish"` (`:114-115`), then always running a separate
  `extract` module (`:117`). Also smolagents `_run_stream`
  (`frameworks2/smolagents/src/smolagents/agents.py:540-610`).
- **Plan-and-Execute** — smolagents `planning_interval`
  (`agents.py:550-551`: replan when `step_number == 1 or (step_number-1) %
  planning_interval == 0`), and Magentic-One (below).
- **Reflexion** — `memory/reflexion/programming_runs/reflexion.py:8-90`:
  outer `while cur_pass < pass_at_k and not is_solved` (`:33`), inner
  `while cur_iter < max_iters` (`:57`), with `exe.execute(...)` as the
  programmatic verifier (`:43,76`) and `reflections += [reflection]` accumulating
  (`:61`).
  DSPy's `Refine` is the same idea with an LLM-generated `advice` dict per module
  (`optim/dspy/dspy/predict/refine.py:15-38`).
- **Tree-of-Thought** — MetaGPT `ThoughtSolverConfig`
  (`frameworks2/metagpt/metagpt/strategy/tot_schema.py:23-30`) — six scalars and
  two pluggables. `BFSSolver` (`tot.py:126-178`), `DFSSolver` (`tot.py:180-228`),
  `MCTSSolver` → `NotImplementedError` (`tot.py:230-232`).
- **Self-consistency** — DSPy `majority(...)`
  (`optim/dspy/dspy/predict/aggregation.py:9-53`): normalise, count
  (`:38,46`), tie-break to the earliest completion (`:49-51`).
  `BestOfN(module, N, reward_fn, threshold, fail_count)`
  (`optim/dspy/dspy/predict/best_of_n.py:7,36-49`) with early exit at
  `reward >= self.threshold` (`:72`) and diversity via `rollout_id` +
  `temperature=1.0` (`:57`).
- **CodeAct** — DSPy `class CodeAct(ReAct, ProgramOfThought)`
  (`optim/dspy/dspy/predict/code_act.py:15`). Its signature adds
  `generated_code: str` and `finished: bool` output fields (`:65-66`) and it keeps
  a separate `extractor = dspy.ChainOfThought(extract_signature)` (`:76`).
  The *inheritance* is the finding: CodeAct is literally ReAct with a different
  action encoding.

### 6.2 Magentic-One deserves its own row

`frameworks/autogen/.../_magentic_one/_magentic_one_orchestrator.py` is the most
complete "loop with meta-control" in the corpus:

- Outer loop builds a **task ledger** = `facts` + `plan` (`:96-97`, built at
  `:161-186`), re-entered by `_reenter_outer_loop` (`:262`).
- Inner loop asks the model for a **progress ledger** — a JSON object with five
  required keys `is_request_satisfied`, `is_progress_being_made`, `is_in_loop`,
  `instruction_or_question`, `next_speaker`, each `{answer, reason}`
  (`:347-354`), validated key-by-key (`:356-365`) plus a membership check that
  `next_speaker.answer ∈ participant_names` (`:367-372`); parse failure retries
  and then raises (`:381`).
- `is_request_satisfied` → final answer (`:385-389`).
- `not is_progress_being_made` **or** `is_in_loop` → `_n_stalls += 1`; otherwise
  `self._n_stalls = max(0, self._n_stalls - 1)` (`:391-397`).
  **The stall counter is a leaky bucket, not a monotone counter** — progress
  *repays* stall debt. PACT's `stall.patience` must specify decay or two adapters
  will disagree on when a loop replans.
- `_n_stalls >= _max_stalls` → `_update_task_ledger` then `_reenter_outer_loop`
  (`:400-405`).

**This is a declarable pattern**, and PACT's `stall:` block (§4) is directly
modelled on it. It also proves the *route node's decide-by-model* form is
necessary: the next speaker here is a model output constrained to the participant
name set (`:370-371` validates membership).

### 6.3 The loop fields that are NOT optional

Three loop-level fields are load-bearing and are missing from most frameworks:

1. **`on_budget_exhausted`.** smolagents does not abort at `max_steps`; it calls
   `provide_final_answer` (`agents.py:606-607` → `_handle_max_steps_reached` at
   `:625-640`, which calls `provide_final_answer` at `:627`). A spec that treats
   `max_iterations` as a hard abort produces a *worse agent* than the frameworks
   it replaces — F-4 says that is a defect.

2. **`context_policy`.** DSPy truncates the oldest tool call on
   `ContextWindowExceededError` and retries up to three times, then fails
   (`react.py:145-156`; `truncate_trajectory` at `:169-186`, which pops the four
   keys of the oldest tool call). Eve compacts at a `thresholdPercent` (default
   0.9) and its compaction explicitly "resets read-before-write tracking" and
   "re-injects the active todo list" (`docs/concepts/default-harness.md`). Context
   policy changes measured behaviour and is a *model-portability lever* (weak
   models degrade faster with context bloat — SYNTHESIS F2). It must be IR, not
   runtime config:
   ```yaml
   context_policy:
     on_overflow: truncate_oldest | compact | fail
     compact: {threshold_pct: 0.75, model: <ref>, preserve: [todo, decisions, constraints]}
     keep: {first_n_turns: 1, last_n_turns: 6, always: [/system, /task]}
   ```

3. **`sampling` + `select`.** These make self-consistency a *node attribute*
   rather than a graph rewrite. Normative desugaring (needed for O1.3's
   `explode(collapse(X)) ≡ X`): a node with `sampling.n = k` desugars to
   `map over range(k) with variance: rollout` → `join(all) → select`. Both forms
   MUST canonicalise to the same `canonical.json`.

---

## 7. Sufficiency proof — the six loops

### 7.1 ReAct
```yaml
loop:
  channels: {trajectory: {kind: append, scope: turn}}
  nodes:
    - {id: think_act, kind: agent, role: act, writes: [trajectory],
       tools: [<resource refs>, finish]}
    - {id: observe, kind: tool, role: observe, writes: [trajectory]}   # tool dispatch
  edges: [START→think_act, think_act→observe {when: {tool_called: "*"}},
          observe→think_act, think_act→END {when: {tool_called: finish}}]
  budget: {max_iterations: 12}
  on_budget_exhausted: goto force_answer
  context_policy: {on_overflow: truncate_oldest}
```
Sugar: `loop: {pattern: react, tools: [...], max_iterations: 12}`.

### 7.2 Plan-and-Execute (and Magentic-One)
```yaml
nodes:
  - {id: facts,   kind: agent, role: plan, writes: [ledger]}
  - {id: plan,    kind: agent, role: plan, reads: [ledger], writes: [plan]}
  - {id: execute, kind: map,   over: /plan/steps, as: step, body: worker, concurrency: 1}
  - {id: worker,  kind: graph, ref: react_loop}
  - {id: gather,  kind: join,  mode: all, reducer: {fold: concat, into: /results}}
  - {id: progress,kind: route, role: score,
     decide: {model: {output_schema: progress_ledger.schema.json}},
     emit: [satisfied, continue, stalled]}
edges:
  START→facts→plan→execute, execute→gather {join:{group:x, mode: all}}, gather→progress
  progress→END      {route: satisfied}
  progress→execute  {route: continue}
  progress→plan     {route: stalled}          # replan
stall: {detector: model_judged, patience: 2, on_stall: goto plan}
```
The `progress_ledger.schema.json` is literally Magentic-One's five-key object
(`_magentic_one_orchestrator.py:347-372`) — but as a declared `output_schema`
instead of hand-rolled JSON validation and a hand-rolled membership check.

### 7.3 Reflexion
```yaml
channels:
  reflections: {kind: append, scope: run}     # survives across attempts — the whole point
  candidate:   {kind: last,   scope: run}
  feedback:    {kind: last,   scope: turn}
nodes:
  - {id: generate, kind: agent, role: act, reads: [reflections], writes: [candidate]}
  - {id: verify,   kind: tool,  role: score, ref: <programmatic checker / eval suite>,
     writes: [feedback], output_schema: {passed: bool, detail: string}}
  - {id: reflect,  kind: agent, role: reflect, reads: [candidate, feedback], writes: [reflections]}
edges:
  START→generate→verify
  verify→END      {when: {path: /feedback/passed, equals: true}}
  verify→reflect  {when: {path: /feedback/passed, equals: false}}
  reflect→generate                       # generate.on_reentry: reset (fresh attempt, old reflections retained)
budget: {max_iterations: 4}               # inner
outer:  {repeat: 3, until: {path: /feedback/passed, equals: true}}   # sugar → a wrapping graph node
```
Two nested loops = a `graph` node containing this graph, with its own budget.
Matches `reflexion.py:32-90` exactly, including the crucial detail that
`reflections` outlives the inner loop while `feedback` does not.

**AC-4.5 note:** `verify` here is a `tool` node, i.e. a deterministic checker.
That is the deterministic-first ordering as a *graph property*, not a runtime
convention.

### 7.4 Tree-of-Thought
```yaml
channels:
  frontier: {kind: last, scope: turn, schema: {type: array, items: thought}}
  solutions:{kind: append, scope: turn}
nodes:
  - {id: expand, kind: map, over: /frontier, as: node, body: propose,
     concurrency: 4, max_items: 8}
  - {id: propose, kind: agent, role: act,
     sampling: {n: 5, temperature: 1.0}}                 # n_generate_sample = 5
  - {id: collect, kind: join, mode: all, reducer: {fold: concat, into: /candidates}}
  - {id: score,   kind: agent, role: score, reads: [candidates], writes: [scored]}
  - {id: select,  kind: transform, role: select,
     set: {/frontier: "topk(/scored, 3, by=score, mode=greedy)"}}      # n_select_sample = 3
edges: [START→expand, expand→collect {join:{group:t, mode: all}}, collect→score, score→select,
        select→expand {when: {not: {any: [{path: /solutions, size_gte: 1},
                                          {budget_exhausted: iterations}]}}},
        select→END {when: {any: [{path: /solutions, size_gte: 1}, {budget_exhausted: iterations}]}}]
budget: {max_iterations: 3}                                            # max_steps = 3
```
Every MetaGPT `ThoughtSolverConfig` field maps: `max_steps → budget.max_iterations`,
`n_generate_sample → propose.sampling.n`, `n_select_sample → topk width`,
`method_select → topk mode (greedy|sample)`, `parser → propose.output_schema`,
`evaluator → score node`. `strategy: BFS` is this shape; `DFS` is the same graph
with `frontier` a stack and `concurrency: 1`; `MCTS` is **not expressible** (needs
backpropagation over a persistent tree with visit counts) — declare `unsupported`,
matching MetaGPT's own `NotImplementedError` (`tot.py:230-232`).

Sugar: `loop: {pattern: tree-of-thought, strategy: bfs, branch: 5, beam: 3, depth: 3, scorer: <ref>}`.

### 7.5 Self-consistency
```yaml
nodes:
  - {id: solve, kind: agent, sampling: {n: 5, temperature: 1.0},
     select: {kind: majority, field: answer, normalize: text}}
```
No edges change. `select.kind ∈ {majority, best_of, first_over_threshold, argmax}`;
`best_of` and `first_over_threshold` take `scorer` + `threshold`, matching
`BestOfN` (`best_of_n.py:37-49, 73-74`). `majority`'s tie-break rule must be
specified as "earliest completion wins" to match DSPy (`aggregation.py:48-51`) —
otherwise two adapters disagree on ties and the CTS flaps.

### 7.6 CodeAct
```yaml
channels: {trajectory: {kind: append, scope: turn}, sandbox: {kind: last, scope: turn, durable: false}}
nodes:
  - {id: write_code, kind: agent, role: act,
     output_schema: {generated_code: string, finished: bool}}
  - {id: run_code,   kind: tool,  role: observe, ref: resource://code-interpreter,
     effects: at_least_once, timeout: {run: 30s}, writes: [trajectory]}
  - {id: extract,    kind: agent, role: halt, reads: [trajectory]}
edges: [START→write_code, write_code→run_code, run_code→write_code {when: {path: /finished, equals: false}},
        run_code→extract {when: {path: /finished, equals: true}}, extract→END]
budget: {max_iterations: 5}
on_budget_exhausted: goto extract
```
Mirrors `code_act.py:60-75` (the `finished` flag and the separate extractor) and
`react.py:118` (extract always runs). The only delta from ReAct is that `run_code`
binds a sandbox Resource and `write_code`'s output schema is code rather than a
tool call — which is exactly what DSPy's class hierarchy asserts (`code_act.py:15`).

### 7.7 Loop sufficiency table

| Loop | New node kind? | New edge field? | New channel kind? | New node attribute |
|---|---|---|---|---|
| ReAct | no | no | no | — |
| Plan-and-Execute | no | no | no | `stall` (graph-level) |
| Reflexion | no | no | no | `on_reentry` |
| Tree-of-Thought | no | no | no | `sampling`, `topk` fold |
| Self-consistency | no | no | no | `sampling`, `select` |
| CodeAct | no | no | no | — |

**Result: zero new node kinds are required for any of the six loops.** All six are
graph shapes plus node attributes plus budgets. This is the strongest single
argument for the one-construct thesis in §8.

---

## 8. One construct or two? — the argument

### 8.1 The case for two
The honest case: a topology's state is a *shared workspace across agents*; a
loop's state is *one agent's trajectory*. They have different identity (agent vs
turn), different persistence expectations, different failure blast radius, and
different authors (an ops manager wires a topology; an agent engineer tunes a
loop). D13/D14 argue for surfacing them differently.

### 8.2 Why that case fails as an IR argument
1. **A framework that had both is deleting one.** ADK's `LoopAgent` is deprecated
   "in favor of Workflow" (`agents/loop_agent.py:53-56`). `SequentialAgent` and
   `ParallelAgent` remain only because "Workflow cannot yet be used as an
   `LlmAgent` sub-agent" (same docstring) — i.e. the blocker is a composition bug,
   not a semantic distinction.
2. **The frameworks that ship one construct express both.** AutoGen's `DiGraph`
   handles cycles with exit conditions (`_digraph_group_chat.py:149-205`); Mastra
   puts `loop` in the same union as `parallel` (`types.ts:547-553`); Serverless
   Workflow puts `for`/`while` in the same `task` union as `fork`/`switch`
   (`schema/workflow.yaml:223-239, 677-713`).
3. **Bud already compiles topology → graph.** `Team.to_workflow_manifest()`
   "compiles executable `sequential`, `parallel`, `dag`, `debate`, and `consensus`
   team strategies into canonical Bud Workflows" (`sdk:936-940`). The superset
   obligation (D3) therefore *requires* PACT to have a single graph that Teams
   desugar into.
4. **Zero of six loops needed a new node kind** (§7.7). If loops needed a
   different algebra, at least one would have.
5. **Two constructs means two validators, two optimisers, two checkpointers, two
   CTS suites.** D28's named failure mode #1 ("too complex to actually use") is a
   direct consequence.

### 8.3 The reconciler: `on_reentry`
There *is* a real asymmetry, and it is one field wide. When control returns to a
node:

- a **loop** usually wants the node's accumulated context (the ReAct agent
  remembers its trajectory) → `accumulate`;
- a **topology** usually wants a fresh invocation (a reviewer re-reviewing a new
  draft should not carry the old critique) → `reset`;
- a **search** wants a new independent instance per path → `fork`.

Both behaviours already exist in source under different names:
ADK `ctx.reset_sub_agent_states(self.name)` on each loop iteration
(`agents/loop_agent.py:129`) is `reset`; AutoGen's
`_reset_triggered_activation_groups` restoring `_origin_remaining`
(`_digraph_group_chat.py:429-450`) is the join-side equivalent; ADK's
`use_sub_branch` on dynamic scheduling (`_schedule_dynamic_node.py:52-53`) is
`fork`. Nobody has made it a declarable field. PACT should.

### 8.4 Conclusion (recommendation)

> **ONE construct: `graph`. TWO authoring surfaces: `team.yaml` and `loop.yaml`.
> THREE reconciling fields: `node.on_reentry`, `channel.scope`, and `node.role`.**

`team.yaml` and `loop.yaml` are pattern sugar with normative desugaring into the
same `graph` IR (satisfying D20's no-code first demo, and O1.3's bijection
requirement). `agent.yaml`'s `loop:` field and `teams/*/team.yaml` produce
**identical `canonical.json` node/edge structures**; only `channel.scope` defaults
and `role` tags differ. A conformance test should assert this: author the same
logical system as a team and as a loop and diff the canonical graphs.

---

## 9. Durability and resume across three runtime classes

Target runtimes: **(A) in-process** (gaia-ai-runtime executing the tree natively,
D2), **(B) Temporal-style durable execution** (Temporal / Restate / DBOS /
Inngest / Vercel Workflow), **(C) Bud run ledger** (event-sourced runs with
`plan → execute → resume`, `sdk:18-21`).

### 9.1 What the three classes actually give you

| Concern | Temporal | Restate | DBOS | Inngest | Vercel/Eve |
|---|---|---|---|---|---|
| Instruction set | 18 `COMMAND_TYPE_*` incl. `SCHEDULE_ACTIVITY_TASK`, `START_TIMER`, `START_CHILD_WORKFLOW_EXECUTION`, `SIGNAL_EXTERNAL_WORKFLOW_EXECUTION`, `RECORD_MARKER`, `CONTINUE_AS_NEW_WORKFLOW_EXECUTION` (grep over `runtime/temporal`) | Command/Notification pairs: `Run`, `Sleep`, `Call`, `OneWayCall`, `SendSignal`, `GetPromise`/`CompletePromise`, `Get/SetState`, `AttachInvocation` (`service-protocol/dev/restate/service/protocol.proto:303-760`) | `@workflow`, `@step`, `@transaction`, `send`/`recv`, `set_event`/`get_event`, `sleep`, `start_workflow` (`dbos/_dbos.py:1040,1076,1058,1521,1635,1790,1683,1223`) | 14 `StepType`s incl. `Run`, `SendEvent`, `SendSignal`, `Sleep`, `WaitForEvent`, `Invoke`, `AiInfer`, `AiWrap`, `Fetch`, `WaitForSignal` (`pkg/enums/step_type.go:12-27`); opcodes at `pkg/enums/opcode.go:9-30` | session/turn/step; parked work on approvals, OAuth, subagents (`docs/concepts/execution-model-and-durability.md`) |
| Step identity | positional event IDs; drift handled by `patched()`/versioning | positional `completion_id` (`protocol.proto:643-648`) | **positional counter** `ctx.function_id += 1` (`dbos/_context.py:105,185,203`) | hashed step IDs (`UseDeterministicIDs`, `pkg/devserver/api.go:431`; `HashedID` in state) | opaque |
| Await/join | futures | **`Future` combinator tree** with 4 `CombinatorType`s (`protocol.proto:110-149`) | futures | futures | — |
| Side-effect journaling | `RECORD_MARKER` / activity | dedicated `RunCommandMessage` (`protocol.proto:643`) | `@step` | `step.run` | "step" |
| Recovery bound | retry policy | — | `max_recovery_attempts` (`dbos/_dbos.py:1044`) | — | — |

Two things to steal outright:

- **Restate's `Future` combinator tree** — a suspension carries a *tree* of what
  it is waiting on, with `FIRST_COMPLETED / ALL_COMPLETED /
  FIRST_SUCCEEDED_OR_ALL_FAILED / ALL_SUCCEEDED_OR_FIRST_FAILED`
  (`protocol.proto:110-149`). PACT's suspension record should be this shape, so a
  `join` with `mode: any` over three branches suspends as a legible tree rather
  than an opaque "waiting".
- **Inngest's hashed step IDs** — the only corpus runtime whose step identity is
  *not* positional.

### 9.2 The eight requirements

**R1 — Step identity is content-addressed, never positional.**
```
step_key = H( node_id ‖ branch_path ‖ iteration_index ‖ map_item_key ‖ input_digest )
```
Rationale: DBOS's `function_id` counter (`_context.py:105,185,203`) means
inserting a step anywhere renumbers everything after it. PACT specs are rewritten
by the optimiser (D22 admits agents changing "their own structure and topology"),
so positional identity would invalidate every in-flight run on every accepted
learning candidate. ADK independently names this: `node_name` is "a deterministic
tracking name ... critical for matching events on resume"
(`_schedule_dynamic_node.py:47-49`). `map_item_key` must be derived from the item's
identity, not its index, or reordering the input list re-runs everything.

**R2 — A run pins the spec digest; drift is classified, never silent.**
The run ledger records `canonical_digest`. On resume:
1. digest equal → resume;
2. digest differs → run D23's change-classification function over the spec diff:
   - *cosmetic* (descriptions, instructions text) → resume, record `SpecDrift{level: cosmetic}`;
   - *additive* (new node not yet reached, new optional channel) → resume, record;
   - *structural* (removed/renamed node, changed edge topology, changed schema) →
     **refuse to resume**; emit a typed `ResumeRefused` with the offending node
     and the two options (fork a new run, or apply a declared migration).
3. Explicit `--allow-drift` records the override in the ledger.

This is the fix for the three silent-drop sites found:
`langgraph/pregel/_algo.py:978` (discards pending sends to unknown nodes),
`google-adk .../agents/loop_agent.py:153-159` (`except ValueError:` → "A sub-agent
was removed so the agent name is not found. For now, we restart from the
beginning."; `start_index` stays 0), and
`google-adk .../workflow/_graph.py:175-181` (unmatched route ⇒ warning, branch
ends). Note the ADK loop case is the worst: it silently *re-runs already-completed
work*, which for `effects: external` nodes means double-charging.

**R3 — Effects are declared per node.**
`effects: pure | idempotent | at_least_once | at_most_once | external`, with
`idempotency_key: <expr>` mandatory for `at_most_once`. Eve states the hazard
plainly: "A step interrupted mid-execution re-runs, so make non-idempotent side
effects like charges or emails idempotent, or gate them with approval"
(`docs/concepts/execution-model-and-durability.md`). A no-code author cannot "make
it idempotent" in code; they *can* tick a box that says this tool sends money, and
PACT can then (a) require an idempotency key expression, (b) refuse `durability:
none`, and (c) route it through an approval gate by policy. **This is the single
most important no-code safety feature in the whole orchestration layer.**

**R4 — Suspension is a typed await-tree.** Per R1's key plus Restate's `Future`
shape. Every `human`, `join`, `map`, and `tool` with `effects: external` can
suspend; the suspension record is
`{await: <Future tree>, step_keys: [...], resume_schema: <ref>, deadline}`.

**R5 — Durability is declared as a guarantee, not a mechanism.**
```
durability: none | at_step | at_node | at_effect
```
- `none` — in-process only, no resume (LangGraph `Durability="exit"`, `types.py:92`).
- `at_step` — checkpoint after each super-step (LangGraph `"async"`).
- `at_node` — checkpoint before and after every node (LangGraph `"sync"`).
- `at_effect` — additionally journal every `effects != pure` call before it runs
  (Restate `RunCommandMessage`; Temporal `RECORD_MARKER`).

Adapters declare the highest level they support in the capability lattice; a graph
requesting more than the adapter supports fails **at resolve time**, not at run
time. This is P-5 made concrete.

**R6 — Resume input is a typed `Command`, validated against declared routes.**
Adopt LangGraph's `Command{update, resume, goto}` (`types.py:758-808`) plus Bud's
validation rule: "rejects routes that were not declared by the manifest"
(`sdk:912-913`). Add `Command.step_key` so a resume can target a *specific*
suspended step when several are open (LangGraph's `Interrupt.id` already does
this, `types.py:556-557`).

**R7 — Volatile state is declared and re-acquired.** `channel.durable: false`
(LangGraph `UntrackedValue`, `untracked_value.py:16`). Sandboxes, MCP sessions,
open streams, and provider conversation handles are volatile by definition. On
resume, PACT must re-acquire them via the Resource's `reacquire` contract and
*fail loudly* if it cannot — a resumed run holding a dead sandbox handle is the
classic silent corruption.

**R8 — Cancellation and timeouts are IR.** Two distinct timeouts per node:
`timeout.run` (hard wall-clock) and `timeout.idle` (no observable progress), with
`refresh_on: auto | heartbeat` — LangGraph's design (`types.py:465-479`), and it
is right: a 4-minute reasoning call is not a hang, but a 4-minute silent tool is.
Cancellation must be cooperative and must distinguish `cancelled` from `failed` in
the ledger (LangGraph has both `NodeCancelledError` and `NodeTimeoutError`,
`errors.py:168,190`; DBOS has `preemptible` for cancel-on-workflow-cancel,
`_dbos.py:1102-1103`).

### 9.3 Cross-runtime mapping table

| PACT construct | In-process (gaia) | Temporal-style | Bud ledger |
|---|---|---|---|
| `agent` node | direct call | activity (or child workflow if it has its own graph) | run + child run |
| `tool` node, `effects: pure` | call | local activity | step event |
| `tool` node, `effects: external` | call + journal | activity with idempotency key | step event + effect record |
| `map` node | task group | child workflows or activity fan-out | child runs |
| `join`, `mode: all` | barrier | `ALL_SUCCEEDED_OR_FIRST_FAILED` | reducer step (`.reduce`, `sdk:841`) |
| `join`, `mode: any` | first-completed | `FIRST_COMPLETED` | reducer with quorum |
| `join`, `mode: quorum(k)` | counter | emulated: `ALL_COMPLETED` + cancel | reducer with quorum |
| `human` node | park + local hook | signal / update / `WaitForSignal` | interrupt + `run resolve-interrupt` (`sdk:896-901`) |
| `graph` node | recursion | child workflow | subgraph (`sdk:855`) |
| `budget.max_*` | counters | workflow timeout + counters; `CONTINUE_AS_NEW` when history grows | `limits{...}` (`sdk:824-830`) |
| `channel` durable | in-memory + snapshot | workflow state (bounded!) | ledger state + RFC 7396 patches |
| `channel` `blob` | filesystem ref | **must be external** (payload limits) | content-addressed artifact |
| `durability: at_effect` | journal file | markers/`RunCommand` | effect events |

**Two portability hazards worth flagging in the conformance report:**
- Durable engines bound history size; a long ReAct loop with an `append` trajectory
  channel will hit it. Temporal's answer is `CONTINUE_AS_NEW`
  (`COMMAND_TYPE_CONTINUE_AS_NEW_WORKFLOW_EXECUTION`). PACT needs an equivalent:
  `context_policy.compact` must be able to *truncate the durable channel*, not just
  the prompt, and that truncation must itself be a journaled step.
- `blob` channels (audio/video/screenshots, D16) must never enter workflow state.
  The IR should forbid `blob` channels with `durable: true` unless a
  `content_store` Resource is declared.

---

## 10. What cannot be expressed declaratively — the typed escape hatches

Six escapes, each with a mandatory no-code default so D14 holds.

| # | Escape kind | Why declarative fails | Corpus evidence | **Mandatory no-code default** |
|---|---|---|---|---|
| 1 | `scorer` | arbitrary reward computation | DSPy `reward_fn: Callable[[dict, Prediction], float]` (`best_of_n.py:39-44`); MetaGPT `evaluator: BaseEvaluator` (`tot_schema.py:29`) | a metric URI from the eval registry (`deepeval:*`), a rubric judge, or a programmatic checker from the closed checker library — covers O4.1 |
| 2 | `router` | arbitrary next-speaker logic | AutoGen `selector_func` **commented out of its own config** (`_selector_group_chat.py:355`) and callable edge conditions `Field(exclude=True)` (`_digraph_group_chat.py:45`) | `decide: {model: {...}, emit: [labels]}` or a predicate tree — covers supervisor/swarm/debate |
| 3 | `transform` | computation beyond a pure expression | CrewAI `script` action: "Trusted inline Python source... **This is not sandboxed**" (`flow_definition.py:527-530`) | RFC 7396 patch + JSON Pointer `set` (Bud `.command`, `sdk:891`) + the closed fold set |
| 4 | `tool` | a capability with no MCP/HTTP surface | every framework | MCP server reference (D14 explicitly allows "custom tools (via MCP)") |
| 5 | `search` | tree search with backpropagation | MetaGPT `MCTSSolver` → `NotImplementedError` (`tot.py:230-232`) | `strategy: bfs \| dfs \| beam` with declared branch/beam/depth; **MCTS declared `unsupported` in the lattice** |
| 6 | `stream_transform` | token-level emission policy | LangGraph's seven stream modes (`types.py:120-134`); Eve's compaction internals | a profile-level streaming policy + modality-aware SLOs (D16) |

**Escape hatch type obligations (F-2: "typed and declared, so they remain
analysable"):**

```yaml
kind: escape
lang: python | typescript | wasm | http | mcp
entry: <module:qualname | url | component>
input_schema: <ref>          # required
output_schema: <ref>         # required
effects: pure | idempotent | at_least_once | at_most_once | external   # required
determinism: pure | deterministic | nondeterministic                   # required
timeout: {run: ..., idle: ...}
capabilities: [net, fs, subprocess, secrets]     # what the sandbox must grant
resources: [<resource refs>]
```

`determinism` is load-bearing for §9: only `pure`/`deterministic` escapes may be
replayed rather than re-executed; `nondeterministic` escapes must be journaled
(`durability >= at_effect`) or the resume is unsound. No corpus framework asks for
this declaration; every durable engine requires it implicitly.

**Portability accounting.** An `escape` is `native` only when the target adapter
hosts the same `lang`; otherwise `unsupported`, and the Portability Report says
so (F-3). `lang: http` and `lang: mcp` are portable everywhere, which is why the
no-code defaults route through them.

**Things that are NOT escapes, and why:**
- *Cross-run/global coordination* (tenant rate limits, market clearing across
  runs) — D24 says registry/routing/multi-tenancy stay minimal and adapter-shaped.
  These are Resources, not node kinds.
- *Streaming transport* — that is the adapter's job, not the IR's.
- *Model choice per node* — that is Strategy, resolved by the Resolver (O3.3),
  not an escape.

---

## 11. Risks, gaps, and what to build first

1. **Market/auction has no reference implementation anywhere in the corpus** (§5.8).
   Highest CTS risk in AC-5.1. Build the fixture before the spec freezes.
2. **`queue` (claimable channel) is a PACT invention** with only CAMEL's bespoke
   class as evidence (`task_channel.py:174`). It needs its own conformance test:
   two workers, one item, exactly one execution, plus lease expiry.
3. **`quorum(k)` joins have no durable-engine primitive** — emulated on Temporal
   and Restate. Declare `emulated` in the lattice.
4. **ToT `beam` requires a `topk` fold over a scored list.** Adding `topk` to the
   closed fold set is the only fold that takes parameters; keep it in or ToT needs
   a `transform` escape, which breaks D14.
5. **`sampling`/`select` desugaring must be normative** or `collapse/explode`
   (O1.3, AC-1.2) is not a bijection.
6. **Context/trajectory compaction must be journaled** or durable-engine history
   limits break long loops (§9.3).
7. **The `role` tag has no upstream precedent.** It is justified by the optimiser
   requirement (SYNTHESIS F3: every text field is a trainable parameter), but it is
   an invention and should be marked as such in the spec.
8. **Bipartite (step/event) vs unipartite (node/edge) storage.** LlamaIndex stores
   events as nodes (`representation/types.py:32-58`). PACT should store
   unipartite and *render* bipartite, but a UI/renderer contract is needed so
   D18's "form-renderable" surface does not fork the IR.

---

## 12. Verified vs inferred — explicit ledger

**Verified by reading source (file:line cited above):** every framework construct,
field, validation rule, error message, and semantic note in §1, §2, §6; the
durable-runtime instruction sets in §9.1; the absence of auction/bidding
primitives; the absence of claim semantics in LangGraph channels; MetaGPT's
unimplemented MCTS; AutoGen's excluded `selector_func`; the three silent-drop
sites.

**Inferred (marked in text):** the proposed node/edge/channel closure itself; the
`role` tag; the `on_reentry` field; the `queue` channel design; the market/auction
encoding; the claim that unipartite storage beats bipartite; the CEL-for-transform
/ closed-algebra-for-predicates split; the mapping of PACT `join.mode` onto
Restate `CombinatorType`.

**Not investigated (out of scope or time):** Dify/Langflow node vocabularies (both
are single-runtime object-graph serialisations per the thesis §1.3 table);
`agentscope` (its v2 tree under `src/agentscope/` no longer contains a `pipeline`
or `msghub` module — grep for `MsgHub|sequential_pipeline|fanout_pipeline` over
`src/` returns nothing, so the pipeline abstraction appears to have been removed);
Haystack pipelines; `dapr-agents`; `strands`; `agno`.
