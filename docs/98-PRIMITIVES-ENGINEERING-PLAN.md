# 98 — Engineering plan: the seven primitives, made real

**Date:** 2026-11-10. **Status:** Approved plan, in execution.
**Decisions it carries out** (the four `docs/97-PRIMITIVES.md` §14 put to the
owner, answered the same day):

1. **Change the schema and the checker:** yes, in full.
2. **Law 2's default:** option A. Every cycle is metered, by the author or by
   a default that now reaches every host, and an owner may opt one scope out.
3. **A learnability study with people:** not now.
4. **More checked examples:** the plan's call. It writes one workspace for each
   pattern a new keyword unlocks, and no more (§6).

**What "done" means.** Each of the 16 kernel operations that has no keyword
today gets one, read by the Rust checker and acted on by the Python harness.
Each of the eight laws becomes a checker rule, or a runtime guard where only
the run can see the fact. A reference workflow runtime is built, because three
operations need one and none exists. Every work package passes the repository
gate (`./scripts/test-all.sh`, clippy with `-D warnings`, `cargo fmt --check`)
before the next starts.

---

## 1. What the code says today

Three surveys of the code (2026-11-10) fixed the starting point. Each claim
below is a file and line in this repository.

**The checker.** `spec/schema.yaml` is compiled into the binary
(`crates/pact-cli/src/main.rs:419`). Rules run in one fixed sequence in
`validate()` (`main.rs:1461-1926`). A rule module exposes
`check(document, [schema,] diags)` and pushes `Diagnostic::error | warning |
note` with a literal rule id (`crates/pact-diag/src/lib.rs:166-261`). A
*note* does not fail `--deny-warnings` (`lib.rs:246-253`). A new `S-GOV` or
`S-EXEC` field must be blessed into `tests/golden/schema-fields.txt` with
`PACT_BLESS=1 cargo test -p pact-cli --test nothing_that_already_works_changes`.

**The laws.** None is fully enforced. Pieces of 2, 4 and 6 are strong; 1, 3,
5 and 7 are partial; 8 is absent. One defect: `reachability.rs:531-562`
(`walkable`) gives up on any loop that uses `decided-by:` or `may-go-to:`, so
`loader/stage-nothing-reaches` and `loader/loop-that-never-finishes` are
silently skipped for those loops.

**The harness.**
- **No workflow runtime.** `WorkflowSpec` and `StageSpec` (`ir.py:1659-1873`)
  are read and exported to a pydantic-graph skeleton whose step bodies raise
  `NotImplementedError` (`pydantic_graph_lowering.py:219`). The only
  concurrency is team delegation (`delegation.py:546-741`).
- **Claims are per run.** `Ledger` (`at_most_once.py:262`) is an in-process
  dict; `the-team` and `the-workspace` change only the refusal sentence
  (`at_most_once.py:99-104`). No lease.
- **No shared store between agents** (`docs/remediation/F7-...md`).
- **No fork**: answer-more-than-once shares one conversation (`loops.py:563`).
- **Hiding is one-way**: `[removed]` with no restore (`interceptors.py:1040`).
- **No origin on values**; `never-from` is delegated to the host store.
- **No streaming** (`harness.py:342-397`; `pact_agent.py:1339`).
- **No cancel by reference**; no run ids in the harness.
- **Ceilings reach foreign hosts only when written**:
  `pydantic_ai_interop.py:1320` passes `None` when `steps_written` is false.

**The second port.** TypeScript reports what it does not do rather than doing
it (`harness.ts:201`, `notDoneHere` at 319; architecture §7.28). New agent keys
are declared there and named on `unenforced`.

**The census tests a new field must pass.** `test_every_field_has_a_reader.py`
(a reader in some port, or a `DELEGATED` row), `test_every_value_an_author_may_
type_is_reachable.py` (every closed choice appears in source),
`test_the_loader_to_adapter_boundary_is_total.py`, `test_one_table_says_what_
each_field_becomes.py` (a row in `pydantic_ai_registry.yaml` for agent, tool
and action fields), and the TypeScript key tests in `test_portability.py`.

---

## 2. The keywords

One table, the contract for everything after it. Every keyword is in the
house style: plain words a support lead can read, a closed choice where the
checker must prove something, and a `help:` that says what goes wrong without
it.

| Operation | Keyword | Where | Checker | Harness |
|---|---|---|---|---|
| `store.fork` | `forks: yes` | an `each`, `together` or `repeat` stage; a loop stage | allowed only on those; a fork that writes a spending action needs a claim (law 3) | each branch or attempt starts from a copy of the conversation (agent) or of the run's memory (workflow); nothing it said or wrote survives unless it is the answer or is combined out |
| `store.claim` (team, lease) | `same-request-key-across: the-team \| the-workspace` enforced; `claim-lasts: <duration>` | action | `claim-lasts` needs `same-request-key`; a claim wider than `durability:` is warned | a `ClaimStore` the host supplies, with a file-backed reference store; an expired claim is free again |
| team store | `shared-with: the-team`; `admitted-when:`; `admitted-by:` | a `remembers` entry on an agent with a team | `shared-with` needs a team; `admitted-by` names an agent that answers yes-or-no | members are offered `read` and `write` on it; a write is kept only if every `admitted-when` line holds and the admitting agent says yes |
| `shape.stream` | `stream of <shape>` | any answer shape | parsed, nested, held in conditions | an answer is built only from parts whose kind is `answer`; reasoning and tool-call parts never reach it; a transport that cannot stream yields one part |
| `shape.reference` | the `agent` shape, held | any `agent`-shaped answer | unchanged | a value naming an agent the asker was not granted is refused |
| `shape.digest` | `in-share: <percent>`; approvals bound to the exact request | `when-this` | percent, 0-100 | a stable slice by SHA-256 of the value; a person's yes is recorded with the digest of what they saw, and a call whose arguments differ is asked again |
| `label.propagate` | origins on values | runtime | four `never-from` sources checked statically (law 7) | tool results, retrieved passages, the customer's input and a teammate's answer carry their origin; a memory write refused by `never-from` is refused at run time too |
| `label.placeholder` | `gets-hidden-values: yes` | action | needs `inspects:` or `takes:` | a hidden value becomes `⟦name-n⟧`; the real value is put back only in the arguments of an action that says it gets hidden values |
| `actor.effect` | `effect: reads \| writes \| spends \| cannot-be-undone` | `when-this` | the four words; the action's class is computed | a policy or interceptor can gate on the class; read-only tool calls asked together run together |
| `actor.write-set` | `writes: [<place>, ...]` | action | two branches of one `together`, or one `each`, that may write the same place with no claim are warned | carried into the run record |
| `flow.join` (growing) | `keeps-taking: yes` | an `each` | needs `limits.items-at-most` (law 2) | items added to the `over:` list while it runs are taken too; it ends when the list is quiet and nothing it started is running |
| `flow.cancel` | `does: stop` with `stops: <run>` | a workflow stage | the binding must be a `.run` of a stage that did not wait | the detached run is cancelled and its undo plan runs |
| `check.detector` | `detectors:` | workspace | names resolve where used; patterns compile | `anything that looks like <name>` in redaction and interceptor sentences, and `looks-like: <name>` in `when-this` |
| `check.reachability` | `carries: [private-data, untrusted-content, a-way-out]` | tool | an agent that can reach all three with no person guarding the way out is refused | — |
| `allowance.revoke` | `rests-after: <n failures>`; `rests-for: <duration>` | tool | both or neither | after n failures in a row the tool is withdrawn for the period; asking for it meanwhile is a refusal the model is told about |
| `allowance.value` | `{value: <binding>, at-most: <figure>}` | any figure in `limits:` | the binding resolves; `at-most` is required and fixed | the figure is read when the run starts and never exceeds `at-most` |
| law 2 opt-out | `unbounded: yes` | `limits` | only where the path is listed in `owners:` with `owned-by`; reported as a note | no default ceiling for that scope |

---

## 3. The laws as rules

| Law | New rules (id) | Severity | Built on |
|---|---|---|---|
| 1 Closure | `loader/declared-lighter-than-it-does` — an action `reads-only: yes` whose `program:`/`calls:` writes; effect class (reads < writes < spends < cannot-be-undone) computed for every action, agent, team and workflow and printed by `pact discover` | error | `workflows::writes` (`workflows.rs:612-694`), `money::moves_money` |
| 2 Termination | `loader/unbounded-without-an-owner`; `loader/this-tree-may-not-stop` (note); the workflow call graph gains `team:`, loop `may-use:`, port `then-run:` and reminder `runs:` edges | error, note | `calls_go_round` (`workflows.rs:863-898`), `teams::walk` |
| 2 runtime | every host receives a step ceiling: the author's, or `DEFAULT_STEPS`; `unbounded: yes` is the only way to receive none | — | `ir.py:36`, `pydantic_ai_interop.py:1320` |
| 3 Exactly-once | `loader/repeated-with-no-claim` (an action that cannot be undone, reached inside a retry, `repeat`, `each`, `together`, a fork or a team, with no `same-request-key`); `loader/a-key-that-changes-every-attempt` (the key's binding is produced inside the repeated body); `loader/a-claim-wider-than-what-keeps-it` | error, error, warning | `failures::cannot_be_undone_unasked`, `bindings::Graph` |
| 4 Closed world | `loader/a-stage-may-use-what-the-agent-cannot`; `loader/a-program-may-pick-a-stage-not-listed` | error | `programs.rs`, `reachability.rs` |
| 5 Attenuation | `loader/a-locked-part-changed-below` (`locked: here-and-below` honoured across `based-on:`); `loader/a-helper-allowed-more-than-its-caller` (a teammate's money or step ceiling above its caller's); `loader/a-copy-wider-than-its-template` | error, error, warning | `derive.rs`, `teamwork.rs` |
| 6 Decisions | the `walkable` defect fixed: `may-go-to:` lists are edges, `decided-by:` is not a stage | — | `reachability.rs:531` |
| 7 Origins | `loader/written-from-a-source-it-refuses` (all four `never-from` sources, on `remember-as:` and `comes-from:`); `loader/hidden-from-the-ai-but-handed-to-it`; `loader/a-model-outside-the-region` | error | `approvals.rs:111-185`, `bindings.rs:1083`, the catalogue's `served-by.region` |
| 8 Two phases | a learning proposal and a `narrowed-new` helper are written to a scratch copy of the tree and checked with `pact check` before they take effect | — | `learning.py:359`, `delegation.py:827` |

---

## 4. The reference workflow runtime

A new module, `adapters/python/src/pact_adapters/workflow_runtime.py`, runs a
`WorkflowSpec`. It is the reference semantics, the way `harness.py` is for an
agent. Hosts may keep their own engine; this one is what the tests hold every
engine to.

- **Stages.** `call` (a tool action, an agent through `run()`, a program, a
  workflow), `decide` (rungs: rules through `conditions`, an agent, a person),
  `each`, `together`, `repeat`, `ask-someone` (through `questions.py`),
  `answer`, and the new `stop`.
- **Joining.** `teamwork.waits-for` with the same five meanings as
  `delegation.met_by`; `combines-by` through `combine.py`, which finally gets
  its engine; `if-someone-fails`.
- **Failure.** `if-it-fails` with `use-a-backup`, `carry-on`, `ask-a-person`,
  `undo` (newest first) and `stop-and-say-so`; `at-most` retries.
- **Limits.** The workflow's `limits:` through `limits.Meter`; items ceilings;
  `paused-during`.
- **Memory.** `remembers` with `comes-from` and `combines-by` across rounds of
  a `repeat`.
- **The new operations** that need it: `forks`, `keeps-taking`, `stop`.
- **Run references.** Every detached call returns a `RunRef` the run can stop.

---

## 5. Work packages, in order

Each ends with the gate green. Rust and Python land in the same package, so a
field is never readable by one port and silent in the other.

| WP | Content | Gate adds |
|---|---|---|
| **0** | The census repaired: the seven new pattern workspaces listed where the census looks (`test_the_orchestration_patterns_are_distinct_and_run.py`, roadmap, verified counts); the `build` stage renamed; `owners:` path keys made explodable. | 6 failures to 0 |
| **1** | Law 6 defect and law 4 rules. | 3 Rust tests |
| **2** | Law 1: the effect lattice, `declared-lighter-than-it-does`, `pact discover` prints each part's class. | Rust tests |
| **3** | Law 2: the extended call graph; `limits.unbounded`; the note; the default ceiling reaching every host. | Rust + Python tests |
| **4** | Law 3: the three exactly-once rules. | Rust tests |
| **5** | Law 5: locks across `based-on:`, helpers no wider than callers, copies no wider than templates. | Rust tests |
| **6** | Law 7: the static origin rules. | Rust tests |
| **7** | Store claims across a team and a workspace, with a lease: `ClaimStore`, file-backed reference store, `claim-lasts`. | Rust + Python |
| **8** | The team store: `shared-with`, `admitted-when`, `admitted-by`; read and write offered to members. | Rust + Python |
| **9** | The reference workflow runtime (§4), without the new operations. | Python |
| **10** | `forks` on agent loop stages and workflow stages; `keeps-taking`; `does: stop`. | Rust + Python |
| **11** | Origins at run time and `never-from` enforced; placeholders and `gets-hidden-values`. | Python + Rust |
| **12** | `detectors:`; `effect:` and `in-share:` in `when-this`; approvals bound to the exact request; parallel read-only calls. | Rust + Python |
| **13** | `carries:` and the leak rule; `writes:` and the overlap rule; `rests-after`/`rests-for`. | Rust + Python |
| **14** | `stream of`; answer-kind parts; the `agent` reference held at run time; `allowance.value`. | Rust + Python |
| **15** | Law 8: proposals and new helpers checked before they take effect. | Python |
| **16** | The second port: every new agent key declared and reported on `unenforced`; §7.28 updated. | TS typecheck + parity tests |
| **17** | The examples (§6), `scripts/pattern-coverage.py` moved to "has a keyword" for all 76 operations, `docs/97-PRIMITIVES.md` and the page updated, CHANGELOG, README counts. | full gate |

---

## 6. The examples (decision 4)

One workspace per pattern a new keyword unlocks, each checked by the gate's
"every shipped tree under `--deny-warnings`":

| Workspace | Pattern | Keywords it shows |
|---|---|---|
| `examples/kernel/blackboard/` | Blackboard, judge-gated finding exchange | team store, `admitted-by`, team claim with `claim-lasts` |
| `examples/kernel/self-consistency/` | Independent samples that vote | `forks: yes` on `answer-more-than-once`, `combines-by: vote` |
| `examples/kernel/tree-search/` | Tree-of-Thought with backtracking | `forks: yes` on a `repeat`, a frontier in `remembers` with `top 3` |
| `examples/kernel/circuit-breaker/` | Agent circuit breaker | `rests-after`, `rests-for` |
| `examples/kernel/private-by-placeholder/` | PII tokenisation, credential broker | `detectors:`, `gets-hidden-values` |
| `examples/kernel/canary/` | Canary rollout | `in-share:` |
| `examples/kernel/no-leak/` | Lethal trifecta | `carries:` and the policy that guards the way out |
| `examples/kernel/work-queue/` | Fair-share queue with leases, LLMCompiler | `keeps-taking`, team claim, `claim-lasts`, `stop` |

---

## 7. Risks, said before they happen

- **Breaking shipped trees.** A new error that fires on `examples/` or
  `tests/trees/` is either a real defect in that tree, fixed in the same WP and
  named in the CHANGELOG, or a rule drawn too wide, narrowed. The census tests
  decide which; nothing is silenced.
- **The workflow runtime becomes a second semantics.** It is held to the same
  vocabulary (`delegation.met_by`, `combine.py`, `conditions`) rather than
  reimplementing them, and its tests run the shipped workflow trees.
- **Origins are coarse through a model.** A model's answer after reading a tool
  result is, strictly, influenced by that result. The harness labels direct
  flows exactly and labels a model's answer as *the model's own words*; the
  stricter reading (every answer after a tool call is tool output) would make
  `never-from: tool output` unusable on any agent with tools. This is said on
  `RunResult.unenforced`, not hidden.
- **Streaming through seven frameworks.** WP-14 gives the harness and the
  reference transport real parts. Framework transports that cannot stream yield
  one part and say `streaming: emulated`, which the transport lattice already
  reports.
- **Size.** Seventeen packages. Each is independently green, so stopping after
  any of them leaves a working repository.

---

## 8. What is deliberately not in this plan

- A learnability study with people (decision 3).
- Markets and auctions as a vocabulary of their own. With a team store, a
  team claim and `allowance.value` they can be built; `docs/remediation/F7`'s
  evidence that model bids are noise still stands, so no example ships.
- Commits. Changes are left in the working tree for the owner to review and
  commit, one work package at a time if they wish; §5 names each package's
  files in the CHANGELOG entry it writes.

---

## 9. What was built differently from this plan

Said here so nobody reads §2 to §6 as a description of the code where it is not.

- **Where the examples live.** The fifteen pattern workspaces of this plan and
  of the first round sit in `examples/kernel/`, not `examples/patterns/`. The
  census test for `examples/patterns/` holds every workspace there to the
  orchestration shapes of `docs/92`; these fifteen show kernel operations
  instead, so they have their own folder and are checked by the same
  "every shipped tree under `--deny-warnings`" step.
- **`allowance.value` is one figure, not a general binding.** §2 proposed
  `{value: <binding>, at-most: <figure>}` on any `limits:` figure. What shipped
  is `cost-per-request-from: <run input>` beside `cost-per-request-under:`: the
  budget a caller hands in is read when the run starts and never exceeds the
  written figure. It is the one figure a pattern needed (budget-aware
  delegation); the general form waits for a second.
- **Read-only calls asked together are not run together by the harness.**
  `harness.py` calls tools through synchronous functions, so it runs them one
  after another. What shipped is the part a host needs to do it: every call's
  class is computed (law 1) and readable as `effect: reads` in `when-this`,
  and `questions.effects_of` returns it. A host with asynchronous tools can
  run those calls together; the harness does not yet.
- **A narrowed helper has no run-time check of its own.** Law 5's "a helper
  allowed no more than its caller" is held by `pact check`
  (`loader/a-helper-allowed-more-than-its-caller`). The harness has no point
  where a helper is created at run time from a narrower copy, so there is
  nothing there to hold; a proposed new helper goes through law 8's checker,
  which runs the same rule.
- **Origins through a model stay coarse,** as §7 said they would: direct flows
  (a tool's answer into memory) are refused at run time by `never-from: tool
  output`; a model's own words after reading a tool result are labelled as the
  model's.
- **The second port is smaller, and says so.** The TypeScript port offers a
  team's shared board under the same name and refuses calls to it, runs a
  forking loop stage on one conversation, and keeps its step ceiling under an
  owner's `unbounded: yes`. Each is a line on `RunResult.unenforced`, and
  `docs/20-ARCHITECTURE-DRAFT.md` §7.28 list B has a row for the first two.
