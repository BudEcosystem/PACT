# Research stream: `bud-integration`

**Question:** PACT replaces `bud.dev/v1` (D3). What exactly does that require?

**Date:** 2026-07-26.
**Method:** read the Rust source in `/home/bud/ditto/gaia-ai-runtime/bud-agentic-runtime/`
first, design docs second. Where the docs and the source disagree, **the source wins
and the disagreement is recorded as a finding**. Every claim below carries a
`file:line`. Anything I did not read in source is marked `INFERRED`.

**Files read in source (not summaries):**
`src/lib.rs` (15 593 lines), `src/manifest_compiler.rs` (3 702),
`src/declarative_normalization.rs` (6 381), `src/eval.rs` (2 139),
`src/policy_runtime.rs` (2 948), `src/portability.rs` (2 879),
`src/registry.rs` (2 584), `src/registry_sources.rs` (5 761),
`src/run_planning.rs` (6 619), `src/agent_package.rs` (585),
`src/package_trust.rs`, `src/event_subscription.rs` (6 831),
`src/sdk_codegen.rs` (schema bundle), `src/goose_adapter.rs` (44 561, targeted),
`src/bin/bud.rs` (targeted), `crates/bud-agent-types/src/lib.rs` (1 446).
**Docs read:** `sdk-and-declarative-dev.md`, `registry-and-portability.md`,
`runtime-gap-analysis.md`, `architecture.md` (targeted),
`server-control-plane-and-execution.md`, `scoped-agent-memory.md`,
`durable-agent-mailboxes.md`, `research/SYNTHESIS.md`.

---

## 0. Headline results

1. **`bud.dev/v1` is a five-kind family, not one kind.** `Agent`, `Team`,
   `Workflow`, `Schedule`, `EventSubscription` share `apiVersion: bud.dev/v1`;
   `Eval` is a sixth manifest kind with its own `apiVersion` handling. PACT's
   superset obligation is over **six** manifests, plus one non-manifest authoring
   type (`AgentBlueprint`) and one Goose-source projection kind
   (`UniversalGooseAgent`).
2. **The `Eval` manifest kind already exists** and is fully implemented
   (`src/eval.rs:16-165`, CLI at `src/bin/bud.rs:480`). The thesis §7.5 claim that
   it is "the missing `Eval` manifest kind named in the in-repo gap analysis" is
   **wrong on both halves**: the gap analysis never names it
   (`runtime-gap-analysis.md` mentions "eval" only twice, both as *recovery* and
   *evaluator-optimizer*, lines 105 and 108), and it is implemented. PACT must be a
   **superset of an existing eval kind**, not a filler of a hole.
3. **`spec.permissions` is (almost entirely) decorative.** The only behaviour it
   drives is `mode: chat` → `GooseMode::Chat`
   (`src/goose_adapter.rs:34386-34395`). The documented vocabulary
   `ask | readonly | accept_edits | deny_unapproved | bypass`
   (`sdk-and-declarative-dev.md:2128`) is **not enforced**. Real enforcement lives
   in `spec.tools.autoApprove / requireApproval / deny` via the `bud_tool_policy`
   inspector (`src/goose_adapter.rs:33990-34019`).
4. **`bud.dev/v1` cannot express modality at all.** There is no `spec.input`;
   run input is always `kind: "text"` (`src/lib.rs:8349-8353`, every construction
   site hardcodes `"text"`), and every A2A projection hardcodes
   `["text/plain","application/json"]`
   (`src/manifest_compiler.rs:3677`, `src/portability.rs:2051`,
   `src/agent_registry_card.rs:204`). D16 (all four modalities in v1) is a pure
   addition with no bud.dev/v1 antecedent.
5. **A local Bud agent cannot be run without a build step today.** Run planning
   hard-fails if `recipes/<name>.goose.yaml` is absent from the package directory
   (`src/run_planning.rs:2447-2473`). D2 ("no build artifact may be required to
   run") is *violated by the current registry-backed run path* and *satisfied by*
   the in-process path `BudUniversalAgentRuntime::create_agent(manifest, dir)`
   (`src/goose_adapter.rs:9970-9983`), which takes a manifest struct and never
   touches a recipe file. **PACT's native-execution contract must be built on the
   second path and the first must be re-plumbed.**
6. **`bud.dev/v1` has no extension mechanism.** Unknown fields are rejected at
   root, `metadata`, and `spec` (`src/manifest_compiler.rs:49-67`, called at
   `:141`, `:152`, `:158`). `x-bud` exists **only** inside OSSA export/import
   (`src/portability.rs:1108-1114`). PACT's `x-` namespace (O1.4) has no
   forward-compatible landing zone in the current format — every PACT field added
   to a bud manifest is a hard validation error on the old binary.
7. **`bud.dev/v1` Agent has no version and no namespace.** `AgentMetadata` is
   `{name, description, displayName, aliases}` only (`src/lib.rs:3652-3660`).
   Version/namespace/revision live exclusively in the registry release catalogue
   (`crates/bud-agent-types/src/lib.rs:960-966`), and both exporters hardcode
   `"version": "1.0.0"` (`src/manifest_compiler.rs:3435`, `:3667`).
8. **The gap analysis (2026-07-19) is stale in PACT's favour.** It says declarative
   guardrails are "only contains/regex" and there is "no general run cost budget"
   (`runtime-gap-analysis.md:110`). The tree now has 8 guardrail stages
   (`src/lib.rs:3782-3799`), 3 evaluator kinds
   (`src/declarative_normalization.rs:4411`), and a 7-dimension
   `AgentBudgetPolicy` (`src/policy_runtime.rs:753-782`). Do not design PACT
   against the stale list.

---

## 1. COMPLETE FIELD INVENTORY OF `bud.dev/v1`

### 1.0 Kind census (what exists, authoritative)

| Kind | Rust type | Normalizer | Strictness | Notes |
|---|---|---|---|---|
| `Agent` | `BudAgentManifest` `src/lib.rs:3644` | `normalize_agent_manifest` `src/manifest_compiler.rs:126` | rejects unknown at root/metadata/spec (`:141`,`:152`,`:158`) | the only kind `normalize_agent_manifest` accepts (`:144`) |
| `Team` | `BudTeamManifest` `src/lib.rs:4430` | `normalize_team_manifest` `src/manifest_compiler.rs:438` | rejects unknown (`:452`,`:463`,`:469`) | 11 strategies |
| `Workflow` | `BudWorkflowManifest` `src/lib.rs:4475` | `normalize_workflow_manifest` `src/manifest_compiler.rs:285` | rejects unknown (`:311`,`:322`,`:328`) | 4 strategies, 5 node kinds |
| `Schedule` | `BudScheduleManifest` `src/lib.rs:4952` | `normalize_schedule_manifest` `src/manifest_compiler.rs:1418` | kind-checked `:1424` | cron → Goose 6-field |
| `Eval` | `BudEvalManifest` `src/eval.rs:16` | `normalize_eval_manifest` `src/eval.rs:327` | `#[serde(deny_unknown_fields)]` on every struct | 8 graders, all deterministic |
| `EventSubscription` | `BudEventSubscriptionManifest` `src/event_subscription.rs:40` | `normalize_event_subscription_manifest` `:685` | allow-list `:691-713` | CloudEvents-shaped filter |
| `UniversalGooseAgent` | — (Goose markdown frontmatter `bud.kind`) | `import_bud_universal_goose_agent_source` `src/manifest_compiler.rs:2063` | — | round-trip projection of `Agent` |
| `AgentRecord` | `BudAgentRecord` `crates/bud-agent-types/src/lib.rs:679` | — | `apiVersion: bud.dev/agent-record/v1` (`:5`) | registry wire contract, **not** an authoring manifest |
| *(doc only)* `Channel` | — | **none** | — | `sdk-and-declarative-dev.md:2564` shows `kind: Channel`; **no normalizer exists**. Channels are registry descriptors only (`src/lib.rs:5781-5787`). **Negative finding.** |

`BUD_API_VERSION = "bud.dev/v1"` — `src/lib.rs:51`.
Related versioned contracts that PACT inherits: `bud.dev/sdk-schema-bundle/v1`
(`:52`), `bud.loop.v1` (`:53`), `bud.dev/agent-record/v1`, `bud.dev/agent-access/v1`
(`crates/bud-agent-types/src/lib.rs:5,7`), `bud.dev/eval-report/v1`
(`src/eval.rs:3`), `bud.dev/memory/v1` (`scoped-agent-memory.md:3`),
`bud.dev/registry-access-adoption/v1` (`registry-and-portability.md:733`).

---

### 1.1 `kind: Agent` — complete field table

Source of truth: `AgentSpec` (`src/lib.rs:3663-3680`) + the accepted-field
allow-list `AGENT_SPEC_FIELDS` (`src/manifest_compiler.rs:8-31`) + the generated
JSON schema (`src/sdk_codegen.rs:11034-11083`).

Note: every `spec.*` field is **also** accepted at manifest root as a shorthand
(`src/manifest_compiler.rs:140`, `root_fields.extend_from_slice(AGENT_SPEC_FIELDS)`),
and `metadata.*` fields likewise (`:130-139`). PACT must decide whether to keep
this dual-placement.

#### 1.1.1 Envelope

| Field | Req | Semantics (verified) | Evidence | PACT home |
|---|---|---|---|---|
| `apiVersion` | defaulted | `"bud.dev/v1"`; schema pins it as `const` | `src/lib.rs:51`, `sdk_codegen.rs:11040` | `apiVersion: pact.dev/v1`; converter rewrites |
| `kind` | defaulted `"Agent"` | only `"Agent"` accepted | `manifest_compiler.rs:143-148` | `kind: Agent` (Contract) |

#### 1.1.2 `metadata`

| Field | Req | Semantics (verified) | Evidence | PACT home |
|---|---|---|---|---|
| `metadata.name` | **required** | slugified to `[a-z0-9-]+`, ≤80 chars, no `/` or `\`; collapse-runs of `-` | `runtime_validation.rs:1405-1441` | `metadata.name` — **PACT must relax to allow namespace or add `metadata.namespace`** |
| `metadata.description` | optional | defaults to `"Bud agent {name}."` | `manifest_compiler.rs:177-182` | `metadata.description` |
| `metadata.displayName` | optional | falls back to the pre-slug raw name when it differs | `manifest_compiler.rs:167-175` | `metadata.displayName` |
| `metadata.aliases` | optional | string or list; ≤128 entries, ≤256 bytes each, no control chars, deduped; **must not** be given twice (metadata + root) | `manifest_compiler.rs:69-124`, consts `:3-4` | `metadata.aliases` |
| *(absent)* `metadata.version` | — | **does not exist**; OSSA/A2A export hardcode `1.0.0` | `manifest_compiler.rs:3435`, `:3667` | **PACT MUST ADD** `metadata.version` (semver), bound to the registry release coordinate |
| *(absent)* `metadata.namespace` | — | **does not exist**; namespacing is registry-side only (`bud:`/`goose/`/`a2a:` prefixes) | `registry_sources.rs:420`, `registry-and-portability.md:56-66` | **PACT MUST ADD** `metadata.namespace` |
| *(absent)* `metadata.owner`, `labels`, `license` | — | present in the *design* `AgentRecord` sketch (`registry-and-portability.md:548-553`, `:1274-1283`) but **not in the manifest** | — | PACT `metadata.owner` / `metadata.labels` (Contract, governance) |

#### 1.1.3 `spec` — the 11 canonical fields

| Field | Req | Semantics (verified) | Evidence | PACT home |
|---|---|---|---|---|
| `spec.instructions` | **required** | free text; rejected if it contains Unicode Tags Block chars (hidden-prompt guard) | `manifest_compiler.rs:186-191`; `sdk-and-declarative-dev.md:1049-1051` | Strategy → `instructions` (file or `instructions.md`) |
| `spec.model` | defaulted `"default"` | string **or** mapping requiring `provider` + `name`\|`model`. Canonical keys after normalisation: `provider`, `name`, `thinking_effort`, `max_tokens`, `request_params`, plus arbitrary passthrough (the whole input object is cloned). `modelSettings` is an *authoring alias* that is **erased** into those canonical keys. | `declarative_normalization.rs:3041-3097` | Split: **Contract** gets capability predicates; **Strategy** gets `model:` binding; `pact.lock` gets the resolved pin |
| `spec.tools` | defaulted empty | `ToolPolicy` (see 1.1.4) | `lib.rs:3709-3739`, `declarative_normalization.rs:3099-3168` | Strategy → `tools` + Policy → approval matrix |
| `spec.skills` | defaulted empty | `SkillPolicy { use[], define[] }` (see 1.1.5) | `lib.rs:3750-3756`, `declarative_normalization.rs:3406-3446` | Resources → `skills/` |
| `spec.capabilities` | optional | `[{name, description, tags[]}]`; strings accepted as shorthand; duplicates merged | `lib.rs:3758-3766`, `declarative_normalization.rs:3448-3480` | **Contract** → declared capabilities (registry index + A2A skills + OSSA) |
| `spec.handoffs` | optional | `[{name, agent, description}]`; string shorthand normalises local names to `bud:<slug>` | `lib.rs:4421-4427`, `declarative_normalization.rs:3338-3404` | Topology → handoff edges |
| `spec.output` | optional | `{schema: <JSON Schema>}` only. Aliases `outputSchema/output_schema/outputType/output_type/outputFormat/output_format` all fold in. Compiles to Goose `response.json_schema`. | `lib.rs:3768-3778`, `declarative_normalization.rs:4018-4054`, `manifest_compiler.rs:1860-1867` | Contract → `io.output.schema` (PACT must add `io.input`) |
| `spec.guardrails` | optional | `AgentGuardrailPolicy`: **8 stages** (see 1.1.6) | `lib.rs:3780-3820` | Policy → guardrails (portable) |
| `spec.budgets` | optional | `AgentBudgetPolicy`: **7 dimensions** (see 1.1.7); `deny_unknown_fields` | `policy_runtime.rs:753-782` | **Contract → operational SLO/budget** |
| `spec.permissions` | defaulted `{"mode":"ask"}` | free-form mapping; only `mode` is normalised (string shorthand → `{mode}`); **everything else passes through unvalidated** | `declarative_normalization.rs:3996-4016` | Policy → autonomy + approval; **PACT must give it real semantics** |
| `spec.runtime` | defaulted `{"kind":"goose"}` | mapping; `kind` must be `"goose"` (hard error otherwise); open object otherwise (see 1.1.8) | `declarative_normalization.rs:5164-5220` | Substrate → `runtime:` profile, and several sub-keys promote to Contract/Strategy |

Cross-cutting validation applied after assembly:
`validate_no_embedded_secret_config` on `spec.model`, `spec.permissions`,
`spec.runtime` — rejects secret-like keys and `Bearer …` strings
(`manifest_compiler.rs:256-258`, `portability.rs:1686-1710`).
**PACT must keep this: no credential material in the spec, ever.**

#### 1.1.4 `spec.tools` — `ToolPolicy`

| Sub-field | Aliases accepted | Semantics | Evidence |
|---|---|---|---|
| `available` | `allow`, `use`, `tools` | what the model can see/call | `lib.rs:3711`, `declarative_normalization.rs:3110-3114` |
| `autoApprove` | `auto_approve`, `allowed_tools`, `allowedTools` | runs without interrupt → Goose `always_allow` | `lib.rs:3713-3721`, `manifest_compiler.rs:3078-3084` |
| `requireApproval` | `require_approval` | forces interrupt → `ask_before` | `lib.rs:3722-3728` |
| `deny` | `hide`, `disallowed_tools`, `disallowedTools` | blocked pre-approval → `never_allow`; entries containing `:` or whitespace are treated as **patterns** | `lib.rs:3729-3736`, `declarative_normalization.rs:3207-3209` |
| `agents` | `agentTools` | `[{name, agent, description, delegateSource?}]` — agent-as-tool bindings | `lib.rs:4411-4419`, `declarative_normalization.rs:3244-3336` |

Enforced invariants PACT must preserve:
- a tool name may not appear in two of `{autoApprove, requireApproval, deny-exact}`
  (`declarative_normalization.rs:3170-3205`);
- each alias family may be specified **once only** — supplying both `allow:` and
  `available:` is an error (`:3211-3242`);
- tool refs may not contain whitespace, and `ns__tool` requires both halves
  (`runtime_validation.rs:1482-1494`).

Projection to a stable audit shape: `BudToolPermissionProjection {kind, target,
permission, source}` (`lib.rs:3741-3748`, built at `manifest_compiler.rs:3076-3106`).
**This projection is the real permission model. PACT should adopt it verbatim as
the normative approval matrix.**

#### 1.1.5 `spec.skills` — `SkillPolicy`

| Sub-field | Semantics | Evidence |
|---|---|---|
| `use[]` | Goose skill names, validated by `validate_goose_skill_name` | `declarative_normalization.rs:3428-3430` |
| `define[]` | `SkillDefinition {name, description, instructions, supportingFiles[{path, contents}]}`; duplicate names rejected; defined names auto-added to `use` | `lib.rs:3863-3883`, `declarative_normalization.rs:3431-3441` |

Skills materialise to `.agents/skills/<name>/SKILL.md` + supporting files
(`agent_package.rs:23-36`). A skill directory can be read back into a
`SkillDefinition` (`lib.rs:3907-3925`). **This is already the Expansion Rule in
miniature** — `skills.define[i]` ⇄ a directory. PACT should generalise it, not
reinvent it.

#### 1.1.6 `spec.guardrails` — 8 stages × per-guardrail record

Stages (`lib.rs:3782-3799`, dispatcher `:3808-3819`):
`input` (agent input) · `modelInput` · `modelOutput` · `toolInput` ·
`toolOutput` · `handoff` · `graphTransition` · `output` (agent output).

`AgentGuardrail` (`lib.rs:3822-3861`):

| Field | Default | Values / semantics | Evidence |
|---|---|---|---|
| `name` | — | required | `lib.rs:3825` |
| `evaluator` | `deterministic` | `deterministic \| sdk_callback \| model_judge` | `declarative_normalization.rs:4411` |
| `match` | — | `contains \| regex` (deterministic only) | `declarative_normalization.rs:4256-4290` |
| `pattern` | — | required for deterministic; forbidden for the other two | `:4291-4300` |
| `message` | — | required | `lib.rs:3835` |
| `caseSensitive` | `false` | | `lib.rs:3836-3837` |
| `action` | `block` | `block \| reject_content \| replace \| require_approval \| defer`; **only** settable for `deterministic` | `declarative_normalization.rs:4418-4426`, `:4326-4331` |
| `replacement` | — | deterministic + `replace` only | `:4337-4341` |
| `callback` | — | required iff `sdk_callback`; `[A-Za-z0-9_.-]{1,128}` | `:4302-4313`, `:4436-4444` |
| `model`, `prompt` | — | `model_judge` only | `:4315-4322` |
| `failureMode` | `block` | `block \| allow` (fail-closed default) | `policy_runtime.rs:31-33`, `declarative_normalization.rs:4428-4434` |
| `timeoutMs` | `30000` | | `policy_runtime.rs:39-41` |

**This is a fully-formed, portable, no-code guardrail language.** PACT should keep
the exact 8-stage vocabulary; adding stages is additive, removing any is a
migration break.

#### 1.1.7 `spec.budgets` — `AgentBudgetPolicy`

`policy_runtime.rs:753-782`, `deny_unknown_fields`:

| Field | Type | Evidence |
|---|---|---|
| `wallClockMs` | `u64?` | `:757` |
| `turns` | `u64?` | `:759` |
| `modelTokens.{input,output,total}` | `u64?` each | `:760-761`, `AgentModelTokenBudget` `:~735-751` |
| `toolCalls` | `u64?` | `:763` |
| `providerCostMicros` | `u64?` | `:765` |
| `handoffs` | `u64?` | `:767` |
| `childRuns` | `u64?` | `:769` |

Runtime accounting: `BudRunBudgetUsage` (`:786-803`), `BudRunBudgetReservation`
(`:832-845`), `BudRunBudgetState` with `apiVersion`, `rootRunId`, deadline,
reservations, and a `providerCostUnknown` flag (`:849-863`). Run plan carries
`budget` + `budgetRecords` (`lib.rs:8295-8298`).

**PACT's SLO object must be a strict superset of these 7 dimensions and must keep
the reservation/accumulator model.** Note what is *missing* and D16 requires:
no TTFT, no TPOT, no percentile semantics, no per-modality budget. Those are pure
additions (O4.2).

#### 1.1.8 `spec.runtime` — the open substrate object

`normalize_runtime` (`declarative_normalization.rs:5164-5220`) requires
`kind == "goose"` and otherwise clones the object. Generated schema declares it a
**non-strict** object (`sdk_codegen.rs:11085-11098`) with named keys
`loop`, `container`, `hooks`, `smartApprove`, `runState`, `subagents`; everything
else passes through. Observed keys in source:

| Key | Semantics | Evidence |
|---|---|---|
| `kind` | must be `"goose"` — **the single hardest lock-in point in the whole format** | `:5173-5175` |
| `loop` (aliases `agentLoop`, `agent_loop`, specifiable once) | `{kind: goose\|custom, protocol: "bud.loop.v1", maxIterations 1..=1024 (default 64), label ≤128B, executor{id, revision: sha256:<64 hex>}}` | `:5222-5385`, `lib.rs:3684-3707` |
| `container` | id string \| `false` \| `null` \| mapping `{id, engine, scope, appliesTo, developerTools}` | `:5426-5760` |
| `mcpServers` / `mcp_servers` | Goose extension configs; compiled into recipe `extensions` | `:5915-5940`, `manifest_compiler.rs:1845` |
| `subagents[]` | `[{manifest: <inline Agent>, package{path}} \| {budAgentToolProxy{schemaVersion, toolName}}]` — **the native nesting mechanism**; depth-limited to 5 below the root | `manifest_compiler.rs:1636-1720`; depth rule `sdk-and-declarative-dev.md:498-501` |
| `memory` | scoped-memory declaration: shorthand `session\|run\|agent\|agent_release\|user\|project\|team\|workspace\|organization\|false`, or `{stores[], context{maxRecords,maxBytes,query}}` | `scoped-agent-memory.md:29-62` |
| `gooseRecipe` | import-preservation block: `prompt`, `parameters`, extensions, sub-recipes, activities, retry, author metadata | `manifest_compiler.rs:1872-1930`; import contract `sdk-and-declarative-dev.md:3030-3034` |
| `gooseCustomAgent` | import provenance: `path`, `compatibility: role_agent`, `unsupportedSkillReferences` | `manifest_compiler.rs:2055-2058`; `sdk-and-declarative-dev.md:2952-2963` |
| `portable.unsupported` | OSSA import loss record | `registry-and-portability.md:1191`, `manifest_compiler.rs:2576` |
| `hooks`, `smartApprove`, `runState` | passthrough; each produces an OSSA export warning | `portability.rs:1813-1839` |

**PACT consequence.** `spec.runtime` is doing five unrelated jobs at once:
substrate binding (`kind`, `container`), execution semantics (`loop`), resource
declaration (`mcpServers`, `memory`, `subagents`), and import provenance
(`gooseRecipe`, `gooseCustomAgent`, `portable`). PACT must decompose it; the
converter needs a five-way fan-out rule, not a rename.

---

### 1.2 `kind: Team` — field table

`BudTeamManifest` `src/lib.rs:4430-4472`. Allowed spec fields
(`manifest_compiler.rs:45-47`): `strategy, manager, members, agents, shared, state, policy`.

| Field | Semantics | Evidence | PACT home |
|---|---|---|---|
| `spec.strategy` | default `sequential`; one of **11**: `sequential, parallel, dag(=graph), manager, router, supervisor, debate, consensus, map_reduce, mixture(=moa), evaluator_optimizer` | `declarative_normalization.rs:110-134` | Topology IR `kind:` |
| `spec.manager` | agent ref of the moderator/chair; when omitted the **last member** is moderator | `manifest_compiler.rs:493-499`; `sdk-and-declarative-dev.md:968-970` | Topology `coordinator:` |
| `spec.members[]` | `TeamMember {id, agent, inlineAgent?: BudAgentManifest, role?, prompt?, needs[], retry?}` | `lib.rs:4458-4472` | Topology nodes; `inlineAgent` ⇄ Expansion Rule directory |
| `spec.shared` | free `Value` (e.g. `{memory:{scope:team}}`) | `lib.rs:4452-4453` | Resources → shared memory/blackboard |
| `spec.policy` | free `Value` (e.g. `{approvalPropagation: parent}`) | `lib.rs:4454-4455` | Policy → propagation |

`sequential` auto-wires `needs` to the previous member
(`declarative_normalization.rs:147-149`) — an implicit-edge rule PACT must either
keep or make explicit in the converter.

Compilation: `manager|router|supervisor` compile to a **manager Agent** with
workers as `tools.agents` (`manifest_compiler.rs:1014`, `:1132`); every other
strategy compiles to a `Workflow` (`:538-553`). `debate/consensus/map_reduce/
mixture` become fan-in DAGs with Bud-native reducers
(`debate_argument_matrix`, `consensus_vote_tally`) — `sdk-and-declarative-dev.md:964-972`.

**PACT topology-superset check.** Against AC-5.1's eight patterns:
supervisor ✓, hierarchical ✓ (nested subagents), sequential pipeline ✓,
parallel map-reduce ✓, swarm/handoff ✓ (`spec.handoffs`), debate ✓,
**blackboard ~** (memory blackboard exists at `bud.dev/memory/v1` but is not a
Team strategy), **market/auction ✗** (no antecedent). Two of eight are new.

---

### 1.3 `kind: Workflow` — field table

`BudWorkflowManifest` `src/lib.rs:4475-4507`. Allowed spec fields
(`manifest_compiler.rs:32-44`).

| Field | Semantics | Evidence |
|---|---|---|
| `spec.strategy` | `sequential \| parallel \| dag \| graph`(aliases `state_machine`) | `declarative_normalization.rs:100-107` |
| `spec.entrypoint` | graph start node | `lib.rs:4494-4495` |
| `spec.state` | initial durable JSON state | `lib.rs:4496-4497` |
| `spec.stateSchema`, `spec.outputSchema` | JSON Schema | `lib.rs:4498-4501` |
| `spec.limits` | `WorkflowGraphLimits {maxTransitions, maxNodeExecutions, maxFanOut, maxConcurrency, maxStateBytes, maxSubgraphDepth, maxWorkflowDurationMs?, maxStepDurationMs?}` | `lib.rs:4532-4556` |
| `spec.saga` | `{compensateOn[], onCompensationError}` | `lib.rs:4509-4514` |
| `spec.steps[]` | `WorkflowStep` — see below | `lib.rs:4706-4749` |

`WorkflowStep` fields: `id, kind, agent?, prompt?, needs[], next[WorkflowEdge],
inputs[], promptTemplate?, includeState?, reducer?, output{path,reducer}?,
outputSchema?, command{update,goto,resume}?, foreach{path,maxItems,concurrency,
onOverflow,sampleSeed,onMissing}?, workflow(subgraph)?, state, retry?,
compensate?, model(override)?`.

- Node kinds: `agent | humanReview | reducer | command | subgraph`
  (`declarative_normalization.rs:956-976`).
- Edge conditions: JSON Pointer `path` + operator from the **closed,
  non-executable** set `eq, ne, exists, truthy, falsy, contains, gt, gte, lt, lte`
  (`declarative_normalization.rs:1968-2005`, `:2069-2080`).
- State reducers: `replace, append, extend, merge, sum, reference, discard`
  (`declarative_normalization.rs:1754`).
- Fan-out overflow policy: `fail | truncate | sample(seeded)`
  (`lib.rs:4592-4605`); missing-path policy `error | empty` (`:4613-4625`).
- Retry: `maxRetries, backoffMs, includeFailureContext, backoffStrategy
  (fixed|exponential), backoffMultiplier, maxBackoffMs, jitterMs`
  (`lib.rs:4811-4840`); jitter is **deterministically seeded by SHA-256** so
  replays reproduce delays exactly (`:4893-4901`).
- `includeFailureContext` appends a machine-derived, prompt-injection-hardened
  failure block to the retry prompt (`lib.rs:4908-4938`) — this is a **Reflexion
  primitive already in the format**.
- Per-step model override is **additive and cannot introduce tools or
  permissions**, by design (`lib.rs:4686-4704` and its doc comment).

**PACT loop-IR consequence:** the `command` node + `goto` + `foreach` + reducers +
seeded jitter give PACT most of `G-3` for free. What is missing versus AC-5.2:
no self-consistency/best-of-N node, no explicit tool/function/router node kinds
(also named in `runtime-gap-analysis.md:154`), no tree-of-thought.

---

### 1.4 `kind: Schedule` — field table

`ScheduleSpec` `src/lib.rs:4999-5025`.

| Field | Semantics | Evidence |
|---|---|---|
| `spec.target` | `RegistrySelector` — id **xor** search filters; both → error; neither → error | `agent_package.rs:267-332` |
| `spec.prompt` | run input | `lib.rs:5002` |
| `spec.cron` | 5-field normalised to Goose 6-field; validated with the *same* `croner` parser Goose uses; `@daily` rejected | `agent_package.rs:367-409` |
| `spec.timezone` | `local` sentinel or validated IANA id (≤128 chars, checked against bundled tzdb) | `agent_package.rs:413-438` |
| `spec.concurrency` | `skip_if_running \| allow_parallel` only | `agent_package.rs:481-489` |
| `spec.enabled` | bool | `lib.rs:5006` |
| `spec.catchupPolicy` | `{mode: skip \| coalesce \| replay{max}}`, default `skip` | `lib.rs:4978-4997` |
| `spec.catchupWindowSecs` | `0` disables catch-up | `lib.rs:5016-5024` |

---

### 1.5 `kind: Eval` — field table (the one PACT most has to beat)

`src/eval.rs`. Every struct is `deny_unknown_fields`.

| Field | Semantics | Evidence |
|---|---|---|
| `metadata.{name, description, displayName?}` | | `:24-31` |
| `spec.target` | exactly one of `agent` (registry id) / `selector` (RegistrySelector) / `manifest` (path) / `inlineAgent` (full `BudAgentManifest`) | `:44-60`, resolver `:375` |
| `spec.cases[]` | `{id, prompt, graders[]}` — **no expected output, no dataset ref, no context/retrieval fields** | `:62-68` |
| `spec.thresholds` | `{minimumPassRate (default 1.0), maximumFailedAttempts?}` | `:131-147`, `:2042-2044` |
| `spec.execution` | `{repetitions (default 1), failFast (default false)}` | `:149-165`, `:2046-2048` |

**Graders — the complete set (8, all deterministic, `#[serde(tag="kind")]`,
`:70-129`):** `terminalStatus{statuses[] default ["completed"]}` ·
`outputContains{value, caseSensitive}` · `outputNotContains{…}` ·
`outputEquals{value}` · `outputRegex{pattern, caseSensitive}` ·
`jsonSchema{schema}` · `eventCount{event, minimum, maximum?}` ·
`artifactCount{artifactKind?, artifactName?, mimeType?, minimum, maximum?}`.

Bounds enforced: ≤1 000 cases, ≤10 000 attempts, ≤64 graders/case,
≤100 000 grader evaluations, ≤1 MiB prompt, ≤4 KiB regex, ≤1 MiB case artifact,
≤128 MiB report artifact (`:5-12`).

**Negative findings that define PACT's eval work:**
- **No LLM judge, no semantic metric, no rubric.** Every DeepEval-class metric
  (faithfulness, answer_relevancy, contextual_*) is inexpressible.
- **No dataset files.** Cases are inline only; no CSV/JSONL/`datasets/` reference.
- **No trace→case promotion.** Recovery explicitly refuses to keep prompts and
  raw model output as recovery artifacts (`sdk-and-declarative-dev.md:763-766`).
- **No per-metric thresholds.** One global `minimumPassRate`.
- **No SLO assertions.** Latency/cost cannot be asserted in an Eval.
- Attempts run as **normal Goose child runs** with full ledger lineage, and fully
  graded attempts commit redacted versioned evidence before the parent advances
  (`sdk-and-declarative-dev.md:752-766`). *This part is excellent and PACT must
  keep it.*

---

### 1.6 `kind: EventSubscription` — field table

`src/event_subscription.rs:40-94`.

| Field | Semantics |
|---|---|
| `spec.filter` | `BudEventFilter {eventTypes[], sources[], subjects[]}` — CloudEvents-shaped (`:69-77`) |
| `spec.target` | tagged enum: `{kind: agent, selector}` **or** `{kind: workflow, workflow: <BudWorkflowManifest>}` (`:79-84`) |
| `spec.prompt` | run input |
| `spec.retry` | `{maxAttempts, initialBackoffMs, maxBackoffMs, multiplier, leaseMs}` (`:86-94`) |
| `spec.concurrency`, `spec.maxPending`, `spec.enabled` | (`:59-67`) |

**This is the "feedback events" construct the assignment asked about — it already
exists.** The gap-analysis line that motivated the ask
(`runtime-gap-analysis.md:193-196`: "Resident operation needs a durable
mailbox/task queue, claimed-delivery leases, **event subscriptions**, dead-letter
handling, and scoped cross-run memory") is stale: `src/event_subscription.rs` is
6 831 lines with a full create/list/inspect/update/delete/activate/cancel/purge
control plane (dispatcher `:540-616`).

---

### 1.7 `AgentBlueprint` — authoring sugar (not a manifest)

`src/lib.rs:3959-4119` (root) and `AgentSubagentDefinition` `:4121-4317` (child).
This is the **no-code on-ramp** and is where D13/D14 must actually land.

Root fields (with their accepted aliases, all verified in the `#[serde]` attrs):
`name`, `aliases`, `purpose` (`goal|task|role`), `instructions`
(`systemPrompt|system_prompt|prompt`), `description`, `displayName`, `model`,
`tools` (`tool`), `skills` (`skill`), `contextFiles`
(`context_files|knowledgeFiles|knowledge_files|knowledge`), `capabilities`,
`agentTools` (`agent_tools`), `handoffs`, `subagents`
(`programmaticSubagents`), `initialPrompt`, `recipePrompt`
(`inputTemplate|runPrompt`), `recipeParameters`
(`inputParameters|runtimeParameters`), `memory`, `mcpServers`, `maxTurns`,
`effort` (`thinkingEffort|reasoningEffort`), `thinking`, `maxThinkingTokens`
(`maxReasoningTokens`), `background`, `permissionMode`, `output`
(`outputSchema|outputType|outputFormat`), `guardrails`, `permissions`,
`runtime`, `includeGuideSkill` (default **true**).

`AgentSubagentDefinition` adds: `mode`, `asTool` (`as_tool|agentTool`),
`handoff` (`handoffEnabled`), `toolName`, `handoffName`, `allowedTools`,
`disallowedTools`, and recurses via its own `subagents`.

Semantic notes verified in source/doc:
- `mode: agentTool | handoff` selects whether the child becomes a
  `tools.agents` binding or a `handoffs` binding (`blueprint.rs:1209`).
- `effort` normalises to Goose `thinking_effort`; `thinking.enabled` /
  `maxThinkingTokens` normalise to `request_params.budget_tokens`
  (`sdk-and-declarative-dev.md:492-497`).
- `contextFiles` are *not* skills — they land as `SkillSupportingFile` records
  (`lib.rs:3997-4007`).
- `includeGuideSkill: true` **silently injects a guide skill** into every
  blueprint-authored agent (`lib.rs:4117-4118`). PACT must decide: keep as a
  profile default (F-1 says every default must live in a profile), or drop.

**PACT consequence:** the blueprint is a *lossy-upward* sugar layer over the
Agent manifest. Under D14 ("no-code is the ceiling") PACT cannot have a
two-tier format where the beginner tier can express less. The Expansion Rule
plus profiles must replace the blueprint entirely — otherwise the converter has
to preserve blueprint↔manifest asymmetry forever.

---

### 1.8 What `bud.dev/v1` **cannot** express (negative inventory)

These are the hard adds PACT owes, each verified as absent:

| Missing construct | Evidence of absence | PACT requirement |
|---|---|---|
| **Input contract / modality** | no `spec.input` in `AGENT_SPEC_FIELDS` (`manifest_compiler.rs:8-31`); `RunInputMetadata.kind` always `"text"` (`lib.rs:8349`, all call sites); cards hardcode `text/plain`+`application/json` (`manifest_compiler.rs:3677`, `portability.rs:2051`) | D16: content-typed `io.input`/`io.output`; card projection driven from it |
| **Streaming semantics** | `capabilities.streaming: true` hardcoded on every card (`manifest_compiler.rs:3673-3676`) | Contract: declared streaming mode, per-modality |
| **Capability *requirements*** | `spec.capabilities` is what the agent **provides** (`lib.rs:3758-3766`, exported as A2A skills `portability.rs:2067-2089`) — nothing declares what an executor must **have** | O3.1 predicate language is 100% new |
| **Model catalogue / benchmark predicates** | `spec.model` is a binding, not a requirement (`declarative_normalization.rs:3041`) | `models/catalog.yaml` + predicates (D8) |
| **Variants** | no field; one model per agent | Strategy-space: `variants/` |
| **Version / namespace on the manifest** | `AgentMetadata` (`lib.rs:3652-3660`); exporters hardcode `1.0.0` | `metadata.version`, `metadata.namespace` |
| **Extension namespace (`x-`)** | unknown fields hard-rejected (`manifest_compiler.rs:49-67`) | `x-` blocks that round-trip (O1.4, AC-1.3) |
| **SLO percentiles / TTFT / TPOT** | `AgentBudgetPolicy` has none (`policy_runtime.rs:753-770`) | O4.2 |
| **Eval judge/metric/dataset** | grader enum is closed at 8 deterministic kinds (`eval.rs:70-129`) | D6 provider URIs, D19 five on-ramps |
| **Learning / optimizer** | no field anywhere | O5.3 Learning IR |
| **Non-Goose runtime** | `spec.runtime.kind != "goose"` is a hard error (`declarative_normalization.rs:5173-5175`) | Substrate must be open; `goose` becomes one profile |
| **Market/auction + blackboard topologies** | not in the 11 team strategies (`declarative_normalization.rs:116-129`) | AC-5.1 |
| **`Channel` manifest** | documented (`sdk-and-declarative-dev.md:2564`) but **no normalizer exists** | PACT should either specify it or explicitly declare channels out of scope (D24) |

---

## 2. WHAT THE RUNTIME DOES THAT A SPEC MUST NOT BREAK

Each subsection states the invariant, its evidence, and the PACT obligation.

### 2.1 Registry coordinates & revisions

- An agent's runtime identity is the **immutable triple**
  `BudAgentReleaseCoordinate {id, version, revision}`
  (`crates/bud-agent-types/src/lib.rs:960-966`). The revision is a
  `sha256:` over **behaviour-affecting entry data plus credential-binding names**,
  deliberately excluding local discovery paths and lease bookkeeping
  (`registry-and-portability.md:74-83`).
- Registry IDs are prefix-namespaced and stable: `bud:<slug>`, `a2a:<slug>`,
  `goose/current`, `goose/recipe/<slug>`, `goose/agent/<slug>`,
  `goose/skill/<slug>` (`registry-and-portability.md:56-66`;
  construction at `registry_sources.rs:420`).
- Namespaces must be claimed before publication; `bud`, `goose`, `a2a` are
  reserved to `system/bud`, `system/goose`, `system/a2a`
  (`registry-and-portability.md:85-87`). Dependency ranges are SemVer; an opaque
  active dependency reports `invalid_version` (`:80-83`).
- Activation is CAS/generation-checked with append-only history and rollback
  (`:88-92`, `:616-625`).
- Non-runnable inventory records carry `budRuntimeRunnable: false` and are
  excluded from ranked discovery and A2A invocation (`:94-97`).

**PACT obligation.** PACT identity must *project onto* this triple, not replace
it. `metadata.name` + `metadata.namespace` + `metadata.version` → `{id, version}`;
`canonical.json` digest is a **candidate** for `revision` but is not equal to it
today (the registry revision covers registry-entry data, not the source tree).
Decide explicitly: either (a) PACT digest becomes the revision, and the registry
revision computation is changed, or (b) they stay distinct and the lockfile
records both. **Silently reusing the word "revision" for two different digests is
a migration hazard.**

### 2.2 Access envelope (`bud.dev/agent-access/v1`)

- Every registry record carries one owner `(tenant, subject)`, a visibility
  (`private | tenant | public`), an optimistic `generation`, and typed grants over
  the closed action set `discover, read, invoke, manage, publish`
  (`registry-and-portability.md:640-660`; types at
  `crates/bud-agent-types/src/lib.rs:148-170`, `:367`).
- The policy is persisted in a **reserved metadata envelope**
  `_budAgentAccessV1` (`crates/bud-agent-types/src/lib.rs:8`). A record without it
  is deterministically read as generation 0, private,
  owner `legacy/system-legacy`, and only a system context can see or migrate it
  (`registry-and-portability.md:676-681`).
- **Agent-supplied metadata is untrusted**: kind, namespace, package path, display
  name, package/card body and agent metadata are never trusted tenant inputs;
  producers overwrite forged `_budAgentAccessV1` input before the first insert
  (`registry-and-portability.md:683-691`).
- `AgentRecord.access` is a **projection**: non-managers see only apiVersion,
  generation, owner tenant, and visibility (`:769-776`).
- Startup fails closed if the registry is not access-ready
  (`:693-698`).

**PACT obligation.** Access is **not** a spec field. PACT manifests must carry no
owner/visibility/grant data, and the loader must not invent any. The PACT→registry
producer must run inside `BudRegistryProducerContext`. This is the concrete meaning
of D24 "minimal + adapter-shaped": PACT declares *identity and capability*; the
registry declares *who may see and invoke*.

### 2.3 A2A Agent Card projection

Two projections exist and they must not diverge:

1. **Package card** — `export_a2a_agent_card(manifest, base_url)`
   (`manifest_compiler.rs:3656-3702`) → `.well-known/agent-card.json`
   (`agent_package.rs:77-82`).
2. **Registry card** — `agent_registry_card.rs`, served at
   `GET /bud/registry/{id}/a2a-card` and
   `GET /.well-known/agent-card.json?targetId=…`
   (`registry-and-portability.md:1011-1013`).

Fixed shape (verified `manifest_compiler.rs:3664-3692`):
`name`, `description`, `version: "1.0.0"` (hardcoded), one
`supportedInterfaces[]` entry `{url: <base>/a2a/v1, protocolBinding: "JSONRPC",
protocolVersion: "1.0"}`, `capabilities {streaming:true, extendedAgentCard:false}`,
`defaultInput/OutputModes` hardcoded, `skills` from `a2a_skills`, and
`metadata.bud {runtime, agentTools, capabilities, handoffs, a2a}`.

`a2a_skills` (`portability.rs:2043-2117`) emits, in order and deduped by id:
- a synthetic `default` skill when both `skills.use` and `capabilities` are empty;
- one skill per `skills.use[]`;
- one skill per `spec.capabilities[]` (tags = `bud,goose,capability` + declared tags);
- `agent-tool:<name>` per `spec.tools.agents[]`;
- `handoff:<name>` per `spec.handoffs[]`.

Hard security rules PACT must preserve
(`registry-and-portability.md:1029-1040`, `:171-178`): public cards must **not**
contain `packagePath`, `sourceUrl`, endpoint provenance for proxied targets,
artifact paths, Goose custom-agent/recipe filesystem paths, Goose skill
support-file paths, Goose data directories, working directories, or Goose session
ids. Every published skill must have non-empty `id/name/description/tags`.
Cards are `Cache-Control: public, max-age=60, must-revalidate` with a strong ETag
over the exact JSON body and `304` on `If-None-Match` (`:1041-1043`).
`pushNotifications` is deliberately **not advertised** until server-side push
config + durable webhook delivery ship together (`:1085-1090`).

`agent-tool:` / `handoff:` skill ids are **selectable by remote peers** via
`params.metadata.skillId | budSkillId | "bud.skillId"`; Bud plans the addressed
agent as parent and executes the named declared child
(`sdk-and-declarative-dev.md:1113-1124`).

**PACT obligation.** The facade-id grammar `agent-tool:<name>` / `handoff:<name>`
is a **wire contract with remote peers**. Renaming PACT's tool/handoff bindings
changes remote invocation. PACT must (a) drive `version` from
`metadata.version` instead of `"1.0.0"`, (b) drive `defaultInput/OutputModes` from
the new I/O contract, and (c) keep the id grammar byte-compatible.

### 2.4 Run ledger lineage

`BudRunPlan` (`lib.rs:8255-8301`) is the durable unit. Fields PACT must not
disturb: `runId, status, backend, targetId, targetVersion, targetRevision,
targetKind, targetName, input, authorization, agentRegistrySnapshot, lineage,
fork, orchestration, goose, gooseCustomAgent, gooseSession, a2a, events,
interrupts, checkpoints, artifacts, executionPolicy, budget, budgetRecords,
guardrailDecisions`.

- `RunLineage {parentRunId, rootRunId, nodeId, relationship, depth}`
  (`lib.rs:8355-8363`). `relationship` carries `agent_as_tool | handoff |
  child_run | spawned_by_run | bundled_subagent` (values observed at
  `registry-and-portability.md:238`, `:613-614`, `:179-180`).
- `RunEvent {seq, kind, status?, message?, metadata}` — per-run monotonic `seq`,
  append-only, `Last-Event-ID`-style cursor replay
  (`lib.rs:8463-8473`; `sdk-and-declarative-dev.md:1131-1137`).
- `RunArtifact {artifactId, kind, name, mimeType, bytes, sha256, uri,
  contentPath, metadata}` (`lib.rs:8524-8537`) — content-addressed sidecars.
- `RunCheckpoint {id, kind, reason, eventSeq, runStatus, activeNodeId?,
  childRunIds[], pendingInterruptIds[], artifactIds[], metadata}`
  (`lib.rs:8504-8522`).
- `RunForkPlan {sourceRunId, sourceCheckpointId?, sourceEventSeq, sourceStatus,
  sourceGooseSessionId?, forkedGooseSessionId?, metadata}` (`lib.rs:8365-8379`) —
  an executable fork **requires a copied Goose session id** so a branch never
  reuses the source session (`sdk-and-declarative-dev.md:2724-2731`).
- `BudRunAgentRegistrySnapshot {source, allowedAgentIds[]}` (`lib.rs:8318-8346`)
  pins the set of agents a run may reach.
- `BudRunAuthorizationEvidence` (`run_authorization_evidence.rs:361-403`):
  principal, required action, `planScopeJcsSha256`, per-coordinate decisions,
  `parentEvidenceJcsSha256`, `evidenceJcsSha256` — a **JCS-canonical hash chain**
  from parent run to child run.
- The ledger deliberately does **not** persist raw prompts or raw artifact text
  (`registry-and-portability.md:1095-1097`; `RunInputMetadata` records only
  `kind/bytes/redacted`).

**PACT obligation.** Learning (T6/O5.3) needs traces; the ledger by design does not
store prompts. PACT's trace→eval promotion must therefore define a **separate,
opt-in, redaction-policy-bound trace store**, not assume the ledger has the text.
This is the single biggest hidden dependency in the learning design.

### 2.5 Interrupts

`RunInterrupt {id, source, status, reason, requestId?, eventSeq, decision?,
metadata}` with `RunInterruptDecision {decision, message?, decidedAtSeq,
command?: WorkflowCommand, metadata}` (`lib.rs:8475-8502`).

Unified sources (`registry-and-portability.md:240-257`): Goose tool approvals,
Goose elicitations, A2A `input-required`/`auth-required` task states (including
the `TASK_STATE_*` spelling), and workflow human-review gates.
Child interrupts propagate to the parent as `child_run` interrupts linking
child run, child interrupt, node id, relationship, source, request id; resolving
the parent applies the same decision to the child (`:255-257`).
Resume of a workflow gate applies review output + RFC 7396 state patch + routing
in **one cursor commit**, and rejects routes the manifest did not declare
(`sdk-and-declarative-dev.md:908-911`).

Bounds: interrupt resolution message ≤64 KiB, workflow command ≤1 MiB,
Goose elicitation user data ≤1 MiB (`lib.rs:86-88`).

**PACT obligation.** PACT's HITL construct must map 1:1 onto this: one interrupt
model, four sources, parent/child propagation, declared-routes-only resume. Adding
a fifth interrupt source is additive; changing the resolve semantics is not.

### 2.6 Permissions — the real enforcement path

**Verified reality (this contradicts the docs):**
- `spec.permissions.mode` affects execution in exactly one way: `chat`/`chatOnly`/
  `chat_only` → `GooseMode::Chat`; everything else falls to `GooseMode::default()`
  (`goose_adapter.rs:34386-34395`).
- Enforcement comes from `ToolPolicy`: if any of `autoApprove/requireApproval/deny`
  is non-empty, the `bud_tool_policy` inspector is added to preflight and applies
  exact and pattern decisions per call
  (`goose_adapter.rs:33990-34019`, `:34022-34025`).
- Session-level user permissions are layered on top by
  `bud_session_tool_permissions`, but **never override a `bud_tool_policy` deny**
  (`goose_adapter.rs:34026-34060`).
- Goose's own resolution order is
  session-user → user → mode-derived (`goose_adapter.rs:34340-34356`).
- `spec.permissions` is otherwise consumed only by explain
  (`manifest_compiler.rs:3259`), OSSA autonomy (`:3451` →
  `autonomy_level` `portability.rs:2031-2041`: `ask|manual|readonly` →
  `supervised`; `approve|auto` → `autonomous`; anything else → `collaborative`),
  Goose-source frontmatter (`:3060`), and export warnings
  (`portability.rs:1769-1799`).
- `permissions.rules.{allow,ask,deny}` from `sdk-and-declarative-dev.md:2129-2137`
  is **not parsed anywhere**. `normalize_permissions` clones unknown keys through
  (`declarative_normalization.rs:4004-4015`).

Separation of controls is an architecture invariant:
"Availability, permission, approval, and policy are separate controls. An SDK tool
becoming visible never means it is auto-approved"
(`runtime-gap-analysis.md:76-78`; also `architecture.md:1440-1441`).

**PACT obligation.** Do **not** carry `permissions.mode` forward as if it were
enforcement. Make the tool-permission projection (`kind/target/permission/source`)
the normative surface, define `mode` as a *profile default* that expands into that
projection, and mark `permissions.rules` as never-implemented so the converter can
warn instead of silently dropping.

### 2.7 Goose recipe compilation (the lowering PACT inherits)

`compile_goose_recipe` (`manifest_compiler.rs:1821-1870`) emits:
`version: "1.0.0"`, `title` = `metadata.name`, `description`, `instructions` (from
`spec.instructions` via `goose_instructions`), `prompt` (default
`"{{ bud_prompt }}"`, overridable only if `spec.runtime.gooseRecipe.prompt`
*contains* `bud_prompt` — `:1872-1885`), `parameters` (always contains a
`bud_prompt` parameter — `:1887-1919`), `extensions` (from `tools.available` +
`skills.use` + `runtime.mcpServers`, plus `summon` when sub-recipes exist),
`sub_recipes` (from `runtime.subagents`), `settings` (from `spec.model`), and
`response.json_schema` (from `spec.output.schema`).

Delegation-safe variant makes `bud_prompt` optional with a default so a `summon`
child can run without an explicit prompt (`agent_package.rs:121-140`).
Agent-tool proxies compile to a stub recipe carrying
`kind: bud.agent_tool_proxy`, `schemaVersion: 1`, `toolName` in
`author.metadata` (`agent_package.rs:142-171`).

Export loss reporting is real: unsupported `spec.model` keys outside
`{provider,name,temperature,max_tokens,thinking_effort,request_params,max_turns}`
warn (`portability.rs:1861-1879`); agents-as-tools, handoffs, inline skills,
guardrails, permissions and runtime metadata all warn
(`sdk-and-declarative-dev.md:3026-3029`).

**PACT obligation.** `bud_prompt` is a **wire contract** with the Goose CLI
(`goose run --recipe … --params bud_prompt=<input>` —
`sdk-and-declarative-dev.md:1074`, template built at
`run_planning.rs:2526-2530`). PACT's Goose adapter must keep emitting it.

### 2.8 Package materialisation & trust

`materialize_agent_package` (`agent_package.rs:3-86`) writes exactly:
```
agent.bud.yaml                       canonical manifest (serde_yaml of the normalized struct)
.agents/agents/<name>.md             Goose custom-agent source + `bud:` frontmatter
.agents/skills/<skill>/SKILL.md      per skills.define[]
.agents/skills/<skill>/<file>        supportingFiles
recipes/<name>.goose.yaml            Goose recipe
recipes/<sub-recipe path>            per runtime.subagents[]
subagents/<child>/…                  full nested package, recursively
portable/agent.ossa.yaml             OSSA export
.well-known/agent-card.json          A2A card
README.md
```
`check_agent_package` (`:193-261`) re-derives every generated artifact and
byte-compares it against the on-disk copy, then scans for secrets. The package
digest is a domain-separated SHA-256 over sorted `path/len/bytes`
(`package_trust.rs:99-120`) and is the payload for Ed25519 signing
(`:122-128`).

Trust policies: `allow_unverified | require_lockfile |
require_signature_marker | require_verified_signature`; strict policies preview
the install in a temporary plugin root and reject before mutating the real Goose
package directory; `BUD_AGENT_PACKAGE_TRUST_POLICY` sets the default
(`sdk-and-declarative-dev.md:2890-2899`).

**PACT obligation.** The package layout is the *closest existing thing to a PACT
tree*, and `check_agent_package` is the closest thing to `explode∘collapse ≡ id`
(AC-1.2). Reuse both. But note: **the digest covers derived artifacts**, so under
D2 (`canonical.json` derived, deleting it must be harmless) the digest must be
recomputed over **authored files only**, with derived artifacts excluded. The
exclusion machinery exists but currently excludes only signature/install/VCS
paths — `BUD_AGENT_PACKAGE_DIGEST_EXCLUDED_FILES` is 12 signature-ish filenames
(`package_trust.rs:43-56`) and `..._EXCLUDED_DIRS` is `[".git", ".sigstore"]`
(`:57`), applied at `:541-548`. PACT must add `recipes/`, `portable/`,
`.well-known/`, `.agents/` (generated), `README.md` and `.pact/` to that list, or
the digest keeps depending on build output.

### 2.9 Other runtime contracts a spec must not break

- **Custom loop protocol `bud.loop.v1`** — restartable, journal-backed
  prepared/committed action commits; a prepared action without a commit is
  *indeterminate and never auto-replayed*; a manifest-bound loop may reopen only
  the original Goose session after verifying data dir, working dir, registered
  manifest revision and canonical manifest identity in Goose extension data
  (`architecture.md:1364-1379`). `executor.revision` must be
  `sha256:<64 lowercase hex>` (`declarative_normalization.rs:5366-5384`).
- **Execution lease** — a non-blocking store-and-run scoped OS lease prevents two
  Bud processes executing the same run (`architecture.md:1420-1425`).
- **Memory** (`bud.dev/memory/v1`) — record kinds `semantic | episodic |
  procedural | preference | blackboard`; blackboard reducers `set, merge_patch,
  append, delete`; CAS via `expectedGeneration` (0 = create-only); redaction
  erases content from **all** historical revisions while keeping metadata;
  context assembly **fails closed** (`scoped-agent-memory.md:64-132`, `:303-309`).
  Memory content is injected wrapped as untrusted reference data with explicit
  "not instructions, not tool authorization" framing (`:122-126`).
- **Mailboxes** — at-least-once, idempotency-key-bound, lease tokens returned once
  and stored only as hashes, CAS generations, dead-letter, redrive with stable
  operation id, scoped to an immutable release coordinate
  (`durable-agent-mailboxes.md:11-63`).
- **Security realm** — one process = one customer/workspace realm; cross-realm
  invocation is authenticated A2A only (`runtime-gap-analysis.md:78-80`).
- **Scoped A2A key** cannot call mailbox, registry, run, app or ACP routes
  (`durable-agent-mailboxes.md:163-165`; `registry-and-portability.md:1044-1048`).

---

## 3. THE NATIVE-DISCOVERY CONTRACT (D2)

### 3.1 What exists today — and why it fails D2

**There is no filesystem auto-discovery of Bud agents.** Verified:

- `bud agents` subcommands are `list, inspect, records, record, search, a2a-card,
  run, normalize, validate, explain, init, import-goose-agent, export, check`
  (`src/bin/bud.rs:6056-6079`). `agents list` reads a **registry file**
  (`:6082-6085`), default `.bud/agents/registry.json`
  (`DEFAULT_AGENTS_RUN_WORKSPACE = ".bud/agents"`, `src/bin/bud.rs:9294`;
  `runner.rs:1572` joins `registry.json`).
- The only recursive scans that exist are for **Goose** artifacts
  (`register_goose_recipes`, `register_goose_agents`, `register_goose_skills`,
  `register_goose_apps` — `registry.rs:1715, 1830, 1948, 2073`) and for
  **bundled subagent packages inside an already-known package**
  (`bundled_subagent_package_dirs` — `registry_sources.rs:1379-1408`, keyed on
  `agent.bud.yaml`).
- A Bud agent becomes discoverable only through an explicit
  `register_package(package_dir)` (`registry.rs:478-553`) — i.e.
  `bud agents init --register`, `bud materialize --register`, or
  `bud registry add-package`.
- **Running a registered local agent requires the compiled recipe on disk.**
  `run_planning.rs:2447-2473`: the artifact `recipes/<name>.goose.yaml` must be
  listed in `entry.artifacts` (when non-empty) *and* must exist as a file, else
  `"Goose recipe artifact {} not found for registry entry {:?}"`.

**Conclusion: `bud.dev/v1` requires a build step. D2 is currently violated.**

### 3.2 The escape hatch that makes D2 achievable

`BudUniversalAgentRuntime::create_agent(&BudAgentManifest, working_dir)`
(`goose_adapter.rs:9970-9983`) and `::run(BudUniversalAgentRunRequest)`
(`:9985-10013`) build a live Goose agent **directly from the manifest struct**.
They call `create_bud_agent_session(manifest, working_dir)`
(`goose_adapter.rs:27509-27516`) and never read `recipes/*.goose.yaml`.
Input guardrails are enforced on this path
(`enforce_agent_input_guardrails`, `:9990`).

So the runtime already contains a **manifest-in-memory executor**. What is missing
is (a) a tree→manifest loader and (b) a registry entry that does not demand a
recipe artifact.

### 3.3 The contract PACT should specify

**What the runtime scans for.** Two roots, both already conventional in the tree:

1. `.agents/` — the OSSA-aligned project convention Goose already discovers for
   `skills/` and `recipes/` (`registry-and-portability.md:304-331`);
2. `.bud/agents/` — the existing default agent workspace
   (`src/bin/bud.rs:9294`).

Discovery unit = **a directory containing a PACT root file**. Recommended root
names, in resolution order, all of which must be recognised:
`agent.yaml` (PACT native), `agent.bud.yaml` (bud.dev/v1 compatibility),
`team.yaml`, `workflow.yaml`, `eval.yaml`, `workspace.yaml`.
Precedent for "directory identified by a well-known file" is already
`bundled_subagent_package_dirs` keying on `agent.bud.yaml`
(`registry_sources.rs:1402`).

**What the runtime is guaranteed** (this is the normative list PACT owes):

| Guarantee | Why the runtime needs it | Backed by |
|---|---|---|
| G1. The tree loads to a complete in-memory document **with zero derived files present** | D2.2; enables `create_agent(manifest, dir)` | `goose_adapter.rs:9970` |
| G2. Loading is **pure and offline** — no network, no shell, no code execution | D17 air-gap; the loader runs inside a security realm | `runtime-gap-analysis.md:78-80` |
| G3. A stable `id` = `namespace/name`, a `version`, and a content `revision` computed over **authored files only** (derived paths excluded) | registry release coordinate | `crates/bud-agent-types/src/lib.rs:960`; exclusion machinery `package_trust.rs:541-548` |
| G4. `capabilities[]` with `{name, description, tags}` | registry capability index + A2A skills + OSSA | `lib.rs:3758`, `portability.rs:2067` |
| G5. Declared `tools[]`, `skills[]`, `mcpServers` and `models` as **references the runtime may already own** — never inline copies | AC-6.2; MCP dependency preflight | `registry-and-portability.md:1130-1131` |
| G6. The tool-permission projection `{kind,target,permission,source}` | `bud_tool_policy` inspector | `manifest_compiler.rs:3076-3106`, `goose_adapter.rs:33990` |
| G7. Guardrails resolved per stage, ready to run before the first provider call | 8-stage pipeline | `lib.rs:3808-3819` |
| G8. Budget policy (7+ dims) for the run accumulator | `BudRunBudgetState` | `policy_runtime.rs:849-863` |
| G9. `io.input`/`io.output` content types → card `defaultInput/OutputModes` and `RunInputMetadata.kind` | D16; today hardcoded | `manifest_compiler.rs:3677`, `lib.rs:8349` |
| G10. Autonomy level for the Ladder | OSSA `spec.autonomy.level` | `portability.rs:2031-2041` |
| G11. Declared child bindings (`tools.agents`, `handoffs`, `subagents`) resolvable to registry refs **before** the parent run is persisted | facade preflight fails atomically | `sdk-and-declarative-dev.md:1120-1123` |
| G12. Every eval suite in the tree, addressable as a schedulable target | `Eval` runs as a Goose child run | `eval.rs:436` |
| G13. A machine-readable **load report**: every file consumed, every file ignored, every unknown `x-` block preserved | AC-7.1 no silent loss | new |

**Explicit non-guarantees** (so the runtime cannot come to depend on them):
the tree does not supply ownership/visibility/grants (§2.2); does not supply
credentials (`portability.rs:1686`); does not supply the registry revision unless
PACT and the registry are explicitly unified (§2.1).

**Two loader modes PACT must specify.**
- *Cold* (D2 path): tree → document → `create_agent` in process. No `.pact/`, no
  recipe, no registry write. This is what makes AC-6.1 true.
- *Warm* (production path): tree → document → registry entry + optional
  materialisation for the Goose CLI/scheduler/A2A backends. `.pact/canonical.json`
  is a cache keyed by the authored-file digest; **deleting it must only cost time**.

**The one runtime change PACT forces.** `plan_local_bud_agent` must gain a branch
that plans a `bud_universal_agent` backend from a manifest path, with no
`recipes/*.goose.yaml` precondition. Without that change, the CLI, HTTP control
plane, scheduler, workflow executor and A2A ingress all keep requiring a build.

---

## 4. NAMED GAPS → PACT CONSTRUCTS

The assignment named four gaps. **Two of them are already closed.** Corrected map:

| Named gap | Actual status (verified) | PACT construct |
|---|---|---|
| **Eval manifest kind** | **Already exists** — `src/eval.rs:16-165`, CLI `bin/bud.rs:480`, 8 deterministic graders. Gap analysis never named it (`runtime-gap-analysis.md` has 2 "eval" hits, lines 105/108). | `kind: Eval` **superset**: keep the 8 graders as `pact:` provider metrics; add `deepeval:*` metric URIs (D6), `datasets/`, per-metric thresholds, SLO predicates, rubrics, and the five D19 on-ramps desugaring into one document model. |
| **Registry versioning** | **Mostly closed** — namespaces, immutable coordinates, dependency preflight, cycle detection, CAS activation/rollback, governance states, health TTL all exist (`registry-and-portability.md:68-115`, `:616-625`). **Still open:** "registration replaces the single active record for an id" — no simultaneous installed versions (`runtime-gap-analysis.md:177-183`). | PACT supplies the *authoring-side* half the registry lacks: `metadata.version` + `metadata.namespace` on the manifest, and a `pact.lock` that pins `(agent, variant, model, adapter, runtime, tools)` to exact coordinates. PACT must **not** build multi-version activation — D24 says that is AgentZero's. |
| **Feedback events** | **Already exists** — `kind: EventSubscription` (`src/event_subscription.rs:40-94`) with CloudEvents-shaped filter, agent/workflow targets, retry+lease, concurrency, maxPending. Gap-analysis line `:193-196` is stale. | PACT construct: `kind: EventSubscription` carried forward **plus** a `learning` binding — an event subscription whose target is the optimizer, filtered on eval-failure and guardrail-block event types. That is how T6/O5.3's trace→eval promotion becomes no-code (D14). |
| **Workflow-v2** | **Partially closed.** Present: bounded graph, conditions, cycles with `maxTransitions`, `foreach` fan-out with overflow/missing policy, 7 reducers, human review, command nodes, subgraphs, retries with seeded jitter, saga compensation types (`WorkflowSagaPolicy`, `WorkflowCompensation`, `WorkflowStepForwardFailurePolicy` — `lib.rs:4509-4530`, `:4778-4798`). **Still open (`runtime-gap-analysis.md:152-154`):** explicit event triggers, richer state-schema validation, dedicated tool/function/router node kinds. | PACT Loop IR + Topology IR: add node kinds `tool`, `function`, `router`, `ensemble` (self-consistency/best-of-N), and `verify`; keep the existing 5 kinds unchanged. Event triggers come from `EventSubscription` targeting a workflow — the plumbing already exists (`event_subscription.rs:79-84`). |

**Two further gaps PACT should claim** (not in the assignment list but named in
source):
- *Guardrail ordering vs tool approval* — "Ordering relative to tool approval must
  be explicit" (`runtime-gap-analysis.md:188-190`). PACT should make stage ordering
  normative: `input → modelInput → [provider] → modelOutput → toolInput →
  [approval] → [dispatch] → toolOutput → handoff/graphTransition → output`.
  *(INFERRED ordering from the stage names and `AgentGuardrailPolicy::for_stage`;
  I did not find a single source location that states the full order.)*
- *Blackboard as a topology* — memory has a blackboard with reducers
  (`scoped-agent-memory.md:100-114`) but no Team strategy uses it. PACT's
  blackboard pattern (AC-5.1) should be a Team strategy over the existing memory
  primitive, not a new store.

---

## 5. MIGRATION PLAN — RISKS, BREAKS, SHIMS, DUAL-READ

### 5.1 What breaks (hard, verified)

| # | Break | Evidence | Severity |
|---|---|---|---|
| B1 | **Every PACT-only field is a validation error on the old binary.** Unknown fields rejected at root/metadata/spec. There is no `x-` escape. | `manifest_compiler.rs:49-67`, `:141`, `:152`, `:158` | Blocking — old and new manifests cannot coexist in one file |
| B2 | **`apiVersion` change invalidates the generated SDK schema bundle.** `BudAgentManifest.apiVersion` is a JSON-Schema `const` of `bud.dev/v1`. | `sdk_codegen.rs:11040`, `lib.rs:51-52` | Blocking for Python/TS clients |
| B3 | **`metadata.version` does not exist**, so a PACT agent's version has nowhere to go in a bud manifest, and both exporters emit a hardcoded `1.0.0`. | `manifest_compiler.rs:3435`, `:3667` | Major — versioned A2A cards change |
| B4 | **Name slugification is lossy and namespace-free.** `Release Reviewer` → `release-reviewer`; two distinct PACT namespaced names can collide. | `runtime_validation.rs:1405-1441` | Major — silent identity merge |
| B5 | **`spec.runtime.kind` must be `goose`.** Any PACT manifest naming another substrate fails validation. | `declarative_normalization.rs:5173-5175` | Blocking for adapters |
| B6 | **The Goose-source round trip is lossy for `spec.budgets`.** `bud_agent_source_metadata` emits apiVersion, runtime, kind, runtimeConfig, model, tools, toolPolicy, toolPermissionProjection, agentTools, skills, capabilities, handoffs, permissions, displayName, output, guardrails — **not `budgets`, not `skills.define`**. The importer *does* read `skillDefinitions` (`:2203-2209`) but nothing ever writes it. | writer `manifest_compiler.rs:3046-3074`; reader `:2063-2135`, `:2195-2211` | Major — `.agents/agents/*.md` → manifest silently drops budgets |
| B7 | **Materialised packages are byte-checked.** `check_agent_package` re-derives every artifact and byte-compares. Any PACT change to recipe/card/OSSA generation invalidates every existing package. | `agent_package.rs:242-257` | Major — all packages must be re-materialised |
| B8 | **Package digests change**, so signatures over them break, so `require_verified_signature` installs fail. | `package_trust.rs:99-128`; policy `sdk-and-declarative-dev.md:2890-2899` | Major — re-signing campaign required |
| B9 | **Registry `revision` changes** if entry-derived data changes, forcing re-publication and breaking pinned A2A card URLs (`?targetVersion=&targetRevision=`). | `registry-and-portability.md:74-83`, `:578-585`, `:627-632` | Major — pinned remote callers 404 |
| B10 | **`permissions.mode` semantics were never real.** Any migration that "faithfully preserves" them ports a fiction. | `goose_adapter.rs:34386-34395` | Moderate — but a correctness trap if unnoticed |
| B11 | **Team `sequential` implicit `needs` wiring.** A converter that drops the implicit edge changes execution order. | `declarative_normalization.rs:147-149` | Moderate |
| B12 | **`includeGuideSkill` defaults to true**, so blueprint-authored agents carry an injected skill; a naive port either loses it (behaviour change) or carries it forever (F-1 violation). | `lib.rs:4117-4118` | Moderate |
| B13 | **Alias explosion.** `AgentBlueprint` accepts ~30 alias spellings. A strict PACT parser rejects real user files. | `lib.rs:3959-4119` | Moderate — needs an alias table in the converter |
| B14 | **Dual placement** (`spec.x` also accepted at root) doubles the converter's input space. | `manifest_compiler.rs:140` | Minor but must be handled |

### 5.2 What needs a shim

| Shim | Contract |
|---|---|
| **S1 — `bud.dev/v1 → pact.dev/v1` converter** | Pure, offline, total on the existing corpus. Emits a `ConversionReport` in the `ExportReport` shape already defined (`registry-and-portability.md:1178-1186`: `target, exact_fields, scaffolded_fields, lossy_fields, unsupported_fields, runtime_requirements`). Must fan `spec.runtime` out five ways (§1.1.8). |
| **S2 — `pact.dev/v1 → bud.dev/v1` down-converter** | Needed for the dual-read window. Fails closed on: non-goose substrate, variants, capability predicates, non-deterministic eval metrics, I/O modality other than text. Each failure is an `unsupported_fields` entry, never a silent drop (T7). |
| **S3 — `apiVersion` dispatch in the loader** | One entry point reads `apiVersion` and routes to the v1 normalizer or the PACT loader. Mirrors the existing OSSA `apiVersion.starts_with("ossa/")` check (`manifest_compiler.rs:3282-3286`). |
| **S4 — `x-bud-legacy` preservation block** | Everything the converter cannot map (unknown `spec.runtime.*` keys, `permissions.rules`, blueprint-only fields) lands in a PACT `x-` block that round-trips (AC-1.3). |
| **S5 — Goose-source frontmatter v2** | Extend `bud_agent_source_metadata` to emit `budgets` and `skillDefinitions` **before** migration begins, so the `.md` round trip stops losing data (fixes B6 independently of PACT). |
| **S6 — Digest/revision bridge** | Publish, for one release, both the old package digest and the new authored-file digest on each entry, so signature verification and pinned cards keep working through the cutover. |
| **S7 — `bud_universal_agent` run backend** | New `BudRunPlan.backend` value planning from a manifest path with no recipe precondition (§3.3). This is the change that actually delivers D2. |

### 5.3 What must be dual-read during transition

1. **Manifest ingress.** Every place that calls `normalize_agent_manifest` must
   accept both apiVersions: `manifest_compiler.rs:126`; SDK payload path
   `sdk_codegen.rs:6435`; runner validation `runner.rs:3074`; package load
   `run_planning.rs:3195`; registry entry build `registry_sources.rs:387`;
   Goose-source import `manifest_compiler.rs:2063`.
2. **Registry entries.** `RegistryEntry.metadata` is a flat
   `BTreeMap<String,String>` (`crates/bud-agent-types/src/lib.rs:783-784`) — a
   `pactApiVersion` key can carry the format marker without a schema change.
   *(INFERRED: I verified the type is an open string map; I did not find an
   existing key with that name.)*
3. **Package roots.** Recognise both `agent.bud.yaml` and `agent.yaml` in
   `local_bud_package_registry_entry_with_producer_context`
   (`registry_sources.rs:387`), `local_package_manifest`
   (`run_planning.rs:3196`), and `bundled_subagent_package_dirs`
   (`registry_sources.rs:1402`).
4. **Eval manifests.** `normalize_eval_manifest` (`eval.rs:327`) currently
   defaults `kind` to `"Eval"` and hard-checks it at `:1470`; dual-read means
   accepting PACT eval documents whose graders include non-deterministic metric
   URIs, and rejecting those on the v1 path with a named error.
5. **A2A cards.** Serve v1-shaped cards (`version: "1.0.0"`, hardcoded modes)
   until every known consumer is upgraded; then switch to
   `metadata.version` + real `defaultInput/OutputModes`. Because cards are
   ETag-cached with `max-age=60` (`registry-and-portability.md:1041-1043`), the
   switch is observable within a minute — schedule it deliberately.
6. **Run ledger.** No dual-read needed — `BudRunPlan` has no apiVersion field and
   is format-agnostic (`lib.rs:8255`). This is a genuine piece of luck: the
   ledger survives the migration untouched.

### 5.4 Verification plan for the superset claim (D3)

The corpus to convert is enumerable and small:
- fixtures under `tests/agent_manifest.rs`, `tests/sdk_types.rs`,
  `tests/sdk_schema.rs`, `tests/eval.rs`, `tests/cli.rs` (all match
  `grep -l "bud.dev/v1"`);
- every `.bud/agents/packages/*/agent.bud.yaml` produced by
  `materialize_agent_package`;
- the generated schema bundle itself (`sdk_codegen.rs:19-22`) — converting the
  **schema** and diffing required/optional sets is a cheap mechanical proof that
  no field was dropped.

Proposed gate: `pact convert --from bud.dev/v1 <corpus>` must produce, for every
input, a document whose down-conversion (S2) re-normalises to a **byte-identical**
`BudAgentManifest` YAML — the same equality test `check_agent_package` already
performs (`agent_package.rs:242-249`).

---

## 6. EVIDENCE INDEX (quick lookup)

| Claim | Location |
|---|---|
| `BUD_API_VERSION` | `src/lib.rs:51` |
| `BudAgentManifest` / `AgentMetadata` / `AgentSpec` | `src/lib.rs:3644` / `:3652` / `:3663` |
| Accepted spec fields, unknown-field rejection | `src/manifest_compiler.rs:8-31`, `:49-67` |
| `normalize_agent_manifest` | `src/manifest_compiler.rs:126-283` |
| `ToolPolicy` / permission projection | `src/lib.rs:3709` / `src/manifest_compiler.rs:3076-3106` |
| Guardrail policy (8 stages) / guardrail record | `src/lib.rs:3782-3799` / `:3822-3861` |
| Guardrail evaluators / actions | `src/declarative_normalization.rs:4411` / `:4418-4426` |
| `AgentBudgetPolicy` (7 dims) | `src/policy_runtime.rs:753-782` |
| `normalize_model` | `src/declarative_normalization.rs:3041-3097` |
| `modelSettings` whitelist | `src/declarative_normalization.rs:2632-2677` |
| `normalize_permissions` (mode-only) | `src/declarative_normalization.rs:3996-4016` |
| `normalize_runtime` (goose-only) | `src/declarative_normalization.rs:5164-5220` |
| Loop policy `bud.loop.v1` | `src/declarative_normalization.rs:5222-5385`, `src/lib.rs:3684-3707` |
| `runtime.subagents` | `src/manifest_compiler.rs:1636-1720` |
| Team strategies (11) | `src/declarative_normalization.rs:110-134` |
| Team → workflow compilation | `src/manifest_compiler.rs:538-553` |
| Workflow step kinds / condition ops / reducers | `src/declarative_normalization.rs:956-976` / `:1968-2005` / `:1754` |
| Workflow retry + seeded jitter | `src/lib.rs:4811-4901` |
| Schedule cron/timezone/concurrency | `src/agent_package.rs:367-489` |
| `BudEvalManifest` + 8 graders | `src/eval.rs:16-129` |
| `BudEventSubscriptionManifest` | `src/event_subscription.rs:40-94` |
| `materialize_agent_package` | `src/agent_package.rs:3-86` |
| `check_agent_package` (byte-equality) | `src/agent_package.rs:193-261` |
| Package digest / signature payload | `src/package_trust.rs:99-128` |
| A2A card export | `src/manifest_compiler.rs:3656-3702` |
| `a2a_skills` (facade ids) | `src/portability.rs:2043-2117` |
| `autonomy_level` | `src/portability.rs:2031-2041` |
| OSSA export + `x-bud` | `src/manifest_compiler.rs:3419-3503` |
| Secret-config guard | `src/portability.rs:1686-1710` |
| Goose recipe compile + `bud_prompt` | `src/manifest_compiler.rs:1821-1919` |
| Goose source frontmatter (writer/reader) | `src/manifest_compiler.rs:3046-3074` / `:2063-2135` |
| Recipe-artifact precondition (D2 breaker) | `src/run_planning.rs:2447-2473` |
| Manifest-direct execution (D2 enabler) | `src/goose_adapter.rs:9970-9983`, `:27509-27516` |
| Tool-policy enforcement inspector | `src/goose_adapter.rs:33990-34060` |
| `permissions.mode` → GooseMode::Chat only | `src/goose_adapter.rs:34386-34395` |
| `BudRunPlan` / lineage / interrupts / checkpoints / artifacts | `src/lib.rs:8255` / `:8355` / `:8475` / `:8504` / `:8524` |
| Run authorization evidence chain | `src/run_authorization_evidence.rs:361-403` |
| `RegistryEntry` / `RegistrySelector` / `BudAgentRecord` | `crates/bud-agent-types/src/lib.rs:756` / `:903` / `:679` |
| Release coordinate | `crates/bud-agent-types/src/lib.rs:960-966` |
| Access envelope constants | `crates/bud-agent-types/src/lib.rs:5-14` |
| Default agents workspace | `src/bin/bud.rs:9294` |
| `bud agents` subcommands | `src/bin/bud.rs:6056-6079` |

---

## 7. OPEN QUESTIONS FOR THE ARCHITECTURE DOC

1. Does the PACT canonical digest **become** the registry revision, or do the two
   coexist in `pact.lock`? (Affects B9 and every pinned A2A card URL.)
2. Is `AgentBlueprint` deleted, or preserved as a PACT profile/template? D14 argues
   for deletion; the existing SDK surface argues for preservation.
3. Does PACT own a **trace store** (needed for T6 learning) given the run ledger
   deliberately excludes prompts and raw output?
4. Is `kind: Channel` specified by PACT or declared out of scope under D24?
5. Where does `spec.permissions.mode` land once it is admitted to be non-enforcing
   — a profile default that expands into the tool-permission projection, or a
   deprecated field with a converter warning?
6. Does PACT's `metadata.name` allow `/` (namespace) — which today is a hard
   validation error (`runtime_validation.rs:1415-1419`) — or does namespace get its
   own field?
