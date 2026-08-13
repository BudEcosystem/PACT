# C2 — Bundle mounting: four decisions, taken

*(The file is named for the work item; the row it answers is **C2** in
`docs/70-PRODUCTION-GAP-REGISTER.md`. C7 in that register is closed and is about
the CI gate.)*

**Status: decided, not built.** This document takes the four decisions that
block mounting and says what each costs. It does not implement mounting. The
half of C2 that is closeable today — a real tree that exercises the check —
*is* closed, by `tests/trees/what-a-bundle-brings/` and
`crates/pact-loader/tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs`.

Every number below names the command that produces it.

---

## The state before this document

A workspace can say `bundles:`. Each bundle says where its folder is (`from:`,
required), which kinds it may contribute (`brings:`, required), and — not typed
by an author — what it actually holds (`contributes:`).
`crates/pact-loader/src/bundles.rs` refuses a bundle contributing a kind outside
its `brings:`, and warns when nothing mounted it at all.

**Nothing mounts one.** `from:` is resolved by no pass in this loader. So a
workspace can declare three bundles, load cleanly, and contain not one
definition from any of them.

Two things were also true and worth writing down, because they change what the
decisions below have to be:

**One.** Every test of that check built its own document. `s()`, `list()`,
`map()`, `tree()`, `mounted()` and `unmounted()` in `bundles.rs`'s own `mod
tests` construct a `Value::Map` by hand; no file was ever parsed. That matters
more here than usual, because `contributes:` is not something an author types —
its own line in `spec/schema.yaml` says *"You do not type this — it is what is in
the bundle's own folder."* Either the folder form produces it or nothing does,
and a document a test assembled cannot tell you which.

**Two.** The register measured that with the wrong command. It said:

```bash
grep -rn "bundles:" examples/ tests/     # returned nothing, before this work
```

It returned nothing then, and it would have gone on returning nothing after a
dozen trees declared bundles — because a workspace collection is normally a
**folder**, not a line, and no author types `bundles:` anywhere. The question
the register meant to ask is:

```bash
$ find examples tests -type d -name bundles
tests/trees/what-a-bundle-brings/bundles      # after this work; nothing before it
```

A measurement that could not have detected its own fix is the thing this
register exists to catch, reached one level up. The sharpest demonstration is
what that grep returns **today**, with the tree shipped and the gap half closed:

```bash
$ grep -rn "bundles:" examples/ tests/
tests/trees/what-a-bundle-brings/README.md:20:`bundles:` is how a workspace says …
tests/trees/what-a-bundle-brings/README.md:30:(The register asked that with `grep …
```

Two hits, both **prose in a README** — the one place in the tree where the
string is typed by a human, and the one place where it means nothing to the
loader. The command went from a false negative to a false positive without ever
having answered the question.

---

## Decision 1 — Path resolution and containment

> `from:` is `type: text` with two documented meanings in one field: *"a path
> inside this workspace, or a name your platform team publishes"*. Nothing
> distinguishes them. What is the containment rule?

### The decision

**`from:` is never resolved, and PACT never opens a path it names.** Contributed
content reaches the document by exactly one route: the folder
`bundles/<name>/contributes/`, which the ordinary loader already walks on its
way down from the workspace root. `from:` is provenance — a note saying where
this folder was copied from — and it is read by people, not by code.

So there is no containment rule to write. The containment rule is the loader's,
unchanged: the walk starts at the root and only ever descends.

### Why

The alternative is a second path resolver, and a second path resolver is a
second place to get containment wrong. The first one already carries four rules
that took work to get right, and a `from:` resolver would have to reproduce all
four:

| rule | where it lives |
| --- | --- |
| a symlink is skipped, never followed | `lib.rs:162`, `Policy::follow_symlinks` defaults false |
| including inside a payload directory | `crates/pact-loader/tests/a_shortcut_inside_an_attachment_folder_is_refused_like_any_other.rs` |
| nesting is bounded | `lib.rs:103`, `MAX_DIR_DEPTH = 32` |
| a folder that contains itself is refused | `lib.rs:290`, `loader/cycle` |

Measured today, on a copy of the shipped tree with `from:` rewritten:

```text
$ # bundles/refund-toolkit/refund-toolkit.yaml: from: ../../../../../../etc
$ cargo run -p pact-cli -- check <copy>
warning: the bundle 'refund-toolkit' names `from: ../../../../../../etc` and nothing
         here mounted it, so none of its definitions are in this workspace.
OK — <copy> loaded with 1 warning(s).                                    # exit 0
```

Accepted, because nothing looks. That is safe **only** for as long as nothing
looks, which is the point: the moment `from:` becomes a path anything opens,
that line is an escape, and it bypasses all four rules above at once because
none of them is on that code path.

The header of `bundles.rs` already argues for this without quite saying it:
*"A PACT bundle is a folder of definitions the same loader reads, so the cost of
mounting one is reading files."* The same loader. Not a second one.

### What it costs

**A bundle has to be vendored.** A platform team's release process becomes
"here is a folder, copy it into `bundles/<name>/contributes/`", and an upgrade
is a diff a person reads in their own repository. There is no central upgrade:
if the publisher ships a security fix, every workspace has to take the folder
again. That is a genuine operational cost and it is the one being chosen.

It is chosen because the alternative cost is worse and is not paid by the person
choosing it. A workspace that fetches gets a supply chain: the diff that changes
what your agent can do lives in somebody else's repository, nobody here approved
it, and — per `bundles.rs`'s own header — it can arrive as an `interceptors/`
folder that stops or redirects your runs. `brings:` exists to bound that, and
`brings:` bounds *kinds*, not *content*. Vendoring bounds content, because the
content is in your diff.

**And `from:` keeps a meaning nothing enforces**, which is the honest residue:
`from: acme/refund-toolkit` and `from: bundles/customer-lookup` are both legal
and only the second describes anything real. The warning already says so
(`loader/bundle-not-mounted`), and its wording should be narrowed with the
mounting work to name the folder to create rather than say "copy what it defines
into this tree".

---

## Decision 2 — Merge semantics: where mounting goes, and what re-runs

> `contributes:` would have to be projected into the workspace's typed
> collections and re-validated. Where does mounting go, and what re-runs?

### The decision

**Mounting is a document rewrite in the loader, at exactly the point
`derive::resolve` already sits** — `crates/pact-cli/src/main.rs:1328`, after the
tree loads and the specification is built, before `schema.validate` and before
every whole-tree pass. It **consumes its source** the way `based-on:` is
consumed: a contributed entry moves out of `contributes:` and into the
workspace's own collection, and `contributes:` is left empty.

`a_bundle_brings_only_what_it_said` **moves up to run immediately before the
rewrite.** It is the precondition for projecting, not a check on the result.

Then nothing "re-runs". One document reaches everything. Measured:

```bash
$ awk 'NR>=1416 && NR<=1720' crates/pact-cli/src/main.rs \
    | grep -cE "^\s+(pact_loader::)?[a-z_:]+\((root|$)"
25
```

25 whole-tree passes, all reading `root`. `bundles::a_bundle_brings_only_what_it_said`
is the 18th of them today.

**That number is a reading, not an invariant, and no test pins it.** The range
`1416..1720` is literal and the pattern also matches any call whose first
argument is `root` or that wraps at the end of a line, so one inserted function
changes the answer silently. It is quoted here because the argument needs a
*count* — the alternative to rewriting once is N passes each remembering bundles
exist, and N being roughly twenty-five is the point. Nothing below depends on it
being exactly 25; read "every whole-tree pass" wherever the figure appears. The
same caveat covers the four line numbers this document cites
(`main.rs:1328`, `lib.rs:103`, `:162`, `:290`): all four are correct today and
all four drift.

### Why

This is not a new idea in this codebase; it is the idea `derive.rs` already
uses, and `main.rs` states the argument at the call site:

> Resolving first means one document reaches the schema, the digest, `show` and
> both adapters — the alternative is four places that each have to remember to
> merge.

The alternative — mounting as a pass among the 25, or as a resolution *view* the
name-resolving passes consult — fails on the same argument twice. Half the
passes would see contributed content and half would not, and which half is
decided by whether a pass walks the document blindly or looks in a named
collection. That split exists **today**, and it is measurable:

- A contributed **agent** is held to the egress boundary, because
  `nothing_reaches_outside_the_box` walks every model field wherever it is
  (`crates/pact-cli/tests/every_model_a_document_names_is_held_to_the_boundary.rs::an_agent_a_bundle_contributes_is_held_to_the_boundary_like_any_other`).
- A contributed **tool** is held to nothing at all, because every check on a
  tool starts from `tools:`.

Measured, by replacing the shipped `contributes/tools/find-customer.yaml` with
three lines that are refused anywhere else in the same tree:

```text
connect: a-server-that-does-not-exist
reads: yes
gizmo: 3
```

Under `tools/` that file gives three **errors** — `schema/unknown-field` twice
and `schema/no-such-name` once — and a fourth diagnostic, the
`loader/nothing-points-at-it` warning it earns for being a tool no agent names,
so `pact check` prints `3 problem(s) and 2 warning(s)` and exits 1. Under
`bundles/customer-lookup/contributes/tools/` the same file gives **nothing at
all**, and `pact check` prints `loaded with 1 warning(s)` and exits 0.
Pinned by
`what_a_bundle_brings_is_read_from_a_folder_of_files.rs::a_document_a_bundle_contributes_is_read_as_anything_and_held_to_nothing`,
which fails the day this stops being true.

Rewriting before validation makes that whole class of question go away: a
contributed tool is a tool, in `tools:`, and every one of the 25 passes holds it
to the same thing it holds a written one to. There is no list of passes that
must remember bundles exist.

### Why it must consume its source, and not copy

Because of `load(explode(D)) ≡ D` — AC-1.2′, checked by
`adapters/python/tests/test_a_document_explodes_back_into_its_tree.py` against
the real CLI.

If projection **copied**, `D` would hold `tools.find-customer` *and*
`bundles.customer-lookup.contributes.tools.find-customer`. `explode` would write
both to disk, and re-loading that tree would project a second time onto a name
already taken — a collision under decision 3, so `load(explode(D))` fails
outright. If projection **moves**, `D` holds `tools.find-customer` and a bundle
with no `contributes:`; `explode` writes exactly that; reloading gives the same
document. The round trip survives because the rewrite is idempotent on its own
output, which is precisely why `derive` removes `based-on:` once resolved.

### What it costs

1. **`pact show` stops matching the folder one-to-one.** A setting appears under
   `tools:` that no file in `tools/` produced. This is already true of
   `based-on:`, so it is a cost the format has accepted once; it is still the
   thing a reader trips over.
2. **Diagnostics have to point at the bundle's file and offer a fix in it.** The
   span is already right — spans carry the file a node came from — but fix text
   written for authored trees ("Add a file `tools/x.yaml`") is wrong when the
   document is somebody else's. Each pass that emits a fix naming a file needs
   the case checked, and there are 25 of them.
3. **The unmounted warning has to move with the check**, or it will fire on a
   bundle that was mounted, because after the rewrite every mounted bundle has
   an empty `contributes:` — the exact shape the warning currently reads as
   "nothing mounted it".

---

## Decision 3 — Collisions and recursion

> No collision rules exist. `brings: [bundles]` is a legal choice, so mounting is
> transitive and nothing bounds the recursion.

### The decision, in two parts

**Collisions are an error. Never a merge, never a silent winner, in either
direction.** A contributed name that already exists in the workspace's
collection, and two bundles contributing the same name, both refuse — with both
spans, the way `loader/ambiguous-field` already does:

> `'{}' is set in two places: here, and inside {}.` … `Keep only one.`

**Recursion needs no new bound.** `brings: [bundles]` stays legal and the scope
check becomes recursive.

### Why collisions refuse

There is no defensible silent winner. "The workspace wins" means a bundle's
security fix is silently ignored because somebody here wrote a file with the
same name last year. "The bundle wins" means a third party's next release
silently replaces a definition this workspace wrote and reviewed — which is
`bundles.rs`'s stated hazard arriving through the front door instead of through
`brings:`. Refusing costs one rename, said out loud, by the person who can see
both files.

The precedent is already in the loader: a field set both by a self file and by a
sibling entry is refused rather than picked, on T7. This is the same shape one
level up.

### Why recursion needs no new bound

Because decision 1 says contributed content only ever arrives as folders under
the workspace root. A bundle inside a bundle is a folder inside a folder, so the
recursion is bounded by the filesystem and by `MAX_DIR_DEPTH = 32`, and a folder
that contains itself is already `loader/cycle`. There is no unbounded recursion
here to bound — there is only a check that does not go deep enough.

`a_bundle_brings_only_what_it_said` reads `top.get("bundles")` and stops. It
never looks at `contributes.bundles`. Measured: a bundle nested inside another
bundle's `contributes/`, declaring `brings: [bundles]`, produces **no diagnostic
at all**.

Today that is harmless, because nothing mounts and a nested bundle contributes
nothing to anything. The day mounting lands it stops being harmless: a workspace
saying `brings: [bundles]` about one bundle would have no line anywhere bounding
what arrives two levels down, and `brings:` — the field whose whole purpose is
to bound that — would be checked at exactly one level.

**This was deliberately not fixed here.** It is a change to the reach of a
shipping diagnostic that guards nothing until mounting exists, and it belongs in
the same change as the thing it guards, where its test can mount something.

---

## Decision 4 — Digest impact

> `pact_doc::digest` hashes the whole document. If mounted content lands in the
> node, every workspace digest moves when a third party ships. If it does not,
> the digest stops describing what actually runs.

### The decision

**Mounted content is in the digest.** The digest is taken after the rewrite, so
the digest of a mounted tree equals the digest of the same tree written out
longhand.

### Why this is already decided, and by what

It is decided twice over, and neither decision was made for bundles.

**First, by decision 1.** Because contributed content is only ever files under
the workspace root, it is already hashed — the digest is over the document, and
the document is the tree. Measured on a copy of the shipped tree, changing one
word inside `bundles/customer-lookup/contributes/tools/find-customer.yaml`
(`account number` → `customer number`):

```text
$ cargo run -p pact-cli -- discover <copy> | grep digest
    "digest": "sha256:5a926713a24327b6ec1289b2d8e1f10c1df75184cb79fb6c5b012fcf12035278"
$ # one word changed inside the bundle folder
    "digest": "sha256:65a8d5af544c22b555964a2e113d9c4e584d97284cc9c6533131d14f02eb0f36"
```

The dilemma in the question — *the digest moves when a third party ships*, or
*the digest stops describing what runs* — only exists if `from:` can fetch. It
cannot. A third party cannot ship into your tree; a person here copies a folder
in, and that is a line in your diff. So the digest both moves for every
meaningful change and describes what runs, and it does so without anyone having
to choose.

**Second, by `derive.rs`**, which took the identical decision for `based-on:`:

> `based-on:` itself is removed once resolved, so a document that has been
> derived reads like one that was written out longhand — which is what makes the
> digest of a derived tree comparable to the digest of an expanded one.

Doing the opposite for bundles — hashing the pre-rewrite document — would mean
the digest deliberately omitted a folder of the tree, and would break property 2
of `canonical.rs`'s own header: *"it moves under every meaningful change."*

### What it costs

**There is no digest that answers "did OUR authors change anything".** One
digest, over the whole document, cannot separate "we edited an instruction" from
"we took version 2.2 of a bundle". A reviewer diffing two digests learns that
something changed and not who changed it. Closing that needs a second, narrower
digest over the non-contributed collections, and **we are not adding one**: a
second digest is a second thing lockfiles, caches and signatures can refer to,
and getting two of those consistent is a larger risk than the question is worth
until somebody has the question.

**And `version:` becomes decoration.** `bundle.version` is a text field that
nothing compares against anything; with vendoring, the digest is what actually
pins, and `version:` is a note saying which release the folder was copied from.
That is worth saying in the field's help and is not worth enforcing, because
enforcing it would mean opening `from:`.

---

## Recommendation

**Build the folder form. Never build fetching.**

The folder form is a rewrite beside `derive::resolve`, a recursive scope check,
and a collision error. It is small, it reuses the loader's containment
wholesale, and it closes the gap an author actually hits — that a bundle's tool
loads and no agent can name it.

Fetching should not be built at any point. Every one of the four questions above
is easy because `from:` does not open anything, and hard the moment it does:
containment becomes a new resolver, the digest has to choose between the tree and
the run, `version:` has to be enforced, and `brings:` has to bound content it
cannot see. The register should record that as a decision rather than as an
absence.

---

## Acceptance

The tests that close C2. Named in the house style, each with the mutation that
must kill it.

| # | Test | Mutation |
| --- | --- | --- |
| 1 | `a_tool_a_bundle_contributes_is_a_tool_an_agent_can_name` — the shipped tree's `agents/desk/` gets `uses: [find-customer]` and loads cleanly | delete the projection step |
| 2 | `a_contributed_document_is_held_to_everything_a_written_one_is` — the three-line broken tool above gives the same three diagnostics under `contributes/` as under `tools/` | move the projection after `schema.validate` |
| 3 | `a_name_two_places_supply_is_refused_rather_than_picked` — workspace `tools/find-customer.yaml` beside the bundle's, both spans reported | make either side win |
| 4 | `a_bundle_inside_a_bundle_is_held_to_its_brings_line_too` — a nested bundle contributing `policies` outside its `brings:` is refused | make the scope check read only `top.get("bundles")` |
| 5 | `a_mounted_bundle_is_not_told_nothing_mounted_it` — no `loader/bundle-not-mounted` after the rewrite empties `contributes:` | leave the check at position 18 |
| 6 | `a_mounted_tree_digests_as_the_same_tree_written_longhand` — two trees, one mounting and one with the tool written into `tools/`, same digest | take the digest before the rewrite |
| 7 | `load(explode(D)) ≡ D` — the existing AC-1.2′ suite, extended to `tests/trees/what-a-bundle-brings/` | make the projection copy instead of move |

Test 7 is the one that decides whether decision 2 was implemented as written,
and it is the cheapest: it is an existing suite gaining one tree.

---

## What was built here, and what was not

**Built.** `tests/trees/what-a-bundle-brings/` — a real, loadable, documented
workspace declaring two bundles, one whose folder is present and one whose is
not — and `crates/pact-loader/tests/what_a_bundle_brings_is_read_from_a_folder_of_files.rs`,
eight tests reading it off disk through the real loader.

`a_bundle_brings_only_what_it_said` emits **three** rules, and all three are now
witnessed from a real folder of files rather than only from a map a test built:

| rule | how the tree reaches it |
| --- | --- |
| `loader/bundle-not-mounted` (warning) | `bundles/refund-toolkit/` has no `contributes/` folder, and `bundles/customer-lookup/` does — so the same tree shows the warning firing and staying silent |
| `loader/bundle-brings-more-than-it-said` (error) | a copy of the tree gains `bundles/customer-lookup/contributes/policies/strict.yaml`, which is exactly how the supply-chain case happens: somebody else's version 2.1 ships a directory |
| `loader/bundle-brings-an-unknown-kind` (error) | the same copy gains `contributes/gizmos/` |

The two refusals matter most as folder-witnessed claims, because a hand-built
map holds the key `policies` or `gizmos` because a test typed it, whereas on disk
that key exists only because the loader turned a **directory name** into one. If
the loader ever began filtering directory names against the schema on the way in,
every hand-built test would keep passing over a branch nothing could reach.

Five hand-built tests in `bundles.rs` now carry a comment naming the file-based
test that supersedes each as the sole witness, or saying why it remains the sole
witness of something narrower (the `agents` kind specifically; the *absence* of
the governance sentence for an ordinary kind, which needs a second bundle a
single tree does not have). None was deleted or weakened, because each runs in
microseconds and pins the wording where the wording is written.

The tree is in `tests/trees/` and not `examples/` because it **must warn** — the
warning is the behaviour under test — and `scripts/test-all.sh` runs
`pact check --deny-warnings` over every workspace in `examples/`. Putting it
there would either turn the gate red or force `loader/bundle-not-mounted` to be
quietened, and quietening a diagnostic to keep a script green is how a checker
stops checking. `tests/trees/one-line-gate/` is the existing precedent.

```text
$ cargo run -p pact-cli -- check tests/trees/what-a-bundle-brings
warning: the bundle 'refund-toolkit' names `from: acme/refund-toolkit` and nothing
         here mounted it, so none of its definitions are in this workspace.
OK — tests/trees/what-a-bundle-brings loaded with 1 warning(s).          # exit 0
$ cargo run -p pact-cli -- check tests/trees/what-a-bundle-brings --deny-warnings
                                                                         # exit 1
```

**Not built.** Mounting. The recursive scope check, which guards nothing until
mounting exists. The narrowed wording of `loader/bundle-not-mounted`, which
should name the folder to create and belongs with the code that reads it.
