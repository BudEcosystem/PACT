# F3 — Doing the same thing to each of N things. **Refused.**

**The decision: fan-out stays a list of names an author typed. There is no `map`,
and there will not be one until something else supplies the collection.**

---

## What cannot be written

*"For each of the forty documents this search returned, pull out the dates and
bring them back."*

**Fan-out is a `team:`, and a `team:` is names in a file.** `spec/schema.yaml`:

```yaml
team:
  type: map of text
  key-names: agents
```

Each key is an agent that must have a folder under `agents/`. So the width of a
fan-out is decided when somebody types it, and every branch is a *different*
agent rather than the same one over a different item. `examples/patterns/swarm/`
and `examples/patterns/quorum/` are both this shape: three named members,
written out.

**And the budget is sized before anyone answers.**
`adapters/python/src/pact_adapters/delegation.py`:

```python
def share_of(self, member: str) -> float:
    ...
    return self.total / max(1, len(self.members))
```

`Pool` takes `members` at construction and `divides-the-budget: evenly` divides
by that count. `by-share` is worse for this: its help says *"Everyone under
`team:` needs a line here, or nothing will run"* — a percentage per name, typed.
A collection whose size is not known until a tool comes back has no share to be
given.

## What it would take

Three things, and only the first is small.

1. **A collection with a runtime size.** Nothing in the format has one.
   `answers-with:`'s `list of images` and friends are *aliases for the scalar
   shapes* — `Shape.written()` round-trips `list of images` → `images`
   non-injectively (`docs/95-FIX-PLAN.md`'s **A4** row, measured) — so there is
   not even a list type to hold the forty documents in.
2. **Somewhere for it to come from**, which is a tool's return value, and
   nothing carries a tool's return anywhere an author can name. That is **F1's**
   missing primitive, arriving again.
3. **A budget policy that can be decided after the size is known.** `as-needed`
   is the only one of the three that survives an unknown count, and it survives
   by setting nothing aside at all — so a forty-item fan-out under `evenly` is
   either forty shares of a budget written for three, or no reservation at all.
   Neither is a decision the author made.

## What it collides with

**D14, at the point where it stops being a list.** A named team is readable by
somebody who cannot write code: three lines, three folders, three sets of
instructions you can open. `for each <thing> in <the result of a tool>` is a
loop with a bound variable, and a bound variable is the thing that makes YAML
into a programming language. The register's AC-3.2 row settled the same question
for comparisons and the reasoning transfers: *"an expression language is a
language, with precedence and parentheses, which is the one thing a non-coder
must never have to learn."*

**And the depth price in `docs/00-THESIS.md` §7.3 is against it on the
evidence.** `Acc(N,K) ≈ (a − b ln N)^{γK}` with `γ > 1`: a K-step pipeline scores
*below* K independent draws, and worse as the executor weakens. Fan-out over
forty items is forty draws that then have to be folded, and the fold is the
step that is priced super-multiplicatively.

## The price

**Deep research cannot be written**, and `docs/93-GAPS.md` A.0 already records
that in one line — *"deep research ❌ needs fan-out over a work-list"*. So can
nothing that processes a batch: forty documents, a queue of tickets, every row of
a report.

What an author does instead:

1. **Name them.** If the collection is known and small — three readers, four
   regions — write them out. This is the case the format is for, and it is a
   larger fraction of real work than it sounds.
2. **Put the loop inside one MCP tool.** The tool takes the forty documents and
   returns forty answers. This works today and it is the answer PACT's own gap
   register gives (*"buildable as an MCP tool, governed by nothing"*) — and the
   second half of that sentence is the price. Every ceiling, every gate, every
   redaction and every watch is at the PACT boundary, so a fan-out that happens
   inside a tool spends money PACT never metered, calls models PACT never
   chose, and writes nothing to `.pact/`. The `pact show` document does not
   contain the agent's actual shape. **That is the specification's central claim
   — *everything the system does is in the folder you were handed* — failing for
   an entire class of agent.**
3. **Run the workspace forty times from outside.** Correct, cheap, and it makes
   the forty runs independent, which is often what was wanted. What it cannot do
   is fold them: the combining step is outside PACT too.

**The residue worth stating: the third option is better than it looks and is
not written down anywhere an author would find it.** `answer-more-than-once`'s
own file already says *"If you need real independence, run the agent three times
from the outside and compare"*, and no equivalent sentence exists for fan-out.
If this refusal stands — and it should — that sentence belongs in `team:`'s help.
