# Gap R1-1 — The reflector meta-benchmark (`reflect-bench`) and §4.4a's competence gate

**Assignment.** §4.4a's competence gate needs a shipped, air-gappable propose-and-improve
benchmark over frozen fixtures with known-good improvements, plus a calibrated threshold.
Without it the gate is a placeholder and RES-8 has no principled refusal point. §13.9b
motivates the gate by asserting that *"a local reflector's expected gain is at or below
zero"* while D17 makes local mandatory.

**Headline result — the gap is closable, but not in the direction the assignment assumed.**
The corpus contains one controlled optimiser-strength ablation (SkillOpt Table 5). It
**falsifies §13.9b's headline claim**: a *target-matched* optimiser — the weak local model
reflecting on itself, exactly PACT's air-gapped case — is positive in 4 of 4 cells and
recovers 56–74% of a frontier optimiser's gain, **provided the loop is validation-gated and
bounded-edit**. All three evidence items §4.4a cites for the opposite conclusion fail
verification. The real variable is the **accept gate**, not the reflector, and that is
source-verified in three independent implementations.

So `reflect-bench` should still ship — but its job changes from *"is this reflector
competent enough to be allowed to run?"* to *"what will a fixed budget buy, and is the
answer distinguishable from zero?"* That reframing gives RES-8 a **principled refusal point
that needs no cross-model calibration table**, which is the part the original design could
not supply.

Evidence markers: `[SRC]` read in source; `[TBL]` read from a paper table; `[DER]` derived
arithmetic; `[INF]` my inference, marked as such.

---

## 1. What did not survive verification

### 1.1 The ACE ladder is not a reflector ablation `[SRC/TBL]`

§4.4a, §13.9b and `research/notes/model-portability.md` §Q2 all lean on
*"ACE +17.1 at 671B → +7.6 at 120B → +2.4 at Llama-3.3-70B"* as a reflector-strength curve.

Verified against the paper (`/home/bud/ditto/gaia-ai-runtime/research/papers/2510.04618-ace.pdf`,
Appendix A.1, first paragraph):

> "We evaluated ACE with three additional models of varying size, cost, and capability:
> GPT-OSS-120B (Table 5 and 7), GPT-5.1 (Table 6 and 8), and Llama-3.3-70B-Instruct
> (Table 9). **In each case, the Generator, Reflector, and Curator were all switched to the
> new model** without changes to the algorithm."

Two independent defects:

1. **Confounded.** Every row changes the *executor* and the *reflector* together. Nothing
   in that sequence isolates the reflector. §8.7 already says this ("confounds executor
   with optimiser"); §4.4a and §13.9b were never updated to match, and both still print the
   ladder as the gate's justification.
2. **Three different benchmarks.** `+17.1` is AppWorld (Table 3, ACE + offline warmup,
   average Δ over four columns). `+7.6` is FiNER only (Table 2 / Table 17 baseline row,
   70.7 → 78.3). `+2.4` is the Financial Analysis benchmark on Llama-3.3-70B (Table 9,
   62.5 → 64.9). The three numbers are not on a common scale, so the "ladder" is not a
   quantity. `[DER]`

The like-for-like series §8.7 substitutes (Financial Analysis, offline, GT labels:
DeepSeek-671B **+12.8**, GPT-OSS-120B **+12.1**, GPT-5.1 **+9.5**, Llama-70B **+2.4**;
Tables 2/7/8/9) `[TBL]` is correct but **non-monotone in capability** — GPT-5.1 gains less
than GPT-OSS-120B — and is still executor-confounded. It supports "the weakest endpoint is
weak"; it does not support a capability→gain function.

### 1.2 ACE's *only* controlled reflector ablation says the opposite `[TBL]`

ACE Table 16 (FiNER; Generator and Curator held fixed at DeepSeek-V3.1; **only the
Reflector varies**):

| Reflector | Accuracy | Δ vs base LLM (70.7) |
|---|---|---|
| GPT-OSS-120B | 76.6 | **+5.9** |
| DeepSeek-V3.1-671B | 78.3 | **+7.6** |
| GPT-5.1 | 78.5 | **+7.8** |

A 1.9 pp spread across a 120B→frontier range. ACE §4.6 states the conclusion in its own
words:

> "ACE is robust to reflection quality: it remains effective with a much weaker Reflector
> and shows only modest additional gains from stronger reflectors."

and Appendix A.4:

> "Across all choices, ACE consistently improves over the base LLM, **including when the
> Reflector is much weaker**."

The paper PACT cites as its primary evidence that reflector strength is decisive concludes,
in the one experiment that isolates it, that it is **not** decisive. This is the single
largest evidence error in §4.4a.

### 1.3 "Import beats weak re-optimisation" is 1 of 4 rows `[TBL]`

§4.4a clause 3 and §13.9b both assert: *"SkillOpt Table 4(a) shows a skill imported from a
stronger model beating one re-optimised on the target."* The full table
(`papers/2605.23904-skillopt.pdf` Table 4(a)) `[TBL]`:

| Benchmark | Target | Baseline | **Direct** (re-optimised on target) | **Transferred** (imported) |
|---|---|---|---|---|
| SpreadsheetBench | GPT-5.4-mini | 36.1 | **47.5** | 45.5 |
| SpreadsheetBench | GPT-5.4-nano | 23.5 | **42.5** | 26.5 |
| LiveMath | GPT-5.4-mini | 14.7 | **32.8** | 19.2 |
| LiveMath | GPT-5.4-nano | 23.2 | 27.2 | **28.8** |

Local re-optimisation wins **3 of 4**, by up to **16.0 pp** (Spreadsheet nano: 42.5 vs
26.5) `[DER]`. The paper's own summary of the table is *"the remaining cross-model rows
still recover a useful fraction of the in-domain gain"* and *"no row falls below the
target's no-skill baseline."*

**Correct reading:** bundle import is a **safe fallback** (never below baseline, 4/4) but is
**usually inferior** to optimising locally. RES-7b's justification text is therefore wrong,
and §4.4a's recommendation to prefer import over running the local loop is contradicted by
the same table it cites.

---

## 2. What the corpus actually says: the gate is on the loop, not the reflector

### 2.1 The decisive experiment — SkillOpt Table 5 `[TBL]`

The only controlled optimiser-strength ablation in the corpus. Same loop, same rollout
batches, same validation gate, same bounded edit budget, same rejected-edit buffer, same
slow/meta update — **only the optimizer model varies**, between a strong frontier optimizer
(GPT-5.5) and a **target-matched** optimizer that *shares the target model*. That
target-matched arm is precisely PACT's D17 configuration.

| Benchmark | Target | Baseline | Strong optimizer | **Target-matched** | recovery |
|---|---|---|---|---|---|
| SpreadsheetBench | GPT-5.4-mini | 36.1 | 47.5 (+11.4) | 43.2 (**+7.1**) | 62% |
| SpreadsheetBench | GPT-5.4-nano | 23.5 | 42.5 (+19.0) | 35.4 (**+11.9**) | 63% |
| SearchQA | GPT-5.4-mini | 75.9 | 80.2 (+4.3) | 78.3 (**+2.4**) | 56% |
| SearchQA | GPT-5.4-nano | 55.8 | 74.8 (+19.0) | 69.9 (**+14.1**) | 74% |

(recovery column `[DER]`.) The paper's two stated observations:

> "First, the stronger optimizer produces larger absolute gains on every (benchmark, target)
> cell we test… **The bounded-edit, validation-gated loop is what makes this monotone:
> without the gate, a stronger optimizer could just as easily push larger but harmful
> rewrites.** Second, the target-matched optimizer is **far from collapsed** — it recovers
> 56–74% of the strong-optimizer gain across the four cells, confirming that SkillOpt is not
> a distillation pipeline from a stronger teacher into a weaker student."

**Consequence for §13.9b.** Its headline — *"Air-gapped optimisation EFFICACY is worse than
unproven — it is measured negative"* — is falsified by the only measurement that controls
for everything except the reflector. Expected gain for a self-reflecting target is measured
**positive in 4/4 cells, between +2.4 and +14.1 pp**.

**Consequence for §4.4a.** A gate whose default action is *refuse to invoke RES-8* would
have refused all four of these configurations. Under D11 that converts a recoverable FAIL
into a permanent one.

### 2.2 Harm tracks the absence of an accept gate — source-verified `[SRC]`

The −24.0 / −15.3 / −11.8 pp cells §4.4a attributes to weak reflectors are **all TextGrad**,
and TextGrad has no accept gate at all.

`research/repos/optim/textgrad/textgrad/optimizer/optimizer.py:168-193` —
`TextualGradientDescent.step()`:

```python
def step(self):
    for parameter in self.parameters:
        prompt_update_parameter = self._update_prompt(parameter)
        new_text = self.engine(prompt_update_parameter, system_prompt=self.optimizer_system_prompt)
        ...
        parameter.set_value(new_value)
```

The value is set **unconditionally**. `grep -rn "revert|validation|rollback"` over
`textgrad/` returns two hits, both dataset-split names in `tasks/gsm8k.py` and
`tasks/mmlu.py` — there is no acceptance criterion, no validation check and no revert
anywhere in `textgrad/optimizer/`. `[SRC]`

Now compare, in the **same table, same weak targets** (SkillOpt Table 1) `[TBL]`:

| Target | Method | Worst cell |
|---|---|---|
| Qwen3.6-35B-A3B | **TextGrad** (ungated) | LiveMath 31.2 → **7.2** (−24.0); Spreadsheet 38.2 → 22.9 (−15.3); OfficeQA 45.9 → 33.7 (−12.2) |
| Qwen3.6-35B-A3B | GEPA (gated) | OfficeQA 45.9 → 43.6 (**−2.3**) |
| Qwen3.5-4B | **TextGrad** (ungated) | LiveMath 22.4 → **10.6** (−11.8); SearchQA 68.1 → 60.7 (−7.4) |
| Qwen3.5-4B | GEPA (gated) | DocVQA 86.9 → 85.1 (**−1.8**) |
| Qwen3.5-4B | SkillOpt (gated) | no negative cell; worst is DocVQA +2.1 |

On the weakest model in the paper (Qwen3.5-4B), the gated methods produce **no cell worse
than −1.8** while the ungated one produces −11.8. `[DER]`

Third independent confirmation, ACE Table 17 — an **explicitly adversarial** reflector
instructed to inject harmful bullets, invoked once every X steps `[TBL]`:

| Harmful-reflector frequency | Accuracy (base 70.7) |
|---|---|
| every 1 iteration | 66.7 (−4.0) |
| every 5 | 76.1 (**+5.4**) |
| every 10 | 77.0 (+6.3) |
| none | 78.3 (+7.6) |

An actively malicious reflector at 20% duty cycle still nets **+5.4** because the Curator
gate absorbs it. ACE's own conclusion: *"ACE's update mechanism tolerates substantial noise
in the reflection stream, with failures emerging only under intentionally adversarial
conditions."*

**PACT already has the gate.** RES-8 re-verifies on held-out, `keep-only-if:
scores-higher-on-evals` maps to OBL-2/OBL-3, and §8.5 mounts held-out only into the
eval-runner process. So the regression risk the competence gate was invented to prevent is
handled elsewhere in the architecture. What remains is a **budget** question — which is
where §13.9 started, before §13.9b escalated it to an efficacy question on faulty evidence.

### 2.3 The one surviving negative has a gate-size mechanism, not a reflector mechanism `[SRC]`

GEPA scoring 59.41 against a 62.5 baseline on Llama-3.3-70B (ACE Table 9) is real and
survives. Its mechanism is source-verifiable:

- `research/repos/optim/gepa/src/gepa/strategies/acceptance.py:44-53` —
  `StrictImprovementAcceptance.should_accept` is `sum(subsample_scores_after) >
  sum(subsample_scores_before)`, and it is *"the default acceptance criterion used by
  GEPA."*
- `research/repos/optim/gepa/src/gepa/api.py:355` —
  `EpochShuffledBatchSampler(minibatch_size=reflection_minibatch_size or 3, …)`. The default
  accept gate is **three examples**.

PACT's own §6.9-A arithmetic applies directly: a *perfect* n=8 Clopper–Pearson one-sided 95%
lower bound is 0.6877; n=3 certifies essentially nothing. A 3-example accept gate
false-accepts at high rate; final Pareto selection then happens on the validation set and
the selected candidate regresses on test. `[INF, but the two source facts and the §6.9-A
table are not inferences]`

**This is a better-evidenced and far cheaper intervention than a reflector competence gate:
put a minimum-n on the optimiser's accept gate.** It is currently unspecified in §8.8.

### 2.4 Format compliance is the first failure mode of a weak reflector `[SRC]`

- `textgrad/textgrad/optimizer/optimizer.py:180-185` raises `IndexError` when the
  new-variable tags cannot be found, with the message: *"This can happen if the optimizer
  model cannot follow the instructions. **You can try using a stronger model**…"* — a hard
  crash, from the library's own author, attributed to weak-model format failure.
- `gepa/src/gepa/strategies/instruction_proposal.py:124-153` — GEPA's `output_extractor`
  degrades instead: with no fence it returns whatever prose it finds, so a chatty refusal
  becomes the new instruction.
- `opencompass/opencompass/openicl/icl_evaluator/icl_judge_evaluator.py:12-33` — the
  reference meta-benchmark scorer increments `count` **before** checking parseability, so an
  unparseable answer counts as **wrong** rather than being dropped. That is the correct
  treatment and reflect-bench must copy it.

⇒ format compliance is a first-class, separately-reported track, and non-compliance counts
as failure.

---

## 3. What to build: `reflect-bench` v1

### 3.1 The target statistic already has a name in the literature `[TBL]`

MetaSkill-Evolve (`papers/2607.05297-metaskill-evolve.pdf` §3.2, Eq. 3) defines
**meta-productivity**:

> `P(m | s) = E[ (1/K) Σ_{k=1..K} U(s'_k) − U(s) ]`
> "the expected per-child improvement over K proposals, estimated per node by the empirical
> mean `P̂_v = ΔU_children of v` (zero for nodes with no children)."

and its archive rule:

> "A child enters the archive only when it **strictly improves** on its parent, `ΔU_v > 0`.
> Accuracy-neutral or regressing children are not eligible to be selected as parents, but
> are still persisted… so a neutral or failed edit can still inform a later proposal."

This is exactly the quantity a competence gate should estimate: **expected per-proposal
improvement**, decomposable into *yield* (fraction of proposals clearing the gate) × *mean
accepted Δ*. It is not a competence score, and PACT should stop calling it one.

Corroborating magnitudes for what a realistic yield looks like — SkillOpt Table 6 `[TBL]`:
accepted edits per benchmark are **1–4 (median 2.5)**; LiveMath's +29.3 pp and OfficeQA's
+39.0 pp each came from a **single** accepted edit; final skills are 379–1,995 tokens
(median ~920). The paper: *"the optimizer model proposes many more edits per epoch, but only
a handful pass the held-out check… This is direct evidence that the validation gate is doing
real work."*

### 3.2 The reflector's interface is already standardised, so the fixture format is not an invention `[SRC]`

- `gepa/src/gepa/core/adapter.py:47-77` — `ProposalFn.__call__(candidate: dict[str,str],
  reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]], components_to_update:
  list[str], *, metadata) -> dict[str,str]`. Identical in shape to PACT's §8.8 optimiser ABI
  (`candidate = dict[str,str]`, requirement 1).
- `gepa/tests/test_reflection_lm.py:45-46` — the reflective-dataset record is
  `{"Inputs": …, "Generated Outputs": …, "Feedback": …}`.
- `gepa/src/gepa/strategies/instruction_proposal.py:13-42` — the default proposal prompt
  takes exactly `<curr_param>` (current component text) and `<side_info>` (rendered
  reflective dataset) and returns fenced text; `validate_prompt_template` enforces both
  placeholders.

A reflect-bench fixture therefore serialises exactly: `(component text, reflective dataset
records, components_to_update)`. A "reflector under test" is any `ProposalFn`.

### 3.3 Structural prior art for the benchmark shape `[SRC/TBL]`

**Frozen-pair discriminative meta-benchmarks, scored with zero LLM calls.** OpenCompass ships
JudgeBench and RewardBench as `(prompt, chosen, rejected, winner)` tuples
(`opencompass/opencompass/datasets/judge/judgebench.py:29-55`; the loader swaps A/B so the
gold letter matches the arranged position) scored by
`opencompass/openicl/icl_evaluator/icl_judge_evaluator.py:12-33` — pure string extraction and
exact match, no model in the scorer. This is the only meta-benchmark family in the 141-repo
corpus and it is the exact shape of reflect-bench's cheap track. **One hazard:** position
balance is inherited from the source `winner` field rather than constructed, so reflect-bench
must present every item in both orders and report order-sensitivity.

**Construction and auditability discipline.** SkillResolve-Bench 1.0
(`papers/2606.10388-skillresolve-bench.pdf` §1, §Contributions) ships 661 labelled pairs with
source-role and admission evidence, a **risk taxonomy**, **cue/leakage checks**,
**query-disjoint splits**, released **hashes**, a fixed 7,982-candidate pool, and held-out
outputs. That is the checklist reflect-bench must meet to be citable rather than
self-serving.

### 3.4 The design

`reflect-bench` is **a PACT eval suite over frozen fixtures**, authored in the existing
`pact:` deterministic assertion family (§6.3: `contains-all`, `contains-any`, `regex`,
`one-of`, `word-count`, `similarity`). Dogfooding, no new scorer engine, no code, D14-clean.

Four mandatory tracks (all executor-free at scoring time) plus one optional anchor track.

| Track | What the reflector is asked | Scored by | Executor calls | Reflector calls |
|---|---|---|---|---|
| **RB-A `discriminate`** | Given seed + frozen reflective dataset + **K candidate edits with pre-measured held-out Δ**, rank them | exact match on the argmax + Kendall-τ vs the pre-measured order | 0 | 2N (both orders) |
| **RB-B `propose`** | The real `ProposalFn` call: free-form replacement component text | per-fixture rubric of `pact:` assertions — **required** propositions (disjunctive regex sets), **forbidden** propositions (the known destructive edits), length/structure bounds | 0 | N |
| **RB-C `do-no-harm`** | Same, but the seed is already at ceiling and the frozen feedback is *distractor* (failures caused by ambiguous ground truth, not by the artifact) | fraction of items where the proposal deletes or contradicts a proposition already present and required in the seed | 0 | N |
| **RB-D `format`** | (derived from A–C) | fraction of calls yielding a parseable artifact under the reference extractor; unparseable counts as **failure**, never dropped | 0 | 0 |
| **RB-E `yield`** *(optional, the calibration anchor)* | run the real gated loop on M frozen PACT reference agents at a fixed budget | accepted edits and held-out Δ, i.e. `P̂` (Eq. 3) | many | many |

**Why RB-B can be executor-free.** The known-good improvement in every measured system is a
*single stated rule*, and the rule is publishable prose. SkillOpt Figure 4 prints them
verbatim `[TBL]`, e.g. SpreadsheetBench: *"Inspect workbook structure and formulas, then
write evaluated static values across the full requested target range instead of relying on
Excel recalculation"*; LiveMath: *"In strongest-statement MCQs, rank choices by theorem
strength and prefer a justified stronger-result option over true but weaker corollaries."*
Whether a proposal states that rule is decidable by deterministic assertions.

**RB-B is one-sided and must be reported as such.** It can only credit *rediscovery of the
known-good rule*; it cannot credit a novel, different, better rule. RB-B is therefore a
**lower bound** on proposal quality, and the bias is toward refusal.

**Baselines and normalisation.** Every track runs against three shipped baselines on the
same fixtures:

- `noop` — return the seed unchanged. By construction RB-A = chance, RB-B = 0, RB-C = 1.
- `paraphrase` — a fixed, **model-free** lexical paraphraser shipped as a program. Detects
  fixtures a reflector can pass by rewording alone.
- `oracle` — the known-good edit. RB-A = RB-B = RB-C = 1.

Normalised: `r = (s − s_noop) / (s_oracle − s_noop)`, with a Clopper–Pearson interval over
**items** (never item × repeat), computed by §6.9's single `verdict()` function so the gate
cannot render a number the interval does not support.

### 3.5 The gate, re-specified — four outcomes, no absolute threshold

The refusal point becomes *"not measurably better than doing nothing on fixtures where
doing something is known to work"*, which requires **no cross-model calibration table**.

1. **REFUSE RES-8** when the 95% interval on `r` **contains or lies below 0** on RB-B *and*
   RB-A. Recommend RES-7b import — stated honestly as a *fallback that is usually inferior
   to local optimisation* (§1.3), not as a superior path.
2. **REFUSE** when RB-D is below the profile's format floor (builtin `0.90`), naming format
   as the reason. An unparseable proposal cannot reach the accept gate at all (§2.4).
3. **Do NOT refuse on RB-C.** A low do-no-harm score is a *loop-configuration* finding
   (§2.2), so the response is loop configuration: force bounded-edit, raise the accept-gate
   min-n, force `may-also-change: []`, drop the auto-apply ceiling. Never a refusal.
4. **Otherwise RUN, with the budget sized from `r̂`**: `evals_effective = ceil(evals_budget ×
   r̂)`, printing the expected yield. Spend proportional to measured competence rather than
   all-or-nothing.

**The `0.40` threshold in R3 is deleted.** It was not derived from any measurement, and
under it the resolver would have refused every cell of SkillOpt Table 5.

### 3.6 The calibration protocol, for anyone who wants an absolute τ

Copy SkillOpt Table 5's design exactly:

- **CAL-1** Hold loop, gate, budget, batches, edit bound and rejected-edit buffer fixed.
  Vary **only** the reflector binding.
- **CAL-2** ≥ M reflector models spanning the local range × ≥ K frozen PACT reference agents.
- **CAL-3** For each cell record `(r, RB-D, P̂, held-out Δ, accepted edits, evals spent)`.
- **CAL-4** Regress RB-E's held-out Δ on the RB-A/B/C composite `r`. Publish
  `(n, slope, R², residual sd)` **with every printed τ**. A τ without them is unusable, by
  the same rule §4.2 applies to catalogue benchmark figures.
- **CAL-5** τ := the smallest `r` whose one-sided 95% **predicted-gain lower bound** exceeds
  zero. Until `n` reaches the profile's minimum, **τ is `unset`** and only the §3.5 zero-floor
  rule applies.

**PACT v1 ships with n = 0 and therefore with no absolute τ.** Every `reflect-bench:` figure
currently in the document (`0.44` in §4.6, `0.21` in §11.10) is a placeholder and must be
labelled as one.

### 3.7 Fixture-construction requirements (adopted from SkillResolve-Bench)

- **FX-1** ≥ 60 items per track, each with a *measured* held-out Δ for its known-good edit
  and for every distractor candidate, obtained under the same loop and gate.
- **FX-2** Every item carries provenance: source agent, seed digest, trace digest, the
  measurement run id, and the executor the Δ was measured on.
- **FX-3** Cue/leakage checks: no item may be solvable from the seed alone (verified by
  running the reflector with the reflective dataset blanked) and no required proposition may
  be lexically present in the feedback text (verified by the `paraphrase` baseline scoring
  at chance).
- **FX-4** Agent-disjoint splits: `public` (shipped, hashed) and `sealed` (hashes published,
  content withheld) — because a published meta-benchmark becomes training data.
- **FX-5** Both presentation orders for every RB-A item; order-sensitivity reported, never
  averaged away.
- **FX-6** Cost bound: the whole mandatory suite must cost **< 1%** of the `evals:` budget it
  gates. At 60 items × 3 tracks × ~2 calls that is ~400 reflector calls against a 2000-eval
  budget whose unit is a full suite run — comfortably inside `[DER, INF]`.

---

## 4. Residual uncertainty — what this does not close

1. **Proxy validity is unmeasured, and nothing in the corpus measures it for anything.**
   No paper in the 141-repo corpus or the 53-paper set measures whether a cheap
   propose-and-improve proxy predicts downstream optimisation gain. RB-A/B/C → RB-E is a
   **bet**, and it must be carried as a numbered hypothesis with RB-E as its falsifier.
2. **No data point exists for a small open-weight local reflector under a gated loop.**
   SkillOpt Table 5's target-matched arm is GPT-5.4-mini/nano — hosted models of undisclosed
   size. Extrapolating "target-matched nano works" to "qwen3-14b works" is `[INF]`. This is
   the honest residual of §13.9b: not *measured negative*, but *unmeasured at PACT's actual
   operating point*.
3. **RB-B's one-sidedness biases toward refusal.** Safe only because refusal is cheap under
   D11 — RES-9 still runs and still recommends. If refusal ever becomes expensive, RB-B must
   be replaced by RB-E.
4. **The economics question of §13.9 is untouched.** GEPA needs 1,839–7,051 rollouts per
   task; nobody has published wall-clock or GPU cost against a locally hosted model.
   reflect-bench sizes the budget; it does not tell you whether the budget is affordable.
5. **Contamination.** Once published, reflect-bench fixtures enter training corpora.
   FX-4's sealed split is the mitigation and it degrades over time; the calibration table
   must record the fixture-set version alongside every τ.
6. **`similarity` in the RB-B rubric is the one non-deterministic assertion** in the `pact:`
   family (it implies an embedder). RB-B rubrics should prefer `contains-all` /
   `contains-any` / `regex` / `one-of`, and any fixture that needs `similarity` must be
   flagged, because it reintroduces a model into a scorer that is otherwise model-free.

---

## 5. Applied to `20-ARCHITECTURE-DRAFT.md`

| Edit | Section |
|---|---|
| §4.4a rewritten: evidence corrected (§1.1–1.3), gate respecified to four outcomes with a zero-floor refusal, absolute τ deleted | `### 4.4a` |
| RES-7b's justification corrected — import is a fallback, usually inferior to local re-optimisation | `### 4.4 RES-7b` |
| New `### 6.5b reflect-bench` — the shipped meta-benchmark, tracks, baselines, normalisation, fixture requirements, calibration protocol | after `### 6.5a` |
| §8.7's reflector paragraph: ACE Table 16 and SkillOpt Table 5 added; the gate-vs-reflector finding stated | `### 8.7` |
| §8.8: new normative accept-gate minimum-n requirement, from GEPA's default of 3 vs §6.9-A | `### 8.8` |
| §13.9b retitled and rewritten: the "measured negative" claim is withdrawn and replaced by the honest residual (item 2 above) | `### 13.9b` |
| §4.6 lockfile: `reflect-bench` scalar → a record with tracks, fixture-set digest and interval; marked placeholder | `### 4.6` |
| §11.10 worked output rewritten to the new semantics (budget-sizing, not refusal) | `### 11.10` |
| §12.3: reflect-bench + RB-E calibration added as a continuous benchmark | `### 12.3` |
| §14.1: new hypothesis H32 (proxy validity) with RB-E as falsifier | `### 14.1` |
| §0.0 changelog: X30 | `## 0.0` |
