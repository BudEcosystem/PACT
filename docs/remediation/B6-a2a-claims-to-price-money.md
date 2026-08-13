# B6 — a transport that could count tokens was taken to be able to price them, so a spend cap over somebody else's agent reported itself enforced and metered 0.00 for the life of the workspace

**Severity: high.** `cost-per-request-under:` is the one governance field whose
failure mode is an invoice. The author wrote a spend cap, the report told them it
was enforced, and the meter it was enforced against could not move.

**Status: fixed — and the first fix was wrong in the way that matters most.** It
repaired the INSTANCE (`A2ATransport`) and left the CLASS open, and the class is
the entire reachable surface: nothing in `adapters/python/src/` constructs a
transport, so every transport that ever runs is written by a host or copied from
the out-of-tree exemplar. That exemplar shipped B6 verbatim, live and measured,
*after* the instance fix landed. The second port shipped it too, twice over. The
repair pass fixed the class in both ports, fixed an independent falsehood in a
second report channel found while measuring, corrected a documented event
semantics the code no longer honoured, and filed the default in the audit that
structurally could not see it. Three things are **not** closed and are named
under [What remains open](#what-remains-open).

**Register row it corrects:** `docs/70-PRODUCTION-GAP-REGISTER.md` row **C5**.

---

### How to read the numbers in this document

Every figure below names the command that produced it and was produced **by this
pass, on this machine, against this working tree**, on 2026-08-08 — with exactly
one exception, the cost of the default flip, which is no longer reproducible here
and is labelled where it appears. Where a figure could only be produced against a
broken state — the fix has landed, so the before-picture no longer exists in the
tree — the exact mutation is named, and each was applied to the file, measured,
and restored from a byte-compared backup in the session scratchpad
(`cmp -s` clean, `md5sum` printed).

**Two probes are referenced by name.** `$SCRATCH/probe.py` stands up a real
`http.server.HTTPServer` on `127.0.0.1:0` and drives the shipped `harness.run`
over the shipped `A2ATransport` and over the shipped out-of-tree exemplar;
`$SCRATCH/mutate.sh` applies one named mutation, runs the scoped test file,
restores, and verifies the restore. `$SCRATCH` is the session scratchpad.

**One process failure from the earlier repair pass, disclosed rather than
buried.** Restoring the first mutation, that pass used
`git checkout adapters/python/src/pact_adapters/transports/a2a_transport.py`,
which reverts to `HEAD` and therefore discarded that file's uncommitted
working-tree content. It was reconstructed and verified structurally against the
`.pyc` left by the run immediately before: every code object sat at a constant
`+3` line offset (the restored declaration plus two lines of rewritten comment),
and the `lattice()` docstring and its `connected_tools` key were recovered
verbatim from the marshalled constants. The only content not recovered
byte-for-byte is the `#:` comment block above `prices_money`, which the default
flip required rewriting anyway. No `git` command that discards work was used
after that, and none was used in this pass at all.

**Another session is writing this repository.** `git status --porcelain` lists
60+ modified files this issue never touched. Every mutation below was applied to
a single file for a few seconds and restored; `git diff --stat` over the five
files this issue owns was checked afterwards and matches the pre-mutation state.

---

## What is wrong

`harness.run` asks a transport two questions in two steps, and for a round the
second was answered with the first's answer:

```python
reports_usage = callable(getattr(transport, "usage", None))
prices_money  = bool(getattr(transport, "prices_money", reports_usage))
result.unmetered = spec.limits.unmeterable(reports_usage, prices_money)
```

The two questions are genuinely different. *Can tokens be counted?* is answerable
whenever a call is made. *Can anything put a PRICE on them?* is answerable only if
a catalogue publishes a row. `transports/_metering.py` states the rule in the
imperative:

> **An unpriced row yields `None`, never zero.** … Metering a ceiling at 0.0 USD
> is … a spend cap that can never be reached, under an author who believes they
> capped their spend.

So any transport with a `usage()` and no `prices_money` was taken to price its
calls. `A2ATransport` is bound to an **agent**, not a model — no row in
`models/catalog.yaml` can ever describe it, and its own `usage()` docstring says
the answer is *"Almost always `None`"*.

### The reproduction, at the seam that decides it

`Limits.unmeterable` (`adapters/python/src/pact_adapters/limits.py:346`) is the
whole of the report decision, and it is directly measurable both ways. From
`$SCRATCH/probe.py`, on a spec carrying
`Limits(cost_per_request_under=0.05, cost_currency="USD", tokens_at_most=100_000)`:

```
$ cd adapters/python && uv run python $SCRATCH/probe.py
A2ATransport.prices_money      : False
unmeterable(True,  True )      : ()
unmeterable(True,  False)      : ('cost-per-request-under',)
```

`unmeterable(True, True)` is what the old default produced for `A2ATransport`:
an empty list, which is the report saying *every ceiling you wrote is being
measured*. The verbatim failure the test file records from the broken tree is

```text
    AssertionError: the run told the author their spend cap was enforced
    against an agent nobody can price: ()
    assert 'cost-per-request-under' in ()
     +  where () = RunResult(output='Approved.', ... used=Meter(..., tokens=0,
        money=0.0), ...).unmetered
```

The author is told the cap is enforced; the meter it is enforced against reads
0.00 for the life of the workspace.

### A second falsehood, on a second channel, from the same flag

`_never_reached` (`adapters/python/src/pact_adapters/harness.py:2680`) is the
*"the meter is correct and always zero"* channel: it says a money ceiling is
unreachable because the bound model's catalogue row is priced at nothing, and
D11 (`docs/01-DECISIONS.md:95-107`) makes it hang a recommendation off that
price. It built its model list as

```python
models = [str(getattr(transport, "model", "") or "") or spec.model]
```

which on a transport with no `.model` and a document with no `model:` is `[""]`.
The loop `continue`d past every lookup, `total` stayed at its initialiser `0.0`,
and `Limits.priced_at_nothing(0.0)` (`limits.py:400`) reported every money
ceiling as priced-at-nothing **having asked the catalogue nothing**. The `None`
guard written for exactly this case was inside the loop and never ran.

Measured. With the seam guard removed (mutation 3 below) and the flag forced
`True`, `$SCRATCH/probe.py` prints the sentence the report used to emit:

```
_never_reached(..., True ) : ('agents/<this agent>/limits.yaml:1 — `cost-per-request-under`
 is measured against ``, and the model catalogue publishes that row at 0 USD in and 0 USD
 out. Every call this run makes for itself costs 0.00, so nothing it does on its own can
 reach this ceiling. fix: write `tokens-at-most: 200000` beside it — that is the ceiling
 that still bites when the model is free.',)
_never_reached(..., False) : ()
```

A claim about a row in the author's own tree, for an **empty model name**, that
no lookup produced — and a D11 recommendation whose sizing follows from the
invented price. D11 makes recommending an obligation; a recommendation founded
on a fabricated catalogue row inverts it.

So before the fix an a2a run with a money cap was wrong on **two** channels at
once: silently enforced on `unmetered`, and fabricating a catalogue row on
`never_reached`.

### And the instance fix left the class open in three places

**(1) The out-of-tree exemplar — the one file a third party is told to copy.**
`adapters/out-of-tree/echo_adapter/transport.py` was

```python
def usage(self) -> tuple[int, float]:
    """Tokens and money for the last call. Free, and counted honestly."""
    return (len(self.prefix) // 4, 0.0)
```

with no `prices_money`, and returning `0.0` — the exact value `_metering.py`
forbids. On the tree with the instance fix landed, a real
`asyncio.run(run(spec, EchoTransport(), "hello"))` measured:

```text
declares prices_money: <absent>
usage(): (2, 0.0)
unmetered    : ()
never_reached: ('agents/<this agent>/limits.yaml:1 — … publishes that row at 0 USD in and 0 USD out. …',)
spent        : 0.0
```

That is B6 verbatim, plus the fabricated catalogue claim, in the exemplar. The
class guard could not see it: its population glob was
`adapters/python/src/pact_adapters/transports/*.py` only, while the guard's own
docstring said *"The defect CLASS, not the instance."*

**(2) The second port shipped the mechanism and no transport that used it.**
`grep -rn "pricesMoney" adapters/typescript/src/*.ts` returned the interface
field, two read sites in `harness.ts` and two in `limits.ts` — **zero
assignments**. So the false branch was unreachable by construction and
`cost-per-request-under` could never appear on that port's `unmetered` for any
document. `vercel-transport.ts` hardcoded the money half of `usage()` to `0` and
its own comment claimed this was *"the same honesty every Python transport
keeps"*, which is the opposite of `_metering.py`'s rule. Measured through the
port's own driver on that tree: `unmetered: []`.

**(3) `run-trace.ts`'s `Watching` wrapper dropped the field.** Its constructor
forwarded `name`, `lattice()` and `usage` only, and it is the *only* door the
Python cross-port suite has to that port. Measured at the time: declaring
`pricesMoney = false` on `VercelAITransport` alone left the driver answering
`"unmetered":[]`, **unchanged**. The wrapper's own comment records having made
this exact mistake once already, with `usage`.

### And a sixth honesty channel nobody had counted

`harness.py:1036` emits `session.limit.failed` unconditionally whenever
`RunResult.unmetered` is non-empty, and that address is documented in words at
`docs/20-ARCHITECTURE-DRAFT.md:7069` (and its `20-ARCHITECTURE-R5.md` twin). B6's
fix reworded `RunResult.unmetered`'s contract from *"did not enforce"* to
*"cannot promise to measure"* — precisely so the `unmetered` + `cost-limit` pair
is honest — and left the derived channel five lines below documented under the
old contract. It is subscribable (`watches.py:163` lists it in `EMITTED`,
`spec/schema.yaml`), so it is a durable, author-facing record and not an internal
signal.

Measured on a real HTTP a2a run whose stub bills 5.00 against a 0.05 USD cap
(`$SCRATCH/probe.py`):

```text
halted                         : cost-limit
unmetered                      : ('cost-per-request-under',)
never_reached                  : ()
used.money / used.tokens       : 5.0 / 120
session.limit.failed           : [{'limits': ['cost-per-request-under'], 'transport': 'this transport', 'pinned': '', 'bound': ''}]
```

---

## Root cause

One decision, taken in one line, about a question nobody had separated: **how
much does the harness assume on behalf of a transport that said nothing?**

`getattr(transport, "prices_money", reports_usage)` is a default that GRANTS a
capability claim to every transport that has not thought about it. That is the
population it is worst for. Nothing in `src/` constructs a transport, so the
default lands on exactly the host-written and copied-from-the-exemplar files that
no in-tree declaration reaches — and the person it lies to is the author who
wrote a spend cap and cannot read `harness.py`. D14
(`docs/01-DECISIONS.md:122-128`) names this shape: *"'Expert users write code for
this' is not an acceptable answer for any capability in the core."*

**The class is therefore "an undeclared capability defaulted to granted", not
"one transport forgot a line".** Declaring the attribute on `A2ATransport` fixes
the one file in the repository where the mistake was *already* made and leaves
every file where it will next be made.

The `_never_reached` fabrication has an independent root cause with the same
shape: **`0.0` as an initialiser is indistinguishable from `0.0` as an answer**,
and the boundary that consumes it (`Limits.priced_at_nothing`, `limits.py:400`)
is documented to take "what the catalogue charges", with `None` for unpriced. A
total synthesised from zero lookups is neither, and the type cannot say so.

---

## Why nothing caught it

**1. The five end-to-end tests of `A2ATransport` never wrote a money ceiling.**
Three test files in the suite construct an `A2ATransport`
(`grep -rln "A2ATransport(" adapters/python/tests/ | wc -l` → `3`); before this
issue none of them carried `cost-per-request-under:`. A transport is only wrong
about pricing when somebody asks it about a price.

**2. The repository's own mechanism for this class of default could not see it.**
`adapters/python/tests/test_no_default_decides_a_capability_in_secret.py` states
the property — *"no default decides a capability in secret"* — and its walk,
`_capability_literals()`, inspects `tree.body` (module level only), requires
`target.id.isupper()`, and excludes booleans by name. The B6 default is **inside
a function, lower case, and a boolean**. It failed all three filters. This is not
a gap in the audit's intent; it is a gap in the shape it can reach.

**3. The class guard that was added with the instance fix was scoped to the
population the defect could not reach.** It globbed
`src/pact_adapters/transports/*.py` — the nine files that all already declare —
and not `adapters/out-of-tree/*/transport.py`, which is the one file in the
repository whose stated purpose is to be copied, and which had the defect live.
Only test touching the exemplar was
`adapters/python/tests/test_an_eighth_adapter_needs_no_core_change.py`, whose
spec carries no `limits:` at all.

**4. Nothing scanned the second port for the class**, and the second port's own
`pricesMoney` mechanism existing made a reader grepping the name conclude it was
compliant.

**5. `never_reached` was held by nothing.** Before this pass the B6 test file
quoted `never_reached = ()` inside a docstring as measured output and asserted
nothing about it. A mutation that reintroduced the fabricated sentence at the
caller left the whole suite green.

---

## The fix

**Python core.**

* `adapters/python/src/pact_adapters/harness.py:893` —
  `prices_money = bool(getattr(transport, "prices_money", False))`. Was
  `getattr(..., reports_usage)`. Consumed at `:894` by `Limits.unmeterable` and
  at `:930` by `_never_reached`.
* `adapters/python/src/pact_adapters/learning.py:1043` — the same default, for
  `Learner.priced`, which gates whether `cycle-limits.per-month` is a held
  ceiling. A cycle's `per-month` and the run inside it answering differently is a
  defect of its own.
* `adapters/python/src/pact_adapters/harness.py:2726, :2735` — `_never_reached`
  counts lookups instead of inferring them from `total`. `asked` is incremented
  on each successful `price_of`, and

  ```python
  if not asked:
      return ()  # nothing was looked up, so nothing can be said about a row
  ```

  Fixed at the seam, not at the caller: the `prices_money` short-circuit at
  `:2712` masks this for `A2ATransport` only.

**The two files third parties copy.**

* `adapters/out-of-tree/echo_adapter/transport.py:82` — `prices_money = False`,
  and `usage()` (`:84`) typed `tuple[int, float | None]` returning
  `(tokens, None)` (`:95`). `_meter_usage` already handles a `None` money half,
  so the token count still reaches `tokens-at-most` and nothing is added to the
  money meter.
* `adapters/typescript/src/vercel-transport.ts:81` — `pricesMoney = false`, and
  the comment claiming parity with the Python transports is corrected to say what
  is actually true.

**The wrapper, in the same change.**

* `adapters/typescript/src/run-trace.ts:83, :91-92` — `Watching` declares and
  forwards `pricesMoney`. Without this the transport declaration is invisible to
  every cross-port test in the repository.
* `adapters/typescript/src/run-trace.ts:158` — `capsNothingCanReach` is projected
  as its own trace field. `harness.ts` merges *"no spend can reach this cap"* and
  *"nothing here can price it"* into one `unmetered` array on purpose, and that
  is right for an author (*"cannot promise"* is true of both). It is wrong for
  the cross-port suite: once the transport declared honestly, every money ceiling
  landed on `unmetered` for the second reason and the control assertions in
  `test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py` — *"a real
  figure is not named as an unusable one"* — could no longer see which finding had
  fired, and would have gone green on the port forgetting how to read a figure.
  Those assertions now read the channel they were about, and one is strictly new.
* `adapters/typescript/src/harness.ts:542-543` — the default is `false` there
  too. Two ports answering one author's `cost-per-request-under:` differently is
  the defect the cross-port suite exists to catch.

**The documented event.**

`docs/20-ARCHITECTURE-DRAFT.md:7069` and its `20-ARCHITECTURE-R5.md` twin now
state the address as *"cannot PROMISE to measure"*, with a paragraph naming the
`session.limit.failed` + `halted == 'cost-limit'` pair as the intended report and
explaining why the honesty is in the words rather than in a condition: the event
fires **before the first model call**, so it cannot know how the run ended, and
moving it to the end to find out would throw away the up-front warning that is
the whole reason the address exists.

**The audit that could not see the default.**

`adapters/python/tests/test_no_default_decides_a_capability_in_secret.py` gains a
fourth ledger, `OPTIONAL_ON_THE_TRANSPORT` (`:165`), and a second walk,
`_transport_fallbacks()` (`:292`), which finds every
`getattr(transport, "X", <not None>)` in the package. `None` is excluded and that
is the whole discrimination: a `None` fallback is *"the transport did not say"*,
which every reader in this package turns into a sentence on
`RunResult.unmetered`; anything else is a value the harness invents on the
transport's behalf, and inventing one has to be argued. Four names are filed —
`prices_money`, `unenforced`, `model`, `name` — each saying what the fallback
grants.

**Where the reasoning lives in the code.** Three files carry it and none is the
sole source: `harness.py:840-892` (the default and why `False` is not the
mirror-image lie), `harness.py:137-168` (`RunResult.unmetered`'s *"cannot
promise"* contract and the deliberate `unmetered` + `cost-limit` pair),
`limits.py:346-398` (`unmeterable` naming `A2ATransport` in its own docstring),
and `harness.py:2688-2711` (`_never_reached`'s *"asked and got zero is not never
asked"*).

---

## Alternatives rejected

**(a) Declare `prices_money = False` on `A2ATransport` and stop there.** This is
what landed first, and it is not wrong — it is *insufficient*. Measured: with the
default still `reports_usage`, the shipped exemplar reported
`unmetered: ()` and `spent: 0.0` on a real run. A repair that only the instance's
own declaration keeps true is a repair the next transport does not get, and the
next transport is the entire reachable surface.

**(b) A property computing `self._counted is not None`.** Rejected in the class
comment. The flag is read once at `harness.py:893`, before any `model_call`, so a
property would answer `False` there regardless and then disagree with itself
later — against `Transport.prices_money`'s stated contract (`harness.py:280`),
*"decided once at construction and never changes"*. `False` is also the honest
answer for *every* run: an agent may price one exchange and not the next, and a
ceiling enforceable only when somebody else feels like saying so is not one a run
can promise.

**(c) Drop the money half in `_what_it_cost` so `usage()` never returns a price.**
Then `unmetered` and `halted` could never disagree and the surprising pair
vanishes. Rejected, and the rejection is right: it buys a tidier report by
throwing away a real stop, and it fails the author who most needed the cap — told
at the END of a run that their cap was unmeasurable, having already gone through
it.

**(d) `self.prices_money = can_price(self.model, self.workspace)` in `__init__`,
as the seven model-bound transports do** (`anthropic_transport.py`,
`autogen_transport.py`, `langchain_transport.py`, `langgraph_transport.py`,
`ollama_transport.py`, `openai_agents_transport.py`, `pydantic_ai_transport.py`).
Unavailable here for the reason `runtime = "a2a"` already states: `can_price`
takes a model id and this transport is bound to an agent. A plain class attribute
is the smallest thing that fits the same read.

**(e) Leave the default at `reports_usage` and file the flip as a recommendation.**
This is what the first pass did — parked on register row C5 — on the grounds that
`False` was *"the same lie pointing the other way"*: four suite stand-ins bill a
real money figure from `usage()` and declared nothing, so they would report a cap
as unmeasurable while the meter ticked. **That objection held against
`RunResult.unmetered`'s OLD wording, *"did not enforce"*, and does not hold
against the new one.** A harness that was never told a transport can price
genuinely has no promise to make. The cost of the flip, with nothing else
changed, was `4 failed, 1926 passed, 7 skipped` — all four those stand-ins, which
now declare `prices_money = True`, the line a real host-written transport that
can price writes anyway. **That figure was measured by the repair pass and is not
reproducible on this tree**: the four stand-ins now declare, so flipping the
default back changes nothing. It is the one number in this document this pass did
not produce itself, and it is recorded as an attribution rather than a
measurement. Filing a capability decision in prose also puts it
outside the mechanism built for exactly that (`test_no_default_decides_a_
capability_in_secret.py`), which is the second reason it was the wrong home.

**(f) Fix the fabricated `never_reached` sentence at the caller.** The
`prices_money` short-circuit at `harness.py:2712` already suppresses it for
`A2ATransport`. That is a mask on one caller: measured, the same sentence was
still reachable from the shipped exemplar. Fixed at the seam instead.

---

## Blast radius

**Six channels carry `prices_money`'s answer, and the first analysis counted
five.** Measured on `A2ATransport` with the flag forced both ways
(`$SCRATCH/probe.py`) and on a real HTTP run:

| channel | where | moves? |
|---|---|---|
| `RunResult.unmetered` | `harness.py:894` via `Limits.unmeterable` | **yes** — `()` → `('cost-per-request-under',)` |
| `RunResult.never_reached` | `harness.py:930` via `_never_reached` | **yes** — fabricated sentence → `()` |
| `session.limit.failed` (bus, subscribable by `watches:`) | `harness.py:1036` | **yes — the sixth, uncounted** |
| `Learner.priced` → `cycle-limits.per-month` | `learning.py:1043` | **yes** |
| `RunResult.used.money` (the meter) | `_meter_usage` | no — the flag is a promise about the REPORT |
| `halted` / `stoppedBy` | `Limits.reached` | no — a volunteered figure still trips the ceiling |

The last two rows are what make the deliberate pair possible, and it is measured
above: `halted: cost-limit` **and** `cost-per-request-under` on `unmetered`, on
the same run, with `used.money == 5.0`.

**Unaffected channels, checked rather than assumed:** `unenforced`
(`harness.py`, `NOT_OURS` sentences), `unwatched` (`spec.watches.subscribe`), and
`unretrieved` (knowledge-source route) take no pricing input.

**Digest stability — not affected, categorically.** `pact_doc::digest`
(`crates/pact-doc/src/canonical.rs`) is `sha256(canonical_string(node))` over a
parsed *document*. B6 touches no document, no `spec/schema.yaml` key, no
canonicaliser and no Rust at all: `grep -rn "prices_money\|pricesMoney" crates/
spec/` returns nothing. No authored document's digest moves.

**Four-artifact rule (§7.28) — not triggered.** `prices_money` is a transport
implementation attribute, not an authored key, and nothing changes about which
keys the second port reads or reports. Measured,
`grep -c "prices_money\|pricesMoney"`: `README.md` **0**,
`crates/pact-cli/tests/the_subset_the_second_port_runs.rs` **0**,
`adapters/python/tests/test_the_subset_the_second_port_runs.py` **0**.
`adapters/typescript/src/run-trace.ts` returns **5** — all five are the
`Watching` wrapper forwarding a transport attribute, none is a field the trace
reports, so the subset the two ports agree on is unchanged.

**Population.** Nine in-tree transports, one out-of-tree exemplar, one TypeScript
transport, plus every host-written transport there is — and the last group is
unbounded and is where the default lands.

**Both ports.** The TypeScript port now carries the mechanism *and* a transport
that uses it, *and* the wrapper that lets a test see it. Measured end to end:

```
$ cd adapters/typescript && node --experimental-strip-types src/run-trace.ts \
   '{"name":"Refund Desk","instructions":"Decide.","maxSteps":8,
     "tools":[{"name":"zendesk","description":"read"}],
     "limits":{"cost-per-request-under":"0.05 USD","tokens-at-most":100000}}' \
   '{"turns":[{"text":"done"}]}' 'hello'
unmetered          : ['cost-per-request-under']
capsNothingCanReach: []
halted             : final
```

**Counts.** `cd adapters/python && uv run pytest tests/ -q --collect-only` →
`1944 tests collected`. `README.md:73` and `:79` state
`2858 tests (914 Rust + 1944 adapter)` and are in sync — that figure is held by
`test_the_headline_test_count_is_the_count.py`, which reads `README.md` and
nothing else. Three other artifacts that `scripts/sync-counts.sh` writes in the
same pass are **stale and nothing reads them**: `site-docs/status/verified.md:16`
(`1928`) and `:17` (`2,842`), `site-docs/index.md:50` (`2,842 — 914 Rust, 1928
adapter`), and `docs/90-REVIEW.md:84` (`1928 tests`). See
[What remains open](#what-remains-open).

`scripts/test-all.sh:59`'s hardcoded *"62 test files read the worked example"* is
not affected — the B6 test file reads no worked example, and nothing asserts that
figure (`grep -rn "62 test files" scripts/` → one occurrence, in that script).

---

## The test

**File:** `/home/bud/ditto/agent-inter-op/adapters/python/tests/test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py`
— 800 lines, 13 tests.

```
$ cd adapters/python && uv run pytest tests/test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py -q
13 passed in 2.21s
```

**Through which door.** Nine of the thirteen are real runs. `agent_at` stands up
a real `http.server.HTTPServer` on `127.0.0.1:0` and the a2a tests call
`asyncio.run(run(_capped(), A2ATransport(url), ...))` — the shipped
`harness.run`, the shipped `A2ATransport`, real `httpx` over a real socket. The
exemplar test imports and runs the real `EchoTransport`. The second-port test
shells out to `node --experimental-strip-types src/run-trace.ts`, which is the
path every cross-port test in this repository uses. No seam is monkeypatched and
no transport under test is stubbed; the only stub is the far side of the wire,
which is the counterparty, not the thing under test.

The remaining four are source-text guards, and each says in its own docstring
that it is one and names the effect test that covers the same ground.

| test | line | what it asserts | door |
|---|---|---|---|
| `test_a_spend_cap_over_a_remote_agent_is_reported_as_unheld` | 234 | `"cost-per-request-under" in out.unmetered` on a run whose stub volunteers no `usage` block; `out.spent == 0.0` | real HTTP run |
| `test_the_token_ceiling_is_not_taken_away_with_the_money_one` | 254 | `"tokens-at-most" not in out.unmetered` and `out.used.tokens == 120` while money stays on | real HTTP run |
| `test_a_price_the_agent_volunteers_still_reaches_the_meter` | 279 | `out.spent == 0.004`, `out.halted == "final"` — `prices_money=False` is not a gag on the meter | real HTTP run |
| `test_a_cap_on_unmetered_can_still_be_the_thing_that_stopped_the_run` | 300 | the deliberate pair: `halted == "cost-limit"` AND `cost-per-request-under` on `unmetered`; **plus `never_reached == ()`** and the `session.limit.failed` payload | real HTTP run |
| `test_a_ceiling_over_a_model_nobody_named_claims_nothing_about_a_catalogue` | 386 | `out.never_reached == ()` for a transport that declares `prices_money = True`, counts tokens and names no model, against a spec with no `model:` — the seam, not the caller | real run, transport built in the test |
| `test_a_transport_that_never_said_it_could_price_is_not_taken_to_have` | 443 | the default, as an EFFECT: an undeclared billing transport puts money on `unmetered`, keeps tokens off it, and still meters `0.01` | real run, transport built in the test |
| `test_the_honest_and_inert_stand_in_is_unchanged` | 500 | `mock.ReferenceTransport` still puts both ceilings on `unmetered` | real run |
| `test_the_exemplar_a_third_party_copies_meters_a_spend_cap_honestly` | 519 | `prices_money is False`, `usage()[1] is None`, money on `unmetered`, tokens off it, `never_reached == ()` | real run over the shipped exemplar |
| `test_the_second_port_reports_a_spend_cap_it_cannot_price` | 578 | `"cost-per-request-under" in got["unmetered"]`, `"tokens-at-most"` not | `node run-trace.ts`, subprocess |
| `test_the_wrapper_the_cross_port_suite_runs_through_forwards_every_seam` | 623 | every optional member of the `Transport` interface in `harness.ts` is read off `inner` inside `Watching` | source text, both TS files |
| `test_the_register_states_the_measured_metering_matrix` | 671 | `len(_the_transports()) == 9`, `usage()` on 8, `apply_settings` on 7, and row C5 states both | source text + register |
| `test_every_transport_that_counts_says_whether_it_can_price` | 715 | the class guard: `^\s*(self\.)?prices_money\s*[:=]` over the in-tree nine **plus** `adapters/out-of-tree/*/transport.py`, with the glob asserted non-empty | source text |
| `test_the_second_port_declares_the_same_thing_about_the_same_seam` | 770 | the same class in the second port: `^\s*(this\.)?pricesMoney\s*[:=]` over `adapters/typescript/src/*-transport.ts` | source text |

**Two details worth naming.** The class guard matches an ASSIGNMENT, not a
mention — an earlier draft matched the word and was satisfied by the comment
explaining the bug, which is a guard a paragraph can pass. And `_the_exemplars()`
asserts its glob is non-empty at the call site, because a glob that silently
matches nothing is how a class guard becomes decorative.

**Also changed, and load-bearing:**
`adapters/python/tests/test_no_default_decides_a_capability_in_secret.py` — the
fourth ledger and the companion walk, with `test_the_companion_walk_sees_
something` as its own vacuity guard.

---

## The mutation

**Nine mutations, each applied to the tree by this pass, run, and restored from a
`cmp`-verified backup** (`$SCRATCH/mutate.sh <n>`). Scope in every case:
`cd adapters/python && uv run pytest tests/test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py -q`.
Verbatim results:

| # | mutation | measured result |
|---|---|---|
| 1 | delete `prices_money = False` from `a2a_transport.py:102` | `1 failed, 12 passed` — `test_every_transport_that_counts_says_whether_it_can_price` |
| 2 | `harness.py:930` `_never_reached(spec, transport, prices_money)` → `…, reports_usage)` | **`13 passed`** — see below |
| 3 | delete `if not asked: return ()` from `_never_reached` (`harness.py:2735`) | `1 failed, 12 passed` — `test_a_ceiling_over_a_model_nobody_named_claims_nothing_about_a_catalogue` |
| 4 | mutations 2 **and** 3 together | `3 failed, 10 passed` — `…that_stopped_the_run`, `…claims_nothing_about_a_catalogue`, `…exemplar…meters_a_spend_cap_honestly` |
| 5 | delete `prices_money = False` from `echo_adapter/transport.py:82` | `2 failed, 11 passed` — the class guard and the exemplar's own run |
| 6 | exemplar `usage()` returns `0.0` instead of `None` | `1 failed, 12 passed` — `…exemplar…meters_a_spend_cap_honestly` |
| 7 | delete `pricesMoney = false` from `vercel-transport.ts:81` | `1 failed, 12 passed` — `…second_port_declares_the_same_thing…` |
| 8 | delete the `pricesMoney` forward from `Watching` (`run-trace.ts:91-92`) | `1 failed, 12 passed` — `…wrapper…forwards_every_seam` |
| 9 | delete the `usage` forward from `Watching` instead | `2 failed, 11 passed` — the wrapper guard **and** `…second_port_reports_a_spend_cap_it_cannot_price` |

Restores verified: `RESTORED-OK` printed for each, and `git diff --stat` over the
five owned files afterwards is
`360 insertions(+), 35 deletions(-)` across `harness.py`, `a2a_transport.py`,
`echo_adapter/transport.py`, `run-trace.ts`, `vercel-transport.ts` — the
pre-mutation state. `harness.py` md5 `54fdf64adb3ba605f214e0ec2d403613` before
and after every harness mutation.

**Mutations 1, 2 and 7 are recorded because of what they do NOT do, and that is
the more useful fact.**

*Mutation 1* used to redden four tests in this file; it now reddens one. That is
not a weakening — it is what a class repair looks like. The default now agrees
with the declaration, so deleting the declaration changes no behaviour, and what
holds the line is the class guard rather than the effect. Mutation 7 is the same
story in the other port.

*Mutation 2* is the one an adversarial review found **green on the pre-fix tree**,
while a real run through it emitted the fabricated catalogue sentence. It is
green here for the opposite reason: it reintroduces nothing, because the seam
below no longer produces a sentence to reintroduce. That is the difference
between fixing the caller and fixing the seam, and mutation 4 shows the pair red
together.

**One mutation the seam probe makes visible directly.** With mutation 3 applied,
`$SCRATCH/probe.py` prints `_never_reached(..., True)` as the fabricated sentence
quoted under [What is wrong](#what-is-wrong); restored, it prints `()`.

---

## Failure cases

| # | case | status |
|---|---|---|
| 1 | Remote agent volunteers no usage block at all (the usual case) — `cost-per-request-under` on `unmetered`, `spent == 0.0` | covered-by `test_a_spend_cap_over_a_remote_agent_is_reported_as_unheld` (234), real HTTP run |
| 2 | Remote agent volunteers tokens and no cost — `tokens-at-most` must stay OFF `unmetered` while money stays ON, `used.tokens == 120` | covered-by `test_the_token_ceiling_is_not_taken_away_with_the_money_one` (254) |
| 3 | Remote agent volunteers a cost BELOW the cap — the meter must still charge it | covered-by `test_a_price_the_agent_volunteers_still_reaches_the_meter` (279): `spent == 0.004`, `halted == 'final'` |
| 4 | Remote agent volunteers a cost ABOVE the cap — the deliberate pair: `halted == 'cost-limit'` AND money on `unmetered` | covered-by `test_a_cap_on_unmetered_can_still_be_the_thing_that_stopped_the_run` (300) |
| 5 | `never_reached` must be EMPTY on an a2a run with a money cap | covered-by the same test (300) — this was **UNCOVERED** before this pass and is the finding that mutation 2 exposed |
| 6 | `session.limit.failed` must carry the same list and the same wording as `unmetered` | covered-by the same test (300), which asserts the payload |
| 7 | A transport with `usage()`, no `prices_money` and no `.model` must not have a catalogue claim fabricated for it | covered-by `test_a_ceiling_over_a_model_nobody_named_claims_nothing_about_a_catalogue` (386) — was **UNCOVERED and live** |
| 8 | A transport that bills and declares nothing must not be taken to price | covered-by `test_a_transport_that_never_said_it_could_price_is_not_taken_to_have` (443) — was a prose assertion on the register row |
| 9 | The NEXT in-tree transport ships `usage()` and forgets the declaration | covered-by `test_every_transport_that_counts_says_whether_it_can_price` (715) |
| 10 | The out-of-tree exemplar ships `usage()` and forgets the declaration | covered-by the same guard, population widened, plus `test_the_exemplar_a_third_party_copies_meters_a_spend_cap_honestly` (519) as an effect — was **UNCOVERED and live after the instance fix** |
| 11 | The exemplar returns `0.0` rather than `None` for an unpriced row | covered-by (519), mutation 6 |
| 12 | The second port's transport forgets `pricesMoney` | covered-by `test_the_second_port_declares_the_same_thing_about_the_same_seam` (770) and `test_the_second_port_reports_a_spend_cap_it_cannot_price` (578) — was **UNCOVERED and live** |
| 13 | `run-trace.ts`'s `Watching` drops an optional `Transport` member | covered-by `test_the_wrapper_the_cross_port_suite_runs_through_forwards_every_seam` (623); mutation 9 confirms it would have caught the `usage` omission the wrapper's own comment records |
| 14 | `transports/mock.py` must be unaffected — no `usage()`, both ceilings stay on `unmetered` | covered-by `test_the_honest_and_inert_stand_in_is_unchanged` (500) |
| 15 | A transport is added to or removed from the directory | covered-by `test_the_register_states_the_measured_metering_matrix` (671) |
| 16 | The four suite stand-ins that bill a real figure must declare `prices_money = True` | covered-by the suite itself: the flip reddened exactly those four (`4 failed, 1926 passed, 7 skipped`, measured by the repair pass — see the note in [Alternatives rejected](#alternatives-rejected)) and they now declare |
| 17 | `learning.Learner` scoring through an `A2ATransport` — `Learner.priced` false, so `cycle-limits.per-month` is reported rather than held | **UNCOVERED.** `grep -rln "A2ATransport" tests/ \| xargs grep -ln "Learner"` returns only this file, and `grep -n "Learner"` in it finds three docstring mentions and no construction. The code path is byte-identical to `harness.run`'s (`learning.py:1043`), so this is a coverage gap and not a suspected bug |
| 18 | A capability fallback read off a local NOT named `transport` | **UNCOVERED by construction.** `_transport_fallbacks()` is scoped to the parameter literally named `transport`; its own docstring says so rather than leaving it to be found |
| 19 | `never_reached`'s wording versus a catalogue row whose input and output prices sum to zero | **UNCOVERED.** See [What remains open](#what-remains-open) |
| 20 | Adding tests moves the headline counts | partially covered: `README.md` is held by `test_the_headline_test_count_is_the_count.py` and is in sync at `1944`. Three other artifacts are stale and **nothing reads them** |

---

## What remains open

**1. `never_reached`'s wording is still stronger than its evidence in one case.**
It says the catalogue *"publishes that row at 0 USD in and 0 USD out"* on the
basis of `price_of(name, 1_000_000, 1_000_000) == 0.0`, which is a *total* over
input and output. A row publishing a negative input price and a matching positive
output price would sum to zero and be described wrongly. Measured:
`grep -n "per-mtok: -" models/catalog.yaml` returns nothing, so it is not
reachable from the shipped distribution — but a workspace-local
`models/catalog.yaml`, which `resolve.price_of(workspace=…)` layers over it, is a
route this pass did not check.

**2. Three published test-count artifacts are stale and no test reads them.**
Measured: `uv run pytest tests/ -q --collect-only` → `1944 tests collected`;
`site-docs/status/verified.md:16` says `1928` and `:17` says `2,842`;
`site-docs/index.md:50` says `2,842 — 914 Rust, 1928 adapter`;
`docs/90-REVIEW.md:84` says `1928 tests`. `README.md` is correct at `1944` /
`2858` because one test reads it. `scripts/sync-counts.sh` writes all four in one
pass and has not been re-run. **This pass did not run it**: it requires a full
`cargo test --workspace` for the Rust half and would rewrite four files another
session may be holding. That is shared drift across the whole remediation round
rather than B6's alone, but B6's tests are most of it.

**3. The audit's companion walk is scoped to the parameter literally named
`transport`.** A capability fallback read off a differently-named local is
outside it. Stated in `_transport_fallbacks()`'s own docstring rather than left
to be found.

**4. `Learner` over an `A2ATransport` is not exercised anywhere** (failure case
17). The read is the same one line, so this is a coverage gap, not a known
defect — but it is the channel that decides whether `cycle-limits.per-month` is a
held ceiling, and it is held by nothing of its own.

**Not claimed.** This pass ran the Python port and the TypeScript type-checker,
which is the whole of what this issue touches. No Rust source was changed
(`grep -rn "prices_money\|pricesMoney" crates/ spec/` → nothing), so
`cargo test --workspace` and clippy were not re-run and nothing is claimed about
them.

---

## Verification

```
$ cd adapters/python && uv run pytest tests/ -q
1937 passed, 7 skipped in 138.36s (0:02:18)

$ cd adapters/python && uv run pytest tests/ -q --collect-only | tail -1
1944 tests collected in 2.17s

$ cd adapters/python && uv run pytest tests/test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py -q
13 passed in 2.21s

$ cd adapters/typescript && npx --no-install tsc --noEmit
(no output, exit 0)

$ cd adapters/typescript && node --experimental-strip-types src/run-trace.ts \
    '{"name":"Refund Desk","instructions":"Decide.","maxSteps":8,
      "tools":[{"name":"zendesk","description":"read"}],
      "limits":{"cost-per-request-under":"0.05 USD","tokens-at-most":100000}}' \
    '{"turns":[{"text":"done"}]}' 'hello'
unmetered: ['cost-per-request-under']   capsNothingCanReach: []   halted: final

$ cd adapters/python && uv run python $SCRATCH/probe.py
A2ATransport.prices_money      : False
unmeterable(True,  True )      : ()
unmeterable(True,  False)      : ('cost-per-request-under',)
_never_reached(..., True )     : ()
_never_reached(..., False)     : ()

--- real HTTP a2a run, stub bills 5.00 against a 0.05 USD cap
halted                         : cost-limit
unmetered                      : ('cost-per-request-under',)
never_reached                  : ()
used.money / used.tokens       : 5.0 / 120
session.limit.failed           : [{'limits': ['cost-per-request-under'], 'transport': 'this transport', 'pinned': '', 'bound': ''}]

--- shipped exemplar adapters/out-of-tree/echo_adapter/transport.py
declares prices_money          : False
usage()                        : (2, None)
unmetered                      : ('cost-per-request-under',)
never_reached                  : ()
used.money / used.tokens       : 0.0 / 2
```

Baseline before the repair pass, same first command: `1930 passed, 7 skipped`
(recorded by that pass; this pass measured only the post-fix figure).

**Files this issue owns**, and what changed in each:

```
adapters/python/src/pact_adapters/harness.py                   default -> False; _never_reached counts lookups; comments
adapters/python/src/pact_adapters/learning.py                  the same default
adapters/python/src/pact_adapters/transports/a2a_transport.py  prices_money = False + the comment above it
adapters/out-of-tree/echo_adapter/transport.py                 prices_money = False; usage() -> (tokens, None)
adapters/typescript/src/harness.ts                             default false; interface comment
adapters/typescript/src/vercel-transport.ts                    pricesMoney = false; comment corrected
adapters/typescript/src/run-trace.ts                           Watching forwards pricesMoney; capsNothingCanReach projected
adapters/python/tests/test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py    7 -> 13 tests
adapters/python/tests/test_no_default_decides_a_capability_in_secret.py        fourth ledger + companion walk
adapters/python/tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py  channel-correct assertions; Spending declares
adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py            Spending declares
adapters/python/tests/test_termination.py                                      Costing declares
adapters/python/tests/test_a_months_spend_on_improving_is_held.py              Costing declares
docs/20-ARCHITECTURE-DRAFT.md, docs/20-ARCHITECTURE-R5.md                      session.limit.failed semantics
docs/70-PRODUCTION-GAP-REGISTER.md                                             row C5
README.md                                                                      test count
```

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md` row **C5** (line 850) carries the change and
is held by two tests in this issue's file
(`test_the_register_states_the_measured_metering_matrix` and the C5 assertions in
`test_a_transport_that_never_said_it_could_price_is_not_taken_to_have`). Verified
present in the row as it now stands:

* the metering matrix restated with `prices_money` at **8 of 9** and
  `apply_settings` at **7 of 9** — both asserted against the tree, not described;
* the B6 paragraph: *"`a2a_transport.py` had `usage()` and no `prices_money` …
  a spend cap over a remote agent was therefore reported as **enforced** and
  metered 0.00 for the life of the workspace"*, and the deliberate
  `unmetered` + `cost-limit` pair named as the intended report;
* the class statement: the guard's population is *"the in-tree nine **plus**
  `adapters/out-of-tree/*/transport.py` plus the second port's
  `adapters/typescript/src/*-transport.ts`"*;
* the second, independent defect recorded — `_never_reached` fabricating a
  catalogue row for an empty model name, *"fixed at the seam rather than at the
  caller"*;
* **still open (i)** — `thinking` at 1 of 9, unrelated to this issue and the
  row's largest remaining hole;
* **(ii) marked CLOSED** — the `prices_money` default is now `False`, with the
  measured cost of the flip (4 failures out of 1930) and the four stand-ins that
  now declare, and the note that the seam is filed in
  `tests/test_no_default_decides_a_capability_in_secret.py` under
  `OPTIONAL_ON_THE_TRANSPORT`;
* **still open (iii)** — `tool-choice:` naming a tool no stage offers, unrelated
  to this issue.

Nothing further is owed to the register by B6. What is owed elsewhere is
`scripts/sync-counts.sh`, for the three stale count artifacts named under
[What remains open](#what-remains-open).
