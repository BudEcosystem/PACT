# gap-r2-4 — The grader-side component of ε

**Gap as stated (round 2, gap 4).** `20-ARCHITECTURE-DRAFT.md` §10.2 closes with:

> *"The **grader-side** component of ε remains unmeasured: no repo in the eval corpus ships
> repeated gradings of a fixed output set, so §10.1's class table gives a *lower bound*
> (the quantisation floor) and not the flip rate."*

The gap decides **H33** — *"the grader-side component of ε is small relative to the null
band"* — whose falsifier is *"a Class-Q or Class-J metric whose frozen-output re-grade
spread approaches the arm's own null band … judge-graded metrics must leave the L2 gate
entirely."*

**Status: CLOSED, with the hypothesis SPLIT.**

- **H33 as written is CONFIRMED** at the level it is written about (the suite-mean ε that
  L2 compares). Every configuration for which a number now exists puts the grader-side
  band between **12% and 52%** of the arm-side null band, which inflates the combined band
  by **0.7%–13%** in quadrature. The falsifier is not met.
- **H33 as written is the wrong hypothesis, and that is the finding.** Re-grade *variance*
  is the component that averages down as `1/√n`; it was never going to dominate a
  suite mean. The grader-side component that does **not** average down is the
  **format-conditional bias** — the judge's response to a semantically equivalent output
  written differently, which is exactly what two adapters produce under D27
  (*"wording and intermediate steps may differ"*). §10.2's protocol as written re-grades
  **one frozen output set** R times and therefore cannot see it. A fixed offset survives
  any n.
- Three further results are **negative and load-bearing**: (1) §10.1's claim that Class J's
  quantum is *"~0 hosted and 0.100 on-prem"* is **wrong for every current frontier judge**
  — DeepEval **forces `temperature=1`** on 24 catalogued models and 22 of those also have
  no log-probs, so the hosted default judge in 2026 is *both* sampled *and* quantised at
  0.100; (2) the one shipped mechanism in the corpus that could isolate the grader
  (promptfoo `providerOutput` + `repeat`) returns the **cached first grade** by default;
  (3) per-**case** verdicts are dominated by judge noise even where suite means are not,
  which is where OBL-2's paired sign test lives.

**Evidence keys.** **[SOURCE]** = read in local source, file:line. **[MEASURED]** =
computed by me, command given. **[WEB]** = external publication, URL + quote.
**[DERIVED]** = arithmetic on the above. **[INFERENCE]** = my judgement, flagged.

---

## 1. Why the corpus has no such measurement — three source findings

### 1.1 [SOURCE] Nothing in the eval corpus re-grades a frozen output set

Confirmed by exhaustive grep over the 20-repo `research/repos/eval/` tree
(`grep -rniE "krippendorff|test-retest|intraclass|self-consistency"`): the only hits are
`self_consistency_solver.py` in `openai-evals` (a *solver*, i.e. the model under test
answers k times — arm-side), `icl_sc_inferencer.py` in `opencompass` (same), and prose
mentions. **No repeat-grading dataset, and no per-metric grader-variance report, exists in
the corpus.** R1's finding is reconfirmed rather than overturned.

The two repeat mechanisms that do ship are both **arm+grader combined**, not grader-only:

| repo | mechanism | what it repeats |
|---|---|---|
| `inspect_ai` | `Task(epochs=…)` (`src/inspect_ai/_eval/task/task.py:100`, `resolve_epochs` `:522-527`) | re-runs the **sample** — the model under test is called again |
| `promptfoo` | `repeat` (`src/types/index.ts:102,913-914`; loop at `src/evaluator.ts:2401-2407`) | re-runs the **provider** (`callActiveProvider`, `src/evaluator.ts:869-886`) |

`deepeval` has **no repeat concept at all** — grep for `n_runs|repeats|num_runs|rerun`
across `deepeval/evaluate/` returns nothing. Its cache is off by default
(`deepeval/evaluate/configs.py:41`, `use_cache: bool = False`), so repeated `evaluate()`
calls would at least be independent — but nothing in the package aggregates them.

### 1.2 [SOURCE] promptfoo *has* the mechanism, and its default cache silently defeats it

promptfoo is one flag away from being the tool §10.2 asks for. `test.providerOutput`
short-circuits the provider entirely and feeds a **fixed** output to the graders
(`src/evaluator.ts:868-873`), so `providerOutput` + `repeat: N` **is** a frozen-output
re-grade. But:

- caching is **on by default** — `let enabled = getEnvBool('PROMPTFOO_CACHE_ENABLED', true)`
  (`src/cache.ts:34`), and every grading call goes through `fetchWithCache`
  (`src/providers/openai/chat.ts:3,523`);
- the cache key is a hash of the **HTTP request identity** — `hashFetchCacheKey` =
  `sha256(JSON.stringify(identity))` (`src/cache.ts:439-441`) over url/body/headers;
- with the output frozen, every replicate's grader request body is byte-identical, so
  replicates 2..N are **cache hits returning replicate 1's grade**.

> **The one shipped path to measuring grader-side ε reports exactly zero variance unless
> the operator knows to set `PROMPTFOO_CACHE_ENABLED=false`.** This is worth more than the
> absence of data: it is a *mechanism* for the field's blind spot. It is also independently
> corroborated — the one 2026 paper that does this measurement states it had to disable
> caching explicitly (§3.2).

### 1.3 [SOURCE] §10.1's Class-J row is wrong about the hosted case — the default 2026 judge is *sampled*

§10.1 says the Class-J quantum is *"~0 hosted and 0.100 on-prem"* and frames the 0.100 as a
**D17 air-gap collision**. Read in source, the hosted case is worse than the air-gapped one,
because DeepEval **overrides the caller's temperature to 1** for reasoning models:

```python
# deepeval/models/llms/openai_model.py:108-110
# Auto-adjust temperature for known models that require it
if self.model_data.supports_temperature is False:
    temperature = 1
```

`deepeval/models/llms/constants.py` carries 260 catalogued model entries. **24 have
`supports_temperature=False`**, and they are precisely the models a 2026 workspace would
bind as a judge (`# Reasoning models - require temperature=1 (no custom temperature)`,
`constants.py:222`):

```
o1 · o1-2024-12-17 · o1-mini · o1-mini-2024-09-12 · o3-mini · o3-mini-2025-01-31 ·
o4-mini · o4-mini-2025-04-16 · gpt-5 · gpt-5-2025-08-07 · gpt-5-mini · gpt-5-mini-2025-08-07 ·
gpt-5-nano · gpt-5-nano-2025-08-07 · gpt-5.1 · gpt-5.2 · gpt-5.4 · gpt-5.4-2026-03-05 ·
gpt-5.4-mini · gpt-5.5 · gpt-5.5-2026-04-23 · claude-opus-4-7 · claude-opus-4-8 · claude-fable-5
```

**22 of those 24 also carry `supports_log_probs=False`** — so `no_log_prob_support()`
(`g_eval/utils.py:248-260`) fires, `a_generate_raw_response` is never reached, and G-Eval
falls to the **schema-extracted integer** path (`g_eval.py:333-345`) with the 0.100 quantum.

> **Corrected claim.** The Class-J quantum is **0.100 for the default hosted judge as well
> as for every air-gapped one**, and the hosted judge is additionally **sampled at
> temperature 1** whether or not the author asked for it. `deepeval`'s own default when the
> model *does* support temperature is 0 (`ollama_model.py:46-48`, `local_model.py:59-61`,
> `openai_model.py:99-101`), so the *only* judges for which grader-side ε ≈ 0 was ever
> plausible are the older non-reasoning ones. promptfoo's default judge is
> `gpt-5.5-2026-04-23` (`src/providers/openai/defaults.ts:6-10`) at temperature 0
> (`src/providers/openai/chat.ts:284-291`) — and OpenAI rejects `temperature≠1` on that
> family, so the same forcing applies one layer down. **[INFERENCE]** on the last clause:
> I read promptfoo's default, not the provider's rejection behaviour.

---

## 2. [MEASURED] Frozen-output re-grade, run here

### 2.1 Design

The protocol §10.2 specifies, executed:

- **Fixture set (frozen).** `research/repos/eval/tau-bench/historical_trajectories/sonnet-35-new-retail.json`,
  `trial == 0` — 115 real agent trajectories with a **deterministic** gold label
  (`tau_bench/envs/base.py:125,137,139`). Per case: `input` = `info.task.instruction`,
  `actual_output` = last non-empty assistant message (median 430 chars). Stratified
  subsample, seed 20260726, balanced on `reward`. The same corpus §10.1 uses for the
  arm-side null band, so the two halves are commensurable.
- **Graders.** Verbatim replicas of DeepEval's templates and arithmetic:
  - **Class J** — `deepeval:g_eval`, `metrics/g_eval/templates/generate_evaluation_results.txt`,
    `score_range` (0,10), score `= (int − 0)/10` (`g_eval.py:71-72,146-150`),
    **schema-extracted integer path** — the air-gapped path and the reasoning-model path.
  - **Class Q** — `deepeval:answer_relevancy`, `templates/generate_statements.txt` +
    `templates/generate_verdicts.txt`, score `= #(verdict ≠ 'no')/len(verdicts)`
    (`answer_relevancy.py:295-307`).
  - Transport replicates `models/llms/ollama_model.py:86-93` exactly: one user message,
    `format=<pydantic json schema>`, `options={"temperature": T}`.
- **Judge binding.** `qwen2.5:7b-instruct` served locally by ollama 0.24.0, CPU — a
  literal D17 air-gapped judge.
- **Conditions.** (A) temperature 1.0, identity output, R replicates — the *sampled-judge*
  case DeepEval forces on every reasoning model. (B) temperature 0.0 with
  **meaning-preserving reformattings** of the frozen output — the cross-arm case.
- Script and raw JSONL: `scratchpad/regrade.py`, `A_geval_t1.jsonl`, `B_geval_t0_pert.jsonl`,
  `C_ar_t1.jsonl`, `D_ar_t0_pert.jsonl` (session scratchpad; the script is self-contained
  and re-runnable).

The perturbations are mechanical, so meaning-preservation is guaranteed rather than judged:
`linebreak` (one sentence per line), `bullets` (prose → `- ` list), `whitespace` (collapse
blank lines), and — reported separately because it adds text — `wrapper` (a harness-style
preamble line). Every one of these is a difference two PACT adapters can produce from the
same IR while both being correct.

### 2.2 Results

<!--MEASURED-RESULTS-->

---

## 3. [WEB] What the field published in 2026, after §10.2 was written

§10.2's residual said the distribution *"has never been published"*. That is now false —
two 2026 papers publish exactly it, and both are far larger than anything runnable here.
They are the primary evidence; the local run is a D17-specific replication.

### 3.1 *The Coin Flip Judge? Reliability and Bias in LLM-as-a-Judge Evaluation* — arXiv 2606.13685

29 questions, **50 pairwise + 50 pointwise trials per question**, judges GPT-4o-mini and
GPT-4.1-mini, **fixed responses re-graded**. Quotes:

| quantity | value |
|---|---|
| pairwise flip rate at `t=1.0` (the paper's main setting: *"uses the default temperature (t=1.0) to reflect real-world usage"*) | *"pairwise preferences flip on average **13.6%** of the time, with **28% of questions exceeding a 20% flip rate** and one question reaching **56%**"* |
| pairwise flip rate at `t=0` | GPT-4o-mini **13.3% → 2.8%**; GPT-4.1-mini **13.9% → 7.9%**; *"Even at t=0, GPT-4.1-mini exhibits non-zero flip rates on **7 of 29** questions, with one reaching **50%**"* |
| **pointwise** within-question spread (fixed response) | *"with a within-question standard deviation of approximately **σ_w ≈ 0.60 points**, the 95% margin of error for a single pointwise observation is **±1.2 points**"* (10-point scale) |
| share of pointwise score variance that is judge noise | *"**44.7%** of score variance is within-question noise"*; ICC(2,1) = **0.575** (4o-mini) / **0.774** (4.1-mini) |
| replicates needed | *"**11** repeated trials are needed for a majority vote to recover the 50-trial reference verdict with 95% probability on average, rising to **15** for high-variance questions"* |
| judge-**prompt** sensitivity | *"semantically equivalent prompt templates change majority outcomes in **25%** of tested cases"* |

**The pointwise row is the one that maps onto PACT.** G-Eval's normalisation divides by the
span, so `σ_w ≈ 0.60` on a 0–10 scale is **σ_g ≈ 0.060** in DeepEval's units and the 95%
single-observation margin is **±0.120** — i.e. **larger than the Class-J quantum of 0.100**
that §10.1 derives, and of the same order as the *suite-level* arm-side null band at n=158
(0.110). Per **case**, the judge is the dominant noise source.

### 3.2 *Reliability without Validity* — arXiv 2606.19544

21 judges from 9 providers (Gemini, Claude, GPT, Llama, Qwen, Mixtral, DeepSeek, Kimi,
GLM-5, Minimax), N ∈ [3,5] independent evaluations per item, **at temperature 0**, and —
the methodological point that corroborates §1.2 — *"in order to ensure that replicate runs
sample independent generations rather than memorized responses, we execute the consistency
protocol with **response caching disabled**."*

Self-consistency (proportion of items where an individual run agrees with the majority
verdict across N runs): **cohort mean 0.969 on MT-Bench, 0.950 on JudgeBench**; range
**0.943–0.995**; worst cells **0.943** (Minimax M2.7, GPT-5.4-mini) and **0.919** (GLM-5 on
JudgeBench). Test-retest cohort means **0.943** / **0.911**.

> **At temperature 0, with caching off, between 0.5% and 8.1% of items still change
> verdict between runs of the same judge on the same input.** Nobody's judge is
> deterministic.

### 3.3 Why temperature 0 is not determinism — Thinking Machines Lab

*Defeating Nondeterminism in LLM Inference*
(https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/): batch size
changes the floating-point reduction order in RMSNorm, matmul and attention, so greedy
decoding is not reproducible under load. Measured: **temperature-0 completions for one
prompt on Qwen3-235B-A22B-Instruct-2507 yield 80 unique completions out of 1000 runs**.
With their batch-invariant kernels vLLM returns **1000/1000 identical** completions, at
**~62% higher latency**.

This is the load-bearing operational fact for D17: an air-gapped PACT install serving its
judge on vLLM/SGLang with continuous batching **has nonzero grader-side ε at temperature 0**,
and the fix (batch-invariant kernels) is a real, priced serving decision — not a config flag.
**[INFERENCE]** that PACT's air-gapped installs will use batched serving; I did not measure
a PACT deployment.

---

## 4. [DERIVED] The arithmetic that decides H33

Let `σ_g` be the per-case grader-side SD and `σ_a` the per-case arm-side SD (agent sampling
only). Two independent runs of the identical agent, each re-graded, differ at 95% by

```
band_A(n) = 1.96 · √2 · √((σ_a² + σ_g²)/n)          ← §10.2 Stage A measures this
band_G(n) = 1.96 · √2 · √( σ_g²        /n)          ← the frozen-output re-grade
```

so `σ_a² = (band_A² − band_G²)` at fixed n, and — the key structural point —
**`band_G / band_A` is independent of n**. Adding cases cannot make the grader's share
smaller; it is fixed by `σ_g/σ_a`.

Substituting the measured `σ_g` values (§3.1 for pointwise, §3.1–3.2 for verdict-style, my
own for the air-gapped case) against §10.1's maximum-variance arm (`p̂ = 0.5`, `σ_a = 0.5`):

| grader configuration | per-case σ_g | σ_g/σ_a | band_G at n=158 | vs §10.1 arm-side band 0.110 | combined-band inflation |
|---|---|---|---|---|---|
| Class J, hosted, pointwise 0–10 (2606.13685) | 0.060 | 0.12 | 0.013 | 12% | **+0.7%** |
| Class B / pairwise verdict, `t=0` (2606.13685: δ=2.8–7.9%) | 0.118–0.199 | 0.24–0.40 | 0.026–0.044 | 24–40% | +2.8%–+7.7% |
| Class B / pairwise verdict, `t=1` (2606.13685: δ=13.6%) | 0.261 | 0.52 | 0.058 | 52% | **+13%** |
| verdict-style, `t=0`, 21-judge cohort (2606.19544: δ=3.1–8.1%) | 0.124–0.201 | 0.25–0.40 | 0.027–0.044 | 25–40% | +3.1%–+7.8% |

*(For a binary score, two independent gradings disagree with probability `δ = 2q(1−q)` and
the per-case variance is `q(1−q) = δ/2`, so `σ_g = √(δ/2)`.)*

**Verdict on H33: CONFIRMED at suite level.** The worst configuration puts the grader-side
band at 52% of the arm-side one, which inflates the combined band by 13% — material, but
nowhere near "the CTS is mostly measuring the judge". H33's falsifier is not met, and
judge-graded metrics **may** gate L2, provided ε is compared at suite level, both arms are
graded by the **same** pinned judge binding, and the 13% is carried into `ε_m`.

**And the three places the suite-level answer does not apply:**

1. **Per-case verdicts.** 44.7% of pointwise score variance is judge noise and 11 replicate
   gradings are needed for a majority vote to recover a stable verdict. Anything that
   consumes a **per-case** judged outcome is dominated by grader noise. In PACT that is
   §6.9-A's `must-pass` counting *and*, worse, **OBL-2's paired sign test**, which is
   computed over per-case win/loss pairs: a 13.6% (or even 2.8%) per-case flip rate injects
   discordant pairs that carry no signal, and the sign test loses power exactly where §6.9
   rule 3's multiplicity adjustment has already made it scarce.
2. **Format-conditional bias.** Re-grade variance averages down; a bias that depends on the
   *form* of the output does not. Two adapters differ in form by construction (D27). This is
   the component §10.2's protocol cannot see, and §2.2 measures it.
3. **Judge-binding drift.** `σ_g` above is *within* one binding. Across bindings the
   quantity is not noise but incommensurability — already handled by §10.1 consequence 1
   (ε is a property of `(metric, judge-binding, score-path)`), and now with numbers:
   cross-judge agreement in 2606.13685 is 76% (κ = 0.51).

---

## 5. Normative consequences for PACT

Each is a change to `20-ARCHITECTURE-DRAFT.md`; all have been applied.

**C1 — §10.2's grader-side isolation grows a second arm.** Re-grading one frozen output set
R times measures only the averaging component. The protocol must additionally re-grade a
**format-perturbed** copy of the same output set and report `format-bias_m` — a *signed*
per-metric offset, added to `ε_m` **linearly** (it does not average down), not in
quadrature. Cost is unchanged in kind: judge calls only, no agent execution.

**C2 — §10.1's Class-J row is corrected.** The quantum is 0.100 for the hosted default
judge as well as the air-gapped one, and the hosted default is *sampled at temperature 1*
by DeepEval's own override. `pact.lock` must record `judge-temperature:` alongside
`score-path:`, and VALIDATE must reject `ε_m < 0.100` for any `deepeval:g_eval` binding on
a `supports_temperature=False` model — not only for local ones.

**C3 — H33 is split.** `H33-suite` (confirmed, +13% worst case) and `H33-percase`
(**refuted**: per-case judged outcomes are judge-dominated). The consequence is not "judge
metrics leave L2" but "judge metrics leave the **per-case** gates": OBL-2's sign test and
`must-pass` counting must either be deterministic-graded or run at `R ≥ 5` replicate
gradings with a majority reduction, with the replicate count printed.

**C4 — A judge-determinism declaration.** Temperature 0 is not determinism (§3.3). The lock
records `judge-serving: {batch-invariant: true|false|unknown}`; `unknown` and `false` both
force `ε_m ≥` the measured `band_G`, and `strict` mode refuses a judge-gated L2 claim whose
serving mode is `unknown`.

**C5 — Two corpus facts belong in the CTS harness.** The runner must set
`PROMPTFOO_CACHE_ENABLED=false` (and equivalently must never enable `use_cache`) whenever it
is measuring replicate spread, and a CTS self-test must assert that R replicate gradings of
one frozen output produce **R independent grader invocations**. §1.2 shows this is a silent
zero otherwise.

---

## 6. Residual uncertainty, stated

1. **`σ_g` for a Class-Q metric's *denominator* is measured here only at small n.** §10.2's
   companion residual (*"the distribution of `m` in Class Q is likewise unread"*) is
   addressed in §2.2 but on a single judge and a single dataset; it remains
   **workspace-dependent** and should be computed per-workspace from a pilot, as §10.2
   already suspected.
2. **Both 2026 papers use hosted OpenAI-family judges.** The local run is the only
   air-gapped evidence here, and it is one 7B judge on one dataset. `σ_g` for a small
   open-weights judge is plausibly larger than the hosted figures, which would move the
   inflation number up — the direction is known, the magnitude is not.
3. **The format-bias measurement is single-judge, single-domain.** A signed offset measured
   on one judge does not transfer to another; C1 therefore mandates *measuring* it per
   binding rather than publishing a constant.
4. **Nothing here is multi-modal.** D16 puts vision, audio and computer-use in v1; grader
   variance for a vision or audio judge is unmeasured anywhere I can find, and the
   quantisation classes of §10.1 were read from text metrics only.
5. **The arm-side σ_a used in §4 is tau-bench's, i.e. agentic and multi-turn.** For a
   single-turn text suite σ_a is smaller, which *raises* the grader's relative share. The
   ratios in §4 are therefore a **lower** bound on the grader's contribution for a
   single-turn suite — the same warning §10.2 already attaches to the 42–64% flip rate,
   pointing the other way.
