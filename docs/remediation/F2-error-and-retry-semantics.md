# F2 — A tool that failed. **Not refused: this one should be built.**

Six of the seven documents in this set are refusals. This is the one that
examined on its merits and came out the other way. **The decision: add one
outcome and one watch moment. Do not add a `retries:` field.**

---

## What cannot be written

*"Retry the payments API three times, then escalate."*

A stage's endings are closed —
`adapters/python/src/pact_adapters/loops.py`:

```python
OUTCOMES = ("used-a-tool", "answered", "too-many-times")
```

A tool that timed out and a tool that answered end the stage identically:
`harness.py:2178` decides the outcome from the stage's own kind and never looks
at what came back.

```python
outcome = "answered" if phase.does is Does.ANSWER else "used-a-tool"
```

The failure is not lost — `_call_tool` catches it and returns
`error: 'payments' could not run: <e>` as the tool's result, deliberately, so
the model can read it and decide. That is the right default and it is the whole
of the mechanism: **the decision belongs to the model, and the author cannot
take it back.**

## The asymmetry that makes this a defect rather than a gap

A **teammate** that fails is a first-class event with an authored policy. A
**tool** that fails is neither. Measured against the closed lists in
`spec/schema.yaml`:

| | teammate | tool |
|---|---|---|
| a moment a watch can be bound to | `step.delegate.failed`, `turn.delegate.failed` | **none** |
| an authored policy for it | `teamwork.if-someone-fails: carry-on \| stop` | **none** |
| visible in a loop | — | **no** |

```bash
$ grep -oE "(step|turn)\.(tool|delegate)\.[a-z]+" spec/schema.yaml | sort -u | grep failed
step.delegate.failed
turn.delegate.failed
```

Every `tool` moment the same command prints is `before`, `started`, `completed`,
`cancelled`. There is no failure among them.

So a run whose payment tool failed four times writes down three `completed`
events that say nothing about it, and an operator reading the watch log cannot
tell that run from a healthy one. That is not an expressiveness question. It is
evidence missing from the record.

## What it would take

**One outcome value and one watch moment. Not a retry field.**

1. `OUTCOMES` gains `tool-failed`, and `harness.run` sets it when `_call_tool`
   caught something. **From the exception, not from the string.** `_call_tool`
   already knows structurally whether the call raised; the `error: …` text is a
   *rendering* for the model. Sniffing that prefix would make a tool that
   legitimately returns the word `error` route as a failure — the same
   string-test-on-content mistake `F1` refuses.
2. `step.tool.failed` joins the watch vocabulary, beside the two the delegate
   already has.
3. Both ports and `spec/loops/*.yaml`'s drift check move together, as
   `test_loops.py::test_the_two_copies_of_a_shipped_shape_have_not_drifted`
   requires.

**"Three times, then escalate" then needs nothing more**, because the bounded
part already exists — `at-most:` on a stage and `too-many-times:` routing off
it is the retry shape, written today for `react` and `reflexion`:

```yaml
charge:
  does: use-tools
  at-most: 3
  then:
    tool-failed: charge          # go round again
    too-many-times: escalate     # the fourth entry finds it spent
    answered: done
```

That composition is the design and it is **not built or measured here.** What is
measured is the two facts it rests on: `_stage_to_run` routes past a spent stage
before entering it, and a stage with no `too-many-times:` line hands on to its
`answered:` target.

## Why no `retries:` field

Because `docs/95-FIX-PLAN.md` §1.18 already built the neighbouring field — `A6
tries:` — and measured four independent kills, two of which apply here word for
word: a stage that fans out **parks with the work lost and re-charges it on
resume** (`visits: {}`, `used: 0.0` after three paid calls), and its runs are
**byte-identical** to `at-most:` except for a `Step.index` it breaks. A retry
count is a second spelling of a bound this format already has, and R57 —
two ways to say one thing — is the rule that decides it.

## What it collides with

**Almost nothing, and that is the finding.** It adds one value to a closed list
and one moment to another. Measured against those lists as they stand:
`OUTCOMES` at `adapters/python/src/pact_adapters/loops.py:61` has **three**
members, and `spec/schema.yaml`'s `outcome:` group says so in its own comment —
*"The three ways a stage can end"*; the watch-moment list under `reaches:` has
**thirty**, and its comment says that too — *"§7.13's table of thirty … A run
has thirty moments"*. It needs no predicate, no new noun, and no second place to write a
condition, so `loops.py`'s standing objection — *"the fourth place in this
project where an author can write a condition"* — does not reach it: the
condition is *what happened*, which is what the other three outcomes already
are.

The one real cost is `docs/95-FIX-PLAN.md` §1.19's growth rule: **every value in
every closed choice must be read by something that is not a test and not
prose**, because an unread value is not merely dead, it is *recommended* to
every author who makes a nearby typo. Two values, two readers, and the rule is
the acceptance test.

## The price of NOT building it — which is why this one is owed

**Today an author cannot promise that a failure was handled, and cannot prove it
was not.** Concretely:

1. **Retry is the model's decision and nobody's contract.** The transcript says
   `error: …` and the model may retry, may apologise, may invent a refund
   reference. Two models will do different things with the same document, which
   is the portability claim this project is built on, broken on the most
   ordinary failure a tool has.
2. **The evidence is missing.** No watch can be bound to a tool failure, so the
   `.pact/` record of a run that failed four times and one that succeeded twice
   are the same shape. An operator cannot count tool failures across runs at
   all.
3. **The workaround costs a whole agent.** The only expressible escalation is
   `team:` — give the escalation its own agent and let the parent choose — which
   buys a second history, a second budget slice and a second latency budget to
   express *"try again"*.

**Sequenced after the safety work, not before it.** `docs/93-GAPS.md`'s own
sequencing principle is that production defects gate expressive ones, and this
is an expressive addition. It should ship, and it should ship last of the things
that are shipping.
