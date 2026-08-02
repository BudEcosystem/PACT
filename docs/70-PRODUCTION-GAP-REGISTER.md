# What PACT needs to be functional, meet its thesis, and ship

Every row below was found by running a command against this repository, and the
command is given so any row can be rechecked or disputed. Nothing is inherited
from an earlier document — several rows contradict earlier documents, which is
why they are here.

**Summary of the finding:** the parts that exist are good and are tested. The
problem was not quality, it was **reach** — a large fraction of the authoring
surface was read by nothing at run time, and the test count measured the parts
rather than the whole.

**Class A is now closed** (A1–A5b, plus the root cause as Phase 1.1) and so are
the twelve bugs of Phase 3. What replaced the individual fixes is the thing that
matters: three mechanical checks that make the defect class hard to reproduce —
**boundary completeness** (every `run()` parameter is declared authored or
host-only), **reachability** (every reader is reachable from an entry point by
call graph, not grep), and **authored-path coverage** (a run handed nothing but a
transport behaves as the document says). Each was mutation-tested by restoring
the bug it exists to catch.

**Class B — the thesis's acceptance criteria — remains mostly unmet**, and that is
now the bulk of the outstanding work. Nothing below claims otherwise.

Three findings from closing Class A are worth carrying forward, because each was
a test of *mine* that passed while the thing it named was broken:

* **A list of known gaps is a ratchet in one direction only.** `UNREACHABLE`
  asserted that broken things stay broken and could not notice a fix coming
  undone; severing the A2 door left the whole suite green.
* **A seam is not an effect.** The first `settings:` test checked the mapping
  table and what `apply_settings` returned — both true of a transport that then
  dropped every setting on the floor.
* **Normalising in a test moves the problem where nobody looks.** The Expansion
  Rule's central claim was held by two tests that trimmed both sides before
  comparing, and one of the two trims turned out not even to be load-bearing —
  its fixture was written without the trailing newline that every real file has.

---

## Class A — declared, tested, and wired to nothing

This is the defect this project produces most often, and it has produced it
again. The pattern: a mechanism is built, tested, and correct; the tests
construct its object directly; **nothing on the authored path ever builds one.**

Found by parsing every public function in `adapters/python/src/pact_adapters`
and comparing production call sites against test call sites, then checking each
survivor by hand.

### A1 — `survives-shortening:` reaches nothing · ~~critical~~ **CLOSED**

**What it was.** The G9 mechanism shipped built, mutation-tested and entirely
unwired: `grep -rn "Facts" harness.py` → nothing, `grep -rn "remembers" ir.py` →
nothing, no caller for `Facts.from_document` or `Facts.record`. The `Tidier`
accepted a `facts=` argument and restated correctly when given one; nothing on
the shipped path gave it one. The mutation test passed because it **built
`Facts` in Python** — the anti-pattern the build guidance warns about, committed
in the change written to prevent it.

**Fixed.** `ir.py:367` reads `remembers:` into `AgentSpec.facts`;
`AgentSpec.tidier` passes them to the `Tidier` — deliberately there rather than
in `run()`, because a caller who forgets gets a tidier that silently drops the
run's evidence, which is exactly what shipped. The harness records
`<slot>-was-approved` when a person clears a gate, and the worked example
declares that fact so the path is exercised by the shipped tree.

Held by
`test_what_the_author_wrote_reaches_the_run.py::test_a_fact_the_author_marked_survivable_reaches_the_tidier_from_the_document`,
which loads the real document and passes nothing. Both links mutation-tested:
removing `facts=self.facts` fails it, and so does removing the
`Facts.from_document` call.

**Residual: CLOSED.** `stops-being-true-when:` now has both halves. A run raises
the one trigger it can observe — `the turn ends` — through `_turn_ended`, and
`RunResult.facts_expired` says which facts did not survive, so a reviewer can see
what a NEXT turn cannot rely on. **A suspension deliberately does not raise it:**
a parked run is waiting, not finished, and expiring its facts would forget the
approval it is parked on, which is the whole of G9.

The other half is the one that matters. `stops-being-true-when:` is `list of
text` and the schema's own help offers *"`the file changes` or `the turn
ends`"* — nothing here watches a file, so `Facts.never_raised` reports every
trigger a run cannot raise rather than leaving the author believing their fact
expires.

Three things this needed that the first attempt got wrong, each found by
mutation rather than by reading:

* **Three lines end a turn and the wiring caught one.** A fact that expires or
  survives depending on which way the run happened to finish is not a property
  anybody could reason about from the document — the same multi-exit shape that
  made `run` need a declared boundary. All three go through `_turn_ended` now.
* **My behavioural test claimed to cover all three and covered one.** Traced:
  `pact:loop/standard`, the example's `careful` loop and a one-step ceiling all
  leave by the same line, and the third suspends rather than ending. Two
  mutations left it green. No fixture here reaches the other two, so
  `test_every_ending_routes_through_one_place` covers them **structurally** and
  says that is what it is doing.
* **The reachability walk could not see the new caller.** It resolved annotations
  on fields and returns but not on **parameters**, so `_finish(..., facts:
  "Facts | None")` calling `facts.something_happened()` read as dead. That is the
  fourth time this walk has needed extending, and each time it was reporting a
  live caller as dead — the safe direction, and still wrong.

### A2 — model selection has no shipped caller · ~~critical~~ **CLOSED**

`resolve()` filters the catalogue on `needs:`, runs the eval cases against each
candidate strategy, refuses when none passes, and recommends the cheapest that
would. It works. Its only caller is `tests/test_model_portability.py`.

`scoring.py` — the one entry point a person can run — imports `ModelEntry`,
`load_catalogue` and `needs_of` from that module and **not `resolve()`**.

**Fixed.** `--choose-model` on the scoring entry point calls `resolve()` through
`scoring._choose`, using the same two seams the named-model path already uses —
one transport per case, and the author's own `graded-by:` judge — so a chosen
model is measured exactly as a named one is.

The distinction the two now draw is the useful part: `_bind` decides
**admissibility** from what the catalogue publishes; `_choose` decides whether
the model can do the job **by doing it**, which is the only honest answer for
behaviour that is probabilistic. When nothing passes it returns the refusal and
the cheapest row that would pass, rather than a number.

Two false sentences in the command's own `USAGE` went with it: `PATH` never
defaulted to the working directory, and `--model` never fell back to "the
cheapest model that meets its `needs:`" — that was this function, which nothing
called.

### A3 — the learning cycle has no shipped caller · **CLOSED**

`Learner.cycle` had 27 test calls and no production caller; the whole 980-line
module had **no importer in `src/` at all**, so the held-out split, the
blast-radius classifier, the monthly spend cap and the drift measurement were
every one of them capabilities of the test suite.

**The door is `--propose FIELD=FILE`** on the scoring entry point
(`scoring.propose`). The person writes the proposal — nothing here invents one,
because there is no optimiser (AC-3.5) and adding one silently is the opposite of
what D23 asks. What PACT answers is *may this be applied, and does it help*.

Four defects surfaced only once something real called it:

1. **`_with` silently returned the incumbent** for any field but `instructions`,
   so a `description` proposal scored two identical specs at full price and
   reported *"held-out score did not improve"* — a true sentence about a
   comparison with no candidate in it. Now `CAN_BE_APPLIED` names the applicable
   set, `cycle` refuses before spending, and `_with` raises rather than agreeing.
2. **The first version of that refusal masked the blast-radius classifier.** A
   proposed `uses:` change was answered *"nothing in a run reads it"* — the wrong
   answer for a reviewer, and false: `uses:` is the skills the agent may read.
   `cls.needs_a_person` is now checked first, so a high-risk field is *held*.
3. **No suite held anything out.** With an empty holdout both scoring runs grade
   zero cases and the answer read *"held-out score did not improve (0% → 0%)"* —
   which reads as a measured tie. The module's own first named gate is *"a frozen
   held-out split, locked before the cycle starts"*; it now enforces that rather
   than assuming it, and the worked example declares two `split: held-out` cases.
4. **`_bind`'s reason was discarded** by the new door, printing *"name one with
   `--model`"* to somebody who had just named one — gating without recommending,
   which is the D11 failure.

Mutation-tested: severing the door, restoring the silent `_with`, dropping the
holdout guard, and un-declaring the example's splits each turn the suite red.

**A false row of my own, found by fixing the walk.** This register said
`Permissions.of` "has no per-field caller". It was **wrong**: `classify` calls
`rules.of(p.field)` one line after building `rules`, and always has. The
reachability walk could not see through
`rules = permissions or Permissions.default()` — a `BoolOp` — so it read a live
caller as dead and this document repeated that as fact for several rounds.
`UNREACHABLE` is now **empty**.

All five gaps found in that walk failed the same way: a live caller read as dead.
That is the safe direction, chosen on purpose, and it was still wrong every time —
so a new entry there should be suspected of being the sixth before it is believed.
Fixing it also turned up that the walk decided "what type is this expression" in
**two places**, and adding `BoolOp` to one of them changed nothing. Two places
deciding one question is how they come to disagree.

**And another of mine:** the reachability walk listed `evals.main` as an
entry point. It does not exist — `python -m pact_adapters.evals` imports
`scoring.main` — so the walk silently started from three places instead of four
and every unreachability assertion passed a little more easily.
`test_every_entry_point_exists` now fails on a name no module defines. The walk
also could not resolve a method called on a local variable, so it reported
`learning.cycle` dead while `scoring.propose` called it on the line above; it now
binds locals through **declared return annotations**, which adds edges from
declarations rather than from guesses.

### A4 — `Slo.assess` has no shipped caller · **CLOSED**

`limits:` ceilings *are* enforced in the harness; this was the separate
assessment path, and nothing called it — so a scored suite made no latency claim
in either direction while the example declared `finishes-within: 30s`.

`scoring._run_every_case` now times each case and `score` asks
`spec.slo.assess(latencies, "e2e")`. `e2e` only: `slo.py`'s own header explains
that time-to-first-token is not the time to the first step, and nothing here
measures it.

**The useful output is the refusal.** Six cases cannot support a p95, so the
report says `speed  no claim — 6 samples, need 20 for p95` rather than a figure.
That is the same treatment an eval bar over too few cases already gets, because
it is the same mistake: a percentile over a handful of runs reads like evidence
and is not. `UNGOVERNED` prints nothing at all — an author who promised nothing
does not need a line saying so.

### Phase 1.1 — the root cause, closed by declaration · **CLOSED**

`run()` takes sixteen optional objects and had **seven** hand-written
`X if X is not None else spec.X` lines for them. That is the cause of this whole
class: authored configuration and host overrides share one channel, so
derivation was optional, per-parameter, and invisible when omitted.

A `Bound` object was the plan and does not survive contact with two of the
sixteen — `summarise` and `tidy` close over the run's own `meter`, so they cannot
be built before the run exists, and an object holding fourteen-of-sixteen leaves
exactly the invisible gap it was for. So the boundary is **declared** instead:
`DERIVED_FROM_THE_DOCUMENT` maps each authored parameter to the expression that
derives it, `SUPPLIED_BY_THE_HOST` records the ones no document describes, and
`test_the_boundary_between_a_document_and_a_run_is_declared.py` makes the pair
total in both directions. A seventeenth parameter in neither map fails the suite,
so adding a mechanism forces the decision to be written down.

Three checks, and each catches the shipped bug independently: the register must
be complete, every declared derivation must appear in `run`, and a run handed
*nothing but a transport* must behave as the document says. Restoring
`chain = chain or Chain()` — the line that made the worked example's redaction
documents inert — turns three of them red.

**One live inconsistency found by it:** `loop = loop or spec.loop`. A `Loop` is
always truthy so no stages were being lost, but it is the same `or` that cost
`chain` and `teamwork` their documents, and one spelling for one rule is what
keeps the next one from being the falsy case.

### A5 — two fields have zero readers anywhere · **CLOSED**

Both are wired in **both** ports, and closing them turned up a third field with
the same problem that this register had not recorded.

**`answers-with:` — the one that mattered, and it was not on any list.**
`tier: core`, in the worked example, emitted by `pact show`, read by nothing.
The consequence had been sitting in the test suite in plain sight the whole time:
every scripted answer in the eval suite hand-writes
`"Decision: approved. Amount: 40 USD."` — because the shape the author had
already declared never reached a model, so a person had to write the format
twice. `_system_for` now appends it, last and under one heading, in the author's
own words (`one of approved, declined` is already the clearest statement of that
constraint; rewriting it into JSON Schema would put two descriptions of one rule
in the tree).

**`answers-with-mode:`** picks how. Its help promised *"PACT picks from the shape
you declared above, and records what it picked"* and nothing picked anything.
It picks `prompted` — the only mode all seven targets can honour and the only one
that needs nothing off this machine (D17). `native-json-schema` and `tool`
constrain the answer at the provider, which no transport here does, so they land
on `unenforced` with the line to type. Serving prose and calling it done would be
the silent degradation T7 forbids.

**`model-for-checking:`** is honoured for stages whose `does` is `check-its-work`
when a host supplies a second transport, and reported when it does not — so
"think with a cheaper model, check with a better one" is a capability rather than
a sentence in the schema. `run` gained one parameter for it, which is now a
*declared* decision in `SUPPLIED_BY_THE_HOST` rather than a sixteenth invisible
one: the model name is authored, which transport serves it cannot be.

Both ports had to change, and the suite made that non-optional:
`test_portability.py::test_the_typescript_target_agrees_too` went red the moment
the reference port started sending the shape, because two ports that hand the
model different instructions are not running the same agent. §7.28's lists A and
B, the Rust test that enforces them, and the README's scope sentence were all
updated in the same change — the front page now says nine governance keys, not
eight.

**And the payload bug that let this hide (Phase 3 item 10):** the conformance
payload in `test_portability.py` is hand-written, and it never sent `answersWith`.
A field absent from that dict is outside the comparison *by construction*, which
is why neither port asking for the author's declared shape went unnoticed for a
whole session. Projecting the payload from `pact show` is still open.

### A5b — three model settings no transport passes on · **CLOSED**

The reason they reached nothing is the one a reader would least guess. It was
never that no table mapped them: **the only transport that implemented
`apply_settings` at all was the Anthropic one, and that provider has no
penalties.** The locally-served transport — the one an air-gapped install
actually runs — implemented none of it, so `settings:` reached the wire on one of
seven targets.

`OllamaTransport` now maps nine of the twelve keys onto the OpenAI-compatible
`/v1/chat/completions` shape, which is exactly where the three live. `thinking:`
and `parallel-tool-calls:` are still returned as left over and land on
`RunResult.unmetered` — that endpoint takes neither, and a row mapping them onto
something approximate would make `unmetered` lie by omission.

**`tool-choice` was the one that needed translating rather than copying.** Its
help says *"auto, required, none, or one tool name"*, and a NAME is
`{"type": "function", "function": {"name": …}}` on the OpenAI-compatible endpoint
and `{"type": "tool", "name": …}` on Anthropic's — whose `required` is also
spelled `any`. Passed through as a bare string the OpenAI endpoint **accepts it
and it silently means nothing**, which is the translate-or-nothing line: a setting
in a shape the provider ignores is worse than one reported unhonoured, because
nothing says it did not happen. Anthropic's table was missing the key entirely —
that gap was in this repository's mapping, not in the API.

**A test of mine failed its own mutation here.** The first version asserted
`_WIRE` membership and what `apply_settings` returned — both true of a transport
that then drops every setting on the floor — and severing the settings from the
request left the suite green. `payload_for` is split out of `model_call` so the
request itself can be asserted without a served model. Same defect as the six,
one layer down: a seam checked instead of an effect.

### A6 — the full audit, now mechanical

`tests/test_every_field_has_a_reader.py` now checks **every field of every
kind** against every non-test source file in all three languages. It found 13
fields with no reader, which split cleanly:

**Genuine delegations, previously undocumented (8).** Each is a host
responsibility already named in `50-NOT-COPIED.md` §4 — *"Seven ways of
verifying a caller … the host does the checking"*, *"the store refuses a write
from a source `never-from:` names"*. They were correct all along and nothing
said so; now they are a reviewable list with reasons.

**Real defects (5),** carried in `KNOWN_GAPS`:

| Field | Why it is a defect |
|---|---|
| `agent.model-for-checking` | shipped last session, never wired |
| `agent.answers-with-mode` | no reader in any runtime |
| `settings.tool-choice` | no transport passes it on |
| `settings.frequency-penalty` | as above |
| `settings.presence-penalty` | as above |

`KNOWN_GAPS` **may only shrink**: a companion test fails the moment one of
these gains a reader, so closing a gap forces this register to be updated in the
same change. That is the failure mode this document would otherwise have itself.

**The Rust loader's passes are clean** — every validation pass is called from
`check`, verified by walking each `pub fn` against `main.rs`. An earlier version
of this line said "the Rust loader is clean", which was wrong:
`LoadReport::wake_ups()` and `Wait::wakes()` have no CLI caller, because
`waits_cmd` reads `LoadReport.waits` directly. The gap is *concentrated* in
Python runtime wiring, not confined to it.

---

## Class B — the thesis's own acceptance criteria

35 criteria in `docs/00-THESIS.md` §6. Assessed against the tree.

### Not met, and structural

| AC | Requires | Actual |
|---|---|---|
| ~~**2.1**~~ | golden set of ≥12 agents per framework | **MET for the breadth it claims.** **28 agents** across **9 workspaces** run over all seven Python targets and the TypeScript port, generated from the tree rather than listed — an agent added to `examples/` joins by existing. Compared on what the model was **told** and **offered**, not only on what it said back: the first draft compared traces alone, and deleting the answer shape *and* the written procedures from the second port's system text left all fifty-nine assertions green. A scripted model says the same thing whatever you tell it, so comparing what it said compares the script. **Bounded honestly:** the script answers without calling a tool, so multi-step tool sequences and parking runs are out of scope here — the second port publishes `durable_resume: unsupported`, and asserting over a documented divergence would be asserting that the ports differ. `test_portability.py` holds one agent in depth; this is breadth, and the thesis asks for both |
| **5.1** | ≥8 orchestration patterns incl. swarm, debate, blackboard, market | **PARTIAL — eight ship, three of the named ones cannot.** `examples/patterns/` holds `quorum`, `race`, `pipeline`, `swarm`, `weighted`, `escalation`, `debate`, `first-answer` — each a workspace that loads, and each **runs** to an answer or a clearable wait, which is what makes them shapes rather than documents. Held distinct on the WAITING RULE (`waits-for` / `enough-is` / `gives-up-after` / `starts` / `divides-the-budget` / `if-someone-fails`), so eight names for one behaviour fails. **`blackboard`, `market` and `auction` are absent and cannot be built on today's primitives**: `blackboard` needs a store agents read and write between turns; the other two need bidding and a settlement rule. `teamwork:` is a *waiting* vocabulary. Inventing shared mutable state between agents to satisfy a criterion would be the largest design change in the system made for the smallest reason — so this AC needs either those primitives designed on their merits, or amending |
| ~~**5.2**~~ | ~~≥6 loop patterns~~ | **MET.** Six ship: `standard`, `plan-then-do`, `react`, `reflexion`, `tree-of-thought`, `answer-more-than-once`. Each terminates (asserted by walking the stage graph AND by running it to `halted == final`), each tells the model something no other shape does, and the drift check between `spec/loops/*.yaml` and the two adapter copies is now **derived from the directory** — it was a hand-written pair, so the four new shapes joined the library and nothing compared them. **CodeAct is deliberately absent**: it means the agent writes code as its action, which is `runs-as: code`, refused in `docs/50-NOT-COPIED.md` because a spec naming code to run makes `pact check` decide whether that code is safe. Building it as a loop shape would reintroduce a refusal through a side door |
| **6.3** | export to Bud `AgentRecord`, A2A card, OSSA with a loss report | **PARTIAL — two of three, and the third is refused.** `exporting.py` ships `ExportReport` and `to_bud_agent_record`, beside the A2A card `pact card` already emits. The record's shape is **read off the real interface** in `gaia-ai-runtime/goose/ui/desktop/src/acp/bud.ts`, and a test parses that file — an exporter written against an invented schema is a file that loads nowhere, dressed as an integration. `silent_losses` is **computed from the source**, like `ImportReport.silent_drops`. **Six fields are left empty on purpose** — `version`, `revision`, `status`, `registryKind`, `runtimeBackend`, `invocation.url` — because they are registry and deployment facts, and PACT owning them would be the specification deciding where it runs; inventing a version and a URL fails the suite. The loss report gives each lost field its own sentence rather than defaulting to "unsupported", because *which kind of thing it is* decides whether losing it matters: a registry losing `instructions:` is expected, one losing `policy:` means an index that cannot tell a governed agent from an ungoverned one. **OSSA is refused, not omitted:** no OASF schema exists in this repository or in `gaia-ai-runtime` — the only matches are Italian translation strings, where `ossa` means "bones" — so writing one would produce exactly the artifact this project keeps finding. Blocked on the AGNTCY schema |
| ~~**7.1**~~ | a fuzzer proving no semantic element vanishes without a report | **MET.** `test_nothing_vanishes_between_the_file_and_the_document.py`, seeded (`SEED` fixed, every case prints the mutation that produced it — a fuzzer nobody can reproduce is a flake generator). Three properties: every key an author writes **arrives** in `pact show`; an unknown key inserted anywhere is **refused by name or visible**, never silently accepted and gone; a changed **value** reaches the document. Property A has a demonstrated mutation — making `Node::to_json` skip `because:` turns it red by name. **Property B does not, and the file says so**: the shape it guards is *accepted and dropped*, and no single edit produces it because `show` runs the same validation `check` does. It earns its place as the only property that can see a key the tree does not contain. Two claims in the first draft were wrong and are corrected in place: renaming a key mostly produced *"must have a 'name'"* — a refusal for a different reason that never reached the question — and "dropped by show" was a misreading of empty stdout from a command that had exited 1 |
| **1.5** | a non-programmer authors a working agent | protocol written, **never run** |

**AC-2.1 was the one that most weakened the headline claim.** "Byte-identical
across seven targets" was proven on **one** agent — an existence proof, not a
conformance set. It is now 28 agents over 8 targets, and the eight orchestration
patterns built for AC-5.1 are what supplied 25 of them: the two criteria turned
out to be one body of work.

### Partially met

| AC | Requires | Actual |
|---|---|---|
| ~~**3.2**~~ | predicate language evaluating `MMLU > 80 && SWE-Verified > 40` | **MET, and it uncovered a crash.** The comparison vocabulary was always in the format — `needs.scores` is `type: map of threshold` and `coerce.rs` parses `>`, `>=`, `<`, `<=`, `=` and a trailing `%` — so `MMLU: "> 80"` loaded cleanly and `pact show` emitted the string. `satisfies` then did `have <= threshold` with a float on the left and `"> 80"` on the right: **a `TypeError`, so the format's own documented syntax crashed the resolver** rather than refusing or working. `_threshold` and `_HOLDS` mirror `Op::holds`, and an unreadable threshold is now a refusal naming the shape to write. **There is deliberately no `&&`:** the conjunction is the map — every line has to hold — and an expression language is a language, with precedence and parentheses, which is the one thing a non-coder must never have to learn. Two lines that both have to be true is the same predicate without the parser |
| ~~**4.1**~~ | published coverage matrix of every DeepEval metric | **MET.** `providers.coverage()` emits a `MetricCoverage` artifact: every metric DeepEval ships, the URI an author types, and for the ones not offered, why. **50 ship, 47 reachable, 3 excluded** — all three abstract base classes. **Computed from the installed DeepEval, never listed**: a hand-written matrix is a second copy of somebody else's release notes and is wrong the first time they ship a metric, which is the coupling invariant E-4 exists to remove. The row that must never appear is *"shipped by DeepEval and not reachable from config"* — `Base*` and `Ragas*` are decisions with reasons, anything else in that bucket is a **defect**, and excluding one metric in a mutation makes the suite say so in those words. DeepEval being absent is reported as an absence rather than shown as an empty matrix, which is a different fact |
| ~~**4.3**~~ | evals run against a *remote* agent over A2A/HTTP | **MET.** `A2ATransport` binds an **agent** rather than a model: something already running behind a URL that does its own thinking. Held against a stub agent on localhost — **remote means not in this process**, and D17 is untouched. **The property that matters is not that it works**: a remote agent owns its own loop, so the author's stages, interceptor rules and ceilings decide nothing, and the run SAYS so on `unenforced` — a score that did not would attribute somebody else's behaviour to a document they never read. `tool_calls: unsupported` is the surprising lattice entry and the correct one: the remote agent may well use tools and **we do not see them**; `native` would claim to have observed something nobody observed. No default URL, so it cannot reach anywhere nobody chose. **A harness bug it uncovered:** `_meter_usage` unpacked `usage()` unconditionally, so a transport that HAS the method and could not measure a call took the run down with a `TypeError` — while the docstring one line above already said what cannot be measured is reported rather than guessed. That was true of a transport with no `usage()` and not of one whose `usage()` returned nothing |
| ~~**4.4**~~ | promote a failing production trace to an eval case in one command | **MET.** `--from-trace FILE --called NAME` writes the case into the agent's own `cases/` folder. **The security half shipped broken first and is worth recording:** `as_record` took `asked: str` from the caller, and the obvious thing to pass is the question as typed — so promoting a run on the worked example, whose author wrote `redact-card-numbers`, put `4111 1111 1111 1111` into a YAML file destined for version control. Measured, not reasoned about. `RunResult.asked` is now set by the harness from the message **after** the chain ran and `as_record()` takes no argument, so there is no parameter left to get wrong. `expect:` arrives empty on purpose — the answer that run gave is the wrong one, and writing it in would make the bug the specification — and **`evals/case-asserts-nothing`** is the new loader rule that makes that mean something: `expect:` is `type: anything`, so `expect: {}` loaded cleanly and a suite carrying a promoted case reported one more case than it could grade. `must-also:` counts as an assertion |
| ~~**5.5**~~ | a rejected learning candidate influences the next cycle | **MET.** `Learner.rejected` was a list nothing read, and its own comment beside the append stated the purpose it did not serve — *"a rejected candidate that is simply forgotten will be proposed again next cycle"*. Forgetting happened **twice over**: nothing consulted the list, and a `Learner` is built fresh per cycle so it did not outlive the process. `Refusals` keeps them in `.pact/learning/refused.jsonl` beside the spend ledger, and `cycle` recognises a repeat **before the evals run** — the expensive part of learning that an edit does not help is finding out, and finding out twice is paying twice for one answer. The first refusal's reason is handed back, so a reviewer sees why. **Two refusals are deliberately NOT remembered:** `enabled: off` and a spent ceiling are about the workspace, and drift is about how far the agent has moved since the baseline — remembering either would make an edit permanently unaskable because of where the agent happened to be when it was first proposed. Eleven refusal paths each built their own `Outcome`; they agreed only because nobody had added a twelfth, so they now go through one `_refuse` |
| **6.1/6.2** | `gaia-ai-runtime` discovers and binds | `pact discover` exists; the integration is unproven here |

### Met — held by a named test that asserts the thing

`2.6`, `4.2`, `4.5`, `5.3`, `1.3` (first half), and — since Phase 3 — `1.4`.

Six. **The previous version of this section listed fifteen, and was wrong
about at least three of them.** An independent pass checked each against the
tree:

| Was listed Met | Actually |
|---|---|
| **1.2′** | **MET, with one residual that is itself a finding.** `exploding.explode` writes a document back out as a tree, and **all eight pattern workspaces round-trip** through the real Rust loader — `load` is the CLI, because an `explode` checked against a Python re-implementation would prove the two agreed with each other. The alphabet is checked over the WHOLE document **before a byte is written**, which is the criterion's `MUST NOT emit a tree`: half a tree on disk is worse than none, because the half that wrote looks like it worked. A document carrying **payloads** gets its own refusal — a payload is bytes the loader carried verbatim and what reaches a document is a *reference*, so `refund-desk` genuinely cannot be exploded, and saying "unportable key" would send somebody renaming `$payload`, which is not theirs to rename. **The residual, and it is about an earlier fix of mine:** the round trip is exact *up to trailing whitespace on prose*, because the three spellings do not agree — `instructions: Be kind.` gives `"Be kind."`, `instructions.md` gives `"Be kind."` (trimmed by `pact_doc::prose`, the Phase 3 fix), and `instructions: \|` gives `"Be kind.\n"`. Phase 3 made two of the three agree and building the inverse is what showed the third still does not. **SETTLED — the block scalar is trimmed, and all three spellings now give one digest.** The argument that decides it is not about which newline is nicer: a plain scalar CANNOT express a trailing newline, and a real file ALWAYS has one, because every editor writes it and POSIX defines a line as ending in `\n`. So if the trailing newline is content, the inline form and the file form can never be equivalent and the Expansion Rule is false for prose **permanently**. The only reading under which all three agree is that trailing whitespace on a block is not part of what was written. `resolve_scalar` trims `Literal` and `Folded` styles. **What it costs, said plainly:** `\|` and `\|-` now mean the same thing and `\|+` no longer keeps what it asked to keep — `yaml_rust2` reports one style for all three, so telling them apart is not on offer, and the no-code ceiling says the distinction should not survive anyway. An author who has to know that a pipe keeps a newline and a pipe-minus strips it is being asked to learn YAML chomping indicators to write down what their agent should do. A quoted `"Be kind.\n"` still keeps its newline, because an explicit escape is a deliberate act and not a spelling anybody reaches by accident. **Nothing in the repository broke**, which is itself worth recording: no digest is pinned as a literal anywhere — every digest test computes both sides — so the change was invisible to the suite until `test_the_three_ways_of_writing_prose_are_one_document` pinned the equivalence, which is the property that matters rather than the value |
| **1.4** | **was** *"both tests normalise before comparing"* — `lib.rs:757` trimmed `instructions` on both sides and `example_refund_desk.rs:205` rewrote the node, while the two forms really did produce different digests. **Now MET:** Phase 3 bug 11 fixed it at load (`pact_doc::prose`), both normalisations are deleted, and reverting the trim turns the equivalence test red |
| **7.2** | **PARTIAL — the audit half is met, the profile half is not.** *"A core audit finds no capability-affecting literal"* is now held: **21 numeric module-level defaults**, each filed as author-settable (naming the field), not-about-capability, or deliberate-and-closed (saying what an author overriding it could weaken). One in none of the three fails, and the message asks the question rather than saying to add a name to a list. **The first version audited 141** — every upper-case global, most of them vocabulary tables naming the format's own words. Those decide what something is CALLED; a number decides *how much*, and how much is a capability. An audit of 141 rows is a bookkeeping exercise nobody reads. **The profile half needs a mechanism that does not exist:** `workspace.profile` is `tier: core` and selected nothing, silently. `pact check` now warns `loader/profile-selects-nothing`, so an author writing `profile: production` is told it changes nothing — which took the field out of `KNOWN_GAPS` (a warning IS a reader, by that check's rule, and the rule is right) and leaves the real remaining work here |
| **3.1, 3.4, 5.4, 3.3, 3.1b, 2.3, 1.1** | downgraded to PARTIAL — each has a real half and a missing half, detailed in the plan |

### Omitted entirely — seven criteria appeared in no table

`2.2`, `2.4`, `2.5`, `3.5`, `3.6`, `6.4`, `7.3`. The register covered 28 of 35
and did not say so, which reads as coverage.

- **2.2** — **MET.** `pact_adapters.conformance` emits a `ConformanceReport` over
  every (golden agent × adapter) pair — **28 agents × 6 adapters = 168 pairs**,
  against the framework-free control. **ε is declared and is zero**, with the
  reason in the artifact: every comparison is driven by a scripted transport, so
  two adapters running one agent have nothing legitimate to differ about and a
  tolerance would be room for a real divergence to hide in. The criterion's `or`
  clause is what the design turns on — a divergence is excused only where the
  adapter declared the feature `degraded`/`unsupported` **before execution** — so
  the lattice declarations are emitted *ahead of* the results and a test asserts
  that ordering. The report also states **what it does not cover**, in the
  artifact rather than in a docstring: a conformance report whose scope is
  implicit reads as covering everything. Mutation-verified by injecting an
  adapter that answers differently — it is caught and counted as an *undeclared*
  divergence, which is the clause that makes the whole thing falsifiable
- **2.4 / 6.4** — **PARTIAL, and the honest part is which two.** `importing.py`
  ships `ImportReport` and two importers, both with **zero silent drops**:
  an **A2A Agent Card** (which PACT itself exports, so the round trip is
  checkable) and an **Anthropic Messages request**. `silent_drops` is
  **computed from the source**, never maintained — a key in none of
  mapped/unmapped/not-portable is a drop by definition, so a construct nobody
  thought about lands there without anybody remembering. Mutation-verified
  three ways, including making the measurement itself return `()`.
  **The other five targets are blocked, not skipped:** every framework here
  defines its agents in *code*, and importing code means executing it — which
  D17 and D23 forbid outright — or parsing it, which is a different project.
  A card and a request body are the two places a framework's intent stops
  being computed and gets written down. AC-2.4 says *"real agents taken from
  each framework's own examples"*, and that is what remains unmet.
  Two design points the report makes visible: a **card is a facade**, so the
  import produces a stub and the report lists `instructions:`, `limits:`,
  `loop:` and `policy:` as still to write rather than letting somebody believe
  they imported an agent; and a **transcript is not an agent**, so `messages`
  is reported not-portable rather than freezing one exchange into a
  specification
- **2.5** — **PARTIAL, and the missing half is named.** `adapters/out-of-tree/echo_adapter/`
  is an eighth adapter that lives outside the core: in no package the core installs,
  imported by nothing under `src/`, in no registry. A test puts its directory on
  `sys.path` the way a separate checkout would and the agent runs.
  **The property is structural, not documented.** `Transport` is a `Protocol`, so
  conformance is by shape — an object with `model_call` IS one, nothing is inherited
  and there is nowhere to register. A registry is the one thing that could quietly
  make "no core modification" false while every behavioural test still passed, so
  there is a test asserting the core mentions this adapter **nowhere** and another
  asserting `Transport` is still a Protocol. Both mutations fail.
  **The shortfall:** the criterion says a separate *repository* and this is a separate
  *directory*. A directory proves no core CHANGE is needed; a repository would also
  prove no core RELEASE is needed, and that needs publishing — row C6. The plugin ABI
  the row also asked for turns out not to be a thing that has to exist: a Protocol is
  the ABI, and adding one would be inventing the coupling the criterion is about
- **3.5** — **PARTIAL: the mechanism ships, the measurement does not.**
  `optimising.improve_on` writes a proposal from what the TRAIN cases got wrong,
  and `Learner.cycle` gates it exactly as it gates a hand-written one — so in the
  shipped example every proposal is held for a person, which is the only
  arrangement D23 permits near decision logic.
  **The property worth more than the rest: it never sees the held-out split.** An
  optimiser tuned on the cases it is scored against reports an improvement that
  exists only in the tuning, and it refuses outright when nothing was held out.
  `MARGIN` is declared at five points and is deliberately stricter than
  `Learner.cycle`'s own `after > before`: the cycle asks *is this better*, right for
  applying an edit, and the criterion asks *better BY A MARGIN*, right for claiming
  an optimiser works.
  **NOT MET:** *"improves … by a declared margin"* is an empirical result against a
  small model, and no model is served in this environment. A scripted stand-in can
  prove the mechanism and cannot prove an improvement, so the claim is unmade rather
  than asserted. Blocked on served weights.
  **A test of mine that survived its own mutation:** the first version asserted no
  held-out case reached the optimiser's PROMPT — and the prompt carries each case's
  text, not its key, so including one leaked nothing it looked at. It asserts on the
  proposal's rationale now, which names exactly what was written from
- **3.6** — **MET, and the row it replaces was wrong about this repository's own
  code.** It read *"enforced at neither resolve time nor run time"*. The run-time
  half was already there: `Limits.reached` stops a run on `finishes-within` and
  `cost-per-request-under` against what that run actually spent, which is
  enforcement at run time against measurements. That is the sixth register row of
  mine to be false about code sitting in the tree, and the reason the registers
  that matter are computed from source rather than maintained.

  **The resolve-time half is new.** `slo.against_the_catalogue` compares the two
  ceilings an author wrote — `tokens-at-most` and `cost-per-request-under` —
  against the price the catalogue publishes, and names the one that governs
  nothing. 100k tokens at 1 USD/Mtok costs 0.10–1.00; a cap of 0.01 means the
  money ceiling always bites first and the token ceiling is decoration. It stops
  nothing: `Limits` does the stopping, and this module deleted a `Budget` to
  establish that there is one enforcer. Two doors, because `score` returns before
  binding a model when a workspace has no cases — right for the eval command, and
  wrong as the only way to reach a check whose whole point is to precede a run —
  so `pipeline`'s stage literally named `resolve` runs it with no suite at all.

  **There is deliberately no latency half, and that is a finding rather than a
  gap.** The criterion asks for TTFT/TPOT *against catalogue estimates*. A
  catalogue latency figure is not a property of a model: the same weights answer
  in 200 ms on an H100 and 8 s on a laptop. Publishing one would be the exact
  substitution `models/catalog.yaml` refuses for price — *"a number nobody
  published, given to an author as though somebody had"* — and would hand out
  resolve-time verdicts wrong on most machines. `first-reply-within` and
  `per-word-under` come back on `RunResult.unmetered` instead.

  **A surviving mutation found a real bug and then a better answer.** Mutating
  `USD` out of the finding's sentence left the suite green, which exposed that
  `resolve._cost` reads `raw.split()[0]` and **discards the currency word** — so
  every price this package produces is a bare float that everything downstream
  reads as dollars. A cross-currency branch was written for it, and then the
  loader turned out to refuse the case already, in better words:
  `loader/currency-nothing-can-price` says *"1000 JPY is not 1000 USD"*, and a
  bare number is refused as *"should be an amount of money"*. **The branch was
  deleted rather than kept** — a second enforcer of a rule already enforced is how
  one ceiling comes to mean two things, which is this module's own argument
  applied to itself — and both loader rules are now pinned by tests, because
  together they are what makes the arithmetic same-currency by construction
- **7.3** — **MET.** `pact_adapters.pipeline` runs `validate → resolve → build → eval →
  report` over one workspace, offline, as `pact-pipeline`. Every stage existed and
  **nothing composed them** — `resolve` was reachable via `--choose-model`, `build` is
  what `pact show` produces — but only as separate things somebody had to know to run
  in order, which is not a pipeline. Two properties carry it, both mutation-tested:
  **a stage that cannot be ATTEMPTED does not fail the run** (a machine with no model
  served still gets a validated, resolved, built tree — the four fifths somebody
  fixing a document needs long before they have weights, and failing there answers a
  question they did not ask), and **a REFUSED stage stops everything downstream**
  (nothing said about a tree the checker rejected can mean anything). Offline is a
  property, not a hope: the only socket is the eval stage's call to a model on this
  machine, and an unserved one gives `--` with the line to type rather than a network
  error

**Why this section was wrong.** It was written by reading the tree and asserting
a verdict — the same method that produced every defect it documents. Nothing
compared it back. It is now the third document in this repo found asserting
coverage it did not have, which is why Phase 0 of the plan extends the mechanical
documentation check to `README.md` and the FRD.

---

### Phase 1.2 — the loader→adapter boundary, made total · **CLOSED**

The `pact show` → `AgentSpec.from_document` boundary had no completeness check at
all. A field could be emitted by the Rust loader, sit in the JSON, and be dropped
by `ir.py` with **nothing anywhere comparing the two** — which is how `remembers:`,
`run-inputs:`, `ports:` and `variants:` each came to be authored, validated,
emitted and read by nobody.

The other two checks start from the schema and ask whether a reader exists. This
one starts from **what the loader actually emitted for the real worked example**,
which is the only view that knows what an author's tree produces rather than what
the format permits. Two directions, both enforced: an emitted key is read or named
with what reads it instead, and a name whose key the loader no longer emits must
be deleted.

**"Nothing reads it" is not an allowed entry.** That is the defect, and it belongs
in `KNOWN_GAPS` where the only-shrinks rule applies.

*A correction of my own, mid-build.* The first version parsed the AST of
`from_document` for string literals and reported `remembers`, `interceptors`,
`policy` and `teamwork` as unread — because each is read by a **helper** it calls
and the literal lives there. A parse that stops at one function answers a question
nobody asked. It now **records** key access during a real load, which answers the
right question — *did the thing that turns a document into a run look this key up*
— and follows every helper for free. Severing either the `remembers` or the
`answers-with` reader now fails it by name.

---

### The defect, reproduced today, in the work meant to close it

Four modules written **this session** — `exploding`, `importing`, `exporting`,
`optimising` — shipped with no `main`, no console script, and no importer in
`src/`. Built, tested, mutation-verified, and reachable from **nothing a person
could type**. That is exactly the failure this register exists for, committed by
the change written to prevent it, which is the third time that has happened here.

It was missed because `test_no_new_reader_has_become_unreachable` looks for
functions named `from_document`, `of` or `for_document` — **a hand-written name
list**, the same shape of scope failure corrected three times elsewhere in the
same suite. A module whose public function is called `explode` was invisible to
it.

`test_every_module_is_reached_from_somewhere_or_is_a_door` closes it by asking
the question about MODULES rather than about names: every module is reached from
an entry point, or is a **door** with an installed console script, or is a
**library** with a row saying what reaches it. Nothing else. Adding an orphaned
module now fails by name, and a door that loses its console script fails
separately.

All four have doors now — `pact-explode`, `pact-import`, `pact-export`,
`pact-improve` — and the P-1 audit immediately noticed that two of them had
become commands, because a door reads a file and a run-path module may not. That
is two independent checks disagreeing usefully about the same change.

**And three more defects in the same day's work, found by running it rather
than reading it.**

* `pact-import` used `Path` in its `main` and imported it nowhere. Every library
  test passed — `from_a2a_card` was covered eight ways — because **nothing had
  ever invoked the door**. Registering a `main` as a console script without
  running it makes an untested function somebody else's crash.
* `A2ATransport` recorded an agent that counted tokens and named no price as
  costing **0.00**, which is a claim the call was free. `models/catalog.yaml`
  forbids that substitution in its own words, and `_meter_usage` already handled
  `None` for exactly this case one line after saying `0.0` would be the mistake.
  Written in a file that quotes the rule, an hour after reading it.
* `explode` chose whether to write a directory's settings file with
  `settings or not said.wrote` — a GLOBAL question standing in for a local one.
  It was right for every valid document by accident, and produced a workspace
  with no `workspace.yaml` for a document whose only top-level field was prose.

**The door test needed two goes, for the reason everything else here did.** Its
first version ran each door with `--help`, which returns before the line that was
broken — so removing the `Path` import again left it green. It now runs every
door with arguments that reach past parsing into real work, and asserts a
refusal is a sentence rather than a stack. That is the fourth time in this
session a check of mine tested the seam instead of the effect.

## The walk that could not see the thing it was for

**The orphan check looked at three function names.** `test_a_reader_is_reachable
_from_a_run.py` asked *"is this reachable from an entry point"* by walking a call
graph, and its `test_no_new_reader_has_become_unreachable` filtered to functions
called `from_document`, `of` and `for_document`. Everything else was outside its
reach **by construction** — the same shape as the TypeScript port having no
producer, which this register already records as a root cause.

It was found by mutation and not by reading: the callers were deleted from a
mechanism wired an hour earlier, and the file stayed green.

**`ENTRIES` did not include the doors.** Six `main`s that `pyproject.toml`
installs as console scripts were not entry points to the walk, so `explode`,
`from_a2a_card`, `to_bud_agent_record`, `improve_on` and `run_pipeline` all read
as reachable from nothing, and nothing said so. Adding them cut the orphan list
from 36 to 25.

**Three real mechanisms were reached by nothing but their own tests.** Each had a
full test file and passed every assertion in it:

| | what it did | what that meant |
|---|---|---|
| `harness.delegate_by_running` | a hundred lines with `Grant.spend` and a budget charge-back | `scoring` ran every eval case with **no `ask_member`**, so a delegation parked the run, the case came back "did not answer", and the model was blamed. **Scoring an agent with a `team:` measured a suspension** |
| `optimising.measured` | AC-3.5's *"by a declared margin"* | no report asked whether a margin was cleared, so the criterion's own emphasis was a property of the test suite |
| `providers.coverage` | AC-4.1's coverage matrix | computed correctly and **published nowhere**, which is the whole of a criterion that says *published* |

All three are wired, each mutation-tested by severing the wire. `measured` also
took a signature change — it asked for a `Learner` and used it for one count, so
the one reader that has both verdicts could not call it and computed the same
three facts itself. Two functions answering one question is how they come to
disagree.

**The check that catches the next one is a different question.** The call-graph
walk is imprecise in the safe direction — it cannot see through a module alias,
a default argument, a dict of handlers or duck-typed dispatch, and 22 live
functions still read as dead there. A list of 22 declared exceptions saying *"the
tool is imprecise here"* would rot on contact. So
`test_nothing_public_is_named_by_nothing.py` asks a question the source answers
exactly: **does any file in `src/` so much as mention this name?** No graph, no
types. It would have caught all three, it has one declared exception
(`interceptors.guard`, the §5.5 host escape hatch, which is public precisely so
that nothing internal calls it), and that exception is deleted the moment
something does.

**And two of my own tests failed their mutations first.** The door test ran each
door with `--help`, which returns before the line that was broken — so removing
the `Path` import again left it green. The `ask_member` test read the source and
asserted the keyword was passed, so mutating the builder to `if False else None`
kept the keyword, passed `None`, and stayed green: the defect reproduced inside
the test written to catch it. Both now exercise the effect.

---

---

## Phase 3 — the twelve real bugs

Found by audit, fixed and mutation-tested unless marked. Nine of the twelve were
in the **second port or the loader**, and the reason they clustered there is one
bug: number 10.

| # | Bug | State |
|---|---|---|
| 1 | **`pact discover` labelled `limits` as `slo`** — the key said `slo` and the value was the whole termination block, so a runtime reading it for a latency promise got `steps-at-most: 12` as a service level | **fixed.** Both keys emitted, each with its own. `finishes-within` is in both on purpose — the author's file says it is *"both the promise and … the wall-clock stop"*. The old assertion was `desk["slo"].is_object()`, true of the wrong value: **an assertion about a type cannot catch a value that is the wrong thing** |
| 2 | **`discover` emitted no governance** — no `policy`, `interceptors`, `teamwork`, `remembers`, so a host routing work could not tell an agent that stops for a person from one that does not | **fixed.** A `governance` block of the author's own names, so the runtime can fetch the documents by them. An agent governed by nothing says so rather than omitting the key — a missing key and "no policy" read alike and mean different things |
| 3 | **The TS port dropped nested `limits.*` keys in silence** — `feel`, `first-reply-within`, `per-word-under`, `measured-at`, `asks` | **fixed.** `LIMITS_FIELDS` names what it reads and the rest is reported. §7.28 accounted for these five under `slo.*` — **a row that could never fire**, because `pact show` nests them under `limits:` and nothing ever arrives under `slo:` |
| 4 | **The undeclared-key guard was on the conformance driver, not the library.** §7.28 said this port *"refuses to start"*; that was true of `run-trace.ts` and of nothing else | **fixed.** `run` refuses with `SpecError`; the driver calls the same function rather than keeping a second copy of the rule |
| 5 | **TS hardcoded `unit: "USD"`** — `cost-per-request-under: 500 JPY` reported as `500 USD`, and the sentence *is* the contract | **fixed.** `spend()` returns amount and currency from the one authored line. Two follow-ons: the unit is now **appended** conditionally (interpolating gave `"(0 of 0 )"` once the unit could be empty), and `stoppedBy` now projects `unit` and `sentence` at all — **neither was in the trace, so the wording the architecture calls the compared contract could not be compared** |
| 6 | **`unmeterable` arity differed** — two questions in Python, one in TS | **fixed.** Both ask `countsTokens` and `pricesMoney` separately, so a model with a known window and no price keeps `tokens-at-most`, which is that field's own documented promise |
| 7 | **`httpx` imported and not declared** | **fixed**, and a second one found with it: `openai`, imported at module level and resolving only through `openai-agents`. `test_the_manifest_names_what_the_source_imports.py` now holds both, and checks what `scripts/pact-eval` probes for — that probe decides whether the bare-interpreter fallback is used at all |
| 8 | **`scoring.py` USAGE claimed `PATH` defaults to the working directory** | **fixed** in the A2 round |
| 9 | **Empty `teamwork: {}` reported a false "not applied"** — `{}` is truthy in JavaScript | **fixed.** `Object.keys(...).length`. A false "not applied" tells the author their file contains something it does not |
| 10 | **The conformance payload is hand-written** — so a field absent from it is outside the comparison **by construction**. This is why 3, 5, 6 and 9 survived, and why `answers-with:` stayed unported for a session while `tier: core` and in the worked example | **fixed, structurally.** One `_payload_for` instead of two inline copies, and `test_every_key_the_loader_emits_is_sent_to_the_second_port_or_accounted_for` compares it against `pact show` — every emitted key is sent or named with its §7.28 category. There is no third option, and "nobody added it to the dict" was the third option |
| 11 | **Flat and tree forms were not byte-identical** — the Expansion Rule's central claim | **fixed at load.** `pact_doc::prose` trims the trailing newline, because `instructions.md` saved by any editor gave `"Be kind.\n"` where inline gave `"Be kind."` — two documents, two digests, from the two forms the format promises are one. **Both test-side normalisations are deleted.** The one in `lib.rs` turned out not even to be load-bearing: its fixture was written in Rust *without* a trailing newline, which no real file has, so the trim was a no-op there and the divergence lived entirely in files. Measured on a two-file workspace, not reasoned about |
| 12 | **`needs.scores` could not be satisfied by any data** — every `ModelEntry` was built `scores={}` and the `benchmarks:` key was never read | **fixed.** `_benchmarks` reads the `value:`/`provenance:` shape and a bare number. A figure written `unknown` is **dropped, not zeroed**: zero satisfies no threshold and reads as a measurement. The shipped catalogue still publishes none and says so, so `needs.scores:` refuses here — correctly, which is the distinction the trap destroyed |

---

## Phase 4 — dead code, and the two items that were not dead

Deleted outright (zero references anywhere): `Pin.explain`, `AgentSpec.load` and
its now-unused `import json`, `Script.reset`, `export type Outcome`,
`Limits.from_document`, `Slo.from_document`, `crates/pact-schema/examples/schema_check.rs`,
`.claude/at-most-once-wiring.patch`, `research/exp/gap-r2-2/` (orphaned, no
write-up, 518 KB log), `adapters/python/experiments/*.log`, `minimal_t4.py`, and
two empty directories. `.gitignore` gained the five entries that would otherwise
have been captured by the first `git add` — the repository has no commits.

**The vacuous test, resolved.** `test_one_order_across_kinds.py` declared
`WATCHING_RUNS_AT = 100` and asserted `100 > 50 > 20 > 10`. That compares four
integer literals, cannot fail, and `Bus` never sorted by band — so the safety
property its comment claimed was enforced by nothing. Both are deleted and the
behavioural test kept: moving `bus.emit` above `chain.run` — the edit that looks
like an improvement, *"log it before anything changes it"* — turns it red.

**`Wait::wakes` and `LoadReport::wake_ups` were not dead; their consumer was
missing.** They were the only two functions in `pact-loader` with no caller
outside a test, and the reason was in the projection: `to_json` handed a runtime
every wait and no way to tell which of them a scheduler can time. So a consumer
complying with §9.4 G14 had to reimplement the rule, and could reimplement it
differently. The JSON now carries `wakes` per wait and a filtered `wake-ups` list.

Worth recording how nearly this was mis-tested: **every wait in the worked example
carries a deadline**, so hardcoding `wakes: true` and dropping the filter both
passed every example-based test. The assertions had to go on the one fixture in
the tree with a wait that never ends.

**`Op` cannot be narrowed, and my own audit was wrong to list it.** It is the
field type of a public enum variant (`Threshold { op: Op }`), so Rust requires it
to be at least as visible as that enum. The other five — `is_folder`, `source_of`,
`from_node`, `ROLES`, `PAYLOAD_MARKER` — are now `pub(crate)`.

---

### AC-2.3 / invariant P-1 — measured rather than assumed · **HELD**

*"No adapter reads author files"* is the invariant everything else leans on, and
nothing checked it. **Twenty-one modules make up the run path and not one opens a
file** — asserted per module, so a failure names which. Plus the behavioural half:
an `AgentSpec` built from a document with **no `source=` and no tree** runs, which
is the case a registry or a message queue actually has.

A run path that reached back into the folder would mean the Expansion Rule had two
implementations — one in Rust and one accidentally in Python — and every
portability claim here would be about a tree rather than a specification.

The commands are named separately with the reason each is not a breach: `scoring`,
`pipeline`, `conformance` and `exploding` are things a person types at a tree, and
`learning`, `watches` and `resolve` touch only the derived area or the price list.
The line P-1 draws is not *"no Python touches a disk"* — it is that the code
turning a document into a run does not.

**Two of my own excuses were wrong.** `judge` and `providers` were filed as
disk-reading commands and neither opens a file — `judge` asks a served runtime
over HTTP, `providers` imports DeepEval. I had assumed rather than measured, and
the reverse check caught it on the first run. They are on the run path now, where
their cleanliness is asserted rather than excused.

---

## Class C — production readiness

Not thesis criteria; the things a team hits in week one.

| # | Gap | Why it matters |
|---|---|---|
| ~~**C1**~~ | **CLOSED. Spec versioning.** `pact-version:` is a `tier: expert` workspace field, and `pact_doc::SPEC_VERSION` is the one string the loader enforces and the discovery index publishes — it was a bare literal inside `discover.rs`, so the only versioned thing in the system was the projection. Absent stays the ordinary case: a no-code author writes no version line and the tree is read as this build's version, so the shipped example is unchanged. Stating a version this build cannot read is an **error**, not a warning, because refusing loudly is the entire reason to write the line — a document read under the wrong version of a format loads, validates, and means something else. Both mutations (removing the gate, downgrading it to a warning) turn the suite red | a format with no version cannot evolve without breaking every consumer silently |
| **C2** | **`bundle.from:` resolves nothing** — still true, and no longer silent. `from:` is `required: yes` and no pass in this loader resolves it, so a workspace could declare three bundles, load cleanly, and contain **not one definition from any of them**, with the author told nothing. `loader/bundle-not-mounted` now says so. A **warning, not an error**: the field's own help says `from:` may be *"a path inside this workspace, or a name your platform team publishes"*, and the second kind is resolved by a host that knows its registry — refusing outright would break the case the field was written for, while silence misleads the case it was not. **Mounting itself remains unbuilt**, and that is what this row still tracks: it needs path resolution, merge semantics, collision rules and a decision about what mounting does to the digest. A pre-existing test asserted an unmounted bundle produced `len() == 0` diagnostics under the name *"is not accused of anything"* — which conflated *not accused* with *told nothing*, and is now the narrower assertion it always meant | declared, scope-checked, and cannot actually mount anything |
| **C3** | **TypeScript port is behaviour-only** — still true of the four governance mechanisms, and now *narrower*: it honours `answers-with:`, reports keys **inside** `limits:` that it does not read, and **refuses** a field it does not know from the library rather than only from the test driver | interceptors, context-policy, policy, teamwork all `unenforced` there |
| **C4** | **G9 is Python-only even once wired** | see A1. `remembers:` is never put on the wire to the second port, so it is a §7.28 *"never arrives"* key rather than one reported on `unenforced` — and if it did arrive the port now refuses and names it, which is the right answer for a line that changes what a run may forget |
| **C5** | **No transport reports usage on most targets** | `cost-per-request-under` and `tokens-at-most` land on `unmetered` in practice. Both ports now ask the two questions separately (`countsTokens`, `pricesMoney`), so a model with a known window and no published price keeps `tokens-at-most` — which is that field's own documented promise and was being lost as a side effect |
| **C6** | **PARTIAL — installable now, not yet published.** `cargo install --path crates/pact-cli` puts `pact` on the PATH and works: the schema and the model catalogue are `include_str!`, so an installed binary carries them. The adapters were **not a package at all** — no `[build-system]`, so `uv` refused to install entry points and `pip install` could not work; that was the whole of the Python half. `pact-eval` and `pact-conformance` are console scripts now. Three things `cargo package` refused, all fixed: path dependencies with no version, no description on any crate, and a `description` field left at `uv init`'s *"Add your description here"*. **Publishing itself remains open** and is a release process rather than a code change — the crates must go to crates.io in dependency order, and `include_str!` reaches outside each crate's own directory, which a published crate cannot do. **A warning the gate could never see:** `--all-targets` builds with debug assertions ON, so `SpecSource::Unsafe` — deliberately unconstructible in a release binary, which is what stops `PACT_SPEC` deciding the governance columns in an installed copy — is live there and its `dead_code` warning appeared only on the first `cargo install`. `cargo clippy --release -p pact-cli -- -D warnings` is now in the gate | there is no `pip install pact`, no released binary; everything is `cargo run` from a checkout |
| ~~**C7**~~ | **CLOSED.** `.github/workflows/gate.yml` runs `scripts/test-all.sh` on push, on pull request, and weekly — the schedule so a dependency that moved under us is found by the calendar rather than by somebody's next commit. **It runs the script rather than re-listing its steps**, and a test enforces that: a workflow spelling out `cargo test`, `clippy`, `pytest` is a second copy of the gate, the two drift, and the interesting failures become the ones only one of them catches. **A hole in the gate itself, found while writing it:** `test-all.sh` ran the adapter suite whether or not the CLI had been built, and **39 test files** read the worked example through that binary — measured, **19 tests skip** without it and the script exited 0 regardless. A gate reporting green over a suite that has quietly stopped checking invariant P-1 is this register's own defect wearing the gate's clothes. It now refuses. The TypeScript type check still skips locally when `node_modules` is absent, on purpose — a contributor without node gets a useful run — and CI installs them so the skip never fires there | the suite is green because it is run by hand |
| ~~**C8**~~ | **CLOSED.** `.pact/` still lands beside the workspace by default, and **`$PACT_DERIVED_DIR` redirects the whole derived area** — so a read-only checkout is run by pointing it somewhere writable rather than by copying the tree. An environment variable and not a field: where derived output lands is a deployment fact, and a workspace that named its own would stop being runnable in two places. **The worse half was that it did not degrade** — `base.mkdir` raised inside a bus handler, so an observability feature took down the run it was only observing. Writability is now asked ONCE when the watches attach (a run that discovers it on the fortieth event has already said nothing about the first thirty-nine), the run survives and names the record it could not keep on `RunResult.unwatched`, and both learning ledgers degrade the same way — a cycle that fails because it could not write down that it happened has turned bookkeeping into a run failure. **A regression this change first caused:** the writability probe CREATES the area, so a workspace declaring no `watch:` acquired a `.pact/` for having been run — caught by an existing test, and the probe is now skipped when there is nothing to write. It also bit inside this repository earlier: a test pointed a real learning cycle at `examples/refund-desk`, whose spend ledger the spend-ceiling test then `copytree`d into its own fixture — twenty-eight recorded runs at `money: 0.0` diluted `per_run` to zero and five passing tests went red. Both copies exclude `.pact` |

---

## What to do, in order

Ordered by consequence. Each states the test that would prove it landed.

1. **Wire G9 (A1).** *Proof:* an approval recorded before a shortening still
   gates the call after it, driven through `pact show` with nothing passed in.
2. **Give model selection a door (A2).** Add `--choose-model` to the scoring
   entry point, calling `resolve()`. *Proof:* the command refuses a failing model
   and names a cheaper passing one.
3. **Wire or delete `model-for-checking` and `answers-with-mode` (A5).** A field
   with no reader should not be in the schema. *Proof:* a test asserting every
   `agent` field has a reader — which would have caught all of Class A.
4. **Build the golden set (AC-2.1).** Twelve agents spanning the patterns, run
   across all seven targets. *Proof:* the conformance suite over twelve, not one.
5. **Version the spec (C1).** *Proof:* a document declaring an unknown version
   is refused with the version it needs.
6. **Wire the learning cycle (A3)** or state it as delegated.
7. **Ship loop and orchestration patterns (AC-5.1, 5.2)** as library documents.
8. **Run the human trial (AC-1.5).** Blocked on people, not code.

---

## The systemic fix

Four separate mechanisms have now shipped built, tested and unreachable —
interceptors, context-policy, the model pin, the team budget — and this audit
found four more. Each was caught one at a time, after the fact, by an
adversarial pass.

**The fix is a test, not more vigilance:** for every field in the schema, assert
that some production module reads it, or that it appears on an explicit
"declared and delegated" list. That test would have caught A1, A2, A5 and A6 on
the day each landed, and it is the only item here that prevents the next one.
