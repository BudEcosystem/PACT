# F6 — Reflections that outlive the run. **Refused.**

**The decision: a reflection is evidence inside one run and nothing else. There
is no reflection buffer, and improvement across runs stays `learning:` — a
proposed edit to a file, with a person on it.**

---

## What cannot be written

*"Remember what went wrong last time and do not do it again."*

`pact:loop/reflexion` writes a critique and hands it to a second attempt. That
is real and it works, and its reach is one run. `spec/loops/reflexion.yaml`:

> the criticism is not measured against a document, it is the agent's own
> account of what it got wrong, and it is handed back to a second attempt as
> input.

Handed back *within* the loop. The critique is a message in the history;
`at-most: 2` bounds the rounds; the run ends and the history goes with it. The
next customer's run starts from the same instructions and makes the same
mistake.

**Reflexion the technique is defined by the part that is missing.** Its whole
mechanism is an episodic buffer: the reflection text is *persisted* and
*prepended to the next episode*, so an agent that failed a task once carries its
own account of the failure into the retry. What ships here is
self-critique-then-revise, which is one round of that with the buffer removed.

**This is the same finding as F5's, and the AC-5.2 row records it as one.**
`spec/loops/reflexion.yaml` describes what the two stages do and why they are
separate, and never claims the critique goes anywhere afterwards — but it never
says it does not, either, and that is a weaker disclosure than
`spec/loops/tree-of-thought.yaml` and `spec/loops/answer-more-than-once.yaml`
give, both of which name in their own text the thing they are not. So `reflexion`
is a **third approximation** rather than an exception to F5: it implements
Reflexion's mechanism at one trial's depth and it is not the technique whole. F5
enumerates it that way; this file is why it stays that way rather than being
built.

## What it would take

**A store PACT owns, plus a rule for what goes into it and what comes out.**
Three questions, none of which has an obvious answer here:

1. **What is kept.** The critique's text is prose the model wrote. Keeping all
   of it makes the next run's prompt grow without bound; keeping some of it is
   a summariser deciding what an agent believes about itself.
2. **When it is read.** Prepending every past reflection to every run means run
   forty carries thirty-nine self-criticisms, and `docs/00-THESIS.md` §7.3
   measures context bloat as *worse* on small models, which are the models this
   project exists for.
3. **Who reviewed it.** This is the one that decides it, below.

## What it collides with

**D23 and the whole of `learning.py`.** PACT already has a channel for an agent
changing what it does across runs, and it is deliberately not a buffer:

> An agent improves itself by proposing an **edit to a spec file**. Never
> weights, never hidden state, never an opaque adapter — because an agent that
> learns must still be one you can read, review, sign, fork and port.

with three gates — a frozen held-out split, a blast-radius classifier, and
cumulative drift against a baseline — and the finding that justifies them:

> model-authored skills measure **8–11 points below no-skill**, and ungated
> libraries score **below the baseline outright**. Learning without a gate is
> worse than no learning.

A reflection buffer is a model-authored skill with no gate, arriving under a
different name. It is exactly the artifact that measurement is about: text the
model wrote about how it should behave, applied to future runs, that nobody
approved and that does not appear in `pact show`. **An agent whose behaviour
depends on a buffer is not portable** — hand somebody the folder and they get a
different agent, which is T6 and the Expansion Rule's premise both.

## The price

**An agent cannot get better at the same mistake without a person.** Stated
plainly, because that is what the decision buys and it is a real cost:

1. **Every run starts naive.** The same misreading of the same ambiguous policy
   happens to every customer until somebody notices, writes the correction into
   `instructions.md`, and runs `--propose`.
2. **`learning:` is slower by design and needs things a small deployment may not
   have.** The cycle refuses outright when nothing was held out, so a workspace
   with no `split: held-out` cases cannot use the channel at all — and the
   blast-radius classifier holds anything touching tools, permissions or
   decision logic for a person whatever the evals say. That is correct and it
   means the loop closes in days, not in the next request.
3. **The published gains are given up.** GEPA-class reflective evolution is
   `docs/00-THESIS.md` §7.3 mechanism 8 at **+29.3 pp single-benchmark**, and its
   own failure column is the reason this is survivable: *"gain scales with the
   **reflector's** strength"*, and under D17 the reflector is the same small
   air-gapped model that made the mistake.

**And the residue: the machinery to persist already exists, which will make this
look like an oversight.** `.pact/learning/refused.jsonl` keeps a rejected
candidate across processes so it is not proposed twice (AC-5.5), and
`$PACT_DERIVED_DIR` says where the derived area lives. Somebody will reasonably
ask why a reflection cannot go in the same folder. The answer is not that we
cannot write the file. It is that `refused.jsonl` records **what a person
decided**, and a reflection buffer would record **what a model concluded**, and
only one of those may reach a later run unreviewed.
