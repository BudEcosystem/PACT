# 26 — Binding across models, machines and ways of working

*How one agent comes to run correctly on a 7B model on a CPU box and on a
frontier model on an H100, without the author writing a conditional.*

**Status: design, second draft. Nothing here is built.** The first draft proposed
a `machines/` kind and a `must-run-on:` field; both were killed on review and §5
records why, because the refusal is more useful than the proposal was. §11
separates what ships, what this repository designed and never built, and what is
new — most of the answer is the middle column, and a reader who mistakes it for
the first will believe PACT does things it does not. Every figure names the
command that produced it, measured **2026-08-07** against this tree.

---

## 0. The question

> *"Shouldn't it have an option to say `if model == x`, `model.size > 7B`,
> `if eval.score > 70 & eval.score < 90: model = y`, or
> `eval.row[1].result = true`? Also `recommended models = [x,y,z]`, and variants
> which are the entire instruction, tools etc."*

And behind it: instructions, tools, pipeline, sequence length and topology all
differ by model size, type and capability — **and by the hardware.** An Intel
Xeon 5th gen cannot prefill 10,000 tokens inside any reasonable SLO, so on that
box the same agent must become routing-plus-retrieval, or must not run.

---

## 1. The finding, in three layers

### Layer 1 — the conditionals are not the gap. The facts are.

`MMLU > 80` is already in the shipped spec, with a parser on both ports and a
comparison table pinned to nine decimal places (`spec/comparisons.yaml`):

```yaml
needs:
  scores:
    MMLU: "> 80"          # spec/schema.yaml:1001 — `type: map of threshold`
    SWE-Verified: "> 40"  # two lines, because the conjunction is the map
```

**It is not merely unpopulated. It is unsatisfiable by construction.** The
`model` group permits eight fields and `benchmarks:` is not one of them, so the
figure the predicate needs cannot legally be written. Reproduced against the
shipped binary:

```console
$ ./target/debug/pact check <tree with a benchmarks: block in models/catalog.yaml>
error: 'benchmarks' is not something a model can have.
  fix: Remove it, or use one of: description, family, tier, also-known-as,
       served-by, capabilities, reasoning, cost.
  rule: schema/unknown-field
```

Meanwhile `resolve.py:519` calls `_benchmarks(row.get("benchmarks"))` — a parser
for a field the checker refuses — and `satisfies` returns
`no published {metric} score` for every row (`:208`). So `MMLU: "> 80"` empties
the candidate set unconditionally, and **no author or importer can fix it.**
`_benchmarks`'s own docstring names the class: *"a predicate that empties the
candidate set whatever the data says is a trap, and it is the one Y12 was written
about."*

The same shape repeats. `reasoning:` has a four-rung ladder and **9 of 13 rows
are `unknown`**. `tier:` is on every row, read once at construction and gating
nothing, while `resolve.py:136` claims *"`tier` gates variant selection"* —
false, and defect **M-7** in §10.

The sharpest instance is a **core-tier** field whose own help states a condition
nothing can check. `settings.thinking: [none, low, medium, high]`
(`schema.yaml:1211`) is documented *"how hard to think before answering, **where
the model supports it**"* — and `grep -c thinking models/catalog.yaml` → **0**.
So `thinking: high` on a model without it is dropped at the transport: the
honest-and-inert failure this repository has already fixed three times (context
windows, spend caps, `computer-use`).

So `model.size > 7B` is unwritable not because PACT refuses comparisons — it
ships one — but because **no row publishes a size, and the row could not legally
carry one.** Adding an `if` on top of that buys nothing.

### Layer 2 — most of the rest was designed here, and never built

`docs/20-ARCHITECTURE-DRAFT.md` §2.4b already specifies the widened variant
*including the guard the question asks for*. Shipped versus designed:

```bash
$ python3 -c "import yaml;print(len(yaml.safe_load(open('spec/schema.yaml'))['groups']['variant']['fields']))"
5        # when, instructions, says, steps-at-most, may-use
```

against the ten the draft declares legal (`:1002–1006`) — `for`, `instructions`,
`uses`, `team`, `loop`, `context`, `sampling`, `settings`, `answers-with-mode`,
`optimiser-config` — plus a normative refusal list (`:998–1001`) making
`policy`, `limits`, `needs`, `evals`, `answers-with`, `accepts`, `run-inputs`,
`model` and `models` **validation errors inside a variant**. That refusal list is
the rule *a variant may change how, never what*, already normative. And `team`
being legal means **routing topology may already vary by model, by design.**

Also designed and unbuilt: `benchmarks:`, `capabilities.decoding:`,
`slo-measurements` keyed by operating point, `pact slo probe`, `pact explain`,
and `pact.lock` (`grep -rn 'pact.lock' crates/*/src/*.rs adapters/**/*.py` → 0).

### Layer 3 — one axis was never designed: the machine

```bash
$ grep -nE 'machine|gpu|accelerator|throughput|prefill' spec/schema.yaml
# 11 hits, every one prose inside a help: string or a # comment. No field.
```

The draft gets closest with `slo-measurements: [{operating-point: …}]` inside a
catalogue row (`:1583`), but nothing derives a ceiling from it and nothing
refuses a binding because of it. **This is the genuinely new work, and §5 is a
correction of how not to do it.**

---

## 2. What ships today

| The question | The line | Where |
|---|---|---|
| tool calling, in parallel | `needs.tool-calling: parallel` | `schema.yaml:953` |
| images / audio / a screen | `needs.images/audio/computer-use` | `:968–982` |
| must hold 32k | `needs.context-at-least: 32k` | `:983` |
| must think this hard | `needs.reasoning: careful` (UNKNOWN binds, ranks last) | `:945` |
| `MMLU > 80 && SWE > 40` | two lines under `needs.scores:` — **unsatisfiable, §1** | `:1001` |
| pin one model | `model:` | `:555` |
| check with a better model | `model-for-checking:` (needs a `loop:`) | `:571` |
| another way of working | `variants:` — ordered, tried after the authored agent | `:609` |
| nothing qualifies | fail-then-recommend, `_cheapest_passing` | `resolve.py:1526` |
| **answer from a corpus instead of a full document** | `knowledge:` — `documents`, `passages-at-most`, `must-cite`, `use-when`, all **core tier** | `schema.yaml` |

**Two corrections to how this is usually described**, both of which the first
draft of this document got wrong:

* `resolve()` takes **one** `requested: str` (`resolve.py:1271`). It walks that
  model's strategies and binds the first that passes (`:1416–1423`). The model
  axis is walked only in `_cheapest_passing` (`:1547`), which **recommends and
  binds nothing** — the verdict stays FAIL. So the shipped rule is *"try the
  requested model's variants; on failure, recommend"*, not *"bind the first
  passing pair"*.
* `must-stay-on-this-machine` is **derived, not authored**:
  `bool(_egress.missing_for(document, agent))` (`resolve.py:867`), which reads
  `allow-egress:` in `workspace.yaml`. The field an author writes is
  `allow-egress:`. Adding a second one is **R61** — *"two settings for what must
  never leave a workspace"* — refused by name in `docs/50-NOT-COPIED.md:489`.

**And the rule that matters most: nobody declares which variant a model needs —
it is measured.**

---

## 3. The rule that replaces `if`

> **The author declares what must be true. The resolver measures what is true.
> Where they differ it refuses, names the fact, and recommends the cheapest
> thing that passes.**

Each conditional in §0 is one of three things, and only the third is new:

1. **A requirement** — *"needs MMLU > 80"*. Already `needs.scores:`; §1 is why it
   does not work, and the fix is a catalogue field, not a conditional.
2. **A decision that must be measured** — *"if the eval scores 70–90, use model
   y"*. This is what the search already does, and freezing it as an `if` makes it
   worse: the author's guess about which model clears 90 is stale the day a new
   model lands. §7 gives the honest form.
3. **A guard on which ways of working are worth trying** — designed as `for:`,
   unbuilt. §7.

**No expression language.** Decision **Y4** deleted Tier-1 CEL from v1 and set
**H6** as the readmission trigger: *"re-admitted the day a fixture shows a
required predicate Tier 0 cannot express and no single atom covers"*
(`draft:1508`). **AD-16 states the budget: 8 catalogue atoms + 7 run-state
atoms, and the response to H6 is one new typed atom.** The first draft cashed one
H6 firing for seven atoms with no fixture; that was out of order, and §7 now
spends four against four named fixtures.

Two shapes carry the logic and neither is a syntax: **conjunction is the map**
(every line must hold) and **disjunction is the list** (alternatives are
variants, tried in order). There is no `&&` and no `||`.

**And the designed combinators are refused, which must be said rather than
glossed.** The predicate grammar this document builds on specifies
*"`all-of`, `any-of`, `none-of`. **Nestable.**"* (`draft:1369`). Nesting is
precedence, and precedence is the one thing AC-3.2 says a non-coder must never
have to learn — *"an expression language is a language, with precedence and
parentheses"*. `none-of` is worse than the other two: negation is where a guard
silently admits everything, and this design's own safety argument says a wrong
guard is never reported. So `for:` here is a **flat map with no combinators**:
`all-of` is the map itself, `any-of` is a second variant, and `none-of` has no
spelling. Taking the designed `for:` while dropping its grammar is a real
disagreement with the draft and is recorded as one.

---

## 4. Facts, and who publishes them

**(a) The catalogue — facts about a model.** Distribution-supplied, workspace
override at `models/catalog.yaml`. The `model` group grows by five; **every one
is `tier: expert`, matching all 27 catalogue fields today.**

```yaml
qwen2.5-7b-instruct:
  family: qwen2.5
  released: 2024-09-19                       # ← new
  parameters:                                # ← new — the missing `size`
    total:  { value: 7.6B, provenance: {...} }
    active: { value: 7.6B, provenance: {...} }   # MoE: active ≠ total
  served-by:
    - runtime: ollama
      endpoint: local
      quantisation: q4_k_m                   # ← new, and on THIS row, not the model:
      decoding: [json-mode]                  #   both are how a runtime serves the
    - runtime: vllm                          #   weights, not what the weights are
      endpoint: local
      quantisation: bf16
      decoding: [json-mode, json-schema, regex, cfg]
  capabilities:
    tool-calling: parallel
    thinking: none                           # ← new — `settings.thinking:` is CORE tier
    modality-in: [text]                      #   and binds against nothing today
    modality-out: [text]
    context-window:    { value: 32768, provenance: {...} }
    max-output-tokens: { value: 8192,  provenance: {...} }   # ← new
  reasoning: { value: steady, provenance: {...} }
  benchmarks:                                # designed (draft:1575), REFUSED by the
    MMLU: { value: 74.2, provenance: {...} } #   shipped checker today (§1)
  cost: { input-per-mtok: 0 USD, output-per-mtok: 0 USD }
```

`decoding:` and `quantisation:` sit **under `served-by:`**, not under
`capabilities:` where the draft put `decoding:`. The draft's own finding forces
it — *"`decoding` is a property of the substrate, not the model"* (`:1609`):
Outlines supports no constrained output at all for Anthropic, `json-mode`/
`json-schema` for OpenAI, full grammar only where the runtime has logit access.
Quantisation moves for the identical reason: it is a ~2× lever on decode rate and
one row must be able to describe q4-on-ollama *and* bf16-on-vllm.

`parameters:` and `released:` have a source to import — HELM's
`model_metadata.yaml` carries parameter count and release date, and no scores at
all (`:1600`), which is exactly why `benchmarks:` stays first-party work.

**(b) The author** — `needs:`, `limits:`, the contract, `prefers:`, `variants:`,
`knowledge:`. **(c) The run** — eval scores, per-case results, and the observed
token trace; never authored, always recorded.

---

## 5. The machine — and the design that was refused

**The first draft proposed a `machines/` concept, named operating points in the
tree, and `must-run-on: [xeon, h100]` in `workspace.yaml`. It is refused. The
reasons are worth more than the proposal.**

1. **AD-10 closes the kind list at eleven.** A `machines/` kind is a twelfth.
2. **C8 §3.4, horn one.** A `pact.lock` with per-machine rows must be *indexed at
   run time by something that knows which box this is*, and nothing in the tree
   can know that. *"Then two runs with the same digest are two different agents…
   that is not a trade-off, it is the failure."* The declaration being in-tree
   answers the *inside*-the-tree horn; the **selection** was still outside it.
3. **C8 §6 price 4, aimed exactly here:** *"a field whose meaning is supplied by
   whichever runtime reads it is a portability hole in a format whose one promise
   is that the same document means the same thing on every substrate. **The right
   place for that fact is the host's own records.**"* And **R20**: resolving a
   name only the host can know *"would make the portable artifact depend on one
   host's inventory."*
4. **C8 §3.5.** *"Profiles are a fleet idea: they pay off when one specification
   is deployed to many environments by people who cannot edit it. That is not
   this system's shape, and D17's air-gap makes it not this system's shape on
   purpose."* Under the air gap the Xeon and the H100 cannot share a probe run,
   so each tree would carry figures it never measured.
5. **C8 §3.1's real test is locality, not tree-residency:** *"the name of the
   layer is written next to the value it changes."* `must-run-on:` at the top of
   `workspace.yaml` fails it through a four-file chain.

### What replaces it

> **Hardware fitness is a report, not a contract. The tree never names a
> machine.**

The resolver **runs on the box it runs on**, and `resolve.evaluate` already
executes the agent over every case (`resolve.py`), through `harness.run`. So the
question *"can this box keep this promise?"* needs no declaration and no
selector: it is answered by running, on the box, the suite the author already
wrote. `pact check` on the Xeon refuses; `pact check` on the H100 passes; the
tree, and its digest, are identical and mean the same thing in both places.

That is not a portability hole — it is what a **`PortabilityReport` already is**,
extended from *which models* to *this machine*. The tree states its promises
(`limits:`); the environment either keeps them or is reported as unable to.

Measurements live in the **host's own records** — `measurements/*.yaml`, surface
`S-GEN`, written by `pact slo probe`, never authored, never part of the contract
and never digested into it. This is C8 price 4 followed rather than argued with,
and it is the draft's own position: *"Measurements are evidence, not policy"*
(`:1540`); *"Nobody in support knows their prefix-cache hit rate, and no design
may require them to"* (`:1552`).

**`pact slo probe` writes the whole row, including the machine's identity,
accelerator and concurrency — detected, not authored.** Otherwise the headline
capability has a mandatory expert-tier authoring step on a file the schema says
D13 never writes, which is C8 §3.5 verbatim.

**The honest price, stated as price 4 in §9:** until the probe has run, there is
no machine verdict at all. This design does not move the failure from run time to
bind time on an unprobed box; it moves it to **probe time**, and a tree authored
and reviewed before anyone probed the Xeon is refused later, by someone who is
not the author.

---

## 6. Measure, don't predict

The first draft derived `usable-input = prefill-tokens-per-second ×
first-reply-within`. **That is naive arithmetic and it fails optimistically —
the direction that admits a binding which then blows the SLO.** Five reasons,
each fatal on its own:

* **It models one request; the agent makes `steps-at-most` of them over a growing
  prompt.** Without prefix reuse, total prefill over N steps is
  `N·P₀ + Δ·N(N−1)/2`. For a 4k opening prompt, 800 tokens added per step, N=12:
  **100,800 tokens, not 4,000** — 107 s at 940 tok/s against a 30 s promise,
  while the formula reports a comfortable positive margin.
* **Prefill is not linear.** Attention adds a quadratic term; the error is always
  optimistic and **worse on smaller models** — precisely the CPU population this
  exists for. 12–32% inside the worked band, 2–3× at the top of a long window.
* **Decode slows with context** — every step reads the whole KV cache; ~−30% at
  32k on the worked example.
* **A rate is undefined without a protocol.** `940` per stream or aggregate
  across four concurrent requests differ by 4×, and three of four derived numbers
  flip on the reading.
* **A mean cannot back a promise the author reads as "always."**

### The correction — smaller than what it replaces, and zero new authored fields

**(a) The measured fact is a table of times at lengths, not a rate.** The probe
already runs; sweeping four lengths costs about two minutes, once.

```yaml
# measurements/shop-floor-xeon.yaml — host records. S-GEN. Written by `pact slo probe`.
driven-at-concurrency: 4        # closed-loop: four in flight at all times
statistic: p95                  # per request; not aggregate, not mean
prefill-seconds:   { 1024: 1.2, 4096: 5.0, 16384: 21.6, 32768: 47.9 }
decode-tokens-per-second: { 1024: 4.6, 16384: 4.0, 32768: 3.3 }   # ONE stream
prefix-reuse: opportunistic     # guaranteed | opportunistic | none — a runtime fact
```

Four points identify curvature with a margin, and **the top point is the model's
context window**, so the resolver interpolates piecewise-linearly and **never
extrapolates** — conservative between points by construction on a convex
function. Above the top point there is no answer, only the INTERPOLATED label.

A single operating point suffices *because `concurrency` is a closed-loop bound,
not an arrival rate*: with four permanently in flight, queue depth is bounded and
p95 is finite and reproducible. Production concurrency above the declared figure
is a run-time fact, and the door already exists — `RunResult.unmetered`.

**(b) Sum an observed trace instead of inverting a rate.** The resolver is
already running the agent, and the transport contract already exposes
`usage() -> (tokens, money)` per call, accumulated by `harness._meter_usage`. It
does not need to *predict* token counts — it needs to *record* them. One code
delta: split the single `tokens` counter into per-step
`(prompt_tokens, completion_tokens)` and keep the trace. Then:

```
predicted-first-reply = prefill(prompt_tokens[0]) + 1 / decode(prompt_tokens[0])
predicted-run         = Σ_k [ prefill(prompt_k) + completion_k / decode(prompt_k) ]
refuse if  predicted-first-reply > first-reply-within
       or  predicted-run         > finishes-within
       or  1 / decode(max prompt_k) > per-word-under
```

That last line is the cheapest and most decisive check and the first draft
ignored it: `per-word-under` (`schema.yaml:1118`) is a bare comparison against a
rate, and on the Xeon 4.5 tok/s = **222 ms/word** kills the binding at any
context length. It also catches what a prefill model cannot see — for a `careful`
model, thinking tokens emitted before the first visible word are **decode**:
1,000 of them at 4.5 tok/s is 222 s of TTFT.

**(c) Conservative by construction.** Derive assuming **no prefix reuse** unless
the row says `prefix-reuse: guaranteed`. Print both bounds; refuse on the
pessimistic one. The author is never asked about hit rate, so the D13 constraint
holds intact, and the gap becomes the most useful line in the report:

> `shop-floor-xeon` — this run is 18 s with prompt reuse and 107 s without.
> `ollama` reuse is opportunistic, so `finishes-within: 30s` cannot be promised.
> `retrieve-then-answer` predicts 24 s without reuse and binds.

**(d) `usable-input` survives only as a *report*** — the largest length in the
table whose prefill fits `first-reply-within`. A lookup, not an inversion, and
never the decision.

### And `feel:` may not decide this until it prints its numbers

The first draft said *"`feel:` acquires real teeth here"* and put its headline
figure at 9,400. **On the shipped worked example it is 940.**
`examples/refund-desk/.../limits.yaml` writes `feel: interactive`, whose
`first-reply-within` is 1.0 s from a Python dict (`slo.py`'s `FEELS`) — the
9,400 figure silently assumed 10 s, which is `feel: background`.

So a **core**-tier one-word field would decide a hard token ceiling through an
**expert**-tier duration the author never wrote, from a table no shipped command
prints, in a port where `feel` is dropped in silence
(`adapters/typescript/src/limits.ts` — `feel` and `first-reply-within` are both
outside `LIMITS_FIELDS`). That is C8's own **D-2**, still open, and F-1 —
*"no hardcoded default that caps capability"* — violated by a core field.

**Two consequences, both binding on this design.** C8 **D-2** (expand `feel:` in
the loader so both ports and `pact show` see the numbers) is a **prerequisite**,
not related work. And where a duration came from `feel:` rather than the author's
hand, the machine verdict is reported **provisional**, naming the implied
duration and the line to write — never an outright refusal.

---

## 7. Four fields

### (a) `for:` — the guard, with the comparator in the value

Already designed (`draft:1002`); this document asks for it to be built, and
**disagrees with one part of the design.**

```yaml
# agents/refund-desk/agent.yaml — the AGENT declares the authority; see §9 price 6.
uses: [policy-search, ticket-lookup, refund-issue]   # a variant may only narrow this

variants:
  retrieve-then-answer:
    when: the model cannot hold the whole policy at once   # prose, printed
    for:                                    # a flat map — no combinators (§3)
      reads:      "<= 16k"                  # ← the derived report-fact of §6(d)
      parameters: "<= 14B"                  # ← new catalogue fact
    says: Look the policy clause up before deciding. Quote it.
    loop: pact:loop/plan-then-do
    context: tight
    answers-with-mode: prompted             # decoding mode only, never the shape
    may-use: [policy-search, ticket-lookup] # SHIPPED spelling; a subset of `uses:`
    steps-at-most: 8
```

Every atom carries its comparator; `may-use:` is a strict subset of the agent's
`uses:`; no contract field appears. The first draft's example failed all three,
which is why the agent line is shown here rather than left implied.

**The disagreement: polarity spellings are refused in favour of `map of
threshold`.** The draft makes `reasoning-up-to: simple` normative — the same
token as `needs:` with inverted polarity, distinguished by a name suffix
(`:1378–1385`). PACT already faced this question one field over and answered it
the other way. `needs.scores:` refuses a bare `80`, and its comment says why:

> *"whether you meant at least 80 or at most 80 is the whole of what the line
> says — and on a latency or an error rate it is the other one."*

`reads:` is a latency-derived ceiling — the exact case that comment names. Three
further reasons:

* A load-time error catches `reasoning: careful` inside `for:`. It **cannot**
  catch `reasoning-up-to: deep` — correct spelling, inverted direction — which is
  a guard that admits everything and, by this design's own safety argument, is
  never reported.
* `-up-to` is a **third** ceiling convention: six shipped fields spell a ceiling
  `-at-most` and one spells a floor `-at-least`. Zero use `-up-to`.
* `map of threshold` is the shipped type, parsed by both ports, pinned by
  `spec/comparisons.yaml`, already refusing bare values. The author learns **one**
  rule — *always write the comparison* — covering `scores:`, `for:` and every
  future atom, instead of memorising which block inverts which token.

**Four new atoms, four fixtures** — the AD-16 budget spent deliberately, since
H6's trigger is *a fixture*, not an intention:

| Atom | The fixture that needs it |
|---|---|
| `parameters` | a 7B and a 70B need different step budgets; nothing today distinguishes them (`tier:` gates nothing) |
| `reads` | §5's Xeon: the same model on two boxes |
| `decoding` | native JSON on vLLM, prompted on Ollama — same weights |
| `thinking` | a core-tier setting that binds against nothing (§1) |

`quantisation`, `accelerator` and `family` are **withdrawn** from the first
draft's list. `family` in particular was the near-identity escape, and a guard on
an identity cannot fire for a model that does not exist yet — which is the one
thing this format sells. Bare model-name equality stays refused for the same
reason: if a variant exists because one model mangles JSON, record `decoding:`
on that row and guard on the fact.

**A guard filters which pairs are worth running the evals on. It never decides;
the evals decide.** A wrong guard costs a wasted candidate, never a wrong
binding.

**Two corrections the first draft got wrong and that block building §2.4b as
written.** `may-use:` is the shipped spelling and the draft's `uses:` would be
two names for one field (**R57**). And the draft's *"the legal variant fields are
**exactly**"* those ten omits `when`, `says` and `steps-at-most` — all three of
which the shipped flagship `examples/refund-desk` uses, so building the list as
written **stops the worked example loading**, and there is no deprecation channel
(`docs/93-GAPS.md` C7). The list must be the union, or the example migrated in the
same change. `sampling` is also **deleted** from it: `settings:` already carries
`temperature`, `top-p`, `top-k`, `seed`, `stop-sequences`, and two spellings for
one setting is **R21**, refused by name.

### (b) `prefers:` — the ordered candidate list

```yaml
prefers: [claude-haiku-4-5, qwen2.5-14b-instruct, qwen2.5-7b-instruct]
```

Distinct from the designed `models:`, a **role map** (`llm, stt, tts, embedder,
judge, reflector`, `draft:947`), and from `model: {exactly: <id>}`, which
disables substitution (AC-3.4). It closes the real gap named in §2: today the
model axis is walked **only by the recommender**, which binds nothing.
`prefers:` is what makes that loop a binder — the author's order first, then
cheapest-first for the fall-through, with models outer and variants inner as
`_cheapest_passing` already iterates (`:1547` outer, `:1572` inner). `model:`
remains the hard pin; the two are mutually exclusive.

### (c) `these-must-pass:` — named cases, not indices

```yaml
must-pass: 90%                                              # aggregate, as today
these-must-pass: [refund-outside-window, duplicate-charge]  # ← new, `names: ^cases`
prefer-above: 97%                                           # ← new — the band
```

`eval.row[1].result = true` becomes a **name**: an index breaks the moment
somebody inserts a case above it and silently starts asserting something else.
The loader already strips ordinal prefixes, so `evals/cases/02-outside-window.yaml`
is keyed `outside-window` and renumbering does not break the reference — and
declaring `names: ^cases` gets a typo caught at check time with a *did you mean*,
without which a renamed case silently drops the assertion the field exists to
guarantee.

### (d) `prefer-above:` — and it must be actionable or deleted

A binding at or above `must-pass` but below `prefer-above` binds and is reported
**provisional** while the search continues. That report *is* `if 70 < score < 90`,
produced by measurement rather than a frozen guess.

**But a provisional binding a support lead cannot act on is reporting noise.** So
two things are required, not optional: it must **name a model the author can type
into `prefers:`** — the shipped `Alternative{model, sentence, strategy}` already
carries exactly that — and **`pact check --deny-provisional` must exit 1.**
Without both, delete the field. An inverted band (`prefer-above` below
`must-pass`) is `schema/missing-companion`.

**`must-stay-on-this-machine:` is withdrawn entirely.** §2 shows it is derived
from `allow-egress:`; a second spelling is R61.

---

## 8. Tiers

The schema supplies the rule: `needs.scores:` is expert *"on purpose: … this can
only empty the candidate set until somebody records the figures."* Generalised —
**a field that can only narrow the candidate set until somebody records a fact is
expert.**

| Field | Tier | Why |
|---|---|---|
| `prefers:` | **core** | a list of ids beside `model:` (core); one line, no new concept |
| `these-must-pass:` | **core** | sits beside `must-pass:` (core), takes names the author already wrote |
| `prefer-above:` | **expert** | reporting-only until it names a model and gates an exit code |
| `for:` and its four atoms | **expert** | inside `variants:`, which is expert, as are all five of its fields |
| catalogue additions | **expert** | all 27 catalogue fields are expert today |
| `measurements/` | **expert**, `S-GEN` | never authored; written by the probe |
| derived facts | **not fields — but core vocabulary** | they appear in refusals every author reads |

That last row is the real cost. An author who opted into nothing must still be
able to read a refusal naming derived facts and catalogue fields. **So
`pact explain` is a prerequisite of the derived facts specifically**, not of the
design as a whole: a refusal printing `reads` without a command expanding it into
its inputs and their `file:line` is one D13 cannot act on.

---

## 9. What is refused, and the price

1. **No arithmetic, no `&&`/`||`/parentheses.** Y4 and AC-3.2 upheld. *Price:* a
   predicate needing arithmetic has no escape; H6 fires again for one more atom.
2. **No run-time branching on content.** `for:` is **bind-time only**. F1's
   refusal stands — and its real argument is *"a fourth place an author can write
   a condition"*, not merely content-routing. §7(a) answers it by making `for:`
   the **same** dialect as `needs.scores:` rather than a second one; had the
   polarity spellings been kept, this price would be unpaid.
3. **No machine named in the tree.** *Price:* the tree cannot state hardware
   requirements at all, and a fleet needs an out-of-band process to check each
   box. Accepted: C8 §3.5 says a fleet is not this system's shape.
4. **No verdict before the probe runs.** *Price:* the failure moves to probe
   time, not bind time, and lands on someone who is not the author.
5. **The refusal must not offer the most typeable fix.** Lowering
   `needs.context-at-least: 32k` → `9k` is one line, passes the check, and
   truncates at run time. FR-1.3.1's typeable-fix requirement produces the wrong
   answer here and must be written against. The remedies, in the order a support
   lead should be shown them: **relax `feel:`** (one closed-choice word, ~10×
   leverage — unmentioned in the first draft); **write `first-reply-within:`
   explicitly**; **add a `knowledge:` corpus and a retrieval variant** — a
   *shipped, core-tier, no-code* path the first draft never named; **accept the
   box is too slow.**
6. **A variant cannot introduce a tool.** The corpus goes on the agent's `uses:`
   and the variant narrows to it with `may-use:`. The first draft's own flagship
   example broke this and its own acceptance test.
7. **Unusable without provenance reporting.** `pact explain`, `pact slo probe`
   and `pact.lock` are designed and unbuilt; `pact` has five verbs. C8 **D-1**,
   **D-2** and **D-5** are prerequisites, D-2 most of all (§6).
8. **`needs.scores:` is a shipped trap until the catalogue can carry a figure.**
   It is not "load-bearing"; it is a load-time error away from being usable, and
   §1 measures it.

---

## 10. Acceptance

| # | Test | Mutation that must kill it |
|---|---|---|
| 1 | `a_score_bar_can_actually_bind` — `benchmarks:` loads, one row binds, another is refused **on the figure** | leave `benchmarks:` a `schema/unknown-field` |
| 2 | `a_guard_narrows_what_is_tried_and_never_decides` | let a guard select a variant without running the evals |
| 3 | `a_guard_atom_is_written_with_its_comparator` — a bare `reads: 16k` is refused as `scores:` refuses a bare `80` | admit polarity spellings and a bare value |
| 3b | `a_guard_has_no_combinators` — `any-of:`/`none-of:` inside `for:` are refused, and the fix names "write a second variant" | build the nestable grammar of `draft:1369` |
| 4 | `the_run_is_timed_over_every_step_not_the_first` | derive the run's time from one step's prefill |
| 5 | `prefill_time_comes_from_the_length_table_not_a_rate` | derive it from a single tokens-per-second figure |
| 6 | `a_throughput_figure_states_its_protocol` — per-stream, p95, at a declared closed-loop concurrency | read it as aggregate, or leave the statistic unstated |
| 7 | `a_verdict_that_rests_on_an_implied_duration_is_provisional` | let `feel:` refuse a binding silently |
| 8 | `feel_prints_the_numbers_it_stands_for_in_both_ports` (C8 **D-2**) | expand it in the Python adapter only |
| 9 | `per_word_under_refuses_before_any_context_arithmetic` | skip the cheap check |
| 10 | `a_variant_may_not_change_the_contract` — the nine fields of `draft:998–1001` | allow `limits:` in a variant |
| 11 | `a_variant_may_not_widen_authority` | let a variant introduce a tool |
| 12 | `the_shipped_worked_example_still_loads` — `when`, `says`, `steps-at-most` | build the "exactly ten" list as written |
| 13 | `a_guard_cannot_read_what_a_tool_returned` — F1 held | give guards a run-time evaluator |
| 14 | `a_named_case_that_fails_refuses_at_any_aggregate`, and a typo is caught by `names: ^cases` | make `these-must-pass:` advisory or unresolved |
| 15 | `a_provisional_binding_names_a_model_and_deny_provisional_exits_1` | report a band with no action attached |
| 16 | `a_refusal_does_not_offer_lowering_the_need_as_its_fix` | emit the most typeable fix-patch |
| 17 | `no_second_spelling_for_what_may_not_leave_the_box` (R61) | add `must-stay-on-this-machine:` as a field |
| 18 | `no_docstring_still_claims_tier_gates_variant_selection` (**M-7**) | leave `resolve.py:136` |

---

## 11. What was built here, and what was not

**Built: nothing.** This is a design document, and this is its second draft; §5,
§6 and §7(a) reverse first-draft proposals that did not survive review.

**Ships today:** `needs:` (with `scores:` unsatisfiable, §1); `variants:` with
five fields and *measured* selection; `ModelEntry.satisfies`/`ranks_after`;
`_cheapest_passing` as a **recommender that binds nothing**; the catalogue with
per-figure provenance; `knowledge:`, core tier, the no-code retrieval path;
`per-word-under`. Three defects sit in this same code, queued and unfixed —
**D10** (`agent_key` defaulted: with it 1 of 13 rows is admitted, without it 5),
**D11**, **D12** — so "load-bearing" is not the same as "sound".

**Designed here and never built:** the ten legal variant fields and the
nine-field contract refusal (§2.4b); `for:`; `benchmarks:`;
`capabilities.decoding:`; operating points; `pact slo probe`; `pact explain`;
`pact.lock`.

**New here:** `parameters:`, `released:`, `max-output-tokens:`,
`capabilities.thinking:`; `decoding:` **and** `quantisation:` under `served-by:`;
hardware fitness as a **report** with measurements in the host's records; the
length-keyed time table with a stated protocol; deriving from an **observed token
trace** rather than an inverted rate; no-prefix-reuse as the conservative
default; `per-word-under` as the first check; the comparator-in-value form of
`for:` against the draft's polarity spellings; `prefers:`; `these-must-pass:` and
an actionable `prefer-above:`.

**Withdrawn from the first draft:** the `machines/` kind; `must-run-on:`; named
operating points in the tree; per-machine `pact.lock` rows;
`must-stay-on-this-machine:` as a field; the atoms `quantisation`, `accelerator`
and `family` in `for:`; `usable-input` as a decision rather than a report.

**Two places this disagrees with `20-ARCHITECTURE-DRAFT.md` rather than
implementing it**, both in §7(a) and both recorded so a later reader does not
take them for oversights: the **polarity spellings** (`reasoning-up-to:`) are
replaced by `map of threshold` on the `needs.scores:` precedent, and the
**nestable `all-of`/`any-of`/`none-of` combinators** are dropped for a flat map.

**A reader must not believe** that a score bar binds today, that a variant can
change a loop today, that `pact` has an `explain` verb, or that any figure in §6
was measured on real hardware — they are illustrative, and the one number the
first draft did assert about the shipped example was wrong by 10×.
