# When something happens

A **reaction** says: *when this happens while an agent works, do that.* Remind
the agent of something, ask another agent first, tell another agent afterwards,
or stop.

```yaml title="reactions/wrap-up.yaml"
description: A run that is taking long is told to finish with what it has.
at: step.run.started
more-than: 6
then:
  - remind: You have taken more than six steps. Answer with what you have.
```

In the [PACT language](the-pact-language.md) the same thing is three lines
inside the agent it is for:

```text
when the agent has taken more than 6 steps
  remind it: You have taken more than six steps. Answer with what you have.
```

## What a reaction can wait for

Three kinds of thing, and the kind decides how far a rule may rely on it.

| It waits for | Written | In the language | Certain? |
|---|---|---|---|
| a **moment** in the run | `at: step.tool.before`, narrowed with `when-this:` and `more-than:` | `when the agent is about to call invoices/send` | exact |
| a **topic** the work turns to | `topic: finance` | `when the work touches finance` | exact when a tagged tool is used; a guess when the agent says so itself |
| a **judgement** | `judged: yes` — a second model answers the `description:` as a yes-or-no question | `when it looks like the customer is upset` | a guess |

The moments: `turn.run.started` (the turn begins), `step.run.started` (a step
begins — the one to count with), `step.tool.before` (a tool is about to be
called), `step.tool.completed` (one has answered), `step.message.after` (the
agent has written a step) and `step.delegate.before` (a teammate is about to
be asked).

## What a reaction can do

| Step | In the language | What happens |
|---|---|---|
| `remind: <text>` | `remind it: <text>` | The text is added to what the model is told, for the rest of the run |
| `consult: <agent>` | `consult <agent>` | That agent is asked about what is happening, and its answer is put in front of the model. Before a tool call, the call is **held**: the answer comes back in its place, and the model can make the call again |
| `tell: <agent>` | `tell <agent>` | That agent is told what happened. Its answer is recorded and not shown to the model |
| `stop: <text>` | `stop and say: <text>` | The run ends with this sentence |

Asking a *person* is not on the list on purpose. Before a call, that is an
[approval policy](approvals.md); when a count runs out, it is
`limits.when-it-runs-out: ask-a-person`.

## Topics

A topic is what the work can be about, given a name.

```yaml title="topics/finance.yaml"
description: Money moving — refunds, invoices, credit, tax.
noticed-by: [tags, the-agent]
```

```yaml title="tools/billing.yaml"
description: Invoices and refunds.
topics: [finance]
```

`noticed-by:` says how the runtime finds out:

- **`tags`** — a tool, an action or a set of documents tagged `topics:
  [finance]` is about to be used. Exact, and what you get if you leave the line
  out.
- **`the-agent`** — the agent is given a `working-on` tool and says so itself.
  It costs nothing extra and it is a guess: the agent can forget.
- **`a-judge`** — a second model reads every step. A guess that costs a model
  call each time.

## An agent that listens

A subscription is a reaction written from the other side. The agent that wants
to hear about something says so in its own file, and no other agent's file
changes.

```yaml title="agents/finance-desk/agent.yaml"
description: Knows the rules for refunds, invoices and tax.
listens-for:
  - { topic: finance, how: asked-first }
```

```yaml title="agents/auditor/agent.yaml"
description: Keeps a note of every refund.
listens-for:
  - { event: refund-issued, how: told-after }
```

`asked-first` makes it a `consult`: every other agent whose work touches
finance waits for the finance desk's answer. `told-after` makes it a `tell`.
An `event:` is a moment with a name, written once under `events/` so several
things can wait for it.

### What a run looks like

A customer asks for a refund on `examples/kernel/finance-first`:

1. The support agent calls `billing`, which is tagged `finance`.
2. The finance desk listens for that topic `asked-first`, so the call is held
   and the finance desk is asked. What it says comes back in place of the
   tool's answer.
3. The support agent makes the call again. Now the approval policy applies and
   a person is asked — once, about a call that will actually happen.
4. The refund goes out. The auditor is told.

## What is refused, and why

| Rule | Fires when |
|---|---|
| `loader/a-signal-says-one-thing` | a reaction waits for nothing, or for two different things |
| `loader/a-guess-cannot-stop` | `stop:` on a judgement, or on a topic the agent or a judge notices |
| `loader/a-narrowing-with-nothing-to-narrow` | `when-this:` at a moment that is not about a call |
| `loader/a-signal-names-no-such-call` | `when-this:` names a tool or an action the workspace does not have |
| `loader/a-judge-reads-words` | `judged: yes` at a moment that carries no words |
| `loader/asks-only-itself` | a reaction an agent names does nothing except wake that same agent |
| `loader/a-tag-nobody-reads` | something is tagged with a topic whose `noticed-by:` leaves out `tags` |

**An agent that is asked or told can leak what the first one read.** What one
agent read is put in front of the other, so `pact check` follows `consult:`,
`tell:` and `listens-for:` the way it follows `team:` when it looks for an
agent that reaches private data, a stranger's words and a way out
(`loader/three-things-that-make-a-leak`).

**A guess may advise and may not stop.** A judgement can be wrong and an agent
can forget to say what it is working on. A run that is stopped only when a
guess is right is not guarded, so `stop:` is written on something exact — a
moment, or a tag — and a guess gets `remind:` or `consult:`.

Two more are held while a run is going, because they are about a run:

- **A reaction does not wake itself.** While one is being carried out it does
  not fire again — in the consulted agent's run, or beneath it. However agents
  consult each other, that ends.
- **A consulted agent is paid from the same budget.** What it costs is charged
  to the limits of the run that woke it.

## What each runtime does

The Python harness carries all of this out. The TypeScript port does not: it
offers the `working-on` tool so both show the model the same tools, and names
every reaction it did not carry out on `RunResult.unenforced`. With nothing to
run another agent, or no model to judge with, the Python harness says the same
way what it could not do.
