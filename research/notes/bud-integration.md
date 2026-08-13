# Research stream: `bud-integration`

**Question (D3):** PACT replaces `bud.dev/v1`. What exactly does that require?

**Date of this pass:** 2026-08-07. **Supersedes** the 2026-07-26 pass of this
file, which is now line-stale (`src/lib.rs` 15 593 → 16 096, `manifest_compiler.rs`
3 702 → 3 899, `declarative_normalization.rs` 6 381 → 6 830, `goose_adapter.rs`
44 561 → 48 225 between the two passes). **Every line number below was
re-verified against the tree at `1a91f50`.**

**Method.** Rust source first, design docs second, and — new in this pass — the
**actual `bud` binary** (`target/debug/bud`, built from this tree) used to
execute the claims. Where docs and source disagree, source wins and the
disagreement is a finding. Where source and *observed behaviour* could disagree,
observed behaviour wins. Claims marked `LIVE` were executed; `INFERRED` marks
anything I reasoned to rather than read or ran.

**Read in source:** `src/lib.rs`, `src/manifest_compiler.rs`,
`src/declarative_normalization.rs`, `src/eval.rs`, `src/policy_runtime.rs`,
`src/portability.rs`, `src/memory.rs`, `src/registry.rs`, `src/registry_sources.rs`,
`src/run_planning.rs`, `src/agent_package.rs`, `src/package_trust.rs`,
`src/event_subscription.rs`, `src/sdk_codegen.rs`, `src/runner.rs`,
`src/runtime_validation.rs`, `src/run_authorization_evidence.rs`,
`src/goose_adapter.rs` (targeted), `src/bin/bud.rs` (targeted),
`crates/bud-agent-types/src/lib.rs`,
`/home/bud/ditto/gaia-ai-runtime/goose/crates/goose-provider-types/src/goose_mode.rs`.
**Docs read:** `sdk-and-declarative-dev.md`, `registry-and-portability.md`,
`runtime-gap-analysis.md`, `scoped-agent-memory.md`, `durable-agent-mailboxes.md`,
`architecture.md` (targeted).

---

## 0. Headline results

1. **`AgentSpec` has grown to 13 fields, not 11.** `spec.context`
   (`AgentContextPolicy { moim }`) and `spec.security`
   (`AgentSecurityPolicy { promptInjection, promptInjectionThreshold, egress,
   adversary }`) are new since the last pass (`src/lib.rs:3857-3879`,
   `:4046-4125`). Both normalize (`LIVE`). PACT's superset obligation is over 13
   spec fields.

2. **`permissions.mode` is no longer decorative — it is now actively
   *misleading*.** Since the "E-C fix", all four Goose modes map at session start
   (`goose_adapter.rs:35844-35855`). But the **documented vocabulary does not
   intersect the implemented one**: `ask`, `readonly`, `accept_edits`,
   `deny_unapproved`, `bypass` (`sdk-and-declarative-dev.md:2126-2128`) all fall
   through `_ => GooseMode::default()`, and `GooseMode::default()` is **`Auto` —
   "Automatically approve tool calls"**
   (`goose/crates/goose-provider-types/src/goose_mode.rs:24-27`). The manifest's
   own default is `{"mode":"ask"}` (`manifest_compiler.rs:252`). **Therefore the
   default Bud agent starts in auto-approve mode while its manifest says `ask`
   and its OSSA export says `autonomy.level: supervised`
   (`portability.rs:2035-2044`).** This is the single sharpest governance-honesty
   defect in the format PACT replaces, and PACT must not port `mode` forward as
   though it meant anything.

3. **The runtime already implements "a declaration that cannot be enforced is a
   refusal, not a warning" — but only for tool policy.**
   `refuse_tool_policy_on_dispatch_owning_provider` (`goose_adapter.rs:35306-35331`)
   hard-fails a run when the provider dispatches its own tools, naming the exact
   manifest fields (`ToolPolicy::declared_permission_rule_fields`,
   `lib.rs:3957-3969`); `seed_bud_session_tool_policy_permissions`
   (`:35334-35361`) hard-fails an un-boundable `tools.deny` pattern. **This is the
   T7 posture PACT wants and it already exists — PACT should generalise it to
   every declared control.** The same runtime silently discards `spec.context` in
   its own documented shape (§1.1.9, `LIVE`).

4. **`apiVersion` is not validated on Agent, Team, Workflow, or Schedule.**
   `string_or_default(root.get("apiVersion"), BUD_API_VERSION, "apiVersion")`
   (`manifest_compiler.rs:265`, `:424`, `:527`, `:1506`) passes any string
   through. **`LIVE`: a document declaring `apiVersion: pact.dev/v1` normalizes
   cleanly as a `bud.dev/v1` Agent and round-trips carrying the PACT version
   string.** Only `Eval` (`eval.rs:1468-1473`) and `EventSubscription`
   (`event_subscription.rs:841-844`) validate. **This is fail-open and is the
   number-one migration hazard: a half-migrated tree runs under v1 semantics
   while claiming PACT.**

5. **D2 is violated on *every* execution path, including the one the last pass
   thought was clean.** `BudRunner::plan` (`runner.rs:1898-1909`) and
   `prepare_universal_agent_run` (`goose_adapter.rs:14450-14453`) both call
   `materialize_and_register_agent…` before planning. `LIVE`: `bud agents run
   sec.yaml --workspace ws` wrote `README.md`, `agent.bud.yaml`,
   `.well-known/agent-card.json`, `recipes/sec-agent.goose.yaml`,
   `portable/agent.ossa.yaml`, `.agents/agents/sec-agent.md` into
   `ws/packages/.bud-package-objects/<digest>/` and a full `registry.json`
   entry, *before* execution. The **only** manifest-direct path is the library
   API `BudUniversalAgentRuntime::create_agent(&BudAgentManifest, working_dir)`
   (`goose_adapter.rs:10387-10400`) / `::run` (`:10402-…`), which never touches
   the runner, registry, or recipe.

6. **There is no filesystem discovery of Bud agents, and the documented one does
   not exist.** `registry-and-portability.md:287` claims Bud manifests are
   discovered at `.bud/agents`, `.agents`, explicit paths, and `:304-331` shows
   `.agents/<name>/agent.yaml`. **The string `agent.yaml` appears nowhere in the
   Rust source** — only `agent.bud.yaml` (`registry_sources.rs:387`,
   `run_planning.rs:3205`, `:3227`, `registry_sources.rs:1402`,
   `agent_package.rs:14`). The only recursive scans are for Goose artifacts
   (`registry.rs:1741/1856/1974/2099`) and bundled subagent packages
   (`registry_sources.rs:1379-1408`).

7. **The generated SDK schema has already drifted from the Rust type.**
   `bud_agent_manifest_schema()` (`sdk_codegen.rs:11069-11117`) and
   `BudAgentManifestInput` (`:11030-11066`) omit `spec.context` and
   `spec.security`, and `strict_sdk_object` sets `additionalProperties: false`
   (`:24373-24377`). **Two live manifest fields are invisible to — and rejected
   by — every generated Python/TS client.** PACT must derive schema and type from
   one source or inherit this class of bug.

8. **The flagship declarative example in the design doc does not validate.**
   `LIVE`: `sdk-and-declarative-dev.md:281-320` ("Canonical Declarative Shape")
   fails with `Agent manifest contains unsupported field at spec.memory`. With
   `spec.memory` removed it passes — but `spec.runtime.goose` is warned and
   ignored, and `output: {text: true}` is accepted as a JSON Schema. Do not treat
   the doc examples as a specification of behaviour.

9. **The Goose-source round trip now silently drops four fields, not two.**
   `LIVE`: export → import of a manifest carrying `context`, `security`, and
   `budgets` returns a manifest with all three gone and **no warning**.
   `bud_agent_source_metadata` (`manifest_compiler.rs:3071-3099`) emits neither
   `budgets`, `skills.define` (`skillDefinitions`), `context`, nor `security`;
   the importer reads `skillDefinitions` (`:2226`) that nothing writes. OSSA and
   A2A exports drop the same three (`LIVE`).

10. **`kind: Channel` still does not exist**, despite the recent
    "apps.* and channels.*" HTTP-method restoration (`6a56d45`). No
    `BudChannelManifest`, no `normalize_channel_*` anywhere in `src/` or
    `crates/`. Channels remain registry descriptors only.

11. **The gap analysis (2026-07-19) is stale in PACT's favour on three of five
    counts.** It says guardrails are "only contains/regex" and there is "no
    general run cost budget" (`runtime-gap-analysis.md:110`); the tree has 8
    guardrail stages × 3 evaluator kinds and a 7-dimension budget policy. It says
    "event subscriptions … do not [exist]" (`:111`, `:194-196`);
    `src/event_subscription.rs` is 6 850 lines. It says saga compensation remains
    (`:106`, `:152`); `WorkflowSagaPolicy` / `WorkflowCompensation` exist
    (`lib.rs:4856-4879`). **Do not design PACT against that list.**

---

## 1. COMPLETE FIELD INVENTORY OF `bud.dev/v1`

### 1.0 Kind census (authoritative)

| Kind | Rust type | Normalizer | `apiVersion` required? | Strictness |
|---|---|---|---|---|
| `Agent` | `BudAgentManifest` `lib.rs:3839` | `normalize_agent_manifest` `manifest_compiler.rs:128` | **no — any string accepted** `:265` | unknown fields rejected at root/metadata/spec `:143`,`:154`,`:160` |
| `Team` | `BudTeamManifest` `lib.rs:4777` | `normalize_team_manifest` `manifest_compiler.rs:444` | **no** `:527` | rejected `:458`,`:469`,`:475` |
| `Workflow` | `BudWorkflowManifest` `lib.rs:4822` | `normalize_workflow_manifest` `manifest_compiler.rs:291` | **no** `:424` | rejected |
| `Schedule` | `BudScheduleManifest` `lib.rs:5316` | `manifest_compiler.rs:~1490` | **no** `:1506` | kind-checked |
| `Eval` | `BudEvalManifest` `eval.rs:16` | `normalize_eval_manifest` `eval.rs:327` | **yes — must equal `bud.dev/v1`** `eval.rs:1468-1473` | `deny_unknown_fields` on every struct |
| `EventSubscription` | `BudEventSubscriptionManifest` `event_subscription.rs:40` | `:685` | **yes — must equal `bud.dev/event-subscription/v1`** `:838-844` | allow-list `:691-713` |
| `UniversalGooseAgent` | — (Goose markdown frontmatter `bud.kind`) | `import_bud_universal_goose_agent_source` `manifest_compiler.rs:~2063` | — | projection of `Agent` |
| `AgentRecord` | `BudAgentRecord` `crates/bud-agent-types/src/lib.rs:679` | — | `bud.dev/agent-record/v1` (`:5`) | registry wire contract, **not authoring** |
| *(doc only)* `Channel` | — | **none exists** | — | `sdk-and-declarative-dev.md:2558`; **negative finding** |

`BUD_API_VERSION = "bud.dev/v1"` — `lib.rs:51`.
Sibling versioned contracts PACT inherits: `bud.dev/sdk-schema-bundle/v1` (`:52`),
`bud.loop.v1` (`:53`), `bud.dev/agent-record/v1`, `bud.dev/agent-access/v1`
(`crates/bud-agent-types/src/lib.rs:5,7`), `bud.dev/eval-report/v1` (`eval.rs:3`),
`bud.dev/eval-validation/v1` (`bin/bud.rs:659`),
`bud.dev/memory-space|record|revision|event|context|statistics/v1`
(`memory.rs:3-8`), `bud.dev/event-subscription/v1`, `bud.dev/event-activation/v1`
(`event_subscription.rs:5,7`), `bud.runner-package-tree.v2` (registry metadata,
`LIVE`).

**PACT consequence.** The "one apiVersion" story is already false: six version
strings coexist in the authoring surface alone. PACT should declare **one**
`pact.dev/v1` for all authoring kinds and keep sub-contract versions out of the
authored tree entirely.

---

### 1.1 `kind: Agent` — complete field table

Source of truth: `AgentSpec` (`lib.rs:3857-3879`) + the accepted-field allow-list
`AGENT_SPEC_FIELDS` (`manifest_compiler.rs:8-33`, **23 entries = 13 canonical +
10 aliases**) + the generated JSON schema (`sdk_codegen.rs:11069-11117`, which is
**already out of date**, see §5.1 B15).

Every `spec.*` key is *also* accepted at manifest root as a shorthand
(`manifest_compiler.rs:142`), and every `metadata.*` key likewise (`:132-141`).
Root and `spec` are checked against the **same** list, so `spec` may be omitted
entirely.

#### 1.1.1 Envelope

| Field | Req | Semantics (verified) | Evidence | PACT home |
|---|---|---|---|---|
| `apiVersion` | defaulted | `"bud.dev/v1"`; **not validated** — any string accepted and echoed | `manifest_compiler.rs:265`; `LIVE` | `apiVersion: pact.dev/v1`, **validated, dispatching** |
| `kind` | defaulted `"Agent"` | only `"Agent"` accepted | `manifest_compiler.rs:145-150` | `kind: Agent` |

#### 1.1.2 `metadata`

`AgentMetadata` = `{name, description, displayName?, aliases[]}` — `lib.rs:3847-3855`.

| Field | Req | Semantics (verified) | Evidence | PACT home |
|---|---|---|---|---|
| `metadata.name` | **required** | ≤80 chars in, no `/` or `\`, then `goose_slugify_agent_name`: every non-`[a-z0-9]` char → `-`, runs collapsed, trimmed, **truncated to 64**, empty → `"agent"` | `runtime_validation.rs:1481-1530` | `metadata.name` — **PACT must add `metadata.namespace`; `/` is a hard error today** |
| `metadata.description` | optional | defaults to `"Bud agent {name}."` | `manifest_compiler.rs:179-184` | same |
| `metadata.displayName` | optional | auto-filled with the pre-slug raw name when it differs — this is the *only* thing that preserves a non-ASCII name | `manifest_compiler.rs:169-177`; `LIVE`: `Análisis de Ventas` → name `an-lisis-de-ventas`, displayName preserved | same |
| `metadata.aliases` | optional | string or list; ≤128 entries (`MAX_AGENT_ALIAS_COUNT` `:3`), ≤256 bytes each (`:4`), no control chars, deduped; **error if given twice** (metadata + root) | `manifest_compiler.rs:71-126` | same |
| *(absent)* `metadata.version` | — | **does not exist**; hard error `LIVE`. Both exporters hardcode `"1.0.0"` (`manifest_compiler.rs:3748`, `:3516`) | — | **PACT MUST ADD** semver `metadata.version` |
| *(absent)* `metadata.namespace` | — | **does not exist**; namespacing is registry-side prefixing only (`bud:`, `goose/`, `a2a:`) | `registry_sources.rs:419` | **PACT MUST ADD** |
| *(absent)* `metadata.owner/labels/license` | — | present in the *design* `AgentRecord` sketch, absent from the manifest | `registry-and-portability.md:514-558` | PACT `metadata.owner`/`labels` |

#### 1.1.3 `spec` — the 13 canonical fields

| # | Field | Req | Semantics (verified) | Evidence | PACT home |
|---|---|---|---|---|---|
| 1 | `instructions` | **required** | free text; rejected if it contains Unicode Tags Block chars (hidden-prompt guard) | `manifest_compiler.rs:188-193` | Strategy → `instructions` / `instructions.md` |
| 2 | `model` | defaulted `"default"` | string **or** mapping; canonical keys `provider`, `name`, `thinking_effort`, `max_tokens`, `request_params` + arbitrary passthrough. `modelSettings` is an authoring alias erased into those | `declarative_normalization.rs:3139-3200`, `:2908-…` | split: Contract → capability predicates; Strategy → binding; `pact.lock` → pin |
| 3 | `tools` | defaulted empty | `ToolPolicy`, §1.1.4 | `lib.rs:3908-3938` | Strategy → tools; Policy → approval matrix |
| 4 | `skills` | defaulted empty | `SkillPolicy { use[], define[] }`, §1.1.5 | `lib.rs:4012-4018` | Resources → `skills/` |
| 5 | `capabilities` | optional | `[{name, description, tags[]}]`; strings accepted; duplicates merged. **This is what the agent *provides*, not what it requires.** | `lib.rs:4020-4028`, `declarative_normalization.rs:3551-…` | Contract → declared capabilities |
| 6 | `handoffs` | optional | `[{name, agent, description}]`; local names normalise to `bud:<slug>` | `lib.rs:4770-…`, `declarative_normalization.rs:3441-…` | Topology → handoff edges |
| 7 | `output` | optional | `{schema: <JSON Schema>}`. 6 root aliases + 8 inner aliases fold in. **`validate_output_schema` is weak: `{text: true}` is accepted** (`LIVE`) | `lib.rs:4030-4040`, `declarative_normalization.rs:4140-4176` | Contract → `io.output.schema`; PACT must add `io.input` |
| 8 | `guardrails` | optional | `AgentGuardrailPolicy`, **8 stages**, §1.1.6. Plus root shorthands `inputGuardrails`/`outputGuardrails` | `lib.rs:4127-4167`, `declarative_normalization.rs:4341-4441` | Policy → guardrails |
| 9 | **`context`** *(new)* | optional | `{moim: String}` only — a per-session "top of mind" string injected into every turn's `<turn-context>`. Aliases `topOfMind`/`top_of_mind`. String shorthand accepted. **Anything else in the object is silently dropped** | `lib.rs:4042-4064`, `declarative_normalization.rs:4178-4209`; `LIVE` | Strategy → per-turn context injection |
| 10 | **`security`** *(new)* | optional | `{promptInjection: bool, promptInjectionThreshold: 0.0–1.0, egress: log\|approve\|block → Log\|RequireApproval\|Deny, adversary: bool \| {enabled, policy}}`. Per-**session**, never process-global | `lib.rs:4066-4125`, `declarative_normalization.rs:4211-4339` | Policy → per-agent security posture |
| 11 | `budgets` | optional | `AgentBudgetPolicy`, **7 dimensions**, §1.1.7. Root alias `budget` | `policy_runtime.rs:755-782` | **Contract → operational SLO/budget** |
| 12 | `permissions` | defaulted `{"mode":"ask"}` | free-form mapping; **only `mode` is normalised**, everything else passes through **unvalidated and unenforced** | `declarative_normalization.rs:4118-4138`; `LIVE` | Policy — **but see §2.6; do not port `mode` as enforcement** |
| 13 | `runtime` | defaulted `{"kind":"goose"}` | mapping; `kind` **must** be `"goose"` (hard error); everything else cloned through with a warn-only unknown-key check, §1.1.8 | `declarative_normalization.rs:5450-5535` | Substrate + 5-way fan-out |

Cross-cutting: `validate_no_embedded_secret_config` on `model`, `permissions`,
`runtime` (`manifest_compiler.rs:260-262`) rejects secret-like keys and
`Bearer …` strings. **PACT must keep this: no credential material in the tree,
ever.**

#### 1.1.4 `spec.tools` — `ToolPolicy` (`lib.rs:3908-3938`)

| Sub-field | Aliases | Semantics |
|---|---|---|
| `available` | `allow`, `use` | what the model can see/call |
| `autoApprove` | `auto_approve`, `allowed_tools`, `allowedTools` | runs without interrupt → Goose `always_allow` |
| `requireApproval` | `require_approval` | forces interrupt → `ask_before` |
| `deny` | `hide`, `disallowed_tools`, `disallowedTools` | blocked pre-approval → `never_allow`; entries with `:` or whitespace are **patterns** |
| `agents` | — | `[{name, agent, description, delegateSource?}]` agent-as-tool bindings (`lib.rs:4760-4768`) |

Enforced invariants PACT must preserve:
- a name may not appear in two of `{autoApprove, requireApproval, deny-exact}`;
- each alias family may be given **once only** (`allow:` + `available:` = error);
- tool refs may not contain whitespace; `ns__tool` requires both halves
  (`runtime_validation.rs:~1560`);
- **an argument-scoped `deny` pattern with no tool selector and no non-empty
  `available` surface is a hard refusal**, not a warning
  (`goose_adapter.rs:35341-35354`).

Stable audit projection: `BudToolPermissionProjection {kind, target, permission,
source}` (`lib.rs:4003-4010`), built by `tool_policy_permission_projection`
(`manifest_compiler.rs:3101-3131`). **This is the real permission model. PACT
should adopt it verbatim as the normative approval matrix and make
`permissions.mode` desugar *into* it.**

#### 1.1.5 `spec.skills` — `SkillPolicy` (`lib.rs:4012-4018`)

- `use[]` — Goose skill names. **WS1 change:** names now resolve against on-disk
  skill directories via `resolve_use_skill_definitions(manifest, resolve_dir)`
  (`manifest_compiler.rs:3223-3260`), called at `goose_adapter.rs:28621` with the
  registry's `gooseSkillPath` lookup. **Warn-only**: an unresolved name is skipped
  with a diagnostic; `define` wins a name collision.
- `define[]` — `SkillDefinition {name, description, instructions,
  supportingFiles[{path, contents}]}` (`lib.rs:4210-4230`); materialised to
  `.agents/skills/<name>/SKILL.md` + files (`agent_package.rs:23-36`); readable
  back with `skill_definition_from_directory` (`lib.rs:4254-4272`).

**This pair is the Expansion Rule in miniature *and* the AC-6.2
bind-to-what-the-runtime-owns mechanism, both already shipping.** PACT should
generalise `resolve_use_skill_definitions` into the normative
reference-resolution hook, and should **not** keep it warn-only (T7).

#### 1.1.6 `spec.guardrails` — 8 stages × per-guardrail record

Stages (`lib.rs:4127-4146`, dispatcher `:4155-4166`):
`input` · `modelInput` · `modelOutput` · `toolInput` · `toolOutput` · `handoff` ·
`graphTransition` · `output`.

`AgentGuardrail` (`lib.rs:4169-4208`):

| Field | Default | Values | Evidence |
|---|---|---|---|
| `name` | auto `guardrail-N` | slugified | `declarative_normalization.rs:4489-4494` |
| `evaluator` | `deterministic` | `deterministic \| sdk_callback \| model_judge` | `:4693-4701` |
| `match` | — | `contains \| regex`; `contains:`/`regex:` shorthands | `:4541-4560` |
| `pattern` | — | required for deterministic | `:4541-…` |
| `message` | — | required | `lib.rs:4182` |
| `caseSensitive` | `false` | | `lib.rs:4183-4184` |
| `action` | `block` | `block \| reject_content \| replace \| require_approval \| defer` | `:4703-4711` |
| `replacement` | — | `replace` only | |
| `callback` | — | iff `sdk_callback`; `[A-Za-z0-9_.-]{1,128}` | `:4721-4733` |
| `model`, `prompt` | — | `model_judge` only | `:4735-…` |
| `failureMode` | `block` | `block \| allow` (fail-closed default) | `:4713-4719` |
| `timeoutMs` | `30000` | | `lib.rs:4203-4207` |

A bare string is accepted and becomes `{contains, action: block, message:
"Guardrail blocked this request."}` (`:4475-4491`) — a genuinely no-code on-ramp.

**PACT must keep the exact 8-stage vocabulary.** Adding stages is additive;
removing any is a migration break. The **ordering** relative to tool approval is
still undocumented (`runtime-gap-analysis.md:188-190`) — PACT should make it
normative.

#### 1.1.7 `spec.budgets` — `AgentBudgetPolicy` (`policy_runtime.rs:755-782`)

`wallClockMs` · `turns` · `modelTokens.{input,output,total}` · `toolCalls` ·
`providerCostMicros` · `handoffs` · `childRuns`. All `Option<u64>`.

Runtime accounting: `BudRunBudgetUsage` (`:784-…`), `BudRunBudgetReservation`,
`BudRunBudgetState` with `apiVersion`, `rootRunId`, deadline, reservations, and a
`providerCostUnknown` flag. Run plan carries `budget` + `budgetRecords`
(`lib.rs:8669-8671`).

**PACT's SLO object must be a strict superset of these 7 and must keep the
reservation/accumulator model.** Missing and required by D16/O4.2: TTFT, TPOT,
percentile semantics, per-modality budgets, throughput. Those are pure additions.

#### 1.1.8 `spec.runtime` — the open substrate object

`normalize_runtime` (`declarative_normalization.rs:5450-5535`):
- `kind` must be `"goose"` — **hard error otherwise (`:5459-5461`). The single
  biggest lock-in point in the entire format.**
- `container`, `loop` are normalised; `dockerContainer`/`docker_container`/
  `agentLoop`/`agent_loop` are import aliases removed after folding.
- **Every other key is cloned through**, with a `tracing::warn!` if not in
  `KNOWN_RUNTIME_KEYS` = `{kind, container, dockerContainer, docker_container,
  loop, agentLoop, agent_loop, subagents, gooseRecipe, background, mcpServers,
  mcp_servers, enabled}` (`:5508-5533`).

| Key | Semantics | Evidence | In `KNOWN_RUNTIME_KEYS`? |
|---|---|---|---|
| `kind` | must be `goose` | `:5459` | yes |
| `loop` | `{kind: goose\|custom, protocol: "bud.loop.v1", maxIterations 1..=1024 (default 64), label ≤128B, executor{id ≤128 `[A-Za-z0-9._:/-]`, revision `sha256:<64 lowercase hex>`}}` | `:5537-5700`, `lib.rs:3882-3906` | yes |
| `container` | id \| `false` \| `null` \| `{id, engine, scope, appliesTo, developerTools}` | `:5741-6065` | yes |
| `mcpServers` | Goose extension configs → recipe `extensions` | `manifest_compiler.rs:1867` | yes |
| `subagents[]` | `[{manifest, package{path}} \| {budAgentToolProxy{schemaVersion, toolName}}]` — native nesting; **rejects graphs deeper than 5 levels** | `manifest_compiler.rs:1651-…`; `sdk-and-declarative-dev.md:498-501` | yes |
| `gooseRecipe` | import-preservation block (prompt, parameters, extensions, sub-recipes, …) | `manifest_compiler.rs:1894-…` | yes |
| `background` | **accepted, warned, and ignored — explicitly not implemented** | `:5524-5527` | yes |
| **`memory`** | scoped-memory declaration — shorthand `session\|run\|agent\|agent_release\|user\|project\|team\|workspace\|organization\|false`, or `{stores[≤32], context{maxRecords, maxBytes, query: recent_user_text\|none}}`. **Real and parsed** at `memory.rs:1435-1439` | `memory.rs:1454-1556` | **NO — warns "possible typo" while being honoured** |
| `gooseCustomAgent` | import provenance (`source`, `compatibility`, `path`, `instructionHash`) — **written by the runtime itself** | `manifest_compiler.rs:~2100`; `LIVE` | **NO — the runtime warns about its own output** |
| `portable.unsupported` | OSSA import loss record | `registry-and-portability.md:1191` | NO |
| `hooks`, `smartApprove`, `runState` | passthrough; each produces an OSSA export warning | `portability.rs:1820-1836` | NO |

**PACT consequences.**
1. `spec.runtime` does **five unrelated jobs**: substrate binding (`kind`,
   `container`), execution semantics (`loop`), resource declaration (`mcpServers`,
   `memory`, `subagents`), import provenance (`gooseRecipe`, `gooseCustomAgent`,
   `portable`), and dead config (`background`, `hooks`, `smartApprove`,
   `runState`). **The converter needs a five-way fan-out rule, not a rename.**
2. There is **no single registry of runtime keys**, so the warn list has already
   drifted from the parse list. PACT's equivalent must be one table used by both
   the validator and the reader, or this recurs.

#### 1.1.9 Documented-but-not-real `spec` shapes (all `LIVE`-tested)

| Documented shape | Doc line | Actual behaviour |
|---|---|---|
| `spec.memory: {session: goose}` | `sdk-and-declarative-dev.md:311-312` | **hard error** `Agent manifest contains unsupported field at spec.memory` |
| `spec.runtime.goose: {session, apps}` | `:313-316` | warn `not a recognized runtime option and is ignored`; **preserved verbatim in the canonical manifest and never read** |
| `spec.output: {text: true}` | `:319-320` | **accepted** as `output.schema: {text: true}` — a nonsense JSON Schema |
| `spec.policy: {toolOrigin, packageTrust}` | `:2141-2148` | **hard error** — `policy` is not in `AGENT_SPEC_FIELDS` |
| `spec.security: {promptInjection: {enabled, action}}` | `:2149-2153` | **hard error** `spec.security.promptInjection must be a boolean` — the real shape is a bare bool |
| `spec.context: {hints, persistent, compaction, promptTemplates}` | `:2186-2196` | **validates clean and is silently discarded in full** — `normalize_context` reads only `moim` |
| `spec.permissions.rules.{allow,ask,deny}` | `:2129-2137` | **preserved verbatim in the canonical manifest, surfaced by `normalize`, and enforced by nothing** |
| `permissions.mode: readonly` | `:2126` | not a match arm → `GooseMode::Auto` (auto-approve) while OSSA exports `autonomy.level: supervised` |

**This table is the strongest single argument for PACT's "every field has a
reader" test.** Three distinct failure modes coexist in one format: hard reject,
silent drop, and preserve-but-never-read. The third is the worst — an operator
reading `bud agents normalize` sees a deny rule that does not exist.

---

### 1.2 `kind: Team` — field table

`BudTeamManifest` `lib.rs:4777-4819`; `TEAM_SPEC_FIELDS = {strategy, manager,
members, agents, shared, state, policy}` (`manifest_compiler.rs:47-49`).

| Field | Semantics | Evidence |
|---|---|---|
| `spec.strategy` | default `sequential`; **11 values**: `sequential, parallel, dag(=graph), manager, router, supervisor, debate, consensus, map_reduce(=mapreduce), mixture(=moa/mixture_of_agents), evaluator_optimizer(=optimizer_evaluator)` | `declarative_normalization.rs:114-138` |
| `spec.manager` | moderator ref; when omitted the **last member** is moderator | `manifest_compiler.rs:499-505` |
| `spec.members[]` (alias `agents`) | `TeamMember {id, agent, inlineAgent?: BudAgentManifest, role?, prompt?, needs[], retry?}` | `lib.rs:4805-4819`, `manifest_compiler.rs:509-513` |
| `spec.shared` | free `Value`; **also read from `spec.state.shared`** | `manifest_compiler.rs:513-518` |
| `spec.state` | **accepted, but only `state.shared` is read — the rest is silently dropped** | `manifest_compiler.rs:516` |
| `spec.policy` | free `Value` | `:519-523` |

`sequential` auto-wires `needs` to the previous member
(`declarative_normalization.rs:151-153`) — an **implicit edge** the converter
must either preserve or make explicit.

Compilation: `manager|router|supervisor` → a **manager `Agent`** with workers as
`tools.agents` (`compile_team_manager_agent` `manifest_compiler.rs:1017`,
predicate `:1140`); every other strategy → a `Workflow`
(`compile_team_workflow` `:544`, fan-in `:620`, evaluator-optimizer `:803`).

**Topology superset check against AC-5.1's eight patterns:** supervisor ✓,
hierarchical ✓ (nested subagents), sequential pipeline ✓, parallel map-reduce ✓,
swarm/handoff ✓ (`spec.handoffs`), debate ✓, **blackboard ~** (the memory
primitive exists — `BudMemoryRecordKind::Blackboard`, reducers `Set/MergePatch/
Append/Delete`, `memory.rs:71-105` — but no Team strategy uses it),
**market/auction ✗** (no antecedent). Two of eight are new work.

---

### 1.3 `kind: Workflow` — field table

`BudWorkflowManifest` `lib.rs:4822-…`; `WORKFLOW_SPEC_FIELDS`
(`manifest_compiler.rs:34-46`).

| Field | Semantics | Evidence |
|---|---|---|
| `spec.strategy` | `sequential \| parallel \| dag \| graph`(=`state_machine`) | `declarative_normalization.rs:101-112` |
| `spec.entrypoint` | graph start node | `lib.rs:4841-4842` |
| `spec.state` | initial durable JSON state | `lib.rs:4843` |
| `spec.stateSchema`, `spec.outputSchema` | JSON Schema | `lib.rs:4845-4848` |
| `spec.limits` | `WorkflowGraphLimits {maxTransitions, maxNodeExecutions, maxFanOut, maxConcurrency, maxStateBytes, maxSubgraphDepth, maxWorkflowDurationMs?, maxStepDurationMs?}` | `lib.rs:4880-4906` |
| `spec.saga` | `WorkflowSagaPolicy {compensateOn[], onCompensationError}` | `lib.rs:4856-4861` |
| `spec.steps[]` | `WorkflowStep`, below | `lib.rs:5056-5104` |

`WorkflowStep`: `id, kind, agent?, prompt?, needs[], next[WorkflowEdge], inputs[],
promptTemplate?, includeState?, reducer?, output{path,reducer}?, outputSchema?,
command{update,goto,resume}?, foreach{path,maxItems,concurrency,onOverflow,
sampleSeed,onMissing}?, workflow(subgraph)?, state, retry?, compensate?, model?`.
The authoring alias table is 60+ keys wide (`declarative_normalization.rs:20-99`).

- **Node kinds (5):** `agent | humanReview | reducer | command | subgraph`
  (`declarative_normalization.rs:960-980`), each with 3–6 aliases.
- **Edge conditions:** JSON Pointer `path` + a **closed, non-executable** operator
  set `eq, ne, exists, truthy, falsy, contains, gt, gte, lt, lte`
  (`:2087`, `:2106-2120`).
- **State reducers (7):** `replace, append, extend, merge, sum, reference,
  discard` (`:1790`).
- **Fan-out overflow:** `fail | truncate | sample(seeded)`; missing-path policy
  `error | empty`.
- **Retry:** `maxRetries, backoffMs, includeFailureContext, backoffStrategy
  (fixed|exponential), backoffMultiplier, maxBackoffMs, jitterMs`; jitter is
  **SHA-256-seeded so replays reproduce delays exactly**.
- `includeFailureContext` appends a machine-derived, injection-hardened failure
  block to the retry prompt — **a Reflexion primitive already in the format**.
- Per-step `model` override is additive and **cannot introduce tools or
  permissions**, by design.
- `MAX_WORKFLOW_SUBGRAPH_DEPTH = 16` (`declarative_normalization.rs:14`).

**PACT loop-IR consequence.** `command` + `goto` + `foreach` + reducers + seeded
jitter give PACT most of `G-3` for free. Missing versus AC-5.2: no
self-consistency/best-of-N node, no `tool`/`function`/`router` node kinds (also
named at `runtime-gap-analysis.md:153-154`), no tree-of-thought, no `verify` node.

---

### 1.4 `kind: Schedule` — field table

`ScheduleSpec` `lib.rs:5363-5387`.

| Field | Semantics |
|---|---|
| `spec.target` | `RegistrySelector` — id **xor** search filters |
| `spec.prompt` | run input |
| `spec.cron` | 5-field normalised to Goose 6-field, validated with the *same* `croner` parser Goose uses; `@daily` rejected |
| `spec.timezone` | `local` sentinel or validated IANA id ≤128 chars against the bundled tzdb |
| `spec.concurrency` | `skip_if_running \| allow_parallel` only |
| `spec.enabled` | bool |
| `spec.catchupPolicy` | `{mode: skip \| coalesce \| replay{max}}`, default `skip` (`lib.rs:5335-5348`) |
| `spec.catchupWindowSecs` | `0` disables catch-up regardless of policy |

---

### 1.5 `kind: Eval` — field table (the one PACT most has to beat)

`src/eval.rs`. **Every struct is `deny_unknown_fields`** — the strictest kind in
the family.

| Field | Semantics | Evidence |
|---|---|---|
| `metadata.{name, description, displayName?}` | | `:24-31` |
| `spec.target` | exactly one of `agent` (registry id) / `selector` / `manifest` (path) / `inlineAgent` (full `BudAgentManifest`) | `:44-60` |
| `spec.cases[]` | `{id, prompt, graders[]}` — **no expected output, no dataset ref, no context/retrieval fields** | `:62-68` |
| `spec.thresholds` | `{minimumPassRate (default 1.0), maximumFailedAttempts?}` | `:131-147` |
| `spec.execution` | `{repetitions (default 1), failFast (default false)}` | `:149-165` |

**Graders — the complete set (8, all deterministic, `#[serde(tag="kind")]`,
`:70-129`):** `terminalStatus{statuses[] default ["completed"]}` ·
`outputContains{value, caseSensitive}` · `outputNotContains{…}` ·
`outputEquals{value: Value}` · `outputRegex{pattern, caseSensitive}` ·
`jsonSchema{schema}` · `eventCount{event, minimum, maximum?}` ·
`artifactCount{artifactKind?, artifactName?, mimeType?, minimum, maximum?}`.

Bounds (`:5-12`): ≤1 000 cases, ≤10 000 attempts, ≤64 graders/case, ≤100 000
grader evaluations, ≤1 MiB prompt, ≤4 KiB regex, ≤1 MiB case artifact, ≤128 MiB
report artifact.

**Negative findings that define PACT's eval work:**
- **No LLM judge, no semantic metric, no rubric.** Every DeepEval-class metric is
  inexpressible. (Ironically, the *guardrail* subsystem has `model_judge`
  — `declarative_normalization.rs:4696` — so the judge machinery exists; it is
  simply not wired to Eval.)
- **No dataset files.** Cases are inline only.
- **No trace→case promotion.** Recovery explicitly refuses to keep prompts and
  raw model output as recovery artifacts (`sdk-and-declarative-dev.md:757-762`).
- **No per-metric thresholds** — one global `minimumPassRate`.
- **No SLO assertions** — latency/cost cannot be asserted in an Eval, even though
  `AgentBudgetPolicy` measures them.
- **No variant/model axis** — an Eval targets one agent, not (agent × model).
- Attempts run as **normal Goose child runs with full ledger lineage**, and fully
  graded attempts commit redacted versioned evidence before the parent advances.
  *This part is excellent and PACT must keep it.*

---

### 1.6 `kind: EventSubscription` — field table

`event_subscription.rs:40-100`. `apiVersion` **must** be
`bud.dev/event-subscription/v1` (`:838-844`).

| Field | Semantics |
|---|---|
| `spec.filter` | `BudEventFilter {eventTypes[], sources[], subjects[]}` — CloudEvents-shaped (`:70-77`), ≤128 values per list |
| `spec.target` | `{kind: agent, selector: RegistrySelector}` **or** `{kind: workflow, workflow: BudWorkflowManifest}` (`:80-84`) |
| `spec.prompt` | default `"Handle this event according to your instructions."`, ≤64 KiB |
| `spec.retry` | `{maxAttempts ≤32 (default 5), initialBackoffMs, maxBackoffMs ≤24 h, multiplier, leaseMs 1 s–1 h}` (`:86-94`) |
| `spec.concurrency` | `serial`(=`one_at_a_time`/`skip_if_running`) \| `parallel`(=`allow`) |
| `spec.maxPending` | 1..=100 000, default 1 000 |
| `spec.enabled` | bool |

**This is the "feedback events" construct the assignment asked about — it already
exists**, with a full create/list/inspect/update/delete/activate/cancel/purge
control plane, dead-letter, dedupe retention (30 d), and SQLite schema v3.

---

### 1.7 `AgentBlueprint` — authoring sugar (not a manifest)

`lib.rs:4308-4468` (root) + `AgentSubagentDefinition` `:4470-…`.

Root fields with verified `#[serde]` aliases: `name`, `aliases`, `purpose`
(`goal|task|role`), `instructions` (`systemPrompt|system_prompt|prompt`),
`description`, `displayName` (`display_name`), `model`, `tools` (`tool`),
`skills` (`skill`), `contextFiles`
(`context_files|knowledgeFiles|knowledge_files|knowledge`), `capabilities`,
`agentTools` (`agent_tools`), `handoffs`, `subagents`
(`programmaticSubagents|programmatic_subagents`), `initialPrompt`, `recipePrompt`
(`recipe_prompt|inputTemplate|input_template|runPrompt|run_prompt`),
`recipeParameters` (+5 aliases), `memory`, `mcpServers`, `maxTurns`, `effort`
(`thinkingEffort|thinking_effort|reasoningEffort|reasoning_effort`), `thinking`,
`maxThinkingTokens` (+3), `background`, `permissionMode` (`permission_mode`),
`output` (+6), `guardrails`, `permissions`, `runtime`, `includeGuideSkill`
(`include_guide_skill`, **default `true`**).

**Critical asymmetry (unchanged, now worse):** `AgentBlueprint` has **no
`budgets`, no `context`, no `security`**. The "easy" tier cannot express the
operational contract, the turn-context policy, or the security posture.

Semantics: `mode: agentTool | handoff` selects `tools.agents` vs `handoffs`;
`effort` → Goose `thinking_effort`; `thinking.enabled`/`maxThinkingTokens` →
`request_params.budget_tokens`; `contextFiles` land as `SkillSupportingFile`
records, **not** skills; `includeGuideSkill: true` **silently injects a guide
skill into every blueprint-authored agent**.

**PACT consequence.** Under D14 ("no-code is the ceiling") PACT cannot have a
two-tier format where the beginner tier expresses *less*. The Expansion Rule plus
profiles must replace the blueprint outright, or the converter carries
blueprint↔manifest asymmetry forever. `includeGuideSkill` must become a profile
default (F-1) or be dropped.

---

### 1.8 What `bud.dev/v1` **cannot** express (negative inventory)

| Missing construct | Evidence of absence | PACT requirement |
|---|---|---|
| **Input contract / modality** | no `spec.input` in `AGENT_SPEC_FIELDS` (`manifest_compiler.rs:8-33`); `RunInputMetadata.kind` is hardcoded `"text"` at **every** construction site (`run_planning.rs:2419-2422`, `policy_runtime.rs:2700`, `http_control_plane.rs:8524`, `lifecycle_callback.rs:6712`, `process_runtime.rs:2100`, `workflow_graph.rs:3450`, `lib.rs:14664`); cards hardcode `text/plain`+`application/json` (`manifest_compiler.rs:3758-3759`, `portability.rs:2064-2065`) | D16: content-typed `io.input`/`io.output`; card projection driven from it |
| **Streaming semantics** | `capabilities.streaming: true` hardcoded on every card (`manifest_compiler.rs:3754-3757`) | Contract: declared streaming mode, per modality |
| **Capability *requirements*** | `spec.capabilities` is what the agent **provides** (`lib.rs:4020-4028`, exported as A2A skills `portability.rs:2072-2093`); nothing declares what an executor must **have** | O3.1 predicate language is 100 % new |
| **Model catalogue / benchmark predicates** | `spec.model` is a binding, not a requirement | `models/catalog.yaml` + predicates (D8) |
| **Variants / strategy plurality** | no field; one model, one strategy per agent | Strategy-space: `variants/` |
| **Version / namespace on the manifest** | `AgentMetadata` `lib.rs:3847-3855`; `metadata.version` is a hard error (`LIVE`) | `metadata.version`, `metadata.namespace` |
| **Extension namespace (`x-`)** | unknown fields hard-rejected at root/metadata/spec (`manifest_compiler.rs:51-69`); `x-bud` exists **only** inside OSSA export (`:3536-3546`) | `x-` blocks that round-trip (O1.4, AC-1.3) |
| **SLO percentiles / TTFT / TPOT / throughput** | `AgentBudgetPolicy` has none (`policy_runtime.rs:755-770`) | O4.2 |
| **Eval judge / metric / dataset / SLO assertion** | grader enum closed at 8 deterministic kinds (`eval.rs:70-129`) | D6 provider URIs, D19 five on-ramps |
| **Learning / optimizer / lineage of learned artifacts** | no field anywhere in any kind | O5.3 Learning IR |
| **Non-Goose runtime** | `spec.runtime.kind != "goose"` is a hard error (`declarative_normalization.rs:5459-5461`) | Substrate must be open; `goose` becomes one profile |
| **Market/auction + blackboard topologies** | not in the 11 team strategies | AC-5.1 |
| **`Channel` manifest** | documented (`sdk-and-declarative-dev.md:2558`); **no type, no normalizer** | specify, or declare out of scope under D24 |
| **Conformance / fidelity metadata** | nothing records which adapter ran, at what fidelity | Portability Report, `pact.lock` |

---

## 2. WHAT THE RUNTIME DOES THAT A SPEC MUST NOT BREAK

### 2.1 Registry coordinates & revisions

- Runtime identity is the immutable triple `BudAgentReleaseCoordinate {id,
  version, revision}` (`crates/bud-agent-types/src/lib.rs:962-968`). The revision
  is a `sha256:` over **canonical behaviour-affecting entry data plus
  credential-binding names**, deliberately excluding local discovery paths and
  lease bookkeeping (`registry-and-portability.md:74-83`).
- IDs are prefix-namespaced and stable: `bud:<slug>`, `a2a:<slug>`,
  `goose/current`, `goose/recipe/<slug>`, `goose/agent/<slug>`,
  `goose/skill/<slug>` (`registry_sources.rs:419`; `LIVE`: `bud:sec-agent`).
- Namespaces must be **claimed** before publication; `bud`, `goose`, `a2a` are
  reserved to `system/bud`, `system/goose`, `system/a2a`
  (`registry-and-portability.md:85-87`). Dependency ranges are SemVer; an opaque
  active dependency reports `invalid_version`.
- Activation is CAS/generation-checked, append-only, rollback-capable
  (`:88-92`).
- Non-runnable inventory carries `budRuntimeRunnable: false` and is excluded from
  ranked discovery and A2A invocation (`:94-97`).
- **Three distinct digests coexist on one entry** (`LIVE`): `budPackageDigest`
  (SHA-256 over the whole materialised tree, `package_trust.rs:99-120`),
  `budPackageObjectDigest`, and the registry `revision`.

**PACT obligation.** PACT identity must *project onto* the triple, not replace
it: `metadata.namespace` + `metadata.name` → `id`; `metadata.version` → `version`.
The `canonical.json` digest is a **candidate** for `revision` but is not equal to
it today. Decide explicitly — (a) PACT's authored-file digest becomes the
revision and the registry computation changes, or (b) they stay distinct and
`pact.lock` records both. **Reusing the word "revision" for two different digests
is a migration hazard.**

### 2.2 Access envelope (`bud.dev/agent-access/v1`)

- Every record has one owner `(tenant, subject)`, visibility
  `private | tenant | public`, an optimistic `generation`, and typed grants over
  the **closed** action set `discover, read, invoke, manage, publish`
  (`crates/bud-agent-types/src/lib.rs:129-190`;
  `registry-and-portability.md:648-660`).
- Persisted in the reserved metadata envelope `_budAgentAccessV1`
  (`crates/bud-agent-types/src/lib.rs:8`; `LIVE`: the compatibility producer
  emits `{"apiVersion":"bud.dev/agent-access/v1","generation":1,"owner":
  {"tenant":"bud-system","subject":"registry-compatibility"},"visibility":
  "private"}`). A record without it is deterministically read as generation 0,
  private, owner `legacy/system-legacy`, visible only to a system context.
- **Agent-supplied metadata is untrusted**: kind, namespace, package path,
  display name, card body and agent metadata are never trusted tenant inputs;
  `BudRegistryProducerContext` is deliberately non-Serde and **overwrites forged
  `_budAgentAccessV1` input before the first insert**
  (`registry-and-portability.md:685-694`).
- `AgentRecord.access` is a **projection**: non-managers see only apiVersion,
  generation, owner tenant, and visibility.
- Startup **fails closed** if the registry is not access-ready (`:697-701`).

**PACT obligation.** Access is **not a spec field**. PACT manifests must carry no
owner/visibility/grant data and the loader must not invent any. The PACT→registry
producer must run inside `BudRegistryProducerContext`. This is the concrete
meaning of D24: **PACT declares identity and capability; the registry declares
who may see and invoke.**

### 2.3 A2A Agent Card projection

Two projections that must not diverge: package card
(`export_a2a_agent_card`, `manifest_compiler.rs:3737-3783` →
`.well-known/agent-card.json`, `agent_package.rs:75-80`) and registry card
(`agent_registry_card.rs`, served at `GET /bud/registry/{id}/a2a-card` and
`GET /.well-known/agent-card.json?targetId=…`).

Fixed shape (`LIVE`-confirmed): `name`, `description`, **`version: "1.0.0"`
hardcoded**, one `supportedInterfaces[]` entry `{url: <base>/a2a/v1,
protocolBinding: "JSONRPC", protocolVersion: "1.0"}`, `capabilities
{streaming: true, extendedAgentCard: false}`, **`defaultInputModes` /
`defaultOutputModes` hardcoded** to `["text/plain","application/json"]`, `skills`
from `a2a_skills`, and `metadata.bud {runtime, agentTools, capabilities,
handoffs, a2a}` (+ `output`, `guardrails` when non-default).

`a2a_skills` (`portability.rs:2048-2122`) emits, in order, deduped by id:
1. a synthetic `default` skill when both `skills.use` and `capabilities` are empty;
2. one per `skills.use[]` (tags `bud, goose, skill`);
3. one per `spec.capabilities[]` (tags `bud, goose, capability` + declared);
4. **`agent-tool:<name>`** per `spec.tools.agents[]`;
5. **`handoff:<name>`** per `spec.handoffs[]`.

Hard security rules PACT must preserve (`registry-and-portability.md:1029-1040`):
public cards must **not** contain `packagePath`, `sourceUrl`, endpoint provenance
for proxied targets, artifact paths, Goose custom-agent/recipe filesystem paths,
Goose skill support-file paths, Goose data directories, working directories, or
Goose session ids. Every published skill needs non-empty `id/name/description/
tags`. Cards are `Cache-Control: public, max-age=60, must-revalidate` with a
strong ETag over the exact JSON body and `304` on `If-None-Match`.
`pushNotifications` is deliberately **not advertised** until server-side push
config and durable webhook delivery ship together.

`agent-tool:` / `handoff:` skill ids are **selectable by remote peers** via
`params.metadata.skillId | budSkillId | "bud.skillId"`; Bud plans the addressed
agent as parent and executes the named declared child.

**PACT obligation.** The facade-id grammar `agent-tool:<name>` / `handoff:<name>`
is a **wire contract with remote peers**; renaming PACT's tool/handoff bindings
changes remote invocation. PACT must (a) drive `version` from `metadata.version`,
(b) drive `defaultInput/OutputModes` from the new I/O contract (the doc already
*claims* this — `registry-and-portability.md:1023` "inputModes/outputModes |
manifest IO plus model/tool capabilities" — while the code hardcodes it), and (c)
keep the id grammar byte-compatible.

### 2.4 Run ledger lineage

`BudRunPlan` (`lib.rs:8629-8674`) is the durable unit: `runId, status, backend,
targetId, targetVersion, targetRevision, targetKind, targetName, input,
authorization, agentRegistrySnapshot, lineage, fork, orchestration, goose,
gooseCustomAgent, gooseSession, a2a, events, interrupts, checkpoints, artifacts,
executionPolicy, budget, budgetRecords, guardrailDecisions`.

- `RunLineage {parentRunId, rootRunId, nodeId, relationship, depth}`
  (`:8731-8738`); `relationship` ∈ `agent_as_tool | handoff | child_run |
  spawned_by_run | bundled_subagent`.
- `RunEvent {seq, kind, status?, message?, metadata}` (`:8838-8847`) — per-run
  monotonic `seq`, append-only, `Last-Event-ID`-style cursor replay.
- `RunArtifact {artifactId, kind, name, mimeType, bytes, sha256, uri,
  contentPath, metadata}` (`:8900-8912`) — content-addressed sidecars.
- `RunCheckpoint {id, kind, reason, eventSeq, runStatus, activeNodeId?,
  childRunIds[], pendingInterruptIds[], artifactIds[], metadata}` (`:8880-8897`).
- `RunForkPlan {sourceRunId, sourceCheckpointId?, sourceEventSeq, sourceStatus,
  sourceGooseSessionId?, forkedGooseSessionId?, metadata}` (`:8741-8757`) — an
  executable fork **requires a copied Goose session id** so a branch never reuses
  the source session.
- `BudRunAgentRegistrySnapshot {source, allowedAgentIds[]}` (`:8694-8700`) pins
  the set of agents a run may reach; `permits()` is a binary search over the
  sorted list.
- `BudRunAuthorizationEvidence` (`run_authorization_evidence.rs:363-373`):
  `apiVersion, principal, requiredAction, planScopeJcsSha256, decisions[],
  internalRoot?, parentEvidenceJcsSha256, evidenceJcsSha256` — a **JCS-canonical
  hash chain from parent run to child run**.
- The ledger deliberately does **not** persist raw prompts or raw artifact text;
  `RunInputMetadata` records only `{kind, bytes, redacted}`.

**PACT obligation.** `BudRunPlan` has **no `apiVersion` field** and is
format-agnostic (`lib.rs:8629`) — the ledger survives the migration untouched.
But learning (T6/O5.3) needs traces and **the ledger by design has no text**.
PACT's trace→eval promotion must therefore define a **separate, opt-in,
redaction-policy-bound trace store**. This is the single biggest hidden
dependency in the learning design.

### 2.5 Interrupts

`RunInterrupt {id, source, status, reason, requestId?, eventSeq, decision?,
metadata}` + `RunInterruptDecision {decision, message?, decidedAtSeq, command?:
WorkflowCommand, metadata}` (`lib.rs:8851-8877`).

Four unified sources (`registry-and-portability.md:240-257`): Goose tool
approvals, Goose elicitations, A2A `input-required`/`auth-required` task states,
and workflow human-review gates. Child interrupts propagate to the parent as
`child_run` interrupts; resolving the parent applies the same decision to the
child. Resume of a workflow gate applies review output + RFC 7396 state patch +
routing in **one cursor commit**, and **rejects routes the manifest did not
declare**.

Bounds: interrupt resolution message ≤64 KiB, workflow command ≤1 MiB, Goose
elicitation user data ≤1 MiB (`lib.rs:86-88`).

**PACT obligation.** PACT's HITL construct must map 1:1: one interrupt model,
four sources, parent/child propagation, declared-routes-only resume. A fifth
source is additive; changing resolve semantics is not.

### 2.6 Permissions — the real enforcement path (**substantially revised**)

**Verified reality:**

- `manifest_initial_goose_mode` (`goose_adapter.rs:35824-35833`) →
  `initial_goose_mode_from_token` (`:35844-35855`) maps
  `chat|chatonly|chat_only → Chat`, `smart|smartapprove|smart_approve →
  SmartApprove`, `approve → Approve`, `auto → Auto`, **everything else →
  `GooseMode::default()` = `Auto`**
  (`goose/crates/goose-provider-types/src/goose_mode.rs:24-27`).
- **The manifest's own default `mode: "ask"` is "everything else."** So a manifest
  that says `ask` starts the session in auto-approve.
- Real enforcement is `ToolPolicy`: when any of `autoApprove/requireApproval/deny`
  is non-empty, the `bud_tool_policy` inspector is added to preflight and applies
  exact and pattern decisions (`goose_adapter.rs:35434-35470`). Session-level user
  permissions layer on top via `bud_session_tool_permissions` but **never override
  a `bud_tool_policy` deny** (`:35472-35495`).
- **Fail-closed refusals** (new, and the right pattern):
  `refuse_tool_policy_on_dispatch_owning_provider` (`:35306-35331`) refuses a run
  when `provider_owns_tool_dispatch` (`lib.rs:3991-4001`: any `*_acp` provider or
  `claude_code`) would execute tools outside Goose's inspection path;
  `seed_bud_session_tool_policy_permissions` (`:35334-35361`) refuses an
  un-boundable argument-scoped deny. Both name the offending manifest field.
- `spec.permissions` is otherwise consumed only by `explain`, OSSA `autonomy`
  (`portability.rs:2031-2044`: `ask|manual|readonly → supervised`;
  `approve|auto → autonomous`; else `collaborative`), Goose-source frontmatter,
  and export warnings.
- **`permissions.rules` is parsed nowhere.** `normalize_permissions` clones
  unknown keys through (`declarative_normalization.rs:4135-4137`); `LIVE` shows
  `rules.deny: ["shell:rm -rf *"]` surviving into the canonical manifest with no
  reader.

Architecture invariant to preserve: *"Availability, permission, approval, and
policy are separate controls. An SDK tool becoming visible never means it is
auto-approved"* (`runtime-gap-analysis.md:76-77`).

**PACT obligations.**
1. **Do not carry `permissions.mode` forward as enforcement.** Make the
   tool-permission projection `{kind, target, permission, source}` the normative
   surface and define `mode` as a *profile default that expands into that
   projection*.
2. **Never let `default` mean `auto-approve`.** PACT's default must be
   deny-by-default or ask-by-default and must be *the same* value at every layer.
3. **Mark `permissions.rules` as never-implemented** so the converter warns
   rather than silently carrying a fiction.
4. **Adopt the refusal pattern generally:** every declared control is either
   enforced on the chosen substrate or the resolve/plan step refuses, naming the
   field. The runtime proves this is implementable.
5. **The OSSA autonomy projection must be derived from the enforced
   projection, not from `mode`** — otherwise PACT re-exports a false governance
   claim.

### 2.7 Goose recipe compilation (the lowering PACT inherits)

`compile_goose_recipe` (`manifest_compiler.rs:1843-1892`) emits:
`version: "1.0.0"`, `title` = `metadata.name`, `description`, `instructions`
(via `goose_instructions`), `prompt` (default `"{{ bud_prompt }}"`, overridable
only if `spec.runtime.gooseRecipe.prompt` **contains** `bud_prompt` —
`:1894-1905`), `parameters` (always containing a `bud_prompt` parameter),
`extensions` (from `tools.available` + `skills.use` + `runtime.mcpServers`, plus
`summon` when sub-recipes exist), `sub_recipes`, `settings` (from `spec.model`),
`response.json_schema` (from `spec.output.schema`).

Delegation-safe variant makes `bud_prompt` optional with a default so a `summon`
child runs without an explicit prompt (`agent_package.rs:~121`). Agent-tool
proxies compile to a stub recipe carrying `kind: bud.agent_tool_proxy`,
`schemaVersion: 1`, `toolName` in `author.metadata`.

Export loss reporting is real and typed (`BudGooseRecipeExportWarning {path,
message}`, `runner.rs:1182`): unsupported `spec.model` keys outside
`{provider, name, temperature, max_tokens, context_limit, thinking_effort,
request_params, max_turns}` warn (`portability.rs:1863-1885`); agents-as-tools,
handoffs, tool approval policy, inline skills, `skills.use`, capabilities,
guardrails, non-`ask` permission modes, and every non-`{kind, gooseRecipe}`
runtime key each warn (`:1902-1992`). **Note what does *not* warn: `budgets`,
`context`, `security`.**

**PACT obligation.** `bud_prompt` is a **wire contract with the Goose CLI**
(`goose run --recipe … --params bud_prompt=<input>`); PACT's Goose adapter must
keep emitting it. The warning *shape* (`{path, message}`, deduped by path) is the
right skeleton for `ExportReport` — but it must become **exhaustive by
construction** (derived from the field table), not a hand-written list that
already misses three fields.

### 2.8 Package materialisation & trust

`materialize_agent_package` (`agent_package.rs:3-85`) writes exactly:

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
(`LIVE`-confirmed, minus skills/subagents for the test manifest.)

`check_agent_package` (`agent_package.rs:193-259`) re-derives **every** generated
artifact and **byte-compares** it against disk, including the manifest itself
(`serde_yaml::to_string(&normalize(parse(file))) == file`), then scans for
secrets. Package digest is a domain-separated SHA-256 over sorted
`path/len/bytes` (`package_trust.rs:99-120`), and is the Ed25519 signing payload
(`:122-128`). Trust policies: `allow_unverified | require_lockfile |
require_signature_marker | require_verified_signature`, default from
`BUD_AGENT_PACKAGE_TRUST_POLICY` (`package_trust.rs:4`).

**PACT obligation.** The package layout is the closest existing thing to a PACT
tree, and `check_agent_package`'s manifest-canonical check is **exactly
`collapse(load(X)) ≡ X`** — reuse it as the AC-1.2 harness. But note: **the digest
covers derived artifacts.** Under D2 (`canonical.json` derived, deleting it must
be harmless) the digest must be computed over **authored files only**. The
exclusion machinery exists but excludes only signature-ish paths:
`BUD_AGENT_PACKAGE_DIGEST_EXCLUDED_FILES` is 12 signature filenames
(`package_trust.rs:43-57`) and `..._EXCLUDED_DIRS` is `[".git", ".sigstore"]`
(`:58`). PACT must add `recipes/`, `portable/`, `.well-known/`, generated
`.agents/`, `README.md` and `.pact/` — or the digest keeps depending on build
output and every build-tool change invalidates every signature.

### 2.9 Other runtime contracts a spec must not break

- **Custom loop protocol `bud.loop.v1`** — restartable, journal-backed
  prepared/committed action commits; a prepared action without a commit is
  *indeterminate and never auto-replayed*; a manifest-bound loop may reopen only
  the original Goose session after verifying data dir, working dir, registered
  manifest revision, and canonical manifest identity in Goose extension data
  (`architecture.md:1364-1379`). `executor.revision` must be
  `sha256:<64 lowercase hex>` (`declarative_normalization.rs:5688-5696`).
  A custom-loop manifest **cannot** be executed by `BudRunner::run` — it must go
  through `plan` + the loop controller (`runner.rs:1729-1733`,
  `goose_adapter.rs:14442-14446`).
- **Execution lease** — a non-blocking store-and-run scoped OS lease prevents two
  Bud processes executing the same run (`LIVE`: `runs.json.execution-locks/…lease`).
- **Memory** (`bud.dev/memory-*/v1`) — record kinds `semantic | episodic |
  procedural | preference | blackboard` (`memory.rs:71-78`); sensitivity
  `public | internal | confidential | restricted` (`:80-88`); blackboard reducers
  `set, merge_patch, append, delete` (`:98-105`); nine scopes (`:114-124`); CAS via
  `expectedGeneration`; redaction erases content from **all** historical revisions
  while keeping metadata; context assembly **fails closed**; memory content is
  injected wrapped as untrusted reference data with explicit "not instructions,
  not tool authorization" framing.
- **Mailboxes** — at-least-once, idempotency-key-bound, lease tokens returned once
  and stored only as hashes, CAS generations, dead-letter, redrive with a stable
  operation id, **scoped to an immutable release coordinate**
  (`durable-agent-mailboxes.md:11-63`).
- **Security realm** — one process = one customer/workspace realm; cross-realm
  invocation is authenticated A2A only (`runtime-gap-analysis.md:78-80`).
- **Scoped A2A key** cannot call mailbox, registry, run, app, or ACP routes.
- **Registry-entry capability index** is *derived*, not authored
  (`registry_sources.rs:1490-1530`): declared capabilities + `skill:` per
  `skills.use` + per-tool capabilities + `agents.as_tools` + `agent-tool:<n>` +
  `handoffs` + `handoff:<n>` + `structured_output` + container facts + `model:<name>`
  (`LIVE`: `capabilities: ["model:default"]` for a manifest that declared none).
  **PACT must specify this derivation, because discovery depends on it and it is
  currently implicit.**

---

## 3. THE NATIVE-DISCOVERY CONTRACT (D2)

### 3.1 What exists today — and exactly why it fails D2

**(a) No filesystem discovery of Bud agents.**
`bud agents` subcommands are `list, inspect, records, record, search, a2a-card,
run, normalize, validate, explain, init, import-goose-agent, export, check`
(`bin/bud.rs:6177-6193`). `agents list` reads a **registry file**;
`DEFAULT_AGENTS_RUN_WORKSPACE = ".bud/agents"` (`bin/bud.rs:9669`). The only
recursive scans are `register_goose_recipes|agents|skills|apps`
(`registry.rs:1741, 1856, 1974, 2099`) and `bundled_subagent_package_dirs`
(`registry_sources.rs:1379-1408`, keyed on `agent.bud.yaml`). A Bud agent becomes
discoverable only through explicit `register_package` (`registry.rs:504-516`).
**The documented `.agents/<name>/agent.yaml` layout
(`registry-and-portability.md:304-331`) does not exist: the string `agent.yaml`
is absent from the entire Rust source.**

**(b) Running requires a build — on every path.**
- Registry-backed local run: `run_planning.rs:2450-2483` requires
  `recipes/<name>.goose.yaml` to be listed in `entry.artifacts` **and** to exist
  as a file, plus `entry.metadata["gooseRecipeAcceptsBudPrompt"] == "true"`
  (`:2430-2437`) and no unsupported required recipe parameters (`:2441-2449`).
- Manifest-in runs: `BudRunner::plan` (`runner.rs:1898-1909`) and
  `prepare_universal_agent_run` (`goose_adapter.rs:14450-14453`) both
  **materialise and register a package first**. `LIVE`: confirmed on disk.
- Even *building a registry entry* compiles a Goose recipe:
  `registry_runtime_metadata_for_manifest` calls `compile_goose_recipe`
  (`registry_sources.rs:1612`).

**Conclusion: D2 is currently violated everywhere except one library call.**

### 3.2 The escape hatch that makes D2 achievable

`BudUniversalAgentRuntime::create_agent(&BudAgentManifest, working_dir)`
(`goose_adapter.rs:10387-10400`) and `::run(BudUniversalAgentRunRequest)`
(`:10402-…`) build a live Goose agent **directly from the manifest struct** via
`BudGooseSessionHost::create_bud_agent_session` (`:28565`), never reading
`recipes/*.goose.yaml`, never touching the registry. Input guardrails are
enforced on this path (`:10409`), output guardrails after
(`:10432-10435`), structured output attached from `spec.output.schema` (`:10431`).

So **the manifest-in-memory executor already exists.** What is missing is (a) a
tree→document loader and (b) a run-planning branch that does not demand a
package.

### 3.3 The contract PACT should specify

**What the runtime scans for.** Three roots, all already conventional in the tree:

1. `.agents/` — the OSSA-aligned project convention Goose already discovers for
   `skills/`, `recipes/`, `agents/`, `plugins/`
   (`goose_adapter.rs:27202-27235`, discovery triple `[".agents",".goose",".claude"]`
   at `:27774`, `:39055`);
2. `.bud/agents/` — the existing default agent workspace (`bin/bud.rs:9669`);
3. an explicit `--workspace`/`--path` root.

Discovery unit = **a directory containing a PACT root file**, resolved in this
order, all of which must be recognised: `agent.yaml` (PACT native),
`agent.bud.yaml` (bud.dev/v1 compatibility), `team.yaml`, `workflow.yaml`,
`eval.yaml`, `schedule.yaml`, `subscription.yaml`, `workspace.yaml`. Precedent
for "directory identified by a well-known file" is already
`bundled_subagent_package_dirs` keying on `agent.bud.yaml`
(`registry_sources.rs:1402`).

**What the runtime is guaranteed** — the normative list PACT owes:

| # | Guarantee | Why the runtime needs it | Backed by |
|---|---|---|---|
| G1 | The tree loads to a complete in-memory document **with zero derived files present** | D2.2; feeds `create_agent(manifest, dir)` | `goose_adapter.rs:10387` |
| G2 | Loading is **pure and offline** — no network, no shell, no code execution, no `$(…)` | D17 air-gap; the loader runs inside one security realm | `runtime-gap-analysis.md:78-80` |
| G3 | A stable `id` = `namespace/name`, a `version`, and a content `revision` over **authored files only** (derived paths excluded) | registry release coordinate | `crates/bud-agent-types/src/lib.rs:962`; exclusion machinery `package_trust.rs:43-58` |
| G4 | `capabilities[]` `{name, description, tags}` **plus the derived index** (`skill:`, `agent-tool:`, `handoff:`, `structured_output`, `model:`) | registry capability index + A2A skills + OSSA | `registry_sources.rs:1490-1530` |
| G5 | Declared `tools[]`, `skills[]`, `mcpServers`, `models` as **references the runtime may already own** — never inline copies; with a specified resolution hook | AC-6.2; the WS1 skill resolver is the precedent | `manifest_compiler.rs:3223-3260` |
| G6 | The tool-permission projection `{kind, target, permission, source}` | `bud_tool_policy` inspector | `manifest_compiler.rs:3101-3131`, `goose_adapter.rs:35434` |
| G7 | Guardrails resolved per stage, ready before the first provider call | 8-stage pipeline | `lib.rs:4155-4166` |
| G8 | Budget policy (7+ dims) for the run accumulator | `BudRunBudgetState` | `policy_runtime.rs:755-782` |
| G9 | `io.input`/`io.output` content types → card `defaultInput/OutputModes` **and** `RunInputMetadata.kind` | D16; both hardcoded today | `manifest_compiler.rs:3758`, `run_planning.rs:2420` |
| G10 | Autonomy level **derived from the enforced permission projection**, not from a mode string | OSSA `spec.autonomy.level`; the Ladder | `portability.rs:2031-2044` |
| G11 | Declared child bindings (`tools.agents`, `handoffs`, `subagents`) resolvable to registry refs **before** the parent run is persisted | facade preflight fails atomically | `sdk-and-declarative-dev.md:1120-1123` |
| G12 | Every eval suite in the tree addressable as a schedulable target | `Eval` runs as a Goose child run | `eval.rs:44-60` |
| G13 | A machine-readable **load report**: every file consumed, every file ignored, every unknown `x-` block preserved, every unenforceable declaration named | AC-7.1 no silent loss | new |
| G14 | Per-agent `security` posture and `context` injection, since both are per-session state the host must set before the first turn | `spec.security`/`spec.context` | `lib.rs:4042-4125` |

**Explicit non-guarantees** (so the runtime cannot come to depend on them): the
tree does **not** supply ownership/visibility/grants (§2.2); does **not** supply
credentials (`manifest_compiler.rs:260-262`); does **not** supply the registry
revision unless PACT and the registry are explicitly unified (§2.1).

**Two loader modes PACT must specify.**
- *Cold* (D2 path): tree → document → `create_agent` in process. No `.pact/`, no
  recipe, no registry write, no package directory. **This is what makes AC-6.1
  true and it is currently impossible through any CLI/HTTP entry point.**
- *Warm* (production path): tree → document → registry entry + optional
  materialisation for the Goose CLI / scheduler / A2A backends.
  `.pact/canonical.json` is a cache keyed by the authored-file digest; deleting it
  must only cost time.

**The runtime changes PACT forces** (minimum set):
1. `plan_local_bud_agent` gains a branch that plans a `bud_universal_agent`
   backend **from a manifest path**, with no `recipes/*.goose.yaml` precondition
   (`run_planning.rs:2450-2483`).
2. `BudRunner::plan` / `prepare_universal_agent_run` gain a **no-materialise**
   mode (`runner.rs:1898`, `goose_adapter.rs:14450`).
3. `registry_runtime_metadata_for_manifest` stops requiring a compiled recipe to
   derive metadata (`registry_sources.rs:1612`).
4. `apiVersion` becomes a **dispatch key** on Agent/Team/Workflow/Schedule
   (`manifest_compiler.rs:265`, `:424`, `:527`, `:1506`).

Without (1)–(3), the CLI, HTTP control plane, scheduler, workflow executor, and
A2A ingress all keep requiring a build. Without (4), migration is unsafe.

---

## 4. NAMED GAPS → PACT CONSTRUCTS

The assignment named four gaps. **Two are already closed; one is closed in the
opposite direction from what was assumed.** Corrected map:

| Named gap | Actual status (verified) | PACT construct |
|---|---|---|
| **Eval manifest kind** | **Already exists and is strict** — `eval.rs:16-165`, CLI `bin/bud.rs:646-666`, 8 deterministic graders, `deny_unknown_fields` everywhere, validated `apiVersion`. The gap analysis never names it (`runtime-gap-analysis.md` has two "eval" hits, `:106` recovery and `:108` evaluator-optimizer). The thesis §7.5 claim that it is "the missing `Eval` manifest kind named in the in-repo gap analysis" is **wrong on both halves**. | `kind: Eval` **superset**: keep the 8 graders as `pact:` provider metrics; add `deepeval:*` metric URIs (D6), `datasets/`, per-metric thresholds, SLO predicates, rubrics, a (model × variant) axis, and the five D19 on-ramps desugaring into one document model. **Reuse the existing `model_judge` guardrail evaluator machinery (`declarative_normalization.rs:4696`, `goose_adapter.rs:1126-1717`) rather than building a second judge.** |
| **Registry versioning** | **Mostly closed** — namespaces, immutable coordinates, dependency preflight, cycle detection, CAS activation/rollback, governance states, health TTL, ranked discovery. **Still open:** "registration replaces the single active record for an id" — no simultaneous installed versions (`runtime-gap-analysis.md:177-183`). | PACT supplies the *authoring-side* half the registry lacks: `metadata.version` + `metadata.namespace` on the manifest, and `pact.lock` pinning `(agent, variant, model, adapter, runtime, tools)` to exact coordinates. PACT must **not** build multi-version activation — D24 says that is AgentZero's. |
| **Feedback events** | **Already exists** — `kind: EventSubscription`, 6 850 lines, CloudEvents filter, agent/workflow targets, retry + lease + dead-letter + dedupe. Gap-analysis `:194-196` is stale. | Carry `kind: EventSubscription` forward **plus a `learning` binding**: a subscription whose target is the optimizer, filtered on eval-failure and guardrail-block event types. That is how T6/O5.3's trace→eval promotion becomes no-code (D14). Requires the separate trace store from §2.4. |
| **Workflow-v2** | **Mostly closed.** Present: bounded graph, closed condition operators, cycles with `maxTransitions`, `foreach` with overflow/missing policy, 7 reducers, human review, command nodes, subgraphs (depth 16), retries with SHA-256-seeded jitter, **and saga compensation** (`WorkflowSagaPolicy`/`WorkflowCompensation`/`WorkflowStepForwardFailurePolicy`, `lib.rs:4856-4879`) which the gap analysis still lists as open. **Still open:** dedicated `tool`/`function`/`router` node kinds, richer state-schema validation, and explicit event triggers *inside* the Workflow kind. | PACT Loop IR + Topology IR: add node kinds `tool`, `function`, `router`, `ensemble` (self-consistency/best-of-N), `verify`; keep the existing 5 unchanged. Event triggers come from `EventSubscription` targeting a workflow — the plumbing already exists (`event_subscription.rs:80-84`). |

**Four further gaps PACT should claim** (not in the assignment list, all named or
demonstrated in source):

1. **Guardrail ordering vs tool approval** — "Ordering relative to tool approval
   must be explicit" (`runtime-gap-analysis.md:188-190`). PACT should make stage
   ordering normative: `input → modelInput → [provider] → modelOutput → toolInput
   → [approval] → [dispatch] → toolOutput → handoff/graphTransition → output`.
   *(INFERRED from the stage names and `AgentGuardrailPolicy::for_stage`; no
   single source location states the full order.)*
2. **Blackboard as a topology** — the memory primitive with reducers exists
   (`memory.rs:98-105`) but no Team strategy uses it. PACT's blackboard pattern
   (AC-5.1) should be a Team strategy over the existing memory primitive, not a
   new store.
3. **Schema/type drift** — `spec.context` and `spec.security` exist in Rust and
   are absent from the generated SDK schema (`sdk_codegen.rs:11069-11117`). PACT
   must generate schema, docs, converter, and export-warning list **from one field
   table**, with a CI test that fails when any of the four diverges.
4. **Unenforceable-declaration policy** — the runtime is inconsistent (hard
   refusal for tool policy, silent drop for `context`, preserve-but-unread for
   `permissions.rules`). PACT needs **one rule**: a declared control is enforced,
   emulated-and-reported, or refused — never silently retained.

---

## 5. MIGRATION PLAN — RISKS, BREAKS, SHIMS, DUAL-READ

### 5.1 What breaks (hard, verified)

| # | Break | Evidence | Severity |
|---|---|---|---|
| B1 | **Every PACT-only field is a validation error on the old binary.** Unknown fields rejected at root/metadata/spec. No `x-` escape exists outside OSSA export. | `manifest_compiler.rs:51-69`, `:143`, `:154`, `:160`; `LIVE`: `metadata.version` → error | **Blocking** — old and new manifests cannot coexist in one file |
| B2 | **`apiVersion` is fail-open on 4 of 6 kinds**, so a PACT document is *silently accepted* as v1 rather than rejected. | `manifest_compiler.rs:265, 424, 527, 1506`; `LIVE` | **Blocking** — half-migrated trees run under the wrong semantics with no error |
| B3 | **`metadata.version` does not exist**, and both exporters hardcode `1.0.0`. | `manifest_compiler.rs:3516`, `:3748`; `LIVE` | Major — versioned A2A cards change |
| B4 | **Name slugification is lossy, namespace-free, and truncates at 64.** `Análisis de Ventas` → `an-lisis-de-ventas`; `/` is a hard error. Two distinct PACT namespaced names can collide. | `runtime_validation.rs:1481-1530`; `LIVE` | Major — silent identity merge; also a D13/D21 blocker for non-English authors |
| B5 | **`spec.runtime.kind` must be `goose`.** Any PACT manifest naming another substrate fails validation. | `declarative_normalization.rs:5459-5461` | **Blocking** for adapters |
| B6 | **The Goose-source round trip silently drops `budgets`, `skills.define`, `context`, and `security`.** The writer omits all four; the importer reads a `skillDefinitions` key nothing writes. **No warning is emitted.** | writer `manifest_compiler.rs:3071-3099`; reader `:2226`; `LIVE` | Major — `.agents/agents/*.md` is a lossy identity for four fields |
| B7 | **Materialised packages are byte-checked.** `check_agent_package` re-derives every artifact and byte-compares. Any PACT change to manifest serialisation, recipe, card, or OSSA generation invalidates every existing package. | `agent_package.rs:240-256` | Major — all packages must be re-materialised |
| B8 | **Package digests change**, so signatures break, so `require_verified_signature` installs fail. The digest covers *derived* artifacts, so it changes even if no authored byte changes. | `package_trust.rs:99-128`, exclusion list `:43-58` | Major — re-signing campaign required |
| B9 | **Registry `revision` changes** if entry-derived data changes, forcing re-publication and breaking pinned A2A card URLs (`?targetVersion=&targetRevision=`). | `registry-and-portability.md:74-83`, `:1008-1010` | Major — pinned remote callers 404 |
| B10 | **`permissions.mode` semantics are a fiction *and* an unsafe default.** `ask` → `GooseMode::Auto`. Any migration that "faithfully preserves" the field ports auto-approve while claiming supervision. | `goose_adapter.rs:35844-35855`; `goose_mode.rs:24-27`; `portability.rs:2035-2037` | **Blocking for correctness** — must be fixed, not preserved |
| B11 | **Team `sequential` implicit `needs` wiring.** A converter that drops the implicit edge changes execution order. | `declarative_normalization.rs:151-153` | Moderate |
| B12 | **`includeGuideSkill` defaults to true**, so blueprint-authored agents carry an injected skill; a naive port either loses it (behaviour change) or carries it forever (F-1 violation). | `lib.rs:4467` | Moderate |
| B13 | **Alias explosion.** `AgentBlueprint` accepts ~40 alias spellings; `AGENT_SPEC_FIELDS` 10; `WorkflowStep` 60+; `ToolPolicy` 8. A strict PACT parser rejects real user files. | `lib.rs:4308-4468`; `manifest_compiler.rs:8-33`; `declarative_normalization.rs:20-99` | Moderate — needs a machine-generated alias table in the converter |
| B14 | **Dual placement** (every `spec.x` also accepted at root) doubles the converter's input space, and root/`spec` share one allow-list so `spec` may be absent entirely. | `manifest_compiler.rs:132-142` | Minor but must be handled |
| B15 | **The generated SDK schema is already behind the Rust type** (`spec.context`, `spec.security` missing; `additionalProperties: false`). Migrating on top of a drifting schema means the converter's "complete field list" is wrong on day one. | `sdk_codegen.rs:11030-11117`, `:24373-24377` | Major — fix before converting |
| B16 | **`spec.runtime` unknown keys are warn-and-keep**, and the warn list has already drifted from the parse list (`memory`, `gooseCustomAgent` warn while being honoured/emitted). A converter that trusts `KNOWN_RUNTIME_KEYS` will mis-classify real config. | `declarative_normalization.rs:5508-5533` vs `memory.rs:1435-1439`; `LIVE` | Moderate |
| B17 | **Team `spec.state` is accepted but only `state.shared` is read**; the rest is dropped without a warning. | `manifest_compiler.rs:513-518` | Minor — but a silent-loss path the fuzzer (AC-7.1) will find |

### 5.2 What needs a shim

| Shim | Contract |
|---|---|
| **S0 — `apiVersion` gate, shipped *before* anything else** | Make `apiVersion` a validated dispatch key on Agent/Team/Workflow/Schedule (`manifest_compiler.rs:265, 424, 527, 1506`). An unknown version must be a **named error**, mirroring the existing OSSA check (`apiVersion.starts_with("ossa/")`, `manifest_compiler.rs:~3360`) and the Eval/EventSubscription checks. **Without S0 the migration is unsafe and every other shim is untestable.** |
| **S1 — `bud.dev/v1 → pact.dev/v1` converter** | Pure, offline, total on the existing corpus. Emits a `ConversionReport` in the existing warning shape `{path, message}` (`runner.rs:1182-1195`), extended to `{path, disposition: exact\|renamed\|scaffolded\|lossy\|unsupported\|never-implemented, message}`. Must fan `spec.runtime` out five ways (§1.1.8) and must classify `permissions.mode`/`permissions.rules` as `never-implemented`. |
| **S2 — `pact.dev/v1 → bud.dev/v1` down-converter** | Needed for the dual-read window. Fails closed on: non-goose substrate, variants, capability predicates, non-deterministic eval metrics, I/O modality other than text, `metadata.version`/`namespace`. Each failure is an `unsupported` entry, never a silent drop (T7). |
| **S3 — `x-bud-legacy` preservation block** | Everything the converter cannot map (unknown `spec.runtime.*` keys, `permissions.rules`, `spec.state` remainder, blueprint-only fields) lands in a PACT `x-` block that round-trips (AC-1.3). |
| **S4 — Goose-source frontmatter v2** | Extend `bud_agent_source_metadata` to emit `budgets`, `skillDefinitions`, `context`, `security` **before** migration begins, so the `.md` round trip stops losing data (fixes B6 independently of PACT). Add the matching reader branches. |
| **S5 — Field-table single source** | Generate `AGENT_SPEC_FIELDS`, the SDK schema, the alias table, the export-warning list, and the converter map from **one** table; CI fails on divergence (fixes B15, B16, and the missing `budgets`/`context`/`security` export warnings in one move). |
| **S6 — Digest/revision bridge** | Publish, for one release, both the old package digest and the new authored-file digest on each entry, so signature verification and pinned cards keep working through the cutover. Requires extending `BUD_AGENT_PACKAGE_DIGEST_EXCLUDED_*` (`package_trust.rs:43-58`). |
| **S7 — `bud_universal_agent` run backend without materialisation** | A `BudRunPlan.backend` value planning from a manifest **path** with no recipe precondition and no package write (§3.3 changes 1–3). This is the change that actually delivers D2. |
| **S8 — Name/namespace compatibility map** | A persisted `{pact_id → bud_slug}` table so B4's lossy slugification does not silently merge two PACT agents, and so existing `bud:<slug>` references keep resolving. |

### 5.3 What must be dual-read during transition

1. **Manifest ingress.** Every caller of `normalize_agent_manifest` must accept
   both apiVersions: `manifest_compiler.rs:128` (the normalizer itself);
   SDK payload path `sdk_codegen.rs:6471`; runner validation `runner.rs:1725`,
   `:1892`; universal-agent path `goose_adapter.rs:14438`; package load
   `run_planning.rs:3205`, `:3227`; registry entry build
   `registry_sources.rs:387`; Goose-source import `manifest_compiler.rs:~2063`;
   package check `agent_package.rs:224`; CLI `bin/bud.rs:2167`.
2. **Registry entries.** `RegistryEntry.metadata` is a flat
   `BTreeMap<String,String>` (`crates/bud-agent-types/src/lib.rs:~778`) — a
   `pactApiVersion` key can carry the format marker without a schema change. The
   precedent already exists: `budPackageObjectSchema: "bud.runner-package-tree.v2"`
   (`LIVE`). *(INFERRED that no `pactApiVersion` key exists yet; I verified the map
   is open and untyped.)*
3. **Package roots.** Recognise both `agent.bud.yaml` and `agent.yaml` in
   `local_bud_package_registry_entry_with_producer_context`
   (`registry_sources.rs:387`), `bundled_subagent_package_dirs` (`:1402`), and
   `local_package_manifest` (`run_planning.rs:3205`, `:3227`).
4. **Eval manifests.** `normalize_eval_manifest` (`eval.rs:327`) hard-checks
   `apiVersion == bud.dev/v1` (`:1468`); dual-read means accepting PACT eval
   documents whose graders include non-deterministic metric URIs, and rejecting
   those on the v1 path with a **named** error rather than a
   `deny_unknown_fields` serde message.
5. **A2A cards.** Serve v1-shaped cards (`version: "1.0.0"`, hardcoded modes)
   until every known consumer is upgraded, then switch to `metadata.version` +
   real `defaultInput/OutputModes`. Because cards are ETag-cached with
   `max-age=60`, the switch is observable within a minute — schedule it
   deliberately.
6. **Run ledger.** **No dual-read needed** — `BudRunPlan` has no `apiVersion`
   field and is format-agnostic (`lib.rs:8629`). Genuine luck: the ledger, the
   interrupt model, the artifact model, and the authorization chain all survive
   the migration untouched.

### 5.4 Verification plan for the superset claim (D3)

The corpus to convert is enumerable and small:
- fixtures under `tests/agent_manifest.rs`, `tests/sdk_types.rs`,
  `tests/sdk_schema.rs`, `tests/eval.rs`, `tests/cli.rs`, `tests/workflow_graph.rs`,
  `tests/observability.rs` (all match `grep -l "bud.dev/v1"`);
- every `agent.bud.yaml` produced by `materialize_agent_package`, including the
  content-addressed `packages/.bud-package-objects/<digest>/` layout (`LIVE`);
- the **generated schema bundle itself** (`sdk_codegen.rs`) — converting the
  *schema* and diffing required/optional sets is a cheap mechanical proof that no
  field was dropped. **Fix B15 first or this proof is wrong.**

**Proposed gate.** `pact convert --from bud.dev/v1 <corpus>` must produce, for
every input, a document whose down-conversion (S2) re-normalises to a
**byte-identical** `BudAgentManifest` YAML — the same equality test
`check_agent_package` already performs (`agent_package.rs:240-250`).

**Second gate (the one that catches the real bugs).** For every field in the
13-field table, a test asserts the field survives: manifest → normalize →
serialize → parse → normalize, **and** manifest → each of the four exports →
import, with any loss appearing in a report. This test, run today, fails for
`budgets`, `skills.define`, `context`, and `security` (`LIVE`).

---

## 6. EVIDENCE INDEX (quick lookup, verified at `1a91f50`)

| Claim | Location |
|---|---|
| `BUD_API_VERSION`, `BUD_AGENT_LOOP_PROTOCOL_VERSION` | `src/lib.rs:51`, `:53` |
| `BudAgentManifest` / `AgentMetadata` / `AgentSpec` (13 fields) | `src/lib.rs:3839` / `:3847` / `:3857` |
| `AGENT_SPEC_FIELDS` (23 entries), unknown-field rejection | `src/manifest_compiler.rs:8-33`, `:51-69` |
| `normalize_agent_manifest`, apiVersion pass-through | `src/manifest_compiler.rs:128-289`, `:265` |
| `ToolPolicy`, `declares_permission_rules` | `src/lib.rs:3908-3969` |
| `provider_owns_tool_dispatch` | `src/lib.rs:3991-4001` |
| `BudToolPermissionProjection` / builder | `src/lib.rs:4003-4010` / `src/manifest_compiler.rs:3101-3131` |
| `AgentContextPolicy` (`moim`) | `src/lib.rs:4042-4064`; normalizer `src/declarative_normalization.rs:4178-4209` |
| `AgentSecurityPolicy`, `AgentEgressMode`, `AgentAdversaryPolicy` | `src/lib.rs:4066-4125`; normalizer `:4211-4339`; `parse_egress_mode` `:4330-4339` |
| `AgentGuardrailPolicy` (8 stages) / `AgentGuardrail` | `src/lib.rs:4127-4167` / `:4169-4208` |
| Guardrail evaluators / actions / failure modes | `src/declarative_normalization.rs:4693-4719` |
| `AgentBudgetPolicy` (7 dims) | `src/policy_runtime.rs:755-782` |
| `normalize_model` | `src/declarative_normalization.rs:3139-3200` |
| `normalize_permissions` (mode-only, clones the rest) | `src/declarative_normalization.rs:4118-4138` |
| `normalize_output` (weak schema check) | `src/declarative_normalization.rs:4140-4176` |
| `normalize_runtime` (goose-only; `KNOWN_RUNTIME_KEYS`) | `src/declarative_normalization.rs:5450-5535` |
| Loop policy / executor revision format | `src/declarative_normalization.rs:5537-5700`; `src/lib.rs:3882-3906` |
| Agent memory policy from `spec.runtime.memory` | `src/memory.rs:1435-1439`; validation `:1454-1556` |
| Memory record kinds / sensitivity / blackboard reducers / 9 scopes | `src/memory.rs:71-78` / `:80-88` / `:98-105` / `:114-124` |
| Team strategies (11) / member wiring / manager compile | `src/declarative_normalization.rs:114-138` / `:151-153` / `src/manifest_compiler.rs:1017`, `:1140` |
| Workflow strategies / node kinds / condition ops / reducers | `src/declarative_normalization.rs:101-112` / `:960-980` / `:2087`, `:2106-2120` / `:1790` |
| Workflow saga / compensation / limits | `src/lib.rs:4856-4879` / `:4880-4906` |
| `MAX_WORKFLOW_SUBGRAPH_DEPTH = 16` | `src/declarative_normalization.rs:14` |
| `BudEvalManifest` + 8 graders + bounds | `src/eval.rs:14-165`, `:5-12` |
| Eval apiVersion/kind hard check | `src/eval.rs:1468-1479` |
| `BudEventSubscriptionManifest` + apiVersion check | `src/event_subscription.rs:40-100`, `:838-844` |
| `AgentBlueprint` / `includeGuideSkill` default | `src/lib.rs:4308-4468` / `:4467` |
| `materialize_agent_package` | `src/agent_package.rs:3-85` |
| `check_agent_package` (byte-equality) | `src/agent_package.rs:193-259` |
| Package digest / signature payload / exclusions | `src/package_trust.rs:99-120` / `:122-128` / `:43-58` |
| A2A card export (hardcoded version + modes) | `src/manifest_compiler.rs:3737-3783` |
| `a2a_skills` (facade ids) | `src/portability.rs:2048-2122` |
| `autonomy_level` | `src/portability.rs:2031-2044` |
| OSSA export + `x-bud` | `src/manifest_compiler.rs:3499-3580` |
| OSSA/recipe export warnings | `src/portability.rs:1820-1992`; warning type `src/runner.rs:1182-1195` |
| Secret-config guard | `src/manifest_compiler.rs:260-262` |
| Goose recipe compile + `bud_prompt` | `src/manifest_compiler.rs:1843-1905` |
| Goose source frontmatter writer / reader | `src/manifest_compiler.rs:3071-3099` / `:2130-2232` |
| WS1 `skills.use` directory resolution | `src/manifest_compiler.rs:3223-3260`; caller `src/goose_adapter.rs:28621` |
| Recipe-artifact precondition (D2 breaker) | `src/run_planning.rs:2430-2483` |
| Materialise-before-run (D2 breaker, both paths) | `src/runner.rs:1898-1909`; `src/goose_adapter.rs:14450-14453` |
| Manifest-direct execution (D2 enabler) | `src/goose_adapter.rs:10387-10400`, `:28565` |
| Tool-policy enforcement inspector | `src/goose_adapter.rs:35434-35495` |
| Fail-closed unenforceable-policy refusals | `src/goose_adapter.rs:35306-35331`, `:35334-35361` |
| `permissions.mode` → GooseMode (4 arms + Auto default) | `src/goose_adapter.rs:35824-35855` |
| `GooseMode::default() == Auto` | `goose/crates/goose-provider-types/src/goose_mode.rs:24-27` |
| `BudRunPlan` / lineage / interrupts / checkpoints / artifacts | `src/lib.rs:8629` / `:8731` / `:8851` / `:8880` / `:8900` |
| `RunInputMetadata.kind` hardcoded `"text"` | `src/lib.rs:8723`; `src/run_planning.rs:2419-2422` (+6 more sites) |
| Run authorization evidence chain | `src/run_authorization_evidence.rs:363-373` |
| `RegistryEntry` / `BudAgentRecord` / release coordinate | `crates/bud-agent-types/src/lib.rs:756` / `:679` / `:962` |
| Access envelope constants | `crates/bud-agent-types/src/lib.rs:5-15` |
| Registry entry build from package | `src/registry_sources.rs:383-437` |
| Derived capability index | `src/registry_sources.rs:1490-1530` |
| Registry metadata needs a compiled recipe | `src/registry_sources.rs:1612` |
| Name slugification (lossy, 64-char) | `src/runtime_validation.rs:1481-1530` |
| Generated SDK schema for the Agent manifest (drifted) | `src/sdk_codegen.rs:11030-11117`; `strict_sdk_object` `:24373-24377` |
| Default agents workspace / `bud agents` subcommands | `src/bin/bud.rs:9669` / `:6177-6193` |
| `bud agents run` backends | `src/bin/bud.rs:2184`, `:2211-2318` |

**`LIVE` reproductions** (all run against `target/debug/bud` at `1a91f50`, scratch
dir `/tmp/claude-1000/-home-bud-ditto-agent-inter-op/a71e8707-…/scratchpad`):

| # | Command | Result |
|---|---|---|
| L1 | `bud agents validate doc_example.yaml` (the doc's Canonical Declarative Shape) | `invalid Bud manifest: Agent manifest contains unsupported field at spec.memory` |
| L2 | same, `spec.memory` removed | valid; warns `spec.runtime.goose is not a recognized runtime option and is ignored`; `output: {text: true}` accepted as `output.schema` |
| L3 | `bud agents normalize pactish.yaml` with `apiVersion: pact.dev/v1` | accepted, echoed verbatim |
| L4 | same with `metadata.version: 1.2.3` | `Agent manifest contains unsupported field at metadata.version` |
| L5 | `metadata.name: "Análisis de Ventas"` | → `an-lisis-de-ventas`, displayName preserved |
| L6 | `bud agents normalize sec.yaml` (context + security + budgets) | all three normalize; `egress: block` → `deny` |
| L7 | `export --target goose-custom-agent` → `import-goose-agent` | **context, security, budgets all gone, no warning**; `spec.runtime.gooseCustomAgent` added and then warned about as a typo |
| L8 | `export --target ossa` | only `version: 1.0.0`; no budgets/security/context |
| L9 | `export --target a2a` | `version: "1.0.0"`, `defaultInput/OutputModes` hardcoded |
| L10 | `bud agents normalize` with the documented `spec.context: {hints,…}` | **validates, silently discarded in full** |
| L11 | same with the documented `spec.security: {promptInjection: {enabled,…}}` | `spec.security.promptInjection must be a boolean` |
| L12 | same with `permissions: {mode: readonly, rules: {allow, deny}}` | **`rules` preserved verbatim in the canonical manifest**; OSSA exports `autonomy.level: supervised` |
| L13 | `bud agents run sec.yaml --workspace ws` | wrote `ws/packages/.bud-package-objects/<digest>/{README.md, agent.bud.yaml, .well-known/agent-card.json, recipes/*.goose.yaml, portable/agent.ossa.yaml, .agents/agents/*.md}` + `registry.json` + leases, **before** failing on the missing `goose` binary |
| L14 | inspect generated `ws/registry.json` | `id: bud:sec-agent`, `_budAgentAccessV1` envelope, `budPackageDigest`, `budPackageObjectDigest`, `budPackageObjectSchema: bud.runner-package-tree.v2`, `gooseRecipeAcceptsBudPrompt: "true"`, derived `capabilities: ["model:default"]` |

---

## 7. OPEN QUESTIONS FOR THE ARCHITECTURE DOC

1. Does the PACT canonical digest **become** the registry revision, or do the two
   coexist in `pact.lock`? (Affects B8, B9, and every pinned A2A card URL.)
2. Is `AgentBlueprint` deleted, or preserved as a PACT profile/template? D14
   argues for deletion — the blueprint provably cannot express `budgets`,
   `context`, or `security` — while the shipped SDK surface argues for
   preservation.
3. Does PACT own a **trace store**, given the run ledger deliberately excludes
   prompts and raw output (§2.4) and Eval recovery explicitly refuses to keep
   them? Without one, T6 learning has no input.
4. Is `kind: Channel` specified by PACT or declared out of scope under D24? The
   HTTP surface now exists (`6a56d45`) but no manifest kind does.
5. Where does `permissions.mode` land once it is admitted to be non-enforcing and
   *unsafe-by-default* — a profile default that expands into the tool-permission
   projection, or a deprecated field with a hard converter error?
6. Does PACT's `metadata.name` allow `/` (namespace) — today a hard validation
   error — or does namespace get its own field? And what is the ASCII-only
   slugification policy for a non-English domain expert (D13/D21)?
7. Does PACT adopt the runtime's **refuse-what-you-cannot-enforce** rule as a
   universal invariant? If yes, resolve-time substrate capability checking becomes
   mandatory for guardrails, budgets, security, memory, and modality — not just
   tool policy. If no, PACT inherits the silent-drop class of bug it exists to
   eliminate.
8. `spec.context.moim` and `spec.security.*` are **per-session** state the host
   sets before the first turn. Which PACT layer owns them — Strategy (they change
   behaviour) or Policy (they are governance)? The answer decides whether they are
   optimisable by the learning loop.
