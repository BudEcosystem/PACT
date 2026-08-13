# PACT research stream — SLO & Observability

**Date:** 2026-07-26 · **Stream:** `slo-observability` · **Status:** research notes, evidence-linked.
**Binding inputs read first:** `docs/00-THESIS.md`, `docs/01-DECISIONS.md` (D1–D28).
**Scope:** the *operational contract* — TTFT, TPOT/ITL, E2E latency, cost, throughput — across
all four modalities (D16) and all four deployment targets including air-gapped (D17),
plus the trace schema that must serve evals, learning, and SLO verification from one stream.

**Rules of evidence applied.** Every factual claim below carries a `file:line` or a document
section. Where I computed something (percentile sample sizes, vision token counts) I show the
computation and mark it **[DERIVED]** — reproducible, not cited. Where I am proposing rather than
reporting, I mark it **[PROPOSAL]**. Negative findings are marked **[NEGATIVE]** and are treated
as results.

---

## 0. Executive summary — the eight things that change the design

1. **There is no such thing as "TTFT" without a named measurement point.** vLLM's *client*
   TTFT fires on the first SSE frame that carries `choices`, even if the delta contains only
   `role` and no content
   (`research/repos/routing/vllm/vllm/benchmarks/lib/endpoint_request_func.py:403-408`).
   AgentOps' TTFT fires only on the first delta with non-empty `content` **or** a `tool_calls`
   entry (`research/repos/eval/agentops/agentops/instrumentation/providers/openai/stream_wrapper.py:109-125`).
   vLLM's *server* TTFT is `first_token_ts - scheduled_ts` and excludes queueing and network
   (`research/repos/routing/vllm/vllm/v1/metrics/stats.py:466-468`). OTel names the client-side
   quantity `time_to_first_chunk` and reserves `time_to_first_token` for the server
   (`research/repos/protocols/otel-semconv/model/gen-ai/deprecated/metrics-deprecated.yaml:99-188`).
   These are three different numbers for the same request. **PACT must name the observer, not the metric.**

2. **No open model catalogue carries latency.** The LiteLLM catalogue — 2,979 models, 145
   distinct keys, 81 of them cost keys — has **zero** TTFT/TPOT/throughput fields, and `rpm`/`tpm`
   for only 56 models
   (`research/repos/routing/litellm/litellm/model_prices_and_context_window_backup.json`, enumerated §1.4).
   D8's local-first catalogue therefore *cannot* inherit SLO estimates from anywhere; PACT must
   define an SLO record and populate it by measurement.

3. **Latency is not a property of a model; it is a property of a (model, serving config,
   operating point).** vLLM's own tuner sweeps `max-num-seqs` × `max-num-batched-tokens` ×
   `request-rate` × `prefix-cache-hit-%` and *searches* for the config that meets a P99 E2E
   budget (`research/repos/routing/vllm/benchmarks/auto_tune/README.md`, "How It Works" §3).
   A scalar `ttft_p95: 400ms` in a catalogue is meaningless. Estimates must be tuples over a
   declared operating point, with error bars.

4. **Agent E2E latency is a *censored* distribution.** The harness survey's Terminal-Bench 2.0
   analysis (32,604 trial records) reports timeout rates of 7.9 %–20.7 % for the *same model*
   under different harnesses (arXiv:2606.20683 §7.4, Tab. 8). When 20.7 % of runs are truncated
   by a timeout, p90 and p95 of E2E latency **do not exist**. Any SLO language that lets an
   author write `e2e_p95` without also constraining the timeout rate is unsound.

5. **The Bud run ledger has no wall clock.** `RunEvent` is `{seq, kind, status, message,
   metadata: BTreeMap<String,String>}` — no timestamp
   (`gaia-ai-runtime/bud-agentic-runtime/src/lib.rs:8463-8473`). `BudRunPlan` has no
   `startedAt`/`finishedAt` (`:8253-8301`). `BudRunTraceItem` is ordered by `seq` only (`:8814-8830`).
   Time exists *only* inside the budget subsystem (`BudRunBudgetRecord.recorded_at_unix_ms`,
   `src/policy_runtime.rs:960-978`). Reconciliation is therefore an *additive* change: PACT
   adds a timing plane; it does not rewrite the causal ledger.

6. **DeepEval cannot express an SLO.** 53 metric classes; none measures latency, cost, or
   throughput of the system under test. `LLMTestCase` carries `token_cost` and `completion_time`
   (`research/repos/eval/deepeval/deepeval/test_case/llm_test_case.py:385-394`) but **no metric in
   `deepeval/metrics/` reads either field**. `BaseMetric.evaluation_cost` is the cost of running
   the *judge* (`deepeval/metrics/base_metric.py:57,90-95`). Given D6 (DeepEval first) and
   O4.2 (config-only SLO assertions), SLO predicates must be a **native PACT metric family**,
   not a DeepEval provider metric.

7. **Cost is not `tokens × price`.** The catalogue has 4 context-tier breakpoints
   (`*_above_128k/200k/272k/512k_tokens`), 3 service tiers (`_flex`, `_priority`, `_batches`),
   separate audio/image/video/character/second/request/pixel units, and cache read/write lines.
   OpenAI's own Agents SDK keeps `request_usage_entries` precisely because "the aggregated
   `input_tokens` would be 330K, but `request_usage_entries` would preserve the [100K, 150K, 80K]
   breakdown" (`research/repos/frameworks/openai-agents-python/src/agents/usage.py:160-171`).
   **Cost MUST be computed per model call and summed. Summing tokens first is wrong.**

8. **Voice, vision, and computer use each break a different assumption.**
   Audio input tokens cost 8×–67× text tokens across 116 catalogue models (§7.1);
   a 16:9 screenshot costs a fixed **1,105** input tokens at OpenAI `detail:"high"` regardless of
   resolution **[DERIVED]** (§7.2); and computing that number requires an HTTP GET of the image
   when the URL form is used (`litellm/litellm_core_utils/token_counter.py:206-218`) — a network
   dependency that violates D17.

---

## 1. Evidence survey — what the ecosystem actually measures

### 1.1 vLLM — the reference definitions

`research/repos/routing/vllm/vllm/benchmarks/serve.py`

| Metric | Definition in source | Line |
|---|---|---|
| `ttft` | `time.perf_counter() - st` at the **first SSE frame containing `choices`** | `lib/endpoint_request_func.py:231-236` (completions), `:400-408` (chat) |
| `itl` | `timestamp - most_recent_timestamp` for every frame after the first | `lib/endpoint_request_func.py:240`, `:412` |
| `latency` (E2EL) | `most_recent_timestamp - st` — the **last content frame**, *excluding* the trailing `usage`/`[DONE]` frame | `lib/endpoint_request_func.py:257`, `:424` |
| `tpot` | `(latency - ttft) / (output_len - 1)`, only when `output_len > 1` | `serve.py:607-611` |
| `request_throughput` | `completed / dur_s` | `serve.py:731` |
| `output_throughput` | `sum(actual_output_lens) / dur_s` | `serve.py:733` |
| `max_output_tokens_per_s` | max over 1-second buckets of reconstructed token emission times | `serve.py:678-706` |
| `max_concurrent_requests` | max over 1-second buckets of in-flight requests | `serve.py:693-706` |
| `rtfx` | `input_audio_duration / dur_s` — **real-time factor for audio** | `serve.py:762` |
| `goodput` | fraction of requests satisfying **all** declared SLOs simultaneously | `serve.py:622-645` |

Percentiles: `np.percentile(xs, p)` — exact, linear interpolation, over the *whole* run
(`serve.py:735-759`). Selectable metrics for percentiles: `ttft, tpot, itl, e2el`
(`serve.py:1686-1687`). Goodput SLO names: `ttft, tpot, e2el` only (`serve.py:1365`), parsed
as `KEY:VALUE` millisecond pairs (`serve.py:1384-1397`).

**Two subtleties that matter for spec text.**

- *Goodput and percentile TPOT are computed over different populations.* `tpots` excludes
  requests with `output_len <= 1`; `all_tpots` includes them with `tpot = 0.0` and is the list
  fed to goodput (`serve.py:607-613`, `:631-635`). A one-token reply therefore *always* passes
  the TPOT goodput SLO. PACT must state which population its TPOT SLO ranges over.
- *E2EL excludes the usage frame.* An agent that needs the `usage` block to compute cost pays
  a tail the E2EL number does not show.

### 1.2 vLLM server-side decomposition — the only place queueing is visible

`research/repos/routing/vllm/vllm/v1/metrics/stats.py:452-499`

```
e2e_latency   = now                - arrival_time
queued_time   = scheduled_ts       - queued_ts        # QUEUED → first SCHEDULED
prefill_time  = first_token_ts     - scheduled_ts     # includes preemptions
decode_time   = last_token_ts      - first_token_ts   # includes preemptions
inference_time= last_token_ts      - scheduled_ts
mean_tpot     = decode_time / (num_generation_tokens - 1)
```

Emitted as Prometheus histograms with these bucket sets
(`vllm/v1/metrics/loggers.py`):

| Histogram | Buckets (s) | Line |
|---|---|---|
| `vllm:time_to_first_token_seconds` | 0.001…2560 (22 buckets, dense below 1 s) | `:796-822` |
| `vllm:inter_token_latency_seconds` | 0.01…80 (19 buckets) | `:829-857` |
| `vllm:request_time_per_output_token_seconds` | 0.01…80 | `:859-887` |
| `vllm:e2e_request_latency_seconds` | 0.3…7680 (21 buckets) | `:889-917` |
| `vllm:request_queue_time_seconds` | same as e2e | `:922-929` |
| `vllm:request_inference_time_seconds` | same as e2e | `:932-939` |
| `vllm:request_prefill_time_seconds` | same as e2e | `:942-949` |
| `vllm:request_decode_time_seconds` | same as e2e | `:952-959` |

Implication: **client TTFT = queue + prefill + network + client-side scheduling.** Only the
middle two are the model's; the first is the fleet's and the last is the deployment's. An
SLO written against a model is under-specified.

### 1.3 SGLang — same shape, three additional facts

`research/repos/routing/sglang/python/sglang/benchmark/serving.py`

- `concurrency = np.sum(e2e_latencies) / dur_s` — Little's Law, average in-flight requests
  (`:1234`). Cheap, exact, and the right primitive for a throughput SLO.
- **Speculative decoding corrupts ITL.** When `spec_accept_length > 0`, SGLang *re-tokenizes*
  each streamed chunk and divides the chunk's ITL by the number of tokens it actually contained,
  emitting `adjusted_itl` repeated per token (`:1102-1110`, `:1193`). Without this, an
  accept-length-3 speculative decoder reports ITL 3× too high.
- Vision tokens are tracked separately at the request level:
  `total_input_text` vs `total_input_vision` (`:1097-1099`, `:1197-1198`).

### 1.4 LiteLLM — the de-facto model catalogue, and what it does *not* have

`research/repos/routing/litellm/litellm/model_prices_and_context_window_backup.json`

- **2,979 model entries, 145 distinct keys, 81 of which are cost keys.**
- **0 entries carry any latency, TTFT, TPOT, or throughput figure.** **[NEGATIVE]**
- `rpm` on 56 entries, `tpm` on 56 entries — the only rate information present.
- 916 entries carry a `source` URL. Provenance exists but is *per model*, not *per figure*,
  and is a bare URL with no date, harness, or method.

Cost-key families (full list in §5.3): base token, 4 context-length tiers
(`_above_128k/200k/272k/512k_tokens`), 3 service tiers (`_flex`, `_priority`, `_batches`),
cache create/read (incl. `_above_1hr`), audio token / audio-per-second, image / image-token /
pixel, video token / video-per-second (with 8 s and 15 s interval breakpoints), character,
`input_cost_per_request`, `input_cost_per_second`, `output_cost_per_reasoning_token`,
`code_interpreter_cost_per_session`, `file_search_cost_per_1k_calls`,
`file_search_cost_per_gb_per_day`, `vector_store_cost_per_gb_per_day`,
`search_context_cost_per_query` (by context size), `web_search_billing_unit`,
`computer_use_input/output_cost_per_1k_tokens`, `ocr_cost_per_page`, `annotation_cost_per_page`,
`regional_processing_uplift_multiplier_eu/us`.

**Router "TTFT" is not TTFT.** `research/repos/routing/litellm/litellm/router_strategy/lowest_latency.py:104-109`:

```python
time_to_first_token = safe_divide_seconds(ttft_seconds, completion_tokens)
```

LiteLLM divides TTFT by the completion-token count before storing it, and routes on that
(`:437-447`). It is a per-token-normalised prefill proxy, not TTFT. Any telemetry harvested
from a LiteLLM gateway is **not** comparable to vLLM/SGLang/OTel TTFT. **[NEGATIVE]**

`completion_start_time` (the raw first-chunk stamp) is set by the streaming wrapper and
defaults to `end_time` if the stream never yielded
(`litellm/litellm_core_utils/litellm_logging.py:1849-1851`), so a non-streaming call silently
reports TTFT == E2E (`:5051-5073`).

**Catalogue loading is remote-by-default with a local fallback** —
`litellm/litellm_core_utils/get_model_cost_map.py`. `LITELLM_LOCAL_MODEL_COST_MAP=True` forces
local; otherwise it fetches
`https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json`
(`litellm/__init__.py:404`, `:518`) and validates the result against the bundled backup
(non-empty dict; ≥ `MODEL_COST_MAP_MIN_MODEL_COUNT`; not shrunk beyond
`MODEL_COST_MAP_MAX_SHRINK_RATIO`). `get_model_cost_map_source_info()` returns
`{source, url, is_env_forced, fallback_reason}`. This is a good D8/D17 pattern to copy —
**but PACT must invert the default to local-first and move provenance from map-level to
figure-level (AC-3.3).**

### 1.5 OpenTelemetry GenAI semconv — the naming authority, and its status

`research/repos/protocols/otel-semconv/`

| Instrument | Meaning | Line |
|---|---|---|
| `gen_ai.client.operation.duration` | histogram, seconds, client-observed | `model/gen-ai/deprecated/metrics-deprecated.yaml:74-98` |
| `gen_ai.client.operation.time_to_first_chunk` | "from when the client issues the generation request to when the first **chunk** is received"; streaming only | `:99-117` |
| `gen_ai.client.operation.time_per_output_chunk` | per chunk after the first, previous-chunk-end → this-chunk-end | `:118-137` |
| `gen_ai.server.request.duration` | "time-to-last byte or last output token" | `:138-154` |
| `gen_ai.server.time_per_output_token` | after the first token, successful responses only | `:155-171` |
| `gen_ai.server.time_to_first_token` | successful responses only | `:172-188` |

The chunk/token split is deliberate and exactly matches the correction vLLM's multi-turn
benchmark has to apply by hand (§1.6). **PACT should adopt the chunk/token distinction
verbatim.**

Span attributes worth adopting (`model/gen-ai/deprecated/registry-deprecated.yaml`):
`gen_ai.response.time_to_first_chunk` (double, seconds, `:562-576`);
`gen_ai.usage.input_tokens` — "SHOULD include all types of input tokens, including cached"
(`:577-593`); `gen_ai.usage.cache_read.input_tokens` (`:594-607`);
`gen_ai.usage.cache_creation.input_tokens` (`:608-621`); `gen_ai.usage.output_tokens` (`:622-633`);
`gen_ai.usage.reasoning.output_tokens` — "SHOULD be included in output_tokens" (`:634-647`);
`gen_ai.conversation.id`, `gen_ai.agent.{id,name,description,version}`,
`gen_ai.tool.{name,call.id,description,type}`, `gen_ai.workflow.name` (`:1295-1307`).

**Evaluation is already in the span vocabulary**: `gen_ai.evaluation.name`,
`gen_ai.evaluation.score.value` (double), `gen_ai.evaluation.score.label` (low-cardinality
string, examples `pass`/`fail`), `gen_ai.evaluation.explanation` (`:1230-1282`). This is direct
support for the "one stream serves evals and SLOs" requirement.

`gen_ai.operation.name` enum: `chat, generate_content, text_completion, embeddings, retrieval,
create_agent, invoke_agent, execute_tool, invoke_workflow` (`:914-965`).
Spans: `invoke_agent` client + internal (`spans-deprecated.yaml:531-596`), `execute_tool`
internal (`:597-648`), `invoke_workflow` internal (`:703-739`).

Anthropic reconciliation rule, normative and non-obvious:
`gen_ai.usage.input_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens`
(`spans-deprecated.yaml:690-701`). Provider token accounting is **not** uniform.

**Status caveat [NEGATIVE].** Every gen_ai group in this snapshot is `deprecated: moved to
the OpenTelemetry GenAI semantic conventions repository`, and `docs/gen-ai/README.md` is a
redirect stub. `git log -1` = `bfa5492`. Every gen_ai attribute is `stability: development`.
**PACT cannot treat OTel gen_ai as a stable dependency.** It should mirror the names into
`pact.dev/v1` with a documented mapping table and a conformance test that detects drift —
not `$ref` an external spec.

**What OTel gen_ai lacks, that PACT needs:** no agent-level TTFT, no step/turn counter, no
loop-iteration concept, no cost attribute, no SLO/verdict attribute, no notion of "first
user-visible output" distinct from "first model chunk", no censoring/timeout metric.

### 1.6 vLLM multi-turn benchmark — the closest thing to an agent SLO harness

`research/repos/routing/vllm/benchmarks/multi_turn/benchmark_serving_multi_turn.py`

- Field docs say what the raw numbers really are: `ttft_ms: float  # time to first chunk`;
  `tpot_ms: float  # time per output chunk (one or more tokens)` (`:104-105`).
- **Chunk → token correction** (`:486-505`):
  ```
  if output_num_tokens > 1 and output_num_tokens > first_chunk_tokens:
      tpot_ms = (latency_ms - ttft_ms) / (output_num_tokens - first_chunk_tokens)
  if first_chunk_tokens > 1:
      ttft_ms = max(0.1, ttft_ms - (first_chunk_tokens - 1) * tpot_ms)
  ```
  i.e. a multi-token first chunk *overstates* TTFT and must be back-corrected.
- **Percentiles gated on sample size** (`:1145-1155`):
  ```
  percentiles = [0.25, 0.5, 0.75, 0.9]
  if len(raw_data) >= 100:   percentiles.append(0.99)
  if len(raw_data) >= 1000:  percentiles.append(0.999)
  if len(raw_data) >= 10000: percentiles.append(0.9999)
  ```
  This is the only sample-size gate I found anywhere in the corpus. It is a *lower bound* on
  what is defensible (see §3).
- **Warm-up trimming is a first-class parameter**: results are recomputed for several
  `warmup_percentages`, each dropping a leading fraction of samples (`:1196-1204`).
  Cold-start (weight load, KV warm, JIT, prefix-cache cold) is a distinct regime.
- `approx_cached_percent = 100 * history_tokens / input_tokens` (`:481-484`) — the benchmark
  treats prefix-cache coverage as a *reported covariate* of latency, not a constant.

### 1.7 Agent-trace schemas (Phoenix / OpenInference / Langfuse / AgentOps)

| System | Latency model | TTFT | Percentiles | Cost |
|---|---|---|---|---|
| **OpenInference** (spec) | span start/end only | **none** | n/a | none (token counts only) |
| **Phoenix** | `latency_ms = end_time - start_time` on Span, Trace, ExperimentRun (`src/phoenix/db/models.py:779-785`, `:850-856`, `:1687-1693`) | **none** | SQL `percentile_cont` (exact) on Postgres, `func.percentile` on SQLite (`server/api/types/Project.py:816-820`, `:1468-1471`) | token-price model |
| **Langfuse** | observation start/end | `completion_start_time - start_time`, NULL if unset (`packages/shared/src/features/query/dataModel.ts:558-565`) | `p50/p75/p90/p95/p99` → ClickHouse `quantile()` (`features/query/server/queryBuilder.ts:150-158`) — **approximate** | `total_cost` per observation |
| **AgentOps** | `gen_ai.agent.execution_time`, `gen_ai.agent.turns`, `gen_ai.agent.runs` meters (`agentops/semconv/meters.py`) | `gen_ai.streaming.time_to_first_token` (`semconv/span_attributes.py:103`) — non-standard name | none built in | `gen_ai.usage.total_cost` |

OpenInference token vocabulary is richer than OTel's and worth mirroring:
`llm.token_count.{prompt, completion, total}`,
`llm.token_count.prompt_details.{cache_read, cache_write, audio}`,
`llm.token_count.completion_details.{reasoning, audio}`
(`research/repos/eval/openinference/spec/semantic_conventions.md:58-65`), plus `session.id`,
`user.id`, `tag.tags`, `metadata` (`:93-114`). Span kinds: *Chain, Retriever, Reranker, LLM,
Embedding, Agent, Tool, Guardrail, Evaluator, Prompt* (`spec/traces.md:169`).

**AgentOps is the only implementation in the corpus that confronts the tool-call TTFT
question.** `research/repos/eval/agentops/agentops/instrumentation/providers/openai/stream_wrapper.py:109-125`:

```python
if self._first_token_time is None:
    if any(choice.delta.content for choice in chunk.choices ...):
        ... span.add_event("first_token_received", {...})
    elif any(choice.delta.tool_calls for choice in chunk.choices ...):
        ... span.add_event("first_tool_call_token_received", {...})
```

Same attribute, **two distinct span events**. That is the right shape and PACT should
generalise it (§2.4).

**Approximation caveat.** ClickHouse `quantile()` is a reservoir-sampled approximate quantile.
A CI gate that reads p95 from Langfuse is reading an estimate of an estimate. PACT's SLO
*verification* path must compute exact order statistics over a bounded, retained sample; the
observability backend is for exploration, not for gating. **[NEGATIVE / design constraint]**

### 1.8 inspect_ai — the best time model in the corpus

`research/repos/eval/inspect_ai/`

- **`working_time` vs wall time.** `sample_working_time() = time.monotonic() - start_time -
  waiting_time` (`src/inspect_ai/_util/working.py:32-34`). `waiting_time` accumulates only the
  intervals where at least one task was blocked on a semaphore or a rate-limit retry, with
  explicit de-duplication of concurrent waits (`:56-94`).
- Five stackable limits: `token_limit`, `message_limit`, `turn_limit`, `time_limit` (wall clock,
  enforced by anyio cancellation scope), `working_limit` ("wall clock time minus any waiting
  time e.g. waiting before retrying in response to rate limits or waiting on a semaphore")
  (`src/inspect_ai/util/_limit.py:834-874`). Limits are **cooperative** — consumers must call
  `check_*_limit()` (`:578`, `:715`).
- **Every event carries both clocks.** `BaseEvent = {uuid, span_id, timestamp: UtcDatetime,
  working_start: float, metadata, pending}` (`src/inspect_ai/event/_base.py:16-30`).
  `ModelEvent` adds `completed: UtcDatetime | None` and `working_time: float | None`
  (`src/inspect_ai/event/_model.py:102-105`).

This is the model PACT should adopt: **dual-clock events, and a working-time SLO alongside a
wall-clock SLO.** An agent that spends 40 s in a 429 backoff is not "slow" in the sense the
author means when they write an interactivity budget; it is *throttled*, and that is a
different failure with a different fix.

### 1.9 The Bud run ledger (`bud.dev/v1`) — what PACT must be a superset of

`gaia-ai-runtime/bud-agentic-runtime/`

**Time.** `RunEvent` has *no* timestamp (`src/lib.rs:8463-8473`). `BudRunPlan` has *no*
`startedAt`/`finishedAt` (`:8253-8301`). `BudRunTraceSummary` exposes counts and
`latest_event_seq` only (`:8757-8782`); `BudRunTraceItem` is `{seq, event_kind, status, message,
metadata, checkpoint?, interrupt?}` (`:8814-8830`). The ledger is a **causal, replayable,
digest-stable event log** — deliberately clock-free. **[NEGATIVE for SLOs, positive for determinism.]**

**Budgets** (`src/policy_runtime.rs`) — the only operational contract that exists today:

```rust
pub struct AgentBudgetPolicy {          // :753-770
    wall_clock_ms: Option<u64>,
    turns: Option<u64>,
    model_tokens: AgentModelTokenBudget,   // {input, output, total}  :738-745
    tool_calls: Option<u64>,
    provider_cost_micros: Option<u64>,
    handoffs: Option<u64>,
    child_runs: Option<u64>,
}
pub struct BudRunBudgetUsage {          // :784-803
    turns, model_input_tokens, model_output_tokens, model_total_tokens,
    tool_calls, provider_cost_micros, handoffs, child_runs   // all u64
}
```

- Cost is **integer micro-dollars** (`provider_cost_micros: u64`) — no float drift, exactly
  summable. Adopt.
- `provider_cost_known: bool` on both the reservation and the record, and
  `provider_cost_unknown: bool` on the state (`:838-842`, `:859-860`, `:967-971`). Unknown cost
  is modelled, not guessed. Adopt — this is T7 honesty already implemented.
- Two-phase: **reserve worst case, then commit actuals.** `BudRunBudgetRecordStatus =
  {Reserved, Denied, Committed, Released, Expired}` (`:916-924`) with matching event kinds
  `run_budget_reserved/denied/committed/released/expired` (`:937-945`). Reservation is
  `estimated_input_tokens + model_config.max_output_tokens()`
  (`src/goose_adapter.rs:1650-1690`), with a smaller `fallback` reservation for the
  no-output case (`:1681-1686`).
- `BudRunBudgetRecord` **does** carry `recorded_at_unix_ms` and `event_seq` (`:960-978`), and
  `BudRunBudgetState` carries `started_at_unix_ms` / `deadline_at_unix_ms` (`:847-863`).
  So wall-clock already exists in exactly one subsystem, correlated to `event_seq`.
- `exceeded_dimensions: Vec<String>` (`:974-975`) — the failure names the dimension. Adopt.

**Gaps versus PACT's operational contract:** no TTFT, no TPOT, no percentile semantics, no
per-modality cost split, no throughput/concurrency, no timeout-rate, no distinction between
wall-clock and working time, no per-model-call cost record (only the aggregate counter).

**Guardrail stages** are already an 8-point taxonomy that PACT's timing plane can reuse as
span boundaries: `agent_input, model_input, model_output, tool_input, tool_output, handoff,
graph_transition, agent_output` (`src/policy_runtime.rs:76-111`).

`bud.dev/v1` manifests contain **no SLO block at all** — verified by reading every manifest
example in `sdk-and-declarative-dev.md` (`:283-322`, `:345-370`, `:374-388`) and grepping the
whole document for `slo|ttft|latency|percentile` (only prose hits, no schema).
PACT's `contract/slo.yaml` is therefore purely additive: **superset holds trivially.**

### 1.10 Protocol layer

- **MCP**: "Implementations **SHOULD** establish timeouts for all sent requests…
  **MAY** choose to reset the timeout clock when receiving a progress notification…
  however, implementations **SHOULD** always enforce a maximum timeout, regardless of progress
  notifications" (`research/repos/protocols/mcp-spec/docs/specification/2025-11-25/basic/lifecycle.mdx:246-262`).
  Progress notifications carry `{progressToken, progress, total?, message?}` and `progress`
  MUST increase (`.../basic/utilities/progress.mdx:33-56`). ⇒ **Tool-call latency is unbounded
  by protocol.** The harness owns the ceiling, and progress notifications are the only
  in-flight liveness signal PACT can surface to a user during a long tool call.
- **A2A**: `AgentCard` fields are `{name, description, supported_interfaces, provider, version,
  capabilities, security_requirements, default_input_modes, default_output_modes, skills,
  signatures}` (`research/repos/protocols/a2a-spec/specification/a2a.proto:365-390`).
  **No latency, cost, throughput, rate-limit, or SLO field anywhere in `a2a.proto`.** **[NEGATIVE]**
  `TaskState` = `SUBMITTED, WORKING, COMPLETED, FAILED, CANCELED, INPUT_REQUIRED, REJECTED,
  AUTH_REQUIRED` (`:187-208`); `TaskStatus` carries an ISO-8601 timestamp (`:211-218`).
  ⇒ For a remote sub-agent, the *only* portable timing signal is the sequence of
  `TaskStatus.timestamp` transitions. PACT's remote-agent SLO must be defined on those, and
  must attribute `INPUT_REQUIRED`/`AUTH_REQUIRED` time to a **blocked** bucket, not to latency
  (this is the A2A analogue of inspect_ai's `waiting_time`).

### 1.11 Prior in-repo results

- `gaia-ai-runtime/research/RESULTS.md:44-48` (bench 2, n = 20 tasks): FULL80 p50 latency 1.44 s
  at 1,773 prompt tokens; TOP5 1.42 s at 148 tokens; HIER 1.23 s at 259 tokens.
  Only **p50** is reported — correctly, for n = 20 (see §3).
- `RESULTS.md:10-12`: "both v4 models are reasoning models — completion caps must budget for
  thinking tokens (we hit this twice; caps ≥1200 for routing, ≥2500 for JSON tasks)."
  ⇒ Reasoning tokens are invisible in the output but consume the output budget *and* the
  decode-time budget. `output_cost_per_reasoning_token` exists in the catalogue as a separate
  price line. A TPOT SLO must state whether reasoning tokens count as output tokens
  (OTel says they do: `gen_ai.usage.reasoning.output_tokens` "SHOULD be included in
  `gen_ai.usage.output_tokens`", `registry-deprecated.yaml:645-646`).
- `SYNTHESIS.md:160-163` (F5): "Per-agent/per-run **budget objects** (tokens, cost, wall-clock)
  enforced in the runner." PACT's SLO block is the generalisation of exactly this.

### 1.12 Harness-design survey — agent-level evidence (arXiv:2606.20683)

- §7.2: evaluation dimensions beyond task success are *Task success, Reliability, Efficiency
  (token usage, API cost, compute cost), **Latency: wall-clock time or number of interactions**,
  Safety, Process quality.* ⇒ Step count is a first-class latency proxy, not a curiosity.
- §7.4, Terminal-Bench 2.0, 75 submissions / **32,604 trial records**:
  field coverage is reward 97.2 %, agent-runtime 98.1 %, full-runtime 100.0 %,
  input/output tokens **45.0 %**, **dollar cost 15.2 %**. The survey explicitly declines to make
  cross-harness monetary claims because "public cost fields are sparse and often depend on
  harness-specific accounting, cache handling, and model-price assumptions."
- Same-model, different-harness operating points (Tab. 8):

  | Model | Harness | median agent time | timeout rate | median input tokens |
  |---|---|---|---|---|
  | GPT-5.3-Codex | SageAgent | 5.7 min | 12.1 % | — |
  | GPT-5.3-Codex | Terminus 2 | 8.9 min | 20.7 % | 58.4 K |
  | GPT-5.3-Codex | Mux | 5.5 min | 8.1 % | 238.7 K |
  | Claude Opus 4.6 | Terminus 2 | — | 18.2 % | 79.4 K |
  | Claude Opus 4.6 | Meta-Harness | — | 7.9 % | 755.0 K |

- Median within-model accuracy range across harnesses **13.6 %**; 14 of 20 models vary ≥ 10 %.

**Three consequences.** (a) The harness — i.e. PACT's lowering — dominates latency, cost, and
timeout rate at fixed model. D26's "small runtime overhead" budget must be measured against a
*named* baseline harness, not "native", because "native" varies by 3.7× in input tokens.
(b) Cost is the least-reported and least-comparable dimension in public agent evaluation;
PACT emitting a *reproducible* per-call cost ledger is a genuine differentiator.
(c) Timeout rate is a first-class SLO dimension (§2.9).

---

## 2. Normative SLO definitions for an agent  **[PROPOSAL]**

### 2.1 The clock model

Three clocks, all three required on every event.

| Clock | Type | Source | Purpose |
|---|---|---|---|
| `wall` | RFC-3339 UTC, µs | system clock | correlation with external systems, human reading |
| `mono_ms` | f64 ms since run start | monotonic | **all latency arithmetic** — immune to NTP steps |
| `work_ms` | f64 ms since run start, minus blocked intervals | derived | working-time SLOs (inspect_ai model, `_util/working.py:32-34`) |

`blocked` intervals are attributable and typed:
`rate_limit | queue | approval | external_wait | scheduler | sandbox_boot`.
Only intervals where **no** in-flight work exists for the run count as blocked (de-duplicated
across concurrent branches, cf. `_util/working.py:56-94`).

**Rule.** Every latency SLO names its clock. `e2e_p95` defaults to `mono`; `e2e_work_p95` is
`work`. HITL approval time is always blocked, therefore always excluded from `work`.

### 2.2 The observation point

Every latency figure is tagged with **where it was observed**:

| Observer | Meaning | Precedent |
|---|---|---|
| `server` | inside the inference server; excludes network and gateway | `vllm/v1/metrics/stats.py:452-499` |
| `gateway` | at the model gateway / router; includes routing decision, excludes app | LiteLLM `Logging` |
| `runtime` | inside the PACT harness, at the transport boundary | new |
| `agent` | at the agent's declared output surface (what the caller sees) | new |
| `user` | at the end-user device (voice/UI) | out of PACT's control; declarable, never asserted by PACT |

**Only `runtime` and `agent` are PACT-owned and therefore the only two an SLO may be asserted
against.** `server`/`gateway` figures are *diagnostics*, carried in the trace for attribution.

### 2.3 Per-model-call metrics (adopted, renamed for precision)

For one model call *c*:

| PACT name | Definition | Adopted from |
|---|---|---|
| `call.ttfc_ms` | `mono(first response frame containing any choice/delta) − mono(request issued)` | OTel `gen_ai.client.operation.time_to_first_chunk`; vLLM `ttft` |
| `call.ttft_ms` | `ttfc_ms − (tokens_in_first_chunk − 1) × tpot_ms`, floored at 0.1 ms | vLLM multi-turn correction, `benchmark_serving_multi_turn.py:499-505` |
| `call.itl_ms[]` | per-frame `mono(frame_i) − mono(frame_{i-1})`, i ≥ 2 | vLLM `itl` |
| `call.tpoc_ms` | mean of `itl_ms[]` | OTel `time_per_output_chunk` |
| `call.tpot_ms` | `(last_content_frame − ttfc) / (output_tokens − tokens_in_first_chunk)` | vLLM `serve.py:607-611` + multi-turn `:488-492` |
| `call.e2e_ms` | `mono(last frame that changes the response, incl. the terminal `usage` frame) − mono(request issued)` | **diverges from vLLM deliberately** — see note |
| `call.queue_ms` | `server`-observed, when the provider reports it | `stats.py:464` |
| `call.blocked_ms` | retry/backoff/semaphore inside this call | inspect_ai `waiting_time` |

**Divergence, stated.** vLLM's E2EL stops at the last *content* frame
(`lib/endpoint_request_func.py:257`, `:424`), excluding the trailing `usage`/`[DONE]` frame.
PACT includes it, because PACT *needs* `usage` to compute cost and must not report a latency
that excludes work the agent actually waited for. This must be recorded in the CTS mapping table
so PACT numbers are known to be slightly larger than vLLM's.

**Speculative decoding.** If the provider reports an accept length, `itl_ms[]` MUST be
re-expanded per token as SGLang does (`benchmark/serving.py:1102-1110`); otherwise ITL is
reported as `chunk`-granular only and the `tpot` field MUST be null, not estimated.

### 2.4 Agent-level TTFT, including when the first thing is a tool call

This is the question the assignment names, and the corpus has no answer. Here is the proposal.

**Define three agent-level first-response metrics, not one.**

```
agent.ttfb_ms   "time to first byte"      — first frame of ANY kind emitted on the
                                            agent's output stream (incl. status/progress)
agent.ttft_ms   "time to first token"     — first frame carrying content of the agent's
                                            declared output modality (text token, audio
                                            frame, image chunk)
agent.ttfa_ms   "time to first action"    — first externally-observable side effect
                                            (tool invoked, handoff issued, approval requested)
```

Rules:

1. **`agent.ttft_ms` is the interactivity SLO. It is measured at the `agent` observation point,
   and it does NOT stop at the first model chunk.** If the loop's first model turn emits a tool
   call and no user-visible content, `agent.ttft_ms` keeps running through the tool execution and
   the second model turn, until user-visible content appears. This is the only definition that
   matches what a user experiences.

2. **`agent.ttfa_ms` is what stops on a tool call.** It is the debugging/attribution metric and
   the right SLO for a *background* agent (which has no interactivity requirement but does have a
   "is it alive?" requirement).

3. **A `filler` declaration decouples them.** If the loop declares
   `emit_on: [thinking, tool_start]` (voice agents must), the runtime emits a status frame and
   `agent.ttfb_ms` fires there, while `agent.ttft_ms` still waits for real content. Reporting
   `ttfb` as `ttft` is exactly the gaming vector PACT must foreclose:
   **an SLO on `ttfb` alone is unsatisfiable-proof and therefore forbidden as the sole
   latency assertion; the schema requires `ttft` or `e2e` whenever `ttfb` is asserted.**

4. **Per-frame typing is mandatory.** Every frame on the agent output stream carries
   `frame_kind ∈ {status, thinking, content, tool_call, tool_result, approval_request,
   handoff, artifact, usage, error, done}` and a `visible: bool`. `agent.ttft_ms` = first
   `content` frame with `visible: true`. This generalises AgentOps' two-event pattern
   (`first_token_received` / `first_tool_call_token_received`,
   `.../openai/stream_wrapper.py:115`, `:125`) from two cases to the whole frame taxonomy.

5. **Non-streaming agents.** If the agent's interface declares `streaming: false`,
   `agent.ttft_ms` is defined as equal to `agent.e2e_ms` and MUST be flagged
   `ttft_degenerate: true` in the trace. It must not be silently reported as a small number,
   which is what LiteLLM does when `completion_start_time` defaults to `end_time`
   (`litellm_logging.py:1849-1851`). **[NEGATIVE precedent, do not copy.]**

6. **`agent.ttft_ms` for an agent whose declared output modality is a tool call** (e.g. a pure
   router agent whose contract output is a structured handoff) — then `content` frames *are*
   the tool-call frames, and `ttft == ttfa`. The rule falls out of the contract's declared
   `output.modality`, which is why I/O contracts must be content-typed (G-1/D16) *before* SLOs
   can be defined.

### 2.5 Multi-step aggregation (one agent, N loop iterations)

Let a run have steps *s₁…s_N*, each with model calls *C(sᵢ)*.

| PACT name | Aggregation | Note |
|---|---|---|
| `run.steps` | `N` | the "number of interactions" latency proxy (arXiv:2606.20683 §7.2) |
| `run.model_calls` | `Σᵢ \|C(sᵢ)\|` | ≥ N when a step retries or self-consists |
| `run.e2e_ms` | `mono(terminal frame) − mono(run start)` | **not** `Σ` of anything |
| `run.work_ms` | `run.e2e_ms − Σ blocked` | |
| `run.model_ms` | `Σ_c c.e2e_ms` over all calls | can exceed `run.e2e_ms` under parallelism |
| `run.tool_ms` | `Σ_t t.duration` over tool spans | ditto |
| `run.overhead_ms` | `run.e2e_ms − critical_path(model ∪ tool ∪ blocked)` | **PACT's own tax; this is the D26 number** |
| `run.tpot_ms` | `Σ_c decode_ms(c) / Σ_c (output_tokens(c) − first_chunk_tokens(c))` | **token-weighted**, never mean-of-means |
| `run.ttft_ms` | as §2.4 | single value per run, not aggregated |
| `run.step_latency_ms[]` | per-step wall duration | the distribution that matters for computer use |

**Hard rules.**

- **Never average TPOTs across calls.** A run with one 5-token call and one 5,000-token call has
  a meaningless unweighted mean. Weight by output tokens. (vLLM's per-run mean is per-*request*;
  at agent level the equivalent is per-*run* token-weighted.)
- **`run.model_ms + run.tool_ms + blocked` may exceed `run.e2e_ms`.** Report the *critical path*
  separately from the *sum*; the ratio `Σ/critical_path` is the parallelism factor and is a
  useful strategy-selection signal.
- **`run.overhead_ms` is the only latency number PACT is allowed to be judged on for D26/F-4.**
  Everything else is the model's or the tool's.

### 2.6 Multi-agent aggregation

Runs form a tree via `RunLineage` / `child_run_ids` (Bud already models this:
`src/lib.rs:8357-8365`, `RunCheckpoint.child_run_ids` `:8514-8515`).

- **Latency composes by the graph, not by summation.** For each topology node kind:
  - *sequential*: `e2e = Σ children e2e + parent overhead`
  - *parallel / map-reduce*: `e2e = max(children e2e) + reducer + parent overhead`
  - *supervisor*: `e2e = Σ over selected children + supervisor decision latency × (rounds)`
  - *debate / self-consistency*: `e2e = max over parallel branches + judge`
  - The topology IR (O5.1) already encodes which; the SLO evaluator walks the same graph.
- **Cost and tokens compose by summation over the *distinct* call set.** The double-counting
  hazard is real: if a sub-agent's usage is both recorded on the sub-run and rolled up into the
  parent, naive summation doubles. **Rule: every model call has exactly one owning `run_id`; a
  parent's `cumulative_*` fields are derived and MUST be marked `derived: true`.** Phoenix
  already distinguishes `llm_token_count_*` from `cumulative_llm_token_count_*` on the span row
  (`src/phoenix/db/models.py:844-847`, rollups at `:959-968`) — adopt that naming.
- **`run.agents` and `run.handoffs`** are counters PACT inherits from Bud
  (`AgentBudgetPolicy.handoffs`, `child_runs`, `src/policy_runtime.rs:767-769`).
- **Remote sub-agents (A2A)**: latency contribution is measured from `TaskStatus.timestamp`
  transitions (`a2a.proto:211-218`); the interval spent in `INPUT_REQUIRED` or `AUTH_REQUIRED`
  is `blocked`, not latency. The `WORKING` interval is opaque and MUST be labelled
  `attribution: opaque` — a remote agent can never contribute to a TTFT/TPOT SLO, only to E2E.

### 2.7 Cost

**Definition.** `run.cost_micros: u64` = `Σ over model calls c: price(c)` where `price(c)` is
evaluated **per call** against the catalogue entry for the *actually served* model
(`gen_ai.response.model`, not `gen_ai.request.model`), using that call's own token vector.

The token vector per call (union of OTel + OpenInference + catalogue units):

```
input_text, input_cached_read, input_cache_write, input_cache_write_1hr,
input_audio, input_audio_cached, input_image, input_image_tokens, input_video,
input_characters, input_seconds, input_requests, input_pixels,
output_text, output_reasoning, output_audio, output_image, output_video,
output_characters, output_seconds,
tool_units: {web_search_queries, code_interpreter_sessions, file_search_calls,
             ocr_pages, annotation_pages, vector_store_gb_days}
```

Rules:

1. **Per-call evaluation is mandatory** because of context-length tiering. The catalogue has
   `input_cost_per_token_above_{128k,200k,256k,272k,512k}_tokens` and matching output/cache keys.
   OpenAI's Agents SDK keeps `request_usage_entries` for exactly this reason
   (`src/agents/usage.py:160-171`). Summing tokens across calls and applying one price is
   arithmetically wrong for any run that crosses a tier. **[Hard rule]**
2. **Service tier is part of the price key**, not a modifier: `_flex`, `_priority`, `_batches`
   variants exist for input, output, cache-create, and cache-read
   (`litellm/litellm_core_utils/llm_cost_calc/utils.py:214-217`, `:238-242`).
   The resolved tier is a lockfile field.
3. **Integer micro-dollars**, matching `provider_cost_micros: u64`
   (`src/policy_runtime.rs:798`). Round half-up at the per-call boundary; never accumulate floats.
4. **`cost_known: bool` per call**, aggregated to `run.cost_complete: bool`. If any call has an
   unknown price, the run's cost is a **lower bound** and a cost SLO MUST fail closed unless
   `allowLoss: cost_unknown` is declared. Bud already models this
   (`provider_cost_known` / `provider_cost_unknown`, `src/policy_runtime.rs:838-842`, `:859-860`).
5. **Cache economics are strategy-determined, not model-determined.** Across 691 catalogue models
   carrying both keys, `cache_read / input` price ratio has median **0.10**, min 0.0083, max 1.0;
   Anthropic's `cache_creation / input` ratio is **1.25**, with
   `prompt_cache_min_tokens` = 4096 (Opus 4.5) / 1024 (Sonnet 4.5) **[DERIVED from the catalogue]**.
   A loop whose prefix is stable pays 0.1×; a loop that mutates its system prompt per step pays
   1.25× to re-create the cache and gets nothing back. **Loop shape is a cost lever of ~12×.**
   PACT's cost estimator must read the loop IR, not just the model id.
6. **Reservation before commit.** Adopt Bud's two-phase pattern
   (`src/goose_adapter.rs:1650-1700`): reserve `estimated_input + max_output` at
   worst-case price, commit actuals, release the difference. This makes a cost cap *enforceable*
   rather than merely *reportable*, which matters because the alternative is discovering the
   overrun after paying for it.

### 2.8 Throughput and concurrency

- `throughput.requests_per_s = completed / window_s` (vLLM `serve.py:731`)
- `throughput.output_tokens_per_s = Σ output_tokens / window_s` (`serve.py:733`)
- `concurrency = Σ run.e2e_ms / window_ms` — Little's Law (SGLang `serving.py:1234`)
- `throughput.peak_output_tokens_per_s` and `throughput.peak_concurrency` from 1-s bucketing
  (`serve.py:673-706`)
- **`goodput_rate`** = fraction of runs satisfying **all** declared SLOs simultaneously
  (vLLM `serve.py:622-645`). This is the headline number; per-metric percentiles are the
  diagnosis.

For an *agent*, add:

- `throughput.steps_per_s` and `throughput.tool_calls_per_s` — the cost drivers.
- `throughput.runs_per_agent_instance` — needed for the residency/mailbox model (F5).

### 2.9 Censoring, timeouts, and error accounting  **— the rule the corpus is missing**

Agent runs are unbounded. Every real harness imposes a timeout, and Terminal-Bench 2.0 shows
timeout rates of 7.9 %–20.7 % for the same model (arXiv:2606.20683 §7.4 Tab. 8).
A timed-out run has E2E latency `≥ T`, not `= T`. The empirical distribution is
**right-censored at T**.

**Normative rules:**

1. Every latency SLO declaration MUST carry a `censor_at_ms` (explicit, or inherited from the
   run's `wall_clock_ms` budget).
2. `p` is **estimable only if `p < 1 − censored_rate`**. Asking for `e2e_p95` when 20.7 % of runs
   are censored is a *schema error*, reported as
   `SLO_UNESTIMABLE: e2e_p95 requires censored_rate < 0.05, observed 0.207`.
3. `timeout_rate` is a first-class SLO dimension with its own threshold.
4. The three run outcomes are disjoint and all three are counted:
   `completed | censored (timeout/budget) | failed (error)`. Percentiles are computed over
   `completed` only, and the report always states `n_completed / n_total`.
   vLLM prints failed-request errors and excludes them from percentiles (`serve.py:659-666`) but
   does not distinguish censored from failed — PACT must.
5. **Never** substitute `T` for a censored run's latency, and never drop censored runs silently.
   Both are the "silent degradation" T7 forbids.

### 2.10 Summary SLO vocabulary

```
Latency (all *_ms, all with {clock, observer, percentile}):
  agent.ttfb | agent.ttft | agent.ttfa | run.e2e | run.work
  run.step_latency | run.overhead | call.ttfc | call.ttft | call.tpot | call.itl
Rate:
  throughput.requests_per_s | throughput.output_tokens_per_s | concurrency
  throughput.steps_per_s | throughput.tool_calls_per_s
Cost:
  run.cost_micros | run.tokens.{input,output,cached_read,cache_write,reasoning,audio,image}
  run.cost_per_success_micros            (= Σcost / n_passing_eval)
Volume/shape:
  run.steps | run.model_calls | run.tool_calls | run.handoffs | run.child_runs
Reliability:
  goodput_rate | timeout_rate | error_rate | censored_rate
Modality-specific (§7):
  voice.response_latency | voice.barge_in_latency | voice.rtf | voice.underrun_rate
  vision.image_tokens_per_step
  cua.step_latency | cua.actions_per_task | cua.screenshot_tokens_per_task
```

---

## 3. Percentile semantics and sample size

### 3.1 What "p95" must mean in PACT

1. **Exact order statistics, not sketches.** Definition: for sorted completed samples
   `x₍₁₎ ≤ … ≤ x₍ₙ₎`, `pP = x₍k₎` with `k = ceil(P/100 × n)` (nearest-rank, no interpolation).
   *Rationale:* interpolation (numpy's default, `serve.py:739-741`) invents a value that was
   never observed; for a pass/fail CI gate the reported number must be a real measurement.
   PACT reports both `pP_nearest_rank` (the gate) and `pP_interp` (for continuity with vLLM/Phoenix).
2. **The sample is the run set, retained.** A PACT SLO verification stores the full vector of
   per-run measurements in `.pact/slo/<suite>/<run-set>.jsonl`. Percentiles are recomputed from
   raw samples, never from a backend's approximate aggregate. (Langfuse's `quantile()` is
   ClickHouse's reservoir-sampled approximation, `features/query/server/queryBuilder.ts:150-158`.
   Phoenix's `percentile_cont` is exact but is a *query*, not an artifact.)
3. **Percentile over what population?** Declared explicitly, one of:
   `per_run` (default), `per_step`, `per_model_call`, `per_tool_call`, `per_turn`.
   vLLM's ITL percentile is per-*token-interval* pooled across all requests
   (`serve.py:614`, `:748-753`) — a heavy-output request dominates. PACT must not silently pool.
4. **Warm-up is declared, not assumed.** Adopt the vLLM multi-turn convention of reporting
   at several warm-up fractions (`benchmark_serving_multi_turn.py:1196-1204`) and record
   `warmup_dropped: k`. A cold prefix cache is a different regime.
5. **Covariates are recorded with the sample**: input tokens, output tokens, cached fraction,
   concurrency at admission, model id, adapter, harness version, hardware. Without them a
   percentile is unreproducible.

### 3.2 Minimum sample sizes  **[DERIVED]**

A one-sided SLO gate "true `p`-quantile ≤ T at confidence 1−α" is a binomial test:
let `X = #{samples > T}`; under H₀ (true quantile = T), `X ~ Bin(n, 1−p)`. Accept the SLO iff
`P(Bin(n, 1−p) ≤ X) ≤ α`. Minimum `n` for α = 0.05:

| quantile | k=0 violations | k=1 | k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|---|---|
| p50 | 5 | 8 | 11 | 13 | 16 | 18 |
| p90 | 29 | 46 | 61 | 76 | 89 | 103 |
| **p95** | **59** | 93 | 124 | 153 | 181 | 208 |
| **p99** | **299** | 473 | 628 | 773 | 913 | 1049 |
| p99.9 | 2 995 | 4 742 | 6 294 | 7 752 | 9 151 | 10 511 |

Closed form for the zero-violation case: **`n ≥ ln(α) / ln(p)`**
(p95 → 58.4; p99 → 298.1; p99.9 → 2994.2).

Two-sided nonparametric 95 % CI for the quantile, expressed as the rank interval
`[x₍lo₎, x₍hi₎]` (width = hi − lo, i.e. how many order statistics the true quantile could be):

| n | p50 | p90 | p95 | p99 |
|---|---|---|---|---|
| 20 | [6,15] w=9 | **not estimable** | **not estimable** | **not estimable** |
| 24 | [7,17] w=10 | not estimable | not estimable | not estimable |
| 30 | [10,21] w=11 | [22,30] w=8 | not estimable | not estimable |
| 50 | [18,32] w=14 | [40,49] w=9 | not estimable | not estimable |
| 100 | [40,60] w=20 | [84,96] w=12 | [90,99] w=9 | not estimable |
| 200 | [86,114] w=28 | [171,188] w=17 | [183,196] w=13 | not estimable |
| 384 | [172,211] w=39 | [333,357] w=24 | [356,373] w=17 | [376,384] w=8 |
| 500 | [228,272] w=44 | [436,463] w=27 | [464,484] w=20 | [491,500] w=9 |
| 1000 | [469,531] w=62 | [880,918] w=38 | [937,964] w=27 | [983,996] w=13 |

"not estimable" = no rank interval within the sample attains 95 % coverage, i.e. the upper end of
the CI is `+∞`.

**Normative gate table for PACT.**

| Declared percentile | Minimum `n_completed` | Behaviour below the minimum |
|---|---|---|
| p50 | 20 | error |
| p75 | 30 | error |
| p90 | 50 | error |
| p95 | **100** | error |
| p99 | **400** | error |
| p99.9 | 3 000 | error |

These sit above the zero-violation binomial floor (so a single violation does not immediately
invalidate the run) and at/above the two-sided-CI estimability threshold. They are strictly
stricter than vLLM's gate (p99 at n ≥ 100, `benchmark_serving_multi_turn.py:1148-1149`), which is
the right direction for a CI gate as opposed to a benchmark report.

**Cross-check against in-repo practice.** `gaia-ai-runtime/research/RESULTS.md:44-48` used
n = 20 and reported **p50 only** — correct under this table.

### 3.3 The eval-suite tension  **[design constraint]**

D14 says a non-technical domain expert authors eval cases. Realistically that is 10–50 cases.
**A 50-case eval suite cannot support a p95 SLO with one run per case.** Resolutions, in
preference order:

1. **Repeat factor.** `slo.samples.repeats: 4` runs each case 4×, giving `n = cases × repeats`.
   Also gives a variance estimate for the *quality* metrics, which the optimizer needs anyway
   (R6, held-out protocol). Cost is the obvious objection; the SLO block therefore also carries
   `samples.max_cost_micros`.
2. **Synthetic load cases.** SLO-only cases that need no ground truth — the input distribution
   matters, the answer does not. Authored as a length/modality distribution, not as examples.
   This is the config-only analogue of vLLM's `--dataset` sweep.
3. **Production trace promotion.** AC-4.4 already requires trace→eval promotion; the same
   pipeline supplies SLO samples at production `n`. Requires the redaction policy to allow
   *timing without content*, which is a cheap policy to grant.
4. **Degrade the assertion, loudly.** With n = 40, `p95` is refused and the report says
   `p90 (n=40, CI rank [34,39])` plus `max observed`. Never silently compute p95 from 40 samples.

### 3.4 Additional statistical rules

- **Compare distributions, not point estimates.** CTS fidelity comparisons between adapters use a
  paired bootstrap on the per-case latency deltas (same cases, same seeds), reporting a CI on the
  median delta. D26's "a few percent" must be a CI that excludes the threshold, not a
  point difference.
- **Seed and record everything stochastic.** Temperature, sampling seed, tool-order shuffles, and
  concurrency schedule all go in the sample record. Otherwise the p95 is not reproducible and
  AC-7.3 (offline reproducibility) fails.
- **Report `n`, `censored_rate`, `error_rate` next to every percentile, always.** A percentile
  without them is not a claim.

---

## 4. Resolve-time estimation vs run-time measurement

### 4.1 What the catalogue can and cannot say

**Can (present in real catalogues today):** price per unit for ~20 unit kinds; `max_input_tokens`;
`max_output_tokens`; capability booleans (`supports_vision`, `supports_audio_input/output`,
`supports_computer_use`, `supports_reasoning`, `supports_prompt_caching`,
`supports_parallel_function_calling`, …); `rpm`/`tpm` for a few entries; `prompt_cache_min_tokens`;
`deprecation_date`.

**Cannot:** anything about time. Zero latency figures in 2,979 entries (§1.4). And this is not an
oversight — vLLM's tuner demonstrates that P99 E2E is a *search result* over
`{max-num-seqs, max-num-batched-tokens, request-rate, prefix-cache-hit-%, gpu-mem-util, TP, hardware}`
(`benchmarks/auto_tune/README.md`, "How It Works"). A single number cannot be right.

### 4.2 The proposed catalogue SLO record  **[PROPOSAL]**

Not a scalar. A set of **measurements at declared operating points**:

```yaml
# models/catalog.yaml → entry.slo
slo:
  measurements:
    - id: mp-a100-bs1-cold
      operating_point:
        deployment: onprem              # onprem | airgapped | saas | edge
        hardware: "1×A100-80GB"
        server: "vllm 0.11"
        tensor_parallel: 1
        max_num_seqs: 256
        max_num_batched_tokens: 2048
        concurrency: 1
        input_tokens: 4000
        output_tokens: 512
        prefix_cache_hit_pct: 0
      observed:                          # nearest-rank, from n samples
        n: 400
        ttfc_ms:  {p50: 190, p95: 260, p99: 410}
        tpot_ms:  {p50: 12.1, p95: 14.8, p99: 21.0}
        e2e_ms:   {p50: 6400, p95: 7900, p99: 9600}
      provenance:
        method: "vllm bench serve"
        harness_version: "..."
        date: 2026-07-20
        operator: "bud-perf-lab"
        raw: ".pact/slo/raw/mp-a100-bs1-cold.jsonl"
        digest: "sha256:..."
    - id: mp-a100-c32-warm
      ...
```

Rules:

- **A figure with no `provenance` cannot satisfy an SLO predicate in `strict` mode.** Direct
  extension of AC-3.3 from benchmark scores to SLO figures.
- Provenance is **per figure**, not per model — LiteLLM's map-level `source` info
  (`get_model_cost_map.py`, `get_model_cost_map_source_info()`) and per-model `source` URL
  (916/2979 entries) are both too coarse.
- Measurements are **immutable and content-addressed**; the resolver records which measurement id
  it used in `pact.lock`.

### 4.3 The estimator, and its honest error bars

Estimation is a two-stage model.

**Stage 1 — analytic, low error where it applies.**

```
call.ttfc ≈ queue(λ, config) + α · uncached_input_tokens + β + network
call.decode ≈ tpot(config, concurrency) · output_tokens
call.e2e ≈ call.ttfc + call.decode
```

`α` (prefill s/token) and `β` (fixed overhead) are fitted from ≥ 2 measurements at the same
operating point with different input lengths. This is a good model for *prefill* because prefill
is compute-bound and roughly linear in uncached tokens; it is exactly what the `queued/prefill/
decode/inference` decomposition (`vllm/v1/metrics/stats.py:463-476`) exists to expose.

**Stage 2 — the agent, where error explodes.**

```
run.e2e ≈ Σ over expected steps [ call.e2e(step) + tool.e2e(step) ] + overhead
```

The unknowns and their honest error contributions:

| Unknown | Why it is unknowable at resolve time | Error contribution |
|---|---|---|
| **Step count `N`** | Model-dependent, input-dependent, and the single largest term | **Dominant.** Terminal-Bench: same model, different harness → 5.5 vs 8.9 min median (1.6×) and 8.1 % vs 20.7 % timeout (2.6×) (arXiv:2606.20683 §7.4). |
| **Output tokens per step** | Reasoning models emit invisible thinking tokens; `RESULTS.md:10-12` shows caps of 1200–2500 were needed | Large; multiplies TPOT |
| **Prefix-cache hit rate** | Depends on loop shape, tenant mix, cache TTL, and server config | vLLM makes it an explicit sweep axis (`auto_tune/README.md`, use case 3) |
| **Concurrency at admission** | Depends on fleet load | vLLM's queue histogram exists precisely because this is unbounded |
| **Tool latency** | External systems; MCP sets no bound (`lifecycle.mdx:246-262`) | Unbounded |
| **Retries / rate limits** | Provider-side | Handled by the `work` clock, not by estimation |

**Stated position.** PACT's resolver MUST publish estimates as **intervals with a coverage claim
and a named dominant uncertainty**, and MUST refuse to bind on an estimate alone for the
interactivity-critical metrics.

Concretely, the resolver emits one of four verdicts per SLO:

| Verdict | Condition | Consequence |
|---|---|---|
| `MEASURED` | a catalogue measurement exists at an operating point within tolerance of the target, and n meets §3.2 | may bind |
| `INTERPOLATED` | between two measurements on the same axis | may bind; interval widened by the interpolation residual; recorded in the lockfile |
| `EXTRAPOLATED` | outside the measured envelope | **may not bind for `ttft`/`tpot`**; may bind for `cost` (cost is deterministic given tokens) |
| `UNKNOWN` | no measurement | fail closed; D11 recommendation search runs on the models that *do* have measurements |

**Error bars I am willing to defend, marked as engineering judgement rather than measurement:**

- `call.ttfc` at a *measured* operating point, ±1 concurrency step: **±20 % on p50, ±50 % on p95**
  — from vLLM's TTFT bucket geometry (`loggers.py:799-822` spans 0.001 s to 2560 s with dense
  buckets below 1 s, which is a designed-for-heavy-tail choice).
- `call.tpot` at a measured operating point: **±10 % on p50** — decode is the most stable
  quantity; it is nearly linear in batch occupancy.
- `run.e2e` for an agent: **the interval is at least [0.5×, 3×] of the estimate**, because the
  step-count and timeout terms are unbounded. Terminal-Bench's 1.6× same-model spread across
  harnesses is a *lower* bound on this, since it holds harness *family* roughly constant.
- `run.cost_micros`: **exact given the token vector**, ±(cache-hit uncertainty). If the loop's
  prefix is declared stable and the model supports caching, the interval on cost is roughly
  `[0.1×, 1.25×]` of the uncached estimate for the cacheable prefix portion **[DERIVED, §2.7.5]**.

**Therefore [PROPOSAL]:** `resolve` runs a **calibration probe** — a short, offline-capable
measurement (N runs of the agent's own eval smoke subset against the candidate binding) whenever
an SLO is asserted and the verdict would otherwise be `EXTRAPOLATED` or `UNKNOWN`. This is the
SLO analogue of T2's "evals are the oracle": *measure, do not assert*. It is air-gapped-compatible
because it only needs the local model.

### 4.4 What resolve-time estimation is genuinely good for

Not for asserting `ttft_p95 ≤ 400 ms`. It is good for:

- **Pre-filtering.** Eliminating candidates that cannot possibly meet the budget
  (e.g. `output_tokens × tpot_p50_floor > e2e_budget` → drop). Cheap, sound, one-sided.
- **Cost ranking for D11's recommendation.** Cost is deterministic given tokens; a token estimate
  from one calibration run makes the "3.1× cheaper" claim in D11's example computable.
- **Capacity planning.** `concurrency = throughput × latency` (Little's Law, SGLang `:1234`)
  turns a latency target into a fleet size.
- **Detecting impossible contracts early.** `ttft_p95 ≤ 200 ms` on a model whose measured
  `p50` at concurrency 1 is 190 ms is refusable at resolve time with high confidence.

---

## 5. The one-stream trace schema

### 5.1 Requirement

One event stream must simultaneously serve: (a) SLO verification, (b) eval scoring and
trace→eval promotion (AC-4.4), (c) optimizer training signal (F3/O3.4), (d) governance/audit,
(e) debugging. Today these are four different systems with four schemas.

### 5.2 Structure

Three planes over one identity spine.

```
IDENTITY SPINE (every record)
  trace_id, span_id, parent_span_id, run_id, root_run_id, seq
  spec_digest        # canonical.json digest — ties the trace to the exact spec
  lock_digest        # pact.lock digest — ties it to the exact binding
  agent{ id,name,version }, variant, adapter, framework, runtime, deployment_target
  session_id, conversation_id, user_id(hashed), tenant(optional)

CAUSAL PLANE  (Bud-compatible, clock-free, replayable)
  seq: u64, kind, status, message, metadata
    → byte-compatible superset of Bud RunEvent (src/lib.rs:8463-8473)

TIMING PLANE  (new; the SLO substrate)
  wall: RFC3339, mono_ms: f64, work_ms: f64, duration_ms, blocked_ms,
  blocked_reason?, observer ∈ {server,gateway,runtime,agent}
  frame_kind (on stream events), visible: bool

SEMANTIC PLANE (OTel gen_ai + OpenInference names, mirrored not referenced)
  gen_ai.operation.name, gen_ai.provider.name,
  gen_ai.request.model, gen_ai.response.model,
  gen_ai.usage.{input_tokens, output_tokens,
                cache_read.input_tokens, cache_creation.input_tokens,
                reasoning.output_tokens}
  llm.token_count.{prompt_details.audio, completion_details.audio}   # OpenInference
  gen_ai.tool.{name, call.id, type}, gen_ai.agent.*, gen_ai.workflow.name
  gen_ai.response.time_to_first_chunk
  pact.cost.{micros, known, price_key, service_tier, catalog_digest}
  gen_ai.evaluation.{name, score.value, score.label, explanation}
```

### 5.3 Span kinds

Union of OpenInference's 10 (`spec/traces.md:169`) and OTel's operations
(`registry-deprecated.yaml:914-965`), plus what PACT's loop IR requires:

```
run          workflow     agent        turn        step        loop_iteration
llm          tool         mcp_tool     handoff     subagent    remote_agent(a2a)
retriever    reranker     embedding    prompt      guardrail   evaluator
approval     memory_read  memory_write sandbox     optimizer_trial
```

`loop_iteration` and `step` are the two that no existing schema has, and they are the two an
agent SLO and the optimizer both need. `approval` is required so HITL time lands in `blocked`.

### 5.4 Event kinds on the agent output stream

The frame taxonomy from §2.4.4, which is what makes `ttfb`/`ttft`/`ttfa` computable from the
trace alone without re-instrumenting:

```
status | thinking | content | tool_call | tool_result | approval_request
| handoff | artifact | usage | error | done
```

Each carries `visible: bool`, `modality ∈ {text,image,audio,video,binary,tool}`,
`bytes`, `tokens?`.

### 5.5 Two derived records the stream must materialise

**`RunSloRecord`** — one row per run, the SLO sample:

```
run_id, spec_digest, lock_digest, case_id, repeat_index, seed
outcome ∈ {completed, censored, failed}, censor_at_ms, error_type?
agent_ttfb_ms, agent_ttft_ms, agent_ttfa_ms, ttft_degenerate: bool
run_e2e_ms, run_work_ms, run_blocked_ms{by_reason}
run_overhead_ms, critical_path_ms, sum_model_ms, sum_tool_ms
run_steps, run_model_calls, run_tool_calls, run_handoffs, run_child_runs
tokens{...full vector...}, cost_micros, cost_known
covariates{ input_tokens, cached_fraction, concurrency_at_admission,
            model, adapter, hardware, warmup_index }
```

**`CallCostRecord`** — one row per model call, so that tiered pricing is computable
(§2.7.1) and so cost is auditable independent of the aggregate:

```
run_id, span_id, provider, request_model, response_model, service_tier,
token_vector, price_key_used, unit_prices{...}, cost_micros, cost_known,
catalog_entry_digest
```

### 5.6 Why one stream actually works

- **SLO verification** reads `RunSloRecord` + `CallCostRecord`.
- **Evals** read the semantic plane; `gen_ai.evaluation.*` attaches verdicts back onto the same
  spans (OTel already defines these, `registry-deprecated.yaml:1230-1282`).
- **Trace→eval promotion (AC-4.4)** needs input/output content plus the redaction policy; both
  live on the semantic plane with `visible`/redaction flags.
- **Optimizer (F3/O3.4)** needs `(spec_digest, case_id, score, cost, latency, steps)` — a
  projection of the same two derived records. This is what makes "optimise for accuracy subject
  to a cost/latency SLO" a single-query operation rather than a join across three systems.
- **Governance** needs the causal plane plus identity, which is exactly what Bud already stores.

### 5.7 Retention and privacy

- The timing plane is **content-free** and can be retained at full fidelity under any redaction
  policy. This matters: it means production SLO samples (§3.3 option 3) are available even where
  content retention is forbidden.
- Content on the semantic plane follows the existing Bud posture: the ledger stores "only bounded
  metadata and digests" and "artifact payloads are read [separately]"
  (`bud-agentic-runtime/README.md:1723`, `:1731`). PACT keeps that: full content is a
  content-addressed artifact, the trace holds the digest.

---

## 6. Reconciliation with the Bud run ledger

### 6.1 The three changes required, in order of invasiveness

| # | Change | Invasiveness | Justification |
|---|---|---|---|
| R1 | **Add a timing sidecar keyed by `(run_id, seq)`** — `RunEventTiming { seq, wall, mono_ms, work_ms, blocked_ms, blocked_reason?, observer }` | **Additive, zero risk.** No change to `RunEvent`, so digests, replay, and determinism are untouched. | `RunEvent` has no timestamp (`src/lib.rs:8463-8473`); the ledger is deliberately causal |
| R2 | **Add `startedAt/finishedAt/durationMs` to `BudRunPlan`** and `firstOutputAt` | Small; `BudRunPlan` is already `camelCase` serde with optional fields | needed for `run.e2e_ms` without replaying the sidecar |
| R3 | **Extend `BudRunBudgetUsage`/`AgentBudgetPolicy` with SLO dimensions** | Medium: `deny_unknown_fields` on both (`policy_runtime.rs:754`, `:785`) means adding fields is a breaking wire change for old readers — which is what E-2 wants (reject loudly) | budgets are caps; SLOs are distributions; both belong in the operational contract |

**Why a sidecar rather than putting time in `RunEvent`.** The ledger's clock-freeness is a
feature: it is what makes replay deterministic and event digests stable. Putting a wall clock in
`RunEvent` would make every replay produce a different digest. The sidecar is joinable on
`(run_id, seq)`, is separately prunable under retention policy, and can be dropped entirely in
a deterministic-replay context. `BudRunBudgetRecord` already demonstrates the pattern — it
carries both `recorded_at_unix_ms` and `event_seq` (`policy_runtime.rs:976-977`).

### 6.2 Field-level mapping

| PACT | Bud today | Action |
|---|---|---|
| `run.cost_micros` | `BudRunBudgetUsage.provider_cost_micros` | **reuse verbatim** (u64 micro-dollars) |
| `run.cost_known` | `provider_cost_known` / `provider_cost_unknown` | **reuse verbatim** |
| `run.steps` | `BudRunBudgetUsage.turns` | reuse; PACT `steps` = Bud `turns` |
| `run.tool_calls` | `tool_calls` | reuse |
| `run.handoffs`, `run.child_runs` | `handoffs`, `child_runs` | reuse |
| `run.tokens.{input,output,total}` | `model_input_tokens/output/total` | reuse; **extend** with cached_read, cache_write, reasoning, audio, image |
| `slo.budget.wall_clock_ms` | `AgentBudgetPolicy.wall_clock_ms` | reuse as the **censoring threshold** (§2.9) |
| `slo.budget.work_clock_ms` | — | **new** |
| `slo.objectives.*` (percentile assertions) | — | **new** — Bud has caps only, no distributions |
| `slo.violation.dimensions` | `BudRunBudgetRecord.exceeded_dimensions` | reuse the pattern and the naming |
| SLO enforcement events | `run_budget_reserved/denied/committed/released/expired` | **extend** with `run_slo_violated`, `run_slo_verified`, `run_censored` |
| span boundaries | `BudGuardrailStage` 8-point taxonomy (`policy_runtime.rs:76-111`) | reuse as timing checkpoints |

### 6.3 Superset check against `bud.dev/v1` (D3)

Everything the Bud manifest expresses operationally is `AgentBudgetPolicy`'s seven fields.
PACT's SLO block contains all seven as `budget.*` (hard caps, enforced) plus `objectives.*`
(distributional assertions, verified). **The superset requirement is satisfied by construction,
and the converter is mechanical**: `spec.policy.budget` → `contract.slo.budget`, field for field.

---

## 7. Modality-specific concerns

### 7.1 Voice / streaming audio (D16)

**The budget is not TTFT; it is response latency measured from end-of-user-speech.**

The turn-detection layer sits between "user stopped talking" and "request issued", and it is
*configurable*:
`research/repos/frameworks/openai-agents-python/src/agents/realtime/config.py:96-124` —
`{type: semantic_vad|server_vad, eagerness, prefix_padding_ms, silence_duration_ms,
threshold, idle_timeout_ms, interrupt_response, create_response}`.
Default in that SDK is `{"type": "semantic_vad", "interrupt_response": True}`
(`.../realtime/openai_realtime.py:174`). Input sample rate default 24 000 Hz
(`.../voice/input.py:13`).

So the user-perceived latency decomposes as:

```
voice.response_latency_ms
  = vad_endpoint_ms            # silence_duration_ms + VAD compute; CONFIGURED, not measured
  + upstream_transport_ms
  + [ stt_ms ]                 # cascaded pipelines only; zero for speech-native models
  + agent.ttft_ms              # §2.4 — through any tool calls
  + tts_first_audio_ms         # cascaded only
  + downstream_transport_ms
  + playout_buffer_ms
```

Only `agent.ttft_ms` is PACT-owned. **PACT must therefore report the decomposition, assert on
`agent.ttft_ms`, and *declare* the rest as budget line items the deployment owns.** Asserting on
the end-to-end number PACT does not control would be dishonest.

Additional voice metrics PACT must define:

- **`voice.barge_in_latency_ms`** — from user speech onset to agent audio stop. The Realtime
  config exposes `interrupt_response` as a boolean (`config.py:108-109`), which means barge-in
  is a *capability*, and PACT's capability vocabulary needs it. Without a barge-in SLO a voice
  agent can be technically fast and conversationally unusable.
- **`voice.rtf`** (real-time factor) — vLLM already computes exactly this as
  `rtfx = input_audio_duration / dur_s` (`vllm/benchmarks/serve.py:762`, plumbed from
  `soundfile.info(f).duration`, `lib/endpoint_request_func.py:562`, `:575`).
  For streaming TTS the constraint is `rtf ≥ 1` sustained, or the audio underruns.
- **`voice.underrun_rate`** — fraction of playout buffer starvation events. This is the audio
  analogue of TPOT: TPOT tells you the *mean* is fine; underrun tells you the *tail* broke the
  experience. A single 400 ms ITL spike mid-sentence is audible; the same spike in a text
  stream is invisible.
- **Voice ITL must be asserted at p99, not p95.** A 60-second call at 20 frames/s has ~1,200
  frames; a p95 assertion permits 60 audible glitches per call.

**Voice token economics [DERIVED from `model_prices_and_context_window_backup.json`]:**

- 116 models price audio input tokens separately; the `input_cost_per_audio_token /
  input_cost_per_token` ratio ranges **8×–66.7×** (gpt-realtime: 3.2e-5 / 4e-6 = **8×**;
  gpt-4o-mini-audio-preview: **66.67×**).
- 50 models price audio output separately; ratio **4×–33.3×** (gpt-realtime: 6.4e-5 / 1.6e-5 = **4×**).
- `gpt-realtime` `max_input_tokens: 32000` — an order of magnitude below its text sibling, and
  audio consumes context ~8× faster per unit of content. **Voice sessions hit context limits
  fast; compaction strategy is a voice SLO concern, not just a quality concern.**
- `cache_creation_input_audio_token_cost` and `cache_read_input_audio_token_cost` exist as
  distinct keys — audio caching is priced separately from text caching.

### 7.2 Vision (D16)

**Image tokens are a step function of aspect ratio, not of resolution.**

Reproducing OpenAI's rule as implemented in
`research/repos/routing/litellm/litellm/litellm_core_utils/token_counter.py`:
`base_tokens = 85` (`:274`); `low`/`auto` → 85 flat (`:292-293`);
`high` → resize so short side ≤ 768 and long side ≤ 2000 (`:120-154`,
constants `MAX_SHORT_SIDE_FOR_IMAGE_HIGH_RES=768`, `MAX_LONG_SIDE_FOR_IMAGE_HIGH_RES=2000`,
`litellm/constants.py:301-302`), tile at 512×512 (`:303-304`), then
`total = 85 + 170 × tiles` (`token_counter.py:300-302`).

**[DERIVED]** — computed by re-implementing those exact functions:

| Source image | Resized | Tiles | Tokens (`detail:"high"`) |
|---|---|---|---|
| 512×512 | 512×512 | 1 | **255** |
| 768×768 | 768×768 | 4 | **765** |
| 1024×768 (XGA) | 1024×768 | 4 | **765** |
| 1280×800 (browser) | 1228×768 | 6 | **1105** |
| 1512×982 (laptop screenshot) | 1182×768 | 6 | **1105** |
| 1920×1080 (FHD) | 1365×768 | 6 | **1105** |
| 2560×1440 (QHD) | 1365×768 | 6 | **1105** |
| 3840×2160 (4K) | 1365×768 | 6 | **1105** |

Consequences for the spec:

1. **Every 16:9 screenshot costs exactly 1,105 input tokens.** Downscaling a 4K screenshot to
   FHD saves *nothing*. Cropping to 4:3 saves 31 %. This is a strategy lever the resolver and the
   optimizer can both use, and it is only visible if the IR records image dimensions.
2. **`detail: "low"` is a 13× token reduction** (85 vs 1105) and is a legitimate variant axis for
   model portability — it should be a first-class strategy field, not a provider passthrough.
3. **[NEGATIVE / D17 blocker]** Computing the `high` token count for a URL-form image performs an
   HTTP GET (`token_counter.py:206-218`, `_get_httpx_client()` + `safe_get`), bounded by
   `MAX_IMAGE_URL_DOWNLOAD_SIZE_MB`. In an air-gapped deployment this fails and the code falls
   back to `DEFAULT_IMAGE_WIDTH/HEIGHT = 300×300` (`litellm/constants.py:61-62`) → 4 tiles →
   765 tokens, or to `DEFAULT_IMAGE_TOKEN_COUNT = 250` (`:35`) if the caller opts in.
   **A 44 % under-estimate on every screenshot, silently.**
   ⇒ **PACT MUST require intrinsic dimensions on every image part in the IR** (`width`,
   `height`, `detail`), computed at ingest from local bytes, and MUST refuse to estimate image
   cost from a URL it cannot read. Cost estimation must never depend on network reachability.
4. **Prefill latency scales with image tokens.** SGLang tracks `total_input_vision` separately
   from `total_input_text` (`benchmark/serving.py:1098-1099`) because vision preprocessing is a
   distinct cost. PACT's token vector separates them for the same reason.
5. `input_cost_per_image` (flat per image) and `input_cost_per_pixel` exist as alternative
   billing units alongside `input_cost_per_image_token` — the cost function must dispatch on
   which key the catalogue entry actually has, exactly as LiteLLM does
   (`llm_cost_calc/utils.py:88-101`, `:222-227`).

### 7.3 Computer use / browser automation (D16)

166 catalogue models declare `supports_computer_use: true`; **only the `sample_spec` placeholder
carries `computer_use_input/output_cost_per_1k_tokens`** — i.e. in practice computer use is
billed at ordinary token rates plus screenshot image tokens **[DERIVED from the catalogue]**.

The dominant cost/latency structure:

```
cua.step_latency_ms = screenshot_capture + encode + upload
                    + model.ttfc + model.decode
                    + action_dispatch + settle_time(page load / animation)
cua.screenshot_tokens_per_task ≈ steps × 1105     (16:9, detail:high)
```

At 40 steps that is **44,200 image tokens minimum**, before any history retention. If the loop
retains prior screenshots in context, cumulative image tokens are **O(steps²)**.

Spec consequences:

1. **`cua.step_latency_ms` is the interactivity metric, not `run.e2e_ms`.** A 6-minute
   computer-use task with 40 smooth 9-second steps is acceptable; the same total with one
   200-second stall is not. Assert on the *step* distribution.
2. **`cua.actions_per_task` is a first-class SLO** — it is the "number of interactions" latency
   proxy the harness survey names (arXiv:2606.20683 §7.2) and it is the term the optimizer can
   actually move.
3. **Screenshot retention policy must be an IR field** (`keep_last_n_screenshots`), because it is
   the difference between O(N) and O(N²) cost. It is exactly the kind of thing that is invisible
   in a framework port and therefore exactly what "translate or nothing" (D15) is for.
4. **Approval gates are `blocked`, not latency.** D16 mandates approval gates for computer use;
   `inspect_ai`'s working/wall split (`_util/working.py:32-34`) is the mechanism. A human taking
   90 s to approve a click must not fail a latency SLO — but it must appear in `run.e2e_ms` and
   in the `blocked{approval}` breakdown, because the *user* waited.
5. **Sandbox boot is a distinct blocked reason.** Cold sandbox start (e2b/microsandbox/container)
   precedes step 1 and belongs in `blocked{sandbox_boot}`, which is also why warm-up trimming
   (§3.1.4) matters more here than anywhere else.

### 7.4 Text + tools (baseline)

Covered by §2.3–2.6. The one modality-specific note: **parallel tool calls change the
aggregation rule.** `supports_parallel_function_calling` is declared on 560 catalogue entries;
when true, a step's tool latency is `max` over the parallel set, not `Σ`, and the strategy
choice between parallel and sequential tool exposure is a latency lever the resolver can pull.

---

## 8. Air-gapped operation (D17)

Every component of the SLO/observability pipeline, audited for network dependencies.

| Component | Network dependency found | Air-gapped resolution |
|---|---|---|
| Model catalogue | LiteLLM fetches from raw.githubusercontent by default (`litellm/__init__.py:404`, `get_model_cost_map.py`) | PACT catalogue is **local-first by default**; remote feeds are opt-in providers. Adopt LiteLLM's integrity checks (min count, max shrink ratio) for the import path. |
| Image token counting | HTTP GET of image URLs (`token_counter.py:206-218`) | **Forbid.** Require intrinsic `width`/`height`/`detail` in the IR at ingest (§7.2.3). |
| Benchmark scores | External leaderboards | Already handled by AC-3.3 (provenance-required, `strict` mode refuses unprovenanced figures) |
| SLO figures | No external source exists anyway (§1.4) | Local measurement is the only option — which conveniently makes this constraint free |
| Trace export | OTLP to a collector | Collector must be optional; the **file-backed JSONL trace under `.pact/` is the source of truth**, OTLP is a projection. Mirrors Bud's "Rust emits the canonical event/trace stream" posture (`sdk-and-declarative-dev.md:134`) |
| Percentile computation | Langfuse/ClickHouse, Phoenix/Postgres | **Computed in-process from retained samples** (§3.1.2). No database required for a CI gate. |
| Judge models for evals | Hosted LLM | Already a D17 requirement; the SLO path needs no judge at all — SLO metrics are deterministic, which is why they should run *before* judges (AC-4.5 ordering) |
| Calibration probe (§4.3) | Model endpoint | Local model. This is the reason the probe is viable air-gapped. |

**Net position: the SLO subsystem is the *most* air-gap-friendly part of PACT**, because every
quantity is measured locally and no external oracle exists. The only genuine blocker found is the
image-dimension fetch, and the fix is a schema requirement rather than a workaround.

---

## 9. No-code surface (D13/D14)  **[PROPOSAL]**

D14 requires a non-technical domain expert to author SLO limits in YAML alone. Under the
Expansion Rule (T5) this is `contract/slo.yaml`, or an inline `contract.slo:` key.

**Tier 1 — what a support lead writes:**

```yaml
# agents/refund-helper/contract/slo.yaml
slo:
  feel: interactive          # interactive | conversational | background | batch
  budget:
    cost_per_run: $0.05
    max_minutes: 2
```

`feel` expands from a profile (F-1: no hardcoded defaults) into full objectives:

| `feel` | expands to |
|---|---|
| `voice` | `agent.ttft p95 ≤ 700 ms`, `call.itl p99 ≤ 120 ms`, `voice.barge_in p95 ≤ 300 ms`, `censor_at 30 s` |
| `interactive` | `agent.ttft p95 ≤ 2 s`, `run.e2e p95 ≤ 20 s`, `censor_at 120 s` |
| `conversational` | `agent.ttft p95 ≤ 5 s`, `run.e2e p95 ≤ 60 s`, `censor_at 300 s` |
| `background` | `agent.ttfa p95 ≤ 30 s`, `run.e2e p95 ≤ 15 min`, `censor_at 30 min` |
| `batch` | no latency objective; `cost` and `timeout_rate` only |

These numbers are **profile values, not spec constants** (F-1), and must be justified per
deployment. Naming them `feel` rather than `tier` is deliberate: a domain expert knows how the
thing should feel; they do not know what 700 ms means.

**Tier 2 — full fidelity (D19's "expert upload" analogue):**

```yaml
slo:
  observer: agent
  clock: mono
  samples:
    source: eval_suite            # eval_suite | synthetic | production_traces
    repeats: 4
    min_n: 100
    warmup_drop: 0.1
    max_cost_micros: 2_000_000
  censor_at_ms: 120_000
  objectives:
    - metric: agent.ttft_ms
      percentile: p95
      max: 2000
    - metric: call.itl_ms
      percentile: p99
      max: 250
      population: per_model_call
    - metric: run.e2e_ms
      percentile: p95
      max: 20000
      clock: work                 # exclude rate-limit waits
    - metric: run.cost_micros
      statistic: mean
      max: 50000
    - metric: timeout_rate
      max: 0.02
    - metric: goodput_rate
      min: 0.95
  on_violation: fail              # fail | warn | recommend
```

**Error messages must satisfy O7.3** (file, line, rule, fix):

```
evals/suite.yaml:12  SLO_UNESTIMABLE
  objective `agent.ttft_ms p95` needs n_completed >= 100; the suite has 24 cases
  and repeats: 1, giving n = 24.
  Fix: set slo.samples.repeats: 5  (n = 120, est. cost $0.31)
    or: change percentile to p90    (needs n >= 50)
    or: add slo.samples.source: production_traces
```

```
pact.lock  SLO_UNMEASURED
  `qwen3-4b @ onprem/1xA100` has no SLO measurement in models/catalog.yaml.
  Verdict: UNKNOWN — refusing to bind (strict mode).
  Fix: run `pact slo probe qwen3-4b --profile onprem-a100`   (offline, ~4 min)
  RECOMMENDED: qwen3-14b — MEASURED at this operating point, ttft p95 = 310 ms
               (budget 2000 ms), cost 1.8x
```

The second message is D11's "fail, then recommend" applied to SLOs rather than to eval scores.

---

## 10. Divergence matrix — the same request, six ways

For one streaming chat call that begins with a tool call, the reported "TTFT" is:

| Source | Fires on | Value relative to first content token | Citation |
|---|---|---|---|
| vLLM client bench | first frame with `choices` (incl. role-only delta) | **smallest** | `lib/endpoint_request_func.py:403-408` |
| vLLM multi-turn bench | first chunk, then back-corrected for multi-token chunks | small, corrected | `benchmark_serving_multi_turn.py:499-505` |
| vLLM server metric | `first_token_ts − scheduled_ts` (excludes queue + network) | **smallest, different basis** | `vllm/v1/metrics/stats.py:466-468` |
| OTel `time_to_first_chunk` | first chunk, client-observed | = vLLM client | `metrics-deprecated.yaml:99-117` |
| AgentOps | first delta with `content` **or** `tool_calls` | skips role-only frame | `.../openai/stream_wrapper.py:109-125` |
| LiteLLM router | `(completion_start_time − start) / completion_tokens` | **not a latency at all** | `router_strategy/lowest_latency.py:104-109` |
| Langfuse | `completion_start_time − start_time`, NULL if SDK didn't set it | SDK-dependent | `features/query/dataModel.ts:558-565` |
| **PACT `agent.ttft`** | first `content` frame with `visible: true`, **after any tool calls** | **largest — and the only one a user would recognise** | this document §2.4 |

This table is the argument for §2.2: PACT must carry all of these as separately-named,
separately-observed quantities and must never let two of them be compared as if equal. The CTS
needs a test that asserts the mapping, because an adapter that silently reports the gateway's
number as `agent.ttft` would pass every functional test while making the SLO meaningless.

---

## 11. Open questions

1. **`feel` profile values.** The numbers in §9 are placeholders and must be set from real
   measurement plus product judgement. Voice `agent.ttft p95 ≤ 700 ms` in particular should be
   validated against the deployment's VAD `silence_duration_ms`, since the two are additive.
2. **Repeat cost vs statistical power.** §3.3 option 1 multiplies eval cost by the repeat factor.
   Is there an acceptable design where SLO samples come from a *cheaper* synthetic distribution
   than the quality evals, and if so how is the distribution declared no-code?
3. **Should `goodput_rate` be the primary SLO or a derived one?** vLLM makes it primary
   (`serve.py:622-645`). It composes badly with per-metric recommendation (D11) — "which
   dimension failed" needs the per-metric view. Proposal: assert on `goodput_rate`, report
   per-metric, but this needs a decision.
4. **`overhead_ms` measurement methodology.** D26/F-4 require a continuous harness-vs-native
   benchmark. The harness survey shows "native" is not a single thing (3.7× input-token spread
   across harnesses at fixed model). What is the named baseline?
5. **Remote-agent (A2A) attribution.** Should a PACT contract be allowed to assert an E2E SLO
   when part of the run is an opaque remote agent? Current proposal: yes for `e2e`, never for
   `ttft`/`tpot`. Needs confirmation against the intended A2A usage.
6. **Timing-plane retention default.** Content-free timing data is cheap and useful; is
   indefinite retention acceptable under the tenant policies PACT must respect, or does it need
   the same TTL as content?
7. **OTel gen_ai drift.** The conventions moved to a separate repo and are all
   `stability: development`. Mirroring them into `pact.dev/v1` risks divergence. Should the CTS
   include a conformance test against a pinned snapshot of the external repo, and if so how does
   that work air-gapped?
8. **Speculative decoding and TPOT SLOs.** SGLang re-expands ITL per token using `accept_length`
   (`benchmark/serving.py:1102-1110`), but that field is provider-specific and absent from OTel.
   Should PACT require it as a capability declaration, or null out `tpot` whenever the provider
   is known to speculate?
9. **`cost_per_success` as the real objective.** §2.10 lists it. Since the eval suite is already
   the oracle (T2), `Σcost / n_passing` is computable from the same stream and is arguably the
   metric the optimizer should minimise. Is it an SLO or an optimizer objective, or both?

---
---

# PART II — Second pass (2026-08-07)

**Why there is a Part II.** Part I was written on 2026-07-26 against the corpus alone, before the
prototype existed. Since then `spec/schema.yaml`, `crates/`, `adapters/python` and
`adapters/typescript` have shipped, and §§2–9 above were partly absorbed into
`20-ARCHITECTURE-DRAFT.md` and `25-ARCHITECTURE-DECISIONS.md` (AD-23, AD-100). Part II does three
things and nothing else:

* **§A — re-verifies** Part I's load-bearing citations against the source as it stands today, and
  **corrects four of them that are wrong**. Part I's line numbers for the Bud ledger are all stale.
* **§B — reports what the shipped PACT code actually does** about SLOs and traces. This is the new
  centre of gravity: the gap between Part I's proposal and the running system is larger and more
  specific than the gap between Part I and the corpus.
* **§C — adds evidence Part I did not have**, most of it new to the corpus survey: OTel's MCP
  metrics, the OTel gen_ai *metric dimension set*, Gemini's per-modality token accounting, Phoenix's
  price schema, inspect_ai's cost limit, and the OpenAI Realtime playback clock.

Marking is unchanged: **[VERIFIED]** = read in source this pass; **[CORRECTION]** = Part I is
wrong and this supersedes it; **[DERIVED]** = computed here, reproducible; **[NEGATIVE]** = an
absence that is itself a result; **[PROPOSAL]** = mine, not reported.

---

## A. Re-verification and corrections

### A.1 vLLM's reference definitions are not one definition — they differ **per endpoint**  [CORRECTION]

Part I §1.1 gives one row for `latency (E2EL)` and says it excludes the trailing `usage` frame,
citing `lib/endpoint_request_func.py:257` and `:424`. Read this pass, the two paths in that one file
disagree, and §2.3's "Divergence, stated" is therefore built on a false premise.

`research/repos/routing/vllm/vllm/benchmarks/lib/endpoint_request_func.py`:

| Endpoint | first-token trigger | `most_recent_timestamp = timestamp` sits | ⇒ E2EL includes the `usage` frame? |
|---|---|---|---|
| **completions** (`:205-257`) | `first_chunk_received` bool, set at `:233-236` | **inside** `if choices:` — `:242` | **No** |
| **chat** (`:395-424`) | `if ttft == 0.0` at `:406-408` | **outside**, at the `if chunk != "[DONE]"` level — `:420` | **Yes** |
| **audio transcription** (`:500-542`) | `if ttft == 0.0` at `:522-524` | outside, `:538` | **Yes** |
| **pooling / embeddings** (`:588-600`) | n/a | n/a — `output.ttft = output.latency = time.perf_counter() - st` at `:596` | degenerate |

Two further asymmetries in the same file:

* The chat path stamps `timestamp = time.perf_counter()` at `:400`, **before** `json.loads` at
  `:401`. The completions path stamps it at `:231`, **after** `json.loads` at `:221`. So reported
  ITL includes JSON-parse cost on one endpoint and excludes it on the other.
* The chat path's guard is `if ttft == 0.0`, not a boolean. A frame that genuinely arrives at
  `perf_counter()` delta `0.0` re-arms the branch. Cosmetic in practice; it is the completions
  path's `first_chunk_received` flag that is the correct pattern.

**What this changes.** Part I §2.3 justified PACT diverging from vLLM by *including* the usage
frame in `call.e2e_ms`. Against the chat endpoint — the only one an agent uses — PACT does not
diverge at all; it matches. The divergence note should be rewritten as: *PACT matches vLLM's
chat/audio paths and diverges from its completions path, and the CTS mapping table must name the
endpoint, not just the tool.* **The observer axis in §2.2 is insufficient: an observed latency needs
`(observer, endpoint, streaming?)`, because the reference implementation itself varies on all three.**

Everything else in Part I §1.1 re-verified unchanged: `serve.py:607-613` (TPOT population split
`tpots` vs `all_tpots`), `:622-645` (goodput over all declared SLOs), `:731-733` (throughput),
`:1365` (`VALID_NAMES = ["ttft","tpot","e2el"]`), `:742-746` (percentiles over `tpots`, the
`output_len > 1` population). **[VERIFIED]**

### A.2 SGLang's speculative-decoding correction is **backend-gated**  [VERIFIED, sharpened]

`research/repos/routing/sglang/python/sglang/benchmark/serving.py`:

```python
use_retokenized_itl = (
    accept_length is not None
    and accept_length > 0
    and backend in ("sglang-oai", "sglang-oai-chat")     # :1083-1086
)
...
adjusted_itl = itl / num_tokens                          # :1109
retokenized_itls.extend([adjusted_itl] * num_tokens)     # :1110
...
itls = retokenized_itls if use_retokenized_itl else itls # :1193
```

Part I §1.3 reported the correction; it did not report that it is **conditioned on the backend
string**. Benchmarking a speculative-decoding vLLM or lmdeploy server *through SGLang's harness*
silently skips the correction and reports ITL inflated by the accept length. `concurrency =
np.sum(e2e_latencies) / dur_s` re-verified at `:1236`; `total_input_text` / `total_input_vision`
at `:1098-1099`.

**Consequence for PACT (unchanged in direction, stronger in force):** a `per-word-under` SLO is
uninterpretable without knowing whether the serving stack speculates *and* whether the measuring
stack corrects for it. PACT must record `speculative_decoding: {enabled, accept_length}` as a
sample covariate and **null out TPOT when `enabled ∧ ¬corrected`**, rather than reporting a number.

### A.3 The catalogue numbers, recomputed  [DERIVED — supersedes Part I §1.4 and §7.1]

Recomputed this pass over
`research/repos/routing/litellm/litellm/model_prices_and_context_window_backup.json`:

| Quantity | Value |
|---|---|
| model entries | **2,979** |
| distinct keys | **145** (81 contain `cost`/`price`) |
| entries carrying any latency/TTFT/TPOT/throughput field | **0** — regex over all 145 keys returns empty **[NEGATIVE]** |
| entries with `rpm` / `tpm` | 56 / 56 |
| `supports_vision` / `supports_audio_input` / `supports_computer_use` | 886 / 105 / 166 |
| context-tier price keys (`*_above_<N>_tokens`) | **30 distinct** |

Price-ratio distributions (only entries carrying both keys, both non-zero):

| Ratio | n | min | median | max |
|---|---|---|---|---|
| `input_cost_per_audio_token / input_cost_per_token` | 116 | **0.56** (`gemini-2.5-pro-preview-tts`) | **3.33** | **66.67** (`gpt-4o-mini-audio-preview-2024-12-17`) |
| `output_cost_per_audio_token / output_cost_per_token` | 50 | 1.2 (`azure/gpt-4o-mini-tts`) | **8.0** | 33.33 |
| `cache_read_input_token_cost / input_cost_per_token` | 691 | 0.00833 (`deepseek-v4-pro`) | **0.10** | 1.0 |
| `cache_creation_input_token_cost / input_cost_per_token` | 212 | 0.5 | **1.25** | 1.25 |
| `output_cost_per_reasoning_token / output_cost_per_token` | **52** | **0.375** | **1.0** | **3.33** |

**[CORRECTION]** Part I §7.1 states the audio-input ratio range as "8×–66.7×". The true minimum is
**0.56×** — a TTS model where the audio side is cheaper than text. The *median* is 3.33×, not 8×.
The 8× figure is specific to the `gpt-realtime` family and should be quoted as such.

**[NEW]** The reasoning-token price row did not exist in Part I. 52 models price reasoning output
separately from ordinary output; the median is exactly 1.0 (reasoning billed at the output rate),
but the range 0.375×–3.33× means a cost model that folds reasoning into output is wrong by up to
3.3× on some models in the expensive direction.

Realtime family, read directly (all values USD/token):

| Model | `input_cost_per_token` | `input_cost_per_audio_token` | ratio | `output` | `output_audio` | ratio | `max_input_tokens` |
|---|---|---|---|---|---|---|---|
| `gpt-realtime`, `-1.5`, `-2`, `-2025-08-28` | 4e-6 | 3.2e-5 | **8×** | 1.6e-5 | 6.4e-5 | **4×** | **32,000** |
| `gpt-realtime-2.1` | 4e-6 | 3.2e-5 | 8× | 2.4e-5 | 6.4e-5 | 2.67× | 128,000 |
| `gpt-realtime-mini`, `-2.1-mini` | 6e-7 | 1e-5 | **16.7×** | 2.4e-6 | 2e-5 | 8.3× | 128,000 |
| `gpt-4o-realtime-preview` | 5e-6 | 4e-5 | 8× | 2e-5 | 8e-5 | 4× | 128,000 |
| `gpt-4o-mini-audio-preview-2024-12-17` | — | — | **66.67×** | — | — | 33.33× | — |

Note `gpt-realtime`'s `cache_creation_input_audio_token_cost` = 4e-7, i.e. **0.0125× the audio input
price** — audio cache creation is 80× *cheaper* than audio input, the opposite sign to text (1.25×).
`gpt-realtime-2.1` publishes create and read at the same 4e-7. Audio cache economics are not a
scaled copy of text cache economics and must not be modelled as one.

### A.4 Image tokens: the table holds, the air-gapped failure mode does not  [CORRECTION]

Re-derived by re-implementing `resize_image_high_res` (`token_counter.py:119-153`),
`calculate_tiles_needed` (`:157-166`) and `calculate_img_tokens` (`:285-302`) with the current
constants (`litellm/constants.py:301-304`: short 768, long 2000, tile 512×512; base 85):

| Source | Resized | Tiles | Tokens (`detail:"high"`) |
|---|---|---|---|
| 300×300 *(the fallback size)* | 300×300 | 1 | **255** |
| 512×512 | 512×512 | 1 | 255 |
| 768×768 / 1024×768 / 1024×1024 | ≤768×768 | 4 | 765 |
| 1280×800, 1456×816, 1512×982, **1920×1080, 2560×1440, 3840×2160**, 2560×1600 | short side → 768 | 6 | **1105** |

The 16:9 result (1105 tokens for every resolution from 1280×800 up) is confirmed. **[VERIFIED]**

**[CORRECTION]** Part I §7.2.3 says the air-gapped fallback yields "4 tiles → 765 tokens, a 44%
under-estimate". Both numbers are wrong, and the failure mode is worse than reported:

* `DEFAULT_IMAGE_WIDTH/HEIGHT = 300` (`constants.py:61-62`) → 1 tile → **255 tokens**. Against 1105
  that is a **77% under-estimate (4.33× under)**, not 44%.
* More importantly, the 300×300 fallback is at the **end of `get_image_dimensions`**
  (`token_counter.py:268`) and is only reached if the bytes were obtained and the magic-number
  sniff failed. On the URL path with no network: `_get_httpx_client()`/`safe_get` raises, the
  `except Exception: pass` at `:217-218` leaves `img_data = None`, and control falls to
  `_header, encoded = data.split(",", 1)` at `:220`. **Reproduced:** for
  `https://example.com/screenshot.png` this raises `ValueError: not enough values to unpack
  (expected 2, got 1)` — an **uncaught crash**, not a fallback. For a URL that happens to contain a
  comma it "succeeds" into `base64.b64decode` of a path fragment and then reaches the 300×300
  fallback and the 255-token answer.

So in an air-gapped deployment the reference cost estimator for `detail:"high"` URL images either
**crashes** or **under-reports by 4.33×, depending on whether the URL contains a comma**. That is a
sharper argument for Part I's rule than Part I made: **PACT must require intrinsic `width`/`height`
on every image part at ingest and must never derive image cost from a URL** — not because the
fallback is inaccurate but because it is *non-deterministic in the URL's punctuation*.

### A.5 The Bud run ledger — all Part I line numbers are stale  [CORRECTION + VERIFIED]

`/home/bud/ditto/gaia-ai-runtime/bud-agentic-runtime/src/lib.rs` has moved by ~370 lines.

| Struct | Part I said | Actually (this pass) | Substance |
|---|---|---|---|
| `BudRunPlan` | `:8253-8301` | **`:8629-8674`** | still **no** `startedAt` / `finishedAt` / `durationMs` **[NEGATIVE, holds]** |
| `RunLineage` | `:8357-8365` | **`:8731-8737`** | `{parent_run_id, root_run_id, node_id, relationship, depth}` — the multi-agent aggregation spine, holds |
| `RunEvent` | `:8463-8473` | **`:8838-8846`** | `{seq, kind, status?, message?, metadata}` — still **no timestamp** **[NEGATIVE, holds]** |
| `BudRunTraceItem` | `:8814-8830` | **`:9190`** | ordered by `seq` only, holds |

`src/policy_runtime.rs` re-verified: `BudGuardrailStage` `:76`; `AgentModelTokenBudget` `:738-745`;
`AgentBudgetPolicy` `:755-770` (seven dims, `deny_unknown_fields`); `BudRunBudgetUsage` `:786-`;
`BudRunBudgetState` `:849-` with `deadline_at_unix_ms` `:856`; `BudRunBudgetRecord` `:960-978` with
`exceeded_dimensions` `:975` and `recorded_at_unix_ms` `:976`.

**[NEW — the most useful thing in this file for PACT]** `budget_exceeded_dimensions`
(`policy_runtime.rs:1077-1135`) treats *unknown cost* as a violated dimension in its own right:

```rust
if state.provider_cost_unknown && state.policy.provider_cost_micros.is_some() {
    exceeded.push("provider_cost_unknown".to_string());          // :1100-1102
}
```

That is Part I §2.7.4's "a cost SLO MUST fail closed when any call's price is unknown", **already
implemented in the system PACT must be a superset of**. PACT's `cost-per-request-under` currently
has no equivalent (§B.9). Also worth copying: the wall-clock check is `now_unix_ms >= deadline`
(`:1093-1099`) — inclusive, evaluated against reserved-plus-projected usage, i.e. reserve-then-commit
(`:1082-1092`).

### A.6 OTel gen_ai — unchanged, and one thing Part I missed  [VERIFIED + NEW]

`research/repos/protocols/otel-semconv`, `git log -1` = `bfa549224a08931dca5ba8fdf7bdfa540b6c0ab2`
(*Fri Jul 24 2026*) — **the same snapshot Part I read**. `model/gen-ai/` still contains only
`deprecated/`, every group carrying `note: Moved to the OpenTelemetry GenAI semantic conventions
repository`, every attribute `stability: development`. Part I's conclusion (mirror the names into
`pact.dev/v1`, do not `$ref` an external spec) stands unrevised. **[VERIFIED]**

Two normative sentences worth quoting verbatim in the spec, both re-read this pass:

* `metrics-deprecated.yaml:109` and `:129` — for both
  `gen_ai.client.operation.time_to_first_chunk` and `gen_ai.client.operation.time_per_output_chunk`:
  > "This metrics SHOULD be reported for streaming calls and **SHOULD NOT be reported otherwise**."

  This is the standards answer to the LiteLLM degenerate-TTFT defect (Part I §1.4): a non-streaming
  call must emit **no** TTFT, not a TTFT equal to E2E. Part I §2.4.5 proposed
  `ttft_degenerate: true`; OTel's rule is stricter and better — *emit nothing*. Recommend PACT adopt
  the stricter rule and keep `ttft_degenerate` only as a diagnostic on the run record.

* `spans-deprecated.yaml:717-727` — the don't-double-report rule for `invoke_workflow`:
  > "This span SHOULD be reported by the instrumentations when they can reliably determine that
  > invocation is a workflow (i.e. groups several agent invocations) and SHOULD NOT be reported by
  > instrumentations that can't distinguish it `invoke_workflow` from `invoke_agent`. eg: Some
  > frameworks like ADK have workflow agents that orchestrate other agents and report `invoke_agent`
  > spans, so `invoke_workflow` SHOULD NOT be reported by such instrumentations."

  Under harness lowering (D12) PACT *always* knows statically whether a node is a team or an agent,
  so PACT can satisfy this rule where framework instrumentations structurally cannot. This is a
  concrete, standards-anchored argument for AD-100 (PACT emits its own spans).

**[NEW — the OTel gen_ai metric dimension set cannot express an agent SLO]**
`metrics-deprecated.yaml:2-25`, group `metric_attributes.gen_ai`, is the complete attribute set for
every gen_ai histogram:

```
server.address, server.port, gen_ai.response.model, gen_ai.request.model,
gen_ai.provider.name, gen_ai.operation.name        (+ error.type on the server variants)
```

There is **no** `gen_ai.agent.name`, no `gen_ai.workflow.name`, no `gen_ai.conversation.id` on the
metrics. Those attributes exist only on *spans*
(`registry-deprecated.yaml`, `gen_ai.agent.*`, `gen_ai.workflow.name`). **[NEGATIVE]**

Therefore: `gen_ai.client.operation.time_to_first_chunk` p95 answers *"how fast is this model"*, and
there is no conforming way to ask *"how fast is this agent"* — you would have to add a non-standard
dimension and accept the cardinality. Combined with A.6's `invoke_workflow` rule, this settles an
open question: **PACT's agent-level SLO metrics are necessarily PACT-native. The OTel mapping is
span-level only, and the metric layer is a projection PACT computes itself from retained samples**
(which is what AD-100 already decided, now with the reason stated in the standard's own terms).

### A.7 A2A, MCP, inspect_ai, Langfuse, AgentOps — re-verified  [VERIFIED]

* **A2A** — `specification/a2a.proto` grepped case-insensitively for
  `latency|slo|throughput|rate.limit|cost|deadline|timeout`: **zero hits**. `TaskStatus` `:211-219`
  = `{state, message, timestamp}`; `TaskStatusUpdateEvent` `:296-305`. Part I §1.10 holds without
  amendment: for a remote sub-agent the only portable timing signal is the sequence of ISO-8601
  `TaskStatus.timestamp` transitions, and `INPUT_REQUIRED`/`AUTH_REQUIRED` intervals must land in a
  blocked bucket.
* **Langfuse** — `packages/shared/src/features/query/dataModel.ts:559-560` computes
  `timeToFirstToken` as `date_diff('millisecond', start_time, completion_start_time)` and returns
  `NULL` when `completion_start_time` is null (comment at `:559`: *"Return NULL … to represent
  unknown TTFT"*) — i.e. Langfuse already implements OTel's don't-fabricate rule.
  `:517` computes an output-tokens-per-second metric over `completion_start_time → end_time`.
  `queryBuilder.ts:150-158` maps p50/p75/p90/p95/p99 to ClickHouse `quantile()` — approximate.
* **AgentOps** — the two-event pattern re-verified at
  `agentops/instrumentation/providers/openai/stream_wrapper.py:113-125`
  (`first_token_received` on a non-empty `delta.content`; `first_tool_call_token_received` on
  `delta.tool_calls`). **[NEW]** the clock is `time.time()` (`:8`, `:44`, `:249`, `:602`) — a
  **wall** clock, so a TTFT measured across an NTP step is wrong by the step. Every other
  implementation surveyed uses a monotonic clock. Part I §2.1's rule ("all latency arithmetic on
  `mono_ms`") now has a named counter-example to cite.
* **inspect_ai** — `_util/working.py`: `sample_working_time() = time.monotonic() - start_time -
  waiting_time` (`:31-34`); `sample_waiting_for` de-duplicates concurrent waits via
  `concurrent_wait_count` (`:56-94`) so only intervals where *at least one* task is blocked count.
  Re-verified verbatim.

### A.8 vLLM auto_tune — the "latency is a search result" claim, quoted  [VERIFIED]

`research/repos/routing/vllm/benchmarks/auto_tune/README.md`, Configuration table:

* `MAX_LATENCY_ALLOWED_MS` — *"The maximum allowed **P99 end-to-end latency** in milliseconds."*
* the search axes are `NUM_SEQS_LIST` × `NUM_BATCHED_TOKENS_LIST`, held at fixed `INPUT_LEN`,
  `OUTPUT_LEN`, `MAX_MODEL_LEN`, `TP`, `SYSTEM` (`TPU|GPU`) and `MIN_CACHE_HIT_PCT`.

So the *upstream project that defines TTFT* treats a P99 E2E budget as a **constraint on a
configuration search over seven variables**, not as a property of a model. Part I §4.1's position is
confirmed in the primary source's own words: a scalar `ttft_p95` in a model catalogue is not a
figure that can be right.

---

## B. What the shipped PACT prototype actually does — the implementation gap

This section is new. Everything here was read this pass in
`/home/bud/ditto/agent-inter-op/{spec,adapters,crates,models}`.

### B.1 The authored surface is `limits:` — a scalar-cap block with **one** percentile for everything

`spec/schema.yaml:1082-1196`, group `limits`, twelve fields:

| Field | Type | Tier | Meaning |
|---|---|---|---|
| `feel` | one-of `voice\|interactive\|conversational\|background\|batch` | core | supplies the two latency figures |
| `finishes-within` | duration | core | E2E promise **and** ceiling |
| `cost-per-request-under` | money | core | whole-tree spend cap |
| `first-reply-within` | duration | **expert** | "how long before the first words come back" |
| `per-word-under` | duration | **expert** | "how long between words once it has started" |
| `steps-at-most`, `tool-calls-at-most`, `runs-for-at-most`, `tokens-at-most` | integer/duration | core | hard ceilings |
| `when-it-runs-out` | one-of `stop-and-say-so\|ask-a-person\|answer-with-what-it-has` | core | required with any ceiling |
| `asks` | text → `questions` | core | which question, when `ask-a-person` |
| **`measured-at`** | one-of `p50,p90,p95,p99,mean,max` | **expert** | *"whether these are typical or worst-case numbers"* |

**[NEGATIVE — six things Part I argued are load-bearing are absent from the schema]**

1. **No `objectives:` list.** `20-ARCHITECTURE-DRAFT.md:1737-1742` shows an expert form with
   `- {metric: ttft, percentile: 90, at-most: 2s}` and a per-objective `clock:`. **No such field
   exists in `spec/schema.yaml`.** One `measured-at:` governs the whole block, so an author cannot
   say "p50 on cost, p99 on the gap between words" — which is exactly what a voice contract needs
   (Part I §7.1: ITL must be asserted at p99 while E2E at p90 is fine).
2. **No observer.** Nothing distinguishes `runtime` from `agent` from `gateway` (Part I §2.2).
3. **No population.** `per-word-under` cannot say whether it ranges per-run or per-model-call.
4. **No clock selector.** `runs-for-at-most`'s help says person-wait is excluded; `finishes-within`'s
   does not; there is no field that says which clock a figure is on (see §B.8).
5. **No censoring field and no `timeout_rate`/`goodput_rate`/`error_rate`** (Part I §2.9).
6. **No sample-size declaration** — no `samples:`, no `repeats:`, no `min-n:`, no `source:`.
   `25-ARCHITECTURE-DECISIONS.md` AD-23 says latency percentiles default to `source: probe`; there
   is no `source` field in the schema and no probe in the code (§B.5).

`measured-at` is `tier: expert`, and `20-ARCHITECTURE-DRAFT.md:1157-1158` already names the
consequence: *"the minimum-n gate, the disjoint-split check and the censoring test are silent on a
core-tier suite"*. Verified: a core-tier author writing only `feel:` and `finishes-within:` gets a
p95 gate they never chose (`slo.py:118` defaults `measured_at="p95"`) at whatever `n` their eval
suite happens to have.

### B.2 The percentile is computed one rank too low  [DERIVED — defect]

`adapters/python/src/pact_adapters/slo.py:162-163`:

```python
q = {"p50": 0.50, "p90": 0.90, "p95": 0.95, "p99": 0.99}.get(self.measured_at, 0.95)
value = ordered[max(0, int(len(ordered) * q) - 1)]
```

Nearest-rank is `ordered[ceil(q*n) - 1]`. The shipped expression is `ordered[floor(q*n) - 1]`,
which equals nearest-rank **only when `q*n` is an integer** and is otherwise exactly one rank lower.
Enumerated over `n ∈ {20,25,30,40,50,60,72,100,120,150,200,384,400,500,1000}` × `q ∈ {.5,.9,.95,.99}`:
**it differs in 20 of 60 pairs, and in every case the shipped index is lower.** Examples:

| n | `measured-at` | shipped index | nearest-rank index | shipped reports |
|---|---|---|---|---|
| 30 | p95 | 27 | 28 | the 28th of 30, i.e. ≈p93.3 |
| 72 | p95 | 67 | 68 | the 68th of 72, i.e. ≈p94.4 |
| 384 | p99 | 379 | 380 | the 380th of 384, i.e. ≈p98.9 |

The error is **always in the direction that makes an SLO pass**. For a gate whose entire purpose is
to refuse a number that reads like evidence, a systematically optimistic estimator is the wrong
sign. Fix is one character-class: `ordered[math.ceil(q * len(ordered)) - 1]`.

### B.3 The minimum sample size is a flat 20, independent of the percentile  [defect]

`slo.py:136` — `def assess(self, samples, metric, min_samples: int = 20)`. The only production
caller is `scoring.py:542` — `scored.latency = spec.slo.assess(latencies, "e2e")` — which passes
nothing. So p50, p90, p95, p99, `mean` and `max` all gate at **n ≥ 20**.

Recomputed here, the one-sided binomial floor (accept "true quantile ≤ T" at 95% confidence with
`k` observed violations; closed form for `k=0` is `n ≥ ln α / ln p`):

| quantile | k=0 | k=1 | k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|---|---|
| p50 | 5 | 8 | 11 | 13 | 16 | 18 |
| p75 | 11 | 18 | 23 | 29 | 34 | 40 |
| p90 | 29 | 46 | 61 | 76 | 89 | 103 |
| **p95** | **59** | 93 | 124 | 153 | 181 | 208 |
| **p99** | **299** | 473 | 628 | 773 | 913 | 1049 |
| p99.9 | 2 995 | 4 742 | 6 294 | 7 752 | 9 151 | 10 511 |

Two-sided 95% nonparametric rank CI for the quantile (recomputed; matches Part I §3.2 — independent
re-derivation, so both stand):

| n | p50 | p90 | p95 | p99 |
|---|---|---|---|---|
| 20 | [6,15] w9 | **not estimable** | **n/e** | **n/e** |
| 24 | [7,17] w10 | n/e | n/e | n/e |
| 30 | [10,21] w11 | n/e | n/e | n/e |
| 50 | [18,32] w14 | [40,49] w9 | n/e | n/e |
| **72** | [28,45] w17 | [60,70] w10 | [64,72] w8 | **n/e** |
| 100 | [40,60] w20 | [84,96] w12 | [90,99] w9 | n/e |
| 200 | [86,114] w28 | [171,188] w17 | [183,196] w13 | n/e |
| 384 | [172,211] w39 | [333,357] w24 | [356,373] w17 | [376,384] w8 |
| 1000 | [469,531] w62 | [880,918] w38 | [937,964] w27 | [983,996] w13 |

**Worked failure.** A 24-case suite with `measured-at: p99` and `finishes-within: 30s`:
`len(samples)=24 ≥ 20` so the gate passes; `q=0.99`; `int(24*0.99)-1 = 22`; `ordered[22]` is the
**23rd of 24**, i.e. the empirical p95.8. The string returned is
`PASS (p99=…s vs 30.00s)`. A p99 claim, printed under the author's own word, computed from a p96
estimate over a sample 12× too small for p99's `k=0` floor of 299.

This is **the same defect class the module documents having already fixed one level down**:
`slo.py:154-160` explains that `mean` and `max` used to fall through to `q=0.95` and be *"printed
under the author's own word"*, and calls it *"worse than no verdict"*. The fix was applied to the
statistic and not to the sample size, so the identical sentence is still true of `p99` at n=24.

**[PROPOSAL]** `min_samples` must be a function of `measured_at`, taking the values Part I §3.2
normatively fixed (p50 ≥ 20, p75 ≥ 30, p90 ≥ 50, p95 ≥ 100, p99 ≥ 400, p99.9 ≥ 3000) with
`mean`/`max` treated as: `mean` ≥ 20 with a reported CI; `max` never gated but always reported as
`max of n`, never as a quantile.

### B.4 Latency samples come from the eval suite, one per case, **run serially**

`adapters/python/src/pact_adapters/scoring.py:686-697`:

```python
for case in cases:
    began = time.monotonic()
    result = asyncio.run(run(spec, transport_for(), case.when, {}, ...))
    latencies.append(time.monotonic() - began)
```

Three properties follow, all of them load-bearing:

1. **`n` = number of eval cases.** AD-23 says the eval and latency sample streams are *"decoupled"*
   and that *"eval-case count never gates a percentile"*. In the shipped code they are the same
   stream and the eval-case count is the only thing that gates it. There is no probe.
2. **Concurrency is exactly 1.** Cases run in a `for` loop with `asyncio.run` per case. Every vLLM/
   SGLang result in §A says latency is a function of batch occupancy; a p95 measured at concurrency 1
   is the *best-case* operating point and systematically under-predicts production. Nothing in the
   sample record says so.
3. **The clock is `time.monotonic()`** — correct, and it brackets the whole run including tools and
   delegation, which is the right definition of an `agent`-observer E2E. Credit where due: this is
   Part I §2.1's rule, correctly implemented.

### B.5 Censored runs enter the latency vector as if they had completed  [defect — the §2.9 rule, violated in code]

`scoring.py:697` appends unconditionally. It does not read `result.halted`, which can be
`time-limit`, `cost-limit`, `step-limit`, `tool-call-limit` or `token-limit`
(`limits.py:299-332`, `Ceiling.halted`). A run stopped by `finishes-within: 30s` therefore
contributes a ~30 s sample indistinguishable from a run that genuinely took 30 s.

Because `finishes-within` doubles as the wall ceiling when no `runs-for-at-most` is written
(`limits.py:274-277`), **the very field the SLO asserts on is also the field that truncates its own
sample distribution.** The measured distribution is right-censored at the assertion threshold, and
the report contains no `censored_rate`, no `timeout_rate`, and no `completed | censored | failed`
split. Part I §2.9 rules 1–5 are all unimplemented.

Second, smaller defect on the same loop: on a transport exception the loop **`break`s**
(`scoring.py:698-704`), so a failure at case 7 of 24 yields a 6-sample latency vector. The suite
verdict correctly becomes `UNDECIDED`, but `scored.latency` was already computed from the truncated
vector at `:542` — before the partial-results check at `:544`. Order matters: the latency string is
built from a sample the surrounding code is about to declare unusable.

### B.6 Nothing measures TTFT or TPOT — and both ports say so  [VERIFIED — honest, and the honesty is the design]

`slo.py:20-26` (module docstring) and `slo.py:125-133`:

> *"Measuring a first token needs the transport to say when one arrived, and none of the seven does;
> measuring the gap between words needs a token stream, and the harness has whole answers."*

`Slo.unmetered()` returns exactly the fields the author *wrote* (`written`, built at `slo.py:119-122`
from `first-reply-within` and `per-word-under`), never the ones `feel:` supplied — so a `feel:
interactive` default does not generate noise. That is a genuinely good rule and should survive into
the spec text.

The TypeScript port goes further and reports the **whole** unread set:
`adapters/typescript/src/limits.ts:237-245` declares `LIMITS_FIELDS` (the seven keys it reads) and
`limitsNotRead()` returns the rest; `harness.ts:600-607` emits one `unenforced` line per key. The
comment there records that `feel`, `first-reply-within`, `per-word-under`, `measured-at` and `asks`
were *"dropped in silence"* until that list existed, and that §7.28 of the architecture accounted for
them under `slo.*` — *"a row that could never fire"* because `pact show` nests them under `limits:`.

**Net position for the assignment's Deliverable 1.** PACT today has a *definition* problem and a
*measurement* problem, and only the second is admitted. `first-reply-within`'s help text is
*"how long before the first words come back"* — which is Part I's `agent.ttft_ms` (keeps running
through tool calls) and **not** `call.ttfc_ms`. Nothing in the schema says so. When a transport
eventually reports first-token time, the obvious implementation (stamp the first model chunk) will
silently implement `agent.ttfa`/`call.ttfc` under the name of `agent.ttft`, and the SLO will be
satisfied by an agent that emitted a tool call and nothing a user can read. **The definition must be
written into the field's help text before the measurement exists, not after.**

### B.7 PACT's own event stream carries **no clock at all**  [NEGATIVE — the blocking observability finding]

`adapters/python/src/pact_adapters/events.py:128-134`:

```python
@dataclass
class Event:
    address: Address
    payload: dict[str, Any] = field(default_factory=dict)
    at: tuple[int, ...] = ()      # session/turn/step indices
```

No timestamp, no duration, no monotonic offset. Grepping the module for
`time|timestamp|monotonic|elapsed|duration` returns one comment hit and no code.

The only shipped observability *output* is `watch:` (`spec/schema.yaml:3591-3690`), and its record is
built at `watches.py:230-242`:

```python
record = {"happened": str(event.address), "at": list(event.at)}
for key in RECORDED:                       # RECORDED at :133-157
    if key in event.payload: record[key] = event.payload[key]
```

`RECORDED` is a six-name allow-list: `name, does, outcome, reason, member, tools`. So a watch line is
`{happened, at, …names}` — **and the schema's own help for `writes-to:` (`schema.yaml:3689`) says
"Each line says WHAT happened, WHEN, and where in the run it was."** The "WHEN" is the causal
position `at`, not a clock. A reader of that sentence will expect a timestamp and will not get one.

Consequences, stated plainly:

* **Not one latency number in this document's vocabulary is computable from PACT's trace.** Not
  TTFT, not TPOT, not step latency, not tool latency, not `overhead_ms`, not the parallelism factor.
  The only timing that exists anywhere is `Meter.seconds` (an aggregate, `limits.py:139-142`) and the
  per-case `time.monotonic()` bracket in `scoring.py`.
* Part I §5's "one stream serves SLO + evals + learning + governance" is **not implementable on the
  current stream**, and Part I §6's R1 (a timing sidecar keyed by `(run_id, seq)`) is still the
  correct minimal change — it just now applies to PACT's own `Event`, not only to Bud's `RunEvent`.
* The watch record is **content-free by construction** (`watches.py:37-48`: a watch *"cannot write
  down what an interceptor was written to hide"*, which is why authoring one needs no approval).
  That is precisely the property Part I §5.7 wanted for the timing plane: **timing is content-free,
  so adding a monotonic offset and a duration to the watch line does not change its permission
  class.** This is the cheapest correct fix available anywhere in this stream.

**[PROPOSAL]** Add exactly three keys to the watch line and one to `Event`:
`Event.mono_ms: float` (monotonic offset from run start), and on the record
`{"ms": <mono_ms>, "took": <duration_ms|null>, "blocked": <"approval"|"rate-limit"|"sandbox"|null>}`.
No content, no permission change, no new group in the schema, and every metric in §2.10 becomes
computable from a file an author already knows how to ask for.

### B.8 Three different working-clock definitions are now live at once  [design conflict]

| System | "the clock a deadline runs on" | Excludes |
|---|---|---|
| **Bud** `wall_clock_ms` (`policy_runtime.rs:1093-1099`) | pure wall: `now_unix_ms >= deadline_at_unix_ms` | **nothing** |
| **PACT** `Meter.seconds` (`limits.py:139-142`) | `carried + (now - started)`, where `carried` is restored across a **durable park** (`Meter.restored`, `:157-169`) | only time the run was *parked for a person* |
| **inspect_ai** `sample_working_time()` (`_util/working.py:31-34`) | `monotonic - start - waiting_time`, `waiting_time` accumulated over semaphore + rate-limit waits with concurrent-wait de-duplication (`:56-94`) | approvals **and** throttling **and** queueing |

`spec/schema.yaml:1148-1150` (`runs-for-at-most`) promises the middle one — *"Time spent waiting for
a person does not count against it — nobody should fail a deadline because the approver went to
lunch"* — and `finishes-within`'s help (`:1099-1102`) promises nothing about clocks while inheriting
the same enforcement path.

**Two consequences.**

1. **D3's superset claim is not field-for-field on this row.** `bud.dev/v1`'s
   `spec.policy.budget.wallClockMs` → PACT's `runs-for-at-most` is a *semantic change*: a run that
   Bud would kill at 300 s survives under PACT if 200 s of it was an approval wait. The mechanical
   converter must either emit `runs-for-at-most` **and** record the clock change in the migration
   report, or map to a new `wall-clock-at-most` field. Silently changing what a deadline means is
   the T7 failure, applied to the migration itself.
2. **A rate-limited run is charged for the throttling.** PACT excludes approval waits but not 429
   backoff or semaphore contention. Under D17 (air-gapped, self-served models) that is mostly
   harmless; under a hosted binding it means `finishes-within` fails for a reason the author cannot
   fix by changing the agent. inspect_ai's split is the right one and its de-duplication algorithm
   (`_end_sample_wait`, `:88-94`) is directly portable.

### B.9 Cost is modelled with two prices, and that is wrong by up to 67× for D16's modalities  [blocking]

`spec/schema.yaml`, group `model-cost`, has exactly two fields: `input-per-mtok` and
`output-per-mtok`. `resolve._cost` (`resolve.py:572-600`) reads one of the two, divides by 1000, and
`raw.split()[0]` discards the currency word (safe only because
`loader/currency-nothing-can-price` refuses a cap the price list cannot price — documented at
`slo.py:184-196`).

Against §A.3's measured ratios, a `cost-per-request-under` computed from those two numbers is wrong
by:

| Workload | Direction | Factor |
|---|---|---|
| Voice, audio input (`gpt-4o-mini-audio-preview`) | **under**-charges | **66.7×** |
| Voice, audio input (`gpt-realtime` family) | under-charges | **8×** |
| Voice, audio output (`gpt-realtime`) | under-charges | 4× |
| Any loop with a stable cached prefix | **over**-charges | up to **120×** (`cache_read/input` min 0.0083) |
| Any loop that mutates its system prompt per step | under-charges | 1.25× on the re-created prefix |
| Reasoning-heavy binding (worst of 52) | under-charges | 3.33× |
| Any run crossing a 128k/200k/272k/512k tier boundary | under-charges | per the 30 tier keys |
| Vision, per screenshot | under-charges | 1105 tokens/image that nothing counts |

The `cost-per-request-under` ceiling is the **single most important no-code control in the whole
system** (D14 names it; `teamwork:` divides it; `Limits.reached` enforces it; `against_the_catalogue`
reasons about it). It is currently sound only for a text-in/text-out, uncached, non-reasoning,
sub-128k binding. That is not the v1 scope D16 declares.

**[PROPOSAL — minimal, no-code-preserving]** Keep the two-field shape as the *author-facing* default
and add an optional `cost:` sub-block with the six keys that carry the measured mass — a distribution
concern, not an author concern, since `models/catalog.yaml` is distribution-supplied by design
(its own header says the author never writes it):

```yaml
cost:
  input-per-mtok:  4.00 USD
  output-per-mtok: 16.00 USD
  cached-input-per-mtok:   0.40 USD    # median 0.10× input
  cache-write-per-mtok:    5.00 USD    # median 1.25× input
  audio-input-per-mtok:   32.00 USD    # median 3.33×, up to 66.7×
  audio-output-per-mtok:  64.00 USD    # median 8×
  reasoning-output-per-mtok: 16.00 USD # median 1×, range 0.375–3.33×
```

with the rule that **a key the row does not publish makes that token bucket `unknown`, and an
`unknown` bucket that a run actually uses makes the whole run's cost a lower bound** — the fail-closed
posture Bud already implements as `provider_cost_unknown` (§A.5). Anything else silently prices a
voice agent as a text agent.

### B.10 The catalogue cannot bind two of D16's four modalities  [NEGATIVE — blocking for D16]

`models/catalog.yaml` ships **13 rows**. Counted this pass:

* rows declaring `capabilities.modality-in: [..., audio]` or `modality-out: [..., audio]`: **0**
* rows declaring `capabilities.computer-use: yes`: **0** (`grep -c computer-use` → 0)
* rows declaring `modality-in: [text, image]`: 7 (`qwen2.5-vl-7b-instruct`, `claude-opus-5`,
  `claude-sonnet-5`, `claude-haiku-4-5`, `gpt-5.4`, `gemini-3.5-flash`, `grok-4.5`)

The requirement side exists — `needs: {images, audio, computer-use}` (`schema.yaml`, group `needs`)
and `model-can: {computer-use, modality-in, modality-out}` (`:830-870`). The `model-can.computer-use`
field's own comment records why it was added: *"`needs: computer-use: yes` translated to a capability
token no catalogue row could ever publish… measured, 0 of 13 rows passed, the refusal appended no
fix, and `pact check` said nothing at all."* The field was added; **the data was not.**

So today: `needs: {audio: yes}` → no candidate model → refuse to bind, with no recommendation
(D11's second half has nothing to recommend). `feel: voice` → a 300 ms first-reply band
(`slo.py:302`) that nothing measures, on a catalogue with no audio model, for a cost model with no
audio price. **Voice is declarable end-to-end and executable nowhere**, and the same is true of
computer use minus the cost problem.

This is not an argument against D16; it is the concrete work item D16 implies: **three catalogue
rows** (one realtime/audio, one computer-use, one already-present vision row extended with image
pricing) plus §B.9's cost keys would make all four modalities bindable, and none of it requires a
schema change beyond `cost:`.

### B.11 `feel:` bands are constants in Python, not values in a profile  [F-1 violation]

`slo.py:301-307`:

```python
FEELS: dict[str, tuple[float, float]] = {
    "voice":          (0.3,  5.0),
    "interactive":    (1.0,  30.0),
    "conversational": (2.0,  60.0),
    "background":     (10.0, 600.0),
    "batch":          (60.0, 3600.0),
}
```

`find -name profiles` over the repo returns nothing — **there is no `profiles/` directory.**
`25-ARCHITECTURE-DECISIONS.md` AD-23 states `feel:` expands *"from a builtin profile document printed
in full"* and that `profiles/*.yaml` is *"optional and overriding"*. Neither the builtin document nor
the override layer exists. The docstring defends the location (*"a number in `spec/schema.yaml` would
read as something they had chosen"*) — which is a good argument against putting them in the schema
and **not** an argument for putting them in code. Invariant F-1 is explicit: *"Every default is a
value in a profile, overridable at workspace/agent/variant/run scope"*, tested by a *"zero-magic
audit: grep the core for literals"*. These ten literals fail that audit.

Substantively, `voice: (0.3, 5.0)` also disagrees with Part I §9's placeholder table (700 ms) by
2.3×, and neither number is sourced. Part I §7.1's decomposition is why: the user-perceived voice
budget is `vad_endpoint_ms + transport + agent.ttft + tts_first_audio + playout`, and only
`agent.ttft` is PACT's. A 300 ms `agent.ttft` band is defensible *only if* the deployment's
`silence_duration_ms` and playout buffer are separately declared; nothing declares them.

### B.12 Team budget: post-hoc charge, leaf-first failure  [design divergence, worth a decision]

`delegation.py:197-270` (`Pool`) and `harness.py:2885-2916` (`delegate_by_running`):

* the grant becomes the child's own ceiling, `min(own, allowance)` (`harness.py:2892-2899`) — good,
  a child's tighter limit is never raised;
* the pot is charged **after the child returns**: `grant.spend(out.spent)` at `harness.py:2905`;
* `OverBudget` is re-raised as `RuntimeError(str(over))` *"as this member's failure rather than
  allowed out of the join, so the author's `if-someone-fails:` decides what happens next"*
  (`harness.py:2905-2912`).

Compare the two systems that have solved this:

* **inspect_ai** `_CostLimit.check` (`util/_limit.py:1235-1240`) walks **root to leaf** with the
  reason stated in the source: *"This is so that if multiple limits are simultaneously exceeded, the
  outermost (closest to root) one raises the error, **preventing certain sub-agent architectures from
  ending up in an infinite loop**."*
* **Bud** reserves worst case then commits actuals (`budget_exceeded_dimensions` projects
  `usage + reserved + additional`, `policy_runtime.rs:1082-1092`).

PACT does neither. The exposure is bounded — a child stops at its own `min(own, allowance)` ceiling,
so overshoot is at most one step — but the *failure attribution* is leaf-first, which is exactly the
shape inspect_ai's comment warns about: a supervisor whose pot is exhausted is told *"member X
failed"*, and `if-someone-fails: ask-another` will ask another member, which will also fail. The
author sees N member failures and no statement that the **pot** is empty.

**[PROPOSAL]** When `Pool.allowance(member) == 0` for every remaining member, the failure raised must
name the *parent's* `cost-per-request-under`, not the member. One `if not pool.metered or
pool.spent_total >= pool.total` check before the join, and the diagnostic changes from
*"fraud-checker failed"* to *"the team has spent the 0.05 USD you allowed; nobody was asked."*

### B.13 One-character semantic difference in what "under" means

`limits.py:341-343` — `if at >= c.limit: return Reached(...)`. inspect_ai — `if self._cost >
self.limit`. Bud — `now_unix_ms >= deadline` for wall clock, `$actual > limit` for the counted
dimensions (`policy_runtime.rs:1105-1109`). So PACT stops a run whose spend has *reached*
`cost-per-request-under`, which is the reading the field name supports (`under`), while Bud's
counted dimensions and inspect_ai's cost limit both allow equality. Trivial in money, **not trivial
in `steps-at-most`**: `steps-at-most: 10` in PACT permits 9 completed steps and stops on reaching
the 10th; in Bud, `turns: 10` permits 10. The converter must not map these as equal integers.

---

## C. Evidence Part I did not have

### C.1 OTel has MCP metrics, and they give tool latency a client/server split  [NEW]

`research/repos/protocols/otel-semconv/model/mcp/deprecated/metrics-deprecated.yaml` (same
deprecation/moved note as gen_ai, `stability: development`):

| Instrument | Definition (verbatim) | Line |
|---|---|---|
| `mcp.client.operation.duration` | *"The duration of the MCP request or notification as observed on the sender from the time it was sent until the response or ack is received."* | `:46-69` |
| `mcp.server.operation.duration` | *"MCP request or notification duration as observed on the receiver from the time it was received until the result or ack is sent."* | `:71-86` |
| `mcp.client.session.duration` | duration of the MCP session, client-observed | `:88-110` |
| `mcp.server.session.duration` | ditto, server-observed | `:112-131` |

Session attributes include `mcp.protocol.version`, `jsonrpc.protocol.version`, `network.transport`
(with the normative note *"SHOULD be set to `pipe` if the transport is stdio"*), and `error.type`
*"if and only if the session ends with an error"* (`:14-44`). Operation attributes extend
`mcp.common.attributes` and add `server.address`/`server.port`; `mcp.method.name` is a closed enum of
~20 JSON-RPC methods (`registry-deprecated.yaml:13-...`) including `notifications_progress`.

**Why this matters.** Part I §1.10 established that MCP sets *no protocol bound* on tool latency and
that progress notifications are the only liveness signal. That is still true. What is new is that the
**observation-point discipline PACT wants for models is already standardised for tools**:
`client.duration − server.duration` is the transport+queue share of a tool call, and it is
attributable without instrumenting the tool. PACT's `step.tool.started`/`step.tool.completed` pair
should carry both, and `run.tool_ms` should decompose into `tool_exec_ms` (server) and
`tool_transport_ms` (client − server). For a stdio MCP server the difference is process-spawn and
pipe latency, which is the dominant term for short tools and is invisible today.

### C.2 Gemini reports a per-modality token vector on the wire — and the reference reader approximates it  [NEW]

`research/repos/routing/litellm/litellm/llms/vertex_ai/gemini/vertex_and_google_ai_studio_gemini.py:1780-1935`.

The wire format carries `promptTokensDetails[]`, `candidatesTokensDetails[]` and
`cacheTokensDetails[]`, each a list of `{modality, tokenCount}` over
`TEXT | IMAGE | AUDIO | VIDEO | DOCUMENT`, plus scalar `thoughtsTokenCount` and
`toolUsePromptTokenCount`. So for Gemini, Part I §2.7's token vector is **provider-reported**, not
computed. For OpenAI it must be computed (§A.4). For Anthropic, `gen_ai.usage.input_tokens` is itself
a derived sum (`spans-deprecated.yaml:690-701`).

Three specific behaviours worth carrying into the spec:

1. **`DOCUMENT` is folded into text** (`:1829`, `:1860`) — a PDF page's tokens are reported as text
   tokens. PACT's vector must either keep a `document` bucket or record that the provider collapsed
   it, because "how many tokens did the PDF cost" is a question a vision-agent author will ask.
2. **Implicit caching is attributed to text by assumption.** `:1896-1902`, comment verbatim:
   *"Implicit caching: only cachedContentTokenCount is provided (no cacheTokensDetails) — Subtract
   from text tokens since implicit caching is primarily for text content."* For a voice or vision
   agent under implicit caching, the cached tokens are subtracted from the **wrong modality**. The
   resulting cost error is bounded by the modality price ratio, i.e. up to 66.7× on the affected
   tokens. **PACT must mark such a vector `attribution: assumed` and refuse to use it as the basis of
   a cost SLO verdict in strict mode.**
3. **Cost is not a function of the token vector alone.** `:1927-1931`:
   `billable_tool_use_prompt_tokens = 0 if _response_has_search_grounding(...) else
   tool_use_prompt_tokens`. Whether a bucket is billable depends on **which built-in tool ran**.
   Part I §2.7's `CallCostRecord` needs a `billable: bool` per bucket, not only a `cost_known` flag
   per call.

### C.3 Phoenix's price schema is an independent implementation of Part I's `CallCostRecord`  [NEW — corroboration]

`research/repos/eval/phoenix/src/phoenix/db/models.py`:

* `SpanCost` (`:2738-2850`) — one row **per span**, i.e. per model call, with
  `{span_rowid, trace_rowid, span_start_time, model_id, total_cost, total_tokens, prompt_cost,
  prompt_tokens, completion_cost, completion_tokens}` and hybrid `*_cost_per_token` properties.
  `append_detail` (`:2838-2850`) accumulates cost and tokens from details rather than multiplying
  aggregates.
* `SpanCostDetail` (`:2852-2880`) — `{token_type, is_prompt, cost, tokens, cost_per_token}`, unique
  on `(span_cost_id, token_type, is_prompt)`. **This is Part I §2.7's per-call token vector, keyed by
  token type, with the price recorded alongside the quantity.**
* `GenerativeModel` (`:2454-2502`) — `{name, provider, start_time, name_pattern (regex),
  is_built_in, created_at, updated_at, deleted_at}` with unique partial indexes on
  `(name_pattern, provider, is_built_in) WHERE deleted_at IS NULL`. Price rows are **time-versioned**
  (`start_time`) and **soft-deleted**, and `SpanCost.model_id` is `ondelete=RESTRICT` — a price row
  cannot be removed while a cost references it.
* `TokenPrice` (`:2504-...`) — `{model_id, token_type, is_prompt, base_rate, customization}`.
* `ThresholdBasedTokenPriceCustomization`
  (`src/phoenix/db/types/token_price_customization.py:11-16`) — `{type: "threshold_based", key,
  threshold, new_rate}`, with a forward-compatible parser (`:18-29`) that round-trips unknown
  customization shapes rather than dropping them.

Three lessons, all directly actionable for D8:

* **Threshold-based pricing is the generic form of context tiering.** LiteLLM's 30 `*_above_N_tokens`
  keys are one instance. PACT's catalogue should carry `{key, threshold, new-rate}` triples rather
  than N named keys, which also makes it forward-compatible with the next breakpoint a vendor invents
  — an E-2 property.
* **Prices must be time-versioned and soft-deleted, not edited.** A run's cost must remain
  reproducible after a price change. `models/catalog.yaml` is a git file so history exists, but
  nothing in the run record pins which revision priced it. Part I §5.5's
  `catalog_entry_digest` on `CallCostRecord` is the fix and is not implemented.
* **Never multiply aggregates.** Phoenix accumulates per-detail and sums; the `*_per_token` values
  are *derived for display only*. Same rule as Part I §2.7.1, arrived at independently.

**Also new:** OpenInference now carries a full cost vocabulary — `llm.cost.{prompt, completion,
total}`, `llm.cost.prompt_details.{input, cache_write, cache_read, cache_input, audio}`,
`llm.cost.completion_details.{output, reasoning, audio}`
(`research/repos/eval/openinference/spec/semantic_conventions.md`). Part I §1.7's table says
OpenInference has "none (token counts only)" — **[CORRECTION]**. Two caveats for PACT: they are
**floats in USD** (Bud uses `u64` micro-dollars, exactly summable) and there is **no `cost_known`
flag**, so a zero and an unknown are indistinguishable. Grep of `spec/` for
`time_to_first|ttft|latency|first_token` still returns **nothing**: OpenInference remains
latency-free. **[NEGATIVE, holds]**

### C.4 inspect_ai has grown a **cost** limit, and its check order is a spec decision  [NEW]

`research/repos/eval/inspect_ai/src/inspect_ai/util/_limit.py:1190-1268` — `_CostLimit`, alongside
`_TokenLimit` (`:1009`), `_TurnLimit` (`:1106`), `_MessageLimit` (`:1272`), `_TimeLimit` (`:1346`)
and `_WorkingLimit`. Part I §1.8 listed five limits; there are now six, and the sixth is cost.

Two implementation details PACT should copy verbatim:

* `record()` walks **to the parent first** (`:1229-1232`), so a nested agent's spend is charged to
  every ancestor before itself.
* `check()` walks **root to leaf** (`:1235-1240`) for the stated reason quoted in §B.12.

And one to reject: `_check_self` raises on `self._cost > self.limit` (`:1256`), a strict inequality,
which is the opposite of PACT's `>=` (§B.13). Pick one and record it; do not let the two ports and the
converter each pick separately.

### C.5 Voice: the barge-in truncation point is computed from a **receive** clock, not a playout clock  [NEW — the sharpest voice finding]

`research/repos/frameworks/openai-agents-python/src/agents/realtime/`:

* Turn detection is fully configurable and every field is a latency term:
  `RealtimeTurnDetectionConfig` (`config.py:96-124`) =
  `{type: semantic_vad|server_vad, create_response, eagerness: auto|low|medium|high,
  interrupt_response, prefix_padding_ms, silence_duration_ms, threshold, idle_timeout_ms,
  model_version}`. Default is `{"type": "semantic_vad", "interrupt_response": True}`
  (`openai_realtime.py:174`).
* Audio arithmetic is fixed by format: PCM16 at **24 000 Hz × 2 bytes** = 48 000 B/s; G.711 at
  **8 000 Hz × 1 byte** = 8 000 B/s (`_util.py:6-8`, `calculate_audio_length_ms` `:10-20`).
  `DEFAULT_SAMPLE_RATE = 24000` on the cascaded voice path too (`voice/input.py:14`).
* `ModelAudioTracker.on_audio_delta` (`_default_tracker.py:32-40`) records
  `ModelAudioState(initial_received_time = time.monotonic(), audio_length_ms)` and accumulates
  `audio_length_ms` per `(item_id, content_index)`.
* **The playback position is then estimated as elapsed receive time**
  (`openai_realtime.py:885`):

  ```python
  elapsed_ms = (time.monotonic() - audio_state.initial_received_time) * 1000
  ```

  used only when no `_playback_tracker` was supplied by the application (`:878-880`).
* On `input_audio_buffer.speech_started` the SDK stops local playback and truncates the assistant's
  conversation item at `truncated_ms = max(int(round(effective_elapsed_ms)), 0)`
  (`:1147-1185`), preferring the server's `audio_end_ms` when it is positive (`:1160-1164`) and
  falling back to the receive-clock estimate otherwise. `_send_interrupt` does the same on an
  explicit interrupt (`:905-944`), skipping when `elapsed_ms <= 0` (`:920`, `:940-945`).

**Why this is an SLO finding and not a voice-plumbing detail.** The truncation point *is what the
model believes the user heard*. It is written into the conversation history and conditions every
subsequent turn. If the client holds a 200 ms jitter buffer and no `playback_tracker` is wired, the
model's transcript claims the user heard 200 ms of speech they never heard — a **correctness** error
produced by a **latency** mis-measurement. Every other metric in this document answers "was it fast
enough"; this one answers "is the timing model accurate enough for the transcript to be true".

Consequences for PACT:

1. **`playout` is a fifth observation point** in Part I §2.2, and unlike `user` it is *not* outside
   PACT's control — it is a seam the runtime either wires or does not. The IR must name who owns
   playout position (`voice.playback-tracked-by: client | estimated`), and when it is `estimated`,
   the run record must carry `transcript_truncation: estimated` so a downstream eval knows the
   history may be wrong. **This is the one place in the whole SLO stream where an unmeasured latency
   corrupts the eval oracle rather than merely the report.**
2. **`voice.barge_in_latency_ms` decomposes** into `vad_detect (server, governed by
   silence_duration_ms/threshold/eagerness) + downstream transport + local stop`, and only the third
   is PACT's. Assert on the third; declare the first two.
3. **`prefix_padding_ms` and `silence_duration_ms` are additive to any user-perceived first-reply
   budget** and are *configuration*, not measurement. A `feel: voice` band of 300 ms
   (`slo.py:302`) is meaningless without them: with `silence_duration_ms: 500` the user waits
   ≥ 800 ms no matter how fast the agent is. **The `feel: voice` expansion must fail closed unless
   the deployment declares its VAD endpointing, or must be documented as an `agent`-observer figure
   that explicitly excludes endpointing.**
4. **`max_input_tokens: 32000` on the `gpt-realtime` family** (§A.3) with audio consuming context at
   the audio-token rate makes conversation compaction a *voice SLO* concern: the compaction step is
   on the interactive path, and Part I's `step.compaction.started/completed` events already exist in
   PACT (`watches.py:167-168`) — they just carry no duration (§B.7).

### C.6 Computer use: the cost term nobody counts  [carried forward, now quantified against the shipped code]

Combining §A.4's re-derivation with §B.9 and §B.10:

* Every 16:9 screenshot at `detail:"high"` is **1105 input tokens**, invariant from 1280×800 through
  4K. Downscaling saves nothing; cropping to 4:3 (1024×768 → 765) saves **31%**; `detail:"low"` is
  85 tokens, a **13×** reduction.
* A 40-step computer-use task is therefore ≥ **44 200 image tokens**, and **O(steps²)** if prior
  screenshots stay in context.
* PACT counts **none** of them: `model-cost` has no image price (§B.9), no catalogue row declares
  `computer-use` (§B.10), and `tokens-at-most` is metered from what the transport reports rather than
  from what PACT can compute for an image it is about to send.
* `cua.step_latency_ms` is the right interactivity metric (a 6-minute task of 40 smooth 9-second
  steps is fine; the same total with one 200-second stall is not) and PACT cannot compute it,
  because `step.*` events have no clock (§B.7).
* Approval gates and sandbox boot are `blocked`, and PACT's `Meter` gets the approval half right
  (park time is excluded, `limits.py:139-142`) and the sandbox half wrong (cold-start is charged to
  the run and is invisible in the report).

The single highest-leverage IR field remains `keep-last-n-screenshots`, because it is the difference
between O(N) and O(N²) and is exactly the kind of thing a framework port loses silently — which is
what D15 ("translate or nothing") exists to prevent.

---

## D. Restating the five deliverables, as of this pass

**D1 — Definitions.** Part I §§2.3–2.6 stand, with two amendments: an observed latency is keyed by
`(observer, endpoint, streaming?)` not `observer` alone (§A.1), and a non-streaming call must emit
**no** TTFT rather than a flagged one (§A.6, OTel `SHOULD NOT be reported otherwise`). The
tool-call-first question is answered by the `ttfb / ttft / ttfa` triple and the frame taxonomy, and
the shipped `first-reply-within:` help text already commits to the `ttft` reading without saying so —
which must be fixed in the help text *before* a transport implements it (§B.6).

**D2 — Percentiles and sample size.** Part I §3 stands and was independently re-derived here (§B.3).
The shipped implementation violates it in three ways: one-rank-low estimator (§B.2), flat n≥20 gate
(§B.3), censored samples counted as completed (§B.5). All three are small, local fixes.

**D3 — Resolve-time estimation.** Part I §4 stands unrevised and is now confirmed in vLLM's own words
(§A.8). The shipped code takes the honest position and says so: `slo.against_the_catalogue`'s
docstring argues that a catalogue latency figure *"is not a property of a model: the same weights
answer in 200 ms on an H100 and 8 s on a laptop"* and refuses to publish one. That is right. What is
missing is the other half — the **calibration probe** (Part I §4.3, AD-23's `source: probe`) — which
would let a *measured* verdict exist at all. Today every latency objective resolves to `UNKNOWN` and
the only honest outcome is `unmetered`.

**D4 — The one-stream trace schema.** Part I §5's structure stands; §6's R1 (timing sidecar) is
unimplemented and now applies to PACT's own `Event` as well as Bud's `RunEvent` (§B.7). The
reconciliation with the Bud ledger needs one correction: the clock semantics of
`wallClockMs → runs-for-at-most` differ (§B.8), so the converter is not field-for-field. Three
additions to Part I §5.2's semantic plane: MCP client/server durations (§C.1), per-bucket `billable`
and `attribution: reported|computed|assumed` on the token vector (§C.2), and `catalog_entry_digest`
per call (§C.3).

**D5 — Modalities.** Voice gains a fifth observation point (`playout`) and a correctness-not-just-
speed argument for measuring it (§C.5). Vision's token table is confirmed and its air-gapped failure
mode is worse than reported (§A.4). Computer use is unchanged in analysis and now quantified against
a catalogue that cannot bind it (§B.10). All three share one root cause: **the cost model has two
prices and the trace has no clock.**

---

## E. Open questions added by this pass

1. **Does `measured-at:` stay one word for the whole block?** A voice contract needs p99 on the
   inter-word gap and p90 on E2E simultaneously. Either `measured-at` becomes per-field
   (`per-word-under: {at-most: 120ms, measured-at: p99}`) or the expert `objectives:` list from
   `20-ARCHITECTURE-DRAFT.md:1737` actually ships. Both cost no-code simplicity; doing neither means
   voice cannot be expressed.
2. **Where do the `feel:` numbers live?** F-1 says a profile; AD-23 says a builtin profile document;
   the code says a Python dict; no profile exists. This needs one decision and one file.
3. **Is the calibration probe in v1?** Without it, every latency objective is `UNKNOWN` and
   `feel:`/`first-reply-within:`/`per-word-under:` are decorative. With it, `pact` needs a
   run-N-times-and-measure mode that is not the eval suite.
4. **Does the timing sidecar go on `Event` or beside it?** Bud's argument for a sidecar (replay
   determinism, stable digests) applies to PACT's `Event` too — but PACT's `Event` has no digest and
   is not replayed, so a `mono_ms` field may simply be correct. Deciding this decides whether the
   watch line can carry time without a permission change (§B.7).
5. **Should `cost-per-request-under` refuse to bind against a row missing a price key the run will
   use?** Bud already does the equivalent (`provider_cost_unknown` as an exceeded dimension, §A.5).
   Doing it in PACT means a voice agent cannot run against a text-priced row — which is correct and
   will read as a regression.
6. **What is the `steps-at-most` off-by-one, normatively?** `>=` vs `>` differs by one whole step
   (§B.13), and the bud.dev/v1 converter has to pick.
7. **Does PACT assert an E2E SLO when part of the run is an opaque A2A agent?** Part I's proposal
   (yes for `e2e`, never for `ttft`/`tpot`) is unchanged and still unconfirmed; A2A still publishes
   nothing but `TaskStatus.timestamp` (§A.7).
8. **Is `playout` a declared capability or a measured one?** §C.5 turns a latency question into a
   transcript-correctness question, which may mean it belongs in `needs:`/`model-can:` rather than in
   `limits:`.
