# Why PACT exists

## The problem

You build an agent on LangGraph. Six months later you need it on Pydantic AI —
a different team, a different deployment, a different set of constraints. Today
that is a rewrite.

It is a rewrite because the industry models an agent as a **program**, and then
tries to translate the program. Programs don't translate. These three encode
genuinely different semantics:

| Framework | What it actually is |
|---|---|
| LangGraph | a checkpointed state machine |
| AutoGen | an actor mailbox |
| Pydantic AI | a typed run |

A translator between them either loses something or invents something. Every
prior "universal agent format" hit this wall, which is why they were lossy.

## The second problem, which is worse

Even if you solve framework portability, you have not solved the expensive one:
**the same agent on a smaller model.**

A prompt tuned against a frontier model does not behave the same on a 7B model
served locally. Teams discover this in production. And because agent behaviour is
probabilistic, there is no type system that can warn you — "it still works" is
not a compile-time property.

## The idea

Model the agent as **two separable things**:

- **A contract about behaviour** — what it must achieve. Capabilities it needs,
  evals it must pass, latency and spend ceilings, the policy about when a person
  must be asked. This is *portable and invariant*.
- **A space of strategies** for satisfying it — instructions, topology, tools,
  the shape of its loop. These are *selected for a target*.

The contract travels. The strategy is chosen. And because behaviour is
probabilistic, fidelity is **measured against the author's own eval suite**
rather than declared.

!!! quote "The closest correct analogy"
    A cost-based query planner. SQL declares *what*; the planner chooses *how*
    against statistics and a cost model. PACT declares the agent's *what*; the
    resolver plans the *how* against a model catalogue and a cost model. Evals
    replace relational algebra as the correctness oracle.

## Why a folder of files

Three reasons, in order of how much they matter.

**A person who cannot write code has to be able to author one.** The worked
example — a supervisor, two specialists, MCP tools, a written policy, an eval
suite — contains no code at all. That is the bar. Any capability that needs a
`.py` to be useful has failed it.

**Files diff, review and version.** An agent's behaviour is a governance
question in most organisations that deploy one. A pull request is the tool that
industry already has for "somebody must approve this change".

**No build step.** The tree you author is the tree that runs. Nothing is
generated, so nothing can drift from what you wrote — and a runtime can index a
workspace without executing anything.

## Who this is for

- **The person who owns the agent's behaviour** — often not an engineer. A
  support-operations lead who needs the refund rules to be right.
- **The engineer who has to run it somewhere specific**, and would rather not
  rewrite it to do so.
- **The organisation that has to answer "who approved this change?"**

---

**Next:** [How it works](how.md) — the three mechanisms that make the above true.
