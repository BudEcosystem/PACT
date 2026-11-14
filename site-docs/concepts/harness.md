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

**An answer is held to what the agent says it gives.** An agent that writes
`answers-with:` has promised a shape to whoever calls it, and may write rules
of its own for an answer under `checked-by:`. The harness holds a reply to both
before it is the answer.

```yaml
answers-with:
  decision: one of approved, declined
  amount: money
  note: text, optional
checked-by:
  - must-contain: [refund]
    because: say what happens to the money
checks-at-most: 2
```

| The reply | What happens |
|---|---|
| has every field, each as its line asks | it is the answer; the run's `answer` is those fields |
| leaves a field out, or writes a value its line refuses (`decision: maybe`) | the model is asked again and told what was wrong, in the author's own words for each field |
| has a field the agent did not declare | nothing: it is not a reason to ask again, and it is not handed back |
| fits, and breaks a `checked-by:` rule | the model is asked again and told which rule and why |
| still is not the answer after `checks-at-most:` tries (2 when unwritten) | the run ends `checks-failed`, says how many times it was asked and what was wrong with the last reply, and hands back no answer |

The shape and the rules spend from one count. An empty reply that arrived is
one of the tries; a call to the model that failed is not. A field written
`stream of text` is the reply itself as it arrives, so it is not looked for on
a line of its own. An agent that writes neither line is held to nothing.

The closing answer of a run that reached a ceiling is held the same way, from
the same count. One that never fits is not handed back: the run keeps the
ceiling's own word, because it did run out, and says it was left with no
answer.

What the model is told when it is asked again is added to its instructions for
that one request, never put in the customer's voice:

```text
Your last answer did not fit what your answer must contain:
- `decision` is missing. It should be: one of approved, declined.
- `amount` is missing. It should be: money.
Answer again, with every field as it is asked for.
```

Checked live, by replacing a real model's first reply with one that names no
field: told this, gpt-4o-mini and gpt-5-nano each answered again with every
field.

**Ceilings that actually stop things.** `steps-at-most`, `runs-for-at-most`,
`tool-calls-at-most`, `tokens-at-most`, `cost-per-request-under` — each with the
author's own `when-it-runs-out:` action, and each reported distinctly so
"ran out of budget" is never confused with "finished".

| `when-it-runs-out:` | What the run does at the ceiling | What it hands back |
|---|---|---|
| `stop-and-say-so` | makes no further request | a sentence naming the setting and both figures |
| `answer-with-what-it-has` | makes one closing request with no tools offered, which tells the model a limit was reached and which of its calls were not made | the model's answer, reported as having reached the ceiling |
| `ask-a-person` | waits, and asks whether to keep going | after a yes, the same budget again from where it is, and the model is told which of its calls were not made; after a no, a sentence naming the ceiling and saying a person declined |

A run that asked and was told no ends as `out-of-budget`, and says so:
*"Stopped before finishing: this run reached the limit you set with
`tool-calls-at-most` (2 of 2 tool calls). A person was asked and said not to
keep going."* If the wait ran out instead, it says nobody answered in time.

The closing request says why the tools have gone. Taking them away is not a
message: a live model asked for five lookups, allowed two, and sent one more
request with no word of explanation wrote a third tool result itself, for a
lookup that was never made, and that was the run's answer. Told *"This run has
reached its limit … These calls you asked for were NOT made … Answer now, from
the results you already have"*, the same model answered with the two it had and
named the three it did not get to.

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
