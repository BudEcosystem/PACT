# F5 — AC-5.2 names six techniques. Two of them ship. The register said all six.

**This is not a refusal. It is a correction.** The other six documents in this
set price things PACT will not build. This one names a claim that is wider than
what holds, in the document whose stated purpose is to stop exactly that — and
the evidence against the claim was already written, by us, in the files the
claim is about.

*(Named `F5` to sit in this set's numbering. The row it corrects is **AC-5.2** in
`docs/70-PRODUCTION-GAP-REGISTER.md`.)*

---

## The claim, as it stands

`docs/70-PRODUCTION-GAP-REGISTER.md`, the AC-5.2 row, struck through and marked
**MET**:

> Six ship: `standard`, `plan-then-do`, `react`, `reflexion`, `tree-of-thought`,
> `answer-more-than-once`. Each terminates … each tells the model something no
> other shape does …

Both of those sub-claims are true, and both are held by tests. What the row does
not say is that **six shapes shipping is not six techniques shipping**. Two of
the shapes are named for techniques they do not implement, one implements part of
the technique it names, and one is named for no technique at all — while the
criterion the row answers names its six techniques by name.
`docs/00-THESIS.md` §6:

> **AC-5.2** ≥ 6 loop patterns (ReAct, Plan-and-Execute, Reflexion,
> Tree-of-Thought, self-consistency, CodeAct)

**The names are not illustrative.** `docs/30-FRD.md` FR-6.1.5 restates the same
list as a requirement — *"≥6 loop patterns MUST be expressible: ReAct,
Plan-Execute, Reflexion, Tree-of-Thought, self-consistency, CodeAct"* — so the
enumeration is the criterion and the `≥ 6` is its consequence, not the other way
round. Six shapes with different names would satisfy a count; they do not satisfy
this.

## The evidence, in our own files

Neither of these had to be discovered. Both shapes say it themselves, in the
`description:` an author reads and in the header comment above it.

**`tree-of-thought`** — `spec/loops/tree-of-thought.yaml`, and the same words in
`adapters/python/src/pact_adapters/loops.py`:

> The branches are written down and pruned in the transcript, not executed and
> compared.

and, in the file's header:

> **This is a tree only in the sense that three branches are written down and two
> are cut.** PACT's loop is a state machine over stages, so it cannot actually
> run three branches and compare what happened.

Tree-of-Thought is defined by search: branches are *executed*, each is *scored*,
and the search *backtracks* to a sibling when a branch fails. What ships is one
`think` stage instructed to write three approaches, one `check-its-work` stage
instructed to argue against them, and one `use-tools` stage that carries out the
survivor once. Three stages, one conversation, one path.

**`answer-more-than-once`** — `spec/loops/answer-more-than-once.yaml`:

> The attempts share a conversation, so they are not independent samples.

and:

> Calling it `self-consistency` would be claiming the statistical property it
> does not have.

That file is admirably honest and it is correct: it **refuses the name**. But
the register then counts it as the criterion's fifth pattern, which is the
sixth line of the criterion's own list — `self-consistency` — awarded to a shape
whose own file says it is not that. The refusal happened in the library and not
in the claim.

## What the tests actually hold

The check that carries AC-5.2 is
`adapters/python/tests/test_loops.py::test_the_specification_ships_the_six_loop_patterns_the_thesis_asks_for`.
It asserts `len(LIBRARY) >= 6` and that six named keys are present. Its sibling
walks each stage graph and asserts a path to `done` exists.

**Existence and termination. Neither test asks whether a shape does what its name
means**, and no test could: a name's meaning is not in the document. So the
register's *"each terminates"* is exactly what is held, and *"six loop patterns"*
is what the criterion asked for and is not what is held.

## And the mechanism the thesis lists separately

`docs/00-THESIS.md` §7.3 enumerates eight portability mechanisms — the things
the Resolver is supposed to be able to reach for when a smaller model has to do
the same job. Number 7:

> **Ensembling.** Self-consistency / best-of-N **with a programmatic selector**;
> an SLM at N=5 can be cheaper *and* better than one frontier call.

The four emphasised words are the missing half, and they are missing in both
places an author could reach for them:

- In `loop:` — no stage can run with a fresh context, so there are no independent
  samples to select over.
- In `teamwork:` — there ARE independent samples.
  `examples/patterns/quorum/` runs three byte-identical readers, each a whole run
  with its own `history`, `Meter` and `Ledger`, and `docs/95-FIX-PLAN.md` §1.18
  is right that this is the sampling half of the shape, arrived at without a new
  field. **The selector is still a model.** The referee's instructions are *"Say
  which two you used and whether they agreed with each other"* — a prompt, not a
  rule. And the pattern's own `workspace.yaml` says what it is for:
  *"you are buying tail latency, not accuracy."*

So §7.3 mechanism 7 is expressible in its sampling half and not in its selecting
half, and the register records neither.

## The correction

**The criterion names techniques, so the names bind.** That is the whole of the
argument above — `answer-more-than-once` is disqualified because the slot it was
awarded is the criterion's own word `self-consistency`. A rule that decides one
shape decides all of them, so here is the same rule applied to every shape in
`spec/loops/`, and to every name in the criterion, with **no figure standing for
either**. Both lists are enumerated because they are different lists, and the
original error was letting one of them count as the other.

**What ships, by file.** `spec/loops/` holds `standard`, `plan-then-do`, `react`,
`reflexion`, `tree-of-thought`, `answer-more-than-once`. That is the list
`test_loops.py` holds — it asserts these keys exist and that each stage graph
reaches `done`.

**What the criterion asks for, name by name:**

| The criterion's name | What answers it |
|---|---|
| **ReAct** | `react`. Ships. Reason/act alternation is the mechanism, expressed as stages. |
| **Plan-and-Execute** | `plan-then-do`. Ships. A plan stage the later stages carry out. |
| **Reflexion** | `reflexion`, **in part** — see below. |
| **Tree-of-Thought** | Nothing. `tree-of-thought` is a prompt shape and its own file says so. |
| **self-consistency** | Nothing. `answer-more-than-once` refuses the name in its own file. |
| **CodeAct** | Refused, with a reason, in `docs/50-NOT-COPIED.md`. A decision, not a shortfall — unchanged by any of this. |

**`standard` answers none of the six.** It is a real and useful shape, and it is
not a named technique: `loops.py` calls it *"what an agent does when nobody says
otherwise"*, and `adapters/python/tests/test_loops.py` records that its opening is
byte-identical to `reflexion`'s because *"`use-tools` adds nothing to the prompt,
and that is exactly what makes `standard` the same as having no loop at all."*
Counting a shape that is the same as having no loop as one of six named patterns
is the same move as counting `answer-more-than-once` as `self-consistency`, and
an earlier draft of this correction made it.

**`reflexion` is the third approximation, and the least self-checking of the
three.** What ships is real: the critique is written in its own stage and the
revision is conditioned on it, which is Reflexion's mechanism at one trial's
depth. What is absent is the thing the technique is built on —
`docs/remediation/F6-reflexion-has-no-memory-across-runs.md`, shipped in this
same change, states it plainly:

> Reflexion the technique is defined by the part that is missing. Its whole
> mechanism is an episodic buffer … What ships here is
> self-critique-then-revise, which is one round of that with the buffer removed.

By this document's own standard — a defining mechanism is absent, therefore the
name is wider than the shape — that is the same finding as `tree-of-thought`'s,
differing in degree and not in kind. And the disclosure is worse rather than
better: `spec/loops/tree-of-thought.yaml` and `spec/loops/answer-more-than-once.yaml`
each say in their own text what they are not, and `spec/loops/reflexion.yaml`
says nothing about the buffer either way. **F6 is the price of that absence; this
row is the record of it.** Refusing the buffer (F6) and claiming the technique
whole (this row, as it stood) cannot both be right, and F6 is the one with the
argument.

**So: two of the criterion's six names ship, one ships in part, two do not ship,
and one is refused.** The register row is amended in this change to enumerate
them rather than to carry a number, because a number is what went wrong here
twice — once when six shapes were counted as six techniques, and once when this
correction's first draft answered that with *"four of six"* by counting
`standard`, which is named for nothing on the list.

## What each of the three would actually need

**Tree-of-Thought needs branch execution and backtracking.** Three things, none
of which exists: a stage that can be entered more than once with a *different*
context rather than a longer one; a per-branch score the run holds rather than
the model recites; and a route back to a sibling branch when the chosen one
fails. Today `follow`'s instruction covers the last case with words — *"say so
rather than switching to another one silently"* — which is the honest thing to
do when you cannot switch.

**Self-consistency needs independent samples and a programmatic selector.** The
samples exist in `teamwork:`, so the missing piece is smaller than it looks: a
way to say *how the answers are combined* that is not a sentence given to a
model. Majority vote over an exact match is the smallest useful one, and
`docs/90-REVIEW.md` records that **majority voting is the worst aggregator
tested** — so the field would have to admit more than one rule, and the day it
admits more than one rule it is a vocabulary and not a flag.

**Reflexion needs a buffer that outlives the attempt, and that is refused rather
than missing.** `docs/remediation/F6-reflexion-has-no-memory-across-runs.md` is
the decision and carries the price. It is the one of the three whose gap is a
*decision* — the other two are unbuilt, this one is declined — which is why the
register row points at F6 rather than describing work.

Neither of the two unbuilt ones is designed here, and neither should be started
before AC-5.1's three missing patterns (F7) are decided, because all of them want
the same absent primitive.

## The price of the correction itself

**A criterion moves from met to partial, and it stops being answerable with a
number.** That is the whole cost, and it is a cost paid in a document rather than
by an author: the shapes do not change, nothing that runs today stops running,
and `tree-of-thought`, `answer-more-than-once` and `reflexion` remain three of
the most useful things in the library for the failures they really do address —
an agent that commits to the first approach it thinks of, a question with one
arithmetic slip in the middle, and an answer nobody read back before sending.

**What the overclaim was costing is the larger figure.** An author reading the
register learns that PACT ships Tree-of-Thought; an author reading
`spec/loops/tree-of-thought.yaml` learns that it does not. We were shipping the
correction in the place only somebody who had already chosen the shape would
read it, and the claim in the place somebody decides whether to choose PACT at
all. That is a T7 breach — a claim wider than what holds — and the register is
the document that exists to catch them.
