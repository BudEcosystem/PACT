# Topics, events, reactions and subscriptions

The complete reference for the five kinds that let a workspace say *"when this
happens while an agent works, do that"*. For a first read, start with the
guide: [When something happens](../guide/events-and-reactions.md).

| Kind | Written under | What it is |
|---|---|---|
| **topic** | `topics/<name>.yaml`, or a `topic <name>` block | a subject the work can turn to, given a name |
| **event** | `events/<name>.yaml`, or an `event <name>` block | something that can happen in a run, given a name so several things can wait for it |
| **reaction** | `reactions/<name>.yaml`, a `reaction <name>` block, or a `when …` block | what to do when a signal holds |
| **reaction step** | a line of a reaction's `then:` | one thing a reaction does |
| **subscription** | a line of an agent's `listens-for:` | a reaction written from the side of the agent that wants to hear |

Three places take tags or names that point at these: `topics:` on a tool, on
one action of a tool and on a set of documents; `reactions:` on an agent (the
reactions that cover it); and `listens-for:` on an agent.

## Signals

A **signal** is what an event or a reaction waits for. It is exactly one of
three things, and `pact check` refuses a signal that is none or more than one
(`loader/a-signal-says-one-thing`).

| Kind of signal | Fields | Certain? |
|---|---|---|
| a **moment** in the run | `at:`, narrowed by `when-this:` and `more-than:` | exact |
| a **topic** | `topic:` | exact when a tag raised it; a guess when the agent or a judge did |
| a **judgement** | `judged: yes`, with `description:` as the question | a guess |

A reaction may instead name an event with `event: <name>`; then it waits for
whatever that event waits for.

### The six moments

| `at:` | Holds | Carries words a judge can read |
|---|---|---|
| `turn.run.started` | when the turn begins | yes, what the customer wrote |
| `step.run.started` | when each step begins; the one to count steps with | no |
| `step.tool.before` | when a tool is about to be called | no |
| `step.tool.completed` | when a tool has answered | no |
| `step.message.after` | when the agent has written a step | yes, what the agent wrote |
| `step.delegate.before` | when a teammate is about to be asked | no |

### Narrowing a moment

`when-this:` says which calls a moment is about. It is allowed only at the two
moments that are about a call, `step.tool.before` and `step.tool.completed`
(`loader/a-narrowing-with-nothing-to-narrow` otherwise), and every tool and
action it names has to exist (`loader/a-signal-names-no-such-call`). Every
line of it has to hold.

```yaml
when-this:
  - { tool: invoices/send }                                   # one action
  - { tool: payments, effect: spends }                        # every action that moves money
  - { tool: payments/issue-refund, arg: amount, more-than: 200 USD }   # what the model chose
```

`more-than: <n>` beside `at:` says how many times the moment has to have
happened in this run. `more-than: 5` beside `at: step.run.started` holds from
the sixth step on.

## Topic

| Field | Type | |
|---|---|---|
| `description` | text, required | what counts as this subject, in a sentence a person or a model could decide by |
| `noticed-by` | list of `tags`, `the-agent`, `a-judge` | how the runtime finds out. Left out, it is `[tags]` |

How each way of noticing works:

- **`tags`**: a tool, an action or a set of documents tagged `topics:
  [<name>]` is about to be used. Nothing is guessed, so a reaction on this may
  stop a run.
- **`the-agent`**: the agent is offered a tool called `working-on` that takes
  one argument, the topic, chosen from the topics that matter to it. The
  tool's description lists each topic with its `description:`. Calling it
  raises the topic. It costs no extra model call, and it is a guess: the agent
  can forget.
- **`a-judge`**: a second model reads each step the agent writes and answers
  whether the work has turned to the topic. A guess, and one model call each
  time it looks.

Two rules keep tags and topics honest. A topic that nothing is tagged with and
that only tags could raise is a warning (`loader/a-topic-nothing-carries`). A
tag on a topic whose `noticed-by:` leaves out `tags` is an error
(`loader/a-tag-nobody-reads`), because the tag would be read by nothing.

## Event

| Field | Type | |
|---|---|---|
| `description` | text, required | what has happened when this holds. Where `judged: yes`, it is the question the judge answers |
| `at` | a moment | one of the six above |
| `when-this` | list | which calls, at a moment about a call |
| `more-than` | whole number | how many times first |
| `topic` | a topic's name | the subject the work has to turn to |
| `judged` | yes or no | a second model decides |

An event does nothing by itself. It exists so that a reaction (`event:
<name>`) or a subscription (`{ event: <name>, how: … }`) can wait for it, and
so that the moment is described once.

## Reaction

| Field | Type | |
|---|---|---|
| `description` | text, required | what this does and why |
| `event` | an event's name | wait for that event; or leave it out and write the signal here |
| `at`, `when-this`, `more-than`, `topic`, `judged` | as for an event | the signal, written in place |
| `applies-to` | `the-agents-that-name-it` or `every-agent` | who it covers. The first is the default: an agent lists it under `reactions:` |
| `fires` | `once-a-run` or `every-time` | how often. The first is the default |
| `then` | list of steps, required | what to do, in order |

`fires: every-time` on a reaction that holds a call back means each
*different* call: the agent can make the same call again and have it go
through.

A reaction nothing names and that does not cover every agent is reported by
`loader/nothing-points-at-it`, the rule every named thing in a workspace is
under.

## Reaction step

Each line of `then:` has exactly one of these (`loader/a-step-does-one-thing`).

| Step | What happens | Allowed on a guess |
|---|---|---|
| `remind: <text>` | the text is added to what the model is told, from its next step to the end of the run. Nothing waits | yes |
| `consult: <agent>` | that agent is run and told what is happening; its answer is put in front of the model. Before a tool call, the call is **held** | yes |
| `tell: <agent>` | that agent is run and told what happened. Its answer is recorded and not shown to the model | yes |
| `stop: <text>` | the run ends with this sentence | **no** (`loader/a-guess-cannot-stop`) |

A reaction that an agent names and that does nothing except wake that same
agent is refused (`loader/asks-only-itself`).

## Subscription

A line of an agent's `listens-for:`.

| Field | Type | |
|---|---|---|
| `topic` | a topic's name | the subject to hear about |
| `event` | an event's name | the event to hear about |
| `how` | `asked-first` or `told-after`, required | whether its answer goes to the agent whose work it is |

A subscription is turned into a reaction on every *other* agent in the
workspace: `asked-first` becomes a `consult` that fires once a run, and
`told-after` becomes a `tell` that fires every time. The agent that listens is
never woken by its own work.

## What happens in a run

The Python harness, the code that owns the agent's loop, looks for signals at
six places in that loop. A framework is used only to make one model call or
run one tool, so these are places in PACT's own code and nothing is
intercepted.

| When | What the harness does |
|---|---|
| the turn starts | reactions at `turn.run.started`; a judge, if one is written for this moment, reads the customer's words; tagged documents that were retrieved raise their topics |
| each step starts | counts the step; reactions at `step.run.started` |
| the model has written a step | the step is paid for first; then a judge, if one is written, reads the words; reactions at `step.message.after` |
| before each tool call | after the workspace's interceptors, so a consulted agent sees what the tool would see: reactions at `step.tool.before`, and the topics the tool or action is tagged with |
| after each tool call | reactions at `step.tool.completed` |
| before a teammate is asked | reactions at `step.delegate.before` |

### A held call

When a `consult` fires before a tool call:

1. The call is not made. The consulted agent is run and told which call was
   about to happen and with what arguments.
2. Its answer is given to the model in place of the tool's result, marked as
   coming from that agent.
3. If the model makes the same call again, it goes through.
4. A held call is not put to a person for approval in the same step. Approval
   is asked on the call that will actually happen, once.

### The laws a run holds

- **A reaction does not wake itself.** While a reaction is being carried out,
  the same reaction does not fire again, in the consulted agent's run or in
  any run beneath it. However agents consult each other, that ends.
- **A consulted agent is paid from the same budget.** What it costs is charged
  to the limits of the run that woke it.
- **A consulted agent consults in turn only if it says it may**, with
  `limits.asks-itself-at-most:`, the rule delegation already has.
- **Reaction state survives a pause.** When a run parks to wait for a person,
  what has fired, what has been counted, which calls were held and which
  reminders were given are saved with it, and the run resumes with them.

### What a run reports

| On the result | Holds |
|---|---|
| `reactions` | one entry for each time a reaction was carried out: `reaction` (its name), `at` (the step), `did` (what it did, in words), `certainty` (`exact` or `guess`) and, where an agent was woken, `heard`: which agent, `asked-first` or `told-after`, and what it said |
| `unenforced` | a sentence for anything written that this run could not carry out |

A run says so on `unenforced` in three cases: nothing here can run another
agent, so a `consult` or `tell` was skipped and the call went through; no
model was available to judge with; or the runtime is the TypeScript port,
which offers the `working-on` tool, so both runtimes show the model the same
tools, and carries no reaction out.

### Who judges

A run given a second model for checking (`model-for-checking:`) judges with
it. A run given one model judges with the model that is doing the work. Each
question a judge is asked is counted separately from the agent's own model
calls, and is paid for from the same limits.

## What `pact check` refuses

| Rule | Level | Fires when |
|---|---|---|
| `loader/a-signal-says-one-thing` | error | an event or reaction waits for nothing, or for two different kinds of thing |
| `loader/a-narrowing-with-nothing-to-narrow` | error | `when-this:` at a moment that is not about a call |
| `loader/a-signal-names-no-such-call` | error | `when-this:` names a tool or action the workspace does not have |
| `loader/a-judge-reads-words` | error | `judged: yes` at a moment that carries no words |
| `loader/a-guess-cannot-stop` | error | `stop:` on a judgement, or on a topic the agent or a judge notices |
| `loader/a-step-does-one-thing` | error | a `then:` line with no verb, or two |
| `loader/asks-only-itself` | error | a reaction an agent names only wakes that same agent |
| `loader/a-tag-nobody-reads` | error | something is tagged with a topic whose `noticed-by:` leaves out `tags` |
| `loader/a-topic-nothing-carries` | warning | a topic only tags could raise, and nothing is tagged with it |

One older rule reaches further than it did. `loader/three-things-that-make-a-leak`
looks for an agent that can read private data, read a stranger's words and
send something out. It follows `consult:`, `tell:` and `listens-for:` the way
it follows `team:`, because what one agent read is put in front of the agent
it wakes.

## Where it lives in the code

| Part | File |
|---|---|
| The five kinds and their fields | `spec/schema.yaml` |
| The rules above | `crates/pact-loader/src/reactions.rs` |
| The leak rule's new edges | `crates/pact-loader/src/leaks.rs` |
| Signals, the reactor and the judge | `adapters/python/src/pact_adapters/reactions.py` |
| The six places in the loop | `adapters/python/src/pact_adapters/harness.py` |
| State kept across a pause | `adapters/python/src/pact_adapters/suspension.py` |
| What the TypeScript port reports | `adapters/typescript/src/harness.ts` |
| A workspace that uses all of it | `examples/kernel/finance-first` |
