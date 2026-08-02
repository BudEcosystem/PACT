# Gaps and blockers

The honest list. Ordered by how much it should affect a decision to adopt.

Nothing here is a surprise discovered later — each was found by an adversarial
review pass and written down at the time.

---

## Blockers

Things that would stop a production deployment.

### `bundle.from:` resolves nothing yet

A `bundle` is a named set of definitions a workspace mounts. The kind exists,
the scope check exists, and a bundle contributing a kind outside its `brings:`
is refused — including the supply-chain case where a new version quietly starts
shipping approval rules.

**What is missing:** actually reading another folder into the tree. That is the
host's half and no host in this repository does it.

**Consequence:** you can declare a bundle and be protected from a bad one; you
cannot yet use one to share capabilities between workspaces.

### The human trial has not been run

The claim that a non-programmer can author a working agent is the load-bearing
claim of the whole design. There is a written protocol (`docs/ac-1.5/`). It
needs five non-programmers and a moderator.

**It has not been run.** Until it is, "authorable by a support lead" is a design
intention supported by careful diagnostics, not a measured fact.

---

## Known partial implementations

Real, working, and smaller than they sound.

### The TypeScript port is a subset

It implements the loop, the ceilings, stage routing and the answer shape the
author declared under `answers-with:`, and agrees with the Python harness on all
of them. It does **not** implement interceptors, context policy, approval policy
or teamwork — and reports each on `unenforced` rather than dropping it silently.

This is deliberate: a runtime that silently ignores a governance line is worse
than one that says it cannot honour it. But it means **cross-runtime agreement
covers behaviour, not governance.**

Two things make that claim checkable rather than stated. Keys *inside* a block are
reported too — `limits.feel`, `limits.asks` and the rest were dropped in silence
until each was named. And a field the port does not know **refuses the run**, from
the library and not only from the test driver: for a round that check lived in the
conformance driver alone, so a library consumer got a silent cast.

### Survivable state is Python-only

`survives-shortening:` — the mechanism that stops a conversation summary from
destroying the evidence a policy depends on — lives in the Python harness.

`remembers:` is never put on the wire to the TypeScript port, so it is one of the
keys §7.28 files under *"never arrive"* rather than one reported on `unenforced`.
If it did arrive the port would **refuse to start** and name the field, which is
the right answer for a line that changes what a run is allowed to forget: a
governance key honoured by nobody and reported by nobody is the failure both
behaviours exist to prevent, and refusing is the louder of the two.

### Some ceilings need transport support

`cost-per-request-under` and `tokens-at-most` require the transport to report
usage. A transport that cannot report it leaves those ceilings on `unmetered` —
visible, never silently unenforced. The same applies to `summarised-by`, which
needs a second model binding.

---

## Deferred by choice

Not missing — refused, with the fixture that would let them back in. All are
recorded in `docs/50-NOT-COPIED.md` with reasons.

| Deferred | Why |
|---|---|
| The five privileged built-in tools (`bash`, `read_file`, …) | a portable format that ships a shell is not portable; it is a runtime |
| Model-authored code orchestrating subagents | a spec naming code to run makes `pact check` decide whether that code is safe |
| `runs-as: code` | same reason, arriving through a field instead of a feature |
| A dev TUI | 4,754 lines of terminal rendering is a product, not a specification |

---

## Known imprecision in our own documents

Recorded because a specification that cannot correct itself in public should not
be trusted about anything else.

- **The compaction claim was wrong and was narrowed.** We said Eve's context
  window is "a fixed count of 10". It is token-aware *and* capped at a private
  10 — `min(10, what fits)`. Wrong about the mechanism, right about the ceiling.
- **The approval claim was wrong and was narrowed.** We said Eve defines approval
  as "exactly two options". The *render* has two; the *policy* has four
  outcomes. PACT's advantage is that its outcomes are schema-carrying YAML, not
  that there are more of them.
- **A justification went stale.** The case for total derivation cited two
  near-identical interceptor files. They no longer exist — an earlier change
  merged them by a different route. The mechanism is still right; the example
  that motivated it was fixed another way.
