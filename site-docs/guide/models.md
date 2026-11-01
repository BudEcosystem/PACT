# Choosing and pinning a model

## Two ways to say which model

An agent either **pins** a model or says **what a model has to reach**, and PACT
picks one that does. Both are lines in `agent.yaml`; neither is code.

```yaml title="agents/desk/agent.yaml — pinned"
model: gpt-5.5                    # one exact model; a list is a fallback chain
settings:
  thinking: none                  # see below: GPT-5.5 drops sampling while it reasons
  max-tokens: 2048                # the longest answer
  temperature: 0.2
  top-p: 0.9
  seed: 7
```

```yaml title="agents/desk/agent.yaml — chosen by what it must reach"
needs:
  because: a phone call cannot wait, and customers read the replies
  prefer: cheapest                # or fastest, or best-on-the-evals
  accept-when:
    - mmlu.score > 50             # a benchmark the catalogue records
    - refund-tone.score >= 0.8    # a check of your own suite, by its name
    - pass-rate >= 90%            # the whole suite, on this model
    - cost < 0.05 USD             # what one case cost on this model
    - context-window >= 128k
```

`max-tokens:` is the longest **answer**. How much a model can **read** is its
catalogue `context-window`, which `accept-when:` (or `needs.context-at-least:`)
holds it to.

## A setting the model would throw away is refused

Not every model takes every setting. In the code PACT runs on, OpenAI's models
are never sent `top-k`, GPT-5.x drops `temperature` and `top-p` while it reasons
(and GPT-5.5 reasons unless told not to), and Claude Opus 5 drops all three. Each
catalogue row records which settings its model ignores, so this is refused where
you wrote it:

```text
error: `desk` sets `temperature:`, and 'gpt-5.5' takes no notice of it while it is
thinking — which it does here, so the run would use the model's own temperature
and nothing would say so.
  fix: Write `thinking: none` under `settings:` to keep `temperature:` …
```

## How `accept-when:` lines are decided

One comparison per line, and every line has to hold — there is no `&&` to learn.
What a line may name is closed and each name has a unit:

| Name | Unit | Known |
|---|---|---|
| a benchmark — `mmlu`, `gsm8k`, `humaneval`, `terminal-bench`, `swe-bench-verified`, … | out of 100 (`81` and `81%` mean the same) | before anything runs |
| a metric of your suite, by its `name:` — any DeepEval metric, a G-Eval in your words | a share: `0.8` or `80%`; `.score` is the mean, `.pass-rate` the share of cases over its own bar | after the model runs your cases |
| `pass-rate`, `cost` | a share; money in USD | after |
| `input-price`, `output-price` (per million tokens), `context-window`, `first-words-within` | money, size, time | before |

A figure nobody recorded never holds: a model with no MMLU score is not accepted
by `mmlu.score > 50`, and the refusal says so. `cost > 0.05` is refused too —
write the currency, `cost < 0.05 USD`.

## Where benchmark figures come from

The model catalogue declares the benchmarks by name, with their aliases (`MMLU`
and `mmlu` are one score) and how each is measured: DeepEval runs eleven of them
(`runs: deepeval:MMLU`), and the rest — Terminal-Bench, SWE-bench Verified, GPQA,
MMMU — come from their own harness or a published table. Every figure a row
records carries where it came from.

In Bud Agent Flow, `budflow benchmark record` writes a figure with its source,
`budflow benchmark run` measures a DeepEval benchmark against a model you serve,
and `budflow choose-model --candidate URL#MODEL …` runs your suite on each
candidate and picks by `accept-when:` and `prefer:`.
