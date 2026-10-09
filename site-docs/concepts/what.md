# What you write

Files. That's the whole answer — but it's worth seeing a real one.

---

## The smallest agent that loads

Three files. Verified by building this exact tree and running `pact check` on it
— it reports `loaded cleanly (7 settings)`:

```
workspace.yaml
agents/hello/agent.yaml
agents/hello/instructions.md
```

```yaml title="workspace.yaml"
name: Hello world
```

```yaml title="agents/hello/agent.yaml"
name: Hello
description: Answers questions concisely.
```

```markdown title="agents/hello/instructions.md"
Be brief. Say when you are unsure.
```

There is no `id`, no `version`, no registration step. **The folder name is the
name.**

!!! tip "`instructions.md` is not a third concept"
    Drop it and `pact check` says: *"That line can go in `agent.yaml`, or the
    same words can go in `agents/<name>/instructions.md` beside it — the two mean
    exactly the same thing, so write it in whichever file you already have
    open."* That is the [Expansion Rule](expansion-rule.md) talking. Two files
    or three, your choice; the loaded document is identical.

---

## A real one

This is the worked example that ships in the repository — 43 files, 498
settings, and nothing you have to write code for. One of the 43 *is* code —
`skills/refund-policy/scripts/check_window.py`, six lines, a payload the
skill carries — and it is here to show that a skill may bring one, not
because anything needs it:

```
agents/
  refund-desk/          agent.yaml  instructions.md  limits.yaml
                        needs.yaml  teamwork.yaml    run-inputs.yaml
  policy-checker/       agent.yaml  instructions.md
  fraud-checker/        agent.yaml  instructions.md
tools/                  zendesk.yaml  payments.yaml
skills/                 refund-policy/…
policies/               approvals.yaml          ← when a person must be asked
questions/              is-this-ok.yaml  how-much-to-refund.yaml
interceptors/           redact-card-numbers.yaml  stop-runaway-refunds.yaml
loops/                  careful.yaml            ← how this agent thinks
context-policies/       long-threads.yaml       ← what to do when it overflows
ports/                  slack.yaml  email.yaml  weekly-review.yaml
evals/                  suite.yaml  cases/01…06
learning.yaml
workspace.yaml
```

The agent file reads like this — the comments are from the real file:

```yaml title="agents/refund-desk/agent.yaml"
name: Refund Desk
description: Decides whether a customer's refund request should be approved.

# Who helps with this work, and what each of them is for.
team:
  policy-checker: Checks the request against our written refund policy.
  fraud-checker: Looks for signs the request is not genuine.

# What this agent is allowed to use.
uses:
  - zendesk
  - payments
  - refund-policy
```

Notice what is *not* there: no imports, no wiring, no registry. `team:` names
folders. `uses:` names tools. `pact check` refuses a name with no folder behind
it — so a typo is caught where you typed it, not at 3am in production.

---

## The shape of a definition

Every kind follows the same pattern, which is why 44 of them is not 44 things to
learn:

```yaml
description: what this is, in one line     # every kind has this
<the two or three fields that kind needs>
```

And every field carries three things the schema enforces:

- **`help:`** — one line explaining it to somebody who cannot write code
- **`surface:`** — which governance class it belongs to
- **`tier:`** — `core` (you'll need it) or `expert` (you probably won't)

A field with no `help:` cannot exist: the CLI refuses to validate against a
specification that leaves one out, because nothing could then tell an author what
they were being asked for.

---

## When you get it wrong

The whole format is designed around this moment. Every diagnostic names the
file, the line, what is wrong, **and a fix you can type**:

```
error: 'loop' names 'carefull', and there is no such entry in `loops:`.
  --> agents/refund-desk/agent.yaml:36:7
   |
36 | loop: carefull
   |       ^^^^^^^^
  fix: Change it to one of: careful, pact:loop/answer-more-than-once, pact:loop/plan-then-do, pact:loop/react, pact:loop/reflexion, pact:loop/standard, pact:loop/tree-of-thought — or add a file `loops/nonsense.yaml`.
       — or add a file `loops/carefull.yaml`.
  rule: schema/no-such-name
```

That is not a special case for loops. **52 fields** declare what they name, and
the same machinery produces the same shape of message for all of them.

---

**Next:** [The Expansion Rule](expansion-rule.md), or jump to
[Your first agent](../guide/first-agent.md).
