# 99 — The PACT language, and the events it is written around

*Plan and specification. §7 says what is built, and where the build differs from this plan.*

PACT is a folder of YAML and Markdown that `pact check` reads and seven
frameworks run. This document adds two things on top of that, and changes
nothing underneath:

1. **A language.** One `.pact` file that says what the folder says, in
   sentences where a sentence is clearer and in the same `key: value` settings
   everywhere else. `pact check team.pact` reads it directly.
2. **Events.** A way to say *"when this happens while the agent works, do
   that"* — when a tool is about to be called, when the work turns to a topic,
   when a count is passed — and a way for one agent to subscribe to another's
   work.

The language is a second way of *writing* a workspace. It is not a second
specification: every line of a `.pact` file becomes the same document a folder
becomes, and every rule `pact check` has is run on that document.

## 1. Decisions taken

Two questions were open when the build started. Both were decided so the work
could proceed, and both can be revisited without undoing it.

| Question | Decision | Why |
|---|---|---|
| Who is the language for? | One language, written in sentences, for both the non-programmer and the developer. No separate builder library. | A builder library is a second surface to keep in step; a developer can read sentences, a non-programmer cannot read a builder. |
| Are guessed events allowed? | Yes, marked as guesses, and a guess may add advice and never stop the run. | The example this was asked for — *"if the work turns to finance, speak to the finance agent first"* — is a guess. Refusing guesses would refuse it. |

## 2. The model in one page

```
signals            what the runtime can see happen
   │
events             a named condition over signals        events/<name>.yaml
   │
reactions          "when this event, then do that"       reactions/<name>.yaml
subscriptions      an agent's own "tell me / ask me"     agent.yaml  listens-for:
```

**Signals** are of three kinds, and the kind decides how far a rule may trust
it:

| Signal | Written | How it is seen | Certainty |
|---|---|---|---|
| A moment | `at: step.tool.before` with optional `when-this:` and `more-than:` | The harness is at that point in the loop; conditions are read off the call | exact |
| A topic | `topic: finance` | A tool, action or knowledge set tagged `topics: [finance]` is touched (exact); the agent says so through the `working-on` tool (guess); a judge reads the step (guess) | exact or guess, by the topic's `noticed-by:` |
| A judgement | `judged: yes` | A second model answers the event's `description:` as a yes/no question about the step | guess |

**Reactions** do one or more of four things, in order:

| Step | What happens | Blocks the agent? |
|---|---|---|
| `remind: <text>` | The text is added to what the model is told for the rest of the run | no |
| `consult: <agent>` | That agent is asked about what is happening and its answer is put in front of the model. Before a tool call, the call is held and the answer comes back in its place; the model may then make the call again | yes |
| `tell: <agent>` | That agent is told what happened. Its answer is recorded and not shown to the model | no |
| `stop: <text>` | The run ends with this sentence | yes |

Asking a *person* is deliberately not on the list: before a call it is what a
`policy` does, and when a count runs out it is what `limits.when-it-runs-out`
does. A third way to say either would be a second source of truth.

**Subscriptions** are reactions declared from the other side. An agent that
writes `listens-for: [{topic: finance, how: asked-first}]` is consulted by every
other agent whose work touches finance; `how: told-after` makes it a `tell`.

### Mapping onto the seven primitives

Nothing here is an eighth primitive.

| New word | Primitive | Because |
|---|---|---|
| `topics:` on a tool, action or knowledge set | Origin | A tag on where something comes from, carried with it |
| `events:` — `at`, `when-this`, `more-than`, `topic` | Check | A condition that holds or does not |
| `judged: yes` | Check + Actor | A condition decided by a model |
| `reactions:` — `event`, `fires`, `then` | Flow | What happens next, and how often |
| `remind`, `stop` | Flow | A step |
| `consult`, `tell`, `listens-for` | Flow + Actor | A step that puts another agent to work |
| the cost of a judge or a consulted agent | Allowance | Charged to the run's own ceilings |

## 3. What is added to the specification

### 3.1 Workspace

```yaml
topics:                       # topics/<name>.yaml
  finance:
    description: Money moving — refunds, invoices, tax.
    noticed-by: [tags, the-agent]        # tags | the-agent | a-judge ; default [tags]

events:                       # events/<name>.yaml
  invoice-about-to-go:
    description: An invoice is about to be sent.
    at: step.tool.before
    when-this:
      - { tool: invoices/send }

reactions:                    # reactions/<name>.yaml
  finance-first:
    description: Finance work is checked with the finance desk first.
    topic: finance            # an inline signal, or `event: <name>`
    applies-to: every-agent   # default: the-agents-that-name-it
    fires: once-a-run         # default; or every-time
    then:
      - consult: finance-desk
```

A signal is written one way: `event:` naming an event, or exactly one of `at:`,
`topic:` and `judged:` inline. `when-this:` and `more-than:` narrow an `at:`.

The moments an event can be `at:`:

| Address | When |
|---|---|
| `turn.run.started` | the turn begins; a judge reads the customer's words |
| `step.run.started` | each step begins — the one to count steps with |
| `step.tool.before` | a tool is about to be called; `when-this:` reads the call |
| `step.tool.completed` | a tool has answered |
| `step.message.after` | the agent has written a step's words; a judge reads them |
| `step.delegate.before` | a teammate is about to be asked |

`more-than: 5` holds from the sixth matching moment of one run onward.

### 3.2 Agent, tool, action, knowledge

```yaml
# agent.yaml
reactions: [wrap-up]                       # the reactions this agent names
listens-for:
  - { topic: finance, how: asked-first }   # or  event: <name> ; how: told-after

# tools/payments.yaml, an action of it, or knowledge/<name>.yaml
topics: [finance]
```

### 3.3 The laws `pact check` holds

| Rule | Severity | Fires when |
|---|---|---|
| `loader/a-signal-says-one-thing` | error | an event or reaction names no signal, or more than one |
| `loader/a-narrowing-with-nothing-to-narrow` | error | `when-this:` or `more-than:` beside `topic:` or `judged:`, `when-this:` at a moment that is not about a call, or a `when-this:` line that looks at a value instead of a call |
| `loader/a-signal-names-no-such-call` | error | a `when-this:` line names a tool, or an action of one, the workspace does not have |
| `loader/a-judge-reads-words` | error | `judged: yes` at a moment that carries no words |
| `loader/a-guess-cannot-stop` | error | `stop:` on a signal that can be a guess |
| `loader/a-topic-nothing-carries` | warning | a topic noticed only by tags that no tool, action or knowledge set carries |
| `loader/a-tag-nobody-reads` | error | something is tagged with a topic whose `noticed-by:` leaves out `tags` |
| `loader/asks-only-itself` | error | a reaction an agent names consults or tells that same agent and nobody else |
| `loader/nothing-points-at-it` | warning | a reaction that is not `every-agent` and that no agent lists; an event or a topic nothing waits for (the existing rule, three more kinds) |
| `loader/a-step-does-one-thing` | error | a `then:` step with no verb, or two |

One existing law reaches further than it did. **An agent that is asked or told
is reached the way a teammate is.** `loader/three-things-that-make-a-leak`
follows a reaction's `consult:` and `tell:`, and every `listens-for:` line, as
it follows `team:` — what one agent read is put in front of the other, so an
agent that reads strangers' words and wakes one that can send mail is refused
unless a person stands at the door out. The edge is one nobody wrote in the
first agent's own file, which is why the checker has to draw it.

Two laws are held at run time, because they are about a run:

- **A handler does not wake itself.** While a reaction is being carried out,
  the same reaction does not fire again — in the consulted agent's run or
  anywhere beneath it. The depth of consultation is bounded by the number of
  reactions written.
- **A consulted agent is paid from the same pot.** Its cost is charged to the
  run that woke it, against the same `limits:`.

## 4. The language

### 4.1 Shape

A `.pact` file is a list of **blocks**. A block is a header at the left margin
and an indented body.

```
workspace "Refund Desk"
  description: Decides refund requests.

agent refund-desk "Refund Desk"
  description: Decides whether a customer's refund request should be approved.
  takes message: text, photos: list of images
  gives decision: one of approved, declined, reason: text, amount: money
  uses zendesk, payments
  asks policy-checker: Checks the request against our written refund policy.
  at most 8 steps
  when it runs out: stop and say so

  when the work touches finance
    consult finance-desk

  instructions
    You decide refund requests. Read the ticket before anything else.
```

A body line is one of three things:

| Line | Looks like | Means |
|---|---|---|
| a **setting** | `key: value`, with anything YAML allows beneath it | exactly that field. Every field in the specification can be written this way, so nothing is out of reach |
| a **sentence** | starts with one of the words in §4.3 | the field or fields the table gives |
| a **text block** | a field's name alone on a line, text indented beneath | that field, holding the text as written |

A line that is none of the three is refused, naming the nearest sentence.

### 4.2 Headers

`workspace "<name>"` holds the workspace's own settings. Every collection has a
header word — `agent`, `tool`, `workflow`, `policy`, `question`, `loop`,
`topic`, `event`, `reaction`, `knowledge`, `skill`, `resource`, `program`,
`value`, `port`, `shape`, `remembers`, `detector`, `owner`, `context-policy`,
`bundle`, `interceptor`, `watch` — followed by the entry's name:
`tool payments`. An `agent` may add its display name in quotes. The five
single documents — `redaction`, `evals`, `learning`, `release`, `models` — are
headers with no name. `when <signal>` is a reaction (§4.3).

### 4.3 Sentences

| In | Sentence | Becomes |
|---|---|---|
| agent | `takes <field>: <shape>, …` | `accepts:` |
| agent | `gives <field>: <shape>, …` | `answers-with:` |
| agent | `uses <name>, …` | `uses:` |
| agent | `asks <agent>: <what for>` | one line of `team:` |
| agent | `at most <n> steps` / `tool calls` / `tokens` | `limits.steps-at-most:` … |
| agent | `spends under <money> a request` | `limits.cost-per-request-under:` |
| agent | `when it runs out: <what>` | `limits.when-it-runs-out:` |
| agent | `remembers <name>` + body | one entry of `remembers:` |
| agent | `listens for topic <t>: asked first` / `told after` (or `event <e>`) | one line of `listens-for:` |
| agent, top | `when <signal>` + body | a reaction; inside an agent, one that agent names |
| tool, knowledge | `about <topic>, …` | `topics:` |
| policy | `before <tool>/<action>[, when <arg> is more than <x>]: ask <question>, because <why>` | one `ask-a-person:` rule |
| reaction, event | `when <signal>` | the signal's fields, for a `reaction <name>` or `event <name>` block |
| reaction | `remind it: <text>` | `then: [{remind: …}]` |
| reaction | `consult <agent>` | `then: [{consult: …}]` |
| reaction | `tell <agent>` | `then: [{tell: …}]` |
| reaction | `stop and say: <text>` | `then: [{stop: …}]` |
| reaction | `called <name>` | the reaction's name, when the one made from its sentence will not do |
| reaction | `every time` | `fires: every-time` |
| workflow, program | `takes …` · `gives …` | `accepts:` (a program's `takes:`) · `answers-with:` |
| workflow, loop | a statement (§4.3a) | one stage of `steps:` |
| any block | `based on <name> [with <name>: <value>, …]` | `based-on:`, and `with:` |
| top | `let <name> = <figure>` | one entry of `values:` |

Signals, after `when`:

| Signal sentence | Becomes |
|---|---|
| `the agent is about to call <tool>[/<action>]` | `at: step.tool.before`, `when-this: [{tool: …}]` |
| `the agent has called <tool>[/<action>] more than <n> times` | the same, with `more-than: <n>` |
| `<tool>[/<action>] has answered` | `at: step.tool.completed`, `when-this: [{tool: …}]` |
| `the agent has taken more than <n> steps` | `at: step.run.started`, `more-than: <n>` |
| `a turn starts` | `at: turn.run.started` |
| `the agent is about to ask a teammate` | `at: step.delegate.before` |
| `the agent has written a step` | `at: step.message.after` |
| `the work touches <topic>` | `topic: <topic>` |
| `it looks like <description>` | `judged: yes`, and `description:` the sentence, capitalised — it is the question the judge answers. Where the judge reads is a setting beneath it: `at: turn.run.started` for what the customer wrote |
| `<event> happens` | `event: <event>` |

### 4.3a Figures, patterns and programs

The document already had the parts of a programming language, under other
names. The language writes them the way a program is written, and adds nothing
to what they mean.

| What a programmer calls it | What the document has | Written |
|---|---|---|
| a constant | `values:` — one figure, used as `{use: <name>}` in a setting and `values.<name>` in a binding | `let refund-limit = 200 USD` |
| a variable | a stage's answer, read by the stage's name — `steps.plan.findings` | `plan = call planner …`, then `plan.findings` |
| a function | a workflow: `accepts:`, `answers-with:`, `steps:` — and an agent or a carried program, called the same way | `workflow <name>` with `takes …`, `gives …` and statements; `call <name> with …` |
| a template with parameters | a base with `expects:`, filled by `based-on:` and `with:` | `based on desk with domain: billing, cap: 0.10 USD` |
| a loop over a list | a stage that `does: each` | `for each item in input.documents` |
| a loop until something holds | a stage that `does: repeat`, with `until:` | `repeat at most 4 times`, `until:` beneath |
| a branch | a stage that `does: decide` | `decide`, with an `if <label>` for each way it can go |
| at once | a stage that `does: together` | `together` |
| return | a stage that `does: answer` | `answer with result: make.result` |

```
workflow deliver
  description: Research a brief, plan from the findings, then build from the plan.
  takes brief: text
  gives result: text

  research = call researcher with brief: input.brief
  plan = call planner with brief: input.brief, findings: research.findings
  make = call builder with plan: plan.plan
  answer with result: make.result
```

**Statements**, in a `workflow` or a `loop` block, and inside a `for each`, a
`repeat` or a `together`:

| Statement | Becomes |
|---|---|
| `<name> = <statement>` | the stage `<name>`. Without it the stage is named after what it does: `call planner` is the stage `planner` |
| `call <target> [with <input>: <binding>, …]` | `does: call`, `call:`, `bind:` |
| `for each item in <binding>` + body | `does: each`, `over:`, and the body as its `steps:` |
| `repeat [at most <n> times]` + body | `does: repeat`, `at-most:`, and the body as its `steps:` |
| `together` + body | `does: together`; the statements in the body all start at once |
| `decide` + an `if <label>` for each label | `does: decide`, `chooses-between:` |
| `answer [with <field>: <binding>, …]` | `does: answer`, `bind:` |
| `stop <binding>` | `does: stop`, `stops:` |
| `ask <question>` | `does: ask-someone`, `asks:` |
| `think` · `use tools` · `check its work` · `run code` | `does:` that — the stages of a `loop` |

**Order is the wiring.** A statement goes on to the one written after it
(`then: { answered: <next> }`) and the first is where the body starts
(`starts-at:`). An `answer` goes nowhere. The statements beneath an `if` are
stages beside the decision, and the last of them goes on to whatever is
written after the `decide` — which is how branches come back together.
`if <label>: <stage>` points at a stage written elsewhere, or at `done`.

**Settings go beneath a statement**, as beneath anything: `at-most:`,
`if-it-fails:`, `until:`, `limits:`. A `then:` written there is kept, and where
it says `answered:` the order does not — so a stage that goes back, or to
`done`, says so itself.

**A binding is still a path, never an expression** (02W §2.0). `plan.findings`
is `steps.plan.findings`; a path that starts with one of the words a binding
starts with (`input`, `item`, `remembers`, `values`, `steps`, `latest-update`,
`run-inputs`, `used`) is left as written. There is no arithmetic and no
assignment after the fact: a name is given once, by the stage that answers.
That is the document's rule, and it is what lets `pact check` say before
anything runs that a stage reads something that may not have happened
(`loader/a-binding-to-a-stage-that-may-not-have-run`).

**The printer writes statements only where an order of lines can say the
wiring**, and settings otherwise — found out, as everything here is, by reading
its own text back. Every workflow and loop under `examples/` is written as
statements.

### 4.4 Where a `.pact` file may sit

- **On its own.** `pact check team.pact` — the file is the workspace.
- **At the top of a folder**, beside the things that are files by nature: a
  knowledge set's documents, a skill's scripts. Several `.pact` files in one
  folder are read as one; an entry written twice is refused.

### 4.5 The two directions

| Command | Does |
|---|---|
| `pact check <file.pact>` / `pact show <file.pact>` | read it like any workspace |
| `pact write [PATH]` | print the workspace at PATH as one `.pact` file |
| `pact build <file.pact> --to <folder>` | write the folder of YAML and Markdown it stands for |

**The round-trip guarantee.** For every workspace `W`: reading `pact write W`
gives the same document as reading `W`. It is held by a test that does this for
every workspace under `examples/`, and it is what keeps the two ways of writing
from drifting: a keyword the language cannot print fails that test.

It holds by construction rather than by a table of keywords. The printer writes
a sentence only after reading its own sentence back and getting the field it
started from; anything else is written as a setting, and a setting can say
anything.

## 5. What happens at run time

The harness (`adapters/python/src/pact_adapters/harness.py`) owns the loop: the
framework performs one model call and executes one tool. So the moments above
are places in PACT's own code, and nothing has to be intercepted.

| Moment | What the harness does |
|---|---|
| start of turn | reactions at `turn.run.started`; a judge, if one is written, reads the customer's words; tagged knowledge that was retrieved raises its topics |
| start of each step | counts the step; reactions at `step.run.started` |
| after the model's step | a judge, if one is written, reads the words; `step.message.after` |
| before each tool call | after the workspace's interceptors have run, so a consulted agent sees what a tool would see: `step.tool.before`, and the topics the tool or action carries. A `consult` holds the call |
| after each tool call | `step.tool.completed` |
| before a teammate is asked | `step.delegate.before` |

The agent is offered a `working-on` tool when a topic that matters to it is
`noticed-by: the-agent`. Calling it raises the topic; what a consulted agent
says comes back as the tool's answer.

What a runtime cannot do it says: with nobody to run a consulted agent, or no
model to judge with, the reaction is reported on `RunResult.unenforced`, and
the TypeScript port reports every reaction that way.

## 6. Work packages

| | Package | Where |
|---|---|---|
| L1 | Specification: `topics`, `events`, `reactions`, `listens-for`, `topics:` tags | `spec/schema.yaml` |
| L2 | The laws of §3.3 | `crates/pact-loader/src/reactions.rs` |
| L3 | The run-time half | `adapters/python/src/pact_adapters/reactions.py`, `harness.py`, `ir.py` |
| L4 | The second port says what it does not do | `adapters/typescript/src/harness.ts` |
| L5 | The language: reader and printer | `crates/pact-lang` |
| L6 | The loader reads `.pact`; `pact write`, `pact build` | `crates/pact-loader`, `crates/pact-cli` |
| L7 | Examples, the round-trip test, coverage scripts, documentation | `examples/language`, `tests`, `scripts`, `site-docs` |

## 7. Status: what is built, and where it differs from this plan

All seven packages are built (12 November 2026), and an eighth that was not in the plan: L8, asked for once the first seven could be used.

| | What exists | Held by |
|---|---|---|
| L1 | Five groups (`topic`, `event`, `reaction`, `reaction-step`, `subscription`), `reactions:` and `listens-for:` on an agent, `topics:` on a tool, an action and a set of documents. 68 kinds, 569 keywords, 342 closed-choice words | `scripts/primitive-coverage.py`, which stops on a keyword with no primitive |
| L2 | `crates/pact-loader/src/reactions.rs`, nine rules; three more kinds in `unnamed.rs` | `crates/pact-cli/tests/a_reaction_waits_for_one_thing.rs` |
| L3 | `reactions.py`; six hooks in `harness.py`; `Suspension.reactions` | `adapters/python/tests/test_a_reaction_is_carried_out_where_it_was_written.py` |
| L4 | `harness.ts` offers `working-on` and names every reaction on `unenforced`; §7.28 list B of `docs/20` has the row | the golden set, and `the_subset_the_second_port_runs.rs` |
| L5 | `crates/pact-lang`: `read`, `write`, and `tree` for a folder | `crates/pact-lang/tests/every_sentence_means_one_thing.rs` |
| L6 | The loader reads `.pact`, alone or at the top of a folder; `pact write`, `pact build`; `pact discover` finds a folder with a `.pact` file | `crates/pact-cli/tests/the_language_and_the_folder_are_one_workspace.rs` |
| L7 | `examples/kernel/finance-first`, `examples/language/{hello,finance-first,staff-desk}`; two guide pages | the round trip over every workspace under `examples/` |
| L8 | §4.3a: `let`, `based on … with …`, `takes`/`gives` on a workflow and a program, and statements for a workflow's and a loop's stages (`crates/pact-lang/src/read/flow.rs`, `write/flow.rs`). `examples/language/help-centre`: four files, a pattern and two desks, two workflows with one calling the other, figures, a reaction, learning | `crates/pact-lang/tests/a_workflow_is_written_in_the_order_it_runs.rs`; `every_shipped_workflow_and_loop_is_written_in_the_order_it_runs`; `adapters/python/tests/test_a_workflow_written_as_statements_runs.py`, which runs both workflows |

### Where the build differs

- **`event:`, not `on:`.** A YAML 1.1 reader takes a bare `on` for the word
  "true". PyYAML is one, and it is what half the tooling here reads the schema
  with, so the first draft's `on:` could not be loaded by this repository's own
  tests.
- **A subscription says how often by what it is.** `asked-first` fires once a
  run: once the answer is in front of the model it is there. `told-after` fires
  every time: a record that hears only the first refund is wrong. A reaction
  written out in full still has `fires:`.
- **`tell` is waited for.** The agent told is run where the reaction fired, and
  the step goes on when it has finished. Its answer is recorded
  (`RunResult.reactions`) and never shown to the model, which is the part of
  "told, not asked" that changes what the model does. Running it alongside is
  the host's to do.
- **A consulted agent can consult in turn only if it writes
  `limits.asks-itself-at-most:`.** That is the rule delegation already has for
  an agent that is put to work by another, not a new one.
- **With nothing here that can run another agent, a call is not held.** The run
  says so on `unenforced` and carries on. An agent that could be asked and
  failed is different: the call waits once, and the model is told why.
- **The judge is the checking model, or the working one.** A run handed a
  second transport for `model-for-checking:` judges with it; a run handed one
  transport judges with the model that is doing the work, and each question is
  counted (`Reactor.judged`).
- **`pact build` takes a `.pact` file.** A folder that already has attachment
  files in it is not rebuilt; the files it would have to copy are the
  author's to move.

- **A proposed change is checked against the folder a `.pact` tree stands
  for.** `checking.check_instructions` copies the author's tree to try a
  learning cycle's proposal on it. A copy written in the language is rewritten
  as a folder first — `pact write`, then `pact build`, with the files it
  carries left in place — because that module changes one field of a file and
  must not edit a `.pact` file's text by position. Before this, such a tree was
  checked unchanged and the proposal passed whatever it said.

### What is not done

- **Comments are not carried between the two ways of writing.** A comment is
  not part of the document either is read into, so `pact write` and `pact
  build` drop them.

- **The fixes that name a file still name the folder form.** `pact check` on a
  `.pact` file says *"Add a file `tools/zendesk.yaml`"* where the block to
  write is `tool zendesk`. The message is the schema's and is the same for both
  ways of writing.
- **Sentences cover the lines people write most, not every field.** Questions,
  evals, ports, a decision's `by:` rungs and a repeat's `until:` are written
  as settings. Nothing is out of reach — a setting can say any of it.
- **No expressions.** A statement's bindings are paths, as the document's are.
  `more than`, `is` and the rest live in `when-this:` lines, where they are
  checked; there is no `a + b`, and adding one would be a change to the
  specification, not to the language.
- **The loop variable is always `item`.** `for each item in …`, and
  `item.<part>` inside. The document has one word for it, so the language does.
- **No run against a live model.** Every test here drives a scripted one, which
  is how the rest of this repository tests a loop. Whether a model calls
  `working-on` when it should is not something a script can show.
- **No study with people.** Whether the language is easier than YAML for
  somebody who has seen neither is the question it exists to answer, and it has
  not been asked of anybody.
