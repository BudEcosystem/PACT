# A3 — a shortcut that copies itself could kill the checker, and closing it for one file was read as closing it for a tree

**Severity: critical.** · **Status: fixed — the alias-expansion half had landed;
four further defects were found against that fix by measurement and are repaired
here.** · **Register row: `docs/70-PRODUCTION-GAP-REGISTER.md` had no row for
this at all — `grep -rn 'too-large\|copies itself' docs/70-PRODUCTION-GAP-REGISTER.md
docs/90-REVIEW.md README.md site-docs/` returned zero hits — so one is added; see
[Register update](#register-update).**

Every number below names the command that produced it, run against this working
tree on this machine. Where a measurement was taken against a mutated or
pre-fix state, it says which state and how that state was produced. Another
session is editing files in this repository right now; nothing outside this
issue's own files was touched, and nothing was left mutated
(`md5sum crates/pact-doc/src/yaml.rs crates/pact-loader/src/lib.rs` was compared
before and after every mutation run).

---

## What is wrong

YAML lets an author name a block once with `&name` and reuse it with `*name`.
`pact check` used to be killed outright by a twelve-line agent file that did
that: `*name` was charged **one** setting however much it stood for, and charged
*after* `.cloned()` had already made the copy, so neither half of `MAX_NODES`
could work. That much was found, fixed and tested before this document existed.

What this document is about is the **four further ways the same command could
still be killed, or could still lie about why it refused, after that fix had
landed and the gate was green.** All four were reproduced against the fixed
build.

### 1. Defining `&name` keeps a copy, and that copy was charged against nothing

`Anchored::of` did `node.clone()` (`git show HEAD:crates/pact-doc/src/yaml.rs`,
`:161-168`) and `emit` called it at `:343` — after charging `afford(1, own_text)`
for the node's own single setting and nothing at all for the whole-subtree
duplicate about to be stored in `self.anchors`. Every limit in the module was on
the alias arm. A file that never uses a shortcut never reaches that arm.

Definitions written **inside** one another therefore pay for their subtree once
per level, uncharged. Measured, on a workspace whose one agent file is 62 nested
`&name` list definitions around 190,000 leaves, 760,476 bytes, and **zero**
`*name`:

```
$ /usr/bin/time -f 'PEAK_KB=%M ELAPSED=%e' ./target/debug/pact check <ws>
PEAK_KB=3683232 ELAPSED=4.10
EXIT=1                            # from schema/unknown-field, not from any limit
$ grep -c 'too-large\|too-deep' <out>
0
```

The identical tree with the `&`s deleted: `PEAK_KB=127816 ELAPSED=0.75`. So the
3.5 GB is the definitions, not the shape. Under a cap:

```
$ ( ulimit -v 1500000; ./target/debug/pact check <ws> )
memory allocation of 1 bytes failed
Command terminated by signal 6
PEAK_KB=1470232   EXIT=134
$ ( ulimit -v 1500000; ./target/debug/pact discover <ws> )
memory allocation of 120 bytes failed        EXIT=134   (core dumped)
```

The control survives the same cap at `PEAK_KB=127592 EXIT=1`. This is byte for
byte the EXIT=134 the original fix was written to delete, through a door no test
in the repository could open: the only `Anchored::of` call site was the
definition, the copy counter incremented only in `Anchored::copy`, and the
document never produces an `Event::Alias` at all.

### 2. Both budgets reset per file, so the loader survived one file and not a folder

`Builder::new` starts `nodes: 0, text: 0` once per `parse_yaml` call. Nothing
counted the second file against the first. Measured on the fixed build, 400
agent files of 277 bytes each — every one of them ~74,700 settings against a
`MAX_NODES` of 200,000, and 110,817 bytes on disk in total
(`du -sb` on the folder):

```
$ ( ulimit -v 3000000; ./target/debug/pact check <ws> )
memory allocation of 1 bytes failed
Command terminated by signal 6
PEAK_KB=2998240 ELAPSED=4.05   EXIT=134
$ ( ulimit -v 3000000; ./target/debug/pact discover <ws> )
memory allocation of 125 bytes failed
Command terminated by signal 6
PEAK_KB=2998240 ELAPSED=3.94   EXIT=134
```

`crates/pact-cli/tests/a_shortcut_that_copies_itself_cannot_bring_down_the_checker.rs`
declared exactly this outcome to be the defect it closed — *"gaia-ai-runtime is
specified to discover and load trees it did not write, so this is a loader that
any untrusted folder can stop"* — and asserted it with `status.code() ==
Some(1)`. That assertion passed identically whether the loader was safe against
a tree or not, because **every workspace-building helper in the file wrote
exactly one agent file.** A folder is the unit the threat model names and the
unit nothing tested.

### 3. The refusal misdescribed the author's tree and put the caret on an innocent line

Once a `*name` had spent most of the settings budget, the next **ordinary
literal** setting tipped it over and got the no-shortcut-involved wording.
Measured on a 738-byte, 72-line agent file (n0…n4 nine-way shortcuts, then one
`*n4`, seven `*n3`, eight `*n2`, six `*n1`, two `*n0`, then forty plain `zN: 1`
lines):

```
error: This file is too large to load (over 200000 settings).
  --> .../agents/desk.yaml:38:1
38 | z5: 1
   | ^^
  fix: Split it into several files. Any setting can become its own file or folder.
  rule: doc/too-large
```

Both halves are false. The file is 738 bytes. `z5: 1` costs one setting. The
module's own rationale for having two wordings (`yaml.rs:214-218` before this
change) is that *"the author is looking at three words on a line and needs to be
told that those three words stand for everything the shortcut holds"* — and the
one direction that was asserted was the wrong way round:
`a_file_that_really_is_that_big_is_refused_in_its_own_words` asserted
`!err.message.contains("shortcut")`, and nothing asserted the converse. Under
D13/D14 (`docs/01-DECISIONS.md:116-129` — the reader *"cannot write code"*, and
*"expert users write code for this" is not an acceptable answer*) a support lead
handed `z5: 1` and *"split it into several files"* has no path from the message
to the cause.

### 4. Two independent 4 MB literals, one of them unreachable, and a register sentence that is false about both

`crates/pact-doc/src/yaml.rs` grew `MAX_TEXT = 4 * 1024 * 1024`; `pact_loader::
Policy::default` had `max_text_bytes: 4 * 1024 * 1024` already. Two literals,
two crates, no link. Because the charged text of a document is never more than
the bytes present in its file, the loader's always fires first on a file with no
shortcut in it, so `Ran::OutOfText`'s `written_out` arm — *"This file holds too
much writing… Move the long pieces of writing into files of their own beside
this one"* — is not reachable through any production door. Measured, a 5,242,935-byte
agent file:

```
error: '.../agents/desk.yaml' is too big to load (limit is 4 MB).
  fix: Split it into several smaller files in a folder of the same name.
  rule: loader/file-too-large
```

Never `doc/too-large`. The sentence added to `docs/70-PRODUCTION-GAP-REGISTER.md:463`
in this tree — *"`crates/pact-doc/src/yaml.rs:52` `MAX_TEXT = 4 MB` refuses a 5 MB
knowledge file"* — is therefore wrong about which rule refuses it and about what
the author is told to do. That row belongs to C8; see
[Corrections owed elsewhere](#corrections-owed-elsewhere).

And `MAX_TEXT` is a **capability-affecting literal in the Rust core**, which
F-1 (`docs/00-THESIS.md:274`, *"Zero-magic audit: grep the core for literals;
all must resolve from profile"*) and FR-8.1.3 (`docs/30-FRD.md:206`, *"the core
MUST contain no capability-affecting literal"*, status ◐) forbid in so many
words, with `docs/20-ARCHITECTURE-DRAFT.md:1762` fixing "the core" as the Rust
crates. `git show HEAD:crates/pact-doc/src/yaml.rs | grep -n 'const '` returns
only `MAX_DEPTH` and `MAX_NODES`, so `MAX_TEXT` and `MAX_TEXT_MB` are new here.
The first version of this work never named F-1, FR-8.1.3 or AC-7.2 at all.

---

## Root cause

One sentence: **the module counted what a document expands to and forgot that
naming a block is itself an expansion, and the loader counted a document when
the thing it retains is a tree.**

Both are the same mistake at two scales — an accounting boundary drawn where the
*code* has a function call rather than where the *memory* is.

* `Builder::afford` is asked before every allocation the parser makes **except
  one**: the clone `Anchored::of` performed as its last field initialiser. The
  module comment at `:27-34` asserted the invariant (*"charged against what the
  document expands to"*) that the code did not hold, and the module-of-one-type
  arrangement (`mod shortcut`) had been built precisely so copies would be
  countable — with the counter on `copy` and nothing on the constructor.
* `parse_yaml` is the boundary of one document. `Loader::load` is the boundary
  of what is held in memory at once. The per-file budget is a bound on
  *amplification within a file* (277 bytes → 74,732 settings). Nothing bounded
  the number of files, so the amplification is per-file and the retention is
  per-load, and 400 × 74,732 is 30 million settings from 110 KB.
* The two wordings `written_out` and `copied_in` are chosen by **which code path
  noticed**, not by **what spent the budget**. Those coincide only when a
  document is homogeneous. Mix a shortcut and a literal and the wording tracks
  the wrong thing.

---

## Why nothing caught it

Measured, not assumed:

* `grep -rln "too-large" crates/ --include=*.rs` → three files:
  the CLI test, `pact-doc/src/yaml.rs`, `pact-loader/src/lib.rs`. Nothing else
  in the repository mentions the rule.
* The copy counter (`shortcut::COPIES_MADE`) incremented in `Anchored::copy`
  only. The definition path called `Anchored::of`. A test that counts copies
  could not see half of them, and
  `a_shortcut_too_big_to_copy_is_refused_without_first_copying_it` asserted
  `honest_use == 1` when the true number of copies a one-use shortcut makes is
  two — so the counter was **calibrated to the bug**.
* Every test that reached the size accounting reached it through
  `Event::Alias`. A document of nested definitions produces no such event.
* Both workspace helpers in the CLI test file
  (`workspace_with_a_bomb`, `workspace_with_a_wall_of_writing`) wrote exactly
  one `agents/desk.yaml`. `status.code() == Some(1)` cannot fail for a shape
  nobody builds.
* The mirror assertion for the wording existed in one direction only
  (`!message.contains("shortcut")`), so a shortcut wrongly *not* named cost
  nothing.

---

## The fix

Five parts. Line numbers are of this tree after the change.

### 1. The copy a definition keeps is priced without copying, then charged, then made — `yaml.rs:466-503`

`Anchored::of` is split into `Priced::of` (a walk, no allocation,
`yaml.rs:189-200`) and `Anchored::kept` (the allocation, `yaml.rs:218-222`).
`emit` now does:

```rust
if anchor != 0 {
    let priced = Priced::of(&node);
    if let Some(over) = self.afford(priced.size, priced.text) {
        let d = self.over_budget(over, Ran::kept_for_reuse, node.span.clone());
        self.fail(d);
        return;
    }
    self.anchors.insert(anchor, Anchored::kept(&node, priced));
}
```

Same order as the alias arm, for the same reason: a budget consulted after the
fact has already paid for the allocation it exists to refuse. Peak memory for
the parser is now bounded by roughly `2 × MAX_NODES` nodes, because the largest
single charge is one subtree and a subtree is itself under the budget.

`Anchored::kept` increments `COPIES_MADE` as well, so the invariant the module
claims — *no copy of a shortcut's contents exists that a test cannot count* — is
now true of both copies rather than one of them.

### 2. A third wording, for the author who never wrote a `*name` — `yaml.rs:276-302`

`Ran::kept_for_reuse` says *"Naming this for reuse (`&name`) keeps a second copy
of everything under it, which takes the file to over 200000 settings"*, with
*"Either write these values out where they are used, without naming them, or
move them into a file of their own and name that file instead."* The other two
wordings would each be false about such a file: nothing was copied in from
elsewhere, and the file as written is half the size the limit is talking about.
Held to the same no-jargon bar as the other two by an assertion in
`shortcuts_written_inside_one_another_are_refused_though_none_is_ever_used`.

### 3. The refusal points at what spent the budget — `yaml.rs:342-350`, `:449-462`

`Builder` carries a `CopiedIn` record: how many settings and how much writing
`*name` copies have cost, and the single widest copy in each. `over_budget`
consults it:

> if `*name` copies have paid for **more than half** of everything charged in the
> budget that ran out, the report is `copied_in` against the widest copy;
> otherwise it is the caller's wording against the line that ran out.

More than half, not "any", so one small honest `*name` in a file that really is
too big is not blamed for it; and not "all", because the shape that produced the
false report had 59 of its 200,000 settings written out by hand. The same file
as in [defect 3](#3-the-refusal-misdescribed-the-authors-tree-and-put-the-caret-on-an-innocent-line)
now reports:

```
error: This shortcut (`*name`) copies in so much that the file works out to over 200000 settings.
  --> .../agents/desk.yaml:9:4
 9 | a: *n4
   |    ^
```

### 4. A budget for the whole load, not for one file — `pact-loader/src/lib.rs:105-137`, `:185-250`, `:285-294`

`Loader` carries `loaded_settings`, `loaded_text` and `stopped` (`Cell`, because
the walk is recursive and single-threaded and hands `&self` down five call
sites). `load()` resets them, so one `Loader` is one load's worth of budget.
`load_file` is now a wrapper that reads the file and then charges what it turned
out to hold; the old body is `read_file`. Every file kind goes through it —
settings, prose and plain text alike — because all three are held for the life
of the load and the budget is about memory, not about YAML. An attachment folder
needs no charge: it carries file names, never contents.

`MAX_LOAD_SETTINGS = 1_000_000` and `MAX_LOAD_TEXT = 64 MB`. **Measured, not
chosen.** On this machine `pact check` costs ~320 bytes of peak resident memory
per setting and ~3.2 bytes per byte of writing:

| workspace | total | `PEAK_KB` | `ELAPSED` |
|---|---|---|---|
| 1 agent, 2 settings | baseline | 6,144 | 0.08 |
| 400 agents × 500 settings | ~200,000 settings | 72,128 | 0.91 |
| 400 agents × 2,500 | ~1,000,000 settings | 322,236 | 4.16 |
| 400 agents × 5,000 | ~2,000,000 settings | 638,728 | 8.38 |
| 50 files × 1 MB prose | 50 MB writing | 159,920 | 0.15 |
| 400 files × 1 MB prose | 400 MB writing | 1,235,264 | 0.68 |

So the pair is a ceiling around 500 MB — five times the per-file settings budget
and sixteen times the per-file writing budget, which is far above any tree a
person writes and far below what stops a build machine.

The charge is taken **after** each file is read, because what a file costs is
not known until it is read. That leaves the load at most one file over the line,
which is why the per-file budgets have to stay: they are what makes "one file" a
bounded amount. The two budgets are a pair, not a duplicate.

The refusal, `loader/too-much-to-load`, is raised **once** — `stopped` then makes
`load_path` and `load_file` return `None` in silence, so the remaining entries
become the same `unloaded` placeholder an unreadable file already becomes and
the schema stays quiet about documents nobody read. On the 400-file
reproduction that is the difference between one message and 386 copies of it.
Measured on the fixed build:

```
$ ( ulimit -v 3000000; ./target/debug/pact check <ws> )
PEAK_KB=360512 ELAPSED=1.36   EXIT=1
$ grep 'rule:' <out> | sort | uniq -c
      1   rule: loader/too-much-to-load
     65   rule: schema/unknown-field       # the reproduction's own field names
$ ( ulimit -v 3000000; ./target/debug/pact discover <ws> )
PEAK_KB=360288 ELAPSED=1.31   EXIT=0    →  []  +  "skipping <ws>: 66 problem(s)"
```

### 5. The two 4 MB figures are one constant — `yaml.rs:80`, `policy.rs:160`

`pact_doc::yaml::MAX_TEXT` is now `pub` and `Policy::default` reads it rather
than restating it. They are the same answer to the same question — how much
writing one document may hold — asked at two moments: of the file on disk, and
of what the file works out to once every `*name` has been copied in. Written out
separately they were free to drift, and the direction of the drift decides which
of two differently-worded refusals an author gets for one file.

---

## Alternatives rejected

**Store the anchored subtree by reference instead of cloning it.** This is the
better fix in principle — it makes `Anchored::copy` the only allocation point
and needs no second charge — and it is not available. `Node` holds
`Value::List(Vec<Node>)` and `Value::Map(Map)` by value, so there is no cheap
clone to hand out; the node has already been moved into its parent by the time
the anchor is registered, so it cannot be retained by index without a path
fix-up every time a frame pops. Charging is the honest accounting of what is
actually allocated, and it is three lines.

**Give an anchored block a smaller allowance instead of a full second charge.**
Rejected: the memory is a full second copy. Any discount is a number that has to
be right for the DoS not to reopen, and there is no reading under which "half a
copy" is what happens.

**Carry the load budget by threading a `Spent` accumulator through
`parse_yaml_at`.** Rejected on scope and on coverage. It changes a public
signature in `pact-doc` for every caller, and it still counts only
`FileKind::Structured` — a folder of 400 × 3.9 MB prose files is 1.5 GB the
parser never sees. Charging in the loader covers every kind that is retained,
in one place, and needs no API change.

**Refuse each subsequent file once the load is over.** Rejected: 386 copies of
the same sentence is the pile-on that `unloaded` (`pact-loader/src/lib.rs`,
`fields_of_self_file`) was written to prevent. One mistake gets one message.

**Blame the *last* `*name` rather than the widest.** Rejected: the author's
remedy is to shrink or delete the biggest copy, and in the reproduction the last
alias is `*n0`, which stands for nine words.

**Delete `Ran::OutOfText::written_out` as dead.** Rejected: `pact-doc` is a
library, `parse_yaml` is public, and the arm is a real guard for a caller that
is not the loader. It is documented as such at `yaml.rs:70-79` instead, which is
what was actually missing.

---

## Blast radius

* **`pact_doc::yaml::MAX_TEXT` became public.** Additive; no caller changes.
* **`Policy::max_text_bytes` default is unchanged in value** (4 MB) and now
  derives. Any caller constructing a `Policy` literal is untouched.
* **`Loader` gained three private fields** and `Loader::new` now delegates to
  `with_policy`. `Loader` was already `!Sync` in practice (nothing shares one
  across threads); the `Cell`s make that explicit to the compiler. All 21
  construction sites found by
  `grep -rn "Loader::new\|Loader::with_policy" --include=*.rs crates/` compile
  unchanged; `cargo test -p pact-loader` → 299 passed across 15 binaries.
* **An anchored block now costs twice its size against `MAX_NODES`.** The
  effective ceiling for a single `&name` block is ~100,000 settings rather than
  200,000. The shipped specification is the only anchored document in the
  repository (`spec/schema.yaml:462`, `:3181`, `:3315`;
  `grep -rn '&[a-zA-Z_][a-zA-Z0-9_-]*\|: \*[a-zA-Z_]' --include=*.yaml --include=*.yml examples/`
  → 0 hits), and it loads with room to spare — held by
  `the_shortcut_the_worked_example_relies_on_still_loads`, which mutation M4
  shows would go red if that stopped being true.
* **Two existing assertions moved, both because the fix changed when the budget
  runs out, and both re-measured rather than relaxed:**
  `a_shortcut_that_copies_itself_wider_every_line_...` from column 14 to column
  10 (n0…n4 cost 149,469 rather than 74,732, so the *first* copy of `*n4` on
  line 6 is the one that goes over, not the second); `check_refuses_a_shortcut_that_
  stands_for_a_wall_of_writing` from line 31 to line 30, and its unit twin from
  line 28 to line 27 (the 150 KB block is charged twice on its own line, so
  `u25` crosses 4 MB rather than `u26`).
* **One existing assertion was strengthened rather than moved.**
  `a_shortcut_too_big_to_copy_is_refused_without_first_copying_it` asserted
  `honest_use == 1`; the true number of copies is 2 and always was. Changing it
  to 2 is not weakening a test — it is correcting a figure that was calibrated
  to the defect. The test now covers three cases where it covered one.
* **No source outside these three crates changed.** The files this issue
  touched: `crates/pact-doc/src/yaml.rs`, `crates/pact-loader/src/lib.rs`,
  `crates/pact-loader/src/policy.rs`,
  `crates/pact-cli/tests/a_shortcut_that_copies_itself_cannot_bring_down_the_checker.rs`,
  this document, the queue row, one register row — and two numbers in
  `README.md`, because the headline test count is asserted against the live
  `#[test]` count and this issue adds five Rust tests
  (`adapters/python/tests/test_the_headline_test_count_is_the_count.py`).

---

## The tests

Four new, three corrected, all in files that already existed.

| test | file | what it holds |
|---|---|---|
| `shortcuts_written_inside_one_another_are_refused_though_none_is_ever_used` | `pact-doc/src/yaml.rs` | 30 nested `&name` definitions, no `*name` anywhere; refused as `doc/too-large` in the `kept_for_reuse` wording, jargon-free |
| `a_file_a_shortcut_filled_up_is_not_blamed_on_the_next_ordinary_line` | `pact-doc/src/yaml.rs` | the 738-byte mixed tree; the caret must land on a line containing `*n` and the message must say "shortcut" |
| `check_refuses_a_folder_of_shortcuts_instead_of_being_killed_by_it` | `pact-cli/tests/…the_checker.rs` | 20 agent files each inside every per-file budget; `code() == Some(1)`, one `loader/too-much-to-load`, exactly one `rule:` line in the whole report |
| `discover_survives_the_same_folder_it_cannot_load` | `pact-cli/tests/…the_checker.rs` | the same folder through the command D2 specifies for walking foreign trees; `code() == Some(0)`, `[]`, and a `skipping` line |
| `check_refuses_shortcuts_written_inside_one_another_though_none_is_used` | `pact-cli/tests/…the_checker.rs` | the nested-definition file through **both** `pact check` and `pact discover`; `code().is_some()` in both, one `doc/too-large` from `check` |
| `a_shortcut_too_big_to_copy_is_refused_without_first_copying_it` | `pact-doc/src/yaml.rs` | now three counts, not one: honest use makes **2** copies; refused-at-the-use makes **1** (the kept one) and never the second; refused-at-the-definition makes **0** |
| `check_refuses_a_shortcut_that_copies_itself_instead_of_being_killed_by_it` | `pact-cli/tests/…the_checker.rs` | gained the message assertion, without which it no longer bites M1 — see below |

Two deliberate choices about the folder tests:

* **Twenty files, where the reproduction used four hundred.** The load-wide
  budget runs out on the fourteenth file either way, so files fifteen to four
  hundred are never read and the measured peak is the same. What the extra 380
  change is only what happens when the fix is absent — 30 million settings and
  three gigabytes on a machine other people are building on. Same argument the
  file already made for five levels rather than eight.
* **Every field in those agent files carries the `x-` prefix.** This is load-bearing
  and was found by measurement: with one ordinary unknown field in them, the
  mutated build's answer is 66 `schema/unknown-field` complaints, `pact discover`
  skips the workspace for *that*, and `discover_survives_the_same_folder_it_cannot_load`
  passes under M7 while the folder it was written about is still unbounded.
  Measured before and after the prefix was added.

---

## The mutation

Eight mutations, each applied to this tree, measured, and reverted with
`md5sum` compared. `M*` names are the ones written into the test docstrings.

| # | mutation | `cargo test -p pact-doc --lib` | `cargo test -p pact-cli --test a_shortcut_…the_checker` |
|---|---|---|---|
| **M1** | restore the pre-fix alias arm: `self.anchors.get(&id).map(\|a\| a.copy())` then `emit(node, 0)` | `42 passed; 6 failed` | `4 passed; 3 failed` |
| **M2** | charge settings only: `afford(size, 0)`, `afford(1, 0)`, `afford(priced.size, 0)` | `45 passed; 3 failed` | `6 passed; 1 failed` |
| **M3** | in the alias arm, make the copy above the two checks and attach it after | `47 passed; 1 failed` | `7 passed` |
| **M4** | `size: node.node_count() + 200_000` in `Priced::of` | `39 passed; 9 failed` | `1 passed; 6 failed` |
| **M5** | delete the `afford` in `emit` that pays for the kept copy | `43 passed; 5 failed` | `5 passed; 2 failed` |
| **M6** | `emit` calls `over.written_out(...)` directly instead of `over_budget` | `47 passed; 1 failed` | `7 passed` |
| **M7** | `Loader::affordable` returns `true` unconditionally | `48 passed` | `5 passed; 2 failed` |
| **M8** | hoist `Anchored::kept` above the `afford` that pays for it | `47 passed; 1 failed` | `7 passed` |

Three things in that table are worth naming, because each is a claim the
previous round got wrong or could not have made:

* **M1 no longer reds `check_refuses_a_shortcut_that_copies_itself_instead_of_being_
  killed_by_it` on rule and location alone.** With the definition charge in
  place, the mutated build still refuses that file, at line 9, as
  `doc/too-large` — in the definition's words rather than the use's. Measured,
  then fixed by asserting the message. A test that checked only the rule would
  have gone on passing while half the fix was reverted.
* **M7 reds only the two folder tests.** Every single-file test stays green,
  which is precisely the blindness [defect 2](#2-both-budgets-reset-per-file-so-the-loader-survived-one-file-and-not-a-folder)
  describes, now demonstrated rather than argued.
* **M4 takes the whole CLI file down** (`1 passed; 6 failed`) because no command
  can parse the compiled-in specification, which is what says where the
  honest-reuse surface really is:

  ```
  The specification itself has problems (the built-in specification):
  error: Naming this for reuse (`&name`) keeps a second copy of everything under it, …
    --> spec/schema.yaml:463:15
  error: cannot validate against a broken specification
  ```

  Not anything under `examples/`. `BUILTIN_SPEC` is
  `include_str!("../../../spec/schema.yaml")` at `crates/pact-cli/src/main.rs:369`.

**The prose that was wrong, and is now corrected in place.** The previous round
recorded four mutation claims that do not survive measurement:

| where | said | measured |
|---|---|---|
| CLI test file, module header | *"Both tests below then go red"* | three of seven go red under M1 |
| CLI test file, module header | *"Every other test in the suite stayed green"* | `pact-doc --lib` is `42 passed; 6 failed` under M1 |
| `yaml.rs`, `…wider_every_line…` | *"The other sixteen tests in this module stayed green"* | there are 47 others and six are red |
| `yaml.rs`, `…a_lot_of_writing…` | under M2 *"every other test in this module stays green"* | two others are red |

Three of the four CLI tests also carried **no** mutation of their own, contrary
to the protocol; all seven do now.

---

## Failure cases

Enumerated, each with what the checker does today.

| # | input | before | now |
|---|---|---|---|
| 1 | one file, nine-way `*name` five deep | SIGABRT, EXIT=134 | `doc/too-large`, `copied_in` wording, line 9 col 10 |
| 2 | one file, one 150 KB block used 60 times | SIGABRT, EXIT=134, 3,989,076 KB | `doc/too-large`, `copied_in` (writing), line 30 |
| 3 | one file, 62 nested `&name`, **no `*name`** | 3,683,232 KB then SIGABRT under a cap | `doc/too-large`, `kept_for_reuse` wording, `PEAK_KB=93376` |
| 4 | one file, one `&name` block of 150,001 settings, never used | loaded | refused at the definition, **0** copies allocated |
| 5 | one file, `&name` block that fits twice, used once | loaded, then killed at the use | refused at the use, **1** copy allocated (the kept one) |
| 6 | 400 files each inside every per-file budget | SIGABRT through `check` **and** `discover` | `loader/too-much-to-load` once, `PEAK_KB=360512`, EXIT=1 |
| 7 | shortcut spends 99.97% of the budget, a literal tips it over | `written_out` on `z5: 1` | `copied_in` on the widest `*name` |
| 8 | 4 MB of writing, no shortcut anywhere | `written_out` (writing) | unchanged — `copied_in` requires shortcuts to have paid for more than half |
| 9 | 5 MB file on disk | `loader/file-too-large` | unchanged, and now documented as the reason the parser's twin arm is library-only |
| 10 | `*name` for a single word, 5,000 times | loaded | unchanged — one setting per use, held by `a_shortcut_that_stands_for_one_word_still_costs_one_setting` |
| 11 | `*name` and the literal it stands for at 60–66 levels | agree | unchanged — held by the sweep in `a_shortcut_and_the_word_it_stands_for_are_refused_at_the_same_depth` |
| 12 | `spec/schema.yaml` and `examples/refund-desk` | load | unchanged, EXIT=0 |
| 13 | 70-level self-nesting `*name` tower | `doc/too-deep` | unchanged |
| 14 | `*name` that was never defined | `doc/unknown-reference` | unchanged |
| 15 | a folder of 400 × 1 MB prose files | 1,235,264 KB, no limit | `loader/too-much-to-load` at 64 MB of writing |

Cases 3–7 and 15 are new behaviour; each has a test in the table above except
15, which shares `MAX_LOAD_TEXT`'s single code path with 6 and is stated here as
tested only through that path.

---

## Verification

Scoped runs, all on this tree, all green:

```
cargo test -p pact-doc --lib                                         48 passed; 0 failed
cargo test -p pact-doc                                               48 passed (+ 0 doc-tests)
cargo test -p pact-loader                                           299 passed across 15 binaries
cargo test -p pact-cli --test a_shortcut_…the_checker                 7 passed; 0 failed
cargo clippy -p pact-doc -p pact-loader -p pact-cli --all-targets -- -D warnings
                                                                      Finished, no diagnostics
```

The revert-and-rerun check was done per fix, not once at the end: every one of
the eight mutations above was applied to the real source, built, run, and
reverted, and the failures listed are what the runs printed. The end state was
confirmed with `md5sum` against copies taken before the first mutation.

The full gate (`cargo test --workspace`) was run once, after all source changes
had landed.

---

## Register update

`docs/70-PRODUCTION-GAP-REGISTER.md` has no row for any of this — measured:
`grep -rn 'too-large\|copies itself\|too-much-to-load' docs/70-PRODUCTION-GAP-REGISTER.md
docs/90-REVIEW.md README.md site-docs/` returns nothing. A known
remote-triggerable abort in the command `gaia-ai-runtime` is specified to use
was recorded nowhere a reader could find it, which is T7
(`docs/00-THESIS.md:227-231`, *"no silent degradation anywhere"*) applied to the
project's own register. One row is added, in the resource-limits section, saying
what is bounded and at what figures.

### Corrections owed elsewhere

Two, both in documents this issue does not own. They are flagged rather than
edited:

1. **`docs/70-PRODUCTION-GAP-REGISTER.md:463`** (row 7.2, C8's) says
   *"`crates/pact-doc/src/yaml.rs:52` `MAX_TEXT = 4 MB` refuses a 5 MB knowledge
   file"*. Measured: a 5 MB knowledge file is refused by `loader/file-too-large`
   with a different remedy, and `MAX_TEXT` never sees it. The constant is real
   and the criticism of it stands; the example is wrong.
2. **`docs/remediation/C8-profiles.md:49`** cites `yaml.rs:52` for `MAX_TEXT` and
   `yaml.rs:48-49` for `MAX_DEPTH`/`MAX_NODES`. Those are now `:80` and `:60-61`.

Both belong to C8's work item **D-4** (`C8-profiles.md:674`, test 7,
`no_constant_in_the_core_decides_a_capability_in_secret`), which is explicitly
not implemented.

---

## What remains open

Stated at the strength the evidence supports, and no higher.

1. **F-1 / FR-8.1.3 / AC-7.2 is further from met than before this change, not
   closer.** `MAX_TEXT` was one unfiled capability literal in the Rust core;
   this issue adds `MAX_LOAD_SETTINGS` and `MAX_LOAD_TEXT`, and
   `pact_loader::Policy::max_text_bytes` has no author-facing setting either.
   All four are filed **DELIBERATE_AND_CLOSED** in the sense C8 uses — what an
   author raising one buys is the abort it was written to prevent — and the
   reasoning is written at `yaml.rs:49-59` and `pact-loader/src/lib.rs:105-133`
   so D-4 has something to file rather than a constant to discover. **That is a
   filing, not an implementation of F-1.** No Rust-side audit exists
   (`ls crates/*/tests/ | grep -iE 'default|literal|secret|audit'` → nothing).
2. **The load budget is per `Loader`, and `pact discover` builds one per
   workspace.** A folder of N workspaces is therefore bounded at N × the budget,
   not at the budget. Measured that this does not accumulate in
   `discover_cmd` (`crates/pact-cli/src/main.rs:2225-2247` drops each `Found`
   after `inventory`), so the *peak* is one workspace at a time — but that is a
   property of the current call site, not something the loader enforces, and
   nothing tests it.
3. **The charge is taken after a file is read.** The load can go one file over
   the line: at most `MAX_NODES` settings and `MAX_TEXT` of writing, by
   construction, which is why the per-file budgets cannot be removed in favour
   of the load-wide one.
4. **A 760 KB single-line document prints a 760 KB source excerpt.** Visible in
   the defect-3 reproduction: the renderer echoes the offending line in full.
   Not this issue's rule, not fixed here, and the refusal itself is correct.
5. **`Ran::OutOfText::written_out` remains reachable only from a library
   caller** or through a document a shortcut inflated. Documented at
   `yaml.rs:70-79` rather than deleted, because `parse_yaml` is public API.
