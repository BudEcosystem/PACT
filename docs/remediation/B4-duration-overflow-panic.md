# B4 — a length of time too long to count killed `pact check` outright, and where it did not kill it, it kept a ceiling nobody wrote

**Severity: high.** · **Status: fixed. The overflow half had already landed and
survives every attack made on it here; one further defect was found against the
fixed build by measurement, and is repaired in this pass.** · **Register row:
`docs/70-PRODUCTION-GAP-REGISTER.md` had no row for this at all — see
[Register update](#register-update).**

Every number below names the command that produced it, run against this working
tree on this machine. Where a figure was measured against a mutated or pre-fix
state, it says which state and how that state was produced.

**Another session is editing this repository right now, and during this pass it
had a mutation of its own live in the very file this issue lives in.** At one
point `crates/pact-schema/src/coerce.rs` contained the line
`*total = (*total).map(|t| t + ms as u64); // MUTATION — B4 reproduction, restore me`,
which is not mine. Nothing of theirs was reverted: the file was left alone until
they restored it, which they did within ten seconds, and their restore carried
my change forward intact. Only this issue's own files were touched.

---

## The name `B4` means three different things in this repository

Before anything else, because the last document in this series was bitten by the
same thing one letter over:

* **Queue `B4`** (`docs/remediation/QUEUE.md`, row 5) is `duration-overflow-panic`
  — this document.
* **Gap-register `B4`** (`docs/93-GAPS.md:114`) is *"a person's answer to
  `ask-someone` bypasses the chain"*.
* **Fix-plan `B4`** (`docs/95-FIX-PLAN.md:184`, and eight more lines) is one
  third of *"B1/B2/B4 — one `park()` helper"*.

They are unrelated. A reader who greps `B4` will find the park helper first, and
this row does not touch Python at all.

---

## What is wrong

A length of time is written the way a person writes one — `30s`, `1m30s`,
`5 minutes`, `1d` — and `coerce::duration` adds its parts up into a whole number
of milliseconds. The addition was

```
crates/pact-schema/src/coerce.rs:174   (git show HEAD:...)
        *total += (v * mult) as u64;
```

Both halves of that line are traps.

* **The cast saturates.** Converting a floating-point number to a whole number
  in Rust does not wrap and does not fail — it pins the result at the largest
  whole number there is. So one oversized part quietly became
  18,446,744,073,709,551,615 milliseconds.
* **The addition then goes over the top of that.** A second part added to a
  total already pinned at the maximum overflows. In a debug build — the build
  `cargo run` produces and the one the README tells an author to use — that is
  an immediate crash.

### Reproduction, verbatim

The pre-fix arithmetic was restored (see [The mutation](#the-mutation)), the
binary rebuilt, and the worked example edited on one line:

```
$ sed -i 's/finishes-within: 30s/finishes-within: "99999999999999999999h 99999999999999999999h 99999999999999999999h"/' ws/agents/refund-desk/limits.yaml
$ cargo build -p pact-cli
$ ./target/debug/pact check ws
thread 'main' (3466189) panicked at crates/pact-schema/src/coerce.rs:276:23:
attempt to add with overflow
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace
EXIT=101
```

No file name, no line, no rule, no fix — the whole command gone, on one line of
one file. For the reader this project is built for, who cannot read a stack
trace, `pact check` simply stops existing.

### And the half that did not crash is worse

A release build does not panic; it wraps. Same tree, same edit,
`cargo build -p pact-cli --release`:

```
$ ./target/release/pact check ws
OK — /tmp/.../ws loaded cleanly (498 settings).
EXIT=0
```

The checker said the tree was fine. To see what ceiling it had actually kept,
the same three spellings were put on a question's `answer-within:` and read back
through the tool that hands deadlines to whatever times them:

```
$ ./target/release/pact waits ws | ... "deadline-ms" for how-much-to-refund
"99999999999999999999h"                                      -> 18446744073709551615
"18000000000000000000ms 400000000000000000ms 100000000000000000ms" ->    53255926290448384
"99999999999999999999h 99999999999999999999h ... (three)"    -> 18446744073709551613
```

The middle line is the one to look at. Three parts, each individually a number
the checker can hold, adding to 18,500,000,000,000,000,000 — just past the top.
It came back as **53,255,926,290,448,384**: the sum minus 2⁶⁴, which is about
616 days. A person wrote something absurd, and a scheduler was handed something
plausible, and nothing anywhere said the figure had moved.

Both figures are stated in
`crates/pact-schema/tests/durations_say_what_they_accept.rs:214-215` and both
reproduce exactly, which is worth saying because the equivalent prose in the
last issue's test file did not.

---

## Root cause

**The class is: a floating-point value converted to a whole number without
asking whether it fits, and then used in arithmetic that assumes it did.**

It is not a duration bug. It is a cast bug that happened to be under a duration.
The same two lines of code appear one screen apart in the same file, and the
second one — `size`, which reads `32k` as 32,000 — had exactly the same cast:

```
crates/pact-schema/src/coerce.rs   (git show HEAD:...)
    Some((v * mult) as u64)
```

`size` has no addition after the cast, so it never crashed. It was only ever
quietly wrong: `context-at-least: 99999999999999999999m` saturated into a
requirement no model on earth meets, and `pact check` said the tree was fine.
That is precisely the release-build half of the duration defect, sitting one
function away.

The cast is the class, and the class was swept. Grepping the whole Rust core for
conversions of this kind:

```
$ grep -rn " as u64\| as i64\| as u32\| as usize" crates/*/src/*.rs \
    | grep -vi "len()\|count()\|\.0 as\|u64::MAX as"
crates/pact-doc/src/canonical.rs:135     c if (c as u32) < 0x20 =>          # a character, not a figure
crates/pact-doc/src/canonical.rs:136     write!(out, "\\u{:04x}", c as u32) # the same character
crates/pact-schema/src/coerce.rs:279     checked_add(ms as u64)             # this fix
crates/pact-schema/src/coerce.rs:384     *i as u64                          # an integer already >= 0
crates/pact-schema/src/coerce.rs:426     tokens as u64                      # the size fix
crates/pact-loader/src/policy.rs:160     MAX_TEXT as u64                    # a constant
```

There are exactly two places where a figure an author wrote is converted from
floating point to a whole number, and both are in this file, and both are fixed.
Money is the third quantity of this shape and never had the defect, because it
stays a floating-point number end to end and is guarded for infinity instead
(`schema/too-much-to-count`).

---

## Why nothing caught it

**The type had a floor and no ceiling, and the floor is where everybody looked.**
`finishes-within: 0s` had already been found and fixed — it is
`schema/below-the-floor`, held by two tests, and its rationale is written out at
length in `crates/pact-schema/src/lib.rs:1616` onward. The reasoning it records
is *"a length of time is more than nothing"*. Nobody wrote down the other half:
a length of time is also less than forever.

**The existing duration tests all used sensible values.** Before this fix, the
accepted-spellings list in `coerce.rs` topped out at `999999h`
(3,599,996,400,000 ms) — a hundred and fourteen years, and about four million
times too small to reach the cast. Every test asserted the reader was *generous
enough*; none asked what it did at its end.

**The release build hides the crash and the debug build hides the wrap.** The
two builds fail in opposite ways from the same line. A suite run under `cargo
test` — a debug build — would have shown the panic; there was no test to run.

**And the guard that would have caught it does not exist in Rust by default.**
Integer overflow is checked in debug and wrapping in release; a float-to-whole-number
cast is *saturating in both*. Nothing warns. (Whether `cargo clippy -D warnings`
would have flagged the pre-fix line was **not measured** — clippy was run only
against the fixed tree.)

---

## The fix

Three edits, all in the Rust core, none changing any caller's signature.

### 1. The running total learns how to say "it did not fit"

`crates/pact-schema/src/coerce.rs:239`

```rust
let mut total: Option<u64> = Some(0);
```

`None` here does not mean *"this is not a length of time"*. It means *"the parts
so far have already run off the end of the milliseconds they are kept in"*.

### 2. The cast is guarded, and the addition is checked

`crates/pact-schema/src/coerce.rs:273-295`

```rust
let ms = v * mult;
*total = if ms >= u64::MAX as f64 {
    None
} else {
    (*total).and_then(|t| t.checked_add(ms.round() as u64))
};
```

`u64::MAX as f64` is 2⁶⁴ exactly, so `ms >= it` is precisely the condition
*"the cast below is the one that would saturate"* — the guard is not a
conservative approximation of the boundary, it is the boundary.
`checked_add` then hands back `None` rather than wrapping or panicking, so the
two failure modes become one answer.

The `.round()` is the repair made during this pass; it is
[the defect found against the fixed build](#what-this-pass-found-against-the-landed-fix) below.

### 3. It leaves as what it is, and is refused where the author is

`crates/pact-schema/src/coerce.rs:320-323`

```rust
match (any, total) {
    (false, _)      => None,                            // nothing was written
    (true, Some(ms))=> Some(Coerced::Duration(ms)),
    (true, None)    => Some(Coerced::DurationTooLong),  // written, and does not fit
}
```

`Coerced::DurationTooLong` (`coerce.rs:29`) carries no number, because there is
no number to carry — the point is that the one the author wrote does not fit.
It is refused one layer up, in `Schema::check_ceiling`
(`crates/pact-schema/src/lib.rs:1723-1728`), as `schema/too-long-to-count`.

This is the same shape as the floor, and for the same reason. `None` would mean
*"that is not a length of time"*, which is false about a correctly spelled line
and would send its author hunting for a typo that is not there.

**What an author now sees** (measured, current build):

```
$ ./target/debug/pact check ws
error: 'finishes-within' is 99999999999999999999h 99999999999999999999h 99999999999999999999h, which is a longer time than this can keep track of.
  --> .../ws/agents/refund-desk/limits.yaml:10:18
   |
10 | finishes-within: "99999999999999999999h 99999999999999999999h 99999999999999999999h"
   |                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  fix: Write `finishes-within: 30s`, or any shorter length of time, or remove the line. — how long the whole thing may take. …
  rule: schema/too-long-to-count
1 problem(s) found in .../ws. Nothing was run.
EXIT=1
```

### 4. The second warning that called a refused deadline a missing one

`crates/pact-loader/src/report.rs:753-756`

```rust
-    if milliseconds(written).is_some() || if_nobody_answers.is_empty() {
+    if q.get("answer-within").is_some() || if_nobody_answers.is_empty() {
```

`answer-within:` is read twice — the schema judges the length of time, and
`loader/wait-with-no-deadline` asks whether there is one at all. The second used
to ask by trying to *parse* it. So a deadline the schema had just refused by
name, quoting the line, was in the next paragraph reported as never written.
One mistake, two messages, and the second one plainly false beside the first.

`report.rs:943` is worth naming because of what it is *not*: `milliseconds` does
not re-implement the reader, it calls `pact_schema::coerce::check(.., Ty::Duration)`
and takes only `Coerced::Duration(ms)`. There is exactly one duration reader in
the Rust core, so `DurationTooLong` cannot be read as a number anywhere.

---

## What this pass found against the landed fix

The overflow fix survived every attack made on it. **One defect did not**, and
it is inside a claim the landed test file makes in its own words:

> `the_longest_deadline_that_fits_reaches_a_scheduler_as_the_number_written`
> — *"it stopped crashing" is not the claim … so the number is asserted.*

A fraction of a second is not held exactly by a floating-point number.
`1.001 * 1000.0` comes to `1000.9999999999999`, and the conversion to whole
milliseconds **threw the tail away**. Measured through the shipped command,
against the build that had the overflow fix and before this pass touched it:

```
$ sed -i 's/answer-within: 4h/answer-within: "1.001s"/' ws/questions/how-much-to-refund.yaml
$ ./target/debug/pact check ws
OK — … loaded cleanly (498 settings).
$ ./target/debug/pact waits ws | ... deadline-ms
1000
```

`answer-within: 1.001s`, and a scheduler is handed 1000 milliseconds. Also
measured: `1.005s → 1004`. A sweep of the first 20,000 thousandths for each of
the five units (`0.001`…`20.000` × `ms`,`s`,`m`,`h`,`d`) finds **3,404**
spellings whose product lands a millisecond short of the figure written.

It is one millisecond. It is here because it is the *same complaint the file's
own header makes*: reading `1m30s` as one second is called out there as a
ceiling ninety times tighter than the one written, *with nothing anywhere to say
so*. This is that, smaller. And it is a cross-port divergence — measured,
`pact_adapters.limits.seconds("1.001s")` returns `1.0009999999999999` seconds,
which is 1001 ms to the nearest millisecond, so the two ports disagreed about
what the same line means.

**Repaired here** by rounding rather than truncating (`coerce.rs:294`,
`ms.round() as u64`). Rounding cannot lift anything over the top, because it
moves a figure by at most half a millisecond and the boundary guard is checked
on the *unrounded* product; and it cannot invent time where there was none,
because `0.4ms` still rounds to zero and is still refused at the floor. Both are
asserted (`coerce.rs`, `a_fraction_of_a_second_is_the_fraction_that_was_written`).

---

## Alternatives rejected

**Refuse it in the reader, as `None`.** Cheapest, and wrong for the reason the
floor already established: `None` becomes `schema/wrong-type`, which says *"that
is not a length of time"* about a line spelled exactly the way the help says to
spell it. The author would read the fix — *"write it like `2s`, `500ms`,
`1m30s`…"* — look at their `99999999999999999999h`, and see a number and a unit.
There is no edit that sentence asks for.

**Saturate deliberately, and treat the largest number there is as "forever".**
Rejected on what the fields mean. `finishes-within:` is a promise made to
whoever waits and, with no `runs-for-at-most:` beside it, the wall-clock stop as
well; `forget-after:` is the only thing that ever discards what was remembered
about a person. A silent "forever" on either is a worse answer than a refusal,
and it is unfalsifiable — no report would ever say the figure had changed.

**Count in a wider number.** Real, and rejected as buying nothing: 128-bit
arithmetic moves the boundary from 585 million years to 10²² years and leaves
the same cliff at the new edge, with a wider number threaded through every
caller of `Coerced::Duration`. The problem is not that the range is too small.
It is that going past it said nothing.

**Check the whole string's magnitude before parsing** (e.g. refuse any part with
more than N digits). Rejected: it is a guess at the boundary rather than the
boundary. `18000000000000000000ms 400000000000000000ms 100000000000000000ms` has
no oversized part in it — each one fits — and it is the case that wrapped.

**Panic with a better message.** Not considered seriously, and named only
because it is the shape of "fix" that a stack trace invites. Every other refusal
in this system names a file, a line, a rule and an edit; a crash names none of
them, however politely worded.

**Round in the reader from the start, instead of truncating.** This is the one
that *should* have been taken and was not — see the section above. It was not a
considered trade-off in the original fix; truncation was simply inherited from
the pre-fix line, which also truncated.

---

## Blast radius

**Callers, outward.** `coerce::check` is the one door, and its signature did not
change: `Option<Coerced>` in, `Option<Coerced>` out. Two variants were added to
a public enum (`Coerced::DurationTooLong`, `Coerced::SizeTooBig`), so every
`match` on `Coerced` in the workspace had to be re-examined. Measured — outside
`pact-schema` there are five call sites and none of them matches exhaustively:
`crates/pact-loader/src/report.rs:943` (`Duration` only),
`teamwork.rs:422` (`Percent`), `money.rs:500,654` and `approvals.rs:475`
(`YesNo`), `currency.rs:145,205` (`Money`). Each takes one variant and falls
through on anything else, so a duration that does not fit is *absent* rather
than *wrong* at every one of them.

**Every door refuses it, not just `check`.** Measured on the current build, same
bad workspace:

| command | result |
|---|---|
| `pact check` | `schema/too-long-to-count`, EXIT=1 |
| `pact show` | same diagnostic, EXIT=1 |
| `pact waits` | same diagnostic, EXIT=1 — **no `deadline-ms` is projected at all** |
| `pact card refund-desk` | same diagnostic, EXIT=1, zero bytes on stdout |
| `pact discover` | `skipping …: 1 problem(s)`, prints `[]`, EXIT=0 |

`pact waits` is the one that matters: it is the projection a runtime reads to set
a timer, and before the fix it was the thing being handed 53,255,926,290,448,384.

**Every duration field, not the one somebody remembered.** The ceiling belongs to
the type, so it arrives on all seven duration fields in `spec/schema.yaml` at
once. Measured, one workspace per field:

```
'first-reply-within' is 99999999999999999999h, which is a longer time … rule: schema/too-long-to-count
'per-word-under'     … schema/too-long-to-count
'runs-for-at-most'   … schema/too-long-to-count
'forget-after'       … schema/too-long-to-count
'finishes-within'    … schema/too-long-to-count
'answer-within'      … schema/too-long-to-count
```

(`gives-up-after`, `spec/schema.yaml:3927`, is the seventh; it needs a `teamwork:`
block to reach and was not driven separately. It is the same `Ty::Duration`
through the same `check_ceiling` call at `lib.rs:1553`.)

**Digest stability — structural, not a before/after diff.** `pact-doc` is where
digests are computed (`canonical.rs:38`) and its only PACT dependency is
`pact-diag` (`crates/pact-doc/Cargo.toml:11`); `grep -rn "pact_schema" crates/pact-doc/src/`
returns nothing but a comment. Coercion is downstream of the document and cannot
reach the hash. The ten workspace digests under `examples/` were recorded from
`pact discover examples` as a baseline; the first is
`sha256:17393f6f55feee8f9d22d76e8d0ba605f01255e2c3744622c0050fd1f2d71609`.
**Stated honestly: this is a dependency-direction argument plus a baseline, not a
measured comparison against a pre-fix binary.**

**The five honesty channels — not affected.** They live on `RunResult` in
`adapters/python/src/pact_adapters/harness.py` (`unretrieved:136`,
`unmetered:168`, `unenforced:173`, `unwatched:178`, `never_reached`). This fix is
in the Rust schema layer, which is never on a run path, and no adapter source
file reads an author's files at all (held by
`adapters/python/tests/test_no_adapter_reads_the_authors_files.py`).

**Cross-port — a deliberate parting, and it is one-way.** Both other ports read
the same spellings and have no top end, because they count in floating point:

```
$ python3 -c "from pact_adapters.limits import seconds; print(seconds('99999999999999999999h'))"
3.6e+23
```

`adapters/typescript/src/limits.ts:378` is the same shape. The divergence is
written down in `limits.py:517-526` — *"the Rust side is stricter at both ends …
that is safe in the direction it runs, `pact check` is the gate"* — and the
direction is what makes it safe: the Rust reader refuses a superset of what the
others refuse, so nothing the checker rejects can reach a run. **No test asserts
that.** See [Failure cases](#failure-cases).

**Counts — self-correcting.** `scripts/sync-counts.sh` computes the Rust and
adapter figures from live runs and writes them into four documents. Run after
this pass: `rust=903 adapter=1747 total=2650`, written into `README.md`,
`site-docs/status/verified.md`, `site-docs/index.md` and `docs/90-REVIEW.md`
(was 901/2648). The hardcoded `54` at `scripts/test-all.sh:53` counts *Python*
test files and is untouched — this issue adds no Python.

**Rule ids.** `schema/too-long-to-count` and `schema/too-big-to-count` are new
ids. Grepped: they appear nowhere in `site-docs/reference/` or `docs/90-REVIEW.md`,
because this repository has no rule index to keep in step — the diagnostic is
the documentation. Nothing to sync.

---

## The test

Three files, three altitudes. The door-level ones are not seams: the
reproduction *is* `pact check` dying, and a library test proves a reader refuses
a string, not that the command survives reaching it.

### Through the shipped command
`crates/pact-cli/tests/a_duration_means_what_the_help_says.rs` — **9 tests**,
each copying `examples/refund-desk` to a temp tree, editing exactly one line, and
running `env!("CARGO_BIN_EXE_pact")`. Four are this issue's:

* `a_length_of_time_too_long_to_count_is_refused_at_check_time` — asserts the run
  is refused, the rule is `schema/too-long-to-count`, the message names the
  setting *and quotes what was written*, the file and line appear
  (`limits.yaml:10`), the fix is a line that can be typed, and
  `schema/wrong-type` does **not** appear.
* `a_deadline_too_long_to_count_is_reported_once_and_not_also_called_missing` —
  one mistake, one message: `loader/wait-with-no-deadline` must be absent.
* `a_deadline_never_written_at_all_is_still_reported` — the boundary of that,
  so narrowing the gate did not narrow it to nothing.
* `the_longest_deadline_that_fits_reaches_a_scheduler_as_the_number_written` —
  `100000h 30m` must arrive at `pact waits` as `"deadline-ms": 360001800000`.
  This is the one that makes "it stopped crashing" not the claim.
* **New in this pass:** `a_fraction_of_a_second_reaches_a_scheduler_as_the_fraction_written`
  — `1.001s` must arrive as `"deadline-ms": 1001`, through the same command.

### Through the schema seam
`crates/pact-schema/tests/durations_say_what_they_accept.rs` — 8 tests; this
issue's is `a_length_of_time_nobody_can_count_is_refused_by_name_rather_than_crashing`,
which drives three spellings (one oversized part; the three-part reported line;
and three parts each of which fits) and asserts the field is named, the written
text is quoted, the fix is typeable, and `schema/wrong-type` is absent.

### Through the reader itself
`crates/pact-schema/src/coerce.rs` `mod tests` — 14 tests. Three matter here:

* `a_length_of_time_too_long_to_count_parses_here_and_is_refused_one_layer_up` —
  the three spellings come back as `Coerced::DurationTooLong`, not `None` and
  not a number.
* `durations_accept_the_obvious_spellings` — the guard did not take the good
  values with it, and the sums are exact to the millisecond:
  `1000000h → 3_600_000_000_000`, `100000h 30m → 360_001_800_000`,
  `9999d 23h 59m 59s 999ms → 863_999_999_999`. All three verified by hand.
* **New in this pass:** `a_fraction_of_a_second_is_the_fraction_that_was_written`
  — `1.001s → 1001`, `1.005s → 1005`, `2.29m → 137400`, and the two boundaries
  rounding must not break: `0.4ms → 0` (still no time at all) and `0.5ms → 1`.

---

## The mutation

**All of these were applied to real source, built, measured, and reverted.**
The file was copied to a scratchpad first and restored from that copy; the
restore was verified by `md5sum` each time.

### M1 — put the pre-fix arithmetic back

`coerce.rs:291-295` replaced with `*total = Some((*total).unwrap_or(0) + ms as u64);`
— the saturating cast and the unchecked addition, which is `*total += (v * mult) as u64`
in the shape the current signature takes.

| suite | result under M1 |
|---|---|
| `cargo test -p pact-schema --lib` | `FAILED. 53 passed; 2 failed` — `a_length_of_time_too_long_to_count_parses_here_and_is_refused_one_layer_up` (`left: Some(Duration(18446744073709551615))`) **and** `a_fraction_of_a_second_is_the_fraction_that_was_written` (`left: Some(Duration(1000))`) |
| `cargo test -p pact-schema --test durations_say_what_they_accept` | `FAILED. 7 passed; 1 failed` — `a_length_of_time_nobody_can_count_is_refused_by_name_rather_than_crashing`, `panicked at coerce.rs:292:23: attempt to add with overflow` |
| `cargo test -p pact-cli --test a_duration_means_what_the_help_says` | `FAILED. 6 passed; 3 failed` — the refusal test (empty stdout, because the binary died), the "not also called missing" test, **and** `a_fraction_of_a_second_reaches_a_scheduler_as_the_fraction_written` |
| `cargo test -p pact-loader` | all green — 199 lib + every integration target |

The two rows carrying **and** are a correction to what this document first
recorded (`53 passed; 1 failed` and `6 passed; 2 failed`). Those numbers do not
add up to the suites' sizes — 55 and 9 — and the reason is that M1, written as
`+ ms as u64`, drops the ROUNDING as well as the guard. It therefore kills M2's
tests too, and M1 and M2 do **not** hit disjoint sets: M2 is the strictly smaller
of the two. The claim that survives, and the one that matters, is the one below.

And, at the door, the reproduction quoted at the top of this document: debug
build EXIT=101 with `attempt to add with overflow`; release build
`OK — loaded cleanly (498 settings)` EXIT=0 with the three wrapped `deadline-ms`
figures.

`pact-loader` staying entirely green under M1 is worth stating: it means the
loader-side change (`report.rs`) is held by the CLI test and not by anything in
its own crate. That is a thin place, not a wrong one — the warning it suppresses
is only visible in a report, and the report is what the CLI test reads.

### M2 — put the truncating cast back

`ms.round() as u64` → `ms as u64`, the state the tree was in before this pass.

| suite | result under M2 |
|---|---|
| `cargo test -p pact-schema --lib` | `FAILED. 54 passed; 1 failed` — `a_fraction_of_a_second_is_the_fraction_that_was_written` |
| `cargo test -p pact-cli --test a_duration_means_what_the_help_says` | `FAILED. 8 passed; 1 failed` — `a_fraction_of_a_second_reaches_a_scheduler_as_the_fraction_written`, reporting `"deadline-ms": 1000` |

Everything else stayed green, including
`the_longest_deadline_that_fits_reaches_a_scheduler_as_the_number_written` —
which is exactly why that test could not hold this: `100000h 30m` is whole
milliseconds and rounds and truncates to the same figure.

**No test in this issue passes with and without the fix.** Each of the six is
killed by M1 or M2.

### M3 — put `milliseconds(written).is_some()` back in `report::check_deadline`

The mutation named in that test's own docstring. Recorded here as *not
performed* until a later pass applied it, in an isolated copy of the workspace
so it could not collide with concurrent work on the same files.

| suite | result under M3 |
|---|---|
| `cargo test -p pact-loader` | **all green** — 15 targets, 199 lib tests among them |
| `cargo test -p pact-cli --test a_duration_means_what_the_help_says` | `FAILED. 8 passed; 1 failed` — `a_deadline_too_long_to_count_is_reported_once_and_not_also_called_missing`, and only that one |

So the thin place named under M1 is now measured rather than argued: the
`report.rs` edit is held by exactly one test, and that test lives in another
crate and drives the shipped binary. `a_deadline_never_written_at_all_is_still_reported`
stays green under M3, which is correct — M3 restores a gate that still reports
genuine silence, and that test's job is to stop the narrowing going too far.

### M4 — write the guard `>` instead of `>=` — **THE ONE THAT SURVIVED**

`*total = if ms >= u64::MAX as f64` → `if ms > u64::MAX as f64`. This is the
edit the fix's own comment rules out in prose — *"`u64::MAX as f64` is 2^64
exactly, so `ms >= it` is precisely 'the cast below is the one that would
saturate'"* — and, as this document first stood, **nothing tested it**:

| suite | result under M4, before the boundary case existed |
|---|---|
| `cargo test -p pact-schema --lib` | `ok. 55 passed; 0 failed` |
| `cargo test -p pact-schema --test durations_say_what_they_accept` | `ok. 8 passed; 0 failed` |
| `cargo test -p pact-cli --test a_duration_means_what_the_help_says` | `ok. 9 passed; 0 failed` |

Green everywhere, while the defect this whole row is about walked back in
through the one millisecond the three existing cases cannot reach. Measured
against the M4 build, through the shipped command:

```text
$ cat questions/how-much-to-refund.yaml
answer-within: "18446744073709551616ms"

$ pact check .
OK — … loaded cleanly (498 settings).

$ pact waits .
      "deadline-ms": 18446744073709551615,
```

That is 2^64 ms written and `u64::MAX` handed to a scheduler — the saturating
cast, unguarded, producing a ceiling nobody wrote and saying nothing. It is a
false *negative* at the boundary and is not the same as failure case 15, which
is a false *positive* 616 ms below it.

**Repaired.** `"18446744073709551616ms"` is now the fourth entry in both
`coerce::a_length_of_time_too_long_to_count_parses_here_and_is_refused_one_layer_up`
and `durations_say_what_they_accept::a_length_of_time_nobody_can_count_is_refused_by_name_rather_than_crashing`.
With it, M4 gives `FAILED. 54 passed; 1 failed` (`left: Some(Duration(18446744073709551615))`,
`right: Some(DurationTooLong)`) and `FAILED. 7 passed; 1 failed`; reverted, both
are green again at 55 and 8. Neither test's count changes — they are loop
entries — so `scripts/sync-counts.sh` is untouched by the repair.

---

## Failure cases

| # | case | status |
|---|---|---|
| 1 | One part whose cast alone saturates — `99999999999999999999h` | covered by `durations_say_what_they_accept::a_length_of_time_nobody_can_count_…` and `coerce::a_length_of_time_too_long_to_count_…` |
| 2 | Several oversized parts, so the *addition* overflows — the reported line | covered by both of the above, and by the CLI's `a_length_of_time_too_long_to_count_is_refused_at_check_time` |
| 3 | Parts that each fit and together do not — `18000000000000000000ms 400000000000000000ms 100000000000000000ms` | covered by both, and it is the case a digit-counting guard would have missed |
| 4 | A long length of time that *does* fit must still load, exactly | covered by `durations_accept_the_obvious_spellings` (three values) and the CLI's `the_longest_deadline_that_fits_…` (through `pact waits`) |
| 5 | A refused deadline must not also be called a missing one | covered by `a_deadline_too_long_to_count_is_reported_once_and_not_also_called_missing` |
| 6 | A deadline genuinely never written must still be reported | covered by `a_deadline_never_written_at_all_is_still_reported` |
| 7 | Zero must still be refused at the floor, not at the ceiling | covered by `a_promise_of_zero_time_is_refused_at_check_time` and `a_length_of_time_of_none_parses_here_…` |
| 8 | A real word where a length of time goes (`soon`, `5 bananas`) must stay `schema/wrong-type` | covered by `durations_accept_the_obvious_spellings` |
| 9 | A fraction of a second must arrive as the fraction written | covered by `a_fraction_of_a_second_is_the_fraction_that_was_written` and its CLI twin — **found broken in this pass and repaired here** |
| 10 | The same overflow one type over — `context-at-least: 99999999999999999999m` | covered by `crates/pact-cli/tests/a_size_this_cannot_count_is_refused_rather_than_changed.rs` (2 tests) — that is a different queue row's fix; named here because it is the same cast |
| 11 | The refusal must reach `pact waits`, `pact show` and `pact card`, not only `pact check` | **UNCOVERED.** Measured correct at all four doors (table above); no test drives any door but `check` — except `the_longest_deadline_…`, which reaches `waits` on a value that *loads*. |
| 12 | `gives-up-after:` — the seventh duration field, inside `teamwork:` | **UNCOVERED, and correct by construction.** Not driven separately; it reaches `check_ceiling` through the same `lib.rs:1553` as the six that were measured. |
| 13 | The Python and TypeScript readers accept what the Rust reader refuses | **UNCOVERED.** Measured: `seconds('99999999999999999999h')` → `3.6e+23`. Deliberate and documented at `limits.py:517-526`; the safety argument is *"`pact check` is the gate"* and **no test asserts that a runtime cannot be handed a document the checker never saw.** |
| 14 | A duration between 2⁵³ and 2⁶⁴ milliseconds is kept exactly | **UNCOVERED, and it is not.** Measured: `answer-within: "9007199254740993ms"` loads and `pact waits` reports `9007199254740992` — one millisecond short, at 285,616 years. |
| 15 | A duration in the top 616 ms below the limit is accepted | **UNCOVERED, and it is not.** Measured: `18446744073709551000ms` fits in the number used and is refused as `schema/too-long-to-count`, because its nearest floating-point value is 2⁶⁴ exactly. |
| 16 | The guard's boundary is the boundary — `18446744073709551616ms`, i.e. 2⁶⁴ ms exactly, is refused rather than saturated | **WAS UNCOVERED; covered now.** The whole suite stayed green with the guard written `>`, while `pact check` said `OK — loaded cleanly` and `pact waits` handed a scheduler `18446744073709551615`. See mutation M4. Added to the case lists of `coerce::a_length_of_time_too_long_to_count_…` and `durations_say_what_they_accept::a_length_of_time_nobody_can_count_…` |

Cases 14 and 15 are the residual of counting in floating point at all, they sit
585 million years out, and they are named rather than fixed. Closing them means
parsing the digits directly into a whole number instead of multiplying — a
larger change than this row, and one whose only beneficiary is a document nobody
will write.

---

## Verification

```
$ cargo test --workspace
   … passed=903 failed=0

$ cargo clippy --all-targets -- -D warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.67s      # exit 0

$ cargo test -p pact-schema
test result: ok. 55 passed   (lib)
test result: ok. 8 passed    (durations_say_what_they_accept)
   … and seven further targets, all ok

$ cargo test -p pact-cli --test a_duration_means_what_the_help_says
test result: ok. 9 passed; 0 failed

$ ./scripts/sync-counts.sh
rust=903 adapter=1747 total=2650
wrote 2650 into 4 documents
```

At the door, on the current build:

```
$ ./target/debug/pact check <ws with finishes-within: "999…h 999…h 999…h">
error: 'finishes-within' is 99999999999999999999h …, which is a longer time than this can keep track of.
  rule: schema/too-long-to-count
EXIT=1

$ ./target/debug/pact check <ws with answer-within: "1.001s">
OK — … loaded cleanly (498 settings).
$ ./target/debug/pact waits <same>   → "deadline-ms": 1001
```

**The Python suite was not run.** `adapters/python/src/pact_adapters/` has
twenty-odd modified and four untracked files belonging to the other session in
this tree, and this issue touches no Python. Running it would have measured
their work in progress, not this fix.

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md` had **no row for this**. Measured before
this document existed:
`grep -n "overflow\|panic\|attempt to add" docs/70-PRODUCTION-GAP-REGISTER.md`
returned only C10's and C11's own text, neither about durations. A crash in the
shipped checker was fixed and nothing outside the test file recorded it.

**The row below has been added** to the Class C table (`## Class C — production readiness`), after the C11
row, as **C12** — noting that `C12` is also a queue slug (`underflow-to-zero`,
QUEUE row 14) and `B4` is also a fix-plan item (`park()`), exactly the collision
this register already warns about for its F-numbers:

> | ~~**C12**~~ | **CLOSED, and the closure had a second, quieter half of its own.** A length of time was added up with `*total += (v * mult) as u64`, and a float-to-whole-number cast in Rust SATURATES rather than failing: one oversized part pinned the running total at the largest number there is and the next part went over the top of it. In a debug build — what `cargo run` and this README give an author — `finishes-within: "99999999999999999999h 99999999999999999999h 99999999999999999999h"` killed the command outright: `thread 'main' panicked … attempt to add with overflow`, EXIT=101, no file, no line, no rule. In a release build it did not die, which is worse: `OK — loaded cleanly (498 settings)`, EXIT=0, and `pact waits` handed a scheduler **53,255,926,290,448,384 ms** for three parts that summed just past the top — about 616 days, in place of a figure the author would have recognised as absurd. Now the cast is guarded on `ms >= u64::MAX as f64` (2⁶⁴ exactly, so the guard *is* the boundary) and the addition is `checked_add`; a length of time that does not fit leaves the reader as `Coerced::DurationTooLong` and is refused one layer up by name — `schema/too-long-to-count`, at the author's own line, with a line they can type — for the same reason `0s` is refused at the floor rather than called "not a length of time". `loader/wait-with-no-deadline` no longer asks whether the deadline *parsed*, so a refused deadline is not also reported as never written. **The second half**, found against the fixed build in this pass: the cast TRUNCATED, so `answer-within: 1.001s` reached `pact waits` as `"deadline-ms": 1000` — a millisecond short, silently, and one millisecond away from what the Python port reads. It rounds now. Held by `crates/pact-cli/tests/a_duration_means_what_the_help_says.rs` (9 tests, through the real binary and through `pact waits`), `crates/pact-schema/tests/durations_say_what_they_accept.rs` and three tests in `coerce.rs`; two mutations, each applied, measured and reverted. **What is open**, and named rather than fixed: above 2⁵³ ms the figure kept is not exactly the figure written (measured, `9007199254740993ms` → `9007199254740992`), and the top 616 ms below the limit is refused though it fits — both 585 million years out, both residuals of counting in floating point. See `docs/remediation/B4-duration-overflow-panic.md` | was: one line of one file could kill the shipped checker, and where it did not, the ceiling a runtime enforced was not the one anybody wrote |

---

## What remains open

Stated plainly, because this pass fixed one thing and did not fix these:

1. **Nothing asserts the cross-port safety argument.** Both other ports read
   lengths of time with no top end, and the reason that is safe is that
   `pact check` refuses a superset of what they refuse. That sentence is written
   in `limits.py` and held by no test in either port. (Failure case 13.)
2. **The refusal is only tested through `pact check`.** It is correct at
   `show`, `waits` and `card` — measured — and untested at all three.
   (Failure case 11.)
3. **Two floating-point residuals at the top of the range**, measured, named,
   not closed. (Failure cases 14 and 15.)
4. **The `report.rs` change is held only by a CLI test**, with nothing in
   `pact-loader`'s own suite; and its mutation was reasoned about in this pass
   rather than re-applied.
