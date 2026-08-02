# PACT — Architecture Decision Record

**Date:** 2026-07-26 · **Status:** Baseline for `30-FRD.md` and `40-IMPLEMENTATION-PLAN.md`.
**Supersedes as the decision record:** `20-ARCHITECTURE-DRAFT.md` R5/R6 (which remains the
*rationale* document — every row below cites the section that argues it).
**Binding inputs:** `00-THESIS.md` (T1–T7, G/O/AC/P/E/G/F/NG), `01-DECISIONS.md` (D1–D28).

**What this document is.** The draft survived two adversarial rounds and is 9,259 lines of
argument. This is the extract an implementer works from: every decision with the
alternative it beat, every surviving bet with its falsifier and my confidence in it, every
trade-off we have agreed to pay, everything still unproven, and the order to build in.

**Reading key.** `AD-*` = architectural decision (stable id; cite these in the FRD).
`EDIT-*` = an editorial defect in the draft that must be fixed before the FRD is written.
Confidence is my judgement of survival probability against the draft's own evidence:
**high** = evidence in hand or a property test makes it a theorem; **medium** = reasoned
from source but unmeasured; **low** = a genuine research bet.

---

## 0. Editorial pass — defects found in R5/R6 that must be fixed first

The draft is internally coherent on the things it was attacked for. It is not coherent on
what the last two rounds' deletions left behind. Twelve findings, three of them blocking.

### 0.1 Blocking — resolve before the FRD is written

**EDIT-1 — `minimum-credible-bar` makes the flagship example uncertifiable, and reopens the
affordability hole Y21 closed.** §6.9-A rule 3 (`:4584`) refuses to certify below `0.90`
for *"any agent whose tools carry `effects: external` **or whose policy has an
`ask-a-person` gate**"*. §11.6 gives the refund desk an `ask-a-person` gate. So:

- §11.8 writes `must-pass: 70%` "chosen at `pact init` from a TARGET of 16 cases" (`:8032`);
- §4.6's lockfile records `verdict.status: PASS`, `bar: {value: 0.70, target-cases: 16}`
  (`:2460-2462`);
- rule 3 says the resolver must report **UNDECIDED**, never PASS, for exactly this workspace;
- and at `0.90` §6.9-A's own table demands **29** gating cases at k=1 / **54** at k=14 —
  so §11.1's headline ("16 to certify a 70% bar") is wrong for the workspace it describes,
  and the D20 case-authoring cost roughly triples.

Two normative rules disagree on the flagship artifact, and `pact init` writes a bar the
resolver is then required to refuse. **RESOLVED 2026-07-26 — AD-58a below.** The defensible fix
is to scope the floor to the *assertions that gate the money-moving path* rather than to the
suite bar, because "an approval gate exists" is a reason to trust the agent *less* with
autonomy, not a reason to demand a higher pass rate on unrelated assertions — and because a
floor that forces 54 cases on every workspace with an approval gate re-creates PACT-E3009 in
a new place.

> **AD-58a (resolution of EDIT-1).** `minimum-credible-bar` is scoped to the
> **money-moving assertion subset**, not to the suite bar.
>
> 1. An assertion is *consequential* if it gates a tool carrying
>    `effects: external`, or is named in a `policy.ask-a-person` condition.
> 2. Consequential assertions must reach `1.00` on every gating case — they are
>    correctness invariants, not a rate to be averaged. A refund approved outside
>    the window is not offset by six correct ones.
> 3. The **suite** bar stays as `pact init` chose it, sticky and printed.
> 4. `effects: external` alone no longer raises the suite bar.
>
> This keeps the flagship certifiable at 16 cases, and is *stricter* where it
> matters: the previous rule let a money-moving mistake pass inside a 90%
> average, and this one does not. The trade is that a consequential assertion
> now needs enough gating cases to be meaningful, which §6.9-A's minimum-n
> already governs.
>
> Rationale for not simply deleting the floor: the floor was answering a real
> question — "how much evidence before an agent may move money?" — and the
> answer is *per-assertion certainty*, not *aggregate rate*.

**EDIT-2 — RESOLVED 2026-07-26 (R6).** §6.2's example now loads: workspace-relative reference, `<tool>/<action>` form, explicit `graded-by` id, mandatory `population:`, and the `pact:tool_order` spelling. The §12.1 code-fence gate is extended from re-deriving verdicts to asserting loadability, so this class cannot recur. Original finding: §6.2's own suite example violated five of the document's normative rules.** The
section that *defines* the eval suite ships an example that would not load (`:3821-3838`,
`:3958-3980`):

| Line | Violates |
|---|---|
| `must-match-shape: ../agents/refund-desk/answers-with.yaml` | §1.8 — `..` is forbidden in an authored reference; LOAD-1 rejects it |
| `graded-by: { model: local }` | §6.5 — `graded-by` must name an explicit id, never the alias `local` |
| `must-call-before: { call: issue-refund, first: look-up-order }` | §1.8 `[R5]` action row — the authored form is `<tool>/<action>` |
| no `population:` | §6.2's own rule — *"the loader refuses a suite with no `population:`"* |
| `uri: pact:tool-order` in the expert `metrics:` block | X23, **stated 90 lines above** — *"the `pact:tool-order` URI spelling is deleted"* |

§11.8 was corrected in R5; §6.2 was not. Fix §6.2 to be §11.8's superset, and add it to the
§12.1 code-fence CI gate (which currently only re-derives *verdicts*, not *loadability*).

**EDIT-3 — RESOLVED 2026-07-26 (R6).** All four sites rewritten to the rules that replaced them. Original finding: normative text still depended on subsystems Y1/Y2 deleted.** Four live sites,
each contradicting the R5 rules that replaced them:

| Site | Stale claim | Contradicts |
|---|---|---|
| §8.7 `:6610-6615` | *"§4.4a's pre-flight scales the budget to the measured `r̂` … and stages a RES-7b bundle for approval as a fallback"* | §4.4a.1 (full budget + sequential stop), Y1 (RES-7b deleted), Y2 (`r̂` scaling deleted) |
| §8.9 `:6846-6853` | *"`optimised-for` … is what RES-7b consumes … §8.11 is the format around them … BND-9 compares `catalog-entry-digest`"* | §8.11 deleted; §8.9's own R5 amendment says both fields are **labels** |
| §8.10 `:6976` | *"§8.11 is the format that makes this enforceable rather than aspirational"* | §8.11 deleted; §11.5's no-`command` rule is what makes it enforceable |
| §13.14-legacy `:8884` | *"§8.11 closes the format question"* | §8.11 deleted |

Delete or rewrite all four. §13.14-legacy should be cut entirely — §13.14 already states the
re-admission bar, and keeping a section that asserts a deleted subsystem "closes" a question
is the exact contradiction class R2 was attacked for.

### 0.2 Non-blocking — fix in the same pass

**EDIT-4 — VAL identifier mis-references, which is the defect §15 exists to prevent.**
§7.7's fix (1) cites *"VAL-10 makes any other cycle through the owning agent a load-time
error"* (`:5503`) — that rule is **VAL-14** (§7.6 `:5422`); VAL-10 is the approval-atom rule
in §4.1. §7.7's fix (2) cites *"`reads:` is REQUIRED on every emitted `agent` node
(VAL-11)"* (`:5523`) — that is **VAL-15** (§7.6 `:5428`); VAL-11 is the argument-role rule in
§5.10. §14.2c's added-count row still reads *"VAL-10..VAL-13, graph VAL-10/VAL-11"*.

**EDIT-5 — §5.7's lattice example has a duplicate mapping key.** `tool.computer-use` is
declared at `:3291` and again at `:3316`. §1.5 makes duplicate keys *"an error at every
nesting level, with no fallback reader"*. The document's own example fails its own parser.

**EDIT-6 — §11.12 uses a document kind that does not exist.** `resources/browser.yaml`
declares `kind: sandbox` (`:8376`); §2.1's kind list is closed at eleven and contains no
such kind. The form is `kind: Resource` + `resource-kind: sandbox`, per §11.5's MCP
precedent. §2.6/§5.3's note also refers to *"a `kind: sandbox` Resource"*, which is the same
error in prose.

**EDIT-7 — counting drift in three places.** (a) §15.1 says *"Eight core verbs"* over a table
with **ten** core rows — Y27's list omits `pact tools`, which §11.1's own quickstart requires
twice. (b) §15 records the `H` series cardinality as **31**; §14.1 carries **36** live bets
(H1, H3–H31, H32-perf, H33, H35, H36, H37a, H37d), and the preamble still says *"Bets are
`H1..H31`"*. (c) §14.1 lists **two** `~~H34~~` rows with different dispositions ("RETIRED
`[R5]`" at `:9016` and "RESOLVED BY DELETION `[R5]`" at `:9019`).

**EDIT-8 — X23 ("one assertion vocabulary") is not discharged.** §6.3 ships 36 assertions
named `one-of`, `contains`, `tool-order`; `rules:` uses `must-say-one-of`,
`must-not-contain`, `must-call-before`. X23 asserts *"§6.3's list **is** the vocabulary"*, but
the two lists do not match name-for-name and no mapping table is published — a second
spelling layer inside a document whose X1 rule is one name per field. Either publish the
normative `must-*` ⇄ assertion-id map or rename §6.3's family to the `must-*` spellings.

**EDIT-9 — two permission lists still shipped as open text.** `keep-only-if:` has two
observed values (`a-person-approves-it` §11.10, `scores-higher-on-evals` §8.8 OPT-GATE-1)
and no enum. `may-also-change: [loop | tools | topology]` (§8.7) has no entry in the 1:1
surface map, which covers only the four `may-improve-on-its-own` members. This is the exact
defect §12.1 schedules a Stage-1 fix for on the sibling list; do both in one commit.

**EDIT-10 — `sampling` is a legal variant field with no Agent field-table row.** §2.4b lists
`sampling` (S-CTRL) among legal variant fields and §7.2 lists it node-common, but §2.4's
Agent table omits it. A variant may override a field the parent document cannot declare.

**EDIT-11 — section ordering.** §2.8 sits between §2.6 and §2.7; §6.9-E is a bold paragraph
inside §6.9-F rather than a heading; §13 runs 13.1–13.9b, 13.13, 13.15, 13.14, 13.14-legacy,
13.10, 13.11, 13.12. Cosmetic, but it costs every implementer the same ten minutes.

**EDIT-12 — `tool-result-disposition: reflect | return` is justified in §5.3's six-field
table and absent from the `ModelRequest` struct listing**, one line from
`tool-result-media-disposition`, which is a different field.

### 0.3 Checked and found consistent (negative findings)

Worth recording, because these were the previous rounds' fatal areas: the single `surface`
annotation with zone/plane/tier all derived (§2.2, §8.2, LOAD-12/13) has **no residual
path-based table anywhere**; the atom sets sum correctly (8 catalogue + 7 run-state) and
every legal position is annotated; node kinds (8), channel kinds (6) and the one edge type
survive the `stall:`/`max-transitions` deletions with VAL-2 correctly repointed at
`budget.turns`; the air-gap badge lists exactly six traps matching the six survivors; §12.1
lists exactly seven CI gates; §11.1's "nine files you edit" matches nine `[EDIT n]` markers;
§6.3's groups sum to 36; and §4.5's regenerated report is arithmetically consistent with
`verdict()` (0.83 [0.76, 0.89] correctly reads UNDECIDED against 0.80).

---

## 1. Architectural decisions

### 1.1 Representation and the loader

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-1** | The **folder-and-file tree is the native form**; `canonical.json` is a derived, deletable index. `gaia-ai-runtime` executes the tree. | canonical.json as source of truth (every prior universal format); a required build step (Eve) | D2. A build artifact as a prerequisite makes the format a compiler target rather than an authoring surface, and Eve fails its own cold-start test by construction (§3.1). |
| **AD-2** | **Typed Expansion (EXP-1..EXP-11)**, not the unqualified slogan. Expansion form is declared per field by the schema (`dir \| payload \| none`); the fold is disjoint union; order is in-band as `NN-name.ext`. | "any directory is exactly a field"; last-wins; `_order.yaml` manifests; CUE's meet | Six shipping systems implement the slogan and disagree mutually on ordering, precedence and collisions (§1.3). CUE's `a & a = a` unifies silently — PACT errors. Under D18 a git diff is a review surface, so a silent agreeing merge makes "where did this come from?" unanswerable. |
| **AD-3** | **`explode` is partial and says so.** A document is always representable as one file; not always as a tree. Keys outside the portable alphabet fail loudly. | key mangling; restricting what may be imported | Both alternatives break a thesis invariant (T7 silent loss / P-3 lossless import). Proven on ext4 (§13.1). AC-1.2′. |
| **AD-4** | **The core schema is compiled into the binary and sha256-verified at startup.** Workspace extension only via additive `spec/extensions/*.yaml` that may introduce `x-` fields only and may never set `open`/`surface`/`tier` on a core field. `$PACT_SPEC` removed from release builds. | schema discovered by walking up from the target (shipped today at `pact-cli/src/main.rs:117-130`) | The schema **is** the blast-radius classifier's rule table. A discoverable rule table is not a defence — a shared repo containing `spec/schema.yaml` re-annotates `policy` as `S-GEN` and deleting the approval policy auto-applies at CLASS-1 (LOAD-13). |
| **AD-5** | **Blob integrity is exactly the signature over `workspace-digest`, and no stronger.** Blob bytes fold into `node-digest → doc-digest → workspace-digest` at load. | `blobs.lock` (a second signed manifest) | A second Merkle tree anchoring what the first anchors, defeated in both designs by the same one thing; it shipped its own re-bless bypass (`--write-blobs` as the mandatory machine-applicable fix) and put a sha256 manifest on the D13 persona's review surface. Residual stated at §13.15.1 (Y6). |
| **AD-6** | **One reference syntax**: workspace-absolute paths (`/evals/suite.yaml`) plus bare-name-by-kind sugar with a normative resolution table. `..`, `#fragment`, URLs and OS paths forbidden. Ambiguous or unresolved names are errors naming every candidate. Actions are `<tool>/<action>`. | seven ad-hoc spellings (R2); first-wins shadowing | Three of R2's spellings were rejected by LOAD-1's own rule, so the flagship `agent.yaml` did not load. First-wins is the shadowing channel by which a learning cycle displaces a governed skill (§1.8, §8.2). |
| **AD-7** | **`workspace-id` (ULID, minted by `pact init`) is the tenancy key; `at-digest` is the version pointer and is never compared for trust.** | `origin.workspace-digest` as the tenancy key | `workspace-digest` moves on every commit, and a learning-enabled workspace changes files continuously — so either evidence counters never accumulate (§8.6's `n ≥ 100` retirement can never fire) or `ESC-UNTRUSTED` fires on the workspace's own week-old evidence (§1.9, Y17). |
| **AD-8** | **YAML 1.2 core schema only**, type-directed coercion, duplicate keys an error at every level with **no fallback reader**, no anchors/aliases/merge keys, versions string-typed. Block style, with one-line flow maps of scalars permitted. | permissive parse-then-retry (roo-code's `uniqueKeys: true` defeated by its own `catch → JSON.parse`) | A hardened parser with a permissive fallback is not hardened. `version: 1.10` parses to the float `1.1` in every core-schema parser tested (§1.5). |
| **AD-9** | **Every diagnostic carries seven fields including a machine-applicable `fix-patch`**; all errors in one pass by default; no implementation frames; no programmer jargon; `expected:` lists canonical names only. | KCL's design minus `suggested_replacement`; CUE's stop-on-first-eval-error | FR-1.3.2 makes a diagnostic without a fix structurally impossible. Half of Pkl's error goldens append `pkl:base` frames, from which a support lead concludes the tool is broken (§1.6). |

### 1.2 The document model

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-10** | **Eleven kinds, closed.** Workspace, Agent, Graph, Tool, Skill, Resource, EvalSuite, Policy, Profile, ModelCatalog, Learning. | sixteen kinds (Dataset, EvalCase, Variant, Lock, Trace as kinds) | Anything that *is* a field gets its directory form free from T5; declaring it a kind as well is the slot table T5 abolishes, and it gave EXP-6 two mutually exclusive readings on `evals/cases/` and `variants/` (X15). |
| **AD-11** | **ONE per-field annotation — `surface` — from which zone, π_contract and blast class are all computed.** | three overlapping partitions (`plane` 5–7 values, `surface` 8, a path-based zone table) with no stated consistency rule | Makes H2 a theorem instead of a bet (no S-GEN/S-ROUTE/S-CTRL/S-TOPO edit can move `contract-digest`), makes `class(diff) == class(collapse/explode(diff))` a theorem, restores D22(c) reachability for `uses`/`team`, and removes the five-line agent's structural exclusion from learning (X14, §8.2). |
| **AD-12** | **`tier: core \| expert` is a first-class schema property, and it fails CLOSED** (a missing annotation means `expert`). Expert-tier rules do not fire on a document using no expert-tier field. | a `no-code` badge that checks for the absence of `impl: code` | That badge checks the wrong thing: a workspace can be 100% code-free and still unauthorable by a support lead — which `examples/refund-desk` failing R2 eleven times demonstrated. Tiering is the only mechanism by which D14 is *checkable* (X13, §2.8). |
| **AD-13** | **One name per field, and it is the plain-language one.** `tools` + `skills` merge into `uses:`. Alias tables exist only inside importers. | a dual vocabulary (`output_schema` canonical / `answers-with` authoring) | Non-injective (`tools` and `skills` both mapped to `uses`, so `explode` had no inverse and AC-1.2′ was unsatisfiable), and it admitted a two-line silent-drop edit with zero diagnostics (X1). Cost accepted at AD-T5. |
| **AD-14** | **`x-` blocks are preserved in the IR and `canonical.json` and are NEVER emitted into any substrate, under any declaration.** Export-path keys validated against the portable alphabet. | `x-passthrough: {namespace, effect}` opt-in declared by an adapter's own lattice | The opt-in was an RCE reachable through `pip install pact-adapter-goose`: consent came from an out-of-tree lattice file plus a `pact.lock` entry `resolve` had just written, and air-gap trap (vi) asserted against that same entry — circular. AC-1.3 asks for **preservation, not projection**; D15 forbids projection (Y5). |
| **AD-15** | **Digests are a Merkle tree** over the canonical document plus every referenced blob, with transitive coverage of references. | hashing the tree bytes | Byte-hashing makes the digest depend on comments and line endings, so every reformat invalidates every lockfile and signature (§3.3). |

### 1.3 Contract, catalogue and resolver

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-16** | **Tier-0 typed predicate atoms only. No second predicate language in v1.** 8 catalogue atoms + 7 run-state atoms, one combinator grammar, legal positions annotated per atom. | Tier-1 CEL as an expert escape | CEL has no in-language error representation, non-deterministic `&&` ordering, check-time numeric-type failures a non-coder cannot diagnose, and would need a vendored evaluator in an air-gapped Rust core — to serve a tier D14 says must never be necessary. A `when:` needing arithmetic is **H6 falsified**, and the response is one new typed atom (Y4, §4.1). |
| **AD-17** | **`because:` is document-scoped and schema-required once per predicate document**; the resolver generates the per-atom explanation mechanically. Per-atom `because:` is expert tier. | mandatory per-atom `because:` | Fanning one string across six atoms prints literal nonsense in the one output fail-then-recommend exists to make legible; requiring one each makes the flat six-checkbox form unwritable (§4.1). |
| **AD-18** | **The model catalogue is distribution-supplied and signed** (`pact:catalog/builtin`). A workspace catalogue is an optional override layer. **Benchmark predicates are expert tier.** | the author writes `models/catalog.yaml`, including `scores: {MMLU: "> 80"}` on the no-code surface | A support lead cannot hand-enter provenance per figure, and §4.2 proves no open catalogue carries a benchmark or a latency figure at all — so the atom can only ever empty the candidate set (X21, §4.2). |
| **AD-19** | **`reasoning` is a closed ordered ladder** (`simple < steady < careful < deep`), a catalogue-row field with provenance, derived by a published versioned derivation from figures the distribution already measures. **UNKNOWN does not filter at core tier**; it binds and ranks last. | deleting `reasoning` from Tier 0 | It is the first line of the first predicate file an author writes and it bound against nothing — the only reachable outcomes were "matches everything" and "matches nothing". Deleting it leaves the core predicate set with no quality axis, making D11's ranking purely cost-based (Y12). Residual: **AD-R2**. |
| **AD-20** | **Every core SLO spelling expands to BOTH a reported objective AND an enforced budget dimension**, flowed verbatim onto the desugared `team:` graph. `stop-after: {tool-calls, turns}` is a core spelling. | core `limits:` as reporting targets only | X24's own rationale was that the supervisor plus two specialists could run past `cost-per-request-under: 0.05 USD` — and X24 applied its fix to `limits.budget`, a field the core tier cannot write. The identical failure survived one tier up (Y10, §4.3). |
| **AD-21** | **One budget record, one key set, on one construct**: `budget:` on any node (`tokens, cost, wallclock, tool-calls, turns, handoffs, child-runs`) plus `graph.bounds:` for structural limits only. `learning.cycle-limits` for meta-budgets. | five budget vocabularies with three duplicate dimensions | The desugared team graph silently dropped the author's cost cap (X24). |
| **AD-22** | **One loop counter, defined: `turns` = one model request issued by the node that owns the loop.** `handoffs` and `child-runs` defined in the same table. A halted run names exactly one binding constraint with its `file:line`. | four undefined counters (`max-transitions`, `max-iterations`, `turns`, `loop-bound`) | A support lead who wrote three lines got a halt naming a generated field, in a graph they never saw — and VAL-2 named a field X24 had already abolished (Y20). |
| **AD-23** | **`feel:` expands to p90 from a builtin profile document printed in full; SLO percentiles default to `source: probe`.** `profiles/*.yaml` is optional and overriding. | `samples: {source: eval-suite}` default; p95 | Composed with the min-n rule, a ten-case suite could never satisfy its own latency objective, and the offered fix cost ~50 minutes and 5 USD on every `pact resolve`. Decoupling the two sample streams means eval-case count never gates a percentile (§4.3). |
| **AD-24** | **Cost is computed per model call from a `CallCostRecord`** with a full token vector and integer micro-dollars, using the **response** model. | summing tokens then applying a price | Five context-length breakpoints and three service tiers are present in the shipped catalogue; the tier list must be read from the catalogue, not hardcoded (§4.3b). |
| **AD-25** | **`usage.*` is a lattice family and `cost-known: false` is a pre-execution `degraded` entry naming the adapter — never a run-time SLO failure.** Adapters MUST force the provider flag where one exists (langgraph MUST set `stream_usage=True`). | fail a cost SLO closed at run time unless `allow-loss: [cost-unknown]` | Verified: `langchain_openai` auto-enables `stream_usage` **only** when no custom `base_url` is set, so pointed at a local vLLM the identical tree passes the cost cap on one adapter and fails on the other for a reason that has nothing to do with the agent — D28 failure mode #2 in one line (Y14). |
| **AD-26** | **Fail-then-recommend, with a closed mechanism set each TRIED-with-delta or NOT-TRIED-with-reason**, including `collapse-team` and `decomposition`. Every claim of "X% of the reference" prints both ratios or the `not-measurable` record. | a FAIL report that is a list of failing metrics | D11 makes the resolver a recommender. Without the closed set the author is told to try what has been tried and never told what is cheaper — the flagship homogeneous topology runs at up to 3× the cost of the collapsed single agent and R4 never mentioned it (Y27, §4.5). |
| **AD-27** | **Resolver-proposed decomposition has no v1 expression. Decomposition is author-declared, full stop.** The resistant-task taxonomy survives as a named prior in the FAIL report. | a matched single-step probe estimating a capability gap `G` against `G* = 0.25` | No oracle (nothing in §6 can label a sub-step of a decomposition invented at resolve time); `Ĝ`'s 95% half-width is ±0.49 at n=8 and ±0.21 at n=44, every author-scale n wider than `G*`; the law is bivariate and was applied to k steps; and the cited law is about **fusion**, not decomposition (Y3, §13.5). |
| **AD-28** | **The reflector pre-flight is ONE free check** — `RB-D format` against a profile floor (builtin 0.90) — and RES-8 runs at the full authored budget under a **sequential stop** (`stop-after-no-accept`, builtin 12). | `reflect-bench` (5 tracks, 3 baselines, FX-1..6, CAL-1..5) and an `r̂`-scaled budget | `r̂` is a per-proposal yield, so `evals × r̂` makes yield ∝ `B·r̂²` — 4.4% of full-budget yield while the report claimed 21%. And the instrument was priced at ≥180 items each costing a full gated optimisation run, as a **v1 precondition** for a gate the document shipped with `n = 0` and no threshold (Y2, §6.5b). |
| **AD-29** | **`pact.lock` records the full statistical envelope**: `verdict()` output, per-metric `n_m`/coverage/ε/class/score-path, `population:`, `bar:` provenance, judge TPR/TNR with n and LCB, canary FPR, labeller record, `endpoint-class-per-role` over all six roles, resolved `settings`, resolved `output-mode`, ledger digests. Both recovery ratios are **records decided by `verdict()`**, never scalars. | bare two-decimal scalars | A ratio of two pass rates at p ≈ 0.85 has a 95% half-width of ±0.176 at n=44 — against AC-3.1's 0.05 margin. The flagship claim was undecidable at every corpus size the document contemplates while the lock printed it as a fact (§4.5, §4.6). |

### 1.4 Lowering, the adapter ABI, and the wire

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-30** | **Two levels: transport lowering (mandatory, always faithful) and native feature satisfaction (opt-in per feature, every `native` claim carrying a CTS attestation id).** Native project emission is an export artifact, deferred to v1.1 and never a run path. | "native lowering" as a peer execution path | R1 specified an ABI with no verb capable of executing one, making `level: native` unfalsifiable. A lattice entry `{level: native}` without `attested-by:` is now a validation error in the adapter's own lattice (§5.1). |
| **AD-31** | **Three execution verbs** — `model_call`, `model_stream`, `tool_call` — plus lifecycle. `ctx` is a closed typed host-owned record. **A fourth verb (`model_call_raw`) is explicitly rejected.** | a raw provider-payload escape verb | It would let any adapter claim conformance by punting to a provider-specific payload, destroying P-1 and reopening the opaque wrapping D15 forbids. The correct behaviour is a lattice `unsupported` entry plus fail-then-recommend (§5.2, §5.7). |
| **AD-32** | **The realtime/duplex ABI is deleted from v1.** `session: turns \| duplex` survives as a **contract** declaration resolving through fail-then-recommend to the cascade. | four realtime verbs + ~15 config fields, mandatory for `session: duplex` | There is no local duplex model in the corpus, so they would ship with zero conformance coverage and make `air-gapped` and `modality:audio` mutually unsatisfiable. Purely additive to re-admit (X20, §5.2b). |
| **AD-33** | **`settings:` is a closed provider-neutral request-parameter record** with a normative default table shipped as a builtin profile document, recorded resolved in `pact.lock`. `max-tokens` and `thinking` are core tier. | node-common `sampling: {n, temperature}` only | Verified: pydantic-ai sends `max_tokens=4096` for **every** Anthropic model while langchain-anthropic reads the model profile — so identical trees truncate on one arm and not the other, a straight D27 failure caused by two framework literals PACT never chose. Also, R3's own thinking-signature CTS fixture was unauthorable because nothing enabled extended thinking (Y13). |
| **AD-34** | **`output-mode` has a normative default table** keyed on `(declared shape kind, function-tools non-empty)`, and `answers-with-mode:` is a **sibling** field, never a key inside the shape map. | adapter-chosen default; `mode:` inside `answers-with` | The single most behaviour-determining wire parameter was adapter-chosen **for the D20 artifact**, and the two reachable choices differ by far more than any ε L2 admits. `mode:` inside a `map<shape>` is indistinguishable from an output field named `mode` (Y25, §5.3d). |
| **AD-35** | **PACT's harness performs the tool-result media split**, so the canonical transcript is identical across arms and only the wire projection differs. `tool-result-media-disposition` is lattice-keyed on `(adapter, provider, api-surface)`. | encode one wire shape in the IR | One provider has **three** distinct wire shapes for a tool result carrying media, verified in source. §12.2's assertion (iii) — the test the draft says decides everything — could not pass. D16 makes this the hot path at 318 tool calls per OSWorld task (Y25, §5.4). |
| **AD-36** | **Two content parts R2 lacked: `reasoning` (opaque provider-keyed blob with signature) and `malformed-tool-call`.** Mapping each framework's error channel into the latter is a conformance obligation. | one text part; `thinking` as a request parameter only | Without `reasoning`, a reconstructed transcript sends `<thinking>…</thinking>` as ordinary assistant text — a different context and a different bill. Without `malformed-tool-call`, the same model on the same case scores 0 on one adapter and 1 on the other because LangChain routes a parse failure to `invalid_tool_calls` while pydantic-ai keeps it (§5.3a). |
| **AD-37** | **One media part for all four modalities** (open IANA type + tagged source union incl. `provider-ref`), with `fetch:` defaults normative and fail-closed, RFC1918/link-local/loopback refused unconditionally, and a `url` source with no local bytes a validation error. | per-modality part types (LangChain's five parallel blocks) | Two independent projects converged on this shape; per-modality hierarchies keep needing new members. `provider-ref` is required because Anthropic emits no inline media block at all. The `fetch:` rules remove the token-accounting SSRF entirely rather than policing it (§5.4). |
| **AD-38** | **Prompt-cache breakpoints are first-class IR** (`cache-boundaries:` in three positions, `cache.breakpoints` in the lattice, `reuse-context:` as the no-code surface), and prefix **stability** is a load-time property: `after: tool-manifest` is an error when any in-scope `uses:` entry carries `available-when:` unless the gating is monotone-additive. | `instructions` carrying `static\|dynamic` provenance alone | The substrate has four cache controls, not one; the arithmetic on §11's own workspace is ~5× billed input tokens, which is D28 failure mode #3 in the document's own example. And `available-when:` mutates the tool manifest by design, invalidating the breakpoint the same round added (§5.3b, Y25). |
| **AD-39** | **`sampling: {n}` canonicalises to a FOLD; the map-over-k lowering is the emulated form**, gated on `sampling.native-n` in the lattice. | mandating the map lowering for bijection | LangChain bills the prompt **once** for k choices; PACT's mandated map billed it k times — ~5× input tokens against a hand-written `ChatOpenAI(n=5)` baseline, on a pattern AC-5.2 requires PACT to ship (Y25, §7.7). |
| **AD-40** | **Four harness invariants**: exactly-once across an approval boundary (`@task` granularity mandated only for `effects: at-most-once \| external`, with a barrier-group lowering for read-only batches); loop-body determinism; four HITL decision kinds with MRTR as the resume wire shape; `halt.reason: refusal` terminal. | `@task` for every side-effecting step | Native LangGraph runs a whole parallel batch in one node and one checkpoint write; R2's rule made it three serialised round trips per turn against a real durable store — and `run.overhead-ms` was *defined* to exclude checkpoint I/O, so the one number PACT is judged on could not see the cost the mandate introduced (§5.8). |
| **AD-41** | **`native-tools`/`provider-options` deleted; `web-search`, `code-interpreter` and `web-scrape` removed from the `capability` atom in v1.** Computer use survives via a PACT-owned sandbox action vocabulary with a pinned provider tool version. | keep the capability atoms and a typed provider escape | An author could require `web-search`, have RES-3 filter on it, bind a model that has it, **and nothing could turn it on** — an unenforceable declared control, which T7 says is worse than an absent one. `provider-options` was the untyped hole through which any adapter could claim an undescribed capability (Y25, §5.3). |
| **AD-42** | **Adapter roster re-cut on seam evidence**: Tier 1 = pydantic-ai, langgraph, vercel-ai, **anthropic-sdk-python**, openai-agents. `claude-agent-sdk` is **cut** (no model/tool transport seam — it is a client for the `claude` CLI). Session lowering deferred as opaque wrapping. | claude-agent-sdk as the Anthropic representative | Transport lowering there means reimplementing Claude Code. The Anthropic adapter is additionally pinned to `beta.messages.parse/.stream` and forbidden `_beta_session_runner` (a hosted server-side loop with server-side permission evaluation), asserted by a CI import-graph test (X9, §5.6). |
| **AD-43** | **`reach:` on a runtime-owned MCP connection is a load-time error** naming the platform team; `egress.enforced` is a lattice feature; a declared-but-unenforced capability manifest fails the `no-code` badge. | a decorative `reach: {may-contact: […]}` on the tool that moves money | PACT neither launches nor sandboxes a runtime-owned MCP server, so there is no sandbox to configure. Under T7 an unenforceable declared control is worse than an absent one, because the author stops looking (§5.7, §11.5). |

### 1.5 Run-scoped inputs and the approval path

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-44** | **`run-inputs:` on the Agent + `bind:` on a tool action**, where `bind:` removes the property from the model-visible schema. Instruction interpolation restricted to `run-inputs.*`. `bind:` is `S-EXEC`. | expose the argument and let the model choose it | Porting pydantic-ai's canonical example converts a structurally impossible privilege escalation into a live one: a prompt-injected ticket reading "for order 99999" reads another customer's data. ~70% of the highest-priority framework's own examples were otherwise unimportable (X19, §5.10). |
| **AD-45** | **VAL-11 is split by ARGUMENT ROLE.** `subject` arguments (`customer-id`, `account`) MUST be host-bound; `inspected` arguments (`amount`) MUST NOT be, and are the only role a predicate may read. | "every argument named in an approval predicate must be host-bound" | That rule rejected the flagship approval policy, and its only possible fix deleted the capability — a host-bound amount means the model can never propose a refund figure. VAL-11's own rationale was describing the purpose of an approval gate (Y9). |
| **AD-46** | **The approval request is a STRUCTURED RECORD**; authored prose and argument values render in separate labelled regions, model-chosen values as quoted, length-capped, control-stripped data. **VAL-12** forbids a free-text model-chosen argument in an `ask:`. | `ask: "Approve a {tool-arg.amount} refund for order {tool-arg.order-number}?"` | Every structural control held and the outcome was the one they exist to prevent, because the last hop into the only human control in the system was string concatenation (Y18). |
| **AD-47** | **VAL-13 — run-input provenance is a typed static dataflow across delegation boundaries.** A non-entry node's run-inputs may only be a graph literal, an explicit `from: parent.run-inputs.*` projection, or a declared host channel. TOPO-3 is restated over `(tool, bind:, available-when:)`. | protect the entry agent only | `bind:` lives on the shared Tool document, so `run-inputs.customer-id` resolves against whichever agent is calling. Adding one line to `team:` produced a child whose only run-input supplier was the supervisor's route node — i.e. the model (§5.10). |
| **AD-48** | **A channel whose effective trust is `model` or `external` may not be read by any `available-when:` predicate**, and `sanitises: yes` does not lower it for a tool carrying `spends-money: yes`. | apply the taint rule to control flow only | A gate on the reachable **capability set** (S-CAP, the most-protected surface) was enforced more weakly than a gate on control flow. The exploit reaches the money tool through a merge channel a specialist writes from customer text (§4.1). |

### 1.6 Evaluation and statistics

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-49** | **One EvalSuite document, five on-ramps as sugar**, with a **normative `expect:` desugaring table keyed on the declared shape in `answers-with`** and declared normalisation. `answers-must-match` deleted. | "assertions come from the shape of `expect`" | Whether a free-text field silently becomes a judged assertion decides whether the whole `must-pass` bar is legal, and AC-4.5 is uncheckable by an author who cannot see which cases invoke a judge. `answers-must-match` was this table, guessed at (§6.1). |
| **AD-50** | **One assertion vocabulary.** `rules:`, `must-also:` and `metrics:` take the same records; `uri:` is reserved for external providers and is expert tier; assertions deduplicate by `(assertion-id, case-id)`, which gives `must-pass` a defined denominator. | four normative spellings for "was `issue-refund` called after `look-up-order`?" | §11 used two of them simultaneously, leaving undefined whether one failure counted once or twice against the bar that gates D11's binding decision (X23). **Not yet fully discharged — see EDIT-8.** |
| **AD-51** | **An unmatched plain-language rule is an ERROR WITH A ONE-KEYSTROKE FIX**, not a rejection: the diagnostic names the judge cost and carries a `fix-patch` converting it to `judged:`. | reject free sentences (R2); "try deterministic, else g_eval" (R1) | R1 had no mechanism — the loader is normatively incapable of running a model. R2's rejection is how the D20 artifact stopped loading. Prefix-matching against a closed set *is* decidable at load time (§6.2). |
| **AD-52** | **36 deterministic `pact:` assertions in the Rust core**, including a new **environment** group (`http`, `file-contains`, `shell-exit-code`, `sandbox-file-contains`). Deterministic assertions run first; judges only on what remains. | DeepEval alone | DeepEval walls its deterministic `Scorer` layer off from `evaluate()`, so AC-4.5 is unreachable on it. Eve's agentic assertion surface is richer and entirely deterministic and is adopted. Computer-use evals must grade **environment final state**, which nothing in the corpus expresses declaratively (§6.3). |
| **AD-53** | **51/56 DeepEval parity with five shims**; the five legacy `ragas.py` wrappers are excluded by design and replaced by a first-class `ragas:` provider. Four hard provider rules (telemetry off by settings-assertion, never export via `dag_to_dict`, reject `model: null`, do not normalise DeepEval's numeric semantics). | 56/56 with five shims (R1) | Verified refutation. `dag_to_dict`'s `_maybe_jsonify` silently drops rubrics, tools and schemas with **no warning channel at all**; `initialize_model(None)` falls through to OpenAI, breaking air-gapped runs (X10, §6.4). |
| **AD-54** | **Judge hardening is honest**: TPR **and** TNR each with their own n, gated on the one-sided 95% **lower bound** ≥ 0.70; a shipped mandatory **canary suite** of the ten measured master keys at every judge binding; CoT and majority voting explicitly **not** counted as hardening. | a scalar `agreement` figure; CoT + voting as hardening | An always-`pass` judge scores the base rate and clears a 0.70 scalar gate with TNR 0.0. Measured, CoT+5-vote **raises** worst-case FPR (12.6\|31.0 → 40.4\|91.3 on the smaller judge). R3's own worked figure `0.74 [0.61, 0.85] on n=40` fails its own gate (X11, §6.5, §6.9-A′.2). |
| **AD-55** | **A judged rule gates only when calibrated ON THAT RULE** with author labels; otherwise it loads `severity: soft` and says so. The labelling instrument is recorded (`labelled-by`, `labellers.n`, κ) and **caps** certifiable agreement. | calibrate on the distribution's shipped corpus | A judge can be excellent at shipped rubrics and arbitrary at *"one sentence a customer can understand"*, and the number in `pact.lock` looked identical either way. A 90%-consistent labeller bounds attainable TPR at 0.90 (Y26, §6.5). |
| **AD-56** | **Where no admissible LOCAL second judge exists, a judged rule loads non-gating. Never self-graded, never silently egressed.** `allow-egress:` is a `workspace.yaml` list over all six model roles. | egress gated on the reflector role only | With one served model the admissible-judge search finds a **hosted** row and POSTs every eval case off-box on every resolve, while `pact check` still awards the `air-gapped` badge because the trap inspected `models.reflector`. The judge sees strictly more data than the reflector ever did (Y16, §6.5a). |
| **AD-57** | **`verdict(point, interval, threshold, k)` is ONE function** used by the FAIL path, the RECOMMENDED path, ALSO-CONSIDERED, the learning obligations and the lockfile writer. Certification is `LCB ≥ θ`, stated once. `UNDECIDED` is a first-class verdict. | report-level formatting of point estimates | R2's own flagship report printed `passes at 0.83 [0.76, 0.89]` against a 0.80 bar and wrote it into the lock. Interval discipline held until it blocked the demo, then quietly reverted. A CI test now parses every code fence and re-derives its verdicts (X22, §4.5, §6.9). |
| **AD-58a** | **`minimum-credible-bar` is scoped to the money-moving ASSERTION SUBSET, not the suite bar.** Consequential assertions must reach 1.00 on every gating case; the suite bar stays as `pact init` chose it. | a 0.90 floor on the whole suite for any agent with an approval gate | Resolves EDIT-1. The old rule made the flagship uncertifiable and tripled authoring cost, while *also* being weaker where it mattered — a money-moving mistake could hide inside a 90% average. |
| **AD-58** | **`must-pass` is chosen ONCE at `pact init` from a TARGET case count, is sticky, is printed in the verdict line, and is never silently re-derived.** A profile floor (`minimum-credible-bar`, builtin 0.90) applies to consequential agents. | "`must-pass` defaults from the observed n" | Both readings were fatal: under one PASS is unsatisfiable by construction; under the other it is a tautology. On real tau-bench data an 8-case derived bar has a 5th–95th percentile spread of **[0.111, 0.688]**. And a bar that is a function of n **rises as the author adds cases**, teaching the one behaviour that kills eval suites (Y21). The floor's scope is resolved by **AD-58a**. |
| **AD-59** | **Minimum gating-case counts are enforced at VALIDATE time**, from a published table, with the three-fix diagnostic pattern. | a `must-pass` bar with no minimum-n rule (R2: `n ≥ 1` was legal) | `pact resolve` on the §11 workspace returned UNDECIDED forever and the only escape was `--allow-unverified`, i.e. binding with no verdict at all — the silent degradation T7 forbids, reached by the front door (§6.9-A). |
| **AD-60** | **Per-split floors are derived from the decision each split is read for**: Clopper–Pearson for `held-out`, the same at the judge gate **doubled and per class** for `calibration`, an exact **sign test on discordant pairs** for `validation` (d ≥ 5 at k=1, d ≥ 9 at k=14), and a **consumption** floor for `train` that certifies nothing. Ratios are **optimizer-declared**, never schema-fixed. | "the same table as §6.9-A" for all four; DSPy's 20/80 in the schema | §6.9-A answers the question only `held-out` is read for. Fixing 20/80 in the schema would misconfigure PACT's own reference optimiser (GEPA declares the opposite convention and discourages valsets above 35) by ~4× (§6.9-A′). |
| **AD-61** | **Intervals are over CASE MEANS with clustered standard errors on `case-id`**; `repeats` may enter latency counts but never an accuracy denominator; `cases` and `runs` are two distinct fields everywhere; below n ≈ 30, Clopper–Pearson or a t-interval replaces bare bootstrap and the method is named in the lock. | n = cases × repeats | Understates the half-width by up to √3, and within-case correlation is high precisely because a model confidently wrong about a four-clause policy is wrong all three times. inspect_ai's estimator and its two guards are ported rather than rewritten (§6.9-B). |
| **AD-62** | **`verdict()` decides PER METRIC on `n_m`, not on the suite `n`**, and a suite cannot be more decided than its least-decided gating metric. **ε is a property of `(metric, judge-binding, score-path)`** with a class-derived floor (D/Q/J/B/E). | one suite-level `(ε, n)` pair | Measured on tau-bench: one metric covers 3–4 of 50 cases with a 66.7 pp spread while another covers 91% with 2.6 pp. `n ≥ 158` is sufficient for exactly one thing — 100% coverage at p̂ ≥ 0.70. And `deepeval:g_eval`'s per-case quantum is ~0 hosted and **0.100 air-gapped**, so a CI verdict does not transfer to the customer's install (§10.1). |
| **AD-63** | **Emitting a lockfile on UNDECIDED is a PROFILE decision** (`requires-verdict: pass \| not-fail`), carried into the lock and the A2A card. **UNDECIDED → FAIL is automatic; UNDECIDED → PASS never is.** | `--allow-unverified` | The flag bound a model with no verdict at all. And the automatic upgrade closed the oracle loop through the system under test: the traces that decide whether the model passes are produced by that model and filtered by a human who only ever sees what it produced (Y23, §6.9-C). |
| **AD-64** | **The held-out / validation / calibration query ledger lives in the AUTHORED TREE (`heldout.ledger`, S-GOV, prev-digest chained), with resolve-time rollback detection and a hard query budget.** Multiplicity is **cumulative** over the ledger. `k` is **counted by the eval runner**, never declared by the optimiser. | a ledger under `.pact/`; `candidate-count` self-reported | `.pact/` is mandated deletable and excluded from every digest, so `rm -rf .pact/` reset cumulative multiplicity with an identical `workspace-digest` and every signature still verifying. And a vendor declaring `candidate-count: 1` while internally ranking 200 gets α = 0.05 against a 0.9988 false-accept probability (Y17, Y26, §6.9-D). |
| **AD-65** | **Every gating corpus declares its `population:`** (`authored-enumeration \| promoted-traces \| sampled-frame`), carried into the lock, the report and the A2A card, with the honest sentence printed. **Coverage against a self-authored artifact is labelled as such.** | publish a Clopper–Pearson interval as a capability claim | The cases were not drawn — a support lead enumerated the scenarios she thought of. Coverage reports `4 of 4 clauses covered` against a `SKILL.md` that may transcribe four of nine, so the agent and the oracle share the identical blind spot (Y22, §6.9-F, §6.9a). |
| **AD-66** | **Promoted traces land in QUARANTINE and never gate**; traces are append-only, integrity-chained and terminal-record-signed; promotion is scoped to `(workspace-id, run-id)` and the origin's redaction-policy digest travels in the signed segment; `pact promote` records the review denominator. | "a second disjoint validation run" as an alternative to a human; trace-id as an authorisation token | Anything with write access to `.pact/traces/` could append fabricated records that a second automated run would confirm. On a shared host there is ONE runtime key, so a signature proves "a runtime wrote this", not "this run belongs to this workspace" (§6.6, Y17). |

### 1.7 Topology and loop

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-67** | **ONE construct (`Graph`), TWO authoring surfaces (`team:`, `loop:`), TWO reconcilers (`node.on-reentry`, `channel.scope`).** | separate topology and loop constructs | A framework that had both is deleting one (ADK); frameworks that ship one express both; Bud already compiles topology → graph, so D3's superset obligation *requires* it; and two constructs means two validators, two optimisers, two checkpointers and two CTS suites (§7.1). |
| **AD-68** | **Eight node kinds, one edge type with four fields, six channel kinds.** `join` is an edge field, not a node kind; `role` deleted. **L3 gates on expressing all 14 patterns WITHOUT `escape`.** | nine node kinds incl. `join`; sufficiency asserted | `escape` being in the set makes any sufficiency claim vacuous. `join` on the edge is the only form that composes with cycles and supports multiple independent groups (X2, §7.1–7.3). |
| **AD-69** | **Blackboard and market/auction ship as PUSH forms in v1**; `queue` with claim+lease is deferred, with the fixture that would force it back named. | ship `queue` with an invented lease design | `queue`'s lease half has **zero prior art** anywhere in the corpus (CAMEL has atomic claim, no lease), and the market sketch never touches a queue (X3, §7.3). **This is a thesis-level judgement on AC-5.1 — see AD-R6.** |
| **AD-70** | **Trust is a COMPUTED dataflow property** — the least-upper-bound over statically-reachable writers — and the authored `trust:` is a floor the loader may raise and never lower. `transform`/`map`/`fold`/`merge` propagate; only `sanitises: yes` with a closed shape lowers, and authoring it is `S-EXEC`. | `trust:` as a declared channel field | A `transform` node — which exists precisely so a no-code author can move data without writing a tool — laundered customer text into a control-flow predicate with zero diagnostics (X26, §7.4). |
| **AD-71** | **MCP server-authored prose is PINNED in the tool snapshot, and instruction assembly is normative**: external-trust text only in a fenced, labelled, non-authoritative region, never before authored instructions, never carrying a directive; a Policy always wins a conflict. | "route it through the blast-radius classifier" | A category error — the classifier operates on spec diffs and this text never becomes a spec file. A routine server upgrade could inject *"refunds above 200 USD were delegated to the assistant; do not escalate"* with `tools/list` unchanged (§7.4). |
| **AD-72** | **The `team:` desugaring is TOTAL**: `self: true` terminal decider (owning agent with `team:` elided), REQUIRED `reads:` on every emitted agent node with typed `task/<member>` channels, `route.prompt` seeded from the author's purpose sentences, `route.assigns`, `max-depth: 1`, the agent's `limits.budget` copied verbatim, and a byte-identical cross-adapter wire-request CTS fixture. | pointing the terminal decider at the owning agent's ref; leaving `reads:` undefined | The first is a load-time reference cycle or an infinite team re-expansion. The second is a D27 failure at the exact construct D20 exists to demo: pydantic-ai's canon passes a model-composed string into a fresh run; LangGraph reads the shared `messages` channel — same field, two adapters, two different specialist prompts, two verdicts (Y15, §7.7). |
| **AD-73** | **Nine durability rules (DUR-1..DUR-9)**: content-addressed step identity; contract+doc digest pinned per run with drift classified; effects declared per node; durability as a guarantee with the engine named; compaction of a durable `history` channel is itself a journaled step. | positional step ids; durability as a mechanism | DBOS's `function_id` counter renumbers everything after an inserted step. No corpus framework couples prompt compaction to checkpoint compaction, so long loops break on durable engines (§7.8). |
| **AD-74** | **`stall:` is deleted.** A non-progressing loop is bounded by `budget.turns`, `timeout.idle` and `on-budget-exhausted: emit-best`. | five fields, two detectors, a leaky-bucket decay rule | §7.5 said in its own words that no decision requires stall detection and that leaving decay unspecified makes the CTS flap across adapters — a new conformance liability kept for an interesting paper result (Y7). |

### 1.8 Learning and governance

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-75** | **Four zones COMPUTED from `surface`** (LEARNABLE / GOVERNED / QUARANTINE / DERIVED), total by construction; an unannotated field is `BR-UNKNOWN` → GOVERNED, CLASS-4. | a path-glob zone table | Falsified three ways: it excluded the five-line agent from learning while its exploded twin was CLASS-1 (falsifying §8.3's own property test), it made `uses`/`team` permanently GOVERNED so D22(c) was unreachable, and it did not match the shipped layout (X14, §8.2). |
| **AD-76** | **Eight effect surfaces; the classifier is `max(rule(surface))` plus escalators.** **Firing ANY escalator ends auto-apply eligibility** (the ceiling is "CLASS-1 with zero escalators"). `ESC-JUDGED` has a CLASS-3 floor. | escalators as +1 increments with a CLASS-2 ceiling | Both named escalators escalated *into* the auto-apply band and changed nothing: a judge-fooling instruction suffix is S-GEN → CLASS-1, +1 → CLASS-2 → auto-applies, signed, with a full audit trail asserting it was proven (X18, §8.3). |
| **AD-77** | **The recorded classification is a CLAIM the Rust core recomputes** from `(signed baseline digest, current tree, compiled-in schema)` on every load, refusing with a typed `ClassMismatch`. The signature covers `(base-digest, result-digest, recomputed-class)`. Recomputation never lives in the learning service. | trust the class the learning service stamped | OBL-1's base-digest CAS proves what the tree *was*, not what the diff *means*. A bug or compromise could remove `policy: approvals` while stamping `{class: CLASS-1}` with a valid signature (§8.3). |
| **AD-78** | **Skill bodies carry SUB-DOCUMENT surfaces.** Normative clauses (list items — numbered **or bulleted** — under a `## Rules`-class heading, or named by a frontmatter `normative:` selector) are `S-EXEC-adjacent` with a CLASS-3 floor and are **immutable under `skill-notes`**. | `skill.body` as one S-GEN field | The shipped `SKILL.md` body **is** the refund policy, in bullets. Deleting *"Personalised items cannot be returned unless faulty"* is ~9% of the file, has no numeral, is not a numbered item and touches no anchor: zero escalators, CLASS-1, auto-applied and signed. An identical sentence in `policies/approvals.yaml` is CLASS-4 (Y19, §8.3a). |
| **AD-79** | **Core-tier learning is `enabled: propose-only` and requires NO splits.** The four-split apparatus, OBL-2's sign test, the judge gate, the ledgers and the regret disclosure are expert tier, entered only by `enabled: applies-safe-changes-itself` (AD-102; `auto-apply: yes` when AD-79 was written). | `learning.enabled: yes` promoting the workspace to expert-tier splits | That made D14's explicit "learning loop enabled" clause require **142–180 gating cases** against a support lead's ~10, with *"keep learning off"* offered as the **first** fix — a direct D14 violation printed as remediation — and the shipped example did not load. Propose-only certifies nothing statistically and therefore needs no statistics (Y8, §8.7). |
| **AD-80** | **The review queue is a specified object (QUEUE-1..7)**: hard depth cap = `cycle-limits.per-cycle` (4); a deliberately weak recall-tuned pre-filter that certifies nothing; **three-valued** typed outcomes (`accepted \| edited-then-accepted \| rejected`) with a closed reason enum in an authored `proposals.ledger`; empty cycles recorded; rubber-stamping detected as a warning; no proposal class permanently suppressed; the diff seen in the editor/PR view. | "a person looks at it" | Unbounded, the measured destination is a 46.2–96.2% override rate. Binary approve/discard discards the highest-information outcome. And without a rejection record H37 is unfalsifiable and AC-5.5 has no core-tier mechanism. Google's production analogue *lowered* model precision 50% → 40% because reviewers could reject, and end-to-end value rose 4.9% → 7.5% (§8.7a). |
| **AD-81** | **Eight auto-apply obligations**, with **OBL-3's ε COMPUTED** (`max(class quantum, null band at n_heldout)`) and OBL-3 declared **NON-GATING with auto-apply disabled** when it exceeds `smallest-regression-worth-catching`; OBL-3 also runs against the frozen drift baseline. OBL-2 moves to a proposer-invisible `validation-accept` sub-slice. | a fixed ε; OBL-2 on the selection split | At the 16-case held-out floor the two-run null band is **0.346**, so a candidate whose true score dropped 30 points passed every week — 20 weeks of that is ~60 points below the signed baseline with every obligation passing. And GEPA returns the argmax over validation, so a sign test on that split does not have level 0.05 (Y26, §8.5). |
| **AD-82** | **Cumulative drift against a frozen signed baseline over a 10-generation window**, and **`pact approve --baseline` is the sole writer of `drift.baseline`**, requiring approval over the **rendered delta**, not the digest. | a hand-editable `baseline:` field | The PR diff is a single hex string; a one-line edit committed as "refresh learning baseline" disarms the design's answer to the strongest cited attack on incremental self-modification (§8.4). |
| **AD-83** | **A closed operator set for topology self-modification**, with `ADD-AGENT` unconditionally CLASS-4, writing a template whose contract fields are **immutable references to the parent's** — mechanising TOPO-3 rather than asserting it. | widening the LEARNABLE glob to `agents/**` | That single-character change would make `policy`, `uses`, `needs`, `limits`, `evals`, `model` and `models` (including the judge role) all optimiser-writable, converting the governance design into decoration in one commit (§8.5). |
| **AD-84** | **Held-out is mounted into the eval-runner process only**; `fs.read`/`fs.write` are denied on the workspace root by default; **any `fs.*` scope intersecting a GOVERNED canonical path is a VALIDATION ERROR, not a CLASS-4 review item.** | held-out protected by a path allow-list + CLASS-4 review | A `fs.read: [evals/]` "look up past decisions" tool passes its own acceptance suite trivially, one human approves a read-only lookup, and every eval run then reads the expected decision. A reviewer cannot see that consequence, so there is nothing for review to add (§8.5). |
| **AD-85** | **Under the `no-code` badge a self-authored tool must be a `composite` over already-approved pinned actions.** A code-bodied tool requires a distinct `engineer` role and an approval surface that states *"this tool contains code that has not been read by a person."* "Does not raise an exception" is forbidden as an acceptance criterion. | a capability manifest plus a model-evaluated QA suite | The real gate was a model, and under D13 the human signing it cannot read the body. SkillWeaver's exception criterion was gamed by silencing every atomic action's errors (§8.5). |
| **AD-86** | **The optimiser ABI narrows what the proposer sees**: component addresses, per-case scores, and a **redacted failure category from a closed vocabulary**; reason text goes to a separate non-proposing reflector. `objective:` and `background:` are **typed**, with a salted 13-gram near-duplicate sketch between them and every gating suite's assertion texts as a load-time check. | `objective: str` + `background: str  # domain + evaluation rules, prose` | "Evaluation rules" is the grading surface, in prose, by the field's own comment — a complete paraphrase of the suite, passing the verbatim-substring fixture. The shortest path to +score becomes "satisfy the checkers" with the rubric in hand (§8.2, §8.8a). |
| **AD-87** | **OPT-GATE-1** — the optimiser's own accept gate carries a validated minimum n, declared in the descriptor and checked against §6.9-A. | inherit the optimiser's default | GEPA's default gate is `sum(after) > sum(before)` over **three** examples; a perfect n=8 certifies only 0.6877. That gate-size defect is the mechanism behind the one surviving negative result in the corpus, which R3 attributed to reflector weakness (§8.8). |
| **AD-88** | **The reflector defaults to the strongest LOCALLY-SERVED model**; any non-local binding requires a lock-recorded `allow-egress:` entry; redaction policy applies to the optimiser context; `enabled: yes` + non-local + no redaction is a load-time error. | "strongest available" | The flagship `learning.yaml` literally read `reflection: gpt-5.5`, and §8.8 *mandates* that per-case failures carry error text — so a default cycle posts the customer's ticket prose and attached photo to a third-party API, and the flagship cycle cannot run air-gapped at all (§8.7). |
| **AD-89** | **A human-authored commit IS the approval record.** `pact approve` writes a plain `approval:` block the commit carries. Ed25519 keys, four roles, `.pact-keys/` and the revocation list move to expert tier / v1.1. The learning-service signature stays. | "writes require two keys"; every machine diff needs an Ed25519 approver signature | The two-key rule had no ceremony, no key distribution, no verification point and no CLI verb — and it collided with D13 (a support lead cannot change her own approval threshold without a second key holder). Meanwhile §11's own configuration makes `ESC-JUDGED` fire on every accept path, so **every** cycle in the D20 workspace terminated at a signing ceremony no build stage built (Y24, §8.10). |
| **AD-90** | **The portable optimisation bundle (§8.11) is DELETED from v1**, with `producer.model` and `optimised-for` kept as provenance **labels** and the 13-gram sketch kept for grader-visibility. | ship the bundle format | No decision requires it; no build stage built it; §10's headline `air-gapped` badge asserted a property of `pact import-bundle`; and the same revision's evidence demoted import to a fallback that **loses 3 of 4** measured cells to local re-optimisation. Re-admission is gated on a measured strategy-transfer result (Y1, §13.14). |
| **AD-91** | **Learning permissions are closed enums renamed along the surface boundary**: `phrasing` / `examples` / `skill-notes` (S-GEN) and `when-skills-are-used` (S-ROUTE, OFF by default, requiring OBL-8 first). Membership in both lists is a load-time error. | `wording` | §8.1 opens with this document's own warning that a description edit is a wording change with **global routing blast radius** — so the plain word offered to a support lead authorised precisely the thing the architecture says must not be treated as wording (§8.7). |

### 1.9 Ecosystem, conformance and process

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| **AD-92** | **Two runtime changes to `gaia-ai-runtime` for cold execution**: a planner path accepting a tree with no registry entry or artifact precondition, **and** removal of the subagent → package → recipe round-trip inside `create_agent`. | "the one runtime change is a deletion" (R1) | Verified: run planning hard-fails unless the compiled Goose recipe physically exists, **and** `create_agent` itself reads it back off disk whenever `spec.runtime.subagents` is non-empty. Two gates, not one (X7, §9.1). |
| **AD-93** | **Only workspace-relative discovery may supply anything nameable by `team:`/`uses:`.** Machine-global roots contribute only under an explicit `host/<name>` namespace, may supply GOVERNED read-only artifacts only, and `$GOOSE_PATH_ROOT`/`$HOME` are dropped unless enumerated in `workspace.yaml`. | inherit Goose's root set | Unauthenticated agent injection plus name shadowing: anything that can write `~/.claude/agents` drops a `fraud-checker` that always returns "no fraud signal", and `allowedAgentIds` is pinned *after* it is already in the set. AC-6.1 is preserved intact (§9.3). |
| **AD-94** | **Five conformance levels (L0–L4) plus three orthogonal badges** (`air-gapped` with six **static** traps, `no-code` asserting against the core tier, `modality:<m>`). **M0–M2 is a separate model-portability track, and only M0 is a v1 gate.** | L0–L4 alone; M1/M2 as v1 gates | L0–L4 are entirely framework-portability levels; model portability — the thesis's second result — had no level, no ε and no corpus-sizing rule, and its whole representation was two bare scalars. M1's corpus is ~316 cases per arm and PACT will not build it in v1; defining the level now means the ratio is at least *reported in the right shape* (§10). |
| **AD-95** | **ε and n are ONE published conformance parameter, per metric, sized from `max_m ⌈n(ε_m, p̂_m)/c_m⌉`.** CTS **Stage A (null band, R ≥ 8 replicates of ONE adapter)** lands before the second adapter. | ε as a single number to be chosen later | The missing quantity was never ε alone. Twelve golden agents at ~10 cases is 120 cases, at which the team gets overlapping intervals on everything and cannot distinguish "the adapters agree" from "we have no power" — the exact observation the CTS exists to make (§10, §10.2). |
| **AD-96** | **Import coverage is a published per-framework figure over the framework's own `examples/`, with refusals counted and the refusing construct named**, and it is a release gate that must go up. **≥ 4 of 12 golden agents must be direct translations of named upstream examples.** | "zero silent drops on a curated fixture set" | Measured: 9 of 13 pydantic-ai examples use Python-callable constructs D15 forbids wrapping. If ~70% of the highest-priority target's own canon is unimportable, the golden agents are written by PACT for PACT and the conformance suite cannot fail (§12.4). |
| **AD-97** | **LangGraph is chosen for DURABILITY distance, not loop distance**, and L2 is conditional on the divergence fixture family (malformed tool-call JSON, thinking/signature round-trip, provider-assigned id normalisation) **plus Stage A landing first**. §12.2's assertion (iii) is scoped to "byte-identical after the published normalisation of provider-assigned ids". | D7's original rationale as stated | `entrypoint.__call__` builds a one-node Pregel graph, so under D12 **none** of LangGraph's distinguishing semantics is on the execution path — the CTS would compare two thin wrappers over the same HTTP call and pass within any ε, having falsified nothing (§12.5). |
| **AD-98** | **A normative CLI verb table with a `core \| expert` column**, and a CI gate asserting every `pact <verb>` spelling in the spec appears in it and is implemented or marked v1.1. `pact run` is **not** a PACT verb. | 19 verbs across 28 invocation forms, indexed nowhere | The shipped binary implements two, §15 indexed every identifier series and no verbs, and §11.1's "one command" was three (§15.1). **Count is EDIT-7.** |
| **AD-99** | **Seven CI gates land with Stage 1 and never come down**, including: §11 is **materialised into `examples/`** and the gates run against that; the file count in §11.1's headline is asserted against the materialised tree; every code fence's verdicts are re-derived from `verdict()`; every quantitative law in a normative rule carries its sign sentence **and its baseline condition**. | a hand-maintained example beside a documented tree | That is how §11.9 came to reference a skill in no tree and how `learning.enabled: yes` shipped against a workspace with no splits. **Extend the code-fence gate to loadability, not just verdicts — see EDIT-2** (§12.1). |
| **AD-100** | **PACT emits its own spans** (causal / timing / semantic planes over one identity spine); the file-backed JSONL trace is the source of truth and OTLP is a projection; percentiles are computed in-process from retained samples. `AGENTS.md` is emitted as a projection and **never accepted as an input format**. | query an observability backend for SLO figures | Langfuse maps p95 to ClickHouse `quantile()`, a reservoir approximation — a gate reading that is reading an estimate of an estimate. Under harness lowering PACT knows statically whether a node is a team or an agent, which is exactly what OTel's don't-double-report rule requires and framework instrumentations cannot satisfy (§4.3, §9.8). |
| **AD-101** *(supersedes the spelling in AD-20 and AD-22; keeps both rulings)* | **The ceilings are one flat family, each carrying the author's own action.** `steps-at-most`, `tool-calls-at-most`, `runs-for-at-most`, `tokens-at-most`, `cost-per-request-under` — all enforced, all reported by the name the author typed, all governed by `when-it-runs-out: stop-and-say-so \| ask-a-person \| answer-with-what-it-has`. `stop-after: {tool-calls, turns}` is **deleted**. A ceiling written without `when-it-runs-out` is refused by `pact check`, through a general `needs-also:` in the schema rather than a rule in the validator. | `stop-after` as a nested group with `turns` as the loop counter | AD-22 already ruled there is **one** loop counter; the tree shipped two spellings of it (`stop-after.turns` and `steps-at-most`), which is the `same-setting-twice` mistake the validator exists to catch, sitting in the specification itself. And `turn` had since been given a second, incompatible meaning by the event lattice, where a turn *contains* steps. AD-20's substance is unchanged and is now executed rather than declared: every ceiling is enforced during the run (G2). `tokens-at-most` is added because it is the only ceiling that still bites with no price list — the air-gapped case D17 mandates — and it is the one bound Eve does have. |
| **AD-102** *(supersedes the spelling in AD-79 and AD-81; keeps both rulings)* | **One setting decides whether the agent changes itself, and its three answers are named for what happens.** `learning.enabled: off \| propose-only \| applies-safe-changes-itself`. `learning.auto-apply:` is **deleted**, and the obligation it carried moves onto the third ANSWER as `needed-when: {may-improve-on-its-own: applies-safe-changes-itself}` — asked for when it is owed rather than whenever the deleted line was present. | `enabled: [off, propose-only, yes]` with `auto-apply: yes-no` beside it, the pair jointly deciding the tier | Two settings for one decision is six spellings for three real states, and two of the six contradict each other in silence. Measured: `enabled: propose-only` beside `auto-apply: yes` printed *"OK — loaded cleanly"*, exit 0, and the reader takes `enabled:` first, so the author's `yes` was discarded with nothing said. The reverse was worse — `enabled: yes` with no `auto-apply:` line defaulted to no, so the strongest word on the setting that decides whether a system rewrites itself with nobody watching meant nothing at all. And `needs-also:` fires on PRESENCE, so `auto-apply: no` — the line meaning *"nothing applies itself"* — demanded a list of what does. `yes` was also the whole description of the third state, and it describes nothing: AD-79's own argument is that this is the tier boundary, so it is the one answer that has to read as consequential to the support lead D13 names. Recorded as a refusal in `docs/50-NOT-COPIED.md` §5 R59. |

---

## 2. Surviving hypotheses

Twelve bets were retired or closed across R3–R6 (H2 became a theorem; H32/H34 were retired
with `reflect-bench`; H37 split, with H37b and H37c **closed by measurement**). What remains
is below, with the test that kills it and my confidence.

### 2.1 High confidence — a property test or shipped code decides them

| # | Bet | Falsified by | Conf. |
|---|---|---|---|
| **H1** | Typed Expansion is total and deterministic | a loader conformance vector producing two documents on ext4/APFS/NTFS, or a schema field with no sound fold | high — EXP-1..11 close every divergence found in six shipping systems; the flat/tree equivalence test passes today |
| **H11** | A Merkle digest over doc + blobs + transitive refs is the right identity | a semantic change that does not move it, or a meaningless one that does | high — four property tests, three already passing in `canonical.rs` |
| **H14** | `surface` annotation in a signed, compiled-in schema structurally protects governance | any proposal reaching a GOVERNED **field**, or a schema-extension path that sets a surface on a core field | high (restated) — the partition is now the signed binary, not a table in a document the optimiser can reach |
| **H30** | Surface-derived zones and π_contract are sound — one annotation, three answers | a field whose correct zone genuinely differs from its correct blast class | high — three round-2 fatal findings collapsed into this and none re-opened |
| **H22** | `x-` + a namespace map round-trips across four protocol boundaries | any boundary that renames, drops or type-coerces a block | high — CloudEvents is the binding constraint and all PACT fields live inside `data` |
| **H25** | Plain-language field names do not block adoption | third-party tooling shipping a snake_case translation layer | high — no incumbent to be compatible with, and D13/D18 make it the right default |

### 2.2 Medium confidence — reasoned from source, unmeasured

| # | Bet | Falsified by | Conf. |
|---|---|---|---|
| **H3** | Three verbs suffice as the text/tool/vision ABI | any adapter needing a fourth to reach L1 | medium-high — the obvious fourth is explicitly rejected (AD-31); highest-risk candidate remains openai-agents, whose Model seam speaks Responses on both sides |
| **H4** | One `Graph` covers 8 topologies × 6 loops **without `escape`** | a pattern needing a 9th node kind or an `escape` | medium — sufficiency was never demonstrated; L3's sweep is the first real test |
| **H5** | Node-scoped `on-reentry` is the only reconciler needed | a fixture needing different re-entry policy for two channels read by one node | medium — no prior art for node-scoped re-entry or for `fork`; marked INFERENCE in the draft |
| **H7** | 51/56 DeepEval parity at five shims | a sixth shim, or a metric in the 51 needing author code | medium-high — enumerated from source, refuting R1's 56/56 |
| **H8** | Five on-ramps desugar into one form losslessly | judged-rule fraction of the D20 corpus exceeding ~30% | medium — the `expect:` table is now normative, which is what made this testable |
| **H10** | A library loop graph substitutes for a `harness:` enum | a model tier where the raw model beats every PACT loop graph on the shared suite | medium — strictly more expressive, and the harness-vs-raw CTS arm is mandatory |
| **H12** | Effect surfaces give a conservative explainable classifier | any of the 14 mutation fixtures classified too low | medium — two new fixtures (30→300 inversion; unnumbered-bullet deletion) were added *because* the first design missed them, which is evidence the fixture set is still incomplete |
| **H13** | Cumulative drift detection is affordable | a window-10 audit exceeding the cycle budget, or a ten-step erosion all classifying ≤ R2 with the cumulative audit also missing it | medium |
| **H15** | `bud.dev/v1 → PACT` is total and reversible | one corpus manifest failing byte-round-trip | medium — three known hazards named (the Goose frontmatter writer drops `spec.budgets` and `skills.define`; three open sub-objects with no PACT home) |
| **H18** | The determinism clause makes LangGraph's ordinal memoisation safe | either replay fixture failing under a conforming loop | medium — the mechanism is read from source; the fixtures are not yet written |
| **H19** | `session:` as a contract declaration suffices for v1 | an air-gappable duplex substrate appearing before v1.1, or the cascade failing `modality:audio` | medium-high |
| **H20** | One media part covers all four modalities | a modality needing a distinct part type | medium-high — two projects converged independently; `provider-ref` already absorbs the nearest counter-example |
| **H21** | Exact in-process percentiles + min-n are authorable no-code | authors routinely lowering the percentile to p50 or deleting the SLO in a moderated session | medium — `source: probe` removes the pressure that made this likely |
| **H23** | L0–L4 is a meaningful partition | an L2 adapter nobody can use because every real workspace needs L3/L4 | medium |
| **H26** | Push-form blackboard/market is sufficient in v1 | the blackboard fixture requiring claim+lease to avoid double execution | medium — and this one decides whether AC-5.1 is met in v1 |
| **H27** | A digest-pinned MCP snapshot is operationally tolerable | snapshot drift forcing re-pins more often than teams tolerate over a quarter | medium-low — the air-gapped escape (`tool-snapshot-max-age: 3650d`) is *predictable* behaviour, not a hypothetical |
| **H29** | Tiering is a sufficient mechanism for checking D14 | a D14-required capability with no core-tier expression, or a core-tier construct a support lead cannot author (AC-1.5) | medium |
| **H31** | The judge canary suite generalises | a judge passing at ≤ 0.10 FPR that is nonetheless fooled by an optimiser-discovered suffix in the D9 run | medium — ten measured master keys is a floor, not a proof |
| **H33** | The grader-side component of ε is small relative to the null band | a Class-Q or Class-J metric whose frozen-output re-grade approaches the arm's null band | medium — if false, judge-graded metrics leave the L2 gate entirely |
| **H35** | A **gate**, not a stronger reflector, is what makes learning safe | a properly-gated cycle at OPT-GATE-1's n that still ships a held-out regression | medium-high — TextGrad's unconditional `set_value`, GEPA's n=3 default and ACE Table 17's adversarial-reflector row all point one way |
| **H36** | The `reasoning` ladder is a usable quality axis | two distributions ranking the same model pair oppositely, or a workspace where it never changes candidate ordering | medium-low — a derived ranking, not a portable scale (AD-R2) |

### 2.3 Low confidence — genuine research bets, and the ones that would hurt

| # | Bet | Falsified by | Conf. |
|---|---|---|---|
| **H16** | Cold execution needs exactly **two** `gaia-ai-runtime` changes | a third precondition (most likely: `allowedAgentIds` pinned at plan time for run-authorisation evidence, or a Goose-specific compiler downstream of `create_agent`) | low-medium — R1's one-change claim was already falsified once. **This gates D20 on another team's codebase.** |
| **H17** | Exactly-once HITL holds on both adapters at `durability: at-effect` | the §12.2 kill test | low-medium — pydantic-ai's skip sentinel is not crash-safe on its own; LangGraph's mid-loop `interrupt()` inside one `@task` is **unspiked** |
| **H6** | Tier-0 predicates are total for D14 | any required `when:` needing arithmetic or aggregation | low-medium — with Tier-1 CEL deleted there is no escape; the response is one new typed atom, which is cheap but means H6 is falsified in the literal sense |
| **H9** | Fail-then-recommend is affordable fully offline | candidate verification exceeding the declared eval budget before producing a recommendation | low-medium — compounded by §13.9's unmeasured air-gapped optimisation economics |
| **H24** | The optimiser ABI produces net-positive learning | the D9 end-to-end run failing to improve, or improving on validation and regressing on frozen held-out | low-medium — `deepeval/optimizer/` has still never been read (AD-R4) |
| **H28** | A core-tier no-code suite can reach `PASS` | no no-code suite reaching PASS after the Stage-3 milestone | **low — and EDIT-1 may already have falsified it for the flagship.** If it fails, D21 ships non-technical people's agents under a permanent UNDECIDED |
| **H32-perf** | A per-metric `(ε_m, n_m, p̂_m)` gate is affordable | any gating metric whose coverage forces a corpus PACT will not build (the observed floor is 6–8%, implying ~2,000 cases) | low-medium |
| **H37a** | A `propose-only` cycle **yields** proposals at n ≈ 10 | 20 consecutive `- proposal: none` rows in `proposals.ledger` during the D9 run | low — nothing in the corpus measures proposal yield at this operating point; the binding input is the supply of *failing traces*, not the case count |
| **H37d** | A capped typed review queue stays out of the fatigue regime | a sustained reject rate above ~50%, or `PACT-W3013` firing repeatedly | low-medium |
| **AC-1.5** *(not an H, but the deepest bet in the project)* | A non-programmer can author a 3-agent system with evals in YAML/Markdown in a moderated session | the moderated study | low — the only prior study (n=23) recruited participants who *"generally all had prior programming experience"*. **This is the claim D21 rests on and it has zero supporting evidence** (§13.6) |

### 2.4 The four claims this architecture would most like to be wrong about

1. **H16** — if cold execution needs more than two runtime changes, D20 slips behind someone
   else's roadmap.
2. **H6** — if Tier-0 cannot express the topologies' `when:` clauses, the answer is new atoms
   until the atom set is an expression language by other means.
3. **H12** — if the classifier misclassifies downward, D23 becomes "human review for
   everything", which is a different product.
4. **H28** — if no core-tier suite reaches PASS, T2's claim that the eval suite *is* the
   portability mechanism rests on an oracle too small to decide anything.

---

## 3. Accepted trade-offs and residual risks

### 3.1 Trade-offs we are choosing to pay

| # | Trade-off | What we get |
|---|---|---|
| **AD-T1** | **Translate or nothing** (D15). PACT's importers will refuse a large fraction of real LangGraph and pydantic-ai apps — measured, 9 of 13 pydantic-ai examples. | Every agent in PACT is genuinely portable. The alternative (`runtime_deps`-style out-of-band code pointers, as OASF/Oracle use) is the escape that makes a "portable" spec unportable. |
| **AD-T2** | **Harness lowering means generated code does not look like hand-written LangGraph**, and PACT owns loop quality (F-4 makes underperformance a tracked defect). | Fidelity is a property PACT can guarantee rather than hope for; native feature satisfaction recovers idiom per-feature where the CTS proves equivalence. |
| **AD-T3** | **Disjoint union means a value shared by two documents cannot be written twice.** It must come from the profile chain — a different composition operator. | "Where did this value come from?" is always answerable, and a subsequent one-sided edit cannot change behaviour with a diff that reads as a no-op. |
| **AD-T4** | **The transcript is canonical but NOT fully portable.** A provider-scoped residue (`reasoning.signature`, `provider-details`) exists; cross-provider replay drops it with a loss report. | Honest. R2 claimed "always faithful" and had nowhere to put the residue at all, which is strictly worse. |
| **AD-T5** | **Plain-language field names diverge from spec convention** (`answers-with`, not `output_schema`) — a cost against D10.2's open-standard goal. | D13/D14/D21 make the non-technical author the design centre, and D18 makes the file the API for a form UI and a git diff. |
| **AD-T6** | **`explode` is not total.** | No key mangling and no import restriction. The asymmetry is stated rather than hidden. |
| **AD-T7** | **AC-5.1's blackboard and market patterns ship in PUSH form only.** | No invented lease design in v1. Whether push-form satisfies AC-5.1 is a thesis-level judgement this architecture has **taken**, not escalated — see AD-R6. |
| **AD-T8** | **`propose-only` certifies nothing statistically.** The claim is exactly *"a person read this diff and wanted it."* | D14's learning clause is reachable at n=3, today, by the persona it was written for. |
| **AD-T9** | **M1/M2 model-portability conformance is defined but not gated in v1** (~316 cases per arm). | T4 is not made permanently uncertifiable by a corpus nobody will build; the ratio is at least reported in the right shape. |
| **AD-T10** | **Some approval-relevant capabilities are out of scope in v1** — history-derived predicates (§13.13), `queue`, duplex sessions, provider-native web-search/code-interpreter. | Each was a subsystem serving one example line. Each is stated in §13 so nobody builds on it. |
| **AD-T11** | **PACT ships no scheduler.** `review: weekly` desugars to a host-facility binding and `pact check` **fails closed** if nothing is bound. | NG1 holds, and a learning loop nothing triggers is caught rather than silently inert. |
| **AD-T12** | **A judged gate costs 66–510 human labels before it may gate anything.** | "Prefer deterministic checks" stops being a style preference and becomes a budget a non-technical author can be shown. |

### 3.2 Residual risks — stated plainly

| # | Risk | Status |
|---|---|---|
| **AD-R1** | **Blob substitution is undetectable on an unsigned D2 cold path.** The loader detects corruption, not substitution. Signing the workspace closes it; nothing else does. | Accepted. `pact check` warns when a workspace referencing payload blobs carries no signature. |
| **AD-R2** | **The `reasoning` ladder is a derived ranking, not a portable scale.** Two catalogue versions may rank differently. | Accepted. `catalog-entry-digest` makes a verdict reproducible against the catalogue it was computed on. H36. |
| **AD-R3** | **`settings:`'s default table is asserted, not measured.** The `max-tokens` row is a judgement chosen to avoid the pydantic-ai/langchain divergence. | Open. Falsified by a golden agent whose score moves materially with `max-tokens` inside the range both frameworks admit. |
| **AD-R4** | **`deepeval/optimizer/` has never been read** — a full package (COPRO, MIPROv2, SIMBA, GEPA, a rewriter, a Pareto scorer) that may already satisfy or already violate the frozen-held-out protocol. | Open. **Do not freeze the optimiser ABI before reading it.** |
| **AD-R5** | **Typed Expansion has never been tested against an arbitrary JSON Schema** (`$ref`, `$defs`, ordering-sensitive `allOf`/`anyOf`, duplicate keys) — the stress test the thesis itself names. | Open. Fallback is `expand: none` on schema-typed fields, which weakens T5's generality claim. |
| **AD-R6** | **AC-5.1 is satisfied only in push form**, and whether that meets the thesis is a judgement taken rather than escalated. | Open. If push-form fails the blackboard fixture, either `queue` returns with an invented lease design or AC-5.1 is restated at 6 patterns. |
| **AD-R7** | **The shared usage/budget object does not cross a delegation boundary.** Pydantic AI's delegation works only because `usage=ctx.usage` is passed by reference in-process; that breaks across a Temporal activity or a LangGraph subgraph. TOPO-2 mandates Σ(children) ≤ parent's remaining with no specified mechanism. | Open. SLO and cost contracts for multi-agent runs depend on it. |
| **AD-R8** | **Durability ownership is undecided and changes the ABI.** `durable_exec` wraps the Agent, not the Model, so a transport harness inherits nothing; LangGraph's `@entrypoint(checkpointer=)` supplies it free and would double-checkpoint. | **Must be decided before either adapter is written.** |
| **AD-R9** | **LangGraph mid-loop `interrupt()` inside one `@task` is unspiked.** It is unverified whether resume replays the entire loop body. | **Decides whether D12 is implementable end-to-end on LangGraph.** Never executed in any research stream. |
| **AD-R10** | **The registry-revision vs PACT-digest question is deferred, not answered.** Every pinned A2A card URL depends on it. | Interim: publish both for one release. |
| **AD-R11** | **No UI-hint layer is specified, yet D18 requires form rendering** (sort order, label distinct from key, widget type, group, conditional enable, immutability). KubeVela's `UIParameter` enumerates exactly this gap. | Open. E-3's "new authoring surface is free" holds for the filesystem, not for the UI. Note `show-when:` was deleted for good reasons (NG4), so this needs a *presentation-layer* answer, not an IR field. |
| **AD-R12** | **Evidence-hygiene debt.** `ESC-SHRINK`'s 40% (one data point), `N-min = 100` / `τ = 0.10` (one benchmark, one model, three seeds), `V-min ≈ 15,000` (2 of the studied datasets) and `expected-flip-rate = 0.25` (one in-repo data point) are the operative defaults. Several §8/§13 figures cite line numbers in `/tmp` extracts that no longer exist. | Open. All are marked provisional and profile-tunable. Extracts must move under `research/` with a sha256 and a pinned `pdftotext` version before any of these enters a published document. |
| **AD-R13** | **`tool-snapshot-max-age` is disabled by design on every air-gapped install.** A 30-day hard-fail with no sync path means every such workspace sets `3650d`. The signed dated snapshot bundle (§11.5 rule 3) is the answer and it is ~15 lines of unscheduled work. | Open. H27. |
| **AD-R14** | **PACT's flagship no-code topology is homogeneous by construction** (one local model under D17), which is precisely the regime the corpus measures multi-agent as buying least in — up to 3× the cost at equal accuracy. | Accepted, with RES-5b reporting both arms. The D20 demo is a *topology* demo running in the regime where topology is worth least. |

---

## 4. What is unproven and must be validated by building

Ordered by how much they change if the answer is unfavourable. Each names the artifact that
settles it.

| # | Unproven | Settled by | If it goes badly |
|---|---|---|---|
| **U1** | Cold execution needs exactly two `gaia-ai-runtime` changes (**H16**) | make both changes; run the §11 tree with no `.pact/`, no recipe, no registry write | D20 slips behind a runtime refactor. **Spike this in week 1, before anything else, because it is the only item on another team's codebase.** |
| **U2** | Exactly-once tool side effects across an approval boundary on both adapters (**H17**) | the §12.2 kill test — request approval mid-parallel-tool-batch, kill, resume | *"If it does not pass, no other conformance result matters."* Write the fixture before the adapters. |
| **U3** | Whether a mid-loop `interrupt()` inside one `@task` replays the loop body (**AD-R9**) | a 50-line LangGraph spike | Decides whether D12 is implementable on LangGraph at all; may force per-step `@task` granularity and its checkpoint cost |
| **U4** | Who owns durability (**AD-R8**) | a written decision, before adapter code | Changes the harness ABI. Do not start Stage 4 without it. |
| **U5** | ε — the per-metric null band (**AD-95**) | CTS **Stage A**: R ≥ 8 replicates of the pydantic-ai adapter over the full gating corpus | Until this exists, AC-2.2 is not evaluable and L2 has no gate. It needs **no second adapter**, so it is not blocked by Stage 5. |
| **U6** | Whether a core-tier no-code suite can reach PASS (**H28**) | Stage 3 + Stage 8 on the §11 workspace, after EDIT-1 is resolved | D21 ships under permanent UNDECIDED and T2's oracle claim weakens |
| **U7** | Whether a non-programmer can author the D20 system (**AC-1.5**) | a **pre-registered moderated study** with an operational non-programmer screen and a control arm | The whole design centre. It is also the project's most defensible research contribution and should be run as such, not as a self-assessment |
| **U8** | Whether transport lowering costs accuracy vs native (**F-4, H10**) | §12.3 benchmark #1 with the scaffold held fixed: same spec digest, prompts, tools, model, seed, cases; PACT-lowered vs a hand-written `create_agent` StateGraph | D26's "small overhead is acceptable" is currently an unpriced commitment |
| **U9** | Whether the optimiser produces net-positive learning air-gapped (**H24, H37a, §13.9**) | the D9 end-to-end run, instrumented by `proposals.ledger` (QUEUE-4) | If yield is zero at n ≈ 10, D14's learning clause needs §6.6 trace promotion as a hard prerequisite rather than an option |
| **U10** | Whether the classifier ever under-classifies (**H12**) | the 14-mutation fixture suite, including the 30→300 inversion and the unnumbered-bullet deletion | D23 becomes "human review for everything" |
| **U11** | Whether one `Graph` covers 14 patterns without `escape` (**H4, H5, H26**) | the L3 sweep + the blackboard push fixture | A 9th node kind, or `queue` returns, or AC-5.1 is restated |
| **U12** | Whether Typed Expansion survives an arbitrary JSON Schema (**AD-R5**) | explode/collapse a real tool snapshot's input schema | `expand: none` on schema-typed fields; T5's generality claim narrows |
| **U13** | Whether `bud.dev/v1 → PACT` byte-round-trips (**H15**) | the corpus converter over every `tests/*.rs` fixture and every materialised `agent.bud.yaml` | D3's superset requirement is not met; the migration path needs an escape |
| **U14** | Whether `deepeval/optimizer/` is adoptable (**AD-R4**) | read it — a day's work, unscheduled in every plan so far | The optimiser ABI may be wrong in a way that is cheap to fix now and expensive later |

---

## 5. Prioritised build order

**Principle (D20).** The first demo is a non-technical author building a multi-agent system.
Everything that is not on that path waits, **except** the three de-risking spikes, which are
cheap and gate work on someone else's codebase.

**Where we start.** 4,311 lines of Rust across five crates; loader steps LOAD-1..LOAD-10
exist and are tested; `spec/schema.yaml` is 692 lines carrying `surface` and `tier` on every
field; `examples/refund-desk` loads (`pact check` → OK, 249 settings); the CLI implements
**two** verbs (`check`, `show`) of the ten core verbs the spec names.

### Phase 0 — Unblock (days, in parallel, before Phase 1 code)

| # | Task | Why now |
|---|---|---|
| **0.1** | **Fix EDIT-1..EDIT-12 in the draft.** EDIT-1 is a *decision*, not an edit: scope `minimum-credible-bar` so the flagship can certify, and re-cost §11.1's case count against whatever bar survives. | The FRD cannot be written from a document whose flagship example cannot certify and whose defining eval section does not load |
| **0.2** | **Spike U1** — make both `gaia-ai-runtime` changes and run a bare tree cold | It is the only critical-path item on another team's codebase, and R1's version of this claim was already falsified once |
| **0.3** | **Spike U3** — LangGraph mid-loop `interrupt()` inside one `@task` | ~50 lines, and it decides Phase 5's shape |
| **0.4** | **Decide U4 (durability ownership)** and record it as an AD | Changes the harness ABI; every later adapter decision depends on it |
| **0.5** | **Read `deepeval/optimizer/` (U14)** | One day. It may make Phase 8 mostly adoption rather than construction |
| **0.6** | **Write the §12.2 HITL kill fixture** (it will not pass yet) | It is the test the architecture says decides everything; writing it first shapes the ABI |

### Phase 1 — The authoring surface (the D20 substrate)

Delivers **L0**, AC-1.1, AC-1.4, O7.1, O7.3. Everything downstream reads these annotations.

1. **Compiled-in, digest-verified schema** (AD-4). Delete `$PACT_SPEC` from release builds;
   gate it behind `--unsafe-spec` in dev, recorded in the lock, auto-apply disabled.
2. **Close the shipped schema drift**: `may-improve-on-its-own` / `needs-a-person-to-approve`
   / `keep-only-if` / `may-also-change` become closed enums with membership-in-both an error;
   `needs-approval-before` becomes a structured `(server, method) + tool-arg` predicate typed
   against the pinned snapshot. **Same commit as the example edit** (AD-99).
3. **LOAD-11..LOAD-14**: type validation, surface attachment, zone/π_contract computation,
   `LoadReport`.
4. **Delete `PAYLOAD_MARKER` and `payload_dirs`** from `pact-loader/src/policy.rs`; replace
   the bare `continue` at `lib.rs:387` with a LoadReport line; CI test that no directory
   becomes a payload except through `expand: payload` (EXP-7).
5. **`pact init`** with FR-1.2.5 templates (single agent, supervisor + specialists, pipeline),
   minting `workspace-id`, writing both specialists' `instructions.md` from the `team:`
   purpose sentences, writing `population:` and the chosen `must-pass:` bar, and printing the
   steps it cannot run.
6. **`pact explain`** (composition chain, desugaring, the ENFORCED/REPORTED split).
7. **The seven CI gates**, including materialising §11 into `examples/` and asserting the
   §11.1 file count — **plus the EDIT-2 extension: every code fence must load, not only
   re-derive its verdicts.**

**Exit gate:** `pact check --tier core examples/refund-desk` green with zero expert-tier
diagnostics; flat/tree equivalence property test green; loader conformance vectors green.

### Phase 2 — Cold execution (the D20 demo itself)

Delivers **D20, D2, AC-6.1**. Gated on 0.2.

1. Both `gaia-ai-runtime` changes (AD-92): planner path with no artifact precondition;
   remove the subagent → package → recipe round-trip in `create_agent`.
2. Workspace-relative discovery only; `host/<name>` namespace for machine-global roots
   (AD-93).
3. The `team:` → `Graph` desugaring (AD-72) — `self: true`, `task/<member>` channels,
   `route.prompt`/`assigns`, budget flow — because the demo is a *multi-agent* system.
4. The `.pact/`-deleted CI test, extended: a resolve after deletion must reproduce the same
   verdict (which is why `heldout.ledger` is in the tree).

**Exit gate:** a support lead's tree, authored in Phase 1's templates, runs on
`gaia-ai-runtime` with zero derived files. **This is the demo D20 asks for.**

### Phase 3 — The oracle

Delivers **G4, AC-4.5, AC-4.2**, and the ε floor everything later compares against.

1. `EvalSuite` + the 36 deterministic `pact:` assertions in the Rust core (AD-52).
2. `verdict()` as one function (AD-57); intervals over case means with clustered SE (AD-61);
   per-metric `n_m`/coverage/ε (AD-62); validate-time minimum-n (AD-59).
3. `population:` (AD-65), coverage derivation (§6.9a), and the honesty lines.
4. The DeepEval provider with its four hard rules (AD-53); `pact judge calibrate`; the
   **judge canary suite** (AD-54).
5. **CTS Stage A — the null-band measurement** (U5): R ≥ 8 replicates of one adapter over the
   full gating corpus, published per metric as `class, n_m, c_m, p̂_m, quantum, sd, max |Δ|`.
   **Needs no second adapter. Do not defer it to Phase 5.**

**Exit gate:** the §11 suite runs; the per-metric ε table is published; **U6 answered** —
does a core-tier suite reach PASS?

### Phase 3b — The approval mechanism

Delivers **AD-89**. Small, and every learning cycle in the D20 workspace terminates here.

`pact approve` / `pact reject` writing a plain `approval:` block and appending typed
three-valued rows to `proposals.ledger` (AD-80 QUEUE-3), plus QUEUE-1's depth cap and
QUEUE-5's rubber-stamp warning.

### Phase 4 — First adapter (pydantic-ai)

Delivers **L1**. Gated on 0.4 (durability ownership) and 0.6 (the kill fixture exists).

Three verbs + typed `ctx` (AD-31); `settings:` with the normative default table (AD-33);
`output-mode` defaulting (AD-34); harness-performed tool-result media split (AD-35); the
`reasoning` and `malformed-tool-call` parts (AD-36); `usage.*` with the flag forced (AD-25);
cache boundaries (AD-38); the capability lattice with `attested-by` on every `native`.

**Exit gate:** golden agents 1–4 × the shared suite; the kill test passes on one adapter.

### Phase 5 — Second adapter (LangGraph) and the fidelity measurement

Delivers **L2, D7, D27**. Gated on Stage A having landed.

1. The langgraph adapter, pinned to `langgraph.func` + the `langchain_core` ABCs (never an
   agent factory), with all three distribution versions recorded.
2. **The divergence fixture family** (AD-97): malformed tool-call JSON, thinking/signature
   round-trip, provider-assigned id normalisation, and the screenshot-tool-result fixture.
3. **CTS Stage B** — the cross-arm band, harness-vs-native **and harness-vs-raw**, plus the
   hand-written `create_agent` StateGraph baseline (U8).
4. Publish `output.native-json-schema: unsupported` on day one with its source reason, and
   demonstrate §11.9's **refusal** as the demonstration.

**Exit gate:** the published per-metric `(ε_m, n_m, p̂_m)` table; the kill test passes on
both adapters (**U2**).

### Phase 6 — Composition

Delivers **L3**. The `Graph` IR, the topology and loop fixture sweep **without `escape`**,
VAL-1..VAL-15, the blackboard push fixture (**U11**, and the fixture that would force `queue`
back in).

### Phase 7 — Operational

Delivers **L4**. Durability at the declared level with the engine named; kill-and-resume;
spec-drift classification on resume; the determinism replay pair; SLO sampling with the
min-n gate; OTel emission.

### Phase 8 — The resolver

Delivers **D11**. Distribution catalogue with the `reasoning` ladder; `pact probe`;
RES-1..RES-9 including **RES-5b collapse-team**; fail-then-recommend with the closed
mechanism set and both ratio records; `pact.lock` with the full envelope; `heldout.ledger`
with cumulative multiplicity and rollback detection.

### Phase 9 — Learning

Delivers **D9, D22, D23**. The blast-radius classifier with core-side recomputation (AD-77);
the 14-mutation fixture suite (**U10**); `propose-only` with the specified queue (AD-80); the
optimiser ABI with typed `objective`/`background` and the 13-gram check (AD-86); OPT-GATE-1
(AD-87); one real end-to-end run (**U9**).

### Phase 10 — Migration

Delivers **D3**. The `bud.dev/v1` converter and the corpus byte-round-trip (**U13**); the
published per-framework import-coverage figure (AD-96).

### Runs alongside, from Phase 1

- **The AC-1.5 moderated study (U7)**, pre-registered, with a control arm. It should be
  designed while Phase 1 is being built and run against Phase 2's output. It is the deepest
  bet in the project and the longest lead time.
- **The three continuous benchmarks** (§12.3): harness-vs-raw and harness-vs-native;
  `run.overhead-ms` **including durability I/O** with its `{harness, durability,
  serialisation}` breakdown and `durability-writes-per-turn`; `cost-per-success`;
  `cached-read-fraction`; `prompt-tokens-amortised`; `RB-D proposal-format`.
- **Evidence hygiene (AD-R12)**: move every PDF extract under `research/` with a sha256 and a
  pinned `pdftotext` version before any of those figures enters a published document.

### What is explicitly NOT in v1

The realtime/duplex ABI (X20); Tier-1 CEL (Y4); the portable optimisation bundle (Y1);
`reflect-bench` beyond RB-D (Y2); `queue` with claim+lease (X3); `stall:` (Y7); `blobs.lock`
(Y6); `x-` projection into any substrate (Y5); resolver-proposed decomposition (Y3);
history-derived approval predicates (§13.13); provider-native web-search / code-interpreter /
web-scrape (Y25); native project emission (`pact export --native`); Ed25519 multi-writer
signing (AD-89); M1/M2 as conformance gates (AD-94); a third transport adapter (§12.5).

Each is recorded in §13 of the draft with the measurement or fixture that re-admits it.
