# gap-r1-4 — Per-split minimum sizes: the derivation §6.2 promised and did not do

**Round 1, gap 4.** Target text: `docs/20-ARCHITECTURE-DRAFT.md:2860` —
*"Minimum sizes per split come from the same table as §6.9's minimum-case rule."*

**Status: closed, with one residual that is a genuine impossibility rather than an
omission (§7).**

---

## 0. What the gap actually is

§6.2 declares five splits (`train | validation | held-out | calibration | quarantine`)
and asserts their floors come from §6.9-A's table (`20-ARCHITECTURE-DRAFT.md:3246-3255`).
That assertion is false as written, for a reason that is structural and not clerical:

**§6.9-A's table answers exactly one question** — *what is the smallest n at which a
perfect score certifies a true pass rate above `must-pass` at one-sided 95%?* That is the
decision the **held-out** split is read for. It is not the decision `validation`,
`calibration` or `train` are read for, so the table cannot be transplanted onto them:

| split | what it is read for (per §6.2's own table and §8.8) | is that a one-sample proportion test against a fixed threshold? |
|---|---|---|
| `held-out` | OBL-3 non-regression; RES-6/RES-8 verification | **yes** — §6.9-A applies verbatim |
| `validation` | OBL-2 *strict improvement*; the optimiser's accept test | **no** — a *paired two-sample* comparison |
| `calibration` | judge agreement `a`, which §6.9 rule 1 uses as a ceiling on any judged threshold | **yes, but per class, and against a different θ** |
| `train` | the proposer's search signal | **no test at all** — nothing is certified from `train` |

And the second half of the gap: the draft's only quantitative support for split *ratios*
is DSPy's 20/80 line, cited at `20-ARCHITECTURE-DRAFT.md:2851-2853`. That citation is
accurate but is (a) a ratio, not a floor, (b) about a **two-way** split PACT does not
have, and (c) **contradicted by PACT's own reference optimiser** (§4 below).

The unifying principle that closes the gap, and that I recommend become the normative
sentence replacing line 2860:

> **A split's floor is the smallest n at which the decision that split is read for can
> come out in that split's favour at one-sided 95%.** One method, four decisions, three
> different exact tests — and for `train`, no test, therefore no statistical floor and an
> honestly-labelled empirical one.

---

## 1. Reproducing §6.9-A (so the extension is on the same footing)

Method as stated at `20-ARCHITECTURE-DRAFT.md:3231-3244`: Clopper–Pearson one-sided 95%
lower bound on a **perfect** score, Bonferroni-adjusted by the candidate count k. For a
perfect score the bound has a closed form, `LCB = α^(1/n)`, so the floor is
`n = ⌈ln α / ln θ⌉` with `α = 0.05/k`.

Recomputed (`scipy 1.17.1`, `beta.ppf`; script retained at
`scratchpad/derive.py`, `scratchpad/derive2.py`):

| `must-pass` θ | k=1 | k=14 | k=20 | k=50 |
|---|---|---|---|---|
| 70% | **9** | **16** | 17 | 20 |
| 80% | 14 | 26 | 27 | 31 |
| 90% | 29 | 54 | 57 | 66 |
| 95% | 59 | 110 | 117 | 135 |

**Verified:** every cell reproduces the draft's table except one. **The draft's `70% / k=14`
cell reads 17; the correct value is 16.** `ln(0.05/14)/ln(0.70) = 5.6348/0.35667 = 15.798`,
and at n=16, `(0.05/14)^(1/16) = 0.7031 > 0.70`. The other three k=14 cells (25.25→26,
53.48→54, 109.85→110) are right. This is a one-cell rounding erratum, not a method
disagreement; it is worth fixing because the diagnostic prints "add N cases" and N would
be off by one at the tier a support lead actually lands in.

*Inference (marked):* the draft's k=20 and k=50 columns are not printed in §6.9-A (they
appear only in the prose at `:3238-3239` as "57 at 20 candidates, 66 at 50", which my
recomputation confirms exactly for θ=0.90).

---

## 2. `held-out` — §6.9-A applies unchanged, and that is the *only* split it applies to

No new derivation needed. Two consequences worth recording:

- The floor is a floor on **gating cases**, i.e. cases in `held-out` that carry a
  `severity: gate` assertion — the denominator §6.3's counting rule defines
  (`20-ARCHITECTURE-DRAFT.md:2815-2818`). A held-out case whose only assertion is `soft`
  does not count toward it.
- **The in-repo validated experiment sits below this floor.** Bench 3 used
  `8 train / 8 val / 8 test` (`/home/bud/ditto/gaia-ai-runtime/research/RESULTS.md:70`)
  and reported `0% → 81.2%` held-out. Under §6.9-A, 8 held-out cases certify **nothing**:
  even a perfect 8/8 gives `LCB = 0.6877`, and the observed score was 0.812, whose
  one-sided 95% LCB on n=8 is far lower still. This does not invalidate bench 3 as a
  demonstration that the loop runs; it does mean **the number PACT quotes most often —
  81.2% — would be reported `UNDECIDED` by PACT's own verdict function.** That is the
  system working correctly, and the architecture should say so rather than let the two
  documents quietly disagree.

---

## 3. `calibration` — the same table, at a different θ, **twice**

### 3.1 What the split must decide

§6.9 rule 1 (`:3211-3216`): a judge-gated threshold above the judge's measured agreement
`a` is unsatisfiable; `a` comes from the `calibration` split. §8.5's gate table
(`:3033`) makes it concrete: *"A judge may gate anything only after scoring ≥ 70%
agreement on the `calibration` split."*

So the decision is: **is the judge's true agreement above the judge-gate θ_j?** Same shape
as held-out, so the same Clopper–Pearson machinery — with two corrections the draft does
not currently make.

### 3.2 Correction A — agreement is not one number; it is two

Arize Phoenix's evaluator-validation guidance is the most explicit source in the corpus
and it never reports a single agreement figure:

- `research/repos/eval/phoenix/.agents/skills/phoenix-evals/references/validation.md:12`
  — *"| TPR/TNR | Both >70% |"*, and `:19-20` define them as `TP/(TP+FN)` and `TN/(TN+FP)`.
- `.../validation-evaluators-typescript.md:4` — *"Target: **>80% TPR and >80% TNR**"*,
  with `:94-95` naming the distinct failure each side protects against.
- `.../fundamentals-anti-patterns.md:9` — *"Ignoring humans | Uncalibrated LLM judges |
  Validate >80% TPR/TNR"*.
- `.../observe-sampling-python.md:57` and `.../observe-sampling-typescript.md:145` —
  sample-size table, **"Judge calibration | 100+ per class"** (emphasis on *per class*).

The reason is arithmetic, not stylistic: **scalar agreement is confounded with class
prevalence.** A judge that returns `pass` unconditionally has agreement equal to the base
rate. On a calibration split that is 75% passes it scores 0.75 — above PACT's 0.70 gate —
while having TPR 1.0 and TNR 0.0, i.e. it cannot detect the failures the gate exists to
catch. **PACT's current single `agreement:` field admits exactly this judge.** This is a
negative finding about the draft, and it is load-bearing: the judge gate is what stands
between a judged `must-pass` and a bound verdict.

**Therefore:** the floor is computed **per class**, and the split must be **class-balanced
enough** that both classes clear it. Total floor = 2 × the per-class floor.

### 3.3 Correction B — the gate must read the interval, not the point estimate

§6.9 rule 2 (`:3217-3218`) makes every score an interval; §4.6's lockfile already records
`agreement-n` and `agreement-ci` (`:3033`, `:1849`). But the gate at `:3033` compares the
**point estimate** to 0.70. Applying the document's own doctrine to its own field, the
gate must compare the **one-sided 95% lower bound**.

The draft's worked example then fails its own gate:
`agreement: 0.74 [0.61, 0.85] on n = 40 calibration cases` (`20-ARCHITECTURE-DRAFT.md:1700`).
Lower bound **0.61 < 0.70** — recomputed independently: 30/40 = 0.75 observed gives
Clopper–Pearson one-sided 95% LCB **0.6129**. So this judge may not gate, and §2.8's own
finding list already flags `must-pass: 90%` "against a 0.74 judge" as a defect
(`:2200`-ish, the eleven-failure list) — the interval reading makes that defect strictly
worse than recorded, because the judge cannot gate at *any* threshold.

### 3.4 The calibration floor table (per class, one-sided 95%, Clopper–Pearson)

Smallest n at which an *observed* per-class agreement `â` certifies true agreement
**> θ_j**. k is the number of judge configurations tried before one was kept (judge-prompt
search is a search, and inherits rule 3's multiplicity).

**θ_j = 0.70 (PACT's current gate):**

| observed `â` | min n per class, k=1 | k=3 |
|---|---|---|
| 1.00 | 9 | 12 |
| 0.95 | 14 | 18 |
| 0.90 | 19 | 28 |
| 0.85 | 33 | 51 |
| 0.80 | 69 | 104 |
| 0.75 | 255 | 407 |

**θ_j = 0.80 (Phoenix's target, k=1):** â=1.00 → 14; 0.95 → 22; 0.90 → 57; 0.85 → 198.

Three things fall out of this table, all of them design-relevant:

1. **The `â = 1.00` row is literally §6.9-A's table.** `min n = 9` at θ=0.70 and `14` at
   θ=0.80 are the 70% and 80% rows of §6.9-A. So §6.2's claim *"the same table as §6.9"*
   is **true for `calibration`, in its best case, doubled for the two classes** — a
   structural floor of **18** at the 0.70 gate. That is the schema-enforceable number,
   because the validator cannot know `â` before the labels exist.
2. **The realistic floor is much larger, and it is a hyperbola in `â − θ_j`.** A judge
   observed at 0.85 needs 33 labels per class (66 total); at 0.80, 69 per class (138); at
   0.75, 255 per class (510) — infeasible for D13's support lead by two orders of
   magnitude. Phoenix's "100+ per class" is the same conclusion reached empirically.
3. **This table is the strongest available argument for AC-4.5's deterministic-first
   ordering** — it converts "prefer deterministic checks" from a style preference into a
   budget: a judged gate costs 66–510 human labels *before it may gate anything*, a
   `must-contain` costs zero. That is the sentence to put in front of a non-technical
   author, and it is derived, not asserted.

Consequently the gate is **two-stage**, which is also the only form that can be
implemented at validate time:
- **VALIDATE time (structural):** `calibration ≥ 2 × §6.9-A[θ_j]`, both classes non-empty
  and each ≥ `§6.9-A[θ_j]`.
- **CALIBRATE time (`pact judge calibrate`):** compute per-class CP LCB; if either
  ≤ θ_j, refuse the gate and print the three fixes plus **the exact number of additional
  labels needed at the observed rate** (i.e. read this table forward).

---

## 4. `validation` — a paired comparison, so a sign test, not a proportion bound

### 4.1 What the split must decide

OBL-2 (`20-ARCHITECTURE-DRAFT.md:4082`): *"strict improvement on the `validation` split
frozen before the cycle"*. §8.8 hands `splits {train, validation}` to the optimiser
(`:4394`). Two *different* decisions ride on this one split, and both need floors:

- **(a) the accept test** — is candidate C truly better than incumbent B?
- **(b) the selector** — argmax over k candidates, which is what GEPA/MIPROv2 actually do.

### 4.2 (a) The accept test — exact one-sided sign test

The scores are paired (same cases, two strategies), so the correct exact test is the sign
test on **discordant pairs** — cases where exactly one of B, C is correct. With d
discordant pairs all favouring C, the one-sided exact p-value is `0.5^d`:

| d | p |
|---|---|
| 3 | 0.1250 |
| 4 | 0.0625 |
| **5** | **0.0313 ← first d with p ≤ 0.05** |
| 9 | 0.0020 |

**A validation split cannot certify *any* strict improvement with fewer than 5 discordant
pairs, no matter how large the observed delta.** This is an absolute, distribution-free
floor and it is the direct analogue of §6.9-A's "n=29 for 90%". Under Bonferroni over k
candidates (`α = 0.05/k`) the requirement is `d ≥ ⌈ln(0.05/k)/ln 0.5⌉`: **k=1 → 5,
k=5 → 7, k=14 → 9, k=20 → 9**.

Since d ≤ n, the **hard** schema floor is `validation ≥ d_req` (5 at k=1, 9 at k=14).

### 4.3 (a) continued — the *useful* floor, given a flip rate

d is a random variable: `D ~ Bin(n, δ)` where δ is the discordance (flip) rate an accepted
edit produces. Smallest n with `P(D ≥ d_req) ≥ 0.80`:

| δ (flip rate) | k=1 | k=5 | k=14 | k=20 |
|---|---|---|---|---|
| 0.10 | 66 | 90 | 113 | 113 |
| 0.15 | 44 | 59 | 75 | 75 |
| 0.20 | 33 | 44 | 56 | 56 |
| **0.25** | **26** | 35 | **44** | 44 |
| 0.33 | 19 | 26 | 33 | 33 |
| 0.50 | 12 | 17 | 21 | 21 |

δ is not knowable at validate time, so under **F-1** ("every default is a value in a
profile") it must be a profile field with a builtin, not a hardcoded constant. δ = 0.25 is
the defensible builtin: it says *"an edit worth auto-applying flips a quarter of the
cases"*, and it is roughly what the in-repo bench 3 produced in one step
(`RESULTS.md:72-77`: validation 0.000 → 0.750 on 8 cases, i.e. 6 of 8 flipped, δ ≈ 0.75 —
so 0.25 is conservative by 3×). At δ = 0.25 the floor is **26 (k=1) / 44 (k=14)**.

### 4.4 (b) The selector — and why author-scale validation cannot select

Selecting the argmax of k candidates on n shared cases needs a uniform-deviation bound.
Hoeffding + union: `n ≥ ln(2k/δ_conf)/(2ε²)` for selection regret ε at confidence
1 − δ_conf = 0.95:

| k | ε=0.05 | ε=0.10 | ε=0.15 | ε=0.20 |
|---|---|---|---|---|
| 1 | 738 | 185 | 82 | 47 |
| 14 | 1266 | 317 | 141 | 80 |
| 50 | 1521 | 381 | 169 | 96 |

Inverted at k=14 — **the guaranteed selection regret at author scale**:

| n | ε guaranteed |
|---|---|
| 8 | ±0.63 |
| 24 | ±0.36 |
| 50 | ±0.25 |
| 100 | ±0.18 |
| 300 | ±0.10 |

**Negative finding, and the sharpest one in this note:** at the corpus size the thesis
itself sets ("a handful", `00-THESIS.md:714`), argmax over 14 candidates on the validation
split carries a selection regret wider than the entire quality range PACT is trying to
gate. §4.5's own report evaluates 14 candidates. **The number of candidates must therefore
be budgeted against `|validation|`, not chosen freely** — the same relationship §6.9-D
already established between candidate count and *held-out*, applied one split earlier.
This is a real architectural obligation the draft does not currently state.

*(Hoeffding is loose; a paired/clustered bound would be tighter. I did not compute one
because the paired variance is not knowable a priori and the qualitative conclusion —
author-scale validation cannot finely rank 14 candidates — is robust to a 2× tightening.
Marked as a conservative bound, not a tight one.)*

---

## 5. `train` — no certification, therefore no statistical floor. An honest empirical one.

Nothing is certified from `train`; it is the proposer's search signal. Asserting a
confidence-bound floor for it would be the kind of false rigour §4.3's own note warns
against ("R1 implied it was, and that is a false theorem a reviewing statistician would
find immediately", `20-ARCHITECTURE-DRAFT.md:1530-1533`). Its floor is a **consumption**
floor: how much data the proposer's own batch machinery needs before it degenerates.

Read from source in the corpus:

| constraint | value | source |
|---|---|---|
| GEPA reflection minibatch (the unit the proposer reflects over) | **3** | `research/repos/optim/dspy/dspy/teleprompt/gepa/gepa.py:345`; upstream `research/repos/optim/gepa/src/gepa/api.py:157,355` |
| MIPROv2 data-aware proposer's view batch | **10** | `optim/dspy/dspy/teleprompt/mipro_optimizer_v2.py:125` |
| Bootstrapped demos needed per predictor | **4** (`max_bootstrapped_demos`) | `mipro_optimizer_v2.py:67`; `bootstrap.py:42` |
| MIPROv2 minibatching switches on above | **50** (`MIN_MINIBATCH_SIZE`) | `mipro_optimizer_v2.py:44,307` |
| MIPROv2 default minibatch | **35** | `mipro_optimizer_v2.py:121` |
| SIMBA **hard assert** on trainset size | **≥ 32** (`bsize`) | `simba.py:33,105` — `assert len(trainset) >= self.bsize` |
| DSPy's stated data guidance | *"you can often get substantial value out of 30 examples, but aim for at least 300"* | `optim/dspy/docs/docs/learn/optimization/overview.md:8` |
| DSPy `auto` validation sizes | light **100**, medium **300**, heavy **1000** | `mipro_optimizer_v2.py:47-51` (`AUTO_RUN_SETTINGS`) |
| DSPy's own hard minimum, in code | trainset ≥ 2, valset ≥ 1 | `mipro_optimizer_v2.py:322-331` |

The proposer floor that follows, and it is explicitly labelled empirical:

```
train ≥ max( 3 × reflection-minibatch,            # ≥3 distinct minibatches per epoch,
                                                  # else every reflection sees the same evidence
             ⌈max-bootstrapped-demos / p_success⌉, # enough successful traces to fill demos
             10 )                                  # the data-aware proposer's view batch
```

At PACT's builtin GEPA-class defaults (reflection minibatch 3, demos 4, and the pessimistic
`p_success = 0.25` a failing small model exhibits) this is `max(9, 16, 10) = 16`, with
DSPy's **30** as the recommended target and **300** as the "this is now a real training
set" mark. The 16 is a floor below which the optimiser is provably starved; it is not a
number that certifies anything, and the diagnostic must say so.

---

## 6. The ratio (DSPy's 20/80) is optimizer-declared, not schema-fixed

The draft cites DSPy's 20/80 at `20-ARCHITECTURE-DRAFT.md:2851-2853`. Read in full
(`optim/dspy/docs/docs/learn/optimization/overview.md:8`), the same sentence contains its
own exception:

> *"When splitting data for most prompt optimizers, we recommend an unusual split compared
> to deep neural networks: 20% for training, 80% for validation. This reverse allocation
> emphasizes stable validation, since prompt-based optimizers often overfit to small
> training sets. **In contrast, the dspy.GEPA optimizer follows the more standard ML
> convention: Maximize the training set size, while keeping the validation set just large
> enough to reflect the distribution of the downstream tasks.**"*

Confirmed in GEPA's source, not just its docs — `optim/dspy/dspy/teleprompt/gepa/gepa.py:517`
emits, as a runtime warning:

> *"Provide the smallest valset that is just large enough to match the downstream task
> distribution, while keeping trainset as large as possible."*

and `:523-525` actively *discourages* valsets above 35, because a large Pareto-tracking set
costs exploration budget.

**Three findings:**

1. **The draft cites a ratio that its own reference optimiser inverts.** §8.8's reference
   implementation is GEPA-class (`00-THESIS.md:355`, AC-3.4). Fixing 20/80 in the schema
   would misconfigure PACT's default optimiser by ~4×.
2. **DSPy's 20/80 is over a two-way pool that is not PACT's four-way split.** DSPy's
   sentence describes `train : val` *within the optimisation data*, with the held-out test
   set explicitly *"in addition to"* it, and DSPy has no calibration split at all. So
   20/80 may be applied **only to the `train ∪ validation` pool** and says nothing about
   `held-out` or `calibration`. Applying it to all four is a category error.
3. **Therefore the ratio belongs in the optimizer descriptor, not the schema** — a
   `splits-preference: stable-validation | maximise-train` field on the optimizer ABI
   (§8.8), consumed by `pact init splits` to *scaffold* a ratio, and never a validation
   rule. `MIPROv2` declares `stable-validation` (20/80, and its code does exactly that:
   `valset_size = min(1000, max(1, int(len(trainset) * 0.80)))`,
   `mipro_optimizer_v2.py:326`); `GEPA` declares `maximise-train`.

---

## 7. What this costs, and the residual uncertainty

### 7.1 The total-corpus arithmetic, stated once

Summing the floors for a workspace that turns on learning and uses a judged gate
(k = 14 candidates, judge gate 0.70, δ = 0.25, judge observed at a realistic 0.85):

| split | must-pass 70% | 80% | 90% |
|---|---|---|---|
| `held-out` | 16 | 26 | 54 |
| `validation` | 44 | 44 | 44 |
| `calibration` (2 × 33, only if a judge gates) | 66 | 66 | 66 |
| `train` | 16 | 16 | 16 |
| **total** | **142** | **152** | **180** |
| **total, deterministic assertions only (no calibration)** | **76** | **86** | **114** |

D13's support lead writes ~10 cases. The gap is 7×–18×. **This is not an argument against
the floors; it is the quantified argument for three things the architecture already
contains**, which now have numbers behind them rather than intuition:

- **§2.8's tiering** — core tier has no splits and no judged gates *because it cannot
  afford them*, not merely because splits are complicated.
- **§6.9a's coverage machinery and §6.6's trace promotion** — the only sustainable source
  of a 142-case gating corpus is production traffic. §6.9-D already says this for
  `held-out`; it is true of all four.
- **AC-4.5's deterministic-first ordering** — worth 66 human labels per judged gate.

### 7.2 Splits are *grown*, never *carved*

§6.9's worked arithmetic says "§6.2's split rules leave ~3 held-out" (`:3232`) — i.e. it
imagines the author's 10 cases being *partitioned*. Every floor above says partitioning is
the wrong operation: carving 10 cases four ways guarantees all four splits fail their
floor simultaneously, and the diagnostic then fires four times for one root cause.
`pact init splits` must scaffold **empty** splits with the required counts printed, and
the diagnostic must name the *total* additional cases needed, once.

### 7.3 Residual uncertainty — stated honestly

1. **δ (the flip rate) is a profile default, not a derived quantity.** I set the builtin at
   0.25 from one in-repo data point (bench 3, δ ≈ 0.75, so 0.25 is 3× conservative) and no
   external measurement. Nothing in the 141-repo corpus reports paired discordance rates
   for accepted prompt edits — I looked; the optimiser repos report score deltas, never
   flip counts. **This is the weakest number in the note.** It is falsifiable cheaply: one
   instrumented learning cycle emits d directly, and the profile default should be
   revisited once `.pact/` ledgers contain a few.
2. **The selection bound is Hoeffding-loose** (§4.4). A paired-bootstrap or clustered
   bound would give smaller n for the same ε. The direction of the conclusion is safe; the
   magnitudes are upper bounds.
3. **Calibration assumes labels are i.i.d. and correct.** If the human labeller is
   themselves ~90% consistent, the certifiable ceiling on judge agreement drops
   accordingly and the floors rise. Phoenix's guidance does not address this either. The
   corpus contains `cohen_kappa_score` usage (`phoenix-evals/references/validation.md:26`)
   but no sample-size guidance for kappa, and I did not derive one — a kappa-based floor
   would additionally need the marginal distribution, which is not knowable at validate
   time. **Left open.**
4. **The `train` floor is genuinely not derivable.** No confidence statement exists for a
   set nothing is certified from. §5's number is a consumption floor read from four
   optimiser implementations; a different optimiser family (e.g. one that fine-tunes)
   would have a completely different one. This is why §6's conclusion — that the ratio,
   and arguably the train floor too, are **optimizer-declared** — is the only stable
   answer. Marked as an inference, not a measurement.
5. **Multiplicity k for the calibration split** is modelled as "judge prompts tried". If a
   team iterates a judge rubric 10 times against the same calibration labels, the
   calibration split is itself a depleting resource in exactly the sense of §6.9-D, and
   PACT does not currently ledger it. I flag this rather than solve it: **the held-out
   query ledger has an unbuilt twin for calibration.**

---

## 8. Evidence index

**Verified by reading source:**
- `research/repos/optim/dspy/docs/docs/learn/optimization/overview.md:8` — 20/80, the GEPA
  exception, 30/300 guidance.
- `research/repos/optim/dspy/dspy/teleprompt/mipro_optimizer_v2.py:44` (`MIN_MINIBATCH_SIZE = 50`),
  `:47-51` (`AUTO_RUN_SETTINGS` val_size 100/300/1000), `:67-68` (demos 4/4), `:121` (minibatch 35),
  `:125` (`view_data_batch_size = 10`), `:214-215` (minibatch ≤ valset), `:322-331` (train ≥ 2,
  val ≥ 1, `valset_size = min(1000, max(1, int(len(trainset) * 0.80)))`).
- `research/repos/optim/dspy/dspy/teleprompt/gepa/gepa.py:345` (`reflection_minibatch_size = 3`),
  `:515-528` (the maximise-train warning; the >35 valset discouragement).
- `research/repos/optim/gepa/src/gepa/api.py:157,355` — upstream default 3, confirming the
  DSPy binding is not a re-parameterisation.
- `research/repos/optim/dspy/dspy/teleprompt/simba.py:33,105` — `bsize = 32` and the hard
  `assert len(trainset) >= self.bsize`.
- `research/repos/eval/phoenix/.agents/skills/phoenix-evals/references/observe-sampling-python.md:52-58`
  and `.../observe-sampling-typescript.md:139-145` — sample-size table, "Judge calibration | 100+ per class".
- `.../phoenix-evals/references/validation.md:3,12,19-20,26,67` — >80% agreement target,
  TPR/TNR both >70%, `cohen_kappa_score`.
- `.../phoenix-evals/references/validation-evaluators-typescript.md:4,94-95` and
  `.../validation-evaluators-python.md:3,41-42`.
- `.../phoenix-evals/references/fundamentals-anti-patterns.md:9`.
- `research/repos/eval/phoenix/.agents/skills/pxi-eval-dataset/SKILL.md:126` — *"If you
  cannot fill at least 10 rows, the target is probably too narrow"* (the only floor-shaped
  statement in the eval corpus).
- `/home/bud/ditto/gaia-ai-runtime/research/RESULTS.md:62-84` — bench 3, 8/8/8, 0 → 81.2%.

**Computed by me** (scipy 1.17.1; scripts in
`/tmp/claude-1000/-home-bud-ditto-agent-inter-op/3d6268c6-7a89-486b-b119-7c394c8ce3b1/scratchpad/derive.py`,
`derive2.py`): every table in §1, §3.4, §4.2–4.4, §7.1.

**Negative findings (things the corpus does *not* contain):**
- No repo in `eval/` or `optim/` derives a minimum eval-set size from a confidence bound.
  `deepeval`, `ragas`, `promptfoo`, `inspect_ai`, `openai-evals`, `langfuse`, `trulens`,
  `giskard` all let you run a suite of n=1. `inspect_ai` is the only one that computes a
  clustered interval at all (`inspect_ai/scorer/_metrics/std.py:56-125`, already cited by
  §6.9-B) and it guards `cluster_count < 2` rather than imposing a floor.
- No source anywhere in the corpus states a minimum **validation** split size for prompt
  optimisation. DSPy's `len(valset) < 1` check is the entire industry state of the art.
- No source states a discordance/flip rate for accepted prompt edits (§7.3.1).
- **Nobody in the corpus does this derivation.** If §6.9-A + this extension ship, PACT is
  the only agent specification that refuses to emit a verdict its corpus size cannot
  support. That is a differentiator on the T2 axis the thesis already names as the real
  one (`00-THESIS.md:151`).
