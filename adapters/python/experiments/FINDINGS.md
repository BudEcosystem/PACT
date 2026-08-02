# Real-weights findings

Everything here was measured against locally-served models over a real HTTP API,
fully offline. The host was contended throughout (load 33-61 on 20 cores, from a
separate benchmark), so latencies are not model characterisations — but the
pass/fail outcomes are real.

## 1. T4's mechanism is demonstrated

`qwen2.5:7b-instruct`, one case, contract held fixed, only the strategy changed:

```
authored    FAIL  'Yes, a refund is appropriate in this case. Since the lamp arrived damaged…'
decomposed  PASS  'DECISION: approved\nREASON: Within 30-day damage policy.'
```

This is the mechanism the model-portability thesis rests on: **a failing binding
became a passing one without touching the contract.** Measured, not asserted.

## 2. There is a capability wall, and strategy does not cross it

`llama3.2:1b`, same case, same two strategies:

```
authored    FAIL  "I'll process your refund request. According to our store's return…"
decomposed  FAIL  'DECISION: declined  Reason: The customer did not provide sufficient notice…'
```

Both failed, and **the decomposed strategy failed worse**: it produced perfectly
formatted output with the wrong decision and an invented justification.

**Format compliance and judgement are independent axes.** Strategy changes fix
the first reliably. They do not fix the second. A strategy that makes a weak
model *look* compliant while it is still wrong is more dangerous than one that
fails visibly — which is an argument for keeping the eval oracle semantic, not
structural.

This matches what the literature predicted: procedural specification helps most
where the *procedure* is missing and least where the *capability* is.

## 3. A real defect in the grader, found only by real weights

The 7B model answered *"Yes, a refund is appropriate in this case"* — correct on
the substance — and a literal `"approved" in text` check marked it **wrong**.

Grading the wording instead of the decision makes the oracle measure the wrong
thing, and every claim built on it inherits the error. Fixed with a closed,
auditable equivalence table (`EQUIVALENT` in `evals.py`) and a regression test.
No scripted test would ever have caught this: scripted models emit exactly the
strings the test author imagined.

## 4. The UNDECIDED safeguard fires correctly

A 3-case run returned `UNDECIDED`, not `FAIL`, because three cases cannot support
a 70% bar. The system refused to produce a number that would have read as
evidence. That is the designed behaviour, confirmed against real output.

## What is still unmeasured

**Accuracy retention at scale.** One case is an existence proof of the mechanism,
not a measure of how much accuracy survives a downgrade. That needs the full
matrix — 6 cases x the model ladder x both strategies — on an uncontended host.
`real_model_portability.py` runs it unchanged; set `PACT_LADDER`.

Observed cost on a saturated box: p95 of **641 s** per case. On idle hardware
with a GPU this is minutes, not hours.

---

## 5. An admissible verdict on real weights

`qwen2.5:7b-instruct`, decomposed strategy, six cases — enough to clear PACT's
own `min_cases` floor, so this is a verdict the system will accept about itself
rather than an `UNDECIDED`:

```
clear-approve      PASS   'DECISION: approved  REASON: Item arrived damaged within 30 days'
outside-window     PASS   'DECLINED  Change-of-mind returns are allowed within 30…'
personalised       PASS   'DECISION: declined  …not allowed for personalised items'
sale-damaged       PASS   'DECISION: approved  Damaged item within 30-day window'
faulty-late        PASS   'DECLINED  EXCEEDED RETURN PERIOD'
change-of-mind-ok  FAIL   'DECLINED  …not allowed for full-price items'   ← invented rule

=== VERDICT === PASS  score=83%  bar=70%
```

Four verdict types, both directions, one policy exception, one boundary case.

### The single failure is the most useful line

On `change-of-mind-ok` the model declined a valid return, justifying it with
*"not allowed for full-price items"* — **a rule that appears nowhere in the
contract.** Same shape as the 1B failure ("did not provide sufficient notice").

**Forcing a rigid output format converts "I won't commit" into "I'll commit
confidently, sometimes wrongly."** Better on aggregate (0% → 83%), worse in the
tail. That is precisely why AD-58a exists: a money-moving decision cannot ride on
an 83% average, and consequential assertions are graded at 1.00 or not at all.

## 6. The frontier baseline — partial, and why

`qwen2.5:14b-instruct`, authored strategy (AC-3.1's baseline is the
*hand-authored* frontier strategy, not an optimised one):

```
clear-approve      PASS (1433 s)  'Yes, a refund is allowed in this case…'
```

**1 of 6, at 24 minutes per case** under a host load of 60. Six cases is 2.4
hours; the ladder is a day. Not completable here.

Two things this partial run still establishes:

1. The frontier model passes on the **authored** strategy where 7B failed —
   the expected shape, and the reason a strategy rescue is needed at all.
2. It passed with *"Yes, a refund is allowed"* — which scores correctly **only
   because of the grader fix in §3.** Without the equivalence table this would
   have been a false FAIL, and the retention ratio computed from it would have
   been wrong in the direction that flatters the small model. A bug found on
   7B would have silently corrupted the 14B measurement.

### What is still missing, precisely

The **retention ratio** — small-model rescued score ÷ frontier hand-authored
score, on the same suite. One number, blocked only on an uncontended host.
`verdict_6.py` computes it: run with `T4_MODEL` / `T4_STRATEGY` and divide.

### Faster-frontier attempt, also blocked

`gpt-oss:20b` is mixture-of-experts (~3.6 B active of 20 B), so it should be far
faster than dense 14 B despite being larger. Tried as a cheaper route to the
frontier baseline: **no output after 8 minutes on a single short call.** Under
this contention the active-parameter advantage does not survive.

Every route to the frontier baseline on this host has now been tried and failed:
dense 14 B (1433 s/case), MoE 20 B (>8 min, no completion), and the full matrix
on 7 B (timeouts). The blocker is the host, not the approach.

---

## 7. The retention ratio — MEASURED

Same six cases, same contract. The baseline is the **hand-authored** frontier
strategy, which is what AC-3.1 requires (not an optimised one).

```
qwen2.5:14b-instruct   authored (frontier baseline)   FAIL  67%  (4/6)
qwen2.5:7b-instruct    decomposed (rescued)           PASS  83%  (5/6)

retention = 83 / 67 = 124%
```

**The 7 B model, re-strategised, outperforms the 14 B model on the strategy its
author actually wrote.** On this suite the contract does not merely survive the
downgrade — it improves. 124 % sits just above the 98–114 % range the published
literature reports against hand-authored frontier baselines.

### Why the frontier model failed is the important part

Both 14 B failures are the *same defect* the 7 B authored run had: it reasons
correctly and never states a verdict.

```
faulty-late  FAIL  'Since the kettle was purchased 40 days ago, it is outside th…'
```

Correct reasoning, truncated before committing. **The bigger model is better at
reasoning and no better at answering.**

So strategy selection is not compensating for weak reasoning. It is fixing an
**output-discipline** failure that afflicts models at every size — which is a
different and more general claim than the thesis originally made. The 1 B result
gives the floor: below some capability threshold, forcing the format yields a
confident *wrong* answer rather than a correct one. Between those bounds the
mechanism does real work.

### Scope

Six cases, one task, two model tiers, temperature 0, one machine. An existence
proof with a number attached — not a benchmark. Widening it means more tasks and
more tiers, and `verdict_6.py` runs unchanged via `T4_MODEL` / `T4_STRATEGY`.
