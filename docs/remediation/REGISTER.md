# Remediation index — what was touched, where it stands, what holds it

**This is an index, not a source of truth.** Every row points at the document
that carries the evidence — `docs/70-PRODUCTION-GAP-REGISTER.md` for a gap,
`docs/95-FIX-PLAN.md` for a designed fix, a file in this folder for a decision —
and at the test that fails when the thing comes undone. Where the two disagree,
the register and the test are right and this file is stale.

**Nothing here is a count.** This repository has now had four documents go wrong
by carrying a figure beside a computed one (AC-2.1's `28 agents`, AC-7.2's `21`
defaults, A6's `13 unread`, C7's `39 test files`), and an index is the most
tempting place of all to add a fifth. Where a number is wanted, run the command
the register names for it.

**"Closed" means a named test fails if the fix is reverted.** A row that says
*decided* has no code behind it and does not claim any. A row that says
*narrowed* moved and did not finish.

---

## 1. Decisions taken as documents

These produced no behaviour. Each is a decision with its price written down, and
each names the acceptance tests that would close it if it is ever built.

| Doc | Answers | Decision |
|---|---|---|
| `docs/remediation/C7-bundle-mounting.md` | **C2** — `bundle.from:` resolves nothing | Build the folder form (`bundles/<name>/contributes/`), **never build fetching**. Four sub-decisions taken: containment, merge point, collisions, digest. Seven acceptance tests written out. **Not built.** |
| `docs/remediation/C8-profiles.md` | **AC-7.2's profile half** | **Delete `workspace.profile`** and amend the criterion. The two halves of AC-7.2 contradict each other, and a profile is the precedence FR-1.1.4 forbids. **Not implemented**; three named defects are part of its price. |
| `docs/remediation/F1-content-conditional-routing.md` | routing on what a tool returned | **Refused.** No predicate over content anywhere. |
| `docs/remediation/F2-error-and-retry-semantics.md` | a tool that failed | **Not refused — build it.** One outcome (`tool-failed`), one watch moment (`step.tool.failed`), no `retries:` field. The only one of the seven that should ship. **Not built.** |
| `docs/remediation/F3-iteration-over-a-collection.md` | fan-out over N items | **Refused.** Fan-out stays a `team:` of names somebody typed. |
| `docs/remediation/F4-inter-stage-state.md` | a value carried between stages | **Refused.** No variables; everything transits the conversation. |
| `docs/remediation/F5-two-loops-named-for-what-they-are-not.md` | **AC-5.2** | **A correction, not a refusal.** Six shapes shipping is not six techniques shipping: `tree-of-thought` and `answer-more-than-once` are approximations whose limits their own files state and the register did not, `reflexion` is a third (its missing half is F6's decision), and `standard` is named for no technique in the criterion. The AC-5.2 row is amended in the same change to enumerate rather than to count. |
| `docs/remediation/F6-reflexion-has-no-memory-across-runs.md` | reflections that outlive a run | **Refused.** Improvement across runs stays `learning:` — a proposed edit to a file, with a person on it. |
| `docs/remediation/F7-blackboard-market-auction.md` | **AC-5.1's three missing patterns** | **Refused, and the register's existing verdict survives.** The criterion should be amended rather than satisfied. |

*(The `F` numbers are this folder's own sequence. `docs/95-FIX-PLAN.md` uses
`F6` for an interceptor sentence and `A6` for a `tries:` field; neither is
related. `docs/remediation/C7-bundle-mounting.md` is likewise named for its work item and answers
register row **C2**.)*

---

## 2. Closed — a named test fails if it is reverted

Grouped by where the register records them. The register row is the evidence;
this column is the file to run.

### Class A — declared, tested, wired to nothing

| # | Held by |
|---|---|
| **A1** `survives-shortening:` reached nothing | `adapters/python/tests/test_what_the_author_wrote_reaches_the_run.py` |
| **A2** model selection had no door | `adapters/python/tests/test_the_model_choosing_door_survives_being_opened.py` |
| **A3** the learning cycle had no caller | `adapters/python/tests/test_three_mechanisms_that_only_their_tests_reached.py` |
| **A4** `Slo.assess` had no caller | same |
| **A5 / A5b** `answers-with:`, `answers-with-mode:`, `model-for-checking:`, three model settings | `adapters/python/tests/test_portability.py`, `adapters/python/tests/test_every_field_has_a_reader.py` |
| **A6** the field audit, made mechanical | `adapters/python/tests/test_every_field_has_a_reader.py` — `KNOWN_GAPS` is empty, and the check to trust is `test_every_authored_field_is_read_by_something_or_declared_delegated` |
| **Phase 1.1** the run boundary, declared | `adapters/python/tests/test_the_boundary_between_a_document_and_a_run_is_declared.py` |
| **Phase 1.2** the loader→adapter boundary, made total | `adapters/python/tests/test_the_loader_to_adapter_boundary_is_total.py` — it records key access during a real load; the argument is the register's Phase 1.2 section |
| **the orphan walk** | `adapters/python/tests/test_a_reader_is_reachable_from_a_run.py`, and the question the source answers exactly, `adapters/python/tests/test_nothing_public_is_named_by_nothing.py` |
| **public tables**, the same question one level down | `adapters/python/tests/test_a_table_nothing_reads_is_not_a_source_of_truth.py` |
| **a door that answers with silence** | `adapters/python/tests/test_no_plausible_command_at_this_package_answers_with_silence.py` |

### Class B — acceptance criteria the register records as met

The register records each of these as **MET** — some as a struck-through table
row, some as a prose bullet, and nothing checks which. The register is where the
argument is; this is where the test is.

| AC | Held by |
|---|---|
| **1.2′** explode/load round trip | `adapters/python/tests/test_a_document_explodes_back_into_its_tree.py` |
| **1.4** flat and tree forms are one document | `crates/pact-loader/tests/example_refund_desk.rs::the_flat_and_expanded_forms_have_the_same_digest` (the equivalence test Phase 3 bug 11 fixed), and one level up `crates/pact-loader/tests/digest_equality_for_the_new_kinds.rs` |
| **2.1** golden set | `adapters/python/tests/test_the_golden_set_runs_everywhere.py` (`len(GOLDEN)` is the figure; no number is written down) |
| **2.2** conformance report | `adapters/python/tests/test_the_conformance_report_is_honest.py` |
| **3.2** the comparison vocabulary | `crates/pact-schema/tests/a_comparison_means_the_same_thing_in_both_ports.rs` and `adapters/python/tests/test_a_comparison_means_the_same_thing_in_both_ports.py`, against the shared `spec/comparisons.yaml` |
| **3.6** ceilings at resolve time and run time | `adapters/python/tests/test_two_ceilings_that_disagree_are_caught_before_the_run.py`, over `slo.against_the_catalogue` as `pipeline`'s `resolve` stage reaches it |
| **4.1** DeepEval coverage matrix | `providers.coverage()`, wired — see `adapters/python/tests/test_three_mechanisms_that_only_their_tests_reached.py` |
| **4.3** evals against a remote agent | `adapters/python/tests/test_scoring_an_agent_that_is_not_here.py`, over `A2ATransport`; its metering half by `adapters/python/tests/test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py` |
| **4.4** promote a trace to a case | `adapters/python/tests/test_what_the_author_wrote_reaches_the_run.py` — both halves: the `--from-trace` door, and the checker refusing the promoted case with the diagnostic code `evals/case-asserts-nothing` until somebody fills in `expect:` |
| **5.5** a rejected candidate influences the next cycle | `adapters/python/tests/test_a_months_spend_on_improving_is_held.py` and `adapters/python/tests/test_a_read_only_workspace_still_runs.py`, over `learning.Refusals` — which persists to `.pact/learning/refused.jsonl`, a run-time artifact and not a file in this tree |
| **7.1** the fuzzer | `adapters/python/tests/test_nothing_vanishes_between_the_file_and_the_document.py` |
| **7.3** the offline pipeline | `adapters/python/tests/test_the_whole_pipeline_runs_offline.py`, over `pact_adapters.pipeline` (run as `pact-pipeline`) |

### Class C — production readiness

| # | Held by |
|---|---|
| **C1** spec versioning | `crates/pact-cli/tests/a_format_that_can_say_which_version_it_is.rs` |
| **C7** the CI gate | `.github/workflows/gate.yml`; `adapters/python/tests/test_the_gate_is_run_by_something.py` |
| **C8** `$PACT_DERIVED_DIR`, and degrading rather than taking the run down | `adapters/python/tests/test_a_read_only_workspace_still_runs.py`; the argument is the register's C8 row |
| **C9** a spend cap no money can reach | `crates/pact-schema/tests/a_spend_cap_is_an_amount_of_money_and_has_a_bottom.rs`; `adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py`, `adapters/python/tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py`, `adapters/python/tests/test_both_ports_read_every_way_a_spend_cap_is_written.py`; the third money field by `crates/pact-cli/tests/a_gate_whose_figure_is_not_a_figure_is_refused.rs` |
| **C10** numbers too big and too small to hold | `crates/pact-cli/tests/a_number_too_big_to_hold_is_kept_as_it_was_written.rs`, `crates/pact-cli/tests/a_number_too_small_to_hold_is_kept_as_it_was_written.rs`; the figure-not-the-spelling rule by `crates/pact-doc/src/yaml.rs`'s `a_whole_number_is_past_holding_when_it_writes_back_different_digits`; the duration spelling across both ports by `adapters/python/tests/test_what_the_author_wrote_reaches_the_run.py`'s `test_every_length_of_time_the_checker_passes_is_read_here_the_same_way`. See `docs/remediation/C10-number-too-big-dead-end.md` |

### Loader and checker defects with no register row of their own

Found while closing the rows above. Each is a real refusal or a real report that
did not exist before, and each has a test that is its only witness.

| What | Held by |
|---|---|
| an entry skipped for its folder NAME is reported, never silently gone | `crates/pact-loader/tests/an_agent_in_a_folder_named_build_is_never_silently_gone.rs`, `crates/pact-cli/tests/a_folder_the_checker_skips_is_named_on_the_way_past.rs` |
| a shortcut is refused inside an attachment folder too | `crates/pact-loader/tests/a_shortcut_inside_an_attachment_folder_is_refused_like_any_other.rs` |
| a self-copying YAML anchor cannot bring the checker down | `crates/pact-cli/tests/a_shortcut_that_copies_itself_cannot_bring_down_the_checker.rs` |
| prose below the `---` line never just disappears — and the fence it sits under is refused rather than planted in the slot the prose was meant for, so one mistake is one message (**B1**) | `crates/pact-loader/tests/a_sentence_below_the_settings_never_just_disappears.rs` (the document), `crates/pact-cli/tests/a_fence_that_is_not_settings_is_one_mistake_told_once.rs` (the exit status and the message count) — argument in `docs/remediation/B1-markdown-body-dropped.md` |
| a token count too big to hold is refused where it was written | `crates/pact-cli/tests/a_size_this_cannot_count_is_refused_rather_than_changed.rs` |
| a folder that HAS a `workspace.yaml` is never told it has none | `crates/pact-cli/tests/a_workspace_with_no_agents_in_it_yet_is_still_a_workspace.rs` |
| every field that binds a model is held to `allow-egress:` | `crates/pact-cli/tests/every_model_a_document_names_is_held_to_the_boundary.rs` |
| every `role:` an author may write is a word the egress rule knows | `crates/pact-cli/tests/every_part_the_boundary_offers_is_one_the_checker_knows.rs` |
| the workspace a check finds is the one a runtime finds | `crates/pact-cli/tests/the_workspace_a_check_finds_is_the_workspace_a_runtime_finds.rs` |
| every spelling of yes means one thing to every reader | `adapters/python/tests/test_one_word_for_yes_means_one_thing_to_every_reader.py`, against `adapters/python/src/pact_adapters/yes_no.py` / `adapters/typescript/src/yes-no.ts` |
| a document that counts the honesty channels counts the ones the run has | `adapters/python/tests/test_a_channel_count_in_a_document_is_the_count_the_run_has.py` |
| the held-out count on a report is the split itself | `adapters/python/tests/test_the_held_out_count_on_a_report_is_the_split_itself.py` |
| a transport factory that cannot be called with two arguments is refused at the door, named, rather than crashing four frames down (**D3**) | `adapters/python/tests/test_the_model_choosing_door_survives_being_opened.py::test_the_search_refuses_without_a_way_to_run_anything`, `::test_the_door_refuses_a_factory_it_cannot_call_with_two_arguments` — argument in `docs/remediation/D3-transport-factory-defaulted-to-none.md` |
| a model nothing was run against is never reported as having been measured against the bar (**D3**, the same family, no register row of its own) | `adapters/python/tests/test_the_model_choosing_door_survives_being_opened.py::test_a_caller_who_asked_for_no_strategies_is_not_told_the_box_is_silent`, `::test_a_row_nothing_was_run_against_is_not_reported_as_having_failed` |
| the README cannot go on saying `resolve()` has no shipped caller once it has one — the guard now fires in both directions | `adapters/python/tests/test_the_documentation_site_tells_the_truth.py::test_output_the_readme_shows_is_attributed_to_something_that_can_produce_it` |

---

## 3. Narrowed, not closed

| # | Where it got to | Held by |
|---|---|---|
| **C2** bundles | All three of the check's rules — the not-mounted warning and both refusals — are exercised from a real tree; **mounting is still unbuilt**, and its decisions are `docs/remediation/C7-bundle-mounting.md` | `crates/pact-loader/tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs`, against `tests/trees/what-a-bundle-brings/` |
| **C3** the second port | Behaviour-only for the four governance mechanisms, and narrower than it was: it honours `answers-with:`, reports unread keys inside `limits:`, refuses an unknown field from the library, and names a `knowledge:` corpus it never looked in | `adapters/python/tests/test_the_subset_the_second_port_runs.py`, `crates/pact-cli/tests/the_subset_the_second_port_runs.rs`, `adapters/python/tests/test_a_corpus_the_second_port_never_looked_in_is_not_silent.py` |
| **C5** what a transport passes on | Re-measured key by key from the source. Five transports gained `apply_settings` coverage; `tool-choice` is now guarded per call on the two provider-bound ones; `thinking` still reaches one of nine, which is the hole to act on | the five `test_what_the_author_asked_for_*` files, and `adapters/python/tests/test_the_two_provider_transports_send_a_choice_a_call_can_carry.py` |
| **AC-7.2** | The audit half is held; the profile half is a **decision** (`docs/remediation/C8-profiles.md`) and the amendment it asks for is unmade | `adapters/python/tests/test_no_default_decides_a_capability_in_secret.py` |
| **AC-5.2** | Corrected from MET to **PARTIAL** (`F5`). Of the six techniques the criterion names: ReAct and Plan-and-Execute ship, Reflexion ships in part (`F6` refuses the missing half), Tree-of-Thought and self-consistency do not ship, CodeAct is refused. `standard` answers none of the names. **No figure**, for the reason at the top of this file | `adapters/python/tests/test_loops.py` holds existence and termination — **and nothing holds fidelity**, which is the finding |
| **AC-5.1** | Eight patterns ship; three named ones are **refused with a price** (`F7`) rather than open work | `adapters/python/tests/test_the_orchestration_patterns_are_distinct_and_run.py` |

---

## 4. Open, and nothing here holds them

Listed so that the sections above cannot be read as coverage. All of these are in
`docs/70-PRODUCTION-GAP-REGISTER.md` under *"What to do, in order"*.

- **AC-6.1 / 6.2** — **BLOCKED**, not undone. Closing it needs two changes to
  `gaia-ai-runtime`, another team's codebase (AD-92). Nothing in this repository
  can do it.
- **AC-6.4** — unmet on both halves: no recipe, custom-agent or skill importer,
  and no re-export-and-compare path for the two importers that do ship.
- **AC-1.5** — the human trial. Protocol written, never run. Blocked on people.
- **AC-2.5's second half** — a separate *directory*, not a separate
  *repository*; needs publishing (C6).
- **AC-3.5's measurement** — the mechanism ships, the improvement is unclaimed.
  Blocked on served weights.
- **C6** — installable, not published.
- **The criteria the register carries as PARTIAL.** They are not all in one
  place and there is no count of them here: the *"Was listed Met"* table has a
  row that names a set of them, and `5.1`, `5.2`, `6.3` and `7.2` carry rows of
  their own. Read the register's tables rather than this bullet.
- **F2** — the one thing in section 1 that should be built and is not.

---

## 5. What this index deliberately does not do

It does not restate a verdict. Every row above is a pointer, and the reason is
the failure this whole remediation is about: a summary beside a computed thing
becomes a second copy of it, and the second copy is the one that goes stale.
`docs/70-PRODUCTION-GAP-REGISTER.md` records four of its own rows going wrong
exactly that way — the four in the second paragraph of this file — and the fix
each time was to compute the figure rather than to write it more carefully. The
register's AC-3.6 row records the other shape of the same habit: *"the sixth
register row of mine to be false about code sitting in the tree."*

So the check on this file is not a test. It is that **every path given here as a
pointer opens**, and a row whose file has been renamed is a broken pointer rather
than a false claim. Three names look like paths and are not pointers, and each is
marked as such where it appears: `.pact/learning/refused.jsonl` is written at run
time and is not in the tree; `evals/case-asserts-nothing` is a loader diagnostic
code (`crates/pact-cli/src/main.rs`), not a file; and `workspace.yaml` in the
last table is the subject of a sentence rather than somewhere to look.
