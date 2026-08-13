# Adapters and the lattice

## Why a lattice

Every adapter publishes what it can and cannot do. The table records **real
differences rather than flattering uniformity** — a portability claim that
hides a difference is worse than one that admits it, because the difference
still exists and now nobody is looking for it.

```
              model_cal | tool_call | text_with | parallel_ | streaming | durable_r | connected
reference     native    | native    | native    | native    | unsupport | unsupport | unsupport
pydantic-ai   native    | native    | native    | native    | emulated  | unsupport | native
langgraph     native    | emulated  | native    | emulated  | emulated  | native    | unsupport
langchain     native    | native    | native    | native    | emulated  | unsupport | unsupport
autogen       native    | native    | emulated  | native    | emulated  | unsupport | unsupport
openai-agents native    | native    | native    | native    | emulated  | unsupport | unsupport
anthropic     native    | native    | native    | native    | emulated  | unsupport | unsupport
vercel-ai     native    | native    | native    | native    | emulated  | unsupport | unsupport
```

Seven targets plus `reference` — the framework-free control arm, which is not a
target. `connected` is `connected_tools`, truncated like the other headings.

Three things worth reading:

- **LangGraph** is the only target with native durable resume, and the only one
  that emulates tool calls.
- **AutoGen** cannot carry an assistant sentence *and* tool calls in one result.
  Its text rides in `thought`, so the value survives and the difference is
  declared instead of hidden.
- **`connected_tools`** is the column that decides whether a tool's `connect:`
  line reaches the system it names, and **Pydantic AI is the only target that
  can**: `mcp_bridge` turns a `connect:` into that runtime's own client. Every
  other target here binds a model and nothing else, so on those a `connect:`
  tool arrives at the model as a name and the call is answered `error: no tool
  named …` — which is exactly the kind of thing that must be published before a
  run rather than discovered during one. A row that is `unsupported` here is not
  a broken adapter; it is an adapter you hand the call back to yourself.

## The seams

Each adapter takes the framework's **lowest** seam, so none of them owns the
loop:

| Target | Seam |
|---|---|
| Pydantic AI | `direct.model_request` — below `Agent` |
| LangGraph | `func.entrypoint` / `task` — the functional API, not `StateGraph` |
| LangChain | `BaseChatModel` — below chains, AgentExecutor and LCEL |
| AutoGen | `ChatCompletionClient` — below `AssistantAgent` and group chat |
| OpenAI Agents | `models.interface.Model` — below `Runner`, handoffs, guardrails |
| Anthropic | `messages` content blocks — explicitly *not* the hosted session loop |
| Vercel AI SDK | a `LanguageModelV2` provider with `stopWhen: stepCountIs(1)` |

Plus two that are not targets: a scripted **reference** transport (the control
arm, which makes a divergence attributable to an adapter rather than to
sampling) and an **Ollama** transport for running real local weights
air-gapped.

## The second runtime

The Vercel target runs in **Node**, so its harness is a second, independent port
of the same specification. It agrees with the Python one on the loop, the
ceilings and stage routing — **cross-runtime agreement, which is a stronger
claim than one implementation agreeing with itself.**

!!! warning "It is a smaller port, and it says what it is smaller by"
    A spec carrying `interceptors:`, `context-policy:`, `policy:` or `teamwork:`
    runs there without them and comes back with each named on `unenforced`:

    ```
    interceptors: redact-card-numbers — read and not run on this runtime,
      so nothing is hidden, stopped or sent elsewhere. The Python harness
      carries these out; this port has no chain.
    ```

    It also has no durable resume and publishes `durable_resume: unsupported`
    rather than leaving that to be discovered.

## Two reports, and the difference matters

| Field | Means |
|---|---|
| `unmetered` | *nobody could measure it* — the transport cannot report usage, so a ceiling could not be enforced |
| `unenforced` | *this runtime does not do that* — the rule was read and not applied |
| `never_reached` | *it could never fire* — e.g. a spend cap bound to a zero-priced model |

Three different failures, kept distinguishable. Merging them into one bucket
would send a reader hunting for a transport problem that does not exist.

## Writing an adapter

Implement one method:

```python
async def model_call(self, system, history, tools) -> tuple[str, list[ToolCall]]: ...
```

…plus `lattice()` declaring what you support. Six further things are *asked for
and never required* — `usage()`, `context_window()`, `write_summary()` and
others. A transport that cannot answer says nothing, and the run reports what it
could not therefore enforce **rather than guessing a number**.
