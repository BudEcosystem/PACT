# Vercel `eve` — line-by-line teardown

**Research stream:** `eve-teardown`
**Date:** 2026-07-26 (Part I) · **2026-08-07 (Part II — second independent pass, §12–§17)**

> **Reading order.** Part I (§0–§11) is the first pass. Part II (§12–§17) is a
> **second, independent source read** done without consulting Part I first, then
> reconciled against it. Part II records (a) which Part I claims I re-verified
> line-by-line, (b) findings Part I does not contain, and (c) the small number of
> places I would sharpen Part I's wording. Nothing in Part I was found to be
> wrong. Where Part II and Part I overlap, Part I stands.
**Target:** `/home/bud/ditto/agent-inter-op/research/repos/frameworks/vercel-eve`
**Version read:** `eve@0.27.6`, Apache-2.0, HEAD `05f3480` (2026-07-25, "Version Packages (#1176)")
**Source read:** `packages/eve/src/**` (~351k LOC incl. tests; ~1005 non-test `.ts` files). Docs read only to find claims, then verified against source.

> **Evidence discipline.** Every claim below cites `file:line` relative to
> `/home/bud/ditto/agent-inter-op/research/repos/frameworks/vercel-eve/`.
> Claims marked **[INFERRED]** were not directly observed in a single site and
> are reasoned from the code I did read; everything else was read in source.
> Where docs and source could disagree, source wins and I say so.

---

## 0. Executive summary (for the impatient)

eve is the **best existing proof that path-as-identity works as an authoring
surface**, and simultaneously the **cleanest possible demonstration of why a
fixed slot table plus a TypeScript-only escape hatch cannot reach PACT's
no-code ceiling**.

Five structural facts dominate everything else:

| # | Fact | Where |
|---|---|---|
| S1 | The runtime **never reads the authored tree**. It loads `.eve/compile/compiled-agent-manifest.json` + `.eve/compile/module-map.mjs`. A build is a *prerequisite*, not an optimisation. | `src/runtime/loaders/manifest.ts:37-67`, `src/runtime/loaders/module-map.ts:37-72` |
| S2 | The tree→graph step is **code generation**: `module-map.mjs` is emitted with `import * as module_N from "…"` for every module-backed slot. The object graph exists only because a JS engine evaluated generated ESM. | `src/compiler/module-map.ts:65-112` |
| S3 | The compiler **executes author code at build time**, after bundling each authored module with rolldown. `agent.ts`, every tool, channel, connection, schedule, sandbox, subagent config is imported and its default export called. | `src/compiler/normalize-helpers.ts:40-60`, `src/internal/authored-module-loader.ts:1-90` |
| S4 | Exactly **three slots accept Markdown**: `instructions`, `skills`, `schedules`. Everything else — agent config, tools, connections, channels, hooks, sandbox, subagents, extensions, evals — is TypeScript-only. | `src/discover/filesystem.ts:7-14`, `src/internal/helpers/markdown.ts` |
| S5 | The harness loop is a **closed constant**. `createToolLoopHarness` has one call site, takes no loop shape, and hooks are documented and implemented as observe-only. | `src/execution/node-step.ts:84-96`, `src/public/definitions/hook.ts:96-101` |

S1+S2+S3 together mean: **eve's "filesystem-native" is a compile-time story, not
a runtime story.** PACT decision D2 ("the runtime reads the tree; deleting
`canonical.json` must be harmless") is a *different architecture*, not a
refinement of eve's.

---

## 1. (a) The discovery / loader algorithm

### 1.1 Pipeline shape

```
resolveDiscoveryProject(startPath)     → { appRoot, agentRoot, layout }
  └─ discoverAgent({appRoot, agentRoot, source, role})
       → AgentSourceManifest            (pure refs; NO author code executed)
  └─ compileAgentManifest(manifest)
       → CompiledAgentManifest          (author code IS executed here)
  └─ materializeWorkspaceResources()    (copies skill/workspace bytes into .eve)
  └─ createCompiledModuleMapSource()    (emits module-map.mjs)
  └─ writeCompilerArtifacts()           (5 files under .eve/)
```

Entrypoints: `src/compiler/compile-agent.ts:76` (`compileAgent`) and
`src/compiler/compile-agent.ts:92` (`compileAgentInWorkspace`). Both are called
from `src/internal/nitro/host/prepare-application-host.ts:56` (dev) and `:111`
(production) — **the dev server compiles too**, into an isolated workspace with
a staged "generation". There is no interpret-the-tree path anywhere.

### 1.2 Root resolution (`src/discover/project.ts:52-103`)

Walks upward from `startPath` (default `process.cwd()`), and at each directory
tries three rules in order:

1. **Nested-from-agent-dir** (`:116-135`): `basename(dir) === "agent"` **and**
   the parent contains a project marker → `{agentRoot: dir, appRoot: parent, layout:"nested"}`.
2. **Nested-from-app-root** (`:137-156`): dir contains a project marker **and**
   `dir/agent` exists → `{agentRoot: dir/agent, appRoot: dir}`.
3. **Flat** (`:158-167`): any entry in dir classifies as a known agent-root slot
   other than `unknown`, `ignored-directory`, or `lib-directory` →
   `{agentRoot: dir, appRoot: dir, layout:"flat"}`.

Project markers are exactly `["package.json", "vercel.json"]`
(`src/discover/filesystem.ts:20`). Failure throws
`DiscoveryProjectResolutionError` with code `discover/project-not-found`
(`:96-102`).

**Notable:** the flat rule fires on the *presence of any recognised slot name*.
A directory containing only `tools/` is an agent root. This is loose but it is
what makes `agent/instructions.md` alone a valid agent.

### 1.3 `discoverAgent` — the normative walk (`src/discover/discover-agent.ts:90-369`)

One `readdir` of the agent root, sorted by `localeCompare`
(`src/discover/grammar.ts:170-179`) — **sort order is `localeCompare`, not
byte order**, which is locale-sensitive and a real determinism hazard for a
digest-addressed IR. Then, in fixed source order:

| Order | Slot | Function | Recursive |
|---|---|---|---|
| 1 | unsupported-dir warnings | `createUnsupportedRootDirectoryDiagnostics` (`grammar.ts:549`) | — |
| 2 | `instructions` | `discoverInstructionsSource` (`grammar.ts:192`) | no (dir walk is flat) |
| 3 | `agent.{ts,…}` | `discoverFlatModuleSource` (`grammar.ts:364`) | — |
| 4 | `channels/` | `discoverNamedSourceDirectory` | yes |
| 5 | `lib/` | `discoverLibSources` | yes |
| 6 | `schedules/` | `discoverScheduleSources` | yes (md+ts) |
| 7 | `connections/` | `discoverConnectionSources` | file+folder forms |
| 8 | `sandbox` | `discoverSandboxSource` | — |
| 9 | `tools/` | `discoverNamedSourceDirectory` | yes |
| 10 | `hooks/` | `discoverNamedSourceDirectory` | yes |
| 11 | `extensions/` | `discoverNamedSourceDirectory` | **no** |
| 12 | `skills/` | `discoverSkills` | flat + package dirs |
| 13 | `subagents/` | `discoverSubagents` | yes (recursive agents) |
| 14 | extension mounts | `collectExtensionMounts` (`:435`) | — |
| 15 | root-namespace collision check | `detectRootNamespaceCollisions` (`:529`) | — |
| 16 | resolve + recurse into each mount | `discoverAgent({role:"extension"})` (`:299`) | — |

Discovery is **purely structural**: it produces `SourceRef` values
(`{sourceKind, logicalPath, sourceId, exportName?}`) and never imports a module.
Markdown *is* read and lowered during discovery (`discoverMarkdownSource`), which
is why markdown slots carry a `definition` while module slots do not.

### 1.4 The generic directory walker (`src/discover/named-source-directory.ts`)

Shared by `tools/`, `channels/`, `hooks/`, `lib/`, `schedules/`, `instructions/`,
`extensions/`. Behaviour worth recording:

- Missing directory → silent `{diagnostics:[], sources:[]}` (`:132-134`).
- Present but not a directory → one error diagnostic (`:136-147`).
- Walk order is **subdirectories first, depth-first, then leaves at each level**
  (`:216-224`) — so `sources` order is *not* lexicographic overall.
- `validateSegment` runs on every subdirectory name *and* every leaf slot name;
  a failing segment drops the candidate and emits a diagnostic (`:239-244`, `:339-350`).
- **Unrecognised leaf files are silently ignored** unless the caller passes
  `unsupportedFileCode`. The comment at `:61-69` says this is deliberate for
  `tools/`, `channels/`, `hooks/` "so authors can drop incidental files into
  those directories without build errors". Only `schedules/` opts into strictness
  (`src/discover/schedules.ts:61-64`). **A `tools/search.yaml` is silently
  invisible.**

### 1.5 Compilation (`src/compiler/normalize-manifest.ts:35-286`)

`compileAgentManifest` walks the source manifest and, per slot, calls
`loadModuleBackedDefinition` (`src/compiler/normalize-helpers.ts:40-60`), which
`loadAuthoredModuleNamespace(path)` → rolldown-bundles the module into
`node_modules/.cache/eve/authored-modules/<hash>.mjs` → dynamic-`import()`s it →
`materializeAuthoredModuleExport` (calls it if it's a factory). Errors are
wrapped with the authored file path.

Consequences:
- **Compilation requires Node + a bundler and executes arbitrary author code.**
- A tool's `inputSchema`/`description` is only knowable by running the module.
- The AST of dynamic-tool files is *rewritten* to hoist inline `execute`
  functions into module-scope durable steps
  (`src/internal/workflow-bundle/dynamic-tool-transform.ts:1-27`), with a stated
  limitation: `execute: myFn` (a reference, not a literal) is **not detected**,
  "the tool works on the first workflow step but is not replayable" — a silent
  durability hole.

### 1.6 Artifacts (`src/compiler/artifacts.ts:116-253`)

```
<appRoot>/.eve/
  discovery/agent-discovery-manifest.json   (AgentSourceManifest, v12)
  discovery/diagnostics.json                (kind eve-discovery-diagnostics, v1)
  compile/compiled-agent-manifest.json      (CompiledAgentManifest, v36)
  compile/compile-metadata.json             (kind eve-compile-metadata, v5)
  compile/module-map.mjs                    (generated ESM)
  compile/workspace-resources/<nodeId>/...  (skill + sandbox-workspace bytes)
  cache/model-catalog.json                  (AI Gateway catalog cache)
```

`compile-metadata.json` carries `sha256` per artifact plus a composite
`discovery.sourceGraphHash = sha256(manifestHash:diagnosticsHash:moduleMapHash)`
(`:188`). That is a real content-addressed identity for the build — a good idea
PACT should copy, but note it hashes the **derived** artifacts, not the tree.

**Schema version churn is instructive:** compiled manifest is already at **v36**
and discovery manifest at **v12** for a 0.27.x product
(`src/compiler/manifest.ts:44`, `src/discover/manifest.ts:23`). Every new slot or
field bumped a monolithic version. This is exactly the cost PACT's Expansion Rule
is meant to avoid.

---

## 2. (b) The authored slot table — exhaustive

`classifyAgentRootEntry` (`src/discover/filesystem.ts:127-206`) is the whole
grammar. **Adding a slot means editing this function** — there is no registry, no
schema-driven expansion.

### 2.1 Root agent slots

| Slot | Forms accepted | Required | Markdown? | Identity | Collision rule |
|---|---|---|---|---|---|
| `instructions` | `instructions.md`, `instructions.{ts,cts,mts,js,cjs,mjs}`, `instructions/` dir (flat, md+module), legacy `system.*` | **yes** at root; optional for subagents/extensions | **yes** | path | md+module same base → `discover/slot-collision` error; 2 modules → `discover/module-slot-collision` |
| `agent.{ts,…}` | flat module only | no (defaults to `{model: DEFAULT_AGENT_MODEL_ID}`) | no | — | 2 modules → error |
| `tools/` | `<name>.{ts,…}`, recursive | no | **no** | filename verbatim = model tool name | md+module → error; unknown files **silently ignored** |
| `channels/` | recursive modules; segments may be `[param]` or `.dotted` | no | no | dir path → channel name; URL from module's `routes[].path` | as above |
| `hooks/` | recursive modules | no | no | path slug | as above |
| `connections/` | `<name>.ts` **or** `<name>/connection.ts` | no | no | basename or dirname | file+folder both → `discover/connection-file-folder-collision`; empty folder → `discover/connection-folder-empty` |
| `skills/` | `<name>.md`, `<name>.{ts,…}`, `<name>/SKILL.md` (+ `scripts/`, `references/`, `assets/`) | no | **yes** | dirname/basename; frontmatter `name` **silently ignored** | duplicate id → error **and both dropped** (`src/discover/skills.ts:117-130`) |
| `schedules/` | `<name>.{ts,…}` or `<name>.md` with `cron:` frontmatter, recursive | no | **yes** | relative path minus ext | strict: unknown files error |
| `sandbox` | `sandbox.{ts,…}` or `sandbox/sandbox.{ts,…}`; plus `sandbox/workspace/` bytes | no | no | singleton | — |
| `subagents/` | `<id>.{ts,…}` (single-file) or `<id>/` package with **required** `agent.{ts,…}` | no | no | dirname/basename = tool name, **no prefix** | subagent name vs tool name → build rejected (docs `subagents.mdx`) |
| `extensions/` | `<ns>.{ts,…}` or `<ns>/extension.{ts,…}` (+ override slots) | no | no | mount filename = namespace | both forms → `discover/extension-mount-ambiguous` |
| `lib/` | recursive modules; **not** a runtime slot | no | no | — | — |
| ignored dirs | `.eve .next .output .vercel node_modules` | — | — | — | `src/discover/filesystem.ts:23-29` |
| anything else | — | — | — | — | **warning only**: `discover/unsupported-directory` (`grammar.ts:549-572`) |

### 2.2 Name charsets (`src/discover/grammar.ts:119-149`)

| Slot | Pattern |
|---|---|
| tool | `/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/` — verbatim model tool name, no normalisation |
| connection | `/^[a-z][a-z0-9-]{0,63}$/` |
| channel segment | `/^(\.?[a-z][a-z0-9-]{0,63}\|\[[a-zA-Z][a-zA-Z0-9_]{0,63}\])$/` |
| hook segment | `/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/` |
| extension mount | `/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/` |
| skill / subagent | **no pattern at all** — any directory name is accepted |

Skills and subagents having *no* charset validation while tools have a 64-char
ASCII rule is an inconsistency, and subagent names land in the same model tool
namespace as tools (`src/execution/node-step.ts:203-224`).

### 2.3 Precedence and conflict resolution — the complete rule set

1. **Markdown vs module in one slot** → hard error `discover/slot-collision`.
   Never "markdown wins" or "module wins".
2. **Two module extensions, same base** → hard error
   `discover/module-slot-collision`. `tool.ts` + `tool.js` is fatal.
3. **Flat `instructions.md` + `instructions/` directory coexist.** The flat file
   is `unshift`ed to the front (`grammar.ts:225-232`), directory entries follow
   in `localeCompare` order. All static entries are then joined with `"\n\n"`
   (`normalize-manifest.ts:225-240`). **There is no way to control ordering
   beyond filename sorting.** This is the single most fragile authoring rule in
   the system: a prompt's meaning depends on lexical filenames.
4. **Authored tool over framework tool.** A file at `tools/write_file.ts`
   replaces the built-in of that name; `disableTool()` sentinel removes it;
   a filename matching no known framework tool → build error (docs
   `concepts/default-harness.md`, enforced via `getAllFrameworkToolNames()`
   at `src/runtime/framework-tools/index.ts:70-81`).
5. **Dynamic tools override same-named authored tools at runtime**
   (`src/harness/tool-loop.ts:843-846`, comment: "Dynamic tools override a
   same-named authored tool"). This is a *runtime* precedence rule invisible to
   the compiled manifest.
6. **Extension composition is first-registration-wins**, iterated over mounts
   sorted by namespace (`normalize-manifest.ts:186-223`). Duplicate composed
   names from two extensions: the alphabetically-first namespace wins **silently**.
7. **Consumer overrides beat the extension** they override, implemented by
   listing overrides first into the same first-wins merge
   (`src/compiler/normalize-extension.ts:79-87`).
8. **Root-level `<ns>__…` names are rejected** when `<ns>` is a mounted extension
   (`discover-agent.ts:529-553`) — overriding must be co-located in the mount dir.
9. **Extensions may not mount extensions** — hard error
   `discover/extension-nested-mount-unsupported` (`discover-agent.ts:276-284`).
10. **Extensions may not declare `agent.ts`, `sandbox`, or `schedules`** — three
    hard errors (`discover-agent.ts:165-196`).
11. **Subagents may not declare `schedules/`** —
    `discover/local-subagent-schedules-invalid` (`discover-subagent.ts:317-337`).
12. **Errors are fail-closed, unknown directories are fail-open.** `hasDiscoverErrors`
    throws `CompileAgentError` after artifacts are written
    (`compile-agent.ts:142-153`); unknown root dirs are only warnings.

**Verdict on the slot table:** the *rules* are good — mostly fail-loud, mostly
explicit. The *architecture* is a hand-maintained switch statement with 18
`AgentRootEntryKind` variants and a parallel 16-variant
`LocalSubagentEntryKind` that must be kept in sync by hand
(`filesystem.ts:39-78`). They already drifted: subagents get
`invalid-schedules-directory` where root gets `schedules-directory`, and
subagents silently lack `channels` and `extensions`.

---

## 3. (c) Identity: how it is derived, and where it breaks

### 3.1 Derivation

- **Agent identity** = `deriveAgentIdFromRoots(appRoot, agentRoot, packageName)`
  (`src/discover/manifest.ts:350-366`):
  - agentRoot == appRoot, or agentRoot == `<appRoot>/agent` →
    `packageName ?? basename(appRoot)`
  - otherwise → `basename(agentRoot)`
  `packageName` is `package.json#name` with the npm scope stripped
  (`discover-agent.ts:579-598`). The compiled config's `name` is exactly this
  (`normalize-agent-config.ts:86`).
- **`PublicAgentDefinition` has no `name` field at all**
  (`src/shared/agent-definition.ts:251-256`: "Authored definitions do not carry a
  `name` field"). `defineAgent` uses `ExactDefinition`, so authoring `name:`
  is a *compile error*.
- **Source identity** = `createPathDerivedSourceId(logicalPath)` = the
  normalised logical path, verbatim (`manifest.ts:371-373`). No hash, no
  namespace.
- **Subagent node id** = `sourceId` at depth 1, `parent::sourceId` deeper
  (`src/compiler/manifest.ts:898-904`).
- **Tool name** = filename slug verbatim (`grammar.ts:112-119`, explicitly: "The
  model-facing tool name is the filename slug verbatim — there is no authored
  `name` override and no compile-time normalization").

### 3.2 Where it breaks — verified

| # | Break | Evidence |
|---|---|---|
| I1 | **No version, namespace, owner, or stable GUID anywhere.** The agent's whole identity is one string derived from a directory name. Two agents named `support` in different repos are indistinguishable. | `shared/agent-definition.ts:257-300` (full field list), `manifest.ts:350-366` |
| I2 | **CI path leakage was a real bug they patched around.** `packageName` exists precisely because builds in `/vercel/path0` produced the agent id `"path0"` (`manifest.ts:250-256`, `:346-349`). The fallback chain is still `packageName → basename(appRoot) → basename(agentRoot)`; with no `package.json` the CI path still wins. | `manifest.ts:250-256` |
| I3 | **Renaming a directory silently re-identifies everything.** `sourceId` is the path; the module map is keyed by `sourceId`; durable session state and approvals key off tool names. Renaming `tools/search.ts` → `tools/find.ts` is, to the model and to every persisted approval, a *different tool*. Nothing warns. | `manifest.ts:371-373`, `module-map.ts:295-323` |
| I4 | **Extension state namespace ≠ mount namespace, deliberately.** `packageNamespace` scopes durable state to the *package* so "a consumer renaming the mount file cannot orphan persisted state" — an explicit admission that path-derived identity is unsafe for stateful things. | `src/compiler/manifest.ts:689-707` |
| I5 | **Channel identity is split.** The channel *name* is path-derived; the channel *URL* comes from `routes[].path` inside the module. Path-as-identity does not hold for the externally visible surface. | `src/compiler/normalize-channel.ts:34-60` |
| I6 | **Subagents share the tool namespace with tools**, with no prefix, so `subagents/researcher/` and `tools/researcher.ts` collide and the build is rejected rather than disambiguated. | docs `subagents.mdx`; `node-step.ts:163-197` |
| I7 | **Skill frontmatter `name` is parsed and silently discarded** for Agent-Skills-ecosystem compatibility. An imported skill whose `name` differs from its directory is silently renamed. | `src/internal/helpers/markdown.ts` (`IGNORED_SKILL_FRONTMATTER_KEYS = ["name"]`) |
| I8 | **Directory sort is `localeCompare`.** Instruction concatenation order — hence prompt semantics — is locale-dependent. | `grammar.ts:170-179` |

---

## 4. (d) Durable execution model and its coupling to Vercel Workflow

### 4.1 The model

Three nesting levels: **session** (durable conversation) ⊃ **turn** (one user
message and everything it triggers) ⊃ **step** (one model call + its tool calls).

- `turnWorkflow(rawInput)` carries `"use workflow"`
  (`src/execution/turn-workflow.ts:52-62`) and contains a plain
  `while (true) { const result = await turnStep(...) }` loop
  (`:107-211`).
- `turnStep(rawInput)` carries `"use step"`
  (`src/execution/workflow-steps.ts:133-134`) and is the durable checkpoint.
- The inner model call is pinned to exactly one step:
  `stopWhen: isStepCount(1)` on the `ToolLoopAgent`
  (`src/harness/tool-loop.ts:907`). **The AI SDK's own multi-step loop is
  deliberately disabled** and replaced by the durable outer loop. This is
  effectively *harness lowering over the Vercel AI SDK* — the same move PACT
  D12 mandates, done by the closest prior art. Strong external validation.
- Turn results are a four-way union: `done`, `park`, `cancelled`,
  `dispatch-workflow-runtime-actions` (`workflow-steps.ts:~100-127`).
- Parking is durable and compute-free: HITL approval, OAuth, subagent waits.
- Cancellation is a session-scoped hook `{sessionId}:cancel` that aborts the
  serialized `AbortSignal` and settles as `turn.cancelled → session.waiting`,
  never as failure (`turn-workflow.ts:43-50`, `:96-129`).
- 49 non-test files carry `"use step"` / `"use workflow"` directives — the
  directive is pervasive, not isolated to one module.

### 4.2 Coupling to Vercel — the honest assessment

**It is less coupled than it looks, but the seam is a vendored beta protocol.**

- The Workflow SDK is open-source (`workflow-sdk.dev`) and eve vendors
  `@workflow/{core,errors,serde,utils,world,world-local,world-vercel}` at
  `5.0.0-beta.*` into `#compiled/*` (`packages/eve/package.json`
  devDependencies; `scripts/vendor-compiled/@workflow`). Runtime `dependencies`
  is literally `{"nitro": "..."}` — one entry.
- **A local, offline "world" exists and is the dev/self-host default**: it
  persists runs on disk at `.eve/.workflow-data` via
  `@workflow/world-local` with `dataDir: resolveLocalWorkflowWorldDataDirectory(process.cwd())`
  (`src/internal/application/compiled-artifacts.ts:246-275`).
- The world is swappable by package name from `agent.ts`:
  `experimental.workflow.world: "@workflow/world-postgres"`
  (`src/shared/agent-definition.ts:221-229`), validated at boot against the
  vendored protocol version (`src/internal/workflow/validate-world.ts:33-58`,
  `isWorkflowWorld` requires `createQueueHandler`, `events`, `specVersion`).
- Vercel-specific behaviour is genuinely additive: `deploymentId: "latest"`
  routing, dashboard run metadata
  (`src/execution/workflow-runtime.ts:59-104`).
- **But**: `nitro` is a hard runtime dependency and hosts every route and the
  workflow entrypoints; the build emits a Nitro function directory and a
  Vercel-shaped workflow output
  (`src/internal/workflow-bundle/vercel-workflow-output.ts`,
  `nitro-step-entry.ts`). Deployment portability is "any Node host that can run
  a Nitro build", not "any runtime".

**Verdict:** the durable-execution *semantics* (session/turn/step, park, resume,
cancel, one-model-call-per-step) are portable and worth copying wholesale.
The *implementation* is bound to a `5.0.0-beta` protocol from one vendor,
vendored by SHA into the package. For PACT: specify the semantics in the IR
(P-5), adapt to Temporal/Restate/DBOS/Bud-ledger; do not adopt the protocol.

---

## 5. (e) The default harness loop — is it modifiable?

**No. Not at all, by design.**

### 5.1 What the loop does (`src/harness/tool-loop.ts:467-1300`, 2547 lines)

Fixed sequence per step:
1. Open/restore OTel turn span (`:480-511`).
2. Consume deferred step input; resolve pending **runtime actions**; may park (`:531-542`).
3. Two-pass stale-response handling — drop session-limit continuations, convert the rest to plain user text (`:544-560`).
4. Resolve pending HITL/approval input; may park; emit rejected `action.result` events for denials (`:562-607`).
5. Emit turn preamble (`:611-623`).
6. Apply session-limit continuation (fresh budget or end session) (`:630-640`).
7. Append `context` entries and the user message; **stage attachments into the sandbox**, replacing bytes with `eve-sandbox:` URLs (`:642-657`).
8. Dispatch dynamic-model event; resolve the active model (`:662-683`).
9. Detect prompt-cache path; get an Anthropic cache marker (`:682-683`).
10. **Compaction** (`maybeCompact`, `:691-702`), before the model call so compacted messages flow into history.
11. Hydrate sandbox attachment refs back to bytes *for this call only* (`:723`).
12. Split system messages out (AI SDK rejects `role:"system"` in `messages`), append dynamic instructions and a pending skill announcement (`:727-747`).
13. Build the toolset: advertised authored tools → provider tools → dynamic tools (override authored) → `final_output` when an output schema is set (`:819-851`).
14. Apply the *last-tool* cache breakpoint (`:876`).
15. Construct `ToolLoopAgent` with `stopWhen: isStepCount(1)` and run (`:887-912`).
16. Recovery pipeline: transient retry, unsupported-provider-tool recovery (drop the tool, re-call), empty-response recovery (`:1501-1785`).
17. `handleStepResult` decides `done` / `park` / continue (`:1786-2063`).

### 5.2 The extension points that exist

| Surface | Can it change loop control flow? | Evidence |
|---|---|---|
| `hooks/` (`defineHook`) | **No.** 28 typed events + `*`; docs and types say "Handlers are observe-only: they cannot inject model context." Handlers return `void \| Promise<void>`. | `src/public/definitions/hook.ts:18-49`, `:96-101` |
| `defineDynamic` in `instructions/` | Injects `system` messages per event. Content only. | `src/compiler/normalize-instructions.ts:74-91`; consumed at `tool-loop.ts:737` |
| `defineDynamic` in `tools/`, `skills/` | Changes the tool/skill *set* per event. | `manifest.ts:192-217` |
| Dynamic model | Changes the model per step. | `tool-loop.ts:663-681` |
| `compaction.thresholdPercent`, `compaction.model` | Two numbers. "There is no per-tool hook to configure" compaction behaviour. | `shared/agent-definition.ts:100-146`; docs `concepts/default-harness.md` |
| `limits.max{Input,Output}TokensPerSession` | Budget only. | `shared/agent-definition.ts:148-179` |
| `experimental_workflow` tool | Lets the **model** author JS that orchestrates subagents inside one durable step, capped at `maxSubagents` (default 100). Root-only. | `manifest.ts:183-185`, docs `concepts/default-harness.md` |

`createToolLoopHarness` has **exactly one non-test call site**
(`src/execution/node-step.ts:84-96`) and its config accepts:
`abortSignal, capabilities, workflow, workflowMaxSubagents, handleEvent, mode,
onCompaction, dispatchDynamicModelEvent, resolveModel, runtimeIdentity, tools`.
**No loop program, no state machine, no step policy, no halt predicate, no
verifier, no self-consistency, no plan/execute phase.**

### 5.3 The only real loop-shaping lever

The `Workflow` tool — model-authored JavaScript that fans out to subagents.
That is *the model* writing the topology at runtime, in code, non-deterministic,
non-reviewable, non-portable. It is the opposite of PACT's "loop as authored
data" (G-3 / O5.2) and of D22/D23's reviewable-source requirement.

**Verdict: eve has zero loop engineering. The loop is a 2547-line constant.**

---

## 6. (f) Subagent isolation — and why "inherits nothing"

### 6.1 The two mechanisms

| | Built-in `agent` tool | Declared subagent |
|---|---|---|
| Where | root session only; auto-registered unless disabled (`node-step.ts:179-194`) | `agent/subagents/<id>/` |
| Config | none | **required** `agent.{ts,…}` with **required** `description` |
| Instructions | inherited (it *is* a copy) | own or framework default |
| Tools / connections / skills / hooks / sandbox | inherited | **own only** |
| History / state | fresh | fresh |
| Recursion | forbidden — copies never get `agent` | allowed; bounded only by the directory tree |
| Model tool name | `agent` | bare directory name, no prefix |

Enforced in source: `discoverLocalSubagentPackage` requires the config module
(`discover-subagent.ts:211-221`, diagnostic
`discover/required-subagent-config-module-missing`), and
`compileSubagent` throws when `description` is missing
(`normalize-subagent.ts:177-183`). `discoverSubagents` recurses into each
package's own `subagents/` (`discover-subagent.ts:276-281`), so nesting is
unbounded — "eve does not apply a separate depth limit; nesting ends where the
authored directory tree ends" (docs `subagents.mdx`), and
`subagent-depth.ts` only *tracks* depth for attribution, it does not cap it.

### 6.2 Why "inherits nothing" — the actual reason, from the code

The reason is **structural, not philosophical**: a declared subagent's directory
is discovered by *the same function as the root*, with the same
`AgentSourceManifest` shape (`discover-subagent.ts:283-303`). There is no merge
step anywhere in `normalize-subagent.ts` or `normalize-manifest.ts`. Inheritance
would require a slot-aware merge algebra (what does it mean to inherit
`instructions` when the child also has some? to inherit a `sandbox` when the
child declares one? to inherit half a tool?), and eve chose to have no merge
algebra at all.

The cost is stated plainly in their own docs (`docs/subagents.mdx`):

> "For a declared subagent this means duplicating anything the child needs. When
> two subagents need the same procedure, **copy the markdown under each
> `skills/` directory**, or share typed helpers via `lib/`."

Copy-paste as the sanctioned reuse mechanism. `lib/` (TypeScript) is the only
DRY escape hatch, and it is TypeScript-only, so **a non-programmer cannot share
anything between agents**. Extensions (npm packages) are the other reuse path,
and they too require TypeScript plus a publish step.

**This is the single clearest place PACT can beat eve on merit**: a declarative,
explicit composition operator (`extends:` / `include:` / profile layering) with
a specified merge algebra and a rendered "effective agent" view.

### 6.3 Isolation quality — what they got right

- Fresh `defineState` per child, always.
- Parent transfers data only through the `message` string; the child never sees
  parent history. Docs are explicit about the data-handling consequence.
- Cancellation propagates recursively to descendants
  (`cancelDescendantTurnsStep`, `turn-workflow.ts:118-121`).
- HITL/authorization events from descendants are proxied up to the root channel
  so one UI can answer for the whole tree
  (`runProxySubagentEventStep`, `turn-workflow.ts:297-306`).
- Child token budget is capped by the parent's remaining quota — "a child can
  never outspend its parent's budget" (`shared/agent-definition.ts:157-170`).
- Docs explicitly warn subagent delegation is **not** an approval boundary.

That set of guarantees is genuinely well-designed and PACT should adopt all of it.

---

## 7. (g) The eval runner architecture

### 7.1 Shape

```
eve eval [ids…] [--url REMOTE]
  discoverAndImportEvals(appRoot)      evals/**/*.eval.ts  → import → EveEval[]
  discoverEvalConfig(appRoot)          evals/evals.config.ts (REQUIRED)
  target = --url ? remote : createDevelopmentServer(appRoot, 127.0.0.1:0)
  resolveEvalTargetHandle()            poll /eve/v1/health (60s), GET /eve/v1/info,
                                       assert agent name matches package.json#name
  runEvals()                           bounded pool (default 8), reporters, artifacts
  exit 0 / 1 (failed, or --strict + scored) / 2 (config error)
```
`src/evals/cli/eval.ts:43-178`, `src/evals/runner/discover.ts`,
`src/evals/target.ts:19-44`, `src/evals/runner/run-evals.ts:55-145`.

### 7.2 The three architectural choices worth stealing

1. **Evals are black-box over the wire protocol.** The runner only ever speaks
   `/eve/v1/*` HTTP to a `Client`. The *same* eval file runs against a locally
   spawned dev server or a deployed URL with zero changes
   (`eval.ts:110-132`). This is precisely PACT's **AC-4.3** ("evals run
   identically against any adapter, and against a remote agent with no
   eval-file changes") — already proven to work.
2. **Eval identity is path-derived and authoring an `id`/`name` throws**
   (`define-eval.ts:30-41`). Array exports fan out to `<file-id>/0000`
   (`discover.ts:99-124`). Duplicate derived ids are a hard error (`:150-155`).
3. **A first-class mock model** (`src/evals/mock-model.ts`, 380 lines) with a
   normalised `MockModelRequest` (messages, userMessages, tools, toolResults) and
   a responder that can emit tool calls. This makes deterministic, offline,
   zero-cost eval of *loop behaviour* possible. PACT needs this for air-gapped
   CI (D17).

### 7.3 The assertion surface — complete inventory

**Structural (`src/evals/assertions/run.ts`, all deterministic):**
`succeeded`, `parked`, `messageIncludes`, `calledTool`, `notCalledTool`,
`loadedSkill`, `toolOrder`, `usedNoTools`, `maxToolCalls`, `calledSubagent`,
`noFailedActions`, `event`, `notEvent`, `eventOrder`, `eventsSatisfy`,
`outputEquals`, `outputMatches(StandardSchema)`.

**Value matchers (`src/evals/expect/index.ts`):**
`includes`, `satisfies`, `equals`, `matches`, `similarity`.

**LLM judges (`src/evals/judge.ts:66-86`) — exactly four**, all from
`autoevals`: `factuality`, `summarizes` (Summary), `closedQA`, `sql`.

**Severity model:** every assertion is a handle with `.gate(t)` / `.soft(t)` /
`.atLeast(n)` (`types.ts:150-165`). Judges default to **soft**; only `--strict`
turns a low score into exit 1 (`eval.ts:162-166`).

**Session driving:** `t.send`, `t.start`, `t.respond`, `t.respondAll`,
`t.sendFile`, `t.newSession`, `t.cancel`, `t.requireInputRequest`,
`t.dispatchSchedule`, `t.fetch`, `t.attachSession`, `t.watchTurn`
(`types.ts:244-431`). HITL and multi-session flows are genuinely first-class —
better than most eval frameworks.

### 7.4 What it cannot do

- **No config-only authoring.** `defineEval` requires `test(t)` to be a
  *function* (`define-eval.ts:83-85`) and they *removed* the declarative keys —
  `input`, `run`, `checks`, `scores`, `expected`, `thresholds`, `parseOutput`,
  `cases`, `requires` all now throw with migration guidance
  (`define-eval.ts:43-81`). **eve deliberately moved away from declarative evals
  toward imperative ones.** `loadYaml`/`loadJson` exist
  (`src/evals/loaders/`) but only as *data* loaders you call from inside `test`.
- **No RAG / groundedness metrics.** Four judges vs DeepEval's ~40. No
  faithfulness, answer relevancy, contextual precision/recall, hallucination,
  bias, toxicity, G-Eval, DAG, conversational metrics, or arena comparison.
- **No SLO assertions.** No TTFT/TPOT/E2E-latency/cost predicates anywhere in
  `src/evals/types.ts`. `--timeout` is a runner-level kill switch.
- **No dataset/case model.** "Each eval file is one case"; datasets are an
  array export from one file.
- **No trace→eval promotion.** No path from a production session to a case.
- **No optimiser.** Nothing consumes eval results to change the agent.
- **No statistical machinery** — no repeats, no seeds, no confidence intervals,
  no held-out splits.
- **Judge hardening: none.** Any model can judge; nothing prevents the agent's
  own model from judging itself.

---

## 8. Structural limitations blocking PACT's goals

Organised by the PACT goal each one blocks. Each is a *structural* limitation —
not a missing feature but a consequence of an architectural choice.

### L1 — Build is mandatory; the tree is not executable (blocks **D2**)

`loadCompiledManifest` reads `.eve/compile/compiled-agent-manifest.json` or
bundled artifacts and throws otherwise
(`src/runtime/loaders/manifest.ts:60-66`). `loadCompiledModuleMap` `import()`s
generated ESM (`src/runtime/loaders/module-map.ts:44-60`). Even `eve dev`
compiles into a staged workspace first
(`prepare-application-host.ts:33-99`). **There is no code path that interprets
the authored tree.**
→ PACT's derived index must be *optional*; the loader must be the runtime.

### L2 — Tree→graph is code generation, not data (blocks **D4** Rust core)

`createCompiledModuleMapSource` emits `import * as module_N from "..."` plus a
frozen object literal (`src/compiler/module-map.ts:97-111`). A Rust runtime can
read the JSON manifest but **cannot materialise a single tool, channel,
connection, hook, sandbox, or subagent config** without a JS engine, because
every one of them is a `sourceKind:"module"` ref whose value only exists after
ESM evaluation.
→ PACT's IR must carry *declarative* node bodies, with code as a typed,
out-of-process `ref:` (F-2), never as the default representation.

### L3 — Compile executes author code (blocks **D17** air-gap hygiene, **D23** governance)

`loadModuleBackedDefinition` bundles with rolldown and dynamic-`import()`s
(`normalize-helpers.ts:47-52`; `authored-module-loader.ts`). Validating an agent
requires running it. There is no static-only `validate`.
→ PACT `validate` must be pure: parse + schema + reference check, no execution.

### L4 — Markdown covers 3 of 13 slots (blocks **D13/D14** no-code ceiling)

`SUPPORTED_AUTHORED_MODULE_FILE_EXTENSIONS = [".cts",".mts",".cjs",".mjs",".ts",".js"]`
(`filesystem.ts:7-14`) — **no `.yaml`, no `.json`, anywhere.** Markdown lowering
exists only for instructions, skills, schedules
(`src/internal/helpers/markdown.ts`).

A non-technical author therefore **cannot**: add an MCP connection, add a tool,
add an eval, declare a subagent, configure a model, set a token limit, add a
channel, or configure a sandbox. Concretely, D14's target scenario — "a
multi-agent system with custom tools via MCP, their own eval cases, SLO limits,
and the learning loop enabled, entirely in YAML/Markdown" — is expressible in
eve at **0%**.
→ PACT: every slot needs a YAML form; TypeScript is one of several `ref:` kinds.

### L5 — No multi-agent topology; only a delegation tree (blocks **G-2 / O5.1**)

The compiled graph is `subagents: CompiledSubagentNode[]` + `subagentEdges:
{parentNodeId, childNodeId}[]` (`src/compiler/manifest.ts:662-682`) — a
**tree**, built from directory nesting, with one edge kind. Delegation is
lowered to a tool with a fixed `{message, outputSchema?}` schema
(`node-step.ts:203-224`).

Of PACT's eight required patterns: supervisor ✔ (as a tree), hierarchical ✔,
sequential pipeline ✘, parallel map-reduce ✘ (only "emit multiple `agent` calls
in one response" — model-decided, not declared), swarm/handoff ✘ (no peer
edges, no handoff), debate ✘, blackboard ✘ (no shared state — "`defineState` is
never shared"), market/auction ✘.

And "multi-agent" at the top level means **separate deployments**:
`apps/frameworks/next-multi-agent/package.json` builds each with
`cd agents/billing && eve build`; the README describes three independent agents
mounted at three URL prefixes. There is no workspace concept.
→ PACT needs a first-class topology graph with a closed set of node/edge kinds,
independent of directory nesting.

### L6 — Loop is a constant (blocks **G-3 / O5.2 / AC-5.2-3**)

See §5. Zero of PACT's six required loop patterns (ReAct, Plan-and-Execute,
Reflexion, ToT, self-consistency, CodeAct) is authorable. Hooks are observe-only
by type signature (`hook.ts:96-101`).

### L7 — No model abstraction; the catalogue is a network service (blocks **D8, D17, O3.\***)

- `model` is a gateway id string or an AI SDK `LanguageModel` instance
  (`shared/agent-definition.ts:53-56`). **No capability predicates, no tiers,
  no requirements, no alternatives, no cost/SLO model.**
- Context-window metadata comes from
  `https://ai-gateway.vercel.sh/v1/models/catalog`
  (`src/internal/gateway.ts:5,11`; `model-catalog.ts:215`), cached 24h at
  `.eve/cache/model-catalog.json`.
- The built-in offline fallback table has **exactly three models**:
  `anthropic/claude-opus-4.7`, `openai/gpt-5.4`, `openai/gpt-5.4-mini`
  (`model-catalog.ts:60-82`).
- The default model is `anthropic/claude-sonnet-5`
  (`src/shared/default-agent-model.ts`) — **not in that table**. So a *fresh,
  fully air-gapped* `eve build` of a default agent **fails**:
  `resolveModelsFromCacheOrFetch` returns `null`, the built-in lookup misses,
  and `withCompiledRuntimeModelLimits` throws "does not have known AI Gateway
  context window metadata" (`normalize-agent-config.ts:306-320`). The escape
  hatch is authoring `modelContextWindowTokens` by hand — i.e. TypeScript.
→ PACT D8's local-first authoritative catalogue is *mandatory*, and this is the
concrete failure it prevents.

### L8 — No inheritance, no composition primitive (blocks **D14, G-4**)

No merge algebra exists (§6.2). Sanctioned reuse is copy-paste of markdown or
TypeScript `lib/`. Extensions require an npm package, a TS mount file, and
cannot nest.

### L9 — Evals are imperative TypeScript, and became *more* so (blocks **G4/D19, O4.\***)

§7.4. They actively deleted the declarative form. Four judge metrics. No SLO
predicates, no datasets-as-data, no trace promotion, no judge hardening.

### L10 — No learning subsystem at all (blocks **D9, D22, D23, T6**)

Grep finds no optimiser, no variant, no candidate, no promotion, no
change-classification. Nothing writes back to author files. The agent is static
between commits.

### L11 — Contract-shaped fields do not exist (blocks **T1** Contract/Strategy split)

`PublicAgentDefinition` is 10 fields (`shared/agent-definition.ts:257-300`):
`description, build, compaction, experimental, model, modelContextWindowTokens,
modelOptions, reasoning, limits, outputSchema`.

Absent: name, version, namespace, owner; input schema (only *output*);
modalities; capability requirements; eval bindings; SLOs (TTFT/TPOT/E2E/cost);
policies/autonomy level; provenance/signing; temperature/topP/maxTokens (only
`providerOptions` per provider). There is nothing to *port*, because there is no
declared contract — only a strategy.

### L12 — TypeScript-only, single runtime (blocks **G1**, non-TS adapters)

Everything is `.ts/.js`; the loader bundles with rolldown; `nitro` is a hard
runtime dependency; the workflow bundler emits Nitro/Vercel output. Python
adapters (Pydantic AI, LangGraph, AutoGen, OpenAI Agents — PACT's primary
targets) have no ingress.

### L13 — Modality coverage is partial (blocks **D16**)

Only **two** media classes are first-class: `image/*` (inline up to 3 MiB) and
`application/pdf` (inline up to 20 MiB)
(`src/harness/attachment-staging.ts:45-54`). Everything else is staged to the
sandbox and substituted with a *text reference* to a file path, so the model
reaches it only through `read_file`/`bash`. The staging pipeline itself is good
(`tool-loop.ts:648-657`, `:723`).

**Audio/voice: nothing.** The only `audio/` and `video/` strings in non-test
source are Slack attachment *display* classification
(`src/public/channels/slack/attachments.ts:136-137`,
`src/public/channels/slack/inbound.ts:332-333`). No streaming audio I/O, no
duplex session, no TTFT-sensitive path, no SLO surface.
**Computer use: nothing.** Framework tools are `bash, read_file, write_file,
glob, grep, web_fetch, web_search, todo, ask_question, agent, load_skill,
connection_search` (`src/runtime/framework-tools/index.ts:24-39`) — no browser
driver, no screenshot loop, no coordinate-space actions.
No content-typed I/O contract exists at all: the interface is `message: string`
in, text or `outputSchema` out.

### L14 — Registry / multi-tenancy is out of scope (consistent with **D24**, noted for completeness)

There is no registry, no discovery service, no tenancy model. Multi-tenancy is
documented as a *pattern* (`docs/patterns/multi-tenant-*.md`) built from
per-session auth. eve made the same minimal choice D24 makes — mild
confirmation the seam is drawn in the right place.

### L15 — Determinism hazards in the loader

`localeCompare` ordering (`grammar.ts:176`); silently-ignored unknown files in
`tools/`/`channels/`/`hooks/` (`named-source-directory.ts:61-69`);
warning-only unknown root directories (`grammar.ts:549-572`); instruction
concatenation order driven by filenames. For a digest-addressed IR these are
correctness bugs, not style issues.

---

## 9. What is genuinely GOOD — keep these

Being fair: this is a well-built system with several ideas that are simply
correct and that PACT should adopt rather than reinvent.

| # | Idea | Evidence | Why it matters to PACT |
|---|---|---|---|
| G1 | **Path-as-identity, no redundant `name` fields.** Enforced to the point that authoring `name` is a *compile error* (`define-eval.ts:30-41`) and `defineAgent`'s `ExactDefinition` rejects it. | AGENTS.md principle 5; `shared/agent-definition.ts:251-256` | Eliminates a whole class of drift. PACT should keep it — and add explicit `id`/`version` *only* at the workspace/contract level where portability requires it. |
| G2 | **Minimum viable agent is one Markdown file.** `agent.ts` is optional (`discover-agent.ts:118-122`; default config at `normalize-agent-config.ts:38-40`); only `instructions` is required. | — | Directly satisfies PACT **O7.1** (≤5 lines, no code). Proven ergonomic. |
| G3 | **Harness lowering over the AI SDK.** `stopWhen: isStepCount(1)` disables the framework's own loop; eve owns the loop. | `tool-loop.ts:907` | Independent validation of PACT **D12/T3** by the strongest prior art. Cite it. |
| G4 | **Durable session/turn/step with park-and-resume as the default.** Kill-and-resume, cancellation as a first-class non-failure outcome, compute-free parking. | `execution/turn-workflow.ts:52-211` | Exactly PACT **P-5 / AC-2.6**. Adopt the *semantics* verbatim. |
| G5 | **Progressive skill disclosure.** Only `name: description (path)` in the system prompt; body loaded on demand via `load_skill`. | `execution/skills/instructions.ts:26-64`; `runtime/prompt/compose.ts:30-38` | Matches the in-repo hierarchical-routing result (full accuracy at ~15% tokens). Make it the default strategy, not an option. |
| G6 | **Swappable durable "world" by package name, protocol-version-checked at boot.** | `shared/agent-definition.ts:221-229`; `internal/workflow/validate-world.ts:33-58` | The right shape for PACT's runtime adapters — a named module + a validated capability protocol. |
| G7 | **Content-hashed build metadata.** Per-artifact `sha256` plus a composite `sourceGraphHash`. | `compiler/artifacts.ts:159-199` | PACT **O1.2** digest for lockfiles/signing. Copy, but hash the *tree*, not the derived files. |
| G8 | **Evals as black-box HTTP against a live target**, identical local and remote. | `evals/cli/eval.ts:110-132`; `evals/target.ts` | Delivers **AC-4.3** with no extra machinery. |
| G9 | **First-class mock model for deterministic eval.** | `evals/mock-model.ts` | Required for offline CI under **D17**. |
| G10 | **Rich structural (non-LLM) assertions**: tool order, tool count, subagent calls, skill loads, event order, no-failed-actions. | `evals/assertions/run.ts:37-360` | Directly serves **AC-4.5** (deterministic-first). Broader than DeepEval here — a genuine gap DeepEval does *not* cover. Keep both. |
| G11 | **Gate/soft/threshold severity per assertion** with `--strict` promotion. | `evals/types.ts:150-165`; `eval.ts:162-166` | Clean model for PACT's eval verdicts. |
| G12 | **Subagent guarantees**: fresh state always, no history leakage, recursive cancellation, HITL proxied to the root channel, child budget capped by parent's remainder. | `turn-workflow.ts:118-121`, `:297-306`; `shared/agent-definition.ts:157-170` | Adopt wholesale as PACT's isolation defaults. |
| G13 | **Attachment staging out of the message path.** Bytes go to the sandbox; messages carry `eve-sandbox:` refs; rehydration is per-call and transient. | `tool-loop.ts:648-657`, `:723` | The right answer for multimodal durable state (**D16**) — durable history never carries blobs. |
| G14 | **Diagnostics as data**: `{code, severity, message, sourcePath}` written to `diagnostics.json`, summarised, fail-closed on error. | `compiler/artifacts.ts:144-153`; `compile-agent.ts:142-153` | Close to PACT **O7.3**; add `line`, `rule`, and `fix` and it is there. |
| G15 | **Override / disable / add as three explicit verbs** for framework defaults, with a typo in a disable filename being a build error. | docs `concepts/default-harness.md`; `framework-tools/index.ts:70-81` | A clean, teachable model for PACT's default-tool surface. |
| G16 | **First-registration-wins with a deterministic sort** for extension composition, and co-location-required overrides. | `normalize-manifest.ts:179-223`; `discover-agent.ts:529-553` | A defensible precedence rule — but PACT must make the shadowing *reported*, not silent. |
| G17 | **One runtime dependency (`nitro`); everything else vendored.** | `packages/eve/package.json`; `scripts/vendor-compiled/` | Supply-chain posture worth imitating for an air-gapped core. |

---

## 10. Design implications for PACT (specific, actionable)

1. **Loader is normative and interprets the tree.** Specify `load(tree) →
   Document` as a pure function over a `ProjectSource`-like abstraction (eve's
   own `ProjectSource` seam at `src/discover/project-source.ts` is the right
   idea — it already lets discovery run against an in-memory tree). `.pact/`
   is a cache keyed by tree digest; deleting it changes nothing but speed.
2. **Every node kind must have a data body.** A `tool` is a document with
   `input_schema`, `output_schema`, `description`, and an `impl:` that is one of
   `{mcp, http, python, ts, wasm, prompt, builtin}`. Never make code the only
   representation — that is what makes L2/L3/L12 unavoidable.
3. **`validate` executes nothing.** Schema + reference + policy checks only.
   Code refs are checked for *existence and signature declaration*, not run.
4. **Replace the 18-variant switch with the Expansion Rule.** eve's
   `classifyAgentRootEntry` and its already-drifted subagent twin
   (`filesystem.ts:127-282`) are the concrete argument for T5. Also: their
   compiled-manifest schema hit **v36** because every slot addition bumped a
   monolith. Feature-gate per field instead (E-2).
5. **Canonical ordering must be byte-order, and explicit.** Ban `localeCompare`.
   Any multi-document field (instructions fragments, skills, tools) gets an
   explicit `order:` key with a specified default; sort ties by byte-order path.
6. **Fail-closed on unknown files inside typed directories.** eve's silent skip
   in `tools/`/`channels/`/`hooks/` (`named-source-directory.ts:61-69`) means
   `tools/search.yaml` vanishes without a word. PACT must error with "did you
   mean" and support an explicit `.pactignore`.
7. **Ship an explicit composition operator with a published merge algebra.**
   Per-field strategies (`replace | append | prepend | merge | remove`), a
   `pact explain <agent>` that renders the effective document with per-field
   provenance, and a shadowing report. This is the direct answer to
   `docs/subagents.mdx`'s "copy the markdown under each `skills/` directory".
8. **Topology is a separate document from the agent tree.** Directory nesting
   must not imply an edge. Node kinds `{agent, router, aggregator, judge,
   human, tool}`; edge kinds `{delegate, handoff, broadcast, pipe, vote,
   subscribe}`; explicit shared-state ("blackboard") as a declared resource
   since eve proves that "state is never shared" blocks 3 of the 8 patterns.
9. **Loop is a document.** A state machine over
   `perceive/plan/act/observe/reflect/halt` with declared halt predicates,
   verifier passes, and ensemble/self-consistency as first-class nodes. Use
   eve's step sequence (§5.1) as the *default* loop's specification — it is a
   good default — but it must be one authored, replaceable, diffable document.
10. **Hooks must be able to mutate, not only observe.** Keep eve's typed event
    map (28 events at `hook.ts:18-49`) as the observation surface, and add a
    *separate*, declared `interceptor` kind with a typed
    `(state) → state | halt | redirect` contract so it stays analysable.
11. **Model binding is a predicate plus a lockfile, and the catalogue is local.**
    `models/catalog.yaml` is authoritative and offline (D8); network feeds are
    optional providers that *populate* it. eve's failure mode — default model
    absent from a 3-entry built-in table, hard failure when offline
    (`model-catalog.ts:60-82` vs `default-agent-model.ts`) — is the regression
    test to write.
12. **Contract fields eve lacks are the reason PACT exists.** Add to the agent
    document: `id/version/namespace/owner`, content-typed `io` (text, image,
    audio, video, binary, stream), `capabilities` (required + optional),
    `evals` binding, `slo` (TTFT/TPOT/E2E/cost, percentile + modality-aware),
    `policy` (approval gates, redaction, autonomy level), `provenance`.
13. **Evals: one document model, five on-ramps (D19), zero required code.**
    Steal eve's structural assertions verbatim — `calledTool`, `toolOrder`,
    `maxToolCalls`, `usedNoTools`, `calledSubagent`, `loadedSkill`, `eventOrder`,
    `noFailedActions` (`assertions/run.ts`) — as YAML predicates; DeepEval does
    not cover this axis. Keep gate/soft/`atLeast` severity. Add SLO predicates
    and dataset documents, which eve has neither of. And note the direction of
    travel: eve deleted its declarative eval keys
    (`define-eval.ts:43-81`) — PACT must show the declarative form is *more*
    expressive, not less, or it will lose the same argument.
14. **Ship a mock/replay model in the core.** Non-negotiable for D17 offline
    CI and for making loop-engineering evals deterministic. eve's
    `MockModelRequest` normalisation (messages / userMessages / tools /
    toolResults) is a good starting shape.
15. **Durable semantics in the IR, adapters underneath.** Adopt
    session/turn/step, park, resume, recursive cancel, and
    child-budget-capped-by-parent as *IR concepts*; map to
    Temporal/Restate/DBOS/Vercel-Workflow/Bud-ledger. Do not vendor a beta
    protocol.
16. **Never carry blobs in durable history.** Specify content-addressed
    attachment refs with per-call hydration (eve's `eve-sandbox:` pattern) —
    required for D16's vision/audio/computer-use in a durable runtime.
17. **Make silent shadowing impossible.** eve has three silent precedence
    rules: extension first-wins across mounts (`normalize-manifest.ts:195-218`),
    dynamic tools overriding authored tools at runtime
    (`tool-loop.ts:843-846`), and discarded skill frontmatter `name`. Under T7
    every one of these must emit a report entry.
18. **Two orthogonal identity axes.** eve conflates "where the file is" with
    "what this thing is", and then had to invent `packageNamespace` to protect
    durable state from renames (`compiler/manifest.ts:689-698`). PACT: path
    derives the *default* local name; a stable `id` (or content digest) carries
    durable identity; renames produce a migration warning, not silent divergence.

---

## 11. Open questions

1. **Does harness lowering cost measurable quality?** eve pins
   `stopWhen: isStepCount(1)` and reimplements retry, empty-response recovery,
   and unsupported-tool recovery in 2547 lines. Whether that beats or trails the
   AI SDK's native multi-step loop is untested here and is exactly PACT's **F-4**
   continuous benchmark. eve's `tool-loop.test.ts` (9531 lines) is the closest
   thing to a specification of the behaviour and is worth mining for CTS cases.
2. **Can the Expansion Rule survive eve's hard cases?** Specifically:
   `sandbox/workspace/` (opaque bytes), skill packages
   (`SKILL.md` + `scripts/` + `references/` + `assets/`), and channel
   `[param]` path segments. These are directories that are *not* fields —
   they are payloads. Needs an explicit `binary`/`payload` node kind. This is
   the T5 stress test named in thesis §9.3.
3. **Is `localeCompare` ordering observable in eve's own artifacts?** I did not
   construct a failing case; the hazard is read from `grammar.ts:176`. Worth a
   10-minute experiment (e.g. `tools/`/instructions with `İ`, `_`, `-` under
   `tr-TR` vs `C`) to cite a concrete break rather than a code smell.
4. **How much of eve's e2e fixture corpus is portable as PACT CTS fixtures?**
   `e2e/fixtures/` has 23 entries (17 agent trees + 6 extension packages)
   covering skills, subagents, subagent-HITL, tool-HITL (generic and
   OpenAI-specific), cancellation, compaction regressions, schedules, channels,
   session limits, prompt cache, OpenAPI/Swagger, dynamic model, sandbox tools,
   and a workflow stress case. These are behaviour specs with runnable evals —
   plausibly the fastest path to a real CTS.
5. **What exactly does `@workflow/world` `specVersion` guarantee?**
   `isWorkflowWorld` checks three members (`validate-world.ts:60-72`). Whether
   Temporal/Restate/DBOS can satisfy the same contract determines whether PACT
   can reuse the Workflow SDK as *one* adapter rather than writing its own
   durable layer. Not answerable from this repo alone.
6. **Was there ever a declarative-eval design, and why did it lose?**
   `define-eval.ts:43-81` rejects nine legacy keys with migration guidance —
   evidence of a deliberate reversal. The reasoning (likely in the repo's
   `research/` dir or PR history) is directly load-bearing for PACT's G4/D19
   claim and I did not chase it down.
7. **Does anything in eve support audio at all?** I found no audio path
   (no streaming audio I/O, no TTFT instrumentation beyond OTel spans). Marked
   negative, but I searched by directory and grep rather than exhaustively.

---
---

# PART II — Second independent pass (2026-08-07)

**Method.** Re-read `packages/eve/src/{discover,compiler,harness,execution,runtime,evals,public,internal}`
from source at the same HEAD (`05f3480`, `eve@0.27.6`), plus `docs/**` for claims,
then reconciled against Part I. Same evidence discipline: every claim below is
`file:line` relative to
`/home/bud/ditto/agent-inter-op/research/repos/frameworks/vercel-eve/`.

---

## 12. Re-verification of Part I's load-bearing claims

These are the Part I claims that PACT's design leans on hardest. All were
re-derived independently from source; none required correction.

| Part I claim | Re-verified at | Status |
|---|---|---|
| Runtime never reads the tree; loads compiled artifacts | `src/runtime/compiled-artifacts-source.ts:1-45` — the source union is `{kind:"bundled"}` or `{kind:"disk", appRoot, moduleMapLoaderPath?}`; the doc comment states the module-map loader path is "Omitted in deployed runtimes, where the module map **must** come from the compiled artifact emitted by the build" | ✔ confirmed |
| Tree→graph is code generation | `src/compiler/module-map.ts:63-112` (`createCompiledModuleMapSource` emits `import * as module_N`); `src/compiler/artifacts.ts:123-136` writes it to `.eve/compile/module-map.mjs` | ✔ confirmed |
| Compile executes author code | `src/internal/authored-module-loader.ts:1-40` — rolldown-bundles each authored module into `node_modules/.cache/eve/authored-modules/<hash>.mjs`, then `import()`s it (`AUTHORED_MODULE_BUNDLE_DIRECTORY_PATH` at `:35-40`) | ✔ confirmed |
| Only 3 slots take Markdown | `src/discover/filesystem.ts:7-14` (`SUPPORTED_AUTHORED_MODULE_FILE_EXTENSIONS = [".cts",".mts",".cjs",".mjs",".ts",".js"]`); `src/internal/helpers/markdown.ts` exports exactly `lowerInstructionsMarkdown`, `lowerSkillMarkdown`, `lowerScheduleMarkdown` | ✔ confirmed |
| Zero YAML/JSON authoring surface | Grep for `yaml\|yml\|\.json"` across `src/discover/` + `src/compiler/` returns **only** `package.json`, `vercel.json` (project markers, `filesystem.ts:20`), the five `.eve/*.json` output artifacts, and `_manifest.json` (extension compat). No authored `.yaml` path exists anywhere in the loader. | ✔ confirmed |
| Harness pins one model call per durable step | `src/harness/tool-loop.ts:907` — `stopWhen: isStepCount(1)` inside `agentSettings`, `new ToolLoopAgent(agentSettings)` at `:912` | ✔ confirmed |
| Hooks are observe-only | `src/public/definitions/hook.ts:99-102` — "Handlers are observe-only: they cannot inject model context"; `StreamEventHook` returns `void \| Promise<void>` (`:83`) | ✔ confirmed |
| Loop config has no loop shape | `ToolLoopHarnessConfig` consumed at `tool-loop.ts:467-511`; the only behavioural knobs threaded in are `mode`, `workflow`, `workflowMaxSubagents`, `capabilities`, `resolveModel`, `dispatchDynamicModelEvent`, `onCompaction`, `tools`, `abortSignal`, `handleEvent`, `runtimeIdentity` | ✔ confirmed |
| Agent config is 10 fields | `src/shared/agent-definition.ts:257-303` (`PublicAgentDefinition`); closed-world enforced at `src/internal/authored-definition/core.ts:45-61` | ✔ confirmed |
| Model catalogue is a network service with a 3-entry offline table | `src/internal/gateway.ts:5,11` (`https://ai-gateway.vercel.sh/v1/models/catalog`); `src/compiler/model-catalog.ts:60-82` (built-in table: `anthropic/claude-opus-4.7`, `openai/gpt-5.4`, `openai/gpt-5.4-mini`); fetch at `:215`, 24 h TTL at `:8`, disk cache at `.eve/cache/model-catalog.json` (`:99-101`) | ✔ confirmed |
| Subagents inherit nothing; copy-paste is the sanctioned reuse | `docs/subagents.mdx:66` ("A declared subagent inherits nothing from the root's authored slots"), `:80` ("copy the markdown under each `skills/` directory"); no merge step exists in `src/compiler/normalize-subagent.ts` or `normalize-manifest.ts` | ✔ confirmed |
| Evals are imperative TypeScript only | `src/evals/types.ts:475-478` (`EveEvalInput.test(t)` is required and is a function); `src/evals/runner/discover.ts:7,10` (`EVAL_FILE_SUFFIX = ".eval.ts"`, `EVAL_CONFIG_FILE = "evals.config.ts"`) | ✔ confirmed |
| Schema-version churn: compiled v36, discovery v12 | `src/compiler/manifest.ts:44`, `src/discover/manifest.ts:23` | ✔ confirmed |
| Identity derives from `package.json#name` or a directory basename | `src/discover/manifest.ts:350-366`; `docs/reference/project-layout.md:19` | ✔ confirmed |

---

## 13. Findings Part I does not contain

### N1 — `tools/` flattens nested paths into a dash-joined slug, and the resulting collision fails at **first session**, not at build

`src/compiler/normalize-tool.ts:49-51`:

```ts
const toolName = stripLogicalPathExtension(source.logicalPath)
  .replace(/^tools\//, "")
  .replaceAll("/", "-");
```

The doc comment at `:27-34` is explicit: *"`tools/billing/refund.ts` → `"billing-refund"`. Path separators cannot reach the model — most providers reject `/` in tool names — so tools are the one path-derived primitive that flattens nested directories into a slug-safe single segment."*

**The collision this creates is not detected by discovery or by compilation.**
`tools/billing-refund.ts` and `tools/billing/refund.ts` are two distinct
`logicalPath`s, so `discoverNamedSourceDirectory` emits two source refs with no
diagnostic, and `compileAgentNodeManifest` pushes two `CompiledToolDefinition`s
with the *same* `name` into `manifest.tools`
(`src/compiler/normalize-manifest.ts:112-114`). The duplicate is only caught in
`createRuntimeToolRegistry` (`src/runtime/tools/registry.ts:41-53`,
`duplicateMessage: "Found multiple authored tools named …"`), which runs inside
`resolveRuntimeAgentGraph` (`src/runtime/resolve-agent-graph.ts:171-184`).

Who calls that? Only `src/runtime/sessions/compiled-agent-cache.ts:74` (session
bootstrap) and `src/execution/sandbox/prewarm.ts:222,329`. **`eve info` does
not** — it reads the compiled manifest fields directly
(`src/cli/commands/info.ts:56-62`). So the author's feedback loop is:
`eve info` clean → `eve build` clean → **first message fails at runtime.**

*Design consequence for PACT:* name derivation that is not injective on paths
must be validated **in the loader**, at the moment both candidates are visible,
not in a downstream registry. And PACT's `validate` must run whatever check the
runtime registry would run, or `validate` is not a gate.

### N2 — The compiled manifest embeds **absolute host paths**, so the derived artifact is machine-bound

`src/compiler/manifest.ts:638-640` and `:723-726`: both
`compiledAgentNodeManifestSchema` and `compiledAgentManifestSchema` require
`agentRoot: z.string()` and `appRoot: z.string()`, populated from
`resolve(input.agentRoot)` / `resolve(input.appRoot)`
(`src/discover/manifest.ts:311-316`). Skill packages additionally carry absolute
`rootPath`, `skillFilePath`, `assetsPath`, `referencesPath`, `scriptsPath`
(`src/compiler/manifest.ts:474-484`), and extension mounts carry an absolute
`sourceRoot` (`:700-707`).

`.eve/compile/compiled-agent-manifest.json` therefore **cannot be moved between
machines, containers, or CI runners**. It is a build cache, not an interchange
format — which is a second, independent reason it is nothing like PACT's
`canonical.json`.

*Design consequence for PACT:* `canonical.json` must be **path-free**. Every
reference is a workspace-relative logical path or a content digest. Absolute
paths appear only in `pact.lock` / run-scoped state, never in the IR. Add this
as a mechanical CI check (grep the emitted IR for `/` or drive-letter prefixes).

### N3 — eve versions its **extension** contract per-capability, and its **own** manifest monolithically. The contrast is the argument for PACT's E-2.

`src/compiler/extension-compatibility.ts:22-34`:

```ts
const EXTENSION_CAPABILITY_CONTRACTS = {
  extension:  { current: 1, supported: [1],       dropped: {} },
  tool:       { current: 2, supported: [1, 2],    dropped: {} },
  dynamicTool:{ current: 3, supported: [1, 2, 3], dropped: {} },
  connection: { current: 2, supported: [1, 2],    dropped: {} },
  hook:       { current: 2, supported: [1, 2],    dropped: {} },
  skill:      { current: 1, supported: [1],       dropped: {} },
  …
  state:      { current: 2, supported: [1, 2],    dropped: {} },
} as const satisfies Record<string, ExtensionCapabilityContract>;
```

`eve extension build` stamps only the capabilities the extension actually used
into `_manifest.json#requires`
(`EXTENSION_COMPATIBILITY_MANIFEST_FILENAME = "_manifest.json"`, `:14`;
manifest shape at `:69-76`), and the consuming eve validates each requirement
against its own `supported` set, reporting `UnsupportedExtensionCapability`
per capability (`:78-82`). `dropped` carries a *per-version removal reason*, so
a rejection can explain itself.

This is **exactly PACT invariant E-2** ("unknown features are rejected loudly by
old adapters, never ignored") and it is better than what eve does for its own
artifact, which is a single `COMPILED_AGENT_MANIFEST_VERSION = 36`
(`src/compiler/manifest.ts:44`) that bumps whenever *any* field changes.

*Design consequence for PACT:* copy the extension model, not the manifest model.
The IR carries `requires: {capability: version}` for only the capabilities a
document actually uses; each adapter publishes `supported: number[]` and
`dropped: {version: reason}` per capability. A version bump to `loop` must not
invalidate a document that only uses `tools`.

### N4 — Authored definitions are validated **closed-world** by hand-written normalisers, but no machine-readable schema for the *authored* surface is ever emitted

`src/internal/authored-definition/core.ts:45-61` — `normalizeAgentDefinition`
calls `expectOnlyKnownKeys(record, ["build","compaction","description",
"experimental","limits","model","modelContextWindowTokens","modelOptions",
"outputSchema","reasoning"], message)`. Same pattern for instructions
(`:327-336`, key set `["markdown"]`) and skills (`:345-351`, key set
`["description","files","license","markdown","metadata"]`). Unknown keys throw.

Two consequences:

1. **Good:** unknown-field rejection is fail-closed, matching PACT **AC-1.3**'s
   first half. Worth adopting as the default posture.
2. **Bad for D18:** zod schemas exist only for the **compiled** manifest
   (`src/compiler/manifest.ts:280-751`). There is no JSON Schema, no descriptor,
   nothing a form-renderer could consume for the *authored* surface. eve's only
   authoring contract is TypeScript types plus `ExactDefinition`
   (`src/public/definitions/exact.ts`). A UI that "reads and writes the same
   files" (**D18**) would have to emit TypeScript — i.e. it would have to be a
   code generator, and round-tripping edits back out of hand-written TS is
   undecidable in general.

*Design consequence for PACT:* the authored schema must be a first-class,
published, machine-readable artifact (`pact schema --json`), and the four author
surfaces of D18 (editor, UI, builder agent, PR review) all bind to *it*, not to
a language's type system.

### N5 — Remote agents speak eve's private `/eve/v1/session` protocol. There is no A2A, no MCP-server egress, no cross-vendor agent edge.

`src/public/definitions/remote-agent.ts:78-84`:

```ts
export function defineRemoteAgent(input: RemoteAgentDefinitionInput): RemoteAgentDefinition {
  return { ...input, kind: "remote", path: input.path ?? EVE_CREATE_SESSION_ROUTE_PATH };
}
```

`EVE_CREATE_SESSION_ROUTE_PATH` comes from `src/protocol/routes.ts`. The remote
node is lowered to the same `{message, outputSchema?}` subagent tool as a local
child (`src/runtime/resolve-agent-graph.ts:336-398`). Auth is an outbound
`OutboundAuthFn` plus optional principal forwarding (`:20,39`).

So eve's multi-deployment story is **eve-to-eve only**. It cannot call a
LangGraph service, an A2A endpoint, or an MCP-hosted agent as a peer; and it
emits no Agent Card. (MCP appears only on the *ingress* side, as a tool source:
`defineMcpClientConnection`, `docs/connections/mcp.mdx`.)

Part I's L5 covers the missing *topologies*; this is the separate limitation
that the one edge kind eve does have is **proprietary**. It blocks PACT
**O6.2** (emit A2A Agent Cards / OSSA with loss reports) and **NG3** (PACT
emits and consumes both edges).

*Design consequence for PACT:* the remote-agent node kind must be
protocol-tagged (`a2a | mcp | http | pact`), and A2A card emission must be a
projection of the Contract, not an extra authoring step.

### N6 — Concrete inventory of capability-capping hardcoded defaults (input for PACT's **AC-7.2** "zero-magic audit")

Every one of these is a literal in the core with no profile indirection:

| Default | Value | Site |
|---|---|---|
| Root session input-token cap | `40_000_000` | `src/execution/session.ts:9` |
| Compaction threshold | `0.9` of context window | `src/execution/session.ts:7`, applied `:32` |
| Compaction recent-window | `10` messages | `src/execution/session.ts:6` |
| Compaction summary reserve | `2_048` tokens | `src/harness/compaction.ts:15` |
| Model-call attempts | `3` (1 + 2 retries) | `src/harness/tool-loop.ts:235` |
| Retry base delay | `500 ms`, doubling + jitter | `src/harness/tool-loop.ts:242` |
| Workflow subagent budget | `100` per program | `src/harness/workflow-subagent-limit.ts:8` |
| Workflow sandbox bridge requests | `256` | `src/harness/workflow-sandbox.ts:23` |
| `read_file` line limit | `2000` (offset `1`) | `src/execution/sandbox/read-file-tool.ts:16-17` |
| `glob` / `grep` result limit | `100` each | `src/execution/sandbox/glob-tool.ts:12`, `grep-tool.ts:12` |
| `web_fetch` timeout | `30_000 ms` | `src/execution/web-fetch/tool.ts:6` |
| Vercel sandbox timeout | `30 min` | `src/execution/sandbox/bindings/vercel.ts:649` |
| microsandbox CPU / memory | `1` CPU / `1024 MiB` | `src/execution/sandbox/bindings/microsandbox-options.ts:5-6` |
| Eval concurrency | `8` | `src/evals/runner/run-evals.ts:13` |
| Eval target health timeout / poll | `60_000 ms` / `250 ms` | `src/evals/target.ts:16-17` |

Of these, exactly **two** are author-overridable (`compaction.thresholdPercent`,
`limits.max{Input,Output}TokensPerSession` —
`src/shared/agent-definition.ts:104-179`). The other thirteen are constants.
`maxToolCalls`-style loop budgets, verifier passes, and self-consistency `k`
do not exist to be defaulted at all.

*Design consequence for PACT:* this table is the shape of the **F-1 / AC-7.2**
audit. Every one of these belongs in a `profiles/` document with
workspace → agent → variant → run scoping, and the audit is a grep for
capability-affecting numeric literals in the core.

### N7 — Instruction composition is **concatenation**, and its ordering is `localeCompare`

Part I flags the `localeCompare` hazard (§3.2 I8, §8 L15). Part II pins the
exact fold and the exact blast radius:

- `readSortedDirectoryEntries` sorts with `left.name.localeCompare(right.name)`
  with **no locale argument** (`src/discover/grammar.ts:170-179`), i.e. ICU
  default collation from the host environment.
- Same pattern at `src/discover/slots.ts:56,108,111` (module candidates and slot
  names), `src/compiler/module-map.ts:81,124`, `src/compiler/manifest.ts:891`,
  `src/compiler/workspace-resources.ts:152`,
  `src/compiler/normalize-manifest.ts:186-188` (extension mount order, which
  decides first-registration-wins), `src/compiler/extension-compatibility.ts:158`.
- The fold: `src/compiler/normalize-manifest.ts:225-240` —
  `composedMarkdown = [...staticInstructions.map(e => e.markdown), ...extensionInstructionFragments]`
  then `markdown: composedMarkdown.join("\n\n")`.

So the **system prompt's text order is a function of the host's ICU locale**.
For pure-lowercase-ASCII filenames this is a no-op; for mixed case, underscores,
hyphens, or non-ASCII it is not (ICU treats punctuation as variable-weighted and
orders `a < A < b`, whereas byte order gives `A < B < a`). And
`normalize-manifest.ts:186-188` means the *extension shadowing winner* is
locale-dependent too.

I did **not** construct a failing case (Part I §11 Q3 also leaves this open).
The claim "`localeCompare` is not byte order and is environment-dependent" is
verified from source; the claim "eve produces different prompts under `tr-TR`
vs `C`" remains **[INFERRED]** until someone runs the experiment.

### N8 — The `Workflow` sandbox is a genuinely good escape-hatch design, and PACT should copy its *shape*

`docs/guides/dynamic-workflows.md:69-73`: the model-authored orchestration
program runs in a **QuickJS** isolate. *"Nothing from the host realm crosses in,
so there is no `process`, no `globalThis` from the agent, and no
`import`/`require`. The program can reach exactly two things, the agent
functions bridged in as `tools.<name>` and the ordinary language built-ins.
That is an allowlist, not a denylist."* Reach is capped at the agent's own
subagents — "No files, network, shell, skills, or connections" (`:57`). Budget
is `maxSubagents` (default 100, `src/harness/workflow-subagent-limit.ts:8`);
over-budget calls resolve **inside the program** as
`WORKFLOW_SUBAGENT_LIMIT_REACHED` rather than throwing, and the budget is
stated in the tool description so the model can size its fan-out
(`docs/guides/dynamic-workflows.md:63-67`). Bridged calls are dispatched as
ordinary delegations, so they emit the normal `subagent.called` /
`subagent.completed` events and stay observable (`:79-84`).

This is the right *mechanism* attached to the wrong *authority*: the **model**
writes the program, at runtime, unreviewably. PACT needs the identical
sandbox contract for its **authored** code escapes (F-2/F-3) — capability
allowlist, no ambient host realm, declared budget, budget exhaustion as a
typed in-band result, and every bridged call surfacing on the normal event
stream.

### N9 — Authored modules are forbidden from carrying workflow directives; durability is entirely framework-owned

`src/internal/authored-directive-prologue.ts:3,28-33`:

```ts
const UNSUPPORTED_WORKFLOW_DIRECTIVES = new Set(["use step", "use workflow"]);
…
throw new Error(
  `Authored module "${input.filePath}" contains an actual "${statement.directive}" directive. ` +
    "Workflow directives are reserved for eve-generated workflow entrypoints.",
);
```

Authors can never declare a durability boundary. eve instead *rewrites* author
code to insert them: `src/internal/workflow-bundle/dynamic-tool-transform.ts:76-78`
hoists dynamic-tool `execute` bodies to module scope and adds `"use step"`.

This is a clean, defensible ownership line — the framework owns durability, the
author owns behaviour — and it is the same line D12 draws for loop semantics.
But it is also the mechanism behind the silent replay hole Part I §1.5 names:
the transform is *syntactic*, so `execute: myFn` compiles, runs once, and then
fails to replay (`docs/guides/dynamic-capabilities.md:54-56` states this
explicitly as a documented limitation, not a bug).

*Design consequence for PACT:* durability boundaries are IR concepts (P-5), never
author annotations — adopt eve's line. But a *syntactic* requirement on author
code with a silent-at-build / broken-at-replay failure mode is exactly the class
of trap T7 forbids. If PACT ever needs a shape constraint on a code escape, it
must be **checked and reported at validate time**, not assumed.

### N10 — The public hook event map is deliberately decoupled from the internal protocol union

`src/public/definitions/hook.ts:10-17`: *"The explicit map keeps hook
compatibility independent from the internal protocol union: new protocol events
do not become extension hook events until eve exposes them here."*
`HookEventMap` (`:17-46`) enumerates 28 event types by hand, each as
`ProtocolEvent<"...">`.

This is a small but excellent stability practice: the observable surface is an
explicit allowlist that a refactor of the internal union cannot silently widen.
PACT's trace/event vocabulary (which feeds hooks, evals, learning, and the
Portability Report) should be specified the same way — an explicit, versioned
event catalogue, not "whatever the runtime happens to emit".

### N11 — The single-file subagent form produces a subagent with **no slots at all**, and inherits the parent's `agentRoot` string

`src/discover/discover-subagent.ts:153-177` (`discoverSingleFileSubagent`)
builds `createAgentSourceManifest({ agentId, agentRoot: input.agentRoot, appRoot, configModule })`
— note `agentRoot` is the **parent's** root, and no `tools`, `skills`,
`instructions`, `connections`, or nested `subagents` are discovered. So
`subagents/echo.ts` is a config-only child: it can set a model and a
description, and nothing else. `subagents/echo/` (the directory form) is a full
agent root (`discoverLocalSubagentPackage`, `:179-315`).

Two authoring forms of the same concept with materially different capability
sets, distinguished only by whether the author typed `.ts` — and the manifest
for the file form reports an `agentRoot` that is not that subagent's root. This
is a concrete instance of the file-vs-directory ambiguity PACT's **Typed
Expansion** rule exists to eliminate: expansion form should be declared per
field by the schema, and the two forms must be *semantically identical*, not
"one is a weaker version of the other".

### N12 — The `evals/` tree is outside `agent/`, and eve actively detects the mistake

`src/evals/runner/discover.ts:47-61` (`findMisplacedEvalDirs`) scans
`<appRoot>/agent/**` for `*.eval.ts` specifically to produce a clear error when
an author put evals in the agent tree. `docs/reference/project-layout.md:43`:
"Evals live in `evals/` at the app root, a sibling of `agent/`, not inside it."

Worth recording because PACT is likely to make the opposite choice (evals as an
expansion of the agent's `contract.evals` field, co-located with the agent).
eve's separation exists because their evals are *drivers* — they speak HTTP to a
running server, so they belong to the app, not the agent
(`src/evals/target.ts:19-44` requires a live target, polls `/eve/v1/health`
for 60 s, then `GET /eve/v1/info` and asserts the served agent name matches
`package.json#name` at `:29-36`). If PACT co-locates evals with agents, it
inherits the obligation to make an eval runnable **without** a server — which
is what the config-only + mock-model design buys.

---

## 14. Where Part II would sharpen Part I

Not corrections — refinements.

1. **§0/S1 "the runtime never reads the authored tree" is true but has one
   nuance.** `RuntimeDiskCompiledArtifactsSource.moduleMapLoaderPath`
   (`src/runtime/compiled-artifacts-source.ts:22-28`) exists so that in
   *development* the runtime "loads modules directly from authored source
   instead of the bundled-compiled module map". It still requires the compiled
   **manifest**; only the module map is bypassed. The claim stands — there is no
   path that interprets the tree — but the dev path is a partial exception worth
   naming, and it is the closest eve comes to PACT's D2.

2. **§2.1's "unknown files silently ignored" deserves the sharper framing that
   the *class* of ignored file is unbounded.** `emitUnsupportedLeafDiagnostics`
   only runs when a caller supplies `unsupportedFileCode`
   (`src/discover/named-source-directory.ts:220-222`), and the only caller that
   does is `schedules/` (`src/discover/schedules.ts`). So under `tools/`,
   `channels/`, `hooks/`, `lib/`, `instructions/` and `extensions/`, a
   `.yaml`, `.json`, `.py`, `.wasm` or `.md` file is not merely unread — it
   produces **no diagnostic of any kind**, and `eve info` will not mention it.
   For a non-technical author this is the worst possible failure mode: silence.

3. **§5's "no loop engineering" understates one point.** It is not only that the
   loop is fixed; it is that the loop's *inputs* are fixed too. The
   assembly order at `tool-loop.ts:749-783` hardcodes the system-message
   composition: `[extraSystemNote, session.agent.system, ...systemMessages]`,
   merged by `mergeSystemInstructions` (`:269-298`) with `join("\n\n")`. Prompt
   *structure* — not just prompt text — is a constant. Any PACT strategy that
   varies prompt composition (a documented model-portability mechanism, thesis
   §7.3) is inexpressible in eve at the type level, not merely unauthored.

4. **§7.2's "evals are black-box over the wire" should carry its cost.** The
   same property that makes `AC-4.3` free also means **an eval cannot run
   without booting a server** (`src/evals/cli/eval.ts` starts a dev server when
   `--url` is absent; `src/evals/target.ts:171-189` blocks up to 60 s on
   health). Combined with the compile step, "run one eval" means
   discover → compile → bundle → boot Nitro → poll health → drive HTTP. For
   PACT's D17 air-gapped `validate → resolve → build → eval → report`, adopt the
   *protocol-neutrality* of the design but not the *server dependency*: the eval
   runner must accept an in-process target as a first-class target kind.

---

## 15. Additions to the "genuinely GOOD" list

Supplements Part I §9 (G1–G17); numbering continues.

| # | Idea | Evidence | Why it matters to PACT |
|---|---|---|---|
| G18 | **Per-capability contract versioning with `supported` sets and `dropped` reasons**, stamped as `requires` only for capabilities actually used. | `src/compiler/extension-compatibility.ts:16-34,69-82` | The correct implementation of **E-2**. Strictly better than eve's own monolithic `v36`. Copy this, not that. |
| G19 | **`ProjectSource` — the loader's only filesystem interface**, with a disk impl and an in-memory impl, and the memory impl normalising Windows drive letters "so all paths are POSIX-rooted for determinism across platforms". | `src/discover/project-source.ts:43-66`, `:72-99`, `:140-269`, `:283-296` | PACT's loader is normative (**D2**) and must be property-testable without disk. This is the exact seam to specify. Adopt the interface shape verbatim: `readDirectory`, `readTextFile`, `stat` — nothing more. |
| G20 | **Closed-world authored-key validation** (`expectOnlyKnownKeys`), so an unknown field is an error with the full legal key list in the message. | `src/internal/authored-definition/core.ts:45-61` | First half of **AC-1.3**. PACT adds the second half: `x-` prefixed keys round-trip untouched. |
| G21 | **Explicit, hand-maintained public event allowlist** decoupled from the internal event union. | `src/public/definitions/hook.ts:10-46` | PACT's trace/event vocabulary feeds hooks, evals, learning and the Portability Report; it must be a versioned catalogue, not an emergent surface. |
| G22 | **Capability-allowlist code sandbox with in-band budget exhaustion.** QuickJS isolate, no host realm, reach limited to the agent's own delegation edges, `maxSubagents` stated in the tool description, over-budget calls returning `WORKFLOW_SUBAGENT_LIMIT_REACHED` as a *value*. | `docs/guides/dynamic-workflows.md:57,63-73`; `src/harness/workflow-subagent-limit.ts:8` | The right contract for PACT's typed code escapes (**F-2/F-3**) — attached to authored code rather than model-authored code. |
| G23 | **Identity forwarding is opt-in on both ends and defaults off**; only principal metadata crosses, never tokens; a receiver that refuses the forwarder returns 403 rather than silently downgrading. | `src/public/definitions/remote-agent.ts:20-39` | Exactly the fail-closed posture **T7** demands, applied to cross-deployment identity. Adopt as PACT's default for any remote node kind. |
| G24 | **Diagnostics separate `error` (fail-closed, artifacts still written) from `warning` (printed, build proceeds)**, and artifacts are written *before* the throw so a failed build is still inspectable. | `src/compiler/compile-agent.ts:76-85,142-165` | Writing the derived artifact even on failure is a small, excellent DX decision — the author can diff what the loader *thought* it saw. PACT should always emit `.pact/diagnostics.json` even when `validate` fails. |
| G25 | **Three explicit verbs for framework defaults — override / disable / add — with a typo'd disable filename being a hard error listing the legal names.** | `src/runtime/resolve-agent-graph.ts:153-169` (`"…is not a framework tool. Rename the file to one of: …"`) | The error message *contains the fix*, which is **O7.3**. Use it as the template for every PACT loader error. |

---

## 16. Additions to the design implications

Supplements Part I §10 (1–18); numbering continues. These are the ones Part I
does not already state.

19. **Name derivation must be injective, and the loader must prove it.**
    eve's `tools/a/b.ts → "a-b"` flattening (`normalize-tool.ts:49-51`) is
    non-injective and the collision surfaces at first session
    (`runtime/tools/registry.ts:50`), past `eve info` and `eve build`. PACT rule:
    **for every derived name, the loader computes the full derived-name set and
    errors on collision, naming both source paths.** If a derivation cannot be
    injective (e.g. flattening for a provider charset), the spec must require an
    explicit disambiguator rather than a silent join.

20. **`canonical.json` must be path-free and relocatable, and CI must check it.**
    eve's compiled manifest hardcodes absolute `agentRoot`, `appRoot`, skill
    `rootPath`/`skillFilePath`, and extension `sourceRoot`
    (`compiler/manifest.ts:638-640,474-484,700-707`). PACT's IR carries only
    workspace-relative logical paths and content digests; absolute paths live in
    `pact.lock` and run state. Add a mechanical test: emitted IR contains no
    string matching `^/` or `^[A-Za-z]:`.

21. **Version per capability, never per document.** Replace a monolithic
    `pact.dev/v1` manifest version with `requires: {<capability>: <version>}`
    stamped only for capabilities the document uses, and per-adapter
    `supported: number[]` + `dropped: {version: reason}`. eve proves both sides:
    the monolith reached **v36** in a 0.27 product
    (`compiler/manifest.ts:44`) while their per-capability extension contract
    sits at 1–3 with clean supported-ranges
    (`extension-compatibility.ts:22-34`).

22. **Silence is the worst diagnostic; make unknown files inside typed
    directories an error by default.** eve emits *no diagnostic at all* for an
    unrecognised leaf under `tools/`, `channels/`, `hooks/`, `lib/`,
    `instructions/`, `extensions/` — the strictness hook exists but only
    `schedules/` opts in (`named-source-directory.ts:220-222`,
    `discover/schedules.ts`). PACT inverts the default: unknown extension inside
    a typed directory → error, with a "did you mean" and an explicit
    `.pactignore` opt-out.

23. **Publish the authored schema as data, and make all four D18 surfaces bind
    to it.** eve has zod for the compiled manifest but nothing machine-readable
    for the authored surface (`internal/authored-definition/core.ts` is
    hand-written normalisers; the authoring contract is TypeScript types).
    Ship `pact schema --json` covering every document kind, and require the UI,
    the builder agent, and the diff/review tooling to consume it. Without this,
    D18's "UI reads and writes the same files" degrades into a code generator.

24. **`validate` must run every check the runtime would run.** eve splits checks
    across three phases — discovery (`discover/*` diagnostics), compile
    (`normalize-*` throws), and graph resolution (`runtime/tools/registry.ts`,
    `runtime/subagents/registry.ts`) — and only the first two run before boot.
    A PACT `validate` that does not include the registry/uniqueness/reference
    phase is not a gate, and **AC-7.3**'s offline pipeline would pass agents that
    fail on first message.

25. **The eval runner needs an in-process target kind.** eve's HTTP-only target
    (`evals/target.ts:19-44`, 60 s health poll) is what makes AC-4.3 free, but it
    forces compile+bundle+boot to run one eval. PACT keeps the protocol-neutral
    target abstraction (`local-process | in-process | http | a2a`) so an
    air-gapped `pact eval` against a mock model needs no server.

26. **Two authoring forms of one concept must be semantically identical.**
    eve's `subagents/<id>.ts` (config only, and it reports the *parent's*
    `agentRoot`) versus `subagents/<id>/` (a full agent root) —
    `discover-subagent.ts:153-177` vs `:179-315` — is a file-vs-directory split
    where the file form is a strictly weaker thing wearing the same name.
    Under Typed Expansion this must be impossible: `X.yaml` and `X/` are the
    *same field*, and `load(explode(D)) ≡ D`. Make it a property test in the
    conformance suite, not just a rule in prose.

27. **Specify the ordering function, and ban locale-sensitive comparison in
    normative text.** eve uses bare `localeCompare` in nine ordering-relevant
    sites, three of which are semantically load-bearing: directory entry order
    (`grammar.ts:176`) → instruction concatenation order
    (`normalize-manifest.ts:225-240`); extension mount order
    (`normalize-manifest.ts:186-188`) → which extension wins a name collision.
    PACT's spec should say, in normative language: *ordering is by UTF-8 byte
    sequence of the NFC-normalised path segment; ties are an error; ordered
    collections carry order in-band as `NN-name.ext`.*

28. **Durability boundaries are framework-owned — adopt eve's line, reject its
    enforcement style.** `authored-directive-prologue.ts:28-33` forbids authors
    from writing `"use step"` / `"use workflow"`; the framework inserts them by
    AST rewrite. The line is right (same line D12 draws for loops). The
    enforcement is not: the rewrite is syntactic, so `execute: myFn` builds
    clean and breaks only on replay
    (`docs/guides/dynamic-capabilities.md:54-56`). Any structural requirement
    PACT places on a code escape must be **checked at validate time and
    reported**, never assumed by a transform.

---

## 17. Open questions added by Part II

*(Part I's Q1–Q7 stand.)*

8. **Does `eve build` ever resolve the runtime agent graph?** I traced
   `resolveRuntimeAgentGraph` to exactly three non-test callers —
   `runtime/sessions/compiled-agent-cache.ts:74` and
   `execution/sandbox/prewarm.ts:222,329` — and `prewarmBuiltAppSandboxes` is
   called from `internal/nitro/host/start-production-server.ts:244`, i.e. at
   *start*, not at *build*. If a Vercel build's sandbox prewarm also resolves
   the graph, then N1's collision would surface at build after all, on that one
   path. Worth 15 minutes in `internal/nitro/host/vercel-build-prewarm.ts` to
   settle whether the late-failure claim holds on every path or only the
   local one.

9. **Is the `agentRoot`/`appRoot` absoluteness load-bearing at runtime, or
   vestigial?** If the compiled manifest's absolute paths are only used for
   sandbox/workspace materialisation and diagnostics, eve is one refactor from a
   relocatable artifact — which would change how strongly N2 argues for
   path-free IR. Grep `manifest.agentRoot` consumers.

10. **What is the actual authoring cost of "inherits nothing" in eve's own
    fixtures?** `e2e/fixtures/agent-subagents/` has one declared subagent with
    its own `instructions.md`; the duplication cost is invisible at n=1. A count
    of duplicated markdown across a real multi-subagent eve app would turn
    Part I §6.2's argument from principled into measured. Not answerable from
    this repo (no such app exists in it).

11. **Was the tool-name flattening (N1) ever collision-checked and then
    removed, or never checked?** The doc comment at `normalize-tool.ts:27-34`
    reads as a considered decision but says nothing about collisions. Git
    history is unavailable here (single squashed commit `05f3480`), so this
    would need the upstream repo.
