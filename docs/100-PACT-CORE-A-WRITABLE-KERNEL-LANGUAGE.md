# 100 — PACT Core: a small language you can write, changeable while it runs

**Date:** 2026-11-16. **Status:** Proposed plan. Nothing in this document is built.
It carries one owner instruction and proceeds on the defaults in §3 until the
owner changes one.

**The instruction** (the owner, 16 November 2026): *"come up with a detailed plan
on how to build this, test it, validate it, live validate it, extreme real world
agentic scenarios to test it with. We need an actual writable syntax, not just
categorisation. Like a mini language, and it should also support NOOA concepts.
During runtime, this can be changed. Means it's more JIT than AOT."*

**Words used here, defined once.**

- **Primitive.** One of PACT's seven building blocks: Shape, Origin, Store,
  Actor, Flow, Check, Allowance (`docs/97-PRIMITIVES.md`).
- **Operation.** One specific thing a primitive does, such as `store.claim`
  ("take this key, at most once"). There are 76, listed in `spec/kernel.yaml`.
  Together they are **the kernel**.
- **Keyword.** A line an author types today, such as `answers-with:`. There are
  569 in `spec/schema.yaml`.
- **AOT (ahead of time).** Everything is checked once, before a run starts, and
  a run cannot change what it is running. This is PACT today.
- **JIT (just in time).** A definition can be added or changed while runs are
  going, and is checked at the moment it arrives, before anything can use it.
- **NOOA.** NVIDIA's "object-oriented agents" framework, studied in
  `docs/28-RESEARCH-NOOA-OO-AGENTS.md`. Its ideas that matter here: an agent is
  one typed object; a capability whose body is left empty is carried out by a
  model and one with a body is ordinary deterministic code; the model acts by
  writing small programs; large values are passed by reference and shown as
  short previews; and the model can define new typed operators in the middle of
  a task.
- **Cell.** A small piece of PACT Core that a model, a person or a learning
  cycle hands to a running session to be checked and then carried out.

---

## 1. What this is, in one page

**Today.** The seven primitives and their 76 operations are a way of
*classifying* PACT. `docs/97-PRIMITIVES.md:1402` says so: "The seven are a
mental model, not a syntax. An author keeps writing PACT's keywords." A
developer still has to know the keywords, a new construct still needs a new
keyword and new code in the checker and every runtime, and a run cannot change
what it runs.

**What this plan builds.** Four things, in this order:

1. **PACT Core, a language with one written form for each of the 76
   operations.** A developer who knows the kernel can write any agent or
   workflow without knowing a single keyword.
2. **`define`: new words made from existing ones.** A word has typed
   parameters and a body written in Core. PACT's existing keywords become a
   library of such words (the **prelude**), wherever that can be proven to
   change nothing.
3. **A live session.** Definitions can be added, replaced and withdrawn while
   runs are going. Each change is checked by the same checker, at the moment it
   arrives, and takes effect at a defined point.
4. **NOOA's concepts, in PACT's terms.** Capabilities whose body is "a model
   decides", values passed by reference, state on the agent, and a model that
   acts by writing cells in Core, including defining new typed operators
   mid-task.

**What does not change.** The keywords stay, for the people who cannot write
code: they become the prelude, not a casualty. The eight laws stay. The checker
stays the only judge. And one set of things stays out of reach of any run, any
model and any cell (§6.3).

**The one-line picture.**

```text
   what people write           what it becomes            who runs it
   ─────────────────           ───────────────            ───────────
   keywords (YAML, .pact) ─┐
                           ├─► PACT Core ─► kernel plan ─► any runtime that
   Core, written directly ─┤     (76 ops)   (checked,       implements the
                           │                 versioned)     76 operations
   cells, during a run ────┘        ▲
                                    └── the same checker, every time
```

---

## 2. What the code and the documents say today

Each claim is a file in this repository, or a measurement taken on 16 November.

- **The kernel is a file.** `spec/kernel.yaml` lists 76 operations: Actor 15,
  Store 13, Flow 12, Allowance 11, Shape 10, Check 9, Origin 6. Each records the
  keyword that is that operation today. 75 of the 76 are named by at least one
  schema field through a `kernel-op:` line (291 fields carry one); one is
  syntax only. `crates/pact-schema/tests/every_kernel_operation_is_written_somewhere.rs`
  holds the two files to each other.
- **A statement language already exists for part of Flow.** `.pact` files
  (`crates/pact-lang`, 3,876 lines) read `x = call a with k: path`, `for each
  item in`, `repeat at most N times`, `together`, `decide` with `if label`,
  `answer with`, `let`, and `based on X with k: v` (`docs/99-THE-PACT-LANGUAGE.md`
  §4). It has no expressions, and no way to define a new word.
- **Patterns with parameters exist.** A base agent with `expects:` and
  `<name>` marks, filled by `based on … with` (`site-docs/guide/programs-in-the-language.md`).
  This is the nearest existing thing to `define`, and `define` generalises it.
- **Law 8 is already "one checker, at the moment of creation".** Anything a
  run creates must pass the same checker before it can be asked
  (`docs/97-PRIMITIVES.md` §4). `adapters/python/src/pact_adapters/checking.py`
  does it for three things today, by writing the proposed document to a scratch
  folder and running the real `pact check` binary on it: a helper a run starts
  (`with_helper`), a skill a run wrote (`with_skill`) and a code snippet
  (`with_program`).
- **A whole-tree check is already fast.** Measured, as a fresh process
  including reading the files: `examples/refund-desk` 0.22 s; the largest tree
  in Bud Agent Flow's corpus (`115-pharmacovigilance`, 123 files) 0.06 s; a
  one-file `.pact` workspace 0.01 to 0.02 s. A model call takes seconds. So a
  check on every cell is affordable before any cleverness.
- **The checker and the runtimes are large.** The checker is 61 rule modules
  and 35,942 lines of Rust (`crates/pact-loader/src`). The reference agent
  harness is 4,757 lines and the reference workflow runtime 1,394 lines of
  Python. Any plan that rewrites these at once is not a plan.
- **Some things were deliberately put out of a run's reach.**
  `docs/27-PROGRAMS-AND-DYNAMIC-STRUCTURE.md` §B3 and §B4: no run, model,
  optimiser or bundle may alter the schema, a field's governance class, the
  meters, the approval path, redaction or the egress boundary while anything
  executes. This plan keeps every one (§6.3).
- **Four NOOA ideas were rejected for PACT in August** (`docs/28` §4.8): code
  as the authoring surface, free Python expressions, running generated code in
  the agent's own process, and behaviour that depends on a method's name. This
  plan takes NOOA's *concepts* without reversing any of the four: the language
  a model writes is PACT Core, which is closed, checked and metered, and never
  Python (§5).

**A correction to something I said on 15 November.** I told the owner that the
Expansion Rule (`site-docs/concepts/expansion-rule.md`) was an existing
mechanism for defining shorthand. It is not. It says that a folder and a field
are two ways of writing one setting. The existing mechanism nearest to `define`
is `based on … with`.

---

## 3. Decisions this plan proceeds on

Each is my recommendation and the default the plan uses. Any of them can be
changed by the owner before the phase that depends on it (§15).

| # | Decision | Default | Why |
|---|---|---|---|
| D1 | A new file type? | **No.** Core is more statements in the same `.pact` files, read by the same reader. | One language, as `docs/99` §1 decided. A second file type is a second thing to learn. |
| D2 | Do the keywords go away? | **No.** They become the prelude: words defined in Core, shipped with PACT. | The no-code author is half of PACT's audience. |
| D3 | Expressions (`a + b`)? | **Not in the first version.** Conditions stay the closed Check grammar (law 6). Arithmetic is a pure program, written inline. | A general expression language inside conditions is what law 6 exists to prevent: the checker could no longer prove where a refund over 200 USD goes. |
| D4 | What may a model write? | **Cells in Core**, each checked before it runs. Never Python, never a host language. | Keeps `docs/28` §4.8. A cell can only say what the 76 operations can do. |
| D5 | May a model keep what it defines? | **For the call or the run only.** Keeping it for the workspace is a write to the definitions, which needs the Allowance to write and, where the owners say so, a person. | Law 5: a self-improving agent must not write itself a bigger budget. |
| D6 | When does a change take effect? | **Between asks.** An ask in flight finishes under the version it began with. | Without this a tool call could be approved under one rule and made under another. |
| D7 | Which runtime first? | **PACT's Python reference**, then Bud Agent Flow through shared cases. The TypeScript port says it does not do it. | The order every other feature has landed in. |
| D8 | What does "JIT" mean here? | **Late admission, incremental checking and cached plans.** Not machine code. | Said plainly so nobody expects a compiler. |

---

## 4. The language

### 4.1 Rules it is designed by

1. **One written form for each operation.** `spec/kernel.yaml` gains a
   machine-readable `form:` beside each operation, and a test fails if an
   operation has none.
2. **A superset of today's `.pact`.** Every file that loads today loads
   unchanged and means the same.
3. **Sentences, not symbols.** `for each item in`, `at most 8 steps`, `never
   from the web`. It should read aloud.
4. **Total and bounded.** Every loop has a ceiling, every split has an item
   count, every program has fuel. A file that cannot be shown to stop is
   refused, unless an owner opted that one cycle out (law 2).
5. **Nothing is declared that can be computed.** What a word may do to the
   world, where it can reach and how much it may spend are worked out from its
   body (laws 1, 4 and 5), never written beside it.
6. **Each form reads one way.** Held by the test the language already has
   (`crates/pact-lang/tests/every_sentence_means_one_thing.rs`).

### 4.2 The forms, by primitive

The syntax below is the proposal that phase K1 settles. It is shown so the
shape of the language can be judged; the exact words are that phase's work.

```text
# Shape — what a value looks like
shape refund
  decision: one of approved, declined
  amount: money
  note: text, optional

# Store — what outlives a step
store attempts
  holds: list of text
  kept per run
  merges by keep-all

# Check — a judgment the checker can read
check over-the-line
  input.amount more than 200 USD

# Allowance — what a part may do, and how much
allowance desk-budget
  reach orders, payments
  at most 8 steps
  spend under 0.05 USD a request
  start at most 2 helpers

# Actor — anything that can be asked to do one thing
actor desk
  within desk-budget
  keeps attempts
  can decide(order: text) gives refund
    by model
  can total(amounts: list of money) gives money
    by program sum-amounts

# Flow — how asks are put together
flow refund-one(order: text) gives refund
  seen = call orders/look with order: order
  claim attempts by order
  verdict = call desk.decide with order: order
  if over-the-line
    ok = ask may-we-refund showing verdict
  answer with verdict
```

**Origin has no block of its own.** Where a value came from is stamped by the
host and cannot be written by an author or a model (law 7). What an author
writes is a restriction: `never from the web` on an input, `fenced` on a value
shown to a model, `hidden` on a value that travels as a reference.

**Operations that are verbs inside a flow.** Each is one statement:

| Statement | Operation |
|---|---|
| `x = call a with k: path` | `flow.ask` |
| `for each item in list at most N, M at once` | `flow.split` |
| `together`, `wait for everyone / the first / K of them` | `flow.split`, `flow.join` |
| `decide … if label` with rungs | `flow.choose` |
| `wait until <check> at most <time>` | `flow.await` |
| `start x, not waiting` giving a run reference | `flow.detach` |
| `stop <run>` | `flow.cancel` |
| `on failure …`, `on running out …`, `before …`, `after …` | `flow.handler` |
| `when <check> start <flow>` | `flow.starts-when` |
| `read`, `write … to`, `claim … by`, `fork`, `find in … by meaning`, `forget`, `pin` | the Store operations |
| `x as <shape>`, `parse x as <shape>`, `digest of x`, `render <template> with …` | the Shape operations |

### 4.3 `define`: a new word

A word has a name, typed parameters and a body in Core. Using it is the same as
writing its body with the parameters filled in.

```text
define guarded(action: action, line: money, asks: question)
  before <action>
    if input.amount more than <line>
      ask <asks> first

use guarded with action: payments/issue-refund, line: 200 USD, asks: may-we-refund
```

Three rules make this safe:

- **Parameters are typed and filled as values, never as text.** A parameter
  filled with `200 USD` cannot become part of an instruction. This is the rule
  `based on … with` already keeps.
- **A word cannot name itself**, directly or through another word, unless the
  cycle is metered (law 2).
- **A word is checked where it is used**, after it is expanded, by the same
  rules as if its body had been typed there. A word is never trusted because of
  who wrote it.

**The prelude.** Each existing keyword is then either an **intrinsic** (it is
one of the kernel's own forms) or a **word** defined in
`spec/prelude/*.pact`. For example, `needs-a-person: yes` on a tool action is
the word:

```text
define needs-a-person(on: action)
  before <on>
    ask pact:question/is-this-ok first
```

How many of the 569 keywords can honestly be written this way is not known
today. Phase K0 counts it, and that count decides how far the plan goes (§8).

### 4.4 A capability's body: a model, a program, or steps

This is NOOA's central idea in PACT's words. Every capability has a signature
(what it takes and gives). Its body is one of three things, and the difference
is visible on the page:

```text
  can decide(order: text) gives refund
    by model                       # a model decides, in a loop the harness meters

  can summarise(doc: text) gives summary
    by model, one shot             # one request, no tools, answer held to its shape

  can total(amounts: list of money) gives money
    by program sum-amounts         # computed, under fuel, the same every time

  can refund-one(order: text) gives refund
    seen = call orders/look with order: order
    answer with decision: approved, amount: seen.amount     # written steps
```

`by model` accepts the loop the harness should use: `one shot`, `in a loop`
(the default), `writing cells` (§4.5), `checking its work`. These are the loop
shapes PACT already ships under `loop:`.

### 4.5 Cells: a model acting by writing Core

With `by model, writing cells`, the model's action is a cell. The harness
checks it, carries it out, and shows the model what came back.

```text
cell
  define judge-one(claim: text) gives verdict
    by model, one shot
  each = for each item in input.claims at most 500, 20 at once
    v = call judge-one with claim: item
  answer with verdicts: each.v
```

What this gives that a list of tool calls does not:

- **The model can loop, branch and fan out** in one action, inside ceilings it
  cannot raise.
- **The model can make a new typed operator** (`judge-one`) and use it 500
  times. It lives for this call.
- **Values stay where they are.** `input.claims` may be a million rows. The
  model sees a bounded preview and the cell works on the whole value (§5).
- **A refused cell teaches.** The model is told why, in the checker's words,
  and writes another. This is the same loop as an answer that does not fit its
  shape, merged on 15 November (`answers_fit.py`).

---

## 5. NOOA's concepts, and where each lands

| NOOA's concept | In PACT Core | What keeps it safe | Phase |
|---|---|---|---|
| An agent is one typed object: fields are state, methods are capabilities | `actor` with `keeps <store>` and `can <name>(…) gives <shape>` | State is a Store, with a scope and a lifetime, not an attribute a model can add | K1 |
| A method with an empty body is carried out by a model; one with a body is deterministic | `by model` / `by program` / written steps (§4.4) | The boundary is on the page; the checker computes each one's effect on the world | K1, K4 |
| Typed inputs and validated typed returns, retried on failure | `gives <shape>`, held by `answers_fit` (merged 15 November), `checks-at-most` tries | One count for shape and rules; no answer handed back that does not fit | done, K4 |
| Pass by reference, bounded previews | A value is a Store entry; the model is shown `kind(len=N, first…, last…)`; a bare value is always whole, a marker always means cut | The preview form is one grammar, stated once to the model; a value's Origin travels with the reference | K5 |
| Code as action | Cells in Core (§4.5) | A cell can only use the 76 operations; checked before it runs; metered | K6 |
| Loop engineering by the model | `for each`, `repeat`, `together`, `decide` inside a cell | Every loop needs a ceiling within the definer's own Allowance | K6 |
| The model defines a new operator mid-task | `define` inside a cell | Never wider than its definer; lives for the call unless promoted | K6 |
| A persistent library the agent grows | Promotion: a word kept for the workspace | A write to the definitions: needs the Allowance, the drift budget, and a person where the owners say so | K8 |
| Object state re-rendered every turn | `shows <store> as <closed form>` on an actor | A named renderer, never a free expression | K5 |
| Harness APIs the model can call (history, context) | `read` on the host Stores (the conversation, the run record), by Allowance | Hidden unless granted; values keep their Origin | K5 |
| Loaded but not shown (load/activate split) | `uses` (wired) against `may-use` (offered), already in PACT | Unchanged | none |
| Evidence gates the model cannot skip | A Check between two asks in written steps | Law 6: the checker reads it | K1 |
| Three-region context for cache reuse | The cached plan keeps a stable prefix; state is rendered last | A change to a definition invalidates exactly the plans that read it | K7 |

**What is deliberately not taken:** Python as the language anyone writes;
expressions evaluated from strings; generated code running inside the agent's
own process; behaviour that changes when a name is changed.

---

## 6. Run time: changeable while it runs

### 6.1 The live session

A **session** holds a set of definitions (shapes, stores, checks, allowances,
actors, flows, words), each with a version and a fingerprint, and the runs
going against them. A change arrives as a **proposal** from one of three
places: an author saving a file, a model handing in a cell, or a learning
cycle. Every proposal goes through the same door:

```text
proposal ─► read ─► expand words ─► check (whole graph) ─► admitted, versioned
                                         │                        │
                                         └─► refused, with the    └─► takes effect at
                                             checker's sentence       the next safe point
```

### 6.2 The ten rules of a change

1. **One checker, at the door.** Nothing is asked before it is admitted. It is
   the same binary and the same rules as `pact check` (law 8).
2. **Changes land between asks.** An ask in flight finishes under the version
   it began with. A tool call approved under one rule is made under that rule.
3. **Every ask is pinned.** The run's record says which version of which
   definition each ask used. Replaying a run re-reads those versions, so a
   replay is the same run.
4. **A definition has a reach.** In widening order: the call, the run, the
   session, the workspace. Widening a definition's reach is a write to the
   definitions and needs `allowance.write`; into the workspace it also needs
   whatever `owners:`, `locked:` and `learning:` already require.
5. **Never wider.** What a run-time definition may do to the world, reach or
   spend is computed and must be within its definer's (laws 1, 4 and 5). A
   model cannot write a reference: names it was not given do not resolve.
6. **Model-written words instruct only what the model was allowed to start.**
   Text a model wrote is not reviewed text (law 7). It can be the instructions
   of a helper that is narrower than the model's own agent. It can never
   become instructions for the agent that wrote it, for a sibling, or for the
   workspace, except by promotion that a person approves.
7. **The floor does not move** (§6.3).
8. **The checker is metered too.** A cell has a size limit, a nesting limit, a
   count of definitions per run and a time limit on its check. Over any of
   them, it is refused. A model cannot stall a run by writing a large cell.
9. **A waiting run and a changed definition.** The change is classed as
   cosmetic (wording a person reads), additive (something new nothing waits
   on) or structural (what the waiting run will do next). A waiting run moves
   to a cosmetic or additive change by itself. A structural one leaves the run
   on its pinned version, or asks a person.
10. **Taking away is immediate at the next safe point.** A withdrawn Allowance
    or word is gone for every run when its current ask ends.

### 6.3 What no run, model or cell can change

Taken whole from `docs/27` §B4 and stated again because everything else leans
on it:

- the 76 operations and the eight laws;
- the schema and each field's governance class;
- the meters and what they count under;
- the approval path and who may approve;
- redaction, the watch record and the egress boundary.

A word can never add an operation. It can only arrange the ones that exist.

### 6.4 The three speeds

| Tier | What happens | When |
|---|---|---|
| **Read** | Keywords and Core are read into one checked document, as today | Always; a file that loads today takes this path unchanged |
| **Interpret** | A flow is carried out operation by operation from its kernel plan | From K4, for flows first |
| **Cached** | The parts of a plan that do not change (the instruction prefix, the tools offered, the tables a Check reads) are kept by fingerprint and reused | From K7; a change to a definition drops exactly the plans that read it |

---

## 7. Architecture

| Piece | Where | What it is |
|---|---|---|
| The kernel, machine-readable | `spec/kernel.yaml` gains `form:`, `takes:` and `lowers-to:` per operation | The single list every other piece reads |
| The Core reader and printer | `crates/pact-lang` | Reads the forms of §4; prints them back; round trip held by construction as today |
| Word expansion | `crates/pact-lang`, before the checker | As `based on` is resolved before the schema sees anything today |
| The kernel plan | new `crates/pact-kernel` | A checked document lowered to operations: typed, serialisable, fingerprinted. What a runtime carries out |
| The prelude | `spec/prelude/*.pact` | Keywords as words |
| The session server | `pact serve` in `crates/pact-cli` | The checker kept running: load once, take proposals, answer admitted or refused, keep versions. The same binary as `pact check` |
| The kernel interpreter | `adapters/python/src/pact_adapters/kernel/` | One function per operation; flows first |
| The session, cells and previews | `adapters/python/src/pact_adapters/session.py`, `cells.py`, `previews.py` | The run-time half of §6 |
| Shared cases | `tests/conformance/core.json`, `cells.json`, `sessions.json` | What a second runtime replays |

**The order that keeps one checker.** In phases K0 to K3 Core lowers to the
*same loaded document* the keywords produce, so the existing 61 rule modules
check it unchanged and there is never a second set of rules. The kernel plan
is introduced beside the document for *running* flows (K4) and only later, rule
by rule and only where measured to matter, for *checking*.

---

## 8. The build, in phases

Sizes are estimates for one focused working session of the kind that built the
`.pact` language: **S** a day or two, **M** about a week, **L** two to three
weeks. Each phase ends at a gate. A phase that misses its gate stops the plan
there, with what is already merged still standing on its own.

### K0. The proof, before any commitment (S)

- Add `form:` to six operations and write four shipped workspaces in Core by
  hand, using a throwaway reader: `examples/kernel/fallback`,
  `examples/kernel/work-queue`, `examples/language/help-centre` and
  `tests/conformance/trees/triaged-defects`.
- Classify all 569 keywords by script: **intrinsic** (is a kernel form),
  **word** (can be written as `define` over the kernel with the checker saying
  the same things), or **stuck** (neither), with the reason for each stuck one.
- Measure a whole-tree check kept in memory, per proposal, on the largest
  corpus tree.

**Gate.** The four workspaces load to the *identical* document as their
keyword versions; the stuck list is under 15% of keywords and each stuck one
has a named reason; a check per proposal is under 100 ms at the 95th
percentile. **If the stuck list is larger**, the plan continues with Core and
the live session (K1 to K8), and the prelude (K3) is cut to the words that
were proven, because "keywords as a library" would then be a claim the
evidence does not support.

### K1. The language, read and printed (M)

Every form of §4.2 and §4.4 in `crates/pact-lang`; `form:` for all 76
operations; `pact write --core` prints any loaded workspace in Core.

**Gate.** 76 of 76 operations have a form and a test that reads and prints it;
every shipped tree printed in Core and read back is the identical document;
the one-reading test passes.

### K2. `define` and `use` (M)

Typed parameters, expansion before the checker, diagnostics that point at the
line the author wrote and say which word it came from, the cycle rule.

**Gate.** A word used wrongly is refused with the same sentence its expanded
body would get; an unmetered self-naming word is refused; parameters cannot
reach an instruction position (a test tries, in every position).

### K3. The prelude (M to L, set by K0's count)

Each keyword K0 classed as a word is defined in `spec/prelude/`. A keyword
moves only when its test passes.

**Gate.** For every shipped tree and every tree of Bud Agent Flow's corpus
(136, read only), loading with the keyword built in and loading with it
expanded from the prelude give the identical document and the identical
diagnostics.

### K4. The kernel plan and its interpreter, for flows (L)

`crates/pact-kernel`: a checked workflow lowered to operations. The Python
interpreter carries out a plan with one function per operation. The existing
workflow runtime stays, and the two are compared.

**Gate.** All 43 shared workflow cases give the identical `expect` through the
interpreter; every `examples/` workflow runs the same both ways.

### K5. By reference: values, previews and state (M)

A value handed to a model as a reference with a bounded preview; the preview
grammar told to the model once; `shows <store> as …`; the host Stores readable
by Allowance.

**Gate.** A one-million-row value costs the same tokens as a one-hundred-row
one; a hidden value never appears in a preview (tested against every
redaction rule the worked example ships); a preview always says when it is
cut.

### K6. The live session and cells (L)

`pact serve`; the ten rules of §6.2; `by model, writing cells`; cell-scoped
`define`.

**Gate.** The red-team set of §9.5 has no escape; a refused cell is followed by
a corrected one in the scripted cases; killing the process at every step of an
admission and resuming gives a consistent session (§9.6).

### K7. Cached plans (M)

Plans kept by fingerprint; exact invalidation; the instruction prefix held
stable across turns.

**Gate.** With the cache on and off, every shared case gives the identical
result; after a change, no ask uses a plan that read the old definition
(a test changes each kind of definition and looks).

### K8. Promotion and learning (M)

A run-scoped word proposed for the workspace; the person's approval; the drift
budget; old runs still replaying under old versions.

**Gate.** No path writes a definition into the workspace without the Allowance
and the approval the owners wrote (a test tries each path); replaying a run
from before a promotion gives the same record.

### K9. The second runtime, and the documents (M)

Shared cases published; Bud Agent Flow replays them; the TypeScript port says
it runs none of §6 (`unenforced`, §7.28 list B); the guide, the reference and
the first-hour page.

**Gate.** Bud Agent Flow reports every case, each agreed or refused by name;
`mkdocs build --strict`; a reader who has seen only the first-hour page writes
the worked example in Core (§10, item 5).

**Order and what can run side by side.** K0 → K1 → K2 → K3 in a line. K4 can
start after K1. K5 after K4. K6 needs K2 and K4. K7 and K8 need K6. K9 last.

---

## 9. How it is tested

Seven layers. Each names the mistake it exists to catch.

### 9.1 The reader: every form reads one way, and comes back

- For each of the 76 operations, a test that reads its form and prints it back.
- Round trip on every shipped tree: `read(write(document)) == document`.
- The one-reading test: no sentence can be read as two forms.
- A fuzzer on the reader (random bytes and mutated real files). It may refuse;
  it may never crash, hang or read garbage as a program.

*Catches:* a form that means two things; a printer that loses a line.

### 9.2 Coverage: nothing in the kernel is unwritable

A script that fails unless every operation has a form, at least one shared
case that uses it, and at least one shipped example. It extends the test that
already holds `spec/kernel.yaml` to the schema.

*Catches:* an operation that exists on paper and cannot be typed.

### 9.3 Equivalence: Core means what the keywords mean

- **Document equivalence.** For every tree, the keyword version and its Core
  printing load to the identical document. Trees: everything under
  `examples/`, `tests/trees/`, `tests/conformance/trees/`, and Bud Agent
  Flow's 136 corpus trees (read only).
- **Diagnostic equivalence.** For every rule in the checker that has a test
  tree which breaks it, the Core version of that broken tree is refused by the
  same rule with the same sentence.
- **Run equivalence.** The 80 shared cases (43 workflow, 37 agent) and the
  golden set (every shipped agent on seven targets) give identical results
  whether the tree was written in keywords or in Core, and (from K4) whether a
  flow was run by today's runtime or by the kernel interpreter.

*Catches:* a second meaning creeping in beside the first.

### 9.4 Properties: the laws hold for anything that can be written

A generator writes random well-formed Core: definitions, words and cells. For
each thing the checker admits, properties are asserted, at least 100,000
generated programs for each:

| Law | Property asserted of everything admitted |
|---|---|
| 1 | Its computed effect on the world is at least the worst effect of anything it can ask |
| 2 | Every cycle in the graph of what starts what is metered by a ceiling the cycle cannot write |
| 3 | Every ask that spends or cannot be undone, inside anything that repeats, carries a claim key that does not depend on the attempt |
| 4 | Everything it can reach was granted to its definer; no name it was not given resolves |
| 5 | Its Allowance is within its definer's, in every quantity |
| 6 | Every decision the checker must prove is a Check or a pick from a closed list |
| 7 | No value of an unreviewed Origin sits in an instruction position |
| 8 | Nothing in it was asked before it was admitted |

*Catches:* a hole that no hand-written test thought of.

### 9.5 The red-team set: attacks written down

At least 25 hand-written attacks for each law, 200 in all, each a cell or a
sequence of cells that tries one specific thing: a helper wider than its
starter, a ceiling read from a Store the loop writes, a payment in a retry
with no key, a hidden value rendered into a helper's instructions, a word
that names itself through three others. Each must be refused by the named
rule.

Then the mutation check the repository already uses
(`test_a_guarantee_nothing_would_miss_is_not_a_guarantee.py`): each run-time
rule of §6.2 is removed in a throwaway copy, one at a time, and at least one
attack must then get through. A rule whose removal nothing notices is not
being tested.

*Catches:* a guard that is present and does nothing.

### 9.6 The session: change at every moment

- A definition changed at each point of an ask: before it starts, while the
  model is being called, while a tool is running, while a person is being
  waited for, after it ends. Rule 2 and rule 3 are asserted each time.
- The process killed at every step of an admission (after the proposal is
  recorded, after it is checked, after it is versioned, before it takes
  effect), then resumed. The session is either wholly before or wholly after.
  This machine powers itself off under heat, so this is not a hypothetical.
- Two proposals arriving at once for the same definition: one wins, the other
  is told it was built on an old version.
- Replay: a recorded run, with every cell it was handed, replays to the same
  record with no model call.

*Catches:* half-applied changes, and a run that cannot be reproduced.

### 9.7 Speed and cost

Admission time per proposal (50th and 95th percentile) on the worked example
and on the largest corpus tree; interpreter overhead per ask against today's
runtime; tokens per task for cells against tool calls. Budgets are in §13.

---

## 10. How it is validated

Testing says the code does what was written. Validation asks whether what was
written is right.

1. **The stuck list is published.** Every keyword that could not be written as
   a word is listed with its reason. That list is the honest size of "a small
   subset through which everything can be created".
2. **The 203 published patterns.** `scripts/pattern-coverage.py` already types
   each pattern's recipe against the kernel. It gains a column: is there a
   Core program for it that loads? The 57 that exist as PACT today must each
   have one by K3. The count for the rest is reported, not targeted.
3. **A second runtime.** Bud Agent Flow replays `core.json`, `cells.json` and
   `sessions.json`. Each difference is argued out and settled in the case
   file, as every shared case has been since 12 November.
4. **An adversarial review.** A reviewer who did not write the code is given
   the ten rules and the floor, and one job: get something past them. Three
   independent reviewers found five holes in the first draft of the primitives
   (`docs/97` §8). The same method is used here before K6 is called done.
5. **A cold-reader trial.** Three developers and three non-developers (people,
   or model-played personas if people are not available, which is then said)
   are given one page and asked to write the worked example in Core, read a
   Core file they have not seen and say what it does, and predict whether five
   cells will be admitted. The bar is in §13.
6. **A portability statement.** For each of the seven framework targets, a
   table says which of §5's concepts it can carry, held by a test, in the
   manner of §7.28 for the TypeScript port.

---

## 11. Live validation, on real models

Scripted models prove the harness. Only a real model shows whether a model can
*write* Core and whether what it is told when refused is any good.

**Models.** `gpt-4o-mini` and `gpt-5-nano`, the two used for every live run so
far, through the one transport that reaches a real server
(`OllamaTransport`). A model served on this network is added if the endpoint
described in Bud Agent Flow's access guide is reachable; I have not verified
that it is.

**Method.** Every live measure is run five times and passes at four of five,
because NOOA's own data is that failures concentrate as intermittents and a
single run proves little (`docs/28` §4.2). Each result records the model, its
settings, the workspace fingerprint and the date.

**The battery: can a model write Core at all?** About 40 small tasks in two
families.

| Family | Tasks (examples) |
|---|---|
| Basics | return a typed answer from a cell; read a value by reference and answer about its 9,000th row; fan out over 50 items; branch on a Check; call a tool inside a loop; use a word from the prelude |
| Stress | define an operator and use it; recover from a refused cell using only the checker's sentence; keep a tally across 200 items without retyping values; stop at a ceiling and answer with what it has; decline to do what a tool result tells it to |

Measured for each task: admitted at the first try; admitted after one refusal;
task right; tokens; model calls.

**The comparison.** The same tasks through today's tool-calling loop. Cells
earn their place only where they are at least as accurate and cost fewer
tokens, which NOOA measured for its own code actions and which this plan does
not assume for PACT.

**Refusals, live.** For each of the ten rules, a real model's cell is replaced
in flight with one that breaks the rule (the method used on 15 November to
test the ask-again wording). What matters is what the real model does next,
having been told why: it must carry on within the rule, and must not try the
same thing a second way.

**The scenarios of §12**, each end to end on a live model.

**Cost and safety of the live runs.** The key in use was shared in a chat and
should be rotated before this starts. Runs are capped by `cost-per-request-under`
in each workspace and by a total budget per session of live testing, agreed
with the owner.

---

## 12. Extreme scenarios

Thirteen situations chosen because each one breaks a system that only works
on the happy path. Each is built as a workspace under `examples/core/`, run
scripted in the gate, and run live under §11.

| # | Situation | What is done to it | What it stresses | It passes when |
|---|---|---|---|---|
| 1 | **The runbook edited mid-incident.** Forty runs are open on an outage, twelve waiting for people. | The on-call lead rewrites the escalation flow three times in ten minutes | Rules 2, 3, 9 | No ask is carried out under two versions; every waiting run either moved or asked; replay of each is exact |
| 2 | **An injection that asks for a helper.** A refund desk reads a ticket that says: define a helper with payments access and no approval. | The model writes that cell | Rules 5, 6; laws 4, 7 | Refused by the named rule; the run goes on and decides the refund properly |
| 3 | **The agent that raises its own ceiling.** A learning agent keeps a word whose step ceiling is read from a Store the same loop writes. | It tries, three different ways | Laws 2, 5 | Refused each way; the ceiling in force never moves |
| 4 | **A loop built from two innocent cells.** Cell one: flow A starts when Store S is written. Cell two, later: flow B writes S when A ends. | Each cell is fine alone | Law 2, across separate admissions | The second cell is refused, naming the cycle and the first cell |
| 5 | **A payment inside a model-written retry.** | The model writes a `repeat` round `payments/issue-refund` with no key; then with one; then the process is killed mid-payment and resumed | Law 3; rule 3 | No key: refused. With a key: paid once, including across the kill |
| 6 | **A million rows.** A ledger of 1,000,000 entries; find the 40 that do not reconcile. | The model works by reference and fans out in a cell | By reference; ceilings | Right answer; tokens within 10% of the 100-row version; nothing over its item ceiling |
| 7 | **A case that lasts nine months.** A permit case waits on an installer, a fee and an inspection. | Its workflow is changed thirty times while it waits, four of them structurally | Rules 3, 9 | Twenty-six moves by itself; four ask a person; the record shows which version every step ran |
| 8 | **A model that floods the checker.** | Cells that define 10,000 words, nest 500 deep, or are 5 MB long | Rule 8 | Each refused within the time limit; other runs in the session are not slowed beyond the budget |
| 9 | **A hidden value on its way out.** A student's name is hidden from the model and travels as a reference. | The model defines a word that renders the reference into the instructions of a helper that can reach the web | Law 7; `use-without-seeing` | Refused; passing the reference to the one tool allowed to see it still works |
| 10 | **The kill switch.** Two hundred runs are making payments. | The owner withdraws the payments Allowance | Rule 10 | No run makes a payment after its current ask ends; every payment in flight is settled once |
| 11 | **Power loss during a change.** | The machine is stopped at each step of an admission, forty times | §9.6 | Every resume finds the session wholly before or wholly after |
| 12 | **A word worth keeping.** A run invents an operator that works. | It is proposed for the workspace, approved by a person, and used by the next thousand runs; an old run is replayed | Rule 4; laws 5, 8 | Not usable by anyone before approval; old replay unchanged; the drift budget counted it |
| 13 | **Two engines, one session.** | The same recorded session, cell for cell, on PACT's reference and on Bud Agent Flow | Conformance | The same admissions, refusals and records |

---

## 13. Measures, and the bar for each

The bars marked *proposed* are starting points; K0 measures the baseline and
they are then fixed before the phase they gate.

| Measure | Bar |
|---|---|
| Operations with a written form | 76 of 76 |
| Shipped trees whose Core printing loads to the identical document | all |
| Keywords classed intrinsic or word | at least 85%, each stuck one explained |
| Shared cases identical through Core, and through the kernel interpreter | 80 of 80 |
| Escapes in the red-team set and in generated programs | 0 |
| Run-time rules whose removal no test notices | 0 |
| Admission time per proposal, 95th percentile, largest corpus tree | under 100 ms (a cold whole-tree check measures 60 ms today) |
| Sessions left inconsistent by a kill | 0 |
| Live: cells admitted at first try (*proposed*) | 80% on basics, 60% on stress |
| Live: admitted after one refusal (*proposed*) | 95% |
| Live: after a refused attack, the model stays within the rule | 5 of 5, every rule |
| Live: tokens for by-reference tasks against tool calls | fewer, at equal or better accuracy |
| Cold readers who write the worked example in Core from one page (*proposed*) | 4 of 6 |

---

## 14. What could go wrong, and what would show the plan is mistaken

| Risk | How it would show | What is done |
|---|---|---|
| Most keywords cannot be written as words | K0's stuck list is large | The prelude is cut to what was proven (§8, K0); Core and the live session stand without it |
| Core becomes a second language with its own bugs | A tree means one thing in keywords and another in Core | Core lowers to the same document and the same checker until K4; §9.3 is in the gate from K1 |
| A change during a run breaks a guarantee | A red-team attack or a generated program gets through | Rule 1 makes the existing checker the judge; §9.4 and §9.5 run on every change to K6 |
| Models write Core badly | The battery's first-try rate is low and does not recover after a refusal | Cells stay an option beside tool calls; the comparison of §11 decides where each is used. Core is still worth having for people |
| The checker becomes a way to stall a session | Scenario 8 slows other runs | Rule 8, with its own budget and test |
| The language grows expressions by the back door | A request to compare two computed values inside a condition | D3 holds; a pure program computes and a Check compares, so the checker still reads every decision |
| The no-code author is left behind | Documentation and examples drift to Core | The prelude is the keywords; `pact write` prints either; the guide's first page stays the keyword page |
| Scale of the work | A phase misses its gate | Each phase merges something that stands alone; the plan can stop after any of them |

**What would falsify it.** Three findings would mean this should not be built
as written: the stuck list is most of the keywords; no model tested writes
admissible cells at a useful rate even after refusal; or holding the ten
rules costs more per ask than a model call. K0 answers the first, and the
battery and the timing in K6 answer the other two before K7 to K9 are spent.

---

## 15. What the owner is asked to decide

The plan proceeds on the defaults of §3. These five are the ones worth a
moment, in the order they bind.

| Before | Question | Default |
|---|---|---|
| K0 | Is "the keywords become a library" a goal in itself, or only if the evidence supports it? | Only if K0's count supports it |
| K1 | Same `.pact` files, or a separate file type for Core? | Same files |
| K1 | No expressions in the first version? | None; arithmetic is a pure program |
| K6 | May a model act by writing cells, given that code as an *authoring* surface was rejected in August (`docs/28` §4.8)? | Yes, because a cell is PACT Core and not a host language |
| K8 | May anything a model defines ever be kept for the workspace? | Only by promotion that a person approves |

---

## 16. What happens first

K0, and nothing else until its gate is read:

1. Write the four workspaces in Core by hand and make them load to the
   identical document.
2. Run the keyword classification and publish the stuck list.
3. Measure a check per proposal with the tree held in memory.
4. Report the three numbers to the owner with a recommendation: the whole
   plan, the plan without the prelude, or stop.
