# C10 — a figure too big for the machine to hold was called a typo, and the rule written to stop that asked how the figure was punctuated instead of how big it was

**Severity: high.** · **Status: closed at both doors, at both ends of the number
line and at all six typed fields. Four residuals remain and are named, with
measurements, in [What remains open](#what-remains-open).** · **Register:
`docs/70-PRODUCTION-GAP-REGISTER.md:855`, the `C10` row** (already rewritten;
the one addition still owed is given in [Register update](#register-update)). ·
Queue row: `docs/remediation/QUEUE.md` row 15.

**How to read the numbers in this document.** Every figure below names the
command that produced it. Everything was run on 2026-08-09 against this working
tree, whose three changed source files were, at the time of measurement:

```
$ sha1sum crates/pact-doc/src/yaml.rs crates/pact-schema/src/coerce.rs crates/pact-schema/src/lib.rs
c7301aa730ffefd320cc009e8c5ac03ee5db8ef9  crates/pact-doc/src/yaml.rs
bd0ddfd89b6fc6ebea9d2f2f52b276c83485800a  crates/pact-schema/src/coerce.rs
0ac9ef785245a35826b25e71f1e28810ad558dd9  crates/pact-schema/src/lib.rs
```

Another session is working in this repository at the same time, so every
*deliberately broken* build in this document was made in a byte-identical copy
of the tree (`scratchpad/repo`, built into its own target directory), never in
the real one. The three files above carry the same checksums now as they did
before the first break. The real tree was never edited by this pass.

Where a "before" picture is quoted, the document says which break produced it
and whether I produced it myself or am reporting a measurement somebody else
recorded. Digests come from the fixture described in
[Reproduction](#reproduction); a different fixture gives different hashes, so
what matters about a digest claim is whether two hashes are the **same** or
**different**, never the literal value.

---

## What is wrong

An author writes a figure. The machine cannot hold it. There are exactly two
honest things to do, and PACT was doing a third.

* **Keep it.** Where nothing reads the value — an `x-` field, which is the
  author's own namespace — the text they wrote is what comes back out. Nothing
  is lost, and two documents that differ still get different digests. That is
  AC-1.3.
* **Name it.** Where the specification says a figure is wanted, refuse the line
  where it was written and say what is wrong with the **figure**.
* **The third answer, which is the defect.** *"'temperature' should be a number,
  but it is some text."* That is a typo's sentence, said about a line spelled
  exactly the way a number is spelled, with the fix *"Change it to a number"* —
  an instruction to do the thing the author already did. It is a dead end: it
  points at no edit that helps. This repository condemns that sentence, and its
  near relative *"should be a whole number, but it is a number"*, in seven
  places in its own source (`crates/pact-schema/src/coerce.rs:94`, `:330`,
  `:339`, `:405`, `:452`, `:635`, `:726`) — and was still shipping both.

One round closed the exponent spelling (`1e999`). A second closed the plain
digit-run spelling (`99999999999999999999`) with a rule about **how the figure
is punctuated** — *"an optional sign, then ASCII digits, that `i64` cannot
parse"*. That rule is what this document is mostly about, because a rule about
punctuation cannot answer a question about a figure. It was one character wide,
it left four more doors printing the condemned sentence, and it made the checker
contradict itself about single values.

### Reproduction

The fixture is a two-file workspace. `workspace.yaml` says `name: desk-shop`
and `description: A workspace.`; `agents/desk/agent.yaml` says `name: Desk`,
`description: A desk.`, `instructions: Do it.` and then the one line under test.
The commands are the shipped binary: `pact check`, `pact show`, `pact discover`.

**1 — the digest collapse the whole issue exists to delete was still live, one
character away.** Measured by me, in the isolated copy, with mutation **G**
applied (which puts the punctuation rule back exactly as the previous round
shipped it) and the rest of the fix in place:

```text
x-big: 99999999999999999999.0   -> sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888
x-big: 99999999999999999998.0   -> sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888
x-big: 100000000000000000000.0  -> sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888

$ pact show      # x-big: 99999999999999999999.0
      "x-big": 1e+20
```

Three different documents, one hash. A lockfile that pins that hash cannot tell
them apart, and `pact show` hands the runtime a figure nobody wrote. That is the
same harm, byte for byte the same hash, that the earlier round had recorded as
its own *before* picture — restored by adding a `.` and a `0`.

The same three lines through today's binary, and the round-trip beside them:

```text
x-big: 99999999999999999999.0   -> sha256:e2e11e9fc204e3be182a9555f43b41c044457189cc96089cd632cf5395ae85f5
x-big: 99999999999999999998.0   -> sha256:2254e680a8c7fe090d47ddf71f039e91aebc8a4107616d58f3084c8768313154
x-big: 100000000000000000000.0  -> sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888

$ pact show      # x-big: 99999999999999999999.0
      "x-big": "99999999999999999999.0"
```

**2 — one value, two opposite verdicts.** The ceiling asked
`text.parse::<i64>()`, so the answer depended on notation. This is the
adversarial review's measurement against the tree as it stood then; I did not
re-create it, because the mutation that would restore it (**F**) is one of the
seven I did not re-run:

```text
settings: temperature: 1e19                  -> OK — loaded cleanly (10 settings)
settings: temperature: 10000000000000000000  -> error: … is more than this can keep track of.
                                                rule: schema/too-big-to-count
```

`1e19` and `10000000000000000000` are the same double to the last bit
(`python3 -c "print(float('1e19') == float('10000000000000000000'))"` → `True`),
so the first line proves the second line's sentence false. `coerce::size` had
the mirror, and the punctuation rule is what created it: `context-at-least:
1e19` was *"should be a size … but it is a number"* while `context-at-least:
10000000000000000000` loaded cleanly, as a context window no model on earth can
meet. Today, measured by me, both spellings give one answer on both fields:

```text
$ pact check   # settings: temperature: 1e19
error: 'temperature' is 10000000000000000000, which is more than this can keep track of.
  rule: schema/too-big-to-count
$ pact check   # settings: temperature: 10000000000000000000
error: 'temperature' is 10000000000000000000, which is more than this can keep track of.
  rule: schema/too-big-to-count
$ pact check   # needs: context-at-least: 1e19   /   10000000000000000000
error: 'context-at-least' is 10000000000000000000, which is more than this can keep track of.
  rule: schema/too-big-to-count      (both spellings, identical report)
```

**3 — the condemned sentence, still shipped, at three more doors.** Each of
these I produced myself, in the isolated copy, by putting back the one thing the
repair changed at that door.

*A length of time carrying the very unit the help asks for* (mutation **J**:
the parse loop reads the `e` of `1e999s` as the first letter of a unit called
`e`):

```text
finishes-within: 1e999s        -> error: 'finishes-within' should be a length of time,
finishes-within: 1e300h           like `2s`, `500ms` or `5 minutes`, but it is some text.
finishes-within: 1e999 seconds    rule: schema/wrong-type
finishes-within: 1e400 ms
finishes-within: 1e6s          -> the same sentence, about one million seconds
```

*A whole number written with an exponent or a point* (the `Value::Float` arm
removed from `Ty::Integer`'s dispatch, `coerce.rs:259`):

```text
$ pact check   # limits: tokens-at-most: 1e6
error: 'tokens-at-most' should be a whole number, but it is a number.
  fix: Change it to a whole number.
  rule: schema/wrong-type
```

One million is a whole number. The sentence denies what the author wrote and the
fix restates it. Identical output for `1000000.0` and for `1e19`.

*A share of the whole, at the top end only.* The review measured
`when-full: 1e999%` as *"should be a percentage, like `90%`, but it is some
text"* while `1e-999%`, closed one round earlier, was named properly. I could
not reproduce that exact sentence, because the coercer has since gained a third
answer; what I measured under mutation **L** (the ceiling arm disabled) is the
other failure the same hole allows — silence:

```text
when-full: 1e999%    -> OK — rd2 loaded cleanly (498 settings).
when-full: -1e999%   -> OK — rd2 loaded cleanly (498 settings).
when-full: 1e-999%   -> error: … is closer to zero than this can keep track of.
```

Today, all three are named, and the two ends read differently on purpose:

```text
when-full: 1e999%    -> error: 'when-full' is 1e999%, which is more than this can keep track of.
when-full: -1e999%   -> error: 'when-full' is -1e999%, which is further below zero than this can keep track of.
when-full: 1e-999%   -> error: 'when-full' is 1e-999%, which is closer to zero than this can keep track of.
when-full: 85%       -> OK — rd2 loaded cleanly (498 settings).
```

**4 — the fix line itself was false, and the test only checked it was there.**
The review measured `temperature: 1e999` refused with *"fix: Write
`temperature: 10`, or any smaller number, or remove the line."* and then
`temperature: 9223372036854775808` — a smaller number, written in obedience to
that advice — refused by the identical rule, while `1e19`, which is larger,
loaded. I did not re-create this: the sentence no longer exists to be measured.
Today the same line reads:

```text
$ pact check   # settings: temperature: 1e999
error: 'temperature' is 1e999, which is more than this can keep track of.
  fix: Write `temperature: 10`, or any figure of fifteen digits or fewer, or remove the line.
  rule: schema/too-big-to-count
```

---

## Root cause

**One question was being asked in two places, and in both places it was a
question about spelling rather than about size.**

Two layers have to decide whether a figure survived being read: the document
layer (`pact_doc::yaml::resolve_scalar`, `crates/pact-doc/src/yaml.rs:725`),
which decides whether a scalar becomes a number or stays the author's text, and
the schema layer (`Schema::check_ceiling`,
`crates/pact-schema/src/lib.rs:1789`), which decides whether a figure a field
was given is one the field can hold. Both had ended up asking *"is this text a
run of ASCII digits that `i64` refuses?"* That question has three defects, and
no amount of care at the call sites could have removed any of them:

1. **A `.` or an `e` walks straight past it.** `99999999999999999999.0` is the
   same figure as `99999999999999999999` and is not a run of digits.
2. **It is a question about `i64`, and the value is a double.** `1e19` is
   exactly representable as a double; `parse::<i64>()` refuses
   `10000000000000000000`. One value, two answers, and the refusal sentence —
   *"more than this can keep track of"* — was false about a figure the checker
   demonstrably kept track of one line earlier.
3. **It cannot be said to an author.** *"More than this can keep track of"* is a
   claim about where a machine stops telling one figure from the next. For a
   field read as a double, `i64` is simply not that place.

Underneath sits the floating-point fact the original coercers were written
without: `"1e999".parse::<f64>()` does not fail — it succeeds and returns
infinity — and `"99999999999999999999".parse::<f64>()` succeeds and returns a
perfectly **finite** `1e20`. So an `is_finite` guard can see the first and is
blind to the second by construction.

**The class this belongs to, which is what makes the siblings findable.** At the
first round's HEAD, every coercer returned `Option<Coerced>`, so `None` had to
carry two different meanings — *"this is not that kind of thing"* and *"this is
that kind of thing and I cannot hold it"* — and `wrong_type` could only ever
print the first. The error channel was lossy at the type level. The remaining
false sentences are the same shape one level down: each type had its own
hand-written test for *"is this a figure or a word"*, and four of those tests
were about spelling too. `coerce::duration`'s parse loop read the `e` of
`1e999s` as a unit; `Ty::Integer` and `Ty::Size` accepted a string and an
integer but not a float, so a figure the document layer had deliberately held
fell out of a `_ => None`; `coerce::percent` filtered through `(0.0..=1.0)` and
had no third answer at all.

So the class is: **a total-looking coercer whose `None` is overloaded, plus a
`match` on the value that omits one legal spelling, so a correctly written
figure never reaches its own parser.**

---

## Why nothing caught it

* **The test asserted the fix string was present, never that it was true.** The
  guards on the message were `text.contains("fix: Write `temperature: 10`, or
  any smaller number, or remove the line.")` in three places. A test that pins
  the seam (a fix exists) rather than the claim (the fix is the right one)
  cannot go red when the sentence becomes false. This file's own header had
  diagnosed exactly that blind spot in another test
  (`crates/pact-cli/tests/check_reports_real_mistakes.rs:63`) and then
  reproduced it.
* **The mutation record was stale by two rounds.** It recorded `6 passed; 3
  failed` for mutation A against a file that had grown from nine tests to
  fifteen. Re-measured on the shipped file, the same edit gave `10 passed; 5
  failed`. Arithmetic in a record that does not reproduce is the same defect the
  file condemns in a diagnostic, and it is why every count in this document was
  re-run.
* **One of the five word-guards was pinned by nothing at all.** Deleting `&&
  crate::has_a_digit(&s)` from `coerce::duration`'s bare-infinity special case
  left the C10 test file at 15/15, the whole of `pact-cli` green under
  `--no-fail-fast` and the whole of `pact-schema` green — while the binary told
  the author of `finishes-within: inf` that their line was *"a longer time than
  this can keep track of"*, which is the opposite of what the file's own header
  says must happen to a word.
* **No test in the repository wrote the spellings that broke.** `grep -rn
  "finishes-within: inf" crates/ adapters/ spec/ examples/` returned nothing;
  `grep -rnE "1e[0-9]+ ?(s|ms|m|h|d|seconds|minutes|hours|days)\b" crates/
  adapters/ tests/ spec/` returned a single hit, and it was a **size** test.
* **The structural answer, which is the honest one.** Until `Coerced` gained a
  third kind of answer, no test written against that signature could have
  expressed the failure. The blind spot was in the type, and every test
  inherited it.

---

## The fix

Two questions, asked once each, about the **figure**. Line numbers were read
today out of the files whose checksums are at the top of this document.

### 1. The document layer: does the whole number this text spells survive?

`pact_doc::whole_number_written` (`crates/pact-doc/src/yaml.rs:933`) reduces a
literal to the plain digits of the whole number it spells — `1e10` →
`10000000000`, `2.50e1` → `25`, `99999999999999999999.0` → twenty nines — and
returns nothing for a literal that spells no whole number.
`whole_number_past_holding` (`:995`) reads the literal as a double, writes the
double back out, and compares. If the digits differ, the machine cannot hold
what was written, and `resolve_scalar` keeps the author's text instead of a
number (`:805`). The non-finite half is a separate arm (`:876`, the `&&
f.is_finite()` on the float branch), because a figure that could not be read at
all is a different case and two rules must not own one line.

```text
99999999999999999999      the double writes 100000000000000000000    -> kept as text
99999999999999999999.0    the same                                   -> kept as text
9223372036854775808       the double writes 9223372036854776000      -> kept as text
1e10, 1e20, 10000000000000000000, 1.5e30   write back exactly        -> stay numbers
1.5, 0.7                  spell no whole number                      -> not this rule's
```

### 2. The schema layer: 2^53, the last whole number a double can tell apart

`coerce::PAST_COUNTING` (`crates/pact-schema/src/coerce.rs:156`) is
`9_007_199_254_740_992.0`, and `past_counting_figure` (`:166`) is
`!v.is_finite() || v.abs() >= PAST_COUNTING`. That is precisely what *"more than
this can keep track of"* has always claimed. It is asked by `Ty::Number`
(`lib.rs:1877`), `Ty::Threshold` (`lib.rs:1909`) and `Ty::Size`
(`coerce.rs:761`), so one figure gets one answer whichever field and whichever
spelling it arrives in. It is **smaller** than the `i64` bound it replaced, so
nothing that used to be refused is accepted now. `Ty::Integer` keeps `i64`
(`coerce.rs:384`), because there the machine really is an `i64` and
`tool-calls-at-most: 9223372036854775807` is a whole number it holds exactly —
measured: that line loads, and `9223372036854775808` does not.

### 3. The four doors that were still calling a figure a word

| door | the edit | file:line |
|---|---|---|
| a length of time with an exponent **and** a unit | the parse loop reads an exponent as part of the figure instead of as a unit's first letter | `coerce.rs:585` (`is_exponent_at`), used at `:546` |
| a bare figure no unit could have saved | `Value::Float(f) if *f >= u64::MAX as f64` → `DurationTooLong` — past the milliseconds this counts in, the missing unit is not what is wrong with the line | `coerce.rs:278` |
| a whole number written `1e6` or `1000000.0` | `Ty::Integer` reads a float by writing it back out and reading the whole number it spells | `coerce.rs:259`, `integer` at `:346-388` |
| a size the document layer held as a number | `Ty::Size` reads a float the same way | `coerce.rs:692-697` |
| a share past holding | new answer `Coerced::PercentPastHolding` | `coerce.rs:45`, `:658`, ceiling arm `lib.rs:1970` |

`coerce::duration`'s hand-written bare-infinity special case is **gone**. With
the exponent read as part of the figure, `1e999` overflows in the ordinary way
like every other length of time, and `inf`, `nan` and `Infinity` are strings
with no figure in them that the loop already refuses. One fewer hand-written
word test to leave unpinned.

### 4. The sentence, and the fix line

`as_written(node)` (`lib.rs:2759`) gives the message a figure to quote when the
node is not text — the ceiling now refuses floats as well, and asking a float
for its string gives nothing, which would have left an empty space where the
value goes. Past twenty-one characters it uses the exponent form, because
`1e308` written out is a paragraph of zeros in the middle of a sentence.

`HELD` (`lib.rs:2964`) is the string **"any figure of fifteen digits or
fewer"**, and it replaced *"any smaller number"* / *"any shorter length of
time"* / *"any smaller amount"* on the three types that print a set. Every whole
number under 10^15 is inside 2^53 and inside `i64`, so a reader who follows the
sentence lands somewhere every one of these fields accepts. *"Any smaller
number"* cannot be made true by any choice of bound: the refused set is
`|v| ≥ bound`, so for any refused figure there are smaller figures that are also
refused.

`past_counting` (`lib.rs:2966`) is one function rather than two match arms, on
purpose, so that a number and a comparison against a number cannot drift into
two sentences about one figure. It gives the top of the scale *"more than this
can keep track of"* and the bottom *"further below zero than this can keep track
of"*, because an author told that `-1e999` is *"more than"* anything would go
looking for a smaller number and find the one they had already written.

`kind_as_written` (`lib.rs:2771`) is the residual repair: for the cases that
still, rightly, fall through to `schema/wrong-type`, a string carrying a digit
that parses as a figure is described as *"a whole number"* or *"a number"* and
not as *"some text"*. Measured today: `context-at-least: -99999999999999999999`
→ *"but it is a whole number"*, `-1e999` → *"but it is a number"*, `-inf` →
*"but it is some text"*.

### 5. Both other ports moved with the duration change

`coerce::duration`'s own note says the Rust side and the reader side are
deliberately different sets, and that the difference runs one way only: the Rust
side is stricter, so nothing it lets through may be unreadable at the far end.
Teaching the Rust loop about exponents without teaching the readers would have
opened exactly that gap — `pact check` saying `OK` about `finishes-within: 1e6s`
while the reader answered "no ceiling". So the same rule was written into
`adapters/python/src/pact_adapters/limits.py:829` (`_exponent_at`) and
`adapters/typescript/src/limits.ts:536` (`exponentAt`). Measured today:

```
$ uv run python -c "from pact_adapters.limits import seconds; print(seconds('1e6s'), seconds('2.5e2 ms'), seconds('inf'))"
1000000.0 0.25 None
```

---

## Alternatives rejected

**"Only accept a literal that names its double exactly."** The obvious general
rule, and the one the review asked for. It refuses every ordinary decimal in the
format: `Decimal(float('0.1'))` is
`0.1000000000000000055511151231257827021181583404541015625` and
`Decimal(float('0.7'))` is `0.6999999999999999555910790149937383830547332763671875`,
so every temperature in every example becomes text. The line is drawn at **whole
numbers** because that is where "the figure that was written is the figure that
arrives" can be honoured without refusing arithmetic itself. What that leaves is
recorded in [What remains open](#what-remains-open) rather than hidden.

**"Only accept a float that round-trips its own text."** A weaker version of the
same thing, and it refuses `1e10`, which comes back `10000000000.0` — the same
number, reformatted, that nobody would call corrupted. Pinned in the opposite
direction by `ordinary_numbers_are_untouched`.

**Keep the `i64` yardstick and reword the sentence** (*"more digits than a whole
number here can hold"*). It leaves a number field bounded by an integer type it
never uses, and it still answers `1e19` and `10000000000000000000` differently
unless the test is made value-shaped anyway — at which point `i64` is a bound
with no meaning for a double.

**Saturate to `f64::MAX` / `i64::MAX` / `u64::MAX`.** This is the silent
degradation T7 and FR-8.1.1 forbid, and it is the measured before-picture:
`pact show` printing `1e+20` where twenty nines were written, `pact check` exit
0, three documents on one digest. Worse than the `null` it replaced, because
`1e20` looks like an answer.

**Refuse at the document layer** (a `doc/…` problem on `x-big: 1e999`). `x-` is
the author's own namespace and PACT does not read it; refusing would break
AC-1.3's round-trip promise in the other direction. Pinned by
`a_number_too_big_to_hold_is_not_a_problem_of_its_own`, which runs
`--deny-warnings` and requires exit 0 — measured today: `OK — loaded cleanly (9
settings)`, `rc=0`.

**Keep the text and stop there.** This *is* the dead end the issue is named for:
a value saved from being lost, and then a false sentence said about it.

**Bare figures on a duration field are seconds.** The review's first suggestion
for the `1e308` case. Two tests pin the opposite deliberately, with their
reasoning written out —
`crates/pact-cli/tests/a_duration_means_what_the_help_says.rs:191` and
`crates/pact-schema/tests/durations_say_what_they_accept.rs:144`: *"`90` is as
likely to mean ninety minutes as ninety seconds, and a ceiling out by sixty
times would be applied silently."* Accepting bare seconds means deleting those
assertions. The rule taken instead keeps both: the unit is required **because a
unit would settle the question** — which stops being true the moment the figure
is past holding even in milliseconds, the smallest unit there is. Measured
today: `finishes-within: 90` is still `schema/wrong-type`, and `1e308` is
`schema/too-long-to-count`.

**Fold `inf` and `nan` into the ceiling too.** Simpler code, one fewer guard, and
false: a word spelled where a figure goes never overflowed anything, and *"more
than this can keep track of"* is not true about it. Measured today: `temperature:
inf` → *"should be a number, but it is some text"*, `schema/wrong-type`.

**Leave `Ty::Size`'s ceiling at `u64::MAX`.** Then `context-at-least:
10000000000000000000` keeps loading as a requirement no model can meet. The
duration ceiling *does* stay at `u64::MAX`, and that is a different choice for a
stated reason: a length of time is counted in whole milliseconds in a `u64`, the
product is guarded before the cast.

---

## Blast radius

**Into the changed code.** `resolve_scalar` has exactly one production call
site, the scalar handler in the YAML reader, so every authoring door inherits
the change with no per-door work. Verified at the binary: the plain `agent.yaml`
door, the markdown door (`agent.md` front matter →
`error: 'temperature' is 1e999, which is more than this can keep track of.
--> W/agents/desk/agent.md:5:16`, `schema/too-big-to-count`), and scalars nested
in a list and a map (`x-list: [1e999, 99999999999999999999]` and `x-map:
{inner: 1e400}` come back out of `pact show` as those strings). `check_floor`
and `check_ceiling` have exactly one call site each, `lib.rs:1552-1553`.

**Out of the changed code.** `Coerced` is matched outside `pact-schema` in seven
places, all in `pact-loader`: `report.rs:1012` (`Duration`),
`teamwork.rs:423` (`Percent`), `approvals.rs:476` and `money.rs:761`, `:930`
(`YesNo`), `currency.rs:151`, `:208` (`Money`). Every one matches the single
variant it wants and falls through on anything else, so the new
`PercentPastHolding` cannot be read as a share by any of them — and a document
carrying one is refused by `check_ceiling` before any of them runs.
`cargo test --workspace` covers all of them and is green.

**What changed for documents that already loaded.** Three widenings and three
narrowings, all deliberate, all measured:

* *Widened.* `tokens-at-most: 1e6` and `1000000.0` now load. `context-at-least:
  1.28e5` now loads. `finishes-within: 1e6s` and `2.5e2 ms` now load, and both
  other ports read them.
* *Narrowed.* A figure at or past 2^53 on a number, a comparison or a size is
  now refused however it is spelled. `context-at-least: 0.5` written without
  quotes is now `schema/below-the-floor` — *"which is no tokens at all"* — where
  it used to load as a context window of zero.
* *Digests.* `x-big: 10000000000000000000` moves from a quoted string to a
  number, because the double writes it back exactly.

**Digest stability for anything that ships: not affected, and this was checked
rather than assumed.** No authored document in the repository contains a scalar
this rule can reach:

```
$ grep -rnE '(^|[^0-9])[0-9]{16,}' --include=*.yaml --include=*.yml --include=*.md examples/ tests/ spec/ templates/ site-docs/
(no output)
$ grep -rnE ':[ ]+-?[0-9.]+[eE][+-]?[0-9]+' --include=*.yaml --include=*.yml examples/ tests/ spec/
(no output)
```

**The five honesty channels** — `unmetered`, `unenforced`, `unwatched`,
`never_reached`, `unretrieved` (`adapters/python/src/pact_adapters/harness.py`,
fields at `:136`, `:168`, `:173`, `:178`). **Not affected, and none is owed.**
Where the specification wants a figure and the figure will not fit, the document
is refused with exit 1 at the author's line and no run begins, so there is
nothing to report as unwatched. Where the specification does not read the value
(`x-`), the text survives intact, which is strictly more honest than the number
it used to be turned into.

**Both ports.** Neither adapter parses the author's YAML — they read the IR the
Rust loader emits — so the document-layer rule is Rust-only by construction. The
one place the two could have parted is the duration set, and they were moved
together (above), with
`test_every_length_of_time_the_checker_passes_is_read_here_the_same_way`
(`adapters/python/tests/test_what_the_author_wrote_reaches_the_run.py:963`)
driving `pact check` and `limits.seconds` over the same six spellings and
requiring both to agree. `npx tsc --noEmit` is clean.

**Counts.** `./scripts/sync-counts.sh` prints `rust=955 adapter=1962
total=2917` and writes those into four documents; `README.md:73` and
`site-docs/index.md:50` already read them, so the tree is in sync and this pass
changed no count.

---

## The test

`crates/pact-cli/tests/a_number_too_big_to_hold_is_kept_as_it_was_written.rs` —
**19 tests**, measured today:

```
$ cargo test -p pact-cli --test a_number_too_big_to_hold_is_kept_as_it_was_written
test result: ok. 19 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

**The door: the shipped binary, on real files.** Every one of the nineteen
spawns `Command::new(env!("CARGO_BIN_EXE_pact"))` (`:252-255`) against a
workspace written into the temp directory (`:257-273`), and reads `pact show`
(`:274`), `pact discover` (`:286`, taking the published `sha256:` a lockfile
would pin) and `pact check` (`:300`). The file calls no internal function
directly — not `resolve_scalar`, not `coerce::check`, not
`Schema::check_ceiling`. It is an effect test, not a seam test, which is why a
full revert of the change fails eleven of it rather than one.

| test | what it claims |
|---|---|
| `a_number_too_big_to_hold_survives_show` (`:312`) | `x-threshold: 1e999`, `x-note: 1e400`, `x-below: -1e999` come back out of `pact show` as those strings, and the output contains no `null` |
| `a_whole_number_too_big_to_hold_survives_show_too` (`:339`) | the digit-run spellings, the `i64` edge from both sides, a forty-digit run; and no `e+` anywhere |
| `three_documents_that_differ_do_not_digest_the_same` (`:384`) | three documents differing only in that figure publish three distinct digests — including the `.0` spellings |
| `a_number_too_big_to_hold_is_not_a_problem_of_its_own` (`:422`) | an `x-` field with `1e999` loads, exit 0, under `--deny-warnings` |
| `a_number_field_given_one_is_refused_by_name` (`:439`) | `temperature: 1e999` → `schema/too-big-to-count`, **not** `schema/wrong-type`, quoting the value, naming the line, with a typeable fix |
| `the_fix_is_followed_rather_than_matched` (`:476`) | reads the offered line out of the report, types it back into the file, and requires the workspace to load — then types a member of the set the sentence promises, on four fields, and requires that to load too |
| `one_figure_gets_one_answer_however_it_is_spelled` (`:564`) | `1e19` and `10000000000000000000` on a number, a size and a comparison; the 2^53 edge from both sides; and the bare `0.5` size silence |
| `a_whole_number_field_takes_a_whole_number_however_it_is_punctuated` (`:656`) | `1e6`, `1000000.0` load; `1.5` does not |
| `a_share_of_the_whole_reads_the_same_at_both_ends` (`:709`) | `1e999%`, `-1e999%`, `1e-999%` all named; `150%` deliberately still out-of-range rather than past-holding |
| `a_number_field_given_the_far_bottom_end_says_so` (`:780`) | `-1e999` gets the other sentence — *"further below zero"* — never *"more than"* |
| `a_number_field_given_a_whole_number_past_holding_is_refused_by_name` (`:809`) | the finite spellings no `is_finite` guard can see, including `…9999.0` and `999999999999999999990e-1` |
| `a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo` (`:890`) | `tool-calls-at-most` past `i64` is named, `i64::MAX` itself still loads, `inf` stays a typo |
| `a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo` (`:950`) | `1e999`, `1e308`, `1e999s`, `1e300h`, `1e999 seconds`, `1e400 ms`, `1e999ms` → `schema/too-long-to-count`; `30s`, `1m30s`, `2 minutes`, `500ms`, `1e6s`, `2.5e2 ms` still load; `90` still wants its unit |
| `the_bottom_end_of_a_length_of_time_and_a_size_is_not_called_text_either` (`:1073`) | the types with no bottom end to run off say *"a number"* / *"a whole number"*, never *"some text"* — and `-inf` still says *"some text"* |
| `the_word_infinity_where_a_number_goes_is_still_a_typo` (`:1156`) | `inf`, `nan`, `Infinity`, `-inf` → `schema/wrong-type`, and **not** `too-big-to-count`, at every door |
| `a_bar_no_score_could_ever_clear_is_refused_too` (`:1213`) | `> 1e999`, `> 99999999999999999999`, `> inf`; and the fix must be `` `> 80` `` and never the untypeable `` `scores: > 80` `` |
| `the_words_for_infinity_are_still_plain_text` (`:1288`) | YAML's own `.inf`, `-.inf`, `.nan` unchanged |
| `ordinary_numbers_are_untouched` (`:1311`) | `1.5`, `1e10` → `10000000000.0`, `0.5`, `42`, `-3.25` stay bare numbers |
| `an_ordinary_number_field_still_takes_an_ordinary_number` (`:1335`) | `temperature: 0.7`, `top-p: 1e-3`, `top-k: 40` load |

**Two other doors, deliberately at a different level.**
`crates/pact-doc/src/yaml.rs`'s
`a_whole_number_is_past_holding_when_it_writes_back_different_digits` (`:1195`)
asks the document-layer rule directly, so the rule has a unit-level pin
and not only an end-to-end one. The Python test named above drives the binary
and the reader together, which is the only place the two ports' duration sets
can be compared.

---

## The mutation

Thirteen edits are recorded as holding this file, in the file's own docstring
(`:160-247`), each with the names of the tests it turns red. Baseline: `19
passed; 0 failed`.

**Six of them I applied myself today**, in the isolated copy, one at a time,
each restored byte-for-byte and rebuilt before the next (restoring with
timestamps preserved makes cargo skip the rebuild and invalidates the
experiment, so every restore was followed by `touch`). All six reproduced the
recorded count, and where the record names the failing tests, the same tests
failed:

| # | the edit | measured today | recorded |
|---|---|---|---|
| **B** | disable the `Coerced::Number(n) if past_counting_figure` arm of `check_ceiling` (`lib.rs:1877`) | `14 passed; 5 failed` — `a_number_field_given_one_is_refused_by_name`, `a_number_field_given_the_far_bottom_end_says_so`, `a_number_field_given_a_whole_number_past_holding_is_refused_by_name`, `one_figure_gets_one_answer_however_it_is_spelled`, `the_fix_is_followed_rather_than_matched` | 14 / 5, same five |
| **E** | disable the `whole_number_past_holding` arm of `resolve_scalar` (`yaml.rs:805`) | `14 passed; 5 failed`; `cargo test -p pact-doc --lib` → `51 passed; 2 failed` | 14 / 5, same five; 51 / 2 |
| **G** | put the digits-only punctuation rule back inside `whole_number_past_holding` (`yaml.rs:995`) | `17 passed; 2 failed` — `three_documents_that_differ_do_not_digest_the_same`, `a_number_field_given_a_whole_number_past_holding_is_refused_by_name`; `pact-doc --lib` → `50 passed; 3 failed` | 17 / 2, same two; 50 / 3 |
| **I** | make `coerce::integer` refuse a point or an exponent again (`coerce.rs:346`) | `17 passed; 2 failed` — `a_whole_number_field_takes_a_whole_number_however_it_is_punctuated`, `a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo` | 17 / 2, same two |
| **J** | make `is_exponent_at` always false, so the `e` of `1e999s` is a unit again (`coerce.rs:585`) | `18 passed; 1 failed` — `a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo` | 18 / 1, same one |
| **L** | disable the `PercentPastHolding` arm of `check_ceiling` (`lib.rs:1970`) | `18 passed; 1 failed` — `a_share_of_the_whole_reads_the_same_at_both_ends` | 18 / 1, same one |

I also applied a seventh edit that is **not** in the record, to produce the
before-picture for the whole-number door: replacing `Ty::Integer`'s
`Value::Float` dispatch arm (`coerce.rs:259`) with `None`. That gives `18
passed; 1 failed`
(`a_whole_number_field_takes_a_whole_number_however_it_is_punctuated`) and makes
the binary print *"'tokens-at-most' should be a whole number, but it is a
number."* about `1e6`.

**Seven I did not re-run**, and this document does not claim otherwise. They are
recorded by the session that landed the repair, with failing test names, in the
docstring: **A** (drop `&& f.is_finite()` from `resolve_scalar` → 14/5, plus
`pact-doc --lib` 51/2), **C** (drop the `Threshold` ceiling arm → 17/2),
**D** (drop the word-or-figure guard in `coerce::number` → 18/1, plus
`pact-schema --lib` 56/1), **F** (narrow `past_counting_figure` back to
`!v.is_finite()` → 15/4, plus `pact-schema --lib` 56/1), **H** (drop
`coerce::size`'s `Value::Float` arm → 18/1), **K** (drop the `Value::Float` arm
for `Ty::Duration` → 18/1), **M** (put `node.as_str()` back in `check_floor`'s
`Size(0)` guard → 18/1).

After the last restore, the isolated copy was green again (`19 passed; 0
failed`) and its three source files carried the same checksums as the real
tree's, which are the ones at the top of this document.

**What the mutations show about where the coverage is.** Mutation B leaves the
whole of `cargo test -p pact-schema` green: the ceiling arms have exactly one
door in this repository, and it is this CLI file. Mutations E and G do turn
`pact-doc`'s own unit tests red, so the document-layer rule has a second,
independent door. That asymmetry is worth knowing before anybody edits either
layer.

---

## Failure cases

**Kept as the author's text at the document layer** — covered by
`a_number_too_big_to_hold_survives_show` and
`a_whole_number_too_big_to_hold_survives_show_too`: `1e999`, `1e400`, `-1e999`,
`99999999999999999999`, `…9999.0`, `999999999999999999990e-1`,
`9223372036854775808`, `-9223372036854775809`, a forty-digit run, `.inf`,
`-.inf`, `.nan` (the last three covered by
`the_words_for_infinity_are_still_plain_text`).

**Read as numbers, untouched** — covered by `ordinary_numbers_are_untouched` and
`an_ordinary_number_field_still_takes_an_ordinary_number`: `42`, `1.5`, `0.5`,
`0.7`, `1e10`, `-3.25`, `1e20`, `10000000000000000000`, `9223372036854775807`.

**Two documents that differ get two digests** — covered by
`three_documents_that_differ_do_not_digest_the_same`, in both the point-free and
the `.0` spellings; verified red under mutations E and G.

**An `x-` field is not a problem of its own, even under `--deny-warnings`** —
covered by `a_number_too_big_to_hold_is_not_a_problem_of_its_own`.

**A number field** given `1e999`, `-1e999`, `±99999999999999999999`,
`99999999999999999999.0`, `1e19`, `10000000000000000000` → named, never
`schema/wrong-type` — covered by `a_number_field_given_one_is_refused_by_name`,
`a_number_field_given_the_far_bottom_end_says_so`,
`a_number_field_given_a_whole_number_past_holding_is_refused_by_name`,
`one_figure_gets_one_answer_however_it_is_spelled`; red under B, E, F, G.

**A whole-number field** given `9223372036854775808`, `1e999`, `1e19` → named;
given `1e6`, `1000000.0`, `5e3`, `9223372036854775807` → loads; given `1.5` →
wrong-type — covered by
`a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo` and
`a_whole_number_field_takes_a_whole_number_however_it_is_punctuated`; red under
E and I.

**A length-of-time field** given `1e999`, `1e308`, `1e999s`, `1e300h`,
`1e999 seconds`, `1e400 ms`, `99999999999999999999h` → `too-long-to-count`;
given `30s`, `1m30s`, `2 minutes`, `500ms`, `1e6s`, `2.5e2 ms` → loads; given
`90` → wrong-type, because a unit would settle it — covered by
`a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo`;
red under J and K.

**A size field** given `1e999`, `1e19`, `10000000000000000000`,
`18446744073709551615` → `too-big-to-count`; given `128000`, `1.28e5`,
`32000.0`, `32k` → loads; given `0.5` → `below-the-floor`, *"which is no tokens
at all"* — covered by `one_figure_gets_one_answer_however_it_is_spelled`; red
under H and M.

**A comparison** given `> 1e999`, `> 1e19`, `> 10000000000000000000`,
`> 99999999999999999999%` → `too-big-to-count` with the same sentence a bare
number gets; given `> inf` → wrong-type; and the fix must be `` `> 80` `` and
never `` `scores: > 80` `` — covered by
`a_bar_no_score_could_ever_clear_is_refused_too`; red under C and F.

**A share of the whole** given `1e999%`, `-1e999%`, `1e-999%` → named at all
three ends; given `85%` → loads — covered by
`a_share_of_the_whole_reads_the_same_at_both_ends`; red under L.

**A word where a figure goes** — `inf`, `nan`, `Infinity`, `-inf` at every door
— stays `schema/wrong-type` and never reaches the ceiling — covered by
`the_word_infinity_where_a_number_goes_is_still_a_typo`; red under D.

**The noun for a type with no bottom end** — `finishes-within: -1e999` and
`context-at-least: -99999999999999999999` say *"a number"* / *"a whole
number"*, and `-inf` still says *"some text"* — covered by
`the_bottom_end_of_a_length_of_time_and_a_size_is_not_called_text_either`.

**The fix line is followed, not matched** — covered by
`the_fix_is_followed_rather_than_matched`, on `temperature`, `context-at-least`,
`tokens-at-most` and `finishes-within`; red under B and F.

**The markdown authoring door.** `1e999` in `agent.md` front matter reaches the
same rule at the right file and line. **UNCOVERED by any test** — no
number-line test file mentions `agent.md`. Measured by hand today:
`--> W/agents/desk/agent.md:5:16`, `schema/too-big-to-count`. Structurally it
cannot diverge, because `resolve_scalar` has one call site.

**Figures past holding nested inside a list or a map.** **UNCOVERED.** Measured
by hand: `x-list: [1e999, 99999999999999999999]` and `x-map: {inner: 1e400}`
come back out of `pact show` as `"1e999"`, `"99999999999999999999"` and
`"1e400"`. Same single call site.

**Money past holding written as a digit run.** **UNCOVERED, and genuinely
broken** — see [What remains open](#what-remains-open), item 2.

**A fractional literal past 2^53.** **UNCOVERED and out of scope by choice** —
see item 1.

**A size written as a plain whole number above 2^53.** **UNCOVERED** — see
item 3.

**The noun for `150%`.** **UNCOVERED as a defect; the rule around it is
covered** — see item 4.

---

## What remains open

Four things. None of them was repaired by this pass, and each is stated with the
measurement that shows it.

**1. A fractional literal past 2^53 still rounds onto its neighbour, and two
such documents still share a digest.** Measured:

```text
x-big: 9999999999999999999999e-2  -> sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888
x-big: 9999999999999999999998e-2  -> sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888
x-big: 100000000000000000000.0    -> sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888
```

Those two literals spell `99999999999999999999.99` and `…98.99`, which are not
whole numbers, so the whole-number rule does not reach them — deliberately,
because the only rule that would also refuses `0.1` and `0.7`. This is the same
bound C12 recorded at the bottom of the scale (`3e-324`, `5e-324`, `7e-324` on
one digest), stated here for the top.

**2. Money still asks only whether the amount overflowed.** Measured:

```text
$ pact check   # limits: cost-per-request-under: 99999999999999999999 USD
OK — W loaded cleanly (11 settings).      rc=0
$ pact show
        "cost-per-request-under": "99999999999999999999 USD",
$ pact check   # limits: cost-per-request-under: 1e999 USD
error: 'cost-per-request-under' is 1e999 USD, which is a larger amount than this can keep track of.
  fix: Write `cost-per-request-under: 0.05 USD`, or any smaller amount, or remove the line.
  rule: schema/too-much-to-count
```

Two problems in one field: the digit-run spelling loads and the checker holds
`1e20`, a figure nobody wrote; and the fix line still says *"or any smaller
amount"*, which is the false-set sentence this pass replaced everywhere else.
The published IR does carry the author's text, so the loss is confined to the
checker's own figure. Money was not in this issue's findings and its fix line is
asserted by
`crates/pact-schema/tests/a_spend_cap_is_an_amount_of_money_and_has_a_bottom.rs`;
making `coerce::money` ask `past_counting_figure` is a one-line change with one
test assertion to move, and it belongs to the money row (`B3`).

**3. A size written as a plain whole number is held above 2^53.** Measured:

```text
needs: context-at-least: 9007199254740993     -> loads
needs: context-at-least: 9007199254740993.0   -> error: … is more than this can keep track of.
```

That is each door refusing exactly what it cannot hold — the integer path
(`coerce.rs:694`) is a `u64` and holds the figure exactly, the double path does
not — but it is two answers for one figure, immediately after a document that
says *"one figure, one answer"*. It is bounded: the smallest figure it affects
is 2^53 + 1 tokens, which no model has.

**4. The noun for a share out of range.** Measured: `when-full: 150%` →
*"'when-full' should be a percentage, like `90%`, but it is some text."* The
rule is right (150% is not a share of a whole) and the fix line names the range,
but the noun is wrong in exactly the way this family of defects is about.
`kind_as_written` cannot rescue it because `150%` does not parse as a figure.

**A fifth, smaller thing: two stale citations inside the test file's own
header.** `crates/pact-cli/tests/a_number_too_big_to_hold_is_kept_as_it_was_written.rs:42`
cites `pact-schema/src/lib.rs:1659` and `:1698` as two of the places this
repository condemns the dead-end sentence. Read today, those lines are
`coerce::Coerced::Integer(n) => match f.at_least {` and a comment inside
`check_floor` — the C12 round moved them. The live citations are
`crates/pact-schema/src/coerce.rs:330`, `:405` and `:726`. A stale citation
beside a live assertion makes a reader doubt the assertion too, which is the
argument this project makes about its own measurements.

---

## Verification

Run on the real tree today, in this order:

```
$ cargo test -p pact-cli --test a_number_too_big_to_hold_is_kept_as_it_was_written
test result: ok. 19 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out

$ cargo test -p pact-doc
test result: ok. 53 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out

$ cargo test --workspace --no-fail-fast     # summed over every "test result" line
955 passed, 0 failed

$ cargo clippy --all-targets -- -D warnings
Finished `dev` profile [unoptimized + debuginfo] target(s)

$ cd adapters/python && uv run pytest tests/ -q
1955 passed, 7 skipped in 150.53s

$ cd adapters/typescript && npx tsc --noEmit
(no output, exit 0)

$ ./scripts/sync-counts.sh
rust=955 adapter=1962 total=2917
wrote 2917 into 4 documents
```

One honest note about the workspace run: the first of my three runs reported one
failure, and it was taken while the Python suite was running at the same time
and using the same built binary. Two subsequent runs with nothing else running
both summed to `955 passed, 0 failed`, and the single failure did not name a
test in either run's output. It is recorded here rather than dropped.

The revert check that matters is the mutation table above: six edits removed one
at a time, each watched to go red on the tests the record names, each restored
and the copy watched to go green again.

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md:855` — the `C10` row — was rewritten by the
session that landed this repair and is correct as it stands: it is struck
through, it says **CLOSED**, it records the punctuation rule and its replacement,
the four doors that were still printing the condemned sentence, the false fix
line, the unpinned duration word-guard and the silence the repair itself opened
and closed, and it ends `See docs/remediation/C10-number-too-big-dead-end.md.`

**The one change still owed** is to its *"What stays open"* clause, which today
names only C12's bottom-of-the-scale residual (`3e-324`, `5e-324`, `7e-324` on
one digest). It should also name the four measured in this pass. Proposed
addition, to be appended to that clause — **not applied by this pass**, because
another session is editing that file:

> Four residuals are measured and named rather than waved at, in
> `docs/remediation/C10-number-too-big-dead-end.md`: a FRACTIONAL literal past
> 2^53 still rounds onto its neighbour and still digests with it
> (`9999999999999999999999e-2` and `…98e-2` both `sha256:2aa9f0c9…`), for the
> same reason the bottom end does — the only rule that would catch it refuses
> `0.1`; money still asks only whether the amount overflowed, so
> `cost-per-request-under: 99999999999999999999 USD` loads clean with the
> checker holding `1e20` and `1e999 USD` still offers the false *"or any smaller
> amount"* (it belongs to `B3`); a size written as a plain whole number goes
> through a `u64` and so holds figures above 2^53 that its double-valued twin
> refuses (`context-at-least: 9007199254740993` loads, `9007199254740993.0` does
> not); and `when-full: 150%` is still *"but it is some text"*, because a share
> with a `%` on it does not parse as a figure for `kind_as_written` to name.

No other register row is affected. `docs/remediation/QUEUE.md` row 15 already
reads `done` with this file in the Doc column.
