# How it works

Three mechanisms. Each exists because a simpler answer was tried and failed.

---

## 1. The harness owns the loop

**The problem.** If you map an agent onto each framework's own agent
abstraction, that framework's control flow leaks in — and two "identical" agents
diverge. This is the failure every prior portable format hit.

**What PACT does instead.** A framework is used only as a **transport**:
something that can perform *one model call* and *execute one tool*. Everything
else — the step sequence, halting, tool dispatch, retry, history construction —
lives in PACT's harness, identically for every target.

That is why each adapter takes the framework's **lowest** seam:

| Target | Seam taken |
|---|---|
| Pydantic AI | `direct.model_request` — below `Agent` |
| LangGraph | `func.entrypoint` / `task` — the functional API, not `StateGraph` |
| LangChain | `BaseChatModel` — below chains and AgentExecutor |
| AutoGen | `ChatCompletionClient` — below `AssistantAgent` |
| OpenAI Agents | `models.interface.Model` — below `Runner` |
| Anthropic | `messages` content blocks — *not* the hosted session loop |
| Vercel AI SDK | a `LanguageModelV2` provider, `stopWhen: stepCountIs(1)` |

None of them gets to own the loop, so none of them can bend it.

→ [The harness in detail](harness.md)

---

## 2. A directory is a field; a field may be a directory

**The problem.** A format either has a fixed slot table (and every new capability
costs a version bump) or it is free-form (and nothing can be checked).

**What PACT does instead.** One rule, applied totally:

```
agents/refund-desk/agent.yaml        agents/refund-desk/agent.yaml
  name: Refund Desk           ≡        name: Refund Desk
  instructions: Be precise.          agents/refund-desk/instructions.md
                                       Be precise.
```

Both produce the **identical document**. A beginner writes one file; an expert
writes a tree; nobody learns a slot table. Any future field gets its directory
form for free.

→ [The Expansion Rule](expansion-rule.md)

---

## 3. Correctness is measured, not declared

**The problem.** "Does this still work on a smaller model?" has no static
answer. Agent behaviour is probabilistic.

**What PACT does instead.** The author's own eval suite travels *inside* the
portable artifact and becomes the correctness oracle — for framework
portability, model substitution and self-improvement alike.

A model is only bound if it passes. When none does, PACT **refuses to bind and
then recommends the cheapest one that would pass**, rather than silently
degrading:

```
PORTABILITY: FAIL for llama3.2-1b-instruct  (agent Refund Desk, strategy authored)
  score 0% vs bar 70%
  llama3.2-1b-instruct thinks at the 'simple' rung and this needs at least 'steady'
```

→ [Evals and scoring](../guide/evals.md)

---

## What this buys you, concretely

**Byte-identical traces across seven targets.** One folder, loaded by the Rust
CLI, executed over all seven, produces the same trace, tool sequence and
model-call count.

!!! warning "That claim is bounded, and the bound is written down"
    It covers `instructions:`, `tools:`, `skills:`, `team:`, `loop:` and the
    `limits:` ceilings. It does **not** cover the governance keys the TypeScript
    port reports on `unenforced` — see [Adapters](../reference/adapters.md).
    A runtime that silently dropped a governance line would be worse than one
    that refused the document, so the smaller port says what it is smaller by.

**A human-in-the-loop kill test that survives everything.** Request approval
mid-parallel-tool-batch, serialise the paused state, drop every object, resume in
a fresh transport — each tool executes exactly once, the decision is honoured,
and the history is identical across frameworks.

---

**Next:** [What you write](what.md).
