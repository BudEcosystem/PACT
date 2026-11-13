# Changelog

What changed in PACT, newest first. Each entry says what an author can now write, or what now
holds that did not; the commits are listed under it for whoever wants the detail.

## 2026-11 — the TypeScript port computes effects as the checker does

`adapters/typescript/src/effects.ts` is `crates/pact-loader/src/effects.rs` (law 1) in TypeScript,
function for function: an action's effect from its own lines, a tool's as its worst action's, an
agent's as the worst of what it uses and its team's, a workflow's from its stages, and whether an
`effect:` word in a `when-this` holds. A runtime that gates calls by effect, or builds an agent in
code with no tree to `discover`, now has the checker's answer without the binary;
`test_both_ports_compute_one_effect.py` holds the port to `pact discover` on every agent of the
corpus. A tick is read with the five words `coerce.rs::yes_no` accepts; `workflows.rs::said_yes`
takes three, so `reads-only: y` is a lookup to the port and a write to the checker until that
reading follows `coerce.rs`.

## 2026-11 — a digest moves only when the tree does, and who answered a wait (13 November)

Bud Agent Flow asked whether "a new version of PACT never moves the digest of a tree nobody
edited" was a rule PACT held, with a check. It was true and nothing checked it. Three smaller
things were settled in the same exchange. Nothing here changes a field of the schema.

- **A tree's digests are pinned across versions of PACT.** `tests/conformance/digests.json` holds,
  for ten trees in this repository, the tree's `digest` and each workflow's `doc-digest` and
  `contract-digest` as `pact discover` prints them. A test compares. A change to PACT that moves
  one without the tree being edited fails, and has to change that file in the same commit and say
  here which trees move and why. A runtime that pins PACT holds the same file with one
  `pact discover` per tree. (Checked against binaries built on 18 October and 12 November: the
  trees unedited since then have the digests they had.)
- **On a stage that waits for people, `steps.<stage>.answered-by` is a list**, in the order they
  answered, also when one person did: a question can need several answers, and a binding's shape
  must not depend on how many people happened to answer. On a `decide` it stays one name. The
  reference runtime passed through whatever a host put there. Two new cases on a new workflow,
  `sign-off`: 28 workflow cases, 52 cases of replayed runs.
- **`loader/a-decision-asked-of-several`** (an error): a `decide` whose person rung asks a
  question that is `answered-by: everyone` or `enough-of-them`. A decision is one label from one
  person, and nothing says which label stands when several pick different ones. None of Bud Agent
  Flow's 184 trees writes it; it is refused before one does.
- **A stage that waits shows the person what the question says to show.** The reference showed
  them nothing: it read the stage's `bind:`, which a waiting stage cannot write, and not the
  question's `shows:`, which a `decide` asking the same question did read. Found by the first
  shared case with a waiting stage in it.
- Ruled, with no case yet: a workflow run a port ended (`if-still-running: stop`,
  `cancel-previous`) ends as `cancelled`. `stopped` stays "could not go on, and says why".

## 2026-11 — a served model is shown its own calls, and is told what a yes changed (13 November)

Running the limits cases on live models (gpt-4o-mini and gpt-5-nano) found three things about
PACT's own transport for a served model, and one more thing a model has to be told. Bud Agent Flow
measured the last on its engine, six wordings, ten runs each. Nothing here changes a field of the
schema.

### What a runtime must match

- **After a person says to keep going, the next request says so, once.** Last in its system text:
  the ceiling the run had reached and what it is now, which calls the model asked for were not
  made, and not to repeat a call that already has a result. No other request carries it. The
  wording is `Reached.raised` (`pact_adapters/limits.py`); a case records it as `after-a-yes` in
  `expect`, one text for each yes.
- Why the calls are named. Five calls asked for at once, a ceiling of two, then a yes, on
  gpt-5-nano: told nothing, or told only that the limit was raised (with or without how much was
  left, once or on every request), a model gave up and blamed the limit a person had just raised,
  or repeated calls it already had, in one or two runs of ten. Told which calls were not made, ten
  of ten made exactly those.
- One new case, `a-call-not-made-is-named-to-the-model-after-a-yes`: 11 limits cases, 50 shared
  cases of replayed runs in all.
- A call is written to a model in the form the model made it. In a case it is the tool's name, a
  space, and its arguments as JSON with sorted keys.

### What was wrong in PACT's transport for a served model

- **A model was not shown its own calls.** A turn that called tools was sent as `.`, and each
  result as a line of the user's (`[result of ledger] rent: entry found`). Asked for five lookups
  with three steps allowed, gpt-4o-mini made the same five in every step, fifteen in all, and ran
  out of steps. Sent `tool_calls` and `tool` messages, it makes five and answers. The conversation
  record now keeps what each call was given (`calls:` beside `tool_calls:`), through a tidying step
  and across the Pydantic AI message form, which used to drop it and say so.
- **A current model could not be reached at all.** gpt-5-nano answers 400 to `max_tokens` and to
  any temperature but its own, and every request carried both. The transport now reads the
  server's refusal and asks again: the same ceiling as `max_completion_tokens`, and no temperature
  when the one refused was the transport's own default. A `temperature:` the author wrote is never
  dropped.

### Still owed

- A closing answer that does not fit `answers-with:` (ruled, not built in the reference).
- Whether a workflow should be able to branch on "the agent this stage called ran out and
  answered with what it had". Today the stage ends `answered` and the overrun is recorded; there
  is no word a later stage can read.
- A shared case for claims.

## 2026-11 — what a run does when a limit runs out, as shared cases (13 November)

No shared case covered limits, so two runtimes could differ there unseen. Writing the first ten
and running them on a live model found five things PACT's own harness got wrong. Nothing here
changes a field of the schema.

### What a runtime must match

- **A ceiling is reached when the count is at the figure written**, and the first one reached is
  the one that acts; `halted` is its word (`tool-call-limit`, `step-limit`). With
  `tool-calls-at-most: 2` both calls run. A third asked for in the same reply as the second is not
  run.
- **`answer-with-what-it-has`** makes one closing request with no tools offered, and its text is
  the answer. The run reports the ceiling; it is not `final`.
- **The closing request says why.** Last in its system text: which ceiling was reached, which
  calls the model asked for were not made, and to answer from what it already has. The wording is
  `Reached.closing` (`pact_adapters/limits.py`), and a case records it as `closing` in `expect`.
- **`stop-and-say-so`** makes no further request and ends with a sentence naming the ceiling.
- **`ask-a-person`** parks. A yes grants the same budget again, of every ceiling, from where the
  run is; that budget can run out and ask again. A no ends the run (`out-of-budget`), and the run
  says which ceiling and that a person declined: *"Stopped before finishing: this run reached the
  limit you set with `tool-calls-at-most` (2 of 2 tool calls). A person was asked and said not to
  keep going."* The wording is one function, `Reached.declined` (`pact_adapters/limits.py`), so two
  runtimes do not each write it. A wait that ran out says nobody answered in time instead: that is
  not a person saying no, and the sentence does not say one did.
- **The ceiling named is the one that stopped the run.** A run can be at two together: with
  `steps-at-most: 2` and `tool-calls-at-most: 2`, a second step that asks for two calls runs one
  and is refused the other. It is then at two of two of each, and it was the calls that stopped it.
- **`people: ["nobody"]`** is new in a case: no answer is given and the time the question allows
  passes.
- Ten cases: `tests/conformance/limits.json`, on `tests/conformance/trees/metered-desk`.

### What was wrong in PACT's harness

- **"Keep going" did not let a run keep going.** A yes raised the step ceiling and no other, so a
  run that had reached `tool-calls-at-most` (or tokens, money, time) parked again at once with the
  same question. `Limits.kept_going` existed to grant all of them and was called by nothing in the
  harness.
- **A granted budget was lost at the next park.** It is now carried in the park
  (`Suspension.budget`, `budget` in its JSON), so a run told to keep going and then parked for an
  approval comes back under the ceilings it had been raised to.
- **The closing request was told less than any other**: the bare `instructions:`, without the
  agent's procedures, the shape of its answer, or what a reaction had reminded it of. It is now
  told what every request is told, less a stage's own line.
- **The closing request did not say a limit had been reached**, and a live model made the rest up.
  Asked for five lookups and allowed two, gpt-4o-mini answered the closing request with
  `[result of ledger] water: entry found`: a tool result it wrote itself, for a lookup never made,
  handed back as the run's answer. Five runs of five. Told what had happened, none of five, and it
  named the three lookups it had not got to. No scripted test could have found this.
- **A run a person refused more budget said nothing about why.** Its answer was the model's last
  words, which is an empty string when its last step was a call. Bud Agent Flow's engine named the
  ceiling and the refusal, and that is now the rule above. The park records which ceiling stopped
  the run (`Suspension.reached`), because working it out again afterwards can name another: a run
  at `steps-at-most` and `tool-calls-at-most` together was stopped by one of them.

### Still owed

- **A closing answer that does not fit `answers-with:`.** Ruled with Bud Agent Flow: it is asked
  for at most twice in all (`checks-at-most:`'s own default), no tool offered, and then the run
  stops naming the ceiling. PACT's harness cannot hold this yet: it never checks an agent's answer
  against its shape, so it makes one closing request and takes what comes.
- ~~The transport for a served model does not show the model its own calls.~~ Done in the entry
  above.
- A shared case for claims.

## 2026-11 — `pact about`: the binary says which commit it was built from (13 November)

A runtime pins PACT by commit and then runs whatever `pact` binary it finds. The binary could not
say what it was, so one built from an edited checkout, or left over from another commit, passed
every check a pin makes of the source beside it. Bud Agent Flow's pin guard asked for this.

- **`pact about`** prints three lines, each `<name>: <value>`: `version:`, `commit: <40 hex, or unknown>` and
  `uncommitted: no | yes | unknown` — whether anything the binary is built from (`crates`, `spec`,
  `models`, `Cargo.toml`, `Cargo.lock`) differed from that commit when it was built. Both are fixed
  at compile time (`crates/pact-cli/build.rs`). Built with no repository around it, both are
  `unknown`.
- A pin check compares `commit:` with its pin and refuses anything but `uncommitted: no`.

## 2026-11 — a decision as the specification says it: who is asked, what a model is shown, what is recorded (13 November)

Writing a shared case for a classifier found that PACT's reference runtime read neither
`if-unsure-below:` nor `if-it-disagrees: go-on`: a classifier one-tenth sure decided, and a second
opinion was never asked. Bud Agent Flow had built both, and its answers to five questions are how
the unwritten parts were settled. Nothing here changes a field of the schema.

### What a runtime must match

- **Rungs, and the label that stands.** A rung that decides makes its label the standing one. While
  a label stands a rung is not asked, unless it writes `if-it-disagrees: go-on`, which makes it a
  second opinion: the same label and it stands; another, or a second opinion that passes on itself,
  and nothing stands, so the rungs after it are tried as if nobody had decided. With nothing
  standing a `go-on` rung decides as any other. The decision is the label standing after the last
  rung asked (`workflow_runtime.decide`).
- **`if-unsure-below:`** passes the decision on when the classifier's `score` (a share of one,
  beside its label) is under the figure, or it gave none. Exactly at the figure decides.
- **Passing on is to the next rung**, never to the next model of the agent's `model:` list. That
  list is tried when a call fails (its own help: "never because an answer was wrong").
- **What a `decide` records**: `.label`; `.decided-by`, one of `rules`, `agent`, `person`;
  `.answered-by`, the agent's name on an agent rung and the person on a person rung — who that
  was is the host's to say, beside the answer, under `answered-by` (a name no question's answer can
  have a field called). The reference wrote `by` and `because`, names the specification does not
  have. A rule's `because:` is the run's
  "why this path" (`WorkflowResult.because`), not a field a binding reads.
- **What every stage has besides its answer**: `.outcome`, the word it ended in (`answered` for a
  `decide`); and on a `repeat`, `.rounds` and `.ended` — `passed` or `ran-out`, and absent where the
  repeat writes no `until:`. The reference had none of them, so `steps.<stage>.outcome` passed
  `pact check` and read nothing.
- **A workflow hands back what an `answer` stage bound**, and `{}` where it reached none. The
  reference handed back the last stage's own record, which is what a body hands the stage that
  holds it and nothing a workflow said it gives.
- **A classifier is not given the stage's `says:`.** An agent all of whose models are
  `kind: decision` is given its fields as they are; nothing is reported, since nothing was owed.
- **What a model is shown of what an agent was given** (`accepts:`, in its help): all of it and
  nothing else — the `message` as the words, every other field by name and value, in `accepts:`
  order. With no `message` nothing is put in front; in particular not the agent's `description:`.
  How the fields are laid out is each runtime's (`workflow_runtime.worded` is this one's).
- Twelve shared cases hold these, on `tests/conformance/trees/triaged-defects`: three for the
  threshold, five for the second opinion and the record, three for a loop's rounds, one for a
  workflow that reaches no `answer`.

### What `pact check` now says

- **`loader/a-rung-with-two-kinds-of-reader`** (a warning) — an agent on a rung lists a decision
  model and a language model in one `model:`. It reads as a cascade and is a fallback for a failed
  call; both would be given one message.
- **`loader/a-deciding-agent-given-nothing`** no longer counts a `says:` as something a classifier
  is given.

### What was wrong in what PACT ships

- PACT's own live suite sent a called agent its `message` and dropped every other field it was
  given. It now sends all of them (`worded`).

### Proposed, not built

- **Showing the person who breaks a tie what the two opinions were.** A person reached after a
  disagreement is shown the question's `shows:` and nothing about the disagreement, in both
  runtimes. A name for it (`steps.<stage>.opinions`) would be new vocabulary.

### Still owed

- A shared case for claims (`same-request-key:`, `claim-lasts:`); none of the 39 touches them.
- A packaged copy of `spec/schema.yaml` that an editable install leaves in `site-packages` can go
  stale; nothing in PACT reads it, and nothing checks it.
- The `pact` command cannot say which commit it was built from.

## 2026-11 — an agent that decides is given what it decides about (13 November)

Bud Agent Flow's full gate, run under the rule that a deciding agent is given only what it
`accepts:`, found six of its own workspaces where the agent on a `decide`'s rung was handed
nothing and a scripted agent answered regardless. Two of the six could not be fixed in PACT as
it stood: the agent had to judge what an earlier stage found, and a `decide` could not say so.

### What an author can now write

- **`bind:` on a stage that does `decide`**, and in the language `decide with kind:
  triage.kind, summary: triage.summary` — the word a `call` uses. It is what the agents on the
  stage's rungs are given besides the workflow's input and the current item, and the only way
  one of them is shown what an earlier stage found. No field is new: `bind:` was refused on a
  `decide` (`loader/a-line-this-stage-never-reads`) and is now read there.
- **`bind: {note: item}`** says where a one-value item goes, for an agent that does not call it
  `message`.

### What a runtime must match

- **What a deciding agent is given**, in this order, a later one winning: the workflow's input;
  the fields of the item it is inside a `for each` of (an item that is one value is its
  `message`); the stage's `bind:`. Of that, only what the agent `accepts:` — no `accepts:` is a
  `message` and nothing else. The stage's `says:` goes at the start of the `message`, a bound
  one included (`workflow_runtime.given_to`).
- **A name the stage binds is the binding's alone.** Where the binding reads nothing — an
  optional field the earlier stage left out — the agent is given nothing under that name. The
  workflow's input is not read for it instead, so a `kind` that the stage says comes from
  triage is never quietly the `kind` the request came in with.
- **Every agent rung of one `decide` is given the same subject**, each as much of it as it
  accepts. Written rules read their own bindings and a person is shown the question's
  `shows:`; neither reads `bind:`.
- **A one-value item an agent cannot take as `message` is reported** on `unenforced` only when
  the stage does not bind `item` to a name.
- Three shared cases hold these: `tests/conformance/workflows.json`, on the new tree
  `tests/conformance/trees/triaged-defects`.

### What `pact check` now refuses

- **`loader/a-deciding-agent-given-nothing`** — an agent on a `decide`'s rung requires an input
  nothing can ever give it, or accepts nothing that anything can. What can give it one: a field
  of the workflow's `accepts:`, a part of the item's shape, `message` for a one-value item or a
  stage that writes `says:`, and a `bind:` key. The message lists what is on offer. It says
  nothing where the list's shape cannot be known.
- **`loader/a-call-that-does-not-fit`** on a `decide`'s `bind:` — a name none of its agents
  accepts, or a value in a shape one of them does not take. Each value is read as any binding
  is (`loader/a-binding-to-nothing`, `-from-later`, `-to-a-stage-that-may-not-have-run`,
  `loader/an-item-outside-for-each`).
- **`loader/a-line-this-stage-never-reads`** — `bind:` on a `decide` with no agent rung.
- **`loader/hidden-from-the-ai-but-handed-to-it`** (a warning) now also covers a value a
  `decide` binds for its agent.

A workspace that loaded clean can now be refused: one whose deciding agent was never going to
be shown anything.

### What was wrong in what PACT ships

- **`tests/trees/workflows-48-invoices`**, the invoice inbox the workflow specification prints,
  was a seventh silent case. Its attachment sorter wrote no `accepts:`, so it took a `message`;
  an attachment has a `name` and a `file` and no `message`; it was asked to sort a file it was
  never given. It now accepts `name` and `file`.

### Still owed

- A value the workflow `hides:` from `the-ai` that reaches a deciding agent BY NAME (the input
  has a field the agent accepts) is not warned about; only one bound for it is.
- The reference runtime passes a `bind:` key written with a dot (`fills.first-name`) as that
  literal name, on a `call` and on a `decide` alike.

## 2026-11 — a case expects only what the specification fixes (12 November)

Bud Agent Flow's second replay: 21 of 24 agreed, and the three that did not were each a question
the cases had answered by accident.

### What a runtime must match

- **A run that stopped because its answer does not fit hands back an empty record.** PACT handed
  back the unfitting answer beside the word `stopped`, which a caller could still read fields
  off. Why it stopped is in `said` (`workflow_runtime.run_workflow`).
- **A field the run did not set is absent from its answer**, not `null`: `gives reply: text,
  optional` and a run that never set it answers `{}`.
- **The order agents are asked in across the items of an `each`** is the runtime's to choose
  unless the stage says `at-once-at-most: 1`, as the schema's help has always said. The shared
  case that expected an order now runs on a tree that writes it.

## 2026-11 — the shared cases, replayed by a second runtime: three things PACT had wrong (12 November)

Bud Agent Flow replayed `tests/conformance/` and sent the cases that differed before recording
any as its own. Three were PACT's.

### What a runtime must match

- **A workflow's answer is held to what it says it gives.** `run_workflow` handed back whatever
  the `answer` stage bound; it now reads each field of `answers-with:` by its shape and stops
  with *the answer does not fit `answers-with:` — …* when one does not (`halted: stopped`). A
  field left out is refused unless its shape says `, optional`.
- **Before anything has been remembered**, a `repeat`'s `remembers:` entry with no `starts-as:`
  is what its `combines-by:` makes of nothing: an empty list for a rule that keeps several
  (`keep-all`, `top 3 …`), and absent — so a `bind:` reading it is left out — for one that keeps
  one thing. It was `null` for every rule.
- **A workflow that hands back nothing answers with an empty record**, `{}`: `answers-with:` is
  a set of fields, and no fields is still a set.
- **An agent a workflow's stage calls is an agent's run**, under its own limits, approvals and
  the reactions that cover it (`docs/99` §5). The reference workflow runtime does not run agents
  — `Callers.agent` is the host's — and now says so.

### What was wrong in what PACT ships

- `examples/language/help-centre`'s `clear-inbox` said `gives replies: text, optional` and handed
  back a list. It says `list of text, optional`. `pact check` passed it: nothing holds an
  `answer` stage's `bind:` to the workflow's `answers-with:` at check time. Owed.
- The shared case on `examples/kernel/tree-search` scripted a scorer whose ideas had no `text`,
  which the workspace's own `idea` shape requires. Corrected, and the wrong data kept as a case
  of its own: *an-answer-that-does-not-fit-what-the-workflow-gives-stops-the-run*.
- The six routing cases ran on `help-centre`, whose desks are covered by a reaction, so a runtime
  that refuses an uncarried guard refused the whole workflow. They run on
  `tests/conformance/trees/routed-desk`: the same two workflows, agents no reaction covers.
  Their `expect` is unchanged to the letter.

## 2026-11 — how a call's key and a claim's number reach the server (12 November)

The schema's help for `same-request-key:` and `claim-lasts:` now says what was left to each host
to invent, and one gap in what a deciding agent is given is closed. Agreed with Bud Agent Flow, which already sent the first of these in
production.

### What a runtime must match

- **A call's own key** (`same-request-key: the-call`) is sent as the `Idempotency-Key` header on
  a `url:` tool, and as `dev.pact/request-key` in the request's `_meta` on a connected one.
- **A claim's fencing token** is sent as `Pact-Fence` with `Pact-Claim` (the scoped claim key) on
  a `url:` tool, and as `dev.pact/fence` with `dev.pact/claim` in `_meta` on a connected one:
  both or neither, only for a claim taken from a store, and never as an argument, which would
  change the call's own key. PACT's reference harness records the token (`Ledger.fences`) and
  sends neither; a host does.
- **An item that is one value is the deciding agent's `message`** (`rung.agent`'s help, and
  `workflow_runtime.given_to`). `for each item in input.notes` over a list of texts handed the
  sorter the stage's `says:` and nothing about the note. An agent that accepts no `message`
  cannot be given it, and the run says so on `unenforced`. Two shared cases hold it
  (`tests/conformance/trees/sorted-notes`): a loop over texts, and a loop over records where
  the sorter is given the fields it accepts and nothing else.
- **A claim is taken when the call is let through**, after a person has said yes and just before
  the tool is reached, and not while anybody is being asked. Before a person is asked the ledger
  only looks (`Ledger.look`).

## 2026-11 — held to a second runtime: what reviewing Bud Agent Flow against PACT found in PACT (12 November)

Bud Agent Flow was reviewed for conformance to `docs/99`, and asked its own questions back. Seven
of them had no answer in PACT, or the wrong one. Nothing here changes a field of the schema; one
help text now says what was unwritten.

### What a runtime must match

Behaviour another runtime can observe, with where PACT does it. This section is in every entry
from now on, because a runtime that pins PACT could not tell a change of behaviour from a
refactor without reading the diff.

- **A guess does not spend what is exact.** A reaction that is once-a-run fires once on a guess
  and once on something exact. A topic `noticed-by: [tags, the-agent]` raised by the agent
  saying so is advice; the tagged call that comes later is still held
  (`reactions.py` `_due`/`_spend`; saved state gains `sure`).
- **What a deciding agent is given** (`rung.agent`, now in the schema's help): the current
  item's fields over the workflow's input, as many as it `accepts:` and nothing it does not;
  the stage's `says:` at the start of its `message`; an agent with no `accepts:` takes a
  `message` only (`workflow_runtime.py` `given_to`). A `says:` that cannot be delivered is said
  on `WorkflowResult.unenforced`, which is new.
- **Which implementation does an interface's work** is the runtime's to decide by `chosen-by:`,
  and there is now one reading of it: `pact_adapters.interfaces.chosen(document, agent,
  run_inputs, picked_by_the_host)`. Nothing was read before; an agent that looked things up in
  an interface looked them up in nothing.
- **What a teammate could not do reaches the run that asked it.** Each line of a member's
  `unenforced` and `unmetered` is on the caller's own, worded `<member> (put to work by this
  agent): <its line>`, for a teammate, an agent consulted or told by a reaction, and across a
  park (`Suspension.from_members`). `delegate_by_running.ask` returned the member's words and
  nothing else. Bud Agent Flow was told its engine dropped these where PACT's did not; PACT's
  dropped them too, and the wording is Bud Agent Flow's.
- **An agent a reaction woke is not offered `working-on`.** It was run to be asked or told
  about one thing; what the work has turned to is the waking run's to say. What its own tagged
  calls raise is exact and still holds. Found live, once a woken agent's lines reached the run
  that woke it: the auditor, told of a refund, said `finance`.
- **A workspace's own `.pact/` area** is `<folder>/.pact/` for a folder and
  `<folder>/.pact/<name>/` for a workspace that is one file `<name>.pact`
  (`watches.area`). A lone `.pact` file used to lose its learning ledger without a word.

### What an author or a host can now do

- **A workspace written in the language brings its own model rows.**
  `resolve.load_catalogue(workspace=…)` reads a `.pact` workspace's `models` from the document,
  and `load_catalogue(document=…)` takes one a host has already loaded. It opened
  `models/catalog.yaml` from the disk only, so such a workspace's transcriber and speaker passed
  `pact check` and were unknown to everything that binds or prices a model.
- **`pact_adapters.checking.as_a_folder(root)`** is public: a COPY of a tree written in the
  language, rewritten as the folder it stands for, for a runtime that tries a change on a
  scratch copy.
- **`benchmarks.record`** on a workspace written in the language hands back the lines to add to
  its `models` block, where it used to write a file nothing reads.

### The shared cases

`tests/conformance/reactions.json` (13) and `workflows.json` (8): a scripted run written down —
the tree, who runs, what the model writes at each step, what each tool, agent, judge and person
answers — and everything another runtime can observe of it. PACT's own runtime is held to them
(`test_the_shared_cases_are_what_this_runtime_does.py`); another runtime replays the same cases.
`tests/conformance/trees/guarded-desk` is a workspace whose calls are stopped, held, counted and
reported by reactions on exact signals.

### Owed, and written down so it is not lost

A shipped loop the default step ceiling cannot finish (`pact:loop/reflexion` at 8 steps); a URL
as a run input (a host fetches it under `allow-egress:` and hands over a file — unwritten until
now); the words an answer shape is asked for in (`docs/99` §7); a warning for a shape named one
letter from a built-in kind; an edit that changes one field of a `.pact` file in place.

## 2026-11 — the language writes programs: figures, patterns, and workflows in the order they run (12 November)

`docs/99-THE-PACT-LANGUAGE.md` §4.3a. Nothing here is new to the specification: a `.pact` file
can now SAY, the way a program is written, what a folder of YAML already could.

### What an author can now write

- **A workflow's steps as statements, in the order they run.** In a `workflow` block:
  `plan = call planner with brief: input.brief`, `for each item in input.documents`,
  `repeat at most 4 times`, `together`, `decide` with an `if <label>` for each way it can go,
  `answer with result: make.result`, `stop watch.run`, `ask <question>`. The order of the lines
  is the wiring — `starts-at:` and each stage's `then: { answered: … }` are written for you —
  and the statements beneath an `if` come back together at whatever follows the `decide`.
- **A step's name is a variable.** `plan.findings` is `steps.plan.findings`. A path that starts
  with `input`, `item`, `remembers`, `values` or another word a binding starts with is left as
  written.
- **`takes` and `gives`** on a workflow (`accepts:`, `answers-with:`) and on a carried program
  (`takes:`, `answers-with:`).
- **How an agent thinks, the same way.** A `loop` block takes `think`, `use tools`,
  `check its work`, `run code` and `answer` as statements.
- **`let refund-limit = 200 USD`** — one entry of `values:`. `{use: refund-limit}` now stands
  for a figure inside a sentence too: `before billing/issue-refund, when amount is more than
  {use: refund-limit}: ask …`.
- **`based on desk with domain: billing, cap: 0.10 USD`** — `based-on:` and `with:` on one
  line, in any block.

### What now holds

- **`pact write` prints every workflow and loop this repository ships as statements**, and each
  is read back and compared before it is used, as every block is. Wiring no order of lines can
  say — a stage a statement cannot name — is written as the settings it is.
- **A name no step has is told where it was read.** The checker's own
  `loader/a-binding-to-nothing` points at `nobody.reply` on the statement's line.
- **`examples/language/help-centre`** is one workspace in four `.pact` files: figures, a
  pattern and two desks made from it, tools and an approval, two workflows with one calling
  the other, a reaction, an agent that listens, and `learning:`. Both workflows are RUN by
  `test_a_workflow_written_as_statements_runs.py`, through the reference workflow runtime.

### What was wrong, and is fixed

- **A learning cycle on a workspace written in the language checked the wrong tree.** A
  proposal is held to `pact check` by copying the tree and writing the new instructions where
  they live. In a `.pact` file they lived nowhere that code looked, so on a workspace that
  also carries files (a set of documents) nothing was written, the author's own tree was
  checked, and a change that breaks a rule passed. The copy is now rewritten as the folder it
  stands for first (`pact write`, then `pact build`), and a tree in which the instructions
  still cannot be found is refused as uncheckable instead of checked as it stands.

### What a runtime must match

- `working-on` is offered with `{"topic": "one of a, b"}` as its arguments, like every tool, and is
  no longer offered once every topic the agent can say has been said (`harness.py`,
  `Reactor.more_to_say`; `harness.ts` `saidTopics`). Saved reaction state gains `said`.
- A `decide` stage's agent and person are handed something (see the entry above for what);
  both were handed `{}`.
- A workflow's `starts-at:` and each `then: { answered: … }` are unchanged in the document: the
  statements are a way of writing them and nothing a runtime sees.

### What a real model found

The `.pact` examples were run against a live model for the first time
(`test_the_language_runs_on_a_live_model.py`, opt-in; `gpt-4o-mini`): the refund on
`finance-first`, a judge reading who is upset, a topic only the agent can notice, and both
`help-centre` workflows with real agents. Nine cases pass. Four things it found are fixed,
each with a test that needs no model:

- **A tool's arguments were never sent to a served model.** `OllamaTransport` sent
  `"properties": {}` for every tool. It sends the author's `takes:` now, `one of a, b` as a
  closed list, and takes an `api_key` for a server that wants one.
- **`working-on`'s arguments were a JSON schema**, which no transport reads; a provider was
  sent three arguments called `type`, `properties` and `required`.
- **`working-on` is not offered once every topic has been said**, on both ports. Told
  `noted: legal`, a model said it again until its steps ran out.
- **An agent or a person that decides is shown what it decides about.** The reference
  workflow runtime handed both `{}`: the agent now gets the workflow's input, as much as it
  `accepts:`, and the person the question's own `shows:`.

The older opt-in live test (`test_the_phase_1_fields_reach_a_live_model.py`, the Pydantic AI
path) was run too and passes; its one stale line expected no step ceiling, which law 2 gave
every run on 10 November.

One is written down and not fixed: an agent that `gives reply: text` ends its reply with the
line `- reply: text`, word for word (`docs/99` §7).

### What is not there

Expressions. A path is a path: no arithmetic, no reassignment, and the loop variable is always
`item`. Those are the document's rules (02W §2.0) and they are why a stage that reads
something that may not have run is refused before anything runs.

## 2026-11 — a set of documents names its embedder and its reranker to the runtime (12 November)

`knowledge.embedded-by:` and `reranked-by:` were checked (`pact check` holds each to a catalogue
row of kind `embedding` and `reranking`) and read by nothing: `KnowledgeSpec` dropped them, so a
runtime indexed every set with its own embedder whatever the set said. `KnowledgeSpec` now carries
`embedded_by` and `reranked_by`, `""` when not written. One test; README count 4766.

Not changed here: an agent that `uses:` a knowledge interface (`interface: yes`, 96 §B1) is still
given the interface's entry, not the set that `implements:` it.

## 2026-11 — the PACT language, and reactions (12 November)

Two things, specified in `docs/99-THE-PACT-LANGUAGE.md`. Neither changes anything a folder of
YAML already says.

### A workspace can be one file

A `.pact` file is a second way of writing a workspace: blocks at the left margin (`agent desk`,
`tool payments`, `workspace "Its name"`), and under each one settings (`key: value`, exactly as
in YAML), sentences (`uses zendesk, payments`, `asks finance-desk: …`, `at most 8 steps`) and
text blocks. `pact check team.pact` reads it directly, and every existing rule points at the
line of the `.pact` file.

- **`pact write [PATH]`** prints any workspace as one `.pact` file. **`pact build <file> --to
  <folder>`** writes the folder a file stands for, and reads it back before it says it is done.
- **A `.pact` file can sit at the top of a folder**, beside the things that are files by nature
  (a knowledge set's documents, a skill's scripts). Several are read as one; anything written in
  two places is refused.
- **The two ways of writing cannot drift.** For every workspace under `examples/`, reading what
  `pact write` printed gives back the document the folder gave
  (`every_shipped_workspace_reads_back_from_what_pact_write_prints`). The printer reads each
  block back as it writes it and falls back from a sentence to a setting where the sentence
  would not come back the same, so a field added to the schema later round-trips with no change
  here.
- `examples/language/` has three: the smallest workspace there is, `finance-first` (the same
  workspace as `examples/kernel/finance-first`), and `staff-desk` (a `.pact` file beside a
  knowledge set's documents).

### "When this happens, do that"

- **`topics:`** in a workspace, and **`topics: [finance]`** on a tool, an action or a set of
  documents. A topic's `noticed-by:` says how the runtime finds out the work has turned to it:
  `tags` (exact), `the-agent` (it is given a `working-on` tool and says so) or `a-judge`.
- **`events:`** — a named moment: `at:` one of six places in the loop, narrowed with `when-this:`
  and `more-than:`; or a `topic:`; or `judged: yes`.
- **`reactions:`** — `event:` (or the same fields inline) and `then:` a list of `remind:`,
  `consult:`, `tell:` and `stop:`. An agent lists the ones that cover it under `reactions:`, or
  the reaction says `applies-to: every-agent`. In the language: `when the work touches finance`
  with what to do indented under it.
- **`listens-for:`** on an agent — `{ topic: finance, how: asked-first }` or `{ event: …, how:
  told-after }`. Every other agent's work is what it hears; no other file changes.
- A `consult` before a tool call **holds the call**: the consulted agent's answer comes back in
  the call's place, and the model can make the call again. A held call is not put to a person
  for approval in the same step.

### What holds

- **A guess does not stop a run** (`loader/a-guess-cannot-stop`). `stop:` on a judgement, or on
  a topic the agent or a judge notices, is refused; a guess may `remind:` or `consult:`.
- **A reaction waits for one thing** (`loader/a-signal-says-one-thing`), names a call that is
  there (`loader/a-signal-names-no-such-call`), and narrows only a moment that is about a call
  (`loader/a-narrowing-with-nothing-to-narrow`). Five more rules are in `reactions.rs`.
- **A reaction does not wake itself.** While one is carried out it does not fire again beneath
  itself, so however agents consult each other, the consulting ends.
- **A consulted agent is paid from the run that woke it**, against the same `limits:`.
- What a run has already reacted to **survives a park** (`Suspension.reactions`).
- The TypeScript port offers the `working-on` tool and names every reaction it does not carry
  out on `unenforced`.
- **What an agent woken said is written down with the run.** Each entry of
  `RunResult.reactions` carries `heard:` — which agent, `asked-first` or `told-after`, and its
  words. `tell:`'s own help promised this and the record held only "told auditor".

### Where to read about it

- `README.md` has a section for each: the tutorial again as one file, and events and reactions.
- `site-docs/guide/first-agent-in-one-file.md` is the tutorial, step by step, with real output.
- `site-docs/reference/language.md` is every block, sentence, signal and `lang/` rule.
- `site-docs/reference/reactions.md` is every field of the five kinds, the six moments, what a
  held call does, and what a run reports.
- `crates/pact-lang/README.md` is for somebody changing the reader or the printer.
- `examples/language/README.md` and `examples/kernel/finance-first/README.md` walk the examples.

### What a runtime must match

- The six moments, and the order at a tool call: the workspace's own rules rewrite the arguments;
  a call a reaction will hold is not put to a person in that step; reactions due before the call
  are carried out in the order written and the first `stop:` ends the run; a `consult:` answers
  the call with `not done yet — <agent> was asked first about this, and said: …` and the tool is
  not run; then approval, at-most-once and the call; then reactions due after it
  (`harness.py`, `reactions.py`).
- A count (`more-than:`) is of calls that REACHED the moment — approved, and including ones a
  reaction then held — not of calls that ran.
- A reaction being carried out does not fire again beneath itself; an agent woken is paid from the
  waking run's remaining budget; what has fired survives a park.
- A runtime that cannot carry a reaction out says so on `unenforced`, one line for each; it may
  refuse to run the agent instead, and never runs it as though the reaction were not written.

### What an existing workspace will notice

Nothing, unless it has a setting called `topics`, `events`, `reactions` or `listens-for` under
an `x-` prefix it meant to keep. Three counts moved: 68 kinds (was 63), 569 keywords (was 536),
342 closed-choice words (was 333).

## 2026-11 — a catalogue row carries its voices, languages, sessions and dimensions (12 November)

`model-can.voices`, `languages`, `sessions` and `dimensions` were checked by `pact check` for a
`voice:` that names its models, and read by nothing else: `ModelEntry` dropped them, so a host
that binds a model the tree does not name had no row to hold it to, and `voice.plan_for` read
`sessions` from the raw rows beside the entry. Now:

- **`ModelEntry` carries the four lines** (`voices`, `languages`, `sessions`, `dimensions`), read
  where `regions` and `first_words_ms` are; a line the row leaves out is not said, never a guess.
- **`ModelEntry.fits_voice(plan, role)`** holds the model a host binds for a voice plan as the
  loader holds a named one (`crates/pact-loader/src/voice.rs`): the speaker must have the voice
  `speaks-as:` names, every model listening or speaking must handle each of `languages:` (`en`
  covers `en-GB`), and the one model of a plan that talks both at once must hold a duplex session.
- **`voice.plan_for` reads `sessions` off the entry**; `rows=` is still read beside it for a caller
  that builds entries by hand.
- **A benchmark's `with:` reaches DeepEval as DeepEval takes it.** `run_deepeval` passed `with:` as
  written, and a word where the benchmark's constructor takes a member of its enum
  (`MMLU(tasks=[MMLUTask.…])`) crashed inside DeepEval; each such word is now read into that
  member (`tasks: [high_school_computer_science]`), and one the enum lacks is refused naming some
  it has.
- **A DeepEval benchmark is answered by a model that obeys its prompt.** `AskModel.generate` read
  only JSON when a schema was asked for, and DeepEval's MMLU asks for a bare letter: every question
  raised `answer Field required`. A one-field schema now takes the reply itself, and a field of
  a few words (`Literal["A", "B", "C", "D"]`) the first of them the reply says. A package a
  benchmark imports only when it runs (`pandas`) is refused naming it, not raised. Measured
  through Bud Agent Flow's `budflow benchmark run`: gpt-4o-mini, 90 on twenty MMLU
  high-school computer science questions.

## 2026-11 — law 3 as the Bud Agent Flow corpus reads it (11 November)

Running the new checker over Bud Agent Flow's 168 shipped trees refused 29 of them, all with
`loader/repeated-with-no-claim` or `loader/a-key-that-changes-every-attempt`. Read one by one,
three of the rule's readings were wider than law 3, and each is narrowed here with a test:

- **A `together` is not repetition by itself.** Its branches are different stages, each run
  once: an email in one branch and a chat message in the other are two calls. What repeats is
  the *same* action called from two branches side by side, and that is still refused
  (`two_branches_calling_the_same_write_do_it_twice`). The old reading also replaced the
  context around a `together`, so a `together` inside a `repeat` lost the repeat; it now keeps
  it (`a_together_inside_a_repeat_still_runs_every_round`).
- **The stock memory tools are not held by the rule.** `bud/remember` and `bud/forget` in a
  `repeat` are how a round leaves what it learned for the next (Reflexion's buffer); the memory
  is the workspace's own (`a_round_may_keep_what_it_learned`).
- **A key bound from the round's own output is a warning.** The author wrote a claim, and a
  retry of one round produces the same output and so the same key. Whether two *different*
  rounds aim at the same thing is an intent the checker cannot see; a rolling plan whose every
  round posts a new update is the other reading, and the corpus has nine of them. A call with
  no claim at all inside a `repeat` or a retry is still an error.

The other trees were real defects (writes retried or repeated with no claim) and were fixed in
Bud Agent Flow by giving each action the key its business has.

## 2026-11 — the seven primitives, built (10 November)

`docs/97-PRIMITIVES.md` names seven building blocks (Shape, Origin, Store, Actor, Flow, Check,
Allowance) and eight laws, and shows that every PACT keyword and all 203 patterns at
agentic-patterns.com are made of them. Sixteen of the 76 kernel operations had no keyword and
none of the laws was a checker rule. `docs/98-PRIMITIVES-ENGINEERING-PLAN.md` is the plan that
closed both; its §9 says where the build differs from the plan.

### What an author can now write

- **`forks: yes`** on an `each`, `together`, `repeat` or loop stage: each item, branch or attempt
  starts from a copy, so three votes are three votes (`examples/kernel/self-consistency`,
  `tree-search`).
- **A board a team shares**: `shared-with: the-team` on a `remembers` entry, gated by
  `admitted-when:` and an `admitted-by:` agent that answers yes or no (`kernel/blackboard`).
- **A claim across a team, with a lease**: `same-request-key-across: the-team | the-workspace`
  and `claim-lasts:` on an action; the host supplies a `ClaimStore` (`kernel/work-queue`).
- **`keeps-taking: yes`** on an `each` (a growing work list), and **`does: stop`** with
  `stops: steps.<stage>.run` to cancel a run that was started without waiting.
- **`detectors:`** in a workspace, used as `looks-like:` in a condition and as "anything that
  looks like <name>" in redaction and interceptor sentences; **`gets-hidden-values: yes`** on an
  action, so hidden values travel as placeholders and come back only there
  (`kernel/private-by-placeholder`).
- **`effect:`**, **`in-share:`** and **`looks-like:`** in `when-this`; a person's yes is bound to
  the exact request they saw (`kernel/canary`).
- **`carries:`** on a tool and **`writes:`** on an action (`kernel/no-leak`);
  **`rests-after:`** with **`rests-for:`** on a tool (`kernel/circuit-breaker`).
- **`stream of <shape>`** as an answer shape; **`cost-per-request-from:`** a run input, never
  above `cost-per-request-under:`.
- **`limits.unbounded: yes`**, only on a path `owners:` lists with `owned-by:`. Pydantic AI's own loop
  is now handed the step ceiling too, eight when the author wrote none (law 2, option A).

### What now holds that did not

- **The eight laws as `pact check` rules**, among them `loader/three-things-that-make-a-leak`,
  `loader/repeated-with-no-claim`, `loader/a-helper-allowed-more-than-its-caller`,
  `loader/written-from-a-source-it-refuses` and `loader/unbounded-without-an-owner`. Each
  part's effect class is computed, never declared, and `pact discover` prints it.
- **A change a learning cycle proposes goes through `pact check`** before it is scored or
  applied (law 8, `checking.py`).
- **A reference workflow runtime** in Python (`workflow_runtime.py`) runs a workflow stage by
  stage, so the new stage lines have run-time meaning outside a framework.
- **The TypeScript port says** it neither forks a loop stage, lifts the step ceiling, nor keeps
  a team's shared board, on `RunResult.unenforced`; the board is still offered under the same
  name, so both ports show the model the same tools.
- **`scripts/pattern-coverage.py --ops`** reports no kernel operation without a keyword; fifteen
  workspaces under `examples/kernel/` are cited as the shipped form of 61 patterns.

### Changed for existing trees

- An agent run on Pydantic AI's own loop now stops at the default step ceiling where it used
  to receive none; on PACT's loop nothing changes. A tree that relied on running unmetered there needs an owner's
  `unbounded: yes`.

## 2026-10 — production on Pydantic AI (the Bud Agent Flow round)

Running PACT trees in production on Pydantic AI 2.54, through
[Bud Agent Flow](https://github.com/BudEcosystem/Bud-Agent-Flow), drove these changes. Every
addition is checked by `pact check` (Rust) and held by the Python harness, and the whole suite
runs offline: 4114 tests, 1445 Rust and 2669 adapter.

### A pinned model's settings, held to what it takes (1 November)

- **`model-can.ignores`, `ignores-while-thinking`, `thinks-unless-told`** on a catalogue row, read
  from the Pydantic AI code this repository pins and recorded for GPT-5.5, GPT-5.4, GPT-5.4 mini,
  Claude Opus 5 and Claude Sonnet 5. `pact check` refuses a `settings:` line the pinned model
  would throw away (`settings.rs`: `loader/a-setting-the-model-ignores`,
  `loader/a-setting-ignored-while-it-thinks`) — `temperature: 0.2` on GPT-5.5 with no
  `thinking: none`, `top-k:` on any OpenAI model, any sampling on Claude Opus 5. Bud Agent Flow's
  `choose-model` and its bind-time check hold candidates and bindings to the same reading
  (`ModelEntry.ignored_settings`).

### Choosing a model by evals: benchmarks, your own checks, cost (28 October)

- **`needs.accept-when:`** — the figures a model has to reach to be used for an agent, one
  comparison per line, all of which hold: `mmlu.score > 50`, `terminal-bench.score >= 40`,
  `refund-tone.score >= 0.8` (any metric of the suite by its new `name:`, a DeepEval G-Eval
  included), `pass-rate >= 90%`, `cost < 0.05 USD`, `input-price`, `output-price`,
  `context-window`, `first-words-within`. Each name has its own unit and is refused where it is
  written when it does not fit (`accept.rs`, ten rules); `spec/accept-when.yaml` holds the Rust
  checker and the Python resolver to one reading. Catalogue figures are held before anything runs
  (`ModelEntry.satisfies`), suite figures after the candidate runs its suite
  (`selection.held_after`; `CaseOutcome.scores` keeps every metric score).
- **Named benchmarks.** `models/catalog.yaml` declares `benchmarks:` — seventeen ship, eleven
  measured by DeepEval (`runs: deepeval:MMLU`) and six by their own harness (`runs:
  host:terminal-bench`) — each with its aliases and scale; a row's score under a name no
  benchmark has is refused. `benchmarks.record` writes a figure with its provenance, and copies the
  distribution's row first so recording a score never drops where a model is served.
- **In Bud Agent Flow:** `budflow choose-model --candidate URL#MODEL …` runs the suite on each
  candidate and chooses by `accept-when:` and `prefer:`; `budflow benchmark record|run` writes a
  figure; `budflow run` refuses a bound model whose catalogue figures miss a line.

### Modalities, interfaces, templates, turns and tool schemas from the server (27 October)

Designed in [`docs/96-MODALITIES-INTERFACES-TEMPLATES-TURNS.md`](docs/96-MODALITIES-INTERFACES-TEMPLATES-TURNS.md),
which also lists what is still pending at run time.

- **Voice, documents, video, embeddings.** Two answer shapes, `documents` and `video`. Six model
  kinds (`language`, `decision`, `embedding`, `transcription`, `speech`, `reranking`), held per
  line by a new `model-kind:` attribute (`loader/the-wrong-kind-of-model`). `agent.voice:` says how
  an agent listens and speaks — the pipeline, who may interrupt, the transcriber, the speaker and
  its voice, the languages, how long a pause ends a turn, whether the sound is kept — each line
  held against the catalogue (`voice.rs`). A transcriber and speaker on this machine now keep a
  caller's voice here behind a hosted language model, needing only `llm` in `allow-egress:`.
  `knowledge.embedded-by:` and `reranked-by:` name the models a set of documents is indexed and
  ordered with, which makes meaning-search writable on an air-gapped box for the first time.
- **`needs.scores:` can be satisfied.** A catalogue row may now record `benchmarks:` (it was
  refused, so every score requirement emptied the candidate set), and `speed:`.
  `needs.prefer: cheapest | fastest | best-on-the-evals` orders the models that pass.
- **Interfaces.** `interface: yes`, `implements:` and `chosen-by:` on tools, skills and sets of
  documents: one `email` contract, Gmail and Outlook as its implementations, picked per person by
  the host or per run by a run input. An implementation says only how it reaches its server
  (`calls:`, `passes:`), may ask more of a person and never less, and is written out longhand
  from its interface by the loader (`interfaces.rs`, fourteen rules). `tool.category:` labels a
  tool for finding.
- **Jinja.** `template-language: jinja` lets an agent's words choose and repeat, in the dialect
  Jinja2 and MiniJinja both render one way — no includes, macros or calls, the shared filters
  only, names written with `_` (`jinja.rs`; `holes.fill(language="jinja")` renders it sandboxed).
  Which texts are filled is now `template: yes` in the schema.
- **Turns.** `agent.turns:`, `variant.turns:` and `case.turns:`, from `system`, `developer`,
  `user`, `agent` and `tool`, with tool calls and attachments; standing instructions only at the
  start, every call answered (`turns.rs`).
- **Tool schemas from the server.** `pact-sync <server>` records what an MCP server offers into
  `resources/<server>.yaml` as `published:`; `tool.schemas-from: the-snapshot | the-server` sends
  the server's own arguments while which actions may be called, and what needs a person, stay
  written here. `pact check` holds `inspects:`, `same-request-key:`, `bind:` and `passes:` to the
  recorded arguments (`snapshots.rs`); `resource.if-it-changes:` says what a run does when the
  server changed, and a change an approval rests on always stops it
  (`mcp_bridge.when_it_changed`). `tool.unlisted-actions: each-call-asks-a-person` offers what the
  server adds behind a person.

### Tests over recorded runs (18 October)

- **A suite says which runs it is a score of.** `population: past-runs` with `from-the-last:`
  replays real runs with every write stubbed; `sampled-frame` with `sample:` and `reviewed-by:`
  puts a share of finished live runs in front of reviewers; `sliced-by:` breaks the score down by
  what each run was given; `runs-every:` re-runs the checks on a timer port's clock (02W §2.13).
  `pact check` refuses each line that would load and do nothing: a sample with no share or no
  reviewer (`schema/missing-companion`), a line only another population reads
  (`loader/a-line-this-suite-never-reads`), a slice no workflow held to the suite accepts
  (`loader/slices-by-what-no-run-is-given`), a schedule no clock can keep
  (`loader/every-is-not-a-time`). `populations.py` reads them, and says which runs a sample
  takes (by each run's own id, so every runtime samples the same runs) and each slice's verdict.
- **Two more rule shapes, wherever a rule is written.** `program:` names a carried `pure` program
  that passes or fails the answer with its reason (a program that is not pure is
  `loader/only-a-pure-program-grades`; one the workspace lacks is `schema/no-such-name`, WF-34's
  program half), and `library:` one of four ready-made checks (`library_checks.py`):
  `numbers-come-from-the-source`, `quotes-are-word-for-word`, `cites-its-sources` and
  `only-goes-up`, which hold an answer to what the run was given (`RunResult.given`, new) and what
  its calls returned. Both are decided before any judge. `tests/trees/workflows-48-invoices`
  checks its reader with `library: numbers-come-from-the-source`, as 02W §5.2 prints it.

### The rest of what Pydantic AI keeps in files, and built graphs, imported (18 October)

- **`pact-import --as mcp-json | pydantic-evals | agent-folder | skills`.** An `mcp.json` becomes
  one `resources/<server>.yaml` per server (a command, a credential or `${...}` in an address is
  `endpoint: host/<server>`; `args`, `env`, `cwd` and `headers` are named and never copied); a
  pydantic-evals dataset file becomes `evals/suite.yaml` and `evals/cases/`, each evaluator as
  the registry's new `evaluator.` door says and metadata a named loss (the package is never
  imported); a folder of harness agent definitions becomes `agents/`; a Skills directory
  becomes `skills/`. Each kind meets its reader in one place, `importing.read_files`, for
  `pact-import` and a host alike; a file is read by `importing.read_mapping`, whose refusal
  names the problem and its line, never the text there (an `mcp.json`'s lines hold tokens); a
  folder's hidden entries and links are named and never read.
- **Skills out as a directory.** `pact-pydantic-ai PATH AGENT --skills DIR` writes the agent's
  skills as a harness Skills directory, every PACT line kept in `SKILL.md`'s frontmatter and
  `references/`, `scripts/` and `assets/` copied, so importing it back gives the same skills.
- **A built pydantic-graph `Graph` read as a workflow** (`pydantic_graph_reading.workflow_of`),
  through public attributes and without running a step: steps as `call` stages on host actions
  to write, decisions as rules-rung `decide`s, maps and broadcasts as `each` and `together`, a
  branch back as `repeat`; `pydantic_graph_lowering.graph_of` goes the other way, and export
  then import gives the workflow's structure again. `pydantic-graph` is now a declared core
  dependency (Pydantic AI already brought it).
- `tests/parity/` holds the graph rows G1 to G9 (147 rows), and no row waits for an importer.

### A workflow's policy question held to its call (16 October)

- **`loader/shows-nothing-can-supply` reads a workflow's `policy:`.** A question a workflow's
  policy puts about a gated call shows that call's own arguments (`Question.about_call` keeps
  the names the call is given), and the check that says a `shows:` name is dropped in silence
  walked only agents' parks. So a question only a workflow's policy put could show
  `item.blast-radius`, a name no call carries, and load clean while the person approving was
  shown one value fewer than written. It is now held the same way, with the action's own names
  in the fix. Found by Bud Agent Flow's corpus case #103, whose incident commander was to read
  each containment's blast radius and rollback.

### An empty phrase, a decide's own question, and a negation in the field before (14 October)

- **`loader/an-empty-phrase`.** Every answer contains the empty phrase, so a rule with one
  (`must-not-contain: [""]`, or a hole filled with `""`) loaded clean and failed every answer:
  each checked answer was asked for again and every request went to the backup; under
  `must-contain:` or `must-say-one-of:` it held for every answer. `pact check` now refuses an
  empty or blank phrase wherever a rule is written, and says that `[]` checks nothing. Found by
  Bud Agent Flow's *Route to a specialist* template, whose `never-say` hole fills
  `must-not-contain:`.
- **A question a `decide`'s person rung asks is the workflow's.** Only a stage's, a limit's and
  a failure plan's `asks:` counted, so a workspace question only a rung asked was read as an
  agent's: it had to say `if-nobody-answers:`, and an `escalate` written there loaded and was
  never read, since a decide's silence stops the run. It is now a workflow's question, so the
  line is refused (`loader/an-agent-only-spelling`, which now says what a rung's silence does and
  that a reminder's `hands-over-to:` passes the question on first). A question nothing names
  (a tree begun from a template, before the `decide` that asks it is written) is held to neither
  reader's lines, since the one an agent would need is the one a workflow refuses:
  `loader/nothing-points-at-it`, which reads the same names, alone says it takes no effect. Any
  other question some line names keeps `if-nobody-answers:`: a gate reads it when a workflow's
  call is gated as when an agent's is, whether the gate is a policy's `ask-a-person` rule or a
  resource's `asks-to-connect:` or `asks-to-run:` reached through a tool only a workflow calls.
  Found by Bud Agent Flow's *Sort and route an inbox* template.
- **A negator in the field before is that field's** (`evals._stated_at`). The window looked back
  across a line break or a quote, so a reply field ending *"... we can't"* negated the
  `path: simple` written after it, and a correct answer graded FAIL (*Route to a specialist*,
  recorded live). The window now stops where the value's own field begins: a string closed by
  `,` `:` `}` or `]`, or a line that starts `<key>:`. A lone quote or line break is no boundary,
  so *not "approved"* is still a refusal, and a negator ends at any space, a line break too.
- Tests: 7 Rust (`a_question_a_decide_asks_is_the_workflows.rs` (5),
  `an_empty_phrase_is_refused.rs` (2)), 2 adapter (the field-before cases in
  `test_a_negation_is_a_word_not_part_of_one.py`), each failing without its change.

### A route back, a field a stage word hides, and a negation inside a word (14 October)

- **`loader/a-route-back-to-an-earlier-stage`.** A workflow's stage runs once a run and keeps
  what it did under its name, so a line that led back to a stage the run had already been
  through (a declined diff sent back to its dry run) loaded, and the second visit was answered
  with the first visit's answer: the run went round the same stages for ever. `pact check` now
  refuses such a line where it is written, in one `steps:` or any inside it, and says to put the
  stages that run again inside a `repeat`. Found by Bud Agent Flow's corpus case #94.
- **`loader/an-answer-field-a-stage-word-hides`.** `steps.<stage>.outcome` (and `.label`,
  `.decided-by`, `.answered-by`, `.ended`, `.rounds`, `.run`) reads what every stage has besides
  its answer, so a callee whose answer has a field of one of those names could never have it
  read: the binding loaded and read the stage's own word. It is refused where it is read, with
  the fix to rename the field. Found by Bud Agent Flow's corpus case #102 (a sub-workflow
  answering `decided-by`), and it caught pattern AP15's workflow reading its agent's `outcome`.
- **A negation is a word, not part of one** (`evals._stated_at`). The negators were matched as
  plain substrings, so the `no ` at the end of *Merino* negated the expected value written after
  it and a correct answer graded FAIL (Bud Agent Flow's corpus case #76). Each now begins at a
  word's start (`n't` still ends one).
- Tests: 4 Rust (`a_route_back_to_an_earlier_stage_is_refused.rs`,
  `an_answer_field_a_stage_word_hides_is_refused.rs`), 2 adapter
  (`test_a_negation_is_a_word_not_part_of_one.py`), each failing without its change.

### A stage named `done` (13 October)

- **`loader/a-stage-named-done`.** `done` is where a route ends: a `then:` line or a label that
  says `done` ends the run, the item, the round or the branch there. A stage of that name was
  accepted and could never be reached (a run compiled from it ended where the stage was meant to
  run); `pact check` now refuses it where its name is written, and says to give it another.
  Found by Bud Agent Flow's corpus kit, whose test tree named its answer stage `done`.
- Tests: 2 Rust (`crates/pact-cli/tests/a_stage_named_done_is_refused.rs`), failing without the
  rule.

### An agent somewhere else, reached over A2A (13 October)

- **`resource-kind: a2a-agent`** (N1). A remote agent that speaks A2A is a resource like an MCP
  server, with no field of its own: `endpoint:` where it is (held to `allow-egress: [tools]` when
  it is off this machine), `auth:` where its credential is kept, `asks-to-connect:` the question
  answered before it is first asked anything, and `tool-snapshot-digest:` (with its date and
  maximum age) what its card said when somebody read it. A tool reaches it with `connect:`, and
  that tool's `actions:` are the skills of the card the model may ask, each by the skill's id.
- **Two shapes of such a tool are refused.** One that asks it for no skill
  (`loader/a-remote-agent-asked-for-no-skill`), and an action that says `answers-with:`
  (`loader/a-remote-agent-answers-in-words`): what comes back is words a remote agent wrote,
  fenced off as text nobody here reviewed, never values a run acts on.
- **`pact_adapters.a2a_bridge`**: `card_digest` (canonical JSON of the card as served, its
  signatures aside: what `tool-snapshot-digest:` pins), `check_card` (a skill the tree asks for
  that the card does not list, a card that is not the one pinned, a review past its maximum age),
  and `reply` (the reply fenced as `mcp_bridge.quarantined` fences a server's prose).
  `mcp_bridge.check_pin` is the one reader of the three `tool-snapshot-*` lines for both, and
  `quarantined(what=)` says whose words they are. `mcp_toolset_for` defers such a resource's tools
  with a reason naming the A2A client's two calls, rather than as a kind it does not know.

### Where a model is served: `served-by.region` (12 October)

- **`served-by.region`** on a catalogue row's `served-by:` entry names the region that runtime
  serves the model in, as the runtime names it (`us-baa-region`). A workflow's `data-stays-in:`
  names a region and a model not served there is refused, and until now no line could say where
  a model is served. The resolver reads it as `ModelEntry.regions`, each region with the endpoint of
  the entry that names it, so a call is held to the runtime the host binds; a row that names no
  region is served in none, never in every one.

### How much of a limit is used, read in a decide's rules (12 October)

- **`used.<ceiling>` in a `decide`'s rules.** 02W §2.0 reads `used.<ceiling>` (how much of a
  limit is used, as a percent) in `when-this` lines, and a decide's rules are `when-this` lines,
  yet the loader read it only in a `repeat`'s `until:` and refused it in a rule
  (`loader/a-binding-to-nothing`, "is read only in a condition"). It is now read in every
  condition and still refused anywhere else (a `bind:`, an `over:`, a `call:`).
- **A share of a limit nobody writes is refused.** `used.<ceiling>` reads how much of a pot is
  spent, so its ceiling is one a pot keeps (`cost-per-request-under`, `tokens-at-most`,
  `tool-calls-at-most`) written in a `limits:` group around the stage that reads it: its own, a
  stage it is inside, or the workflow's. Any other was read as nothing, and a rule over it never
  fired; it is now `loader/a-share-of-no-limit-around-it`, with the line to write.

### An OpenAPI description imported as reviewed tool files; blanks in an address (12 October)

- **`pact-import --as openapi FILE [--out DIR]`** (decision P10). Each operation of an OpenAPI 3
  description becomes `tools/<operation-id>.yaml`: a `url:` tool whose address is the API's name
  (bound by the host to the API's address and its credentials) and the path, one action named for
  its `method:`, `takes:` from the path and query parameters or the JSON body's parts in PACT's
  shape words, and `answers-with:` from the success answer when PACT can say all of it. An object
  is a named shape, added to `workspace.yaml`'s `shapes:`. Nothing is guessed about an effect: an
  operation that does not declare it (`x-pact-reads-only: true` or `false`) gets no `reads-only:`
  and a *Needs a look* line, so it stays a write that cannot be undone until a person decides. The
  security schemes are named in a comment, never written as a value. The `ImportReport` accounts
  for every key read, down to each schema keyword: what PACT cannot say (a `oneOf` of several
  shapes, a free-form object, a shape that contains itself) is named and left out, never
  flattened. Held on ten public descriptions under `tests/trees/openapi/`, each with its licence
  recorded: every written file passes `pact check`. A list in the address is written as the
  server reads it: `list of ...` when OpenAPI's default spelling holds (one pair per item in the
  query), `text` with what joins the items when the server reads one value (`explode: false`),
  and any other spelling (`deepObject`, `matrix`, ...) reported and listed to write by hand.
  `adapters/python/tests/test_an_openapi_description_imports_as_reviewed_tool_files.py`.
- **A blank in an address is an argument.** `url: host/pets/{pet-id}?tag={tag}` fills each
  `{name}` from the call's argument of that name, in the path or in a query (where it is left out
  when the call has none); a blank that no `takes:` or `bind:` line of the tool's actions fills is
  refused (`loader/a-blank-in-the-address-nothing-fills`). `method:`'s help now says where the
  other arguments go: the query for `get` and `delete`, one JSON body for `post`, `put` and
  `patch`. `crates/pact-cli/tests/an_address_leaves_blanks_only_for_arguments.rs`.

### Deciding by models and people; money on a workflow's paths; one pot per run (12 October)

- **A decide may ask an agent, then a person** (02W §2.5). A rung of `by:` writes exactly one of
  `rules:`, `agent:` (an agent whose `answers-with:` has one `one of` line naming the stage's
  labels, and may add `not-sure`, which passes the decision on) and `asks:` (the person rung, a
  question whose answer has a `one of` line naming the labels; always last). `if-unsure-below:`
  is a decision model's score under which it passes the decision on; `if-it-disagrees: go-on`
  passes it on when this rung picks another label than the rung before. Refused: a rung with
  none or two ways (`loader/one-rung-one-way`), a person rung that is not last or a first rung
  that disagrees with nobody (`loader/a-rung-out-of-order`), an agent or question whose labels
  differ (`loader/a-label-with-nowhere-to-go`, WF-15), a last agent rung that may pass the
  decision on, by `not-sure`, `if-unsure-below:` or `if-it-disagrees: go-on`
  (`loader/a-decide-that-can-run-out-of-rungs`, WF-16), and `if-unsure-below:` on an
  agent with no decision model (`loader/sure-only-a-decision-model-can-be`, WF-17). Read in
  Python by `conditions.Rung`. `crates/pact-cli/tests/a_decide_cannot_run_out_of_rungs.rs`.
- **A decision model is a catalogue row with `kind: decision`** (02W §2.12): a trained
  classifier that answers a label and a score. An agent on decision models only needs no
  `instructions:`, and `pact discover` lists it as runnable. `resolve.ModelEntry.kind`.
  `tests/trees/workflows-48-invoices` now sorts its attachments as 02W §5.2 prints it.
- **Money moves only past a person or a written rule, on a workflow's paths too** (WF-23
  extended, WF-24, F1). A stage calling a `spends-money` action nobody guards is told about
  (`loader/money-moves-with-nobody-asked`) when a path reaches it with no wait a person answers
  and no decide by written rules or a person on the way: a warning on a path from the start, as
  on an agent, and refused on a path from a decide an agent may choose for. A write that cannot be
  undone on a path an agent may pick is refused (`loader/a-model-chose-what-cannot-be-undone`, in
  place of the note `loader/cannot-be-undone-and-nobody-asked` on that call). A call to a workflow is judged by that
  workflow's own checks. `crates/pact-cli/tests/money_moves_only_past_a_person_or_a_written_rule.rs`.
- **A run has one money pot** (WF-31, R32). `cost-per-request-under:` on a stage is its share of
  the run's figure; a share with no pot, or shares adding up to more than their pot, is
  `loader/a-share-of-no-pot`. `limits.counted-per:` (`run`, `connection`, `team`, or in a
  workflow a binding) and `limits.resets-every:` say what a ceiling is counted across and when it
  starts again (`loader/counted-across-nothing`); the Python harness counts one run and says a
  wider count on `RunResult.unmetered` (`Limits.across_runs`).
  `crates/pact-cli/tests/a_run_has_one_money_pot.rs`.
- **One table of answer shapes.** Each shape's spellings, words, example and JSON Schema
  fragment are one row of `questions._KINDS`, read through `Shape.json_schema`;
  `pydantic_ai_interop._SHAPE_SCHEMAS`, the second copy, is gone.
  `adapters/python/tests/test_one_shape_table_and_the_rungs_are_read.py`.

### A tree is the same wherever it is checked out; a wait hears its own events (12 October)

- **An empty folder contributes nothing.** A folder with no file in it, at any depth, is no part
  of the document: not a field, not a note. Git cannot carry an empty folder, so a `questions/`
  left empty read as `questions: {}` here and as nothing in a checkout of the same commit, and the
  two digests differed, so a journal recorded under one would not replay under the other.
  `crates/pact-cli/tests/an_empty_folder_contributes_nothing.rs`.
- **A wait hears only its own events** (`question.only-when:`, N193). In a question a workflow
  asks of a port, `only-when:` lines in the one condition grammar say which events the wait hears:
  each looks at what the event brought, `value: event.<field>`, and compares it with a figure or a
  value the wait can read (`is: {value: item.custodian-id}`), so the waits of an `each` that all
  listen at one port each hear their own item's; an event a wait does not hear is kept for the
  next. Refused: `only-when:` on a question asked of no port (`loader/a-line-this-stage-never-reads`),
  a line that looks at anything but the event (`loader/compared-in-the-wrong-shape`), a field
  that nothing arriving at its ports has (`loader/a-binding-to-nothing`, with the fields that
  do), and a comparison in another shape than the field's. `Question.only_when` and
  `Question.hears` read it in Python. `crates/pact-cli/tests/a_wait_hears_only_its_own_events.rs`,
  `adapters/python/tests/test_a_wait_hears_only_its_own_events.py`.
- **A circle through an agent has its caret on the agent's `uses:` entry** the fix names, for a
  circle of any length, and says each hop after a `uses` as `, which calls`
  (`loader/a-workflow-its-own-agent-starts`).

### Workflows: failure plans, undo, silence, and the five worked trees (9 October)

- **What happens after a failure is one record** (02W §2.7, F2). A workflow stage writes
  `if-it-fails:` with `after-that:` (`use-a-backup`, `carry-on`, `ask-a-person`,
  `wait-for-a-new-version`, `undo`, `stop-and-say-so`) and the line each choice needs:
  `backup:` (called with the stage's own `bind:`, held to the backup exactly as a `call:` is:
  an input left empty, one it does not take, or one of another shape is
  `loader/a-call-that-does-not-fit`), `carry-on-with:` (fields the stage answers with, else
  `loader/a-binding-to-nothing`; each value a binding read like any other, in the shape of
  the field it stands in for), `asks:` (the workflow's question, wherever it is written), `new-version-of:`, `undo:` and `undo-where:` (only
  when `undo:` names an `each`). `gives-up-after:` is a moment. A stage's `when-it-runs-out:`
  of `use-a-backup`, `wait-for-a-new-version` or `undo` takes its companion from the same
  record (`schema/missing-companion`), and a workflow's own ceiling cannot use a backup or a
  version. An agent's loop may not write it.
- **A write says how it is undone** (02W §2.12). `action.undone-by:` (a `<tool>/<action>` or a
  workflow: then the action is *Changes*) and `action.status-check:` (a read asked before a
  retry). An undo — an action's, a stage's or a workflow's — that only reads, or takes an input
  the write's inputs and answer cannot fill by name and shape, is
  `loader/an-undo-that-does-not-fit` (WF-26); a status check that writes, or that the call's
  own inputs cannot fill, is `loader/a-status-check-that-does-not-fit`. A workflow stage
  calling a write with no undo and no *Ask before* gets the note
  `loader/cannot-be-undone-and-nobody-asked` (WF-25).
- **Silence never approves, by structure** (02W §3 WF-20, WAIT-4, R13, R50). The
  `nobody-answered` exit of a wait a person answers may not reach, before another wait a person
  answers, a stage whose call needs a person's yes (`needs-a-person:` or a rule in the
  workflow's policy), or a stage making a write (the same `<tool>/<action>`, agent or
  workflow) the wait's `answered` exit makes (`loader/silence-reaches-a-gated-step`, with a
  quiet place to send it instead). A wait only the clock or events answer has no gate, and
  silence walks on through every exit of it.
- **An `answer` is held to what its workflow answers with**: its `bind:` (in the workflow's
  own `steps:`) names only fields of `answers-with:`, fills every required one, each in its
  shape (`loader/a-call-that-does-not-fit`). A `values.<name>` binding is read in the
  value's `shape:`.
- **`pact waits` lists every workflow wait**: besides each `ask-someone` stage, each park a
  failure plan or a ceiling asks (`if-it-fails.asks:`, a stage's or the workflow's
  `limits.asks:`), whose silence stops the run and says so; a park on the workflow's own
  ceiling names no stage.
- **A judged check has a judge** (WF-34): a workflow's `judged:` check with no `graded-by:` on
  the checks it names is `loader/a-check-nothing-can-run`.
- **The five worked trees of 02W §5 load clean** — `tests/trees/workflows-16-trial-booking`
  (was `a-trial-booking-case`), `workflows-48-invoices`, `workflows-69-reflexion`,
  `workflows-79-supervisor`, `workflows-60-interconnection` — with the agents, tools, programs
  and values they name. Fixed on the way: an `answer` stage hands back its `bind:` (it was
  refused as a call-only line); a port's `same-conversation-when:` may name a part of a named
  shape (`invoice.vendor-tax-id`); a repeat's `comes-from:` may name a stage some rounds skip
  (such a round adds nothing); and the trees write retention in days and `one of` choices
  in block maps.
- Conformance tests `every_example_loads_clean`, `silence_never_approves` (a mutation sweep of
  every `nobody-answered` against a separate reading of the tree, and the first diagnostic
  02W §3 prints), `a_failed_item_is_kept_not_dropped` and `undo_reverses_exactly_what_succeeded`
  (loader halves), `a_judged_check_has_a_judge`. Python: `moments.FailurePlan` on
  `ir.StageSpec.if_it_fails`. 56 kinds.

### Workflows: waits, questions, reminders, time, ports and value tables (9 October)

- **A wait is still a question, and the clock and events answer it** (02W §2.8, R12 reopened).
  In a question a workflow asks, `asked-of:` may name `the-clock` (a time-only wait whose time
  is `answer-within:` and whose one exit is `nobody-answered`) or a port (an event); `says:` and
  `answer:` are required only where a person or a group is asked
  (`loader/a-question-with-nothing-to-say`, WF-22). `answer-within:` is a `moment`. New lines:
  `answered-by:`/`enough-is:`, `asked-in:` (only for a channel — written `"#name"` —,
  `the-requester` or an outside contact: `loader/asked-in-for-someone-who-chooses`, WF-36),
  `urgency:`, `not-the-same-as:`, `needs-signature:`, `starts-with:`, `ordered-by:`,
  `counts-events-from:` and `reminds-at:` of the new `reminder` group (`at:` and exactly one of
  `nudges`, `tells`, `hands-over-to`, `runs`). `question-rule.first-times:`.
  `loader/nobody-can-answer` (WF-21) also covers a question a workflow asks naming nobody, the
  clock with no time, a question only the clock or events answer that asks for an answer, and a
  reminder or milestone with none or two actions. A question a workflow asks has no
  `if-nobody-answers:` (`loader/an-agent-only-spelling`, WF-40, with `when-it-runs-out:
  answer-with-what-it-has`); one no workflow asks still must. What only a workflow reads,
  written where an agent reads it — the clock or a port as an answerer, a moment as a deadline,
  a workflow's `when-it-runs-out:` choice, `join` on an agent's port — is
  `loader/a-workflow-only-spelling`.
- **Ports answer workflows** (02W §2.9, R23 and R44 reopened). `answers:` names an agent or a
  workflow; new `accepts:`, `bind:`, `only-when:` (read by the one condition reader),
  `signed-with:`, `in-time-zone:`, `if-missed:`, `per-row-of:` (timer lines, refused off a
  timer), `answer-within:`, `counts-as-the-same-for:`, `ordered-by:`, `undo:`, `then-run:`.
  `if-still-running:` has six choices on every kind of port and lost its "only a timer"
  refusal. New rules: `loader/an-event-the-wait-will-never-hear` (WF-19),
  `loader/a-key-that-is-not-a-field` (WF-27), `loader/overlap-with-no-key` (WF-28), the note
  `loader/a-port-that-cannot-start-a-run` (WF-29).
- **Time** (02W §2.10): `limits.finishes-within:` is a `moment`; `starts-from:`,
  `paused-during:` (`loader/a-pause-for-something-that-does-not-wait`, WF-32), `milestones:`,
  `at-once-at-most:`, and five workflow choices for `when-it-runs-out:` (`use-a-backup`,
  `carry-on`, `wait-for-a-new-version`, `undo`, `wait-its-turn`). A moment read from a date or
  counted in business days, or a workflow's timer at a time of day, with no zone on the line or
  the workspace is `loader/a-time-with-no-zone` (WF-30).
- **Value tables** (02W §2.12): `value.shape: table` with `rows-are:` a named shape; every row
  is held to it, and `workspace.calendar:` and `per-row-of:` name tables
  (`loader/a-table-that-is-not-one`; a calendar's rows have a `date` part). A value a run reads
  by name (the calendar, `per-row-of:`, a `values.<name>` binding, now held to the values there
  are) stays in the document under `values:`; every other figure is put in place and removed as
  before.
- **`pact waits` lists every workflow wait** with `waiting-for-a-person`, `waiting-for-a-time` or
  `waiting-for-an-event`, its stage, where silence goes and a deadline written as a moment.
- Python: `pact_adapters.moments` (`Moment`, typed, with `Reminder` and `RegionLimits`),
  `ir.PortSpec`'s new lines, `ir.values_of`/`ValueSpec`, `Question`'s new lines and
  `Question.asked_by` (a workflow's own question first), `Rule.first_times`, and the three
  reasons in `suspension.REASONS`. Fixture `tests/trees/a-trial-booking-case` (#16); conformance
  tests `the_clock_is_somebody_who_answers`, `an_event_finds_only_its_own_run`,
  `overlap_is_said_once_per_port`, `a_question_appears_where_its_answerer_chose` and
  `a_table_is_rows_in_one_shape`. 55 kinds.

### Workflows: one condition grammar, decide by rules, combine rules (9 October)

- **One condition grammar, read by one function on each side** (02W §2.6, F1 reopened).
  `when-this` gains `value:` (a binding), `less-than:`, `contains-any-of:` and `is-empty:`, so
  there are six condition words, and `tool:` is no longer required. The right-hand side is a
  `comparand`: a figure written as the value is declared (`5000 USD`, `85%`, `0.85`,
  `2026-10-09`, `enterprise`) or exactly one of `{value: <binding>}`, `{now-plus: 14 days}`,
  `{now-minus: 30 days}` (`schema/not-a-comparand`). An approval rule's `when:`, a routing rule's
  `when:` and a repeat's `until:` are held by `crates/pact-loader/src/conditions.rs`, which
  tells the same mistake in the same words in every position: `loader/compared-in-the-wrong-shape`
  (WF-18, extended) now refuses a value compared with a figure of another shape wherever the
  shape is declared (a score against money, a date against a number, money against
  `now-plus:`), a line that looks at both `tool:` and `value:` or at neither, `tool:` outside an
  approval rule and `value:` inside one, and a `{value:}` or `{now-plus:}` comparand in an approval rule (a gate has only the call). `loader/threshold-is-not-a-figure` covers `less-than:`
  too. There are no combinators; "or" is two rules (`or_is_two_rules`).
- **Python's one reader**: `pact_adapters.conditions` — `holds(line, value, read=, now=, zone=)`
  answers every word (`None` when a line cannot be told), `all_hold` and `choose` read a rules
  rung. `now` is the caller's, so a replay reads the journaled `now`; days count on the calendar
  in the value's zone (`{now-plus: 1 day}` is 25 hours across the autumn clock change), hours on
  the clock. The approval gate's comparisons go through it (`questions._atom_stops`; its lenient
  twin is gone), so the new words work in a policy.
- **Decide by written rules** (02W §2.5, rules half): `stage.by:` takes `rung`s, a rung its
  `rules:`, each `route-rule` its `when:`, `choose:` and `because:`, read into
  `ir.StageSpec.by`. `loader/a-label-with-nowhere-to-go` (WF-15) refuses a label the stage's
  `chooses-between:` lacks, offering the nearest; `loader/a-decide-that-can-run-out-of-rungs`
  (WF-16) a `decide` with no rung, or whose last rung is rules with no "otherwise".
- **The six combine rules mean one thing** (`pact_adapters.combine.Combine`): each a fold with an
  associative `join`, so items combined inside a segment and segments combined by a parent come
  to the same result, ties included (the earliest item wins), held by a property test. The
  spellings are read from `spec/schema.yaml`'s one copy.
- **Review fixes.** A gate stops a call that carries its argument as null (`amount: null`
  cannot be told against `200 USD`; only a call that leaves the argument out is not the call
  the rule is about), as it did before the one reader. A time of day is compared as a time
  (`more-than: 14:30` loads, is held to a `time` value, and is read as a time, never by its
  hour). The gate reads a date and time an argument carries with no offset in the workspace's
  `time-zone:` (`Gate.zone`). `add up` sums money exactly, to the most decimal places written
  (`0.004 USD` twice is `0.008 USD`, `1000 JPY + 1 JPY` is `1001 JPY`), and refuses money with
  a bare number. `top <n> ... by <field>` ranks dates, moments and times as the condition
  reader orders them (`conditions.ordered_as`), not by their year. `Rule.fires_on`, a twin of
  `Rule.stops_on`, is gone.
- Fixture `tests/trees/an-invoice-case/` (#48's routing and tiers); conformance tests
  `one_grammar_for_every_condition`, `compared_in_its_own_shape`, `or_is_two_rules` and
  `a_decide_cannot_run_out_of_rungs`; an `until:` of `tool:` lines is now refused (WF-18) and
  WF-14's positive half is tested.

### Workflows: bindings and shapes (9 October)

- **A binding reaches only what ran** (`crates/pact-loader/src/bindings.rs`). `pact check` refuses
  a binding that names nothing, offering the nearest three names (WF-4); one to a stage some path
  reaches the reader without passing, naming that path — unless the input it fills is
  `, optional` (WF-5); one to a stage that runs after the reader, or later in a repeat's round
  (WF-6); `item.` outside an `each` (WF-7); a `call:` picked from a binding with no `may-call:`
  (WF-9); a repeat's memory with no `comes-from:`, or one from outside the round (WF-13); an
  `until:` that reads nothing the round writes (WF-14); and a call whose `bind:` leaves a required
  input of its target empty, fills one it does not take, or binds a value of another shape (WF-39,
  the direct and auto-map rungs). The third printed example of design 02W §3 prints as shown.
- **Answer shapes gain `date`, `time` and `date-and-time`, and three ways to build on any shape**:
  `list of <shape>`, a name from the workspace's `shapes:`, and `<shape>, optional`, read by one
  Rust reader (`pact_schema::shape`, behind `schema/not-an-answer-shape`) and by
  `questions.Shape.parse(written, shapes, zone)`. A date and time written without a zone is read
  in the workspace's `time-zone:`, and refused when there is none. A shape made of itself is
  refused (`loader/a-shape-made-of-itself`). `shaped-like:` is held to the same shapes.
- **Memory between rounds** (02W §2.11): `lasts: one-run`, `comes-from:`, `combines-by:` (a
  repeat's `remembers:` only) and `kept-per:` (a workflow's or the workspace's), read into `Fact`.
- **Python**: `ir.AgentSpec` carries the workspace's `shapes` and `time_zone`; PACT's own Pydantic
  AI path shows a named shape as an object and leaves an optional line out of `required`; a
  question and a suspension carry the named shapes they use across a process boundary.
- **Review fixes.** What a repeat reads when a round ends (`comes-from:`, `until:`) must have run
  on every way the round can end — a decision can end it first — or WF-5 names the path. A first
  stage that reads a stage coming round to it again reads from later (WF-6), never "the path
  through ''". A `bind:` key written with dots (`fills.first-name`) is a part of the input's named
  shape: an unknown part is refused with the nearest three, the part's shape is held, and the
  input counts as filled only when every required part is (WF-39). A stage's `at:` and
  `in-time-zone:` are read once, at any depth, and a `bind:` key called `at` is never a moment.
  Until `value:` can be written in a condition, an `until:` of `tool:` lines only is not held by
  WF-14. A question's answer line marked `, optional` may be left out (`Question.validate`).

### Workflows: a `workflows/` collection and its structure (9 October)

- **A workspace can hold workflows.** `workflows/<name>.yaml` is a collection like `agents/`: a
  stage loop that belongs to no agent, with `accepts:`, `answers-with:`, `starts-at:`, named
  `steps:` and the five new `does:` values `call`, `decide`, `each`, `repeat` and `together`
  (design 02W §2.2, §2.3). A stage's `then:` gains `declined`, `nobody-answered` and `heard`. The
  workspace gains `time-zone:`, `calendar:`, named `shapes:`, shared `remembers:`, `owners:` and
  `release:`; a bundle may bring all of them. Two field types join the schema: `moment` (a length
  of time, or `{at:, after:|before:, counted-in:, in-time-zone:}`) and `combine-rule` (`keep-all`,
  `keep-the-latest`, `merge`, `add-up`, `vote`, `top <n> highest|lowest by <field>`).
- **`pact check` holds a workflow's structure** (`crates/pact-loader/src/workflows.rs`): a workflow
  with a mind of its own (WF-1), a stage that thinks (WF-2) and, the other way round, an agent's
  loop that writes a workflow's stage, or a line or an outcome only a workflow's stage reads
  (`limits:`, `checked-by:`, `checks-at-most:`, `undone-by:`, `then.declined:`, ...); a line
  beside a `does:` it does not belong to, an outcome under `then:` its `does:` never ends in
  (02W §2.4: a `decide` and an `answer` have no `then:`), and `items-at-most:` anywhere but an
  `each`'s own `limits:` (WF-3);
  workflows that call each other in a circle (WF-8); an `each` with no ceiling (WF-10) or whose
  items are told apart by position (WF-11, a write by a member of a called agent's `team:`
  included); a `repeat` with no bottom (WF-12); a version of
  something that has none (WF-35); a path that answers nothing (WF-38); a call to a name that is
  not here; and a workflow sharing a name with an agent or a program. Reachability walks a
  workflow and the inside of each `each`, `repeat` and `together`.
- **`forget-after:` is now `kept-for:`.** The old name loads for one more release with the warning
  `loader/forget-after-is-now-kept-for`; `Fact.kept_for` reads either.
- **A `then:` names the stages beside its stage**, never the ones inside it: `names: ^steps`
  resolves to the block the value is written in, then the nearest `steps:` it sits inside.
- **Python reads a workflow as a typed spec**: `ir.WorkflowSpec.from_workflow`, `ir.StageSpec`, `ir.Moment`,
  with the workspace lines a workflow is read under resolved once.

### A rewrite reaches an answer in a shape (9 October)

- **`replace the answer with what <a program> returns` rewrites a structured answer too.** A
  runtime whose agent answers in a shape (`answers-with:`) hands the chain the answer's fields,
  and the program's `takes: content: text` refused them, so the rule left every such answer as
  it was. The chain now hands the program the answer's JSON and reads its reply back as JSON;
  a reply that is not JSON leaves the answer exactly as it was and says so in `unenforced`, as
  any program's failure does (`interceptors._rewritten`).

### The loader as a wheel (9 October)

- **`pip install pact-adapters` brings the `pact` binary.** A new distribution, `pact-loader`
  (`pyproject.toml` at the root, maturin `bin` bindings over `crates/pact-cli`), installs the
  loader into the environment's scripts folder; `pact-adapters` depends on it at exactly its own
  version. Wheels are manylinux 2.28 for x86_64 and aarch64, linked with zig so a newer build
  machine asks for no newer glibc; the source distribution carries `spec/` and
  `models/catalog.yaml`, which the binary compiles in.
- **The loader is found beside the interpreter.** `pact_binary()` looks, after `PACT_BIN`, at a
  checkout's own build, then at the `pact` the wheel installed beside this interpreter (with its
  folder on no `PATH`), then on the `PATH`. A checkout's build now comes before anything on the
  `PATH`: a development environment has the wheel installed too, built from the source as it was
  at the last sync.
- **One script builds and proves what is published.** `scripts/build-wheels.sh` builds the
  wheels and the loader's source distribution, runs `twine check`, builds the loader from its
  source distribution alone, and runs `pact check` from the installed wheels outside the
  checkout. `.github/workflows/wheels.yml` runs it on both architectures and publishes on a tag,
  through PyPI trusted publishing, after the owner approves.

### Review fixes to the parity round (9 October)

- **A collection folder's own file still holds several entries.** `watch/watch.yaml` and
  `tools/tool.yaml` (the folder's name, or the kind the collection holds) are the folder's self
  file again; only a file named after another kind (`tools/catalog.yaml`) is one entry
  (FR-1.1.3 says so now).
- **`model: [a, b]` is a `FallbackModel` on PACT's own Pydantic AI path**:
  `build_agent(spec, models={id: model, ...})` makes the chain from the host's models, in the
  author's order, falling over on a provider error only.
- **The completeness test reads every capability in the installed Pydantic AI**, from its source,
  not only `pydantic_ai.capabilities`: `OpenAICompaction`, `AnthropicCompaction` and
  `BaseDurabilityCapability` have rows now.
- **Each parity row asserts its whole test column**, or `tests/parity/README.md` says why not;
  the export report names each ceiling it cannot carry.
- **A teammate asked twice in one step keeps its answer across a park** for another member that
  failed: the record is keyed by each call's slot.
- **A bank account is hidden only when it passes the IBAN check** (ISO 13616), so a hex digest, a
  dashless UUID or a URL segment that merely starts like one is left alone.

### The parity suite, and five defects the corpus hit (9 October)

- **`tests/parity/`**: one folder per 02P row Phase 1 compiles, each a fixture and an
  `expect.yaml`, run by `adapters/python/tests/test_parity.py`: the import accounts for every key,
  the report a person reads uses plain words, and each row's behaviour holds on PACT's own Pydantic
  AI path. One completeness test fails on any Pydantic AI name the registry has no row for, through
  seven doors (capabilities, `AgentSpec` keys, `ModelSettings` keys, message parts, stream events,
  `ToolDefinition` fields, `GraphBuilder` members). `ImportReport.in_plain_words()` is that report,
  and `pact-import` prints it first.
- **Two calls to one tool in one step are two calls.** The harness kept a step's results and
  refusals keyed by the tool's name, so a cleared call waited while a sibling of the same tool
  waited, and a no to one refused both. They are keyed by the call (`harness.slots_of`).
- **A pattern a bundle contributes is checked as a pattern.** Its `more-than: <limit>` hole was
  refused as a finished rule (`loader/threshold-is-not-a-figure`); it is held to its own
  `expects:` instead, as a workspace's pattern is.
- **`redaction.yaml` can name a social security number**, and a bank account in lower case is a
  bank account.
- **The "not a shape" refusal names only shapes that parse** (it offered descriptions such as
  "an amount of money, like `25.00 USD`").
- **`tools/catalog.yaml` is the tool `catalog`.** A file named after a kind directly in a
  collection's folder was read as the folder's own settings.

### New in the spec

- **Values known only at run time.** `{{run-inputs.<name>}}` and `{{remembers.<name>}}` may
  appear in an agent's `instructions:` and `help:`; the surrounding system fills them before the
  model reads the words. A hole naming nothing the agent declares is refused; `\{{...}}` keeps
  braces meant for the model, and braces that are nearly a hole get a warning.
- **Fallback models.** `model:` takes an ordered list; the next model is tried only when a call
  fails at the provider (never because an answer was wrong). Each model in the list is held to
  `allow-egress:` and `needs:` exactly as a single one is.
- **Answers checked before they count.** `checked-by:` holds a live answer to the same rule shapes
  as `evals:` (`must-contain:`, `must-not-contain:`, `must-say-one-of:`, `must-call-before:`,
  `judged:`); a failed check asks again with the reason, up to `checks-at-most:` attempts
  (default 2), then the run stops and names the rule.
- **Typed action results.** An action may say what it hands back with `answers-with:`, in the
  same shapes as an agent's answer. On an action that runs a `program:`, the two must agree.
- **Governed run-time composition.** `teamwork.may-start:` (`catalogue`, `narrowed-new`) lets an
  agent bring in others while it works. `pact check` refuses it without `limits.starts-at-most:`
  and `limits.nests-at-most:`; each start is journaled, counted across levels and paid from the
  request's pot, and nothing it starts is written into the tree.
- **Schedules.** A port's `every:` is held to one grammar where it is written, and an hour is
  never guessed; a port and its clock are read once, the same way, by every runtime.
- **Program bodies.** A `python` body is one `.py` file given `inputs` (keyed by `takes:`) whose
  last line is the answer; a `wasm` body reads its inputs as one JSON object on standard input and
  writes its answer as one on standard output. A host is handed everything it needs to run one.
- **Learning.** A cycle can be scored by the host's own runner from a kept baseline; "held for a
  person" is its own outcome; what a host hands the grader reaches the measurement it is for.
- **`feel:`** is a latency band a report measures against. It stops nothing; a run is stopped by
  a line with a figure on it.

### Held more tightly

- Nobody is asked to approve a call that at-most-once would refuse anyway.
- An amount nothing can read as a figure stops at the gate.
- A card number written with no-break spaces or dots between its groups is redacted too.
- A value written without a dash is one value, not its letters.
- A sentence is not something that was sent; an answer is checked before it is the answer.
- A deadline can be applied by a runtime that replays a journal.

### The Python adapters

- Run on **Pydantic AI 2.54**, import none of its private names, and never hand it a ceiling
  nobody wrote.
- One table, `pydantic_ai_registry.yaml`, says what every field becomes in Pydantic AI, and a loss
  row says who holds the line instead.
- The core installs with three packages (`pydantic-ai-slim`, `pyyaml`, `httpx`); every other
  framework is an extra. The catalogue and the schema travel with the package, and the loader
  binary is found one way by every command (`PACT_BIN`, then `pact` on the `PATH`, then the
  checkout's own build).

### Commits

- a card number parted by no-break spaces or dots is hidden too (5b53777)
- docs: the test counts are the counts (1139 Rust, 2370 adapter) (6578dd3)
- the test for an approved refund sent again now fails without the look (da506bc)
- what the branch added is held by a test, and three documents say what the code does (8b58ef6)
- `every:` is held to one grammar where it is written, and an hour is never guessed (2aa5da4)
- its own harness says what it does not hold, and its own builder holds what it was skipping (18d9d72)
- braces a model is meant to read, braces that are nearly a hole, and a variant's holes (c2ea8bc)
- the build made last answers, no private Pydantic AI name is imported, and a gate that cannot run the second port stops (f3e108b)
- an amount nothing can read as a figure stops at the gate (2b27eb2)
- the catalogue and the schema travel with the package (ae794e5)
- the mutation test breaks a copy, never the source other processes import (0f379b6)
- nobody is asked to approve a call at-most-once will refuse (257ea1e)
- `feel:` is a latency band, and stops nothing (640aed1)
- a value written without a dash is one value, not its letters (923be88)
- the Pydantic AI table says what budflow builds, and a loss row says who holds the line (e214203)
- a sentence is not something that was sent (ed471e0)
- held for a person is its own answer on a learning Outcome (2e5951c)
- the learning record is read from where it is written (5e11cdb)
- a port and its clock, read once for every runtime (0205d5f)
- a learning cycle a host scores with its own runner, from a kept baseline (800136c)
- what a host hands the grader reaches the measurement it is for (84dabab)
- governed run-time composition (may-start), and one place a grant becomes a member's ceiling (5f0f88e)
- an agent's answer is checked before it is the answer; a variant holds what it says (7bfef1c)
- a pinned server's schema is read by its current name (c3e47a1)
- what an agent is offered and what it can be sent cross the ir wall (c00f122)
- which stage runs now is the loop's own public answer (Loop.stage_to_run) (711d653)
- a projection is what the model reads, and the whole answer is metadata (1e9f70d)
- a keep-going answer grants every ceiling again, and feel: is a wall clock a runtime can hold (8fcf54a)
- a host is handed everything it needs to run a carried program (1a20541)
- a summary a runtime awaits, the one summary text, a watch line written without a bus (a34c6c6)
- memory terms ride on Fact, a run's own Facts, and a pure at-most-once claim (cbb195f)
- a deadline can be applied by a runtime that replays a journal (f54afb1)
- docs: KNOWN-ON-2.54 gives the suite's count now, beside the one at the move (c882edf)
- a bare `{{brand}}` the agent declares is told the one hole it means (32cb4b8)
- the importers' and the exporter's field words live in the registry too (2f4d48b)
- three Phase 1 test files sort their imports (d2007da)
- A1, A2 and A4 reach a live model on Pydantic AI 2.54 (d933476)
- a ceiling nobody wrote is not handed to Pydantic AI (4d9810f)
- the adapters run on Pydantic AI 2.54 (a45fbbf)
- the core installs with three packages; every framework is an extra (51166ad)
- one table says what each field becomes in Pydantic AI (02P §4) (ffe6111)
- an action may say what it hands back (A4) (954837f)
- `model:` may name fallbacks, each held to the same lines (A2) (bbedf39)
- a value only known when a run starts has a place in the words (A1) (c6c773e)
- the loader binary is found one way, by every command (5b8df06)
