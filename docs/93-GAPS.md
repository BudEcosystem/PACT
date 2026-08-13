# PACT — What is missing, in three registers

**Date:** 2026-08-01. **Status:** consolidated gap register. Not binding.
**Sources:** `90-REVIEW.md` (independent review), `91-REVIEW-CRITIQUE.md`
(six-lens adversarial pass, 50 upheld / 32 overturned), `92-SWARM.md`
(coordination analysis), the ten-persona cold-authoring trial, four research
streams, and 131 papers in `research/papers/`. Every row was produced by a
command against this tree or a cited measurement.

---

## 0. The framing, before the list

**"Support every type of agent" is not the goal, and pursuing it is a named
failure mode.** The thesis calls it R1 — *lowest-common-denominator collapse*, a
spec so broad it is too weak to be useful. Three things are correctly refused and
should stay refused, with their prices written down:

| Refused | Why it is right | The undisclosed price |
|---|---|---|
| **Code mode** (agent writes code to call tools) | literally the agent writing code; needs a language runtime in the sandbox; collides with the air-gap | best-measured tool-scaling mitigation available — 150,000 → 2,000 tokens; flat-catalogue selection 13.6% → 43%+ |
| **Markets / bidding** | self-assessment is the bottleneck, not plumbing — LLMs are miscalibrated on both their own success probability and their own token cost | none. This one is free |
| **The Graph** (8 node kinds, edges, channels) | nothing in the 2026 literature needs it; three constructs cover every measured pattern | none, if the documents stop describing it |

So the real target is: **every shape whose absence blocks a real use case, with
every refusal priced.** That is what the three registers below enumerate.

**Sequencing principle.** Register B (production) gates Register A (expression):
adding capability on top of six live safety defects widens the blast radius. And
Register C (public) has two items that gate *everything*, because they are legal
and structural rather than technical.

---

## A. Expressive gaps — what cannot be written

### A.0 Coverage, honestly

**Agent shapes**

| Shape | Status |
|---|---|
| conversational · task/batch · scheduled · event-driven | ✅ ships |
| supervisor + specialists | ✅ ships, and the flagship is well-designed for it |
| voice / phone | ⚠️ port kind exists; **no turn-taking** — a triage script cannot be written |
| computer-use / browser | ⚠️ capability declarable; **no sandbox kind** (R58 narrowed `resource-kind` to `[mcp-server]`) |
| coding agent | ⚠️ expressible; no code-mode by decision |
| **answers-from-documents (RAG)** | ❌ **cannot be written at all** |
| deep research | ❌ needs fan-out over a work-list |
| long-running / always-on | ⚠️ no durability declaration |
| remote / federated | ⚠️ `pact card` emits A2A; no authored half |

**Patterns**

| Pattern | Status |
|---|---|
| ReAct · plan-then-do · reflexion · pipeline · supervisor · race · quorum · escalation | ✅ ship |
| **debate** | ✅ ships and is **well-designed** — star through a judge, bounded rounds, adversarial split: the topology the evidence favours |
| tree-of-thought | ⚠️ ships; its own file says it is "a tree only in the sense that three branches are written down" |
| self-consistency | ❌ ships as `answer-more-than-once`, which **refuses the name** because it cannot sample independently |
| best-of-N · verifier-guided search · distill re-entry | ❌ no context forking |
| map-reduce / fan-out over N items | ❌ no `map` |
| blackboard / gap-directed fan-out | ❌ buildable as an MCP tool, **governed by nothing** |
| CodeAct | ❌ refused (R42), priced above |
| market / auction | ❌ correctly refused |

**Components**

| Component | Status |
|---|---|
| instructions · tools · skills · ports · watches · questions · policies · interceptors · learning · model catalogue | ✅ |
| memory — run-established **facts** | ✅ `remembers:` is genuinely ahead of the field |
| memory — **stores** (episodic/semantic, retrieval, consolidation) | ❌ |
| **knowledge / retrieval** | ❌ |
| evals — cases | ✅ · **datasets** ❌ · **retrieval-context** ❌ (plumbing exists, disconnected) |
| context policy | ⚠️ destructive only; no reversibility, no control-plane reserve |
| **durability** | ❌ no field — *and the refusal ledger §4 says there is one* |
| **sandbox / isolation** | ❌ |
| trust / provenance between components | ❌ designed (X26, §7.4), **0 field declarations** |

### A.1 The gaps, in evidence-per-cost order

| # | Gap | Cost | Evidence |
|---|---|---|---|
| **A1** | **Nothing constrains what the agent *says*.** Every enforcement surface reaches actions. The moments that see the answer accept only hiding sentences; the only moment that can stop never sees an answer. **In neither the refusal ledger nor the deferred list** — the fourth category §0 says cannot exist | **one sentence form + one predicate row** | 6 of 10 personas blocked: *answer only from the handbook* · *never give medical advice* · *never double-book* · *stop at the first failed step* |
| **A2** | **`retrieval-context:` on an eval case.** `providers.evaluate_metric` **already takes the parameter** and forwards it to `LLMTestCase`; its only caller never passes one | **one field + one argument** | the four canonical RAG metrics are accepted by name and can never return a score |
| **A3** | **Approvals can only compare money.** `when-this` is `{tool, arg, more-than: money}` | **two fields** — `is:` / `is-one-of:` | two personas ended with a gate that is not a gate; the workaround hands *the model* the decision about whether a person is asked |
| **A4** | **`list of <shape>`** in the answer vocabulary | **one entry** beside `one of a, b, c` | a citation list or findings list is untypeable at the exact boundary evals grade against |
| **A5** | **`same-request-key` scope** — widen from "one run" to a declared scope | **one field** | four independent lines converge here: this register, the persona trial's double-booking, and two arguments in `90-REVIEW.md` |
| **A6** | **`tries:` — a stage over independent contexts**, folded by a declared selector | one field + a fold | RTV 67.4→73.6% SWE-bench; select-K re-entry **+8.19pp vs +1.00pp** single-summary, same model same budget; CATTS **+4.7pp at −56% tokens** |
| **A7** | **`knowledge:` — the data plane** | one kind + one agent field | the most common enterprise shape cannot be written; pushing it to MCP makes the eval oracle measure the host, breaking T2 and R17 |
| **A8** | **`durability:` declaration** — `none \| checkpoint \| durable-execution` | one field | the ledger §4 already promises it. Checkpointing ≠ durable execution: *"if your process crashes, no one knows"* |
| **A9** | **Sandbox kind restored** + isolation level | two fields | D16 puts computer-use in v1 and R58 removed the only way to say "run this isolated" |
| **A10** | **Budget as a policy, not a scalar** — per-role, difficulty-conditioned | — | easy problems cross the overthinking threshold at 2K tokens, hard at 8K; orchestrator thinking **+18.2 GAIA**, sub-agent thinking null-to-harmful |
| **A11** | **Turn-taking with a person** | — | `ask-someone` is staff approval; a phone triage script is the whole task for one persona and cannot be written |
| **A12** | **Three answer shapes parse and cannot be read** — `images`, `audio`, `file` have no branch in `Shape.read` | a bug fix | D16's v1 modalities are declarable and unusable |
| **A13** | **Eval dataset pointer** | one field | 2,000 labelled cases become 2,004 committed YAML files generated by a script outside the tree — inverting D2 |
| **A14** | **Reversible compaction + control-plane reserve** | `keep-room-for:` | ACE **+3.6 to +8 GAIA** from re-deciding raw/abstract/drop per step; preflight gives **25–48/48 fail-closed vs 0/48** |

**A1 is the highest-value item in this document**: one form entry, zero new field
names, and it unblocks more real tasks than A6, A7 and A9 combined.

---

## B. Production readiness — what is unsafe or unoperable

### B.1 Live defects

| # | Defect | Consequence |
|---|---|---|
| **B1** | `escalate()` carries `granted`, drops `spent_keys` (`suspension.py:641`) | **a refund issued before the park can be issued again** — ACRFence *Action Replay*, measured 10/10 across 12 frameworks |
| **B2** | four of five park sites never set `Suspension.used` | **parking for approval hands the run a fresh spend budget** |
| **B3** | `answer-with-what-it-has` bypasses the interceptor chain (`harness.py:2102`) | **escapes every redaction rule**; `_finish`'s own docstring states the guarantee it breaks |
| **B4** | a person's answer to `ask-someone` bypasses the chain | same bypass, second door |
| **B5** | `anthropic_transport.py:206` builds `_request` and never uses it | settings **reported honoured** and dropped |
| **B6** | `Learner.baseline` never set by `from_document` | the cumulative-drift gate evaluates `0.0 > limit` forever |
| **B7** | `may: [stop-the-run]` at `turn.message.after` loads clean and **can never fire** | a declarable power nothing produces — the exact defect R24 deleted two powers for |

**B1, B2 and B4 have one cause**: five park sites each assemble a `Suspension` by
hand and disagree about which fields. **One `park()` helper closes three.**

### B.2 The checker says OK when it should not

| # | Written | What happens |
|---|---|---|
| **B8** | a **map** under any `type: text` field | `loop:\n  banana: purple` → `OK — loaded cleanly (9 settings)`, counting the junk as a setting. A **list** in the same position is caught perfectly. One missing validator arm |
| **B9** | `allow-egress: []` + `endpoint: https://…` + an upload action | **clean pass.** All six egress choices are model roles; the path customer data takes is ungoverned |
| **B10** | `judged:` with no `graded-by:` · `use-tools` with no tools · `based-on:` **silently disabling** the reachability check · a colonless metric URI · a non-string `expect:` · any `x-` field | six reproduced classes of inert control passing green |
| **B11** | `asked-of: [typo]` | passes, **and `pact waits` prints it back as a live gate**. The security persona nominated the agent as its own approver |
| **B12** | a money-typed `amount` with `spends-money:` omitted | **zero diagnostics.** And a rule with `more-than: 100000000 USD` marks the action guarded, silencing the warning for every payment below — which is a *warning*, and there is no `--deny-warnings` |
| **B13** | a contended `claim` on a shared board | 0 diagnostics. The identical action marked `spends-money: yes` triggers exactly-once + cross-agent reachability + approval. **The machinery exists and is keyed to the word *money*** |

### B.3 Structural

| # | Issue |
|---|---|
| **B14** | **No way to run an agent.** `pact try` does not exist. Every defect above was found by *reading*; the two worst findings of the review cycle needed *running* — a suspension crossing a delegation boundary silently becomes a member failure, making an approval gate vanish on the unmodified flagship |
| **B15** | **The reader table is not held to the schema.** ~90 hardcoded `.get("<field>")` literals checked against nothing. `available.rs` iterates `("skills","knows")` and `("resources","uses")` — **the agent group has neither field**, so G12 is never checked and one arm always warns falsely. `derive.rs` names three collections that do not exist |
| **B16** | **The trust lattice is unbuilt.** `trust:`, `sanitises:`, `written-by` → **0 declarations**. Its motivating example is one component laundering text another reads — which is what `Grant.so_far` already does, as prose, today. **Required before any shared state ships** |
| **B17** | **Adapter ABI ≠ documented ABI.** No `model_stream`, no `tool_call` verb, no `ToolCallContext`, no `lattice.yaml`, no attestation; the runtime uses a fourth lattice value (`emulated`) that conformance never validates |
| **B18** | **No delegation depth limit or cycle guard.** Two-level teams are not refused at load time, not documented as unsupported, and fail as an opaque `RuntimeError` |
| **B19** | **TypeScript port diverges** — currency parsing wrong on 4 of 6 spellings, `parseInt` accepts trailing garbage. The two ports print different words for the same file |
| **B20** | **Schedules are invisible to every verb.** `pact waits` promises "the deadline a runtime must set a timer for" and returns empty `wake-ups` for a schedule port — **on the shipped example** |
| **B21** | **Observability points at a removed spec.** FR-7.1.5 mandates OTel `gen_ai`, which was **removed from core semconv in v1.43.0** and has no schema URL to pin. And there is no `pact.step.replayed` — without it every cost and latency aggregate double-counts recovery |

---

## C. Public availability — what blocks release

| # | Blocker | Evidence | Fix |
|---|---|---|---|
| **C1** | **Zero commits.** `git rev-list --count HEAD` → 0 | the entire history of this work is uncommitted | commit |
| **C2** | **No LICENSE file**, while `Cargo.toml` declares `license = "Apache-2.0"` | legal blocker for both open-sourcing and crates.io | add Apache-2.0 + NOTICE |
| **C3** | **`cargo package -p pact-cli` FAILS** | `include_str!("../../../spec/schema.yaml")` and `../../../models/catalog.yaml` reach **outside the crate root**; verified — 0 files under `spec/` or `models/` in the package list, then `error: failed to prepare local package for uploading` | a `pact-spec` crate that *owns* `schema.yaml`, `models/catalog.yaml` and `spec/questions/`, depended on by the others. **This is a code change, not a release process** — the gap register calls it the latter |
| **C4** | No `CONTRIBUTING`, `SECURITY`, `CODE_OF_CONDUCT`, `CHANGELOG`, `CODEOWNERS` | all missing | standard set |
| **C5** | No published binary, no `pip install pact` | everything is `cargo run` from a checkout | crates.io in dependency order; PyPI for the adapters |
| **C6** | **The documents describe a different system.** 39 constructs specified and absent from the schema; three flagship examples that do not load; four named loops that do not exist; the FRD reports 33/120 with evals and portability at zero | a public reader starting at "Functional Requirements" gets a picture thousands of tests out of date | schema normative; Graph → a not-built register with re-admission fixtures; regenerate the FRD |
| **C7** | **No deprecation channel.** Fields are deleted and refused by name (R42, R57, R59, R60, R61) — right, and it makes every deletion breaking | Eve's checker still loads a deprecated slot and names the exact rename | a soft channel for a field on its way out |
| **C8** | **Discovery is entirely reactive.** No `pact init`, no templates, no `explain` | **8 of 10 personas — all five non-technical — got unstuck only by opening `examples/refund-desk`**; one needed 32 `pact check` runs | `pact init` with templates; ship the schema with the binary so a coding agent can author against it |
| **C9** | **No spec governance.** Who owns the schema, how it changes, what a version means to a consumer | `pact-version:` exists; the process does not | a written process before external adopters exist |

**The load-bearing correction:** the D14 bar is **one file, 34 lines, 29 keys** —
not the 132 of the showcase example. Vocabulary size is *not* the barrier to
public adoption. **Discovery is.**

---

## D. Sequence

Each phase ends in a gate that is a test, not a judgement.

### P0 — Unblock (hours)
`LICENSE` · first commit · **`pact try` + one real end-to-end run (D9)**.
*Gate:* an agent answers a question on this machine.
**`pact try` is first because the instrument is what the safety phase is measured
with** — not because it is developer convenience, which is how I first filed it.

### P1 — Safety (days)
One `park()` helper (B1/B2/B4) · route `answer-with-what-it-has` through the
chain (B3) · bind approvals to the arguments approved · the map-under-text arm
(B8) · `resources.endpoint` into the egress walk (B9) · `loader/reads-nothing`
generalising `profile-selects-nothing` (B10) · `asked-of:` may not name an agent
(B11) · infer `spends-money` from a money-typed argument + `--deny-warnings`
(B12) · refuse two-level teams (B18) · generalise the reader-table test (B15).
*Gate:* each defect has a test that fails before and passes after.

### P2 — Make the documents true (days)
Schema normative · Graph, `pact.lock`, the lattice, the escapes and the 36
assertions → `21-NOT-BUILT.md`, each with its re-admission fixture · regenerate
the FRD from the schema · extend the code-fence gate to **loadability**.
*Gate:* every fence in the normative documents loads.

### P3 — The ladder (weeks)
`pact init` + templates · declare `based-on:` on all **14 kinds it already
resolves** and is documented on one · `pact explain --tidying` · `pact check
--json` · ship the schema with the binary.
*Gate:* a support lead reaches the D14 bar with ≤ N check-failures and **zero
reads of `examples/`**. Baseline: 32 runs, 8 of 10 reading the example.

### P4 — Expression (weeks), cheapest-first
A1 output constraints · A2 `retrieval-context:` · A3 `is:`/`is-one-of:` · A4
`list of` · A5 `same-request-key` scope · A12 the three unreadable shapes — *then*
A6 `tries:` · A7 `knowledge:` · A8 `durability:` · A9 sandbox.
*Gate:* the RAG shape, the self-consistency shape and the contended-claim shape
each have a workspace that loads **and runs**.

### P5 — Publishable (weeks)
The `pact-spec` crate (C3) · crates.io in dependency order · PyPI · the standard
governance files · the deprecation channel.
*Gate:* `cargo install pact` and `pip install pact-adapters` on a clean machine.

### P6 — The studies that decide the claims
**AC-1.5** — the moderated non-programmer study, never run, and by the ADR's own
account the deepest bet in the project · **CTS Stage A** — the per-metric null
band, which needs no second adapter and is the thing AC-2.2 is currently
unevaluable without.

---

## E. What is already good and must survive

Any redesign that loses these has gone backwards.

- **A diagnostic is unconstructable without a fix** — enforced by constructor
  signature, with four independent layers of pile-on suppression.
- **Semantic reachability warnings** — *"money moves without anybody being
  asked"* is a check across four documents. Nothing in the 140-repo corpus does
  this.
- **Five honesty channels** — `unmetered` / `unenforced` / `unwatched` /
  `never_reached` / `unretrieved`. The fourth has no counterpart anywhere; the
  fifth is separate from `unenforced` because its recipient is, *the corpus was
  never read* being a sentence for whoever runs the thing rather than for the
  author of the document.
- **The schema is data.** No slot table. Adding a field costs a YAML block.
- **Governance survives compaction by construction** — policies are re-applied
  from the document, not carried in history. The measured failure mode
  (0% → 30–59% violation from one compaction step) is **unreachable here**,
  except via B3.
- **`survives-shortening:`** — pins facts that were never messages. No framework
  surveyed lets an author declare what may not be dropped.
- **Skills carry applicability boundaries** — `use-when:` / `do-not-use-when:` /
  `if-unsure:`, which is exactly what the literature names as the missing thing
  that makes skills harmful.
- **Ceilings are deterministic bounds**, mandatory and checked before each tool
  call in a batch — in a field where 68 confirmed infinite-loop failures were 66%
  concentrated in the two frameworks with the strongest cycle validators.
- **The `debate` pattern** — star through a judge, bounded rounds, adversarial
  split: the topology and agent count the evidence favours.
- **690 + 1,207 sentence-named tests, doc↔code drift guards, and a gap register
  that argues against its own author.** That habit is why this list could be
  written at all.
