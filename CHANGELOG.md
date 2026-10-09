# Changelog

What changed in PACT, newest first. Each entry says what an author can now write, or what now
holds that did not; the commits are listed under it for whoever wants the detail.

## 2026-10 — production on Pydantic AI (the Bud Agent Flow round)

Running PACT trees in production on Pydantic AI 2.54, through
[Bud Agent Flow](https://github.com/BudEcosystem/Bud-Agent-Flow), drove these changes. Every
addition is checked by `pact check` (Rust) and held by the Python harness, and the whole suite
runs offline: 3672 tests, 1175 Rust and 2497 adapter.

### Workflows: a `workflows/` collection and its structure (9 October)

- **A workspace can hold workflows.** `workflows/<name>.yaml` is a collection like `agents/`: a
  stage loop that belongs to no agent, with `accepts:`, `answers-with:`, `starts-at:`, named
  `steps:` and the five new `does:` values `call`, `decide`, `each`, `repeat` and `together`
  (design 02W §2.2, §2.3). A stage's `then:` gains `declined`, `nobody-answered` and `heard`. The
  workspace gains `time-zone:`, `calendar:`, named `shapes:`, shared `remembers:`, `owners:` and
  `release:`; a bundle may bring all of them. Two field types join the schema: `moment` (a length
  of time, or `{at:, after:|before:, counted-in:, in-time-zone:}`) and `combine-rule` (`keep-all`,
  `keep-the-latest`, `merge`, `add-up`, `vote`, `top <n> highest|lowest by <field>`).
- **`pact check` holds a workflow's structure** (`crates/pact-loader/src/workflows.rs`): a workflow
  with a mind of its own (WF-1), a stage that thinks (WF-2) and, the other way round, an agent's
  loop that writes a workflow's stage; a line beside a `does:` it does not belong to (WF-3);
  workflows that call each other in a circle (WF-8); an `each` with no ceiling (WF-10) or whose
  items are told apart by position (WF-11); a `repeat` with no bottom (WF-12); a version of
  something that has none (WF-35); a path that answers nothing (WF-38); a call to a name that is
  not here; and a workflow sharing a name with an agent or a program. Reachability walks a
  workflow and the inside of each `each`, `repeat` and `together`.
- **`forget-after:` is now `kept-for:`.** The old name loads for one more release with the warning
  `loader/forget-after-is-now-kept-for`; `Fact.kept_for` reads either.
- **A `then:` names the stages beside its stage**, never the ones inside it: `names: ^steps`
  resolves to the block the value is written in, then the nearest `steps:` it sits inside.
- **Python reads a workflow as a typed spec**: `ir.WorkflowSpec.from_workflow`, `ir.StageSpec`, `ir.Moment`,
  with the workspace lines a workflow is read under resolved once.

### A rewrite reaches an answer in a shape (9 October)

- **`replace the answer with what <a program> returns` rewrites a structured answer too.** A
  runtime whose agent answers in a shape (`answers-with:`) hands the chain the answer's fields,
  and the program's `takes: content: text` refused them, so the rule left every such answer as
  it was. The chain now hands the program the answer's JSON and reads its reply back as JSON;
  a reply that is not JSON leaves the answer exactly as it was and says so in `unenforced`, as
  any program's failure does (`interceptors._rewritten`).

### The loader as a wheel (9 October)

- **`pip install pact-adapters` brings the `pact` binary.** A new distribution, `pact-loader`
  (`pyproject.toml` at the root, maturin `bin` bindings over `crates/pact-cli`), installs the
  loader into the environment's scripts folder; `pact-adapters` depends on it at exactly its own
  version. Wheels are manylinux 2.28 for x86_64 and aarch64, linked with zig so a newer build
  machine asks for no newer glibc; the source distribution carries `spec/` and
  `models/catalog.yaml`, which the binary compiles in.
- **The loader is found beside the interpreter.** `pact_binary()` looks, after `PACT_BIN`, at a
  checkout's own build, then at the `pact` the wheel installed beside this interpreter (with its
  folder on no `PATH`), then on the `PATH`. A checkout's build now comes before anything on the
  `PATH`: a development environment has the wheel installed too, built from the source as it was
  at the last sync.
- **One script builds and proves what is published.** `scripts/build-wheels.sh` builds the
  wheels and the loader's source distribution, runs `twine check`, builds the loader from its
  source distribution alone, and runs `pact check` from the installed wheels outside the
  checkout. `.github/workflows/wheels.yml` runs it on both architectures and publishes on a tag,
  through PyPI trusted publishing, after the owner approves.

### Review fixes to the parity round (9 October)

- **A collection folder's own file still holds several entries.** `watch/watch.yaml` and
  `tools/tool.yaml` (the folder's name, or the kind the collection holds) are the folder's self
  file again; only a file named after another kind (`tools/catalog.yaml`) is one entry
  (FR-1.1.3 says so now).
- **`model: [a, b]` is a `FallbackModel` on PACT's own Pydantic AI path**:
  `build_agent(spec, models={id: model, ...})` makes the chain from the host's models, in the
  author's order, falling over on a provider error only.
- **The completeness test reads every capability in the installed Pydantic AI**, from its source,
  not only `pydantic_ai.capabilities`: `OpenAICompaction`, `AnthropicCompaction` and
  `BaseDurabilityCapability` have rows now.
- **Each parity row asserts its whole test column**, or `tests/parity/README.md` says why not;
  the export report names each ceiling it cannot carry.
- **A teammate asked twice in one step keeps its answer across a park** for another member that
  failed: the record is keyed by each call's slot.
- **A bank account is hidden only when it passes the IBAN check** (ISO 13616), so a hex digest, a
  dashless UUID or a URL segment that merely starts like one is left alone.

### The parity suite, and five defects the corpus hit (9 October)

- **`tests/parity/`**: one folder per 02P row Phase 1 compiles, each a fixture and an
  `expect.yaml`, run by `adapters/python/tests/test_parity.py`: the import accounts for every key,
  the report a person reads uses plain words, and each row's behaviour holds on PACT's own Pydantic
  AI path. One completeness test fails on any Pydantic AI name the registry has no row for, through
  seven doors (capabilities, `AgentSpec` keys, `ModelSettings` keys, message parts, stream events,
  `ToolDefinition` fields, `GraphBuilder` members). `ImportReport.in_plain_words()` is that report,
  and `pact-import` prints it first.
- **Two calls to one tool in one step are two calls.** The harness kept a step's results and
  refusals keyed by the tool's name, so a cleared call waited while a sibling of the same tool
  waited, and a no to one refused both. They are keyed by the call (`harness.slots_of`).
- **A pattern a bundle contributes is checked as a pattern.** Its `more-than: <limit>` hole was
  refused as a finished rule (`loader/threshold-is-not-a-figure`); it is held to its own
  `expects:` instead, as a workspace's pattern is.
- **`redaction.yaml` can name a social security number**, and a bank account in lower case is a
  bank account.
- **The "not a shape" refusal names only shapes that parse** (it offered descriptions such as
  "an amount of money, like `25.00 USD`").
- **`tools/catalog.yaml` is the tool `catalog`.** A file named after a kind directly in a
  collection's folder was read as the folder's own settings.

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
