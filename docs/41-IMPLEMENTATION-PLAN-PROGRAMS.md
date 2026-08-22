# PACT — Implementation Plan: Programs, Arguments, and Dynamic Structure

**Date:** 2026-08-14. **Status:** Plan — companion to `docs/27-PROGRAMS-AND-DYNAMIC-STRUCTURE.md`
(the agreed proposal, with its two owner-approved amendments and Design C).
Nothing lands until its phase's tests exist and fail first. Where this plan and
`spec/schema.yaml` disagree, the schema is what PACT is until the phase that
changes it ships.

**Builds, in one sentence:** named values with one-write reuse; typed-argument
templates on every `based-on:`; payload digests and a governed `.pactignore`;
the dynamic-bottom rule for agents-as-values; author-widened learning
(`may-also-change:` / `applies-up-to:`); the `program` kind with a sandbox
resource, declared egress, and fuel; programs as a fourth capability kind wired
through tools, memory, metrics, questions, interceptor sentences, routing
(`decided-by:`), and CodeAct; and, last, the self-authored-tool lane.

---

## 0.1 Status — what is built, and where the plan was wrong

**Built and committed** (`06ac849` … `ffd1540`, suite green at every step):

| Phase | State | Commit |
|---|---|---|
| P0 the inertness net | done | `06ac849` |
| P1 `values:` | done, then hardened twice | `06ac849`, `498875c`, `ffd1540` |
| P2 `expects:`/`with:` | done, then hardened twice | `06ac849`, `498875c`, `3aace86` |
| P3 payload digests | done | `2b3b735` |
| P4 dynamic-bottom rule | done, both halves; base door closed later | `bf9a29b`, `3aace86` |
| P5 learning widening | done, NOT as written — see below | `295db17` |
| P6 `program` kind + sandbox + egress role | done | `f1fbdc8` |
| P7 executor | done as a SEAM, not an engine — see below | `c18fa28` |
| P8 capability wiring | waves 1–4 of 8 | `26993a1`, `3985b5d`, `6a62b4e`, this |
| P9 self-authored lane | not started | — |

**Three places this plan was wrong, and what was built instead.**

*P5 named a class vocabulary the product does not have.* It proposed
`learning.applies-up-to: CLASS-2`; `classify()` answers LOW, HIGH or UNKNOWN,
and UNKNOWN is treated as HIGH. A four-class dial in front of a three-value
judgement would have been a second spelling of one decision — R59's mistake, in
the file R59 is about. The real gap was that `may-improve-on-its-own:` is
`tier: core`, offers four words, and three of them named fields
`CAN_BE_APPLIED` could not apply: the author's grant was unusable. That is what
was closed.

*P7 said "the wasm executor".* Building one means fetching a runtime into the
core of a project whose D17 promise is that everything runs air-gapped, or
vendoring one the portable artifact cannot keep current. A program runner is a
transport, and every transport here is host-supplied: `Transport` and
`tool_impls` are both in `SUPPLIED_BY_THE_HOST` and nothing in `src/` builds
either. So P7 shipped the seam, the metering and the honest absence — a run with
no runner names every program it could not start, before the first call.

*The plan assumed its own analysis was sound.* It was, mostly — but five defects
in P1/P2 were found by adversarial audit rather than by the tests written for
them, and **two of those were introduced by fixes for the other three**. The
lesson is recorded where it belongs, in the protocol below: a fix aimed at one
case must be re-checked against the case it was fixing before.

**P8's waves, individually:** 1 `uses:` takes a pure program · 2 `bind:
remembers.<name>` and `remember-as:` · 3 the `program:` metric scheme · 4
`question.checked-by:` · 5 `action.projects-with:` · 6 program-holed interceptor
sentences · 7 `decided-by:`/`may-go-to:` · 8 `does: run-code` + codeact. Four
built, four to go.

**Known open, recorded rather than dropped:** a figure inside a sentence
(interpolation — a new capability, not a defect); list-valued pattern arguments;
templates reading inside `x-` blocks (AD-14); substitution provenance in the
LoadReport (P2's own exit gate); P8 waves 2–8; P9.

## 1. The TDD protocol, calibrated to this repo

Extreme TDD here is not a slogan; the repo already runs on four standing
guard-rail suites that behave as always-on failing tests. The protocol per
work item:

1. **Fixture first.** Every behaviour lands as an on-disk tree under
   `tests/trees/` (Rust, through the real binary) or a spec dict in
   `adapters/python/tests/` — never as a hand-built `Value::Map` alone. This
   is C8 §7 D-3's lesson, already paid for once.
2. **Red before green.** The test is written, run, and observed to fail for
   the *stated* reason before any implementation line. A refusal test always
   ships with its **positive control** — the same tree minus the new line
   still passing — per the pattern in
   `crates/pact-schema/tests/a_base_may_leave_required_lines_unwritten.rs`
   ("the silence above proves nothing unless the same block without
   `base: yes` still draws the ordinary refusal").
3. **Inertness is a test, not a claim.** Every runtime change ships a
   byte-equality trace test proving a workspace that writes none of the new
   lines behaves identically — the pattern pinned by
   `test_an_agent_without_the_line_is_never_asked_to_count`
   (`adapters/python/tests/test_asking_yourself_has_a_bottom.py:184`),
   including its sharpest form:
   `assert "<new-key>" not in json.dumps(default.trace())`.
4. **Every diagnostic through the real door.** New rules are tested by
   running `pact check` on a broken copy of a fixture and asserting the
   where/what/why/how of the message (the
   `authoring_surface.rs::a_reference_to_something_this_workspace_does_not_have_is_caught_where_the_author_is`
   pattern). A diagnostic without a typeable fix cannot be constructed
   (`pact-diag`'s constructor signature) — rely on that, don't re-test it.
5. **The standing suites are the safety net; extend them, never bypass:**
   - `governance_is_complete` (`crates/pact-cli/src/main.rs:406-429`) — a new
     field without `surface:`+`tier:` refuses the whole run. Every phase that
     touches `spec/schema.yaml` inherits this test for free.
   - `unnamed.rs::every_collection_a_line_can_name_is_warned_about_or_excused`
     (`crates/pact-loader/src/unnamed.rs:256`) — a new collection fails the
     build until its row exists. This is TDD enforced by the compiler.
   - The boundary registry (`DERIVED_FROM_THE_DOCUMENT` /
     `SUPPLIED_BY_THE_HOST`, `harness.py:385-424`) — a new `run()` parameter
     in neither map fails the suite.
   - Reader-coverage: `test_every_field_has_a_reader.py`,
     `test_nothing_vanishes_between_the_file_and_the_document.py`,
     `test_every_value_an_author_may_type_is_reachable.py` — a field that
     loads and does nothing fails. Every schema addition must arrive with its
     reader in the same phase.
   - Cross-port: `test_portability.py:481-558` holds field names across the
     two ports; anything unported must land on the TS port's `notDoneHere` /
     `unenforced` list *with a test asserting the sentence*.
6. **Ledger before merge.** A phase that touches a refusal row amends
   `50-NOT-COPIED.md` in the same change, the way §8.3 records R29's
   withdrawal: the row is amended, never deleted, and
   `deliberate_refusals.rs` / `eve_inventory.rs` must stay green.
7. **Full suite green per phase**: `./scripts/test-all.sh` (Rust + both
   adapter ports, offline) plus `--deny-warnings` on all example workspaces.
   No phase merges on a subset.

---

## 2. Master blast-radius matrix

Abbreviations: **S** = `spec/schema.yaml`, **L** = `crates/pact-loader`,
**Sc** = `crates/pact-schema`, **C** = `crates/pact-cli`, **Py** =
`adapters/python/src/pact_adapters`, **TS** = `adapters/typescript`.

| Item | Spec surface touched | Rust | Python | TS | Standing tests that fire | Ledger/decisions touched |
|---|---|---|---|---|---|---|
| **P1 Values** | new `values:` collection + `value` group (S); `{use:}` legal in scalar position everywhere | new `L/values.rs` pass; 4 collection sites (`C/main.rs:820-840` `node_is_collection`, `L/unnamed.rs` KINDS, `Sc/lib.rs:2228` `file_for`, `L/policy.rs` `kind_stems`) | none (load-time; ports consume the expanded document) | none | `unnamed.rs`, `governance_is_complete`, digest tests | none refused; classify-on-resolved principle (research note) now normative |
| **P2 Templates** | `expects:` field on the 13 collection kinds (S); `with:` loader-only beside `based-on:` | `L/derive.rs` (substitution after merge, strip `with:`), hole scanner, shape coercion via `Sc/coerce` | none | none | derivation tests, `a_restated_block_says_what_it_dropped.rs` must stay green | R17 unaffected (bundles stay folders); AC-1.4 digest-comparability extended |
| **P3 Digests + ignore** | none (S unchanged) | `pact-doc` `FileRef` +`digest`; `L/lib.rs:771-980` payload walk hashes; `.pactignore` into LoadReport + digest | none | none | golden-manifest tests; every workspace digest moves (recorded) | EXP-8/EXP-10 land (designed, unbuilt); closes the flagged laundering channel (`L/lib.rs:89-105`) |
| **P4 Dynamic bottom** | help text on `agent` shape rows (S) | `L/teams.rs` sixth base door + receivable-without-figure warning | `harness.py` delegate admission beside `:3001-3015`; value→`ask_member` wiring at `:723` / `:2965-3070` | declared absent (`notDoneHere`) | boundary registry; inertness trace; `a_base_is_something_to_build_on.rs` extended | closes the fuel/shape gap named in 27 §B2; no refusal touched |
| **P5 Learning widening** | `learning.may-also-change:`, `learning.applies-up-to:` (S) | none (fields are data; egress untouched) | `learning.py`: derive apply-set from opt-in × class; keep union-only; X18 escalator ceiling | n/a | reader-coverage; existing learning tests; drift tests | D22(b)/(c) partially unlocked; AD-76/77/82 preserved by test |
| **P6 Program kind + sandbox + egress** | new `programs:` collection, `program` + `program-fuel` groups; `resource-kind:` gains `sandbox` (+`engines:`, `asks-to-run:`); `allow-egress:` gains `programs`; `action.program:` (S) | 4 collection sites; `L/reach.rs` untouched (tool still reaches one place); new `L/programs.rs` checks (names resolve, fuel present, reaching program under empty egress refused — pattern of `C/egress.rs`) | none yet | none | `unnamed.rs`, egress tests (R30 pattern), `eve_inventory.rs` | **R58 amended** (return condition met: fields only it needs); **R42 amended** (letter kept: no script named for PACT to run; executor is the host's declared, consent-gated resource); egress stays one story (B9 lineage) |
| **P7 Executor + fuel** | none (S done in P6) | none | `program_executor` host seam (registry!); wasm engine (vendorable dep, imported inside function like `mcp/client.py`); fuel → `_ran_out` path; trace rows | `unenforced` declaration + test | boundary registry, trace-shape tests, `test_portability.py` | D17 (engine local), D26 (overhead benchmarked), §7.28 coverage list amended |
| **P8 Capability-kind + vocabularies** | `uses:`/`stage.may-use:`/`variant.may-use:` `names:` lists gain `programs`; `action.remember-as:`; `bind:` second source; `question.checked-by:`; metric `program:` scheme; `action.projects-with:`; interceptor `forms:` + program sentences; `stage.then.decided-by:` + `may-go-to:`; `does: run-code`; `spec/loops/codeact.yaml` + both `or-one-of:` lists (S) | `L/approvals.rs` (program actions gated), `L/reachability.rs` (`may-go-to` reachable), `Sc` forms machinery (data), `L/teams.rs` (may-use programs) | `ir.py` (offering), `harness.py` (bind sources, remember-as guard, projection site, dispatch branch for `run-code`, `_where_next` decided-by), `providers.py:169-174` third scheme, `questions.py` checked-by, `interceptors.py` AUTHORABLE + `WIRED` | per-feature: port or declare | reader-coverage, `test_typed_questions.py:380` one-list test, interceptor power tests (`power-nothing-can-use`), reachability tests | **R24 partially withdrawn** (rewrite powers become authorable *when program-backed* — recorded like R29); F1 stance preserved via badge exclusion; R9 untouched (projection is on actions, not tidy steps); FR-6.1.5 CodeAct lands; R16 untouched (no model-authored structure) |
| **P9 Self-authored lane** | `tool` gains `composite:`; approval-surface wording; revocation fields (`supersedes`, `revoked-by`) (S) | resolver-side refusal of revoked digests | `learning.py` proposal kinds for tools; AD-85 acceptance path | n/a | learning suite, QUEUE tests | AD-85, AD-89, FR-6.2.5/M7.4 land |

**Schema growth budget:** 2 new collections, 3 new groups (`value`,
`program`, `program-fuel`), ~14 new fields on existing groups, 2 enum
widenings, 2 `names:`-list widenings, 1 new metric scheme, ~4 new sentence
forms, 1 new stage kind, 1 new loop file. Every field: `surface:`, `tier:`,
`help:` — enforced.

---

## 3. Conflict and integration analysis

Checked item-by-item against the binding decisions and the ledger. Three
kinds of contact, none a conflict:

**(a) Reopenings with their recorded conditions met.**
- **R58** (`resource-kind: sandbox` deleted because no field only it would
  use): returns carrying `engines:` and `asks-to-run:` — the row's own
  return condition. Ledger row amended, not deleted.
- **R42/R60** (a tool naming a script for PACT to run): the letter is kept —
  no `runs-as:`, no command, `pact check` still opens nothing. What changes
  is recorded as an amendment: a tool may name a *program* whose executor is
  a *declared, consent-gated host resource*, exactly the `mcp-server` shape.
  The original reason ("check would decide whether a script is safe") is
  answered structurally: check decides declaration-completeness only.
- **R24** (interceptor rewrite powers not authorable): partially withdrawn —
  authorable **only** through a program-holed sentence naming an in-tree,
  digested, fueled program. The row gains the same "provided, and by §0's
  rule the row must say so" treatment as R29.

**(b) Refusals deliberately NOT touched** (the plan's tests assert their
survival): R5/FR-1.5.6 (a CI test already asserts the validator opens no
socket and spawns no process — extend it to assert the same *with programs
present in the tree*); R9 (tidy steps stay closed; `projects-with:` lives on
actions); R16 (no model-written structure; CodeAct code has no structural
authority); R45 (no regex/jsonpath in redaction — program recognisers are
named references, not inline patterns); AD-14 (`x-` never emitted); F1's
no-code stance (`decided-by:` excluded from the `no-code` badge, asserted by
a badge test); F4 (no free variables — `remembers.` reads are declared
bindings); Y4/AD-16 (no expression grammar anywhere in any new field).

**(c) Decisions every phase must satisfy, with their per-phase test:**
D14 — a badge test per phase: the worked no-code example must keep its badge
untouched through all nine phases (its tree never changes). D17 — the
air-gap suite runs the wasm fixture with the network namespace disabled.
D15 — export tests: a program-carrying tree round-trips; nothing lands as an
out-of-band pointer. D26 — the continuous benchmark gains a program-call
row. D27/T7 — every capability a port lacks is a sentence on
`unenforced`/`unsupported`, tested verbatim.

---

## 4. Capability preservation — and maximisation

**Preservation is proven, not promised.** The master inertness suite (P0)
runs the three shipped example workspaces and the eight pattern trees through
the reference harness before and after every phase and asserts byte-identical
traces — the strongest possible statement that existing agents lose nothing.
No existing field is renamed, removed, retyped, or re-tiered anywhere in this
plan; the diff to `spec/schema.yaml` is additive in every phase (a CI check
asserts the old schema's field set is a subset of the new one's, with equal
attributes).

**Maximisation is the composition table.** Each new mechanism multiplies the
existing ones rather than standing beside them:

| × | composes with | yielding |
|---|---|---|
| values | policies, interceptors, evals, limits | one figure governing gate + guard + test, drift-proof |
| templates | all 13 collections, bundles, abstract bases | parameterised capability libraries; `base:` + `expects:` = declared-argument classes |
| programs | the action governance vocabulary | `needs-a-person:`, `spends-money:`, `same-request-key:`, `bind:`, `inspects:` apply to program calls unchanged — the approval algebra is inherited, not rebuilt |
| programs | evals' deterministic-first band | exact custom graders, offline |
| programs | interceptor powers | the two host-only rewrite powers become authorable, fueled, fingerprinted |
| agent-shape dispatch | recursion fuel + teamwork joins | dynamic worker selection with the same bottom the static graph has |
| learning widening | operator algebra + drift + classifier | self-change over loops/tools/topology with per-class autonomy the author dials |

The power-delta in one line: before — exact computation requires a server;
routing cannot read content; rewrite powers are host-only; workers are
static; learning applies wording only. After — all five, each behind one
written line, none by omission.

---

## 5. The phases

Ordering rule: loader-only work first (zero runtime risk, immediate power),
then runtime admission rules, then execution, then vocabulary integration,
then self-authoring. Each phase lists **tests written first** (with their
failing assertion), **implementation sites**, **exit gate**.

### P0 — The net before the wire

*Tests first (all must pass before any phase, and forever after):*
- `inertness_suite` (Py + Rust): golden traces + golden `pact show` JSON for
  `examples/refund-desk`, `examples/mcp-desk`,
  `examples/answers-from-documents`, and all eight `examples/patterns/*`;
  asserts byte-equality across every subsequent phase.
- `schema_growth_is_additive` (Rust test): old-vs-new field-set subset check.
- `check_is_still_pure_with_programs_present`: extend the no-socket/no-spawn
  CI assertion to a tree carrying `programs/` with a body.
- `the_no_code_badge_survives`: the worked example's badge evaluation,
  pinned.
*Implementation:* none. *Exit gate:* suite green on HEAD.

### P1 — `values:` (one write, many readers)

*Tests first:*
- `tests/trees/one-figure-three-doors/`: a value `refund-approval-threshold`
  used by a policy rule (`more-than:`), an interceptor sentence hole, and an
  eval case; golden `pact show` asserts all three sites print `200 USD`;
  editing the value file (test copies the tree, edits, re-checks) moves all
  three.
- `a_use_of_a_name_that_is_not_there_is_refused`: `{use: refund-threshhold}`
  → error naming the value that exists, with fix; positive control: correct
  name loads clean.
- `a_value_of_the_wrong_shape_is_refused_at_the_use_site`: duration into a
  money field → names both lines (use site and definition).
- `a_use_in_a_key_position_is_refused`; `a_value_nothing_points_at_is_warned`
  (extends `unnamed.rs`).
- `expanded_and_longhand_trees_have_one_digest` (AC-1.4 pattern).
*Implementation:* `value` group + `values:` collection in S (shape via the
answer-shape vocabulary; `surface: S-META`, use-site surface governs
classification); new `L/values.rs` substitution pass wired in
`C/main.rs:1431` *before* `derive::resolve`; the 4 collection sites.
*Exit gate:* full suite + P0 inertness (trivially: no `{use:}` in any
existing tree).

### P2 — `expects:` / `with:` (operators with arguments)

*Tests first:*
- `tests/trees/two-desks-one-pattern/`: the interceptor template from 27 §C2
  plus two `with:` calls; golden expansion; digest equality against a
  hand-written longhand twin.
- `an_unfilled_parameter_is_refused_naming_it_and_its_shape` (+ positive
  control).
- `an_argument_outside_expects_is_refused_listing_the_declared_ones`.
- `a_hole_in_a_key_is_refused_at_the_template` and
  `a_hole_no_parameter_declares_is_refused`.
- `an_argument_may_be_a_value` (`with: {ceiling: {use: default-ceiling}}`).
- `a_template_chain_expands_outside_in` (base-of-base with `expects:` at both
  levels); the based-on circle test stays green.
- `restating_a_block_still_warns_inside_a_template_expansion` — D-1's
  warning must survive substitution with correct spans.
*Implementation:* `expects:` field on the 13 kinds (S, one anchored block);
`L/derive.rs`: after merge — substitute declared holes in `Value::Str`
scalars, coerce by declared shape, strip `with:`; refuse the residues.
*Exit gate:* suite + inertness + `pact explain`-style provenance line in the
LoadReport for every substitution.

### P3 — Payload digests + governed `.pactignore`

*Tests first:*
- `a_payload_file_carries_its_digest` (golden manifest for the refund-desk
  script); `removing_a_script_moves_the_workspace_digest`.
- `an_ignore_rule_is_part_of_the_document`: `.pactignore` appears in
  canonical form; `ignoring_a_script_moves_the_digest_too` — the laundering
  channel closes.
*Implementation:* `pact-doc` `FileRef.digest`; `L/lib.rs` payload walk
hashing (sha2 already a dependency); ignore-file lift into the document.
*Exit gate:* suite green; **known cost recorded**: every payload-carrying
workspace digest moves once — release-noted as a digest-v2 line.

### P4 — The dynamic-bottom rule

*Tests first (Python, mirroring `test_asking_yourself_has_a_bottom.py`):*
- `an_agent_by_value_with_a_figure_is_put_to_work_and_spends_it`: a
  run-input of shape `agent` reaches delegation; the meter decrements; trace
  shows the dispatch.
- `an_agent_by_value_without_the_figure_is_refused_as_that_members_failure`
  (OverBudget-shaped; `if-someone-fails:` decides) + positive control.
- `a_base_by_value_is_refused` (sixth door).
- `no_agent_shaped_value_no_behaviour_change`: byte-equal traces; the new
  key absent from `json.dumps(trace())`.
*Rust tests:* `a_receivable_agent_with_no_bottom_is_warned` on a closed
`one of` value space, naming the agent and the line to add;
`a_base_is_something_to_build_on.rs` gains the by-value door.
*Implementation:* `harness.py` — admit agent-shaped values from
`run_inputs`/tool results into the existing `ask` path (`:723`, beside
`:3001-3015`); `L/teams.rs` warning.
*Exit gate:* suite + both new Python tests + TS `notDoneHere` sentence test.

### P5 — Learning widening

*Tests first:*
- `may_also_change_extends_the_proposal_surface_and_not_the_floor`: a loop
  proposal with the opt-in classifies ≥ CLASS-3; without it, refused with
  the sentence naming the line.
- `applies_up_to_lets_class_two_apply_and_class_three_never`: with
  `applies-up-to: CLASS-2` and a green suite at the minimum-case floor,
  CLASS-2 auto-applies; CLASS-3 queues regardless.
- `the_union_may_only_widen` (extend the existing HIGH_RISK union test);
  `an_escalator_still_ends_auto_apply` (X18); `drift_is_not_optable`.
*Implementation:* two S fields on `learning`; `Py/learning.py` — apply-set
derived from opt-in × class instead of `CAN_BE_APPLIED` constant; routing
per class.
*Exit gate:* suite + queue/ledger tests green + the shipped example (which
opts into nothing) inert.

### P6 — The `program` kind, the sandbox resource, the egress role

*Tests first:*
- `tests/trees/a-desk-with-a-program/`: `programs/check-window/` (wasm body
  payload, `takes:`, `answers-with:`, `fuel:` with `when-it-runs-out:`),
  `resources/local-sandbox.yaml` (`engines: [wasm]`, `asks-to-run:`),
  `tools/refund-window.yaml` (`connect: local-sandbox`,
  `actions.check.program: check-window`); `pact check --deny-warnings` exit 0.
- `a_program_action_naming_no_program_is_refused_naming_the_ones_there_are`.
- `a_reaching_program_under_an_empty_egress_list_is_refused_where_the_author_is`
  (R30 pattern, with the `programs` role as the fix line) + positive control
  (non-reaching program loads clean under `allow-egress: []`).
- `a_program_with_no_fuel_is_refused` (`needs-also:` chain) and
  `fuel_without_when_it_runs_out_is_refused`.
- `a_sandbox_that_does_not_host_the_engine_is_refused_at_check`.
- `pact_waits_lists_the_may_we_run_gate`.
- `discover_and_card_do_not_leak_program_bodies` (projection tests).
*Implementation:* S (groups + choices + role); 4 collection sites; new
`L/programs.rs`; `C/egress.rs` role read.
*Exit gate:* suite + `eve_inventory.rs`/`deliberate_refusals.rs` green after
the R58/R42 ledger amendments land in the same change.

### P7 — Execution: the wasm engine and fuel

*Tests first:*
- `the_boundary_declares_the_executor`: `program_executor` present in
  `SUPPLIED_BY_THE_HOST` (registry test fails until declared).
- `a_program_call_is_a_tool_call_in_the_trace`: golden trace rows; counted
  by `tool-calls-at-most` (`harness.py:2013` site).
- `a_result_is_coerced_by_answers_with` (reuse `Shape.read`; a program
  answering the wrong shape is that call's failure sentence, never a crash).
- `fuel_exhaustion_takes_the_authors_exit`: an infinite-loop wasm fixture
  exhausts `instructions-at-most` deterministically → `_ran_out` →
  `when-it-runs-out:` honoured; asserted on two runs for identical spend.
- `no_executor_means_an_honest_sentence`: without a host executor the call
  returns the `error: no tool named …`-class sentence and the workspace's
  programs land on `unenforced`.
- `the_air_gapped_run_passes_with_the_network_disabled` (D17 suite).
- TS: `programs_are_declared_absent` (`notDoneHere` + `unenforced` line).
*Implementation:* `Py` executor seam + vendorable wasm runtime imported
inside the function (the `mcp/client.py` pattern); deterministic fuel
metering; charge sites beside `_meter_usage`.
*Exit gate:* suite + D26 benchmark row recorded + §7.28 coverage list
amended honestly.

### P8 — Programs as a capability kind; the vocabularies

Eight sub-waves, each red-green-complete before the next starts; all carry
inertness + reader-coverage + both-ports statements.

1. **`uses:`/`may-use:` gain `programs`** — offering test (`tool_defs`
   carries the program with its `takes:` schema); stage narrowing test;
   `L/teams.rs` may-use resolution.
2. **`bind: remembers.<name>`** — bound argument invisible to the model
   (schema-projection test), resolved from state; unknown state name refused
   at check.
3. **`action.remember-as:`** — result lands in declared state; the guard
   test: a state whose `never-from:` lists `tool output` refuses the line at
   check time, naming both lines (+ positive control with the line removed).
4. **`program:` metric scheme** — `providers.py:169-174` becomes three;
   `why_unavailable` lists all three; deterministic band ordering test
   (a fully decidable suite still never invokes a model).
5. **`projects-with:`** — projection applied before the model sees the
   result (golden conversation test); only `determinism: pure` programs
   accepted (refusal names the line).
6. **Program-holed sentences** — `forms:` rows (data) + compiler; powers:
   `rules_with_a_program_the_tree_does_not_have_are_refused`;
   `change_the_answer_is_authorable_only_with_a_program_hole`
   (AUTHORABLE table change + `power-nothing-can-use` stays green);
   rewrite recorded in trace with the program digest.
7. **`checked-by:` on questions** — a human answer failing the check is
   re-asked with the program's sentence, never silently accepted; check-time
   name resolution.
8. **`decided-by:` + `may-go-to:` + `does: run-code` + codeact** —
   `a_route_outside_may_go_to_is_a_loop_error_kept_in_the_steps`;
   `reachability_counts_may_go_to_destinations`;
   `decided_by_never_overrides_a_ceiling` (fuel outranks routing — the
   ordering test); `run_code_requires_a_sandbox_at_check`;
   `every_snippet_is_in_the_transcript`; `spec/loops/codeact.yaml` +
   both `or-one-of:` lists + the badge-exclusion test
   (`a_workspace_with_decided_by_does_not_earn_the_no_code_badge`).

*Exit gate per wave:* full suite; ledger amendment for R24 lands with wave 6.

### P9 — The self-authored lane

*Tests first:* `a_composite_tool_over_pinned_actions_needs_no_engineer`;
`a_code_bodied_tool_without_an_engineer_approval_is_refused_with_the_exact_wording`
("this tool contains code that has not been read by a person");
`does_not_raise_is_not_an_acceptance_path` (only the eval gate keeps a
learned program); `a_revoked_digest_cannot_bind` (resolver + lockfile);
`a_learned_program_is_a_new_blob_with_a_supersedes_edge_at_class_four`.
*Implementation:* S `composite:`; `Py/learning.py` proposal kinds; resolver
refusal.
*Exit gate:* suite + QUEUE-ledger tests + the D14 badge still intact on the
worked example.

---

## 6. Cross-port strategy

The TypeScript port stays the honest smaller port. Per phase: P1–P3 cost it
nothing (loader-side; it consumes the expanded document). P4, P7, P8 land as
**declared absences first** — one `notDoneHere` entry and one `unenforced`
sentence each, with a test asserting the sentence — then port in this order
if/when parity is wanted: shapes validation (its standing gap), programs,
dynamic dispatch. A capability the second port lacks but names is the
project's stated norm (§7.28 list B); a capability it lacks silently is a
defect this plan may not create.

## 7. Risks, with their falsifiers

1. **Deterministic fuel across hosts** — if the wasm engine cannot make
   `instructions-at-most` bite identically on two machines, program calls
   move to §7.28's list B (outside the byte-identical claim) *before* P7
   merges; the falsifier is the two-host fuel test.
2. **Template metaprogramming pressure** — the first real request for a hole
   in a key or a generated field is the signal to *stop* and take it to a
   fixture review, not to widen the scanner; the refusal test is the tripwire.
3. **`decided-by:` becoming the default lane** — watched by the badge test
   and by `pact waits`-style visibility; if pattern trees start needing it,
   that is H6-class evidence the three-outcome table needs a fourth *named*
   outcome instead.
4. **Digest migration noise** (P3) — one-time, release-noted; the falsifier
   for "safe" is the golden-manifest suite on all examples.
5. **Learning autonomy regressions** — the propose-only example must never
   change behaviour; any diff to its queue output fails P5.

## 8. Standing obligations checklist (every phase)

- [ ] failing test observed before implementation, positive controls present
- [ ] `surface:` + `tier:` + `help:` on every new field (gate enforces)
- [ ] reader exists for every new field (reader-coverage suites)
- [ ] inertness trace suite green
- [ ] both ports: parity or a tested declared absence
- [ ] diagnostics through the real binary with typeable fixes
- [ ] ledger/gap-register/site-docs counts amended in the same change
- [ ] `./scripts/test-all.sh` fully green, offline
