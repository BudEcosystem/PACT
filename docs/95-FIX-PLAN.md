I have verified every load-bearing claim first-hand. Writing the converged document.

---

# THE CONVERGED DESIGN AND ITS IMPLEMENTATION ORDER

**Everything below was reproduced against `/home/bud/ditto/agent-inter-op/target/debug/pact` on scratch workspaces under `/tmp/claude-1000/-home-bud-ditto-agent-inter-op/06201250-5bf5-4160-a1c1-ef33e0f724f8/scratchpad/{v1..v7,w1}`, or read at `file:line`. Baseline census, measured just now over `/home/bud/ditto/agent-inter-op/spec/schema.yaml`: 43 groups · 262 field entries · 207 distinct names · 138 distinct core names · 126 distinct closed-choice values.**

## 0. The three decisions that reorder the whole set

**(1) D5 is first, but not as the test instrument.** The TDD pass is right and the draft's stated reason is wrong. Effect-level tests are writable today (`adapters/python/src/pact_adapters/script.py` ships a `Script` transport; `adapters/python/tests/test_hitl_kill_resume.py` already parks and resumes a real run). What `pact try` is the only possible home for is *printing the honesty channels*: `grep -rn "unenforced\|unmetered\|unwatched\|never_reached" crates/ --include=*.rs` outside tests returns two comments in `crates/pact-loader/src/approvals.rs` and **no producer and no printer**. Every channel lives only on the Python `RunResult` (`adapters/python/src/pact_adapters/harness.py:110-135`). D5's gate is the honesty printer, not the test harness.

**(2) The single strongest test in the set is one this repo already wrote and under-scoped.** `crates/pact-cli/tests/one_typo_is_one_message.rs:118` is `typing_the_fix_the_one_message_gives_leaves_a_tree_that_checks_clean`, whose comment reads *"doing exactly what it says finishes the job."* Its scope is two typos. I reproduced its violation:

```
$ ./target/debug/pact check $W
warning: 'desk' lists 'lookup', which is only offered when the agent has a written
         procedure to load — and 'desk' declares no `skills:`.
  fix: Add `skills:` to 'desk', ...
  rule: loader/never-offered

$ # typed exactly that
$ ./target/debug/pact check $W
error: 'skills' is not something an agent can have.
  rule: schema/unknown-field
```

Generalising it costs one file, it is red today, and it catches a defect *class*. It gates everything.

**(3) The set answers one of the three shapes its own P4 gate names.** `docs/93-GAPS.md:204-205` requires *"the RAG shape, the self-consistency shape and the contended-claim shape each have a workspace that loads and runs."* This set designs the RAG shape (A7). A6 (self-consistency) is undesigned and `docs/93-GAPS.md:81` ranks it **above** A7 in evidence-per-cost. B13 (contended claim) has no row at all in `94-DRAFT-FIXES.md` §D4. **Both get rows here, in §2 and §6. A gate that names three shapes may not be closed by one.**

---

# 1. THE DESIGN SET, FINAL

Seventeen items ship. Each carries the exact schema block (where it touches the schema), the authored example, and the diagnostics it adds.

---

## 1.1 B15 — the four loader tables become data *(instrument; no new author-facing vocabulary)*

**Re-scoped from the draft.** As drafted ("every field name any loader module looks up must be a field the schema declares") it does not reach its own motivating bug. The `.get("x")` reading finds 96 distinct lookups in `crates/pact-loader/src` and **zero unknown**. The all-literals reading finds `knows`, `redactions`, `schedules` — but none of the *positional* errors, because `skills` and `watches` are real schema names in the wrong position. **B15 is about (kind, field) pairs, and the fix is to make the tables computable.**

Measured, all four:

| table | file:line | wrong rows |
|---|---|---|
| `NEEDS` | `crates/pact-loader/src/available.rs:32-36` | `("this-agent-has-procedures","skills")`, `("this-agent-has-connections","resources")` — the agent group has neither field |
| iteration | `crates/pact-loader/src/available.rs:45` | `("skills","knows")` — no agent has `knows:` |
| `COLLECTIONS` | `crates/pact-loader/src/derive.rs:47-63` | `watches`, `schedules`, `redactions` — no such workspace fields |
| `CONTRIBUTABLE` | `crates/pact-loader/src/bundles.rs:27-38` | `watches` (the field is `watch`) |
| `KINDS` | `crates/pact-loader/src/unnamed.rs:47-89` | 7 rows; `skills` absent |

The workspace's 23 fields, measured: `[name, pact-version, workspace-id, description, owner, profile, allow-egress, agents, tools, resources, skills, policies, redaction, questions, evals, learning, ports, loops, context-policies, bundles, interceptors, watch, models]` — `watch` and `redaction` singular, no `schedules`.

**The schema change is one new attribute, `satisfied-by:`, on the `available-when` choice list.** Everything else is computed:

```yaml
      available-when:
        # R6-shaped: which OTHER field satisfies a condition is the half the
        # schema could not state, so `available.rs` kept it in a hand-written
        # table of three rows — and two of them named a field the agent group
        # does not have. MEASURED: a tool with `this-agent-has-procedures`
        # warned "'desk' declares no `skills:`", and typing the fix it offered
        # gave `error: 'skills' is not something an agent can have`. A warning
        # whose fix is an error is worse than no warning.
        #
        # `satisfied-by:` says it as data, and it is checked in BOTH directions:
        # every name here must be a field the `agent` group actually has.
        type: one-of
        choices: [always, this-agent-has-helpers, this-agent-has-procedures, this-agent-has-connections, a-person-can-be-asked]
        satisfied-by:
          this-agent-has-helpers: agent.team
          this-agent-has-procedures: agent.uses
          this-agent-has-connections: agent.uses
        surface: S-ROUTE
        tier: expert
        help: >
          when this is offered to the model at all. Leave it out and it is
          always offered.
```

`derive.rs::COLLECTIONS` becomes *every workspace field typed `map of group:*`* — computed, not written. `bundles.rs::CONTRIBUTABLE` becomes the `bundle.brings` choices, which are themselves generated from the workspace collection names, so the two spellings cannot diverge again. `unnamed.rs::KINDS` becomes *every workspace collection with an inbound `names:` edge* — the schema already carries all 30 `names:` bindings, and this is what adds the missing `skills` row for free.

**Diagnostics added:**
- `loader/never-offered` becomes fixable (the fix line now names `uses:`, which an agent has).
- `loader/nothing-points-at-it` starts covering `skills` — measured absent today.
- `loader/bundle-brings-more-than-it-said` starts covering `watch:`, `agents:`, `ports:`, `evals:`, `learning:`, `context-policies:`, `models:` — **15 of 23 collections it is blind to today.** `crates/pact-loader/src/bundles.rs:88-91` does `if !CONTRIBUTABLE.contains(&kind) { continue }`, so `brings:` governs the spelling no real tree produces and is blind to the one it does. That `continue` becomes a refusal. **`spec/schema.yaml:3277-3279` states `bundles.rs` is the ONLY constraint; that sentence is false in one direction today and must be re-verified by test, not by comment.**

---

## 1.2 B10 — split into the two things it actually is *(redesigned; 3 of 5 lenses)*

B10 as drafted ("`loader/reads-nothing`, fired wherever a written line binds nothing") requires enumerating "wherever", which is the vigilance `adapters/python/tests/test_every_field_has_a_reader.py` was invented to replace. And it cannot distinguish an inert control from an honest §4 delegation — which is the shape the whole `knowledge:` design rests on. **It becomes two mechanisms, neither of them a broad heuristic warning.**

### (a) A port-parity corpus — the instrument

Reproduced in one workspace printing `OK — loaded cleanly (30 settings)`: `judged:` with no `graded-by:`; `metrics: - uri: faithfulness` with no colon (which `spec/schema.yaml:1965-1972` promises *"is refused rather than guessed at"*); `x-run-arbitrary: yes`. All three ARE decided — in Python, at run time (`providers.py:447-462`, `:653-663`), in a process the author never starts.

No schema change. `tests/corpus/decidable-statically/` grows; `pact check` must refuse every workspace the Python runtime refuses from the document with no model.

### (b) `loader/power-nothing-can-use` — the half the draft missed

Reproduced: `may: [hide-values, stop-the-run]` at `turn.message.after` with one hiding rule → **`OK — loaded cleanly (20 settings)`**. `stop-the-run` is declared, `harness.py:2848-2851` honours it there, and no sentence in the closed vocabulary produces one there. That is R24's defect surviving *inside the list R24 was applied to*, and `docs/50-NOT-COPIED.md:253` (G5) asserts the invariant it breaks: *"Every power in that list has a sentence that reaches it and an address that carries it out."*

**The check must run over (power × address), not power.** No schema change — the `forms:` block at `spec/schema.yaml:2823` already carries `needs:` and `at:` per sentence, so this is a fold over data the schema already has, in `crates/pact-schema/src/sentences.rs`.

**Diagnostic added:**
```
error: this rule may `stop-the-run`, and no sentence you can write at
       `turn.message.after` stops anything — so that power sits there and
       nothing can use it.
  fix: Take `stop-the-run` off the `may:` line, or add a moment it works at:
       step.tool.before.
  rule: loader/power-nothing-can-use
```

**This must land BEFORE F7, or F7 closes one case and leaves R24's class open.**

---

## 1.3 B8 — gate on the FIELD, not the type *(redesigned; the draft's fix breaks the flagship)*

The draft's fix — *"a mapping under a `type: text` field raises `schema/wrong-type`"* — **would break the `instructions/` folder feature**, which is D2's Expansion Rule and the flagship's shipped shape. `agent.instructions`'s own help says so: *"That line can go in `agent.yaml`, or the same words can go in `agents/<name>/instructions.md` beside it — the two mean exactly the same thing."*

And the real defect is far wider than a `loop:` typo. `crates/pact-schema/src/lib.rs:1330` is `Ty::Text if node.as_map().is_some_and(is_all_prose) => {}` — gated on the **type**. Measured, mine:

| written | result |
|---|---|
| `loop: carefull` | `error: 'loop' names 'carefull', and there is no such entry in \`loops:\`` |
| `loop: {banana: purple}` | **OK — loaded cleanly (12 settings)** |
| `model: {pick: gpt-9, alt: or gpt-8}` | **OK — loaded cleanly (13 settings)** |
| `policy: {a: b}` | **OK — loaded cleanly (12 settings)** |
| `context-policy: {a: b}` | **OK — loaded cleanly (12 settings)** |
| `loop: {banana: 512}` | `error: 'loop' should be some text, but it is a set of settings` |
| `loop: [a, b]` | `error: 'loop' should be some text, but it is a list` |

**22 schema fields carry both `type: text` and `names:`** (measured): `agent.policy`, `agent.evals`, `agent.model`, `agent.model-for-checking`, `agent.loop`, `agent.context-policy`, `limits.asks`, `resource.asks-to-connect`, `tool.connect`, `question-rule.question`, `evals.graded-by`, `learning-model.model`, `port.answers`, `loop.based-on`, `loop.starts-at`, `stage.asks`, `outcome.used-a-tool`, `outcome.answered`, `outcome.too-many-times`, `context-policy.summarised-by`, `context-policy.asks`, `teamwork.asks`. **Every one accepts an all-prose map and skips `check_name` entirely.** One missing predicate disables a check that IS implemented, on 22 fields.

**Schema change: one new field attribute, set on exactly two fields.**

```yaml
      instructions:
        type: text
        may-be-a-folder: yes
        required: yes
        surface: S-GEN
        tier: core
        help: >
          what it should actually do, in plain words. That line can go in
          `agent.yaml`, or the same words can go in
          `agents/<name>/instructions.md` beside it — the two mean exactly the
          same thing, so write it in whichever file you already have open.
          Once it runs past a paragraph, the separate file is the usual place.
```

```yaml
      content:
        # `may-be-a-folder:` is the half `Ty::Text` could not state. The arm at
        # `lib.rs:1330` forgave a map of prose under EVERY text field, which was
        # right for these two and wrong for the twenty-two that resolve a name:
        # MEASURED, `loop: carefull` was refused with six alternatives offered
        # while `loop: {banana: purple}` printed "OK — loaded cleanly" and
        # skipped name resolution altogether. One missing predicate turned off a
        # check that was already written. No field may carry both this and
        # `names:`, and a test says so.
        type: text
        may-be-a-folder: yes
        surface: S-GEN
        tier: core
        help: >
          the procedure itself. This is the body of `SKILL.md` — you write it
          as prose under the settings above, not as a `content:` line.
```

`lib.rs:1330` becomes `Ty::Text if field.may_be_a_folder && node.as_map().is_some_and(is_all_prose) => {}`.

**Diagnostics added:** none new — it *reuses* `schema/wrong-type`'s existing message ("'loop' should be some text, but it is a set of settings") on 22 more fields, and restores `schema/no-such-name` behind it.

**This is a precondition for D1**, because `documents:` would otherwise be a `type: text` field a map loads clean under.

---

## 1.4 B1/B2/B4 — one `park()` helper *(ship as drafted; confirmed site by site)*

Worse than "four of five missing one field" — measured, **no site sets all three durable blocks**:

| site | `spent_keys` | `granted` | `used` |
|---|---|---|---|
| `harness.py:1050` | ✅ | ✅ | ✗ |
| `harness.py:1135` | ✅ | ✅ | ✗ |
| `harness.py:1557` | ✅ | ✅ | ✗ |
| `harness.py:1682` | ✅ | ✅ | ✗ |
| `harness.py:2058` | ✅ | ✗ | ✅ |
| `suspension.py:647` `escalate()` | **✗ (absent)** | ✅ | ✅ |

`Suspension` declares all three: `used:571`, `granted:586`, `spent_keys:597`.

**Runtime only.** Zero Rust, zero TypeScript (interceptors and limits are on the TS `REPORTED` list, `crates/pact-cli/tests/the_subset_the_second_port_runs.rs:80-90`), zero examples, no digest moves.

`park()` takes all three as **required keyword arguments** — the shape `_ran_out` already uses for `once:` (`harness.py:2004-2008`, with a comment saying why). Copy it.

---

## 1.5 B3 — route the closing answer through the chain *(ship, with one addition)*

Confirmed at `harness.py:2102-2116`: the `Action.ANSWER` path does `text, _ = await transport.model_call(...)`, `result.output = text`, `bus.emit("turn.message.completed", ...)` — **no `chain.run`**. And `_finish`'s own docstring at `:2841-2846` states the guarantee it breaks, verbatim:

> *"Routed through `turn.message.after` like every other reply, so a redaction rule cannot be escaped by finishing from a stage rather than by running out of steps."*

Running out of steps is the exact escape.

**The addition the draft owes:** the chain may **rewrite `content`** and may **not overwrite `halted`**. `limits.RAN_OUT = {step-limit, tool-call-limit, time-limit, cost-limit, token-limit}` (`limits.py:350-355`) is the set a caller asks "did it run out?" with; a stop rule firing there must not make the ceiling unreportable. `_ran_out` gains a keyword-only `chain` across four callers (`harness.py:1014, 1205, 1928, 1993`).

**This must land BEFORE F7**, or a "never give medical advice" rule is escapable by exhausting the step budget.

---

## 1.6 F7 — the stopping sentence *(ships; F6 does not — see §2)*

The draft's wiring claim is **verified true and is the strongest thing in it**. `harness.py:2848-2853` and `:1262-1267` both honour `Decision.stop`; and the checker already refuses a rule bound where nothing can carry it — I reproduced `error: nothing in a run ever reaches 'step.tool.completed'`. The gap really is the sentence list.

**Four changes from the draft:**

1. **Take a list.** `mentions one of "diagnos", "prescri"` is one rule, not three files. Matches `must-not-contain:`, which is `type: list of text`.
2. **One matcher, shared.** `evals._breaks` (`adapters/python/src/pact_adapters/evals.py:650-654`) is `str(v).strip().lower() in text` — case-insensitive plain substring. F7 calls the same function. Different acts (grade a recorded case vs stop a live run) so both exist; the same words for the same act, which is the `*the-hiding-sentences` merge precedent stated at `spec/schema.yaml:2779-2800`.
3. **The help says in one sentence that this is a plain word test and not a meaning test.** The draft's own example, `"diagnos"`, is a regex author's trick.
4. **Say out loud that `always-may:` already excludes it from `redaction.yaml` for free.** `redaction.hide` carries `always-may: [hide-values]` (measured), implemented at `from_doc.rs:194` and enforced at `lib.rs:734/930`, so any form needing `stop-the-run` is filtered out with no work. This pre-empts a reviewer's first objection.

**Schema block** — one entry appended to the `one-of:` list inside `forms: &the-hiding-sentences` (`spec/schema.yaml:2823`), matching its neighbours exactly:

```yaml
            # A1. The first sentence in this list whose CONDITION reads the
            # answer. Both stopping sentences above it count tool calls and are
            # pinned to `step.tool.before`, so `may: [stop-the-run]` at
            # `turn.message.after` loaded clean and could never fire — MEASURED,
            # "OK — loaded cleanly (20 settings)" — which is R24's defect
            # surviving inside the list R24 was applied to, against §2 G5's own
            # invariant that every power here has a sentence that reaches it.
            #
            # A PLAIN WORD TEST, deliberately. It matches the words you write,
            # folded to lower case, anywhere in the answer — the same match
            # `must-not-contain:` makes on a graded case, from the same
            # function, so an author who has written one has written the other.
            # It does not know what an answer MEANS. For that, write a `judged:`
            # rule in `evals/` with a `graded-by:` model to read it.
            - say: 'if the answer mentions <these words>, stop and say "<why>"'
              needs: stop-the-run
              at:
                - step.message.after
                - turn.message.after
```

**Authored example** — the clinic ops lead:

```yaml
# interceptors/no-medical-advice.yaml
description: This desk books appointments; it does not advise.
when: turn.message.after
applies-to: every-agent
may: [stop-the-run]
rules:
  - if the answer mentions "diagnosis", "prescription", "dosage", stop and say "A nurse will call you back about anything clinical."
```

**Diagnostics added:** none new. It *removes* one false state (`loader/power-nothing-can-use` at `turn.message.after` now has a sentence), and inherits `schema/not-a-rule`'s existing fix list, which prints every form including this one — the best discovery affordance in the format.

`result.output = decision.stop` means the author's `"<why>"` **becomes the reply the customer reads.** The help must say that.

---

## 1.7 `step.tool.completed` into the interceptor `reaches:` list *(not in the draft; it is A1's root cause)*

`interceptor.when`'s `reaches:` is five moments — `step.message.before`, `step.message.after`, `turn.message.after`, `step.tool.before`, `step.delegate.before` — and **not one sees a result.** Reproduced, both directions:

```
interceptor  when: step.tool.completed  → error: nothing in a run ever reaches
                                          'step.tool.completed', so 'when' would
                                          sit there and never fire.
watch        when: step.tool.completed  → OK — loaded cleanly (15 settings)
```

The run *does* reach it. The chain simply is not offered it.

Consequences, all three real: a card number returned **by** a tool is never redacted, so `redaction.yaml`'s promise *"what must never leave this workspace"* is one-directional; Tom's persona ("stop at the first failed step") cannot be written; and any retrieved text has no address a rule can reach — which is D1's own unresolved trust question, with no address to bind to.

```yaml
      when:
        type: list of event-address
        parts: { ... unchanged ... }
        reaches:
          - step.message.before
          - step.message.after
          - turn.message.after
          - step.tool.before
          # What came BACK. Every other moment here is "words are about to
          # leave"; nothing saw a result, so redaction was one-directional — a
          # card number the agent typed was hidden and the same card number a
          # tool returned was not. A watch already binds here, which is how we
          # know the run reaches it: the chain was simply never handed it.
          - step.tool.completed
        required: yes
        surface: S-CTRL
        tier: core
        help: ... unchanged ...
```

**And fix the wording.** *"nothing in a run ever reaches X"* is literally false when a watch binds there. It becomes *"no rule is handed the run at X"*.

---

## 1.8 B11 — half one only *(4 lenses unanimous; `people:` deferred)*

Reproduced, mine: `asked-of: [desk]` where `desk` is the agent the rule gates → `OK — loaded cleanly (51 settings)`, and `pact waits` prints:

```json
{ "reason": "needs-approval", "agent": "desk", "question": "ask",
  "asked-of": ["desk"], "escalates-to": ["desk"], "wakes": true }
```

A live gate where the agent approves itself, and escalates to itself. **Both fields need the check.**

**No schema change and no new collection.** `asked-of:` stays `list of text` with no `names:`, which honours R36 precisely *because* "may not name an agent" is a **negative** constraint needing no register of people. One arm in `crates/pact-loader/src/report.rs`, beside `loader/nobody-can-answer`.

**Diagnostic added:**
```
error: 'is-this-ok' is asked of 'desk', and 'desk' is one of this workspace's
       own agents — so the thing being checked is what does the checking.
  fix: Name the people who decide instead — an audience like `support-leads`.
       `asked-of:` is who a person is, not which agent runs.
  rule: loader/approves-its-own-work
```

---

## 1.9 B9 — one mechanism, computed, host-relative exempt *(redesigned)*

Both doors reproduced, mine, under `allow-egress: []`:

```
tool.url: https://vendor.example.com/upload + method: post + an upload action
  → OK — loaded cleanly (22 settings)        ← the draft does not address this one
resource.endpoint: https://vendor.example.com/mcp + connect: + an upload action
  → OK — loaded cleanly (26 settings)
```

The `url` door is the one an attacker writes: **it needs no resource file at all.**

The draft names two incompatible mechanisms ("joins the egress role table" AND "a sibling `allow-connect:` hostname list"). Both lose: `crates/pact-cli/src/egress.rs:47-50` refuses to invent a seventh role *in the module*, and `docs/50-NOT-COPIED.md:489` (R61) refuses *"two settings for what must never leave a workspace"* — so a sibling field re-proposes a refusal. And `resource.endpoint`'s own help says it is *"a name your platform team publishes… it is their list, not a file in here"*, so a hostname allow-list is R20's unresolvable name.

**The answer is one new closed-choice value on the field that already promises this, plus one new field attribute so the address set is computed.** `allow-egress:`'s own help already says *"which parts of this system are allowed to talk to something outside this box. Empty means nothing is."* The six existing choices are model roles because models were the only reachers ever checked. The tools are the seventh part.

```yaml
      allow-egress:
        # B9. The six choices were all MODEL roles (R30's job), while the help
        # promised the whole boundary. MEASURED under `allow-egress: []`: a tool
        # with `url: https://vendor.example.com/upload`, `method: post` and an
        # upload action printed "OK — loaded cleanly (22 settings)" — no
        # resource file needed, which is why it is the door an attacker writes.
        #
        # `tools` is the seventh PART, not a seventh model role, and it is one
        # setting rather than two: a sibling hostname list is R61 (two settings
        # for what must never leave) and R20 (a name only the host can resolve)
        # at the same time. Which fields carry an outbound address is data —
        # `reaches-outside:` — so the sixth one joins by existing.
        #
        # An address the runtime resolves is not something leaving the box:
        # `host/payments-mcp` in the worked example has no scheme, so it stays
        # clean under `allow-egress: []` and the flagship does not move.
        type: list of one-of
        choices: [llm, stt, tts, embedder, judge, reflector, tools]
        surface: S-EXEC
        tier: core
        help: >
          which parts of this system are allowed to talk to something outside
          this box. Empty means nothing is. `tools` covers every address a tool
          or a server you connect to reaches — an address your runtime resolves,
          written without `https://`, is not outside this box. Adding a role
          here always needs a person to approve it.
```

And on each outbound address, one attribute:

```yaml
      url:
        type: text
        reaches-outside: yes
        needs-also: [method]
        surface: S-CAP
        tier: core
        help: ... unchanged ...
```

(same on `resource.endpoint` and `served-by.endpoint`).

**Diagnostic added:**
```
error: nothing in this workspace may talk to something outside this box, and
       'vendor' reaches `https://vendor.example.com/upload`.
  fix: Add `tools` to `allow-egress:` in workspace.yaml — that needs somebody to
       approve it — or use an address your runtime resolves, like
       `host/vendor-upload`.
  rule: loader/reaches-outside-the-box
```

**Regression guard owed:** the set of outbound-address fields is derived from `reaches-outside:`, not hand-written. Otherwise this is B15 in a new file.

---

## 1.10 B12 — infer `spends-money`, drop half the draft, defer the flag

Reproduced, mine: `takes: {amount: money}`, `inspects: [amount]`, **no** `spends-money:` → `OK — loaded cleanly (51 settings)`, zero diagnostics. Adding the single word turns on three mechanisms at once.

**Drop from the draft: *"`guarded_by` reads `more-than:`"*.** `crates/pact-loader/src/money.rs:327-356` inserts `when.get("tool")` and never looks at the figure — and there is **no principled ceiling to compare against**; picking one would be an unauthored policy. Reproduced: `more-than: 100000000 USD` marks the action guarded with zero diagnostics. The decidable replacement: warn when the only rule guarding a money-moving action carries a `more-than:` and the agent declares no `limits:` money cap to read it against.

**Defer `--deny-warnings` to P2.** Three measurements decide it. (i) Warning census, run just now — `pact check` on `examples/refund-desk` and all eight `examples/patterns/*` gives **nine `OK` lines, zero warnings**, so the flag changes nothing today. (ii) There are **14 warning rule names** in the tree, every one a heuristic cross-document judgement; the property that makes them *safe to add* is that a false positive costs a line of noise, not a broken build, and the flag removes exactly that. (iii) `docs/93-GAPS.md:227-228` names semantic reachability warnings as one of the eight things that must survive. A flag that freezes the warning surface may not land in the same phase as a redesign of it.

**Schema unchanged.** One arm in `money.rs`.

**Diagnostic added:**
```
warning: `issue-refund` takes `amount`, which is an amount of money, and does
         not say `spends-money:`. So none of the three things that guard money
         is on: no same-request key, no approval rule, no cross-agent check.
  fix: Add `spends-money: yes` next to `takes:` — or `spends-money: no` if this
       action only reads.
  rule: loader/money-that-moves-with-nobody-asked
```

---

## 1.11 A12 — the three unreadable shapes, and the wire form *(ship; the type decision is the real content)*

`adapters/python/src/pact_adapters/questions.py:185-232` branches on `yes-or-no`, `text`, `money`, `number`, `whole-number`, `one-of` and falls to `raise Rejected` for `images`, `audio`, `file` — while `_SPELLINGS` accepts all three. **`examples/refund-desk/agents/refund-desk/agent.yaml:21` declares `photos: list of images`, so the flagship cannot read its own declared input.**

Two hand-maintained lists in one class, held to each other by nothing.

**But there is no path type in the format.** `watch.writes-to` is `type: file-name`, help *"Just a name, no folders in it"*, and `grep -n "glob\|wildcard\|\*\*" spec/schema.yaml` returns nothing. Adding branches without deciding the wire form is how B19's currency divergence repeats on D16's headline modalities. **One new type, two consumers:**

```yaml
# In the type vocabulary, beside `file-name`:
#
#   workspace-path — a file inside this workspace, written relative to its root,
#   like `evals/attachments/receipt.png`. No leading `/`, no `..`, no `~`: a
#   path that climbs out is refused and told what to type instead, the same rule
#   `file-name` already makes one level down. It is what `images`, `audio` and
#   `file` answers are read as, in both ports, so a picture means the same thing
#   on either side of the wire — which is what B19 (currency parsed four ways in
#   two ports) is the argument for deciding once.
```

**Runtime + type decision. Zero schema field changes.** The `shapes:` anchor is unchanged.

**Cannot be tested in-tree:** that a model actually *sees* the image. Lands on `unmetered`, naming the transport.

---

## 1.12 A2 — `from-these-passages:` and `RunResult.retrieved` *(redesigned; one field is not enough)*

Confirmed verbatim, mine: `adapters/python/src/pact_adapters/providers.py:630` declares `retrieval_context`, `:694` forwards it into `LLMTestCase`, and the sole caller `adapters/python/src/pact_adapters/evals.py:595-601` passes five arguments and never it (`grep -c retrieval_context evals.py` → **0**).

**But one field wired to one parameter makes three of the four canonical RAG metrics tautological.** `research/notes/deepeval-surface.md:190-193`: `contextual_precision`, `contextual_recall` and `contextual_relevancy` never read `actual_output`. If the author hand-writes the passages, those three grade the author's own constant against the author's own `expect:` — identical whether the runtime retrieved the right passage, the wrong one, or nothing.

**So it is two things: an authored gold context (a field) and an observed one (a `RunResult` field).**

```yaml
      from-these-passages:
        # A2. `providers.evaluate_metric` has taken a `retrieval_context`
        # argument since it was written and its one caller has never passed one,
        # so `deepeval:faithfulness` was accepted by name and could never return
        # a score. This is the reader-table defect running the other way — a
        # parameter with no author — and the guard for it is the mirror of
        # `test_every_field_has_a_reader.py`.
        #
        # These are the passages you WROTE DOWN, so a grader can check the answer
        # against the right ones whether or not this machine has an index. What
        # the run actually retrieved is a different fact and is reported by the
        # run, not typed here: three of the four retrieval metrics never look at
        # the answer at all, so grading them against a constant you typed scores
        # your own typing.
        #
        # Named for what the author is writing, not for what DeepEval calls its
        # argument. The adapter keeps `retrieval_context`; nothing else in this
        # schema matches its adapter's identifiers, and this group's neighbours
        # are `when:`, `expect:` and `because:`.
        type: list of text
        surface: S-GOV
        tier: expert
        help: >
          the passages the answer was supposed to come from, one per line —
          what a grader reads when it asks whether the answer is actually
          supported. Write them out; a name pointing at a file is not enough
          for a grader that has to read the words.
```

**Authored example** — one case in `evals/cases/`:

```yaml
when: A customer asks how many days of carry-over leave they get.
from-these-passages:
  - "Unused annual leave: up to five days may be carried into the next year."
  - "Carry-over must be used by 31 March."
expect: Up to five days, and they must be used by 31 March.
because: Both facts are in the handbook and both are needed to answer safely.
```

**Type it `list of text` as a plain list so it does not depend on A4.**

---

## 1.13 A5 → `same-request-key-across:` *(renamed; `this-run` enforced only)*

Reproduced: omitting `same-request-key` under `spends-money: yes` is already `schema/missing-companion`. So the concept has a name, and `at-most-once-across:` would make **three** names for one act — the field, the new field, and `Suspension.spent_keys`. Every shipped ceiling is `<thing>-at-most`; `at-most` already carries two meanings (`stage.at-most`, `drift.at-most`).

And "only the scope word changes" is false. `adapters/python/src/pact_adapters/at_most_once.py:167-204`: `spent` is a per-process dict whose docstring says *"Mutable and per-run on purpose"*; `harness.py:467` builds one `Ledger` per `run()`; `grep -n "Ledger" delegation.py` returns nothing, so a delegated member gets its own.

```yaml
      same-request-key-across:
        # A5. A scope on the line above it, not a second setting: `at-most-once`
        # would have been a third name for one act, beside `same-request-key:`
        # and `Suspension.spent_keys`, and every ceiling in this format is
        # already spelled `<thing>-at-most`.
        #
        # Only `this-run` is enforced by the reference harness: `Ledger.spent` is
        # a dict built fresh in `run()` and restored from the parked suspension,
        # so it survives a park and nothing wider. The other two are §4 —
        # declared here, kept by the store the host supplies — and a run that
        # cannot keep the scope you wrote says so on `unenforced`, naming this
        # file and this line. `durability:` is where you say the store exists.
        type: one-of
        choices: [this-run, the-team, the-workspace]
        needs-also: [same-request-key]
        needed-when: { durability: durable-execution }
        surface: S-EXEC
        tier: expert
        help: >
          how far "the same call" reaches. `this-run` is the default and stops
          one run doing the same thing twice, including after it parks for an
          approval. `the-team` and `the-workspace` need a runtime that keeps a
          record outside this run — say so with `durability:` — and a run that
          cannot keep it tells you rather than quietly narrowing it.
```

The refusal sentence at `at_most_once.py:242` is hardcoded to say *"in this run"*. It must be built from the declared scope, and when the scope is wider it must say the call was made by **another run** — or the second customer's model is told they are booked.

---

## 1.14 A8 → `durability:` *(A8 as drafted is a fatal re-proposal; this is 93-GAPS' own spelling)*

**`requires-of-the-runtime: {durable-resume: yes}` was deleted in writing.** `docs/91-REVIEW-CRITIQUE.md:189` (E30):

> **DELETE the field. Keep the test.** … is **two settings for one decision**, which R59 (`50-NOT-COPIED.md:487`) already refuses in this repository with a measured reason… **Duplicating a refusal made with a good reason is a fatal flaw in the item, not a hedge to be softened.**

`docs/93-GAPS.md:5` names `91-REVIEW-CRITIQUE.md` as one of its own sources and `93-GAPS.md:92` **already carries the corrected spelling**. The draft regressed from the register it exists to answer.

**And the name is taken.** `durable_resume` is a lattice key on **eleven** transports with a three-value vocabulary (`native | degraded | unsupported`), owned by the adapter, meaning *"what this transport can do"* — `mock.py:51`, `vercel-transport.ts:85`, `pydantic_ai_transport.py:147`, `langgraph_transport.py:158`, `autogen_transport.py:228`, `ollama_transport.py:168`, `anthropic_transport.py:154`, `langchain_transport.py:171`, `openai_agents_transport.py:181`, `a2a_transport.py:91`, `adapters/out-of-tree/echo_adapter/transport.py:50`. One spelling would mean both "what this workspace needs" and "what this transport does" — **while the comparison between them is the only interesting thing about the field.**

Also: `pact waits examples/refund-desk` returns **13 waits with deadlines to 4 hours** — PACT already *computes* the fact. A hand-written assertion is `same-setting-twice`, the reason `park` was refused. And it is the wrong polarity: `allow-egress: []` can be **contradicted**; `durable-resume: yes` can only be confirmed.

```yaml
      durability:
        # A8. The §4 row that already promises this field (docs/50-NOT-COPIED.md
        # :404 — "Durability is declared and the host supplies it") finally has
        # one. NOT `requires-of-the-runtime: {durable-resume: yes}`: that is two
        # settings for one decision (R59), it was deleted in writing at
        # 91-REVIEW-CRITIQUE.md:189, and `durable_resume` is already a lattice
        # key on eleven transports meaning what a TRANSPORT can do. One spelling
        # for two facts would have made the only interesting comparison
        # unwritable — and `conformance.py` already runs exactly that comparison
        # for every other lattice key.
        #
        # Contradictable, which is what makes it worth writing: `pact waits`
        # already finds every place a tree parks (13 of them in the worked
        # example, out to four hours), so `durability: none` on a tree that parks
        # is REFUSED rather than believed. A closed list rather than a map: a
        # field nothing knows about has no `surface:` (R41), and declaring a
        # container before there is a second thing to put in it is cost with no
        # benefit.
        type: one-of
        choices: [none, checkpoint, durable-execution]
        surface: S-GOV
        tier: expert
        help: >
          what the system running this promises about a run that is interrupted.
          `none` means a killed run is lost. `checkpoint` means it can be picked
          up from the last thing it wrote down. `durable-execution` means it
          survives the process dying without anybody noticing. Leave it out and
          PACT reads what your tree needs off the places it parks — write it when
          you want a runtime that cannot promise it to refuse the tree loudly.
```

**Diagnostics added:**
```
error: this workspace parks 13 times waiting for a person or a timer, and
       `durability: none` says a run that stops is lost. Every one of those
       waits would be.
  fix: Write `durability: checkpoint` — or take the parks out.
  rule: loader/parks-with-nothing-to-resume-it
```
plus `pact waits` gains `requires: [durable-resume]` and `longest-wait: 4h`, **derived** from the parks it already finds, and a run reports `durability:` against `transport.lattice()["durable_resume"]` on `unenforced` when the two disagree.

**Sequence A8 BEFORE A5.** A5's wider scopes are only honest once there is a place to declare that the runtime keeps the record.

---

## 1.15 A3 — three changes, not two fields *(redesigned)*

Two blockers, both measured.

**(a) `needs-also:` fires on presence.** `spec/schema.yaml` gives `when-this.arg` `needs-also: ['more-than']` (measured), and the schema header says *"`needs-also:` fires on presence."* So `{tool: t/go, arg: reason, is: fraud}` is refused: `error: 'arg' is set, but 'more-than' is not`. **A3 cannot be written by an author as drafted.** `crates/pact-loader/src/reach.rs:27-32` says in its own words that *"exactly one of these three is a statement about a set … and a field can say neither of those things about its siblings."*

**(b) There is no shape check today.** `more-than: 200 USD` against a `text`-typed argument loads clean. And a lead score gated by currency: `{tool: crm/write, arg: score, more-than: 80}` → *"'more-than' should be an amount of money … fix: Write it like `0.05 USD`"*; following that fix gives `OK` and `pact waits` prints a live 30-minute human gate comparing a score to dollars. **This is a live defect today, independent of A3, and A3 would double it.**

**One new field attribute, two new fields, one shape rule.**

```yaml
    when-this:
      fields:
        tool: ...unchanged...
        arg:
          # `needs-also:` fires on presence and can only name ONE field, so it
          # could not say "and exactly one way of comparing it". `needs-one-of:`
          # is that, and it is an attribute rather than a module because the
          # next field that needs it is already visible (`reach.rs`'s
          # exactly-one-of-three transport rule is the same shape by hand).
          type: text
          needs-one-of: [more-than, is, is-one-of]
          surface: S-EXEC
          tier: core
          help: >
            which of that action's arguments to look at — one of the names under
            its `inspects:`. Leave this out and the rule applies to every call.
        more-than:
          # `type: money` was right when money was the only thing a gate could
          # compare. It now reads the argument's own declared shape from
          # `takes:`, because MEASURED, a lead score gated with `more-than: 80`
          # was told to "Write it like `0.05 USD`" — and doing that printed
          # "OK", then `pact waits` showed a live thirty-minute human gate
          # comparing a score to dollars.
          type: like-the-argument
          needs-also: [arg]
          surface: S-EXEC
          tier: core
          help: >
            the figure above which a person is asked — `200 USD` for an amount
            of money, `80` for a score. Written the way that argument is
            declared, and written with `arg:`, never on its own.
        is:
          type: like-the-argument
          needs-also: [arg]
          surface: S-EXEC
          tier: core
          help: >
            the one value that makes this rule apply — for example
            `is: enterprise` on a customer tier. For several values write
            `is-one-of:` instead.
        is-one-of:
          # A3. Two personas ended the cold-authoring trial with a gate that was
          # not a gate, because a tier, a region, a status or a store boundary
          # could not be compared at all and the only workaround handed the model
          # itself the decision about whether a person is asked.
          type: list of like-the-argument
          needs-also: [arg]
          surface: S-EXEC
          tier: core
          help: >
            the values that make this rule apply, one per line. Where the
            argument is declared as `one of a, b, c`, every choice you leave out
            is a call nobody is asked about, and `pact check` names them.
```

**Diagnostics added:**
```
error: 'arg' says which value to look at, and nothing says what to compare it
       to.
  fix: Add one of `more-than:`, `is:` or `is-one-of:` next to it.
  rule: schema/missing-one-of

error: this rule compares 'score' to an amount of money, and `crm/write`
       declares `score` as a number.
  fix: Write it as a number: `more-than: 80`.
  rule: loader/compared-in-the-wrong-shape

warning: `crm/write` declares `tier` as one of enterprise, mid-market,
         self-serve, and this rule names only enterprise. A call whose tier is
         mid-market or self-serve is not gated by anything.
  fix: Add them to `is-one-of:`, or write a second rule for them.
  rule: loader/a-value-this-rule-never-sees
```

**The four Python readers must land in the same commit** or the gate becomes unconditional: `adapters/python/src/pact_adapters/questions.py:1114-1119` `_atom_holds` and `:1160-1167` `_atom_stops` both short-circuit `if "more-than" not in atom: return True`; plus `:993` and `:1005`.

---

## 1.16 D1 → `knowledge:`, reduced core *(5 of 5 lenses returned redesign; this is the redesign)*

The construct is right. Four independent blockers killed the draft, each reproduced. Here is what survives.

**What the draft got right, measured:** the folder form is free — `knowledge/hr.yaml` was expanded by the generic directory walker and reached schema validation (`error: 'knowledge' is not something a workspace can have`), so **only the schema declaration is missing**; `at-least: 1` on `passages-at-most:` is free; `connect:` name resolution is free.

**What is cut and why is in §2.** Here is the shipping design.

### `workspace.knowledge`

```yaml
      knowledge:
        # A7. The most common enterprise shape could not be written at all.
        #
        # A separate kind and not a `skill`, and the plumbing argument for that
        # is FALSE — `skill` already carries `description`, `available-when:`,
        # `use-when:`, `costs-about:` and a digested `references/` folder, and is
        # already named by `uses:`. The argument that wins is the one about
        # reviewing: somebody who has read a skill has read every word the model
        # will see, and `passages-at-most: 5` means nobody knows at check time
        # which five. A skill is DETERMINATE and this is not, and that is a
        # difference a reviewer has to be told about rather than one PACT can
        # hide by reusing a word.
        type: map of group:knowledge
        surface: S-CAP
        tier: core
        help: sets of documents the agents look things up in and quote back
```

`agent.uses` gains `knowledge` in its `names:` list. **This is the strongest single argument in the draft and I measured it true**: `uses: [staff-handbook]` then produces

```
error: 'uses' names 'staff-handbook', and there is no such entry in `tools:`,
       `skills:` or `knowledge:`.
  fix: Change it to one of: hr-handbook — or add a file `tools/staff-handbook.yaml`,
       `skills/staff-handbook/SKILL.md` or `knowledge/staff-handbook/staff-handbook.yaml`.
```

— the per-kind file template is derived at `crates/pact-schema/src/lib.rs:1587-1594` and the sibling-kind search at `crates/pact-schema/src/elsewhere.rs:23-28`, so the existing diagnostic **starts teaching the construct** to an author who never heard of it, with no Rust change. `agent.uses`'s help must be updated in the same commit — help text is what `schema/missing-field` quotes back.

**One line owed on the way in:** `crates/pact-schema/src/lib.rs:1539` builds `places` with `.join(" or ")`, giving *"in `tools:` or `skills:` or `knowledge:`"*, while `or_list` one screen down (`:1596-1604`) produces "a, b or c" and is used for the file list in the same message. D1 puts the ungrammatical sentence in front of every author.

### The `knowledge` group

```yaml
  # Documents an agent looks something up in, rather than a procedure it reads
  # end to end.
  #
  # PACT does not retrieve, embed, index or chunk. A runtime that does all four
  # already exists; this kind declares what it needs to know and governs the part
  # a reviewer has to be able to read — the §4 declared-and-delegated pattern
  # (docs/50-NOT-COPIED.md §4), the same one `port.through:` and the durable
  # store use.
  #
  # Every other §4 row pairs the declaration with a channel. This one pairs it
  # with `unretrieved`, a FIFTH honesty channel: one sentence per entry a run
  # could not consult, naming the file, the line, why, and a line to type. It is
  # not a fifth use of `unenforced` for the same reason `never_reached` is not
  # `unmetered` — "the rule could not be evaluated" sends the author to the rule,
  # "the corpus was never read" sends them to the operator, and in between those
  # two sentences the agent answers from what the model already knew.
  knowledge:
    describe: set of documents
    fields:
      description:
        type: text
        required: yes
        surface: S-GEN
        tier: core
        help: >
          what this set of documents is, in one line. If it is one procedure and
          it always applies, write a skill instead: a skill is read end to end,
          this is looked things up in.

      documents:
        # NOT a glob, and this is the change that made D1 shippable. There is no
        # path type in this language and no glob anywhere in it — `grep -n
        # "glob\|wildcard\|\*\*" spec/schema.yaml` returns nothing — and the file
        # ORDER a glob returns is load-bearing for a digest `pact-loader`
        # promises is "reproducible on any machine". MEASURED with the glob:
        # `documents: /etc/passwd` and `documents: ../../../../etc/**` both
        # printed "OK — loaded cleanly", and so did a glob matching zero files.
        #
        # The folder convention already ships. `skills/<name>/references/` is
        # digested, typed and sized by `policy.rs`'s `payload_dirs` walker —
        # `pact show` emits `{"$payload": ..., "files": [{"$file": "leave.md",
        # "contentType": "application/md", "sizeBytes": 32}]}` — and adding
        # `documents` to that list is one line. It cannot climb out of the
        # workspace, its order is the walker's, and deleting a document moves
        # the digest.
        type: anything
        surface: S-CAP
        tier: core
        help: >
          the documents themselves, in a `documents/` folder beside this file.
          Kept as files rather than settings, so a table stays a table. A set of
          documents with no documents in it is refused: nothing would come back
          and the agent would answer from nothing.

      looked-up-by:
        # Plain words for what the literature calls dense retrieval, BM25 and
        # hybrid. Two draft choices are gone. `connections` (graph RAG) names a
        # structure a folder of documents does not carry. `the-agent-decides`
        # (agentic RAG) reads to a support lead as the leave-it-to-the-system
        # option — the one you pick when you do not know — while selecting the
        # most expensive and least predictable strategy; and one field below,
        # `split-by:` spelled the genuine leave-it-alone case `the-runtime-
        # decides`, so the two words that look like synonyms meant opposite
        # things. ABSENCE is the leave-it-alone option here, the way it is for
        # `available-when:`.
        #
        # `meaning` and `meaning-and-words` need an embedder, which is a model
        # outside this box. `embedder` was the one role in `allow-egress:` with
        # NO producer anywhere in the tree — `egress.rs:15` says so in its own
        # docstring — so this field is its fifth binding, and `allow-egress: []`
        # with `looked-up-by: meaning` is refused rather than quietly calling a
        # hosted embedder on every question a customer asks.
        type: one-of
        choices: [meaning, words, meaning-and-words]
        surface: S-CTRL
        tier: expert
        help: >
          how the runtime finds the right passages. `words` matches the words
          you typed, which is what you want for clause numbers, product codes
          and policy references. `meaning` matches what the question is about,
          and needs `embedder` in `allow-egress:` because that is a model
          outside this box. Leave it out and the runtime picks.

      split-by:
        type: one-of
        choices: [paragraph, heading, page, whole-file]
        surface: S-CTRL
        tier: expert
        help: >
          how a long document is broken up before anything is looked up in it.
          Leave it out and the runtime picks, which is the usual answer.

      passages-at-most:
        # S-GOV, not S-EXEC. MEASURED: all six other `<thing>-at-most` fields in
        # this file are S-GOV and none is S-EXEC — a passage count grants no
        # authority, and the security argument the draft made for S-EXEC is
        # already carried by S-GOV, which is CLASS-4 and GOVERNED just the same.
        # The durable argument is the other one: the number is declared in the
        # folder rather than set in the host, so a reviewer can read it.
        type: integer
        at-least: 1
        surface: S-GOV
        tier: core
        help: >
          how many pieces of document come back for one question. More is not
          better: every extra passage is more text a poisoned document could be
          hiding in. Leave it out and the runtime picks.

      must-cite:
        # The whole of what a support lead is trying to buy, and the ONE spelling
        # of it — the draft had a second, `if the answer does not name <a
        # knowledge>` as an interceptor sentence, which is R57's shape exactly
        # (two ways to say one thing, one of them unactionable).
        #
        # It is not decoration. An entry the run could not consult reports on
        # `unretrieved`, and `must-cite: yes` on such an entry FAILS THE TURN —
        # otherwise the agent answers from what the model already knew and cites
        # a document it never opened, which is the worst outcome available and
        # is the one that looks most like success.
        type: yes-no
        surface: S-GOV
        tier: core
        help: >
          whether an answer has to say which document it came from. `yes` means
          an answer with no source is not an answer: if the documents could not
          be read at all, the turn fails and says so rather than answering from
          memory.

      use-when: *the-applicability-boundary-use-when
      do-not-use-when: *the-applicability-boundary-do-not
      if-unsure: *the-applicability-boundary-if-unsure
```

The last three are taken **by YAML anchor from `skill`**, not restated — the `*the-hiding-sentences` precedent. `docs/93-GAPS.md:238-240` names them as must-survive: *"exactly what the literature names as the missing thing that makes skills harmful"* — and the hazard is strictly worse for retrieved text than for an authored procedure. The draft's field table silently dropped all three.

### The authored surface a support lead writes

```yaml
# knowledge/hr-handbook/hr-handbook.yaml
description: The HR handbook everyone asks about.
must-cite: yes
```

```
knowledge/hr-handbook/documents/leave.md
knowledge/hr-handbook/documents/pay.md
knowledge/hr-handbook/documents/notice-periods.md
```

```yaml
# agents/helpdesk/agent.yaml
uses: [hr-handbook]
```

**Two keys and a folder.** That is the D13 bar for this capability, and it is the number §7 measures.

### Diagnostics added

```
error: 'hr-handbook' is a set of documents with no documents in it.
  fix: Put the files in `knowledge/hr-handbook/documents/`. Nothing would come
       back from an empty one, and the agent would answer from nothing.
  rule: loader/knowledge-with-no-documents

error: nothing in this workspace may talk to something outside this box, and
       `looked-up-by: meaning` needs an embedder, which is a model that is.
  fix: Write `looked-up-by: words`, which matches the exact words and needs
       nothing outside — or add `embedder` to `allow-egress:`, which needs
       somebody to approve it.
  rule: loader/reaches-outside-the-box

warning: nothing anywhere names 'hr-handbook', so no agent will ever look
         anything up in it.
  fix: Add `- hr-handbook` under `uses:` on the agent that should answer from it.
  rule: loader/nothing-points-at-it        ← free, once B15 makes KINDS data
```

### Three things D1 owes that are not fields

1. **`never-from:` must be closed in the same change.** Measured, mine: replacing the flagship's `never-from: [tool output]` with `never-from: [the shoe size of a customer, retrieved passages]` printed **`OK — loaded cleanly (499 settings)`, exit 0.** `docs/50-NOT-COPIED.md:510` deleted a redaction sentence for exactly this property. It is `type: list of text`, S-EXEC, and it is on the `DELEGATED` register with the reason *"§4 row: the store refuses a write from a source this names"* — the enforcement is honestly delegated and **the vocabulary is held against nothing.** The first author who writes the protection `knowledge:` makes necessary gets a line that binds nothing and believes they are protected. Closed list: `[tool output, retrieval, the customer, a teammate]`. **Prerequisite, not follow-on.**

2. **`pact card` must not publish a corpus as an invocable skill.** `crates/pact-cli/src/discover.rs:196-208` maps **every** `uses:` entry to an A2A skill with `"description": format!("uses {s}")`, and the function's own docstring says a card is *"for discovery and invocation"*. One screen down it already distinguishes a different kind of thing (`handoff:{m}` / `"delegates to {m}"`), so the vocabulary exists. **Knowledge is the first thing `uses:` will ever carry that is not invocable.** Decision: it is **not projected at all** — a card is a facade (`"instructions, filesystem paths and credential bindings are not projected"`), a corpus name is closer to an internal detail than a callable capability, and not projecting it also stops corpus names leaking to another organisation.

3. **Six `DELEGATED` rows, each with its written reason** — `looked-up-by`, `split-by`, `passages-at-most`, `must-cite` (the enforcement half), plus the two the run reports. `DELEGATED` has 14 entries today and `KNOWN_GAPS` is **empty**. That is +43% to a ledger the whole project took 14 entries to accumulate, from one fix — which is a real cost and the reason the rows are written, not a reason to skip them. The alternative is silence, and `docs/50-NOT-COPIED.md` §6's own rule is *"never silence."*

### Where the example goes

**Not `examples/refund-desk`.** Measured, mine: `crates/pact-cli/tests/authoring_surface.rs:73` asserts `files <= 26` and the tree measures **exactly 26**; `:147` asserts `extra <= 15` and it measures **exactly 15**. And `knowledge` is in **neither** the `CORE` nor the `SHOWCASE` list, which is the failure both test comments name: *"a directory nobody counts is a directory that can grow without anyone noticing."* The RAG shape gets `examples/patterns/answers-from-documents/`, which is what P4's gate asks for and costs neither ceiling — and `knowledge` joins the `SHOWCASE` list in the same commit so it can never be uncounted.

---

## 1.17 D5 — `pact try`, as the honesty printer

Re-proposes no refusal: `docs/50-NOT-COPIED.md` §1.3 refuses a 17,838-line terminal console (its own "what to do instead" is `pact check` on the folder), §1.4 refuses executing the *author's code*, and NG1 was explicitly revised at `docs/01-DECISIONS.md:261` — *"PACT is not a server, but it does own an execution model."* The verb-promise drift guard at `crates/pact-cli/tests/authoring_surface.rs:357-431` is one-directional, so adding a verb is free.

**Four conditions, all of which change the phase gate:**

1. **It runs the full `pact check` first and refuses the same trees.** R54 — `card`, `waits`, `show` and `discover` were all made to do this, because *"only `check` refuses it"* meant *"every adapter accepts it."* A verb that RUNS a tree `check` refuses is the strongest form of that hole.
2. **The deterministic mock is the DEFAULT**, so it satisfies D17 with no flag. An instrument that needs a served model cannot measure the safety phase on an air-gapped machine.
3. **A run against the mock reports every ceiling on `unmetered`, naming the mock.** `models/catalog.yaml` has no row for it; a real zero reported as a working ceiling is R25/R38's family.
4. **`--why-not` prints all five honesty channels.** This is the *reason* the verb exists. Nothing in Rust emits or prints them today.

**Known limitation, stated rather than discovered:** the mock publishes `durable_resume: "unsupported"` (`mock.py:51`) and `pact try` is one turn with no resume verb, so it **cannot** exercise B1/B2/B4. Those are tested at the Python layer, where `test_hitl_kill_resume.py:132` already parks and resumes. Writing this down is what stops the phase gate measuring the wrong thing.

---

## 1.18 A6 → `tries:` — **REFUSED. The shape already ships.**

*This section closes the first of the two silences §2 filed against this document. It is a refusal, and the refusal is the finding.*

A6 asked for self-consistency: work the question several ways, then settle. `93-GAPS.md:81` ranks it above A7 on evidence-per-cost. A `stage.tries` field was designed for it — `+1 field name, 0 groups, 0 choice values`, `type: integer`, `at-least: 2`, S-GOV/expert, matched to `stage.at-most`. It was then **built** and measured, and it does not survive.

### It is not a gap. `examples/patterns/quorum/` is the answer, authored today

| | |
|---|---|
| `agents/reader-a\|b\|c/agent.yaml` | three readers, **instructions byte-identical** — verified, all three hash `12050f70e08a` |
| `agents/referee/agent.yaml` | `waits-for: enough-of-them` · `enough-is: 2` · `starts: all-at-once` · `divides-the-budget: evenly` · `if-someone-fails: carry-on` |
| the fold | *"Say which two you used and whether they agreed with each other. If the two you got disagree, say so plainly rather than picking one."* |

That is best-of-N with a disagreement-reporting settle, and each member is a whole run with **its own `history`, `Meter` and `Ledger`** — so it is independent of the run so far as well as of its siblings, which is the property `tries:` was for and the property a same-history fan-out cannot have. It also gets concurrency, budget division and a failure policy, none of which `tries:` had.

### The four measured kills, any one of which is sufficient

1. **Its one cross-cutting edit is inert, and its own named mutation cannot turn it red.** `spec.limits.reached()` is called at three sites (`harness.py:1013`, `:1204`, `:1750`) and **none passes `steps_at_most`**; the ceiling is enforced solely by `for i in range(start, limit)` falling off the end, and `harness.py:1992` then overwrites the accumulator with `meter.steps = limit`. Built, with `steps-at-most: 4` and `tries: 3`: **12 model calls made, reported as `` `steps-at-most` (4 of 4 steps) `` — the identical sentence the 4-call control prints.** Restoring the design's own red-maker produced **byte-identical output**. The single item in the set carrying a runtime justified it with a test whose named mutation is a no-op.
2. **A `tries:` stage can park, and the park loses the work and re-charges it.** Measured at a `0.05 USD` cap with three tries at `0.02`: `parked.history` holds only `[('user','q')]` — all three tries' text gone; `parked.used steps: 0.0` after three paid calls, which is the figure `questions/keep-going.yaml` shows a person; `parked.visits: {}`, so resume re-runs the whole fan-out. **That is B2's shape** — *"parking for approval hands the run a fresh spend budget"* — arriving through the one item added to fix an expressiveness gap.
3. **It is indistinguishable from `stage.at-most`.** Same spec, same script: `tries: 3` and `at-most: 3` + ring produce identical call counts, identical `phases`, identical step texts. The only difference is `Step.index` (`0,0,0,1` vs `0,1,2,3`) — which the design breaks anyway by making it non-unique, on a field whose docstring reads *"The comparable shape. Two transports agree iff these are equal."*
4. **It is undemonstrable on the only air-gapped model PACT ships.** `Script.next_turn` keys on the assistant-message count (`script.py:38-48`, deliberately — its docstring gives the resume reason). Three tries have identical histories by construction, so the scripted transport returns the same text three times. Its own test *"scripted so the three answers differ"* is **not writable**, and D17 requires the pipeline to run air-gapped.

### And the example has nowhere to live

The design placed it at `examples/patterns/answers-more-than-one-way/` to stay under the 26-file D14 bound. Creating that directory fails `test_the_orchestration_patterns_are_distinct_and_run.py:73-80`; adding it to `LEADS` then hits `:98-106`, which asserts `spec.teamwork is not None` for **every** pattern. The only directory PACT has for a "several answers, then settle" example is guarded by a test requiring the very construct the design argued `tries:` was not.

### Two silent holes it never closed

`does: ask-someone` + `tries: 3` → **0 model calls, silently ignored**. A terminal `tries:` stage (`then: answered: done`) → **the customer receives the fold**, `try 1 of 3:` labels and all. Its own example was one deleted line from the second.

### What is owed instead

Not a second parallel mechanism. **Measure whether `quorum/` is enough** — and if it is not, the missing piece is a *scope* on the existing `teamwork:` fold, not a new field whose runs are byte-identical to `at-most:`. Filed to `50-NOT-COPIED.md` §6 with `examples/patterns/quorum/` as its re-admission fixture: *A6 is re-admitted when someone writes a case `quorum/` cannot express.*

---

## 1.19 The closed-choice growth test — **ships, sequenced late, with the instrument repaired first**

*This closes the second silence: this set adds **16 new closed-choice values to a shipped population of 126 (+12.7%)**, and nothing in the tree bounds that.*

### Why a value, not a name

**A dead field name is inert. A dead choice value is *recommended*.** When an author writes an unknown value, the checker prints the whole legal list in its own `fix:` line — so a value nothing reads is not merely unused, it is *taught to every author who makes a typo near it*. That is R24's sentence verbatim, arriving through the one construct the field-level instrument does not cover.

### The three alternatives, rejected with computed data

| candidate | why not |
|---|---|
| a budget (`≤ N values`) | arbitrary; no principle sets N |
| a ratio (values ÷ names) | `126/207 = 0.609` → `142/219 = 0.648`; fires identically on healthy and unhealthy growth |
| a per-field cap | the largest shipped list is **8** (`bundle.brings`), the largest new one is **7** — a cap at today's maximum is **green through the entire set** |

The rule is therefore **per-value reachability**: every value in every closed choice must be read by something that is not a test and not prose.

### It would have caught what the ledger deleted — and today's instrument would not

| | R58 (`sandbox`, `content-store`, `memory`) | R60 (`prompt`, `built-in`) |
|---|---|---|
| shipped `reader_exists`, shipped corpus | **1 / 3** | **0 / 2** |
| literal-match, comments stripped, no `tests/` | **3 / 3** | **2 / 2** |

`test_every_field_has_a_reader.py` **would have blessed the values R58 and R60 deleted** — matching only comments, including, at `crates/pact-loader/src/reach.rs:7`, a comment about its own deletion.

### The instrument is broken today, and not in the way first reported

`reader_exists` (`test_every_field_has_a_reader.py:100-111`) tries five patterns, the last of which is `f" {snake}"` — a space and the word. Run against the shipped corpus, **every one of this plan's new names is already lit, by English prose inside a diagnostic string**:

```
tries      lit-by=[' tries']   crates/pact-loader/src/callable.rs:159:
                               "so the first thing this agent tries to do fails
                                before a word is written."
knowledge  lit-by=[' knowledge']
documents  lit-by=[' documents']
claim      lit-by=[' claim']
owner      lit-by=[' owner']
```

Three consequences, in order of severity:

1. **A new field can ship, be read by nothing, and the honesty instrument stays green** — the failure mode the instrument exists to prevent, live, on five of this plan's own names.
2. **Stripping comments does not fix it.** A diagnostic message is a *string literal*. The growth test's own corpus remedy would leave all five lit. The `f" {snake}"` pattern must go, or be confined to identifier positions.
3. `sources()` skips a file only `if "test" in p.name`, so **56 of the 139 files it walks are under a `tests/` directory** — 2,634,433 chars of corpus, of which the tightened rule keeps 800,631. Dark slots go **12 → 36 of 155**; field-level orphans go 9 → 10, and the one new orphan is exactly `state.forget-after`.

**Repairing `reader_exists` is therefore a prerequisite of the growth test, not a footnote to it** — and it is the higher-value half. It ships as its own commit, with `state.forget-after` as the regression the corpus fix must surface.

### Sequencing — **P5, not P0**

Sequenced first, the growth test is **red on 13 of this set's own 16 new values**: `this-run`, `the-team`, `the-workspace`, `meaning`, `meaning-and-words`, `paragraph`, `heading`, `page`, `whole-file`, `durable-execution`, `retrieval`, `the customer`, `a teammate`. Three arrive lit **by accident** — `checkpoint` (a message flag in `context_policy.py:1198`), `words` (a token unit, `:493`), `tool output` (a part-kind, `:98`) — none of which has anything to do with the field claiming them.

And `the-team`/`the-workspace` have **no seam in the reference harness** (§1.13). Once `scope.rs` compares them as literals they become "lit" by a *check-time refusal* while nothing at run time honours them — the exact false-liveness this test exists to detect. Meanwhile `this-run`, the only scope actually enforced, arrives dark.

So the order is: **repair `reader_exists` (P0, as a bug fix)** → ship the values (P1–P4) → **admit the growth test last (P5)**, when the population it polices exists. A guard that is red on 81% of the work it is guarding is not a guard; it is a blocker with a test's name.

### The sentence-name and its mutation

```
every_value_an_author_may_type_is_read_by_something_that_is_not_a_test
```

**Mutation:** delete the arm in `crates/pact-loader/src/scope.rs` that compares `the-workspace`. The value stays in `spec/schema.yaml`, stays in every `fix:` line the checker prints, and the test must turn **red**. If it stays green the corpus is still too loose.

---

# 2. WHAT WAS CUT, AND WHY

| Cut | The argument that killed it |
|---|---|
| **F6** — `if the answer does not name <a knowledge>, stop and say "<why>"` | Four independent kills, and they compound. **(i)** Its verb `name` collides with `names:`, the loader's most load-bearing word (30+ fields). **(ii)** As a *deterministic* test it can only be a substring test on the slug, so *"I am not allowed to use hr-handbook for this"* passes and *"per the HR Handbook §4"* fails — **it fires on correct answers and passes wrong ones**, which is worse than no rule. **(iii)** The payload at `turn.message.after` is `{"content": text}` (`harness.py:1246`) and nothing else; `Carries` (`interceptors.py:722-742`) has three flags and no column for what was cited. **(iv)** It is R57's shape — two ways to say one thing, one of them unactionable — beside `must-cite:`. Its intent lands on `must-cite:` as the single spelling. |
| **A4** — `list of <shape>` | **Cut as motivated, not as an idea.** Its only stated purpose in this set was D1 loader check #4, and that check is undecidable (`answers-with` is `map of answer-shape` with author-chosen keys; nothing distinguishes `citations: list of text` from `notes: list of text`) *and* its consumer F6 is cut. What remains: `answers-with:` is a prompt instruction — `harness.py:2671-2684` emits *"End your reply with each of these, one per line"*, the two modes that would constrain the reply at the provider are `MODES_NOTHING_HERE_DELIVERS` (`harness.py:326`) and no transport implements either. **A4 would buy the ability to write the word "list" inside a sentence pasted into a system prompt.** And it is a head-on collision: `list of images`, `list of audio` and `list of files` already ship as **aliases for the SCALAR shapes** (`spec/schema.yaml:385-393`, measured), `Shape.written()` round-trips `list of images` → `images` non-injectively, and two egress modules in two languages hardcode `"list of audio"`. Deferred with a fixture. |
| **`requires-of-the-runtime:`** | Deleted in writing at `docs/91-REVIEW-CRITIQUE.md:189` on the R59 argument, and `durable_resume` is a lattice key on eleven transports. Replaced by `durability:`, which is `93-GAPS.md:92`'s own spelling. |
| **`knowledge.connect:`** | **The single most dangerous line in the draft.** `crates/pact-loader/src/report.rs:552-565` and `adapters/python/src/pact_adapters/suspension.py:385-390` both resolve connection-consent waits by looking the `uses:` name up **under `tools:` only** — so a knowledge entry connecting to a resource carrying `asks-to-connect:` produces **no wait**. `report.rs:545-551`'s own comment describes this exact failure as already-fixed-once: *"a human consent gate on money, gone in silence."* It also re-opens R58 (`resource-kind:` has one surviving choice, `mcp-server`; a retrieval service is a content store) without executing R58's named re-admission path, and it carries no `actions:` allow-list, which is §1.1's whole argument for having no built-in tools. Deferred with a fixture. |
| **`knowledge.freshest-by:`** | An open-text hole in an **S-GOV** field naming a field in a document PACT never reads. `freshest-by: the shoe size of a customer` loads clean. That is simultaneously `50-NOT-COPIED.md:510`'s deleted-sentence shape and R20's shape (resolving a name only the host can know), in a governance column. The quietest re-proposal in the set; no lens touched it. |
| **`knowledge.file-types:`** | Derivable from the folder the moment `documents:` is a folder — `policy.rs`'s walker already emits `contentType` per file. An authored list that can disagree with the files on disk (`file-types: [pdf]` over a folder of `.md` loads clean) is a second spelling of a fact the tree carries. |
| **`knowledge.available-when:`** | Three of its five choices are meaningless for a corpus (`this-agent-has-helpers`, `this-agent-has-procedures`, `a-person-can-be-asked`), which is verbatim R58's reason — a required-looking control with one sensible value and three ways to be wrong. And the mechanism it would inherit is the broken one B15 is fixing. |
| **`looked-up-by: connections` and `the-agent-decides`** | `connections` names a structure a folder of documents does not carry. `the-agent-decides` reads to a support lead as the leave-it-to-the-system option while selecting agentic RAG, and one field below `split-by: the-runtime-decides` spelled the *genuine* leave-it-alone case — two words that look like synonyms meaning opposite things. Absence is the leave-it-alone option, per `available-when:`'s own precedent. |
| **`split-by: the-runtime-decides`** | A value spelling of an absence, i.e. two ways to say one thing. |
| **B11's `people:` map** | A **seventh top-level collection** carrying the full D1 registry cost (`derive.rs`, `unnamed.rs`, `bundle.brings`, digest, discovery), crossing into §4's host-inventory delegation (*"a registry of them would make the portable artifact depend on one host's inventory"*). It also **breaks the shipped flagship on four files** and contradicts `spec/questions/is-this-ok.yaml:39`, which PACT itself supplies with `asked-of: [whoever-is-running-this]`. Deferred with a fixture. |
| **B12's `guarded_by` reads `more-than:`** | `money.rs:327-356` inserts `when.get("tool")` and never looks at the figure, and **there is no principled ceiling to compare against** — picking one would be an unauthored policy. Reproduced: `more-than: 100000000 USD` marks the action guarded with zero diagnostics, so `--deny-warnings` would have nothing to deny. |
| **`--deny-warnings` in P1** | Measured inert (0 warnings across nine shipped workspaces) and load-bearing in the wrong direction: it turns 14 heuristic cross-document judgements into build failures, removing the property that makes them safe to add — in the same phase as a redesign of one of them. Moved to P2, after B15 makes `loader/never-offered` fixable. A flag that turns *unfixable* warnings into build failures is worse than no flag. |
| **B10 as `loader/reads-nothing`** | It cannot distinguish an inert control from an honest §4 delegation — which is the shape D1 rests on — and enumerating "wherever a written line binds nothing" is the vigilance `test_every_field_has_a_reader.py` exists to replace. Replaced by the port-parity corpus and `loader/power-nothing-can-use`. |
| **B8's type-gated arm** | Would break the `instructions/` folder feature, which is D2's Expansion Rule and the flagship's shipped shape. Replaced by `may-be-a-folder:`. |
| **`allow-connect:`** | R61 (*"two settings for what must never leave a workspace"*) plus R20 (`endpoint:` is a platform-published name, not a hostname, so a hostname list can never be matched against it). Replaced by one value on `allow-egress:` plus `reaches-outside:`. |
| **A3's fail-closed runtime polarity** | Deferred, not cut — see §6. It changes what an existing `more-than:` rule means and no lens produced evidence about which polarity an author expects. Replaced in this set by `loader/a-value-this-rule-never-sees`, which is decidable and says the same thing at check time for the closed-choice case. |
| **`passages-at-most: S-EXEC`** | Measured: six of seven shipped `<thing>-at-most` fields are S-GOV and **none** is S-EXEC. The security intent is already carried by S-GOV (both are CLASS-4, both GOVERNED). Also, the 6%→20%→38% attack-rate sequence the draft cites was corrected at `docs/91-REVIEW-CRITIQUE.md:267`; the durable argument is *"declared in the folder rather than set in the host."* |

**Three cuts from the second iteration, added after the two silences below were worked:**

| Cut | The argument that killed it |
|---|---|
| **A6 `tries:`** — the whole field | **Built and measured; see §1.18.** Its one cross-cutting edit is inert and its own named mutation produced byte-identical output; a `tries:` stage parks with `visits: {}` and `used: 0.0` after three paid calls, re-running the fan-out on resume — B2's shape, reintroduced by an expressiveness fix; its runs are byte-identical to `stage.at-most` except for a `Step.index` it breaks; and it is undemonstrable on the shipped air-gapped `Script` transport. **`examples/patterns/quorum/` already ships the shape**, with independent `Meter`/`Ledger` per member, concurrency, budget division and a failure policy. Deferred with `quorum/` as its own re-admission fixture. |
| **B13's `needed-when:` on `same-request-key-across:`** | Not a new cut — a **correction to §1.13**, which shipped `needed-when: { durability: durable-execution }`. That attribute is **doubly dead**. `crates/pact-schema/src/lib.rs:681` looks the partner up in `g.fields` — *the same group only* — and `continue`s in silence when it is absent; `durability:` is a **workspace** field and this is an **action** field, so the tie can never be evaluated. And `durable-execution` is not among the field's own choices, so the comparison at `:668-676` could never be true either. Reproduced through `--unsafe-spec`: `same-request-key-across: the-workspace` on a tree with **no `durability:` line anywhere** printed `OK — loaded cleanly`. An attribute that cannot fire is R24's defect wearing schema meta. The check moves to `crates/pact-loader/src/scope.rs`, where a fact about two documents belongs. |
| **A6's warning `loader/more-ways-than-there-are-steps`** | A measured **false refusal**. For `tries: 3` / `at-most: 2` / `steps-at-most: 4` it would have said *"That stage cannot finish."* The run finishes — 7 model calls, `halted: final`. `steps-at-most` bounds stage entries, never model calls. It would have landed in the phase gated by `the_shipped_tree_gains_no_new_diagnostic_from_any_of_these`. |

**The two silences this document filed against itself, now closed:**

- **B13 (contended claim)** — closed in §D4 as a deferral, and the answer is that **PACT already has one**: `same-request-key: <id>` plus `same-request-key-across:` at a scope wider than one run **is** mutual exclusion. Measured — the reference harness withheld a second claim of `Q-7` made by a *different agent* in a *different run* once the host handed the record back. What a claim additionally needs — releasing it, seeing who holds it, expiring it — is a **lease**, and that is deferred with a fixture, because `Ledger` has no release and no introspection and a lease is a design nobody in this literature has built. **Zero new field names, zero new groups, zero new choice values.** The row's honesty limit is stated in §D4: the drafted reason (*"the machinery stays keyed to the word money"*) is **right in the half an author meets** — on a non-money `claim`, the checker is what they see — and wrong only in the mechanism beneath it.
- **A6 (`tries:`)** — closed as a **refusal** in §1.18. `93-GAPS.md:81` ranked it above A7 on evidence-per-cost, and that ranking is not disputed; what is disputed is that PACT lacks the shape. It does not. P4's gate named three shapes; this set answers one and **refuses one with its answer named**, which is the register's own contract.

---

# 3. THE DEPENDENCY GRAPH

```
                      ┌─────────────────────────────────────────┐
                      │  P0 · THE INSTRUMENTS — nothing first   │
                      └─────────────────────────────────────────┘
    every_fix_the_checker_offers_leaves_a_tree_that_checks_clean   ── red today
                                  │
                                  ▼
                   B15  (four tables → data; (kind,field) pairs)
                     │        │            │             │
        ┌────────────┘        │            │             └────────────┐
        ▼                     ▼            ▼                          ▼
  available.rs        derive.rs      bundles.rs                unnamed.rs
  fixable warning     COLLECTIONS    contributed-kind          KINDS gains
                                     is REFUSED not skipped    `skills` + `knowledge`
        │                                                             │
        └──────────────────────────► --deny-warnings (P2) ◄───────────┘

    port-parity corpus  ──────────────►  every later diagnostic is DRIVEN by it
    (test_what_one_port_refuses…)

┌──────────────────── P1 · SAFETY — dependency-ordered ─────────────────────┐
│                                                                          │
│  B8  (may-be-a-folder:)  ── free-standing ──┐                            │
│  B1/B2/B4 (park())       ── free-standing ──┼─ can land in PARALLEL      │
│  B11 half one            ── free-standing ──┤                            │
│  B12 inference           ── needs B15 ──────┘                            │
│                                                                          │
│  B3 (chain on ANSWER) ──┐                                                │
│                         ├──► F7 (the stopping sentence)                  │
│  power-nothing-can-use ─┘                                                │
│                                                                          │
│  step.tool.completed → reaches:  ── free-standing, but gates D1's trust  │
│  B9 (reaches-outside: + `tools`) ── free-standing ── gates D1            │
│  never-from: closed              ── free-standing ── gates D1            │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────── P3 · THE SMALL ADDITIONS ────────────────────────────┐
│  A12 + workspace-path  ── free-standing, cheapest, PARALLEL              │
│  A2 + RunResult.retrieved ─ free-standing, PARALLEL                      │
│  A8 durability:  ────────►  A5 same-request-key-across:                  │
│  A3 (needs-one-of: + shape + uncovered-choices)  ── free-standing        │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────── P4 · D1 · knowledge: ────────────────────────────────┐
│  gated on ALL of:  B15 · B8 · B9 · never-from: closed ·                  │
│                    step.tool.completed · the `unretrieved` channel ·     │
│                    the TS `notDoneHere` row + REPORTED row               │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────── P5 · THE GROWTH GUARD — deliberately LAST ───────────┐
│  every_value_an_author_may_type_is_read_by_something_that_is_not_a_test  │
│  gated on ALL 16 new values existing:  A5 · A8 · A3 · D1 · never-from:   │
└──────────────────────────────────────────────────────────────────────────┘

D5 (pact try) runs ALONGSIDE from the start.  Nothing depends on it.
```

**Two corrections the second iteration forced into this graph.**

`A8 durability: ──► A5 same-request-key-across:` in P3 is now **also** written by the B13 correction (§2), which deletes the dead `needed-when:` from that same block and adds `crates/pact-loader/src/scope.rs`. Two items writing one schema block in one phase: they are **one commit**, not two, and the phase owns the `money.rs` bug fixes B13 measured alongside it.

The growth guard is **P5 and cannot be P0**. Sequenced first it is red on 13 of this set's own 16 values (§1.19). But its prerequisite — **repairing `reader_exists`** — *is* P0, because that instrument is green today on five names this plan is about to add and nothing reads (`tries`, `knowledge`, `documents`, `claim`, `owner`), all lit by English prose inside diagnostic strings. The repair is a P0 bug fix; the new guard it enables is P5.

**What can land in parallel, explicitly:** in P1, `B8` · `B1/B2/B4` · `B11 half one` · `B9` · `never-from:` · `step.tool.completed` are six independent commits touching disjoint files. In P3, `A12` and `A2` are independent of everything and of each other. `B3` and `power-nothing-can-use` are independent of each other and both gate `F7`.

**The three hard gates, restated as sentences:**
- `--deny-warnings` may not land before B15, because `loader/never-offered` is an *unfixable* warning today — I typed its fix and got `schema/unknown-field`.
- `F7` may not land before `B3`, or a "never give medical advice" rule is escapable by exhausting the step budget.
- `F7` may not land before `power-nothing-can-use`, or it closes one case and leaves R24's class open.

---

# 4. THE IMPLEMENTATION ORDER

Each phase ends in a **named test**. Nothing advances until the named mutation turns the named test red *and* the fix turns it green.

### P0 — The instruments. No fix lands first.

| # | Work | Gate (named test) | Red today? |
|---|---|---|---|
| 1 | Generalise the type-the-fix test | `every_fix_the_checker_offers_leaves_a_tree_that_checks_clean::a_fix_the_binary_refuses_when_typed_is_not_a_fix` | **yes** — reproduced |
| 2 | The four tables → data | `a_table_in_the_loader_names_only_what_the_schema_declares::every_agent_field_a_condition_asks_for_is_a_field_an_agent_can_have` | **yes** — `knows`, `skills`, `resources` |
| 3 | Bundle contribution refuses | `a_bundle_is_held_to_everything_it_contributes::a_contributed_kind_the_table_does_not_know_is_refused_and_not_skipped` | **yes** |
| 4 | Port-parity corpus | `test_what_one_port_refuses_the_other_refuses_too::test_every_document_the_runtime_refuses_from_the_document_alone_is_refused_by_check` | **yes** — three classes |
| 5 | **Repair `reader_exists`** — drop the ` {snake}` prose pattern, exclude `tests/` dirs, strip comments | `test_every_field_has_a_reader::a_field_named_only_in_a_sentence_the_checker_prints_is_not_a_field_anything_reads` | **yes** — `tries`, `knowledge`, `documents`, `claim`, `owner` all lit by prose |

**Phase gate: `a_fix_the_binary_refuses_when_typed_is_not_a_fix` is green over the whole fixture corpus.** After this, adding a field costs a YAML block — the precondition for every fix below.

**Item 5 is new in the second iteration and it is the one that reorders the rest.** The honesty instrument this whole plan leans on is green today for five names this plan is about to introduce and nothing reads — all five matched by `f" {snake}"` against English prose inside diagnostic strings, e.g. `crates/pact-loader/src/callable.rs:159`. Its regression is `state.forget-after`, which appears as a tenth field-level orphan the moment `tests/` is excluded. Repairing it is P0; the **growth guard it enables is P5** (§1.19), because sequenced early it is red on 13 of this set's own 16 new values.

### P1 — Safety, in dependency order.

| # | Work | Gate (named test) |
|---|---|---|
| 5 | B8 `may-be-a-folder:` | `a_folder_of_prose_is_never_a_name::a_field_that_resolves_a_name_refuses_a_folder_of_prose` (parameterised over all 22, computed) **and** `instructions_written_as_a_folder_of_files_still_loads` |
| 6 | B1/B2/B4 `park()` | `test_a_park_carries_everything_a_resume_needs::test_every_park_site_fills_the_same_durable_block` |
| 7 | `power-nothing-can-use` | `a_power_no_sentence_can_reach_is_refused_where_it_is_written::a_may_entry_no_rule_at_any_of_this_files_moments_can_produce_is_refused` |
| 8 | B3 chain on ANSWER | `test_the_closing_answer_goes_through_the_same_rules::test_a_card_number_in_the_answer_at_the_step_ceiling_is_still_hidden` |
| 9 | **F7** | `one_vocabulary_for_hiding::a_live_stop_and_a_graded_case_use_the_same_words_for_the_same_act` |
| 10 | `step.tool.completed` → `reaches:` | `one_rule_at_several_moments::a_rule_can_see_what_came_back_and_not_only_what_is_about_to_go` |
| 11 | B11 half one | `nobody_approves_their_own_work::an_agent_may_not_be_named_as_the_person_who_approves_it` |
| 12 | B9 | `one_file_says_what_must_never_leave::a_tool_that_reaches_the_internet_is_refused_when_nothing_may_leave` **and** `an_address_the_host_resolves_is_not_something_leaving_the_box` |
| 13 | `never-from:` closed | `one_file_says_what_must_never_leave::a_source_no_store_could_recognise_is_refused_where_it_is_written` |
| 14 | B12 inference | `money_that_moves_with_nobody_asked::an_argument_typed_money_is_money_moving_whether_or_not_anybody_said_so` |

**Phase gate: `the_shipped_tree_gains_no_new_diagnostic_from_any_of_these` — all nine example trees stay at zero warnings and zero errors.**

### P2 — Make the flag safe, then turn it on.

15. `--deny-warnings` + a CI job over `examples/**`.
**Gate: `the_examples_stay_clean_under_deny_warnings`.**

### P3 — The small additions.

| # | Work | Gate |
|---|---|---|
| 16 | A12 + `workspace-path` | `test_the_shapes_a_person_can_answer_with::test_the_flagship_can_read_the_input_it_declares` |
| 17 | A2 + `RunResult.retrieved` | `test_a_retrieval_score_measures_the_retrieval::test_a_faithfulness_score_moves_when_the_passages_move` |
| 18 | A8 `durability:` | `waits_the_worked_example_can_produce::a_workspace_that_parks_may_not_say_it_needs_no_durable_resume` |
| 19 | A5 `same-request-key-across:` | `test_at_most_once::test_a_scope_this_run_cannot_keep_is_reported_and_not_silently_narrowed` |
| 20 | A3 (one commit: attribute + 2 fields + shape rule + 4 Python readers) | `a_gate_that_reads_what_it_may_not::a_comparison_is_written_in_the_shape_the_argument_declares` |

**Phase gate: `a_gate_written_in_one_line` passes for a tier, a region and a score, and none of the three can be written as a currency.**

### P4 — `knowledge:`.

21. `knowledge` group + `workspace.knowledge` + `agent.uses` + `SHOWCASE` row.
22. `documents/` into `policy.rs::payload_dirs`.
23. The `unretrieved` channel; `must-cite:` fails the turn on it.
24. `discover.rs` stops projecting it; TS `notDoneHere` + `REPORTED` row + §7.28 list B + README (four coordinated edits or the drift guard fires).
25. `examples/patterns/answers-from-documents/`.

**Phase gate: `digest_equality_for_the_new_kinds` covers a fifth kind, and `test_must_cite_on_an_entry_that_reported_unretrieved_fails_the_turn` is green.**

### P5 — The growth guard. Last, on purpose.

26. `every_value_an_author_may_type_is_read_by_something_that_is_not_a_test`, over the corpus P0 item 5 tightened.

**Phase gate: it is green on all 142 values, and the named mutation — deleting `scope.rs`'s `the-workspace` arm while leaving the value in the schema and in every `fix:` line the checker prints — turns it red.** If that mutation stays green, the corpus is still too loose and the guard has not been earned.

### Alongside, from day one

**D5 `pact try`**, with `--why-not` printing all five channels. **Its gate is a list, not a judgement:** (i) does a rule bound at `turn.message.after` fire on the `Action.ANSWER` path, before and after B3; (ii) does an interceptor at `step.tool.before` actually receive nested argument values, which the schema's help promises; (iii) does a stopping rule that *did not fire* look different in the output from one that did. **Not** (iv) does a resumed run refuse a replayed key — the mock publishes `durable_resume: "unsupported"` and `pact try` has no resume verb; that one is tested in Python.

---

# 5. THE TEST PLAN

Every test with its sentence-name and its mutation. **Layer** says which port pays.

## P0

| file · fn | layer | asserts | mutation that must turn it red |
|---|---|---|---|
| `crates/pact-cli/tests/every_fix_the_checker_offers_leaves_a_tree_that_checks_clean.rs` · `a_fix_the_binary_refuses_when_typed_is_not_a_fix` | CLI, over the real binary | for each fixture drawing a diagnostic whose `fix:` names a line to add: apply it literally, re-run, assert the new output contains no `schema/unknown-field` naming the key just added | restore `("skills","knows")` and `("resources","uses")` in `available.rs:45` — **red today** |
| `crates/pact-loader/tests/a_table_in_the_loader_names_only_what_the_schema_declares.rs` · `every_collection_a_loader_module_walks_is_a_field_the_workspace_has` | loader | `COLLECTIONS` ⊆ the workspace's 23 fields | re-add `"schedules"` to `derive.rs:47-63` |
| ″ · `every_agent_field_a_condition_asks_for_is_a_field_an_agent_can_have` | loader | every `satisfied-by:` value names a real `agent.*` field | point one row at `agent.skills` |
| ″ · `every_kind_a_bundle_may_bring_is_a_collection_the_workspace_has` | loader | `brings:` choices are generated from workspace collection names | hand-write `watches` back |
| `crates/pact-cli/tests/a_bundle_is_held_to_everything_it_contributes.rs` · `a_contributed_kind_the_table_does_not_know_is_refused_and_not_skipped` | CLI | `contributes: {watch: …}` outside `brings:` is an error | change the refusal back to `continue` — **red today** |
| `adapters/python/tests/test_what_one_port_refuses_the_other_refuses_too.py` · `test_every_document_the_runtime_refuses_from_the_document_alone_is_refused_by_check` | cross-port | for each workspace in `tests/corpus/decidable-statically/`, Python raises or marks `unenforced` **from the document with no model** AND `pact check` exits non-zero | delete the colonless-URI arm at `providers.py:447` — the test must fail **asymmetrically** and name which port lost it |

**The seam version to avoid:** asserting `NEEDS` has three rows, or that the rows are schema names. Both pass while the author is still walked into an error.

## P1

| file · fn | layer | asserts | mutation |
|---|---|---|---|
| `crates/pact-schema/tests/a_folder_of_prose_is_never_a_name.rs` · `a_field_that_resolves_a_name_refuses_a_folder_of_prose` | schema | parameterised over all **22** fields carrying `type: text` + `names:`, **computed from the schema, not listed** | drop the `names:` predicate → red on all 22 |
| ″ · `instructions_written_as_a_folder_of_files_still_loads` | schema | `agents/refund-desk/instructions.md` still loads; the flagship still checks clean | drop the `may-be-a-folder` allowance → the flagship stops loading |
| ″ · `a_typo_and_a_map_in_the_same_position_are_the_same_message_family` | schema | `loop: carefull` and `loop: {banana: purple}` are both refused, same field, same family | reorder the arm relative to name resolution |
| ″ · `no_field_carries_both_a_name_to_resolve_and_a_folder_of_prose` | schema | the invariant, computed | set `may-be-a-folder` on `agent.loop` |
| `adapters/python/tests/test_a_park_carries_everything_a_resume_needs.py` · `test_every_park_site_fills_the_same_durable_block` | runtime | the register is total in **both** directions: every `suspend()` goes through `park()`, and `park()` takes all three as required kwargs | add a sixth `suspend()` bypassing the helper |
| ″ · `test_a_refund_issued_before_a_park_cannot_be_issued_again_after_it` | runtime | run → refund → park → resume → replay the key → **refused**, and `RunResult` says so | drop `spent_keys=` from `escalate()` (the shipped bug) |
| ″ · `test_parking_for_approval_does_not_hand_the_run_a_fresh_spend_budget` | runtime | `used` survives the park at all four sites | drop `used=` from `park()` |
| ″ · `test_an_escalated_wait_still_refuses_a_key_the_first_wait_already_spent` | runtime | `escalate()` goes through the same helper | restore the hand-written `Suspension(...)` |
| `crates/pact-schema/tests/a_power_no_sentence_can_reach_is_refused_where_it_is_written.rs` · `a_may_entry_no_rule_at_any_of_this_files_moments_can_produce_is_refused` | schema, over **(power × address)** | `may: [stop-the-run]` at `turn.message.after` with only a hiding rule is refused | delete the arm → the fixture loads clean again — **red today** |
| `adapters/python/tests/test_the_closing_answer_goes_through_the_same_rules.py` · `test_a_card_number_in_the_answer_at_the_step_ceiling_is_still_hidden` | runtime | drive the worked example to its step ceiling with a `Script` transport emitting `4111 1111 1111 1111`; assert it is **not** in `result.output` **and not in `result.steps[-1].text`** | remove `chain.run` from the ANSWER path — **red today** |
| ″ · `test_a_rule_stopping_the_closing_answer_does_not_hide_which_ceiling_ended_the_run` | runtime | after a stop there, `result.stopped_by` still names the ceiling and `limits.RAN_OUT` still answers yes | let the stop overwrite `result.halted` |
| `crates/pact-cli/tests/one_vocabulary_for_hiding.rs` · `a_live_stop_and_a_graded_case_use_the_same_words_for_the_same_act` | CLI + runtime | F7's matcher and `evals._breaks` are **one shared function** | give each its own copy |
| ″ · `a_stopping_sentence_at_the_moment_that_sees_the_answer_is_accepted` | CLI | the B7 fixture now has a sentence | — |
| ″ · `the_stop_the_author_wrote_is_the_reply_the_person_reads` | runtime | `result.output == decision.stop` | — |
| ″ · `a_stopping_sentence_is_still_refused_in_the_file_that_may_only_hide` | schema | `always-may: [hide-values]` keeps F7 out of `redaction.yaml` | delete `always-may` from `redaction.hide` |
| `crates/pact-cli/tests/one_rule_at_several_moments.rs` · `a_rule_can_see_what_came_back_and_not_only_what_is_about_to_go` | CLI | an interceptor at `step.tool.completed` loads; a card number a tool returns is hidden | remove `step.tool.completed` from `reaches:` |
| ″ · `the_message_for_a_moment_no_rule_is_handed_says_so` | schema | the wording is *"no rule is handed the run at X"*, not *"nothing ever reaches X"* | restore the old string |
| `crates/pact-cli/tests/nobody_approves_their_own_work.rs` · `an_agent_may_not_be_named_as_the_person_who_approves_it` | loader | both `asked-of:` and `escalates-to:` | delete the arm → `pact waits` prints the self-approval again |
| `crates/pact-cli/tests/one_file_says_what_must_never_leave.rs` · `a_tool_that_reaches_the_internet_is_refused_when_nothing_may_leave` | CLI | the `url` door → error | delete the `reaches-outside:` walk over `tool.url` |
| ″ · `a_connected_server_outside_this_box_is_refused_when_nothing_may_leave` | CLI | the `endpoint` door → error | same, for `resource.endpoint` |
| ″ · `an_address_the_host_resolves_is_not_something_leaving_the_box` | CLI | `host/payments-mcp` under `allow-egress: []` → **clean**, and `examples/refund-desk` still loads | treat every `endpoint:` as egress → the flagship goes red, which is the point |
| ″ · `every_field_that_carries_an_address_out_of_this_box_is_found_from_the_schema` | CLI | the outbound-address set is derived from `reaches-outside:`, never written | hand-write the list |
| ″ · `a_source_no_store_could_recognise_is_refused_where_it_is_written` | schema | `never-from: [the shoe size of a customer]` → error | reopen the list to free text — **red today** |
| `crates/pact-cli/tests/money_that_moves_with_nobody_asked.rs` · `an_argument_typed_money_is_money_moving_whether_or_not_anybody_said_so` | loader | `takes: {amount: money}` + `inspects:` + no `spends-money:` → diagnosed | delete the inference — **red today** |
| ″ · `the_shipped_tree_gains_no_new_diagnostic_from_the_inference` | CLI | all nine example trees stay at zero warnings | the safety net |

## P2

| file · fn | asserts | mutation |
|---|---|---|
| `crates/pact-cli/tests/authoring_surface.rs` · `the_examples_stay_clean_under_deny_warnings` | CI runs `pact check --deny-warnings` over `examples/**` | make one example warn |

## P3

| file · fn | layer | asserts | mutation |
|---|---|---|---|
| `adapters/python/tests/test_the_shapes_a_person_can_answer_with.py` · `test_the_flagship_can_read_the_input_it_declares` | runtime | `photos: list of images` on the real worked example, read end to end | remove the `images` branch — **red today** |
| ″ · `test_every_spelling_the_parser_accepts_the_reader_can_read` | runtime | `set(_SPELLINGS) == set of kinds Shape.read handles` — the cause-level guard, two lines | add a spelling with no branch |
| ″ · `test_a_path_that_climbs_out_of_the_workspace_is_refused` | both ports | `workspace-path` refuses `..`, `/`, `~` | drop the check |
| ″ · `test_a_picture_means_the_same_thing_in_both_ports` | conformance | the declared wire form round-trips identically | change one port's form |
| `adapters/python/tests/test_a_retrieval_score_measures_the_retrieval.py` · `test_a_faithfulness_score_moves_when_the_passages_move` | runtime | two cases identical but for the passages get **different** scores | sever the kwarg at `evals.py:600` — the fix's own red state |
| ″ · `test_a_score_that_grades_the_retriever_reads_what_the_run_retrieved_and_not_what_the_author_typed` | runtime | the three retriever metrics read `RunResult.retrieved` | point them at the authored field → they go constant across two runs, and the test says so |
| ″ · `test_every_keyword_an_adapter_takes_has_an_author_or_a_named_delegation` | cross-cutting | **the mirror of `test_every_field_has_a_reader.py`** | add a kwarg to `evaluate_metric` with no field and no row |
| `crates/pact-loader/tests/waits_the_worked_example_can_produce.rs` · `a_tree_that_parks_says_so_without_anybody_writing_it_down` | loader | `pact waits` emits `requires: [durable-resume]` and `longest-wait: 4h`, derived from the 13 parks | derive it from a written field → the flagship, which writes nothing, stops reporting |
| ″ · `a_workspace_that_parks_may_not_say_it_needs_no_durable_resume` | loader | `durability: none` on a parking tree → **error** | make it a warning |
| `adapters/python/tests/test_portability.py` · `test_what_the_workspace_needs_is_compared_to_what_the_transport_does` | conformance | `durability:` vs `transport.lattice()["durable_resume"]`, reported on `unenforced` | drop the comparison |
| `adapters/python/tests/test_at_most_once.py` · `test_a_scope_this_run_cannot_keep_is_reported_and_not_silently_narrowed` | runtime | one sentence on `unenforced` naming the file, the line, and the line to type | drop the sentence → the double-booking happens silently |
| ″ · `test_the_refusal_says_which_scope_it_was_refused_under` | runtime | built from the declared scope, not the literal `"in this run"` (`at_most_once.py:242`) | hardcode `"in this run"` again |
| `crates/pact-schema/tests/a_missing_companion_says_what_the_missing_setting_is.rs` · `exactly_one_comparison_per_rule_and_the_message_names_the_other_two` | schema | `needs-one-of:` refuses zero and refuses two | make it accept zero |
| `crates/pact-cli/tests/a_gate_that_reads_what_it_may_not.rs` · `a_comparison_is_written_in_the_shape_the_argument_declares` | loader | the `score`-vs-`USD` gate is refused; `more-than: 80` on a `number` loads | delete the shape check — **red today** |
| `crates/pact-cli/tests/a_gate_written_in_one_line.rs` · `a_choice_no_rule_names_is_named_back_to_the_author` | loader | `is-one-of:` over a `one of a, b, c` argument names the uncovered choices | delete the arm |

## P4

| file · fn | layer | asserts | mutation |
|---|---|---|---|
| `crates/pact-loader/tests/digest_equality_for_the_new_kinds.rs` · `a_fifth_kind_written_as_a_folder_and_written_inline_are_one_artifact` | loader | `knowledge/hr/hr.yaml` and inline `knowledge: {hr: …}` hash alike | change the stem-keyed expansion |
| `crates/pact-loader/tests/a_set_of_documents_is_documents.rs` · `a_set_of_documents_with_no_documents_in_it_is_refused` | loader | error, not warning | downgrade it — **passes today with the glob** |
| ″ · `deleting_a_document_moves_the_digest` | loader | `pact show` emits the `$payload` file list; removing a file changes the hash | drop `documents` from `payload_dirs` |
| ″ · `nothing_points_at_a_set_of_documents_is_reported` | loader | free, once `KINDS` is data | remove the derivation |
| `crates/pact-cli/tests/one_file_says_what_must_never_leave.rs` · `looking_things_up_by_meaning_is_a_model_outside_this_box` | CLI | `allow-egress: []` + `looked-up-by: meaning` → error naming `embedder` | delete the fifth binding in `egress.rs` |
| `crates/pact-cli/tests/discovery.rs` · `a_set_of_documents_is_not_something_another_organisation_can_call` | CLI | `pact card` does not project knowledge as an A2A skill | project it → the corpus name appears in the card |
| `adapters/python/tests/test_an_answer_that_had_to_cite_cannot_be_given_uncited.py` · `test_must_cite_on_an_entry_that_reported_unretrieved_fails_the_turn` | runtime | the turn fails; the sentence names the file, the line and the reason | let `must-cite` decorate rather than fail → an agent answers from memory and cites a file it never opened |
| `crates/pact-cli/tests/the_subset_the_second_port_runs.rs` · (extend `REPORTED`) | CLI | `knowledge` has a row; §7.28 list B and README agree | omit one of the four edits → the drift guard fires |
| `crates/pact-cli/tests/authoring_surface.rs` · `the_showcase_directories_stay_optional_and_bounded` | CLI | `knowledge` is in `SHOWCASE`; refund-desk unchanged at 15 | leave it out of both lists → a directory nobody counts |

## The regression guards each fix owes

| fix | guard | ratchet direction |
|---|---|---|
| B15 | the four tables are **derived**; a fifth hand-written table fails by name | replaces vigilance with computation |
| B8 | no field carries both `names:` and `may-be-a-folder:` | computed from the schema |
| B1/B2/B4 | the park register is total **in both directions**, like `DERIVED_FROM_THE_DOCUMENT` | a sixth site in neither map fails |
| B3 | `RAN_OUT` stays answerable after a stop at the closing moment | extends `test_termination_vocabulary.py:231` with a **new case**, not a change |
| B9 | the outbound-address set is derived from `reaches-outside:` | grows by existing |
| B10 | the statically-decidable corpus **only grows** | same shape as `KNOWN_GAPS`, opposite direction |
| A12 | `set(_SPELLINGS) == set of kinds Shape.read handles` | two lines, cause-level |
| A2 | every adapter keyword parameter has a schema field or a named delegation | the **mirror** of `test_every_field_has_a_reader.py` |
| A3 | `needs-one-of:` sets are checked in both directions | — |
| A5 | every declarable scope is enforced or reported | — |
| A8 | a computed requirement and a written one may not disagree | — |
| F7 | one matcher shared with `must-not-contain`, pinned by test | extends `one_vocabulary_for_hiding.rs` |
| D1 | four coordinated edits (TS `REPORTED` + §7.28 list B + README + `SHOWCASE`) or the drift guard fires | — |
| **all new fields** | **no new field name may pass `reader_exists` on a prose or foreign-owned substring** | the adversary's mirror finding: **six of the drafted names pass today with no reader**, including A2's own (` retrieval_context` at `providers.py:630`), `durable-resume` (` durable_resume`, `vercel-transport.ts:85`), `is` (`"is"` in `these_rules(spans.len(), "is", "are")`, `lib.rs:1016`), `documents` (a doc comment at `unnamed.rs:39`), `people` (` people` in prose at `limits.py:227`) and `knowledge` (prose). **Ship the field without wiring it and the honesty test blesses the bug.** |
| all | `KNOWN_GAPS` is currently **empty**; any fix leaving a field unread must add an entry, and `test_known_gaps_only_shrink` forces this register updated in the same change | one direction only |

## What cannot be tested in-tree, plainly

| claim | why not | channel it lands on instead |
|---|---|---|
| a retrieval returned the right passage | PACT does not do retrieval | **`unretrieved`** (new), plus `must-cite` failing the turn |
| `looked-up-by: meaning` was honoured | the host picks the retriever | `unenforced`, naming the file and line |
| a model actually saw the image | no served model (D17) | `unmetered`, naming the transport |
| a DeepEval metric's absolute value | needs DeepEval + a judge model | assert **movement between two cases**; absence reported as absence, per `providers.coverage()`'s existing discipline |
| the host blocked the socket | §4 delegation | PACT refuses the *document*; the host enforces the network |
| cross-process exactly-once | `Ledger` is per-run and in-process | `unenforced`, once `durability:` gives it a place to be declared |
| the index a colleague had is the index I have | no `pact.lock`, no index identity | open question §6 |
| a non-programmer can author this | AC-1.5, never run | the P6 moderated study — blocked on people, not code |

---

# 6. THE OPEN QUESTIONS IMPLEMENTATION WILL SETTLE

| # | Question | The experiment that settles it |
|---|---|---|
| **Q1** | **A3's runtime polarity: does an `is-one-of:` value on no list mean gated or ungated?** Fail-closed protects against a model-chosen (and, with D1, attacker-supplied) string; fail-open is what the author literally wrote. `more-than:` is unambiguously fail-open and must stay. | Write both harnesses behind a flag; run the cold-authoring persona (Marcus, `docs/90-REVIEW.md:552`) on a tier gate with three declared choices, one of which the rule omits. **Settled by which one he is surprised by.** Ship `loader/a-value-this-rule-never-sees` either way — it says the same thing at check time for the closed-choice case, which is the only case where the set is knowable. |
| **Q2** | **Is `looked-up-by:` authorable at all, or should v1 ship absence-only?** It is `expert` here, but a support lead may still meet it. | `examples/patterns/answers-from-documents/` ships with **no** `looked-up-by:` line. If the P3 discovery gate (a support lead reaching the bar with ≤ N check-failures and zero reads of `examples/`) shows nobody adds one, it stays expert. If they add one and pick `meaning` under `allow-egress: []`, the refusal is the teaching moment and the field stays. |
| **Q3** | **Does `unretrieved` need a fifth channel, or is it `unenforced` with a different sentence?** | Build both. Run the P4 fixture (a `must-cite: yes` entry on a host with no index). **If a reader of `unenforced` sends the ticket to the author when the correct recipient is the operator, the fifth channel is earned.** That is the exact test that separated `never_reached` from `unmetered`. |
| **Q4** | **A4's collision: rename the compound (`several <shape>`) or delete the three aliases behind C7's deprecation channel?** | Measure the blast radius of deleting them: `examples/refund-desk/agents/refund-desk/agent.yaml:21` is `photos: list of images`, plus `egress.py:53-56` and `egress.rs:47`. **If C7's deprecation channel exists by then, delete the aliases — one grammar, one meaning. If it does not, `several <shape>` and the aliases stay.** A4 does not ship until this is decided; there is no consumer waiting on it. |
| **Q5** | **Does a knowledge index need an identity, and if so is it `bundle.version:`'s shape?** A parked run resumed after a reindex resumes into a different corpus with no record. `Suspension` declares 19 fields and none identifies the tree or the corpus. | Once P4's `unretrieved` exists: park a run mid-question, change one document, resume. **If the resumed answer differs and nothing anywhere says so, `index-version:` is owed.** The candidate shape is `bundle.version:`'s exact one and its exact help sentence. |
| **Q6** | **Does the retrieval seam need a transport verb (B17)?** `passages-at-most: 5` has nothing to be handed to. The ABI is `lattice()` + `model_call(system, history, tools)` + four optional methods; `run()`'s `SUPPLIED_BY_THE_HOST` is a **closed frozenset** (`harness.py:349-357`) guarded by `test_the_boundary_between_a_document_and_a_run_is_declared`. Tools reach the host through `tool_impls: dict[str, ToolFn]`; knowledge has no analogue. | Wire the `answers-from-documents` pattern against a real RAG runtime through `tool_impls` alone. **If `passages-at-most:` cannot be honoured without a new parameter, B17 is owed and the frozenset grows by one, in the same commit as its guard row.** |
| **Q7** | **A13 (eval dataset pointer) — does A2 make the RAG eval story worse without it?** A case is ~8 lines and the flagship carries 6; `from-these-passages:` puts N passages of prose inline in **every** case, and RAG metrics are per-case statistical measures over hundreds. A13's own complaint (*"2,000 labelled cases become 2,004 committed YAML files"*) is strictly worse once each also carries its passages. | Generate a 200-case RAG suite in the authored form and measure the byte count and the review time against the same suite behind a pointer. **A13 ships if inline crosses whatever the P3 discovery gate sets as one screen.** |
| **Q8** | **A6 (`tries:`) and B13 (contended claim) — does P4's gate stand as written?** It names three shapes; this set answers one, and `93-GAPS.md:81` ranks A6 above A7. | Either design both before the P4 gate is claimed, or **restate the gate to name the one shape it measures.** Not both, and not silence. B13's blocker is specific and worth writing down: there is no observable type meaning *"this is a scarce resource"*, so the exactly-once machinery stays keyed to the word `money`. The candidate second observable is a shape on `takes:`. |

---

# 7. THE HONEST COST

`docs/90-REVIEW.md` was convicted of not measuring its own proposal. Here is the measurement, taken with a script over `spec/schema.yaml` just now.

## Baseline, measured

| | count |
|---|---|
| groups | **43** |
| field entries | **262** |
| distinct field names | **207** |
| distinct **core** field names | **138** |
| distinct closed-choice values | **126** |
| distinct surfaces in use | 8 (S-GOV 77, S-CAP 50, S-EXEC 41, S-CTRL 37, S-GEN 34, S-ROUTE 12, S-TOPO 10, S-META 1) |
| warning rule names | **14**, of which **0** fire on any shipped tree |
| `DELEGATED` rows | **14** · `KNOWN_GAPS` rows: **0** |
| D14 core file budget | **26 / 26** — exactly at bound |
| showcase file budget | **15 / 15** — exactly at bound |

## What this design set adds

### New distinct field names: **11** (all verified absent from the 207)

| name | group | tier |
|---|---|---|
| `knowledge` | workspace | core |
| `documents` | knowledge | core |
| `must-cite` | knowledge | core |
| `passages-at-most` | knowledge | core |
| `looked-up-by` | knowledge | expert |
| `split-by` | knowledge | expert |
| `durability` | workspace | expert |
| `is` | when-this | core |
| `is-one-of` | when-this | core |
| `same-request-key-across` | action | expert |
| `from-these-passages` | case | expert |

**Reused by anchor, not restated: 3** — `use-when`, `do-not-use-when`, `if-unsure` on `knowledge`, taken from `skill` by YAML anchor. They are **not new names** and the author already knows them.

**Names growth: 207 → 218, +5.3%. Core names: 138 → 143, +3.6%.**

### New groups: **1** (`knowledge`). Not 3 — `person` and `requires-of-the-runtime` are cut.

**Groups growth: 43 → 44, +2.3%.**

### New closed-choice values: **16** — *corrected from 17 in the second iteration*

| field | values | n |
|---|---|---|
| `looked-up-by` | meaning · words · meaning-and-words | 3 |
| `split-by` | paragraph · heading · page · whole-file | 4 |
| `durability` | checkpoint · durable-execution (`none` already exists) | 2 |
| `same-request-key-across` | this-run · the-team · the-workspace | 3 |
| `never-from` | tool output · retrieval · the customer · a teammate | 4 |
| `allow-egress` | ~~tools~~ — **already a closed-choice value** | **0** |

**The arithmetic was wrong by one, in the direction that flattered it.** `tools` already appears as a choice value in `learning.needs-a-person-to-approve` (`spec/schema.yaml:2122`) and `bundle.brings` (`:3266`). Verified. The claim *"all verified absent from the 126"* was false for exactly one row.

**Values growth: 126 → 142, +12.7%** (not 143 / +13.5%).

**This is still the fastest-growing column — 12.7% against 5.3% on names.** Three mitigations are built in: `never-from:`'s four values **replace an open text hole** (net −1 unheld field, and it is S-EXEC); D1's value count is 7 rather than the draft's 18 because `connections`, `the-agent-decides`, `the-runtime-decides` and the whole of `file-types:` are cut; and A6's field is refused outright, so it contributes none.

**~~A column growing at 2.5× the rate of its neighbour needs a test, and this set does not add one.~~** *That gap is closed:* §1.19 adds `every_value_an_author_may_type_is_read_by_something_that_is_not_a_test`, sequenced P5. The reason it is a **value** test and not a name test is the one sentence worth carrying out of the second iteration: **a dead field name is inert; a dead choice value is *recommended*** — the checker prints the whole legal list in its own `fix:` line, so a value nothing reads is taught to every author who makes a typo near it.

One thing this column's arithmetic hides: `never-from: tool output` collides word-for-word with the existing part-kind spelling at `context_policy.py:98` — same words, different mechanism. Not a defect; a naming decision to make on purpose rather than by collision.

### New field *attributes* (schema meta — costs Rust, not author vocabulary): **4**

`may-be-a-folder:` (B8) · `needs-one-of:` (A3) · `satisfied-by:` (B15) · `reaches-outside:` (B9). Each costs `crates/pact-schema/src/from_doc.rs` (parse) + `crates/pact-schema/src/lib.rs` (check) + one diagnostic wording. **An author never types one.** Three of the four *remove* a hand-written Rust table, which is the R6 bargain (*"a check the product used to lack is DATA rather than a Rust `if` per pairing"*) taken four more times.

### New types: **1** — `workspace-path` (A12), and `like-the-argument` (A3) is a resolution rule on `more-than:`/`is:`/`is-one-of:` rather than a new type name.

### New diagnostics: **9**

`loader/power-nothing-can-use` · `loader/approves-its-own-work` · `loader/reaches-outside-the-box` · `loader/parks-with-nothing-to-resume-it` · `loader/knowledge-with-no-documents` · `loader/compared-in-the-wrong-shape` · `loader/a-value-this-rule-never-sees` · `schema/missing-one-of` · plus `loader/never-offered` becoming *fixable*, which is a repair not an addition.

**Two of the nine are warnings** (`a-value-this-rule-never-sees`, `money-that-moves-with-nobody-asked` extension), taking the warning surface from 14 to 15 — and `--deny-warnings` is sequenced a phase later precisely because of that.

**Second-iteration correction: 9 → 11.** Relocating A5's dead `needed-when:` into `crates/pact-loader/src/scope.rs` (§2) costs two — `loader/a-scope-with-nothing-to-keep-it` and `loader/a-scope-with-nobody-in-it`. It does **not** cost the two A6 would have added: `loader/a-try-that-can-do-something` and `loader/more-ways-than-there-are-steps` are refused with the field, and the second was a measured false refusal. Warning surface 14 → 16.

### New honesty channel: **1** — `unretrieved`, taking the four to five. New `DELEGATED` rows: **6**, taking 14 to 20 (**+43%**, from one fix). Both are costs, both are written down rather than silent, and Q3 is the experiment that decides whether the fifth channel is earned.

**And one cost this document was not counting at all.** `DELEGATED` goes 14 → 20 → **21**, because repairing `reader_exists` (P0 item 5) surfaces `state.forget-after` as a tenth field-level orphan. Alongside it sit `NOTHING_READS` (~22 rows) and `HANDED_ON` (~4): **roughly 47 rows of "somebody else does it" or "nothing does it", written across this plan, against a shipped bar of `< 30` for the one register that has a bar.** The registers are how this project stays honest, and this set grows them faster than it grows the schema. Whether that bar moves or the work shrinks is a decision, not an oversight — and it belongs in §6 with the other open questions.

### The no-code bar

**The D14 bar does not move.** D14 is a multi-agent system with custom MCP tools, eval cases, SLO limits and learning (`docs/01-DECISIONS.md:124-126`) — one file, 34 lines, **29 keys** per `docs/93-GAPS.md:162`. **None of the 11 new names is in it.** All four core-tier additions (`knowledge`, `documents`, `must-cite`, `passages-at-most`, `is`, `is-one-of`) are optional and absent from every path through that bar.

**A new bar appears, and it is the number to hold this set to.** D14's consequence clause makes the RAG author a D13 persona:

| the RAG author's bar | keys |
|---|---|
| `knowledge/hr-handbook/hr-handbook.yaml` — `description:` + `must-cite: yes` | **2** |
| `knowledge/hr-handbook/documents/*.md` — the files themselves | **0** |
| `agents/helpdesk/agent.yaml` — `uses: [hr-handbook]` added to a file that exists | **1** |
| **total** | **3 keys and a folder** |

Of those three, **every one is held to something**: `description:` is `required: yes`; `must-cite: yes` fails the turn when the corpus was not read; `uses:` resolves against the workspace and teaches the kind when it misses; and the *absence* of documents is refused. **The draft's version had five core lines of which the checker held none.** That difference is the whole redesign.

### File budgets

Both are at bound — 26/26 and 15/15, measured. The RAG example lands in `examples/patterns/answers-from-documents/`, which costs **neither**, and `knowledge` joins the `SHOWCASE` list in the same commit so it can never be an uncounted directory.

### What this set does *not* buy, stated plainly

**~~It answers 1 of the 3 shapes P4's own gate names.~~** *Superseded by the second iteration.* It answers **3 of 3**, and two of the three answers are refusals with their alternatives named:

| shape | answer |
|---|---|
| **A7** retrieval | `knowledge:` ships — §1.16 |
| **A6** self-consistency | **refused** — `examples/patterns/quorum/` already ships the shape, with independent `Meter`/`Ledger` per member. §1.18 |
| **B13** contended claim | **deferred with a fixture** — `same-request-key:` + `same-request-key-across:` *is* mutual exclusion, measured across two runs and two agents. What is missing is a lease. §D4 |

**A refusal with its alternative named and measured is an answer. A silence is not.** That distinction is the one this document was convicted on, and closing the two silences cost **zero new field names, zero new groups and zero new choice values** — which is itself the finding: both gaps were expressible in what already ships, and the first iteration did not check.

**What genuinely remains unbought**, now that the register is honest:

- **A lease** — releasing a claim, seeing who holds it, expiring it. `Ledger` has no release and no introspection. Nobody in this literature has built one; it is deferred with a fixture rather than designed badly.
- **Whether `quorum/` is enough.** A6's re-admission fixture is *a case `quorum/` cannot express*. Nobody has written one. Until somebody does, "PACT lacks self-consistency" is a claim this plan has now measured and rejected.
- **The register bar.** ~47 delegation rows against a `< 30` bar. See §6.
- **The `the-team` / `the-workspace` seam.** §1.13 ships them enforced at check time only. Once `scope.rs` compares them as literals they become "lit" to the P5 growth guard while nothing at run time honours them — the exact false-liveness that guard exists to detect, arriving through a field in this set. `this-run`, the only scope actually enforced, is the one that stays dark. **That inversion is the sharpest thing the second iteration found and this plan does not fix it.**
---

# 9. WHAT HAS LANDED — P0, verified

**State at the end of P0:** Rust 67 suites / 708 tests, clippy clean · Python 1204 passed, 5 skipped · all ten shipped trees `OK — loaded cleanly`, zero new diagnostics. Every item below has a named test whose named mutation was run and observed red.

| # | Work | Test | Mutation observed |
|---|---|---|---|
| 5 | **`reader_exists` repaired** — key lookups matched in the whole file, identifiers only in a corpus with comments *and string literals* removed; `tests/` directories excluded | `a_field_named_only_in_a_sentence_the_checker_prints_is_not_a_field_anything_reads` · `a_fixture_that_writes_a_field_is_not_a_runtime_that_reads_it` | restoring the `" {snake}"` pattern → red; counting `tests/` → red; dropping multi-line Rust string handling → red |
| 2 | **B15 — all four loader tables become data.** `satisfied-by:` added to the schema and checked in both directions; `available.rs` walks the schema's own `names:` edges; `derive.rs` and `bundles.rs` compute their lists; `unnamed.rs` keeps its prose and gains a held set | `the_fix_a_never_offered_warning_offers_is_a_line_an_agent_can_have` · `every_collection_a_line_can_name_is_warned_about_or_excused` · `what_a_bundle_may_bring_is_what_a_workspace_can_hold` + 6 more | pointing a satisfier at `knows` → **the specification refuses itself**; deleting the `resources` row → red; dropping `agents` from `brings:` → red |
| 3 | **A contributed kind the schema does not know is refused, not skipped** | `a_contributed_kind_the_schema_does_not_know_is_refused_and_not_skipped` · `a_bundle_that_quietly_starts_supplying_an_agent_is_refused` | reverting the arm to a bare `continue` → red |
| 1 | **The type-the-fix test generalised** from 2 keys to every key the flagship writes | `every_fix_that_names_a_setting_leaves_a_tree_that_checks_clean` | a suggester that offers a real-but-wrong name → **81 fix lines** caught, against 2 before |
| 4 | **Port parity** — `judged:` with no `graded-by:`, and a metric `uri:` with no provider, are now decided at check time in the runtime's own words | `a_rule_decided_by_reading_the_answer_needs_somebody_to_read_it` · `the_two_ports_refuse_a_providerless_metric_in_the_same_words` · `whether_this_machine_has_the_provider_is_left_to_the_machine` | disabling either check → red |

## 9.1 Two places this plan was wrong, found by implementing it

- **§1.1 said `loader/nothing-points-at-it` should start covering `skills`.** It should not. `crates/pact-loader/src/unnamed.rs:27-31` states the omission as a decision with a reason — *"a skill nothing lists is a written procedure somebody may be about to attach and reads perfectly well on its own"* — and the plan read that absence as an oversight. What was genuinely missing is that the decision was **prose**: nothing held the set. It is now `OMITTED`, five rows with reasons, and a test that every collection something can name is either warned about or excused.
- **§1.2(a) listed `x-run-arbitrary: yes` as a port-parity gap.** It is not. The `x-` prefix is the extension point that survived the deletion of `open:`, documented at `crates/pact-schema/src/lib.rs:360-365`, and it is per-field and per-author by design. Two of the three named classes were real; this one was a decision.

## 9.2 What the work added that the plan did not anticipate

- **`reader_exists` was broken in a way nobody had measured.** Its `f" {snake}"` pattern matched English prose inside diagnostic *string literals* — not comments — so `tries`, `knowledge`, `documents`, `claim` and `owner`, five of this plan's own new names, were already reported as read. The growth test's stated corpus fix (strip comments) would not have caught a single one.
- **Six fields were unread and reported as read.** `figure.provenance`, `provenance.as-of`, `port.through`, `resource.auth`, `state.lasts`, `state.forget-after` — now delegated with reasons. `DELEGATED` is 20 of its bar of 30.
- **`resolve.py::_window` does not enforce what its own docstring claims.** It refuses a bare integer and then reads only `value:`, so a catalogue figure with `value:` and no `provenance:` is accepted. Measured directly. Recorded in the delegation reason rather than fixed here, because it is not this phase's item.
- **`available-when:` was never exercised by any shipped tree** — zero occurrences across `examples/`. The condition that could not hold had also never been run.

---

# 10. P1 — SAFETY. What has landed, verified

**State:** Rust 70 suites / 724 tests, clippy clean · Python 1229 passed, 5 skipped · all ten shipped trees clean. Every row's named mutation was run and observed red.

| # | Work | Reproduction that justified it | Mutation observed |
|---|---|---|---|
| 5 | **B8 `may-be-a-folder:`** — the map-of-prose exemption gated on the FIELD, not the type | `loop: carefull` refused with the real loops offered; `loop: {banana: purple}` **"OK — loaded cleanly"**, skipping name resolution on all 22 fields that carry `names:` | reverting to the type-only gate → red |
| 6 | **B1/B2/B4 `_park_state()`** — one helper fills the whole durable block; `escalate` keeps `spent_keys` | `tool-calls-at-most: 5` → **3 calls before an approval park and 4 after it: seven against a ceiling of five.** `Meter.restored` falls back to the step index for STEPS alone, so seconds, tool calls, tokens and money all restarted at zero | removing `used` from the helper → red; dropping `spent_keys` from `escalate` → red |
| 7 | **`loader/power-nothing-can-use`** — over (power × moment), not over sentences | `may: [hide-values, stop-the-run]` at `turn.message.after` → **"OK — loaded cleanly"**. R24's defect inside the list R24 was applied to, against §G5's own invariant | — (the check *is* the assertion; its fixture had to be rewritten when F7 gave `stop-the-run` a sentence there, which is the check working) |
| 8 | **B3** — the closing answer goes through `turn.message.after` | `_finish`'s docstring states the guarantee verbatim: *"a redaction rule cannot be escaped by finishing from a stage rather than by running out of steps."* Running out of steps was the escape | removing the chain call → red. The ceiling stays reported when a rule stops it, or `limits.RAN_OUT` becomes unanswerable |
| 9 | **F7 — the sixth sentence** `if the answer mentions "…", stop and say "…"` | **The #1 gap from the persona trial.** Every ceiling, gate and redaction bounds what an agent DOES; nothing bounded what it SAYS. Both stopping sentences count tool calls and are pinned to `step.tool.before` | dropping the answer-carrying gate → red; `evals` ceasing to share `said_any` → red |
| 10 | **`step.tool.completed` into `reaches:`** | Hiding was **one-directional**: the card number the agent typed was masked, the same card number a tool returned was not — and a tool result enters the history and is read back next turn | the harness ceasing to hand the chain the result → red |
| 11 | **B11 — nobody approves their own work** | `asked-of: [desk]` on the question gating `desk` → "OK — loaded cleanly", and `pact waits` published `"asked-of": ["desk"], "escalates-to": ["desk"]` — a gate where the thing checked does the checking and escalates to itself on a timer | checking only `asked-of` and not `escalates-to` → red |

## 10.1 Three things the work changed that the plan did not foresee

- **`_ran_out` needed `given` as well as `chain`.** The budget-park site was missing `granted` not by oversight but because the grants were never passed in — so a person who approved a connection before a ceiling was asked again after it. Both are now required keyword arguments, for the reason `once` already was: a caller that forgets loses a guarantee in silence.
- **`step.tool.completed` must NOT carry `which_tool`.** The obvious modelling (the payload has `name`, so set the flag) is wrong twice over: the flag's contract is that a call can be *counted* there, which needs `so-far`; and counting in order to prevent a call has to happen before the call. Stopping after the money moved is not stopping.
- **F7 invalidated the `power-nothing-can-use` fixture, correctly.** `stop-the-run` at `turn.message.after` stopped being a defect the moment a sentence existed for it. A check computed from the vocabulary noticed; a list of known-bad pairs would not have. The fixture moved to `send-elsewhere` and gained a test that the *old* case is now silent.

## 10.2 What remains in P1

B9 (`reaches-outside:`), `never-from:` closed, and B12 (infer `spends-money`). Then P2 (`--deny-warnings`), P3 (the small additions), P4 (`knowledge:`), P5 (the growth guard).

---

# 11. P2 AND P3 — landed and verified

**State:** Rust 73 suites / 744 tests, clippy clean (debug and release) · Python 1262 passed, 5 skipped · all nine shipped trees clean under `--deny-warnings` · `scripts/test-all.sh` green end to end including all seven adapter targets and the TypeScript port.

| Phase | Work | Reproduction | Mutation |
|---|---|---|---|
| P2 | **`--deny-warnings`** + the gate script now checks **every** shipped tree, not just the flagship | Eight orchestration patterns were checked by nothing. A warning meant a shipped example teaches a shape the checker disagrees with | disabling the flag → red; misspelling it → still refused by name |
| P3 | **A12 `workspace-path`** — `images`, `audio`, `file` were accepted by `_SPELLINGS` and fell through `Shape.read` to `raise Rejected` | **The flagship could not read its own declared input**: `photos: list of images` at `agent.yaml:21` | removing the branch → 10 of 15 red |
| P3 | **A2 `from-these-passages:` + `RunResult.retrieved`** | `evaluate_metric` has declared `retrieval_context` since it was written; its one caller never passed it, so `deepeval:faithfulness` loaded by name and could never score | ceasing to pass it → red |
| P3 | **A8 `durability:`** + the contradiction check | `pact waits` finds 13 waits in the worked example, so `durability: none` is a claim the tree disproves — which is why the field is worth writing and `durable-resume: yes` was not | — |
| P3 | **A5 `same-request-key-across:`** with a scope-aware refusal | The sentence said *"already ran in this run"* whatever the author wrote; on a workspace scope that sends somebody through the wrong transcript | each scope's phrase asserted separately |
| P3 | **A3 `needs-one-of:` + `is:` + `is-one-of:` + the shape check** | `arg:` carried `needs-also: [more-than]`, so `{arg: reason, is: fraud}` was refused — a rule written correctly. And a score gated by `more-than: 200 USD` loaded clean, giving a live human gate comparing a score to dollars | both mismatch directions red; `needs-one-of` red |

## 11.1 What P3 cost that the plan did not price

- **A3 broke the currency guarantee and the suite caught it.** `more-than:` was `type: money`, and that type carried TWO facts: the shape an author must write, and the fact that `currency.rs` must hold it against what the price list can price. Making the type permissive silently dropped the second, reopening `more-than: 200 JPY` gating at about 1.30 USD. Restored with `may-be-money:` — a fourth attribute, and the honest one: *this is money when the thing it compares is money*.
- **`is:` was falsely lit by the repaired reader instrument.** `\bis\b` matches Python's `is` operator in comment-and-string-stripped code — exactly the one-word residual the repair documents. `is-one-of` was correctly reported. Neither was wired; both now are, in **both** halves of the gate, because `_atom_holds` chooses the wording a person reads and `_atom_stops` decides whether the call is withheld, and two readings of one rule is how somebody gets asked about a call that was never stopped.
- **A3's fixture needed `inspects:` widened.** The pre-existing "a rule may only look at what the action offers" check fired first, and the test would have been asserting that instead.

---

# 12. P4 AND P5 — landed and verified. The plan is complete.

## 12.1 P4 — `knowledge:` (A7), in both ports

The commonest enterprise shape — an agent that answers out of a set of documents
and says which one it used — could not be written at all. It ships as its own
kind, not as a `skill`, and the argument is about **reviewing**: somebody who has
read a skill has read every word the model will see, and `passages-at-most: 3`
means nobody knows at check time which three. A skill is determinate and this is
not, and a reviewer has to be told that rather than have it hidden behind a
reused word.

| What | Measured |
|---|---|
| The construct | `knowledge/<name>/<name>.yaml` with a `documents/` folder beside it. Digested by the payload walker, so `pact show` emits each file with its type and size — which is what makes "these are the documents" checkable rather than asserted |
| **A folder, not a glob** | With a glob, `documents: /etc/passwd` and `documents: ../../../../etc/**` both printed "OK — loaded cleanly", and so did a glob matching zero files. There is no path type in this language, and a glob's file ORDER is load-bearing for a digest the loader promises is reproducible |
| The teaching diagnostic | A typo in `uses:` now prints ``there is no such entry in `tools:`, `skills:` or `knowledge:` `` and offers `knowledge/<name>/<name>.yaml` — **no Rust change**, and it fixed the ungrammatical `.join(" or ")` the same message used in its own first half |
| `must-cite:` | **Fails the turn** on a corpus nothing retrieved, before a single model call. Answering anyway gives an answer from what the model already knew, citing a document it never opened — the worst outcome available and the one that looks most like success |
| `unretrieved` | The fifth honesty channel. A fifth rather than a fifth use of `unenforced`, for the reason `never_reached` is not `unmetered`: *the rule could not be evaluated* sends the author to the rule; *the corpus was never read* sends them to whoever runs it |
| `looked-up-by: meaning` | Refused under `allow-egress: []`. `embedder` was the one role with no producer anywhere in the tree; this is its first, and it is the one that matters — a hosted embedder sees every question a customer types |

**Four instruments caught obligations the design had not listed**, and every one
was a real hole rather than a formality: the stage/agent `may-use:` asymmetry
(an agent could use a corpus, no loop stage could narrow to one), `bundle.brings`
and `unnamed.rs`'s excused set (both B15 guards, both correct), the
loader-to-adapter boundary, and the §7.28 port-parity register plus the README
claim it holds.

**The port divergence was real and is closed.** With `knowledge` absent from the
conformance payload, Python refused a `must-cite:` corpus it could not read and
Node answered. The TypeScript port now refuses identically, before a model call,
in the same words — and the payload carries the key, which is what let the driver
see it at all.

## 12.2 P5 — the growth guard, and the defect it was written by finding

**A dead field name is inert. A dead choice value is *recommended*** — type a
near-miss and the checker prints the whole legal list back in its own `fix:`
line. 147 values across 45 lists, and nothing bounded them.

Sequenced last, deliberately: run first it is red on most of a plan's new values
on the day they land, because the value ships in the schema before the arm that
reads it. Run last it is a guard.

It found `limits.measured-at`. `mean` and `max` are two of its six values and
neither is a percentile, so both fell to a dict default of `0.95` and were printed
under the author's own word. **Over samples 1..100, `measured-at: max` reported
`max=95.00s` when the true maximum is 100.0, and `mean` reported `mean=95.00s`
when the true mean is 50.5.** Somebody who writes `max` wants the worst case; they
were shown a number that hides it, labelled with the word they chose. Both arms
now exist and five statistics over one sample set no longer agree.

## 12.3 Production

- **LICENSE.** `Cargo.toml` said `license = "Apache-2.0"` and the repository had no
  licence file. It has one now, and every crate's publish metadata (`license`,
  `description`, `repository`) is complete.
- **`cargo package`** succeeds for `pact-diag` and fails for the rest only on
  publish order — each depends on a sibling version not yet on crates.io, which
  resolves as they are published bottom-up. Not a defect.
- **A test wrote into the repository.** `pact_adapters.exploding` was pointed at
  `no-such-dir/out`, and it does what it says: running the suite expanded a
  workspace into the repository root and left it there. A test that dirties the
  tree it is testing makes `git status` lie about what somebody changed. It now
  writes to a temp directory.
- **One normative artefact, said out loud.** `docs/20-ARCHITECTURE-DRAFT.md` now
  opens by stating that `spec/schema.yaml` is what PACT is, that the draft is a
  design record describing constructs the schema does not have, and where the
  measured gap is recorded. That is the "two PACTs" finding of `90-REVIEW.md`
  closed as far as a document can close it.
