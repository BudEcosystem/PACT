# Refund Desk — a worked example

This folder is a complete multi-agent system: a supervisor (`Refund Desk`) and
two specialists, with their own tools, a written policy, a set of checks, and
learning switched on.

**There is nothing here you have to write code to say.** Every setting in it is
YAML or Markdown. The one file that is neither —
`skills/refund-policy/scripts/check_window.py` — rides along inside the skill,
the way a printed policy comes with a ready-reckoner: it is material the policy
points at, not a setting, and the desk works the same with it deleted. That is
the point: decision D14 says a non-technical domain expert must be able to build
exactly this, and this folder is the acid test for whether the format delivers.

Try it:

```bash
cargo run -p pact-cli -- check examples/refund-desk
cargo run -p pact-cli -- show  examples/refund-desk | head -40
```

## Does it pass?

`check` says the folder is written correctly. This says whether the desk is
actually getting the answers right, against the examples in `evals/` and the bar
in `evals/suite.yaml`:

```bash
./scripts/pact-eval examples/refund-desk
```

You get a verdict — **PASS**, **FAIL**, or **UNDECIDED** when there was not
enough to decide on — the score against your own `must-pass:` line, every example
that came out wrong and why, a separate verdict for the ones that moved money,
and every rule you wrote that nothing was able to apply. That last part matters:
a green score never means every rule was checked, so the ones that were not are
printed underneath it.

It needs a model, and it will only use one that is running on this machine —
`workspace.yaml` says nothing here may talk to anything outside the box, and that
holds for scoring too. If the model is not running, you get UNDECIDED and the
line to type, never a score. If your model is served somewhere other than the
usual place, say so:

```bash
./scripts/pact-eval examples/refund-desk --serving-at http://localhost:8000/v1
```

That command is a small wrapper around the eval runner, which lives in the
Python adapter because that is the port that runs models. If you would rather
call it directly:

```bash
PYTHONPATH=adapters/python/src python -m pact_adapters.evals examples/refund-desk --help
```

## What each file is for

| File | What it says |
|---|---|
| `workspace.yaml` | What this whole system is called. |
| `agents/refund-desk/agent.yaml` | The main agent: who it works with, what it can use. |
| `agents/refund-desk/instructions.md` | What it should actually do, in plain words. |
| `agents/refund-desk/needs.yaml` | What the AI model behind it has to be capable of. |
| `agents/refund-desk/limits.yaml` | How fast and how cheap it has to be. |
| `agents/refund-desk/teamwork.yaml` | How it waits for the two specialists, and how the money is divided between them. |
| `agents/refund-desk/run-inputs.yaml` | What the ticketing system hands it at the start, which nothing in the conversation may change. |
| `agents/policy-checker/`, `agents/fraud-checker/` | The two specialists. |
| `tools/*.yaml` | The outside systems it can reach, and what needs approval. |
| `resources/*.yaml` | Where each of those systems actually is, and which stored login gets in. |
| `policies/approvals.yaml` | When a person has to be asked, and which question to put. |
| `redaction.yaml` | What must never leave this system inside a saved example or a report. One for the whole workspace, so no agent can opt out by deleting a line — and nothing points at it, the same way nothing points at `learning.yaml`. |
| `questions/*.yaml` | What a person is asked, and what counts as an answer. |
| `loops/careful.yaml` | The shape of its thinking: look things up, read the decision back against the policy, then reply. |
| `context-policies/long-threads.yaml` | What to keep and what to shorten when a conversation gets too long to send. |
| `interceptors/*.yaml` | Rules that change what happens as it runs: hiding card numbers, and stopping a second refund. |
| `watch/tool-calls.yaml` | Writes down every tool call as it finishes, so afterwards you can read what it did. |
| `skills/refund-policy/SKILL.md` | The written policy it follows. |
| `skills/refund-policy/references/window-table.md` | The refund windows as a table, read only when it is needed. |
| `skills/refund-policy/scripts/check_window.py` | A small helper the policy can run to work out whether a purchase is still in time. |
| `ports/*.yaml` | Where requests come in from: the Slack channel and the support mailbox. |
| `ports/weekly-review.yaml` | A standing job — every Friday, summarise the week's decisions for the team. The clock is a port whose `kind:` is `schedule`, not a kind of its own. |
| `evals/` | How we know it works. The bar, the rules, and the examples. |
| `learning.yaml` | What it may improve by itself, and what needs a person. |

A skill is a folder, not a file. `SKILL.md` is the policy itself, kept short
enough to read in one go; anything long or fiddly sits beside it in
`references/` and `scripts/`, which are opened only when they are needed.

## Asking a person is not a special case

Look at `questions/`. `is-this-ok.yaml` asks for one yes-or-no — that is what
everyone else calls an approval. `how-much-to-refund.yaml`, right next to it,
asks for an **amount**, and `keep-going.yaml` asks whether to spend more time.
All three are the same kind of file and travel the same path.

That matters because the alternative is what every other framework does: build
approval as two fixed options named approve and deny, then discover that "how
much?" and "keep going?" do not fit, and dress them up as approvals anyway.

## The one rule that makes this work

**A folder is a setting; a setting can be a folder.**

`agents/refund-desk/instructions.md` and an `instructions:` line inside
`agent.yaml` mean exactly the same thing. Start with one file; split it up when
it gets long. Nothing else changes.

> **Draft.** The field names here are a proposal being pressure-tested by the
> architecture workflow. The *structure* — one rule, no code, plain language —
> is settled.
