# 97 — Seven primitives: what every PACT keyword, and every agent pattern, is made of

**Date:** 2026-11-04, revised 2026-11-10. **Status:** The final list of
primitives for PACT. Nothing in `spec/schema.yaml` changes because of this
document. §9 lists what would have to change for the patterns PACT refuses
today to become buildable.

**What the revision added.** The seven were tested against three complete
inventories, each by a script that fails if anything is left unassigned:
the 569 keywords of the schema, the 342 closed-choice words those keywords
accept (`scripts/primitive-coverage.py`), and the 203 patterns published at
agentic-patterns.com (`scripts/pattern-coverage.py`, §5.4, Appendix B). Each
pattern's construction is typed against a closed kernel of **76 operations**
of the seven (Appendix C), and the 57 patterns that exist as PACT today are
loaded by `pact check`. The seven held. No primitive was added or removed. Six
*operations* on existing primitives were made explicit because a pattern
needed them by name (§5.4). One primitive was **renamed**: Label became
Origin after a reader test (§11) in which two cold readers both took "Label"
for a tag the author chooses. §11 gives the seven in the order to learn them
and reports that test, §12 answers whether the set is Turing complete (yes,
with law 2 revised so an owner may opt a cycle out of the halting guarantee),
and §13 records why this is the final list rather than a fresh start.

**The question.** PACT has 569 keywords in 68 groups (counted by loading
`spec/schema.yaml`, not by reading it). Is there a small set of fundamental
pieces, five to ten of them, that meets two conditions?

1. Every one of those 569 keywords is a particular arrangement of the pieces.
2. Every agentic design pattern, multi-agent topology, tool, workflow, loop,
   condition, hook and capability that has been published can be built from them.

**The answer is seven:**

| Primitive | Its job |
|---|---|
| **Shape** | Data: what form it has |
| **Origin** | Data: where it came from |
| **Store** | State: data that persists |
| **Actor** | Work: anything that can be asked to do one thing |
| **Flow** | Composition: how asks are put together |
| **Check** | Judgment: a decision the checker can read |
| **Allowance** | The boundary: what a part may do, and how much |

The seven come with eight laws that say how they may be combined. The laws are
needed because seven pieces with no rules can build an agent that pays a refund
ten times.

**How this was reached**, so that the result can be argued with rather than
believed:

| Step | What was done | Evidence |
|---|---|---|
| Inventory | Extracted every field of every group in the schema, with its type, choices and help text | §6, Appendix A |
| First proposal | Drafted seven primitives from clusters in the inventory: the five beside Origin here, plus Shape, plus **Hook** | §8 |
| Mechanical coverage | Assigned every keyword the primitives it is built from, using a script that fails if any keyword is left unassigned | `scripts/primitive-coverage.py` |
| Three independent attacks | One reviewer per direction, none shown the others' work: (a) find a keyword the primitives cannot produce, reading the help text and comments rather than the names; (b) find a published pattern they cannot build; (c) find a primitive that is redundant, or two that overlap | §8 |
| Revision | Removed Hook (it is part of Flow), added **Origin** (both coverage reviewers asked for it independently), added the operations the reviewers found missing, wrote eight soundness laws | §2, §4, §8 |
| Pattern catalogue | Built each pattern from the seven, including every pattern PACT currently records as unbuildable | §5, §7 |

---

## §0 What a primitive has to earn

A piece is admitted only if removing it costs something specific. Either of
two costs is enough:

- **Expressive necessity.** Some pattern cannot be built without it.
- **Checkability necessity.** `pact check` gives some guarantee *before anything
  runs* that cannot be computed without it. Examples: "every loop stops",
  "nothing leaves this machine", "every route label has somewhere to go", "a
  refund is paid at most once", "text from a web page never becomes an
  instruction".

The second test is why the answer is seven and not three. Consider
expressiveness alone. Allow an Actor to be an arbitrary program and *every*
pattern becomes trivially buildable: write the pattern as the program. The
actor model needs only *create*, *send* and *become*. But a tree made of opaque
programs is a tree nobody can check. PACT's thesis (`docs/00-THESIS.md`) is
that the author is a support lead editing YAML, and the checker is what stands
between them and an outage.

So the claim this document makes is the stronger one: **every pattern can be
built with the checker's guarantees still intact.** No decision the checker
must prove is hidden inside code. A piece that a smaller set *could* simulate
still earns its place if simulating it would destroy a guarantee.

---

## §1 The seven at a glance

| # | Primitive | In one sentence | What it is closed over |
|---|---|---|---|
| 1 | **Shape** | What form a piece of data has. | scalars, `one of`, records, lists, maps, optional, streams, host-issued references; validate / describe / parse / render |
| 2 | **Origin** | Where a piece of data came from, and where it may go. | origin (customer, person, tool, retrieval, model, teammate, server, reviewed definition); sensitivity; region; propagation through every ask |
| 3 | **Store** | Data that outlives the step that wrote it. | read (also as of a version), write through a merge rule, claim, fork, find, forget |
| 4 | **Actor** | Something that can be asked to do one thing, and answers. | model, program, tool action, person, remote agent; any named Flow |
| 5 | **Flow** | How asks are put together. | ask, then-by-outcome, choose, split/join, await, scope with handlers, starts-when, name |
| 6 | **Check** | A judgment the checker can read. | comparisons, typed comparisons, named detectors, counts and order over the run record, aggregates; all / any / not |
| 7 | **Allowance** | What a part may do, and how much of it. | reach, see, use without seeing, write, start, mediate; quantities counted per scope and per period; passable, never widened |

Read as a sentence:

> **An Actor is asked, in a Flow, with data of some Shape and Origin, read from
> and written to Stores, on the strength of Checks, within an Allowance.**

Every keyword in PACT is one way of filling in that sentence.

The seven fall into four kinds:

| Kind | Primitives | What that means |
|---|---|---|
| Things that run or persist | Store, Actor, Flow | the moving parts |
| Languages the moving parts use | Shape, Check | describe data; decide |
| Metadata the host attaches to every value | Origin | authors and models never write it |
| The boundary around all of it | Allowance | what may happen at all |

The split is deliberate:
- The two languages are small and closed so that the checker can read them.
- Origins are assigned by the host so that a model cannot forge them.
- The boundary is data rather than code, so the checker can prove things about
  it without executing anything.

---

## §2 The seven, one by one

Each primitive gets the same five parts:
- **What it is.**
- **What it is closed over:** its operations and parameters.
- **Keywords built mostly from it.**
- **Why it is not one of the others.**
- **What is lost without it.**

### 2.1 Shape: what form a piece of data has

**What it is.** A description of a value, used in four directions:
- **validate** a value that arrived;
- **describe** the expected value to whoever must produce it: JSON Schema for a
  model's constrained decoding, an MCP `inputSchema`, a form for a person;
- **parse** loose text into it;
- **render** a template into it (`{{run-inputs.x}}` holes, or Jinja with
  conditionals and loops), with the guarantee that nothing filled in is ever
  read as a template again.

**Closed over.**
- **Scalars.** The 14 answer shapes the schema already enumerates (`text`,
  `yes-or-no`, `money`, `number`, `whole-number`, `images`, `audio`, `file`,
  `documents`, `video`, `agent`, `date`, `time`, `date-and-time`), plus the
  value shapes `duration`, `percent`, `size` and `table`.
- **`one of <labels>`.** A closed set of words. This is what makes "every label
  has somewhere to go" provable.
- **Containers.** Records with named parts, lists, maps, optional values, and
  a *failed* marker on an item, because "a failed item is kept, marked failed,
  never dropped" (`stage.combines-by`).
- **`stream of T`** (added in review). An answer that arrives in parts. It is
  what voice, streaming replies and starting work before a plan is finished are
  made of (§2.4, §5). Each part carries a **kind** (answer, reasoning, tool
  call), so a result can be built from answer parts alone (§5.4).
- **digest** (added 2026-11-10). A value's fingerprint, which a Check may
  compare. It binds an approval to the exact ask it approved, and picks a
  deterministic slice of runs for a canary (§5.4).
- **Host-issued references** (added in review): to an agent, a run, a stored
  value or an Allowance. A model can pass a reference along but cannot invent
  one. Today the schema's `agent` answer shape is a plain scalar, so a model can
  write the name of *any* agent. As a host-issued reference, it can only name an
  agent it was handed (law 4).

**Built mostly from it.** `accepts`, `answers-with`, `takes`, `run-inputs`,
`shapes`, `shaped-like`, `question.answer`, `value.shape`, `rows-are`,
`model-can.modality-in/out`, `moment`, `time-zone`, `template-language`,
`answers-with-mode` (which wire route enforces the Shape on a given model).

**Why it is not Check.** Shape and Check are two sides of one idea. Shape judges
one value *before* it exists, and Check judges values *after*. A Check that runs
afterwards could simulate Shape, but then nothing could be told the shape in
advance:
- no constrained decoding;
- no MCP schema;
- no form for a person;
- no static typing of `steps.x.result.amount`.

The cut between them: **a rule about one value on its own is Shape. A rule that
reads other values, the clock or the run record is Check.**

### 2.2 Origin: where a piece of data came from, and where it may go

*Called Label until 2026-11-10. Renamed after the reader test in §11, where
both cold readers took "Label" for a tag the author chooses and both proposed
"Origin". The stamp still records three things: origin, sensitivity and
region. Origin is the one a reader meets first, and the other two are decided
at the moment of origin.*

**What it is.** Information the **host** attaches to every value it holds. The
author never writes it, and a model's output cannot change it.

**Closed over.**
- **Origin.** One of:
  - the customer;
  - a named person, and whether they approved;
  - a tool's output;
  - retrieval;
  - the model's own words;
  - a teammate;
  - a server's published prose;
  - the reviewed definition (text an author wrote and an owner approved);
  - the clock.
- **Sensitivity.** A category the value belongs to: card number, personal data,
  "a student's name". Set by a named detector or by `hides:`.
- **Region.** Where the value may live (`data-stays-in`).
- **Placeholder** (added 2026-11-10). A hidden value may travel as a
  host-issued reference that an Actor can pass along but not read; the host
  restores the real value only for an Actor whose Allowance says *use without
  seeing*. This is PII tokenisation and the credential broker (§5.4).
- **Propagation.** Anything computed from labelled values carries the
  combination of their labels. A model's answer carries the labels of
  everything in its context; a summary of a tool's output is still tool output.
  A label can be removed only by a *declared* rule. For example, redaction
  removes the card-number label by removing the card number.

**Built mostly from it.** These keywords exist in PACT today, spread across five
groups:

| Keyword | What it says | What that is, in Origin terms |
|---|---|---|
| `state.never-from` | "tool output, retrieval, the customer, a teammate" may never write here | a test on origin |
| `question.shows` | values appear "as quoted data in their own box, never folded into your wording" | data is not instruction |
| server prose in a tool snapshot | stays "fenced off and still cannot instruct this agent" | an origin rule |
| `hides`, `redaction` | some readers may not see some values | sensitivity |
| `always-keep: anything a person approved` | a person's approval survives tidying | selection by origin |
| `tidy-step` `drop-parts` | drop "the model's own thinking, tool results" | selection by origin |
| `turn.from` | who wrote an entry in the conversation | origin, stated outright |
| `data-stays-in` | where data may live | region |
| `allow-egress` | the half that is about what *data* leaves | flow of labelled data |

**Why it is not Allowance.** This is a well-known distinction in security.
Allowance is **access control**: it decides *who may do what*. Origin is
**information-flow control**: it decides *where data may go*. Access control
alone cannot stop a part that may read a secret from handing it to a part that
may write to the outside world. Each step is permitted, and the leak happens
anyway. Only a label that travels with the data, through every computation, can
see that.

**Why it is not Shape.** A label written into a Shape is written by whoever
produced the value. For a model's answer that is the model, so the model could
forge it.

**Why it is not Check.** A Check reads a value at one moment. A label has to
*propagate* through every ask, which a judgment at one point cannot do.

**What is lost without it.** Three guarantees:
- "One poisoned web page never becomes a remembered fact" (`never-from`).
- "Text from a tool is never read as an instruction" (the dual-model and
  CaMeL-style defences against prompt injection, §5.2).
- "A hidden name never reaches the logs through the tool that summarised it."

PACT makes all three promises today, each by its own mechanism. None of the
three can be checked across the whole tree.

**Its count is low on purpose, and that is evidence of a gap, not of a weak
primitive.** Origin is the main ingredient of only 7 keywords, because PACT
encodes origin piecemeal: a `never-from` list in one place, a fenced box in
another. Those keywords hold the format's security promises, so they are the
most consequential ones it has.

### 2.3 Store: data that outlives the step that wrote it

**What it is.** A named cell or collection, with a Shape, six parameters and six
operations.

**Parameters.**

| Parameter | Values | PACT keywords it carries |
|---|---|---|
| scope | step, turn, conversation, run, flow, team, workspace; optionally one per key | `lasts`, `kept-per`, `same-request-key-across`, `counted-per` |
| lifetime | until a moment, or until an event | `kept-for`, `forget-after`, `stops-being-true-when` |
| durability (added in review) | none, checkpoint, durable-execution | `workspace.durability` |
| merge rule | the schema's own `combine-rules`: keep-all, keep-the-latest, merge, add-up, vote, top-n by a field (`spec/schema.yaml:5561`); or a pure program. Under a split, only rules whose result does not depend on arrival order (keep-all, add-up, vote, top-n) are safe. The checker flags keep-the-latest and merge there, because which branch wins would be a race. | `combines-by`, `comes-from` |
| versions | every write may create a version with a digest | `based-on: name@version`, `stage.version`, `tool-snapshot-digest`, `drift` |
| pins (added in review) | pinned entries are never removed, including when a conversation is shortened | `always-keep`, `survives-shortening` |

**The six operations.**

| Operation | What it does | What it is the whole of |
|---|---|---|
| **read** | Any path: `input.x`, `steps.x.result`, `remembers.x`, `latest-update`; or the value *as of* a version or date | every binding in the format; `stage.version` "in effect on that date" |
| **write** | Goes through the Store's merge rule | `remember-as`, `remembers`, `watch.writes-to`, every stage's result |
| **claim** | Insert-if-absent, or compare-and-swap, optionally with a lease that expires; *take* is a claim followed by a forget | `same-request-key` (exactly-once), a mutex, a claimed work item, an auction award, a queue |
| **fork** | A copy-on-write branch, or a snapshot. A branch is discarded when its scope ends. The only thing that leaves it is what its join writes to an outer Store, so a losing search branch leaves nothing behind. | checkpoints, independent samples, search branches, and "a stage entered again with a *different* context rather than a longer one", which is the primitive `docs/70-PRODUCTION-GAP-REGISTER.md` says is missing |
| **find** | By key, by words, by meaning, reranked, at most N results | `knowledge:` (`looked-up-by`, `split-by`, `passages-at-most`, `embedded-by`, `reranked-by`) |
| **forget** (added in review) | Remove an entry or let it expire | `kept-for`, `stops-being-true-when`, the `forget` stock action, `drop-parts` |

**Stores the host provides.** Most of the format's special-looking things turn
out to live in one of these.

| Host Store | What it holds | PACT keywords that read or write it |
|---|---|---|
| **the conversation** | the context window: merge rule keep-all, pinned entries, a size limit | `turns:` (its starting contents) |
| **the run record** | every ask and answer, every approval, and who gave each, appended | `must-call-before`, `not-the-same-as`, `population: past-runs` |
| **the inbox** | outside arrivals, each with a correlation key, held until something listens | `counts-events-from` (`whenever-they-arrived` keeps what arrived earlier; `this-wait` counts only from now) |
| **the run registry** | open runs, by concurrency key | `if-still-running:` |
| **the clock and calendar** | `now`, and the workspace's working days and holidays | `every:`, deadlines, `counted-in: business-days` |
| **the directory** | people, roles, and how to reach each | `asked-of`, `escalates-to`, `owned-by` |
| **the catalogue** | models and their figures, each with where the number came from | model selection, `needs:` |
| **the definition** | the tree itself, versioned | see below |

The definition Store has the largest consequences. It is read in two phases:
- **At load time** (law 8):
  - `values:` are substituted (`spec/schema.yaml:1199-1208`: "deliberately NOT a
    variable");
  - `based-on:` overlays are merged;
  - bundles are mounted;
  - the checker runs.
- **During a run**, writes to it are what learning, meta-agents and skill
  libraries do. `release:` and `owners:` govern those writes, and law 5 limits
  them.

**Why it is not the others.** Actors answer and forget. Flow is control, not
data. And Store is not Origin: a Store is a *place* and an Origin is a *property of
a value*, which moves with the value between places.

**What is lost without it.** All of these:
- memory across steps or across runs;
- exactly-once;
- the blackboard;
- search trees;
- retrieval;
- durable waits.

### 2.4 Actor: something that can be asked to do one thing, and answers

**What it is.** A participant in the UML sense, a role played by a person or a
system. It is not the Hewitt sense of a process with a mailbox; a mailbox is a
Store plus an `await` (§3). Every Actor has the same outline. Actors differ in
one thing only: how they decide.

| Kind | How it decides | PACT keywords |
|---|---|---|
| model | by sampling; nondeterministic | `model`, `catalog`, `settings`, `needs`, `voice.hears-with/speaks-with`, `embedded-by`, `summarised-by`, `graded-by` |
| program | by computing; pure, deterministic or not | `programs`, `program`, `engine`, `determinism`, `fuel`, `decided-by`, `projects-with`, `run-code` |
| tool action | an outside system decides | `tools`, `actions`, `resources`, `connect`, `url`, `method`, MCP, A2A |
| person | a human answers; slow and authoritative | `questions`, `asked-of`, `escalates-to`, `reviewed-by`, `owned-by` |
| remote agent | someone else's agent decides | `resource-kind: a2a-agent` |
| composite | a named Flow (§2.5) | `agents`, `workflows`, `loops`, `team`, `published-as` |

**The outline every Actor has.**
- **Signature.** The Shapes it takes and answers with. Either side may be a
  stream: inputs that keep arriving, answers that arrive in parts.
- **Effect class.** One of none, reads, writes, spends or irreversible. It comes
  with *how to undo it* (`undone-by`) and *how to ask whether it already
  happened* (`status-check`). A Check may read it, and may read the Actor's
  declared **write set** (added 2026-11-10), which is what lets a Flow run
  reads-only asks together and make overlapping writers wait (§5.4). For a composite, the effect class is **computed**
  as the worst class among its steps and is never declared (law 1).
- **May it park?** Whether it can wait on a person or an event. A `run-code`
  snippet may only call Actors that never wait.
- **Figures.** Cost, latency, context size, capabilities and benchmark scores.
  Each carries where the number came from (`model-cost`, `model-speed`, `figure`,
  `provenance`).
- **Identity.** Who acted, recorded in the run record. Added in review:
  - **on whose behalf** it acted;
  - **how strongly** its identity was established, which `needs-signature`
    requires to be a fresh sign-in.
- **Location.** Where it runs (`served-by.region`), so that `data-stays-in` can
  be checked against it.
- **Settings.** How it is asked: `temperature`, `thinking`, `instructions`,
  `says`, `turns`.

**References to an Actor come in three strengths.**
1. **Concrete.** A name, as in `uses: payments`.
2. **Chosen at run time from a closed set.** For example, `call:
   steps.pick.result` together with `may-call:`, or a `decided-by:` program
   together with `may-go-to:`.
3. **By requirement.** `needs:` on a model; `interface:`, `implements:` or
   `chosen-by:` on a tool, skill or knowledge set. These are resolved by a
   Check over the candidates in a Store (the catalogue, or the definition),
   followed by a preference order (`prefer: cheapest`).

**Model selection and interface binding are the same operation.** A fourth form,
**instantiate**, makes an Actor from a definition *value* during a run. This is
what `may-start: narrowed-new` and `run-code` do, and it is governed by law 8.

**What is lost without it.** Actor is the only source of effects; nothing
happens in the world without asking one. The effect class also lives here, and
it is the input to the two most important proofs PACT makes: exactly-once, and
egress.

### 2.5 Flow: how asks are put together

**What it is.** The composition primitive. It says which Actor is asked when,
with what, and what happens next. It is closed over eight operators.

| Operator | What it does | PACT keywords |
|---|---|---|
| **ask** | Ask one Actor, with inputs bound from Store paths. Wait for the answer, or detach and get a run reference back. | `does: think / use-tools / call / run-code / ask-someone / answer`, `call`, `bind`, `waits-for-result`, `version` |
| **then** | Every ask ends in a labelled outcome. The next step is chosen by that label, either a sibling or `done`. Cycles among siblings are allowed; nothing jumps into or out of a nested block. A run may also resume at a label from a fork, which is "time travel". | `then`, `outcome`, `starts-at`, `steps` |
| **choose** | Pick one label from a closed `one of`, using rungs tried in order: written rules (Checks), then Actors cheapest first, then a person. | `does: decide`, `chooses-between`, `rung`, `route-rule`, `if-unsure-below`, `if-it-disagrees` |
| **split / join** | Start fixed branches, one branch per item of a list, one per part of a stream, or one per entry of a Store that is still growing. Join by waiting until *k* arrivals pass a Check, until a Check over the combined result holds, until a deadline, or until the set is quiet and nothing it started is still running. Then decide what happens to the branches still running: cancel them, let them finish and ignore them, or detach them. Combine the answers with a Store merge rule. | `does: together / each`, `over`, `identified-by`, `ordered-by`, `combines-by`, `teamwork.waits-for`, `enough-is`, `gives-up-after`, `starts` |
| **await** (added in review) | Pause until a Check over Stores holds: something arrived in the inbox with this run's correlation key, a person answered, a moment passed, a value changed. Has a deadline. This is Temporal's *signal* and the π-calculus *receive*. | `heard`, `answer-within`, `nobody-answered`, `counts-events-from`, `only-when`, `turn-ends-after` |
| **scope** | A region with its own Store fork (a shared or an isolated conversation), its own Allowance, its own meters (which can be paused, for `paused-during`), and **handlers**. A scope, or a run reached through its reference, can be **cancelled**. | `if-it-fails`, `interceptors`, `policy`, `context-policy`, `redaction`, `watch`, `limits` on a stage |
| **starts-when** | A named Flow's trigger: a Check over Stores becomes true (an arrival, a clock match, a Store change). It carries a concurrency key and a rule for overlap: start, queue, join, cancel-previous, skip, or stop. Every trigger draws from an Allowance (law 2). | `ports`, `every`, `if-still-running`, `if-missed`, `per-row-of`, `runs-every`, `review`, `reminds-at`, `milestones` |
| **name** | A Flow with a Shape signature *is* an Actor. | `agents`, `workflows`, `loops`, `published-as` |

**Handlers** are where the format's hooks, interceptors, policies, failure plans
and limits all live, and they are why there is no separate Hook primitive. A
handler sits on a scope and receives five kinds of thing from the steps inside
it:

| Moment | A handler may | PACT keywords that are exactly this |
|---|---|---|
| *before an ask* | change the request; hold it for a person and resume on yes; send it to another Actor from a closed list; refuse it | `needs-a-person`, `ask-a-person` rules, `interceptor.may: change-the-request / send-elsewhere / stop-the-run`, `redaction`, `asks-to-run`, `asks-to-connect`, `if-it-changes` |
| *a part of a streamed answer* | look at it; cut the answer off, recording what was actually delivered | `may-be-interrupted`, `first-reply-within`, `per-word-under` |
| *after an answer* | change the answer; hide values; record it; refuse this one answer and keep waiting for others (an approver who may not answer under `not-the-same-as`) | `change-the-answer`, `hide-values`, `projects-with`, `watch`, `remember-as` |
| *a failure* | try again; call a backup; carry on with set values; undo the scope, newest first; ask a person; wait for a new version | `if-it-fails.after-that`, `backup`, `carry-on-with`, `undo`, `new-version-of`, `checks-at-most` |
| *an Allowance running out* | anything from the failure list | `when-it-runs-out`, `if-it-still-does-not-fit` |

The schema's interceptor address, `<part>.<thing>.<moment>`, has three parts:
- **part**: *which scope* (`session`, `turn`, `step`, `action`);
- **thing**: *which kind of ask* (`message`, `tool`, `delegate`, `model`);
- **moment**: *when* (`before`, `after`, `failed`, and so on).

A workspace-wide policy is a handler on the outermost scope, which encloses
every agent. So `applies-to: every-agent` is not a special case; it is the
outermost scope.

This is the algebraic-effects reading of hooks:
- every ask is an *effect*;
- every handler is installed by a scope;
- the nearest handler sees an effect first;
- `runs-at:` orders the handlers on one scope.

**The rule that keeps Flow and Allowance from overlapping:** a handler *acts*,
and an Allowance never does. An Allowance only answers "may I?". When the answer
becomes no, it ends the ask with an outcome, and the nearest handler receives
that outcome.

**The rule that keeps Flow from overlapping itself:**
- A failure on the path the author wrote is an **outcome label** and routes like
  any other label.
- A failure that cuts across many steps belongs to a **handler**: a ceiling
  running out, a policy refusal, a deadline set from outside.

**Why it is not the others.** Composition is irreducible: Store is data, and
Actor is a single ask. The checker's proofs about control also need control
written as Flow rather than hidden inside an Actor. Those proofs include: loops
exit, splits join, labels are covered, and every handler around a payment can be
listed.

### 2.6 Check: a judgment the checker can read

**What it is.** A small, decidable language. It answers yes or no, or picks a
label, and it returns a verdict with a reason.

**Closed over.**
- **Comparisons** over Store paths and constants: `more-than`, `less-than`,
  `is`, `is-one-of`, `contains-any-of`, `is-empty` (`when-this`).
- **Typed comparisons.** Money compared in its currency. Durations.
  `{now-plus: 14 days}`. Business days on the workspace calendar (`comparand`,
  `moment.counted-in`).
- **Named detectors** (added in review). A closed set of recognisers: card
  number, bank account, email address, phone number, social security number.
  This is exactly the set that `redaction.hide` and the interceptor sentences
  accept already. When a detector matches, the host stamps the value sensitive (Origin).
  An author may **declare** further detectors (added 2026-11-10): a pattern
  with a name, matched the same way, for threat rules and trigger phrases
  (§5.4).
- **Origin tests** (added in review). For example, "this value's label includes
  tool output". These are what `never-from` reads.
- **Counts and order over the run record.**
  - "Called more than *n* times in one run".
  - `must-call-before`.
  - Distinct entries among the last *k*, added in review for detecting livelock,
    as in a handoff that bounces back and forth.
- **Reachability over the definition**, as in `available-when:
  this-agent-has-helpers`.
- **Schedule matches** on the clock, as in `every: weekday mornings at 9`.
- **Aggregates over a set:** the share passing, percentiles, broken down by a
  field (`must-pass`, `sliced-by`, `measured-at`, `accept-when`, `scores`,
  `feel`).
- **Combinators:** all, any, not.

**Judged checks are not Checks.** Each of the following is an **Actor that is
asked**, after which a Check reads its answer:
- a model grader (`judged:` with `graded-by:`);
- a DeepEval metric (`metrics:` with `threshold:`);
- a carried program (`eval-rule.program`);
- a person's review (`question.checked-by`).

This keeps Check itself decidable. Selection formulas that do not fit the closed
language can be written as pure programs, used as merge rules or selectors.
Examples are the UCT rule in tree search and time-decay ranking. The checker
treats such a program as deterministic but opaque. Law 6 lists the decisions
that may never be opaque.

**Built mostly from it.** `when-this`, `comparand`, `until`, `only-when`,
`route-rule.when`, `needs`, `accept-when`, `eval-rule`, `must-pass`,
`keep-only-if`, `drift`, `undo-where`, `available-when`.

**Why it is not an Actor running a pure program.** A program could compute every
one of these. But then the checker could not:
- prove that a set of rules covers every case (`amount > 200` / `amount ≤ 200`);
- prove that a loop's exit is reachable;
- evaluate a policy's blast radius without running author code.

A program would also need a code runtime on every one of the seven target
frameworks in order to give the same answer on each. Check is the part of the
format that is *read*, not run.

**The cut between Check and Allowance.** Two cold readers found this the
hardest line to draw (§11), so here it is in one rule. An Allowance is a
*meter or a door*: a quantity the host counts down as a part spends it
(steps, calls, money, time, items), or a reach that is open or shut. A Check
is a *question about values at one moment*. If deleting the line would let
the agent do more, it was an Allowance. If deleting it would change which way
the agent goes, it was a Check. So `steps-at-most: 50` is an Allowance,
`amount more-than 200 USD` is a Check, and `answer-within: 4h` is an
Allowance of time on a wait, with what happens when it is spent being a
handler (Flow).

### 2.7 Allowance: what a part may do, and how much of it

**What it is.** The boundary: a grant of authority, with or without a quantity.
A permission is just a quantity that is either zero or unlimited, so the two are
one primitive and obey the same laws.

**Permissions.**

| Permission | PACT keywords |
|---|---|
| reach an Actor or an address | `uses`, `may-use`, `may-call`, `may-go-to`, `actions`, `unlisted-actions`, `allow-egress`, `available-when`, `auth`, `credential-reference` |
| see a value with a given Origin, per reader (the model, logs, a person, a role, a tool) | `hides`, `redaction`, `shows`, `inspects` |
| use a value without seeing it | `hides: [the-ai]`: "the original is put back only at a write that needs it" |
| write to a Store, or to part of the definition | `never-from`, `owners`, `owned-by`, `locked`, `locked-until`, `bundle.brings`, `may-improve-on-its-own`, `needs-a-person-to-approve` |
| start new agents | `may-start`, `starts-at-most`, `nests-at-most` |
| mediate (a handler's powers) | `interceptor.may`, `applies-to` |
| be reached from outside | `who-can-reach-it`, `signed-with` |

**Quantities.** Allowances can limit:
- steps, tool calls and attempts;
- tokens, money and wall-clock time;
- items, concurrent runs and nesting depth;
- uses per period, and how far the wording may drift.

Each limit is counted per run, per connection, per team or per key, and may
reset every period. Its meters can pause while a scope waits on a person. The
keywords: `limits`, `program-fuel`, `cycle-limits`, `at-most`, `checks-at-most`,
`items-at-most`, `at-once-at-most`, `counted-per`, `resets-every`,
`paused-during`, `first-times`, `divides-the-budget`, `shares`,
`passages-at-most`, `costs-about`.

**Allowances are values** (added in review). An Allowance is a host-issued
reference, so a Flow can hold one, split it and pass it on:
- a parent chooses at run time which tools a helper gets;
- an auctioneer hands the winner a budget equal to its bid;
- a team member that claims more work draws more from a shared pool.

Every such operation conserves the total, so the most any part can ever hold is
still the static grant the checker read at load (law 5). Grants can also be
**revoked** or **expire** (`locked-until`, `tool-snapshot-max-age`, credential
rotation), and a grant may be **revoked for a period** (added 2026-11-10): a
tool whose last ten asks failed loses its Allowance for five minutes, and a
trigger that just fired may not fire again until its cooldown passes (§5.4).

**Why it is not a handler that refuses.** A handler could simulate an Allowance.
But a handler is a procedure and may contain a model, so proving what it refuses
is undecidable. Each of the following is a property of the tree that the
checker reads off Allowance data without running anything:
- "Nothing leaves this machine."
- "This agent's blast radius."
- "A helper never has more than its parent."
- "Every loop is bounded."

Allowance is the clearest case of a primitive justified entirely by what it
lets the checker prove.

---

## §3 How the familiar things are built

None of these is a primitive. Each row is a recipe.

| Thing | Built as |
|---|---|
| **Agent** | A named Flow (and so an Actor) whose body is the agent's loop. Its instructions and turns are the starting contents of its conversation Store, and `uses:` is its Allowance. |
| **Loop** (`loops/*.yaml`) | A named Flow of asks with `then:` cycles. Every cycle is metered (law 2). |
| **Tool-use loop (ReAct)** | Ask the model. On `used-a-tool`, ask the tool it named: a run-time Actor reference, which must be inside `may-use`. Go back to the model. On `answered`, finish. |
| **Condition** | A Check. |
| **Hook / interceptor** | A handler on a Flow scope, with powers from an Allowance. |
| **Trigger / port** | `starts-when` on a named Flow: a Check over the inbox or the clock. |
| **Capability** | An Actor reference, plus the Allowance that lets a part reach it. |
| **Tool** | An outside Actor (a tool action) with a signature and an effect class. |
| **Workflow** | A named Flow that no agent owns. |
| **Team** | Split/join over member Actors. Dividing the budget is passing Allowance values on. |
| **Memory** | A Store with a scope, a lifetime and a merge rule; its writes are tested on origin Origins. |
| **RAG / knowledge** | Store `find`, with an embedding Actor and a reranking Actor. Every passage carries the origin Origin *retrieval*. |
| **Context compaction** | A handler on "before a model ask". Its Check is "the conversation is over 90% full", and it writes a shorter conversation that keeps pinned entries. |
| **Human approval** | A *before* handler asks a person Actor and writes the answer to the run record. The Allowance's condition is a Check over that record. |
| **Question with escalation** | Ask a person Actor, then await with a deadline. A handler on `nobody-answered` asks the next people on the list. |
| **Budget / limit** | An Allowance quantity. Running out ends the ask with an outcome, which the nearest handler receives. |
| **Exactly-once** | A Store `claim` on the request key, at the declared scope. |
| **Undo / saga** | The run record of completed writes, plus a handler that asks each write's `undone-by` Actor, newest first. |
| **Eval suite** | A Flow over a Store of cases (or of past runs) that asks the Actor under test and applies Checks to the answers. `runs-every` is `starts-when` on the clock. |
| **Learning** | A scheduled Flow (step by step below). |
| **Template / `based-on:`** | A versioned read of the definition Store at load time, merged with an overlay. |
| **Interface** | An Actor reference by requirement. |
| **Variant** | `choose` between alternative bodies, using a Check over the model that was resolved. |
| **Bundle** | A load-time read of someone else's definitions, limited by an Allowance over which kinds it may bring. |
| **Watch** | An *after* handler that writes to a file-backed Store. A write stamped as the customer's words is refused there. |
| **Voice** | A Flow of streaming Actors: speech-to-text, then a model, then text-to-speech. Barge-in is split {speak, await "the person started talking"} joined on first, cancelling the rest, with what was actually spoken recorded. |
| **Streaming reply** | An Actor whose answer is `stream of text`. A handler fires on each part. |
| **Message / mailbox** | An entry in a Store. A mailbox is a Store plus an `await` on it, which is how the Hewitt actor model is derived. |
| **Event** | A write to a Store (the inbox, the run record or the clock) that some `await` or `starts-when` is waiting for. |
| **Identity / principal** | A property of an Actor, recorded in the run record. |

The learning Flow, step by step:
1. Ask a reflector Actor to propose a change.
2. Check that the change touches only what the Allowance permits.
3. If the change is in `needs-a-person-to-approve`, ask a person.
4. Run the eval Flow.
5. Check `keep-only-if` and `drift`.
6. Write the change to the definition Store.

---

## §4 The eight laws

Seven primitives with no rules can build unsafe agents. Each law names the
unsafe agent that exists without it. The reviewers found laws 2, 3, 4, 5 and 8
as concrete holes in the first draft (§8).

1. **Closure.** A named Flow with a signature is an Actor. Its effect class is
   the *worst* effect class of anything it can ask, and it is computed, never
   declared.
   *Without it:* a workflow that pays money is published as `reads-only`, and
   every caller skips the exactly-once machinery.

2. **Termination, unless an owner says otherwise.** Every cycle is metered by
   an Allowance, written by the author or supplied by default. Every split has
   an item ceiling. Every `starts-when` draws from an Allowance. Nesting is
   bounded. The checker builds the graph of which Flows start which others,
   using each one's Store write set, and requires every cycle in that graph to
   be metered too. A ceiling may be a Store value, but never one that the
   metered cycle itself can write, or a loop could raise its own ceiling and
   the meter would be a fiction. An owner, and only an owner, may mark one
   cycle `unbounded` through `release`; the checker then records, as a named
   finding on the load report, that the halting promise is not made for that
   tree, instead of refusing it (§12).
   *Without the last clause:* Flow A writes Store S, which starts Flow B, which
   writes S, which starts A. Every individual loop is bounded and the system
   never stops.
   *What PACT does today:* the Python harness supplies `DEFAULT_STEPS = 8` when
   the author writes no `steps-at-most`, so that "a bound is never absent"
   (`adapters/python/src/pact_adapters/ir.py:33-36`). But a host whose loop is
   not PACT's carries the ceiling only when the author wrote it (`ir.py:516-520`).
   And `spec/loops/standard.yaml` loops `work → work` with no `at-most`. The law
   holds on PACT's own harness and depends on the host elsewhere.

3. **Exactly-once survives repetition.** Some asks have effect class *spends* or
   *irreversible*. Any such ask inside a retry, a repeat, a fork or a split must
   carry a claim key that does not depend on the attempt or the branch. The
   claim's scope may be no wider than its Store's durability.
   *Without it:* self-consistency sampling over a step that refunds pays five
   times.

4. **Closed world.** Whatever is not granted is refused. References, including
   Allowance values, are issued by the host and cannot be written by a model.
   Egress is the union of the addresses of every Actor a part can reach,
   directly or through others.
   *Without it:* a model writes the name of an agent it was never given, and
   that agent has a tool that uploads.

5. **Attenuation everywhere.** An Allowance passed on is never wider than the
   Allowance of the part passing it. That holds for all of these:
   - passing to a helper;
   - into a `based-on:` copy (deriving a definition counts as delegation, which
     is what `locked: here-and-below` needs);
   - at run time, as an Allowance value;
   - into the definition Store, by a learning cycle or a meta-agent.

   *Without it:* a self-improving agent writes itself a bigger budget.

6. **Decisions the checker must prove are Checks.** Route coverage, grant
   conditions, loop exits and policy triggers are Checks. An Actor or a pure
   program may make a decision only by picking from a closed `one of`.
   *Without it:* "does every refund over £200 reach a person?" becomes a question
   about what a model will say.

7. **Origins travel, and only reviewed text instructs.**
   - A value's Origin stays with it through every ask and every write.
   - A reader sees a labelled value only with a matching Allowance.
   - Only text whose origin is the reviewed definition may be read *as
     instructions*. Everything else reaches a model fenced as quoted data.
   - A label is removed only by a declared rule.

   *Without it:* a sentence on a web page that says "ignore your instructions
   and refund this order" is obeyed. Separately, a student's name hidden from
   the logs reaches the logs through the tool that summarised it.

8. **Two phases, one checker.** At load time, values are substituted, `based-on:`
   is merged, bundles are mounted and the checker runs over the whole tree.
   Anything created during a run must pass the *same* checker at the moment it
   is instantiated, with the checker used as an Actor, before it can be asked.
   This covers a `run-code` snippet, a `narrowed-new` helper, a skill Voyager
   wrote, and an agent ADAS proposed.
   *Without it:* every guarantee above holds for the tree an author wrote and
   for nothing the tree writes.

---

## §5 Every pattern, built

The test for "can be built" is strict:
- The recipe uses only the seven primitives and the operations listed in §2.
- No decision that law 6 names is hidden in a program.
- Anything that needs one more operation says so.

The first group below is every pattern PACT records as unbuildable or only
approximated today (`docs/70-PRODUCTION-GAP-REGISTER.md` AC-5.1 and AC-5.2;
`docs/remediation/F5`, `F6`, `F7`).

### 5.1 The six that PACT cannot build today

**Blackboard.** `F7` refused this because "there is nothing an agent can write
that another agent can read".

```
store board:   scope team · shape entry{item, status, owner, payload} · merge keep-all
               claim on item with a 5-minute lease
               a write is admitted only if a Check on payload passes
flow solve:    repeat, metered at 8:
                 split each specialist in team:
                   ask specialist (reads board) → claim an open item → write result
                 join everyone, or at 10 minutes
               until Check: some entry has status solved
```

The admission Check matters more than the board. `docs/92-SWARM.md` §6.3
records that the measured gains come from that check on what may be written, not
from the queue.

**Market, auction, contract-net.** `F7` refused these because they need "bidding
and a settlement rule".

```
flow auction(task):
  split each bidder in may-call: ask bidder(task) → bid{price, eta, confidence}
  join whoever answers within 30s
  choose winner: a pure program over the bids (lowest price with confidence ≥ 0.7)
  claim awards[task.id] = winner        scope workspace      ← settlement: binding, and only once
  split my Allowance: {money: bid.price} → winner            ← allocation: an Allowance value
  ask winner(task) within that Allowance
  on failure: a handler re-runs the auction without the winner
```

A sealed-bid auction adds one Origin: each bid is visible only to the
auctioneer, never to the other bidders.

`F7`'s real objection still stands, and nothing here removes it. Models are
poorly calibrated about their own cost and their own chance of success
(`docs/93-GAPS.md` §0), so the bids may be noise. That objection is about
whether the pattern is *worth building*, not whether it *can* be built.

**Tree-of-Thought with real search and backtracking.** `F5` says real
Tree-of-Thought "would need a stage to execute more than once with different
context".

```
store frontier: scope flow · list of {thought, score, snapshot} · merge top 3 highest by score
flow tot: repeat, metered at depth 4:
  split each node in frontier:
    scope fork(conversation from node.snapshot):    ← a different context, not a longer one
      ask model "propose 3 next steps" → children
      split each child: ask evaluator(child) → score
  join everyone → write frontier                    ← pruning is the merge rule
until Check: best score ≥ 0.9
```

Backtracking is not a special move. A sibling that lost one round stays in the
frontier, and it wins the next round if the branch that beat it scores badly.
Depth-first search with an explicit stack uses `claim` followed by `forget`
(take).

**Self-consistency with a programmatic selector.** `F5` says the shipped shape
fails because "the attempts share a conversation, so they are not independent
samples".

```
split 5 times: scope fork(conversation from one snapshot): ask model
join everyone; combine answer by vote          ← or by a pure program
```

Independence comes from forking all five from one snapshot. The selector is the
merge rule.

**Reflexion with an episodic buffer.** `F6` says "the episodic buffer the
technique is built on is absent".

```
store lessons: scope workspace · one per task-kind · kept for 90 days · merge top 5 latest
               never-from: tool output, the customer
flow attempt: repeat, metered at 3:
  ask actor (reads lessons) → answer
  ask evaluator → verdict
  on verdict fail: ask reflector → write lessons
until Check: verdict passes
```

`F6`'s own objection is that a remembered lesson is "a model-authored skill with
no review gate". Law 7 answers it. A lesson carries the origin Origin *the
model's own words*, so it reaches the next attempt fenced as data, not as
instruction, unless a person has reviewed it.

**Gap-directed fan-out over a claimable evidence board.** This is the pattern
`F7` prices at "+12.7 pts at 8 workers". Build it as the blackboard above, with
two changes:
- Workers are started by `starts-when` on each new gap written to the board.
- The final join is "quiet, and nothing it started is still running".

The orchestrator reads only the board's summary, never a worker's transcript.
That is what keeps its context under the measured 21.5K tokens.

### 5.2 Published patterns

| Pattern | Recipe |
|---|---|
| Prompt chaining | Flow `then` across model asks, with a Check gate between them |
| Routing | `choose` by rungs: rules, then a classifier Actor, then a person |
| Parallelisation (sectioning) | Split fixed branches, join everyone, combine with merge |
| Parallelisation (voting) | Split N identical asks from one fork, join everyone, combine with vote |
| Orchestrator–workers | Ask a planner for a list of subtasks. Split each, with the Actor chosen per item from `may-call` and an Allowance value per worker. Join, then ask a synthesiser |
| Evaluator–optimiser, Self-Refine, CRITIC | Repeat {ask the generator; ask a critic, or a tool for CRITIC} until a Check passes, metered |
| Autonomous agent | The ReAct Flow, with Allowances on steps, tokens, money and time |
| Andrew Ng's four (reflection, tool use, planning, multi-agent) | The rows above |
| Plan-and-Execute | Ask a planner and write the plan to a Store. Split or sequence over the plan. A re-plan handler runs on failure |
| ReWOO | Ask a planner for a plan with placeholders. Fill them from tool answers without involving the model. Ask the solver once |
| LLMCompiler (a dependency graph of tool calls run in parallel) | The planner *streams* tasks into a Store. A `starts-when` per task waits for "all its dependencies are written" and claims the task. Join when the set is quiet and nothing is running. Tasks start before the plan is finished |
| LATS / MCTS | Tree-of-Thought above, plus a visits-and-value Store merged by add-up (back-propagation) and a pure program for the selection rule |
| Graph-of-Thoughts | Tree-of-Thought with an aggregating step: ask an aggregator over several frontier entries and write one result |
| Mixture-of-Agents | Layered split/join. Each layer's asks read every answer from the layer before, out of a Store |
| CodeAct | Ask the model for code. Instantiate it as a program Actor in a sandbox (`run-code`, `runs-in`, `fuel`; law 8). Return to the model |
| Voyager skill library | Ask the model to write a program. Ask the sandbox to test it. Check the tests pass. Write it to the definition Store (Allowance: programs only, pure, wasm). Later asks may name it |
| ADAS / meta-agent search | Write candidate agent definitions to the definition Store, each checked at instantiation (law 8) and narrowed (law 5). Run the eval Flow on each and keep the best |
| DSPy / GEPA prompt optimisation | The learning recipe in §3, with proposals limited to `phrasing` and `examples` |
| MemGPT / Letta | Core memory is a small pinned Store inside the conversation. Archival memory is a workspace Store with `find`. The Store operations are offered to the model as tool actions. Paging is the compaction handler |
| Generative Agents memory stream | An append-only Store. `find` ranks by a pure program over recency × importance × relevance. Reflection is `starts-when` "importance added since the last reflection is over a threshold" |
| Self-RAG, CRAG, agentic RAG | `find`, then ask a grader, then `choose`: answer, search again with a rewritten query, or search the web. Metered |
| Magentic-One | Task ledger and progress ledger as Stores. An inner repeat asks the orchestrator for {done?, progressing?, next speaker, instruction}. A stall counter lives in a Store, with a pure program for the leaky decay. When a Check says stalls exceed 2, re-plan |
| Handoff / swarm | An ask ends in the outcome label `hand-to:<agent>`, and Flow routes by it. The conversation Store is shared, not forked. The run registry records who owns the conversation now, so the next arrival goes there. A Check on distinct handoffs among the last *k* catches ping-pong |
| Supervisor | Repeat {ask the supervisor for a `one of` worker label or `finish`; ask that worker} |
| Hierarchical | Supervisors as members of supervisors, bounded by `nests-at-most` |
| Debate | Split the sides from one snapshot. Each round writes to a shared transcript Store. Ask a judge. Metered |
| Voting / quorum | Join *k* of *n* that pass a Check; combine with vote. A weighted quorum joins until a Check over the combined weights holds |
| Stigmergy | An environment Store that agents react to with `starts-when` on its changes; no dispatcher. Pheromone decay is a scheduled Flow that rewrites strengths |
| Gossip | Each agent's inbox is a Store. A pure program picks peers. Agents `await` their inbox |
| Negotiation | Rounds of offers written to a shared Store, each party's reservation price hidden by Origin. A Check tests whether the terms agree. Metered, and a person is asked on deadlock |
| BabyAGI task queue | A task Store ordered by priority. Repeat {take the top task; ask the executor; ask the creator and append its tasks; ask the prioritiser to rewrite the order} |
| Sleep-time compute | `starts-when` idle (a Check that `now` minus the last activity exceeds some time) or on the clock: a consolidation Flow that rewrites memory Stores |
| Model cascade (FrugalGPT) | `choose` rungs: a cheap model, then a Check that confidence ≥ x, otherwise the next model (`if-unsure-below`) |
| Race-and-cancel, speculative execution | Split, join on first, cancel the rest |
| Parallel guardrails with a tripwire | Split {agent, guardrail}; join everyone, but stop on the first failure and cancel the other branch |
| Streaming guardrail | A handler on each part of a streamed answer; cut the answer off on a match |
| Dual-model / CaMeL-style injection defence | A privileged planner model sees only text whose origin is the reviewed definition or the customer. A quarantined model reads tool output, and its answers carry the Origin *tool output*. Law 7 keeps those answers from being read as instructions, and law 6 keeps control decisions in Checks |
| Human-in-the-loop with escalation | The question recipe in §3. `not-the-same-as` is a Check over identities in the run record |
| Durable long-running agent | Stores with `durability: durable-execution`, and `await` across days |
| Reminders an agent sets for itself | The agent writes moments to a Store. A `starts-when` per entry checks that `now` has reached it |
| Computer use | A screen Actor whose answers are image Shapes, inside the ReAct Flow |
| A2A remote agent | A remote-agent Actor; an `input-required` reply is an outcome label. Publishing with `published-as: a2a-agent` means naming a Flow and exposing it through `starts-when` on an inbound call |
| MCP tools, resources, prompts | Tools are Actors, resources are Stores, prompts are text in a Store with the origin *server*. **Sampling** (the server asks the host's model) and **elicitation** (the server asks the person) are inbound asks, each passing through a handler with an Allowance |
| Steering a running agent mid-run | An arrival with the run's correlation key is written to its conversation Store, and the loop reads it each turn (`if-still-running: join`) |
| Time travel / resume from an earlier step | Fork the Stores at a recorded version and resume the Flow at that step's label |
| Spawning helpers with narrowed powers | Instantiate a definition value (law 8) with an Allowance value split from the parent (law 5), inside `starts-at-most` and `nests-at-most` |
| Reconcile toward a desired state (Kubernetes) | `starts-when` a Check finds that actual differs from desired (level-triggered). A Flow corrects it, and a Check confirms convergence |

### 5.3 Workflow control-flow patterns (van der Aalst et al.)

The 43 workflow patterns are the standard test of whether a control language is
complete. All of them reduce to the Flow operators plus Store and Check.

| Patterns | Built as |
|---|---|
| Sequence, parallel split, synchronisation, exclusive choice, simple merge | `then`, split, join everyone, `choose`, a sibling reached by two labels |
| Multi-choice; structured, local and general synchronising merge; acyclic synchronising merge | Split where each branch has a Check guard. Join "everyone that started", which the run record knows |
| Multi-merge; structured, blocking and cancelling discriminator; N-out-of-M join | Join modes: every arrival continues, or first, or *k* of *n*. The others are cancelled, allowed to finish and be ignored, or detached |
| Arbitrary cycles, structured loop, recursion | Sibling `then` cycles, metered; repeat-until; an Actor asking itself within `nests-at-most` / `asks-itself-at-most` |
| Implicit and explicit termination | A Flow ends when no ask is open and nothing it started is running, or at `done` |
| Multiple instances without synchronisation, or with design-time or run-time knowledge | Split each over a list, detached or joined |
| Multiple instances *without* a-priori run-time knowledge | Split over a Store that is still growing. Join when it is quiet and a Check says "no more coming" |
| Static, cancelling and dynamic partial join for multiple instances | Join *k* of a growing set, with or without cancelling the rest |
| Deferred choice | Split {await A, await B}, join on first, cancel the rest |
| Interleaved parallel routing, critical section, interleaved routing | A Store `claim` used as a mutex, at the right scope |
| Milestone | An `await` on a Check over a Store. The task is enabled only while the milestone holds |
| Cancel task, case, region, or multiple-instance task; complete multiple-instance task | Cancel a scope. A case is the outermost scope of a run, reached through the run registry |
| Transient vs persistent trigger | An `await` that counts from this wait, or one that counts from whenever things arrived in the inbox |
| Thread split, thread merge | Split / join without data |
| Generalised AND-join | Join over branches still in flight, using the run record |
| Resource patterns (direct, role-based, deferred, separation of duties, retain familiar, capability-based, escalation, delegation) | Person Actor references by requirement, resolved against the directory Store. `asked-of`. Checks over identities in the run record |

---

### 5.4 The 203 patterns at agentic-patterns.com

The catalogue at agentic-patterns.com is the largest public list of agent
design patterns: 203 entries in eight categories, each with a one-line
mechanism. A snapshot of the catalogue taken on 2026-11-10 is in
`research/extracts/agentic-patterns-2026-11-10.json` (title, category,
status and summary only; the full text stays on the site).
`scripts/pattern-coverage.py` builds every pattern from the seven, and
Appendix B is its output. "Builds" means three things, each checked by the
script, which fails on the first one that does not hold:

1. **Every pattern has a construction**: a recipe in the seven primitives. No
   pattern in the snapshot is without one and no recipe is orphaned.
2. **Every construction is typed against the kernel.** Each recipe lists the
   operations it uses, and every operation must be one of the **76 operations
   of the seven primitives** that the script defines in one place (Appendix C).
   A recipe is therefore not free prose: it may use only moves the primitives
   have. The converse is also checked: every one of the 76 operations is used
   by at least one pattern, so the kernel carries no dead weight.
3. **Where PACT has the pattern as YAML, the script cites it and `pact
   check` loads it.** 57 patterns exist as PACT today: the core of a shipped
   example, a stock loop, or one of the seven pattern workspaces written for
   this audit under `examples/kernel/` (`fallback`, `triage`, `phases`,
   `lanes`, `governed-change`, `map-reduce`, `reconcile`). Where the citation
   is one file inside a workspace, that file is the pattern and the script
   checks the workspace that holds it. With `--check-shipped` the script runs
   the checker on every citation and fails if any does not load.

What the three levels establish differs, and the difference should be kept
in view. Level 3 is the strongest: the pattern exists as PACT today. Level 2
shows that a construction uses only operations the primitives have, which is
what "built from the primitives" means, but it does not run the construction.
Level 1 alone would be a claim in prose. Of the 203, all pass levels 1 and 2;
57 pass level 3. The seven new workspaces took one afternoon and the checker
caught eleven mistakes in them before they loaded, which is the method working
as intended. The other 146 fall in two groups: those whose operations all have
a keyword today (most of them) could be written the same way, and those that
lean on one of the 16 keyword-less operations in §9 cannot be written until
the keyword exists. Appendix B's "Operations" column says which is which.

Every pattern also carries a **kind**, which says where the construction's
edge is. The kind does not excuse a pattern from being built; it says what the
construction hands to something outside the agent.

| Kind | Count | Where the construction's edge is |
|---|---:|---|
| **mechanism** | 175 | Nothing outside. Everything the pattern does runs inside the agent. |
| **training** | 7 | The construction is the whole pipeline: the episode Store, the grader Checks, the trainer as a tool Actor, and the write of the new model into the catalogue Store, which law 8 makes pass the evals before anything asks it. The weight update itself happens inside the trainer Actor, the way a refund happens inside the payments tool. PACT describes and governs it; it does not perform it. |
| **practice** | 18 | The construction is the pattern's mechanical part: the feedback port, the canary route, the `locked-until` date, the release gate. The decision the practice is really about (to dogfood, to burn the boats, to ship as research) is taken by people, and no primitive set builds a decision. |
| **PACT itself** | 3 | The construction is a PACT tree: "declarative multi-agent topology definition", "specification-driven development", "team-shared configuration as code". |

By category:

| Category | Patterns | Mechanisms | Practices | Training | PACT itself |
|---|---:|---:|---:|---:|---:|
| Orchestration & Control | 61 | 54 | 4 | 1 | 2 |
| Reliability & Eval | 28 | 27 | 0 | 1 | 0 |
| Tool Use & Environment | 27 | 21 | 6 | 0 | 0 |
| Security & Safety | 23 | 23 | 0 | 0 | 0 |
| Context & Memory | 22 | 22 | 0 | 0 | 0 |
| UX & Collaboration | 17 | 11 | 5 | 0 | 1 |
| Feedback Loops | 14 | 11 | 1 | 2 | 0 |
| Learning & Adaptation | 11 | 6 | 2 | 3 | 0 |

**No eighth primitive was needed.** Every one of the 203 constructions uses
only the 76 operations of the seven under the eight laws. Six times, though, a pattern
asked for an operation by name that §2 had not written down. Each is an
operation on a primitive that already exists, and each fails the §0 test as
a primitive of its own, because it has no meaning apart from the primitive
it belongs to.

| Operation made explicit | On | Patterns that needed it | Why it is not a primitive |
|---|---|---|---|
| **digest**: a value's fingerprint, compared by a Check | Shape | Exact-Action Authorization Binding (the approval is bound to the digest of the exact ask); Approval-Bound Transactional Write; Canary Rollout (`digest(run id) mod 100 < 5` picks a deterministic slice); Soulbound Identity (a committed state hash); Prompt Caching; Action Caching & Replay | A function of one value, like `is-empty`. It is how the checker compares two things without reading them. |
| **declared detectors**: author-written rules beside the built-in named detectors (card number, email) | Check | Deterministic Threat Rule Scanning; Hook-Based Safety Guard Rails (block a destructive command); Proactive Trigger Vocabulary | A Check that matches a pattern is still a Check: decidable, yes or no, with a reason. |
| **a kind on each part of a stream** (answer, reasoning, tool call) | Shape | Reasoning-Token Firewall (the result is built from answer-kind parts only, never by stripping text); Chain-of-Thought Monitoring | A `stream of` a `one of`. Nothing new. |
| **placeholder**: a hidden value replaced by a host-issued reference and restored for an Actor allowed to *use without seeing* | Origin | PII Tokenization; Local-First Credential Broker; External Credential Sync | A *sensitive* Origin stamp plus a host-issued reference (Shape) plus the Allowance "use without seeing". The composition is what the three patterns are. |
| **revoke for a period** (a cool-down) | Allowance | Agent Circuit Breaker (a tool's Allowance withdrawn for a while after too many failures); Signal-Driven Activation (cooldown); Denial Tracking | §8 already had revoke and expire. This is revoke with a lifetime. |
| **effect class and declared write set, readable by a Check** | Actor | Conditional Parallel Tool Execution (all reads-only, so run together); Design-Time File Partition (overlapping write sets wait); Lethal Trifecta (no path has private data, untrusted input and an external write) | The effect class was already on the Actor (§2.4). The change is that a Check may read it, which is what makes the three patterns provable before the run. |

**What the audit says about the primitives, one by one.**

- **Origin earns its place again.** All 23 Security & Safety patterns are
  mechanisms, and 25 patterns across the catalogue lean on Origin. The Lethal
  Trifecta is the clearest case: it cannot be stated at all without an Origin
  for *private data* and *untrusted content* beside an Allowance for
  *external communication*. Access control alone (Allowance) sees three
  permitted steps and no leak.
- **Store and Flow carry the orchestration category.** 54 of the 61
  orchestration patterns are mechanisms, and almost all reduce to a Store
  with the right merge rule, `claim` or `fork`, plus a Flow join mode. The
  fair-share queue with heartbeat leases is `claim` with a lease renewed by a
  clock trigger; the design-time file partition is `claim` on a declared
  write set; the cross-cycle consensus relay is compare-and-swap on one key.
- **Check does the work the catalogue calls "deterministic".** Deterministic
  grader, evidence questions not verdict questions, non-generative judgment
  routing, action selector: each is law 6, a model answering a closed `one
  of` and a Check or pure program reducing the answers to the decision.
- **Shape is where the catalogue's "structured output" patterns live,** and
  three of the six new operations are Shape operations. That is a sign the
  first draft under-described Shape, not that Shape is weak.
- **Allowance covers every budget, cap, lane, cooldown and permission
  pattern,** and the money patterns (402-first payments, escrow, non-custodial
  spending) are Allowance values held in a Store and moved by claims, which
  §2.7 already had.

**The eighteen practices**, so nobody looks for a missing mechanism:
Dogfooding; Frontier-Focused Development; Shipping as Research; Burn the
Boats; Disposable Scaffolding; Progressive Autonomy with Model Evolution;
Tool Selection Guide; Tool Use Steering via Prompting; Patch Steering via
Prompted Tool Selection; Agent-First Tooling and Logging; CLI-First Skill
Design; Dual-Use Tool Design; LLM-Friendly API Design; AI-Accelerated
Learning; Agent-Friendly Workflow Design; Codebase Optimization for Agents;
Dev Tooling Assumptions Reset; Latent Demand Product Discovery. Three of
these (the prompt-steering ones) are text in the reviewed definition. The
rest are decisions a team makes.

**Limits of this audit.** A recipe is a construction, not a proof, as §10
says of the keyword mapping. The recipes were written from the site's
one-line summaries plus the longer excerpt of each pattern, not from running
code. A pattern whose summary hides a requirement would need its recipe
revised, and the script is where that revision goes.

---

## §6 Every keyword, accounted for

`scripts/primitive-coverage.py` assigns every one of the 569 keywords in
`spec/schema.yaml` the primitives it is built from (Appendix A has the table).
The script fails if a group in the schema has no entry, or if an entry names a
group that is not in the schema. A keyword added to the schema without a
decision about what it is made of therefore stops the script rather than going
uncounted.

| Primitive | Keywords where it is the **main** ingredient | Keywords it takes **any** part in |
|---|---|---|
| Actor | 120 | 165 |
| Flow (including handlers and triggers) | 111 | 140 |
| Store | 110 | 138 |
| Check | 75 | 114 |
| Allowance | 74 | 99 |
| Shape | 31 | 40 |
| Origin | 14 | 26 |
| none: words for people only (`description`, `because`, `name`) | 34 | 35 |

Three readings of this table:

- **Six of the seven are the main ingredient of 31 keywords or more.** A
  primitive that only two or three keywords used would be a feature, not a
  primitive.
- **Origin is the exception, and §2.2 says why.** It is admitted on the
  checkability test, not by count. The 14 keywords it is the main ingredient of
  are PACT's security promises (`never-from`, `hides`, `redaction`, `shows`,
  fenced server prose, `turn.from`, `data-stays-in`, and since 10 November
  `carries` and `gets-hidden-values`) and, since 12 November, the `topics:`
  tags of `docs/99` — a stamp on where something comes from that says what it
  is about. Law 7's checker rules read the first group as one stamp.
- **34 keywords have no behaviour at all.** They are `description:`, `because:`
  and names: text written for whoever reads a diagnostic. That is a property of
  the format, not a gap.

**The 342 closed-choice words are mapped too** (revision of 2026-11-10). 82 of
the 569 keywords accept only a fixed list of words: the twelve things a stage
can `do`, the eight things a limit may do `when-it-runs-out`, the five things
an interceptor `may` do, the five ways a team `waits-for` its members, and so
on. Each word is a feature in its own right, so each is assigned. A word
inherits its keyword's primitives unless the script says otherwise, and 28
keywords needed per-word entries: `does: decide` is a Flow `choose` over a
Check, while `does: run-code` is a program Actor under a fuel Allowance.
`python3 scripts/primitive-coverage.py --choices` prints all 342.

| Primitive | Closed-choice words where it is the **main** ingredient |
|---|---:|
| Flow (handlers and triggers included) | 80 |
| Actor | 74 |
| Allowance | 72 |
| Store | 41 |
| Check | 33 |
| Shape | 28 |
| Origin | 14 |

The coverage reviews went through the schema's help text and comments keyword
by keyword. Between them they found:
- **one missing primitive**, Origin, which both found independently;
- **about twenty keywords** whose first-draft mapping named a primitive that
  lacked the operation the keyword needs.

Every one of those is fixed in §2 and recorded in §8. Where a reviewer showed
that a first-draft mapping was simply wrong, the script was corrected:
- `limits.feel` "stops nothing", so it is a Check target for reports, not an
  Allowance.
- `values` are substituted at load time, so they are a load-time read of the
  definition, not a Store anything reads during a run.

---

## §7 Scenarios run end to end

Three walkthroughs that each touch most of the primitives and laws. They show the
pieces working together, not one at a time.

**A refund desk on a Monday morning.**
1. A customer writes in. The conversation port is `starts-when` "an arrival in
   the inbox", keyed by thread. A second message on the same thread therefore
   *joins* the open run instead of starting another one (the run registry, with
   `if-still-running: join`).
2. The customer pasted a card number. Before anything else, a *before* handler
   on `step.message` runs the named detector "card number". The value gets a
   *sensitive* Origin stamp, so the logs never see it (law 7).
3. The agent, a named Flow, asks the model. The model asks for
   `payments/issue-refund` with `amount: 340 GBP`.
4. The ask passes outward through the scopes: the stage's handler, then the
   agent's, then the workspace's.
5. The workspace scope holds the policy handler. Its Check, `amount more-than
   200 GBP`, holds. So it holds the ask and asks the person Actor named in
   `asked-of`, who has `answer-within: 4h`.
6. The approval is written to the run record. The Allowance condition on
   `issue-refund` is a Check over that record, and it passes.
7. The ask carries `same-request-key: order-id`, which is a Store `claim` at run
   scope. After a network error the model retries, and the claim refuses the
   second payment (law 3).

**A three-reader quorum, made honest.** Today `examples/patterns/quorum` runs
three readers that share an instruction and differ only in what each happens to
say. With `fork`:
1. All three start from one snapshot of the conversation and cannot see each
   other. That is what makes them independent.
2. The join is `enough-of-them` with `enough-is: 2`: *k* of *n* arrivals that
   pass a Check.
3. The answers combine with `decision: vote`.

If one reader's step were a payment, law 3 would refuse the tree at check time,
unless the payment's claim key did not depend on the branch. The first draft of
this document would have paid three times.

**An agent that improves itself, and cannot cheat.**
1. Once a week, the learning Flow starts (`starts-when` on the clock, drawing
   from a per-period Allowance) and asks the reflector Actor for a change.
2. The proposed change raises `tool-calls-at-most` from 10 to 40. Law 5 refuses
   it outright: a write to the definition may not widen an Allowance. The
   change is in `needs-a-person-to-approve: [limits]`, so the Flow asks a
   person.
3. The person says yes. The eval Flow runs on the `held-out` split. Those cases
   carry an Origin that lets only the judge read them, so the reflector never sees
   the test.
4. `keep-only-if: scores-higher-on-evals` holds, and `drift at-most 15%` holds.
5. The definition Store is written as a new version. `release:`, a *before*
   handler on writes to that Store, asks its approvers before the new version
   goes live.

---

## §8 What the review changed

The first proposal had seven primitives: today's seven, minus Origin, plus Hook.
Three reviewers attacked it independently. What they found and what changed:

**Hook was not a primitive.** The draft had Hook ("when something happens, do
something") beside Flow. The minimality review showed that it was two things,
and both were already Flow:
- *in-path* hooks are handlers on a scope, as in algebraic effects;
- *triggers* are `starts-when` and `await` over Stores.

Folding Hook in made the set smaller and **more checkable**. A global hook keyed
to an event name can be added anywhere, so the checker cannot list the hooks
around a given ask. A handler on a scope can always be listed, and the
exactly-once proof needs exactly that list. Every keyword that used Hook maps
to a Flow handler or trigger (§6).

**Origin is a primitive.** The two coverage reviewers found it independently, one
from keywords (`never-from`, `shows`, fenced server prose, `drop-parts`,
`watch`) and one from patterns (sealed bids, CaMeL, teammates who must not see
each other's sources). Both made the same argument. The guarantees need labels
that the *host* assigns and that propagate through every ask. A field an author
or a model writes can be forged, and a judgment made at one point cannot
propagate. The first draft had put "sensitivity labels" on Shape. That was the
forgeable version.

**Five soundness holes** (from the minimality and pattern reviews), each now a
law in §4:

| Hole | Concrete failure | Law |
|---|---|---|
| Chains of hooks were unbounded | Two triggers write each other's Store, forever | 2 |
| Forking over a payment | Five independent samples make five refunds | 3 |
| A composite could declare its own effect class | A paying workflow published as read-only | 1 |
| A model could write an agent reference | Reach to an agent that was never granted | 4 |
| Writes to the definition could widen an Allowance | A learner grants itself more budget | 5 |

**A law corrected by measurement.** The draft said every cycle carries an
`at-most`. The coverage review pointed to `spec/loops/standard.yaml`, whose
cycle has none. Reading the code showed the full picture:
- The PACT harness supplies `DEFAULT_STEPS = 8` (`ir.py:33-36`).
- A foreign host does not (`ir.py:516-520`).

Law 2 now says "metered, by the author or by default", and it states where it
does not hold today.

**Operations added**, each tied to a keyword's help text or to a pattern the
first draft could not build:

| Added | Because of |
|---|---|
| Store **durability**, **versions**, **pins**, **forget**, **read as of** | `workspace.durability`; `same-request-key-across`; `stage.version`; `drift`; `always-keep`; `kept-for` |
| Host Stores: **inbox**, **run registry**, **directory** | `counts-events-from`; `if-still-running: join / cancel-previous / stop`; role-based allocation |
| Flow **await**, with a correlation key | `heard`; persistent vs transient triggers; deferred choice; mid-run signals |
| Flow **join** over growing sets and run references, with a choice of what happens to the rest; **cancel** a scope or a run | dynamic fan-out; LangGraph `defer`; discriminator; cancel region and cancel case; race-and-cancel; tripwire guardrails |
| Shape **`stream of T`** and Actor streaming; a handler on each **part** | `voice.talking: both-at-once`; `may-be-interrupted`; `first-reply-within`; `per-word-under`; LLMCompiler |
| Shape **render** and a **load-time phase** (law 8) | `template-language: jinja`; `values`; `based-on` |
| Shape **host-issued references**; Allowance **values** that can be split and passed | `agent` answer shape; delegation at run time; auction allocation; the `Pool` problem in `F3` and `F7` |
| Check **named detectors**, **origin tests**, **percentiles**, **distinct-in-last-k**, **reachability** | `redaction.hide`; `never-from`; `measured-at`; handoff livelock; `available-when` |
| Actor **identity strength**, **on behalf of**, **location**, **may park** | `needs-signature`; `data-stays-in`; `run-code` callees "can never wait" |
| Allowance meters that **pause** by scope; **revoke / expire** | `paused-during`; `locked-until`; `tool-snapshot-max-age` |
| The schema's real **combine-rules** list | `combines-by` (`spec/schema.yaml:5561`) |
| Order-independent merges required under a split; fork branches discarded unless joined out | the pattern review's race between non-commutative merges, and its question of whether a backtracked branch commits |
| A handler may refuse one answer and keep waiting | `answered-by: everyone` with `not-the-same-as` |
| Stored text read into a prompt is fenced unless reviewed (law 7) | the pattern review's point that `F6`'s objection applies to any Store read into instructions, not only to the definition |

**Proposals not taken, and why:**

- *Introduce a Channel primitive for two-way streaming.* A channel is a Store
  with merge rule append, written in parts by one Actor, plus an `await` on it
  by another. Duplex voice is two of those. That construction loses nothing, so
  Channel is not admitted.
- *Ban backward edges, making Flow purely block-structured.* That would make
  "every split joins" trivial to check. But PACT's shipped loops are sibling
  cycles (`spec/loops/react.yaml`: `act → reason`), and the schema already
  forbids the dangerous case: "nothing jumps into or out of a stage's own
  `steps`". Allowing cycles among siblings while keeping nesting
  block-structured keeps both properties.
- *Make "reconcile toward a desired state" the only trigger semantics.* It is a
  good default: level-triggered, it never misses an event, and it is how
  `if-missed: run-when-back` behaves. But `if-missed: skip` and
  `counts-events-from: this-wait` are edge-triggered, so `starts-when` keeps
  both kinds.
- *A general expression language inside Check* (for UCT, decay, leaky counters).
  It would make Check undecidable. Pure programs as merge rules and selectors
  cover these, and law 6 keeps them away from the decisions the checker must
  prove.
- *Atomic updates across several keys at once.* `claim` is on one key. Changing
  several entries as one transaction is not provided. `docs/92-SWARM.md` §6.3
  finds "multi-entry transactional invariants" not warranted by any measured
  result, and every pattern in §5 needs only single-key claims.
- *Rename Actor.* The objection is fair: in the Hewitt sense, an actor has a
  mailbox. The word is kept in its UML sense, and §3 shows that a mailbox is
  derivable.

### Candidates considered and rejected as primitives

| Candidate | Why it is not one |
|---|---|
| Hook / Event | Flow handlers, plus `starts-when` and `await` over Stores |
| Channel / Stream | A Store with an append merge, written in parts, plus `await` |
| Message / Turn | An entry in the conversation Store, with an origin Origin |
| Time | A Shape (moments, durations) plus the clock Store |
| Identity / Principal | A property of an Actor, recorded in the run record |
| Budget | Allowance quantities |
| Model | One kind of Actor |
| Prompt / Instructions | Settings of a model Actor: text in the definition Store, with the origin *reviewed definition* |
| Graph / Edge / Channel kinds (`research/notes/orchestration-loops.md` §3) | Its 9 node kinds, 1 edge type and 7 channel kinds are Flow operators and Store merge rules. Its `queue` channel (claimable, "nothing in the corpus") is a Store `claim` with a lease |
| Agent | A named Flow |
| Policy | A handler, a person Actor and a Check |
| Eval | A Flow, plus Checks over a Store of cases |

### What the 203-pattern audit changed (2026-11-10)

**No primitive added or removed.** The six operations in §5.4 were added to
§2's inventories. Each is an operation on a primitive that already existed.

**Names were re-examined and kept.** The brief for this revision asked that
the primitives be easy to understand and easy to learn, so every name was
tried against its alternatives:

| Kept | Alternatives tried | Why the alternative lost |
|---|---|---|
| **Shape** | Type, Schema | "Type" means too many things to programmers and nothing to a support lead. "Schema" is jargon. A shape is what a form has. |
| **Origin** (was Label) | Label, Provenance, Tag, Stamp | Label was the 4 November name, kept at first because origin is only one of the stamp's three parts. The reader test (§11) overturned that: both cold readers took "Label" for a tag the author chooses, which is the opposite of what it is, and both proposed Origin. "Provenance" is jargon. "Tag" has the same problem as Label. "Stamp" is the office picture and reads oddly in a sentence. |
| **Store** | Memory, State | "Memory" names one use. "State" is what a program has, and suggests a single blob rather than named cabinets with scopes and merge rules. |
| **Actor** | Worker, Party, Participant | "Worker" is wrong for a person who approves. "Party" is legal. "Participant" is long. Actor has one known confusion (the Hewitt sense, §8) and the doc names it. |
| **Flow** | Process, Workflow, Plan | "Workflow" is already a PACT kind. "Process" is an operating-system word. "Plan" is a thing a planner Actor writes. |
| **Check** | Rule, Guard, Condition, Test | Both cold readers (§11) suggested "Rule". PACT's own keywords agree halfway: `rules:`, `route-rule` and `eval-rule` are *lists of Checks*. But a rule, in the policy sense, *acts*, and a Check never does; keeping the element and the container distinct is what lets §2.5 say "a handler acts, a Check decides". "Test" suggested a run-time test to one reader, when a Check is also what the checker reads before the run. "Guard" is one use. |
| **Allowance** | Permission, Budget, Grant, Limit | Each alternative names one half. Allowance means both "what you may do" and "how much of it", which is exactly the primitive. |

**Flow stays one primitive, taught in three parts.** The reviewers' strongest
learnability objection was that Flow is big: eight operators and five
handler moments. The alternative was to split it into *compose* (ask, then,
choose, split/join), *scope* (a region with handlers, its own Stores and
Allowance) and *trigger* (`starts-when`, `await`). That split was tried and
rejected for the same reason Hook was folded in (§8): a scope's handlers
are listable only because a scope is a node in the Flow, and a trigger is an
`await` at the top of a Flow. Three names for one graph would give the
checker three places to look. §11 teaches Flow in those three parts
anyway, which costs nothing.

---

## §9 What PACT needed in order to build what it refused, and now has

Most of the seven already existed in the format under other names. This is the
complete list of what did not, ordered by what each item unlocks. **All of it
has shipped** (2026-11-10, `docs/98-PRIMITIVES-ENGINEERING-PLAN.md`): the table
keeps its "smallest change" column as written before the work, and the table
after it names the keyword each operation got.

| Was missing | Unlocks | Smallest change, as proposed |
|---|---|---|
| **Store `fork`**: a stage run again from a snapshot, not on a longer transcript | Real Tree-of-Thought, independent self-consistency, LATS, debate from a common start (the two names AC-5.2 leaves unanswered) | A `fork-from:` on `each`, `together` and `repeat`, naming a snapshot point |
| **Store `claim` across a team, with a lease** | Blackboard, BabyAGI, LLMCompiler, gap-directed fan-out, auction settlement (the three names AC-5.1 refuses) | Widen `same-request-key-across:` to a team-scoped Store and add a lease (`docs/92-SWARM.md` §6.1 already argues for this) |
| **A team-scoped Store** that agents read and write between turns | Blackboard, stigmergy, Mixture-of-Agents | `remembers:` at `team` scope, writable by members, with writes admitted by a Check |
| **Origin as host-assigned origin, propagated** | One mechanism for `never-from`, `shows`, fenced server prose, `hides`, `drop-parts`; CaMeL-style injection defence; Reflexion's buffer without `F6`'s objection | An origin on every value the harness holds, and the join rule on every ask |
| **Join over growing sets; `await` with a correlation key; cancel by run reference** | LLMCompiler, deferred choice, cancel case, steering mid-run | Most of this exists piecemeal (`heard`, `if-still-running`, `.run`); what is missing is one operator each |
| **Allowance values; quantities taken from Store values** | Auctions, run-time delegation, a budget pool that can grow | Let a `limits:` figure be a binding, and let `divides-the-budget` move budget during a run |
| **Laws 1–8 as checker rules** | The guarantees above, enforced mechanically | Each is a load-time rule over data the checker already reads (law 8 also needs an instantiation-time call) |

The first two rows restate an observation `docs/70-PRODUCTION-GAP-REGISTER.md`
makes about AC-5.1 and AC-5.2, that "both want the same absent primitive", and
make it precise. The absent primitive is not new. It is two operations on Store.

**The 16 operations that had no keyword, and the keyword each has now.** 60
of the 76 kernel operations had a PACT keyword before this round; these are
the rest. `scripts/pattern-coverage.py --ops` now reports none without one.
Where the shipped keyword differs from what this section first proposed, the
last column says so.

| Operation | Primitive | Keyword now | Example workspace |
|---|---|---|---|
| `shape.stream` | Shape | answer shape `stream of <shape>`; an answer is built only from `answer` parts | — |
| `shape.reference` | Shape | an `agent`-shaped answer used as a `call:` binding, held to `may-call:` | — |
| `shape.digest` | Shape | `in-share: <percent>`; a person's yes bound to the digest of what they saw (not `digest-of:`) | `kernel/canary` |
| `label.propagate` | Origin | `never-from:` held at check time and again on every memory write at run time | — |
| `label.placeholder` | Origin | `gets-hidden-values: yes` on an action (not `hides: … as-placeholder`) | `kernel/private-by-placeholder` |
| `store.claim` | Store | `same-request-key-across: the-team \| the-workspace` with `claim-lasts:` (not `lease:`) | `kernel/work-queue` |
| `store.fork` | Store | `forks: yes` on an `each`, `together`, `repeat` or loop stage (not `fork-from:`) | `kernel/self-consistency`, `kernel/tree-search` |
| `actor.effect` | Actor | computed by the checker; `effect:` in `when-this`; `pact discover` prints it | — |
| `actor.write-set` | Actor | `writes: [<place>, …]` on an action | `kernel/no-leak` |
| `flow.join` | Flow | `keeps-taking: yes` on an `each` | `kernel/work-queue` |
| `flow.cancel` | Flow | `does: stop` with `stops: steps.<stage>.run` | `kernel/work-queue` |
| `check.detector` | Check | workspace `detectors:`, used as `looks-like:` and in sentences | `kernel/private-by-placeholder` |
| `check.reachability` | Check | `carries:` on a tool, and the three-part leak rule | `kernel/no-leak` |
| `check.digest` | Check | request digests on approvals; `in-share:` | `kernel/canary` |
| `allowance.revoke` | Allowance | `rests-after:` with `rests-for:` on a tool (not `paused-for:`) | `kernel/circuit-breaker` |
| `allowance.value` | Allowance | `cost-per-request-from:` a run input, never above `cost-per-request-under:` (one figure, not every `limits:` figure) | — |

A team-scoped Store is `shared-with: the-team` on a `remembers` entry, gated by
`admitted-when:` and `admitted-by:` (`kernel/blackboard`). Law 2's owner
opt-out is `limits.unbounded: yes`, accepted only on a `limits` path listed
under `owners:` with `owned-by:`, and reported as a note on the load report.
The eight laws are checker rules; `docs/98` §3 names each rule.

---

## §10 Limits of this analysis

- **Coverage is a mapping, not a proof.** Each of the 569 assignments is a
  judgement about a keyword's help text, checked by reviewers who read the
  schema independently. A formal proof would need a semantics for every
  keyword, which PACT does not have in one place. Today, the adapters are that
  semantics.
- **"Every published pattern" means every pattern in the catalogue in §5.** A
  pattern nobody has written down yet may need something new. The admission rule
  in §0 decides whether it does: show a pattern that cannot be built with the
  guarantees intact, or a guarantee that cannot be checked.
- **The pattern review relied on memory for some 2025–2026 work.** That includes
  CaMeL, the injection-defence patterns and sleep-time compute. The reviewer had
  no web access to confirm them, and its report says so.
- **Buildable is not the same as worth building.** The auction can be built, and
  `F7`'s evidence that its bids would be noise still stands. This document
  answers whether the pieces are sufficient, not whether every pattern should
  ship.
- **The laws are written, not enforced.** Nothing in `pact check` implements
  laws 1–8 as stated here. Law 2 is the closest: the harness default supplies
  most of it.
- **A typed construction is not a running one.** Appendix B's recipes use
  only the 76 kernel operations and the script proves that much. It does not
  execute them. Of the 203, 57 exist as PACT today and load through the
  checker; the other 146 are constructions. Those whose operations all have a
  keyword could be written as examples the way the seven new pattern
  workspaces were; those that lean on a keyword-less operation (§9) cannot be
  until the keyword exists. "Loads through the checker" is also weaker than
  "ran and did the right thing": the checker proves shape, routing, bounds and
  gates, and no run was made.
- **The reader test is two readers played by a model.** It measured
  placement of fifteen keywords and five patterns from a one-page briefing
  (§11). It is evidence that the one-pager teaches the seven, and evidence of
  which lines confused newcomers. It is not a study of recruited people.
- **The kernel is this document's choice of granularity.** Another author
  could split or merge operations (is `claim` one operation or three?). The
  76 are the smallest set found in which every pattern names only operations
  the primitives have and every operation is used. Changing the split changes
  the count, not the seven.

---

## §11 The first hour: the seven in the order to learn them

The seven are a mental model, not a syntax. An author keeps writing PACT's
keywords, and this section is for the author who wants to know what the
keywords are made of, the reviewer who wants to know what the checker can
promise, and the adapter writer who wants to know what a host must provide.

**One sentence to remember.** An **Actor** is asked, in a **Flow**, with data
of some **Shape** and **Origin**, read from and written to **Stores**, on the
strength of **Checks**, within an **Allowance**.

**Each block answers one question.**

| Block | The question it answers | Learn these first | Learn these when you need them |
|---|---|---|---|
| **Shape** | What does this piece of data look like? | text, money, yes-or-no, `one of`, records, lists | streams and their part kinds, host-issued references, digest, render |
| **Actor** | Who or what can I hand one task to? | a model, a tool action, a person; what it takes and answers with; its effect (reads, writes, spends, cannot be undone) | programs, remote agents, figures, identity strength, location, "may it park" |
| **Flow** | In what order, and what happens next? | **do:** ask, then-by-outcome, choose · **many:** split and join, await · **around:** a scope with before/after/failure handlers (retry, back up, undo), `starts-when` | join modes over growing sets, cancel, detach with a run reference, handler ordering |
| **Store** | What has to outlive this step? | read, write, scope (step, conversation, run, team, workspace), lifetime; **claim**, so that a thing happens exactly once | merge rules, leases, fork, find by meaning, versions and pins, the host Stores |
| **Check** | Can a computer answer this yes or no, before the run? | compare, typed compare (money, time), all / any / not. *A Check changes which way the agent goes.* | detectors, origin tests, counts and order over the run record, aggregates, reachability |
| **Allowance** | What may this part do, and how much? | which tools it may reach; steps, tool calls, money, time. *An Allowance is a meter or a door: remove it and the agent may do more.* | per-scope and per-period counting, pass-down (always narrower), revoke for a period, values that can be split |
| **Origin** | Where did this value come from, and where may it go? | origin (customer, tool, person, reviewed definition); "only reviewed text instructs" | sensitivity, region, propagation rules, placeholders |

**A learning order that produces a working agent at every step.**

1. **Shape + Actor + Flow(do).** A model Actor with an `accepts` and an
   `answers-with` Shape, asked once. That is `examples/refund-desk` with
   nothing but `agent.yaml`. One hour.
2. **Store.** Give it `remembers:` so it keeps what the customer said.
3. **Check + Flow(around).** Add the approval rule: a Check over `amount`
   and a before-handler that asks a person. The agent is now governed.
4. **Allowance.** Add `limits.yaml` and `uses:`. The agent now has a
   boundary the checker can prove.
5. **Flow(many) + Actor(composite).** Add the two helpers and `teamwork`.
   The agent is now a team, and the team is itself an Actor.
6. **Origin.** Read `never-from` and the redaction interceptor as what they
   are: one Origin mechanism spread over several keywords today.

**Tested on two cold readers (2026-11-10).** Learnability was asserted in the
first draft. It was then measured. Two readers who had never seen PACT, one
played as a non-programming support team lead and one as a senior distributed-
systems developer, were given *only* the one-page version of this section (the
sentence, the table above, the office pictures and three notes) and nothing
else from the repository. Each then did three tasks blind: name the main
primitive of fifteen PACT keywords from their help text alone; build five
patterns from the catalogue in §5.4 (circuit breaker, PII tokenisation,
fair-share queue with leases, plan-then-execute, canary rollout); and say what
was hard.

| Measure | Support lead | Developer |
|---|---|---|
| Keywords: main primitive agrees with `primitive-coverage.py` | 10 of 15 | 10 of 15 |
| Keywords: main or secondary agrees with any primitive the script lists | 13 of 15 | 14 of 15 |
| Patterns: recipe names the primitives the script's recipe leans on | 5 of 5 (one missed Allowance in PII tokenisation, one missed Store for the plan) | 5 of 5 |
| Self-rated ease, 1 to 5 | 3 | 3 |

The same three keywords confused both readers, and each confusion was
instructive:

- `same-request-key` was read as Flow ("runs once" sounds like control) or
  Actor ("an idempotent action"). It is a Store `claim`. The one-pager had
  claim under "learn later"; it is now under "learn first", with the words
  "so that a thing happens exactly once".
- `evals.population` ("where these test cases came from") was read as Origin
  by both. The script had it as Store only. Both readers were right that
  provenance of a test case is an Origin question, and the script now lists
  Origin as its second ingredient. The reader test corrected the mapping.
- `context-policy.when-full` was read as Store by both, because it is a rule
  about how full the conversation Store may get. The script had it as a
  handler trigger (Flow) with a Check. Store is now listed as well.

Both readers named the same two things as hardest: **Check versus
Allowance** ("a time limit, a spending ceiling and keep-only-if all read as
rules"), and the name **Label**, which both took for a tag the author chooses
and for which both proposed *Origin*. The first produced the cut sentence now
at the end of §2.6 and in the table above. The second renamed the primitive.
Both readers also suggested *Rule* for Check; §8 says why Check was kept.

The developer listed four things they "could not place": idempotency, retry
with back-off, metrics export and a lease's heartbeat. All four are in §2
(claim; the failure handler; the run record read by a tool Actor; a clock
`starts-when`), and none was on the one-pager. The one-pager now names claim
and retry. The support lead's one request was a worked example with each line
of YAML tagged by primitive, which `docs/97-PRIMITIVES.html` is, and which
was deliberately withheld from the test.

Two readers is a small sample and both were played by a model given a
persona, not recruited people. What the test establishes is narrower than
"easy to learn": a reader with no PACT exposure, given one page, places two
keywords in three on the primitive the authors chose and builds five patterns
they have never seen with the right pieces. The misses were systematic, not
random, and each led to a change.

**What the office picture does for each.** The blank form (Shape), anyone
with an in-tray (Actor), the procedure manual (Flow), the filing cabinets
(Store), the written rules (Check), the keycard and the company card
(Allowance), the mailroom's stamp (Origin). `docs/97-PRIMITIVES.html` is built
around these pictures.

**What a reader should *not* have to learn.** The 569 keywords, the 342
words, the 62 kinds. Those are the surface, and `pact check` names the right
one when it is needed (`site-docs/reference/kinds.md`). The seven are what a
reader needs in order to predict what a keyword they have never seen will do.

---

## §12 Is it Turing complete?

Yes. And the halting guarantee that law 2 gives is a *profile* the owner can
step out of, not a contradiction hidden in the design.

**Expressively, yes.** Flow has sequence (`then`), branching (`choose`,
then-by-outcome), loops (sibling cycles, `repeat until`), and recursion (a
named Flow is an Actor and may ask itself within `nests-at-most`). Store is
unbounded memory. Program Actors (`engine: wasm`, `python`, `typescript`)
are general-purpose languages. Any computable agent behaviour can be written.

**The two properties cannot both hold for one tree, and nobody should claim
they do.** A language in which every program provably halts is not Turing
complete; that is the halting problem, not a PACT limitation. So PACT has to
choose per tree, and law 2 says how:

- **By default, every cycle is metered**, by the author or by the harness
  default, and the ceiling may be a Store value but never one the cycle itself
  can write. The checker can then promise "this agent stops", and that promise
  is what makes `pact check` worth running before a payment loop goes live.
- **An owner may opt one cycle out**, writing `limits.unbounded: yes` on a
  path `owners:` lists with `owned-by:`. The tree is then Turing complete in the strict sense, and the
  checker says so on the load report as a named finding, the same way it
  reports a degraded adapter feature: visible, attributable to a person, never
  silent.

**What was true before this was implemented.** PACT's own
harness supplies a ceiling of eight steps when an author writes none
(`adapters/python/src/pact_adapters/ir.py:33-36`), so on that harness every
tree halts. A host whose loop is not PACT's carries a ceiling only when the
author wrote one (`ir.py:516-520`), so on those hosts a loop with no `at-most`
runs unmetered and PACT is already Turing complete in the strict sense, by
omission rather than by decision. The owner opt-out above turns that omission
into a visible choice, reported the same way on every host. Now every host is
handed the ceiling (eight steps when the author wrote none), and only an
owner's `unbounded: yes` removes it (`loader/unbounded-without-an-owner`,
note `this-tree-may-not-stop`).

**This is the standard stance for anything that checks before it runs.** The
eBPF verifier in the Linux kernel accepts only bounded loops and offers
`bpf_loop` for the rest; Temporal workflows run under a history limit and
`continue-as-new`; WebAssembly hosts meter fuel. Each is used to write
arbitrary programs, and each makes the author say so when a bound is removed.

**The guarantees are the point.** A set of three primitives (create, send,
become) is Turing complete and can build every pattern in Appendix B as an
opaque program. §0 explains why that answer is refused: it builds the pattern
and destroys the guarantee. The seven are the smallest set found that builds
every pattern *with* the eight guarantees available, which is the stronger
claim and the one PACT needs.

---

## §13 Why this is the final list, and not a fresh start

The question put to this revision was whether the 2026-11-04 proposal was
sound enough to extend or should be replaced. The evidence says extend, for
four reasons.

1. **Three complete inventories, no leftovers.** 569 keywords, 342 words and
   203 patterns were each assigned mechanically, and the scripts fail on the
   first unassigned item. A rival set would have to clear the same three bars
   and show a guarantee or a pattern the seven cannot reach. None was found.
2. **Independent attacks converged on the same set.** The first draft had
   Hook and no Origin. Three reviewers who did not see each other's work
   removed Hook, added Origin and found five soundness holes (§8). The
   203-pattern audit, eleven days later, found no further hole and added only
   operations. A set that stabilises under independent attack is a set to
   keep.
3. **The admission rule is sharp enough to say no.** Channel, Message, Time,
   Identity, Budget, Policy, Eval and Hook were each proposed as an eighth
   primitive and each was shown to be a composition (§8). An eighth that
   clears §0 would be welcome, and the rule says exactly what it would have to
   do.
4. **The names survived a learnability review.** Each was tried against its
   alternatives and kept (§8). The one real learnability cost, Flow's size, is
   handled by teaching it in three parts (§11) rather than by splitting the
   primitive and giving the checker three places to look.

What was open when this document was written was implementation, not design,
and it has since been done (`docs/98-PRIMITIVES-ENGINEERING-PLAN.md`, all
seventeen work packages): the 16 keyword-less operations, the owner opt-out of
law 2, and the eight laws as checker rules. §9 names the keyword each got, and
`docs/98` §9 says where the build differs from that plan. Two further things cannot be done from
inside this repository at all: recruiting readers for a learnability study
with people rather than personas (§11), and writing the remaining 146
constructions as checked examples, which is open-ended and grows with the
catalogue.

---

## §14 Four decisions this document cannot take

Everything above that could be done from inside the repository has been done
and is checked by a script. Four things remain, and each is a decision for
the owners of PACT rather than a step left undone.

| Decision | What it would take | Recommendation |
|---|---|---|
| **Done (2026-11-10).** ~~Add the 16 keyword-less operations and the owner opt-out to the schema, and the eight laws to `pact check`.~~ | Changes to `spec/schema.yaml`, the Rust loader and the Python adapters, with tests in both ports. §9 names the keyword for each. | Do it as a numbered work package, starting with Store `fork` and team-wide `claim`, which unlock the five patterns PACT refuses by name (AC-5.1, AC-5.2). |
| **Decided: option A.** ~~Choose the default for law 2.~~ Strict Turing completeness and a halting guarantee cannot both hold for one tree. Today the harness meters every loop and other hosts meter none. | One line in law 2 and one checker rule: either "metered unless an owner opts out" (§12, the current text) or "unmetered unless the author writes a ceiling, and the checker warns". | Keep "metered unless an owner opts out". The thesis (`docs/00-THESIS.md`) sells the checker's promises, and "this agent stops" is the one a payment loop needs. The opt-out keeps the language Turing complete for the owner who wants it. |
| **Run a learnability study with people.** The two-reader test (§11) used personas played by a model. | Recruit two or three support leads and two or three developers who have not seen PACT, give them the one-pager, score the same fifteen keywords and five patterns. Half a day each. | Do it before the names are printed anywhere public. The persona test already changed one name; people may change another. |
| **How many of the remaining 146 constructions to write as checked examples.** Seven took one afternoon and the checker caught eleven mistakes. | Each is a small workspace under `examples/kernel/`. Those that lean on a keyword-less operation wait for the first decision. | Write the ones the README will point at, and let the rest stay as typed constructions. The script will keep saying which is which. |


## Appendix A: every keyword and its primitives

Generated by `python3 scripts/primitive-coverage.py --table`. The main
ingredient is listed first. "Flow" includes handlers and triggers. "-" means
words for a person, with no behaviour.

| Keyword | Built from |
|---|---|
| `workspace.name` | - |
| `workspace.pact-version` | Store |
| `workspace.workspace-id` | Store |
| `workspace.description` | - |
| `workspace.owner` | Actor |
| `workspace.profile` | Store |
| `workspace.durability` | Store |
| `workspace.allow-egress` | Allowance + Origin |
| `workspace.agents` | Actor + Flow |
| `workspace.workflows` | Flow + Actor |
| `workspace.shapes` | Shape |
| `workspace.template-language` | Shape + Origin |
| `workspace.time-zone` | Shape |
| `workspace.calendar` | Store |
| `workspace.remembers` | Store |
| `workspace.detectors` | Check + Shape |
| `workspace.owners` | Allowance + Actor |
| `workspace.release` | Flow + Actor + Check |
| `workspace.tools` | Actor |
| `workspace.resources` | Actor |
| `workspace.knowledge` | Store |
| `workspace.skills` | Store |
| `workspace.programs` | Actor |
| `workspace.values` | Store |
| `workspace.policies` | Flow + Check + Actor |
| `workspace.redaction` | Flow + Origin + Check |
| `workspace.questions` | Actor + Shape |
| `workspace.evals` | Flow + Check |
| `workspace.learning` | Flow + Allowance |
| `workspace.ports` | Flow |
| `workspace.loops` | Flow |
| `workspace.context-policies` | Flow + Store |
| `workspace.bundles` | Store + Allowance |
| `workspace.interceptors` | Flow + Allowance |
| `workspace.watch` | Flow + Store |
| `workspace.topics` | Origin |
| `workspace.events` | Check |
| `workspace.reactions` | Flow + Actor |
| `workspace.models` | Store + Actor |
| `agent.name` | - |
| `agent.description` | - |
| `agent.base` | Store |
| `agent.instructions` | Actor |
| `agent.team` | Actor + Flow |
| `agent.teamwork` | Flow + Allowance |
| `agent.uses` | Allowance |
| `agent.accepts` | Shape |
| `agent.answers-with` | Shape |
| `agent.answers-with-mode` | Shape + Actor |
| `agent.checked-by` | Check + Flow |
| `agent.checks-at-most` | Allowance + Flow |
| `agent.run-inputs` | Shape + Store |
| `agent.needs` | Check + Actor |
| `agent.limits` | Allowance |
| `agent.settings` | Actor |
| `agent.policy` | Flow |
| `agent.evals` | Check + Flow |
| `agent.model` | Actor |
| `agent.model-for-checking` | Actor |
| `agent.loop` | Flow |
| `agent.variants` | Flow + Check |
| `agent.context-policy` | Flow + Store |
| `agent.remembers` | Store |
| `agent.interceptors` | Flow |
| `agent.reactions` | Flow |
| `agent.listens-for` | Flow + Actor |
| `agent.voice` | Flow + Actor |
| `agent.turns` | Store |
| `variant.when` | - |
| `variant.instructions` | Actor |
| `variant.says` | Actor |
| `variant.steps-at-most` | Allowance |
| `variant.may-use` | Allowance |
| `variant.turns` | Store |
| `voice.pipeline` | Flow + Actor |
| `voice.talking` | Flow |
| `voice.hears-with` | Actor |
| `voice.speaks-with` | Actor |
| `voice.speaks-as` | Actor |
| `voice.languages` | Shape + Check |
| `voice.turn-ends-after` | Flow |
| `voice.may-be-interrupted` | Flow |
| `voice.keeps-the-audio` | Store + Origin |
| `turn.from` | Origin + Store |
| `turn.says` | Store |
| `turn.attaches` | Store + Shape |
| `turn.calls` | Store + Actor |
| `turn.with` | Store |
| `turn.answer` | Store |
| `value.description` | - |
| `value.shape` | Shape |
| `value.rows-are` | Shape |
| `value.value` | Store + Shape |
| `program.description` | - |
| `program.engine` | Actor |
| `program.determinism` | Actor |
| `program.takes` | Shape |
| `program.answers-with` | Shape |
| `program.fuel` | Allowance |
| `program.body` | Actor + Store |
| `program-fuel.instructions-at-most` | Allowance |
| `program-fuel.runs-for-at-most` | Allowance |
| `program-fuel.memory-at-most` | Allowance |
| `program-fuel.when-it-runs-out` | Flow + Allowance |
| `catalog.version` | Store + Actor |
| `catalog.default` | Actor |
| `catalog.models` | Store + Actor |
| `catalog.benchmarks` | Store |
| `benchmark.description` | - |
| `benchmark.also-known-as` | Store |
| `benchmark.scale` | Store |
| `benchmark.runs` | Actor |
| `benchmark.with` | Actor |
| `model.description` | - |
| `model.family` | Store |
| `model.tier` | Store |
| `model.also-known-as` | Store |
| `model.served-by` | Actor + Allowance |
| `model.capabilities` | Actor |
| `model.reasoning` | Store |
| `model.cost` | Store + Allowance |
| `model.kind` | Actor |
| `model.benchmarks` | Store |
| `model.speed` | Store |
| `served-by.runtime` | Actor |
| `served-by.endpoint` | Actor + Allowance |
| `served-by.region` | Allowance + Store |
| `model-can.computer-use` | Actor |
| `model-can.tool-calling` | Actor |
| `model-can.modality-in` | Shape + Actor |
| `model-can.modality-out` | Shape + Actor |
| `model-can.sessions` | Actor |
| `model-can.languages` | Shape + Actor |
| `model-can.voices` | Actor |
| `model-can.ignores` | Actor |
| `model-can.ignores-while-thinking` | Actor |
| `model-can.thinks-unless-told` | Actor |
| `model-can.dimensions` | Shape + Actor |
| `model-can.context-window` | Store + Actor |
| `model-speed.first-words-within` | Store |
| `figure.value` | Store |
| `figure.provenance` | Store |
| `provenance.source` | Store |
| `provenance.harness` | Store |
| `provenance.contamination` | Store |
| `provenance.date` | Store |
| `provenance.as-of` | Store |
| `provenance.recorded-by` | Store |
| `model-cost.input-per-mtok` | Store |
| `model-cost.output-per-mtok` | Store |
| `needs.reasoning` | Check |
| `needs.tool-calling` | Check |
| `needs.images` | Check |
| `needs.audio` | Check |
| `needs.computer-use` | Check |
| `needs.documents` | Check |
| `needs.video` | Check |
| `needs.prefer` | Check + Flow |
| `needs.accept-when` | Check |
| `needs.context-at-least` | Check |
| `needs.because` | - |
| `needs.scores` | Check |
| `limits.feel` | Check |
| `limits.finishes-within` | Allowance |
| `limits.starts-from` | Allowance + Flow |
| `limits.paused-during` | Allowance + Flow |
| `limits.milestones` | Flow |
| `limits.cost-per-request-under` | Allowance |
| `limits.first-reply-within` | Allowance |
| `limits.per-word-under` | Allowance |
| `limits.steps-at-most` | Allowance |
| `limits.cost-per-request-from` | Allowance + Store |
| `limits.unbounded` | Allowance + Actor |
| `limits.tool-calls-at-most` | Allowance |
| `limits.runs-for-at-most` | Allowance |
| `limits.tokens-at-most` | Allowance |
| `limits.asks-itself-at-most` | Allowance |
| `limits.starts-at-most` | Allowance |
| `limits.nests-at-most` | Allowance |
| `limits.items-at-most` | Allowance |
| `limits.at-once-at-most` | Allowance |
| `limits.counted-per` | Allowance + Store |
| `limits.resets-every` | Allowance + Flow |
| `limits.when-it-runs-out` | Flow + Allowance |
| `limits.asks` | Actor |
| `limits.measured-at` | Check |
| `settings.max-tokens` | Actor |
| `settings.thinking` | Actor |
| `settings.temperature` | Actor |
| `settings.top-p` | Actor |
| `settings.top-k` | Actor |
| `settings.stop-sequences` | Actor |
| `settings.seed` | Actor |
| `settings.presence-penalty` | Actor |
| `settings.frequency-penalty` | Actor |
| `settings.tool-choice` | Actor |
| `settings.parallel-tool-calls` | Actor |
| `settings.service-tier` | Actor |
| `resource.available-when` | Allowance + Check |
| `resource.resource-kind` | Actor |
| `resource.endpoint` | Actor |
| `resource.auth` | Allowance |
| `resource.engines` | Actor |
| `resource.asks-to-run` | Flow + Actor |
| `resource.asks-to-connect` | Flow + Actor |
| `resource.tool-snapshot-digest` | Store + Check |
| `resource.tool-snapshot-taken-at` | Store |
| `resource.tool-snapshot-max-age` | Check + Allowance |
| `resource.published` | Store |
| `resource.if-it-changes` | Flow + Check |
| `resource.asks-when-it-changes` | Actor |
| `resource.description` | - |
| `knowledge.description` | - |
| `knowledge.topics` | Origin |
| `knowledge.documents` | Store |
| `knowledge.looked-up-by` | Store |
| `knowledge.split-by` | Store |
| `knowledge.passages-at-most` | Allowance + Store |
| `knowledge.must-cite` | Check |
| `knowledge.use-when` | Actor |
| `knowledge.do-not-use-when` | Actor |
| `knowledge.if-unsure` | Actor |
| `knowledge.embedded-by` | Actor |
| `knowledge.reranked-by` | Actor |
| `knowledge.interface` | Actor |
| `knowledge.chosen-by` | Actor + Check |
| `knowledge.implements` | Actor |
| `skill.available-when` | Allowance + Check |
| `skill.name` | - |
| `skill.description` | Actor |
| `skill.use-when` | Actor |
| `skill.do-not-use-when` | Actor |
| `skill.if-unsure` | Actor |
| `skill.costs-about` | Allowance |
| `skill.content` | Store |
| `skill.references` | Store |
| `skill.scripts` | Store |
| `skill.assets` | Store |
| `skill.interface` | Actor |
| `skill.chosen-by` | Actor + Check |
| `skill.implements` | Actor |
| `published.taken-at` | Store |
| `published.digest` | Store |
| `published.server-version` | Store |
| `published.instructions` | Origin + Store |
| `published.tools` | Store |
| `published-tool.description` | Store |
| `published-tool.takes` | Shape |
| `published-tool.answers-with` | Shape |
| `published-tool.hints` | Store |
| `detector.description` | - |
| `detector.looks-like` | Check + Shape |
| `detector.examples` | Check + - |
| `credential-reference.by-reference` | Allowance |
| `tool.available-when` | Allowance + Check |
| `tool.description` | Actor |
| `tool.connect` | Actor |
| `tool.url` | Actor + Allowance |
| `tool.method` | Actor |
| `tool.says` | Actor |
| `tool.carries` | Origin + Check |
| `tool.topics` | Origin |
| `tool.rests-after` | Allowance + Check |
| `tool.rests-for` | Allowance |
| `tool.actions` | Actor + Allowance |
| `tool.category` | - |
| `tool.interface` | Actor |
| `tool.chosen-by` | Actor + Check |
| `tool.implements` | Actor |
| `tool.schemas-from` | Shape + Store |
| `tool.unlisted-actions` | Allowance + Flow |
| `action.description` | Actor |
| `action.topics` | Origin |
| `action.takes` | Shape |
| `action.answers-with` | Shape |
| `action.program` | Actor |
| `action.reads-only` | Actor |
| `action.needs-a-person` | Flow + Actor |
| `action.spends-money` | Actor + Store |
| `action.same-request-key` | Store |
| `action.same-request-key-across` | Store |
| `action.writes` | Actor + Store |
| `action.gets-hidden-values` | Origin + Allowance |
| `action.claim-lasts` | Store + Allowance |
| `action.bind` | Flow + Store |
| `action.projects-with` | Flow + Actor |
| `action.remember-as` | Store |
| `action.inspects` | Allowance + Check |
| `action.undone-by` | Actor + Flow |
| `action.status-check` | Actor + Flow |
| `action.calls` | Actor |
| `action.passes` | Actor |
| `policy.applies-to` | Allowance |
| `policy.ask-a-person` | Flow + Check + Actor |
| `question-rule.when` | Check |
| `question-rule.because` | - |
| `question-rule.question` | Actor |
| `question-rule.first-times` | Allowance + Store |
| `when-this.tool` | Check + Flow |
| `when-this.value` | Check |
| `when-this.arg` | Check |
| `when-this.more-than` | Check |
| `when-this.less-than` | Check |
| `when-this.is` | Check |
| `when-this.is-one-of` | Check |
| `when-this.contains-any-of` | Check |
| `when-this.effect` | Check + Actor |
| `when-this.in-share` | Check + Shape |
| `when-this.looks-like` | Check + Shape |
| `when-this.is-empty` | Check |
| `comparand.value` | Check |
| `comparand.now-plus` | Check |
| `comparand.now-minus` | Check |
| `question.description` | - |
| `question.says` | Actor |
| `question.answer` | Shape |
| `question.shows` | Origin + Actor |
| `question.asked-of` | Actor |
| `question.answer-within` | Allowance + Flow |
| `question.answered-by` | Flow |
| `question.enough-is` | Flow + Check |
| `question.asked-in` | Actor |
| `question.urgency` | Actor |
| `question.not-the-same-as` | Check + Actor |
| `question.needs-signature` | Actor + Check |
| `question.starts-with` | Store |
| `question.ordered-by` | Flow |
| `question.counts-events-from` | Flow |
| `question.only-when` | Flow + Check |
| `question.reminds-at` | Flow |
| `question.if-nobody-answers` | Flow |
| `question.escalates-to` | Actor + Flow |
| `question.checked-by` | Check + Actor |
| `reminder.at` | Flow |
| `reminder.nudges` | Flow |
| `reminder.tells` | Actor |
| `reminder.hands-over-to` | Actor + Flow |
| `reminder.runs` | Flow |
| `evals.description` | - |
| `evals.population` | Store + Origin |
| `evals.from-the-last` | Store |
| `evals.sample` | Flow |
| `evals.reviewed-by` | Actor |
| `evals.sliced-by` | Check |
| `evals.runs-every` | Flow |
| `evals.must-pass` | Check |
| `evals.rules` | Check |
| `evals.metrics` | Actor + Check |
| `evals.graded-by` | Actor |
| `evals.cases` | Store |
| `eval-rule.must-say-one-of` | Check |
| `eval-rule.must-contain` | Check |
| `eval-rule.must-not-contain` | Check |
| `eval-rule.must-call-before` | Check |
| `eval-rule.judged` | Actor + Check |
| `eval-rule.program` | Actor + Check |
| `eval-rule.library` | Check |
| `eval-rule.because` | - |
| `metric.uri` | Actor |
| `metric.threshold` | Check |
| `metric.with` | Actor |
| `metric.name` | - |
| `call-order.call` | Check |
| `call-order.first` | Check |
| `case.when` | Store |
| `case.with` | Store |
| `case.turns` | Store |
| `case.expect` | Store + Check |
| `case.from-these-passages` | Store |
| `case.because` | - |
| `case.must-also` | Check |
| `case.split` | Store + Origin + Allowance |
| `learning.enabled` | Allowance |
| `learning.may-improve-on-its-own` | Allowance |
| `learning.needs-a-person-to-approve` | Allowance + Flow |
| `learning.keep-only-if` | Check |
| `learning.review` | Flow |
| `learning.cycle-limits` | Allowance |
| `learning.models` | Actor |
| `learning.drift` | Check + Allowance |
| `learning-model.role` | Actor + Allowance |
| `learning-model.model` | Actor |
| `cycle-limits.per-cycle` | Allowance |
| `cycle-limits.per-month` | Allowance |
| `cycle-limits.evals` | Allowance |
| `drift.at-most` | Check + Store |
| `port.description` | - |
| `port.kind` | Flow |
| `port.every` | Flow |
| `port.says` | Actor |
| `port.if-still-running` | Flow + Store |
| `port.through` | Actor |
| `port.answers` | Actor + Flow |
| `port.accepts` | Shape |
| `port.bind` | Flow + Store |
| `port.only-when` | Check + Flow |
| `port.signed-with` | Check + Allowance |
| `port.in-time-zone` | Shape |
| `port.if-missed` | Flow |
| `port.per-row-of` | Flow + Store |
| `port.answer-within` | Allowance |
| `port.same-conversation-when` | Store |
| `port.counts-as-the-same-for` | Store + Check |
| `port.ordered-by` | Flow |
| `port.undo` | Flow |
| `port.then-run` | Flow |
| `port.who-can-reach-it` | Allowance |
| `port.remembers` | Store |
| `workflow.description` | - |
| `workflow.base` | Store |
| `workflow.accepts` | Shape |
| `workflow.answers-with` | Shape |
| `workflow.starts-at` | Flow |
| `workflow.steps` | Flow |
| `workflow.questions` | Actor + Shape |
| `workflow.policy` | Flow |
| `workflow.limits` | Allowance |
| `workflow.evals` | Check + Flow |
| `workflow.remembers` | Store |
| `workflow.hides` | Origin + Allowance |
| `workflow.data-stays-in` | Origin + Allowance + Store |
| `workflow.kept-for` | Store |
| `workflow.undone-by` | Flow + Actor |
| `workflow.published-as` | Actor + Flow |
| `workflow.release` | Flow + Actor + Check |
| `moment.at` | Store |
| `moment.after` | Shape |
| `moment.before` | Shape |
| `moment.counted-in` | Shape + Store |
| `moment.in-time-zone` | Shape |
| `ownership.owned-by` | Allowance + Actor |
| `ownership.locked` | Allowance |
| `ownership.locked-until` | Allowance + Shape |
| `release.asks` | Actor |
| `loop.description` | - |
| `loop.based-on` | Store |
| `loop.steps` | Flow |
| `loop.starts-at` | Flow |
| `stage.does` | Flow + Actor |
| `stage.forks` | Store + Flow |
| `stage.keeps-taking` | Flow + Store |
| `stage.stops` | Flow |
| `stage.says` | Actor |
| `stage.asks` | Actor |
| `stage.then` | Flow |
| `stage.may-use` | Allowance |
| `stage.at-most` | Allowance |
| `stage.fuel` | Allowance |
| `stage.runs-in` | Actor |
| `stage.call` | Flow + Actor |
| `stage.may-call` | Allowance |
| `stage.bind` | Flow + Store |
| `stage.waits-for-result` | Flow |
| `stage.version` | Store + Actor |
| `stage.chooses-between` | Flow + Check |
| `stage.by` | Flow + Check + Actor |
| `stage.over` | Flow + Store |
| `stage.identified-by` | Store |
| `stage.ordered-by` | Flow |
| `stage.combines-by` | Store |
| `stage.teamwork` | Flow + Allowance |
| `stage.steps` | Flow |
| `stage.starts-at` | Flow |
| `stage.until` | Check |
| `stage.remembers` | Store |
| `stage.checked-by` | Check |
| `stage.checks-at-most` | Allowance |
| `stage.undone-by` | Flow + Actor |
| `stage.limits` | Allowance |
| `stage.if-it-fails` | Flow |
| `rung.rules` | Check |
| `rung.agent` | Actor |
| `rung.if-unsure-below` | Check |
| `rung.if-it-disagrees` | Flow + Check |
| `rung.asks` | Actor |
| `route-rule.when` | Check |
| `route-rule.choose` | Flow |
| `route-rule.because` | - |
| `if-it-fails.after-that` | Flow |
| `if-it-fails.gives-up-after` | Allowance |
| `if-it-fails.backup` | Actor + Flow |
| `if-it-fails.carry-on-with` | Store |
| `if-it-fails.asks` | Actor |
| `if-it-fails.new-version-of` | Flow + Store |
| `if-it-fails.undo` | Flow |
| `if-it-fails.undo-where` | Check |
| `outcome.used-a-tool` | Flow |
| `outcome.answered` | Flow |
| `outcome.too-many-times` | Flow |
| `outcome.declined` | Flow |
| `outcome.nobody-answered` | Flow |
| `outcome.heard` | Flow |
| `outcome.decided-by` | Actor + Flow |
| `outcome.may-go-to` | Allowance + Flow |
| `context-policy.description` | - |
| `context-policy.when-full` | Flow + Check + Store |
| `context-policy.always-keep` | Store + Origin |
| `context-policy.then` | Flow + Store |
| `context-policy.summarised-by` | Actor |
| `context-policy.if-it-still-does-not-fit` | Flow |
| `context-policy.asks` | Actor |
| `tidy-step.what` | Store + Actor |
| `tidy-step.applies-to` | Store + Origin |
| `tidy-step.down-to` | Store + Allowance |
| `interceptor.description` | - |
| `interceptor.when` | Flow |
| `interceptor.applies-to` | Allowance |
| `interceptor.runs-at` | Flow |
| `interceptor.may` | Allowance |
| `interceptor.rules` | Flow + Check |
| `redaction.description` | - |
| `redaction.hide` | Origin + Check + Flow |
| `watch.description` | - |
| `watch.when` | Flow |
| `watch.writes-to` | Store + Origin |
| `topic.description` | - |
| `topic.noticed-by` | Origin + Check |
| `event.description` | - |
| `event.at` | Flow + Check |
| `event.when-this` | Check |
| `event.more-than` | Check |
| `event.topic` | Check + Origin |
| `event.judged` | Check + Actor |
| `reaction.description` | - |
| `reaction.event` | Check |
| `reaction.at` | Flow + Check |
| `reaction.when-this` | Check |
| `reaction.more-than` | Check |
| `reaction.topic` | Check + Origin |
| `reaction.judged` | Check + Actor |
| `reaction.applies-to` | Allowance |
| `reaction.fires` | Flow + Allowance |
| `reaction.then` | Flow |
| `reaction-step.remind` | Flow |
| `reaction-step.consult` | Flow + Actor |
| `reaction-step.tell` | Flow + Actor |
| `reaction-step.stop` | Flow |
| `subscription.topic` | Check + Origin |
| `subscription.event` | Check |
| `subscription.how` | Flow + Actor |
| `state.description` | - |
| `state.lasts` | Store |
| `state.shaped-like` | Shape |
| `state.starts-as` | Store |
| `state.forget-after` | Store |
| `state.kept-for` | Store |
| `state.kept-per` | Store |
| `state.comes-from` | Store + Flow |
| `state.combines-by` | Store |
| `state.shared-with` | Store + Allowance |
| `state.admitted-when` | Store + Check |
| `state.admitted-by` | Store + Check + Actor |
| `state.never-from` | Origin + Allowance |
| `state.survives-shortening` | Store |
| `state.stops-being-true-when` | Store + Flow |
| `bundle.description` | - |
| `bundle.version` | Store |
| `bundle.from` | Store |
| `bundle.brings` | Allowance |
| `bundle.contributes` | Store |
| `teamwork.may-start` | Allowance + Actor |
| `teamwork.waits-for` | Flow |
| `teamwork.enough-is` | Flow + Check |
| `teamwork.gives-up-after` | Allowance + Flow |
| `teamwork.starts` | Flow |
| `teamwork.divides-the-budget` | Allowance |
| `teamwork.shares` | Allowance |
| `teamwork.if-someone-fails` | Flow |
| `teamwork.asks` | Actor |

## Appendix B: every pattern at agentic-patterns.com, built

Generated by `python3 scripts/pattern-coverage.py --table` from the snapshot of 2026-11-10. Kind is one of mechanism, practice, training or pact (§5.4). "Built from" lists the primitives the recipe leans on, main first. "Operations" is the recipe typed against the kernel in Appendix C. "Shipped" names a PACT artifact that is this pattern today and passes `pact check`.

**Context & Memory**

| Pattern | Kind | Built from | Recipe | Operations | Shipped |
|---|---|---|---|---|---|
| Agent-Powered Codebase Q&A / Onboarding | mechanism | Store + Actor + Shape | A knowledge Store over the code (`knowledge:`), indexed by a program Actor into embeddings and a code graph; `find` by meaning and by graph; ask a model with the passages; `must-cite`. | `store.find`, `actor.program`, `actor.model`, `shape.record` | `examples/answers-from-documents` |
| Context Budget as a Governed Resource | mechanism | Allowance + Check + Flow | Allowance on context tokens, `counted-per` source; a Check aggregate over past runs for the trend, with a handler that alerts; item ceilings on every split (law 2). | `allowance.quantity`, `allowance.period`, `check.aggregate`, `flow.handler` |  |
| Context Window Anxiety Management | mechanism | Allowance + Shape | A context Allowance set below the model's window; the remaining figure is a Store value rendered into the instructions (Shape render) so the model can read its own budget. | `allowance.quantity`, `store.read`, `shape.render` |  |
| Context Window Auto-Compaction | mechanism | Flow + Store + Allowance | `context-policy.when-full`: a failure handler on 'context full' tidies the conversation Store (summarise-older, keep pins), a Check confirms it fits under the headroom Allowance, then the ask is retried. | `flow.handler`, `store.forget`, `store.pin`, `check.compare`, `allowance.quantity`, `flow.then` | `examples/refund-desk/context-policies/long-threads.yaml` |
| Context-Minimization Pattern | mechanism | Origin + Store + Shape | Values with origin Origin customer or tool output are parsed into a Shape-typed record and written to a Store; the raw entries are then forgotten by Origin (`drop-parts`), so later asks see only the structured value. | `label.origin`, `shape.parse`, `store.write`, `store.forget` | `examples/refund-desk/agents/refund-desk/agent.yaml` |
| Cross-Agent Lesson Sharing via Git | mechanism | Store + Origin + Flow | A workspace-scope Store backed by a repo (versioned), `find` by words before a debug ask, written by a handler after a fix. Lessons carry the model's-own-words Origin, so they reach the next agent as data (law 7). | `store.scope`, `store.version`, `store.find`, `flow.handler`, `label.origin`, `label.fence` |  |
| Curated Code Context Window | mechanism | Flow + Actor + Store | Ask a search Actor in a forked, isolated conversation; its answer is a Shape list of snippets written to a Store; the main ask reads only that Store, never the search transcript. | `flow.ask`, `store.fork`, `shape.record`, `store.write`, `store.read` |  |
| Dynamic Context Injection | mechanism | Store + Origin + Shape | A person Actor writes files or saved prompts into the conversation Store with origin Origin person; a saved prompt is reviewed-definition text, so it may instruct; an attached file is data. | `store.write`, `label.origin`, `label.fence`, `shape.render` |  |
| Episodic Memory Retrieval & Injection | mechanism | Store + Flow + Origin | A workspace Store of episode records (Shape), written by an after-handler at the end of each run; `find` top-k by meaning at the start of the next; model-written records are fenced as data. | `store.scope`, `flow.handler`, `store.find`, `label.fence` | `examples/refund-desk/agents/refund-desk/agent.yaml` |
| Filesystem-Based Agent State | mechanism | Store + Flow | Stores with `durability: checkpoint` or `durable-execution`; resume is a fork from a recorded version and the Flow continuing at that step's label. | `store.durability`, `store.version`, `store.fork`, `flow.then` |  |
| Layered Configuration Context | mechanism | Store + Flow | Enterprise, user, project and local files are four `based-on:` overlays merged into the definition Store at load time, in that order (law 8). | `store.version`, `store.merge`, `actor.instantiate` |  |
| Memory Synthesis from Execution Logs | mechanism | Store + Flow + Allowance | Each run writes a diary entry to a Store; a `starts-when` on the clock runs a synthesis Flow: `find`, ask a synthesiser, write rules to the definition Store under `needs-a-person-to-approve` and law 5. | `store.write`, `flow.starts-when`, `store.find`, `flow.ask`, `allowance.write`, `allowance.pass` |  |
| Proactive Agent State Externalization | mechanism | Shape + Check + Store | A note template is a Shape record; an after-handler Checks the required parts are present (completeness); an external memory Store with `find` is the fallback. | `shape.record`, `check.compare`, `flow.handler`, `store.find` |  |
| Progressive Disclosure for Large Files | mechanism | Store + Actor + Allowance | Files live in a Store; only their metadata is rendered into the ask; load, peek and extract are tool Actors over that Store, with a read Allowance. | `store.read`, `shape.render`, `actor.tool`, `allowance.see` |  |
| Prompt Caching via Exact Prefix Preservation | mechanism | Store + Shape | The conversation Store merges append-only with the static entries pinned first; the render order is fixed; the digest of the rendered prefix is the cache key the host uses. | `store.merge`, `store.pin`, `shape.render`, `shape.digest` |  |
| Schema-Guided Graph Retrieval for Multi-Hop Reasoning | mechanism | Shape + Store + Actor | One domain Shape is shared by the index-building program Actor, the query-decomposition ask and the typed `find` over the graph Store. | `shape.record`, `actor.program`, `store.find` |  |
| Self-Identity Accumulation | mechanism | Store + Flow + Origin | A pinned identity record in a workspace Store; a scope handler at session start reads it into the conversation, one at session end asks a reflector and writes back; model-written text is data (law 7). | `store.pin`, `flow.handler`, `flow.ask`, `store.write`, `label.fence` |  |
| Semantic Context Filtering Pattern | mechanism | Actor + Shape + Origin | A program Actor projects raw tool output (`projects-with`) to a small Shape before the model sees it; the tool-output Origin travels with the projection. | `actor.program`, `shape.record`, `label.propagate` |  |
| Session-Scoped Context Runtime for Agent Tools | mechanism | Store + Actor + Shape | A conversation-scope Store keyed by the digest of each read; an ask checks the Store first; a program Actor normalises tool output to one Shape. | `store.scope`, `shape.digest`, `store.read`, `actor.program` |  |
| Surface-Scoped System Prompt | mechanism | Flow + Check + Actor | `variants:` chosen by a Check over the run input that names the surface (interactive, headless, task); each variant has its own instructions. | `flow.choose`, `check.compare`, `actor.model` | `examples/refund-desk/agents/refund-desk/agent.yaml` |
| Tool Search Lazy Loading | mechanism | Store + Actor + Allowance | The tool catalogue is a Store; `find` by meaning returns Actor references; the Allowance grants reach to the tools found, not to all of them. | `store.find`, `shape.reference`, `allowance.reach` |  |
| Working Memory via Task Tracking | mechanism | Store + Shape + Actor | A task Store of records {title, status, blocker, next}, written by the model through a tool action, rendered to the person, pinned through tidying. | `store.write`, `shape.record`, `actor.tool`, `store.pin`, `shape.render` | `examples/kernel/reconcile` |

**Feedback Loops**

| Pattern | Kind | Built from | Recipe | Operations | Shipped |
|---|---|---|---|---|---|
| AI-Assisted Code Review / Verification | mechanism | Flow + Actor + Shape | Ask a critic Actor for a Shape list of findings and an intent summary; ask a person (`ask-someone`) with the findings shown as quoted data. | `flow.ask`, `actor.model`, `shape.record`, `actor.person`, `label.fence` |  |
| Background Agent with CI Feedback | mechanism | Flow + Store + Check | `starts-when` a CI result arrives for this branch (correlation key); a fork of the repo Store is the branch; repeat, metered: ask the coder, ask the CI tool, until a Check says green or a handler says blocked. | `flow.starts-when`, `store.fork`, `flow.then`, `allowance.quantity`, `actor.tool`, `check.compare` |  |
| Deterministic Grader in the Loop | mechanism | Actor + Check + Flow | `eval-rule.program`: a pure program Actor scores and answers a Shape of raw counts; a Check sets the threshold; repeat until it passes, metered. | `actor.program`, `shape.record`, `check.compare`, `flow.then`, `allowance.quantity` | `examples/refund-desk/evals/suite.yaml` |
| Dogfooding with Rapid Iteration for Agent Improvement | practice | Store + Flow | A feedback port writes a Store (the low-friction channel); `evals.population: past-runs` grades the team's own runs; a `release` handler with a person Actor gates each change to the definition Store. Deciding to use the agent daily is a team's choice. | `flow.starts-when`, `store.write`, `store.host`, `flow.handler`, `actor.person`, `allowance.write` |  |
| Graph of Thoughts (GoT) | mechanism | Store + Flow + Check | Tree-of-Thought (fork per node, frontier Store merged top-n) plus an aggregating ask over several frontier entries that writes one result back. | `store.fork`, `store.merge`, `flow.split`, `flow.join`, `flow.ask`, `check.compare` |  |
| Incident-to-Eval Synthesis | mechanism | Flow + Store + Check | `starts-when` an incident is written; ask a synthesiser for a case; Check its Shape; write it to the eval cases Store in the `quarantine` split until reviewed; `must-pass` gates release. | `flow.starts-when`, `flow.ask`, `shape.validate`, `store.write`, `check.aggregate` | `examples/refund-desk/evals/suite.yaml` |
| Inference-Healed Code Review Reward | mechanism | Actor + Check + Shape | Ask a critic Actor for a Shape of per-criterion scores with reasons (`evals.metrics`, `graded-by`); a pure program combines them; a Check sets the bar. | `actor.model`, `shape.record`, `actor.program`, `check.compare` |  |
| Iterative Prompt & Skill Refinement | mechanism | Flow + Store + Allowance | A feedback port writes a Store; the learning Flow proposes changes limited to `phrasing` and `skill-notes` (`may-improve-on-its-own`), kept only if evals improve; anything else needs a person. | `flow.starts-when`, `store.write`, `allowance.write`, `check.aggregate`, `actor.person` | `examples/kernel/governed-change` |
| Reflection Loop | mechanism | Flow + Check + Actor | Repeat, metered: ask the generator; ask the critic with a rubric Shape; until a Check says the score clears the threshold. | `flow.then`, `allowance.quantity`, `flow.ask`, `shape.record`, `check.compare` | `spec/loops/reflexion.yaml` |
| Rendered UI Finish Gate | mechanism | Check + Actor + Shape | A renderer tool Actor produces the page; the design contract is a Shape; each required state is a closed `one of`, each Checked; the gate is `must-pass` before release. | `actor.tool`, `shape.one-of`, `check.combine`, `check.aggregate` |  |
| Rich Feedback Loops > Perfect Prompts | mechanism | Actor + Store + Flow | Tool Actors answer with compiler, test and lint output as a Shape written to the conversation Store; the next turn of the ReAct Flow reads it. | `actor.tool`, `shape.record`, `store.write`, `store.host`, `flow.then` | `spec/loops/react.yaml` |
| Self-Critique Evaluator Loop | training | Actor + Store + Check | A judge Actor compares candidate answers and writes preference records to a Store; a trainer tool Actor reads that Store and writes a new judge model to the catalogue Store; law 8 makes the new judge pass the evals before it becomes `graded-by`. The weight update is inside the trainer Actor. | `actor.model`, `store.write`, `actor.tool`, `store.host`, `actor.instantiate`, `check.aggregate` |  |
| Spec-As-Test Feedback Loop | mechanism | Flow + Check + Actor | `starts-when` a commit arrives; ask a test generator; ask the test runner tool; Check; route by outcome to a fixer ask or to `ask-someone` about an unclear spec clause. | `flow.starts-when`, `flow.ask`, `actor.tool`, `check.compare`, `flow.then`, `actor.person` |  |
| Tool Use Incentivization via Reward Shaping | training | Check + Actor | The reward is a Check aggregate over the run record (counts of compile, lint and test asks per episode) written to a Store; a trainer tool Actor consumes it and writes a new model to the catalogue Store under law 8. | `check.count`, `check.aggregate`, `store.write`, `actor.tool`, `store.host` |  |

**Learning & Adaptation**

| Pattern | Kind | Built from | Recipe | Operations | Shipped |
|---|---|---|---|---|---|
| Agent Reinforcement Fine-Tuning (Agent RFT) | training | Actor + Check + Store | Episodes run under a sandbox Actor and are recorded in the run record; graders are eval Checks or program Actors; a trainer tool Actor reads both and writes a new model Actor to the catalogue Store with figures from the eval run; law 8 gates its use. | `actor.location`, `store.host`, `check.aggregate`, `actor.program`, `actor.tool`, `actor.figures`, `actor.instantiate` |  |
| Commitment Ledger with Reality-Gated Credit | mechanism | Store + Flow + Check | A Store of promises {claim, outcome Check, credit}; an `await` on the external outcome arriving before the credit field is written; `find` ranks by credit. | `store.write`, `flow.await`, `check.compare`, `store.find` |  |
| Compounding Engineering Pattern | mechanism | Flow + Store + Allowance | After each run, the learning Flow writes skill notes, handlers (hooks) and helpers to the definition Store, under `needs-a-person-to-approve` and law 5. | `flow.handler`, `store.write`, `allowance.write`, `allowance.pass` | `examples/refund-desk/learning.yaml` |
| Frontier-Focused Development | practice | Actor + Check | The model is an Actor referenced by requirement: `needs:` with `prefer: best-on-the-evals`, resolved against the catalogue Store by a Check over benchmark figures; no model name is pinned. Choosing to rework often is a strategy. | `actor.by-requirement`, `store.host`, `check.compare`, `actor.figures` |  |
| Memory Reinforcement Learning (MemRL) | mechanism | Store + Actor + Flow | Store entries carry a utility score; `find` by meaning, then `reranked-by` a pure program over utility; an after-handler writes score updates with the add-up merge rule. | `store.find`, `actor.program`, `flow.handler`, `store.merge` |  |
| Merged Code + Language Skill Model | training | Actor + Flow | Two trainer asks in a split (`together`), each writing a specialist to the catalogue Store; a merge program Actor writes the merged model; evals Check it before `needs:` may resolve to it. | `flow.split`, `actor.tool`, `store.host`, `actor.program`, `check.aggregate`, `actor.by-requirement` |  |
| Persistent Test Memory Feedback Loop | mechanism | Store + Check + Flow | A workspace Store of test lessons, `kept-for` with a forget when a staleness Check holds; `find` before running tests; written after. | `store.scope`, `store.lifetime`, `store.forget`, `check.compare`, `store.find`, `store.write` |  |
| Self-Discover: LLM Self-Composed Reasoning Structures | mechanism | Store + Flow + Shape | A Store of reasoning modules (reviewed definition); the model picks a subset and an order from a closed `one of`; the result is instantiated as a Flow (law 8) and run. | `store.read`, `shape.one-of`, `actor.instantiate`, `flow.name` |  |
| Shipping as Research | practice | Store + Check | Each feature is a definition Store version; a `choose` by digest routes a slice of runs to it; evals over past runs feed a Check; a person decides through `release` whether the version stays or the previous one is written back. | `store.version`, `flow.choose`, `shape.digest`, `check.aggregate`, `actor.person`, `allowance.write` |  |
| Skill Library Evolution | mechanism | Store + Actor + Check | Ask the model for a program; ask the sandbox to test it; Check the tests pass; write it to the definition Store (Allowance: pure programs only); later asks `find` it on demand. | `flow.ask`, `actor.tool`, `check.compare`, `store.write`, `allowance.write`, `store.find`, `actor.instantiate` | `examples/refund-desk/skills/refund-policy` |
| Variance-Based RL Sample Selection | training | Flow + Check + Store | Split N asks from one fork per sample; a Check over the variance of the scores keeps a sample only when it is neither always right nor always wrong; the kept set is a Store the trainer tool Actor reads. | `flow.split`, `store.fork`, `check.aggregate`, `store.write`, `actor.tool` |  |

**Orchestration & Control**

| Pattern | Kind | Built from | Recipe | Operations | Shipped |
|---|---|---|---|---|---|
| 402-First Machine Payments (Price-Before-Work Tool Purchases) | mechanism | Allowance + Check + Store | Ask the tool; the outcome `price-quoted` carries an amount; a Check compares it with the remaining money Allowance; claim a payment key; ask pay; ask again with the receipt. | `flow.ask`, `flow.then`, `check.typed`, `allowance.quantity`, `store.claim` |  |
| Action-Selector Pattern | mechanism | Shape + Allowance + Origin | The model answers a closed `one of` pre-approved action ids with Shape-validated parameters; the Flow asks that action; its answer carries the tool-output Origin and the selector has no Allowance to see it. | `shape.one-of`, `shape.validate`, `flow.ask`, `label.origin`, `allowance.see` | `examples/kernel/triage` |
| Agent Modes by Model Personality | mechanism | Flow + Check + Allowance | One `variants:` entry per mode with its own instructions, `may-use` and settings; chosen by a Check on the run input that names the mode. | `flow.choose`, `check.compare`, `allowance.reach`, `actor.model` | `examples/refund-desk/agents/refund-desk/agent.yaml` |
| Agent-Driven Research | mechanism | Flow + Actor + Check | Repeat, metered: ask a planner for a Shape list of queries; split each search tool; join; ask a reflector for gaps; until a Check says none; answer with `must-cite`. | `flow.then`, `allowance.quantity`, `flow.ask`, `shape.record`, `flow.split`, `flow.join`, `check.compare` | `spec/loops/react.yaml` |
| Artifact-Driven Analysis Pipeline Orchestration | mechanism | Flow + Actor + Store | Split each analysis program Actor; each writes a Shape report to a Store; join; ask a merger over the Store. | `flow.split`, `actor.program`, `shape.record`, `store.write`, `flow.join`, `flow.ask` |  |
| Autonomous Workflow Agent Architecture | mechanism | Actor + Store + Flow | A sandbox Actor (`runs-in`), a checkpoint Store, `await` with deadlines for the monitoring sleeps, and failure handlers with `carry-on-with` and `undo`. | `actor.location`, `store.durability`, `flow.await`, `flow.handler`, `allowance.pause` |  |
| Board-Mediated Async Inter-Agent Coordination | mechanism | Store + Flow + Origin | A team-scope board Store of cards with comment threads (merge keep-all); a prefixed write also creates an inbox entry; the target Flow `await`s its inbox. | `store.scope`, `store.merge`, `store.write`, `flow.await`, `store.host` | `examples/kernel/blackboard` |
| Budget-Aware Model Routing with Hard Cost Caps | mechanism | Flow + Allowance + Check | `choose` by rungs, cheapest model first (`prefer: cheapest`); a quality Check gates each rung; escalate only on failure; a money Allowance is the hard cap. | `flow.choose`, `actor.by-requirement`, `check.compare`, `allowance.quantity` |  |
| Burn the Boats | practice | Store + Check | The old feature is a definition version with `locked-until` the announced date; a clock `starts-when` on that date writes the removal and a Check refuses references to it afterwards. Announcing the date is a decision. | `store.version`, `allowance.revoke`, `flow.starts-when`, `store.write`, `check.reachability` |  |
| Capability-Escrow-Receipt | mechanism | Allowance + Store + Actor | The capability listing is an Actor description signed by its identity; escrow is an Allowance value moved into a Store by a claim atomic with the hire ask; the receipt is a signed run-record entry; a Check on it releases the funds. | `actor.identity`, `allowance.value`, `store.claim`, `flow.ask`, `store.host`, `check.digest` |  |
| Classify-Then-Act for Background Agents | mechanism | Flow + Check + Store | `choose` one of {has-default, needs-intent, out-of-scope} by rungs; only has-default is built, in a sandbox fork; the result is written to a review queue Store for a person Actor. | `flow.choose`, `shape.one-of`, `store.fork`, `store.write`, `actor.person` |  |
| Conditional Parallel Tool Execution | mechanism | Check + Flow + Actor | A Check reads the effect class of every requested action; all reads-only runs them `together`, otherwise one after another; the join keeps request order (`ordered-by`). | `actor.effect`, `check.compare`, `flow.split`, `flow.join`, `flow.then` | `examples/kernel/map-reduce` |
| Continuous Autonomous Task Loop Pattern | mechanism | Store + Flow + Allowance | Repeat, metered: take (claim then forget) the top task from a Store; ask a worker in a fresh fork; commit through a tool; a rate-limit outcome routes to an `await` whose length is an Allowance per period. | `flow.then`, `allowance.quantity`, `store.claim`, `store.forget`, `store.fork`, `actor.tool`, `flow.await`, `allowance.period` |  |
| Cross-Cycle Consensus Relay | mechanism | Store + Shape + Flow | The relay document is one Store entry {decisions, questions, next action}; each cycle reads it, works, and writes it back by compare-and-swap claim, so the write is atomic. | `shape.record`, `store.read`, `store.claim`, `store.write` |  |
| Cross-Domain Agent Conflict Resolution | mechanism | Store + Check + Actor | Recommendations are written to a Store keyed by resource; a Check finds two that disagree on one key; a pure program policy picks one of a closed set, else `ask-someone`. | `store.write`, `check.compare`, `actor.program`, `shape.one-of`, `actor.person` |  |
| Custom Sandboxed Background Agent | mechanism | Actor + Shape + Flow | A sandbox Actor; progress is a `stream of` parts to a port; repeat on compiler and test feedback, metered. | `actor.location`, `shape.stream`, `flow.starts-when`, `flow.then`, `allowance.quantity` |  |
| Declarative Multi-Agent Topology Definition | pact | Flow + Actor + Allowance | This is a PACT workspace: agents, workflows, gates (Checks and questions) and hooks (handlers) in one tree, lowered by adapters to each framework. | `flow.name`, `actor.composite`, `flow.handler`, `check.compare`, `allowance.reach` |  |
| Design-Time File Partition as Concurrency Control | mechanism | Store + Check + Flow | Each task declares its write set (a Shape list of Store paths); a Check for overlap between pending tasks adds an `await` on the other's completion; a claim on each path enforces it at run time. | `actor.write-set`, `check.compare`, `flow.await`, `store.claim` |  |
| Deterministic Zero-LLM Orchestration | mechanism | Actor + Flow + Check | A program Actor is the coordinator (`decided-by`); one model ask for the decomposition; split each coding Actor; a Check on the tests; a commit tool. | `actor.program`, `flow.choose`, `flow.ask`, `flow.split`, `check.compare`, `actor.tool` |  |
| Discrete Phase Separation | mechanism | Flow + Store + Shape | Three scopes, each with an isolated conversation fork; only Shape-typed Store writes (the distilled output) cross from one to the next. | `flow.scope`, `store.fork`, `store.write`, `shape.record` | `examples/kernel/phases` |
| Disposable Scaffolding Over Durable Features | practice | Flow + Check | Scaffolding is a `variants:` entry; evals run both variants over the same cases; when a Check says the plain model passes without it, the variant is removed by a write to the definition Store under `release`. | `flow.choose`, `check.aggregate`, `store.write`, `allowance.write` |  |
| Distributed Execution with Cloud Workers | mechanism | Flow + Store + Actor | Split each over a plan Store with an `await` on each task's dependencies being written; each branch is a fork of the repo Store (a worktree) on a remote Actor; join; a merge tool; approval gates are `ask-someone`. | `flow.split`, `flow.await`, `store.fork`, `actor.remote`, `flow.join`, `actor.tool`, `actor.person` |  |
| Dual LLM Pattern | mechanism | Origin + Allowance + Actor | The privileged model may see only values whose Origin is reviewed definition or customer; the quarantined model has no reach to tools; its answers carry the tool-output Origin and are fenced (law 7). | `allowance.see`, `label.origin`, `allowance.reach`, `label.propagate`, `label.fence` |  |
| Dual-Rail Message Delivery | mechanism | Store + Flow + Check | One write fans out to two Stores (the rails); the receiver `await`s both; a Check that they agree, with an alert handler when they do not; the ACK is a write back, awaited with a deadline. | `store.write`, `flow.await`, `check.compare`, `flow.handler` |  |
| Explicit Posterior-Sampling Planner | mechanism | Store + Actor + Check | The posterior is a Store value; sampling is a nondeterministic program Actor; plan and act are asks; a Check reads the reward from the outcome; a merge program writes the update. | `store.read`, `actor.program`, `flow.ask`, `check.compare`, `store.merge` |  |
| Factory over Assistant | mechanism | Flow + Allowance + Store | Split each worker with a fork and a narrowed Allowance, detached with run references; `starts-when` test and build arrivals feed each; a person reviews later from the run registry. | `flow.split`, `store.fork`, `allowance.pass`, `flow.detach`, `flow.starts-when`, `store.host` |  |
| Fair-Share Task Queues with Heartbeat Leases | mechanism | Store + Flow + Check | A task Store with claim and lease; a clock `starts-when` renews the lease (heartbeat); an expired lease forgets the claim so the task reappears; a pure program picks the next by weighted deficit; a Check on the failure count moves a task to a dead-letter Store. | `store.claim`, `flow.starts-when`, `store.forget`, `actor.program`, `check.count`, `store.write` | `examples/kernel/work-queue` |
| Feature List as Immutable Contract | mechanism | Store + Origin + Check | The feature list is a Store with the reviewed-definition Origin; a status write is admitted only when a Check finds a verification entry for that feature in the run record, never from the model's word alone. | `label.origin`, `check.count`, `allowance.write`, `store.write` |  |
| Hybrid LLM/Code Workflow Coordinator | mechanism | Actor + Flow | The coordinator of a Flow is an Actor chosen per workflow: a model or a program (`decided-by`), with the same Shape signature either way. | `actor.model`, `actor.program`, `actor.signature`, `flow.choose` |  |
| Inference-Time Scaling | mechanism | Flow + Store + Check | A composition: split N from one fork with a vote merge; `settings.thinking`; repeat with a critic; Tree-of-Thought; a verifier Check. | `flow.split`, `store.fork`, `store.merge`, `actor.model`, `flow.then`, `check.compare` |  |
| Initializer-Maintainer Dual Agent Architecture | mechanism | Store + Flow | A workspace-scope claim 'initialised' guards the one-time Flow; a durable Store holds the feature list and progress; the maintainer Flow takes one feature per run. | `store.claim`, `store.durability`, `flow.name`, `store.forget` |  |
| Inversion of Control | mechanism | Flow + Allowance + Actor | The ReAct Flow: tools as Actors, the objective as input, guardrails as Allowances and handlers; the model orders the asks inside them; people set the policy and review the run record. | `flow.ask`, `actor.tool`, `allowance.reach`, `flow.handler`, `actor.model`, `store.host` | `spec/loops/react.yaml` |
| Iterative Multi-Agent Brainstorming | mechanism | Flow + Store | Split N asks from one fork, each with different instructions; join everyone; ask a merger (`combines-by`). | `flow.split`, `store.fork`, `flow.join`, `store.merge` |  |
| Judge-Gated Finding Exchange Between Parallel Sub-Agents | mechanism | Store + Actor + Origin | An append-only board Store; a small judge Actor decides admission from a closed `one of` and sets a recipient Origin on each note; a retraction is a later write whose merge rule supersedes by key. | `store.merge`, `actor.model`, `shape.one-of`, `allowance.see`, `store.write` |  |
| LLM Map-Reduce Pattern | mechanism | Flow + Origin + Actor | Split each document into its own fork with a quarantined Actor and a constrained Shape answer; a program Actor aggregates (`combines-by` a program). | `flow.split`, `store.fork`, `allowance.reach`, `shape.validate`, `actor.program`, `store.merge` | `examples/kernel/map-reduce` |
| Lane-Based Execution Queueing | mechanism | Allowance + Store + Flow | A concurrency Allowance `counted-per` lane (a Store key); the run registry with `if-still-running: queue`. | `allowance.quantity`, `allowance.period`, `store.host`, `flow.starts-when` | `examples/kernel/lanes` |
| Language Agent Tree Search (LATS) | mechanism | Store + Flow + Actor | Tree-of-Thought plus a visits-and-value Store merged by add-up (back-propagation) and a pure program for the selection rule. | `store.fork`, `store.merge`, `actor.program`, `flow.split`, `flow.join` | `examples/kernel/tree-search` |
| Markdown Polis — Multi-Vendor Agent Coordination via Filesystem Constitution | mechanism | Store + Origin + Check | Capability cards and work contracts are versioned Store entries with the reviewed Origin; routing is a pure program over a Store of settled outcomes (the bandit), choosing from a closed set (law 6). | `store.version`, `label.origin`, `actor.program`, `store.read`, `flow.choose`, `shape.one-of` |  |
| Multi-Model Orchestration for Complex Edits | mechanism | Flow + Actor | `then`: a retrieval model ask, a large model ask, then split each hunk to a small apply model. | `flow.then`, `actor.model`, `flow.split` |  |
| Non-Generative Judgment Routing with Typed Escalation | mechanism | Flow + Actor + Check | A `choose` rung with a decision-kind model Actor answering a typed `one of`; `if-unsure-below` sends the rest to the next rung, the LLM; a batch is split each question. | `flow.choose`, `actor.model`, `shape.one-of`, `flow.split` | `examples/kernel/triage` |
| Opponent Processor / Multi-Agent Debate Pattern | mechanism | Flow + Store + Origin | Split the sides from one fork; each round writes a shared transcript Store; ask a judge; metered. | `flow.split`, `store.fork`, `store.write`, `flow.ask`, `allowance.quantity` | `examples/patterns/debate` |
| Oracle and Worker Multi-Model Approach | mechanism | Flow + Check + Allowance | The worker model runs the Flow; a Check 'stuck' (n failed attempts in the run record) routes to an oracle ask; a money Allowance on oracle calls. | `actor.model`, `check.count`, `flow.then`, `allowance.quantity` | `examples/kernel/fallback` |
| Parallel Tool Call Learning | training | Actor | Training data is the run record filtered by a Check for independent asks; a trainer tool Actor writes the new model; at run time the capability is `model-can.tool-calling: parallel` and `together` in the Flow. | `store.host`, `check.count`, `actor.tool`, `actor.model`, `flow.split` |  |
| Plan-Then-Execute Pattern | mechanism | Store + Origin + Check | The plan is written to a Store before any tool ask; tool outputs carry the tool-output Origin and may fill only Shape-typed parameters, never choose a step (laws 6 and 7). | `store.write`, `label.origin`, `shape.validate`, `check.origin`, `flow.then` |  |
| Planner-Worker Separation for Long-Running Agents | mechanism | Flow + Store + Actor | A planner writes a task Store; workers are split each in isolated forks; a judge ask answers `one of` continue or stop; repeat, metered. | `store.write`, `flow.split`, `store.fork`, `flow.ask`, `shape.one-of`, `flow.then`, `allowance.quantity` |  |
| Progressive Autonomy with Model Evolution | practice | Check + Flow | On each catalogue Store change (`starts-when`), evals run every variant against the new model Actor; a Check compares scores; variants the new model no longer needs are proposed for removal and a person approves through `release`. | `flow.starts-when`, `check.aggregate`, `actor.person`, `allowance.write` |  |
| Progressive Complexity Escalation | mechanism | Allowance + Check + Actor | Tiers are Allowance levels; a Check over metrics plus a person's approval through `release` widens the Allowance. The owner sits above the agent, so law 5 allows it. | `allowance.quantity`, `check.aggregate`, `actor.person`, `allowance.write`, `allowance.pass` |  |
| Recursive Best-of-N Delegation | mechanism | Flow + Check + Allowance | Split each subtask into N candidate workers, recursively within `nests-at-most`; tests and a judge score; the merge rule keeps the top one and it moves up. | `flow.split`, `allowance.start`, `check.compare`, `store.merge` |  |
| Self-Rewriting Meta-Prompt Loop | mechanism | Flow + Store + Allowance | The learning recipe with proposals limited to `phrasing`; guardrails are Checks and law 5; the new version is written to the definition Store. | `flow.ask`, `check.compare`, `allowance.pass`, `store.write`, `store.version` | `examples/kernel/governed-change` |
| Signal-Driven Agent Activation | mechanism | Flow + Check + Allowance | `starts-when` a Check over a watched Store crosses its threshold; the cooldown is an Allowance on starts per period; the rules are Checks. | `flow.starts-when`, `check.compare`, `allowance.period`, `allowance.start` | `examples/kernel/lanes` |
| Specification-Driven Agent Development | pact | Store | The PACT tree is the spec; `based-on: name@version` links every copy back to the clause it came from. | `store.version`, `store.host` |  |
| Stop Hook Auto-Continue Pattern | mechanism | Flow + Check + Allowance | A handler at the end of the scope Checks the success criteria; if they fail, `then` routes back to work; the Allowance on repeats bounds it. | `flow.handler`, `check.compare`, `flow.then`, `allowance.quantity` | `examples/refund-desk/loops/careful.yaml` |
| Sub-Agent Spawning | mechanism | Flow + Allowance + Store | Split each helper with a fork (fresh context) and a narrowed `may-use` Allowance; join; `combines-by`. | `flow.split`, `store.fork`, `allowance.pass`, `flow.join`, `store.merge` | `examples/patterns/swarm` |
| Subject Hygiene for Task Delegation | mechanism | Shape + Check | A Shape rule on the delegation's subject (action plus target as required record parts), Checked at ask time. | `shape.record`, `shape.validate` |  |
| Swarm Migration Pattern | mechanism | Flow + Store + Allowance | Split each chunk under an item ceiling; each worker is a fork with a claim on its disjoint write set; join everyone; a merge tool. | `flow.split`, `allowance.quantity`, `store.fork`, `store.claim`, `actor.write-set`, `flow.join`, `actor.tool` |  |
| Three-Stage Perception Architecture | mechanism | Flow + Actor + Shape | Three named Flows (so, three Actors) in sequence, each with its own Shape signature and its own evals. | `flow.name`, `actor.composite`, `actor.signature`, `check.aggregate` |  |
| Tool Capability Compartmentalization | mechanism | Allowance + Origin + Check | Tool classes are Allowances (read, process, write); private data and untrusted input are Origins; a reachability Check over the tree refuses any path that combines all three. | `allowance.reach`, `label.origin`, `label.sensitivity`, `check.reachability` |  |
| Tool Selection Guide | practice | Actor | Instructions in the reviewed definition (Origin: reviewed, so they instruct) plus each skill's `use-when` and `do-not-use-when`, which are Checks a `choose` rung reads before any model is asked. | `label.fence`, `check.compare`, `flow.choose` |  |
| Tracker-as-Desired-State Reconciliation | mechanism | Flow + Check + Store | A clock `starts-when` re-reads the tracker Store every tick (level-triggered: a Check that actual differs from desired); only a short-lease claim is kept locally; missed events heal on the next tick. | `flow.starts-when`, `store.read`, `check.compare`, `store.claim` | `examples/kernel/reconcile` |
| Tree-of-Thought Reasoning | mechanism | Store + Flow + Check | A frontier Store merged top-n by score; repeat to depth d: split each node in a fork from its snapshot, ask for children, ask an evaluator, write back. Pruning is the merge rule. | `store.merge`, `flow.then`, `store.fork`, `flow.split`, `flow.ask`, `check.compare` | `spec/loops/tree-of-thought.yaml` |
| Workspace-Native Multi-Agent Orchestration | mechanism | Store + Flow + Actor | The host Stores (the workspace's memory, directory and inbox) plus ports as `starts-when`; the platform's integrations are tool Actors. | `store.host`, `flow.starts-when`, `actor.tool` |  |

**Reliability & Eval**

| Pattern | Kind | Built from | Recipe | Operations | Shipped |
|---|---|---|---|---|---|
| Action Caching & Replay Pattern | mechanism | Store + Actor + Flow | A Store of recorded actions keyed by the step's digest; a replay Actor answers from it first; a failure outcome routes to the model as `backup`. | `shape.digest`, `store.read`, `actor.program`, `flow.then`, `flow.handler` |  |
| Adaptive Sandbox Fan-Out Controller | mechanism | Flow + Check + Allowance | Split in batches over a Store that grows; join; a Check over the aggregates (success rate, variance) chooses scale up, stop or rewrite the prompt; metered. | `flow.split`, `flow.join`, `check.aggregate`, `flow.choose`, `allowance.quantity` |  |
| Agent Circuit Breaker | mechanism | Check + Allowance + Flow | A Check on the failure rate over the last k asks of one tool in the run record revokes that tool's Allowance for a period; a handler routes to a backup meanwhile. | `check.count`, `check.aggregate`, `allowance.revoke`, `flow.handler` | `examples/kernel/circuit-breaker` |
| Anti-Reward-Hacking Grader Design | mechanism | Check + Actor + Store | The grader is several Checks and judge Actors combined by a pure program; `must-pass`; hardening is adding cases to the eval Store, as incident-to-eval does. | `check.combine`, `actor.model`, `actor.program`, `check.aggregate`, `store.write` |  |
| Approval-Bound Transactional Write | mechanism | Check + Store + Flow | The approval record carries the digest of the plan version; the Allowance condition is a Check that the digest matches and has not expired; claim the idempotency key, ask the write, Check the postcondition; on failure undo and forget the claim. | `shape.digest`, `check.digest`, `store.lifetime`, `store.claim`, `flow.ask`, `check.compare`, `flow.handler`, `store.forget` | `examples/refund-desk/tools/payments.yaml` |
| Asynchronous Coding Agent Pipeline | mechanism | Store + Flow + Actor | The queues are Stores with claim; each stage is a Flow started by `starts-when` an item arrives; workers run detached. | `store.claim`, `flow.starts-when`, `flow.detach` |  |
| Canary Rollout and Automatic Rollback for Agent Policy Changes | mechanism | Store + Check + Flow | Definition versions; `choose` the version by a Check `digest(run id) mod 100 < slice`; a Check on guardrail metrics over past runs; a handler writes the previous version back through `release`. | `store.version`, `flow.choose`, `shape.digest`, `check.compare`, `check.aggregate`, `flow.handler`, `store.write` | `examples/kernel/canary` |
| CriticGPT-Style Code Review | mechanism | Actor + Check + Flow | Ask a critic Actor for a Shape of findings; a Check on severity routes to a regenerate ask. | `flow.ask`, `actor.model`, `shape.record`, `check.compare`, `flow.then` |  |
| Dead-Man's Switch for Scheduled Agent Jobs | mechanism | Store + Flow + Check | The job writes a sentinel to a Store; a second `starts-when` on the clock Checks the sentinel is missing or stale, then `ask-someone` or writes a task. | `store.write`, `flow.starts-when`, `check.typed`, `actor.person` | `examples/kernel/reconcile` |
| Evidence-Layered Evaluation for Interactive Agents | mechanism | Check + Store + Shape | Eval cases with an outcome Check; the run record holds the actions, screenshots (image Shape), network and messages, linked by run reference. | `check.compare`, `store.host`, `shape.scalar`, `shape.reference` |  |
| Extended Coherence Work Sessions | mechanism | Store + Flow + Allowance | Context-policy handlers for compaction, a pinned prefix for caching, and durable Stores for persisted state. | `flow.handler`, `store.pin`, `store.durability` | `examples/refund-desk/context-policies/long-threads.yaml` |
| Failover-Aware Model Fallback | mechanism | Flow + Shape + Actor | The failure reason is an outcome label (a closed `one of`); `then` routes retryable ones to a backup model and auth, billing and abort to stop-and-say-so. | `flow.then`, `shape.one-of`, `flow.handler`, `actor.model` |  |
| LLM Observability | mechanism | Store + Actor | The run record Store, read and exported to a tool Actor; a span is an ask; cost and latency are Actor figures recorded on each. | `store.host`, `store.read`, `actor.tool`, `actor.figures` | `examples/refund-desk/watch/tool-calls.yaml` |
| No-Token-Limit Magic | mechanism | Allowance | A prototyping profile sets the Allowances very high. The checker still requires one (law 2): the limit is large, not absent. | `allowance.quantity` |  |
| Orchestration Prompt-Writing Benchmark | mechanism | Check + Actor + Shape | Evals over the orchestrator's delegation asks: the sub-prompt is a Shape graded by a judge Actor; the metric is separate from task success. | `check.aggregate`, `shape.record`, `actor.model` |  |
| Out-of-Process Provider-Boundary Replay | mechanism | Actor + Store + Flow | An interceptor on model asks replaces the model Actor with a replay Actor that answers from a Store recorded at the provider boundary. | `flow.handler`, `actor.program`, `store.read` |  |
| Output Verification Loop | mechanism | Flow + Check + Store | Ask an extractor for a Shape list of claims; split each: `find` evidence in a Store and ask a verifier for a score; combine; a Check on the threshold before acting. | `flow.ask`, `shape.record`, `flow.split`, `store.find`, `check.compare`, `store.merge` |  |
| Own-Check Fault Injection | mechanism | Flow + Check + Store | An interceptor with `change-the-answer` plants the fault; three Checks over the run record look for a detection, a reaction and a recovery entry, each its own verdict. | `flow.handler`, `check.count`, `check.combine` |  |
| RLAIF (Reinforcement Learning from AI Feedback) | training | Actor + Store + Origin | The principles are reviewed-definition text (Origin: reviewed); a judge model Actor writes preference labels to a Store; a trainer tool Actor reads it and writes a reward model, then a policy, to the catalogue Store under law 8. | `label.fence`, `actor.model`, `store.write`, `actor.tool`, `store.host` |  |
| Reasoning-Token Firewall | mechanism | Shape + Store | The answer is a `stream of` parts and each part carries a kind (answer, reasoning, tool call); the result is combined from answer-kind parts only, by the merge rule, never by stripping text. | `shape.stream`, `store.merge` |  |
| Reliability Problem Map Checklist for RAG and Agents | mechanism | Check + Flow + Store | A Flow of sixteen Checks per incident, each mapping to a repair action from a closed set; the failing case is re-run from the eval Store. | `check.combine`, `flow.choose`, `shape.one-of`, `store.read` |  |
| Schema Validation Retry with Cross-Step Learning | mechanism | Shape + Flow + Store | A Shape validation failure is an outcome carrying the error; `if-it-fails` retries with the error in the conversation; a Store of recent errors is read into later asks. | `shape.validate`, `flow.then`, `flow.handler`, `store.write`, `store.read` | `examples/kernel/fallback` |
| Skill Activation as a Precision/Recall Measurement | mechanism | Check + Store | Eval cases of labelled prompt to expected skill; precision and recall are metrics; `must-pass` thresholds fail the release. | `check.aggregate`, `store.host`, `flow.handler` |  |
| Structured Output Specification | mechanism | Shape | `answers-with` a Shape, enforced by `answers-with-mode` (native schema, tool or prompted) on the chosen model. | `shape.record`, `shape.validate`, `shape.describe` | `examples/refund-desk` |
| Subagent Compilation Checker | mechanism | Flow + Actor + Shape | Split each module to a helper in a fork with the compiler tool; the helper answers a short Shape error list or a Store reference; join. | `flow.split`, `store.fork`, `actor.tool`, `shape.record`, `shape.reference`, `flow.join` | `examples/kernel/map-reduce` |
| Tier Auto-Apply by Mechanical Impact | mechanism | Check + Store + Allowance | The learning Flow diffs the proposed change into which parts changed; a Check against a tier table Store (paths by change kind) decides auto-apply or `needs-a-person-to-approve`. | `store.version`, `check.compare`, `store.read`, `allowance.write` | `examples/kernel/governed-change` |
| Versioned Constitution Governance | mechanism | Store + Flow + Allowance | The definition Store is signed and versioned; `learning.enabled: propose-only`; the `release` handler asks reviewers and a CI Check before the version goes live. | `store.version`, `actor.identity`, `allowance.write`, `flow.handler`, `actor.person`, `check.compare` | `examples/kernel/governed-change` |
| Workflow Evals with Mocked Tools | mechanism | Check + Actor + Flow | Evals run the Flow with tool Actors replaced by replay Actors; `must-call-before` Checks the call order; `graded-by` a judge for quality. | `actor.program`, `check.count`, `check.aggregate`, `actor.model` | `examples/kernel/governed-change` |

**Security & Safety**

| Pattern | Kind | Built from | Recipe | Operations | Shipped |
|---|---|---|---|---|---|
| Authenticated Authority Channel | mechanism | Origin + Allowance | Law 7: only text with the reviewed-definition or person Origin may instruct; retrieved content reaches the model fenced as data and can inform but not command. | `label.origin`, `label.fence`, `allowance.see` |  |
| Black-Box Skill Invocation | mechanism | Actor + Shape + Allowance | A remote Actor exposed by its Shape signature only (`published-as: tool`); the caller's Allowance sees inputs and outputs, never the body. | `actor.remote`, `actor.signature`, `shape.describe`, `allowance.see` |  |
| Consequence-Family Coverage Audit | mechanism | Check + Flow | A checker rule: for each effect class and consequence family, a reachability Check that some handler or policy covers it. | `check.reachability`, `actor.effect`, `flow.handler` |  |
| Cryptographic Governance Audit Trail | mechanism | Flow + Store + Check | Every ask passes a policy Check in a handler; the run-record entry is signed by the Actor's identity and chained by the digest of the previous entry. | `flow.handler`, `check.compare`, `actor.identity`, `store.host`, `shape.digest` |  |
| Denial Tracking & Permission Escalation | mechanism | Check + Flow + Allowance | A Check on the count of refusals in the run record reaching n; a handler asks a person for a wider Allowance or routes to a fallback Flow. | `check.count`, `flow.handler`, `actor.person`, `allowance.reach` | `examples/refund-desk/questions/keep-going.yaml` |
| Deterministic Security Scanning Build Loop | mechanism | Actor + Check + Flow | Scanner tool Actors in a repeat; a Check on each exit code; `must-pass` before the answer. | `actor.tool`, `flow.then`, `check.compare`, `check.aggregate` |  |
| Deterministic Threat Rule Scanning | mechanism | Check + Flow | A before-handler on tool asks and on skill text with a Check that matches author-declared detectors (the regex rules). | `flow.handler`, `check.detector` |  |
| Evidence Questions, Not Verdict Questions | mechanism | Check + Shape + Actor | Law 6 exactly: models answer narrow, typed Shape questions; a Check or pure program reduces the answers to allow, ask or block. | `shape.one-of`, `actor.model`, `check.combine`, `actor.program` | `examples/kernel/triage` |
| Exact-Action Authorization Binding | mechanism | Check + Store + Shape | The approval record carries the digest of the complete ask as shown to the reviewer; at the acting boundary a Check recomputes it and compares; `kept-for` makes it short-lived. | `shape.digest`, `check.digest`, `store.lifetime`, `store.host` | `examples/refund-desk/policies/approvals.yaml` |
| External Credential Sync | mechanism | Allowance + Store | A credential reference (Allowance: use without seeing) resolved from a host Store with a lifetime; a claim is the refresh fence. | `allowance.use-without-seeing`, `store.lifetime`, `store.claim`, `store.host` |  |
| Hook-Based Safety Guard Rails for Autonomous Code Agents | mechanism | Flow + Check | Before and after handlers on tool asks; a Check matching declared detectors blocks a destructive command (`stop-the-run`) or lints an edit (`change-the-request`). | `flow.handler`, `check.detector` | `examples/refund-desk` |
| Isolated VM per RL Rollout | mechanism | Flow + Actor + Allowance | Each branch of the split is a fork with its own sandbox Actor location; the Allowance confines reach to that sandbox. | `flow.split`, `store.fork`, `actor.location`, `allowance.reach` |  |
| Lethal Trifecta Threat Model | mechanism | Origin + Allowance + Check | Private data is an Origin; exposure to untrusted content is an Origin; external communication is an Allowance to reach; a reachability Check refuses any path that has all three. | `label.sensitivity`, `label.origin`, `allowance.reach`, `check.reachability` | `examples/kernel/no-leak` |
| Local-First Credential Broker | mechanism | Allowance + Origin + Store | The secret stays in a host Store; the Actor holds a placeholder reference it may use without seeing; the host restores the real value at the network boundary. | `label.placeholder`, `allowance.use-without-seeing`, `store.host`, `label.region` |  |
| Non-Custodial Spending Controls | mechanism | Flow + Check + Allowance | A before-handler on spending asks: a Check against the allowlist, a money Allowance and a rate per period; fails closed (law 4). | `flow.handler`, `check.compare`, `allowance.quantity`, `allowance.period`, `allowance.reach` | `examples/refund-desk/policies/approvals.yaml` |
| One OS User per Agent | mechanism | Actor + Allowance | The Actor's identity and location are supplied by the host; its Allowance is the OS user's. | `actor.identity`, `actor.location`, `allowance.reach` |  |
| PII Tokenization | mechanism | Origin + Flow + Allowance | A detector Check stamps the value *sensitive* (Origin); the handler replaces the value with a host-issued placeholder; on an outgoing tool ask with use-without-seeing, the host restores it. | `check.detector`, `label.sensitivity`, `label.placeholder`, `flow.handler`, `allowance.use-without-seeing` | `examples/kernel/private-by-placeholder` |
| Policy-Gated Tool Proxy | mechanism | Flow + Check + Store | A handler on every tool ask at workspace scope (`applies-to: every-agent`) with a policy Check; the run record is the immutable audit. | `flow.handler`, `flow.scope`, `check.combine`, `store.host` |  |
| Sandboxed Tool Authorization | mechanism | Allowance | Deny-first allow and deny patterns are an Allowance; profiles are named Allowances; helpers inherit by attenuation (law 5). | `allowance.reach`, `allowance.pass` | `examples/refund-desk/agents/refund-desk/agent.yaml` |
| Soulbound Identity Verification | mechanism | Actor + Store + Check | A non-transferable identity is a host-issued reference on the Actor; signed state changes go to a Store chained by digest; a Check tests continuity. | `actor.identity`, `shape.reference`, `store.write`, `shape.digest`, `check.compare` |  |
| Transitive Vouch-Chain Trust | mechanism | Store + Actor + Check | A Store graph of signed vouches; a pure program derives trust with decay per hop; a Check on the threshold decides reach. | `store.write`, `actor.program`, `check.compare`, `allowance.reach`, `actor.identity` |  |
| Zero-Knowledge Verified Agent Egress | mechanism | Flow + Actor + Check | A before-handler on egress asks asks a prover Actor over the private Store; a Check on the proof; refuse when it fails. | `flow.handler`, `flow.ask`, `check.compare`, `allowance.reach` |  |
| Zero-Trust Agent Mesh | mechanism | Actor + Allowance + Check | Every remote ask carries the Actor's identity, an attenuated Allowance value (the delegation token) and the nesting depth (`nests-at-most`), each Checked at the receiver. | `actor.identity`, `allowance.value`, `allowance.start`, `check.compare`, `allowance.pass` |  |

**Tool Use & Environment**

| Pattern | Kind | Built from | Recipe | Operations | Shipped |
|---|---|---|---|---|---|
| AI Web Search Agent Loop | mechanism | Flow + Actor + Check | Ask a query translator; split each search worker by domain and time range; join; a Check for gaps; repeat; answer with citations. | `flow.ask`, `flow.split`, `flow.join`, `check.compare`, `flow.then` |  |
| Agent SDK for Programmatic Control | mechanism | Actor + Allowance + Flow | A named Flow is an Actor callable from code (`published-as: api`), with the Allowance set by the caller. | `flow.name`, `actor.composite`, `allowance.pass` |  |
| Agent-First Tool Discovery | mechanism | Store + Actor | A tool catalogue Store whose `find` is ranked by a pure program over the Actors' figures. | `store.find`, `actor.program`, `actor.figures` |  |
| Agent-First Tooling and Logging | practice | Actor + Store | Tool Actors whose answers are a Shape (JSON), with exit codes as outcome labels; the run record Store is the one log stream and a tool Actor exports it. | `actor.tool`, `shape.record`, `flow.then`, `store.host` |  |
| Agentic Search Over Vector Embeddings | mechanism | Flow + Actor + Store | `find` by words through grep-and-read tool Actors inside a ReAct repeat, instead of an embedding index. | `store.find`, `actor.tool`, `flow.then`, `allowance.quantity` |  |
| CLI-First Skill Design | practice | Actor + Shape | A skill's scripts are program Actors with a Shape signature; the exit code is the outcome label the Flow routes by; the same Actor is asked by a person from a shell and by a model from a Flow. | `actor.program`, `actor.signature`, `flow.then`, `actor.person` |  |
| CLI-Native Agent Orchestration | mechanism | Flow + Shape | The Flow runs headless from a port; it answers a Shape of JSON; the exit code is its outcome label. | `flow.starts-when`, `shape.record`, `flow.then` |  |
| Code Mode MCP Tool Interface Improvement Pattern | mechanism | Actor + Allowance + Flow | A `run-code` Actor (typescript engine, fuel) whose Allowance reaches the MCP tool Actors; only the program's result returns to the conversation. | `actor.program`, `allowance.quantity`, `allowance.reach`, `actor.tool` |  |
| Code-Over-API Pattern | mechanism | Actor + Allowance + Shape | `run-code` in a sandbox with reach to the tools; the program answers summaries and samples as a Shape. | `actor.program`, `actor.location`, `allowance.reach`, `shape.record` |  |
| Code-Then-Execute Pattern | mechanism | Actor + Origin + Check | Ask the model for a program; before it may be asked (law 8) the checker runs the Origin flow Check over it (the taint check); then a sandbox Actor with fuel runs it. | `flow.ask`, `actor.instantiate`, `label.propagate`, `check.origin`, `actor.location`, `allowance.quantity` |  |
| Cross-Protocol Agent Discovery | mechanism | Store + Actor | A directory Store aggregating Actor descriptions (A2A cards, MCP listings); references by requirement resolve against it. | `store.host`, `store.find`, `actor.by-requirement` |  |
| Dual-Use Tool Design | practice | Actor + Allowance | One tool Actor with one Shape, one Allowance and one run record entry per ask, whether the asker is a person Actor or a model Actor; the Origin stamp says which. | `actor.tool`, `actor.signature`, `allowance.reach`, `store.host`, `label.origin` |  |
| Egress Lockdown (No-Exfiltration Channel) | mechanism | Allowance | Law 4: egress is the union of the addresses of reachable Actors; everything else is refused. | `allowance.reach`, `check.reachability`, `label.region` | `examples/refund-desk/workspace.yaml` |
| Filesystem-Mediated Host Delegation | mechanism | Store + Flow + Check | A spool Store; a host Flow `starts-when` a request is written, Checks it against the allowlist, claims it for idempotency and writes the result; the agent `await`s it. | `store.write`, `flow.starts-when`, `check.compare`, `store.claim`, `flow.await` |  |
| Intelligent Bash Tool Execution | mechanism | Actor + Flow + Allowance | A tool Actor whose mode is a closed `one of` chosen by a Check; background jobs are detached asks with run references; signals are cancel; approvals are `needs-a-person`. | `actor.tool`, `shape.one-of`, `flow.choose`, `flow.detach`, `flow.cancel`, `flow.handler` |  |
| LLM-Friendly API Design | practice | Actor + Shape | The API is a tool Actor: Shape describe publishes its arguments; versions are Store versions; errors are outcome labels with reasons the Flow can route by. | `actor.tool`, `shape.describe`, `store.version`, `flow.then` |  |
| MCP Pattern Injection | mechanism | Store + Origin + Actor | An MCP server resource; its patterns are Store entries with the server-prose Origin, so they reach the model fenced as data. | `actor.tool`, `store.read`, `label.origin`, `label.fence` | `examples/mcp-desk` |
| Multi-Platform Communication Aggregation | mechanism | Flow + Shape + Actor | Split each adapter tool Actor with one shared Shape; join everyone; a program merges, de-duplicates and ranks. | `flow.split`, `actor.tool`, `shape.record`, `flow.join`, `actor.program` | `examples/kernel/map-reduce` |
| Multi-Platform Webhook Triggers | mechanism | Flow + Check + Store | One port (`starts-when`) per platform; `signed-with` is a Check; `counts-as-the-same-for` is the idempotency key; `every:` is the schedule. | `flow.starts-when`, `check.compare`, `store.claim` | `examples/kernel/lanes` |
| Patch Steering via Prompted Tool Selection | practice | Actor + Flow | Reviewed-definition instructions naming the edit tool Actor and examples; the negative rules are Checks in a before-handler; the fallback order is `if-it-fails.backup`. | `label.fence`, `flow.handler`, `check.detector` |  |
| Precomputed Code Graph Lookup | mechanism | Store + Actor + Shape | A program Actor builds a graph Store; `find` by typed queries whose verbs are a closed `one of`. | `actor.program`, `store.write`, `store.find`, `shape.one-of` |  |
| Progressive Tool Discovery | mechanism | Store + Shape + Allowance | The catalogue Store is a hierarchy; `find` returns names, then descriptions, then full Shapes (Shape describe) on demand. | `store.find`, `shape.describe`, `allowance.reach` | `examples/refund-desk/skills/refund-policy` |
| Static Service Manifest for Agents | mechanism | Store + Origin + Allowance | A resource's `published` description, a Store entry with the server Origin, read before any ask; its limits become Allowances. | `store.read`, `label.origin`, `allowance.quantity` |  |
| Tool Use Steering via Prompting | practice | Actor | Reviewed-definition instructions for the model Actor; a shorthand that maps to a tool sequence is a named Flow (an Actor) the model may ask; `use-when` Checks route to it. | `label.fence`, `flow.name`, `check.compare`, `flow.choose` |  |
| Unified Tool Gateway | mechanism | Flow + Allowance + Store | Every tool ask passes one handler at workspace scope that resolves the Actor, Checks the Allowance and credential, and records the cost in the run record. | `flow.handler`, `flow.scope`, `actor.by-requirement`, `allowance.reach`, `allowance.use-without-seeing`, `store.host` | `examples/mcp-desk` |
| Virtual Machine Operator Agent | mechanism | Actor + Allowance | A `resource-kind: sandbox` Actor with its program engines; the Allowance says what it may reach. | `actor.location`, `actor.program`, `allowance.reach` |  |
| Visual AI Multimodal Integration | mechanism | Shape + Actor | Image, video and audio Shapes; `model-can.modality-in`; the model Actor chosen by `needs:`. | `shape.scalar`, `actor.by-requirement`, `actor.model` |  |

**UX & Collaboration**

| Pattern | Kind | Built from | Recipe | Operations | Shipped |
|---|---|---|---|---|---|
| AI-Accelerated Learning and Skill Development | practice | Actor + Store | A tutor model Actor; the learner's level is a workspace Store written after each session; `variants:` chosen by a Check on that level fade the support. | `actor.model`, `store.write`, `flow.choose`, `check.compare` |  |
| Abstracted Code Representation for Review | mechanism | Actor + Shape + Store | Ask a summariser for a Shape {pseudocode, intent, logical diff}; show it to the person (`question.shows`) with a Store reference for the drill-down. | `flow.ask`, `shape.record`, `allowance.see`, `shape.reference`, `actor.person` |  |
| Agent-Assisted Scaffolding | mechanism | Actor + Shape + Allowance | Ask the model for a Shape file tree; a tool Actor writes the files within a write Allowance on those paths. | `flow.ask`, `shape.record`, `actor.tool`, `allowance.write` |  |
| Agent-Friendly Workflow Design | practice | Shape + Flow | The goal and the result are Shapes; the plan is written to a Store and shown to a person (`ask-someone`) before the execute scope runs; the model chooses the steps inside its Allowance. | `shape.record`, `store.write`, `actor.person`, `flow.scope`, `allowance.reach` |  |
| Chain-of-Thought Monitoring & Interruption | mechanism | Shape + Flow + Store | A `stream of` parts (kind reasoning or tool call) to a port; a person's arrival in the inbox cancels the scope and writes the redirection to the conversation Store. | `shape.stream`, `flow.handler`, `flow.cancel`, `store.write`, `store.host` |  |
| Codebase Optimization for Agents | practice | Actor | The verify loop is one tool Actor with a Shape answer; tests and docs are Store entries the model `find`s; a Check on the tool's outcome gates `answer`. | `actor.tool`, `shape.record`, `store.find`, `check.compare` |  |
| Democratization of Tooling via Agents | mechanism | Actor + Flow + Store | The skill-library recipe with a person Actor in the loop: ask for a program, test it, show it, write it to the definition Store. | `flow.ask`, `actor.tool`, `check.compare`, `actor.person`, `store.write`, `actor.instantiate` |  |
| Dev Tooling Assumptions Reset | practice | Flow | Dispatch is `starts-when` an arrival, not a ticket; variations are a split of N forks; the review is a Check over test outcomes plus one person Actor at `release`. Removing the ceremony is the team's decision. | `flow.starts-when`, `flow.split`, `store.fork`, `check.compare`, `actor.person` |  |
| Human-in-the-Loop Approval Framework | mechanism | Flow + Check + Actor | Policy handlers with Checks on the high-risk asks route to questions for person Actors (`asked-in` several channels); the run record is the audit trail. | `flow.handler`, `check.compare`, `actor.person`, `actor.park`, `store.host`, `allowance.pause` | `examples/refund-desk` |
| Latent Demand Product Discovery | practice | Store | Usage is the run record Store; a scheduled Flow `find`s repeated workarounds (a Check on counts over past runs) and writes candidates to a Store a person reads. Building the feature is a decision. | `store.host`, `flow.starts-when`, `store.find`, `check.count`, `store.write` |  |
| Milestone Escrow for Agent Resource Funding | mechanism | Allowance + Store + Check | An Allowance value held in a Store; each release is a claim per milestone gated by a Check on an independent verifier Actor's verdict. | `allowance.value`, `store.write`, `store.claim`, `check.compare`, `actor.model` |  |
| Proactive Trigger Vocabulary | mechanism | Check + Flow + Store | Each skill's `use-when` phrases are a Check (`contains-any-of`, or a declared detector) in a `choose` rung; proactive activation is `starts-when` an arrival matches. | `check.compare`, `check.detector`, `flow.choose`, `flow.starts-when` |  |
| Seamless Background-to-Foreground Handoff | mechanism | Store + Actor + Flow | The run reference and the conversation Store are handed to a person Actor, who becomes the caller; the branch and PR are Store references. | `shape.reference`, `store.host`, `actor.person`, `flow.detach` |  |
| Shell Command Contextualization | mechanism | Actor + Store + Origin | The person asks a tool Actor directly; the command and its output are written to the conversation Store with the person and tool-output Origins. | `actor.tool`, `store.write`, `label.origin` |  |
| Spectrum of Control / Blended Initiative | mechanism | Allowance + Flow + Check | Modes are `variants:` with different Allowances (everything `needs-a-person`, or background); chosen per task by a Check on the input. | `flow.choose`, `allowance.reach`, `actor.park`, `check.compare` | `examples/refund-desk/agents/refund-desk/agent.yaml` |
| Team-Shared Agent Configuration as Code | pact | Store | The PACT tree in version control, reviewed through pull requests. | `store.version`, `actor.person`, `allowance.write` |  |
| Verbose Reasoning Transparency | mechanism | Store + Shape + Allowance | The run record rendered on demand (Shape render); the person's Allowance to see it. | `store.host`, `shape.render`, `allowance.see` |  |


## Appendix C: the kernel, every operation of the seven

Generated by `python3 scripts/pattern-coverage.py --ops`. 76 operations. The last column names the PACT keyword that is this operation today; since 2026-11-10 every operation has one.

| Operation | Primitive | What it does | PACT keyword today |
|---|---|---|---|
| `shape.scalar` | Shape | text, money, yes-or-no, number, date, duration, image, audio, file | accepts / answers-with / takes |
| `shape.one-of` | Shape | a closed set of words | `one of a, b` |
| `shape.record` | Shape | records, lists, maps, optional, a failed marker | `list of`, nested `accepts:` |
| `shape.stream` | Shape | an answer that arrives in parts, each part with a kind | answer shape `stream of <shape>`; the harness builds an answer only from `answer` parts (voice `talking: both-at-once` too) |
| `shape.reference` | Shape | a host-issued reference to an agent, run, stored value or Allowance | an `agent`-shaped answer as a `call:` binding, held to `may-call:` at check and run time |
| `shape.validate` | Shape | accept or refuse a value that arrived | answers-with-mode |
| `shape.describe` | Shape | tell a producer the expected form (JSON Schema, MCP inputSchema, a form) | schemas-from, published-tool |
| `shape.parse` | Shape | read a value out of loose text | answers-with-mode: prompted |
| `shape.render` | Shape | fill a template; nothing filled in is read as template again | template-language, `{{run-inputs.x}}` |
| `shape.digest` | Shape | a value's fingerprint | `in-share: <percent>` in `when-this`; a person's yes bound to the digest of the request they saw |
| `label.origin` | Origin | customer, person, tool, retrieval, model, teammate, server, reviewed definition, clock | turn.from, never-from |
| `label.sensitivity` | Origin | a category such as card number or personal data, set by a detector or `hides` | hides, redaction |
| `label.region` | Origin | where a value may live | data-stays-in |
| `label.propagate` | Origin | anything computed from labelled values carries the combined label | `never-from:` checked statically (law 7) and again at run time on every memory write |
| `label.fence` | Origin | only reviewed text instructs; everything else reaches a model as quoted data | question.shows, server prose fenced |
| `label.placeholder` | Origin | a hidden value travels as a reference and is restored only for use-without-seeing | `gets-hidden-values: yes` on an action; hidden values travel as placeholders |
| `store.read` | Store | read a path, or as of a version | `input.x`, `steps.x.result`, `remembers.x` |
| `store.write` | Store | write through the merge rule | remember-as, remembers, writes-to |
| `store.merge` | Store | keep-all, keep-the-latest, merge, add-up, vote, top-n, or a pure program | combines-by |
| `store.claim` | Store | insert-if-absent or compare-and-swap, with an optional lease; take = claim then forget | same-request-key, `same-request-key-across: the-team | the-workspace`, `claim-lasts:` |
| `store.fork` | Store | a copy-on-write branch or snapshot, discarded unless joined out | `forks: yes` on an each, together, repeat or loop stage |
| `store.find` | Store | by key, words or meaning, reranked, at most N | knowledge: looked-up-by, passages-at-most, reranked-by |
| `store.forget` | Store | remove an entry or let it expire | kept-for, drop-parts, stops-being-true-when |
| `store.scope` | Store | step, turn, conversation, run, flow, team, workspace; one per key | lasts, kept-per, counted-per |
| `store.lifetime` | Store | until a moment or an event | kept-for, forget-after |
| `store.durability` | Store | none, checkpoint, durable-execution | workspace.durability |
| `store.version` | Store | every write may create a version with a digest | based-on: name@version, stage.version, tool-snapshot-digest |
| `store.pin` | Store | pinned entries survive tidying | always-keep, survives-shortening |
| `store.host` | Store | the conversation, run record, inbox, run registry, clock, directory, catalogue, definition | turns, population: past-runs, counts-events-from, if-still-running, every, asked-of, catalog, values |
| `actor.model` | Actor | decides by sampling | model, settings, needs |
| `actor.program` | Actor | decides by computing, under fuel | programs, run-code, engine, determinism |
| `actor.tool` | Actor | an outside system decides | tools, actions, resources, MCP |
| `actor.person` | Actor | a human answers; slow and authoritative | questions, asked-of, escalates-to |
| `actor.remote` | Actor | someone else's agent decides | resource-kind: a2a-agent |
| `actor.composite` | Actor | a named Flow with a signature | agents, workflows, published-as |
| `actor.signature` | Actor | what it takes and answers with | accepts, answers-with, takes |
| `actor.effect` | Actor | none, reads, writes, spends, irreversible; with undo and status-check; readable by a Check | computed from reads-only, spends-money, undone-by; Check-readable as `effect:` in `when-this`; shown by `pact discover` |
| `actor.write-set` | Actor | the Store paths an Actor declares it writes | `writes: [<place>, ...]` on an action; overlapping branches are warned |
| `actor.park` | Actor | may wait on a person or an event | ask-someone, answer-within |
| `actor.figures` | Actor | cost, latency, context, capabilities, benchmark scores, with provenance | model-cost, model-speed, figure, provenance |
| `actor.identity` | Actor | who acted, on whose behalf, how strongly established | needs-signature, owned-by, not-the-same-as |
| `actor.location` | Actor | where it runs | served-by.region, runs-in |
| `actor.by-requirement` | Actor | chosen from a catalogue by a Check and a preference | needs, prefer, interface, implements, chosen-by |
| `actor.instantiate` | Actor | make an Actor from a definition value during a run, through the checker (law 8) | may-start: narrowed-new, run-code |
| `flow.ask` | Flow | ask one Actor with inputs bound from Stores; wait, or detach for a run reference | does: call / think / use-tools, call, bind |
| `flow.then` | Flow | every ask ends in a labelled outcome; the label picks the next step | then, outcome, starts-at |
| `flow.choose` | Flow | pick one label from a closed set by rungs: Checks, then Actors, then a person | does: decide, chooses-between, rung, route-rule, if-unsure-below |
| `flow.split` | Flow | fixed branches, one per item, one per stream part, or one per entry of a growing Store | does: each / together, over, teamwork.starts |
| `flow.join` | Flow | everyone, first, k of n passing a Check, deadline, or quiet; then cancel / ignore / detach the rest | waits-for, enough-is, gives-up-after, combines-by; growing sets: `keeps-taking: yes` on an each |
| `flow.await` | Flow | pause until a Check over Stores holds, with a correlation key and a deadline | heard, answer-within, counts-events-from, only-when |
| `flow.scope` | Flow | a region with its own Store fork, Allowance and meters | a stage's steps, team, isolated conversation, limits on a stage |
| `flow.handler` | Flow | before, each part, after, failure, ran-out: change, hold, divert, refuse, retry, back up, undo | interceptors, policies, if-it-fails, when-it-runs-out, context-policy, watch, redaction |
| `flow.starts-when` | Flow | a trigger: a Check over Stores becomes true; with a concurrency key and an overlap rule | ports, every, if-still-running, if-missed, per-row-of |
| `flow.cancel` | Flow | cancel a scope or a run by reference | if-someone-fails: stop-the-others; by reference: `does: stop` with `stops: steps.<stage>.run` |
| `flow.detach` | Flow | start and get a run reference instead of waiting | waits-for-result: no |
| `flow.name` | Flow | a Flow with a signature is an Actor | agents, workflows, loops |
| `check.compare` | Check | more-than, less-than, is, is-one-of, contains-any-of, is-empty | when-this |
| `check.typed` | Check | money in its currency, durations, now-plus, business days | comparand, moment.counted-in |
| `check.detector` | Check | a named recogniser: built in (card number, email) or declared by the author | redaction.hide; declared: workspace `detectors:`, used as `looks-like:` and in sentences |
| `check.origin` | Check | a test on a value's Origin | never-from |
| `check.count` | Check | counts and order over the run record; distinct in the last k | must-call-before, `called more than n times` |
| `check.aggregate` | Check | shares, percentiles, means over a population | must-pass, metrics, threshold, measured-at |
| `check.combine` | Check | all, any, not | rules lists |
| `check.reachability` | Check | what a part can reach, directly or through others | available-when; `carries:` on a tool, and the three-part leak rule |
| `check.digest` | Check | compare two fingerprints | tool-snapshot-digest; request digests on approvals; `in-share:` |
| `allowance.reach` | Allowance | which Actors and addresses a part may ask | uses, may-use, may-call, allow-egress, who-can-reach-it |
| `allowance.see` | Allowance | who may read a labelled value | hides, question.shows, inspects |
| `allowance.use-without-seeing` | Allowance | pass a value along without reading it | credential-reference |
| `allowance.write` | Allowance | what a part may write, including to the definition | owners, locked, learning.needs-a-person-to-approve |
| `allowance.start` | Allowance | whether and how many helpers a part may start, and how deep | may-start, starts-at-most, nests-at-most |
| `allowance.quantity` | Allowance | steps, tool calls, tokens, money, time, items, attempts, fuel | limits, at-most, fuel, checks-at-most |
| `allowance.period` | Allowance | counted per scope and reset per period | counted-per, resets-every |
| `allowance.pass` | Allowance | handed down, never wider; totals conserved | divides-the-budget, shares |
| `allowance.revoke` | Allowance | taken back, expired, or withdrawn for a period | locked-until, tool-snapshot-max-age; for a period: `rests-after:` with `rests-for:` on a tool |
| `allowance.pause` | Allowance | a meter paused during a scope | paused-during |
| `allowance.value` | Allowance | a grant as a run-time value that can be split and passed | `cost-per-request-from:` a run input, never above `cost-per-request-under:` |
