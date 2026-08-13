# D3 — the transport factory defaulted to `None`, and the resolver reported measurements it never took

**Severity: critical** — not for the crash, which was loud, but for the third defect found while
attacking the fix: a rendered `PORTABILITY:` report claiming models were measured against their bar
after zero cases were run. · **Status: fixed — the filed issue, plus three further defects raised
against that fix by the adversarial review, all repaired and each held by a mutation-verified
test.** · **Register: D3 has no row of its own in `docs/70-PRODUCTION-GAP-REGISTER.md`
(`grep -n "D3" docs/70-PRODUCTION-GAP-REGISTER.md` → no output). The row it corrects is
`A2 — model selection has no shipped caller`, `docs/70-PRODUCTION-GAP-REGISTER.md:106`. See
[Register update](#register-update) for the exact amendment and what is still owed.**

*Queue row 2 of `docs/remediation/QUEUE.md`. The A1 round left `resolve()` with a factory parameter
that defaults to `None`; this round is about that default, what a guard against it is actually
worth, and the larger defect the guard was mistakenly credited with closing.*

**On this document's filename.** The workflow asked for `undefined-undefined.md`. That is a
templating failure, not a name: the queue row reads `| 2 | D3 | transport-factory-defaulted-to-none
| … |`, and the file is named for the row so that `QUEUE.md`'s Doc column points somewhere a reader
can follow. No file called `undefined-undefined.md` exists in `docs/remediation/`.

Every figure below was produced by running the code as it stands. Where a number is quoted, the
command that produced it is beside it.

---

## What is wrong

Three things, and only the first was the issue as filed.

**1. A caller who omits the factory gets a crash from inside the search, not a refusal at the door.**
`resolve()` decides portability by *running* the author's eval cases. Without a transport factory it
has nothing to run them on. The parameter nonetheless defaulted to `None`, and the failure surfaced
four frames down as `TypeError: 'NoneType' object is not callable` at the line that builds a
transport (`adapters/python/src/pact_adapters/resolve.py:1208`) — a message naming neither `resolve`
nor `transport_for` nor the shape either expects.

**2. The guard written for that checked identity against `None`, so seven other wrong shapes went
straight past it.** Measured through the public `resolve()` against `examples/refund-desk`, with the
one-word guard in place (scratchpad probe, no source edit):

```
None                         -> TypeError: resolve() needs a transport_for(...) | frames=2 | resolve.py:1311
zero-arg lambda              -> TypeError: <lambda>() takes 0 positional arguments but 2 were given | frames=4 | resolve.py:1207
one-arg lambda (A1's defect) -> TypeError: <lambda>() takes 1 positional argument but 2 were given  | frames=4 | resolve.py:1207
three-arg lambda             -> TypeError: <lambda>() missing 1 required positional argument: 'c'   | frames=4 | resolve.py:1207
transport instance           -> TypeError: 'ATransport' object is not callable | frames=4 | resolve.py:1207
a bare string                -> TypeError: 'str' object is not callable        | frames=4 | resolve.py:1207
False                        -> TypeError: 'bool' object is not callable       | frames=4 | resolve.py:1207
0                            -> TypeError: 'int' object is not callable        | frames=4 | resolve.py:1207
```

`False` is the sharpest: falsy, not callable, not `None`, admitted. The one-argument lambda is the
sharpest in a different way — it is sibling issue A1's entire subject, the shape `scoring._choose`
actually shipped.

**3. And the harm the guard was credited with preventing was still live with the guard in place.**
A "fully rendered `NO ALTERNATIVE:` measurement claim off zero model calls" is reachable with a
perfectly valid two-argument factory, through `strategies={}` — an input `resolve()`'s own docstring
declares supported. Measured, guard in place, factory instrumented to record every call:

```
$ uv run python scratchpad/probe1.py          # examples/refund-desk via target/debug/pact show
cases: 6
factory calls: []
results ran: 0
PORTABILITY: FAIL for claude-haiku-4-5  (agent Refund Desk, strategy authored)
  score: not measured (bar 70%)
NO ALTERNATIVE: nothing in the catalogue passed: 5 model(s) met the requirements and none
                reached the bar, and the rest were ruled out before any eval ran — ...
```

Zero transports built, zero cases run, and the author is told five models were measured against
their bar and missed it. The remedy that sentence implies is *edit your eval suite*. Nothing was
scored. This is T7 — *"there is no silent degradation anywhere in the system"*
(`docs/00-THESIS.md:227-231`) — broken by the very function whose refusal message argues that
returning a report off zero runs is dishonest.

The same input also produced a head verdict of `PORTABILITY: FAIL for qwen2.5-vl-7b-instruct
(agent Refund Desk, strategy exhausted)` with `results ran: 0`. Nothing was exhausted and nothing
failed.

---

## Root cause

### 3a. `scored_it = not strategies` recorded a true fact in the wrong place

`_cheapest_passing` walks the catalogue and sorts qualifying rows into two populations: rows that
produced a score (`measured`) and rows that qualified and went silent (`no_score`, which earns the
"start a model runtime" remedy). A round before this one, the flag was seeded `False`, and a caller
passing `strategies={}` made the inner loop run zero times — so every qualifying row fell into
`no_score` and the author was told to start a runtime over a search that opened no socket. The
repair was to seed the flag `not strategies`.

That is a **true statement about those rows** — they did not go silent — **filed under the wrong
one of two available labels**. There were only ever two, and the rows belong to neither. Marking
them *scored* put them in `measured`, and `measured` is what the "met the requirements and none
reached the bar" sentence counts (`resolve.py:1620` in the current file).

The missing concept is a third population: a row nobody **tried**. It is not scored and it is not
silent; it is **unrun**, and its remedy is neither "edit the suite" nor "start a runtime" but
"pass a strategy". Printing it as either of the other two sends the author somewhere that cannot
help — the shape `docs/70-PRODUCTION-GAP-REGISTER.md` already records as C9, and the same shape D13
names for the CLI.

### 3b. `last or Verdict("FAIL", ...)` labelled `"exhausted"`

In `resolve()` itself, `last` holds the verdict of the last strategy tried. With `strategies={}` the
loop never runs and `last` stays `None`, and the fall-through built the report as
`last or Verdict("FAIL", 0.0, bar, [])` with the strategy named `"exhausted"`. `render` was already
honest about the *figure* — it prints `score: not measured` whenever there are no results
(`resolve.py:969-983`) — so what remained false was the outcome word and the strategy name, which
are the first thing a reader sees and the thing a script greps for.

### 1a & 2a. The default, and the comment that licensed the narrow guard

The parameter kept a `None` default because `strategies` sits in front of it. The comment beside the
guard justified that with two claims, both of which fail on measurement:

* *"would break all nine existing call sites, every one of which passes it positionally."*
  Measured by **parsing** the three files that call this function and counting `ast.Call` nodes whose
  callee is the name `resolve` — a grep for the string also matches `Path.resolve()`, `Loop.resolve`
  and prose, which is how the earlier counts went wrong in both directions:

  ```
  $ cd adapters/python && python3 -c '
  import ast, pathlib
  for f in ["tests/test_model_portability.py",
            "tests/test_the_model_choosing_door_survives_being_opened.py",
            "src/pact_adapters/scoring.py"]:
      for n in ast.walk(ast.parse(pathlib.Path(f).read_text())):
          if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "resolve":
              print(f, n.lineno, len(n.args))'
  ```
  → **17** call sites, not nine: **15 positional** (five or more positional arguments), **one that
  omits the argument on purpose** — the guard's own test at
  `test_the_model_choosing_door_survives_being_opened.py:614` — and the one **production** caller,
  `scoring.py:1005`, which passes `transport_for=` **by keyword**. Making the parameter keyword-only
  would break **zero** shipped callers and cost fifteen mechanical edits. Seven of the seventeen
  arrived with this work itself: all seven are in the door test file, which
  `git status --porcelain` still reports as `?? .../test_the_model_choosing_door_survives_being_opened.py`
  — so "existing" was wrong as well as "nine".

  **That corrected count was itself stale for a round, in the same direction.** The comment at
  `resolve.py:1303-1315` read **FOURTEEN** — measured before the two tests this change added had been
  written, so the three call sites they brought were never re-counted. Found by re-measuring while
  writing this document, and corrected at the source line, where the comment now says out loud that a
  number in a comment is a measurement with no test behind it.
* *"It CANNOT see the factory's ARITY … The guard that actually holds the arity is the test."*
  Measured false in three lines. `inspect.signature(f).bind("m", "s")` rejects the exact A1 defect
  and admits every real caller in the tree:

  ```
  shipped closure (2-arg)          -> accepted
  None                             -> REJECTED: not callable
  one-arg lambda (A1)              -> REJECTED: wrong arity (too many positional arguments)
  zero-arg lambda                  -> REJECTED: wrong arity (too many positional arguments)
  three-arg lambda                 -> REJECTED: wrong arity (missing a required argument: 'c')
  transport instance / string /False-> REJECTED: not callable
  *args factory                    -> accepted
  callable object __call__(m,s)    -> accepted
  functools.partial 2->2           -> accepted
  2-arg with defaults              -> accepted
  dict (type, not introspectable)  -> accepted (arity not introspectable)
  ```

  The shipped factory it must admit is `def transport_for(model_name: str, _strategy_name: str)` at
  `adapters/python/src/pact_adapters/scoring.py:1000-1003`.

The type-checker half of that comment was true and is still true —
`grep -n "mypy\|pyright\|\[tool.ruff\]" adapters/python/pyproject.toml pyproject.toml` returns
nothing and `grep -n "mypy\|pyright\|ruff" scripts/test-all.sh` returns nothing — but that is an
argument **for** a runtime check, not against one. `TransportFactory = Callable[[str, str], Any]`
(`resolve.py:1065`) was a declared control nothing enforced, carried alongside a
`# type: ignore[assignment]` addressed to a checker that does not run, and a comment explaining that
the control is not enforced. `docs/25-ARCHITECTURE-DECISIONS.md:227` — *"Under T7 an unenforceable
declared control is worse than an absent one, because the author stops looking"* — and AD-41 at
`:225`, whose remedy is deletion, and VAL-10 at `docs/20-ARCHITECTURE-DRAFT.md:1458` —
*"A gate that silently never fires is worse than an absent one"* — between them foreclose exactly
the option that had been taken: keep the unenforced annotation **and** narrate the gap.

---

## Why nothing caught it

**The guard's test witnessed the guard's presence, not its consequence.** It used the document
`{"agents": {"a": {"instructions": "answer", "model": "m"}}}` and asked for `"m"`. Measured with the
guard deleted, that scenario returns a completely honest report:

```
SHIPPED-TEST SCENARIO, GUARD OFF -> PortabilityReport FAIL
PORTABILITY: FAIL for m  (agent a, strategy authored)
  score: not measured (bar 90%)
  'm' is not in the catalogue
```

The early return for a model that is not in the catalogue fires **before** anything touches the
`None`. So the only red a mutation could produce was `Failed: DID NOT RAISE TypeError` — a gate
proven present rather than proven necessary.

**The `strategies={}` test asserted only absences.** It checked that `"never answered"` and
`"none of them answered"` were absent — the previous round's defect — and never asserted against the
*positive* claim that models were measured. Both of its assertions pass on a report that says five
models met the bar and missed it.

**The guard is dead code with respect to every shipped command**, which is why a seam test is the
only door onto it that exists. `grep -rn "resolve(" adapters/python/src/` finds exactly one
production call to this resolver — `scoring.py:1005`, behind `--choose-model` — and it passes a
two-argument closure by keyword, so it can never reach the refusal. Every other hit is
`Path.resolve`, `Loop.resolve`, `ContextPolicy.resolve` or prose. That fact was not written down
anywhere, so a future reader would either delete the seam test as a shortcut or trust it as product
coverage. Neither is right.

**And the ordinary forgetful-caller path already raised before the guard existed.** Measured with
the guard deleted and defaults everywhere except the omitted factory:

```
$ resolve(spec, doc, 'qwen2.5-vl-7b-instruct', agent_key='refund-desk')
  File ".../pact_adapters/resolve.py", line 1207, in evaluate
    transport = transport_for(model, strategy_name)
TypeError: 'NoneType' object is not callable
```

Loud, not silent. **The guard's honest justification on that path is "a better error message four
frames earlier", not "prevents a silent wrong answer."** The silent-wrong-answer variant needs
`strategies={}` as well — and that variant survived the guard entirely, which is defect 3 above.

---

## The fix

### 1. The guard checks callability and arity, not identity — `resolve.py:1344-1367`

```python
what = "nothing" if transport_for is None else repr(transport_for)
needed = (
    "resolve() needs a transport_for(model_name, strategy_name) factory: "
    "it decides portability by RUNNING the author's cases, and there is "
    "nothing honest to return without something to run them on"
)
if not callable(transport_for):
    raise TypeError(f"{needed} — got {what}, which is not callable")
try:
    shape: "inspect.Signature | None" = inspect.signature(transport_for)
except (TypeError, ValueError):
    shape = None          # a C builtin whose arity is not introspectable
if shape is not None:
    try:
        shape.bind("model_name", "strategy_name")
    except TypeError as wrong_arity:
        raise TypeError(
            f"{needed} — got {what}, which cannot be called with two "
            f"positional arguments: {wrong_arity}"
        ) from wrong_arity
```

Measured after the change, same eight shapes, same probe:

```
None / transport instance / string / False / 0 -> resolve() needs a transport_for(...) | frames=2 | resolve.py:1351
zero-arg / one-arg / three-arg lambda          -> resolve() needs a transport_for(...) | frames=2 | resolve.py:1364
good two-arg factory                           -> passes the door (fails later in harness, as before)
```

All eight now stop at the door, one frame below the caller, with a sentence naming the parameter and
its shape. A signature that cannot be read at all is **admitted** rather than refused: refusing on
"I could not look" is a gate firing on the wrong evidence, and it would close the door on callers
that are fine.

### 2. `TransportFactory | None`, and the `# type: ignore` deleted — `resolve.py:1281`

The annotation now states what the parameter can actually hold, so the directive suppressing a
checker this tree does not run is gone. AD-41's remedy applied to the half of the control that could
not be enforced; the half that could is now enforced above, so `TransportFactory` stays and is no
longer decorative.

### 3. A row nobody tried is UNRUN, and says so — `resolve.py:1563`, `resolve.py:1605-1617`

`scored_it` is seeded `False` again, and the third population gets its own branch before either of
the other two sentences:

```python
if not strategies:
    head = (
        f"nothing was measured: {len(tried)} model(s) met the requirements "
        f"and no strategy was supplied, so not one of them was run"
    )
    if ruled_out:
        head += f". The rest were ruled out before any eval ran — {reasons}"
    return Alternative(sentence=f"{head}.{fix}")
```

The previous round's defect does not come back: with zero strategies the inner loop leaves
`why_not` as `None`, and the guard on the `no_score` assignment is `if not scored_it and why_not is
not None`, so nothing is filed as silent either.

### 4. `UNDECIDED` rather than `FAIL`/`"exhausted"` when the loop never ran — `resolve.py:1427-1436`

```python
if last is None:
    report = PortabilityReport(
        spec.name, requested, baseline,
        Verdict("UNDECIDED", 0.0, bar, [],
                f"no strategy was supplied, so {requested} was never run"),
        "none supplied",
    )
else:
    report = PortabilityReport(spec.name, requested, baseline, last, "exhausted")
```

`UNDECIDED` is the outcome this module already returns for "no score could be taken"
(`resolve.py:1252`).

Measured after 3 and 4, same probe:

```
==================== ruled-out row, agent_key
factory calls: [] | results: 0 | outcome: FAIL
  claude-haiku-4-5 thinks at the 'steady' rung and this needs at least 'careful'
NO ALTERNATIVE: nothing was measured: 1 model(s) met the requirements and no strategy was
                supplied, so not one of them was run. The rest were ruled out ...
==================== QUALIFYING row, agent_key
factory calls: [] | results: 0 | outcome: UNDECIDED
PORTABILITY: UNDECIDED for qwen2.5-vl-7b-instruct  (agent Refund Desk, strategy none supplied)
  score: not measured (bar 70%)
  no strategy was supplied, so qwen2.5-vl-7b-instruct was never run
```

### 5. The README stops saying the resolver has no shipped caller — `README.md:157-166`

`A2` is closed (`docs/70-PRODUCTION-GAP-REGISTER.md:106` — *"model selection has no shipped caller ·
CLOSED"*), `scoring.py:87` imports `resolve`, `scoring.py:1005` calls it, and
`scoring.py:1633` declares `FLAGS: tuple[str, ...] = ("--choose-model",)` with help text at
`scoring.py:155-165`. The paragraph now says so and names the caller. This was pre-existing, not
caused by D3 — but D3 is the change that rewrote twenty-one lines of commentary about `resolve()`'s
callers and left the front page asserting the opposite.

---

## Alternatives rejected

**Make `transport_for` required, or keyword-only.** The measurement that killed the original comment
(seventeen sites, the one production caller passing by keyword) also says this is cheap: fifteen
mechanical edits in two test files, zero shipped callers broken. It was reopened on that evidence
and **declined**, for one reason: a required parameter buys Python's stock `TypeError: resolve()
missing 1 required keyword-only argument: 'transport_for'` and **loses the authored sentence**,
which is the one that says *why* a factory is needed. D13 — a refusal is a sentence, not a stack —
applies to a library door as much as to the CLI. The defect class is closed by the check, which
covers omission, non-callability and wrong arity together; parameter ordering would have closed only
omission and would still have needed the check for the other two. The corrected reasoning is written
at `resolve.py:1303-1343` so the next reader inherits the measurement rather than the folklore.

**Delete `TransportFactory` and the annotation entirely (AD-41's literal remedy).** AD-41 forecloses
*keeping an unenforced control plus a comment explaining that it is unenforced*. Enforcing it is the
other way out of that, and it is strictly better: the annotation now describes something the code
actually checks.

**Reject a factory whose signature cannot be introspected.** Refused. `inspect.signature` raises for
some C builtins; refusing on that would turn the guard into a closed door for callers that are fine.
The `except (TypeError, ValueError): shape = None` branch admits them deliberately, and the reason is
at the source line.

**Fix the `strategies={}` sentence by special-casing the string rather than the population.**
Refused. The count in that sentence comes from `measured`, and `measured` is derived from `tried`
minus `no_score`. Leaving an unrun row inside `measured` and rewording the sentence would leave the
next sentence built on that set wrong too. The third population is the real missing concept.

---

## Blast radius

* **`resolve()`'s door** — every caller now goes through two checks instead of one. Verified that
  none of the seventeen call sites is refused: the whole adapter suite runs green, and the five
  admitted shapes (two-argument closure, `*args` forwarder, callable object, defaults, `partial`)
  are asserted positively in the new door test.
* **`scoring._choose` / `--choose-model`** — unaffected. Its closure is two positional parameters
  (`scoring.py:1000-1003`) and it passes the check; it also always passes non-empty strategies, so
  neither the unrun branch nor the `UNDECIDED` branch is reachable from the CLI.
* **`test_a_factory_with_the_wrong_arity_is_a_defect_and_not_a_model_that_did_not_answer`
  (`test_the_model_choosing_door_survives_being_opened.py:975`)** — this is the one place the widened
  guard *displaced* an existing test. It handed a bare one-argument factory to `resolve()` to prove
  that `evaluate` builds the transport outside its `try` and that `_why_it_stopped` re-raises a
  `TypeError` instead of filing it as "the model did not answer". The door now refuses that factory
  before `evaluate` is reached, which would have silently turned it into a second test of the door.
  It was rewritten to go through a `*args` forwarder — the shape `inspect.signature` cannot see
  through, and the ordinary shape of a decorator or forwarding wrapper — so it still exercises
  `evaluate`. A new assertion (`"resolve() needs a transport_for" not in said`) fails if the door
  ever starts refusing `*args` and quietly takes the test over again.
* **Report rendering** — `PortabilityReport.render` was not touched. It already printed
  `score: not measured` for any verdict with no results (`resolve.py:969-983`); the change is to the
  outcome word, the strategy name and the recommendation sentence beside it.
* **The `no_score` / "start a model runtime" sentence** — unchanged, and the tests that hold it
  (`:466`, `:536`, `:1063`, `:1255`) still pass. The unrun branch returns before the
  `measured`/`no_score` split is consulted, so no existing sentence changed shape.
* **The headline test count** — adding two tests moved the number the front page quotes, and
  `test_the_headline_test_count_is_the_count.py` failed on it, which is that test doing its job.
  Recomputed from the session rather than guessed (`request.session.items`, which counts skips too)
  and from `crates/` (`888`): **2516 = 888 Rust + 1628 adapter**, written in both README places and
  in the two site pages that repeat it (`site-docs/index.md:50`,
  `site-docs/status/verified.md:16`) so a reader does not get whichever they looked at first.

---

## The test

Four tests, all in
`adapters/python/tests/test_the_model_choosing_door_survives_being_opened.py`, plus one in
`adapters/python/tests/test_the_documentation_site_tells_the_truth.py`. Each is stated below with
**the mutation that turns it red immediately beneath it**, because a test named apart from its
mutation is a claim without its check; [The mutation](#the-mutation) collects them in one table.

**THROUGH WHICH DOOR.** The four door tests are **seam** tests: they import
`pact_adapters.resolve.resolve` and call it directly. That is not a shortcut and it is not a choice
between doors — it is the only door there is. `--choose-model` cannot reach the refusal, because the
one production caller (`scoring.py:1005`) always passes the two-argument closure built at
`scoring.py:1000-1003`. The subprocess door in the same file (`open_the_door`, which runs
`scoring.main` against `target/debug/pact` and `examples/refund-desk`) covers the neighbouring A1
arity defect, not this one. Every mutation below was applied to the real file, run, and reverted; the
red is quoted from the run.

**`test_the_search_refuses_without_a_way_to_run_anything` (:579)** — rewritten so its scenario needs
the factory. It now loads `examples/refund-desk` through `target/debug/pact show` and asks for
`qwen2.5-vl-7b-instruct`, the one row this workspace serves, so the search walks past the
not-in-the-catalogue early return into the code that calls the factory. Its docstring records,
measured, that `scoring.py:1005` is the only production caller and always passes a closure — so this
guard protects library and embedder callers only and cannot be reached through `--choose-model`.

> MUTATION: delete the `if not callable(transport_for): raise` block.
> ```
> E       AssertionError: 'NoneType' object is not callable
> E       assert 'transport_for' in "'NoneType' object is not callable"
> FAILED ...::test_the_search_refuses_without_a_way_to_run_anything
> 2 failed, 15 passed
> ```
> The red is now the harm — the unnamed crash from inside the search — where before it was
> `Failed: DID NOT RAISE TypeError`.

**`test_the_door_refuses_a_factory_it_cannot_call_with_two_arguments` (:627)** — new. Six wrong
shapes refused (zero-, one- and three-argument factories, a transport instance, a bare string,
`False`), five good shapes admitted (two-argument closure, `*args` forwarder, callable object,
defaults, `functools.partial`). The admitted half is not decoration: a guard that rejects good
callers is worse than none.

> MUTATION: narrow the guard back to `if transport_for is None:` and disable the arity check.
> ```
> E   AssertionError: a zero-argument factory reached the search and crashed there instead of being
>     refused at the door, so the author reads a message that names neither the parameter nor its shape:
> E     ...<lambda>() takes 0 positional arguments but 2 were given
> 1 failed, 16 passed
> ```

**`test_a_caller_who_asked_for_no_strategies_is_not_told_the_box_is_silent` (:714)** — extended with
the assertion it never had, plus two preconditions that make the test fail loudly rather than
vacuously if the fixture drifts: that catalogue rows actually qualified (otherwise the search returns
"nothing in the catalogue meets what this agent needs" and every assertion passes for the wrong
reason), and that zero results were produced.

> MUTATION: restore `scored_it = not strategies` and delete the `if not strategies:` branch.
> ```
> E   AssertionError: zero transports were built and zero cases ran, and the author is being told
>     models were measured against their bar and missed it — a measurement claim about a search that
>     took no measurement, and it sends them to edit a suite that was never scored:
> E     nothing in the catalogue passed: 5 model(s) met the requirements and none reached the bar, ...
> 1 failed, 16 passed
> ```

**`test_a_row_nothing_was_run_against_is_not_reported_as_having_failed` (:812)** — new; holds the
head verdict where the test above holds the recommendation.

> MUTATION: restore `last or Verdict("FAIL", 0.0, bar, [])` with `"exhausted"`.
> ```
> E   AssertionError: nothing was run against qwen2.5-vl-7b-instruct and it is being reported as
>     FAIL — a verdict about a run that did not happen:
> E     PORTABILITY: FAIL for qwen2.5-vl-7b-instruct  (agent Refund Desk, strategy exhausted)
> E   assert 'FAIL' == 'UNDECIDED'
> 1 failed, 16 passed
> ```

**`test_output_the_readme_shows_is_attributed_to_something_that_can_produce_it`
(`test_the_documentation_site_tells_the_truth.py:220`)** — made bidirectional. It computed
`shipped` and only asserted `if not shipped:`; `shipped` became `True` when `--choose-model` landed,
at which point its only assertion became unreachable and the README went on saying the opposite with
a green suite.

> MUTATION, in two parts, because one alone proves nothing:
> * stale README paragraph restored **with** the new `else:` present → red:
>   `AssertionError: scoring.py calls resolve() — measured in this test — and the README still says
>   'no shipped command' beside the portability block.`
> * same stale README **with** the `else:` deleted → `18 passed`. That is the measurement showing the
>   old test was dead code, not merely quiet.

---

## The mutation

Five mutations, one per test above, collected. **Every one was performed** — applied to the real
file, the suite run, the red read off the run, then reverted with the file's md5 checked back against
the pre-mutation copy. None of these was reasoned about rather than executed.

| # | The exact edit | Test that goes red | The red |
|---|---|---|---|
| 1 | delete the `if not callable(transport_for): raise TypeError(...)` block (`resolve.py:1350-1351`) | `test_the_search_refuses_without_a_way_to_run_anything` | `assert 'transport_for' in "'NoneType' object is not callable"` |
| 2 | narrow the guard back to `if transport_for is None:` and disable the `inspect.signature` arity check | `test_the_door_refuses_a_factory_it_cannot_call_with_two_arguments` | `a zero-argument factory reached the search and crashed there … <lambda>() takes 0 positional arguments but 2 were given` |
| 3 | restore `scored_it = not strategies` (`resolve.py:1563`) and delete the `if not strategies:` branch (`:1605-1617`) | `test_a_caller_who_asked_for_no_strategies_is_not_told_the_box_is_silent` | `… being told models were measured against their bar and missed it … 5 model(s) met the requirements and none reached the bar` |
| 4 | restore `last or Verdict("FAIL", 0.0, bar, [])` with the strategy named `"exhausted"` (`resolve.py:1427-1436`) | `test_a_row_nothing_was_run_against_is_not_reported_as_having_failed` | `assert 'FAIL' == 'UNDECIDED'` |
| 5a | restore the stale README paragraph **with** the new `else:` present | `test_output_the_readme_shows_is_attributed_to_something_that_can_produce_it` | `README still says 'no shipped command' beside the portability block` |
| 5b | same stale README **with** the `else:` deleted | *(nothing)* | `18 passed` — the measurement proving the old one-directional test was dead code, not merely quiet |

Row 5b is the one that matters most and is the easiest to skip: mutating the *subject* shows a test
fires, but only mutating the *test* as well shows the previous version could not have.

**One mutation was NOT re-performed in this documenting session.** The five above were run when the
fix landed. This session re-ran the holding tests green (`17 passed`, `75 passed`) and re-read every
cited source line, but did not re-mutate a tree that another session is editing at the same time.
That is a weaker check than a fresh red, and it is stated here rather than implied away.

---

## Failure cases

| Input to `resolve()` | Before | After |
|---|---|---|
| factory omitted, default `strategies` | `TypeError: 'NoneType' object is not callable`, 4 frames down, names nothing | authored sentence at the door, 1 frame below the caller |
| `transport_for=None` explicitly | authored sentence | authored sentence (unchanged) |
| `transport_for=False` / `0` / `""` / a transport instance | `TypeError: 'bool' object is not callable`, 4 frames down | authored sentence, names what was passed |
| one-argument factory (A1's shape) | `<lambda>() takes 1 positional argument but 2 were given`, 4 frames down | authored sentence naming the arity, at the door |
| zero- or three-argument factory | same, 4 frames down | authored sentence naming the arity |
| `*args` forwarder wrapping a one-arg factory | `TypeError` from `evaluate` | unchanged — the door cannot see through `*args`, and `evaluate`'s re-raise is what holds it (test at :975) |
| a C builtin whose signature cannot be read | admitted | admitted, deliberately |
| valid factory, `strategies={}`, requested row ruled out by `needs:` | `"5 model(s) met the requirements and none reached the bar"` off 0 runs | `"nothing was measured: 5 model(s) met the requirements and no strategy was supplied, so not one of them was run"` |
| valid factory, `strategies={}`, requested row qualifies | `PORTABILITY: FAIL … strategy exhausted` off 0 runs | `PORTABILITY: UNDECIDED … strategy none supplied`, with `no strategy was supplied, so … was never run` |
| valid factory, `strategies={}`, nothing qualifies | `"nothing in the catalogue meets what this agent needs"` | unchanged |
| valid factory, non-empty strategies, some rows silent | mixed sentence, counted separately | unchanged |
| `--choose-model` (the only shipped path) | works | unchanged; none of the new branches is reachable from it |

---

## Verification

Scoped, then the gate once, because source changed.

```
$ cd adapters/python && uv run pytest tests/test_the_model_choosing_door_survives_being_opened.py -q -p no:randomly
17 passed in 5.69s

$ cd adapters/python && uv run pytest tests/test_the_documentation_site_tells_the_truth.py \
    tests/test_model_portability.py tests/test_the_model_choosing_door_survives_being_opened.py \
    tests/test_portability.py -q -p no:randomly
75 passed in 8.46s

$ cd adapters/python && uv run pytest tests/ -q
1623 passed, 5 skipped in 124.52s (0:02:04)

$ cargo clippy --all-targets -- -D warnings
Finished `dev` profile [unoptimized + debuginfo] target(s)
```

No Rust source is touched by this issue, so `cargo test --workspace` was not re-run; `crates/` is
unchanged by it and clippy over `--all-targets` is clean. What makes the revert check bite is
watching the scoped test go red without the fix, and every mutation above was run against the real
file and reverted, with the resulting md5 checked back against the pre-mutation copy.

**Re-measured while writing this document**, against the tree as it now stands, because a document
that repeats an earlier session's numbers is doing the thing this project exists to stop:

```
$ cd adapters/python && uv run pytest tests/test_the_model_choosing_door_survives_being_opened.py -q -p no:randomly
17 passed in 5.92s

$ cd adapters/python && uv run pytest tests/test_the_model_choosing_door_survives_being_opened.py \
    tests/test_model_portability.py tests/test_the_documentation_site_tells_the_truth.py \
    tests/test_portability.py -q -p no:randomly
75 passed in 8.58s
```

That second run is after the one source edit this documenting session made — the corrected call-site
count in the comment at `resolve.py:1303-1319`, which is comment text only and changes no behaviour.

**The full adapter suite is currently RED on one test, and it is not this issue's.** Stated rather
than hidden:

```
$ cd adapters/python && uv run pytest tests/ -q
FAILED tests/test_the_headline_test_count_is_the_count.py::test_the_headline_test_count_on_the_front_page_is_the_number_the_suites_run
1 failed, 1633 passed, 5 skipped in 124.72s

$ cd adapters/python && uv run pytest tests/ -q          # same command, ~8 minutes later
1 failed, 1661 passed, 5 skipped in 124.55s
```

The collected count moved by **28** between two runs of the same command with no edit of mine in
between: another session is adding tests to this tree while this document is being written. That test
compares `README.md`'s headline against `request.session.items` for the current session, so it is
doing exactly its job and its red belongs to whoever is mid-change. This session added **no test** and
created or edited **no test file**; its only source edit is the block of comment lines at
`resolve.py:1303-1319`. So the README figures were left alone rather than raced. `2516 = 888 + 1628`
was correct when the D3 work landed and is what all four places still say; whoever finishes the
in-flight change owns re-taking it.
The five landed source changes were re-read at their cited lines and all five are present:
`if not callable(transport_for)` at `resolve.py:1350`, `shape.bind("model_name", "strategy_name")` at
`:1362`, `transport_for: "TransportFactory | None" = None` at `:1281`, `scored_it = False` at `:1563`
with the unrun branch at `:1605-1617`, and the `if last is None:` / `"none supplied"` branch at
`:1427-1436`. The headline counts the change moved are still consistent across all four places that
carry them (`README.md:73`, `README.md:79`, `site-docs/index.md:50`,
`site-docs/status/verified.md:15-16` → `2516 = 888 + 1628`).

---

## Register update

**The row this corrects: `A2 — model selection has no shipped caller`,
`docs/70-PRODUCTION-GAP-REGISTER.md:106`.** It is already marked `~~critical~~ **CLOSED**` and
already carries an `**Amended.**` paragraph from the A1 round (lines 125-134) recording that the door
could not be opened for a round. D3 adds two facts that paragraph does not contain, and they belong
on that row because they are facts about the same door:

* the search could render a `PORTABILITY:` report claiming catalogue rows *"met the requirements and
  none reached the bar"* after building zero transports and running zero cases — a measurement claim
  over a search that took no measurement;
* the factory the door demands is now checked for **callability and arity**, not merely against
  `None`, so the one-argument factory that was A1's entire subject is refused at the door rather than
  four frames inside the search.

**Applied**, as a new `**Amended again (queue row D3).**` paragraph at the end of that row
(`docs/70-PRODUCTION-GAP-REGISTER.md`, after the `USAGE` paragraph that closes the A1 amendment),
pointing at this document. Nothing already on the row was reworded or deleted — the row is shared
with other sessions' work, and an amendment that rewrites what it found is indistinguishable from an
amendment that loses it.

**A row D3 still does not have, and is owed.** `grep -n "D3" docs/70-PRODUCTION-GAP-REGISTER.md`
returns nothing. D3 exists as an ID only in `docs/remediation/QUEUE.md:20` and in two source
comments. The class it names — *a collaborator the function cannot honestly work without is given a
permissive default, so omitting it yields a plausible-looking answer instead of a refusal* — has two
further live instances measured in this same function and **neither is fixed**; both are listed under
[What remains open](#what-remains-open). Minting a new class row is a change to a document three
other sessions are editing concurrently, so it is named here and not written there.

**What was written instead, and is already in place:** two rows in `docs/remediation/REGISTER.md`,
at `:116` and `:117` — one for the door refusing a factory it cannot call with two arguments, one for
"a model nothing was run against is never reported as having been measured against the bar" — each
naming the test that holds it and pointing at this document for the argument.

**No new rule id was minted, and none is owed.** The refusal is a `TypeError` from a library door, not
a `Problem` with a rule id. No author can reach it: the only production caller, `scoring.py:1005`,
always passes a two-argument closure built three lines above it. D13 — *a refusal is a sentence, not
a stack* — is honoured by the message text rather than by a rule id, and `--choose-model` still
returns `scoring/no-model-passes` when nothing passes.

---

## What remains open

* **The guard cannot be reached from any shipped command**, and that is now stated in the test rather
  than left to be rediscovered. If `--choose-model` ever gains a second caller that builds its
  factory conditionally, this stops being library-only and the docstring at :579 is where to say so.
* **`*args` factories are undecidable at the door** by construction. `evaluate`'s
  outside-the-`try` transport build plus `_why_it_stopped`'s `None` for a `TypeError` is what holds
  them, and the test at :975 is deliberately written to keep exercising that path rather than the
  door.
* **`strategies={}` remains a supported input** rather than a refused one. Refusing it at the door
  was considered and not taken: `resolve()`'s docstring distinguishes "wrote no `variants:`" from
  "passed `{}` deliberately", and a caller who wants the catalogue filtered on `needs:` without
  running anything is asking a coherent question. It now gets a coherent answer instead of a
  fabricated measurement.

### Three instances of D3's own class are still live in this same function. None is fixed.

D3's class is *a collaborator the function cannot honestly work without is given a permissive
default, so omitting it yields a plausible-looking answer instead of a refusal.* The factory was one
instance. Three more sit inside twelve lines of it, all measured today against the tree as it stands,
none repaired by this issue, and none carrying a register row.

**(a) `agent_key: str = ""` — `resolve.py:1285`, consumed at `resolve.py:1391`. UNFIXED, and it
silently widens the search.** `needs = needs_of(document, agent_key or spec.name)`, and `spec.name`
is the *display* name, not the key (`ir.py:479`, `name=_text(a.get("name", agent_key))`). `needs_of`
returns `{}` for a key it cannot find, and an empty `needs` admits every catalogue row. Measured
against the shipped worked example, through `target/debug/pact show`:

```
spec.name = 'Refund Desk' | key = 'refund-desk'
needs_of(key)       = {'capabilities': ['tools','images'], 'context-at-least': '32k', 'reasoning': 'careful', ...}
needs_of(spec.name) = {'capabilities': [],                 'context-at-least': None,  'reasoning': '',        ...}
catalogue rows: 13
admitted WITH the key   : 1 ['qwen2.5-vl-7b-instruct']
admitted WITHOUT the key: 5 ['gpt-oss-20b','llama3.2-1b-instruct','qwen2.5-14b-instruct','qwen2.5-7b-instruct','qwen2.5-vl-7b-instruct']
```

Four rows that cannot handle images and do not reason carefully enough become bindable candidates
because a caller omitted an argument. This fails **worse** than D3 did: D3 crashed, this one
recommends. It is unreachable from the product only because `scoring.py:1005` passes `agent_key=key`.

**(b) `baseline: str = "the hand-authored frontier strategy"` — `resolve.py:1286`. UNFIXED, and it
prints a false provenance line into output the shipped command shows an author.** The field is
declared `baseline: str  # REQUIRED — see module docstring` at `resolve.py:951` and the module
docstring at `:16` gives the reason: *"a report that prints one without naming its baseline is
misleading."* `resolve()` then supplies one by default, and the only production caller never passes
it — `grep -n "baseline" adapters/python/src/pact_adapters/scoring.py` returns two unrelated prose
hits, at `:185` and `:1359`. Measured today, after this issue's own repairs:

```
factory calls: []   results ran: 0
PORTABILITY: UNDECIDED for qwen2.5-vl-7b-instruct  (agent Refund Desk, strategy none supplied)
  measured against: the hand-authored frontier strategy
  score: not measured (bar 70%)
  no strategy was supplied, so qwen2.5-vl-7b-instruct was never run
```

Two adjacent lines of one report, one saying it was measured against a frontier strategy and the next
saying nothing was run at all. No frontier strategy exists in that document and none was executed.
This issue made the contradiction *visible* — the honest `UNDECIDED` line now sits directly beneath
the fabricated attribution — and did not close it.

**(c) `scores: dict[str, float] = None  # type: ignore[assignment]` — `resolve.py:157`. Defused, same
idiom.** Non-optional annotation, `None` default, and a `type: ignore` aimed at the checker this tree
does not run — the exact shape deleted from `transport_for` at `:1281`. Harmless only because its one
reader writes `(self.scores or {})`. A `field(default_factory=dict)` closes it.

None of the three is fixed here, because this issue is the factory and the tree is shared with other
sessions. All three are the same class, all three are measured above, and (b) is the one that reaches
an author's terminal today.
