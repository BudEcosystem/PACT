# Research stream: model-portability — evidence review for T4 / D11

**Date:** 2026-07-26
**Scope:** the empirical basis for PACT thesis T4 ("model portability is variant
selection followed by strategy synthesis, gated by evals"), §7.3 ("why *same
output on a smaller model* is achievable"), AC-3.1, AC-3.5, and D11 ("fail, then
recommend").
**Corpus read:** `research/repos/optim/{dspy,gepa,textgrad,trace,adalflow,promptwizard,sammo,agent-lightning,baml,guidance,outlines}`,
`research/repos/routing/{routellm,semantic-router,litellm}`, and 20 PDFs from
`/home/bud/ditto/gaia-ai-runtime/research/papers/`.
**Method:** source read before docs; PDFs extracted with `pdftotext -layout` and
read at table level. Every number below is transcribed from a table or a source
line, not from memory. Derived ratios are labelled DERIVED and the arithmetic is
shown.

## 0. Evidence classes used in this document

| Class | Meaning | Weight |
|---|---|---|
| **[SRC]** | Read from source code in the local corpus, file:line given. | Highest — it is what actually runs. |
| **[TBL]** | Transcribed from a numbered table in a local PDF. | High. |
| **[DER]** | Arithmetic I performed on [TBL] values. Shown inline. | High, but check my arithmetic. |
| **[VEN]** | Vendor/marketing claim in a repo's own docs. Not independently reproduced. | Low — flagged every time. |
| **[CIT]** | A claim a local paper attributes to a paper *not* in the local corpus. | Lowest — I did not read the primary. |

---

# 1. Q1 — What is the ACTUAL measured transfer?

The question has to be split, because the literature measures three different
things and the thesis conflates them:

- **T-A. Naive strategy transfer.** Take the strategy optimised for the big
  model, run it unchanged on the small model. *This is the operation a naive
  "portable agent format" performs.*
- **T-B. Re-optimisation on the target.** Run the optimiser again with the small
  model as executor. *This is what T4 proposes.*
- **T-C. The residual gap after T-B.** Small-model-optimised vs
  big-model-optimised. *This is what AC-3.1 is actually measuring, and nobody
  states it clearly.*

## 1.1 T-A — Naive strategy transfer, large → small (the only direct measurements)

Only **two** studies in the entire local corpus measure strong→weak strategy
transfer directly. Both are recent, both are small-N.

### SkillOpt, `papers/2605.23904-skillopt.pdf`, Table 4(a) [TBL]

A skill document optimised with GPT-5.4 as executor, then deployed unchanged on
a smaller model in the same family.

| Benchmark | Target | Target no-skill baseline | Re-optimised on target ("Direct") | Transferred unchanged | **Fraction of available gain captured by transfer [DER]** |
|---|---|---|---|---|---|
| SpreadsheetBench | GPT-5.4-mini | 36.1 | 47.5 | 45.5 | (45.5−36.1)/(47.5−36.1) = 9.4/11.4 = **82.5%** |
| SpreadsheetBench | GPT-5.4-nano | 23.5 | 42.5 | 26.5 | 3.0/19.0 = **15.8%** |
| LiveMath | GPT-5.4-mini | 14.7 | 32.8 | 19.2 | 4.5/18.1 = **24.9%** |
| LiveMath | GPT-5.4-nano | 23.2 | 27.2 | 28.8 | 5.6/4.0 = **140%** (transfer beats re-optimisation) |

**Headline numbers to quote:**
- Naive transfer captures **16% – 140%** of the gain that re-optimisation on the
  target achieves. Median of the four cells ≈ **54%**.
- Re-optimising on the target is worth up to **+16.0 absolute points** over
  transfer (SpreadsheetBench, nano: 42.5 vs 26.5).
- On one of four cells, transfer *beat* re-optimisation (LiveMath nano, 28.8 vs
  27.2) — i.e. re-optimising on a very weak executor can produce a *worse*
  artifact than importing one produced by a stronger executor. This is a
  first-order design fact: **the optimiser's own quality is bounded by the
  reflecting model**, which is why the reflection model must be separable from
  the execution model (see §4.3).
- The paper's own summary sentence is weaker than the data: "All four
  cross-model rows are positive" (line 746 of extracted text). Positive ≠
  sufficient.

### AFlow, `papers/2410.10762-aflow.pdf`, Table 2 [TBL]

A *workflow* (topology + operators) discovered with one executor, then run with
another. HumanEval pass@1, averaged over 3 runs.

| Executor \ Workflow | IO | CoT | CoT-SC | MedPrompt | MultiPersona | SelfRefine | **Ours** (searched w/ GPT-4o-mini) | **Ours\*** (searched w/ DeepSeek-V2.5) |
|---|---|---|---|---|---|---|---|---|
| GPT-4o-mini | 87.0 | 88.6 | 91.6 | 91.6 | 89.3 | 87.8 | **94.7** | 90.8 |
| DeepSeek-V2.5 | 88.6 | 89.3 | 88.6 | 88.6 | 89.3 | 90.0 | 93.9 | **94.7** |
| GPT-4o | 93.9 | 93.1 | 94.7 | 93.9 | 94.7 | 91.6 | **96.2** | 95.4 |
| Claude-3.5-sonnet | 90.8 | 92.4 | 93.9 | 91.6 | 90.8 | 89.3 | **95.4** | 94.7 |

- Worst-case transfer loss: **−3.9 pp** (GPT-4o-mini running the
  DeepSeek-searched workflow: 90.8 vs 94.7 native).
- The paper's own conclusion (extracted line 685): *"different language models
  require different workflows to achieve their optimal performance."*
- **Caveat I must state**: HumanEval is saturated in the 87–96 band here, so
  effect sizes are compressed. A −3.9 pp loss on a saturated benchmark is
  probably an underestimate of the loss on an unsaturated one.

### The direction the literature actually validates is weak → strong, not strong → weak

GEPA `papers/2507.19457-gepa.pdf` Table 2, row "GEPA-Qwen-Opt" [TBL]: prompts
optimised **entirely on Qwen3-8B** and evaluated on GPT-4.1-mini score **+9.00
aggregate** over baseline, beating MIPROv2 (+5.64), TextGrad (+6.11) and Trace
(+3.27) *which were optimised directly on GPT-4.1-mini*. The paper's
"Observation 6: cross-model generalization" is entirely about this direction.

**This is a load-bearing negative finding for the thesis.** The single most-cited
piece of evidence for "optimised strategies transfer across models" is evidence
for the direction PACT does not need. PACT needs strong → weak. In that
direction the evidence is SkillOpt Table 4(a) and AFlow Table 2, and it says
transfer is *partial and unreliable*.

## 1.2 T-B — Re-optimisation on the target (the mechanism T4 proposes)

Every optimiser in the corpus improves a small model when re-run against it.
The gains are real and large.

| System | Small executor | Benchmark set | Baseline → optimised | Δ | Source |
|---|---|---|---|---|---|
| GEPA | Qwen3-8B | 6-task aggregate | 45.23 → 54.85 | **+9.62** | gepa Table 1 [TBL] |
| GEPA | Qwen3-8B | HotpotQA | 42.33 → 62.33 | **+20.00** | gepa Table 1 |
| MASS | Gemini-1.5-flash | 8-task avg | 60.87 → 74.30 | **+13.43** | mass Table 1 [TBL] |
| MASS | Mistral-Nemo-12B | 4-task avg | 40.4 → 55.9 | **+15.5** | mass Table 5 [TBL] |
| SkillOpt | Qwen3.5-4B | 6-benchmark avg | (per-cell, avg Δ) | **+19.2** | skillopt §4.1 [TBL] |
| SkillOpt | Qwen3.5-4B | ALFWorld | 30.6 → 81.3 | **+50.7** | skillopt Table 1 |
| SkillOpt | GPT-5.4-nano | 6-benchmark avg | — | **+26.7** | skillopt §4.1 |
| ReasoningBank+MaTTS | Gemini-2.5-flash | WebArena overall SR | 40.5 → 51.8 | **+11.3** | reasoningbank Table 1 [TBL] |
| ACE | GPT-OSS-120B | AppWorld avg | 34.6 → 42.2 | **+7.6** | ace Table 5 [TBL] |
| TextGrad | gpt-3.5-turbo | Object Counting | 77.8 → 91.9 | **+14.1** | textgrad Table 3 [TBL] |
| In-repo bench 3 | deepseek-v4-flash | ticket triage (held-out) | 0.000 → 0.812 | **+0.812** | `gaia-ai-runtime/research/RESULTS.md:77` |
| PACT-relevant floor | — | — | — | — | — |

So T-B is not in doubt. **Re-optimising on the target works, and it works
better than transferring.**

## 1.3 T-C — the residual gap. This is where the thesis is at risk.

**The optimiser lifts the large model at least as much as the small one. The gap
does not close; on some suites it widens.**

### GEPA, six benchmarks, Qwen3-8B vs GPT-4.1-mini [TBL Tables 1 & 2, ratios DER]

| Benchmark | Qwen3-8B base | Qwen3-8B GEPA | mini base | mini best | small-opt / **large-base** | small-opt / **large-opt** |
|---|---|---|---|---|---|---|
| HotpotQA | 42.33 | 62.33 | 38.00 | 69.00 | 164.0% | 90.3% |
| IFBench | 36.90 | 38.61 | 47.79 | 55.95 | 80.8% | 69.0% |
| HoVer | 35.33 | 52.33 | 46.33 | 56.67 | 112.9% | 92.3% |
| PUPA | 80.82 | 91.85 | 78.57 | 96.46 | 116.9% | **95.2%** |
| AIME-2025 | 27.33 | 32.00 | 49.33 | 59.33 | 64.9% | **53.9%** |
| LiveBench-Math | 48.70 | 51.95 | 58.20 | 64.13 | 89.3% | 81.0% |
| **Aggregate** | 45.23 | 54.85 | 53.03 | 66.36 | **103.4%** | **82.7%** |

- Gap before optimisation: 53.03 − 45.23 = 7.80.
  Gap after optimisation: 66.36 − 54.85 = **11.51**. The gap **widened by 3.71
  points** [DER].
- AC-3.1's "≥95% of reference eval score" is met on **1 of 6** benchmarks if the
  reference is the *optimised* large model, and **3 of 6** if the reference is
  the *naive* large model.

### MASS, eight benchmarks, Gemini-1.5-flash vs Gemini-1.5-pro [TBL Table 1, ratios DER]

| Benchmark | flash CoT | flash+MASS | pro CoT | pro+MASS | flash-opt / pro-CoT | flash-opt / pro-MASS |
|---|---|---|---|---|---|---|
| MATH | 66.67 | 81.00 | 71.67 | 84.67 | 113.0% | 95.7% |
| DROP | 71.79 | 91.68 | 70.59 | 90.52 | 129.9% | 101.3% |
| HotpotQA | 57.82 | 66.53 | 57.43 | 69.91 | 115.8% | 95.2% |
| MuSiQue | 37.10 | 43.67 | 37.81 | 51.40 | 115.5% | 85.0% |
| 2WikiMQA | 63.40 | 76.69 | 63.39 | 73.34 | 121.0% | 104.6% |
| MBPP | 63.33 | 78.00 | 68.33 | 86.50 | 114.2% | 90.2% |
| HumanEval | 75.67 | 84.67 | 86.67 | 91.67 | **97.7%** | 92.4% |
| LCB | 51.17 | 72.17 | 66.33 | 82.33 | 108.8% | 87.7% |
| **Average** | 60.87 | 74.30 | 65.28 | 78.79 | **113.8%** | **94.3%** |

- Gap before: 65.28 − 60.87 = 4.41. Gap after: 78.79 − 74.30 = 4.49. **Unchanged**
  [DER].
- ≥95% of *optimised* large: 4 of 8. ≥95% of *naive* large: 8 of 8.

### SkillOpt, six benchmarks, Qwen3.5-4B vs GPT-5.5 [TBL Table 1, ratios DER]

| Benchmark | 4B no-skill | 4B SkillOpt | GPT-5.5 no-skill | GPT-5.5 SkillOpt | 4B-opt / 5.5-naive | 4B-opt / 5.5-opt |
|---|---|---|---|---|---|---|
| SearchQA | 68.1 | 71.2 | 77.7 | 87.3 | 91.6% | 81.6% |
| SpreadsheetBench | 9.3 | 23.9 | 41.8 | 80.7 | **57.2%** | **29.6%** |
| OfficeQA | 14.5 | 29.7 | 33.1 | 72.1 | 89.7% | 41.2% |
| DocVQA | 86.9 | 89.0 | 78.8 | 91.2 | 113.0% | **97.6%** |
| LiveMath | 22.4 | 52.0 | 37.6 | 66.9 | 138.3% | 77.7% |
| ALFWorld | 30.6 | 81.3 | 83.6 | 95.5 | 97.2% | 85.1% |
| **Average** | 38.6 | 57.85 | 58.77 | 82.28 | **98.4%** | **70.3%** |

This is the cleanest single table for the thesis, and it is double-edged:

> **A 4B model with an optimised skill reaches 98.4% of a frontier model's
> zero-shot average across six benchmarks — and only 70.3% of the frontier
> model's own optimised score. Per-benchmark it ranges from 29.6% to 113%.**

### ReasoningBank, WebArena overall SR [TBL Table 1, DER]

| Backbone | No memory | ReasoningBank | +MaTTS |
|---|---|---|---|
| Gemini-2.5-flash | 40.5 | 48.8 | 51.8 |
| Gemini-2.5-pro | 46.7 | 53.9 | 56.3 |
| Claude-3.7-sonnet | 41.7 | 46.3 | 48.8 |

Gap flash↔pro: 6.2 → 5.1 → 4.5. Slightly narrowed. flash+MaTTS (51.8) beats
pro-no-memory (46.7) by +5.1, but is 4.5 behind pro+MaTTS.

### ACE, cross-family [TBL Tables 1, 5, 9]

| Base model | Benchmark | Baseline | +ACE (best) | Δ |
|---|---|---|---|---|
| DeepSeek-V3.1 (671B MoE) | AppWorld avg | 42.4 | 59.5 | **+17.1** |
| GPT-OSS-120B | AppWorld avg | 34.6 | 42.2 | **+7.6** |
| Llama-3.3-70B-Instruct | Finance avg | 62.5 | 64.9 | **+2.4** |

Also on the Llama-3.3-70B row, **GEPA scored 59.41, i.e. −3.09 *below* the
un-optimised baseline** [TBL Table 9].

ACE's headline — *"ReAct + ACE (59.4%) matches the top-1-ranked IBM CUGA (60.3%),
a production-level GPT-4.1-based agent, despite using the much smaller
open-source model DeepSeek-V3.1"* (extracted line 458) — is the single best
quote for the thesis. **But DeepSeek-V3.1 is a 671B-parameter MoE.** "Smaller"
here means *open-weight*, not *small*. The thesis must not cite this as
SLM evidence.

## 1.4 Summary answer to Q1

1. **Naive transfer** (large-tuned strategy, small executor) recovers **16%–140%
   of the available gain, median ≈54%**, and costs up to **−3.9 pp** vs a
   natively-searched workflow. [SkillOpt T4a, AFlow T2]
2. **Re-optimisation on the target** reliably adds large absolute gains:
   **+7.6 to +50.7 pp** depending on model and task, **+9.6 to +26.7 pp** as a
   multi-benchmark average.
3. **The residual gap does not close.** Across the three suites that optimise
   *both* tiers: GEPA gap **widened** 7.80 → 11.51; MASS gap **unchanged**
   4.41 → 4.49; ReasoningBank gap **narrowed** 6.2 → 4.5. The optimiser is a
   rising tide.
4. **The realistic PACT claim is against the naive frontier baseline, not the
   optimised one.** Against the author's *hand-written* frontier strategy, an
   optimised small model reaches **98.4%** (SkillOpt 6-bench), **113.8%** (MASS
   8-bench) and **103.4%** (GEPA 6-bench) on average. Against the *optimised*
   frontier strategy it reaches **70.3% / 94.3% / 82.7%**.

---

# 2. Q2 — Mechanism ranking by measured effect size, and where each fails

Effect sizes are **not commensurable across benchmarks**; the ranking is by the
size and consistency of the gain on a *weak* executor. Cost column is my
inference from the mechanism's structure unless cited.

| # | Mechanism | Best measured gain on a weak executor | Typical | Evidence | **Where it FAILS** |
|---|---|---|---|---|---|
| 1 | **Procedural specification (trained skill documents)** | **+50.7 pp** (Qwen3.5-4B ALFWorld 30.6→81.3) | +16.6 to +19.2 pp | skillopt Table 1; skillsbench §5.1 (+16.6 pp mean over 18 model×harness configs); in-repo bench 3 (0→81.2) | Model-authored skills: **−8.1 / −11.3 / −11.5 pp** vs no-skill (skillsbench §5.1.1). Ungated libraries fall **below** the no-skill baseline (library-drift). >4 skills: +10.1 vs +19.0 for 2–3. "Comprehensive" prose: **+0.7 pp** vs +21.5 for standard length. 13/87 tasks negative, worst −7.4 pp. Weakest where pretraining already covers the domain (Math & OR +9.7, SWE +11.6, vs Natural Science +28.8). |
| 2 | **Reflective prompt/context evolution (GEPA / ACE / MASS-1PO)** | **+29.3 pp** single benchmark (GPT-5.5 LiveMath); **+20.0 pp** (Qwen3-8B HotpotQA) | +9.6 to +17.1 aggregate | gepa Tables 1–2; ace Tables 1/5; mass Table 6 | Gain **scales with the reflector's strength**: ACE +17.1 (671B) → +7.6 (120B) → +2.4 (70B), and ACE §5 says so explicitly. Optimiser **hyperparameters do not transfer across tiers**: GEPA+Merge helps GPT-4.1-mini (+13.33 agg) but on Qwen3-8B IFBench takes 38.61 → **28.23** (gepa §Obs 5). TextGrad on small models is often **destructive**: Qwen3.6-35B LiveMath 31.2 → **7.2**; Spreadsheet 38.2 → **22.9** (skillopt Table 1). GEPA below baseline on Llama-3.3-70B Finance (**−3.09**, ace Table 9). No help where priors are already strong (ace §5: HotpotQA, Game-of-24). |
| 3 | **Context discipline / hierarchical capability routing** | routing accuracy **71.3% → 91.7%**; hijack **22.4% → 4.1%** | +10 to +17 pp F1 in production | skill-scaling-laws §abstract; enterprise-routing §abstract (110 agents/584 tools, +10–11 pp F1, production study +10–17 pp on 1,435 labelled utterances); in-repo bench 2 | Buys **tokens, not accuracy**, when the catalogue is small: in-repo bench 2 FULL80 = **1.000** accuracy at 1,773 tokens vs HIER 0.900 at 259. Flat top-k is **retrieval-bound**: accuracy == gold-in-context rate **exactly** (0.650). A **confusion gap survives perfect retrieval**: enterprise oracle ceiling falls 79% → 69% at scale. Names-only routing costs **8.4 pt** vs full descriptions (in-repo bench 1). |
| 4 | **Constrained decoding / schema-aligned parsing** | **+34.4 pp** (claude-3-haiku BFCL: function-calling 57.3% → SAP 91.7%) [VEN] | +4.5 pp on strong models | baml `fern/01-guide/why-baml.mdx:349-355` [VEN]; baml BFCL blog [VEN] | **Substrate-bound, not model-bound.** `outlines/src/outlines/models/anthropic.py:120-129` — *no* output type is supported for Anthropic. `outlines/src/outlines/models/openai.py:157-167` — regex and CFG raise `TypeError`; JSON-schema only. `guidance/guidance/models/_openai_base.py:596` — `"Regex not yet supported for OpenAI"`. Full CFG/regex only on `transformers/llamacpp/vllm/sglang/mlxlm` backends. **Quality can degrade**: BAML documents gpt-5.2 returning `quantity: 1` under structured outputs where the completions API returns the correct `0.46` (`typescript2/app-website/blog-content/2025-12-14-structured-outputs-create-false-confidence.mdx`), and cites *Let Me Speak Freely* (arXiv:2408.02442) for average degradation under schema constraint [CIT]. Blocks chain-of-thought when the schema forbids free text. |
| 5 | **Verification loops / held-out gating** | Enables everything else; alone worth +3.0 pp | +1.7 to +3.1 | maestro §Results (graph+config 72.00 vs prompt-only 70.33 on HotpotQA; 59.18 vs 56.12 on IFBench); mass Table 6 (+2TO = +2.99) | LLM judges below ~70% accuracy stop helping: ReasoningBank Fig. 8 shows SR flat at 49.4–49.7 for simulated judge accuracy 100%→70%, then falling to **47.6** at 60% and 50%. Measured judge accuracy on that task was only **72.7%**. One-token judge attacks (in-repo `2507.08794`). Terminal-only rewards give no credit assignment (agent-lightning's AIR motivation). |
| 6 | **Decomposition into sub-agents / topology search** | **+2.99 pp** (MASS 2TO stage); AgentSquare +17.2% over best-known human designs on GPT-4o | +1.7 to +3.1 | mass Table 6; maestro §Results; agentsquare §abstract | **Quantitatively bounded by pipeline DEPTH.** `[CORRECTED — see gap-r2-1.md; the capability-gap threshold cited here previously is a law about JOINING steps, not splitting them, and does not apply.]` skill-scaling-laws Prop. 2 (p.19): `Acc(N,K) = p_N(p_N − η_N)^{K−1} < p_N^K` — a `K`-step pipeline scores **below** `K` independent draws — empirically `Acc(N,K) ≈ (a − b ln N)^{γK}` with `γ = 6.7b + 1.09 > 1` (p.5, `R² > 0.97`, 15 models). `γ` rises with the model's routing fragility `b`, so **decomposition costs more the weaker the executor**. Exposure and depth compound: ≈3 pp per doubling of exposed skills, then raised to `γK`. Tightly-coupled pairs lose **−7.2%** downstream quality when the upstream artifact is wrong (pooled, 23,739 rows, p.38); loose pairs gain 2.8%; sign flips at `κ* ≈ 0.28` (Prop. 5, p.25). Mid-chain steps are the fragile ones (U-shape, p.5). And a strong single multi-turn agent matches homogeneous multi-agent workflows *and* an automatically-optimised heterogeneous workflow, more cheaply via KV reuse (`2601.12307-single-agent-baseline` abstract). Meta-agent economics break even only at high volume (in-repo SYNTHESIS cites ~15k queries). |
| 7 | **Ensembling / self-consistency / best-of-N** | **+2.9 pp** (Gemini-1.5-pro SC 68.18 vs CoT 65.28) | +1.3 to +3.0 | mass Table 1; aflow Table 1 (CoT-SC 76.0 vs CoT 74.7); reasoningbank Table 1 (MaTTS k=5: +3.0 flash, +2.4 pro) | Multiplies cost by *k* for a **single-digit** gain. Useless when the model is *consistently* wrong (AIME-class). Requires a programmatic selector to be worth anything. |
| 8 | **Model routing (RouteLLM / semantic-router)** | claimed 85% cost cut at 95% GPT-4 quality [VEN] | — | routellm `README.md:14` [VEN]; metric implementation `routellm/evals/evaluate.py:77-114` [SRC] | **Not a model-portability mechanism at all.** `pct_call_metric` computes *the percentage of strong-model calls needed to reach x% of the (strong − weak) performance gap*, and `apgr_metric` normalises AUC between the weak and strong constant lines. Routing does not make the weak model better; it decides which queries still need the strong one. **Under D17 (air-gapped, SLM-only) it contributes zero.** |
| 9 | **Weight training (RL on the agent)** | **no absolute numbers published** | — | agent-lightning §4.1–4.3 | The paper reports only "reward curves" (Figures 5, 6, 7) with Llama-3.2-3B-Instruct on Spider / MuSiQue / Calc-X. **There is no table of test accuracy and no comparison against a frontier baseline anywhere in the paper.** Requires GPUs and weight access; incompatible with no-code (D14) and with closed models. |

## 2.1 The ordering inside prompt-vs-topology, quantified

MASS Table 6 (Gemini-1.5-pro, 8-task average) is the cleanest ablation in the
corpus [TBL, deltas DER]:

| Stage | Score | Δ |
|---|---|---|
| Base agent | 63.54 | — |
| + APO (agent-level prompt optimisation) | 67.44 | +3.90 |
| + 1PO (block-level prompt optimisation) | 74.56 | +7.12 |
| + 2TO (topology optimisation) | 77.55 | +2.99 |
| + 3PO (workflow-level prompt optimisation) | 78.40 | +0.85 |

**Prompt-side stages contribute +11.87 of the +14.86 total (79.9%); topology
contributes +2.99 (20.1%).** This is the quantitative form of the
"optimise text before structure" rule already in `SYNTHESIS.md` F3.

Maestro moderates but does not overturn this: on HotpotQA with gpt-4.1-mini,
config-only optimisation reaches 70.33 at **240 rollouts** vs GEPA's 69.00 at
**>6,000 rollouts**; adding graph search reaches **72.00 at 420 rollouts**
(`papers/2509.04642-maestro.pdf` §Results, lines 169–178). Graph search adds
**+1.67 pp** on HotpotQA and **+3.06 pp** on IFBench (59.18 vs 56.12) over
prompt-only.

The workflow-optimisation survey states the mechanism-level reason PACT should
keep both: *"prompt tuning alone cannot supply missing structural capabilities
such as validation, conditional routing, or intermediate decomposition"* and
warns that *"better prompts can compensate for weak topology, making a poor
scaffold look competitive while increasing cost and reducing robustness"*
(`papers/2603.22386-workflow-opt-survey.txt` §3.2, §3.3).

---

# 3. Q3 — The honest ceiling: task classes no strategy rescues

Five classes, each with a measurement.

### C1 — Competition mathematics and multi-step exact arithmetic

| Evidence | Small model | Optimised | Frontier naive | Frontier optimised | Ratio |
|---|---|---|---|---|---|
| GEPA AIME-2025 | Qwen3-8B 27.33 | 32.00 | 49.33 | 59.33 | **53.9%** of optimised |
| MASS MATH | Mistral-Nemo-12B 13.3 | 43.7 | 71.67 (pro CoT) | 84.67 | **51.6%** of optimised, **61.0%** of naive |
| SkillOpt LiveMath | GPT-5.4-nano 23.2 | 27.2 | 37.6 (GPT-5.5) | 66.9 | **40.7%** of optimised |

On AIME the gap **widened** under optimisation (22.0 → 27.3). On MASS-MATH the
optimiser tripled the 12B model's score and still left it at 61% of the
frontier's *un-optimised* score. **No mechanism in the corpus closes this.**

### C2 — Long-horizon, tightly-coupled procedural tool work with strict output contracts

SkillOpt SpreadsheetBench is the worst cell in the entire corpus: Qwen3.5-4B
9.3 → 23.9 against GPT-5.5's 41.8 → 80.7, i.e. **29.6% of the optimised
frontier and 57.2% of the naive frontier** — after the strongest skill-training
method published. GPT-5.4-nano transfer captures only 15.8% of the available
gain on the same benchmark.

The skill-scaling-laws execution law explains the mechanism: in tightly-coupled
step pairs, a wrong upstream state propagates and the pair **loses >15%**; only
loosely-coupled pairs can ignore a bad upstream result (+2.8%).

### C3 — Cross-site / cross-domain compositional agentic tasks

ReasoningBank Table 1, WebArena "Multi" subset (29 tasks, requires transferring
memory across sites):

| Backbone | No memory | Synapse | AWM | ReasoningBank | +MaTTS |
|---|---|---|---|---|---|
| Gemini-2.5-flash | 10.3 | 10.3 | **3.4** | 13.8 | 17.2 |
| Gemini-2.5-pro | 6.9 | 6.9 | **3.4** | 13.8 | 20.7 |
| Claude-3.7-sonnet | **0.0** | 0.0 | 0.0 | 3.4 | 10.3 |

Everything is near the floor; a *strong* model (Claude-3.7) scores **0.0**
without memory; a memory mechanism (AWM) *halves* flash's score. This is the
class where the contract is most likely to be unsatisfiable by any strategy on
any tier.

### C4 — Tasks where the deficit is a missing capability, not a missing procedure

SkillsBench domain breakdown [TBL Table 3]: Natural Science **+28.8**, Media
**+24.1**, Cybersecurity **+18.9**, Industrial **+15.7**, Finance **+14.2**,
Office **+12.6**, Software Engineering **+11.6**, Mathematics & OR **+9.7**.
The paper's reading: gains are largest where the procedure is
*underrepresented in pretraining*, smallest where the model already has the
capability. Conversely, where the model *lacks the capability* rather than the
procedure, ACE states the limit directly: *"In domain-specific tasks where no
model can extract useful insights, the resulting context will naturally lack
them"* (`ace` §5).

### C5 — Anything where the optimiser must itself run on the weak model

This is the class the thesis does not currently name, and it is the most
dangerous.

- ACE gain vs base-model strength: **+17.1 (671B) → +7.6 (120B) → +2.4 (70B)**;
  ACE §5 attributes it to "smaller or weaker models naturally generate noisier
  feedback."
- Trace `README.md:391-399`: with `gpt-4o-2024-05-13` as optimiser, the system
  *"often hallucinates even in very basic optimization problems and does not
  follow instructions"*, attributed to the optimiser's JSON output requirement.
- TextGrad on small executors is frequently destructive (skillopt Table 1:
  −24.0, −15.3, −11.8, −7.4, −6.1 pp cells).
- SkillOpt Table 4(a) LiveMath nano: a skill *imported* from a stronger model
  (28.8) beat one *re-optimised* on the nano model (27.2).

**Design consequence:** the reflection/optimiser model must be a separate,
declarable binding from the execution model, and PACT must default it to the
strongest available model, never to the target.

---

# 4. Q4 — What must a SPEC expose for an optimizer to operate on it?

This section is the actionable output. I derived the contract by reading the
four optimizer ABIs in the corpus and the two formalisms.

## 4.1 The minimal optimizer ABI, read from source

### GEPA — `research/repos/optim/gepa/src/gepa/core/adapter.py` [SRC]

```python
Candidate = dict[str, str]                                   # line 12
class EvaluationBatch:                                       # line 16
    outputs: list[RolloutOutput]                             # line 31
    scores: list[float]                                      # line 32
    trajectories: list[Trajectory] | None                    # line 33
    objective_scores: list[dict[str, float]] | None          # line 34
class GEPAAdapter(Protocol):                                 # line 81
    def evaluate(batch, candidate, capture_traces) -> EvaluationBatch   # line 143
    def make_reflective_dataset(candidate, eval_batch, components_to_update)
        -> Mapping[str, Sequence[Mapping[str, Any]]]         # line 183
    propose_new_texts: ProposalFn | None                     # line 217
```

Three requirements fall straight out:

1. **A flat, stable, addressable namespace of named text components.** The
   candidate *is* `{component_name: text}`. Anything not in that map cannot be
   optimised.
2. **The system must be instantiable from that map.** DSPy does this with
   `pred.signature = pred.signature.with_instructions(candidate[name])`
   (`dspy/teleprompt/gepa/gepa_utils.py:139-141`). PACT's loader must support
   the same: *rebuild the whole agent from the tree with a set of named text
   fields overridden*.
3. **Per-component trajectories with `Inputs / Generated Outputs / Feedback`.**
   The recommended reflective record schema is spelled out at
   `adapter.py:204-209`. Scores alone are insufficient: the whole point of the
   reflective family is that natural-language feedback carries more signal than
   scalar rewards.

Plus, from `adapter.py:134-140`: **never raise on a per-example failure**; return
a failure score *and* a trajectory containing the error message. Failures are
the highest-signal training data.

### GEPA `optimize_anything` — `src/gepa/optimize_anything.py` [SRC]

```
seed_candidate: str | Candidate | None      # 94   — single text OR named multi-component
evaluator: (candidate[, example]) -> (score: float, info: dict)   # 96, 120-125
dataset / valset / test_set                 # 98, 99, 102
objective: str                              # 100  — "short goal statement", surfaced verbatim
background: str                             # 101  — "problem statement, evaluation rules, domain notes"
config.max_evals | config.max_token_cost    # oa/config.py:36-44
```

Two things here are not in the thesis and should be:

- **`objective` and `background` are first-class.** The optimiser needs a
  natural-language statement of the goal *and* the domain rules, surfaced
  verbatim. PACT's Contract must carry these as named fields, not bury them in
  a free-text description.
- **The held-out test set is structurally isolated**, not merely by convention:
  *"the test set never enters the eval server, so engines and agents cannot see
  it"* (`optimize_anything.py:146-151`). AC-3.5's "frozen held-out split locked
  before optimisation" should be enforced the same way — by making the test
  split unreachable from the optimiser process, not by policy.

Two budgets, not one (`oa/config.py:36-44`): `max_evals` caps eval calls;
`max_token_cost` caps *the optimiser's own LLM spend* and is explicitly "**not**
an eval-budget field". PACT's optimizer ABI needs both, and a run must be
rejected if neither is set (the code warns on unbounded runs).

`reflection_lm` defaults to a named strong model independent of the task model
(`src/gepa/gepa_launcher.py:756`, `ReflectionConfig` at line 731). Confirms §3-C5.

### Agent Lightning — `agentlightning/types/resources.py` [SRC]

```python
class Resource(BaseModel):   resource_type: Any               # 36
class LLM(Resource):         endpoint, model, api_key,
                             sampling_parameters: Dict        # 43-55
class PromptTemplate(Resource): template: str,
                             engine: Literal["jinja","f-string","poml"]  # 146-152
NamedResources = Dict[str, ResourceUnion]                      # 172
class ResourcesUpdate(BaseModel):
    resources_id: str; create_time; update_time;
    version: int; resources: NamedResources                    # 192-206
```

This adds the deployment half of the contract: the optimisable surface is a
**named, typed, versioned bag of resources broadcast to executors**, where the
agent *requests a named resource* rather than embedding the text. `LLM` carries
`sampling_parameters` — so decoding parameters are part of the optimisable set,
not configuration trivia.

### AdalFlow — `adalflow/adalflow/optim/types.py:28-53` [SRC]

```python
PROMPT     = ("prompt", ..., True)      # trainable
DEMOS      = ("demos", ..., True)       # trainable
HYPERPARAM = ("hyperparam", ..., False) # NOT trainable
INPUT / OUTPUT / *_OUTPUT / LOSS_OUTPUT / SUM_OUTPUT
@dataclass EvaluationResult: score: float in [0,1]; feedback: str
```

Two lessons: (a) **each optimisable field needs a declared type and a
`trainable` flag** — the enum is literally `(name, description, default_trainable)`;
(b) **the evaluation result is a pair `(score, feedback)`**, matching GEPA. A
metric that returns only a number is unusable by a reflective optimiser.

DeepEval already satisfies this: `deepeval/metrics/base_metric.py` carries
`reason: Optional[str]` and `include_reason: bool` on all three base metric
classes (lines 49/55, 112/118, 175/179). **PACT's metric contract must require
`reason` to be populated when the metric participates in optimisation.**

### SAMMO — structural addressing and a declarative search space [SRC]

- `sammo/search_op.py:13` — `__all__ = ["one_of", "many_of", "permutate",
  "optional", ...]`. The search space is declared with combinators, not code.
- `sammo/mutators.py` — mutators are typed and named: `Paraphrase`,
  `ShortenSegment`, `SegmentToBulletPoints`, `RemoveStopWordsFromSegment`,
  `DropExamples`, `DropIntro`, `RepeatSegment`, `ChangeDataFormat`,
  `ChangeSectionsFormat`, `DecreaseInContextExamples`, `APO`, `APE`,
  `InduceInstructions`, `PruneSyntaxTree`, `BagOfMutators`.
- `sammo/css_matching.py:65` — `find_all(css_expression)` over an XmlTree built
  from `reference_id → id`, `reference_classes → class`. The README example
  targets a *markdown section* by id: `Paraphrase("#instr")`.

**This is the single most important structural finding for PACT's authoring
surface.** Prompts should be *addressable documents with stable section
anchors*, so an optimiser can rewrite one section, and a reviewer can see
exactly which section changed (which D23's blast-radius classifier requires).

### Trace / Opto [SRC]

- `opto/trace/nodes.py:10` — `node(data, name, trainable, description, constraint)`.
  Trainable parameters can be **arbitrary values with a declared `constraint`**,
  not only strings.
- `opto/trace/bundle.py:27-34` — `bundle(description, traceable_code, trainable,
  catch_execution_error, allow_external_dependencies, ...)` makes a **block of
  code** a trainable parameter. This is the D22(b) "agents author their own
  tools" capability, and it is why D22 needs sandboxing (GEPA has
  `config.sandbox` defaulting to `True`, `oa/config.py:56-60`).

### PromptWizard — the only genuinely no-code optimiser config [SRC]

`demos/gsm8k/configs/promptopt_config.yaml` is a complete optimiser
specification in YAML with no code: `prompt_technique_name`, `unique_model_id`,
`mutate_refine_iterations`, `mutation_rounds`, `refine_instruction`,
`refine_task_eg_iterations`, `style_variation`, `questions_batch_size`,
`min_correct_count`, `max_eval_batches`, `top_n`, `task_description`,
`base_instruction`, `answer_format`, `seen_set_size`, `few_shot_count`,
`num_train_examples`, `generate_reasoning`, `generate_expert_identity`,
`generate_intent_keywords`.

This is the template for PACT's no-code `optimizer:` block under D14.

## 4.2 The two formalisms

### Maestro's joint objective — `papers/2509.04642-maestro.pdf` §2 [TBL]

Node `v` is a stochastic function `F_v : X_v × c_v → Dist(Y_v)` where the node
configuration is *"model family and weights θ_v, prompt ρ_v, tool set, decoding
and control hyperparameters"*. Edges carry adapter parameters
`α_e` — *"templates, serializers, schema maps"*. Nodes carry merge parameters
`β_v` — one per incoming edge. The full configuration is

> `C := {c_v}_{v∈V} ∪ {α_e}_{e∈E} ∪ {β_v}_{v∈V}`

and the optimisation problem is

> `max_{G∈𝒢, C∈𝒞} E[μ(Y_O, m)]  s.t.  E[c(G,C;x)] ≤ κ,  Ω(G) ≤ τ,  R_train(G,C) ≤ B`

with `κ` a cost budget, `Ω(G) ≤ τ` a *structure* budget (penalties on
#nodes/#edges), `B` a rollout budget. Cycles are handled by unrolling `t=1:T`
or a fixed-point operator; conditional edges by activations `a_e ∈ {0,1}` with
merge operators that ignore absences.

**Two of these are missing from the thesis §7.2 strategy list**: edge adapter
parameters (`α_e`) and merge parameters (`β_v`). An inter-agent edge is not a
plain arrow — it is a typed transformation with tunable serialisation, and a
node with several parents needs a declared merge policy.

### The survey's three preconditions — `papers/2603.22386-workflow-opt-survey.pdf` §3.1

> *"First, there must be an executable search space, whether defined by typed
> operators, code templates, or structured workflow languages. Second,
> evaluation must be reliable enough to discriminate candidates. Third, the
> search space must embody a useful inductive bias: if candidate workflows are
> mostly invalid or semantically incoherent, black-box search quickly becomes
> prohibitively expensive. This is precisely why typed operators, code
> scaffolds, and constrained graph languages are so important in practice."*

and

> *"search quality is often limited less by the nominal optimizer than by the
> representation and evaluator it is allowed to use."*

and, on MermaidFlow/VFlow (§3.4):

> *"verification is not added after search; it is part of the optimization
> process itself."*

**This is the strongest theoretical argument for PACT's existence.** A validated,
typed spec *is* the search space. `pact validate` is not developer hygiene — it
is the operator that keeps the optimiser's proposal distribution inside the
feasible set.

## 4.3 The optimisability contract — consolidated

A spec is *optimisable* iff it exposes all of the following:

| # | Requirement | Source of the requirement |
|---|---|---|
| O-1 | **Stable, addressable names for every text component**, including sub-document anchors (section ids) so a single section can be rewritten. | gepa `adapter.py:12`; sammo `css_matching.py:65` + `Paraphrase("#instr")` |
| O-2 | **A typed `trainable` flag and a declared `constraint` per field.** | adalflow `types.py:28-41`; trace `nodes.py:10` |
| O-3 | **Instantiation from an override map**: `build(tree, {name: text}) → runnable agent`, with no source-tree edits. | dspy `gepa_utils.py:136-142` |
| O-4 | **Per-component trajectories** recording that component's inputs, its outputs, and a textual feedback string. | gepa `adapter.py:183-215` |
| O-5 | **Evaluation returns `(score: float, feedback: str)` per example**, plus optional `objective_scores: {name: float}` for multi-objective. Never raise on per-example failure — score it 0 and record the error. | gepa `adapter.py:31-34, 134-140`; adalflow `types.py:71-82`; deepeval `base_metric.py:49-55` |
| O-6 | **`objective` (short goal) and `background` (domain rules, evaluation rules) as first-class contract fields.** | gepa `optimize_anything.py:142-145` |
| O-7 | **Train / validation / test splits with the test split structurally unreachable from the optimiser.** | gepa `optimize_anything.py:146-151` |
| O-8 | **Two budgets: eval budget and optimiser-spend budget.** Reject unbounded runs. | gepa `oa/config.py:36-44` |
| O-9 | **A reflection/teacher model binding independent of the execution model.** | gepa `gepa_launcher.py:731,756`; ACE §5; Trace README:391-399 |
| O-10 | **Node config = {model, prompt, tool set, decoding params, control params}; edge config = adapter/serialiser params; node merge policy.** All addressable. | maestro §2 |
| O-11 | **Explicit budgets in the objective**: cost `κ`, structure `τ` (node/edge count), rollouts `B`. | maestro §2.2 |
| O-12 | **A declarative search space** (`oneOf` / `manyOf` / `optional` / `permutate`) over strategy fields, so a non-programmer can declare the variant space. | sammo `search_op.py:13` |
| O-13 | **A typed, statically-validatable IR** so most proposals are legal by construction. | workflow-opt-survey §3.1, §3.4 |
| O-14 | **Versioned, named resource delivery at runtime** (`resources_id`, `version`) so a new candidate can be swapped in without redeploying the agent. | agent-lightning `resources.py:172-206` |
| O-15 | **Optimiser hyperparameters declared per model tier, not globally.** | gepa §Obs 5 (Merge helps mini, hurts Qwen3-8B); skillopt Table 2(e) (LR scheduler moves SpreadsheetBench 80.7 vs 72.9) |

## 4.4 What today's leading framework does NOT expose — the gap PACT fills

DSPy's optimisable surface is exactly *the instruction string of every
`dspy.Predict` reachable by attribute path*:

- `dspy/teleprompt/gepa/gepa.py:575` — `seed_candidate = {name: pred.signature.instructions for name, pred in student.named_predictors()}`
- `dspy/primitives/module.py:131-141` — `named_predictors()` returns
  `(attribute path, Predict)` pairs.

Therefore **DSPy+GEPA cannot optimise**: the loop (`ReAct.__init__` hard-codes
`max_iters: int = 20`, `dspy/predict/react.py:17`), the tool exposure set
(`tools: list[Callable]`, same line), the model binding, decoding parameters,
the adapter/serialisation choice, or the topology.

AdalFlow declares `HYPERPARAM` but marks it `default_trainable=False`
(`types.py:41`).

**This is precisely PACT's opening.** If the loop, tool exposure, model binding,
decoding parameters and topology are *authored data in the tree* rather than
constructor arguments in code, then a single optimizer ABI can mutate all of
them. The thesis §7.2 strategy list is right; nobody can execute it today
because no framework represents those things as data.

---

# 5. Findings that contradict or weaken the thesis as written

| # | Finding | Evidence | What must change |
|---|---|---|---|
| N1 | Optimisation does **not** close the model gap. On GEPA's six benchmarks it *widened* (7.80 → 11.51). On MASS it was unchanged (4.41 → 4.49). | gepa Tables 1–2; mass Table 1 [DER] | §7.3's framing ("the strategy was tuned to a strong executor, a weaker one needs a different strategy") is only half true. Both executors benefit. AC-3.1 must name its reference point. |
| N2 | AC-3.1's "≥95% of reference eval score" is met on **1/6** (GEPA), **4/8** (MASS), **1/6** (SkillOpt) benchmarks against an *optimised* frontier reference. | §1.3 tables | Either set the reference to the *authored* frontier strategy (then it is 3/6, 8/8, 3/6) or lower the bar. As written, AC-3.1 fails on the best published evidence. |
| N3 | The published cross-model transfer evidence is **weak → strong**, not strong → weak. | gepa §Obs 6, Table 2 "GEPA-Qwen-Opt" | Do not cite GEPA's cross-model result as support for downgrade portability. |
| N4 | Optimisation gains **shrink as the executor weakens** for reflection-based methods. | ace Tables 1/5/9: +17.1 (671B) → +7.6 (120B) → +2.4 (70B); ace §5 | The optimiser is *not* an equaliser. The reflection model must be a separate binding, defaulted to the strongest available. |
| N5 | Optimiser **hyperparameters do not transfer across tiers**. GEPA+Merge: +13.33 on GPT-4.1-mini, but Qwen3-8B IFBench 38.61 → **28.23**. | gepa §Obs 5, Table 1 | Optimiser config belongs *inside* the variant, not in a global profile. |
| N6 | Ungated automatic strategy edits are **actively harmful**, up to **−29.6 pp**. | skillopt Table 1 (LLM-skill on GPT-5.4 OfficeQA 50.0→20.4; TextGrad on Qwen3.6-35B LiveMath 31.2→7.2); skillsbench self-generated −8.1/−11.3/−11.5 | The held-out gate is not a nicety; it is the difference between +50 and −30. Make refusal-to-publish the default (already T7/D23 — now quantified). |
| N7 | **ACE's flagship "small model matches GPT-4.1 agent" result uses a 671B MoE.** | ace §4.3 line 458 | Never cite it as SLM evidence. It is *open-weight* vs *closed*, not *small* vs *large*. |
| N8 | **TextGrad's headline claim is unsupported by its own table.** The abstract says "we push the performance of GPT-3.5 close to GPT-4 in several reasoning tasks"; Table 3 contains **no GPT-4 numbers**. | textgrad line 97 vs Table 3 | Do not cite TextGrad for small↔large parity. |
| N9 | **TextGrad's published numbers were not reproducible.** | trace `2406.16218` footnote 9: *"The numbers in the original paper cannot be reproduced exactly despite using the released TextGrad code."* Table 2: BBH Word Sorting reported 79.8 vs reproduced 72.0; MMLU-ML 88.4 vs 86.1 | Treat single-paper optimiser gains as upper bounds. PACT's own benchmarks must be the oracle (which is the thesis's own position — this strengthens it). |
| N10 | **Agent Lightning publishes no absolute numbers.** Reward curves only. | agent-lightning §4.1–4.3, Figures 5–7 | It is an *architecture* to copy (as `SYNTHESIS.md` F3 already says), not an evidence source. |
| N11 | **Routing is not portability.** RouteLLM's metric measures how many strong-model calls you still need. | `routellm/evals/evaluate.py:77-114` [SRC] | Keep routing out of the model-portability story under D17. It belongs to cost optimisation with a frontier model present. |
| N12 | **Constrained decoding is a property of the substrate, not the model.** Anthropic supports no output types in outlines at all; OpenAI supports JSON-schema only (no regex, no CFG); guidance refuses regex on OpenAI. | `outlines/src/outlines/models/anthropic.py:120-129`, `openai.py:157-167`; `guidance/guidance/models/_openai_base.py:596` [SRC] | The capability vocabulary must distinguish `structured_output: json_schema` from `structured_output: grammar`, and the lattice must be over **(model × provider × runtime)**, not model alone. |
| N13 | **Constrained decoding can reduce answer quality.** Documented gpt-5.2 case: structured-outputs API returns `quantity: 1`, completions API returns the correct `0.46`. | baml `2025-12-14-structured-outputs-create-false-confidence.mdx` [VEN, reproducible case] | Constrained decoding must be a *variant choice under eval*, not a default. |
| N14 | **The industry model catalogue has no quality axis.** LiteLLM's 2,984-model catalogue has `supports_*` booleans, pricing, context windows and `deprecation_date` — and **zero** benchmark/quality fields. `source` provenance covers only **921/2984 = 30.9%** of entries. | `routing/litellm/model_prices_and_context_window.json` [SRC, enumerated] | O3.2/AC-3.2/AC-3.3 cannot be satisfied by importing an existing catalogue. PACT must define and populate the quality axis itself, offline (D8/D17), and `strict` mode will reject ~69% of imported rows. |
| N15 | **LiteLLM's default remedy for capability mismatch is silent deletion.** `drop_params=True` pops unsupported parameters; otherwise `UnsupportedParamsError` is raised. | `litellm/utils.py:2874-2885` [SRC] | When PACT consumes LiteLLM (NG2), it must set `drop_params=False` and translate `UnsupportedParamsError` into a Portability Report entry. Anything else violates T7. |
| N16 **[CORRECTED — see `gap-r2-1.md`]** | ~~Decomposition has a measured negative regime. `S(G) ≈ −0.0775 + 0.31·G` for `G < 0.25`.~~ **`S(G)` is a law about JOINING two already-separate steps, not about splitting one.** Its baseline is `Acc(A)·Acc(B)`, the same two steps run independently (p.38); Prop. 6 (p.26) calls the negative term the *"crowding cost of **joint execution**"*; `A`/`B` are two steps of an already-decomposed pipeline (p.4, p.38); the paper runs **no** monolithic-vs-decomposed comparison. And the weak-tie arm is unmeasured: small-gap product synergy is **+1.5% ± 3.4%** (p.38), an interval containing zero with a *positive* point estimate, and the source disclaims the closed form as a deployment rule. **The measured cost of decomposition is a DEPTH law:** `Acc(N,K) = p_N(p_N − η_N)^{K−1} < p_N^K` (Prop. 2, p.19); empirically `Acc(N,K) ≈ (a − b ln N)^{γK}` with `γ = 6.7b + 1.09 > 1` (p.5, `R² > 0.97`). | skill-scaling-laws pp. 5, 9, 19, 25, 26, 38, 39 (re-extracted `pdftotext -layout`) | §7.3 mechanism #1 keeps a caveat, but a different one: **every extra step is priced super-multiplicatively, and the price rises as the executor weakens** (`γ` grows with routing fragility `b`). Exposed-tool count and depth multiply: `(a − b ln N)^{γK}`. Prefer loose coupling (tight edges cost −7.2% on wrong upstream state vs +2.8% loose, crossover `κ* ≈ 0.28`) and re-anchor the user task at mid-chain steps (U-shaped fragility). |
| N17 | **A strong single multi-turn agent matches optimised multi-agent workflows.** | `2601.12307-single-agent-baseline` abstract | Topology search must be volume/benefit-gated, and the single-agent baseline must be in the CTS as a control. |

---

# 6. Findings that strengthen the thesis

| # | Finding | Evidence |
|---|---|---|
| P1 | Against the **realistic** reference (the author's hand-written frontier strategy), an optimised small model averages **98.4% / 113.8% / 103.4%** across three independent 6–8-benchmark suites. | §1.3 tables [DER] |
| P2 | Procedural specification is the largest single lever on weak executors: **+50.7 pp** best case, **+16.6 pp** mean over 18 model×harness configs, and the in-repo bench 3 reproduction (0 → 81.2 from one gated edit). | skillopt Table 1; skillsbench abstract; `RESULTS.md:77` |
| P3 | **Compact beats comprehensive**: 2–3 skills +19.0 vs ≥4 +10.1; standard-length +21.5 vs comprehensive prose **+0.7**. Optimised prompts are also **up to 9.2× shorter** than MIPROv2's, and higher-scoring optimisers produce shorter prompts. | skillsbench §5.1.2 (Finding 6); gepa §Obs 4 |
| P4 | **Verification tolerates a mediocre judge.** WebArena SR is flat (49.4→49.7) for simulated judge accuracy 100%→70%; the real judge measured 72.7%. Below 60% it degrades to 47.6. | reasoningbank Fig. 8 |
| P5 | **A well-typed, statically-validatable IR is the precondition for cheap search**, not a nicety. | workflow-opt-survey §3.1, §3.4 |
| P6 | **Prompts before topology, quantified**: 79.9% of MASS's total gain is prompt-side; 20.1% topology. And a staged schedule (1PO → 2TO → 3PO) is what makes joint optimisation stable. | mass Table 6 [DER]; workflow-opt-survey §3.3 |
| P7 | **Sample efficiency of reflective evolution is very high**: GEPA matches GRPO's best validation with **102 / 32 / 6 / 179 train rollouts** on four tasks; Maestro reaches 70.33 on HotpotQA in **240 rollouts** vs GEPA's >6,000. Offline optimisation under D17 is therefore economically feasible. | gepa §Obs 1; maestro §Results |
| P8 | The independent harness-design survey converges on PACT's own control loop: `(θ_{t+1}, φ_{t+1}) = VerifyRetain(U(θ_t, φ_t, E_t))` where `φ` is the *harness configuration*, with "held-out evaluation, ablations, audit logs, rollback, and human approval for high-impact changes." | harness-design-survey §8.2 |
| P9 | The same survey supports NG3: *"protocol standardization is not the same as harness generalization. The harness must still decide what to expose, which actions to allow, how to verify outcomes and recover from failure."* | harness-design-survey §8.3 |

---

# 7. Direct implications for the PACT documents

### 7.1 AC-3.1 must be rewritten

Current: *"achieves ≥ 95% of its reference eval score on a designated small model
after variant resolution and, if needed, optimisation."*

The word **reference** is doing all the work and is undefined. Proposal:

> **AC-3.1 (revised).** Let `R_authored` be the reference agent's eval score on
> its authored (frontier) binding, and `R_optimised` its score after the same
> optimisation budget is spent on the frontier binding. A resolution to a small
> model reports **both** ratios. The pass bar is `≥ 95% of R_authored`. The
> report must additionally state `score / R_optimised` and must never present
> the `R_authored` ratio without it.

Rationale: on the best published evidence the `R_authored` bar is met on 3/6
(GEPA), 8/8 (MASS) and 3/6 (SkillOpt) benchmarks, while the `R_optimised` bar is
met on 1/6, 4/8, 1/6. A criterion that the state of the art fails five times out
of six is not an acceptance criterion; it is a wish.

### 7.2 The capability lattice must be over (model × provider × runtime)

`supports_response_schema` and grammar-constrained decoding are *different*
capabilities and they are provider-dependent, not model-dependent
(§5 N12). The vocabulary in §7.2 needs at minimum:

```yaml
structured_output: [none, json_mode, json_schema, regex, cfg]
```

with `regex`/`cfg` satisfiable only on substrates with logit access
(transformers, llama.cpp, vLLM, SGLang, MLX). Since the same model behind two
providers has two different values, the catalogue key must be
`(model_id, provider, runtime)`.

### 7.3 The optimizer ABI (O3.4 / E-5) — concrete shape

```
optimize(
  spec_tree,                       # the folder tree (D2 native form)
  components: [ComponentRef],      # O-1: addressable names incl. section anchors
  eval_suite,                      # O-5: returns (score, reason) per case
  splits: {train, val, test},      # O-7: test structurally unreachable
  objective: str, background: str, # O-6
  budgets: {evals, optimiser_cost, rollouts, structure},  # O-8, O-11
  models: {execution, reflection}, # O-9: independent bindings
  search_space,                    # O-12: oneOf/manyOf/optional/permutate
  optimiser_config                 # O-15: per-tier, lives in the variant
) -> (candidate_tree_diff, verdict, provenance)
```

### 7.4 Additions to the strategy space (§7.2)

Add, from Maestro §2 and the SkillOpt ablations:
- **edge adapter parameters** — templates, serialisers, schema maps on each
  inter-node edge;
- **merge policy per node** with more than one incoming edge;
- **structure budget** `Ω(G) ≤ τ` (max nodes / max edges) as an authored
  constraint;
- **optimiser hyperparameters as part of the variant** (learning rate,
  scheduler, batch/mini-batch size, slow-update samples) — SkillOpt Table 2(e)
  shows scheduler choice alone moves SpreadsheetBench 80.7 (constant) vs 72.9
  (linear), a **7.8-point** swing.

### 7.5 Authoring surface

`instructions.md` and every skill document must carry **stable section anchors**
(SAMMO's `#instr` pattern) so that:
- the optimiser can rewrite one section (`components_to_update` is a *list*),
- D23's blast-radius classifier can attribute a diff to a section kind
  (`## Output format` = low risk; `## Tool policy` = high risk),
- the Learning IR (O5.3) emits minimal diffs rather than whole-document
  replacements.

Skill frontmatter should additionally carry the **complexity contract**
SkillsBench proposes (§6): expected tool/token cost, applicability boundaries,
and a required lightweight fallback path — this is the direct fix for the 13/87
tasks where skills *hurt*.

### 7.6 Learning-loop defaults justified by evidence

| Default | Value | Justification |
|---|---|---|
| Reflection model | strongest available, **never** the target | §3 C5; ACE §5; gepa `ReflectionConfig` |
| Skill count per agent | cap at **3** | skillsbench Finding 6 (2–3 = +19.0; ≥4 = +10.1) |
| Skill length | "standard" (≈300–2,000 tokens) | skillsbench (+21.5 standard vs +0.7 comprehensive); in-repo bench 3 artifact = 283 words |
| Judge accuracy floor | **70%** measured on a labelled subset before a judge may gate a learning cycle | reasoningbank Fig. 8 |
| Candidate acceptance | strict improvement on a **structurally isolated** held-out split | gepa `optimize_anything.py:146-151`; N6 (ungated edits cost up to −29.6 pp) |
| Rejected candidates | retained as negative evidence | skillopt rejected-edit buffer; AC-5.5 |
| Topology search | **gated** on prompt optimisation being exhausted first, and on run volume | mass Table 6 (79.9% of gain is prompt-side); `2601.12307` single-agent baseline |
| Optimiser budget | two caps (evals, optimiser spend); refuse unbounded | gepa `oa/config.py:36-44` |

### 7.7 D11 (fail, then recommend) is well-supported and should be strengthened

The evidence supports a **richer** report than D11's example. A resolver that has
run the mechanisms knows *why* it failed, and the failure classes are
identifiable from §3:

```
PORTABILITY: FAIL for qwen3-4b
  spreadsheet_exact_match 0.239 < 0.700 required (best of 14 candidate strategies)
  FAILURE CLASS: long-horizon procedural + strict output contract
    — mechanism ceiling: skill optimisation reached 57.2% of the frontier's
      un-optimised score on the closest published analogue (SkillOpt,
      SpreadsheetBench, Qwen3.5-4B). Re-optimisation is unlikely to close this.
  MECHANISMS TRIED: skill synthesis (+14.6), tool curation (+2.1),
      constrained decoding (n/a — provider lacks grammar support),
      self-consistency k=5 (+1.8, 5.0× cost)
RECOMMENDED: qwen3-14b — passes at 0.83, 3.1× cheaper than your current binding
```

---

# 8. Open questions this review could not settle

1. **No published measurement of full strategy re-synthesis (topology +
   decomposition + tools + loop) for a downgrade.** SkillOpt varies only the
   skill; AFlow only the workflow; MASS re-runs the whole pipeline per model but
   never reports a *transfer* row. PACT's own bench must produce this.
2. **No evidence at all for downgrade portability in vision, audio, or computer
   use.** Every measurement above is text or text+tools. D16 requires all four
   modalities in v1 and the corpus is silent on three of them.
3. **The 4B/7B tier is barely represented.** The corpus's "small" models are
   Qwen3-8B, Qwen3.5-4B, Mistral-Nemo-12B, Llama-3.2-3B, gpt-3.5-turbo,
   Gemini-1.5-flash, GPT-5.4-nano. Only Qwen3.5-4B and Llama-3.2-3B are truly
   small, and Llama-3.2-3B has no absolute numbers published.
4. **Nobody has measured whether harness lowering costs accuracy.** F-4 asserts
   that harness-underperforming-native is a defect; the harness-design survey
   warns a generic harness "may provide weak inductive bias for the target
   bottleneck." This is an unmeasured risk to D12.
5. **Air-gapped optimisation economics.** GEPA needs 1,839–7,051 rollouts;
   Maestro 240–2,220. On a local model these are wall-clock costs nobody has
   published. Feasibility under D17 is inferred, not demonstrated.
6. **Is the "capability gap" `G` measurable at resolve time?** The
   skill-scaling-laws decomposition law is stated in terms of per-step accuracy,
   which requires per-step evals. Whether PACT can estimate `G` cheaply enough
   to gate decomposition automatically is untested.

---

# 9. Evidence index

## Source files read
```
research/repos/optim/gepa/src/gepa/core/adapter.py            :12,16,31-34,81,134-140,143,183-215,217
research/repos/optim/gepa/src/gepa/optimize_anything.py       :93-183 (esp. 96,100-102,120-125,142-151)
research/repos/optim/gepa/src/gepa/oa/config.py               :24-93 (esp. 36-44,56-60,61-90)
research/repos/optim/gepa/src/gepa/gepa_launcher.py           :731,751-761
research/repos/optim/dspy/dspy/teleprompt/gepa/gepa.py        :117,557,575
research/repos/optim/dspy/dspy/teleprompt/gepa/gepa_utils.py  :104-220 (esp. 136-142,196-215)
research/repos/optim/dspy/dspy/primitives/module.py           :131-141
research/repos/optim/dspy/dspy/predict/react.py               :16-17,87-88,95-98
research/repos/optim/dspy/dspy/adapters/base.py               :34,314-347,366,713
research/repos/optim/dspy/dspy/adapters/two_step_adapter.py   :15-46
research/repos/optim/dspy/dspy/adapters/baml_adapter.py       :1-60
research/repos/optim/dspy/dspy/signatures/signature.py        :224-304
research/repos/optim/adalflow/adalflow/optim/types.py         :13-82
research/repos/optim/trace/opto/trace/nodes.py                :10-42,1995
research/repos/optim/trace/opto/trace/bundle.py               :27-51
research/repos/optim/trace/README.md                          :389-399
research/repos/optim/sammo/sammo/search_op.py                 :13,75,84
research/repos/optim/sammo/sammo/mutators.py                  :29-818 (class list)
research/repos/optim/sammo/sammo/css_matching.py              :8-65
research/repos/optim/sammo/README.md                          :45-72
research/repos/optim/promptwizard/demos/gsm8k/configs/promptopt_config.yaml  (whole)
research/repos/optim/agent-lightning/agentlightning/types/resources.py :36,43-55,146-152,172,192-206
research/repos/optim/outlines/src/outlines/models/anthropic.py :118-129,176-183
research/repos/optim/outlines/src/outlines/models/openai.py    :157-181
research/repos/optim/outlines/src/outlines/models/ollama.py    :132-145
research/repos/optim/outlines/src/outlines/backends/           (outlines_core, llguidance, xgrammar)
research/repos/optim/guidance/guidance/models/_openai_base.py  :314-320,562-596
research/repos/optim/guidance/README.md                        :369-427
research/repos/optim/baml/fern/01-guide/why-baml.mdx           :339-378
research/repos/optim/baml/typescript2/app-website/blog-content/2024-08-13-bfcl-sota.mdx  :1-110
research/repos/optim/baml/typescript2/app-website/blog-content/2025-12-14-structured-outputs-create-false-confidence.mdx :1-60
research/repos/routing/routellm/routellm/evals/evaluate.py     :60-125
research/repos/routing/routellm/README.md                      :14-15,117-121
research/repos/routing/litellm/model_prices_and_context_window.json  (2,984 entries enumerated)
research/repos/routing/litellm/litellm/utils.py                :2241,2293,2480,2819-2914 (drop_params)
research/repos/routing/semantic-router/README.md               :28,121,137
research/repos/eval/deepeval/deepeval/metrics/base_metric.py   :49,55,112,118,175,179
```

## Papers read (all under `/home/bud/ditto/gaia-ai-runtime/research/papers/`)
```
2507.19457-gepa.pdf                 Tables 1,2,3; Observations 1-6; §5.1
2502.02533-mass.pdf                 Tables 1,5,6
2605.23904-skillopt.pdf             Tables 1,2(a-f),4(a-c); §4.1,§4.3
2510.04618-ace.pdf                  Tables 1,2,5,9,10,11; §4.3,§4.4,§5
2509.25140-reasoningbank.pdf        Table 1; Figure 8
2509.04642-maestro.pdf              §1 Results; §2 formalism; §2.2 objective
2410.10762-aflow.pdf                Tables 1,2; §5.2
2410.06153-agentsquare.pdf          §abstract, §2 modular design space, §4.3
2406.07496-textgrad.pdf             Tables 2,3; §3.3
2406.16218-trace-msr.pdf            Tables 1,2; §5.3-5.5; §6 Limitations
2508.03680-agent-lightning.pdf      §3.2-3.3; Table 1; §4.1-4.3 (NO result tables)
2602.12670-skillsbench.pdf          §abstract, Table 3, §5.1.1, §5.1.2 Finding 6, §6
2605.16508-skill-scaling-laws.pdf   §abstract, §4 execution law, Eq. 4, Fig. 6
2605.19576-library-drift-ratchet.pdf §abstract, §1
2606.17519-enterprise-agent-routing.pdf §abstract
2603.22386-workflow-opt-survey.pdf  §3.1,§3.2,§3.3,§3.4
2606.20683-harness-design-survey.pdf §8.1,§8.2,§8.3,§9
2601.12307-single-agent-baseline.pdf §abstract
```
`2502.04180-maas.pdf` **could not be read** — `pdftotext` fails with
"Couldn't find trailer dictionary / Couldn't read xref table". The file appears
corrupt. No MaAS claims are made in this document.

## In-repo prior research consumed
```
/home/bud/ditto/gaia-ai-runtime/research/SYNTHESIS.md   F1-F6 (built on, not repeated)
/home/bud/ditto/gaia-ai-runtime/research/RESULTS.md     bench 1 (:21-26), bench 2 (:44-48), bench 3 (:73-77)
```
