# PACT Core: actors, functions, and a workspace that changes while it runs

PACT Core is a way of writing a workspace as a small program. It is read by the
same `pact check` and becomes the same document as the keywords you already
know, so every rule holds for it. This page is what exists today; the plan for
the rest is `docs/100-PACT-CORE-A-WRITABLE-KERNEL-LANGUAGE.md`.

## An actor, and what it can do

An **actor** is one name with several capabilities. What is written beneath
each `can` says who carries it out.

```text
actor desk
  description: Decides refund requests.
  uses orders
  at most 6 steps
  when it runs out: stop and say so

  can judge(order: text, facts: text) gives decision: one of approved, declined, reason: text
    by model
    instructions: Decide whether this order is refunded, from the facts given.

  can decide-one(order: text) gives decision: text, reason: text
    seen = orders/look(order: input.order)
    ruled = desk.judge(order: input.order, facts: seen.facts)
    answer with decision: ruled.decision, reason: ruled.reason
```

- `by model` means a model decides. It becomes an agent, `desk-judge`, with
  everything the actor shares: what it uses, its limits.
- Statements mean the steps are written out and are the same every time. They
  become a workflow, `desk-decide-one`.
- A capability is called as `desk.judge(…)`.

Nothing here is a new kind of thing. `pact show` prints the agents and
workflows an actor is, and `pact check` holds them to the rules it always had.

## A function

What a flow takes and gives is written on the line that names it, and it is
called with what it is given in brackets.

```text
flow decide-all(orders: list of text) gives summary: text, verdicts: list of verdict
  description: Decide every order in a list, five at a time, and sum up.
  each = for each item in input.orders
    limits:
      items-at-most: 50
      at-once-at-most: 5
      when-it-runs-out: stop-and-say-so
    one = desk.decide-one(order: item)
  told = desk.summarise(verdicts: each.items)
  answer with summary: told.summary, verdicts: each.items
```

`flow` is another word for `workflow`. `x = name(k: v)` is another way of
writing `x = call name with k: v`. Inside a flow, what it was given is read as
`input.<name>`.

Two things a statement cannot do, on purpose: state a value of its own
(`decision: "approved"` is refused), and work one out (`a + b`). A value comes
from something the flow was given or something it called. To judge or compute,
call something that does.

## Two ways to run a workspace

=== "Interpreted: it can change while it runs"

    ```python
    from pact_adapters.session import Session

    session = Session.open("examples/core/refund-desk", journal="desk.journal")
    session.propose(text)            # new definitions
    session.change(text)             # the same names, replaced
    session.withdraw("agent", "cashier")
    ```

    Every proposal goes through one door, and the judge at it is `pact check`.
    What is refused changes nothing and comes back with the checker's own
    sentence. A run that is already going finishes under the version it began
    with; the next run is the new one. Every version has a fingerprint
    (`session.version`), and a session opened again on its journal is exactly
    where it was.

=== "Pre-compiled: checked once and sealed"

    ```python
    from pact_adapters.session import Plan, compile_plan

    compile_plan("examples/core/refund-desk").save("desk.plan.json")
    plan = Plan.load("desk.plan.json")   # refuses a file that was edited
    ```

    A plan runs with no `pact` binary beside it and takes no change: every
    proposal is refused and says to open a session instead. Use it where what
    runs must be exactly what was reviewed.

The same document runs on the same runtime either way.

## A model that acts by writing a cell

A **cell** is a few statements a model writes in the middle of a run. One cell
can loop and fan out, which one tool call cannot.

```text
each = for each item in input.orders
  limits:
    items-at-most: 20000
    when-it-runs-out: stop-and-say-so
  page = orders/look(order: item)
answer with summary: input.note
```

```python
from pact_adapters.cells import act_by_a_cell, callers_of

out = await act_by_a_cell(session, "desk-summarise", transport.model_call,
                          "Look up every order.", {"orders": orders, "note": note}, callers)
```

What holds for a cell:

- **It is checked before it runs**, by the same checker. A refused cell is not
  carried out at all, and the model is told why and writes another.
- **It may call only what its writer was given**: the tools that agent `uses`
  and its teammates. A helper it defines may use no tool its writer does not,
  and take no more steps.
- **It may define agents, flows and shapes, and nothing of the workspace's
  own**: no tool, no policy, no egress line.
- **It never replaces something that is there**, and what it defines is gone
  when the call ends. The workspace is then the one it was, to the fingerprint.
- **Values stay whole.** The model is shown a few words of each
  (`list(20000 items; first: …; last: …)`) and the cell works on all of it.

Run on `gpt-4o-mini`, five times each: a cell that looks up twelve orders is
admitted at the first try; after a refusal the model writes one that is
admitted; 20,000 orders are worked on from a preview; and a note telling the
agent to define a tool and make a payment results in neither.

## What is not there yet

Words made from other words (`define`), a capability carried out by a program,
a parameter read by its bare name, and the model's cells as a loop shape inside
an ordinary agent run. The plan says in what order they come.
