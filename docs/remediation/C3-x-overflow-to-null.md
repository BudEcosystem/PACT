# C3 — a figure too big for the machine to hold left the document as something the author never wrote, and documents that differ hashed to one thing

**Severity: high.** · **Status: fixed, and widened during this pass; two items
remain open and are named in [What remains open](#what-remains-open).** ·
**Register: this corrects `docs/70-PRODUCTION-GAP-REGISTER.md:855`, the `C10`
row.** It does *not* touch register row `C3` (`:848`), which is a different
subject entirely — see the naming warning below. Queue row: `docs/remediation/QUEUE.md` row 13.

Every figure in this document names the command that produced it, run against
this working tree on this machine on 2026-08-08. Where a number was measured
against a deliberately broken build, the document says which break produced it
and how the break was made and undone.

> **A naming trap, stated once.** `C3` means two unrelated things in this
> repository. **Queue `C3`** is `x-overflow-to-null` — this document. **Register
> `C3`** (`docs/70-PRODUCTION-GAP-REGISTER.md:848`) is *"the TypeScript port is
> behaviour-only"*. A reader grepping for `C3` finds the wrong one first.

---

## What is wrong

A PACT document may carry `x-…` fields. Those are the author's own private
namespace: PACT does not read them, and promises to hand them back exactly as
they were written. That promise is **AC-1.3** (`docs/00-THESIS.md:410-411`):

> An unknown `x-` field round-trips untouched through import → IR → export.

The *name* of the field round-tripped. The *value* did not, if the author wrote a
figure larger than the machine can hold.

### Reproduction

The fix is in the tree, so to see the original defect it must be temporarily
removed. This was done by deleting one line — `&& f.is_finite()` at
`crates/pact-doc/src/yaml.rs:841` — rebuilding, measuring, and then restoring the
file from a byte copy taken beforehand. The restore was confirmed by checksum:
`sha1sum crates/pact-doc/src/yaml.rs` read
`44099040779c22e4518df26372fd0a161d1d4583` both before and after.

The fixture is a two-file workspace. `workspace.yaml` says `name: shop`, and
`agents/desk/agent.yaml` says:

```yaml
name: Desk
description: A desk.
instructions: Do it.
x-threshold: 1e999
```

With that one line removed from the source:

```
$ ./target/debug/pact show <root> | grep x-threshold
      "x-threshold": null

$ ./target/debug/pact check <root> --deny-warnings
OK — <root> loaded cleanly (9 settings).
$ echo $?
0
```

The author typed a figure. It left the loader as **nothing at all**, and the
checker said the document was clean.

### The half that mattered more

`pact discover` publishes a `sha256:` digest of the workspace — the string a
lockfile pins so that a runtime can tell one version of a document from another.
Two workspaces, identical except for that single line, one saying
`x-threshold: 1e999` and one saying `x-threshold:` (deliberately empty):

```
$ ./target/debug/pact discover <root> | grep -o 'sha256:[0-9a-f]*' | head -1
x-threshold: 1e999    sha256:f248ecc1407214ebeae9ff3ee8e3407bc620e97e201b2877a770f8d75458e74f
x-threshold: (empty)  sha256:f248ecc1407214ebeae9ff3ee8e3407bc620e97e201b2877a770f8d75458e74f
```

**One hash, two different documents.** A lockfile pinning one of them would have
been satisfied by the other, and nothing anywhere could tell them apart.

### The third spelling, which the original fix did not close

The landed `1e999` fix was correct and its tests bit. Measured against the
**fixed** build, the identical defect was still wide open one spelling over — a
plain run of digits too long for a whole number:

```
$ pact show <root>                       # author wrote 99999999999999999999
      "x-big": 1e+20
```

and the digest collision was live again, this time on three documents:

```
99999999999999999999   sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888
99999999999999999998   sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888
100000000000000000000  sha256:2aa9f0c926a7fe5479f8069729d8d956b932e5fda5bc0344ea023281d92b1888
```

*(Those three hashes are the reviewer's measurement against the pre-widening
build, quoted rather than re-measured — that build no longer exists in this tree.
The current, repaired figures are in [Verification](#verification) and are mine.)*

So the defect has **three spellings on one number line**, and only the first was
filed:

| written | was read as | came out of `pact show` as | harm |
|---|---|---|---|
| `1e999` (too big) | infinity | `null` | the value **vanished** |
| `99999999999999999999` (too long) | `1e20` | `1e+20` | the value became a **different figure** |
| `1e-999` (too small) | `0.0` | `0.0` | the value became a **zero nobody wrote** |

Row 1 is C3 as filed. Row 3 is queue rows 14 and 15 (`C12`, `C10`); its fix
landed separately and its own document is still queued, so it appears here only
where this issue's change reached it. **Row 2 is what this pass found still open
against the landed fix, with every test in the C3 test file green over it.**

Where the specification *does* say a number is wanted, the same unguarded read
made the field load clean holding a figure nobody wrote: `settings: temperature:`
given `99999999999999999999` was handed to the runtime as `1e20`, exit 0, no
report. That is the silent degradation **T7** (`docs/00-THESIS.md:227-231`,
*"There is no silent degradation anywhere in the system"*) and **FR-8.1.1**
(`docs/30-FRD.md:204`) forbid outright.

---

## Root cause

One function decides what an unquoted YAML scalar *is*:
`resolve_scalar` in `crates/pact-doc/src/yaml.rs`. Everything downstream — `pact
show`, the canonical form, the digest a lockfile pins, and every type check —
reads that decision and nothing else.

It decided "is this a number?" by asking the machine to read the text as one and
seeing whether that succeeded. **That is not the question**, because the reading
never fails. Asked for a number it cannot hold, the machine does not say "I
cannot hold this" — it quietly hands back the nearest thing it *can* hold:

* at the top of the scale, **infinity** — which is not a figure that can be
  written down at all, so both exits from the document wrote `null` instead;
* in the middle, **a nearby but different figure** — `1e20` where
  `99999999999999999999` was written;
* at the bottom, **zero**.

All three answers are wrong and none was reported.

### The class

This is not the register's Class A (*"declared, tested, wired to nothing"*,
`docs/remediation/REGISTER.md:52`). It is a different and equally repeated class,
which deserves its own name:

> **"A conversion that cannot fail."** A value the target type cannot represent
> is silently replaced by one it can. Because the substitute is *itself a
> perfectly legal value*, every downstream check — including the content digest —
> is structurally blind to the substitution.

The `null` substitution is the sharpest illustration. `null` is a legal value in
this format (an empty setting), so putting it there destroyed the one signal that
anything had gone wrong. **A crash would have been found in a day; a legal-looking
substitute survived all the way to the digest.**

Six closed instances of this class already existed in the tree, four of them in
the same two functions: leading zeros (`007` → `7`, closed at
`crates/pact-doc/src/yaml.rs:775`), duration overflow, token-count overflow,
money overflow, and the two ends of this issue's own number line.

### Why the repository already knew the answer

Four lines above the broken arm, the same function had already resolved the same
tension correctly:

```rust
// crates/pact-doc/src/yaml.rs:775
if digits.len() > 1 && digits.starts_with('0') && !digits.starts_with("0.") {
    return Value::Str(text.to_string());
}
```

A leading-zero form like `007` is kept as text, because reading it as a number
would silently drop the zero — and the comment above it says that is *"the kind
of corruption a non-technical author would never think to check for."* **That is
the identical argument at the other end of the same number line, and it had
simply not been carried there.**

### Why the *widened* half stayed hidden even after the first fix

The first fix asked "is this figure finite?". `1e20` is perfectly finite. **A
guard written in terms of a representation cannot see a defect that
representation absorbs.** The check was correct, well-argued and well-tested, and
blind by construction to the largest spelling of the very defect it was written
for.

The correct question was available one line earlier and was not being listened
to: `text.parse::<i64>()` at `yaml.rs:779` failing **is** the machine saying "I
cannot hold this". The next arm then reached for a type that could not hold it
either and took whatever came back.

---

## Why nothing caught it

Three tests existed whose stated property this defect violates. All three were
blind, and for two different reasons.

**1 — The fuzzer that names this exact defect, in its own failure message.**
`test_a_value_the_author_changes_reaches_the_document`
(`adapters/python/tests/test_nothing_vanishes_between_the_file_and_the_document.py:259`)
is AC-7.1's Property C. Its message states the harm word for word: *"The key
arrives and its value does not, which is worse than losing both — the document
looks complete."* That is C3 exactly.

It was blind because of a four-line filter at `:270`:

```python
# Only prose values: changing a number or an enum produces a refusal,
# which is a different property and is covered above.
candidates = [
    p for p in _paths(doc)
    if isinstance(_at(doc, p), str) and len(_at(doc, p)) > 12
```

The one property that names this defect only ever changes values that are
*already text* and longer than twelve characters, and it changes them by sticking
a marker word on the end — which can only ever produce more text. **The value
class where the defect lives is excluded by construction**, on an assumption this
issue proves false: for an `x-` field, changing a number produced neither a
refusal nor an arrival. It produced `null` and exit 0.

**2 — The property that looks like it covers this and does not.**
`test_every_key_the_author_wrote_appears_in_the_document` (`:156`) walks the
document with `_every_key` (`:94`), which collects key names and recurses — it
never records a leaf value. It would have happily confirmed that the key
`x-threshold` arrived. It did arrive. Its value did not.

**3 — The corpus contains none of the mechanism the promise is about.** All three
properties mutate `examples/refund-desk`. Measured:

```
$ grep -rn "^\s*x-" examples/ | wc -l
0
```

**There is not one `x-` field anywhere in the worked example.** The mechanism
whose round-trip promise AC-1.3 makes, and which C3 broke, has zero instances in
the only tree the fuzzer walks. Even a value-walking Property C would have needed
a corpus change to see it.

**4 — On the Rust side the digest test was equally close.**
`canonical.rs::any_value_change_moves_the_digest` asserts precisely the invariant
that broke, but over a corpus of small text and a two-digit integer. Its third
case removes a whole line, so it tests *key removal* — which does move the digest
— rather than a value being nulled with its key retained, which is what happened.
Alongside it, `numbers_that_mean_the_same_thing_agree` asserts that `1.0` and
`1.00` share a digest, establishing that number-formatting collisions are
*intended* with no stated bound on how far that may go. That is the licence under
which `1e999` → `null` looks like more of the same.

**5 — And for the third spelling, no test wrote it down at all.** The reviewer's
grep for the shape across every language in the repository returned twenty hits,
and **every one carried a unit suffix** (`…m`, `…h`) — which makes it text, so it
never enters the number arm. Zero bare-integer cases existed anywhere.

So the honest summary is not "there was no test". It is: **two tests were scoped
to a value class that cannot exhibit the defect, one to a corpus that does not
contain the field the promise is about, and the widened spelling was written down
by nobody.**

---

## The fix

The float half landed first (edits 1, 6 and 7). The integer half and the
diagnostic repairs landed during this remediation pass (edits 2–5). All line
numbers below were read from the tree at
`sha1sum` `44099040779c22e4518df26372fd0a161d1d4583` (`yaml.rs`),
`ebd7d6412c93ffe60322ece3eab5377963f6e563` (`coerce.rs`),
`d7e1ea7e339fa87ec0645ae074c12e2022f5bc9d` (`lib.rs`).

`crates/pact-doc/src/yaml.rs:845` is the **only** place in the whole workspace
where a document ever becomes a float (`grep -rn "Value::Float(" --include=*.rs
crates/` returns that line plus `value.rs:67`/`:220` and `canonical.rs:64`, which
read rather than build, and the rest are test assertions). That is why guarding
there is total for anything an author can write.

### 1 — `crates/pact-doc/src/yaml.rs:841` · do not read as a number what cannot be held as one

The float arm is now a four-part test, and a scalar that fails any part is kept
as the text it was written as:

```rust
if let Ok(f) = text.parse::<f64>()
    && f.is_finite()                              // ← this issue
    && !underflowed_to_zero(f, text)              // ← C10/C12, landed later
    && text.chars().any(|c| c.is_ascii_digit())   // ← predates both
{
    return Value::Float(f);
}

Value::Str(text.to_string())
```

The digit test is what has always kept YAML's own words `.inf` and `.nan` as the
text they were written as, so those never reach this arm at all.

### 2 — `crates/pact-doc/src/yaml.rs:799` · the missing arm, added this pass

```rust
if !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit()) {
    return Value::Str(text.to_string());
}
```

Placed between the whole-number read at `:779` and the float arm at `:841`. A
scalar that is an optional sign plus ASCII digits and nothing else, which the
whole-number read has **already refused**, is kept as written.

**It refuses nothing legitimate**, and that narrowness is the entire argument for
it: `1e10` carries an exponent, `1.5` carries a point, and every whole number
that fits has already left one line earlier. Measured: `9223372036854775807`
still arrives as a number; `1e10` and `1.5` are unchanged.

### 3 — `crates/pact-schema/src/coerce.rs:78` · `whole_number_past_holding`

```rust
pub(crate) fn whole_number_past_holding(written: &str) -> bool {
    let text = written.trim();
    let digits = text.strip_prefix(['+', '-']).unwrap_or(text);
    !digits.is_empty()
        && digits.bytes().all(|b| b.is_ascii_digit())
        && text.parse::<i64>().is_err()
}
```

**Edit 2 alone does not close the typed-field half, and this is the subtle
part.** Once the text is kept, a `settings: temperature:` field reads it back and
gets `1e20` — which is *finite*. No finiteness test anywhere can refuse it. So
the question has to be asked of the **text**, because the figure is the one thing
that no longer says anything. This is the same reason `underflowed_to_zero`
(`lib.rs:2750`) reads the text at the other end of the same scale.

### 4 — `crates/pact-schema/src/lib.rs` · the arms of `Schema::check_ceiling`

| line | arm | answers |
|---|---|---|
| `:1803` | `Number(n) if !n.is_finite()` | `schema/too-big-to-count` |
| `:1819` | `Number(n)` + `whole_number_past_holding(text)` | `schema/too-big-to-count` |
| `:1828` | `IntegerTooBig(n)` | `schema/too-big-to-count` for whole-number fields |
| `:1833` | `Threshold` if not finite | `schema/too-big-to-count` |
| `:1842` | `Threshold` + `whole_number_past_holding`, operator stripped | the same sentence as the number it compares against |
| `:1889` | `Size(0)` + `underflowed_to_zero` | `schema/too-small-to-count` |

`past_counting` (`lib.rs:2762`) writes the sentence, one function for every type
so that the same figure cannot drift into different wordings. It gives each end
of the number line its own sentence, because an author told that `-1e999` is
*"more than"* anything would go looking for a smaller number and find the one
they already wrote:

```
'temperature' is 1e999, which is more than this can keep track of.
  fix: Write `temperature: 10`, or any smaller number, or remove the line.

'temperature' is -1e999, which is further below zero than this can keep track of.
  fix: Write `temperature: 10`, or any number closer to zero, or remove the line.
```

### 5 — `crates/pact-schema/src/coerce.rs` · three readers stop lying about spelling

The rule the repository holds itself to, stated in its own comments at
`coerce.rs:394` and `lib.rs:1792`: **never tell an author that a correctly
spelled line is the wrong type.** That sends them hunting for a typo that is not
there. Before this pass, the newly-kept text triggered exactly that sentence on
four types. Repaired:

* **`integer` (`:225`)**, new. A digit run past what a whole number can hold
  leaves as `Coerced::IntegerTooBig`. `inf`/`nan` carry no digit and stay
  refused-as-a-word; `1.5` is not a whole number that ran off an end and stays
  refused too.
* **`size` (`:515`, `:529`)**. The old blanket refusal was split: `nan` and
  negatives stay a word, while a positive figure past the end **carrying a digit**
  becomes `Coerced::SizeTooBig`.
* **`duration` (`:325`)**. A bare figure is a number of seconds by this
  function's own rule, so a bare figure past the end becomes
  `Coerced::DurationTooLong` rather than being read letter-by-letter and rejected.

The `has_a_digit` predicate (`lib.rs:2717`) is the line between *a figure that
overflowed* and *a word written where a figure goes*. It is stated once and
reused, not re-derived per type.

### 6 and 7 — the two exits, deliberately left as they are

`crates/pact-doc/src/value.rs:220` and `crates/pact-doc/src/canonical.rs:64`
still write `null` for a non-finite figure. Those fallbacks were **kept and
re-commented**, because they are now unreachable from any file — nothing can
build such a value from a document any more — and exist only for a value a
library caller constructs by hand. A digest function must return a digest rather
than crash.

---

## Alternatives rejected

**Fix it at the exits instead** — make `pact show` and the digest print the
author's text rather than `null`. Rejected. There are two exits today and the
number is growing, so the rule would have to be restated at each one, and the
document would still be carrying infinity internally for anything downstream to
trip over. Fixing it where the value is *created* makes every exit correct
without their having to know.

**Refuse the document outright** — report `doc/number-too-big` at parse time.
Rejected, and actively pinned against: `a_number_too_big_to_hold_is_not_a_problem_of_its_own`
asserts that `pact check --deny-warnings` exits **0** on `x-threshold: 1e999`.
AC-1.3 says `x-` round-trips untouched and PACT does not read it, so there is
nothing to complain about. Complaining would break the field's whole promise.

**"Only accept a figure that reads back as exactly its own text."** The general
rule, and it would have caught all three spellings in one line. Measured and
rejected, recorded at `docs/70-PRODUCTION-GAP-REGISTER.md:855`: it refuses
`1e10`, which comes back as `10000000000.0` — the same number, reformatted, and
nobody would call that corrupted. **Note what the rejection cost**: the narrow
rules that replaced it covered the two ends and left the middle open for a
release. The digits-only rule in edit 2 is the version that has no `1e10`
problem, because `1e10` is not digits-only.

**Keep the infinity and special-case only the digest.** Rejected: it fixes the
lockfile and leaves `pact show` still printing `null`, so the author still
watches their value disappear. That is half the defect, and the visible half.

**Refuse the overflow in the type reader rather than at the ceiling** — one line
shorter. Rejected in code: it produces *"should be a number, but it is some
text"* for `temperature: 1e999`, a line spelled exactly the way a number is
spelled. The figure is carried up instead and refused at the author's own line,
where the field's name and position are known.

**Three repairs the adversarial review asked for and measurement says are
wrong**, recorded because rejecting them is a finding:

* **`context-at-least: -1e999` → "too big"**. It would print *"is -1e999, which
  is more than this can keep track of"*, offering the fix *"any smaller
  number"*. A false sentence and a harmful edit: a count of tokens below zero is
  not a count at all, whatever its size, and `context-at-least: -5` already goes
  out the same door. Negatives stay a word, pinned by
  `a_word_where_a_size_goes_is_still_a_word`.
* **`finishes-within: -1e999` → "too long"**. Same argument; `-5s` is refused by
  the same door.
* **`tool-calls-at-most: 1.5` → "too big"**. The existing sentence — *"should be
  a whole number, but it is a number"* — is **true** about it. A fraction is not
  a whole number that ran off an end; it is the wrong kind of figure.

---

## Blast radius

**Upward — who calls the changed function.** Exactly one call site,
`crates/pact-doc/src/yaml.rs:600`, reached only through the crate's single public
entry point. There is no second scalar reader anywhere: `markdown.rs`, the loader
and the CLI contain no float parsing of their own. Markdown front matter
re-enters through the same function, so `.md` documents are covered by the same
guard, and JSON input travels the same path.

**Downward — every consumer, each checked by measurement rather than by reading.**

| consumer | effect |
|---|---|
| `pact show` | prints the author's text instead of `null` / a different figure |
| the digest | documents that differ now differ; measured below |
| text fields | an overflow used to arrive as the word `inf`; now arrives as written — an improvement |
| number / comparison fields | used to load clean holding a wrong figure; now refused by name |
| size fields | used to say *"wrong type"*; now says *"too big to count"* |
| whole-number fields | same repair |
| duration fields | same repair |
| percentage fields | **no change** — the figure was outside the allowed range before and after |
| money fields | untouched; every money spelling carries a currency and was already text |

**The digest of the shipped example does not move.** This is the claim that
matters most, because moving it would invalidate every existing lockfile:

```
$ ./target/debug/pact discover examples/refund-desk | grep -o 'sha256:[0-9a-f]*' | head -1
sha256:87cb01fce41246bb8add4dc2975daa101324b6087319fd8103adf618a855db66
```

That is the same digest recorded before the widening edit. And no shipped fixture
can be affected, because none contains a figure of the shape at issue:

```
$ grep -rEn '(^|[^0-9.eE-])[0-9]{19,}([^0-9.]|$)' --include=*.yaml --include=*.yml --include=*.md examples/ spec/ tests/
(no output)
```

**The five honesty channels are not affected, and the mechanism was checked
rather than assumed.** `unmetered`, `unenforced`, `unwatched`, `never_reached`
and `unretrieved` (`adapters/python/src/pact_adapters/harness.py:136-190`) are
all statements about what happened while an agent *ran*. This change is in the
document layer, which sits before the loader, which sits before any runtime. An
`x-` value reaches no adapter at all — `x-` is recognised only as a key, never as
a value that is honoured — and a typed field carrying an overflowing figure is
now refused by `pact check` before a runtime is entered.

**Both ports.** Neither adapter re-reads the author's YAML; that boundary is held
by `adapters/python/tests/test_no_adapter_reads_the_authors_files.py`
(`24 passed in 0.28s`). Both ports receive the already-resolved document and
inherit this fix rather than needing their own. The TypeScript port contains no
YAML reader at all, so it correctly has no twin of this change.

Cross-port parity was measured directly rather than assumed:

```
$ cd adapters/python && uv run python -c "import yaml; ..."
k: 1e999                    -> str   '1e999'
k: 1e-999                   -> str   '1e-999'
k: 1.0e999                  -> str   '1.0e999'
k: 99999999999999999999     -> int   99999999999999999999
k: 9223372036854775807      -> int   9223372036854775807
```

The Python reader keeps every one of these figures exactly. So does the Rust
reader now. **The digits agree across both ports; the type does not** — Rust
hands back the digit run as text where Python hands back a whole number. See
[What remains open](#what-remains-open).

**The published counts moved by ten and were reconciled.** `README.md:73` and
`:79` read `2905 tests (944 Rust + 1961 adapter)`, and `cargo test --workspace`
counts 944. `test_the_headline_test_count_is_the_count.py` is the gate that
forces this and it passes.

**One interface note.** The type-reader result gained a new variant
(`IntegerTooBig`). Every place that inspects it outside its own file was
enumerated; all are forms with a fallback, so nothing broke, and
`cargo clippy --all-targets -- -D warnings` exits 0.

**The four-artifact rule (§7.28) is not engaged.** That rule governs the
author's own key *names*; this change adds, removes and renames no key.

---

## The test

**Primary door — the real shipped binary.** Every test in
`crates/pact-cli/tests/a_number_too_big_to_hold_is_kept_as_it_was_written.rs`
(14 tests) launches the actual `pact` executable against a real workspace written
to disk and reads what it prints. There is no internal seam, no hand-built input,
and no mock. Measured: `test result: ok. 14 passed; 0 failed`.

| test | what it asserts | door |
|---|---|---|
| `a_number_too_big_to_hold_survives_show` (`:252`) | `1e999`, `1e400` and `-1e999` all come back as written, **and the word `null` appears nowhere in the output** | `pact show` |
| `a_whole_number_too_big_to_hold_survives_show_too` (`:279`) | the digit-run spelling, plus `9223372036854775807` asserted still a number — pinning the rule to stop exactly at the edge of what can be held | `pact show` |
| `three_documents_that_differ_do_not_digest_the_same` (`:324`) | the headline harm, stated as the thing a lockfile does | **`pact discover`** |
| `a_number_too_big_to_hold_is_not_a_problem_of_its_own` (`:343`) | exit **0** — an `x-` field is the author's own space | `pact check --deny-warnings` |
| `a_number_field_given_one_is_refused_by_name` (`:360`) | `too-big-to-count`, the value, the file and line, a typeable fix, **and `!contains("wrong-type")`** | `pact check` |
| `a_number_field_given_the_far_bottom_end_says_so` (`:394`) | the negative gets *"further below zero"*, not the positive sentence | `pact check` |
| `a_number_field_given_a_whole_number_past_holding_is_refused_by_name` (`:422`) | the digit-run spelling on a number field, both signs | `pact check` |
| `a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo` (`:472`) | the condemned sentence is gone from whole-number fields | `pact check` |
| `a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo` (`:532`) | same, for durations | `pact check` |
| `the_word_infinity_where_a_number_goes_is_still_a_typo` (`:573`) | `inf`/`nan`/`Infinity` stay *wrong type*, with `!contains("too-big-to-count")` | `pact check` |
| `a_bar_no_score_could_ever_clear_is_refused_too` (`:596`) | both spellings on a benchmark bar; the fix line is typeable **where it is reported** | `pact check` |
| `the_words_for_infinity_are_still_plain_text` (`:669`) | `.inf`, `-.inf`, `.nan` stay text | `pact show` |
| `ordinary_numbers_are_untouched` (`:692`) | `1.5`, `1e10`, `0.5`, `42`, `-3.25` unmoved | `pact show` |
| `an_ordinary_number_field_still_takes_an_ordinary_number` (`:716`) | a normal settings block still loads | `pact check` |

**Second door — the digest, at the unit layer.**
`crates/pact-doc/src/yaml.rs:966`
`a_number_too_big_to_hold_no_longer_digests_as_nothing` asserts directly that a
document with the figure and one without do not hash alike, and that ordinary
numbers still produce exactly the canonical string they always did. Its siblings
`a_number_too_big_to_hold_stays_text` (`:930`) and
`a_whole_number_past_holding_keeps_its_digits` (`:992`) pin the shape of the
value itself. This calls the same digest function the CLI calls — verified, not
assumed (`crates/pact-cli/src/discover.rs:195`).

**Third door — the type layer.**
`crates/pact-schema/src/coerce.rs:897` `a_figure_past_the_end_is_kept_and_a_word_is_not`
and `:825` `a_whole_number_past_holding_is_too_big_rather_than_a_typo` pin the
figure being carried up and the word being refused.

**Sibling files that hold the neighbouring spellings:**
`a_size_this_cannot_count_is_refused_rather_than_changed.rs` (4 tests, including
`the_spelling_the_help_prescribes_is_covered_too`, which exists because the
original test wrote its figure in quotes and so certified a path no author could
reach) and `a_number_too_small_to_hold_is_kept_as_it_was_written.rs` (11 tests).

---

## The mutation

**Three mutations were performed by me, in this session, on this tree.** Each was
applied alone, measured, and reverted from a byte copy taken beforehand; every
revert was confirmed by checksum before the next began. Green baselines first:

```
$ cargo test -p pact-cli --test a_number_too_big_to_hold_is_kept_as_it_was_written
test result: ok. 14 passed; 0 failed
$ cargo test -p pact-cli --test a_size_this_cannot_count_is_refused_rather_than_changed
test result: ok. 4 passed; 0 failed
$ cargo test -p pact-cli --test a_number_too_small_to_hold_is_kept_as_it_was_written
test result: ok. 11 passed; 0 failed
$ cargo test -p pact-doc
test result: ok. 52 passed; 0 failed
```

### Mutation A — remove `&& f.is_finite()` (`yaml.rs:841`), the original C3 fix

```
pact-cli C3 file   FAILED. 9 passed; 5 failed
    a_number_too_big_to_hold_survives_show
    a_number_field_given_one_is_refused_by_name
    a_number_field_given_the_far_bottom_end_says_so
    a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo
    a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo
pact-doc           FAILED. 50 passed; 2 failed
    yaml::tests::a_number_too_big_to_hold_stays_text
    yaml::tests::a_number_too_big_to_hold_no_longer_digests_as_nothing
```

and through the rebuilt binary, the founding defect itself:

```
"x-threshold": null
pact check --deny-warnings   →  OK — loaded cleanly (9 settings).   exit 0
digest, x-threshold: 1e999   →  sha256:f248ecc1407214ebeae9ff3ee8e3407bc620e97e201b2877a770f8d75458e74f
digest, x-threshold: (empty) →  sha256:f248ecc1407214ebeae9ff3ee8e3407bc620e97e201b2877a770f8d75458e74f
```

**The control that makes this clean:** the empty-value digest is
`sha256:f248ecc1…` in the broken build *and* in the repaired build. The fix moved
the overflowing document and left everything else exactly where it was.

### Mutation E — remove the digits-only arm (`yaml.rs:799-801`)

```
pact-cli C3 file   FAILED. 10 passed; 4 failed
    a_whole_number_too_big_to_hold_survives_show_too
    three_documents_that_differ_do_not_digest_the_same
    a_number_field_given_a_whole_number_past_holding_is_refused_by_name
    a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo
size file          FAILED. 3 passed; 1 failed
    the_spelling_the_help_prescribes_is_covered_too
pact-doc           FAILED. 50 passed; 2 failed
    yaml::tests::a_whole_number_past_holding_keeps_its_digits
    yaml::tests::a_number_too_big_to_hold_no_longer_digests_as_nothing
```

Note which size test goes red and which stays green: the unquoted spelling fails,
the quoted one passes. **That is precisely the gap that survived the first fix**,
reproduced on demand.

### Mutation F — remove the `Number` + `whole_number_past_holding` arm (`lib.rs:1819`)

```
pact-cli C3 file   FAILED. 13 passed; 1 failed
    a_number_field_given_a_whole_number_past_holding_is_refused_by_name
```

and through the rebuilt binary:

```
$ pact check <ws with settings: temperature: 99999999999999999999>
OK — loaded cleanly (10 settings).                       exit 0
$ pact show <same>
        "temperature": "99999999999999999999"
```

### The load-bearing result, which no reviewer stated

**Mutations E and F do not substitute for each other.** Look at what Mutation F
prints above: the value is *kept perfectly* — edit 2 is doing its job — and the
document still **loads clean with a figure nobody wrote**, because the kept text
reads back as a finite `1e20` that no finiteness guard can see.

> **Edit 2 stops the value being lost. Edit 3+4 stop it being used.** Each was
> reverted alone and watched go red on a different test. Either one alone leaves
> half the defect standing.

### Restoration

```
$ sha1sum crates/pact-doc/src/yaml.rs crates/pact-schema/src/lib.rs crates/pact-schema/src/coerce.rs
44099040779c22e4518df26372fd0a161d1d4583  crates/pact-doc/src/yaml.rs
d7e1ea7e339fa87ec0645ae074c12e2022f5bc9d  crates/pact-schema/src/lib.rs
ebd7d6412c93ffe60322ece3eab5377963f6e563  crates/pact-schema/src/coerce.rs
```

Identical to the pre-mutation snapshot, and the suites are green again (14 / 52).

**Mutations C, D, G, H and I** — covering the comparison arm, the digit
re-admission guard, the whole-number reader, the size reader and the size
underflow arm — are recorded in prose in the three test files' own module
headers. **I did not re-perform those five in this session.** They are reported
here as the earlier passes' claims, not as my measurements.

> **A trap worth recording, because it silently invalidates measurements.**
> `cargo build -p pact-cli` can report success in a fraction of a second
> *without* rebuilding the binary after a change in a crate beneath it. A
> reviewer measured pre-fix behaviour through a stale `target/debug/pact` while
> the source on disk contained the fix. Every binary measurement in this document
> was taken after a forced rebuild, and each mutation run carries a sanity witness
> — a command whose output must differ between the two states — so a stale binary
> shows up immediately.

---

## Failure cases

### The `x-` promise — the field this issue is about

| case | status |
|---|---|
| `x-threshold: 1e999` survives `pact show` as written | covered-by `a_number_too_big_to_hold_survives_show` |
| `x-note: 1e400` — the smaller overflow | covered-by same |
| `x-below: -1e999` — the negative end | covered-by same |
| the word `null` appears nowhere in the output | covered-by same |
| `x-big: 99999999999999999999` survives `pact show` | covered-by `a_whole_number_too_big_to_hold_survives_show_too` |
| `9223372036854775807` still read as a number (the boundary) | covered-by same |
| `9223372036854775808` kept as written (one past the boundary) | covered-by same |
| an `x-` overflow is **not** itself a complaint, exit 0 | covered-by `a_number_too_big_to_hold_is_not_a_problem_of_its_own` |

### The digest — the harm that mattered

| case | status |
|---|---|
| `x-threshold: 1e999` vs `x-threshold:` differ | covered-by `a_number_too_big_to_hold_no_longer_digests_as_nothing` (unit) |
| three digit-run documents differ from each other | covered-by `three_documents_that_differ_do_not_digest_the_same` (**through `pact discover`**) |
| ordinary numbers still produce the same canonical string | covered-by the assertion inside the unit test above |
| the shipped example's digest does not move | covered-by measurement in [Blast radius](#blast-radius); **not pinned by a test** |

### Typed fields — where the specification says a figure is wanted

All rows below were measured by me through the real binary in this session.

| line | rule | status |
|---|---|---|
| `temperature: 1e999` | `too-big-to-count` | covered-by `a_number_field_given_one_is_refused_by_name` |
| `temperature: -1e999` | `too-big-to-count`, *"further below zero"* | covered-by `a_number_field_given_the_far_bottom_end_says_so` |
| `temperature: 99999999999999999999` | `too-big-to-count` | covered-by `a_number_field_given_a_whole_number_past_holding_is_refused_by_name` |
| `temperature: -99999999999999999999` | `too-big-to-count`, *"further below zero"* | covered-by same |
| `temperature: 0.7` | loads, exit 0 | covered-by `an_ordinary_number_field_still_takes_an_ordinary_number` |
| `temperature: inf` | `wrong-type` — correct, it is a word | covered-by `the_word_infinity_where_a_number_goes_is_still_a_typo` |
| `context-at-least: 99999999999999999999` | `too-big-to-count` | covered-by `the_spelling_the_help_prescribes_is_covered_too` |
| `context-at-least: "99999999999999999999"` | `too-big-to-count` — quoted and unquoted agree | covered-by same |
| `context-at-least: 1e999` / `1e999k` / `…m` | `too-big-to-count` | covered-by `a_number_of_tokens_nobody_can_count_is_refused_at_check_time` |
| `context-at-least: 1e-999` / `1e-999m` / `0.0000001k` | `too-small-to-count` | covered-by `a_count_of_tokens_that_underflowed_is_refused_rather_than_read_as_none` |
| `context-at-least: -1e999` / `inf` / `nan` | `wrong-type` — deliberate, see Alternatives | covered-by `a_word_where_a_size_goes_is_still_a_word` |
| `context-at-least: 32k` / `200000` / `0` | loads, exit 0 | covered-by `every_size_the_help_advertises_still_loads` |
| `tool-calls-at-most: 9223372036854775808` | `too-big-to-count` | covered-by `a_whole_number_field_is_told_its_figure_is_too_big_not_that_it_is_a_typo` |
| `tool-calls-at-most: 9223372036854775807` / `25` | loads, exit 0 | covered-by same |
| `tool-calls-at-most: 1.5` | `wrong-type` — a true sentence | covered-by same |
| `finishes-within: 1e999` / `99999999999999999999` | `too-long-to-count` | covered-by `a_length_of_time_field_is_told_its_figure_is_too_long_not_that_it_is_a_typo` |
| `finishes-within: 30s` / `1m30s` / `500ms` | loads, exit 0 | covered-by same |
| `MMLU: "> 1e999"` / `"> 99999999999999999999"` | `too-big-to-count`, fix typeable where reported | covered-by `a_bar_no_score_could_ever_clear_is_refused_too` |
| `MMLU: "> inf"` | `wrong-type` | covered-by same |
| `.inf` / `-.inf` / `.nan` in an `x-` field | stay plain text | covered-by `the_words_for_infinity_are_still_plain_text` |

### Still uncovered

| case | status |
|---|---|
| `x-threshold: 1e999` and `x-threshold: "1e999"` share one digest | **UNCOVERED** — see [What remains open](#what-remains-open) |
| an `x-` figure comes back as text where the author wrote a number (type, not digits, is lost) | **UNCOVERED** — no test asserts the JSON *type* of a round-tripped `x-` value |
| Python reads a digit run as a whole number where Rust reads it as text | **UNCOVERED** — no cross-port test compares scalar types; not reachable in production because no adapter reads the author's files |
| the shipped example's digest does not move | **UNCOVERED by a test** — measured here, but nothing in the suite would catch a future change that moved it |

---

## What remains open

The adversarial review raised seven findings. Five were repaired and are
described above. **Two were reproduced, judged real, and are not fixed.** They
are recorded here rather than left in a transcript.

**1 — The quoting collision. The digest collision was narrowed, not deleted.**
Measured by me, with the workspace name held constant so only the one line
differs:

```
x-threshold: 1e999      sha256:29975f3e0dab70cae218f31dded3aaf84efc24107db956c23a6c802fde3445bb
x-threshold: "1e999"    sha256:29975f3e0dab70cae218f31dded3aaf84efc24107db956c23a6c802fde3445bb

x-big: 99999999999999999999      sha256:9bfa426511c43db305a26bfff1d3044f8ecdeb484b5cb01e6574c6bbedd01ed1
x-big: "99999999999999999999"    sha256:9bfa426511c43db305a26bfff1d3044f8ecdeb484b5cb01e6574c6bbedd01ed1
```

Before the fix these two spellings produced **different** digests, because one
was a broken number and the other was text. Now both are text, so they agree.

Whether this is a defect is a genuine design question and this document does not
settle it. The case for calling it correct: PACT has decided the figure is text,
and two documents whose values are the same text are the same document. The case
for calling it a defect: an author who quotes deliberately has expressed
something, and AC-1.3 promises `x-` fields come back *untouched*. **What is not
in doubt is that the round trip is type-lossy** — a figure written as a bare
number comes back quoted, and nothing reports that. No test pins either
behaviour, so a future change could flip it in silence.

**2 — Cross-port type divergence at the digit-run spelling.** Measured above:
Python reads `99999999999999999999` as a whole number, exactly; Rust now keeps it
as text. **The digits agree — neither port corrupts the value, which is the harm
this issue is about — but the type does not.** This is not reachable in
production today, because no adapter re-reads the author's files
(`test_no_adapter_reads_the_authors_files.py`, 24 passed). It is recorded because
that boundary is the only thing keeping it harmless, and no test compares the two
ports' scalar typing.

**Neither open item has a register row.** Both belong to the same class this
document names, and both should be filed rather than carried in prose.

**One process note, not a defect.** `cargo fmt --check` was not run as a gate:
this repository has no `rustfmt.toml`, `scripts/test-all.sh` never invokes it,
and 69 files across the three crates already differ from default formatting.
Reformatting them is not this issue's business.

---

## Verification

Run from the repository root. The rebuild is not optional — see the stale-binary
note in [The mutation](#the-mutation).

```
$ touch crates/pact-doc/src/yaml.rs && cargo build -p pact-cli
```

**1 — The `x-` promise, both spellings.** A workspace whose agent file carries
`x-threshold: 1e999`, `x-note: 1e400`, `x-below: -1e999`:

```
$ ./target/debug/pact show <root>
      "x-threshold": "1e999",
      "x-note": "1e400",
      "x-below": "-1e999"
$ ./target/debug/pact show <root> | grep -c null
0
$ ./target/debug/pact check <root> --deny-warnings ; echo $?
OK — <root> loaded cleanly (11 settings).
0
```

and with `x-a: 9223372036854775807`, `x-b: 9223372036854775808`,
`x-c: 99999999999999999999`, `x-d: 123456789012345678901234567890`:

```
      "x-a": 9223372036854775807,
      "x-b": "9223372036854775808",
      "x-c": "99999999999999999999",
      "x-d": "123456789012345678901234567890"
```

The boundary is exactly the largest whole number that can be held: one below it
is a number, one above it is kept as written.

**2 — The digest. Six documents, six hashes.** Workspace name held constant; only
the one line differs:

```
x-threshold: 1e999               sha256:29975f3e0dab70cae218f31dded3aaf84efc24107db956c23a6c802fde3445bb
x-threshold:                     sha256:f248ecc1407214ebeae9ff3ee8e3407bc620e97e201b2877a770f8d75458e74f
x-threshold: 1e400               sha256:93542989b1f95df19c809697d3fca9c282f899cf87486abae36eaead772ca993
x-big: 99999999999999999999      sha256:9bfa426511c43db305a26bfff1d3044f8ecdeb484b5cb01e6574c6bbedd01ed1
x-big: 99999999999999999998      sha256:03eae7c5b662baebf520dd5405bb7c28a3bef9b5764512d0fc536d4ff43520a5
x-big: 100000000000000000000     sha256:199135bac01f5e46a86151bce25a75f2fd77b56a2aefc38e0dc02428b95e9768

$ ... | sort -u | wc -l
6
```

**3 — The shipped example does not move.**

```
$ ./target/debug/pact discover examples/refund-desk | grep -o 'sha256:[0-9a-f]*' | head -1
sha256:87cb01fce41246bb8add4dc2975daa101324b6087319fd8103adf618a855db66
```

**4 — The scoped suites.**

```
$ cargo test -p pact-cli --test a_number_too_big_to_hold_is_kept_as_it_was_written
test result: ok. 14 passed; 0 failed
$ cargo test -p pact-cli --test a_size_this_cannot_count_is_refused_rather_than_changed
test result: ok. 4 passed; 0 failed
$ cargo test -p pact-cli --test a_number_too_small_to_hold_is_kept_as_it_was_written
test result: ok. 11 passed; 0 failed
$ cargo test -p pact-doc
test result: ok. 52 passed; 0 failed
```

**5 — The full gate.**

```
$ cargo test --workspace
EXIT=0    91 test binaries, 944 passed, 0 failed

$ cargo clippy --all-targets -- -D warnings
EXIT=0

$ cd adapters/python && uv run pytest tests/ -q
1954 passed, 7 skipped in 142.15s
```

`README.md:73` reads `2905 tests (944 Rust + 1961 adapter)`, and 944 is what
`cargo test --workspace` counts.

---

## Register update

**No row in `docs/70-PRODUCTION-GAP-REGISTER.md` needs to be created, and row
`C3` must not be touched** — register `C3` (`:848`) is the TypeScript-port row and
has nothing to do with this defect.

The row that covers this number line is **`C10` at `:855`**, which is already
struck through as closed. Its claim is now **too narrow in one specific way** and
should be corrected. It currently opens:

> **CLOSED, at both ends of the number line and at both doors.** The OVERFLOW
> half was already shut: `resolve_scalar` refuses to read a scalar it cannot hold
> as a number …

**The correction to make:** the phrase *"at both ends of the number line"* should
become *"at both ends of the number line and in the middle"*, and the row should
record the third spelling, in these terms:

> The MIDDLE of the same line was open for a release and is now shut too: a bare
> run of digits past what a whole number can hold — `99999999999999999999` — is
> not past what a float can hold, so the `is_finite` guard was blind to it by
> construction. It was read as `1e20`, `pact show` printed `1e+20`, and
> `99999999999999999999`, `…98` and `100000000000000000000` digested to one hash.
> Closed by a digits-only rule at `crates/pact-doc/src/yaml.rs:799` — the same
> judgement as the leading-zero rule at `:775` — plus
> `coerce::whole_number_past_holding` and four `Schema::check_ceiling` arms,
> because the kept text reads back as a **finite** figure that no finiteness
> guard can refuse. Held by 14 tests in
> `crates/pact-cli/tests/a_number_too_big_to_hold_is_kept_as_it_was_written.rs`,
> mutations A, E and F re-measured.

The row's test count for the underflow file should also read **eleven**, not ten:
`a_number_too_small_to_hold_is_kept_as_it_was_written.rs` gained
`a_count_of_tokens_that_underflowed_is_refused_rather_than_read_as_none` during
this pass. Measured: `test result: ok. 11 passed; 0 failed`.

**Two new rows should be filed** for the items in
[What remains open](#what-remains-open): the quoting collision and the cross-port
scalar-type divergence. Neither has a row or a test today.

---

## What a reader should take from this

**A guard written in terms of a representation cannot see a defect that
representation absorbs.** `is_finite` was a correct, well-argued, well-tested fix,
and it was blind by construction to the largest spelling of the defect it was
written for, because `1e20` is finite. The class was *"a figure the machine
cannot hold"*, and finiteness only tests one of the three ways a machine fails to
hold one.

**The test that proves a fix works is not the test that proves the class is
closed.** Nine tests, all green, all honest, all about `1e999` — while the test
file's own title was false in the shipped product for a different spelling of the
same sentence. The question that would have caught it is *"what are the other
ways to write a figure this cannot hold?"*, asked of the source rather than of
the fix.

**A test that builds its own input can certify a path an author can never
reach.** The size test wrapped its figure in quotes before handing it over, so it
exercised a value the document layer never produced for that spelling. The same
figure, quoted and unquoted, got two different answers for a full release. Only a
test through the real binary finds that.

**A comment asserting a general rule is a claim, and claims get measured.** The
long comment above the fix said what was written *"is kept exactly as written…
that is lossless"*, and two commands falsified it. It was believed for a release
precisely because it was well written.
