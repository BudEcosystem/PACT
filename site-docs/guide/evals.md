# Evals and scoring

## Why evals are part of the agent, not part of your CI

Agent behaviour is probabilistic. There is no type system that can tell you
whether an instruction change, a model swap or a smaller model still produces the
right answer.

So **the author's own eval suite is the correctness oracle**, and it travels
*inside* the portable artifact. An agent whose definition of "working" lives in
somebody's CI is not portable — you can move the agent and lose the only thing
that could tell you whether the move worked.

The same suite answers three different questions:

- did this change break it?
- does it still work on a cheaper model?
- should the agent be allowed to keep a change it proposed to itself?

## How

```yaml title="evals/suite.yaml"
description: Checks the Refund Desk makes the right call and explains itself.

# These are the situations we thought of and wrote down. That is what this
# score describes — not everything a customer might send us.
population: authored-enumeration

must-pass: 70%

rules:
  - must-say-one-of: [approved, declined]
    because: the customer needs a clear answer
  - must-not-contain: ["refund by", "arrive on"]
    because: we must never promise a date we do not control
  - must-call-before:
      { call: payments/issue-refund, first: payments/look-up-order }
    because: issuing money without looking up the order is the expensive mistake
```

!!! tip "`population:` is a claim about what the score means"
    `authored-enumeration` says: *these are the cases we thought of*. It stops a
    70% from being read as "70% of customer requests" when it means "70% of the
    six situations we wrote down". A number without its population is not a
    measurement.

A case:

```yaml title="evals/cases/01-clear-approve.yaml"
when: |
  A customer bought a lamp 6 days ago for 40 USD. It arrived with a cracked
  base. They want their money back.
expect:
  decision: approved
  amount: 40 USD
because: Within 30 days and the item arrived damaged, so policy allows a refund.
must-also:
  - must-call-before:
      { call: payments/issue-refund, first: payments/look-up-order }
```

## Judged rules

Some things cannot be checked by matching text. A `judged:` rule is graded by a
model — named in the file, resolved against the catalogue, and **refused if it
would leave the box** when `allow-egress:` forbids it.

Adding one line changes a measured score:

```
without `judged:`  →  6/6 = 100% PASS
with    `judged:`  →  4/6 =  67% FAIL   (the author's bar is 70%)
```

Same six cases, same six answers, same deterministic rules. The only difference
is one line the author wrote.

!!! note "A grader that answers neither PASS nor FAIL has decided nothing"
    It is reported, never scored either way. An undecided judge silently
    becoming a pass inflates every score downstream; becoming a fail deflates
    them. The third state is the honest one.

## Running it

Not a `pact` verb, because it runs models:

```bash
./scripts/pact-eval <PATH>
```

Or, if you would rather name the interpreter yourself:

```bash
cd adapters/python && uv run python -m pact_adapters.evals <PATH>
```

`pact check` tells you the suite is **well-formed**. This tells you it
**passes**.

## What the score is used for

**Model portability.** A model is bound only if it passes:

```
PORTABILITY: PASS for claude-haiku-4-5   score 100% vs bar 70%
PORTABILITY: FAIL for llama3.2-1b-instruct   score 0% vs bar 70%
  llama3.2-1b-instruct thinks at the 'simple' rung and this needs at least 'steady'
```

When none passes, PACT **refuses to bind and then recommends** the cheapest one
that would — rather than degrading silently.

**The learning gate.** A change the agent proposes to itself is held against the
same suite, on a frozen held-out split. `learning.yaml` in the worked example
says `enabled: propose-only`, `auto-apply: no`, and its comment reads *"Nothing
changes by itself."* Two tests hold that, and both were written after mutation
testing showed the checks could be deleted with the suite still green.
