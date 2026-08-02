# gap-r2-1 — The sign of the capability-gap synergy law `S(G)`

**Status: CLOSED.** The paper was re-extracted with `pdftotext -layout` and Proposition 6,
Eq. (4)/(49)/(50), Table 8 and the ±3.4% aggregate were all read directly. The gap is
resolvable and the answer is: **the attacker is right about the direction and wrong about
the arithmetic sign; R1–R4 and `00-THESIS.md:633` cite the wrong law entirely.**

Source: `/home/bud/ditto/gaia-ai-runtime/research/papers/2605.16508-skill-scaling-laws.pdf`
— *The Scaling Laws of Skills in LLM Agent Systems*, Evolvent AI Team, arXiv:2605.16508v1,
15 May 2026. All page numbers below are PDF pages, verified per-page with
`pdftotext -layout -f P -l P`. Working extraction:
`<scratchpad>/skill-scaling.txt` (2949 lines, regenerable in one command).

---

## 1. What the paper actually says (verified, verbatim)

### 1a. The arithmetic sign is exactly as written. Prop. 6 does **not** flip it.

**p.26, Proposition 6 (Strong-tie promotion threshold)** — verbatim:

> Let joint execution have crowding cost `c(G)` that decreases approximately linearly with
> capability gap in the weak-tie regime, and scaffold benefit `h(G)` that is zero below a
> threshold `G*` and saturates above it:
> `c(G) = (c₀ − c₁G)₊`, `h(G) = h_max(1 − e^{−(G−G*)/τ})·𝟙{G ≥ G*}`.  (50)
> **Then the net synergy `S(G) = h(G) − c(G)` is negative-but-increasing below `G*`** and
> becomes positive-saturating once the scaffold benefit exceeds the residual cost, matching
> the empirical form in Law 12 in main text.

Proof body, same page: *"For `G < G*`, `h(G) = 0`, so `S(G) = −c₀ + c₁G` … a shallow
negative line whenever `0 < c₁G < c₀`."*

So `−c₀ = −0.0775` and `c₁ = 0.31`. **Prop. 6 states `S < 0` below `G*`, in agreement with
Eq. (4).** The attacker's hypothesis that Prop. 6 implies the *opposite arithmetic sign* is
**refuted**. Recorded as a negative finding.

Eq. (4) itself, **p.9 §4.3** (and repeated identically as Eq. (49), **p.25**, "L12"):

```
             ⎧ −0.0775 + 0.31·G                 G < G* ≈ 0.25   (Weak-Tie)
S(G)  ≈      ⎨
             ⎩ +0.265·(1 − e^{−(G−G*)/0.12})    G ≥ G*          (Strong-Tie)
```

Fig. 6(c), p.9: x-axis "Capability Gap `G` (`Acc(A) − Acc(B)`)", y-axis "Δ Overall Rubric
Score (%)", regions labelled "Weak-Tie Drag" (below `G*`) and "Strong-Tie Promotion",
"Theoretical Fit: R²=0.79".

### 1b. But `S` is the synergy of **joining**, so `S < 0` argues for keeping steps **separate**

This is the part R1–R4 got backwards, and the attacker's semantic reading is **correct**.

* **The counterfactual baseline is independent execution of the same two steps.** p.38,
  §D.1: *"its observed joint success `Acc(A,B)` is compared with `Acc(A)Acc(B)` through
  `Δ = Acc(A,B) − Acc(A)Acc(B)`"*; and *"rescue ratio is measured as the realized joint
  success divided by the product baseline"*. p.4 §2: *"We compare joint success to the
  multiplicative baseline implied by independent routing."* The p.38 capability-gap
  paragraph calls the quantity **"product synergy"**.
* **`c` is a cost incurred BY joining.** Prop. 6, p.26: *"Let **joint execution** have
  crowding cost `c(G)`…"*. Nothing in the paper assigns a cost to *splitting*.
* **`A` and `B` are two steps of an already-decomposed pipeline, not one step vs. two.**
  p.4 §2: *"in two-step analyses, `A` denotes the upstream step and `B` the downstream
  step"*. p.38: *"The execution-state experiments use ordered two-skill pairs from
  annotated pipelines."* **The paper never runs a monolithic-vs-decomposed comparison.**
* **The paper's own deployment rule points the other way.** Table 8, p.39, row
  *Execution-state propagation*, Rule column — verbatim: *"Runtime context gating and
  closure checks: **prefer loose dependency between steps**; when joint execution is
  needed, pair skills across a sufficient capability gap rather than as weak-tie peers."*
  Mechanism column: *"strong-tie pairs promote weaker steps once `G ≥ G*`, while weak-tie
  pairs create drag."*

**Therefore:** `S(G) < 0` for `G < G*` means *coupling/merging two similar-capability steps
underperforms running them independently*. Read as a design rule it says **"do not fuse
weak-tie peers"** — it is an argument *for* separation below `G*`, not against it. It is
**not** evidence that "decomposition is harmful below a capability gap of 0.25".

### 1c. The weak-tie regime is not empirically established; the paper disclaims the closed form

p.38, §D.1 *Wrong-state and capability-gap robustness* — verbatim:

> Across 11 models and 253 model-pair summaries, large-gap pairs have positive product
> synergy (**+25.2% on average, CI half-width 11.6%**), whereas small-gap pairs are near
> zero (**+1.5%, CI half-width 3.4%**). The sign is model-stable in the large-gap regime
> (10 positive models, none negative). **Thus the thresholded `G` result is not used as a
> universal closed-form deployment rule**; it summarizes where positive joint execution is
> most consistently observed.

Two things follow, both verified:

1. **The small-gap aggregate is `+1.5% ± 3.4%` → 95% interval ≈ `[−1.9%, +4.9%]`.** It
   contains zero and its **point estimate is positive**. Meanwhile Eq. (4) predicts a mean
   of ≈ `−3.9%` over `G ∈ [0, 0.25]` (`−7.75%` at `G = 0`). **The pooled measurement and
   the fitted line disagree in sign in the weak-tie regime.** The `R²=0.79` fit in
   Fig. 6(c) is dominated by the large-gap arm, where the effect is 17× larger.
2. The paper itself refuses to use the threshold as a deployment rule. Any PACT gate built
   on it would be using the source more aggressively than the source permits.

The large-gap arm (`+25.2% ± 11.6%`, 10/11 models positive) is the **only** part of Law 12
that is empirically solid — and it is a claim about *when joining helps*, not about
decomposition.

### 1d. The law that actually bounds decomposition is Law 2 / Prop. 2, which R1–R4 never cited

**p.19, Proposition 2 (Pipeline compounding from context compression):**

> Let `p_N = a − b ln N` be the isolated single-step routing probability. In a route-only
> pipeline, suppose each downstream step after the first pays a compression penalty
> `0 ≤ η_N < p_N` because the prompt contains an intermediate plan state rather than the
> full original task anchor. Then strict all-correct pipeline success is
> `Acc(N,K) = p_N(p_N − η_N)^{K−1}`.  (12)
> If `η_N > 0`, then **`Acc(N,K) < p_N^K`, so pipeline success falls below independent
> repetition.**

Empirical form, **p.5** (Routing Scaling law box, §3):

> Single-step routing follows `Acc(N) = a − b ln N` with `R² > 0.97`; **each doubling costs
> ≈ 3 percentage points**. In planned route-only pipelines, the loss compounds as
> `Acc(N,K) ≈ (a − b ln N)^{γK}` with empirical exponent **`γ = 6.7b + 1.09`**. Per-step
> accuracy is U-shaped: middle steps are more error-prone than the first or last.

`γ > 1` ⇒ **every additional decomposition step costs more than an independent draw**, and
the penalty scales with the model's own routing fragility `b` — which is larger for weaker
models. *This* is the measured, sign-unambiguous cost of decomposition. It is a **depth**
law (`K`), not a capability-gap law (`G`), it is monotone (no threshold to test), and it
needs no per-step accuracy labels to state.

Supporting geometry, p.5: *"three-step routing plans fall below the accuracy predicted by
independently repeating the single-step selector"*; *"A wrong early route moves the plan
into the wrong semantic neighborhood, making later routes more likely to fail"*; the
U-shape *"locates the fragile point: middle steps inherit most plausible continuations,
while terminal steps partially recover when the final goal narrows the choice set."*

### 1e. The ">15%" tight-coupling number that §13.5 retains is itself softer in the appendix

* **p.9 §4.3 (main text, from Fig. 6(b)):** *"tight pairs lose over 15% because the required
  input is missing or incorrect. If the downstream skill does not really need it … loose
  pairs gain 2.8%."* Fig. 6(b) spans upstream rubric Perfect (1.0) → Wrong (>0.33).
* **p.38 §D.1 (pooled audit, 11 models × 68 ordered pairs, 23,739 downstream-scored rows):**
  *"Tight dependencies lose quality when the upstream artifact is wrong rather than perfect
  (**-7.2%**), while loose dependencies show a small positive difference (+2.8%) …
  Independent pairs stay near zero (-0.8%)."*
* Law 11 in the appendix law table (p.18) is stated as `ΔQ_B = −0.072κ + 0.028(1 − κ)`,
  matching the −7.2% pooled figure, and formalised as **Prop. 5, p.25**:
  `ΔQ_B(κ) = −λκ + r(1 − κ)`, *"negative for `κ > r/(λ + r)`"* ⇒ crossover at
  `κ* = 0.028/0.100 = 0.28`.
* p.38 also warns the loose-pair gain is not repair: *"The ignored-upstream rate rises in
  all three groups (about +10.5% to +14.5%), so the loose-pair gain should be read as
  bad-state rejection or fallback, not as true repair of the wrong artifact."*

So **">15%" is a figure-range headline; the defensible pooled coefficient is −7.2%**, and
it applies only to *tight* (`κ` high) couplings. §13.5's retained prior should quote the
pooled number and the `κ* ≈ 0.28` crossover, not the headline.

---

## 2. Resolution

| Claim under test | Verdict | Evidence |
|---|---|---|
| Prop. 6 gives `S(G)` the opposite arithmetic sign to Eq. (4) | **FALSE** (attacker wrong) | p.26: *"`S(G) = h(G) − c(G)` is negative-but-increasing below `G*`"* |
| `S(G)` is the synergy of **joining**, so `S < 0` favours keeping steps separate | **TRUE** (attacker right) | p.26 (`c` = crowding cost of *joint execution*); p.38 (baseline = `Acc(A)Acc(B)`); p.39 Table 8 (*"prefer loose dependency between steps"*) |
| `00-THESIS.md:633` reads Law 12 as "decomposition is harmful below `G* = 0.25`" | **WRONG LAW, WRONG DIRECTION** | The paper never compares monolithic vs. decomposed; `A`/`B` are two steps of an existing pipeline (p.4, p.38) |
| The `+1.5% ± 3.4%` weak-tie aggregate exists and contains zero | **TRUE** | p.38: interval ≈ `[−1.9%, +4.9%]`, point estimate **positive**, i.e. opposite in sign to Eq. (4)'s `≈ −3.9%` mean over the same range |
| The source disclaims the closed form as a deployment rule | **TRUE** | p.38: *"not used as a universal closed-form deployment rule"* |
| Table 8 exists and its rule is "pair across a sufficient capability gap" | **TRUE** | p.39, row *Execution-state propagation* |
| A measured, sign-unambiguous cost of decomposition exists | **TRUE, and it is a different law** | Prop. 2 p.19 (`Acc(N,K) < p_N^K`); empirical `γ = 6.7b + 1.09 > 1`, p.5 |

**Net:** the contested row is resolved by *replacing the citation*, not by adjudicating a
sign. Law 12 / `S(G)` does not belong in a "cost of decomposition" row at all. Law 2 /
Prop. 2 (`γ = 6.7b + 1.09`) does, and it is stronger evidence than the thing it replaces:
`R² > 0.97`, 15 models, 3M decisions, monotone in `K`, no threshold, no per-step labels.

---

## 3. What this changes in PACT

Nothing that §4.4b already deleted comes back. The probe stays deleted — but for a
**better and now-verified reason**, and one retained prior gets stated correctly.

1. **§13.5 / `00-THESIS.md:633` — correct, don't hedge.** The old text said "sign
   contested, PACT does not adjudicate". That understates what is now known: the sign of
   Eq. (4) is *not* in dispute, the *referent* was. `S(G)` describes **fusion of
   already-separate steps**. It must be removed from any sentence about whether to
   decompose.
2. **The decomposition cost that survives, and its shape.** `Acc(N,K) ≈ (a−b ln N)^{γK}`,
   `γ = 6.7b + 1.09 > 1` (p.5, Prop. 2 p.19). Consequences that PACT can actually use, all
   of which are *design defaults*, not resolve-time gates:
   * **Depth is the cost driver, not the gap.** Fewer steps beats more steps, all else
     equal, and the penalty is worse on weaker executors (`γ` grows with `b`, and `b` is a
     per-model fitted fragility). This is a directly usable prior for the D17 SLM-only
     regime and it needs no measurement of any sub-step.
   * **Middle steps are the fragile ones** (U-shape, p.5). Table 8 p.39's pipeline-fragility
     rule: *"reintroduce user intent at mid-chain steps; order reliable upstream steps
     before hard downstream choices."* This is a *prompt-assembly* rule PACT's harness
     lowering can implement unilaterally — re-anchor the original task at every step —
     with no author input and no probe.
   * **Library size multiplies with depth.** `p_N = a − b ln N`, ≈3pp per doubling of
     exposed skills/tools, then raised to `γK`. Tool/skill exposure discipline and
     decomposition depth are *not* independent knobs; the combined penalty is
     `(a − b ln N)^{γK}`. This is the sharpest argument in the corpus for PACT's
     per-step tool-scoping.
3. **The tight-coupling prior, stated correctly.** Not ">15%". Pooled: tight dependencies
   lose **−7.2%** on downstream quality when the upstream artifact is wrong vs. perfect;
   loose gain **+2.8%**; independent **−0.8%** (p.38). Crossover at dependency weight
   `κ* ≈ 0.28` (Prop. 5, p.25). Design consequence, unchanged in direction and now
   correctly sourced: **prefer loose coupling between steps**, and where a step genuinely
   requires an upstream artifact, that edge needs a closure check — which is exactly what
   Table 8 p.39 prescribes ("runtime context gating and closure checks").
4. **The one thing Law 12 *is* good for, if PACT ever wants it.** The large-gap arm is the
   solid half: `+25.2% ± 11.6%`, 10/11 models positive (p.38). Read as a *fusion* rule it
   says: when two adjacent steps have very different difficulty, running them as one
   coupled unit lets the easy one scaffold the hard one. That is a candidate **merge**
   heuristic for a future optimiser, gated on the same measurement problem §13.5 already
   identified (`Ĝ` is undecidable at author-scale `n`). It is **not** available in v1 and
   must not be reintroduced as a gate.

## 4. Residual uncertainty (honest)

* **`S(G)`'s exact counterfactual is under-specified in the source.** "Joint execution"
  could mean (a) a single call asked to perform both routes, or (b) a coupled two-step
  pipeline with `A`'s artifact inserted into `B`'s context. p.29 §B.5 supports both
  readings in different conditions (*"No-state execution probes present the two steps
  jointly but withhold any upstream artifact"* vs. correct-/wrong-state probes that execute
  `A` first). **This does not change the conclusion** — under either reading the negative
  term is a cost of *coupling*, and under neither reading is the alternative "one
  undecomposed step". But it does mean the large-gap `+25.2%` cannot be translated into a
  precise mechanism without contacting the authors or the artifact repo
  (`github.com/evolvent-ai/skill-laws`, p.1 — **not fetched; offline constraint D17
  respected, and not needed for this resolution**).
* **`γ = 6.7b + 1.09` is a fit over this paper's 14 software-automation domains and its
  1,141-skill library** (p.4). Whether the coefficient transfers to PACT's target
  workloads is untested. The *sign* (`γ > 1`, super-multiplicative) is what PACT relies on,
  and that follows from Prop. 2 for any `η_N > 0`, independent of the coefficient.
* **Single source.** No second paper in the corpus independently measures pipeline-depth
  compounding with this protocol. `research/notes/model-portability.md:253` pairs it with
  MASS (+2.99pp) and AgentSquare (+17.2%), which measure the *benefit* of good topology,
  not the cost of depth. The two are not in contradiction — topology search picks *which*
  decomposition, Prop. 2 prices *how deep* — but nothing in the corpus reconciles them
  quantitatively.
* **`b` is per-model and unmeasurable air-gapped without a routing sweep.** So the
  "penalty is worse on weaker models" claim is directionally usable but not quantifiable
  at PACT resolve time. It stays a design default, never a gate. This is the same
  measurement wall §13.5 already documents for `Ĝ`, and it is why point 2 above is framed
  as defaults + harness behaviour rather than as any new probe.
