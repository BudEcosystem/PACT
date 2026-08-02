# Gap R1-2 — The signed optimisation bundle (RES-7b)

**Date:** 2026-07-26. **Status:** gap closed to a normative spec, with four named residuals.
**Applied to:** `docs/20-ARCHITECTURE-DRAFT.md` — §0.0 (X30), §4.4 (RES-7b restated as
stage-and-report), §4.4a item 7, §8.9 (cross-ref), §8.10 (citations), **new §8.11**
(BND-1..BND-9, IMP-1..IMP-10), §10 air-gap trap (vii), §13.9b (cross-ref), **new §13.14**
(four residuals), §14.2 (vocabulary arithmetic), §15 glossary (`BND-`, `IMP-`).

---

## 0. The gap, restated precisely

R3 specifies RES-7b as one line:

> `RES-7b IMPORT: if a signed optimisation bundle exists whose 'optimised-for' matches the
> candidate and whose 'producer.model' is stronger than any locally-available reflector,
> apply it and re-verify.` *(`20-ARCHITECTURE-DRAFT.md:1616-1620`)*

and §13.9b made it load-bearing: *"the **only** air-gap-compatible mechanism the evidence
supports"*. The format is specified only by the two fields it consumes — `producer.model`
and `optimised-for` (§8.9).

> **Cross-stream correction, applied here.** While this pass ran, gap R1-1 **withdrew**
> §13.9b's "measured negative" finding: SkillOpt Table 5's target-matched-optimizer arm is
> positive in 4/4 cells (+2.4 to +14.1 pp, recovering 56–74%), and SkillOpt Table 4(a) —
> R3's evidence for import — is 4 rows of which **local re-optimisation wins 3, by up to
> 16.0 pp**. So bundle import is a **fallback whose real property is that it is never below
> the target's no-skill baseline**, not a superior path, and *not* the only mechanism.
> **This makes the gap more urgent, not less.** A mechanism whose upside is now known to be
> modest cannot be allowed to carry an unbounded downside, and every failure mode in §2
> below is a way for an import to be *worse* than doing nothing. The spec below is
> unchanged by the correction except for BND-8, which was drafted as a
> producer-must-be-stronger **gate** and is now a **report**.

Three sub-questions had no answer:

- **Q1 — what is *in* a bundle?**
- **Q2 — a bundle was produced against contract-digest `A`; the importing workspace is at
  contract-digest `B`. When is it applicable?** (`A = B` is neither necessary nor
  sufficient — proven in §3 below.)
- **Q3 — what re-verification is mandatory on import?**

**Result of this pass:** all three are answerable from the corpus, and the answer is
*smaller* than it looks — a bundle is a signed, digest-anchored envelope around **one
Variant plus the LEARNABLE artifacts it references**, and every applicability and
governance rule it needs already exists in the draft (§2.4b, §8.3 `ESC-UNTRUSTED`, §6.9-D,
§6.6 QUARANTINE). What was genuinely missing was **the anchoring set** (which digests, at
what granularity) and **the fact that RES-7b as written contradicts §8.3** — an imported
bundle always fires `ESC-UNTRUSTED` → CLASS-4 → human gate, so the resolver may never
"apply it" mid-resolve.

---

## 1. What shipping optimisation artifacts actually contain

Read from source, not docs. Five artifacts, all in the corpus except the last.

| System | Artifact | Payload | Bound to source program? | Signed? | Applicability check on load |
|---|---|---|---|---|---|
| **DSPy** state | `*.json` / `*.pkl` | `{param-name → {demos, traces, train, signature{instructions, fields[{prefix,description}]}, lm{model,…}}}` + `metadata.dependency_versions` | **No.** No digest of the program anywhere | **No** | name lookup + version **warning** |
| **DSPy** program | dir: `program.pkl` + `metadata.json` | cloudpickle of the whole module | No | No | `allow_pickle=True` required; version **warning** |
| **GEPA** | `GEPAResult.to_dict()` | `candidates: list[dict[str,str]]`, `parents`, `val_aggregate_scores`, `val_subscores`, Pareto fronts, `discovery_eval_counts`, `seed`, `run_dir` | **No.** Not even the seed candidate's digest | No | `validation_schema_version` ≤ 2 only |
| **Letta `.af`** | one JSON | agents, blocks, tools (**incl. `source_code`**), MCP servers, skills (`files: path→content`), `metadata: Dict[str,str]` | No | **No** — zero `sha256`/`signature`/`verify` in the serialisation manager | none |
| **vLLM LoRA** | `adapter_config.json` + weights | rank, alpha, `target_modules`, `base_model_name_or_path` | **Yes** — by *name string* | No | 3-tier: identity, structural, host-capability |
| **PAM** (arXiv 2605.11032, web) | envelope + component DAG | `pam_version`, `source_agent{name,model_family,runtime}`, `root_hash` (BLAKE3), `signature` (Ed25519), `capability_tokens`, five component types, per-entry content-addressed `id` + `parent_ids` | **Partially** — records `source_agent`, never checks it | **Yes** | **none** |

### Citations

- DSPy save/load: `research/repos/optim/dspy/dspy/primitives/base_module.py:171-252` (save),
  `:254-292` (load), `dspy/utils/saving.py:15-61` (program mode).
- DSPy version mismatch is a `logger.warning`, never an error:
  `base_module.py:284-291`; `saving.py:51-58`.
- DSPy state application iterates the **receiving** module's parameters —
  `for name, param in module.named_parameters(): param.load_state(state[name])`
  (`base_module.py:162-167`) — so a missing name raises `KeyError` and an **extra** state
  entry is silently dropped.
- GEPA result: `research/repos/optim/gepa/src/gepa/core/result.py:40-62` (fields),
  `:121-148` (`to_dict`), `:150-162` (`from_dict` — the only check is a schema-version
  ceiling).
- Letta: `research/repos/memory/letta/letta/schemas/agent_file.py:431-446`
  (`AgentFileSchema` — no signature field, `metadata: Dict[str,str]` free-form),
  `:358-367` (`ToolSchema(Tool)`), `letta/schemas/tool.py:46` (`source_code`),
  `agent_file.py:426-428` (`strip_env_from_stdio_config` removes **only** `env`;
  `command`/`args` survive), `:370-398` (`SkillSchema.files: path→content`, validated only
  for the presence of a `SKILL.md` key — no path confinement).
  `grep -n "signature|verify|sha256|digest" letta/services/agent_serialization_manager.py`
  → **zero matches**.
- vLLM: `research/repos/routing/vllm/vllm/plugins/lora_resolvers/filesystem_resolver.py:30-45`;
  `vllm/lora/peft_helper.py:62-80` (structural), `:118-132` (`validate_legal` — host
  capability).
- PAM: <https://arxiv.org/html/2605.11032v1> §3.2, §4.5, Appendix A, Table 3.

### The three findings that matter

**(a) Nobody binds the artifact to the program it was optimised against.** DSPy and GEPA
record *zero* identity of the source program. PAM records `source_agent.model_family` and
never validates it. Only vLLM checks — and by **string equality on a model name**
(`adapter_config["base_model_name_or_path"] == base_model_name`,
`filesystem_resolver.py:36-38`), which any repo rename defeats, and on mismatch it returns
`None` — a **silent skip**, not a diagnostic. *(Aside, verified: the same function derives
its adapter id as `abs(hash(lora_name))`, `:39-41` — Python's string hash is
per-process-randomised unless `PYTHONHASHSEED` is fixed, so the id is not stable across
restarts. Identity must be a digest, never a hash of a name.)*

**(b) The most credible external design — the one that does everything else right — has
exactly the hole RES-7b needs filled.** PAM ships Ed25519 signing, a BLAKE3 content-
addressed DAG, three-phase import verification (recompute every entry id; check DAG
acyclicity and referential integrity; verify the root signature) and measured transfer
results (0.84–0.88 mean continuity vs 0.35 no-memory baseline, N=50, authors' own caveat:
*"directional rather than definitive"*). And its re-hydration pipeline is
*Verify → Filter → Rank → Compress → Format → Frame → Inject* with **no compatibility
stage at all** — `model_family` is recorded but never checked, and there is no rejection
criterion. It also has no replay detection, no quarantine and no offline revocation.
**So the envelope problem is solved prior art; the applicability problem is not solved
anywhere.** That is the actual content of this gap.

**(c) Two shipped systems demonstrate the exact failure modes to design against**, below.

---

## 2. Four failure modes, each derived from a verified defect

### FM-1 — Positional mis-application (DSPy, verified)

`Signature.dump_state` writes, per field, **only** `{prefix, description}` — the field
*names are not serialised* (`dspy/signatures/signature.py:524-534`). `Signature.load_state`
then applies them by position with `strict=False`:

```python
for field, saved_field in zip(signature_copy.fields.values(), state["fields"], strict=False):
    field.json_schema_extra["prefix"] = saved_field["prefix"]
    field.json_schema_extra["desc"]   = saved_field["description"]
```
`signature.py:537-545`

A state file produced against a 3-field signature, loaded into a 5-field signature,
**silently** assigns the first three descriptions positionally and leaves two untouched.
No error, no warning. This is precisely "a bundle produced against contract A applied to
contract B", and it is the strongest single argument in the corpus for **per-component
pre-image digests**: an optimisation delta must be applied as a 3-way merge against a known
base, and a base-digest mismatch must **refuse the component**, never fall back to
position or to overwrite.

### FM-2 — The artifact rewrites the contract and the substrate

`Predict.load_state` does `setattr(self, name, value)` for every state key outside a
three-item exclusion list (`dspy/predict/predict.py:102-106`) — arbitrary attribute
assignment from an untrusted file. It then replaces the **signature** (the I/O contract)
wholesale, and reconstructs the LM from `state["lm"]`. `BaseLM.dump_state` includes
`"model": self.model` (`dspy/clients/base_lm.py:678-685`), and `model` is **not** in
`UNSAFE_LM_STATE_KEYS = {"api_base", "base_url", "model_list"}` (`predict.py:21`).

Consequence, on the *default* path (`.json`, `allow_pickle=False`,
`allow_unsafe_lm_state=False`): **an imported optimisation artifact silently rebinds the
model.** The endpoint keys are stripped with a `logger.warning` (`predict.py:24-39`), the
model id is not. In PACT terms the artifact moves `π_substrate` and `π_contract` — the two
projections a bundle must never touch (§2.2, `:741-753`).

### FM-3 — Verdict laundering and held-out leakage

A bundle arrives carrying `answer-relevancy 0.83`. Three independent reasons that number
cannot be the importer's verdict:

1. **Different suite.** The producer's `evals/suite.yaml` is a different document; §4.6's
   `verdict.eval-suite` is digest-pinned for exactly this reason (`:1820`).
2. **Different judge.** §6.9 rule 1 makes a threshold above the judge's measured agreement
   arithmetic nonsense (`:3211-3216`); the producer's judge binding and `agreement-n` are
   not the importer's.
3. **Leakage.** The producer optimised on *its* train/validation split. If any of those
   cases is also in the importer's `held-out` split (common — both may derive from a shared
   template corpus, a vendor starter pack, or the same public dataset), the importer's
   re-verification is contaminated and §6.9's interval is fiction. GEPA's result carries
   `val_subscores: list[dict[DataId, float]]` (`result.py:44`) — per-instance ids — so the
   information needed to detect this exists in the optimiser's own output and is simply
   never exported anywhere.

**And a fourth, which is new and is the sharpest:** §6.9-D makes the held-out set a
depleting resource with a **cumulative** multiplicity adjustment over an append-only query
ledger, and a hard budget of 200 candidate-evaluations per held-out case (`:3314-3330`).
Nothing in RES-7b counted bundle imports as candidates. **Bundle-shopping** — import 40
bundles, re-verify each, keep the one that passes — is best-of-40 selection on the held-out
set, and under the existing rules it would have been invisible.

### FM-4 — The bundle is executable

Verified for Letta (§1 citations): `.af` carries tool `source_code` and un-stripped MCP
`command`/`args`, plus a `path → content` file map with no path confinement. §8.10 already
states the rule — *"PACT's importer treats any imported bundle as untrusted code until
signed and re-certified"* (`:4584-4588`) — but there was no bundle format for it to apply
to, so it was unenforceable.

---

## 3. Why `contract-digest` equality is the wrong applicability test

`contract-digest(D) = sha256(canonical-string(π_contract(D)))` (§3.3, `:1099`), and §2.2
proves it is stable under strategy edits (`:773-775`). It is the obvious anchor. It is also
wrong on both sides.

**Too strict.** `π_contract` contains identity, `accepts`, `answers-with`, `run-inputs`,
`needs`, `limits`, `policy`, `evals`, autonomy (`:751`). Raising an SLO band, adding a
policy rule, bumping `version`, or adding one eval case all move `contract-digest` while
leaving the bundle's optimisation exactly as valid as before. Under strict equality a
bundle expires on the first unrelated contract edit — which, given that D11 makes the
resolver a recommender run on every catalogue refresh, is roughly weekly. A mechanism whose
measured value is already only "a safe fallback" cannot additionally have a one-week
half-life and remain worth specifying.

**Too loose.** `contract-digest` says nothing about `π_strategy`. Two workspaces can share
a contract digest exactly and have completely different instruction section anchors,
different skill files, and a different `uses:` set. Applying a bundle addressed to
`instructions#how-to-work` when that anchor no longer exists is FM-1 with extra steps.
§8.8 already fixes the addressing model — SAMMO-shaped selectors over **named Markdown
sections** (`## Tool policy {#tool-policy}`), `:4438-4443` — and named anchors are exactly
what can silently disappear (`ESC-SHRINK` already treats anchor deletion as a trigger,
`:3957`).

**The resolution, and it is already in the document's own vocabulary.** Digests are a
**Merkle tree** (§3.3, `:1093-1108`), so sub-digests are free. Applicability is decided on
**two disjoint digest sets at different granularities**:

- **Applicability set** — a subset of `π_contract` sub-digests naming what the optimisation
  actually *depended on*. Not the root.
- **Anchor set** — one **pre-image digest per component**, so application is a 3-way merge
  with a known base rather than an overwrite.

This is exactly in-toto's shape: `subject` is an **array** of ResourceDescriptors, each
independently digest-matched, and the spec is explicit that *"the field that consumers are
expected to match the digest against is ultimately determined by the predicate type"*
(`research/repos/protocols/in-toto-attestation/spec/v1/resource_descriptor.md`, Semantics;
`statement.md` `subject`). And OCI's `subject` is deliberately *"a **weak** association to a
separate Merkle DAG"* (`oci-image-spec/manifest.md:100-103`) — the referred artifact never
knows about its referrers. Same here: a bundle points at a contract; a contract never points
at bundles, so nothing in the workspace changes when a bundle exists.

---

## 4. Envelope prior art worth adopting verbatim

| Rule | Source | Why it transfers |
|---|---|---|
| Sign `PAE(payloadType, payload)` over **raw bytes**; *"SHOULD avoid depending on canonicalization for security"* | in-toto `spec/v1/envelope.md` (DSSE/ITE-5 requirements) | PACT digests are computed over RFC-8785 canonical form (§3.2). A signature that re-canonicalises before verifying inherits every canonicaliser bug as a forgery. Sign the bytes; use the canonical digest as the *anchor value inside* the signed payload. |
| Envelope MUST support **multiple signatures**, each with a `keyid` | in-toto `envelope.md`; noted there that Sigstore Bundle is non-compliant because it allows only one | §8.10 has four key roles (learning-service, approver, engineer, publisher). Producer-signature and approver-co-signature must coexist in one envelope. |
| A multi-attestation bundle **is not authenticated as a whole**; *"an attacker might be able to delete valid attestations, replay obsolete attestations, and/or inject… without being detected"* | in-toto `spec/v1/bundle.md` | **Do not copy JSON-Lines bundling.** A PACT optimisation bundle MUST be sealed by one signature over a Merkle root covering the complete component set, or a stripped component (e.g. dropping the one that made the diff CLASS-4) is undetectable. |
| **Monotonic principle** — ignoring an attestation or field must never turn DENY into ALLOW; prefer *"deny unless a 'no vulnerabilities' attestation exists"* | in-toto `spec/v1/README.md` (Parsing rules) | Makes "consumers MUST ignore unrecognized fields" safe. A bundle's unknown `x-` fields may be ignored; a bundle's *absence* of an expected field must fail closed. This is the same shape as `BR-UNKNOWN`/CLASS-4 (§8.3, `:3949-3950`). |
| Verifier identity + **policies used** + `timeCreated`, with time-bounded properties expressed as named properties rather than expiry fields | in-toto `spec/predicates/svr.md` | The producer-side verdict must name *which* verifier and *which* suite produced it. SVR explicitly *"does not include information for reproducing the verification result"* — which is why PACT cannot accept a producer verdict as a verdict (FM-3). |
| Signature as a **referrer** keyed to the record digest, not embedded in the record | `agntcy-dir/proto/agntcy/dir/sign/v1/signature.proto:17-40` (+ OCI referrers) | Lets a bundle be co-signed by an importing org's approver without changing the bundle's own digest. |
| Three-phase import: recompute every content-address; check DAG integrity; verify root signature. Halt on first failure. | PAM §3.2 | Directly adoptable as IMP-1..IMP-3. |
| Three-tier LoRA load: identity → structural (unknown fields filtered, required fields enforced) → **host capability** (`validate_legal` raises on DoRA / `modules_to_save` / rank > max) | `vllm/lora/peft_helper.py:62-80, 118-132` | The host-capability tier is the one PACT's capability lattice (§5.7) makes cheap and that nothing else in the corpus has. A bundle that depends on grammar-constrained decoding is inapplicable on a substrate whose lattice says `unsupported` — checkable before any eval is run. |
| 13-gram overlap as the contamination criterion (OpenAI GPT-3 App. C; harness uses n=13 uniformly) | `lm-evaluation-harness/docs/decontamination.md`; `lm_eval/decontamination/janitor.py:42-46, 111-160` | Gives an **offline, content-free** leakage check: the bundle publishes salted 13-gram digests of its train+validation cases; the importer intersects with its own held-out cases. Neither side reveals case text. |

---

## 5. The spec (as applied to §8.11)

Summarised here; normative text lives in `20-ARCHITECTURE-DRAFT.md` §8.11.

**A bundle is not a new document kind.** It is a sealed envelope around **one Variant plus
the LEARNABLE artifacts that variant references**. That choice does the majority of the
work for free:

- §2.4b.2 already makes contract fields (`policy`, `limits`, `needs`, `evals`,
  `answers-with`, `accepts`, `run-inputs`, `model`, `models`) a **validation error inside a
  variant** (`:890-893`). FM-2 becomes structurally impossible rather than a review item.
- §2.4b.5 already refuses to bind a variant with `producer.kind: optimizer` and no approval
  signature (`:903-904`). FM-4's "untrusted until signed" becomes enforceable.
- §8.3 `ESC-UNTRUSTED` already fires CLASS-4 on *"evidence whose `origin.workspace-digest`
  differs from the workspace being optimised"* (`:3963`). An imported bundle **always**
  differs, so a human gate is already mandatory — see §6 below, because this contradicts
  RES-7b as written.
- The vocabulary count (§14.2, D28 failure mode #1) grows by a manifest schema and two rule
  series, not by a document kind.

`bundle.yaml` carries seven blocks: `producer`, `optimised-for`, `applies-to`
(`contract-atoms` + per-component `base` pre-image digests), `components` (in-toto
ResourceDescriptor shape: `name`, `op`, `surface`, `path`, `media-type`, `digest`, `size`),
`declared-class` (a **claim**, re-derived by the core per §8.3), `evidence` (producer
scores, `cases`/`runs` as two fields per §4.6, `candidates-evaluated`, `split-sketch`,
baseline delta), and `x-`.

**Applicability (BND-4..BND-9)** is a conjunction over the six contract atoms
(`accepts`, `answers-with`, `needs`, `policy`, `tool-surface`, `eval-suite`), with
`eval-suite` mismatch **downgrading the evidence** rather than rejecting the bundle, plus
per-component base-digest equality, plus a lattice check on `requires-capabilities`, plus a
digest (not name) comparison on the target executor, plus a **reported** — not gating —
reflector-strength comparison.

**Import (IMP-1..IMP-10)** is: integrity → signature → policy → applicability → leakage →
quarantine → class re-derivation → human approval → re-verification (counted against the
held-out ledger) → lock.

---

## 6. Two contradictions in R3 that this gap exposed

**(1) RES-7b cannot "apply" anything.** As written it says *"apply it and re-verify"*
inside the resolution algorithm (`:1616-1620`). But an imported bundle's evidence always
carries a foreign `origin.workspace-digest`, so `ESC-UNTRUSTED` fires → CLASS-4 → human
approval (§8.3 `:3963`, §8.10 `:4571-4579`). And §2.4b.5 refuses to *bind* the resulting
variant without an approval signature. So `pact resolve` — a non-interactive command that
runs in CI — cannot legally apply a bundle. §4.4a's own recommendation text already gets
this right (*"instead: `pact import-bundle <…>`"*, `:1654`); only the algorithm step was
wrong.

**Fix applied:** RES-7b **stages and reports**, never applies. It is a discovery step whose
output is a line in the Portability Report and a QUARANTINE materialisation; `pact
import-bundle` + an approver signature is the only path to a bindable variant.

**(2) The held-out ledger did not count bundles.** §6.9-D's multiplicity is cumulative over
`(resolve-id, candidate count, timestamp, split digest)` (`:3325-3330`); a bundle
re-verification is a candidate evaluation and was uncounted. **Fix applied:** IMP-9 records
each re-verified bundle as a candidate, and the *producer's* own
`evidence.candidates-evaluated` is added to the importer's multiplicity whenever the
producer's split sketch overlaps the importer's gating corpus — otherwise a workspace
launders 46 producer-side candidates into a "clean" single import.

---

## 7. Residual uncertainty (honest)

**RU-1 — No measurement exists for bundle transfer in PACT's setting.** The only quantified
transfer result in reach is PAM's Table 3 (0.84–0.88 mean continuity, N=50, memory transfer
across model families, authors' own caveat: *"directional rather than definitive"*), which
is a different artifact class (memory, not strategy). SkillOpt Table 4(a) — the one direct
measurement — is **4 cells, and import loses 3 of them by up to 16.0 pp**. The design is
therefore correct-by-construction and **unvalidated by effect size**; nothing in the corpus
establishes what fraction of *applicable* bundles pass IMP-9.

**RU-2 — The applicability set is a judgement, and it can be wrong in the unsafe direction.**
Choosing six contract atoms rather than the whole `π_contract` root trades staleness for
soundness. If an optimisation depended on a contract field *not* in the atom set — most
plausibly `limits` (a latency band that shaped how verbose the optimised instructions
became) or `run-inputs` (a field the optimiser learned to cite) — the bundle will be
declared applicable when it is not. IMP-9's mandatory re-verification is the only backstop,
and re-verification has finite power (§10's `ε = 0.10 at n ≥ 158`, `:4909`). **Falsifier:**
build a fixture whose optimisation depends on `limits` only, mutate `limits`, and check
whether re-verification catches it at the workspace's actual case count. If it does not,
`limits` joins the atom set.

**RU-3 — Salted 13-gram sketches detect duplication and near-duplication, not paraphrase.**
A producer whose validation set was *generated from the same source scenario* as the
importer's held-out set will not overlap at 13 grams and will still leak. There is no
offline paraphrase-level contamination detector in the corpus, and the harness's own method
is exactly the n-gram one (`decontamination.md`, "OpenAI defined a test document as
contaminated if any N-gram overlap existed"). The honest position: the leakage check is a
**floor**, the held-out query ledger is the real defence, and a bundle from an unknown
producer should be treated as consuming held-out budget generously rather than exactly.

**RU-4 (smaller) — offline revocation.** §8.10 specifies `.pact-keys/` plus an in-tree
revocation list (`:4579`). Under D17 an air-gapped workspace's revocation list is as stale
as its last sneakernet update, so a compromised producer key stays valid locally for
exactly that long. PAM has the same hole and does not name it; this note names it. The
mitigation available without a network is `validity.until` on the producer's signature
(§8.9 already carries `validity`), i.e. **short-lived producer signatures over long-lived
bundles**, re-signed at each distribution refresh. Not yet specified; flagged in §13.14.
