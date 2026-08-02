# Experiments

## `real_model_portability.py`

Runs the worked example's eval suite against **real local models** (Ollama), so
the model-portability claim is measured rather than scripted. Everything is
local, so the air-gap requirement (D17) still holds.

```bash
cd adapters/python && uv run python experiments/real_model_portability.py
tail -f experiments/run.log
```

**This box is CPU-only**: a single model call takes 100–300s, so one
(model × strategy) row over six cases takes 10–30 minutes. The ladder is reduced
to `qwen2.5:7b-instruct` and `llama3.2:1b` for that reason. On a GPU host, widen
`LADDER` back out — `qwen2.5:14b-instruct` and `gpt-oss:20b` are both present.

### What it can and cannot show

It **can** show whether a smaller model meets the same contract, and whether a
different strategy rescues one that does not. That is thesis T4, and it is the
question the whole project exists to answer.

It **cannot** settle accuracy retention in general. Six cases on one task is an
existence proof, not a benchmark. The report says so in its own output rather
than leaving the reader to infer it.

### Already observed

`llama3.2:1b`, asked about a damaged lamp, replied *"you will receive a full
refund within the next 3-5 business days"* — violating the agent's explicit
instruction never to promise a date. The deterministic `pact:absent` check
catches it with no judge involved, which is a small but real demonstration that
the oracle works on genuine model output.

## Measured latency on this host — RETRACTED, see below

| Model | One call, realistic prompt |
|---|---|
| `llama3.2:1b` | **295 s** (includes load) |
| `qwen2.5:7b-instruct` | **100 s**; **255 s** p95 under the full agent prompt |

CPU-only aarch64, no GPU. A single (model × strategy) row over 3–6 cases is
15–25 minutes, and calls under the full instruction set hit a 900 s read timeout.
**The accuracy-retention matrix is not completable on this machine.** It is
parked, not abandoned: run it unchanged on a GPU host and widen `LADDER` back to
`qwen2.5:14b-instruct` and `gpt-oss:20b`, which are already pulled.

### ⚠ Retraction

The numbers above are **not valid measurements of these models.** The host was
running at a load average of **40 on 20 cores** — 2x oversubscribed by unrelated
work — for the whole period they were taken. They measure CPU contention, not
model latency.

An earlier version of this file used them to claim that "every local model misses
the 30s SLO by 3-8x" and that the SLO half of the contract was therefore
evidenced. **That claim is withdrawn.** Latency measured on a saturated box says
nothing about whether a model can meet an SLO, and presenting it as evidence was
wrong regardless of which direction the error pointed.

### Diagnosis (completed)

The blocker was isolated precisely, and it is environmental:

* The host carries a **sustained load average of 30-45 on 20 cores** from work
  unrelated to this project. Identified: `python3 harness.py llama3.2:1b
  qwen2.5:14b-instruct,llama3.2:1b,qwen2.5:7b-instruct`, a separate benchmark
  driving three models concurrently through the same Ollama server, running for
  1h40m+. Nothing this project does can get scheduled around it on a CPU-only
  box, which is why every mitigation failed identically.
* Under that contention a **1B model with `max_tokens=64`** — about as small a
  request as this task can make — still exceeds a **180 s** read timeout.
* Capping output did not help because generation was never the bottleneck;
  CPU scheduling was.

So the failure is not prompt size, model size, or the harness. Three separate
mitigations (fewer cases, smaller model first, capped generation) all failed for
the same underlying reason.

### What is nonetheless established

The transport, the eval runner and the harness all work against **real weights
over a real HTTP API** — that path is exercised and correct. What remains
unmeasured is whether a smaller model *retains accuracy*, which is thesis T4 and
the single most important open number in the project.

**To close it:** run this file unchanged on an uncontended host, ideally with a
GPU, and widen `LADDER` back to `qwen2.5:14b-instruct` and `gpt-oss:20b` (both
already pulled). Nothing in the code needs to change.
