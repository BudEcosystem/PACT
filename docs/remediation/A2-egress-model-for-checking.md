# A2 — the air-gap boundary was a hand-written table, and every layer it moved to was also incomplete

**Severity: critical.** · **Status: fixed — the model walk first, then seven
findings raised against that fix, all of them repaired.** · **Register row:
`docs/remediation/REGISTER.md:110` (*"every field that binds a model is held to
`allow-egress:`"*) is the row this closes; `docs/70-PRODUCTION-GAP-REGISTER.md`
has no row for it at all, and the line to correct there is `:282` — see
[Register update](#register-update).**

Every number below names the command that produced it, run against this working
tree. Where a measurement was taken against a pre-fix state, it says which state
and how that state was produced. Another session is editing files in this
repository right now; nothing outside this issue's own files was touched, and
nothing was left mutated.

---

## What is wrong

`allow-egress:`'s own help promises *"which parts of this system are allowed to
talk to something outside this box. Empty means nothing is."* (`spec/schema.yaml`).
D17 makes that promise the product: an air-gapped workspace writes
`allow-egress: []` and PACT refuses anything that would leave the machine.

The refusal was decided by asking **whether a line was in a list of field names
written out in Rust**. Four paths were in that list. The specification declared
more. So the boundary held or did not hold depending on **which of two adjacent
lines the author wrote the same model id on**:

```console
$ cat probe/agents/desk/agent.yaml
name: Desk
description: A desk.
instructions: Do it.
model-for-checking: claude-opus-5      # served over somebody's API, nowhere else
loop: pact:loop/standard
$ cat probe/workspace.yaml
name: probe
allow-egress: []

$ target/debug/pact check probe
OK — /tmp/probe loaded cleanly (11 settings).
```

The same id one line up, under `model:`, was refused correctly. That is the B15
failure this repository has removed twice already: **a table of field names that
nothing holds against the specification comes to disagree with the
specification.**

The landed fix replaced the table with a walk through the schema —
`names: pact:models` decides which lines bind a model. That was right, and it was
not finished. Seven further faults were found against it, four of them holes the
fix itself opened or left open, and three of them tests that did not bite. They
are in **The fix** below, because on this issue the repair and the findings
against the repair are one story.

---

## Root cause

**One question — "which lines bind a model?" — had two answers, and only one of
them was the specification's.**

The specification's answer is a `names: pact:models` line on a field, in the
place that field is declared. The checker's answer was four paths written into
`crates/pact-cli/src/egress.rs`. Nothing compared them, so they drifted, and the
drift is invisible in exactly the direction that matters: a field the table
misses produces **silence**, and silence from a checker reads as approval.

Moving the answer into `spec/schema.yaml` fixes the drift only if the
specification's own table is complete. It was not. `catalog.default:` — the model
**every agent that pins no `model:` actually runs** — carried no `names:` line.
Enumerated over the shipped specification:

```console
$ grep -n "^        names: pact:models" spec/schema.yaml     # as it now stands
563:        names: pact:models        # agent.model
587:        names: pact:models        # agent.model-for-checking
741:        names: pact:models        # catalog.default        ← added by this fix
2313:        names: pact:models       # evals.graded-by
2675:        names: pact:models       # learning-model.model
3076:        names: pact:models       # context-policy.summarised-by
```

Line 741 is the one this fix adds; the other five are what the specification
declared before it. Five fields named a model. Six bound one. `catalog.default`
was the sixth, and it was the same defect one layer further out — the table moved
from Rust into YAML and was still incomplete.

The second root cause is narrower and produced three of the seven findings:
**the fix widened the walk and did not widen what the walk's answers were
checked against.** Every fixture in the holding test wrote `allow-egress: []`,
under which *every* role refuses identically — so no test could tell `llm` from
`stt` from `judge`, and the ROLE the newly-reached fields were assigned was held
by nothing at all.

---

## Why nothing caught it

Three separate reasons, each worth stating because each needed a different
repair.

1. **The audio half of the boundary was never widened.** The words half walks
   every `names: pact:models` field. The recording half was keyed to
   `agent.model` alone, with a comment justifying it — *"an agent hears and
   speaks with the model doing its work"* — that `model-for-checking:`'s own
   help refutes on the same page: *"Expect the conversation to be read again
   from the start each time it switches."*
2. **Every fixture granted nothing.** `allow-egress: []` refuses every role, so
   the parameterised refusal test passed no matter which role the walk assigned.
3. **The new hand-written tables were not held.** The fix added `fn noun`, a
   two-row table, eight lines below the module's own account of losing the
   hand-written-table argument. A repo-wide grep for either of its sentences
   returned exactly the two source lines that write them.

---

## The fix

### 1. `catalog.default` is a model binding, and the specification now says so — `spec/schema.yaml:741`

One line, `names: pact:models`, plus the comment recording why. It closes two
holes at once, because `names:` is read by both `Schema::validate` (does this id
exist?) and `egress::bindings` (may it be reached?).

**Before** (produced by deleting that one line and rebuilding):

```console
$ target/debug/pact check A          # models/catalog.yaml: default: claude-opus-5
OK — …/A loaded cleanly (11 settings).                       exit=0
$ target/debug/pact check A3         # default: claude-opus-99-nonexistent
OK — …/A3 loaded cleanly (11 settings).                      exit=0
```

**After**, same trees, same binary:

```console
$ target/debug/pact check A
error: `default: claude-opus-5` is only served off this machine, and this workspace
  says `allow-egress: []` — nothing there lets the model doing the work talk to
  anything outside the box.
  fix: write `default: qwen2.5-7b-instruct`, which runs here; or add `llm` to
  `allow-egress:` in workspace.yaml — which is a change a person has to approve.
  rule: loader/leaves-the-box

$ target/debug/pact check A3
error: 'default' names 'claude-opus-99-nonexistent', and there is no such entry in
  the model catalogue.
  fix: Change it to one of: claude-haiku-4-5, claude-opus-5, … — or add a
  `claude-opus-99-nonexistent:` row to `models/catalog.yaml` in this workspace …
  rule: schema/no-such-name
```

The second of those is a rule the **other port already had** and the checker did
not: `adapters/python/src/pact_adapters/resolve.py:535` raises
`catalog/unknown-default` for it. Two ports disagreeing about whether a workspace
loads is the divergence class this repository holds a whole suite against.

That the field is live, not decorative, is `resolve.py:913` — `return
catalogue.default` is what an agent pinning nothing binds — and the egress
module's own comment asserted it in prose: *"PACT then binds the catalogue's
`default:`, which D17 keeps locally servable by construction."* A
workspace-supplied `models/catalog.yaml` is not servable by construction. That
sentence is now a check.

### 2. A list is read as a list only where the specification declares one — `egress.rs:478`

`ids()` read every list as a list of ids, on the argument that a field which
grows into one is then held on the day it does. Every `names: pact:models` field
is `type: text` today, so on real documents that arm could only fire on a line
`schema/wrong-type` was already refusing. **Measured** on that reading:

```console
$ target/debug/pact check D1     # graded-by: [claude-opus-5, gpt-5.4]
error: 'graded-by' should be some text, but it is a list.      rule: schema/wrong-type
error: `graded-by: claude-opus-5` is only served off this machine …
                                                               rule: loader/leaves-the-box
error: `graded-by: gpt-5.4` is only served off this machine …  rule: loader/leaves-the-box
3 problem(s) found
```

Three messages about one line, two of them advising a grant for a document that
cannot load whichever way the author resolves them — breaking `reaches`' own
*"one mistake gets one message"* rule and the invariant its sibling test asserts
literally. Simply ignoring lists would have thrown away the future-proofing the
arm was written for, so the shape is now **asked of the specification**: a
`list of text` field's items are ids, a `text` field's list is somebody else's
error. Both directions are held (see **The test**, case 7). After:

```console
$ target/debug/pact check D1
error: 'graded-by' should be some text, but it is a list.      rule: schema/wrong-type
1 problem(s) found
```

### 3. A row that has not said what it is for is not advised to over-grant — `egress.rs:599`

`learning-model.role` is `required: yes` (`spec/schema.yaml:2665`). `plays()`
already returned `None` for a role word the specification does not offer — so
the schema's message, which names the words that ARE allowed, is the only one
printed. An **absent** required role fell through to `Some(vec!["llm"])`.
**Measured** before the guard:

```console
$ target/debug/pact check R2     # learning.yaml: execution: { model: claude-opus-5 }
error: A model binding must have a 'role'.                     rule: schema/missing-field
error: `model: claude-opus-5` is only served off this machine … nothing there lets
  the model doing the work talk to anything outside the box.
  fix: … or add `llm` to `allow-egress:` …                     rule: loader/leaves-the-box
2 problem(s) found
```

An author who meant `role: judge` was advised, in writing, to make the widest
grant there is — verbatim consequence #1 in the module's own header, *"the only
typeable fix the tool offered was to over-grant."* The guard is keyed on
`required:` rather than on the group's name, because `required: yes` is what
guarantees `schema/missing-field` is already on the row, which is what makes
saying nothing here safe. After: `1 problem(s) found`, and the invalid-word case
one line over still gives `1 problem(s) found`, which is the reading the two were
made to agree on.

### 4. The recording is held against every model the conversation reaches — `egress.rs:792` (`envelope`), `egress.rs:825` (`named`)

`stt` and `tts` are deliberately not covered by `llm` — the module's single
stated asymmetry. That half of the boundary was scoped to `agent.model`.
**Measured** on the pre-fix binary, each tree with `allow-egress: [llm]`, a
locally-served `model:` and one hosted second model:

| tree | said |
|---|---|
| control: `model:` hosted, `accepts: clip: audio` | refused, named `stt` |
| `model-for-checking:` hosted, `accepts: clip: audio` | `OK — loaded cleanly (14 settings)` |
| `model-for-checking:` hosted, `answers-with: reply: a voice message` | `OK — loaded cleanly (14 settings)` |
| `model-for-checking:` hosted, `needs: audio: yes` | `OK — loaded cleanly (15 settings)` |
| named policy's `summarised-by:` hosted, `accepts: clip: audio` | `OK — loaded cleanly (17 settings)` |

The walk saw those lines — the same trees under `allow-egress: []` drew a words
refusal quoting `summarised-by:` by name — so the silence was a scoping choice,
not invisibility. `envelope()` now answers "which models does this agent's
conversation pass through?" from three schema-read sources and no table:

1. every model binding the schema declares **on the agent**, through the same
   `bindings` walk the words half uses;
2. every model binding in the documents the agent **names**, followed through the
   `names:` edges the schema declares on the agent's own fields into the
   workspace collection each one points at — today exactly
   `context-policy:` → `context-policies.<name>.summarised-by`;
3. the catalogue's `default:`, for an agent that pins no `model:`, because that
   is the model it runs.

After, all five trees are refused and each quotes its own line:

```console
error: `model-for-checking: claude-opus-5` is only served off this machine, and
  `accepts: clip: audio` means a recording goes there with the words. This
  workspace says `allow-egress: [llm]`, which lets the words out and does not
  name `stt`.
```

The "already refused" suppression became **per binding** rather than per agent:
under `allow-egress: [llm]` an agent whose `model:` is local and whose
`model-for-checking:` is hosted has nothing said about its words, and the
recording is refused on the line that would carry it.

**What is deliberately NOT in the envelope**, written down because a boundary
nobody can argue with is a boundary nobody can review: `evals.graded-by` and
`learning-model.model`. A judge sees eval **cases**, and whether one holds a
recording depends on `population:` — whose first choice,
`authored-enumeration`, means *"you wrote down the situations you thought of"* —
so refusing every such suite is the over-refusal the words half already measured
and rejected. A learning model is bound in `learning.yaml`, which belongs to the
workspace and to no one agent, so there is no `accepts:` line a message could
quote. `an_eval_judge_is_not_in_an_agents_audio_envelope` holds that position,
with a control proving the field IS held by the words half on the same tree.

### 5. Three tables that nothing held now fail by name

* **`fn noun`** (`egress.rs:499`) — two rows, added by the fix itself. A
  repo-wide grep for either sentence returned exactly two hits before this round, `egress.rs:501` and
  `egress.rs:502` in today's numbering — the source lines themselves. Deleting both arms left **60 test binaries
  green** while the shipped refusal for `model-for-checking:` became *"the model
  doing the work"* — which the field's own help contradicts one line down
  (*"Everything else uses `model:`"*), R56. Now
  `noun_in_the_refusal()` in the test file states an expected noun per field, the
  refusal test asserts it, and a sixth binding cannot arrive without somebody
  deciding what to call it.
* **The role.** See **The mutation** below.
* **The field count.** `every_field_the_specification_binds_a_model_with_has_a_tree_here`
  asserted `len() >= 5`; it now asserts `>= 6`, because otherwise deleting
  `names:` from a field silently shrinks every other test in the file — which is
  precisely how `catalog.default` was outside the boundary.

---

## Alternatives rejected

**Hold `catalog.default` by hand in `egress::reaches`, beside the audio block.**
It would work and it is the defect. The field is a model binding; the
specification is where that is said; and saying it there makes the existing
parameterised test grow a sixth case by itself and demand a fixture — which is
the mechanism the fix was built for. It also gets `schema/no-such-name` for free,
which a hand-written egress check would not.

**Make `egress::ids` ignore every list.** Simpler, and it discards the
future-proofing the arm exists for: the day a model binding is declared
`list of text`, each item is a binding and nothing would hold them. Asking the
declared type costs one `match` and holds both directions.

**Put `evals.graded-by` in the audio envelope.** A suite with
`population: promoted-traces` really can show a judge a recording. But
`authored-enumeration` cannot, PACT does not model per-case content, and
refusing every authored suite in a voice workspace is the over-refusal
`a_model_named_inside_a_block_the_specification_leaves_open_is_left_alone`
already measured and rejected on the words half. The position is written into
`envelope`'s doc-comment and held by a test, so changing it is an edit somebody
makes on purpose.

**Give `catalog.default` its own noun.** Rejected: every agent that pins nothing
runs it, so it IS the model doing the work, and the general noun is the right
answer rather than a missing one. Recorded in `noun_in_the_refusal()` as a
decision rather than left to the fallback.

---

## Blast radius

| touched | what could break | measured |
|---|---|---|
| `spec/schema.yaml:741` (`names:` on `catalog.default`) | any workspace with a `models/catalog.yaml` naming a `default:` that is hosted or misspelt now fails to load | intended. No example in the repository has a `models/catalog.yaml` (`find examples -name catalog.yaml` → nothing), and neither adapter reads `pact:models` (`grep -rn "pact:models" adapters/` → nothing) |
| same line | the site's field count | `grep -cE '^\s*names:' spec/schema.yaml` went 26 → 27; `site-docs/concepts/what.md:132` and `site-docs/status/verified.md:22` updated, held by `test_the_named_field_count_is_the_number_of_fields_that_resolve_a_name` |
| `egress::ids` (declared type) | a model binding written as a list stops drawing egress errors | intended — `schema/wrong-type` is already refusing that line. Held both directions |
| `egress::plays` (required role) | a `learning.yaml` row with no `role:` stops drawing an egress error | intended — `schema/missing-field` is already refusing that row |
| `egress::envelope` (widened audio) | a workspace with a voice agent and a hosted `model-for-checking:`/`summarised-by:`/`default:` under `allow-egress: [llm]` now fails to load | intended, and it is the finding. Controls assert the same trees without the audio line still load |
| `egress::reaches` (per-binding suppression, dedupe) | a message could double when two agents name one context policy | deduped on file+offset+roles+carried line |
| new Rust tests | the README's headline count | 888 → 896 Rust; `README.md:73` and `README.md:79` updated, held by `test_the_headline_test_count_on_the_front_page_is_the_number_the_suites_run` |

Not touched: the words half's walk (`bindings`, `descend`), `role_words`,
`WORDS`, `part`, `travels`, `grants`, `refusals`' guard for a document that
cannot draw a boundary. `cargo test --workspace` covers all of them and is green.

**Callers, downward — one, and it is inside this binary.**
`grep -rn "egress::" crates/ --include=*.rs` returns **14** lines, 13 of them
prose in comments (12 in the test file, one at `main.rs:789`) and exactly one of
them code: `crates/pact-cli/src/main.rs:818`, inside `egress_is_allowed`. `egress` is
`mod egress;` in a **binary** crate, not a library export, so no other crate, no
adapter and no external consumer links it. Nothing downstream can break.

**Callers, upward — nothing in `pact-schema` had to change.** The walk reads
`Group{name, fields}`, `Field{name, aliases, ty, names, required}` and
`Ty::{Group, MapOf, ListOf, OneOf}`, all of which pre-date this issue.
`git show HEAD:crates/pact-schema/src/lib.rs | grep -n "pub names"` finds the
field already there. The `pact-schema` edits visible in this working tree belong
to other queue rows.

**Digest — not affected, and structurally so.** `pact_doc::digest`
(`crates/pact-doc/src/canonical.rs:38`) hashes the canonical string of a node and
takes nothing else. Every function this issue added or changed takes `&Node` and
returns either a borrowed list or `()` — nothing on this path mutates a tree, so
no authored document's canonical form moves. The one line added to
`spec/schema.yaml` is a `names:` declaration read by the checker; it does not
change how any document parses.

**The five honesty channels — not affected.** They are fields on `RunResult` in
`adapters/python/src/pact_adapters/harness.py` — `unretrieved:136`, `unmetered:168`,
`unenforced:173`, `unwatched:178`, `never_reached:190`
(`grep -nE "^    [a-z_]+: tuple\[str" adapters/python/src/pact_adapters/harness.py`).
This is a
check-time rule in Rust; it neither writes nor suppresses any of them. The one
place `model-for-checking:` reaches a channel is a host that supplied no second
transport, reported on `unenforced` — a different fact, untouched.

**Both ports.** TypeScript has no checker at all — `ls adapters/typescript/src/`
is six files (`harness.ts limits.ts loops.ts run-trace.ts vercel-transport.ts
yes-no.ts`) — so there is nothing there to keep in step. Python enforces the same
boundary for the roles it can actually dial (`judge.py`, `scoring.py`,
`resolve.needs_of`) and deliberately does **not** read `model-for-checking:`
against `allow-egress:`, because the checking transport is
`SUPPLIED_BY_THE_HOST` — the adapter never dials that model itself. So the
boundary for these fields is the checker's, which is why the fix is Rust-only.
That asymmetry was unstated anywhere before this document and reads like a hole
until it is written down. `grep -rn "pact:models" adapters/` returns nothing.
The one place the two ports **did** disagree is closed by this fix rather than
created by it: Python already refused a catalogue `default:` naming no model
(`resolve.py:535`, `catalog/unknown-default`) on a workspace the checker said had
loaded cleanly.

**§7.28's four-artifact rule is not engaged.** It fires when what the *second
port reports* changes. `grep -n "egress\|allow-egress\|leaves-the-box\|
model-for-checking"` over both `the_subset_the_second_port_runs` files returns
nothing; this is a check-time rule and owes no coordinated edit.

---

## The test

`crates/pact-cli/tests/every_model_a_document_names_is_held_to_the_boundary.rs`,
15 tests. The cases are **read off the shipped `spec/schema.yaml`** — every field
of every group declaring `names: pact:models` — rather than listed in the file, so
a seventh model binding arrives as a case with no tree to run it in and
`every_field_the_specification_binds_a_model_with_has_a_tree_here` fails by name
until somebody writes one. It now also fails until somebody says what a refusal
should CALL it.

Four axes, so a case cannot pass for the wrong reason:

* **refused** — every field, hosted id, `allow-egress: []`; asserts the rule, the
  quoted line, and the noun;
* **granted** — every field, hosted id, `allow-egress: [llm]`; must load. This is
  the axis that holds the ROLE;
* **control** — every field, locally-served id, `allow-egress: []`; must load;
* **not refused** — `with:` blocks the specification leaves open, and blocks it
  does not recognise, which must not draw a second message.

Everything runs through the real `pact check` binary over real files on disk.

---

## The mutation

Six, each recorded in the test file's own header in prose, each verified by
applying it, running the scoped file, and restoring (`diff` against a backup →
identical every time).

**Provenance, stated plainly.** Those six were applied and observed **during the
repair round that landed the fix**, not while this document was being written.
Writing the document re-ran the holding file (`15 passed; 0 failed`), the whole
workspace (`89` test binaries ok, no `FAILED`), clippy, and the three behaviours
by hand through the binary — it did **not** re-apply the mutations, because
mutating a source file another session may be editing is a risk this document
does not need to take twice. The mutation numbering starts at 4 because 1–3
belong to the first round and are recorded in the test file's header:
1 restores the four-path Rust table, 2 walks by key name instead of by schema,
3 deletes the guard that stops a lone `agent.yaml` being told what a workspace it
does not have says.

| # | mutation | what goes red |
|---|---|---|
| 4 | `if field == "model-for-checking" { return Some(vec!["stt"]); }` at the top of `egress::plays` | `the_same_workspaces_load_cleanly_when_the_workspace_grants_the_role_they_play` — plus both audio tests. **3 failed** |
| 5 | delete both arms of `egress::noun` | `a_model_served_only_off_this_machine_is_refused_wherever_the_specification_binds_one`. **1 failed** |
| 6 | delete `names: pact:models` from `catalog.default` | `every_field_…_has_a_tree_here` and `a_catalogue_default_naming_no_model_at_all_is_a_typo_and_is_reported_as_one`. **2 failed** |
| 7a | `ids()` reads every list | `a_model_binding_written_as_a_list_is_one_problem_and_not_one_per_item`. **1 failed** |
| 7b | `ids()` ignores every list | `a_model_binding_the_specification_declares_as_a_list_is_read_as_one`. **1 failed** |
| 8 | delete the `required: yes` guard in `egress::plays` | `a_model_row_that_has_not_said_what_it_is_for_is_not_told_to_grant_everything`. **1 failed** |
| 9 | `envelope()` returns the agent's own `model:` only | `a_recording_is_held_against_every_model_the_conversation_passes_through`. **1 failed** |

Mutation 4 is the one that matters most, because before this round **nothing in
the repository caught it**. Measured with the mutation applied and the whole
crate run:

```console
$ timeout 2400 cargo test -p pact-cli --no-fail-fast > m4.txt
$ grep -c "^test result: ok" m4.txt
59
$ grep "^error: 1 target failed" -A1 m4.txt
    `-p pact-cli --test every_model_a_document_names_is_held_to_the_boundary`
$ grep "^test .* FAILED" m4.txt
test the_same_agents_without_audio_load_cleanly_under_a_grant_for_words ... FAILED
test the_same_workspaces_load_cleanly_when_the_workspace_grants_the_role_they_play ... FAILED
test a_recording_is_held_against_every_model_the_conversation_passes_through ... FAILED
```

59 of the 60 test binaries in the crate stay green; the only one that goes red is
the file this round added the three tests to. Before those tests existed, the
count was 60 green — and the shipped binary told an author with
`allow-egress: [llm]` to *"add `stt` to `allow-egress:`"* for a text model call,
which is the module header's consequence #1 inverted. It now fails by name.
Coverage confirms nowhere else could have: `grep -rln "model-for-checking"
crates/pact-cli/tests/` names one file, and every occurrence of it there used to
be under `allow-egress: []`, where every role refuses identically.

Mutation 1 from the original round (`if ["model", "summarised-by",
"graded-by"].contains(&f.name.as_str())` in `bindings`) was re-verified after
these changes: **2 failed**, the refusal test and the audio test.

---

## Failure cases

Every row was run through the shipped binary. "before" is the pre-fix state named
in the middle column. The last column is the test that would go red if the row
regressed, or **UNCOVERED** where there is no such test. **Twenty-seven cases in
all — twenty-two in the table plus five below it — and six of them are
UNCOVERED**, which is stated rather than smoothed over: one in the table (row 7)
and all five below. Test names are shortened; all of them
live in
`crates/pact-cli/tests/every_model_a_document_names_is_held_to_the_boundary.rs`
unless another file is named.

| # | document | before | after | held by |
|---|---|---|---|---|
| 1 | hosted id on each of the six `names: pact:models` fields, `allow-egress: []` | five refused, `catalog.default` loaded cleanly | all six refused, each quoting its own line and naming its own noun | covered-by `a_model_served_only_off_this_machine_is_refused_wherever_the_specification_binds_one` (six cases read off the spec) |
| 2 | the same six trees with a locally-served id | loads | loads — the control that stops row 1 passing because a fixture was invalid | covered-by `the_same_workspaces_with_a_model_that_runs_here_load_cleanly` |
| 3 | workspace catalogue `default:` hosted, `[]` | `OK — loaded cleanly (11 settings)` | `loader/leaves-the-box`, quotes `default:`, offers `llm` | covered-by row 1's `catalog.default` case |
| 4 | workspace catalogue `default:` names no model at all | `OK — loaded cleanly (11 settings)` | `schema/no-such-name` | covered-by `a_catalogue_default_naming_no_model_at_all_is_a_typo_and_is_reported_as_one` |
| 5 | `graded-by: [hosted, hosted]`, `[]` | `3 problem(s)` | `1 problem(s)`, `schema/wrong-type` only | covered-by `a_model_binding_written_as_a_list_is_one_problem_and_not_one_per_item` |
| 6 | a `names: pact:models` field the specification declares `list of text`, two hosted items | both items unheld under the "ignore every list" reading | both items refused | covered-by `a_model_binding_the_specification_declares_as_a_list_is_read_as_one` (runs the checker against an edited spec through `$PACT_SPEC` + `--unsafe-spec`) |
| 7 | `model: [hosted]`, `[]` | `2 problem(s)` | `1 problem(s)` — measured here: `error: 'model' should be some text, but it is a list.` | **UNCOVERED** — the list tests use `graded-by:` only. The behaviour is the same code path; no fixture pins it on `agent.model` |
| 8 | `learning.yaml` row with no `role:`, hosted model | `2 problem(s)`, the second advising `llm` | `1 problem(s)`, `schema/missing-field` | covered-by `a_model_row_that_has_not_said_what_it_is_for_is_not_told_to_grant_everything` |
| 9 | `learning.yaml` row `role: tools`, hosted model | `1 problem(s)`, `schema/wrong-type` | unchanged — the reading row 8 was made to match | covered-by that test's own in-test control, and by the sibling file `every_part_the_boundary_offers_is_one_the_checker_knows.rs` (queue row C6) |
| 10 | hosted `model-for-checking:` + `accepts: clip: audio`, `[llm]` | `OK — loaded cleanly (14 settings)` | refused, names `stt` | covered-by `a_recording_is_held_against_every_model_the_conversation_passes_through` |
| 11 | hosted `model-for-checking:` + `answers-with: reply: a voice message`, `[llm]` | `OK — loaded cleanly (14 settings)` | refused, names `tts` | covered-by the same test |
| 12 | hosted `model-for-checking:` + `needs: audio: yes`, `[llm]` | `OK — loaded cleanly (15 settings)` | refused, names `stt` | covered-by the same test |
| 13 | hosted `summarised-by:` on a named policy + audio, `[llm]` | `OK — loaded cleanly (17 settings)` | refused, quotes `summarised-by:` | covered-by the same test |
| 14 | agent pinning nothing + audio + hosted catalogue `default:`, `[llm]` | loaded cleanly | refused, quotes `default:` | covered-by the same test |
| 15 | hosted `model:` + audio, `[llm]` | refused, names `stt` | unchanged — the control arm the audio half always held | covered-by the same test (first case) |
| 16 | every tree in rows 10–15 with the audio line removed, `[llm]` | loads | loads — proves each refusal is about the recording and not the words | covered-by `the_same_agents_without_audio_load_cleanly_under_a_grant_for_words` |
| 17 | hosted `graded-by:` beside a voice agent, `[llm]` | loads | loads — a stated position, not an oversight, with a control proving the field is held by the words half on the same tree | covered-by `an_eval_judge_is_not_in_an_agents_audio_envelope` |
| 18 | every `names: pact:models` field, hosted, `[llm]` | — | loads: the grant admits the role each field plays. This is the axis that holds the ROLE | covered-by `the_same_workspaces_load_cleanly_when_the_workspace_grants_the_role_they_play` |
| 19 | lone `agent.yaml` with no workspace around it | `loader/nothing-can-run-this`, and no claim about `allow-egress:` | unchanged | covered-by `an_agent_with_no_workspace_around_it_is_not_told_what_its_workspace_says` |
| 20 | `metric.with: {model: hosted}` / `case.with: {model: hosted}` (`type: map of anything`) | loads | unchanged — an author cannot rename a key whose name belongs to DeepEval | covered-by `a_model_named_inside_a_block_the_specification_leaves_open_is_left_alone`, which carries its own in-test control |
| 21 | `model:` under a key `evals` does not declare | `schema/unknown-field`, `1 problem(s)` | unchanged | covered-by `a_model_under_a_key_evals_does_not_have_is_not_a_second_problem` |
| 22 | an agent a bundle `contributes:` — the one hand-written exception in the schema-guided walk | refused like any other | unchanged | covered-by `an_agent_a_bundle_contributes_is_held_to_the_boundary_like_any_other` |

**Five more, uncovered, measured here by hand rather than by a test:**

* **Two hosted bindings on one agent must draw two refusals.** Measured:
  `model: claude-opus-5` and `model-for-checking: claude-opus-5` under
  `allow-egress: []` prints both errors and `2 problem(s) found`. Correct, and
  **UNCOVERED** — `reaches`' doc-comment argues for it in prose and nothing holds
  it.
* **A model id in no catalogue at all is a typo, not a boundary crossing.**
  Measured: `model-for-checking: claude-opus-4.5` prints one error,
  *"'model-for-checking' names 'claude-opus-4.5', and there is no such entry in
  the model catalogue."*, `rule: schema/no-such-name`, `1 problem(s)`. That is
  the `known.contains(id)` half of the boundary check. Correct, **UNCOVERED** in
  this file.
* **An alias spelling of a model field.** `bindings` iterates
  `std::iter::once(&f.name).chain(f.aliases.iter())` (`egress.rs:367`).
  `grep -n "aliases" spec/schema.yaml` returns exactly one line — a header
  comment at `:16`, *"`aliases:` are GONE from the native authoring path (X1)"* —
  so `Field::aliases` is empty for every field the loader builds and this branch
  is **unreachable from any document today**. Forward-compatible, harmless, and
  **UNCOVERED**; recorded so no reader assumes it is exercised.
* **`evals.graded-by` in a suite whose `population:` reads real traffic.** Out of
  the audio envelope by decision — see [What remains open](#what-remains-open).
  **UNCOVERED**, and deliberately so, with the current position held by row 17.
* **Pictures.** There is no `vision` role in `allow-egress:`, so an image crosses
  under `llm` with nothing extra asked. Unchanged by this round and **UNCOVERED**:
  the module enforces the list the specification declares and invents no role of
  its own.

---

## Verification

Everything below was re-run for this document, in this working tree, after the
fix had landed. Nothing here is copied from an earlier round.

```console
$ cargo build -p pact-cli
    Finished `dev` profile [unoptimized + debuginfo] target(s)

$ cargo test -p pact-cli --test every_model_a_document_names_is_held_to_the_boundary
test result: ok. 15 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.54s

$ cargo test --workspace --no-fail-fast > ws.txt; echo $?
0
$ grep -c "^test result: ok" ws.txt
89
$ grep -E "^test result: FAILED" ws.txt        # no output

$ cargo clippy --all-targets -- -D warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s)

$ grep -n "pact:models" spec/schema.yaml
563  587  729(comment)  741  2301(comment)  2313  2610(comment)  2675  3076
$ grep -cE '^\s*names:' spec/schema.yaml
27
```

Six field declarations, three comments. `741` is the line this fix adds.

The three behaviours the issue is about, driven by hand through the shipped
binary rather than through a test:

```console
$ target/debug/pact check P            # models/catalog.yaml: default: claude-opus-5
error: `default: claude-opus-5` is only served off this machine, and this workspace
  says `allow-egress: []` — nothing there lets the model doing the work talk to
  anything outside the box.
  --> …/P/models/catalog.yaml:2:10
  fix: write `default: qwen2.5-7b-instruct`, which runs here; or add `llm` to
  `allow-egress:` in workspace.yaml — which is a change a person has to approve.
  rule: loader/leaves-the-box
1 problem(s) found …                                                     exit=1

$ target/debug/pact check P            # default: claude-opus-99-nonexistent
error: 'default' names 'claude-opus-99-nonexistent', and there is no such entry in
  the model catalogue.
  rule: schema/no-such-name

$ target/debug/pact check V   # local model:, hosted model-for-checking:, clip: audio, [llm]
error: `model-for-checking: claude-opus-5` is only served off this machine, and
  `accepts: clip: audio` means a recording goes there with the words. This workspace
  says `allow-egress: [llm]`, which lets the words out and does not name `stt`.
  fix: … or add `stt` to `allow-egress:` in workspace.yaml …
  rule: loader/leaves-the-box
```

The Rust half of the headline count, recomputed with the same regex the test
uses (`^\s*#\[(?:tokio::)?test\]\s*$` followed by an `fn` line, over
`crates/**/*.rs`): **896**, which is what `README.md:73` says.

**The adapter suite is NOT green as of this writing, and it is not this issue's
doing.** Measured twice, thirty minutes apart:

```console
$ cd adapters/python && uv run pytest tests/ -q
1 failed, 1698 passed, 5 skipped in 125.40s
FAILED tests/test_the_headline_test_count_is_the_count.py::
       test_the_headline_test_count_on_the_front_page_is_the_number_the_suites_run
E       AssertionError: README.md quotes a test count the repository does not have:
E           adapter: README.md says 1693, pytest collected 1704
```

The failure names **only the adapter half**; the Rust half it recomputes is 896
and it does not complain about it. The collected adapter count also **moved
between my two runs** — 1703 in the first, 1704 in the second — which is a
concurrent session adding Python tests while this was being measured. The README
line is therefore not this issue's number to set, and it was left alone: editing
a counter another session is still moving would race with them and could lose
their work. The `896` this issue is responsible for is correct.

An earlier round in this same repair recorded two counters that this change did
legitimately move, both caught by the repository's own truth-holding tests rather
than by anybody noticing:

* `test_the_named_field_count_is_the_number_of_fields_that_resolve_a_name` —
  `grep -cE '^\s*names:' spec/schema.yaml` went 26 → 27 when
  `catalog.default` gained its line; `site-docs/concepts/what.md:132` and
  `site-docs/status/verified.md:22` say **27** today, re-checked above.
* `test_the_headline_test_count_on_the_front_page_is_the_number_the_suites_run` —
  the Rust half went 888 → 896 for the eight tests this round added.

No test was weakened, skipped or deleted at any point.

---

## Register update

**There is no row for this defect in `docs/70-PRODUCTION-GAP-REGISTER.md`, and
that is measured, not assumed.**
`grep -n "allow-egress\|leaves-the-box\|egress" docs/70-PRODUCTION-GAP-REGISTER.md`
returns four lines, none of them about the boundary check: one about a
locally-served transport (`:309`), one about a mode that needs nothing off this
machine (`:277`), one inside the long C5 row, and one at `:479`. The air-gap
promise is enforced by a rule the register never named.

**The line to correct is `docs/70-PRODUCTION-GAP-REGISTER.md:282`** — the
paragraph beginning *"**`model-for-checking:`** is honoured for stages whose
`does` is `check-its-work`…"*. That paragraph is about the **run**, and it is
accurate about the run. What it leaves the reader with is the impression that
`model-for-checking:` is a closed subject, while at check time the field was
outside `allow-egress:` altogether. **Applied**, as one additional paragraph
immediately after it, in the same style as the A1 and D3 amendments: nothing
already on that page was reworded or deleted, because the page is being edited by
other sessions and an amendment that rewrites what it found is
indistinguishable from one that loses it.

**The row this closes is in the other register**, and it is already there and
already correct: `docs/remediation/REGISTER.md:110`, *"every field that binds a
model is held to `allow-egress:`"*, naming
`crates/pact-cli/tests/every_model_a_document_names_is_held_to_the_boundary.rs`.
Its claim is now **wider than when it was written** — six fields rather than
five, and the recording half of the boundary as well as the words half — and the
test named on it is the one that holds both. The row's wording still describes
what the file does, so it is left as it stands and this document is what a reader
follows for the argument.

**No new rule id was minted, and none is owed.** Every refusal this round adds
comes out as `loader/leaves-the-box` or `schema/no-such-name`, both pre-existing.
`grep -rln "leaves-the-box"` over `crates/pact-cli/tests/` and
`adapters/python/tests/` finds three files — the two boundary tests and
`test_priced_rows_beyond_one_vendor.py` — and none of them needed a new row.

**A class row is warranted and is not written.** The class this issue names —
*a decision table written in one language while the specification declares the
same table in another* — has now cost this repository three separate rounds
(`bindings`' four paths, `role_words`' constant, and `catalog.default`'s missing
`names:`). A register row for the class, with an inventory of every remaining
hand-written table in `crates/pact-cli/src/`, would be worth more than any of the
three individual fixes. Minting one is a structural change to a page three other
sessions are editing concurrently, so it is named here and not written there.

---

## What remains open

* **`evals.graded-by` in a suite whose `population:` is `promoted-traces` or
  `sampled-frame`.** Those cases really can hold a recording of a customer, and
  the judge grading them is outside the audio envelope by the decision recorded
  above. Closing it precisely means reading the suite's `population:` and
  resolving `agent.evals` — which is a `names: pact:evals` namespace rather than
  a workspace collection, so the edge the envelope walk follows does not reach
  it. Stated here and in `egress::envelope`'s doc-comment, and held in its
  current shape by `an_eval_judge_is_not_in_an_agents_audio_envelope`, so it is a
  decision somebody can reverse rather than a silence they have to discover.
* **`learning-model.model` and audio.** A reflector reading traces from a voice
  agent is the same question at workspace scope, where no agent's `accepts:` line
  can be quoted. Same disposition.
* **`catalogue_default()` in `crates/pact-cli/src/main.rs:1111` reads only
  `BUILTIN_CATALOGUE`.** That is correct for its one job — choosing a
  locally-served id to OFFER in a fix line — but the name does not say so, and a
  future caller wanting "what this workspace actually binds" would get the wrong
  answer. Not touched here; it is not a boundary hole, because the workspace copy
  is now held by the schema.
* **There is no `vision` role**, so pictures cross under `llm` with nothing extra
  asked. Unchanged by this round, and stated in the module header: this file
  enforces the list the schema declares and invents no choice of its own.
* **Six of the twenty-seven failure cases are UNCOVERED**, listed as such in
  [Failure cases](#failure-cases). Three are behaviours that are correct today
  and held by nothing: two hosted bindings on one agent drawing two refusals, a
  model id in no catalogue being a typo rather than a boundary crossing, and a
  model binding written as a list on `agent.model` rather than on `graded-by:`.
  Each is one fixture away from being held, and none of them is a defect — only
  an unheld claim.
* **`bindings`' alias branch is unreachable and ungated.**
  `std::iter::once(&f.name).chain(f.aliases.iter())` at `egress.rs:367` cannot
  fire, because `aliases:` left the native authoring path (X1) and
  `Field::aliases` is empty for every field the loader builds. It is forward
  compatibility with no test and no reader; deleting it or writing a spec-driven
  case for it are both defensible, and doing neither is what this round did.
* **The README's adapter test count is stale and is not this issue's to set.**
  `uv run pytest tests/ -q` fails
  `test_the_headline_test_count_on_the_front_page_is_the_number_the_suites_run`
  with *"adapter: README.md says 1693, pytest collected 1704"*. The Rust half
  (896) is correct and is the half this issue moved. The adapter figure moved
  while this document was being measured — 1703 on one run, 1704 thirty minutes
  later — because another session is adding Python tests, so setting it here
  would be writing a number that is wrong before the file is saved. It belongs
  to whoever lands those tests. Recorded rather than quietly left out, because
  "the full gate is green" is a claim this document would otherwise be making
  falsely.
