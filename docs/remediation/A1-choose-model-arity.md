# A1 — the `--choose-model` flag shipped with a door nobody could open, and five live defects were sitting behind it

**Severity: critical.** · **Status: fixed — the arity first, then eight further
findings raised against that fix, all of them repaired.** · **Corrects register
row A2, `docs/70-PRODUCTION-GAP-REGISTER.md:106`**, which said the door was open
when it could not be opened once.

Every number below names the command that produced it. Where a measurement was
taken in an earlier session of this work rather than re-taken here, it says so on
the line. Two other sessions are editing these same files right now, so nothing
in the source was reverted or mutated to write this document; what could be
re-measured without touching the tree, was.

---

## What is wrong

`pact-eval <folder> --choose-model` exists to answer one question a person cannot
answer by reading a catalogue: **can this model actually do this agent's job?**
It runs the author's own eval cases against the model the agent names, and if
that model does not pass, against the rest of the catalogue — and binds one, or
refuses and says what happened to each row.

The flag parsed. It was in the help. The README showed a `PORTABILITY:` report as
though you could produce one. A test asserted the capability was reached.

It could not be reached once. Deep inside the search, the code that scores one
candidate needs a way to *build* a connection to it, and asks for that by calling
a small factory the caller hands in. The protocol for that factory is written
down in `resolve.py` and takes **two** things — which model, and which strategy
variant is being tried. The one place in the shipped product that supplies such a
factory, `scoring._choose`, supplied a **one**-argument lambda. The first time
the search tried to build a connection, Python raised, six frames down, and the
command died in a stack trace instead of a report.

**Reproduction, measured in the repair session by restoring the pre-fix line and
running the shipped entry point** (not re-run here — reverting a shared file
would race the other sessions):

```console
$ env PYTHONPATH=adapters/python/src PATH=/usr/bin:/bin python3 -c \
   "from pact_adapters.scoring import main; raise SystemExit(main( \
    ['examples/refund-desk','--choose-model','--serving-at','http://127.0.0.1:9/v1']))"
Traceback (most recent call last):
  ...
  File ".../pact_adapters/resolve.py", in evaluate
    transport = transport_for(model, strategy_name)
TypeError: _choose.<locals>.<lambda>() takes 1 positional argument but 2 were given
```

**The contract that line violates, re-measured here without touching anything**
(`cd adapters/python && uv run python` against the tree as it stands):

```console
TransportFactory  : typing.Callable[[str, str], typing.Any]
the call          : transport = transport_for(model, strategy_name)
```

That is `resolve.py:1064` (the alias) and `resolve.py:1207` (the call). Two
arguments, stated and used. The shipped caller passed a function that accepted
one.

Two further faults were **hidden behind** the crash and only became visible once
it was fixed, and five more were introduced or made reachable *by opening the
door*. They are in **The fix** below, because on this issue the repair and the
findings against the repair are the same story.

---

## Root cause

**Two independent factories existed for one protocol, and only the wrong one was
on the shipped path.**

`resolve()` has exactly **one** production caller in the whole tree. Measured:

```console
$ grep -rn "resolve(" adapters/python/src/pact_adapters/*.py
adapters/python/src/pact_adapters/scoring.py:1005:    report = resolve(
```

(the other hits that grep returns are `Path.resolve`, `Loop.resolve` and
`ContextPolicy.resolve` — different functions with the same name). Every other
caller of `resolve()` in the tree is a test, and all of them pass a factory the
**test file wrote for itself**, with the right two parameters. So the two-argument
protocol was exercised exhaustively, always by a factory the suite built, and
never once by the factory the product builds.

`_choose` was written later than `resolve()` — it was added precisely to close
the "resolve() has no shipped caller" gap the register records as A2 — by
somebody reading `_transport_for(name, serving_at, root)`, which returns a
builder taking **no** arguments, rather than reading the `TransportFactory` line
one module over. `lambda name: _transport_for(name, serving_at, root)()` is the
shape you write when you are thinking about the wrong signature.

**The class, which is the part worth carrying away.** The register's standing
class is *"a mechanism is built, tested, correct; nothing on the authored path
ever builds one."* This is the next stage of that disease and deserves its own
name:

> **Reachability asserted by grep, not by execution.** A source-grep is true of
> code that raises on the line it matched.

The test that guarded this capability asserted that the *string* `resolve(`
appeared in `scoring.py` after `def _choose(`. It did — the whole time, on the
line that crashed.

There is a second, shared root behind the other two original faults: the search
had **no exception handling at all** around the run, because every test that had
ever driven it used an in-process scripted transport that cannot fail to connect.
*"The model is not served"* — the ordinary state of an air-gapped box, where
nothing is serving yet — was a state no test had ever put the search into.

---

## Why nothing caught it

Not "there was no test". The test existed, was named for exactly this capability,
sat in the file the suite treats as its gate file, and passed on every run. It
read:

```python
src = Path(scoring.__file__).read_text()
assert "def _choose(" in src and "resolve(" in src.split("def _choose(")[1]
```

Its own docstring declared the limitation as a design choice: *"Asserted at the
seam rather than by running models: the flag exists, the parser accepts it, and
`_choose` is what calls `resolve`."* All three of those sub-claims were true while
the command was one hundred per cent dead.

Three blindnesses reinforced it:

1. **The test it deferred to was measuring a different factory.** That docstring
   pointed at `test_model_portability.py` for correctness. That file drives
   `resolve()` nine ways — always through its own two-argument helper. It tested
   the *protocol* and never the product's *implementation* of it. No test
   anywhere called `scoring._choose`.

2. **The one mechanical check that would have caught it does not run.**
   `TransportFactory = Callable[[str, str], Any]` states the arity exactly.
   Measured: `grep -n "mypy\|pyright\|ty check" adapters/python/pyproject.toml
   scripts/test-all.sh` returns **zero hits**. With no type checker in the gate,
   that annotation is prose. Python binds a callable of any arity happily and
   only complains at call time — and the call was never made, because nothing
   ever ran the command.

3. **The orphan walk was satisfied too.** `test_a_reader_is_reachable_from_a_run.py`
   carries a hand-written table declaring that `scoring` reaches `resolve`, built
   from an abstract-syntax-tree call graph. Such a graph sees a call node; it
   cannot see that the call raises.

---

## The fix

Three source files. The line numbers are as the tree stands today (other sessions
are editing these files, so a line may have drifted by the time you read this;
the names are stable).

### 1. The arity itself — `scoring.py:1000-1003`

```python
def transport_for(model_name: str, _strategy_name: str):
    entry = by_name.get(model_name)
    tag = (_served(entry, serving_at)[0] or model_name) if entry else model_name
    return _transport_for(tag, serving_at, root, connect=5.0)()
```

Two parameters. The second is bound and ignored on purpose — a transport does not
vary by strategy; only the spec handed to the run does. The reasoning is written
at `scoring.py:969-999`.

`connect=5.0` is new and is a consequence stated plainly rather than hidden:
**before the fix the search opened no socket at all**, because it died on the
line that *builds* the transport, one statement ahead of the first request. Now
it really dials, once per qualifying catalogue row per strategy. Against a dead
address that is instant; against a firewalled address that drops packets rather
than refusing, a flat ten-minute timeout would cost ten minutes a row. The
connect phase is therefore capped at five seconds while generation keeps the full
ten minutes (`scoring.py:1196`, `connect: float = 0.0` by default, so the other
call sites are byte-identical in behaviour).

The `_served` lookup is the second half of that line and was **found while
opening the door, reported by nobody**: the search asked the runtime for the
*catalogue id* while the scoring path one screen up asks `_served` for the tag
the runtime has on disk. `qwen2.5-vl-7b-instruct` is what a person types;
`qwen2.5vl:7b` is what Ollama serves. On a real box every locally-served
candidate would have come back 404 and been reported as *"this machine is not
serving them"* — the same false diagnosis this whole change is about, reached by
a different road.

### 2. Egress is decided before anything dials — `scoring.py:954`, `scoring.py:1125`

**This is the most serious finding of the review, and it is a defect the arity
fix created.** The worked example's `workspace.yaml` says `allow-egress: []` —
nothing here may talk outside this machine. The rule that enforces that lived
inside `_bind`, and `score()` calls `_choose` **before** `_bind`. While the crash
held the search shut, nothing left the box. Once the door opened, it did.

Measured in the repair session with a recording HTTP server bound to this
machine's LAN address (not one of the loopback names in `scoring.ON_THIS_MACHINE`):

```text
BEFORE                                  AFTER
exit: 3                                 exit: 3
requests that reached the               requests that reached the
off-box machine: 36                     off-box machine: 0
  path: /v1/chat/completions             error: `--serving-at http://192.168.1.50:…`
  body: {"model":"qwen2.5-vl-7b-instruct",      sends every case to 192.168.1.50, and
   "messages":[{"role":"system",                this workspace says `allow-egress: []`
   "content":"You decide whether a              — nothing there names `llm`
   customer should get a refund…          rule: scoring/egress-refused
```

The agent's system prompt and the author's eval cases left the machine, in a run
whose own report said of other rows *"this workspace does not let the model call
leave the box"*. The identical command with `--model` sent nothing — which is
what makes it a **guard-ordering** defect rather than a missing rule.

Fixed by extracting the rule into `_egress_refusal` (`scoring.py:1125`) and
calling it as the **first statement** of `_choose` (`scoring.py:954`), before the
catalogue is even loaded. `_bind` calls the same function (`scoring.py:1119`), so
there is one rule with two callers rather than two copies.

### 3. A teammate the agent asks is run, not parked — `resolve.py:1191`

`harness.run` only offers a teammate for real when it is given a way to ask one:

```python
# harness.py
delegates: dict[str, str] = dict(spec.team) if ask_member is not None else {}
```

Without it the teammate is still offered as a tool and still named in the system
prompt — it simply **parks** the run instead of running. `scoring._run_every_case`
builds one and says why in its own comment: omitting it *"measured a suspension
and blamed the model for it"*. The search had none — `grep -n ask_member
resolve.py` returned nothing before this change; it now returns the construction
at `resolve.py:1191` and the call at `resolve.py:1211`.

The shipped worked example the door test runs against declares
`team: policy-checker, fraud-checker`. Measured in the repair session over the
real six-case suite with a stub that calls `policy-checker` once and then answers:

```text
BEFORE  outcome FAIL  score 0.0   results 6
          clear-approve   : expected decision 'approved', got ''
          outside-window  : expected decision 'declined', got ''
AFTER   outcome FAIL  score 0.33  results 6
          clear-approve   : passed
```

The score is not the point — one canned answer to six different questions *should*
fail most of them. The point is `got ''`: six cases out of six blamed on a model
that was never asked.

### 4. Classify what stopped the run; re-raise what is a defect — `resolve.py:1067`, `resolve.py:1215-1222`

The first repair caught every exception around the run and wrote one sentence
under all of it. Two populations landed there that are not a model refusing a
connection: **defects in our own program**, and **the product raising on purpose**
(`harness` raises when a delegated member goes over the budget its grant allowed,
or halts — and finding 3 above made both reachable on this path for the first
time).

`_why_it_stopped` now reads the exception and returns either a kind and a cause,
or `None` — and `None` **re-raises**. Measured here, this session, by calling the
classifier directly:

```console
  httpx.ConnectError         -> ('not-serving', 'All connection attempts failed')
  httpx.ConnectTimeout       -> ('not-serving', 'nothing accepted the connection before it timed out')
  httpx.ReadTimeout          -> ('stopped', 'the connection was accepted and no answer arrived before the request timed out')
  json.JSONDecodeError       -> ('not-a-runtime', 'something is listening there and what it sent back was not JSON, so it is not a model runtime')
  RuntimeError (member)      -> ('stopped', 'policy-checker stopped: OVER_BUDGET')
  TypeError (wrong arity)    -> None
  AttributeError (defect)    -> None
```

The last two lines are the whole point: a wrong-arity factory and a missing
attribute are mistakes in **this program**, and they now come out as themselves
rather than as *"start the model runtime"*.

That is also why the line that builds the transport sits **outside** the `try`
(`resolve.py:1207`, with the reason written above it): swallowing a factory error
there would make the door test green against the original bug.

### 5. "Answered three of six and then stopped" is a different fact — `evals.py:270`, `resolve.py:1228`, `resolve.py:1256`

The first repair discarded the results of a suite that stopped, and decided "this
row went quiet" from *"UNDECIDED with no results"* — so **a machine that was
serving perfectly well and had answered half the suite was reported as one that
is not serving anything**. Measured in the repair session over the six-case suite
with a transport that answers one case per row and then refuses:

```text
BEFORE  nothing could be measured: 4 model(s) met the requirements and none of
        them answered — this machine is not serving them. Start the model
        runtime, or run it again with `--serving-at` pointing at the machine
        that does.

AFTER   nothing could be measured: 4 model(s) met the requirements and no score
        could be taken off any — gpt-oss-20b answered 1 of 6 cases and then
        stopped — All connection attempts failed; llama3.2-1b-instruct answered
        1 of 6 cases and then stopped — …
```

Fixed with `Silence` (`evals.py:270`), a frozen record carried on the verdict
(`evals.py:319`) holding the kind, the cause, how many cases answered, how many
there were, and the ungraded-rule sentences. `_went_quiet` now reads
`silence.answered == 0` (`resolve.py:1256`) and `_why_no_score`
(`resolve.py:1400`) groups rows **by remedy and by cause** rather than printing
one sentence over all of them.

Discarding the **score** is still deliberate and is argued at `resolve.py:1239-1252`
(AC-3.1: a figure off a shorter suite is a claim about a different suite).
Discarding the **fact that it answered** was argued nowhere, and was the whole of
what made that false sentence reachable.

### 6. The holes are still printed when the score is refused — `evals.py:326`

`Verdict.unenforced` — the `NOT APPLIED:` lines the report exists to print — is
derived from the results. With the results thrown away, every one of them was
silently zeroed for a stopped suite. That is the silent degradation T7 forbids by
name (`docs/00-THESIS.md:227-232`: *"Every lossy operation … emits a
machine-readable report … There is no silent degradation anywhere in the
system."*). The sentences are now carried on the `Silence` (`resolve.py:1228`)
and read back by `Verdict.unenforced`: **the score stays refused, the hole stays
printed.**

### 7. The flag now does what its own help says — `resolve.py:1378`, `scoring.py:1023`, `scoring.py:155-165`

The help promised it would *"bind the first that passes the bar"*. `_choose` had
exactly two outcome returns: the model the agent already named, or an error. So
the command exited non-zero **over a model it had just watched pass at 83%**,
having spent one model call per case per candidate to find it.

Fixed by making the code true rather than the help. The search's answer is now a
record rather than prose — `Alternative` (`resolve.py:1378`) carried on
`PortabilityReport.instead` (`resolve.py:960`) — and `_choose` binds it
(`scoring.py:1023`). `_bind` still runs afterwards on whatever comes back, so a
chosen row is held to the author's `needs:` and to `allow-egress:` exactly as a
typed one is. The report says which model it bound and why:

```text
model    qwen2.5-vl-7b-instruct — `a-vision-model-nobody-pulled` did not pass
         this agent's own cases, so PACT ran them against the rest of the
         catalogue and bound qwen2.5-vl-7b-instruct — passes at 100% using the
         'authored' strategy, at 0.0/1k tokens
```

The help was rewritten to describe exactly that (`scoring.py:155-165`), including
the part it never said: candidates are tried **cheapest first**, and `variants:`
are strategies, not candidates. The cost is named there too — one model call per
case per candidate.

### 8. No score printed for a row nothing measured — `resolve.py:968`

`render` printed `score 0% vs bar 70%` for rows where nothing had run. Nought per
cent is what a model scores when it answers every case wrongly, not what it
scores when nobody could reach it. The condition is now simply *no results*
(`resolve.py:968`) rather than *UNDECIDED and no results* — because a row refused
on `needs:` before a single case ran has no results either, and was printing the
same false number with a different word above it.

---

## Alternatives rejected

| considered | verdict |
|---|---|
| **Annotate rather than test** — rely on `TransportFactory` to catch the arity. | Rejected. Measured: no type checker runs in this repository (`grep -n "mypy\|pyright\|ty check" adapters/python/pyproject.toml scripts/test-all.sh` → zero hits). The annotation is documentation, not a check. |
| **Keep the source-grep and add a second grep for the arity.** | Rejected. A grep is true of code that raises on the line it matched; that is precisely how this shipped. |
| **Put the execution in the gate file** rather than a separate file. | Rejected on evidence: the gate file is read on every change, is not subprocess-isolated, and an assertion there that shells out to `target/debug/pact` fails for reasons unrelated to what it claims (it was observed failing once in three full-suite runs while a `cargo test --workspace` relinked the loader underneath it). The landed compromise puts the execution in a skip-guarded, subprocess-isolated file, and has the gate file assert that file exists **by name** — so deleting it is visible from the gate without importing the flakiness. |
| **Fix the crash by filtering the catalogue to what the local runtime serves.** | Rejected, and the rejection is **tested** rather than argued: no hosted row can ever appear in a local runtime's tag list, so this would permanently blind the flag to every hosted model and tell the author nothing about the ones they cannot reach. `test_the_door_names_hosted_models_it_could_not_use` fails if a future "fix" takes this route. |
| **Swallow the transport-build error too** (move that line inside the `try`). | Rejected, and the reason is written at the line: it would have made the door test green against the very bug it exists for. |
| **Propagate everything that is not a transport error.** | Rejected in part. The harness raising because a delegated member hit the budget its author set is **the product working**, and letting it out as a traceback is the same failure in the other direction (D13: the reader is a support lead who cannot write code). It is classified `stopped`, reported with its cause, and only genuine defects re-raise. |
| **Fix the help instead of the code**, so `--choose-model` honestly says it only measures the model already named. | Rejected. A flag called `--choose-model` that can only measure the model already named has a false **name**, not just false help — and it throws away a search that has already cost one model call per case per candidate. |
| **Score the cases that answered before the run stopped.** | Rejected for the score (AC-3.1) and **accepted for everything else**: the count, the cause and the ungraded-rule sentences are all carried now. The first repair got this half-right and the review was correct to say so. |
| **A flat timeout instead of a separate connect cap.** | Rejected: ten minutes a row against a black-holing address. `connect` defaults to `0.0`, so the pre-existing callers are unchanged. |

---

## Blast radius

| touched | what changed | who else reads it |
|---|---|---|
| `evals.py` | `Silence`, three kind constants, `Verdict.silence`, `Verdict.unenforced` unions the carried sentences | every `Verdict` in the tree — additive, all fields defaulted |
| `resolve.evaluate` | gains a **required keyword-only** `document` | two call sites, both inside `resolve.py`; no test called it directly |
| `resolve._went_quiet` | reads the `Silence` instead of the results | one caller |
| `resolve._cheapest_passing` | returns an `Alternative`, not a string | two call sites; `report.recommendation` is unchanged for every reader of the text |
| `PortabilityReport` | gains `instead`; `render` prints `score: not measured` whenever there are no results | `render()`'s other callers untouched |
| `scoring._choose` | returns a three-tuple, refuses egress first, binds what passes, asks the runtime by its served tag | one caller |
| `scoring._bind` | its egress block extracted verbatim into `_egress_refusal` | same message, same rule id |
| `scoring._transport_for` | gains `connect: float = 0.0` | three other call sites keep the previous single flat timeout |

`evaluate`'s new parameter is required and keyword-only **on purpose**: the one
thing it is for is the thing that is silently wrong when it is missing, and a
`None` default is exactly how this module's transport factory came to be optional
in the first place (queue row D3).

**Digest stability — not engaged.** This issue touches three Python files and one
Python test file. It touches no byte of `crates/pact-doc`, `crates/pact-loader`,
or any authored document. Measured: `git status --short examples/ models/` is
clean.

**Both ports — not applicable, by design rather than omission.** Measured:
`ls adapters/typescript/src/` returns `harness.ts, limits.ts, loops.ts,
run-trace.ts, vercel-transport.ts, yes-no.ts` — no resolver, no catalogue reader,
no eval runner. `grep -rn "choose-model" adapters/typescript/ crates/` returns
**nothing**. There is no arity to fix in the second port and nothing new on the
conformance wire, so the four-artifact rule for the closed lists in §7.28 is not
engaged either.

**Honesty channels.** The five channels on a run result reach a portability report
only through `Verdict.unenforced`. Before item 6 above they were zeroed whenever
a suite stopped; they are carried now. This is the one place where the first
repair actively lost information, and it is fixed.

**Counts.** This issue adds one test file and eight tests to an existing one. Both
suite-wide counting tests were red for part of this work and are green now —
measured, `README.md:73` says *2514 tests (888 Rust + 1626 adapter)* and the
adapter suite collects 1626 (1621 passed + 5 skipped). Neither red was this
issue's alone: both count across the whole tree, and roughly twenty other queued
rows added test files into the same working tree.

**Not run, and why.** `cargo test`, `cargo clippy` and `cargo build` were not
re-run for this change: it touches zero Rust.

---

## The test

**File:** `adapters/python/tests/test_the_model_choosing_door_survives_being_opened.py`
— 1295 lines, **15 tests**, eight of them added after the review.

**Through which door.** Eleven of the fifteen go through the **real shipped
command in its own process**: the test spawns
`python -c "from pact_adapters.scoring import main; raise SystemExit(main([...]))"`
with a clean environment, so the path exercised is
`main → _parse → score → _choose → resolve → _cheapest_passing → evaluate →
transport_for →` a real transport `→` a real socket. **Nothing is monkeypatched.**
Where a model has to answer, the test stands up a real threaded HTTP server on a
real port — deliberately, because the defect lives in how `_choose` hands the
search a way to *build* transports, so a test that replaces the transport
replaces the thing under test. The workspace is read through the real loader
(`target/debug/pact show`), and the file skips itself with *"build the CLI first:
cargo build -p pact-cli"* when that binary is absent.

The remaining four call `resolve()` or `evaluate()` directly, for contracts the
command cannot reach: the missing-factory guard, the `strategies={}` case, the
wrong-arity contract, and the defect-propagates case. Two of those need **no
socket at all**, which is deliberate — the arity contract is about the protocol,
not about this caller, and a contract only testable through a live port is a
contract nobody runs.

What the fifteen assert, in one line each:

| test | asserts |
|---|---|
| `…refuses_and_does_not_raise_when_nothing_is_served` | no traceback, non-zero exit, `PORTABILITY`, `none of them answered`, and a `--serving-at` line so the refusal is not a dead end |
| `…names_hosted_models_it_could_not_use` | a hosted row and *"leave the box"* survive into the refusal — the anti-filtering tripwire |
| `…runs_the_authors_cases_against_a_model_that_does_answer` | against a live stub, `none of them answered` and `never answered` are **absent** |
| `…a_row_that_never_answered_is_not_reported_as_one_that_missed_the_bar` | the mixed box: `1 model(s) met the requirements and none reached the bar` **and** the quiet row named separately |
| `…a_model_that_never_answered_is_not_given_a_score` | `not measured` present, `score 0%` **absent** |
| `…the_search_refuses_without_a_way_to_run_anything` | `TypeError` naming `transport_for` and saying why |
| `…a_caller_who_asked_for_no_strategies_is_not_told_the_box_is_silent` | a factory that **raises if called**, proving no socket was opened |
| `…a_teammate_the_agent_asks_is_run_rather_than_parked` | no case comes back `got ''` on the `team:` example |
| `…a_factory_with_the_wrong_arity_is_a_defect_and_not_a_model_that_did_not_answer` | the arity, **without a socket** |
| `…a_suite_that_stopped_half_way_publishes_no_score_and_says_how_far_it_got` | results `[]`, *"answered 1 of 6"*, and the sentence the author actually reads |
| `…a_rule_nothing_could_grade_is_still_reported_when_the_suite_stopped` | the `NOT APPLIED:` sentence survives the discarded score |
| `…a_defect_in_our_own_program_is_never_reported_as_a_machine_that_is_not_serving` | a defect propagates instead of being filed as silence |
| `…something_listening_that_is_not_a_model_runtime_is_named_as_that` | *"what it sent back was not JSON"*, and no `score 0%` |
| `…the_search_never_dials_off_this_machine_before_the_workspace_allows_it` | a real listener on a non-loopback address records **zero** requests |
| `…the_door_binds_the_model_that_passed_when_the_agent_s_own_did_not` | exit **0**, and the runtime spelling — not the catalogue id — was posted |

**The gate file points at it.** `test_what_the_author_wrote_reaches_the_run.py:408`
asserts this file exists by name, so deleting it is visible from the gate rather
than silent. The old source-grep there is gone, and the reason is recorded in that
file verbatim.

---

## The mutation

Twelve numbered mutations plus three ordering-and-spelling mutations are recorded
in the test file's own module docstring, which is where a reader looking at the
test will be. **Each was applied by hand, observed red, reverted, and observed
green again — in the repair session, not in this one.** They were not re-applied
here: two other sessions are editing `resolve.py` and `scoring.py` right now, and
mutating a shared file would race them. What was re-verified here is that the
file is green (below) and that the classifier and signatures the mutations act on
are as recorded.

| mutation | goes red |
|---|---|
| restore the one-argument factory in `scoring._choose` | **7 of 15** |
| that, **plus** the pre-fix catch **plus** the build moved inside the `try` | 6 of 15 — and test 1 goes **green against the bug**; see below |
| make the `except` in `evaluate` unreachable | 4 |
| fold the quiet rows back into the "missed the bar" count | 1 |
| seed `heard = False` instead of `heard = not strategies` | 1 |
| disable the no-results branch in `render` | 1 |
| disable the missing-factory guard | 1 |
| drop `ask_member=` from the run call | 1 (the teammate test) |
| widen the `except` back to swallowing everything | 2 |
| keep the results off a shortened suite | 1 (the stopped-half-way test) |
| drop `unenforced=` from the `Silence` | 1 (the ungraded-rule test) |
| refuse instead of binding what passed | 1 (the binding test) |
| restore `UNDECIDED and` in `render` | 1 (the not-a-runtime test) |
| move the egress refusal to after the search | 1 — with **real requests recorded** at an off-box address |
| classify "not JSON" as "not serving" | 1 |
| ask the runtime by catalogue id instead of served tag | 1 |

**The most important measurement in this table is the second row, and it is a
finding against the first repair rather than a proof of it.** The original test 1
claimed `assert "none of them answered" in said` covered the arity. It does not:
that sentence is reachable through the search whatever the factory's arity, as
long as the resulting error is swallowed. With the pre-fix lambda **and** the
pre-fix catch **and** the transport build moved one line into the `try` — a
refactor the source comment explicitly anticipates — nine of the fifteen tests
pass against the arity bug, test 1 among them. The misleading comment is
corrected, and the arity is now witnessed by a test that needs no socket at all.

Two mutations were **reasoned about and not applied**, and are recorded as such:
changing `break` to `continue` in the case loop (against a dead address every
case raises, so only wall-clock differs), and dropping the empty-suite guard in
`_went_quiet` (no suite in the tree has zero cases, so nothing would bite).

---

## Failure cases

Every state `--choose-model` can now end in, what the author is told, and what
holds it.

| state | reported as | held by |
|---|---|---|
| the factory has the wrong arity | **raises** — a defect, not a silent model | covered by `…a_factory_with_the_wrong_arity_is_a_defect…` (no socket) and by the two socket tests |
| nothing on the other end of `--serving-at` | *none of them answered*, start the runtime | covered by `…refuses_and_does_not_raise_when_nothing_is_served` |
| the runtime has not pulled that row (404) | *not serving a model by that name* | covered by `…a_row_that_never_answered_is_not_reported_as_one_that_missed_the_bar` |
| something is listening and it is not a model runtime | *what it sent back was not JSON* | covered by `…something_listening_that_is_not_a_model_runtime_is_named_as_that` |
| the connection is accepted and no answer arrives | *accepted and no answer arrived*, no false remedy | classifier verified by direct measurement (above); **no end-to-end test** |
| a delegated member goes over the budget its grant allowed | *answered N of M and then stopped*, with the cause | classifier verified by direct measurement; **no end-to-end test** |
| some rows answered, some did not | two counts, two sentences, one remedy each | covered by `…a_row_that_never_answered…` |
| a row answered part of the suite then stopped | *answered 1 of 6 and then stopped* — no score | covered by `…a_suite_that_stopped_half_way…` |
| a rule went ungraded on a suite that stopped | the `NOT APPLIED:` line still printed | covered by `…a_rule_nothing_could_grade_is_still_reported…` |
| a `team:` agent's delegations | run, not parked | covered by `…a_teammate_the_agent_asks_is_run_rather_than_parked` |
| every row answered and none reached the bar | *none reached the bar*, three remedies | covered by `…a_model_that_never_answered_is_not_given_a_score` and the mixed-box test |
| the agent's own model failed and another passed | **binds it**, exit 0, says which and why | covered by `…the_door_binds_the_model_that_passed…` |
| the runtime spells the model differently from the catalogue | asked for by the served tag | covered by the binding test's spelling assertion |
| off-box `--serving-at` under `allow-egress: []` | `scoring/egress-refused`, before a socket opens | covered by `…never_dials_off_this_machine…`, which asserts **zero** recorded requests |
| a defect inside PACT | **raises** | covered by `…a_defect_in_our_own_program…` |
| no catalogue at all | `scoring/no-catalogue` | pre-existing; not re-covered here |
| a hosted row nobody can reach from this box | named in the refusal | covered by `…names_hosted_models_it_could_not_use` |
| a firewalled address that drops packets | five-second connect cap | **UNCOVERED** — the cap is verified to reach the transport, but no test exercises a black-holing address |
| a catalogue with duplicate model names | would be double-counted in the "measured" split | **UNCOVERED** — and whether the loader de-duplicates catalogue rows was not established |
| a suite with zero cases | the empty-suite guard | **UNCOVERED** — no suite in the tree has zero cases |
| `break` vs `continue` in the case loop | identical text, different wall-clock | **UNCOVERED**, and low value |

---

## Verification

Run from `adapters/python`. Both were run in this session, on the tree as it
stands.

```console
$ cd adapters/python && uv run pytest tests/test_the_model_choosing_door_survives_being_opened.py -q
15 passed in 5.41s

$ cd adapters/python && uv run pytest tests/ -q
1621 passed, 5 skipped in 124.46s (0:02:04)
```

The five skips are pre-existing and named by the run: one empty parameter set,
two opt-in live-judge tests behind `PACT_LIVE_JUDGE=1`, one branch that only
applies when DeepEval is absent, one loader-guarded case.

The two suite-wide counting tests — the loader-dependent-file count and the
headline test count — are **green** in that run. They were red for part of this
work; neither red was this issue's alone.

`cargo` was not re-run: this change touches no Rust.

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md:106`, row **A2 — model selection has no
shipped caller**, is the row this corrects. It has been amended (lines 125-134)
rather than rewritten, because the original claim was right about the shape of
the gap and wrong about whether it was closed:

* the row now records that the door **could not be opened for a round** — a
  one-argument factory handed to a two-argument protocol — and that once it was
  opened, five further defects behind it turned out to be live and two of the
  tests holding it did not bite;
* **one sentence of that row was false and is corrected there rather than
  deleted**: when the model the agent names does not pass, the search now **binds
  the cheapest row that does** and says so on the report's `model` line. It
  refuses only when nothing passes at all;
* it points at this document for the measurements.

No new rule id was minted. `_choose` still returns `scoring/no-model-passes` when
nothing passes, and the egress refusal reuses the existing `scoring/egress-refused`
with the same message and the same file-and-line, from one function with two
callers.

**A new register row is warranted and is not yet written** for the class this
issue names — *reachability asserted by grep, not by execution* — with the three
other instances of the same grep still in the tree listed under it.

---

## What remains open

Stated plainly, because a document that overclaims is worse than none.

1. **`RunResult.as_record(asked)` is still advertised with a parameter it does not
   take.** Three shipped diagnostics (`scoring.py:169`, `:1564`, `:1580`) tell the
   author to produce a trace with `RunResult.as_record(asked)`. Measured here:
   `inspect.signature(RunResult.as_record)` → `(self) -> 'dict[str, Any]'`. The
   parameter was removed deliberately as a redaction fix, and the register records
   that removal. This is **A1's exact defect** — a one-versus-two argument
   mismatch on the only path an author would take — relocated from a lambda into
   a help string, where neither a type alias nor a test can see it. It is a
   different door (`--from-trace`) and was not fixed here.

2. **`promote()` — the `--from-trace` write path — is still covered by a grep.**
   The neighbouring assertion in the gate file is the same source-grep this issue
   deleted, over a sixty-line function that writes a YAML file into the author's
   tree. The one execution of that door in the suite passes a missing file and
   returns before reaching the interesting half. Driven by hand it works today;
   it is roughly fifty uncovered lines, not a live crash.

3. **The same grep is still deciding whether a documentation caveat is needed.**
   `test_the_documentation_site_tells_the_truth.py` uses a source-grep to decide
   whether the README's `PORTABILITY:` block needs the caveat *"no shipped command
   produces one"*. It answered "shipped" throughout the entire period the command
   crashed — it actively suppressed a caveat that was true.

4. **`resolve()` defaults the author's `needs:` off the display name.** A library
   caller who passes no agent key gets a lookup against *"Refund Desk"* rather
   than the agent's key — no such key, so an empty `needs:` and a candidate set of
   everything the catalogue holds. Every caller in the product passes the key.
   Not touched here because it is not this door, but it is the same defect class
   as the optional transport factory (queue row D3) and belongs in the register.

5. **A deliberate divergence, recorded so nobody "fixes" it.** The scoring path
   keeps the results of a suite that stopped; the search discards them. The
   argument is at `resolve.py:1239-1252`: a portability figure is a claim about a
   decision procedure over the author's **whole** suite. The two readings of one
   event are genuinely different on purpose, and only one of them now documents
   why.

6. **`OllamaTransport.__init__` is annotated `timeout: float` and now receives a
   structured timeout object.** Runtime-correct — it is only ever handed on to the
   HTTP client, which accepts both — but the annotation is false, and nothing in
   this repository checks annotations.

7. **The five-second connect cap is a capability-affecting number the project's
   own zero-magic audit structurally cannot see.** That audit walks module-level
   upper-case names; a call-site literal and a function-parameter default are
   invisible to it. The number decides whether a model is declared unreachable,
   and therefore whether the flag binds anything at all. It is argued in the
   source and is in no register.
