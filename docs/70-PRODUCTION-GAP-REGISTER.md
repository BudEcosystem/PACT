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
behaviour that is probabilistic.

**Amended.** That door could not be opened for a round — `_choose` handed a
one-argument factory to a two-argument protocol, so every run of the flag died
with a `TypeError` six frames inside the search — and once it was opened, five
further defects behind it turned out to be live and two of the tests holding it
did not bite. Written up in full, with the measurements, in
`docs/remediation/A1-choose-model-arity.md`. One sentence of this row is now
wrong and is corrected there rather than deleted here: when the model the agent
names does not pass, the search **binds the cheapest row that does** and says so
on the report's `model` line. It refuses only when nothing passes at all.

Two false sentences in the command's own `USAGE` went with it: `PATH` never
defaulted to the working directory, and `--model` never fell back to "the
cheapest model that meets its `needs:`" — that was this function, which nothing
called.

**Amended again (queue row D3).** Two further facts about the same door.
`resolve()` could render a `PORTABILITY:` report claiming catalogue rows *"met
the requirements and none reached the bar"* after building zero transports and
running zero cases — a measurement claim over a search that took no measurement —
and the door's factory is now checked for **callability and arity** rather than
only against `None`, so the one-argument factory that was this row's original
defect is refused at the door instead of four frames inside the search. Measured
in full, with the mutations that turn each holding test red, in
`docs/remediation/D3-transport-factory-defaulted-to-none.md`. That document also
records three unfixed instances of the same class still live in this function —
`agent_key`, `baseline` and `scores` — which have no row of their own here.

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

**Amended (queue row A2).** The paragraph above is about the **run**. The
**check** is a separate promise and it was not kept. `model-for-checking:` was
outside `allow-egress:` entirely: a hosted second model in a workspace saying
`allow-egress: []` printed *"OK — loaded cleanly"*, while the same id one line up
under `model:` was refused — the boundary held or did not hold depending on which
of two adjacent lines the author wrote the name on. The cause was a list of four
field names written in Rust where the specification declares which fields bind a
model, and moving that answer into `spec/schema.yaml` then exposed the same
defect one layer out: `catalog.default:` — the model every unpinned agent
actually runs — carried no `names: pact:models`, so a hosted or misspelt default
loaded clean too, on a workspace the Python port already had a named problem code
for (`catalog/unknown-default`). The recording half of the same rule was narrower
still: `stt`/`tts` were asked only of `agent.model`, so a voice agent's
`model-for-checking:` or `summarised-by:` carried a recording out of the box
under `allow-egress: [llm]`. All of it is now held at check time by
`crates/pact-cli/tests/every_model_a_document_names_is_held_to_the_boundary.rs`
(15 tests, cases read off the shipped specification rather than listed). Root
cause, blast radius, twenty-seven enumerated failure cases with six marked
uncovered, the six mutations, and what is still open are in
`docs/remediation/A2-egress-model-for-checking.md`.

Both ports had to change, and the suite made that non-optional:
`test_portability.py::test_the_typescript_target_agrees_too` went red the moment
the reference port started sending the shape, because two ports that hand the
model different instructions are not running the same agent. §7.28's lists A and
B, the Rust test that enforces them, and the README's scope sentence were all
updated in the same change — the front page went from eight governance keys to
nine at that point. It says ten now: a loop stage's `asks:` joined list B when
the hole §7.28 had merely *stated* about it was closed.

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
kind** against every non-test source file in all three languages. A field with
no reader is either a **delegation** — a host responsibility already named in
`50-NOT-COPIED.md` §4, *"Seven ways of verifying a caller … the host does the
checking"*, *"the store refuses a write from a source `never-from:` names"* —
or a **defect**, and defects go in `KNOWN_GAPS`.

**`KNOWN_GAPS` is now EMPTY · CLOSED.** The five defects this row used to
tabulate — `agent.model-for-checking`, `agent.answers-with-mode`,
`settings.tool-choice`, `settings.frequency-penalty`,
`settings.presence-penalty` — every one of them has a reader; measured by
calling that file's own `reader_exists` on each, which is the same function the
suite gates on. Three of the five were closed by A5b (the locally-served
transport implementing `apply_settings` at all) and two by A5, and the row
tabulating them was never updated, which is this document's own defect. The
sixth entry the list ever carried, `workspace.profile`, left differently and the
distinction is worth keeping: `pact check` warns `loader/profile-selects-nothing`,
so the field is read and no longer silent — but no profile *mechanism* exists,
and that gap is AC-7.2's, recorded where its new shape is described rather than
here under an old name. Worth being precise about what "read" means here: nothing
asserts that rule id, that message, or that `--deny-warnings` fails on it; what
finds it is `reader_exists` matching the string `"profile"` in the checker. A
name-presence scan is the rule this file states, and the rule is right for its
purpose — but it is not a test of the warning, which is one more reason
`docs/remediation/C8-profiles.md` deletes the field rather than defending it.

**Neither figure is written down any more.** How many fields are delegated and
how many are gaps are `len(DELEGATED)` and `len(KNOWN_GAPS)` in that file, and
nowhere else. The counts in the previous version of this row — 13 unread,
splitting 8 and 5 — were both wrong within two sessions: the delegated list has
grown from that 8 to `len(DELEGATED)`, because the same file stopped counting
its own English prose as a reader and six fields that had never been read turned
out to have been reported as read for as long as they existed. **No multiplier
is given here either**, for the reason this paragraph is about: a count in prose
beside a computed list is a second copy of the list, and so is a ratio between
two of them.

`KNOWN_GAPS` **may only shrink**: `test_known_gaps_only_shrink` fails the moment
an entry gains a reader, and its message says to remove it *"from `KNOWN_GAPS`
and from `docs/70-PRODUCTION-GAP-REGISTER.md`"* — so closing a gap forces this
register to be updated in the same change. **That did not work here**, and the
reason is worth stating: the test enforces the pair only for entries still in
the list, so removing one from the code and leaving its row in this document
passes. An empty `KNOWN_GAPS` also makes that test vacuous. What holds the
emptiness honest is the other direction — `test_every_authored_field_is_read_by_something_or_declared_delegated`
fails the moment any field loses its reader — and that is the check to trust,
not this paragraph.

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
| ~~**2.1**~~ | golden set of ≥12 agents per framework | **MET for the breadth it claims.** Every agent under every `examples/**/workspace.yaml` runs over all seven Python targets and the TypeScript port, generated from the tree rather than listed — an agent added to `examples/` joins by existing. **This row does not say how many, on purpose.** The set is `GOLDEN` in `adapters/python/tests/test_the_golden_set_runs_everywhere.py`, built by asking `pact show` what each workspace contains, and `len(GOLDEN)` is the figure; it said **28 across 9 workspaces** for two sessions after the tree had moved past both, and the same stale pair was copied into three other places in this document. Comfortably past the twelve the criterion asks for, and re-derivable by running that file. Compared on what the model was **told** and **offered**, not only on what it said back: the first draft compared traces alone, and deleting the answer shape *and* the written procedures from the second port's system text left all fifty-nine assertions green. A scripted model says the same thing whatever you tell it, so comparing what it said compares the script. **Bounded honestly:** the script answers without calling a tool, so multi-step tool sequences and parking runs are out of scope here — the second port publishes `durable_resume: unsupported`, and asserting over a documented divergence would be asserting that the ports differ. `test_portability.py` holds one agent in depth; this is breadth, and the thesis asks for both |
| **5.1** | ≥8 orchestration patterns incl. swarm, debate, blackboard, market | **PARTIAL — eight ship, three of the named ones cannot.** `examples/patterns/` holds `quorum`, `race`, `pipeline`, `swarm`, `weighted`, `escalation`, `debate`, `first-answer` — each a workspace that loads, and each **runs** to an answer or a clearable wait, which is what makes them shapes rather than documents. Held distinct on the WAITING RULE (`waits-for` / `enough-is` / `gives-up-after` / `starts` / `divides-the-budget` / `if-someone-fails`), so eight names for one behaviour fails. **`blackboard`, `market` and `auction` are absent and cannot be built on today's primitives**: `blackboard` needs a store agents read and write between turns; the other two need bidding and a settlement rule. `teamwork:` is a *waiting* vocabulary. Inventing shared mutable state between agents to satisfy a criterion would be the largest design change in the system made for the smallest reason — so this AC needs either those primitives designed on their merits, or amending |
| **5.2** | ≥6 loop patterns | **PARTIAL, and this row said MET for several sessions. The correction is `docs/remediation/F5-two-loops-named-for-what-they-are-not.md`.** **No figure is given here, and that is deliberate**: the criterion enumerates six techniques and `spec/loops/` holds six shapes, and letting either number stand for the other is exactly how this row went wrong — twice, because the first draft of the correction answered *"six of six"* with *"four of six"* by counting `standard`, which is named for no technique on the list. Six shapes ship: `standard`, `plan-then-do`, `react`, `reflexion`, `tree-of-thought`, `answer-more-than-once`. Each terminates (asserted by walking the stage graph AND by running it to `halted == final`), each tells the model something no other shape does, and the drift check between `spec/loops/*.yaml` and the two adapter copies is **derived from the directory** — it was a hand-written pair, so the four new shapes joined the library and nothing compared them. All of that is true and all of it is held. **What was never held is that a shape does what its name means.** Two of the six say in their own `description:`, in words an author reads, that they do not: `tree-of-thought`: *"The branches are written down and pruned in the transcript, not executed and compared."* Tree-of-Thought is search — branches executed, each scored, backtracking to a sibling — and what ships is one `think` stage asked for three approaches, one `check-its-work` stage asked to argue against them, and one path. `answer-more-than-once`: *"The attempts share a conversation, so they are not independent samples."* Its own file **refuses the name** `self-consistency` because *"self-consistency samples the model INDEPENDENTLY"*, and this row then counted it as the criterion's fifth pattern, which is the criterion's own word `self-consistency`. The refusal happened in the library and not in the claim, which is a T7 breach in the document that exists to catch them. **The criterion's six names, one by one:** *ReAct* ships as `react` and *Plan-and-Execute* ships as `plan-then-do` — the reason/act alternation and the plan-then-carry-it-out split are the actual mechanisms, expressed as stages. *Reflexion* ships **in part** as `reflexion`: the critique is written in its own stage and the revision is conditioned on it, which is the mechanism at one trial's depth, but the episodic buffer the technique is built on is absent — and it is absent by decision, priced in `docs/remediation/F6-reflexion-has-no-memory-across-runs.md`, which states in the same change that *"Reflexion the technique is defined by the part that is missing … one round of that with the buffer removed."* That makes it a **third approximation** on the same standard as the other two, and the least self-disclosing of the three: `tree-of-thought.yaml` and `answer-more-than-once.yaml` each say in their own text what they are not, and `spec/loops/reflexion.yaml` says nothing about the buffer either way. *Tree-of-Thought* and *self-consistency* are answered by nothing, per the two paragraphs above. *CodeAct* is refused, below. **And `standard` answers none of the six names** — `loops.py` calls it *"what an agent does when nobody says otherwise"*, and `test_loops.py` records that its opening is byte-identical to `reflexion`'s because *"`use-tools` adds nothing to the prompt, and that is exactly what makes `standard` the same as having no loop at all"*; awarding a named slot to a shape that is the same as having no loop is the same move as awarding `self-consistency` to `answer-more-than-once`. **So: two of the six names ship, one ships in part, two do not ship, one is refused.** **The test that carries this row asserts existence and termination**, `test_loops.py::test_the_specification_ships_the_six_loop_patterns_the_thesis_asks_for` plus the stage-graph walk; no test asks about fidelity and none could, because a name's meaning is not in the document. **What each of the three would need** is in F5 (and, for `reflexion`, in F6): for `tree-of-thought`, branch execution and backtracking — a stage entered again with a *different* context rather than a longer one, a per-branch score the run holds rather than the model recites, and a route back to a sibling; for `answer-more-than-once`, independent samples and a **programmatic** selector. The sampling half already exists one construct over — `examples/patterns/quorum/` runs three byte-identical readers, each with its own `history`, `Meter` and `Ledger` (`docs/95-FIX-PLAN.md` §1.18) — so what is missing is the selector, and that pattern's own `workspace.yaml` says *"you are buying tail latency, not accuracy"*. `docs/00-THESIS.md` §7.3 lists *"Ensembling / self-consistency **with a programmatic selector**"* as portability mechanism 7, and that half is expressible nowhere. **CodeAct is deliberately absent and that is unchanged**: it means the agent writes code as its action, which is `runs-as: code`, refused in `docs/50-NOT-COPIED.md` because a spec naming code to run makes `pact check` decide whether that code is safe. Building it as a loop shape would reintroduce a refusal through a side door |
| **6.3** | export to Bud `AgentRecord`, A2A card, OSSA with a loss report | **PARTIAL — two of three, and the third is refused.** `exporting.py` ships `ExportReport` and `to_bud_agent_record`, beside the A2A card `pact card` already emits. The record's shape is **read off the real interface** in `gaia-ai-runtime/goose/ui/desktop/src/acp/bud.ts`, and a test parses that file — an exporter written against an invented schema is a file that loads nowhere, dressed as an integration. `silent_losses` is **computed from the source**, like `ImportReport.silent_drops`. **Six fields are left empty on purpose** — `version`, `revision`, `status`, `registryKind`, `runtimeBackend`, `invocation.url` — because they are registry and deployment facts, and PACT owning them would be the specification deciding where it runs; inventing a version and a URL fails the suite. The loss report gives each lost field its own sentence rather than defaulting to "unsupported", because *which kind of thing it is* decides whether losing it matters: a registry losing `instructions:` is expected, one losing `policy:` means an index that cannot tell a governed agent from an ungoverned one. **OSSA is refused, not omitted:** no OASF schema exists in this repository or in `gaia-ai-runtime` — the only matches are Italian translation strings, where `ossa` means "bones" — so writing one would produce exactly the artifact this project keeps finding. Blocked on the AGNTCY schema |
| ~~**7.1**~~ | a fuzzer proving no semantic element vanishes without a report | **MET.** `test_nothing_vanishes_between_the_file_and_the_document.py`, seeded (`SEED` fixed, every case prints the mutation that produced it — a fuzzer nobody can reproduce is a flake generator). Three properties: every key an author writes **arrives** in `pact show`; an unknown key inserted anywhere is **refused by name or visible**, never silently accepted and gone; a changed **value** reaches the document. Property A has a demonstrated mutation — making `Node::to_json` skip `because:` turns it red by name. **Property B does not, and the file says so**: the shape it guards is *accepted and dropped*, and no single edit produces it because `show` runs the same validation `check` does. It earns its place as the only property that can see a key the tree does not contain. Two claims in the first draft were wrong and are corrected in place: renaming a key mostly produced *"must have a 'name'"* — a refusal for a different reason that never reached the question — and "dropped by show" was a misreading of empty stdout from a command that had exited 1 |
| **1.5** | a non-programmer authors a working agent | protocol written, **never run** |

**AC-2.1 was the one that most weakened the headline claim.** "Byte-identical
across seven targets" was proven on **one** agent — an existence proof, not a
conformance set. It is now every agent in `examples/` over eight targets — the
seven Python entries in `conformance.TARGETS` plus the TypeScript port — and the
eight orchestration patterns built for AC-5.1 supply all of them except the
`refund-desk` and `answers-from-documents` agents: the two criteria turned out to
be one body of work. **The counts that used to stand here are in `len(GOLDEN)`**,
for the reason given in the AC-2.1 row.

### Partially met

| AC | Requires | Actual |
|---|---|---|
| ~~**3.2**~~ | predicate language evaluating `MMLU > 80 && SWE-Verified > 40` | **MET, and it uncovered a crash.** The comparison vocabulary was always in the format — `needs.scores` is `type: map of threshold` and `coerce.rs` parses `>`, `>=`, `<`, `<=`, `=` and a trailing `%` — so `MMLU: "> 80"` loaded cleanly and `pact show` emitted the string. `satisfies` then did `have <= threshold` with a float on the left and `"> 80"` on the right: **a `TypeError`, so the format's own documented syntax crashed the resolver** rather than refusing or working. `_threshold` and `_HOLDS` mirror `Op::holds`, and an unreadable threshold is now a refusal naming the shape to write. **There is deliberately no `&&`:** the conjunction is the map — every line has to hold — and an expression language is a language, with precedence and parentheses, which is the one thing a non-coder must never have to learn. Two lines that both have to be true is the same predicate without the parser |
| ~~**4.1**~~ | published coverage matrix of every DeepEval metric | **MET.** `providers.coverage()` emits a `MetricCoverage` artifact: every metric DeepEval ships, the URI an author types, and for the ones not offered, why. **50 ship, 47 reachable, 3 excluded** — all three abstract base classes. **Computed from the installed DeepEval, never listed**: a hand-written matrix is a second copy of somebody else's release notes and is wrong the first time they ship a metric, which is the coupling invariant E-4 exists to remove. The row that must never appear is *"shipped by DeepEval and not reachable from config"* — `Base*` and `Ragas*` are decisions with reasons, anything else in that bucket is a **defect**, and excluding one metric in a mutation makes the suite say so in those words. DeepEval being absent is reported as an absence rather than shown as an empty matrix, which is a different fact |
| ~~**4.3**~~ | evals run against a *remote* agent over A2A/HTTP | **MET.** `A2ATransport` binds an **agent** rather than a model: something already running behind a URL that does its own thinking. Held against a stub agent on localhost — **remote means not in this process**, and D17 is untouched. **The property that matters is not that it works**: a remote agent owns its own loop, so the author's stages, interceptor rules and ceilings decide nothing, and the run SAYS so on `unenforced` — a score that did not would attribute somebody else's behaviour to a document they never read. `tool_calls: unsupported` is the surprising lattice entry and the correct one: the remote agent may well use tools and **we do not see them**; `native` would claim to have observed something nobody observed. No default URL, so it cannot reach anywhere nobody chose. **A harness bug it uncovered:** `_meter_usage` unpacked `usage()` unconditionally, so a transport that HAS the method and could not measure a call took the run down with a `TypeError` — while the docstring one line above already said what cannot be measured is reported rather than guessed. That was true of a transport with no `usage()` and not of one whose `usage()` returned nothing |
| ~~**4.4**~~ | promote a failing production trace to an eval case in one command | **MET.** `--from-trace FILE --called NAME` writes the case into the agent's own `cases/` folder. **The security half shipped broken first and is worth recording:** `as_record` took `asked: str` from the caller, and the obvious thing to pass is the question as typed — so promoting a run on the worked example, whose author wrote `redact-card-numbers`, put `4111 1111 1111 1111` into a YAML file destined for version control. Measured, not reasoned about. `RunResult.asked` is now set by the harness from the message **after** the chain ran and `as_record()` takes no argument, so there is no parameter left to get wrong. `expect:` arrives empty on purpose — the answer that run gave is the wrong one, and writing it in would make the bug the specification — and **`evals/case-asserts-nothing`** is the new loader rule that makes that mean something: `expect:` is `type: anything`, so `expect: {}` loaded cleanly and a suite carrying a promoted case reported one more case than it could grade. `must-also:` counts as an assertion |
| ~~**5.5**~~ | a rejected learning candidate influences the next cycle | **MET.** `Learner.rejected` was a list nothing read, and its own comment beside the append stated the purpose it did not serve — *"a rejected candidate that is simply forgotten will be proposed again next cycle"*. Forgetting happened **twice over**: nothing consulted the list, and a `Learner` is built fresh per cycle so it did not outlive the process. `Refusals` keeps them in `.pact/learning/refused.jsonl` beside the spend ledger, and `cycle` recognises a repeat **before the evals run** — the expensive part of learning that an edit does not help is finding out, and finding out twice is paying twice for one answer. The first refusal's reason is handed back, so a reviewer sees why. **Two refusals are deliberately NOT remembered:** `enabled: off` and a spent ceiling are about the workspace, and drift is about how far the agent has moved since the baseline — remembering either would make an edit permanently unaskable because of where the agent happened to be when it was first proposed. Eleven refusal paths each built their own `Outcome`; they agreed only because nobody had added a twelfth, so they now go through one `_refuse` |
| **6.1/6.2** | `gaia-ai-runtime` discovers and binds | **NOT MET, and "unproven here" was the wrong word.** *Unproven* says the integration exists and nobody measured it. It was measured: a **case-sensitive** word-boundary grep of `/home/bud/ditto/gaia-ai-runtime` for `PACT`, `agent-inter-op`, `pact-cli`, `pact_adapters` and `pact.dev/v1` returns **zero** hits across the whole checkout — `bud-agentic-runtime/`, `crates/`, `goose/` and the three vendored trees `research/`, `_runtime_refs/` and `_sdk_refs/`. The substring matches are `impact` and `compaction`. **Say the case-sensitivity, because the next reader will drop it:** the same grep with `-i` returns exactly two lines, both English prose in a vendored third-party corpus — `_runtime_refs/agno/cookbook/91_tools/imdb.csv` lines 935 and 937, film synopses about a man who "enters into a pact". Nothing outside that corpus, in either case. An unqualified *zero* that a reader can falsify in one command is the failure mode this register exists to name, even when the conclusion it supports is right. **The integration exists in neither direction.** PACT's half ships and is held — `pact discover` walks a tree, publishes the version, and `crates/pact-cli/tests/the_workspace_a_check_finds_is_the_workspace_a_runtime_finds.rs` pins that the workspace a check finds is the one a runtime finds — but nothing on the other side calls it, and no PACT code binds a skill, tool or model the runtime owns. The only coupling in the tree runs the other way and belongs to a different criterion: `exporting.py` reads `gaia-ai-runtime/goose/ui/desktop/src/acp/bud.ts` to shape the `AgentRecord` (AC-6.3). That is PACT reading somebody's source file, not a runtime discovering a workspace. **It is BLOCKED, not merely undone,** and `docs/25-ARCHITECTURE-DECISIONS.md` AD-92 says on what: closing it needs **two changes to `gaia-ai-runtime` itself, another team's codebase** — a planner path that accepts a tree with no registry entry and no artifact precondition, and removal of the subagent → package → recipe round-trip inside `create_agent`, because run planning hard-fails unless the compiled Goose recipe physically exists and `create_agent` reads it back off disk whenever `spec.runtime.subagents` is non-empty. Two gates, not one. Nothing in this repository can close either |

### Met — held by a named test that asserts the thing

`2.6`, `4.2`, `4.5`, `5.3`, `1.3` (first half), and — since Phase 3 — `1.4`.

Six. **The previous version of this section listed fifteen, and was wrong
about at least three of them.** An independent pass checked each against the
tree:

| Was listed Met | Actually |
|---|---|
| **1.2′** | **MET, with one residual that is itself a finding.** `exploding.explode` writes a document back out as a tree, and **all eight pattern workspaces round-trip** through the real Rust loader — `load` is the CLI, because an `explode` checked against a Python re-implementation would prove the two agreed with each other. The alphabet is checked over the WHOLE document **before a byte is written**, which is the criterion's `MUST NOT emit a tree`: half a tree on disk is worse than none, because the half that wrote looks like it worked. A document carrying **payloads** gets its own refusal — a payload is bytes the loader carried verbatim and what reaches a document is a *reference*, so `refund-desk` genuinely cannot be exploded, and saying "unportable key" would send somebody renaming `$payload`, which is not theirs to rename. **The residual, and it is about an earlier fix of mine:** the round trip is exact *up to trailing whitespace on prose*, because the three spellings do not agree — `instructions: Be kind.` gives `"Be kind."`, `instructions.md` gives `"Be kind."` (trimmed by `pact_doc::prose`, the Phase 3 fix), and `instructions: \|` gives `"Be kind.\n"`. Phase 3 made two of the three agree and building the inverse is what showed the third still does not. **SETTLED — the block scalar is trimmed, and all three spellings now give one digest.** The argument that decides it is not about which newline is nicer: a plain scalar CANNOT express a trailing newline, and a real file ALWAYS has one, because every editor writes it and POSIX defines a line as ending in `\n`. So if the trailing newline is content, the inline form and the file form can never be equivalent and the Expansion Rule is false for prose **permanently**. The only reading under which all three agree is that trailing whitespace on a block is not part of what was written. `resolve_scalar` trims `Literal` and `Folded` styles. **What it costs, said plainly:** `\|` and `\|-` now mean the same thing and `\|+` no longer keeps what it asked to keep — `yaml_rust2` reports one style for all three, so telling them apart is not on offer, and the no-code ceiling says the distinction should not survive anyway. An author who has to know that a pipe keeps a newline and a pipe-minus strips it is being asked to learn YAML chomping indicators to write down what their agent should do. A quoted `"Be kind.\n"` still keeps its newline, because an explicit escape is a deliberate act and not a spelling anybody reaches by accident. **Nothing in the repository broke**, which is itself worth recording: no digest is pinned as a literal anywhere — every digest test computes both sides — so the change was invisible to the suite until `test_the_three_ways_of_writing_prose_are_one_document` pinned the equivalence, which is the property that matters rather than the value |
| **1.4** | **was** *"both tests normalise before comparing"* — `lib.rs:757` trimmed `instructions` on both sides and `example_refund_desk.rs:205` rewrote the node, while the two forms really did produce different digests. **Now MET:** Phase 3 bug 11 fixed it at load (`pact_doc::prose`), both normalisations are deleted, and reverting the trim turns the equivalence test red |
| **7.2** | **PARTIAL — the audit half is met, the profile half is not.** *"A core audit finds no capability-affecting literal"* is held **over the Python adapter package, and nowhere else**: every numeric module-level default in `adapters/python/src/pact_adapters` is filed as author-settable (naming the field), not-about-capability, or deliberate-and-closed (saying what an author overriding it could weaken). **The scope is narrower than the criterion and is stated here rather than left to be found** — this repository's word for "the core" is the Rust crates (`docs/20-ARCHITECTURE-DRAFT.md:1766`, *"the audit forbids capability-affecting literals in the core"*), the walk is one line (`SRC = REPO / "adapters/python/src/pact_adapters"`), and no Rust-side audit exists at all. `crates/pact-doc/src/yaml.rs:52` `MAX_TEXT = 4 MB` refuses a 5 MB knowledge file on a literal nobody filed, and `crates/pact-schema/src/coerce.rs:76 SCORE_TOLERANCE` is the unaudited twin of a constant the decision document quotes as evidence. That is **D-4** in that document's §7, and until it lands, "the audit half is met" carries the package name. One in none of the three fails, and the message asks the question rather than saying to add a name to a list. **This row no longer says how many, on purpose.** The set is whatever `_capability_literals()` returns in `adapters/python/tests/test_no_default_decides_a_capability_in_secret.py`, and `test_every_default_says_which_kind_of_default_it_is` plus `test_nothing_is_accounted_for_that_is_not_a_default` make the three registers account for it exactly, in both directions — so anybody can re-derive the figure by running that file, and nobody has to maintain it here. It said **21** for one session and was wrong by five by the end of the next, because closing a defect anywhere in the package adds or removes a constant and no rule made the two move together. A count in prose beside a computed set is a second copy of the set, which is the failure this whole register is about. **The first version audited every upper-case global** — most of them vocabulary tables naming the format's own words. Those decide what something is CALLED; a number decides *how much*, and how much is a capability. An audit of a hundred-odd rows is a bookkeeping exercise nobody reads. **The profile half is now a DECISION rather than a gap — `docs/remediation/C8-profiles.md`, which says do not build it.** `workspace.profile` is `tier: core` and selected nothing, silently; `pact check` now warns `loader/profile-selects-nothing`, so an author writing `profile: production` is told it changes nothing — which took the field out of `KNOWN_GAPS` (a warning IS a reader, by that check's rule, and the rule is right). What that document then found is that the two halves of AC-7.2 **contradict each other**: every default the audit filed `DELIBERATE_AND_CLOSED` carries a written reason an author must not override it, and *"all defaults resolve from profiles"* is a request for the mechanism that overrides exactly those. **That tension is stated at the strength the evidence supports and no higher** — the architecture draft's own answer, *"a builtin profile shipped as data satisfies F-1/AC-7.2"* (`:1761-1764`), is quoted and answered in the document's §2 rather than stepped around: it rescues the criterion only under per-field closure, a rule nobody has designed, since RES-2 is **later-wins** and a later layer can therefore overwrite a filed-closed default. An earlier draft of this row also said a profile is precedence which **FR-1.1.4** forbids; that claim is **withdrawn**, because FR-1.1.4 is a duplicate-definition rule in the FRD's tree-loading block and PACT ships two layering mechanisms already (`based-on:`, `feel:`). What survives is narrower and is the argument that works: both shipped layers write the layer's name next to the value it changes, and `profile:` at the top of `workspace.yaml` cannot. **FR-8.1.6** (`☐`, never started) — the provenance reporting RES-2 itself asks for — is unmet for the layering that already ships. Its decision: **delete `workspace.profile`, amend AC-7.2 to the half that is held, and amend F-1's enforcement column and FR-8.1.3 to match.** The prices are stated there and **five** of them are work — chiefly that `based-on:`, the shipped mechanism the decision points authors at, drops a restated block's other keys in silence (a spend cap disappearing under `loaded cleanly`, measured), ships with **no** user in `examples/` or `tests/trees/`, and is tested only from hand-built maps; and that **`pact discover` and `pact card` do not run derivation at all** (E25 row 0.10, `docs/91-REVIEW-CRITIQUE.md:166`), so a `based-on:` agent the checker called clean is published to a runtime's index with `model: null` and `limits: null` — measured, no spend cap whatsoever. Pointing authors at `based-on:` while that holds is the same overclaim the document's own §6 was written to avoid, so it is named there as **D-5** and as a prerequisite. **Nothing in that document is implemented.** Until parts 1–7 of its §5 are made, this row stays PARTIAL — but the remaining work is an amendment and five named defects, not a profile resolver. **Update 2026-08-13 — three of the five defects landed, and the sentence before this one is stale for them.** D-1 is closed — `crates/pact-cli/tests/a_restated_block_says_what_it_dropped.rs`: the silent spend-cap drop now warns `loader/restating-a-block-drops-the-rest` naming the dropped keys, and `--deny-warnings` fails on it. D-5 is closed — `crates/pact-cli/tests/an_inherited_ceiling_reaches_discovery_and_the_card.rs`: `discover` and `card` run derivation, so the agent that was published with `model: null` and `limits: null` now carries its inherited ceilings, and the base it derives from has no discovery row. D-3 is closed in its on-disk half — `crates/pact-loader/tests/an_agent_that_inherits_its_limits_is_held_to_them.rs` reads `tests/trees/an-agent-built-on-another/` through the real loader and the real `derive::resolve`; what no test yet shows is the inherited cap **biting in a live run**, and that half is named open rather than claimed. `base: yes` also landed, against C8 §6.6's own stated terms — one field, on the one kind that can act, exemption keyed off the group declaring it — not the thirteen-kind field the deferral refused. D-2 and D-4 remain open and §5 parts 1–7 remain unmade, so the row stays PARTIAL |
| **3.1, 3.4, 5.4, 3.3, 3.1b, 2.3, 1.1** | downgraded to PARTIAL — each has a real half and a missing half, detailed in the plan |

### Omitted entirely — seven criteria appeared in no table

`2.2`, `2.4`, `2.5`, `3.5`, `3.6`, `6.4`, `7.3`. The register covered 28 of 35
and did not say so, which reads as coverage.

- **2.2** — **MET.** `pact_adapters.conformance` emits a `ConformanceReport` over
  every (golden agent × non-reference target) pair — `len(GOLDEN) ×
  (len(TARGETS) - 1)`, which `test_the_conformance_report_is_honest.py` asserts
  **as that arithmetic and not as a literal**, so adding an agent or a target
  cannot leave the report claiming a coverage it no longer has (this document
  carried the product as a literal, `28 × 6 = 168`; the six was right and the
  28 had gone stale, so the product understated what the suite actually runs)
  — against the framework-free control. **ε is declared and is zero**, with the
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
  specification.
  **AC-6.4 asks for three importers this row never named, and none of them
  exists.** Its text is *"a Bud/Goose **recipe**, **custom agent**, and
  **skill** each import into PACT and re-export without behavioural change on
  the CTS"* — three named artifacts and a round trip. `importing.py` defines
  `from_a2a_card` and `from_anthropic_request` and nothing else; `grep -rn
  "recipe" adapters/python/src` finds two English sentences about loop shapes
  and no importer. So AC-6.4 is unmet on **both** halves and for a reason of its
  own, separate from AC-2.4's: the two importers that ship are not the three it
  asks for, and there is no re-export-and-compare path for any of them, so even
  a recipe importer landing tomorrow would leave the *"without behavioural
  change on the CTS"* clause unheld. Carrying 2.4 and 6.4 in one row is what let
  6.4's own words go unread — they are different criteria and the parts of them
  that are missing are different parts
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
| 10 | **The conformance payload is hand-written** — so a field absent from it is outside the comparison **by construction**. This is why 3, 5, 6 and 9 survived, and why `answers-with:` stayed unported for a session while `tier: core` and in the worked example | **fixed at KEY granularity, and that is not the same as fixed.** One `_payload_for` instead of two inline copies, and `test_every_key_the_loader_emits_is_sent_to_the_second_port_or_accounted_for` compares it against `pact show`, so no authored key is silently absent from the accounting. **The guard is on the key and the defect was on the value.** Measured: `_payload_for` (test_portability.py:93-119) emits no `limits` key at all, and the row `"limits": ("maxSteps",)` (:518) passed because the predicate asked `any(k in payload for k in keys)` and `maxSteps` is there — so `cost-per-request-under`, amount AND currency, never crossed this seam, and B5's four divergent money spellings stayed green through every run of it. The predicate is now `all(...)` rather than `any(...)`, at :548. **Measured, that closes nothing today** — deleting the whole `skills` block from `_payload_for` leaves the test green under both, because `uses` and `loop`, the only two multi-key rows, are ALSO exempted by name in `NOT_SENT_TO_THE_SECOND_PORT`; the weakness there is the exemption, not the quantifier, and `all` is the guard for the next multi-key row that is not exempted. What is still open is one level down again: a key that is SENT but sent in one spelling out of six is inside the payload and outside the comparison, which is what `test_both_ports_read_every_way_a_spend_cap_is_written.py` exists for and what no structural check yet reaches |
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
| **C2** | **`bundle.from:` resolves nothing — decided, and half closed.** `from:` is `required: yes` and no pass in this loader resolves it, so a workspace could declare three bundles, load cleanly, and contain **not one definition from any of them**. `loader/bundle-not-mounted` says so — a **warning, not an error**, because the field's own help says `from:` may be *"a path inside this workspace, or a name your platform team publishes"*, and refusing outright would break the case the field was written for while silence misleads the case it was not. **Mounting itself remains unbuilt**, and the four decisions that blocked it — path resolution and containment, merge semantics, collision rules, digest impact — are now **taken, with their price stated, in `docs/remediation/C7-bundle-mounting.md`**: `from:` is never resolved and contributed content arrives only as `bundles/<name>/contributes/` under the root, so the loader's existing containment (`follow_symlinks: false`, `MAX_DIR_DEPTH`, `loader/cycle`) is the whole rule and no second path resolver is written; projection is a document rewrite beside `derive::resolve` in `crates/pact-cli/src/main.rs`, consuming its source the way `based-on:` is consumed, so one document reaches every whole-tree pass rather than each pass remembering bundles exist (about 25 today; the document gives the command and says plainly that the figure is a reading no test pins); a collision refuses on both spans like `loader/ambiguous-field` rather than picking a winner in either direction; and mounted content is **in** the digest, which is not a new decision because the folder form already hashes it — measured, `cargo run -p pact-cli -- discover` on a copy of the shipped tree moves the digest from `sha256:5a926713…` to `sha256:65a8d5af…` when one word changes inside `bundles/customer-lookup/contributes/tools/find-customer.yaml`. The recommendation is **build the folder form, never build fetching**, and the seven acceptance tests that would close this row are written out there. **The half that is now closed: a shipped tree declares bundles.** `tests/trees/what-a-bundle-brings/` holds two — `customer-lookup`, whose `contributes/` folder is present, and `refund-toolkit`, whose `from: acme/refund-toolkit` nothing resolves — so `a_bundle_brings_only_what_it_said` is exercised from a real folder of files instead of only from the hand-built `Node` trees in `bundles.rs`'s own `mod tests`, which was this register's Class A signature defect sitting inside the file written to catch it. `crates/pact-loader/tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs` reads it through the real `Loader` against the shipped `spec/schema.yaml`: eight tests, and the one only a real tree can make is that **the folder form is what builds `contributes:` at all** — its own help says *"You do not type this — it is what is in the bundle's own folder"*, so either the loader produces that shape or nothing does, and a document a test assembles cannot tell you which. **All three rules the pass emits are folder-witnessed, the two errors included**: the warning `loader/bundle-not-mounted` by the shipped tree's two bundles differing in one folder; the error `loader/bundle-brings-more-than-it-said` by a copy of the tree gaining `bundles/customer-lookup/contributes/policies/strict.yaml`, which is exactly how the supply-chain case happens — somebody else's version 2.1 ships a directory; and the error `loader/bundle-brings-an-unknown-kind` by the same copy gaining `contributes/gizmos/`. That the two refusals come from folders is the point: a hand-built map holds the key `policies` because a test typed it, whereas on disk that key exists only because the loader turned a **directory name** into one, so if the loader ever began filtering directory names on the way in, every hand-built test would keep passing over a branch nothing could reach. Five hand-built tests in `bundles.rs` now carry a comment naming which file-based test supersedes each as the sole witness, or saying why it stays the sole witness of something narrower — the `agents` kind specifically, and the *absence* of the governance sentence for an ordinary kind, which needs a second bundle one tree does not have. None was deleted or weakened. The tree lives in `tests/trees/` and not `examples/` because it **must warn** and `scripts/test-all.sh` runs `--deny-warnings` over everything in `examples/` — measured, `cargo run -p pact-cli -- check tests/trees/what-a-bundle-brings` exits 0 with one warning and exits 1 with `--deny-warnings`; `tests/trees/one-line-gate/` is the precedent. **And this row measured its own gap with a command that could not have detected its own fix**: it said `grep -rn "bundles:" examples/ tests/` returns nothing, which it did — and it would have gone on returning nothing after a dozen trees declared bundles, because a workspace collection is normally a **folder** and not a line and no author types `bundles:` anywhere. The question it meant to ask is `find examples tests -type d -name bundles`, which returned nothing before this work and returns `tests/trees/what-a-bundle-brings/bundles` after it. What the old command returns *today* is the sharper illustration: two hits, both **prose in the new tree's README**, the one place in the tree where a human types the string and the one place it means nothing to the loader — a false negative that became a false positive without ever answering the question. **Two things the tree pins that were not written down anywhere.** A contributed document is **not re-validated**: three lines that under `tools/` give three errors — `schema/unknown-field` twice, `schema/no-such-name` once, plus a `loader/nothing-points-at-it` warning, so `3 problem(s) and 2 warning(s)` and exit 1 — give **no diagnostic at all** under `contributes/tools/`. And `a_bundle_brings_only_what_it_said` reads `top.get("bundles")` and stops, so a bundle nested inside another bundle's `contributes/` is scope-checked by nothing — harmless while nothing mounts, and the first thing to break when something does. Both are acceptance tests 2 and 4 in the design document | all three rules of the check are exercised from a real tree and the four decisions are taken; **still unbuilt**: projecting a bundle's contributions into the collections an agent can name, the recursive scope check (`top.get("bundles")` and stop), and the re-validation of contributed documents |
| **C3** | **TypeScript port is behaviour-only** — still true of the four governance mechanisms, and now *narrower*: it honours `answers-with:`, reports keys **inside** `limits:` that it does not read, and **refuses** a field it does not know from the library rather than only from the test driver | interceptors, context-policy, policy, teamwork all `unenforced` there |
| **C4** | **G9 is Python-only even once wired** | see A1. `remembers:` is never put on the wire to the second port, so it is a §7.28 *"never arrives"* key rather than one reported on `unenforced` — and if it did arrive the port now refuses and names it, which is the right answer for a line that changes what a run may forget |
| **C5** | **NARROWED, and re-measured key by key.** This row used to read *"no transport reports usage on most targets"*, which was false, and its replacement gave coverage figures for five of the nine transports and none for the other four. Both halves are now measured from the source rather than described. `adapters/python/src/pact_adapters/transports/` holds twelve `.py` files and three of them — `_metering.py`, `_summarise.py`, `_tool_choice.py` — are shared code every transport imports rather than transports, which is what the `_` prefix says; so the denominator is **nine**. **The metering seams:** `usage()` **8 of 9**, `prices_money` **8 of 9**, `context_window()` **7 of 9**, `write_summary()` **7 of 9**, `summary_usage()` **7 of 9**, `lattice()` **9 of 9**. The seven model-bound transports carry the full metering set, `a2a_transport.py` carries the two a remote agent can answer, and `mock.py` carries none of it on purpose as the honest-and-inert control arm that keeps the `unmetered` route exercised. **The `settings:` seam:** `apply_settings` **7 of 9**, and the measured left-over set of each — obtained by calling the method with all twelve keys, not by reading the mapping table beside it. **`pydantic_ai_transport.py` 12 of 12** (`pydantic_ai.settings.ModelSettings` 2.21.0 is itself a cross-provider vocabulary naming an analogue for every key), of which ten are unconditional and two are answered per run: `thinking` only when the bound model's PROFILE thinks, so against a stand-in model that does not the measured figure is 11 of 12, and `service-tier` only when the authored word is inside `Literal['auto','default','flex','priority']`, the schema having typed that field as free text. **`ollama_transport.py` 9 of 12**, leaving `thinking`, `parallel-tool-calls`, `service-tier` — the OpenAI-compatible `/v1/chat/completions` surface an air-gapped install actually answers on takes none of the three. **`autogen_transport.py` 8 of 12**, leaving `thinking`, `top-k`, `parallel-tool-calls`, `service-tier`. **`anthropic_transport.py` 7 of 12**, leaving `thinking`, `seed`, `presence-penalty`, `frequency-penalty`, `parallel-tool-calls` — that provider has no penalties at all, which is why this transport being the only one with an `apply_settings` was the reason the three penalties-and-choice keys were once recorded as reaching nothing. **`openai_agents_transport.py` sets 8 and promises 6**, leaving `top-k`, `stop-sequences`, `seed`, `presence-penalty`, `frequency-penalty`, `service-tier`. **`langchain_transport.py` and `langgraph_transport.py` 4 of 12** each — `max-tokens`, `temperature`, `stop-sequences`, `tool-choice` — leaving the same eight. **`a2a_transport.py` and `mock.py` 0 of 12**, with no `apply_settings` at all, so every key of the author's block comes back as `settings.<key>` on `RunResult.unmetered`; that is the correct report rather than a gap, because on the first the remote agent owns the loop and no generation parameter of PACT's crosses the boundary, and the second is bound to no model. **Read the other way, per key, how many of the nine honour it:** `max-tokens` 7, `temperature` 7, `tool-choice` 7, `stop-sequences` 6, `top-p` 5, `top-k` 3, `seed` 3, `presence-penalty` 3, `frequency-penalty` 3, `parallel-tool-calls` 2, `service-tier` 2, **`thinking` 1**. That last figure is the one to act on: `thinking` and `max-tokens` are the two `tier: core` keys — the ones a non-technical author writes — and `thinking` is honoured on exactly one transport of the nine (`openai_agents_transport.py`, via `openai.types.shared.Reasoning`) plus conditionally on `pydantic_ai_transport.py`. It is reported on `RunResult.unmetered` everywhere else rather than dropped, so nobody is lied to, but a core key that reaches one target is a coverage hole and not a rounding error. **A defect of exactly this row's own class, found by re-measuring and now fixed.** Five of the seven transports that map `tool-choice` decided per call whether the call could carry it, through `transports/_tool_choice.can_choose`; the two bound to a PROVIDER rather than a framework — `anthropic_transport.py` and `ollama_transport.py` — spread their `_WIRE` table into the request unconditionally and did not. `settings.tool-choice`'s help is *"auto, required, none, or one tool name"* and three of those four are answers about the tools THIS call offers, while `harness.run` closes every ceiling-terminated run with `model_call(spec.instructions, history, [])` and a stage narrows the set besides. Neither surface ignores the key in that state: Anthropic documents `tool_choice` as valid only while providing tools, and `/v1/chat/completions` refuses one sent without `tools`. So both transports built a request the provider declines, on precisely the calls a run makes once it has decided to stop. **Why it survived a round:** the Anthropic request was a LOCAL named `_request`, assembled "so the mapping is exercised" and then never read by anything — no caller, no test, no wire — so that transport's claim to honour seven of the twelve keys rested on a table and a dict discarded on the next line, which is a seam asserted instead of an effect. It is now `request_for()`, the method `model_call` itself uses, matching `ollama_transport.payload_for()`; both transports guard the key with `can_choose`; and `test_the_two_provider_transports_send_a_choice_a_call_can_carry.py` holds the effect on both, keeps `tool-choice: auto|none` sent on a tool-less call (those two ARE satisfiable with nothing to pick from, and a blanket drop would silently discard the `none` an author writes to stop a model reaching for a tool), and asserts the CLASS — any transport file that maps `tool-choice` must reference `can_choose`. An existing test had been pinning the ollama defect as intended behaviour, asserting `tool_choice: required` on a payload built with no tools; it now offers the tool. **What the framework adapters refuse to map, and why refusing is the answer.** `autogen_transport.py`: `ChatCompletionClient.create` (autogen-core 0.7.5) has exactly two doors for a generation parameter — its own `tool_choice` keyword and `extra_create_args`, *"Extra arguments to pass to the underlying client"* — and the second door's vocabulary is that CLIENT's, which this transport does not choose (`runtime = ""`). So the question a row must answer is not *"is this an OpenAI chat-completions parameter"* — being one only gets it past the client's own validator — but *"will the endpoint behind an unknown client DO something with it"*. Every name was checked against `openai.types.chat.completion_create_params.CompletionCreateParamsBase` (openai 2.50.0), and that check is necessary and NOT sufficient, which is why four are refused: `top-k` has no spelling in that set at all (AutoGen's Ollama client nests it in an `options` object, its Anthropic client takes it top-level, so one spelling would be right on one client and silently nothing on another); `service-tier` is an OpenAI-cloud routing word nothing serving weights locally routes on; and `thinking` and `parallel-tool-calls` DO have valid names there — `reasoning_effort`, `parallel_tool_calls` — and are refused anyway, because `ollama_transport._WIRE`, the one table here written against a NAMED endpoint, records that the surface the distribution's default locally-served model answers on takes neither. A transport that does not know which client it has cannot claim more than the one that does. The two tables therefore differ in BOTH directions on purpose — `_WIRE` maps `top-k` because it speaks to a measured endpoint; `_CREATE_ARGS` is the intersection over the clients a host might bind — each file names the other in prose, and `test_the_two_tables_disagree_only_where_one_of_them_knows_more` pins the disagreement so revising one against a real server without the other fails a test instead of publishing two coverage figures that cannot both be right. AutoGen's `tool_choice` is typed `Tool | Literal["auto","required","none"]`, so a NAMED tool is an OBJECT where LangChain and the Agents SDK take a bare string, and the transport builds one (`_NamedTool`) rather than sending a string the type does not admit. `openai_agents_transport.py` **sets eight on the object and promises six**, and that gap is deliberate. Four are refused outright because `agents.model_settings.ModelSettings` (openai-agents 0.19.1) — the whole vocabulary a `Model` implementation is guaranteed to understand — has no field for `top-k`, `stop-sequences`, `seed` or `service-tier`, and neither `models/openai_responses.py` nor `models/openai_chatcompletions.py` puts any of the four into the request it builds; the only door left is the untyped `extra_args` dict, spread straight into whichever provider call the host's `ModelProvider` chose — right on OpenAI's own client, ignored or a `TypeError` on anything else. **Two more have a real field, are set on it, and are reported unhonoured anyway:** `presence_penalty` and `frequency_penalty` are typed fields, so what goes on them is the SDK's own shape and not an approximation — but `models/_openai_shared.py` declares `_use_responses_by_default = True` and `OpenAIProvider` picks `OpenAIResponsesModel` off it, whose create kwargs (temperature, top_p, truncation, max_output_tokens, tool_choice, parallel_tool_calls, reasoning, store, metadata, context_management) contain neither. Only the non-default Chat Completions surface forwards them, and which surface a run gets is the HOST's choice. So `unmetered` here states what the transport can PROMISE was honoured rather than what it sent, and where they differ the promise is the weaker one: an author on the Chat Completions path is told two settings may not have landed when they did. The opposite error — a key reported honoured that the default surface silently drops — is the one this whole round exists to close. Its `tool_choice` is the mirror image of the ollama case: the field is typed `Literal["auto","required","none"] | str | MCPToolChoice` and `Converter.convert_tool_choice` is the SDK's OWN code for turning a bare name into `{"type":"function","name":…}`, so here anticipating the translation would be the error. One more repair on that seam, worth naming because it is what a seam test is FOR: `model_call` passed `tracing=None` where `Model.get_response` types the `ModelTracing` enum, and omitted its three keyword-only parameters entirely, so the call PACT made was one only its own permissive stand-in could have taken — `openai_responses.py` calls `tracing.is_disabled()` and would have raised. It now passes `ModelTracing.DISABLED` and all three, checked against `inspect.signature(Model.get_response)` rather than against the stand-in's tolerance. `langchain_transport.py` and `langgraph_transport.py` map four, and the claims are not equally strong. `stop` is a parameter of `_generate` and `tool_choice` a keyword-only parameter of `bind_tools` — both in a signature. `temperature`/`max_tokens` are only the SPELLING `langchain_core` 1.5.3 uses (`ModelProfile.temperature`; `BaseChatModel._get_ls_params`, which reads both names off the kwargs); neither is a parameter of `BaseChatModel`, what delivers them is an integration's `_generate(**kwargs)` putting them in the request it builds, and `_get_ls_params` itself builds LangSmith TRACING metadata and sends nothing to any provider. No integration package is installed in this tree to check that last hop, so it is recorded as the weaker claim it is. The other eight exist only as kwargs of a concrete integration, spelled differently in each (`top_k` is on `ChatAnthropic` and absent from `ChatOpenAI`, `seed` the other way round); `bind()` forwards an unknown kwarg without complaint, so guessing one would be a setting in a shape the provider ignores with nothing saying it did not happen. They are reported instead — honesty beating coverage, and a floor that rises the day an integration package is a dependency. LangGraph has no generation parameters of its own at all; its model layer IS `langchain_core`. What is its own is that the settings ride in the `@entrypoint` payload and are therefore CHECKPOINTED, so the one transport whose lattice claims `durable_resume: native` resumes with the run's own settings rather than a host's defaults. **That claim was false when this row first made it, in the exact shape of the defect the row is about:** the payload carried the four keys and nothing read them — `langgraph_transport.py` called `Script.next_turn` directly and constructed no `BaseChatModel` at all, so `payload["settings"]` had no reader anywhere in `src/` and four keys came off `RunResult.unmetered`, the author told they were honoured, on runs that dropped all four. Being checkpointed is not being honoured. The `@task` now calls a `BaseChatModel`, the settings are attached with `bind`/`bind_tools`, and the test asserts them where `_generate` receives them rather than where PACT wrote them. On Pydantic AI the same per-call `tool-choice` question does not merely degrade but RAISES: `resolve_tool_choice` is called by all nine provider models and gives `UserError` on `required` with no function tools and on a name it cannot find. **A defect this row hid, now fixed:** `a2a_transport.py` had `usage()` and no `prices_money`, and `harness.run`'s default was `getattr(transport, "prices_money", reports_usage)` — the money answer taken from the token answer. It is bound to an *agent*, so no catalogue row can ever price it and its own `usage()` is *"almost always `None`"*; a spend cap over a remote agent was therefore reported as **enforced** and metered 0.00 for the life of the workspace, the exact outcome `transports/_metering.py` opens by forbidding. `prices_money = False` is declared there now, and one consequence is stated rather than left to be discovered: it is the only transport where `cost-per-request-under` can be on `RunResult.unmetered` **and** be the thing that stopped the run, because an agent that volunteers a cost is still metered and can still trip `Limits.reached`. That is why that field's docstring says *"cannot promise to measure"* and not *"did not enforce"*, and a test over a stub agent billing above the cap pins the pair as the intended report. A test also asserts the CLASS rather than the instance: every transport file with a `usage()` must declare `prices_money`, and the population it walks is the in-tree nine **plus** `adapters/out-of-tree/*/transport.py` plus the second port's `adapters/typescript/src/*-transport.ts`, because the exemplar and the host's own file are the only places this defect can still be written. **A second, independent defect found while measuring it, and fixed at the seam rather than at the caller:** `harness._never_reached` built `models = [transport.model or spec.model]` and, when both are empty, `continue`d past every catalogue lookup, left `total` at its initial `0.0`, and had `Limits.priced_at_nothing(0.0)` report every money ceiling as priced at nothing — emitting *"the model catalogue publishes that row at `` at 0 USD in and 0 USD out"* about an empty model name, and hanging a D11 `tokens-at-most:` recommendation off the fabricated price. The `None` guard written for exactly that case was inside the loop and never ran. Lookups are now counted, and a models list that resolves to nothing returns `()` — nothing was asked, so nothing is claimed. **Still open, and measured rather than assumed.** (i) `thinking` at 1 of 9, above — the largest remaining hole, and a `tier: core` key. (ii) **CLOSED — the `prices_money` default is now `False`, and the class fix came with it.** Declaring it on `a2a_transport.py` fixed the INSTANCE and left the CLASS open, and the class is where the whole reachable surface is: nothing in `src/` constructs a transport, so every transport that ever runs is host-written or copied from `adapters/out-of-tree/echo_adapter/` — and that exemplar shipped the identical defect, live and measured, for a round after the instance fix (`usage()` returning `(tokens, 0.0)`, no declaration, a real run reporting `cost-per-request-under: 0.05 USD` as enforced against a meter reading 0.00). `harness.run` and `learning.Learner` now read `getattr(transport, "prices_money", False)`; the exemplar declares `prices_money = False` and returns `(tokens, None)` per `_metering.py`'s *"an unpriced row yields `None`, never zero"*; the class guard's population was widened from `src/pact_adapters/transports/*.py` to include `adapters/out-of-tree/*/transport.py`. The objection recorded against `False` — four suite stand-ins bill a real figure and declared nothing, so they would report a cap as unmeasurable while the meter ticked — held against `RunResult.unmetered`'s OLD wording, *"did not enforce"*; the field now says *"could not promise to measure"*, which is exactly what is true of a transport that never said it could price. Measured cost of the flip with nothing else changed: 4 failures out of 1930, all four those stand-ins, which now declare `prices_money = True`. The seam is filed in `tests/test_no_default_decides_a_capability_in_secret.py` under `OPTIONAL_ON_THE_TRANSPORT`, a fourth ledger added because that audit walks module-level upper-case NUMBERS and structurally could not see an inline boolean fallback on a `getattr`. The second port had the same hole twice over — `VercelAITransport` declared no `pricesMoney` so the mechanism's false branch was unreachable, and `run-trace.ts`'s `Watching` wrapper dropped the field, which is the only door the Python cross-port suite has to that port; both are fixed and `harness.ts` defaults to `false` to match. `mock.py` is unaffected throughout, having no `usage()` at all. (iii) An author who writes `tool-choice:` naming a tool no stage offers is still told the key was honoured. `apply_settings` is asked once, before the loop, and knows nothing about the tools any call will offer, so the only per-run answer it could give would be wrong in the other direction; the run is now correct on all seven transports and the REPORT is coarse. Closing it means giving `apply_settings` the spec's tools | a ceiling nobody meters is a ceiling the author was told they had |
| **C6** | **PARTIAL — installable now, not yet published.** `cargo install --path crates/pact-cli` puts `pact` on the PATH and works: the schema and the model catalogue are `include_str!`, so an installed binary carries them. The adapters were **not a package at all** — no `[build-system]`, so `uv` refused to install entry points and `pip install` could not work; that was the whole of the Python half. `pact-eval` and `pact-conformance` are console scripts now. Three things `cargo package` refused, all fixed: path dependencies with no version, no description on any crate, and a `description` field left at `uv init`'s *"Add your description here"*. **Publishing itself remains open** and is a release process rather than a code change — the crates must go to crates.io in dependency order, and `include_str!` reaches outside each crate's own directory, which a published crate cannot do. **A warning the gate could never see:** `--all-targets` builds with debug assertions ON, so `SpecSource::Unsafe` — deliberately unconstructible in a release binary, which is what stops `PACT_SPEC` deciding the governance columns in an installed copy — is live there and its `dead_code` warning appeared only on the first `cargo install`. `cargo clippy --release -p pact-cli -- -D warnings` is now in the gate | there is no `pip install pact`, no released binary; everything is `cargo run` from a checkout |
| ~~**C7**~~ | **CLOSED.** `.github/workflows/gate.yml` runs `scripts/test-all.sh` on push, on pull request, and weekly — the schedule so a dependency that moved under us is found by the calendar rather than by somebody's next commit. **It runs the script rather than re-listing its steps**, and a test enforces that: a workflow spelling out `cargo test`, `clippy`, `pytest` is a second copy of the gate, the two drift, and the interesting failures become the ones only one of them catches. **A hole in the gate itself, found while writing it:** `test-all.sh` ran the adapter suite whether or not the CLI had been built, dozens of test files read the worked example through that binary, and the script exited 0 regardless. A gate reporting green over a suite that has quietly stopped checking invariant P-1 is this register's own defect wearing the gate's clothes. It now refuses. **This row said "39 test files" and "19 tests skip" and both were stale**, which is a count in prose beside a computed one — the failure the A6 and AC-2.1 rows above were rewritten to stop making, still being made here. The live figure is stated **once**, in the script's own refusal message, and `test_the_gate_is_run_by_something.py::test_the_gate_refuses_to_run_the_suite_without_the_loader` fails when it stops matching `grep -rl 'pytest.skip("build the CLI first' adapters/python/tests/`. No number is written here. The TypeScript type check still skips locally when `node_modules` is absent, on purpose — a contributor without node gets a useful run — and CI installs them so the skip never fires there. *(Not to be confused with `docs/remediation/C7-bundle-mounting.md`, which despite the filename answers row **C2** above. `docs/remediation/` numbers its files by its own work items — `C8-profiles.md` answers **AC-7.2** the same way — and `docs/remediation/REGISTER.md` is the index that maps them.)* | the suite is green because it is run by hand |
| ~~**C8**~~ | **CLOSED.** `.pact/` still lands beside the workspace by default, and **`$PACT_DERIVED_DIR` redirects the whole derived area** — so a read-only checkout is run by pointing it somewhere writable rather than by copying the tree. An environment variable and not a field: where derived output lands is a deployment fact, and a workspace that named its own would stop being runnable in two places. **The worse half was that it did not degrade** — `base.mkdir` raised inside a bus handler, so an observability feature took down the run it was only observing. Writability is now asked ONCE when the watches attach (a run that discovers it on the fortieth event has already said nothing about the first thirty-nine), the run survives and names the record it could not keep on `RunResult.unwatched`, and both learning ledgers degrade the same way — a cycle that fails because it could not write down that it happened has turned bookkeeping into a run failure. **A regression this change first caused:** the writability probe CREATES the area, so a workspace declaring no `watch:` acquired a `.pact/` for having been run — caught by an existing test, and the probe is now skipped when there is nothing to write. It also bit inside this repository earlier: a test pointed a real learning cycle at `examples/refund-desk`, whose spend ledger the spend-ceiling test then `copytree`d into its own fixture — twenty-eight recorded runs at `money: 0.0` diluted `per_run` to zero and five passing tests went red. Both copies exclude `.pact` |
| ~~**C9**~~ | **CLOSED, at both doors, and they are guarded differently.** B3 put a floor under money in `Schema::check_floor`, so `cost-per-request-under: NaN USD` (and `inf`, `-inf`, `-5`, `0`) is `schema/below-the-floor` where the author WROTE it, and `learning.cycle-limits.per-month` with it — held end to end through the real binary by `adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py`. The other door was a SPEC BUILT IN CODE, which `pact check` and `pact show` never see: `Limits.from_mapping({'cost-per-request-under': 'NaN USD'})` parsed to `nan`, `Limits.reached` said nothing at `sys.float_info.max` or at `math.inf`, and `adapters/typescript/src/limits.ts` read it identically, so **both ports** ran fully metered under no cap at all — measured at 6000 USD spent with `unmetered=()`. There is nothing to refuse on that route, so somebody is TOLD instead: a cap **no spend can ever be at or above** is dropped rather than carried as a row `reached` can never satisfy, and `cost-per-request-under` is named on `RunResult.unmetered`. **The guard is on the VALUE, not on a reader.** It was on the readers first — `from_mapping`, `limitsFrom` — and that closed one door of four: measured with the readers guarded, `Limits(cost_per_request_under=float('nan'))` still spent 6000 USD under `unmetered=()` (and `Limits(...)` is written directly at 21 sites in `adapters/python/tests`), `replace(parsed, cost_per_request_under=inf)` still carried a money row, and in the second port a spread over a member's grant carried a STALE `nothingCanReach` beside a real 0.10 USD ceiling — a run able to halt at `cost-limit` on the field it had just said held nothing. It now lives at `Limits.__post_init__`, which every Python route meets, and at `ceilings()` + `capsNothingCanReach` in `limits.ts`, because a TypeScript object literal has no construction hook. **The record is the FIGURE the author wrote, not a field name**, and the first round of this got that wrong: the stored `nothing_can_reach` tuple claimed to be *"DERIVED, not accepted"* and was neither — measured, `Limits(tool_calls_at_most=1, nothing_can_reach=('tool-calls-at-most',))` ran to `halted='tool-call-limit'` and reported that live ceiling on `unmetered` with the MONEY remedy attached, which is the wrong-diagnosis defect `_unmetered_caveats` exists to remove. A name carries nothing to check it against; a figure does, so `cap_nothing_can_reach` / `wall_nothing_can_reach` hold the written figure, `nothing_can_reach` is a read-only view over them, no constructor argument spells the claim, a hand-set record something CAN reach is dropped, and a real figure arriving clears the record beside it. **`wall_clock_s` is guarded too** — the other float ceiling in the same dataclass carried the identical pathology through the identical door (`Limits(wall_clock_s=inf)` -> row built, `halted='step-limit'`, `unmetered=()`), and the authored route was already shut (`seconds('inf') is None`), so the constructor was the only way in; `_unmetered_caveats` gained a duration remedy so a `runs-for-at-most` that holds nothing is not sent to the money line. **The currency is no longer destroyed:** clearing `cost_currency` beside the amount made two members of one team, handed the same 0.10 USD share, print `(0.11 of 0.1)` and `(0.11 of 0.1 USD)`, and the second port keeps the currency through the same spread — so it was also the two ports printing different `stoppedBy.unit`. `Slo` was the **third reader** of the same line and is guarded the same way: an `inf` cap there produced a true sentence with the wrong reason in it, sending the author to `tokens-at-most`'s price rather than to their own figure. It took the drop and **skipped the report** for a round — `Slo.unmetered()` returned `self.written`, which is built from `first-reply-within` and `per-word-under` alone and could never carry this name — so with the two readers decoupled (`AgentSpec(slo=Slo(cost_per_request_under=nan), limits=Limits())`) a run spent **6000 USD with `unmetered=()`** under an `S-GOV`, `tier: core` cap the author had typed, which is the T7 / FR-8.1.1 silent degradation surviving inside the fix; for `inf` it was a strict regression from a wrong-reason sentence to no sentence at all. `Slo` now carries `cap_nothing_can_reach` and reports it, is **frozen** (its own guard argued for construction *"where every route in meets"* while post-construction assignment restored the whole pathology), and `harness._delegating` hands the join policy's share to BOTH readers. The machine-readable half was fixed with it: `session.limit.failed` carried one list for two reasons beside the transport's name — byte-identical payloads with the transport blamed for a fault it did not cause — and now carries `held_nothing` as well. **`unmetered` and not `never_reached`**, for two reasons: `never_reached` is a fact about the BINDING, built out of the bound model's catalogue price, where this is a fact about the written line; and it exists in one port, so reporting it there would mean inventing a third channel in the second. The sentence a person reads is its own: `scoring._unmetered_caveats` splits this member out of the hard-coded *"fix: nothing to type — what can be measured depends on what the model reports back"*, which for a figure the author typed is a right field name with a wrong diagnosis and a remedy saying do not act. `-inf USD` is deliberately left — `spent >= -inf` is true of every spend, so it fires on the first step and stops the run LOUDLY, and it is the only value exercising the non-finite arm of both reporters (`test_both_ports_read_every_way_a_spend_cap_is_written.py`); the guard is therefore *"no spend can be at or above this"* and not *"this is not finite"*. The EFFECT is held across both runtimes by `adapters/python/tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py` (36 tests: four Python routes into the value, the wall-clock ceiling, the forged record, the currency across the join, a delegated member handed a real share with a positive control proving the bus channel is alive, the three caveat sentences, the third reader through the whole harness, the machine-readable event, and the second port through `run-trace.ts` with `-inf` as the contrast that keeps every `stoppedBy` assertion biting; thirteen single-edit mutations recorded in the file, each measured); the three tests in `test_a_spend_cap_that_can_never_be_reached.py` that pinned the old silence were flipped in the same change and now assert the report. **The RUN-TIME half reached only ONE of the two ceilings until the B3 document was written, and the gap was the worse kind.** `learning.cycle-limits.per-month` had `_nothing_can_reach` on no route at all — measured, three real cycles against a real `.pact/learning/` ledger with `per-month: NaN USD` spent 8.00, 16.00 and 24.00 USD with `Outcome.unmeasured=()` on every one, because the enforcement site is `would_reach > amount` and `Learner._unmeasured` enumerated exactly three reasons the ceiling can fail to bite, none of which a non-figure is. So the honesty channel built for that field AFFIRMED a ceiling that held nothing, on an `S-GOV`, `tier: core` self-improvement budget reachable from a FILE at run time. It is now closed three ways: `Permissions.per_month_cap()` drops the cap, `Learner._unmeasured` gained a fourth sentence quoting the written line, and **`Learner._decide` REFUSES the cycle** — fail-closed, unlike `Limits.__post_init__`, because there the decision point is a method call with no money spent yet and `Outcome(False, …)` is already the module's answer, whereas `Limits` is a frozen object on the delegation path where raising would kill a run one line before it became correct. Held by `adapters/python/tests/test_a_monthly_ceiling_nothing_can_reach_refuses_the_cycle.py` (29 cases; 24 fail with the three edits reverted). The schema floor also had ZERO cargo-run coverage — measured, all 60 `pact-cli` test targets green with the money arm deleted — and now has `crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs`, which cargo builds the binary for so it cannot go stale. Full record: `docs/remediation/B3-money-has-no-floor.md`. **A third money field is deliberately NOT in this row:** `more-than:` on an approval gate is a gate and not a ceiling, so `more-than: 0 USD` ("ask about every refund") stays legal; a non-finite one does not, and is refused by `loader/threshold-is-not-a-figure` in `crates/pact-loader/src/money.rs` — the schema cannot see it, because A3 made the field `type: text` so a score could be gated by a score | a ceiling the author was told they had, reached by the one route the checker never sees |
| ~~**C10**~~ | **CLOSED, at both ends of the number line and at both doors.** The OVERFLOW half was already shut: `resolve_scalar` refuses to read a scalar it cannot hold as a number, so `x-threshold: 1e999` keeps the author's text through `pact show` and the digest, and a `type: number` or `type: threshold` field given one is refused by `schema/too-big-to-count` at the line it was written on. The UNDERFLOW half is now shut by the narrow rule this row worked out: **a scalar that comes back as zero while its SIGNIFICAND carries a figure other than zero is not zero**, and is kept exactly as it was written. So `x-tiny: 1e-999` round-trips as `"1e-999"` through `pact show`, and that workspace and one saying `x-tiny: 0` no longer share a digest — measured, `sha256:ba68ad81…` against `sha256:4d26af60…`, where before they were the same string. The two guards the row named are both held: the exponent is not looked at, so `0`, `0.0`, `-0.0` and `0.0e10` stay the zeros somebody meant (`0e10` is text for an older reason — the leading-zero rule that keeps `007` a code), and the general *"only accept a float that round-trips its own text"* rule is NOT used, because it refuses `1e10` → `10000000000.0`, a number nobody would call corrupted. **The second half this row also owed** is `Schema::check_ceiling`'s mirror arm, `schema/too-small-to-count`: where the specification says a figure is wanted, `settings: temperature: 1e-999` is refused at the author's own line — *"'temperature' is 1e-999, which is closer to zero than this can keep track of"* — rather than read back out of the kept text as a zero they never wrote, and NOT as `schema/wrong-type`, which would send them hunting a typo that is not there. One sentence for both signs, unlike the top end: `-1e-999` is `-0.0` and needs the same edit. **A THIRD half, found by the per-issue pass against the fixed build:** the arm was written for `number`, `threshold` and `size` and NOT for `percent`, which is the same comparison written the way an eval suite writes a bar. `must-pass: 1e-999%` divides by a hundred, lands on `0.0` inside `0.0..=1.0`, and loaded clean — measured on `examples/refund-desk` with its `must-pass: 70%` replaced: `OK — rd loaded cleanly (498 settings)`, exit 0, both before this whole change and after it, on a bar every suite on earth clears. `when-full: 1e-999%` is the same silence one field over. It is refused now, by the same rule and the same sentence. **A FOURTH AND A FIFTH half, found by attacking the landed fix**, both of them damage the fix itself did by changing what the typed fields are handed. (a) The size arm was `Size(0) if underflowed_to_zero(0.0, node)` — a HARD-CODED zero, which never asks whether anything underflowed — so `context-at-least: "0.5"`, `"0.9"` and `0.0004k`, figures an `f64` holds to the last bit, were told they were *"closer to zero than this can keep track of"* and offered *"any number further from zero"*, which `0.0004k` already is. There are three zeros, not one: a zero somebody meant (`0`, `0k`) loads, a real figure TRUNCATED to nothing by the `as u64` (`0.0004k`, `"0.5"`) is now `schema/below-the-floor` — *"which is no tokens at all"*, the sentence `finishes-within: 0.4ms` already had — and only a figure that was never held (`1e-999`, `1e-999m`) is `schema/too-small-to-count`. (b) `Schema::wrong_type` builds its noun from `Value::kind_name`, so the moment a figure started being CARRIED as text every typed field falling through to `wrong-type` began calling a run of digits *"some text"*: `steps-at-most: 1e-999` and `steps-at-most: abc` produced byte-identical reports where before the fix the first said *"but it is a number"* — a true noun LOST, and the exact harm D13 and `coerce`'s own capitalised note forbid. The noun is now read off the written text (`kind_as_written`), and `integer` gets the mirror `Coerced::IntegerTooSmall` so its bottom end is named as its top end is. `duration` and `money` keep `schema/wrong-type` and are right to — `1e-999` carries no unit and no currency — but no longer call a figure text. Held by `crates/pact-cli/tests/a_number_too_small_to_hold_is_kept_as_it_was_written.rs` — fifteen tests, ELEVEN mutations, each applied on its own, measured, and reverted with a full green run in between to prove the revert took (the previous record here was stale: it reported `6 passed; 5 failed` for mutation A when the truth was 6 failed, and quoted totals for a file size that no longer existed — see queue row G5). Blindness measured too: `cargo test -p pact-doc` passes 52/52 with the document-layer guard deleted and `cargo test -p pact-schema` passes 113/113 with the ceiling and floor arms deleted, so those arms have no second door; `pact-schema` DOES catch the two `coerce` mutations, because `coerce::tests` asks the coercer directly. **What stays open** and is bounded rather than waved at: distinct decimal literals still collapse onto one `f64` (`3e-324`, `5e-324` and `7e-324` all digest `sha256:1882cd2c…`), and the obvious widening `f.is_subnormal()` was measured and REJECTED because `1e-310` is subnormal and loses nothing (two distinct digests, measured) while `"0.1"` collapses in the normal range anyway — so the line stays where the figure is gone rather than rounded, and the absolute losslessness claim in the module prose was narrowed to match. **A SIXTH HALF, and the one the per-issue C10 pass was written for: the rule that closed the digit-run spelling asked about PUNCTUATION and not about the figure.** It was *"an optional sign, then ASCII digits, that `i64` cannot parse"*, so one `.` walked past it: measured through the shipped binary with that fix fully in place, `x-big: 99999999999999999999.0`, `…9998.0` and `100000000000000000000.0` published ONE hash — `sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888`, byte for byte the hash this row calls the harm — and `settings: temperature: 99999999999999999999.0` was `OK — loaded cleanly`, exit 0, with `pact show` handing the runtime `1e+20`. The same rule made the checker contradict itself about single values: `temperature: 1e19` loaded while `temperature: 10000000000000000000`, the same `f64` to the last bit, was refused as *"more than this can keep track of"* — a sentence the first line proves false — and `context-at-least: 1e19` was *"not a size"* while `context-at-least: 10000000000000000000` loaded cleanly. Both halves now ask about the FIGURE, once each: `pact_doc::whole_number_past_holding` keeps a scalar as text when the whole number it spells is not the whole number the `f64` writes back (`1e10`, `1e20` and `10000000000000000000` write back exactly what was written and stay numbers; `0.1` and `0.7` spell no whole number and are untouched, because the exactness rule that would catch them refuses every ordinary decimal in the format), and `coerce::PAST_COUNTING` — 2^53, the last whole number a double can tell from its neighbour, which is precisely what the sentence claims — is asked by `Ty::Number`, `Ty::Threshold` and `Ty::Size` alike, while `Ty::Integer` keeps `i64` because there the machine really is one. **Four more doors were still shipping the condemned *"but it is some text"*:** `finishes-within: 1e999s`, `1e300h`, `1e999 seconds`, `1e400 ms` and the perfectly ordinary `1e6s` (the parse loop read the `e` as a unit; only the BARE spelling had been closed, and `pact_adapters.limits.seconds` and the TypeScript reader were moved with the fix, since a spelling the gate passes and the reader answers `None` to is no ceiling at all); `tokens-at-most: 1e6` and `1000000.0` (*"should be a whole number, but it is a number"*, with the fix *"Change it to a whole number"*); `when-full: 1e999%` and `-1e999%`, the top end of the share this row's own fifth half gave a bottom end to; and `finishes-within: 1e308`, which was *"not a length of time"* while `1e999`, a LONGER time, was too long. **The fix line was false and its test only matched it:** *"or any smaller number"*, against a refused `1e999`, while the smaller `9223372036854775808` was refused by the identical rule — it now reads *"or any figure of fifteen digits or fewer"*, which is true for every type that offers it, and `the_fix_is_followed_rather_than_matched` types the offered line back into the file instead of asserting the string is present. **One guard had no test at all:** deleting the word-test from `coerce::duration`'s bare-infinity special case left this file at 15/15, all of `pact-cli` green and all of `pact-schema` green while `finishes-within: inf` was told it was *"a longer time than this can keep track of"*; the special case is now gone entirely and `finishes-within: inf|nan|Infinity|-inf` is pinned. **And the repair opened one silence of its own, closed in the same pass:** a bare `context-at-least: 0.5` reached `check_floor`'s `Size(0)` arm, which asked `node.as_str()` and gets nothing from a float, so it loaded CLEANLY as a context window of zero. Nineteen tests, THIRTEEN mutations, each applied on its own, rebuilt, measured and reverted; the previous mutation record here did not reproduce (it claimed `6 passed; 3 failed` for mutation A where the truth on the shipped file was `10 passed; 5 failed`) and every count is now recorded beside the names of the tests that fail under it. See `docs/remediation/C10-number-too-big-dead-end.md`. See `docs/remediation/C12-underflow-to-zero.md` | was: two different documents, one digest — a lockfile pins the wrong one and nothing says so |
| ~~**C11**~~ | **CLOSED, and the first closure of it held for one file rather than for a tree.** A YAML shortcut (`&name`/`*name`) copies its whole block in at every use, and `pact check` was killed outright by a twelve-line agent file: `memory allocation of 1368 bytes failed`, signal 6, EXIT=134 — no file, no line, no rule. That much was fixed by charging what a copy costs **before** the copy is made. Three further ways to reach the same abort were then found against the fixed build and are also closed, each measured on this tree. **(a) Defining `&name` keeps a second copy of the block, and that copy was charged against nothing**: 62 definitions written inside one another, 190,000 words, and **no `*name` anywhere in the file** took `pact check` to `PEAK_KB=3683232` and, under `ulimit -v 1500000`, to signal 6 — the same tree with the `&`s deleted peaked at 127,816 KB. Every test that held the fix reached it through `Event::Alias`, which that document never produces. **(b) Both budgets reset per file**, so 400 agent files of 277 bytes — each one inside `MAX_NODES`, 110,817 bytes on disk altogether — killed `pact check` AND `pact discover` at `PEAK_KB=2998240`, EXIT=134, on the build that had fixed every single-file case. `pact discover` is the command D2 specifies for walking trees nobody vouched for, so this was a loader any untrusted folder could stop, and the test file that claimed otherwise built workspaces with exactly one agent in them. `pact_loader` now carries a running total across the whole load (`MAX_LOAD_SETTINGS = 1_000_000`, `MAX_LOAD_TEXT = 64 MB`, both measured against ~320 bytes of peak resident memory per setting) and refuses **once**, as `loader/too-much-to-load`, naming the file that crossed the line: same folder, `PEAK_KB=360512`, EXIT=1. **(c) The refusal misdescribed the author's own tree**: once a shortcut had spent 199,941 of the 200,000 settings, the next ordinary `z5: 1` tipped it over and got *"This file is too large to load… Split it into several files"* with the caret under `z5: 1` on a 738-byte, 72-line file. The report now points at the widest `*name` when shortcuts paid for more than half the budget, and a file whose `&name` definitions are the cost gets a third wording that says so. Held by `crates/pact-cli/tests/a_shortcut_that_copies_itself_cannot_bring_down_the_checker.rs` (seven tests, both commands, folders as well as files) and six tests in `crates/pact-doc/src/yaml.rs`; eight mutations, each applied, measured and reverted. **What is open** is F-1: this closure adds two capability-affecting literals to the Rust core and ties a third (`pact_doc::yaml::MAX_TEXT`, now the single source for `Policy::max_text_bytes`), all filed DELIBERATE_AND_CLOSED in the source with the reason, which is a filing and not the audit **D-4** owes. See `docs/remediation/A3-yaml-alias-bomb.md` | was: a folder a runtime was specified to discover could stop the checker with no diagnostic at all, and nothing in this register said so |
| ~~**C12**~~ | **CLOSED, and the closure had a second, quieter half of its own.** A length of time was added up with `*total += (v * mult) as u64`, and a float-to-whole-number cast in Rust SATURATES rather than failing: one oversized part pinned the running total at the largest number there is and the next part went over the top of it. In a debug build — what `cargo run` and this README give an author — `finishes-within: "99999999999999999999h 99999999999999999999h 99999999999999999999h"` killed the command outright: `thread 'main' panicked … attempt to add with overflow`, EXIT=101, no file, no line, no rule. In a release build it did not die, which is worse: `OK — loaded cleanly (498 settings)`, EXIT=0, and `pact waits` handed a scheduler **53,255,926,290,448,384 ms** for three parts that summed just past the top — about 616 days, in place of a figure the author would have recognised as absurd. Now the cast is guarded on `ms >= u64::MAX as f64` (2^64 exactly, so the guard *is* the boundary) and the addition is `checked_add`; a length of time that does not fit leaves the reader as `Coerced::DurationTooLong` and is refused one layer up by name — `schema/too-long-to-count`, at the author's own line, with a line they can type — for the same reason `0s` is refused at the floor rather than called "not a length of time". `loader/wait-with-no-deadline` no longer asks whether the deadline *parsed*, so a refused deadline is not also reported as never written. **The second half**, found against the fixed build by the per-issue pass: the cast TRUNCATED, so `answer-within: 1.001s` reached `pact waits` as `"deadline-ms": 1000` — a millisecond short, silently, and a millisecond away from what the Python port reads. It rounds now. Held by `crates/pact-cli/tests/a_duration_means_what_the_help_says.rs` (9 tests, through the real binary and through `pact waits`), `crates/pact-schema/tests/durations_say_what_they_accept.rs` and three tests in `coerce.rs`; two mutations, each applied, measured and reverted. **What is open**, and named rather than fixed: above 2^53 ms the figure kept is not exactly the figure written (measured, `9007199254740993ms` → `9007199254740992`), and the top 616 ms below the limit is refused though it fits — both 585 million years out, both residuals of counting in floating point. Note the name collides twice: queue row `C12` is `underflow-to-zero` and fix-plan `B4` is the `park()` helper; this row is neither. See `docs/remediation/B4-duration-overflow-panic.md` | was: one line of one file could kill the shipped checker, and where it did not, the ceiling a runtime enforced was not the one anybody wrote |

---

## What to do, in order

Ordered by consequence. Each states the test that would prove it landed.

**Items 1, 2, 3, 4, 5, 6 and 7's second half are DONE** — each is marked closed
or met in its own row above, and this list was left saying otherwise for as long
as it took somebody to read both halves of the same document. It is kept in the
original order rather than rewritten, because the ORDER is the argument and
deleting the done items would take the reasoning with them; what follows the
strikethrough is the row that holds each, and the row is where the evidence is.
**What is left OF THESE EIGHT ITEMS** is item 7 — **AC-5.1's three missing
patterns** (blackboard, market, auction — they need primitives that do not
exist) **and AC-5.2's four unanswered names** (Tree-of-Thought and
self-consistency, answered by shapes that refuse the names in their own files;
Reflexion, answered in part and with its missing half refused in
`docs/remediation/F6-reflexion-has-no-memory-across-runs.md`; and CodeAct, which
is a refusal rather than a shortfall — this list said 5.2 was met, and that was
wrong; see the 5.2 row and
`docs/remediation/F5-two-loops-named-for-what-they-are-not.md`) — and item 8,
**AC-1.5's human trial**.

**That is not the same as what is left in this document, and the first version
of this paragraph read as though it were.** It said the only remaining work was
those two plus Class C, which quietly retired **four criteria and seven partials
the tables above record as unmet** — two of them written up as unmet in the very
change that wrote the summary. An inflated register is worse than a rotted one,
and a reader who stops at this section, which is what this section is for, would
have been told the only work left was three patterns, a human trial and Class C.
The open work this list never contained:

- **AC-6.1/6.2** — the largest open item in the document and the only one
  **BLOCKED** rather than undone: the `gaia-ai-runtime` integration exists in
  neither direction, and AD-92 names **two changes to that repository**, another
  team's codebase, that closing it requires. Nothing here can do it.
- **AC-6.4** — unmet on both halves: no **recipe**, **custom agent** or **skill**
  importer exists, and no re-export-and-compare path exists for the two importers
  that do ship, so the *"without behavioural change on the CTS"* clause is unheld
  even for them.
- **AC-7.2's profile half** — `workspace.profile` is now warned about rather than
  silent, and `docs/remediation/C8-profiles.md` decides that no profile
  **mechanism** should ever exist: the criterion's two halves pull against each
  other, and both shipped layering mechanisms (`based-on:`, `feel:`) write the
  layer's name beside the value it changes, which a workspace-level `profile:`
  cannot. What is left is therefore an **amendment** — to AC-7.2, F-1, FR-8.1.3,
  `docs/20-ARCHITECTURE-DRAFT.md` and `site-docs/reference/kinds.md` — plus
  deleting the field and the five defects that decision's price names, not a
  resolver. **The audit half that IS met is met over the Python adapter package,
  not the Rust core**; closing that (D-4) is what lets the amended criterion use
  the word "core".
- **AC-2.5's second half** — the out-of-tree adapter is a separate *directory*,
  and the criterion asks for a separate *repository*, which needs publishing (C6).
- The criteria the *"Was listed Met"* table downgrades to **PARTIAL** — the row
  reading `3.1, 3.4, 5.4, 3.3, 3.1b, 2.3, 1.1` — each with a real half and a
  missing half. **No count is given, and the list is not repeated anywhere else**:
  these are not the only PARTIAL rows in this document (`5.1`, `5.2`, `6.3` and
  `7.2` carry their own, `5.2` as of this change), and a figure here would be a
  second copy of a set that grows.
- The Class C rows still open: **C2, C3, C4, C5, C6**.

**The eight items, in the original order:**

1. ~~**Wire G9 (A1).**~~ **DONE — see A1.** *Proof:* an approval recorded before a shortening still
   gates the call after it, driven through `pact show` with nothing passed in.
2. ~~**Give model selection a door (A2).**~~ **DONE — see A2.** Add `--choose-model` to the scoring
   entry point, calling `resolve()`. *Proof:* the command refuses a failing model
   and names a cheaper passing one. Held by
   `adapters/python/tests/test_the_model_choosing_door_survives_being_opened.py`,
   which came out of the door raising a `TypeError` out of the middle of the
   search the first time anybody opened it — the proof above was written against
   a command nobody had run.
3. ~~**Wire or delete `model-for-checking` and `answers-with-mode` (A5).**~~ **DONE — see A5 and A6.** A field
   with no reader should not be in the schema. *Proof:* a test asserting every
   `agent` field has a reader — which would have caught all of Class A. That
   test is `adapters/python/tests/test_every_field_has_a_reader.py`, and both
   fields are read; its `KNOWN_GAPS` is empty.
4. ~~**Build the golden set (AC-2.1).**~~ **DONE — see AC-2.1.** Twelve agents spanning the patterns, run
   across all seven targets. *Proof:* the conformance suite over twelve, not one.
   It is every agent under every `examples/**/workspace.yaml`, over eight
   targets — `len(GOLDEN)` in
   `adapters/python/tests/test_the_golden_set_runs_everywhere.py`, and **no
   figure is written here**, because the first version of this line copied one
   (`28 agents`) that had already gone stale in the row it copied it from.
5. ~~**Version the spec (C1).**~~ **DONE — see C1.** *Proof:* a document declaring an unknown version
   is refused with the version it needs.
6. ~~**Wire the learning cycle (A3)**~~ **DONE — see A3.** `--propose FIELD=FILE` is the door.
7. **Ship loop and orchestration patterns (AC-5.1, 5.2)** as library documents.
   Both are **PARTIAL**. **5.1**: eight patterns ship and `blackboard`, `market`
   and `auction` cannot be built on today's primitives — refused, with the price,
   in `docs/remediation/F7-blackboard-market-auction.md`. **5.2**: six loop
   shapes ship, and of the six techniques the criterion names, ReAct and
   Plan-and-Execute ship, Reflexion ships in part, Tree-of-Thought and
   self-consistency do not ship, and CodeAct is refused — `standard` answers
   none of the names. The three approximations' limits are stated in their own
   files (or, for `reflexion`, in F6) and were not stated here — corrected in
   `docs/remediation/F5-two-loops-named-for-what-they-are-not.md`. Both halves
   are still owed, and both want the same absent primitive: a stage that can run
   again with a different context rather than a longer one.
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
