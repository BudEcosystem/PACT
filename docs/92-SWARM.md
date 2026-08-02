# Does swarm-like behaviour help?

**Date:** 2026-08-01. **Status:** analysis. Not binding.
**Question asked:** *does swarm-like behaviour, or anything similar — agents able to
communicate with each other, treating other agents around them as part of the
environment — help in any way?*

**Method.** Eight facts measured against this repository by running commands; two
literature streams covering (a) whether peer communication survives compute
matching and (b) the state of stigmergy, blackboards, markets and claim-lease
queues. `research/papers/` went 100 → 131.

---

## 0. The answer in one paragraph

**"Swarm" bundles six separable mechanisms whose evidence points in opposite
directions, so the question is unanswerable until they are priced separately.**
Peers *talking* — debate, chat, mutual critique — does not survive compute
matching: the largest controlled study (260 configurations, Google/DeepMind/MIT)
puts multi-agent at **−0.3% aggregate**, at **263–285% message overhead** and
**2.8–5× worse success-per-token**, with a capability ceiling above which it is
reliably negative. Peers *sharing a validated store* is a different mechanism and
it does pay — the cleanest ablation in the field holds worker rollouts identical
and varies only the representation, buying **+5.2 points from the store alone**,
and a second system gets **+10.5pp on SWE-bench at half the cost**. But every
system that wins keeps a **dispatcher**. The one system that removed the
controller entirely and coordinated purely through traces in a shared medium got
task-dependent results and a **−7.7% quality cost**. So the honest finding is
that the thing which helps is **division of labour over a governed shared store**
— which is the *opposite* of swarm's defining claim of decentralised coordination
without a controller. And PACT's position is unusual: **it already does the
dangerous half of this and none of the safe half.**

---

## 1. Six mechanisms, six different answers

"Swarm" is used for all of these. They need different runtime primitives and have
different signs.

| # | Mechanism | Coordination signal | Evidence | Sign |
|---|---|---|---|---|
| M1 | **Many agents, no communication** (best-of-N, race) | none — aggregate at the end | matched-call majority voting **+0.9%, plateaus ~8 agents**; self-consistency collapsing on frontier models (+0.4% HotpotQA over 20 samples) | **saturating** |
| M2 | **Peers talking** (debate, chat, mutual critique) | addressed or broadcast messages | **−0.3%** aggregate over 260 configs; auto-MAS underperform CoT-SC at up to **10× cost** | **negative at matched compute** |
| M3 | **Agents as environment** (blackboard, shared store) | read/modify a common state | Argus ablation **+5.2**; DeLM **+10.5pp at half cost**; PatchBoard 84.6% at 45.5k tok/success vs 368.3k | **positive, when governed** |
| M4 | **Trace-in-medium** (stigmergy proper — no dispatcher) | the work product *is* the signal | one instantiation; 100% character convergence, **5–10% semantic conflicts**, quality **−7.7%** (d=−0.71) | **unproven / mixed** |
| M5 | **Orchestrator + workers with context isolation** | dispatch down, summaries up | orchestrator thinking **+18.2 GAIA**; sub-agent thinking null-to-harmful, **+77% latency**; 8B orchestrator ≈ 32B single agent | **positive — and it is a context firewall, not communication** |
| M6 | **Market / bidding** | price or confidence + award + settlement | **zero implementations** in any framework; the nearest academic artifact is calibrated routing wearing auction vocabulary | **empty** |

The user's framing — *"treating other agents around it also as an env"* — is M3/M4,
and it is the right place to look. It is also the place where the distinction
between "governed store" and "emergent trace" decides everything.

---

## 2. Peers talking: the matched-compute verdict

Five independent matched-budget studies plus an audit of six automated
multi-agent systems agree. The load-bearing one is *Towards a Science of Scaling
Agent Systems* (260 configs, 6 agentic benchmarks, matched to μ=4,800 reasoning
tokens/trial **and** matched max iterations):

| Architecture | Overhead | Turns | Success | **Success / 1K tokens** | Trace error amplification |
|---|---|---|---|---|---|
| Single agent | 0% | 7.2 | 0.466 | **67.7** | 1.0× |
| Independent (**no** communication) | 58% | 11.4 | 0.370 | 42.4 | **17.2×** |
| Decentralized (peer-to-peer) | **263%** | 26.1 | 0.477 | 23.9 | 7.8× |
| Centralized (orchestrator) | **285%** | 27.7 | 0.463 | 21.5 | **4.4×** |
| Hybrid | 515% | 44.3 | 0.452 | 13.6 | 5.1× |

Three things fall out.

**The widely-circulated "58% for peer-to-peer" figure is a misquote.** 58% is the
overhead of *independent agents with no peer messages at all*. True peer-to-peer
is **263%**. I had previously recorded this figure as untraceable; it is now
traced and corrected.

**Aggregate multi-agent effect: −0.3%** (95% CI [−58.7, +77.2]) — an interval that
wide is itself the finding. And there is a **capability ceiling**: once the
single-agent baseline clears ~45%, multi-agent returns go reliably negative
(β=−0.236, p=0.004, surviving Holm–Bonferroni and cluster-robust SEs).

**Verification containment is the one thing communication reliably buys.**
Error amplification 17.2× with no communication → 4.4× with a centralized
verifier. That is insurance, priced in accuracy.

Corroborating, and worse for the naive case:

- Auto-designed multi-agent systems **"consistently underperform CoT-SC despite
  being up to 10× more expensive."** In the same audit, DyLAN's agents reach
  **immediate unanimous consensus in ~70% (GPT-4o) to >90% (GPT-5)** of cases —
  *the debate never happens* — and 50% of one system's "discovered" workflows
  reduce to sampling one prompt three times and aggregating.
- Teams underperform **their own best member by 6.3–41.1%**, via integrative
  compromise, **even when explicitly told who the expert is**.
- Anthropic's +90.2% multi-agent research result is **token scaling past one
  context window**, not communication: by their own account "token usage by
  itself explains 80% of the variance," at ~15× chat tokens.
- Fully-connected meshes are mostly waste: pruning the message graph cuts
  **28.1–72.8% of tokens with no performance loss**.
- Debugging it is unsolved: the best automated method identifies the
  failure-responsible *agent* 53.5% of the time and the decisive *step*
  **14.2%** — some methods below random.
- Communication creates a failure class no single agent has: conformity cascades
  where **57–77% of induced flips are correct→wrong**, and prompt injection that
  self-replicates agent-to-agent **"even without global message sharing"**, with
  more capable models executing the attack more effectively.

### 2.1 Why — and the four conditions under which it stops being true

The information-theoretic argument is exact. Let `Y` be the answer, `C` the
context available to a single agent, and `M = g(C)` the messages exchanged. Then
`Y ↔ C ↔ M` is a Markov chain, so by the Data Processing Inequality
`I(Y;C) ≥ I(Y;M)` and `Pe(C) ≤ Pe(M)`. **A peer's message cannot carry
information about the answer that was not already in the shared context.** Under a
fixed budget it is strictly worse, because splitting `B` across `k` agents gives
each `B/k` and adds a lossy compression at every hop.

That argument has exactly four preconditions, and each failure is a real regime:

| # | Precondition | Fails when | Measured payoff |
|---|---|---|---|
| 1 | peers are functions of the **same** context | a peer holds **private input** — different tool, corpus, credential, context shard | judge accuracy 60→88% when debaters hold a passage the judge cannot see; Chain-of-Agents +10% when input exceeds any window |
| 2 | the single-agent comparator **has** that context | the practical single agent is **context-degraded** (truncation, poor long-context use) | this is the honest basis of Anthropic's +90.2% |
| 3 | DPI bounds the **optimal** estimator | LLMs are not Bayes-optimal — the *same byte-identical* error is corrected **23–93pp more often** when relabelled into an external role | real, but capturable single-agent by re-wrapping your own draft |
| 4 | gains come from communication | they come from **aggregation**, which needs no peer visibility | best-of-N, agentic aggregation (+5.3% avg, +10.3% deep research) |

**The strongest positive result in the whole corpus sits squarely in condition 1
and 4 together**: an expert-decomposed system with a *deterministic Python
orchestrator* took GPT-5 from **57.0% → 96.5%** at roughly CoT-SC cost. Parallel
per-entity extract-then-calculate chains, context separation, code-level
aggregation. Automated multi-agent systems on the *same task* failed to beat
CoT-SC. The work was done by decomposition and deterministic control — **not by
agents talking to each other.**

---

## 3. Agents as environment: this is where the value is

The blackboard revival is real and measured, and it is a different mechanism from
peer chat.

| System | Mechanism | Result | Compute matched? |
|---|---|---|---|
| **Argus** | central evidence graph, gap-directed dispatch | +6.0/+8.0/+11.6 over majority-vote K=8; 86.2% BrowseComp @K=64; Navigator context **≤21.5K** (~1200:1 compression) | worker-level yes |
| **DeLM** | verified shared context (admission-gated gists) + dependency-gated claim queue | **+10.5pp** SWE-bench Verified, **~half the cost** (~$0.12/task) | **yes — and cheaper** |
| **PatchBoard** | blackboard + deterministic validation kernel, role write-contracts | **84.6%** at **45.5k tokens/success** vs 368.3k | yes and cheaper |
| **STORM** | shared workspace, write-time read-set validation | **+18.7** Commit0-Lite over git-worktree-per-agent | comparable cost |
| **blackboard-DS** (Google) | volunteer blackboard, helpers self-select | 13–57% relative | **no** — 2.3× RAG cost |

**The cleanest attribution in the field is Argus's representation ablation**: hold
the worker rollouts *identical*, vary only how the shared store represents
evidence. Text-only **69.3** → bare graph **72.0** → full typed DAG **74.5**.
**+5.2 from the structure of the store alone.** That is as close to isolating
"agents as environment" as anything published.

And the mechanism is explicit about why undirected fan-out fails: *"deep research
answers are composed of complementary pieces of evidence, which parallel rollouts
often duplicate rather than complete."* **Directed** fan-out completes; undirected
duplicates. That is the difference between M3 and M1.

### 3.1 But every winner keeps a controller

Argus has a Navigator. DeLM has a dependency queue and an admission verifier.
PatchBoard has a validation kernel. blackboard-DS has a main agent. Anthropic's
research system has a lead.

**The one system that removed the dispatcher entirely** — CodeCRDT, coordinating
purely through a shared CRDT document with no messages at all, which is stigmergy
in the strict sense — reports an honest split verdict: the *substrate* works
perfectly (100% character-level convergence, provable at-most-one-winner claims,
zero merge conflicts), and the *cognition* does not. **5–10% semantic conflicts
remain** — duplicate implementations, incompatible assumptions — that no
consistency model prevents. Quality **−7.7% (d=−0.71)**. Wall-clock ranged from
+21.1% to −39.4% depending on task coupling.

**Convergence is not coherence.** A store that provably merges every write buys
you nothing at the level of meaning.

Two further results make the point structurally rather than empirically:

- On a contested-resource testbed, naive simultaneous claiming deadlocks
  **90.0%** of the time. A **structural** intervention (resource ordering) takes
  it to **0.0%**. One round of inter-agent communication takes it to 86.7% —
  **statistically nothing.** Protocol beats talk.
- The field's own best practice is a *governed* blackboard, not an open one.
  Google's system deliberately breaks the architecture for safety: helper
  responses go to a segregated board readable only by the main agent,
  **"to prevent cross-influence of sub-agents."**

### 3.2 Emergent specialisation does not occur

Checked specifically, because it is the swarm claim: with no inter-agent
communication, controlled studies show temporal synergy but **no cross-agent
alignment**; identity-linked differentiation appears **only when personas are
assigned**, and goal-directed complementarity only with personas *plus* an
instruction to think about others. Every production "specialisation" is
role-prompted by construction.

**There is no measured case of task-productive division of labour emerging
without being seeded in prompts, roles, or model choice. Design it in.**

---

## 4. Markets: empty, and now with a measured reason

Confirmed: **zero implementations** in any shipped framework. The nearest
academic artifact computes `argmax_j(confidence^γ − β·cost)` centrally — routing
in auction vocabulary, with no strategic bidding, no settlement, no transfers.

The reason is not missing plumbing. A 2026 measurement study finds LLMs are
**miscalibrated on both their own success probability and their own token cost**;
allocations built from self-reports diverge from full-information allocation, and
context interventions close the gap only modestly. **Self-assessment is the
binding constraint on market coordination, not mechanism design.**

Payment rails now exist (x402, AP2, ACP) and settle *payments*, not *task
auctions*. Nothing joins the two.

**Verdict: do not build this.** It would inherit a calibration problem no
protocol fixes.

---

## 5. Where PACT actually stands — eight measurements

All run against this repository.

**1. PACT ships a pattern called `swarm`, and it has no communication in it.**
Three solvers, `all-at-once`, `waits-for: the-first-good-answer`. Diversity comes
from three different `instructions:` blocks; solver-a is *told in prose* "another
solver is already trying the other angles." That is M1 — race plus prompt
diversity — which is the saturating mechanism. It is honestly built and honestly
named a race.

**2. PACT already has a peer channel, and it has not been named as one.**
Under `starts: one-after-another`:

```python
prior = "\n".join(f"{a.member} said: {a.text}" for a in grant.so_far if a.ok)
```

Each member receives every earlier member's answer as **attributed prose in its
prompt**. Sequential, forward-only, no contention. PACT's own comment calls this
"the whole point of `one-after-another`" and criticises Eve for paying the
latency and handing over nothing.

**This places PACT at the single safest point on the spectrum** — the point where
every concurrency anomaly is structurally impossible because there is no
concurrency. That is a defensible design position and nothing in the documents
claims it.

**3. A full blackboard is expressible today, and PACT says nothing about it.**
Built one: shared store, `claim`, `post-finding`, three agents, members genuinely
concurrent (`asyncio.gather`):

```
OK — loaded cleanly (49 settings).      ← 0 diagnostics
```

**4. The machinery to govern it already exists and is keyed to the wrong word.**
Mark the *identical* `claim` action `spends-money: yes`:

```
warning: `spends-money: yes` on `claim` is not applied: `lead`, `solver-a` and
`solver-b` can call it and no rule in their approval policies names `board/claim`
error: 'spends-money' says 'yes', and 'same-request-key' is not set — so nothing
       says which argument makes two calls "the same call".
```

Exactly-once enforcement, cross-agent reachability analysis and approval gating
**all already work**. A `claim` on a shared board is structurally identical to a
payment: it must happen at most once, and two agents doing it is the bug. None of
it fires, because the trigger word is *money*.

**5. The safety mechanism designed for exactly this case is unbuilt.**
`trust:`, `sanitises:`, `written-by`, `merged-by` → **0 field declarations in the
schema**; 4 mentions in the docs. X26's motivating example is *"a `transform` node
laundered customer text into a control-flow predicate"* — one component writing
what another reads. **The blackboard and the trust lattice are the same feature.**
PACT designed the guard and built neither the channel nor the guard — while
already shipping the ungoverned prose channel of finding 2.

**6. PACT's own resolver is required to recommend fewer agents.**
`RES-5b collapse-team` must evaluate the collapsed single-agent variant and print
both arms. AD-R14 accepts the flagship is "precisely the regime the corpus
measures multi-agent as buying least in — up to 3× the cost at equal accuracy."
**Adding inter-agent machinery pushes against the one mechanism the resolver is
obliged to try.**

**7. All eight pattern examples put members in the worst measured regime.**
Every one has members with **identical capability** — no `uses:`, no `model:`,
separated only by `instructions:` prose:

```
debate       2 members   IDENTICAL capability
first-answer 2 members   IDENTICAL capability
quorum       3 members   IDENTICAL capability
swarm        3 members   IDENTICAL capability
…8 of 8
```

Members that are conditionally independent given the task are exactly the DPI
regime. **And this is statically checkable — I computed it in twenty lines.**

**8. The flagship is the opposite, and PACT's own assessment misses it.**

| Agent | `uses:` | `answers-with:` |
|---|---|---|
| `fraud-checker` | `[zendesk]` — ticket history | `concern: one of none, low, high` |
| `policy-checker` | `[refund-policy]` — written policy | `allowed: yes or no` |
| `refund-desk` | `[zendesk, payments, refund-policy]` | the decision |

**Disjoint** information. Neither member can see the other's source. That is DPI
failure condition 1 — the strongest one — and it is the cell where the 260-config
study measures multi-agent winning big (+74.5 → +80.8%, centralized).

AD-R14 calls the flagship "homogeneous by construction (one local model under
D17)." **That is true of the model and false of the information**, and the
distinction is the whole finding. The measured 3× penalty is for
homogeneous-in-both.

*Caveat, stated:* collapsing is still possible — the supervisor already holds the
union of all three tools — so `RES-5b` reporting both arms remains right. And
what the split buys is context isolation plus narrow typed outputs, which is M5,
not peer communication.

---

## 6. What follows for PACT

**Do not add swarm.** M1 saturates, M2 is negative at matched compute, M4 is
unproven with a measured quality cost, M6 is empty and calibration-blocked. PACT
already ships M1 honestly and already has the safest form of M3.

**Do govern what is already reachable.** The blackboard is buildable today with
zero diagnostics. This is not a missing capability — it is an **ungoverned** one,
and it is the same shape as the `allow-egress`/`endpoint` hole: the format
governs the path it knows about and is silent on the path people take.

### 6.1 The one change that does the most

**Generalise `same-request-key` from "one run" to a declared scope.**

```yaml
actions:
  claim:
    description: Take a question so nobody else does.
    same-request-key: question-id
    at-most-once-across: the-team        # ← the whole change
```

This is not a new subsystem. `same-request-key` is genuine content addressing
that already survives a park (`Ledger.resumed` rebuilds from
`Suspension.spent_keys`); its only limitation is the word "run" in its refusal
sentence. Widening the scope:

- makes a contended `claim` checkable with **machinery that already works**
- closes the retail persona's double-booking, found independently in the
  cold-authoring trial
- is what Argus's and DeLM's claim step needs
- and was already proposed on two independent grounds in `90-REVIEW.md`

**Four independent lines converge on the same primitive.** That is the strongest
signal in this document.

### 6.2 The second change: make the DPI condition checkable

`pact check` can compute, today, whether a team's members differ in anything the
runtime can see — `uses:`, `model:`, `answers-with:`. If they do not, the team is
in the regime the evidence measures as worst, and the author should be told. That
is `RES-5b`'s collapse-team recommendation, available **at check time** instead of
at a resolve step that does not exist.

A fair caveat: prompt diversity is real diversity, and the `swarm` pattern's three
angles are genuine. It is simply the weakest *measurable* form, and the checker
cannot evaluate prose. So this is a `note:`, not an error.

### 6.3 If a shared store is ever added, the shape is known

A **governed shared log with claimable entries**: entries carrying
`{payload (schema-validated), status, owner, lease-expiry, written-by}`, with
exactly two operations — validated append, and compare-and-swap on `status` with
an optional lease TTL that returns an expired entry to available.

Two warnings that come with it:

- **The accuracy lives in the admission gate, not the queue.** Argus's +5.2 is
  representation; DeLM credits admission verification; PatchBoard credits its
  validation kernel. A claimable queue *without* a validated store reproduces
  CAMEL — mechanically sound, no measured task benefit.
- **Nobody has built the lease.** Claim has three implementations to imitate
  (CAMEL's mutex, CodeCRDT's write-verify, Claude Code's file lock — the last
  with a documented ~50ms double-claim window). **Time-based claim expiry with
  automatic reclaim does not exist anywhere in LLM-agent work.** PACT would be
  first, which is an opportunity and a warning: steal the semantics from queue
  infrastructure (visibility timeout, receive count, dead-letter after N) rather
  than inventing them.

And what it would explicitly **not** warrant: semantic conflict prevention
(CodeCRDT's 5–10%), multi-entry transactional invariants, markets, or emergence.

---

## 7. What would change this conclusion

1. **A matched-compute win for peer chat on a homogeneous team.** Everything here
   rests on the matched-budget studies; if a controlled result shows communication
   beating aggregation at equal tokens with same-model same-tool peers, §2 is
   wrong.
2. **A dispatcherless system that beats a dispatched one.** M4's single data point
   is mixed. A second, cleaner one would move stigmergy from analogy to mechanism.
3. **Calibration solved.** If self-assessment stops being the bottleneck, §4's
   verdict on markets flips from "empty for a reason" to "empty and worth filling".
4. **The flagship measured, not reasoned about.** §5's finding 8 says the flagship
   sits in the good cell. That is an inference from its `uses:` sets, not a
   measurement — and PACT cannot yet run it end-to-end to check.

---

## 8. Provenance and caveats

- The eight PACT findings are commands run against this tree and are reproducible.
- Two literature streams; 31 papers added. One stream had `WebFetch` blocked in
  its environment, so a subset of its web claims carry search-snippet provenance
  and are marked as such in the source report.
- **One error caught and corrected:** the first stream referenced a PACT `debate`
  pattern with `budget.max_iterations` and quorum joins. `budget`,
  `max-iterations` and `quorum` have **0 field declarations** in
  `spec/schema.yaml` — it was quoting the architecture draft, which describes an
  unbuilt Graph. The shipped `debate` is bounded by `at-most: 2` on a stage,
  which is a real host-controlled bound. This is the two-PACTs confusion of
  `90-REVIEW.md` §2 reproducing itself inside the research.
- The shipped `debate` pattern is, on the evidence, **well-designed**: star
  topology through a judge, sides never addressing each other, bounded rounds,
  adversarial split. That is the centralized-and-verified topology the evidence
  favours, at the agent count it favours.
