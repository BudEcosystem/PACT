# Your first agent, in one file

This is [Your first agent](first-agent.md) again, written in the PACT
language: one file instead of a folder. Every command and every output below
is real. It takes about ten minutes, and nothing here needs a model or a
network.

By the end you will have an agent that can look up an order, cannot send a
refund without a person saying yes, stops after six steps, and is reminded to
wrap up when it is running long.

## Step 1: an agent

Make a file called `my-agent.pact`:

```text title="my-agent.pact"
workspace "my-first-agent"
  description: My first PACT agent.
  owner: me

agent helper
  description: Answers questions about our returns policy.

  instructions
    Answer the customer's question about returns. Be brief. Say when you are
    not sure rather than guessing.
```

Two **blocks**, each starting at the left margin. `workspace` holds what is
true of the whole thing; `agent helper` is one agent. The lines indented under
a block belong to it.

Two kinds of line are in use already. `description: …` is a **setting**: a
name, a colon, a value. `instructions` on a line of its own, with text
indented under it, is a **text block**: the field holds the text as you wrote
it.

```console
$ pact check my-agent.pact
OK — my-agent.pact loaded cleanly (8 settings).
```

## Step 2: give it a tool

Add a `tool` block, and one line on the agent saying it may use it:

```text title="my-agent.pact, added"
agent helper
  uses orders

tool orders
  description: Looks up an order.
  url: https://orders.example.com
  method: get
  actions:
    find:
      description: Finds one order by its number.
      takes:
        order-number: text
      reads-only: yes
    refund:
      description: Sends the money back.
      takes:
        order-number: text
        amount: money
      spends-money: yes
```

`uses orders` is the third kind of line, a **sentence**. It means exactly what
`uses: [orders]` means; it is only shorter. Everything under `actions:` is
plain settings, nested the way they would be in a YAML file, because the
language has no sentence for an action and does not need one.

Check it, and the format teaches you something:

```text
error: 'spends-money' says 'yes', and 'same-request-key' is not set — so nothing says which argument makes two calls "the same call".
  --> my-agent.pact:28:7
   |
28 |       spends-money: yes
   |       ^^^^^^^^^^^^
  fix: Add a line next to it: `same-request-key: ...`. — which argument makes two calls "the same call", so it runs once. […]
  rule: schema/missing-companion
```

(The fix line goes on to say when to write `the-call` instead; it is cut
short here.)

The check also prints a warning: the refund moves money and nothing yet asks
a person first. Step 3 answers it.

This is the same rule the folder form gets, pointing at the line in your
file. Add `same-request-key: order-number` under `spends-money: yes`, and the
same refund cannot be sent twice, even across a crash and a resume.

## Step 3: make a person approve it

A question a person can be asked, and a policy saying when:

```text title="my-agent.pact, added"
agent helper
  policy: approvals

question may-we-refund
  description: Asks a person before money moves.
  says: This refund is over the desk's limit. May we send it?
  answer:
    approved: yes or no
  asked-of: [the returns team]
  answer-within: 4h
  if-nobody-answers: stop-and-say-so

policy approvals
  before orders/refund: ask may-we-refund, because money leaves the company and cannot be taken back
```

The `before … : ask …, because …` line is a sentence a policy knows. It
writes one rule of the policy's `ask-a-person:` list.

Now ask what a runtime must be prepared to wait for, before running anything:

```console
$ pact waits my-agent.pact
```

It lists one wait: the question `may-we-refund`, asked of the returns team,
with a four-hour deadline, and `stop-and-say-so` if nobody answers.

## Step 4: limits, and a reminder

```text title="my-agent.pact, added"
agent helper
  spends under 0.05 USD a request
  at most 6 steps
  when it runs out: stop and say so

  when the agent has taken more than 4 steps
    remind it: You are nearly out of steps. Answer with what you have.
```

Three limit sentences, and a `when` block. The `when` block is a
[reaction](events-and-reactions.md): from the fifth step on, the reminder is
added to what the model is told.

```console
$ pact check my-agent.pact
OK — my-agent.pact loaded cleanly (62 settings).
```

## The whole file

```text title="my-agent.pact"
workspace "my-first-agent"
  description: My first PACT agent.
  owner: me

agent helper
  description: Answers questions about our returns policy.
  uses orders
  policy: approvals
  spends under 0.05 USD a request
  at most 6 steps
  when it runs out: stop and say so

  when the agent has taken more than 4 steps
    remind it: You are nearly out of steps. Answer with what you have.

  instructions
    Answer the customer's question about returns. Be brief. Say when you are
    not sure rather than guessing.

tool orders
  description: Looks up an order.
  url: https://orders.example.com
  method: get
  actions:
    find:
      description: Finds one order by its number.
      takes:
        order-number: text
      reads-only: yes
    refund:
      description: Sends the money back.
      takes:
        order-number: text
        amount: money
      spends-money: yes
      same-request-key: order-number

question may-we-refund
  description: Asks a person before money moves.
  says: This refund is over the desk's limit. May we send it?
  answer:
    approved: yes or no
  asked-of: [the returns team]
  answer-within: 4h
  if-nobody-answers: stop-and-say-so

policy approvals
  before orders/refund: ask may-we-refund, because money leaves the company and cannot be taken back
```

## Step 5: turn it into a folder, and back

When the workspace grows, or somebody on the team prefers one file for each
thing, write the folder:

```console
$ pact build my-agent.pact --to my-agent
Wrote 7 file(s) to my-agent. `pact check my-agent` reads the same workspace as `pact check my-agent.pact`.
```

```text
my-agent/
├── workspace.yaml
├── agents/helper/agent.yaml
├── agents/helper/instructions.md
├── policies/approvals.yaml
├── questions/may-we-refund.yaml
├── reactions/the-agent-has-taken-more-than-4-steps.yaml
└── tools/orders.yaml
```

The `when` block became a file under `reactions/`, named from its sentence,
and the agent's file lists it. The sentence in the policy became the rule it
stands for:

```yaml title="my-agent/policies/approvals.yaml"
ask-a-person:
  - when:
      - { tool: orders/refund }
    because: money leaves the company and cannot be taken back
    question: may-we-refund
```

And back again:

```console
$ pact write my-agent
```

prints the same workspace as one file, in sentences wherever a sentence says
it. Comments are the one thing that does not make the trip.

## When you get a line wrong

The checker names the line and what to write instead:

```text
error: This line is not a setting, and not a sentence this kind of block knows.
  --> my-agent.pact:7:3
  |
7 |   use orders
  |   ^^^^^^^^^^
  fix: Did you mean a line starting `uses`?
  rule: lang/not-a-line
```

## Where to go next

- [One file instead of a folder](the-pact-language.md): the short guide to
  the language.
- [The PACT language](../reference/language.md): every block, sentence and
  rule.
- [When something happens](events-and-reactions.md): what else a `when` block
  can wait for and do.
- `examples/language/` in the repository: three workspaces written this way.
