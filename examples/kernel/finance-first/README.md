# Finance first

A support desk whose money questions go past the finance desk first, and whose
refunds are noted by an auditor afterwards. It is the example for topics,
events, reactions and agents that listen.

The same workspace is written as one file at
[`examples/language/finance-first/finance-first.pact`](../../language/finance-first/finance-first.pact).

## What is in it

| File | What it says |
|---|---|
| `topics/finance.yaml` | A subject called `finance`, noticed two ways: by tags, and by the agent saying so |
| `resources/back-office.yaml` | Where the billing and order systems are reached |
| `tools/billing.yaml` | Invoices and refunds, tagged `topics: [finance]`. The refund action moves money and needs a person |
| `tools/orders.yaml` | Orders and deliveries. Not tagged |
| `events/refund-issued.yaml` | A name for the moment `billing/issue-refund` has answered |
| `reactions/wrap-up.yaml` | After six steps, the agent is reminded to finish with what it has |
| `reactions/upset-customer.yaml` | A second model reads what the customer wrote; if they are upset, the agent is reminded to apologise |
| `agents/support` | The agent a customer talks to. It names the two reactions and neither of the other agents |
| `agents/finance-desk` | `listens-for: [{ topic: finance, how: asked-first }]` |
| `agents/auditor` | `listens-for: [{ event: refund-issued, how: told-after }]` |

## What a run looks like

A customer asks for a refund.

1. The support agent calls `billing`, which is tagged `finance`.
2. The finance desk listens for that topic and is asked first, so the call is
   **held**. The finance desk is run, and what it says comes back to the
   support agent in place of the tool's answer.
3. The support agent makes the same call again. This time it goes on to the
   approval the refund action needs, and a person is asked, once, about a
   call that will actually happen.
4. The person says yes. The refund goes out once.
5. `refund-issued` has happened, so the auditor is told. What it answers is
   kept with the run and not shown to the support agent.

That path is a test:
`adapters/python/tests/test_a_reaction_is_carried_out_where_it_was_written.py`,
which runs it from this folder and from the `.pact` file.

## Try it

```bash
pact check examples/kernel/finance-first
pact write examples/kernel/finance-first      # the same workspace as one file
```

To see a rule fire, change `remind:` to `stop:` in
`reactions/upset-customer.yaml` and check again. A judgement is a guess, and a
guess may not stop a run (`loader/a-guess-cannot-stop`).

More: [`site-docs/guide/events-and-reactions.md`](../../../site-docs/guide/events-and-reactions.md)
and [`site-docs/reference/reactions.md`](../../../site-docs/reference/reactions.md).
