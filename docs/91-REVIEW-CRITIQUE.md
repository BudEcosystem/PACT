# Revision of `docs/90-REVIEW.md` — precise edit list

50 attacks upheld. Where two upheld attacks name the same text they are merged into one edit. Edits are in document order. **DELETE** means the item is withdrawn, not weakened.

---

## A. §0 — the headline finding

**E1 — §0, lines 40–42. Rewrite the structural sentence. (upheld: "the moments that see the model's output cannot stop the run")**

Replace:

> The structural reason is exact: **the moments that see the model's output cannot stop the run, and the moment that can stop the run never sees an output.**

with:

> The structural reason is exact, and it is narrower than it looks: **the closed sentence vocabulary has no form whose condition reads the answer's content.** Every stopping sentence is a tool counter (`spec/schema.yaml:2894-2903` binds both counting sentences to `at: [step.tool.before]`). The harness already honours `Decision.stop` at `turn.message.after` (`harness.py:1262-1267`, `2848-2853`), and `may: [stop-the-run]` bound at `turn.message.after` **loads clean today and can never fire** — a live R24 instance (a declarable power nothing can produce), which is a seventh defect this review did not have.

Consequence to carry into 0b.1 (E14) and §4b.1 (E11): the fix is a vocabulary entry, not harness wiring.

**E2 — §0, line 43.** `cheaper than any capability in §5.3` survives, but the price changes. Replace "one sentence in a closed vocabulary that already exists, at a moment that already exists" with "one `forms.one-of` entry in `spec/schema.yaml`, one new predicate row in `interceptors.py`'s `WIRED` table, and one guard". A content-reading condition **cannot** reuse `Carries.values`: `step.tool.before` also carries values but its payload is `{name, args, so-far}`.

---

## B. §1 — what is shipped

**E3 — §1 table, Python row (line 56).** `47 modules, 1207 tests, 7 transports + 2 more` → `**42 modules**, 1207 tests, **8 framework transports plus a deterministic mock**`. (`find adapters/python/src -name "*.py" | wc -l` → 42; transports/: a2a, anthropic, autogen, langchain, langgraph, ollama, openai_agents, pydantic_ai + mock.py.) A table whose whole point is that every cell re-runs may not contain a cell that does not.

**E4 — §1 table, TypeScript row (line 57).** `a second independent port of the loop` → `a second port of **the stepping, the ceilings and the stage path** (`harness.ts:15-21`: "AC-5.3's bar is the stage path") — no interceptor chain, no durable suspension record, no ledger (`harness.ts:208-216` `notDoneHere`; `harness.ts:451-456` returns `halted: "suspended"` with no durable record)`. This row is load-bearing for Phase 3 pricing — see E25.

**E5 — §1.2, line 106. (class-(c) evidence)** `An independent audit of the schema against the draft found **39 constructs**…` — the audit exists nowhere in the tree (`grep -rn "39 construct" docs/ research/notes/` → only this line). Either commit the list in the same edit Phase 1 item 2 proposes (`docs/21-NOT-BUILT.md`) and change the sentence to "the 39 constructs listed in `docs/21-NOT-BUILT.md`", or drop the number and keep the named examples. Same treatment for the other four class-(c) numbers:
- §1.1 line 75 `nothing in the 140-repo corpus produces this` — give the grep or cut the corpus clause (141 clones exist; no command supports the universal negative).
- §1.3 line 159 `diverges on 4 of 6 spellings` → **`diverges on 2 of the 3 spellings the schema's own help offers, and on 4 of the 6 I tested`**, with the six spellings named inline (`USD 0.05`, `$0.05`, `JPY 500`, `usd 0.05` diverge; `0.05 USD`, `500 JPY`, `$0.05 USD`, bare `0.05` agree) and both parser paths cited (`limits.py:479-500` vs `limits.ts:334-347`). Unreproducible as written because the six are never named.
- §2 W5 line 239 `reward hacking when generator and judge share context is *structural, not exhortative*` — carries no citation of any kind. Cite it or cut the clause.
- §4.1 line 443 `GPT Store: 3M built, 95% never shared` — inherited from `docs/40-IMPLEMENTATION-PLAN.md:56`, contradicting the review's own line 6-7 ("Nothing is inherited from an earlier document in this repo"). Source it or drop it.

**E6 — §1.3, insert a new row and renumber. (highest-severity upheld finding in §1)**

The delegation row at line 156-158 misnames the cause. Replace:

> Two more, from the same audit: **no delegation depth limit and no cycle guard** — two-level teams are not refused at load time, not documented as unsupported, and fail as `RuntimeError(f"{member} stopped: suspended")`

with a new **S5** row inserted into the table (renumbering the transport and learner rows to S6/S7):

| **S5** | `harness.py:2626` — `if out.halted != "final" and out.halted not in RAN_OUT: raise RuntimeError(...)`, and `"suspended"` is absent from `RAN_OUT` (`limits.py:353-355`) | **any suspension raised inside any one-level team member becomes a member *failure*** — reproduced on the shipped, unmodified `refund-desk`: `fraud-checker` alone parks correctly (`needs-approval`, `who_can_answer: ('support-leads',)`); the identical member as a teammate emits `step.delegate.failed` and the person is shown `carry-on-without-a-check`. With `if-someone-fails: carry-on` the approval gate on "nothing goes to a customer without a person seeing it first" vanishes with **no human asked at all** |

Then keep the depth/cycle guard as a separate, lower-priority note: *it is a real gap and it is a different bug.*

**E7 — §1.3, lines 148-154. Restate the ACRFence closure claim.** Replace `Fixing it makes PACT the only spec in the survey that structurally closes both` with:

> Fixing it makes PACT the only spec in the survey that structurally closes both **within an agent-run**. Across a team it does not: `once = Ledger(spec.request_keys)` is constructed inside `run_agent` (`harness.py:467`), `run()`'s 23-parameter signature (`harness.py:359-382`) takes no ledger, and `delegate_by_running` calls `run(...)` bare (`harness.py:2610-2612`) — so every delegated member mints a fresh at-most-once record and a fresh `result.steps`. Two teammates sharing a money tool defeat both the ledger and the `so-far` tool counter. Closing this needs `once` and the accumulated tool-call history threaded into `delegate_by_running`, exactly as `chain`, `teamwork` and `team_pot` already are — `harness.py:517` records that the pot was fixed for this reason.

Add the honest scope note: **not reproducible on the flagship example** (`fraud-checker` is `uses: [zendesk]`, `policy-checker` is `uses: [refund-policy]`; neither reaches `payments`, and `harness.py:1211` refuses a call a stage does not offer). The defect class needs a workspace where two agents share a money tool — which nothing refuses.

**E8 — §1.4, first bullet (lines 168-172). Restate the mechanism; it is wrong and the truth is worse.** Replace:

> `available.rs:45` iterates `[("skills","knows"), ("resources","uses")]`. **The agent group has neither field.**

with:

> `available.rs:45` iterates **three** pairs — `[("tools","uses"), ("skills","knows"), ("resources","uses")]` — of which `knows` is not an agent field at all, and `skills`/`resources` are NEEDS predicates (`available.rs:32-36` tests `has_something_under(a, "team"|"skills"|"resources")`) that are likewise not agent fields. So G12 is **inert in both directions**, and the false warning's fix line — `fix: Add \`resources:\` to 'a'` — instructs the author to add a field `schema/unknown-field` rejects. No workspace that passes `check` can reach the resources arm.

Add that fix line to 0b.12's list (E17). Phase 0.3's proof is unaffected.

**E9 — §1.5, line 184 heading and body.** `wired for 14 kinds` → `wired for 14 **names**, of which **10 are real top-level map collections**`. Add the two rows §1.4 does not have:
- `evals` is a **level error**, not a dead row: the workspace declares `evals: group:evals` (a single group), so `resolve_collection` walks the evals group's own fields and `based-on:` on an eval **case** is never resolved — reproduced: `error: 'based-on' is not something a case can have`. `models: group:catalog` is the same level error.
- `bundles: map of group:bundle` **is** a real collection `derive.rs` omits.

---

## C. §2 — the seven wins

**E10 — §2 W7, lines 251-253. DELETE the sentence.** Cut:

> **LangGraph (33.8%) and AutoGen (32.4%), the two frameworks with the strongest cycle-exit validators, account for 66.2% of them.**

These are raw counts out of 68 with no per-framework denominator (the paper's Dataset section reports no stratum sizes for the 6,549 repos), the phrase "strongest cycle-exit validators" appears nowhere in the paper, and the paper's own explanation inverts the review's causal reading: *"Both frameworks encode feedback through APIs rather than visible loop syntax… suggesting that IAL failures are not specific to one framework or loop idiom."* W7 needs no rate. Keep *"All 68 failures share the same root issue: the repeated path is not covered by a strong bound"* (2607.01641:1174) and add *"no framework enforces exactly-once semantics at the tool boundary"* (2603.20625 §1). **This sentence must not reach the README under Phase 1.5.**

**E11 — §2 W1, line 204-213. Annotate, do not retract.** Add after the ConstraintRot figures:

> Scope: the paper explicitly exempts system-message-preserving frameworks from its threat model and measures that channel at **+0** decay, versus +50 / +45 / +33 for a standing user instruction, a memory entry and a tool output. The framework reproductions are **n=20, DeepSeek-V4**. PACT is ahead of the exemption, not merely inside it: the chain is out-of-band entirely, so it also closes the memory channel the paper names as still exposed (+45). The paper's own defence — Constraint Pinning — is what `always-keep:` and `survives-shortening:` already ship, which merges W1 and W2.

**E12 — §2 W3, line 227-228.** `The self-authoring result vindicates \`may-improve-on-its-own:\` excluding new-skill authorship — D23, **confirmed by measurement**` → `— D23, **consistent with measurement**`, plus the disclosed confound (footnote 3: the self-generated runs used effort `max`, the baselines `high`) and the scope (the experiment is in-band, per-task, ungated authoring that *replaces* curation; PACT's loop is offline and eval-gated, so the paper does not measure PACT's design). Then take the two things W3 is missing and the paper does support:
- PACT's `skill` group carries **all three** parts of the complexity contract the paper proposes — `use-when:`/`do-not-use-when:`/`if-unsure:` **plus `costs-about:`** (`spec/schema.yaml:1287-1308`). That is a stronger W3 than the one written.
- Finding 6 (one Skill **+18.0 pp**, 2–3 **+19.0**, ≥4 only **+10.1**; compact/standard **+19.0/+21.5** vs comprehensive **+0.7**) is direct measured support for §4b.6's forty-skill-files finding, which the review currently reports only as a discovery problem.

**E13 — §2 W6, line 245.** `The loop-specification corpus finds 74% of real loops name their terminal states` → `a hand-coded survey of **50 published loop specifications** (single-author position paper, n=50) finds 74%…`. W6's substance needs no number: `_ran_out` always setting `stopped_by` is a property of the code.

---

## D. §3 — the gaps

**E14 — §3 G3, second bullet, line 341-343. DELETE and replace; it is false as written.** Cut:

> It has no way to say "think hard here, cheaply there" except `model-for-checking:`, which is per-stage and singular.

PACT expresses per-team-member thinking mode today, in four lines, and it loads clean: a boss with `settings: {thinking: high}` + `needs: {reasoning: deep}` and a helper with `settings: {thinking: none}` + `needs: {reasoning: simple}` → `OK — loaded cleanly (24 settings)`. That is exactly the intervention arxiv-2601.11327 §5.1-5.2 measures (thinking on/off per role, not a per-role token budget). Replace with the gap that is real:

> `settings.thinking` is per-agent and per-variant but **not per-stage**, so one loop cannot think hard in `plan` and cheaply in `do`. That is one field on `stage`.

And add a **seventh row to §1.3**: `teamwork.divides-the-budget:`'s help (`spec/schema.yaml:3363-3370`) claims it shares out *"the money and thinking room"*; `harness.py:512-513` sets `team_budget = spec.limits.cost_per_request_under or 0.0` and `harness.py:524` builds `Pool(team_budget, …)` — money only. No token or thinking pool exists anywhere. A live doc↔code drift the review walked past.

**E15 — §3 G3 first bullet, line 328-333.** `**provably wrong**` → `suboptimal on the paper's own wording ("suggesting uniform compute allocation is suboptimal")`, and state the scope: DeepSeek-R1-32B and s1-32B, AIME 2024+2025, MATH-500 difficulty labels, open-weight only. (The attack on the 2K/8K figures and on "forced allocation" was overturned — those numbers are the paper's own words for the overthinking threshold and budget forcing is a floor *and* a cap. Do not change them.)

**E16 — §3 G4 first bullet, line 407-412.** Keep AgentFloor; state its scope and its diagnosed mechanism. Replace `Phase decomposition **regressed every model tested** on AgentFloor: −5, −6, −14, **−33 pp**` with:

> Phase decomposition regressed all four models tried — **four open-weight models, 4B–32B, prompt-level phase decomposition**: −5, −6, −14, **−33 pp** (ministral-3:8b), paired bootstrap. The mechanism the paper diagnoses for the largest regression is the model complying with *"Do NOT call any tools yet"* in PLAN and then emitting a prose answer **without ever entering EXECUTE** — which `pact:loop/plan-then-do` structurally forbids, since it routes **both** `used-a-tool: do` and `answered: do` (`spec/loops/plan-then-do.yaml:23-28`; `loops.py:473`). Rest the Phase 4.1 tier warning on the GAIA falsification instead, stating its scope (single independent author; H4 supported in 1 of 10 cells).

Phase 4.1's separate demand — that the shipped comment's word "measured" must cite something — stands unchanged.

---

## E. §4 and §4b — the DX findings

**E17 — §4.1, line 433-435. Fix the misattribution.** `The D14 bar costs **132 distinct keys, 42 files, 1128 lines**` → `**The worked example** costs 132 distinct keys, 42 files, 1128 lines` — which is what §1's table measures. D14's five requirements (`01-DECISIONS.md:124-126`) cost **23 schema keys in 34 lines in one file**, verified: `pact check` → `OK — . loaded cleanly (36 settings).`, exit 0. The 132 figure carries ports, policies, questions, interceptors, redaction, watches, skills, loops and context-policies, none of them in D14.

Keep the paragraph's actual argument (there is no ladder between 4 keys and the example) — it is untouched.

**E18 — §4.1, line 461.** `required on 10 kinds` → `required on **9** kinds` (agent, bundle, interceptor, port, question, skill, state, tool, watch). 9+8+26 = 43, matching §1's group count; 10+8+26 = 44 did not.

**E19 — §4b.1, table lines 510-518. DELETE the "Attempts spent" column.** The four numbers (9/4/7/6) carry neither a command nor a citation, against the review's own method statement at :4-6. Nothing in §4b.1's argument depends on them — the finding is structural and reproduces from the schema and the binary alone.

**E20 — §4b, opening (lines 487-493). Either commit the evidence or restate without it.** The ten workspaces live only in a session-scoped temp directory (`.claude/workflows/pact-dx-personas.js:15`); `ls docs/ac-1.5/` returns `PROTOCOL.md` only; no per-persona transcript survives anywhere. This is the review's highest-ranked evidence base and it is neither a repo command nor a paper. Commit the ten workspaces and their `pact check` transcripts under `docs/ac-1.5/personas/<name>/`, or restate §4b without the counts — §4b.1, §4b.2 and §4b.5 re-derive from the schema and binary and lose nothing.

**E21 — §4b.1, line 540-548. Change the example sentence.** Replace:

```yaml
  - if the answer does not name a <skill>, stop and say "<why>"
```

with:

```yaml
  - if the answer does not quote <a knowledge source>, stop and say "<why>"
```

`<skill>` is a proxy the model satisfies by emitting the skill's name — it reads to Priya as grounding enforcement and grounds nothing (R49's failure mode). The replacement matches against passages the run itself retrieved and holds, which is what §3.2 needs and what Priya asked for. The mechanism is not new: `spec/schema.yaml:2844-2845` already carries `resolve:` / `a tool: tools`, added because `<a tool>` used to be free text and *"`if paymnets is called more than 1 time` loaded clean and the second refund went through"*. `a knowledge source: knowledge` is one line in existing machinery.

Also correct the cost claim beneath it: *"one form entry, one `resolve:` entry, one wiring line"*.

**E22 — §4b.1, after line 538. Add the new finding.** `may: [stop-the-run]` bound at `turn.message.after` **loads clean today** (`OK — w2 loaded cleanly (507 settings).`) and can never fire. That is a declarable power with no producer — a live R24 instance. The alternative fix (refuse the power at that address) must be named and rejected on the record, not skipped.

---

## F. §5 Phase 0 — stop the bleeding

**E23 — Phase 0.1 (line 686). SPLIT. As written it ships S1 open with its own test green.**

`park()` cannot fix S1. S1 lives in `Suspension.escalate` (`suspension.py:641-662`), a Suspension→Suspension copy that enumerates 18 of 19 declared fields and omits `spent_keys` (declared at `:597`). The five park sites all call `suspend()` (`:757-782`), which sets only the "why it stopped" block and none of the durable block. **Nothing in the escalate path passes through `suspend()`**, so the proposed proof — "a sixth park site that forgets a field fails the suite" — does not exercise it.

Replace 0.1 with two rows:

| 0.1a | **One `park()` helper** filling the whole durable block; the five sites (`harness.py:1050, 1135, 1557, 1682, 2058`) call it | S2/S4 fail before, pass after; a sixth park site that forgets a field fails the suite |
| 0.1b | **Make omission unconstructable in `escalate`**: `dataclasses.replace(self, correlation_key=fresh, parked_at=now, if_nobody_answers="stop-and-say-so")` — the same move `Diagnostic::new` makes for `fix`. Plus a field-completeness property test over `dataclasses.fields(Suspension)` covering **all three** hand-enumerations: `escalate` (641), `to_json` (666-710), `from_json` (712-754) | S1 fails before, passes after; adding a 20th field to `Suspension` fails all three |

**E24 — Phase 0.5 (line 690). Rewrite; as written it fixes a depth problem the review misdiagnosed as the cause of a parking problem.** The `RuntimeError` fires at **one** level. Replace with:

| 0.5 | **A member suspension propagates**: the parent parks carrying the child's `Suspension` (reason, question, `who_can_answer`, `waits_for`, `escalates-to`) — the record already holds all of it. **Until that lands**, refuse at load time any workspace where a `team:` member can reach a rule in an `applies-to: every-agent` policy. And `pact waits` must mark member-owned waits, or the walk over-reports **6 of 13 on the flagship** | the shipped `refund-desk` no longer converts `fraud-checker`'s `needs-approval` into `step.delegate.failed`; `loader/team-too-deep` (the depth guard, now a separate item) names the line |

Add the dependency: **§5.3.4 cannot build "which parked runs would this deploy break?" on `pact waits` until member-owned waits are marked.**

**E25 — Phase 0, add three rows the verification produced.**

| 0.8 | **Hash payload file CONTENTS into the digest.** `pact_doc::digest` writes only `$file`/`contentType`/`sizeBytes` (`canonical.rs:86-92`; `lib.rs:495-502`), so a length-preserving semantic edit under a skill's `references/` or `scripts/` is invisible. Reproduced: `30 days`→`90 days` in `skills/refund-policy/references/window-table.md` and `timedelta(days=30)`→`(days=90)` in `scripts/check_window.py` both leave the digest at `sha256:87cb01fce41246bb…`; deleting the file gives `163733fe1adf…`, appending gives `c862b2c9…`, the same edit inside the inlined `SKILL.md` gives `143ffc4967b3…` | the function fails its own documented property 2 (`canonical.rs:10-11`); after the fix a content edit moves the digest |
| 0.9 | **Thread `once` and the accumulated tool-call history into `delegate_by_running`** — see E7 | two teammates sharing a money tool cannot each mint a fresh at-most-once record |
| 0.10 | **`pact discover` and `pact card` must run `derive::resolve`** — `main.rs:884-886` runs it in the check/show path only; `discover.rs:62-66` calls `Loader::load` bare and `card_cmd` goes through it (`main.rs:1405`). The drift guard that should have caught this is the comment at `main.rs:882`, which names "the schema, the digest, `show` and both adapters" and never added `discover`/`card` | a `based-on:` agent publishes its derived `description:` to discovery and to its A2A card; today `show` gives the derived block and `discover` gives `"description": null` |

**0.8 is a prerequisite of §5.3.4.** Do not ship a resume gate that is right for length-changing edits and silent for length-preserving ones. If it is not built, `docs/21-NOT-BUILT.md` must state that payload bodies are out of the digest's scope and `scripts/`/`references/` are unpinnable.

---

## G. §5 Phase 0b

**E26 — 0b.1 (line 706). Reprice.** `one form entry + one wiring line` → `one `forms.one-of` entry in `spec/schema.yaml` (the Rust check is data-driven and free), **one new predicate row in `interceptors.py`'s `WIRED` table**, one regex and one guard`. Not harness wiring — `harness.py:1246-1251`, `1262-1267` and `2848-2853` already honour `Decision.stop` and set `result.halted = "stopped-by-rule"`. See E1/E2.

**E27 — 0b.6 (line 711). Fix the citation and the rewording.**
- Proof column: `one row in \`egress.rs:37-45\`` → `\`egress.rs:182\` (\`fn reaches\`) and \`:293\` (\`pub fn refusals\`)`. Lines 37-45 are a markdown table inside a `//!` doc comment; a change there does nothing. (`const ROLES` is at `:67`, not `:69`.)
- The rewording is narrower than the code. `allow-egress:` gates **content** as well as models — `egress.rs:104-108` records exactly why two vocabularies are kept, and `fn reaches` implements three content-driven rows (`accepts:` audio, `answers-with:` audio, `needs: audio: yes`). Replace *"it governs model roles"* with **"which model calls, and which recordings, may leave this box"**, plus one clause saying it does not govern the servers under `resources:`.
- Make 0b.6 the first customer of 0.3: derive the walk from `Schema::groups()` — every field the schema types as an outside-the-box address — rather than extending the hardcoded `const ROLES`. Same move §1.4 praises `currency.rs:156` for, and it is what stops §3.2 needing a seventh hand-added row.

**E28 — 0b.11 (line 716). DELETE the remedy; keep the complaint.** `wake-ups` is not a list of timers: it is the subset of waits whose `deadline_ms` is set (`report.rs:105-113` `pub fn wakes(&self) -> bool { self.deadline_ms.is_some() }`), and `deadline_ms` is a **relative** duration derived from a question's `answer-within:`. `Friday at 4pm` is an absolute recurrence over `every:`, a deliberately open `type: text` field (`spec/schema.yaml:2298-2314`). Producing an entry needs a recurrence parser, a `now` and a timezone — none exist, and the clock is delegated to the host by §4, by NG1 and by `docs/20-ARCHITECTURE-DRAFT.md:7412` ("PACT has no clock and cannot grow one without becoming a server"). The cost line `output only` is wrong and the destination is wrong: a timer is an **arrival**, not a stop, and putting it on the list a runtime answers waits from puts an unanswerable row beside answerable ones.

Replace with:

| 0b.11 | **Emit the `every:` string verbatim and unparsed** in its own section or verb — file, line, `every:`, `answers:`, `says:`, `if-still-running:`. And fix `pact waits`'s help, which today promises *"the deadline a runtime must set a timer for"* | output only, no clock, no new stop reason | the shipped example's `Friday at 4pm` is printed; `pact waits`'s help stops implying it covers the clock |

**E29 — 0b.12 (line 717).** Add the fifth string: `loader/never-offered`'s fix line `Add \`resources:\` to 'a'` names a field `schema/unknown-field` rejects (see E8).

**E30 — 0b.13 (line 718). DELETE the field. Keep the test.** `requires-of-the-runtime: {durable-resume: yes}` beside Phase 3.4's `durability: none | checkpoint | durable-execution` is **two settings for one decision**, which R59 (`50-NOT-COPIED.md:487`) already refuses in this repository with a measured reason — *"six spellings for three real states, and two of the six say opposite things. MEASURED: `enabled: propose-only` beside `auto-apply: yes` printed 'OK — loaded cleanly', exit 0."* The identical arithmetic holds: 3 values × yes/no = 6 spellings for 3 states, and `durable-resume: no` beside `durability: durable-execution` is a legal contradictory pair. Duplicating a refusal made with a good reason is a fatal flaw in the item, not a hedge to be softened. `durable-resume: yes` is just `durability:` being at least `checkpoint`.

Rewrite 0b.13 as:

| 0b.13 | **A test that every `50-NOT-COPIED.md` §4 row's middle column names a field that exists**, pointed at Phase 3.4's `durability:` | one test | the `durable-resume` row stops being unfalsifiable, and the stale `sandbox` row (R58) is caught |

And add the open question 3.4 must answer rather than silently override: §4's row is **unconditional** — *"a run must survive being killed and resume to the same place"* (`50-NOT-COPIED.md:404`) — so `durability: none` is either inadmissible or §4's row needs rewriting. Decide it in the open.

---

## H. §5 Phase 1

**E31 — Phase 1, line 722. Rewrite the "all deletion" claim.** Replace `and it is all deletion` with:

> and it is deletion plus one mechanical repoint — **24 files, 70 references, 5 test files**, and `section("7.3")` / `section("7.7")` in `crates/pact-cli/tests/one_name_for_how_a_team_waits.rs`, in the same commit. The drift guards are what makes this safe: they fail loudly rather than rot, which is why asset #5 survives the move rather than being lost by it.

(The three "normative-and-consumed" citations were checked and read backwards — `reachability.rs:4-6` and `main.rs:989-991` cite §7.6 as **prior art for a rule they had to write themselves**; `delegation.py:23-26` cites §7.3 to say the draft was **wrong**; and the test asserts that *"§7.3 has to say that the schema is where the words come from"*. That test is evidence **for** Phase 1.1, not against it. Do not weaken the item.)

**E32 — Phase 1.2, add one line.** After *"each with the fixture that would re-admit it"*, add: **the `bud.dev/v1` converter corpus IS the re-admission fixture for the Graph** — `kind: Workflow`'s 5 node kinds and 10 condition ops, `kind: Team`'s 11 strategies, `spec.handoffs` (`docs/20-ARCHITECTURE-DRAFT.md:10546, :10552, :10555-10556`).

---

## I. §5 Phase 2

**E33 — Phase 2.2 (line 749-751). Three corrections; the third is a blocker.**
- `all 14 kinds it already resolves. Thirteen YAML blocks` → **`all 10 kinds it actually resolves. Nine YAML blocks`**, and make 2.2 explicitly downstream of 0.3 — declaring `based-on:` on `watch`/`redaction`/`schedules` creates the mirror defect §1.5 exists to end. Reproduced: `watch: {a: {…}, b: {based-on: a, …}}` gives `error: 'based-on' is not something a watch can have` **plus** the two missing-field errors that `derive.rs:80-88`'s own comment says removal exists to suppress.
- Add: **a derived entry must restate `name:`**, or `name:` is excluded from inheritance and defaults to the map key. Today the shallow-copy rule inherits `name:` — `pact check` → `OK — w1 loaded cleanly (11 settings).` and `pact show` prints agent `b` as `{"name": "a", …}`.
- Add the real blocker (E25 row 0.10): **`pact discover` and `pact card` do not run derivation**, so under 2.2 every forked agent is published to discovery and to its A2A card with none of its inherited fields. 2.2 cannot ship before 0.10.

**E34 — Phase 2 gate (line 769-771). DELETE the key-count gate.** `the D14 bar reachable in **≤ 40 distinct keys** from a template, down from 132` cannot discriminate: D14's five requirements cost **23 keys** hand-written today, with no template (E17). Replace the gate with the one the review already pairs with it one clause later:

> **Gate:** run AC-1.5 — the moderated study that has never been run — and gate on a support lead reaching the D14 bar with N or fewer `pact check` failures and **zero reads of `examples/`**.

Note in passing the finding that minimal workspace produced: it has no `ports/`, so nothing can reach either agent, and `pact check` says OK anyway — §4b.6's own defect, reproduced from the other direction.

**E35 — Phase 2, add one line. (D20 / AD-92 omission)** The seven-phase reordering contains no item for build target #1. Add:

> 8. **AD-92's two `gaia-ai-runtime` changes + the D20 cold-execution demo** on the tree produced by `pact init`. Phase 2 delivers the *authoring* half of D20 (`01-DECISIONS.md:181-187`, *"This outranks the portability demo"*); it stops one step short of the *execution* half D2 requires (`docs/25-ARCHITECTURE-DECISIONS.md:302`, :500-514).

`grep -nE "D20|AD-92|gaia-ai-runtime" docs/90-REVIEW.md` returns zero hits for the first two. Nothing in §5 or §6 argues against D20; this is a missing line, not a re-litigation.

---

## J. §5 Phase 3 — the three capabilities

**E36 — 3.1 `tries:` (lines 777-793). Keep the capability. Delete "one field" and reprice; it is the most under-priced item in the document.**

Replace the illustrative value:

```yaml
    keep: the-best-scored             # | all-of-them
                                      # `the-one-most-agree-with` also exists —
                                      # majority is the worst aggregator tested (§3 G2)
```

— printing `the-one-most-agree-with` as the illustrative value contradicts the sentence eight lines below it (*"majority is the wrong default selector"*) and §3's own table (*"majority voting is the worst aggregator tested"*).

Then **defer `the-best-scored` from the shipped enum** unless the judge generalisation lands in the same phase. There is nowhere in PACT to write a score: the `stage` group's fields are exactly `does, says, asks, then, may-use, at-most` (`spec/schema.yaml:2422`); `answers-with:` is an **agent** field (`:401`); `when-this` is `{tool, arg, more-than: money}`. And `judge_is_not_the_model_under_test` is structurally incapable of seeing a second scoring surface — it opens `let Some(judge) = root.get("evals").and_then(|e| e.get("graded-by")) else { return };` (`main.rs:661-664`) and is a `Diagnostic::warning` (`:690`) with no `--deny-warnings` to gate on. Ship `keep: all-of-them` (which does the PDR/select-K work on its own) plus `the-one-most-agree-with`; re-admit `the-best-scored` when 0b.3's `is:`/`is-one-of:` and a per-stage answer shape exist, bound to `model-for-checking:` (`spec/schema.yaml:494` — *"think with a cheaper model, check with a better one… that is a stage"*), with `judge_is_not_the_model_under_test` generalised from `evals.graded-by` to **every judging binding in the tree**. That generalisation is the named fixture.

Replace *"One field"* and *"**It needs no edges, no channels, and no condition language.**"* with an honest price list:

1. **The ceilings.** State that a stage with `tries: n` counts **n against `steps-at-most:`** (`spec/schema.yaml:1006`) and **once against `runs-for-at-most:`** (`:1025`) when the tries are concurrent. The consumption meters (tokens, tool-calls, money) need no statement — they charge at the point of spending. W7 is the review's strongest claim and it rests on the ceilings being exact; `tries:` is the first construct in PACT that multiplies work.
2. **The pot.** One `team_pot` per request (`harness.py:514-524`), one flat step index (`harness.py:1010`, `meter.steps = i` assigned not incremented), one `_ran_out` door (`harness.py:1013`, `1204`, and `2001-2027` — *"Every path sets `stopped_by`, including the one that produces a good answer"*). Either give `tries:` a division rule in the shape `teamwork.divides-the-budget:` already has, or state that all n branches share the parent's pot and the first to exhaust it ends the turn — and add the check-time diagnostic, because `tries: 3` under `cost-per-request-under: 0.05 USD` is a one-branch agent with two branches of wasted latency.
3. **Identity.** Three run-identity keys are functions of the step index alone, so n branches at one stage are indistinguishable to the approval machinery, the counting rules, and every watch and trace: `correlation_key(reason, at, about)` (`suspension.py:164-174`; `accepts` is key equality alone at `:629-632` — verified, three branches hash to `1de93d0d073fe6ff` identically), `already[call.name]` (`harness.py:1742-1743`), `person_said` keyed by stage (`harness.py:871-872`), and the flat `so-far` projection (`harness.py:1804-1805`) that the shipped `stop-runaway-refunds.yaml` counts over. `events.py:31-37` states `Scope` is *"strictly nested"*; parallel branches are not. **Price it as five edits across three modules, one of which — `correlation_key` — is an on-the-wire format change that `suspension.py:170-171` explicitly calls "deliberately not random: two transports running the same tree must park under the same key."** Fold the try dimension in as part of Phase 0.7, not as a footnote.
4. **Parking.** `Suspension` declares 19 fields and **no branch coordinate**; `to_json`/`from_json` enumerate the same 19. Either (a) refuse at check time a `tries:` stage from which an `ask-someone`, an approval-gated tool or an over-budget branch is reachable, or (b) `Suspension` grows a branch vector and the durable record becomes a list, rewriting `escalate`/`to_json`/`from_json`/`accepts` and five park sites. Do **not** adopt "refuse `tries:` where a `spends-money:` action or a `needs-approval` rule is reachable" — `examples/refund-desk/policies/approvals.yaml:24` is `applies-to: every-agent`, so that refuses `tries:` on every stage of the flagship. Scope any interim refusal to a stage that can reach an *ungated-by-key* action.
5. **Effects.** A shared `Ledger` across branches is **correct** — three attempts at a refund must not issue three refunds — but it makes the branches asymmetric: 2 of 3 get a refusal injected into their context for a reason the author did not write. So `tries:` folds over a stage whose `may-use:` reaches only `pure` actions, which makes **§3.4's `effect:` field a prerequisite of 3.1**. The live hazard is one tool over: `examples/refund-desk/tools/zendesk.yaml`'s `reply:` carries no `same-request-key:` and no `reads-only:`, and `approvals.yaml:38` gates it precisely because *"nothing goes to a customer without a person seeing it first"* — **one yes, three customer replies.**
6. **Two ports.** `tries:` changes `stageToRun`, `route` and `checkAgainst` (`loops.ts:253, 209, 226`), so it is **two harness implementations**, not one — or it is DECLARED out via the TS port's `notDoneHere` channel, in which case §6's *"seven targets already agree byte-for-byte on a bounded subset"* narrows by the same amount. Say which.

**E37 — 3.2 `knowledge:` (lines 795-818). Three edits; the first is the withdrawal of a line.**

(a) **DELETE the `connect:` comment** on line 800. `# or \`connect: <server>\` for a live index` re-admits, inside the fix, the arrangement §3 G1 spends three paragraphs condemning at lines 283-288, and it silently voids the three fields the same block declares enforceable: under `connect:`, `at-most: 5` — annotated *"top-k is a safety parameter, not a knob"* — is a number PACT writes down and a remote index ignores, and `must-cite:`/`freshest-by:` are the same. Two transports under one kind, with no discriminator and no refusal, is the shape R1/R60 refuse one kind over (*"a tool that writes two of the three, or none, is refused by `pact check` naming the file, the line, which of the three are set, and the line to type"*). Pick one. Recommended: **in-folder only**, so `at-most:`/`must-cite:`/`freshest-by:` are things PACT can hold and T2's answer survives. If `connect:` is admitted instead, all three are refused beside it, by name, in R60's shape. Either way, say out loud whether retrieval is PACT-owned or §4-delegated — if the host picks the retriever, T2's oracle is measuring the host, which is the review's own charge at :283-288.

(b) **Replace the glob.** `from: handbook/**.md` would be the first author-written pattern anywhere in the format (`grep -n "glob\|wildcard\|\*\*" spec/schema.yaml` → zero hits; the one path-typed field, `watch.writes-to`, is `type: file-name` with help *"Just a name, no folders in it"*), and §6's own commitment is that *"every result in §3 is reachable with closed vocabularies"*. Use the folder convention that already reaches files at no syntax cost: **`knowledge/<name>/`**, the way `skills/<name>/SKILL.md` + `references/` works. If a subset must be selectable, a **list of paths**, not a pattern.

(c) **Say the real cost.** "One kind, one agent field" is understated. `models/catalog.yaml` has 13 rows, every one a text-generation LLM, zero embedders; the `model` group has no `role:` field at all (`['description','family','tier','also-known-as','served-by','capabilities','reasoning','cost']`); `grep -n embedder spec/schema.yaml` returns two hits, neither usable here. If retrieval is lexical (BM25 over the folder), say so — that is air-gapped-native and needs no catalogue row, and it is the design the sketch implies. If it is embedding-based, the price is: an index/embedder binding resolved against `models/catalog.yaml`, embedder rows carrying the same provenance discipline as `context-window`, a resolver arm for D11's recommendation, and an honesty-channel line (`unmetered`) for "nobody could measure this index". Then §3.2 is a subsystem with a defensible price.

(d) **Name the reader, and say where the text lands.** No moment in `WIRED` carries a tool result or a retrieved document — the complete table is five entries (`interceptors.py:759-765`), none of them post-tool — so every rule an author can write, including the workspace's own card-number redaction, is blind to `knowledge:` text. `examples/refund-desk/interceptors/redact-card-numbers.yaml` states the consequence in its own file. Either add a moment that carries retrieved and tool text (`step.knowledge.after` / `step.tool.after`, `values` + `stop-the-run`) — one row in `WIRED` plus one emit site, the same shape 0b.1 already argues for — or **state plainly that `knowledge:` text is unfiltered**, and say where it lands relative to `_system_for`'s framing (`harness.py:2708-2712`: *"These are the rules of this work. Follow them exactly, and quote them when they decide something"*).

(e) **Soften the top-k absolutism** at line 801-803 and 808-809. Replace *"top-k is a safety parameter, not a knob"* and the bare 6%→20%→38% sequence with: *one small memory-poisoning study (GPT-4o-mini + Llama-3.1-8B, one MIMIC-III task, arXiv preprint) finds attack success rising monotonically with the number of retrieved memories on one model (6/20/38% at k=3/5/10), with injection acceptance quadrupling on that same row (ISR 26/50/100%) — the "acceptance stays high" clause is the Llama row (99/94/98%), not the GPT row; and the same paper reports a well-populated store driving ASR to **0%** (§5.3). `at-most:` is a knob whose safe value is corpus-dependent, and PACT's contribution is that it is **declared in the folder rather than set in the host**.* The design is unaffected; the absolutism is not supportable.

**E38 — 3.3 `board:` (lines 820-824). DELETE the overclaim; take one of the two exits `50-NOT-COPIED.md` §6 already wrote.**

`That is the blackboard, the market and the auction — the three AC-5.1 patterns` is wrong twice. A board with *"the writer recorded"* and explicitly *"not an invented lease design"* has **no exclusivity**, so it cannot deliver market or auction, which are exclusive-assignment patterns. And "three patterns" miscounts: `docs/30-FRD.md:167` lists eight patterns with `market/auction` as **one** row, so the board touches two rows, not three — 8 − blackboard − market/auction is exactly the six §6 names.

Replace with:

> **3.3 — `board:` — shared state between teammates.** A `state` a team may read and write between turns, with the writer recorded. That is the **blackboard** — one of the eight AC-5.1 patterns the gap register records as impossible — and Argus is the published fixture to build against (+12.7 pts at 8 workers; 86.2% BrowseComp at 64; orchestrator context under 21.5K). **Market and auction remain unreachable**: they need exclusive assignment, and `50-NOT-COPIED.md` §6 defers claim-and-lease because *"inventing a lease design nobody has tested is worse than shipping without one"*, naming its own two exits — *"either the claim-and-lease form returns with a real design or the acceptance criterion is restated at six patterns."* This review takes the second: **restate AC-5.1 at six patterns**, and file the claim-and-lease form as a separate item — a claim is a `Suspension` under a sixth `REASONS` member with a lease deadline and a release action, with Argus as the fixture, which is a real design and not a sentence.

Note for the record: satisfying a deferral's own named re-admission condition is not duplicating a refusal — the board half of 3.3 is legitimate. Only the market/auction claim is not.

**E39 — 3.4, line 839. `one-at-a-time: yes` → a closed enum.** A boolean cannot carry the isolation model the review's own §3 G3b(d) sets out — four anomalies and two mechanisms priced more than 20× apart (~8% tokens for snapshot, 1.6–2.3× for pessimistic locking) — and the review argues at line 357 that a one-bit durability declaration *"has said nothing"*, then declares a four-anomaly problem in one bit. `yes` does not say which anomaly is excluded and `no` is undefined, in a format whose stated idiom is that *"the choices are a closed list, and the author picks from it"* (`50-NOT-COPIED.md:246`). Replace with:

```yaml
  isolation: snapshot                 # none | snapshot | one-writer-at-a-time
                                      # each `help:` names the anomaly it excludes
                                      # and the measured token price (§3 G3b(d))
```

plus one sentence saying **who enforces it**: on §4's pattern this is a PACT declaration and a host obligation, and the run reports on `unenforced` when the host supplies something weaker — the shape R25/R37 already established for a ceiling nobody can measure. The alternative, if that is too much for one phase: ship the board **write-only with the writer recorded**, make no isolation claim, and say on `unenforced` that concurrent writes are not governed.

**E40 — 3.4, the digest vector (lines 842-853).** Add the prerequisite from E25: **this table is meaningless until payload file contents are hashed** (0.8). Today the "skills" row is length-sensitive and content-blind for exactly the files it is about. Also say the partition's basis out loud: it is **authored location**, not what the model reads — `_system_for` (`harness.py:2706-2720`) concatenates `instructions` + the stage's `says:` + skill bodies + the answer shape into one system string, so the same sentence moved between three of these rows changes its drift verdict. Name that consequence rather than leaving it to be discovered.

**E41 — 3.4, line 855-857. Give the walk an input.** Replace *"This makes the same walk answer 'which parked runs would this deploy break?'"* with **`pact waits --against <digest-vector>`**, taking stored digests on stdin or from a file and answering which are incompatible with the tree it was pointed at. `pact waits` is a static walk of a folder emitting declarations with no run identity (`"declared-at": "…/approvals.yaml:28:5"`, `"deadline-ms": 1800000`); parked runs live in the host's store (`Suspension.to_json()` is the blob whoever called `run()` holds). The walk stays static and the store stays the host's — no decision moves. And it is blocked on E24: member-owned waits must be marked first.

---

## K. §5 Phases 4 and 5

**E42 — Phase 4.3 (line 867-869). Drop the number.** `would have caught all 68 real hangs in the study` is not supportable: the paper root-causes 100% of the 68 to the **absence** of a bound (*"All 68 failures share the same root issue: the repeated path is not covered by a strong bound"*), and its pipeline runs controller classification and bound verification as two separate steps (§IV-B-2), with only the second producing findings. Figure 7's case is an unbounded `while True` — there is no declared exit for the enum to hold. Rewrite the proof column:

> `halt.controller` makes visible a property PACT's mandatory ceilings already hold (W7 is the catching construct, not this field). PACT's own stage transitions (`answered:`, `used-a-tool:`) would themselves classify as **model**-controlled, which is the point of making it visible. One field, and PACT is the only spec that has it.

**E43 — Phase 4.6 (line 887-892). One clause.** After the 0/48 and 25–48/48 figures add: *a **state-level assembly** result, not a model-compliance result — the paper says so in the same paragraph ("These counts are state-level assembly outcomes, not model-action outcomes") — but the mechanism it isolates, a complete-set preflight before the ladder runs, is exactly what `keep-room-for:` would add.* The proposal is unaffected.

**E44 — Phase 5 item 3 (line 900-902). Delete the premise clause.** `whose \`from:\` currently resolves nothing` is factually wrong: an unmounted bundle emits `loader/bundle-not-mounted` with the message *"the bundle '{name}' names `from: {where_from}` and nothing here mounted it, so none of its definitions are in this workspace"* plus a fix line (`bundles.rs:72-83`), deliberately a warning because *"the second kind is resolved by a host that knows its registry"* (`:60-65`). The residue is one R20-shaped sentence:

> `bundle.from` is the second `port.through:` — a name only the host can know — so it belongs in §4's (b) column, and `loader/bundle-not-mounted` is already the right diagnostic.

---

## L. §7

**E45 — §7 claim 3 (lines 936-938). Rewrite to name D3.** `grep -n -iE "\bD3\b|superset|bud\.dev|Workflow|converter" docs/90-REVIEW.md` → **zero hits**. D3's superset obligation is a written-down dependency on a topology target, not a speculative one (`docs/01-DECISIONS.md:39-48`; AD-67's rationale at `docs/25-ARCHITECTURE-DECISIONS.md:267` says *"D3's superset obligation requires it"*). Replace with:

> 3. **That the Graph should be deleted rather than built.** If converting the `bud.dev/v1` corpus — `kind: Workflow`'s 5 node kinds and 10 condition ops, `kind: Team`'s 11 strategies, `spec.handoffs` — needs a topology IR, **§6's first bullet is wrong** and Phase 3.3 is the wrong shape. The converter corpus is the fixture; Phase 1.2 files the Graph with it.

Do not restate this as fatal: Phase 1.2 already carries each moved construct with its re-admission fixture, so nothing is left without a target — it is left without a **schedule**.

---

# What survived

**This is the load-bearing part of the document.** Six adversarial lenses attacked it and could not move it. Thirty-two attacks were overturned; these are the claims that produced them.

1. **§0's central finding — that nothing in PACT constrains what the agent *says*.** Attacked as false-at-the-implementation-level and it partially is (E1: the harness honours `stop` at `turn.message.after`; the gap is a missing sentence *form*). The finding got **cheaper and sharper**, and it grew a seventh defect: `may: [stop-the-run]` at `turn.message.after` loads clean and can never fire — a live R24 instance. Six of ten personas are still blocked and the ranking is unchanged.

2. **§6's "do not build the Graph."** Attacked four ways — that three capabilities cost 21 field names not three; that Phase 1.2 deletes the trust lattice and the anti-injection architecture; that AD-48/AD-70 name a published exploit; that `pact.lock` is re-derived by 3.4. All four fail on the same fact: `available-when:` is a **closed list of five static choices** with its own comment forbidding an expression language, and `edges:`, `channels:`, `transform`, `kind: route`, `kind: map`, `on-reentry`, `graph:` have **zero hits** in the schema. §7.4's lattice is defined entirely over constructs that do not exist; it is the Graph's own threat model and belongs on the Graph's shelf. And the "three constructs instead of thirty" comparison is against the Graph's thirty, not against schema size — its biggest claimed cost (`description:` universal) is a change that **deletes** a refusal.

3. **The `board:` proposal itself** (as distinct from its market/auction overclaim, E38). Attacked twice as duplicating `50-NOT-COPIED.md` §6 — review rule 3, the fatal one. It is the opposite: the ledger entry is a **conditional deferral that names its own re-admission test** (*"inventing a lease design nobody has tested"*, AD-69's *"zero prior art"*), and §3 G2 supplies exactly the published, benchmarked prior art the deferral asked for, saying so in terms (*"Argus is the fixture to build against, not an invented lease design"*). Executing a ledger's named re-admission path is the opposite of duplicating its refusal.

4. **`knowledge:` as an air-gapped construct.** Attacked as fatal — retrieval needs an embedding model, no catalogue row exists, D17 is broken. Every fact checked out and the inference did not: the construct binds no model, and top-k over Markdown is answerable **lexically**, which needs no model, no network and no catalogue row. D8 also makes `models/catalog.yaml` locally authoritative and author-extensible, so even the embedding branch is a row an operator writes. The residue was a scoping question (E37), not a fatal flaw.

5. **`effect:` and `same-request-key:` (3.4).** Attacked as reopening Action Replay through a mis-authored `reversible` refund. Closed by the line printed immediately beneath the one attacked: `same-request-key: order-number # already exists; now required when not \`pure\``.

6. **Phase 1's document surgery.** Attacked as deleting a specification three shipped modules consume. All three citations read backwards — two cite §7.6 as prior art for a rule they had to write themselves, one cites §7.3 to say the draft was **wrong**, and the test invoked as the guard asserts *"§7.3 has to say that the schema is where the words come from."* The test is evidence for Phase 1.1.

7. **§3 G2's measured table.** Attacked on the +8.19/+1.00 row as splicing two models. Table 1 refutes it exactly: Claude-4.5-Sonnet 69.87 → 78.06 (select-K) and 69.87 → 70.87 (single-rollout) — same model, same N=16/K=4 budget, same table. The row label and its qualifier are both right.

8. **§3 G3's overthinking-cliff bullet.** Attacked as misquoting the thresholds and misdescribing budget forcing. The 2K/8K figures are the paper's own words for the overthinking threshold (the attacker's 1.0K/7.5K is a different quantity — the accuracy peak), and budget forcing force-decodes the end delimiter at the cap. Only "provably wrong" needed softening (E15).

9. **The digest-vector partition** (as a classification, distinct from the hashing bug in E25). Attacked as reinventing a partition `surface:` already carries. Deriving from `surface:` would put `tool.description` (REFUSE) and `skill.use-when` (RESUME) in the same digest part — they are both `S-ROUTE`. A drift-risk classification and a governance-surface classification answer different questions.

10. **`state.never-from:` as an honest delegation.** Attacked as the same unfalsifiable delegation §4b.6 nails for `durable-resume`. It is the inverse: `never-from:` has **both** halves — a declared field with `surface: S-EXEC`/`tier: core` and a matching ledger row — and `KNOWN_GAPS` in the reader test is **empty**, with a record of `workspace.profile` being moved out of DELEGATED the moment a real check was possible. The honesty machinery is policed.

11. **Tool descriptions are in the folder.** Attacked via MCP `DiscoverResult.instructions`. Tool definitions handed to the model are built from the authored `ToolSpec` (`harness.py:675`); no transport is an MCP client; nothing anywhere reads MCP `instructions`. This is W4, and it holds.

12. **Running AC-1.5 after Phase 2, and `pact init` under PROTOCOL.md's no-templates rule.** Attacked as backwards and as protocol-violating. §7 item 1 *is* that attack, written by the review, at the top of its own list of things it would like to be wrong about — and PROTOCOL.md's rule forbids handing the participant a pre-filled workspace, not the shipped CLI having verbs.

13. **W1's mechanism, W4, W6's substance, W2 entire.** Every attack on these landed on scope, register or citation format (E11–E13) and none on the mechanism. `harness.py:1188` rebuilds the system text every step; `_ran_out` always sets `stopped_by`; nothing else in the field lets an author declare what may not be dropped.

---

# The single highest-value thing the review still gets wrong

**It schedules the only execution door — `pact try`, Phase 2.4 — behind every safety fix whose correctness only running can establish, and files it as a DX item.**

Even after E24 and E35, `pact try` sits in Phase 2 under the heading "The ladder", justified as *"Its absence is why a senior dev cannot evaluate this project in an afternoon."* That is the least important thing it does.

Every one of §1.3's six defects was found by reading code. The two most serious findings in this entire review cycle were **not** — they required running the shipped example:

- A suspension crossing a delegation boundary is silently converted into a member *failure*, on the unmodified flagship, with `if-someone-fails: carry-on` making an approval gate vanish with no human asked. Reading `harness.py:2626` gives you a `RuntimeError`; only running it shows you the person being told *"One of the checks could not be completed"* while the reply goes out.
- The at-most-once ledger is per-agent-run, not per-request. `harness.py:467` looks correct in isolation. It is the 23-parameter signature of `run()` and the bare call at `:2610-2612` that make it wrong, and that is an execution-path fact.

Both were mis-scoped in the review precisely because it is, throughout, an **authoring-surface review with a code-reading annex**. The proofs it schedules in Phase 0 are unit tests written against a harness the review has never watched run end to end. `pact check` cannot see any of this: it said `OK` on the workspace that has no `ports/`, on the map-under-`text:` hole, on the `based-on:` name collision, on every one of §4b.3's six inert controls. The checker is not an oracle for the loop.

So the correction is not "add a Phase-2 line for D20." It is: **`pact try` and the D20 cold-execution demo belong in Phase 0, ahead of 0.1a/0.1b, as the instrument the safety phase is measured with** — and D9's *"one real end-to-end run"*, which the review never mentions at all, is the exit gate for Phase 0 rather than an unscheduled obligation. A review that opens by saying the shipped stage machine is *"smaller, sharper, more honest… better"* than the documented Graph, and then proposes seven phases without ever executing it, is making the same category of claim it correctly convicts `50-NOT-COPIED.md` §4 of making about `durable-resume`: a promise recorded in a document, with the half that would falsify it never built.
