# C12 — a figure too small for the machine to hold became an ordinary zero, and nothing downstream could tell it from a zero somebody meant

**Severity: high.** · **Status: fixed at both doors; three further defects found
by attacking the landed fix are fixed with it; four things remain open and are
named in [What remains open](#what-remains-open).** · **Register: closes and
corrects `docs/70-PRODUCTION-GAP-REGISTER.md:855`, the `C10` row.** · Queue row:
`docs/remediation/QUEUE.md` row 14.

Every figure in this document names the command that produced it, run against
this working tree on this machine on 2026-08-08. Where a number was measured
against a deliberately broken build, the document says which break produced it,
how the break was made, and how it was undone. Digests quoted here come from the
fixture described in [Reproduction](#reproduction); a different fixture gives
different hashes, so what matters in every digest claim is whether two hashes are
the SAME or DIFFERENT, never their literal value.

> **A naming trap, stated once.** `C12` means two unrelated things in this
> repository. **Queue `C12`** is `underflow-to-zero` — this document.
> **Register `C12`** (`docs/70-PRODUCTION-GAP-REGISTER.md:857`) is the duration
> overflow panic, which is `docs/remediation/B4-duration-overflow-panic.md`. A
> reader grepping for `C12` finds the wrong one first. This document's register
> row is **`C10`**, at `:855`.

---

## What is wrong

`C3` (`docs/remediation/C3-x-overflow-to-null.md`) closed the TOP of the number
line: `x-threshold: 1e999` parses to infinity, could not be written down, and
left the loader as `null`. Its own prose recorded what it did not close, and the
register kept the row.

This is the same harm at the BOTTOM of the same line, and it reads worse for one
reason: **nothing is null this time.** `1e-999` parses without complaint and
hands back `0.0` — a perfectly ordinary number, sitting where a figure was
written, with no sign at all that anything was lost. The overflow case at least
produced a `null` that a careful reader might notice. This produces a value every
layer downstream accepts without question.

### Reproduction

The fix is in the tree, so the defect has to be temporarily removed to be seen.
The edit that removes it is **mutation A**: delete the line
`&& !underflowed_to_zero(f, text)` from the float arm of `resolve_scalar`,
`crates/pact-doc/src/yaml.rs:871`.

I performed this mutation. `crates/pact-doc/src/yaml.rs` was copied byte-for-byte
first; the copy was restored afterwards and the restore confirmed both by `diff`
(empty) and by `sha1sum`, reading `0d764e78dd6f31a85fad25b10070072fc555e0d0`
before the break and again after the restore.

The fixture is a two-file workspace: `workspace.yaml` says `name: desk-shop`, and
`agents/desk/agent.yaml` says `name: Desk`, `description: A desk.`,
`instructions: Do it.` and then the line under test.

**With the fix removed**, `x-tiny: 1e-999`:

```
$ pact show <root>
      "x-tiny": 0.0

$ pact check <root> --deny-warnings
OK — <root> loaded cleanly (8 settings).
$ echo $?
0
```

The author typed a figure. It reached every consumer as **zero**, and the checker
said the document was clean.

### The half that mattered more

`pact discover` publishes a `sha256:` digest of the workspace — the string a
lockfile pins so a runtime can tell one version of a document from another.
Measured on the broken build, two workspaces identical but for that one line:

```
x-tiny: 1e-999   ->  sha256:9cfbaa692b8bb27823207721d2b0d3fcd04d287e9efe750b457fc1e28851c70e
x-tiny: 0        ->  sha256:9cfbaa692b8bb27823207721d2b0d3fcd04d287e9efe750b457fc1e28851c70e
```

**One hash for two documents an author would call two documents.** A lockfile
pins one and cannot tell it from the other. That is the sentence `AC-1.3`
(`docs/00-THESIS.md:410-411`, *"an unknown `x-` field round-trips untouched"*)
exists to forbid, and the same sentence C3 was written to delete at the other end
of the scale.

With the fix in place, measured by me on the restored build:

```
x-tiny: 1e-999   ->  sha256:d310fd6ab3b5964aacbe0f8960b4939a8d653fa93fe043606223a3e4facb8e4e
x-tiny: 0        ->  sha256:b6e6a8459355a51e0fb7414848e99d6a982ed8958c243c2cbb7f303c2c80682d
$ pact show <root>
      "x-tiny": "1e-999"
```

Two documents, two hashes.

### The typed half

Keeping the text is the whole answer for `x-`, which PACT does not read. Where
the specification says a figure is wanted it is half an answer: the document layer
hands the text on and `coerce::number` parses `0.0` straight back out of it.
Measured on the broken build:

```
$ pact check <ws with settings.temperature: 1e-999>
OK — <root> loaded cleanly (10 settings).
```

A setting the author never wrote, checked silently, exit 0 — the silent
degradation `T7` and `FR-8.1.1` forbid.

---

## Root cause

`crates/pact-doc/src/yaml.rs`, `resolve_scalar` (`:725`). A scalar is read as a
number when it parses as one. `"1e-999".parse::<f64>()` **succeeds** and returns
`0.0`, so every guard that asks whether the parse worked, or whether the result is
finite, answers yes. The figure is gone and nothing in the type system says so.

### The class, not the line

The corruption is invisible to the VALUE and visible only in the TEXT. That is
what makes this one family with its two siblings rather than three separate bugs:

| spelling | parses to | what no guard on the value can see |
|---|---|---|
| `1e999` | `inf` | caught by `is_finite` — the value itself is wrong |
| `99999999999999999999` | `1e20` | finite, ordinary, and not the figure written |
| `1e-999` | `0.0` | finite, ordinary, and not the figure written |

The bottom two rows can only be caught by reading what the author wrote. The
existing `coerce::whole_number_past_holding` (`crates/pact-schema/src/coerce.rs`)
already reads the text for exactly this reason, so the fix is the house pattern
applied at the bottom of the scale rather than a new idea.

The general class is: **a lossy conversion whose output is a member of the
output type's ordinary range.** Overflow escapes into `inf`/`null`, which is
conspicuous. Underflow lands on `0.0`, which is not. Any layer that validates the
result rather than the transformation is blind to the second kind by
construction — which is exactly why nothing caught it.

### The rule, and the two wider ones that do not work

Both wider rules were measured rather than reasoned about, and each is a landed
mutation (C and D) that turns this file red:

* *"only accept a float that round-trips its own text"* refuses **`1e10`**, which
  comes back as `10000000000.0` — the same number, reformatted. Nobody would call
  that corrupted.
* *"any text that parses to zero is suspect"* refuses `0`, `0.0`, `-0.0` and
  `0e10` — zeros an author meant, which lose nothing by being read as zero.

What survives is narrow: **a scalar that comes back as zero while its SIGNIFICAND
carries a figure other than zero is not zero.** The exponent is deliberately not
looked at, because the `10` of `0e10` scales a nothing and says nothing about what
was meant, while the `1` of `1e-999` is the whole of what the author wrote.

---

## Why nothing caught it

Five checks could each have caught this. Each was blind, and each blindness was
measured rather than assumed.

| check | why it was blind |
|---|---|
| `resolve_scalar`'s own guards | `parse::<f64>()` returned `Ok`, and `is_finite()` is true of `0.0`. Both guards ask about the VALUE; the loss is only in the text. |
| `coerce::number` | it re-parses the text and gets the same `0.0`. A second reader of a lossy conversion reproduces the loss; it does not detect it. |
| `pact check` / `--deny-warnings` | there was nothing to report — every layer agreed the value was a valid number. Measured: exit 0 on the broken build. |
| the digest | `sha256` over a canonical form faithfully hashes whatever it is given. It cannot notice that what it was given is not what was written; it made the loss permanent and invisible instead. |
| `cargo test -p pact-doc` | **still blind today**, and this is the standing risk. Measured by me under mutation A: `test result: ok. 52 passed; 0 failed`. The crate that owns the guard is entirely green with the guard deleted. |

The sibling overflow fix left three unit tests inside `yaml.rs`'s own `mod tests`
(`a_number_too_big_to_hold_stays_text`,
`a_number_too_big_to_hold_no_longer_digests_as_nothing`,
`a_whole_number_past_holding_keeps_its_digits`). The underflow half has **none**.
That asymmetry is real, is now written into the module prose, and is why the CLI
test file is the single door — see [The test](#the-test).

There is a sixth answer, and it is the honest one: C3 **knew**. Its own prose
recorded that it closed the top of the number line and not the bottom, and the
register kept the row open. This was not missed; it was deferred and then not
picked up until this pass.

---

## The fix

Five source edits in three files. Line numbers are as the tree now stands
(`crates/pact-doc/src/yaml.rs` sha1 `0d764e78dd6f31a85fad25b10070072fc555e0d0`,
`crates/pact-schema/src/lib.rs` sha1 `d42d1cdd4539473184ed72c97f391f0840e17241`,
`crates/pact-schema/src/coerce.rs` sha1
`56470fee0743f75ef26cc136dfd0aa19a5a1f70e`).

### 1. The document layer — `crates/pact-doc/src/yaml.rs:869-875`

A third conjunct on the float arm of `resolve_scalar`. This is what fixes
`pact show`, the digest, and `x-`.

```rust
if let Ok(f) = text.parse::<f64>()
    && f.is_finite()
    && !underflowed_to_zero(f, text)
    && text.chars().any(|c| c.is_ascii_digit())
{
    return Value::Float(f);
}

Value::Str(text.to_string())
```

The helper is at `:907-913`:

```rust
fn underflowed_to_zero(f: f64, text: &str) -> bool {
    if f != 0.0 {
        return false;
    }
    let significand = text.split(['e', 'E']).next().unwrap_or(text);
    significand.chars().any(|c| c.is_ascii_digit() && c != '0')
}
```

**Ordering against the existing passes matters and is right.** The leading-zero
rule already owns every plain scalar starting `0` that is not `0.`, so `0e10`
never reaches this arm — which is why the zeros test asserts `0.0e10` and says so
in a comment. The `i64` arm and the digits-only arm run first, so nothing spelled
as a whole number reaches the float arm at all.

### 2. `check_ceiling` — `crates/pact-schema/src/lib.rs:1787`, five arms

Mirror arms for `Number` (`:1913`), `Threshold` (`:1919`), `Percent` (`:1941`),
`SizeTooSmall` (`:1969`) and `IntegerTooSmall` (`:1873`), all emitting
`schema/too-small-to-count`, one sentence for both signs. The per-node helper is
at `:2873`; it differs from the document-layer one only in reading
`node.as_str()` and `.trim()`ing first, because a schema node may carry trailing
space.

**The rule id is deliberately not `schema/wrong-type`** — `1e-999` is spelled the
way a number is spelled, and *"it is some text"* sends its author hunting a typo
that is not there. It is deliberately not `schema/below-the-floor` either: the
floor and the underflow are different questions with different edits, and
`a_number_field_given_a_zero_is_not_told_it_is_too_small` holds that line.

Measured diagnostic, verbatim, by me:

```
error: 'steps-at-most' is 1e-999, which is closer to zero than this can keep track of.
  --> …/agents/desk/agent.yaml:6:18
  fix: Write `steps-at-most: 10`, or any number further from zero, or remove the line.
  rule: schema/too-small-to-count
```

Three house rules are obeyed: the sentence quotes what the author actually wrote,
the fix is typeable, and the placeholder is per type (`10`, `> 80`, `32k`, `90%`).

### 3. `check_floor` — `crates/pact-schema/src/lib.rs:1698-1712`, a `Size(0)` arm

Beside the existing `Duration(0)` arm, for a real figure that truncates to no
tokens: *"which is no tokens at all"*, `schema/below-the-floor`. See
[§2](#2--the-size-arm-reported-underflow-for-figures-that-did-not-underflow).

### 4. `crates/pact-schema/src/coerce.rs` — two mirror variants

`Coerced::SizeTooSmall` (`:62`, produced at `:610`) and
`Coerced::IntegerTooSmall(f64)` (`:101`, produced at `:307`), the mirrors of the
existing `SizeTooBig`/`IntegerTooBig`. Both are decided **at the figure before any
multiplier** — the last point at which `1e-999m` and `0.0004k` are still
distinguishable.

### 5. `kind_as_written` — `crates/pact-schema/src/lib.rs:2708`

`wrong_type` (`:2724`) reads its noun off the written text, so a figure is never
called text however it had to be carried. See
[§3](#3--the-fix-made-valuekind_name-lie-about-the-authors-own-tree).

**One sentence covers both signs**, which the top end needed two for. `-1e999` is
genuinely at the far end of the scale and had to be told so; `-1e-999` is `-0.0`,
and *"closer to zero than this can keep track of"* is true of it and of `1e-999`
alike — the edit both authors need is the same one.

---

## The four defects found by attacking the landed fix

The first pass landed the document-layer guard and three ceiling arms. Attacking
that landed fix found four more things, three of them **damage the fix itself
did** by changing what the typed fields are handed. They are recorded here
because the blast radius below is what should have predicted them and did not.

### §1 — `percent` was the one type the arm was not written for

`must-pass: 1e-999%` is `> 1e-999` written the way an eval suite writes a bar.
`coerce::percent` divides by a hundred, finds `0.0` inside `0.0..=1.0`, and hands
back `Percent(0.0)` — a bar every suite on earth clears, out of a line that was
setting one. It loaded clean both before the change and after it.
`when-full: 1e-999%` is the same silence one field over.

Fixed by the matching arm. Measured by me now, against a workspace whose
`evals/suite.yaml` carries the bar:

```
must-pass: 1e-999%     error: 'must-pass' is 1e-999%, which is closer to zero than this can keep track of.   schema/too-small-to-count
must-pass: -1e-999%    error: 'must-pass' is -1e-999%, which is closer to zero than this can keep track of.  schema/too-small-to-count
must-pass: 1e-999      error: 'must-pass' is 1e-999, which is closer to zero than this can keep track of.    schema/too-small-to-count
must-pass: 0.0000001%  OK — loaded cleanly (11 settings)     # 1e-9, held exactly, never underflowed
must-pass: 0%, 0.0, 0.00%, 0.0e10%, 70%, 0.7    OK — loaded cleanly (11 settings)
```

`0.0000001%` is the guard that stops this arm becoming *"any small percentage is
suspect"*.

### §2 — the size arm reported underflow for figures that did not underflow

The landed arm was `Coerced::Size(0) if underflowed_to_zero(0.0, node)` — a
**hard-coded `0.0`**, which never asks whether anything underflowed and only asks
whether the text carries a figure. `coerce::size` multiplies by the `k` or `m` and
CASTS to a whole number, so two different losses arrive at the same `Size(0)`.
Measured against the landed build:

```
context-at-least: "0.5"       error: … is 0.5, which is closer to zero than this can keep track of.
context-at-least: "0.9"       error: … is 0.9, which is closer to zero than this can keep track of.
context-at-least: 0.0004k     error: … is 0.0004k, which is closer to zero than this can keep track of.
  fix: Write `context-at-least: 32k`, or any number further from zero, …
```

`0.5`, `0.9` and `0.4` are held by an `f64` to the last bit. **Nothing
underflowed.** The sentence is false, and the fix offered — *"any number further
from zero"* — is one `0.0004k` already satisfies.

There are three zeros here, not one, and the repair separates them at the last
point where they are still distinguishable: the figure BEFORE the multiplier.

| written | figure | what happened | answer now |
|---|---|---|---|
| `0`, `0k` | 0 | nothing; a zero somebody meant | loads |
| `0.0004k`, `0.0000001k`, `"0.5"` | 0.4, 0.0001, 0.5 | held exactly, TRUNCATED by `as u64` | `schema/below-the-floor` |
| `1e-999`, `1e-999m` | — | never held at all | `schema/too-small-to-count` |

The middle row's sentence was already in the tree one type over —
`finishes-within: 0.4ms` is *"which is no time at all"*, `schema/below-the-floor`
— so the size floor says *"which is no tokens at all"* in the same shape.
Measured by me now:

```
context-at-least: 1e-999      error: 'context-at-least' is 1e-999, which is closer to zero than this can keep track of.   schema/too-small-to-count
context-at-least: 1e-999m     error: 'context-at-least' is 1e-999m, which is closer to zero than this can keep track of.  schema/too-small-to-count
context-at-least: 0.0004k     error: 'context-at-least' is 0.0004k, which is no tokens at all.    schema/below-the-floor
context-at-least: "0.5"       error: 'context-at-least' is 0.5, which is no tokens at all.        schema/below-the-floor
context-at-least: 0.0000001k  error: 'context-at-least' is 0.0000001k, which is no tokens at all. schema/below-the-floor
context-at-least: 0, 0k, 32k, 200000, 0.5k        OK — loaded cleanly (10 settings)
```

### §3 — the fix made `Value::kind_name` lie about the author's own tree

**This is the defect the fix itself caused**, and the one that took longest to see
because it fails in the SENTENCE rather than in the rule.

`Schema::wrong_type` builds its noun from `node.value.kind_name()`. The moment an
underflowing scalar started being carried as `Value::Str` — which is exactly what
stops `pact show` and the digest losing it — every typed field falling through to
`wrong-type` began calling a run of digits *"some text"*. Measured on the landed
build:

```
limits.steps-at-most: 1e-999    error: 'steps-at-most' should be a whole number, but it is some text.   schema/wrong-type
limits.steps-at-most: abc       error: 'steps-at-most' should be a whole number, but it is some text.   schema/wrong-type
```

**Byte-identical.** And measured under mutation A, i.e. the sentence that existed
BEFORE this fix:

```
limits.steps-at-most: 1e-999    error: 'steps-at-most' should be a whole number, but it is a number.
```

So the fix turned a true noun into a false one. Three comments written as part of
this very change set forbid exactly that:

* `crates/pact-doc/src/yaml.rs` — *"a line spelled the way a number is spelled,
  told what is wrong with it, rather than told it is not a number and sent hunting
  for a typo that is not there"*;
* `crates/pact-schema/src/coerce.rs` — *"**BUT A FIGURE THAT OVERFLOWED IS NOT A
  WORD** … the author was told their line should be a size … but it is some text —
  about a line that is a figure"*;
* `crates/pact-doc/src/value.rs:261` — *"D13: a non-coder reads these. No type
  jargon may leak into diagnostics."*

Two repairs, because the noun and the rule are different questions.

**The noun.** `kind_as_written` reads it off the TEXT and answers exactly what the
value kinds would have answered had the tree been able to hold the figure: a run
of digits is *"a whole number"*, anything else parsing as a figure is *"a
number"*, and anything carrying no digit is *"some text"*. Measured by me now:

```
finishes-within: 1e-999                          … but it is a number.
finishes-within: 0.5                             … but it is a number.
finishes-within: 90                              … but it is a whole number.
finishes-within: abc / .inf                      … but it is some text.
cost-per-request-under: "1e-999"                 … but it is a number.
cost-per-request-under: "99999999999999999999"   … but it is a whole number.
```

**The rule, for `integer` only.** `steps-at-most: 1e999` is refused BY NAME
(`schema/too-big-to-count`, measured). Its bottom end being `wrong-type` while its
top end is named is the asymmetry `coerce.rs` argues against for every other type,
so `integer` gets `Coerced::IntegerTooSmall` beside `IntegerTooBig`. Measured by
me now:

```
steps-at-most: 1e-999                 error: 'steps-at-most' is 1e-999, which is closer to zero than this can keep track of.   schema/too-small-to-count
steps-at-most: -1e-999                error: 'steps-at-most' is -1e-999, which is closer to zero than this can keep track of.  schema/too-small-to-count
steps-at-most: 0.5                    error: 'steps-at-most' should be a whole number, but it is a number.    schema/wrong-type
steps-at-most: abc                    error: 'steps-at-most' should be a whole number, but it is some text.   schema/wrong-type
steps-at-most: 1e999                  error: 'steps-at-most' is 1e999, which is more than this can keep track of.   schema/too-big-to-count
steps-at-most: 99999999999999999999   error: 'steps-at-most' is 99999999999999999999, which is more than this can keep track of.
```

**`duration` and `money` keep `wrong-type`, and that is not a residual.**
`finishes-within: 1e-999` carries no unit and `cost-per-request-under: "1e-999"`
carries no currency, so *"should be a length of time, like `2s`"* and *"should be
an amount of money, like `0.05 USD`"* are the TRUE sentences about them — the same
answer `0.5` gets, which is the same mistake. Only the noun was ever wrong, and the
noun is fixed. (`cost-per-request-under: 1e-999 USD`, which DOES carry a currency,
is `schema/below-the-floor`, *"which is no money at all"* — measured by me.)

### §4 — the mutation record was stale, and one row of it was simply wrong

The docstring's mutation record is this fix's only evidence that its tests bite.
Re-performing all six landed mutations showed mutation **A** recorded as
`6 passed; 5 failed` when the truth was **6 failed** with a sixth test unnamed,
and four of the six rows quoting totals for a 10- or 11-test file that no longer
existed.

Every mutation was re-performed and the record rewritten from what the tree
printed — see [The mutation](#the-mutation). The FORM was changed too, because an
absolute pass count rots the moment any later pass adds a test to the file: the
record now **names which tests turn red**, and states the invariant
`passed + failed == 15` so a reader catches the next drift at a glance. The
general version of this is queue row **G5**, scoped to every remediation test file
rather than this one; that row records C12's file as the copyable form.

---

## Alternatives rejected

**Prior art, checked first.** The same shape has been solved four times before and
this fix copies it: `Coerced::DurationTooLong`, `SizeTooBig`, `IntegerTooBig` and
the `!n.is_finite()` `Number` arm all take the identical route — the coercer
refuses to invent a value, and `check_ceiling` says the true sentence one layer up
where the field's name and line are known.

| alternative | why rejected |
|---|---|
| *"only accept a float that round-trips its own text"* | Refuses `1e10` → `10000000000.0`, a number nobody would call corrupted. **Measured as mutation D**: turns `a_number_nobody_would_call_corrupted_is_left_alone` and `a_zero_somebody_meant_is_still_a_zero` red. |
| *"any text that parses to zero is suspect"* | Refuses `0`, `0.0`, `-0.0`, `0e10` — zeros an author meant. **Measured as mutation C**: turns `a_zero_somebody_meant_is_still_a_zero` red. |
| Refuse `1e-999` outright at the document layer, as a parse error | An `x-` field is the author's private namespace and PACT promises AC-1.3 round-tripping. `a_number_too_small_to_hold_is_not_a_problem_of_its_own` pins this: it passes under `--deny-warnings`. |
| Keep the value as `Value::Float` but carry the text alongside | Would have avoided the `coerce::size` and `kind_name` regressions entirely — but changes a public type in `pact-doc` for every caller. The regressions turned out closable within `check_ceiling`/`check_floor`/`coerce`. **This is the alternative with the strongest case**; see the honesty note below. |
| Refuse the underflow inside `coerce::percent` by returning `None` | `None` becomes `schema/wrong-type`, *"should be a percentage … but it is some text"* — false about a line spelled exactly the way a percentage is spelled. Three tests assert `!text.contains("schema/wrong-type")` precisely to stop that. |
| Add a `Coerced::PercentTooSmall` variant | The `TooBig`/`TooSmall` variants exist because the coercer has NO value to hand up. For percent it has one (`0.0`); the question is only whether it is the value written. Matching the ordinary variant with a text-reading guard is what the three sibling arms do. |
| Widen the `Number` arm to cover `Percent` | Impossible — distinct `Coerced` variants, and merging discards the per-type placeholder. A fix line reading ``Write `must-pass: 10` `` is a fix that fails if typed. |
| Leave the percent hole and only document it | Rejected. `must-pass: 1e-999%` loading clean is `> 1e-999` in different clothes, and `> 1e-999` is already refused by an existing test eleven lines away. Shipping for `threshold` and not for the spelling an eval suite actually uses would leave the register claiming a closure it did not have. |
| `f == 0.0 \|\| f.is_subnormal()`, to close the subnormal digest collapse | **Measured and rejected** — see [What remains open §1](#1-distinct-literals-still-collapse-onto-one-f64-and-the-claim-has-been-narrowed-to-match). `1e-310` is subnormal and loses nothing. |

**Worse in the landed approach than in a hypothetical alternative, stated
honestly.** The correctness of this family now rests on a hand-maintained list of
`Coerced` variants inside one `match`. Nothing structural says *"every numeric
variant must answer the underflow question"* — which is exactly why `Percent` was
missed for a round, why `Size` got a hard-coded zero, and why `money` and
`duration` are safe only because their floors already own the bottom of their
scales. A `match` with no wildcard over a `Ty`-indexed table would make the next
omission a compile error. That is a real design improvement and it was **not**
attempted here: it touches every arm of `check_ceiling`, well outside what this
issue may safely change, and it belongs in its own row.

---

## Blast radius

Keeping an underflowing scalar as text does not only stop `pact show` losing it —
it changes the `Value` kind every TYPED field is handed. **That is the part the
first pass got wrong**, and where three of the four defects above came from.

### Upstream: who calls the changed code

Measured with `grep -rn "resolve_scalar(\|check_ceiling(\|check_floor(\|kind_as_written(" crates/ --include=*.rs`:

| function | call sites |
|---|---|
| `resolve_scalar` | exactly **one**, `crates/pact-doc/src/yaml.rs:600`, in the scalar event handler |
| `check_ceiling` | exactly **one**, `crates/pact-schema/src/lib.rs:1553` |
| `check_floor` | exactly **one**, `crates/pact-schema/src/lib.rs:1552` |
| `kind_as_written` | exactly **one**, `crates/pact-schema/src/lib.rs:2728`, inside `wrong_type` |

So every PACT document in the process passes through the changed line, and nothing
bypasses it. No new helper gained a second caller.

### Downstream: what the changed value reaches

| consumer | before | after keeping the text | outcome |
|---|---|---|---|
| `x-` fields | `Float(0.0)` | `Str` | **fixed**: round-trips, digests apart |
| `type: number`, `threshold` | `Float(0.0)`, silent | `Str` → `check_ceiling` | **fixed**: `schema/too-small-to-count` |
| `type: percent` | silent | `Str` → `check_ceiling` | **missed in the first round**, §1 |
| `type: size` | refused at `_ => None` | `Str` — a spelling `size` ACCEPTS | **got worse**, §2 |
| `type: integer` | `wrong-type`, *"a number"* | `Str`, *"some text"* | **got worse**, §3 |
| `type: duration`, `money` | `wrong-type`, *"a number"* | `Str`, *"some text"* | **got worse**, §3 (noun only) |
| `canonical.rs` `Value::Float` arm | the digest | now takes the `Str` arm | **the point of the fix** |
| `pact-loader/src/money.rs` gate-figure reader | `Float(n) => n.to_string()` | takes the `Str` arm one line above, `trim()`ed to the identical string | **unaffected in output** |

### Digest stability — measured, and nothing authored moves

No authored document in the repository contains an underflowing scalar. Measured
with `grep -rnE ':\s*[-+]?[0-9]*\.?[0-9]+[eE]-[0-9]{3,}'` over `examples/`,
`spec/`, `adapters/` and `crates/*/tests`: the only hits are this issue's own test
file and `node_modules`.

`check_ceiling` and `check_floor` emit diagnostics and never rewrite a value, so
they cannot move a digest by construction. The digest DOES move — correctly, and
that is the point — for any workspace that actually writes an underflowing `x-`
scalar.

### The five honesty channels on `RunResult` — not affected

`unmetered`, `unenforced`, `unwatched`, `never_reached`, `unretrieved`
(`adapters/python/src/pact_adapters/harness.py:136-190`). Measured: `pact show` on
a workspace with `needs.context-at-least: 1e-999` prints
`rule: schema/too-small-to-count` and emits **no document**. So no new value shape
can reach the run path, and no field can newly land on `unenforced`/`never_reached`
because it arrived as a zero. The only shape that changes in a VALID document is an
`x-` scalar (`0.0` → `"1e-999"`), and no adapter reads `x-` — the run path never
opens the author's tree at all (invariant P-1, held by
`adapters/python/tests/test_no_adapter_reads_the_authors_files.py`).

### Both ports — the change is correctly Rust-only

The TypeScript port is behaviour-only. `adapters/typescript/src/` is six files
(`harness.ts`, `limits.ts`, `loops.ts`, `run-trace.ts`, `vercel-transport.ts`,
`yes-no.ts`) and **none parses YAML or a canonical document** — measured, the only
matches for `yaml` in that tree are in prose comments. The port takes an
already-IR-shaped `AgentSpec` payload whose keys are `AGENT_SPEC_FIELDS`
(`harness.ts:170`) and refuses anything undeclared. `x-` never reaches it.
`limits.ts`'s `Number.parseFloat` reads money and duration STRINGS off a document
the Rust checker has already refused if it underflows. The same holds for the
Python port. **Neither port has a document-validation layer for this change to be
duplicated into.**

### The four-artifact rule — not engaged

It fires when what the second port reports changes. This adds no field, removes no
field, and changes no key on the wire. `schema/too-small-to-count` is a checker
rule id existing only in Rust — measured, `grep -rl` over `.md`/`.yaml`/`.py`/`.ts`
returns four prose documents (`docs/70-PRODUCTION-GAP-REGISTER.md` and three
`docs/remediation/*.md`) and **zero code outside `crates/`**. `AGENT_SPEC_FIELDS`
is untouched; `the_subset_the_second_port_runs.rs` and its Python twin are
untouched and pass.

### Counts

`scripts/sync-counts.sh` IS engaged, because Rust tests were added.
`README.md:73` now reads **2910 tests (949 Rust + 1961 adapter)** and `:79` the
same figure; `test_the_headline_test_count_is_the_count.py` reads README and holds
it. The two hardcoded figures in `scripts/test-all.sh` (`62 test files read the
worked example`, `68 adapter tests drive the second port`) are counts of PYTHON
test files, live only inside error strings, and are enforced by nothing — measured,
`grep -rn` hits only that script. This issue adds no Python test, so neither moves.
They were not touched; that nothing holds them is noted, and is queue row **E7**.

---

## The test

**File:** `crates/pact-cli/tests/a_number_too_small_to_hold_is_kept_as_it_was_written.rs`
— **15 tests**. Measured: `grep -c "#\[test\]"` returns 15, and
`cargo test -p pact-cli --test a_number_too_small_to_hold_is_kept_as_it_was_written`
returns `test result: ok. 15 passed; 0 failed; 0 ignored`.

**THE DOOR: the real shipped binary.** Every assertion goes through
`Command::new(env!("CARGO_BIN_EXE_pact"))` running `pact show`, `pact check`,
`pact check --deny-warnings` and `pact discover` against a workspace written to a
real temp tree. **No seam, no in-process call into `pact_doc` or `pact_schema`.**
Helpers: `workspace()` (`:233`), `shown()` (`:250`), `suite()` (`:268`, writes
`evals/suite.yaml` — the only place a `type: percent` field is authorable),
`checked()` (`:282`), `digest()` (`:294`).

| test | claim |
|---|---|
| `a_number_too_small_to_hold_survives_show` (`:311`) | `x-tiny: 1e-999`, `-1e-999`, `1e-400` come back out of `pact show` as their own text; no `: 0.0` anywhere |
| `two_documents_that_differ_do_not_digest_the_same` (`:335`) | `x-tiny: 1e-999` and `x-tiny: 0` get different `sha256:` |
| `a_number_too_small_to_hold_is_not_a_problem_of_its_own` (`:352`) | an `x-` field PACT does not read loads under `--deny-warnings` |
| `a_zero_somebody_meant_is_still_a_zero` (`:369`) | `0`, `0.0`, `-0.0`, `0.0e10`, `0.000` stay numbers |
| `a_number_nobody_would_call_corrupted_is_left_alone` (`:405`) | `1e10`→`10000000000.0`, `1e-300` held exactly, `0.1`, `1.50` |
| `a_number_field_given_one_is_refused_by_name` (`:435`) | `settings.temperature: 1e-999` → `too-small-to-count`, NOT `wrong-type`, with file:line and a typeable fix |
| `a_count_of_tokens_that_underflowed_is_refused_rather_than_read_as_none` (`:472`) | `context-at-least: 1e-999`, `1e-999m` refused; `0`, `0k`, `32k`, `200000` still load |
| `a_size_that_rounds_to_no_tokens_is_not_told_its_figure_vanished` (`:525`) | `0.0000001k`, `0.0004k`, `0.0009k`, `"0.5"`, `"0.9"` → `below-the-floor`, *"no tokens at all"*, and explicitly **not** *"closer to zero"* |
| `a_whole_number_field_given_one_is_refused_by_name_too` (`:571`) | `steps-at-most: 1e-999` → `too-small-to-count`; top end named too |
| `a_figure_on_the_page_is_never_called_some_text` (`:633`) | duration/money underflow says *"a number"*, a digit run past `i64` says *"a whole number"*, and `abc`/`.inf`/`.nan`/`quite a while` still say *"some text"* |
| `the_same_sentence_covers_the_other_sign` (`:714`) | `-1e-999` gets the same sentence, not a mirrored one |
| `a_number_field_given_a_zero_is_not_told_it_is_too_small` (`:731`) | `temperature: 0` / `0.0` load and are never told they are too small — the floor/underflow boundary |
| `a_bar_no_score_could_ever_miss_is_refused_too` (`:754`) | `scores: MMLU: "> 1e-999"` refused. Quoted, so the document layer never sees a float — **this case is the schema arm's alone** |
| `a_share_of_the_whole_that_underflowed_is_refused_too` (`:777`) | `must-pass: 1e-999%` / `-1e-999%` / `1e-999` refused; `0%`, `0.0`, `0`, `0.00%`, `0.0e10%`, `0.0000001%`, `70%`, `0.7` still load |
| `the_words_for_nothing_are_still_plain_text` (`:822`) | `.nan`, `.inf`, `-.inf` stay plain text |

A second, narrower door exists for the coercion answers only:
`coerce::tests` in `crates/pact-schema/src/coerce.rs` (`:909`, `:948`, `:957`)
asks the coercer directly about `SizeTooSmall` and `IntegerTooSmall`.

**Measured coverage gap, and it is the headline of this analysis: for the
`check_*` arms no second door exists.** Under mutation A, `cargo test -p pact-doc`
reports `52 passed; 0 failed` — I ran this. Under the schema-arm mutations,
`cargo test -p pact-schema` reports 113 passed. A `Schema::check_*` arm is only
reachable through a loaded document, so the CLI file is the only thing holding
them.

---

## The mutation

**Eleven mutations. All were performed, not reasoned about** — each applied on its
own, rebuilt, this file run, and reverted from a byte copy before the next, with a
full green run in between to prove the revert took. Every row's
`passed + failed` is 15.

| # | mutation | result | tests that turn red |
|---|---|---|---|
| **A** | drop `&& !underflowed_to_zero(f, text)` from `resolve_scalar` | `8 passed; 7 failed` | `a_number_too_small_to_hold_survives_show`, `two_documents_that_differ_do_not_digest_the_same`, `a_number_field_given_one_is_refused_by_name`, `the_same_sentence_covers_the_other_sign`, `a_whole_number_field_given_one_is_refused_by_name_too`, `a_count_of_tokens_that_underflowed_…`, `a_share_of_the_whole_that_underflowed_…` |
| **B** | drop the `Number` + `Threshold` ceiling arms | `12 passed; 3 failed` | `a_number_field_given_one_is_refused_by_name`, `the_same_sentence_covers_the_other_sign`, `a_bar_no_score_could_ever_miss_is_refused_too` |
| **C** | widen `underflowed_to_zero` to the whole text | `14 passed; 1 failed` | `a_zero_somebody_meant_is_still_a_zero` |
| **D** | widen it to `f.to_string() != text` | `13 passed; 2 failed` | `a_number_nobody_would_call_corrupted_is_left_alone`, `a_zero_somebody_meant_is_still_a_zero` |
| **E** | drop the `SizeTooSmall` ceiling arm | `14 passed; 1 failed` | `a_count_of_tokens_that_underflowed_…` |
| **F** | drop the `Percent` ceiling arm | `14 passed; 1 failed` | `a_share_of_the_whole_that_underflowed_…` |
| **G** | drop the `IntegerTooSmall` ceiling arm | `14 passed; 1 failed` | `a_whole_number_field_given_one_is_refused_by_name_too` |
| **H** | put `wrong_type` back on `Value::kind_name` | `14 passed; 1 failed` | `a_figure_on_the_page_is_never_called_some_text` |
| **I** | drop the `Size(0)` floor arm | `14 passed; 1 failed` | `a_size_that_rounds_to_no_tokens_is_not_told_its_figure_vanished` |
| **J** | drop the underflow branch from `coerce::size` | `14 passed; 1 failed` | `a_count_of_tokens_that_underflowed_…` |
| **K** | drop the underflow branch from `coerce::integer` | `14 passed; 1 failed` | `a_whole_number_field_given_one_is_refused_by_name_too` |

**Mutation A was independently re-performed for this document** and reproduced
exactly: `test result: FAILED. 8 passed; 7 failed`, with the seven named tests and
no others. The restore was verified byte-identical (`diff` empty, `sha1sum` back to
`0d764e78dd6f31a85fad25b10070072fc555e0d0`) and the file re-run green at
`15 passed; 0 failed`. The failure message it produced, which is the defect made
visible:

```
wrong rule for `1e-999`:
error: 'context-at-least' should be a size, like `32k` or `200000`, but it is a number.
  rule: schema/wrong-type
```

**A is the seam between the two halves of the fix.** It turns
`a_share_of_the_whole_that_underflowed_is_refused_too` red for exactly ONE of that
test's three cases — `must-pass: 1e-999` with no `%`, the only unquoted spelling
it writes and therefore the only one that goes through the document layer.
`a_bar_no_score_could_ever_miss_is_refused_too` stays GREEN under A, because a
comparison is written quoted and the document layer never touches it. **So neither
half is a second copy of the other.**

**E and J** are the two halves of one claim (the ceiling arm, and the coercion
answer that reaches it) and neither covers the other; **G and K** are the same pair
for `integer`.

**Which suites are blind to which mutation**, measured because it reads like
coverage that is not there:

* `cargo test -p pact-doc` is **blind to A** — 52 passed with the guard deleted.
  *(Re-confirmed by me for this document.)*
* `cargo test -p pact-schema` is **blind to B, E, G and I** — all 113 tests green
  with those arms deleted, because a `check_*` arm is only reachable through a
  loaded document.
* `cargo test -p pact-schema` is **not** blind to J or K: `coerce::tests` asks the
  coercer directly and both turn it red.

---

## Failure cases

Enumerated. Each is marked with the test that holds it, or **UNCOVERED**.

### The document layer

| case | expected | status |
|---|---|---|
| `x-tiny: 1e-999` survives `pact show` as `"1e-999"` | text kept | covered-by `a_number_too_small_to_hold_survives_show` |
| `x-tiny: -1e-999` (arrives `-0.0`, sign preserved) | text kept | covered-by same |
| `x-also: 1e-400` (one order up, still underflows) | text kept | covered-by same |
| `x-tiny: 1e-999` vs `x-tiny: 0` must not share a digest | two hashes | covered-by `two_documents_that_differ_do_not_digest_the_same` |
| an `x-` field PACT does not read loads under `--deny-warnings` | exit 0 | covered-by `a_number_too_small_to_hold_is_not_a_problem_of_its_own` |
| zeros somebody MEANT: `0`, `0.0`, `-0.0`, `0.0e10`, `0.000` | stay numbers | covered-by `a_zero_somebody_meant_is_still_a_zero` |
| `1e10`→`10000000000.0`, `1e-300` exact, `0.1`, `1.50`→`1.5` | left alone | covered-by `a_number_nobody_would_call_corrupted_is_left_alone` |
| `.nan`, `.inf`, `-.inf` | stay plain text | covered-by `the_words_for_nothing_are_still_plain_text` |

`0.0e10` and not `0e10` is deliberate: the leading-zero rule already owns `0e10`,
and the test says so in a comment.

### The schema layer

| case | expected | status |
|---|---|---|
| `settings.temperature: 1e-999` | `too-small-to-count`, never `wrong-type`, file:line, typeable fix | covered-by `a_number_field_given_one_is_refused_by_name` |
| `settings.temperature: -1e-999` | the SAME sentence, not mirrored | covered-by `the_same_sentence_covers_the_other_sign` |
| `settings.temperature: 0` and `0.0` | NOT told they are too small | covered-by `a_number_field_given_a_zero_is_not_told_it_is_too_small` |
| `needs.context-at-least: 1e-999`, `1e-999m` | `too-small-to-count` | covered-by `a_count_of_tokens_that_underflowed_…` |
| `context-at-least: 0`, `0k`, `32k`, `200000` | still load | covered-by same |
| `context-at-least: 0.0000001k`, `0.0004k`, `0.0009k`, `"0.5"`, `"0.9"` | `below-the-floor`, *"no tokens at all"* | covered-by `a_size_that_rounds_to_no_tokens_…` |
| `scores: MMLU: "> 1e-999"` | refused | covered-by `a_bar_no_score_could_ever_miss_is_refused_too` |
| `must-pass: 1e-999%`, `-1e-999%`, bare `1e-999` | refused by name | covered-by `a_share_of_the_whole_that_underflowed_…` |
| `must-pass: 0%`, `0.0`, `0`, `0.00%`, `0.0e10%`, `70%`, `0.7` | still load | covered-by same |
| `must-pass: 0.0000001%` (`1e-9`, held exactly) | still loads | covered-by same — the guard against *"any small percentage is suspect"* |
| `steps-at-most: 1e-999`, `-1e-999` | `too-small-to-count` | covered-by `a_whole_number_field_given_one_is_refused_by_name_too` |
| `finishes-within: 1e-999` / money `"1e-999"` | `wrong-type` but noun *"a number"* | covered-by `a_figure_on_the_page_is_never_called_some_text` |
| `cost-per-request-under: "99999999999999999999"` | noun *"a whole number"* | covered-by same |
| `abc`, `.inf`, `.nan`, `quite a while` | still *"some text"* | covered-by same |

### Known-and-correct, held by no test of their own

| case | measured answer | status |
|---|---|---|
| `when-full: 1e-999%` (context policy) | same `Coerced::Percent` path, refused by construction | **UNCOVERED** — exercises no code `must-pass` does not |
| `drift.at-most: 1e-999%` | same arm | **UNCOVERED** |
| `metric.threshold: 1e-999` (`type: percent`, `spec/schema.yaml:2470`) | same arm | **UNCOVERED** |
| `cost-per-request-under: 1e-999 USD` | `below-the-floor`, *"no money at all"* — measured | **UNCOVERED here**; owned by B3. The money floor already owns the bottom of that scale; an underflow arm would double-report |
| `finishes-within: 0.0000001s` | `below-the-floor`, *"no time at all"* | **UNCOVERED here**; owned by B4 |
| `must-pass: 1e999%` (percent OVERFLOW) | `coerce::percent`'s `(0.0..=1.0)` filter rejects `inf` → `wrong-type`. Refused, not silent | **UNCOVERED**, and not a gap |
| `x-tiny: 1e-999` vs `x-tiny: "1e-999"` | **one digest** — measured | **UNCOVERED**, and open; see [open §4](#4-an-unquoted-underflowing-scalar-and-its-quoted-spelling-now-hash-identically) |
| `finishes-within: 1e-999ms` | *"some text"* | **UNCOVERED**, and open; see [open §3](#3-1e-999ms-is-still-some-text) |
| `context-at-least: 0.5` (bare float) | `wrong-type`, *"a number"* — differs from `"0.5"` | **asserted in `coerce::tests`**, open; see [open §2](#2-a-size-written-as-a-bare-float-still-answers-differently-from-a-quoted-one) |
| `x-tiny: 3e-324` / `5e-324` / `7e-324` | **one digest** — measured | **UNCOVERED**, and open; see [open §1](#1-distinct-literals-still-collapse-onto-one-f64-and-the-claim-has-been-narrowed-to-match) |

---

## Verification

Commands, and what they printed on this tree on 2026-08-08.

```
$ cargo test -p pact-cli --test a_number_too_small_to_hold_is_kept_as_it_was_written
test result: ok. 15 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out

$ cargo test --workspace
… 91 `test result:` lines, all `ok`, 0 failed
   (measured: `cargo test --workspace 2>&1 | grep -cE "^test result: ok"` -> 91
                                          `| grep -c FAILED`             -> 0)

$ cargo clippy --all-targets -- -D warnings
(no output)

$ sha1sum crates/pact-doc/src/yaml.rs
0d764e78dd6f31a85fad25b10070072fc555e0d0
$ sha1sum crates/pact-schema/src/lib.rs
d42d1cdd4539473184ed72c97f391f0840e17241
$ sha1sum crates/pact-schema/src/coerce.rs
56470fee0743f75ef26cc136dfd0aa19a5a1f70e
```

The Python suite is unchanged by this issue and was not re-run for this document;
the pass that landed the fix recorded `1954 passed, 7 skipped`. **That figure is
recalled, not measured here**, and is the only figure in this document that is.

To reproduce the defect and confirm the test bites, in one sequence:

```
cp crates/pact-doc/src/yaml.rs /tmp/yaml.rs.bak
# delete the line `        && !underflowed_to_zero(f, text)` at yaml.rs:871
cargo test -p pact-cli --test a_number_too_small_to_hold_is_kept_as_it_was_written
#   -> test result: FAILED. 8 passed; 7 failed
cargo test -p pact-doc
#   -> test result: ok. 52 passed; 0 failed        <- the blindness
cp /tmp/yaml.rs.bak crates/pact-doc/src/yaml.rs
cargo test -p pact-cli --test a_number_too_small_to_hold_is_kept_as_it_was_written
#   -> test result: ok. 15 passed; 0 failed
```

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md:855`, the `~~**C10**~~` row, **has already
been updated** and now records: both ends of the number line and both doors; the
narrow rule and the two guards on it; the `check_ceiling` mirror arm; the percent
half; the size floor/ceiling split; the `kind_as_written` noun repair; *"fifteen
tests, ELEVEN mutations"*; the measured blindness figures (`pact-doc` 52/52,
`pact-schema` 113/113); and what stays open. It closes with
`See docs/remediation/C12-underflow-to-zero.md`.

Two corrections that row needed and received: it had claimed *"ten tests, four
mutations"* and later *"twelve tests, six mutations"* for a file that now holds
fifteen and eleven, and it had quoted `112/112` for `pact-schema` where the
measured figure is `113`.

**Register `C12` at `:857` is a different issue** (the duration overflow panic)
and was not touched.

---

## What remains open

Named rather than fixed, with the measurement that bounds each. Nothing in this
section is claimed to be closed.

### 1. Distinct literals still collapse onto one `f64`, and the claim has been narrowed to match

The module prose claimed losslessness *"about all three spellings … because a
claim of losslessness that one spelling falsifies is worse than no claim"*. That
absolute claim is false and has been rewritten, because a scalar the tree CAN hold
is read as the `f64` it parses to, and distinct decimals do collapse. Measured by
me:

```
x-tiny: 3e-324, 5e-324, 7e-324   -> all show 5e-324, all digest sha256:f6d40998…
```

The obvious widening — `f == 0.0 || f.is_subnormal()` — was measured and
**rejected**, because it is not narrow: `1e-310` is subnormal (the smallest NORMAL
f64 is `2.2250738585072014e-308`) and loses nothing, so that rule would refuse
figures held to full precision. It would not close the general case anyway: in the
ordinary NORMAL range `"0.1"` and `"0.1000000000000000055511151231257827"` parse
**equal**. Collapse from float rounding is a property of reading YAML numbers as
`f64`, not of the subnormal decade, and closing it means refusing every number in
the format.

The line therefore stays where the figure is **gone** rather than **rounded** —
zero, the only place that is categorically true. The governance surface of the same
gap, measured: `must-pass: 1e-320%` still loads clean, so a bar in the subnormal
decade is not caught. The boundary and these digests are now recorded in
`resolve_scalar`'s own note and in `underflowed_to_zero`'s doc comment, so the
claim in the tree is one the tree can keep.

### 2. A size written as a bare float still answers differently from a quoted one

> **CLOSED by C10** (`docs/remediation/C10-number-too-big-dead-end.md`), which had
> to close it: the same door at the TOP of the scale gave `context-at-least: 1e19`
> and `context-at-least: 10000000000000000000` — one `f64` — two opposite answers.
> `coerce::size` reads a `Value::Float` now, `32000.0` is a size, and the two
> spellings of `0.5` both reach `schema/below-the-floor`. The `coerce::tests`
> assertion below was moved to the new answer rather than deleted, and
> `check_floor`'s `Size(0)` arm had to move with it — measured, it asked
> `node.as_str()`, which a float has none of, so for one build a bare
> `context-at-least: 0.5` loaded CLEANLY as a context window of zero. What
> follows is the record as it stood.

```
context-at-least: 0.5     error: … should be a size, like `32k` or `200000`, but it is a number.   schema/wrong-type
context-at-least: "0.5"   error: … is 0.5, which is no tokens at all.                             schema/below-the-floor
```

Both are true and both point the author at `32k`; they differ because a bare `0.5`
is a `Value::Float` and leaves `coerce::size` at its `_ => return None`, so it never
reaches the floor. Closing the gap means accepting `Value::Float` as a size, which
**widens what loads** — `context-at-least: 32000.0` is refused today and would stop
being — and is a change to the grammar rather than to this fix. Recorded in
`coerce::tests` as an assertion, so it cannot drift unobserved.

### 3. `1e-999ms` is still *"some text"*

Measured: `finishes-within: 1e-999ms` →
*"should be a length of time, like `2s`, `500ms` or `5 minutes`, but it is some
text."*, `schema/wrong-type`. A duration spelling whose number part uses an
exponent is not parsed by `coerce::duration`. This is **not** a regression from
this fix — `1e-999ms` contains letters and has always been a `Value::Str` — and it
is one order of obscurity past `0.4ms`, which is handled. Named here because the
noun repair does not reach it: `"1e-999ms"` does not parse as an `f64`, so
`kind_as_written` correctly declines to call it a figure.

### 4. An unquoted underflowing scalar and its quoted spelling now hash identically

Measured by me:

```
x-tiny: 1e-999     -> show "1e-999"   digest sha256:d310fd6a…
x-tiny: "1e-999"   -> show "1e-999"   digest sha256:d310fd6a…      (identical)
```

Under mutation A these two produced **different** digests, so this collapse is
something the fix introduced. It is the exact shape of queue row **C14**, which
records the same collapse at the TOP of the number line after C3
(`x-threshold: 1e999` vs `"1e999"`). Both readings are defensible — the author
wrote two different things, or the author wrote the same number two ways — and
picking one is a decision about what `x-` promises rather than a bug fix. **No test
pins either behaviour**, at either end. Whoever takes C14 should settle both ends
together; this document's only contribution is to record that the bottom end now
behaves as the top end does.

### 5. The family is held together by hand

Stated in [Alternatives rejected](#alternatives-rejected) and repeated here because
it is the thing most likely to bite next: nothing structural requires a new numeric
`Coerced` variant to answer the underflow question. `Percent` was missed for a
round and `Size` was given a hard-coded zero for a round. A `Ty`-indexed table with
no wildcard would make the next omission a compile error. Not attempted — it
touches every arm of `check_ceiling` and belongs in its own row.
