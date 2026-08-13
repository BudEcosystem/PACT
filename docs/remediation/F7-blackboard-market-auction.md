# F7 — Blackboard, market, auction. **Refused, and the existing verdict stands.**

**The decision: no shared writable medium between agents, no round structure, no
bid, no settlement.** AC-5.1 should be amended rather than satisfied.

---

## The verdict this document is defending

`docs/70-PRODUCTION-GAP-REGISTER.md`, the AC-5.1 row, verbatim:

> **`blackboard`, `market` and `auction` are absent and cannot be built on
> today's primitives**: `blackboard` needs a store agents read and write between
> turns; the other two need bidding and a settlement rule. `teamwork:` is a
> *waiting* vocabulary. Inventing shared mutable state between agents to satisfy
> a criterion would be the largest design change in the system made for the
> smallest reason — so this AC needs either those primitives designed on their
> merits, or amending.

That is right, it survives review, and this document adds the measurements
behind it and the price.

## What cannot be written, measured

**There is nothing an agent can write that another agent can read.** The only
channel between two members of a team is `Grant.so_far`, and it fails as a
medium in four separate ways —
`adapters/python/src/pact_adapters/delegation.py`:

```python
#: What earlier members said. Empty under `all-at-once` — nobody has
#: finished yet — and the whole point of `one-after-another`.
self.so_far = so_far
```

That is the field's whole life: a tuple handed in at construction, assigned
once, never appended to. `grep -n 'so_far' delegation.py` finds no second
assignment.

1. **It is read-only.** A `Grant` has `spend()` and no writer for `so_far`. A
   member cannot post anything; it can only be handed what already arrived.
2. **It is empty in the shape that would need it.** Under
   `starts: all-at-once` — the default, and what `swarm/` and `quorum/` use —
   nobody has finished when the members start, so every member's `so_far` is
   `()`. The field's own comment says so: *"Empty under `all-at-once` — nobody
   has finished yet."*
3. **It is strictly ordered when it is not empty.** `_one_after_another` builds
   it from `asked` in order, so member three reads members one and two and
   member one reads nothing, forever. A blackboard is precisely the structure
   where that is not true.
4. **It is prose.** `harness.py:2900` renders it as
   `f"{a.member} said: {a.text}"` into the next member's prompt. There is no
   claim, no key, no type — so two members cannot even be said to be working on
   *the same item*, which is the thing a blackboard coordinates.

And there is no round: `teamwork:` says who to wait for
(`waits-for`/`enough-is`/`gives-up-after`), when to start
(`starts`), how to divide money (`divides-the-budget`/`shares`) and what happens
on failure (`if-someone-fails`). Six settings, all about **waiting**. Nothing
says *do this again with what you now know*.

For a market, three more things are missing outright and none has any analogue:
a **bid** (a type carrying a price and a claim), a **settlement rule** (who
won, at what price, binding on whom), and an **allocation** that is not the
budget split typed in the file.

## What it would take

**A blackboard needs a store with a claim discipline.** Not a key-value bag —
`docs/95-FIX-PLAN.md`'s open question **Q8** already worked out why: *"there is
no observable type
meaning 'this is a scarce resource', so the exactly-once machinery stays keyed
to the word `money`"*, and B13 is deferred with a fixture for that reason. A
board where two workers can take the same item and both act is worse than no
board.

**A market needs the participants to be able to price themselves**, and
`docs/93-GAPS.md` §0 records the measurement that decides it:

> self-assessment is the bottleneck, not plumbing — LLMs are miscalibrated on
> both their own success probability and their own token cost

## What it collides with

**The bid collides with the evidence, not with a decision.** That is why the
market refusal is free: the plumbing is buildable and the bids would be noise.

**The blackboard collides with `Pool`, with D14 and with the digest.** `Pool`
sizes every member's allowance from a fixed `members` tuple before anyone
answers, so an agent that claims more work mid-round has no budget to claim it
from (see **F3**). A board is state that is not in the folder, which is the
Expansion Rule's premise. And a claim discipline is a lease, a lease is a
timeout, and a timeout on a shared resource is distributed-systems machinery
sitting under a format whose bar is a support lead editing YAML.

## The price

**For market and auction: none.** `docs/93-GAPS.md` §0 already prices this row
*"none. This one is free"*, and nothing found since disturbs it. What the
refusal costs is a criterion — AC-5.1 names both by name — and criteria are
amendable where evidence is not.

**For the blackboard, the price is real and it is one number.**
`docs/90-REVIEW.md` measures the pattern this refusal gives up:

> Gap-directed fan-out over a claimable evidence board (Argus) — **+12.7 pts at
> 8 workers**; 86.2% BrowseComp at 64, orchestrator context **under 21.5K
> tokens**.

That row is worth more than the others in the same table for two reasons the
review states: it is the largest measured gain of the group, and it now has a
**published, benchmarked reference implementation** — so unlike the market, this
is a refusal against something that demonstrably works. The 21.5K figure is the
sharper part: a claimable board is how the orchestrator's context stays small,
and keeping the orchestrator small is `docs/90-REVIEW.md` §G3's other measured
finding (orchestrator-only thinking: **+18.2 GAIA, +36.7 AIME**; sub-agent
thinking **null-to-harmful**). We are
refusing a mechanism that buys accuracy *and* the context discipline this
project needs most on small models.

**And the workaround is governed by nothing**, which is the second half of the
price and the same one **F3** pays. `docs/93-GAPS.md` A.0 records it in the
coverage table: *"blackboard / gap-directed fan-out — ❌ buildable as an MCP
tool, **governed by nothing**"*. An author who needs this will build the board
behind `connect:`, and every ceiling, gate, redaction and watch stops at the
PACT boundary.

**What is owed instead of the primitives: the amendment.** AC-5.1 asks for eight
orchestration patterns *including* blackboard, market and auction, and eight
ship without them. The criterion should be restated to what the evidence
supports — eight patterns, with the three named ones refused and priced here —
rather than left as a row that reads like undone work. That is the same shape
`docs/remediation/C8-profiles.md` took for AC-7.2 and it is owed for the same
reason: a criterion nobody intends to meet is an open item that never closes.
