# Contract, strategy, substrate

The idea underneath everything else. Three layers, and the whole design follows
from which one a thing belongs to.

## Why separate them

Ask "is this agent portable?" and you get a useless answer, because two
different things are bundled into the question:

- *Must it still refuse refunds outside 30 days?* — **yes, everywhere.**
- *Must it use this exact wording to do so?* — **no.** A smaller model may need
  the rules spelled out differently to reach the same answer.

Bundle those and you get formats that either over-constrain (portable but
useless on a different model) or under-constrain (portable and meaningless).

## The three layers

| Layer | What it is | Travels? |
|---|---|---|
| **Contract** | what the agent must achieve — capabilities, evals, ceilings, policy | **invariant** |
| **Strategy** | how it achieves it — instructions, topology, tools, loop shape | **selected** |
| **Substrate** | what runs it — framework, model, sandbox, transport | **projected** |

### Contract

```yaml title="agents/refund-desk/limits.yaml"
finishes-within: 30s
cost-per-request-under: 0.05 USD
```

Plus `needs.yaml` (capabilities required of any model), `policies/` (when a
person must be asked), and the eval suite. **This is the part that must not
change when you move.**

### Strategy

Instructions, the `loop:` shape, which tools a stage may use, the `variants:`
a resolver may choose between. All of it is *a means*, and a different target
may need a different means to satisfy the same contract.

This is why model portability works at all: the resolver may pick a different
strategy for a 7B model, and the contract is what decides whether it worked.

### Substrate

The framework and model. PACT projects onto it through an adapter that takes the
framework's lowest seam, so the substrate supplies capability, never control
flow.

## What follows from this

**Fail, then recommend.** If no model satisfies the contract, PACT refuses to
bind — and then names the cheapest one that *would* pass. Silently binding a
model that fails the author's own evals would make the contract decorative.

**Evals travel inside the artifact.** They are contract, not tooling. An agent
whose correctness oracle lives in someone's CI is not portable.

**Governance attaches to the contract.** Changing the wording of an instruction
is a strategy change. Changing who must approve a refund is a contract change.
The schema marks which is which on every field, so the difference is mechanical
rather than a matter of opinion.

---

**Next:** [The harness owns the loop](harness.md).
