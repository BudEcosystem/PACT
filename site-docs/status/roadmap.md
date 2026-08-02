# Roadmap

Ordered by consequence, not by size. Each item states **what it would refuse** —
a construct that refuses nothing is the defect this project keeps finding in
itself, so "what does this now make impossible?" is the acceptance question.

---

## Next

### 1. Run the human trial

Five non-programmers, a moderator, the protocol in `docs/ac-1.5/`. The single
highest-value unbuilt thing, because it tests the claim everything else rests
on.

**Blocked on:** people, not code.

**Would settle:** whether the diagnostics actually work for their intended
reader, or only look as though they do to the people who wrote them.

### 2. Resolve `bundle.from:`

Make a mounted bundle's folder actually load into the tree, so a diagnostic can
point at a line *inside* it.

**Refuses:** a bundle shadowing a workspace's own definition without saying so.

### 3. Carry survivable state into the TypeScript port

**Refuses:** the same thing it refuses in Python — a shortening that destroys the
evidence a policy reads — on the runtime where it currently cannot.

---

## After that

### 4. Close the TypeScript governance gap, or state it permanently

Two honest options, and the choice should be made rather than drifted into:
implement interceptors, context policy, approval policy and teamwork in the TS
port; **or** declare the port a behaviour-only runtime and say so in the
architecture, once, normatively.

What must not happen is the current state persisting silently — where "seven
targets" is true of behaviour and quietly untrue of governance.

### 5. Transport usage reporting across all seven

Until a transport reports usage, `cost-per-request-under` and `tokens-at-most`
land on `unmetered`. Honest, but two of five ceilings are unenforceable in
practice on most targets.

### 6. Multi-agent patterns beyond the tree — *mostly done*

`examples/patterns/` ships eight coordination shapes, each a workspace that
loads and **runs**: quorum, race, pipeline, swarm, weighted, escalation, debate
and first-answer. Every one carries a termination condition, which was the
acceptance question — a pattern whose end cannot be stated is an unbounded
spend.

Three remain, and they are **refused rather than pending**: `blackboard` needs a
store agents read and write between turns, and `market`/`auction` need bidding
and a settlement rule. `teamwork:` is a *waiting* vocabulary — who is asked, how
long for, what happens when one fails. Inventing shared mutable state between
agents to complete a list would be the largest design change in the system made
for the smallest reason.

**Would refuse:** a pattern whose termination cannot be stated — which is now
asserted, not intended: every shipped shape is walked for a path to `done`, and
any two shapes that coordinate identically fail as duplicates.

---

## Explicitly not planned

- **A registry, routing, or multi-tenancy.** These belong to the runtime that
  hosts PACT, not to the format. Keeping them out is what lets a workspace stay
  a folder.
- **A hosted service of any kind.** Air-gapped operation is a hard constraint,
  not a deployment option.
- **Executing author code at load or build time.** This is refused twice over
  and both refusals should be understood as permanent.

---

## How to tell if this roadmap is being followed

Each item lands with a test that fails when the mechanism is removed. That is the
standard the last eight changes were held to — including mutation checks, where
the fix was deliberately reverted to confirm the new test actually caught it.

If an item ships without one, it has not landed; it has been described.
