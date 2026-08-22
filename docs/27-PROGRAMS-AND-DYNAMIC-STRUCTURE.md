# PACT — Programs in the Tree, and Structure That Changes

**Date:** 2026-08-13. **Status:** Proposal — NOT binding. Nothing here changes
`spec/schema.yaml`; where this document and the schema disagree, the schema is
what PACT is.

**Reads against:** `00-THESIS.md` (F-2/F-3), `01-DECISIONS.md` (D13/D14/D15/D17/
D22/D23), `50-NOT-COPIED.md` (R5, R16, R42, R58, R60), `25-ARCHITECTURE-DECISIONS.md`
(AD-4, AD-14, AD-71, AD-77, AD-83, AD-84, AD-85, AD-89), `20-ARCHITECTURE-DRAFT.md`
§5.5 (escapes), §8.2–§8.5 (zones, classifier, learning operators), `30-FRD.md`
(FR-1.5.6, FR-6.1.5, FR-6.2.5, FR-8.1.7), and commit `78460c1` (the object model).

**The question this answers:** how PACT agent structures can carry *actual
programs* that create new operators — and how PACT structure itself can change
*dynamically* — without breaking the five properties the project is built on:
the no-code ceiling (D14), the air gap (D17), translate-or-nothing (D15),
`pact check` never executing author code (FR-1.5.6, R5), and learning that
emits reviewable source (T6, D22/D23).

---

## 0. Method

Every mechanism proposed below is checked against the refusal ledger before it
is proposed. Three of the ledger's rows sit directly on this path — R42 (a tool
naming a script for PACT to run), R58 (`resource-kind: sandbox` deleted), and
R16 (orchestration code the model writes at run time) — and §6 of
`50-NOT-COPIED.md` states the standard for reopening one: *a named fixture that
the shipped mechanisms cannot express*, and a design that answers the original
reason, not a design that outvotes it. Each reopening below names its fixture
and answers the recorded reason.

A second discipline is separating three truth-values that the documents
themselves separate:

- **ships** — in `spec/schema.yaml` and enforced by the Rust core or the
  reference harness today;
- **designed, unbuilt** — normative text in the architecture draft or a
  decision record, with no implementation (`§5.5` escapes, `spec/extensions/`,
  the sandbox requirements, the `Graph` IR, `pact approve`);
- **proposed here** — new.

---

## 1. What PACT already is, for the record

One paragraph per load-bearing fact; skip if you have read the design set.

**The artifact.** An agent is a contract (portable: capabilities, evals, SLOs,
policy) plus a plural strategy space (instructions, topology, tools, loop),
authored as a folder of YAML/Markdown that is executable as-is (D2). The eval
suite is the correctness oracle for every substitution — framework, model, and
self-improvement alike (T2). `pact check` reads, resolves and refuses; it never
executes (FR-1.5.6 ▣; audited: zero `Command`, zero `unsafe`, zero interpreters
in `crates/` and `adapters/`).

**The interpreter.** The reference harness is an interpreter whose instruction
set is data: five stage kinds × three outcomes (`loops.py:46-61`), one dispatch
seam (`harness.py:1287`), two model-call sites (`harness.py:1439`, `:2471`),
host-supplied effects only (`Transport.model_call` + `tool_impls`, both in
`SUPPLIED_BY_THE_HOST`, `harness.py:385-424`). Every ceiling is a row in one
termination algebra (`limits.py:548-592`) with the author's own
`when-it-runs-out:`.

**The object model (commit `78460c1`).** `docs/remediation/C8-profiles.md:771-780`
names it: encapsulation is the card an outside system reads versus the
internals it never sees; polymorphism is `variants:` graded by one `evals:`
suite — many implementations held to one behavioural contract; visibility is
`teamwork.shares:`; and `based-on:` with `base:` is inheritance that cannot
silently drop (`loader/restating-a-block-drops-the-rest`) or silently publish
(five closed doors on `base: yes`). Inheritance is shallow by design — deep
merge cannot express removal (`derive.rs:32-37`) — and derivation runs before
validation, so a descendant pays a base's unwritten debts through ordinary
required-field checking (`pact-schema/src/lib.rs:672-675`).

**Metered universality.** `team:` cycles are legal iff *every* member on the
circle writes `limits.asks-itself-at-most:` (`teams.rs:61-72`); the runtime
spends a per-request *activation* counter keyed on `AgentSpec.name`
(`harness.py:567`, `:3001-3015`), failing through the same path as
`OverBudget` so `if-someone-fails:` decides. The computational envelope is
therefore: **a terminating, budget-metered, cyclic delegation graph over
closed vocabularies** — recursion supplies the shape of general computation,
fuel supplies termination, and the refusal documents (`docs/remediation/F1`,
`F3`, `F4`; Y4/AD-16) deliberately keep the predicate surface closed: no
predicate over content, no variables, no iteration over runtime collections,
no expression grammar. Growth of expressive power is *one typed atom per named
fixture* (H6), never a language.

**Where programs stand today.** A skill may ship `scripts/`; PACT records the
files and never runs them (`spec/schema.yaml` `skill.scripts`, R42). The
loader carries payload files as `FileRef { path, content_type, size_bytes }` —
names, never bytes, and today never a hash (`pact-loader/src/lib.rs:771-980`).
A tool reaches exactly one of `connect:` / `url:` / `says:` (`reach.rs`);
execution belongs to the host (`tool_impls`), and MCP is HTTP-only, never
spawn (`mcp/client.py:36-44`). The one typed code escape that exists is
host-side: an interceptor body is an opaque `Callable[[dict], Decision]` whose
declared powers are re-checked after the fact (`interceptors.py:321`,
`:376-412`) — powers a YAML file cannot ask for (`change-the-request`,
`change-the-answer`) exist there, deliberately host-only (R24; `50-NOT-COPIED`
§6 "host-only rather than absent"). The thesis promises typed, in-tree code
escapes in any language including WASM, honestly reported where a target
cannot host them (F-2/F-3, FR-8.1.7, §5.5's six kinds) — **none of that is
built**, and `90-REVIEW.md:586-589` says the consequence plainly: a senior
developer has no in-tree extension point at all.

---

## 2. Design A — programs inside agent structures, creating new operators

The design is four layers. Each layer is independently shippable, each keeps
the layer below it meaningful, and the first layer costs no code and no new
concept — which is what D14 demands of any core capability.

### A0. Operators as data — the lane that already exists

A "new operator" in PACT is usually not a program: it is a schema edit plus a
harness branch, because the instruction set is data. The measured costs:

| New operator kind | Cost today | Discipline |
|---|---|---|
| answer shape | one row in `&the-answer-shapes` (reaches all five consuming fields by anchor) + a `Shape.read` branch (`questions.py:225-301`) + a JSON-Schema fragment; a check module only if values need tree resolution (`callable.rs` is the precedent) | the shape must be a *value* vocabulary, never a fetch |
| stage kind (`does:`) | enum member + `SAYS` wording + a branch at the one dispatch seam `harness.py:1287` + `spec/schema.yaml` choices + reachability | a stage kind that does not call the model gets a bespoke branch, as `ask-someone` does |
| outcome (edge label) | `OUTCOMES` + `Loop.route` + `_stage_to_run` + schema `then:` keys | three outcomes have survived every pattern so far; a fourth needs a fixture no `then:` table can express |
| teamwork join | one `Waits` member + `delegation.py` + schema choices | `enough-of-them` and `whoever-answers-in-time` already have no primitive in any surveyed runtime — PACT emulates; a new join is the same shape |
| interceptor sentence | one `forms:` entry (data!) + the regex that produces it + a `Carries`/`WIRED` row | every sentence must name the power it needs and the moments that carry it out; a sentence nothing can perform is refused by construction |
| resolver atom | one typed atom + its fixture (H6) | never an expression language |

**Proposal A0-1.** Keep this lane primary, and write it down as the answer to
"how do I add an operator": *fixture first, then the YAML row, then the
enumerated code sites.* The harness reports above give the exact site lists;
they belong in a contributor document so the cost model stays honest
(§7.13 gap (1) makes the same point about kinds).

**Proposal A0-2.** Adopt the two designed-but-unbuilt vocabulary-growth
conventions, because both make operators addable *without* schema releases:
the `_`-prefixed open-enum convention on every closed enum (E-2,
architecture L1182-1189) and `x-` subjects in event addresses (EVT-4, already
shipped for `watch.when`/`interceptor.when` positions).

### A1. The `program` kind — a carried, declared, digested, *inert* artifact

**What.** A new workspace collection (`programs: map of group:program`),
holding what today hides untyped in `skills/*/scripts/`:

```yaml
# programs/check-window/program.yaml
description: Decides whether a purchase is inside the refund window.
engine: wasm                     # wasm | python | typescript
determinism: pure                # pure | deterministic | nondeterministic  (§5.5)
takes:
  purchased-on: text
answers-with:
  verdict: one of inside, outside
fuel:                            # the program's own termination algebra
  instructions-at-most: 10m      #   counted by the engine, not trusted from the body
  runs-for-at-most: 2s
  memory-at-most: 64m
  when-it-runs-out: stop-and-say-so
body: ...                        # a payload directory: programs/check-window/body/
```

**What it is not.** `pact check` still never opens the body and never runs it
(R5 intact). The kind exists so that what the tree already carries stops being
invisible to governance:

- `takes:`/`answers-with:` reuse the one answer-shape vocabulary (the anchor
  gains a sixth consumer), so a program's interface is reviewable in the same
  words as a tool's `takes:` — and refusable at check time when a caller's
  arguments do not fit.
- `surface: S-EXEC`, `tier: expert` on every field. Expert tier is what keeps
  D14 true: no core capability may *require* a program, a workspace with
  programs simply does not earn the `no-code` badge, and — the README's own
  standard for the carried Python helper — deleting `programs/` must leave a
  working agent.
- `determinism:` decides replay: only `pure`/`deterministic` bodies may be
  replayed rather than re-executed; `nondeterministic` forces
  `durability: at-effect` (§5.5's rule, adopted verbatim).

**Two prerequisite fixes, both already designed:**

1. **Blob digests.** EXP-8 (architecture L530) specifies
   `{ $file, contentType, sizeBytes, digest }`; the shipped `FileRef` carries
   no digest (`pact-loader/src/lib.rs:771-980`). A program body without a
   digest is a body the lockfile cannot pin and a reviewer cannot attest.
   Land EXP-8's digest for payload files — at minimum for `programs/`.
2. **Govern the suppression channel.** `.pactignore` can today remove a
   script from the manifest with only a note (`loader/ignored-on-purpose`);
   the loader's own module doc flags this as ungoverned
   (`pact-loader/src/lib.rs:89-105`), and EXP-10 already specifies the fix:
   `.pactignore` is a first-class governed document inside the digest. Land
   it before programs matter, because an ignore rule is a deletion operator
   the blast-radius classifier cannot see.

**Why a kind and not a fourth tool transport.** R42 refused `runs-as: code`
because it "would make `pact check` the thing that decides whether a script is
safe". The program kind answers that reason rather than outvoting it: the
checker validates the *declaration* (shapes resolve, fuel is written, the
digest is pinned) and decides nothing about safety — safety belongs to the
executor, which is the next layer, exactly as it does for `connect:`.

### A2. The executor seam — reinstating the sandbox as a resource

**What.** Execution stays a *host* property. A program runs only when the host
supplies a sandbox, and the sandbox is declared the way every other host-owned
thing is — as a resource:

```yaml
# resources/local-sandbox.yaml
resource-kind: sandbox           # R58 reinstated — now it has fields only it needs
description: The machine-local executor for this workspace's programs.
engines: [wasm]                  # what it can host; anything else is refused here
asks-to-run: may-we-run          # a question, same mechanism as asks-to-connect
```

R58 deleted `sandbox` from `resource-kind:` because it had "no field in this
kind that only they would use" — a choice that led nowhere. That reason
expires the moment the kind carries `engines:` and `asks-to-run:`, which is
exactly the return condition R58's own text sets ("Each returns with the
fields it needs"). The sandbox itself is specified already: the eight
requirements of §8.5 (architecture L9548-9554) — kernel-level isolation, empty
environment, secrets never in the guest, deny-by-default egress, resource
limits, fully local (D17), configuration in GOVERNED.

**Wiring.** A tool gains the ability to reach a program *through* the existing
one-place rule — `connect:` names the sandbox resource, and the action names
the program:

```yaml
# tools/refund-window.yaml
description: Answers whether a purchase is inside the refund window.
connect: local-sandbox
actions:
  check:
    program: check-window        # names: programs — refused if absent
    takes: { purchased-on: text }
    reads-only: yes
```

This keeps `reach.rs`'s "a tool reaches ONE place" intact, keeps R42's letter
(no tool ever names a script *for PACT to run* — it names a program for the
*host's declared executor* to run, behind a consent question, the exact shape
`mcp-server` has), and gives `pact waits` the `may-we-run` gate for free.

**Metering — the part that makes this "metered universality" and not an
escape hatch.** A program spends from the same one pot per request:

- its `fuel:` rows join the run's termination algebra — enforced by the
  engine (wasmtime's fuel/epoch mechanism for `wasm`), reported through the
  same `_ran_out` path, honouring the program's own `when-it-runs-out:`;
- wall-clock spent in a program charges `runs-for-at-most`; a program call is
  a tool call for `tool-calls-at-most`; the trace records it exactly as it
  records a tool call, so the byte-identical-trace claim extends rather than
  acquiring an exception.

**Amendment (2026-08-14, owner-approved direction): programs may reach
outside — by declaration, never by default.** The v1 text above gave programs
no network at all. The approved relaxation keeps *one* egress story instead of
zero egress: a program that needs the outside world says so on its own face —
`reaches-outside: yes` plus a `connects: [<resource-name>, …]` list naming the
workspace resources it may talk to — and the workspace's `allow-egress:` must
carry a new `programs` role for any such program to bind. The checker then
holds the same line it holds for tools: a reaching program in a workspace
whose egress list says nothing is refused where the author is, naming the line
to add. The sandbox enforces it at run time as deny-by-default plus exactly
the named endpoints (requirement 4 of the eight). What this preserves: the
egress boundary stays one written, contradictable sentence; redaction and
interceptors still see every value that crosses it, because program traffic
flows through host-brokered connections rather than raw sockets. What it
forbids still: an undeclared socket — capability by omission.

**Portability, honestly.** The capability lattice gains one family:
`programs.wasm`, `programs.python`, `programs.typescript` per target,
`native | unsupported`. `wasm` is the portable engine — a self-contained
runtime a host can vendor offline (D17) — and is the only engine the
reference harness should ever ship an executor for. `python`/`typescript`
bodies are legal *declarations* that most targets will report `unsupported`,
which is F-3 behaving as written: declarative-first, never declarative-only,
degradation named before execution.

**Fixture (the reopening standard).** `examples/refund-desk`'s
`check_window.py` — six lines of date arithmetic the model routinely gets
wrong — expressed today only as prose in a skill plus a script a person runs
by hand. The fixture: the same workspace, with the window check as a `wasm`
program behind a `reads-only` action, byte-identical verdicts across two
transports, refused cleanly on a transport with no sandbox. Nothing shipped
can express it: `says:` puts the arithmetic back on the model, `url:`/
`connect:` require a server for six lines, and R18's own standard ("code
stays possible, never necessary") is currently *possible only out-of-process
by a person*.

### A3. Programs at the escape points — realising §5.5 in-tree

§5.5 already enumerates where behaviour may be replaced by a typed escape,
each with a no-code default: `scorer`, `router`, `transform`, `tool`,
`search`, `stream-transform` — plus the host-side interceptor `guard` and the
two host-only rewrite powers. **Proposal: an escape's `impl:` reference may
name a `program` from this same tree** (never a package, never a URL — the
`agent` shape's own containment rule, applied to code):

- `scorer` — an eval metric `uri: program:<name>`; deterministic scorers run
  in the deterministic-first band (AC-4.5), which finally gives authors
  custom *decidable* metrics without a judge. One new provider scheme in
  `providers.py` (the registry is a two-branch constant today,
  `providers.py:169-174` — this is the one place layer A3 costs adapter code).
- `transform` — the deferred `toModelOutput` projection (`50-NOT-COPIED` §6)
  lands as a pure program on `tool.actions.<a>.projects-with:`, replayable
  because `determinism: pure` is declared, reviewable because the body is
  digested.
- `router` / `search` / `stream-transform` — expert-tier, excluded from the
  `no-code` badge and from L3 conformance exactly as §5.5 already rules
  ("the eight topologies and six loops are expressible *without* escape" stays
  a conformance gate). F1's refusal of content-conditional routing in the
  authored format is untouched: a routing program is an *escape*, priced as
  one, never the core lane.

**CodeAct** (FR-6.1.5 / AC-5.2 — required, unshipped, and today
unshippable): with A1+A2 it becomes a loop shape rather than a new execution
model — a stage `does: run-code`, legal only when the agent's workspace
declares a sandbox resource; every model-written snippet lands in the
transcript (reviewable after the fact, like every other model output),
executes under the sandbox's deny-by-default egress and the *stage's* fuel,
and can never touch the tree. This is not R16: R16 refused model-written
*orchestration* — invisible structural change — while CodeAct code is an
in-transcript action with no structural authority, which is precisely the
line AD-83's `meta-depth = 1` draws.

### A4. Programs the agent authors for itself — D22(b) on AD-85's rails

D22 grants agents the right to author tools for themselves; FR-6.2.5/M7.4
plan it; nothing ships. The design is already written and this proposal only
connects it to A1-A3:

- Under the `no-code` badge, a self-authored tool is a **`composite`** —
  a declarative composition of already-approved, pinned actions (AD-85).
  No program involved; reviewable line by line.
- A self-authored **program** requires the distinct `engineer` approval role,
  and the approval surface must say, in those words, *"this tool contains
  code that has not been read by a person"* (AD-85). Acceptance is never
  "does not raise" (AD-85's explicit prohibition); it is the same eval-gated
  keep-only-if the learning loop already applies, on a frozen held-out split.
- Every learned program lands as a *new* digested blob plus a `supersedes`
  edge at CLASS-4 (EXP-7a forbids ADD/EDIT on payload blobs), carries the
  provenance envelope, and is revocable: `supersedes`/`revoked-by` plus a
  resolver that refuses to bind a revoked digest (§8.5 — removal as
  expressible as addition).
- Tool output never writes a program, a skill, or memory directly
  (FR-6.2.7); proposals go through the queue like every other diff.

---

## 3. Design B — PACT structure changing dynamically

"Dynamic" splits into three different time-scales, and conflating them is how
self-modification designs go wrong. PACT already has the right skeleton for
each; what follows names the missing joints.

### B1. Learned structural change — widening the one lane that ships

What ships: `learning.enabled: off | propose-only | applies-safe-changes-itself`;
a `Proposal` is a unified diff against one field; the apply set is
`CAN_BE_APPLIED = ("instructions",)` (`learning.py:86-101`); the optimiser
proposes and never applies (`optimising.py:20-25`); nothing in the tree writes
an author's spec file; a human-authored commit is the approval record (AD-89).

The widening is *already specified* as a closed operator algebra and should be
built as one, not as a growing list of writable fields:

- **Artifact operators** `ADD | EDIT | AGREE | RETIRE`, ≤4 per cycle, ≤1 per
  sub-artifact, no whole-file replacement, retirement bitemporal and offline-
  rollbackable (§8.5).
- **Graph operators** `ADD-EDGE … REBIND-TOOLSET, ADD-AGENT` — closed set,
  statically verified before execution, no free-form authoring (§8.5);
  `ADD-AGENT` unconditionally CLASS-4, emitting a template whose contract
  fields are **immutable references to the parent's** (AD-83) — note this
  *reuses the object model*: the machine's new agent is `based-on:` a parent
  with its contract inherited un-overridably, which is `base:`/`based-on:`
  doing governance work.
- **The opt-in that does not exist yet**: a `may-also-change:` field on
  `learning:` (identified missing in `learning-governance.md` §1.7) so that
  loop/tools/topology learning is explicitly granted, still CLASS-3/4, and
  `needs-a-person-to-approve:` remains union-only (never narrowed —
  `learning.py` already unions with `HIGH_RISK_FIELDS`).
- **Classifier discipline**: classify on the *resolved* diff, present the
  *authored* one (config-nocode's recommendation); cumulative drift against
  the frozen baseline, not per-diff review alone (FR-6.2.3a); the Rust core
  recomputes every classification from `(signed baseline digest, current
  tree, compiled-in schema)` and refuses on mismatch (AD-77).

**Amendment (2026-08-14, owner-approved direction): author-widened autonomy.**
The pipeline above defaults conservative; the approved relaxation makes the
*author* the one who decides how far self-change goes, on two new lines:
`learning.may-also-change: [loops, tools, team, variants]` extends the
proposal surface beyond wording (each entry still classified at its own
surface's floor — a topology proposal is never below CLASS-3), and
`learning.applies-up-to: CLASS-2` lets a workspace opt classes 1–2 into
auto-apply once its eval suite meets the minimum-case floor, instead of
CLASS-1-only. Drift tracking against the frozen baseline stays mandatory and
un-optable — it is what makes wider autonomy survivable — and
`needs-a-person-to-approve:` remains union-only. The classifier and the
schema stay outside reach (B4); everything else opens by writing lines.

### B2. Run-time structural dynamism — the `agent` shape, one dereference short

The `agent` answer shape (commit `78460c1`) makes an agent a passable value:
a validated workspace-key name (`questions.py:287-300`), never a fetch. Today
no code path puts an agent-shaped *value* to work — only static `team:` keys
reach `ask_member` — and wiring it naively would bypass the one rule that
makes recursion safe, because `teams.rs` legalises cycles over the *static*
graph only. The fuel and the shape shipped in the same commit and are not yet
connected. **Proposal — the dynamic-bottom rule, the static rule's exact
analogue:**

> An agent may be put to work *by value* only if it writes its own
> `limits.asks-itself-at-most:` figure. A by-value dispatch of an agent
> without the figure is refused at the delegation site, through the same
> path `OverBudget` takes, so `if-someone-fails:` decides.

Why this is the right generalisation: the static rule says *a circle is legal
iff every member on it writes its own bottom*. Under dynamic dispatch the
potential call graph is "any agent an `agent`-shaped value can name", so the
member-writes-its-own-figure obligation moves from the circle to the
receivable agent itself. The activation meter needs no change — it is already
keyed on `AgentSpec.name` per request and already shared down through grants
(`harness.py:567-580`); admission is the only missing check, and it lands
beside the existing figure check in `delegate_by_running`
(`harness.py:3001-3015`).

Static half: `pact check` warns — naming the field — where a field of shape
`agent` exists whose value space (a closed `one of …`, or any non-base agent
when open) includes an agent with no figure; bases are refused outright (the
sixth door on `base: yes`, joining the five from `78460c1`'s red-team). A
`kind: agent` value may also never name a base at run time for the same
reason the other five doors exist: "it never runs" must not have a value-
shaped exception.

What this buys, concretely: dispatcher patterns stop being prompt-trust —
`examples/patterns/swarm`'s dispatcher can *return* `worker: agent` and have
the harness honour it under fuel, instead of relying on the model to route by
name inside prose; a question can ask a person *which specialist should take
this* (`question.answer` already accepts the shape); the surrounding system
can select workers per request through `run-inputs:` (its stated purpose,
`spec/schema.yaml:521-528`) and that selection can finally reach delegation.
What it does not buy, deliberately: branching on the value in the authored
format (F1 stands — a value can be passed, not predicated on).

### B3. Language-level dynamism — how PACT-the-format grows

The schema is data (282 fields, every attribute read from YAML;
`from_doc.rs:24-257`), so the *language* grows by YAML edit plus enumerated
Rust residue (`node_is_collection`, `unnamed.rs`, `file_for`, `kind_stems` —
four named sites for a new collection; the build fails until `unnamed.rs` is
told). But the schema is also **compiled into the binary and sha256-pinned**
(R40/R41), because the schema *is* the blast-radius classifier's rule table —
a discoverable schema let an attacker's `open: yes` make `run-arbitrary: yes`
load cleanly. So dynamism at the language level is deliberately *slow-path*:

- **workspace-scoped**: AD-4's `spec/extensions/*.yaml` — additive, `x-`
  fields only, every introduced field forced `surface: S-GOV`, never touching
  a core field's `surface`/`tier`. Designed; explicitly not built
  (architecture L382). Building it is the honest answer to "my workspace
  needs a field PACT does not have" — today's answer is bare `x-` keys, which
  round-trip but validate nothing.
- **distribution-scoped**: new atoms (H6: one typed atom per named fixture),
  new sentences (`forms:` is data), new shapes (the anchor), new kinds
  (YAML + one `kind_stems` word), new registries (`names: pact:<x>` + one
  `.knowing()` call — `pact-schema/src/lib.rs:466-500`), versioned by
  `pact-version:` so an old runtime refuses loudly rather than misreading.
- **never run-time**: no mechanism proposed here — or anywhere — may let a
  run, a model, an optimiser, or a bundle alter the schema, a `surface:`, a
  `tier:`, or the classifier's tables while anything executes. That is
  FR-6.2.3b (safety invariants structurally outside the search space), and it
  is the load-bearing wall everything else in this document leans on.

### B4. The invariant floor — what must stay outside every loop's reach

Enumerated once, so no later layer bargains with it piecemeal:

1. The compiled-in schema and its `surface:`/`tier:` columns (R40/R41, AD-4).
2. The GOVERNED zone — structurally absent from `spec_tree_learnable` (§8.8);
   any `fs.*` scope intersecting a GOVERNED path is a validation error, not a
   review item (AD-84).
3. The approval path: the queue, the held-out split, the judge binding
   disjoint from the accept-path judge, `pact approve --baseline` as the sole
   writer of `drift.baseline` (AD-82), the human commit as the approval
   record (AD-89).
4. The meters and their identities: `AgentSpec.name` as the activation key
   (the post-review fix in `78460c1` exists because reading any other
   identity un-meters the circle), the one `Pool` per request, the fixed
   ceiling order.
5. `redaction:`, `watch:` (S-GOV — evidence, not behaviour), and the egress
   boundary (`allow-egress:` + `reaches-outside:` as data). Programs never
   acquire network; only tools and resources reach outside, so the egress
   story stays one story.

---

## 4. Design C — one language: values, arguments, and programs woven through every kind

**(Added 2026-08-14 on the owner's direction: integrate across the entire
spec, for maximum agent power.)** The ask this answers: *define a new value /
operator / variable, callable from YAML, with arguments to make it
contextual.* That is three mechanisms, split by when the call is evaluated —
and the optimal integration is not three bolt-ons but one rule applied
everywhere: **anything nameable once should be reusable everywhere a name of
its kind can appear, and anything reusable should take declared, typed
arguments.**

### C1. Named values — write a fact once (`values:`)

A new workspace collection of named, shaped constants:

```yaml
# values.yaml
refund-approval-threshold:
  shape: money
  value: 200 USD
  description: The figure above which a person decides.
standard-deadline: { shape: duration, value: 30s }
```

Callable anywhere a scalar sits, by one spelling: `{use: <name>}`. The loader
substitutes at load time, *before* derivation and validation, so the checker
validates the finished document, `pact show` prints it expanded, and the
substituted value must fit the field's own type — a duration used where money
belongs is refused at the use site, naming both lines. The power is
convergence: today the €200 threshold lives three times — in the approval
rule (`more-than: 200 USD`), in the runaway-refund interceptor sentence, and
in an eval case — and the three can drift apart in silence. As a value, it is
written once and every reader is the same reader. Governance: classification
runs on the *expanded* document (the classify-on-resolved rule), so editing a
value inherits the highest blast-radius class of any site that uses it — one
edit that widens three gates is reviewed as exactly that.

### C2. Arguments — `expects:` / `with:` on every `based-on:`

`based-on:` already exists on all thirteen collections; this makes every base
a *function*. A base may declare typed parameters; a deriving entry supplies
them; `<name>` holes in the base's scalar values are filled at load time. The
in-house precedent is the interceptor sentence vocabulary, which already
type-checks `<a thing>` and `<n>` holes against closed lists.

```yaml
# interceptors/stop-runaway.yaml            # the template
base: yes
expects:
  which-tool: { shape: text }               # answer-shape typed
  ceiling:    { shape: whole-number }
when: step.tool.before
may: [stop-the-run]
rules:
  - if <which-tool> is called more than <ceiling> times in one run,
    stop and say "That needs a person now."
```

```yaml
# interceptors/stop-runaway-refunds.yaml    # the call
based-on: stop-runaway
with: { which-tool: payments, ceiling: 1 }
```

Rules that keep it decidable and reviewable: holes live in scalar *values*
only — never in keys, never producing structure, so a template cannot
manufacture fields the classifier has not seen; every `expects:` entry is
required and shape-checked (`with:` may itself say `{use: <value>}`); an
unfilled parameter is an ordinary missing-field refusal on the descendant —
the same pay-the-debt rule abstract bases already use; after substitution the
derived document reads like longhand, so digests stay comparable. This turns
the worked example's own founding irritation — two interceptor files
differing in two lines — into one template and two two-line calls, and it
does the same for loops (a `careful` loop parameterised by which written
policy the re-read stage checks against), questions, policies, tools, and
whole agents (`desk-pattern` with `expects: {domain: text, daily-cap:
money}`). Bundles carrying parameterised templates become a genuine
capability library — Eve's extension packages, as data.

### C3. Programs as a first-class capability kind

The maximal-power integration is to stop treating a program as something a
tool wraps and make it the fourth thing an agent can *use*:

- `agent.uses:` and `stage.may-use:` and `variant.may-use:` extend their
  `names:` lists with `programs`. A used program is offered to the model
  directly — its `takes:` becomes the argument schema, its `answers-with:`
  the result shape — with no wrapper file.
- The tool-mediated form (`action.program: <name>`) stays, and is the one to
  reach for when a program call needs the action governance vocabulary:
  `needs-a-person:`, `spends-money:`, `same-request-key:`, `inspects:`,
  `bind:` all apply to program actions unchanged — **the entire approval
  algebra composes with programs for free.**
- `bind:` gains a second source: `bind: { <arg>: remembers.<name> }` beside
  `run-inputs.<name>` — a program (or any tool) can receive a remembered
  fact the model never chooses.
- `action.remember-as: <state-name>` lets a result land in declared memory —
  refused when that state's `never-from:` lists `tool output`, so the
  poisoned-page rule keeps its teeth by default and relaxing it is one
  visible line.

### C4. Programs at the closed vocabularies — powers that become authorable

Each of these is a closed list today whose growth was waiting for a
reviewable executor; a declared, digested, fueled program is that executor:

| Where | Today | With programs |
|---|---|---|
| interceptor `rules:` | six sentences; the two rewrite powers are host-only | new sentence forms with a program hole — `replace the answer with what <a program> returns`, `stop if <a program> says so` — which makes `change-the-request` / `change-the-answer` *authorable*, because the rewriter is in the tree, fingerprinted, and fueled |
| `redaction.hide` / `recognises:` | four recognisable things | `anything <a program> recognises` — domain identifiers (patient IDs, VINs) join card numbers, at expert tier |
| `question.answer` | shape-checked only | `checked-by: <program>` — validate a human's input (a checksum, a date) before the run resumes on it |
| eval `metrics:` | `pact:` / `deepeval:` | `program:<name>` — custom *deterministic* graders, running in the deterministic-first band, air-gapped |
| tool results | raw, or tidied later | `projects-with: <program>` on an action — the reshape-before-the-model-sees-it projection |
| stage `then:` | three fixed outcomes | `decided-by: <program>` as the router escape realised in-tree: content-conditional routing for experts, returning one of the stage's declared outcomes — refused under the `no-code` badge, so the core lane keeps its three-outcome table |

### C5. Variables, honestly named

`remembers:` *is* the variable — declared, lifetime-scoped, write-guarded.
C3's two bindings (`bind: remembers.<name>`, `remember-as:`) make it readable
and writable from the format without creating a condition language: a value
can be carried, shown (`shows: [remembers.<name>]`), handed to programs, and
stored — but the authored no-code format still cannot *branch* on it. Where
branching is genuinely needed, it is C4's `decided-by:` escape, priced and
badged as one.

### C6. What stays closed, even now

Free-floating variables in control flow; an expression grammar; holes that
create structure; schema edits from inside a run. Every one of these is what
makes `pact check` able to say what a tree will do before anything runs —
and each has a sanctioned door beside it (a typed atom, a template, a
program at an escape point) that arrives with review, fuel, and honest
reporting attached.

## 5. Constraint audit

| Constraint | Design A | Design B |
|---|---|---|
| **D13/D14 no-code ceiling** | programs are `tier: expert` everywhere; every operator keeps a closed-vocabulary face (A0); composites are the no-code self-authoring lane (AD-85); deleting `programs/` leaves working agents | closed operator algebra, plain-language classifications, `propose-only` remains the core mode (auto-apply is expert by construction) |
| **D17 air-gap** | `wasm` engine vendored and offline; programs have no network; `program:` metrics run in the deterministic band | everything already offline; extensions are files in the tree |
| **D15 / AD-T1 translate-or-nothing** | escapes typed and in-tree; a body names no out-of-band `runtime_deps`; unsupported engines reported per target before execution (F-3) | structural changes are diffs to the same portable tree |
| **R5 / FR-1.5.6 check never executes** | check validates declarations, digests, shapes, fuel — never opens a body; execution needs a host sandbox + consent question | check classifies diffs; the core recomputes classifications; nothing executes at review time |
| **T7 honesty** | lattice family per engine; `unsupported`/`unenforced` name every gap; trace records program calls | every dropped key named (D-1 warning), every suppression governed (EXP-10), drift cumulative |
| **Metered universality** | program fuel joins the one termination algebra with `when-it-runs-out:`; spend charges the one pot | dynamic dispatch admitted only where a bottom is written (the dynamic-bottom rule) |
| **D22/D23 governance** | learned programs: engineer role, "contains code not read by a person", eval-gated, revocable, CLASS-4 blobs | operators classified by surface; ADD-AGENT CLASS-4 with immutable contract inheritance; invariant floor (B4) |

## 6. What would falsify this design

- A `program` fixture that the composite lane could have expressed — then A1
  overbuilt, and the fixture standard was not met.
- A measured D14 persona who *needs* a program for a core task — then expert
  tier was a lie and the design violates D14 rather than skirting it.
- The dynamic-bottom rule refusing a pattern the static rule permits (or
  admitting one it refuses) — the two rules must agree on every static graph,
  and a conformance test should hold them equal on the shipped pattern trees.
- A wasm executor that cannot enforce `fuel:` deterministically across two
  hosts — then program calls break the byte-identical-trace claim and must be
  declared outside it (§7.28's list B), which halves the value of A2.

## 7. Pending, in build order

1. **`values:` + `expects:`/`with:` templates** (C1, C2) — pure loader work,
   no execution, immediate authoring power on all thirteen collections;
   classify-on-expanded lands here too.
2. **Blob digests for payloads** (EXP-8 half) and **governed `.pactignore`**
   (EXP-10) — prerequisites for programs; small; close standing honesty gaps
   regardless.
3. **The dynamic-bottom rule** — smallest high-leverage runtime piece: one
   admission check beside `harness.py:3001-3015`, one checker warning, the
   sixth `base:` door, tests mirroring `test_asking_yourself_has_a_bottom.py`.
4. **`may-also-change:` + `applies-up-to:` + the operator algebra** for
   learning (B1 and its amendment) — unlocks D22(b)/(c) on rails already
   specified.
5. **The `program` kind** (A1) — schema-only first; it governs what trees
   already carry even before anything executes it.
6. **`resource-kind: sandbox` + the wasm executor + fuel wiring + the
   `programs` egress role** (A2 and its amendment) — the first moment a
   program runs; consent-gated; lattice column added.
7. **Programs as a capability kind** (C3): `uses:`/`may-use:` gain
   `programs`, `action.program:`, `bind: remembers.*`, `remember-as:`.
8. **Escape-point and vocabulary integration** (A3, C4): `program:` metric
   scheme, `projects-with:`, program-holed sentences (rewrite powers become
   authorable), `checked-by:`, `decided-by:`, then `does: run-code` and
   `pact:loop/codeact`.
9. **AD-85 self-authored lane** (A4) — last, because every prior layer is its
   safety equipment.
