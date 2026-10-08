# Changelog

What changed in PACT, newest first. Each entry says what an author can now write, or what now
holds that did not; the commits are listed under it for whoever wants the detail.

## 2026-10 — production on Pydantic AI (the Bud Agent Flow round)

Running PACT trees in production on Pydantic AI 2.54, through
[Bud Agent Flow](https://github.com/BudEcosystem/Bud-Agent-Flow), drove these changes. Every
addition is checked by `pact check` (Rust) and held by the Python harness, and the whole suite
runs offline: 3513 tests, 1139 Rust and 2374 adapter.

### New in the spec

- **Values known only at run time.** `{{run-inputs.<name>}}` and `{{remembers.<name>}}` may
  appear in an agent's `instructions:` and `help:`; the surrounding system fills them before the
  model reads the words. A hole naming nothing the agent declares is refused; `\{{...}}` keeps
  braces meant for the model, and braces that are nearly a hole get a warning.
- **Fallback models.** `model:` takes an ordered list; the next model is tried only when a call
  fails at the provider (never because an answer was wrong). Each model in the list is held to
  `allow-egress:` and `needs:` exactly as a single one is.
- **Answers checked before they count.** `checked-by:` holds a live answer to the same rule shapes
  as `evals:` (`must-contain:`, `must-not-contain:`, `must-say-one-of:`, `must-call-before:`,
  `judged:`); a failed check asks again with the reason, up to `checks-at-most:` attempts
  (default 2), then the run stops and names the rule.
- **Typed action results.** An action may say what it hands back with `answers-with:`, in the
  same shapes as an agent's answer. On an action that runs a `program:`, the two must agree.
- **Governed run-time composition.** `teamwork.may-start:` (`catalogue`, `narrowed-new`) lets an
  agent bring in others while it works. `pact check` refuses it without `limits.starts-at-most:`
  and `limits.nests-at-most:`; each start is journaled, counted across levels and paid from the
  request's pot, and nothing it starts is written into the tree.
- **Schedules.** A port's `every:` is held to one grammar where it is written, and an hour is
  never guessed; a port and its clock are read once, the same way, by every runtime.
- **Program bodies.** A `python` body is one `.py` file given `inputs` (keyed by `takes:`) whose
  last line is the answer; a `wasm` body reads its inputs as one JSON object on standard input and
  writes its answer as one on standard output. A host is handed everything it needs to run one.
- **Learning.** A cycle can be scored by the host's own runner from a kept baseline; "held for a
  person" is its own outcome; what a host hands the grader reaches the measurement it is for.
- **`feel:`** is a latency band a report measures against. It stops nothing; a run is stopped by
  a line with a figure on it.

### Held more tightly

- Nobody is asked to approve a call that at-most-once would refuse anyway.
- An amount nothing can read as a figure stops at the gate.
- A card number written with no-break spaces or dots between its groups is redacted too.
- A value written without a dash is one value, not its letters.
- A sentence is not something that was sent; an answer is checked before it is the answer.
- A deadline can be applied by a runtime that replays a journal.

### The Python adapters

- Run on **Pydantic AI 2.54**, import none of its private names, and never hand it a ceiling
  nobody wrote.
- One table, `pydantic_ai_registry.yaml`, says what every field becomes in Pydantic AI, and a loss
  row says who holds the line instead.
- The core installs with three packages (`pydantic-ai-slim`, `pyyaml`, `httpx`); every other
  framework is an extra. The catalogue and the schema travel with the package, and the loader
  binary is found one way by every command (`PACT_BIN`, then `pact` on the `PATH`, then the
  checkout's own build).

### Commits

- a card number parted by no-break spaces or dots is hidden too (5b53777)
- docs: the test counts are the counts (1139 Rust, 2370 adapter) (6578dd3)
- the test for an approved refund sent again now fails without the look (da506bc)
- what the branch added is held by a test, and three documents say what the code does (8b58ef6)
- `every:` is held to one grammar where it is written, and an hour is never guessed (2aa5da4)
- its own harness says what it does not hold, and its own builder holds what it was skipping (18d9d72)
- braces a model is meant to read, braces that are nearly a hole, and a variant's holes (c2ea8bc)
- the build made last answers, no private Pydantic AI name is imported, and a gate that cannot run the second port stops (f3e108b)
- an amount nothing can read as a figure stops at the gate (2b27eb2)
- the catalogue and the schema travel with the package (ae794e5)
- the mutation test breaks a copy, never the source other processes import (0f379b6)
- nobody is asked to approve a call at-most-once will refuse (257ea1e)
- `feel:` is a latency band, and stops nothing (640aed1)
- a value written without a dash is one value, not its letters (923be88)
- the Pydantic AI table says what budflow builds, and a loss row says who holds the line (e214203)
- a sentence is not something that was sent (ed471e0)
- held for a person is its own answer on a learning Outcome (2e5951c)
- the learning record is read from where it is written (5e11cdb)
- a port and its clock, read once for every runtime (0205d5f)
- a learning cycle a host scores with its own runner, from a kept baseline (800136c)
- what a host hands the grader reaches the measurement it is for (84dabab)
- governed run-time composition (may-start), and one place a grant becomes a member's ceiling (5f0f88e)
- an agent's answer is checked before it is the answer; a variant holds what it says (7bfef1c)
- a pinned server's schema is read by its current name (c3e47a1)
- what an agent is offered and what it can be sent cross the ir wall (c00f122)
- which stage runs now is the loop's own public answer (Loop.stage_to_run) (711d653)
- a projection is what the model reads, and the whole answer is metadata (1e9f70d)
- a keep-going answer grants every ceiling again, and feel: is a wall clock a runtime can hold (8fcf54a)
- a host is handed everything it needs to run a carried program (1a20541)
- a summary a runtime awaits, the one summary text, a watch line written without a bus (a34c6c6)
- memory terms ride on Fact, a run's own Facts, and a pure at-most-once claim (cbb195f)
- a deadline can be applied by a runtime that replays a journal (f54afb1)
- docs: KNOWN-ON-2.54 gives the suite's count now, beside the one at the move (c882edf)
- a bare `{{brand}}` the agent declares is told the one hole it means (32cb4b8)
- the importers' and the exporter's field words live in the registry too (2f4d48b)
- three Phase 1 test files sort their imports (d2007da)
- A1, A2 and A4 reach a live model on Pydantic AI 2.54 (d933476)
- a ceiling nobody wrote is not handed to Pydantic AI (4d9810f)
- the adapters run on Pydantic AI 2.54 (a45fbbf)
- the core installs with three packages; every framework is an extra (51166ad)
- one table says what each field becomes in Pydantic AI (02P §4) (ffe6111)
- an action may say what it hands back (A4) (954837f)
- `model:` may name fallbacks, each held to the same lines (A2) (bbedf39)
- a value only known when a run starts has a place in the words (A1) (c6c773e)
- the loader binary is found one way, by every command (5b8df06)
