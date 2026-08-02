# Gap R2-3 — Effect size for `propose-only` learning (H37)

**Date:** 2026-07-26  **Round:** 2, gap 3  **Bet under test:** H37 `[R5]`
**Binding inputs:** `docs/00-THESIS.md` (T6, T7), `docs/01-DECISIONS.md` (D9, D13, D14,
D17, D18, D22, D23), `docs/20-ARCHITECTURE-DRAFT.md` §8.5, §8.7, §8.10, §11.10, §13.15.3,
§14.1.

**The gap, as stated in R5.** *"`propose-only` learning has no measured effect size. Y8
makes core-tier learning human-gated because the statistics are unaffordable at n=10 —
which is honest, but nothing in the corpus measures whether a weekly human review queue
produces net improvement at a support lead's cadence."* (`20-ARCHITECTURE-DRAFT.md:8600-8605`).
H37's falsifier: *"20 weeks of `propose-only` in the D9 run producing no proposal a human
accepts"* (`:8768`).

**Verdict up front.**

| Sub-claim | Status after this pass |
|---|---|
| **H37b — a human accepts a non-trivial fraction of machine-proposed edits** | **CLOSED against two independent production deployments** (plus one corroborating, unverified-at-source): **63.6%** at the reviewer gate (Google, ICSE-SEIP '24 Table 1), **~30%** per suggestion (Copilot/Accenture), ~60% (Getafix — blog-sourced, §2.3). H37's stated falsifier requires a per-proposal accept probability **below 0.86%** (at 80 proposals) or **3.4%** (at 20) — 9× to 74× below the weakest of these |
| **H37c — a human review gate is worth its ceremony vs. a machine gate alone** | **CLOSED, and the direction is the opposite of the worry.** Google *lowered* their model's precision threshold from 50% → 40% *because* a human gate was added, and end-to-end acceptance **rose 4.9% → 7.5%** |
| **H37a — the cycle emits any proposal at all at n ≈ 10** | **STILL OPEN.** Every analogue measures accept-rate *given a proposal was shown*. Nothing measures proposal **yield** at a support lead's traffic. This is the real residual and it was not where R5 pointed |
| **H37d — H37 is falsifiable as specified** | **NO — and that is a shipped defect.** `propose-only` records approvals (§8.10) and records nothing about rejections, so the D9 run cannot produce the data that would falsify H37. Fixed below |
| **Bonus defect found** | §11.10 prints *"Expected 1-4 accepted proposals (median 2.5, from the reference runs)"* citing SkillOpt Table 6 — but **that figure is post-held-out-gate, and Y8 deleted the gate.** The propose-only queue is therefore **unbounded**, and lands in the 46–96% override regime |

**Evidence hygiene.** Three new PDF extracts are stored under
`research/extracts/` with `SHA256SUMS.gap-r2-3`, `pdftotext version 24.02.0`, flag
`-layout` — per §13.12's outstanding debt. Line numbers below refer to those stored
extracts. Source-code citations are `path:line` against `research/repos/`, read in source.

---

## 1. Corpus sweep — the negative result, itemised

R5 asserted "nothing in the corpus measures it". That is **confirmed**, and the shape of
the misses is itself informative. What I checked and what each actually does:

| System / paper | What I read | What it models | Why it is not H37 evidence |
|---|---|---|---|
| **Langfuse annotation queues** | `eval/langfuse/packages/shared/prisma/schema.prisma:490-524` | `AnnotationQueueItem {objectId, objectType, status, lockedAt, lockedByUserId, annotatorUserId, completedAt}`; `enum AnnotationQueueStatus { PENDING, COMPLETED }`; `AnnotationQueueObjectType { TRACE, OBSERVATION, SESSION }` | **The leading LLM-ops review queue has no accept/reject.** It is a *scoring* queue over traces, two-valued on progress only. A human's *decision* is not a first-class value anywhere in the schema. Nothing to measure |
| **Dify annotation reply** | `frameworks2/dify/api/models/model.py:1344-1350, 1739-1750`; `api/services/annotation_service.py` | Human-authored corrected answers keyed to messages, with hit history | Human *authoring*, not human *adjudication* of a machine proposal |
| **Roo-Code auto-approval** | `filedef/roo-code/packages/types/src/global-settings.ts:97-118` | `autoApprovalEnabled` + **ten** `alwaysAllow*` keys (`ReadOnly`, `ReadOnlyOutsideWorkspace`, `Write`, `WriteOutsideWorkspace`, `WriteProtected`, `Mcp`, `ModeSwitch`, `Subtasks`, `Execute`, `FollowupQuestions`), plus `followupAutoApproveTimeoutMs`, `allowedMaxRequests`, `allowedMaxCost` | **A measured market outcome, not an effect size** — and a warning. Per-action human review did not survive contact with users: the shipped answer is granular bypass *plus a timeout that approves by default*. See §4 |
| **ExpeL** | `memory/expel/agent/expel.py:666, 704-741`; `configs/agent/expel.yaml:4,8` | Operators `ADD/EDIT/AGREE/REMOVE` with a counter: `ADD` → 2 (`:739`), `AGREE`/`EDIT` → +1 (`:734,737`), `REMOVE` → −1, or **−3 when the library is full** (`:730-731`), prune at counter ≤ 0 (`:740`). `max_num_rules: 20`, critique batches of `success_critique_num: 8` trajectories | The reviewer is **an LLM**, not a human. Already adopted verbatim by §8.5 (`20-ARCHITECTURE-DRAFT.md:6013-6016`). Confirms the *operator algebra* at small n; measures no human |
| **GEPA** | `optim/gepa/src/gepa/strategies/acceptance.py:44-53`; `api.py:157, 355`; `strategies/batch_sampler.py:34-101` | `StrictImprovementAcceptance.should_accept` = `sum(after) > sum(before)`; `reflection_minibatch_size` **defaults to 3** | The reference reflective optimiser proposes from **three** examples and accepts on a strict-improvement comparison over those three. Relevant to yield (§3) and to why a human gate is needed at all; measures no human |
| **SkillOpt** | `research/extracts/skillopt.txt:816-849, 25, 713` | Table 6: accepted edits per full run = **1–4, median 2.5**; *"the optimizer model proposes many more edits per epoch, but only a handful pass the held-out check"* (`:846-848`); an edit *"is accepted only when it strictly improves a held-out"* score (`:25`, `:713`) | **Post-gate.** See §5 — this is the number §11.10 mis-cites |
| **Voyager, AWM, mem0, letta, cognee, zep, reflexion** | scanned for a human accept/reject record | none has one | Learning is machine-gated or ungated throughout the memory corpus |

**Conclusion of the sweep.** No system in the 141-repo corpus records a human's
accept/reject decision over a machine-proposed *specification diff*. PACT is not
adopting a review-queue design; it is **defining one**, and it must define the outcome
vocabulary itself.

---

## 2. Web evidence — three measured deployments, and one bound

### 2.1 Google, *Resolving Code Review Comments with Machine Learning*, ICSE-SEIP '24 — the closest analogue that exists

This is the single most useful external result for H37, because it measures a **two-stage
human review queue over machine-proposed diffs** in production. Table 1
(`research/extracts/google-crc-ml.txt:513-531`):

| Stage | V1 (% of total) | V1 (% of prev) | V2 (% of total) | V2 (% of prev) |
|---|---|---|---|---|
| Incoming comments | 100.0 | 100.0 | 100.0 | 100.0 |
| Confident predictions | 34.3 | 34.3 | 49.0 | 49.0 |
| **Accepted by reviewer** | — (no reviewer stage) | — | **33.1** | **63.6** |
| Previewed by author | 10.7 | 31.3 | 10.7 | 34.5 |
| **Applied by author** | **4.9** | 45.6 | **7.5** | **69.5** |

Five findings, each verified in the stored extract:

1. **The human accept rate at the review gate is 63.6%** (`:521`, `:568`). Prose: *"over
   63% are accepted by the reviewer and attached to the comment to be sent to the author"*
   (`:568-569`). This is neither zero nor rubber-stamping — **36.4% are rejected**.
2. **Adding the human gate let them lower the model's precision bar, and end-to-end
   acceptance went up.** *"When reviewers were given the ability to approve or reject
   suggested edits (§5), we were able to reduce the target precision further to 40%, which
   increased recall@40 even further, while still improving downstream acceptance"*
   (`:286-289`); *"since the reviewer can reject obviously incorrect suggested edits, we
   could be even more aggressive with ML confidence thresholds, dropping the V2 minimum
   precision to 40% from 50% and, therefore increasing the number of comments that received
   ML suggestions"* (`:439-445`). Measured consequence: **4.9% → 7.5% of all comments
   resolved** (`:486`, `:543-548`) — a **53% relative increase in delivered value from
   adding a human review step.** This is the direct refutation of "propose-only is
   ceremony": in the one place it has been measured, the human gate *raised* the system's
   useful operating point rather than taxing it.
3. **Weekly aggregate acceptance is stable at a weekly cadence**: V2 *"weekly aggregate
   acceptance rates since full deployment started ranged between 5.4% and 7.5% with a
   standard deviation of about 0.9 percentage points"* (`:548-551`); V1 3.9–5.5% over a
   3-month deployment (`:488-489`). PACT's `review: weekly` is the same cadence.
4. **Placement and latency moved acceptance more than model quality did.** *"only 20% of
   suggested edits were previewed by developers through a click on the 'Show fix' button. A
   UI update that combined the two sources of information … improved discoverability
   considerably (up to about 30%)"* (`:406-409`); reducing the trigger delay 1500 ms → 500 ms
   *"increased [previews] by 12%, and the acceptance rate of ML-suggested edits by authors
   improved by 18%"* (`:439-442`). **Design consequence for PACT:** the proposal must appear
   *inside the artefact the person already looks at* — a diff in the tree, in their normal
   git/editor/UI flow (D18) — not in a separate console.
5. **Explicit ratings were worthless; the accept action was the signal.** *"we found the
   actual numbers of thumbs up/thumbs down relatively uninformative"*, *"applied edits
   constitute strong, indirect positive feedback"*, and negative feedback was *"a mix of
   'comment is not useful' and 'suggested edit is not useful' clicks, which made the data
   very noisy, since the design of our feedback mechanism left room for ambiguous
   responses"* (`:478-490`). **Design consequence:** do not ship a rating widget; ship a
   **typed** outcome record with a **closed** reason vocabulary. Ambiguity in the reason
   field is what destroyed Google's negative signal.

### 2.2 GitHub Copilot × Accenture (GitHub Research, 2024)

*"developers accepted around 30% of GitHub Copilot's suggestions"*; *"developers retained
88% of GitHub Copilot-generated characters in their editor"*; 90% committed Copilot-suggested
code. <https://github.blog/news-insights/research/research-quantifying-github-copilots-impact-in-the-enterprise-with-accenture/>
(fetched 2026-07-26). Lower stakes and far higher frequency than PACT's case; useful as a
**floor** for per-item accept rate in a high-volume regime.

### 2.3 Getafix (Meta), and the honest limit on it

The arXiv abstract (<https://arxiv.org/abs/1902.06111>) carries only the offline figure:
*"predicts exactly the human-written fix as the top-most suggestion between 12% and 91% of
the time, depending on the bug category"*, and *"the top-5 suggestions contain fixes for
526 of the 1,268 bugs"*. The ~60% deployment acceptance figure circulates from the
engineering blog, **not** from the paper abstract I fetched. **Marked as unverified at
source**; it is corroborating, not load-bearing.

### 2.4 The fatigue bound — what happens when the queue is large

Poly et al., *Appropriateness of Overridden Alerts in Computerized Physician Order Entry:
Systematic Review* (JMIR Med Inform 2020, PMC7400042; fetched 2026-07-26): **23 studies**;
*"The range of average override alerts was 46.2%-96.2%"*; *"An average of 29.4%-100% of the
overrides alerts were classified as appropriate"*, with inter-rater kappa 0.79–0.97. By
alert type, drug–drug interaction appropriateness spans **0%–95%**.

This is the negative half of the picture and it is the reason the design must **cap queue
volume**, not merely exist. A high-volume, low-precision proposal stream aimed at a
domain expert converges on ~90% override — i.e. exactly the "ceremony" outcome H37 fears,
reached not because human review fails but because *volume* defeats it.

### 2.5 A record structure for the outcome, and two failure modes to design against

Singh et al., *Learning from Disagreement: Clinician Overrides as Implicit Preference
Signals for Clinical AI in Value-Based Care*, arXiv 2604.28010 (extract
`research/extracts/clinician-overrides.txt`). **This is a framework/position paper, not a
measurement** — its only measured number is Poly's 46–96% (`:37`) and its three-clinician
vignette is illustrative, not observed. I take its *structure*, not its numbers.

- **Three-valued interaction, not binary.** `δt ∈ {accept, modify(a'), reject}` (`:257`),
  recorded as `It = (st, rt, δt, at, k, c, ot+Δ)` (`:259-262`). `modify` is argued to be the
  richest signal: *"(1) a preference pair a′ ≻ rt; (2) a proximity signal … indicating the
  recommendation was approximately correct; and (3) a gradient direction"* (`:366-372`).
- **Automation bias is detectable and must be detected.** The vignette clinician *"accepts
  most recommendations (95% acceptance rate) … This looks like alignment but is the absence
  of clinical judgment"* (`:76-83`); mitigation is *"explicit detection of clinician-level
  acceptance entropy"* (`:519-521`).
- **Suppression / no-self-correction.** *"a subtle and consequential failure mode arises
  when the system stops surfacing a recommendation because the reward model has
  down-weighted it: subsequent overrides cannot occur because the recommendation is no
  longer presented, and the model has no path to discover it was wrong … High-precision/
  low-recall scenarios of this type are particularly dangerous because the reward model is
  internally consistent, override rates are low, and the capability model shows convergence
  — all three conventional health-metrics indicate success while the system is failing"*
  (`:521-534`). PACT has the identical shape: §4.4a's `stop-after-no-accept: 12` sequential
  stop plus ExpeL's `REMOVE → −1` pruning can permanently retire a *class* of proposal after
  a run of human rejections, and nothing re-surfaces it.
- **The architectural warning, quoted because it is the applied conclusion of this note:**
  *"Clinical AI systems generating recommendations to clinicians should be instrumented for
  structured override capture from first deployment … systems tracking only aggregate
  acceptance rates, or recording overrides as unstructured free text, are discarding their
  most valuable training signal. This is a design decision that must be made at the
  architectural level before the first patient: retrofitting structured capture into a
  system built with a binary interaction model is substantially harder than designing it in
  from the start."* (`:849-858`).

### 2.6 The precision floor for a review-gated stream

Sadowski et al., *Lessons from Building Static Analysis Tools at Google*, CACM 61(4), 2018
(<https://cacm.acm.org/research/lessons-from-building-static-analysis-tools-at-google/>;
retrieved via search 2026-07-26 — **the article itself timed out on fetch, so this is a
search-surfaced quotation, marked lower-confidence**): code-review-time checks should have
**less than 10% effective false positives**, and *developers, not tool authors, determine a
tool's perceived false-positive rate*.

Note the apparent tension with Google's own 40%-precision code-review assistant (§2.1):
it is not a contradiction, it is the mechanism. The 10% rule applies to findings that
reach the developer **unfiltered**. Insert a human pre-approval stage and the tolerable
model precision drops to 40%, because the *effective* false-positive rate seen downstream
is what matters. **Two-stage review buys ~4× in tolerable model precision.**

---

## 3. The arithmetic that closes H37b (and the part it does not close)

H37's falsifier is *"20 weeks … producing no proposal a human accepts"*. §11.10 states the
queue carries 1–4 proposals per weekly cycle, so N ∈ [20, 80] over the D9 window. For
independent per-proposal accept probability `p`, `P(zero accepts) = (1−p)^N`:

| `p` | source | N=20 | N=50 | N=80 |
|---|---|---|---|---|
| 0.636 | Google reviewer gate | 1.7e-09 | 1.1e-22 | 7.7e-36 |
| 0.30 | Copilot | 8.0e-04 | 1.8e-08 | 4.1e-13 |
| 0.10 | — | 0.122 | 0.005 | 2.2e-04 |
| 0.049 | Google V1 end-to-end (wrong comparator, included as a pessimistic bound) | 0.366 | 0.081 | 0.018 |

**The falsifier's implied threshold.** `P(zero) = 0.5` requires `p ≤ 3.41%` at N=20,
`1.38%` at N=50, **`0.86%` at N=80**. So H37 is falsified only if a support lead accepts
fewer than roughly **one proposal in 30 to one in 120** — 9× to 74× below the weakest
measured analogue in §2, and 19× to 74× below the strongest.

**What this does and does not establish.**
- It **does** establish that, *conditional on proposals reaching the queue*, H37's stated
  falsification event is improbable to the point of being the wrong thing to watch for.
- It **does not** establish that the accepted proposals improve the agent. Propose-only
  certifies nothing statistically — that is §8.7's own argument — so "a person wanted it"
  is the whole claim, and it is the claim the analogues support. Any stronger claim needs
  the expert-tier apparatus.
- It **does not** cover N = 0. If the cycle emits nothing, every row above is vacuous.
  That is H37a, and it is now the live risk.

---

## 4. Yield at n ≈ 10 — the real residual, restated

Every analogue in §2 measures **accept rate given a proposal exists**. None measures
whether a proposal exists. For PACT the generative question is:

> With ~10 authored eval cases and a support lead's weekly traffic, does a reflective
> proposer emit ≥ 1 well-formed, in-scope candidate per cycle?

What the corpus does say, none of it decisive:

- **The proposal unit is small.** GEPA's `reflection_minibatch_size` defaults to **3**
  (`optim/gepa/src/gepa/api.py:157, 355`); ExpeL critiques successes in chunks of **8**
  (`configs/agent/expel.yaml:8`). n ≈ 10 is *above* both reflection units, so nothing
  suggests n ≈ 10 is too small to reflect over. **Inference, not measurement.**
- **The failing-case supply, not the case count, is the binding input.** A workspace whose
  10 gating cases all pass has nothing to reflect on. §6.6's trace→case promotion is
  therefore not an eval convenience but **the propose-only queue's actual input**, and
  §6.6 already says so for a different reason: *"production traces with human good/bad marks
  are the one labelled resource a support lead genuinely produces at volume"*
  (`20-ARCHITECTURE-DRAFT.md:4358-4362`).
- **Budget is not the limiter.** §4.4a runs at the full `cycle-limits.evals` budget with a
  sequential stop, against §13.9's measured GEPA requirement of 1,839–7,051 rollouts/task.

**Residual, stated honestly:** H37a is unmeasured and is not resolvable from the corpus or
from the web. It is resolvable *cheaply* by the D9 run itself — provided the run records
zero-proposal cycles, which today it does not (§5).

---

## 5. Two defects in the shipped design, found by this pass

### 5.1 §11.10's "Expected 1-4 accepted proposals" mis-cites a post-gate number, and leaves the queue unbounded

`20-ARCHITECTURE-DRAFT.md:8123` prints, on the `propose-only` path:

> `Expected 1-4 accepted proposals (median 2.5, from the reference runs).`

The reference is SkillOpt Table 6. But in SkillOpt an edit *"is accepted only when it
strictly improves a held-out"* score (`research/extracts/skillopt.txt:25`, `:713`), and the paper is
explicit that the pre-gate stream is much larger: *"the optimizer model proposes many more
edits per epoch, but only a handful pass the held-out check and survive into the deployed
skill. The bulk of the optimizer's text-space search is thus rejected"* (`:846-849`).

**Y8 deleted exactly that gate at core tier.** §8.7's table: for `propose-only`, *"Splits
required: none"*, *"OBL-2 sign test: not run"*, *"Held-out / validation ledger: not
required"* (`:6300-6303`). So the 1–4 figure describes a configuration `propose-only` does
not run, and nothing in §8.7 or §11.10 bounds the number of proposals that reach the human.
`cycle-limits.per-cycle: 4` is defined as a cap on **write operators** — *"at most 4 per
cycle and at most 1 per sub-artifact"*, adopted from ExpeL (`:6014`) — and in `propose-only`
no write happens until a human approves, so it does not bind the queue.

Consequence: the D14 persona is pointed at an unbounded weekly stream of uncertified
proposals. §2.4's 46–96% override range is what that produces.

**Fix (applied):** `propose-only` keeps a **pre-filter that ranks and truncates but
certifies nothing** — strict improvement on the author's own cases, which needs no split
because it makes no generalisation claim — and `per-cycle` becomes a hard cap on *queue
depth*, not only on write operators. Google's V2 result is the licence for a deliberately
weak pre-filter: with a human gate downstream they ran the model at 40% precision and got
more value, not less (§2.1.2).

### 5.2 H37 cannot be falsified by the D9 run, because rejections are not recorded

§8.10's core-tier approval mechanism is *"a human-authored commit IS the approval record"*,
optionally `pact approve` writing `approval: {by, at, over}` (`:6778-6784`). There is:

- no record of a **rejected** proposal (so AC-5.5 — *"a rejected learning candidate is
  retained as negative evidence and demonstrably influences the next cycle"* — has **no
  mechanism on the D14 path**, only on the expert path);
- no record of a **modified-then-accepted** proposal, which §2.5 argues is the highest-
  information outcome;
- no record of a **zero-proposal cycle**, which is H37a's entire falsifier;
- no reason vocabulary, so any signal that did exist would be Google's discarded
  free-text/thumbs case (§2.1.5).

H37 is therefore currently **unfalsifiable by construction**, which under T7 is worse than
a bet with a hard falsifier. §2.5's architectural warning applies verbatim: structured
capture has to be designed in, not retrofitted.

**Fix (applied):** an append-only `proposals.ledger` with a three-valued typed outcome and
a closed reason vocabulary, written on every cycle including empty ones.

---

## 6. Design conclusions applied to `20-ARCHITECTURE-DRAFT.md`

| # | Conclusion | Evidence |
|---|---|---|
| C1 | **A human review gate over machine proposals is measured to be worth it, and the mechanism is that it lets the proposer run at LOWER precision.** Propose-only should be tuned for *recall*, with the human as the precision filter | Google Table 1 + `:286-289`, `:439-445`: precision 50%→40%, end-to-end 4.9%→7.5% |
| C2 | **Cap queue depth, hard.** The value of the gate is destroyed by volume, not by low precision | Poly 46.2–96.2% override across 23 studies; Roo-Code's ten `alwaysAllow*` keys + auto-approve timeout as the market's revealed answer to high-frequency review |
| C3 | **Three-valued outcome (`accepted` / `edited-then-accepted` / `rejected`) with a CLOSED reason vocabulary; no rating widget** | Google `:478-490` (thumbs uninformative, ambiguous reasons destroyed the negative signal); arXiv 2604.28010 `:257-262, 366-372` |
| C4 | **Record zero-proposal cycles explicitly** | H37a is the live residual and this is the only instrument that reaches it |
| C5 | **Warn on rubber-stamping** (accept-everything), because a 100% accept rate certifies nothing | arXiv 2604.28010 `:512-521` (acceptance entropy) |
| C6 | **Never permanently suppress a rejected proposal class; re-surface on a schedule** | arXiv 2604.28010 `:521-534` (no-self-correction), against §4.4a's `stop-after-no-accept: 12` and ExpeL's `REMOVE −1` pruning |
| C7 | **The proposal must be a diff in the tree, seen in the flow the person is already in** | Google `:406-409`, `:439-442` — placement and latency moved acceptance more than model quality |
| C8 | **Split H37 into H37a (yield) and H37b (accept rate); H37b is closed, H37a is the bet** | §3 arithmetic + §4 |

---

## 7. Residual uncertainty (what this pass does NOT close)

1. **Yield at a support lead's cadence (H37a) is unmeasured** and cannot be measured from
   the corpus. The instrument now exists (C4); the number does not.
2. **Population transfer is assumed.** Every accept-rate figure in §2 comes from software
   engineers reviewing code, or clinicians reviewing orders. **No measurement exists for a
   non-technical domain expert reviewing an agent-specification diff** — D13's exact
   persona. The direction of the bias is unknown: a support lead has more domain authority
   over a refund rule than a reviewer has over a suggested refactor, but less fluency with
   diffs. **Marked as inference.**
3. **Review time per proposal is unpriced.** Google's only time figure is the ~60-minute
   median for *code shepherding* per changelist (`research/extracts/google-crc-ml.txt:463-466`),
   which is not a per-proposal cost. PACT's ceremony budget (≤ 4 diffs/week) is a
   *judgement*, not a measurement.
4. **Accepted ≠ better.** Nothing here establishes that human-accepted proposals improve
   the agent — §2.5's automation-bias and amplification-bias cases are precisely the
   mechanisms by which they might not. `propose-only` makes no such claim and must not be
   marketed as making one. **The outer-loop check remains the eval suite run before and
   after, reported without a pass/fail claim.**
5. **Getafix's ~60% is unverified at source** (§2.3), and the CACM 10%-false-positive rule
   is search-surfaced rather than fetched (§2.6). Neither is load-bearing; both are
   corroborating.
6. **The independence assumption in §3 is optimistic.** Proposals within a cycle come from
   one reflector on one trace window and are correlated; a reviewer who rejects one is more
   likely to reject its siblings. The effective N is therefore below the nominal N. Even at
   an effective N of 20 the falsifier threshold is 3.4%, still an order of magnitude below
   every measured analogue, so the conclusion survives — but the exact probabilities in §3
   should be read as upper bounds on confidence.
