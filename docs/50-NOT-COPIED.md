# PACT — What Was Not Copied

**Date:** 2026-07-28. **Status:** Binding, in the same sense as `01-DECISIONS.md`.
**Reads against:** `spec/schema.yaml` (what PACT *has*), `01-DECISIONS.md` (why),
`research/notes/eve-capabilities.md` (every Eve capability, numbered, with the
file it was read from), `research/notes/eve-teardown.md` (how Eve is built).

> **A specification that does not say what it refuses accumulates everything.**

Eve is 171,782 lines and 80 distinct capabilities as the plan counts them — 98
once they are enumerated one by one out of the source, which is what §8 now does.
PACT reached parity by taking the general mechanism each Eve feature is a special
case of, not by porting the features one at a time. That method has one honest hazard: anything left out
quietly becomes a to-do rather than a decision, and six months later somebody
adds it "for completeness". This file is the list of things that are decisions.

Nothing here is a gap. Every entry was available, was understood, and was left
out — and says what an author who wants that behaviour does instead.

---

## 0. How to read this file

Every one of Eve's capabilities lands in exactly one of three places.

| | Category | Where you check it |
|---|---|---|
| **(a)** | **Expressible** — an author writes it in YAML or Markdown | `spec/schema.yaml`, and `examples/refund-desk/` for a worked one |
| **(b)** | **Declared and delegated** — the spec says it must happen; the host makes it happen | §4 below, and the schema comments that say so at the point of declaration |
| **(c)** | **Refused** — PACT will not have it | §5, the ledger, with a reason for each; or §6, where a capability is *deferred* with the fixture that lets it back in |

There is no fourth category. If you find an Eve capability that is in none of
the three, that is a defect in this file, and the fix is to add a row to §5 or
to add a field to the schema — never to leave it unlisted. §6 is inside (c) and
not beside it: "deferred" is still "listed here with a reason", and the reason
has to name what would change the answer.

**The count is §8**, and the list it counts is
`research/notes/eve-capabilities.md` — one numbered row per Eve capability, with
the file it was read from and its letter. §8 used to say which part of the
acceptance clause this repository could check and which part it could not,
because that list lived outside the tree. It does not any more.

**What counts as a reason.** A reason names a constraint PACT is under, or a
consequence PACT is unwilling to pay. "We did not need it" is not a reason.
"It requires a hosted service and PACT must run air-gapped" is. Every row in §5
is held to that, and a test enforces it.

---

## 1. The four refusals taken up front

These four were settled before the schema was written, because each one would
have shaped it.

### 1.1 Tools that exist without a file

**What Eve ships.** Twelve tools compiled into the framework itself —
`bash`, `read_file`, `write_file`, `glob`, `grep`, `web_fetch`, `web_search`,
`todo`, `ask_question`, `agent`, `load_skill`, `connection_search`
(`packages/eve/src/runtime/framework-tools/`, one file each). Seven are ordinary
calls onto a sandbox or the network. **Five cannot be reproduced by an author at
all**, because they read or write things that live inside the harness and are
handed to nothing else:

| Tool | What it reaches that an author cannot |
|---|---|
| `agent` | the delegation path; the runtime does not even register it in the tool list, per the source's own note |
| `ask_question` | the pause-and-wait path for human input |
| `todo` | a private store called `eve.todo`, plus a label that protects it from tidying |
| `load_skill` | the private list of loadable skills |
| `connection_search` | the private list of connected servers; it is registered as a resolver rather than as a tool |

There is a matching helper, `disableTool(name)`, whose only job is to turn one
of these off — and misspelling the name is a build error, which is a good rule
solving a problem that only exists because the tools have no files.

**Why PACT declines.** PACT collapses every way of providing a tool into one
kind. A `tool` file says what the tool does and, on exactly one line, where it
reaches: `connect:` for a server the host has set up, `url:` for an address it
publishes, `says:` for a question put to a model. Three lines in place of the six
separate authoring helpers Eve needs. (A fourth naming a script for PACT to run
is not among them, and R42 in §5 says why.) None of the three requires the tool
to be implemented anywhere but inside the host, so PACT has not banned built-in
implementations; it has banned **tools that exist without a file**.

For one round there was a fourth line, `runs-as:`, whose job was to say which of
the other three applied. It was read by nothing, and two of its four choices
named ways of running that nothing here carries out — R60. What replaced it is
not a smaller word but a check: writing two of the three, or none, is refused by
`pact check` at the line it was typed on.

The difference is the whole of D14. A tool with no file cannot be opened, cannot
be copied and narrowed, cannot have `spends-money` ticked on the one action that
moves money, and cannot be put behind an approval question — because there is
nowhere to write any of that. A non-technical author would face a set of powers
that behave differently from every other power in the system and that they can
only switch off. That is the privileged sixth thing, and one privileged thing is
how a format starts growing a second grammar.

It also breaks the allow-list. A PACT tool names its actions, and anything the
server offers that is not named is refused. A built-in with no file has no list
to be missing from.

**What to do instead.** Write the file. `examples/refund-desk/tools/` has two:
`payments.yaml` and `zendesk.yaml`. Each names its actions, marks which ones
only look things up, marks the one that moves money, fixes the argument that
makes two calls the same call, and says which values an approval rule may look
at. That is more than Eve's built-ins carry, and it is fourteen lines.

The five privileged ones each have a home:

| Eve's built-in | PACT's answer |
|---|---|
| `agent` | `team:` and `teamwork:` in `agent.yaml` — who helps, and how it waits for them |
| `ask_question` | a file in `questions/`, and a rule in `policies/` that points at it |
| `todo` | `remembers:` — a thing it keeps, with how long it lasts written down |
| `load_skill` | a folder in `skills/`; the runtime loads the body when it is needed |
| `connection_search` | `resources/` says what exists; each tool's `actions:` says what may be called |

Turning one off is deleting a line, so there is no helper for it.

### 1.2 A durable-execution protocol as a dependency

**What Eve ships.** Durable conversations, turns and steps, with parking and
resuming, built on Vercel's Workflow SDK. It is vendored at `5.0.0-beta.*`
(`@workflow/core`, `-errors`, `-serde`, `-utils`, `-world`, `-world-local`,
`-world-vercel`), 33 non-test source files carry the `"use workflow"` or
`"use step"` marker, and the package's one runtime dependency is `nitro`, which
hosts every route. The build emits a Vercel-shaped output.

To be fair to it: an offline store exists and is the local default, and the
store is swappable by package name. The semantics are good and PACT copies them.

**Why PACT declines.** D17 makes fully air-gapped one of four required
deployment targets, and states the consequence as a prohibition:
*"forbids any core feature that requires a hosted service."* That is a
constraint, not a preference — an air-gapped install is a place PACT has
promised to run, so a feature that cannot run there is not a feature PACT can
have.

The version numbers are the second half of it. A specification whose meaning
depends on a beta protocol from one vendor is a specification with a version
number it does not control. The portable artifact must still mean the same thing
in five years, on a machine that has never seen that vendor.

Concretely, what a hosted dependency costs is visible in Eve's own model
handling: the facts a build needs about a model come from a web address, cached
for a day, with an offline fallback list of exactly three models — and the
default model is not one of the three. A fresh, fully air-gapped build of a
default Eve agent therefore **fails**, and the way out is to hand-write the
number in TypeScript. That is the failure PACT is refusing, not a hypothetical.

**Why this is not a gap.** PACT copies the durable-execution *semantics*
wholesale — sessions, turns, steps, parking, resuming, cancelling as a normal
ending rather than a failure. What it refuses is adopting anyone's protocol.

**What to do instead.** Nothing. Durability is declared and the host supplies
it. `allow-egress: []` in `workspace.yaml` is the same rule at the workspace
level: nothing may talk outside the box unless a person adds a role to that line.

> **Correction.** This paragraph used to end *"A workspace that names something
> the host has not bound is caught by `pact check` rather than discovered at run
> time."* That was false in both halves. `pact check` resolved no cross-file name
> at all — `loop: carefull` and `asks: keep-goin` both loaded clean — and the one
> reference that genuinely points at a **host** binding, `port.through:`, is the
> one `pact check` still cannot resolve, because no file in the tree lists the
> connectors a runtime has set up. Names the *workspace* declares are now resolved
> (architecture §7.12); a name the *host* binds is checked by the host, and that
> is the difference between the (b) column and the (a) column of this file.

### 1.3 The developer's terminal app

**What Eve ships.** A development console: 95 files and 17,838 lines of
non-test source under `packages/eve/src/cli/dev/tui`, of which the screen
renderer alone is 4,754 lines (`terminal-renderer.ts`). It is a good one — a
model picker, a setup flow, a question panel, a todo panel, diagnostics.

**Why PACT declines.** It is a tool, not a specification, and the two have
different lifetimes. D2 makes the folder tree the native form of an agent and
requires it to be directly interpretable — no build artifact may be needed to
run it. A portable artifact that leans on a terminal renderer is portable only
to machines with that renderer.

There is a second reason and it is the sharper one. D18 names four author
surfaces — files in an editor, a UI that reads and writes the same files, a
conversation with a builder agent, and a git review with results attached — and
says the file format is the API for all four. Seventeen thousand lines spent on
one of the four makes the other three second-class by weight alone. The
investment belongs in the format, where all four surfaces collect it.

**What to do instead.** `pact check` on the folder. It names the file, the line,
what is wrong, and a fix you can type — which is the obligation O7.3 sets, and
the thing a console is mostly a wrapper around. Anything richer is a tool
somebody builds on top, and it reads the same files.

### 1.4 Running the author's code in order to check it

**What Eve ships.** Compiling an agent loads and executes every authored module:
tools, channels, sandboxes, schedules, skills, prompt layers and subagents are
all bundled and imported, and their exported factories are called. Eve's own
error message says it plainly — *"Failed to execute the … export"*. There is no
check that does not run the thing being checked.

**Why PACT declines.** Two decisions, and they point the same way.

D14 sets the no-code ceiling: a non-technical domain expert must be able to
build a full system with custom tools, their own example cases, limits and
learning, entirely in YAML and Markdown. If checking a workspace means running
it, then every author is running code, whether they wrote any or not.

D2 requires the tree to be inspectable. Reviewing a workspace a colleague sent
you must not be an act of running their machine's instructions on yours. This is
already enforced at the point it bites hardest: a connected server in PACT
carries a reference to an address and a reference to a stored credential —
**never a command, never arguments, never a credential value** — precisely so
that opening someone else's workspace cannot start a process.

**What to do instead.** `pact check` reads the tree, matches it against the
schema, and resolves the names one document gives another — an agent's `loop:`,
`policy:`, `context-policy:`, `interceptors:` and `uses:`, every `asks:`, a
port's and a schedule's `answers:`, a rule's `question:`, and a stage's
`starts-at:`, `then:` and `may-use:`. It never runs anything, and it never
resolves a name only the **host** can know (§7.12, REF-3). Code is still allowed
and still useful, but it is a declared, out-of-process thing: a script inside a
skill folder, which a person runs. It runs when the agent runs, under the sandbox
and the approval rules — not when someone opens the folder to read it. (A fourth
transport line naming a script — `runs-as: code`, when a word still stood in
front of the three — was the earlier answer here and is refused: R42.)

---

## 2. Refusals inside the eight mechanisms

Each of G1–G8 replaced a hardcoded Eve behaviour with something an author
writes. Each also stopped somewhere, and where it stopped was chosen.

The shape is the same every time: **the choices are a closed list, and the
author picks from it.** The alternative — an expression an author writes freely
— would give more power and would cost the one property the whole format is
built on. A closed list can be shown as a set of buttons (D18), can be
classified for blast radius (D23), can be given a plain-language explanation
next to every option (D13), and can be checked before anything runs. A written
expression can do none of those, and the first person to need one is by
definition not the author D13 describes.

| | Mechanism | What PACT refuses | Because |
|---|---|---|---|
| **G1** | Loop as data | Any way to write a condition for moving between stages. A stage has exactly three outcomes — used a tool, answered, ran too many times — and the author says where each one goes. | Three outcomes is a table anyone can read. A condition language is a second programming language living inside the file that was supposed to remove the first one. |
| **G2** | Termination | Two things: a separate give-up action per ceiling, and a fourth word for the action itself. Also deleted: the older `stop-after` grouping, which counted the same thing twice under two names. | The first is argued in full at `spec/schema.yaml` (the `limits` comment) — what to do when the budget is gone is a property of the work, not of which meter emptied first — and is not restated here. The second is §2.1. |
| **G3** | Context policy | Author-supplied code in a tidying step. There are four moves — shorten long results, drop parts, summarise older, keep recent only — and they compose in the order written. | The moves are what every framework's compaction code actually does, named. Admitting code here would put the one operation that silently loses information beyond review. |
| **G4** | Event lattice | Author-invented parts and moments. The scopes and the moment-words are fixed; authors get a reserved space for their own *names* within them. | An address only works as an address if two systems read it the same way. If everyone can mint scopes, a rule written against one workspace means nothing in another, and the lattice stops being portable. |
| **G5** | Interceptors | Interceptors that run code, powers beyond the three an author may write, **and sentences outside the four that exist**. What one may do is `hide-values`, `stop-the-run`, `send-elsewhere`; what it does is one of four sentence forms, listed under `rules:` in the schema. **Every power in that list has a sentence that reaches it and an address that carries it out**, and the two that did not are gone from it — R24, with the reason and the way back in §6. | These are the only things in the system that can change a run in flight. A closed list of powers is what lets a reviewer answer "what can this do?" by reading one line. The sentences are closed for the same reason as G1's outcomes — and, harder won, because an *open* set of sentences means most of them do nothing, which is worse than refusing them: the author believes they are protected. That argument applies to the POWER LIST too, which is why it is now three: `change-the-request` and `change-the-answer` were choices a non-coder could type that every sentence then refused. |
| **G6** | Suspension | A construct for pausing. There is no `suspend` anywhere in the schema — deliberately. | Waiting is what already happens when a person is asked, when a connection is not yet allowed, or when nobody answers in time. Eve has five separate pause kinds, each with its own bookkeeping; a sixth concept for the same act is a construct that overlaps one that already works. |
| **G7** | Questions | Any wording that lets silence count as approval. `if-nobody-answers` offers decline, escalate, and stop-and-say-so, and no fourth word exists. | If the word existed in the file format, every guarantee downstream would be one edit away from being switched off, by someone who thought they were setting a convenience. |
| **G8** | Teamwork | A join rule the author writes as an expression. `waits-for` is five named ways to wait. | Same reason as G1. The five cover what teams actually do; a sixth is a schema edit, and the schema is data. |

### 2.1 The fourth way for a run to end, and why there is not one

Worth its own section because it is the one somebody will propose again, and
because the reason is not obvious from the three words that are there.

**What was proposed.** A fourth choice for `when-it-runs-out`: **`park`** — stop
now, carry on later, tell nobody. It is the natural fourth, and it is what Eve
does. Its running-out-of-budget case is one of five separate kinds of pause,
each with its own bookkeeping and its own guard.

**Why PACT declines.** Because `ask-a-person` already parks. Not "could be made
to" — reaching a ceiling with `ask-a-person` writes the whole run down and stops
it, costing nothing while it waits, and something picks it up when the answer
arrives. `park` would be that exact mechanism with the person taken out: one
setting, spelled twice. That is the `same-setting-twice` mistake PACT's own
checker exists to catch, appearing in the format the checker is written in.

And taking the person out takes the way back out with it. A stopped run starts
again when somebody says yes, and by nothing else — there is deliberately no
wording anywhere in this format that lets a silence or a timeout say yes on
their behalf (§2, G7). So a run parked with nobody told has no exit at all. That
is not a governance option, it is a run that never finishes, and Eve's version
has precisely that shape: a run waiting on an approver who left the company
waits forever.

**What to do instead.** `when-it-runs-out: ask-a-person`, and name the question.
`examples/refund-desk/questions/keep-going.yaml` is that question, in full:
*"This is taking longer than it should. Keep going?"* — with who is asked, how
long they have, and what happens when nobody answers, which is
`stop-and-say-so`. Eve has this same question and nowhere to put it, so it ships
as an Approve/Stop pair borrowed from the approval widget, for a question in
which nothing is being approved.

---

## 3. Eve capabilities PACT does not mirror at all

### 3.1 A hosted catalogue as the source of model facts

**What Eve ships.** The facts a build needs about a model are fetched from a web
address and cached for a day, with a built-in offline list of three models that
does not include the default one.

**Why PACT declines.** D8 makes the local catalogue authoritative and offline
capable, and D17 makes that mandatory rather than nice. A machine with no
network must be able to validate, resolve, build, evaluate and optimise. A
catalogue behind a web address makes the first of those five impossible.

**What to do instead.** `models/catalog.yaml` ships with the distribution and is
read from disk with no network call. The author never writes it — the reason is
D14 rather than convenience: a support lead cannot hand-enter a context window
for every model they might be moved onto, and the first thing a run needs in
order to be measured at all was the one file with no no-code path.

A workspace-local `models/catalog.yaml` **overrides it, row by row**, with the
same per-figure provenance requirement, and is never a prerequisite. That layer
is what an air-gapped author serving a model this distribution has never heard
of writes; without it their `context-policy:` was permanently reported as
unenforced and the only way out was editing a file inside the product. It is the
`models:` block of `spec/schema.yaml`'s `workspace` kind, `pact check` resolves
`model:` and `summarised-by:` against both layers at once, and
`test_a_workspace_may_add_a_model_the_distribution_has_never_heard_of` holds it.

Better still, most agents should not name a model at all: `needs:` says what the
model has to be able to do — how much thinking, whether it must call tools,
whether it must see pictures, how much it must hold — and PACT picks, then says
what it picked and why. Every one of those lines is now read by the resolver;
for a round they were parsed and bound against nothing.

### 3.2 Orchestration code the model writes while it runs

**What Eve ships.** A tool that lets the model author JavaScript which fans out
to child agents inside one durable step, capped at 100 children. It is the only
real way to shape Eve's loop.

**Why PACT declines.** This is the model deciding the topology, in code, at run
time. It cannot be reviewed before it runs, cannot be diffed, cannot be signed,
and is not the same twice. D22 lets an agent change its own structure and D23
requires anything touching tools, permissions or decision logic to go past a
person first — which is only possible if the change exists as something a person
can read *before* it takes effect. T6 says the same thing shorter: an agent that
learns must still be an agent you can read, review, sign, fork and port.

**What to do instead.** `team:` names who helps and what each is for. `teamwork:`
says how the parent waits and how the budget is shared. Both are lines in a file
that a person can read this morning and a reviewer can compare against yesterday.
If the shape itself should change, that is the learning loop, and it produces a
diff to a file.

### 3.3 Extensions as installable packages

**What Eve ships.** Reusable bundles mounted from packages, with a namespace,
eleven versioned contracts, first-registration-wins merging, and rules about
what may not mount what. Alongside it, no sharing mechanism for the simple case:
Eve's own documentation tells you to copy the Markdown into each folder.

**Why PACT declines.** The package system exists to solve sharing, and sharing
was already solved by naming. A skill, tool, policy, question, loop or context
policy sits once in the workspace, and any agent that wants it names it. In
`examples/refund-desk/`, the refund policy is one folder that two agents both
name in `uses:`. Nothing is copied and nothing is installed.

Adding a package layer on top would buy cross-workspace reuse and cost the
property that makes a PACT folder reviewable: that everything the system does is
in the folder you were handed. It would also need a resolver, a lock file for
it, a version policy and a trust model — a subsystem, for a problem naming
already covers.

**What to do instead.** Put the shared thing at the workspace root and name it.
To share across workspaces, copy the folder — which is a thing you can read,
diff and sign, and which behaves identically wherever it lands.

### 3.4 Checks that can only be written as code

**What Eve ships.** Evaluations as imperative TypeScript with four judge-based
measures. The earlier declarative form was removed.

**Why PACT declines.** T2 makes the evaluation suite the mechanism by which
portability is decided — it is the oracle for model swapping, for framework
lowering, and for whether a learned change is kept. D19 then requires five ways
in, four of which are for people who cannot write code. A suite only an engineer
can write is a suite most agents will not have, and an agent with no suite
cannot be ported at all, because nothing can say whether the port worked.

**Why this is not a ban on code.** Code-based checks stay possible (F-2). What
is refused is code being *necessary* for a check that could be described.

**What to do instead.** `evals/suite.yaml` and one file per case. Write an
example, or a plain rule, or promote a real conversation that went wrong. See
`examples/refund-desk/evals/`.

---

## 4. Declared and delegated — not refused

These look like omissions and are not. PACT carries the declaration; the host
does the work. The schema says so at the point of declaration — for example,
above `port`: *"PACT DECLARES a port. The runtime CONNECTS it. Nothing here
knows what a Slack block looks like."*

| Eve ships | PACT declares | The host supplies |
|---|---|---|
| Eight platform connectors plus a way to write more | `ports/*.yaml` — what arrives, who may send it, what makes two messages one conversation | the connector for Slack, email, or whatever else |
| A separate scheduling subsystem | `ports/*.yaml` with an `every:` line — that line is what makes a port a timer, so `kind: schedule` beside it is optional — plus which agent (`answers:`), what to ask it (`says:`), and what to do if the last run is still going (`if-still-running:`) | the clock |
| Four sandbox implementations plus custom | a resource of kind `sandbox` | the sandbox |
| Seven ways of verifying a caller | `who-can-reach-it:` on a port | the checking |
| Durable sessions, turns and steps | that a run must survive being killed and resume to the same place | the store |
| A stream of run events | the addressing scheme for events and where interceptors attach | the transport |
| Cancelling a turn in flight | that cancelling is a normal ending and not a failure — §1.2's durability semantics, which PACT copies whole | the interruption itself: only the transport can stop a model call it has already started |
| A session-scoped key-value store (`defineState`), untyped, with no expiry, no migration, and its own docs saying not to use it for long-term memory | `remembers:` on an agent or a port — what is kept, how long it lasts (`one-step`/`one-turn`/`one-conversation`/`forever`), what shape it has, when to forget it, and **what may never write to it** | the store, and the refusal of a write from a source `never-from:` names |
| How much context a model can hold | `models/catalog.yaml` — one row per model, one window per row, with the source and the date beside the figure, and the word `unknown` where nobody in this distribution can attribute one | serving the model, and reporting the window through `context_window()` when the runtime knows better than the catalogue — a shorter `num_ctx` than the model card publishes is a fact only the runtime has. A transport that will not say, over a model no row covers, leaves `context-policy:` unenforceable, and the run reports it on `unmetered` rather than guessing |
| One model summarising another's history | `context-policy.summarised-by:` — which model writes the summary, resolved against the same catalogue | the summarising call itself, through `write_summary()` on the transport. A transport that cannot re-bind to a second model reports `summarised-by` on `unmetered`, so a rung of the author's ladder never silently fails to fire |
| Author-set attributes on a trace (`experimental_setAttributes`) | `watch` — which moments to record and what each one carries. A moment is nameable in the format; a span is not, because a span is a shape one tracing vendor chose | the exporter, and the trace itself. PACT names the moment; what a moment becomes on the wire is the host's |
| An integration catalogue of servers a machine can reach | `resource.endpoint` — the author names one server, by a name their platform team publishes | the list of what this machine actually has. A registry of it in the format would make the portable artifact depend on one host's inventory (R20) |

The line is worth stating once, because it is the same line every time: **PACT
holds what a reviewer must be able to read, and what must be identical on two
different machines. Everything that tracks someone else's API belongs to the
host, or the portable artifact rots at the speed of eight third-party APIs.**

This is D24 as well: registry, routing and multi-tenancy stay minimal and
adapter-shaped, because a system for that already exists.

---

## 5. The ledger

The (c) column, in full. Every row names the constraint or the consequence, not
a restatement, and points at the section that argues it.

| # | PACT refuses | Because | Instead | Where |
|---|---|---|---|---|
| R1 | Tools that exist without a file | a tool with no file cannot be read, narrowed, priced or put behind an approval — so it behaves unlike every other power in the system | write the tool file; one of `connect:`, `url:` and `says:` covers every way one can reach somewhere, and writing none of them or two is refused | §1.1 |
| R2 | A helper for switching a built-in tool off | the helper only exists because the tool has no file; when it has one, switching it off is deleting a line | delete the line | §1.1 |
| R3 | A durable-execution protocol as a dependency | it pins the meaning of the artifact to one vendor's beta version number, and air-gapped is a place PACT has promised to run | declare that a run must survive being killed; the host supplies the store | §1.2 |
| R4 | Developer tooling inside the portable artifact — a terminal app, and framework client bindings for React, Vue and Svelte | the tree must be directly interpretable, and weight spent on one author surface makes the other three second-class; bindings also date at the speed of three UI frameworks, which the artifact must not | `pact check`, and any tool built on the same files — the files are the API for all four surfaces | §1.3 |
| R5 | Running the author's code in order to check it | reviewing a workspace someone sent you must not be an act of running their instructions | checking reads and resolves; code runs when the agent runs, under the sandbox | §1.4 |
| R6 | An expression language for loop transitions | it is a second programming language inside the file that was meant to remove the first | three named outcomes, and where each one goes | §2 (G1) |
| R7 | A separate give-up action per ceiling | five actions are five chances to write a governance rule that contradicts itself | one `when-it-runs-out`; the run reports which ceiling it was | `spec/schema.yaml`, `limits` |
| R8 | A fourth way to end at a ceiling — `park`, meaning stop now and tell nobody | `ask-a-person` already stops the run and costs nothing while it waits; taking the person out takes the way back in with it, leaving a run with no exit | `when-it-runs-out: ask-a-person`, and name the question that gets asked | §2.1 |
| R9 | Author-supplied code in a tidying step | tidying is the one operation that silently loses information, so it must stay reviewable | four named moves, composed in the order written | §2 (G3) |
| R10 | Author-invented event parts and moments | an address only works if two systems read it the same way, and minted scopes do not travel | fixed scopes and moments; a reserved space for your own names | §2 (G4) |
| R11 | Interceptors that run code, or hold powers beyond the five | these are the only things that can change a run in flight; a reviewer must be able to answer "what can this do?" from one line | a closed list of powers, and rules in sentences — four forms, compiled by `Chain.from_document` | §2 (G5) |
| R19 | A sentence in `rules:` that PACT cannot carry out | an unrecognised sentence can only be ignored, and a rule that loads and does nothing is worse than one that fails: the author believes the card numbers are being stopped | one of the four published forms; anything else is refused naming the file, the rule and the forms that work | §2 (G5) |
| R20 | Resolving a name only the host can know | `port.through:` names a connector the runtime has set up, and no file in the tree lists them, so there is nothing here to resolve it against; a registry of them would make the portable artifact depend on one host's inventory | the host checks its own bindings; `pact check` resolves every name the **workspace** declares | §1.4 |
| R21 | Two spellings for one setting on the native authoring path | a second accepted name makes the expansion non-injective and lets one line silently discard another with no diagnostic, and it leaves the reader D13 describes with two words to look up for one idea | one name, everywhere — alias tables live only inside importers, applied to documents declaring a foreign origin | `spec/schema.yaml` |
| R22 | A folder path as an agent's only identity | two agents called `support` in different repositories become indistinguishable, renaming a directory silently re-identifies every persisted approval keyed on a tool name, and a build in a CI checkout once produced the agent id `path0` | `name:` is required and `workspace-id:` is minted once by `pact init`, so the path is where a document lives and never what it is | §1.1 |
| R23 | One port writing into another port's session | routing between conversations is platform work with its own delivery guarantees, and a system for it already exists; putting it in the format would make the portable artifact carry a router it cannot honour on a machine that has no queue | a port names the agent it `answers:`, and the host routes | §4 |
| R12 | A construct for pausing a run | waiting already happens when a person is asked, when a connection is not allowed, and when nobody answers — a second concept would overlap one that works | ask a question; the run waits | §2 (G6) |
| R13 | Any wording that lets silence approve | if the word existed, every downstream guarantee would be one edit away from being switched off | decline, escalate, or stop and say so | §2 (G7) |
| R14 | A join rule written as an expression | same as R6; and five named ways to wait cover what teams actually do | `waits-for`, plus a schema edit when a sixth is needed | §2 (G8) |
| R15 | A hosted catalogue as the source of model facts | a machine with no network must still be able to validate and resolve, and a fetched catalogue makes that impossible | a local catalogue file; better, say what the model must be able to do and let PACT pick | §3.1 |
| R16 | Orchestration code the model writes while it runs | it cannot be reviewed before it runs, diffed, signed, or reproduced — and structural change is exactly what needs a person | `team:` and `teamwork:`; structural change arrives as a diff | §3.2 |
| R17 | Extensions as installable packages | naming already solves sharing, and a package layer costs the property that everything the system does is in the folder you were handed | put the shared thing at the workspace root and name it | §3.3 |
| R18 | Checks that can only be written as code | the evaluation suite is what decides whether a port worked, so a suite most authors cannot write makes most agents unportable | example cases, plain rules, or promoted conversations; code stays possible, never necessary | §3.4 |
| R24 | An interceptor power a written rule cannot reach — `change-the-request` and `change-the-answer` were choices in `may:` that no sentence in the vocabulary produces, so declaring one and then writing any rule got the rule refused by the next check down | a choice a non-coder can type that nothing can ever use reads as a capability and is worse than an absent one; and offering it made the list of five look like five answers when three of them were the answers | the three that reach something: `hide-values`, `stop-the-run`, `send-elsewhere`. Rewriting a request or an answer stays available to the system running the agent, through the typed escape §5.5 requires — see §6 below | §2 (G5), **amended — see §8.5** |
| R25 | A **guessed** number for how much a model can hold, so that `context-policy:` always appears to work | a policy measured against an invented budget tidies at the wrong moment and reports that it tidied, which is the silent degradation T7 exists to name; a spend cap with no price list is already reported rather than guessed and this is the same shape | a **sourced** row in `models/catalog.yaml` — a figure with the place it was read from and the date beside it, or the word `unknown`. A model no row covers, on a transport that will not say, leaves the policy on `unmetered` with `session.limit.failed` naming it | §4 |
| R26 | A default context policy for a workspace that never asked for one | every framework's built-in recipe throws the model's own reasoning away and never mentions it, and the one thing that must never happen quietly is losing information | write a `context-policy:`; with none, nothing is dropped and a conversation that outgrows the model fails where it is visible | §2 (G3) |
| R27 | A model pin the run quietly measures around — binding one model and tidying for another's window | the two disagreeing means the run is answering on a model nobody chose, and either half of the obvious fix hides something: measuring against the pin tidies for a window the running model does not have, and ignoring the pin hides that the wrong model answered | the running model's window is used and the disagreement is named, both ids, on `unmetered` with `session.limit.failed` | §4 |
| R28 | A price nobody published, read as free | `cost: unknown` used to sort the one row this catalogue deliberately publishes as unsourced to the head of the list, so D11's recommendation line printed a figure nobody stands behind in the sentence the whole decision hangs on — the same shape as a guessed context window, one column across | an unpriced row ranks LAST, and the recommendation says `at a price this distribution cannot source` | §4, R25 |
| R30 | Binding a model that only answers off this machine, in a workspace that says nothing may leave it | `allow-egress: []` is a sentence a person approved, and a check that passes a hosted `model:` or `summarised-by:` under it turns that approval into decoration; the failure then arrives at run time, in another language, in a process a support lead never starts | `pact check` refuses it where the author is, naming the file, the line, the model, and a locally-served id to write instead — or `llm` added to `allow-egress:`, which is a change a person has to approve | §4 |
| R31 | Throwing a picture away because the summariser cannot read it | `summarise-older` folding a photo into text-only prose is exactly the "keep text, discard the rest" this file criticises, arriving through a step the author wrote as *summarise* and never as *drop*; and D16 puts vision and audio in v1, so it is not a corner | pictures and voice messages are carried into the checkpoint beside the summary and the summariser is told one arrived; `drop-parts` remains the only step that removes a kind of content, because the author named it | §2 (G3) |
| R32 | A spend ceiling that means one step, or one agent | a number that resets per step or per level is not a cap at all: measured, two delegating steps under one written `cost-per-request-under: 0.05 USD` spent 0.10 with nothing refused, and each level of a team added another whole ceiling | one pot per request, divided by `teamwork:` and charged by whoever spends — the parent's own calls, its team's, and their teams' all come out of the one figure the author wrote | §2 (G8) |
| R33 | Rebuilding every tidying step around waiting, so that one of them can wait for a model | three of the four steps never call a model at all, and rebuilding the whole mechanism around a wait to serve the one that does would change four things to fix one — for a call many workspaces never reach | the summarising call is made the plain way and the harness does the whole of the tidying to one side, so a teammate that summarises stops its own clock and nobody else's | §2 (G3) |
| R34 | Letting a parent turn off a teammate's own approval rules by being the one that called it | a specialist with its own `policy:` is an agent whose governance is its own, and a caller that could switch it off would make every approval rule conditional on who asked | the member runs under its own policy, and the one place that suppresses a gate — the eval runner, because a run that parks cannot be scored — says so at the line that does it | §2 (G7) |
| R35 | A moment that is spelled correctly and never happens — `session.tool.completed` | the three words are each in the list, so nothing about the shape of the line is wrong, and a watch bound there loads, is never reached, and writes nothing down; the author's own tool said the file was fine, which is worse than an unchecked field because it produced a reassurance | the moments a run really reaches are a list beside the words they are spelled from, per field, because a watch may look at thirty and a rule may change things at five; a moment outside it is refused naming the ones that thing really has | §2 (G4) |
| R36 | Checking a `shows:` name against a list PACT does not own | a question put about a pending action shows that call's own arguments — an order number, an amount — and PACT has no list of what any tool's arguments are called, so refusing `order-number` because it is not in a table here would refuse the author's correct line | the names are checked only where the run stopping is one PACT does own — a ceiling, a conversation that will not fit, a teammate who could not answer, a stage that asks — and a mistyped one there names the file, the line and what does work | §2 (G7) |
| R37 | Taking away the token ceiling because there is no price list | how many tokens a call carried and what they cost are two facts with two sources: a provider returns the first on every call, and only the model catalogue can supply the second. Tying them together took `tokens-at-most` off an author serving their own model on their own machine — which is the one place that ceiling is the only one left, and is what its own help text promises | an unpriced model reports the count and no price: the money cap is named as unenforced and the token cap goes on working | §4, R25 |
| R38 | A ceiling that measures a real zero, reported as a ceiling that works | five rows in the model catalogue publish a price of nothing, because this machine serves those weights — a sourced zero, not a missing one. So the meter is right, the spend is always 0.00, and an author is told their cap is being enforced against a number that can never move | the run says so in its own words, naming the file, the line, the model that is free, and the token ceiling to write instead — kept apart from "nobody could measure it", which would send the reader looking for a different runtime rather than a different ceiling | §4, R25 |
| R39 | A screen that tells somebody to answer under a name the wait will refuse | two calls stopped in one step must not be answerable by one reply, so the wait renames what it asks for; a screen built from the question's own wording then told the person to type `approved` at a wait keyed on something else, and it read as correct from both ends — the wording was the author's and the contract was right | one substitution, in one place: the answer names, the deadline and the audience on the screen are the **wait's**, and the wording, the reason and the values shown stay the author's | §2 (G7) |
| R40 | Discovering the core schema from the tree | `20-ARCHITECTURE-DRAFT.md` §8.2's whole safety argument is that a field's blast-radius class lives strictly further outside the search space than anything an optimiser can reach. `find_spec` walked UP from the target to the filesystem root, so an edited `spec/schema.yaml` in ANY ancestor directory rewrote the class of every field under it — measured, flipping `agent.remembers` from S-GOV to S-GEN made a state block with no `lasts:` print "OK — loaded cleanly", exit 0, and nothing in the output ever named which specification had been used | the compiled-in copy is the only core schema (LOAD-13). `$PACT_SPEC` needs a debug build AND a typed-out `--unsafe-spec`, and every run that uses it prints the source and the sha256 of its canonical form  | `spec/schema.yaml`, §1.4 |
| R41 | `open: true` on a group | it turned off the unknown-field check for a whole kind, and a field nothing knows about has no `surface:` — so an unvalidated group is an unclassified group, which is LOAD-13 exactly. Combined with R40 an attacker's `open: yes` on `agent` made `run-arbitrary: yes` load cleanly | the `x-` prefix, which is per FIELD and per author rather than per kind, and which round-trips untouched  | `spec/schema.yaml`, §1.4 |
| R42 | A tool that names a script for PACT to run — written `runs-as: code` while a word still stood in front of a tool's transport lines | every other way a tool reaches names a thing the HOST runs and PACT records; this one would make `pact check` the thing that decides whether a script is safe, which is R5 arriving through a field rather than through a build step | `connect:` with an MCP server the host has set up, or `url:` with an address it publishes. A script stays reachable — as something a skill's `scripts/` folder ships and a PERSON runs  | §1.4, R60 |
| R43 | A snapshot of what a server offered, with nothing that writes one | `tool.pinned` named `tools/payments.snapshot.json`, a file not in the tree, and `pact tools sync`, a command that errors — and it was read by no source file, so an author who wrote it got a field that loads and does nothing on the one mechanism meant to stop a server quietly gaining a money-spending action | `actions:` is the closed list, checked at load: anything the server offers that is not named there is refused. A snapshot returns when something writes one  | §1.1 |
| R44 | Two kinds for the clock, and then a second word for the one that was left | `schedule` and `port` were one thing wearing two names — `kind: schedule` was already a choice on a port, and a port written that way could not be made to work while the same file with `every:` and `says:` deleted loaded clean, declaring itself a timer that can never fire. Folding them left `kind:` required with four choices and only one of them doing anything: measured, the shipped `ports/weekly-review.yaml` changed from `kind: schedule` to `kind: event`, with `every: Friday at 4pm`, `says:` and `if-still-running: skip` untouched, printed *"OK — loaded cleanly (492 settings)"* and exited 0 | one `port` kind, and the `every:` line is what makes it a timer — so `kind:` is no longer asked for where the document already answers it, and can no longer disagree with it. `says:` and `if-still-running:` live beside `every:`, and all three are refused on a port that is not a timer, naming the file, the line, and the line to change  | `spec/schema.yaml`, `crates/pact-loader/src/ports.rs` |
| R45 | `jsonpath:` and `regex:` in a redaction rule | they are code in a format whose whole point is that a support lead can write it, and they sat under `policy.rules` — a field nothing read, on a kind an agent could never point at, because `agent.policy:` names ONE policy | a `redaction` kind bound once for the workspace, written in the SAME closed sentences an interceptor uses — one list now, shared rather than copied: `anything that looks like a card number`, `anything that looks like an email address`, `replace anything that looks like a bank account with "[gone]"`  | §3.4 |
| R46 | Prompt-cache markers placed for the provider that supports them | where a cache breakpoint goes is a fact about one provider's wire format and one runtime's connection pooling, and it changes with neither the agent nor the author. `limits.reuse-context` was the field that claimed it, appearing exactly once in the whole repository — in the schema itself | the transport places them. PACT declares nothing about it, which is the honest state for a decision no author can take  | §4 |
| R47 | A second enforcer for a ceiling that already has one | `slo.py` carried a `Budget` raising `SloBreach` from `check_elapsed` and `add_cost`, and nothing in `src/` ever constructed one — so `finishes-within` and `cost-per-request-under` were enforced by `Limits` and by nothing else, while a reader of `slo.py` believed there were two. A ceiling with two enforcers is a ceiling that will come to mean two things | one enforcer, `Limits.reached`. What genuinely has none — `first-reply-within`, `per-word-under` — is named on `unmetered` when the author wrote it  | `spec/schema.yaml`, §2 (G2) |
| R48 | A `must-match-shape:` eval rule | it pointed at `/agents/refund-desk/answers-with.yaml`, a file that is not in the tree because `answers-with:` is a block inside `agent.yaml` — and the shape an answer must have is already `answers-with:`, so a rule restating it is a second copy that can only go stale | `answers-with:` is the shape, and it is checked where the author is by `type: answer-shape`  | §3.4 |
| R49 | Naming a skill, a connected system or a policy in `always-keep:` and calling it a source | `from:<name>` is stamped in exactly one place — on a `role: "tool"` message — so only a TOOL or a TEAMMATE can ever be where a message came from. Resolving the other three to a `SOURCE` pin matched a label nothing stamps, kept nothing, and suppressed the words fallback that would at least have kept something. The worked example's own first pin was exactly that, and nobody was warned | the pin falls back to the WORDS and says which sources really work. A written procedure needs no pin at all: it reaches the model in the instructions, which tidying never touches  | §2 (G3) |
| R50 | A gate whose meaning follows the SPELLING of its answer field | `rulings.py` read a field literally named `approved`, and a question with no such field is cleared by having been ANSWERED — which is right for *"how much should we refund?"* and catastrophic for *"may we use the payments connection?"*. Measured: renaming that one word in the shipped consent question printed "OK — loaded cleanly" and turned the gate into a formality, so a support lead writing `answer: {ok: yes or no}` built something that could not be refused | any `yes or no` line is the gate, whatever it is called. `approved` still wins when present, so a question carrying a gate and an ordinary yes-or-no fact behaves as before  | §2 (G7) |
| R51 | Approvals that bind per agent and opt in | the polarity §7.19 KIND-4 already calls backwards for redaction, on the money path. Measured on the shipped example, `fraud-checker` reaches `zendesk/reply`, the policy gates it, and `pact waits` listed seven waits every one of which said `refund-desk`; one added line took that agent from 0 gates to 3 and `pact check` was silent either way | `policy.applies-to: every-agent`, the same field and the same two words `interceptor` has. The agent that forgets to name the money rules is the agent that spends without asking  | §3.4 |
| R52 | An eval oracle that reads a phrase without reading the negation in front of it | `EQUIVALENT["approved"]` contains `approve` and `eligible for a refund`, and each occurs inside its own negation — so *"This sale item is not eligible for a refund."* graded PASS against `expect: {decision: approved}`, and one string satisfied BOTH verdicts at once. The model-portability figure, the SLO gate and the learning gate are all computed from this number | one negation guard around the `in` test. The table stays closed and auditable rather than growing more phrases, because more phrases is how the next one gets in  | §3.4 |
| R53 | A `list of` field written as settings with a value each | it fell into the arm that forgives a bare scalar and was checked as text, which reports nothing — so `uses:\n  weather: yes` printed "OK — loaded cleanly", the agent was offered ZERO tools, and nothing anywhere said so. Sixty-two fields in the specification are `list of` or `map of`, and the two shapes sit next to each other in the same file | a map where a list belongs is refused, with the list spelling for the field actually written. The scalar leniency stays: that one really is a harmless slip  | `spec/schema.yaml` |
| R54 | Serving `card`, `waits`, `show` and `discover` from the loader alone | a tree `pact check` refuses was published as a valid A2A card, a valid wait list and a valid document at exit 0 — and `pact show` is the door every adapter in this repository reads through, so *only `check` refuses it* meant *every adapter accepts it*. With `asked-of:` deleted, `pact waits` handed a scheduler a human-approval gate on money that nobody can answer | all four run the same checks `pact check` does and refuse the tree the same way. The refusal goes to the error channel, so the machine-readable answer a runtime asked for is never mixed with it  | §1.3 |
| R55 | Writing model-portability strategies as callables the caller hands in | the only strategies anywhere in the tree were two Python lambdas in a test file, one of them the `decomposed` strategy the README quotes a measured result for. That is "expert users write code for this" on the headline differentiator, which D14 rules out for any capability in the core — and `agent.variants:` was `map of anything`, so `variants: {utter-nonsense: [1, 2, 3]}` also loaded clean | `variant` is a closed group and `resolve()` builds its search from it. The `strategies` parameter stays overridable for a test; it is no longer the only source  | §1.4 |
| R56 | A per-role `allow-egress:` message that quotes a line the author did not write | the diagnostic hardcoded `allow-egress: []`, so a workspace saying `[judge]` was told its file said something it does not — and the author who opens the file and sees otherwise stops believing the checker. A typo in any model id fell through the same branch and produced a confident false statement that a model existing nowhere *"is only served off this machine"* | the roles are rendered as written, and an id in no catalogue at all is left to `schema/no-such-name`, which reports it with the right message and the right fix  | §4 |
| R57 | `port.needs-approval-before:` — an approval written as free prose on a port | it named no question, so it carried no wording, no audience, no deadline and no if-nobody-answers, and it appeared on `pact waits` nowhere: every other approval surface in the format names a `question`. The shipped `ports/slack.yaml` said `- replying to a customer` while `policies/approvals.yaml` said the same thing one file away as `{ tool: zendesk/reply }` → `is-this-ok`, resolved and gated. Two ways to say one thing, one of them unactionable, is the same-setting-twice mistake the checker catches everywhere else | a `policy` rule, which is a real wait a runtime can walk  | §4 |
| R58 | Three of `resource-kind:`'s four choices | `sandbox`, `content-store` and `memory` had no field in the `resource` kind that only they would use — `endpoint:`, `auth:` and `asks-to-connect:` are all MCP-shaped — so a required field with four choices had one sensible value and three ways to be wrong. R60 makes the same argument one kind over, and settles it the same way: a choice that leads nowhere is the "loads and does nothing" failure | `mcp-server`. Each of the other three returns with the fields it needs, the way `kind: schedule` did  | `spec/schema.yaml` |
| R59 | `learning.auto-apply:` — a second setting for the decision `learning.enabled:` already takes | two settings for one decision is six spellings for three real states, and two of the six say opposite things. MEASURED: `enabled: propose-only` beside `auto-apply: yes` printed *"OK — loaded cleanly"*, exit 0 — while the reader takes `enabled:` first and throws the other line away, so the author's `yes` decided nothing and nothing anywhere said so. The reverse was worse: `enabled: yes` with no `auto-apply:` line defaulted to no, so the strongest word on the setting that decides whether a system rewrites itself with nobody watching meant nothing at all. And the obligation to list what may change was hung off `auto-apply:` by PRESENCE, so `auto-apply: no` — the line meaning *"nothing applies itself"* — demanded a list of what does | one setting with three answers named for what happens: `off`, `propose-only`, `applies-safe-changes-itself`. The obligation moved onto the third answer, so it is asked for exactly when it is owed, and the deleted spelling is refused by name with the surviving line offered as the fix  | `spec/schema.yaml` |
| R60 | `tool.runs-as:` — a word in front of a tool's three transport lines naming which one applies | it was read by NOTHING: not the loader, not an adapter, and not the worked example, which has never written it. Two of its four choices made it worse than idle — `prompt` and `built-in` named ways of running that nothing in this distribution carries out, so a tool written either way was still offered to the model and came back `error: no tool named ...` on the first call, with no diagnostic at check time and nothing on the run's own list of what it could not enforce. And it was never a choice in the first place: which of `connect:`, `url:` and `says:` is written already says where the tool reaches, so the word could only agree with them or contradict them, and a contradiction was accepted in silence | the three lines themselves. `url:` carries the one obligation the word really held (`method:` beside it), and a tool that writes two of the three, or none, is refused by `pact check` naming the file, the line, which of the three are set, and the line to type  | `spec/schema.yaml`, §1.1 |
| R61 | Two settings for what must never leave a workspace | `redactions:` was a set that could hold several groups of rules and `redaction:` was one piece of text naming one of them, so the SECOND group was unbindable by construction — and the warning written for exactly that case said *"Add a line: `redaction: staff-data` in workspace.yaml"*, which replaces the name already there and switches the first group off in silence, so following the advice turned protection off. MEASURED, the obvious repair was refused as well: `redaction: [customer-data, staff-data]` printed *"'redaction' should be some text, but it is a list"* — a true sentence about a shape the format should never have offered | one `redaction:` setting of the workspace, written as `redaction.yaml` beside `workspace.yaml` — the shape `learning:` already has, so the file IS the setting and there is nothing to bind, nothing to misspell and no second file left dangling. `hide:` is required, and the setting is now READ: a system that improves itself against a model off this machine is refused without one, which is AD-88's load-time rule arriving where the author is | `spec/schema.yaml` |

## 6. Deferred, not refused

Different thing, kept apart on purpose. These are not in v1 and each has a named
measurement or fixture that lets it back in; the list and the re-admission
conditions live in `25-ARCHITECTURE-DECISIONS.md` §4 ("What is explicitly NOT in
v1") and §13 of the architecture draft.

**Four Eve capabilities land here rather than in §5, because refusing them would
be untrue.** All four were found by walking Eve's inventory against the schema
and the shipped binary; each has a home in the format and no field or verb yet,
and putting a row in §5 would record a decision nobody took.

| Eve ships | what PACT would need | what lets it in |
|---|---|---|
| `toModelOutput` — a tool result reshaped before the model sees it, so a 40 kB payload reaches the model as three fields | a projection on `tool.actions.<a>`, and a way to write one that is not code (the sentence vocabulary in `interceptors` is the nearest precedent) | a case where `shorten-long-results` in a context policy is measurably worse than projecting at the source. Until then the tidying step covers the same ground later and reviewably |
| read-before-write enforcement — a tool that may not modify what it has not first read | an ordering constraint between two `actions:`, plus harness support to enforce it | the fixture is a workspace where a write action fires with no preceding read of the same key and the run is refused. `spends-money` already forces a same-request key and an approval, which is the larger half of the same hazard |
| remote agents — a teammate that lives on another deployment | a way to say, in `team:`, that a member is somewhere else, and an address for it. What exists today is `port.answers:`, and a port is entirely INBOUND — `kind:` is how work *arrives* — so it names a LOCAL agent that handles what came in and can never name a teammate to send work out to. This row used to be lettered (b) pointing at §4 on the strength of that field, which was the polarity confusion the plan's §3.1(4) says is real, written down as an answer | `pact card` already prints an A2A Agent Card and `discover` already reads one, so the wire half exists on both sides. What is missing is the authored half and one decision: whether a remote member is a `team:` entry with an address, or a `resource` of a new kind. The fixture is a workspace where one agent's teammate is served by a second workspace and the trace is identical to the local run |
| a verb that scaffolds a workspace — `pact init` | nothing in the format; a command. `spec/schema.yaml` promised this verb in the help text of two fields, which is worse than not having it: a non-coder reads help text as a description of what exists. Those promises are gone, and the fields now say what to do by hand | the same three-line folder the worked example has, written by a command instead of copied. It is deferred rather than refused because every argument for it is convenience and none of them is a constraint — and because `workspace-id:` is the only field whose help ever wanted a generator, which a person can satisfy with any long random string |
| nothing — this one is PACT's own, and it is **host-only rather than absent** | a sentence that *rewrites*. `change-the-request` and `change-the-answer` are real powers of the interceptor mechanism: `Decision.by` names them, `Interceptor.apply` checks them, and a host embedding the harness can produce one through §5.5's typed escape. What does not exist is a way to ASK for one from a file, because no form in the closed vocabulary rewrites — every one of them hides, stops, or sends the run elsewhere | a sentence somebody actually wants. `add "<text>" to what the model is told` is the obvious first one, and it is not written until there is a case for it that `instructions:` and a stage's `says:` do not already cover — both of which are reviewable in a way a mid-run rewrite is not. Until then the power is out of `may:` (R24) rather than sitting there as a choice nothing can use |
| nothing — PACT's own again: **hiding something by the NAME it is stored under**, which is what `redaction.hide`'s second sentence `the <name> of a customer` looked like | the sentence is gone with the merge of the two hiding vocabularies (R63). It had no second meaning PACT could carry out: everything `the email address of a customer` could hide, `anything that looks like an email address` already hides, so it was a second spelling of one act — which is the thing that merge exists to end. Its `<name>` was also open text, the one hole in either list that was never held against anything, so `the shoe size of a customer` loaded cleanly and hid nothing | the reading that is genuinely different: hide the value stored under a given label, whatever it looks like, so that a thing no pattern can recognise can still be named. It needs two pieces PACT has not got — a way to match a label across the spellings people write (`email address`, `email-address`, `emailAddress`), and a moment that carries labelled values, which today is `step.tool.before` alone. The fixture is a workspace whose tool takes an argument holding something unrecognisable, a line naming it, and a run where that argument arrives masked while every other argument arrives whole |

Recording them here rather than nowhere is the whole method of this file: a
capability in none of the three categories is a defect, and the fix is a row —
in §5 if it is refused, here if it is deferred, never silence.

**One deferral sits INSIDE a capability that is (a), and it is worth keeping
separate from the four above.** Eve's interactive authorisation — the park that
waits for a scoped grant and resumes on the callback — is row 52 of the inventory
and is lettered (a) correctly: an author writes `asks-to-connect:` on the server,
the question beside it carries the wording, the audience, the hour and what
happens when nobody answers, and every one of those reaches the run. What has not
landed is the last hop of enforcement: which calls WAIT is still learned from an
argument the host passes rather than from `uses:` → `connect:` →
`asks-to-connect:`. The shape it needs is known and is not the obvious one — the
wait belongs in the approval gate, where the eval runner's one suppression can
reach it, because seeding it beside the gate was tried and a scored eval case that
touches a gated connection then comes back "did not answer" with the model under
test blamed for a consent nobody had granted. **Until it lands the run says so**:
one sentence on `RunResult.unenforced` per gated connection, naming the file, the
line, and what not to rely on. A deferral that produces silence is the fourth
category wearing a delay; §7.14 gap (1) of the architecture draft carries the
measurement.

The one worth naming in §6 proper, because it is the closest to a refusal: **a
shared board that agents claim work from and hold a lease on.** The blackboard and
market patterns ship in push form only in v1 (AD-T7). The reason is that
inventing a lease design nobody has tested is worse than shipping without one,
and the open question — whether push form is enough — is recorded as AD-R6
rather than settled by assertion. If the fixture fails, either the claim-and-lease
form returns with a real design or the acceptance criterion is restated at six
patterns. Either way it is decided in the open, not accumulated quietly.

**Measured since, and it narrows this row rather than closing it.** The half of a
claim that is *mutual exclusion* already ships: `same-request-key: <id>` with
`same-request-key-across:` set wider than one run is exactly "only one of you gets
this". The reference harness withheld a second claim of `Q-7` made by a
**different agent** in a **different run**, once the host handed the record back.
So the deferral is not "PACT cannot express a contended claim" — it is narrower
and more honest: **what is missing is the lease.** Releasing a claim, seeing who
holds it, and expiring it, none of which `Ledger` can do — it has no release and
no introspection at all. Two things an author meets are worth writing down beside
it: on a non-money `claim` the checker still speaks in the vocabulary of money,
because the exactly-once gate is reached through `spends-money:`; and
`at_most_once.py:242` says "in this run" for a key whose scope may be the
workspace. Both are defects of *wording over a working mechanism*, and they land
as bug fixes in the phase that owns `money.rs`, not as a new construct. The
re-admission fixture is unchanged and is now sharper: **a workspace where one
agent takes a claim, fails, and a second agent may take it back.** Nothing in
what ships can express the third clause.

**Deferred alongside it, on the same evidence standard: self-consistency as a
field of its own** — "work this question several ways, then settle". It was
designed as `stage.tries`, built against the reference harness, and withdrawn.
Not because the idea is wrong but because **PACT already ships the shape**:
`examples/patterns/quorum/` runs three readers with byte-identical instructions
and a referee that reports disagreement rather than picking a winner, and each
member is a whole run with its own `history`, `Meter` and `Ledger` — independent
of its siblings *and* of the run so far, which a same-history fan-out inside one
stage cannot be. The built version also failed on its own terms: its runs were
byte-identical to `at-most:` except for a step counter it broke, its park lost
every try's work and re-charged it on resume, and it could not be demonstrated at
all through the only air-gapped model the project ships, because that model keys
its script on the assistant-message count and three tries have identical
histories by construction. The re-admission fixture is one sentence: **a case
`examples/patterns/quorum/` cannot express.** Until somebody writes one, "PACT
has no self-consistency" is a claim that has been measured and found untrue.

---

## 7. How to check this file

The acceptance clause it serves:

> Every one of Eve's 80 capabilities is either (a) expressible in PACT's schema,
> (b) a runtime concern the spec declares and delegates, or (c) listed in
> `50-NOT-COPIED.md` with a reason. No fourth category.

Mechanically. Every capability is a numbered row of
`research/notes/eve-capabilities.md`, which names the Eve file and symbol it was
read from and gives it one letter. Each letter then has a test of its own:

1. **(a)** — the capability corresponds to a field or a kind in `spec/schema.yaml`,
   and that field carries `help:`, `surface:` and `tier:`. Held by
   `authoring_surface.rs::every_field_in_the_specification_carries_help_and_surface_and_tier`,
   which walks every `groups.<g>.fields.<f>` and names the group and the field
   that is short; by
   `eve_inventory.rs::every_capability_in_the_inventory_carries_exactly_one_of_the_three_letters`,
   which refuses a row lettered both (a) and something else; and — the half that
   was missing — by
   `eve_inventory.rs::every_expressible_row_names_a_field_the_schema_actually_has`,
   which resolves the backticked `<group>.<field>` in the row's own cell against
   `spec/schema.yaml` and names the fields that group does have. Two rows pointed
   at `interceptor.on`; the schema's field is `interceptor.when`, and `on` has
   never existed. An (a) row pointing at a phantom field is the fourth category
   wearing a letter, and (a) carries half the inventory.
2. **(b)** — it appears in §4, and the schema says at the point of declaration
   that the host executes it. Held by
   `eve_inventory.rs::every_delegated_row_names_a_row_of_section_four`, which
   requires the row's cell to quote a row that is actually in §4 — row 46
   pointed at a §4 row about remote agents that has never existed, on the
   strength of `port.answers:`, which names a LOCAL agent handling what arrived
   because a port is entirely inbound. Also by
   `every_row_names_the_eve_file_and_the_symbol_it_was_read_from`, because a
   delegated concern is the easiest kind to keep claiming after the thing being
   delegated has moved, and
   `every_cited_eve_path_is_still_in_the_corpus_that_was_read` opens it wherever
   the corpus is on disk.
3. **(c)** — it is a row in §5 with a reason that is a constraint or a
   consequence, or an entry in §6 with the fixture that lets it back in. Held by
   `crates/pact-cli/tests/deliberate_refusals.rs` for the quality of the reason,
   and by
   `eve_inventory.rs::every_refused_row_points_at_a_refusal_that_is_actually_written_down`
   for its existence — a capability marked refused that points at a ledger row
   somebody renamed has become the fourth category while still looking counted.

And the count itself, because three green letters over the wrong number of rows
proves nothing:
`eve_inventory.rs::the_file_cannot_drift_from_the_summary_it_states_about_itself`
compares the rows against the totals the inventory states about itself, and
`the_rows_are_numbered_from_one_with_no_gaps` stops a deletion from leaving a
hole that nobody reading the prose would see.

Anything in none of the three is the fourth category, and finding one is a
finding, not a shrug. Add the row or add the field.

> **Correction.** Step 1 named a test that held only one third of it. For one
> round `authoring_surface.rs` checked `help:` alone, and only as a whole-file
> substring ratio — `helped * 100 >= typed * 90` — which cannot say *which* field
> is missing *what*, and nothing anywhere in the repo read `surface:` or `tier:`
> at all. The property happened to hold (173 fields, none short), but a property
> nothing checks is a property that will stop holding without anyone noticing,
> and each of the three is load-bearing somewhere different: `help:` is the only
> documentation D13's reader ever gets, `surface:` is what the governance zone
> and the blast-radius class in `20-ARCHITECTURE-DRAFT.md` §8.2 and §8.3 are
> looked up in, and `tier:` is what makes D14's no-code badge checkable.
> (Those two numbers are the architecture draft's, not this file's; this file
> now has sections of its own at those numbers, and an unqualified `§8.2` here
> would land on the wrong one.)

**A fifth check, because the schema can promise a product that does not exist.**
Help text is the only documentation D13's reader ever gets, so a command named in
it reads as a command that ships. Four were named and none existed — `pact init`,
`pact tools list`, `pact tools sync` and `pact show models --can-judge` — and the
last was worse than absent, because `show` ignores extra positionals and silently
printed the whole document as JSON. `tool.pinned` was the sharpest: the schema
forbade writing it by hand and named a tool to write it that has never been
written, so the field had no path at all.
`authoring_surface.rs::every_command_the_specification_promises_is_a_command_that_exists`
resolves every backticked `pact <verb>` in `spec/schema.yaml` against the
binary's own dispatch, and
`eve_inventory.rs::every_expressible_row_that_names_a_command_names_one_that_exists`
does the same for the inventory — which is what let rows 95 and 98 land as (a).

**A fourth mechanical check, added because a page can also lie about what the
product does.** Every claim this file makes about `pact check` behaviour is held
by a test that runs `pact check` on a broken copy of the worked example —
`authoring_surface.rs::a_reference_to_something_this_workspace_does_not_have_is_caught_where_the_author_is`
and the two beside it. §1.2 and §1.4 both described resolution that did not exist;
prose and product are now pinned to each other in the direction that decays.

---

## 8. The count `[R8]`

The acceptance clause is a number, so this section is a number. It used to be
the section that said which part of the clause this repository could check and
which part it could not, because the list being counted was somewhere else. The
list is now here.

**Where the number comes from.** `research/notes/eve-capabilities.md` is the
inventory: one numbered row per capability read out of Eve's tree — `packages/eve`,
`packages/eve-catalog`, `apps/`, `docs/` and `skills/` — each carrying the file
it was read from, the name inside that file, and exactly one letter. It replaces what this
section used to count, which was the plan's §1 table: the same inventory
*condensed* into eleven areas and 58 bullets, with the other 22 in an exploration
output that never reached this repository.

> **101 capabilities are enumerated and 101 are accounted for — 49 expressible,
> 22 declared and delegated, 30 refused or deferred, none outside.**

One row moved this round. **85** — prompt-cache markers — was (a), citing
`limits.reuse-context`; that field appeared exactly once in the whole repository,
in the schema itself, so the citation resolved to nothing an author could act on
and the field is deleted. Where a cache breakpoint goes is a fact about one
provider's wire format, so the row is (c) and its reason is **R46**.

| | Category | Rows | What holds it |
|---|---|---|---|
| **(a)** | An author writes it, in `spec/schema.yaml` | 49 | `authoring_surface.rs` — every field explains itself; `eve_inventory.rs::every_expressible_row_names_a_field_the_schema_actually_has` — the field it points at exists |
| **(b)** | Declared here, executed by the host (§4) | 22 | the schema comment at each point of declaration, and `eve_inventory.rs::every_delegated_row_names_a_row_of_section_four` |
| **(c)** | Refused (§5) or deferred (§6) | 30 | `deliberate_refusals.rs` — the reason is a constraint |
| | **Total** | **101** | `crates/pact-cli/tests/eve_inventory.rs` |

### 8.1 Why the count is 101 and not 80

The plan says 80. Re-reading the source gave 98, and the difference is
granularity rather than discovery — every extra row is a power the condensation
named in the plural.

* **Four areas the eleven-area table has no column for**: Eve's own evals system,
  the integration catalogue (`packages/eve-catalog`, 71 entries), the setup and
  scaffolding flow, and the mount points for Next, Nuxt and SvelteKit. Eight rows.
* **Bullets that are several powers under one name**: "`defineTool` + 12 framework
  tools" is one bullet and thirteen powers, and §1.1 above already splits the five
  privileged built-ins into their own table, so the inventory does the same.
  "Seven verifiers", "four sandbox backends", "eight platform channels" and
  "eleven versioned contracts" have the same shape. The other thirty-two rows.

Counting 98 and finding all 98 inside the three categories is a stronger result
than counting 80 and finding the same, so the higher number is kept rather than
merged back down. If a row is thought to be over-split, merging it changes the
total and changes nothing about the clause. What would change the clause is a row
that fits none of the three letters, and there is not one.

### 8.2 Per area, and where the refusals fall

| Area | rows | (a) | (b) | (c), and which row of §5 or §6 |
|---|---|---|---|---|
| Authoring | 9 | 6 | 0 | 3 — path-derived identity (R22); `lib/` modules and the compile step that runs them (R5) |
| Model | 9 | 6 | 0 | 3 — a model built as an object in code (R5); a fetched model catalogue (R15); a **guessed** context window (R25) — hand-recorded-with-a-source is exactly what shipped, so the refusal is the guess and not the hand |
| Tools | 16 | 5 | 0 | 11 — the twelve framework tools, in seven rows (R1), and the helper that switches one off (R2); model-authored fan-out code (R16); `toModelOutput` and read-before-write (§6, deferred) |
| Context | 7 | 6 | 1 | 0 |
| Delegation | 7 | 5 | 1 | 1 — a teammate on another deployment (§6, deferred) |
| Connections | 7 | 6 | 1 | 0 |
| Channels | 9 | 4 | 4 | 1 — one channel writing into another's session (R23) |
| Auth | 6 | 1 | 5 | 0 |
| Sandbox | 5 | 3 | 2 | 0 |
| Runtime | 11 | 2 | 6 | 3 — five separate kinds of pause (R12); extensions as installable packages (R17); prompt-cache markers placed for the provider that supports them (R46) |
| Evals | 4 | 2 | 0 | 2 — checks that can only be written as code (R18) |
| Developer experience, catalogue, templates | 11 | 3 | 2 | 6 — the typed client and the framework hooks, and the terminal app (R4); a verb that scaffolds a workspace (§6, deferred); capability sets as installable packages (§6, deferred); the model orchestrating subagents from JavaScript it wrote (R5, R42) |
| **Total** | **101** | **49** | **22** | **30** |

Five of the thirty are **deferred rather than refused** — `toModelOutput`,
read-before-write, a teammate on another deployment, and a verb that scaffolds a
workspace — and sit in §6 with the fixture that lets each back in. The other
twenty-four are ledger rows in §5.

**§5 has more rows than twenty-four, and the surplus is deliberate.** Some
ledger rows refuse something PACT was tempted by rather than something Eve
ships — R19, R21, R22, R24, and R30 through R39 are of that kind. They are
counted in no column of the table above, because the table counts *Eve's*
capabilities and these are not among them. They live in the same ledger because
the alternative is a second list with the same shape and half the readers, and
because a refusal PACT took on its own account decays into an accident just as
readily as one it took against prior art. R30 through R34 were all taken while
closing the gaps §7 of the architecture draft records at `[R9]`: each is a place
where the obvious repair had a wrong version that would have passed its own
test — letting a per-step budget stand in for a per-request one, dropping a photo
because the summariser cannot read it, binding a model that only answers off this
machine in a workspace that says nothing may leave it. R35 through R39 were taken the same way while closing
the gaps recorded at `[R12]`: a moment spelled correctly that nothing reaches, a
`shows:` name checked against a list PACT does not own, a token ceiling taken away
because there is no price list, a ceiling that measures a real zero reported as
one that works, and a screen telling somebody to answer under a name the wait will
refuse. Each of the five had a wrong version that would have passed its own test —
the sharpest being the last, where the wording was the author's and the contract
was correct and the two named different things.

**Four rows are split, and the split is named rather than rounded.** Each is
lettered for the half PACT answers with, and the same cell names the other half:

* *markdown-or-module* — the markdown half is (a); a slot written as a module is
  author code executed at build time (R5).
* *a model chosen per session, turn or step* — choosing by what the work needs is
  (a), through `needs:` and `variants:`; a switch decided by author code in the
  middle of a run is R5.
* *a sandbox network policy with brokered credentials* — the policy is (a),
  `allow-egress:`; handing the credential to the box is the host's, §4.
* *an integration catalogue* — naming one server is (a), `resource.endpoint:`;
  the list of servers a particular machine has is the host's, §4 and R20. It was
  lettered (a) against `pact tools list`, a command that does not exist.

### 8.3 A refusal that was withdrawn

**R29 is gone, and this is the row that says so.** It refused *"gating a whole
tool because a rule names one of its actions — or gating nothing because it
does"*, on the premise that *"no shipped transport carries which action a call
is"*. The premise went stale rather than being wrong when it was written:
`ir._takes` declares `action:` on every tool with an `actions:` block, so the
model is shown `one of read-ticket, reply`, picks one, and the call carries it —
which is already how `evals._calls` builds `<tool>/<action>` for
`must-call-before:`. One mechanism read the action off a call while the other
said it could not.

So the capability is provided, and by §0's rule a provided capability moves from
(c) to (a) and its row must go. `zendesk/reply` is enforced: it stops a reply and
lets the read-only `read-ticket` lookup through. What is still not guessed at is
narrower — a call that names NO action at all, against a rule that names one and
tests nothing else — and that is reported on `RunResult.unenforced` with a fix
that can be typed: write a rule for the other actions too, because once every
action of a tool has a rule, whichever one a silent call turns out to be, you
have written a rule about it (`Gate._whatever_action_this_is` is what makes that
promise true). The two fixes the old sentence offered are gone with it: writing
`zendesk` instead of `zendesk/reply` would gate the lookup nobody wrote a rule
about, and `pact check` refuses that spelling outright as
`loader/rule-names-no-action`, so it was a line that could not be typed.

A withdrawal is recorded rather than deleted for the same reason a refusal is
recorded at all. A row that quietly disappears is indistinguishable from one
nobody noticed, and the next reader would have no way to tell whether the
capability was provided or the refusal was forgotten.

### 8.5 Half of R24 is withdrawn, and this is the row that says so

**R24 refused an interceptor power a written rule cannot reach**, and named two:
`change-the-request` and `change-the-answer`. The reason was exact and is worth
restating, because it is the reason the withdrawal is now correct: no sentence in
the closed vocabulary rewrote — every one hides, stops, or sends the run
elsewhere — so declaring either got the rule refused by the next check down. *A
choice a non-coder can type and nothing can ever exercise reads as a capability*,
which is worse than an absent one. §6 recorded them as **host-only rather than
absent**, with the condition that would bring them back: *"a sentence somebody
actually wants"*.

That sentence exists now, and what made it writable is the `program` kind:

```
replace the answer with what house-style returns
replace what the model is told with what redact-clinical-terms returns
```

§6's own worry was the sharper half — that a mid-run rewrite *"is not reviewable
in a way `instructions:` and a stage's `says:` are"*. A carried program answers
that rather than dodging it. It is a file in the folder, fingerprinted since the
digest landed, declared with what it takes and what it answers with, and refused
unless it is `pure` — so what the rewrite does is as readable as the instructions
it sits beside, and the same twice.

So the powers are back on `interceptor.may:` and back in `AUTHORABLE`. By §0's
rule a provided capability moves from (c) to (a) — but only half of the row
moves: **the general refusal stands**. A power a written rule cannot reach is
still refused, and the list is still held to it; what changed is that two of them
can now be reached. The row is amended rather than deleted for the reason §8.3
gives about R29: a row that quietly disappears is indistinguishable from one
nobody noticed, and the next reader would have no way to tell whether the
capability was provided or the refusal forgotten.

What did NOT change: a rewriting rule must still declare its power under `may:`,
still name a program this workspace carries, and still be bound at a moment that
carries the thing it rewrites. A rewriter with nothing to run it leaves the words
exactly as they were and says so — half-applying would leave an author believing
their program had run.

### 8.4 What this section used to say, and why it changed

It used to end on an admission: 58 of 58 accounted for, and *"the remaining 22 of
the stated 80 are unverifiable here, because the inventory they were counted from
is not in the tree."* That was the honest statement available at the time and it
prescribed its own fix — land the inventory, and hold it with a test that checks
every row carries a letter and every refused row points at something that exists.

Both landed, and the test does four things rather than three, because the fourth
is where the drift was going to happen: it also checks that the inventory's rows
still agree with the totals the inventory states about itself. A summary nobody
recomputes is how 58 became a number quoted in two documents and derivable from
neither.
