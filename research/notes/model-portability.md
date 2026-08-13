# Research stream: model-portability — evidence review for T4 / D11

**Date of this revision:** 2026-08-07. **Supersedes** the 2026-07-26 pass (same path).
**Scope:** the empirical basis for PACT thesis **T4**, §7.3, **AC-3.1 / AC-3.1b / AC-3.5**,
and **D11** ("fail, then recommend").
**Corpus read:** `research/repos/optim/{dspy,gepa,textgrad,trace,adalflow,promptwizard,sammo,agent-lightning,baml,guidance,outlines}`,
`research/repos/routing/{routellm,semantic-router,litellm}`, and 17 PDFs from
`/home/bud/ditto/gaia-ai-runtime/research/papers/` plus
`/home/bud/ditto/agent-inter-op/research/papers/arxiv-2602.00887.pdf`.
**Method:** every table in §1–§3 was **re-extracted and re-transcribed in this pass**
(`pdftotext -layout`), not carried over. Derived ratios are marked `[DER]` with the
arithmetic shown. Source claims are `file:line`.

> **This revision is not a restatement.** It (a) recovers the MaAS paper the previous
> pass could not read, (b) **corrects three mis-attributions that have already
> propagated into `00-THESIS.md`**, (c) adds the cross-*harness* transfer axis, which
> changes what a lockfile must bind, and (d) replaces the mechanism ranking with one
> based on **tier-differential** effect rather than raw effect size.

---

## 0. Evidence classes

| Class | Meaning | Weight |
|---|---|---|
| **[SRC]** | Read from source in the local corpus, `file:line` given. | Highest — it is what runs. |
| **[TBL]** | Transcribed from a numbered table in a local PDF, re-extracted this pass. | High. |
| **[DER]** | Arithmetic I performed on `[TBL]` values, shown inline. | High; check the arithmetic. |
| **[VEN]** | Vendor claim in a repo's own docs, not independently reproduced. | Low — flagged every time. |
| **[INF]** | My inference from `[SRC]`/`[TBL]`, not stated by the source. | Marked explicitly. |

### 0.1 What changed since 2026-07-26

| # | Change | Consequence |
|---|---|---|
| C1 | **MaAS PDF recovered.** The file is truncated (no EOF marker, no xref; `pdftotext`, `pypdf` and `gs` all fail). Recovered by raw `zlib` inflation of the 197 intact streams and re-assembly of the `BT…ET` text operators. Tables 7 and 8 are legible. | Closes open question #1 of the previous pass. Adds two genuine strong→weak transfer cells. |
| C2 | **ACE's reflector-strength claim was mis-attributed** and the mis-attribution is now quoted verbatim in `00-THESIS.md` AC-3.1b. | AC-3.1b's stated evidence is wrong; the conclusion survives on *different* evidence. See §5.1. |
| C3 | **BAML's +34.4 pp is not constrained decoding.** BAML explicitly disclaims constrained generation for that result. | §7.3's mechanism table row is wrong on both the mechanism and the caveat. See §5.2. |
| C4 | **Cross-harness transfer measured** (SkillOpt Table 4b) — as unreliable as cross-model transfer. | The lockfile must bind an optimised artifact to `(model × harness)`, not to a model. New argument *for* D12. |
| C5 | **EffGen Table 3** gives a mechanism × model-scale ablation. Only prompt optimisation has a negative slope with scale; decomposition, routing and memory all help the *large* model more. | Contradicts §7.3's ordering, which lists decomposition first. See §5.4. |
| C6 | **SkillsBench regression across 15 same-harness configs**: skill gain is uncorrelated with model strength (`r = −0.135`). | The cleanest statistical form of "rising tide, not leveller" in the corpus. |
| C7 | **AgentSquare's +17.2% is on GPT-4o / GPT-3.5-turbo**, not a small model. | Must be removed from the "gain on a weak executor" column. |

---

# 1. Q1 — What is the ACTUAL measured transfer?

The question must be split three ways, because the literature measures three different
things and the thesis conflates them.

- **T-A. Naive strategy transfer.** Take the strategy optimised for the big model, run
  it unchanged on the small one. *This is what a naive "portable agent format" does.*
- **T-B. Re-optimisation on the target.** *This is what T4 proposes.*
- **T-C. The residual gap after T-B.** *This is what AC-3.1 actually measures, and
  nobody states it clearly.*

## 1.1 T-A — naive transfer, measured

### 1.1.1 SkillOpt Table 4(a) — cross-model, harness held constant `[TBL]`

`papers/2605.23904-skillopt.pdf` p.8. A skill optimised for the source model, deployed
unchanged on the target. "Baseline" = target's no-skill score; "Direct" = SkillOpt run
natively on the target.

| Benchmark | Target | Baseline | Direct | Transferred | **Gain captured `[DER]`** |
|---|---|---|---|---|---|
| SpreadsheetBench | GPT-5.4-mini | 36.1 | 47.5 | 45.5 | 9.4/11.4 = **82.5%** |
| SpreadsheetBench | GPT-5.4-nano | 23.5 | 42.5 | 26.5 | 3.0/19.0 = **15.8%** |
| LiveMath | GPT-5.4-mini | 14.7 | 32.8 | 19.2 | 4.5/18.1 = **24.9%** |
| LiveMath | GPT-5.4-nano | 23.2 | 27.2 | 28.8 | 5.6/4.0 = **140.0%** |

**Median gain captured = 53.7%.** Re-optimising is worth up to **+16.0 pp** over
transferring (Spreadsheet/nano: 42.5 vs 26.5). On one cell of four, transfer *beat*
re-optimisation — re-optimising *on a very weak executor* produced a worse artifact
than importing one produced by a stronger executor.

### 1.1.2 SkillOpt Table 4(b) — cross-HARNESS, model held constant `[TBL]` — **NEW**

Same table, panel (b): *"a skill trained inside the source harness is evaluated inside
the target harness, all on GPT-5.5."* Model fixed; only the harness changes.

| Benchmark | Source → Target harness | Baseline | Direct | Transferred | **Gain captured `[DER]`** |
|---|---|---|---|---|---|
| LiveMath | Codex → Claude Code | 40.8 | 56.5 | 42.4 | 1.6/15.7 = **10.2%** |
| LiveMath | Claude Code → Codex | 35.2 | 78.4 | 48.0 | 12.8/43.2 = **29.6%** |
| SpreadsheetBench | Codex → Claude Code | 22.1 | 80.4 | 81.8 | 59.7/58.3 = **102.4%** |
| SpreadsheetBench | Claude Code → Codex | 27.5 | 85.0 | 71.1 | 43.6/57.5 = **75.8%** |

**Median gain captured = 52.7%** — statistically indistinguishable from the cross-model
median of 53.7%.

> **This is the single most important new finding in this pass.** The optimised strategy
> is coupled to the **harness** exactly as tightly as it is coupled to the **model**.
> A strategy is valid for a `(model × harness)` pair, not for a model.

Two consequences follow immediately and neither is in the current design:

1. **`pact.lock` must bind an optimised artifact to `(model, adapter, harness-config)`
   jointly**, and re-resolution must be forced when *any* of the three changes — not
   only on model change (P-4 currently gates model swap alone).
2. **This is a new, evidence-backed argument FOR harness lowering (D12/T3)** that the
   thesis does not currently make. If PACT owns the loop, the harness is *constant*
   across adapters, so an optimised strategy transfers across frameworks by
   construction. Native lowering re-introduces exactly the variance measured above.
   D12's justification today is "fidelity over idiom"; it should also be
   "*optimisation transferability*".

### 1.1.3 The harness is worth ±20 pp on its own, on a frontier model `[TBL, DER]`

From SkillOpt Table 1, GPT-5.5, **no skill**, direct-chat vs the two agent harnesses:

| Benchmark | Direct chat | Codex harness | Claude Code harness | Spread |
|---|---|---|---|---|
| SearchQA | 77.7 | 81.8 (+4.1) | 81.9 (+4.2) | 4.2 |
| SpreadsheetBench | 41.8 | 27.5 (**−14.3**) | 22.1 (**−19.7**) | 19.7 |
| OfficeQA | 33.1 | 38.3 (+5.2) | 57.6 (**+24.5**) | 24.5 |
| DocVQA | 78.8 | 87.2 (+8.4) | 86.6 (+7.8) | 8.4 |
| LiveMath | 37.6 | 35.2 (−2.4) | 40.8 (+3.2) | 5.6 |

Harness choice alone swings **−19.7 to +24.5 pp** on a *frontier* model with no skill.
After SkillOpt it still swings **−21.0 pp** (OfficeQA: direct 72.1 vs Codex 51.1) to
**+11.5 pp** (LiveMath: direct 66.9 vs Codex 78.4).

This is `F-4` and `T3-corollary` with numbers attached, and it is *not* a small-model
phenomenon. It corroborates SkillsBench's own conclusion: *"Skills efficacy depends not
only on Skills quality but also on harness implementation… This motivates evaluating
Skills under multiple harnesses rather than treating 'with Skills' as a single
condition"* (`2602.12670-skillsbench.pdf` §6).

### 1.1.4 MaAS Table 7 — cross-model workflow transfer `[TBL]` — **NEW (recovered PDF)**

`papers/2502.04180-maas.pdf` Table 7. The agentic supernet is optimised with
**gpt-4o-mini**, then the optimised supernet is attached to other backbones.

| Dataset | | gpt-4o-mini (source) | Qwen-2.5-72b | llama-3.1-70b |
|---|---|---|---|---|
| HumanEval | vanilla | 87.08 | 85.60 | 80.06 |
| HumanEval | +MaAS | 92.85 (+5.77) | 90.14 (+4.54) | 85.26 (+5.20) |
| MATH | vanilla | 46.29 | 63.80 | 31.93 |
| MATH | +MaAS | 51.82 (+5.53) | 69.35 (+5.55) | 42.97 (**+11.04**) |

`llama-3.1-70b` is the weaker executor on **both** benchmarks (80.06 < 87.08;
31.93 < 46.29), so those two cells are genuine **strong → weak** transfer, and both are
positive. Against the source model's *naive* score `[DER]`:
HumanEval 85.26/87.08 = **97.9%**; MATH 42.97/46.29 = **92.8%**.
Gap movement `[DER]`: HumanEval 7.02 → 7.59 (**widened**); MATH 14.36 → 8.85 (**narrowed**).

**Caveats I must state.** (i) There is no "re-optimised on llama" row, so the *fraction
of available gain captured* — the statistic that matters — cannot be computed.
(ii) These are 70B-class models, not SLMs. (iii) The paper's prose claims
*"transfers well to models such as Qwen-2.5-70b, with 4.98%–5.50% ↑ in performance"*
(§4, Transferability Analysis), which **does not match its own Table 7**: the four
non-source cells are +4.54, +5.20, +5.55, **+11.04**. I cannot reconcile the stated
range with the table; treat the table, not the prose.

### 1.1.5 AFlow Table 2 — cross-model workflow transfer `[TBL]`

`papers/2410.10762-aflow.pdf` p.8, HumanEval pass@1, mean of 3 runs.

| Executor | IO | CoT | CoT-SC | MP | MPD | SR | **Ours** (searched w/ 4o-mini) | **Ours\*** (searched w/ DeepSeek-V2.5) |
|---|---|---|---|---|---|---|---|---|
| GPT-4o-mini | 87.0 | 88.6 | 91.6 | 91.6 | 89.3 | 87.8 | **94.7** | 90.8 |
| DeepSeek-V2.5 | 88.6 | 89.3 | 88.6 | 88.6 | 89.3 | 90.0 | 93.9 | **94.7** |
| GPT-4o | 93.9 | 93.1 | 94.7 | 93.9 | 94.7 | 91.6 | **96.2** | 95.4 |
| Claude-3.5-sonnet | 90.8 | 92.4 | 93.9 | 91.6 | 90.8 | 89.3 | **95.4** | 94.7 |

Worst-case transfer loss **−3.9 pp** (4o-mini on the DeepSeek-searched workflow).
The paper's own conclusion: *"different language models require different workflows to
achieve their optimal performance."* **Caveat:** HumanEval is saturated at 87–96 here,
so effect sizes are compressed; −3.9 pp is a floor on the true loss.

### 1.1.6 MASS Appendix C.1 Table 4 — transfer can be **catastrophic**, not merely lossy `[TBL]` — **NEW**

`papers/2502.02533-mass.pdf` p.20. Prompt templates transferred **from Gemini to
Claude-3.5-Sonnet**. The paper's own framing: *"As we transfer the prompt template for
each agent from Gemini to Claude, it is noticeable that the basic topology on some tasks
may result in severe degradation of performance."*

| Method (on Claude-3.5-Sonnet) | MATH | DROP | HotpotQA | MBPP | HumanEval | LCB | Avg |
|---|---|---|---|---|---|---|---|
| CoT | 57.33 | 55.52 | 23.56 | 67.50 | 88.67 | 72.67 | 60.21 |
| Self-Consistency | 61.67 | 57.86 | 25.69 | 69.17 | 90.00 | 72.67 | 62.84 |
| Self-Refine | 57.00 | 56.26 | 23.57 | 68.00 | 87.00 | 49.33 | 56.86 |
| **Multi-Agent Debate** | 45.00 | **26.62** | 31.41 | **00.00** | 84.33 | 72.82 | **43.36** |
| Mass (re-optimised) | 63.00 | 68.93 | 66.98 | 68.83 | 93.00 | 73.73 | **72.43** |

**A multi-agent debate topology with transferred prompts scored 0.00 on MBPP.** DROP
fell to 26.62 against CoT's 55.52. Re-optimisation recovered both.

> **This is PACT's D28 failure mode #2 in its purest measured form.** Naive cross-model
> transfer of a *(topology × prompt)* pair is not "lossy" — it can be *total failure*.
> The failure lives in the **interaction**, not in the prompt alone: the same transfer
> under a single-agent CoT loop merely degraded; under a debate topology it zeroed.
> This is decisive support for P-4 (fail-closed on model swap) and for the ordering rule
> "text before topology": the *topology* is what makes a transfer catastrophic.

## 1.2 T-B — re-optimisation on the target works, and the gains are large

| System | Small executor | Benchmark set | Baseline → optimised | Δ | Source |
|---|---|---|---|---|---|
| GEPA | Qwen3-8B | 6-task aggregate | 45.23 → 54.85 | **+9.62** | gepa Table 1 `[TBL]` |
| GEPA | Qwen3-8B | HotpotQA | 42.33 → 62.33 | **+20.00** | gepa Table 1 |
| MASS | Gemini-1.5-flash | 8-task avg | 60.87 → 74.30 | **+13.43** | mass Table 1 `[TBL]` |
| MASS | Mistral-Nemo-12B | 4-task avg | 40.4 → 55.9 | **+15.5** | mass Table 5 `[TBL]` |
| SkillOpt | Qwen3.5-4B | 6-bench avg | 38.63 → 57.85 | **+19.22** `[DER]` | skillopt Table 1 |
| SkillOpt | Qwen3.5-4B | ALFWorld | 30.6 → 81.3 | **+50.7** | skillopt Table 1 |
| ReasoningBank+MaTTS | Gemini-2.5-flash | WebArena SR | 40.5 → 51.8 | **+11.3** | rb Table 1 `[TBL]` |
| ACE | GPT-OSS-120B | AppWorld avg | 34.6 → 42.2 | **+7.6** | ace Table 5 `[TBL]` |
| EffGen | Qwen2.5-1.5B | 13-bench avg | 34.28 → 47.44 | **+13.16** | effgen Table 2 `[TBL]` |
| TextGrad | gpt-3.5-turbo | Object Counting | 77.8 → 91.9 | **+14.1** | textgrad Table 3 `[TBL]` |
| In-repo bench 3 | deepseek-v4-flash | ticket triage (held-out) | 0.000 → 0.812 | **+0.812** | `RESULTS.md:77` |

T-B is not in doubt. **Re-optimising on the target works, and it beats transferring.**

## 1.3 T-C — the residual gap. This is where the thesis is at risk.

**The optimiser lifts the strong executor at least as much as the weak one.**

### 1.3.1 GEPA, six benchmarks, Qwen3-8B vs GPT-4.1-Mini `[TBL Tables 1–2, DER]`

Like-for-like (GEPA row vs GEPA row — methodologically cleaner than the previous pass's
best-of-both mixing):

| | Qwen3-8B base | Qwen3-8B GEPA | mini base | mini GEPA | small-opt / **large-base** | small-opt / **large-opt** |
|---|---|---|---|---|---|---|
| **Aggregate** | 45.23 | 54.85 | 53.03 | 65.22 | **103.4%** | **84.1%** |

- Gap before optimisation: `53.03 − 45.23 = 7.80`.
- Gap after: `65.22 − 54.85 = 10.37`. **Widened by 2.57 pp.**
- Using best-of-{GEPA, GEPA+Merge} on both sides (54.85 vs 66.36): ratio **82.7%**,
  gap `11.51`, **widened by 3.71**. Either construction widens.

Per-benchmark small-opt / large-best: HotpotQA 90.3%, IFBench 69.0%, HoVer 92.3%,
PUPA 95.2%, **AIME-2025 53.9%**, LiveBench-Math 81.0%.

### 1.3.2 MASS, eight benchmarks, flash vs pro `[TBL Table 1, DER]`

| | flash CoT | flash+MASS | pro CoT | pro+MASS | flash-opt / pro-CoT | flash-opt / pro-MASS |
|---|---|---|---|---|---|---|
| **Average** | 60.87 | 74.30 | 65.28 | 78.79 | **113.8%** | **94.3%** |

Gap `4.41 → 4.49`. **Unchanged.**

### 1.3.3 SkillOpt, six benchmarks, Qwen3.5-4B vs GPT-5.5 `[TBL Table 1, DER]` — gap now computed

| Benchmark | 4B no-skill | 4B SkillOpt | 5.5 no-skill | 5.5 SkillOpt | 4B-opt/5.5-naive | 4B-opt/5.5-opt |
|---|---|---|---|---|---|---|
| SearchQA | 68.1 | 71.2 | 77.7 | 87.3 | 91.6% | 81.6% |
| SpreadsheetBench | 9.3 | 23.9 | 41.8 | 80.7 | **57.2%** | **29.6%** |
| OfficeQA | 14.5 | 29.7 | 33.1 | 72.1 | 89.7% | 41.2% |
| DocVQA | 86.9 | 89.0 | 78.8 | 91.2 | 113.0% | **97.6%** |
| LiveMath | 22.4 | 52.0 | 37.6 | 66.9 | 138.3% | 77.7% |
| ALFWorld | 30.6 | 81.3 | 83.6 | 95.5 | 97.2% | 85.1% |
| **Average** | 38.63 | 57.85 | 58.77 | 82.28 | **98.4%** | **70.3%** |

Gap `58.77 − 38.63 = 20.13` → `82.28 − 57.85 = 24.43`. **Widened by 4.30 pp.**
(The previous pass reported the two ratios but never computed this gap.)

### 1.3.4 ACE, FiNER, Llama-3.3-70B vs DeepSeek-V3.1-671B `[TBL Tables 9, 16, DER]` — **NEW**

| Base model | FiNER baseline | + ACE (offline, GT) |
|---|---|---|
| Llama-3.3-70B-Instruct | 62.5 | 64.9 (+2.4) |
| DeepSeek-V3.1-671B | 70.7 | 78.3 (+7.6) |

Gap `8.2 → 13.4`. **Widened by 5.2 pp.** Also on the Llama row, **GEPA scored 59.41,
i.e. −3.09 *below* the un-optimised baseline** (`ace` Table 9) — an optimiser making a
70B model worse.

### 1.3.5 ReasoningBank, WebArena `[TBL Table 1, DER]` — the one narrowing case

| Backbone | No memory | ReasoningBank | +MaTTS |
|---|---|---|---|
| Gemini-2.5-flash | 40.5 | 48.8 | 51.8 |
| Gemini-2.5-pro | 46.7 | 53.9 | 56.3 |
| Claude-3.7-sonnet | 41.7 | 46.3 | 48.8 |

Gap flash↔pro: `6.2 → 5.1 → 4.5`. **Narrowed by 1.7.** flash+MaTTS (51.8) beats
pro-no-memory (46.7) by +5.1 but sits 4.5 behind pro+MaTTS.

### 1.3.6 SkillsBench — the cleanest statistical test in the corpus `[TBL Table 2, DER]` — **NEW**

87 tasks × 18 model-harness configs × 3 trials. Restricting to the **15 OpenHands
configs** (harness held constant) and regressing skill gain on the no-skill baseline:

```
n = 15
corr(no-skill baseline, absolute Δ)   = −0.135
corr(no-skill baseline, normalised g) = +0.180
mean Δ = +15.75 pp,  sd = 6.15
```

Across all 18 configs: `corr(baseline, Δabs) = −0.025`; tertile means
`Δabs`: weakest-6 **+17.2**, middle-6 **+19.2**, strongest-6 **+13.4`.

> **Procedural specification delivers the same absolute lift regardless of executor
> strength (`r ≈ 0`).** It therefore *cannot* close a gap; it translates both tiers
> upward together. This is the strongest and least cherry-picked statement of the
> "rising tide, not leveller" result available.

Head-to-head gap movement within OpenHands `[DER]`:

| Pair | gap before | gap after | movement |
|---|---|---|---|
| GPT-5.5 vs Gemini 3.1 Flash Lite | 35.5 | 47.2 | **+11.7 (widened)** |
| GPT-5.5 vs MiniMax M2.7 | 33.4 | 32.4 | −1.0 (flat) |
| GPT-5.5 vs GPT-5.4 Mini | 21.6 | 25.9 | **+4.3 (widened)** |

### 1.3.7 Scoreboard on gap movement

| Suite | before | after | movement |
|---|---|---|---|
| GEPA 6-bench (like-for-like) | 7.80 | 10.37 | **widened +2.57** |
| SkillOpt 6-bench | 20.13 | 24.43 | **widened +4.30** |
| ACE FiNER (70B vs 671B) | 8.2 | 13.4 | **widened +5.20** |
| SkillsBench (GPT-5.5 vs Flash Lite) | 35.5 | 47.2 | **widened +11.7** |
| SkillsBench (GPT-5.5 vs GPT-5.4 Mini) | 21.6 | 25.9 | **widened +4.30** |
| MASS 8-bench | 4.41 | 4.49 | unchanged |
| SkillsBench (GPT-5.5 vs MiniMax M2.7) | 33.4 | 32.4 | flat |
| ReasoningBank WebArena | 6.2 | 4.5 | **narrowed −1.70** |
| MaAS MATH (transfer) | 14.36 | 8.85 | **narrowed −5.51** |
| MaAS HumanEval (transfer) | 7.02 | 7.59 | widened +0.57 |

**5 widened, 2 flat, 2 narrowed, 1 marginal.** The thesis's current phrasing — "does not
close and sometimes widens" — is accurate but understated. The honest phrasing is:
**the gap widens more often than it narrows.**

## 1.4 Answer to Q1

1. **Naive strong→weak transfer captures a median ≈ 53% of the gain that
   re-optimisation on the target achieves** (range 15.8%–140%, n=4, SkillOpt 4a), and
   costs up to −3.9 pp against a natively-searched workflow (AFlow T2).
2. **Cross-harness transfer is equally unreliable** (median 52.7%, range 10.2%–102.4%,
   SkillOpt 4b). Strategy is bound to `(model × harness)`.
3. **Transfer of a (topology × prompt) pair can be catastrophic, not merely lossy** —
   0.00 on MBPP (MASS App. C.1).
4. **Re-optimisation on the target reliably adds +7.6 to +50.7 pp** (+9.6 to +19.2 pp as
   a multi-benchmark average).
5. **The residual gap does not close.** Across ten measured comparisons it widened in
   five, held flat in two, narrowed in two.
6. **The defensible PACT claim is against the author's hand-written frontier strategy**:
   an optimised small model averages **98.4% / 113.8% / 103.4%** (SkillOpt / MASS /
   GEPA). Against the *optimised* frontier strategy it averages **70.3% / 94.3% /
   84.1%**.

---

# 2. Q2 — Mechanism ranking, and where each fails

## 2.1 The ranking criterion must change

The thesis §7.3 table ranks mechanisms by *"best measured gain on a weak executor."*
That is the wrong statistic. A mechanism that adds +15 pp to *every* tier does nothing
for portability; a mechanism that adds +11 pp at 1.5B and +2 pp at 32B is what
portability actually needs. **Rank by tier-differential (`∂gain/∂scale`), not by raw
effect size.**

The corpus contains exactly one clean mechanism × scale ablation.

### EffGen Table 3 `[TBL]` — `research/papers/arxiv-2602.00887.pdf` p.7

Component ablation, Qwen2.5-Instruct, 13-benchmark average. Each row is the drop from
removing that component.

| Component removed | 1.5B | 7B | 32B | **slope vs scale** |
|---|---|---|---|---|
| **Prompt optimisation** | **−11.2** | −8.9 | **−2.4** | **strongly negative — helps small models most** |
| Complexity routing | −3.6 | −6.2 | −7.9 | positive — helps large models most |
| Task decomposition | −3.3 | −4.7 | −5.5 | positive — helps large models most |
| Memory system | −1.8 | −3.4 | −3.7 | positive |
| All (→ raw ReAct) | −13.2 | −12.3 | −12.7 | flat |

The paper states it directly: *"prompt optimization provides 11.2% gain at 1.5B but only
2.4% at 32B, while complexity routing shows the opposite trend (3.6% at 1.5B, 7.9% at
32B), suggesting small models need better prompts, large models smarter routing"* (§5).

> **Only prompt/context optimisation is a genuine model-portability mechanism.**
> Decomposition, routing and memory all help the strong executor *more* than the weak
> one. §7.3 currently lists **Decomposition as mechanism #1** — that ordering is
> contradicted by the only measurement that varies scale under a fixed pipeline.

### Mechanisms are strongly SUB-ADDITIVE `[TBL, DER]`

EffGen: *"The combined removal drop (12.3–13.2%) is smaller than the sum of individual
drops (19.5–23.2%), indicating overlapping coverage between components."* My arithmetic
reproduces this exactly: sums are 19.9 (1.5B), 23.2 (7B), 19.5 (32B); combined drops
13.2 / 12.3 / 12.7. **Combined / sum = 66% / 53% / 65%, mean ≈ 61%.**

**A resolver that stacks mechanisms and sums their catalogued effect sizes will
over-predict by roughly 1.6×.** Expected-gain estimates must be treated as an upper
bound, and the eval must be the arbiter — never a predicted score.

## 2.2 The ranking

Effect sizes are not commensurable across benchmarks. Ranked by *(tier-differential,
then consistency, then magnitude)*.

| # | Mechanism | Best measured gain on a weak executor | Tier-differential | **Where it FAILS** |
|---|---|---|---|---|
| 1 | **Procedural specification (curated skills)** | **+50.7 pp** (Qwen3.5-4B ALFWorld 30.6→81.3); **+16.6 pp** mean over 18 configs | **≈ 0** (`r = −0.135`, n=15) — lifts all tiers equally | **Model-authored skills fall BELOW the no-skill baseline**: −8.1 / −11.3 / −11.5 pp (skillsbench §5.1.1); SkillOpt Table 1 has LLM-skill cells at −29.6 (GPT-5.4 OfficeQA 50.0→20.4) and −20.9 (GPT-5.2 OfficeQA). **Human-written skills beat model-written ones by up to +29.7 pp on the same cell** (GPT-5.5 Spreadsheet: human +31.1 vs LLM +1.4). >4 skills: +10.1 vs +19.0 for 2–3. "Comprehensive" prose: **+0.7** vs +21.5 standard. 13/87 tasks negative, worst −7.4. Human skills go **negative on ALFWorld for weak models** (−16.4 mini, −12.0 GPT-5.2, −14.9 Qwen3.6-35B) while helping GPT-5.5 (+8.2). Root cause named by the paper: *"a single 'correct' pipeline without applicability boundaries or lightweight fallbacks."* |
| 2 | **Prompt/context optimisation (GEPA / ACE / MASS-1PO / EffGen)** | **+29.3 pp** single benchmark; +9.6 to +17.1 aggregate; **−11.2 pp** to remove at 1.5B | **Strongly favourable** — the only mechanism measured to help small models more | Optimiser **hyperparameters do not transfer across tiers**: GEPA+Merge is +13.33 agg on mini but takes Qwen3-8B IFBench 38.61 → **28.23** (below the 36.90 baseline). **TextGrad is destructive on weak models**: Qwen3.6-35B LiveMath 31.2→**7.2** (−24.0), Spreadsheet 38.2→22.9 (−15.3), OfficeQA 45.9→33.7 (−12.2); Qwen3.5-4B LiveMath 22.4→10.6 (−11.8). GEPA is −3.09 below baseline on Llama-3.3-70B FiNER. Choice of prompt optimiser is worth **7.7 pp** (MASS Table 9, flash MATH: APE 73.3 vs MIPRO 81.0). |
| 3 | **Schema-aligned parsing (post-hoc, substrate-free)** | **+34.4 pp** (claude-3-haiku BFCL 57.3% → 91.7%) `[VEN]` | not measured across scale | `[VEN]` — single vendor benchmark, not reproduced. Depends on an error-tolerant parser being *correct*; a parser that silently coerces is a T7 violation by construction. |
| 4 | **Context discipline / hierarchical routing** | routing 71.3% → 91.7%; hijack 22.4% → 4.1%; +10–17 pp F1 in production | **unfavourable** (EffGen: −3.6 at 1.5B vs −7.9 at 32B) | Buys **tokens, not accuracy**, on small catalogues: in-repo bench 2 FULL80 = 1.000 at 1,773 tokens vs HIER 0.900 at 259. Flat top-k is retrieval-bound (accuracy == gold-in-context rate, 0.650). A confusion gap survives perfect retrieval (oracle ceiling 79% → 69% at scale). Names-only routing costs 8.4 pt vs full descriptions. |
| 5 | **Constrained decoding (regex / CFG)** | **no effect size measured anywhere in the corpus** | unknown | **Substrate-bound.** Verified matrix in §2.3. Also: schema constraint can *degrade* quality (BAML gpt-5.2 receipt case; *"FC-strict… but `gpt-4o-2024-08-06` gets worse"*), blocks chain-of-thought when the schema forbids free text, and **broke an optimiser**: Trace attributes gpt-4o-2024-05-13's hallucination to *"the current implementation of optimizers rely on outputing in json format"* (`trace/README.md:391-399`). |
| 6 | **Verification loops / held-out gating** | Enables everything else; alone +1.7 to +3.1 pp | neutral | LLM judges: ReasoningBank measured its judge at **72.7%** accuracy and reports SR *"not significantly impact[ed]… within reasonable accuracy range (70%–90%)"* (§4.4). ACE Table 17: a *harmful* reflector injecting bad content **every** iteration flips +7.6 → **−4.0**; at every 5th iteration it is still +5.4. So verification tolerates *noise* well and *adversarial corruption* badly. |
| 7 | **Ensembling / self-consistency / best-of-N** | **+2.9 pp** (pro SC 68.18 vs CoT 65.28); MaTTS k=5 +3.0 flash | neutral | Multiplies cost by *k* for single-digit gain. Useless when the model is *consistently* wrong (AIME-class). Needs a selector — and DSPy's shipped selector is `reward_fn: Callable` (`best_of_n.py:37`), i.e. **code**, which violates D14. |
| 8 | **Decomposition into sub-agents / topology search** | **+2.99 pp** (MASS 2TO stage) | **unfavourable** (EffGen: −3.3 at 1.5B vs −5.5 at 32B) | **Priced super-multiplicatively in depth.** `Acc(N,K) = p_N(p_N − η_N)^{K−1} < p_N^K` (skill-scaling-laws Prop. 2, p.19); empirically `Acc(N,K) ≈ (a − b ln N)^{γK}` with `γ = 6.7b + 1.09 > 1` (p.5, `R² > 0.97`, 15 models). `γ` rises with routing fragility `b`, so **decomposition costs more the weaker the executor**. Per-step accuracy is **U-shaped** — mid-chain steps are the fragile ones. Tight coupling costs −7.2% downstream on a wrong upstream artifact (loose +2.8%; crossover `κ* ≈ 0.28`). **A strong single multi-turn agent matches homogeneous multi-agent workflows *and* an automatically-optimised heterogeneous workflow, more cheaply via KV reuse** (`2601.12307` abstract). **AgentSquare's +17.2% is measured on GPT-4o and GPT-3.5-turbo — it is not weak-executor evidence and must be removed from that column.** |
| 9 | **CodeAct as the default loop** | — | **strongly negative** | Smolagents at Qwen2.5-1.5B scores **27.81 vs the raw model's 34.28**, and takes **338.8 min vs 5.3 min on GSM8K (64× slower)** (EffGen Table 2, §4). EffGen's conclusion: *"the right choice of tools matters far more than always converting problems to code."* AC-5.2 requires CodeAct to be *expressible*; the resolver must be free **not to select it** for a weak executor. |
| 10 | **Model routing (RouteLLM / semantic-router)** | 85% cost cut at 95% GPT-4 quality `[VEN]` | n/a | **Not a portability mechanism at all.** `pct_call_metric` interpolates *the percentage of strong-model calls* needed to reach x% of the `(strong − weak)` gap; `apgr_metric` normalises AUC between the constant weak and constant strong lines (`routellm/evals/evaluate.py:77-114` `[SRC]`). Both are **bounded above by the strong model's accuracy by construction** and presuppose it is available. **Under D17 (air-gapped, SLM-only) it contributes zero.** |
| 11 | **Weight training / distillation** | **no absolute numbers published** (agent-lightning §4.1–4.3 reports reward curves only, Figures 5–7) | — | See §2.4 — the shipped implementation has a structural constraint that is fatal for PACT. |

## 2.3 Constrained decoding: three distinct mechanisms, conflated everywhere

The previous pass and the thesis treat "constrained decoding / schema-aligned parsing"
as one row. They are three mechanisms with **completely different portability
profiles**.

| Level | What it is | Substrate requirement | Availability |
|---|---|---|---|
| **L1 — Schema-aligned parsing (SAP)** | error-tolerant *post-hoc* parsing that coerces malformed output to the schema | **none** | everywhere, including PACT's own harness |
| **L2 — Provider structured output** | `response_format` / JSON-schema mode on the provider API | provider feature | ~32% of the LiteLLM catalogue |
| **L3 — Grammar-constrained decoding** | regex / CFG enforced at the logit level | **logit access** | local runtimes only |

**Verified L3 matrix `[SRC]`**, `research/repos/optim/outlines/src/outlines/models/`:

| Backend | JSON schema | Regex | CFG | Evidence |
|---|---|---|---|---|
| **Anthropic** | ✗ | ✗ | ✗ | `anthropic.py:120-128` — `NotImplementedError` for **any** non-`None` output type |
| OpenAI | ✓ | ✗ `TypeError` | ✗ `TypeError` | `openai.py:157-167` |
| Gemini | ✓ | ✗ `TypeError` | ✗ `TypeError` | `gemini.py:163-172` |
| Mistral | ✓ | ✗ | ✗ | `mistral.py:222,230-237` |
| Ollama | ✓ | ✗ | ✗ | `ollama.py:130-141` |
| LMStudio | ✓ | ✗ | ✗ | `lmstudio.py:144-155` |
| Dottxt | ✓ | "soon" | "soon" | `dottxt.py:62-73` |
| TGI | ✓ | ✓ | ✗ | `tgi.py:71-88` |
| **vLLM / vLLM-offline / SGLang** | ✓ | ✓ | ✓ | `vllm.py:64-66`, `vllm_offline.py:92-94`, `sglang.py:68-77` |
| transformers / llama.cpp / MLX | ✓ | ✓ | ✓ | via `backends/{llguidance,xgrammar}.py`; `outlines_core.py:253` raises `NotImplementedError` for CFG |

Also `guidance/guidance/models/_openai_base.py:596` — `"Regex not yet supported for
OpenAI"`.

> **Two consequences, and the second is a happy one.**
> (1) The capability lattice must be keyed on `(model_id, provider, runtime)`, and
> `structured_output` must be an *ordered enum*
> `[none, json_mode, json_schema, regex, cfg]`, not a boolean.
> (2) **L3 is fully available exactly where PACT needs it.** D17's air-gapped,
> local-SLM deployment runs vLLM / SGLang / llama.cpp — which are precisely the
> substrates with full CFG support. The mechanism is unavailable in the cloud and
> available on-prem. That inverts the usual capability story and is worth stating in
> the architecture.

### The +34.4 pp number does not belong to L3 `[SRC]` — correction

`baml/typescript2/app-website/blog-content/2024-08-13-bfcl-sota.mdx`, the source of the
claude-3-haiku 57.3% → 91.7% figure, states explicitly:

> *"We used our prompting DSL (BAML) to achieve this, **without using JSON-mode or any
> kind of constrained generation**."*

The mechanism is (a) TypeScript-like type definitions in the prompt instead of JSON
Schema, and (b) SAP — *"Instead of rejecting imperfect outputs, SAP actively transforms
them to match your schema using custom edit distance algorithms"*
(`fern/01-guide/why-baml.mdx:339-342`).

| Model | Function Calling | Python AST Parser | **SAP** |
|---|---|---|---|
| gpt-3.5-turbo | 87.5% | 75.8% | **92%** |
| gpt-4o | 87.4% | 82.1% | **93%** |
| claude-3-haiku | **57.3%** | 82.6% | **91.7%** |

> **The largest measured structured-output win on a weak model comes from a mechanism
> that requires no substrate support at all.** L1/SAP is pure parser engineering. PACT's
> harness can implement it once and deliver it on **every** adapter and **every**
> provider — including Anthropic, which supports nothing at L3. This should be a
> first-class harness capability, not a per-adapter concern.

**Counter-evidence that must ship with it:** BAML documents `gpt-5.2` returning
`quantity: 1` under the structured-outputs API where the completions API returns the
correct `0.46` (`2025-12-14-structured-outputs-create-false-confidence.mdx`, with a
public reproduction gist), and finds *"FC-strict… improves every older OpenAI model, but
`gpt-4o-2024-08-06` gets worse."* **L2 must be a variant choice under eval, never a
default.**

## 2.4 Distillation is available and structurally incompatible with T4 `[SRC]` — **NEW**

The previous pass omitted weight-level transfer entirely. DSPy ships it.

`dspy/teleprompt/bootstrap_finetune.py` — `BootstrapFinetune.compile(student, trainset,
teacher)` bootstraps traces from a teacher program and fine-tunes the student's LMs
(`:60-133`). `dspy/teleprompt/bettertogether.py` alternates prompt and weight
optimisation (`BetterTogether(metric=..., p=GEPA(...), w=BootstrapFinetune(...))`).

The fatal constraint is at `bootstrap_finetune.py:270-295`:

```python
def prepare_teacher(student, teacher=None):
    ...
    assert_structural_equivalency(student, teacher)   # same predictor COUNT and NAMES
    assert_no_shared_predictor(student, teacher)
```

> **The only shipped teacher→student transfer mechanism in the corpus requires the
> strong-model program and the small-model program to be structurally identical.** That
> is exactly the constraint T4 exists to remove: PACT's small-model variant is supposed
> to be *structurally different* — more decomposition, more verification, a different
> loop. DSPy cannot express that relationship.

It is also incompatible with D14 (needs training infrastructure and code), D17 (needs
local GPUs and weight access) and T6 (emits weights, not source). **Distillation should
be named as an explicitly out-of-scope mechanism with these three reasons attached**,
so that the omission reads as a decision rather than an oversight.

## 2.5 Ordering, quantified

MASS Table 6 (Gemini-1.5-pro, 8-task average) `[TBL, deltas DER]`:

| Stage | Score | Δ |
|---|---|---|
| Base agent | 63.54 | — |
| + APO (agent-level prompt opt.) | 67.44 | +3.90 |
| + 1PO (block-level prompt opt.) | 74.56 | +7.12 |
| + 2TO (topology optimisation) | 77.55 | +2.99 |
| + 3PO (workflow-level prompt opt.) | 78.40 | +0.85 |

Prompt-side = `3.90 + 7.12 + 0.85 = 11.87` of `14.86` total = **79.9%**; topology
**20.1%**. Note 3PO is *not* uniformly positive: MuSiQue falls `52.61 → 51.40` and
HumanEval `92.00 → 91.67`.

**Sample efficiency strongly favours config-first search** — decisive under D17:

| System | HotpotQA | rollouts | IFBench | rollouts |
|---|---|---|---|---|
| GEPA | 69.00 | > 6,000 | 55.95 | > 3,000 (peak at 678) |
| Maestro (config only) | 70.33 | **240** | 56.12 | **700** |
| Maestro (graph + config) | **72.00** | 420 | **59.18** | 900 |

Maestro reaches a better score than GEPA with **14–25× fewer rollouts**
(`2509.04642-maestro.pdf` §1, lines 171–178). And GEPA's reflection calls are
astonishingly few — **17 to 92 per benchmark** (`gepa` Table 4, App. N), at a total cost
of **$86** for the whole 6-benchmark Table 2 run (§E.3).

> **There is no cost argument for binding the reflector to the target model.** A strong
> reflector costs tens of calls per optimisation run. AC-3.1b is nearly free to satisfy.

The workflow-optimisation survey states the mechanism-level reason to keep both:
*"prompt tuning alone cannot supply missing structural capabilities such as validation,
conditional routing, or intermediate decomposition"*, and warns that *"better prompts
can compensate for weak topology, making a poor scaffold look competitive while
increasing cost and reducing robustness"* (`2603.22386` §3.2–3.3).

---

# 3. Q3 — The honest ceiling

Six classes, each with a measurement. **C6 is new.**

### C1 — Competition mathematics and multi-step exact arithmetic

| Evidence | Small model | Optimised | Frontier naive | Frontier optimised | Ratio to optimised |
|---|---|---|---|---|---|
| GEPA AIME-2025 | Qwen3-8B 27.33 | 32.00 | 49.33 | 59.33 | **53.9%** |
| MASS MATH | Mistral-Nemo-12B 13.3 | 43.7 | 71.67 | 84.67 | **51.6%** |
| SkillOpt LiveMath | GPT-5.4-nano 23.2 | 27.2 | 37.6 | 66.9 | **40.7%** |

On AIME the gap **widened** under optimisation (22.00 → 27.33). On MASS-MATH the
optimiser more than tripled the 12B model's score and still left it at **61.0% of the
frontier's un-optimised score**. **No mechanism in the corpus closes this.**

### C2 — Long-horizon, tightly-coupled procedural work with strict output contracts

SkillOpt SpreadsheetBench is the worst cell in the corpus: Qwen3.5-4B `9.3 → 23.9`
against GPT-5.5's `41.8 → 80.7` — **29.6% of the optimised frontier, 57.2% of the naive
frontier**, after the strongest published skill-training method. GPT-5.4-nano transfer
captures only 15.8% of the available gain on the same benchmark.

Mechanism: the depth law. In tightly-coupled step pairs a wrong upstream state
propagates and the pair loses **−7.2%**; only loosely-coupled pairs can ignore a bad
upstream result (**+2.8%**), crossover at `κ* ≈ 0.28`.

### C3 — Cross-site / cross-domain compositional agentic tasks

ReasoningBank Table 1, WebArena **Multi** subset (29 tasks, requires transferring memory
across sites):

| Backbone | No memory | Synapse | AWM | ReasoningBank | +MaTTS |
|---|---|---|---|---|---|
| Gemini-2.5-flash | 10.3 | 10.3 | **3.4** | 13.8 | 17.2 |
| Gemini-2.5-pro | 6.9 | 6.9 | **3.4** | 13.8 | 20.7 |
| Claude-3.7-sonnet | **0.0** | 0.0 | 0.0 | 3.4 | 10.3 |

Everything is near the floor; a *strong* model scores **0.0** without memory; a memory
mechanism (AWM) *halves* flash's score. This is the class where the contract is most
likely unsatisfiable by any strategy on any tier.

### C4 — Tasks where the deficit is a missing capability, not a missing procedure

SkillsBench Table 3 `[TBL]`: Natural Science **+28.8**, Media **+24.1**, Cybersecurity
**+18.9**, Industrial **+15.7**, Finance **+14.2**, Office **+12.6**, Software
Engineering **+11.6**, Mathematics & OR **+9.7**. The paper's reading: gains are largest
where the procedure is *underrepresented in pretraining*, smallest where the model
already has the capability. ACE states the limit directly: *"In domain-specific tasks
where no model can extract useful insights, the resulting context will naturally lack
them"* (§5).

### C5 — Anything where the optimiser must run on the weak model

- **Controlled ablation** (ACE Table 16, FiNER, generator and curator fixed at
  DeepSeek-V3.1): reflector = GPT-OSS-120B → **76.6 (+5.9)**; = DeepSeek-V3.1 →
  **78.3 (+7.6)**; = GPT-5.1 → **78.5 (+7.8)**. Reflector strength is worth **1.9 pp of
  the 7.8 pp total (24%)**, and it **saturates**: 671B → GPT-5.1 buys +0.2.
- **Adversarial reflector** (ACE Table 17): harmful injection every iteration flips
  +7.6 → **−4.0**; every 5th iteration is still +5.4.
- **TextGrad on weak executors is frequently destructive** (SkillOpt Table 1: −24.0,
  −15.3, −12.2, −11.8, −7.4 pp cells).
- **Trace** `README.md:391-399`: with `gpt-4o-2024-05-13` as optimiser the system
  *"often hallucinates even in very basic optimization problems and does not follow
  instructions"*, attributed to the optimiser's JSON output requirement.
- **SkillOpt Table 4(a)**, LiveMath/nano: a skill *imported* from a stronger model
  (28.8) beat one *re-optimised* on the nano model (27.2).

### C6 — Anything where the agent harness is fixed and wrong for the tier — **NEW**

At Qwen2.5-1.5B, all three mainstream frameworks score **below the raw model**:
raw **34.28**, LangChain 32.81, AutoGen 33.57, smolagents 27.81 (EffGen Table 2,
verified from the PDF this pass). The sign flips around 32B. Combined with §1.1.3
(harness worth −19.7 to +24.5 pp on a *frontier* model) and §1.1.2 (strategies do not
transfer across harnesses), the honest statement is:

> **A fixed harness is itself a ceiling.** For some `(task, tier)` pairs no strategy
> rescues the model *inside that harness*, and the only remedy is less scaffolding —
> which the CTS must therefore be able to select, and which `F-4` must measure against
> **raw**, not only against native.

---

# 4. Q4 — What must a SPEC expose for an optimizer to operate on it?

## 4.1 The ABIs, read from source

### GEPA — `gepa/src/gepa/core/adapter.py` `[SRC]`

```python
Candidate = dict[str, str]                                          # :12
@dataclass
class EvaluationBatch:                                              # :16
    outputs: list[RolloutOutput]                                    # :31
    scores: list[float]                                             # :32
    trajectories: list[Trajectory] | None = None                    # :33
    objective_scores: list[dict[str, float]] | None = None          # :34
    num_metric_calls: int | None = None                             # :35
class GEPAAdapter(Protocol):                                        # :81
    def evaluate(batch, candidate, capture_traces) -> EvaluationBatch     # :143
    def make_reflective_dataset(candidate, eval_batch, components_to_update)
        -> Mapping[str, Sequence[Mapping[str, Any]]]                # :183
    propose_new_texts: ProposalFn | None                            # :217
```

Docstring at `:134-140`, verbatim: *"**Never raise for individual example failures.**
Instead: return a valid `EvaluationBatch` with per-example failure scores (e.g., 0.0)…
Even better if the trajectories are also populated with the failed example, including
the error message."* Recommended reflective record schema at `:204-209`:
`{"Inputs", "Generated Outputs", "Feedback"}`.

### GEPA `optimize_anything` — `optimize_anything.py` `[SRC]`

- `objective` (`:100`) — *"Short goal statement… Surfaced verbatim by every engine."*
- `background` (`:101`) — *"Long-form context — problem statement, evaluation rules,
  domain notes. Surfaced verbatim."*
- `test_set` (`:102`) — *"the test set never enters the eval server, so engines and
  agents cannot see it."* **Structural isolation, not policy.**
- `oa/config.py:36-44` — **two budgets**: `max_evals` caps eval calls; `max_token_cost`
  caps *the optimiser's own LLM spend* and is *"**not** an eval-budget field"*.
  *"At least one of `max_evals` / `max_token_cost` must be set so a run is bounded."*
- `oa/config.py:56-60` — `sandbox: bool = True`, OS-jails subprocess engines.
- `gepa_launcher.py:756` — **`reflection_lm: LanguageModel | str | None = "openai/gpt-5.1"`**
  — the shipped default reflector is a *fixed strong model*, independent of the task
  model. This is AC-3.1b, already implemented by the reference optimiser.

### AdalFlow — `adalflow/adalflow/adalflow/optim/types.py` `[SRC]`

(Note: the previous pass cited this path one directory level short.)

```python
PROMPT     = ("prompt", ..., True)      # :28   trainable
DEMOS      = ("demos",  ..., True)      # :34   trainable
INPUT      = ("input",  ..., False)     # :39
OUTPUT     = ("output", ..., True)      # :40
HYPERPARAM = ("hyperparam", "Hyperparameters/args for the component.", False)  # :41
@dataclass
class EvaluationResult:  score: float  # [0,1]      # :71-78
                         feedback: str              # :79-85
```

The enum is literally `(name, description, default_trainable)`. **`HYPERPARAM` is
explicitly not trainable** — decoding parameters, tool sets and loop bounds are outside
the optimisable surface.

### Trace / Opto `[SRC]`

`opto/trace/nodes.py:10` — `node(data, name, trainable, description, constraint)`;
trainable parameters may be **arbitrary values with a declared `constraint`**, not only
strings. `opto/trace/bundle.py:27-34` — `bundle(...)` makes a **block of code** a
trainable parameter (the D22(b) capability, and why D22 needs sandboxing).

### SAMMO — structural addressing `[SRC]`

`sammo/search_op.py:13` — `__all__ = ["one_of", "many_of", "permutate", "optional", ...]`
(built on `pyglove.core.hyper.{OneOf, ManyOf}`): the search space is *declared with
combinators, not code*.
`sammo/css_matching.py:65` — `find_all(css_expression)` over an XmlTree built from
`reference_id → id`, `reference_classes → class`; the README targets a markdown section
by id: `Paraphrase("#instr")`.
`sammo/mutators.py` — typed, named mutators: `Paraphrase`, `ShortenSegment`,
`SegmentToBulletPoints`, `RemoveStopWordsFromSegment`, `DropExamples`, `DropIntro`,
`RepeatSegment`, `ChangeDataFormat`, `ChangeSectionsFormat`,
`DecreaseInContextExamples`, `APO`, `APE`, `InduceInstructions`, `PruneSyntaxTree`,
`BagOfMutators`.

### Agent Lightning — `agentlightning/types/resources.py` `[SRC]`

`Resource` (`:36`), `LLM(endpoint, model, api_key, sampling_parameters)` (`:43-55`),
`PromptTemplate(template, engine: Literal["jinja","f-string","poml"])` (`:146-152`),
`NamedResources = Dict[str, ResourceUnion]` (`:172`),
`ResourcesUpdate(resources_id, create_time, update_time, version, resources)`
(`:192-206`). The optimisable surface is a **named, typed, versioned bag of resources
broadcast to executors**; `sampling_parameters` sits on `LLM`, so decoding parameters
are part of the optimisable set.

### PromptWizard — the only genuinely no-code optimiser config `[SRC]`

`demos/gsm8k/configs/promptopt_config.yaml` is a complete optimiser specification in
YAML with no code: `prompt_technique_name`, `unique_model_id`,
`mutate_refine_iterations`, `mutation_rounds`, `refine_instruction`,
`refine_task_eg_iterations`, `style_variation`, `questions_batch_size`,
`min_correct_count`, `max_eval_batches`, `top_n`, `task_description`,
`base_instruction`, `answer_format`, `seen_set_size`, `few_shot_count`,
`num_train_examples`, `generate_reasoning`, `generate_expert_identity`,
`generate_intent_keywords`. **This is the template for PACT's no-code `optimizer:` block
under D14.**

## 4.2 The two formalisms

### Maestro's joint objective — `2509.04642-maestro.pdf` §2 `[TBL]`

Node `v` is a stochastic function `F_v : X_v × c_v → Dist(Y_v)`, where `c_v` is
*"model family and weights θ_v, prompt ρ_v, tool set, decoding and control
hyperparameters"*. Edges carry adapter parameters `α_e` (*"templates, serializers,
schema maps"*); nodes carry merge parameters `β_v`, one per incoming edge.

> `C := {c_v}_{v∈V} ∪ {α_e}_{e∈E} ∪ {β_v}_{v∈V}`   (line 225)
>
> `max_{G∈𝒢, C∈𝒞} E[μ(Y_O,m)]  s.t.  E[c(G,C;x)] ≤ κ,  Ω(G) ≤ τ,  R_train(G,C) ≤ B`

Cycles: unroll `t = 1:T` or use a fixed-point operator (lines 227-233). Conditional
edges: activations `a_e ∈ {0,1}` with merge operators that ignore absences —
*"This subsumes routing/gating without committing to a particular mechanism"* (`:235-237`).

**`α_e` and `β_v` are missing from thesis §7.2's strategy list.** An inter-agent edge is
not a plain arrow; it is a typed transformation with tunable serialisation, and a node
with several parents needs a declared merge policy.

### The survey's three preconditions — `2603.22386` §3.1

> *"First, there must be an executable search space… Second, evaluation must be reliable
> enough to discriminate candidates. Third, the search space must embody a useful
> inductive bias: if candidate workflows are mostly invalid or semantically incoherent,
> black-box search quickly becomes prohibitively expensive. This is precisely why typed
> operators, code scaffolds, and constrained graph languages are so important."*

and §3.4: *"verification is not added after search; it is part of the optimization
process itself."*

**This is the strongest theoretical argument for PACT's existence.** A validated, typed
spec *is* the search space. `pact validate` is not developer hygiene — it is the operator
that keeps the optimiser's proposal distribution inside the feasible set.

## 4.3 The optimisability contract — consolidated

A spec is *optimisable* iff it exposes all of the following.

| # | Requirement | Source |
|---|---|---|
| O-1 | **Stable, addressable names for every text component**, including sub-document anchors (section ids), so one section can be rewritten. | gepa `adapter.py:12`; sammo `css_matching.py:65` + `Paraphrase("#instr")` |
| O-2 | **A typed `trainable` flag and a declared `constraint` per field.** | adalflow `types.py:28-41`; trace `nodes.py:10` |
| O-3 | **Instantiation from an override map**: `build(tree, {name: text}) → runnable agent`, with no source-tree edits. | dspy `gepa_utils.py:136-142` |
| O-4 | **Per-component trajectories** recording that component's inputs, outputs and a textual feedback string. | gepa `adapter.py:183-215` |
| O-5 | **Evaluation returns `(score: float, feedback: str)` per example**, plus optional `objective_scores`. **Never raise on per-example failure** — score it 0 and record the error. | gepa `adapter.py:31-34,134-140`; adalflow `types.py:71-85`; deepeval `base_metric.py:49-55` |
| O-6 | **`objective` (short goal) and `background` (domain + evaluation rules) as first-class contract fields**, surfaced verbatim. | gepa `optimize_anything.py:100-101` |
| O-7 | **Train / val / test splits with the test split structurally unreachable from the optimiser.** | gepa `optimize_anything.py:102` |
| O-8 | **Two budgets: eval budget and optimiser-spend budget. Reject unbounded runs.** | gepa `oa/config.py:36-44` |
| O-9 | **A reflection/teacher model binding independent of the execution model**, defaulted to a strong model. | gepa `gepa_launcher.py:756` (`"openai/gpt-5.1"`); ACE Table 16; Trace README:391-399 |
| O-10 | **Node config = {model, prompt, tool set, decoding params, control params}; edge config = adapter/serialiser params; per-node merge policy.** All addressable. | maestro §2 (`:225`) |
| O-11 | **Explicit budgets in the objective**: cost `κ`, structure `τ` (node/edge count), rollouts `B`. | maestro §2.2 (`:252-271`) |
| O-12 | **A declarative search space** (`oneOf` / `manyOf` / `optional` / `permutate`). | sammo `search_op.py:13` |
| O-13 | **A typed, statically-validatable IR** so most proposals are legal by construction. | workflow-opt-survey §3.1, §3.4 |
| O-14 | **Versioned, named resource delivery at runtime** (`resources_id`, `version`) so a candidate can be swapped without redeploying. | agent-lightning `resources.py:172-206` |
| O-15 | **Optimiser hyperparameters declared per model tier, not globally.** | gepa Obs. 5 (Merge: +13.33 on mini, IFBench 38.61→28.23 on Qwen3-8B); skillopt Table 2(e) |
| **O-16** | **The harness/adapter binding is part of the optimised artifact's identity.** An artifact is valid for `(model × harness)`. **NEW** | skillopt Table 4(b): cross-harness gain capture 10.2%–102.4% |
| **O-17** | **A no-code selector for verification/ensembling.** DSPy's `BestOfN`/`Refine` take `reward_fn: Callable` — code. Under D14 the selector must be an eval-metric reference plus a threshold. **NEW** | dspy `best_of_n.py:37-47`, `refine.py:41-52` |
| **O-18** | **Mechanism gains must be recorded as measured, never summed.** Stacked mechanisms are ~61% of the naive sum. **NEW** | effgen Table 3 `[DER]` |

## 4.4 What today's leading framework does NOT expose — the gap PACT fills

DSPy's optimisable surface is exactly *the instruction string of every `dspy.Predict`
reachable by attribute path*:

- `dspy/teleprompt/gepa/gepa.py:575` — `seed_candidate = {name: pred.signature.instructions
  for name, pred in student.named_predictors()}`
- `dspy/primitives/module.py:131-141` — `named_predictors()` returns
  `(attribute path, Predict)` pairs.

Therefore **DSPy + GEPA cannot optimise**: the loop (`ReAct.__init__` hard-codes
`max_iters: int = 20`, `dspy/predict/react.py:17`), the tool exposure set
(`tools: list[Callable]`, same line), the model binding, decoding parameters, the
adapter/serialisation choice, or the topology. AdalFlow marks `HYPERPARAM`
`default_trainable=False`. Neither can express a structurally-different small-model
variant (§2.4).

**This is precisely PACT's opening.** If the loop, tool exposure, model binding, decoding
parameters, harness and topology are *authored data in the tree* rather than constructor
arguments in code, one optimizer ABI can mutate all of them.

### A structural advantage that follows, and is not yet claimed

DSPy's `Refine` module must feed the reflecting LLM a synthesised description of the
program: `program_code`, `modules_defn`, `program_trajectory`, `reward_code`
(`dspy/predict/refine.py:23-38`). **In PACT those inputs are the spec tree and the eval
files themselves** — already YAML/Markdown, already human-legible, already anchored.
PACT's declarative form is *more* legible to a reflective optimiser than Python source
is. That is a concrete, defensible advantage of D2 (tree as native form) for T4, and it
belongs in the architecture.

---

# 5. Corrections to the thesis as currently written

These three are already quoted in `00-THESIS.md` and are wrong or unsupported.

## 5.1 AC-3.1b's evidence is mis-attributed `[TBL]`

**Current text:** *"reflective-optimisation gain collapses with reflector strength (ACE:
+17.1 at 671B → +7.6 at 120B → +2.4 at 70B)."*

**What the source says.** Those three numbers come from ACE Tables 1, 5 and 9. Table 1
and Table 5 are **AppWorld**; Table 9 is **FiNER** — a different benchmark. And ACE §A.1
states explicitly: *"In each case, the Generator, Reflector, and Curator were **all**
switched to the new model."* So the ladder (a) mixes benchmarks and (b) confounds
generator capability with reflector capability. **It is not a reflector-strength
measurement.**

**The controlled measurement exists** — ACE Table 16, generator and curator fixed at
DeepSeek-V3.1 on FiNER: reflector GPT-OSS-120B → 76.6 (+5.9); DeepSeek-V3.1 → 78.3
(+7.6); GPT-5.1 → 78.5 (+7.8). Reflector strength is worth **1.9 pp of 7.8 (24%)** and
**saturates**.

**Consequence.** AC-3.1b survives, but its rationale changes and gets *stronger*:

- Not *"gain collapses with reflector strength"* (it degrades ~24% and saturates), but:
- **(i)** a *corrupted* reflector flips the sign (+7.6 → −4.0, ACE Table 17), so the
  binding must be controllable and auditable;
- **(ii)** on a weak target, re-optimising can be **worse than importing** (SkillOpt 4a);
- **(iii)** TextGrad/GEPA driven by weak models are measurably destructive (−24.0 pp
  cells; GEPA −3.09 below baseline on Llama-3.3-70B);
- **(iv)** it is **nearly free** — 17–92 reflection calls per benchmark, $86 for GEPA's
  full 6-benchmark run — so there is no cost reason to collapse the bindings;
- **(v)** the reference implementation already defaults this way
  (`gepa_launcher.py:756` → `"openai/gpt-5.1"`).

The valid *base-model* ladder should be stated separately and within-benchmark:
AppWorld online ACE +17.1 (671B) vs +7.6 (120B); FiNER ACE +7.6 (671B) vs +2.4 (70B).
That is a statement about **executor capability setting the ceiling** — which belongs in
Q3/C4, not in AC-3.1b.

## 5.2 §7.3's constrained-decoding row is wrong on both halves `[SRC]`

**Current text:** *"Constrained decoding | +34.4 pp (BFCL, claude-3-haiku) |
Substrate-bound: regex/CFG unavailable on hosted OpenAI/Anthropic APIs."*

The +34.4 pp figure comes from a technique whose own source says it was achieved
*"without using JSON-mode or any kind of constrained generation"* (§2.3). The
substrate-bound caveat is true, but it applies to a **different** mechanism (L3) whose
effect size is **not measured anywhere in this corpus**. The row must be split into
L1/L2/L3 with L3's effect size marked unknown.

## 5.3 AgentSquare is not weak-executor evidence `[TBL]`

`2410.06153-agentsquare.pdf` reports *"an average performance gain of 17.2% against
best-known human designs"* on **GPT-4o** and **GPT-3.5-turbo-0125** (§4.1, §5.1). Both
were frontier-tier at publication. The number must be removed from the "gain on a weak
executor" column of §7.3.

## 5.4 §7.3's mechanism ordering is contradicted by measurement `[TBL]`

§7.3 lists **Decomposition** as mechanism #1 with the rationale *"Weak models fail at
composition, not at each component."* EffGen Table 3 measures the opposite: removing task
decomposition costs **−3.3 pp at 1.5B** and **−5.5 pp at 32B**. Decomposition is worth
*less* on the small model. This is consistent with the depth law (`γ = 6.7b + 1.09 > 1`,
`γ` rising with routing fragility) and with `2601.12307`'s single-agent baseline.

**Prompt/context and procedural specification must be #1 and #2; decomposition and
topology must move to the bottom of the ordered list**, gated on the cheap mechanisms
being exhausted (which MASS's staged schedule already implies, and which §7.3's prose
already says two paragraphs later — the *table* and the *prose* currently disagree).

## 5.5 Other standing corrections carried forward and re-verified

| # | Finding | Evidence |
|---|---|---|
| N3 | The published cross-model transfer evidence is **weak → strong**. GEPA-Qwen-Opt (optimised entirely on Qwen3-8B) scores **62.03 on GPT-4.1-Mini, +9.00 over baseline**, beating MIPROv2 (+5.64), TextGrad (+6.11) and Trace (+3.27) which optimised *directly on mini*. | gepa Table 2 `[TBL]` |
| N7 | **ACE's flagship "matches GPT-4.1 agent" result uses DeepSeek-V3.1-671B**, an MoE. "Smaller" there means *open-weight*, not *small*. Never cite as SLM evidence. | ace §4.3 |
| N8 | **TextGrad's headline is unsupported by its own table.** The abstract claims GPT-3.5 pushed "close to GPT-4"; Table 3 contains no GPT-4 numbers. | textgrad §1 vs Table 3 |
| N9 | **TextGrad's numbers were not reproducible.** Trace: *"The numbers in the original paper cannot be reproduced exactly despite using the released TextGrad code."* (BBH Word Sorting 79.8 reported vs 72.0 reproduced.) | trace-msr fn. 9 |
| N10 | **Agent Lightning publishes no absolute numbers** — reward curves only (Figs. 5–7). It is an *architecture* to copy, not an evidence source. | agent-lightning §4.1-4.3 |
| N11 | **Routing is not portability** — verified from source (§2.2 row 10). | routellm `evals/evaluate.py:77-114` `[SRC]` |
| N15 | **LiteLLM's default remedy for capability mismatch is silent deletion.** `drop_params=True` pops unsupported params; otherwise `UnsupportedParamsError`. | litellm `utils.py:2874-2886` `[SRC]` |

## 5.6 The model catalogue has no quality axis — and worse, no *tri-state* `[SRC, DER]`

`routing/litellm/model_prices_and_context_window.json`, enumerated this pass:

```
total entries : 2984          distinct keys : 145
with `source` :  921  (30.9%)
keys matching grammar|cfg|regex|constrain|logit : NONE
keys matching mmlu|bench|score|quality|elo|gpqa|swe|aime : NONE
```

| Capability key | true | false | **ABSENT** | absent % |
|---|---|---|---|---|
| `supports_function_calling` | 1667 | 60 | 1257 | 42.1% |
| `supports_vision` | 888 | 92 | **2004** | **67.2%** |
| `supports_response_schema` | 879 | 72 | **2033** | **68.1%** |
| `supports_reasoning` | 770 | 37 | 2177 | 73.0% |
| `supports_parallel_function_calling` | 513 | 47 | 2424 | 81.2% |
| `supports_web_search` | 260 | 10 | 2714 | 91.0% |
| `supports_computer_use` | 166 | 2 | **2816** | **94.4%** |
| `supports_audio_input` | 105 | 4 | **2875** | **96.3%** |
| `supports_audio_output` | 62 | 45 | 2877 | 96.4% |

> **This is a direct threat to D16 + AC-3.2.** D16 puts all four modalities in v1;
> AC-3.2 says predicates filter candidates *before any eval runs*. On the industry's
> most complete catalogue, the computer-use and audio capabilities are **unknown for
> 94–96% of models**. A two-valued predicate silently mis-resolves either way: treating
> absent as `false` discards 94% of the catalogue; treating it as `true` binds models
> that cannot do the job.
>
> **The capability lattice must be three-valued (`true | false | unknown`)**, and
> `strict` mode must treat `unknown` as a *resolve-time failure with a named remedy*
> ("run `pact probe <model>` to measure it"), never as either boolean.

---

# 6. Findings that strengthen the thesis

| # | Finding | Evidence |
|---|---|---|
| P1 | Against the **realistic** reference (the author's hand-written frontier strategy), an optimised small model averages **98.4% / 113.8% / 103.4%** across three independent 6–8-benchmark suites. | §1.3 `[DER]` |
| P2 | Procedural specification is the largest single lever: **+50.7 pp** best case, **+16.6 pp** mean over 18 model×harness configs, in-repo bench 3 reproduction (0 → 81.2 from one gated edit). | skillopt T1; skillsbench §5.1; `RESULTS.md:77` |
| P3 | **Human-authored skills beat model-authored skills by up to +29.7 pp on the same cell**, and self-generated skills land *below* the no-skill baseline on all three dedicated harnesses. | skillopt Table 1; skillsbench §5.1.1 |
| P4 | **Compact beats comprehensive**: 2–3 skills +19.0 vs ≥4 +10.1; standard-length +21.5 vs comprehensive prose **+0.7**. GEPA's optimised prompts are up to **9.2× shorter** than MIPROv2's. | skillsbench Finding 6; gepa Obs. 4 |
| P5 | **Verification tolerates a mediocre judge but not a corrupted one.** ReasoningBank measured its judge at 72.7% and reports SR unaffected across 70–90%; ACE's harmful reflector flips +7.6 → −4.0 only at maximum injection frequency. | rb §4.4; ace Table 17 |
| P6 | **A well-typed, statically-validatable IR is the precondition for cheap search**, not a nicety. | workflow-opt-survey §3.1, §3.4 |
| P7 | **Prompts before topology, quantified**: 79.9% of MASS's total gain is prompt-side. | mass Table 6 `[DER]` |
| P8 | **Offline optimisation is economically feasible under D17.** Maestro reaches 70.33 on HotpotQA in **240 rollouts** vs GEPA's >6,000; GEPA's full 6-benchmark Table-2 run cost **$86** and used **17–92 reflection calls per benchmark**. | maestro §1; gepa §E.3, Table 4 |
| P9 | **PACT's declarative form is a genuine optimiser advantage** — the `program_code` / `modules_defn` inputs DSPy must synthesise for reflection are free when the strategy is already YAML/Markdown. `[INF from SRC]` | dspy `refine.py:23-38` |
| P10 | **Grammar-constrained decoding is fully available exactly where D17 puts PACT** (vLLM / SGLang / llama.cpp / transformers) and unavailable in the cloud. | outlines backend matrix §2.3 `[SRC]` |

---

# 7. Direct implications for the PACT documents

## 7.1 AC-3.1 — keep the revised form, add the harness

The current revised AC-3.1 is sound. One addition: the reference must name the
**harness**, because a strategy is valid for `(model × harness)` (§1.1.2). Reporting
`score / R_authored` without stating which harness both were measured under is not a
comparison.

## 7.2 AC-3.1b — keep the criterion, replace the evidence

See §5.1. The rewritten justification should read: *the optimiser model is a separate
binding because a corrupted reflector inverts the sign of the gain, re-optimising on a
weak target can be worse than importing, weak-model-driven optimisers are measurably
destructive, the reference implementation already defaults this way, and it costs tens
of calls.*

## 7.3 New: bind the harness in the lockfile

`pact.lock` must record `(agent, variant, model, adapter, harness-config, runtime,
tools) + verdict`, and re-resolution must be forced when the harness changes. P-4 should
read *"Model **or harness** swap never silently degrades."*

## 7.4 Capability vocabulary

```yaml
structured_output: [none, json_mode, json_schema, regex, cfg]   # ordered enum
schema_repair:     [none, sap]                                  # harness-provided, substrate-free
```

Lattice keyed on `(model_id, provider, runtime)`. Three-valued: `true | false | unknown`;
`strict` mode fails on `unknown` with a probe remedy.

## 7.5 Optimizer ABI (O3.4 / E-5)

```
optimize(
  spec_tree,                       # D2 native form
  components: [ComponentRef],      # O-1: names incl. section anchors
  eval_suite,                      # O-5: returns (score, reason) per case
  splits: {train, val, test},      # O-7: test structurally unreachable
  objective: str, background: str, # O-6
  budgets: {evals, optimiser_cost, rollouts, structure},  # O-8, O-11
  models: {execution, reflection}, # O-9: independent bindings
  harness,                         # O-16: part of the artifact's identity
  search_space,                    # O-12: oneOf/manyOf/optional/permutate
  optimiser_config                 # O-15: per-tier, lives in the variant
) -> (candidate_tree_diff, verdict, provenance)
```

## 7.6 Additions to the strategy space (§7.2)

- **edge adapter parameters `α_e`** — templates, serialisers, schema maps per edge;
- **merge policy `β_v`** per node with more than one incoming edge;
- **structure budget `Ω(G) ≤ τ`** (max nodes / max edges) as an authored constraint;
- **the harness / scaffolding level itself**, including "no harness";
- **optimiser hyperparameters inside the variant** — SkillOpt Table 2(e) shows scheduler
  choice alone moves SpreadsheetBench 80.7 (constant) vs 72.9 (linear), a 7.8-pt swing.

## 7.7 Authoring surface

`instructions.md` and every skill document must carry **stable section anchors** (SAMMO's
`#instr` pattern) so the optimiser can rewrite one section
(`components_to_update` is a *list*), D23's classifier can attribute a diff to a section
kind, and the Learning IR emits minimal diffs.

Skill frontmatter must carry the **complexity contract**: expected tool/token cost,
**applicability boundaries**, and a **required lightweight fallback path**. SkillsBench
names this as the root cause of all 13 negative tasks: *"a single 'correct' pipeline
without applicability boundaries or lightweight fallbacks."*

## 7.8 Learning-loop defaults justified by evidence

| Default | Value | Justification |
|---|---|---|
| Reflection model | strongest available, **never** the target | §5.1; gepa `gepa_launcher.py:756` |
| Skill count per agent | cap at **3** | skillsbench Finding 6 (2–3 = +19.0; ≥4 = +10.1) |
| Skill length | standard (≈300–2,000 tokens) | skillsbench (+21.5 vs +0.7 comprehensive) |
| Skill authorship | **human-first**; model-authored skills require a stricter gate | skillopt T1 (human +31.1 vs LLM +1.4); skillsbench −8.1/−11.3/−11.5 |
| Judge accuracy floor | **70%**, measured on a labelled subset | reasoningbank §4.4 |
| Candidate acceptance | strict improvement on a **structurally isolated** held-out split | gepa `optimize_anything.py:102` |
| Mechanism stacking | never sum predicted gains; measure the stack | effgen Table 3 (~61% of naive sum) |
| Topology search | **gated** on prompt/skill optimisation being exhausted | mass Table 6; effgen Table 3; `2601.12307` |
| Optimiser budget | two caps (evals, optimiser spend); refuse unbounded | gepa `oa/config.py:36-44` |
| Search order | config-first, graph-second | maestro (240 vs >6,000 rollouts) |

## 7.9 D11 — the failure report should carry a mechanism ledger

```
PORTABILITY: FAIL for qwen3-4b @ harness=pact-native
  spreadsheet_exact_match 0.239 < 0.700 required (best of 14 candidate strategies)
  FAILURE CLASS: long-horizon procedural + strict output contract
    — mechanism ceiling: skill optimisation reached 57.2% of the frontier's
      un-optimised score on the closest published analogue (SkillOpt,
      SpreadsheetBench, Qwen3.5-4B). Re-optimisation is unlikely to close this.
  MECHANISMS TRIED (measured, not predicted):
      skill synthesis            +14.6
      schema-aligned parsing     +3.2
      tool curation              +2.1
      grammar-constrained decode  n/a  (provider=anthropic lacks logit access)
      self-consistency k=5       +1.8   (5.0x cost)
      decomposition K=3          -2.4   (depth penalty; gamma-hat 1.31)
  NOTE: mechanism gains are not additive (~61% of sum observed).
RECOMMENDED: qwen3-14b — passes at 0.83, 3.1x cheaper than your current binding
```

---

# 8. Open questions this review could not settle

1. **No published measurement of full strategy re-synthesis** (topology + decomposition +
   tools + loop + harness) for a downgrade. SkillOpt varies only the skill; AFlow and
   MaAS only the workflow; MASS re-runs the pipeline per model. PACT's own bench must
   produce this. *(Partially narrowed this pass: MaAS Table 7 gives workflow transfer
   but no re-optimised-on-target row, so gain capture is still unmeasured.)*
2. **No evidence for downgrade portability in vision, audio, or computer use.** Every
   measurement above is text or text+tools. D16 requires all four modalities in v1 and
   the corpus is silent on three. This is now compounded by §5.6: the catalogue does not
   even record those capabilities for 94–96% of models.
3. **The 4B/7B tier is barely represented.** Truly small models in the corpus:
   Qwen3.5-4B, Llama-3.2-3B (no absolute numbers), Qwen2.5-1.5B/3B (EffGen only),
   MiniMax M2.7 and Gemini 3.1 Flash Lite (SkillsBench only).
4. **Whether PACT's harness underperforms native is still unmeasured** — but §1.1.3 now
   shows the harness axis is worth ±20 pp on a frontier model, so this is a *large*
   unquantified risk to D12, not a small one. F-4 must measure harness-vs-native **and**
   harness-vs-raw.
5. **Air-gapped optimisation wall-clock is still unpublished.** Rollout counts are now
   well bounded (Maestro 240–2,220; GEPA 1,839–7,051; reflection calls 17–92), and GEPA's
   dollar cost is known ($86 on a hosted model), but nobody has published wall-clock on a
   local model. Feasibility under D17 is *inferred* from rollout counts, not demonstrated.
6. **Can `γ` (the depth penalty exponent) be estimated at resolve time?** `γ = 6.7b + 1.09`
   requires the model's routing fragility `b`, which requires a per-model exposure sweep.
   Whether that probe is cheap enough to gate decomposition automatically is untested.
7. **Is SAP's +34.4 pp reproducible outside BAML's own harness?** It is the largest
   substrate-free small-model gain in the corpus and rests entirely on one vendor
   benchmark. PACT should reproduce it before depending on it.
8. **MaAS's prose contradicts its own Table 7** (§1.1.4). Unresolved; I used the table.

---

# 9. Evidence index

## 9.1 Source files read this pass

```
optim/gepa/src/gepa/core/adapter.py                     :12,16,31-35,81,125-145,183-215,217
optim/gepa/src/gepa/optimize_anything.py                :93-160 (esp. 96,100-102)
optim/gepa/src/gepa/oa/config.py                        :24-95  (esp. 36-44,56-60)
optim/gepa/src/gepa/gepa_launcher.py                    :731,756-761,1385-1400
optim/dspy/dspy/teleprompt/bootstrap_finetune.py        :34-133,245-295  (NEW)
optim/dspy/dspy/teleprompt/bettertogether.py            :1-60            (NEW)
optim/dspy/dspy/teleprompt/ensemble.py                  (whole)          (NEW)
optim/dspy/dspy/predict/best_of_n.py                    :1-60            (NEW)
optim/dspy/dspy/predict/refine.py                       :1-60            (NEW)
optim/dspy/dspy/teleprompt/gepa/gepa.py                 :575
optim/dspy/dspy/primitives/module.py                    :131-141
optim/dspy/dspy/predict/react.py                        :16-17
optim/adalflow/adalflow/adalflow/optim/types.py         :13-90   (path corrected)
optim/trace/opto/trace/nodes.py                         :10-45
optim/trace/opto/trace/bundle.py                        :27-51
optim/trace/README.md                                   :389-399
optim/sammo/sammo/search_op.py                          :1-30
optim/sammo/sammo/css_matching.py                       :55-75
optim/sammo/sammo/mutators.py                           (class list)
optim/promptwizard/demos/gsm8k/configs/promptopt_config.yaml  (whole)
optim/agent-lightning/agentlightning/types/resources.py :36,43-55,146-152,172,192-206
optim/outlines/src/outlines/models/{anthropic,openai,gemini,mistral,ollama,
    lmstudio,tgi,dottxt,llamacpp,mlxlm,sglang,transformers,vllm,vllm_offline}.py  (NEW full sweep)
optim/outlines/src/outlines/backends/{base,outlines_core,llguidance,xgrammar}.py  (NEW)
optim/guidance/guidance/models/_openai_base.py          :596
optim/baml/fern/01-guide/why-baml.mdx                   :335-380
optim/baml/typescript2/app-website/blog-content/2024-08-13-bfcl-sota.mdx        :1-80  (NEW read)
optim/baml/.../2025-12-14-structured-outputs-create-false-confidence.mdx        :1-70
routing/routellm/routellm/evals/evaluate.py             :55-125
routing/litellm/model_prices_and_context_window.json    (2,984 entries re-enumerated)
routing/litellm/litellm/utils.py                        :2819-2890
```

## 9.2 Papers re-extracted and read this pass

```
2507.19457-gepa.pdf                 Tables 1,2,4(App.N); Obs 1-6; §E.2,E.3,E.4
2502.02533-mass.pdf                 Tables 1,4(App.C.1),5,6,8,9      <- C.1 is NEW
2605.23904-skillopt.pdf             Tables 1, 4(a)(b)(c)             <- 4(b) is NEW
2510.04618-ace.pdf                  Tables 1,5,9,16,17; §A.1,A.4     <- 16,17 are NEW
2509.25140-reasoningbank.pdf        Table 1; §4.4 judge calibration
2509.04642-maestro.pdf              §1 results (:171-178); §2 formalism (:225,252-271)
2410.10762-aflow.pdf                Table 2
2410.06153-agentsquare.pdf          §abstract, §4.1 (model setup)    <- corrects prior use
2406.07496-textgrad.pdf             Table 3
2406.16218-trace-msr.pdf            Table 2; fn. 9
2508.03680-agent-lightning.pdf      §4.1-4.3 (NO result tables)
2602.12670-skillsbench.pdf          Table 2 (18 configs), Table 3, §5.1.1-5.1.3, §6
2605.16508-skill-scaling-laws.pdf   Prop. 2 (:1503-1520); gamma fit (:223,292)
2603.22386-workflow-opt-survey.pdf  §3.1-3.4
2601.12307-single-agent-baseline.pdf §abstract
arxiv-2602.00887 (EffGen)           Tables 2, 3; §4 error analysis; §5  <- verified from PDF
2502.04180-maas.pdf                 Tables 4,7,8  <- RECOVERED (see §0.1 C1)
```

### MaAS recovery procedure (reproducible)

The file is truncated: no `%%EOF`, no xref table. `pdftotext`, `pypdf(strict=False)` and
`gs -sDEVICE=pdfwrite` all fail. Recovery:

1. Scan the raw bytes for `stream\r?\n … endstream` pairs (401 found).
2. `zlib.decompress` each; 197 succeed, 204 are image/binary and fail.
3. Keep streams containing `BT`; concatenate the parenthesised string operands inside
   each `BT…ET` block in order.
4. Decode `latin-1`. Ligatures arrive as octal escapes (`\002` = fi, `\003` = fl,
   `\050`/`\051` = parens, `\030` = en-dash); word spacing is lost (kerning is expressed
   as `TJ` array offsets, which this method drops), so the text reads without spaces but
   is unambiguous for numeric tables.

Script retained at
`/tmp/claude-1000/-home-bud-ditto-agent-inter-op/a71e8707-3faa-4fba-960b-ca7089ccdd16/scratchpad/tx/`.

## 9.3 In-repo prior research consumed

```
/home/bud/ditto/gaia-ai-runtime/research/SYNTHESIS.md   F1-F6 (built on, not repeated)
/home/bud/ditto/gaia-ai-runtime/research/RESULTS.md     bench 1 (:21-26), 2 (:44-48), 3 (:73-77)
/home/bud/ditto/agent-inter-op/research/notes/web-frontier.md   §3.1 (EffGen — re-verified from PDF)
/home/bud/ditto/agent-inter-op/research/notes/gap-r2-1.md       N16 correction (carried forward)
```
