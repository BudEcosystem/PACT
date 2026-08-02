# Eve's capabilities, numbered — and where each one lands in PACT

**Read from:** `research/repos/frameworks/vercel-eve` (on disk, 30 MB), packages
`eve` and `eve-catalog`, plus `apps/`, `docs/` and `skills/`.
**Reads against:** `spec/schema.yaml`, `docs/50-NOT-COPIED.md`.
**Held by:** `crates/pact-cli/tests/eve_inventory.rs`.

This file exists to make one sentence falsifiable:

> Every one of Eve's 80 capabilities is either (a) expressible in PACT's schema,
> (b) a runtime concern the spec declares and delegates, or (c) listed in
> `50-NOT-COPIED.md` with a reason. **No fourth category.**

Until this file landed, the 80 were an assertion. The plan's §1 table condenses
them into eleven areas carrying 58 bullets; the numbered list it was condensed
*from* was never in this repository, so `50-NOT-COPIED.md` §8 could account for
58 and had to record 22 as unverifiable. Re-enumerating from source closes that.

**Count:** 101 rows — 49 (a), 22 (b), 30 (c).

## The number is 101, not 80, and that is not padding

Every row below cites a file and a symbol in Eve's tree, so the list can be
walked and disagreed with. The count came out higher than the plan's 80. Both
reasons make the acceptance clause *harder* to satisfy rather than easier:

1. **The plan's eleven areas leave out four things Eve ships.** Its evals system
   (`packages/eve/src/evals` — its own runner, judge, assertions and reporters),
   the integration catalogue (`packages/eve-catalog`, 71 entries), the setup and
   scaffolding flow (`packages/eve/src/setup`), and the mount points for Next,
   Nuxt and SvelteKit are all authored or relied-on capabilities that the
   eleven-area condensation folds into "DX" or drops. **8 rows.**
2. **Bullets in the condensation are plural.** "`defineTool` + 12 framework
   tools" is one bullet and thirteen powers, and §1.1 of `50-NOT-COPIED.md`
   already splits the five privileged ones into their own table, so this file
   does the same. "Seven verifiers", "four sandbox backends", "eight platform
   channels", "5 park kinds" and "eleven versioned contracts" are the same shape.
   **The other 32 rows.**

**The last three rows are the authoring entry points, not capabilities.**
Rows 99–101 were added after an entry-point audit
(`docs/60-EVE-COVERAGE-AND-PLAN.md` §2) found three `define*`/`experimental_*`
exports that appeared in no ledger at all: `defineExtension`,
`experimental_workflow` and `experimental_setAttributes`. Until they landed, the
claim "none outside the three categories" was true of the 98 capabilities this
file enumerated and **false of the 27 things an Eve author can actually write**.
A count is only worth stating if the thing being counted is fixed, so the
entry-point set is now part of what the ledger covers.


Counting 101 and finding all 101 inside the three categories is a stronger
result than counting 80 and finding the same. It is recorded here so that nobody has to
take the number on trust: if a row is over-split, merging it changes the total
and changes nothing about the clause. What would change the clause is a row that
fits none of the three letters, and there is not one.

## The rule used to split rows

**One row per capability an author can name, switch on, or rely on** — read from
a public export, a discovered slot, a compiled manifest field, or a runtime
guarantee Eve's own documentation states. Type-level ergonomics, private
constants and test fixtures are not capabilities and are not rows.

## How to read the letter

| | Means | Where the row points |
|---|---|---|
| **a** | An author expresses it in YAML or Markdown | the schema group and field, in `spec/schema.yaml` |
| **b** | The spec declares it and the host does it | the row of `50-NOT-COPIED.md` §4 that says so |
| **c** | PACT will not have it, or has not yet | the `R<n>` ledger row in §5, or §6 for a deferral |

Four rows carry a letter for the half PACT answers with and name the other half
in the same cell — that is §8.1's rule, not a new one. **Tooling rows are (a)
only when PACT ships that capability as a command that EXISTS**; the cell says
which command, and `crates/pact-cli/src/main.rs` is what it is checked against.
Two rows were lettered (a) against commands nobody had written — `pact init` and
`pact tools list` — and a promised verb is the fourth category with a letter on
it, so both are now (c) or point at a field that ships.

**How a wrong letter used to survive.** `eve_inventory.rs` resolved every (c)
row against the §5 ledger and held (a) and (b) to nothing at all, so the two
letters carrying 71 of the rows were the two that could lie. Both now have a
check of their own: an (a) row's backticked `<group>.<field>` must be a field
`spec/schema.yaml` really has, and a (b) row's cell must quote a row of
`50-NOT-COPIED.md` §4. Five rows failed the first pair of tests the day they
were written, which is the argument for them.

---

## 1. Authoring

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 1 | Agent identity derived from the folder path, with no `name` field | `packages/eve/src/discover/manifest.ts` : `AgentSourceManifest.agentId` | c | R22 |
| 2 | Root agent slots discovered from the folder tree | `packages/eve/src/discover/discover-agent.ts` : `discoverAgent` | a | `workspace.agents`, and the `agent` group |
| 3 | Subagent slots under `subagents/<name>/` | `packages/eve/src/discover/discover-subagent.ts` : `discoverSubagents` | a | `agent.team` |
| 4 | A slot written as markdown or as a module | `packages/eve/src/discover/slots.ts` : `collectFlatSlotCandidates` | a | `workspace.skills`, `skill.content` |
| 5 | Unknown keys rejected on every definition | `packages/eve/src/public/definitions/exact.ts` : `ExactDefinition` | a | `workspace.agents` — every group is closed, so an unknown key is refused by name |
| 6 | Discovery problems collected and reported together | `packages/eve/src/discover/diagnostics.ts` : `DiscoverDiagnostic` | a | `pact check` |
| 7 | `lib/` helper modules the other slots import | `packages/eve/src/discover/lib.ts` : `discoverLibSources` | c | R5 |
| 8 | Compiling by loading and executing every authored module | `packages/eve/src/compiler/compile-agent.ts` : `compileAgent` | c | R5 |
| 9 | A structured final answer the run must produce | `packages/eve/src/shared/agent-definition.ts` : `PublicAgentDefinition.outputSchema` | a | `agent.answers-with`, `agent.answers-with-mode` |

## 2. Model

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 10 | Model named by AI Gateway id | `packages/eve/src/shared/agent-definition.ts` : `PublicAgentStaticModelDefinition` | a | `agent.model` |
| 11 | Model handed in as an SDK object built in code | `packages/eve/src/shared/agent-definition.ts` : `PublicAgentModelDefinition` | c | R5 |
| 12 | Reasoning effort passed down to the model call | `packages/eve/src/shared/agent-definition.ts` : `AgentReasoningDefinition` | a | `needs.reasoning`, `settings.thinking` |
| 13 | A different model chosen per session, turn or step | `packages/eve/src/shared/agent-definition.ts` : `PublicAgentDynamicModelDefinition` | a | `agent.needs`, `agent.variants` — a switch decided by author code mid-run is R5 |
| 14 | Compaction given its own model and a threshold | `packages/eve/src/shared/agent-definition.ts` : `PublicAgentCompactionDefinition` | a | `context-policy.when-full`, `context-policy.summarised-by` — the summarising call itself is §4 |
| 15 | Input and output token ceilings for one session | `packages/eve/src/shared/agent-definition.ts` : `AgentLimitsDefinition` | a | `limits.tokens-at-most` |
| 16 | Model facts fetched from a hosted catalogue and cached for a day | `packages/eve/src/compiler/model-catalog.ts` : `createCompiledRuntimeModelCatalogLoader` | c | R15 |
| 17 | The author writing the model's context window in by hand | `packages/eve/src/shared/agent-definition.ts` : `PublicAgentDefinition.modelContextWindowTokens` | c | R25 |
| 18 | Provider call settings — temperature, top-p, provider options | `packages/eve/src/shared/agent-definition.ts` : `AgentModelOptionsDefinition` | a | `settings.max-tokens`, `settings.temperature`, `settings.thinking` |

## 3. Tools

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 19 | `defineTool` — a tool with a description, an input shape and a body | `packages/eve/src/public/definitions/tool.ts` : `defineTool` | a | the `tool` group: `action.takes` is the input shape, and the body is where the tool reaches — `tool.connect`, `tool.url` or `tool.says`, exactly one of them. This cell used to name a `runs-as:` word in front of those three that nothing read; it is deleted, R60 |
| 20 | Tool name derived from its path; an authored `name` is rejected | `packages/eve/src/compiler/normalize-tool.ts` : `compileToolEntry` | a | `tool.description` — the file's name is the tool's name, and `tool` has no `name` field to write |
| 21 | Per-tool approval decided at call time from the call's own input | `packages/eve/src/public/definitions/approval.ts` : `Approval` | a | `policy.ask-a-person`, `action.inspects` |
| 22 | A tool result reshaped before the model sees it | `packages/eve/src/public/definitions/tool.ts` : `ToolDefinition.toModelOutput` | c | §6, deferred |
| 23 | `disableTool` — switching off a tool that has no file | `packages/eve/src/public/definitions/tool.ts` : `disableTool` | c | R2 |
| 24 | Five file and shell built-ins offered as helpers | `packages/eve/src/public/tools/define-bash-tool.ts` : `defineBashTool` | c | R1 |
| 25 | `web_fetch` and `web_search`, compiled in, search run by the provider | `packages/eve/src/runtime/framework-tools/web-search.ts` : `WEB_SEARCH_ANTHROPIC_OUTPUT_SCHEMA` | c | R1 |
| 26 | `agent` — the delegation tool the runtime never registers | `packages/eve/src/runtime/framework-tools/agent.ts` : `AGENT_TOOL_DEFINITION` | c | R1 |
| 27 | `ask_question` — the pause-and-wait path for a person | `packages/eve/src/runtime/framework-tools/ask-question.ts` : `ASK_QUESTION_TOOL_NAME` | c | R1 |
| 28 | `todo` — a private store the model keeps a list in | `packages/eve/src/runtime/framework-tools/todo.ts` : `TodoStateKey` | c | R1 |
| 29 | `load_skill` — the private list of loadable skills | `packages/eve/src/runtime/framework-tools/skill.ts` : `SKILL_TOOL_DEFINITION` | c | R1 |
| 30 | `connection_search` — the private list of connected servers | `packages/eve/src/runtime/framework-tools/connection-search-dynamic.ts` : `createConnectionSearchResolver` | c | R1 |
| 31 | Read-before-write enforcement on file edits | `packages/eve/src/runtime/framework-tools/file-state.ts` : `ReadFileStateKey` | c | §6, deferred |
| 32 | A tool fetching its own token inline, mid-call | `packages/eve/src/public/definitions/tool.ts` : `ToolContext` | a | `resource.auth`, `resource.asks-to-connect` |
| 33 | Tools produced at run time by a resolver | `packages/eve/src/public/definitions/tool.ts` : `defineDynamic` | a | `stage.may-use`, `agent.uses` |
| 34 | A tool letting the model author JavaScript that fans out to children | `packages/eve/src/public/definitions/tool.ts` : `isExperimentalWorkflowToolDefinition` | c | R16 |

## 4. Context

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 35 | Instructions as one file, a module, or a directory of layers | `packages/eve/src/discover/manifest.ts` : `AgentSourceManifest.instructions` | a | `agent.instructions` |
| 36 | Skills as markdown the model pulls in on demand | `packages/eve/src/discover/skills.ts` : `discoverSkills` | a | `workspace.skills`, `agent.uses` |
| 37 | Skill packages carrying sibling files beside the markdown | `packages/eve/src/shared/skill-definition.ts` : `SkillPackageDefinition` | a | `skill.references`, `skill.scripts`, `skill.assets` |
| 38 | Instructions and skills produced at run time by a resolver | `packages/eve/src/runtime/resolve-dynamic-instructions.ts` : `resolveDynamicInstructionsDefinition` | a | `stage.says`, `agent.variants` |
| 39 | `defineState` — a named store that survives step boundaries | `packages/eve/src/public/definitions/state.ts` : `defineState` | b | §4, `remembers:` |
| 40 | One-turn caller context attached to a message | `packages/eve/src/client/types.ts` : `SendTurnPayload` | a | `agent.run-inputs` |
| 41 | The compaction algorithm — summarise older, keep a recent window | `packages/eve/src/harness/compaction.ts` : `compactMessages` | a | `context-policy.then`, `tidy-step.what`, `tidy-step.down-to` |

## 5. Delegation

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 42 | Subagents declared as their own folders with their own slots | `packages/eve/src/compiler/normalize-subagent.ts` : `compileSubagentGraph` | a | `agent.team` |
| 43 | A subagent reached as a tool call | `packages/eve/src/execution/subagent-tool.ts` : `buildSubagentRunInput` | a | `agent.team`, `agent.teamwork` |
| 44 | Several children started in one response | `packages/eve/src/runtime/framework-tools/agent.ts` : `AGENT_TOOL_DESCRIPTION` | a | `teamwork.starts` |
| 45 | A child's budget inherited from and capped by the parent's | `packages/eve/src/harness/subagent-token-budget.ts` : `resolveRemainingSessionTokenLimits` | a | `teamwork.divides-the-budget`, `teamwork.shares` |
| 46 | Remote agents living on another deployment | `packages/eve/src/public/definitions/remote-agent.ts` : `defineRemoteAgent` | c | §6, deferred — a port is inbound, so nothing here names a teammate on another deployment |
| 47 | Identity forwarded to a remote agent, current and initiator kept apart | `packages/eve/src/channel/forwarded-principal.ts` : `parseForwardedPrincipal` | b | §4, seven ways of verifying a caller |
| 48 | A child's question relayed to the person through the parent | `packages/eve/src/execution/subagent-hitl-proxy.ts` : `emitProxiedInputRequest` | a | `question.escalates-to` |

## 6. Connections

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 49 | An MCP client connection over HTTP or SSE | `packages/eve/src/public/definitions/connections/mcp.ts` : `defineMcpClientConnection` | a | `resource.resource-kind`, `resource.endpoint` |
| 50 | An OpenAPI 3.x or Swagger 2.0 connection | `packages/eve/src/public/definitions/connections/openapi.ts` : `defineOpenAPIConnection` | a | `resource`, `tool.connect` |
| 51 | Choosing which of a server's tools are exposed | `packages/eve/src/public/definitions/connections/mcp.ts` : `McpClientConnectionDefinition` | a | `tool.actions`, `action.takes` |
| 52 | Interactive authorisation that parks the run and resumes on callback | `packages/eve/src/runtime/connections/types.ts` : `defineInteractiveAuthorization` | a | `resource.asks-to-connect` |
| 53 | Per-principal scoped tokens, cached and evicted | `packages/eve/src/runtime/connections/scoped-authorization.ts` : `resolveScopedToken` | b | §4, seven ways of verifying a caller |
| 54 | One approval covering every tool a connection brings | `packages/eve/src/public/definitions/connections/mcp.ts` : `McpClientConnectionDefinition` | a | `policy.ask-a-person` |
| 55 | Extra headers sent to a connected server | `packages/eve/src/public/definitions/connections/mcp.ts` : `HeadersDefinition` | a | `resource.auth` — references, never values |

## 7. Channels

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 56 | Eight platform channels shipped ready to mount | `packages/eve/src/public/channels/index.ts` : the `slack`, `discord`, `teams`, `telegram`, `twilio`, `github`, `linear`, `chat-sdk` exports | b | §4, eight platform connectors |
| 57 | `defineChannel` for a ninth | `packages/eve/src/public/definitions/channel.ts` : `defineChannel` | a | `port.kind`, `port.through` |
| 58 | Routes, including WebSocket upgrades | `packages/eve/src/channel/routes.ts` : `RouteHandlerArgs` | b | §4, the connector |
| 59 | Durable per-channel state | `packages/eve/src/public/definitions/channel.ts` : `ChannelDefinition` | a | `port.remembers` |
| 60 | Sixteen run events a channel may act on | `packages/eve/src/protocol/message.ts` : `HandleMessageStreamEvent` | a | `interceptor.when`, the event address |
| 61 | One channel starting a session on another | `packages/eve/src/channel/cross-channel-receive.ts` : `createCrossChannelReceiveFn` | c | R23 |
| 62 | Continuation tokens re-keyed as a conversation moves | `packages/eve/src/execution/reconcile-session-continuation-token.ts` : `reconcileSessionContinuationToken` | a | `port.same-conversation-when` |
| 63 | Cross-origin rules per channel | `packages/eve/src/channel/cors.ts` : `ChannelCorsOptions` | b | §4, the connector |
| 64 | An upload policy deciding what files a channel accepts | `packages/eve/src/public/channels/upload-policy.ts` : `UploadPolicyConfig` | b | §4, the connector |

## 8. Auth

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 65 | An ordered walk of verifiers over an inbound request | `packages/eve/src/public/channels/auth.ts` : `routeAuth` | b | §4, seven ways of verifying a caller |
| 66 | Seven built-in verifiers | `packages/eve/src/public/channels/auth.ts` : `verifyHttpBasic`, `verifyJwtHmac`, `verifyJwtEcdsa`, `verifyOidc`, `verifyVercelOidc`, `none`, `localDev` | b | §4, seven ways of verifying a caller |
| 67 | Challenges from every verifier gathered into one refusal | `packages/eve/src/public/channels/auth.ts` : `withAuthChallenges` | b | §4, seven ways of verifying a caller |
| 68 | Principal lineage — who is calling now, and who started it | `packages/eve/src/channel/forwarded-principal.ts` : `ForwardedPrincipal` | b | §4, seven ways of verifying a caller |
| 69 | Outbound auth for calling another deployment | `packages/eve/src/public/agents/auth.ts` : `OutboundAuthFn` | a | `resource.auth` |
| 70 | An address allow list in front of a channel | `packages/eve/src/runtime/governance/network/ip-allow-list.ts` : `createIpAllowList` | b | §4, `who-can-reach-it:` |

## 9. Sandbox

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 71 | `defineSandbox` — the box an agent's commands run in | `packages/eve/src/public/definitions/sandbox.ts` : `defineSandbox` | a | `resource.resource-kind`, `resource.auth` |
| 72 | Four backends plus a custom one | `packages/eve/src/public/sandbox/backends/microsandbox.ts` : `microsandbox` | b | §4, four sandbox implementations |
| 73 | `bootstrap` once and `onSession` each time | `packages/eve/src/public/definitions/sandbox.ts` : `SandboxBootstrapUseFn`, `SandboxSessionUseFn` | b | §4, the sandbox |
| 74 | A `workspace/` folder seeded into the sandbox at session start | `packages/eve/src/discover/manifest.ts` : `SandboxWorkspaceFolderSourceRef` | a | `skill.assets`, `resource.endpoint` |
| 75 | A network policy and brokered credentials inside the box | `packages/eve/src/public/sandbox/backends/microsandbox.ts` : `microsandbox` | a | `workspace.allow-egress` — the brokering itself is the host's |

## 10. Runtime

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 76 | Sessions, turns and steps that survive the process dying | `packages/eve/src/execution/durable-session-store.ts` : `DurableSession` | b | §4, durable sessions turns and steps |
| 77 | Five separate kinds of pause, each with its own bookkeeping | `packages/eve/src/execution/workflow-steps.ts` : `NextDriverAction` | c | R12 |
| 78 | A twenty-eight event stream, one JSON object per line | `packages/eve/src/protocol/message.ts` : `HandleMessageStreamEvent` | b | §4, a stream of run events |
| 79 | Rewinding that stream from an offset after a reconnect | `packages/eve/src/client/open-stream.ts` : `followStreamIterable` | b | §4, the transport |
| 80 | Cancelling a turn in flight, as a normal ending | `packages/eve/src/execution/turn-cancellation-control.ts` : `createTurnCancellationControl` | b | §4, cancelling a turn in flight |
| 81 | Resetting a session and starting the conversation over | `packages/eve/src/channel/reset-session.ts` : `createResetFn` | b | §4, the store |
| 82 | Cron schedules that start a run on their own | `packages/eve/src/public/definitions/schedule.ts` : `defineSchedule` | a | `port.every`, `port.if-still-running` |
| 83 | Twenty-eight hook events, all observe-only | `packages/eve/src/public/definitions/hook.ts` : `defineHook` | a | `watch.when`, `watch.writes-to` |
| 84 | Extensions mounted from packages, eleven versioned contracts | `packages/eve/src/compiler/extension-compatibility.ts` : `EXTENSION_CAPABILITY_CONTRACTS` | c | R17 |
| 85 | Prompt-cache markers placed for the provider that supports them | `packages/eve/src/harness/prompt-cache.ts` : `detectPromptCachePath` | c | R46 |
| 86 | An instrumentation slot for OpenTelemetry setup | `packages/eve/src/public/instrumentation/index.ts` : `defineInstrumentation` | b | §4, a stream of run events |

## 11. Evals

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 87 | `defineEval` — one check, written as TypeScript | `packages/eve/src/evals/define-eval.ts` : `defineEval` | c | R18 |
| 88 | `defineEvalConfig` — the suite's models, reporters and thresholds | `packages/eve/src/evals/define-eval-config.ts` : `defineEvalConfig` | c | R18 |
| 89 | Four judge-based measures | `packages/eve/src/evals/judge.ts` : `buildJudgeContext` | a | `evals.graded-by` |
| 90 | Assertions gathered while the run happens, not after | `packages/eve/src/evals/assertions/collector.ts` : `AssertionCollector` | a | `case.expect`, `case.must-also` |

## 12. Developer experience, catalogue and templates

| # | Capability, as Eve names it | Read from | a/b/c | Where it lands |
|---|---|---|---|---|
| 91 | A typed HTTP client for talking to a deployed agent | `packages/eve/src/client/client.ts` : `Client` | c | R4 |
| 92 | React, Vue and Svelte hooks over that client | `packages/eve/src/react/use-eve-agent.ts` : `useEveAgent` | c | R4 |
| 93 | The `eve` command line | `packages/eve/src/cli/commands/register-project-commands.ts` : `registerProjectCommands` | a | `pact check`, `pact show`, `pact discover`, `pact card`, `pact waits` |
| 94 | The development console in the terminal | `packages/eve/src/cli/dev/tui/terminal-renderer.ts` : `TerminalRenderer` | c | R4 |
| 95 | A setup flow that scaffolds a project and connects a channel | `packages/eve/src/setup/onboarding.ts` : `composeOnboardingBoxes` | c | §6, deferred — no verb scaffolds a workspace yet |
| 96 | The CLI editing the author's source file to record a choice | `packages/eve/src/source-change/apply-model-name.ts` : `applyModelNameToSource` | a | `workspace.agents` — the files are the API for every surface (D18) |
| 97 | Mount points for Next, Nuxt and SvelteKit | `packages/eve/src/public/next/index.ts` : `EveNextConfig` | b | §4, the connector |
| 98 | An integration catalogue — 25 channels, 40 connections, 5 extensions | `packages/eve-catalog/src/index.ts` : `INTEGRATIONS` | a | `resource.endpoint` names the server; which servers a machine has is the host's, §4 |
| 99 | `defineExtension` — tools, connections, skills, instruction fragments and hooks packaged as one installable npm unit | `packages/eve/src/public/definitions/extension.ts` : `defineExtension` | c | §6, deferred — G10 `bundle` is the re-admission fixture; PACT has no distribution unit today |
| 100 | `experimental_workflow` — the model orchestrates the agent's own subagents from model-authored JavaScript, one durable step, `maxSubagents` 100 | `packages/eve/src/harness/workflow-subagent-limit.ts` : `DEFAULT_WORKFLOW_MAX_SUBAGENTS` | c | R5 and R42 — a spec that names code to run makes `pact check` decide whether that code is safe |
| 101 | `experimental_setAttributes` — author-set span attributes on the active trace | `packages/eve/src/public/instrumentation/index.ts` : `experimental_setAttributes` | b | §4, the exporter |

---

## What the enumeration turned up

Three things worth carrying forward, each of which came out of walking the
source rather than the condensation:

1. **Row 60 and row 83 are the same lattice from two ends.** A channel may act
   on sixteen of the twenty-eight run events; a hook may observe all twenty-eight.
   Eve has two closed unions of event names for one set of moments. PACT has one
   address, written once and pointed at from both halves — which is why row 60
   lands on `interceptor.when` and row 83 on `watch.when`, and why a bad address
   in either is refused by the same tool under the same rule name. Row 83 pointed
   at `interceptor.may` for a round, and that was wrong in the direction that
   matters: every one of Eve's twenty-eight hooks is **observe-only**, so
   accounting for them under the half that CHANGES things put the safe capability
   behind the dangerous one's review.
2. **Row 45 is the only budget rule Eve has, and it is the right one.** A child
   can never outspend its parent's remaining quota — enforced at dispatch, not
   documented as guidance. PACT's `teamwork.divides-the-budget` owes it.
3. **Row 96 is the shape of D18 done by hand.** Eve's model picker edits
   `agent.ts` through an AST rewrite because its source of truth is code. When
   the source of truth is YAML, the same feature is a file write, which is why
   PACT gets four author surfaces for the price of one format.
