# PACT research stream: **protocols-interop**

**Author:** research subagent · **Date:** 2026-07-26
**Scope:** MCP, A2A, ACP (all three of them), AGNTCY OASF, Zed agent-client-protocol,
AG-UI, agents.md, OTel `gen_ai` semantic conventions, CloudEvents, Serverless Workflow, OAM.
**Method:** read spec source (`.proto`, `schema.ts`, `schema.json`, `*.yaml` registries)
in `/home/bud/ditto/agent-inter-op/research/repos/protocols/`, not READMEs, wherever the two
could disagree. Every claim below carries a `file:line` citation. Statements that are my
inference rather than something I read are marked **[INFERRED]**.

**Corpus commits pinned at read time:**

| Repo | HEAD | Date |
|---|---|---|
| `mcp-spec` | `7634684382c3d14cf7e9f14073fe40a2d8ace3fa` | 2026-07-23 |
| `mcp-python-sdk` | `629ca297d24b24f8055bf191ea7ff046a5c32100` | 2026-07-25 |
| `a2a-spec` | `0ef1b02547e959d770ebf3460d058f5c3421641c` | 2026-07-23 |
| `a2a-python` | `086d70fffbc4dce672ca12cf35d0ee794241128d` | 2026-07-23 |
| `acp` (IBM/BeeAI) | `e5265ca9fa06c55cd011b1e81ee927f6d80af8f6` | **2025-08-25** |
| `agntcy-oasf` | `e8565371ddfeb373ddbb59aad7670bd002905c57` | 2026-07-21 |
| `agent-client-protocol` (Zed) | `649cc279fa8780dc94048d492578de742d9ac7c7` | 2026-07-25 |
| `ag-ui` | `ab9ae4594147ac5ff4d8bf72264dee37c3e0cdf8` | 2026-07-24 |
| `agents-md` | `d1ac7f063d20e70015ed6732664049ae4ba9d74e` | **2026-03-12** |
| `otel-semconv` | `bfa549224a08931dca5ba8fdf7bdfa540b6c0ab2` | 2026-07-24 |
| `cloudevents` | `c2845a49bc9831be02f305a4a792401b932d77d4` | 2026-07-23 |
| `serverless-workflow` | `44c3ecf76ee27f34a888b27927cfde0b369b25b9` | 2026-07-23 |
| `oam-spec` | `a64696e70e24bd4d0ad26705c8338c51a19f5163` | **2024-12-24** |

---

## 0. The one-paragraph answer

**No protocol in this corpus defines an agent.** Every one of them defines either a
*transport* (MCP, A2A, Zed ACP, AG-UI), an *observation format* (OTel `gen_ai`,
CloudEvents), a *catalogue record* (AGNTCY OASF, MCP registry `server.json`), a
*workflow* (Serverless Workflow), a *deployment topology* (OAM), or *nothing at all*
(agents.md is prose). The literal proof: the MCP draft schema contains the substring
`agent` **zero** times (`schema/draft/schema.ts`, `grep -c agent` → 0); the A2A `.proto`
contains no `model`, no `schema`, no `eval`, no `cost`, no `latency` field
(`specification/a2a.proto`, grep). The single object in the entire corpus that carried
JSON Schema for an agent's *input and output* — AGNTCY's `acp_agent` — was **deprecated in
OASF 0.8.0** (`schema/objects/acp.json:6-9`). PACT is therefore not competing with any of
these; it is filling the hole they all leave, and its job at the boundary is **projection
plus a loss report**, not adoption.

---

## 1. MCP — Model Context Protocol

### 1.1 What it standardises

A JSON-RPC 2.0 protocol between a **host/client** and a **server** that supplies three
primitives to a model:

| Primitive | Schema | Line (2025-11-25) | Line (draft 2026-07-28) |
|---|---|---|---|
| **Tool** | `name`, `title`, `description`, `inputSchema` (JSON Schema 2020-12, root `type:"object"`), `outputSchema`, `annotations`, `icons`, `_meta` | `schema/2025-11-25/schema.ts:1249-1292` | `schema/draft/schema.ts:1960-2002` |
| **Prompt** | `name`, `title`, `description`, `arguments[]` (`name`/`description`/`required` only) | `schema/2025-11-25/schema.ts:984-1020` | `schema/draft/schema.ts:1646` |
| **Resource** / **ResourceTemplate** | `uri` (or `uriTemplate`, RFC 6570), `name`, `title`, `description`, `mimeType`, `annotations`, `size`, `_meta` | `schema/2025-11-25/schema.ts:802-878` | `schema/draft/schema.ts:1428` |

Plus, client-side: `roots`, `sampling` (server asks client's LLM to complete),
`elicitation` (form + URL modes, `schema/2025-11-25/schema.ts:2155-2233`), and
`completion` (argument autocomplete).

`ToolAnnotations` is the only behavioural metadata MCP carries about a tool —
`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`, and all four are
explicitly **hints**, not guarantees (`schema/2025-11-25/schema.ts:1180-1221`).

### 1.2 Extension mechanism

Two, and they are different:

1. **`_meta`** on almost every object. Key format is normative:
   `docs/specification/2025-11-25/basic/index.mdx:190-216` — optional dotted-label
   **prefix** ending in `/`, reverse-DNS recommended, and *"Any prefix where the second
   label is `modelcontextprotocol` or `mcp` is reserved"* (line 208). Name segment must
   begin and end alphanumeric, may contain `-`, `_`, `.`.
2. **Capability-negotiated extensions** (draft only), identified by the *same* key format
   with a **mandatory** prefix, declared in `capabilities.extensions` as a map of
   identifier → settings object (`docs/specification/draft/basic/versioning.mdx:80-119`;
   `docs/extensions/overview.mdx:9`). Official extensions live in `ext-*` repos under the
   MCP GitHub org and use the `io.modelcontextprotocol` prefix.

### 1.3 Version story — and the break that matters

Date-based versions, **not** semver (`CLAUDE.md`, "Specification Versioning").
Released: `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`, `2026-07-28`
(`mcp-python-sdk/src/mcp-types/mcp_types/version.py:12-17`).

**`2026-07-28` is a structural break.** The `initialize` handshake is *gone*:

- *"There is no negotiation handshake. Every request carries its protocol version"* —
  `docs/specification/draft/basic/versioning.mdx:12-13`.
- Version, client identity, and client capabilities move into per-request `_meta` keys
  `io.modelcontextprotocol/protocolVersion`, `.../clientInfo`, `.../clientCapabilities`
  (`schema/draft/schema.ts:63-98`).
- New `server/discover` returns `supportedVersions[]`, `capabilities`, and — critically for
  PACT — **`instructions?: string`**, *"Natural-language guidance describing the server and
  its features… can be used by clients to improve an LLM's understanding of available
  tools (e.g., by including it in a system prompt)"* (`schema/draft/schema.ts:678-697`).
- The SDK splits the eras explicitly: `HANDSHAKE_PROTOCOL_VERSIONS` vs
  `MODERN_PROTOCOL_VERSIONS` (`version.py:21-31`), and a 7-row client×server
  compatibility matrix says **Modern-client/Legacy-server and Legacy-client/Modern-server
  both simply FAIL** (`versioning.mdx:164-172`).
- `logging`, `roots`, and **`sampling`** are all deprecated as of `2026-07-28` under
  SEP-2577 (`schema/draft/schema.ts:724-758`, `801-808`), retained ≥12 months.
- `tasks` left the core schema entirely and became the `io.modelcontextprotocol/tasks`
  extension: `CreateTaskResult`, `GetTaskRequest`, `ListTasksRequest`, `CancelTaskRequest`
  and `Tool.execution` are present at `schema/2025-11-25/schema.ts:1229-1240,1344-1505`
  and **absent from `schema/draft/schema.ts`**.

### 1.4 What MCP does NOT cover for agent DEFINITION

- **No agent.** `grep -c agent schema/draft/schema.ts` → `0`.
- No model selection beyond a *hint* list: `ModelPreferences`/`ModelHint` exists only
  inside `sampling` (`schema/2025-11-25/schema.ts:1925-1998`) and sampling is now
  deprecated.
- No loop, no topology, no memory, no handoff, no eval, no SLO, no cost, no policy.
- No **video** and no **computer-use** content type. `ContentBlock = TextContent |
  ImageContent | AudioContent | ResourceLink | EmbeddedResource`
  (`schema/draft/schema.ts:2292-2293`); `grep -in video` and `grep -in computer_use` →
  no hits. This is a hard blocker for D16 modality parity if PACT tried to use MCP content
  as its I/O type system.
- No declarative authoring surface. Tools are code; there is no `tool.yaml` in the spec or
  the Python SDK. **This is the single biggest gap between MCP and D14 (no-code ceiling).**
- Prompt arguments are `{name, description, required}` only — **no type, no schema**
  (`schema/2025-11-25/schema.ts:1006-1020`). An MCP Prompt cannot express a typed
  parameter; PACT's parameterised skills therefore cannot round-trip through
  `prompts/list` without loss.

### 1.5 The MCP registry (`server.json`) — the closest thing MCP has to a manifest

`docs/registry/versioning.mdx:11-30` shows the shape: `$schema`, `name`
(`io.github.user/thing`), `title`, `description`, `version`, `packages[]` with
`registryType` ∈ {npm, pypi, …}, `identifier`, `version`, `transport.type`.
Ownership is verified out-of-band (npm `package.json.mcpName` must equal `server.json.name`,
`docs/registry/package-types.mdx:41-49`). Version strings may be any format but ranges
(`^1.2.3`, `1.x`, `>=1.2.3`) are **prohibited** (`versioning.mdx:44-66`). The registry is in
**preview** with "breaking changes or data resets may occur" (`versioning.mdx:6`).

This is a *distribution* manifest for a server process, not an agent definition. It has no
tools, no prompts, no capabilities — those are discovered at runtime.

---

## 2. A2A — Agent2Agent (Linux Foundation)

### 2.1 Status and version story

**v1.0.1, released 2026-05-26** (`CHANGELOG.md:3`). v1.0.0 (2026-03-12) was a large
breaking release: package renamed to `lf.a2a.v1`, `preferredTransport`/`url` replaced by
`supportedInterfaces[]`, `TaskPushNotificationConfig` merged, OAuth implicit/password
removed, ProtoJSON enum alignment (`CHANGELOG.md:14-32`).

Versioning is **per-interface, not per-server**: `AgentInterface.protocol_version` is a
REQUIRED string like `"0.3"` or `"1.0"` (`specification/a2a.proto:352-355`), and one card
may advertise several interfaces at different versions. There is no global handshake.

The canonical data model is **Protocol Buffers**; all bindings must be functionally
equivalent (`docs/specification.md:768`, `1145-1152`). JSON serialisation is ProtoJSON:
camelCase fields, SCREAMING_SNAKE_CASE enum values
(`docs/specification.md:1204-1222`). Three official bindings — `JSONRPC`, `GRPC`,
`HTTP+JSON` (`specification/a2a.proto:341-344`); custom bindings SHOULD be identified by
URI (`docs/specification.md:1279-1302`).

### 2.2 The AgentCard, field by field

`specification/a2a.proto:362-399` (`// Next ID: 20`):

| # | Field | Req | Notes |
|---|---|---|---|
| 1 | `name` | ✔ | |
| 2 | `description` | ✔ | |
| 3 | `supported_interfaces[]` | ✔ | ordered; first = preferred (`docs/specification.md:1988-1991`) |
| 4 | `provider` | | `{url, organization}` (`:402-409`) |
| 5 | `version` | ✔ | free-form string, of the *agent*, not the protocol |
| 6 | `documentation_url` | | |
| 7 | `capabilities` | ✔ | `{streaming?, push_notifications?, extensions[], extended_agent_card?}` (`:412-421`) |
| 8 | `security_schemes` | | map → APIKey / HTTPAuth / OAuth2 / OIDC / mTLS (`:504-517`) |
| 9 | `security_requirements[]` | | |
| 10 | `default_input_modes[]` | ✔ | **media types**, e.g. `text/plain` |
| 11 | `default_output_modes[]` | ✔ | |
| 12 | `skills[]` | ✔ | |
| 13 | `signatures[]` | | JWS per RFC 7515 (`:457-467`) |
| 14 | `icon_url` | | |

`AgentSkill` (`:436-453`): `id`✔, `name`✔, `description`✔, `tags[]`✔, `examples[]`,
`input_modes[]`, `output_modes[]`, `security_requirements[]`.
**There is no `metadata` field on `AgentCard`.** There is also no schema field anywhere:
`grep -in "json.schema\|inputSchema\|outputSchema" specification/a2a.proto` → **no hits**.

`AgentInterface` (`:336-356`): `url`✔, `protocol_binding`✔ (open string), `tenant`
(opaque routing key — A2A's *entire* multi-tenancy story), `protocol_version`✔.

### 2.3 Signing — and why a non-standard top-level key is dangerous

`docs/specification.md:2002-2083`. Canonicalisation is **RFC 8785 JCS** over the card with
`signatures` removed *and* with proto field-presence semantics applied (optional-unset
fields omitted, REQUIRED fields always present even at default value,
`docs/specification.md:2012-2023`). Meanwhile §5.7 says *"Implementations **SHOULD** ignore
unrecognized fields"* (`docs/specification.md:1275`).

**Consequence:** a producer that adds a non-standard top-level key and signs the card
produces a JCS payload that includes that key; a consumer that parses into the proto
(dropping the unknown field) and re-canonicalises produces a *different* payload, and the
signature fails. Unknown-field tolerance and signature verification are in direct tension.
Any PACT data placed on an Agent Card **must** go in a standard field. **[INFERRED]** —
the two clauses are each explicit; the conflict between them is my deduction, not the
spec's text.

### 2.4 Extension mechanism — and the right hook for PACT

`AgentExtension` (`specification/a2a.proto:424-433`): `uri`, `description`, `required`,
**`params` (`google.protobuf.Struct`)** — i.e. arbitrary JSON, in a *standard* field.
Declared under `capabilities.extensions`; clients opt in per-request via binding-specific
mechanisms (HTTP header `A2A-Extensions`, `docs/specification.md:1051-1060`). Extension URIs
SHOULD carry a version; **breaking changes MUST mint a new URI** and *"MUST NOT fall back
to a previous version automatically"* (`docs/specification.md:1139-1141`).

The governance doc names exactly the category PACT needs: *"**Data-only Extensions**:
Exposing new, structured information in the Agent Card that doesn't impact the
request-response flow"* (`docs/topics/extensions.md:26-29`). Official namespace is
`https://a2a-protocol.org/extensions/`; third parties use their own URIs
(`docs/topics/extensions.md:57-70`).

### 2.5 Runtime model (for completeness)

`Task` (`:167-183`) = `id`, `context_id`, `status`, `artifacts[]`, `history[]`, `metadata`.
`TaskState` (`:187-208`) — 8 states + UNSPECIFIED: SUBMITTED, WORKING, COMPLETED, FAILED,
CANCELED, INPUT_REQUIRED, REJECTED, AUTH_REQUIRED. `Part` (`:224-241`) is a `oneof` of
`text | raw(bytes) | url | data(Value)` **plus** `media_type` and `filename` on *every*
part — so A2A can carry video and computer-use screenshots by media type where MCP cannot.
`Message` (`:260-277`) carries `extensions[]` (URIs) and `reference_task_ids[]`.
Discovery: `GET /.well-known/agent-card.json` (`docs/specification.md:1978`, IANA
registration at `:3326-3353`).

### 2.6 What A2A does NOT cover for agent DEFINITION

- **No I/O schema.** Only media types. A skill cannot say "my input is this JSON Schema".
- No model, no model requirements, no capability predicates.
- No evals, no thresholds, no SLOs, no cost, no budget, no token accounting.
- No instructions/system prompt, no loop, no memory, no topology (a supervisor and its
  three specialists are four unrelated cards).
- No versioned lineage: `version` is a free string with no `previous` pointer.
- No provenance beyond `provider` + optional JWS.
- Multi-tenancy is one opaque `tenant` string (`:345-351`) — consistent with D24's
  "minimal, adapter-shaped" constraint, but it means A2A gives PACT nothing for tenancy.

---

## 3. The three ACPs — disambiguation (this matters; the corpus contains all three)

| # | Name | Owner | Repo | Status |
|---|---|---|---|---|
| 1 | **Agent Communication Protocol** | IBM / BeeAI | `research/repos/protocols/acp` | **DEAD.** README: *"ACP is now part of A2A under the Linux Foundation!"*; last commit **2025-08-25** (`README.md:20-24`) |
| 2 | **Agent Connect Protocol** | AGNTCY | OASF `schema/objects/acp*.json` | **DEPRECATED** since OASF 0.8.0, *"please use A2A instead"* (`schema/objects/acp.json:6-9`) |
| 3 | **Agent Client Protocol** | Zed | `research/repos/protocols/agent-client-protocol` | **ALIVE**, schema v1 and v2 |

**Do not target #1 or #2.** Recommendation for the loss report and for `20-ARCHITECTURE`:
never write "ACP" unqualified again.

### 3.1 Zed agent-client-protocol (the live one)

An **editor ⇄ coding-agent session protocol**, JSON-RPC. Schema v2 has 172 `$defs`
(`schema/v2/schema.json`). Method surface (`schema/v2/meta.json`):
agent side `initialize`, `auth/login`, `session/new`, `session/set_config_option`,
`session/prompt`, `session/cancel`, `session/list`, `session/delete`, `session/resume`,
`session/close`, `auth/logout`; client side `session/request_permission`,
`session/update`, `elicitation/create`, `elicitation/complete`.

Version story: `ProtocolVersion` is a **uint16 integer** — *"only bumped for breaking
changes. Non-breaking changes should be introduced via capabilities"*
(`schema/v2/schema.json`, `$defs.ProtocolVersion`).

**Three vocabularies worth stealing (they are the best in the corpus):**

- `ToolKind` — `read | edit | delete | move | search | execute | think | fetch |
  switch_mode | other`, plus an open string.
- `StopReason` — `end_turn | max_tokens | max_turn_requests | refusal | cancelled`, open.
- `PermissionOptionKind` — `allow_once | allow_always | reject_once | reject_always`, open.

**And one extension convention that is strictly better than `x-`:** every open enum
documents *"Values beginning with `_` are reserved for implementation-specific extensions.
Unknown values that do not begin with `_` are reserved for future ACP variants."* This
gives forward-compatible enum widening without a registry.

Also present and useful: `SessionConfigOption` (a select/boolean/select-group config
surface an agent exposes to the client at runtime), `PlanEntry` with
status/priority, `Cost {amount, currency(ISO-4217)}`, `UsageUpdate`, `Terminal`,
`Diff`/`DiffPatch`, `AvailableCommand` (slash commands with typed input).

**Reconciliation note:** Goose depends on `agent-client-protocol = "1.0"` and
`agent-client-protocol-schema = "1.1"` (`/home/bud/ditto/gaia-ai-runtime/goose/Cargo.toml:29-31`),
i.e. **v1, not v2**. Anything PACT designs against Zed ACP today lands on v1 in the runtime.

**Does NOT cover:** any definition surface whatsoever. No manifest, no card, no discovery
document. It assumes the agent already exists as a launchable process.

---

## 4. AGNTCY OASF — Open Agentic Schema Framework

### 4.1 What it standardises

A **content-addressed catalogue record** for "agentic AI content". Schema version in-tree is
`1.2.0-dev` (`schema/version.json`). The authoring format is an OCSF-style metaschema
(caption/description/extends/attributes/requirement) under `schema/`; the wire format is
protobuf under `proto/agntcy/oasf/types/v1/`.

`Record` (`proto/agntcy/oasf/types/v1/record.proto:21-57`):
`annotations` (map<string,**string**>), `name`, `version`, `schema_version`, `description`,
`authors[]`, `created_at` (RFC 3339), `locators[]`, `skills[]`, `domains[]`, `modules[]`.
The JSON-schema view (`schema/objects/record.json`) marks `name`, `version`,
`schema_version`, `description`, `authors`, `created_at`, `skills` as **required**.

`Skill` and `Domain` are `{annotations, name, id:uint32}` drawn from a **closed, uid-keyed
taxonomy** shipped in-tree: 19 skill categories (`schema/skills/`, e.g.
`reasoning_planning` uid 15 with children `chain_of_thought_structuring` uid 2, …) and 25
domains (`schema/domains/`, e.g. `finance_and_business`, `healthcare`).

`Locator` (`schema/objects/locator.json`): `type` ∈ {unspecified, helm_chart,
container_image, package, source_code, binary, url}, `urls[]`, `annotations`.

### 4.2 Extension mechanism — `Module`, and it is genuinely open

`Module` (`proto/agntcy/oasf/types/v1/module.proto`): `annotations`, `name`, `id:uint32`,
**`data: google.protobuf.Struct`** (arbitrary JSON), **`artifact: Descriptor`**.
`Descriptor` (`descriptor.proto`) is OCI-shaped: `media_type`, `artifact_type`, `size`,
`digest`, `urls[]`, inline `data: bytes`, inline `json: Struct`.

Module registry today (`schema/modules/`): core → `observability` (uid 1), `evaluation`
(uid 2), `language_model`; integration → `mcp` (uid 2), `a2a` (uid 3), `agentspec` (uid 4),
`acp_manifest`. The trend is explicit: both `a2a_data.card_data` and
`mcp_data.mcp_data` are marked *"Inline … payload is deprecated, please use
module.artifact instead"* since 1.0.0 (`schema/objects/a2a_data.json:11-14`,
`schema/objects/mcp_data.json:45-49`). **OASF is converging on "the module points at an
opaque, digest-addressed artifact."** That is a first-class hook for PACT.

Extension *names/uids* are tracked in a flat registry file, `schema/extensions.md`, which
currently contains one row (`dev`, uid 999). Collision avoidance is by manual PR.

### 4.3 Version story

`schema_version` is a record field; proto packages are `v1alpha0`, `v1alpha1`, `v1alpha2`,
`v1`. `v1alpha1` and `v1alpha0` had a `signature.proto`; **`v1` does not** — signing moved
out of the record (to OCI/`agntcy-dir`). `v1alpha2/record.proto:21-25` documents a **4 MB
max record size** and a `previous_record_cid` lineage pointer at field 99; `v1/record.proto`
drops both, and says records are *"packaged and distributed as OCI Artifacts conforming to
the Record Manifest specification"* (`v1/record.proto:16-18`). So v1 loses the lineage
pointer PACT would want for T6/learning provenance.

### 4.4 The evaluation module — a published *result*, never a *specification*

This is the most important negative finding about OASF and it directly touches PACT's T2.

- `evaluation_data` = `overall_rating?`, `overall_scores?`, `referred_evaluations`✔
  (`schema/objects/evaluation_data.json`).
- `referred_evaluation` = `datasets?`, `publisher`✔, `created_at`✔, `evaluation_report?`,
  with `at_least_one: [datasets, evaluation_report]`
  (`schema/objects/referred_evaluation.json`).
- `evaluation_report` = `overall_scores?` + `metrics?`, `at_least_one`
  (`schema/objects/evaluation_report.json`).
- `overall_scores` = exactly three optional numbers: `quality_score`, `cost_score`,
  `security_score` (`schema/objects/overall_scores.json`).
- `metric` = `name`✔, `type`✔ (counter/gauge/histogram), `unit_of_measurement`✔ (UCUM),
  `url?`, `data_points`✔ (`schema/objects/metric.json`).
- `evaluation_dataset` = `url`✔, `name`✔, `version?`, `metadata?`.

**OASF can say "this agent scored 0.83 on dataset X, published by Y on date Z". It cannot
say "this agent MUST score ≥ 0.80 on metric `deepeval:answer_relevancy` over these 40
cases before it may be bound."** There is no threshold, no assertion, no pass/fail, no case,
no rubric, no judge. PACT's entire Quality Contract has no home here.

### 4.5 What OASF does NOT cover

- No instructions, no loop, no topology, no memory, no handoffs.
- No capability *predicates* — `Skill`/`Domain` are enumerated tags from a fixed taxonomy,
  not a predicate language. `reasoning >= strong && MMLU > 80 && context >= 128k` (O3.1)
  cannot be expressed.
- No SLOs. `overall_scores.cost_score` is a scalar rating, not a budget.
- `annotations` is `map<string,string>` — **string values only**, in both record, skill,
  domain, and module. PACT extension data cannot round-trip through OASF annotations; it
  must use `Module.data` or `Module.artifact`.
- The one place agent I/O schemas existed — `acp_agent.input`/`.output` as
  `openapi_schema_object` (`schema/objects/acp.json:16-25`) — is deprecated.
- **Reconciliation with the thesis:** `00-THESIS.md:146` treats "OSSA / OASF (AGNTCY)" as
  one row. **They are two unrelated specifications.** See §12.1.

---

## 5. AG-UI

### 5.1 What it standardises

A **streaming event protocol between an agent and a user-facing app**. Transport-agnostic
(SSE/WS/binary). The unit is `RunAgentInput → Observable<BaseEvent>`
(`CLAUDE.md`, "Key Abstractions").

`EventType` — 31 members (`sdks/typescript/packages/core/src/events.ts:12-61`):
`TEXT_MESSAGE_{START,CONTENT,END,CHUNK}`, `TOOL_CALL_{START,ARGS,END,CHUNK,RESULT}`,
`REASONING_{START,END,MESSAGE_START,MESSAGE_CONTENT,MESSAGE_END,MESSAGE_CHUNK,ENCRYPTED_VALUE}`,
`STATE_SNAPSHOT`, `STATE_DELTA` (JSON Patch RFC 6902), `MESSAGES_SNAPSHOT`,
`ACTIVITY_{SNAPSHOT,DELTA}`, `RUN_{STARTED,FINISHED,ERROR}`, `STEP_{STARTED,FINISHED}`,
`RAW`, `CUSTOM`, plus five deprecated `THINKING_*` aliases.

`RunAgentInput` (`sdks/typescript/packages/core/src/types.ts:209-219`): `threadId`, `runId`,
`parentRunId?`, `state`, `messages[]`, **`tools[]`**, `context[]`, `forwardedProps`,
`resume[]`.

Modality coverage is the **best in the corpus**: `TextInputContent`, `ImageInputContent`,
`AudioInputContent`, **`VideoInputContent`**, `DocumentInputContent`, with a
`InputContentSource` discriminated union of data-URI vs URL
(`types.ts:23-72`). AG-UI is the only protocol here with first-class video.

### 5.2 The inversion that matters

`RunAgentInput.tools` flows **client → agent**: the *frontend* declares tools to the agent
(`ToolSchema = {name, description, parameters: JSON Schema, metadata?}`,
`types.ts:186-191`). This is generative-UI / HITL, and it is the opposite direction from
MCP. `InterruptSchema` (`types.ts:193-201`) with `responseSchema` and `expiresAt` +
`ResumeEntrySchema` (`types.ts:203-207`) is a clean typed HITL interrupt model — worth
copying into PACT's loop IR.

### 5.3 Extension mechanism / version story

`BaseEventSchema` is a Zod `.passthrough()` object (`events.ts:63-69`) — unknown fields
survive, but there is **no key-naming convention**, no reserved prefix, no registry.
`RAW` and `CUSTOM` are the sanctioned escape hatches. There is no protocol version field on
`BaseEvent` at all; versioning is by npm package semver. Deprecations are JSDoc `@deprecated`
with "Will be removed in 1.0.0" (`events.ts:22-41`) — i.e. **pre-1.0**.

### 5.4 What AG-UI does NOT cover

Everything about definition. No card, no manifest, no discovery, no tool registry, no
model, no eval. Its own docs place it as the third leg beside MCP and A2A
(`docs/agentic-protocols.mdx:16-21`).

---

## 6. agents.md

**There is no schema.** *"Are there required fields? — No. AGENTS.md is just standard
Markdown. Use any headings you like; the agent simply parses the text you provide."*
(`components/FAQSection.tsx:13-15`).

The only normative rules I could find in-repo, and they are on a marketing site, not in a
spec document:
1. The file is named `AGENTS.md`.
2. Nested files are allowed in monorepos (`components/HowToUseSection.tsx:35`).
3. **"The closest AGENTS.md to the edited file wins; explicit user chat prompts override
   everything"** (`components/FAQSection.tsx:17-20`).
4. Listed commands will be executed by the agent (`FAQSection.tsx:21-24`).

No version field, no front-matter, no extension mechanism. Last commit 2026-03-12.

**Relevance to PACT is real but narrow:** rule 3 is a *scoping and precedence rule for
instruction files* — exactly the semantics PACT's Expansion Rule needs for
`instructions.md` at nested levels of a workspace tree. PACT should be able to **emit**
`AGENTS.md` (a rendered projection of resolved instructions) so that a PACT workspace is
legible to Claude Code / Codex / Cursor with no adapter. It must never be an *input*
format, because it has no machine-readable structure at all.

---

## 7. OpenTelemetry `gen_ai` semantic conventions

### 7.1 **They moved out of this repo.**

`docs/gen-ai/README.md:6-11`: *"GenAI semantic conventions have moved to the OpenTelemetry
GenAI semantic conventions repository (`semantic-conventions-genai`). This page has moved
and is no longer maintained in this repository."* Confirmed in `CHANGELOG.md:49-53`:
`model/gen-ai/`, `model/openai/`, and `model/mcp/` are deprecated here.

**All eleven `docs/gen-ai/*.md` files are 11-line stubs.** The corpus does **not** contain
`semantic-conventions-genai`. What survives locally is the deprecated-but-complete model
under `model/gen-ai/deprecated/` (3,183 lines incl. `model/mcp/deprecated/`) — deprecated in
*this* repo purely because of the move, with content intact. Everything below is read from
those files and is accurate as of `v1.43.0`; **any figure PACT pins must be re-verified
against `semantic-conventions-genai` before it is normative.** This is an open question, not
a finding.

### 7.2 The attribute registry (60 `gen_ai.*` attributes)

`model/gen-ai/deprecated/registry-deprecated.yaml`. The ones that matter to PACT:

| Attribute | Line | Note |
|---|---|---|
| `gen_ai.operation.name` | 914-961 | Closed enum: `chat`, `generate_content`, `text_completion`, `embeddings`, `retrieval`, **`create_agent`**, **`invoke_agent`**, **`execute_tool`**, **`invoke_workflow`** |
| `gen_ai.agent.{id,name,description,version}` | 688-735 | |
| `gen_ai.workflow.name` | 1295 | *"name of the first chain in LangChain OR name of the crew in CrewAI"* |
| `gen_ai.conversation.id` | 676 | |
| `gen_ai.tool.{name,call.id,description,type,call.arguments,call.result}` | 736-845 | `tool.type` ∈ `function` \| `extension` \| `datastore` (773-790) |
| `gen_ai.tool.definitions` | 846-896 | `type: any`; MUST follow the Tool Definitions JSON Schema; `opt_in` everywhere |
| `gen_ai.system_instructions` | 1069 | `opt_in` |
| `gen_ai.input.messages` / `gen_ai.output.messages` | 1121 / 1184 | `opt_in` |
| `gen_ai.output.type` | 966-1005 | `text` \| `json` \| `image` \| `speech` — **no video, no computer-use** |
| `gen_ai.usage.{input,output}_tokens`, `usage.cache_read.input_tokens`, `usage.cache_creation.input_tokens`, `usage.reasoning.output_tokens` | 577-647 | |
| `gen_ai.response.time_to_first_chunk` | 562 | |
| **`gen_ai.evaluation.{name,score.value,score.label,explanation}`** | 1230-1282 | see §7.4 |
| `gen_ai.prompt.name` | 1283 | e.g. `"analyze-code"` |
| `gen_ai.data_source.id`, `gen_ai.retrieval.{documents,query.text}` | 897, 1019-1068 | |

### 7.3 Spans

`model/gen-ai/deprecated/spans-deprecated.yaml`:

| Span group | Line | Kind | Span name |
|---|---|---|---|
| `span.gen_ai.create_agent.client` | 370 | CLIENT | `create_agent {gen_ai.agent.name}` |
| `span.gen_ai.invoke_agent.client` | 531 | CLIENT | `invoke_agent {gen_ai.agent.name}` — *remote* agent |
| `span.gen_ai.invoke_agent.internal` | 566 | INTERNAL | same name — *in-process* agent (LangChain, CrewAI) |
| `span.gen_ai.execute_tool.internal` | 597 | INTERNAL | `execute_tool {gen_ai.tool.name}` |
| `span.gen_ai.invoke_workflow.internal` | 703 | INTERNAL | `invoke_workflow {gen_ai.workflow.name}` |
| `span.gen_ai.inference.client` | 135 | CLIENT | |
| `span.gen_ai.retrieval.client`, `.embeddings.client` | 331, 291 | CLIENT | |

`invoke_workflow` has an explicit *don't-double-report* rule: emit it only when the
instrumentation can reliably tell a workflow from an agent; ADK-style workflow-agents
SHOULD NOT emit it, CrewAI crews SHOULD (`spans-deprecated.yaml:723-731`).
This is directly relevant to PACT's harness lowering: **PACT knows statically whether a
node is a team or an agent, so it can emit `invoke_workflow` correctly where framework
instrumentations cannot.**

### 7.4 The evaluation event

`event.gen_ai.evaluation.result` (`model/gen-ai/deprecated/events-deprecated.yaml:376-415`):
`gen_ai.evaluation.name`✔, `score.value?` (double), `score.label?` (low-cardinality string,
examples include `"pass"`/`"fail"`), `explanation?`, `gen_ai.response.id?`, `error.type?`.
*"SHOULD be parented to GenAI operation span being evaluated when possible."*

**This is the only place in the whole corpus where an eval result has a standard shape.**
It is a *result* event with no threshold and no verdict-vs-baseline; PACT's
`PORTABILITY: FAIL — answer_relevancy 0.61 < 0.80` (D11) fits `name` + `score.value` +
`score.label:"fail"` + `explanation`, but the *threshold* has no attribute. See §10.

### 7.5 Metrics

`model/gen-ai/deprecated/metrics-deprecated.yaml`: `gen_ai.client.token.usage` (54),
`gen_ai.client.operation.duration` (74), `gen_ai.client.operation.time_to_first_chunk` (99),
`gen_ai.client.operation.time_per_output_chunk` (118), `gen_ai.server.request.duration` (138),
`gen_ai.server.time_per_output_token` (155), `gen_ai.server.time_to_first_token` (172).

**PACT's TTFT/TPOT SLOs (O4.2) map exactly onto the last three.** There is no cost metric
and no E2E-latency metric distinct from `operation.duration`.

### 7.6 MCP conventions (also moved)

`model/mcp/deprecated/registry-deprecated.yaml`: `mcp.method.name` (13),
`mcp.session.id` (151), `mcp.resource.uri` (163), `mcp.protocol.version` (178);
spans `span.mcp.client` (21) / `span.mcp.server` (74); four metrics for client/server
operation and session duration.

### 7.7 What OTel does NOT cover

It is an *observation* schema. No definition, no thresholds, no contract, no policy, no
capability requirement. Modality vocabulary (`gen_ai.output.type`) is narrower than D16.

---

## 8. CloudEvents

**v1.0**, stable and frozen; `cloudevents/v2.md` is a "consideration list" with *"no
guarantee as to when, or if, a v2 might happen"* (`cloudevents/v2.md:5-9`).

REQUIRED context attributes: `id`, `source` (URI-reference), `specversion` (`"1.0"`),
`type` (`cloudevents/spec.md:281-360`). Optional: `datacontenttype`, `dataschema`,
`subject`, `time`.

**Attribute-name constraints are severe and PACT must respect them if it emits
CloudEvents:** lower-case `[a-z0-9]` ASCII only, SHOULD start with a letter, **SHOULD NOT
exceed 20 characters**, MUST NOT be `data` (`cloudevents/spec.md:200-207`). No dots, no
dashes, no underscores. Type system is `Boolean | Integer(int32) | String | Binary |
URI | URI-reference | Timestamp` (`spec.md:211-247`).

Extension mechanism: any number of additional context attributes under the same naming and
type rules, with a documented-extensions list at `cloudevents/extensions/README.md`
(`spec.md:487-515`). Existing extensions include `distributedtracing`, `correlation`,
`dataclassification`, `dataref`, `deprecation`, `sequence`, `severity`, `partitioning`,
`recordedtime`, `expirytime`, `verifiability`.

**Does NOT cover:** anything about agents. It is an envelope.

**Where PACT should use it:** the *feedback/learning* event stream — trace promotion
(AC-4.4), learning-candidate accepted/rejected (AC-5.4/5.5), portability verdicts. The
in-repo gap analysis already names "feedback events" as missing
(`00-THESIS.md:616-618`). CloudEvents is the correct envelope and costs PACT nothing
because the 20-char attribute limit only binds *context attributes*, not `data`.

---

## 9. Serverless Workflow (CNCF)

**DSL 1.0.3** (`schema/workflow.yaml:1`, `$id: .../schemas/1.0.3/workflow.yaml`),
JSON Schema draft 2020-12. Root: `document`✔, `input`, `use`, `do`✔, `timeout`, `output`,
`schedule`, `evaluate`.

`document`✔ = `dsl`✔ (semver), `namespace`✔, `name`✔, `version`✔ (semver), `title`,
`summary` (Markdown), `tags`, `metadata` (`schema/workflow.yaml:7-51`).
`use` = `authentications`, `errors`, `extensions`, `functions`, `retries`, `secrets`,
`timeouts`, `catalogs`.

**Closed task set (12):** `call`, `do`, `fork`, `emit`, `for`, `listen`, `raise`, `run`,
`set`, `switch`, `try`, `wait` (`$defs.task`).

**Extension mechanism (the best structural one in the corpus):** `$defs.extension` =
`extend`✔ (which task kind, or `all`), `when` (runtime expression), `before` (taskList),
`after` (taskList). This is aspect-oriented composition over a closed task set — an
extension cannot invent a new task kind, only wrap existing ones. That is exactly the
property that keeps a spec implementable (thesis R8).

### 9.1 It already speaks A2A and MCP

`schema/workflow.yaml:455-490` — `call: a2a` with `with.agentCard` (externalResource),
`with.server` (endpoint), `with.method` (enum), `with.parameters`.
`schema/workflow.yaml:493-560` — `call: mcp` with `with.protocolVersion`,
`with.method` (enum of `tools/list`, `tools/call`, `prompts/*`, `resources/*`),
`with.parameters`, `with.timeout`, `with.transport.{http,stdio}`.

**But both are already stale.** The A2A method enum (`:482`) is the **v0.3 JSON-RPC method
names** (`message/send`, `tasks/pushNotificationConfig/set`,
`agent/getAuthenticatedExtendedCard`) — A2A v1.0 renamed the surface and moved to
`supportedInterfaces`/protocol bindings. The MCP `protocolVersion` **defaults to
`2025-06-18`** (`:512`), two revisions behind, and predates the `2026-07-28` handshake
removal entirely. This is concrete evidence for thesis R2 (adapter rot) applied to
*specs*, not just adapters.

### 9.2 What it does NOT cover

`grep -in "agent|llm|AI" schema/workflow.yaml` returns only the A2A call task. There is no
agent, no model, no instructions, no tool-set, no memory, no eval, no capability, no
non-deterministic control flow. It is a deterministic orchestrator that can *call* agents.

---

## 10. OAM — Open Application Model

**Dormant.** Latest release v0.3.0; last repo commit **2024-12-24**; working draft v0.3.1
(`README.md:38`). Model: `Application` → `components[]` → `{name, type, properties,
traits[], scopes{}}` (`7.application.md:29-45`), with `ComponentDefinition`
(`3.component_model.md:19-32`), `TraitDefinition`, `WorkloadDefinition`, `ScopeDefinition`.

Three patterns are directly reusable by PACT and I recommend all three:

1. **Definition-registry indirection.** `component.type` is a *name* resolved against a
   registered `ComponentDefinition` whose `schematic` "expose[s] a JSON schema or equivalent
   parameter list" (`3.component_model.md:47-51`). This is exactly PACT's G-5
   ("tools, skills, memory, retrievers, guardrails, hooks, channels, schedules, sandboxes
   are all Resources under one registration/scoping model") with a proven prior art.
2. **Traits as discretionary operational overlays** applied by a different role than the one
   who authored the component (`6.traits.md:3-7`). PACT's policies/SLOs/guardrails are
   traits in this sense — authored by an ops persona, attached without touching the agent.
3. **`conflictsWith`** on `TraitDefinition` (`6.traits.md:33`) — a declared incompatibility
   between overlays, checked before deployment. PACT has no analogue and needs one
   (e.g. `autonomy: full` conflicts with `approval-gate: every-tool-call`).

**Does NOT cover:** anything AI. No agent, no model, no eval. And it is not maintained.

---

## 11. (b) The exact mapping surface

### 11.1 PACT → **A2A Agent Card**

Target: `specification/a2a.proto:362-399`. Direction: emit-only for a PACT agent that is
served over A2A. Fields with no source in PACT are marked `∅`; fields of PACT with no
A2A target go to §12 (loss report).

| A2A field | PACT source | Class |
|---|---|---|
| `name` | `metadata.name` (or `identity.name`) | exact |
| `description` | `metadata.description` | exact |
| `version` | `metadata.version` | exact |
| `provider.{organization,url}` | `metadata.owner` | exact if owner carries both |
| `documentationUrl` | `metadata.docs` | exact |
| `iconUrl` | `metadata.icon` | exact |
| `supportedInterfaces[]` | **runtime-supplied**, not spec-supplied: `{url, protocolBinding, protocolVersion, tenant?}` | scaffolded — PACT declares *bindings offered*; the serving runtime fills `url` |
| `capabilities.streaming` | `contract.interface.streaming` | exact |
| `capabilities.pushNotifications` | `contract.interface.async` / runtime capability | scaffolded |
| `capabilities.extendedAgentCard` | policy: whether the full contract is auth-gated | scaffolded |
| `capabilities.extensions[]` | **PACT's own hook** — see below | exact |
| `securitySchemes` / `securityRequirements` | `policy.auth` | partial (A2A's set is OpenAPI-3.2-shaped; PACT policies that are not APIKey/HTTP/OAuth2/OIDC/mTLS are lossy) |
| `defaultInputModes[]` / `defaultOutputModes[]` | **media types derived from** `contract.interface.io` content types | **lossy — the JSON Schema is dropped, only the media type survives** |
| `skills[].id` | PACT skill id, or `agent-tool:<name>` / `handoff:<name>` facade ids (existing Bud convention) | exact |
| `skills[].name`, `.description` | skill name/description | exact |
| `skills[].tags[]` | capability tags + PACT `capabilities` names (Bud already does this) | exact |
| `skills[].examples[]` | **eval case inputs, projected** | scaffolded |
| `skills[].inputModes/outputModes` | per-skill content types | lossy (same schema loss) |
| `skills[].securityRequirements[]` | per-skill policy | partial |
| `signatures[]` | PACT signing pipeline over the JCS canonical form | exact |

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

`AgentExtension.params` is `google.protobuf.Struct` (`specification/a2a.proto:432`) — a
**standard** field, so it survives proto round-trip and JCS canonicalisation intact. The
"data-only extension" category is explicitly sanctioned
(`docs/topics/extensions.md:26-29`). Version the URI, and mint a new URI on any breaking
change (`docs/specification.md:1139-1141`).

**Do not** put PACT data in a top-level `metadata` key on the card. See §12.3.

### 11.2 PACT → **MCP tool / prompt / resource**

PACT does not *become* MCP; PACT **consumes** MCP as the tool edge (NG3) and **exposes**
PACT resources over MCP where a PACT workspace is served to an MCP client.

| MCP object | PACT source | Class |
|---|---|---|
| `Tool.name` | `tools[].name`, namespaced | exact |
| `Tool.title` | `tools[].title` | exact |
| `Tool.description` | `tools[].description` | exact |
| `Tool.inputSchema` | `tools[].input` (must be `type:"object"` at root — `schema/draft/schema.ts:1985`) | exact where PACT's input is an object; **lossy for non-object roots** |
| `Tool.outputSchema` | `tools[].output` | exact in draft (any JSON Schema); **restricted to `type:"object"` in 2025-11-25** (`schema/2025-11-25/schema.ts:1277-1285`) |
| `Tool.annotations.{readOnly,destructive,idempotent,openWorld}Hint` | `tools[].effects` | **degraded — MCP calls these hints; PACT treats them as policy inputs** |
| `Tool.icons` | `tools[].icon` | exact |
| `Tool._meta["dev.pact/…"]` | tool-level PACT extras (cost model, SLO, approval class, capability requirement) | exact, but **advisory only** |
| `Prompt.name/.title/.description` | `skills[].name/.title/.description` | exact |
| `Prompt.arguments[]` | skill parameters | **lossy — `PromptArgument` is `{name,title,description,required}`; no type, no schema** (`schema/2025-11-25/schema.ts:1006-1020`) |
| `Resource.uri/.name/.mimeType/.size` | workspace files: `instructions.md`, `evals/`, `models/catalog.yaml`, `.pact/canonical.json` | exact |
| `ResourceTemplate.uriTemplate` | parameterised resource families | exact |
| `DiscoverResult.instructions` (draft) | workspace-level instructions projection | exact — and PACT should **consume** this from remote MCP servers as an instruction fragment with provenance |

**No home in MCP:** the agent, the model, the loop, the topology, evals, SLOs, capability
predicates, memory, variants. All of it. `_meta` will carry it, but `_meta` is by definition
ignorable — *"Implementations MUST NOT make assumptions about values at these keys"*
(`docs/specification/2025-11-25/basic/index.mdx:195-197`).

**Key-naming compatibility, actionable:** MCP `_meta` keys must be `prefix/name` with
reverse-DNS prefixes, and any prefix whose *second label* is `mcp` or
`modelcontextprotocol` is reserved (`index.mdx:201-216`). `dev.pact/` is legal
(second label `pact`). A bare `x-` key from the thesis's O1.4 is **not** a legal `_meta`
key and would have to be renamed at the boundary — a silent transform PACT's honesty
invariant (T7) forbids. See design implication D-3.

### 11.3 PACT → **OASF Record**

| OASF field | PACT source | Class |
|---|---|---|
| `name` | `metadata.name` | exact |
| `version` | `metadata.version` | exact |
| `schema_version` | OASF schema version (e.g. `1.2.0`) — **not** `pact.dev/v1` | exact |
| `description` | `metadata.description` | exact |
| `authors[]` | `metadata.owner`, as `name <email>` | exact |
| `created_at` | RFC 3339 build timestamp | exact |
| `annotations{string→string}` | `metadata.labels`; PACT digest as `dev.pact/digest` | **partial — string values only** |
| `skills[]` | mapped from PACT capabilities onto the closed OASF taxonomy (`schema/skills/`) by uid | **lossy — a PACT capability with no taxonomy entry is dropped or must extend the taxonomy upstream** |
| `domains[]` | `metadata.domain` mapped onto `schema/domains/` | lossy, same reason |
| `locators[]` | `{type: source_code\|container_image\|package, urls:[…]}` for the PACT tree / OCI artifact | exact |
| `modules[].name = "dev.pact.spec"`, `.data` | small PACT summary as `Struct` | exact |
| `modules[].artifact` | `{artifact_type: "application/vnd.pact.canonical.v1+json", media_type, size, digest, urls, json?}` pointing at `canonical.json` | **exact — this is the load-bearing mapping** |
| `modules[] name="a2a"` | the emitted Agent Card, via `module.artifact` (inline `card_data` is deprecated) | exact |
| `modules[] name="mcp"` | required MCP servers → `mcp_data.connections[]` (`schema/objects/mcp_server_connection.json`) | exact for stdio/http/sse |
| `modules[] name="evaluation"` | **only post-hoc results**: `referred_evaluations[].evaluation_report.metrics[]` + `overall_scores` | **lossy — thresholds, cases, rubrics, judges have no field** |
| `modules[] name="observability"` | trace endpoint declaration | partial |

**Reconciliation with the thesis:** `00-THESIS.md:146` says the OASF/OSSA mapping "already
yields a loss report." That is true of **OSSA** in the runtime (§12.1); an **OASF** mapping
does not exist in the runtime yet, and the loss profile above is different — OASF loses the
*taxonomy-unmapped capabilities* and *all eval specification*, whereas OSSA loses
*permissions, hooks, and run-state*.

### 11.4 PACT → **OTel `gen_ai` spans**

For harness lowering, PACT owns the loop, so PACT — not the framework — is the correct
emitter. Recommended emission contract:

| PACT construct | Span / event | Attributes |
|---|---|---|
| Team / topology run | `invoke_workflow` INTERNAL, name `invoke_workflow {team}` | `gen_ai.operation.name=invoke_workflow`, `gen_ai.workflow.name`, `error.type?` (`spans-deprecated.yaml:703-746`) |
| Agent run (in-process adapter) | `invoke_agent` INTERNAL | `gen_ai.provider.name`✔, `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.agent.{id,name,description,version}`, `gen_ai.conversation.id` (`:566-596`) |
| Agent run (remote / A2A) | `invoke_agent` CLIENT | same + `server.address`, `server.port` (`:531-565`) |
| Resolver binding an agent to a substrate | `create_agent` CLIENT | `gen_ai.agent.*`, `gen_ai.request.model`, `gen_ai.system_instructions` (opt-in) (`:370-418`) |
| Model call | `gen_ai.inference.client` | request params, `gen_ai.usage.*`, `gen_ai.response.finish_reasons` |
| Tool call | `execute_tool` INTERNAL, name `execute_tool {tool}` | `gen_ai.tool.name`✔, `.call.id`, `.description`, `.type` ∈ function/extension/datastore (`:597-649`) |
| Retriever / memory read | `retrieval` CLIENT | `gen_ai.data_source.id`, `gen_ai.retrieval.{query.text,documents}` |
| Eval metric result | `gen_ai.evaluation.result` **event**, parented to the evaluated span | `gen_ai.evaluation.name`✔, `.score.value`, `.score.label` ∈ pass/fail, `.explanation` (`events-deprecated.yaml:376-415`) |
| SLO measurement | metrics | `gen_ai.client.operation.time_to_first_chunk`, `…time_per_output_chunk`, `…operation.duration`, `gen_ai.client.token.usage` |
| PACT strategy identity | `_` no standard attribute | → `dev.pact.*` custom attributes, see §12 |

`gen_ai.tool.definitions` (`registry-deprecated.yaml:846-896`) is the standard place for
PACT's *exposed tool set* — which is a Strategy artefact — and it is opt-in and
schema-constrained, so PACT can emit its curated exposure set there and make context-
discipline experiments (thesis §7.3 item 4) measurable from traces alone.

---

## 12. (c) The loss report — fields with **no home** anywhere

Grouped by PACT layer. "No home" = I could find no field, attribute, or sanctioned
extension slot in any of the eleven protocols; the value would have to travel in a
vendor-prefixed bag (`AgentExtension.params`, MCP `_meta`, OASF `Module.data`,
CloudEvents extension attributes) that consumers are permitted to ignore.

### Contract layer

| PACT field | Nearest thing | Verdict |
|---|---|---|
| **I/O JSON Schema** (`contract.interface.io`) | A2A: media types only; MCP: tool schemas only, not agent-level; OASF: `acp_agent.input/output` (**deprecated**) | **NO HOME.** The single most important loss. |
| **Capability predicates** (`reasoning >= strong && MMLU > 80 && context >= 128k`) | OASF `skills[]` = closed enum tags; A2A `skills[].tags` = free strings | **NO HOME.** No protocol has a predicate language. |
| **Eval suite** (cases, datasets, metrics, thresholds, rubrics, judge config, deterministic-first ordering) | OASF `evaluation` module carries *results*; OTel carries *result events* | **NO HOME** for the specification. Results have a home; the contract does not. |
| **Pass thresholds / ε for CTS** | — | **NO HOME.** `gen_ai.evaluation.score.value` has no companion "required" attribute. |
| **SLOs** (TTFT/TPOT/E2E/cost/throughput targets, percentiles) | OTel has the *metrics*; OASF has `overall_scores.cost_score` (a rating) | **NO HOME** for the *target*. Measurements have a home. |
| **Budget caps / concurrency limits** | Zed ACP `Cost{amount,currency}` is an actual, not a cap | **NO HOME.** |
| **Autonomy level / blast-radius class (D23)** | Zed ACP `PermissionOptionKind` is a runtime prompt, not a declared level | **NO HOME.** |
| **Data-handling / redaction policy** | CloudEvents `dataclassification` extension (event-level only) | **NO HOME** at agent level. |
| **Modality: computer-use, video** | A2A `Part.media_type` can carry both; MCP cannot; `gen_ai.output.type` cannot | **PARTIAL** — expressible only in A2A, and only as an opaque media type. |

### Strategy layer

| PACT field | Nearest thing | Verdict |
|---|---|---|
| **Instructions / system prompt** | `gen_ai.system_instructions` (opt-in trace attribute); MCP draft `DiscoverResult.instructions` (server-level); AGENTS.md (unstructured prose) | **NO HOME** as a definition field. |
| **Loop program** (ReAct / Plan-Execute / Reflexion / ToT / self-consistency / CodeAct) | Serverless Workflow `do` is deterministic only | **NO HOME.** |
| **Topology** (supervisor, swarm, debate, blackboard, market) | `gen_ai.workflow.name` is a *label*; A2A gives you N unrelated cards | **NO HOME.** |
| **Variants** (per-tier strategies) + variant selection | — | **NO HOME.** |
| **Tool *exposure set* and curation** (vs the tools that exist) | `gen_ai.tool.definitions` (trace-only, opt-in) | **NO HOME** as a definition field. |
| **Skill exposure and ordering** | — | **NO HOME.** |
| **Memory strategy** | — | **NO HOME.** No protocol in the corpus has a memory concept. |
| **Retry / verification strategy** | Serverless Workflow `use.retries` (deterministic HTTP retries) | **NO HOME** for semantic verification. |
| **Model parameters** | `gen_ai.request.{temperature,top_p,top_k,…}` (trace attributes) | **NO HOME** as a definition field. |
| **Model requirement / model catalogue + benchmark provenance** | OASF `language_model` module (identity only) | **NO HOME.** |

### Meta layer

| PACT field | Nearest thing | Verdict |
|---|---|---|
| **Fidelity / conformance level (L0–L4)** | — | **NO HOME.** |
| **Adapter capability lattice** (`native\|emulated\|degraded\|unsupported` per feature) | — | **NO HOME.** |
| **Portability Report / lockfile (`pact.lock`)** | — | **NO HOME.** |
| **Learning lineage** (candidate → verdict → promotion → signature) | OASF `v1alpha2` had `previous_record_cid`; **v1 dropped it** | **REGRESSED** — the one field that fit was removed. |
| **Loss report itself** (`ExportReport`) | — | **NO HOME.** The honesty artefact is unrepresentable in every protocol PACT exports to, which is itself the argument for PACT. |

### 12.1 Reconciliation with the runtime — three corrections I must state explicitly

**(1) OSSA ≠ OASF.** `00-THESIS.md:146` puts "OSSA / OASF (AGNTCY)" in one row. They are
different specs:

- **OSSA** = Open Standard Agents, `https://openstandardagents.org/`
  (`bud-agentic-runtime/agentic-pattern-and-dx-evaluation.md:27`), apiVersion
  **`ossa/v0.5.0`** (`bud-agentic-runtime/src/manifest_compiler.rs:3282-3285,3431`).
  Kinds `Agent`, `Task`, `Workflow`. Shape (from the runtime's own emitter,
  `manifest_compiler.rs:3430-3470`): `spec.role` (= instructions), `spec.llm.{provider,
  model}`, `spec.tools[]`, `spec.autonomy.level`, `spec.a2a.{enabled,protocols}`,
  `spec.capabilities`, `spec.output.schema`, `spec.guardrails`, `extensions.mcp.servers`,
  and everything Bud-native under `spec.x-bud`.
- **OASF** = AGNTCY Open Agentic Schema Framework, `Record`/`Skill`/`Domain`/`Module`/
  `Locator`, schema `1.2.0-dev`.

The runtime implements **OSSA** import/export (`import_openstandardagents`,
`export_openstandardagents_with_report`, `bud ossa`, `bud registry import-ossa` —
`registry-and-portability.md:1140-1156`). It implements **nothing** for OASF.
This is not a contradiction of the runtime, it is a naming error in the thesis, and the
successor documents must fix it or the mapping work will be scoped wrong.

**Notably, OSSA is a *better* target than OASF for PACT's Contract layer** — it has
`spec.output.schema`, `spec.guardrails`, `spec.autonomy.level`, and `spec.capabilities`,
none of which OASF has. But it still has no evals, no SLOs, no loop, no topology, no
variants (per the runtime's own loss table, `registry-and-portability.md:1160-1172`:
permissions → `spec.safety` **lossy**, Goose hooks **lossy**, workflow graph **partial**,
RunState **not exported**).

**(2) Bud's emitted Agent Card contains a non-standard top-level `metadata` key.**
`bud-agentic-runtime/src/agent_registry_card.rs:205-209` emits
`"metadata": {"runtime":"bud","gooseBacked":…,"bud":{…}}`, and
`registry-and-portability.md:1025` documents `metadata.bud.*` as the carrier for registry
identity, agent-tool and handoff bindings. **`AgentCard` has no `metadata` field**
(`specification/a2a.proto:362-399`, "Next ID: 20"). Per §5.7 consumers SHOULD ignore it, so
today it is a *silent* loss rather than a rejection — but it is also incompatible with card
signing (§2.3), which the runtime does not yet do. I am flagging this as a divergence from
the spec, not asserting the runtime is broken: it works against tolerant consumers.
**PACT should not inherit this pattern.** Migration path: move `metadata.bud.*` into an
`AgentExtension` with `uri: https://pact.dev/extensions/bud/v1` and keep `metadata` for one
release as a deprecated mirror.

**(3) "Goose ACP" is Zed's Agent Client Protocol v1, not IBM ACP and not AGNTCY ACP.**
`registry-and-portability.md:1149` mentions `Goose ACP _bud/unstable/registry/import/a2a`,
and `registry.search(protocol: "bud"|"goose"|"a2a"|"acp")` at `:819`. Goose depends on
`agent-client-protocol = "1.0"` / `agent-client-protocol-schema = "1.1"`
(`/home/bud/ditto/gaia-ai-runtime/goose/Cargo.toml:29-31`). Zed's current schema is **v2**
(`schema/v2/meta.json`, `version: 2`), with `session/list`, `session/resume`,
`session/delete`, `session/close`, `session/set_config_option`, and `elicitation/*` — none
of which exist in v1. **[INFERRED]** — I verified Goose's declared dependency versions and
that the Zed repo ships both v1 and v2 schemas; I did not diff v1 against v2 method-by-method.

**(4) Everything else in the runtime is consistent with what I read.**
`registry-and-portability.md:972-980` correctly describes A2A v1.0's
`supportedInterfaces`, per-interface `protocolVersion`, opaque `tenant`, and the three
bindings; `:1035-1040` correctly requires `id`/`name`/`description`/non-empty `tags` on
every emitted skill (matching `specification/a2a.proto:436-444`); `:1023` correctly
withholds `capabilities.pushNotifications` until the server owns the standard push-config
operations. No contradiction found.

---

## 13. (d) Could any of these be PACT's wire format?

**Verdict: no — and the failure is structural, not cosmetic.** PACT must be a strict
superset of `bud.dev/v1` (D3). `bud.dev/v1` already carries `spec.instructions`,
`spec.model`, `spec.tools`, `spec.skills`, `spec.permissions`, `spec.handoffs`,
`spec.output.schema`, `spec.guardrails`, `spec.runtime.mcpServers`. Scored against that
bar plus the PACT additions:

| Candidate | Can express instructions? | Model? | I/O schema? | Evals? | Loop? | Topology? | Verdict |
|---|---|---|---|---|---|---|---|
| A2A AgentCard | no | no | no | no | no | no | **Reject.** Endpoint descriptor. |
| MCP (any object) | server-level only (draft) | no | tool-level only | no | no | no | **Reject.** Zero agent concept. |
| MCP registry `server.json` | no | no | no | no | no | no | **Reject.** Package manifest; in preview. |
| OASF Record | no | no | no | results only | no | no | **Reject as document; adopt as envelope** (§13.1). |
| OSSA `ossa/v0.5.0` | `spec.role` ✔ | `spec.llm` ✔ | `spec.output.schema` ✔ (output only) | no | no | `kind: Workflow`, partial | **Reject.** Closest of all, still ~60% short; runtime's own table calls the rest lossy. |
| Zed ACP | no | no | no | no | no | no | **Reject.** Session protocol. |
| AG-UI | no | no | no | no | no | no | **Reject.** Pre-1.0 event stream. |
| agents.md | prose | no | no | no | no | no | **Reject as input; emit as output.** |
| Serverless Workflow 1.0.3 | no | no | `input`/`output` schemas ✔ | no | deterministic only | task graph, deterministic | **Reject as document; steal the extension mechanism** (§13.3). |
| CloudEvents 1.0 | no | no | `dataschema` ✔ | no | no | no | **Reject as document; adopt as event envelope** (§13.2). |
| OAM v0.3.0 | no | no | schematic ✔ | no | no | component graph | **Reject.** Dormant, non-AI. |

The deeper reason: every candidate models **one edge** of the agent (its callers, its
tools, its catalogue entry, its traces, its deployment). PACT models the agent's
**interior** — and the interior is precisely what none of them has a field for
(see the entire §12). Adopting any of them as the document would force PACT's core
(evals, SLOs, loop, topology, variants, capability predicates) into a
vendor-extension bag that the standard explicitly permits consumers to ignore. That
violates T7 (structural honesty) at the format level.

### 13.1 What PACT **should** adopt: three envelopes and one naming rule

1. **OASF Record as the distribution/registry envelope.** `Module.artifact` is an
   OCI-shaped `Descriptor` with `artifact_type`, `digest`, `urls`, and optional inline
   payload (`proto/agntcy/oasf/types/v1/descriptor.proto`), and OASF is explicitly moving
   *toward* artifact-by-reference and away from inlined payloads
   (`schema/objects/a2a_data.json:11-14`). PACT publishes `canonical.json` as
   `artifact_type: application/vnd.pact.canonical.v1+json` inside a
   `dev.pact.spec` module, projects its capabilities onto OASF `skills[]` where the closed
   taxonomy allows, and lets OASF own CID addressing and OCI packaging. **Cost: near
   zero. Benefit: registry interop for free, without OASF owning any semantics.**
   Air-gap check (D17): OASF is a schema and an OCI artifact type — no hosted service
   required. ✅
2. **CloudEvents 1.0 as the event envelope** for traces-to-evals promotion, learning
   candidate accept/reject, and portability verdicts. Constraint to respect: context
   attribute names are `[a-z0-9]` only, ≤20 chars recommended, `data` forbidden
   (`cloudevents/spec.md:200-207`) — so PACT-specific fields go in `data` with a
   `dataschema` URI, not in context attributes.
3. **A2A Agent Card as the discovery projection**, with all PACT content in one
   versioned `AgentExtension.params` (§11.1).
4. **Reverse-DNS extension keys, not bare `x-`.** MCP `_meta` requires
   `prefix/name` with reverse-DNS prefixes (`index.mdx:201-216`); MCP extension
   identifiers require the same with a *mandatory* prefix
   (`docs/extensions/overview.mdx:9`); A2A extensions are URIs
   (`specification/a2a.proto:424-426`); OASF module names are "fully qualified"
   (`module.proto:20-22`). **Only `x-` is unique to PACT, and it is illegal in three of
   the four.** Adopting `dev.pact/<name>` (or the URI `https://pact.dev/ext/<name>/v1`)
   makes extension keys pass through every boundary unrenamed — which is what O1.4's
   round-trip requirement actually demands.

### 13.2 What PACT should **steal** structurally

- **Serverless Workflow's `extension` object** (`schema/workflow.yaml`, `$defs.extension`):
  `extend` (which node kind, or `all`) + `when` (guard) + `before`/`after` (task lists).
  An extension may wrap but never invent a node kind. This is the mechanism that lets a
  closed core (12 task kinds) stay closed while remaining extensible — exactly thesis R8's
  requirement, and strictly better than "add a new field."
- **Zed ACP's open-enum convention**: `_`-prefixed values are implementation-specific;
  non-`_` unknown values are reserved for future spec versions
  (`schema/v2/schema.json`, `$defs.ToolKind` etc.). This gives PACT forward-compatible
  enum widening for modality, tool kind, loop kind, and node kind with no registry — and it
  makes E-2 ("unknown features are rejected loudly, never ignored") implementable at the
  *value* level, not just the *field* level.
- **OAM's `conflictsWith`** (`6.traits.md:33`) for declaring incompatible policies/traits.
- **agents.md's proximity rule** ("closest file wins") as the normative precedence rule for
  nested `instructions.md` in the Expansion Rule.
- **A2A's per-interface `protocolVersion`** as the model for PACT's adapter-version
  declaration: version the *interface*, not the *server*.

---

## 14. Cross-cutting observations that change PACT's design

### 14.1 Three protocols now have a "Task", and they are not the same task

- **A2A `Task`** — `id`, `context_id`, 8-state lifecycle, `artifacts[]`, `history[]`
  (`specification/a2a.proto:167-208`). Terminal: COMPLETED/FAILED/CANCELED/REJECTED;
  interrupted: INPUT_REQUIRED/AUTH_REQUIRED.
- **MCP `Task`** — 2025-11-25 core (`schema/2025-11-25/schema.ts:1306-1390`), statuses
  `working | input_required | completed | failed | cancelled`; **moved to the
  `io.modelcontextprotocol/tasks` extension in 2026-07-28** (absent from
  `schema/draft/schema.ts`).
- **Zed ACP session** — `StopReason` (`end_turn | max_tokens | max_turn_requests |
  refusal | cancelled`) with an explicit idle `state_update`.

PACT's run-state model must map to all three and cannot inherit any one of them. The union
that covers all three: `{submitted, working, input_required, auth_required, completed,
failed, cancelled, rejected}` plus a separate orthogonal `stop_reason`
{`end_turn`, `max_tokens`, `max_turns`, `refusal`, `cancelled`, `error`}. A2A conflates
"why it stopped" into `TaskState`; Zed separates them, and Zed is right — `refusal` and
`max_tokens` are both "completed" in A2A terms but need different UI and different eval
handling.

### 14.2 The industry is converging on stateless-per-request

MCP `2026-07-28` deletes the `initialize` handshake and puts version + identity +
capabilities in per-request `_meta` (`versioning.mdx:12-13`). A2A already has no handshake:
version is per-interface on the card, per-request via `A2A-Version`. **PACT's runtime
contract should be stateless-per-request too**, with the resolved binding (`pact.lock`
digest) travelling on every call, not established once at session start. This also makes
kill-and-resume (AC-2.6/P-5) simpler: there is no session to reconstruct.

### 14.3 MCP is removing what PACT would have relied on

`sampling` (server asks the client's LLM) is deprecated in `2026-07-28`
(`schema/draft/schema.ts:733-758`). If PACT's harness were to expose its model runtime to
MCP servers via sampling, that path has a 12-month clock on it. `roots` and `logging` are
deprecated too. Design against the `2026-07-28` surface, not `2025-06-18`.

### 14.4 Specs rot exactly like adapters

Serverless Workflow 1.0.3 — a current, actively-maintained CNCF spec — hard-codes A2A
**v0.3** method names and MCP **`2025-06-18`** as its default
(`schema/workflow.yaml:482,512`). This is direct evidence for thesis R2 at the *spec*
level and argues that PACT must never inline another protocol's method enum or version
constant into its schema; it must reference them by URI/version and resolve at build time.

### 14.5 Nobody solved no-code tools

D14 requires a non-technical author to add a custom tool in YAML. **No protocol in the
corpus has a declarative tool-authoring format.** MCP tools are code (no `tool.yaml`
anywhere in `mcp-python-sdk`); OASF `mcp_server_tool` describes a tool that already exists;
A2A skills are descriptions, not implementations; Serverless Workflow's `call`/`run` tasks
come closest — `run.container` (image/command/ports/volumes/env), `call: http`, `call:
openapi`, `call: grpc`, `call: mcp` — and PACT should model its no-code tool kinds on that
closed set, because it is the only proven declarative "call something external" vocabulary
in the corpus.

---

## 15. Open questions (things I could not settle from the local corpus)

1. **`semantic-conventions-genai` is not in the corpus.** Every `gen_ai.*` attribute above
   is read from the *deprecated* mirror in `otel-semconv` at `v1.43.0`. Names, requirement
   levels, and especially the evaluation event may have changed post-move. This must be
   re-verified before PACT pins any attribute name as normative.
2. **MCP registry `server.schema.json`** is referenced as
   `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`
   (`docs/registry/versioning.mdx:13`) and is not in the corpus. I documented `server.json`
   from the doc examples only; the full field set is unverified.
3. **Zed ACP v1 vs v2 delta.** Goose is on v1; I read v2. I did not diff them, so the exact
   migration cost for a PACT↔Goose session surface is unknown.
4. **OASF Record Manifest / OCI packaging spec.** `v1/record.proto:16-18` refers to a
   "Record Manifest specification" that is not in `agntcy-oasf`; it is presumably in
   `agntcy-dir` (present in the corpus, not audited under this brief). Needed before the
   §13.1 recommendation can be implemented.
5. **A2A extension registry.** `docs/topics/extension-and-binding-governance.md` exists but
   I did not read it; whether third-party extension URIs must be registered, and where, is
   unresolved.
6. **Does the runtime's A2A card signing exist yet?** I found `signatures[]` in the spec and
   no signing code path in `agent_registry_card.rs`. If signing is planned, the
   non-standard `metadata` key (§12.1 item 2) becomes a correctness bug rather than a
   tolerance issue.
7. **OSSA v0.5.0 upstream spec.** Not in the corpus. Everything I know about OSSA's shape
   comes from Bud's own emitter and importer, which may not be complete.
