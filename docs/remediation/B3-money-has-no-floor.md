# B3 — money was the only quantity type with no bottom under it, so a spend cap of `NaN USD` loaded clean, was never reached, and reported itself enforced

**Severity: high.** It is the failure that costs money and leaves no trace: the
line is written, the checker says the workspace is fine, the run reports every
ceiling as held, and the only evidence is the invoice.

**Status: fixed at both doors, and one half of it was still missing when this
document was started.** The schema half had landed and survives every attack made
on it here. The run-time half had been applied to one of the two money ceilings
and not the other; the unguarded one was measured spending money under an
honesty channel that affirmed the ceiling held, and it is repaired. Six things
found by review are **not** repaired and are listed under
[What remains open](#what-remains-open).

**Register row: `docs/70-PRODUCTION-GAP-REGISTER.md:854` (`C9`)** — extended, not
corrected. See [Register update](#register-update).

---

### How to read the numbers in this document

Every figure below names the command that produced it, run on this machine
against this working tree. Where a figure could only be produced against the
**broken** state — the fix has landed, so the before-picture no longer exists
here — it was produced in an isolated snapshot and says so.

**Another session was writing this repository throughout this pass.** Measured:
`adapters/python/src/pact_adapters/mcp_bridge.py` was modified at `03:10:12`
while this work ran. So no mutation was applied to the shared tree. The snapshot
is

```
rsync -a --exclude .git --exclude node_modules <repo> $SCRATCH/snap
CARGO_TARGET_DIR=$SCRATCH/snap/target
```

and it is the same source: `diff -rq <repo>/crates $SCRATCH/snap/crates` →
`crates IDENTICAL`, and the same for `spec/schema.yaml` and
`adapters/typescript/src`. Every mutated file was restored and checked by md5
against the working tree's copy; those md5s are in
[The mutation](#the-mutation). **Nothing in the working tree was changed by this
pass except this document and `docs/remediation/QUEUE.md`.**

---

## What is wrong

PACT has four kinds of quantity an author writes as a figure with a unit. Three
of them carry their own bottom, so no field can forget it:

| type | its bottom | where it lives |
|---|---|---|
| duration | *"a length of time is more than nothing"* | `Coerced::Duration(0)` arm of `Schema::check_floor`, `crates/pact-schema/src/lib.rs:1668` |
| percent | `0.0..=1.0`, inside the coercer | `crates/pact-schema/src/coerce.rs:372-373` |
| whole number | `at-least:`, declared per field | `Field::at_least`, read at `crates/pact-schema/src/lib.rs:1659` |
| **money** | **none** | — |

Money carried exactly one property: its currency. `coerce::money`
(`crates/pact-schema/src/coerce.rs`) checks that the three letters after the
figure are three ASCII letters, and hands out whatever `str::parse::<f64>()`
produced — which happily accepts `NaN`, `nan`, `inf`, `infinity` and `1e400`.

### The reproduction

The fix has landed, so the before-picture was reproduced in the snapshot by
disabling the one arm that closes it — `if false && …` on the money arm of
`Schema::check_floor` — rebuilding, and running the shipped binary over a real
copy of `examples/refund-desk` with one line changed in
`agents/refund-desk/limits.yaml`:

```
### cost-per-request-under: NaN USD  -> OK — …/before loaded cleanly (498 settings).
    exit=0
### cost-per-request-under: inf USD  -> OK — …/before loaded cleanly (498 settings).
    exit=0
### cost-per-request-under: -5 USD   -> OK — …/before loaded cleanly (498 settings).
    exit=0
### cost-per-request-under: 0 USD    -> OK — …/before loaded cleanly (498 settings).
    exit=0
### per-month: NaN USD               -> OK — …/before loaded cleanly (498 settings).
```

And the contrast that makes it a missing floor rather than a parser problem —
the **same mutated binary**, the **same file**, the line one row above:

```
$ pact check before2      # finishes-within: 0s
error: 'finishes-within' is 0s, which is no time at all.
  --> …/agents/refund-desk/limits.yaml:10:18
   |
10 | finishes-within: 0s
   |                  ^^
  fix: Write `finishes-within: 30s`, or any length of time above zero, or remove the line. — …
  rule: schema/below-the-floor
1 problem(s) found … Nothing was run.
```

A length of time is not allowed to be zero. An amount of money was allowed to be
zero, negative, infinite, or not a number at all — on the field whose only job is
to stop a run before it costs more than its author agreed to.

### The two halves are different failures

**`0 USD` and `-5 USD` fire too early.** Every ceiling is compared as
`spent >= limit` (`adapters/python/src/pact_adapters/limits.py:341`, inside
`Limits.reached` at `:335`). So `cost-per-request-under: 0 USD` is reached before
the first step: every run stops instantly under a ceiling its author believed was
generous. That is the `0s` case exactly, and it is self-correcting — the first
run fails loudly and somebody goes looking.

**`NaN USD` and `inf USD` never fire at all, and that is worse.** In IEEE-754
every comparison against a NaN is false. The cap is not loose — **it is absent**.
Measured in the snapshot with the run-time guard disabled
(`return False and (…)` on `limits._nothing_can_reach`):

```
  cap parsed  -> nan 'USD' nothing_can_reach= ()
  ceilings    -> [('cost-per-request-under', nan)]
  reached at 1000.0                   -> None
  reached at 1.7976931348623157e+308  -> None
  reached at inf                      -> None
```

A ceiling carried as a live row that no spend there is can satisfy, with every
honesty channel empty. The run completes, the report says the ceiling was
enforced, and the author has done everything right: written the line, read it
back, run `pact check`, been told the workspace is fine.

The same was true of the second money ceiling, `learning.cycle-limits.per-month`
— the `S-GOV`, `tier: core` line that says how much a system may spend rewriting
itself — and there it survived the first round of this fix entirely. See
[The fix, part 6](#6-the-second-money-ceiling-the-half-that-had-not-landed).

---

## Root cause

**The class is: an invariant that belongs to a TYPE was never written, and the
slot where it would have gone was already occupied by a different invariant —
which made the type look validated.**

This is not "somebody forgot a check". Money had a rich, correct, well-tested
property check. It was about the label rather than the figure.

**1. The floor belongs to the type, and the type is where it was missing.**
`Schema::check_floor`'s own doc states the principle: a property every value of
the type has costs nothing per field and cannot be forgotten on the next one.
Duration got *"more than nothing"*. Percent got `0..=1`. Integer got the
per-field `at-least:`. Money got a currency.

**2. The one downstream reader threw the amount away by name.** Every money value
in the workspace passes through one function in `pact-loader`:

```rust
crates/pact-loader/src/currency.rs:144
fn currency_of(node: Option<&Node>) -> Option<String> {
    match coerce::check(node?, &Ty::Money) {
        Some(coerce::Coerced::Money { currency, .. }) => Some(currency),
        _ => None,
    }
}
```

The amount goes into the `..`. And the field selection around it is *derived* and
correct — `crates/pact-loader/src/currency.rs:166`,
`.filter(|f| matches!(f.ty, Ty::Money) || f.may_be_money)` — so a new money field
is covered by a line of YAML with no Rust change. A derived selection over a
half-read value reads, at a glance, as coverage. **A derived selection is not a
derived check.**

**3. The obvious mechanism could not express the bound.** `Field::at_least` is an
`i64`. The bottom a spend cap needs is *"more than nothing"*, not *"at least
one"*, because `0.0001 USD` is a legitimate cap. So the natural per-field place
declares the wrong thing, and the type-level place was never reached for.

**4. The one real objection closed the whole question.** A floor inside
`coerce::money` would break `models/catalog.yaml`, where `input-per-mtok: 0 USD`
is how a locally-served model declares its currency — measured,
`grep -c "input-per-mtok: 0 USD" models/catalog.yaml` → **5**. That objection is
correct about zero and has no force at all about `NaN`, and it was allowed to
settle both.

The consequence is asymmetric in exactly the direction that costs money: the
loud case corrects itself, and the silent case conceals itself.

---

## Why nothing caught it

**The test that should have caught it was green and claimed the opposite.**
`crates/pact-cli/tests/a_ceiling_in_money_nothing_can_price.rs` carried a test
named `every_money_field_the_specification_declares_is_one_this_check_can_see`
whose comment said `money_fields` *"reads the schema for fields typed `money` and
holds their VALUE against the price list"*. Two things were wrong and both were
load-bearing: what is held against the price list is the **currency**
(`currency_of`, above), and the test body enumerated nothing — it was
`assert!(!SPEC.contains("type: list of money"))`, a string-absence assertion
guarding a future nesting case. An auditor asking *"is money covered?"* landed on
a green test whose name promised the coverage that did not exist. That test was
still there, verbatim, when this document was started; it is repaired in
[part 7](#7-the-green-test-that-said-the-opposite-and-the-pin-that-replaces-it).

**Four green tests about money added up to no coverage of the figure.**
`coerce.rs`'s own `money_keeps_its_currency` (`crates/pact-schema/src/coerce.rs:635`)
asserts six things, all about the currency or the spelling. `crates/pact-schema/tests/durations_say_what_they_accept.rs`
made the whole floor argument correctly and generalised it across every field of
the type it was named for, never asking which other types were in the family.
`adapters/python/tests/test_a_ceiling_names_the_currency_the_author_wrote.py` is
the same shape one port over.

**The honesty channel built for this was asking a different question.**
`Limits.unmeterable` (`adapters/python/src/pact_adapters/limits.py:345`) exists
to say *"this run could not promise to hold these ceilings"*, and it is derived
from the transport — does it report tokens, does the catalogue price the model.
A `NaN` cap is metered perfectly by a transport that reports usage, so
`unmeterable` returned `()` and the run reported itself fully enforced. The
channel built for exactly this failure answered correctly about the wrong thing.

**A float has no bad values.** A duration that overflows panics in debug (B4). A
money figure that is not a figure parses, compares, and returns `false`. Nothing
in either language is warned.

---

## The fix

Seven pieces, in three languages. Line numbers are from this working tree today
and move as neighbouring code changes; the function names do not.

### 1. A floor under money, in the TYPE

`crates/pact-schema/src/lib.rs:1684-1714`, a new arm of `Schema::check_floor`
beside the `Duration(0)` arm:

```rust
coerce::Coerced::Money { amount, .. }
    if (!amount.is_finite() || *amount <= 0.0)
        && !money_past_counting(*amount, node) =>
```

Rule `schema/below-the-floor` — the same rule `finishes-within: 0s` gets, so the
two floors read as one rule of the language rather than two special cases. Three
sentences and not one, because they are three different edits:

* *"which is not an amount of money"* — `NaN`, `inf`
* *"which is less than nothing"* — `-5 USD`
* *"which is no money at all"* — `0 USD`

Somebody told that infinity is *too small* would go looking for a bigger number
to write. Measured through the shipped binary today:

```
error: 'cost-per-request-under' is NaN USD, which is not an amount of money.
  --> …/agents/refund-desk/limits.yaml:11:25
   |
11 | cost-per-request-under: "NaN USD"
   |                         ^^^^^^^^^
  fix: Write `cost-per-request-under: 0.05 USD`, or any amount above zero, or remove the line. — the most one request may cost, before it is stopped. …
  rule: schema/below-the-floor
```

Because the floor is the type's, it arrives on every field the specification
types `money` with no line naming any of them. Measured:
`grep -n "type: money" spec/schema.yaml` → **`1104`** (`limits.cost-per-request-under`)
and **`2701`** (`learning.cycle-limits.per-month`).

### 2. The far end, kept off the floor

`crates/pact-schema/src/lib.rs:1784`, an arm of `check_ceiling`:

```rust
coerce::Coerced::Money { amount, .. } if money_past_counting(*amount, node) => (
    "schema/too-much-to-count", …
```

`1e400 USD` and `inf USD` are one `f64::INFINITY` after the parse and two
different mistakes. The only thing that separates them is what the author typed,
so `money_past_counting` (`lib.rs:2725`) reads the text: infinity **and** the
written form has a digit in it (`has_a_digit`, `lib.rs:2659`). A negative
overflow is deliberately not here — it is less than nothing before it is large,
and "less than nothing" is the edit its author has to make. Measured:

```
1e400 USD    -> which is a larger amount than this can keep track of.  rule: schema/too-much-to-count
-1e400 USD   -> which is less than nothing.                            rule: schema/below-the-floor
```

### 3. The third money-shaped field, one crate over

`more-than:` on an approval gate is a GATE and not a ceiling — nothing ever runs
out against it, and `more-than: 0 USD` (*"ask a person about every refund"*) is a
workspace being strict, not broken. The schema floor never reaches it **by
construction and not by an exception**: A3 made the field `type: text` so a score
could be gated by a score, so it never coerces to `Money`.

A threshold that is not a figure is a different matter, and is refused where the
field is already read as a figure: `a_threshold_that_is_not_a_figure`,
`crates/pact-loader/src/money.rs:356`, called at `money.rs:81` — deliberately
before `compared_in_the_shape_the_argument_has` (`money.rs:82`), which carries a
matching suppression so one mistake gets one message. Rule
`loader/threshold-is-not-a-figure`. Measured through the binary on a copy of the
worked example, editing line 26 of `policies/approvals.yaml`:

```
NaN USD    exit=1  …`more-than: NaN USD` is not a figure at all…   loader/threshold-is-not-a-figure
inf USD    exit=1  …                                               loader/threshold-is-not-a-figure
1e400 USD  exit=1  …is a larger figure than this can keep track of loader/threshold-is-not-a-figure
0 USD      exit=0  OK — … loaded cleanly (498 settings).
-5 USD     exit=0  OK — … loaded cleanly (498 settings).
200 USD    exit=0  OK — … loaded cleanly (498 settings).
80         exit=1  …`amount` is an amount of money and `more-than: 80` is not…  loader/compared-in-the-wrong-shape
```

### 4. The run-time half, on the VALUE and not on a reader

`pact check` never sees a spec **built in code**, and that route is supported and
tested. So there is nothing to refuse and somebody has to be told instead.

The guard is `Limits.__post_init__` (`adapters/python/src/pact_adapters/limits.py:210`,
the drop at `:251-266`) over the predicate `_nothing_can_reach` (`limits.py:427`):

```python
return math.isnan(cap) or cap == math.inf
```

It was on the readers first (`from_mapping`, `limitsFrom`) and that closed one
door of four; `Limits(...)` is written directly **31 times across 11 files** in
`adapters/python/tests` (measured, `grep -rc "Limits(" adapters/python/tests/*.py`).
`__post_init__` is the one moment every route meets, and it works in both
directions — it sets `cost-per-request-under` on `nothing_can_reach` and
**clears** it when a real figure replaces the one it was about, which is what
stops `harness._delegating`'s `dataclasses.replace` carrying a stale name beside
a real ceiling. Measured today:

```
  {'cost-per-request-under': 'NaN USD'}   cap=None  cur=''    nothing_can_reach=('cost-per-request-under',)  ceilings=[]
  {'cost-per-request-under': 'inf USD'}   cap=None  cur=''    nothing_can_reach=('cost-per-request-under',)  ceilings=[]
  {'cost-per-request-under': '-inf USD'}  cap=-inf  cur='USD' nothing_can_reach=()  ceilings=[('cost-per-request-under', -inf)]
  {'cost-per-request-under': '0.05 USD'}  cap=0.05  cur='USD' nothing_can_reach=()  ceilings=[('cost-per-request-under', 0.05)]
  direct constructor NaN -> None ('cost-per-request-under',)
  replace with 0.10     -> 0.1 ()
```

`-inf` is deliberately **not** guarded, and the predicate is *"no spend can be at
or above this"* rather than `not math.isfinite`: `spent >= -inf` is true of every
spend, so `-inf USD` fires on the first step and stops the run loudly. That is a
wrong ceiling, not an absent one.

The name reaches the author on `RunResult.unmetered`
(`adapters/python/src/pact_adapters/harness.py:891`), and
`scoring.py:734` splits this member out of the channel's hard-coded *"nothing to
type"* caveat, because here there **is** something to type.

### 5. The second port

`adapters/typescript/src/limits.ts:344` (`nothingCanReach`) and `limits.ts:97`,
where it is applied inside `ceilings()` because a TypeScript object literal has
no construction hook. `capsNothingCanReach` (`limits.ts:319`) derives the
reported names off `ceilings()` rather than off a second call to the predicate,
so the row that is not built and the name that is reported cannot come apart;
wired at `adapters/typescript/src/harness.ts:541`. There is deliberately no
`nothingCanReach` **field** on the TS `Limits` type, with the measurement that
killed it recorded at `limits.ts:52-57`: a spread carried a stale name beside a
real `0.10` ceiling.

### 6. The second money ceiling — the half that had not landed

**This is what this pass found and repaired.** The schema floor reached both
money ceilings. The run-time guard reached one.
`learning.cycle-limits.per-month` had `_nothing_can_reach` on **no route at
all**, and the module has its own honesty channel that said nothing.

Measured (recorded in the code and in the new test file; three real cycles at
8.00 USD each against a real `.pact/learning/` ledger, `per-month: NaN USD`
handed to `Learner.from_document`):

```
cycle 1: applied=False  unmeasured=()  month_total=8.0
cycle 2: applied=False  unmeasured=()  month_total=16.0
cycle 3: applied=False  unmeasured=()  month_total=24.0
```

Twenty-four dollars of self-improvement under a ceiling, and `Outcome.unmeasured`
— the channel built for that exact field — empty on every cycle. Worse than the
before-picture B3 started from: not silence, an affirmation. The enforcement site
is `if would_reach > amount:` and `Learner._unmeasured` enumerated exactly three
reasons the ceiling can fail to bite (no workspace folder, an unpriced model, a
price list that honestly charges nothing), none of which a non-figure is.

Three edits, all in `adapters/python/src/pact_adapters/learning.py`:

* `Permissions.per_month_cap()` (`:386`, guard at `:422`) does not return a cap
  `limits._nothing_can_reach` answers for — the same predicate, imported at
  `learning.py:38`, not a second copy. The new predicate is
  `Permissions.per_month_holds_nothing()` (`:426`).
* `Learner._unmeasured()` gained a **fourth** sentence, first of the four
  (`:976`), quoting what the author wrote in the shape the other three use.
* `Learner._decide` **refuses the cycle** (`:1238`) before anything is scored.

Measured today on the shipped code:

```
  NaN USD   per_month='NaN USD'  cap=None         holds_nothing=True
  inf USD   per_month='inf USD'  cap=None         holds_nothing=True
  -inf USD  per_month='-inf USD' cap=(-inf,'USD') holds_nothing=False
  0 USD     per_month='0 USD'    cap=(0.0,'USD')  holds_nothing=False
  20 USD    per_month='20 USD'   cap=(20.0,'USD') holds_nothing=False
  from_document NaN -> 'NaN USD' None True
```

The author's own text is kept (`per_month` still reads `'NaN USD'`) because every
sentence in `learning.py` quotes it back; only the parsed cap is dropped.

**Why refuse here and report there.** `limits.py` reports and continues; this
refuses, and that is where the decision sits rather than an inconsistency.
`Limits` is a frozen dataclass on the delegation path — `harness._delegating`
calls `replace()` on a member whose own cap is `NaN USD` and hands it the join
policy's real share — so raising there would kill a run one line before it became
correct, and would raise out of `from_mapping`, turning a reportable line into a
crash in a process the author never starts. `Learner._decide` is a method call
with no money spent yet whose ordinary vocabulary is already
`Outcome(False, reason)`; two ceilings above it already answer that way.
`docs/30-FRD.md:204` (FR-8.1.1) says a lossy step is fail-closed by default, and
here fail-closed costs nothing structural, so it is taken. The field is *also*
named on `Outcome.unmeasured`, because a reviewer asking that channel which
ceilings held must not get `()` for the one ceiling that held nothing.

**Not conditional on `self.month.kept`.** The other three `_unmeasured` reasons
are facts about the world, and in each of them the line the author wrote is a
good line this cycle cannot hold — so the cycle runs and is told so. Refusing
those would punish an air-gapped workspace, which is the world this project
designs for. A figure that is not a figure is not one of those.

### 7. The green test that said the opposite, and the pin that replaces it

* `crates/pact-cli/tests/a_ceiling_in_money_nothing_can_price.rs:147` is renamed
  to `a_money_value_nested_inside_a_collection_would_be_out_of_this_walks_reach`
  — which is what it tests — and the false comment is replaced with the actual
  division of labour.
* `crates/pact-loader/src/currency.rs` gained the unit test
  `every_field_this_check_selects_is_also_held_to_being_a_figure`, which makes the
  enumerating claim for real: every field the schema types `money` has `NaN USD`
  validated into its group and `schema/below-the-floor` must come back; the set of
  `may-be-money` fields **not** typed `money` is pinned to `{more-than}`
  (`currency.rs:531`); and no field in the money family may carry an alias
  (`currency.rs:555`), because `money_fields` collects aliases and `money.rs`
  matches the literal key, so an alias would be a legal spelling with the figure
  check switched off.
* `crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs` is
  new, because the floor had **zero** coverage in any cargo-run test — see
  [The mutation](#the-mutation).
* Two documentation claims the code contradicted were rewritten:
  `Schema::check_floor`'s *"the same argument on the same comparison"* (it is not
  the same comparison — `>=` for one field, `>` for the other; see
  [Failure cases](#failure-cases)), and `spec/schema.yaml`'s `cycle-limits:` help,
  which still told authors `per-month` was *"recorded and NOT held"*.

---

## Alternatives rejected

**Put the floor in `coerce::money`.** The obvious home for a type's own bottom,
and it closes the only door out of the currency check: `currency.rs` re-runs
`coerce::check(.., &Ty::Money)` over `models/catalog.yaml`, which has five rows
publishing `input-per-mtok: 0 USD` (measured) as a legitimate way to declare a
currency. It would also report `0 USD` as *"not an amount of money"*, which is
false and offers no edit. The precedent is `0s`: the coercer accepts it and
`check_floor` refuses it, so the sentence can name the field and the line.

**Express it as `at-least:` in the specification.** `Field::at_least` is an
`i64`: it can say "at least one" and cannot say "more than nothing", and
`0.0001 USD` must load. It also would not have caught `NaN` — no comparison
against a NaN is ever true. And it is per field, so the third money field
somebody adds next year silently has no floor.

**Refuse `NaN USD` as `schema/wrong-type`.** Cheapest, and wrong for the reason
the duration floor already settled: it tells an author who spelled the line the
way the help says to spell it that the spelling is wrong, and offers an edit they
cannot find.

**Put the floor on `question-rule.more-than` too.** Rejected on what the field
means: it is a gate, nothing runs out against it, and `more-than: 0 USD` is a
legitimate strict rule. Its non-finite case is real and lives in `money.rs`
instead.

**Guard the readers (`from_mapping`, `limitsFrom`) rather than the value.** Tried
first. One door of four; the direct constructor and `dataclasses.replace` walked
straight past it.

**`not math.isfinite(cap)` instead of `isnan(cap) or cap == inf`.** Rejected:
`-inf` **is** reachable, so it is a wrong ceiling that fires loudly rather than an
absent one, and it is the only value exercising the non-finite arm of both ports'
number formatting.

**Report on `never_reached` rather than `unmetered`.** Rejected twice over:
`never_reached` is a fact about the binding, built from the bound model's
catalogue price, where this is known from the written line before a transport
exists; and it exists in one port only, so routing through it would mean
inventing a third channel in TypeScript to carry a fact with no reader.

**Fail closed in `Limits.__post_init__` — raise instead of reporting.** What
FR-8.1.1 asks for literally, and declined on a measured constraint rather than on
taste: the delegation path builds `Limits` by `replace()` on a member whose own
cap may be `NaN USD` and hands it a real share, so raising would kill a run one
line before it became correct. The fail-closed half of FR-8.1.1 is met where the
author is — `pact check` refuses the document — and is taken in `Learner._decide`,
where it costs nothing structural. This is a recorded decision, not an
impossibility claim; the classification happens before the run starts.

**Derive `money.rs`'s figure check from `may_be_money`, the way `currency.rs`
derives the currency check.** Considered and rejected on the diagnostic:
`a_threshold_that_is_not_a_figure` names the watched action and offers both
spellings the field can take (`more-than: 200 USD` for money, `more-than: 80` for
a score, because which is right depends on the tool's `takes:`), and a generic
walk over `may_be_money` keys can produce neither, while needing suppression
against the specific check to keep one mistake to one message. What is derived
instead is the **failure**: the pin in part 7 fails in front of whoever adds the
next such field. See [What remains open](#what-remains-open), item 1, for what
that does and does not buy.

---

## Blast radius

**Rust, upward.** `check_floor` has one caller, `Schema::check_value`. The single
production entry into `Schema::validate` is
`crates/pact-cli/src/main.rs:1410`, inside `fn validate` (`main.rs:1296`), which
is called from six places: `main.rs:2035`, `:2101`, `:2202`, `:2231`, `:2268`,
`:2316`. So the floor speaks on every subcommand that reads a workspace, not only
`pact check`. Measured on a worked example with `per-month: NaN USD`:

| command | result |
|---|---|
| `pact check` | exit=1 |
| `pact show` | `error: 'per-month' is NaN USD, which is not an amount of money.` exit=1 |
| `pact waits` | same diagnostic, exit=1 |

`pact show` is the one that matters: it is the door every adapter reads through,
so the figure cannot arrive at a run time by the supported route.

**Rust, downward.** No signature changed. The new arms call `money_past_counting`
(`lib.rs:2725`) and `has_a_digit` (`lib.rs:2659`), both shared with existing
checks rather than forked. `money::check`'s new call is one line in an existing
single-pass walk.

**Sideways, and deliberately unchanged.** `currency_of` (`currency.rs:144`) and
`money_fields` (`currency.rs:156`) still read only the currency, which is what
lets `models/catalog.yaml`'s five `0 USD` rows keep working.

**Digests.** No authored document's digest moves: `pact_doc::digest` hashes the
canonical form of the parsed `Node`, and this fix pushes `Diagnostic`s and mutates
no `Value`. (Reasoned from the code, not measured.) The **specification's** digest
does move, because part 7 rewrote one help paragraph in `spec/schema.yaml`;
`spec_digest` (`main.rs:379`) hashes the schema's canonical form and is reported
only when the schema did not come from the built-in copy.

**Honesty channels.** Only two are touched: `unmetered` gains a member
(`harness.py:891`, `harness.ts:541`) and `Outcome.unmeasured` gains a fourth
reason (`learning.py:976`). `unenforced`, `unwatched`, `unretrieved` and
`never_reached` are untouched. No double-reporting: `ceilings()` no longer builds
a money row for an unreachable cap, and `_never_reached` returns early when there
are no ceilings, so the same field cannot land on both.

**Both ports.** Parity is present and pinned from the Python suite
(`test_the_second_port_names_the_same_cap_on_the_same_channel`,
`test_both_ports_name_it_for_one_document`), which is the only place the TS half
is held — there is no vitest twin.

**Counts.** `scripts/test-all.sh` hard-codes the number of adapter test files that
need the built binary; it says **60** and there are **60** (measured,
`grep -rl 'pytest.skip("build the CLI first' adapters/python/tests/*.py | wc -l`).
The new monthly-ceiling test file deliberately does not shell out to the binary,
so it does not move that number. The README headline count is maintained by
`scripts/sync-counts.sh`; it currently reads
`2750 tests (909 Rust + 1841 adapter)` and matches (measured: `909` by the same
attribute count `test_the_headline_test_count_is_the_count.py` uses, and `1841`
collected).

---

## The test

Six files hold B3. Every count below is from running them today.

| file | tests | the door it goes through |
|---|---|---|
| `crates/pact-schema/tests/a_spend_cap_is_an_amount_of_money_and_has_a_bottom.rs` | **10** | a SEAM: `schema_from_yaml(include_str!("../../../spec/schema.yaml"))` then `spec().validate(...)`. Real specification, no binary. |
| `crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs` | **5** | the real binary via `CARGO_BIN_EXE_pact`, over a recursive copy of `examples/refund-desk`, both money ceilings. Cargo builds the binary as a dependency, so it cannot be stale. |
| `crates/pact-cli/tests/a_gate_whose_figure_is_not_a_figure_is_refused.rs` | **6** | the real binary, over a real copy of the worked example with one line rewritten in `policies/approvals.yaml`. |
| `crates/pact-loader/src/currency.rs::every_field_this_check_selects_is_also_held_to_being_a_figure` | **1** | a unit test over the SHIPPED `spec/schema.yaml`: enumerates the money family and requires the refusal to fire on each. |
| `adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py` | **8** | mixed: three shell out to `target/debug/pact`, the rest drive the real harness. |
| `adapters/python/tests/test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py` | **19** | the real harness over four routes into the value, plus the two caveat sentences, plus `Slo`, plus the second port through `run-trace.ts`. |
| `adapters/python/tests/test_both_ports_read_every_way_a_spend_cap_is_written.py` | **10** | both ports, comparing sentences byte for byte across six spellings. |
| `adapters/python/tests/test_a_monthly_ceiling_nothing_can_reach_refuses_the_cycle.py` | **29** | the real `Learner` with a kept month and a priced model, over a real `.pact/learning/` ledger. |

Measured:

```
$ cargo test -p pact-schema --test a_spend_cap_is_an_amount_of_money_and_has_a_bottom
test result: ok. 10 passed; 0 failed
$ cargo test -p pact-cli --test a_money_ceiling_that_could_never_hold_is_refused
test result: ok. 5 passed; 0 failed
$ cargo test -p pact-cli --test a_gate_whose_figure_is_not_a_figure_is_refused
test result: ok. 6 passed; 0 failed
$ cargo test -p pact-loader --lib currency
test result: ok. 11 passed; 0 failed; 189 filtered out
$ cd adapters/python && uv run pytest <the four files above> -q
66 passed in 3.35s        # 8 + 19 + 10 + 29
```

**88 tests in total** (22 Rust + 66 Python). The gate file was 5 tests when this
document's mutation work began and 6 twenty minutes later — another session added
one while this ran. Both runs were green; the count is the later one.

Two of them carry a **positive control inside an absence assertion**, because a
predecessor of one did not:
`a_threshold_a_person_is_asked_above_is_not_a_ceiling_and_keeps_its_zero` asserts
first that the gate document loaded with no errors at all (lines 254-258) and
then, at the end of the same test, that the floor it says must not reach
`more-than:` is switched on and speaking (line 268). Without those two lines the
test passed against a document that had already fallen apart.

---

## The mutation

Six mutations, **all performed by me**, all in the isolated snapshot, each
reverted and checked by md5 against the working tree's copy of the same file.

| # | the edit | measured result |
|---|---|---|
| **M1** | `if false &&` on the money arm of `Schema::check_floor` | `a_spend_cap_is_an_amount_of_money_and_has_a_bottom`: **3 passed, 7 failed**. `a_money_ceiling_that_could_never_hold_is_refused`: **2 passed, 3 failed**. `currency.rs` pin: **1 failed**. The binary rebuilt under it printed `OK — … loaded cleanly (498 settings)` for all four bad figures on both money fields. |
| **M1′** | M1, plus the new CLI test file moved out of the tree | `cargo test -p pact-cli --no-fail-fast` → **targets: 60; non-ok: 0.** Every pact-cli target green with the money floor deleted. This is why the new CLI file exists. |
| **M2** | `a_threshold_that_is_not_a_figure(document, diags);` in `money::check` replaced with a no-op | `a_gate_whose_figure_is_not_a_figure_is_refused`: **0 passed, 5 failed**. The whole of `pact-loader` stayed green (**15 targets, 0 non-ok**) — which is how that hole survived the first round. |
| **M3** | all three `learning.py` edits reverted together | `test_a_monthly_ceiling_nothing_can_reach_refuses_the_cycle.py`: **24 failed, 5 passed**. |
| **M3a** | refusal reverted only (`per_month_cap` guard + the `_decide` block), honesty channel kept | **18 failed, 11 passed** |
| **M3b** | honesty-channel branch deleted only, refusal kept | **6 failed, 23 passed** |
| **M4** | `return False and (…)` on `limits._nothing_can_reach` | the four B3 Python files: **38 failed, 12 passed**. Also produced the run-time before-picture quoted in [What is wrong](#what-is-wrong). |
| **M5** | `return false && (…)` on `limits.ts`'s `nothingCanReach` | **4 failed, 25 passed** — the two cross-port tests × `NaN USD` and `inf USD`. |
| **M6** | `may-be-money: yes` added to `when-this.arg` (a `type: text` field) in `spec/schema.yaml` | the `currency.rs` pin **fails**, with: *"`may-be-money: yes` is now on a field this crate figure-checks nobody … Teach `a_threshold_that_is_not_a_figure` to reach the new field before shipping it. left: {"arg", "more-than"}"* |

M3a and M3b are split on purpose: a fix that reported and did not refuse would
still be caught by 18 tests, and a fix that refused and said nothing would still
be caught by 6. Each half is held by something.

**Restoration, verified.** After every mutation the file's md5 was compared with
the working tree's:

```
crates/pact-schema/src/lib.rs               70f0ec23957841648aa8f708ee3438e9   (matches)
crates/pact-loader/src/money.rs             ef368ea506d60afe7fb7fe353c7cf978   (matched at the time of M2)
spec/schema.yaml                            99161b275209e6a69bab9a21649074d2   (matches)
adapters/python/…/limits.py                 b5de061c35ea13e962df1556eb5207d6   (matches)
adapters/python/…/learning.py               186bddd88dea517bd303e41e3856a922   (matches)
adapters/typescript/src/limits.ts           3be263d02b9cace72c06b75974c1b097   (matches)
```

`money.rs` was then edited by the other session at `03:27:23` (its md5 is now
`e59e9b8d7d0902ec2a229622b71a149f`), which is why the two figures differ if you
check today. B3's half of that file is unmoved — the call is still
`money.rs:81` and the function still `money.rs:356` — and
`a_gate_whose_figure_is_not_a_figure_is_refused` is green after their edit.

**No test in this issue passes with and without the fix.** Every guard is
load-bearing, and one mutation — M6 — proves the pin fires on the hazard rather
than on the defect, which is the only kind of check that can be in place before
the next money field exists.

---

## Failure cases

Every case below was either exercised by a named test or probed by me through the
shipped binary today. Where nothing holds it, it says UNCOVERED.

**The written document — `cost-per-request-under`**

| written | result (measured, `./target/debug/pact check`) | held by |
|---|---|---|
| `NaN USD` | `not an amount of money`, `schema/below-the-floor`, exit 1 | `a_spend_cap_that_is_no_money_at_all_is_refused_where_the_author_wrote_it`; end to end by `a_spend_cap_that_could_never_have_fired_is_refused_where_it_is_written` |
| `inf USD`, `+inf USD`, `-NaN USD`, `nan usd`, `USD -inf`, `infinity USD` | all `not an amount of money` | `every_spelling_of_a_number_that_is_not_one_is_caught` covers 11 spellings; the six I probed today are a superset of some of them — the four marked `+inf`, `-NaN`, `nan usd`, `USD -inf` are **correct but UNCOVERED by name** |
| `0 USD`, `0.0 USD`, `-0 USD` | `no money at all` | `an_amount_that_is_not_an_amount_is_not_told_it_is_too_small` (asserts both directions) |
| `-5 USD` | `less than nothing` | same test |
| `1e400 USD` | `a larger amount than this can keep track of`, `schema/too-much-to-count` | `an_amount_that_is_too_large_to_count_is_not_told_it_is_not_an_amount` (also asserts the floor does **not** fire at the same time) |
| `-1e400 USD` | `less than nothing` | same test's second half |
| `0.05 USD`, `0.0001 USD`, `500 JPY`, `$0.05`, `USD 12`, `1000000 EUR` | load, exit 0 | `an_amount_of_money_anybody_would_write_is_still_an_amount_of_money` |
| a bare `0` / `-5` / `0.05` with no currency | one `schema/wrong-type`, no floor message | `a_figure_with_no_currency_on_it_still_gets_the_one_message_it_already_had` |
| `1e-400 USD` (underflows to `+0.0`) | `no money at all` | **UNCOVERED**, and arguably the wrong sentence — see [What remains open](#what-remains-open) item 3 |
| `-1e-400 USD` (underflows to `-0.0`) | `no money at all` — **not** `less than nothing` | **UNCOVERED**, misclassified — item 3 |
| `5e-324 USD` (the smallest subnormal) | **exit 0, loads cleanly** | **UNCOVERED** — behaviourally the `0 USD` case; item 4 |

**The written document — `learning.cycle-limits.per-month`**

| written | result (measured) | held by |
|---|---|---|
| `NaN USD`, `inf USD` | `not an amount of money`, exit 1 | `the_other_ceiling_priced_in_money_has_the_same_bottom` (seam) and `the_other_ceiling_priced_in_money_has_the_same_bottom_through_the_same_command` (binary) |
| `0 USD` | `no money at all`, exit 1 | same, plus the reason is pinned by `test_a_monthly_ceiling_of_zero_lets_one_cycle_through_and_then_refuses` — because on this field the comparison is `would_reach > amount` and the first cycle of a month forecasts `0.0`, so `0 USD` lets **one** cycle's spend through rather than stopping every run instantly. The refusal is kept; the *reason* in `check_floor`'s doc was corrected to the measured one. |
| `-5 USD` | `less than nothing`, exit 1 | as above |
| `20 USD` | loads, exit 0 | `test_the_authors_own_ceiling_still_runs_the_cycles_it_was_written_for` |

**The written document — `question-rule.more-than` (a gate, not a ceiling)**

| written | result (measured) | held by |
|---|---|---|
| `NaN USD`, `inf USD` | `loader/threshold-is-not-a-figure`, exit 1 | `a_threshold_spelled_like_a_number_and_not_one_is_refused_where_it_is_written` |
| `1e400 USD` | *"larger figure than this can keep track of"*, same rule | `a_threshold_past_the_end_of_counting_is_not_told_it_is_not_a_figure` |
| `0 USD`, `-5 USD`, `200 USD` | load, exit 0 — a strict gate stays legal | `a_threshold_a_person_is_asked_above_is_not_a_ceiling_and_keeps_its_zero`, with two controls |
| `80` against a money argument | `loader/compared-in-the-wrong-shape`, and **not** two messages | `one_mistake_still_gets_one_message` |

**A spec built in code — the route no checker sees**

| route | result | held by |
|---|---|---|
| `Limits.from_mapping({'cost-per-request-under': 'NaN USD'})` | cap dropped, field named, no ceiling row | `test_a_run_under_a_cap_nothing_can_reach_says_so_and_spends_anyway` |
| `Limits(cost_per_request_under=float('nan'))` | same | `test_the_same_cap_handed_straight_to_the_constructor_goes_the_same_way` |
| `dataclasses.replace(parsed, cost_per_request_under=inf)` | same | `test_a_real_cap_replaced_by_one_nothing_can_reach_goes_the_same_way` |
| a delegated member handed a join policy's real share | the stale name is **cleared** | `test_a_member_given_a_real_share_stops_saying_its_cap_holds_nothing` |
| `-inf USD` | kept, fires on the first step, printed identically in both ports | `test_both_ports_read_every_way_a_spend_cap_is_written.py` |
| `Slo(...)` as the third reader | the copy is dropped | `test_the_latency_reader_does_not_keep_a_copy_of_the_unreachable_cap` — but **nothing reports it**; item 5 |
| `Permissions(per_month='NaN USD')` / `Permissions.from_document(...)` | cap dropped, cycle refused, field named on `Outcome.unmeasured` | `test_a_ceiling_nothing_can_reach_is_not_carried_as_a_figure`, `test_a_cycle_under_a_ceiling_nothing_can_reach_is_refused_before_it_spends`, `test_the_ceiling_that_held_nothing_is_named_on_the_honesty_channel` |
| `Limits(wall_clock_s=float('nan'))` — the other ceiling in the same dataclass | carried as a live row nothing can reach, `nothing_can_reach=()` | **UNCOVERED** — item 2 |
| a remote agent's reported cost arriving as `NaN` | the meter, not the cap, is poisoned; every ceiling silently stops firing | **UNCOVERED** — item 2 |
| a price list with `input-per-mtok: NaN USD` | `_cost` returns `nan`, which multiplies into every priced call | **UNCOVERED** — item 2 |
| a run resumed from a pause file containing `NaN` | `Meter.restored` applies `float()` with no finiteness test | **UNCOVERED** — item 2 |

**The catalogue.** `models/catalog.yaml`'s five `input-per-mtok: 0 USD` rows still
load: those fields are `type: text`, so `check_floor` never sees them, and
`currency.rs` calls `coerce::check` directly, which this fix did not change. No
named B3 test covers it; every `pact check` of the worked example exercises it
incidentally (`498 settings`, exit 0).

---

## What remains open

The adversarial review of the landed fix produced seventeen entries, one of which
was a positive control confirming the original reproduction is genuinely gone.
The blocking one (`per-month` unguarded at run time) and the important ones (no
cargo-run coverage; the misleading green test; the false "same comparison"
justification; the false *"that half is arithmetic"* docstring; the stale
`cycle-limits:` help) were repaired and are described above.

**Eight things are not repaired — six substantive, two smaller.** Items 1 and
3–6 come from the review; item 2 comes from the root-cause pass's question *"what
else in this tree is an instance of the same class?"* and is the largest of them.
They are listed rather than implied to be closed.

**1. `may-be-money: yes` is still currency-checked and figure-unchecked.**
`grep -rn "may_be_money" crates/ --include=*.rs` reaches only the currency filter
(`currency.rs:166`) and schema plumbing. Nothing reads it for a figure, and
`Schema::check_floor` matches `Coerced::Money`, which a `type: text` field never
produces. The only figure check for the family is `money.rs:356`, hard-coded to
one path (`policies → ask-a-person → when → more-than`). So a second money-shaped
field declared the way the specification recommends would get the price-list
check, no floor, and no finiteness check. What landed is a **pin, not a fix**:
M6 measured that adding `may-be-money: yes` to another field turns
`currency.rs`'s enumerating test red with a message naming the function to teach.
That fails in front of the person creating the gap, which is the right place —
but the gap is still creatable, and the check is a tripwire rather than a floor.

**2. The fix put a floor under the CAP and left the METER unguarded — the
comparison has two operands.** Measured today on the shipped code:

```
_what_it_cost(json.loads('{"result":{"usage":{"totalTokens":10,"cost":NaN}}}')) -> (10, nan)
meter.money after one such exchange -> nan
Limits(cost_per_request_under=0.05, cost_currency='USD').nothing_can_reach -> ()
cap.reached(meter, 1.0) -> None      # and still None after adding 1,000,000 USD

_cost({'input-per-mtok': 'NaN USD'})   -> nan
_cost({'input-per-mtok': 'inf USD'})   -> inf
_cost({'input-per-mtok': '1e400 USD'}) -> inf

Limits(wall_clock_s=nan).ceilings() -> [('runs-for-at-most', nan)]  nothing_can_reach=()  reached@1e9=None
Limits(wall_clock_s=inf).ceilings() -> [('runs-for-at-most', inf)]  nothing_can_reach=()  reached@1e9=None
Limits(wall_clock_s=0.0)            -> Reached(field='runs-for-at-most', limit=0.0, halted='time-limit')
```

A perfectly good `cost-per-request-under: 0.05 USD` — one this floor accepts and
`pact check` approves — is silently switched off for the rest of a run by one
value in somebody else's JSON (`transports/a2a_transport.py:259`,
`harness.py:672`, `harness.ts:748`), or by a price list
(`resolve.py`, `_cost`), or across a resume (`suspension.py` → `Meter.restored`,
`limits.py:158`). And `wall_clock_s` — the other ceiling in the very dataclass
this fix guards, declared `limits.py:182`, made a ceiling at `limits.py:317` and
compared through the same `at >= c.limit` — has no guard at all. This is strictly
worse than the defect B3 fixed on one axis: the author cannot see the offending
line in their own tree. **Queue rows B5, B6, B8 and B9 are adjacent to this but
are not it.** Nothing on the queue names the meter, the price list, the resume,
or `wall_clock_s`.

**3. A negative underflow gets the wrong one of the three sentences, and a
positive underflow gets a sentence the two sibling types do not use.** Measured:
`cost-per-request-under: -1e-400 USD` → *"which is no money at all"* (it parses to
`-0.0`, so `*amount < 0.0` is false); `1e-400 USD` → *"which is no money at
all"*, where `Coerced::Number` and `Coerced::Threshold` get their own
`schema/too-small-to-count`, *"closer to zero than this can keep track of"*
(`lib.rs`, `underflowed_to_zero` at `:2692`). The fix built the top-end split
(`money_past_counting`) with an argument that applies identically at the bottom
end and did not build the bottom end. No test mentions `1e-400`.

**4. The floor has no bound short of exactly zero.** Measured:
`cost-per-request-under: 5e-324 USD` → exit 0, `loaded cleanly (498 settings)`.
`spent >= 5e-324` is true of every non-zero spend, so that run stops on its first
priced step — behaviourally the `0 USD` case the floor exists to refuse.

**5. `Slo`'s drop is silent.** Measured: `Slo(cost_per_request_under=float('nan'),
cost_currency='USD')` → cap `None`, currency `''`, `unmetered()` → `()`. Its own
docstring says the fact is reported on `RunResult.unmetered`, which is true only
when a `Limits` was built from the same line. A directly-constructed `Slo` loses
the amount and the currency with nothing said anywhere. The B3 test for this
reader asserts the copy is dropped, not that anything says so.

**6. One line can now produce two messages, and one of them was written assuming a
figure.** Measured, `cost-per-request-under: NaN JPY` on a workspace priced in
USD:

```
error: `cost-per-request-under: NaN JPY` is in JPY, and nothing here deals in JPY: … and NaN JPY is not NaN USD.
  rule: loader/currency-nothing-can-price
error: 'cost-per-request-under' is NaN JPY, which is not an amount of money.
  rule: schema/below-the-floor
2 problem(s) found …
```

*"NaN JPY is not NaN USD"* is meaningless about a value that is not a figure. The
`one_mistake_still_gets_one_message` test covers the loader-threshold pair, not
this one.

Two smaller review findings are also unrepaired and are recorded for
completeness: `a_gate_that_cannot_be_read_as_money_is_still_refused_somewhere_else`
(`crates/pact-schema/tests/…:273`) asserts only an absence, and stayed **green
under M1** while seven of its siblings failed — its positive control lives in the
neighbouring test rather than in it; and the fix line the floor offers hard-codes
`0.05 USD` (`placeholder(&Ty::Money)`), so a workspace whose price list charges in
another currency is told to write USD, which
`loader/currency-nothing-can-price` then refuses.

---

## Verification

Scoped first, then whole. Everything below was run for this document.

```
$ cargo test -p pact-schema --test a_spend_cap_is_an_amount_of_money_and_has_a_bottom
test result: ok. 10 passed; 0 failed
$ cargo test -p pact-cli --test a_money_ceiling_that_could_never_hold_is_refused
test result: ok. 5 passed; 0 failed
$ cargo test -p pact-cli --test a_gate_whose_figure_is_not_a_figure_is_refused
test result: ok. 6 passed; 0 failed
$ cargo test -p pact-loader --lib currency
test result: ok. 11 passed; 0 failed; 189 filtered out

$ cargo clippy --all-targets -- -D warnings          # working tree
Finished `dev` profile … ; EXIT=0

$ cargo test --workspace --no-fail-fast              # isolated snapshot, crates byte-identical
targets: 90  non-ok: 0

$ cd adapters/python && uv run pytest tests/ -q      # working tree
1835 passed, 6 skipped in 127.01s

$ ./target/debug/pact check examples/refund-desk
OK — examples/refund-desk loaded cleanly (498 settings).
```

Two honest caveats about the last two lines.

* The workspace `cargo test` was run in the **snapshot**, not the working tree,
  because another session was editing the tree. It transfers because
  `diff -rq crates crates` reported `crates IDENTICAL` and `spec/schema.yaml` and
  `adapters/typescript/src` likewise; only `adapters/python/src/pact_adapters/ir.py`
  differed, which is that session's file and no part of this issue.
* The same full pytest run **inside the snapshot** had one failure:
  `test_the_headline_test_count_is_the_count.py::test_the_headline_test_count_on_the_front_page_is_the_number_the_suites_run`,
  the shared counter that compares README's headline against the suite's size. It
  passes in the working tree — measured, README says `2750 tests (909 Rust +
  1841 adapter)` and the suite collects `1841` — so it was an artifact of copying
  the tree while another session was updating both halves of that number.

To reproduce the before-picture, in a copy of the tree and never in this one:

```
# in a snapshot, with a private CARGO_TARGET_DIR
sed -i 's/if (!amount.is_finite()/if false \&\& (!amount.is_finite()/' crates/pact-schema/src/lib.rs
cargo build -p pact-cli
cp -r examples/refund-desk /tmp/before
sed -i 's/cost-per-request-under: .*/cost-per-request-under: "NaN USD"/' /tmp/before/agents/refund-desk/limits.yaml
./target/debug/pact check /tmp/before      # OK — … loaded cleanly (498 settings).  exit=0
```

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md:854` — the `C9` row. It already recorded the
schema floor and the run-time guard on `limits.cost-per-request-under`
accurately; it named `learning.cycle-limits.per-month` for the **schema** half
only, which was the true state when it was written. It is extended in this pass
with three facts and nothing else is edited in that file:

* the run-time half reached only one of the two ceilings, with the measured
  before-picture (three cycles, 8/16/24 USD, `unmeasured=()`);
* the three `learning.py` edits and why that one is fail-closed where
  `Limits.__post_init__` is report-and-continue;
* the schema floor had **zero** cargo-run coverage (60 of 60 `pact-cli` targets
  green with the arm deleted) and now has
  `crates/pact-cli/tests/a_money_ceiling_that_could_never_hold_is_refused.rs`.

`docs/remediation/QUEUE.md` row 6 (`B3` · `money-has-no-floor`) is marked `done`
with this document in the Doc column. Nothing else in that file is changed.

The six items under [What remains open](#what-remains-open) are **not** in `C9`
and are not on the queue. Item 2 in particular deserves its own row: it is one
sentence — *when a defect is found in a comparison, both operands are in scope,
and every route into each operand is in scope* — and B3 fixed one operand on the
routes an author writes.

---

## What a reader should take from this

1. **A quantity type without a bottom will get one written per field, and then
   forgotten on the next field.** The floor belongs to the type. When the natural
   mechanism (`at-least:`) cannot express it, that is a reason to write it
   somewhere else, not a reason not to write it.
2. **A derived selection is not a derived check.** `money_fields` picked exactly
   the right fields for years and read half of each value. If a slot looks
   occupied, read what is in it.
3. **A green test whose name overclaims is worse than a missing test**, because it
   is where the audit stops. The name is the claim.
4. **"Which comparison is this ceiling made with" is a per-field question.** Two
   fields of one type, one `>=` and one `>`, and a zero means two different wrong
   things. Borrowing one field's justification for the other is how a code comment
   comes to be contradicted by the code one crate over.
5. **Both operands of a broken comparison are in scope.** This fix put a floor
   under the cap and left the meter, the price list, the resume and the sibling
   clock ceiling able to switch every ceiling off silently.
6. **Where fail-closed is declined, the decline is a recorded decision with a
   measured reason** — never a claim that the alternative was impossible.
