# The harness owns the loop

## Why

The obvious way to make an agent portable is to map it onto each framework's
agent abstraction — `Agent` in Pydantic AI, `StateGraph` in LangGraph,
`AssistantAgent` in AutoGen. It is also the way that fails, and it fails in a
specific way: **that framework's control flow leaks in.**

LangGraph decides when to loop. AutoGen decides how a message is delivered.
Pydantic AI decides what a run is. Map onto those and two "identical" agents
diverge on step two, and you cannot tell whether the divergence came from your
agent or from the substrate.

## How

A framework provides exactly two things:

```python
class Transport(Protocol):
    """What a framework must provide. Deliberately one method."""
    name: str
    def lattice(self) -> dict[str, str]: ...
    async def model_call(self, system, history, tools) -> tuple[str, list[ToolCall]]: ...
```

That is the whole contract. **Anything larger would let a framework's own
control flow leak into the loop, which is exactly the divergence PACT exists to
remove** — that sentence is a comment in the source, not a slogan.

Everything else lives in PACT's harness, once, for every target: the step
sequence, halting, tool dispatch, retry, history construction, approval parking,
context tidying, spend metering.

## What that makes possible

**A loop you can author.** Because PACT owns the loop, its shape can be a
document rather than a constant:

```yaml title="loops/careful.yaml"
starts-at: gather

steps:
  gather:
    does: use-tools
    then: { used-a-tool: gather, answered: re-read }

  re-read:
    does: check-its-work
    may-use: [zendesk]     # deliberately not `payments`
    at-most: 2
    then: { used-a-tool: re-read, answered: reply }

  reply:
    does: answer
    then: { answered: done }
```

The comment in the real file explains the `may-use:` line better than a spec
could: *"the stage that exists to doubt a refund cannot issue one while it
doubts."*

!!! info "Compare"
    Vercel Eve's loop is `stopWhen: isStepCount(1)` — **one occurrence in the
    entire package**, at `harness/tool-loop.ts:907`. The continue-decision is not
    authorable there, and the file holding it is 2,547 lines.

**Ceilings that actually stop things.** `steps-at-most`, `runs-for-at-most`,
`tool-calls-at-most`, `tokens-at-most`, `cost-per-request-under` — each with the
author's own `when-it-runs-out:` action, and each reported distinctly so
"ran out of budget" is never confused with "finished".

**Exactly-once side effects.** `same-request-key:` means a refund asked for twice
with the same order number happens once. Eve's documented answer to the same
problem is *"make non-idempotent side effects like charges or emails idempotent,
or gate them with approval"* — the author's problem, with human approval as the
only lever.

**Work that survives being killed.** Park for approval mid-batch, serialise,
drop every object, resume in a fresh transport: each tool runs exactly once and
the decision is honoured.

## The cost of this design

PACT must implement everything itself, in every runtime it supports. That is why
the TypeScript port is smaller than the Python one — and why it
[says what it is smaller by](../reference/adapters.md) rather than pretending
parity.

---

**Next:** [Governance and refusal](governance.md).
