# PACT research stream: **protocols-interop**

**Author:** research subagent · **Pass 2, date 2026-08-07** (pass 1 was 2026-07-26)
**Scope:** MCP, A2A, the three ACPs, AGNTCY OASF (+ `agntcy-dir`, the reference registry),
AG-UI, agents.md, OTel `gen_ai` semantic conventions, CloudEvents, Serverless Workflow, OAM.
Boundary case included because it lives in `protocols/` and bears on deliverable (d):
Oracle **Open Agent Spec**.

**Method.** Read spec source (`.proto`, `schema.ts`, `schema.json`, `*.yaml`/`*.json`
registries, and the reference implementations' Go/Python/Rust) in
`/home/bud/ditto/agent-inter-op/research/repos/protocols/`, not READMEs, wherever the
two could disagree. Every claim carries a `file:line` or `file` citation. Statements that
are my inference rather than something I read are marked **[INFERRED]**.

**What changed in pass 2.** The corpus HEADs are byte-identical to pass 1 (verified below),
so nothing upstream moved. Pass 2 therefore (i) re-verified pass 1's load-bearing claims
against source, (ii) **closed five of the seven open questions** using repos that were in
the corpus but unaudited (`agntcy-dir`, `agent-client-protocol/schema/v1`,
`a2a-spec/docs/topics/extension-and-binding-governance.md`, `oracle-agent-spec`), and
(iii) **corrected four pass-1 claims**. Corrections are marked **[CORRECTION — pass 1]**
and collected in §16.

**Corpus commits pinned at read time (unchanged since pass 1):**

| Repo | HEAD | Commit date |
|---|---|---|
| `mcp-spec` | `7634684382c3` | 2026-07-23 |
| `mcp-python-sdk` | `629ca297d24b` | 2026-07-25 |
| `a2a-spec` | `0ef1b02547e9` | 2026-07-23 |
| `a2a-python` | `086d70fffbc4` | 2026-07-23 |
| `acp` (IBM/BeeAI) | `e5265ca9fa06` | **2025-08-25** |
| `agntcy-oasf` | `e8565371ddfe` | 2026-07-21 |
| `agntcy-dir` | `4f1ec1af810e` | 2026-07-24 |
| `agent-client-protocol` (Zed) | `649cc279fa87` | 2026-07-25 |
| `ag-ui` | `ab9ae4594147` | 2026-07-24 |
| `agents-md` | `d1ac7f063d20` | **2026-03-12** |
| `otel-semconv` | `bfa549224a08` | 2026-07-24 |
| `cloudevents` | `c2845a49bc98` | 2026-07-23 |
| `serverless-workflow` | `44c3ecf76ee2` | 2026-07-23 |
| `oam-spec` | `a64696e70e24` | **2024-12-24** |
| `oracle-agent-spec` | `6668ae0bd9a5` | 2026-06-29 |

---

## 0. The one-paragraph answer

**No protocol in this corpus defines an agent.** Each defines either a *transport*
(MCP, A2A, Zed ACP, AG-UI), an *observation format* (OTel `gen_ai`, CloudEvents), a
*catalogue record* (AGNTCY OASF, MCP registry `server.json`), a *workflow*
(Serverless Workflow), a *deployment topology* (OAM), or *nothing at all* (agents.md is
a marketing website with no schema). Literal proof: the MCP draft schema contains the
substring `agent` **zero** times (`mcp-spec/schema/draft/schema.ts`, `grep -c agent` → `0`);
the A2A `.proto` contains no `json_schema`, `inputSchema`, or `outputSchema` field
anywhere (`a2a-spec/specification/a2a.proto`, grep → no hits). The single object in the
corpus that ever carried JSON Schema for an agent's *input and output* — AGNTCY's
`acp_agent` — was **deprecated in OASF 0.8.0**
(`agntcy-oasf/schema/objects/acp.json:6-9`). PACT is therefore not competing with any of
these; it fills the hole they all leave. Its job at every boundary is **projection plus a
loss report**, never adoption.

**The sharpest new evidence for that, from pass 2:** AGNTCY has already conceded the point
structurally. OASF 1.2.0-dev ships an `integration/agentspec` module whose entire payload
is a *locator to a config file elsewhere* plus deployment options plus
`runtime_deps` — "locators for the non-serializable objects the Agent Spec config depends
on (e.g. tool implementations)" (`agntcy-oasf/schema/objects/agentspec_data.json`). The
best registry standard in the space models a real agent spec as **an opaque pointer**,
because it cannot model its interior. That is exactly the seam PACT should use, and
exactly the reason PACT cannot *be* OASF.

---

# PART A — What each protocol does and does not cover for agent DEFINITION

## 1. MCP — Model Context Protocol

### 1.1 What it standardises

A JSON-RPC 2.0 protocol between a **host/client** and a **server** that supplies three
primitives to a model:

| Primitive | Schema | 2025-11-25 | draft (2026-07-28) |
|---|---|---|---|
| **Tool** | `name`, `title`, `description`, `inputSchema` (JSON Schema 2020-12, root `type:"object"`), `outputSchema`, `annotations`, `icons`, `_meta` | `schema/2025-11-25/schema.ts:1249` | `schema/draft/schema.ts:1960` |
| **Prompt** | `name`, `title`, `description`, `arguments[]` | `schema/2025-11-25/schema.ts:984-1020` | `schema/draft/schema.ts:1646` |
| **Resource** / **ResourceTemplate** | `uri` (or `uriTemplate`, RFC 6570), `name`, `title`, `description`, `mimeType`, `annotations`, `size`, `_meta` | `schema/2025-11-25/schema.ts:802-878` | `schema/draft/schema.ts:1428` |

Client-side: `roots`, `sampling`, `elicitation`, `completion`.

`ToolAnnotations` (`schema/draft/schema.ts:1899`, `schema/2025-11-25/schema.ts:1180`) is
the only behavioural metadata MCP carries about a tool — `readOnlyHint`,
`destructiveHint`, `idempotentHint`, `openWorldHint` — and all four are explicitly
**hints**, not guarantees.

### 1.2 Extension mechanism — two, and they are different

1. **`_meta`** on almost every object. Key format is normative
   (`docs/specification/draft/basic/index.mdx:330-344`, identical text at
   `docs/specification/2025-11-25/basic/index.mdx:199-216`):
   - optional dotted-label **prefix** ending in `/`; labels start with a letter and end
     with a letter or digit; reverse-DNS **SHOULD** be used;
   - *"Any prefix where the second label is `modelcontextprotocol` or `mcp` is
     **reserved**"* — the spec spells out that `dev.mcp/` and `com.mcp.tools/` are
     reserved but `com.example.mcp/` is not;
   - name segment must begin and end alphanumeric, may contain `-`, `_`, `.`.
2. **Capability-negotiated extensions** (draft only), identified by the *same* key format
   with a **mandatory** prefix, declared in `capabilities.extensions` as a map of
   identifier → settings object
   (`docs/specification/draft/basic/versioning.mdx:80-123`). The negotiation rule is
   explicit: *"If one party supports an extension but the other does not, the supporting
   party MUST either revert to core protocol behavior or reject the request with an
   appropriate error"* (`versioning.mdx:120-123`).

**Reserved `_meta` keys in draft** (`index.mdx:348-358`): `progressToken`,
`io.modelcontextprotocol/{protocolVersion,clientInfo,clientCapabilities,logLevel,subscriptionId}`,
and — **as an explicit exception to the prefix rule** — `traceparent`, `tracestate`,
`baggage` for W3C Trace Context (`index.mdx:426-433`). **[NEW in pass 2.]** This is a
normative, first-class OTel propagation slot in MCP, and PACT's harness should use it (§11.4).

### 1.3 Version story — and the break that matters

Date-based versions, not semver. Released: `2024-11-05`, `2025-03-26`, `2025-06-18`,
`2025-11-25`, `2026-07-28` (`mcp-python-sdk/src/mcp-types/mcp_types/version.py:12-17`).

**`2026-07-28` is a structural break.** The `initialize` handshake is *gone*:

- *"There is no negotiation handshake. Every request carries its protocol version"* —
  `docs/specification/draft/basic/versioning.mdx:12-13`.
- Version, client identity and client capabilities move into per-request `_meta`;
  `io.modelcontextprotocol/protocolVersion` and `…/clientCapabilities` are **REQUIRED on
  every request**, and *"A request missing any required field is malformed; the server
  MUST reject it with JSON-RPC error code `-32602`"* (`index.mdx:367-383`).
- New `server/discover` (`schema/draft/schema.ts:665-697`) returns `supportedVersions[]`,
  `capabilities`, and — critically for PACT — **`instructions?: string`**:
  *"Natural-language guidance describing the server and its features… can be used by
  clients to improve an LLM's understanding of available tools (e.g., by including it in a
  system prompt)"* (`schema.ts:688-697`).
- `DiscoverResult extends CacheableResult` (`schema.ts:1081-1110`) — `ttlMs` +
  `cacheScope: "public" | "private"`. **[NEW in pass 2.]** MCP now has explicit cache
  semantics for discovery, which PACT's air-gapped resolver can honour offline.
- The SDK splits eras: `HANDSHAKE_PROTOCOL_VERSIONS` vs `MODERN_PROTOCOL_VERSIONS`
  (`version.py:21-31`); the compatibility matrix says Modern-client/Legacy-server and
  Legacy-client/Modern-server **both FAIL** (`versioning.mdx:164-172`).
- `logging`, `roots`, and **`sampling`** are all deprecated as of `2026-07-28` under
  SEP-2577 (`schema/draft/schema.ts:724-758`), retained ≥12 months.
- `tasks` left the core schema and became the `io.modelcontextprotocol/tasks` extension:
  `CreateTaskResult`, `GetTaskRequest`, `ListTasksRequest`, `CancelTaskRequest` and
  `Tool.execution` are present at `schema/2025-11-25/schema.ts:1229-1505` and **absent
  from `schema/draft/schema.ts`**.

### 1.4 The capability-failure error — a shape PACT should copy

**[NEW in pass 2.]** `MissingRequiredClientCapabilityError` (`schema/draft/schema.ts:513-525`,
code `-32021`) carries `data.requiredCapabilities: ClientCapabilities` — a **structured
statement of exactly which capabilities the caller lacks**, not a string. `ClientCapabilities`
is explicitly an open set: *"this is not a closed set: any client can define its own,
additional capabilities"* (`schema.ts:711-714`).

This is the only place in the corpus where "I cannot serve you, and here is the machine-readable
reason" is a first-class protocol object. It is the exact shape of D11's *fail, then
recommend*: `{ verdict: fail, requiredCapabilities: [...] }`.

### 1.5 Elicitation — and its schema ceiling

`ElicitRequestParams = ElicitRequestFormParams | ElicitRequestURLParams`
(`schema/draft/schema.ts:2775-2833`). The form mode carries `requestedSchema`, but:

> *"A restricted subset of JSON Schema. **Only top-level properties are allowed, without
> nesting.**"* — `schema/draft/schema.ts:2787-2789`

**[NEW in pass 2.]** This is a hard ceiling on PACT's no-code HITL: a PACT approval form
declared in YAML with any nested object cannot round-trip through MCP elicitation. PACT
must either restrict declarative HITL forms to flat primitives, or flatten-with-report at
the MCP boundary. Silently flattening violates T7.

### 1.6 What MCP does NOT cover for agent DEFINITION

- **No agent.** `grep -c agent schema/draft/schema.ts` → `0`. Verified pass 2.
- No model selection beyond a *hint* list: `ModelPreferences`/`ModelHint` exist only inside
  `sampling` (`schema/2025-11-25/schema.ts:1925-1998`), and sampling is now deprecated.
- No loop, no topology, no memory, no handoff, no eval, no SLO, no cost, no policy.
- **No video and no computer-use content type.** `ContentBlock = TextContent |
  ImageContent | AudioContent | ResourceLink | EmbeddedResource` — *identical* in
  `schema/draft/schema.ts:2292-2293` and `schema/2025-11-25/schema.ts:1740-1741`;
  `grep -in "video\|computer_use"` on the draft schema → **no hits**. Verified pass 2.
  A hard blocker for D16 modality parity if PACT tried to use MCP content as its I/O type
  system.
- **No declarative authoring surface.** Tools are code; there is no `tool.yaml` in the spec
  or in `mcp-python-sdk`. **The single biggest gap between MCP and D14 (no-code ceiling).**
- Prompt arguments are `{name, title, description, required}` only — **no type, no schema**
  (`PromptArgument extends BaseMetadata`, `schema/2025-11-25/schema.ts:1006-1015`). A PACT
  parameterised skill cannot round-trip through `prompts/list` without loss.

### 1.7 The MCP registry (`server.json`)

`docs/registry/versioning.mdx:11-30`: `$schema`, `name` (`io.github.user/thing`), `title`,
`description`, `version`, `packages[]` with `registryType` ∈ {npm, pypi, …}, `identifier`,
`version`, `transport.type`. Ownership verified out-of-band (npm `package.json.mcpName`
must equal `server.json.name`, `docs/registry/package-types.mdx:41-49`). Version strings
may be any format but **ranges are prohibited** (`versioning.mdx:44-66`). The registry is
in **preview**: *"breaking changes or data resets may occur"* (`versioning.mdx:6`).

This is a *distribution* manifest for a server process. It has no tools, prompts, or
capabilities — those are discovered at runtime. **Still not in the corpus** (open question
2 stands): `find mcp-spec -iname "*server*.json"` returns only draft examples.

---

## 2. A2A — Agent2Agent (Linux Foundation)

### 2.1 Status and version story

**v1.0.1, released 2026-05-26** (`CHANGELOG.md:3`). v1.0.0 (2026-03-12) was a large
breaking release: package renamed `lf.a2a.v1`, `preferredTransport`/`url` replaced by
`supportedInterfaces[]`, `TaskPushNotificationConfig` merged, OAuth implicit/password
removed, ProtoJSON enum alignment (`CHANGELOG.md:14-32`).

Versioning is **per-interface, not per-server**: `AgentInterface.protocol_version` is a
REQUIRED string like `"0.3"` or `"1.0"` (`specification/a2a.proto:352-355`); one card may
advertise several interfaces at different versions. There is no global handshake.

Canonical data model is **Protocol Buffers**; all bindings must be functionally equivalent
(`docs/specification.md:768`, `1145-1152`). JSON serialisation is ProtoJSON: camelCase
fields, SCREAMING_SNAKE_CASE enums (`docs/specification.md:1204-1222`). Three official
bindings — `JSONRPC`, `GRPC`, `HTTP+JSON` (`specification/a2a.proto:341-344`); custom
bindings SHOULD be identified by URI (`docs/specification.md:1279-1302`).

### 2.2 The AgentCard, field by field

`specification/a2a.proto:362-399` (`// Next ID: 20`, max used = 14 → fields 15–19 are burned):

| # | Field | Req | Notes |
|---|---|---|---|
| 1 | `name` | ✔ | |
| 2 | `description` | ✔ | |
| 3 | `supported_interfaces[]` | ✔ | ordered; first = preferred |
| 4 | `provider` | | `{url✔, organization✔}` (`:402-409`) |
| 5 | `version` | ✔ | free-form string, of the *agent* |
| 6 | `documentation_url` | | |
| 7 | `capabilities` | ✔ | `{streaming?, push_notifications?, extensions[], extended_agent_card?}` (`:412-421`) |
| 8 | `security_schemes` | | map → APIKey / HTTPAuth / OAuth2 / OIDC / mTLS |
| 9 | `security_requirements[]` | | |
| 10 | `default_input_modes[]` | ✔ | *"Defined as media types."* |
| 11 | `default_output_modes[]` | ✔ | |
| 12 | `skills[]` | ✔ | |
| 13 | `signatures[]` | | JWS per RFC 7515 (`:457-467`) |
| 14 | `icon_url` | | |

`AgentSkill` (`:436-453`): `id`✔, `name`✔, `description`✔, `tags[]`✔, `examples[]`,
`input_modes[]`, `output_modes[]`, `security_requirements[]`.

**There is no `metadata` field on `AgentCard`.** Re-verified pass 2 by reading
`a2a.proto:362-399` in full. There is no schema field anywhere in the proto.

`AgentInterface` (`:336-356`): `url`✔, `protocol_binding`✔ (open string), `tenant`
(opaque routing key — A2A's *entire* multi-tenancy story), `protocol_version`✔.

### 2.3 Signing — and why a non-standard top-level key is dangerous

`docs/specification.md:2002-2083`. Canonicalisation is **RFC 8785 JCS** over the card with
`signatures` removed *and* proto field-presence semantics applied (optional-unset fields
omitted, REQUIRED fields always present even at default value, `:2012-2023`). Meanwhile
§5.7 says *"Implementations SHOULD ignore unrecognized fields"* (`:1275`).

**Consequence:** a producer that adds a non-standard top-level key and signs the card
produces a JCS payload containing that key; a consumer that parses into the proto (dropping
the unknown field) and re-canonicalises produces a *different* payload, and verification
fails. Unknown-field tolerance and signature verification are in direct tension. Any PACT
data on an Agent Card **must** go in a standard field. **[INFERRED]** — the two clauses are
each explicit; the conflict is my deduction.

### 2.4 Extension mechanism — the right hook for PACT

`AgentExtension` (`specification/a2a.proto:424-433`): `uri`, `description`, `required`,
**`params` (`google.protobuf.Struct`)** — arbitrary JSON in a *standard* field. Declared
under `capabilities.extensions`; clients opt in per-request via binding-specific mechanisms
(HTTP header `A2A-Extensions`, `docs/specification.md:1051-1060`). Extension URIs SHOULD
carry a version; **breaking changes MUST mint a new URI** and *"MUST NOT fall back to a
previous version automatically"* (`docs/specification.md:1139-1141`).

The governance doc names exactly the category PACT needs: *"**Data-only Extensions**:
Exposing new, structured information in the Agent Card that doesn't impact the
request-response flow"* (`docs/topics/extensions.md:26-29`).

**Open question 5 CLOSED.** `docs/topics/extension-and-binding-governance.md:8-10`:
*"Anyone may develop and publish extensions or custom protocol bindings **independently**.
The tiers and lifecycle described here apply specifically to those hosted under the
`a2aproject` GitHub organization."* Two tiers exist inside `a2aproject` (Official
`ext-{name}` → `https://a2a-protocol.org/extensions/`; Experimental `experimental-ext-{name}`,
requiring maintainer sponsorship), with per-artifact URIs of the form
`https://a2a-protocol.org/extensions/{name}/v1` (`:31-38`). Critically: *"These URIs are
identifiers, **HTTP access is not expected**"* (`:38`) — so a PACT extension URI is
air-gap-safe by construction (D17). **No registration is required for a third-party URI.**

### 2.5 Runtime model

`Task` (`:167-183`) = `id`, `context_id`, `status`, `artifacts[]`, `history[]`, `metadata`.
`TaskState` (`:187-208`) — 8 states + UNSPECIFIED: SUBMITTED, WORKING, COMPLETED, FAILED,
CANCELED, INPUT_REQUIRED, REJECTED, AUTH_REQUIRED. `Part` (`:224-241`) is a `oneof` of
`text | raw(bytes) | url | data(Value)` **plus** `media_type` and `filename` on *every*
part — so A2A can carry video and computer-use screenshots by media type where MCP cannot.
`Message` (`:260-277`) carries `extensions[]` (URIs) and `reference_task_ids[]`.
Discovery: `GET /.well-known/agent-card.json` (`docs/specification.md:1978`; IANA
registration at `:3326-3353`).

### 2.6 What A2A does NOT cover for agent DEFINITION

- **No I/O schema.** Only media types. A skill cannot say "my input is this JSON Schema."
- No model, no model requirements, no capability predicates.
- No evals, thresholds, SLOs, cost, budget, token accounting.
- No instructions/system prompt, no loop, no memory, **no topology** — a supervisor and its
  three specialists are four unrelated cards with nothing linking them.
- No versioned lineage: `version` is a free string with no `previous` pointer.
- No provenance beyond `provider` + optional JWS.
- Multi-tenancy is one opaque `tenant` string (`:345-351`) — consistent with D24's
  "minimal, adapter-shaped" constraint, but it means A2A gives PACT nothing for tenancy.

---

## 3. The three ACPs — disambiguation

| # | Name | Owner | Repo | Status |
|---|---|---|---|---|
| 1 | **Agent Communication Protocol** | IBM / BeeAI | `protocols/acp` | **DEAD.** *"ACP is now part of A2A under the Linux Foundation!"*; last commit **2025-08-25** (`README.md:20-24`) |
| 2 | **Agent Connect Protocol** | AGNTCY | OASF `schema/objects/acp*.json` | **DEPRECATED** since OASF 0.8.0, *"please use A2A instead"* (`schema/objects/acp.json:6-9`) |
| 3 | **Agent Client Protocol** | Zed | `protocols/agent-client-protocol` | **ALIVE**, schemas v1 and v2 both shipped |

**Do not target #1 or #2. Never write "ACP" unqualified in normative PACT text.**

### 3.1 Zed agent-client-protocol — and the v1↔v2 delta (open question 3 CLOSED)

An **editor ⇄ coding-agent session protocol**, JSON-RPC. v1 has 168 `$defs`, v2 has 172
(`schema/v1/schema.json`, `schema/v2/schema.json`).

**Method surface, diffed (`schema/v{1,2}/meta.json`):**

| Side | v1 only | v2 only | Both |
|---|---|---|---|
| Agent | `authenticate`, `session/load`, `session/set_mode` | `auth/login`, `auth/logout` | `initialize`, `session/{new,prompt,cancel,list,delete,resume,close,set_config_option}`, `logout`* |
| Client | **`fs/read_text_file`**, **`fs/write_text_file`**, **`terminal/{create,kill,output,release,wait_for_exit}`** | — | `session/request_permission`, `session/update`, `elicitation/{create,complete}` |

\* v1 spells it `logout`; v2 splits auth into `auth/login` + `auth/logout`.

**The load-bearing change: v2 deletes the entire client-side filesystem and terminal
capability surface.** v1's `ReadTextFileRequest`, `WriteTextFileRequest`,
`CreateTerminalRequest`, `KillTerminalRequest`, `TerminalOutputRequest`,
`ReleaseTerminalRequest`, `WaitForTerminalExitRequest` and `FileSystemCapabilities` are all
absent from v2's `$defs`. v2 replaces them with agent→client *notifications*:
`TerminalUpdate` (upsert with patch semantics — *"omitted fields leave the stored value
unchanged, `null` clears it"*), `TerminalOutput`, `TerminalOutputChunk`. **The direction of
control inverted**: in v1 the agent *called* the editor to read files and run terminals; in
v2 the agent owns the terminal and *reports* it.

Other v2-only `$defs` that matter to PACT: `StateUpdate` / `RunningStateUpdate` /
`IdleStateUpdate` / `RequiresActionStateUpdate`, `ReplayFrom` / `ReplayFromStart`,
`PlanUpdate` / `PlanId` / `PlanItems`, `DiffPatch` / `DiffChange` / `DiffPatchFormat`,
`McpHttpCapabilities` / `McpStdioCapabilities`, `PromptAudioCapabilities` /
`PromptImageCapabilities` / `PromptEmbeddedContextCapabilities`, `Icon` / `IconTheme`,
`MediaType`, `ToolCallPermissionSubject` / `CommandPermissionSubject`,
`AgentMessage` / `UserMessage` / `AgentThought`.

**v2's run-state model is the best in the corpus.** `StateUpdate` is a three-way union —
`running`, `idle`, `requires_action` — and *`stopReason` hangs off `idle`, not off the
state itself*:

> `StateUpdate`: *"The state of the agent's foreground work has changed. Background
> activity can continue and emit other `session/update` notifications while `idle`.
> Those notifications do not change this state."*
> `IdleStateUpdate.stopReason`: *"Indicates why foreground work stopped. Optional. Omitted
> or `null` both mean the agent is not reporting a stop reason."*
> — `schema/v2/schema.json`, `$defs.StateUpdate` / `$defs.IdleStateUpdate`

`StopReason` = `end_turn | max_tokens | max_turn_requests | refusal | cancelled` + open
`other`. **Lifecycle state and stop reason are orthogonal.** A2A conflates them into one
8-member `TaskState`; Zed v2 separates them, and Zed is right (§14.1).

**Three vocabularies worth adopting wholesale:**

- `ToolKind` — `read | edit | delete | move | search | execute | think | fetch |
  switch_mode | other` (open).
- `StopReason` — as above (open).
- `PermissionOptionKind` — `allow_once | allow_always | reject_once | reject_always` (open),
  and in v2 the *subject* is typed too: `RequestPermissionSubject = tool_call | command | other`.

**Two extension conventions strictly better than `x-`:**

1. **Open-enum widening.** Every open enum documents: *"Values beginning with `_` are
   reserved for implementation-specific extensions. Unknown values that do not begin with
   `_` are reserved for future ACP variants."* Some carry a receiver obligation too:
   *"Receivers that do not understand this content type should **preserve the raw payload**
   when storing, replaying, proxying, or forwarding tool call output, and otherwise ignore
   it or display it generically"* (`$defs.ToolCallContent`).
2. **`x-deserialize-default-on-error`.** **[NEW in pass 2.]** This annotation appears
   **213 times in v2** and **242 times in v1** (`grep -c`). It is a per-field instruction:
   an unparseable or unknown value falls back to the field default rather than failing the
   whole message. Combined with (1) this gives *forward compatibility at the value level*
   without a registry — an old client meets a new enum member, keeps the raw payload,
   defaults the typed view, and keeps going.

**Version story:** `ProtocolVersion` is a **uint16 integer** — *"only bumped for breaking
changes. Non-breaking changes should be introduced via capabilities"*
(`schema/v2/schema.json`, `$defs.ProtocolVersion`).

**Reconciliation:** Goose depends on `agent-client-protocol = "1.0"` and
`agent-client-protocol-schema = "1.1"`
(`/home/bud/ditto/gaia-ai-runtime/goose/Cargo.toml:29-31`) — i.e. **v1**. Anything PACT
designs against Zed ACP today lands on v1 in the runtime, and v1 *has* the `fs/*` and
`terminal/*` client methods that v2 removed. A PACT↔Goose session surface built on v1 will
need rework when Goose moves to v2, and the rework is not cosmetic — it is the direction of
control for filesystem and terminal access.

**Does NOT cover:** any definition surface whatsoever. No manifest, no card, no discovery
document. It assumes the agent already exists as a launchable process.

---

## 4. AGNTCY OASF — Open Agentic Schema Framework

### 4.1 What it standardises

A **content-addressed catalogue record** for "agentic AI content". Schema version in-tree
`1.2.0-dev` (`schema/version.json`). Authoring format is an OCSF-style metaschema
(caption/description/extends/attributes/requirement) under `schema/`; wire format is
protobuf under `proto/agntcy/oasf/types/v1/`.

`Record` (`proto/agntcy/oasf/types/v1/record.proto:21-57`), read in full pass 2:
`annotations` (map<string,**string**>, field 1; *"Annotations with `agntcy.` prefix are
reserved for system use"*, `:23`), `name` (2), `version` (3), `schema_version` (4),
`description` (5), `authors[]` (6), `created_at` RFC 3339 (7), `locators[]` (8), `skills[]`
(9), `domains[]` (10), `modules[]` (11). **That is the entire record — 11 fields.**
The JSON-schema view (`schema/objects/record.json`) marks name/version/schema_version/
description/authors/created_at/skills as required.

`Skill` and `Domain` are `{annotations, name, id:uint32}` drawn from a **closed, uid-keyed
taxonomy** shipped in-tree: 19 skill categories (`schema/skills/`) and 25 domains
(`schema/domains/`).

`Locator` (`schema/objects/locator.json`): `type` ∈ {unspecified, helm_chart,
container_image, package, source_code, binary, url}, `urls[]`, `annotations`.

### 4.2 Extension mechanism — `Module`, and it is genuinely open

`Module` (`proto/agntcy/oasf/types/v1/module.proto`): `annotations`, `name`, `id:uint32`,
**`data: google.protobuf.Struct`**, **`artifact: Descriptor`**. `Descriptor`
(`descriptor.proto`) is OCI-shaped: `media_type`, `artifact_type`, `size`, `digest`,
`urls[]`, inline `data: bytes`, inline `json: Struct`.

**The complete module registry, re-enumerated pass 2** (`find schema/modules -type f`):

| Path | uid | Payload object |
|---|---|---|
| `modules/core/core.json` | — | (namespace) |
| `modules/core/observability.json` | 1 | `observability_data` |
| `modules/core/evaluation.json` | 2 | `evaluation_data` |
| `modules/core/language_model/language_model.json` | 3 | `language_model_data` |
| `modules/core/language_model/prompt.json` | 1 | `language_model_prompt_data` |
| **`modules/core/language_model/agentskills.json`** | **2** | **`agentskills_data`** |
| `modules/integration/integration.json` | — | (namespace) |
| `modules/integration/mcp.json` | 2 | `mcp_data` |
| `modules/integration/a2a.json` | 3 | `a2a_data` |
| **`modules/integration/agentspec.json`** | **4** | **`agentspec_data`** |
| `modules/integration/acp_manifest.json` | — | `acp_manifest_data` (deprecated ACP) |

The two bolded rows are **new relative to pass 1** and are the most important OASF findings
in this report.

**The inline-payload deprecation is systemic.** `a2a_data.card_data` and
`mcp_data.mcp_data` both carry *"Inline … payload is deprecated, please use
module.artifact instead"* since 1.0.0 (`schema/objects/a2a_data.json:11-14`,
`schema/objects/mcp_data.json:45-49`). **OASF is converging on "the module points at an
opaque, digest-addressed artifact."** That is a first-class hook for PACT.

Extension *names/uids* are tracked in a flat registry file, `schema/extensions.md`, which
currently contains exactly one row (`dev`, uid 999). Collision avoidance is by manual PR.

### 4.3 The `agentspec` module — OASF's own concession, and PACT's template

**[NEW in pass 2. This is the single most useful finding for PACT's registry story.]**

`schema/modules/integration/agentspec.json` exists for Oracle's Open Agent Spec, and its
payload (`schema/objects/agentspec_data.json`) is:

| Attribute | Requirement | Description (verbatim) |
|---|---|---|
| `config` | required | *"Location of the Agent Spec config. E.g. path to config, github repo url etc."* |
| `deployment_options` | required | *"List of possible configuration to instantiate or consume the agent."* |
| `runtime_deps` | optional | *"List of locators for the non-serializable objects the Agent Spec config depends on (e.g. tool implementations)."* |
| `env_vars` | optional | |

`agentspec_deployment_option` (`schema/objects/agentspec_deployment_option.json`) =
`{name?, protocol✔ (→ `agentspec_communication_protocol`, with A2A and Responses-API
variants), runtime_framework✔}`.

Three consequences for PACT:

1. **This is the exact shape of the PACT OASF module.** A `dev.pact.spec` module carrying
   `{config: locator-to-tree-or-OCI-artifact, deployment_options: [{protocol, runtime_framework}],
   env_vars}` is a *conforming instance of an already-accepted pattern*, not a novel
   extension. Cost of adoption is near zero.
2. **`runtime_deps` is the loss surface made explicit by the standard itself.** Oracle's
   spec needs it because tool implementations are Python objects that do not serialise.
   **Under D14 (no-code ceiling) and D15 (translate or nothing), a conforming PACT agent's
   `runtime_deps` list is EMPTY** — every tool is declarative. That empty list is a
   *machine-checkable differentiator*: "this agent is fully self-describing" is now an
   assertion an external registry can verify. PACT should emit `runtime_deps` explicitly
   and require it to be empty in `strict` mode, with any entry forced through the loss report.
3. It confirms OASF has no ambition to model an agent's interior. It models *where the
   interior lives*.

### 4.4 The `agentskills` module — a validation-verdict shape PACT should mirror

**[NEW in pass 2.]** `schema/modules/core/language_model/agentskills.json` (uid 2) points at
the **Agent Skills / `SKILL.md`** standard (`https://agentskills.io/specification/`).
`agentskills_data` carries `skill_manifest`, `source_locator`, `source_revision`,
`skill_file` (*"Path to the skill definition file, typically SKILL.md"*), `capabilities`,
`artifacts`, `validation`, `standard_version`.

`agentskills_manifest` = `{name✔, description✔, version?, license?, compatibility?,
allowed_tools?, frontmatter_metadata?}` — *"Normalized metadata extracted from a SKILL.md
file."*

`agentskills_validation` (`schema/objects/agentskills_validation.json`) is the important
one:

| Field | Req |
|---|---|
| `validation_status` | ✔ |
| `validator` | ✔ (*"Validator implementation used for the checks (for example, skills-ref)"*) |
| `validated_at` | ✔ |
| `skill_md_valid` | ✔ |
| `artifacts_valid` | |
| `validation_errors` | |
| `validation_warnings` | |
| `validation_report_url` | |

**This is the closest thing in the entire corpus to a PACT Conformance / Portability
Report**: a verdict, *with the identity of the verifier and the time of verification*,
attached to a catalogue entry, plus a pointer to the full report. It is not a *contract*
(no thresholds, no required-to-pass), but it is a **verdict-with-provenance record shape**,
and PACT's `ConformanceReport` and `PortabilityReport` should be structurally isomorphic to
it so they can be published as OASF modules without invention.

**[CORRECTION — pass 1]** Pass 1's loss table said the loss report itself has "NO HOME…
The honesty artefact is unrepresentable in every protocol PACT exports to." That was
written before `agentskills_validation` was found. The correct statement is narrower:
*the verdict has a shape precedent; the **contract that the verdict is measured against**
still has no home anywhere.* Section 12 is corrected accordingly.

### 4.5 Version story, and where lineage actually went (open question 4 CLOSED)

`schema_version` is a record field; proto packages are `v1alpha0`, `v1alpha1`, `v1alpha2`,
`v1`. `v1alpha1`/`v1alpha0` had a `signature.proto`; **`v1` does not** — signing moved out
of the record. `v1alpha2/record.proto:21-25` documented a **4 MB max record size** and a
`previous_record_cid` lineage pointer at field 99. **`v1/record.proto` has neither** —
verified by reading all 57 lines pass 2.

`v1/record.proto:16-18` says records are *"packaged and distributed as OCI Artifacts
conforming to the Record Manifest specification"*. That specification is not in
`agntcy-oasf`; **it is implemented in `agntcy-dir`**, which pass 1 did not audit:

`agntcy-dir/server/store/oci/constants.go:10-51` is labelled *"THE SOURCE OF TRUTH for
field names"* and defines the OCI manifest annotation schema:

| Constant | Key |
|---|---|
| type marker | `org.agntcy.dir/type` = `"record"` (`annotations.go:19`) |
| `ManifestKeyName` | `org.agntcy.dir/name` |
| `ManifestKeyVersion` | `org.agntcy.dir/version` |
| `ManifestKeyOASFVersion` | `org.agntcy.dir/oasf-version` |
| `ManifestKeyCid` | `org.agntcy.dir/cid` |
| `ManifestKeySchemaVersion` | `org.agntcy.dir/schema-version` |
| `ManifestKeyCreatedAt` | `org.agntcy.dir/created-at` |
| **`ManifestKeyPreviousCid`** | **`org.agntcy.dir/previous-cid`** |
| `ManifestKeyCustomPrefix` | `org.agntcy.dir/custom.` |
| `FallbackSchemaVersion` | `"0.7.0"` |

and OCI artifact types at `server/store/oci/types.go:14-20`:
`application/vnd.agntcy.dir.sign.publickey.v1+pem`,
`application/vnd.agntcy.dir.sign.signature.v1+json`,
`application/vnd.agntcy.dir.referrer.v1+json`. Signatures and public keys are **OCI
referrers**, not record fields — confirming where signing went.

**But lineage is still lost for OASF v1 records, and worse than pass 1 said.** The
version-agnostic adapter hard-codes it:

```go
// agntcy-dir/api/core/adapters/oasf_v1.go:92-94
func (v *v1Adapter) GetPreviousRecordCid() string {
	return ""
}
```

versus `oasf_v1alpha1.go:45-46` and `oasf_v1alpha2.go:45-46`, which both return
`v.record.GetPreviousRecordCid()`. So `extractManifestAnnotations`
(`server/store/oci/types.go`, via `annotations.go:50-53`) will **never** emit
`org.agntcy.dir/previous-cid` for a v1 record. The reference registry implementation
*cannot* record lineage for the current schema version.

**Workaround, and it is clean:** `annotations.go:56-60` copies every record annotation into
`org.agntcy.dir/custom.<key>`, and `record.proto:23` reserves only the `agntcy.` prefix.
So PACT sets record annotation `dev.pact/previous-digest`, which lands as OCI manifest
annotation `org.agntcy.dir/custom.dev.pact/previous-digest` and is queryable. This restores
T6/learning lineage through OASF at zero spec cost.

### 4.6 The evaluation module — a published *result*, never a *specification*

The most important negative finding about OASF; it touches PACT's T2 directly.

- `evaluation_data` = `overall_rating?`, `overall_scores?`, `referred_evaluations`✔.
- `referred_evaluation` = `datasets?`, `publisher`✔, `created_at`✔, `evaluation_report?`,
  with `at_least_one: [datasets, evaluation_report]`.
- `evaluation_report` = `overall_scores?` + `metrics?`, `at_least_one`.
- `overall_scores` = exactly three optional numbers: `quality_score`, `cost_score`,
  `security_score`.
- `metric` = `name`✔, `type`✔ (counter/gauge/histogram), `unit_of_measurement`✔ (UCUM),
  `url?`, `data_points`✔.
- `evaluation_dataset` = `url`✔, `name`✔, `version?`, `metadata?`.

**OASF can say "this agent scored 0.83 on dataset X, published by Y on date Z". It cannot
say "this agent MUST score ≥ 0.80 on `deepeval:answer_relevancy` over these 40 cases before
it may be bound."** No threshold, no assertion, no pass/fail, no case, no rubric, no judge.
PACT's entire Quality Contract has no home here. (Note the asymmetry with
`agentskills_validation` §4.4, which *does* have `validation_status` — evaluation gets
scores, skill-file conformance gets a verdict. There is no verdict for evaluation.)

### 4.7 The `language_model` module is a binding, not a requirement

`schema/objects/language_model.json`: `{model✔, provider✔, api_base✔, env_vars?}`.
`language_model_data.models[]` is a list of these. This is a **concrete deployment
binding** — the resolved end of PACT's model story, with nothing on the requirement side.
`schema/objects/prompt.json` = `{name✔, description✔, command✔}` — a slash-command shape,
not a system instruction.

### 4.8 What OASF does NOT cover

- No instructions, no loop, no topology, no memory, no handoffs.
- No capability *predicates* — `Skill`/`Domain` are enumerated tags from a fixed uid
  taxonomy. `reasoning >= strong && MMLU > 80 && context >= 128k` (O3.1) is inexpressible.
- No SLOs. `overall_scores.cost_score` is a scalar rating, not a budget.
- `annotations` is `map<string,string>` — **string values only**, at record, skill, domain
  and module level. Structured PACT data cannot ride in annotations; it must use
  `Module.data` or `Module.artifact`.
- The one place agent I/O schemas existed — `acp_agent.input`/`.output` as
  `openapi_schema_object` (`schema/objects/acp.json:16-25`) — is deprecated.
- **Reconciliation:** `00-THESIS.md:146` treats "OSSA / OASF (AGNTCY)" as one row. **They
  are two unrelated specifications.** See §15.1.

---

## 5. AG-UI

### 5.1 What it standardises

A **streaming event protocol between an agent and a user-facing app**. Transport-agnostic
(SSE/WS/binary). The unit is `RunAgentInput → Observable<BaseEvent>`.

`EventType` — 31 live members + 5 deprecated `THINKING_*` aliases
(`sdks/typescript/packages/core/src/events.ts:12-61`):
`TEXT_MESSAGE_{START,CONTENT,END,CHUNK}`, `TOOL_CALL_{START,ARGS,END,CHUNK,RESULT}`,
`REASONING_{START,END,MESSAGE_START,MESSAGE_CONTENT,MESSAGE_END,MESSAGE_CHUNK,ENCRYPTED_VALUE}`,
`STATE_SNAPSHOT`, `STATE_DELTA` (JSON Patch RFC 6902), `MESSAGES_SNAPSHOT`,
`ACTIVITY_{SNAPSHOT,DELTA}`, `RUN_{STARTED,FINISHED,ERROR}`, `STEP_{STARTED,FINISHED}`,
`RAW`, `CUSTOM`.

`RunAgentInput` (`types.ts:209-219`): `threadId`, `runId`, `parentRunId?`, `state`,
`messages[]`, **`tools[]`**, `context[]`, `forwardedProps`, `resume[]`.

**Modality coverage is the best in the corpus.** `types.ts:40-72,104-107,228-231`:
`InputContentSourceSchema` is a discriminated union (data-URI vs URL) shared by
`ImageInputContentSchema`, `AudioInputContentSchema`, **`VideoInputContentSchema`**, and
`DocumentInputContentSchema`. **AG-UI is the only protocol here with first-class video.**
Verified pass 2.

### 5.2 The inversion that matters

`RunAgentInput.tools` flows **client → agent**: the *frontend* declares tools to the agent
(`ToolSchema = {name, description, parameters: JSON Schema, metadata?}`, `types.ts:186-191`).
This is generative-UI / HITL, the opposite direction from MCP. `InterruptSchema`
(`types.ts:193-201`) with `responseSchema` and `expiresAt`, plus `ResumeEntrySchema`
(`types.ts:203-207`), is a clean **typed HITL interrupt with an expiry** — and unlike MCP
elicitation (§1.5) its `responseSchema` is unrestricted JSON Schema. Worth copying into
PACT's loop IR verbatim.

### 5.3 Extension mechanism / version story

`BaseEventSchema` is a Zod `.passthrough()` object (`events.ts:63-69`) — unknown fields
survive, but there is **no key-naming convention**, no reserved prefix, no registry. `RAW`
and `CUSTOM` are the sanctioned escapes. There is **no protocol version field on
`BaseEvent`**; versioning is npm semver, and `@ag-ui/core` is at **`0.0.57`**
(`sdks/typescript/packages/core/package.json:4`) — verified pass 2. Deprecations are JSDoc
`@deprecated` with "Will be removed in 1.0.0".

**PACT must not take a normative dependency on AG-UI.** A `0.0.x` package with no wire
version field and pre-1.0 removal notices cannot be a stable projection target. Consume its
*vocabulary* (event taxonomy, interrupt shape, modality union); do not bind to its schema.

### 5.4 What AG-UI does NOT cover

Everything about definition. No card, no manifest, no discovery, no tool registry, no
model, no eval. Its own docs place it as the third leg beside MCP and A2A
(`docs/agentic-protocols.mdx:16-21`).

---

## 6. agents.md

**There is no schema and there is no spec.** The repo is a Next.js marketing site:
`ls` returns `components/`, `pages/`, `styles/`, `next.config.ts`, and one `AGENTS.md`.
The only normative-ish statements are React string literals:

- *"Are there required fields? — No. AGENTS.md is just standard Markdown. Use any headings
  you like; the agent simply parses the text you provide."* (`components/FAQSection.tsx:12-15`)
- *"What if instructions conflict? — **The closest AGENTS.md to the edited file wins;
  explicit user chat prompts override everything.**"* (`components/FAQSection.tsx:16-19`)
- *"Will the agent run testing commands found in AGENTS.md automatically? — Yes—if you list
  them."* (`components/FAQSection.tsx:20-23`)
- Nested files allowed in monorepos (`components/HowToUseSection.tsx:35`).

No version field, no front-matter, no extension mechanism. Last commit 2026-03-12.

**Relevance to PACT is real but narrow.** The precedence rule — *closest wins, user prompt
overrides all* — is exactly the semantics PACT's Expansion Rule needs for `instructions.md`
at nested levels of a workspace tree, and it is the only prior art for it that has broad
tool adoption. PACT should be able to **emit** `AGENTS.md` (a rendered projection of
resolved instructions) so a PACT workspace is legible to Claude Code / Codex / Cursor with
zero adapter. It must never be an *input* format: there is nothing machine-readable to read.

---

## 7. OpenTelemetry `gen_ai` semantic conventions

### 7.1 They moved out of this repo

`docs/gen-ai/README.md:6-11`: *"GenAI semantic conventions have moved to the OpenTelemetry
GenAI semantic conventions repository (`semantic-conventions-genai`). This page has moved
and is no longer maintained in this repository."* Confirmed at `CHANGELOG.md:49-53`:
`model/gen-ai/`, `model/openai/`, `model/mcp/` deprecated here.

`ls model/gen-ai/` → **`deprecated` only**. `ls model/mcp/` → **`deprecated` only**. All
eleven `docs/gen-ai/*.md` files are 11-line stubs. `semantic-conventions-genai` is **not in
the corpus** (open question 1 remains open).

**Version correction.** `model/manifest.yaml:1` declares
`schema_url: https://opentelemetry.io/schemas/1.44.0-unreleased`, not v1.43.0.
**[CORRECTION — pass 1]**, minor.

**Stability warning that pass 1 understated.** Of the 60 `gen_ai.*` attributes,
**55 carry `stability: development`** and every one carries `deprecated: reason:
uncategorized` with a "moved to…" note (e.g. `registry-deprecated.yaml:966-974` for
`gen_ai.output.type`). In OTel's own terms these are *not stable conventions*. **PACT must
not pin any `gen_ai.*` attribute name as normative in `pact.dev/v1`;** it must reference
the convention *set* by version and resolve names through an indirection table.

### 7.2 The attribute registry (60 `gen_ai.*` attributes)

`model/gen-ai/deprecated/registry-deprecated.yaml` (count verified pass 2:
`grep -c "      - id: gen_ai\."` → 60). The ones that matter to PACT:

| Attribute | Line | Note |
|---|---|---|
| `gen_ai.operation.name` | 914-961 | closed enum: `chat`, `generate_content`, `text_completion`, `embeddings`, `retrieval`, **`create_agent`**, **`invoke_agent`**, **`execute_tool`**, **`invoke_workflow`** |
| `gen_ai.agent.{id,name,description,version}` | 688-735 | |
| `gen_ai.workflow.name` | 1295 | *"name of the first chain in LangChain OR name of the crew in CrewAI"* |
| `gen_ai.conversation.id` | 676 | |
| `gen_ai.tool.{name,call.id,description,type,call.arguments,call.result}` | 736-845 | `tool.type` ∈ `function` \| `extension` \| `datastore` (773-790) |
| `gen_ai.tool.definitions` | 846-896 | `type: any`; MUST follow the Tool Definitions JSON Schema; `opt_in` |
| `gen_ai.system_instructions` | 1069 | `opt_in` |
| `gen_ai.input.messages` / `gen_ai.output.messages` | 1121 / 1184 | `opt_in` |
| `gen_ai.output.type` | 966-992 | `text` \| `json` \| `image` \| `speech` — **no video, no computer-use**; verified pass 2 |
| `gen_ai.usage.{input,output}_tokens`, `usage.cache_read.input_tokens`, `usage.cache_creation.input_tokens`, `usage.reasoning.output_tokens` | 577-647 | |
| `gen_ai.response.time_to_first_chunk` | 562 | |
| **`gen_ai.evaluation.{name,score.value,score.label,explanation}`** | 1230, 1242, 1254, 1271 | §7.4 |
| `gen_ai.prompt.name` | 1283 | e.g. `"analyze-code"` |
| `gen_ai.data_source.id`, `gen_ai.retrieval.{documents,query.text}` | 897, 1019-1068 | |

A source comment at `registry-deprecated.yaml:993-996` acknowledges the modality gap:
*"we might need to record requested and actual output types on the same span/event at some
point… we may also need to record an array of types."*

### 7.3 Spans

`model/gen-ai/deprecated/spans-deprecated.yaml`:

| Span group | Line | Kind | Span name |
|---|---|---|---|
| `span.gen_ai.create_agent.client` | 370 | CLIENT | `create_agent {gen_ai.agent.name}` |
| `span.gen_ai.invoke_agent.client` | 531 | CLIENT | `invoke_agent {…}` — *remote* agent |
| `span.gen_ai.invoke_agent.internal` | 566 | INTERNAL | same name — *in-process* agent |
| `span.gen_ai.execute_tool.internal` | 597 | INTERNAL | `execute_tool {gen_ai.tool.name}` |
| `span.gen_ai.invoke_workflow.internal` | 703 | INTERNAL | `invoke_workflow {gen_ai.workflow.name}` |
| `span.gen_ai.inference.client` | 135 | CLIENT | |
| `span.gen_ai.retrieval.client` / `.embeddings.client` | 331 / 291 | CLIENT | |

`invoke_workflow` carries an explicit don't-double-report rule: emit it only when the
instrumentation can reliably distinguish a workflow from an agent; ADK-style workflow-agents
SHOULD NOT emit it, CrewAI crews SHOULD (`spans-deprecated.yaml:723-731`).

**This is directly exploitable by PACT.** PACT knows *statically* whether a node is a team
or an agent, because the topology is declared. Framework instrumentations have to guess.
PACT's harness lowering can therefore emit `invoke_workflow` correctly where every
framework's own instrumentation cannot — a concrete, demonstrable observability advantage
of owning the loop (D12).

### 7.4 The evaluation event

`event.gen_ai.evaluation.result` (`model/gen-ai/deprecated/events-deprecated.yaml:376-415`):
`gen_ai.evaluation.name`✔, `score.value?` (double), `score.label?` (low-cardinality string,
examples include `"pass"`/`"fail"`), `explanation?`, `gen_ai.response.id?`, `error.type?`.
*"SHOULD be parented to GenAI operation span being evaluated when possible."*

**The only place in the whole corpus where an eval result has a standard shape.** It is a
*result* event with no threshold and no verdict-vs-baseline. D11's
`PORTABILITY: FAIL — answer_relevancy 0.61 < 0.80` maps to `name` + `score.value` +
`score.label:"fail"` + `explanation` — but **the `0.80` has no attribute.** §12.

### 7.5 Metrics

`model/gen-ai/deprecated/metrics-deprecated.yaml`: `gen_ai.client.token.usage` (54),
`gen_ai.client.operation.duration` (74), `gen_ai.client.operation.time_to_first_chunk` (99),
`gen_ai.client.operation.time_per_output_chunk` (118), `gen_ai.server.request.duration` (138),
`gen_ai.server.time_per_output_token` (155), `gen_ai.server.time_to_first_token` (172).

**PACT's TTFT/TPOT SLOs (O4.2) map exactly onto the last three.** There is no cost metric
and no E2E-latency metric distinct from `operation.duration`.

### 7.6 MCP conventions (also moved)

`model/mcp/deprecated/registry-deprecated.yaml`: exactly four attributes —
`mcp.method.name` (13), `mcp.session.id` (151), `mcp.resource.uri` (163),
`mcp.protocol.version` (178); spans `span.mcp.client` (21) / `span.mcp.server` (74); four
metrics for client/server operation and session duration. The MCP draft spec points at
these conventions by URL when reserving `traceparent` (§1.2), so the two specs are already
coupled.

### 7.7 What OTel does NOT cover

It is an *observation* schema. No definition, no thresholds, no contract, no policy, no
capability requirement. Modality vocabulary is narrower than D16 requires.

---

## 8. CloudEvents

**v1.0**, stable and frozen; `cloudevents/v2.md:5-9` is a "consideration list" with *"no
guarantee as to when, or if, a v2 might happen."*

REQUIRED context attributes: `id`, `source` (URI-reference), `specversion` (`"1.0"`),
`type` (`cloudevents/spec.md:281-360`). Optional: `datacontenttype`, `dataschema`,
`subject`, `time`.

**Attribute-name constraints are severe** (`cloudevents/spec.md:198-207`, verified pass 2):
lower-case `[a-z0-9]` ASCII only, SHOULD start with a letter, **SHOULD NOT exceed 20
characters**, MUST NOT be `data`. No dots, no dashes, no underscores. Type system
(`spec.md:211-247`): `Boolean | Integer(int32) | String | Binary | URI | URI-reference |
Timestamp`.

Extension mechanism: additional context attributes under the same naming and type rules,
with a documented-extensions list (`spec.md:487-515`). Current extensions
(`cloudevents/extensions/`): `authcontext`, `bam`, `correlation`, `data-classification`,
`dataref`, `deprecation`, `distributed-tracing`, `expirytime`, `opcua`, `partitioning`,
`recordedtime`, `sampledrate`, `sequence`, `severity`, `verifiability`.

**Two extensions are directly load-bearing for PACT's learning governance (T6/D23):**

- **`verifiability`** — DSSE signing of individual events, protocol- and format-agnostic,
  giving *authenticity and integrity* without trusting intermediaries; explicitly
  backwards-compatible (*"Conformant producers MAY sign events; conformant consumers MAY
  verify signatures"*) and explicitly **avoids cryptographic agility** in favour of
  simplicity (`cloudevents/extensions/verifiability.md:1-60`). This is the correct wire
  form for PACT's "learning candidate accepted, signed by X" events.
- **`authcontext`** — `authtype` enum `{app_user, user, service_account, api_key, system,
  unauthenticated, unknown}` plus principal identity, *"purely informational and not
  intended to secure CloudEvents"* (`cloudevents/extensions/authcontext.md:24-40`). This is
  the right shape for D23's "who approved this promotion" field.

**Does NOT cover:** anything about agents. It is an envelope.

**Where PACT should use it:** the *feedback/learning* event stream — trace promotion
(AC-4.4), learning-candidate accept/reject (AC-5.4/5.5), portability verdicts. The runtime
gap analysis already names "feedback events" as missing. CloudEvents is the correct
envelope and costs PACT nothing, because the 20-char attribute limit binds only *context
attributes*; PACT payload rides in `data` under a `dataschema` URI.

---

## 9. Serverless Workflow (CNCF)

**DSL 1.0.3** (`schema/workflow.yaml:1`, `$id: …/schemas/1.0.3/workflow.yaml`), JSON Schema
draft 2020-12. Root: `document`✔, `input`, `use`, `do`✔, `timeout`, `output`, `schedule`,
`evaluate`.

`document`✔ = `dsl`✔ (semver), `namespace`✔, `name`✔, `version`✔ (semver), `title`,
`summary` (Markdown), `tags`, `metadata` (`schema/workflow.yaml:7-51`).
`use` = `authentications`, `errors`, `extensions`, `functions`, `retries`, `secrets`,
`timeouts`, `catalogs`.

**Closed task set (12):** `call`, `do`, `fork`, `emit`, `for`, `listen`, `raise`, `run`,
`set`, `switch`, `try`, `wait`.

**Extension mechanism — the best structural one in the corpus.** `$defs.extension` =
`extend`✔ (which task kind, or `all`) + `when` (runtime expression) + `before` (taskList) +
`after` (taskList). Aspect-oriented composition over a closed task set: an extension can
**wrap** but never **invent** a task kind. That is exactly the property that keeps a spec
implementable (thesis R8), and it is strictly stronger than "add a new field."

### 9.1 It already speaks A2A and MCP — and both bindings are already stale

`schema/workflow.yaml:454-492` — `call: a2a` with `with.agentCard` (externalResource),
`with.server` (endpoint), `with.method` (enum), `with.parameters`.
`schema/workflow.yaml:493-560` — `call: mcp` with `with.protocolVersion`, `with.method`
(enum), `with.parameters`, `with.timeout`, `with.transport.{http,stdio}`.

Verified pass 2, both stale:

- The A2A method enum (`:482`) is the **v0.3 JSON-RPC method names**:
  `message/send`, `message/stream`, `tasks/get`, `tasks/list`, `tasks/cancel`,
  `tasks/resubscribe`, `tasks/pushNotificationConfig/{set,get,list,delete}`,
  `agent/getAuthenticatedExtendedCard`. A2A **v1.0** renamed the surface (`SendMessage`,
  `SendStreamingMessage`, …) and moved to `supportedInterfaces` + protocol bindings.
- MCP `protocolVersion` **defaults to `2025-06-18`** (`:512`) — two revisions behind, and
  predating the `2026-07-28` handshake removal entirely. The MCP method enum
  (`tools/list`, `tools/call`, `prompts/*`, `resources/*`) also omits `server/discover`.

This is concrete evidence for thesis R2 (adapter rot) applied to **specs**, not adapters.
OASF shows the same disease independently: `a2a_data.card_data` references the A2A proto at
**tag `v0.3.0`** and `mcp_data.mcp_data` references MCP server schema **`2025-09-29`**
(`agntcy-oasf/schema/objects/a2a_data.json`, `mcp_data.json`).

### 9.2 What it does NOT cover

No agent, no model, no instructions, no tool-set, no memory, no eval, no capability, no
non-deterministic control flow. It is a deterministic orchestrator that can *call* agents.

### 9.3 But it has the only proven declarative "call something external" vocabulary

`call: http` / `call: openapi` / `call: grpc` / `call: asyncapi` / `call: a2a` /
`call: mcp`, plus `run: {container|script|shell|workflow}` with
image/command/ports/volumes/env. For D14 (a non-technical author adds a custom tool in
YAML), **this closed set is the right model for PACT's no-code tool kinds** — it is the only
place in the corpus where "invoke an external thing" is fully declarative and complete.

---

## 10. OAM — Open Application Model

**Dormant.** Latest release v0.3.0; last repo commit **2024-12-24**; working draft v0.3.1
(`README.md:38`). Model: `Application` → `components[]` → `{name, type, properties,
traits[], scopes{}}` (`7.application.md:29-45`), with `ComponentDefinition`
(`3.component_model.md:19-32`), `TraitDefinition`, `WorkloadDefinition`, `ScopeDefinition`.

Three patterns are directly reusable and I recommend all three:

1. **Definition-registry indirection.** `component.type` is a *name* resolved against a
   registered `ComponentDefinition` whose `schematic` "expose[s] a JSON schema or equivalent
   parameter list" (`3.component_model.md:47-51`). This is precisely PACT's G-5 (tools,
   skills, memory, retrievers, guardrails, hooks, channels, schedules, sandboxes are all
   Resources under one registration/scoping model) with a shipped prior art.
2. **Traits as discretionary operational overlays** applied by a *different role* than the
   one who authored the component (`6.traits.md:3-7`). PACT's policies/SLOs/guardrails are
   traits in this sense — authored by an ops persona, attached without touching the agent.
   This is the cleanest available answer to "how does a domain expert author an agent while
   an ops team owns its budget?"
3. **`conflictsWith`** on `TraitDefinition` (`6.traits.md:33`) — a *declared* incompatibility
   between overlays, checked before deployment. **PACT has no analogue and needs one**
   (e.g. `autonomy: full` conflicts with `approval-gate: every-tool-call`;
   `constrained_decoding: grammar` conflicts with a hosted-API substrate).

**Does NOT cover:** anything AI. No agent, no model, no eval. And it is unmaintained.

---

## 11. Boundary case — Oracle Open Agent Spec (in `protocols/`, not a protocol)

Version `26.2.0.dev7` (`VERSION`). Included here only because it lives in the protocols
directory and because deliverable (d) asks whether any corpus artifact could be PACT's wire
format. The full prior-art autopsy belongs to another stream; three findings are
protocols-relevant.

**11.1 — It is the only corpus artifact with a declarative *curated MCP exposure set*.**
`pyagentspec/src/pyagentspec/mcp/tools.py:76-104`:

```python
class MCPToolBox(ToolBox):
    client_transport: ClientTransport
    retry_policy: Optional[RetryPolicy] = None
    tool_filter: Optional[List[Union[MCPToolSpec, str]]] = None
```

with the docstring rules: a `str` entry asserts a tool of that name is expected from the
server; an `MCPToolSpec` entry *"validate[s] the presence and signature of the specified
tool in the MCP Server"*, may override its description, may pin input names/types, and may
override the confirmation flag (`tools.py:91-104`).

This is exactly PACT's "tool exposure set is a Strategy artefact" (thesis §7.3 item 4) made
declarative, **offline-checkable**, and pinnable. Pass 1 listed tool exposure/curation as
having "NO HOME"; it has no home *in the protocols*, but it has a working implementation in
a competing spec. PACT must have it, and must not invent a worse version.

**11.2 — Feature-inferred minimum version.** Every component implements
`_infer_min_agentspec_version_from_configuration()` and
`_versioned_model_fields_to_exclude(version)` (`mcp/tools.py:37-49,58-73,106-118`;
`versioning.py:27-52`). The document does **not** declare a version the author must know;
the library *computes* the minimum version the configuration requires, and serialising to an
older version *excludes* the fields that version cannot express. E.g.
`requires_confirmation` forces ≥ `25.4.2`; `retry_policy` forces ≥ `26.2.0`.

**This is a directly implementable answer to PACT's E-2** ("a new IR feature is additive and
versioned; unknown features are rejected loudly by old adapters, never ignored"). PACT's
canonicaliser should compute `minSpecVersion` from the feature set actually used, and
down-serialisation to an older `pact.dev/vN` should be a **loss-reported** operation rather
than a silent field drop — which is where PACT must diverge from Oracle, whose exclusion is
silent.

**11.3 — OASF already has a module for it (§4.3), and none for PACT.** If PACT wants
registry presence, minting `integration/pact` (uid 5) modelled on `integration/agentspec`
(uid 4) is a ~40-line PR against `agntcy-oasf/schema/modules/integration/` plus one row in
`schema/extensions.md`. That is the entire cost of OASF interop.

---

# PART B — The exact mapping surface

**Report classes.** All tables below use the four classes from the runtime's documented
`ExportReport` (`/home/bud/ditto/gaia-ai-runtime/bud-agentic-runtime/registry-and-portability.md:1181-1192`):
`exact` · `scaffolded` · `lossy` · `unsupported`, plus `runtime_requirements`.
**[CORRECTION — pass 1]** Pass 1 used ad-hoc classes `partial` and `degraded`, which are not
in that vocabulary. PACT must use the runtime's four; §15.2 covers the fact that the
four-class report is *documented but not implemented*.

## 11.1 PACT → **A2A Agent Card**

Target: `a2a-spec/specification/a2a.proto:362-399`. Direction: emit-only for a PACT agent
served over A2A.

| A2A field | PACT source | Class |
|---|---|---|
| `name` | `metadata.name` | exact |
| `description` | `metadata.description` | exact |
| `version` | `metadata.version` | exact |
| `provider.{organization,url}` | `metadata.owner` | exact if owner carries both; else scaffolded |
| `documentationUrl` | `metadata.docs` | exact |
| `iconUrl` | `metadata.icon` | exact |
| `supportedInterfaces[]` | **runtime-supplied**: `{url, protocolBinding, protocolVersion, tenant?}` | scaffolded — PACT declares *bindings offered*; the serving runtime fills `url` |
| `capabilities.streaming` | `contract.interface.streaming` | exact |
| `capabilities.pushNotifications` | runtime capability, not spec | scaffolded |
| `capabilities.extendedAgentCard` | policy: whether the full contract is auth-gated | scaffolded |
| `capabilities.extensions[]` | **PACT's own hook** — see below | exact |
| `securitySchemes` / `securityRequirements` | `policy.auth` | lossy — A2A's set is OpenAPI-3.2-shaped (APIKey/HTTP/OAuth2/OIDC/mTLS); anything else drops |
| `defaultInputModes[]` / `defaultOutputModes[]` | media types derived from `contract.interface.io` content types | **lossy — the JSON Schema is dropped; only the media type survives** |
| `skills[].id` | PACT skill id, or `agent-tool:<name>` / `handoff:<name>` facade ids (existing Bud convention) | exact |
| `skills[].name`, `.description` | skill name/description | exact |
| `skills[].tags[]` | capability tag names | exact |
| `skills[].examples[]` | **eval case inputs, projected** | scaffolded |
| `skills[].inputModes/outputModes` | per-skill content types | lossy (same schema loss) |
| `skills[].securityRequirements[]` | per-skill policy | lossy |
| `signatures[]` | PACT signing pipeline over the JCS canonical form | exact |
| — | topology, loop, variants, evals, SLOs, model requirements, memory | **unsupported** → extension params or loss report |

**The extension hook — normative recommendation.** Emit exactly one A2A extension:

```json
{ "capabilities": { "extensions": [{
    "uri": "https://pact.dev/extensions/contract/v1",
    "description": "PACT contract digest and retrieval",
    "required": false,
    "params": {
      "specVersion": "pact.dev/v1",
      "canonicalDigest": "sha256:…",
      "contractUrl": "https://…/.pact/canonical.json",
      "capabilities": ["vision", "tool_calling:parallel"],
      "io": { "input": {"$ref": "…"}, "output": {"$ref": "…"} },
      "slo": { "ttftP95Ms": 800 },
      "evalVerdict": { "suite": "…", "status": "pass", "at": "…" }
    }
}]}}
```

Justification, all cited: `AgentExtension.params` is `google.protobuf.Struct`
(`a2a.proto:432`) — a **standard** field, so it survives proto round-trip *and* JCS
canonicalisation intact (§2.3). "Data-only extension" is an explicitly sanctioned category
(`docs/topics/extensions.md:26-29`). Third-party URIs need no registration
(`docs/topics/extension-and-binding-governance.md:8-10`), and extension URIs *"are
identifiers, HTTP access is not expected"* (`:38`) — so this is air-gap-safe (D17). Mint a
new URI on any breaking change (`docs/specification.md:1139-1141`).

**Do not** put PACT data in a top-level `metadata` key on the card. See §15.3.

## 11.2 PACT → **MCP tool / prompt / resource**

PACT does not *become* MCP; it **consumes** MCP as the tool edge (NG3) and **exposes** PACT
resources over MCP where a workspace is served to an MCP client.

| MCP object | PACT source | Class |
|---|---|---|
| `Tool.name` | `tools[].name`, namespaced | exact |
| `Tool.title` / `.description` | `tools[].title` / `.description` | exact |
| `Tool.inputSchema` | `tools[].input` | exact where PACT's input has an object root (`schema/draft/schema.ts:1985` requires `type:"object"`); **lossy for non-object roots** |
| `Tool.outputSchema` | `tools[].output` | exact in draft; **restricted to `type:"object"` in 2025-11-25** (`schema/2025-11-25/schema.ts:1277-1285`) |
| `Tool.annotations.{readOnly,destructive,idempotent,openWorld}Hint` | `tools[].effects` | **lossy — MCP defines these as hints; PACT treats them as policy inputs. A PACT policy decision must never be sourced from an MCP hint.** |
| `Tool.icons` | `tools[].icon` | exact |
| `Tool._meta["dev.pact/…"]` | tool-level PACT extras (cost model, SLO, approval class, capability requirement) | exact on the wire, **advisory only** by spec |
| `Prompt.name/.title/.description` | `skills[].name/.title/.description` | exact |
| `Prompt.arguments[]` | skill parameters | **lossy — `PromptArgument extends BaseMetadata` gives `{name,title,description,required}`; no type, no schema** (`schema/2025-11-25/schema.ts:1006-1015`) |
| `Resource.uri/.name/.mimeType/.size` | workspace files: `instructions.md`, `evals/`, `models/catalog.yaml`, `.pact/canonical.json` | exact |
| `ResourceTemplate.uriTemplate` | parameterised resource families | exact |
| `DiscoverResult.instructions` (draft) | workspace-level instructions projection | exact — and PACT should **consume** this from remote servers as an instruction fragment *with provenance* |
| `ElicitRequestFormParams.requestedSchema` | PACT HITL form | **lossy — top-level primitives only, no nesting** (`schema/draft/schema.ts:2787-2789`) |
| `_meta.traceparent` | PACT run trace context | exact (`docs/specification/draft/basic/index.mdx:426-433`) |
| — | agent, model, loop, topology, evals, SLOs, capability predicates, memory, variants | **unsupported** |

**Key-naming compatibility, actionable.** MCP `_meta` keys must be `prefix/name` with
reverse-DNS prefixes, and any prefix whose *second label* is `mcp` or
`modelcontextprotocol` is reserved (`index.mdx:330-344`). `dev.pact/` is legal (second
label `pact`). **A bare `x-` key is not a legal `_meta` key** and would have to be renamed
at the boundary — a silent transform T7 forbids. See D-3.

## 11.3 PACT → **OASF Record**

| OASF field | PACT source | Class |
|---|---|---|
| `name` | `metadata.name` | exact |
| `version` | `metadata.version` | exact |
| `schema_version` | OASF schema version (e.g. `1.2.0`) — **not** `pact.dev/v1` | exact |
| `description` | `metadata.description` | exact |
| `authors[]` | `metadata.owner`, as `name <email>` | exact |
| `created_at` | RFC 3339 build timestamp | exact |
| `annotations{string→string}` | `metadata.labels`; `dev.pact/digest`; **`dev.pact/previous-digest`** (§4.5) | lossy — **string values only**; structured data must not go here |
| `skills[]` | PACT capabilities projected onto the closed OASF uid taxonomy (`schema/skills/`) | **lossy — a PACT capability with no taxonomy entry is dropped or requires an upstream taxonomy PR** |
| `domains[]` | `metadata.domain` → `schema/domains/` | lossy, same reason |
| `locators[]` | `{type: source_code\|container_image\|package, urls:[…]}` for the PACT tree / OCI artifact | exact |
| `modules[] name="dev.pact.spec"` `.data` | **`{config, deployment_options[], runtime_deps[], env_vars}` modelled on `agentspec_data`** (§4.3) | exact |
| `modules[] name="dev.pact.spec"` `.artifact` | `{artifact_type: "application/vnd.pact.canonical.v1+json", media_type, size, digest, urls, json?}` → `canonical.json` | **exact — the load-bearing mapping** |
| `modules[] name="a2a"` | the emitted Agent Card, via `module.artifact` (inline `card_data` deprecated) | exact |
| `modules[] name="mcp"` | required MCP servers → `mcp_data.connections[]` | exact for stdio/http/sse |
| `modules[] name="agentskills"` | PACT skills that are `SKILL.md`-shaped → `agentskills_data.skill_manifest` + `.validation` (§4.4) | exact for the manifest; **lossy for parameterised or non-Markdown skills** |
| `modules[] name="language_model"` | resolved model binding from `pact.lock` (`{model, provider, api_base}`) | exact — but this is the **binding**, not the requirement |
| `modules[] name="evaluation"` | **only post-hoc results**: `referred_evaluations[].evaluation_report.metrics[]` + `overall_scores` | **lossy — thresholds, cases, rubrics, judges, deterministic-first ordering have no field** |
| `modules[] name="observability"` | trace endpoint declaration | lossy |
| — | instructions, loop, topology, variants, capability predicates, SLO targets, budgets | **unsupported** |

**PACT's conformance verdict** should be published as a module whose `data` is structurally
isomorphic to `agentskills_validation` (§4.4): `{status, validator, validated_at,
contract_valid, evals_passed, errors[], warnings[], report_url}`. This is the only
verdict shape in the corpus with an existing precedent.

**Reconciliation:** `00-THESIS.md:146` says the OASF/OSSA mapping "already yields a loss
report." That is true of **OSSA** in the runtime (§15.1); an **OASF** mapping does not exist
in the runtime at all, and its loss profile is different — OASF loses *taxonomy-unmapped
capabilities* and *all eval specification*, whereas OSSA loses *permissions, hooks, and
run-state*.

## 11.4 PACT → **OTel `gen_ai` spans**

Under harness lowering PACT owns the loop, so PACT — not the framework — is the correct
emitter.

| PACT construct | Span / event | Attributes |
|---|---|---|
| Team / topology run | `invoke_workflow` INTERNAL, `invoke_workflow {team}` | `gen_ai.operation.name=invoke_workflow`, `gen_ai.workflow.name`, `error.type?` (`spans-deprecated.yaml:703-746`) |
| Agent run (in-process adapter) | `invoke_agent` INTERNAL | `gen_ai.provider.name`✔, `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.agent.{id,name,description,version}`, `gen_ai.conversation.id` (`:566-596`) |
| Agent run (remote / A2A) | `invoke_agent` CLIENT | same + `server.address`, `server.port` (`:531-565`) |
| Resolver binding an agent to a substrate | `create_agent` CLIENT | `gen_ai.agent.*`, `gen_ai.request.model`, `gen_ai.system_instructions` (opt-in) (`:370-418`) |
| Model call | `gen_ai.inference.client` | request params, `gen_ai.usage.*`, `gen_ai.response.finish_reasons` |
| Tool call | `execute_tool` INTERNAL, `execute_tool {tool}` | `gen_ai.tool.name`✔, `.call.id`, `.description`, `.type` ∈ function/extension/datastore (`:597-649`) |
| **MCP tool call** | `execute_tool` INTERNAL wrapping `span.mcp.client` | propagate `traceparent` into the MCP request `_meta` (`mcp-spec/docs/specification/draft/basic/index.mdx:426-433`); `mcp.method.name`, `mcp.session.id`, `mcp.protocol.version` |
| Retriever / memory read | `retrieval` CLIENT | `gen_ai.data_source.id`, `gen_ai.retrieval.{query.text,documents}` |
| Eval metric result | `gen_ai.evaluation.result` **event**, parented to the evaluated span | `gen_ai.evaluation.name`✔, `.score.value`, `.score.label` ∈ pass/fail, `.explanation` (`events-deprecated.yaml:376-415`) |
| SLO measurement | metrics | `gen_ai.client.operation.time_to_first_chunk`, `…time_per_output_chunk`, `…operation.duration`, `gen_ai.client.token.usage` |
| Exposed tool set (a Strategy artefact) | span attribute | `gen_ai.tool.definitions` (`registry-deprecated.yaml:846-896`) — opt-in, schema-constrained; emitting it makes context-discipline experiments (thesis §7.3 item 4) measurable **from traces alone** |
| Eval **threshold**, variant id, adapter id, lockfile digest, conformance level | no standard attribute | → `dev.pact.*` custom attributes; §12 |

---

# PART C — The loss report

"No home" = I could find no field, attribute, or sanctioned extension slot in any of the
eleven protocols; the value would have to travel in a vendor bag (`AgentExtension.params`,
MCP `_meta`, OASF `Module.data`/`.artifact`, CloudEvents `data`) that consumers are
permitted to ignore.

## 12.1 Contract layer

| PACT field | Nearest thing anywhere | Verdict |
|---|---|---|
| **Agent-level I/O JSON Schema** (`contract.interface.io`) | A2A: media types only; MCP: tool-level only; OASF: `acp_agent.input/output` (**deprecated**); AG-UI `InterruptSchema.responseSchema` (per-interrupt only); bud.dev/v1 `spec.output.schema` (**output only** — `gaia-ai-runtime/bud-agentic-runtime/src/lib.rs:4030-4034`) | **NO HOME.** The single most important loss. Note even the format PACT replaces has no *input* schema. |
| **Capability predicates** (`reasoning >= strong && MMLU > 80 && context >= 128k`) | OASF `skills[]` = closed uid tags; A2A `skills[].tags` = free strings; bud.dev/v1 `AgentCapability {name, description, tags}` (`src/lib.rs:4022-4028`) | **NO HOME.** No protocol *or* predecessor format has a predicate language. Nearest structural analogue anywhere: MCP's `MissingRequiredClientCapabilityError.data.requiredCapabilities` (§1.4) — a *failure* report, not a declaration. |
| **Eval suite** (cases, datasets, metrics, thresholds, rubrics, judge config, deterministic-first ordering) | OASF `evaluation` module carries *results*; OTel carries *result events* | **NO HOME** for the specification. |
| **Pass thresholds / CTS ε** | — | **NO HOME.** `gen_ai.evaluation.score.value` has no companion "required" attribute; `evaluation_report` has no threshold field. |
| **SLO targets** (TTFT/TPOT/E2E/cost/throughput, percentiles) | OTel has the *metrics*; OASF has `overall_scores.cost_score` (a 0-1 rating) | **NO HOME** for the *target*. Measurements have a home. |
| **Budget caps / concurrency limits** | Zed ACP `Cost{amount, currency}` is an actual, not a cap; bud.dev/v1 has `spec.budgets` (`src/lib.rs:3875-3876`) | **NO HOME** in any protocol; regression risk *only at the boundary*, not in PACT itself. |
| **Autonomy level / blast-radius class (D23)** | Zed ACP `PermissionOptionKind` is a runtime prompt; OSSA `spec.autonomy.level` → `{auto, ask}` only (`bud-agentic-runtime/src/portability.rs:1105-1110`) | **NO HOME** for a graded class. |
| **Data-handling / redaction policy** | CloudEvents `data-classification` extension (event-level only) | **NO HOME** at agent level. |
| **Modality: computer-use, video** | A2A `Part.media_type` carries both opaquely; **MCP cannot** (`ContentBlock` unchanged in draft); `gen_ai.output.type` cannot; **AG-UI can** (`VideoInputContentSchema`) | **PARTIAL** — expressible in A2A as an opaque media type and in AG-UI as a typed union. Unrepresentable in MCP and OTel. |

## 12.2 Strategy layer

| PACT field | Nearest thing | Verdict |
|---|---|---|
| **Instructions / system prompt** | `gen_ai.system_instructions` (opt-in trace attribute); MCP draft `DiscoverResult.instructions` (*server*-level); OASF `prompt {name, description, command}` (slash-command shape); AGENTS.md (unstructured prose) | **NO HOME** as a definition field. |
| **Loop program** (ReAct / Plan-Execute / Reflexion / ToT / self-consistency / CodeAct) | Serverless Workflow `do` is deterministic only | **NO HOME.** |
| **Topology** (supervisor, swarm, debate, blackboard, market) | `gen_ai.workflow.name` is a *label*; A2A gives N unrelated cards; OASF `langgraph_config.graph` is an opaque framework blob | **NO HOME.** |
| **Variants** (per-tier strategies) + variant selection | — | **NO HOME.** |
| **Tool *exposure set* and curation** (vs. tools that exist) | `gen_ai.tool.definitions` (trace-only, opt-in). **Outside the protocols: Oracle `MCPToolBox.tool_filter`** (§11.1) | **NO HOME in any protocol**; a working precedent exists in a competing spec, so PACT must not treat this as novel. |
| **Skill exposure and ordering** | OASF `agentskills_data.skill_manifest.allowed_tools` is the inverse (tools a skill may use) | **NO HOME.** |
| **Memory strategy** | — | **NO HOME.** No protocol in the corpus has a memory concept at all. |
| **Retry / verification strategy** | Serverless Workflow `use.retries` (deterministic HTTP retries); Oracle `RetryPolicy` (transport + semantic) | **NO HOME** for *semantic* verification. |
| **Model parameters** | `gen_ai.request.{temperature,top_p,top_k,…}` (trace attributes) | **NO HOME** as a definition field. |
| **Model *requirement*** (as opposed to binding) + catalogue with benchmark provenance | OASF `language_model {model, provider, api_base}` is a **binding** | **NO HOME.** |

## 12.3 Meta layer

| PACT field | Nearest thing | Verdict |
|---|---|---|
| **Fidelity / conformance level (L0–L4)** | — | **NO HOME.** |
| **Adapter capability lattice** (`native\|emulated\|degraded\|unsupported` per feature) | — | **NO HOME.** |
| **Portability Report / `pact.lock`** | — | **NO HOME.** |
| **Learning lineage** (candidate → verdict → promotion → signature) | OASF `v1alpha2.previous_record_cid` **removed in v1**; `agntcy-dir` `org.agntcy.dir/previous-cid` **hard-coded to `""` for v1 records** (`api/core/adapters/oasf_v1.go:92-94`) | **REGRESSED — but recoverable** via `org.agntcy.dir/custom.dev.pact/previous-digest` (§4.5). |
| **Conformance / portability verdict** | **`agentskills_validation`** (§4.4) — status + validator + timestamp + errors + report URL | **HAS A SHAPE PRECEDENT.** *(pass-1 correction)* |
| **The contract the verdict is measured against** | — | **NO HOME.** This, not the verdict, is the irreducible gap. |
| **Loss report itself** (`ExportReport`) | `BudPortableImportReport {source, sourceApiVersion, manifest, lossy: bool, warnings[]}` — in-repo only (`bud-agentic-runtime/src/runner.rs:1199-1212`) | **NO HOME in any protocol.** |

---

# PART D — Could any of these be PACT's wire format?

**Verdict: no — and the failure is structural, not cosmetic.**

PACT must be a strict superset of `bud.dev/v1` (D3). Read from source
(`gaia-ai-runtime/bud-agentic-runtime/src/lib.rs:3839-3879`), `bud.dev/v1` `AgentSpec`
already carries: `instructions`, `model`, `tools` (`ToolPolicy {available, autoApprove,
requireApproval, deny, agents}` at `:3908-3938`), `skills`, `capabilities`, `handoffs`,
`output` (`{schema}`), `guardrails`, `context`, `security`, `budgets`, `permissions`,
`runtime`; plus `BudAgentLoopPolicy {kind, protocol, maxIterations, label, executor}`
(`:3883-3893`). Scored against that bar plus PACT's additions:

| Candidate | Instructions? | Model? | I/O schema? | Evals? | Loop? | Topology? | Verdict |
|---|---|---|---|---|---|---|---|
| A2A AgentCard | no | no | no | no | no | no | **Reject.** Endpoint descriptor. |
| MCP (any object) | server-level only (draft `DiscoverResult.instructions`) | no | tool-level only | no | no | no | **Reject.** Zero agent concept. |
| MCP registry `server.json` | no | no | no | no | no | no | **Reject.** Package manifest; in preview, "data resets may occur". |
| OASF Record | no | binding only | no | results only | no | no | **Reject as document; adopt as envelope** (§13.1). |
| OASF `integration/agentspec` module | no — it is a **locator** | no | no | no | no | no | **Reject as document; it is literally a pointer to one** (§4.3). |
| OSSA `ossa/v0.5.0` | `spec.role` ✔ | `spec.llm` ✔ | `spec.output.schema` ✔ (output only) | no | no | `kind: Workflow`, partial | **Reject.** Closest of all, still ~60% short; the runtime's own table calls the rest lossy. |
| Zed ACP v2 | no | no | no | no | no | no | **Reject.** Session protocol. |
| AG-UI | no | no | no | no | no | no | **Reject.** `0.0.57`, no wire version field. |
| agents.md | prose | no | no | no | no | no | **Reject as input; emit as output.** |
| Serverless Workflow 1.0.3 | no | no | `input`/`output` schemas ✔ | no | deterministic only | deterministic task graph | **Reject as document; steal the extension mechanism** (§13.2). |
| CloudEvents 1.0 | no | no | `dataschema` ✔ | no | no | no | **Reject as document; adopt as event envelope** (§13.1). |
| OAM v0.3.0 | no | no | schematic ✔ | no | no | component graph | **Reject.** Dormant, non-AI; steal three patterns (§10). |
| Oracle Open Agent Spec | ✔ | ✔ | ✔ | **no** (metrics are not serialisable components) | flows only | ✔ | **Reject.** Not a protocol; and its evaluation gap is precisely PACT's differentiator. |

The deeper reason: **every candidate models one *edge* of the agent** — its callers (A2A),
its tools (MCP), its editor (Zed ACP), its UI (AG-UI), its catalogue entry (OASF), its
traces (OTel), its deployment (OAM), its orchestrator (Serverless Workflow). PACT models
the agent's **interior**, and the interior is precisely what none of them has a field for
(the whole of §12). Adopting any of them as the document would force PACT's core — evals,
SLOs, loop, topology, variants, capability predicates — into a vendor bag the standard
explicitly permits consumers to ignore. That violates T7 at the format level.

## 13.1 What PACT should **adopt** — three envelopes and one naming rule

1. **OASF Record as the distribution/registry envelope.** `Module.artifact` is an
   OCI-shaped `Descriptor` with `artifact_type`, `digest`, `urls`, optional inline payload
   (`proto/agntcy/oasf/types/v1/descriptor.proto`), and OASF is explicitly moving *toward*
   artifact-by-reference (`schema/objects/a2a_data.json:11-14`). PACT publishes
   `canonical.json` as `artifact_type: application/vnd.pact.canonical.v1+json` inside a
   `dev.pact.spec` module shaped like `agentspec_data` (§4.3), projects capabilities onto
   OASF `skills[]` where the closed taxonomy allows, carries lineage in
   `dev.pact/previous-digest` (§4.5), and lets `agntcy-dir` own CID addressing, OCI
   packaging, and signature referrers. **Cost: near zero. Benefit: registry interop with
   OASF owning zero semantics.** Air-gap check (D17): OASF is a schema plus an OCI artifact
   type; `agntcy-dir` signing uses local key material. ✅
2. **CloudEvents 1.0 as the event envelope** for trace→eval promotion, learning-candidate
   accept/reject, and portability verdicts, with `verifiability` (DSSE) for signing and
   `authcontext` for the approving principal (§8). Constraint: context attribute names are
   `[a-z0-9]` only, ≤20 chars recommended, `data` forbidden (`cloudevents/spec.md:198-207`)
   — so all PACT fields go in `data` under a `dataschema` URI, never in context attributes.
3. **A2A Agent Card as the discovery projection**, with all PACT content in exactly one
   versioned `AgentExtension.params` (§11.1).
4. **Reverse-DNS extension keys, not bare `x-`.** MCP `_meta` requires `prefix/name`
   reverse-DNS (`index.mdx:330-344`); MCP extension identifiers require the same with a
   *mandatory* prefix (`versioning.mdx:84-87`); A2A extensions are URIs (`a2a.proto:424-426`);
   OASF module names are "fully qualified" (`module.proto:20-22`). **`x-` is legal in none
   of the four.** Adopt `dev.pact/<name>` for keys and
   `https://pact.dev/extensions/<name>/v1` for URIs, so extension keys pass every boundary
   unrenamed — which is what O1.4's round-trip requirement actually demands. See §15.4 for
   the conflict this creates with the runtime's existing `spec.x-bud`.

## 13.2 What PACT should **steal** structurally

- **Serverless Workflow's `extension` object** — `extend` (which node kind, or `all`) +
  `when` (guard) + `before`/`after` (task lists). An extension may *wrap* but never
  *invent* a node kind. This is what lets a closed core (12 task kinds) stay closed while
  remaining extensible — thesis R8's requirement, and strictly better than "add a field."
- **Zed ACP's two forward-compat conventions** — `_`-prefixed enum values for
  implementation extensions, non-`_` unknown values reserved for future spec versions, plus
  the **receiver obligation to preserve the raw payload**; and
  `x-deserialize-default-on-error` per field. Together these make E-2 implementable at the
  *value* level, not just the *field* level.
- **Zed ACP v2's orthogonal `StateUpdate` × `StopReason`** as PACT's run-state model (§14.1).
- **MCP's `MissingRequiredClientCapabilityError` shape** — `{code, data.requiredCapabilities}`
  — as the wire form of D11's fail-then-recommend.
- **OASF `agentskills_validation`** as the shape of PACT's conformance verdict record (§4.4).
- **OASF `agentspec_data.runtime_deps`** as PACT's explicit non-serialisable-dependency
  list — required to be empty under D14/D15, which turns "fully declarative" into a
  machine-checkable claim (§4.3).
- **Oracle's feature-inferred `min_spec_version`** as PACT's versioning mechanism (§11.2),
  but with **loss-reported** down-serialisation instead of silent field exclusion.
- **OAM's `conflictsWith`** for declaring incompatible policies/traits (§10).
- **agents.md's proximity rule** ("closest file wins; explicit user prompt overrides
  everything") as the normative precedence rule for nested `instructions.md`.
- **A2A's per-interface `protocolVersion`** as the model for PACT's adapter-version
  declaration: version the *interface*, not the *server*.

---

# PART E — Cross-cutting findings and reconciliation

## 14. Cross-cutting observations that change PACT's design

### 14.1 Four protocols now have a run-state model, and they disagree

- **A2A `TaskState`** (`a2a.proto:187-208`) — 8 states: SUBMITTED, WORKING, COMPLETED,
  FAILED, CANCELED, INPUT_REQUIRED, REJECTED, AUTH_REQUIRED. **Conflates lifecycle with
  reason.**
- **MCP `Task`** — 2025-11-25 core (`schema/2025-11-25/schema.ts:1306-1390`), statuses
  `working | input_required | completed | failed | cancelled`; **moved to the
  `io.modelcontextprotocol/tasks` extension in 2026-07-28**.
- **Zed ACP v2** — `StateUpdate ∈ {running, idle, requires_action}` **×** orthogonal
  `StopReason ∈ {end_turn, max_tokens, max_turn_requests, refusal, cancelled, _other}`,
  with an explicit note that background activity does not change foreground state.
- **AG-UI** — `RUN_{STARTED,FINISHED,ERROR}` + `STEP_{STARTED,FINISHED}`; no state, only
  transitions.

**Zed v2 is right and PACT should follow it.** `refusal` and `max_tokens` are both
"COMPLETED" in A2A terms but need different UI, different retry policy, and different eval
handling — a `refusal` is an eval signal, a `max_tokens` is an SLO signal. PACT's run state
must be `{state, stopReason?}` with `state ∈ {submitted, running, requires_action, idle,
failed, cancelled, rejected}` and `stopReason` orthogonal; the A2A projection then folds
`(idle, refusal)` and `(idle, end_turn)` both onto `COMPLETED` **with a loss-report entry**,
rather than pretending A2A carried the distinction.

### 14.2 The industry is converging on stateless-per-request

MCP `2026-07-28` deletes the `initialize` handshake and makes version + identity +
capabilities **required per-request `_meta`** (`versioning.mdx:12-13`, `index.mdx:367-383`).
A2A already has no handshake: version is per-interface on the card and per-request via
`A2A-Version`. **PACT's runtime contract should be stateless-per-request too**, with the
resolved binding (`pact.lock` digest) travelling on every call rather than being established
once at session start. This also simplifies kill-and-resume (AC-2.6 / P-5): there is no
session to reconstruct.

Counter-current worth noting: Zed ACP is *more* stateful in v2 (`session/resume` +
`ReplayFrom`), because an editor session genuinely is one. The convergence is on
**machine-to-machine** edges, not human-facing ones.

### 14.3 MCP is removing what PACT would have relied on

`sampling` (server asks the client's LLM) is deprecated in `2026-07-28`
(`schema/draft/schema.ts:733-758`), as are `roots` and `logging`. If PACT's harness exposed
its model runtime to MCP servers via sampling, that path has a 12-month clock. **Design
against the `2026-07-28` surface, not `2025-06-18`.** In particular:
- do not build tool *tasks* on MCP core `tasks` — they are an extension now;
- do not assume an `initialize` round-trip exists;
- `server/discover.instructions` is the supported way to obtain server-level guidance.

### 14.4 Specs rot exactly like adapters — evidence from two independent sources

Serverless Workflow 1.0.3, a current CNCF spec, hard-codes A2A **v0.3** method names and MCP
**`2025-06-18`** as its default (`schema/workflow.yaml:482,512`). OASF 1.2.0-dev references
the A2A proto at tag **`v0.3.0`** and the MCP server schema at **`2025-09-29`**
(`schema/objects/a2a_data.json`, `mcp_data.json`). Two independent, actively-maintained
specs, both stale on both dependencies.

**PACT must never inline another protocol's method enum or version constant into its
schema.** It must reference protocols by URI + version and resolve at build time against a
locally-vendored, air-gap-safe protocol catalogue, exactly as it does for the model
catalogue (D8/D17).

### 14.5 Nobody solved no-code tools

D14 requires a non-technical author to add a custom tool in YAML. **No protocol in the
corpus has a declarative tool-authoring format.** MCP tools are code (no `tool.yaml`
anywhere in `mcp-python-sdk`); OASF `mcp_server_tool` describes a tool that already exists;
A2A skills are descriptions, not implementations. The two closest things are both outside
the protocol set:
- **Serverless Workflow's `call`/`run` closed set** — `http`, `openapi`, `grpc`, `asyncapi`,
  `mcp`, `a2a`, `run.container`, `run.script`, `run.shell`, `run.workflow`. The only proven
  declarative "invoke an external thing" vocabulary in the corpus.
- **Oracle's `MCPToolBox.tool_filter`** — declarative *curation and signature-pinning* of an
  existing MCP server's tools (§11.1).

PACT's no-code tool kinds should be the union of these two, and nothing else in the corpus
raises the bar further.

### 14.6 Every protocol's extension slot is explicitly ignorable — so the loss report is the product

Verbatim, from four separate specs:
- MCP: *"Implementations MUST NOT make assumptions about values at these keys"*
  (`docs/specification/draft/basic/index.mdx:326-327`).
- Zed ACP: *"The `_meta` property is reserved by ACP … Implementations MUST NOT make
  assumptions about values at these keys"* (`schema/v2/schema.json`, ~213 occurrences).
- A2A: *"Implementations SHOULD ignore unrecognized fields"* (`docs/specification.md:1275`).
- OASF: `Module.data` is `google.protobuf.Struct` with no consumer obligation whatsoever.

**Therefore: putting PACT semantics into an extension bag does not make them portable — it
makes them *transmitted*.** The loss report is not a courtesy attached to the mapping; it is
the only artefact that tells a consumer *what it just failed to understand*. This is the
strongest structural argument in this report for T7 and for AC-6.3.

---

## 15. Reconciliation with `registry-and-portability.md` and the runtime

I state these explicitly, per the brief, because each is a place where my recommendation
diverges from what the runtime already implements or documents.

### 15.1 OSSA ≠ OASF — a naming error in the thesis, not in the runtime

`00-THESIS.md:146` puts "OSSA / OASF (AGNTCY)" in one row. They are different specs:

- **OSSA** = Open Standard Agents, `https://openstandardagents.org/`, apiVersion
  **`ossa/v0.5.0`**. Kinds `Agent`, `Task`, `Workflow`. Shape from the runtime's own
  importer/emitter (`bud-agentic-runtime/src/portability.rs`): `spec.role` (= instructions),
  `spec.llm.{provider,model}`, `spec.tools[]`, `spec.autonomy.level` → `{auto|ask}`
  (`portability.rs:1105-1110`), `spec.capabilities`, `spec.output.schema`,
  `spec.guardrails`, `spec.mcp`/`spec.mcpServers`/`extensions.mcp`
  (`portability.rs:1160-1185`), and everything Bud-native under **`spec.x-bud`**
  (`portability.rs:1112-1121`).
- **OASF** = AGNTCY Open Agentic Schema Framework — `Record`/`Skill`/`Domain`/`Module`/
  `Locator`, schema `1.2.0-dev`.

The runtime implements **OSSA** import/export (`import_openstandardagents`,
`bud registry import-ossa`; `registry-and-portability.md:1136-1156`). It implements
**nothing** for OASF. Successor documents must fix the thesis row or the mapping work will
be scoped wrong.

**Notably, OSSA is a *better* Contract-layer target than OASF** — it has
`spec.output.schema`, `spec.guardrails`, `spec.autonomy.level` and `spec.capabilities`,
none of which OASF has. But it still has no evals, no SLOs, no loop, no topology, no
variants, and no input schema.

### 15.2 The documented `ExportReport` is not the implemented one — PACT must pick

`registry-and-portability.md:1181-1192` documents:

```text
ExportReport
  target: ossa | a2a | openai-agents | claude-agent-sdk | crewai | langgraph
  exact_fields
  scaffolded_fields
  lossy_fields
  unsupported_fields
  runtime_requirements
```

**No such struct exists in the Rust source.** `grep -rn "exact_fields\|scaffolded_fields\|
lossy_fields\|unsupported_fields\|runtime_requirements" --include=*.rs src/ crates/` returns
**nothing**. What ships is (`bud-agentic-runtime/src/runner.rs:1199-1212`):

```rust
pub struct BudPortableImportWarning { pub path: String, pub message: String }
pub struct BudPortableImportReport {
    pub source: String, pub source_api_version: String,
    pub manifest: BudAgentManifest,
    pub lossy: bool,
    pub warnings: Vec<BudPortableImportWarning>,
}
```

persisted at `spec.runtime.portable.unsupported` (`src/portability.rs:1148-1155`).

Two divergences PACT must resolve deliberately:

1. **Granularity.** The shipped report has a single `lossy: bool` and untyped
   `{path, message}` warnings. AC-6.3 says PACT's loss report must be "consistent with the
   in-repo `ExportReport` shape" — which shape? **Recommendation: adopt the documented
   four-class shape and upgrade the runtime**, because per-field classification is what
   makes P-3/AC-2.4 ("zero silent drops") mechanically checkable, and a boolean is not.
   PACT should ship a converter that widens `BudPortableImportReport` into the four classes.
2. **Fail-open vs fail-closed.** `lossy: bool` is a *flag*: import succeeds and records the
   flag. T7 requires lossy operations to be **fail-closed by default** with explicit
   `allowLoss`. PACT's importer must therefore *refuse* by default where the runtime today
   *warns*. This is a behavioural change to a shipping code path and must be called out in
   the migration plan (D3), not slipped in.

### 15.3 Bud's emitted Agent Card uses a non-standard top-level `metadata` key

`bud-agentic-runtime/src/agent_registry_card.rs:181-212` (inside
`registry_entry_a2a_agent_card_with_capabilities`, declared at `:101`) emits, as a raw
`json!` literal — **not** through any generated proto type, so nothing validates it:

```rust
"metadata": {
    "runtime": "bud",
    "gooseBacked": entry.kind != "external_a2a_agent",
    "bud": Value::Object(bud_metadata)
}
```

and `registry_entry_operational_a2a_agent_card` (`:215-244`) adds
`metadata.bud.operational.{status,governance,health}` on top.
`registry-and-portability.md:1025` documents `metadata.bud.*` as the carrier for registry
identity, agent-tool and handoff bindings.

**`AgentCard` has no `metadata` field** (`a2a.proto:362-399`, "Next ID: 20", max used 14).
Three consequences, verified pass 2:

- Per §5.7 consumers SHOULD ignore it, so today this is a *silent* loss, not a rejection.
  It works against tolerant consumers.
- It is **incompatible with card signing** (§2.3), which the runtime does not do:
  `grep -rn "signature\|jws\|JWS" src/agent_registry_card.rs` → **no hits**. Open question 6
  closed: **no signing path exists today**, so this is a tolerance issue, not yet a
  correctness bug. It becomes a correctness bug the day signing lands.
- The runtime emits **zero A2A extensions**: `grep -rn "extensions" src/agent_registry_card.rs`
  → **no hits**; `capabilities` is built at `:173-179` with only `streaming`,
  `extendedAgentCard`, and conditionally `pushNotifications`.

**PACT must not inherit this pattern.** Migration path: move `metadata.bud.*` into an
`AgentExtension` with `uri: https://pact.dev/extensions/bud/v1`, keep `metadata` for one
release as a deprecated mirror, and add signing *after* the move — never before.

### 15.4 `x-bud` vs `dev.pact/` — a real conflict, stated plainly

The runtime's OSSA integration already uses an **`x-`-prefixed** extension convention:
`ossa_x_bud()` reads `spec.x-bud` / `spec.x_bud` / `x-bud` / `x_bud`
(`bud-agentic-runtime/src/portability.rs:1112-1121`). My §13.1 recommendation is to drop
bare `x-` in favour of reverse-DNS `dev.pact/`.

These conflict. Resolution I recommend, and the reason:

- **`x-bud` is correct where it lives** — inside an OSSA YAML document, which is a
  Kubernetes-shaped manifest where `x-` is idiomatic and legal.
- **`x-` is illegal at three of PACT's four protocol boundaries** — MCP `_meta` (prefix must
  be dotted labels + `/`), MCP extension identifiers (mandatory prefix), and OASF module
  names ("fully qualified"). Only OSSA and thesis O1.4 permit it.
- **Therefore split by layer, and say so in the schema:** PACT's *document* extension key is
  `x-<vendor>` (preserving OSSA/`bud.dev/v1` round-trip and thesis O1.4 verbatim); PACT's
  *boundary* extension key is `dev.pact/<name>`, and the loader owns a **declared, total,
  bidirectional** mapping between them (`x-bud` ⇄ `dev.bud/`). The mapping must be a table
  in the spec, not an algorithm, so that AC-1.3's "round-trips untouched" stays literally
  true and no key is ever mangled silently.

### 15.5 "Goose ACP" is Zed's Agent Client Protocol **v1**

`registry-and-portability.md:1149` mentions `Goose ACP _bud/unstable/registry/import/a2a`,
and `registry.search(protocol: "bud"|"goose"|"a2a"|"acp")` at `:819`. Goose depends on
`agent-client-protocol = "1.0"` / `agent-client-protocol-schema = "1.1"`
(`/home/bud/ditto/gaia-ai-runtime/goose/Cargo.toml:29-31`). Zed's current schema is **v2**.
Pass 2 diffed them (§3.1): v2 **removes** the `fs/*` and `terminal/*` client methods
entirely and inverts terminal ownership. Anything PACT builds on the Goose ACP surface today
is v1 and will need non-cosmetic rework at the v2 migration.

### 15.6 Everything else in the runtime is consistent with what I read

`registry-and-portability.md:972-980` correctly describes A2A v1.0's `supportedInterfaces`,
per-interface `protocolVersion`, opaque `tenant`, and the three bindings; `:1035-1040`
correctly requires `id`/`name`/`description`/non-empty `tags` on every emitted skill
(matching `a2a.proto:436-444`); `:1023` correctly withholds `capabilities.pushNotifications`
until the server owns the standard push-config operations, and the code matches
(`agent_registry_card.rs:176-179`). No further contradiction found.

---

## 16. Corrections to pass 1

| # | Pass-1 claim | Correction |
|---|---|---|
| 1 | "Learning lineage — OASF `v1alpha2` had `previous_record_cid`; v1 dropped it. **REGRESSED** — the one field that fit was removed." | Correct that the field is gone from `v1/record.proto`, but incomplete. The reference registry moved lineage into the **OCI manifest annotation** `org.agntcy.dir/previous-cid` (`agntcy-dir/server/store/oci/constants.go:43`) — and then **hard-coded it empty for OASF v1** (`api/core/adapters/oasf_v1.go:92-94`). The regression is *worse* than stated, but there is a clean workaround via `org.agntcy.dir/custom.<key>` (§4.5). |
| 2 | "The loss report itself — **NO HOME**. The honesty artefact is unrepresentable in every protocol." | Over-stated. OASF 1.2.0-dev's `agentskills_validation` is a verdict-with-provenance record (status/validator/timestamp/errors/warnings/report-URL) and is a usable shape precedent (§4.4). What has no home is the **contract the verdict is measured against**, not the verdict. |
| 3 | Mapping tables used classes `exact / scaffolded / lossy / partial / degraded`. | `partial` and `degraded` are not in the runtime's `ExportReport` vocabulary. All tables now use the documented four: `exact / scaffolded / lossy / unsupported`. Separately, that four-class report is **documented but unimplemented** (§15.2). |
| 4 | OTel figures accurate "as of `v1.43.0`". | `model/manifest.yaml:1` declares `1.44.0-unreleased`. Also under-stated: **55 of 60 `gen_ai.*` attributes are `stability: development`**, so none should be pinned normatively. |
| 5 | OASF module registry listed as `observability, evaluation, language_model, mcp, a2a, agentspec, acp_manifest`. | Incomplete. Two further modules exist and both matter: `core/language_model/prompt` (uid 1) and **`core/language_model/agentskills` (uid 2)**, the latter carrying `SKILL.md` metadata and the validation record of §4.4. |

---

## 17. Design implications (specific, implementable)

Numbered for citation in `20-ARCHITECTURE` / `30-FRD`.

**D-1 — Extension keys are two-layer with a declared table.** Document-level extension keys
are `x-<vendor>`; boundary-level are `dev.<vendor>/<name>` (MCP `_meta`, OASF module names)
and `https://<vendor>/extensions/<name>/v1` (A2A). The loader ships a *table*, not an
algorithm, mapping between them, and any key without a table entry is a hard validation
error at export. (§13.1, §15.4)

**D-2 — Exactly one A2A extension, URI `https://pact.dev/extensions/contract/v1`, data-only,
in `AgentExtension.params`.** Never a top-level `metadata` key. New URI on any breaking
change. This is the only PACT payload on a card. (§11.1, §15.3)

**D-3 — PACT's run-state IR is `{state, stopReason?}`, orthogonal, modelled on Zed ACP v2.**
`state ∈ {submitted, running, requires_action, idle, failed, cancelled, rejected}`;
`stopReason ∈ {end_turn, max_tokens, max_turns, refusal, cancelled, error, _*}`. The A2A
projection folds `stopReason` away and **must emit a loss-report entry when it does**. (§14.1)

**D-4 — Every closed enum in the PACT schema is an open enum with the Zed convention.**
`_`-prefixed values are implementation extensions; unknown non-`_` values are reserved for
future PACT versions; receivers **must preserve the raw payload** when storing, replaying,
proxying, or forwarding. Applies to modality, tool kind, loop kind, node kind, stop reason,
permission kind. (§3.1, §13.2)

**D-5 — `minSpecVersion` is computed from the feature set used, not declared by the author.**
Down-serialisation to an older `pact.dev/vN` emits a loss report per excluded field and is
fail-closed without `allowLoss`. (§11.2)

**D-6 — Emit `runtime_deps` in the OASF projection and require it empty in `strict` mode.**
Any entry is a D14/D15 violation and must appear in the loss report. This converts "fully
declarative" from a slogan into a registry-checkable assertion. (§4.3)

**D-7 — PACT's conformance/portability verdict record is structurally isomorphic to OASF
`agentskills_validation`:** `{status, validator, validated_at, contract_valid, evals_passed,
errors[], warnings[], report_url}`. Publish it as an OASF module and as a
`gen_ai.evaluation.result` event; carry the *threshold* in `dev.pact.*` attributes, because
OTel has no slot for it. (§4.4, §11.4, §12.3)

**D-8 — Never inline another protocol's method enum or version constant in the PACT schema.**
Reference by URI + version; resolve against a locally-vendored, air-gap-safe protocol
catalogue at build time, mirroring the model catalogue (D8/D17). Both Serverless Workflow
and OASF are provably stale on exactly this. (§14.4)

**D-9 — Loss reports use the runtime's four classes** (`exact / scaffolded / lossy /
unsupported`) plus `runtime_requirements`, and **PACT's importer is fail-closed** where the
runtime today sets `lossy: true` and proceeds. Ship a widener from
`BudPortableImportReport`. (§15.2)

**D-10 — PACT's no-code tool vocabulary is the union of Serverless Workflow's `call`/`run`
closed set and Oracle's `MCPToolBox.tool_filter`.** Concretely: `http`, `openapi`, `grpc`,
`mcp`, `a2a`, `container`, `script`, `shell`, `workflow`, plus a declarative MCP exposure
filter that pins tool name, description override, input signature, and confirmation flag.
Nothing else in the corpus raises the bar. (§9.3, §11.1, §14.5)

**D-11 — Do not build on MCP `sampling`, `roots`, `logging`, or core `tasks`.** Design
against `2026-07-28`: stateless-per-request, `server/discover` for server instructions,
`io.modelcontextprotocol/tasks` as an *extension* if tasks are needed at all. (§1.3, §14.3)

**D-12 — Propagate W3C trace context into MCP `_meta` (`traceparent`/`tracestate`/`baggage`)
on every PACT-originated tool call.** It is normatively reserved and is the only way
`execute_tool` spans link to server-side spans. (§1.2, §11.4)

**D-13 — Declarative HITL forms are restricted to flat primitive properties, or the MCP
elicitation projection is marked `lossy` and flattening is reported.** MCP's
`requestedSchema` forbids nesting. Prefer AG-UI's `InterruptSchema.responseSchema`
(unrestricted) as the *internal* model and treat MCP as the narrower target. (§1.5, §5.2)

**D-14 — Adopt OAM `conflictsWith` for policy/trait incompatibility, checked at resolve
time.** PACT has no analogue and the failure it prevents (e.g. `autonomy: full` +
`approval-gate: every-tool-call`; `constrained_decoding: grammar` + hosted-API substrate) is
exactly the class of contradiction a non-technical author will write. (§10)

**D-15 — Emit `AGENTS.md` as an output projection with the proximity precedence rule
("closest wins, explicit user prompt overrides"); never accept it as input.** (§6)

**D-16 — Model D11's fail-then-recommend on MCP's `MissingRequiredClientCapabilityError`:**
the refusal carries `data.requiredCapabilities` as a structured list, not a message string,
so the recommender can consume its own refusals. (§1.4)

**D-17 — Do not take a normative dependency on AG-UI.** `0.0.57`, no wire version field,
pre-1.0 removal notices. Consume its vocabulary (event taxonomy, `InterruptSchema`,
modality union incl. video); bind to nothing. (§5.3)

**D-18 — PACT emits `invoke_workflow` for team nodes and `invoke_agent` for agent nodes,
statically.** OTel's own guidance says instrumentations should skip `invoke_workflow` when
they cannot distinguish the two; PACT always can, because the topology is declared. This is
a demonstrable observability win from owning the loop (D12). (§7.3)

**D-19 — Carry learning lineage as OASF record annotation `dev.pact/previous-digest`,** which
`agntcy-dir` promotes to `org.agntcy.dir/custom.dev.pact/previous-digest`, because
`org.agntcy.dir/previous-cid` is hard-coded empty for OASF v1 records. (§4.5)

**D-20 — Wrap learning/feedback events in CloudEvents 1.0 with `verifiability` (DSSE) and
`authcontext`; all PACT fields in `data` under a `dataschema` URI, never in context
attributes** (≤20 chars, `[a-z0-9]` only, `data` forbidden). (§8)

---

## 18. Open questions

**Closed in pass 2:**

- ~~Q3 Zed ACP v1 vs v2 delta~~ — diffed, §3.1. v2 removes `fs/*` and `terminal/*` client
  methods and inverts terminal ownership; adds `StateUpdate`, `ReplayFrom`, typed permission
  subjects.
- ~~Q4 OASF Record Manifest / OCI packaging~~ — found in `agntcy-dir/server/store/oci/`,
  §4.5. Annotation schema and artifact types enumerated.
- ~~Q5 A2A extension registry~~ — read
  `docs/topics/extension-and-binding-governance.md`, §2.4. **No registration required** for
  third-party URIs; URIs are identifiers, HTTP access not expected (air-gap-safe).
- ~~Q6 Does the runtime sign A2A cards yet?~~ — **No.** `grep -rn "signature\|jws\|JWS"
  src/agent_registry_card.rs` → no hits. The non-standard `metadata` key is therefore a
  tolerance issue today, a correctness bug the day signing lands. §15.3.
- ~~Q7 OSSA v0.5.0 upstream spec~~ — still not in corpus, but the runtime's importer surface
  is now fully enumerated from `src/portability.rs` (§15.1), which is sufficient for the
  mapping work. Downgraded from open question to a caveat.

**Still open:**

1. **`semantic-conventions-genai` is not in the corpus.** Every `gen_ai.*` attribute in §7 is
   read from the *deprecated mirror* in `otel-semconv` at schema `1.44.0-unreleased`, where
   55 of 60 attributes are `stability: development`. Names, requirement levels, and
   especially the evaluation event may have changed post-move. **Must be re-verified before
   PACT pins any attribute name.** D-8 makes this survivable (reference the convention set
   by version, resolve through a table), but the table's initial contents are unverified.
2. **MCP registry `server.schema.json`** is referenced as
   `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`
   (`docs/registry/versioning.mdx:13`) and is not in the corpus (`find` confirms). §1.7 is
   documented from prose examples only; the full field set is unverified.
3. **Does `agntcy-dir` validate `skills[]` against the closed OASF taxonomy on publish, or
   accept arbitrary uids?** This decides whether PACT's capability→OASF-skill projection is
   `lossy` (drop unmapped) or `unsupported` (reject the record). I did not trace the
   validation path. It changes one cell in §11.3 and one line of the exporter.
4. **A2A `AgentCard` field numbers 15–19 are burned** ("Next ID: 20", max used 14). Whether
   those were removed fields with reserved semantics matters for forward compatibility of
   the JCS signing payload. Not answerable from the proto alone.
5. **`agentskills.io` specification is not in the corpus.** §4.4 is read from OASF's
   normalisation of it. If PACT emits `agentskills` modules, the upstream `SKILL.md` schema
   must be read directly — `filedef/skills-anthropic` is in the corpus and may cover it, but
   it was out of this brief's scope.
6. **Does any A2A implementation actually verify card signatures today?** §2.3's tension
   between §5.7 unknown-field tolerance and RFC 8785 JCS is real in the text; whether it
   bites in practice is unmeasured, and it determines how urgent §15.3's migration is.
