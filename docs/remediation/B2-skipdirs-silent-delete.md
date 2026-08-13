# B2 — an entry the loader skipped because of its NAME left no trace, and the first repair fixed folders, missed prose, invented a noise regression, and hardened the one silent deletion that was left

**Severity: high** · **Status: fixed, then found wrong in six directions and
re-fixed; the re-fix was re-measured and four mutations re-performed in a second,
adversarial pass, which confirmed it and left one sibling silent loss OPEN** ·
**Queue row: `docs/remediation/QUEUE.md` #12 — `done`. No row in
`docs/70-PRODUCTION-GAP-REGISTER.md`; one correction is owed to its lines 31–33.
See [Register update](#register-update).**

`Policy::is_ignored` refused to descend into six directory names and to read
seven documentation filename stems, and its one production caller answered every
one of those refusals with a bare `continue`. So an author who wrote
`agents/build/agent.yaml` lost the whole agent, and `pact check` said the
workspace loaded **cleanly**. Thesis T7 — *no silent loss anywhere* — with a
green tick over it.

**The first repair closed that, and left four things wrong and two things worse.**

* It made the six folder names speak — including `node_modules`, `__pycache__`
  and `venv`, which no author ever types. Any third-party workspace where
  somebody had run `npm install`, `cargo build` or `python -m venv venv` newly
  failed `--deny-warnings` at exit 1, with advice ("rename it to something
  else") that is meaningless for the first and destroys the third. This
  repository's own Python adapter printed five such lines.
* It drew the loud/silent line for FILES at the **extension**, so a
  documentation stem written as prose stayed silent at every depth.
  `agents/keeper/handover/notice.md` — a file somebody wrote, in a folder of
  settings — took no part in the document and produced no diagnostic. That is B2
  verbatim, one file-kind over, and the fix's own stated criterion demands the
  opposite.
* It put the new warning **beside** the false error it was supposed to replace,
  not instead of it, so `tools/license.yaml` under an agent's `uses:` now
  produced two messages and the first one still read *"Add a file
  `tools/license.yaml`"* — of the file the author had open.
* It advertised `.pactignore` as the remedy, and `.pactignore` did not inherit,
  so for the names guaranteed to recur the escape hatch cost one file per
  occurrence.
* It left `pact show`, `pact discover` and `pact card` silent. `discover` is the
  one that matters: it hands `gaia-ai-runtime` an inventory missing an agent, at
  exit 0, with empty stderr.
* It **hardened, pinned and advertised** the loader's one remaining silent
  deletion. `.pactignore` was moved to the front of the loop, made the remedy
  printed under the new warning, and given the first test in this repository
  that *requires* its silence — while EXP-10 names that path verbatim as "the
  project's own canonical objective-hack".

Everything below was measured on this machine against this working tree, in two
passes: the pass that made the repair, and a later pass asked to attack it. The
second pass re-ran the whole gate, re-performed four of the eight mutations, and
re-derived the failure cases from scratch. It confirmed the repair and found
**four corrections**, all applied above and each marked where it appears:

* a live silent loss the document did not record — a filename that is not valid
  UTF-8 — which falsified the loader test file's own headline claim. Recorded in
  [What remains open](#what-remains-open) and **not fixed**;
* a seam count quoted from before this issue added unit tests (15 → **19**);
* a stderr byte count that is a function of the tester's directory, replaced
  with the claim the test actually makes;
* `Ignore::load` and `Ignore::matches` described with their reasons swapped.

---

### How to read the numbers

Three states are distinguished and never mixed:

* **before** — the loader as it stood before B2. Reproduced by applying one
  named mutation (below) to a **copy** of `crates/`, `spec/` and `models/` under
  the scratchpad, building with a private `CARGO_TARGET_DIR`, and running that
  binary. The shared `target/` was never used for a mutated build.
* **as landed** — the state this issue was handed to me in. Measured two ways:
  with the repository's own `target/debug/pact` before I rebuilt it, and (for
  the CHK-12 case) by reverting only my own change in the isolated copy.
* **now** — this working tree. `target/debug/pact`, built from the sources whose
  md5s are in [Verification](#verification).

**Another session was writing this repository throughout.** Only the files this
issue needs were touched, nothing was stashed, and every mutation was reverted
by restoring a byte-copy taken before it was applied.

The mutation used for **before** is: in `Loader::classify`
(`crates/pact-loader/src/lib.rs`), replace the whole `match reason` with
`continue`; replace the `.pactignore` note with `continue`; return
`Ignored::Documentation` for a prose documentation stem at every depth; put
`node_modules`, `__pycache__` and `venv` back on the speaking list; restore
`Ignore::load(dir)` in place of `Ignore::inherited`; restore
`matches!(name.as_str(), "target" | "node_modules")` in `discover.rs`; drop the
stderr routing in `show` and `discover`; drop the `UNLOADED` guard in
`reach.rs`.

---

## What is wrong

### 1. The original reproduction — a whole agent, gone, at exit 0

A two-agent workspace: `agents/keeper/agent.yaml` and `agents/build/agent.yaml`,
nothing else.

```text
$ pact check <ws>/repro
OK — <ws>/repro loaded cleanly (8 settings).
EXIT=0
```

```text
$ pact show <ws>/repro          # before
agents: ['keeper']
stderr: 0 bytes

$ pact discover <ws>/repro      # before
agents: ['pact:keeper']
digest: sha256:57dd7eee663579cc07604228f1b1a7bb3150a103945b511af41899563a46c2cd
stderr: 0 bytes
```

The second agent is not renamed, not reported, not mentioned. `discover` even
publishes a `workspace-digest` computed over a document it is missing from, and
`gaia-ai-runtime` is specified to index exactly that.

### 2. The narrower half — told to write the file you are looking at

`tools/license.yaml` holding `description: Prints the licence terms.`, and an
agent whose `uses:` names `license`:

```text
$ pact check <ws>/lic           # before
error: 'uses' names 'license', and there is no such entry in `tools:`, `skills:` or `knowledge:`.
  --> <ws>/lic/agents/keeper/agent.yaml:5:5
  |
5 |   - license
  |     ^^^^^^^
  fix: Nothing is declared there yet. Add a file `tools/license.yaml`, `skills/license/SKILL.md` or `knowledge/license.yaml`.
  rule: schema/no-such-name
1 problem(s) found in <ws>/lic. Nothing was run.
```

The one message the author gets tells them to create a file that is open in
front of them, because the loader discarded it without a word.

### 3. What the first repair left, and what it broke

| | as landed | why it is wrong |
|---|---|---|
| `pact check adapters/python` | **5** × `loader/folder-skipped-by-name`, all `__pycache__` | no author typed any of them; the line can never rescue anything |
| a workspace with `venv/` + one `__pycache__/` | 2 warnings, `--deny-warnings` **EXIT=1** | `python -m venv venv` is `python -m venv .venv` with the other conventional argument, and `.venv` was deliberately made silent for exactly this reason |
| four sibling `.md` files in `agents/keeper/settings/` | 1 message (about the non-doc one), 3 silent | `notice.md`, `changelog.md`, `contributing.md` gone with no diagnostic and no trace in `pact show` |
| `tools/license.yaml` under `uses:` | `error:` *"Add a file `tools/license.yaml`"* **first**, warning second | CHK-12 — one mistake, one message — broken by the same mechanism CHK-12 describes |
| one `.pactignore` line at the top of a workspace, 3 nested `dist/` | 1 silenced, **2 still warned** | the advertised escape hatch costs one file per occurrence |
| `pact show` / `discover` / `card` on the repro tree | stderr **0 bytes**, exit 0 | the runtime-facing hole is exactly the original bug |
| `agents/.pactignore` holding `ghost` | `OK — <ws> loaded cleanly (8 settings).` EXIT=0, agent absent from `pact show` | EXP-10's "deletion operator the blast-radius classifier cannot see", now with a test requiring the silence |
| `pact discover` on six workspaces, one per skipped name | `"WS-__pycache__" "WS-build" "WS-dist" "WS-packages" "WS-venv"` | one binary, two lists, opposite answers about the same folders |

---

## Root cause

Two causes, and they are the same shape.

**(a) `Option<bool>` where a reason was needed.** `Policy::is_ignored` answered
`bool`, and `Loader::classify` answered it with `continue`. Four different
questions — *is this a dotfile*, *is this a build folder*, *is this a readme*,
*is this a setting that looks like a readme* — arrived at one call site as one
bit, and the only decision available was "skip". Skipping is right for all four.
**Saying nothing** is right for two of them.

The first repair turned the bit into `enum Ignored` with four variants, which is
the right move, and then drew the loud/silent line in the wrong place twice:

* for folders, by putting the whole `SKIP_DIRS` list on the loud side, when the
  docstring's own stated criterion — *"every name here is also an ordinary
  English word somebody might have meant"* — is false of `node_modules` and
  `__pycache__` (`crates/pact-loader/src/policy.rs`, the old `SKIP_DIRS`
  comment);
* for files, by making the **extension** the whole test, which is a proxy for
  *"is this documentation"* that holds **only at a workspace root**. `README.md`
  at the top of a project is documentation on any reading; `README.md` inside
  `agents/keeper/` is a name collision of exactly the kind `agents/build/` is.

**(b) Every list was written twice.** `discover::walk` carried its own
`matches!(name.as_str(), "target" | "node_modules")` — two names against the
loader's six — outside the policy module that invariant F-1 and AC-7.2 reserve
for capability-affecting literals. Nothing made the two agree, and nothing could
notice they did not, because every tree the tests build uses a name both sides
already know.

**Why the second-order failures happened.** The repair reasoned about *the
folder case*, measured *the folder case*, and generalised. The `UNLOADED`
placeholder was rejected on one measurement — a `dist/` folder at the workspace
**root** becomes `error: 'dist' is not something a workspace can have` — and the
rejection was then applied to a *file* inside `tools:`, where the enclosing map
is open and the same measurement does not hold. The prose/structured line was
drawn from one example (`license.yaml`) and applied to a stem in a folder that
example never visited.

---

## Why nothing caught it

Four blind spots, each measured.

**1. The suite had silence controls for files and for dotfiles, and none for a
folder.** `a_readme_is_still_skipped_without_a_word` and
`a_dotfile_is_still_skipped_without_a_word` existed; nothing asserted that a
workspace merely *containing* tool output stays clean. Applying the repair
(making `node_modules`/`__pycache__` silent) turned
`every_name_a_tool_claims_is_reported_not_deleted` **red**, so the test suite
did not merely miss the noise regression — it **forbade the repair**.

**2. The shipped-examples gate is structurally blind to it.**

```text
$ find examples -type d \( -name __pycache__ -o -name node_modules -o -name target \
      -o -name venv -o -name dist -o -name build \) | wc -l
0
```

`the_examples_stay_clean_under_deny_warnings.rs` cannot measure a name no
example tree contains.

**3. The prose control over-generalised.** `a_readme_is_still_skipped_without_a_word`
placed `agents/keeper/LICENSE` alongside four root-level files, so it asserted
"a documentation stem is silent **everywhere**" while reading as "a project's
README is silent". The design then generalised the first from the second.

**4. The CLI test could not see the wording at all.** `said(&out)` is the
*rendered* diagnostic, and a rendered diagnostic carries an `--> <path>:1:1`
arrow line under its sentence, so `said.contains("agents/build")` is answered by
the ARROW whatever the sentence says. Measured, with the folder message replaced
by `"'{dir}' had something skipped, because some folders normally hold files a
tool wrote rather than anything you did."`:

```text
$ cargo test -p pact-cli --test a_folder_the_checker_skips_is_named_on_the_way_past
test result: ok. 3 passed; 0 failed;      # all three green under the mutation
```

That fact was stated in the analysis prose and **not** recorded in the CLI test's
own docstring, which is where the mutation protocol requires it.

---

## The fix

Six changes. Each names the finding it answers.

### F1 — one criterion for a FOLDER: *could an author have meant this name?*

`crates/pact-loader/src/policy.rs`. The old `SKIP_DIRS` is split, and the split
is the criterion the docstring already claimed:

```rust
pub const SPEAKING_SKIP_DIRS: &[&str] = &["dist", "build", "target"];
pub const TOOL_ONLY_DIRS:     &[&str] = &["node_modules", "__pycache__", "venv"];
```

`Ignored::ToolArtifact` is the new, **silent** variant. The warning is only
defensible where a real setting could be behind the name; behind `__pycache__`
there never is one, so the line can only ever be noise.

`target` stays on the speaking side deliberately, and it is the one judgement
call here. It is an ordinary English noun — an author can write a skill about
picking a target — so silence there would be a new silent loss, which is the
whole thing this issue is about. `venv` is not a word, and `python -m venv venv`
is the same command whose dotted form the policy module already argues must stay
silent.

### F2 — one criterion for a FILE: name **and place**

`Policy::is_ignored` gains one bit, `at_workspace_root`, and one variant,
`Ignored::DocumentationInsideTheTree`:

| | at the top of the workspace | anywhere below |
|---|---|---|
| `license.yaml`, `notice.json` | speaks | speaks |
| `README.md`, `LICENSE`, `notice.txt` | **silent** | **speaks** |
| `escalation.md` | loads | loads |

Still a pure function — nothing touches the filesystem, so the answer is the
same on every machine and the digest stays reproducible. The bit is computed in
`Loader::classify` as
`dir.as_str().trim_end_matches('/') == self.root.as_str().trim_end_matches('/')`;
the trailing slash is trimmed because this repository's own gate loop passes
`examples/patterns/*/`.

### F3 — CHK-12: the skipped file contributes its NAME

A `Candidate` gains `name_only: bool`. For
`Ignored::SettingsNamedLikeDocumentation` **below the root**, `classify` pushes a
candidate that `load_dir` turns into the `pact_doc::UNLOADED` placeholder an
unreadable file already becomes, without opening it. The reference resolves,
`schema/no-such-name` stops firing, and the warning is the one message.

Two scoping conditions, both measured rather than assumed:

* **not at the root** — a workspace's own fields are a closed set, so a
  placeholder there is a guaranteed `'license' is not something a workspace can
  have`. That is the same trade the folder rule refuses.
* **structured only** — a placeholder buys something only where a name is
  referenced, and `uses:`/`policy:` name tools, skills, knowledge and policies,
  all written as structured documents. With the placeholder also inserted for
  prose, the four-file fixture printed a warning **and** `error: 'changelog' is
  not something settings can have` per file — CHK-12 broken by the repair for
  CHK-12. Measured; see [Failure cases](#failure-cases) case 7.

`reach::check` (`crates/pact-loader/src/reach.rs`) gains the `UNLOADED` guard
`ports::check` already had. That was a **pre-existing** CHK-12 gap, measured on a
workspace whose only mistake is one unclosed bracket, and it had to be closed for
F3 to deliver one message rather than two.

### F4 — `.pactignore` inherits, and says what it removed

`Ignore` now carries `Pattern { text, from }` and gains:

* `Ignore::inherited(root, dir)` — every `.pactignore` from `root` down to `dir`,
  outermost first, so the line a reader is sent to is the one they would delete;
* `Ignore::matching(name) -> Option<&Pattern>` — which line answered, and where
  it was written.

A match is no longer a bare `continue`. It emits
`loader/ignored-on-purpose` at **`Severity::Note`** (new constructor
`Diagnostic::note`), naming the entry, the pattern and the file the pattern is
in:

```text
note: '<ws>/agents/ghost' takes no part in this workspace, because 'agents/.pactignore' has a line saying 'ghost'.
  fix: Nothing to do — that line is what leaves it out. To bring it back, take 'ghost' out of 'agents/.pactignore'.
```

A note rather than a warning because `--deny-warnings` counts warnings: an
intended suppression must be **visible** without being a gate failure. This
meets EXP-11 and FR-8.1.1 (*no lossy operation proceeds silently*). It does
**not** fully meet EXP-10 — see [What remains open](#what-remains-open).

### F5 — `show`, `discover` and `card` speak on stderr

All three gated their rendering on `diags.has_errors()`. They now sort and print
warnings and notes to **stderr**, leaving stdout exactly the JSON it was.

### F6 — one list, in the policy module

`discover::walk` takes a `&Policy` and asks `policy.is_ignored(&name, true, false)`.
The hardcoded `matches!` is gone, and F-1 holds again.

---

## Alternatives rejected

**Make `venv` silent by looking for `pyvenv.cfg` inside it.** Rejected:
`is_ignored`'s docstring promises a pure function of the name, and the whole
reason is that the digest must be reproducible on every machine. A
filesystem-dependent skip makes the document depend on what a tool happened to
leave behind.

**Drop `target` from the speaking list too** (as one reviewer suggested).
Rejected: `target` is an ordinary English noun, so silence there is a new silent
loss of exactly the kind this issue exists to close. The cost of keeping it loud
is one line on a Rust repository that is itself a PACT workspace root; the cost
of silencing it is an agent nobody hears about.

**Warn about a documentation stem below the root only inside "known" folders
(`agents/`, `skills/`, …).** Rejected: that is a second slot table, which is the
thing the Expansion Rule exists not to have. *Below the root* is one rule an
author can hold in their head.

**Insert the `UNLOADED` placeholder for every skipped file.** Measured and
rejected — it turns one warning into a warning plus an unknown-field error for
prose, and into an error at the workspace root for structured. See case 7 and
case 8.

**Make `.pactignore` suppression a warning.** Rejected: the author asked for it,
and a `--deny-warnings` gate nobody can pass is what made the payload-folder
asymmetry a bug in the first place.

**Keep `.pactignore` per-directory and only reword the `fix:`.** Rejected once
`README.md` below the root started speaking: the one-line answer has to be
one line, or the remedy is worse than the rule.

---

## Blast radius

**Loader.** `Policy::is_ignored` changes signature (one added `bool`). Callers:
`Loader::classify` and, now, `discover::walk`.

`Ignore::load` and `Ignore::matches` both survive the change, and an earlier
draft of this section had their reasons the wrong way round. Measured:

```text
$ grep -rn "Ignore::load" --include=*.rs crates/
crates/pact-loader/tests/an_agent_…_never_silently_gone.rs:761:    // … `Ignore::load` read the
```

One hit, and it is a comment — so `Ignore::load` has no caller *by that name*.
It is not dead: `Ignore::inherited` is built out of it (`policy.rs:857-862`
calls `Self::load` once for the root and once per path component), which is the
whole reason the per-directory reader was kept rather than inlined.
`Ignore::matches` is the opposite case — production calls `matching`, and
`matches` is a one-line wrapper (`policy.rs:887-889`) whose only callers are the
five assertions in `policy::ignore_tests`. A `pub` wrapper reached only from
tests is a mild instance of this register's Class A shape; it is recorded rather
than removed, because it is one line over the function that does the work and
deleting it would be churn in a file a concurrent session was editing.

**Documents that change.** A tree gains settings where it previously lost them
only in one case: a structured documentation-stem file below the root now
contributes its key as an `UNLOADED` placeholder. Nothing else changes what
loads. Trees with a `.pactignore` gain notes; trees with `node_modules`,
`__pycache__` or `venv` lose warnings; trees with a documentation stem below the
root gain one.

**Digest.** `workspace-digest` moves for the one document change above
(a `tools/license.yaml`-shaped file below the root). Every other tree digests
identically. All ten shipped examples load with the same settings count as
before — `refund-desk` 498, `mcp-desk` 46, `answers-from-documents` 21, and the
eight patterns 49/30/24/24/30/25/29/27 — all at exit 0 under `--deny-warnings`.

**`.pactignore` inheritance is the widest change** and the one to watch: a
pattern at the top of a workspace now removes matching entries from the whole
subtree, including from payload folders. No shipped example has a `.pactignore`
(`find examples -name .pactignore` → nothing), so nothing in this repository
moves. An embedder with a per-directory `.pactignore` will see more entries
suppressed — and every one of them now produces a note naming the line, which is
how they will find out.

**CLI.** `show`, `discover` and `card` write to stderr where they wrote nothing.
stdout is byte-identical, and `a_runtime_is_told_what_the_checker_was_told`
asserts the JSON still parses.

---

## The test

Two files, and the division of labour between them is the point.

**`crates/pact-loader/tests/an_agent_in_a_folder_named_build_is_never_silently_gone.rs`**
— eleven tests, asserting on `d.message` with the workspace path removed
(`Tree::tidy`), which is the only level at which the SENTENCE can be checked.

| test | claim |
|---|---|
| `a_folder_a_tool_would_have_named_is_not_just_deleted` | the reproduction, as an effect on the document |
| `every_name_a_tool_claims_is_reported_not_deleted` | every name on `SPEAKING_SKIP_DIRS`, read from the list itself |
| `it_speaks_at_any_depth` | three levels down |
| `a_setting_named_like_a_readme_is_not_just_deleted` | `tools/license.yaml`; `.pactignore` in the fix; the name resolves |
| `writing_inside_the_tree_is_not_just_deleted` | **new** — four sibling `.md` files, one control that must load and three doc stems that must each be named |
| `a_folder_only_a_tool_ever_makes_is_skipped_without_a_word` | **new** — the missing silence control, folder-level |
| `a_readme_is_still_skipped_without_a_word` | **narrowed** to root-level placements, which is all it ever justified |
| `a_dotfile_is_still_skipped_without_a_word` | unchanged |
| `saying_you_meant_it_stops_the_warning_and_does_not_double_report` | **changed** — asserts the two skip rules are absent and nothing above a note is said, instead of `is_empty()` |
| `a_line_the_author_wrote_is_a_deletion_and_says_so` | **new** — EXP-10: the entry AND the pattern |
| `one_line_at_the_top_answers_for_the_whole_tree` | **new** — inheritance, and that inheriting does not cost the record |

**`crates/pact-cli/tests/a_folder_the_checker_skips_is_named_on_the_way_past.rs`**
— six tests through the real binary.

| test | claim |
|---|---|
| `check_does_not_call_a_workspace_clean_when_it_dropped_an_agent` | the word *cleanly* is gone, the rule id is printed |
| `the_gate_this_repository_runs_can_see_a_lost_agent` | `--deny-warnings` EXIT=1; no doubled separator with a trailing-slash argument |
| `a_tool_written_as_license_yaml_is_not_answered_with_write_the_file_you_wrote` | **now earns its name**: `assert!(!said.contains("Add a file"))` |
| `the_warning_line_itself_names_the_folder` | **new** — reads the `warning:` line alone, so the arrow cannot answer for the sentence |
| `a_runtime_is_told_what_the_checker_was_told` | **new** — `discover` stderr names the folder; stdout still parses as JSON at exit 0 |
| `one_binary_gives_one_answer_about_which_folders_it_skips` | **new** — six workspaces under six skipped names, none discovered; a seventh under `packages/` as the control |

Two controls are written out rather than read from the list they control:
`MADE_BY_A_TOOL` in `a_folder_only_a_tool_ever_makes_is_skipped_without_a_word`,
and the `hidden` array in `one_binary_gives_one_answer_about_which_folders_it_skips`.
That is not duplication for its own sake — see mutation 3.

---

## The mutation

Every mutation below was applied to the source, the scoped test was run, and the
source restored from a byte-copy taken beforehand.

**Four of the eight were re-performed independently in a later pass**, by
copying `crates/`, `spec/`, `examples/`, `models/` and `tests/` to a scratchpad
directory, building with a private `CARGO_TARGET_DIR`, and mutating only there —
so the shared tree and any concurrent session were untouched. Mutations **1, 2, 3
and 8 reproduced the results below exactly**, name for name and count for count.
Restoration was checked with `diff -q` against the real files rather than
assumed, and the copy re-ran `11 passed` afterwards. Mutations **4, 5, 6 and 7
were not re-performed** in that pass; they stand as the first pass measured them
and are marked below. Before any of it, the six changed sources were confirmed
byte-unchanged since this document was written — the `md5sum` values in
[Verification](#verification) still match — so both passes measured one tree.

**1 — the diagnostic.** Replace the whole `match reason` in `Loader::classify`
with `continue`.

```text
$ cargo test -p pact-loader --test an_agent_in_a_folder_named_build_is_never_silently_gone
test result: FAILED. 6 passed; 5 failed;
  a_setting_named_like_a_readme_is_not_just_deleted
  every_name_a_tool_claims_is_reported_not_deleted
  a_folder_a_tool_would_have_named_is_not_just_deleted
  it_speaks_at_any_depth
  writing_inside_the_tree_is_not_just_deleted

$ cargo test -p pact-cli --test a_folder_the_checker_skips_is_named_on_the_way_past
test result: FAILED. 1 passed; 5 failed;
```

**2 — the wording.** Replace the folder sentence with `"'{dir}' had something
skipped, because some folders normally hold files a tool wrote rather than
anything you did."` — same rule, same span, no name.

```text
$ cargo test -p pact-cli --test a_folder_the_checker_skips_is_named_on_the_way_past
test result: FAILED. 5 passed; 1 failed;
  the_warning_line_itself_names_the_folder
```

The five that pass are the point: three of them are the tests that shipped with
B2, and the arrow line answers their path assertion. This is now recorded in
that file's own module doc, which is where it belongs.

**3 — the split.** Move `node_modules`, `__pycache__` and `venv` back onto
`SPEAKING_SKIP_DIRS` and empty `TOOL_ONLY_DIRS`.

```text
$ cargo test -p pact-loader --test an_agent_in_a_folder_named_build_is_never_silently_gone
test result: FAILED. 10 passed; 1 failed;
  a_folder_only_a_tool_ever_makes_is_skipped_without_a_word
$ cargo test -p pact-loader --lib
test result: FAILED. 201 passed; 3 failed;
  policy::tests::a_name_only_a_tool_writes_is_told_apart_from_a_name_a_person_might_write
  policy::tests::documentation_files_are_not_fields
  policy::tests::no_folder_this_list_skips_is_one_the_dot_rule_answers_first
```

**This mutation is why the control's list is written out.** With the loop reading
`TOOL_ONLY_DIRS`, the mutation empties the list, the loop runs zero times, and
the test passes having built nothing and asserted nothing. A control that reads
the thing it is controlling is not a control.

Re-confirmed independently, by editing the copy's test to drive its loop from
`TOOL_ONLY_DIRS` (and dropping the growth check) with mutation 3 still applied:

```text
test a_folder_only_a_tool_ever_makes_is_skipped_without_a_word ... ok
test result: ok. 1 passed; 0 failed; 10 filtered out
```

Green, over an empty list, having created no folder and read no diagnostic. The
guard that makes the written-out list safe is the second loop in that test —
every name in `TOOL_ONLY_DIRS` must appear in `MADE_BY_A_TOOL` — so a seventh
silent name cannot be added without the control being told.

**4 — the place** *(first pass only; not re-run independently)*. Return `Ignored::Documentation` for a prose documentation stem
at every depth.

```text
test result: FAILED. 10 passed; 1 failed;
  writing_inside_the_tree_is_not_just_deleted
```

`a_readme_is_still_skipped_without_a_word` stays green, which is what makes the
narrowing meaningful: it now places its files only where a project's own writing
actually lives.

**5 — the suppression record** *(first pass only; not re-run independently)*. Restore the bare `continue` on a `.pactignore`
match.

```text
test result: FAILED. 9 passed; 2 failed;
  a_line_the_author_wrote_is_a_deletion_and_says_so
  one_line_at_the_top_answers_for_the_whole_tree
```

**6 — inheritance alone** *(first pass only; not re-run independently)*. `Ignore::load(dir)` in place of
`Ignore::inherited(&self.root, dir)`.

```text
test result: FAILED. 10 passed; 1 failed;
  one_line_at_the_top_answers_for_the_whole_tree
```

Through the binary, on a workspace with `dist/` at three depths and one
`.pactignore` line at the top:

```text
per-directory: 2 × warning (agents/keeper/dist, agents/keeper/tools/shipper/dist)
inherited:     0 × warning, 3 × note
```

**7 — the placeholder** *(first pass only; not re-run independently)*. Replace the guard
`if !at_root && reason == Ignored::SettingsNamedLikeDocumentation` with
`if false`.

```text
$ cargo test -p pact-cli --test a_folder_the_checker_skips_is_named_on_the_way_past
test result: FAILED. 5 passed; 1 failed;
  a_tool_written_as_license_yaml_is_not_answered_with_write_the_file_you_wrote
$ cargo test -p pact-loader --test an_agent_in_a_folder_named_build_is_never_silently_gone
test result: FAILED. 10 passed; 1 failed;
```

**8 — the second list.** Restore
`matches!(name.as_str(), "target" | "node_modules")` in `discover.rs`.

```text
test result: FAILED. 5 passed; 1 failed;
  one_binary_gives_one_answer_about_which_folders_it_skips
```

---

## Failure cases

Every one of these was run. `<ws>` stands in for the scratchpad path.

**Case 1 — the original reproduction.** `agents/build/` + `agents/keeper/`.

| | before | as landed | now |
|---|---|---|---|
| `pact check` | `loaded cleanly (8 settings)`, EXIT=0 | warning, `loaded with 1 warning(s)` | same |
| `pact show` stderr | 0 bytes | 0 bytes | **non-empty**, names `agents/build` |
| `pact discover` stderr | 0 bytes | 0 bytes | **non-empty**, same warning |
| `pact discover` stdout | 1 agent | 1 agent | 1 agent, still valid JSON, EXIT=0 |

The stderr figure is deliberately not a byte count: the message interpolates the
workspace path, so the count is a function of where the fixture happens to sit.
Re-measured in a second pass from a different scratchpad directory it was 676
bytes rather than the 678 first recorded — the same message, a shorter path. A
number that moves with the tester is not a measurement, so what is asserted is
what the test asserts: non-empty, and naming the folder.

**Case 2 — this repository's own Python adapter.**

```text
before / as landed:  5 × loader/folder-skipped-by-name   (all __pycache__)
now:                 0 × loader/folder-skipped-by-name
                     1 × loader/file-skipped-by-name     (experiments/README.md, below the root)
```

The one remaining line is the new rule working: a `README.md` three folders down
in a tree that is not a workspace. It is a warning, it names the file, and one
`.pactignore` line at the top answers it.

**Case 3 — `python -m venv venv` plus one import.** A workspace with `venv/`
holding `pyvenv.cfg` and one `__pycache__/`.

```text
as landed:  warning ×2, `pact check --deny-warnings` EXIT=1
now:        OK — <ws>/venvws loaded cleanly (8 settings).  EXIT=0
```

**Case 4 — four sibling `.md` files in one ordinary folder.**
`agents/keeper/handover/{escalation,notice,changelog,contributing}.md`, all
identical in shape.

```text
as landed:  escalation.md became a field and was named by the checker.
            notice.md, changelog.md, contributing.md — no error, no warning, no
            mention; `pact show | grep -E "notice|changelog|contributing"` → (none)
now:        3 × loader/file-skipped-by-name, one per file, each naming the file
            and offering .pactignore and "move it to the top of the workspace"
```

**Case 5 — `README.md` at the top of a workspace.** All ten shipped examples,
including `examples/refund-desk/README.md`, load **cleanly** at exit 0 under
`--deny-warnings`, with and without a trailing slash on the argument.

**Case 6 — `tools/license.yaml` named by `uses:`.**

```text
before:     error "Add a file `tools/license.yaml`"        (1 message, false)
as landed:  error "Add a file …" FIRST, warning second     (2 messages, first still false)
now:        warning: '<ws>/lic/tools/license.yaml' was skipped …
            OK — <ws>/lic loaded with 1 warning(s).        (1 message, true)
            `grep -c "Add a file"` → 0
```

**Case 7 — the placeholder inserted for prose (rejected).** With `name_only` set
for `Ignored::DocumentationInsideTheTree` as well:

```text
warning: '…/settings/changelog.md' was skipped, because a file called 'changelog' …
error: 'changelog' is not something settings can have.
  fix: Remove it, or use one of: max-tokens, thinking, temperature, …
```

Two messages per file, and the second sends the reader to remove a line that is
a filename. Scoped out.

**Case 8 — a structured documentation stem at the workspace root.**
`license.yaml` beside `workspace.yaml`:

```text
now: warning: '<ws>/rootlic/license.yaml' was skipped …
     OK — <ws>/rootlic loaded with 1 warning(s).
```

No placeholder, so no `'license' is not something a workspace can have`.

**Case 9 — an unparseable `tools/broken.yaml` under `uses: [broken]`** (a
**pre-existing** CHK-12 gap this pass closed):

```text
before / as landed:
  error: 'broken' does not say where it reaches: it has no `connect:`, no `url:` and no `says:`.
    fix: Add ONE line to this file …
  error: This file is not written correctly: while parsing a flow sequence, expected ',' or ']'
  2 problem(s) found.

now:
  error: This file is not written correctly: while parsing a flow sequence, expected ',' or ']'
  1 problem(s) found.
```

**Case 10 — `.pactignore` deletes an agent.** `agents/.pactignore` holding
`ghost`, beside `agents/ghost/agent.yaml` (`description: Does the payments.`):

```text
as landed:  OK — <ws>/ghost loaded cleanly (12 settings).   without the ignore file
            OK — <ws>/ghost loaded cleanly  (8 settings).   with it, EXIT=0,
                                                            no line naming anything
            pact show → agents: ['keeper']

now:        note: '<ws>/ghost/agents/ghost' takes no part in this workspace,
                  because 'agents/.pactignore' has a line saying 'ghost'.
            OK — <ws>/ghost loaded cleanly (8 settings).    EXIT=0 under --deny-warnings
```

**Case 11 — one `.pactignore` line for a whole tree.** `dist/` at three depths.

```text
per-directory rule:  1 silenced, 2 still warned
inherited:           0 warnings, 3 notes, each naming '.pactignore' and 'dist'
```

**Case 12 — one binary, one list.** Seven identical workspaces, one under each of
the six skipped names plus `packages/` as a control:

```text
before / as landed:  pact discover → "WS-__pycache__" "WS-build" "WS-dist" "WS-packages" "WS-venv"
now:                 pact discover → "WS-packages"
```

**Case 13 — a `.pactignore` inside an attachment folder.** Unchanged behaviour
(`a_pactignore_line_silences_a_shortcut_in_an_attachment_folder_as_it_does_anywhere_else`
still green); the suppression there now also produces a note, which that test
does not forbid because it asserts the absence of one rule rather than emptiness.

**Case 14 — a folder name that is not valid UTF-8. UNCOVERED, and still
silent.** `agents/caf\xe9-agent/agent.yaml` (Latin-1) beside `agents/keeper/`:

```text
now:  OK — <ws>/utf loaded cleanly (8 settings).   EXIT=0 under --deny-warnings
      pact show → keeper alone, stderr 0 bytes
```

No test in either file builds such a tree, and the loader's own `classify` drops
it before any rule in this document is consulted. See
[What remains open](#what-remains-open).

**Case 15 — a payload filename that is not valid UTF-8. UNCOVERED, and it moves
a digest.** `skills/helper/references/` holding `good.txt` and a Latin-1
`r\xe9sum\xe9.txt`:

```text
now:  OK — <ws>/pay loaded cleanly (14 settings).  EXIT=0
      "files": [ { "$file": "good.txt", … } ]      one entry, not two
```

The `files:` manifest is what `workspace-digest` covers, so this is the one case
in this document where a silent skip changes a promise the loader makes about
reproducibility rather than only what an author sees.

**Case 16 — a case-different folder name (`agents/Build/`). UNCOVERED, and
correct.** `SPEAKING_SKIP_DIRS.contains(&name)` is case-sensitive, so `Build/`
loads and nothing is lost:

```text
now:  OK — <ws>/case loaded cleanly (12 settings).  EXIT=0 under --deny-warnings
      pact show → both "Build" and "keeper"        (8 settings for the lowercase tree)
```

That is the safe direction — case sensitivity can only ever cause *fewer* silent
losses — but nothing pins it, so a later `to_ascii_lowercase()` added for
tidiness would start eating `Build/` agents and no test would object.

**Case 17 — the workspace's own root is named `build`. UNCOVERED, and correct.**
`classify` classifies a directory's children and never the root it was handed:

```text
now:  pact check <ws>/root/build --deny-warnings
      OK — … loaded cleanly (8 settings).   EXIT=0
```

Worth a test, because a runtime pointed at a checkout is quite likely to be
pointed at exactly such a directory.

---

## Verification

Run once, on this working tree, after the last mutation was reverted.

```text
$ cargo test --workspace
   … 91 × "test result: ok", 0 × FAILED across the whole workspace

$ cargo clippy --all-targets -- -D warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.98s

$ for d in examples/refund-desk examples/mcp-desk examples/answers-from-documents \
           examples/patterns/*/; do pact check "$d" --deny-warnings; done
0  examples/refund-desk               OK — loaded cleanly (498 settings).
0  examples/mcp-desk                  OK — loaded cleanly (46 settings).
0  examples/answers-from-documents    OK — loaded cleanly (21 settings).
0  examples/patterns/debate/          OK — loaded cleanly (49 settings).
0  examples/patterns/escalation/      OK — loaded cleanly (30 settings).
0  examples/patterns/first-answer/    OK — loaded cleanly (24 settings).
0  examples/patterns/pipeline/        OK — loaded cleanly (24 settings).
0  examples/patterns/quorum/          OK — loaded cleanly (30 settings).
0  examples/patterns/race/            OK — loaded cleanly (25 settings).
0  examples/patterns/swarm/           OK — loaded cleanly (29 settings).
0  examples/patterns/weighted/        OK — loaded cleanly (27 settings).
```

The Python and TypeScript adapters are untouched by this issue — no source under
`adapters/` was changed — so their suites were not re-run for it.

**Re-run independently in a later pass, on the same tree** (the six md5s below
were checked first and all still matched, so nothing had moved underneath):

```text
$ cargo test --workspace 2>&1 | grep -cE "^test result: ok"      →  91
$ cargo test --workspace 2>&1 | grep -c FAILED                   →   0
$ cargo clippy --all-targets -- -D warnings                      →  Finished, no output
$ …the eleven-example --deny-warnings loop above                 →  deny_warnings_failures=0,
                                                                    every settings count identical
$ pact check adapters/python 2>&1 | grep -c loader/folder-skipped-by-name   →  0
$ pact check adapters/python 2>&1 | grep -c loader/file-skipped-by-name     →  1
```

The two scoped files were re-run at the same time: `11 passed` and `6 passed`,
with the eighteen test names matching this document's tables exactly. The
trailing-slash claim in case 5 was re-measured both ways (`examples/refund-desk`
and `examples/refund-desk/`, `examples/patterns/debate` and
`examples/patterns/debate/`) — all four exit 0 — and `pact check <ws>/` on a
workspace with a top-level `dist/` produces **zero** `//` in its output.

Files changed:

| file | md5 (now) | what |
|---|---|---|
| `crates/pact-loader/src/policy.rs` | `245f2b3849079ab15119b99e49e2fd3c` | the split, the place bit, `Pattern`, `Ignore::inherited`, `Ignore::matching`, four unit tests |
| `crates/pact-loader/src/lib.rs` | `91d0790acd351b7b236c6278aa27aa93` | the `Ignored` arms, the note, the `name_only` candidate, the module doc |
| `crates/pact-loader/src/reach.rs` | `c4ce182950321fe863d1d68c5e5f92cd` | the `UNLOADED` guard |
| `crates/pact-diag/src/lib.rs` | `f9e5eb61678e1ea2d99e0cc74feb5168` | `Diagnostic::note` |
| `crates/pact-cli/src/discover.rs` | `b76f49e467a49e3d6425ba3f8c9dedc8` | `walk` asks `Policy::is_ignored` |
| `crates/pact-cli/src/main.rs` | `71c58e04dfaaf54c7dda923e5ca369c9` | stderr routing in `show`, `discover`, `card` |
| `crates/pact-loader/tests/an_agent_in_a_folder_named_build_is_never_silently_gone.rs` | four new tests, two changed, the module doc — **and, in the later pass, the headline claim narrowed and the non-UTF-8 hole added to "Consciously not covered" (prose only; no test touched, still `11 passed`)** |
| `crates/pact-cli/tests/a_folder_the_checker_skips_is_named_on_the_way_past.rs` | three new tests, one assertion added, the module doc |

The md5s are given so a reader can tell whether they are looking at the tree
this document was measured against. The two test files deliberately have none —
the second pass edited one of them, so a fixed value there would be stale by the
time it was read.

---

## Register update

**`docs/70-PRODUCTION-GAP-REGISTER.md` has no row for any of this, and that is
measured, not assumed:**

```text
$ grep -c 'folder-skipped\|file-skipped\|pactignore\|SKIP_DIRS\|is_ignored' \
      docs/70-PRODUCTION-GAP-REGISTER.md
0
```

(The single `node_modules` hit in that file is row `C7`, about the TypeScript
type check skipping when dependencies are absent — a different subject.)

So there is no row to correct. What this issue **does** correct is a
carried-forward finding already in that file, at **lines 31–33**:

> **A seam is not an effect.** The first `settings:` test checked the mapping
> table and what `apply_settings` returned — both true of a transport that then
> dropped every setting on the floor.

B2 is that sentence a second time, in a second crate, and the proof is
mechanical rather than rhetorical. With the caller's whole `match reason`
replaced by `continue` — the defect restored — the seam's own unit tests do not
notice:

```text
$ cargo test -p pact-loader --lib policy      # with the caller's match replaced by `continue`
test result: ok. 19 passed; 0 failed; 0 ignored; 0 measured; 185 filtered out
```

Nineteen, and identical to the unmutated run — the seam's suite cannot see the
defect at all. (This document first recorded that figure as 15, which was the
count *before* this issue added unit tests to `policy::tests`; re-measured under
the mutation today it is 19. The claim is unchanged and the number now comes
from the run above.)

The recommended edit is one clause appended to that bullet, and nothing else in
the file: *"—and again at `Policy::is_ignored`, where the seam returned the
right answer, the one caller answered it with `continue`, and nineteen green
policy assertions could not tell a reported skip from a silent deletion. A seam
test can only ever assert what the seam's RETURN TYPE can express."* That last
sentence is the transferable part: `is_ignored -> bool` set a ceiling on what
any test of it could claim, so the blind spot was in the signature before it was
in the suite.

`docs/remediation/REGISTER.md` §"held by" carries one row per closed issue —
`B1`'s is at line 107. B2 has none; the row to add names both doors, because the
division of labour between them is the finding:

> | an entry skipped for its name is loaded or reported, and a name a tool wrote
> is skipped without noise (**B2**) |
> `crates/pact-loader/tests/an_agent_in_a_folder_named_build_is_never_silently_gone.rs`
> (the document and the sentence),
> `crates/pact-cli/tests/a_folder_the_checker_skips_is_named_on_the_way_past.rs`
> (the exit status, the rendered output, and `discover`) — argument in
> `docs/remediation/B2-skipdirs-silent-delete.md` |

`docs/remediation/QUEUE.md` row 12 (`B2` / `skipdirs-silent-delete`) is `done`,
with this file as its doc. Nothing else in that file is changed.

Two rules join the set an embedder has to know about, and both are listed in the
`pact-loader` module doc, which is this repository's stand-in for a rule
catalogue:

* `loader/file-skipped-by-name` — now also raised for a documentation stem
  written as prose **below the top of the workspace**;
* `loader/ignored-on-purpose` — new, `Severity::Note`, one per entry a
  `.pactignore` line removed.

---

## What remains open

**A name that is not valid UTF-8 is still deleted in silence — and this one
contradicts the headline rather than qualifying it.** Found by a second pass
asked to attack the landed fix, measured today, **not repaired.**

Fifteen lines above the repaired code, and again in the payload walker, the loop
still opens with a bare `continue`:

```rust
// crates/pact-loader/src/lib.rs:897 (classify) and :769 (walk_payload)
let Ok(name) = entry.file_name().into_string() else {
    continue;
};
```

No `Diagnostics` is touched. That is a skip decided by an entry's NAME, which is
exactly what this issue is about, and it is silent. Measured on a workspace
holding `agents/keeper/` beside a Latin-1 `agents/caf\xe9-agent/agent.yaml` —
what a zip from Windows or macOS, or a `LANG=C` shell, produces:

```text
$ pact check <ws> --deny-warnings
OK — <ws> loaded cleanly (8 settings).
EXIT=0

$ pact show <ws>
  agents: keeper only        stderr: 0 bytes
```

Word for word the reproduction at the top of this document, one skip-reason
over, and it survives every part of the fix — including the new stderr routing,
because there is no diagnostic to route.

The payload half is worse in kind. A `skills/helper/references/` folder holding
`good.txt` and a Latin-1 `r\xe9sum\xe9.txt`:

```text
$ pact check <ws> --deny-warnings
OK — <ws> loaded cleanly (14 settings).   EXIT=0
$ pact show <ws>   →   "files": [ { "$file": "good.txt", … } ]     one entry
```

The `files:` manifest feeds `workspace-digest`, which the loader promises is
reproducible on any machine. Here a filename's **encoding** silently changes it
and nothing says so.

**Why it was not fixed in this pass, stated rather than implied.** It is a
different seam: an encoding boundary in three walkers (`classify`,
`walk_payload`, and `discover::walk` at `crates/pact-cli/src/discover.rs:75`),
needing its own rule id, its own place in the module doc's rule catalogue, and a
`#[cfg(unix)]` fixture, because a filename that is not valid UTF-8 is not
creatable the same way on Windows. None of that is name-collision policy, which
is what B2 is, and doing it here would have meant editing three walkers on the
strength of one issue's title.

**What was fixed is the false claim.** The test file's own headline read *"An
entry skipped because of its NAME is either loaded or reported. It is never
silently absent."* — which the measurement above falsifies, and which its
"Consciously not covered" list did not exclude. It now reads *"skipped because
its name collides with a convention"*, and both holes are written into that list
with the commands that produce them. A test file that overclaims is the failure
this whole programme exists to stop, so the claim was narrowed to what the
eleven tests actually hold; no test was weakened, and all eleven still pass.

**It deserves a queue row of its own** — the same standing the siblings found by
other passes were given. It is not on `docs/remediation/QUEUE.md` today.

**EXP-10 is half met, and this document is where that is written down.**
`docs/20-ARCHITECTURE-R5.md` §EXP-10 requires three things of `.pactignore`:

1. every entry it suppresses produces a line naming the entry and the pattern —
   **done**, as a `Severity::Note` diagnostic;
2. `.pactignore` is a first-class typed IR node appearing in `canonical.json` —
   **not done**. `Policy::is_ignored` still answers `Hidden` for any name
   starting with a dot, so `.pactignore` is never an IR node;
3. it is covered by `workspace-digest` — **not done**, for the same reason.

EXP-10 asks for (1) as a **`LoadReport`** line, and `LoadReport` cannot carry one:
`crates/pact-loader/src/report.rs` is `pub struct LoadReport { waits }`, and its
own docstring lists "files suppressed with the pattern that suppressed them" as a
LOAD-14 entry that does not yet exist. A diagnostic is the stand-in. Moving it to
`LoadReport` is the natural next step and needs `LoadReport` to grow a second
field, which is a bigger change than this issue.

**A skipped FOLDER still contributes nothing to the document.** The obvious
repair — a `pact_doc::UNLOADED` marker, as an unreadable file gets — turns the
warning into `error: 'dist' is not something a workspace can have` for every
repository that keeps its build output beside its workspace. Measured, and
strictly worse than what it replaces. The equivalent repair for a skipped FILE
below the root **is** done (F3), because a name in `tools:` is referenced and a
folder name is not.

**`target` is a judgement call, not a proof.** It is on the speaking list because
it is an English noun an author could mean. If measurement later shows more Rust
repositories are PACT workspace roots than there are authors who name something
`target`, the entry moves to `TOOL_ONLY_DIRS` and one line in
`a_folder_only_a_tool_ever_makes_is_skipped_without_a_word` moves with it. The
criterion is written down so that the argument, not the list, is what gets
re-run.

**`.pactignore` inheritance reaches into payload folders.** That is deliberate
and consistent — the same file governs the same subtree everywhere — but it means
a pattern like `*.md` at the top of a workspace now removes documents from a
knowledge corpus. Every removal is noted, so it is visible, but it is a bigger
lever than it was.

---

## What a reader should take from this

Three things.

**A skip needs a reason, and the reason has to be the one thing that decides
whether anybody hears about it.** `Option<bool>` cannot carry that, and a
`continue` at the call site throws away the only information that mattered.

**"Could the author have meant it?" is the whole criterion, and it must be asked
of every case the rule covers, not of the case that motivated it.** B2's first
repair stated that criterion correctly and applied it to folders only. The three
bugs that followed — noisy `__pycache__`, silent `notice.md`, silent `venv` —
are all the same failure to re-ask it.

**A control test that reads the list it controls is not a control.** Mutation 3
empties `TOOL_ONLY_DIRS` and the loop that iterates it runs zero times, green.
Where a test exists to pin a *judgement*, the judgement has to be written out
next to it, with an assertion that the list has not grown past what was written.
