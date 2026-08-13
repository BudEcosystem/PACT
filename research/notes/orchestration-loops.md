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

*(All six of the above are closed in Part II, §R2.8. The `agentscope` inference is
confirmed there.)*

---
---

# PART II — REVISION 2

**Date:** 2026-08-07. **Method:** source reading only, same rules of evidence.
**Baseline:** Part I (above, 2026-07-26) and `docs/20-ARCHITECTURE-DRAFT.md` §7 as
it stands at R12. This revision does **not** restate Part I. It does four things:

1. reads the **Serverless Workflow** DSL schema systematically — the assignment
   named it and Part I only spot-cited it;
2. closes the six frameworks Part I listed as *not investigated*;
3. **corrects three claims** that the architecture draft currently carries as
   PACT inventions or as settled deletions, where source shows otherwise;
4. names **one hole in the closed node set** that all three of the mature
   declarative workflow systems fill and PACT does not.

Paths remain relative to `/home/bud/ditto/agent-inter-op/research/repos/`.

---

## R2.0 What this revision changes, at a glance

| # | Claim as it stands | R2 verdict | Where |
|---|---|---|---|
| 1 | §7.2's eight node kinds are closed and sufficient | **Incomplete** — no failure path exists outside a join group | §R2.2 |
| 2 | `on-reentry` has no prior art (`BET H5`, marked INFERENCE) | **Corrected** — `strands` ships it as `reset_on_revisit`, graph-scoped, default off | §R2.4 |
| 3 | `stall:` deleted; `budget.turns` + `timeout.idle` + `emit-best` suffice (`[R5]` Y7) | **Counterexample found** — a two-agent handoff ping-pong defeats all three; `strands` ships a closed-data detector for exactly it | §R2.5 |
| 4 | DUR-2 classifies spec drift cosmetic/additive/structural and refuses structural | **Superseded by better prior art** — Temporal pins the *run* to a version instead, which removes the classification from the common path | §R2.6 |
| 5 | DUR-1 content-addressed step identity is a PACT departure from positional identity | **Confirmed and corroborated** — Inngest derives `(parent run ID, hashedID)` for the same stated reason | §R2.6 |
| 6 | §7.4's control-flow taint rule is PACT's own | **Independently corroborated** by a standards body, added to the SWF spec three weeks ago | §R2.1.9 |
| 7 | `join` is group-scoped on edges and that is enough | **One case missing** — LangGraph's `defer` is a *run-terminal* join that a static group cannot express | §R2.3 |
| 8 | `queue` (claim + lease) has zero prior art; deferred to v1.1 | **Confirmed** by an exact corpus-wide grep | §R2.9 |
| 9 | `agentscope` pipeline abstraction "appears to have been removed" | **Confirmed** — no `pipeline/` module, no orchestration module, in the v2 tree | §R2.8.1 |
| 10 | PACT's interceptors (§7.10) are new | **Prior art exists** — SWF `extension{extend, when, before, after}` | §R2.1.8 |

---

## R2.1 Serverless Workflow — the DSL read as a whole

`protocols/serverless-workflow`, `schema/workflow.yaml` (1974 lines), at commit
`44c3ecf` ("[Fix #1162] Add security note against evaluating expressions in user
input (#1171)", 2026-07-23).

This is the only artifact in the corpus that is *simultaneously* a closed
declarative control-flow IR, vendor-neutral, versioned by a foundation, and
already implemented by multiple runtimes. It is the closest external thing to
what PACT §7 is trying to be, and it is worth treating as the null hypothesis:
**anything SWF has that PACT does not, PACT must either have a reason to omit or
a hole to fill.**

### R2.1.1 The task union is 12, closed, and `oneOf`

`schema/workflow.yaml:223-239`:

```
task:  oneOf: [ callTask, doTask, forkTask, emitTask, forTask, listenTask,
                raiseTask, runTask, setTask, switchTask, tryTask, waitTask ]
```

Definition sites: `callTask:240`, `forkTask:613`, `doTask:637`, `emitTask:650`,
`forTask:677`, `listenTask:714`, `raiseTask:744`, `runTask:769`, `setTask:956`,
`switchTask:973`, `tryTask:1007`, `waitTask:1057`.

A `taskList` (`:173-183`) is an **array of single-key objects** — `minProperties: 1,
maxProperties: 1` (`:180-181`) — i.e. an *ordered map*. Order is carried by the array
and the name by the sole key. This is the same problem PACT's Typed Expansion solves
with `NN-name.ext`; SWF solves it by refusing the map form entirely. Worth noting
that the most mature declarative workflow spec in existence concluded that an
unordered map cannot carry a task list.

### R2.1.2 `taskBase` — the node-common field set (`:184-222`)

| Field | Line | PACT equivalent |
|---|---|---|
| `if` (runtime expression) | 186-189 | edge `when:` — but SWF puts it on the **node**, PACT on the **edge** |
| `input` / `output` | 190-197 | node `accepts:` / `answers-with:` |
| `export` (write task output to shared context) | 198-201 | node `writes:` |
| `timeout` (inline or **named reference**) | 202-210 | node `timeout:` — but PACT has no named/reusable timeout |
| `then` (flow directive) | 211-214 | edge, see below |
| `metadata` | 215-218 | `x-` |

Two deltas that matter. **`timeout` is referenceable by name** (`TaskTimeoutReference`,
`:208-210`) against a workflow-level `use.timeouts` map — PACT's node `timeout:` is
inline-only, so a workspace cannot state "every external tool call gets our house
timeout" once. Same for `retryPolicy` (`RetryPolicyReference`, `:1050-1053`). For a
no-code author under D14 this is the difference between one line in `workspace.yaml`
and forty lines across the tree.

**`if` on the node, not the edge.** SWF's per-task `if` is a *skip* predicate: false
means the task does not run and control continues. PACT's `when:` on the edge is a
*routing* predicate. These are not the same and both are useful: `if` composes with
a linear `do:` list without introducing an edge, which is why an author writing a
five-step pipeline with one optional step needs no branching vocabulary at all.
**[INFERENCE]** PACT can express this as an edge pair (`A→B when P`, `A→C when not P`)
but it costs the author two edges and a duplicated predicate, and a `then:`-style
linear surface cannot express it at all.

### R2.1.3 `flowDirective` — the anti-spaghetti rule, verified

`:1070-1077`:

```
flowDirective:
  anyOf:
    - enum: [ continue, exit, end ]   default: continue
    - type: string                    # the name of a SIBLING task
```

Four outcomes: continue to the next sibling, exit the containing scope, end the
workflow, or jump to a **named sibling within the same `taskList`**. The draft's
§7.5 claims to adopt this "verbatim" — **confirmed**, and the important half is the
scoping: the free-form string is a sibling name, so there is no cross-depth `goto`
in the type system at all. That is stronger than a validation rule, because it is
unrepresentable rather than merely rejected.

### R2.1.4 `forkTask.compete` — the race is on the fan-**out**, not the fan-in

`:613-636`. `fork.branches` is a taskList; `fork.compete: boolean` (`:632-636`)
"Indicates whether or not the concurrent tasks are racing against each other, with
a single possible winner, which sets the composite task's output."

PACT puts every wait rule on the **edge** (`join.waits-for`). SWF puts the only wait
rule it has on the **node that fans out**. Both are defensible; the draft's §7.3
argument for edge-placement (two independent fan-ins into one target inside a cycle)
is sound and SWF cannot express that case. But note what SWF's placement buys:
`compete` needs no group name, no consistency validation across member edges
(PACT's VAL-4 and VAL-9 exist only because the rule is spread across edges), and
cannot deadlock. **The cost of edge-placed joins is two of PACT's eleven validation
rules.** That is the honest price of the extra expressiveness, and it should be
stated as such rather than presented as free.

### R2.1.5 `forTask` — map and while are ONE task (`:677-713`)

```
for:  { each: <var, default "item">, in: <expr>, at: <index var, default "index"> }
while: <expr>          # ":707" — the condition for the iteration to CONTINUE
do:   <taskList>
```

`for.in` is required (`:711`); `while` is optional and **additive**. So one construct
covers: map over a collection, map with early exit, and — with a constant `in` — a
plain while loop. This is the single strongest external endorsement of the draft's
§7.1 "ONE construct" decision, and it is stronger than the two the draft cites
(ADK deprecating `LoopAgent`, Mastra putting `loop` in the same union as `parallel`),
because SWF unified them *at design time* rather than arriving there by deprecation.

**Delta against PACT:** PACT's `map` node has `over, as, body, concurrency, max-items,
on-error` (§7.2) and no `while`. A bounded map with a data-dependent early exit —
"try each candidate refund policy until one matches, then stop" — needs a cycle plus a
`route` node in PACT and one extra line in SWF. Adding `while:` to the `map` payload
is a one-field change that removes a three-node desugaring from the most common
no-code shape after a plain pipeline. **Recommended.**

### R2.1.6 `listenTask` + `eventConsumptionStrategy` — the fan-in PACT does not have

`listenTask:714-743`; `eventConsumptionStrategy:1527-1568`; `eventFilter:1569-1596`.

```
eventConsumptionStrategy: oneOf
  - all: [ eventFilter ]                       # :1531-1543
  - any: [ eventFilter ]                       # :1544-1563
    until: <expr>  |  <eventConsumptionStrategy with `until: false`>   # :1548-1562
  - one: eventFilter                           # :1564-1568

eventFilter:
  with:      <event properties, minProperties 1>          # :1573-1578
  correlate: { <name>: { from: <expr>, expect: <const|expr> } }   # :1580-1595
```

Three things here have **no PACT equivalent**:

1. **Waiting on external events at all.** PACT's `join.waits-for` waits on
   *internal branches of its own graph*. A PACT graph cannot declaratively say
   "wait until the payments webhook fires or 24h elapse". §7.14's suspension covers
   *asking a person*; there is no *waiting for a system*. For a refund desk — the
   worked example — "wait for the bank to confirm the reversal" is the obvious next
   requirement and it is currently unauthorable.
2. **`until` as a nested consumption strategy** (`:1553-1562`, with `until: false`
   inside to forbid infinite nesting). "Consume any of these events until *that*
   event arrives" is a streaming fan-in with a data-defined close, which is exactly
   the shape a market/auction clearing rule wants (`§5.8` above), and it is the only
   place in the corpus where the *close* condition of a fan-in is itself a filter
   rather than a count or a timeout.
3. **`correlate`** (`:1580-1595`) — a named correlation key extracted from the event
   with `from:`, optionally checked against `expect:`, and *if `expect` is unset the
   first extracted value becomes the expectation*. This is how a durable engine
   matches a late callback to the right suspended run. PACT's DUR-4 suspension record
   is `{await, step-keys, resume-shape, deadline}` — it has a step key but **no
   correlation key**, so an inbound event that does not already know the step key
   cannot be routed to a waiting run. Every A2A callback and every webhook is in that
   category.

`listen.foreach` (`:737-742` → `subscriptionIterator:1947-1974`) additionally lets
each consumed event drive a taskList **as it arrives**, with `item`/`at` variables and
its own `output`/`export`. That is a streaming map. PACT's `map` is over a
materialised collection only.

### R2.1.7 `tryTask` / `raiseTask` / `errorFilter` — see §R2.2

`tryTask:1007-1054`, `raiseTask:744-768`, `errorFilter:1418-1439`,
`retryPolicy:1684-1787`. Treated in full in §R2.2 because it is the hole.

The one detail to record here: `catch` has **four** filters, not one —
`errors.with` (static filter over RFC-7807 fields: `type`, `status`, `instance`,
`title`, `detail` — `:1424-1439`), `when` (dynamic expression), `exceptWhen`
(dynamic negative), and `as` (bind the error to a variable). And `retry` lives
*inside* `catch` (`:1044-1053`), not on the task — so retry is a *response to a
classified error*, never a blanket property. PACT's node-level `retry: {…, on: <error
filter>}` collapses these; the `on:` field is the same idea but the draft never
defines its vocabulary.

`retryPolicy` itself (`:1684-1787`) is worth copying wholesale: `when` / `exceptWhen`
/ `delay` / `backoff: oneOf[constant|exponential|linear]` (`:1707-1728`) /
`limit: {attempt: {count, duration}, duration}` (`:1729-1758`) / `jitter: {from, to}`
(`:1759-1772`). Note **`limit.attempt.duration` (per-attempt) is distinct from
`limit.duration` (all attempts)** — PACT's `retry:` has `max-attempts` and no
total-duration bound, so a node with `max-attempts: 5` and a 10-minute timeout can
burn 50 minutes and no authored field says otherwise.

### R2.1.8 `extension` — prior art for PACT's interceptors (`:1597-1625`)

```
extension:
  extend: enum [ call, composite, emit, for, listen, raise, run, set,
                 switch, try, wait, all ]     # :1603-1607
  when:   <expr>                              # :1608-1611
  before: <taskList>                          # :1612-1615
  after:  <taskList>                          # :1616-1619
```

Declarative before/after hooks, **bound by task KIND** (plus `all`), gated by a
condition. §7.10 of the draft ("Interceptors — rules that may CHANGE what happens")
presents this as PACT's own; it is not. The binding difference is instructive:
SWF binds by *task kind*, PACT binds by *event address prefix* (`step.tool`, `*` —
§7.13). PACT's is strictly more expressive (it can bind a phase of a kind, not just
the kind) and should say so; but SWF's kind-binding is the one a non-technical
author can hold in their head, and `extend: all` is the "every tool call" case that
PACT spells `step.tool`.

### R2.1.9 The security note — §7.4's taint rule, independently arrived at

`dsl.md:386` (added at HEAD, commit `44c3ecf`, 2026-07-23):

> Runtimes **must** evaluate only runtime expressions that are defined in workflow
> definitions, and **must not** parse or evaluate expression syntax embedded in
> workflow input or task input data (for example, `jq`, regular expressions, or
> similar). Treating input data as executable expressions exposes the system to
> injection attacks, potentially allowing unauthorized access to system data and
> resources.

The draft's §7.4 `[R3]` control-flow taint rule — model/external-trust channels may
not reach `when:`/`route:`/`halt:` — is the *agentic generalisation* of this, and it
is now backed by a CNCF-hosted spec that shipped the narrow version as a normative
MUST NOT. That is the strongest external support any §7 rule has. It also implies a
rule PACT does not yet state: **`transform.expr` / `map.over` expressions must be
evaluated from the spec only, never assembled from channel content.** PACT's §7.4
covers control-flow reads; it does not cover *expression construction*.

### R2.1.10 Two more SWF constructs with no PACT form

- **`runTask.await: false`** (`:784-788`, default `true`) — fire-and-forget. Start a
  process and continue without joining. Every PACT node is joined by construction.
  A supervisor that kicks off a long audit and answers the customer now is
  unauthorable. **[INFERENCE]** this is expressible as a `map` with `concurrency` and
  no inbound join edge only if PACT's VAL rules permit a dangling branch, which
  VAL-6 ("at least one start node and one terminal node") does not obviously allow.
- **`schedule`** (`:133-154`): `every` (duration) | `cron` | `after` (delay after
  completion) | `on` (eventConsumptionStrategy). PACT's §7.19 KIND-1 derives a timer
  from a `port` carrying `every:`. SWF's `after:` — "delay before starting again
  *after it completes*" — is the drift-free variant that PACT's `every:` cannot say,
  and `if-still-running: skip` is PACT's answer to the overlap that `after:` makes
  impossible by construction.
- **`evaluate: {language: <default jq>, mode: strict|loose}`** (`:155-172`). The
  expression language is *named in the document*. PACT rejected CEL for
  `when:`/`halt:` (Part I §3.4) and left `transform.expr`/`map.over` unresolved.
  SWF's answer — declare the language, default one, and let a runtime refuse an
  unsupported one — is the portable form, and it is what PACT's capability lattice
  is for.

### R2.1.11 SWF's 12 tasks against PACT's 8 node kinds

| SWF task | PACT | Gap |
|---|---|---|
| `call` | `tool` node | — |
| `run` (container/shell/script/workflow) | `escape` / `graph` node | `await: false` has no form |
| `do` | a chain of edges | — |
| `fork` | `map` / static fan-out + `join` | `compete` ≈ `waits-for: anyone` |
| `for` | `map` node | **`while:` missing** (§R2.1.5) |
| `switch` | `route` node | — |
| `set` | `transform` node | — |
| `wait` | — | **no timer node**; only `port.every:` at workspace scope |
| `listen` | — | **no external-event wait, no correlation** (§R2.1.6) |
| `emit` | — | no way to publish an event from inside a graph |
| `raise` | — | **no way to fail deliberately with a typed error** |
| `try` | — | **no failure path** (§R2.2) |

Five of twelve have no PACT form. Two of those five (`emit`, `wait`) are arguably
Resource/port concerns under D24 and can be declined with a reason. Three — `listen`,
`raise`, `try` — are control flow, and control flow is exactly what §7 claims to own.

---

## R2.2 The hole: PACT has no failure path

### R2.2.1 What PACT has today

A grep of `docs/20-ARCHITECTURE-DRAFT.md` for `on-error|catch|compensat|fallback|
error-handler` returns, for the orchestration layer, exactly three things:

1. node-common `retry: {max-attempts, initial-delay, max-delay, backoff, jitter, on}`
   (§7.2);
2. `on-error` in the `map` node payload (line 5378 — and the payload table is the
   only place it appears; no section defines its values);
3. `join.if-someone-fails: carry-on | stop-the-others | ask-a-person` (line 5461),
   which by construction applies **only to member edges of a join group**.

There is no construct for: *this `agent` node's retries are exhausted, now what?* on
a plain sequential edge. §7.5's `on-budget-exhausted: fail | emit-best | goto <node>`
is the *budget* failure path and has no failure twin.

### R2.2.2 What three independent systems have

**Serverless Workflow — `tryTask` (`schema/workflow.yaml:1007-1054`).** Required
keys `try` + `catch`; `catch` carries `errors.with` (static RFC-7807 filter),
`as`, `when`, `exceptWhen`, `retry`, and `do` (the compensating taskList).
Plus `raiseTask` (`:744-768`) to originate a typed error deliberately.

**LangGraph — `error_handler`, added at node and graph level.**
`libs/langgraph/langgraph/graph/state.py`:
- `add_node(..., error_handler=...)` materialises an auto-generated node named
  `__error_handler__{node}` with a collision check (`:855-870`); the handler is
  flagged `is_error_handler=True` (`:869`) and the failing node records
  `error_handler_node=handler_node_name` (`:879, :891, :903`).
- A graph-level default handler exists and is applied to every non-handler node that
  has none (`:1288-1308`).
- Four normative rules are encoded in the defaulting logic, each with its reason in
  a comment, and **all four are things PACT would otherwise have to discover in
  production**:
  - `:1299-1300` — *"error_handler: regular nodes only — handlers must never catch
    themselves or other handlers."*
  - `:1310-1311` — *"retry: all nodes — handlers should be retried on transient
    failures just like regular nodes."*
  - `:1315-1319` — *"cache: regular nodes only — caching an error-handler result is
    unsafe because the input (failed-node state) may differ across failures even when
    the cache key matches."*
  - `:1322-1323` — *"timeout: all nodes — a stuck handler should be cancelled the
    same way a stuck regular node would be."*

**strands — failure is a first-class node status.**
`frameworks2/strands-sdk-python/strands-py/src/strands/multiagent/graph.py:131-134`:
`GraphState` tracks `completed_nodes`, **`failed_nodes`**, and **`interrupted_nodes`**
as three separate sets, and `GraphResult` reports all three (`:177-181`). A run can
therefore finish with some nodes failed and still return a result — the topology
outlives a member's failure.

### R2.2.3 Why this is blocking, not cosmetic

- **AC-5.1 requires market/auction on ≥3 adapters.** An auction whose clearing rule
  fires only when *every* bidder responds is not an auction; the draft's own
  encoding uses `waits-for: enough-of-them`, which handles slow bidders but not
  *failed* ones — and VAL-4 forces every member edge of the group to agree on
  `if-someone-fails`, so "ignore the two that 500'd, clear on the other six" needs
  `carry-on`, which then also silently ignores a bidder that returned garbage.
- **D14 is the binding constraint.** A support lead building a refund desk cannot
  write a `try/catch`. But the question they *will* hit on day one is "what happens
  when the fraud checker is down?" and today the honest answer is "the customer's
  refund request errors". §7.16's `if-someone-fails: ask-a-person` answers it for
  parallel teammates and nothing answers it for a sequential step.
- **It interacts with DUR-3.** A node with `effects: external` that fails *after*
  the side effect is the case that needs compensation, and PACT declares the effect
  class without providing anywhere to put the compensation.

### R2.2.4 Recommended shape — no new node kind

The closed set survives. Two additions, both fields:

```yaml
# 1. node-common, mirroring §7.5's on-budget-exhausted, in the same vocabulary
if-it-goes-wrong: stop-the-run | carry-on | ask-a-person | goto <node>
asks: <question name>          # required with `ask-a-person`, same rule as join
```

```yaml
# 2. a Tier-0 predicate atom so an edge can route on failure
edges:
  - from: fraud-checker
    to:   manual-review
    when: { atom: went-wrong, of: fraud-checker }   # or: kind, status, timed-out
```

with four validation rules lifted directly from LangGraph's comments:

| Rule | Source |
|---|---|
| A node reachable **only** via a `went-wrong` edge may not itself carry `if-it-goes-wrong` other than `stop-the-run` (handlers must not catch handlers) | `state.py:1299-1300` |
| `retry:` applies to handler nodes | `state.py:1310-1311` |
| Handler nodes are never memoised by `step-key` (the failed-node input differs across failures at an equal key) | `state.py:1315-1319` — and this is a **direct hit on DUR-1**, whose `input-digest` term would otherwise collide |
| `timeout:` applies to handler nodes | `state.py:1322-1323` |

and the error vocabulary itself closed and small — `timed-out | refused | no-answer |
budget | tool-error | policy` — so `retry.on:` and `when: {atom: went-wrong, kind: …}`
share one alphabet, which is what SWF's `errorFilter` (`:1418-1439`) does with
RFC 7807 fields.

The third LangGraph rule is the load-bearing one and is worth restating: **DUR-1's
`step-key = H(node-id ‖ branch-path ‖ iteration-index ‖ map-item-key ‖ input-digest)`
is unsound for a failure handler**, because two different failures of the same node
present the same input digest and the memoised first handler result would be
replayed for the second failure. The failure's own identity must enter the key.

---

## R2.3 LangGraph `defer` — a run-terminal join with no PACT form

`libs/langgraph/langgraph/graph/state.py:379, 395` (and the same pair at `:448/464`,
`:522/537`, `:591/610`, `:667/686` — five overloads):

> `defer: bool = False` — *"Whether to defer the execution of the node until the run
> is about to end."*

Implementation, `:1512-1516`:

```python
self.channels[branch_channel] = (
    LastValueAfterFinish(Any) if node.defer else EphemeralValue(Any, guard=False)
)
```

and for multi-source edges, `:1547-1554`:

```python
if self.builder.nodes[end].defer:
    self.channels[channel_name] = NamedBarrierValueAfterFinish(str, set(starts))
else:
    self.channels[channel_name] = NamedBarrierValue(str, set(starts))
```

So `defer` is implemented by swapping the barrier for its `AfterFinish` variant — the
node fires only once the Pregel loop has drained, i.e. **it joins on "everything that
was ever going to run", not on a named group**.

**Why PACT cannot express this.** §7.3's `join: {group, waits-for}` is
*statically-membered*: the group is the set of edges that name it. That is exactly
right for a declared fan-out. It is wrong for the case `defer` exists for — a node
that fans out dynamically at run time (LangGraph `Send`, PACT `map` with a
data-derived `over:`, or a `route` node whose `starts: all-at-once` emits a variable
number of labels), where a *later* branch may itself fan out further. No static edge
set covers the transitive closure.

**Concretely in PACT terms:** a research desk where the supervisor dispatches N
specialists, and any specialist may itself dispatch a sub-specialist, with one
`write-the-report` node that must see every finding. The reporter's join group can
name the supervisor's edges; it cannot name edges that do not exist until run time.

**Recommendation.** Add one value to the existing field rather than a new construct:
`join.waits-for: everyone-in-the-whole-run` (spelling to match §7.16's authored
vocabulary), defined as *fires once no other node in this graph can run*. It maps to
LangGraph `defer=True` natively; on Temporal it is the workflow's terminal step; in
Bud it is a `.reduce` on the run's completion. **[INFERENCE]** — the mapping is mine;
`defer`'s semantics are read from source. A validation rule follows: at most one
such join per graph scope, and it may not be inside a cycle (there is no "about to
end" inside one).

---

## R2.4 `on-reentry` — the prior art the draft says does not exist

The draft, §7.2 `[R2]`:

> *"PACT's actual contribution is lifting the axis to NODE scope and adding `fork`.
> There is no prior art for node-scoped re-entry policy and none for `fork` as an
> authored field. Marked INFERENCE. BET H5."*

**The re-entry half is wrong.** `frameworks2/strands-sdk-python/strands-py/src/strands/multiagent/graph.py`:

- `GraphBuilder.reset_on_revisit(enabled: bool = True)` (`:374-385`), docstring:
  *"When enabled, nodes will reset their messages and state to initial values each
  time they are revisited (re-executed). This is useful for stateless behavior where
  nodes should start fresh on each revisit."*
- `Graph.__init__(..., reset_on_revisit: bool = False)` (`:505, 521, 539`) — so the
  **default is `False`, i.e. accumulate**.
- Enforcement, `:978-981`: *"Reset the node's state if reset_on_revisit is enabled,
  and it's being revisited"* → `if self.reset_on_revisit and node in
  self.state.completed_nodes: node.reset_executor_state()`.
- What "reset" means is precise and is *context*, not resumption bookkeeping —
  `GraphNode.reset_executor_state()` (`:249-266`) restores `executor.messages`,
  `executor.state` and `executor._model_state` from deep copies captured in
  `__post_init__` (`:237-247`), and clears `execution_status` and `result`.

This is exactly PACT's `on-reentry: reset` vs `accumulate`, authored, declarative,
and shipping. It differs from ADK's `reset_sub_agent_states` (which the draft
correctly identified as resumption state, not context) and from LangGraph's
`Topic(accumulate)` (channel scope). It is **graph**-scoped, not node-scoped.

**Corrected claim.** PACT's contribution is (a) per-node granularity over strands'
per-graph switch, and (b) `fork`. `fork` remains without prior art — I re-grepped and
found nothing that instantiates an independent node instance per traversal path as an
*authored* option.

**Design consequences, both concrete:**

1. **Default `on-reentry` to `accumulate`**, matching strands' `False` default and
   LangGraph's `Topic(accumulate=True)`-by-default reading. The draft does not state a
   default; the two surfaces want different ones (a loop wants accumulate, a topology
   wants reset), and an unstated default here is a cross-adapter behaviour divergence
   of exactly the kind D27 measures.
2. **Admit a graph-level `on-reentry` default with node override.** strands' switch is
   graph-scoped because that is what an author actually reaches for — "this whole
   review board is stateless". Per-node-only means the no-code author writes it N
   times, and D14's ceiling is measured in lines typed.

---

## R2.5 The stall detector — `[R5]` Y7 has a counterexample

The draft deleted `stall:` on the argument that a non-progressing loop is *"already
bounded three times over"* by `budget.turns`, `timeout.idle`, and
`on-budget-exhausted: emit-best`, and that *"no decision in D1–D28 requires stall
detection at all"*. It also pre-committed the re-admission condition:

> *"If a fixture later shows a spin all three miss, `stall` is re-admitted as a
> `timeout.idle` variant, not as a fifth termination construct."*

**Here is the fixture.** A swarm of two agents handing off to each other:
`triage → billing → triage → billing → …`. Each hop makes a model call, writes to
the transcript, and emits events. Therefore:

- `timeout.idle` — defined as "no observable progress" (DUR-8) — **never fires**.
  There is continuous observable progress. It is the wrong instrument: it detects a
  *hang*, and this is a *livelock*.
- `budget.turns` — **fires, at the ceiling**, after burning the whole budget.
- `on-budget-exhausted: emit-best` — then produces a forced answer from a
  conversation that has been going in circles, which is the worst of the three
  outcomes because it is *confidently wrong* rather than an honest failure.

**And a framework ships a declarative detector for exactly this.**
`strands-py/src/strands/multiagent/swarm.py`:

```
Swarm(..., max_handoffs: int = 20, max_iterations: int = 20,
      repetitive_handoff_detection_window: int = 0,
      repetitive_handoff_min_unique_agents: int = 0)        # :245-250
```

docstrings at `:267-269`: *"repetitive_handoff_detection_window: Number of recent
nodes to check for repetitive handoffs"* / *"repetitive_handoff_min_unique_agents:
Minimum unique agents required in recent sequence"*. Enforcement, `:214-224`:

```python
if repetitive_handoff_detection_window > 0 and len(self.node_history) >= repetitive_handoff_detection_window:
    recent = self.node_history[-repetitive_handoff_detection_window:]
    unique_nodes = len({node.node_id for node in recent})
    if unique_nodes < repetitive_handoff_min_unique_agents:
        return False, f"Repetitive handoff: {unique_nodes} unique nodes out of {repetitive_handoff_detection_window} recent iterations"
```

Two integers. No detector plugin, no leaky bucket, no model judgement — which is
precisely why the draft's original objections (undefined `detector: model-judged`,
unspecified decay, CTS flap) do not apply to this form. It is a **pure function of
the run's own node history**, so two adapters cannot disagree about it.

Magentic-One's `is_in_loop` ledger key
(`frameworks/autogen/.../_magentic_one_orchestrator.py:347-354`) is the model-judged
version of the same predicate, and Part I §6.2 already documented that it drives
replanning. Two independent frameworks; one deterministic, one model-judged.

**Recommendation.** Re-admit as the pre-committed variant: a `timeout.idle` sibling
spelled in `teamwork:`'s own vocabulary, e.g.
`stop-if-they-go-in-circles: {looking-back: 6, needs-at-least: 3}` — deterministic,
two integers, off by default (`looking-back: 0`, matching strands), and mapping to
`on-budget-exhausted` for what happens next rather than adding an outcome. This costs
two fields and closes a livelock that D28 failure mode #2 ("portability technically
true but useless") names directly: a swarm that ping-pongs on a weak model and then
fabricates an answer is worse than the framework it replaced, which F-4 classifies as
a defect.

Note this is **more likely on small models**, which is the tier the whole model-
portability thesis targets: handoff loops are a routing failure, and the thesis §7.3
table already records routing fragility rising as the executor weakens.

---

## R2.6 Resume across spec drift — Temporal already solved this, differently

### R2.6.1 DUR-1 is corroborated

`runtime/inngest/pkg/event/defer.go:16-24`:

```go
// event. The ID is derived from (parent run ID, hashedID) so a duplicate
// ...
func DeferEventID(parent ulid.ULID, hashedID string) (ulid.ULID, error) {
    ...
    fmt.Appendf(nil, "defer-event:%s:%s", parent, hashedID),
```

plus `UseDeterministicIDs: true` (`pkg/devserver/api.go:431`) and `HashedID` carried
on the deferred-step record (`pkg/execution/defers/defers.go:68, 85`;
`pkg/cqrs/manager/run_linkage.go:31-43`). Inngest derives step identity from a hash,
for the stated reason of duplicate suppression. **DUR-1's departure from positional
identity is not a PACT eccentricity — it is what the one corpus runtime that had to
solve idempotency across restarts already does.**

### R2.6.2 DUR-2's classification is the wrong default

`runtime/temporal`, grep over `--include=*.go`:

```
VERSIONING_BEHAVIOR_PINNED
VERSIONING_BEHAVIOR_AUTO_UPGRADE
VERSIONING_BEHAVIOR_USE_RAMPING_VERSION
VERSIONING_BEHAVIOR_UNSPECIFIED
```

and, when replay diverges from history, a *typed, first-class* failure cause with its
own metric:

- `service/frontend/workflow_handler.go:1296` —
  `if request.GetCause() == enumspb.WORKFLOW_TASK_FAILED_CAUSE_NON_DETERMINISTIC_ERROR`
- `common/metrics/metric_defs.go:692` —
  `ServiceErrNonDeterministicCounter = NewCounterDef("service_errors_nondeterministic")`

The 18 command types (`grep -o "COMMAND_TYPE_[A-Z_]*"` over `service/`, `common/`,
sorted-unique) are: `CANCEL_TIMER`, `CANCEL_WORKFLOW_EXECUTION`,
`COMPLETE_WORKFLOW_EXECUTION`, `CONTINUE_AS_NEW_WORKFLOW_EXECUTION`,
`FAIL_WORKFLOW_EXECUTION`, `MODIFY_WORKFLOW_PROPERTIES`, `PROTOCOL_MESSAGE`,
`RECORD_MARKER`, `REQUEST_CANCEL_ACTIVITY_TASK`,
`REQUEST_CANCEL_EXTERNAL_WORKFLOW_EXECUTION`, `REQUEST_CANCEL_NEXUS_OPERATION`,
`SCHEDULE_ACTIVITY_TASK`, `SCHEDULE_NEXUS_OPERATION`,
`SIGNAL_EXTERNAL_WORKFLOW_EXECUTION`, `START_CHILD_WORKFLOW_EXECUTION`, `START_TIMER`,
`UNSPECIFIED`, `UPSERT_WORKFLOW_SEARCH_ATTRIBUTES`.

**The argument.** DUR-2 says: on resume, diff the spec, classify the diff
(cosmetic / additive / structural), resume for the first two, refuse for the third.
That places a **semantic diff classifier on the hot path of every resume**, and it
inherits D23's classifier — a component the draft itself requires to be
"conservative and explainable", which for spec-diff-vs-in-flight-run means
conservative-to-the-point-of-refusing.

Temporal's answer avoids the classifier entirely for the common case: a run is
**pinned** to the version it started on and finishes there; new runs get the new
version; `AUTO_UPGRADE` is the opt-in for runs that should follow the deployment.
The classifier is then needed only when someone explicitly asks to migrate an
in-flight run.

**This matters more for PACT than for Temporal**, because D22 lets *the agent itself*
rewrite its instructions, tools and topology, and D23 auto-applies low-risk changes.
Under DUR-2-as-written, every auto-applied learning candidate runs the classifier
against every in-flight run and must be proven cosmetic — so the learning loop's
throughput is coupled to the resume path. Under pinning, it is not: the learned spec
becomes the next run's spec and nothing in flight is disturbed.

**Recommendation.**

```yaml
graph:
  when-the-spec-changes: finish-on-the-old-one | move-to-the-new-one   # default: finish-on-the-old-one
```

- `finish-on-the-old-one` (= PINNED): the run resolves its documents from the pinned
  `contract-digest` + `doc-digest` for its whole life. No classifier, no refusal, no
  `--allow-drift`. Requires the pinned canonical form to be retained for the run's
  maximum lifetime — a real storage obligation and the honest cost of this choice.
- `move-to-the-new-one` (= AUTO_UPGRADE): DUR-2's classifier as written, refusing on
  `structural`.
- Either way, replay divergence gets a typed cause and a counter, following
  `WORKFLOW_TASK_FAILED_CAUSE_NON_DETERMINISTIC_ERROR` — PACT currently has
  `ResumeRefused` for the *pre-flight* check but nothing named for a divergence
  discovered *mid-replay*.

### R2.6.3 Inngest made model inference a first-class durable step

`runtime/inngest/pkg/enums/step_type.go:12-27` — 14 step types:
`Unknown, Run, SendEvent, SendSignal, Sleep, WaitForEvent, Invoke, AiInfer, AiWrap,
Fetch, WaitForSignal, Metadata, GroupExperiment, RealtimePublish`.

`pkg/enums/opcode.go:9-30` — opcodes include `AIGateway`, `Gateway`, `WaitForSignal`,
and **`DeferAdd` / `DeferAbort`**.

`AiInfer` / `AiWrap` / `OpcodeAIGateway` are the finding: a general-purpose durable
execution engine concluded that an LLM call is **not** just another `Run` step and
gave it its own type. That is independent support for PACT's `agent` vs `tool` node
split being a *durability*-relevant distinction and not only a semantic one — the
journal entry for a model call carries a request/response shape the engine knows
about, which is what makes cost accounting and replay-without-re-billing possible.
It also supports §5.3's wire-request IR being a first-class artifact.

### R2.6.4 Restate — the await-tree nests, verified

`runtime/restate/service-protocol/dev/restate/service/protocol.proto`:
`enum CombinatorType` at `:110`, values `FIRST_COMPLETED = 1` (`:114`),
`ALL_COMPLETED = 2` (`:116`), `FIRST_SUCCEEDED_OR_ALL_FAILED = 3` (`:118`),
`ALL_SUCCEEDED_OR_FIRST_FAILED = 4` (`:120`). The doc comment at `:132-136` shows a
**nested** example — an `ALL_SUCCEEDED_OR_FIRST_FAILED` combinator containing a
`FIRST_COMPLETED` one — and `combinator_type` is field 5 of the suspension record
(`:146`), with `SuspensionMessage` at `:151`.

DUR-4's "typed await-tree, shaped like Restate's `Future` combinator tree" is
therefore literally implementable and the nesting is not an extrapolation.

Every command message carries a `completion_id` / `result_completion_id`
(`:222, 263, 282, 333, 343, 384, 394, 429, 439, 453, 463, 484, 494, 507-522,
529-573, 643-654, 675-685, 706-716`). These are **monotonic per-journal integers**,
i.e. positional — which is the same weakness DUR-1 identifies in DBOS, present in
Restate too. A Restate adapter therefore cannot preserve step identity across a
spec edit, and that belongs in its capability-lattice row rather than being
discovered at 3am.

---

## R2.7 Cross-runtime durability, consolidated

| Concern | Temporal | Restate | DBOS | Inngest | PACT today |
|---|---|---|---|---|---|
| Step identity | positional event IDs | positional `completion_id` (`protocol.proto:222 ff.`) | positional counter | **hashed** `(parent, hashedID)` (`event/defer.go:16-24`) | content-addressed (DUR-1) ✔ |
| Spec/version drift | `VERSIONING_BEHAVIOR_{PINNED, AUTO_UPGRADE, USE_RAMPING_VERSION}` + typed `NON_DETERMINISTIC_ERROR` cause (`workflow_handler.go:1296`) | — | — | — | classifier only (DUR-2) — **change recommended** §R2.6.2 |
| Join algebra | futures | 4 nested combinators (`protocol.proto:110-149`) | futures | futures + `DeferAdd/Abort` | 5 `waits-for` values ✔ + missing run-terminal §R2.3 |
| Model call as a step kind | activity (generic) | `Run` (generic) | `@step` (generic) | **`AiInfer` / `AiWrap` / `OpcodeAIGateway`** | `agent` node ✔ |
| External event wait + correlation | signals | `GetPromise`/`SignalNotification` | `recv` | `WaitForEvent` / `WaitForSignal` | **none** — §R2.1.6 |
| History growth | `CONTINUE_AS_NEW` | — | — | — | DUR-9 (journaled compaction) ✔ |
| Deliberate typed failure | `FAIL_WORKFLOW_EXECUTION` | — | — | — | **none** — §R2.2 |
| Failure handler / compensation | (in SDK) | — | — | — | **none** — §R2.2 |

Two rows are empty on PACT's side and are control flow, not plumbing.

---

## R2.8 The six frameworks Part I did not read

### R2.8.1 agentscope — the pipeline abstraction was deleted

`ls frameworks2/agentscope/src/agentscope/` →
`agent app credential embedding event exception formatter mcp message middleware
model permission rag skill state tool tts types workspace` — **no `pipeline/`
module**. `ls src/agentscope/pipeline/` returns nothing;
`grep -rn "def sequential_pipeline|def fanout_pipeline|class MsgHub|class .*Pipeline"
src/agentscope/` returns **zero hits**. `grep -rln "handoff|orchestrat"` over `src/`
returns four files, all in the RAG/session service layer
(`app/_service/_knowledge_base.py`, `app/rag/index_worker/__init__.py`,
`app/_service/_session.py`, `middleware/_rag.py`) — none of them orchestration.

The v2 tree is a **single-agent runtime plus a server**: `agent/` contains only
`_agent.py`, `_config.py`, `_structured_output_tool.py`, `_utils.py`.

**Negative finding, and it is a data point for the ONE-construct decision from the
opposite direction:** a framework that shipped a named-topology combinator library
(`sequential_pipeline`, `fanout_pipeline`, `MsgHub`) removed it wholesale rather than
generalising it. Part I's inference is confirmed.

### R2.8.2 Haystack — a readiness lattice, not a super-step model

`frameworks2/haystack/haystack/core/pipeline/base.py:75-79`:

```python
class ComponentPriority(IntEnum):
    HIGHEST = 1
    READY    = 2
    DEFER    = 3
    BLOCKED  = 4
```

`_calculate_priority` (`:1285-1306`) assigns one of the four per component per tick,
and a priority queue picks the lowest number. `DEFER` means *"has some inputs but is
waiting for more — run it only if nothing is READY"*, i.e. **the "should I wait for
the other branch?" question is answered at run time by a heuristic**, not declared.
The class carries its own hazard: `:1618-1624` documents a "stale queue" check —
*"`ComponentPriority.DEFER > ComponentPriority.READY` which is true, indicating that
the queue is stale"* — forcing a recompute.

This is a **third** execution-model class in the corpus, after LangGraph's super-steps
and AutoGen's activation ready-queue. It is the one PACT should explicitly *not*
adopt, and saying so is useful: PACT's `waits-for` makes the same decision
*declaratively*, which is why a PACT graph's execution order is a function of the
document and Haystack's is a function of the scheduler. That is a D27 (fidelity
within a margin) argument, since a heuristic scheduler is exactly what makes two
adapters disagree.

`max_runs_per_component: int = 100` (`base.py:92, 103, 112`) with a dedicated
`PipelineMaxComponentRuns` exception is a **per-node** execution cap. PACT deleted
`bounds.max-transitions` and `bounds.max-iterations` in favour of the single global
`budget.turns` (`[R5]` Y20). Haystack and Bud (`maxNodeExecutions`) both keep a
per-node cap, and it catches a different failure: one node spinning inside an
otherwise-healthy graph. **[INFERENCE]** `budget.turns` bounds the total and will
eventually stop it, but the diagnostic is "the run ran out of turns" rather than
"`fraud-checker` ran 100 times", and O7.3 requires the error to name the fix. A
per-node execution ceiling is cheap and is a diagnostic-quality argument, not an
expressiveness one.

### R2.8.3 strands — graph + swarm, and the two corrections

Covered in §R2.4 (`reset_on_revisit`) and §R2.5 (repetitive-handoff detection).
Remaining structure, `strands-py/src/strands/multiagent/`:

- `graph.py:108-171` `GraphState` — `completed_nodes` / `failed_nodes` /
  `interrupted_nodes` as three sets (`:131-134`), `execution_order` (`:135`),
  `accumulated_usage` + `accumulated_metrics` (`:141-142`).
- `should_continue(max_node_executions, execution_timeout, …)` (`:152-172`) — two
  graph-level bounds, each returning a **reason string**, not a bare bool
  (`:161-168`). PACT's `on-budget-exhausted` should carry the same: the reason is
  what the trace and the Portability Report need.
- `GraphEdge.condition: EdgeCondition | None` (`:187-193`) plus an
  `EdgeConditionWithContext` **Protocol** (`:66`) — callable conditions again, and
  therefore again non-serialisable. Part I's finding #3 holds for a sixth framework.
- `_validate_node_executor` (`:279-299`) refuses a duplicate executor *instance*
  and refuses an `Agent` with a session manager: *"Session persistence is not
  supported for Graph agents yet."* A framework whose multi-agent graph cannot carry
  per-agent session state is a live example of why PACT keeps state in channels with
  a declared `scope:` rather than inside the agent object.
- `swarm.py:121` `SharedContext` + `:170-190` `SwarmState{shared_context,
  node_history, handoff_node, handoff_message}` — a blackboard by another name, and
  `handoff_message` confirms Part I §5.5's reading that a handoff carries a payload,
  not just a target. PACT's `route.assigns:` (`[R5]`) is the right shape for this.

### R2.8.4 agno — a topology enum replaced by orthogonal booleans

`frameworks2/agno/libs/agno/agno/team/team.py:73` `class Team`, with
`respond_directly: bool = False` (`:108`), `delegate_to_all_members: bool = False`
(`:110`), `determine_input_for_members: bool = True` (`:112`); same three in
`__init__` (`:447-449`) and in `_init.py:73-74, 205-206`. A conflict rule at
`_init.py:729-733` warns and forces `respond_directly = False` when both it and
`delegate_to_all_members` are set.

There is no `mode: route | coordinate | collaborate` enum in the current source.
**Negative finding with a design reading:** a framework that shipped named team modes
replaced them with three orthogonal booleans, then needed a runtime conflict check
because two of the three interact. That is the *worst* of both worlds — named modes
are teachable but not composable; free booleans are composable but produce illegal
combinations. PACT's position (`teamwork:` as authored sugar with a normative
desugaring into one graph, §7.7) is the third option and this is evidence for it: the
sugar stays teachable, and the desugaring is where the combination is checked, at load
time rather than at run time.

`determine_input_for_members` is worth one more line: it is the switch between "the
supervisor rewrites the task for each member" and "each member gets the raw input".
PACT's `route.assigns:` covers the first; the second is `carry: null` (the graph's
shared scope). Both expressible.

### R2.8.5 dapr-agents — a supervisor ledger that mutates its own plan

`runtime/dapr-agents/dapr_agents/agents/orchestrators/llm/schemas.py`:

```
PlanStep / IterablePlanStep{objects: List[PlanStep]}        :23-29
NextStep{next_agent, instruction, step: int, substep: Optional[float]}   :32-58
TaskPlan{plan: List[PlanStep]}                              :60-63
PlanStatusUpdate{step, substep, status: not_started|in_progress|blocked|completed}  :66-85
ProgressCheckOutput{verdict: continue|completed|failed,
                    plan_needs_update: bool,
                    plan_status_update: Optional[List[PlanStatusUpdate]],
                    plan_restructure: Optional[List[PlanStep]]}          :87-104
```

This is Magentic-One's progress ledger (Part I §6.2) with two additions PACT should
take:

1. **The supervisor's structured output can rewrite the plan** — `plan_restructure:
   List[PlanStep]` — and can mark individual steps `blocked` — `plan_status_update`.
   PACT's `route` node emits a label and, since `[R5]`, `assigns:` a payload per
   label. Neither covers "and also mark step 3 blocked in the shared plan". This is
   expressible as a `route` node with a `writes:` onto a `merge` channel, but §7.2's
   `route` payload does not list `writes:` — only `assigns:`. **One-line fix:
   `route` nodes take the node-common `writes:` like every other kind**, or the
   plan-and-execute pattern (AC-5.2, required) needs a `transform` node after every
   routing decision.
2. **`substep: Optional[float]` with a normaliser** (`:45-58`, `:68-80`) — plan steps
   are numbered `3, 3.1, 3.2` so a step can be *inserted* without renumbering its
   successors. That is the plan-level analogue of DUR-1's rule that `map-item-key`
   derives from item identity and never from list index, arrived at independently by
   an orchestrator author for the same reason. Good corroboration; worth citing in
   DUR-1's rationale, since DUR-1 currently rests only on DBOS's counterexample.

### R2.8.6 Dify / Langflow

Not re-read. Thesis §1.3's judgement — *"each is a serialisation of one runtime's
object graph, which is the definition of non-portable"* — is a positioning claim, not
a design input, and nothing in this stream depends on it. Recorded as **not
investigated** rather than confirmed.

---

## R2.9 Re-verified negatives

| Claim | Method | Result |
|---|---|---|
| No claimable work channel with a lease anywhere in the agent corpus | `grep -rln "visibility_timeout\|visibilityTimeout\|lease_duration\|leaseDuration\|renew_lease" --include=*.py --include=*.ts --include=*.go frameworks/ frameworks2/` | **zero files**. Confirms `[R2]` X3's withdrawal of `queue` and the v1.1 deferral |
| CAMEL's `TaskChannel` has claim but not lease | `grep -n "lease\|Lease" frameworks2/camel/camel/societies/workforce/task_channel.py` | **zero hits**. The atomic claim at `:174` stands; there is no expiry, so a crashed worker holds a task forever |
| No quorum / k-of-n join primitive in any durable runtime | Restate's 4 combinators (`protocol.proto:110-120`); Temporal's 18 command types; Inngest's 14 step types | none expresses k-of-n. `enough-of-them` is `emulated` on every runtime, as the draft says |
| No timed join (`whoever-answers-in-time`) primitive | same | none. `emulated` everywhere |
| No auction / contract-net / bidding implementation | Part I §5.8's grep | unchanged; still the highest-risk row in AC-5.1 |

---

## R2.10 The five deliverables, restated with R2's deltas

**(1) Closed minimal node and edge set.** Part I §3 / draft §7.2's **eight** node
kinds and one edge type survive R2 unchanged — nothing in SWF, strands, Haystack,
agno, dapr-agents or agentscope needs a ninth kind. But the *field* set is
incomplete in four places, all of which are one or two fields rather than new kinds:

| Missing | Shape | Forced by |
|---|---|---|
| a failure path | node `if-it-goes-wrong:` + edge atom `went-wrong` | §R2.2 — SWF `try`, LangGraph `error_handler`, strands `failed_nodes` |
| a run-terminal join | `waits-for: everyone-in-the-whole-run` | §R2.3 — LangGraph `defer` |
| bounded iteration on `map` | `map.while:` | §R2.1.5 — SWF `forTask.while` |
| `writes:` on `route` | node-common, already exists for other kinds | §R2.8.5 — dapr-agents `plan_status_update` |

**(2) Loops as data.** Part I §7's six sketches stand; nothing in R2 requires a new
loop primitive. Two corrections: `on-reentry` needs a stated default (`accumulate`,
§R2.4) or ReAct and Reflexion diverge across adapters; and the livelock case
(§R2.5) is a loop-termination gap, not a topology one, so it belongs in the loop
budget vocabulary.

**(3) One construct or two.** The ONE-construct decision is *strengthened*. SWF's
`forTask` unifies map and while **by design** (`:677-713`), which is a better
argument than ADK's deprecation because it was not arrived at by retreat.
agentscope deleting its combinator library and agno replacing its mode enum with
booleans are two more frameworks concluding that named topologies are not the right
storage form. No evidence found for two constructs.

**(4) Durability across three runtime classes.** DUR-1 is corroborated (Inngest
hashing, dapr-agents substep numbering). DUR-4 is verified implementable (Restate's
nested combinator example). DUR-2 should change from *classify-and-refuse* to
*pin-by-default with classify as the opt-in*, following Temporal's
`VERSIONING_BEHAVIOR_PINNED` (§R2.6.2) — this is the single highest-value change in
this revision, because it decouples the learning loop (D22/D23) from the resume path.
Two new obligations: a typed mid-replay divergence cause (Temporal has one, PACT
has only a pre-flight `ResumeRefused`); and a **correlation key** on the suspension
record, without which no external callback can find its waiting run (§R2.1.6).

**(5) What cannot be declared.** Part I §10's six escapes stand. R2 adds no seventh
and **removes the case for one**: the failure path (§R2.2) looked like it might need
an escape and does not — SWF, LangGraph and strands all express it as data. The one
place where declarative genuinely runs out remains unchanged: MCTS-class search with
backpropagation over a persistent tree (MetaGPT's own `NotImplementedError`), plus
arbitrary reward computation, which the eval-metric registry covers for every case
D14 needs.

---

## R2.11 R2 evidence ledger

**Verified by reading source (every file:line above):** the SWF 12-task union and
every field cited from `schema/workflow.yaml`; `dsl.md:386`; LangGraph `defer` and
`error_handler` including the four defaulting comments; strands `reset_on_revisit`,
`reset_executor_state`, `repetitive_handoff_detection_window`, `GraphState`'s three
node-status sets, `_validate_node_executor`; Haystack `ComponentPriority` and
`max_runs_per_component`; agno's three team booleans and the conflict warning;
dapr-agents' orchestrator schemas; agentscope's missing pipeline module; Temporal's
18 command types, four versioning behaviours, and the non-determinism failure cause
plus its metric; Restate's four combinator types, the nested example, and the
per-message `completion_id`s; Inngest's 14 step types, opcode list, and
`DeferEventID`; the five negative greps in §R2.9.

**Inferred (marked in text):** the mapping of `defer` onto a proposed
`waits-for: everyone-in-the-whole-run`; the claim that PACT's edge-placed joins cost
exactly VAL-4 and VAL-9; the reading that per-node execution ceilings are a
diagnostic-quality rather than expressiveness argument; the proposed spellings of
`if-it-goes-wrong:`, `when-the-spec-changes:` and `stop-if-they-go-in-circles:`; the
claim that `run.await: false` is unrepresentable under VAL-6.

**Not investigated:** Dify and Langflow node vocabularies (§R2.8.6); the SWF
`callTask` sub-union (`:240-612` — AsyncAPI/OpenAPI/gRPC/HTTP call shapes), which is
a Resource concern rather than a control-flow one; DBOS beyond Part I's reading;
`dapr` core workflow engine internals (only the Python SDK's `when_all` surfaced, at
`tests/apps/perf/workflowsapp/app.py:17,105`, with no `when_any` in the tree).
