# B8 — `Limits.from_mapping` parsed `NaN USD` to `nan` in both ports, so a spec built in code reported itself fully metered under no cap at all

**Severity: high.** `cost-per-request-under:` is the one governance line whose
failure mode is an invoice, and this failure was silent in both directions at
once: the run spent, and the report said every ceiling had been held.

**Status: fixed — and the first fix was wrong in four ways that mattered, was
attacked, and was repaired.** It put the guard on the value rather than on the
reader, which was right, and then stored the RECORD of what it had dropped as a
tuple of field names anybody could hand in, guarded one of the two float
ceilings in the dataclass, destroyed the author's currency on the way past, and
handed the third reader of the same authored line the drop without the report.
The second port's half was held by a projection computed inside the test driver
itself. All of that is now closed, and a third round — closing the same forgery
one level down, by making the record private — landed from a concurrent session
while this document was being written and was re-measured here. Five things
remain open and every one of them is named in
[What remains open](#what-remains-open): two are other issues (B10, G2), one is a
stale published count, and two are this issue's own residue.

**Register row it corrects:** `docs/70-PRODUCTION-GAP-REGISTER.md` row **C9**,
shared with B3 — B3 put the floor under the AUTHORED door, B8 is the run-time
half for the door no checker sees.

---

### How the numbers in this document were taken

Every figure below was produced by this pass, on this machine, against this
working tree, on 2026-08-08, and the command that produced it is named beside
it. Nothing is carried over from an earlier transcript: where a previous record
disagreed with the measurement, the measurement won and the disagreement is
recorded (see [The mutation](#the-mutation)).

The before-picture no longer exists in the tree, so it was reproduced two ways,
both of which are honest about what they are:

* by `object.__setattr__` on a frozen `Limits` AFTER construction, which puts the
  pre-fix value into the object without editing a single line of source;
* by applying one named edit to one line, measuring, and restoring the file from
  the bytes read before the edit, with `sha256sum` compared afterwards. The
  runner is `$SCRATCH/mutate.py`; it refuses to run if its anchor text does not
  appear exactly once, and it prints `restored=ok` only when the digest matches.

**Another session is writing this repository while this document is being
written, and it is writing THESE files.** `git status --porcelain` lists ~90
modified files this issue never touched. Measured directly: `limits.py` was
`68400667226c…` for the first mutation batch, `bb62882c6de8…` during the second,
back to `68400667226c…` minutes later, and `151c9e1d1b9a…` by the end — the last
of those a further hardening of this very fix, described in
[The fix](#the-fix). Digests of the files this issue
owns, at the end of this pass:

```
$ sha256sum … | cut -c1-12
151c9e1d1b9a  adapters/python/src/pact_adapters/limits.py
afc71837b2b6  adapters/python/src/pact_adapters/slo.py
e9bea874e8e5  adapters/python/src/pact_adapters/harness.py
b375bb53ffb8  adapters/python/src/pact_adapters/scoring.py
437b7d0aa943  adapters/typescript/src/limits.ts
f68f0988e9f7  adapters/typescript/src/run-trace.ts
10999c09bbfe  scripts/test-all.sh
8cab6d7cb4c3  adapters/python/tests/test_a_spend_cap_nothing_can_reach…py
```

Line numbers are given as of those digests and will drift. The symbol names will
not. No `git` command that discards work was used at any point.

---

## What is wrong

An author writes `cost-per-request-under: 0.05 USD` and believes they capped
what one request may cost. Write `NaN USD` or `inf USD` instead and every
comparison against that figure is false — `spent >= nan` is false at every
spend, and nothing can be at or above `inf` — so the ceiling is carried in the
table, is never reached, and nothing anywhere says so.

**The authored door is shut** (B3), re-measured here through the real binary on a
copy of `examples/refund-desk` with one line changed:

```
$ target/debug/pact check .
error: 'cost-per-request-under' is NaN USD, which is not an amount of money.
  --> ./agents/refund-desk/limits.yaml:11:25
  fix: Write `cost-per-request-under: 0.05 USD`, or any amount above zero, or remove the line. …
  rule: schema/below-the-floor
1 problem(s) found in .. Nothing was run.        (exit 1)
```

**The other door is a spec built in code** — a `Limits` assembled by a host, by a
test, by an importer, or by `harness` itself — and `pact check` never sees it.
Reproduced by putting the pre-fix value into a frozen `Limits` with
`object.__setattr__`, so no source was edited (`uv run python`, `src` on path):

```
pre-fix NaN cap, spent 1000.0                  -> reached None
pre-fix NaN cap, spent 1.7976931348623157e+308 -> reached None
pre-fix NaN cap, spent inf                     -> reached None
real 0.05 cap, spent 0.06                      -> Reached(ceiling=…limit=0.05…, at=0.06)
```

and through the whole harness — six model calls, a transport that answers
`usage() -> (100, 1000.0)` and declares `prices_money = True`, so the money meter
genuinely moves:

```
pre-fix cap NaN   spent=6000.0 halted=step-limit unmetered=() never_reached=()
pre-fix cap inf   spent=6000.0 halted=step-limit unmetered=() never_reached=()
pre-fix wall inf  spent=6000.0 halted=step-limit unmetered=() never_reached=()
pre-fix wall nan  spent=6000.0 halted=step-limit unmetered=() never_reached=()
```

Six thousand dollars under a five-cent intention, and `unmetered` empty — which
is the system telling the author that every ceiling they wrote was enforced. The
last two lines are the same fault on `runs-for-at-most`, one field over in the
same object; that half was still open after the first fix and is closed now.

### The guard belongs on the value, not on the reader

Guarding `Limits.from_mapping` and `limitsFrom` closes one route of four. The
direct constructor is the common one: `grep -coE "\bLimits\(" adapters/python/tests/*.py`
counts **46 occurrences across 9 files** today, 23 of them in this issue's own
test file and 23 elsewhere. `harness._delegating` reaches for
`dataclasses.replace` on every delegated member (`harness.py:2980-2981`).
Measured with the readers guarded and the value unguarded, the before-picture
comes back verbatim through a door nobody had looked at:

```
Limits(cost_per_request_under=float('nan'), cost_currency='USD')
    -> spent=6000.0 halted='step-limit' unmetered=() ceilings=['cost-per-request-under']
replace(parsed_0_05, cost_per_request_under=float('inf'))
    -> cap=inf  nothing_can_reach=()  money rows=['cost-per-request-under']
```

A `Limits` is `@dataclass(frozen=True)`, so `__post_init__` is the one moment
every Python route meets. A TypeScript object literal has no construction hook,
so that port's equivalent is the read every ceiling goes through, `ceilings()`.

---

## Root cause

**One sentence:** the answer to *"can any spend ever be at or above this
figure?"* was made a property of the READERS rather than of the VALUE, and when
it was finally moved onto the value the ANSWER was stored in a shape — a field
name — that carried nothing the object could check it against.

Three compounding decisions:

1. **`money()` returns whatever `float()` / `parse::<f64>()` accepts.** `NaN` and
   `inf` are legal spellings of a double. That is fine as long as somebody
   downstream asks whether the figure is one a run can reach; nobody did on this
   route, and by construction no checker can, because there is no document.
2. **The comparison is `at >= c.limit`.** Against `nan` it is false at every
   reading; against `inf` nothing can be larger. Both make the row
   *unsatisfiable* without making it *absent* — and every honesty channel in the
   system is built out of rows that are absent, not rows that never fire.
3. **A record of a lossy operation must be checkable.** The first fix stored a
   tuple of FIELD NAMES. A name asserts something about a figure and carries no
   figure, so nothing on the object could contradict it, `dataclasses.replace`
   copied it forward, and a caller could simply write one. Storing the FIGURE
   makes the record self-justifying and the derived view unforgeable.

**Why the class recurs:** `cost-per-request-under:` has three readers in the
Python port (`Limits`, `Slo`, and `learning.Permissions` for
`cycle-limits.per-month`) and one in the second port. Any answer held by a reader
rather than by the value has to be written N times and gets written N−1 times.
That is exactly how `Slo` came to drop the cap and say nothing.

---

## Why nothing caught it

Six checks could have. Each was blind, and each for a stateable reason.

**1. The schema floor did not exist yet, even for the authored door.** At `HEAD`
(`git show HEAD:crates/pact-schema/src/lib.rs`, `check_floor`), the match had two
arms — `Coerced::Integer(n)` against `at_least`, and `Coerced::Duration(0)` —
and `_ => return` for everything else. There was no `Money` arm at all. B3 added
one in the working tree; B8 is the half B3 cannot reach.

**2. Nothing in the committed tree ever wrote the figure.** `git grep -l "NaN
USD" HEAD` returns **nothing** — not a test, not an example, not a fixture. The
value had never been put through the system on any route.

**3. `unmeterable()` asks a different question.** It answers *"is there anything
here that can price this row?"*, not *"can this row ever fire?"* Measured on the
pre-fix value:

```
pre-fix unmeterable(counts_tokens=True, prices_money=True) -> ()
```

The row is present and priceable and unsatisfiable, and this channel is
therefore silent by design. Same in the second port:
`unmeterable(limitsFrom({"cost-per-request-under":"NaN USD"}), true, true)`
returns `[]` (`node --experimental-strip-types`).

**4. `priced_at_nothing()` names it, and for the wrong reason.** Measured:
`priced_at_nothing(0.0) -> ('cost-per-request-under',)` on the pre-fix value —
but only when the bound model's catalogue price is 0, and the sentence it feeds
says *"the model catalogue publishes that row at 0 USD"*, which is a true
sentence about the wrong thing. An author is sent to the catalogue instead of to
their own line.

**5. `reached()` cannot raise, so no run fails.** It returns `None`, which is the
same answer as a run that is comfortably inside its budget. A silence and a
success are the same value.

**6. The cross-port tests could not see it, and the second port has no tests of
its own.** Every cross-port test hands `run-trace.ts` an AUTHORED JSON document,
so it travels the one route the schema now guards. `find adapters/typescript
-name '*.test.ts' -o -name '*.spec.ts'` (excluding `node_modules`) returns **0
files**, and `package.json` has exactly two scripts, `trace` and `typecheck`. The
second port is exercised only from the Python suite, through a document.

Type checking cannot help with any of this: `float | None` accepts `nan` and
`inf`, and both ports agree that it should.

---

## The attack on the landed fix

The first fix landed green. Hostile review produced eleven findings, two of them
blocking, and **all eleven were upheld** — each was reproduced before being
repaired. Condensed, with the measurement that decided each:

**1. The record was a name, and a name cannot be checked.**
`Limits.nothing_can_reach` was a stored tuple whose own comment read *"DERIVED,
not accepted … passing it in by hand does not make it true."* It was accepted:

```
Limits(tool_calls_at_most=1, nothing_can_reach=('tool-calls-at-most',))
  -> ceilings=['tool-calls-at-most']  halted='tool-call-limit'
     unmetered=('tool-calls-at-most',)
     "these ceilings held nothing, because no amount of money can ever be at or
      above the figure written: tool-calls-at-most.
      fix: write an amount of money on that line, like `cost-per-request-under: 0.05 USD`."
```

A ceiling that demonstrably STOPPED the run, reported on the channel whose
wording is *"cannot promise"*, with a MONEY remedy for a tool-call ceiling — the
wrong-diagnosis defect `scoring._unmetered_caveats` was written to remove,
reintroduced by the field written to remove it.

**2. The guard destroyed the author's currency.** It cleared `cost_currency`
beside the amount and recorded it nowhere, so the clearing arm could not give it
back. On the fix's own motivating path, `_delegating` with `allowed=0.10`:

```
member wrote 'NaN USD'  -> cap=0.1 currency=''    stop: `cost-per-request-under` (0.11 of 0.1)
member wrote '0.50 USD' -> cap=0.1 currency='USD' stop: `cost-per-request-under` (0.11 of 0.1 USD)
```

Two members of one team, handed the same share by the same policy, stopped by
the same ceiling, printing different sentences — and the second port keeps the
currency through the same spread (`spend("NaN USD") -> amount=NaN currency="USD"`,
measured), so it was also the two ports printing different `stoppedBy.unit`,
which is the pair `run-trace.ts` projects in order to be compared.

**3. `wall_clock_s` carried the identical pathology, silently.** The docstring
claimed *"every route into it meets here"* and the loop inspected one of the two
float ceilings. The two `pre-fix wall` lines in
[What is wrong](#what-is-wrong) are the money before-picture verbatim, one field
over. The authored route was already shut — measured, `seconds('inf') is None`,
`seconds('nan') is None`, `seconds('1e400') is None`, and the real binary answers
`runs-for-at-most: inf` with `rule: schema/wrong-type`, exit 1 — which makes the
constructor the only way in, i.e. exactly the door B8 exists for.

**4 and 5 (blocking). `Slo` took the drop and skipped the report.** `Slo` is the
third reader of the same authored line. It set the cap to `None`, cleared the
currency, and recorded nothing: `Slo.unmetered()` returns `self.written`, and
`written` is built from `first-reply-within` and `per-word-under` only, so the
name could never arrive there. Masked because both readers usually take the same
authored `limits:` block. Decoupled and measured through the real harness with
`limits=Limits()`:

```
slo cap nan -> slo.cap=None cur='' unmetered=() never_reached=() spent=6000.0 halted=step-limit
slo cap inf -> slo.cap=None cur='' unmetered=() never_reached=() spent=6000.0 halted=step-limit
```

Six thousand dollars under an `S-GOV`, `tier: core` cap the author typed, with
every honesty channel empty — the T7 / FR-8.1.1 silent degradation surviving
inside the fix. For `inf` it was a strict regression: a wrong-reason sentence
became no sentence at all.

**6. `Slo`'s guard rested on a property `Slo` did not have.** Its own docstring
argued the guard belongs *"on construction, where every route in meets"* — the
property `Limits` earns by being frozen. `Slo` was a bare `@dataclass`, and
post-construction assignment restored the whole pathology.

**7. The machine-readable channel carried one reason for two causes.** The split
was applied to the prose only. Measured, both reasons through the real `Bus`:

```
figure-nothing-can-reach -> {'limits': ['cost-per-request-under'], 'transport': 'spending', …}
transport-cannot-price   -> {'limits': ['cost-per-request-under'], 'transport': 'unpriced', …}
```

Byte-identical apart from the transport's name, with the transport named in the
case where the transport is innocent. T7 requires the machine-readable report,
not only the prose.

**8 (blocking). The TypeScript half was held by a seam.** With the `ceilings()`
guard deleted, every key of the `run-trace.ts` output was byte-identical except
`capsNothingCanReach` — a projection the test driver computes for itself —
because `unmetered` was supplied anyway by `unmeterable()` for the B6
*"nothing here can price it"* reason (`VercelAITransport` declares
`pricesMoney = false`).

**9. The file's own mutation record was false.** It claimed the TypeScript
mutation gave *4 failed, 15 passed*; measured, **2 failed, 17 passed**.

**10. Six tests skipped silently when `node` was broken**, and `scripts/test-all.sh`
had no `node` check at all — while it DOES hard-fail on a missing
`target/debug/pact` for precisely that reason.

**11. The delegation test asserted absence over an unproven channel.** Deleting
the whole `bus.emit("session.limit.failed", …)` block left the file green, so
three `== []` assertions could not tell *"the member stopped saying it"* from
*"nothing says anything any more."*

---

## The fix

Nine files. Every claim below was re-measured at the digests listed at the top.

### `adapters/python/src/pact_adapters/limits.py` — the guard, on the value

* `__post_init__` (`limits.py:346`) walks BOTH float ceilings — `wall_clock_s`
  and `cost_per_request_under` — with three arms, not one:
  **move** a figure nothing can reach off the ceiling field onto its record, so
  no row is built and the figure that justifies the report is still there to
  point at; **clear** the record when a real figure arrives (this is
  `harness._delegating`'s path); **drop** a record the object's own predicate
  disagrees with, which is the arm a tuple of names could not have had.
* The record is the FIGURE, not a field name. `nothing_can_reach` is a read-only
  property (`limits.py:495`) over `held_nothing()` (`limits.py:469`), which
  returns `(field, reads)` pairs in `ceilings()` order so the report can choose a
  remedy per KIND of ceiling.
* `cost_currency` is not cleared. It is the half of the line that parsed.
* The predicate is `_nothing_can_reach` (`limits.py:671`): `math.isnan(cap) or
  cap == math.inf`, deliberately **not** `not math.isfinite(cap)`. See
  [Alternatives rejected](#alternatives-rejected).

Measured after (`uv run python`, one script, all routes):

```
from_mapping NaN USD    cap=None cur='USD' ncr=('cost-per-request-under',) rows=[]
from_mapping inf USD    cap=None cur='USD' ncr=('cost-per-request-under',) rows=[]
from_mapping NaN JPY    cap=None cur='JPY' ncr=('cost-per-request-under',) rows=[]
from_mapping 1e400 USD  cap=None cur='USD' ncr=('cost-per-request-under',) rows=[]
from_mapping -inf USD   cap=-inf cur='USD' ncr=()                          rows=['cost-per-request-under']
from_mapping 0.05 USD   cap=0.05 cur='USD' ncr=()                          rows=['cost-per-request-under']
ctor nan / ctor inf     cap=None cur='USD' ncr=('cost-per-request-under',) rows=[]
replace(parsed, inf)    cap=None cur='USD' ncr=('cost-per-request-under',) rows=[]
ctor wall inf / nan     wall=None          ncr=('runs-for-at-most',)       rows=[]
ctor wall -inf          wall=-inf          ncr=()                          rows=['runs-for-at-most']
forged record beside a live tool-call ceiling      -> ncr=() rows=['tool-calls-at-most']
forged record beside a real 0.10 cap               -> ncr=() cap=0.1
Limits(nothing_can_reach=('tool-calls-at-most',))  -> TypeError
```

### `adapters/python/src/pact_adapters/slo.py` — the third reader

`@dataclass(frozen=True)` (`slo.py:43`), the same three arms in `__post_init__`
(`slo.py:118`), the currency kept, and the record reported by `unmetered()`
(`slo.py:242`). Measured:

```
Slo 'NaN USD'  cap=None cur='USD' unmetered=('cost-per-request-under',)
Slo 'inf USD'  cap=None cur='USD' unmetered=('cost-per-request-under',)
Slo 'NaN JPY'  cap=None cur='JPY' unmetered=('cost-per-request-under',)
Slo '0.05 USD' cap=0.05 cur='USD' unmetered=()
Slo mutated after construction  -> FrozenInstanceError
```

### `adapters/python/src/pact_adapters/harness.py`

* `held_nothing = spec.limits.nothing_can_reach` onto `RunResult.unmetered`
  (`harness.py:905`), with `Slo`'s copy folded in beside it.
* `result.unmetered = tuple(dict.fromkeys(result.unmetered))` (`harness.py:940`)
  — order-preserving, because the order is `ceilings()`' order and a report that
  shuffles between runs is its own defect.
* `session.limit.failed` carries `held_nothing=list(held_nothing)`
  (`harness.py:1077`) beside `limits`, so the machine-readable channel separates
  the two reasons the prose separates.
* `_delegating` hands the join policy's share to BOTH readers
  (`harness.py:2980-2981`).

### `adapters/python/src/pact_adapters/scoring.py`

`_unmetered_caveats` reads `Limits.held_nothing()` (`scoring.py:773`) and prints
one remedy per kind (`scoring.py:745-755`). Measured, through the shipped code:

```
money   : these ceilings held nothing, because no amount of money can ever be at or above
          the figure written: cost-per-request-under. fix: write an amount of money on that
          line, like `cost-per-request-under: 0.05 USD`.
seconds : these ceilings held nothing, because no length of time can ever be at or above
          the figure written: runs-for-at-most. fix: write a length of time on that line,
          like `runs-for-at-most: 30s`.
```

The pre-existing single ending told an author who had typed a bad figure *"fix:
nothing to type"* — a right field name, a wrong diagnosis, and a remedy saying
do not act.

### `adapters/typescript/src/limits.ts` — the guard, at the read

`ceilings()` refuses both rows (`limits.ts:109` wall clock, `limits.ts:121`
money) and `capsNothingCanReach()` derives the names off `ceilings()` rather than
asking the predicate a second time, so the row-not-built and the name-reported
cannot come apart. Measured with `node --experimental-strip-types`:

```
limitsFrom NaN USD          cap=NaN  cur=USD rows=[]                        caps=["cost-per-request-under"]
limitsFrom inf USD          cap=Inf  cur=USD rows=[]                        caps=["cost-per-request-under"]
limitsFrom -inf USD         cap=-Inf cur=USD rows=["cost-per-request-under"] caps=[]
limitsFrom 0.05 USD         cap=0.05 cur=USD rows=["cost-per-request-under"] caps=[]
{...limitsFrom({}), wallClockS: Infinity}   rows=[]  caps=["finishes-within"]
{...limitsFrom({}), wallClockS: NaN}        rows=[]  caps=["finishes-within"]
{...limitsFrom({}), wallClockS: -Infinity}  rows=["finishes-within"] caps=[]
{...limitsFrom({}), wallClockS: 30}         rows=["finishes-within"] caps=[]
{...limitsFrom({cost NaN}), costPerRequestUnder: 0.1} rows=["cost-per-request-under"] caps=[]
limitsFrom({"runs-for-at-most":"inf"}).wallClockS === null
```

The last line is why the second port's wall-clock case is held by a unit probe
rather than by a `run-trace.ts` drive: no authored JSON can reach that door.

There is deliberately **no** stored `nothingCanReach` field in that port
(`limits.ts:52-61` records the spread that removed it). The two ports therefore
run opposite strategies — Python moves the figure off the ceiling field,
TypeScript keeps `NaN` on the object and refuses the row at the read — and
`capsNothingCanReach` depends on the figure surviving. That is now held by tests
in both directions (mutations 11–13 below), which it was not before.

### `adapters/typescript/src/run-trace.ts`

`process.argv[6] === "prices-money"` sets `pricesMoney = true` on the wrapper
(`run-trace.ts:134`). Not a convenience: it switches off the B6
*"nothing here can price it"* finding, which is what makes the SHIPPED
`unmetered` array able to discriminate — the whole of finding 8.

### `scripts/test-all.sh`

Hard-fails when `node` is not on PATH (`test-all.sh:75-81`), naming the count of
tests that would otherwise skip, beside the `target/debug/pact` check that exists
for the same reason.

### The successor that landed during this pass

A concurrent session replaced the two public figure slots
(`cap_nothing_can_reach`, `wall_nothing_can_reach`) with a module-private
`_HeldNothing` row type while this document was being written, so the claim is
now unforgeable **by type** rather than by predicate. It is a genuine further
finding against the shape described above: measured on the tree as this document
first described it, `Limits(cap_nothing_can_reach=inf).nothing_can_reach`
returned `('cost-per-request-under',)` with no cost line anywhere — the same
forgery one level down.

That work is somebody else's and was not touched here. It was re-measured,
because a document that describes a shape the tree no longer has is worth
nothing. At digest `151c9e1d1b9a…` every figure in this section still holds, and
the forgery door is now shut for all four spellings:

```
from_mapping NaN USD / inf USD / NaN JPY / 1e400 USD -> cap=None, currency kept, ncr named, rows=[]
from_mapping -inf USD / 0.05 USD                     -> cap kept, rows=['cost-per-request-under']
ctor nan, replace(parsed, inf), wall inf             -> figure moved, name reported, rows=[]
wall -inf                                            -> still live
Limits(nothing_can_reach=…)      -> TypeError
Limits(cap_nothing_can_reach=…)  -> TypeError
Limits(wall_nothing_can_reach=…) -> TypeError
Limits(_held_nothing=…)          -> TypeError
Slo 'NaN USD' -> cap=None cur='USD' unmetered=('cost-per-request-under',)
Slo 'NaN JPY' -> cap=None cur='JPY' unmetered=('cost-per-request-under',)
Slo '0.05 USD'-> cap=0.05 cur='USD' unmetered=()
```

---

## Alternatives rejected

**A — guard the readers (`from_mapping`, `limitsFrom`).** Tried first, measured
insufficient: `Limits(cost_per_request_under=float('nan'))` still spent 6000 USD
with `unmetered=()`, and `replace` still carried a money row. 46 direct
constructor occurrences in the Python tests alone, against a handful of
`from_mapping` calls. Strictly dominated by guarding the value.

**B — raise from `__post_init__` (fail-closed, matching `Learner._decide`).**
Available: the classification is complete before a single step runs. Rejected for
one structural reason — `harness._delegating` calls
`replace(member.limits, cost_per_request_under=granted)` on a member whose own
cap is `NaN USD` and hands it the join policy's real share, so raising would kill
that run one line before it became correct, and it would turn `from_mapping` into
a crash in a process the author never started. FR-8.1.1's fail-closed half is met
where an author actually is: `pact check` refuses the document (measured above).
**Worse in one respect, and it is stated rather than hidden:** the run still
spends. The mitigation is that the figure is unshippable through the authored
door.

**C — report on `never_reached` instead of `unmetered`.** Rejected twice over.
`never_reached` is a fact about the BINDING, assembled from the bound model's
catalogue price, and a cap that never parsed to a figure has no price to look up.
And `never_reached` exists in the Python port only, so using it would mean
inventing a channel in the second port for a fact whose recipient — the author,
sent back to their own line — is already `unmetered`'s.

**D — a sixth honesty channel, `unreachable`.** Rejected: same payload, same
recipient, and only the remedy sentence differed. `_unmetered_caveats` splits a
sentence in five lines; a channel per remedy multiplies the cross-port shape for
nothing.

**E — `not math.isfinite(cap)` instead of `isnan(cap) or cap == inf`.** Rejected,
and this is the sharpest judgement in the change. It would sweep in `-inf`, which
is the OPPOSITE pathology: `spent >= -inf` is true of every spend, so it fires on
step zero and stops the run LOUDLY. Measured, post-fix: `Limits(-inf)` keeps the
row and the run halts at `cost-limit` with `spent=0.0`. Guarding it would convert
a wrong-but-loud ceiling into an absent-and-quiet one, and would delete the only
value that exercises the non-finite arm of the sentence-builder in either port —
making every `stoppedBy` assertion in the holding test vacuous at the same
stroke. The predicate is *"no spend can be at or above this"*, not *"this is not
finite"*.

**F — mirror Python's drop-at-construction into TypeScript.** Not available: an
object literal has no construction hook. The divergence is real and is now held
by tests rather than by a comment.

**G — the reviewer's remedy "clear the record when the cap goes to `None`".**
Partly rejected, and the reason is measurable. Under the moved-figure design,
`replace(nan_limits, cost_per_request_under=None)` is indistinguishable from the
identity `replace(dropped, tokens_at_most=5)` — both pass `None`, because that is
the value the object already holds after `__post_init__` moved the figure. So
clearing on `None` would delete the record on every unrelated `replace`. The
forgery the remedy was really about is closed harder instead: the record can only
be about money, must be a figure the predicate agrees with, is cleared the moment
a real figure arrives, and (in flight) is not even nameable at the constructor.

**H — the reviewer's remedy "make `_probe()` fail instead of skip".** Not taken.
`node` present with `node_modules` absent makes `run-trace.ts` exit non-zero for a
genuinely missing runtime, not for a port regression, and the two are not
separable there. The gate-level assertion landed instead — which was the
reviewer's own primary remedy. G2 on the queue owns the general idiom.

---

## Blast radius

| surface | who reaches it | what changed |
|---|---|---|
| `Limits` | every Python route: `from_mapping`, direct construction (46 occurrences in `tests/`, 9 files), `dataclasses.replace` in `harness._delegating` | the record is the figure, not a name; both float ceilings guarded; currency kept |
| `Limits.cost_per_request_under` readers | `harness.py:905` (report), the team-budget read, `_delegating`'s `min(own, allowed)` | all three improved: `nan or 0.0` was `nan` (truthy) and became a whole team's pot; now `None or 0.0 -> 0.0` |
| `Limits.ceilings()` consumers | `reached`, `unmeterable`, `priced_at_nothing`, `harness.run` | one fewer row for an unreachable figure; `priced_at_nothing(0.0)` no longer double-reports it with the catalogue reason |
| `Slo` | `AgentSpec.from_document`, direct construction, `against_the_catalogue` | frozen; reports what it drops; currency kept |
| `harness.run` | every Python run | `unmetered` deduplicated; `session.limit.failed` gains `held_nothing` |
| `scoring._unmetered_caveats` | every scored eval run | a third sentence, for a duration ceiling that holds nothing |
| `adapters/typescript/src/limits.ts` | every TypeScript route (`ceilings()` is the read they all go through) | both rows guarded; `capsNothingCanReach` names both |
| `adapters/typescript/src/run-trace.ts` | the cross-port test driver only | `prices-money` argv |
| `scripts/test-all.sh` | every gate run | hard-fails without `node` |

**Document digests (`pact_doc::digest`) — not affected, and cannot be.** This
issue's edit set contains no Rust source. `crates/pact-doc/src/` contains no
reference to `cost-per-request-under`. And no authored document can carry the
figure at all: `pact check` refuses it (measured above), so no digest moves.

**The four-artifact rule — not triggered.** B8 adds and removes no authored key.
`AGENT_SPEC_FIELDS` in `adapters/typescript/src/harness.ts` carries `"limits"` as
one entry and is unchanged; `capsNothingCanReach` is a trace projection, not a
spec field.

**The five honesty channels on `RunResult`.** `unmetered` is the one touched.
`never_reached` changes indirectly and correctly (`priced_at_nothing` sees one
fewer row). `unenforced`, `unwatched`, `unretrieved` are untouched.

**Not reached, and it is a different issue: the METER.** The floor is under the
CAP. A remote agent's `"cost": NaN`, a price list resolving to `nan`/`inf`, and
`Meter.restored` applying `float()` with no finiteness test each switch off a
perfectly good `0.05 USD` cap from the other operand. None of those is a figure
inside a `Limits`, so none of them meets at `__post_init__`. Queued as B10.

---

## The test

**`adapters/python/tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py`.**
The file is untracked (`git status --porcelain` → `??`), so it is new with this
change, and it is being extended under this pass by the concurrent session
described above. Both figures are measured, with the digest each was taken at:

```
$ cd adapters/python && uv run pytest tests/<file> -q --collect-only
29 tests collected in 0.18s     # test file 8cab6d7cb4c3…, limits.py 68400667226c…
36 tests collected in 0.16s     # test file 314bf0aa9e27…, limits.py 151c9e1d1b9a…
$ uv run pytest tests/<file> -q
36 passed in 1.90s              # at the second pair of digests
```

Everything below describes the 29 the mutation table was measured against; the
seven added since hold the `_HeldNothing` forgery door.

**Through which door, per section — this is the part that decides whether the
test is worth anything.**

* **Port 1, the whole harness, not a seam.** `_run_with()` calls `harness.run`
  with a scripted transport that answers `usage() -> (100, 1000.0)` and declares
  `prices_money = True`; six model calls, so `r.spent >= 6_000.0` is asserted.
  The money meter genuinely moves, which is what makes the old silence a finding
  rather than an artefact of a stand-in that could not count.
* **Four routes into the value share one assertion helper** (`_held_nothing`), so
  the routes differ in the test bodies and the CLAIM cannot drift between them:
  `from_mapping`, the bare constructor, `dataclasses.replace`, and — for the
  clearing direction — `harness._delegating` through a real two-agent document.
* **The delegation path, through the real join.** A supervisor + specialist
  document built in code, run with `delegate_by_running`, reading
  `session.limit.failed` off the shared `Bus`. That is the only way out: the
  member's `RunResult` is consumed inside the join. Its three `== []` assertions
  now sit beside a POSITIVE CONTROL
  (`test_the_channel_the_three_assertions_below_read_is_alive`), which is finding
  11 repaired.
* **The sentence a person reads** goes through the shipped
  `scoring._run_every_case`, not through `_unmetered_caveats` directly.
* **Port 2, the real second runtime.** `node --experimental-strip-types
  src/run-trace.ts` in a subprocess with a JSON spec, driven with `prices-money`
  so the assertions land on the SHIPPED `unmetered` array rather than on a
  projection the driver computes for itself.
* **The authored door is held elsewhere** —
  `crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs`
  (B3's) — and was re-measured here through the real binary.

The ten tests added by the repair, and what each holds:

| test | what it holds |
|---|---|
| `test_the_claim_cannot_be_handed_to_the_object_from_outside` | the `TypeError`, and the forgeries the figure slot can still express |
| `test_the_currency_the_author_wrote_survives_the_share_they_are_handed` | two members of one team print the same sentence |
| `test_the_other_ceiling_in_the_same_dataclass_goes_the_same_way` (×2) | `runs-for-at-most: inf` / `nan`, with `0.0` and `-inf` as controls |
| `test_a_duration_that_holds_nothing_is_not_sent_to_the_money_line` | the third remedy, and that the two are not run together |
| `test_the_latency_reader_reports_the_cap_it_dropped` | `Slo` alone, `limits=Limits()`, through the real harness, 6000 USD |
| `test_the_name_is_said_once_when_both_readers_read_one_line` | the deduplication |
| `test_the_channel_the_three_assertions_below_read_is_alive` | the positive control on `session.limit.failed` |
| `test_the_machine_readable_report_carries_the_reason_the_prose_does` | `held_nothing` on the event, both reasons |
| `test_the_second_port_refuses_the_other_unreachable_ceiling_too` | the wall-clock guard in port 2, `-inf` and `30` as controls |

Two existing tests were corrected rather than added to:
`test_the_latency_reader_does_not_keep_a_copy_of_the_unreachable_cap` asserted
`cost_currency == ""`, which ENCODED the currency-destroying defect, and now
asserts the currency is kept; the two second-port tests now drive with
`prices-money`.

---

## The mutation

**Thirteen single-line edits, every one applied to the file, measured, and
restored with the digest compared.** These are this pass's own numbers, produced
by `$SCRATCH/mutate.py` against
`tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py` at 29
tests, with `limits.py` at `68400667226c…` / `bb62882c6de8…`, `slo.py` at
`8189e5392b61…`, `harness.py` at `e9bea874e8e5…`, `scoring.py` at
`de7b289058263…` and `limits.ts` at `9a9929adbe2d…`. Every run printed
`restored=ok`. Every mutation bites: there is no decorative row in this table.

| # | the one edit | measured | the tests that redden |
|---|---|---|---|
| 1 | `limits.__post_init__` move arm → `if False and …` | **18 failed, 11 passed** | 13 distinct tests: all four Python routes, the wall-clock ceiling, the event, both caveats, and the cross-port pair |
| 2 | the clear arm → `elif False:` | **2 failed, 27 passed** | `…member_given_a_real_share…`, `…claim_cannot_be_handed…` |
| 3 | the forgery-refusing arm → `if False and …` | **1 failed, 28 passed** | `…claim_cannot_be_handed_to_the_object_from_outside` |
| 4 | `("wall_clock_s", "wall_nothing_can_reach")` deleted from the loop | **4 failed, 25 passed** | `…other_ceiling_in_the_same_dataclass…[nan]/[inf]`, `…duration_that_holds_nothing…`, `…claim_cannot_be_handed…` |
| 5 | `Slo.__post_init__` move arm → `if False and …` | **4 failed, 25 passed** | the wrong-reason sentence, the 6000 USD, the event, the duplicate |
| 6 | `Slo.unmetered()` → `held = ()` | **3 failed, 26 passed** | `…latency_reader_reports_the_cap_it_dropped`, `…does_not_keep_a_copy…`, `…machine_readable_report…` |
| 7 | `held_nothing=[]` on `session.limit.failed` | **1 failed, 28 passed** | `…machine_readable_report_carries_the_reason_the_prose_does` |
| 8 | the `dict.fromkeys` line deleted | **1 failed, 28 passed** | `…name_is_said_once_when_both_readers_read_one_line` |
| 9 | `slo=replace(member.slo, …)` deleted from `_delegating` | **1 failed, 28 passed** | `…member_given_a_real_share_stops_saying_its_cap_holds_nothing` |
| 10 | the `seconds` remedy deleted from `_unmetered_caveats` | **1 failed, 28 passed** | `…duration_that_holds_nothing_is_not_sent_to_the_money_line` |
| 11 | `limits.ts`: drop `&& !nothingCanReach(l.costPerRequestUnder)` | **4 failed, 25 passed** | both params of `…second_port_names_the_same_cap…` AND of `…both_ports_name_it_for_one_document` |
| 12 | `limits.ts`: drop `&& !nothingCanReach(l.wallClockS)` | **1 failed, 28 passed** | `…second_port_refuses_the_other_unreachable_ceiling_too` |
| 13 | the `wallClockField` line deleted from `capsNothingCanReach` | **1 failed, 28 passed** | the same test |

**Two corrections to earlier records, both made because the measurement
disagreed — and one of them is now stale again, which is disclosed rather than
hidden.**

1. The passed column in the file's own docstring was one lower on every row
   (`18 failed, 10 passed`, `2 failed, 26 passed`, …): those numbers were taken
   when the file held 28 tests and a 29th was added afterwards. The FAILED counts
   were all correct. Ten of those numbers were corrected in the docstring at
   digest `8ddfdb0ae6bc…`. **The concurrent session then rewrote the same file to
   36 tests** (`314bf0aa9e27…`), which makes the whole passed column stale again
   by seven. It was left alone at that point: re-measuring thirteen source
   mutations against a file two sessions are writing would mean restoring source
   bytes over somebody else's live edit, and the risk of destroying their work is
   worse than a stale number in a docstring. **Whoever owns the `_HeldNothing`
   change should re-measure the record.** No test was skipped, weakened or
   deleted at any point.
2. Mutation 11 is the one the pre-repair file got wrong: it claimed four tests
   and measured two, because two of the four assertions were satisfied anyway by
   `unmeterable()`'s own B6 finding. With `prices-money` on the driver the claim
   is true and is made on the SHIPPED array — measured here, **4 failed**.

Controls that stay green under all thirteen, because they are about ceilings that
ARE figures: `test_the_control_cap_still_stops_the_run_it_was_written_for`, the
`wall_clock_s = 0.0` control, `test_the_second_port_still_stops_on_the_one_cap_a_run_can_reach`,
and `test_both_ports_read_every_way_a_spend_cap_is_written.py` entire.

---

## Failure cases

Every case enumerated, each marked with what holds it.

| written / built | before | after | held by |
|---|---|---|---|
| `cost-per-request-under: NaN USD` in a FILE | `schema/below-the-floor`, exit 1 | unchanged | covered-by `crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs` (B3), re-measured here through the real binary |
| `runs-for-at-most: inf` in a FILE | `schema/wrong-type`, exit 1 | unchanged | covered-by the schema; re-measured here |
| `Limits.from_mapping({'cost-per-request-under': 'NaN USD'})` | `cap=nan`, row built, `unmetered=()` | figure moved, currency kept, field named | covered-by `test_a_run_under_a_cap_nothing_can_reach_says_so_and_spends_anyway` |
| `'inf USD'`, `'Infinity USD'`, `'1e400 USD'`, `'NaN JPY'` | same | same | covered-by the same test (two parametrisations) plus the spellings measured above |
| `Limits(cost_per_request_under=float('nan'))` — the bare constructor | 6000 USD, `unmetered=()` | named on `unmetered` | covered-by `test_the_same_cap_handed_straight_to_the_constructor_goes_the_same_way` |
| `replace(parsed, cost_per_request_under=inf)` | row built | figure moved | covered-by `test_a_real_cap_replaced_by_one_nothing_can_reach_goes_the_same_way` |
| a delegated member handed the join policy's real share | stale claim beside a LIVE ceiling — could halt at `cost-limit` on the field it said held nothing | claim cleared on both readers | covered-by `test_a_member_given_a_real_share_stops_saying_its_cap_holds_nothing` (+ positive control) |
| that member's stop sentence | `(0.11 of 0.1)` — currency destroyed | `(0.11 of 0.1 USD)` | covered-by `test_the_currency_the_author_wrote_survives_the_share_they_are_handed` |
| a NaN cap read as a whole TEAM's budget (`cap or 0.0`, and `nan` is truthy) | a NaN pot divided among members | `0.0` | covered-by `test_a_cap_nothing_can_reach_is_not_a_team_budget_either` |
| `Limits(nothing_can_reach=('tool-calls-at-most',))` | a live ceiling reported unheld, with the money remedy | `TypeError` | covered-by `test_the_claim_cannot_be_handed_to_the_object_from_outside` |
| a forged figure record beside a live ceiling | n/a | dropped | covered-by the same test |
| `Limits(wall_clock_s=inf)` / `nan` | row built, `unmetered=()`, 6000 USD | row refused, `runs-for-at-most` named | covered-by `test_the_other_ceiling_in_the_same_dataclass_goes_the_same_way` |
| `Limits(wall_clock_s=-inf)` and `0.0` | live | unchanged, still live | covered-by that test's controls |
| `Slo(cost_per_request_under=nan)` with `limits=Limits()` | 6000 USD, `unmetered=()` | named on `unmetered` | covered-by `test_the_latency_reader_reports_the_cap_it_dropped` |
| a `Slo` mutated after construction | guard bypassed entirely | `FrozenInstanceError` | covered-by the class being frozen; measured here |
| one document, both readers | the name twice on `unmetered` | once | covered-by `test_the_name_is_said_once_when_both_readers_read_one_line` |
| `session.limit.failed` for the two reasons | byte-identical payloads, transport blamed | `held_nothing` separates them | covered-by `test_the_machine_readable_report_carries_the_reason_the_prose_does` |
| the remedy sentence for money | *"fix: nothing to type"* | names the line and shows the replacement | covered-by `test_the_report_sends_the_author_to_the_line_and_not_to_the_transport` |
| the remedy sentence for a duration | (unreachable) | *"write a length of time on that line"* | covered-by `test_a_duration_that_holds_nothing_is_not_sent_to_the_money_line` |
| the OTHER reason a ceiling lands on `unmetered` | one sentence for two causes | split | covered-by `test_the_other_reason_a_ceiling_lands_there_keeps_its_own_sentence` |
| port 2: a money cap nothing can reach | row built, silent | row refused, named on the shipped `unmetered` | covered-by `test_the_second_port_names_the_same_cap_on_the_same_channel`, `test_both_ports_name_it_for_one_document` |
| port 2: `{...limitsFrom({}), wallClockS: Infinity}` | row built, named nowhere | row refused, `finishes-within` named | covered-by `test_the_second_port_refuses_the_other_unreachable_ceiling_too` |
| port 2: a real cap | not named | not named | covered-by `test_the_second_port_leaves_a_cap_that_is_a_figure_alone` |
| `-inf USD` in either port | fires on step 0, printed identically | unchanged | covered-by `test_both_ports_read_every_way_a_spend_cap_is_written.py` |
| a meter poisoned by a remote agent's `"cost": NaN`; a price list resolving to `nan`; `Meter.restored` with no finiteness test | switches off a good cap | unchanged | **UNCOVERED** — the other operand, queued as B10 |
| `tool_calls_at_most`, `tokens_at_most`, `steps_at_most` | `int \| None`, cannot carry a non-finite value | n/a | not a case |
| a code-built `Slo` whose figure is forged into the record slot | n/a | refused by the same predicate | covered-by `Slo.__post_init__`'s third arm; **no dedicated test names it** |

---

## What remains open

1. **B10 — the other operand.** The floor is under the CAP; the METER is
   unguarded and `Limits.__post_init__` cannot see it. Not touched here.
2. **`_probe()` still reports a port regression as a skip** for any error that
   makes `run-trace.ts` exit non-zero on the no-limits document. The gate-level
   `node` assertion closes the environment half — measured, with a `node` on PATH
   that exits 127 this file reports `7 skipped` and the gate now refuses to start
   at all. G2 on the queue owns the general idiom.
3. **`held_nothing` is not on any second-port event.** `harness.ts` emits no bus
   events at all, so there is nothing to add it to. Recorded so a future reader
   does not take the Python payload for a cross-port contract.
4. **The published test counts are stale in two files, and nothing guards them.**
   Measured: `cd adapters/python && uv run pytest tests/ -q --collect-only` →
   **1954 tests collected**. `README.md:73` says `2868 tests (914 Rust + 1954
   adapter)` — current, and `test_the_headline_test_count_is_the_count.py`
   recomputes it. `site-docs/status/verified.md:15-17` says `914 / 1928 / 2,842`
   and `site-docs/index.md:50` says `2,842 — 914 Rust, 1928 adapter` — **stale by
   26**. `scripts/sync-counts.sh` writes all four files; only the README one is
   held by a test. Not corrected here, because the adapter count is moving under
   several sessions at once and writing a number that is wrong in a different way
   would be worse. It is a real hole and it is B8-adjacent, not B8-caused.
5. **The mutation record inside the test file needs re-measuring by whoever owns
   the `_HeldNothing` change.** Its FAILED counts are right; its passed column is
   stale by seven now that the file holds 36 tests, and four of the thirteen
   anchors (the `__post_init__` arms) no longer exist in the form the table names
   — `__post_init__` now walks `_CEILING_FIELDS` and writes a private
   `_HeldNothing` row. This pass did not chase it: restoring source bytes over a
   live edit from another session risks destroying their work, which is worse
   than a stale number. See [The mutation](#the-mutation).
**And the shape of the whole thing**, which is not an open item but is why there
were three rounds. The first fix stored a field NAME and called it derived; it
was not. The second stored the FIGURE in a public slot and called it unforgeable;
measured, it was not — `Limits(cap_nothing_can_reach=inf).nothing_can_reach`
returned `('cost-per-request-under',)` with no cost line anywhere. The third
makes the record private and refuses anything else by type, measured shut for all
four spellings. A record a caller can write is a record a caller will write, and
it took three rounds to apply that one sentence to this one field.

---

## Verification

Scoped, this pass, in order:

```
$ cd adapters/python && uv run pytest tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py -q
29 passed in 1.21s          # test file 8cab6d7cb4c3…, limits.py 68400667226c…
36 passed in 1.90s          # test file 314bf0aa9e27…, limits.py 151c9e1d1b9a… (end of pass)

$ uv run pytest tests/ -q --collect-only
1954 tests collected in 2.15s

$ uv run pytest tests/ -q
2 failed, 1945 passed, 7 skipped in 138.80s
```

**The whole-suite run was taken mid-rewrite and its two failures are named,
because a number without its failures is not a measurement.** At that moment
`test_the_claim_cannot_be_handed_to_the_object_from_outside` failed with
`TypeError: Limits.__init__() got an unexpected keyword argument
'cap_nothing_can_reach'` — the `_HeldNothing` change had landed in the source and
not yet in the test — and
`test_three_mechanisms_that_only_their_tests_reached.py::test_the_margin_line_is_on_the_report_a_reviewer_reads`
failed for reasons unrelated to B8. Both belong to the concurrent session. The
B8 file itself measured `36 passed` once that session's own test update landed,
which is the last measurement in this document. Nothing here was changed to make
a number look better.

Second port and the real binary:

```
$ node --version                                     v24.15.0
$ node --experimental-strip-types <probe against src/limits.ts>     # figures in The fix
$ target/debug/pact check .   (workspace with cost-per-request-under: NaN USD)
  rule: schema/below-the-floor …  Nothing was run.   (exit 1)
$ target/debug/pact check .   (workspace with runs-for-at-most: inf)
  rule: schema/wrong-type …       Nothing was run.   (exit 1)
```

`cargo test --workspace` was **not** run and no crate was rebuilt: this issue
touches no Rust source, and a Rust run right now would measure another session's
in-flight work rather than this change. `npx --no-install tsc --noEmit` was not
re-run in this pass either; `adapters/typescript/node_modules` gating is
unchanged.

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md`, row **C9** — the row already carried B8's
substance. Two figures in it were stale against measurement and have been
corrected in place. Nothing else in the row was touched:

* *"28 tests"* → **36 tests**. Measured twice during this pass:
  `uv run pytest tests/<file> -q --collect-only` → `29 tests collected` at test
  file digest `8cab6d7cb4c3…`, then `36 tests collected` at `314bf0aa9e27…` after
  the concurrent `_HeldNothing` change extended it. The row carries the later
  figure, which is the tree as it now stands.
* *"eleven single-edit mutations recorded in the file, each measured"* →
  **thirteen**, which is what the file records and what this pass re-measured
  and confirmed one by one ([The mutation](#the-mutation)).

`docs/remediation/QUEUE.md` row 10 (B8, `in-code-nan-cap`) is `done` with this
file in the Doc column.
