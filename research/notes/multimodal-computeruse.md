# PACT Research Stream — Multimodal & Computer Use (D16)

**Author:** research subagent, stream `multimodal-computeruse`
**Date:** 2026-07-26
**Binding inputs read:** `docs/00-THESIS.md`, `docs/01-DECISIONS.md` (D2, D3, D12, D13, D14, D15, D16, D17, D18, D19, D22, D23, D24)
**Prior in-repo work checked for overlap:** `gaia-ai-runtime/research/SYNTHESIS.md` — grep for
`modal|vision|audio|computer.use|screenshot` returns **zero substantive hits** (only the word
"vision" in "vision doc"). This stream is new ground; nothing here restates F1–F6.

**Evidence convention.** Every factual claim below carries `path:line`. Claims marked
**[INFERRED]** are my synthesis, not something I read. Claims marked **[NEGATIVE]** are
absence-of-feature findings verified by grep returning zero.

Repo roots abbreviated:
- `FW/` = `/home/bud/ditto/agent-inter-op/research/repos/frameworks/`
- `FW2/` = `/home/bud/ditto/agent-inter-op/research/repos/frameworks2/`
- `EV/` = `/home/bud/ditto/agent-inter-op/research/repos/eval/`
- `PR/` = `/home/bud/ditto/agent-inter-op/research/repos/protocols/`
- `RT/` = `/home/bud/ditto/agent-inter-op/research/repos/runtime/`
- `RO/` = `/home/bud/ditto/agent-inter-op/research/repos/routing/`

---

## 0. Executive summary — the five things that change the design

1. **The industry has already converged on one content shape, and it is not "one part type per
   modality".** It is a single **media-typed part with a source union**: Vercel AI SDK v4
   (`FilePart{mediaType, data: data|url|reference|text}`), A2A (`Part{oneof text|raw|url|data} +
   filename + media_type`), and LangChain's `FileContentBlock` all land on it. Pydantic AI and
   MCP still use per-modality classes. PACT should adopt the media-typed-part shape as canonical
   and *derive* per-modality convenience in the loader — because the per-modality unions are the
   ones that keep needing new members (LangChain literally has a comment listing "3D models,
   tabular data" as future modalities at `FW/langchain/libs/core/langchain_core/messages/content.py:785-787`).

2. **Modality support diverges more by (framework × provider-API) than by framework.** Pydantic AI
   supports audio input on OpenAI **Chat Completions** (`FW/pydantic-ai/pydantic_ai_slim/pydantic_ai/models/openai.py:1668-1674`)
   and raises `NotImplementedError` for the same content on OpenAI **Responses**
   (`.../models/openai.py:3469-3470`). A per-framework capability lattice is therefore too coarse;
   the lattice key must be `(adapter, provider, api-surface, model)`.

3. **Audio is not a message type in most of the target frameworks — it is a separate subsystem.**
   `audio` appears **0 times** in `FW/openai-agents-python/src/agents/items.py` and `agent.py`;
   it lives in `voice/` and `realtime/`. The Claude Agent SDK's `ContentBlock` union has no image
   or audio member at all (`FW/claude-agent-sdk-python/src/claude_agent_sdk/types.py:994-1002`), and
   its MCP tool-result converter **silently drops audio with a log warning**
   (`FW/claude-agent-sdk-python/src/claude_agent_sdk/__init__.py:514-518`). PACT must model voice as
   a distinct **session shape** (realtime duplex) with a **cascaded fallback** (STT → text agent →
   TTS), not as "just another content part".

4. **Computer use has four incompatible action vocabularies and no model-catalogue truth.**
   Anthropic (versioned: `computer_20241022` / `_20250124` / `_20251124`), OpenAI Responses
   (`Click/DoubleClick/Drag/Keypress/Move/Screenshot/Scroll/Type/Wait`), Google Gemini
   (`click_at/hover_at/type_text_at/scroll_at/drag_and_drop/wait_5_seconds/open_web_browser/navigate`),
   and shell-command bundles (SWE-agent). `inspect_ai` is the only project in the corpus that
   normalises across all three native vocabularies (its own 22-action `Action` literal at
   `EV/inspect_ai/src/inspect_ai/tool/_tools/_computer/_computer.py:19-40`, parameter set frozen at
   `:46-58`) — and its Gemini mapping is **explicitly lossy**:
   "actions without Gemini equivalents (screenshot, triple_click, cursor_position, etc.) map to
   wait_5_seconds as a no-op" (`EV/inspect_ai/src/inspect_ai/model/_providers/_google_computer_use.py:152-156`).
   Meanwhile LiteLLM's catalogue marks 166 models `supports_computer_use: true` — **all Anthropic
   plus two Gemini — and omits the flag entirely on OpenAI's own `computer-use-preview`.**

5. **Config-only evaluation of a voice turn is impossible today with DeepEval, and it is not close.**
   `grep -rn "audio" deepeval/` returns **zero hits** across the whole Python package. DeepEval's
   multimodal surface is 5 image metrics (`EV/deepeval/deepeval/metrics/multimodal_metrics/__init__.py:1-5`)
   over an image/PDF-only `MLLMImage` that is embedded in strings as `[DEEPEVAL:IMAGE:<id>]`
   placeholders (`EV/deepeval/deepeval/test_case/llm_test_case.py:100-105`), and
   `Turn.content: str` (`EV/deepeval/deepeval/test_case/conversational_test_case.py:59-61`).
   D16 + D19 + G4 cannot all be satisfied by "DeepEval parity". PACT needs a **native eval
   provider** for audio and computer-use, with DeepEval as one provider among several.

---

## 1. Deliverable 1 — A content-type model for agent I/O

### 1.1 Framework-by-framework survey (source-read)

#### 1.1.1 Pydantic AI (highest-priority adapter, D5)

File: `FW/pydantic-ai/pydantic_ai_slim/pydantic_ai/messages.py` (3583 lines).

| Construct | Line | Notes |
|---|---|---|
| `AudioMediaType` | 82 | Closed literal: wav, mpeg, ogg, flac, aiff, aac |
| `ImageMediaType` | 83 | Closed literal: jpeg, png, gif, webp |
| `DocumentMediaType` | 84-94 | pdf, txt, csv, docx, xlsx, html, md, doc, xls |
| `VideoMediaType` | 95-104 | mkv, mov, mp4, webm, flv, mpeg, wmv, 3gpp |
| `FileUrl` (ABC) | 212 | `url`, `force_download`, `vendor_metadata`, `_media_type`, `_identifier` |
| `VideoUrl` / `AudioUrl` / `ImageUrl` / `DocumentUrl` | 301 / 360 / 407 / 453 | four separate classes |
| `TextContent` | 503 | text + `metadata` **not sent to the LLM** |
| `BinaryContent` | 535 | `data: bytes` + `media_type` (open `str` escape) + `vendor_metadata` |
| `BinaryImage` | 697 | narrowed subclass, validated `image/*` |
| `CachePoint` | 720 | in-band cache boundary marker with `ttl: '5m'|'1h'` |
| `UploadedFile` | 769 | `file_id` + `provider_name` (closed literal of 8 providers, 750-759) |
| `MultiModalContent` union | 896-904 | discriminated on `kind` |
| `UserContent` | 916 | `str \| TextContent \| MultiModalContent \| CachePoint` |
| `ToolReturn` | 930 | `return_value` + `content: Sequence[UserContent]` + `metadata` |
| `FilePart` (model **output**) | 1898 | wraps `BinaryContent`; `provider_name`, `provider_details` |

Three design ideas here are worth stealing outright:

- **Stable content identifier.** `BinaryContent.identifier` is `sha1(data)[:6]`
  (`messages.py:204-208`, `625-640`) so a model can refer to a specific file by ID in a later tool
  call. The docstring is explicit that this identifier is only auto-passed when the content is a
  *tool return*, and that a user-message file needs a separate text part naming it (`messages.py:630-636`).
- **`force_download` with SSRF policy as a typed field** — `False | True | 'allow-local'`
  (`messages.py:145-152`, `220-227`): "blocks private IPs and cloud metadata". A URL-valued content
  part is an SSRF vector and the *policy* is part of the content type.
- **`vendor_metadata` is documented per-provider** (`messages.py:229-238`) — e.g. Google video
  metadata / `media_resolution`, OpenAI/xAI/Groq/Mistral `detail`. This is the escape hatch that
  keeps the closed union usable.

**[NEGATIVE] Model profiles carry no input-modality flags.** `ModelProfile`
(`FW/pydantic-ai/pydantic_ai_slim/pydantic_ai/profiles/__init__.py:40-121`) has
`supports_tools`, `supports_tool_return_schema`, `supports_json_schema_output`,
`supports_json_object_output`, `supports_image_output`, `supports_inline_system_prompts`,
`supports_thinking`, `thinking_always_enabled`, `supported_native_tools` — and **no**
`supports_vision`, `supports_audio_input`, `supports_video_input`, `supports_computer_use`.
Consequence: PACT cannot source modality capability from Pydantic AI; it must own a catalogue.

**[NEGATIVE] No computer use.** `native_tools/__init__.py:15-33` lists `WebSearchTool`,
`XSearchTool`, `CodeExecutionTool`, `WebFetchTool`, `ImageGenerationTool`, `MemoryTool`,
`MCPServerTool`, `FileSearchTool`, `AdvisorTool` — no computer tool. Confirmed by the handler
comment `# Pydantic AI doesn't yet support the ComputerUse built-in tool`
(`.../models/openai.py:2287-2288`), where `ResponseComputerToolCall` is `pass`-ed. Adjacent
`LocalShellCall` is also unsupported (`.../models/openai.py:2292-2294`).

**Streaming.** Delta parts are `TextPartDelta` (2982), `ThinkingPartDelta` (3032),
`ToolCallPartDelta` (3143). **There is no `FilePartDelta`** — binary content is atomic in the
stream. `ModelResponseState` (`messages.py:124-140`) distinguishes
`complete|incomplete|suspended|interrupted`, where `suspended` covers Anthropic `pause_turn` /
OpenAI background mode.

**Telemetry.** `_otel_messages.py` models media for traces as `MediaUrlPart` (48-50, four url
kinds), `UriPart` (53-66, with `modality: image|audio|video` + `mime_type`), `FilePart` (69-75,
`file_id` + `mime_type`), `BinaryDataPart` (78-81), `BlobPart` (84-97, `modality` + `mime_type` +
inline base64). `InstrumentationSettings.include_content` gates whether payload is recorded at all
(`messages.py:198-199`).

#### 1.1.2 LangChain / LangGraph (LangGraph reuses LangChain messages)

File: `FW/langchain/libs/core/langchain_core/messages/content.py` (1488 lines).

| Block | Line | Payload fields |
|---|---|---|
| `TextContentBlock` | 207 | `text`, `annotations` |
| `ToolCall` / `ToolCallChunk` / `InvalidToolCall` | 247 / 291 / 336 | |
| `ServerToolCall` / `ServerToolCallChunk` / `ServerToolResult` | 372 / 397 / 425 | provider-executed tools |
| `ReasoningContentBlock` | 456 | |
| `ImageContentBlock` | 498 | `file_id` \| `url` \| `base64`; `mime_type`; `index` (streaming) |
| `VideoContentBlock` | 549 | same shape |
| `AudioContentBlock` | 600 | same shape |
| `PlainTextContentBlock` | 651 | + `text`, `title`, `context` (Anthropic citations) |
| `FileContentBlock` | 721 | catch-all for PDFs/docs |
| `NonStandardContentBlock` | 790 | `value: dict` passthrough |

Unions at 832-853; `KNOWN_BLOCK_TYPES` at 856-877 with the explicit rule "If a block has a type not
in this set, it is considered to be provider-specific."

Two structural observations:
- Every data block has **exactly the same three-way source union** (`file_id | url | base64`) plus
  `mime_type`. The four classes differ only in their `type` literal. This is redundancy that PACT
  should collapse. LangChain's own comment at 785-787 ("Future modalities to consider: 3D models,
  Tabular data") is evidence the per-modality enumeration does not close.
- `index: int | str` on every data block "used during streaming" — LangChain streams media blocks
  by *index correlation*, not by delta chunks.

#### 1.1.3 AutoGen — **the binding constraint**

`FW2/../autogen/python/packages/autogen-core/src/autogen_core/models/_types.py`:

```
UserMessage.content: Union[str, List[Union[str, Image]]]        # line 32
AssistantMessage.content: Union[str, List[FunctionCall]]        # line 43
FunctionExecutionResult.content: str                            # line 58
```

**[NEGATIVE]** AutoGen's model layer supports **images only**. No audio, no video, no documents, no
file references, and **tool results are plain `str`** — a tool cannot return an image to the model
through the typed API. `autogen-agentchat` `MultiModalMessage.content: List[str | Image]`
(`.../autogen-agentchat/src/autogen_agentchat/messages.py:373-379`), and its
`to_model_text(image_placeholder="[image]")` (381-395) is a documented lossy downgrade path.

AutoGen *does* have an explicit capability declaration: `ModelInfo`
(`autogen-core/src/autogen_core/models/_model_client.py:164-181`) requires
`vision`, `function_calling`, `json_output`, `family`, `structured_output`, optional
`multiple_system_messages`. It is **author-declared**, not catalogue-derived — for any
OpenAI-compatible endpoint the user supplies it by hand.

#### 1.1.4 OpenAI Agents SDK

`FW/openai-agents-python/src/agents/items.py` imports `ResponseInputImageContentParam` (line 35)
and `ResponseInputFileContentParam` (line 34) — mapped at 957 and 968.
**[NEGATIVE] `grep -c audio items.py` → `0`; `grep -c audio agent.py` → `0`.** Audio is entirely
outside the core agent item model. It exists in two *separate subsystems*:

- **`voice/`** — a cascaded pipeline. `AudioInput` is a numpy `int16|float32` buffer with
  `frame_rate` (default `DEFAULT_SAMPLE_RATE = 24000`), `sample_width`, `channels`
  (`voice/input.py:13, 42-57`); `StreamedAudioInput` at `voice/input.py:76`.
  `TTSModelSettings` (`voice/model.py:22-61`) carries `voice` (9-value literal at 17),
  `buffer_size=120`, `dtype`, `transform_data`, `instructions`, `text_splitter`, `speed`.
  `STTModelSettings` (`voice/model.py:104-118`) carries `prompt`, `language`, `temperature`,
  `turn_detection: dict[str, Any]` — untyped.
  Stream events: `VoiceStreamEventAudio`, `VoiceStreamEventLifecycle`
  (`turn_started|turn_ended|session_ended`), `VoiceStreamEventError` (`voice/events.py:9-43`).
- **`realtime/`** — duplex. `RealtimeTurnDetectionConfig` (`realtime/config.py:96-124`):
  `type: semantic_vad|server_vad`, `create_response`, `eagerness`, `interrupt_response`,
  `prefix_padding_ms`, `silence_duration_ms`, `threshold`, `idle_timeout_ms`, `model_version`.
  `RealtimeAudioInputConfig` / `RealtimeAudioOutputConfig` (127-142) carry format, noise reduction
  (`near_field|far_field`, 89-94), transcription config, voice, speed. Formats normalised to
  `audio/pcm@24000 | audio/pcmu | audio/pcma` (`realtime/audio_formats.py:16-52`).

**Computer use is first-class here.** `computer.py:4-5` defines
`Environment = Literal["mac","windows","ubuntu","browser"]` and
`Button = Literal["left","right","wheel","back","forward"]`; `Computer` (line 8) and
`AsyncComputer` (line 72) are ABCs with exactly nine operations:
`screenshot, click, double_click, scroll, type, wait, move, keypress, drag`, plus
`environment` and `dimensions` properties. `ComputerTool` (`tool.py:761-789`) takes a computer
instance/factory plus `on_safety_check` — and its runtime name is pinned to
`"computer_use_preview"` for RunState compatibility (`tool.py:783-785`).

#### 1.1.5 Anthropic SDK + Claude Agent SDK

`FW/anthropic-sdk-python/src/anthropic/types/content_block_param.py` — **input** union:
Text, **Image**, **Document**, SearchResult, Thinking, RedactedThinking, ToolUse, ToolResult,
ServerToolUse, WebSearchToolResult, WebFetchToolResult, CodeExecutionToolResult,
BashCodeExecutionToolResult, TextEditorCodeExecutionToolResult, ToolSearchToolResult,
ContainerUpload, MidConversationSystem.

`content_block.py` — **output** union: Text, Thinking, RedactedThinking, ToolUse, ServerToolUse,
and five tool-result blocks + ContainerUpload. **[NEGATIVE] No image, audio, or video in model
output.** **[NEGATIVE] No audio or video anywhere in the Anthropic content model, input or output.**

Sources are narrow: `ImageBlockParam.source = Base64ImageSourceParam | URLImageSourceParam`
(`image_block_param.py:14`); `DocumentBlockParam.source = Base64PDF | PlainText | ContentBlock |
URLPDF` (`document_block_param.py:17`), plus `citations`, `context`, `title` (28-32).

**Computer tools are date-versioned betas** with drifting schemas:
`types/beta/beta_tool_computer_use_20241022_param.py`, `..._20250124_param.py`,
`..._20251124_param.py`. `BetaToolComputerUse20250124Param` requires `display_width_px`,
`display_height_px`, `name: "computer"`, `type: "computer_20250124"`, and optionally
`display_number` (X11), `allowed_callers`, `defer_loading`, `strict`, `input_examples`.
**[NEGATIVE] The action vocabulary is untyped in the SDK** — `grep -rn "left_click|triple_click|
hold_key|mouse_move" src/` returns nothing. The actions live only in prose in the tool description
served by the API.

**Claude Agent SDK** (`FW/claude-agent-sdk-python/src/claude_agent_sdk/types.py`):
`ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock | ServerToolUseBlock |
ServerToolResultBlock` (994-1002). **[NEGATIVE] No image block.** Media reaches the model only
through `ToolResultBlock.content: str | list[dict[str, Any]]` (line 950) — untyped dicts.
The SDK's own MCP result converter handles `text`, `image`, `resource_link`, and text-only
`resource`, and then:

```python
logger.warning("Binary embedded resource cannot be converted to text, skipping")   # __init__.py:512
logger.warning("Unsupported content type %r in tool result, skipping", item_type)  # __init__.py:516
```

even though `AudioContent` is in the declared output type at `__init__.py:470`. **This is exactly
the silent-loss failure mode T7/AC-7.1 forbids, in a first-party SDK.**

#### 1.1.6 Vercel AI SDK — the cleanest model

`FW/vercel-ai/packages/provider/src/language-model/v4/language-model-v4-prompt.ts`:

- One `LanguageModelV4FilePart` (line 151) with `mediaType` accepting either a full IANA type
  **or just the top-level segment** (`image`, `audio`, `video`, `text`), and `*`-wildcards
  normalised to the top-level segment. Helpers `isFullMediaType`, `getTopLevelMediaType`,
  `detectMediaType` are named in the doc comment.
- `SharedV4FileData` = `{type:'data'} | {type:'url'} | {type:'reference'} | {type:'text'}`
  (`packages/provider/src/shared/v4/shared-v4-file-data.ts`). The `reference` variant is
  `{[provider]: id}` — provider file IDs are first-class, and non-portable by construction.
- Assistant messages may carry file parts (the union at role `assistant` includes
  `LanguageModelV4FilePart`), unlike Anthropic.
- **Tool results are richly multimodal**: `LanguageModelV4ToolResultOutput` (line 288) =
  `text | json | execution-denied | error-text | error-json | content[]` where `content[]` items are
  `text | file | custom`. `execution-denied{reason}` is a *first-class output value* — denial is
  data, not an exception.
- `LanguageModelV4ToolApprovalResponsePart{approvalId, approved, reason}` (line 259) is a
  **message part** in role `tool` (referenced in the role-`tool` content union at line 49).
  Approvals live in the transcript.

Streaming (`language-model-v4-stream-part.ts`): `text-start/-delta/-end`,
`reasoning-start/-delta/-end`, `tool-input-start/-delta/-end`, then whole-object
`LanguageModelV4File`, `LanguageModelV4Source`, `LanguageModelV4ToolCall`,
`LanguageModelV4ToolResult`, `LanguageModelV4ToolApprovalRequest`, plus
`stream-start{warnings}`, `response-metadata`, `finish`, `raw`, `error`.
**Files stream as whole parts; only text/reasoning/tool-input have delta triples.**

**Modality is a model *role*, not a flag.** `packages/provider/src/` contains sibling interfaces:
`language-model`, `embedding-model`, `image-model`, `speech-model`, `transcription-model`,
`realtime-model`, `video-model`, `reranking-model`. `RealtimeModelV4`
(`realtime-model/v4/realtime-model-v4.ts`) is a provider-neutral duplex contract with
`doCreateClientSecret`, `getWebSocketConfig`, `parseServerEvent`, `serializeClientEvent`,
`buildSessionConfig`.

`RealtimeModelV4SessionConfig` (`realtime-model-v4-session-config.ts`) is the **only
provider-neutral voice session schema in the corpus**: `instructions`, `voice`,
`outputModalities: ('text'|'audio')[]`, `inputAudioFormat{type, rate}`, `outputAudioFormat`,
`inputAudioTranscription{model, language, prompt}`, `outputAudioTranscription{...}`,
`turnDetection{type: 'server-vad'|'semantic-vad'|'disabled', threshold, ...}`.

Normalised server events (`realtime-model-v4-server-event.ts`): `session-created`,
`session-updated`, `speech-started`, `speech-stopped`, `audio-committed`,
`conversation-item-added`, `input-transcription-completed`, `response-created`, `response-done`,
`output-item-added/-done`, `content-part-added/-done`, `audio-delta`, `audio-done`,
`audio-transcript-delta`, `audio-transcript-done`, `text-delta`, `text-done`,
`function-call-arguments-delta/-done`, `error`, `custom`.

UI layer: `FileUIPart{mediaType, filename?, url, providerReference?}`
(`packages/ai/src/ui/ui-messages.ts:180-218`) — one part type for all media in the UI too.

### 1.2 Divergence matrix

Legend: **N** native/typed · **P** partial (untyped or via escape hatch) · **—** absent · **X** explicit error

| Capability | Pydantic AI | LangChain/Graph | AutoGen | OpenAI Agents | Claude Agent SDK | Vercel AI v4 | MCP 2025-11-25 | A2A |
|---|---|---|---|---|---|---|---|---|
| Image **in** | N (`ImageUrl`, `BinaryImage`) | N (`ImageContentBlock`) | N (`Image`) | N (`input_image`) | P (tool-result dicts) | N (`file` + `image/*`) | N (`ImageContent`) | N (`media_type`) |
| Image **out** (model emits) | N (`FilePart`) | N (block w/ base64) | — | N (`ImageGenerationCall`) | — | N (`file` stream part) | N | N |
| Audio **in** | N (`AudioUrl`/`BinaryContent`), **X on OpenAI Responses** | N (`AudioContentBlock`) | — | — (only `voice/`,`realtime/`) | — (dropped w/ warning) | N (`file` + `audio/*`) | N (`AudioContent`) | N |
| Audio **out** | P (provider-specific) | N (block) | — | — (only `voice/`,`realtime/`) | — | N | N | N |
| Video **in** | N (`VideoUrl`, 8 formats) | N (`VideoContentBlock`) | — | — | — | N | **—** | N |
| Document/PDF **in** | N (`DocumentUrl`, 9 types) | N (`FileContentBlock`,`PlainTextContentBlock`) | — | N (`input_file`) | P | N | P (`EmbeddedResource`) | N |
| Provider file-ID reference | N (`UploadedFile`, 8 providers) | N (`file_id`) | — | N | — | N (`reference`) | — | — |
| **Multimodal tool result** | N (`ToolReturn.content`) | N (`ToolMessage` blocks) | **— (`str` only)** | P | P (untyped dicts) | N (`content[]`) | N | n/a |
| Streaming media deltas | — (atomic) | P (`index` correlation) | — | audio only in `voice`/`realtime` | — | — (atomic; realtime iface separate) | — | n/a |
| Cache-boundary marker in content | N (`CachePoint`) | — | — | — | — | via providerOptions | — | — |
| Computer use | **—** | — (generic `server_tool_call`) | — (ext: web surfer) | **N** (`Computer` ABC + `ComputerTool`) | P (via CLI tools) | **N** (Anthropic tool factories) | — | — |
| Tool approval in transcript | N (`DeferredToolRequests`) | N (`interrupt()`) | — | N (`ToolApprovalItem`) | N (`can_use_tool`) | **N** (`tool-approval-response` part) | — | `TASK_STATE_INPUT_REQUIRED` |

**The three hard walls for harness lowering (D12):**
1. **AutoGen tool results are `str`.** Any PACT tool returning an image must, on AutoGen, either
   (a) emit the image as a following `UserMessage` part, or (b) degrade to a text placeholder. This
   is a `degraded` lattice entry with a mandatory report.
2. **Anthropic assistant output cannot contain media.** A PACT contract declaring
   `output: {image: ...}` is `unsupported` on any Anthropic-family binding unless the image is
   produced by a tool, not by the model.
3. **MCP has no video content type** — `ContentBlock = TextContent | ImageContent | AudioContent |
   ResourceLink | EmbeddedResource` in both `PR/mcp-spec/schema/2025-11-25/schema.ts:1740-1741` and
   `PR/mcp-spec/schema/draft/schema.ts:2292-2293`. Since D14 makes MCP the no-code custom-tool path,
   **a no-code tool cannot return video in v1.** Workaround: `ResourceLink` to a video URI.

### 1.3 Proposed PACT content model

**Canonical part** (one shape; per-modality forms are sugar the loader desugars):

```yaml
# canonical form
- kind: media                    # text | media | tool_call | tool_result | thinking | approval | control
  mediaType: image/png           # full IANA type, or top-level segment (image|audio|video|text)
  source:                        # exactly one key
    file: ./screenshots/cart.png #   relative to the spec tree  (PACT-native, D2)
    # bytes: <base64>            #   inline (discouraged >64 KiB, see §1.4)
    # url: https://...           #   with fetch policy
    # ref: sha256:...            #   content-addressed artifact store
    # providerRef: {openai: file-abc}   #   non-portable; resolver marks it
    # text: "..."                #   inline text document
  filename: cart.png             # optional
  id: cart-before                # author-stable ID for cross-reference (see §1.3.3)
  role: screenshot               # optional semantic tag (see §1.3.2)
  fetch: {download: false, allowPrivateNetwork: false}   # SSRF policy, from pydantic-ai
  x-vendor: {openai: {detail: high}, google: {media_resolution: high}}
```

Sugar forms the loader accepts and normalises (D13/D18 — a non-coder must be able to write these):
```yaml
- image: ./cart.png              # → kind: media, mediaType inferred from extension
- audio: ./greeting.wav
- document: ./policy.pdf
- text: "hello"
```

Rationale, each traceable:
- **Media-typed single part, not per-modality classes** — matches Vercel v4, A2A
  (`PR/a2a-spec/specification/a2a.proto:224-241`) and the LangChain shape-collapse observation
  (§1.1.2). Adding a modality then requires **zero schema change**, satisfying E-2/E-3.
- **Source as a tagged union with `file:`** — this is the D2 requirement. The native form is a
  folder tree; media must be able to live as a file *in* the tree and be referenced by relative
  path. No other framework has this variant because none of them are filesystem-native.
- **`fetch` policy on the part** — from `pydantic-ai messages.py:145-152, 220-227`. A URL part is an
  SSRF surface; the policy must travel with the content, and in air-gapped mode (D17) the default
  must be `deny`.
- **`x-vendor`** — the `x-` extension mechanism (O1.4) carries the per-provider knobs that
  Pydantic AI documents at `messages.py:229-238` and Vercel calls `providerOptions`.

#### 1.3.1 Tool results

Adopt Vercel's output union verbatim in shape, extended with MCP's `structuredContent`:

```yaml
toolResult:
  callId: t_1
  output:
    kind: content                 # text | json | content | error-text | error-json | execution-denied
    value:
      - text: "Found 3 matches"
      - image: ./out/chart.png
  structured: {...}               # MCP structuredContent, validated against tool outputSchema
```

`execution-denied{reason}` must be a first-class output kind, not an exception —
`FW/vercel-ai/packages/provider/src/language-model/v4/language-model-v4-prompt.ts` (ToolResultOutput
union). This is what makes a *denied approval* replayable and eval-able.

#### 1.3.2 Semantic `role` tag on media — new, not copied

None of the seven frameworks distinguish "this image is a screenshot of the environment" from
"this image is user-supplied evidence". For computer use, the harness must know: screenshots are
**prunable** (SWE-agent elides them: `FW2/swe-agent/sweagent/agent/history_processors.py:171-174`
appends `" (N images omitted)"`), user evidence is **not**. Proposed closed-ish vocabulary:
`screenshot | user_attachment | tool_output | generated | reference`. **[INFERRED]**

#### 1.3.3 Stable content IDs

Adopt Pydantic AI's identifier idea (`messages.py:204-208, 625-640`) but make it **author-visible
and author-stable**: `id:` is an author-chosen slug in the spec tree; the runtime falls back to
`sha256(content)[:12]`. Reason: eval cases must be able to say "the answer must reference
`cart-before`", and a content-derived hash is not writable by a non-coder before the run.

### 1.4 The Expansion Rule vs binary payloads — a genuine stress point

The thesis asks (§9.3) where field↔directory equivalence breaks. Binary media is one of those places.

- **`explode`** (document → tree) of an inline base64 blob must write a **file**, not a YAML scalar,
  or diffs become unreviewable (D18 requires "human-meaningful diffs").
- **`collapse`** (tree → document) of a media file must **not** inline the bytes into
  `canonical.json`, or the derived index becomes gigabytes. Evidence that this is a real failure
  mode, not a hypothetical: OpenHands ships a config flag whose comment reads "The screenshots are
  encoded and can make trajectory json files very large"
  (`FW2/openhands/config.template.toml:31-33`), and SWE-agent raises
  `max_observation_length: 10_000_000  # need longer for images`
  (`FW2/swe-agent/config/default_mm_with_images.yaml:41`).

**Resolution:** `canonical.json` stores a **content-addressed reference**
(`{ref: "sha256:...", mediaType, bytes: 48213}`) and the bytes live in a
content-addressed artifact store under `.pact/blobs/<sha256>`. Round-trip identity
(`explode(collapse(X)) ≡ X`, O1.3/AC-1.2) is then over the *reference*, and byte identity is
guaranteed by the hash. Precedent: promptfoo's `BlobStorageProvider` with `store()/getByHash()/
exists()/deleteByHash()/getUrl()` and a `deduplicated` flag on store
(`EV/promptfoo/src/blobs/types.ts:18-32`).

**Threshold rule [INFERRED]:** inline base64 permitted only below a profile-configured limit
(propose 64 KiB default, per F-1 it must be a profile value, not a literal); above it, `explode`
writes a file and `collapse` writes a `ref`.

### 1.5 Streaming model

Three distinct streaming regimes exist in the corpus and PACT must name all three, because
collapsing them loses the D16 voice-TTFT requirement:

| Regime | Shape | Evidence |
|---|---|---|
| **Token stream** | `*-start` / `*-delta` / `*-end` triples for text, reasoning, tool input | `vercel-ai .../language-model-v4-stream-part.ts:14-68`; pydantic-ai `messages.py:2982,3032,3143` |
| **Atomic artifact** | whole `file` / `source` / `tool-result` parts, no deltas | `vercel-ai .../language-model-v4-stream-part.ts` (file/source/tool parts have no delta variants); pydantic-ai has no `FilePartDelta` |
| **Duplex media session** | continuous `audio-delta` + `audio-transcript-delta` + VAD lifecycle events, bidirectional | `vercel-ai realtime-model-v4-server-event.ts:94-131`; `openai-agents realtime/config.py:96-150` |

PACT's IR needs `streaming: {mode: token|duplex}` on the interface contract, and duplex implies a
`realtime` model role binding. **[INFERRED]**

`stream-start{warnings: SharedV4Warning[]}` with
`SharedV4Warning = unsupported{feature,details} | compatibility{feature,details} |
deprecated{setting,message} | other`
(`FW/vercel-ai/packages/provider/src/shared/v4/shared-v4-warning.ts`) is the industry's existing
runtime loss-report, and it maps 1:1 onto PACT's lattice values `unsupported` / `degraded`
(= `compatibility`). Adopt the wire shape so adapter warnings can be forwarded unmodified.

---

## 2. Deliverable 2 — Capability requirements and how they are verified

### 2.1 What each framework knows about a model's modality

| Source | Has modality capability data? | Fields |
|---|---|---|
| Pydantic AI `ModelProfile` | **No input modalities** | only `supports_image_output` (`profiles/__init__.py:72-73`) |
| LangChain `langchain-model-profiles` | **Yes**, vendored from models.dev | see below |
| AutoGen `ModelInfo` | Partial, author-declared | `vision`, `function_calling`, `json_output`, `structured_output` (`_model_client.py:159-181`) |
| OpenAI Agents SDK | No catalogue | model-name regex for computer use lives in inspect_ai, not the SDK |
| Claude Agent SDK | No | |
| Vercel AI SDK | No catalogue; **runtime rejection instead** | `UnsupportedFunctionalityError({functionality: 'media type: X'})` at `packages/anthropic/src/convert-to-anthropic-prompt.ts:401-402` |
| LiteLLM | **Yes**, largest | see below |

**LangChain / models.dev** (`FW/langchain/libs/partners/openai/langchain_openai/data/_profiles.py`
header: "It contains data derived from the models.dev project. Source:
https://github.com/sst/models.dev, License: MIT"). Full key set observed in the Anthropic file:
`name, release_date, last_updated, status, open_weights, max_input_tokens, max_output_tokens,
text_inputs, image_inputs, audio_inputs, video_inputs, text_outputs, image_outputs, audio_outputs,
video_outputs, reasoning_output, reasoning_effort_levels, reasoning_effort_default, tool_calling,
tool_call_streaming, structured_output, attachment, temperature, image_url_inputs, pdf_inputs,
pdf_tool_message, image_tool_message`.
**[NEGATIVE] No `computer_use` key** — `grep -c computer` on both the OpenAI and Anthropic profile
files returns `0`.

Crucially, LangChain ships a **human override layer**:
`FW/langchain/libs/partners/anthropic/langchain_anthropic/data/profile_augmentations.toml` sets
provider-wide overrides (`image_url_inputs = true`, `pdf_inputs = true`,
`structured_output = false`) then re-enables `structured_output = true` per model. Upstream feed +
local corrections is exactly D8's hybrid, and it is in production today.

**LiteLLM** `RO/litellm/model_prices_and_context_window.json` — 2,984 entries. Modality-relevant
keys present across the file:
`supported_modalities`, `supported_output_modalities`, `supports_vision`, `supports_image_input`,
`supports_audio_input`, `supports_audio_output`, `supports_video_input`, `supports_pdf_input`,
`supports_computer_use`, `supports_web_search`, `supports_url_context`, `supports_multimodal`,
`supports_embedding_image_input`, `supports_native_streaming`, plus per-modality cost fields
(`input_cost_per_audio_token`, `output_cost_per_audio_token`,
`input_cost_per_audio_per_second`, `cache_creation_input_audio_token_cost`, …).

Measured coverage (my count over the file):

| Flag | entries `true` |
|---|---|
| `supports_function_calling` | 1667 |
| `supports_vision` | 888 |
| `supports_reasoning` | 770 |
| `supports_pdf_input` | 464 |
| `supports_web_search` | 260 |
| **`supports_computer_use`** | **166** |
| `supports_audio_input` | 105 |
| `supports_audio_output` | 62 |
| `supports_video_input` | 54 |

`supported_modalities` values seen: `text`(358), `image`(299), `audio`(108), `video`(73).
`supported_output_modalities`: `text`(309), `audio`(44), `image`(38), `video`(27), `code`(8).
`mode` values: `chat`(2285), `image_generation`(209), `embedding`(124), `responses`(85),
`audio_transcription`(62), `completion`(36), `image_edit`(31), `realtime`(28), `audio_speech`(27),
`rerank`(25), `video_generation`(25), `search`(18), `ocr`(13), `moderation`(5), `vector_store`(1),
`None`(9), plus **one entry whose `mode` is literally the string
`"one of: chat, embedding, completion, image_generation, audio_transcription, audio_speech,
image_generation, moderation, rerank, search"`** — i.e. the schema documentation leaked into the
data as a record.

### 2.2 The catalogue is demonstrably wrong — evidence for AC-3.3 `strict` mode

Every `supports_computer_use: true` entry in LiteLLM is Anthropic-family plus
`gemini-2.5-computer-use-preview-10-2025`. And:

```
computer-use-preview        → {mode: chat, supported_modalities: [text,image],
                               supports_vision: true, ... }        # no supports_computer_use
azure/computer-use-preview  → same, no supports_computer_use
gpt-5.5 / gpt-5.4           → supports_vision, supports_pdf_input, supports_web_search;
                               no supports_computer_use
```

**OpenAI's dedicated computer-use model is not marked as supporting computer use in the largest
model catalogue in the ecosystem.** Meanwhile `inspect_ai` gates OpenAI computer use on a
*model-version regex* — `(major, minor) >= (5, 4)` plus an exclusion list, plus an `is_latest`
escape (`EV/inspect_ai/src/inspect_ai/model/_providers/_openai_computer_use.py:89-101`) — i.e. the
best-informed implementation in the corpus does not trust a catalogue either; it hardcodes version
logic.

Design consequences:
- A capability predicate on `computer_use` **must not** be satisfiable by an unprovenanced
  catalogue row in `strict` mode (AC-3.3), and the `PORTABILITY: FAIL / RECOMMENDED` flow (D11)
  must be able to say "capability unknown for this model" as distinct from "capability absent".
- The catalogue schema needs `provenance` **per field**, not per model — `supports_vision` may come
  from models.dev while `supports_computer_use` came from a hand override. LangChain's
  `profile_augmentations.toml` gets this structurally right (overrides are a separate file) but
  records no source or date.

### 2.3 Proposed capability vocabulary and predicate semantics

Split the D16 vocabulary into three *kinds* of requirement, because they are verified differently:

**(a) Model-intrinsic capabilities** — verified against the catalogue at resolve time.
```
modality.input:  text | image | audio | video | document
modality.output: text | image | audio | video
context.window >= 128k
tool_calling: none | serial | parallel
structured_output: none | json_object | json_schema
reasoning: none | optional | always
```
Map directly onto LiteLLM `supported_modalities` / `supported_output_modalities` and models.dev
`{text,image,audio,video}_{inputs,outputs}`.

**(b) Provider-tool capabilities** — verified against the (provider, api-surface) pair, not the
model alone.
```
tool.web_search · tool.web_fetch (web_scrape) · tool.code_interpreter ·
tool.computer_use{environment: browser|mac|windows|ubuntu, actions: [...]}  ·
tool.image_generation · tool.file_search · tool.memory
```
Evidence they are provider-tool-shaped, not model-shaped: Pydantic AI's
`ModelProfile.supported_native_tools: frozenset[type[AbstractNativeTool]]`
(`profiles/__init__.py:120-121`) — a per-profile *set of tool types*; Claude Agent SDK's
`ServerToolName` literal (`types.py:954-963`: advisor, web_search, web_fetch, code_execution,
bash_code_execution, text_editor_code_execution, tool_search_tool_regex, tool_search_tool_bm25);
Anthropic's `allowed_callers` on the computer tool
(`beta_tool_computer_use_20250124_param.py:29-31`).

**(c) Substrate capabilities** — verified against the *runtime*, not the model.
```
sandbox.kind: none | process | container | microvm | remote
sandbox.gui: true            # a display exists at all
sandbox.network: none | allowlist | full
approval.channel: available  # a human can be reached
audio.duplex: true           # a realtime transport exists
```
A `computer_use` contract that binds a capable model to a runtime with no display is a resolve-time
failure that no model catalogue can catch. **[INFERRED]** — no framework in the corpus models this;
the closest is `Computer.dimensions`/`environment` being optional properties on the ABC
(`FW/openai-agents-python/src/agents/computer.py:17-25`).

**Verification levels** (all four required by D17's air-gap rule):
1. **Declared** — catalogue row with provenance. Cheap, offline, pre-filter only (R5).
2. **Probed** — a one-shot capability probe run against the live endpoint, cached in the lockfile.
   Not available air-gapped against remote models, but *is* available against a local model.
3. **Evidenced** — a modality-specific eval in the suite passed (the real oracle, T2).
4. **Asserted** — author wrote `x-capability-override:` with a justification string; recorded in
   the lockfile and surfaced in the Portability Report.

**Prior art for negotiated modality capability:** ACP's `PromptCapabilities`
(`PR/agent-client-protocol/schema/v1/schema.json`, `$defs.PromptCapabilities`) —
`{image: false, audio: false, embeddedContext: false}` by default, with the rule "Baseline agent
functionality requires support for `ContentBlock::Text` and `ContentBlock::ResourceLink` … Other
variants must be explicitly opted in to." PACT should mirror this default-deny stance: **sending a
content kind the binding did not declare is an error, never a silent drop.**

### 2.4 Air-gapped implications (D17)

- **Catalogue**: both candidate feeds are already offline-capable artefacts — LiteLLM's single JSON
  file, and LangChain's *vendored* `_profiles.py` generated by a CLI. Both are MIT/permissive.
  Recommend seeding `models/catalog.yaml` from both, keeping per-field provenance, and shipping the
  merge as a build-time step so `pact validate` needs no network.
- **Vision judge**: DeepEval multimodal metrics instantiate a judge model and pass a multimodal
  array (`EV/deepeval/deepeval/metrics/multimodal_metrics/image_coherence/image_coherence.py:1-45`).
  Air-gapped image evals therefore require a **local vision-capable judge** in the profile. This is
  a hard dependency PACT must declare, not discover at eval time.
- **Voice**: the Bud manifest already has a local path —
  `input.dictation.provider: local` with Whisper model download/selection
  (`gaia-ai-runtime/bud-agentic-runtime/sdk-and-declarative-dev.md:2515-2553`:
  "local transcription uses Goose local Whisper models, cache, audio decode, deduplication, and
  download manager"). **[NEGATIVE] There is no local TTS and no local duplex/realtime model anywhere
  in the corpus.** `FW/openai-agents-python/src/agents/voice/models/` contains only
  `openai_stt.py`, `openai_tts.py`, `openai_model_provider.py`. Air-gapped voice in v1 is therefore
  **STT-in only**, or STT+text+TTS where TTS is out of scope.

---

## 3. Deliverable 3 — Sandboxing and approval gates

### 3.1 Sandbox declaration — prior art

| System | Declaration | Fields observed |
|---|---|---|
| OpenAI Agents SDK | Pydantic `Manifest` (`FW/openai-agents-python/src/agents/sandbox/manifest.py:88-97`) | `version`, `root` (default `/workspace`), `entries: {path: Dir\|File\|Mount}`, `environment` (with `EnvValue` indirection for secrets, 45-84), `users`, `groups`, `extra_path_grants`, `remote_mount_command_allowlist` (default list of 19 commands at 22-40). Backends: `sandboxes/docker.py`, `sandboxes/unix_local.py`. **[NEGATIVE] no network policy field** — `grep -rn network sandbox/ --include=*.py` yields one comment in an S3 mount provider. |
| Claude Agent SDK | `SandboxSettings` TypedDict (`FW/claude-agent-sdk-python/src/claude_agent_sdk/types.py:874-916`) | `enabled`, `autoAllowBashIfSandboxed` (default **True**), `excludedCommands`, `allowUnsandboxedCommands`, `network`, `ignoreViolations`, `enableWeakerNestedSandbox`. `SandboxNetworkConfig` (836-860): `allowedDomains`, `deniedDomains`, `allowManagedDomainsOnly`, `allowUnixSockets`, `allowAllUnixSockets`, `allowLocalBinding`, `allowMachLookup`, `httpProxyPort`, `socksProxyPort`. Docstring at 878-885 is explicit that **filesystem/network restrictions are expressed as permission rules, not sandbox settings** — one policy language, two enforcement points. |
| inspect_ai | `SandboxEnvironmentSpec{type, config}` where config is a filename or provider model (`EV/inspect_ai/src/inspect_ai/util/_sandbox/environment.py:503-536`); shorthands `"docker"` and `("docker","compose.yaml")` | The ABC (`environment.py:92-190+`) is `exec/write_file/read_file/…` with an output cap (`INSPECT_SANDBOX_MAX_EXEC_OUTPUT_SIZE`, default 10 MiB) and typed errors (`OutputLimitExceededError`, `TimeoutError`, `PermissionError`). |
| E2B | `e2b.toml` yup schema (`RT/e2b/packages/cli/src/config/index.ts:8-17`) | `template_id`*, `template_name`, `dockerfile`*, `start_cmd`, `ready_cmd`, `cpu_count>=1`, `memory_mb>=128` |
| microsandbox | CLI `SandboxOpts` (`RT/microsandbox/crates/cli/lib/commands/common.rs:51-91`) | `name`, `cpus`, `max_cpus`, `memory`, `max_memory`, `volume`, `mount_dir`, `mount_file`, `mount_disk`, `mount_named`; microVM isolation; per-pattern upstream CA certs (`common.rs:1977-1983`) |
| OpenHands | TOML (`FW2/openhands/config.template.toml:149-221`) | `timeout`, `user_id`, `base_container_image`, `use_host_network`, `runtime_extra_build_args`, `runtime_extra_deps`, `runtime_startup_env_vars`, `volumes` (`"/host:/workspace:rw,/p2:/workspace/p2:ro"`), `platform`, `enable_gpu`, `cuda_visible_devices`, `keep_runtime_alive`, `close_delay` |
| SWE-agent | YAML tool **bundles are directories** (`FW2/swe-agent/config/default_mm_with_images.yaml:44-50`) | `tools.bundles: [{path: tools/registry}, {path: tools/image_tools}, {path: tools/web_browser}, …]`, `execution_timeout`, `registry_variables` |

**Convergent minimum field set [INFERRED]:** `image/template`, `cpu`, `memory`, `mounts[]` with
`ro|rw`, `env` (with a secret indirection), `network{mode, allowDomains, denyDomains}`,
`timeout`, `user`, `gui{width,height,display}`, `persist{snapshot,keepAlive}`.

**GUI is missing from every sandbox declaration in the corpus.** Nobody declares display geometry
in the sandbox spec — Anthropic requires `display_width_px`/`display_height_px` on the *tool*
(`beta_tool_computer_use_20250124_param.py:12-19`), inspect_ai hardcodes
`DISPLAY_WIDTH=1366, DISPLAY_HEIGHT=768` in the Gemini provider with a comment that these "should
stay in sync with the dimensions used by the container"
(`EV/inspect_ai/src/inspect_ai/model/_providers/_google_computer_use.py:18-21`), and SWE-agent has a
`set_browser_window_size` shell command. **This duplication is a real bug class** and PACT should
own it: declare geometry once in `sandbox.gui`, and derive the tool parameters from it.

The OS-agents survey supplies the reason this matters for accuracy, not just plumbing:
vision encoders commonly ingest ~224×224 while GUI screenshots are 720×1080 or 1920×1080, and
"Resizing screenshots to fit the resolution vision encoders of MLLMs preserves features [but loses
detail] sometimes vital for MLLMs to accomplish OS tasks"
(`gaia-ai-runtime/research/papers/2508.04482-os-agents-survey.pdf`, §3 — extracted text lines
704-716). Screenshot scaling is therefore a **strategy variable** that belongs in the plural
strategy space (T1), and OpenAI's own harness sets `detail: "original"` for exactly this reason:
"preserves full screenshot resolution (up to 10.24M px) and improves click accuracy"
(`EV/inspect_ai/src/inspect_ai/model/_providers/_openai_computer_use.py:117-124`).

### 3.2 Approval gates — four independent implementations, one converged vocabulary

| System | Vocabulary | Evidence |
|---|---|---|
| Claude Agent SDK | `PermissionMode = default \| acceptEdits \| plan \| bypassPermissions \| dontAsk \| auto`; `PermissionBehavior = allow \| deny \| ask`; rules are `{tool_name, rule_content}`; updates are `addRules/replaceRules/removeRules/setMode/addDirectories/removeDirectories` with destination `userSettings\|projectSettings\|localSettings\|session` | `types.py:25-27, 106-140` |
| | `PermissionResultAllow{updated_input, updated_permissions}` / `PermissionResultDeny{message, interrupt}`; `CanUseTool = (name, input, ctx) -> PermissionResult` | `types.py:235-258` |
| | Rich UI context: `title` ("Claude wants to read foo.txt"), `display_name` ("Read file"), `description`, `blocked_path`, `decision_reason`, `suggestions[]` | `types.py:199-233` |
| OpenAI Agents SDK | `Tool.needs_approval: bool \| callable`; durable `RunState.get_interruptions() -> list[ToolApprovalItem]`; `approve(item, always_approve)`, `reject(item, always_reject, rejection_message)` | `tool.py:429-436`; `run_state.py:356-389` |
| ACP (Zed) | `PermissionOptionKind = allow_once \| allow_always \| reject_once \| reject_always`; `RequestPermissionOutcome = cancelled \| selected` | `PR/agent-client-protocol/schema/v1/schema.json` `$defs.PermissionOptionKind`, `$defs.RequestPermissionOutcome` |
| Vercel AI SDK | Approval is a **state machine on the tool part**: `input-streaming → input-available → approval-requested → approval-responded → output-available`, each `approval{id, approved?, reason?, isAutomatic?, signature?}` | `packages/ai/src/ui/ui-messages.ts:290-345` |
| A2A | Approval as a **task state**: `TASK_STATE_INPUT_REQUIRED`, `TASK_STATE_AUTH_REQUIRED` | `PR/a2a-spec/specification/a2a.proto:195-208` |
| LangGraph | `interrupt(value)` + `Command(resume=...)`; note the documented re-execution semantics: "The graph resumes from the start of the node, **re-executing** all logic" | `FW/langgraph/libs/langgraph/langgraph/types.py:535, 811-827` |
| OpenHands | `[security] confirmation_mode`, `security_analyzer = "llm" \| "invariant"`, `enable_security_analyzer` | `FW2/openhands/config.template.toml:226-236` |

**Four systems independently arrived at `{allow, deny} × {once, always}` plus a reason string.**
That is a settled vocabulary; PACT should use it verbatim rather than invent.

Two features only Vercel has, both of which PACT needs:
- **`isAutomatic`** — distinguishes a policy auto-approval from a human decision. Required for
  D23's blast-radius classifier to be auditable.
- **`signature`** — the approval decision is signed. Required because in PACT the approval travels
  in the transcript and the transcript is promotable to an eval case (AC-4.4); an unsigned approval
  in a replayable trace is a forgeable authorisation.

**Computer-use-specific gate: model-side safety checks.** Distinct from tool approval. The OpenAI
Responses computer tool returns `pending_safety_checks` that the harness must explicitly
acknowledge in `computer_call_output.acknowledged_safety_checks`
(`EV/inspect_ai/src/inspect_ai/model/_providers/_openai_computer_use.py:104-129`). The Agents SDK
surfaces this as `ComputerTool.on_safety_check: (ComputerToolSafetyCheckData) -> bool`
(`FW/openai-agents-python/src/agents/tool.py:767-768, 892-906`). **[NEGATIVE] No other framework in
the corpus models a provider-originated safety check.** PACT needs a third approval channel:
`policy.safetyChecks: {auto_acknowledge: false | [codes]}` — and defaulting it to auto-acknowledge
would be a silent policy relaxation under T7.

**Error-channel asymmetry worth recording:** OpenAI's `computer_call_output` has **no error or text
field** — the only payload is a screenshot, so a failed action (e.g. a bad key name) cannot be
reported to the model; inspect_ai substitutes a 1×1 transparent PNG
(`_openai_computer_use.py:109-113`). A PACT computer-use loop that relies on textual error feedback
will silently lose it on OpenAI. This is a `degraded` lattice entry.

### 3.3 No-code declaration proposal

```yaml
# agents/browser-checker/sandbox.yaml     ← expansion of `sandbox:` (D2 Expansion Rule)
kind: container                 # none | process | container | microvm | remote
image: pact/browser-ubuntu:1    # resolved from a profile; not a literal (F-1)
cpu: 2
memoryMb: 4096
timeoutSeconds: 300
gui:
  width: 1366                   # single source of truth; the computer tool inherits these
  height: 768
  display: 0
network:
  mode: allowlist               # none | allowlist | full
  allow: ["*.mycompany.com", "docs.stripe.com"]
  deny:  ["*.internal"]
mounts:
  - host: ./fixtures            # relative to the spec tree
    at: /workspace/fixtures
    mode: ro
env:
  API_BASE: https://staging.mycompany.com
  API_KEY: {secret: staging-api-key}      # never a literal
persist: {snapshot: false, keepAlive: false}
```

```yaml
# agents/browser-checker/policy.yaml      ← expansion of `policy:`
autonomy: supervised            # observe | supervised | autonomous
approvals:
  default: ask                  # allow | deny | ask
  rules:
    - tool: computer.*
      when: "action in [type, key] and target.matches('*password*')"
      decision: ask
      prompt: "The agent wants to type into a password field on {url}. Allow?"
    - tool: computer.navigate
      when: "url.host not in sandbox.network.allow"
      decision: deny
      reason: "Navigation outside the approved domain list."
    - tool: browser.*
      decision: allow           # everything else inside the sandbox is fine
  remember: [allow_always, reject_always]   # which options the UI offers
  timeoutSeconds: 300
  onTimeout: deny                            # fail-closed (T7)
safetyChecks:
  autoAcknowledge: false        # provider-originated checks always reach a human
```

Design notes:
- `decision: allow|deny|ask` + `remember: [allow_always, reject_always]` reproduces the converged
  vocabulary exactly, and the four ACP option kinds fall out as `decision × remember`.
- `prompt:` is the author-written sentence. Claude's SDK already proves the UI wants
  `title`/`display_name`/`description` (`types.py:219-233`); a non-coder can write the sentence, and
  PACT should *require* it for any `ask` rule so the human sees a domain-meaningful question rather
  than a JSON blob.
- The `when:` expression is the one place a predicate language is needed. It must be **CEL or
  equivalent, not code** (`PR/cel-spec` is in the corpus) so D14 holds. Same language as the
  capability predicates (O3.1) — one expression language, not two.
- **Fail-closed default `onTimeout: deny`** — every other system defaults the other way
  (Claude's `autoAllowBashIfSandboxed` defaults **True**, `types.py:889`; PACT should not).

---

## 4. Deliverable 4 — Eval implications

### 4.1 What DeepEval can actually do (the honest sizing for O4.1 / AC-4.1)

- **Images and PDFs only.** `MLLMImage` (`EV/deepeval/deepeval/test_case/llm_test_case.py:40-176`)
  takes `url` **or** (`dataBase64` + `mimeType`), resolves local paths and `file://` URIs
  (`process_url` at 116, `is_local_path` at 131), and auto-loads base64. PDFs get a distinct
  placeholder (`_placeholder`, 101-105: `[DEEPEVAL:PDF:<id>]` vs `[DEEPEVAL:IMAGE:<id>]`).
- **Media is smuggled through strings.** Multimodal content is not a typed field on `LLMTestCase`;
  it is a `[DEEPEVAL:IMAGE:<id>]` marker inside `input`/`actual_output`, re-expanded by
  `parse_multimodal_string` (144-172) against a process-global `_MLLM_IMAGE_REGISTRY` (line 31).
  This registry is in-process state, so a purely declarative YAML case cannot populate it without a
  provider shim.
- **Five image metrics total** (`EV/deepeval/deepeval/metrics/multimodal_metrics/__init__.py:1-5`):
  `TextToImageMetric`, `ImageEditingMetric`, `ImageCoherenceMetric`, `ImageHelpfulnessMetric`,
  `ImageReferenceMetric`. All are LLM-judged and require a vision-capable judge.
- **[NEGATIVE] Zero audio support.** `grep -rn "audio\|Audio" --include=*.py deepeval/` → **no
  hits**. There is no audio test-case field, no audio metric, no audio judge path.
- **[NEGATIVE] Conversational turns are text-only.**
  `Turn{role: 'user'|'assistant', content: str, ...}`
  (`EV/deepeval/deepeval/test_case/conversational_test_case.py:59-61`). A voice turn is not
  representable; only its transcript is.

**Therefore: "config-only expression of every DeepEval metric" (O4.1) is satisfiable for text and
image, and is vacuous for audio and computer use — because DeepEval has nothing there.** The
coverage matrix must say so rather than quietly scoping the claim to text.

### 4.2 What the rest of the ecosystem can do

**inspect_ai** has the most complete eval-side content model:
`Content = ContentText | ContentReasoning | ContentImage | ContentAudio | ContentVideo |
ContentData | ContentToolUse | ContentDocument` (`EV/inspect_ai/src/inspect_ai/_util/content.py`,
union at the tail of the file). `ContentAudio.format: 'wav'|'mp3'`, `ContentVideo.format:
'mp4'|'mpeg'|'mov'`, `ContentImage.detail: 'auto'|'low'|'high'|'original'`,
`ContentDocument` auto-derives `filename` and `mime_type` from a path or data URI
(`set_name_and_mime_type` validator). It also owns the only cross-provider computer tool (§4.3).

**promptfoo** has the best *no-code authoring* story: a YAML var written as
`file://path/to/x.png` is auto-detected by extension and loaded as base64, gated by
`PROMPTFOO_DISABLE_MULTIMEDIA_AS_BASE64` (`EV/promptfoo/src/evaluatorHelpers.ts:306-330`);
`collectFileMetadata` tags each var `{path, type: image|video|audio, format}` (121-150);
PDFs are text-extracted (`extractTextFromPDF` defined at 35, called at 305). Result payloads carry typed
`audio{data, blobRef, transcript, format, sampleRate, channels, duration}`,
`video{blobRef, format, size, duration, thumbnail, spritesheet, model, aspectRatio, resolution}`,
`images[]` (`EV/promptfoo/src/types/index.ts:433-458`), backed by a content-hash
`BlobStorageProvider` (`src/blobs/types.ts:18-32`).

**[NEGATIVE] No project in the corpus has an audio-native assertion.** promptfoo's assertion
directory (`EV/promptfoo/src/assertions/`) has 50+ assertions and none consume audio; the
`audio.transcript` field exists precisely so text assertions can be applied to a transcript.

### 4.3 The two eval cases D16 demands, written the way a non-coder would write them

**(A) A screenshot / vision task**

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
This is buildable today: promptfoo already resolves `file://x.png`; DeepEval's `MLLMImage` accepts a
local path; the only new machinery is desugaring `image:` into the provider's content part.

**(B) A computer-use task**

```yaml
# evals/cases/cancel-subscription.yaml
case: cancel-subscription
environment:
  sandbox: ./environments/billing-app.yaml      # replayable, offline
  reset: snapshot://billing-app@clean           # deterministic start state
input:
  - text: "Cancel the Pro subscription for acme-corp."
expect:
  - trajectory:                                 # step-level assertions
      max_steps: 25
      must_call: [computer.screenshot]
      must_not_call: [computer.type]            # no free-text typing on this task
      must_not_navigate_outside: ["billing.internal"]
  - final_state:                                # environment assertion, not text
      http: GET /api/subscriptions/acme-corp
      json_path: $.status
      equals: "cancelled"
  - approvals:
      required: [computer.click@confirm-cancel]  # the gate must actually have fired
  - slo: {e2e_p95_seconds: 90, cost_usd_max: 0.40}
```

The load-bearing move is `final_state:` — **a computer-use eval is graded on environment state, not
on model text.** This is what OSWorld/AndroidWorld do and it is what makes the eval deterministic
(AC-4.5). Nothing in DeepEval, promptfoo, or inspect_ai's *metric* layer expresses it; inspect_ai
expresses it in Python scorers. **PACT needs a declarative `final_state` assertion family
(`http`, `file`, `sql`, `shell_exit_code`, `sandbox_file_contains`) — this is new work.** [INFERRED]

**Offline determinism is bounded.** The OS-agents survey's taxonomy is the honest frame
(`2508.04482-os-agents-survey.pdf`, extracted §4.2.2, lines 1-27 of the extracted range):
- *Static* environments = cached site copies / recorded traces; "only one-step action are supported";
  Mind2Web "captures comprehensive snapshots … enabling seamless offline replay".
- *Interactive-simulated* = virtual sites/apps built to "avoid the reproducibility issues caused by
  the dynamic nature of real-world environments".
- *Interactive-real-world* = "one must consider the continuously updating nature of the environment,
  uncontrollable user behaviors, and diverse device setups".

**Only static and interactive-simulated are air-gappable (D17).** PACT must therefore type the
environment: `environment.kind: replay | simulated | live`, with `live` **excluded from the CI gate
by default** and flagged in the Portability Report.

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
      - barge_in: allowed                # can the caller interrupt?
      - audio: {max_silence_ms: 1200}
```
Blockers, each verified:
1. DeepEval has no audio at all (§4.1) — no metric, no test-case field.
2. `Turn.content: str` — the multi-turn model in DeepEval cannot hold audio.
3. No local TTS/duplex model exists in the corpus, so an air-gapped voice eval cannot be run
   end-to-end (§2.4).
4. Barge-in / turn-taking has no assertion vocabulary anywhere. The closest primitives are
   `RealtimeTurnDetectionConfig.interrupt_response` (`realtime/config.py:108-109`) and the
   `speech-started`/`speech-stopped` events (`realtime-model-v4-server-event.ts:23-31`) — signals
   exist, assertions do not.

**Realistic v1:** grade a voice turn on its **transcript plus timing**, with the audio kept as an
artifact for human review. That is honest and implementable: transcripts flow through every existing
text metric, `input-transcription-completed` / `audio-transcript-done` events give both sides
(`realtime-model-v4-server-event.ts:47-54, 113-131`), and promptfoo already stores
`audio.transcript` alongside `audio.data` for exactly this reason
(`EV/promptfoo/src/types/index.ts:433-442`).

### 4.4 Modality-aware SLOs (D16 explicitly requires this)

The corpus supplies the parameters that make voice SLOs measurable, and they are *different
quantities* from batch metrics:
- `prefix_padding_ms`, `silence_duration_ms`, `idle_timeout_ms`, `threshold`, `eagerness`
  (`FW/openai-agents-python/src/agents/realtime/config.py:96-124`) — these determine perceived
  latency more than model TTFT does.
- `TTSModelSettings.buffer_size = 120` "minimal size of the chunks of audio data that are being
  streamed out" and a sentence-based `text_splitter`
  (`FW/openai-agents-python/src/agents/voice/model.py:31-58`) — the cascaded pipeline's TTFT is
  dominated by the splitter, not the LLM.
- Audio is billed per audio-token and per second in the catalogue
  (`input_cost_per_audio_token`, `input_cost_per_audio_per_second`, `output_cost_per_audio_token` in
  `RO/litellm/model_prices_and_context_window.json`), so `cost_usd_max` predicates need
  modality-aware cost models, not token counts.
- Image cost is driven by resolution/detail (`detail: original` = "up to 10.24M px",
  `_openai_computer_use.py:117-119`), so a computer-use SLO must budget **screenshots per run**, not
  just tokens.

Proposed SLO vocabulary additions: `ttft_ms` (voice), `turn_latency_ms`, `barge_in_ms`,
`screenshots_per_run`, `audio_seconds_in/out`, `cost_usd` — all percentile-qualified per O4.2.

---

## 5. Deliverable 5 — What is genuinely NOT ready (scope down honestly)

Ranked by how badly a v1 promise would hurt.

| # | Claim that would be false | Verified basis | Recommended v1 scope |
|---|---|---|---|
| 1 | "Config-only evals for voice turns" | DeepEval has **zero** audio code; `Turn.content: str`; no audio assertion exists in promptfoo's 50+ assertions; no local TTS/duplex model in the corpus | **Transcript + timing only.** Audio retained as an artifact. State this in the coverage matrix. |
| 2 | "Portable computer use" | 4 incompatible action vocabularies; inspect_ai's Gemini bridge maps 3+ actions to a **no-op** (`_google_computer_use.py:152-156`); OpenAI drops `triple_click`→`double_click` (`_openai_computer_use.py:159-162`); OpenAI's `computer_call_output` has no error channel (`_openai_computer_use.py:109-113`); Anthropic's action set changes per dated tool version (`computer_20250124.ts:11-27` vs `computer_20251124.ts:11-28`) | Define **one PACT action vocabulary** + per-target mapping tables with **mandatory loss reports**. Ship `browser` environment first (most uniform); desktop `mac/windows/ubuntu` as `experimental`. |
| 3 | "Model catalogue tells you what a model can do" | LiteLLM omits `supports_computer_use` on OpenAI's own `computer-use-preview`; models.dev has no `computer_use` field at all; LangChain must ship a hand-maintained override TOML; one LiteLLM record's `mode` is the schema's docstring | Catalogue is a **pre-filter only** (R5). `strict` mode refuses unprovenanced fields. Add a `probe` verification level. |
| 4 | "Video is first class" | MCP has no video content type in 2025-11-25 **or** draft; Anthropic has none; AutoGen has none; the Claude Agent SDK has none; only Pydantic AI, LangChain and Vercel model it | Video **in** = supported where the binding supports it, reported `unsupported` elsewhere. Video **out** = out of scope for v1. |
| 5 | "Media round-trips through the Expansion Rule" | Base64 in `canonical.json` is a known blow-up (OpenHands flag comment; SWE-agent's 10 MB observation cap) | Content-addressed blob store + `ref:` in canonical.json; inline only under a profile threshold. |
| 6 | "Tool results can be multimodal everywhere" | AutoGen `FunctionExecutionResult.content: str`; Claude Agent SDK drops audio and binary resources with a log warning (`__init__.py:512, 516`) | `degraded` lattice entries with reports; harness-lowering fallback = emit media as a following user part. |
| 7 | "Audio streaming works in the agent loop" | Files are atomic stream parts in Vercel v4 and Pydantic AI has no `FilePartDelta`; duplex audio lives in a *separate model interface* (`realtime-model/`) or a *separate pipeline* (`voice/`) | Model voice as a distinct **session shape** with a separate `realtime` model-role binding. Do not pretend it is a content part. |
| 8 | "Air-gapped multimodal eval" | DeepEval multimodal metrics require a vision-capable judge model; no local TTS anywhere | Require a declared **local vision judge** in the profile; mark audio-out evals as network-dependent. |
| 9 | "Computer-use evals are deterministic" | Only static/simulated environments are reproducible (OS survey §4.2.2); live sites are explicitly called out as non-reproducible | Type the environment `replay|simulated|live`; exclude `live` from CI gates by default. |
| 10 | "Safety checks are handled" | Provider-originated `pending_safety_checks` exist **only** in the OpenAI path; no other framework models them | Third approval channel, default **not** auto-acknowledged. |

**Things that ARE ready and should be promised confidently:**
- Image input, document/PDF input, and provider-file-ID references across all seven targets
  (modulo AutoGen's tool-result gap).
- A single media-typed part model — three independent projects converged on it.
- The approval vocabulary `{allow,deny} × {once,always} + reason` — four independent
  implementations agree.
- Sandbox declaration — six systems, a clear common field set, `{type, config}` adapter seam
  already proven by inspect_ai.
- Config-only image evals — promptfoo's `file://` loading + DeepEval's five image metrics cover it.
- Modality-aware cost data — LiteLLM already carries per-audio-token and per-second pricing.

---

## 6. Recommended v1 conformance scoping

| Feature | v1 level | Rationale |
|---|---|---|
| `image` in (url/bytes/file/providerRef) | **native** on all 7 | universal |
| `document` in (PDF, txt, csv, docx) | **native** on 5, `degraded` AutoGen/Claude-SDK | verified per §1.2 |
| `image` out (model-generated) | **native** on Pydantic AI / Vercel / OpenAI Agents; `unsupported` Anthropic-family | `content_block.py` has no image member |
| `audio` in — cascaded (STT → text) | **native** everywhere (STT is a separate model role) | works even where the message model has no audio |
| `audio` in — native to the model | **native** on Pydantic AI (Chat Completions) / LangChain / Vercel; `unsupported` elsewhere; **error** on OpenAI Responses | `models/openai.py:3469-3470` |
| `audio` out / duplex voice | **native** only where a `realtime` model role is bound (Vercel, OpenAI Agents); `emulated` via TTS elsewhere | separate interface everywhere |
| `video` in | `native` on 3, `unsupported` on 4; **`unsupported` for all MCP tools** | MCP ContentBlock lacks video |
| `computer_use` — browser | **native** OpenAI Agents / Vercel-Anthropic; **harness-lowered** elsewhere via MCP browser tool | PACT owns the action vocabulary (D12) |
| `computer_use` — desktop (X11) | `experimental` | display geometry + action drift |
| Tool approval gates | **native** on 6 of 7 (AutoGen via harness) | converged vocabulary |
| Provider safety checks | **native** OpenAI only; `unsupported` reported elsewhere | |
| Sandbox declaration | **native** via `{kind, config}` seam | D24: adapter-shaped, minimal |

---

## 7. Superset check against `bud.dev/v1` (D3)

Everything the Bud manifest expresses in this area must be expressible in PACT on day one:

| Bud manifest feature | Evidence | PACT expression |
|---|---|---|
| `input.dictation{enabled, provider: openai\|groq\|elevenlabs\|local\|default, model, maxAudioBytes}` | `sdk-and-declarative-dev.md:2519-2527` | `models.roles.stt: {provider, model, maxBytes}` + `interface.input.audio.mode: transcribe` |
| Local Whisper for air-gapped transcription | `sdk-and-declarative-dev.md:2549-2553` | `profiles/airgapped.yaml` binds `stt` to a local model |
| "channels can use dictation for voice attachments, but the transcribed text is still run input" | `sdk-and-declarative-dev.md:2554-2556` | This is the **cascaded** mode. PACT must be a *strict superset*: also support `interface.input.audio.mode: native` and `session: duplex`. |
| `security.sandbox.profile: inherit` | `sdk-and-declarative-dev.md:2160-2161` | `sandbox: {profile: <name>}` with profile inheritance (F-1) |
| `security.promptInjection.action: require_approval` | `sdk-and-declarative-dev.md:2153-2155` | `policy.approvals.rules[].when: injection_detected` |
| `policy.toolOrigin.mode: off\|audit\|ask_on_cross_origin\|deny_sensitive` | `sdk-and-declarative-dev.md:2147-2149` | `policy.approvals.rules` with an origin predicate |
| Parity-contract label "image behavior such as local marker extraction or unsupported MIME types" | `sdk-and-declarative-dev.md:2094` | This is *already* a per-provider capability lattice entry. PACT formalises it as `lattice[adapter][provider].media[mediaType] = native\|emulated\|degraded\|unsupported`. |
| MCP prompt/resource content "structured text, image, resource, and resource-link" | `sdk-and-declarative-dev.md:1588-1589` | maps to the PACT part model directly |

No modality feature in the Bud manifest is inexpressible in the proposed model. The one place PACT
**must go beyond** it is duplex voice: Bud today degrades voice to text before the run.

---

## 8. Open questions for the architecture doc

1. **Does `canonical.json` carry blob bytes at all, ever?** My recommendation is never (refs only),
   but that interacts with the digest/signing story (O1.2): the digest must then cover
   `hash(canonical.json) + hash(each referenced blob)`, i.e. a Merkle root, not a single file hash.
2. **One action vocabulary or a family?** Browser and desktop have genuinely different affordances
   (`navigate`/`open_web_browser` are meaningless on a desktop; `key`/`hold_key` are meaningless in
   a headless DOM driver). Options: one superset with per-environment `supported` subsets, versus
   `computer.browser.*` and `computer.desktop.*` as distinct resource kinds.
3. **Does a media part carry its own retention/redaction policy?** AC-4.4 requires trace→eval
   promotion "preserving redaction policy". A screenshot may contain PII that the text does not.
   Suggests `retention: {redact: [pii], ttlDays: 30}` on the part.
4. **Where does the STT/TTS boundary sit for eval replay?** If an eval case supplies a `.wav` and
   the binding is cascaded, the STT model becomes part of the system under test. Should the eval be
   able to pin a reference transcript to isolate the agent from STT variance?
5. **Screenshot pruning as a strategy variable** — SWE-agent elides old images
   (`history_processors.py:171-174`) and this measurably changes behaviour and cost. Is
   `strategy.mediaRetention: {keepLastN: 3}` in the plural strategy space (optimisable by GEPA), or
   in the contract? My instinct is strategy, which means the optimizer can tune it — an attractive
   result for D9's end-to-end demo.
6. **`allowed_callers` on provider tools** (`beta_tool_computer_use_20250124_param.py:29-31`) lets a
   computer tool be invoked *from inside* a code-execution sandbox. That is a nested-capability
   model PACT has no vocabulary for yet.
7. **Should PACT ship the normalised computer tool as an MCP server** (making it a no-code
   `tools/computer.yaml` reference) rather than a built-in? That would satisfy D14 with zero new
   concepts, at the cost of an MCP round-trip per action.
