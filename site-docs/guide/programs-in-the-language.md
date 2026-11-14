# Variables, functions and loops

A [`.pact` file](the-pact-language.md) can be written like a small program.
It has named values, functions that take inputs and give results, loops,
branches and steps that run at the same time.

None of this is new machinery. PACT's checked document already had every one
of these, under other names, and `pact check` already had rules for them. The
language gives them the spelling a programmer expects.

| You want | You write | In the document it is |
|---|---|---|
| a constant | `let refund-limit = 200 USD` | an entry of `values:` |
| a variable | `plan = call planner …`, then `plan.findings` | a workflow stage, and its answer |
| a function | `workflow deliver`, with `takes` and `gives` | a workflow |
| to call one | `call deliver with brief: input.brief` | a stage that `does: call` |
| a template with parameters | `based on desk with domain: billing` | `based-on:` and `with:` |
| a loop over a list | `for each item in input.documents` | a stage that `does: each` |
| a loop until done | `repeat at most 4 times` | a stage that `does: repeat` |
| a branch | `decide`, with `if <label>` beneath | a stage that `does: decide` |
| things at once | `together` | a stage that `does: together` |
| to return | `answer with result: make.result` | a stage that `does: answer` |

## A function: a workflow

A **workflow** is a flow of work that belongs to no single agent: it calls
agents, tools and other workflows, and hands back a result.

```text
workflow deliver
  description: Research a brief, plan from the findings, then build from the plan.
  takes brief: text
  gives result: text

  research = call researcher with brief: input.brief
  plan = call planner with brief: input.brief, findings: research.findings
  make = call builder with plan: plan.plan
  answer with result: make.result
```

- `takes` and `gives` are its inputs and its result, each with a shape.
- Each line beneath is a **statement**: one step. They run in the order
  written.
- `research = …` gives the step a name. That name is the **variable**:
  `research.findings` on the next line is what that step answered.
- `input.brief` is what the workflow was started with.
- `answer with …` is the return.

What is called can be an agent (`researcher`), another workflow, a tool's
action (`billing/issue-refund`), or a program carried in the workspace. An
agent called this way is a function whose body is a model.

## Constants

```text
let large-refund = 200 USD
let messages-at-most = 50
```

A `let` line at the left margin gives a figure a name. Use it in any setting
as `{use: large-refund}`, including inside a sentence:

```text
policy approvals
  before billing/issue-refund, when amount is more than {use: large-refund}: ask may-we-refund, because a large refund is a management decision
```

The loader puts the figure in place before anything is checked, so raising a
limit is one edit. A figure nothing uses is a warning
(`loader/nothing-uses-this-value`).

A constant is fixed when the file is written. It cannot be changed during a
run; what changes during a run is what steps answer.

## A loop over a list

```text
workflow clear-inbox
  description: Route every message in an inbox.
  takes messages: list of message
  gives replies: list of text, optional

  every = for each item in input.messages
    identified-by: [id]
    limits:
      items-at-most: {use: messages-at-most}
      when-it-runs-out: stop-and-say-so
    one = call route with message: item.text, channel: item.channel
  answer with replies: every.reply
```

- The statements indented under `for each` run once for each item.
- Inside, the current item is always called `item`: `item.text`.
- Settings of the loop sit beside those statements. `identified-by:` says
  what makes an item that item, so a repeat is not done twice.
  `items-at-most:` is required: every loop in PACT has a bound.
- After the loop, `every.reply` is every item's reply.
- `call route` calls another workflow. One function calling another needs
  nothing special.

## A loop until something holds

```text
workflow search
  description: Search over ideas until one scores 0.9 or four rounds have run.
  takes problem: text
  gives ideas: list of idea

  rounds = repeat at most 4 times
    until:
      - { value: steps.score.best, more-than: 0.9 }
    remembers:
      frontier:
        description: the best three ideas so far
        lasts: one-run
        comes-from: steps.score.scored
        combines-by: top 3 highest by score
    then: { too-many-times: reply }
    propose = call proposer with frontier: remembers.frontier
    score = call scorer with ideas: propose.ideas
  reply = answer with ideas: rounds.frontier
```

`remembers:` is what carries over from one round to the next, read inside as
`remembers.frontier`. `until:` is checked when each round ends.

## A branch

```text
workflow route
  description: Send one message to the right desk.
  takes message: text, channel: text
  gives reply: text, optional

  where = decide
    by:
      - rules:
          - when:
              - { value: input.channel, is: invoices-mailbox }
            choose: billing
            because: Everything in the invoices mailbox is billing.
      - { agent: sorter }
      - { asks: which-desk }
    if billing
      bill = call billing-desk with message: input.message
      reply-bill = answer with reply: bill.reply
    if tech
      fix = call tech-desk with message: input.message
      reply-fix = answer with reply: fix.reply
    if out-of-scope
      decline = answer
```

`by:` says who decides, tried in order: written rules first, then an agent,
then a person. Each `if` is one label the decision can pick, with the steps
for it beneath. Steps written *after* the whole `decide` block run once the
chosen branch has finished, which is how branches come back together.
`if <label>: done` ends the run for that label.

### What the deciding agent is shown

An agent that decides is given three things, by name: the workflow's input,
the fields of the item it is inside a `for each` of, and whatever the
`decide` hands it with the word a `call` uses. Of those it gets only what it
`takes`.

```text
  triage = call triager with report: input.report
  assign = decide with kind: triage.kind, summary: triage.summary
    by:
      - { agent: assigner }
    if powerplant: done
    if interiors: done
```

`with` is the only way a deciding agent sees what an earlier step found. A
name written there is filled from that place and no other: if `triage` gave
no `kind`, the assigner is given no `kind`, even when the workflow's input
has a field of the same name.

In a loop over plain texts each text is the agent's `message`. An agent that
calls it something else says so: `decide with note: item`.

An agent that runs only on trained classifiers (`kind: decision` in the model
catalogue) is not given the `says:` line. A classifier follows no
instruction; it scores the text, and an instruction in front of the text
would be scored with it.

`pact check` refuses a decision whose agent would be given nothing it takes,
or would be left without something it requires
(`loader/a-deciding-agent-given-nothing`), and tells you what is on offer.

### Who decides, in what order

The rungs under `by:` are tried from the top. The first that decides makes
its label *the standing one*, and the rungs after it are not asked — with one
exception, a second opinion.

| A rung | Decides when | Passes the decision on when |
|---|---|---|
| `rules:` | a rule's conditions all hold | none does |
| `agent:` | it answers one of the labels | it answers `not-sure` |
| `agent:` with `if-unsure-below: 85%` | its score is 85% or more | its score is lower, or it gave none |
| `asks:` | always (it is last) | never |

`if-it-disagrees: go-on` on an agent's rung makes it a **second opinion**: it
is asked even though a rung above has decided.

```text
    by:
      - rules:
          - when:
              - { value: input.folder, is: invoices }
            choose: bills
      - agent: checker
        if-it-disagrees: go-on
      - { asks: which-shelf }
```

- The checker agrees with the rule: `bills` stands and nobody else is asked.
- The checker picks another label, or is not sure: nothing stands, and the
  person is asked.
- No rule held: the checker decides on its own.

Passing on is always to the next rung. A `model:` list on the agent names
fallbacks for a call that *fails*; it is not tried because an answer was
unsure. To have a classifier and then a language model, write two agents on
two rungs. `pact check` warns about one agent that lists both
(`loader/a-rung-with-two-kinds-of-reader`).

Afterwards the step says who decided: `where.label`, `where.decided-by`
(`rules`, `agent` or `person`) and `where.answered-by` (the agent's name, or
the person). Every step also has `.outcome`, the word it ended in, and a
`repeat` has `.rounds` and `.ended` (`passed` or `ran-out`).

A decision is one person's. A question that needs several answers
(`answered-by: everyone`) cannot decide a branch, because nothing says which
label stands when people pick different ones; `pact check` refuses it
(`loader/a-decision-asked-of-several`). Ask them in a step of its own instead:

```text
  approve = ask may-we-close
  reply = answer with close: approve.close, by: approve.answered-by
```

On a step that asks people, `.answered-by` is a list, in the order they
answered, also when one person did.

`answered-by:` on the question counts the names under `asked-of:`. With
`everyone`, each of them is asked and answers on their own, and one "no" is a
no at once. A name there can be a person or a team; a team is answered for by
one of its members, and who that was is what `.answered-by` keeps.

## Things at once

```text
  both = together
    short = call summariser with verdicts: each-document.verdict
    long = call summariser with verdicts: each-document.reason
```

Every statement under `together` starts at the same time.

## A template with parameters

A **base** is an agent that never runs. It exists for others to be made from.
`expects:` lists what it leaves open, and `<domain>` marks where each goes.

```text
agent desk
  description: A desk that answers questions about <domain>.
  base: yes
  expects:
    domain:
      shape: text
    cap:
      shape: money
  spends under <cap> a request
  when it runs out: stop and say so
  instructions
    Answer questions about <domain>, briefly.

agent billing-desk
  based on desk with domain: billing, cap: 0.10 USD
  uses billing

agent tech-desk
  based on desk with domain: technical problems, cap: 0.05 USD
```

Each desk is the base with its blanks filled, plus whatever it adds. One
thing to know: a block the desk restates, such as `limits:`, replaces the
base's whole block, and `pact check` warns when that drops a line
(`loader/restating-a-block-drops-the-rest`).

## How an agent thinks

The same statements describe an agent's own loop: the shape of its thinking.

```text
loop careful
  description: Look things up, then read the decision back before answering.
  gather = use tools
    then:
      used-a-tool: gather
  re-read = check its work
    at-most: 2
    then:
      used-a-tool: re-read
  reply = answer
    then:
      answered: done
```

A step that goes *back*, or to `done`, says so itself with `then:` beneath it,
because no order of lines can say "go back".

## What you cannot write, on purpose

- **No arithmetic and no expressions.** What a step is given is a path to a
  value: `plan.findings`, `input.brief`, `item.id`. Comparisons such as
  `more-than:` live in `when-this:` and `until:` lines.
- **No reassignment.** A name is given once, by the step that answers.

These are the document's rules, not gaps in the language. They are what lets
`pact check` tell you, before anything runs, that a step reads something that
may not have happened yet:

```text
error: 'answer' reads 'steps.nobody.reply', and this workflow has no stage called 'nobody' there.
  --> hello.pact:14:22
   |
14 |   answer with reply: nobody.reply
   |                      ^^^^^^^^^^^^
  fix: Use one of the names offered: `steps.greet`, `steps.answer`.
  rule: loader/a-binding-to-nothing
```

## One workspace, several files

Every `.pact` file at the top of a folder is part of one workspace, so a
larger system is split by subject:

```text
help-centre/
├── help-centre.pact   the workspace, its constants, and how it learns
├── team.pact          the agents
├── tools.pact         tools, questions, the approval policy
└── flows.pact         the workflows
```

```console
$ pact check examples/language/help-centre
OK — examples/language/help-centre loaded cleanly (212 settings).
```

That example uses everything on this page together, plus a reaction and a
`learning` block. Its two workflows are run by a test, through the reference
workflow runtime.

## More

- [The PACT language](../reference/language.md): every statement and rule.
- [When something happens](events-and-reactions.md): reactions, for what
  should happen *while* an agent works.
