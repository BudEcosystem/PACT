# Gating an action on a person

## Why this is the important one

Most of what an agent does is reversible. A refund is not. The question
"when must a human decide?" is the one an organisation actually has to answer,
and it should be answerable **without reading code**.

!!! danger "The default that matters"
    Vercel Eve's documentation states: *"By default, omitted `approval` behaves
    like `never()`, so tool calls may execute without human approval."* A tool is
    unguarded unless the author remembers to guard it — and the thing an author
    forgets is by definition the thing they did not think about.

    PACT has no spelling that means "ask nobody", and a policy says which agents
    it covers.

## How

```yaml title="policies/approvals.yaml"
applies-to: every-agent

ask-a-person:
  - when:
      - { tool: payments/issue-refund, arg: amount, more-than: 200 USD }
    because: a refund over 200 USD is a management decision
    question: is-this-ok

  - when:
      - { tool: payments/issue-refund, arg: amount, more-than: 500 USD }
    because: above 500 USD a person sets the figure, rather than approving one
             the model chose
    question: how-much-to-refund
```

Two rules over the same tool, and **the narrower one wins**: 210 USD asks
`is-this-ok`; 600 USD asks `how-much-to-refund`. A person is not merely
approving — above 500 they set the number.

## `applies-to: every-agent` is load-bearing

For a round the example's policy covered one of three agents. `fraud-checker`
read Zendesk tickets and could reach the reply action the policy gated —
ungated, because the policy was opt-in per agent. Its own comment now says:

> *"The agent that forgets to name the money rules is the agent that spends
> without asking."*

## What a person actually sees

```yaml title="questions/is-this-ok.yaml"
asks: Approve this refund?
answer:
  approved: yes or no       # ← the word that makes a no mean no
  because: some text
shows: [spent-so-far, which-limit]
answer-within: 30m
if-nobody-answers: escalate
```

`shows:` controls what reaches the approver. `answer-within:` is a real deadline
— `pact waits` prints it so a runtime can set a timer, because a wait nobody
schedules a timer for waits exactly as long as one with no deadline: forever.

## What survives

- **A decline is a decision, not silence.** It ends the run rather than
  re-asking.
- **Partial approval runs the approved subset.** Approve two of three and you get
  two — not none.
- **The record survives a crash.** Serialise the paused state, drop every object,
  resume in a fresh transport: each tool runs exactly once.
- **The record survives a summary.** A conversation shortened past the approval
  does not lose it — see `survives-shortening:`. A check that passes because its
  evidence was summarised away is worse than one that fails.
