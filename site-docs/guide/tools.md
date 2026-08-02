# Adding a tool

## Why tools are files

A tool in PACT is a **declaration of what may be called**, not an
implementation. The implementation belongs to the host — the format's job is to
say what exists, what it takes, and who may use it.

That separation is what makes the same folder run on seven frameworks: the
declaration travels, the implementation is supplied where it runs.

## How

```yaml title="tools/payments.yaml"
description: Where refunds are actually issued.

connect: payments-server        # → resources/payments-server.yaml

actions:
  issue-refund:
    description: Send money back for one order.
    spends-money: yes
    takes:
      order-number: which order
      amount: how much, with the currency
```

Then let an agent use it:

```yaml title="agents/refund-desk/agent.yaml"
uses:
  - payments
```

`pact check` refuses `uses:` naming a tool with no file behind it.

## The one thing worth understanding

**The tool and the server it reaches have different names, deliberately.** The
real file explains why in its own comment:

> *"`uses:` names tools, never servers, so anything that wants to know which
> connections this agent can reach has to walk `uses:` → this line →
> `resources/`. While both were spelled `payments`, a reader that skipped the
> middle hop found the right answer by coincidence."*

That coincidence caused a real defect: renaming the tool alone took a human
consent gate on money off the scheduler's list, silently, while the harness went
on waiting for it. `pact check` now resolves `connect:` against `resources:`, so
the typo is refused where you type it.

## Scoping a tool to part of the loop

A stage can narrow what it may reach:

```yaml title="loops/careful.yaml"
  re-read:
    does: check-its-work
    may-use: [zendesk]      # deliberately not `payments`
```

> *"the stage that exists to doubt a refund cannot issue one while it doubts."*

## Offering a tool only when it makes sense

```yaml
available-when: this-agent-has-helpers
```

The model is not shown a hand-off tool when there is nobody to hand off to. If
the agent can never satisfy the condition, `pact check` warns — because a
capability that loads and is never offered is the hardest kind of nothing to
debug.

---

**Next:** [Gating an action on a person](approvals.md).
