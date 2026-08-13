# B5 — the two ports disagreed on four of the six documented money spellings, and the conformance payload carried no money at all, so nothing could see it

**Severity: high.** `cost-per-request-under:` is the one governance field whose
failure mode is an invoice. The two runtimes read the same authored line, stopped
at the same moment, and then told the person a different thing about what they had
spent and in what currency — and on three spellings one of them did not stop at
all. The suite that exists to compare the two ports could not see any of it,
because the money figure was never *sent* in a divergent spelling.

**Status: fixed, and the first fix was wrong in four further places that this pass
found and repaired.** The reader is repaired in both ports, the reporter is
repaired, the holding file is repaired, and two documents that were asserting the
opposite are corrected. Three things are **not** closed and are named under
[What remains open](#what-remains-open).

**Register rows touched:** `docs/70-PRODUCTION-GAP-REGISTER.md` Phase 3 bug 5
(the `USD` hardcode — the origin) and bug 10 (the hand-written payload — the
reason it survived; corrected by this pass, see [Register update](#register-update)).

---

### How to read the numbers in this document

Every figure below names the command that produced it, run on this machine
against this working tree on 2026-08-08. Where a figure could only be produced
against the **broken** state — the fix has landed, so the before-picture no
longer exists here — it was produced in an isolated mirror and says so.

**Another session was writing this repository throughout this pass.** Measured:
`git status --porcelain` lists 97 modified files, all but five of which this issue
never touched, and
`examples/mcp-desk/` appeared untracked during the pass. So no mutation was ever
applied to the shared tree. The mirror is

```
$SCRATCH/mirror/adapters/typescript/src     <- copy of the real src
$SCRATCH/mirror/adapters/python/src         <- copy of the real src
$SCRATCH/mirror/adapters/typescript/node_modules -> symlink to the real one
$SCRATCH/mirror/{examples,target,models,spec}    -> symlinks to the real ones
```

and it is the same source: `diff -rq <repo>/adapters/typescript/src
$SCRATCH/mirror/adapters/typescript/src` → `MIRROR IDENTICAL`, re-established by
`rsync -a --delete` before every single mutation. **Nothing under the repository
was mutated at any point.** Gate runs against `examples/` were done on
`tempfile.TemporaryDirectory()` copies; `git status --porcelain examples/` was
checked afterwards and shows only the other session's untracked folder.

---

## What is wrong

`coerce::money` (`crates/pact-schema/src/coerce.rs:328-349`) accepts a money
figure written several ways. Its own unit test names three of them and
`spec/schema.yaml`'s help offers them to the author:

```rust
let (amount, currency) = if let Some(rest) = s.strip_prefix('$') {
    (rest.trim().parse::<f64>().ok()?, "USD".to_string())
} else {
    let mut parts = s.split_whitespace();
    ...
    match (a.parse::<f64>(), b) {
        (Ok(v), Some(c)) => (v, c.to_ascii_uppercase()),
        (Err(_), Some(v)) => (v.parse::<f64>().ok()?, a.to_ascii_uppercase()),
```

Amount first or currency first, `$` as a prefix, any case, any Unicode
`White_Space` between the two tokens. All of these load. The TypeScript port read
one of them.

### 1. The reader — four of six spellings, measured

Measured over `spend()` in `adapters/typescript/src/limits.ts` against `money()`
in `adapters/python/src/pact_adapters/limits.py`, before the fix:

| written | Python | TypeScript | |
|---|---|---|---|
| `0.05 USD` | `(0.05, 'USD')` | `[0.05, "USD"]` | agree |
| `USD 0.05` | `(0.05, 'USD')` | `[0.05, ""]` | **DIVERGE** |
| `$0.05` | `(0.05, 'USD')` | `[0.05, ""]` | **DIVERGE** |
| `0.05 usd` | `(0.05, 'USD')` | `[0.05, "usd"]` | **DIVERGE** |
| `JPY 500` | `(500.0, 'JPY')` | `[500, ""]` | **DIVERGE** |
| `0.05 DOLLARS` | `(0.05, '')` | `[0.05, "DOLLARS"]` | **DIVERGE** |

The pre-fix reader is fourteen lines at
`git show HEAD:adapters/typescript/src/limits.ts:335-348`, and every defect is
visible in its loop:

```ts
for (const part of String(raw).replace(/\$/g, " ").split(/\s+/)) {
  if (/^[0-9.]+$/.test(part)) {
    const v = Number.parseFloat(part);
    if (!Number.isNaN(v) && amount === null) amount = v;
  } else if (part && amount !== null && !currency) {
    currency = part;
  }
}
```

* `replace(/\$/g, " ")` — the `$` is deleted rather than read, so `$0.05` has no
  currency;
* `amount !== null` — the currency is taken **positionally**, so a currency
  written before its number can never be taken;
* `currency = part` — no upper-casing, and no check that it is three ASCII
  letters, so `usd` is reported as `usd` where the loader stores `USD` and
  `DOLLARS` is reported as a currency `coerce::money` refuses outright;
* `/^[0-9.]+$/` — no sign, no exponent, no non-finite word, so `-5 JPY` and
  `0e0 JPY` load as **no cap at all** here while binding on the other side;
* `.split(/\s+/)` — JavaScript `\s` does not include `U+0085` NEL, which both
  `char::is_whitespace` and `str.split()` do.

### 2. This was authorable, not synthetic

The holding file's first draft disclaimed this away — *"These are specs BUILT IN
CODE and never pass `pact check`"*. That is true of the degenerate **amount** and
false of the **spellings**. Measured through the shipped binary
(`./target/debug/pact check`) on throwaway copies of `examples/refund-desk` with
`agents/refund-desk/limits.yaml:11` rewritten and nothing else touched:

```
'0.05 USD'        rc=0  OK — . loaded cleanly (498 settings).
'USD 0.05'        rc=0  OK — . loaded cleanly (498 settings).
'$0.05'           rc=0  OK — . loaded cleanly (498 settings).
'0.05 usd'        rc=0  OK — . loaded cleanly (498 settings).
'0.05<U+0085>USD' rc=0  OK — . loaded cleanly (498 settings).
'0.05 DOLLARS'    rc=1  error: 'cost-per-request-under' should be an amount of
                              money, like `0.05 USD`, but it is some text.
```

Four of the five divergent spellings — including the NEL row, the least
believable of the set — are lines a person can write and `pact check` accepts.
That is the strongest fact in this issue.

### 3. The reporter — the same defect one layer on

`Reached.sentence()` is *"the compared contract"* by this repository's own words.
Python formats a figure with `_round` (`limits.py:713`), which is `str(int(v))`
for a whole number and `f"{v:.4g}"` otherwise — C's `%g`. The TypeScript
`round()` (`limits.ts:201`) is a hand port of it, and it was wrong in two
independent ways:

* **non-finite**: `String(v)` writes `Infinity` / `-Infinity` / `NaN` where `%g`
  writes `inf` / `-inf` / `nan`. Live rather than hypothetical: every spend is
  `>= -Infinity`, so a cap of `-inf USD` fires on the first step and prints.
* **the tie rule**: `%g` rounds a half **to even**; JavaScript rounds it away
  from zero. The first repair asked
  `Number(a.toExponential(p)) === a && mant.endsWith("5")` — a **round-trip**
  test, not a **midpoint** test. Measured, `Decimal(10.005)` is
  `10.0050000000000007815970093361102044582366943359375`: strictly *above* the
  decimal midpoint, so `%g` rounds it **up** to `10.01` and never consults the
  tie rule at all. But `(10.005).toExponential(4)` is `1.0005e+1`, which parses
  back to the same double, so the round-trip test believed it had a tie, applied
  half-to-even, and rounded **down** to `10.00` → `"10"`.

Measured through the two shipped formatters (`sentence()` in `limits.ts` against
`_round` in `limits.py`), 54 000 five-significant-digit decimals ending in `5`
(mantissas 1000‥9999, exponents −5‥0 — the shape of an authored cap, and the only
shape that reaches the tie at all):

```
five-significant-digit decimals ending in 5   8439 of 54000 divergent   (15.6%)
uniform random doubles                           0 of  4000 divergent
```

after the repair, both are 0. The second row is why a random fuzz never found
this, and why the holding has to be fixtures naming the amounts.

`cost-per-request-under: 10.005 USD` is `pact check` rc=0. So was `0.12345 USD`,
and so were `10.005 usd`, `USD 10.005` and `$10.005`. This one was authorable in
every spelling.

### 4. The two comments that resolved one trade-off in opposite directions

Both readers had to decide what to do where `float()`, `str.split()` and
`parse::<f64>()` disagree. The file answered twice, differently, thirty lines
apart:

* `SEPARATOR` deliberately included `U+001C`–`U+001F` — which Python's
  `str.split()` splits on and `char::is_whitespace` does not — *"so the two
  readers agree rather than agreeing only where a document can reach"*;
* `FIGURE` deliberately excluded digit-group underscores and non-ASCII Unicode
  decimal digits — which `float()` takes and `parse::<f64>()` does not — as
  *"the safe direction: this reader takes strictly less than `float()` and
  exactly what the gate lets through"*.

One trade-off, two resolutions, and the `FIGURE` side left a **measured
divergence on the route this file is compared over**. Driven through the shipped
conformance driver (`node --experimental-strip-types src/run-trace.ts`) against
the reference port:

```
'0 JPY'    py halted='cost-limit'  node='cost-limit'  AGREE  (control)
'0_0 USD'  py halted='cost-limit'  node='final'       DIVERGE
'０ USD'    py halted='cost-limit'  node='final'       DIVERGE
'٠ USD'    py halted='cost-limit'  node='final'       DIVERGE
```

A ceiling in one port and none in the other — the failure the holding file's own
message calls worse than a wrong noun. And *"no checked document can carry one"*
was never a defence available here: this file's fixtures are specs built in code,
and `run-trace.ts` takes a payload straight off `process.argv[2]` with no gate
anywhere.

### 5. The `$` fix re-introduced the defect it was chosen to close

The first repair replaced `$` **globally**:
`String(raw).replace(/\$/g, " USD ")`. `coerce::money` strips a **prefix** and
then requires the entire remainder to be one float. Measured through the landed
reader, before this pass repaired it:

| written | reader | `pact check` |
|---|---|---|
| `0.05$` | `[0.05, 'USD']` | rc=1 `schema/wrong-type` |
| `5 U$D` | `[5, 'USD']` | rc=1 `schema/wrong-type` |
| `$0.05 USD` | `[0.05, 'USD']` | rc=1 `schema/wrong-type` |

A currency invented out of a dollar sign anywhere in the line, on a governance
field, through the mechanism chosen to stop exactly that — register Phase 3 bug
5's own defect class, re-entering by the door built for it.

### 6. Why a suite that already compares the two ports could not see any of it

The money figure was never *sent* in a divergent spelling.

* `adapters/python/tests/test_portability.py:93-119` (`_payload_for`) emits
  `name`, `instructions`, `tools`, `maxSteps`, `skills`, `team`, `loop`, `loops`,
  `answersWith`, `answersWithMode`. **There is no `limits` key at all.**
* Its own coverage table (`:518`) accounts for the whole block as
  `"limits": ("maxSteps",)`, and the predicate — then at `:528`, now at `:548`
  after the comment block this pass added above it — was
  `any(k in payload for k in keys)`, so the row passed on `maxSteps` being
  present.
* All three money fixtures in `test_termination.py` are written
  `<number> <CUR>` or as a bare number — the one order both readers already
  agreed about.

`docs/70-PRODUCTION-GAP-REGISTER.md:772` said of that payload: *"every emitted
key is sent or named with its §7.28 category. There is no third option."* The
guard is at **key** granularity and the defect was at **value** granularity, and
the register was left claiming the opposite.

`docs/20-ARCHITECTURE-{DRAFT,R5}.md:8931` named
`test_the_typescript_port_stops_at_the_same_ceiling_and_says_the_same_words` as
the **sole** holder of the `limits:` row's *"the words a person reads (G2)"*
claim — the one test measured to be incapable of seeing this. Nothing structural
holds that column: §7.28's own two enforcement tests run over `AGENT_SPEC_FIELDS`
and list B, not over the Held-by cell.

---

## Blast radius

**What reads a money cap.** `limits.py:280` (`Limits.from_mapping`) and
`limits.ts:332` (`limitsFrom`) are the only two call sites, and both take the
amount and the currency off one authored line. `Ceiling.unit` carries the
currency into `sentence()`; nothing else consumes it. So the reach of a wrong
read is: the halt decision (`Limits.reached`, `at >= c.limit`), the sentence a
person is shown, and `RunResult.unmetered` / `capsNothingCanReach`.

**Who else formats a figure.** `round()` is used by `sentence()` for *every*
ceiling, not just money — `${round(r.at)} of ${round(r.ceiling.limit)}` — so the
FUNCTION is on the ordinary path of every wall-clock and token ceiling too, and
the non-finite half of the defect reached all of them. The TIE half did not, and
the measurement says so plainly: 0 of 4 000 uniform random doubles diverged,
because the round-trip test only fires on a double that five significant digits
identify exactly. That is a number a person TYPES — `10.005`, `0.12345` — and
almost never one a clock produces. So the blast radius of the tie is precisely
the authored figure, which is the one a person reads back in the report and
compares against what they wrote. It went unseen because no fixture anywhere
sent a non-integer figure through the compared sentence.

**Who is not affected.** Nothing converts currency, here or anywhere:
`pact check` refuses a money figure the workspace's price list cannot charge in
(`loader/currency-nothing-can-price` — measured, `0.05 JPY` on the worked example
is rc=1). That is what makes the downstream comparison sound and it is unchanged.

**The doors that have no gate on them.** `run-trace.ts` accepts a payload off
argv. `Limits.from_mapping` is reachable from any embedder. `dataclasses.replace`
on a `Limits` is reachable from any test. So *"the gate refuses it"* is a
statement about files, never about the run — which is why the fix had to make the
two READERS agree, and not merely make them agree wherever `pact check` can
reach.

---

## The fix

One rule, stated once, in both ports:

> Read what `coerce::money` reads — the same separators, the same number grammar,
> at most two tokens, `$` as a PREFIX — with exactly two named widenings, each of
> which costs the CURRENCY and never invents one.

The two widenings are deliberate and written down in both files: a **bare number**
is a cap with no noun (`Ty::Money` does not coerce one, so only a code-built spec
reaches it), and a **second token that is not three ASCII letters** is dropped
rather than refusing the line (`0 DOLLARS` is zero of nothing).

| what | `limits.ts` | `limits.py` |
|---|---|---|
| separators, spelled out (Unicode `White_Space`, not `\s`, not `str.split()`) | `:601` | `:599` |
| number grammar — sign, exponent, `inf`/`infinity`/`nan`, `[0-9]` not `\d` | `:639` | `:607` |
| `$` as an anchored prefix, remainder must parse whole | `:544-549` | `:684-689` |
| at most two tokens | `:553` | `:693` |
| currency read lexically, three ASCII letters, upper-cased | `:574` | `:709` |
| `%g` non-finite words | `:211-212` | `:713` |
| `%g` tie to even, off the double's EXACT value in `BigInt` | `:258-292` | `:713`, `f"{v:.4g}"` |

The tie repair is the substantive one. A double is a dyadic rational, so its
exact value is a terminating decimal; `significant()` reconstructs it as
`num / den` in `BigInt` from the IEEE-754 fields and asks
`2 * remainder === den` — an exact equality on integers, which is the only form
of *"exactly a half"* that is not an approximation of one.

Two partings that were argued in opposite directions are now argued the same way,
and both comments say so: `SEPARATOR` no longer takes `U+001C`–`U+001F` (measured:
`0.05<US>USD` is `pact check` rc=1) and `FIGURE` still refuses underscores and
non-ASCII digits — because `limits.py` now makes the same parting. `float()` is
gone from `money()`.

### Reader parity, measured after

50 written forms through `money()` in Python and `spend()` in TypeScript:

```
divergent: 0 of 50
```

including the five digit-grammar forms the two readers parted on (`1_0 USD`,
`1_000.5 USD`, `１２ USD`, `١٢ USD`, `５ USD`) and all three `$`-placement rows.
Non-finite amounts are compared as doubles rather than through JSON, because
`JSON.stringify(Infinity)` is `null` and reads exactly like "no cap" — which
manufactures three false divergences if you let it.

---

## The test that holds it

`adapters/python/tests/test_both_ports_read_every_way_a_spend_cap_is_written.py`
— 19 tests, four fixture classes, each pinned to the reference port FIRST so a
red row is always a statement about the second port and never about a fixture
that was guessed:

| class | what it pins | rows |
|---|---|---|
| `SPELLINGS` | the currency NOUN, for each way `coerce::money` accepts | `0 JPY`, `JPY 0`, `$0`, `0 jpy`, `0 DOLLARS`, `0<NEL>JPY` |
| `GRAMMAR` | the cap BINDS in both, for each number form | `-5 JPY`, `0e0 JPY`, `-inf USD` |
| `ROUNDING` | the FIGURE written, for a cap that is not a whole number | `-10.005`, `-100.45`, `-0.12345`, `-1234.5` |
| `REFUSED` | no ceiling in EITHER port, for what the gate refuses | `0_0 USD`, `０ USD`, `٠ USD`, `0$`, `0 USD 0` |

The comparison is on `Reached.sentence()` **byte for byte**, not on the parsed
amount, because a unit test on `spend()` alone would prove the reader and not the
report — and the report is the contract.

**Why the amounts are degenerate.** `Limits.reached` compares `at >= c.limit`,
and the reference transport is bound to no model, so it spends nothing and reads
`0`. A cap at or below zero is therefore the only one that puts a sentence in the
report at all. That is a licence about the **figure** and not about the reader:
`10.005 USD`, `USD 10.005` and `$10.005` are all `pact check` rc=0, and it is the
same reader either way. `Schema::check_floor` is what refuses the sign and the
zero — measured, `0 USD` is rc=1 *"which is no money at all"* and `-10.005 USD`
is rc=1 *"which is less than nothing"*.

### The mutation

Every mutation applied **alone**, to the mirror, with the source restored by
`rsync -a --delete` and re-diffed before each one. Baseline **19 passed**:

```
no `$` arm at all                            1 failed   $0
global " USD " for the `$` PREFIX arm        1 failed   0$
amount !== null before the currency          1 failed   JPY 0
currency = part           for .toUpperCase() 1 failed   0 jpy
String(v)                 for inf/-inf/nan   1 failed   -inf USD
.split(/\s+/)             for SEPARATOR      1 failed   0<NEL>JPY
no `tokens.length > 2` guard                 1 failed   0 USD 0
round-TRIP tie test       for the midpoint   3 failed   -0.12345, -10.005, -100.45
float(token)              for _FIGURE (py)   3 failed   0_0, ０, ٠ USD
ties away from zero       for ties to even   1 failed   -1234.5
/^[0-9.]+$/               for FIGURE.test    7 failed   -5 JPY, 0e0 JPY, -inf USD,
                                                        and all four ROUNDING rows
the whole pre-B5 spend() restored           15 failed, 4 passed
  + the pre-B5 round()/significant() too    15 failed, 4 passed
```

Three of those are worth reading twice.

* `/^[0-9.]+$/` takes every `ROUNDING` row with it, because those amounts are
  signed. That is the same defect reaching two layers at once.
* The round-trip tie test and the ties-away-from-zero rule redden **disjoint**
  rows: the first three `ROUNDING` amounts are not exact binary midpoints and
  `-1234.5` is. A fixture set with only one kind in it would have held only one
  half of `%g`'s rule.
* Restoring the pre-B5 `round()` **on top of** the pre-B5 reader changes nothing
  — still 15 — because the `ROUNDING` rows are already red on the reader. Two
  independent defects on one row, which is exactly why each was also mutated
  alone.

The four survivors of a full revert are the `0 JPY` control and the three
digit-grammar `REFUSED` rows, which the old reader happens to refuse as well.
`0 JPY` is the only spelling `test_termination.py` sends.

### The anti-skip mechanism, and the false record it replaced

The holding file's own criterion is *"a test that cannot go red when the thing it
is testing crashes is not holding it."* It failed that criterion, and its
docstring recorded a measurement that does not reproduce.

`adapters/typescript/src/harness.ts:467-468` is
`const written = spec.limits ?? {}` followed by an unconditional
`limitsFrom(written)`, and `limits.ts:332` then calls
`spend(m["cost-per-request-under"])` on `undefined`. So the probe's "control"
document — a spec with no `limits:` block, described as *"nothing this file is
about"* — reaches `spend()` too, and a crash there was classified as an absent
runtime. Measured in the mirror:

```
node not on PATH at all                 19 skipped   pytest exit 0
node_modules absent                     19 skipped   pytest exit 0
throw at the top of spend()             19 failed    pytest exit 1
  — the same, against the OLD probe     19 skipped   pytest exit 0
```

The docstring claimed `8 passed, 1 skipped` before the probe and `1 failed`
after. That is nine outcomes for a file `pytest --collect-only` reports 19 tests
in, and the mechanism it described did not exist. Both docstrings are rewritten
with the figures above.

The repair is to classify by **signature** rather than by exit code. `_probe` now
returns `(kind, why)`, and only two signatures skip — `OSError` out of
`subprocess.run` (no `node` on `PATH`, `FileNotFoundError: [Errno 2]`) and
`ERR_MODULE_NOT_FOUND` in stderr (`Cannot find package 'ai' imported from
…/src/vercel-transport.ts`). Everything else is the port breaking, and
`_both_ports` calls `pytest.fail`. The cost is stated in the docstring rather
than hidden: a `node` too old for `--experimental-strip-types` now fails this
file rather than skipping it, which is the right way round.

---

## What remains open

**1. A green gate is still compatible with zero cross-port money comparison.**
With the TypeScript dependencies absent this file is `19 skipped`, pytest exit 0,
and `scripts/test-all.sh:45-49` skips the second port's typecheck under exactly
the same condition:

```sh
if [ -d adapters/typescript/node_modules ]; then
  (cd adapters/typescript && npx --no-install tsc --noEmit)
else
  echo "  (skipped: run \`npm install\` in adapters/typescript)"
fi
```

The probe closes the **per-file** half: a broken port now fails. Nothing closes
the other half. **The missing artifact is one gate-level assertion that the
second port is runnable** — either a test that fails when
`adapters/typescript/node_modules` is absent, or a hard failure in
`scripts/test-all.sh` for the same condition. It was not added by this pass
because it changes the gate for every environment in the project and is not B5's
to decide alone. The idiom is systemic rather than local:
`grep -rn "node/AI SDK unavailable" adapters/python/tests/*.py` returns 10 sites
across 6 other files, including `test_termination.py:770`, `:885` and `:931`.

**2. Both readers are still looser than `coerce::money` on the second token, and
nothing says so.** The second named widening — a token that is not three ASCII
letters is dropped rather than refusing the line — means `5 USDD` and `5 US` are
`[5.0, '']` in both ports and `schema/wrong-type` at the gate. That is a cap the
validator would refuse, enforced by a run, with the surplus dropped in silence:
`unmeterable` (`limits.ts:145`) covers unmeterable caps and `capsNothingCanReach`
(`limits.ts:387`) covers unreachable ones, and neither covers an unreadable
token. It is deliberate — refusing the whole line would turn a typo into no
ceiling at all, which is worse — but it is a T7 silent degradation on the
code-built route and it has no honesty channel. Both ports state the widening by
name in `spend()`/`money()`; **neither reports it at run time.**

**3. Nothing structural holds the §7.28 Held-by column.** The cell was false for
four of six spellings for as long as it was the only citation, and the section's
own enforcement — *"two tests hold the lists to the code rather than to good
intentions"* — runs over `AGENT_SPEC_FIELDS` and list B, not over that column. It
is now correct because it was edited by hand, which is the same standing it had
when it was wrong.

**A note on what `all(...)` did not fix.** Changing
`test_portability.py:548` from `any` to `all` is a real tightening, but measured
it closes nothing today: deleting the whole `skills` block from `_payload_for`
leaves the test green under **both** quantifiers, because `uses` and `loop` — the
only two multi-key rows — are also exempted by name in
`NOT_SENT_TO_THE_SECOND_PORT`. The live weakness there is the exemption, not the
quantifier. `all` is the guard for the next multi-key row that is not exempted.

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md` Phase 3 bug 10 said **"fixed,
structurally … every emitted key is sent or named with its §7.28 category. There
is no third option."** It now says *fixed at KEY granularity, and that is not the
same as fixed*, names the measurement (`_payload_for` carries no `limits` key;
the row passes on `maxSteps`), records the `any` → `all` change and what it does
**not** close, and points at the holding file for the level below.

`docs/20-ARCHITECTURE-DRAFT.md:8931` and `docs/20-ARCHITECTURE-R5.md:8931` now
cite `test_both_ports_read_every_way_a_spend_cap_is_written.py` beside the
existing test for `cost-per-request-under`, and record in the cell itself that
the citation was missing for as long as the row existed, that the cell was false
without it, and that nothing structural holds the column.

---

## Files changed by this pass

| file | what |
|---|---|
| `adapters/typescript/src/limits.ts` | the false round-trip explanation at `significant()` corrected to the measured exact expansion of `10.005`; the fuzz figures replaced with ones produced here (8 439 / 54 000, 15.6%) |
| `adapters/python/tests/test_both_ports_read_every_way_a_spend_cap_is_written.py` | `_probe` classifies by signature; `ROUNDING` and `REFUSED` fixture classes added; the false mutation record and the false *"never pass `pact check`"* claim replaced with measured ones; `0.05$` replaced by `0$` because a positive refused amount cannot go red on this route |
| `adapters/python/tests/test_portability.py` | `any(...)` → `all(...)`, with the measurement of what that does and does not close |
| `docs/70-PRODUCTION-GAP-REGISTER.md` | Phase 3 bug 10 corrected |
| `docs/20-ARCHITECTURE-DRAFT.md`, `docs/20-ARCHITECTURE-R5.md` | §7.28 list A `limits:` Held-by cell |
| `docs/remediation/B5-ts-money-divergence.md` | this document |
| `docs/remediation/QUEUE.md` | row 8 marked done |
| `README.md` | the headline test count, which this pass moved: the holding file went from 10 tests to 19, so the adapter total is 1928 → 1937 and the headline 2842 → 2851. `test_the_headline_test_count_is_the_count.py` is what said so, and it only speaks on a full-suite run |

---

## Verification

Scoped to what this issue touches, and stated as what was run.

```
uv run pytest tests/test_both_ports_read_every_way_a_spend_cap_is_written.py -q
    19 passed
uv run pytest tests/test_portability.py -q
    20 passed
cargo test -p pact-cli --test the_subset_the_second_port_runs
    3 passed        # the two §7.28 enforcement tests, over the row this pass edited
cargo test -p pact-cli --test authoring_surface
    16 passed       # the other reader of docs/20-ARCHITECTURE-DRAFT.md
npx --no-install tsc --noEmit
    rc=0
uv run pytest tests/ -q
    1937 collected
```

No Rust or Python **source** was changed by this pass — only comments in
`limits.ts`, two test files and five documents — so `cargo test --workspace` and
`cargo clippy` were not re-run; the two Rust tests that actually read the edited
document were, and pass.

**A note on the concurrent session, and why the full-suite number is not quoted
as a clean one.** Two full-suite runs during this pass reported failures in
`tests/test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py` — three in the
first (`13:45`), a different one in the second (`13:51`). Neither belongs to
this issue.
`adapters/python/src/pact_adapters/transports/a2a_transport.py` was modified at
`13:47:58` and again at `13:51:49`, inside both run windows, by the session
working the next queue row (`B6 — a2a-claims-to-price-money`), and the file
gives `8 passed` on its own immediately after each. Every other outcome in the
last run was green: `1 failed, 1929 passed, 7 skipped`, including
`test_the_headline_test_count_is_the_count.py`, which is the one that only
speaks on a full run. This is recorded rather than left out, because a green run
that had a red one before it is exactly the kind of thing a document should have
to explain.

### Re-verified independently, after the fact

Everything above was re-measured from scratch in a second pass against the tree
as it then stood, in a fresh mirror, because a document that can only be
confirmed by the session that wrote it is not evidence. Every figure reproduced.

* **The mutation table, row for row.** Seven mutations, each applied **alone** to
  a mirror restored from a pristine copy before each one, baseline `19 passed`:
  `round()`→`String(v)` gave `1 failed [-inf USD]`; the global `" USD "`
  substitution for the `$` prefix arm gave `1 failed [0$]`; dropping the
  `tokens.length > 2` guard gave `1 failed [0 USD 0]`; the positional
  `amount !== null` guard gave `1 failed [JPY 0]`; dropping `.toUpperCase()`
  gave `1 failed [0 jpy]`; `/^[0-9.]+$/` for `figure()` gave
  `7 failed [-5 JPY, 0e0 JPY, -inf USD, and all four ROUNDING rows]`;
  `.split(/\s+/)` for `SEPARATOR` gave `1 failed [0<NEL>JPY]`.
* **The anti-skip repair.** A `throw` as the first statement of `spend()` gives
  `19 failed`, pytest exit 1 — the case the old probe reported as `19 skipped`,
  exit 0. `node` absent from `PATH` still gives `19 skipped` exit 0
  (`[Errno 2] No such file or directory: 'node'`), and `node_modules` absent
  still gives `19 skipped` exit 0 (`ERR_MODULE_NOT_FOUND`). The probe
  distinguishes the three, which is the whole claim.
* **Reader parity.** 51 written forms through `money()` and `spend()`:
  `divergent: 0 of 51`. Python returns `None` where TypeScript returns
  `[null, ""]`, so the two have to be normalised before comparing — a comparison
  that skips that step manufactures divergences that are not there.
* **The gate rows.** All nineteen `pact check` results reproduced on throwaway
  `tempfile.TemporaryDirectory()` copies: `0.05 USD`, `USD 0.05`, `$0.05`,
  `0.05 usd`, `0.05<NEL>USD`, `10.005 USD`, `0.12345 USD`, `USD 10.005` and
  `$10.005` all rc=0; `0.05 DOLLARS`, `0.05<BOM>USD`, `0.05<US>USD`, `5 USDD`,
  `5 US`, `5 USD 7`, `0.05$`, `$0.05 USD`, `1_0 USD` and `０.05 USD` all rc=1
  `schema/wrong-type`. `git status --porcelain examples/` afterwards shows only
  the other session's untracked `examples/mcp-desk/`.
* **Open item 2 confirmed still open.** `money("5 USDD")` and `money("5 US")`
  are `(5.0, '')` in Python and `[5, ""]` in TypeScript, and both are rc=1 at the
  gate — a cap the validator refuses, enforced by a run, with the surplus token
  dropped and nothing said.

**Four citations had drifted and were corrected in this pass**, all because other
sessions edited the surrounding files after the figures were taken — the numbers
they point at were right, the lines had moved: `coerce::money` is
`coerce.rs:328-349` not `:328-350`; the Python `$` arm is `limits.py:684-689` not
`:684-690`; the `any`→`all` predicate is `test_portability.py:548` not `:528`
(the comment block this pass added above it is what moved it); and the
`node_modules` guard is `scripts/test-all.sh:45-49` not `:39-42`. The same stale
`:528` was corrected in the register's bug 10 row. This is the ordinary cost of
citing a line in a tree several sessions are writing, and it is worth saying out
loud: **a line number is the weakest kind of citation in this document, and every
claim above is also anchored to a command that reproduces it.**

