# gap-r1-3 — The per-metric ε distribution

**Gap as stated.** ε and n are published as one parameter (`20-ARCHITECTURE-DRAFT.md:4909`,
L2 v1: `ε = 0.10 at n ≥ 158 gating cases per arm`), but **the per-metric ε distribution is
still unmeasured**. The first CTS milestone must produce it; until then L2's number is a
placeholder derived from tractability rather than observation.

**Status of this note.** The gap is **partially closed**. What is now established, with
evidence:

1. A **real measurement** of same-agent re-run spread on an agentic suite, computed here
   from shipped trajectory data in the local corpus — **the ε floor is 12–17 pp at
   n = 50–115**, and the floor is not attributable to any grader.
2. A **structural taxonomy of ε classes read out of grader source**, with a *derivable,
   pre-measurement* quantisation floor per class.
3. A **negative result that reframes the parameter**: the binding sample size is
   **per-metric**, not per-suite, and metric coverage inside a suite is observed as low as
   **6–8%**. `n ≥ 158 gating cases per arm` therefore does **not** buy ε = 0.10 for any
   metric except a metric that every case exercises.
4. Four **prior-art negative findings**: nobody in the 20-repo eval corpus publishes a
   per-metric ε, the one shipped cross-implementation equivalence tool makes the wrong
   statistical claim, the most careful large-scale harness ships variance measurement
   **off by default**, and the leading agent-eval framework documents that `temperature=0`
   does not remove judge disagreement.

What is **not** closed: the *grader-side* component of ε for judge metrics is still
unmeasured — no repo in the corpus ships repeated judge runs over a fixed output set. §9
states the residual uncertainty and §8 gives the protocol that would close it.

Everything marked **[MEASURED]** was computed by me from local files, and the command is
given. Everything marked **[SOURCE]** was read in source. **[DERIVED]** is arithmetic on
top of those. **[INFERENCE]** is my judgement and is flagged as such.

---

## 1. Method and data

Two independent lines of evidence, because they answer different halves of the question.

- **The arm-side half** — "if I run the *identical* agent twice, how far apart are the two
  scores?" This is the **null band**. Any ε below it is meaningless: two byte-identical
  adapters would fail conformance from sampling noise alone. Measured from
  `research/repos/eval/tau-bench/historical_trajectories/*.json` — four shipped result
  sets, 4 or 8 independent trials each, **1,980 (task, trial) rows total**, with a
  **fully deterministic grader** (§3), which isolates arm-side noise perfectly.
- **The grader-side half** — "given one fixed agent output, how far apart are two
  gradings?" Read out of grader source (DeepEval, Ragas, promptfoo, inspect_ai), because
  no repo in the corpus ships the repeated-grading data that would let me measure it
  (§9.1).

---

## 2. [MEASURED] The null band: same agent, same suite, deterministic grader

`tau-bench` ships the raw per-trial results behind its paper. Each file is a list of
`{task_id, trial, reward, info}` rows; `trial` indexes **independent re-runs of the same
agent against the same tasks** (`tau_bench/run.py:180-203` derives `pass^k` from exactly
this structure). Nothing differs between trials except sampling.

```
cd research/repos/eval/tau-bench/historical_trajectories
# per-trial suite pass rate = fraction of tasks with reward > 1-1e-6
```

| file | tasks n | trials T | per-trial pass rate | **range (pp)** | sd | mean pairwise \|Δ\| |
|---|---|---|---|---|---|---|
| `gpt-4o-retail.json` | 115 | 4 | .617 .617 .600 .583 | **3.5** | .0167 | .020 |
| `gpt-4o-airline.json` | 50 | 4 | .420 .440 .400 .420 | **4.0** | .0163 | .020 |
| `sonnet-35-new-retail.json` | 115 | 8 | .730 .704 .704 .687 .704 .609 .748 .652 | **13.9** | .0441 | .051 |
| `sonnet-35-new-airline.json` | 50 | 8 | .500 .400 .440 .480 .460 .460 .420 .520 | **12.0** | .0400 | .049 |

**The two 8-trial sets are the informative ones** — with T = 4 the observed range is a
badly under-sampled estimate of the true spread, which is exactly why the two 4-trial
files look deceptively tight. At T = 8 the *same agent* on the *same suite* with a
*deterministic grader* spans **13.9 pp (n=115)** and **12.0 pp (n=50)**.

**Task-level instability [MEASURED].** Decomposing to per-task success counts `c/T`:

| file | n | T | always pass | always fail | **flips** | flip % |
|---|---|---|---|---|---|---|
| gpt-4o-retail | 115 | 4 | 44 | 22 | 49 | **42.6%** |
| gpt-4o-airline | 50 | 4 | 10 | 14 | 26 | **52.0%** |
| sonnet-35-new-retail | 115 | 8 | 41 | 7 | 67 | **58.3%** |
| sonnet-35-new-airline | 50 | 8 | 8 | 10 | 32 | **64.0%** |

**42–64% of cases are coins.** This is the physical reason the null band is wide, and it
is a property of *agentic* suites specifically — a multi-turn trajectory has many more
branch points than a single completion.

> **This is the single most important number in this note.** PACT's CTS compares two arms
> that are *supposed* to differ (harness vs native, adapter A vs adapter B). It cannot
> resolve a difference smaller than the difference it sees between an arm and *itself*.

---

## 3. [SOURCE] The grader contributed none of that spread

`tau_bench/envs/base.py:124-164`:

- `r_actions` — the environment replays the ground-truth action list and compares a **hash
  of the resulting database state** to the agent's: `data_hash = self.get_data_hash()`
  (`:125`), `gt_data_hash = self.get_data_hash()` (`:137`), `r_actions = data_hash ==
  gt_data_hash` (`:139`). Pure function of the agent's write-set.
- `r_outputs` — case-insensitive substring containment of each required output string in
  some `respond` action's content (`:150-158`). Pure function of the agent's text.

Both graders are deterministic. **Grader-side ε = 0 by construction, and the 12–17 pp
still happened.** This is the cleanest available isolation of arm-side noise in the corpus,
and it means every ε number for a *judged* metric is this floor **plus** grader noise, not
instead of it.

### 3.1 [MEASURED] …and the two deterministic components already disagree with each other

Decomposing per reward component — i.e. treating `r_actions` and `r_outputs` as two
metrics over the same suite, which is exactly what PACT's per-metric ε means:

| file | metric | cases/trial | mean | **range (pp)** | sd | max pairwise \|Δ\| |
|---|---|---|---|---|---|---|
| gpt-4o-retail | `r_actions` | 76–77 | .562 | 2.6 | .011 | .026 |
| gpt-4o-retail | `r_outputs` | 38 | .697 | 7.9 | .034 | .079 |
| sonnet-35-retail | `r_actions` | 76–77 | .663 | **16.9** | .057 | .169 |
| sonnet-35-retail | `r_outputs` | 38 | .753 | **13.2** | .044 | .132 |
| gpt-4o-airline | `r_actions` | 45–46 | .445 | 8.7 | .039 | .087 |
| gpt-4o-airline | `r_outputs` | **3–4** | .229 | **66.7** | .315 | **.667** |
| sonnet-35-airline | `r_actions` | 45–46 | .455 | **15.2** | .046 | .152 |
| sonnet-35-airline | `r_outputs` | **3–4** | .615 | **50.0** | .183 | **.500** |

**Two metrics, one suite, one agent, one run pair — and the per-metric spreads differ by an
order of magnitude (2.6 pp to 66.7 pp).** A single suite-wide ε is not a summary of this
distribution; it is a number that is simultaneously too loose for `r_actions` on retail and
absurdly too tight for `r_outputs` on airline.

**The driver is n, not the metric.** `r_outputs` applies to only **3–4 of 50** airline
cases because only those tasks declare `task.outputs` (`base.py:144`). Which brings us to
the finding that actually reframes the parameter.

---

## 4. [DERIVED] The binding n is per-metric, and suite n does not buy it

Model the null band directly. Two independent runs of the same agent, per-case success
probability `p`, `n` cases: each run's mean has sd `√(p(1−p)/n)`, so the 95% band on the
**difference** is `1.96·√2·√(p(1−p)/n)`.

**Null band on |score_A − score_B| for two runs of the *same* agent:**

| n | p = 0.50 | p = 0.70 | p = 0.90 |
|---|---|---|---|
| 8 | 0.490 | 0.449 | 0.294 |
| 24 | 0.283 | 0.259 | 0.170 |
| 30 | 0.253 | 0.232 | 0.152 |
| 50 | 0.196 | 0.180 | 0.118 |
| 100 | 0.139 | 0.127 | 0.083 |
| 115 | 0.129 | 0.118 | 0.078 |
| **158** | **0.110** | **0.101** | 0.066 |
| 193 | 0.100 | 0.091 | 0.060 |
| 550 | 0.059 | 0.054 | 0.035 |
| 769 | 0.050 | 0.046 | 0.030 |

**Minimum n for the null band to fall at or below ε:**

| ε | p = 0.50 | p = 0.70 | p = 0.90 |
|---|---|---|---|
| 0.20 | 49 | 41 | 18 |
| 0.15 | 86 | 72 | 31 |
| **0.10** | **193** | **162** | **70** |
| 0.05 | 769 | 646 | 277 |
| 0.02 | 4,802 | 4,034 | 1,729 |

### 4.1 Where the published 158 actually sits

`n = 158` is the n at which the null band equals 0.10 **at p̂ ≈ 0.70** (the table gives 162
for exactly 0.10; 158 gives 0.101). At **p̂ = 0.50 — the worst case, and the case a
conformance suite should assume — the requirement is n ≥ 193, and at n = 158 the null band
is 0.110, i.e. *wider than ε itself*.**

So the published pair is not conservative-but-tractable. **It is correct only under an
unstated assumption about p̂ and only at suite level.** The right statement is that
**ε, n and p̂ are one parameter, not two** — the doc's `[R3]` insight is right and one
variable short.

The empirical check is consistent: the `sonnet-35-retail` set has p̄ ≈ 0.70 at n = 115,
predicted band 0.118, and the observed max pairwise |Δ| over 28 pairs is **0.139** —
slightly above, as a max-of-28 should be. **[INFERENCE]** The binomial model is a *floor*,
not a fit: real re-runs share provider state, environment state and time-correlated
degradation, so genuine spread should meet or exceed it. With T ∈ {4, 8} the observed sd is
too noisy to test this, and I do not claim to have tested it.

### 4.2 [DERIVED] The coverage collapse — the actual defect in the published parameter

A metric only scores the cases that exercise it. Observed coverage in tau-bench:
`r_actions` 67% (retail) / 91% (airline); `r_outputs` **33%** (retail) / **6–8%** (airline).

Take the published `n ≥ 158 gating cases per arm` and propagate:

| metric coverage c | n_m at suite n=158 | null band (p=.5) | null band (p=.7) |
|---|---|---|---|
| 100% | 158 | 0.110 | 0.101 |
| 67% | 106 | 0.135 | 0.123 |
| 50% | 79 | 0.156 | 0.143 |
| 33% | 52 | 0.192 | 0.176 |
| 20% | 32 | 0.245 | 0.225 |
| 10% | 16 | 0.346 | 0.318 |
| **8%** | **13** | **0.384** | **0.352** |

Suite n required so the *worst* metric reaches ε = 0.10 at p̂ = 0.70 (i.e. n_m ≥ 162):

| worst coverage | suite n required |
|---|---|
| 100% | 162 |
| 50% | 324 |
| 33% | 491 |
| 20% | 810 |
| 10% | 1,620 |
| 8% | 2,025 |

> **Conclusion.** `n ≥ 158 gating cases per arm` is not a sufficient condition for ε = 0.10
> on any metric. It is sufficient only for a metric with **100% coverage and p̂ ≥ 0.70**.
> The gate must be `n_m ≥ n(ε_m, p̂_m)` **per metric**, and the CTS corpus must be sized
> from `max_m ⌈n(ε_m, p̂_m) / c_m⌉`.
>
> This is also the honest reason the per-metric distribution is "unmeasured": it was never
> going to be a distribution over metric *identities*. It is a distribution over
> `(metric-class, n_m, p̂_m)` triples, and two of the three are properties of the author's
> suite, not of PACT.

---

## 5. [SOURCE] ε classes, read out of grader construction

The grader-side component of ε is not a free empirical parameter either — a large part of
it is **derivable from source before any measurement**, because the score arithmetic
quantises. Five classes, all read in source.

### Class D — deterministic / programmatic. Grader-side ε ≡ 0.

Pure functions of the agent output. Verified:

| grader | source | construction |
|---|---|---|
| tau-bench `r_actions` | `tau-bench/tau_bench/envs/base.py:125,137,139` | DB-state hash equality |
| tau-bench `r_outputs` | `tau-bench/tau_bench/envs/base.py:150-158` | case-insensitive substring |
| DeepEval `JsonCorrectnessMetric` | `deepeval/metrics/json_correctness/json_correctness.py:87-93,137-143` | `score = 1 if valid_json else 0` via Pydantic `model_validate_json` |
| DeepEval `ToolCorrectnessMetric` | `deepeval/metrics/tool_correctness/tool_correctness.py:371-387` | exact match / weighted-LCS over tool names |
| promptfoo deterministic family (17 assertion types: `equals`, `contains*`, `regex`, `starts-with`, `is-json`, `contains-json`, `is-html`, `is-sql`, `is-xml`, `levenshtein`, `rouge`, `bleu`, …) | `promptfoo/site/docs/configuration/expected-outputs/index.md:112-133` | shipped, named "Deterministic eval metrics", explicitly partitioned from "Model-assisted eval metrics" at `:166-170` |

**ε for a Class-D metric is entirely the null band of §4.** Nothing else contributes. This
is a genuinely useful result: for the deterministic half of a suite, ε is *computable in
advance* from `(n_m, p̂_m)` and needs no measurement at all.

### Class Q — quantised ratio of LLM verdicts. Quantum `1/m`, `m` itself LLM-decided.

The dominant DeepEval family. Every one of these computes `score = k / len(self.verdicts)`
where the verdict list is produced by an extraction LLM call:

| metric | source line | form |
|---|---|---|
| `FaithfulnessMetric` | `faithfulness/faithfulness.py:375-392` | `faithfulness_count / number_of_verdicts` |
| `AnswerRelevancyMetric` | `answer_relevancy/answer_relevancy.py:296-307` | `relevant_count / number_of_verdicts` |
| `ContextualRecallMetric` | `contextual_recall/contextual_recall.py:249-260` | `justified_sentences / number_of_verdicts` |
| `ContextualRelevancyMetric` | `contextual_relevancy/contextual_relevancy.py:252-265` | `relevant_statements / total_verdicts` |
| `HallucinationMetric` | `hallucination/hallucination.py:240-251` | `hallucination_count / number_of_verdicts` |
| `ToxicityMetric` | `toxicity/toxicity.py:269-280` | `toxic_count / total` |
| `BiasMetric` | `bias/bias.py:272-283` | `bias_count / number_of_verdicts` |
| `SummarizationMetric` (alignment) | `summarization/summarization.py:292-305` | `faithfulness_count / total` |
| `ContextualPrecisionMetric` | `contextual_precision/contextual_precision.py:330-354` | weighted precision@k — same denominator dependence |

**Cross-library, not a DeepEval quirk.** Ragas is identical:
`ragas/src/ragas/metrics/_faithfulness.py:182-194` — `num_statements =
len(answers.statements)`; `score = faithful_statements / num_statements`.

Two independent noise sources, and the second is the one nobody accounts for:

1. **Numerator noise** — a verdict flips. Moves the case score by `1/m`.
2. **Denominator noise** — the extraction LLM decides `m` differently on the second run.
   **This moves the score with the agent's output held byte-identical.** `3/4 = 0.750`
   becomes `3/5 = 0.600` — a **15 pp move attributable entirely to the grader**.

**[DERIVED] Per-case quantum for typical `m`:** m=3 → 0.333; m=4 → 0.250; m=5 → 0.200;
m=8 → 0.125; m=10 → 0.100. **[INFERENCE]** `m` in the 3–8 range is what these prompts
elicit for ordinary answer lengths; I did not measure the distribution of `m`, and §9.2
records that as open.

`strict_mode` does **not** help: it collapses the score to `0` below threshold
(`faithfulness.py:392` etc.), or to `1` above threshold for the inverted metrics
(`hallucination.py:251`, `toxicity.py:280`, `bias.py:283`). That converts Class Q into
Class B — quantum 1.0 — which **raises** variance while removing quantisation.

### Class J — judge integer score. Quantum `1/span`, and **the path is substrate-dependent**.

`GEval` is the case that breaks the assumption that ε is a property of a metric.
`deepeval/metrics/g_eval/g_eval.py` selects among **three different score-generation paths
at run time**:

1. **Log-prob weighted continuous** (`g_eval.py:311-329` → `utils.py:336-381`): asks for
   `top_logprobs` (default 20, `g_eval.py:55,81`), filters tokens below 1% linear
   probability (`utils.py:350-356`), and returns `Σ score·p / Σ p`. Continuous;
   **lowest variance of the three.**
2. **Raw integer** — taken when `no_log_prob_support(self.model)` (`g_eval.py:305-307`,
   gate at `utils.py:248-260`, which consults `supports_log_probs` on `GPTModel` /
   `AzureOpenAIModel` / `OPENAI_MODELS_DATA`), or when `strict_mode` is set
   (`g_eval.py:322-323`).
3. **Schema-extracted integer** (`g_eval.py:335-345`): the fallback when the model object
   has no `a_generate_raw_response` at all — i.e. **any custom/local judge**.

The score is an **integer** in `score_range`, defaulting to `(0, 10)`
(`utils.py:400-404`; the `Rubric` validator hard-caps both ends to 0..10,
`utils.py:39-50`), normalised as `(g_score − lo) / span` (`g_eval.py:71-72,147-148,210`).

> **[SOURCE] This is a direct D17 collision, and it is the sharpest finding in §5.**
> Paths 2 and 3 are the *only* paths available to a local, air-gapped judge — no
> `top_logprobs`, no `a_generate_raw_response`. So **the same `deepeval:g_eval` metric has
> a per-case quantum of ~0 in a hosted deployment and 0.100 on-prem** (1.000 in
> `strict_mode`, whose template forces `score ∈ {0,1}`,
> `templates/generate_strict_evaluation_results.txt`).
>
> **ε is therefore not a property of `(metric)`. It is a property of
> `(metric, judge-binding, score-path)` — and the air-gapped path is the noisier one.**
> A conformance verdict computed in CI against a hosted judge does not transfer to the
> customer's air-gapped install. Under D17 that is the deployment PACT is actually
> certifying, so the *noisier* path is the one L2 must be sized for.

### Class B — binary judge. Quantum 1.0 per case.

`strict_mode` anywhere; `GEval` strict template; `promptfoo` `llm-rubric` with a pass/fail
rubric. Pure Bernoulli — no quantisation, maximum per-case variance. The §4 tables apply
directly with `p` = the judge's pass rate, **and** the judge's own disagreement rate adds
on top.

### Class E — embedding similarity. Deterministic given a pin; undefined across substrates.

`promptfoo` `similar` (`src/assertions/similar.ts:21`, default threshold 0.75) is a cosine
threshold over an embedding model. Given a pinned embedding model it is a pure function
(ε = 0, Class D). **Across a different embedding model the score is not comparable at all**
— not "noisier", *incommensurable*. **[INFERENCE]** the correct treatment is not an ε but a
lockfile obligation: the embedding binding is part of the metric's identity, and an
unpinned Class-E metric must not be gateable.

### Summary table

| class | grader-side ε | per-case quantum | governed by |
|---|---|---|---|
| **D** deterministic | **0** | n/a | `(n_m, p̂_m)` only — *computable, no measurement needed* |
| **Q** ratio-of-verdicts | > 0, two-source | `1/m`, `m` LLM-decided | `(n_m, p̂_m, m̄)` + verdict-flip rate |
| **J** judge integer | > 0, **path-dependent** | `1/span` (0.100 default) on paths 2–3; ~0 on path 1 | `(n_m, p̂_m, judge, score-path)` |
| **B** binary judge | > 0, maximal | 1.000 | `(n_m, p̂_m, judge)` |
| **E** embedding | 0 if pinned; **undefined** if not | n/a | the embedding binding, which is part of metric identity |

---

## 6. Prior-art negatives — nobody has this number, and the obvious tool is wrong

### 6.1 The one shipped cross-implementation equivalence test makes the wrong claim

`lm-evaluation-harness` treats HuggingFace as the reference implementation and ships a
comparator for vLLM against it (`README.md:455`). Reading
`scripts/model_comparator.py`:

```python
Z = (acc1 - acc2) / np.sqrt((st_err1**2) + (st_err2**2))     # :30
p_value = 2 * norm.sf(abs(Z))                                # :32  two-tailed
...
comparison_df[f"p > {alpha}"] = comparison_df["P-Value"].apply(
    lambda p: "✓" if p > alpha else "×")                     # :60-62
```

This is **a difference test used as an equivalence test**. `p > α → ✓` is *failure to
reject the null of equality*, which is not evidence of equality — and its power is worst
exactly where PACT operates: the default is `--limit 100` (`:76-80`) with `alpha=0.05`
(`:81-86`). **At small n it passes by construction.** This is precisely the failure
`20-ARCHITECTURE-DRAFT.md:3217-3218` (§6.9 rule 2) already forbids for PACT, and it is now
backed by a shipped counter-example rather than by argument.

Two things it gets *right* and PACT should copy: the z is computed **per task**, never
pooled (`:132-137`), and it consumes the harness's own per-task `acc_stderr` rather than
re-deriving one (`:28-29`).

### 6.2 The most careful large-scale harness ships variance measurement off by default

HELM's `AdapterSpec` (`helm/src/helm/benchmark/adaptation/adapter_spec.py`):

```python
num_train_trials: int = 1   # :102 "Number of trials, where in each trial we choose an
                            #       independent, random set of training instances.
                            #       Used to compute variance."
num_trials: int = 1         # :106 "...same requests, but different random seeds."
```

**Both default to 1.** HELM has a purpose-built `Stat` accumulator with `variance` and
`stddev` (`helm/src/helm/benchmark/metrics/statistic.py:17-31`) and the default
configuration produces neither. **[INFERENCE]** this is the systemic reason the per-metric
ε distribution does not exist anywhere in the literature: measuring it costs a multiple of
the eval budget and nobody's default pays it.

### 6.3 `temperature=0` does not remove judge disagreement — documented, not folklore

`inspect_ai/docs/model-graded.qmd:190-193`, in the "For more reproducible grading" list:

> "Run multiple `epochs` and inspect grade variance — setting `temperature=0` reduces, but
> does not always eliminate, run-to-run disagreement."

This closes off the tempting shortcut ("pin temperature, ε_grader → 0"). It does not.

### 6.4 The estimator question is settled; import it, don't invent it

`inspect_ai/src/inspect_ai/scorer/_metrics/std.py:56-125` implements clustered standard
errors per arXiv 2411.00640 App. A with a finite-cluster correction, guards
`cluster_count < 2 → 0.0` (`:104-107`), and **raises rather than guessing** when cluster
metadata is missing (`:88-93`). `20-ARCHITECTURE-DRAFT.md:3276-3281` already adopts this;
this note confirms it is the right import and adds that the same file's
`bootstrap_stderr` (`:16-52`) is the estimator to *avoid* below n ≈ 30, consistent with
§6.9-B.

### 6.5 The field explicitly disclaims cross-implementation comparability

`lm-evaluation-harness/README.md:778`: *"we prioritize agreement with the procedures used
by other groups to decrease the harm when people inevitably compare runs across different
papers **despite our discouragement of the practice**."*

**[INFERENCE]** PACT's L2 is precisely the discouraged practice, done deliberately and with
statistics attached. That is defensible — but it means the CTS is measuring something the
field has never published a tolerance for, and PACT cannot borrow one.

---

## 7. What this changes for L2

1. **The parameter is a triple, not a pair, and it is per metric.**
   `(ε_m, n_m, p̂_m)` — because `n(ε, p̂) = ⌈2·z²·p̂(1−p̂)/ε²⌉` and p̂ is the third free
   variable. `ε = 0.10 at n ≥ 158` is the p̂ = 0.70 point on that surface.
2. **`n` must be counted per metric, not per suite.** The suite gate must be derived:
   `suite_n ≥ max_m ⌈n(ε_m, p̂_m) / c_m⌉` where `c_m` is metric m's coverage. At the
   observed coverage floor (6–8%) that is a factor of 12–17 on suite size.
3. **A metric whose `n_m` is below its requirement is `UNDECIDED`, never `PASS`.** This is
   the existing §6.9 verdict machinery applied at metric granularity — the fix is
   plumbing, not new semantics. `r_outputs` at `n_m = 3` must be reported, not silently
   folded into a suite mean.
4. **ε_m has a floor that is known before any measurement**, from the class table in §5.
   An ε_m below the class quantum is unsatisfiable arithmetic — exactly the error §6.9
   rule 1 already forbids for judge-gated thresholds, extended to ε. In particular
   **ε_m ≥ 0.100 is forced for an air-gapped `deepeval:g_eval`** on the default 0–10 range.
5. **The score path belongs in the lockfile.** A verdict obtained on G-Eval's log-prob path
   does not transfer to the schema-extract path, and under D17 the customer runs the second
   one. Recording `score-path:` alongside `interval-method:` costs one field.
6. **Class D is free.** For deterministic metrics ε is fully determined by `(n_m, p̂_m)` and
   needs no CTS measurement at all. The first CTS milestone should therefore measure
   **only classes Q, J and B**, which shrinks it by roughly half **[INFERENCE]** and makes
   it affordable.
7. **The default ε should be class-keyed, and 0.10 is the *floor*, not the value.**
   §4 shows 0.10 is the same-agent null band at n=158/p̂=0.70 — i.e. a suite that just
   satisfies the current gate is operating *at* its own noise floor with zero margin.

---

## 8. The protocol that closes the rest of the gap

The first CTS milestone should be a **two-stage design**, because the quantity it must
report is a *ratio*, not an absolute:

**Stage A — measure the null band (arm vs itself).** Run the reference adapter `R ≥ 8`
times over the full gating corpus. Report, per metric: `n_m`, `c_m`, `p̂_m`, observed sd of
the metric mean across replicates, and observed max pairwise |Δ|. R ≥ 8 because the two
`T = 4` tau-bench files under-report their own spread by 3–4× relative to the `T = 8` files
(§2). This stage needs **no second adapter** and can run in Stage 1 of the implementation
plan.

**Stage B — measure the cross-arm band.** Same corpus, harness-vs-native and
harness-vs-raw. `ε_m` is then set as the **larger of** (i) the class quantum from §5 and
(ii) the Stage-A null band inflated by the multiplicity adjustment already specified in
§6.9 rule 3.

**Grader-side isolation, which nothing in the corpus does.** For classes Q/J/B, re-grade a
**frozen set of agent outputs** `R` times without re-running the agent. The difference
between that spread and Stage A's is the grader-side component — the number §9.1 says is
missing. This is cheap: no agent execution, only judge calls.

**Report shape.** One row per metric: `metric, class, n_m, c_m, p̂_m, quantum,
null-band, cross-arm-band, ε_m, verdict`. This *is* the per-metric ε distribution the
milestone owes, and it is publishable as an artifact rather than as a single number.

---

## 9. Residual uncertainty — stated honestly

**9.1 The grader-side component of ε is still unmeasured, and I could not measure it.**
No repo in the 20-repo eval corpus ships repeated gradings of a fixed output set. HELM
*could* produce it (`num_trials`) but ships it disabled (§6.2); inspect_ai *could*
(`epochs`) and its docs recommend it (§6.3) without publishing a result; DeepEval has no
replicate concept at all. §5 gives the *quantisation floor* from source, which is a lower
bound. The flip rate on top of it is unknown. **This is the honest remainder of the gap,
and §8's frozen-output re-grade is the cheapest way to close it.**

**9.2 The distribution of `m` (verdict count) in Class Q is unmeasured.** The quantum is
`1/m` and I read the arithmetic, not the values. m is data-dependent (answer length,
retrieval-context size) and therefore workspace-specific — **[INFERENCE]** it may be better
computed per-workspace at validate time from a pilot run than published as a constant.

**9.3 tau-bench is agentic and multi-turn; the null band may be narrower for single-turn
text metrics.** 42–64% of tau-bench cases flip (§2) because a trajectory has many branch
points. A single-completion faithfulness case plausibly flips less. I did **not** measure
that, and generalising the 12–17 pp figure to single-turn metrics would be unwarranted.
What *does* generalise is the arithmetic in §4 — it is model-free given `(n, p̂)`.

**9.4 The independent-Bernoulli model is a floor and I did not test it.** §4.1. With
T ∈ {4, 8} the observed sd is too noisy to confirm or refute. One of four files exceeds the
model by 1.5×.

**9.5 Two of the four tau-bench files are T = 4** and are shown only because omitting them
would be selective. The T = 8 files carry the finding.

**9.6 I did not re-run any model.** Every number in §2 and §3.1 is a recomputation over
data tau-bench committed to its own repository. That is a strength for reproducibility and
a weakness for currency — the models are gpt-4o and claude-3.5-sonnet-new, and
**[INFERENCE]** a 2026 frontier model is plausibly more self-consistent, which would narrow
the null band without changing any of the structural conclusions in §4.2 or §5.

---

## 10. Evidence index

| Claim | Evidence |
|---|---|
| Same-agent re-run spread 13.9 pp @ n=115, 12.0 pp @ n=50 | **[MEASURED]** `research/repos/eval/tau-bench/historical_trajectories/{sonnet-35-new-retail,sonnet-35-new-airline}.json`, 8 trials each |
| 42–64% of agentic cases flip across identical re-runs | **[MEASURED]** same files, per-`task_id` success counts |
| Per-component spread 2.6 pp → 66.7 pp on one suite | **[MEASURED]** same files, `info.reward_info.info.{r_actions,r_outputs}` |
| Both tau-bench graders deterministic | `tau-bench/tau_bench/envs/base.py:124-164`, esp. `:125,137,139,150-158` |
| Metric coverage as low as 3–4 / 50 cases | **[MEASURED]** `gpt-4o-airline.json`, `sonnet-35-new-airline.json`; mechanism at `base.py:144` |
| pass^k is computed from exactly this replicate structure | `tau-bench/tau_bench/run.py:180-203` |
| Nine DeepEval metrics score as `k/m`, m LLM-decided | `deepeval/metrics/{faithfulness:375-392, answer_relevancy:296-307, contextual_recall:249-260, contextual_relevancy:252-265, contextual_precision:330-354, hallucination:240-251, toxicity:269-280, bias:272-283, summarization:292-305}` |
| Same pattern in Ragas | `ragas/src/ragas/metrics/_faithfulness.py:182-194` |
| `strict_mode` collapses Q → binary | `faithfulness.py:392`, `hallucination.py:251`, `toxicity.py:280`, `bias.py:283` |
| G-Eval has three score paths chosen at run time | `deepeval/metrics/g_eval/g_eval.py:305-345`; gate `g_eval/utils.py:248-260` |
| G-Eval score is an integer over a 0–10 default range, normalised by span | `g_eval/utils.py:39-50,400-404`; `g_eval.py:71-72,147-148,210` |
| Log-prob weighting is the variance-reduction path | `g_eval/utils.py:336-381`, 1% filter at `:350-356` |
| Strict template forces score ∈ {0,1} | `g_eval/templates/generate_strict_evaluation_results.txt` |
| Deterministic DeepEval metrics | `json_correctness/json_correctness.py:87-93,137-143`; `tool_correctness/tool_correctness.py:371-387` |
| promptfoo ships a deterministic / model-assisted partition | `promptfoo/site/docs/configuration/expected-outputs/index.md:112-133,166-170` |
| Embedding assertions are substrate-bound | `promptfoo/src/assertions/similar.ts:21` |
| The shipped cross-impl test is a difference test used as equivalence | `lm-evaluation-harness/scripts/model_comparator.py:25-33,60-62,76-86`; `README.md:455` |
| Field disclaims cross-implementation comparability | `lm-evaluation-harness/README.md:778` |
| HELM ships variance measurement off by default | `helm/src/helm/benchmark/adaptation/adapter_spec.py:102-107`; `metrics/statistic.py:17-31` |
| temperature=0 does not eliminate judge disagreement | `inspect_ai/docs/model-graded.qmd:190-193` |
| Clustered-SE estimator to import; bootstrap to avoid at small n | `inspect_ai/src/inspect_ai/scorer/_metrics/std.py:16-52,56-125,88-93,104-107` |
| Null-band and required-n tables | **[DERIVED]** `band = 1.96·√2·√(p(1−p)/n)`; `n = ⌈2·1.96²·p(1−p)/ε²⌉` |
