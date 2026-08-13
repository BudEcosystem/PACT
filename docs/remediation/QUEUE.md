# Remediation queue

One row per issue. The `/loop` takes the first row marked `queued`, drives it through the
per-issue workflow (RCA → source analysis → solution research → blast radius → integration →
brutal review → iterate → detailed implementation plan), writes
`docs/remediation/<ID>-<slug>.md`, and marks the row `done`.

**Every issue below already has its fix landed and the gate green.** What is missing is the
per-issue document: the RCA, the blast-radius analysis, the failure-case enumeration, the mutation
that was verified, and the test that holds it. That reasoning currently lives in workflow
transcripts and code comments rather than anywhere a reader can find it. The document is the
deliverable; where it disagrees with the code, the code is re-checked and the disagreement is the
finding.

Status: `queued` · `done` · `open` (fix not landed).

| # | ID | Slug | Status | Doc |
|---|---|---|---|---|
| 1 | A1 | choose-model-arity | done | [A1-choose-model-arity.md](A1-choose-model-arity.md) |
| 2 | D3 | transport-factory-defaulted-to-none | done | [D3-transport-factory-defaulted-to-none.md](D3-transport-factory-defaulted-to-none.md) |
| 3 | A2 | egress-model-for-checking | done | [A2-egress-model-for-checking.md](A2-egress-model-for-checking.md) |
| 4 | A3 | yaml-alias-bomb | done | [A3-yaml-alias-bomb.md](A3-yaml-alias-bomb.md) |
| 5 | B4 | duration-overflow-panic | done | [B4-duration-overflow-panic.md](B4-duration-overflow-panic.md) |
| 6 | B3 | money-has-no-floor | done | [B3-money-has-no-floor.md](B3-money-has-no-floor.md) |
| 7 | B9 | more-than-nan-gate-never-fires | done | [B9-more-than-nan-gate-never-fires.md](B9-more-than-nan-gate-never-fires.md) |
| 8 | B5 | ts-money-divergence | done | [B5-ts-money-divergence.md](B5-ts-money-divergence.md) |
| 9 | B6 | a2a-claims-to-price-money | done | [B6-a2a-claims-to-price-money.md](B6-a2a-claims-to-price-money.md) |
| 10 | B8 | in-code-nan-cap | done | [B8-in-code-nan-cap.md](B8-in-code-nan-cap.md) |
| 11 | B1 | markdown-body-dropped | done | [B1-markdown-body-dropped.md](B1-markdown-body-dropped.md) |
| 12 | B2 | skipdirs-silent-delete | done | [B2-skipdirs-silent-delete.md](B2-skipdirs-silent-delete.md) |
| 13 | C3 | x-overflow-to-null | done | [C3-x-overflow-to-null.md](C3-x-overflow-to-null.md) |
| 14 | C12 | underflow-to-zero | done | [C12-underflow-to-zero.md](C12-underflow-to-zero.md) |
| 15 | C10 | number-too-big-dead-end | done | [C10-number-too-big-dead-end.md](C10-number-too-big-dead-end.md) |
| 16 | C5 | payload-symlinks | queued | |
| 17 | C11 | false-not-a-pact-folder | queued | |
| 18 | C13 | third-answer-to-what-is-a-workspace | queued | |
| 19 | C1 | discover-fabricated-path | queued | |
| 20 | C2 | ts-unretrieved-channel | queued | |
| 21 | C6 | egress-roles-drift | queued | |
| 22 | C4 | scoring-module-silence | queued | |
| 23 | B7a | settings-pydantic-langchain-langgraph | queued | |
| 24 | B7b | settings-autogen-openai-agents | queued | |
| 25 | G1 | ts-asks-hole | queued | |
| 26 | D1 | duplicate-yes-in-resolve | queued | |
| 27 | D6 | three-copies-of-yes | queued | |
| 28 | D2 | comparison-tolerance-drift | queued | |
| 29 | D7 | bare-number-threshold | queued | |
| 30 | D8 | dead-answer-modes | queued | |
| 31 | D9 | dead-python-egress-roles | queued | |
| 32 | D4 | margin-measured-a-proxy | queued | |
| 33 | D5 | unreachable-venv-entry | queued | |
| 34 | E1 | register-defaults-count | queued | |
| 35 | E2 | register-metering-matrix | queued | |
| 36 | E3 | register-importers-row | queued | |
| 37 | E4 | schema-model-field-comment | queued | |
| 38 | E5 | register-gaia-integration | queued | |
| 39 | E6 | register-bundles-fixture-only | queued | |

## Found by the per-issue pass — live, measured, unfixed

Each was surfaced by an RCA phase asked to name *other instances of the same class still in the
tree*. That question is why they are here rather than in a document nobody reads.

| # | ID | Slug | Status | Doc |
|---|---|---|---|---|
| 40 | D10 | needs-read-off-the-wrong-key | queued | |
| 41 | D11 | baseline-printed-when-nothing-ran | queued | |
| 42 | D12 | scores-defaulted-to-none | queued | |
| 43 | D13 | as-record-advertises-a-parameter-it-does-not-take | queued | |
| 44 | B10 | a-good-cap-switched-off-by-a-bad-meter | queued | |
| 45 | B11 | the-argument-side-of-a-gate-is-fail-open | queued | |
| 46 | G2 | a-green-gate-that-compared-nothing | queued | |
| 47 | E7 | three-published-counts-no-test-reads | queued | |
| 48 | G3 | held-nothing-has-no-second-port-event | queued | |
| 49 | G4 | nine-test-files-rebuild-the-binary-they-checked-for | queued | |
| 50 | B12 | a-filename-that-is-not-utf8-is-deleted-in-silence | queued | |
| 51 | C14 | quoting-a-too-big-number-collides-with-not-quoting-it | queued | |
| 52 | D14 | the-two-ports-disagree-on-the-type-of-a-huge-integer | queued | |
| 53 | G5 | mutation-records-quote-counts-that-rot | queued | |
| 54 | C15 | four-doors-still-ask-how-a-figure-is-spelled | queued | |
| 55 | D15 | the-corpus-file-list-is-built-and-read-by-nothing | queued | |

- **D10** — `resolve.py:1285` `agent_key: str = ""`. Measured: with the key, 1 of 13 catalogue rows
  is admitted; without it, **5**. Any caller omitting it makes four unsuitable models bindable. The
  one production caller passes it correctly today, which is exactly what hid it.
- **D11** — `resolve.py:1286` `baseline: str = "the hand-authored frontier strategy"` is printed on
  reports where nothing ran. Measured output shows `measured against: the hand-authored frontier
  strategy` one line above `no strategy was supplied, so … was never run`.
- **D12** — `resolve.py:157` `scores: dict[str, float] = None`, defused only by one `or {}`.
- **D13** — `RunResult.as_record(asked)` is advertised with a parameter it does not take, in three
  shipped diagnostics on the `--from-trace` door. A1's exact defect relocated into a help string.
- **B10** — **B3 inverted, and worse.** B3 needed the author to write `NaN`; this needs nothing from
  them. The floor guards the CAP and not the METER, so a perfectly good `cost-per-request-under:
  0.05 USD` is silently switched off by any of: a remote agent reporting `"cost": NaN`
  (`a2a_transport.py:259` → `harness.py:672` / `harness.ts:748`), a price list resolving to
  `nan`/`inf` (`resolve._cost`), a resumed run (`Meter.restored`), or `wall_clock_s` carried
  non-finite through the `__post_init__` that guards its siblings — where it stays a live ceiling
  and reports `nothing_can_reach=()`. Both ports. Measured in B3's pass; see
  `B3-money-has-no-floor.md` §What remains open for the four reproductions and the five smaller
  residuals beside them.
- **B11** — the `more-than:` FIGURE is now checked; the `arg:` side it is compared against is not,
  and it is fail-OPEN. Measured: `_atom_stops({'more-than': '200 USD'}, {'amount': 'about two
  hundred'})` → `False`, so the gate does not fire and the refund goes out with nobody asked. Same
  function, same table as B9, no checker. **This is the harm B9's queue title described**; B9
  itself turned out to be fail-CLOSED (`NaN USD` fires on everything). Two nearby spellings share
  the shape and are recorded in `B9-more-than-nan-gate-never-fires.md`: `more-than: .50 USD` read
  as `50.0` (a silent 100× threshold error, clean through `check` and `show`), and a float `nan`
  returning `False` for a 999,999 USD refund.
- **G2** — **a green gate is compatible with zero cross-port comparison, and the idiom is
  systemic.** With the TypeScript dependencies absent, the money-parity file reports `19 skipped`
  and exits 0, and `scripts/test-all.sh` skips the typecheck under the same condition — so the
  suite whose whole job is to compare the two ports can report success having compared nothing.
  Measured in B5's pass, which also confirmed the probe genuinely distinguishes the three states
  (`throw` in `spend()` → `19 failed` exit 1; `node` absent → `19 skipped` exit 0; `node_modules`
  absent → `19 skipped` exit 0). **The same skip-on-absence idiom appears at 10 sites across 6
  other files.** The missing artifact is one gate-level runnability assertion; it was not added
  inside B5 because it changes the gate for every environment, which is a decision rather than a
  fix. Closely related: the §7.28 Held-by column is correct today only because it was edited by
  hand — the same standing it had when it was false.
- **E7** — **the count-sync mechanism holds one document and three others rot.**
  `README.md` is correct (1944) *because one test reads it*; `site-docs/status/verified.md:16-17`
  (1928 / 2,842), `site-docs/index.md:50` and `docs/90-REVIEW.md:84` are stale and **no test reads
  any of them**. `scripts/sync-counts.sh` writes all four, so the numbers agree only when somebody
  remembers to run it — which is the same standing the register rows had before this programme.
  Measured in B6's pass, which deliberately did not run the script because it needs a full
  `cargo test --workspace` and rewrites four files a concurrent session may hold. **Ran on
  2026-08-08 after B8** — the script does write all four; what E7 is about is that only README is
  *held*, so the other three are correct exactly as long as nobody edits them by hand.
- **G3** — **`held_nothing` exists in one port only.** Python emits `session.limit.failed` carrying
  `held_nothing`; `harness.ts` emits no such event, so the second port can build a run under a cap
  that holds nothing and say so on `unmetered` while emitting nothing on the event stream a host
  watches. The fifth honesty channel's *event* half is single-port, the same shape as C2
  (`unretrieved`). Measured in B8's pass, which closed the `ceilings()` and `ceilingRows` halves
  in both ports but left the event asymmetric.
- **G4** — **nine test files skip unless the binary is built, then rebuild it anyway.** Each guards
  with `if not (…/"target/debug/pact").exists(): pytest.skip("build the CLI first")` and then calls
  `subprocess.run(["cargo", "run", "--quiet", "-p", "pact-cli", "--", "show", …], check=True)` —
  which ignores the binary it just checked for, takes the cargo target-dir lock, and **recompiles
  from whatever is on disk**. Measured 2026-08-08: **10 call sites across 9 files**
  (`test_a_person_can_say_no.py:406` and `test_action_scoped_approvals`,
  `test_a_gate_reads_only_what_it_may`, `test_context_policy`, `test_hitl_partial_approval`,
  `test_judged_rules`, `test_metrics_an_expert_brings`, `test_suspension`,
  `test_the_gate_is_run_by_something`) against **49 files** using the prebuilt `PACT_BIN` idiom.
  Consequence, measured across **five** full-suite runs on 2026-08-08 with no tree edits between
  them: four runs clean (`1954 passed, 7 skipped`, three of them back-to-back at 140–142s), and
  **one run failed both `test_the_authors_own_question_lets_a_person_refuse_with_nothing_passed_in`
  and `test_the_worked_example_still_lets_the_same_person_say_yes`** — the run that overlapped a
  concurrent `cargo test --workspace`. Both pass in 0.19s in isolation. So the suite's verdict
  depends on what else is touching `target/`, and `scripts/test-all.sh` itself runs cargo. The
  failure is silent about its cause: nothing in the output says "another cargo held the lock". A compile failure or a lock contention surfaces as
  `CalledProcessError`/`json.loads` rather than as a sentence. Same class as G2: a gate whose
  answer is not a function of the code. The guard is also the wrong guard — it promises a binary
  the helper never uses.
- **B12** — **B2's own defect, one skip-reason over, still live.** A filename that is not valid
  UTF-8 is deleted in silence at `crates/pact-loader/src/lib.rs:897` and `:769`. Measured
  2026-08-08 in B2's pass: a Latin-1 `agents/café-agent/agent.yaml` gives `OK — loaded cleanly
  (8 settings)`, **EXIT=0 under `--deny-warnings`, stderr 0 bytes** — a whole agent gone with no
  channel saying so. The payload half is worse in kind: a Latin-1 filename in `references/` yields
  a one-entry `files:` manifest, so **an encoding silently moves `workspace-digest`**. This
  falsified the loader test file's own headline docstring (*"An entry skipped because of its NAME
  is either loaded or reported. It is never silently absent."*), which B2 narrowed in prose to
  *"because its name collides with a convention"* and listed under "Consciously not covered" — no
  test weakened, skipped or deleted. The code fix is a separate seam: three walkers, a new rule id,
  and a `#[cfg(unix)]` fixture.
- **C14** — **the collision was narrowed, not deleted.** After C3's fix `x-threshold: 1e999` and
  `x-threshold: "1e999"` share a digest, where before the fix they did not — so the round trip is
  demonstrably type-lossy against AC-1.3's *"untouched"*, and **no test pins either behaviour**.
  C3's pass deliberately did not settle it: both readings are defensible (the author wrote two
  different things; the author wrote the same number two ways), and picking one is a decision about
  what `x-` promises rather than a bug fix. Whoever takes it decides first, then tests.
  **The bottom end is the same, and C12's fix introduced it**: `x-tiny: 1e-999` and
  `x-tiny: "1e-999"` now hash identically where under mutation A they did not. One decision
  settles both ends; taking them separately risks answering the same question two ways.
- **D14** — **the two ports disagree on the type of a huge integer.** Python reads
  `99999999999999999999` as a whole number; Rust keeps it as text. The digits agree, the types do
  not. Harmless today only because no adapter re-reads the author's files — which is a property of
  the current call graph, not a guarantee. Same class as D2/D7: two readers, one question, no test
  holding them together. Measured in C3's pass.
- **G5** — **the mutation protocol records a number that rots, and nothing reads it.** The house
  rule is *"record the mutation in prose in the test's docstring"*, and every pass has written it as
  an absolute count — *"Mutation A: 6 passed; 5 failed"*. That count is stale the moment any later
  pass adds a test to the same file, and **no test reads it**, so it rots silently exactly like the
  published test counts in E7. Measured in C12's pass, by re-performing the mutations rather than
  trusting the record: mutation A's docstring says `6 passed; 5 failed`, the truth is **6 failed**,
  and the sixth failing test (`a_share_of_the_whole_that_underflowed_is_refused_too`) is not named;
  four of the six records quote totals for a 10- or 11-test file that no longer exists. This is the
  evidence base for *"the test bites"* across this whole programme, so the scope is every
  remediation test file, not C12's. The fix is a decision about form — record **which tests turn
  red**, which survives a file growing, rather than **how many pass**, which cannot. **C12's own
  file now uses that form** and can be copied from: every mutation row names the tests that go red,
  all eleven were re-performed with a green run between each to prove the revert took, and the
  docstring states the invariant `passed + failed == <test count>` so the next reader catches drift
  at a glance. The remaining files are untouched. **One mutation in C12's pass was measured three
  times and gave three answers** — docstring `6 passed; 5 failed`, attack `6 failed`, verifier
  `8 passed; 7 failed` naming all seven — none dishonest, because the file grew from 10 to 11 to 15
  tests underneath the record. A number that changes when a neighbour is added was never evidence
  about the mutation, which is the whole argument for the new form. Note the
  earlier passes that re-measured mutations independently (B8: 13/13; B2: 4 re-performed) found
  their counts right, so this is drift rather than fabrication — but drift nobody can detect is the
  same problem the register had.

- **C15** — **C10 fixed three doors and four still ask how a figure is SPELLED.** C10 replaced the
  spelling test with a value test at two layers (`pact_doc::whole_number_past_holding`,
  `coerce::PAST_COUNTING` = 2^53). Four doors were measured and left, all 2026-08-09:
  1. **Fractional literals past 2^53 still collapse** — `9999999999999999999999e-2` and `…98e-2`
     both hash `sha256:2aa9f0c9…`. Two authored documents, one digest, which is the founding harm.
  2. **Money asks only about overflow** — `cost-per-request-under: 99999999999999999999 USD` loads
     clean with the checker holding `1e20`, and `1e999 USD` still offers the false
     *"or any smaller amount"*. Nominally B3's territory, but **B3 is closed**, so it has no owner
     without this row. A spend cap holding a figure the author did not write is the same shape as
     B10.
  3. **The `Value::Int` size door holds above 2^53** — `context-at-least: 9007199254740993` loads,
     `9007199254740993.0` is refused. One value, two verdicts, decided by punctuation — the exact
     defect C10 exists to delete, surviving at a fourth door.
  4. `when-full: 150%` is still *"but it is some text"* — `Ty::Percent` got a bottom end in C12 and
     still has no top end, tested nowhere.
  Minor and separate: the C10 test file's header still cites `lib.rs:1659`/`:1698`, which the C12
  round moved — a stale pointer inside the artifact that exists to be a reliable pointer.

- **D15** — **the knowledge corpus file list is computed, carried into the IR, and read by nothing.**
  The loader walks a `documents/` payload folder, builds `Value::Payload.files`, `pact show` renders
  it, `ir.py:208-226` `_document_names` turns it into `KnowledgeSpec.documents` (populated at
  `ir.py:620`) — and **`grep -rn "\.documents" adapters/python --include=*.py` returns exactly one
  hit, `tests/test_a_desk_that_answers_from_documents.py:76`**. `harness.ts` does not read payload
  file names at all. Measured in C5's pass, as its blast radius: a document dropping out of a corpus
  changes no trace, no system message and no report, in either port. This is the register's own
  signature defect with the arrow reversed — not *"a mechanism nothing on the authored path ever
  builds"* but *a mechanism the authored path builds faithfully and no reader consumes.* Bears on
  C2 (`unretrieved`) and the whole `knowledge:` story: an honesty channel that names corpora the run
  could not consult is worth less if the list of what a corpus contains reaches no reader either.

## Already documented — no queue row needed

`C7-bundle-mounting` · `C8-profiles` · `F1`–`F7` · `REGISTER.md`

## Deferred by decision — out of scope for this programme

`AC-1.5` (needs people) · `AC-3.5` (needs served weights) · `AC-6.3` (needs the AGNTCY schema) ·
`C6-publish` (release process) · `AC-2.5` (depends on publishing) · `AC-6.1/6.2` (needs two changes
to `gaia-ai-runtime`, another team's codebase)
