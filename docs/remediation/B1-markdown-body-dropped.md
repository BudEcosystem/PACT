# B1 — a markdown body was dropped without a word when its front matter was not a map, and the first repair traded that silent loss for the opposite one

**Severity: high** · **Status: fixed, then found wrong in four directions and
re-fixed in this pass** · **Register row: this replaces the one-line row *"prose
below the `---` line never just disappears"* in
`docs/remediation/REGISTER.md` §2 — see [Register update](#register-update).**

`instructions.md`, `SKILL.md` and every other markdown file an author writes is
*settings, then prose*. When the part between the `---` lines was not settings,
the prose had nowhere to go and went nowhere: no message, exit 0, and the
sentence that capped a refund simply absent from the document.

**The first repair reported the loss and kept the wrong half.** It refused the
file, which closed the silence — and then handed the parsed fence downstream, so
the sentence was *still* missing from the document, the schema added a second
error about a field the author never typed, and on a self file one mistake came
out as four messages. Every one of those was measured in this pass, on the
shipped worked example, through the real binary. The rule kept its id and its
severity; what changed is **which half of the file survives**, and that is now
asserted rather than left open.

---

### How to read the numbers below

Every figure names the command that produced it, run by me against this working
tree on this machine. Three states are distinguished and never mixed:

* **before** — the original defect, reproduced by applying one named mutation to
  the current source in an isolated copy of the tree, building the binary there,
  and running it. The mutation and the checksum after reverting are in
  [The mutation](#the-mutation).
* **first repair** — the state this issue was handed to me in:
  `crates/pact-doc/src/markdown.rs` md5 `60d809b99189957685f22f96ad920d2d`.
* **now** — this working tree, md5 `8938ad6888c04cac3d8d06897dd174af`.

**Another session was writing this repository throughout.** Every build for these
measurements used a private `CARGO_TARGET_DIR` under the scratchpad, and every
mutation was applied to a copy of `crates/`, `examples/`, `spec/` and `models/`
outside the repository, so nothing here depended on — or disturbed — the shared
`target/`.

---

## What is wrong

### The reproduction, before

A one-agent workspace. `agents/desk/instructions.md`:

```text
---
Be brief.
---
You are a careful refund desk. NEVER approve a refund over 100 USD.
```

```text
$ pact check <ws>
OK — <ws> loaded cleanly (8 settings).
exit=0

$ pact show <ws>
      "instructions": "Be brief."
exit=0
```

The refund limit — the one line in the file that exists to stop money going out
of the door — is gone, and the checker says the workspace is clean. T7 (*no
silent loss anywhere*) and AC-7.1 broken in the quietest way available.

### What the first repair actually did, measured

`pact check` on one-agent workspaces, one file each, against the binary built
from `60d809b99189957685f22f96ad920d2d`:

| file | before | first repair | now |
|---|---|---|---|
| field file, scalar fence (`---` / `Be brief.` / `---` / sentence) | exit 0, *"loaded cleanly (8 settings)"*, `instructions: "Be brief."` — sentence gone | 1 error, sentence **still gone** from the document | 1 error, **sentence in the document** |
| field file, list fence | 1 error (`schema/wrong-type`, *"'instructions' should be some text, but it is a list"*), sentence dropped in silence | **2 errors** — the same `wrong-type` plus the new refusal | 1 error, sentence in the document |
| field file, empty fence pair (`---` / `---` / blank / body) | 1 error (`schema/wrong-type`, *"…but it is nothing"*), body dropped in silence | **2 errors** | **loads cleanly, body in the document** |
| self file `agent.md`, scalar fence | 3 errors, incl. *"'content' is not something an agent can have — fix: Remove it, or use one of: name, description, …"* | **4 errors**, the same invented `'content'` among them | **1 error** |
| self file `agent.md`, list fence | 3 errors (`loader/self-file-not-settings` + two `schema/missing-field`) | **4 errors** — first and last are one mistake told twice | **1 error** |
| `SKILL.md` with `content:` at the top **and** prose below | warning, **exit 0**, prose absent from `pact show` | unchanged | **1 error, exit 1** |

The first repair made four of the six shapes *worse* by message count, left the
issue's own author-visible outcome (`instructions: "Be brief."` with the sentence
missing) in place under a different exit code, and left a seventh shape — the
`content:`-plus-prose conflict twenty lines above it in the same function —
producing exactly the outcome B1 exists to prevent.

### The conflict arm was the same defect, and the comment said it was not

`markdown.rs` had a warning for *"this file sets the body field at the top and
also has text below the line"*, justified in a comment as: *"An ERROR, not a
warning like the conflict above: there both values are still in front of the
author and only the choice is open, whereas here content would simply be
discarded"*. Both halves of that sentence are true of the **file** and false of
the **document**. Measured on a copy of the shipped worked example whose
`skills/refund-policy/SKILL.md` is

```text
---
name: refund-policy
description: What refunds we allow.
use-when: a customer asks for money back
content: Ask for the receipt.
---
NEVER approve a refund over 100 USD.
```

```text
$ pact check <copy>
warning: This file sets 'content' at the top and also has text below the '---' line.
  rule: doc/body-and-field
OK — <copy> loaded with 1 warning(s).
exit=0

$ pact show <copy>            # exit=0
      "content": "Ask for the receipt.",
$ pact show <copy> | grep -c 'NEVER approve a refund over 100'
0
```

`content:` is a documented field of a skill (`spec/schema.yaml:1673`), so this is
reachable with nothing but the spec in front of the author — and its own help
text (`spec/schema.yaml:1682`) says the procedure is *"prose under the settings
above, not a `content:` line"*, which is the shape that collides.

---

## Root cause

`Markdown::into_node` (`crates/pact-doc/src/markdown.rs`) folds the prose into
the front matter under a body field. That fold is only possible when the front
matter is a **map**, and the map case was written as an `if let` with no `else`:

```rust
if let Value::Map(m) = &mut fm.value {
    m.insert(body_field.to_string(), …);   // the prose lands here
}
(fm, None)                                  // ← and otherwise, nothing
```

Three ways an author's file reaches that arm, none of them exotic:

1. **a stray sentence** between the fences — `---` used as a horizontal rule, or
   a template pasted in;
2. **a list** — `- keep every receipt` / `- log every refund`;
3. **an empty fence pair**, or one holding only `#` comments — YAML's answer for
   both is *no document at all*, which is not a map either.

The loss is not in the parser: `parse_markdown` returns the body intact in
`Markdown::body`. It is in the one function that decides where the body goes,
which had one destination and no answer when that destination did not exist.

### Why the first repair was wrong

It filled in the missing `else` with a diagnostic and returned `(fm, Some(d))` —
**the parsed fence**. Two consequences, both measured above:

* the prose was reported and still lost, so the document had the hole the issue
  is named for;
* the fence was planted in the slot the prose was meant for, so the schema then
  complained about *that* — `'instructions' should be some text, but it is a
  list` — and on a self file the fence's scalar became `content`, a field name
  the author never typed. One mistake, four messages. `crates/pact-loader/src/lib.rs:573`
  states the rejected principle verbatim, fifty lines from where it happened:
  *"The placeholder is an EMPTY map rather than the parsed fragment: … required-field
  complaints about a file that did not parse would be the same pile-on in another form."*

---

## Why nothing caught it

* **The rule existed in two places in the whole repository.** `grep -rn
  "front-matter-not-settings" --include=*.rs --include=*.py --include=*.ts .`
  (excluding `research/` and the generated `site/`) returned, in the state this
  pass received, the source line in `markdown.rs` and the test's own `RULE`
  constant — nothing else. No CLI test, no Python test, nothing at the shipped
  door. Re-run now it also returns the new CLI test and this document.
* **The test asserted a disjunction over one half of the file.** *"the sentence
  is in the document OR a diagnostic names the file"*, and then `if reached {
  return; }`. Nothing asserted that the front matter survived or was reported, so
  the opposite repair — fold the prose into a fresh map and drop the author's
  front matter silently — passed it. I verified that with mutation **M2** below:
  under it the old file's six tests were green.
* **Three of the six tests were vacuous without the fix.** They asserted only the
  ABSENCE of the new rule id, so they could not tell *"correctly silent"* from
  *"the rule does not exist"*.
* **Every fixture omitted the blank line after the closing fence** — the layout
  this module's own header documents and the shipped `SKILL.md` uses — which was
  the only layout in which the caret happened to land on words. See
  [Failure cases](#failure-cases), case 8.
* **The message wording and the span arrangement were pinned by nothing.**
  Mutating `kind_name()` to a raw enum discriminant, or swapping the two spans,
  left all six tests green (reviewer's measurement, reproduced here as **M3** and
  **M4**: both now go red).
* **The fuzzer that exists for this class cannot generate the input.**
  `adapters/python/tests/test_nothing_vanishes_between_the_file_and_the_document.py`
  mutates YAML documents; a markdown body under a non-map fence is outside its
  reach by construction.

---

## The fix

Four changes, all in the two files the fold lives in.

### 1. An empty fence pair is not front matter — `markdown.rs:111`

```rust
if matches!(fm.value, Value::Null) {
    return Folded::plain(Node::str(self.body, self.body_span));
}
```

`---` / `---`, or fences holding nothing but `#` comments, hold **no document**;
there is nothing above the line to lose, so the file is simply its text. This is
the module's own stated dichotomy (`markdown.rs:15-25`) and the same line
`pact_loader::holds_no_document` (`crates/pact-loader/src/lib.rs:1017`) already
draws one crate up. Refusing it was PACT refusing to read a file every other tool
reads: of the nine files in this repository's vendored corpus whose front matter
parses to something that is not a map and whose body is not blank, **six are this
shape** — see [Blast radius](#blast-radius).

### 2. The prose is what survives, and it says so — `markdown.rs:168-221`

The non-map arm returns `Node::str(self.body, self.body_span)` and reports the
**front matter** as what has nowhere to go:

```text
error: The part of 'instructions.md' between the '---' lines is a list instead of
       a set of settings, so none of it could be read and none of it reached the
       document.
  --> …/agents/desk/instructions.md:2:1
  |
2 | - keep every receipt
  | ^^^^^^^^^^^^^^^^^^^^
  note: the text below the line was read as the whole of 'instructions.md' (…:5:1)
  fix: Delete both '---' lines, so the whole of 'instructions.md' is just its text.
       If the top really is meant to be settings, write one per line between the
       '---' lines, like `description: what this is`.
  rule: doc/front-matter-not-settings
```

Three things move together here, and they have to: the **sentence** now says the
fence is what was refused, the **caret** is under the fence, and the **note** is
on the prose that was kept. The reviewer's prescription was the opposite
arrangement — caret on the prose — which was right for the *old* message, whose
subject was the lost body. A caret under the half that survived would now
contradict the words above it, so the arrangement is inverted deliberately and
pinned in both directions (span line, note line, and the rendered kind word) by
`nothing_the_author_wrote_in_a_markdown_file_vanishes`.

Keeping the prose is also what costs the author the fewest messages: it is what
the slot asked for, so the schema has nothing to add. The list and empty-fence
shapes went from two messages to one and zero.

### 3. A self file that supplied no settings contributes nothing — `pact-loader/src/lib.rs:151-168`, `:437-439`, `:498`

The prose is right for a field slot and wrong for a self file, where its
destination is a name the author never typed. `Folded` carries a third field,
`front_matter_refused`, and `Loader::read_file` now takes the file's `Position`:

```rust
if folded.front_matter_refused && position == Position::SelfFile {
    return None;
}
```

`load_dir` already has the answer for a self file it could not read — a
placeholder carrying `pact_doc::UNLOADED`, so the schema says nothing about a
document that did not come out (CHK-12, `docs/20-ARCHITECTURE-R5.md:8368`). This
is that case, so it gets that answer: `agents/desk/agent.md` went from **four**
errors to **one**, and the invented `'content' … fix: Remove it` — the exact pair
of strings `crates/pact-cli/tests/an_unfinished_file_is_reported_only_for_what_is_missing.rs:110-119`
forbids — is gone from this shape.

`unloaded()` is deliberately **not** used for the field-file half. I read
`crates/pact-schema/src/lib.rs:554`: `UNLOADED` is consulted in exactly one place,
`settings_incomplete`, which suppresses *absence* complaints on a group. A
placeholder map planted in a slot that takes text would still trip
`schema/wrong-type`, so it would have swapped one derivative message for another.

### 4. `doc/body-and-field` is an error — `markdown.rs:127-155`

One field written twice in one file is the same mistake as one field written in
two files, and the loader has refused that all along:
`crates/pact-loader/src/lib.rs:535` — *"A field defined by the self file AND by a
sibling entry is ambiguous. Refuse rather than pick (T7)."* Exactly one of the two
authored values reaches the document, so the run does not start until the author
says which one they meant. The message says so now (*"the same setting is written
twice and only one of them can be kept"*); the fix is unchanged, because it was
already the typeable one.

### 5. The caret is under words, never under the blank line — `markdown.rs:250-293`

`body_span` started at the byte after the closing fence. Convention puts a blank
line there, so the primary caret of **both** rules landed on nothing:

```text
  --> …/instructions.md:4:1
  |
4 |
  | ^
```

Measured on this repository's own vendored real-world file,
`research/repos/filedef/opencode/packages/opencode/test/config/fixtures/empty-frontmatter.md`,
copied verbatim into a workspace. `first_line_with_words` advances the span to the
first line of the body that has non-whitespace on it. The body **string** is
untouched — leading whitespace is content, an indented first line is a code block
— so this moves where the reader is pointed and nothing else.

---

## Alternatives rejected

| Alternative | Why not |
|---|---|
| **Keep the front matter, report the body** (the first repair) | Leaves the document with the hole the issue is named for, and plants a value of the wrong shape in the slot, which the schema then reports as a second mistake. Measured: two errors for the list shape, four for a self file. |
| **Keep the whole file, fences and all, as the body** | Lossless, and it invents content: `instructions` would begin `---\nBe brief.\n---` and those fence lines are not something the author wrote as instruction text. "Translate or nothing" cuts against a translation that is subtly wrong, and the load is refused anyway, so nothing is bought. |
| **Return `unloaded()` for the field slot** | `pact-schema/src/lib.rs:554` consults `UNLOADED` only to suppress absence complaints on a group. A placeholder map in a text slot still trips `schema/wrong-type` — the same pile-on in another form. |
| **Fold the body into a fresh map and carry on** | The mutation **M2** below. Silently discards the author's front matter — the same class of loss, reopened from the other side, with a green gate. It passed all six tests of the previous version of the test file. |
| **Leave `doc/body-and-field` a warning and only delete the false comment** | The reviewer offered this as option (b). It leaves `pact check` exiting 0 over a document that is missing a line the author wrote, which is the sentence in this issue's title. `loader/ambiguous-field` already refuses the same mistake spelled across two files; two answers to one question is the drift this repository keeps paying for. |
| **Refuse the empty fence pair too, for uniformity** | Nothing is above the line to lose, so there is nothing to refuse — and six of the nine real-world instances in the corpus are that shape. Uniformity would have bought a refusal of files that lose nothing. |
| **Fix the prose-in-a-self-file fold as well** (see [What remains open](#what-remains-open)) | A different root cause — it needs no `---` line at all — and closing it needs the folder's *kind* inside the loader, which is a change of a different size. Recorded, measured, and left. |

---

## Blast radius

**What reads this code.** `Markdown::into_node` has exactly one non-test caller:
`Loader::read_file`. `grep -rln "front.matter\|front_matter\|frontmatter"
adapters/ --include=*.py --include=*.ts` returns nothing, so there is no second
markdown reader in the Python or TypeScript port and no parity work to mirror.

**What the author sees.** Six shapes change (the table in [What is
wrong](#what-is-wrong)). One shape newly loads clean where it used to be refused
(the empty fence pair), and one newly refuses where it used to warn
(`doc/body-and-field`). The shipped example is untouched: `pact check
examples/refund-desk` → *"OK — … loaded cleanly (498 settings)"*, exit 0, and
`the_shipped_example_is_untouched_by_all_of_this` holds it.

**Real files.** Every `.md` under `examples/ spec/ site-docs/ adapters/ crates/
docs/ research/ tests/` that opens with `---`, has a closing fence, front matter
that is not a map, and a non-blank body — `python3` + `yaml.safe_load`, my scan:

* **16** files, of which **7** have front matter YAML cannot parse at all (a
  different rule, `doc/yaml-syntax`, and untouched here);
* **9** parse to a non-map. **6 are `None`** — opencode's
  `test/config/fixtures/empty-frontmatter.md` and five pydantic-ai
  `.github/workflows/shared/*.md` whose fences hold only `#` comments — and all
  six now load clean where the first repair refused them. **3 are strings**
  (`mastra/auth/cloud/cloud-auth.md`, `letta/tests/data/test.md`,
  `memgpt-paper-code/tests/data/test.md`), which are refused, with their prose in
  the document.

**Digests.** No value changes for any document that loaded before: the span fix
moves a caret, and `Folded` is a return shape. `cargo test --workspace` includes
`digest_equality_for_the_new_kinds` and `example_refund_desk`; both pass.

---

## The test

| File | What it holds |
|---|---|
| `crates/pact-loader/tests/a_sentence_below_the_settings_never_just_disappears.rs` (5 tests, rewritten) | The document. For every shape: the prose arrives, **and** what the fences held is either in the document or refused out loud, once, as an error, with the file named, the kind in plain words, the caret on the fence and the note on the prose. Plus: the empty fence pair loads clean and silent; a self file invents no setting; a blank body is left alone *and keeps what it does hold*; the conflict arm is refused once and the discarded half is pinned. |
| `crates/pact-cli/tests/a_fence_that_is_not_settings_is_one_mistake_told_once.rs` (6 tests, new) | The shipped door, on copies of the worked example. `check` refuses and prints the rule id; the problem is told **exactly once**; the block names the kind, carries a typeable fix, and never says `'content'` or `Remove it`; `show`, `waits` and `card` all exit non-zero on the same tree; the empty fence pair loads clean and `pact show` prints the body; the untouched example still loads. |
| `crates/pact-cli/tests/an_unfinished_file_is_reported_only_for_what_is_missing.rs` (+1 test) | That file's own invariant, on the shape that used to escape it: a markdown **self** file whose fences are not settings gets one message, and no invented setting name. Every other fixture in it is YAML or an empty markdown file. |
| `crates/pact-doc/src/markdown.rs` (+3 in-module tests) | The unit-level shape of the same three decisions: the blank line after the fence is not what the span points at; a fence pair holding nothing (or only comments) is not front matter; the refusal keeps the prose, refuses the fence, and says which is which. |

Two doors on purpose. The loader test can assert what the document *becomes* and
cannot see an exit status; the CLI test can assert the exit status and the message
count and cannot see the document. The claim in this issue's title needs both.

---

## The mutation

Each was applied **alone** to a copy of the tree
(`scratchpad/iso`, holding `crates/ examples/ spec/ models/ Cargo.*`), the four
affected suites were run, and the source was restored and re-checksummed. The
scaffold that did it is `scratchpad/mutate.py`; it asserts the mutated snippet
occurs exactly once and compares md5 before and after.

| # | Mutation | Result |
|---|---|---|
| M0 | The original defect: drop the diagnostic, end the non-map arm with `Folded::plain(fm)` | loader `FAILED. 3 passed; 2 failed` · cli-fence `FAILED. 2 passed; 4 failed` · cli-unfinished `FAILED. 6 passed; 1 failed` · doc-lib `FAILED. 50 passed; 1 failed` |
| M1 | The first repair: return `Folded { node: fm, … }` | loader `FAILED. 4 passed; 1 failed` (`nothing_the_author_wrote_…`) · cli-fence `FAILED. 5 passed; 1 failed` (`a_list_above_the_line_of_a_field_file_is_told_once`) · doc-lib `FAILED. 50 passed; 1 failed` |
| M2 | Fold anyway into a fresh map, no diagnostic — the opposite silent loss, which passed all six of the previous tests | loader `FAILED. 3 passed; 2 failed` · cli-fence `FAILED. 2 passed; 4 failed` · cli-unfinished `FAILED. 6 passed; 1 failed` · doc-lib `FAILED. 50 passed; 1 failed` |
| M3 | `format!("{:?}", std::mem::discriminant(&fm.value))` for `kind_name()` | loader `FAILED. 4 passed; 1 failed` · cli-fence `FAILED. 2 passed; 4 failed` · doc-lib `FAILED` |
| M4 | Swap the spans: caret on the prose, note on the fence | loader `FAILED. 4 passed; 1 failed` · doc-lib `FAILED` |
| M5 | `Diagnostic::warning` for `doc/front-matter-not-settings` | loader `FAILED` · cli-fence `FAILED. 2 passed; 4 failed` · cli-unfinished `FAILED. 6 passed; 1 failed` · doc-lib `FAILED` |
| M6 | Refuse the empty fence pair (drop the `Value::Null` arm) | loader `FAILED` (`a_fence_pair_holding_nothing_…`) · cli-fence `FAILED. 5 passed; 1 failed` · doc-lib `FAILED` |
| M7 | Delete the `Position::SelfFile` arm of `Loader::read_file` — the one mutation in `pact-loader` | loader `FAILED` (`a_self_file_whose_fences_…`) · cli-fence `FAILED. 4 passed; 2 failed` · cli-unfinished `FAILED. 6 passed; 1 failed` |
| M8 | Point `body_span` at the byte after the fence again | loader `FAILED` · doc-lib `FAILED` (`the_body_span_skips_the_blank_line_…`) |
| M9 | `doc/body-and-field` back to a warning | loader `FAILED` (`the_body_and_field_conflict_…`) · doc-lib `FAILED` |

`markdown.rs` md5 after every revert: `8938ad6888c04cac3d8d06897dd174af`;
`pact-loader/src/lib.rs` after M7: `7e8eb39e6ba673b583ae3f2df35dd733`.

Two of these — M3 and M4 — are the mutations the previous test file could not see
at all, and the reviewer reports having watched a build in this tree print
`… is Discriminant(4) instead of a set of settings` while measuring. I did not
reproduce that build; what I did reproduce is that the mutation now fails four
tests in two crates.

---

## Failure cases

Every shape I put through the binary, with what it does **now** and which test
holds it. Short names: **L** = the five tests in
`crates/pact-loader/tests/a_sentence_below_the_settings_never_just_disappears.rs`;
**C** = the six in
`crates/pact-cli/tests/a_fence_that_is_not_settings_is_one_mistake_told_once.rs`;
**U** = the one added to
`crates/pact-cli/tests/an_unfinished_file_is_reported_only_for_what_is_missing.rs`;
**D** = the in-module tests in `crates/pact-doc/src/markdown.rs`.

1. `---` / scalar / `---` / prose, **field file** — one error, prose in the document.
   covered-by `L nothing_the_author_wrote_in_a_markdown_file_vanishes` (case `scalar`)
   and `C a_stray_sentence_above_the_line_of_a_field_file_is_told_once`.
2. The same **without** the blank line after the fence — same answer; both layouts
   are fixtures, because the tight one was all the old test had.
   covered-by `L nothing_the_author_wrote_…` (case `scalar-tight`).
3. The caret under the fence and the note on the first line of prose (line 5 of the
   conventional layout, not the blank line 4).
   covered-by `L nothing_the_author_wrote_…` — `d.span.line == 2` and
   `note.span.line == line_of(md, SENTENCE)`, asserted per case — and by
   `D the_body_span_skips_the_blank_line_the_convention_puts_after_the_fence`.
4. `---` / list / `---` / prose — one error (was two: `schema/wrong-type` came with it).
   covered-by `L nothing_the_author_wrote_…` (case `list`) and
   `C a_list_above_the_line_of_a_field_file_is_told_once`.
5. `---` / `4242` / `---` / prose — one error, *"a whole number"*.
   covered-by `L nothing_the_author_wrote_…` (case `number`); this is the third kind
   word, so `kind_name()` is pinned on three shapes rather than one.
6. `---` / real settings / `---` / prose — both halves in the document, nothing said.
   covered-by `L nothing_the_author_wrote_…` (case `real-settings`) and
   `D front_matter_and_body_combine`.
7. `---` / `---` / prose — loads clean, body in the document (was one error before, two under the first repair).
   covered-by `L a_fence_pair_holding_nothing_loses_nothing_and_says_nothing`
   (case `opencode-shape`), `C a_fence_pair_holding_nothing_still_loads_clean`, and
   `D a_fence_pair_holding_nothing_is_not_front_matter_at_all`.
8. `---` / `# comment` / `---` / prose — loads clean.
   covered-by the `comments-only` case of the same `L` test and the
   `comment-fences` case of the same `C` test.
9. The vendored opencode fixture copied in **verbatim** as `instructions.md` — loads
   clean, `pact show` prints the body. Measured by hand:
   `pact check opencode` → *"OK — opencode loaded cleanly (498 settings)"*, exit 0.
   UNCOVERED as a file — the tests reproduce its *shape* (case 7), not the file, because
   a test that reads `research/` would tie the gate to a vendored tree.
10. A pydantic-ai `.github/workflows/shared/adversarial-review.md` verbatim as
    `instructions.md` — measured by hand: exit 0, and `pact show | grep -c
    adversarial` → 1. UNCOVERED as a file, same reason; its shape is case 8.
11. `---` / scalar / `---` / **blank** body — silent, and the scalar is still the field's value.
    covered-by `L an_unfinished_file_with_no_text_below_the_fences_is_left_alone`
    (case `blank-scalar`, which asserts both the silence and that `Be brief.` survives)
    and `D empty_body_after_front_matter_is_not_a_conflict`.
12. `---` / `---` / blank body — silent, and the field is still contributed.
    covered-by the `blank-empty` case of the same `L` test.
13. `---` / scalar / `---` / prose, **self file** `agent.md` — one error (was four, one of them naming `content`).
    covered-by `C a_stray_sentence_above_the_line_of_a_self_file_is_told_once` and
    `U a_markdown_self_file_whose_fences_are_not_settings_names_no_invented_setting`.
14. `---` / list / `---` / prose, self file — one error (was four; the first and last were one mistake told twice).
    covered-by `L a_self_file_whose_fences_are_not_settings_invents_no_setting_to_hold_its_prose`
    (which also asserts the folder carries `pact_doc::UNLOADED` and that the refusal is
    the *only* diagnostic) and `C a_list_above_the_line_of_a_self_file_is_told_once`.
15. `SKILL.md` with `content:` **and** prose, on the shipped example — one error, exit 1,
    `show`/`waits`/`card` all exit 1 (was: one warning, exit 0, and `pact show` printing a
    skill with the sentence missing). Measured by hand on a copy of `examples/refund-desk`
    with `content: Ask for the receipt.` added above the closing fence:
    *"error: This file sets 'content' at the top and also has text below the '---' line…
    rule: doc/body-and-field · 1 problem(s) found · Nothing was run"*, `check`/`show`/`waits`/`card`
    all exit 1.
    covered-by `L the_body_and_field_conflict_is_refused_once_and_the_discard_is_pinned`
    for the document (one report, `Severity::Error`, the explicit setting kept and the prose
    provably not in the document) and `D setting_the_body_field_twice_is_refused_rather_than_silently_picked`.
    **UNCOVERED at the shipped door**: no test runs `pact check` over a `doc/body-and-field`
    tree, so the exit status of *this* rule, and the `SKILL.md` slot specifically, rest on the
    hand measurement above. `grep -rn "body-and-field" crates/pact-cli/tests/` returns nothing.
16. **CRLF line endings with a BOM, over a scalar fence** — measured by hand: one error, the
    kind word *"some text"*, caret on line 2, note on line 5, exit 1. UNCOVERED:
    `D crlf_and_bom_are_tolerated` uses **map** front matter, so no test puts a non-map
    fence through the CRLF path. Correct today, cheap to add as one more `Case` row.
17. Prose with no fences at all — untouched, still the file's text.
    covered-by `D plain_markdown_is_just_text` (and every `instructions.md` in the
    shipped example).
18. An unterminated `---` — untouched, `doc/unterminated-front-matter`, refused before
    `into_node` runs.
    covered-by `D unterminated_front_matter_is_a_clear_error`.
19. `pact check examples/refund-desk` — *"OK — … loaded cleanly (498 settings)"*, exit 0.
    covered-by `C the_shipped_example_is_untouched_by_all_of_this`, plus
    `the_examples_stay_clean_under_deny_warnings` and `example_refund_desk` in the gate.
20. A `SKILL.md` that is nothing but prose (no fences) — still its own procedure, not an
    unfinished file. covered-by
    `an_unfinished_file_is_reported_only_for_what_is_missing.rs::a_procedure_written_as_plain_prose_is_not_mistaken_for_an_unfinished_file`.

Four entries above are marked UNCOVERED, and every one of them is **measured
correct** rather than suspected broken: the two vendored files as files (9, 10), the
`doc/body-and-field` exit status at the shipped door (15), and CRLF+BOM over a
non-map fence (16).

---

## Verification

Scoped, in this working tree, with a private `CARGO_TARGET_DIR`:

```text
$ cargo test -p pact-doc                → ok. 51 passed; 0 failed
$ cargo test -p pact-loader             → ok, 15 binaries, 0 failed
$ cargo test -p pact-cli --test a_fence_that_is_not_settings_is_one_mistake_told_once
                                        → ok. 6 passed; 0 failed
$ cargo test -p pact-cli --test an_unfinished_file_is_reported_only_for_what_is_missing
                                        → ok. 7 passed; 0 failed
```

The full gate, once:

```text
$ cargo test --workspace                → 91 `test result: ok` lines, 923 passed, zero FAILED
$ cargo clippy --all-targets -- -D warnings
                                        → Finished; no warnings
$ cd adapters/python && uv run pytest tests/ -q
                                        → 1954 passed, 7 skipped in 137.98s
```

`README.md`'s headline count is a claim a test reads
(`tests/test_the_headline_test_count_is_the_count.py`), and this pass adds nine
Rust tests (+3 in `markdown.rs`, +6 in the new CLI file, +1 in the unfinished-file
file, −1 from the loader file, which went from six tests to five). It failed
first, naming the numbers; `README.md:73` and `:79` now read **2884 tests (923
Rust + 1961 adapter)**, and the suite passes.

---

## Register update

`docs/remediation/REGISTER.md` §2 carried one row for this: *"prose below the
`---` line never just disappears | `crates/pact-loader/tests/a_sentence_below_the_settings_never_just_disappears.rs`"*.
True and not sufficient — that test could not tell the landed fix from the
opposite silent loss, and it never saw an exit status. The row now names both
doors and this document. `docs/remediation/QUEUE.md` row 11 is `done`.

---

## What remains open

Two measured defects that are **not** this arm, left deliberately, and one
judgement call.

**1. Prose in a self file whose kind has no body field.** `agents/desk/agent.md`
containing nothing but prose — no `---` line anywhere — still gives:

```text
error: An agent must have a 'description'.
error: An agent must have 'instructions'.
error: 'content' is not something an agent can have.
  fix: Remove it, or use one of: name, description, instructions, …
3 problem(s) found. exit=1
```

Measured on this tree, now. It is the invariant
`an_unfinished_file_is_reported_only_for_what_is_missing.rs` states, violated by a
file with no fences in it, so B1's arm is not the cause and was not the cure:
`fields_of_self_file` (`crates/pact-loader/src/lib.rs:621`) folds prose into
`policy.body_field` for every folder, and `content` is a field of a **skill**
(`spec/schema.yaml:1673`), not of an agent. Closing it means the loader knowing the
folder's kind before it folds, which is a change of a different size from this one.
It is why the fourth test in that file uses `skills/refund-policy/SKILL.md`.

**2. The blank line after the fence is inside the value.** `pact show
examples/refund-desk` gives `skills.refund-policy.content` beginning `'\n# Refund
policy\n\n## Rules…'`, while `agents/refund-desk/instructions.md` — the same words
in a file with no front matter — begins `'You decide whether…'`. That leading
newline is the mirror image of the trailing one `prose()`'s own docstring records
as having broken the Expansion Rule (`content:` written inline versus the same
words in a file are meant to be the same document). Fixing it changes the value —
and therefore the digest — of every front-matter document in the repository,
including the shipped example, so it belongs in its own pass with its own
before-and-after. This pass moved the **span** only.

**3. `doc/body-and-field` is now an error, and that is a behaviour change for
authors outside this repository.** Nothing in `examples/`, `spec/` or the corpus
writes a body field twice, and the shipped example is unaffected; the argument for
refusing rather than warning is in [Alternatives
rejected](#alternatives-rejected). If it ever needs to be a warning again, the
thing that must change with it is the exit code, not the message.

---

## What a reader should take from this

The defect was one missing `else`. The interesting part is that **filling it in
was not the fix** — the first repair closed the silence and left the hole, because
"report the loss" and "lose nothing" are different requirements and only the first
one was written down. What forced the difference into the open was asking, of each
of the two halves the author wrote, *where is it now* — and putting a distinct
sentinel in each half so no single string could answer for both.
