# Help centre

One workspace in four `.pact` files. It is the example for writing a larger
system in the PACT language: several agents, several workflows, tools,
inheritance, named figures, a reaction, an agent that listens, and learning.

```bash
pact check examples/language/help-centre     # reads all four files as one workspace
pact write examples/language/help-centre     # prints it as one file
```

## The files

| File | Holds |
|---|---|
| `help-centre.pact` | the workspace, two named figures (`let`), and the `learning` block |
| `team.pact` | the agents: a pattern (`desk`), two desks made from it, a sorter, and a finance desk that listens |
| `tools.pact` | a topic, the billing tool tagged with it, two questions, and the approval policy |
| `flows.pact` | two workflows, and the shape of one message |

## What to read, and what it shows

**A constant.** `let large-refund = 200 USD` in `help-centre.pact`. It is used
in `tools.pact`, inside the policy's sentence, as `{use: large-refund}`.

**A template with parameters.** `agent desk` in `team.pact` has `base: yes`,
so it never runs. `expects:` lists what it leaves open, and `<domain>` and
`<cap>` mark where each goes. Then:

```text
agent billing-desk
  based on desk with domain: billing, cap: 0.10 USD
  uses billing
```

**A function with a branch.** `workflow route` in `flows.pact` takes a message
and a channel. `where = decide` picks a label, by a written rule first, then
by asking the `sorter` agent, then by asking a person. Each `if` holds the
steps for one label.

**A variable.** `bill = call billing-desk with message: input.message`, and on
the next line `bill.reply`.

**A loop, and one function calling another.** `workflow clear-inbox` goes
through `input.messages` and calls `route` for each one.

**An agent that listens.** `finance-desk` writes `listens for topic finance:
asked first`. The billing tool is tagged `about finance`, so the finance desk
is consulted before `billing-desk` uses it. Nothing in `billing-desk` names
the finance desk.

**A reaction.** Inside `billing-desk`: `when the agent has taken more than 5
steps`, it is reminded to answer with what it has.

**Learning.** The `learning` block says `enabled: propose-only`: the system
may suggest improvements to itself, a person decides, and nothing changes
until somebody says yes.

## What holds it

- `crates/pact-cli/tests/the_language_and_the_folder_are_one_workspace.rs`
  checks that the four files, the one file `pact write` prints, and the
  folder `pact build` writes from it are the same workspace.
- `adapters/python/tests/test_a_workflow_written_as_statements_runs.py` runs
  both workflows: a message from the invoices mailbox reaches the billing
  desk, the sorter is asked when no rule decides, and `clear-inbox` calls
  `route` once for each message.
