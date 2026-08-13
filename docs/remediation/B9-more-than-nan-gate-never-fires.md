# B9 — an approval gate whose figure was not a figure loaded cleanly, and the gate then meant something nobody wrote

**Severity: high** · **Status: fixed, in both languages, after the first fix was
found to be wrong in two directions** · **Register row: this corrects the closing
sentence of row `C9` in `docs/70-PRODUCTION-GAP-REGISTER.md:854` — see
[Register update](#register-update).**

`more-than:` is the figure on an approval rule above which a person is asked. It
decides whether somebody stands in front of money. Nothing checked that it was a
figure, and the runtime that reads it cannot complain — it returns a number or
nothing, never an error.

**The title in the queue is off by one word, and the word matters.** `more-than:
NaN USD` does not make the gate never fire; measured, it makes the gate fire on
*everything*, including a one-dollar refund. The sentence "a refund of any size
went out with nobody asked" is true of the same field written a *different* way —
`more-than: .50 USD`, read at run time as fifty dollars — which the first fix
could not have caught and which this pass found and closed.

---

### How to read the numbers below

Every figure names the command that produced it, run by me against this working
tree on this machine. Before-pictures are produced by applying one named edit,
running, and reverting; the file checksums after every revert are in
[The mutation](#the-mutation). Where a claim was **not** re-measured in this pass
it says so in the same sentence.

**Another session was writing this repository throughout.** Its work shows in the
full-suite figures and is called out where it does.

**Three unrelated things in this repository are called `B9`.** Queue `B9`
(`docs/remediation/QUEUE.md`, row 7) is this document. Gap-register `B9`
(`docs/93-GAPS.md:127`) is *"`allow-egress: []` + `endpoint:` + an upload
action"*. Fix-plan `B9` (`docs/95-FIX-PLAN.md:336`) is `reaches-outside:`. A
reader who greps `B9` will find the egress work first.

---

## What is wrong

The shipped worked example writes the field twice:

```
$ sed -n '26p;31p' examples/refund-desk/policies/approvals.yaml
      - { tool: payments/issue-refund, arg: amount, more-than: 200 USD }
      - { tool: payments/issue-refund, arg: amount, more-than: 500 USD }
```

The reproduction is one edit to line 26, then `pact check`. Verbatim, against the
binary this tree builds (`cargo build -p pact-cli`), with the figure that
**produced these lines before the fixes landed** taken from the module's own
recorded measurement at `crates/pact-loader/src/money.rs:295-301` and the
`_amount` column re-measured by me today against the pre-repair regex:

| written into line 26 | `pact check` **before** | `questions._amount` **before** | what the gate then did |
|---|---|---|---|
| `NaN USD` | `OK — … loaded cleanly (498 settings).` exit 0 | `None` | stopped **every** call, a 1 USD refund included |
| `.nan USD` | `OK — … loaded cleanly (498 settings).` exit 0 | `None` | stopped every call |
| `TBD USD` | `OK — … loaded cleanly (498 settings).` exit 0 | `None` | stopped every call |
| `<amount> USD` | `OK — … loaded cleanly (498 settings).` exit 0 | `None` | stopped every call |
| `NaN$ USD` | `OK — … loaded cleanly (498 settings).` exit 0 | `None` | stopped every call |
| `$.50` | `OK — … loaded cleanly (498 settings).` exit 0 | **`50.0`** | **a 40 USD refund went out unasked** |
| `.50 USD` | `OK — … loaded cleanly (498 settings).` exit 0 | **`50.0`** | **a 40 USD refund went out unasked** |
| `-.5 USD` | `OK — … loaded cleanly (498 settings).` exit 0 | **`+5.0`** | a gate written to stop *everything* stopped nothing under 5 USD |
| `1e5 USD` | `OK — … loaded cleanly (498 settings).` exit 0 | **`1.0`** | a 100,000 USD gate fired at one dollar |
| `float('nan')`, built in code | never seen by the checker | `nan` | **let a 999,999 USD refund past, silently** |

The `_amount` column, re-measured by me today by restoring the old regex
(`_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")`) into
`adapters/python/src/pact_adapters/questions.py:1289` and running:

```
$ cd adapters/python && uv run pytest tests/test_a_spend_cap_that_can_never_be_reached.py -q
FAILED tests/test_a_spend_cap_that_can_never_be_reached.py::test_every_threshold_the_checker_lets_through_is_read_back_as_what_was_written
1 failed, 9 passed in 1.18s
```

Here is the same set through the tree **as it now stands**, which is my own
measurement and the state a reader will find:

```
$ ./target/debug/pact check <copy of examples/refund-desk, line 26 rewritten>

### [NaN USD] exit=1
    error: this rule asks a person when `payments/issue-refund` is called, and
      `more-than: NaN USD` is not a figure at all — so the rule has no figure to
      hold a call against, and which calls it stops is nobody's decision.
      --> …/policies/approvals.yaml:26:64
       |
    26 |       - { tool: payments/issue-refund, arg: amount, more-than: NaN USD }
       |                                                                ^^^^^^^
      fix: Write the figure a person should be asked above, the way that argument
      is declared in the tool's `takes:` — `more-than: 200 USD` for an amount of
      money, `more-than: 80` for a score.
      rule: loader/threshold-is-not-a-figure

### [TBD USD] exit=1        rule: loader/threshold-is-not-a-figure
### [<amount> USD] exit=1   rule: loader/threshold-is-not-a-figure
### [NaN$] exit=1           rule: loader/threshold-is-not-a-figure
### [""] exit=1             rule: loader/threshold-is-not-a-figure
### ["≥5 USD"] exit=1       rule: loader/threshold-is-not-a-figure
### [.nan USD] exit=1       rule: loader/threshold-is-not-a-figure
### [1e400 USD] exit=1      "is a larger figure than this can keep track of"
### [NaN JPY] exit=1        rule: loader/threshold-is-not-a-figure   (one message)
### [200 NaN] exit=1        rule: loader/currency-nothing-can-price  (one message)

### [$.50] exit=0    ### [.50 USD] exit=0   ### [-.5 USD] exit=0
### [1e5 USD] exit=0 ### [0 USD] exit=0     ### [-5 USD] exit=0
```

and the reader on the other side, measured by me today:

```
$ cd adapters/python && uv run python -c "from pact_adapters import questions as q; …"
'$.50'    -> 0.5      '.50 USD' -> 0.5     '.5 USD'  -> 0.5
'.05 USD' -> 0.05     '-.5 USD' -> -0.5    '-5 USD'  -> -5.0
'1e5 USD' -> 100000.0 '1,500.00 USD' -> 1500.0       '+5 USD' -> 5.0
'NaN USD' -> None     'TBD USD' -> None    '<amount> USD' -> None
float('nan') -> None  float('inf') -> None
```

---

## Root cause

There are three defects here and they are three different classes. The first fix
addressed one of them.

### 1. The figure had no checker, because every figure-checker in this repository hangs off a type

`Ty::Money` buys a field three things: `coerce::number` refuses word-spelled
non-finites, `Schema::check_ceiling` refuses overflowed ones, and B3's
`Schema::check_floor` puts a bottom under money. **`more-than:` deliberately has
no type**, so it gets none of the three. The reason is written into the
specification itself:

```
$ sed -n '2058,2071p' spec/schema.yaml
      more-than:
        # `type: money` was right when money was the only thing a gate could
        # compare, and wrong the moment it was not. MEASURED: a lead score gated
        # with `more-than: 80` was told to "Write it like `0.05 USD`", and doing
        # what that said printed "OK — loaded cleanly" and then `pact waits`
        # showed a live thirty-minute human gate comparing a score to dollars.
        #
        # The shape cannot be stated HERE, because it is the shape of an argument
        # declared in another document — the tool's `takes:`. So the schema is
        # permissive and `crates/pact-loader/src/money.rs` holds the figure
        # against what the argument actually is, which is the only place that
        # knows both.
        type: text
        may-be-money: yes
```

That was the right call for authorability (it is A3's), and it silently opted the
field out of every figure guard the project has. Its only reader in the whole
Rust tree, `compared_in_the_shape_the_argument_has`
(`crates/pact-loader/src/money.rs:574`), asked whether the value *looked like*
money — a three-letter word or a leading `$` — and never asked whether the
characters in front of that word were a number.

**The class**, in the register's own words: *a mechanism is built, tested,
correct; nothing on the authored path ever builds one.* Here the guard exists
three times over in `pact-schema` and reaches this field zero times.

### 2. The run-time consequence is the opposite of the obvious one, and depends on how you spell it

`amount > NaN` is never evaluated, because the threshold never becomes a float.
`questions._amount` (`adapters/python/src/pact_adapters/questions.py:1301`) hunts
for digits and returns `None` when it finds none, and `_atom_stops` at
`questions.py:1254` answers `True` for a threshold it cannot read — **on
purpose**. Its own docstring argues the case: *a malformed `more-than:` is a
mistake, and refusing to ask because of one would turn a typo into a disabled
gate.* Measured by me today:

```
_atom_stops({'tool':'payments/issue-refund','arg':'amount','more-than':'NaN USD'},
            {'amount': '1 USD'})   ->  True
```

So the gate does not vanish. It swallows the figure and parks every refund for a
manager — a refund desk nobody keeps using, on a line that reads exactly like a
threshold. That is fail-CLOSED.

**But a genuine float `nan` lands on the other side of the same `if`.**
`_amount(float('nan'))` used to return `nan`, `nan > anything` is `False`, and
the gate silently never fired. Two spellings of one value, opposite behaviours,
and the float one is the fail-OPEN half. `.nan` in a YAML file is what PyYAML
turns into that float on the Python side, while `crates/pact-doc/src/yaml.rs`
deliberately keeps `.nan`/`.inf` as **text** so nothing downstream in Rust ever
holds a non-finite. That is the right decision and it is exactly why asking
Rust's `str::parse::<f64>` alone was not enough.

**The class**, sharper than the register's: *the checker parses an authored
scalar with the HOST language's grammar while the runtime consumes it with the
FILE FORMAT's, and the difference is the unchecked set.*

### 3. The reader misread three ordinary, valid spellings of a figure

```python
# adapters/python/src/pact_adapters/questions.py, before this pass
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")     # requires a digit BEFORE the dot
_GROUPING = str.maketrans("", "", ",_ ")     # strips the space FIRST
```

`'.50 USD'` becomes `'.50USD'`, and the first thing that matches is `50`. The
`-?` cannot start where it is not allowed to reach, so `-.5` matches `5` — a
**sign flip**. There is no exponent alternative, so `1e5` matches `1`.

Every one of those is a **valid figure**. No refusal in the loader could ever
have caught them, because there is nothing to refuse. `pact check` said "loaded
cleanly", `pact show` handed the adapters the line, and the gate meant something
else by a factor of 100. This is the fail-OPEN half and it is the one the issue's
title actually describes.

The eight lines above the regex record that this exact defect had already
happened once on this exact function and had been measured end to end —
`'1,500.00 USD'` read as **1.0** and slipped under a 200 USD approval threshold.
The comma spelling was fixed by stripping separators. The leading dot, the sign
and the exponent were never considered, on the same argument the model chooses.

---

## Why nothing caught it

**The test that should have caught it had the field in view and stepped over
it.** `crates/pact-schema/tests/a_spend_cap_is_an_amount_of_money_and_has_a_bottom.rs`
is B3's own coverage test, written to make this class of mistake impossible. Its
first half walks `spec.groups()` filtering `matches!(f.ty, Ty::Money)`, writes
`<field>: NaN USD` for each, and demands `schema/below-the-floor`; it then pins
`assert_eq!(typed, 2)`. `more-than:` is `type: text`, so the filter never selects
it and the count of 2 stayed right. **A type-driven enumeration cannot see a
field whose whole point is that it has no type** — the blind spot is the root
cause wearing a different hat.

**The Python side had a test-shaped alibi.** `_atom_stops` had *decided* what to
do about an unreadable threshold and reasoned about it in prose, so the port felt
covered. What that decision never covered is a threshold that IS readable and is
`nan`. The alibi held for the spelling the tests used and inverted for the
spelling YAML produces.

**The first landing's own test could not see any of what was still wrong**, and I
verified each of these by mutation in this pass:

* *It never witnessed the traversal.* The helper edited the **first**
  `more-than:` in the only policy file of the only fixture, so every loop the
  check walks was crossed exactly once at index 0.
* *Its only location assertion was the filename.* `said.contains("approvals.yaml:")`
  is satisfied by any span in that file, and the message quotes `more-than: NaN
  USD` from the format string rather than from the span.
* *Its decision test was a disjunction.* `assert!(ok || !said.contains(rule))`
  stays green if the document starts being refused under any *other* rule id.
* *The suppression it claimed to hold was unwitnessed.* Deleting the `continue`
  left all 76 `pact-loader` + `pact-cli` test binaries green, because the test
  used `NaN USD`, whose last word is a currency, so the shape check would have
  gone quiet one line later regardless.

**And the growth guard pinned the wrong dimension.**
`crates/pact-loader/src/currency.rs` asserts that the set of
`may_be_money && !Ty::Money` **field names** is exactly `{"more-than"}`. The
hazard it names in its own failure message was a hard-coded **path**. A second
place in the specification mounting `group:question-rule` adds no field name, so
the guard stays green while the defect reopens.

---

## The fix

Four source files. Nothing was deleted, weakened or skipped.

### `crates/pact-loader/src/money.rs:323` — `no_figure_in`, inverted

The first version asked *"is one of these words a spelling of a non-figure?"* and
knew four. The class behind four spellings is open. It now asks the positive
question:

```rust
pub(crate) fn no_figure_in(written: &str) -> Option<&'static str> {
    let slot = figure_slot(written);
    match slot.parse::<f64>() {
        Ok(n) if n.is_finite() => None,
        Ok(_) => Some(if slot.chars().any(|c| c.is_ascii_digit()) {
            "is a larger figure than this can keep track of"
        } else {
            "is not a figure at all"
        }),
        Err(_) => Some("is not a figure at all"),
    }
}
```

Two sentences and not one, because `1e400` and `NaN` are different mistakes: one
is a real figure past the end of counting, and a reader told it "is not a figure"
would go hunting a typo that is not there.

### `crates/pact-loader/src/money.rs:365` — `figure_slot`, the shared grammar

Takes off a currency code at either end (spaced or attached), a leading `$`, and
`,`/`_`/spaces — **the same strips `questions._GROUPING` makes**, so the checker
and the reader agree about what the figure *is*. Nothing else is stripped, which
is the point: what remains must be a whole number and nothing else. `TBD`,
`<amount>`, `NaN$` and `two hundred` all fail that.

It is counted in **characters**, not bytes, and `money.rs:389-394` says why: the
first draft of this line sliced at `len() - 3` and panicked `pact check` with
exit 101 on `more-than: ≥5 USD`. That is B4's defect — a checker that crashes
instead of speaking — reintroduced in the file that refuses figures.

### `crates/pact-loader/src/money.rs:546` — `every_gate`, a derivation and not a path

The walk was `policies -> ask-a-person -> when -> more-than` by hand. It is now a
recursive search for the **key** wherever it is written, and both `more-than:`
checks (`a_threshold_that_is_not_a_figure` at :476 and
`compared_in_the_shape_the_argument_has` at :574) go through it. There is no path
left to forget, which also makes the field-name guard in `currency.rs` the
correct dimension rather than a decoy.

### `crates/pact-loader/src/money.rs:695` — `add_a_currency_to`, a fix line that cannot manufacture the defect

`loader/compared-in-the-wrong-shape` built its advice by interpolating the
author's own token, so whatever was wrong with the token was inherited by the
line telling them how to fix it. Measured end to end: `more-than: NaN$` was
refused with ``fix: … like `NaN$ USD`.``, and doing exactly that printed
`OK — … loaded cleanly (498 settings)`. The proposal is now put **back through
the same grammar** and offered only if it survives and the author's token was
nothing but a figure; otherwise the diagnostic gives its literal example.

### `crates/pact-loader/src/currency.rs:224` and `:244` — one mistake gets one message

`more-than: 200 NaN` drew two errors from one token and they contradicted each
other: `loader/currency-nothing-can-price` offering to add a NAN row to
`models/catalog.yaml` (i.e. "NAN may be a currency you genuinely deal in"), beside
`loader/threshold-is-not-a-figure` saying the value contains no figure — when
`200` plainly is one. `has_a_figure_to_price` makes the currency check stay quiet
when there is no figure to price. Measured today: `200 NaN` gives the currency
error alone; `NaN JPY` gives the figure error alone.

### `adapters/python/src/pact_adapters/questions.py:1289` and `:1332` — the reader

```python
_NUMBER = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?")
...
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
```

The first line is the leading-dot, sign and exponent repair. The second puts the
guard **on the value** rather than on a reader, which is where B3's own record
says it belongs (`docs/70-PRODUCTION-GAP-REGISTER.md:854`, *"The guard is on the
VALUE, not on a reader"*), and makes the float spelling fail-closed like the text
one. `None` is the case `_atom_stops` already handles by stopping.

### `crates/pact-loader/src/money.rs:81` — the wiring, unchanged and load-bearing

```rust
a_threshold_that_is_not_a_figure(document, diags);
compared_in_the_shape_the_argument_has(document, diags);
```

in that order, per the comment above it at `money.rs:78-80`: *"this is not a
figure" is the more fundamental complaint and the shape check stays quiet about
anything this one has already spoken about. One mistake gets one message.* The
quieting is the `continue` at `money.rs:621`.

---

## Alternatives rejected

**Put a floor in the schema, as B3 did.** This is the house pattern for money and
it is the first place I looked. It cannot work: `Schema::check_floor` only sees
values that coerced to `Money`, and A3 made this field `type: text` on purpose.
`currency.rs` already asserts that `more-than` is the *sole* `may_be_money &&
!Ty::Money` field — i.e. the sole field the floor structurally cannot reach.
Confirmed from the other direction, measured: `cost-per-request-under: NaN USD`
is `schema/below-the-floor`; `more-than: NaN USD` was silent.

**Re-type `more-than:` as `money` and get the floor for free.** Undoes A3 and
breaks `more-than: 80` on a score argument, which
`crates/pact-cli/tests/a_gate_compares_two_things_of_one_kind.rs` holds. Rejected.

**Give it a floor rather than a figure check.** Wrong, and the landed code is
right to refuse it. `more-than: 0 USD` means "ask a person about every refund" —
a workspace being strict — and `-5 USD` is the same rule written oddly. **Nothing
ever runs out against a gate.** Measured today: `0 USD` and `-5 USD` both load
cleanly.

**Refuse the odd spellings in the loader instead of fixing the reader.**
`.50 USD` *is* a figure. Refusing it would make an ordinary, correct line
unwritable to hide a bug in a regular expression, and would leave the **argument**
side of the same comparison — the value the model chooses, read by the same
function — still misread. The Rust test now pins `$.50`, `.50 USD`, `-.5 USD`,
`1e5 USD`, `1,000 USD` and `+5 USD` as **loading**, so that cheaper answer is not
available.

**Fold this into `loader/compared-in-the-wrong-shape` rather than mint a rule
id.** Cheaper by one id and worse for the reader. Measured before the repair,
`more-than: .nan` produced exactly that message with ``fix: Write the figure the
way the argument is declared, like `.nan USD`.`` — advice to write the value the
check exists to refuse. The separation is the better call.

**Guard at run time in `questions.py` instead of at load time.** `_atom_stops`
already fails closed on purpose, and the author is not in that process. The whole
point is that the mistake is decidable where the author is. (The reader was
repaired *as well*, for the class the checker cannot reach.)

**Make `yaml::resolve_scalar` refuse `.nan`/`.inf` outright.** Tempting and
wrong: keeping them as text is C3's deliberate decision, and refusing them at the
parser would break `x-` fields that legitimately carry the words.

**A second hard-coded path for a second `group:question-rule` reference.** The
same defect one line later. The walk is a derivation instead.

---

## Blast radius

**Callers, upward.** `pact_loader::money::check` (`crates/pact-loader/src/money.rs:71`)
has exactly one production call site — `crates/pact-cli/src/main.rs:1636`, inside
`fn validate` (`main.rs:1396`). `validate` has six call sites, measured:

```
$ grep -n "validate(" crates/pact-cli/src/main.rs
2142: fn check              2212: fn check_in_context     2314: fn waits_cmd
2343: fn discover_cmd       2383: fn card_cmd             2431: fn show
```

So the refusal fires on all six commands, `pact show` included — the door every
adapter reads a document through. Measured: `pact show` over a tree with
`more-than: NaN USD` exits **1**, so the adapter door is closed for this class.
Two loader integration tests call `money::check` directly
(`crates/pact-loader/tests/an_action_that_only_looks_things_up.rs:31` and
`crates/pact-loader/tests/a_gate_written_in_one_line.rs:52`) and are unaffected.

**Callers, downward.** `no_figure_in` has three callers, all measured by grep:
`a_threshold_that_is_not_a_figure` (`money.rs:485`), the suppression `continue`
(`money.rs:621`), and `currency.rs:245` (`has_a_figure_to_price`, added by this
pass). `figure_slot` and `is_a_currency_code` are private to `money.rs`.

**Digest — not affected, measured.** `money::check(&Node, &mut Diagnostics)` takes
the document immutably and only pushes diagnostics.

```
$ ./target/debug/pact discover examples/refund-desk | grep digest
    "digest": "sha256:87cb01fce41246bb8add4dc2975daa101324b6087319fd8103adf618a855db66"
```

which is the same value the pre-repair binary produced. No authored document's
digest moves.

**Honesty channels — no new channel, and this time the reason is measured rather
than assumed.** The five channels (`unretrieved`, `unmetered`, `unenforced`,
`unwatched`, `never_reached`) are Python fields on `RunResult`. The earlier draft
of this analysis argued no channel was needed because the run-time failure was
"fail-CLOSED and loud". That was true of `'NaN USD'` and **false of a float
`nan`**, which was fail-open and silent — a lossy operation proceeding silently,
which FR-8.1.1 (`docs/30-FRD.md:204`, thesis T7) forbids. The repair closes the
asymmetry at the value rather than adding a channel to report it: both spellings
now return `None`, and `None` is the case `_atom_stops` already stops on. What
this does **not** do is report the stop; see [What remains open](#what-remains-open).

**Documents that used to load and now do not.** Every threshold with no readable
figure. **No document in this repository is affected** — measured, `grep -rn
"more-than" examples/` returns exactly two lines, both in
`examples/refund-desk/policies/approvals.yaml`, and both are `200 USD` / `500
USD`. Each newly-refused document already produced a gate that stopped every
call, so each was already broken and is now refused where it is written.

**Documents whose diagnostic changed but whose verdict did not.** `more-than: ""`
moves from `loader/compared-in-the-wrong-shape` to
`loader/threshold-is-not-a-figure`; `200 NaN` loses its second, contradictory
error; `NaN JPY` loses the currency error and keeps the figure one.

**Run-time behaviour that changed.** `_amount` returns a different number for
leading-dot, negative-leading-dot and exponent spellings — in every case **the
number the author wrote** instead of a wrong one — and returns `None` rather than
a non-finite float. Every change is strictly toward fail-closed.

**Second port — nothing to mirror, and correctly nothing there.** Measured:

```
$ grep -rn "more-than\|moreThan" adapters/typescript/src/
adapters/typescript/src/loops.ts:554:export const ANSWER_MORE_THAN_ONCE = "pact:loop/answer-more-than-once";
```

one unrelated hit, a loop-shape name. `§7.28` list B already records `policy:`
(`ask-a-person`) as unimplemented in the second port, so there is no threshold
reader there to diverge. The four-artifact rule is not engaged: no authored field
is added and nothing the second port reports changes.

**Counts — in sync, and I did not touch them.** Measured today:

```
$ cargo test --workspace 2>&1 | grep -E "^test result" | awk -F'[ ;]' '{s+=$4} END {print s}'
914
$ cd adapters/python && uv run pytest tests/ -q
1855 passed, 6 skipped in 129.40s
```

and the published figures already read 914 Rust / 1861 adapter
(`README.md:73`, `site-docs/index.md:50`, `site-docs/status/verified.md:15-16`,
`docs/90-REVIEW.md:83-84`); 1855 passed + 6 skipped = 1861 collected. A concurrent
session ran `scripts/sync-counts.sh` during this work. I did not run it and did
not edit those four files.

---

## The test

Two files, two languages, one guard. **Neither is sufficient alone**, and that is
the finding rather than a note: five of the mutations below turn only one of the
two red.

### `crates/pact-cli/tests/a_gate_whose_figure_is_not_a_figure_is_refused.rs` — 10 tests

**Through which door: the real binary, over a real tree.** `fn pact()` is
`Command::new(env!("CARGO_BIN_EXE_pact"))` (line 103), so cargo builds the CLI for
this target and it cannot go stale. `fn edited()` (line 112) copies the whole of
`examples/refund-desk` to a temp root, **asserts the fixture still contains the
string it is about to rewrite** (`"fixture drifted: {from:?} not in {file}"`), so a
drifting example fails loudly rather than silently testing nothing, then rewrites
one occurrence. `fn ran()` (line 138) runs `pact check <root>` and returns
`(exit_ok, stdout+stderr)`. **No seam anywhere**: no `Node` built by hand, no
direct call into `money::check`, no fixture invented for the test.

Three edit helpers, and the second and third exist because the first was the
blind spot: `gated_at` (:147) edits the **first** rule at line 26,
`gated_at_the_second_rule` (:164) the **second** at line 31, and
`gated_at_the_second_clause` (:179) adds a **second `when:` clause** at line 27.

| test | what it asserts |
|---|---|
| `a_threshold_spelled_like_a_number_and_not_one_is_refused_where_it_is_written` (:194) | `NaN USD`, `inf USD`, `-inf USD`: non-zero exit, the rule id, the message quoting what was written, the action named, **the caret at `approvals.yaml:26:64`** and the underline width — not merely the filename |
| `a_rule_that_is_not_the_first_one_is_walked_too` (:229) | the same, on rule 2 (`:31:64`) and on clause 2 (`:27:64`) |
| `the_spellings_yaml_itself_documents_are_refused_like_the_ones_rust_takes` (:273) | `.nan USD`, `.inf USD`, `-.inf USD`, `.NaN USD`, `$.nan` — the grammar `str::parse::<f64>` does not take |
| `a_threshold_that_is_no_kind_of_number_is_refused_like_the_ones_that_are` (:309) | the open class: `TBD USD`, `??? USD`, `abc USD`, `two hundred USD`, `<amount> USD`, `NaN$`, `NaN$ USD`, `""`, and four non-ASCII rows (`≥5 USD`, `€5`, `£200`, `２００ USD`) that are a **crash** regression |
| `the_fix_offered_is_a_line_a_person_who_is_not_a_programmer_can_type` (:361) | the fix line shows both spellings and contains none of `NaN`, `non-finite`, `IEEE`, `f64`, `float` |
| `a_fix_line_never_proposes_a_threshold_this_would_refuse` (:391) | **mechanical, not wording**: extracts the replacement the fix line actually proposes, substitutes it back into the file, re-runs the checker, and demands it loads and draws no figure error |
| `a_threshold_past_the_end_of_counting_is_not_told_it_is_not_a_figure` (:445) | `1e400 USD` gets the overflow sentence and **not** the not-a-figure one |
| `one_mistake_still_gets_one_message` (:467) | exactly one diagnostic for `NaN USD`, `.nan`, `200 NaN` and `NaN JPY` |
| `a_gate_that_stops_for_a_person_on_any_spend_at_all_is_left_alone` (:537) | `0 USD` and `-5 USD` load — **`assert!(ok)`, not a disjunction**; the seven previously-misread figures load; `80` draws the *shape* rule; and a positive control on `NaN USD` so deleting the check cannot leave the loops vacuously green |
| `a_second_route_to_the_same_field_is_walked_too` (:604) | via `PACT_SPEC` + `--unsafe-spec` over a **copy** of the specification carrying one extra mount of `group:question-rule` — no repository file touched |

### `adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py` — 10 tests

**Through which door: the same built binary, by subprocess, plus the real reader
function.**

* `test_a_threshold_a_person_is_asked_above_is_refused_for_a_different_reason`
  (:301) — subprocesses the built binary over its own `shutil.copytree`, asserts
  `loader/threshold-is-not-a-figure` is present **and** `schema/below-the-floor`
  is absent, pinning that a gate must not be told it is a ceiling.
* `test_a_threshold_nothing_can_read_stops_every_call_rather_than_none` (:348) —
  the run-time half through the real reader, so the issue is not argued from
  arithmetic.
* `test_every_threshold_the_checker_lets_through_is_read_back_as_what_was_written`
  (:383) — **the invariant no loader test can state**: *for every threshold the
  checker accepts, the figure the run holds is the figure the author wrote.*
  Thirteen rows, each asserted through `_amount`, each then driven through the
  real binary to prove the checker really does accept it, plus the two harms
  spelled out (`$.50` firing on a 40 USD refund; `-.5 USD` stopping at every
  amount including negative ones).
* `test_a_threshold_that_is_not_a_finite_number_reads_as_no_threshold_at_all`
  (:487) — the float door.

### `crates/pact-loader/src/currency.rs` `mod tests` — a growth guard, not a case

Asserts the money-typed field count, that the `may_be_money && !Ty::Money` set is
exactly `{"more-than"}` (`currency.rs:633-641`), and that no money-ish field
carries an `aliases:` entry (`currency.rs:656-666`) — because `money.rs` matches
the literal key, so an alias would be a legal spelling that turns the figure check
off. These fail on a **schema** change rather than on a document, which is the one
thing a document-driven test cannot do.

---

## The mutation

**Seven, all applied by me in this pass, run, and reverted.** Baseline before any
of them:

```
$ cargo test -p pact-cli --test a_gate_whose_figure_is_not_a_figure_is_refused
test result: ok. 10 passed; 0 failed
$ cd adapters/python && uv run pytest tests/test_a_spend_cap_that_can_never_be_reached.py -q
10 passed in 2.51s
```

| # | the exact edit | Rust | Python |
|---|---|---|---|
| 1 | `questions.py:1289` → `_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")` | **`ok. 10 passed`** — nothing | `FAILED … test_every_threshold_the_checker_lets_through_is_read_back_as_what_was_written`, `1 failed, 9 passed` |
| 2 | `questions.py:1332` → `return float(value)` (drop `math.isfinite`) | not re-run; no document can express a float `nan` | `FAILED … test_a_threshold_that_is_not_a_finite_number_reads_as_no_threshold_at_all`, `1 failed, 9 passed` |
| 3 | `money.rs:546` `every_gate` list arm → `items.iter().take(1)` | `FAILED. 9 passed; 1 failed` — `a_rule_that_is_not_the_first_one_is_walked_too` | — |
| 4 | `money.rs:323` `no_figure_in` → the four-spelling list the first round shipped | `FAILED. 8 passed; 2 failed` — `a_threshold_that_is_no_kind_of_number_…`, `one_mistake_still_gets_one_message` | — |
| 5 | `currency.rs:224` → suppression removed (`{ let _ = has_a_figure_to_price; true }`) | `FAILED. 9 passed; 1 failed` — `one_mistake_still_gets_one_message` | — |
| 6 | `money.rs:502` caret → `when.get("tool").map(\|t\| t.span.clone())` | `FAILED. 8 passed; 2 failed` — `a_threshold_spelled_like_a_number_…`, `a_rule_that_is_not_the_first_one_…` | — |
| 7 | `money.rs:704` `add_a_currency_to` guard → `if true` (echo the token blindly) | `FAILED. 9 passed; 1 failed` — `a_fix_line_never_proposes_a_threshold_this_would_refuse` | — |

**Mutation 1 is the whole argument for the Python test existing.** A
wrong-figure threshold is a *valid document*, so the checker's own suite is
structurally blind to it: the entire Rust test binary stayed at `10 passed` with
the reader misreading `.50 USD` as fifty dollars.

Every file was restored and the checksum checked back:

```
$ md5sum crates/pact-loader/src/money.rs crates/pact-loader/src/currency.rs \
         adapters/python/src/pact_adapters/questions.py
187392e3afc0be91ceb2353886ea16b9  crates/pact-loader/src/money.rs
518f529551b3b47ca3a944a8d2890d0c  crates/pact-loader/src/currency.rs
06a4cf298df7deebd61bf8a1cfba6068  adapters/python/src/pact_adapters/questions.py
$ cargo test -p pact-cli --test a_gate_whose_figure_is_not_a_figure_is_refused
test result: ok. 10 passed; 0 failed
```

**Three further mutations are recorded in the source's own prose and were NOT
re-performed by me in this pass.** They are named here as claims of the repair
pass, not as measurements of mine: (a) `every_gate(document, …)` narrowed back to
`every_gate(policies, …)`, which the source says turns
`a_second_route_to_the_same_field_is_walked_too` red; (b) `figure_slot`'s currency
strip returned to byte slicing, which the source says makes `pact check` exit 101
on `≥5 USD` and turns `a_threshold_that_is_no_kind_of_number_…` red; (c) an extra
`loader/threshold-below-the-floor` for any threshold parsing `<= 0.0`, which the
source says now turns `a_gate_that_stops_for_a_person_on_any_spend_at_all_is_left_alone`
red where it previously did not.

---

## Failure cases

| # | class | example | status |
|---|---|---|---|
| 1 | Rust's float grammar | `NaN USD`, `inf USD`, `-inf USD` | **covered by** `a_threshold_spelled_like_a_number_and_not_one_is_refused_where_it_is_written` and `test_a_threshold_a_person_is_asked_above_is_refused_for_a_different_reason` |
| 2 | YAML's own grammar | `.nan USD`, `.inf USD`, `-.inf USD`, `.NaN USD`, `$.nan` | **covered by** `the_spellings_yaml_itself_documents_are_refused_like_the_ones_rust_takes` |
| 3 | a real figure past the end of counting | `1e400 USD` | **covered by** `a_threshold_past_the_end_of_counting_is_not_told_it_is_not_a_figure` (asserts both halves: the overflow sentence present, the not-a-figure sentence absent) |
| 4 | a placeholder left behind mid-edit | `TBD USD`, `??? USD`, `abc USD`, `two hundred USD`, `<amount> USD` | **covered by** `a_threshold_that_is_no_kind_of_number_is_refused_like_the_ones_that_are` |
| 5 | manufactured by the tool's own advice | `NaN$` → `NaN$ USD` | **covered by** `a_fix_line_never_proposes_a_threshold_this_would_refuse` (mechanical round-trip) and by the `NaN$` / `NaN$ USD` rows of case 4 |
| 6 | empty | `""`, `''`, `"  "` | **covered by** the `("empty", "\"\"")` row of case 4 |
| 7 | wrong figure, right shape (**fail-open**) | `$.50`, `.50 USD`, `.05 USD` | **covered by** `test_every_threshold_the_checker_lets_through_is_read_back_as_what_was_written`; the loading half pinned by `a_gate_that_stops_for_a_person_on_any_spend_at_all_is_left_alone` |
| 8 | sign flip (**fail-open**) | `-.5 USD` | **covered by** the same two, plus the `-0.10/0.10/4/6 USD` stop assertions |
| 9 | exponent dropped (**fail-open**) | `1e5 USD` | **covered by** the same two |
| 10 | non-finite float, no document (**fail-open, silent**) | `float('nan')`, `float('inf')` | **covered by** `test_a_threshold_that_is_not_a_finite_number_reads_as_no_threshold_at_all` |
| 11 | not the first rule | `NaN USD` on rule 2 | **covered by** `a_rule_that_is_not_the_first_one_is_walked_too` (caret `31:64`) |
| 12 | not the first `when:` clause | `NaN USD` on clause 2 | **covered by** the same (caret `27:64`) |
| 13 | a second route to the field in the specification | `more-than:` mounted under `agent` | **covered by** `a_second_route_to_the_same_field_is_walked_too` (`PACT_SPEC` + `--unsafe-spec`) |
| 14 | two contradictory messages | `200 NaN` | **covered by** `one_mistake_still_gets_one_message`; measured today, currency error alone |
| 15 | two messages, both with something to say | `NaN JPY` | **covered by** the same; measured today, figure error alone |
| 16 | a legal strict gate | `0 USD`, `-5 USD` | **covered by** `a_gate_that_stops_for_a_person_on_any_spend_at_all_is_left_alone`, now `assert!(ok)` |
| 17 | not ASCII (**crash regression**) | `≥5 USD`, `€5`, `£200`, `２００ USD` | **covered by** the four non-ASCII rows of case 4 |
| 18 | a second `may-be-money` field appearing | — | **covered by** `currency.rs:633-641` (assertion, not document) |
| 19 | `more-than:` growing an alias | — | **covered by** `currency.rs:656-666` (assertion, not document) |
| 20 | a `when:` clause carrying `more-than:` and no `tool:` | — | **UNCOVERED.** `money.rs:490-500` handles it — the `about` prefix falls back to empty so the sentence still reads — but no test writes such a document. Reachable only on a document the schema is already refusing for the missing `tool:`, so it is a wording risk and not a correctness one |
| 21 | `$NaN` — Rust's spelling behind the dollar sign | — | **UNCOVERED as written.** The `$` strip is witnessed through `$.nan` in case 2, and `NaN$` in case 4, but no test writes `$NaN` itself |
| 22 | the coupling to `crates/pact-doc/src/yaml.rs`'s `&& f.is_finite()` guard | — | **UNCOVERED.** If that guard were dropped, `.nan` would resolve to `Value::Float(NaN)`, `figure.as_str()` would return `None` at `money.rs:482`, and this whole check would go **silent** for the YAML spellings. Nothing links the two files |
| 23 | a document handed to a harness in memory, never through `pact check`/`pact show` | `{'more-than': '.nan USD'}` built in code | **UNCOVERED, and out of scope.** Fail-CLOSED (every call parks), and it is queue item `B8` (`in-code-nan-cap`). Named because it is the one route the checker never sees |
| 24 | the **argument** side of the same comparison | `{'amount': 'about two hundred'}` | **UNCOVERED, and open.** See below — this one is fail-OPEN |
| 25 | a currency written in lower case | `more-than: 200 usd` | **UNCOVERED, and open.** See below |

---

## What remains open

Stated plainly, because none of it is fixed here.

**The `arg:` side of the comparison has no checker at all.** The threshold is now
held to being a figure; the value the *model* supplies is read by the same
`_amount` and can be anything. Measured by me today:

```
_amount('about two hundred')                              -> None
_atom_stops({… 'more-than': '200 USD'}, {'amount': 'about two hundred'}) -> False
```

The gate does **not** fire. That is a genuine fail-open path, on the side an
author cannot see and a checker cannot reach, and it is out of B9's scope — but
it is the same function and the same table, and it should be a queue row.

**`more-than: 200 usd` in lower case loads cleanly.** Measured: exit 0. `_amount`
reads `900 usd` as `900.0` and the gate fires correctly, so the consequence today
is benign; nothing checks that the author's currency is spelled the way the price
list spells it, which is a different issue from this one. Not touched.

**A gate whose threshold cannot be read still stops every call, silently.**
`_atom_stops` returns `True` and nothing appears on any report. That state is now
unreachable *from a document* — `pact check` refuses it at all six doors — but it
is reachable from a spec built in code, which is exactly the door B3 found for
`Limits`. There is no `unmetered`-style honesty channel for approval gates. Not
built here: a channel is a design, not a line.

**`questions._amount` and `money::figure_slot` are two grammars held together by a
test, not by a shared definition.** The test is the right one — *every threshold
the checker accepts is read back as the figure that was written* — but it
enumerates thirteen spellings rather than deriving them. A spelling neither file
has thought of can still disagree, and the failure mode is a document that loads
and a figure read as a *different valid number*, which is the fail-open class.
Closing this properly means one reader, which means the loader and the adapter
sharing code they do not share today.

**Failure cases 20, 21 and 22 above are UNCOVERED** and are not repaired here.
Case 22 is the sharpest of the three: a change in a different crate would turn
this check silent and no single test would go red.

---

## Verification

All run by me, in this working tree, after every mutation was reverted.

```
$ cargo build -p pact-cli
    Finished `dev` profile

$ cargo test -p pact-cli --test a_gate_whose_figure_is_not_a_figure_is_refused
test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out

$ cd adapters/python && uv run pytest tests/test_a_spend_cap_that_can_never_be_reached.py -q
10 passed in 2.51s

$ cargo clippy --all-targets -- -D warnings
    Finished `dev` profile        (exit 0)

$ cargo test --workspace 2>&1 | grep -E "^test result" | awk -F'[ ;]' '{s+=$4} END {print s}'
914
$ cargo test --workspace 2>&1 | grep failed | grep -v "0 failed"
(no output)

$ cd adapters/python && uv run pytest tests/ -q
1855 passed, 6 skipped in 129.40s (0:02:09)
```

The full adapter suite was green on the single run I made of it. That is worth
qualifying rather than boasting about: the repair pass that landed this change
reported three consecutive runs with **8, 2 and 4** failures in **disjoint** sets,
every one passing alone, none reading `questions._amount`, `money.rs` or
`currency.rs` — another session was editing `adapters/python/src` and
`adapters/typescript/src` throughout. The disjointness is the evidence that they
were not this change: a defect here would fail the same test every time.

**Repository state after this pass.** No source file was left modified by me:

```
$ md5sum crates/pact-loader/src/money.rs crates/pact-loader/src/currency.rs \
         adapters/python/src/pact_adapters/questions.py \
         crates/pact-cli/tests/a_gate_whose_figure_is_not_a_figure_is_refused.rs
187392e3afc0be91ceb2353886ea16b9  crates/pact-loader/src/money.rs
518f529551b3b47ca3a944a8d2890d0c  crates/pact-loader/src/currency.rs
06a4cf298df7deebd61bf8a1cfba6068  adapters/python/src/pact_adapters/questions.py
af0256499327293f06cffc3c938c34f1  crates/pact-cli/tests/a_gate_whose_figure_is_not_a_figure_is_refused.rs
```

---

## What this change damaged

Reported because it is churn in files this issue did not need, and because it
happened.

The repair pass ran `cargo fmt -p pact-loader -p pact-cli`. **This repository is
not rustfmt-formatted** — there is no `rustfmt.toml` anywhere in it, and
`scripts/test-all.sh` runs clippy but never `cargo fmt --check` — so 96 files were
reformatted. 67 were verified to differ from `HEAD` by nothing but that formatting
and were restored exactly with `git checkout`. **12 tracked files and 15 untracked
ones could not be restored**, because they carry another session's uncommitted
work:

```
crates/pact-cli/src/discover.rs      crates/pact-loader/src/bundles.rs
crates/pact-cli/src/egress.rs        crates/pact-loader/src/lib.rs
crates/pact-cli/src/main.rs          crates/pact-loader/src/policy.rs
crates/pact-cli/tests/a_ceiling_in_money_nothing_can_price.rs
crates/pact-cli/tests/a_duration_means_what_the_help_says.rs
crates/pact-cli/tests/discovery.rs   crates/pact-loader/src/report.rs
crates/pact-cli/tests/one_grant_names_one_role.rs
crates/pact-cli/tests/the_subset_the_second_port_runs.rs
```

plus 15 untracked test files under `crates/pact-cli/tests/` and
`crates/pact-loader/tests/`. The change to all 27 is **layout only** — no
statement, name, string or assertion altered, and the full workspace suite is
green — but it should not have happened, and the lesson is the one-line rule: do
not run a formatter in a repository that does not enforce one.

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md:854`, row `C9`, closing sentence. It currently
reads:

> **A third money field is deliberately NOT in this row:** `more-than:` on an
> approval gate is a gate and not a ceiling, so `more-than: 0 USD` ("ask about
> every refund") stays legal; a non-finite one does not, and is refused by
> `loader/threshold-is-not-a-figure` in `crates/pact-loader/src/money.rs` — the
> schema cannot see it, because A3 made the field `type: text` so a score could
> be gated by a score

Two things in that are now wrong. *"a non-finite one"* understates the check:
`loader/threshold-is-not-a-figure` refuses **any** threshold with no readable
figure, which is the class rather than the four spellings the first landing knew.
And the sentence stops at the checker, when the worse half of the defect was in
the reader and is fixed in `questions.py`. Replace it with:

> **A third money field is deliberately NOT in this row:** `more-than:` on an
> approval gate is a gate and not a ceiling, so `more-than: 0 USD` ("ask about
> every refund") and `-5 USD` stay legal — nothing runs out against a gate.
> A threshold with **no readable figure in it** does not: `loader/threshold-is-not-a-figure`
> in `crates/pact-loader/src/money.rs` refuses the class, not a list of spellings,
> and the schema cannot reach it at all because A3 made the field `type: text` so
> a score could be gated by a score. **The worse half was in the reader and not
> in the checker**, and no refusal could have caught it: `more-than: .50 USD`
> loaded cleanly through `pact check` *and* `pact show` while
> `questions._amount` read it as **50.0**, so a 40 USD refund went out with
> nobody asked — the same harm, off by 100x, on a valid document;
> `-.5 USD` read back as **+5.0**, flipping the sign of a gate written to stop
> everything; and a float `nan` from a spec built in code made `_atom_stops`
> return `False` for a 999,999 USD refund with no report entry, which is the
> FR-8.1.1 breach this row's own standard names. Fixed at the value
> (`questions._amount` returns `None` for a non-finite) and in the grammar
> (`_NUMBER` takes a leading dot, a sign and an exponent), and held across both
> languages by the invariant *every threshold the checker accepts is read back as
> the figure that was written*
> (`adapters/python/tests/test_a_spend_cap_that_can_never_be_reached.py`). Full
> record: `docs/remediation/B9-more-than-nan-gate-never-fires.md`

**No new register row is needed** for B9 itself: C9 is the row that owns
"a ceiling the author was told they had", and this is its gate-shaped sibling
already cross-referenced there. Two things found in this pass **do** want queue
rows and do not have them — the unchecked `arg:` side of the comparison (failure
case 24, fail-open) and the lower-case currency (case 25).

---

## What a reader should take from this

**A refusal that enumerates spellings is a refusal that has not been written
yet.** `loader/threshold-is-not-a-figure` named a class in its own sentence and
enforced a list of four. The gap between the two was `TBD USD` — what an author
actually leaves behind mid-edit — plus `<amount> USD`, which the tool itself types
for them one diagnostic over.

**A diagnostic that echoes the author's token inherits whatever is wrong with
it.** The shortest path from "refused" to "loaded cleanly with the same defect"
was doing exactly what the tool said.

**A loader test that asserts a document loads cannot see a gate that loads and
then means something else.** The 100x error and the sign flip lived on documents
that were valid, in a function no Rust test can call. Two ports, two grammars, one
invariant — and the invariant has to be written down on the side that can measure
it.
