# C8 — Profiles: the half of AC-7.2 that should not be built

*(The file is named for the work item. The row it answers is **AC-7.2** in
`docs/70-PRODUCTION-GAP-REGISTER.md`, whose profile half this closes — as a
refusal.)*

**Status: decided, and the decision is DO NOT BUILD.** `workspace.profile`
should be deleted and AC-7.2 amended to the half that is held. Nothing here is
implemented; every change this document asks for is listed in §5 and none of it
has been made.

Every number below names the command that produces it. Measured **2026-08-06**
against this tree.

---

## 1. Where this stands

AC-7.2 is one sentence with two halves:

> *All defaults resolve from profiles; a core audit finds no capability-affecting
> literal.*

**The audit half is met over the Python adapter package, and nowhere else.**
Every numeric module-level default in `adapters/python/src/pact_adapters` is
filed as author-settable (naming the field), not-about-capability, or
deliberate-and-closed (saying what an author overriding it could weaken). One in
none of the three fails the suite. It is held by
`adapters/python/tests/test_no_default_decides_a_capability_in_secret.py`.

**That is narrower than the criterion, and the narrowing is stated here rather
than left to be found.** AC-7.2 says *"a core audit"*, and this repository's own
word for the core is the Rust crates — `docs/20-ARCHITECTURE-DRAFT.md:1766`,
*"the audit forbids capability-affecting **literals in the core**"*; ARCH:1500,
*"an air-gapped Rust core"*. The shipped walk reads one directory and it is not
that one:

```python
# adapters/python/tests/test_no_default_decides_a_capability_in_secret.py:45
SRC = REPO / "adapters/python/src/pact_adapters"      # the entire walk
```

The core carries unfiled numeric constants, each of which decides what an author
may write, and no Rust-side audit exists to make anybody file them
(`ls crates/*/tests/ | grep -iE 'default|literal|secret|audit'` → nothing):

| constant | what it decides |
|---|---|
| `crates/pact-doc/src/yaml.rs:52` `MAX_TEXT = 4 * 1024 * 1024` | a 5 MB knowledge file is refused |
| `crates/pact-doc/src/yaml.rs:48-49` `MAX_DEPTH = 64`, `MAX_NODES = 200_000` | how large a document may be |
| `crates/pact-loader/src/lib.rs:103` `MAX_DIR_DEPTH = 32` | how deeply a tree may nest |
| `crates/pact-loader/src/callable.rs:66` `LONGEST = 64` | how long a tool name may be |
| `crates/pact-schema/src/summary.rs:86` `MOST_WORDS = 16` | how long a refusal sentence may be |

Worse for this document's own evidence: `resolve.SCORE_TOLERANCE` is quoted in §2
as proof the closed group is real, and its twin
`crates/pact-schema/src/coerce.rs:76 pub const SCORE_TOLERANCE: f64 = 1e-9` is
audited by nothing. The mechanism the audit's docstring claims — *"adding one
forces the decision to be written down"* — does not operate on the core at all.
**This is defect D-4 in §7**, and until it is closed, "the audit half is met"
must be read with the package name attached to it. The decision below does not
depend on the core being audited: it depends on the closed group being non-empty
in the half that *is* walked, which it is.

**The profile half is unbuilt, and is not partly built.** `workspace.profile` is
`type: text` with no `choices:` (`spec/schema.yaml:143`). Nothing resolves it:

```bash
$ grep -rln "profile" crates/ --include="*.rs"
crates/pact-cli/src/main.rs          # and nothing else — 12 lines: eleven in
                                     # `a_profile_selects_nothing_yet` and its
                                     # doc, one at the call site (main.rs:1447)
$ grep -rn "profile:" examples/ tests/
                                     # nothing. No workspace here has ever written one
```

`pact check` says so out loud rather than letting an author believe otherwise:

```text
warning: `profile: production` chooses a set of defaults, and nothing in PACT
         reads it — so this workspace behaves exactly as one with no `profile:` line.
  rule: loader/profile-selects-nothing
```

**And the documentation site advertises it anyway.** `site-docs/reference/kinds.md`
lists the workspace's five core fields as
`name`, `workspace-id`, `description`, `owner`, **`profile`** — the fifth thing a
newcomer is shown about the top-level kind is the one field in it that does
nothing. `site-docs/status/gaps.md` does not mention it; the only place the truth
is written is a warning you have to run the checker to see.

---

## 2. What a profile would actually select — the walk, re-measured

```bash
$ cd adapters/python && uv run python -c "
import sys; sys.path.insert(0,'tests')
import test_no_default_decides_a_capability_in_secret as t
print(len(t._capability_literals()), len(t.AUTHOR_SETS_IT),
      len(t.NOT_ABOUT_CAPABILITY), len(t.DELIBERATE_AND_CLOSED))"
26 7 9 10
```

**26 today.** A previous pass measured 25, and both figures are correct for the
day they were taken — closing a defect anywhere in the package adds or removes a
constant. That is why the register refuses to carry the number and why this
document carries it with a date beside it. **The decision below does not depend
on the figure.** It depends on the split, and on one member of the split being
non-empty.

| group | count | what a profile could do with it |
|---|---:|---|
| `AUTHOR_SETS_IT` | 7 | supply a value the author did not write |
| `NOT_ABOUT_CAPABILITY` | 9 | nothing worth having — by their own filing, no agent can do more or less because of one |
| `DELIBERATE_AND_CLOSED` | 10 | **undo ten decisions taken on purpose** |

### The criterion's two halves pull against each other

*"All defaults resolve from profiles"* and *"a core audit finds no
capability-affecting literal"* are not comfortably two halves of one requirement.
Ten of the 26 are filed `DELIBERATE_AND_CLOSED`, and each row states what an
author overriding it could weaken:

> `evals.CONSEQUENTIAL_BAR` — *"an author who could lower it could accept a suite
> that sometimes refunds the wrong person"*
>
> `exploding.RESERVED` — *"an author who could shorten this list could write a
> document that vanishes on somebody else's machine"*
>
> `resolve.SCORE_TOLERANCE` — *"an author who could widen it could have `= 80` met
> by a model publishing 79.99"*

A profile layer **as the architecture draft proposes it** is, by definition, a way
for an author to lower `CONSEQUENTIAL_BAR`.

**The draft has an answer to this, and it must be quoted rather than stepped
around.** `docs/20-ARCHITECTURE-DRAFT.md:1761-1764`:

> A builtin profile shipped as *data* satisfies F-1/AC-7.2 — the audit forbids
> capability-affecting **literals in the core**, not a versioned default profile
> document.

On that reading the two halves do not contradict: ship the closed group as a
`builtin` profile document nobody may override, and *"all defaults resolve from
profiles"* is true without `CONSEQUENTIAL_BAR` becoming settable. So the flat
claim *"building both is not possible"* is too strong, and it is withdrawn.

**What survives is narrower and still decisive.** The proposal's own resolution
order is `builtin → profile → workspace → agent → variant → run-override`,
**later-wins** (RES-2, quoted whole in §3.1). Later-wins is precisely what makes
a workspace layer able to overwrite a `builtin` one. For the shipped-data reading
to hold, `builtin` would have to be a layer that later layers *cannot* overwrite —
per-field closure, a rule that says *"this row of the builtin document is
final"*. Nothing in RES-2, in FR-8.1.3, or anywhere else in this repository
designs that. So the honest statement is:

> AC-7.2's two halves can only both be true under a mechanism nobody has
> designed — a profile layer with per-field closure. Under the mechanism that
> *is* written down, they contradict, because later-wins makes every filed-closed
> default settable by the next layer along.

And a per-field-closed builtin document would not remove the reason this document
refuses profiles anyway; it relocates the number from a constant with a comment
beside it to a shipped YAML file the reader has to go and find. §3.3 and §3.5 are
about *where the number is relative to the reader*, and a builtin document makes
that strictly worse, not better.

The audit half is the one with the test.

### And the 7 that remain do not want a profile

| default | the field that overrides it | where that field is written |
|---|---|---|
| `ir.DEFAULT_STEPS` | `limits.steps-at-most:` | on an agent |
| `slo.FEELS` | `limits.feel:` | on an agent — **and is already a named default set** |
| `learning.SHRINK_LIMIT` | `learning.max-drift:` | once, on the workspace |
| `context_policy.SUMMARY_RESERVE` | `context-policy.keep-under:` | on one context policy |
| `interceptors.HIDING_RUNS_AT` | `runs-at:` | on one rule |
| `interceptors.REDACTION_RUNS_AT` | `runs-at:` | on one rule |
| `interceptors.EVERYTHING_ELSE_RUNS_AT` | `runs-at:` | on one rule |

Three of the seven are `runs-at:` **on a rule**, and a profile-wide `runs-at:`
means nothing — the whole point of the three constants is that a hiding rule and
a stop-the-run rule fire at different moments. One is per-context-policy. One
(`slo.FEELS`) is *already* the thing a profile would be, spelled at the field.

So `profile: production` could plausibly supply **two numbers** — how many steps
an agent takes when it says nothing, and how much a learning proposal may
rewrite — and the table above names the one-line field that already reaches each
of them (`limits.steps-at-most:`, `learning.max-drift:`). The count of numbers a
profile would reach that **no existing mechanism reaches is zero**. Every row of
`AUTHOR_SETS_IT` is, by its own filing, already settable by a named field in the
file where it takes effect; that is what puts it in that group.

---

## 3. Five arguments, each measured

### 3.1 PACT layers in exactly one shape, and a profile is not that shape

An earlier draft of this section said *"this format refuses precedence"*. That is
false and it is refuted by §4 of this same document, which nominates a layering
mechanism as the replacement for profiles. The claim is narrowed to what
survives, which is enough.

**What PACT actually refuses** is precedence between two spellings of *one field
in one entry*. `crates/pact-loader/src/lib.rs:30-33`:

> **Every ambiguity is refused rather than resolved by precedence** (thesis T7 —
> there is no silent loss anywhere). Defining `instructions` both in `agent.yaml`
> and as `instructions.md` is a mistake the author wants to know about; picking a
> winner would hide it.

`docs/30-FRD.md:22` says it as a MUST and marks it **`▣`**:

> **FR-1.1.4** — Defining the same field twice MUST be an error naming both
> locations. **Precedence MUST NOT be used to resolve it.**

That row sits in the FRD's §1.1 *Expansion Rule* block, between FR-1.1.3
(self-files) and FR-1.1.5 (entry order). It is a tree-loading rule about
duplicate definition, not a prohibition on layering — so there is **no direct
contradiction** between it and FR-8.1.3, and the earlier draft's claim of one is
withdrawn.

**What PACT does ship is layering, twice, and both instances share one property.**

* `based-on:` — `crates/pact-loader/src/derive.rs:25-27`: *"The base's fields are
  taken, the deriving entry's fields are **laid over the top**"*. That is
  later-wins.
* `feel:` — `slo.py`'s `from_mapping`: *"`feel:` supplies what the author did not
  write, and never overrides what they did"*. A builtin→authored layer.

The property both have, and the one a workspace-level `profile:` cannot have:
**the name of the layer is written next to the value it changes.** `based-on:
house` is a line in the agent whose fields it supplies; `feel: interactive` is a
line inside the `limits:` block whose figures it fills. `profile: production` at
the top of `workspace.yaml` tells a reader looking at an agent's `limits:` block
nothing at all, because it is not there. That is the argument, and §4 is where it
is developed.

**The proposal's own resolution order, quoted whole.**
`docs/20-ARCHITECTURE-DRAFT.md:2094-2099`, RES-2:

> Select profile (target). Expand every default through the vertical chain:
> `builtin → profile → workspace → agent → variant → run-override`.
> Linear, **later-wins**, no diamonds. **Record every layer that touched a
> field.** `builtin` is a shipped profile DOCUMENT (the `feel` table, §4.3), not
> a set of literals in the core — AC-7.2 is about literals.

Two clauses in that block answer this document and both are answered back:

1. *"Record every layer that touched a field"* — this is FR-8.1.6, *"Shadowing
   and precedence decisions MUST be reported, never silent"*, marked **`☐` not
   started**. The proposal contains its own safety requirement, which is to its
   credit; the requirement has never been built, which is the point. A promise
   inside an unbuilt mechanism does not rescue the mechanism, because the two
   would have to be built together and only the cheap half ever is. Nothing in
   the repository reports provenance for the layering it *already* ships — see
   §6 price 5, where `based-on:` drops a spend cap in silence, which is FR-8.1.6
   unmet for a mechanism that has been shipping for months.
2. *"`builtin` is a shipped profile DOCUMENT … AC-7.2 is about literals"* —
   answered in §2. It rescues the criterion only under per-field closure, which
   nobody has designed, and it relocates the number further from the reader
   rather than closer.

### 3.2 The one named default set PACT already ships means two different things in two ports

`feel:` is a profile: one word, a closed list of five, standing for a set of
numbers. Its help says *"This one word supplies `first-reply-within:` and
`finishes-within:` when you have not written them … Anything you write yourself
wins."*

Measured, on a five-line agent whose only limit is `feel: interactive`:

```text
$ pact show <tree>          # what every adapter receives
"limits": { "feel": "interactive", "when-it-runs-out": "stop-and-say-so" }

$ python -c "from pact_adapters.slo import Slo; print(Slo.from_mapping(
      {'feel':'interactive','when-it-runs-out':'stop-and-say-so'}))"
Slo(first_reply_within_s=1.0, finishes_within_s=30.0, …)
```

Two facts in that pair:

1. **The numbers the word stands for never reach `pact check` or `pact show`.**
   The expansion happens at `adapters/python/src/pact_adapters/slo.py:97`
   (`band = FEELS.get(...)`). An author cannot see, from the checker, what
   promise they made.
2. **The second port does not expand it at all.** `feel` is not in
   `LIMITS_FIELDS` (`adapters/typescript/src/limits.ts:237`), so `limitsNotRead`
   returns it and the TypeScript port runs the agent with no latency band. That
   is now *reported* rather than silent — which took a defect and a fix to
   achieve — but it is still one word meaning two things on two substrates.

One field, one closed list of five choices, resolving in one place, and it
already leaks across the port boundary. A profile is that mechanism with an
**open** name space over the 13 fields of `limits:` (13 since 2026-08-13, when
`asks-itself-at-most:` landed), the 12 of `settings:`, and
every `loop:` — and each one of those would need the same two properties
established and tested in both ports before it could be trusted.

### 3.3 A profile is a second place a capability number can come from, which is what F-1 exists to prevent

`docs/00-THESIS.md:274` states F-1 in two columns:

| Invariant | Enforcement |
|---|---|
| **F-1** No hardcoded defaults that cap capability. | Every default is a value in a *profile*, overridable at workspace/agent/variant/run scope. |

The **invariant** is a property. The **enforcement** column is one proposed
mechanism for it, written before any of this was built. The property is met — by
the audit, which proves no default caps capability *in secret*. The mechanism was
never the point, and adopting it would cost the property: after a profile layer,
the answer to *"what caps this agent?"* is no longer "the number in front of you
or a default whose reason is written down", it is "whichever of two places wrote
it last".

### 3.4 Either the digest stops describing the run, or the profile buys nothing

`crates/pact-doc/src/canonical.rs:10` gives the digest two properties, of which
the second is:

> **It moves under every meaningful change.** Any change to a value, a list
> order, or the set of fields must produce a different digest.

A profile has to be selected somewhere, and there are only two places:

**Outside the tree** — a flag, an environment variable, a host setting. Then two
runs with the same digest are two different agents, and the digest that lockfiles,
caches, signatures and provenance records refer to no longer describes what ran.
On a tree whose whole governance story is *the specification is the tree and a
change is a diff a person approved*, that is not a trade-off, it is the failure.

**Inside the tree** — `profile: production` in `workspace.yaml`. Then the
development tree and the production tree differ by exactly one line, the digest
does move, and nothing has been gained over editing the line the profile stands
for: the author still maintains two versions of one file, only now the difference
between them is indirect and the reader has to find a second document to know what
it was.

This is the same dilemma `docs/remediation/C7-bundle-mounting.md` decision 4 faced
for bundles, and it dissolved there for the same reason it dissolves here: it only
exists if something outside the tree can change what the tree means.

### 3.5 D13/D14 — the reader cannot write code, and cannot follow a chain either

D13 is a support lead who *"can edit YAML/Markdown if shown how; cannot write
code"*. D14 makes no-code authoring mandatory for every core capability. The gate
`docs/91-REVIEW-CRITIQUE.md:220` proposes for AC-1.5 is:

> a support lead reaches the D14 bar with ≤ N `pact check` failures and **zero
> reads of `examples/`**

A profile fails that gate by construction. The number that stops the agent is in a
document the author was not shown, found by a name written in a different file.

**Not because nothing prints the resolved value — something does.** §4 measures
`pact show` printing `"settings": {"max-tokens": 1024}` on an agent whose
directory never wrote it. A profile resolved in the loader would show up there the
same way, and it would be wrong to claim otherwise. What no shipped command prints
is **provenance**: which layer supplied the value, and from which file and line.
`pact` has five verbs (`check`, `show`, `waits`, `discover`, `card`) and the
`pact explain --field limits` the architecture draft assumes at
`docs/20-ARCHITECTURE-DRAFT.md:1764` — *"prints the builtin layer with its own
`file:line` so the provenance chain still resolves"* — is not one of them. That
command is FR-8.1.6 (`☐`) wearing a CLI. So the resolved *number* is reachable;
the answer to *"why is it that, and what would I edit to change it"* is not, and
that second question is the one D13 has.

And the deployment PACT is written for is one air-gapped box. Profiles are a fleet
idea: they pay off when one specification is deployed to many environments by
people who cannot edit it. That is not this system's shape, and D17's air-gap makes
it not this system's shape on purpose.

---

## 4. What PACT already has, and why its shape is the right one

Three mechanisms ship today that do what profiles were meant to do:

**`feel:`** — one word, five closed choices, supplying two latency figures, on the
agent, with *"anything you write yourself wins"*.

**`based-on:`** — restate what differs, inherit the rest, on **13** collections:

```bash
$ python3 -c "import yaml; ws=yaml.safe_load(open('spec/schema.yaml'))['groups']['workspace']['fields']
print(len([k for k,v in ws.items() if str(v.get('type','')).startswith('map of group:')]))"
13
# agents tools resources knowledge skills policies questions ports loops
# context-policies bundles interceptors watch
```

It works between agents today. Measured, on a ten-line tree — `agents/house/`
carrying `limits:` and `settings:`, `agents/desk/` carrying `based-on: house`:

```text
$ pact check <tree> --deny-warnings
OK — <tree> loaded cleanly (27 settings).                                # exit 0
$ pact show <tree>        # agents.desk
"settings": { "max-tokens": 1024 }        # inherited, never written in desk/
```

**`loop: pact:loop/react`** — a named shape from a shipped library, with
`based-on:` inside a loop for deriving one.

The property all three share, and the one a workspace-level `profile:` cannot
have: **the name of the default set is written next to the value it changes.** A
reader who finds `feel: interactive` has found the mechanism. A reader who finds
`limits:` on an agent and does not find `finishes-within:` under it has found the
whole story. `profile: production` at the top of `workspace.yaml` tells a reader
looking at an agent's `limits:` block nothing at all, because it is not there.

`pact show` is already documented as the answer to "what did this resolve to"
(`site-docs/reference/cli.md:51` — *"what a `based-on:` inherited"*), which is the
resolved-value question §3 of the brief asks about. It is answered for the
mechanism that ships.

---

## 5. The decision

**Do not build a profile mechanism. Delete the field. Amend the criterion.**

Seven parts, none of them made here:

1. **Delete `workspace.profile`** from `spec/schema.yaml:143`, and with it
   `a_profile_selects_nothing_yet` in `crates/pact-cli/src/main.rs:861` and its
   call site at `main.rs:1447`. **There is no test to delete.**
   `grep -rn "profile-selects-nothing"` returns three hits — the rule id in
   `main.rs:867` and two prose comments — and nothing asserts the rule id, the
   message, or that `--deny-warnings` fails on it. The only thing holding the
   warning in place is `adapters/python/tests/test_every_field_has_a_reader.py`,
   whose `reader_exists` finds the string `"profile"` in the checker
   (`root.get("profile")`) — a name-presence scan, not an assertion about the
   diagnostic. That is worth stating plainly, because the register row cites this
   warning as the reason `profile` left `KNOWN_GAPS`: the field's only claim to
   being read is a substring, which is itself an argument for the decision.
   *This cannot change what any tree does*, because the field has never done
   anything and no shipped tree writes one (`grep -rn "profile:" examples/ tests/`
   → nothing). The only tree it breaks is one that wrote a line that never worked,
   and breaking that tree loudly is the same service the warning performs today,
   made permanent.

2. **Amend AC-7.2** in `docs/00-THESIS.md:526` to the half that is held and
   testable — and to the scope the test actually walks, which is not yet the
   core (§1, D-4):

   > **AC-7.2** No default decides a capability in secret: in every audited
   > component, each numeric default is either overridable by a named document
   > field, is about reporting rather than capability, or is a capability
   > decision recorded with what an author overriding it could weaken. The
   > audited components are named in `scripts/test-all.sh`; today that is the
   > Python adapter package, and D-4 adds the Rust core.

   **The word "core" must not appear in this amendment until D-4 lands.** Writing
   *"every constant in the core"* today would put a false sentence in the thesis
   on the day it was written, which is the exact failure this register exists to
   stop. If D-4 is closed first, the amendment can say "core" and mean it.

3. **Amend F-1's enforcement and test columns** in `docs/00-THESIS.md:274`. The
   invariant — *"No hardcoded defaults that cap capability"* — does not change.
   The enforcement becomes *"Every default is either overridable by a document
   field or filed with the reason it is not"*, and the test becomes the audit
   suite rather than *"grep the core for literals; all must resolve from profile"*.

4. **Amend FR-8.1.3** in `docs/30-FRD.md:206` to match, and mark it `▣`. As
   written — *"Every default MUST resolve from a profile"* — it requires a field
   part 1 deletes and a mechanism §3 refuses. It is **not** in contradiction with
   FR-1.1.4; §3.1 withdrew that claim. It is simply asking for something that is
   not going to exist.

5. **Record it as a decision, not an absence** — a new `D-` entry in
   `docs/01-DECISIONS.md`, so that the next reader of AC-7.2 finds a refusal with
   a price rather than a gap with no owner. The same treatment `C7`'s *"never
   build fetching"* got.

6. **Amend `docs/20-ARCHITECTURE-DRAFT.md`**, which specifies more of this
   mechanism than any other file and is the one an implementer would read.
   Three sites: **RES-2** (`:2094-2099`), whose resolution chain and *"Record
   every layer that touched a field"* become the design that was refused rather
   than the design pending; the *"builtin profile shipped as data"* paragraph
   (`:1761-1764`), which needs the per-field-closure gap from §2 written beside
   it; and the two authored snippets that still show the deleted field,
   `:2629` and `:11097`, both `profile: production`. Leaving these is how a
   deleted field gets re-proposed by somebody reading the architecture rather
   than the register.

7. **Amend `site-docs/reference/kinds.md:24`**, which today lists the
   workspace's five core fields as
   `name`, `workspace-id`, `description`, `owner`, **`profile`** — so the fifth
   thing a newcomer is shown about the top-level kind is the field being
   deleted. This is the site line acceptance test 5 in §8 is about, named here
   as well so that §5 is a complete list of what has to move.

---

## 6. What it costs

Seven prices. Each is real and each is being chosen.

**1. A criterion is amended rather than met.** This is the honest headline and it
should not be softened: AC-7.2 as the thesis wrote it will never be true of this
system. Saying "the profile half is unbuilt" forever is worse — it implies work
that is coming.

**2. There is no workspace-wide `limits:` or `settings:`.** Measured: the
`workspace` group has neither field; `agent` has both, and they carry 12 fields
each.

```bash
$ python3 -c "import yaml; g=yaml.safe_load(open('spec/schema.yaml'))['groups']
print('limits' in g['workspace']['fields'], 'settings' in g['workspace']['fields'])"
False False
```

An author who wants *"no agent here may cost more than 0.05 USD"* writes it once
per agent, or writes one base agent and one `based-on:` line per agent. There is
no single line for it, and this decision does not add one. **A workspace-level
`limits:` block would be a reasonable thing to add later and is not a profile** —
it is one more place a number is written, in the tree, in the file the reader is
already in.

**3. Development and production have no switch.** The answer is two trees, or one
tree and a diff a person makes before deploying. Nothing in PACT will stop
somebody forgetting to make it. That is the cost of the digest meaning what it
says.

**4. A host that does resolve profiles has nowhere in the document to record which
one it used.** The current warning's fix text offers this case —
*"Nothing to type if the system running this resolves profiles itself"* — and
after the deletion it has no field. Priced: a field whose meaning is supplied by
whichever runtime reads it is a portability hole in a format whose one promise is
that the same document means the same thing on every substrate. The right place
for that fact is the host's own records.

**5. `based-on:` narrows in silence, and this decision makes that matter more.**
This is the largest price and it is a defect, measured on the same ten-line tree
as §4 — `agents/house/` sets `finishes-within: 30s` and
`cost-per-request-under: 0.05 USD`; `agents/desk/` says `based-on: house` and
restates `limits:` with two other keys:

```text
$ pact check <tree> --deny-warnings
OK — <tree> loaded cleanly (27 settings).                                # exit 0
$ pact show <tree>        # agents.desk.limits
{ "steps-at-most": 12, "when-it-runs-out": "stop-and-say-so" }
```

**The spend cap and the time promise are gone, and the checker says "cleanly".**
The shallow rule itself is right and `derive.rs:32` argues it correctly — a deep
merge cannot express removal, and losing the ability to narrow a permission is
worse than typing an extra line. But *removal is expressible* and *removal is
silent* are different sentences, and T7 says there is no silent loss anywhere.
Recommending `based-on:` as the answer to shared defaults while it drops a spend
cap without a word is not honest; the warning in §7 is part of the price of this
decision, not an optional follow-up.

**6. A base entry is a runnable agent.** `pact discover` on the same tree lists
`pact:house` — carrying its `description:`, *"Do nothing; this entry exists to be
inherited from"* — with `"runnable": true`, so a runtime indexing the workspace
offers it. (`discover` prints the `description` field; the §9 listing writes that
sentence as `instructions:` because the probe tree gave both the same text.
Corrected in §9, where the tree now has both lines.) There is no way
today to say "this entry is a base". Accepted rather than fixed here: a
`base: yes` field is a new field on 13 kinds to solve a problem nobody has had
yet, and the workaround — inherit from a real agent — costs nothing.

*Closed 2026-08-13, on this deferral's own terms.* What was refused above was
"a new field on 13 kinds"; what landed is one field, on the one kind that can
act — `agent.base` (`spec/schema.yaml`) — and the required-line exemption is
keyed off the group declaring the field, so giving another kind the same word
later is a YAML edit, not a Rust one. `pact discover` leaves a `base: yes`
entry out, `pact card` refuses it naming the runnable choices, and no `team:`
may name it — pinned by `crates/pact-cli/tests/a_base_is_something_to_build_on.rs`,
and held over a real on-disk tree by
`an_inherited_ceiling_reaches_discovery_and_the_card.rs` on
`tests/trees/an-agent-built-on-another/`, whose `desk-pattern` base has no
discovery row at all.

**7. `based-on:` ships with no users.**

```bash
$ grep -rn "based-on" examples/ tests/trees/
                       # nothing
$ grep -c '#\[test\]' crates/pact-loader/src/derive.rs
7                      # all in `mod tests`, all hand-built Value::Map, no file parsed
```

Seven tests, every one of them constructing a document in memory. This is exactly
the finding `C7-bundle-mounting.md` made about `bundles.rs` — *"a document a test
assembled cannot tell you which"* — one kind over, and it is being made about the
mechanism this document nominates as the answer. Nominating it without a tree that
exercises it off disk would be recommending something nobody has run.

---

## 7. The work this decision creates

Five named defects. They are the price above, written as items somebody can pick
up. **None is implemented here.**

**D-1 — a restated block does not say what it dropped.** `based-on:` narrowing a
map should warn, naming the keys the base carried and the restatement does not:

> `limits:` here replaces the whole block `house` set, so
> `cost-per-request-under: 0.05 USD` and `finishes-within: 30s` do not apply to
> this agent. Restate them if you meant to keep them.

Not deep merge — `derive.rs:32`'s removal argument stands. A warning keeps removal
expressible and makes it deliberate, and it is the first piece of FR-8.1.6 anyone
has built.

*Closed 2026-08-13 — see `crates/pact-cli/tests/a_restated_block_says_what_it_dropped.rs`.*
`pact check` over `tests/trees/a-narrower-desk/` warns
`loader/restating-a-block-drops-the-rest`, naming exactly the keys quoted above
— `cost-per-request-under: 0.05 USD` and `finishes-within: 30s` — and
`--deny-warnings` turns it into exit 1.

**D-2 — `feel:` resolves in one port, and never where the author can see it.**
Either both ports expand it, or the loader does and neither port has to. The
second is the shape `spec/comparisons.yaml` already established for
`SCORE_TOLERANCE` — *"two ports deciding one author's line differently is the
defect it was added to fix"*.

**D-3 — `based-on:` has no tree.** One workspace under `tests/trees/` deriving
across at least two kinds, read off disk by the real loader, in the manner of
`tests/trees/what-a-bundle-brings/`.

*Closed 2026-08-13 as written — see
`crates/pact-loader/tests/an_agent_that_inherits_its_limits_is_held_to_them.rs`.*
`tests/trees/an-agent-built-on-another/` goes through the real `Loader` against
the shipped `spec/schema.yaml` and resolves with the real `derive::resolve` —
the same three steps `pact check` takes — and the descendant comes back with
the base's ceilings filled in. One half stays open and is named here so the
test's name does not overclaim: what is held is that the inherited cap
*resolves onto the agent*; no test yet runs that agent and shows the inherited
spend cap **biting in a live run** the way a locally-written one does.

**D-4 — the core is not audited, and AC-7.2 is about the core.** The walk in
`test_no_default_decides_a_capability_in_secret.py:45` reads
`adapters/python/src/pact_adapters` and stops. §1 lists five unfiled numeric
constants in the Rust crates and a sixth — `coerce.rs:76 SCORE_TOLERANCE` — whose
Python twin this document quotes as evidence. The fix is the same mechanism one
language over: a Rust-side audit walking `crates/*/src` for numeric `const`
items, with the same three registers and the same failure message asking which
kind of default it is. Until then, every sentence claiming the audit half is met
carries the package name. **This is the one defect that changes what §5 part 2
may say**, which is why it is not optional bookkeeping.

**D-5 — `pact discover` and `pact card` do not derive, so a `based-on:` agent is
published with no ceiling at all.** This is worse than price 5 and it was sitting
in a command output §6 quoted. Measured on a two-agent tree — `house` with
`model: qwen2.5-7b-instruct` and `limits: {cost-per-request-under: 0.05 USD,
finishes-within: 30s, when-it-runs-out: stop-and-say-so}`, `desk` with nothing but
`based-on: house`:

```text
$ pact check <tree> --deny-warnings
OK — <tree> loaded cleanly (25 settings).                                # exit 0
$ pact show <tree>          # agents.desk — derivation ran
model= qwen2.5-7b-instruct  limits= {cost-per-request-under: 0.05 USD, …}
$ pact discover <tree>      # derivation did not run
pact:desk   model= None   limits= None
pact:house  model= qwen2.5-7b-instruct   limits= {…0.05 USD…}
$ pact card desk <tree>
"description": ""           # inherited from house; check passed on the derived value
```

A runtime that indexes the workspace through `discover` — which is what
`discover` is for, *"an inventory a runtime can index"* — receives `desk` with no
model and **no spend cap**, from a tree the checker called clean. The repository
already knows: `docs/91-REVIEW-CRITIQUE.md:166` (E25 row 0.10) —
*"`main.rs:884-886` runs `derive::resolve` in the check/show path only;
`discover.rs:62-66` calls `Loader::load` bare and `card_cmd` goes through it"* —
and `:216`, *"every forked agent is published to discovery and to its A2A card
with none of its inherited fields"*.

*Closed 2026-08-13 — see
`crates/pact-cli/tests/an_inherited_ceiling_reaches_discovery_and_the_card.rs`.*
On `tests/trees/an-agent-built-on-another/`, `pact discover` now reports the
derived agent whole — inherited `limits:` non-null, no `based-on:` seam in the
output — and `pact card` carries the inherited description; the base itself has
no row, which is §6 price 6's defect closed in the same pass.

D-1, D-3 and **D-5** are prerequisites for §5 part 1 being an honest change.
Deleting `profile:` and pointing the author at `based-on:` is only defensible
once `based-on:` stops dropping spend caps quietly and stops publishing uncapped
agents to a runtime's index. D-4 is a prerequisite for §5 part 2 saying the word
"core". Recommending a mechanism whose failures are in this list, without the
list, is the same class of overclaim §6 price 5 was written to avoid.

---

## 8. Acceptance

The tests that close AC-7.2. Named in the house style, each with the mutation that
must kill it.

| # | Test | Mutation |
|---|---|---|
| 1 | `a_workspace_cannot_name_a_profile_that_selects_nothing` — `profile: production` is `schema/unknown-field`, and the fix names `limits:`, `settings:` and `loop:` rather than listing 24 fields | put the field back with no reader, or delete it and accept the generic unknown-field text |
| 2 | `test_no_default_decides_a_capability_in_secret.py` still passes, unedited | touch the audit half while removing the profile half |
| 3 | `a_restated_block_says_what_it_dropped` (D-1) — the §6 tree; `cost-per-request-under` gone, warning names it, `--deny-warnings` exits 1 | make the loss silent again, or make the merge deep |
| 4 | `an_agent_that_inherits_its_limits_is_held_to_them` (D-3) — a `tests/trees/` workspace where a derived agent's inherited spend cap actually bites in a run | keep the mechanism tested only from hand-built maps |
| 5 | `no_page_still_promises_a_profile` — extends `test_the_documentation_site_tells_the_truth.py`: no `site-docs/` page names `profile` as a workspace field, and `status/gaps.md` does not list it as unbuilt work either, because it is not work | amend the thesis and leave `reference/kinds.md` saying `profile` is a core field |
| 6 | `no_requirement_still_asks_for_the_mechanism_that_was_refused` — FR-8.1.3 does not still read *"Every default MUST resolve from a profile"* while `workspace.profile` is gone, and `docs/20-ARCHITECTURE-DRAFT.md` carries no authored `profile: production` snippet | amend AC-7.2 and leave the FRD row and the architecture snippets |
| 7 | `no_constant_in_the_core_decides_a_capability_in_secret` (D-4) — the Rust twin of test 2, walking `crates/*/src`, three registers, and a message asking which kind of default it is | leave `yaml.rs`'s `MAX_TEXT` and `coerce.rs`'s `SCORE_TOLERANCE` unfiled and let §5 part 2 say "core" anyway |
| 8 | `an_inherited_ceiling_reaches_discovery_and_the_card` (D-5) — the §7 tree; `pact discover` reports `desk`'s inherited model and spend cap, and `pact card desk` its inherited `description:` | run `derive::resolve` in the check/show path only, as `main.rs:884-886` does today |

Test 5 is the one that decides whether this was really taken as a decision: the
site currently tells a newcomer that `profile` is one of a workspace's five core
fields, and the amendment is not done until that line is gone. Test 6 is stated as
*"nothing still asks for the refused mechanism"* rather than as the FRD holding two
opposite rules, because §3.1 withdrew that claim: FR-1.1.4 is a duplicate-definition
rule and does not contradict FR-8.1.3. What FR-8.1.3 does is ask for a field that
part 1 deletes, which is enough to make it wrong.

---

## 9. What was built here, and what was not

**Built: nothing.** This is a decision document and the brief asked for one.

The probe tree every measurement in §4 and §6 came from is twelve lines and is
reproduced here so that anybody can rebuild it rather than take the numbers on
trust. It was written in a scratch directory and is not in this repository — D-3
above is the item that puts a real one in `tests/trees/`.

**An earlier draft of this listing was missing both `description:` lines and did
not load** — `pact check` gave two `schema/missing-field` errors and exit 1, which
is the one thing a reproduction block in a document built on measurement cannot
do. Corrected, and re-run: every figure in §4 and §6 comes back exactly.

```text
workspace.yaml     name / workspace-id / description / owner / allow-egress: []
agents/house/agent.yaml
    name: House Defaults
    description: Do nothing; this entry exists to be inherited from.
    instructions: Do nothing; this entry exists to be inherited from.
    limits: {finishes-within: 30s, cost-per-request-under: 0.05 USD,
             steps-at-most: 8, when-it-runs-out: stop-and-say-so}
    settings: {max-tokens: 1024}
agents/desk/agent.yaml
    name: Desk
    description: Answer the customer's question about their order.
    based-on: house
    instructions: Answer the customer's question about their order.
    limits: {steps-at-most: 12, when-it-runs-out: stop-and-say-so}
```

`pact check <tree> --deny-warnings` → `OK — <tree> loaded cleanly (27 settings).`,
exit 0. The D-5 tree in §7 is a second, smaller one: drop `desk`'s `limits:` block,
give `house` a `model:`, and the count reads 25.

**Not built.** The deletion of `workspace.profile`. The six amendments in §5
parts 2–7. D-1 through D-5. The register row for AC-7.2 points here and says which
half is which, and over what scope; nothing else in the tree changed.

**Update 2026-08-13.** Three of the five defects are now built and the closure
notes sit on their rows in §7: D-1
(`a_restated_block_says_what_it_dropped`), D-3 in its on-disk half
(`an_agent_that_inherits_its_limits_is_held_to_them`, with the live-run half
named open on the row), and D-5
(`an_inherited_ceiling_reaches_discovery_and_the_card`). §6 price 6's deferral
closed on its own terms (`agent.base`, one field on the one kind that can act).
D-2 and D-4 remain open, and §5 parts 1–7 remain unmade.

**A recognition, not an addition.** What this round made sharper is that the
object-orientation a profile mechanism kept being asked to supply was already
here under plain names: the card an outside system reads versus the internals
it never sees is *encapsulation*; `variants:` graded by one set of `evals:` —
many implementations held to one behavioural contract — is *polymorphism*; and
`teamwork.shares:` is *visibility*, saying who may see what. `based-on:` with
`base:` now rounds that out as inheritance that cannot silently drop or
silently publish. Nothing was added to make PACT object-oriented; the names
were recognised on mechanisms that already ship, which is the cheapest kind of
universality there is.
