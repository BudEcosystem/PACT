# PACT — Independent Review, and a Proposal

**Date:** 2026-07-31, revised 2026-08-01 after adversarial review.
**Status:** Proposal. Not binding.
**Companion:** `91-REVIEW-CRITIQUE.md` — six adversarial lenses attacked this
document; every attack was independently re-verified before it was believed.
**50 upheld, 32 overturned.** The corrections that change conclusions are folded
in below and marked; the full edit list, and the thirteen claims six lenses could
not move, are in the companion.
**Method:** every number below was produced by running a command against this
repository or read from a paper in `research/papers/`. The command or the
citation is given so any row can be disputed. Nothing is inherited from an
earlier document in this repo — several rows contradict them.

**Scope:** a full read of the specification and implementation; a source-level
comparison against Vercel Eve; and a literature review of agentic patterns,
loops, memory, compaction, durability, skills, tools and protocols current to
July 2026, with 100 papers now in `research/papers/`.

---

## 0. The finding, in one paragraph

**There are two PACTs, and the gap between them is the project's central
problem.** The one in `docs/` is a topology-IR architecture: a `Graph` with eight
node kinds, six channel kinds, an edge algebra, a lockfile, a capability lattice,
typed escapes and 36 deterministic assertions. The one in `spec/schema.yaml` +
`crates/` + `adapters/` is a **stage machine, a waiting vocabulary, and a
closed-sentence governance layer** — and it is smaller, sharper, more honest, and
on the evidence of its diagnostics and its five honesty channels, **better**. The
documented Graph has zero implementation and no schema group. Almost every
"gap register" entry in this repository is a symptom of that unmade decision,
and almost every genuine strength of the shipped system is uncited because the
documents are describing a different artifact.

The proposal is therefore not *add things*. It is: **decide which one is PACT,
make its own promises checkable, close six live safety defects, and buy the
capabilities the evidence says are load-bearing and PACT cannot express.**

**And one finding outranks all of that.** A cold-authoring trial — ten personas,
five of whom cannot write code, each building a real agent against the shipped
checker — found that **nothing in PACT constrains what the agent *says* or
*concludes*.** Every enforcement surface reaches actions. Six of the ten needed a
rule about an output — *answer only from the handbook*, *never give medical
advice*, *never double-book*, *stop at the first failed step* — and none could
write one.

The structural reason is narrower than it first looks, and the narrowing makes it
both cheaper to fix and worse than described. **The harness already stops on an
output**: `Decision.stop` is honoured at `turn.message.after` (`harness.py:2848`)
and at `step.message.after` (`:1262`). What is missing is that **no sentence form
in the closed vocabulary has a condition that reads the answer's content** — both
stopping sentences are tool counters bound to `at: [step.tool.before]`
(`spec/schema.yaml:2894`). So the moment works, the power works, the harness
works, and there is no way to ask.

Which produces a **seventh defect this review did not have**:
`may: [stop-the-run]` at `turn.message.after` **loads clean and can never fire** —
a declarable power nothing can produce from a file. That is precisely the defect
R24 deleted `change-the-request` and `change-the-answer` for, reintroduced one
field over.

The fix is a **vocabulary entry plus one predicate row**, not harness wiring —
still cheaper than any capability in §5.3, and it unblocks more real tasks than
all of them combined.

---

## 1. What is actually shipped

Measured, not read.

**The two test counts are written by `./scripts/sync-counts.sh`, not by hand**
(E3). They were `690` and `1207` for as long as it took somebody to re-run the
suites, in a table whose stated point is that every cell re-runs — which is the
same defect as everything this review is about, committed by the review. The
script counts both suites and rewrites the two cells below; `--check` prints
them and changes nothing.

| | |
|---|---|
| Schema | **43 groups, 262 field entries, 207 distinct field names** (core 123, expert 69, both 15), 40 closed enums, 27 cross-reference constraints, **0 fields missing `tier:` or `surface:`** |
| Rust | 5 crates, **1147 tests**, `unsafe_code = forbid`, clippy-deny, edition 2024 |
| Python | **47 modules** (`find adapters/python/src -name "*.py" \| wc -l`), **2487 tests**, **nine transports** — seven model-bound (`anthropic`, `autogen`, `langchain`, `langgraph`, `ollama`, `openai_agents`, `pydantic_ai`), one bound to a remote *agent* (`a2a`), one deterministic mock; `_metering.py`, `_summarise.py` and `_tool_choice.py` are shared code the transports import, which is what the `_` says — offline by default |
| TypeScript | 5 modules, 2,305 lines, a second port of **the stepping, the ceilings and the stage path** (`harness.ts:15-21`: *"AC-5.3's bar is the stage path"*) — **not** of the loop entire: no interceptor chain, no durable suspension record, no ledger (`notDoneHere`; a park returns `halted: "suspended"` and writes nothing down). This row is load-bearing for the Phase 3 pricing below (E4) |
| CLI | **6 verbs**: `check`, `show`, `waits`, `discover`, `card`, `help` |
| Worked example | 42 files, 1128 lines, **132 distinct authored keys**, `pact check` → OK (498 settings) |
| Minimum agent | 2 files, 4 keys → OK (7 settings) |

### 1.1 The five things that are genuinely excellent

These are the project's assets and no redesign may lose them.

1. **A diagnostic is unconstructable without a fix.** `Diagnostic::new` takes
   `fix` by signature (`pact-diag/src/lib.rs:198`). O7.3 enforced structurally,
   not by review. Four independent layers of pile-on suppression sit on top.
2. **Semantic reachability warnings.** Measured live:
   ```
   warning: `spends-money: yes` on `issue-refund` is not applied: `desk` can call
   it and no rule in its approval policy names `payments/issue-refund`, so money
   moves without anybody being asked.
   ```
   Nothing in Eve, and nothing in the 140-repo corpus, produces this.
3. **Five honesty channels** — `unmetered` (nobody could measure it),
   `unenforced` (nobody could evaluate it), `unwatched` (nowhere to write it),
   `never_reached` (the meter is right and always zero), `unretrieved` (the
   documents were never opened, so the answer is what the model already knew).
   The fourth has no counterpart anywhere and is the sharpest of them. The fifth
   is a fifth rather than a fifth use of `unenforced` because it has a different
   recipient: *the rule could not be evaluated* sends the reader to the rule,
   *the corpus was never read* sends them to whoever runs the thing.
4. **The schema is data.** No `match field_name` anywhere in `pact-schema`.
   Adding a field costs a YAML block and buys coercion, the directory form,
   span-accurate diagnostics, `x-` extension, digest participation and six
   constraint attributes.
5. **Doc↔code drift guards as tests.** The file count printed in the
   architecture draft is asserted against the tree; every Eve inventory row must
   carry a category; the README's portability claim is held against §7.28's
   lists. Few projects do any of this.

### 1.2 The Graph is unbuilt

```
$ grep -rn "desugar|Graph\b" crates/*/src adapters/*/src   → nothing relevant
$ grep -rl "kind: map|kind: route|on-reentry|channels:|edges:|blackboard" … → nothing
$ grep -n "^  graph:" spec/schema.yaml                      → nothing
```

AD-67 — *"ONE construct (`Graph`), TWO authoring surfaces, TWO reconcilers"* —
has no implementation and no schema group. Neither does `Profile`. The
architecture draft admits this at its own §16 item 13; that sentence is one line
inside 12,802, and every summary document above it describes the Graph as the
design.

Constructs the draft specifies normatively and the schema does not have,
**named rather than counted** (E5): `pact.lock` (~60 leaf fields, and §2.1
deletes `Lock` as a kind so none of it is machine-checkable), `lattice.yaml`,
the six typed escapes, the trust lattice, the 36 `pact:` assertions, eval
`severity:`/`splits:`, `x-namespaces:`, the `ESC-*` escalators, the optimiser
ABI, and `impl:` — so the `no-code` badge's own linter clause *"rejects any
`impl: code` reference"* has no referent.

**This sentence used to open *"an independent audit … found 39 constructs"*, and
the audit does not exist.** `grep -rn "39 construct" docs/ research/` returns
this line and the critique row that caught it, and nothing else — no list, no
command, no file. A figure with no artifact behind it is not a measurement, and
attributing it to an *"independent audit"* borrowed authority the number had not
earned. The named examples above are each checkable in one grep and are what the
paragraph was always resting on; the number was resting on nothing. It stays
uncounted until somebody commits the list — the same standard this review's own
method paragraph sets, applied to this review.

**Three of the draft's flagship examples do not load**: §6.2's suite (the section
that *defines* the eval suite), §11.9's small-model variant, and §11.10's
`learning.yaml`. **Four loops named in the draft do not exist**
(`pact:loop/minimal`, `plan-execute`, `self-consistency`, `codeact`) — and §5.3c
says `stop-sequences` is *"required by `pact:loop/codeact`"*. §7.11 says *"Two
shapes ship."* Six ship.

### 1.3 Seven defects, three safety-relevant — three since fixed, four still live

All were in code the gap register listed as CLOSED. None was caught by a test.

**Re-measured against the tree as it stands, and the table now says which are
still there.** A review that keeps claiming a defect somebody has fixed is the
same failure as a register claiming a fix nobody made — it is this document's own
stated method (*"every number below was produced by running a command"*) pointing
the other way, and the four fixed rows below were still written as live. Each
`FIXED` row names the line that closes it so the claim can be disputed in one
`sed`; each `LIVE` row was re-run today.

| # | Defect | Status | Consequence |
|---|---|---|---|
| **S1** | `escalate()` copied `used` and `granted` with a comment for each and **did not copy `spent_keys`** | **FIXED** — `suspension.py:670` `spent_keys=tuple(self.spent_keys)` | was: an escalated wait returns with an empty at-most-once ledger — **a refund issued before the park can be issued again** |
| **S2** | four of five park sites never set `Suspension.used`; only the budget park did | **FIXED** — every park site now goes through `_park_state` (`harness.py:2203`), which sets `used`, `granted` and `spent_keys` in one place (`:2246-2248`) | was: `Meter.restored({})` rebuilds tokens, money, tool-calls and seconds at **zero** — **parking for an approval hands the run a fresh spend budget** |
| **S3** | `_ran_out`'s `answer-with-what-it-has` path made a model call and assigned `result.output` with **no `chain.run("turn.message.after", …)`** — it did not even take `chain` | **FIXED** — `chain` is now a required keyword argument of `_ran_out` (`harness.py:2265-2267`, *"required rather than defaulted … a caller that forgets it loses the rules on the closing answer in silence"*) and the path runs the moment at `:2388` | was: **that setting escapes every redaction rule in the workspace**, contradicting `_finish`'s own docstring |
| **S4** | a person's answer to an `ask-someone` stage is appended to history directly | **NARROWED, half still live** — the *answer* door closed with S3: when the stage is the last one the reply goes through `_finish`, which runs `turn.message.after` (`harness.py:3139`). The *history* door did not: `harness.py:1253-1254` appends the person's words to `result.steps` and to `history` with no `chain.run` anywhere between `:1204` and there | a redaction rule never sees what a person typed into a wait, so it reaches the next model call — narrower than "same bypass, second door", and not nothing |
| **S5** | `harness.py:2917` — `if out.halted != "final" and out.halted not in RAN_OUT: raise RuntimeError(...)`, and `"suspended"` is **absent** from `RAN_OUT` (`limits.py:463-465`, which holds only the five ran-out names) | **LIVE, and it is the safety-relevant one this review did not have** | **any suspension raised inside any team member becomes a member *failure***. A member that parks to ask a person is not a member that failed; the author's `if-someone-fails:` then decides, and with `carry-on` the approval gate vanishes **with no human asked at all**. `RAN_OUT`'s own comment says it is *"every way `RunResult.halted` can say a ceiling ended this"* — a park is not a ceiling, so the guard is asking the wrong question rather than holding a stale list |
| **S6** | `anthropic_transport.py:206` builds `_request` and never uses it — `self._message(history, system)` on the next line takes neither the tools nor the settings | **LIVE** | tool schemas, `max-tokens`, `temperature`, `tool-choice` are dead while `apply_settings` **reports them honoured** |
| **S7** | `Learner.from_document` (`learning.py:875-897`) never sets `baseline`, and `_drift` returns `0.0` when it is `None` (`learning.py:1278-1279`) | **LIVE** | the cumulative-drift gate — justified by *"17 of 25 MLAS attack-surface cells have no per-diff defence"* — evaluates `0.0 > limit` on every real cycle |

**S1, S2 and S4 had one cause**, and the fix was the one this review proposed:
the five park sites each assembled a `Suspension` by hand, assigning eight to ten
fields inline, and disagreed about which. **One helper closed three defects** —
`_park_state`, whose docstring records the measurement that justified it
(`tool-calls-at-most: 5`, three calls before an approval park and four after,
**seven against a ceiling of five**). S4's history half is the residue, and it is
a different bug in the same door: the park sites now agree about what they carry
*across* the boundary, and nothing yet governs what a person's answer carries
*back in*.

**S5 is new here and belongs with S1–S4 rather than with S6/S7**, because it is
the same class: a guarantee the author wrote down — *ask a person before money
moves* — dissolved by a run being one level deeper than the one that was tested.
It is not caught by a test, and it is not reproducible on the flagship
`refund-desk` by inspection alone, so it is recorded as read off the two lines
above rather than as a reproduction. That distinction is the one this review
keeps asking of everybody else.

**S1 and S2 are not ordinary bugs. They are the two published attacks on agent
checkpoint-restore, reproduced in this codebase.** ACRFence (arXiv:2603.20625)
names them:

- **Action Replay** — restore, and the agent re-synthesises a *different* request
  the server treats as new. Measured: **10/10 checkpoint-restore trials produced
  duplicate commits; 0/10 without checkpointing.** Their Table 1 lists the same
  defect across **12 frameworks** (LangGraph 8+, CrewAI 5 "Crew runs twice;
  emails resent", Claude Code 5, OpenClaw 6 with a GHSA advisory).
- **Authority Resurrection** — *"a consumed single-use approval token reappears
  in restored state"*; **2/2 token-reuse attempts succeeded** against stateless
  validation.

**PACT already has the primitives that close both**, which is what makes S1
serious rather than routine: `spent_keys` **is** the single-use consumption
record and `granted` **is** the approval capability surviving the park. S1 was
the one line where `escalate()` carried `granted` and dropped `spent_keys` — so
PACT shipped the defence for Authority Resurrection and reintroduced Action
Replay through the escalation path.

**S1 is fixed, so that last sentence is now a claim and not a proposal**, and it
is narrower than it was written. Closing S1 makes PACT the only spec in the
survey that structurally closes both **within an agent-run**. Across a team it
does not: the at-most-once ledger is constructed inside the per-agent run, and a
delegated member is started by a bare call that hands it neither the ledger nor
the accumulated tool-call history — so every member mints a fresh at-most-once
record and a fresh step list, and two teammates sharing a money tool defeat both
the ledger and the `so-far` tool counter. **Not reproducible on the flagship
example**: `fraud-checker` is `uses: [zendesk]` and `policy-checker` is
`uses: [refund-policy]`, neither reaches `payments`, and the harness refuses a
call a stage does not offer. The defect class needs a workspace where two agents
share a money tool — which nothing refuses (E7).

Two more, from the same audit, and **they have gone opposite ways**:

- **No delegation depth limit and no cycle guard** — still true. Two-level teams
  are not refused at load time and not documented as unsupported. What they fail
  *as* is now recorded as **S5** above, which is the more serious half and is a
  different bug: the `RuntimeError(f"{member} stopped: suspended")` fires on a
  one-level team the moment a member parks, with no depth involved at all.
  Keeping the depth guard as its own note, at lower priority, because it is real
  and it is not that.
- **The TypeScript currency parser no longer diverges.** This review said it
  *"diverges on 4 of 6 spellings"* and never named the six, which made the claim
  unreproducible as written; re-measured today it is **0 of 8**. Both ports were
  handed `0.05 USD`, `USD 0.05`, `$0.05`, `500 JPY`, `JPY 500`, `usd 0.05`,
  `$0.05 USD` and a bare `0.05`, through `Limits.from_mapping` and `limitsFrom`
  respectively, and agreed on the amount **and the currency noun** on every one —
  including the bare number, where both return an empty currency because nothing
  was written and there is no noun to print. The row stays in this document
  rather than being deleted: a defect that was real and is fixed is evidence the
  20-line comment the two parsers share is doing its job, and deleting it would
  leave the next reader unable to tell a fixed claim from one nobody checked.

### 1.4 The reader table nobody holds to the schema

~90 hardcoded `.get("<field>")` literals across `pact-loader` and `pact-cli`,
checked against `spec/schema.yaml` by nothing. Two live consequences:

- `available.rs:45` iterates `[("skills","knows"), ("resources","uses")]`. **The
  agent group has neither field.** So `available-when: this-agent-has-procedures`
  is never checked, and `this-agent-has-connections` **always** warns falsely.
  Undetected because `grep -rn "available-when" examples/` returns nothing — G12
  is not exercised by the shipped tree at all.
- `derive.rs:47` names `watches`, `schedules`, `redactions`. The workspace
  declares `watch`, `redaction`, and no `schedules` (R44 folded it into `port`).
  Three dead rows.

This is Eve's slot table in a quieter form: not a table deciding *what an author
may write*, but a table deciding *what actually gets checked*. **The fix already
exists and is used once** — `Schema::groups()` lets `currency.rs:156` ask *"every
field the schema types `money`"* instead of keeping names in a `const`.
Generalising its companion test to *every field name any loader module looks up*
closes both defects and the next one.

### 1.5 `based-on:` is wired for 14 kinds and documented for one

`derive::resolve` runs before validation and resolves `based-on:` across agents,
tools, skills, resources, policies, questions, interceptors, watches, loops,
ports, context-policies and evals. **It is declared as a field on exactly one
group — `loop` (`spec/schema.yaml:2387`).**

That is the mirror image of the defect this project keeps finding. The usual one
is *declared and wired to nothing*. This is **wired and declared nowhere** — and
it is the single cheapest DX win in the tree, because it is the fork-and-tweak
path FR-1.2.5 demands and Eve's own docs name as their worst gap (*"There's no
shared-skill mechanism… copy the markdown under each `skills/` directory"*).

---

## 2. Where PACT is ahead of the field and does not say so

The project measures itself against its own gap register and never against the
thing it is replacing. Seven wins, each with the evidence it should be citing.

**W1 — Governance survives compaction by construction.** ConstraintRot (1,323
episodes, 7 models, deterministic tool-call grading): a standing policy in
context gives **0%** violation; **one compaction step gives 30% pooled, up to
59%**. Where the constraint survives the summary: **0% (n=90)**; where dropped:
**38% (n=315)**. Tightening the summary budget 300→15 words drops survival
88%→23%. Reproduced in LangGraph (0%→65%), LangMem (95%), AutoGen (100%).
**PACT's `policy:`, `interceptors:` and `redaction:` are not in the message
history at all** — the chain is re-applied from the document at
`step.tool.before` every step. The failure mode is unreachable. *Except via S3,
which is why S3 is the highest-priority fix in this document.*

**W2 — Two constructs nobody else has.** `always-keep:` pins **messages**;
`survives-shortening:` pins **facts the run established, which were never
messages**. Every framework surveyed exposes compaction as a threshold plus a
prompt. None lets an author declare what may not be dropped.

**W3 — Skills carry applicability boundaries.** SkillsBench: curated skills
**+16.6 pp**; **self-authored skills −8.1 to −11.5 pp *below* the no-skill
baseline**; independently, LLM-authored **+0.0 pp** vs human-curated **+16.2 pp**.
The named cause of skill-induced harm is *"a single 'correct' pipeline without
applicability boundaries or lightweight fallbacks."* PACT's `use-when:`,
`do-not-use-when:` and `if-unsure:` are exactly that, and Agent Skills' six-field
format has no equivalent. The self-authoring result vindicates
`may-improve-on-its-own:` excluding new-skill authorship — D23, confirmed by
measurement.

**W4 — Tool effects are authored locally, which is now what MCP mandates.**
MCP `2026-07-28`: *"clients **MUST** consider tool annotations to be untrusted
unless they come from trusted servers."* PACT writes `reads-only:` and
`spends-money:` in its own tool file and refuses tools without one (R1).

**W5 — Judge independence is enforced.** `judge_is_not_the_model_under_test`
compares the `(model-id, provider, runtime)` tuple. The 2026 finding is that
reward hacking when generator and judge share context is *structural, not
exhortative*; and that relabelling an erroneous claim from the agent's own
`<thought>` to an external role lifts explicit-correction rate by **23 to 93
percentage points** across 7 model families (*"not a cognitive deficit; a
chat-template artifact"*).

**W6 — Exhausted is never success.** Every ceiling exits through one door,
`_ran_out`, which always sets `stopped_by` — including on the path that produces
a good answer. The loop-specification corpus finds 74% of real loops name their
terminal states and states the rule PACT already holds: *"an error or an
exhausted budget never counts as success."*

**W7 — Ceilings are deterministic bounds, and that is rarer than it sounds.**
A study of 6,549 agent repos found **68 confirmed infinite-agentic-loop failures
across 47 projects**, 100% root-caused to *"missing strong bound"* — and
**LangGraph (33.8%) and AutoGen (32.4%), the two frameworks with the strongest
cycle-exit validators, account for 66.2% of them.** A cycle-exit predicate is not
a bound when its controller is the model. PACT's ceilings are host-controlled,
mandatory (`needs-also: when-it-runs-out`), and checked at three points including
**before each individual tool call inside a batch** — because *"`tool-calls-at-most:
40` that lets the 41st through because it shared a batch is a suggestion, not a
ceiling."*

**Every one of these should be a line in the README and a test named after it.**

---

## 3. Where PACT cannot express what real agents need

Four gaps, ordered by how many real use cases they exclude.

### G1 — There is no data plane

The complete `agent` field list, printed by the checker:

```
name, description, instructions, team, teamwork, uses, accepts, answers-with,
answers-with-mode, run-inputs, needs, limits, settings, policy, evals, model,
model-for-checking, loop, variants, context-policy, remembers, interceptors
```

`retriev`, `vector`, `dataset`, `chunk`, `rerank`, `cite` → **zero hits in the
schema**. Tested cold: *"answer staff questions from the HR handbook"* **cannot
be written**. `state`/`remembers:` is facts a run established — a good design,
and not a corpus, a store, a retrieval policy or a consolidation rule.

The only available answer is `connect:` to an MCP retrieval server, which puts
**what the agent knows** entirely in the host. That breaks the project's own
claims twice: **T2** (if retrieval lives in the host, two substrates score
differently on the same folder for a reason the folder does not contain — the
oracle is measuring the host) and **R17's own words** (*"everything the system
does is in the folder you were handed"*).

Eval datasets have the same hole: `evals` takes `case` documents only; D19's
fifth on-ramp has no door for a corpus.

### G2 — A stage cannot run twice with different context

The shipped loop is a state machine over stages **that all share one
conversation**. It therefore cannot fork context, compare branches, carry a
per-branch score, backtrack, fan out over N items, or share mutable state
between agents.

The shipped library is admirably honest about exactly this —
`tree-of-thought.yaml` says *"This is a tree only in the sense that three
branches are written down and two are cut"*, and `answer-more-than-once.yaml`
refuses the name `self-consistency` because *"self-consistency samples the model
INDEPENDENTLY … This does not do that, and cannot."* **Those two comments are
the finding**: six loops ship, AC-5.2 is recorded MET, and two of the six are
named after techniques they explicitly do not implement — for the same missing
primitive in both cases.

What that primitive is worth, measured:

| Technique | Result |
|---|---|
| Recursive Tournament Voting over **structured summaries** | Claude-4.5-Sonnet SWE-bench **67.4→73.6%**, Terminal-Bench **40.6→54.6%** |
| Parallel-Distill-Refine, select-K vs single-summary re-entry | **+8.19 pp** vs **+1.00 pp**, same model, same budget shape |
| Agentic aggregation over K trajectories | up to **+10.3 pts** on deep research; **majority voting is the worst aggregator tested** |
| Confidence-gated selection (CATTS) | **+4.7 pp at −56% tokens** |
| Gap-directed fan-out over a claimable evidence board (Argus) | **+12.7 pts at 8 workers**; 86.2% BrowseComp at 64, orchestrator context **under 21.5K tokens** |

The last row matters twice: it is the blackboard the gap register records as
impossible on today's primitives, and it now has a **published, benchmarked
reference implementation** to build a fixture against — which the market/auction
pattern still does not.

### G3 — Budget is a scalar, and the evidence says it must be a policy

Two independent results:

- **Overthinking cliff.** Marginal utility per 500 tokens for R1-32B on AIME:
  0.5–2K **+3.2%**, 8–12K +0.1, 12–16K **−0.3**. Accuracy peaks at 12K and
  *declines* at 16K. The negative/positive answer-flip ratio crosses 1.0 at
  **~7K tokens**; 67.5% of sampled flips are genuine overthinking. **Easy
  problems cross the threshold at 2K, hard at 8K — a single global budget is
  provably wrong for one of them.**
- **Where the thinking goes beats how many agents.** Orchestrator-only thinking:
  **+18.2 GAIA, +36.7 AIME, +10.0 MuSiQue**. Sub-agent thinking:
  **null-to-harmful, +77% latency vs +8%**. An **8B orchestrator matches a 32B
  single agent on GAIA (23.0 vs 23.0)** and beats it on AIME (55.0 vs 45.0); once
  orchestrator thinking is on, sub-agent size is irrelevant (23.0 / 23.0 / 23.6
  for 1.7B / 8B / 32B).

PACT's `teamwork.divides-the-budget:` divides **money**. It has no way to say
"think hard here, cheaply there" except `model-for-checking:`, which is per-stage
and singular.

### G3b — Durability is declared as one bit, and it is at least four

`durability` does not exist as a field at all; PACT declares that a run must
survive being killed and delegates the store (`50-NOT-COPIED.md` §4). That is the
right *division*, and it is under-specified in four ways the 2026 evidence makes
concrete.

**(a) Checkpointing is not durable execution, and the distinction is the whole
game.** For LangGraph — the most widely deployed checkpointer — *"If your process
crashes, no one knows. There is no supervisor, no watchdog, no heartbeat
mechanism,"* and *"If two processes try to resume the same `thread_id`
simultaneously… LangGraph has no built-in coordination to prevent both from
executing."* **A spec that says "durable" without saying *who detects failure*
has said nothing.** The class is declarable in one enum:
`none | checkpoint | durable-execution`.

**(b) Nobody pins an in-flight run to an agent definition.** Every serious engine
now pins *code*: Temporal Worker Versioning (GA), AWS Lambda Durable Functions
(version/alias), DBOS `application_version`, Restate immutable deployments,
Golem component version. **No agent framework pins a run to the agent it
started under.** PACT's digest is the closest thing in the field to a fix — and
one digest is too coarse, because the changes that matter to an agent are
invisible to journal replay. Restate is the only vendor to have written this
down: *"your code is the manual the LLM uses to interpret its own execution
history."* Changing a tool description from *"risk score from 0 to 10"* to
*"0 to 100"* leaves the transcript byte-identical and inverts its meaning;
removing a tool means *"the history references tool calls that no longer exist
and the agent will likely ignore them or hallucinate"*; changing a policy means
*"a human approval granted under one policy gets treated as an approval under a
different one."* Journal replay detects **topology change and nothing else**.

**(c) Effect class is the highest-value missing field in the spec, and PACT is
80% of the way there.** The research's verdict: an effect partition
(`pure | bufferable | reversible | irreversible`) plus a compensator and an
idempotency binding *"is the single highest-value field in the whole spec and no
protocol has it"* — MCP `2026-07-28` tool definitions carry `inputSchema` /
`outputSchema` and nothing about effects. PACT already ships `reads-only:`,
`spends-money:` and `same-request-key:`. What is missing is **reversibility and
its inverse**.

**(d) Isolation is a missing axis entirely.** A TLA⁺-verified study formalises
four anomalies under exactly the deterministic-replay regime durable engines
enforce — stale-generation, phantom-tool, causal-cascade, tool-effect reordering
— reproduces *"a silent lost update in ByteDance's deer-flow"* and
*"tool-effect reordering in LangGraph's `ToolNode`"*, and prices the fix at
**~8% tokens for snapshot isolation, 1.6–2.3× for pessimistic locking — not the
order-of-magnitude penalty commonly assumed.** **This binds directly on the
`board:` proposal in §5.3.3: shared state without a declared isolation level
ships lost updates.**

**(e) One PACT requirement is now pointing at a moving target.** FR-7.1.5 says
traces MUST use OTel `gen_ai` semantic conventions. As of July 2026 `gen_ai` was
**deprecated in core semconv v1.42.0 and removed in v1.43.0**, moved to a
dedicated repository with **no releases, no tags and no schema URL to pin**, and
nothing in it is marked Stable. `slo-observability.md`'s existing rule — *mirror,
do not `$ref`* — is now the only tenable position, and the requirement should say
so.

### G4 — Two shipped claims are contradicted by 2026 evidence

- **`pact:loop/plan-then-do`.** Its own comment claims *"The measured difference
  from `standard` on the same model and the same question is a real difference in
  behaviour."* Phase decomposition **regressed every model tested** on AgentFloor:
  −5, −6, −14, **−33 pp** (ministral-3:8b), paired bootstrap. Independently, the
  pre-registered hypothesis that planner-executor wins on file tasks was
  **falsified** on GAIA (supported in 1 of 10 cells; that cell does not survive
  the robust slice). **The shape is not wrong — its applicability is model-tier
  conditional, and PACT ships it with no such note.**
- **`check-its-work` and `pact:loop/reflexion`.** The critique stage reads its own
  trace in the same conversation. Correction rate moves **23–93 pp** on the chat
  *role label* alone. The fix is cheap and PACT can make it: present the prior
  answer to a `check-its-work` stage as an **external** message, not as the
  model's own turn.

And one assumption to retire: **scaffold sensitivity is not monotone in model
capability.** The largest scaffold gap measured belongs to **Opus 4.7**, the most
capable model in the study. The portability report must not assume "translating
down is risky, translating up is safe."

---

## 4. The DX problem, measured

The stated goal is *"even a normal user can create an agent, with best DX for a
senior dev with full control."* Both halves currently fail, for different
reasons.

### 4.1 The non-technical author has no ladder

**Corrected against an adversarial rebuild — my original number here was
misleading and the correction matters.** I wrote that "the D14 bar costs 132
distinct keys, 42 files, 1128 lines." That is the key count of
`examples/refund-desk`, a showcase carrying six questions, two interceptors,
redaction, watches, ports, a context policy, variants and run-inputs. **It is not
the cost of the bar.**

Measured by building the bar from scratch: **one file, 34 lines, 29 distinct
keys** (23 of them schema keys) — two agents joined by `team:`, a custom tool over
MCP, an eval case, an SLO ceiling with its action, and `learning: propose-only`.
That is D14 verbatim, and `pact check` returns `OK — loaded cleanly (36
settings)`.

**So vocabulary size is not the barrier, and the ≤40-key gate I proposed was
already passed before it was written.** The barrier is *discovery*: Priya needed
**32 `pact check` runs** to find her keys; every diagnostic fires only on
something already written, so a construct never guessed stays invisible; and
**eight of ten personas — all five non-technical, three of five experts — got
unstuck only by opening `examples/refund-desk`.**

The floor works (2 files, 4 keys, 7 settings). The bar is 29 keys away. **What
sits between them is not vocabulary but a search problem**, and there is no
`pact init`, no templates, no `pact explain` and no builder agent to make the
search shorter — only `pact check` and a 12,802-line architecture document.

`pact init` is filed in `50-NOT-COPIED.md` §6 as **deferred, not refused**,
because *"every argument for it is convenience and none of them is a
constraint."* That reasoning contradicts three things this repository already
holds: **FR-1.2.5** makes templates a **MUST**; the implementation plan says
*"fork-and-tweak dominates real usage (GPT Store: 3M built, 95% never shared)…
Authoring from scratch is the demo; forking is the product"*; and the ADR
schedules `pact init` to mint `workspace-id` (the tenancy key AD-7 requires to be
a ULID) and to write `population:` and `must-pass:` — three fields the author is
otherwise required to invent.

**A cold-authoring trial I ran myself**, as a reader who had already read the
schema, made four errors in four steps, each one a thing a support lead would
also make:

| Wrote | Schema wants |
|---|---|
| `policy:` with `description:` + `rules:` | `applies-to:` + `ask-a-person:` |
| `question:` with `asks:` | `says:` (`asks:` is a question's *name* everywhere else) |
| `takes:` with prose per argument | an answer-shape; there is nowhere to say what an argument *means* |
| `case:` with `description:` + `asked:` | `when:` + `expect:` |

Underneath two of those is a rule with no learnable pattern: **`description:` is
required on 10 kinds, optional on 8, and refused on 26** — including `policy`,
`case`, `learning`, `teamwork`, `limits`, `stage`. Two different words carry
"why this exists" (`description:` on 18 kinds, `because:` on 4) and they never
co-occur. The shipped `policies/approvals.yaml` therefore carries **no statement
of what it is for**, on the document that decides when money stops for a human.

### 4.2 The senior dev cannot run an agent, and cannot escape

- **There is no way to converse with an agent.** `pact run` is *"not a PACT
  verb"* by design (NG1). `pact-eval` scores an eval suite. There is no
  `pact try`, no dev server, no REPL. A developer with this repository cannot ask
  their agent a question.
- **`pact check` refuses to resolve `port.through:`** (correctly — it names a
  host binding), but nothing else fills that hole either.
- **Escape hatches: the docs specify six typed escapes; the schema has none.**
  `impl:` does not exist. The only escape is a `scripts/` folder in a skill,
  which PACT records and never runs. That is right for `pact check` and it leaves
  a senior dev with **no in-tree extension point at all**.
- **Over half the adapter test files gate on the Rust binary and skip without
  it.** The loader is disk-bound; Eve's `ProjectSource` in-memory abstraction is
  the fix. **The figures are deliberately not written here** — this line said
  *"1207 adapter tests, but 48 of 69 files … and 19 tests silently skip"* and all
  three had moved. The live count is stated once, in `scripts/test-all.sh`'s
  refusal message, and `test_the_gate_is_run_by_something.py` fails when it stops
  matching `grep -rl 'pytest.skip("build the CLI first' adapters/python/tests/`.
  **The silence itself is closed**: the gate now refuses to run the suite at all
  when `target/debug/pact` is absent, so the skip can no longer be reported as a
  pass.

---

## 4b. The cold-authoring trial

Ten personas — five who cannot write code, five senior engineers — each built a
real agent against the shipped checker, unaided. Every attempt was recorded and
every verdict was independently re-run before it was believed. **All ten
workspaces reproduce exactly; six persona claims were overturned** (notably: `one
of a, b, c` *does* work on `answers-with:`; `loop.steps` *is* an ordered-process
construct; `always-keep:` *is* read, by four readers — it is a phrase match, not
a name). What survived is below, most severe first.

### 4b.1 The finding that outranks everything else in this document

**Nothing in PACT constrains what the agent SAYS or CONCLUDES.** Every
enforcement surface reaches *actions*: `policy:` holds only `applies-to` and
`ask-a-person`; `limits:` is cost and speed; `context-policy:` is compaction;
`interceptor.rules:` is five closed sentences — three that hide patterns, two
that count tool calls.

The structural reason, verified directly: **the moments that see the model's
output (`step.message.after`, `turn.message.after`) accept only the hiding
sentences, and the only moment that can `stop-the-run` (`step.tool.before`) never
sees an output or a tool result.**

Six of ten personas needed it and none could have it:

| Persona | Needed | Attempts spent |
|---|---|---|
| Priya (HR) | answer only from the handbook, refuse otherwise | 9 |
| Amara (clinic) | never give medical advice | 4 |
| Lena (retail) | two people must never be double-booked | 7 |
| Tom (finance) | stop at the first failed step | 6 |
| Marcus (sales) | ask a human when *the agent's own score* is hot | — |
| Researcher | route on the verifier's score | — |

**And it is in neither `50-NOT-COPIED.md` §5 nor §6.** R11 and R19 refuse
*interceptors that run code* and *sentences PACT cannot carry out* — not this
capability. By §0's own rule — *"If you find an Eve capability that is in none of
the three, that is a defect in this file"* — this is the fourth category that
document says cannot exist.

**PACT states the asymmetry itself.** Binding a stopping rule at the moment that
sees the answer produces, verbatim:

```
error: Nothing at `turn.message.after` can carry this rule out, so it would do nothing.
  fix: Change `when:` to one of: step.tool.before.
```

The message is excellent and it is the evidence: the only moment that can stop a
run is the one that never sees an output. *(Reproduced by me directly, along with
§4b.2's map hole — `loop:` with an arbitrary map gives `OK — loaded cleanly (9
settings)`, and it counts the junk key as a setting — and §4b.4(1)'s egress hole:
`allow-egress: []` beside `endpoint: https://ingest.evil.example.com/v1/mcp` and
an upload action loads cleanly.)*

**The fix is one sentence in the vocabulary that already exists, at a moment that
already exists:**

```yaml
when: turn.message.after
may: [stop-the-run]
rules:
  - if the answer does not name a <skill>, stop and say "<why>"
```

The moment, the power, the sentence matcher and the refusal machinery are all
built. Today the moment that sees the answer cannot stop, and the moment that can
stop cannot see the answer. **This is cheaper than every capability I proposed in
§5.3 and it unblocks more personas than all three combined.**

### 4b.2 One validator arm is missing, and it silently ate a persona's schedule

**A YAML map written under any `type: text` + `names:` field is swallowed whole,
with arbitrary keys, and produces no diagnostic.** Verified for `loop:`,
`policy:`, `context-policy:` and `model:`. A **list** in the same position is
caught correctly (`'loop' should be some text, but it is a list`); a map under a
`list of` field is caught; a map under a `one-of` field is caught. **This one arm
is missing**, and it sits underneath the exact spot four personas reached for a
rule construct.

Tom wrote `loop:\n  schedule: ...`, then `loop:\n  banana: purple elephants on
tuesday`, and got **two clean green runs** believing his monthly timer was
configured.

**Cheapest high-value fix in the entire trial**: one arm in the schema validator,
reusing the message that already exists beside it — *"'loop' should be some text,
but it is a set of settings."*

### 4b.3 `pact check` says OK on workspaces whose central control is inert

Six independently reproduced instances:

| # | Written | What happens |
|---|---|---|
| a | `judged:` eval rules with **no `graded-by:` anywhere** | clean OK; the safety rule never runs |
| b | `does: use-tools` stages in a workspace with **zero tools** | clean OK (Tom shipped eleven) |
| c | `based-on:` beside authored `steps:` | **silently switches OFF the reachability check** — measured both ways: with the line an orphan stage passes; delete it and `loader/stage-nothing-reaches` fires |
| d | `metrics[].uri: nonsense_no_colon` | loads clean, though the schema's own help promises *"A name with no colon in it is refused rather than guessed at"* |
| e | a non-string `expect:` | asserts nothing (`evals.py:539` `if not isinstance(want, str): continue`) and is not even reported on `unenforced` |
| f | any `x-` field | unvalidated, echoed by `pact show`, counted in the settings total |

**The fix is a diagnostic PACT already owns.** `loader/profile-selects-nothing`
already prints, in exactly the right voice: *"…and nothing in PACT reads it — so
this workspace behaves exactly as one with no `profile:` line."* It fires for one
field. Generalise it to `loader/reads-nothing`.

### 4b.4 Three governance holes the security persona walked through

1. **`allow-egress: []` does not govern the path customer data actually takes.**
   Its help says *"which parts of this system are allowed to talk to something
   outside this box. Empty means nothing is."* All six choices are **model
   roles**. Reproduced in one workspace: a hosted `model:` under
   `allow-egress: []` is refused by name; a `resources/*.yaml` with
   `endpoint: https://ingest.evil.example.com/v1/mcp` and a tool action uploading
   customer records **is silent**. The shipped example carries the comment
   *"Nothing about this system may talk to anything outside this box"* directly
   above that line.
2. **The money chain hangs off one deletable boolean, and any rule naming an
   action suppresses the warning that guards it.** An action named `pay`,
   described *"send money out"*, taking a `money`-typed `amount`, with
   `spends-money:` omitted → **zero diagnostics**. Add the tick and three checks
   fire. Separately, `loader/money-moves-with-nobody-asked` fires only when *no*
   rule names the action — so a rule with `more-than: 100000000 USD` marks it
   fully guarded and silences the warning for every payment below it. And it is a
   **warning**: `pact check` exits 0 with four of them and there is no
   `--deny-warnings`, so no pipeline can gate on it.
3. **The human half of the only human control is unvalidated free text.**
   `asked-of:` and `escalates-to:` are `list of text` with no `names:`. A typo'd
   audience passes `check` **and** `pact waits` prints it back as a live
   `needs-approval` wait with a real deadline. The tool half of the same gate is
   checked to the letter. The security persona **nominated the agent as its own
   approver and escalation target.**

### 4b.5 An approval can only compare money

`when-this` has exactly three fields — `tool`, `arg`, `more-than` — and
`more-than` is `type: money`. So a score, a tier, a store boundary, a region or
any status value **cannot gate anything**. The only workaround is to split the
action in two and gate one half unconditionally — which moves the business rule
out of the policy file and hands *the model* the decision about whether a person
is asked. Both personas who did it ended with a gate that is not a gate; Lena's
two "different" tools point at the identical URL.

**Fix: `is:` and `is-one-of:` beside `more-than:`.** That is data in the shape
`more-than:` already has, decidable at check time against machinery that exists
— `arg:` is already resolved against `inspects:`, and `answers-with:` already
parses `one of a, b, c`.

### 4b.6 Six more, each with a small fix

- **`durable-resume` does not exist and `50-NOT-COPIED.md` §4 says it does.** The
  table's middle column reads *"that a run must survive being killed and resume
  to the same place"*, and R3 repeats it as the reason for refusing a
  durable-execution dependency. `grep -n durab spec/schema.yaml` → one unrelated
  comment. **A recorded delegation whose declaration half was never built** — and
  therefore unfalsifiable by `test_every_field_has_a_reader.py`, which walks
  fields that exist. §4 has at least one other stale row: it offers *"a resource
  of kind `sandbox`"* and R58 narrowed `resource-kind:` to `[mcp-server]`.
- **Answer shapes are flat scalars only.** No `list of`. A citation list or a
  findings list is declarable only as one `text` blob — at the exact boundary
  PACT owns, since `answers-with:` is what evals grade against.
- **Evals cannot carry per-case retrieval context, and the plumbing is already
  built and disconnected.** `providers.evaluate_metric` **takes a
  `retrieval_context` parameter and forwards it into `LLMTestCase`**; its only
  caller in `evals.py` never passes one, because no field exists. So the four
  canonical RAG metrics are accepted by name and can never return a score.
  **One schema field and a one-argument change at a single call site** — the
  smallest edit for the largest capability recovered anywhere in the trial.
- **`waits-for: enough-of-them` means "the first N back", not "the best N".**
  `delegation.py:433` counts `state == ANSWERED`; the rest are cancelled. The
  help says *"how many of the team have to come back with a **good** answer"* —
  which reads as selection-by-quality and is selection-by-latency.
- **Schedules are invisible to every verb.** `pact waits` promises *"the deadline
  a runtime must set a timer for"* and returns an empty `wake-ups` for a schedule
  port — confirmed **on the shipped example**, whose `ports/weekly-review.yaml`
  says `kind: schedule` / `every: Friday at 4pm` and produces 13 approval waits
  and no timer.
- **Discovery is entirely reactive.** Every diagnostic fires on something you
  already wrote, so a construct you never guessed is invisible. A workspace with
  **no `ports/` at all** — meaning nothing can reach the agents — loads cleanly.
  Priya built **40 skill files for one handbook**, clean pass, wrong shape,
  because the fix line for a `.md` under `skills/` says *"Write it as `name:
  value` lines"* and never mentions front matter or the `SKILL.md` + `references/`
  folder form that the schema documents as first-class.

**And the headline number: all five non-technical personas, and three of the five
experts, got unstuck only by opening `examples/refund-desk`.** That is AC-1.5's
answer, obtained in simulation: the example is currently doing the job `pact
init` is supposed to do, and it is the only thing doing it.

---

## 5. Proposal

Ordered by (evidence × cheapness). Every item names the test that proves it
landed.

### Phase 0 — Run it, then stop the bleeding (days)

**0.0 — `pact try` and the D20 cold run come FIRST, as the instrument the rest of
this phase is measured with.** I originally filed `pact try` in Phase 2 as a
developer convenience. That was the worst scheduling error in this document, and
the adversarial round is right about why.

**Every defect in §1.3 was found by reading code. The two worst findings of the
whole review cycle were not — they required running the shipped example:**

- **A suspension crossing a delegation boundary is silently converted into a
  member *failure*.** On the unmodified flagship, with `if-someone-fails:
  carry-on`, an approval gate simply vanishes and the reply goes out with no
  human asked. Reading `harness.py:2626` gives you a `RuntimeError`; only running
  it shows you the person being told *"One of the checks could not be
  completed."*
- **The at-most-once ledger is per-agent-run, not per-request.**
  `harness.py:467` looks correct in isolation; it is the bare call at `:2610`
  that makes it wrong, and that is an execution-path fact.

`pact check` cannot see any of this. It said `OK` on the workspace with no
`ports/`, on the map-under-`text:` hole, on the `based-on:` collision, and on
every one of §4b.3's six inert controls. **The checker is not an oracle for the
loop.** So D9's *"one real end-to-end run"* — which this review did not mention
anywhere — is Phase 0's exit gate, and the proofs below are written against a
harness that has been watched running.

*This correction applies to the review itself: it is an authoring-surface review
with a code-reading annex, and it never executed an agent. That is the same
category of claim it convicts `50-NOT-COPIED.md` §4 of making about
`durable-resume` — a promise recorded in a document with the half that would
falsify it never built.*

| # | Do | Proof |
|---|---|---|
| 0.1 | **One `park()` helper** filling the whole durable block; all five sites call it | S1/S2/S4 each fail before, pass after; a sixth park site that forgets a field fails the suite |
| 0.2 | **Route `answer-with-what-it-has` and the `ask-someone` answer through the chain** | a workspace with `redact-card-numbers` and `when-it-runs-out: answer-with-what-it-has` does not emit a card number |
| 0.3 | **Generalise the reader-table test**: every field name any loader module looks up is a field the schema declares | `available.rs`'s `knows`/`resources` and `derive.rs`'s three dead rows fail it |
| 0.4 | **Delete or wire `Learner.baseline`**; refuse a drift limit with no baseline | a cycle with `drift.at-most` and no baseline is refused, not silently passed |
| 0.5 | **Refuse two-level teams at load time** until delegation depth is designed | `loader/team-too-deep`, naming the line |
| 0.6 | **Fix the TS currency parser and `parseInt`**; add the six spellings to the conformance payload | `test_the_typescript_target_agrees_too` fails before |
| 0.7 | **Bind an approval to the arguments it approved.** The correlation key already hashes `(reason, step, sorted things-waited-on)`; add the canonicalised argument values, with a per-action `same-request-key`-style projection so a nonce can be excluded | an approval issued for `issue-refund(order=99, amount=50)` is refused against `issue-refund(order=99, amount=5000)`. Today the question is bound to the *call slot*, not to what was shown to the person |

0.7 is the second half of the ACRFence fix and the cheapest guarantee in this
document: the approver reads `shows: [amount, order-number]`, and nothing
currently makes the resumed call carry the amount they read.

### Phase 0b — The trial's findings, in cost order (days)

Every item is small, and each closes something a persona hit. **This phase
outranks Phase 3 and should be done first**; I had it ranked lower before the
trial ran.

| # | Do | Cost | Proof |
|---|---|---|---|
| **0b.1** | **One sentence at `turn.message.after` with `may: [stop-the-run]`** — §4b.1. The single highest-value change in this document | one form entry + one wiring line | an agent that answers without naming a skill is stopped; 6 personas' blocked tasks become writable |
| **0b.2** | **Refuse a map under a `type: text` field** — §4b.2 | one validator arm | `loop:\n  banana: purple` fails; today it is green |
| **0b.3** | **`is:` / `is-one-of:` beside `more-than:`** — §4b.5 | one group, two fields | `{tool: crm/write, arg: score, is: hot}` gates; today only money can |
| **0b.4** | **Generalise `loader/profile-selects-nothing` → `loader/reads-nothing`** — §4b.3 | one rename + N call sites | `judged:` with no `graded-by:`, `use-tools` with no tools, a colonless metric URI and every `x-` field all say so |
| **0b.5** | **`based-on:` must not disable the reachability check** — §4b.3(c) | a bug fix | an orphan stage fails with or without the line |
| **0b.6** | **Add `resources.<r>.endpoint` to the egress walk**, governed by an `allow-connect:` hostname list — §4b.4(1). Immediately and for free: reword `allow-egress:`'s help to say it governs *model roles* | one row in `egress.rs:37-45` | a public `endpoint:` under `allow-egress: []` is refused |
| **0b.7** | **An action whose `takes:` declares a `money` argument must state `spends-money:` explicitly** — §4b.4(2). And make `guarded_by` read `more-than:`, so an unreachable threshold stops counting as a guard. And add `--deny-warnings` | `needs-also` machinery already exists | omitting the tick on a money action fails; a 100,000,000 USD rule no longer silences the warning |
| **0b.8** | **`asked-of:` / `escalates-to:` may not name an agent** — §4b.4(3). Then a workspace `people:` map with `names: people` on both | one comparison against a map the loader holds | an agent cannot approve its own actions |
| **0b.9** | **`retrieval-context:` on a case** — §4b.6. `providers.evaluate_metric` already takes the parameter and its only caller never passes one | one field, one argument | `deepeval:faithfulness` returns a score instead of nothing |
| **0b.10** | **`list of <shape>` in the answer-shape vocabulary** — §4b.6 | one entry beside `one of a, b, c` | a citation list is typeable, so an eval rule about it is writable |
| **0b.11** | **Schedule ports appear in `pact waits`'s `wake-ups`** — §4b.6 | output only | the shipped example's `Friday at 4pm` produces a timer, not silence |
| **0b.12** | **Three fix-line corrections and one help-text correction** — the map-as-list fix emits invalid YAML if followed literally; `shaped-like:`'s message has nothing to copy; `rules:` on an agent suggests `uses:` and steers away from `loop:`; and `enough-of-them`'s help says "good answer" when the code counts the first N back | text | each is one string |
| **0b.13** | **`requires-of-the-runtime: {durable-resume: yes}`** — §4b.6. The decision is already taken in R3 and §4; only the line is missing. Plus a test that every §4 row's middle column names a field that exists | one field | the row stops being unfalsifiable, and the stale `sandbox` row is caught |

### Phase 1 — Make the documents describe the system (days)

The single highest-leverage change in this document, and it is all deletion.

1. **Declare the schema normative.** `docs/20-ARCHITECTURE-DRAFT.md` becomes
   `docs/20-RATIONALE.md` and is explicitly non-normative.
2. **Move the Graph, `pact.lock`, `lattice.yaml`, the typed escapes, the 36
   assertions, the trust lattice, `x-namespaces:` and the optimiser ABI into
   `docs/21-NOT-BUILT.md`**, each with the fixture that would re-admit it. This
   is the method `50-NOT-COPIED.md` already uses and it works.
3. **Rewrite `30-FRD.md` from the schema**, not by hand. It currently reports
   33/120 with evals, portability and orchestration at zero, five days and
   several thousand tests out of date.
4. **Extend the code-fence gate to loadability.** Three flagship examples in the
   draft do not load; four named loops do not exist. A fence that does not load
   is a defect in the same class the gate already catches for verdicts.
5. **Write the seven W-claims into the README with their citations.** The project
   is stronger than its own front page.

### Phase 2 — The ladder (weeks)

**`pact init` is not convenience. It is the mechanism by which 132 keys becomes
reachable.**

1. **`pact init [template]`**, minting `workspace-id`, writing `population:` and
   a `must-pass:` chosen from a target case count, and **printing the steps it
   cannot run**. Templates, from the shapes that actually occur:
   `single`, `supervisor`, `pipeline`, `answers-from-documents`, `triage-and-route`,
   `scheduled-report`, `approve-then-act`.
2. **Declare `based-on:` on all 14 kinds it already resolves.** Thirteen YAML
   blocks turn an invisible mechanism into the fork-and-tweak path. *This is the
   cheapest item in this document and possibly the highest-value.*
3. **`pact explain`** — the composition chain, the desugaring, and
   **`--tidying`**: what compaction removed, which rung removed it, which pins
   held. `Tidied` already carries `before`/`after`/`outcome`/`did`/`notes` and
   `step.compaction.completed` already emits them; **nothing renders it.** The
   memory literature's own recommendation is that *"a simple memory diff…
   provides more diagnostic value than traditional log analysis."*
4. **`pact try <agent> "question"`** — one turn, against a served model or the
   deterministic mock. Not a server (NG1 holds); a door. Its absence is why a
   senior dev cannot evaluate this project in an afternoon.
5. **Make `description:` universal.** Optional on all 43 kinds; keep `because:`
   where it is genuinely a *reason shown to a person*, and say so in one line.
6. **Emit `pact check --json`** with the existing rule ids. That is three of
   D18's four authoring surfaces for one emitter.
7. **Ship the schema and a `PACT.md` with the binary**, as Eve ships `docs/` and
   points coding agents at it. D18's "conversation with a builder agent" surface
   costs nothing more than this.

**Gate — restated, because the original was already passed.** The bar is 29 keys
today (§4.1), so a key-count gate measures nothing. Gate on the search instead:
**a support lead reaches the D14 bar with ≤ N `pact check` failures and zero
reads of `examples/`** — Priya's 32 runs and eight-of-ten example-reads are the
baseline. That is AC-1.5, which has never been run and is, by the ADR's own
account, the deepest bet in the project.

### Phase 3 — The three capabilities (weeks)

Only three. Each names the evidence and the smallest construct that closes it.

**3.1 — `tries:` on a stage.** One field. A stage may run *n* times over
**independent contexts**, folded by a declared selector:

```yaml
steps:
  work:
    does: think
    tries: 3                    # independent contexts, not three turns
    keep: the-one-most-agree-with     # | the-best-scored | all-of-them
```

This closes real self-consistency, best-of-N, CATTS gating, ToT branch
comparison and PDR's `distill` re-entry — and it lets
`answer-more-than-once.yaml` finally be named after what it does. **It needs no
edges, no channels, and no condition language.** Two known-correct defaults from
the literature: fold over **structured summaries, not raw traces**, and
**majority is the wrong default selector** for long-horizon work.

**3.2 — `knowledge:` — the data plane.** One kind, one agent field:

```yaml
# knowledge/handbook.yaml
description: The HR handbook.
from: handbook/**.md          # or `connect: <server>` for a live index
answers-from: text            # what a retrieved thing is
at-most: 5                    # ← S-EXEC. top-k is a safety parameter, not a knob
must-cite: yes
freshest-by: updated-at       # deterministic supersession, not a judgement
```

Three things the evidence forces into the design rather than leaving to a host:
**top-k is an attack-surface parameter** (attack success rises 6% → 20% → 38% as
k goes 3 → 5 → 10 while injection *acceptance* stays high); **freshness must be a
declared deterministic aggregation** (all 22 systems in MemoryAgentBench
underperform an explicitly-stated "newest wins" rule; a purpose-built bi-temporal
graph scores **7.0%**, the worst of the 22; candidate-extraction + `max(serial)`
beats the best published system by **+28 pp** at 262K); and **citations must be
declarable**, because grounding sufficiency is a validated independent predictor
of hallucination resistance.

Without this, the most common enterprise agent shape cannot be written, and T2's
oracle is measuring the host.

**3.3 — `board:` — shared state between teammates.** A `state` a team may read
and write between turns, with the writer recorded. That is the blackboard, the
market and the auction — the three AC-5.1 patterns the gap register records as
impossible — and Argus is the fixture to build against, not an invented lease
design.

**3.4 — Four durability declarations, three of them one line each.**

```yaml
# workspace.yaml
durability: durable-execution        # none | checkpoint | durable-execution
                                     # `checkpoint` means nobody detects failure. Say so.

# tools/payments.yaml → actions.issue-refund
  effect: irreversible               # pure | bufferable | reversible | irreversible
  undone-by: cancel-refund           # required when `reversible`; refused otherwise
  same-request-key: order-number     # already exists; now required when not `pure`

# agents/desk/board.yaml (with §3.3)
  one-at-a-time: yes                 # the isolation level, in the one word that fits
```

And the digest, promoted from one value to a **vector with a per-part action**,
because the parts differ in how dangerous drift is:

| Part | Drift is | Default on resume |
|---|---|---|
| topology (loop, team, stages) | detectable by replay | **refuse** |
| tool contract (names, args, effects) | detectable on next call | **refuse** |
| policy (approvals, redaction, limits) | invisible | **refuse** — an approval granted under one policy is not an approval under another |
| model binding | invisible | **refuse** |
| tool *descriptions* — what the model reads | **invisible and catastrophic** | **refuse** |
| instructions, skills | invisible | resume, record the drift |
| knowledge index (§3.2) | invisible | resume, record the drift |

`pact waits` already walks every wait a tree can produce. **This makes the same
walk answer "which parked runs would this deploy break?"** — the question every
version-pinning engine exists to answer, and no agent framework can.

### Phase 4 — Honesty about what the loops do (days)

1. **Model-tier applicability on pattern sugar.** `plan-then-do` regressed every
   model tested; the resolver should warn below a declared tier. The shipped
   comment's claim that the difference is "measured" should cite something.
2. **Present a `check-its-work` stage's input as an external message.** 23–93 pp,
   for a role label.
3. **`halt.controller` — one enum.** Classify every exit as
   `deterministic | model | tool | external`. PACT's ceilings are already
   deterministic; this makes the property *visible* and would have caught all 68
   real hangs in the study. One field, and PACT is the only spec that has it.
4. **Reversible compaction.** ACE's entire gain (**+3.6 to +8 GAIA points across
   four frameworks**) comes from re-deciding `raw | abstract | drop` per step
   each turn against a lossless store — impossible if compaction is a destructive
   edit. PACT's ladder is destructive. This is the largest single accuracy result
   in the compaction literature and it is a change to *where the store lives*,
   not to the authored vocabulary.
5. **Amend FR-7.1.5.** `gen_ai` left core semconv in July 2026 and has no schema
   URL to pin. Mirror the attribute names, do not depend on them, and define the
   `pact.*` set the standard has no vocabulary for: `pact.run.attempt`,
   **`pact.step.replayed`** (without it every cost and latency aggregate
   double-counts recovery), `pact.step.key`, `pact.spec.drift[]`,
   `pact.suspend.reason`, `pact.suspend.blocked_ms`, `pact.approval.{subject,
   single_use, expires_at, outcome}`, `pact.tool.{effect_class, idempotency_key,
   dedupe_hit}`, `pact.run.outcome`. Two normative rules fall out and PACT
   already half-holds both: **suspension time is `blocked`, never latency**, and
   **every spec digest is on the root span** so a trace says which agent produced
   it.
6. **`keep-room-for:` on `context-policy`** — reserve the control-plane budget
   and check it **before** the ladder runs. The measured minimality result:
   best-effort assembly gives **0/48 fail-closed and 25–48/48 silent incomplete
   control**; adding a preflight gives **25–48/48 fail-closed, 0/48 silent**.
   `if-it-still-does-not-fit: stop` is already the right shape; only the
   preflight is missing.

### Phase 5 — What to take from Eve

1. **35 machine-readable diagnostic codes written to a file** → `--json`, above.
2. **A deprecation channel in the checker.** Eve's deprecated slot still loads
   and names the exact rename. PACT deletes fields and refuses them by name —
   right, and it makes every deletion breaking.
3. **Versioned capability contracts validated before any extension code runs**,
   with unknown names failing closed — the finished shape of `bundle.brings:`,
   whose `from:` currently resolves nothing.
4. **`ProjectSource`** — an in-memory tree source. Removes the largest fragility
   in PACT's own suite (19 silently skipped tests).
5. **A deterministic `mockModel()` as a documented fixture**, so a multi-step
   tool-loop test needs no served model.

---

## 6. What I would not do

- **Do not build the Graph.** Nothing in the 2026 literature needs eight node
  kinds. `tries:`, `knowledge:` and `board:` cover every measured pattern and
  preserve the property that makes PACT authorable: **there is no condition
  language.**

  **The honest cost, since I opened this document by measuring the format's size
  and then did not measure my own proposal.** Everything proposed here adds
  roughly **21 new field names (207 → ~228, +10%)**, **4–6 groups (43 → 47–49)**,
  **4 closed enums (40 → ~44)** and **~69 field entries (262 → ~331, +26%)**.
  "Three constructs instead of thirty" is a comparison against *the Graph's*
  thirty, not against schema size, and it should never have been written without
  the after-number beside it. Two mitigations, both real: the largest single line
  item — making `description:` universal — **deletes** a refusal rather than
  adding a rule; and the highest-value item in the whole document, 0b.1, adds an
  entire enforcement class for **one form entry and zero new field names**. That
  is the standard every Phase 3 item should have to meet before it earns a name.
- **Do not add an expression language** (R6, R14). Every result in §3 is
  reachable with closed vocabularies.
- **Do not admit code mode**, but **price the refusal in the ledger.** It is the
  best-measured tool-scaling mitigation available (**150,000 → 2,000 tokens**;
  flat-catalogue selection recovery **13.6% → 43%+**; **+11% accuracy at −24%
  tokens**) and the least no-code-compatible thing in the field. R42 is
  defensible; the cost is currently undisclosed.
- **Do not chase framework count.** Seven targets already agree byte-for-byte on
  a bounded subset. The eighth buys less than `pact init` does.

---

## 7. The three claims this review would most like to be wrong about

1. **That `pact init` is the binding constraint on D21.** If a moderated study
   shows a support lead reaching the D14 bar without templates, Phase 2 shrinks
   to `explain` and `try`.
2. **That the data plane must be in the spec.** If retrieval can be pushed to the
   host without making the eval suite measure the host, G1 collapses to a
   documentation problem.
3. **That the Graph should be deleted rather than built.** If the topology IR is
   needed for `gaia-ai-runtime` integration in a way this review has not seen,
   §6's first bullet is wrong and Phase 3.3 is the wrong shape.

Each is falsifiable, and the first is falsifiable this quarter.
