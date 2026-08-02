# Your first agent

Three files, five minutes. Every command here was run to produce the output
shown.

## 1. Make a workspace

```bash
mkdir -p hello/agents/greeter && cd hello
```

```yaml title="workspace.yaml"
name: Hello world
```

## 2. Write the agent

```yaml title="agents/greeter/agent.yaml"
name: Greeter
description: Answers questions concisely.
```

```markdown title="agents/greeter/instructions.md"
Be brief. Say when you are unsure rather than guessing.
```

## 3. Check it

```console
$ pact check .
OK — . loaded cleanly (7 settings).
```

That's an agent. No registration, no build, no `id` field — **the folder name is
the name**.

---

## Get it wrong on purpose

This is the part worth trying, because it is the part the whole format is
designed around. Misspell something:

```yaml title="agents/greeter/agent.yaml"
name: Greeter
descriptoin: Answers questions concisely.
```

```console
$ pact check .
error: 'descriptoin' is not something an agent can have.
  fix: Did you mean 'description'?
```

Now delete `instructions.md` entirely:

```console
$ pact check .
error: An agent must have 'instructions'.
  fix: Add a line: `instructions: ...` — what it should actually do, in plain
       words. That line can go in `agent.yaml`, or the same words can go in
       `agents/<name>/instructions.md` beside it — the two mean exactly the
       same thing, so write it in whichever file you already have open. Once
       it runs past a paragraph, the separate file is the usual place.
```

Read that fix again: it does not just name the missing field, it tells you the
**two places it can live and that they are equivalent**. That is the
[Expansion Rule](../concepts/expansion-rule.md) surfacing itself at the moment
you need it, rather than in documentation you were supposed to have read.

---

## What to add next

| You want to… | Read |
|---|---|
| let it call something | [Adding a tool](tools.md) |
| make a person approve an action | [Gating an action](approvals.md) |
| know whether it actually works | [Evals and scoring](evals.md) |
| change how it thinks | [The harness](../concepts/harness.md) |

## See a complete one

```bash
pact check examples/refund-desk
pact show  examples/refund-desk | head -40
```

43 files: a supervisor, two specialists, MCP tools, a written policy, an eval
suite, a learning policy — and no code.
