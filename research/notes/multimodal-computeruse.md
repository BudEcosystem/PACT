# PACT Research Stream — Multimodal & Computer Use (D16)

**Author:** research subagent, stream `multimodal-computeruse`
**Date:** 2026-08-07 (supersedes the 2026-07-26 revision of this file)
**Binding inputs read:** `docs/00-THESIS.md`, `docs/01-DECISIONS.md`
(D2, D3, D5, D8, D11, D12, D13, D14, D15, D16, D17, D18, D19, D22, D23, D24, D26, D27)

**Relationship to the previous revision.** The 2026-07-26 pass of this stream produced a
1048-line document. This revision **re-verified its load-bearing claims against source**,
**corrects four of them**, and adds ~20 findings from source the prior pass did not read
(Vercel **Eve**'s attachment staging/hydration, **Goose**'s image and permission model,
**AG-UI**'s capability schema, **SWE-agent**'s YAML browser-tool bundle, **terminal-bench**'s
task format, **promptfoo**'s trajectory assertion family, and quantitative catalogue analysis).
Corrections are marked **[CORRECTION]**; new material is marked **[NEW]**.

**Evidence convention.** Every factual claim carries `path:line` or an exact quote.
**[INFERRED]** = my synthesis, not something I read. **[NEGATIVE]** = absence verified by a
grep that returned zero. Line numbers were re-read on 2026-08-07 unless stated.

Repo roots abbreviated:
- `FW/` = `/home/bud/ditto/agent-inter-op/research/repos/frameworks/`
- `FW2/` = `/home/bud/ditto/agent-inter-op/research/repos/frameworks2/`
- `EV/` = `/home/bud/ditto/agent-inter-op/research/repos/eval/`
- `PR/` = `/home/bud/ditto/agent-inter-op/research/repos/protocols/`
- `RT/` = `/home/bud/ditto/agent-inter-op/research/repos/runtime/`
- `RO/` = `/home/bud/ditto/agent-inter-op/research/repos/routing/`
- `FD/` = `/home/bud/ditto/agent-inter-op/research/repos/filedef/`

---

## 0. Executive summary — the seven things that change the design

1. **[CORRECTION] The industry has *not* converged on a single media-typed part. It has
   converged on the *source union*.** The previous revision claimed convergence on
   `FilePart{mediaType, source}`. That is wrong as a general claim: **AG-UI moved in the
   opposite direction and did so deliberately**, deprecating its generic
   `BinaryInputContent{mime_type, id|url|data}` in favour of per-modality classes
   `ImageInputContent | AudioInputContent | VideoInputContent | DocumentInputContent`, all
   sharing one `InputContentSource` union
   (`PR/ag-ui/sdks/python/ag_ui/core/types.py:106-160`; the deprecation warning naming the
   replacements is at `types.py:152-159`). What **is** universal across all eight systems
   surveyed is the *source* shape: `{inline-bytes | url | provider-file-id | inline-text}`
   plus a MIME type. **PACT's discriminator should be the modality class** (because every
   capability-negotiation surface in the corpus is a per-modality boolean — §2.1), **with
   `mediaType` required and the modality class derived from it by a normative table**, so
   adding a modality is a table entry, not a schema change.

2. **[NEW] Vercel Eve — the system PACT is modelled on — already ships the media
   degradation ladder PACT needs, and PACT should adopt it verbatim.** Inbound attachment
   bytes are written into the sandbox at `/workspace/attachments` and the message part is
   rewritten to a compact ref `eve-sandbox:?path=…&size=…&type=…`
   (`FW/vercel-eve/packages/eve/src/internal/attachments/sandbox-refs.ts:1-62`;
   `harness/attachment-staging.ts:26-30`). At model-call time, bytes are inlined **only**
   for `image/*` ≤ 3 MiB and `application/pdf` ≤ 20 MiB
   (`attachment-staging.ts:45,51,266-274`); everything else becomes a **text part naming
   the file path** so the agent reads it with its ordinary filesystem tools:

   > "only the shapes every major provider supports natively qualify for byte inlining.
   > Everything else — raw documents, archives, source code, oversized images/PDFs — reaches
   > the model as a text reference so the agent's filesystem tools do the reading."
   > — `attachment-staging.ts:259-265`

   This converts an unsatisfiable modality requirement into a satisfiable filesystem
   requirement. It is the single most important mechanism for D17 (air-gapped, weak
   local models) and for the `fail-then-recommend` stance (D11).

3. **[NEW] Goose does the exact *inverse* transformation, silently, and Goose is Bud's
   execution home.** `detect_image_path` scans **tool-output text** for `.png/.jpg/.jpeg`
   paths and `load_image_file` promotes them to `ImageContent`
   (`FD/goose/crates/goose-provider-types/src/images.rs:36-100, 202-241`). So the same PACT
   folder yields *text* on Eve and *an image* on Goose for the identical tool output.
   **This is a portability defect that exists today between two of PACT's own targets.**
   PACT must make media promotion/demotion an explicit, declared, lowering-time rule with a
   loss report — never an adapter heuristic.

4. **[NEW] Capability derivation in PACT's highest-priority adapter is substring matching on
   the model name.** Pydantic AI: `is_image_model = 'image' in model_name`
   (`FW/pydantic-ai/pydantic_ai_slim/pydantic_ai/profiles/google.py:61`);
   `supports_web_search = '-search-preview' in model_name` and
   `supports_image_output = model_name.startswith('gpt-5') or 'o3' in model_name or '4.1' in
   model_name or '4o' in model_name` (`profiles/openai.py:314-317`). `inspect_ai` gates
   OpenAI computer use on a version regex `(major, minor) >= (5, 4)` plus an exclusion list
   and an `is_latest` escape (`EV/inspect_ai/src/inspect_ai/model/_providers/_openai_computer_use.py:88-101`).
   **Nobody derives modality capability from a catalogue.** PACT must own the catalogue
   *and* expect adapter-internal guesses to disagree with it; the lockfile must record which
   source decided.

5. **[NEW, quantified] The largest model catalogue in the ecosystem is structurally bimodal,
   and a naive modality predicate silently excludes most of it.** Measured over
   `RO/litellm/model_prices_and_context_window.json` (2,984 entries) on 2026-08-07:
   `supported_modalities` present on **360** entries (12.1%); `supports_vision` present on
   **980**; both on **272**; **861 entries (28.9%) carry no capability key at all**. Of 297
   `claude`-named entries, **4** carry `supported_modalities`. A predicate written as
   `modality.input contains image` against `supported_modalities` therefore **excludes 293 of
   297 Claude models**. Where both keys exist they agree (2 disagreements, both TTS models).
   ⇒ The catalogue schema needs a **normative merge order across synonymous keys** and a
   **tri-state** (`true | false | unknown`), with `unknown` never satisfying a predicate in
   `strict` mode (AC-3.3).

6. **Computer use has five incompatible action vocabularies, three coordinate spaces, and no
   catalogue truth.** Anthropic (dated tool versions), OpenAI Responses, Google Gemini
   (**normalised** coordinates), inspect_ai's 22-action normalisation, and SWE-agent's
   17-action browser bundle. Verified: `supports_computer_use` is **absent** from LiteLLM's
   entry for OpenAI's own `computer-use-preview` (§2.3), and **166** entries carry it — all
   Anthropic-family except two `gemini-2.5-computer-use-preview-10-2025` rows.
   `computer_use` does not exist as a capability at all in **AG-UI**, **ACP**, **A2A**, or
   **models.dev**.

7. **Config-only evaluation: images are feasible today, computer use needs one new assertion
   family, voice is not close.** DeepEval has **zero** audio code and `Turn.content: str`
   (§4.1). promptfoo already ships a **declarative, trace-backed trajectory assertion
   family** — `trajectory:goal-success`, `trajectory:tool-used`, `trajectory:tool-sequence`,
   `trajectory:tool-args-match`, `trajectory:step-count`
   (`EV/promptfoo/src/assertions/index.ts:143-147`, `src/types/index.ts:651-655`) — so PACT
   should adopt rather than invent that. **[NEGATIVE] No project in the corpus has a
   declarative environment-state assertion.** terminal-bench grades by running **pytest
   inside the container** (`parser_name: pytest`); inspect_ai grades in Python scorers;
   promptfoo's `sql` assertion is a *syntax* check on model output, not a database query.
   `final_state:` is genuinely new work.

---

## 1. Deliverable 1 — A content-type model for agent I/O

### 1.1 Framework-by-framework survey (source-read, re-verified 2026-08-07)

#### 1.1.1 Pydantic AI (highest-priority adapter, D5/D7)

`FW/pydantic-ai/pydantic_ai_slim/pydantic_ai/messages.py`:

| Construct | Line | Notes |
|---|---|---|
| `AudioMediaType` | 82 | closed literal: `audio/wav, mpeg, ogg, flac, aiff, aac` |
| `ImageMediaType` | 83 | `image/jpeg, png, gif, webp` |
| `DocumentMediaType` | 84-94 | pdf, txt, csv, docx, xlsx, html, markdown, msword, ms-excel |
| `VideoMediaType` | 95-104 | mkv, mov, mp4, webm, flv, mpeg, wmv, 3gpp |
| `AudioFormat`/`ImageFormat`/`DocumentFormat`/`VideoFormat` | 106-109 | parallel **extension** literals — a second vocabulary for the same thing |
| `FileUrl` (ABC) | ~212 | `url`, `force_download`, `vendor_metadata`, `_media_type`, `_identifier` |
| `VideoUrl`/`AudioUrl`/`ImageUrl`/`DocumentUrl` | 301/360/407/453 | four classes |
| `BinaryContent` | 535 | `data: bytes` + `media_type: str` (open escape) |
| `BinaryImage` | 697 | narrowed subclass |
| `CachePoint` | 720 | in-band cache boundary, `ttl: '5m'\|'1h'` |
| `UploadedFile` | 769 | `file_id` + `provider_name` (closed literal of 8) |
| `MultiModalContent` | 896-904 | `ImageUrl \| AudioUrl \| DocumentUrl \| VideoUrl \| BinaryContent \| UploadedFile`, discriminated on `kind` |
| `UserContent` | 916 | `str \| TextContent \| MultiModalContent \| CachePoint` |
| `ToolReturn` | ~930 | `return_value` + `content: Sequence[UserContent]` + `metadata` |

Worth stealing:
- **Content identifier** `sha1(data)[:6]` so the model can name a file in a later call
  (`messages.py:204-208`, `625-640`); auto-passed only for *tool returns*.
- **`force_download: False | True | 'allow-local'`** — SSRF policy as a typed field on the
  content part (`messages.py:145-152`, `220-227`).
- **`vendor_metadata`** documented per provider (`messages.py:229-238`).

**[NEW] Two divergences the previous revision missed, both load-bearing:**

- **The type system's media support is wider than any binding's.** `AudioMediaType` admits
  six formats, but the OpenAI Chat Completions mapping executes
  `assert item.format in ('wav', 'mp3')` (`models/openai.py:1668-1674`). A `.flac` audio part
  is *type-valid* and *runtime-fatal*. **Type-level support ≠ binding-level support**, and
  PACT's lattice key must therefore be `(adapter, provider, api-surface, model)` — not
  `(adapter)`.
- **Video is `NotImplementedError` on *both* OpenAI surfaces**, not just Responses:
  `models/openai.py:1686` and `:1736` (Chat Completions), `:3472` and `:3501` (Responses).
  Audio is `NotImplementedError` on Responses only (`:3470`), and works on Chat Completions
  (`:1668-1674`). The previous revision recorded only the Responses audio case.

**[NEGATIVE] `ModelProfile` carries no *input* modality flags.**
`profiles/__init__.py:40-138` has `supports_tools` (48), `supports_tool_return_schema` (51),
`supports_json_schema_output` (58), `supports_json_object_output` (65),
**`supports_image_output` (72)**, `supports_inline_system_prompts` (75),
`supports_thinking` (95), `supported_native_tools` (120) — and **no** `supports_vision`,
`supports_audio_input`, `supports_video_input`, `supports_computer_use`.

**[NEW] The one per-model media allowlist in the whole corpus is here.**
`GoogleModelProfile.google_supported_mime_types_in_tool_returns: tuple[str, ...]`
(`profiles/google.py:47-50`), populated from
`_GOOGLE_NATIVE_TOOL_RETURN_MIME_TYPES = ('image/png','image/jpeg','image/webp',
'application/pdf','text/plain')` (`google.py:7-14`) and gated on Gemini 3+ (`google.py:78`).
**Tool-result media capability is narrower than input media capability and is model-specific.**
PACT's capability model must carry media types *per direction and per position*
(user-input / assistant-output / tool-result), not one `vision: bool`.

**[NEGATIVE] No computer use.** `native_tools/__init__.py:15-33` lists WebSearch, XSearch,
CodeExecution, WebFetch, ImageGeneration, Memory, MCPServer, FileSearch, Advisor — no
computer tool. Confirmed by `# Pydantic AI doesn't yet support the ComputerUse built-in tool`
(`models/openai.py:2287-2288`).

**Streaming.** Delta parts are `TextPartDelta`, `ThinkingPartDelta`, `ToolCallPartDelta`
only. **There is no `FilePartDelta`** — binary content is atomic in the stream.

#### 1.1.2 LangChain / LangGraph

`FW/langchain/libs/core/langchain_core/messages/content.py` (1488 lines):
`TextContentBlock` (207), `ToolCall`/`ToolCallChunk`/`InvalidToolCall` (247/291/336),
`ServerToolCall`/`Chunk`/`ServerToolResult` (372/397/425), `ReasoningContentBlock` (456),
**`ImageContentBlock` (498)**, **`VideoContentBlock` (549)**, **`AudioContentBlock` (600)**,
`PlainTextContentBlock` (651), `FileContentBlock` (721), `NonStandardContentBlock` (790).
Unions 832-853; `KNOWN_BLOCK_TYPES` 856-877 with the rule "If a block has a type not in this
set, it is considered to be provider-specific."

Two structural observations that survive:
- Every data block has the **same three-way source union** `file_id | url | base64` plus
  `mime_type`; the classes differ only in their `type` literal. LangChain's own comment
  listing "3D models, Tabular data" as future modalities is at `content.py:785-787` —
  evidence the per-modality enumeration does not close.
- `index: int | str` on every data block, "used during streaming": LangChain streams media
  by **index correlation**, not delta chunks. This is a third streaming regime (§1.5).

#### 1.1.3 AutoGen — the binding constraint

`FW2/../autogen/python/packages/autogen-core/src/autogen_core/models/_types.py`:
```
UserMessage.content: Union[str, List[Union[str, Image]]]      # line 32
AssistantMessage.content: Union[str, List[FunctionCall]]      # line 43
FunctionExecutionResult.content: str                          # line 58
```
**[NEGATIVE]** Images only. No audio, no video, no documents, no file references, and
**tool results are plain `str`** — a tool cannot return an image to the model through the
typed API. `MultiModalMessage.content: List[str | Image]` in agentchat, with
`to_model_text(image_placeholder="[image]")` as a documented lossy downgrade.

`ModelInfo` (`autogen-core/src/autogen_core/models/_model_client.py:164-181`) requires
`vision`, `function_calling`, `json_output`, `family`, `structured_output`, optional
`multiple_system_messages`. **Author-declared, not catalogue-derived** — the deprecated
`ModelCapabilities` at `:157-161` had the same three flags. AutoGen is the only target
framework that *requires* a modality declaration, and it requires the human to supply it.

#### 1.1.4 OpenAI Agents SDK

`FW/openai-agents-python/src/agents/items.py` imports `ResponseInputImageContentParam` (35)
and `ResponseInputFileContentParam` (34).
**[NEGATIVE] `grep -c audio items.py agent.py` → `0` and `0`** (re-verified). Audio lives in
two *separate subsystems*:
- **`voice/`** — cascaded. `AudioInput` is a numpy `int16|float32` buffer with `frame_rate`
  (`DEFAULT_SAMPLE_RATE = 24000`), `sample_width`, `channels` (`voice/input.py:13,42-57`);
  `StreamedAudioInput` (`voice/input.py:76`). `TTSModelSettings` (`voice/model.py:22-61`):
  `voice` (9-value literal at 17), `buffer_size=120`, `dtype`, `transform_data`,
  `instructions`, `text_splitter`, `speed`. `STTModelSettings` (`voice/model.py:104-118`):
  `prompt`, `language`, `temperature`, `turn_detection: dict[str, Any]` (untyped).
- **`realtime/`** — duplex. `RealtimeTurnDetectionConfig` (`realtime/config.py:96-124`):
  `type: semantic_vad|server_vad`, `create_response`, `eagerness`, `interrupt_response`,
  `prefix_padding_ms`, `silence_duration_ms`, `threshold`, `idle_timeout_ms`,
  `model_version`. Audio formats normalised to `audio/pcm@24000 | audio/pcmu | audio/pcma`
  (`realtime/audio_formats.py:16-52`).

**Computer use is first-class.** `computer.py:4-5`:
`Environment = Literal["mac","windows","ubuntu","browser"]`,
`Button = Literal["left","right","wheel","back","forward"]`. `Computer` ABC (line 8) and
`AsyncComputer` (72) expose exactly nine operations — `screenshot, click, double_click,
scroll, type, wait, move, keypress, drag` — plus optional `environment` (17-20) and
`dimensions` (22-25) properties. `ComputerTool` (`tool.py:761-789`) takes the computer plus
`on_safety_check`, with its runtime name pinned to `"computer_use_preview"` (`tool.py:783-785`).

#### 1.1.5 Anthropic SDK + Claude Agent SDK

Anthropic **input** union (`types/content_block_param.py`): Text, **Image**, **Document**,
SearchResult, Thinking, RedactedThinking, ToolUse, ToolResult, ServerToolUse, five
tool-result blocks, ContainerUpload, MidConversationSystem.
**Output** union (`types/content_block.py`): Text, Thinking, RedactedThinking, ToolUse,
ServerToolUse, five tool-result blocks, ContainerUpload.
**[NEGATIVE] No image, audio, or video in model output. No audio or video anywhere.**

Sources are narrow: `ImageBlockParam.source = Base64ImageSourceParam | URLImageSourceParam`
(`image_block_param.py:14`); `DocumentBlockParam.source = Base64PDF | PlainText |
ContentBlock | URLPDF` (`document_block_param.py:17`) plus `citations`, `context`, `title`.

Computer tools are **date-versioned betas**: `beta_tool_computer_use_20241022_param.py`,
`..._20250124_param.py`, `..._20251124_param.py`. `BetaToolComputerUse20250124Param`
requires `display_width_px`, `display_height_px`, `name:"computer"`, `type:"computer_20250124"`,
optionally `display_number`, `allowed_callers`, `defer_loading`, `strict`, `input_examples`.
**[NEGATIVE] The action vocabulary is untyped in the SDK** — the actions exist only in the
prose tool description served by the API.

**Claude Agent SDK** (`FW/claude-agent-sdk-python/src/claude_agent_sdk/types.py:994-1001`):
```python
ContentBlock = (
    TextBlock | ThinkingBlock | ToolUseBlock
    | ToolResultBlock | ServerToolUseBlock | ServerToolResultBlock
)
```
**[NEGATIVE] No image block.** Media reaches the model only through
`ToolResultBlock.content: str | list[dict[str, Any]]` — untyped dicts. The SDK's MCP result
converter declares `ImageContent | AudioContent` in its input type
(`__init__.py:469-470`) and then:
```python
logger.warning("Binary embedded resource cannot be converted to text, skipping")   # __init__.py:512
logger.warning("Unsupported content type %r in tool result, skipping", item_type)  # __init__.py:516
```
**This is exactly the silent-loss failure mode T7/AC-7.1 forbids, in a first-party SDK of a
target framework.** PACT's adapter for the Claude Agent SDK must intercept before this
point and emit a lattice `degraded` entry rather than let the warning be the report.

#### 1.1.6 Vercel AI SDK v4 — the cleanest *language-model* model

`FW/vercel-ai/packages/provider/src/language-model/v4/language-model-v4-prompt.ts`:
- One `LanguageModelV4FilePart` (line 151) with `filename?` (157), `data: SharedV4FileData`
  (168), and `mediaType: string` (181) accepting **either a full IANA type or just the
  top-level segment**, with `*`-subtype wildcards normalised to the top-level segment
  (doc comment 169-180, naming helpers `isFullMediaType`, `getTopLevelMediaType`,
  `detectMediaType`).
- `SharedV4FileData` (`packages/provider/src/shared/v4/shared-v4-file-data.ts:6-46`) =
  `{type:'data', data: Uint8Array|string} | {type:'url', url: URL} |
  {type:'reference', reference: {[provider]: id}} | {type:'text', text: string}`.
  **[NEW, load-bearing negative] There is no `path`/file variant.** Every filesystem-native
  system in the corpus fakes one with a custom URL scheme (Eve's `eve-sandbox:`, §1.2).
  PACT is filesystem-native by D2, so `path:` must be a **first-class source variant** —
  this is one of the few places PACT must exceed its best prior art rather than copy it.
- Assistant messages may carry file parts (unlike Anthropic).
- **Tool results are richly multimodal.** `LanguageModelV4ToolResultOutput` (288) =
  `text | json | execution-denied | error-text | error-json | content[]` where `content[]`
  items are `text | file | custom`. **`execution-denied{reason}` is a first-class output
  value** — denial is data, not an exception. This is what makes a denied approval
  replayable and eval-able.
- `LanguageModelV4ToolApprovalResponsePart{approvalId, approved, reason}` (259) is a
  **message part** in role `tool`. Approvals live in the transcript.

Streaming (`language-model-v4-stream-part.ts`): `text-start/-delta/-end`,
`reasoning-start/-delta/-end`, `tool-input-start/-delta/-end`, then whole-object
`LanguageModelV4File`, `…Source`, `…ToolCall`, `…ToolResult`, `…ToolApprovalRequest`, plus
`stream-start{warnings}`, `response-metadata`, `finish`, `raw`, `error`.
**Files stream as whole parts; only text/reasoning/tool-input have delta triples.**

**Modality is a model *role*, not a flag.** `packages/provider/src/` contains sibling
interfaces: `language-model`, `embedding-model`, `image-model`, `speech-model`,
`transcription-model`, `realtime-model`, `video-model`, `reranking-model`.
`RealtimeModelV4SessionConfig` is the **only provider-neutral voice session schema in the
corpus**: `instructions`, `voice`, `outputModalities: ('text'|'audio')[]`,
`inputAudioFormat{type, rate}`, `outputAudioFormat`, `inputAudioTranscription{model,
language, prompt}`, `outputAudioTranscription`, `turnDetection{type:
'server-vad'|'semantic-vad'|'disabled', threshold, …}`.

`SharedV4Warning = unsupported{feature,details} | compatibility{feature,details} |
deprecated{setting,message} | other`
(`packages/provider/src/shared/v4/shared-v4-warning.ts`) is the industry's existing runtime
loss report, and it maps 1:1 onto PACT's lattice values `unsupported` / `degraded`.
**Adopt the wire shape so adapter warnings forward unmodified.**

#### 1.1.7 **[NEW] Vercel Eve — the filesystem-native answer

Eve is PACT's closest structural analogue (D2) and its media handling is the most directly
transferable code in the corpus.

**Two ref schemes, both versioned custom URLs occupying `FilePart.data`:**

| Scheme | Shape | Purpose | Evidence |
|---|---|---|---|
| `eve-attachment:` | `?v=1&p=<base64url JSON {params, size?}>` | carries file identity across step boundaries without inlining bytes; `params` is adapter-defined and "must not carry credentials" | `internal/attachments/refs.ts:1-42, 50-69` |
| `eve-sandbox:` | `?path=<urlencoded>&size=<bytes>&type=<mediaType>` | names a file already staged in the sandbox; size and mediaType snapshotted so hydration can decide without re-reading | `internal/attachments/sandbox-refs.ts:1-62` |

The attachment-ref decoder **rejects any wire version other than `1`** — "so a future format
bump doesn't silently misparse" (`refs.ts:19-22`). That is PACT's E-2 rule
("unknown features rejected loudly, never ignored") already implemented.

**Staging → hydration ladder** (`harness/attachment-staging.ts`):
- `ATTACHMENTS_ROOT = "/workspace/attachments"` (line 30) — a canonical authored path that
  `SandboxSession.writeFile` translates to the backend-native location.
- Filenames are sanitised `UNSAFE_FILENAME_CHARS = /[^\w.-]+/g` and prefixed with
  `sha256(bytes).slice(0,16)`; a missing filename becomes `file-<sha>`
  (`:33-34, 386-393`). **This is a working solution to AC-1.2′'s portable-key problem for
  binary payloads.**
- `HYDRATE_IMAGE_INLINE_MAX_BYTES = 3 * 1024 * 1024` (`:45`);
  `HYDRATE_PDF_INLINE_MAX_BYTES = 20 * 1024 * 1024` (`:51`, comment: "Matches provider-side
  caps for native document understanding").
- `shouldInlineSandboxRefAsBytes` (`:266-274`) inlines **only** `image/*` under 3 MiB and
  `application/pdf` under 20 MiB. Everything else →
  `renderSandboxRefAsTextPart` → `{type:"text", text:"Attached file <path> (<mediaType>)"}`
  (`:285-287`), deliberately matching "the text shape produced by the compaction summarizer
  … so the model sees one consistent surface for 'there is a file at this path'".

**Declarative media policy** — `public/channels/upload-policy.ts`:
```ts
export type UploadPolicy = "disabled" | UploadPolicyConfig;
export interface UploadPolicyConfig {
  readonly maxBytes: number;
  readonly allowedMediaTypes: readonly string[] | "*";   // "image/*" wildcards supported
}
export const DEFAULT_UPLOAD_POLICY = { allowedMediaTypes: "*", maxBytes: 25 * 1024 * 1024 };
export type UploadPolicyViolation =
  | { kind: "too-large";             mediaType; filename?; byteLength; limit }
  | { kind: "disallowed-media-type"; mediaType; filename?; allowedMediaTypes };
```
(`upload-policy.ts:12-24, 30-34, 43-59`), with violations mapping to HTTP 413/415.
**This is the shape of PACT's `interface.input.media` constraint** — but note the default
is *permissive* (`"*"`). PACT should invert it to default-deny, matching ACP's stance (§2.4)
and T7.

**[NEGATIVE] Eve's image eval is TypeScript code.**
`e2e/fixtures/agent-basic-runtime/evals/runtime/image-attachment.eval.ts` is a
`defineEval({ async test(t) { … } })` that calls `t.sendFile(prompt, filePath, "image/png")`,
then hand-inspects `turn.events` for a `message.received` event whose `data.parts` contains
a `type:"file"` part with `mediaType === "image/png"`, throwing a hand-written `Error`
otherwise. **The closest system to PACT cannot express an image eval in configuration.**
That is the gap D19/AC-4.2 exists to close.

#### 1.1.8 **[NEW] Goose — Bud's execution home (D3 superset target)

- `ImageFormat = OpenAi | Anthropic` (`FD/goose/crates/goose-provider-types/src/images.rs:11-14`)
  and `convert_image` (`:17-33`) emits either `{"type":"image_url","image_url":{"url":"data:…"}}`
  or `{"type":"image","source":{"type":"base64","media_type":…,"data":…}}`. **Only two image
  wire shapes exist in practice** — a useful narrowing for the adapter ABI.
- `detect_image_path(text)` (`images.rs:36-100`) scans arbitrary text for `.png/.jpg/.jpeg`
  paths (case-insensitive, up to `MAX_PATH_LEN = 4096`, handling spaces in paths);
  `load_image_file(path)` (`images.rs:202-241`) reads the file, infers MIME from the
  extension (**png/jpg/jpeg only**), base64-encodes and returns `ImageContent`.
  ⇒ **Implicit text→image promotion.** See §0.3 for why this is a portability hazard.
- The `developer` extension's `ImageTool` (`FD/goose/crates/goose/src/agents/platform_extensions/developer/image.rs`)
  takes `ImageReadParams{source: String, crop: Option<CropParams{x,y,width,height}>}` where
  the crop doc-comment reads "use to zoom in and get more details" (`:19-23`), enforces
  `MAX_IMAGE_BYTES = 20 * 1024 * 1024` (`:14, 241-244`), and returns **both** a text summary
  and the image, with `structured_content` carrying `{source, mimeType, width, height,
  originalWidth, originalHeight}` (`:52-66, 128-158`). **This is the runtime answer to the
  OS-survey resolution problem (§3.1) expressed as a tool rather than a preprocessing step**
  — and therefore something the PACT optimiser could select.

### 1.2 Divergence matrix (re-verified)

Legend: **N** native/typed · **P** partial (untyped or via escape hatch) · **—** absent ·
**X** explicit error

| Capability | Pydantic AI | LangChain/Graph | AutoGen | OpenAI Agents | Claude Agent SDK | Vercel AI v4 | Eve | Goose | MCP 2025-11-25 | A2A | AG-UI | ACP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Image **in** | N | N | N (`Image`) | N (`input_image`) | P (tool-result dicts) | N (`file`+`image/*`) | N (staged) | N | N (`ImageContent`) | N (`media_type`) | N | N (opt-in) |
| Image **out** | N (`FilePart`) | N | — | N (`ImageGenerationCall`) | — | N (`file` stream part) | N | N | N | N | N (cap flag) | N |
| Audio **in** | N, **X on Responses**, wav/mp3 only on Chat | N | — | — (only `voice/`,`realtime/`) | — (dropped w/ warning) | N | P (upload policy allows; no model path) | — | N | N | N | N (opt-in) |
| Audio **out** | P | N | — | — (only `voice/`,`realtime/`) | — | N | — | — | N | N | N (cap flag) | — |
| Video **in** | N (8 formats) but **X on both OpenAI surfaces** | N | — | — | — | N | — | — | **—** | N | N (cap flag) | — |
| Document/PDF **in** | N (9 types) | N | — | N (`input_file`) | P | N | N (≤20 MiB inline) | N | P (`EmbeddedResource`) | N | N (cap flag) | N |
| Provider file-ID ref | N (`UploadedFile`, 8) | N (`file_id`) | — | N | — | N (`reference`) | N (`eve-attachment:`) | — | — | — | — | — |
| **Filesystem path source** | — | — | — | — | — | **—** | **N** (`eve-sandbox:`) | N (path scan) | — | — | — | N (`ResourceLink`) |
| **Multimodal tool result** | N (`ToolReturn.content`) | N | **— (`str`)** | P | P (untyped) | N (`content[]`) | N | N | N | n/a | n/a | N |
| Streaming media deltas | — (atomic) | P (`index`) | — | audio only in `voice`/`realtime` | — | — (atomic) | — | — | — | n/a | — | — |
| Computer use | **—** | — | — | **N** (`Computer` ABC) | P (via CLI tools) | **N** (Anthropic factories) | — | — | — | — | **—** | — |
| Tool approval in transcript | N (`DeferredToolRequests`) | N (`interrupt()`) | — | N (`ToolApprovalItem`) | N (`can_use_tool`) | **N** (`tool-approval-response` part) | N | N (`PermissionLevel`) | — | `TASK_STATE_INPUT_REQUIRED` | N (`interrupts`) | N (4 option kinds) |

**The four hard walls for harness lowering (D12):**
1. **AutoGen tool results are `str`** (`_types.py:58`). A PACT tool returning an image must,
   on AutoGen, either emit the image as a following `UserMessage` part or degrade to a text
   placeholder. `degraded` lattice entry with a mandatory report.
2. **Anthropic assistant output cannot contain media** (`content_block.py` has no image
   member). `output: {image: …}` is `unsupported` on any Anthropic-family binding unless the
   image is produced by a *tool*.
3. **MCP has no video content type.** `ContentBlock = TextContent | ImageContent |
   AudioContent | ResourceLink | EmbeddedResource` in **both**
   `PR/mcp-spec/schema/2025-11-25/schema.ts:1740-1741` and
   `PR/mcp-spec/schema/draft/schema.ts:2292-2293`; `grep -rn video PR/mcp-spec/schema/`
   returns **zero** across all five schema versions. Since D14 makes MCP the no-code
   custom-tool path, **a no-code tool cannot return video in v1.** Workaround: `ResourceLink`.
   (Note `SamplingMessageContentBlock` at `:1693-1698` is a *different, narrower* union —
   `Text | Image | Audio | ToolUse | ToolResult`, no resources — so a tool result and a
   sampling message are not interchangeable content-wise.)
4. **No target framework has a filesystem-path source.** PACT must define one and adapters
   must lower it (to inline bytes, a provider upload, or an Eve-style text reference).

### 1.3 Proposed PACT content model

**Canonical part.** Discriminated on **modality class**, with `mediaType` required and the
class derived from it by a normative table (so a new modality is a table row, not a schema
change — E-2/E-3). Rationale for choosing modality-as-discriminator over Vercel's
media-typed-part: **every capability negotiation surface in the corpus is a per-modality
boolean** (ACP `PromptCapabilities{image, audio, embeddedContext}`; AG-UI
`MultimodalInputCapabilities{image, audio, video, pdf, file}`; AutoGen `ModelInfo.vision`),
so the modality must be a first-class discriminator for the gate to be expressible; and
AG-UI's deliberate deprecation of the generic form (§0.1) is a warning against it.

```yaml
# canonical form
- kind: image                    # text | image | audio | video | document | binary
                                 #  | tool_call | tool_result | thinking | approval | control
  mediaType: image/png           # REQUIRED, full IANA type. `kind` is derivable from it.
  source:                        # exactly one key
    path: ./screenshots/cart.png #   relative to the spec tree  (PACT-native, D2) — see §1.2 wall 4
    # bytes: <base64>            #   inline (permitted below a profile threshold, §1.4)
    # url: https://...           #   with fetch policy
    # blob: sha256:...           #   content-addressed artifact store
    # providerRef: {openai: file-abc}   #   non-portable by construction; resolver marks it
    # text: "..."                #   inline text document
  filename: cart.png
  id: cart-before                # author-stable ID for cross-reference (§1.3.3)
  role: screenshot               # semantic tag (§1.3.2)
  fetch: {download: false, allowPrivateNetwork: false}   # SSRF policy, from pydantic-ai
  x-vendor: {openai: {detail: high}, google: {media_resolution: high}}
```

Sugar the loader normalises (D13/D18 — a non-coder must write these):
```yaml
- image: ./cart.png              # → kind inferred from extension → mediaType from table
- audio: ./greeting.wav
- document: ./policy.pdf
- text: "hello"
```

Traceability of each choice:
- **Source union `{path|bytes|url|blob|providerRef|text}`** — the union minus `path`/`blob`
  is Vercel `SharedV4FileData` verbatim (`shared-v4-file-data.ts:6-46`); `path` is required
  by D2 and has no prior art outside Eve's `eve-sandbox:` hack; `blob` is required by §1.4.
- **`fetch` policy on the part** — from `pydantic-ai messages.py:145-152, 220-227`. A URL
  part is an SSRF surface and the policy must travel with the content. Air-gapped (D17)
  default is `deny`.
- **`x-vendor`** — the `x-` mechanism (O1.4) carrying what Pydantic AI calls
  `vendor_metadata` (`messages.py:229-238`) and Vercel calls `providerOptions`.

#### 1.3.1 Tool results

Adopt Vercel's output union in shape, extended with MCP's `structuredContent`:
```yaml
toolResult:
  callId: t_1
  output:
    kind: content                # text | json | content | error-text | error-json | execution-denied
    value:
      - text: "Found 3 matches"
      - image: ./out/chart.png
  structured: {...}              # MCP structuredContent, validated against tool outputSchema
```
`execution-denied{reason}` must be a first-class output kind
(`language-model-v4-prompt.ts:288`ff), not an exception — this is what makes a **denied
approval replayable and eval-able** (§4.3 case B).

**Constraint from §1.1.1:** the set of media types permitted in a tool result is a **separate,
narrower** capability than the set permitted in a user message
(`pydantic-ai profiles/google.py:7-14, 47-50`). The PACT capability model must key media on
`(direction, position, mediaType)`.

#### 1.3.2 Semantic `role` tag on media

None of the frameworks distinguish "this image is a screenshot of the environment" from
"this image is user-supplied evidence". For computer use the harness must know: screenshots
are **prunable**, user evidence is not. SWE-agent's `LastNObservations` processor elides old
observations and appends `" (N images omitted)"`
(`FW2/swe-agent/sweagent/agent/history_processors.py:171-175`), parameterised by
`n` (`:114`), `polling` (`:117`), `always_remove_output_for_tags` (`:124`) and
`always_keep_output_for_tags` (`:129`) — i.e. **the retention policy is already tag-driven
in production**. Proposed vocabulary:
`screenshot | user_attachment | tool_output | generated | reference`. **[INFERRED]**

#### 1.3.3 Stable content IDs

Adopt Pydantic AI's identifier idea (`messages.py:204-208, 625-640`) but make it
**author-visible and author-stable**: `id:` is an author-chosen slug in the tree; the runtime
falls back to `sha256(content)[:16]` (Eve's `SHA_PREFIX_LENGTH = 16`,
`attachment-staging.ts:34`). Reason: an eval case must be able to say "the answer must
reference `cart-before`", and a content-derived hash is not writable by a non-coder before
the run.

### 1.4 The Expansion Rule vs binary payloads

Binary media is one of the places field↔directory equivalence breaks (thesis §9.3).

- **`explode`** (document → tree) of an inline base64 blob must write a **file**, or diffs
  become unreviewable (D18 requires human-meaningful diffs).
- **`collapse`** (tree → document) of a media file must **not** inline bytes into
  `canonical.json`. Evidence this is a real failure mode: OpenHands ships
  `save_screenshots_in_trajectory` with the comment "The screenshots are encoded and can make
  trajectory json files very large" (`FW2/openhands/config.template.toml:31-33`); SWE-agent
  raises `max_observation_length: 10_000_000  # need longer for images`
  (`FW2/swe-agent/config/default_mm_with_images.yaml:41`).

**Resolution.** `canonical.json` stores a **content-addressed reference**
(`{blob: "sha256:…", mediaType, bytes: 48213}`), bytes live under `.pact/blobs/<sha256>`.
Round-trip identity (`explode(collapse(X)) ≡ X`, O1.3/AC-1.2′) is over the *reference*; byte
identity is guaranteed by the hash. Precedent: promptfoo's `BlobStorageProvider`
(`EV/promptfoo/src/blobs/types.ts:18-32`: `store()/getByHash()/exists()/deleteByHash()/getUrl()`
with a `deduplicated` flag), and Eve's sha-prefixed staged filenames
(`attachment-staging.ts:386-393`).

**Threshold rule.** Inline base64 only below a **profile-configured** limit (F-1 forbids a
literal). Anchors from shipping systems: Eve inlines images ≤ **3 MiB** and PDFs ≤ **20 MiB**
(`attachment-staging.ts:45,51`); Eve's inbound cap is **25 MiB**
(`upload-policy.ts:30-34`); Goose caps images at **20 MiB**
(`developer/image.rs:14`). Recommend `64 KiB` for *inline-in-document*, distinct from the
much larger *inline-at-model-call* thresholds, which are a lowering concern.

**Consequence for O1.2 (digest).** If `canonical.json` never carries bytes, the artifact
digest must be a **Merkle root over `hash(canonical.json)` plus `hash(blob_i)` for each
referenced blob**, not a single file hash. Otherwise two agents with different screenshots
share a digest.

### 1.5 Streaming model — four regimes, not three

| Regime | Shape | Evidence |
|---|---|---|
| **Token stream** | `*-start`/`*-delta`/`*-end` triples for text, reasoning, tool input | `vercel-ai .../language-model-v4-stream-part.ts:14-68`; pydantic-ai `TextPartDelta`/`ThinkingPartDelta`/`ToolCallPartDelta` |
| **Atomic artifact** | whole `file`/`source`/`tool-result` parts, no deltas | Vercel file/source/tool parts have no delta variants; pydantic-ai has no `FilePartDelta` |
| **[NEW] Index-correlated media** | media blocks re-emitted with a stable `index: int\|str`, reassembled by the consumer | LangChain `content.py` — `index` on `ImageContentBlock` (498), `VideoContentBlock` (549), `AudioContentBlock` (600), "used during streaming" |
| **Duplex media session** | continuous `audio-delta` + `audio-transcript-delta` + VAD lifecycle, bidirectional | `vercel-ai realtime-model-v4-server-event.ts`; `openai-agents realtime/config.py:96-150` |

PACT's IR needs `interface.streaming: {mode: token | duplex}` and, for duplex, a separate
`realtime` model-role binding. **Do not model duplex audio as a content part** — in every
framework that supports it, it is a separate interface (`realtime-model/`) or a separate
pipeline (`voice/`). **[INFERRED]**

---

## 2. Deliverable 2 — Capability requirements and verification

### 2.1 What each system knows about modality

| Source | Modality capability data? | Shape |
|---|---|---|
| Pydantic AI `ModelProfile` | **No input modalities**; only `supports_image_output` (`profiles/__init__.py:72`) | derived by **substring match on the model name** (`profiles/google.py:61`, `profiles/openai.py:314-317`) |
| LangChain `langchain-model-profiles` | **Yes**, vendored from models.dev | 28 keys incl. `{text,image,audio,video}_{inputs,outputs}`, `pdf_inputs`, `image_url_inputs`, `pdf_tool_message`, `image_tool_message` |
| AutoGen `ModelInfo` | Partial, **author-declared** | `vision`, `function_calling`, `json_output`, `structured_output`, `family` (`_model_client.py:164-181`) |
| OpenAI Agents SDK | No catalogue | — |
| Claude Agent SDK | No | — |
| Vercel AI SDK | No catalogue; **runtime rejection instead** | `UnsupportedFunctionalityError({functionality: 'media type: X'})` in provider converters |
| **AG-UI** | **Yes — at the *agent* level** | `MultimodalCapabilities{input:{image,audio,video,pdf,file}, output:{image,audio}}` (`capabilities.py:223-283`) |
| **ACP** | **Yes — negotiated, default-deny** | `PromptCapabilities{image:false, audio:false, embeddedContext:false}` |
| **A2A** | **Yes — REQUIRED MIME lists** | `AgentCard.default_input_modes` / `default_output_modes` (`a2a.proto:386-390`, both `REQUIRED`), per-skill `input_modes`/`output_modes` (`:446-451`) |
| LiteLLM | **Yes**, largest and least consistent | §2.3 |

**[NEW] AG-UI's `AgentCapabilities` is a near-complete draft of PACT's contract-side
capability block**, and its normative tri-state rule is exactly what PACT needs:

> "All fields are optional — agents only declare what they support. **Omitted fields mean the
> capability is not declared (unknown), not that it's unsupported.** The `custom` field is an
> escape hatch for integration-specific capabilities."
> — `PR/ag-ui/sdks/python/ag_ui/core/capabilities.py:363-371`

Its category set (`capabilities.py:362-414`): `identity`, `transport`, `tools`, `output`,
`state`, `multi_agent`, `reasoning`, `multimodal`, `execution`, `human_in_the_loop`, `custom`.
Notable members PACT should mirror:
- `ExecutionCapabilities{code_execution, sandboxed, max_iterations, max_execution_time}`
  (`:285-313`) — `sandboxed` is documented as "Only meaningful when `code_execution` is
  `True`", i.e. a **conditional capability**, which PACT's predicate language must express.
- `HumanInTheLoopCapabilities{supported, approvals, interventions, feedback, interrupts,
  approve_with_edits}` (`:316-358`) — `approve_with_edits` ("tool-call interrupts accept
  editedArgs in the resume payload") is the one approval affordance PACT would otherwise miss.
- `OutputCapabilities.supported_mime_types: List[str]` (`:134`) — MIME lists again.

**[NEGATIVE] `computer_use` does not exist as a capability in AG-UI, ACP, A2A, or
models.dev.** Only LiteLLM has it, and §2.3 shows it is wrong. There is no ecosystem-wide
vocabulary for computer use; PACT must define one and cannot import one.

### 2.2 **[NEW]** Quantitative catalogue audit (LiteLLM, 2,984 entries, measured 2026-08-07)

`supports_*` flags set `true`:

| Flag | count | | Flag | count |
|---|---|---|---|---|
| `supports_function_calling` | 1667 | | `supports_computer_use` | **166** |
| `supports_tool_choice` | 1508 | | `supports_audio_input` | 105 |
| `supports_vision` | 888 | | `supports_audio_output` | 62 |
| `supports_response_schema` | 879 | | `supports_video_input` | 54 |
| `supports_reasoning` | 770 | | `supports_url_context` | 50 |
| `supports_pdf_input` | 464 | | `supports_embedding_image_input` | 19 |
| `supports_web_search` | 260 | | `supports_image_input` | **6** |
| `supports_native_streaming` | 222 | | `supports_multimodal` | **6** |

**Key coverage/consistency findings:**
- `supported_modalities` present on **360 / 2984 = 12.1%**; `supports_vision` present on
  **980**; **both** on **272**; `supported_modalities`-only on **88**; `supports_vision`-only
  on **708**.
- **861 entries (28.9%) carry no capability key at all.**
- Of **297** `claude`-named entries, **4** carry `supported_modalities`. Anthropic rows use
  `supports_vision`; OpenAI rows use `supported_modalities: [text, image]`.
- Where both keys exist they agree — only **2** disagreements
  (`gemini-2.5-pro-preview-tts`, `gemini/gemini-2.5-pro-preview-tts`).
- Three near-synonymous keys coexist: `supports_vision` (888), `supports_image_input` (6),
  `supported_modalities` containing `image` (299).

**Design consequence.** A modality predicate is only sound if the catalogue schema defines
(a) a **normative key-merge order** across synonyms, and (b) a **tri-state** where `unknown`
never satisfies a predicate in `strict` mode. Without both, `modality.input contains image`
evaluated against `supported_modalities` excludes 293 of 297 Claude models — a silent,
catastrophic resolver bug that would surface as "no candidate model passes".

### 2.3 The catalogue is demonstrably wrong on computer use

Verified entries (exact key sets read 2026-08-07):

```
computer-use-preview        mode: chat, supported_endpoints: ["/v1/responses"],
                            supported_modalities: [text,image], supports_vision: true,
                            supports_reasoning: true            ← NO supports_computer_use
azure/computer-use-preview  identical                            ← NO supports_computer_use
gpt-5.5                     supports_vision, supports_pdf_input, supports_web_search
                                                                 ← NO supports_computer_use
claude-opus-4-5             supports_computer_use: true, supports_vision: true
                                                                 ← NO supported_modalities
gemini-2.5-computer-use-preview-10-2025
                            supports_computer_use: true, supported_modalities: [text,image]
```

**OpenAI's dedicated computer-use model is not marked as supporting computer use in the
largest model catalogue in the ecosystem.** Meanwhile the best-informed implementation in the
corpus does not trust a catalogue either: inspect_ai hardcodes
`(major, minor) >= (5, 4)` plus `_COMPUTER_USE_EXCLUDED_VARIANTS` plus an `is_latest` escape
(`EV/inspect_ai/src/inspect_ai/model/_providers/_openai_computer_use.py:88-101`), and gates
Gemini on `"gemini-2.5-computer-use-preview" in model_name or "gemini-3-flash-preview" in
model_name` (`_google_computer_use.py:24-36`).

Also: **models.dev has no `computer_use` key** — `grep -c computer` on LangChain's vendored
OpenAI and Anthropic `_profiles.py` returns `0`. And LangChain ships a **human override
layer**: `libs/partners/anthropic/langchain_anthropic/data/profile_augmentations.toml` sets
provider-wide `image_url_inputs = true`, `pdf_inputs = true`, `structured_output = false`,
then re-enables `structured_output = true` per model. **Upstream feed + local corrections is
exactly D8's hybrid, in production today** — but it records **no source and no date**, which
is precisely what AC-3.3 requires and PACT must add.

### 2.4 Proposed capability vocabulary and predicate semantics

Split the D16 vocabulary into three kinds, because they are verified differently:

**(a) Model-intrinsic** — verified against the catalogue at resolve time.
```
media.in[<mediaType glob>]      # e.g. media.in["image/*"], media.in["application/pdf"]
media.out[<mediaType glob>]
media.toolResult[<mediaType glob>]      # narrower than media.in — see §1.1.1 (google profile)
context.window >= 128k
tool_calling: none | serial | parallel
structured_output: none | json_object | json_schema
reasoning: none | optional | always
```
Keying on **MIME globs rather than modality words** is the change from the previous
revision. Justification: A2A's card contract is MIME lists (`a2a.proto:386-390`), Eve's
policy is MIME globs (`upload-policy.ts:19-23`), AG-UI's `OutputCapabilities` is
`supported_mime_types` (`capabilities.py:134`), and the one per-model tool-return allowlist
in the corpus is a MIME tuple (`pydantic-ai profiles/google.py:7-14`). Modality words
(`vision`, `audio_in`) remain as **sugar that desugars to globs** for D13 authors.

**(b) Provider-tool capabilities** — verified against `(provider, api-surface)`, not the model.
```
tool.web_search · tool.web_fetch (web_scrape) · tool.code_interpreter ·
tool.computer_use{environment: browser|mac|windows|ubuntu, actions: [...], coordinateSpace: ...} ·
tool.image_generation · tool.file_search · tool.memory
```
Evidence they are tool-shaped, not model-shaped: Pydantic AI's
`ModelProfile.supported_native_tools: frozenset[type[AbstractNativeTool]]`
(`profiles/__init__.py:120`) — a per-profile *set of tool types*, adjusted per model family
(`profiles/openai.py:324-325`); Claude Agent SDK's `ServerToolName` literal (`types.py:954-963`:
advisor, web_search, web_fetch, code_execution, bash_code_execution,
text_editor_code_execution, tool_search_tool_regex, tool_search_tool_bm25); Anthropic's
`allowed_callers` on the computer tool (`beta_tool_computer_use_20250124_param.py:29-31`).

**(c) Substrate capabilities** — verified against the *runtime*, not the model.
```
sandbox.kind: none | process | container | microvm | remote
sandbox.gui: true                 # a display exists at all
sandbox.gui.geometry: {w, h}
sandbox.network: none | allowlist | full
approval.channel: available       # a human can be reached
audio.duplex: true                # a realtime transport exists
filesystem.tools: true            # needed for the Eve-style text-reference fallback (§0.2)
```
A `computer_use` contract bound to a capable model on a runtime with no display is a
resolve-time failure no model catalogue can catch. **[INFERRED]** — nothing in the corpus
models this; the closest is `Computer.environment`/`Computer.dimensions` being optional
properties on the ABC (`FW/openai-agents-python/src/agents/computer.py:17-25`), and AG-UI's
`ExecutionCapabilities.sandboxed` (`capabilities.py:296-302`).

**Verification levels** (all four needed under D17):
1. **Declared** — catalogue row with per-field provenance. Cheap, offline, **pre-filter only** (R5).
2. **Probed** — one-shot capability probe against a live endpoint, cached in the lockfile.
   Unavailable air-gapped against remote models; available against a local model.
3. **Evidenced** — a modality-specific eval in the suite passed. The real oracle (T2).
4. **Asserted** — author wrote `x-capability-override:` with justification; recorded in the
   lockfile and surfaced in the Portability Report.

**Default-deny is settled prior art.** ACP: "Baseline agent functionality requires support
for `ContentBlock::Text` and `ContentBlock::ResourceLink` … **Other variants must be
explicitly opted in to**", with `image`, `audio`, `embeddedContext` all `default: false`
(`PR/agent-client-protocol/schema/v1/schema.json`, `$defs.PromptCapabilities`). PACT should
mirror it: **sending a content kind the binding did not declare is an error, never a silent
drop.** Note this *conflicts* with Eve's permissive `allowedMediaTypes: "*"` default
(`upload-policy.ts:30-34`); PACT should follow ACP, not Eve, here.

### 2.5 Air-gapped implications (D17)

- **Catalogue.** Both candidate feeds are offline-capable artefacts: LiteLLM's single JSON
  file, and LangChain's *vendored* `_profiles.py`. Both permissive-licensed (the LangChain
  header names models.dev, MIT). Seed `models/catalog.yaml` from both, keep **per-field**
  provenance, ship the merge as a build step so `pact validate` needs no network.
- **Vision judge.** DeepEval's five multimodal metrics all instantiate a judge model and pass
  a multimodal array. Air-gapped image evals therefore require a **declared local
  vision-capable judge** in the profile — a hard dependency PACT must declare, not discover
  at eval time.
- **Voice.** `FW/openai-agents-python/src/agents/voice/models/` contains only
  `openai_stt.py`, `openai_tts.py`, `openai_model_provider.py`.
  **[NEGATIVE] There is no local TTS and no local duplex/realtime model anywhere in the
  corpus.** The Bud manifest does have a local STT path — `input.dictation.provider: local`
  with Whisper model download/selection
  (`gaia-ai-runtime/bud-agentic-runtime/sdk-and-declarative-dev.md:2515-2553`). **Air-gapped
  voice in v1 is therefore STT-in only.**
- **[NEW] terminal-bench-style container evals are not air-gap-clean by default.** Its
  generated `run-tests.sh` does `apt-get update` and
  `curl -LsSf https://astral.sh/uv/0.7.13/install.sh | sh` at grading time
  (`EV/terminal-bench/original-tasks/weighted-max-sat-solver/run-tests.sh:9-16`). PACT's
  environment declaration must therefore distinguish **build-time network** from
  **run-time network** and forbid the former in air-gapped profiles.

---

## 3. Deliverable 3 — Sandboxing and approval gates

### 3.1 Sandbox declaration — prior art

| System | Declaration | Fields observed |
|---|---|---|
| OpenAI Agents SDK | Pydantic `Manifest` (`FW/openai-agents-python/src/agents/sandbox/manifest.py:88-97`) | `version`, `root` (default `/workspace`), `entries: {path: Dir\|File\|Mount}`, `environment` (with `EnvValue` indirection for secrets, 45-84), `users`, `groups`, `extra_path_grants`, `remote_mount_command_allowlist` (19 defaults, 22-40). Backends `sandboxes/docker.py`, `sandboxes/unix_local.py`. **[NEGATIVE] no network policy field.** |
| Claude Agent SDK | `SandboxSettings` TypedDict (`types.py:874-916`) | `enabled`, `autoAllowBashIfSandboxed` (**default `True`**, `:889`), `excludedCommands`, `allowUnsandboxedCommands`, `network`, `ignoreViolations`, `enableWeakerNestedSandbox`. `SandboxNetworkConfig` (836-860): `allowedDomains`, `deniedDomains`, `allowManagedDomainsOnly`, `allowUnixSockets`, `allowAllUnixSockets`, `allowLocalBinding`, `allowMachLookup`, `httpProxyPort`, `socksProxyPort`. Docstring 878-885 is explicit that **filesystem/network restrictions are permission rules, not sandbox settings** — one policy language, two enforcement points. |
| inspect_ai | `SandboxEnvironmentSpec{type, config}` where config is a filename or provider model (`util/_sandbox/environment.py:503-536`); shorthands `"docker"` and `("docker","compose.yaml")` | ABC is `exec/write_file/read_file/…` with an output cap (`INSPECT_SANDBOX_MAX_EXEC_OUTPUT_SIZE`, 10 MiB default) and typed errors (`OutputLimitExceededError`, `TimeoutError`, `PermissionError`) |
| E2B | `e2b.toml` yup schema (`RT/e2b/packages/cli/src/config/index.ts:8-17`) | `template_id`*, `template_name`, `dockerfile`*, `start_cmd`, `ready_cmd`, `cpu_count>=1`, `memory_mb>=128`. **[NEW]** A `desktop` template with X11 exists (`packages/python-sdk/tests/bugs/test_envelope_decode.py:9-41` uses `Desktop(timeout=30)`, `Xlib.display.Display(os.environ["DISPLAY"])`, `desktop.pyautogui(...)`) — but **it is not declared in `e2b.toml`**; GUI is a template property, invisible to the config schema. |
| microsandbox | CLI `SandboxOpts` (`RT/microsandbox/crates/cli/lib/commands/common.rs:51-91`) | `name`, `cpus`, `max_cpus`, `memory`, `max_memory`, `volume`, `mount_dir`, `mount_file`, `mount_disk`, `mount_named`; microVM isolation. **[NEGATIVE] `grep -rn "screenshot\|display\|gui\|vnc" crates/` finds no GUI concept.** |
| OpenHands | TOML (`FW2/openhands/config.template.toml:149-221`) | `timeout`, `user_id`, `base_container_image`, `use_host_network`, `runtime_extra_build_args`, `runtime_extra_deps`, `runtime_startup_env_vars`, `volumes` (`"/host:/workspace:rw,/p2:/workspace/p2:ro"`), `platform`, `enable_gpu`, `cuda_visible_devices`, `keep_runtime_alive`, `close_delay`. Core has `enable_browser = true` (`:48`) — **a modality capability as a config toggle** — and `replay_trajectory_path` (`:36`) for deterministic replay. VNC is env-gated: `'OH_ENABLE_VNC': '0'` (`openhands/app_server/sandbox/docker_sandbox_spec_service.py:42`). |
| SWE-agent | YAML tool **bundles are directories** (`config/default_mm_with_images.yaml:44-50`) | `tools.bundles: [{path: tools/registry}, {path: tools/image_tools}, {path: tools/web_browser}, …]`, `execution_timeout`, `registry_variables` |
| terminal-bench | **directory-per-task** | `task.yaml` (`instruction`, `author_*`, `difficulty`, `category`, `tags`, `parser_name`, `max_agent_timeout_sec`, `max_test_timeout_sec`, `run_tests_in_same_shell`, `disable_asciinema`) + `Dockerfile` + `docker-compose.yaml` + `tests/` + `run-tests.sh` + `solution.sh` |

**Convergent minimum field set [INFERRED]:** `image/template`, `cpu`, `memory`, `mounts[]`
with `ro|rw`, `env` (with secret indirection), `network{mode, allowDomains, denyDomains}`,
`timeout`, `user`, `gui{width, height, display}`, `persist{snapshot, keepAlive}`.

**GUI geometry is missing from every sandbox declaration in the corpus, and the duplication
is a live bug class.** Anthropic requires `display_width_px`/`display_height_px` on the
*tool* (`beta_tool_computer_use_20250124_param.py:12-19`); inspect_ai hardcodes
`DISPLAY_WIDTH = 1366, DISPLAY_HEIGHT = 768` in the Gemini provider with the comment "These
should stay in sync with the dimensions used by the container"
(`_google_computer_use.py:18-21`); SWE-agent exposes a `set_browser_window_size <width>
<height>` shell command (`tools/web_browser/config.yaml`); e2b's desktop geometry lives in
the template image. **PACT should declare geometry once in `sandbox.gui` and derive every
tool parameter from it.**

**[NEW] There are three coordinate spaces, and a coordinate is not portable without knowing
which one it is in.**
1. **Native display pixels** — the container's actual resolution.
2. **Scaled API pixels** — inspect_ai down-scales to a fixed aspect-matched table
   `MAX_SCALING_TARGETS = {XGA: 1024×768, WXGA: 1280×800, FWXGA: 1366×768}`
   (`_resources/tool/_x11_client.py:35-40`, comment at `:34`: "sizes above XGA/WXGA are not
   recommended"), matching aspect ratio within `0.02` tolerance and converting both
   directions (`_scale_coordinates`, `:377-410`), with screenshots resized via
   `convert -resize {x}x{y}!` (`:344-345`).
3. **Normalised 0-1 (Gemini)** — `_denormalize_coordinate` is applied to every Gemini
   action (`_google_computer_use.py:161, 165, 175`).

Screenshot scaling is also an **accuracy variable, not just plumbing**. The OS-agents survey:
vision encoders commonly ingest ~224×224 while GUI screenshots are 720×1080; "Resizing
screenshots to fit the resolution vision encoders of MLLMs preserves features of general
layout and most objects, but text and small icons cannot be well perceived, which sometimes
would be vital for MLLMs to accomplish OS tasks"
(`gaia-ai-runtime/research/papers/2508.04482-os-agents-survey.pdf`, §3.2.1, extracted lines
703-708). OpenAI's harness therefore sets `detail: "original"` — "preserves full screenshot
resolution (up to 10.24M px) and improves click accuracy"
(`_openai_computer_use.py:117-124`). Goose's answer is a **crop tool** with explicit
`originalWidth`/`originalHeight` reporting (`developer/image.rs:19-23, 52-66`).
⇒ **Screenshot resolution/crop policy belongs in the plural strategy space (T1), and is
optimisable.**

### 3.2 Approval gates — six independent implementations, one converged vocabulary

| System | Vocabulary | Evidence |
|---|---|---|
| Claude Agent SDK | `PermissionMode = default \| acceptEdits \| plan \| bypassPermissions \| dontAsk \| auto`; `PermissionBehavior = allow \| deny \| ask`; rules `{tool_name, rule_content}`; updates `addRules/replaceRules/removeRules/setMode/addDirectories/removeDirectories` with destination `userSettings\|projectSettings\|localSettings\|session` | `types.py:25-27, 106-140` |
| | `PermissionResultAllow{updated_input, updated_permissions}` / `PermissionResultDeny{message, interrupt}`; `CanUseTool = (name, input, ctx) -> PermissionResult` | `types.py:235-258` |
| | UI context: `title`, `display_name`, `description`, `blocked_path`, `decision_reason`, `suggestions[]` | `types.py:199-233` |
| **Goose** | `PermissionLevel = AlwaysAllow \| AskBefore \| NeverAllow`; `PermissionConfig{always_allow: Vec<String>, ask_before: Vec<String>, never_allow: Vec<String>}` **persisted to a config file**, managed by `PermissionManager{config_path, permission_map}` | `FD/goose/crates/goose/src/config/permission.rs:18-37` |
| **Goose (autonomy dial)** | `GooseMode = Auto \| Approve \| SmartApprove \| Chat` with human-readable messages: "Automatically approve tool calls" / "Ask before every tool call" / "**Ask only for sensitive tool calls**" / "Chat only, no tool calls" | `FD/goose/crates/goose-provider-types/src/goose_mode.rs:22-32` |
| OpenAI Agents SDK | `Tool.needs_approval: bool \| callable`; durable `RunState.get_interruptions() -> list[ToolApprovalItem]`; `approve(item, always_approve)`, `reject(item, always_reject, rejection_message)` | `tool.py:429-436`; `run_state.py:356-389` |
| ACP | `PermissionOptionKind = allow_once \| allow_always \| reject_once \| reject_always`; `RequestPermissionOutcome = cancelled \| selected`, with the normative rule that a `session/cancel` **MUST** answer all pending permission requests with `cancelled` | `PR/agent-client-protocol/schema/v1/schema.json` `$defs.PermissionOptionKind`, `$defs.RequestPermissionOutcome` |
| Vercel AI SDK | Approval is a **state machine on the tool part**: `input-streaming → input-available → approval-requested → approval-responded → output-available`, each `approval{id, approved?, reason?, isAutomatic?, signature?}` | `packages/ai/src/ui/ui-messages.ts:290-345` |
| A2A | Approval as a **task state**: `TASK_STATE_INPUT_REQUIRED`, `TASK_STATE_AUTH_REQUIRED` | `PR/a2a-spec/specification/a2a.proto:195-208` |
| AG-UI | Capability flags `{supported, approvals, interventions, feedback, interrupts, approve_with_edits}` | `capabilities.py:316-358` |
| LangGraph | `interrupt(value)` + `Command(resume=...)`; documented re-execution semantics: "The graph resumes from the start of the node, **re-executing** all logic" | `FW/langgraph/libs/langgraph/langgraph/types.py:535, 811-827` |
| OpenHands | `[security] confirmation_mode`, `security_analyzer = "llm" \| "invariant"`, `enable_security_analyzer` | `FW2/openhands/config.template.toml:226-236` |

**Six systems independently arrived at `{allow, deny} × {once, always}` plus a reason
string.** Settled vocabulary; PACT should use it verbatim.

**[NEW] Goose already ships the non-technical author's autonomy dial** — and Goose is Bud's
execution home, so D3's superset requirement makes `GooseMode`'s four values a *floor*, not
a design option. `SmartApprove` ("ask only for sensitive tool calls") is a
**classifier-driven** mode, which is exactly D23's blast-radius classification applied at
tool-call time rather than at learning time. PACT should unify the two: one classification
function, two call sites.

Two features only Vercel has, both of which PACT needs:
- **`isAutomatic`** — distinguishes a policy auto-approval from a human decision. Required
  for D23's classifier to be auditable, and for AC-4.4 (a promoted trace must not look like
  a human approved something a rule did).
- **`signature`** — the approval decision is signed. Required because in PACT the approval
  travels in the transcript and the transcript is promotable to an eval case; an unsigned
  approval in a replayable trace is a forgeable authorisation.

**Computer-use-specific gate: model-side safety checks.** Distinct from tool approval. The
OpenAI Responses computer tool returns `pending_safety_checks` that the harness must
explicitly acknowledge in `computer_call_output.acknowledged_safety_checks`
(`_openai_computer_use.py:104-129`). The Agents SDK surfaces it as
`ComputerTool.on_safety_check: (ComputerToolSafetyCheckData) -> bool`
(`tool.py:767-768, 892-906`). **[NEGATIVE] No other framework in the corpus models a
provider-originated safety check.** PACT needs a third approval channel:
`policy.safetyChecks: {autoAcknowledge: false | [codes]}` — defaulting it to
auto-acknowledge would be a silent policy relaxation under T7.

**Error-channel asymmetry.** OpenAI's `computer_call_output` has **no error or text field** —
the only payload is a screenshot, so a failed action (e.g. a bad key name) cannot be reported
to the model; inspect_ai substitutes a 1×1 transparent PNG
(`_openai_computer_use.py:104-113`, comment verbatim). A PACT computer-use loop that relies
on textual error feedback silently loses it on OpenAI. `degraded` lattice entry.

### 3.3 **[NEW]** The no-code computer-tool declaration already exists — in SWE-agent

SWE-agent's browser bundle is declared **entirely in YAML**, backed by executables in
`bin/`, with per-argument `type`, `description`, `required`, and `enum`
(`FW2/swe-agent/tools/web_browser/config.yaml`; 18 executables in `tools/web_browser/bin/`):

```yaml
tools:
  click_mouse:
    signature: "click_mouse <x> <y> [<button>]"
    docstring: "Click at the specified coordinates (shown as a red crosshair) on the current page"
    arguments:
      - {name: x, type: integer, description: "X coordinate", required: true}
      - {name: y, type: integer, description: "Y coordinate", required: true}
      - {name: button, type: string, description: "Mouse button to click (left or right, default: left)",
         required: false, enum: ["left", "right"]}
```

Its 17 actions — `open_site, close_site, screenshot_site, click_mouse, double_click_mouse,
move_mouse, drag_mouse, type_text, scroll_on_page, execute_script_on_page, navigate_back,
navigate_forward, reload_page, wait_time, press_keys_on_page, set_browser_window_size,
get_console_output` — are a **fifth vocabulary**, and they include two affordances no
model-native vocabulary has (`execute_script_on_page`, `get_console_output`) while lacking
OS-level `key`/`hold_key`. This confirms browser and desktop are genuinely different action
domains (open question #2 in §8).

**Media handling is also a declared pipeline stage.**
`history_processors: [{type: image_parsing}]`
(`config/default_mm_with_images.yaml:73-74`) with
`ImageParsingHistoryProcessor.allowed_mime_types: set[str] = {"image/png","image/jpeg","image/webp"}`
(`sweagent/agent/history_processors.py:340-344, 378`), and
`templates.disable_image_processing: false` (`default_mm_with_images.yaml:6`).
**A declarative media-type allowlist attached to a declarative history-transform stage** is
precisely PACT's `strategy.media` shape.

### 3.4 No-code declaration proposal

```yaml
# agents/browser-checker/sandbox.yaml     ← expansion of `sandbox:` (D2 Expansion Rule)
kind: container                 # none | process | container | microvm | remote
image: pact/browser-ubuntu:1    # resolved from a profile, never a literal (F-1)
cpu: 2
memoryMb: 4096
timeoutSeconds: 300
gui:
  width: 1366                   # SINGLE SOURCE OF TRUTH; the computer tool inherits these
  height: 768                   # matches inspect_ai FWXGA (_x11_client.py:38)
  display: 0
  coordinateSpace: pixels       # pixels | normalized — declared, never inferred (§3.1)
network:
  buildTime: allow              # air-gapped profiles force `deny` (§2.5)
  runTime:
    mode: allowlist             # none | allowlist | full
    allow: ["*.mycompany.com", "docs.stripe.com"]
    deny:  ["*.internal"]
mounts:
  - {host: ./fixtures, at: /workspace/fixtures, mode: ro}
env:
  API_BASE: https://staging.mycompany.com
  API_KEY: {secret: staging-api-key}      # never a literal
persist: {snapshot: false, keepAlive: false}
```

```yaml
# agents/browser-checker/policy.yaml      ← expansion of `policy:`
autonomy: supervised            # observe | supervised | smart | autonomous
                                #   ↑ four values, matching GooseMode (D3 superset)
media:                          # from Eve UploadPolicy, but default-deny per ACP
  in:
    accept: ["image/png", "image/jpeg", "application/pdf"]
    maxBytes: 26214400
  onReject: fail                # fail | drop-with-report   (never silent — T7)
approvals:
  default: ask                  # allow | deny | ask
  rules:
    - tool: computer.*
      when: "action in ['type','key'] && target.matches('*password*')"
      decision: ask
      prompt: "The agent wants to type into a password field on {url}. Allow?"
    - tool: computer.navigate
      when: "!(url.host in sandbox.network.runTime.allow)"
      decision: deny
      reason: "Navigation outside the approved domain list."
    - tool: browser.*
      decision: allow
  remember: [allow_always, reject_always]   # which options the UI offers
  timeoutSeconds: 300
  onTimeout: deny                            # fail-closed (T7)
  onCancel: cancelled                        # ACP requires pending requests be answered
safetyChecks:
  autoAcknowledge: false        # provider-originated checks always reach a human
```

Design notes:
- `decision: allow|deny|ask` + `remember: [allow_always, reject_always]` reproduces the
  converged vocabulary exactly; ACP's four option kinds fall out as `decision × remember`;
  Goose's three `PermissionLevel`s fall out as `allow`/`ask`/`deny` with `remember: [always]`.
- `prompt:` is the author-written sentence. Claude's SDK proves the UI wants
  `title`/`display_name`/`description` (`types.py:219-233`); **PACT should *require* a prompt
  for any `ask` rule** so a human sees a domain-meaningful question rather than a JSON blob.
  This is a D13/D18 requirement, not a nicety.
- `when:` needs **one** expression language, shared with the capability predicates (O3.1).
  CEL is in the corpus (`PR/cel-spec`) and is not code, satisfying D14.
- **Fail-closed defaults.** Every other system defaults the other way: Claude's
  `autoAllowBashIfSandboxed` defaults `True` (`types.py:889`); Eve's `allowedMediaTypes`
  defaults `"*"` (`upload-policy.ts:30-34`); Goose's `GooseMode` defaults `Auto`
  (`goose_mode.rs:23-25`). PACT must not.

---

## 4. Deliverable 4 — Eval implications

### 4.1 What DeepEval can actually do (honest sizing for O4.1 / AC-4.1)

- **Images and PDFs only.** `MLLMImage` (`EV/deepeval/deepeval/test_case/llm_test_case.py:39-176`)
  takes `url` **or** (`dataBase64` + `mimeType`), resolves local paths and `file://` URIs
  (`process_url` at 116-128, `is_local_path` at 131-142), and auto-loads base64
  (`_load_base64`, 89-93). PDFs get a distinct placeholder (`_placeholder`, 100-104:
  `[DEEPEVAL:PDF:<id>]` vs `[DEEPEVAL:IMAGE:<id>]`).
- **Media is smuggled through strings.** Multimodal content is not a typed field on
  `LLMTestCase`; it is a marker inside `input`/`actual_output`, re-expanded by
  `parse_multimodal_string` (144-172) against a **process-global** `_MLLM_IMAGE_REGISTRY`
  (line 31).
- **[CORRECTION] A config-only image case *is* reachable today.** The previous revision
  claimed "a purely declarative YAML case cannot populate [the registry] without a provider
  shim". That is wrong: `parse_multimodal_string` falls back to
  `MLLMImage(url=img_id, _id=img_id)` when the id misses the registry
  (`llm_test_case.py:161-163`), and `MLLMImage.__post_init__` resolves a bare local path via
  `is_local_path`/`process_url`. So a YAML case may emit
  `[DEEPEVAL:IMAGE:./fixtures/invoice.png]` and it loads. This *lowers* the cost of PACT's
  DeepEval image-eval provider considerably.
- **Five image metrics total** (`metrics/multimodal_metrics/__init__.py:1-5`):
  `TextToImageMetric`, `ImageEditingMetric`, `ImageCoherenceMetric`, `ImageHelpfulnessMetric`,
  `ImageReferenceMetric`. All LLM-judged; all require a vision-capable judge.
- **[NEGATIVE] Zero audio support.** `grep -rn "audio\|Audio" --include=*.py deepeval/`
  returns **no hits** (re-verified). No audio test-case field, no audio metric, no audio
  judge path.
- **[NEGATIVE] Conversational turns are text-only.** `Turn{role: Literal["user","assistant"],
  content: str, user_id, retrieval_context, tools_called, mcp_tools_called,
  mcp_resources_called, mcp_prompts_called, metadata}`
  (`test_case/conversational_test_case.py:59-81`). A voice turn is not representable — only
  its transcript. Note the multi-turn case *does* extract image ids from turn strings
  (`_get_images_mapping`, `:324-350`), so images survive in conversations via the same
  placeholder hack; audio has no equivalent.

**Therefore: "config-only expression of every DeepEval metric" (O4.1) is satisfiable for text
and image and *vacuous* for audio and computer use — because DeepEval has nothing there.**
The coverage matrix must say so rather than quietly scoping the claim to text.

### 4.2 What the rest of the ecosystem can do

**inspect_ai** has the most complete eval-side content model:
`Content = ContentText | ContentReasoning | ContentImage | ContentAudio | ContentVideo |
ContentData | ContentToolUse | ContentDocument` (`EV/inspect_ai/src/inspect_ai/_util/content.py`).
`ContentAudio.format: 'wav'|'mp3'`, `ContentVideo.format: 'mp4'|'mpeg'|'mov'`,
`ContentImage.detail: 'auto'|'low'|'high'|'original'`, `ContentDocument` auto-derives
`filename` and `mime_type` from a path or data URI. It also owns the only cross-provider
computer tool (§4.4). **But its scorers are Python.**

**promptfoo** has the best *no-code authoring* story:
- A YAML var written `file://path/to/x.png` is auto-detected by extension and loaded as
  base64, gated by `PROMPTFOO_DISABLE_MULTIMEDIA_AS_BASE64`
  (`EV/promptfoo/src/evaluatorHelpers.ts:306-330`); `collectFileMetadata` tags each var
  `{path, type: image|video|audio, format}` (121-150); PDFs are text-extracted
  (`extractTextFromPDF`, defined 35, called 305).
- Result payloads carry typed
  `audio{data, blobRef, transcript, format, sampleRate, channels, duration}`,
  `video{blobRef, format, size, duration, thumbnail, spritesheet, model, aspectRatio,
  resolution}`, `images[]` (`src/types/index.ts:433-458`), backed by a content-hash
  `BlobStorageProvider` (`src/blobs/types.ts:18-32`).
- **[NEW] It ships a declarative trajectory assertion family** — the single most reusable
  thing in the corpus for D16 computer-use evals:

  | Assertion | Value shape | Evidence |
  |---|---|---|
  | `trajectory:tool-used` | step matcher `{name \| pattern}` | `src/assertions/index.ts:147`, `types/index.ts:655` |
  | `trajectory:tool-sequence` | `{mode: 'exact'\|'in_order', steps: (string \| StepMatcher)[]}` | `src/assertions/trajectory.ts:22-25` |
  | `trajectory:step-count` | `{name\|pattern, min?, max?}` | `trajectory.ts:17-21` |
  | `trajectory:tool-args-match` | `{name\|pattern, args, mode: 'exact'\|'partial', defaults, ignore}` | `trajectory.ts:32-38` |
  | `trajectory:goal-success` | `string` or `{goal: string}` — LLM-graded | `trajectory.ts:26-28`, listed in `MODEL_GRADED_ASSERTION_TYPES` (`index.ts:133`) |

  All five read **OTel trace spans** (`getTraceOrThrow`, `trajectory.ts:39-46`; the
  `TRACE_AWARE_ASSERTION_TYPES` set at `index.ts:135-148` also contains
  `trace-error-spans`, `trace-span-count`, `trace-span-duration`). ⇒ **PACT should adopt this
  family and its trace-backed implementation**, which also means **tracing is a prerequisite
  for computer-use evals**, not an optional observability feature.

**[NEGATIVE] No project in the corpus has an audio-native assertion.** promptfoo's
`src/assertions/` has **57** files and none consume audio; `audio.transcript` exists
precisely so text assertions apply to a transcript.

**[NEGATIVE] No project in the corpus has a declarative *environment-state* assertion.**
- terminal-bench grades by running **pytest inside the container**: `parser_name: pytest`
  in `task.yaml`, `run-tests.sh` invoking `uv run pytest $TEST_DIR/test_outputs.py -rA`, and
  `tests/test_outputs.py` containing hand-written Python
  (`assert solution_path.read_text().strip() == "26160"`). Its five parsers are
  `pytest`, `mlebench`, `swebench`, `swelancer`, `sweperf` (`terminal_bench/parsers/`).
- inspect_ai expresses final-state checks in Python scorers.
- promptfoo's `sql` assertion is a **syntax validity check on model output**
  (`src/assertions/sql.ts:1-30`, node-sql-parser), not a database query.

### 4.3 The eval cases D16 demands, written the way a non-coder would write them

**(A) A screenshot / vision task — buildable today**

```yaml
# evals/cases/invoice-total.yaml
case: invoice-total
input:
  - text: "What is the invoice total?"
  - image: ./fixtures/invoice-2024-11.png       # file:// semantics, promptfoo-style
expect:
  - contains: "1,248.50"                        # deterministic first (AC-4.5)
  - not_contains: ["I can't", "unable to"]
  - metric: deepeval:answer_relevancy           # judge only if needed
    threshold: 0.8
```
Machinery required: promptfoo already resolves `file://x.png`
(`evaluatorHelpers.ts:306-330`); DeepEval's `MLLMImage` accepts a bare local path and the
`[DEEPEVAL:IMAGE:<path>]` fallback works (§4.1 correction). The only new work is desugaring
`image:` into the provider's content part. **Ship this in v1 with confidence.**

**(B) A computer-use task — mostly buildable, one new assertion family**

```yaml
# evals/cases/cancel-subscription.yaml
case: cancel-subscription
environment:
  kind: vm-snapshot                             # replay | simulated | vm-snapshot | live
  sandbox: ./environments/billing-app.yaml      # a sandbox.yaml, same schema as §3.4
  reset: snapshot://billing-app@clean           # deterministic start state
input:
  - text: "Cancel the Pro subscription for acme-corp."
expect:
  # --- existing prior art: promptfoo trajectory family, trace-backed ---
  - trajectory:tool-used: {name: computer, args: {action: screenshot}}
  - trajectory:step-count: {pattern: "computer", max: 25}
  - trajectory:tool-args-match:
      name: computer
      mode: partial
      args: {action: navigate}
      ignore: [coordinate]
  - not:
      trajectory:tool-used: {name: computer, args: {action: type}}
  # --- NEW WORK: declarative environment-state assertion ---
  - final_state:
      http: {method: GET, path: /api/subscriptions/acme-corp}
      json_path: $.status
      equals: "cancelled"
  # --- NEW WORK: approval assertion ---
  - approvals:
      required: [computer.click@confirm-cancel]
      forbidden_automatic: true                 # must have been a human, not `isAutomatic`
  - slo: {e2e_p95_seconds: 90, cost_usd_max: 0.40, screenshots_max: 25}
```

The load-bearing move is `final_state:` — **a computer-use eval is graded on environment
state, not on model text.** The OS-agents survey names this the task-level criterion:

> "Task-level evaluation centers on the final output and evaluates whether the agent reaches
> the desired final state. The two main criteria are task completion and resource
> utilization." — `2508.04482-os-agents-survey.pdf` §4.1.2 (extracted lines 1670-1673)

and the same section names the two other metric families PACT should adopt verbatim:
**step-level** (action-grounding accuracy, element match by ID *or* position, step SR;
"a given task may have various valid paths", so step-level alone is insufficient — extracted
lines 1651-1668) and **efficiency** (`Step Ratio` = agent steps ÷ human-optimal steps, `API
Cost`, `Execution Time`, `Peak Memory Allocation` — extracted lines 1679-1690).
⇒ PACT SLO vocabulary should include **`step_ratio`** alongside latency and cost.

**Proposed `final_state` assertion family (new work):**
`http` · `file{path, exists|contains|sha256}` · `sql{query, equals}` ·
`shell{command, exit_code, stdout_matches}` · `sandbox_file{path, contains}`. Each must be
executable **inside the declared sandbox** (so it works air-gapped) and must not require the
author to write code — which is exactly where terminal-bench stops and PACT must continue.

**Environment typing — four values, not three. [CORRECTION]** The previous revision proposed
`replay | simulated | live`. The survey's taxonomy is static vs interactive, with interactive
splitting into simulated and real-world (§4.2.2, extracted lines 1729-1758) — and it
classifies **OSWorld's VMs as real-world**, not simulated. But a VM snapshot *is*
reproducible. So the reproducibility axis and the fidelity axis are independent, and PACT
needs:

| `environment.kind` | Reproducible? | Air-gappable? | CI-gateable by default? | Corpus example |
|---|---|---|---|---|
| `replay` | yes (cached pages / recorded traces; one-step only) | yes | yes | Mind2Web "captures comprehensive snapshots … enabling seamless offline replay" (extracted 1740-1742); OpenHands `replay_trajectory_path` (`config.template.toml:36`) |
| `simulated` | yes ("to avoid the reproducibility issues caused by the dynamic nature of real-world environments", extracted 1751-1753) | yes | yes | FormWoB, virtual apps |
| `vm-snapshot` | yes, if `reset:` is declared | yes (if the image is local) | yes | OSWorld VMs; terminal-bench `docker-compose.yaml` + `Dockerfile` per task |
| `live` | **no** ("continuously updating nature of the environment, uncontrollable user behaviors, and diverse device setups", extracted 1756-1758) | no | **no — excluded from the gate, flagged in the Portability Report** | real sites/apps |

**(C) A voice turn — and why it cannot be written today**

```yaml
# evals/cases/refund-voice.yaml     ← ASPIRATIONAL; see §5
case: refund-voice
session: duplex
turns:
  - user: {audio: ./fixtures/refund-request.wav}
    expect:
      - transcript_contains: ["order number"]
      - slo: {ttft_ms_p95: 800}          # voice TTFT ≠ batch E2E (D16)
      - barge_in: allowed
      - audio: {max_silence_ms: 1200}
```
Blockers, each verified:
1. DeepEval has zero audio (§4.1) — no metric, no test-case field.
2. `Turn.content: str` (`conversational_test_case.py:59-61`) — the multi-turn model cannot
   hold audio.
3. No local TTS and no local duplex model exists in the corpus (§2.5), so an air-gapped
   voice eval cannot run end-to-end.
4. **Barge-in / turn-taking has no assertion vocabulary anywhere.** The closest primitives
   are `RealtimeTurnDetectionConfig.interrupt_response` (`realtime/config.py:108-109`) and
   the `speech-started`/`speech-stopped` server events
   (`realtime-model-v4-server-event.ts`). Signals exist; assertions do not.

**Realistic v1:** grade a voice turn on its **transcript plus timing**, keeping the audio as
an artifact for human review. This is honest and implementable: transcripts flow through
every existing text metric; `input-transcription-completed` / `audio-transcript-done` give
both sides; promptfoo already stores `audio.transcript` alongside `audio.data`
(`src/types/index.ts:433-442`).

**Open design question this forces (§8.4):** if the case supplies a `.wav` and the binding is
cascaded, **the STT model becomes part of the system under test**. PACT should let an eval
pin a reference transcript to isolate the agent from STT variance —
`expect: [{transcript_equals_reference: ./fixtures/refund-request.txt}]` — otherwise a
change of STT model shows up as an agent regression.

### 4.4 Modality-aware SLOs (D16 explicitly requires this)

Voice SLO quantities are *different quantities*, not tighter thresholds:
- `prefix_padding_ms`, `silence_duration_ms`, `idle_timeout_ms`, `threshold`, `eagerness`
  (`openai-agents realtime/config.py:96-124`) determine perceived latency more than model
  TTFT does.
- `TTSModelSettings.buffer_size = 120` ("minimal size of the chunks of audio data that are
  being streamed out") and a sentence-based `text_splitter`
  (`voice/model.py:31-58`) — the cascaded pipeline's TTFT is dominated by the splitter, not
  the LLM.
- Audio is billed **per audio-token and per second** in the catalogue
  (`input_cost_per_audio_token`, `input_cost_per_audio_per_second`,
  `output_cost_per_audio_token`, `cache_creation_input_audio_token_cost` in
  `RO/litellm/model_prices_and_context_window.json`), so `cost_usd_max` needs a
  modality-aware cost model, not token counts.
- Image cost is driven by resolution/detail (`detail: original` = "up to 10.24M px",
  `_openai_computer_use.py:117-119`), so a computer-use SLO must budget **screenshots per
  run**. inspect_ai already parameterises this: `computer(max_screenshots: int | None = 1,
  timeout: int | None = 180)` (`_computer.py:74`).

**Proposed SLO vocabulary additions:** `ttft_ms` (voice), `turn_latency_ms`, `barge_in_ms`,
`screenshots_per_run`, `step_ratio` (from the OS survey), `audio_seconds_in/out`,
`cost_usd` — all percentile-qualified per O4.2.

---

## 5. Deliverable 5 — What is genuinely NOT ready (scope down honestly)

Ranked by how badly a v1 promise would hurt.

| # | Claim that would be false | Verified basis | Recommended v1 scope |
|---|---|---|---|
| 1 | "Config-only evals for voice turns" | DeepEval has **zero** audio code; `Turn.content: str`; no audio assertion in promptfoo's 57 assertion files; no local TTS/duplex model in the corpus | **Transcript + timing only.** Audio retained as an artifact. State it in the coverage matrix. |
| 2 | "Portable computer use" | **Five** action vocabularies; **three** coordinate spaces; inspect_ai's Gemini bridge maps unmapped actions to `wait_5_seconds` **as a no-op** (`_google_computer_use.py:152-156`); `triple_click → double_click` and `hold_key → Keypress` (dropping `duration`) on OpenAI (`_openai_computer_use.py:159-172`); OpenAI's `computer_call_output` has no error channel; Anthropic's action set changes per dated tool version | Define **one PACT action vocabulary** + per-target mapping tables with **mandatory loss reports**. Ship `browser` first; desktop `mac/windows/ubuntu` as `experimental`. |
| 3 | "The model catalogue tells you what a model can do" | 12.1% `supported_modalities` coverage; 28.9% of entries have no capability key; 293/297 Claude entries lack `supported_modalities`; `supports_computer_use` absent on `computer-use-preview`; models.dev has no `computer_use`; LangChain ships a hand-maintained override TOML with no provenance | Catalogue is a **pre-filter only** (R5). Tri-state with `unknown`. `strict` refuses unprovenanced fields. Add a `probe` level. |
| 4 | "Video is first class" | MCP has no video in **any** schema version; Anthropic has none; AutoGen has none; Claude Agent SDK has none; pydantic-ai raises `NotImplementedError` on **both** OpenAI surfaces | Video **in** = supported where the binding supports it, `unsupported` elsewhere. Video **out** = out of scope for v1. |
| 5 | "Media round-trips through the Expansion Rule" | base64 in `canonical.json` is a known blow-up (OpenHands flag comment; SWE-agent's 10 MB observation cap) | Content-addressed blob store + `blob:` refs; inline only under a profile threshold; **digest becomes a Merkle root** (§1.4). |
| 6 | "Tool results can be multimodal everywhere" | AutoGen `FunctionExecutionResult.content: str`; Claude Agent SDK drops audio and binary resources with a log warning (`__init__.py:512, 516`); tool-return MIME allowlists are model-specific and narrow (5 types, Gemini 3+ only) | `degraded` lattice entries with reports; harness fallback = emit media as a following user part, or Eve-style text reference. |
| 7 | "Audio streaming works in the agent loop" | Files are atomic stream parts in Vercel v4; pydantic-ai has no `FilePartDelta`; duplex audio lives in a *separate model interface* or *separate pipeline* everywhere | Model voice as a distinct **session shape** with a separate `realtime` model-role binding. |
| 8 | "Air-gapped multimodal eval" | DeepEval multimodal metrics require a vision-capable judge; no local TTS anywhere; terminal-bench-style graders `curl` from the network at test time | Require a declared **local vision judge** in the profile; separate build-time from run-time network in the environment declaration. |
| 9 | "Computer-use evals are deterministic" | Only static / simulated / snapshot-reset environments are reproducible; live sites explicitly called out as non-reproducible (OS survey §4.2.2) | Type the environment `replay\|simulated\|vm-snapshot\|live`; exclude `live` from CI gates by default. |
| 10 | "Safety checks are handled" | Provider-originated `pending_safety_checks` exist **only** in the OpenAI path | Third approval channel, default **not** auto-acknowledged. |
| 11 | **[NEW]** "The same folder behaves the same on every runtime, for media" | Eve demotes oversized/unsupported media to a text path (`attachment-staging.ts:259-287`); Goose promotes a text path to an image (`images.rs:36-100, 202-241`). Two PACT targets, opposite implicit transforms | Make promotion/demotion an **explicit declared lowering rule** with a loss report; forbid adapter heuristics; add a CTS fixture that pins the behaviour. |
| 12 | **[NEW]** "Modality capability can be read off the adapter" | Pydantic AI derives capability by substring-matching the model name (`profiles/google.py:61`, `profiles/openai.py:314-317`); inspect_ai by version regex | The catalogue is authoritative; adapter guesses that disagree are a **reported conflict**, and the lockfile records which source decided. |

**Things that ARE ready and should be promised confidently:**
- Image input, document/PDF input, and provider-file-ID references across all seven targets
  (modulo AutoGen's tool-result gap).
- The **source union** `{bytes | url | provider-ref | text}` + MIME — eight systems agree.
- The approval vocabulary `{allow, deny} × {once, always}` + reason — **six** independent
  implementations agree, including Goose (D3 superset target).
- Sandbox declaration — eight systems, a clear common field set, `{type, config}` adapter
  seam already proven by inspect_ai.
- **Declarative trajectory assertions** — promptfoo ships five, trace-backed, config-only.
- Config-only **image** evals — promptfoo's `file://` loading + DeepEval's five image metrics
  + the `[DEEPEVAL:IMAGE:<path>]` fallback cover it end to end.
- **Eve's staging/hydration ladder** — a proven, shipping media degradation strategy.
- Modality-aware cost data — LiteLLM already carries per-audio-token and per-second pricing.

---

## 6. Recommended v1 conformance scoping

| Feature | v1 level | Rationale |
|---|---|---|
| `image` in (url/bytes/path/providerRef) | **native** on all 7 | universal |
| `document`/PDF in | **native** on 5, `degraded` AutoGen / Claude-SDK | §1.2 |
| `image` out (model-generated) | **native** Pydantic AI / Vercel / OpenAI Agents; **`unsupported`** Anthropic-family | `content_block.py` has no image member |
| **media→path fallback** (oversized/unsupported → text reference) | **native** wherever `filesystem.tools` is available | Eve `attachment-staging.ts:259-287` |
| `audio` in — cascaded (STT → text) | **native** everywhere (STT is a separate model role) | works even where the message model has no audio |
| `audio` in — native to the model | **native** Pydantic AI (Chat Completions, **wav/mp3 only**) / LangChain / Vercel; **error** on OpenAI Responses; `unsupported` elsewhere | `models/openai.py:1668-1674, 3470` |
| `audio` out / duplex voice | **native** only where a `realtime` model role is bound (Vercel, OpenAI Agents); `emulated` via TTS elsewhere | separate interface everywhere |
| `video` in | `native` on 3, `unsupported` on 4; **`unsupported` for all MCP tools**; **error** on both OpenAI surfaces in pydantic-ai | MCP `ContentBlock` lacks video |
| `computer_use` — browser | **native** OpenAI Agents / Vercel-Anthropic; **harness-lowered** elsewhere via an MCP browser tool | PACT owns the action vocabulary (D12) |
| `computer_use` — desktop (X11) | `experimental` | geometry duplication + action drift + 3 coordinate spaces |
| Tool approval gates | **native** on 6 of 7 (AutoGen via harness) | converged vocabulary |
| Provider safety checks | **native** OpenAI only; `unsupported` reported elsewhere | |
| Sandbox declaration | **native** via `{kind, config}` seam | D24: adapter-shaped, minimal |
| Trajectory assertions | **native** wherever tracing is on | promptfoo family |
| `final_state` assertions | **native** wherever `sandbox.kind != none` | new work |

---

## 7. Superset check against `bud.dev/v1` and Goose (D3)

| Existing feature | Evidence | PACT expression |
|---|---|---|
| `input.dictation{enabled, provider: openai\|groq\|elevenlabs\|local\|default, model, maxAudioBytes}` | `sdk-and-declarative-dev.md:2519-2527` | `models.roles.stt: {provider, model, maxBytes}` + `interface.input.audio.mode: transcribe` |
| Local Whisper for air-gapped transcription | `sdk-and-declarative-dev.md:2549-2553` | `profiles/airgapped.yaml` binds `stt` to a local model |
| "channels can use dictation for voice attachments, but the transcribed text is still run input" | `sdk-and-declarative-dev.md:2554-2556` | the **cascaded** mode. PACT must be a strict superset: also `interface.input.audio.mode: native` and `session: duplex`. |
| `security.sandbox.profile: inherit` | `sdk-and-declarative-dev.md:2160-2161` | `sandbox: {profile: <name>}` with profile inheritance (F-1) |
| `security.promptInjection.action: require_approval` | `sdk-and-declarative-dev.md:2153-2155` | `policy.approvals.rules[].when: injection_detected` |
| `policy.toolOrigin.mode: off\|audit\|ask_on_cross_origin\|deny_sensitive` | `sdk-and-declarative-dev.md:2147-2149` | `policy.approvals.rules` with an origin predicate |
| Parity-contract label "image behavior such as local marker extraction or unsupported MIME types" | `sdk-and-declarative-dev.md:2094` | formalised as `lattice[adapter][provider].media[mediaType] = native\|emulated\|degraded\|unsupported` |
| MCP prompt/resource content "structured text, image, resource, and resource-link" | `sdk-and-declarative-dev.md:1588-1589` | maps to the PACT part model directly |
| **[NEW] Goose `GooseMode = Auto\|Approve\|SmartApprove\|Chat`** | `goose_mode.rs:22-32` | `policy.autonomy: autonomous\|supervised\|smart\|observe` — **four values are a floor** |
| **[NEW] Goose `PermissionConfig{always_allow, ask_before, never_allow}`** | `config/permission.rs:24-30` | `policy.approvals.rules` desugars to these three lists for the Goose adapter |
| **[NEW] Goose `ImageTool{source, crop{x,y,width,height}}`, 20 MiB cap** | `developer/image.rs:14-36` | a first-party PACT tool, with `crop` in the strategy space |
| **[NEW] Goose implicit text-path→image promotion** | `images.rs:36-100` | must become an **explicit** `strategy.media.promotePathsInToolOutput: bool` (default `false`), reported when enabled |

No modality feature in the Bud manifest or in Goose is inexpressible in the proposed model.
The two places PACT **must go beyond** them are **duplex voice** (Bud degrades voice to text
before the run) and **explicit media promotion** (Goose does it implicitly).

---

## 8. Open questions for the architecture doc

1. **Does `canonical.json` carry blob bytes at all, ever?** Recommendation: never (refs
   only) — but then the artifact digest (O1.2) must be a **Merkle root** over
   `hash(canonical.json)` plus each referenced blob, not a single file hash. Signing and
   caching both change shape.
2. **One action vocabulary or a family?** SWE-agent's browser bundle (`execute_script_on_page`,
   `get_console_output`, no OS-level keys) versus inspect_ai's desktop set (`hold_key`,
   `cursor_position`, `zoom`) is direct evidence that browser and desktop are different
   domains. Options: one superset with per-environment `supported` subsets, versus
   `computer.browser.*` and `computer.desktop.*` as distinct resource kinds. Leaning:
   distinct kinds, because a single superset makes every unsupported action a runtime
   surprise rather than a resolve-time failure.
3. **Does a media part carry its own retention/redaction policy?** AC-4.4 requires
   trace→eval promotion "preserving redaction policy". A screenshot may contain PII the text
   does not. Suggests `retention: {redact: [pii], ttlDays: 30}` on the part.
4. **Where does the STT/TTS boundary sit for eval replay?** If a case supplies a `.wav` and
   the binding is cascaded, the STT model is inside the system under test. Should a case be
   able to pin a reference transcript (§4.3C)? My view: yes, and it should be the default
   for regression suites.
5. **Screenshot pruning and resolution as strategy variables.** SWE-agent's
   `LastNObservations{n, polling, always_keep_output_for_tags, always_remove_output_for_tags}`
   (`history_processors.py:114-129`), inspect_ai's `max_screenshots`
   (`_computer.py:74`), Goose's `crop` (`developer/image.rs:19-23`), and OpenAI's
   `detail: original` (`_openai_computer_use.py:117-124`) are four independent knobs that
   measurably change accuracy and cost. Put them in the **plural strategy space** so the
   optimiser can tune them — an attractive target for D9's end-to-end demo.
6. **`allowed_callers` on provider tools** (`beta_tool_computer_use_20250124_param.py:29-31`)
   lets a computer tool be invoked *from inside* a code-execution sandbox. That is a
   nested-capability model PACT has no vocabulary for yet.
7. **Should PACT ship the normalised computer tool as an MCP server** (making it a no-code
   `tools/computer.yaml` reference) rather than a built-in? That satisfies D14 with zero new
   concepts, at the cost of an MCP round-trip per action — and MCP has `ImageContent`, so
   screenshots round-trip fine. Counter-argument: MCP has no video and no structured
   coordinate-space negotiation.
8. **[NEW] Do PACT's own eval assertions run inside the sandbox?** `final_state` must, for
   air-gap and for `shell`/`file` assertions. That makes the eval runner a sandbox client,
   which couples the eval layer to the substrate layer in a way §7.1's L-model does not
   currently admit.
9. **[NEW] Does the media part model make `kind` authoritative or derived?** I recommend
   `mediaType` authoritative and `kind` derived by a normative table, but two authors writing
   `kind: document` + `mediaType: image/png` must get a loud error, and the table itself is
   then a versioned normative artifact that adapters must agree on.
