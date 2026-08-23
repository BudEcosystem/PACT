# Research: NVIDIA-labs Object-Oriented Agents (NOOA) — what it is, why it works, and what PACT should take from it

**Status: Research note. Not binding. Written 2026-08-22, revised 2026-08-22 (second pass).**

Sources studied in full, both held locally so every claim here is re-checkable offline:

- Paper: *NVIDIA-labs OO Agents: Native Python Object-Oriented Agents*, arXiv:2607.20709 (49 pp., 22 Jul 2026) — read cover to cover including all four appendices.
  Local: `research/papers/arxiv-2607.20709.pdf`, text extract `research/extracts/nooa-oo-agents.txt`.
- Repository: `github.com/NVIDIA-NeMo/labs-OO-Agents` (`nooa`, ~97k lines of Python across `src/` and `packages/`) — core source, all docs, all 14 SKILL.md files, the memory / bench / CLI / ACP packages, and the examples tree.
  Local: `research/repos/oo-agents/labs-OO-Agents`, pinned at commit `97f52dec84ed88ca3b202f91bee0bc0074626246`, recorded in `research/repos/_clone.log`.

Evidence discipline follows `research/notes/README.md`: source is read in preference to READMEs, and
claims cite `file:line` in the pinned clone. Line numbers below are relative to that commit.

This note has three jobs: (1) explain every load-bearing concept in NOOA and why it is designed that way; (2) record benefits and disadvantages honestly; (3) map what transfers to PACT — checked against PACT's hard constraints (no-code ceiling, air-gapped, translate-or-nothing, fail-then-recommend, harness lowering, minimal-near-scale).

---

## 1. What NOOA is

NOOA is a model-agnostic Python framework where **an agent is a single Python class**. Fields are state, methods are capabilities, docstrings are prompts, type annotations are contracts. A method whose body is a bare ellipsis (`...`) is implemented at runtime by an LLM-driven loop; a method with a real body stays deterministic Python. There is no separate tool registry, prompt template, workflow graph, or callback layer — the class *is* the executable definition, and a metaclass wraps ellipsis methods at class-creation time (`src/nooa/metaclass.py`).

The framing inspiration is PyTorch: "a powerful runtime can still present users with a simple programming model." The target audience is developers **and coding agents** — the paper's term is *agent readiness*: because the interface is ordinary Python (the most in-distribution formal language there is), both humans and models can read, write, test, refactor, and improve agents with zero framework-specific training.

### The five design principles (paper §2)

1. **Reuse Python abstractions** — never introduce a DSL where a mature Python form exists. Classes = agents, methods = capabilities, annotations = contracts, `asyncio` = concurrency, exceptions = failures.
2. **Reframe agentic loops as method calls** — the application sees an agentic loop as a normal typed method call, not an unstructured text exchange.
3. **Move deterministic work out of the agentic loop** — LLMs for judgment; exact rules, arithmetic, parsing, and state transitions in real method bodies. The boundary is local and visible: real body vs `...`.
4. **Unlock the model's existing Python knowledge** — the model acts by writing Python (CodeAct), so it can use loops, conditionals, libraries, and `asyncio.gather` without bespoke prompting.
5. **Expose the harness as explicit APIs** — context construction, event history, and state rendering are model-callable Pythonic APIs, not hidden host machinery.

### The six interface capabilities (the paper's comparison axes)

1. **Typed I/O** — agentic methods have typed inputs and validated typed returns; validation failures are fed back to the model and the loop retries.
2. **Pass by reference** — the model operates on live objects. Large values render as *bounded previews* (`list(len=100, [:5]=[...], [-5:]=[...])`) while the variable itself stays whole in the execution environment.
3. **Code as action** — the model writes Python cells with control flow and inline method/tool calls (`execute_python` / `return_result`).
4. **Loop engineering** — control flow for single- and multi-agent orchestration is ordinary Python available to both developer and model (the model can define new `@strategy` functions in a cell and fan out with `asyncio.gather`).
5. **Object state** — durable, model-visible state lives on the agent object and is re-rendered from the live object each turn, not reconstructed from transcript.
6. **Model-visible harness APIs** — context blocks and the queryable event history are APIs the model itself can call (hidden by default; developer opts them in).

The paper surveys fourteen frameworks/harnesses (LangGraph, Deep Agents, Microsoft Agent Framework, OpenAI Agents SDK, Google ADK, PydanticAI, smolagents, Claude Agent SDK, OpenAI Codex, OpenHands, PI, Hermes, OpenCode, OpenClaw) and finds every one converging on *subsets* of these six — often flag-gated or developer-only — with NOOA the first to combine all six natively on one surface (paper Table 7 + 24 pp. of pinned-commit evidence in Appendix A).

---

## 2. The core mechanisms, one by one

### 2.1 The agent loop (paper §3, `docs/architecture.md`)

Per turn: **render context → call LLM → execute Python → update events and state → (on `return_result`) validate → return**. Two built-in strategies decide how the ellipsis is implemented, chosen per method by decorator:

- **PredictStrategy** — one structured attempt, no tools; output validated against the return annotation; validation errors trigger provider retries. Inputs are rendered in full but guarded by a **hard size cap that fails loudly rather than truncating** — "Predict is single-shot, so a silently-truncated input would mean silently-wrong output."
- **CodeActStrategy** (default) — iterative Jupyter-style REPL. The model has exactly two verbs: `execute_python(code)` and `return_result(value)`. Method arguments are live REPL locals; helpers persist across cells within one call; generated code can call visible methods on `self`, await other generation methods, and spawn subagents.
- Additional strategies exist (Reflexion — generate, self-critique, retry; CodeActLite; PurePython) and strategies are an extension point: they control context overrides, instructions, and the turn loop, but never the method's Python interface.

Design consequences worth naming:

- **Strategy ≠ model.** A method can pin `@strategy(PredictStrategy(), llm=accurate_llm)` while the agent default is a fast model. Routing stays out of the caller-facing contract.
- **Instance locking.** Predict/CodeAct serialize generation calls per agent instance; parallel fan-out = one instance per task. Nested same-agent calls follow stack discipline and append to one event history.
- **Prefill.** Code written between the docstring and the `...` runs deterministically before the first LLM turn, and its variables land in the REPL. The default "inspect inputs" prefill prints each parameter's type and bounded preview as cell one — so the model's first sight of its arguments is itself a checked execution, not prose.
- **Return validation as termination.** The loop only ends when a value validates against the return annotation. There is a documented coercion ladder (bare value → REPL variable name → JSON/literal parse → constructor evaluated with empty builtins) before rejection.

### 2.2 Context: three regions engineered for KV-cache (paper §3.2)

Context is split into **static blocks** (computed once — system prompt, strategy instructions, execution context, `doc(self)` API rendering), **event history** (append-only typed events: tasks, tool calls, Python outputs, results), and **dynamic blocks** (re-evaluated before every turn, rendered at the tail with their generating expression visible, e.g. `<state expr="self.todo.status()">`). The layout is explicitly designed so the cached prefix never invalidates: static prefix unchanged, history append-only, volatile state at the tail. Total fixed overhead is small (~1k chars framework prompt + ~2.5k CodeAct strategy instructions).

Context blocks are one unified value type used identically at five scopes (class kwarg, instance kwarg, `@strategy` decorator, scoped with-block, runtime assignment): literal vs expression content is one axis, cacheable-prefix vs volatile-suffix placement the other, `None` suppresses a block — including the framework's own well-known blocks (`system_prompt`, `self`, `state`, `strategy_prompt`, `execution_context`), which authors may override by key.

Events are typed Python objects with tags; the agent (when granted visibility) can query (`self.events.query(type=..., limit=...)`) and collapse ranges into summaries. `EventQuery` filters (last-N, by-type, current-call) are attachable declaratively at class/instance/method scope. Summarizers are themselves agents (token-budget summarizer for chat; per-method summarizer for batch).

### 2.3 Pass by reference and bounded previews (paper §3.2, §3.4)

The single most important scaling idea: **the amount of data an agent can process is bounded by the execution environment, not the prompt.** A method can take a multi-million-row table; the model sees `records = list(len=1000000, [:5]=[...], [-5:]=[...])` — concrete type, true length, head/tail sample — and operates on the whole thing by writing code. The preview grammar is uniform (list/tuple/dict/set/str/ndarray/structured instances), a bare literal always means *complete*, and a marker always means *elided*, so the model can distinguish small data from truncated data. Truncated stdout is explicitly marked non-recoverable; oversized outputs can be file-backed with the path in the truncation notice so the model can grep the full text.

The invariant is worth stating in isolation because it is cheap and PACT can have it: **a rendered
value is self-describing about its own lossiness.** `src/nooa/agentdoc/_pformat.py:1750-1752`:
*"The marker's presence signals truncation — a bare `[1, 2, 3]` is always a complete value."* No
separate "was this truncated?" channel, no per-call convention to remember. The system prompt states
the grammar once (paper Appendix B, the cached prefix listing every marker form), and every value
the model ever sees obeys it.

The same idea reaches beyond method arguments into the event log. Every event carries a tag, and the
system prompt tells the model how to dereference one: *"Event history: system entries in
`<sys tag="N">`; reference via `self.events["N"]`"* (paper Appendix B). Channel outputs make the
split explicit — `QueueOutput` renders `source`, `value_type` and `value_preview` into the prompt
while the payload itself is carried on the event under
`Annotated[Any, Field(repr=False)]`, invisible to the model but retrievable by non-LLM code as
`event_manager.get(tag).value` (`src/nooa/runtime/channels.py:38-49`). So the history is not a
transcript of values; it is a set of addressable handles with previews attached. That is the design
PACT's run ledger needs if answers are ever to be bound by name rather than re-transcribed.

### 2.4 Visibility: Python-style, hide-explicitly (`AGENTS.md`, agentdoc)

The model-visible API is governed by one rule — visible by default, hidden explicitly. Public methods/fields visible; `_private` hidden; `@hidden` / `Annotated[T, hidden]` / `with hidden:` to hide; `spec(hidden=False)` to opt back in. `context`/`events` APIs exist on every agent but are hidden until opted in per instance. `doc(self)` renders the visible surface compactly (Pydantic constraints as `[≥0, ≤150]`, field descriptions as comments, referenced types expanded once); `doc(obj)` inside the REPL gives progressive disclosure of anything encountered. A standard hygiene rule: **hide the orchestrator entry point** so generated code cannot recursively call the workflow it is inside.

### 2.5 Trust boundary: instructions vs data (`docs/concepts/prompts-and-context.md`)

Docstrings + trusted config are the instruction channel; method parameters (user messages, documents, tool output) are the data channel, rendered by the strategy under truncation controls. Re-interpolating `{param}` into a docstring is treated as a bug for three stated reasons: redundant, unbounded (bypasses truncation), and it **promotes untrusted data into the instruction channel**. Template expansion is reserved for what the signature cannot show (`{self.attr}`, `{len(items)}`).

### 2.6 Orchestration doctrine (`docs/concepts/orchestration.md`)

"Types validate values; Python validates the world." Pydantic proves properties of the returned value; only deterministic code can prove a file exists, a test passed, a row was saved. The house pattern: a hidden pure-Python `run()` that sequences focused agentic methods and applies **evidence gates** the model cannot skip (`evidence_exists()` before findings leave the workflow; `pytest` before "done"). One method = one LLM judgment; a coordinator with no ellipsis methods shouldn't subclass Agent at all. Multi-agent systems are just objects: subclass polymorphism gives role panels, `asyncio.gather` gives fan-out, typed method arguments make handoffs explicit, children inherit nothing implicitly.

### 2.7 Skills: packaging, disclosure, and the load/activate split

A NOOA `Skill` is a plain class whose **docstring is the usage guide** and whose methods are the API; wrapping a third-party object or a Markdown directory (`TextSkill`, Claude-Code-compatible SKILL.md frontmatter, lenient parsing, only `name`+`description` required) also works. Skills may declare:

- `requires: (names...)` — transitive dependency resolution (deps are loaded but deliberately **not activated** — present but invisible until named);
- `context_block: (key, expr)` — a live status block auto-installed on activation, removed on deactivation;
- `attach(agent)` / `detach()` lifecycle hooks; bundled `scripts/` runnable via a path-escape-checked `run_script`;
- `@slash_command` methods — user-typed `/commands` whose **return value is injected as a prompt to the agent** (or display-only with `output_to_agent=False`).

The registry's central idea is the **load/activate split**: *loading* is Python wiring (attribute exists, `attach` ran); *activation* is prompt visibility (unhidden in `doc(self)`, context block installed, one-line summary in the model-visible skill index). The model itself can activate skills mid-run from the index of one-liners. Namespace collisions are a documented scar: a client-supplied skill once silently replaced the agent's real shell "while the model kept being told it still had one" — there is now a protected-attribute check.

### 2.8 Self-extension: three escalating levels

1. **In-cell helpers** — `def` in a REPL cell; gone when the method returns.
2. **Standalone `@strategy` functions in a cell** — the model defines a new LLM-powered typed function with an ellipsis body and fans it out with `asyncio.gather`; runs on a fresh stub, shares no state. This is *the model minting a new operator mid-task*.
3. **Persistent libraries** (`SkillWriting` / `self.libs`) — real Python packages under a managed `libs/` dir: `create(name, description)` → write with shell tools → `reload(name)` (lint gate: forbidden builtins and star-imports are hard errors; imports outside the agent's allowed set warn) → `run_tests(name)`. Each library exports a Skill subclass that auto-attaches as `self.<lib>` with full `doc()` discovery, and can ship its own slash commands. Doctrine: "libraries are forever — a junk drawer pollutes `doc(self)` every turn"; "reload ≠ relearn"; test-before-claiming-done enforced in the orchestrator.

### 2.9 Long-term memory (paper §3.7 + Appendix C; `nooa-memory` package)

An optional subsystem with an **additive guarantee**: `MemoryManager.install(agent)` wires storage, retrieval, and hooks onto an unmodified agent through existing extension points (event subscriptions, middleware, context blocks); uninstalling restores the agent exactly; disabled install is inert.

- **The agent authors its own memory** — seven model-callable verbs (`remember`, `recall`, `search`, `update_memory`, `forget`, `associate`, `deref`), plus an injected ~45-line ownership guide *templated on the actual host API* so it can never document a method the host lacks. Writing a memory is a deliberate model action, not a background extraction pipeline.
- **Verbal boundary** — the model reads/writes ordered ALL-CAPS bands (CRITICAL…TRIVIAL); scoring stays numeric internally; translation happens at exactly one boundary and raises on unknown labels. Ladders chosen so defaults round-trip and HIGH=8.0 lands exactly on the forgetting-protection threshold.
- **Two recall channels** — deliberate (tools) and spontaneous (a BeforeTurn hook derives a query from recent events and injects into a dynamic block, ~2k char budget). **Injection never self-reinforces**: surfaced-but-not-used memories don't gain activation, or the recency signal becomes a feedback loop.
- **Retrieval** — dense KNN ∪ keyword search, ranked by ACT-R activation (relevance = cosine + cue overlap; recency = base-level activation; importance), then beam-limited typed-graph spread with causal edges weighted higher. `explain()` is a dry-run returning the full scored table — the debugging surface for "why wasn't X recalled."
- **Reflection** — offline, interruptible, per-item-committing, idempotent consolidation: deterministic merge of near-duplicates (provenance edge added, dupe archived), optional LLM reconciliation of conflicting values into one current record, deterministic edge formation, importance re-scoring, optional episode→reflection distillation, decay-based pruning. Pruning never removes recent memories, protected types, **open todos**, or importance ≥ 8.
- **One SQLite file as source of truth**; vector indexes derived and rebuildable; every access recorded *on the memory itself* so an exported row carries its usage story.
- **Pass-by-reference memories** — a record may hold `kind:key` typed references (`var:plan`, `file:docs/spec.md`) resolved against **live agent state at recall time** by strict name lookup (never eval — stored strings from a shared store would otherwise be an injection primitive), returning LIVE or a stale-stamped DANGLING snapshot.
- Measured effect: +11.8 RHAE points on ARC-AGI-3 vs the identical agent with markdown files in place of memory; memory engagement per decision correlates with wins (ρ=+0.52); reflection *hurts* pinpoint lookup (−20%) and helps only under genuine retrieval bottlenecks — hence consolidation is configurable per store.
- Caveats found in source: the air-gapped default embedder is hashing-based (no synonymy) so the graph/spread machinery is largely inert offline unless a local semantic embedder is supplied; several schema fields are aspirational (declared, never written); ~60 tuning knobs with `explain()` as the only way to reason about them.

### 2.10 Middleware, observers, hooks, channels

Three interception surfaces with one decision rule: change behaviour → **middleware** (`intercept("agent_call"|"llm_call"|"execute_python", fn)` — onion-style `async (ctx, nxt)`, can mutate messages/code/params, can short-circuit but must set the output slot); react → **observer** (`on(EventType, fn)` — fire-and-forget, errors isolated); telemetry → **instrumentation hooks** (paired before/after protocol; each `before_*` returns a context object handed to `after_*`). A documented trap: hooks are a single contextvar slot that `enable_tracing()` occupies — one more argument against single-slot extension points.

**Channels** are the producer side for long-running/interactive agents: *queue* mode ("must handle" — buffered, drained item-by-item) vs *event* mode ("should notice" — no buffer; a `put()` renders inline into the next turn's prompt). `race()` blocks on all registered channels (registration order = priority; losers restored to channel heads); `spawn()` runs background producers returning `JobHandle`s; bundled producers cover process monitors, timers, cron, file tails. Safety pattern: expose only a read-only `channel.reader` to the model.

### 2.11 Tracing and the run record

Tracing follows the **Python call tree**, not just the LLM transcript: `method.*` → `generation` → `litellm.acompletion` / `code_execution` / `method_call.*` / `tool_execution.*`, so deterministic orchestration is as observable as model calls. Events (agent-visible working history) and traces (operational record with timing/nesting) are explicitly different views. Auto-tracing streams to a local viewer when reachable and is silently off otherwise; durable runs configure JSONL/journal exporters explicitly. The viewer adds annotations (score/label/comment/tags), a playground that re-runs a turn under a different model and diffs, and eval tables reconstructed from `eval.*` span attributes. A separate agent-facing **trace explorer** does progressive-disclosure drill-down (overview → errors → session → turn → search) — built for a *coding agent* to debug another agent's run, including "read the turn to see the context window the model actually saw."

`print_prompt(agent.method, args)` renders the **exact** prompt — real state, real blocks, real arguments — with no LLM call. The `refine-agent-prompt` skill builds an eight-question audit on top of it (execution context clean? duplicate content? internal methods visible? entry point hidden? task prompt non-redundant? skills usable one-shot? returns strongly typed? blocks vs inline docs?), each question paired with an explicit tradeoff to discuss before changing anything.

### 2.12 The harness counts every time it silently helps the model

`src/nooa/runtime/harness_metrics.py` (1,076 lines) exists for one purpose, stated in its own
docstring at line 5: *"Tracks all places where the harness silently 'helps' the model: fence
removal, import stripping, response fixups, error recovery, etc."* Forty-five named recorder methods
cover the whole repair surface — `fence_removal`, `xml_wrapper_stripped`, `import_stripped`,
`gpt4o_double_quote_fix`, `variable_ref_resolved`, `constructor_string_coerced`,
`json_auto_parsed`, `args_normalized`, `tool_call_translated`, `text_to_synthetic`,
`missing_await`, `return_type_redefined`, `infinite_loop`, and so on (`harness_metrics.py:215-400`).
They are flushed onto the OpenTelemetry span for the generation
(`harness_metrics.py:443` `flush_to_span`), and `get_harness_metrics()` never returns `None` — a
no-op singleton stands in outside a session (`harness_metrics.py:994-1031`), so call sites carry no
`if` guard and instrumenting a new fixup costs one line.

Why this matters more than it looks. Every one of those counters marks a place where the *declared*
interface and the *actual* model behaviour diverged, and the harness papered over it. The return
path alone shows the shape: `_handle_return_result` normalises loose keyword arguments into a
`result` field, unwraps a double-quoted string, resolves a bare variable name, parses a JSON string,
and evaluates a constructor expression — five coercions, each metered, before the value is offered
to Pydantic (`src/nooa/strategies/codeact.py:1706-1900`). Without the counters that ladder is
invisible generosity. With them it is a measurement: *how much friction does my interface actually
impose on this model?* That number is a design signal (fix the interface where the counter is hot)
and a model-selection signal (a model needing many repairs is a model the contract is straining).

### 2.13 ATIF: a versioned, cross-harness trajectory interchange format

`src/nooa/atif/` implements **ATIF v1.7** (Agent Trajectory Interchange Format), an
RFC-numbered spec (`0001-trajectory-format-2.md`, cited at `src/nooa/atif/schema.py:5`) for
serialising a run so that other tools — the paper names CyberGym uploaders, dashboards, and SFT
pipelines — can consume it. It is the one genuinely PACT-shaped artifact in the repository, and its
design choices line up with decisions PACT has already taken:

- **Strict by default, extensible by name.** Every model sets `model_config = ConfigDict(extra="forbid")`,
  so an unrecognised key is an error, while each level carries an explicit `extra: dict[str, Any] | None`
  slot for out-of-band data (`schema.py:38`, `:359`). That is exactly PACT's "unknown key = error, plus
  `x-` extension namespaces" (O1.4), arrived at independently.
- **Structural validation and normative rules are separate layers.** The schema module says so
  outright (`schema.py:13-19`): required fields, enum values and conditional fields are enforced by
  Pydantic; the cross-cutting rules — sequential step ids, joinability, context-management boundary
  semantics, `is_copied_context` propagation — are enforced by a separate normative test module and
  at exporter build time. Some correctness properties simply cannot live in a schema. PACT's
  Conformance Test Suite is the same admission, and this is prior art for drawing the line explicitly
  rather than letting the schema pretend to totality.
- **Recursive composition with an identity rule.** A `Trajectory` embeds
  `subagent_trajectories: list[Trajectory]`, each of which *must* carry a unique `trajectory_id`,
  validated at parse time (`schema.py:360-384`). No depth special-cases — PACT's G-4 invariant in
  someone else's format.
- **Compaction is recorded, not hidden.** `StepObject.is_copied_context` marks a step retained
  across a compaction boundary (`schema.py:283-287`), so a reader can tell what the model actually
  saw from what was reconstructed. This is the trace-level version of PACT's structural-honesty
  pillar (T7), and it is the single most transferable field in the format.
- **Resolution keys are named, and non-keys are labelled as such.** `SubagentTrajectoryRef.session_id`
  is documented "**Informational only** in v1.7 — NOT a resolution key" (`schema.py:160-166`).
  Saying which identifiers are joinable, in the schema, is a discipline PACT's ledger should copy.

### 2.14 Evaluation machinery (two separate systems)

- **`nooa-bench` + Harbor** (external benchmarks): a deliberately non-specialized 253-line BenchAgent (shell + repo navigation + todo) run inside a third-party container harness. The transferable idea is the **forced-reflection return contract**: the agent cannot just stop — it must return a validated `TaskResult{solution_description, evidence, command_to_verify}`; trace analysis showed the *absence* of this in other harnesses (OpenCode stops whenever the model doesn't call a tool; 77% of its failed Terminal-Bench trials terminate within ten steps).
- **`util/eval_pipeline`** (internal capability tests): YAML-declared experiments (models w/ registry + tags, test suites with **tiers** `stable`/`frontier`/`horizon`, per-test scorers with weights), JSONL task data (`args/kwargs/expected/metadata`), weighted multi-scorer pass thresholds, `--runs N` self-consistency, A/B agent comparison, crash-safe versioned append-only JSONL results. Scorer families: deterministic output scorers (exact/subset/type match with mismatch pinpointing), **trace-introspection scorers that score process, not product** (AST-parse executed code: did the agent use code vs internal reasoning? did it call for help? did it write a naive keyword classifier?), and fail-closed LLM judges (retry 3×, judge tokens routed to a separate session so they don't pollute agent metrics). Weaknesses recorded: results are reconstructed from span attributes (a second, drifted store from the JSONL), reproducibility pins are missing (no config hash / git SHA / data hash), rubric placeholder errors are swallowed at judge time, and scoring round-trips through a localhost HTTP server even offline.

### 2.15 Containment (paper §4.4, Appendix D; `docs/concepts/safety.md`)

The stated position: in-process validators (AST checks, module deny-lists, blocked `eval/exec/compile/input`, blocking-call and unbounded-loop detection) protect the *agent loop*, not the host; they are defense in depth. The **containment boundary is OS-level** — container/VM/OpenShell. The ARC-AGI-3 fleet demonstrates the layered end state: per-cell kernel-enforced sandbox (Landlock filesystem default-deny, seccomp network block, memory/CPU rlimits, hard cell timeout) over the in-process cell guard, per-run OS privilege drop, end-to-end identity anonymisation (agents only ever see opaque aliases), and a red-team loop re-scanning the live fleet every 30 minutes — 18 passes, zero leakage, the one escape attempt blocked. Key design sentence: "the hard layers are external to the agent, so reading the defense code does not help escape."

### 2.16 Evaluation results (paper §4)

- **Capability suite**: 88 tests × 36 families × 10 models × 5 runs = 4,400 records; 97.9% pass. Every model ≥ 91%. The interface is not a burden — models already know Python. Six **stress families** (batch bookkeeping, error recovery, refinement, decomposition, REPL iteration) fall to 84.7% and separate model scales (small 70.8% vs frontier 93.9%) — the remaining frontier is *disciplined multi-step harness use*, not interface comprehension. Appendix B's forensic lesson: "sophistication and success are orthogonal" — Opus's elegant subagent fan-out failed by re-typing results by hand (dropped item 43 of 50); a plain model passed by careful bookkeeping. Both had a safe path available: *return the computed variable, don't transcribe it*.
- **SWE-bench Verified**: 82.2% (GPT-5.5 xhigh) — best open harness in every configuration tested, ~1.1M tokens/task vs 2.2M for PI at similar score; **the interface margin is largest at low reasoning effort** (harness discipline substitutes for model planning).
- **Terminal-Bench 2.0**: 73.0; **CyberGym**: 86.8% top open-source, with a rule-based "cheat check" over trajectories to prove no network leakage.
- **ARC-AGI-3**: the previous SOTA was DreamTeam — six specialized agents, ~150k lines, 1,821 lines of role prompts, a 4,690-line harness-side retrodiction engine. NOOA replaced it with **one agent + one 50-line world-model skill** (~6.1k lines total): REPL as simulator, context blocks as shared state, memory subsystem as carry-forward ledger. RHAE 50.2% (GPT-5.5) / **85.1%** (GPT-5.6-sol, <$20/game) vs 13.3% for the raw model — a 6.4× harness effect. Failure forensics: the two hung games ran *ad-hoc in-cell searches* lacking the bounds their own *persisted* planners carried — "durable, curated artifacts were reliably better engineered than improvised cell code."

---

## 3. Honest assessment

### What NOOA gets right

- The six capabilities are real and measured, not aspirational; the field comparison shows everyone independently converging on them.
- Token economics as a first-class result: three-region cache layout + pass-by-reference + bounded previews beat transcript-serialization harnesses at equal or better accuracy.
- Typed, validated termination (evidence + verification command) demonstrably prevents unsupported completion claims.
- The evidence-gate doctrine (types validate values; code validates the world) is the cleanest statement anywhere of where declarative validation ends.
- The memory subsystem is the most principled in any harness surveyed (their own Table 8), and its design decisions (verbal boundary, injection-never-reinforces, one inspectable file, live references, additive install) are individually transferable.
- Comment-the-incident discipline: the codebase records *why* in docstrings, often naming the production failure that forced the design.

### Structural disadvantages (from PACT's standpoint)

- **Python-shaped to the bone.** The spec surface is source code: prompts are docstrings, contracts are annotations, context expressions are `eval`'d Python strings, field discovery AST-parses `inspect.getsource` (fails silently without source files). Nothing is portable; there is no IR; behavior is pinned to CPython semantics and litellm.
- **Developer-only.** Fails PACT's no-code ceiling completely — "agent readiness" means *coding agents* can author agents, not analysts. The prompt-refinement methodology assumes a human/agent who reads rendered prompts and Python.
- **Prompt = code identity.** Renaming a method changes behavior (presented as a feature; also means refactoring silently changes semantics — nothing pins meaning independent of names).
- **In-process execution is load-bearing.** Pass-by-reference exists *because* generated code runs in the agent's process; the containment answer is pushed entirely to OS layers the framework doesn't provide. Sandboxed code modes elsewhere trade the reference semantics away at the serialization boundary — NOOA chose the opposite trade.
- **The published spec and the shipping code already disagree.** This is the sharpest checkable
  instance: the paper's own Figure 4 — the canonical illustration of context engineering — writes
  `self.context.set_dynamic("todo", "self.todo.status()")`, and that call is deprecated in the
  shipping tree, emitting a `DeprecationWarning` with a documented replacement
  (`skills/context-blocks/SKILL.md:133-146`). NOOA handles it well: there is a real deprecation
  path with a migration table, plus documented compatibility no-ops (`nooa.visible` per
  `skills/nooa-agentdoc/SKILL.md:106`; Rich's `console`/`indent_guides` accepted-and-ignored per
  `skills/nooa-agentdoc/SKILL.md:132`, with `indent_guides` documented "aesthetic only in our
  impl" at `src/nooa/runtime/pprint.py:22,35`). But the lesson stands and is the argument for a versioned
  schema: when the interface *is* an imperative Python API, the reference description of it goes
  stale between publication and release, and nothing mechanical catches it. PACT's equivalent — a
  schema with a version, unknown-key rejection, and golden files — makes that class of drift a
  test failure rather than a documentation bug.
- **Silent failure modes.** Auto-tracing silently off, hook exceptions swallowed, skill-load failures logged-and-continued, single-slot hooks stolen by tracing — convenient interactively, hostile to reproducibility.
- **Evals not air-gap-clean.** Harbor bootstrap needs network; the internal pipeline needs a localhost HTTP round-trip and optional LLM judges; reproducibility pins (hashes, SHAs) absent.

---

## 4. What transfers to PACT

PACT and NOOA make *opposite* bets on the authoring surface (plain sentences vs Python) but the **same** bet underneath: put the contract where the model's training distribution is, and let a strong runtime do the rest. NOOA's evidence is directly usable: it identifies *which harness mechanics current models actually operate well* — and those mechanics are exactly what PACT's lowering should target, while the authoring surface stays no-code. Mapping, checked against the hard constraints:

### 4.1 Adopt in lowering (PACT owns loop semantics — these become lowering rules)

1. **Three-region context layout as a normative lowering rule.** Stable spec-derived prefix (agent sentences, capability docs), append-only typed history, volatile state at the tail with its generating expression visible. Directly serves the "too slow or expensive" failure mode; framework-independent; measurable (NOOA's fixed overhead ≈ 3.5k chars is a benchmark to publish against).
2. **Bounded-preview grammar for values.** Standardize one preview form (`kind(len=N, head…, tail…)`; bare literal ⇔ complete; marker ⇔ elided; truncated stdout marked non-recoverable; oversized outputs file-backed with the path disclosed). This is the concrete missing piece around PACT's payload blob digests (EXP-8) and `values:` collection — blobs need *render semantics*, not just digests.
3. **Validated termination.** A question's answer shape is already typed in PACT; add NOOA's twist as schema surface: an answer may declare it must carry **evidence** and a **verification step** (`checked-by:` in docs/27 is exactly this — the NOOA data says make it prominent, not an escape hatch). Termination becomes a validated action, not a convention.
4. **Answer-by-reference.** The stress-test forensics ("return the variable, don't retype it") justify docs/27's `bind: remembers.<n>` lane: an agent should be able to answer *with a named value it computed* rather than re-transcribing it through the model. Transcription is a measured, recurring failure mode — design it out.
5. **Instruction/data channel separation as a checked rule.** PACT sentences are the instruction channel; payloads render as data blocks under truncation. The checker should reject templates that splice payload holes into instruction positions — NOOA states the security rationale plainly (untrusted data must not be promoted into instructions). docs/27's "holes in scalar values only" already points this way; add "and never into instruction sentences."
6. **Per-question loop semantics (strategy field).** Predict vs CodeAct vs Reflexion is a *declarative, per-capability choice* in all but syntax. PACT can expose `answered-by: one-shot | code-loop | reflect` (naming TBD) with metered loop guards (max turns, error budget, consecutive-text-only handling) — NOOA's corrected semantics (cumulative error budget; text-only recovery converting a prose reply into a no-op cell with corrective feedback) are worth copying exactly. This slots into §5.5 escape points (`pact:loop/codeact`) but the evidence says it should be first-class, not an escape.
7. **Progressive disclosure.** Capability surfaces render as one-liners with full docs fetchable on demand (NOOA: skill index + `doc()`; same shape as deferred tools). Bounded initial prompt; model pulls detail when needed.
8. **Trace the whole tree.** The run ledger should record deterministic orchestration and model turns in one parent-child tree (NOOA's six span kinds are a good minimal vocabulary), keep agent-visible history and operational trace as distinct views, and mark "logic outside the tree is invisible" as a design smell.

### 4.2 Adopt in the resolver (fail-then-recommend)

9. **A capability battery as the binding gate.** NOOA's 88-test suite is the strongest methodological transfer: small, targeted, per-interface-behavior integration tests (typed calls, structured returns, stateful manipulation, routing to helpers, truncation-marker comprehension, batching, error recovery, decomposition), run per (model × reasoning effort), five repeats, with **stress families** separated from basics. PACT's resolver needs exactly this to refuse-then-recommend with evidence: "this model fails batch-bookkeeping at 2/5 — contract requires ≥4/5 — cheapest passing model is X." Air-gap-compatible (local task fixtures + replayable LLM transport). Two findings shape it: reasoning effort is a capability equalizer for small models (test at the effort the contract will run at), and harness discipline substitutes for model planning at low effort (a strong lowering widens the set of cheap models that pass — the recommender should exploit that, not ignore it).
10. **Intermittency as a first-class measurement.** 94% of (test, model) pairs are stable across 5 runs; failures concentrate as intermittents. Pass criteria should be k-of-n, not one-shot.

### 4.3 Adopt in the schema (authorable, no-code)

11. **Verbal scales at every model-facing and author-facing boundary.** CRITICAL…TRIVIAL over floats — in-distribution for models, authorable for analysts, numeric only inside engines, unknown labels rejected loudly. PACT is already sentence-shaped; this confirms the bet and extends it to quantities.
12. **The load/activate split for capabilities.** "Wired" vs "visible" as independent axes, with dependencies loaded-but-not-activated, and (tier-gated) agent-initiated activation from a one-liner index. Maps cleanly onto `uses:`/`may-use:`.
13. **Skill/capability-declared live-status blocks.** A capability may declare one named status line rendered each turn while active (NOOA's `context_block`). In PACT this must be a *closed* form — a named, harness-provided status renderer or a program reference — never a free eval string.
14. **Namespace-collision rules up front.** NOOA's "client skill silently replaced the agent's shell while the model was told it still had one" is precisely the failure PACT's merge of based-on layers + connected tools could reproduce. Specify collision resolution (reserved names, protected attributes, refuse-don't-shadow) in the schema, not as a later patch.
15. **Reflection/audit tooling for authors:** a `pact explain`-style command that renders the exact lowered prompt for a question against fixture state with **no model call** (NOOA's `print_prompt`), plus an audit checklist in the spirit of the eight questions (duplicate content? entry point exposed? payload spliced into instructions? capability docs one-shot usable?). This is the cheapest possible DX win for the personas exercise.

### 4.4 Adopt in memory design (when PACT grows one)

16. Agent-curated memory with a small verb set; ownership guide templated on the actual granted surface; deliberate + spontaneous channels with **injection-never-reinforces**; one inspectable file, derived indexes; typed live references resolved by strict lookup (never eval) with stale-stamped DANGLING fallback; forgetting guards (protected kinds, open commitments, high importance); consolidation off by default and configurable per store (it measurably *hurts* pinpoint lookup). Air-gap warning from source: without a local semantic embedder the graph machinery is inert — either bundle a local embedding model in the catalogue or ship lexical-recall-only and say so.

### 4.5 Adopt in programs/dynamic structure (docs/27 alignment)

17. **The dynamic-operator ladder maps one-to-one** onto NOOA's three levels: in-cell helpers ≈ ephemeral computation inside a `program` run; standalone `@strategy` functions ≈ the `agent`-shaped answer / dynamic-bottom lane (a model-minted typed operator with its own contract); persistent libraries ≈ programs-in-tree with admission checks. NOOA's lint-gate-at-write (hard errors block the write; import allowlist = declared capabilities) is the same move as docs/27's admission checks — validation at authoring time, not run time.
18. **Fuel and bounds vindicated.** The ARC forensics — persisted planners carried bounds, improvised in-cell searches didn't, and the unbounded ones hung — is direct evidence for PACT's recursion fuel and the `program` kind's `fuel`/`when-it-runs-out`, and for *preferring declared durable operators over improvised generation*. "Durable, curated artifacts beat improvised cell code" should be quoted in docs/27's rationale.
19. **Containment layering, declaratively.** Sandbox resource-kind should require: in-process validation is defense-in-depth only; hard layers external (filesystem default-deny, network block by default, cpu/mem/wall limits); **egress by declaration only** (docs/27 already says this — NOOA's seccomp-default-deny is the same shape); defenses external to the agent so reading them doesn't help escape. The 30-minute red-team rescan loop is a good idea for PACT's eval/SLO story on long fleets.

### 4.6 Adopt in evals (PACT ships evals in-tree)

20. **Process scorers, not just product scorers.** Deterministic checks over the *trace* — did the agent use the declared tool? did it hand-transcribe instead of binding? did it verify before answering? — are cheap, offline, reproducible, and catch what output-matching can't. PACT's ledger format should be stable enough to write these against (a minimal typed event vocabulary, versioned).
21. **Tiers on eval suites** (`stable`/`frontier`/`horizon`) so aspirational tests aren't noise; **k-of-n runs**; weighted multi-scorer aggregation; fail-closed judges with the failure reason preserved; judge cost metered separately from agent cost.
22. **Reproducibility pins NOOA lacks:** spec content hash, data hash, scorer identity, model+params recorded in every result header. One durable result artifact (not two drifting stores); annotations attach to result IDs.

### 4.7 Adopt in the run ledger and the trace format

23. **Meter the harness's own generosity.** Every coercion, fixup and recovery PACT's lowering
    performs on a model's output should be a named counter written onto the run record, on the model
    of `harness_metrics.py`. PACT has more of these than NOOA will, not fewer: sentence-shaped
    contracts lowered onto a probabilistic executor will need repair at the answer boundary, the
    tool-argument boundary and the termination boundary. Three uses follow immediately, and all three
    are things PACT already needs. *Design:* a hot counter names the place where the lowering is
    fighting the model — fix the interface, not the prompt. *Resolution:* repair volume is a cheap,
    offline, model-discriminating signal that costs nothing extra to collect during the capability
    battery (item 9) and sharpens fail-then-recommend from "passed / failed" to "passed, but needed
    4× the repairs of the next model down." *Honesty (T7):* an un-metered coercion is a silent
    degradation by another name — the system quietly accepted something the contract did not
    describe. Make the no-op-singleton choice too, so instrumenting a new fixup is one line and
    never guarded.

24. **Mark what survived compaction.** ATIF's `is_copied_context` (`schema.py:283-287`) is the
    cheapest structural-honesty win available to PACT's ledger: one boolean per step saying whether
    the model actually saw that content or whether it is a post-compaction reconstruction. Without
    it, any process scorer written over a long run (item 20) is scoring a trace that misrepresents
    the model's field of view, and any replay is a different run wearing the same name.

25. **Say which identifiers are joinable.** ATIF labels `session_id` "**Informational only** —
    NOT a resolution key" *in the schema* (`schema.py:160-166`), and states that embedded subagent
    trajectories MUST carry a unique `trajectory_id`, validated at parse time (`schema.py:360-384`).
    PACT's ledger should do both: name the resolution keys, mark the informational ones, and enforce
    child-identity uniqueness structurally rather than by convention. This is what makes a nested
    multi-agent record reassemblable by a tool that did not produce it.

26. **Split structural validation from normative rules, and say so in the schema.** ATIF's schema
    module declares its own limits (`schema.py:13-19`): Pydantic enforces required fields, enums and
    conditional fields; sequential step ids, joinability and compaction-boundary semantics are
    enforced by a separate normative test module. PACT has the same two layers — `pact check` and
    the Conformance Test Suite — and the transferable practice is *documenting the boundary in the
    schema itself*, so nobody mistakes a green validator for a conforming artifact. It also settles
    a recurring design argument in PACT's favour: when a rule cannot be expressed structurally, the
    answer is a conformance test, not a weaker schema.

### 4.8 Reject, with reasons

- **Code-as-authoring-surface** — violates the no-code ceiling; PACT's whole wager is that sentences lower onto the same six capabilities.
- **Free Python expressions in context blocks / dynamic status** — an eval-injection surface and unportable; PACT needs closed forms.
- **In-process execution of generated code** — PACT's programs go through the sandbox resource with declared egress; accept the serialization cost at the boundary, mitigate with answer-by-reference *inside* the sandbox session.
- **Prompt-identity-from-names** — PACT sentences are the meaning; classifier and schema stay outside the search space (existing red line).
- **Single-slot extension points, silent fallbacks, imperative kwarg config** — all three are documented failure sources in NOOA; PACT's schema-validated tree is the antidote and should stay strict (unknown key = error, absent capability = refuse loudly).

### 4.9 Tensions to keep honest about

- **Six-capability lowering vs harness diversity.** NOOA's numbers argue the six capabilities *are* the performant interface. PACT lowers onto multiple frameworks; Table 7 shows most targets support only subsets, often flag-gated. Harness lowering being mandatory means PACT's runtime (gaia) can be six-capability-native, but *fidelity claims* on third-party frameworks need per-target capability statements — a lowering conformance matrix per framework, in the spirit of Appendix A's pinned-commit scoring.
- **Pass-by-reference vs air-gapped portability.** Live references don't serialize. PACT's equivalent is named values + payload digests with preview semantics — weaker than live objects but portable; the gap is real and worth stating in docs.
- **The compression lesson cuts both ways.** One-agent-plus-rich-harness beat six specialized agents — which validates PACT's minimal-topology stance, but only because the harness primitives (REPL-as-simulator, shared blocks, memory ledgers) were strong. Topology minimalism without harness richness would just be weakness.

---

## 5. Examples, production systems, and tooling detail

_(Condensed from full-repo sweeps of `examples/`, `notebook_tutorials/`, `src/nooa/tracing/`, `atif/`, `packages/nooa-cli/`, `packages/nooa-acp/`.)_

### 5.1 What the examples demonstrate

The quickstart tier covers: minimal generation method; structured output with constraint-carrying Pydantic returns and validation-retry; methods-as-tools with zero registration (`doc(self)` is the discovered surface); per-method strategy choice on one class; live docstring templating from instance state (`{self.target_language}`); progressive disclosure of unknown runtime objects via `doc()`; context blocks (fixed prefix vs per-turn expression); token-budget summarization; skills (direct field and model-facing registry); MCP via the standard `.mcp.json` schema with per-instance connection objects; opt-in memory; multimodal `Image` params (CodeAct prefill auto-`show()`s them); ATIF export; and a middleware runtime (request-header injection, a tool-execution guardrail that AST-rejects `os.system`/`subprocess` patterns before execution, lifecycle subscribers).

Composition (notebook 4) has exactly three patterns, all "just Python": sequential handoff through typed arguments; parallel `asyncio.gather` with one instance per task; and **model-directed spawning** — a CodeAct parent whose docstring names child classes, with generated code instantiating and awaiting them. Children created inside an active parent call inherit the parent's resolved LLM; children share no history/context — every handoff is explicit. There is deliberately no DAG language.

Two production systems anchor the claims:

- **ARC-AGI-3 solver**: agent and game run as separate processes communicating only through two append-only JSONL files. The agent is an `InteractiveAgent` whose one CodeAct turn per state ends in a checked `submit_actions(..., rationale)`. The **self-extension loop is real**: `write_helper(filename, source)` persists a model-authored `.py` module (AST-gated to pure compute), `load_helpers()` imports it as `self.h.<module>` for later turns — the world model is durable authored code, refined when its predictions fail. A large share of the code is anti-leakage: module denylists, an AST cell scanner, a jailed `open()`, output redaction so the agent only ever sees an opaque game alias, plus a wall-clock effort ladder stepping `

---

## 6. Pointers

- Paper: https://arxiv.org/abs/2607.20709 · Repo: https://github.com/NVIDIA-NeMo/labs-OO-Agents (studied at commit 97f52de)
- Blog: https://developer.nvidia.com/blog/six-agent-harness-capabilities-for-higher-model-performance/
- Local copies (durable, in-repo): `research/papers/arxiv-2607.20709.pdf`, text extract
  `research/extracts/nooa-oo-agents.txt`, full clone `research/repos/oo-agents/labs-OO-Agents`
  pinned at `97f52dec84ed88ca3b202f91bee0bc0074626246` and logged in `research/repos/_clone.log`.
- Companion work referenced by the paper: Workspace Optimization (arXiv:2605.09650 — learning by writing typed evidence-gated artifacts), Recursive Language Models (arXiv:2512.24601 — prompt-as-variable), Code-as-agent-harness survey (arXiv:2605.18747), OpenShell (github.com/NVIDIA/OpenShell).
