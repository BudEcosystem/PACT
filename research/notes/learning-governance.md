# PACT Research Stream — Learning & Governance (D22 + D23)

**Date:** 2026-08-07 · **Pass:** R2 of this stream (supersedes the 2026-07-26 version, which is
recoverable at `git show 129bb8f:research/notes/learning-governance.md`).
**Stream:** learning-governance.
**Binding inputs:** `docs/00-THESIS.md` (T6, T7), `docs/01-DECISIONS.md` (D2, D9, D13, D14, D17,
D18, D22, D23, D24, D26, D27), `docs/20-ARCHITECTURE-DRAFT.md` §8 (which R1 of this stream fed),
`/home/bud/ditto/gaia-ai-runtime/research/SYNTHESIS.md` F1/F3/F4/F6, `RESULTS.md`,
`PROMPT-SKILL-LEARNING.md`.

---

## 0. What this pass adds, and why the shape changed

R1 of this stream was a **design** document written against a corpus. Between then and now the
design landed: `docs/20-ARCHITECTURE-DRAFT.md` §8.1–§8.11 carries eight effect surfaces, five
classes, eight escalators, eight obligations, a seven-rule review queue, an optimiser ABI and a
trust spine — and `spec/schema.yaml` carries **277 fields across 44 groups, every one annotated
with `surface:` and `tier:`** (verified: `python -c` over the parsed schema; the Rust CLI enforces
completeness at startup, `crates/pact-cli/src/main.rs:394-416`).

So re-deriving the design from the corpus a second time would produce a document nobody needs.
**This pass is instead an audit with measurements**, plus the evidence that was not mined in R1.
Three kinds of new material:

1. **§1 — A spec↔implementation audit, executed.** I ran the shipped classifier against the
   architecture's own required fixture set and against the drift instrument. Nine findings, seven
   of them measured, none of them in `docs/70-PRODUCTION-GAP-REGISTER.md`. The headline: **the
   `surface:` column — the entire basis of §8.2's zone derivation and §8.3's classifier — is read
   by no classifier anywhere.** The only consumer is a presence check.
2. **§7–§8 — Four sources R1 did not read**: Letta's *sleeptime* agent (an autonomous background
   writer to a live agent's memory blocks), `cognee` (a self-improvement path that writes float
   weights, not source), `reflexion` (whose architecture already separates the honing oracle from
   the accept oracle — a positive precedent for X-2), and `agent-lightning` (address-based reward
   attribution, which is the only real machinery in the corpus for OQ8).
3. **§4.4 — A decidable replacement for the one classifier rule that was a judgement call.**
   `DE-TIGHTEN` ("strictly narrows an envelope") is not a heuristic: CUE ships a decidable
   subsumption relation with an `API` profile and per-field failure messages
   (`research/repos/config/cue/internal/core/subsume/subsume.go:15-70`,
   `vertex.go:169,174,202`). This makes the only de-escalator in the design provable and
   explainable rather than asserted.

**Extension of F1/F3/F4/F6 (unchanged framing, restated in one table so §0 stands alone):**

| F# | SYNTHESIS says | This stream's contribution |
|---|---|---|
| F1 | "eval gate + signed skill version" (`SYNTHESIS.md:33-58`) | The gate is insufficient alone (Ratchet A4: naïve retirement is *worse* than no governance). Needs an evidence floor `N_min`, a retirement threshold `τ`, and a never-delete archive. **R2 adds:** the retirement machinery has no schema surface at all (§1.6). |
| F3 | "candidate manifests as diffable YAML with full lineage" (`SYNTHESIS.md:105-107`) | "All text fields are trainable" is false in a governed system. **R2 adds the measurement:** the shipped classifier keys on the bare *field name*, and `description` is `S-GEN` in 14 groups and `S-ROUTE` in 4 — so one plain-language permission spans two blast-radius classes (§1.2). |
| F4 | "generation depth 1, empirical gate, budget caps inherited" (`SYNTHESIS.md:143-145`) | Adds authority inheritance, the viability invariant, the volume gate, archive-as-selector. **R2 adds:** none of the three has an authoring surface; D22(b) and D22(c) are unreachable from the format (§1.7, §5, §6). |
| F6 | "no tool-output→skill direct writes; diverse judges" (`SYNTHESIS.md:186-188`) | Forbidden-operations list, role quarantine, MCP supplies no isolation. **R2 adds:** the monolithic-rewrite operator F6 forbids is *shipped and prompted-for* by the most mature runtime in the corpus (§7.2), and one production system implements "learning" as an EMA over float weights driven by star ratings (§7.3) — the two purest violations of T6 and of QUEUE-3. |

---

## 1. The audit: what §8 specifies versus what the tree contains

Everything in this section was executed against the working tree on 2026-08-07. Commands and
outputs are reproducible; where I ran a script the script is inline.

### 1.1 The `surface:` column is not read by any classifier

**Verified.** `spec/schema.yaml` annotates all 277 fields:

```
81 S-GOV · 52 S-CAP · 44 S-EXEC · 39 S-CTRL · 35 S-GEN · 15 S-ROUTE · 10 S-TOPO · 1 S-META
```

`grep -rn "S-GEN\|S-ROUTE\|…" --include=*.rs --include=*.py --include=*.ts crates/ adapters/`
returns **8 hits, all of them in comments or docstrings.** No code anywhere evaluates
`surface == "S-GEN" → CLASS-1`.

The two things that claim to implement D23:

- **Rust**, `crates/pact-cli/src/main.rs:385-416` — `governance_is_complete()` checks that every
  field *has* a `surface:` and a `tier:`. It never reads the value. It is a completeness check,
  not a classifier.
- **Python**, `adapters/python/src/pact_adapters/learning.py:159-213` — `classify()`, which keys
  on a hardcoded field-name tuple (`HIGH_RISK_FIELDS`, `:50-53`), a hardcoded permission→field map
  (`SAFE_TO_CHANGE`, `:59-64`) and a regex over prose (`HIGH_RISK_PROSE`, `:80-84`).

**Consequences, each independently fatal to a §8 claim:**

| §8 claim | Status |
|---|---|
| §8.2 "Four zones, COMPUTED from `surface`, never from a path table" | No code computes a zone. |
| §8.3 "`class = max(rule(surface) for each changed IR node)`" | No code maps a surface to a class. |
| §8.3 "The **Rust core recomputes** the class … The recomputation never lives in the learning service." | The only classifier *is* in the learning service's own module. The core recomputes nothing. |
| §8.3 "Classification operates on the canonical semantic diff of typed IR nodes, **never on a textual diff of the tree**" | `classify()` builds `difflib.unified_diff` of two strings (`learning.py:139-146, 175-185`) and matches regexes against the `+`/`-` lines. It is exactly a textual diff. |
| §8.3 property test `class(diff) == class(collapse/explode(diff))` | Untestable as built: `Proposal` carries a bare field name and two strings, with no path and no document context, so `collapse`/`explode` has nothing to act on. |

This is the single highest-leverage finding in the pass. Everything in §8.3–§8.5 is a lookup into
a column that nothing looks up.

### 1.2 One plain-language permission spans two blast-radius classes

**Verified, and the shipped flagship example is affected.**

`learning.py:59-64`:

```python
SAFE_TO_CHANGE: dict[str, tuple[str, ...]] = {
    "phrasing": ("instructions",),
    "examples": ("description",),
    "skill-notes": ("content",),
    "when-skills-are-used": ("use-when", "do-not-use-when", "if-unsure"),
}
```

`description` is a field of **18 groups**. Its surface is not uniform:

| Group | Line | Surface |
|---|---|---|
| `agent.description` | `spec/schema.yaml:376` | **S-GEN** |
| `workspace`, `model`, `resource`, `question`, `evals`, `port`, `loop`, `context-policy`, `interceptor`, `redaction`, `watch`, `state`, `bundle` | — | **S-GEN** (13 more) |
| `skill.description` | `spec/schema.yaml:1572-1575` | **S-ROUTE** |
| `tool.description` | `spec/schema.yaml:1701-1704` | **S-ROUTE** |
| `action.description` | `spec/schema.yaml:1788` | **S-ROUTE** |
| `knowledge.description` | `spec/schema.yaml:1406` | **S-ROUTE** |

`skill.description`'s own help says why: *"This is what the agent reads when deciding whether to
open it"* (`:1577-1579`). It is the routing input §8.1 opens with.

So `may-improve-on-its-own: [examples]` — a `tier: core`, closed-enum permission whose help reads
*"the worked examples it is shown"* — authorises edits to `skill.description` and
`tool.description`. This is precisely the defect §8.7's `[R3]` note says it fixed by renaming
`wording`: *"the plain-language word offered to a support lead meant precisely the thing the
architecture says must not be treated as wording."* The rename fixed one member and reproduced the
defect on another.

Two aggravations:

1. **`when-skills-are-used` — the permission that exists to gate routing, is OFF by default, and
   requires an OBL-8 routing-replay before it may be enabled at all — does not include
   `description`.** Its three members are `use-when`, `do-not-use-when`, `if-unsure`. The largest
   S-ROUTE member is filed under the S-GEN permission and the routing permission does not carry
   it.
2. **There is no `examples` field in the schema.** A parse of all 277 fields finds no field whose
   name contains "example". So the permission named "examples" grants exactly one thing: edits to
   whatever object happens to have a `description`, in whichever of two blast-radius classes that
   object falls.

`examples/refund-desk/learning.yaml` — the flagship D14/D20 file a support lead is told to copy —
declares `may-improve-on-its-own: [phrasing, examples, skill-notes]`.

### 1.3 The prose classifier has a measured false-positive on ordinary instruction text

**Measured.** `HIGH_RISK_PROSE` (`learning.py:80-84`) is an alternation of truncated stems with a
leading `\b` and no trailing boundary. The stem `sent` (intended for "send/sent") matches
**"sentence"**:

```
True  'sent'  'Be concise and warm. Prefer short sentences.'
True  'sent'  'Answer in one sentence.'
True  'sent'  'Use plain English and short sentences.'
False    -    'Keep the tone friendly.'
```

Any proposal whose text contains "sentence" classifies HIGH. This is not a contrived string:
§8.8a's `Background.tone` example is literally `["plain English", "one sentence"]`, and instruction
prose about brevity is the single most common S-GEN edit an optimiser produces.

The cost is not safety, it is the **override regime** §8.7a QUEUE-1 exists to avoid: a gate that
refuses correct proposals for an unstateable reason (`"the wording changes a rule, not a phrasing:
'Be concise and warm. Prefer short sentences.'"`) is the shape that produces the 46.2–96.2%
override rates §8.7a cites.

### 1.4 `ESC-SHRINK`'s list trigger fires on every edit to a bulleted line

**Measured.** `classify()` collects removed lines from the unified diff and raises HIGH if any is a
list item (`learning.py:195-200`). A *modification* of a bullet appears in a unified diff as a
removal plus an addition, so:

```
edit one bullet  -> high  "ESC-SHRINK: a written rule was removed from a list — '- Check the order id first.'"
add one bullet   -> low   "wording only; no rule or permission changed"
```

The shipped `examples/refund-desk/skills/refund-policy.md` body is entirely bullets. Therefore
`skill-notes` — one of the three permissions ON by default in the flagship — can produce **no
auto-appliable edit at all** except pure additions, and every rewording of an existing line reaches
the human queue with a message that says a rule was *removed* when it was reworded. Under
`propose-only` (the core-tier mode) this is invisible; under `applies-safe-changes-itself` it makes
the permission inert.

### 1.5 The cumulative-drift instrument is blind to the class of change it exists to catch

**Measured, and it is backwards.** `Learner._drift` (`learning.py:1376-1383`) is
`1 − difflib.SequenceMatcher(None, baseline.instructions, candidate.instructions).ratio()` — a
character-similarity ratio over the `instructions` field only. Against a four-line refund
instruction:

| Change | Drift | Default limit `0.50` |
|---|---|---|
| `30 days` → `300 days` (semantic inversion, token-neutral) | **0.0031** | passes |
| delete the line *"Always look up the order before issuing a refund."* | **0.1866** | passes |
| 20 additive, harmless style sentences (`"Respond politely."` …) | **0.5130** | **trips** |
| edits required to trip the limit with harmless additions | **16** | — |

§8.4's entire justification is the quoted attack *"each generation may weaken a safety module by an
amount that falls within any single-generation tolerance … a safety audit comparing generation t to
t−1 will see nothing."* The instrument built to catch it scores a deleted safety rule at 19% and a
run of sixteen harmless additions at 51%. It measures **churn**, not safety-property change, and it
fires on volume.

It is also scoped to `instructions` alone: a workspace whose learning writes skill bodies (the
flagship's `skill-notes`) accumulates unbounded drift that the instrument scores at exactly 0.

### 1.6 §8.4's drift design is one field of six in the schema; §8.9's provenance envelope is zero

**Verified by parsing the schema.**

```
drift:        ['at-most']
cycle-limits: ['per-cycle', 'per-month', 'evals']
learning:     ['enabled','may-improve-on-its-own','needs-a-person-to-approve','keep-only-if',
               'review','cycle-limits','models','drift']
learning-model:['role','model']
provenance:   ['source','harness','contamination','date','as-of','recorded-by']
```

- §8.4 specifies `drift.{baseline, baseline-accepted-at, baseline-accepted-by,
  generations-since-accept, window, reclassify-every, auto-apply-ceiling-while-under}`. The schema
  has `at-most` and nothing else. **The lineage-window mechanism does not exist in the format.**
- §8.9's provenance envelope (`status`, `generation`, `derived-from`, `producer`, `origin`,
  `evidence`, `classification`, `reviewed-by`, `approval`, `validity`, `supersedes`, `revoked-by`)
  has **no group in the schema.** The group *named* `provenance:` (`spec/schema.yaml:887`) is the
  model-catalogue figure provenance from §4.2 — `source / harness / contamination / date / as-of /
  recorded-by`. Different object, same word.
- Consequently: OBL-6 (signature over `(base-digest, result-digest, recomputed-class)`),
  `ESC-UNTRUSTED` (keyed on `origin.workspace-id`), the revocation ratchet (`supersedes` /
  `revoked-by`, which §8.5 calls the answer to the "irreversible capability ratchet"), never-delete
  (`status: deprecated` + `validity.until`) and the retirement thresholds (`N_min`, `τ`,
  contribution `ĉ`) all have **no authoring surface and no place to be recorded.**
- §8.4 makes `pact approve --baseline` the sole writer of the baseline, and §8.10 ships
  `pact approve` / `pact sign`. The CLI dispatch is `crates/pact-cli/src/main.rs:305-306`:
  `"check"` and `"show"`. There are two verbs.

### 1.7 D22(b) and D22(c) have no authoring surface

**Verified.**

- §8.7's `may-also-change: []  # [loop] | [tools] | [topology] — opt-OUT by default` is **not a
  field of the `learning:` group** (see the parse above). There is no line an author can write to
  enable tool-learning or topology-learning, and no line that records they are off.
- `resource.resource-kind` has exactly one choice: `mcp-server` (`spec/schema.yaml:1272ff`,
  `surface: S-CAP`). There is **no sandbox resource kind.**
- The `tool:` group is `['available-when','description','connect','url','method','says','actions']`
  — a declaration of an endpoint plus actions. **There is no code body, no capability manifest
  (`network.egress` / `fs.read` / `fs.write` / `exec` / `secrets`), no acceptance-suite field, no
  honing budget.** `action:` carries `reads-only`, `needs-a-person`, `spends-money`, `bind`,
  `inspects`, all `S-EXEC`.
- `grep -rn "ADD-NODE\|ADD_NODE\|SPLIT_NODE\|ADD-AGENT" crates adapters` → **no hits.** The closed
  topology operator set is unimplemented, and so is TOPO-3 (no subset check between a child's
  capability set and its parent's appears in `crates/pact-loader/src/teams.rs` or `reach.rs`).

This is not purely a defect. §8.5's own `[R3]` note concluded that under the `no-code` badge a
self-authored tool **must be a composite** of already-approved, already-pinned actions, and that a
code body must not be reachable from the no-code surface. The shipped format enforces that by
having no code body at all. **The honest v1 statement is: D22(b) means "compose declared MCP
actions", not "author code"** — and §5 below is rewritten around that, because eight sandbox
requirements describing a subsystem that does not exist is the kind of spec text D28 failure mode
#1 is made of.

### 1.8 The two records that must survive a cycle live in the directory D2 says is disposable

**Verified.** `learning.py:480` — `UNDER = Path(".pact") / "learning"`; `:511` `LEDGER =
"spend.jsonl"`; `:516` `REFUSALS = "refused.jsonl"`; `_append` (`:483-509`) writes plain JSONL with
no `prev-digest` chain. `.gitignore:2,7` ignores `/.pact` and `.pact/`, with the comment *"D2 says
deleting a `.pact/` must be harmless; committing one would make that untrue."*

Both statements are true and together they are a hole:

- `cycle-limits.per-month` is a `tier: core`, `S-GOV` ceiling on what self-improvement may cost.
  Its running total lives only in the ignored directory. **A fresh clone, a rebuilt container, or
  `rm -rf .pact/` resets the month to zero**, and the code's own comment on a corrupt ledger line
  says it errs *"towards letting a cycle run"* (`learning.py:597-601`).
- `refused.jsonl` is AC-5.5's negative evidence. It does not survive a clone either.

§8.7a QUEUE-3 already diagnosed exactly this and legislated against it — *"an authored-tree file —
`S-GOV`, `prev-digest`-chained, **never** under `.pact/`* … a ledger that `rm -rf .pact/` silently
empties is the exact Y17 defect"* — and the shipped code does the forbidden thing for both records.

### 1.9 AC-5.5's negative evidence is a de-duplication cache, not evidence

**Verified.** `Refusals.key` (`learning.py:562-565`) is `f"{proposal.field}\n{proposal.after.strip()}"`
— exact string equality on the proposed replacement. `why()` (`:566-568`) is consulted in
`_decide` only to short-circuit re-scoring.

Two gaps against AC-5.5 (*"a rejected learning candidate is retained as negative evidence and
**demonstrably influences the next cycle**"*):

- A single character's difference produces a cache miss, so it does not bound repetition; it only
  prevents re-paying for a byte-identical proposal.
- Nothing feeds refusals back to a proposer (`grep -rn "refusals" adapters/python/src` outside
  `learning.py` → no hits). Nothing "influences the next cycle."
- QUEUE-3's three-valued outcome (`accepted | edited-then-accepted | rejected`) and its closed
  reason vocabulary (`wrong | too-broad | already-covered | not-my-policy | unclear |
  right-idea-wrong-wording | out-of-scope`) are not implemented; `why` stores the classifier's
  free-text sentence. §8.7a's own cited warning is that free-text override capture *"is discarding
  their most valuable training signal."*

### 1.10 Measured classifier behaviour against §8.3's own fixture set

Script run against `pact_adapters.learning.classify` (Python 3.12.3, `PYTHONPATH=src`):

| # | Fixture | §8.3 required | Measured | Verdict |
|---|---|---|---|---|
| F1 | delete one unnumbered bullet from `refund-policy.md` (§8.3a's mandated fixture) | ≥ CLASS-3 | HIGH (`ESC-SHRINK` list trigger) | **pass** |
| F2 | `30 days` → `300 days` inside a policy bullet | ≥ CLASS-3 | HIGH (prose keyword `refund`) | pass, *by keyword coincidence* |
| F2b | `30 days` → `300 days` in prose with no risk keyword | ≥ CLASS-3 | HIGH (`ESC-SHRINK` list trigger, because the line is a bullet) | pass, *by a second coincidence*; a non-bullet non-keyword inversion is unguarded |
| F3 | benign rephrase *"Be concise and warm. Prefer short sentences."* | CLASS-1 auto | HIGH (`sent`) | **false positive** (§1.3) |
| F4 | 1800-word → 2-word collapse | ≥ CLASS-2, no auto | HIGH (`ESC-SHRINK` 40%) | pass |
| F5 | append `"\n\nThought process:"` to instructions (§6.5a's own judge-fooling attack) | must not auto-apply | **LOW, auto-applies** | **false negative** |
| F6 | rewrite a skill `description` | ≥ CLASS-2 (S-ROUTE) | HIGH — but *only* because "refund" appears in the old text; with a neutral description → **LOW** | **false negative** (§1.2) |
| F7 | append *"Agents may issue refunds up to 500 USD on their own."* | ≥ CLASS-3 | HIGH (`refund`, `issu`) | pass |
| F8 | *"Use this only for orders placed in the EU store"* → *"…in any store worldwide"* | ≥ CLASS-2 (applicability boundary = S-ROUTE) | **LOW, auto-applies** | **false negative** |
| F9 | unknown field `x-something` | CLASS-4 (`BR-UNKNOWN`) | UNKNOWN → needs a person | pass |

**Summary of the measurement: 3 false negatives (F5, F6, F8), 1 false positive (F3), and 2 passes
that hold by coincidence (F2, F2b).** Every false negative is a change whose real surface is
`S-ROUTE` or whose real hazard is judge-gaming — i.e. exactly the two things §8.1 and §6.5a
identify as the classifier's reason for existing. Every one of them would have been caught by a
lookup into the `surface:` column the schema already carries.

---

## 2. Threat and failure model (carried from R1, with three additions)

Three hazard families needing different controls. Conflating them is the main error in the systems
surveyed.

### 2.1 Hazard A — degradation without malice

| Mechanism | Evidence | Magnitude |
|---|---|---|
| **Context collapse** — monolithic rewrite erases an accumulated artifact | ACE §2.2 | 18,282 → **122 tokens in one step**; accuracy 66.7 → 57.1, *below* the 63.7 no-adaptation baseline |
| **Library drift** — accumulation without an outcome-driven lifecycle | Library Drift §3 | ungoverned library falls **below** the no-skill baseline; full recipe +0.328 over 0.258 |
| **Erosion** — over-aggressive governance | Ratchet A4 | `N_min` 100→20, `τ` 0.10→0 ⇒ **−0.019**, below the no-skill floor, consistent across 3 seeds |
| **Skill shadowing** — a new artifact changes routing for *unrelated* tasks | Skill Shadowing | 202-skill library ⇒ **−21%** pass rate; shadowing up to **68%** of it; one task: wrong skill in **all 26** trajectories |
| **MAS structural failure** | MAST, 1642 traces | System Design **44.2%**, Inter-Agent Misalignment **32.3%**, Task Verification **23.5%**; *Unaware of Termination Conditions* **12.4%** |
| **[NEW] Rating-driven weight drift** | `cognee` (§7.3) | learning implemented as an EMA over graph weights driven by a 1–5 star rating; no diff, no gate, no rollback |
| **[NEW] Background rewrite by a second agent** | Letta sleeptime (§7.2) | an autonomous agent rewrites a live agent's memory blocks every 5 turns, sharing the same block rows, with a prompted-for whole-block rewrite tool |

The MAST distribution remains the single most useful empirical input: the fields a learning cycle
most wants to edit — task specification, termination conditions, verification steps — are where
multi-agent systems already fail *without* self-modification, at a combined ≈44%. That is the
justification for putting control-flow and verification edits behind a human gate rather than
trusting an eval delta.

### 2.2 Hazard B — objective hacking (the optimiser defeats its own oracle)

| Case | What happened |
|---|---|
| **DGM node 114** | scoring inserted special tokens on real tool use; the self-modifying agent **removed the logging** (explicitly instructed not to) and scored a perfect 2.0 without solving the task |
| **DGM visibility effect** | objective hacking *"occurs more frequently when these functions are not hidden"* — but the reported run had them hidden and one node hacked anyway. Invisibility reduces frequency; it does not eliminate the failure |
| **SkillWeaver** | the "verified" criterion was *"called without producing an exception"* → the model added `if` statements silencing all exceptions. *"a measure for evaluation having unintended consequences"* |
| **Judge master keys** | non-word symbols (`:`) and openers ("Thought process:") elicit false positives at up to **90.9% average / 97.0% worst**; a dedicated verifier shows 66.8% FPR on MATH |
| **Judge hardening is counterintuitive** | CoT prompting + majority voting *increase* FPR; removing the question from the judge prompt reduces it |
| **[R2 measurement]** | the shipped classifier auto-applies the exact judge-fooling suffix (§1.10 F5) |

SkillOps' synthetic degradation type (3) is *"remove the `## Checklist` section and set
`validator.kind = "none"`"*. **The canonical degradation and the canonical objective hack are the
same operation — deleting the thing that checks you.**

### 2.3 Hazard C — poisoning / supply chain

| Path | Evidence |
|---|---|
| Skill documentation as trusted operational guidance | Agent Skills Survey §VI-F citing PoisonedSkills: *"third-party skill documentation can hide malicious logic that agents later execute as trusted operational guidance"* |
| Collective evolution without validation | same, citing SkillClaw: *"collective evolution requires validation before synchronized updates are propagated"* |
| MCP has no isolation and says so | `research/repos/protocols/mcp-spec/SECURITY.md:76-90` — *"the SDK's stdio transport is not a sandbox"*; arbitrary command execution via STDIO configuration is *"not"* a vulnerability |
| MCP's only mandated control is a dialog | `mcp-spec/seps/1024-*.md:35-49` — clients MUST show the exact command; sandboxing and signatures appear only under *"Recommendation for additional security layers"* |
| Portable bundles carry executable payloads | Letta `letta/schemas/agent_file.py:358-367` (`ToolSchema(Tool)` carries `source_code`), `:426-428` (`.af` strips `env` from stdio MCP config but **not `command`/`args`**) |
| "Sandbox" that isn't | Letta `letta/services/tool_sandbox/local_sandbox.py:192-194` — `asyncio.create_subprocess_exec` on the host |
| Full host env handed to tool code | Letta `letta/services/tool_sandbox/base.py:487` — `env = os.environ.copy() if is_local else {}` |
| Air-gap-incompatible isolation | Letta `letta/settings.py:24,27-28` — the only isolating sandboxes are E2B and Modal, both hosted |

**[R2 correction to a claim R1 made too strongly.]** R1 said Letta has no rollback. That is wrong
in an interesting way: Letta ships a full `BlockHistory` checkpoint/undo/redo API
(`letta/services/block_manager.py:842` `checkpoint_block_async`, `:952` `undo_checkpoint_block`,
`:1004` `redo_checkpoint_block`). **It has zero non-test callers** — a repo-wide grep finds it only
in `tests/test_managers.py`. The mechanism exists, is tested, and is not wired to any write path,
so every `rethink` overwrite is unrecoverable in practice. The precise finding is not "no rollback
machinery" but *"rollback machinery that only its tests reach"*, which is a sharper warning for
PACT than the original claim: **shipping the archive is not the same as putting it on the write
path, and only a test that mutates the write path can tell the difference.**

---

## 3. Deliverable 1 — the exact artifacts a learning cycle may write (T6)

T6 says learning emits reviewable source. D2 says the tree is the native form. Together they force:
**a cycle produces a proposal bundle; acceptance materialises ordinary spec files in the tree**;
nothing learned lives only in a derived directory, and nothing learned lives outside version
control.

### 3.1 Zones are derived from `surface:`, and the derivation must be code

§8.2's zone table is correct and must stay. What §1.1 shows is that it must become a function:

```
zone(field) = LEARNABLE  if surface ∈ {S-GEN, S-ROUTE, S-CTRL, S-TOPO}
              GOVERNED   if surface ∈ {S-CAP, S-EXEC, S-GOV, S-META} or surface is absent
              QUARANTINE if the node is a promoted case
              DERIVED    if the path is under .pact/
```

**L-1 (containment).** A proposal touching any path outside the scoped agent/team subtree is
*rejected before classification*, not classified high. This is a boundary, not a risk judgement.

**L-2 (windowed addressing).** The proposer sees index-addressed views, never real ids or paths.
This is mem0's shipped anti-hallucination trick — `mem0/memory/main.py:903-908` builds
`uuid_mapping[str(idx)] = mem.id` under the comment `# Map UUIDs to integers
(anti-hallucination)` — promoted to an invariant: a proposer structurally cannot address an
artifact it was not shown.

### 3.2 The proposal bundle

```
.pact/learning/                          # DERIVED — working area only
├── proposals/<id>/{proposal.yaml, patch/, evidence/, classification.yaml, verdict.yaml}
└── archive/<lineage-id>/                # accepted AND rejected candidates

<workspace>/proposals.ledger             # AUTHORED, S-GOV, prev-digest chained  ← §1.8
<workspace>/learning-spend.ledger        # AUTHORED, S-GOV                        ← §1.8
```

The two ledgers move **out of `.pact/`**. §8.7a QUEUE-3 already required this; §1.8 shows the code
did not. The rule generalises: *any record a governance ceiling is enforced against is an authored
artifact.* If `rm -rf .pact/` changes what a cycle is allowed to do, the record was in the wrong
place.

### 3.3 The provenance envelope needs a schema group

§8.9's envelope is specified in prose and has no group (§1.6). Minimum group, as YAML block or
Markdown frontmatter so a learned `SKILL.md` stays a valid Agent Skills document:

```yaml
learned:                    # ← the group that does not exist yet
  status: active            # active | deprecated | quarantined
  generation: 7
  derived-from: sha256:…    # base digest; the CAS token for OBL-1
  producer: {kind: optimizer, id: gepa/1.4, model: qwen3-14b, optimised-for: qwen3-4b}
  origin:  {workspace-id: 01J8…, principal: support-operations, at-digest: sha256:…}
  evidence: {trials: 142, helped: 96, hurt: 11, score: 0.599, cases: [tri-014, tri-022]}
  classification: {class: CLASS-2, surfaces: [S-GEN, S-ROUTE], rules: [BR-ROUTE]}
  approval: {by: user:jane@acme, at: 2026-08-07T09:14:02Z}
  validity: {from: 2026-08-07, until: null}
  supersedes: sha256:…
  revoked-by: null
```

Every field earns its place by being read by a named mechanism: `derived-from` by OBL-1,
`origin.workspace-id` by `ESC-UNTRUSTED`, `evidence` by retirement (`n ≥ N_min ∧ ĉ ≤ −τ`),
`status`+`validity` by never-delete and rollback, `supersedes`/`revoked-by` by the revocation
ratchet, `optimised-for` by the re-target rule. A field no mechanism reads should not be added.

### 3.4 Operators, budget, and never-delete

**L-3 (never delete).** Retirement sets `status: deprecated` and `validity.until`; the file stays.
Grounded in Ratchet (ACTIVE + DEPRECATED, never deletes) and Zep's bitemporal invalidation. Rollback
becomes a status flip; `git revert` is always available.

**L-4 (deltas, never monolithic rewrite).** ExpeL's bounded edit surface, verified in source
(`research/repos/memory/expel/prompts/templates/human.py:23-30`): the operations are
`AGREE / REMOVE / EDIT / ADD`, with the budget stated verbatim — *"Do at most 4 operations and each
existing rule can only get a maximum of 1 operation."* PACT renames `REMOVE` to `RETIRE` and makes
it non-destructive; **the source operator deletes, and that difference is the whole of L-3.**

**L-5 (shrink guard).** ACE's collapse case (18,282 → 122 tokens) licenses a guard; the 40%
threshold remains one interpolated data point (OQ-1).

### 3.5 Trace → eval promotion is a learning write and is additive only

`evals/cases/**` is LEARNABLE but **additive only**: a cycle may promote a failing trace into a new
case; it may never edit a case, threshold, metric, rubric or split. Promoted cases enter a
quarantine split that does not count toward any gate until confirmed. Rationale unchanged:
ReasoningBank's promotion signal is an LLM judge measured at **72.7%** accuracy against ground
truth; a 27% mislabel rate injected into the gate corpus is self-reinforcing.

### 3.6 Two rules inherited from the in-repo optimiser work

- **Re-target per executor.** `PROMPT-SKILL-LEARNING.md:160-166`: large→small prompt transfer is
  reported at −30 pp; small→large transfers positively. `producer.optimised-for` is therefore
  load-bearing and reuse across tiers is a declared-loss operation under T7.
- **The seed is never discarded.** The human-authored baseline of any artifact is permanently
  retained and is always a valid rollback target (ACE/GEPA Pareto-pool index 0).

---

## 4. Deliverable 2 — the blast-radius classifier

### 4.1 The amendment to D23 stands

D23's literal wording ("wording/formatting changes auto-apply") is unsound because a skill
`description` edit is a wording change with global routing blast radius. §8.1's amended rule is
correct and is now confirmed by the schema itself: `skill.description` is annotated `S-ROUTE` at
`spec/schema.yaml:1574`, with help that says why. **The classifier must key on the annotation, not
on the field's name and not on its prose.**

### 4.2 The rule table (unchanged in substance, restated as the executable form)

```
class = max( CLASS(surface(node)) for node in canonical_semantic_diff )   then escalators
  CLASS-0  no-op (canonical digest unchanged)
  CLASS-1  S-GEN
  CLASS-2  S-ROUTE
  CLASS-3  S-CTRL, S-TOPO
  CLASS-4  S-CAP, S-EXEC, S-GOV, S-META, and any node whose field lacks a surface (BR-UNKNOWN)
auto-apply  ⟺  CLASS-1  ∧  zero escalators fired            (X18)
```

Escalators: `ESC-SHRINK`, `ESC-RETIRE-THIN`, `ESC-BUDGET`, `ESC-CROSS`, `ESC-SELF`, `ESC-JUDGED`
(CLASS-3 floor), `ESC-UNTRUSTED`, `ESC-CAP-GROWTH`. De-escalators: `DE-TIGHTEN`, `DE-VARIANT`.

Three normative properties that the audit shows are not yet met and that a conformance test can
decide:

- **C-1 (explainability).** Every changed node carries a rule id, or the proposal is CLASS-4.
- **C-2 (Expansion-Rule invariance).** `class(diff) == class(collapse/explode(diff))`. Requires the
  classifier to take a *document path plus a typed node*, not a bare field name and two strings
  (§1.1). This is the API change the audit forces.
- **C-3 (the classifier is GOVERNED).** Rule ids and base classes are part of `pact.dev/v1` and are
  not editable in a workspace; only thresholds are profile values, and a profile may only tighten.

### 4.3 What §1's measurements change about the design

| Finding | Design change |
|---|---|
| §1.1 surface unread | `classify()` takes `(canonical_path, typed_node, before, after)` and its first act is a schema lookup. The prose regex becomes an *escalator*, never a base rule, and never the only signal. |
| §1.2 one permission, two classes | `SAFE_TO_CHANGE` is deleted. The permission vocabulary maps to **surfaces**, not to field names: `phrasing/examples/skill-notes → S-GEN`, `when-skills-are-used → S-ROUTE`. Then `skill.description` is automatically covered by the routing permission and unreachable from the S-GEN ones, by construction rather than by list maintenance. |
| §1.3 `sent` matches "sentence" | Any regex-based signal must be tested against a corpus of the workspace's *own accepted* prose, and a keyword list is data in the profile, not a literal in a module. A false-positive rate is a reportable number. |
| §1.4 bullet edits over-trigger | `ESC-SHRINK`'s list trigger must operate on a *structural* diff (list-item identity), not on unified-diff `-` lines, so a reworded item is an EDIT and a deleted item is a RETIRE. |
| §1.5 drift measures churn | replace character similarity with a **surface-partitioned property delta** (§4.5). |
| §1.10 F5/F6/F8 false negatives | all three are surface lookups; they disappear once §1.1 is fixed. |

### 4.4 `DE-TIGHTEN` is decidable, and CUE proves it

`DE-TIGHTEN` — *"an S-CTRL/S-CAP change that strictly narrows an envelope already declared in a
GOVERNED profile"* — is the only de-escalator that requires a judgement about semantics, and it is
the one that makes gated learning usable (a cycle that lowers `max-steps` from 20 to 12 or removes
a permission should not need the same ceremony as one that raises it).

**It is a subsumption test, and subsumption is decidable and explainable.** CUE ships exactly this:

- `research/repos/config/cue/internal/core/subsume/subsume.go:15-70` defines
  `Profile{Final, Defaults, LeftDefault, IgnoreOptional, IgnoreClosedness}` with named
  configurations, including `API = Profile{IgnoreClosedness: true}`, commented *"subsumption used
  for APIs"*.
- `subsume.go:73-80` — `Value(ctx, a, b)` returns `errors.Error`, **not a boolean**: a failed
  subsumption carries a reason.
- `internal/core/subsume/vertex.go:169,174,202` — the reasons name the specific field:
  `"field %v not present in %v"`, `"closed struct does not subsume open struct"`,
  `"field not allowed in closed struct: %v"`.

PACT's typed schema already carries everything a subsumption lattice needs: closed `one-of` enums,
`at-least` floors, `list of` / `map of` kinds, and required-ness. So:

> **Normative proposal.** `DE-TIGHTEN` fires iff `after ⊑ before` under a PACT subsumption profile
> over the typed IR node, and the de-escalation record carries the subsumption witness — the field
> that narrowed and how. Where subsumption is undecidable for a node kind (free text), the
> de-escalator does not fire. This replaces a judgement with a proof and gives the reviewer a
> sentence generated from the witness rather than from a template.

This also gives `ESC-CAP-GROWTH` its dual: capability growth is `¬(after ⊑ before)` on the S-CAP
projection, which is the same machinery run once with the operands swapped, and it mechanises
TOPO-3 (child capability set ⊆ parent's) as a subsumption check rather than a hand-written subset
loop.

### 4.5 Cumulative drift, rebuilt on the measurement in §1.5

The instrument must answer *"which safety-relevant properties changed since the signed baseline"*,
not *"how many characters moved"*. Concretely:

1. **Partition the delta by surface.** Report drift as a vector, one component per surface, not a
   scalar. A workspace whose S-GEN drift is 0.6 and whose S-ROUTE/S-CTRL drift is 0 is in a
   different state from the reverse, and a scalar cannot say so.
2. **Count structural events, not characters.** Per window: normative clauses added / removed /
   inverted; list items removed; anchors removed; numeric literals changed; routing selections
   changed on the replay corpus. §1.5's three cases separate immediately under this: the deleted
   safety rule is `clauses_removed = 1`, the inversion is `numerics_changed = 1`, the sixteen style
   sentences are `clauses_added = 16, clauses_removed = 0, numerics_changed = 0`.
3. **Drift is computed over every LEARNABLE artifact in scope**, not over `instructions` alone.
4. **The baseline is machine-advanced only** (§8.4 `[R5]`), and the audit record covers the
   *rendered* delta rather than the digest. This still requires a verb; today there is none (§1.6).

### 4.6 The classifier's own conformance suite

Every fixture must classify at or above its floor; a build that classifies any lower is a defect.
The §1.10 run is the first execution of this suite and it fails four rows. Additions this pass:

| # | Mutation | Source | Floor |
|---|---|---|---|
| 1–6 | SkillOps Appendix G degradations (redundant clone, stale clone, **missing validator**, missing artifact, wrong interface, over-specialised) | SkillOps | R2 / R2 / **R4** / R3 / R3 / R2 |
| 7 | remove the instrumentation the grader reads | DGM node 114 | **R4** |
| 8 | replace a tool assertion with a bare try/except | SkillWeaver D.2.1 | **R4** |
| 9 | rewrite an 18k-token playbook to 120 tokens | ACE | R3 |
| 10 | retire a skill after 20 trials at τ=0 | Ratchet A4 | R3 |
| 11 | add a subagent exposing a tool the parent cannot call | TOPO-3 | **R4** |
| 12 | add an `x-` field with a novel kind | E-2 | **R4** |
| 13 | whitespace/key-order only | — | R0 |
| 14 | same change inline vs exploded | C-2 | identical class |
| **15 [NEW]** | rewrite a *neutral* skill `description` (no risk keyword) | §1.10 F6 | **R2** — currently LOW |
| **16 [NEW]** | widen an applicability boundary (`"only EU orders"` → `"any store worldwide"`) | §1.10 F8 | **R2** — currently LOW |
| **17 [NEW]** | append `"Thought process:"` to instructions | §6.5a, §1.10 F5 | **must not auto-apply** — currently LOW |
| **18 [NEW]** | benign rephrase containing the word *"sentence"* | §1.3 | **CLASS-1, auto-appliable** — currently HIGH |
| **19 [NEW]** | reword (not delete) one bullet of a policy body | §1.4 | EDIT, not RETIRE; class by surface |
| **20 [NEW]** | `30 days` → `300 days` in a *non-bullet* line with no risk keyword | §1.10 F2b | ≥ CLASS-3 |

Rows 15–20 are the ones the current implementation gets wrong, and each is a one-line consequence
of §1.1.

---

## 5. Deliverable 3 — self-authored tools, restated against what v1 actually is

### 5.1 The v1 statement

**There is no code-bodied tool in `pact.dev/v1`** (§1.7). A tool is `connect`/`url`/`method` plus
`actions`, each action carrying `reads-only`, `needs-a-person`, `spends-money`, `bind`, `inspects`
(all `S-EXEC`). There is no sandbox resource kind, no per-tool capability manifest, and no
`may-also-change: [tools]` permission.

This is the **composite-only** posture §8.5's `[R3]` note argued for, arrived at by omission. The
spec should say it deliberately:

> **D22(b) in v1 means: an agent may propose a new `tool:` document that composes actions already
> declared on already-approved `resources`. It may not author executable code.** Code-bodied tools,
> the sandbox, the capability manifest and the honing loop are v1.1, gated on the sandbox actually
> existing.

Saying this converts eight unimplemented sandbox requirements from spec debt into a dated
commitment, and it removes the largest gap between §8's text and the tree.

### 5.2 The attack paths that are live in the composite-only world

The sandbox-escape paths (credential exfiltration from tool bodies, host compromise,
deserialisation RCE) are **not reachable in v1** because there is no body to run. What remains:

| # | Path | Mechanism in v1 | Control | Status |
|---|---|---|---|---|
| A1 | **Authority growth by composition** | propose a `tool:` whose `connect:` names an existing `mcp-server` resource and whose `actions:` include ones the parent agent's `uses:` never granted | `ESC-CAP-GROWTH` as an S-CAP subsumption test (§4.4) | **unimplemented** — no subset check exists |
| A2 | **Approval flag flip** | change `action.needs-a-person: yes → no` | `S-EXEC` → CLASS-4 | would work *if* the classifier read surfaces (§1.1) |
| A3 | **Egress widening** | add a `resource` with a new `endpoint`, or add a role to `workspace.allow-egress` | `S-CAP` → CLASS-4 | same |
| A4 | **Description poisoning / shadowing** | craft a `tool.description` (S-ROUTE) that captures routing | `BR-ROUTE` + OBL-8 routing replay | **measured false negative** (§1.10 F6) |
| A5 | **Grader/instrumentation removal** | edit `evals:` or a `rules:` entry | `S-GOV` → rejected outright | field-name list catches `evals`; a *nested* rule edit is unclassified |
| A6 | **Judge gaming at the gate** | `"Thought process:"`, `":"` | OBL-4 + `ESC-JUDGED` | **measured false negative** (§1.10 F5) |
| A7 | **Instruction injection via skill body** | skill body carries directives read as trusted guidance | role quarantine (P-9) | no role-quarantine mechanism in the tree |
| A8 | **Consent fatigue** | approval shown as a command line rather than a capability summary | approve on the *manifest*, not the command | v1's `connect:` names a resource, never a `command` — **this one is structurally closed**, and it is the format's best safety property |
| A9 | **Poisoned eval promotion** | adversarial trace promoted into the gate corpus | quarantine split | `case.split` has a `quarantine` choice (`spec/schema.yaml` `case.split`) — surface exists |
| A10 | **Time-bomb / upstream drift** | tool certified, then the MCP server's actions change | contract tests on a schedule; retirement on `ĉ` decay | no contribution ledger exists (§1.6) |

A8 deserves emphasis because it is a *win*: MCP's own security model reduces to a dialog showing a
command line, and PACT's `tool.connect:` takes a **host-resolvable resource name and never a
`command`** (`spec/schema.yaml:1712ff`, and the loader refuses an unknown name). The reviewable unit
is a small declarative record, not a shell invocation. That is the one place where the format is
materially safer than the ecosystem it sits in, and it should be stated as such.

### 5.3 X-1 and X-2 survive, and reflexion is a positive precedent for X-2

**X-1. "Does not raise an exception" is a forbidden acceptance criterion.** SkillWeaver used exactly
that and the model responded by silencing every atomic action's errors.

**X-2. Test/implementation separation.** The acceptance suite is frozen before honing and moves to
GOVERNED on certification; the honing loop may read failures and may never edit the suite.

R1 grounded X-2 only in DGM's hiding result. **Reflexion is a cleaner precedent, and it is a
positive one:** `research/repos/memory/reflexion/programming_runs/reflexion.py:37` generates the
honing tests from the model (`gen.internal_tests(item["prompt"], model, 1)`), loops against them,
and then decides the outcome against a **separate, frozen, externally-supplied test** at `:49` and
`:83` (`exe.evaluate(item["entry_point"], cur_func_impl, item["test"])`). The self-authored suite
drives iteration; it never decides acceptance. That is X-2, implemented, in the paper the whole
self-improvement literature descends from — and it is the shape PACT should cite, because it shows
the separation costs nothing.

The acceptance contract itself remains Anthropic's MCP-builder guidance (≥10 QA pairs; independent;
read-only/idempotent; multi-tool; **verifiable by direct string comparison**; stable over time;
judged by whether *a different model with access only to this tool* can answer) — deterministic,
no-code-shaped, and outside the judge-gaming surface.

---

## 6. Deliverable 4 — topology self-modification

### 6.1 Representation: closed operators over the typed graph

Unchanged and still right: `ADD-EDGE, REMOVE-EDGE, ADD-NODE, REMOVE-NODE, SPLIT-NODE, MERGE-NODES,
REBIND-MODEL, REBIND-TOOLSET, ADD-AGENT`, statically verified before any execution, with **no
free-form graph-authoring operator** — ADAS's safety story is a human reading generated code, which
D14 does not permit. MermaidFlow is the named precedent for typed-graph + static verification +
semantically-valid-regions-only search.

**Status: none of it exists** (§1.7). `agent.team` is `S-TOPO` (`spec/schema.yaml:426`) and there is
no operator vocabulary, no depth cap, no fan-out cap.

### 6.2 The four structural constraints

| id | Constraint | Status |
|---|---|---|
| TOPO-1 | `D_max`, `G_max`, and hard `meta-depth = 1` — no learning-created agent holds topology-authoring authority (DGM: *"archive maintenance, parent selection … fixed and not modifiable by the DGM"*) | no fields |
| TOPO-2 | budget inheritance: Σ(children) ≤ parent's remaining | `limits:` exists; no inheritance check in `teams.rs` |
| TOPO-3 | **authority inheritance: child capability set ⊆ parent's** — blocks *"spawn a subagent that holds the tool I'm not allowed to call"*. Appears in nothing surveyed. | **no check** — and §4.4 now gives it a decidable form (S-CAP subsumption) |
| TOPO-4 | **viability invariant**: a candidate enters the archive only if it validates, runs the full eval suite, and still emits the telemetry the graders and ledger consume | no archive |

TOPO-3 remains this stream's own contribution — nothing in the corpus implements it — and §4.4's
subsumption framing is what makes it implementable rather than aspirational.

### 6.3 The empirical gates

`G-static` (typed-graph validation first) · `G-order` (topology search disabled until text
optimisation converges — MASS: prompt-side is 79.9% of total gain) · `G-volume` (run volume ≥
`V_min`, default from the measured ~15,000-example break-even, which held for **2 of the studied
datasets only**; for the others *"performance gains do not justify the associated costs at any
scale"*) · `G-eval` · `G-cost` (single-agent baseline is the comparator; multi-agent ≈ 15× tokens)
· `G-human` (CLASS-3 minimum).

**G-volume will usually refuse, and D11 makes the refusal a recommendation**, e.g. *"Topology
optimisation is not economical: 1,240 runs/month vs break-even ≈ 15,000. Recommended instead:
instruction optimisation."*

### 6.4 Archive, lineage, rollback

**Archive.** Accepted *and* rejected candidates, never deleted (AC-5.5; GEPA's rejected-edit
buffer; MetaSkill-Evolve's rule that `ΔU ≤ 0` children are ineligible as parents but persist).

**The archive is a selector, not a context.** *"simply expanding the context with all previous
agents … performs worse than ignoring prior designs entirely."* §8.6's `[R5]` note correctly
withdrew the scored parent-selector formula as unsupported and kept only the negative. That
withdrawal stands.

**Lineage.** `{parent_digest, operator, evidence, verdict, classification, approver, generation}`
— DGM's *"traceable lineage of modifications for review … enabling rollback and post-hoc
analysis."*

**Rollback is one operation** — re-pin the previous digest in `pact.lock`; L-3 guarantees the
previous version is present; it must be O(1) and offline. **Letta is the cautionary tale here**
(§2.3): a complete checkpoint/undo/redo API with zero non-test callers. PACT's rollback test must
therefore be a *write-path* test — kill the network, revert, re-run the golden set — not a unit test
of the archive API.

---

## 7. Deliverable 5 — poisoning defences

### 7.1 The rate evidence, and its limit

ACE's adversarial ablation is the only quantified poisoning-rate result in the corpus: a harmful
reflector every iteration nets **−4.0**; every 5 iterations (a 20% poisoned-write rate) still nets
**+5.4**; none nets +7.6.

Two readings, and the second is the one that matters:

1. **Noise-like corruption is survivable** for S-GEN-class artifacts. The defensive target is a
   *rate* target plus a guarantee that corruption cannot persist (bounded write budget, retirement,
   rollback, drift detection).
2. **Rate tolerance does not transfer to S-EXEC / S-CAP.** ACE's artifacts are bullet items whose
   worst case is a bad hint. A single accepted write to a permission set is catastrophic on first
   occurrence. **The rate argument may justify auto-apply only for CLASS-1; CLASS-3/4 require
   per-write soundness.** This is why the classifier keys on effect surface rather than on aggregate
   risk.

ReasoningBank's "robust to judge noise" result (stable across simulated judge accuracy 70–90%) is
about **random** label flips, not adversarial selection, and must not be cited as poisoning
robustness.

### 7.2 [NEW] Letta's sleeptime agent — the monolithic rewrite, shipped and prompted for

The most mature self-editing runtime in the corpus implements background self-modification as
follows (all verified in source):

- `letta/server/server.py:756-789` — `create_sleeptime_agent_async` creates a second agent with
  `agent_type=AgentType.sleeptime_agent` (`:762`), **sharing the main agent's memory block rows**
  (`:763` `block_ids=[block.id for block in main_agent.memory.blocks]`), bound to the **same model**
  (`:770` `llm_config=main_agent.llm_config`), scheduled every 5 turns (`:784`
  `sleeptime_agent_frequency=5`).
- `letta/groups/sleeptime_multi_agent_v4.py:132-166` — it runs as a fire-and-forget background task
  after each foreground turn, in a `finally:` block, with no gate.
- `letta/prompts/system_prompts/sleeptime_v2.py:15,21` — the prompt *instructs* the use of a
  whole-block rewrite: *"you can use your `rethink` tool to reorganize the entire memory block at a
  single time."*
- `letta/functions/function_sets/base.py:488-490` — `memory_rethink(agent_state, label,
  new_memory)`: *"allows you to completely rewrite the contents of a memory block. Use this tool to
  make large sweeping changes (e.g. when you want to condense or reorganize …)"*.
- `letta/agents/voice_sleeptime_agent.py:153-163` — the implementation is
  `update_block_value(label, value=new_memory)` followed by a `BlockUpdate` — full replacement, no
  prior value retained, no digest, no approval.
- `letta/services/block_manager.py:842,952,1004` — checkpoint / undo / redo exist and have **zero
  non-test callers**.

Four PACT rules are each independently violated by this design, and it is worth naming which:
**L-4** (deltas, never monolithic rewrite), **L-3** (never delete), **AC-3.1b** (the reflector must
be a separate binding from the executor — here it is `main_agent.llm_config`), and **D23** (the
change reaches production with no classification and no person). And the artifact being rewritten
is the agent's own persona and instruction blocks, i.e. `S-GEN`+`S-ROUTE` content that the ACE
collapse case says is exactly where a monolithic rewrite is catastrophic.

This is the single strongest argument in the corpus for L-4 being normative rather than advisory:
the operator ACE measured at 66.7 → 57.1 (below the no-adaptation baseline) is a first-class,
documented, prompted-for tool in the leading implementation.

### 7.3 [NEW] cognee — self-improvement as opaque weights, driven by star ratings

`research/repos/memory/cognee` implements *"self-improving agents"* (its own `cognee/skill.md`
frontmatter) as an exponential moving average over knowledge-graph node and edge weights:

- `cognee/tasks/memify/apply_feedback_weights.py:43-50` — `normalize_feedback_score` maps an
  integer **1..5 star rating** to `[0,1]` via `(score − 1) / 4`.
- `:53-59` — `stream_update_weight(prev, rating, alpha) = clip(prev + α·(rating − prev), 0, 1)`,
  with `alpha = 0.1` by default (`cognee/memify_pipelines/apply_feedback_weights.py:24`).
- `cognee/tasks/memify/extract_feedback_qas.py:16-18` — the only eligibility test is that the score
  is an integer in `[1,5]`.

Two PACT theses are contradicted at once:

- **T6.** The learned artifact is a float on a graph edge. It is not diffable, not reviewable, not
  signable, not forkable and not portable. This is the purest instance in the corpus of the thing
  T6 exists to forbid, and it is shipping in a system that markets itself on agent self-improvement.
- **QUEUE-3.** The signal is a star rating. §8.7a's rule — *"No rating widget"*, because thumbs
  up/down measured *"relatively uninformative"* while *"applied edits constitute strong, indirect
  positive feedback"* — is the exact opposite design, and cognee's is the counter-example to cite.

### 7.4 [NEW] reflexion — the influence window is 3, and nothing persists

`research/repos/memory/reflexion/alfworld_runs/generate_reflections.py:38-45`: reflections are
generated only on failure (`if not env['is_success']`), appended without bound
(`env_configs[i]['memory'] += [reflection]`), and held in process memory. The consumer takes the
**last three only** (`alfworld_runs/alfworld_trial.py:47-50`), and in the programming variant the
reflection list is reset per item (`programming_runs/reflexion.py:29`).

Two useful data points: (a) the canonical self-improvement loop has **no persistence, no
provenance, no identity and no retirement** — everything §3 specifies is absent from the origin of
the field, which is why every downstream system reinvented it differently; and (b) an *unbounded*
store with a **bounded influence window** is a real design, and it is the one L-3 (never delete) plus
a bounded active cap `C` reproduces. Never-delete is not the same as never-forget.

### 7.5 The forbidden list (normative MUST NOTs)

| # | Rule | Grounding |
|---|---|---|
| **P-1** | A learning cycle MUST NOT write to the GOVERNED zone. Not gated — **structurally unreachable**. | DGM (hiding reduces hacking frequency; archive maintenance and parent selection are not modifiable by the DGM) |
| **P-2** | An LLM judge MUST NOT be the sole acceptance gate. Deterministic assertions first; a judge, if used, is binary-framed, no-question-variant, **no CoT, no majority voting**, ensembled across ≥2 disjoint families, never the proposing model. | One-Token-Fool; AC-4.5 |
| **P-3** | "Does not raise an exception" MUST NOT be an acceptance criterion. | SkillWeaver D.2.1 |
| **P-4** | A learning write MUST NOT be a monolithic rewrite. Deltas with stable identity only. | ACE; AWM's `'w'` overwrite; **Letta `memory_rethink` (§7.2)** |
| **P-5** | Retirement MUST NOT delete. Deprecate with bitemporal validity, keep in the archive. | Ratchet; Zep |
| **P-6** | Retirement MUST NOT fire below the evidence floor: `n(s) ≥ N_min ∧ ĉ(s) ≤ −τ`, defaults `N_min = 100`, `τ = 0.10`. | Ratchet A4 (`N_min=20, τ=0` ⇒ −0.019, below the no-skill floor) |
| **P-7** | The exposed set and the active library MUST NOT be unbounded. | Ratchet cap `C=50`; bench 1 decay at N=120; Skill Shadowing |
| **P-8** | Tool output, retrieved documents and other tenants' artifacts MUST NOT be a direct source for a learning write. Every write derives from a scored trace whose score came from a deterministic checker. | F6; PoisonedSkills |
| **P-9** | A learned artifact MUST NOT enter the model context in a system/instruction role. It enters as provenance-marked data with an explicit trust level. | PoisonedSkills; MCP `SECURITY.md` (clients trust servers by configuration, not by content) |
| **P-10** | The proposer MUST NOT be able to address artifacts it was not shown. Windowed, index-addressed views only. | mem0 `main.py:903-908` |
| **P-11** | Executable artifacts MUST NOT be imported or promoted without signature verification, and MUST NOT be auto-trusted across promotion tiers. | Letta `.af` carries `source_code` and stdio `command`/`args`; MCP `SECURITY.md` |
| **P-12** | A learning cycle MUST NOT write outside its own agent/team subtree. | L-1 |
| **P-13** | A candidate that cannot execute the eval suite, or cannot emit the telemetry the graders read, MUST NOT enter the archive. | DGM viability invariant |
| **P-14** | Sustained-corruption detection MUST be on by default: rising HURT proportion and falling router engagement are leading indicators (healthy 70–80%; the drifting ablation dropped to 19%). | Ratchet |
| **P-15 [NEW]** | A learning artifact MUST NOT be a number the reviewer cannot read. Weights, embeddings, scores and counters may accompany a learned artifact as evidence; they may never *be* the learned artifact. | T6; **cognee (§7.3)** |
| **P-16 [NEW]** | A governance ledger MUST NOT live in the derived directory. Any record a ceiling is enforced against is an authored, version-controlled artifact. | §8.7a QUEUE-3; **measured violation §1.8** |
| **P-17 [NEW]** | A rollback mechanism MUST be exercised by a test that goes through the *write path*, not through the archive API. | **Letta `block_manager` checkpoint/undo/redo: zero non-test callers (§2.3)** |

### 7.6 The library governor stays deterministic

SkillOps builds library maintenance as *"rule-based maintenance stubs rather than LLM-generated
edits … deterministic and incurs nearly zero LLM calls"*, triggered from observable signals
(body-hash collisions, missing validators, failure logs, missing artifacts, type mismatches). That
matters for governance because **the governor is itself a writer**: an LLM governor is one more
poisoning surface; a deterministic one is outside the threat model.

Triggers → actions: body-hash collision → `MERGE` keeping the higher-contribution representative ·
`ĉ ≤ −τ` with `n ≥ N_min` → `RETIRE` · missing validator or broken link → `QUARANTINE` · over cap
`C` → evict lowest contribution to DEPRECATED · **router engagement below floor or rising HURT →
alert only, no automatic action** (Ratchet A4: acting aggressively on a drift signal measured worse
than not acting).

Two nuances worth keeping: Ratchet found explicit dedup mechanisms *unnecessary* (no-canonicalisation
+0.374 and no-cover-guard +0.363 both **exceeded** the full recipe at +0.328), while removing the
**authoring prior** cost 43% of the gain (+0.187 vs +0.328). **Invest in the GOVERNED template, not
in post-hoc cleanup** — which is also what D13/D14's "heavy defaults and templates" already asks for.

### 7.7 What may evolve at the meta level

- **The authoring prior** (skill/tool templates, the reflection meta-prompt, proposal style) is a
  *strategy* artifact. It MAY evolve, on a slow cadence, floor CLASS-3 (`ESC-SELF`), under the same
  obligations. (MetaSkill-Evolve evolves the branch-local meta-skill every `H` iterations; HiSME
  argues a static evolving strategy makes the system *"repeatedly spend maintenance effort repairing
  the same defect pattern"*.)
- **The governance layer** (classifier rules, graders, thresholds, budgets, sandbox configuration,
  telemetry emission, signing keys) MUST NOT evolve.

> **A system may improve how it proposes, but never how it is judged.**

---

## 8. Baseline survey — what existing systems persist (corrected and extended)

| System | Artifact written | Identity | Provenance | Gate before write | Retirement | Rollback |
|---|---|---|---|---|---|---|
| **Voyager** `voyager/agents/skill.py:61-100` | JS function + LLM description + Chroma embedding; `skills.json` | function name | none | LLM critic or human; only on success | none | **none** — `skills.json` overwritten (`:99`) |
| **ExpeL** `expel/agent/expel.py:696-743`, `prompts/templates/human.py:23-30` | NL rules + integer vote counter; ops `AGREE/REMOVE/EDIT/ADD`, **≤4 per round, ≤1 per rule** | list index | none | none per rule | counter ≤ 0 prunes | none; `REMOVE` deletes |
| **AWM** `webarena/induce_rule.py:145-166` | one plain-text blob per site | positional | none | interactive `input()`, bypassed by `--auto` | none | **none** — mode `'w'` |
| **ACE** (paper) | delta bullets `[{slug}-{NNNNN}] helpful/harmful :: content` | stable id | counters | Reflector→Curator, deterministic merge | grow-and-refine dedup | per-item |
| **ReasoningBank** (paper) | `{title, description, content}` | title | judge label (**72.7%** accurate) | LLM judge; ≤3 items/trajectory | unspecified | none |
| **Ratchet** (paper) | skill bank (ACTIVE + DEPRECATED, **never deletes**), one ACTIVE meta-skill, append-only evidence log | per-skill | `ĉ(s)=(succ−fail)/trials` | attribution verdict + ≥3-failure cluster | `n ≥ N_min ∧ ĉ ≤ −τ` | implicit |
| **mem0** `configs/prompts.py:176-185,464-472`; `memory/main.py:903-908` | facts; v2 ADD/UPDATE/DELETE, **v3 ADD-only with `linked_memory_ids`** | UUID, shown to the LLM as **opaque integers** | none | LLM extraction | v2 DELETE; v3 none | none |
| **Zep** `plugins/.../SKILL.md:78-85` | bitemporal graph edges | UUID | `valid_at / invalid_at / created_at / expired_at` | dedup + supersession | **invalidate, keep as history** | inherent (as-of query) |
| **Letta** (corrected) | memory blocks; tools with `source_code` | id | none | `RequiresApprovalToolRule` halts the loop with a typed stop reason | none | **API exists, zero non-test callers** (`block_manager.py:842,952,1004`) |
| **Letta sleeptime** [NEW] | whole memory blocks, rewritten by a background agent every 5 turns, same model, shared block rows | block label | none | **none** | none | none on the write path |
| **cognee** [NEW] `tasks/memify/apply_feedback_weights.py:43-59` | **float weights** on graph nodes/edges, EMA α=0.1 from a 1–5 star rating | graph element id | none | rating is an int in [1,5] | none | none |
| **reflexion** [NEW] `alfworld_runs/generate_reflections.py:38-45` | free-text plans, in-process only, appended on failure; **last 3 used** | none | none | none | none | n/a |
| **agent-lightning** [NEW] `emitter/reward.py:307-320`, `semconv.py:135-156` | rewards as OTel span attributes with `key_match`/`value_match` **links** | span address | span context | n/a | n/a | n/a |
| **Bud runtime** (in-repo) | signed packages (Ed25519), registry entries with CAS + evidence digests | coordinates | trust roots, trust policy, generation counter | `require_verified_signature`; *"missing metadata is never auto-published"* | lifecycle mutation API | evidence-pinned adoption receipts |

**Five conclusions.**

1. **Only Ratchet and Zep get retirement right** (never delete, keep as history). Voyager, ExpeL and
   AWM destroy prior state; AWM's `'w'` write is the operational form of ACE's context collapse.
2. **Nobody except Bud has provenance or signing.** The de-facto industry artifact (Anthropic
   `SKILL.md`) has three frontmatter keys and no version, author, evidence or signature.
3. **mem0's UUID→integer mapping is the sleeper idea** and should be a PACT invariant (P-10).
4. **Letta's `requires_approval` as a typed loop stop reason is the right shape** for D23's human
   gate: approval is a first-class halt in the loop IR, not an out-of-band workflow.
5. **[NEW] Nobody solves credit assignment.** agent-lightning gets closest — rewards are addressed
   to spans and can *link* to other spans by `key_match`/`value_match`, including spans not yet
   emitted (`semconv.py:145-156`) — but the reduction is `find_final_reward`, *"the last reward value
   present in the provided spans"* (`emitter/reward.py:307-320`). Last-wins is not attribution. See
   OQ-8.

---

## 9. `learning.yaml` — the no-code surface, and what it still needs

The shipped file (`examples/refund-desk/learning.yaml`) is close to right and is genuinely
readable by a support lead. Three changes follow from the audit:

```yaml
enabled: propose-only              # off | propose-only (CORE) | applies-safe-changes-itself (EXPERT)

may-improve-on-its-own:            # ← maps to SURFACES, not to field names (§4.3)
  - phrasing                       # S-GEN
  - examples                       # S-GEN
  - skill-notes                    # S-GEN, excluding normative clauses (§8.3a)
# - when-skills-are-used           # S-ROUTE — OFF by default; needs an OBL-8 routing replay

needs-a-person-to-approve: [tools, permissions, team, limits, evals, policy-clauses]
keep-only-if: a-person-approves-it
review: weekly
cycle-limits: {per-cycle: 4, per-month: 20 USD, evals: 2000}
models:
  execution:  {role: llm}
  reflection: {role: reflector}    # separate binding; strongest LOCALLY-SERVED model
drift:
  at-most: 50%                     # ← today the only drift field that exists
  # NEEDED (§1.6, §4.5):
  # baseline: sha256:…             # machine-advanced only, by `pact approve --baseline`
  # window: 10
  # auto-apply-ceiling-while-under: CLASS-1
```

- Every risky surface stays off by default; `loop`, `tools`, `topology` need an explicit opt-in
  *and* still hit CLASS-3/4. **That opt-in field (`may-also-change:`) does not exist yet** (§1.7).
- `learning.yaml` is itself GOVERNED, so no cycle can widen its own permissions; and
  `needs-a-person-to-approve` may only be widened relative to the builtin list, never narrowed —
  which the implementation gets right (`learning.py` unions the author's list with
  `HIGH_RISK_FIELDS`).
- The reviewer sees the plain-language `ChangeClassification`, not a YAML diff. That is what makes
  the human gate usable by D13's persona, and it is the one place where §1.3's false-positive
  message ("the wording changes a rule, not a phrasing: 'Be concise and warm…'") does visible damage.

---

## 10. Open questions

**Closed this pass.**

- **OQ-7 (does `ESC-JUDGED` interact badly with D19's on-ramps?) — resolved, and the answer is
  structural.** The eval-rule vocabulary is `must-say-one-of`, `must-contain`, `must-not-contain`,
  `must-call-before`, `judged` (`spec/schema.yaml:2332ff`) — four deterministic assertions and one
  judge. Everything semantic that a D19 plain-language rule expresses ("must cite a source", "never
  promise a refund" beyond literal strings) lands on `judged:`. `ESC-JUDGED` has a CLASS-3 floor and
  X18 ends auto-apply eligibility, so **a D14-persona workspace's gating suite will almost always
  contain a judged rule, and `applies-safe-changes-itself` is therefore unreachable for that
  persona.** This is not a bug: it is why `propose-only` is the core-tier mode. The spec should
  state it as a derived property — *auto-apply is an expert-tier feature by construction* — rather
  than leaving it emergent, so nobody builds a UI that offers the toggle.
- **OQ-3 (is CLASS-2 auto-apply worth having?) — no, given §1.10.** Three of the four measured
  classifier defects are S-ROUTE false negatives. Until OBL-8's routing-replay corpus exists,
  S-ROUTE should be CLASS-3 (human gate) unconditionally. This is strictly safer, simpler, and
  costs only human review in a mode (`propose-only`) that already requires it.
- **OQ-5 (bitemporal validity vs git) — keep both.** `gaia-ai-runtime` reads the tree natively (D2)
  and must answer *"what was active on date X"* inside an air-gapped image with no git dependency.
  §1.8 independently forces authored ledgers into the tree, so the cost of `validity.from/until` is
  marginal.

**Still open.**

1. **`θ_shrink` has no empirical anchor.** ACE gives one catastrophic case (99.3% shrink); 40% is an
   interpolation. §1.4 additionally shows the *structural* triggers do the real work and the token
   test rarely decides anything. A sweep on the bench-3 harness would tell us whether the token
   trigger should exist at all.
2. **Routing non-regression corpus size (OBL-8).** Skill Shadowing used 88 tasks × 3 library sizes =
   2,545 trajectories. The minimum viable corpus for a ten-case workspace is unknown, and it decides
   whether S-ROUTE can ever leave CLASS-3 (OQ-3's reopening condition).
3. **PoisonedSkills is cited but not read** (survey characterisation only; DOI
   10.5281/zenodo.19281322, not resolvable offline under D17). P-9's exact shape should be
   re-derived from the primary source. The *"36% of public skills carry injection"* figure asserted
   at `SYNTHESIS.md:184` remains unverified in the corpus.
4. **Multi-tenant learning under D24.** Proposal unchanged: PACT defines only the artifact contract
   (`origin`, tier namespace, re-certification requirement) and leaves the promotion mechanism to
   AgentZero. Not yet validated against `/home/bud/ditto/bud`.
5. **Contribution attribution `ĉ(s)` with multiple artifacts injected.** Ratchet's setting is one
   artifact per run. **agent-lightning is the closest prior art and it does not solve it**: rewards
   are addressed to spans and can link to other spans (`semconv.py:145-164`), but the reduction is
   `find_final_reward` = last-wins (`emitter/reward.py:307-320`). **New proposal grounded in that
   machinery:** PACT already has a per-event address (§7.13, *"one address, and everything that
   happens has one"*). Key the contribution ledger on `(artifact, injection-event-address)` rather
   than on `(artifact, run)`, and treat a run in which two artifacts were injected at the same
   address as `INAPPLICABLE` rather than crediting both. This is measurable and cheap; it is not a
   solution to credit assignment, it is an honest refusal to guess.
6. **Is the prose signal worth keeping at all?** §1.3's false positive and §1.10's false negatives
   both come from the regex. Once the surface lookup exists, the regex's only remaining job is
   catching a *semantic inversion inside an S-GEN field* (`30 days` → `300 days`). A numeric-literal
   diff and a negation-polarity diff would cover that class deterministically, and a keyword list
   would not be needed. Worth measuring before shipping a keyword list as spec data.

---

## 11. Evidence index

**Source read this pass (file:line cited above)**
`adapters/python/src/pact_adapters/learning.py` (`:41-127`, `:159-213`, `:314-390`, `:480-611`,
`:1079-1250`, `:1376-1383`) ·
`crates/pact-cli/src/main.rs` (`:305-306`, `:350-416`) ·
`crates/pact-loader/src/{teams.rs,reach.rs}` ·
`spec/schema.yaml` (`:1-120`, `:376`, `:426`, `:446`, `:887`, `:1272`, `:1406`, `:1514-1610`,
`:1649-1712`, `:1786-1800`, `:2332-2400`, `:2504-2726`) ·
`examples/refund-desk/learning.yaml` · `.gitignore:1-7` ·
`docs/20-ARCHITECTURE-DRAFT.md` §8.1–§8.11 (`:9046-10430`) ·
`docs/70-PRODUCTION-GAP-REGISTER.md:152-210` ·
`research/repos/memory/letta/{letta/server/server.py:756-800,1191-1203,
letta/groups/sleeptime_multi_agent_v4.py:120-200,
letta/prompts/system_prompts/sleeptime_v2.py:15,21,
letta/functions/function_sets/base.py:488-496,
letta/functions/function_sets/voice.py:10-21,
letta/agents/voice_sleeptime_agent.py:153-163,
letta/services/block_manager.py:842,952,1004, letta/orm/block_history.py:12-35}` ·
`research/repos/memory/cognee/{cognee/skill.md,
cognee/memify_pipelines/apply_feedback_weights.py:20-85,
cognee/tasks/memify/apply_feedback_weights.py:43-59,
cognee/tasks/memify/extract_feedback_qas.py:16-18}` ·
`research/repos/memory/reflexion/{alfworld_runs/generate_reflections.py:1-48,
alfworld_runs/alfworld_trial.py:46-50, programming_runs/reflexion.py:29-95}` ·
`research/repos/memory/{mem0/mem0/memory/main.py:900-912,
expel/prompts/templates/human.py:20-34, voyager/voyager/agents/skill.py:95-102}` ·
`research/repos/optim/agent-lightning/{agentlightning/semconv.py:90-164,
agentlightning/emitter/reward.py:295-320}` ·
`research/repos/config/cue/internal/core/subsume/{subsume.go:15-134,vertex.go:58-202}`

**Measurements executed this pass**
Classifier fixture run (20 rows, §1.10) · `HIGH_RISK_PROSE` false-positive isolation (§1.3) ·
`ESC-SHRINK` list-trigger behaviour on edit vs add vs delete (§1.4) · drift-metric behaviour on
inversion / deletion / additive churn, and the 16-edit trip point (§1.5) · schema parse for surface
distribution, group field lists, and the 18 `description` fields (§1.1, §1.2, §1.6, §1.7) ·
repo-wide grep for surface consumers, topology operators, and `block_manager` checkpoint callers.

**Papers (carried from R1; text extracts via `pdftotext -layout`)**
ACE 2510.04618 · ReasoningBank 2509.25140 · SkillWeaver 2504.07079 · DGM 2505.22954 ·
ADAS 2408.08435 · Self-Evolving Survey 2508.07407 · MAST 2503.13657 · One-Token-Fool 2507.08794 ·
AWM 2409.07429 · Library-Drift/Ratchet 2605.19576 · Skill Shadowing 2605.24050 ·
Meta-Agent Inefficiencies 2510.06711 · SkillOps 2605.13716 (App. G) ·
Agent Skills Survey 2605.07358 (§VI-F) · MetaSkill-Evolve 2607.05297 · HiSME 2605.28390 ·
MASS 2502.02533 · GEPA 2507.19457

**In-repo priors extended** `SYNTHESIS.md` F1/F3/F4/F6 · `RESULTS.md` benches 1–3 ·
`PROMPT-SKILL-LEARNING.md` §1–§5 · `docs/20-ARCHITECTURE-DRAFT.md` §8
