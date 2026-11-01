# 96 — Modalities, interfaces, templates, turns, and tool schemas from the server

**Date:** 2026-10-27. **Status:** Implemented in `spec/schema.yaml`, the loader and
the Python adapters; runtime gaps listed in §H. Reference tree:
`tests/trees/a-desk-that-listens-reads-and-chooses/`.

Five things were asked of PACT:

1. **Voice and the other modalities** — documents, embeddings, text, vision.
2. **Abstraction** — choose a model by evals, cost and other figures while still
   letting an author pin one; tools with **categories and descriptions**, so a
   templated agent can say "email" and get Gmail for one customer and Outlook for
   the next; the same for skills.
3. **Jinja templates** in instructions, prompts and turns.
4. **Turns** — system, developer, user, agent.
5. **MCP tool schemas loaded from the server**, rather than copied by hand into
   `tools/` and going stale when the server changes.

Each is answered against the rest of PACT, not beside it. The organising rule is
the one the format already runs on (README, "The idea"): a **contract** that
travels unchanged, and a **strategy** chosen per target. Every answer below puts
the new thing on one side of that line, and most of the design falls out of
where it goes.

---

## §0 What was already there, measured

| Ask | What the spec had | What was wrong with it |
|---|---|---|
| Modalities | `images`, `audio`, `file` answer shapes; `model-can.modality-in/out: [text, image, audio]`; `needs.images/audio`; `limits.feel: voice`; egress roles `stt`, `tts`, `embedder` | No `documents` or `video`. `model.kind` was `language` or `decision`, so an embedder, a transcriber or a speaker had no row. The egress roles `stt`, `tts` and `embedder` existed with **no line able to name the model that plays them**. Voice was deferred by X20 on the stated premise that "no local TTS and no local duplex model" exists; by 2026 both do. |
| Model abstraction | `model:` pin (and fallback list), `needs:` filter, `variants:`, the resolver's "cheapest that passes" (D11) | `needs.scores:` could **never** be satisfied: the resolver reads `benchmarks:` off catalogue rows and the schema refused the field. Measured: `'benchmarks' is not something a model can have`. One fixed ranking (cheapest) — wrong for voice. |
| Tool abstraction | `uses:` names one concrete tool; `based-on:` copies at load time | Nothing could say "any email tool". `based-on:` is a load-time copy, not a run-time choice. No category. |
| Templates | `{{run-inputs.x}}` / `{{remembers.x}}` holes in four fields, listed as a Rust const | No conditionals or loops. The const of field names meant the next templated field would load unchecked. |
| Turns | None | No few-shot conversations, no multi-turn eval cases (DeepEval's conversational case; D19 on-ramp 5). |
| MCP schemas | `actions:` as an allow-list **with hand-written `takes:`**; `tool-snapshot-digest:` pinned by hand; the runtime compares at connect time | `pinned:` was deleted in R43 because "nothing writes it"; the architecture said *"a snapshot returns when something writes one."* Nothing did. |

---

## §A Modalities

**A1 — Two answer shapes join: `documents` and `video`.** `file` stays the opaque
thing handed to a tool; `documents` is something a model *reads* (a PDF, a scanned
form). The difference matters to the resolver, which is the reason for a separate
shape rather than a convention.

**A2 — Model kinds are the model ABIs every framework already has.** `kind:
language | decision | embedding | transcription | speech | reranking`. Vercel AI
has language, embedding, transcription and speech model specs; LangChain has chat
and embeddings; Pydantic AI has a model and an embedder. A vision or "omni" model
is **not** a kind. It is a `language` model whose `modality-in:` says so, because
it is called the same way. A model that listens while it speaks is `language` with
`sessions: [duplex]`.

Which kind each model line takes is **data**: `model-kind:` beside `names:
pact:models`, read by `crates/pact-loader/src/modelkinds.rs`. `agent.model:
nomic-embed-text` is refused by kind, with the right kind's models offered. The
Python resolver never offers a non-language row as an agent's model.

**A3 — `model-can` grows what each kind needs.** `modality-in: [..., video,
document]`, `sessions: [turns, duplex]`, `languages:`, `voices:` (speech models)
and `dimensions:` (embedders).

**A4 — `model.benchmarks:` (the bug fix) and `model.speed.first-words-within:`.**
Both use per-figure provenance, the shape `reasoning:` and `context-window:`
already have.

**A5 — `needs.documents:` and `needs.video:`, only for what the contract doesn't
show.** An agent that `accepts: documents` needs a document-reading model, and the
resolver derives that from the line it already wrote. The `needs:` lines are for
documents that arrive another way, such as from a tool.

**A6 — Voice: the contract was already writable; the strategy is `voice:`.**
The contract stays where it was: `accepts: {message: audio}`, `answers-with:
{reply: audio}`, `limits.feel: voice`. The new `agent.voice:` block (expert tier)
is the strategy:

```yaml
voice:
  pipeline: transcribe-think-speak    # or one-speech-model, or pact-picks (default)
  talking: takes-turns                # or both-at-once (barge-in, duplex)
  hears-with: whisper-large-v3        # model-kind: transcription, egress role stt
  speaks-with: kokoro-82m             # model-kind: speech,        egress role tts
  speaks-as: af_heart                 # checked against that model's voices:
  languages: [en-GB]                  # checked against each model's languages:
  turn-ends-after: 700ms
  may-be-interrupted: yes
  keeps-the-audio: no                 # S-GOV: a recording is personal data
```

Each line is a fact that holds on every provider. The voice id is the one
provider-specific value, and it is checked against the speaking model's own
`voices:`. So a voice that exists on only one vendor is refused the day the agent
moves, not discovered on a phone call. X20's contract half (`session: turns |
duplex`) returns as `talking:` and `sessions:`. X20's wire protocol stays an
adapter's business, which is what X20 asked for.

**The sovereignty consequence, which the old egress rule got wrong.** A voice
desk usually wants the caller's voice to stay on its own machines while the
reasoning may run on a hosted model. With `hears-with:` and `speaks-with:` naming
local models, the recording stops at the transcriber, and the hosted language model
is sent only words. So `allow-egress: [llm]` is the whole grant needed.
`egress.rs::carried` used to demand `stt` for any hosted model behind any audio
input. It now credits a named transcriber and speaker. Without them, the old
demand stands. Both directions are tested.

**A7 — Embeddings belong to the documents, not the agent.** `knowledge.embedded-by:`
and `knowledge.reranked-by:`. The reason is not taste. Passages were turned into
numbers by one model when the documents were indexed, and a question embedded by a
different model is compared in a space it doesn't share. The answer that comes back
is confidently unrelated. So two agents reading the same documents must use the
same embedder, and the documents carry it.

A named local embedder also makes **air-gapped semantic search writable** for the
first time. `looked-up-by: meaning` under `allow-egress: []` was refused
unconditionally; it now loads when `embedded-by:` names a model served on the
machine.

**Rejected:** a separate `realtime` kind (it's a language model in a session), a
per-agent `embedder:` (breaks the index invariant above), an image-generation kind
(no use case in the asks; `modality-out: [image]` already covers a language model
that draws).

---

## §B Abstraction

### B1 — Interfaces: the contract/strategy split, applied to tools, skills and documents

A **category** and an **interface** are different things, and the design keeps both
because the request needs both:

- `tool.category: email` is a **label** for finding and grouping, which is what
  `pact discover` and a builder's connector catalogue browse by. It promises
  nothing about what tools in it accept: one CRM takes a deal id, another an
  opportunity number.
- An **interface** is a **contract**, and it is what makes Gmail and Outlook
  interchangeable:

```yaml
# tools/email.yaml — the contract, written once
category: email
interface: yes
chosen-by: run-inputs.mailbox          # or the-host (default): per person's connected account
actions:
  search-messages: {takes: {query: text}, reads-only: yes}
  send-message:
    takes: {to: text, subject: text, body: text}
    needs-a-person: yes
    inspects: [to]

# tools/gmail.yaml — one strategy
implements: email
connect: gmail-server
actions:
  search-messages: {calls: search_threads, passes: {q: query}}
  send-message:    {calls: send_email, passes: {recipient: to, html_body: body}}
```

An agent writes `uses: [email]`. A policy written against `email/send-message`, an
eval's `must-call-before: email/search-messages`, and the model's view of the tool
are all written against the **interface**, so they mean the same thing whichever
provider runs.

**The rule that makes it safe:** an implementation may say only *how* it reaches
its own server. That means `calls:`, `passes:`, `bind:`, `program:`,
`projects-with:`, `status-check:`, `undone-by:`, and `needs-a-person: yes`, which
only ever asks more of a person. Restating `takes:`, or saying a call needs no
person where the interface says it does, is refused
(`loader/an-implementation-restates-the-interface`). Otherwise the contract would
hold only for whichever provider happened not to restate it. After that check, the
loader writes the interface's contract into each implementation
(`interfaces::inherit`). Approvals, same-request keys and every runtime then read
Gmail as if it were written out longhand, the promise `derive.rs` already makes
for `based-on:`.

**Who picks.** `chosen-by: the-host` (the default) means the host picks for each
person from the accounts they connected. That's how every connected-account
platform works, and it's a closed set: only entries that `implements:` the
interface can ever be picked. `chosen-by: run-inputs.<name>` makes it a run input,
which must be a `one of` whose choices are all implementations, on every agent
that uses the interface. Pinning is still writing `uses: [gmail]`. Writing both
the interface and one of its implementations is warned about as the same
capability offered twice.

The same three fields — `interface:`, `implements:`, `chosen-by:` — exist on
**skills** (each shop's own refund procedure) and **knowledge** (each customer's
own document set, the most common multi-tenant need of all). An interface skill
has no body, and an interface document set has no documents.

**Rejected:** categories as the substitution mechanism, i.e. `uses: [category:
email]` meaning any email tool. Actions differ across providers, so a policy or an
eval can't be written against "any tool in a category", and the approval rule over
`send-message` would hold on none of them. Also rejected: `implemented-by:` on the
interface instead of `implements:` on the implementation. The open direction lets a
connector bundle add a provider without editing the interface. A bundle's `brings:`
still has to list `tools`, so what it may contribute stays reviewed.

### B2 — Models: pin, filter, rank

| What the author wants | Written as | Status |
|---|---|---|
| This exact model | `model: <id>` (or a fallback list) | existed |
| Any model that can do X | `needs:` | existed; `documents`/`video` added |
| Any model that scores ≥ N on a benchmark | `needs.scores:` | **now satisfiable** (A4) |
| Any model that passes *my* evals | `evals:` + `must-pass:` — the resolver's gate (D11) | existed |
| …and among those, the cheapest / fastest / best | `needs.prefer: cheapest \| fastest \| best-on-the-evals` | **new** |

`prefer:` ranks only models that already passed. The gate is `needs:` plus the
evals, and this is the order within it, so no preference can bind a model that
fails. `fastest` ranks by `speed.first-words-within`, with unmeasured rows last
(Y12). `best-on-the-evals` measures every qualifying row and offers the highest
score, a cheaper row winning a tie.

### B4 — Choosing a model by evals: benchmarks, your own checks, cost, as comparisons

**`needs.accept-when:`** is a list of comparisons, every one of which has to hold, for a model to be
used for an agent:

```yaml
needs:
  because: a phone call cannot wait, and the replies are read by customers
  prefer: cheapest
  accept-when:
    - mmlu.score > 50                # a named benchmark the catalogue records
    - terminal-bench.score >= 40     # another; measured by its own harness
    - refund-tone.score >= 0.8       # YOUR check: a DeepEval G-Eval in the suite, by its name
    - refund-tone.pass-rate >= 90%   # the share of cases it passed its own bar on
    - pass-rate >= 90%               # the whole suite, on this model
    - cost < 0.05 USD                # what a case actually cost on this model
    - input-price <= 3 USD           # per million tokens, from the catalogue
```

**One comparison per line, all of which must hold.** There is no `&&`, `||` or
parenthesis, which is the decision `needs.scores:` already records. What a line may
**name** is closed and checked (`accept.rs`), and each name has its own unit:

| Measure | Unit | Known |
|---|---|---|
| a **benchmark** the catalogue declares (`mmlu`, `gsm8k`, `humaneval`, `terminal-bench`, `swe-bench-verified`, … or your own), `.score` optional | its `scale:`: `percent` (out of 100; `81` and `81%` mean the same) or `fraction` | before anything runs |
| a **metric** of the suite by its `name:` (default: the part of `uri:` after the colon) — any DeepEval metric, a `deepeval:geval` judgement in plain words, a `pact:` score, a carried `program:` | a share: `0.8` or `80%`; `.score` is the mean, `.pass-rate` the share of cases over its own `threshold:` | after the candidate has run the suite |
| `pass-rate` | share | after |
| `cost` (mean per case, at the catalogue's price for that model) | money, in USD | after |
| `input-price`, `output-price` (per million tokens) | money | before |
| `context-window` | size | before |
| `first-words-within` | duration | before |

**Units are part of the check.** `cost > 0.050` is refused: an amount with no
currency could be any currency. Write `cost < 0.05 USD` (and probably `<`: an upper
bound is what a spend ceiling means). `pass-rate > 80` is refused because a share is
out of one. These come with a fix line, at the line the author wrote.

**Two moments, kept apart.** A catalogue figure is known before anything runs, so
`ModelEntry.satisfies` holds those lines, and so does every runtime that binds
through it. A model that fails one never runs a case. A suite figure is known only
after the candidate has run the suite, so it is held then
(`selection.held_after`). Passing `must-pass:` is necessary but not sufficient. A
figure nobody recorded (no MMLU score, an unpriced model, an unmetered run) never
holds, and the reason says which.

**Named benchmarks live in the catalogue.** Each has a key, its aliases (`MMLU`,
`MMLU (5-shot)`), its scale, and **how it is measured**:

- `deepeval:<Name>` for the benchmarks DeepEval ships: MMLU, GSM8K, HumanEval,
  HellaSwag, TruthfulQA, BIG-Bench Hard, DROP, ARC, Winogrande, IFEval, MathQA.
- `host:<name>` for one a separate harness runs: Terminal-Bench, SWE-bench Verified,
  GPQA Diamond, MMLU-Pro, MMMU, τ-bench.

A row's `benchmarks:` may record only names the catalogue declares, so a typo is
refused (`loader/a-score-for-no-benchmark`) rather than silently never matching.
Every figure carries `provenance:`.

**Where the runtime is: Bud Agent Flow.** PACT keeps the one copy of what a line
means (`pact_adapters.selection`), of what may be recorded and how
(`pact_adapters.benchmarks`), and of the per-case scores
(`CaseOutcome.scores`). Agent Flow (`../budFlow`) puts them to work:

- **At bind time**, `catalogue.refuse_unfit` calls `ModelEntry.satisfies`, so
  `budflow run` refuses a bound model whose catalogue figures miss a line. The
  model's kind and speed are now carried into that entry.
- **`budflow choose-model TREE --candidate URL#MODEL ...`** holds each candidate to
  the catalogue lines, runs the suite live on each one with the agent's `model:` set
  to the candidate, holds the measured lines, and picks the first accepted model in
  `prefer:` order (`choosing.py`).
- **`budflow benchmark record TREE --model M --benchmark terminal-bench --value 41.3
  --source "..."`** writes a figure measured elsewhere.
  **`budflow benchmark run TREE --benchmark mmlu --candidate URL#MODEL`** measures a
  DeepEval benchmark against a served model and records it (`benchmarking.py`).
  When the workspace has no row for the model yet, the recorder copies the
  distribution's row first. Workspace rows replace shipped rows whole, so a row
  holding only a figure would lose where the model is served and what it costs.

### B5 — Pinning a model and its sampling, held to what that model takes

Pinning was always writable, and still is:

```yaml
model: gpt-5.5                  # one exact model; a list is a fallback chain
settings:
  thinking: none                # GPT-5.5 reasons unless told not to — and drops sampling while it does
  max-tokens: 2048              # the longest answer
  temperature: 0.2
  top-p: 0.9
  seed: 7
  stop-sequences: ["\n\n\n"]
```

"Sequence length" is two different figures in PACT. `settings.max-tokens:` is the
longest **answer**. How much a model can **read** is its catalogue
`context-window`, which an agent requires with `needs.context-at-least: 128k` or
`accept-when: context-window >= 128k`.

**What changed is that a setting the model would throw away is refused.** The
`settings:` group claimed "every key here works on every provider". The Pydantic AI
code this repository pins says otherwise, and each drop surfaced only as a Python
`UserWarning`:

- OpenAI's chat models are never sent `top_k`.
- GPT-5.x drops `temperature`, `top_p` and the two penalties while it reasons, and
  GPT-5.5 reasons unless told not to.
- Claude Opus 5 and Sonnet 5 drop `temperature`, `top_p` and `top_k` whatever is
  written.

So `model: gpt-5.5` with `temperature: 0.2` loaded clean and ran at the model's own
temperature.

A catalogue row now says which `settings:` a model ignores
(`model-can.ignores`), which it ignores while thinking (`ignores-while-thinking`),
and whether it thinks unless told (`thinks-unless-told`). Each is read from the
vendored source and cited on the row. `settings.rs` refuses the inert line, with
the fix: `thinking: none` to keep sampling, or take the line out. It checks every
model a line can reach: each fallback, `model-for-checking:`, and the catalogue
default for an agent that pins none.

A row that records nothing is not judged. That's the local Qwen rows, Gemini and
Grok, until someone records them.

The same reading is `ModelEntry.ignored_settings` in PACT. In Bud Agent Flow,
`choose-model` refuses a candidate that would throw an agent's settings away, and
`catalogue.refuse_unfit` refuses such a binding at run time. That covers the two
places a model is bound without `pact check` seeing it.

---

## §C Templates

**`workspace.template-language: holes | jinja`.** `holes` stays the default and the
no-code path. There is one switch for the whole tree: two dialects in one workspace
would mean the same `{{ }}` checked two ways two folders apart.

Which texts are templates is now **data**: `template: yes` on a field. That covers
`agent.instructions`, `agent.description`, `variant.instructions`, `variant.says`
and `turn.says`. `holes.rs` finds them by walking the schema, so a templated field
added later is checked by existing. That's what the old const of two names could
not do.

**The dialect** (`crates/pact-loader/src/jinja.rs`, `holes._render_jinja`):

- `{% if %}`, `{% for %}`, `{% set %}`, `{% raw %}`, comparisons,
  `and`/`or`/`not`, and **only the filters and tests that Jinja2 3.1 and
  MiniJinja 2.21 both ship with one meaning**. One list, held equal in both ports
  by a test.
- **No** `include`, `import`, `extends`, `block`, `macro`, `call`, function calls
  or method calls. Each either pulls in text the review didn't read, or is where
  the two engines differ and where sandbox escapes start. The checker is built
  without MiniJinja's `macros` and `multi_template` features, so these don't even
  parse. They are named before parsing, so the author is told what the tag does.
- **Names are what the agent declares, with `_` for `-`**: `run_inputs.brand_voice`.
  This isn't style. `{{ run-inputs.brand }}` is subtraction in Jinja, so a
  workspace that switches to Jinja is told exactly that, with the fixed spelling.
  Two names that collide after the mapping are refused.
- **A picture is never put into words.** A run input that is `images`, `audio`,
  `documents`, `video` or `file` can't be printed; it is attached to a turn.
- **What is filled in is data.** It is rendered once, in `SandboxedEnvironment`
  with no globals and `StrictUndefined`, and never rendered again. A customer who
  types `{{ 7*7 }}` is quoted, not obeyed, which closes the server-side template
  injection hole every Jinja deployment has to close.

**Deliberately not templated:** `question.says` (the wording a human approver reads
is fixed wording the author wrote; the field's own help says so), `evals` `judged:`
(a grader's question must not vary per run), and skill bodies (`SKILL.md` is a
cross-tool standard that other readers don't render).

**Rejected:** full Jinja, per-agent switches, user-defined filters, and Handlebars
or Liquid as a second option. Each multiplies what both ports must agree on, which
is the portability claim itself.

---

## §D Turns

One `turn` group, used in three places: `agent.turns` (a conversation placed before
every live one: a worked example, a fixed opening), `variant.turns` (the few-shot
example a small model needs and a large one doesn't, which is exactly what
variants are for), and `case.turns` (multi-turn eval cases).

```yaml
turns:
  - from: developer
    says: Every caller has been told the call may be recorded.
  - from: user
    says: Did you get my email about the broken kettle?
    attaches: [run-inputs.receipt]
  - from: agent
    calls: email/search-messages
    with: {query: broken kettle}
  - from: tool
    answer: One message, sent yesterday, subject "Kettle arrived cracked".
  - from: agent
    says: Yes — I have it here.
```

**Five speakers, and these are the only ones**: `system`, `developer`, `user`,
`agent`, `tool`. They are what every provider's chat format can carry, under
different names. Lowering them is the adapter's job, not the author's:

| PACT | OpenAI | Anthropic | Gemini | Pydantic AI |
|---|---|---|---|---|
| `system` | `system` | top-level `system` | `system_instruction` | `SystemPromptPart` |
| `developer` | `developer` | appended to `system` | appended to `system_instruction` | `SystemPromptPart` |
| `user` | `user` | `user` | `user` | `UserPromptPart` |
| `agent` | `assistant` | `assistant` | `model` | `ModelResponse` |
| `agent` + `calls:` | `tool_calls` | `tool_use` | `functionCall` | `ToolCallPart` |
| `tool` | `tool` | `tool_result` (in `user`) | `functionResponse` | `ToolReturnPart` |

**Rules** (`crates/pact-loader/src/turns.rs`), each one something a provider
enforces or a model learns wrongly:

- `system` and `developer` come only before anyone speaks. Two of the three big
  formats can't place an instruction mid-conversation without moving it, and a
  moved instruction is a different conversation.
- Every `calls:` is answered by the very next turn, from `tool`. Anthropic rejects
  an unanswered call, and a model shown one learns that calls go unanswered.
- A call names an action the agent can use. An attachment names a media run input,
  or a case's own `with:` file.
- A case's last turn is the person's or a tool's. The agent's next reply is what
  `expect:` grades.
- `instructions:` remains the agent's standing words. A `system` turn is an
  addition, lowered after them, in the way `variant.says:` already is.

`agent` rather than `assistant`, because it's PACT's own word for the thing that
answers. Importers map `assistant` and `model` to it.

---

## §E MCP tool schemas: from the server, with the permissions kept here

**The question asked:** shouldn't PACT load tool schemas from MCP servers
dynamically instead of hard-coding them?

**The answer:** yes for the *schemas*, no for the *permissions*. They were one list,
and that was the defect. `actions:` held two things:

- **which actions this agent may call**, which is a decision and the reviewer's;
- **what each takes**, which is a fact the server already publishes.

The second moves. The first doesn't, because "the server added a money-moving tool
between two runs" is the failure the allow-list exists to stop (architecture §11.5,
R2), and an MCP server's tool annotations (`readOnlyHint`, `destructiveHint`) are
written by the server and can't be trusted to decide anything.

**`tool.schemas-from: this-file | the-snapshot | the-server`.**

| Mode | Where `takes:` comes from | What `pact check` can hold offline |
|---|---|---|
| `this-file` (default) | the hand-written `takes:` | if a snapshot exists: every authored argument against the server's, and every argument the server *requires* that nothing supplies |
| `the-snapshot` (recommended) | the server's own schema, as **recorded** by `pact-sync` | every `inspects:`, `same-request-key:`, `bind:` and `passes:` argument against what the server really takes |
| `the-server` | whatever the server says at each connect | nothing about arguments; the runtime holds governed arguments at connect |

**The snapshot is in the tree, not in `.pact/`.** It lives in `resource.published:`,
written by `pact-sync <server>` (`adapters/python/src/pact_adapters/syncing.py`),
for the reason Y17 moved the held-out ledger: `.pact/` is deletable and outside
every digest, and this is what a reviewer approved. A server that changes its tools
**shows up as a diff in a pull request**, which is the review the hand-copied
`takes:` was a poor substitute for. `pact-sync --from-file` records a captured
`tools/list` response (the air-gapped path, D17); `--url` asks a live server.
`pact check` never connects.

**When the server changes anyway: `resource.if-it-changes: stop-and-say-so |
ask-a-person | use-what-was-reviewed | use-the-new-one`.** One class of change
**no setting can wave through**: a change to an action that spends money or needs a
person, or to an argument an approval, a same-request key or a host-bound value
rests on. It always stops, or asks when `asks-when-it-changes:` names a question
(`mcp_bridge.when_it_changed`). A new tool is never offered because it appeared.

**`tool.unlisted-actions: refused | each-call-asks-a-person`** is the dynamic half,
safely. A tool can offer whatever the server adds, but every call to an unlisted
action stops for a person, who sees the action and its arguments. It requires
`schemas-from:` other than `this-file`, because nothing here says what such an
action takes.

**Why not just fetch at run time and drop `actions:`.** It was weighed and refused:
there would be no allow-list, no approval rule that can be type-checked, no
same-request key to hold, and a run that reviews nothing. That's the opaque-wrapper
shape D15 rules out, one level down.

---

## §F Critique — what was attacked, and what survived

The design was attacked from six directions. Each attack is either answered in the
design above or became a rule.

1. **"An implementation can quietly loosen the interface."** It would have, through
   `needs-a-person: no` or a restated `takes:`. It is now refused, and the only
   allowed direction is asking more. Tested in both directions.
2. **"`chosen-by: run-inputs.x` lets a caller pick an unreviewed provider."** Only
   an entry that `implements:` the interface can ever be picked. The run input must
   be a `one of` whose every choice is one, checked per agent.
3. **"Jinja is an expression language, and D13 forbids making a non-coder learn
   one."** It's opt-in, expert tier and workspace-wide, and `holes` stays the no-code
   default. The dialect is small enough that a check names every way out of it.
4. **"Jinja breaks portability: Python and Rust engines differ."** The allowed
   filters and tests are the intersection, held equal by a test that reads the Rust
   list from the Python suite. Calls, methods, includes and macros (where they
   differ) are refused. The TypeScript port has no renderer yet (§H) and must use
   the same list.
5. **"Template injection."** Values are rendered once, as data. There are no
   globals, the environment is sandboxed, and an undefined value is strict. A test
   types `{{ 7*7 }}` into a run input.
6. **"A `system` turn in the middle is portable."** It isn't, on Anthropic or
   Gemini, so it is refused, not silently moved.
7. **"A local transcriber in front of a hosted model is still sending the voice
   out."** It isn't, and the old egress rule was wrong about it. The other direction
   was attacked too: remove the transcriber, and the demand for `stt` returns.
8. **"An embedder named on the agent."** Refused by design (A7). Two agents with
   different embedders over one index would retrieve nonsense.
9. **"Dynamic MCP schemas let the server change what an approval looks at."** A
   governed change always stops, and new tools are never offered by appearing.
10. **"A help text promising a command that doesn't exist"** was caught by the
    repository's own `every_command_the_specification_promises_is_a_command_that_exists`.
    It is exactly how `pinned:` died in R43, so `pact-sync` was built rather than
    promised.
11. **"A field nobody reads."** `model-speed.tokens-per-second` was drafted and
    deleted, because nothing ranks on it. The `dimensions:` help originally promised
    a check nothing performs, and the promise was removed.

---

## §G Where it lives

| Part | Files |
|---|---|
| Schema | `spec/schema.yaml`: groups `voice`, `turn`, `model-speed`, `published`, `published-tool`; 59 fields; attributes `model-kind:`, `plays-role:`, `template:` |
| Schema reader | `crates/pact-schema/src/{lib,from_doc,elsewhere}.rs`, which self-checks that `model-kind:`/`plays-role:` sit only on model lines and name real kinds and roles |
| Loader checks | `crates/pact-loader/src/{modelkinds,voice,interfaces,turns,snapshots,jinja}.rs`; `holes.rs` (schema-driven); `reach.rs`, `unnamed.rs` (interfaces) |
| Boundary | `crates/pact-cli/src/egress.rs`: `plays-role:`, kind-aware fix, and a named transcriber or speaker stops the recording |
| Python | `holes.py` (Jinja), `syncing.py` (`pact-sync`), `mcp_bridge.when_it_changed`, `voice.plan_for`, `resolve.py` (kinds, `prefer`, documents/video), `questions.py` (shapes), `ir.py` |
| Model choice (§B4) | `spec/accept-when.yaml` (one table, both ports); `crates/pact-loader/src/accept.rs`; `adapters/python/src/pact_adapters/{selection,benchmarks}.py`; `models/catalog.yaml` `benchmarks:`; Bud Agent Flow `src/budflow_core/{choosing,benchmarking}.py`, `catalogue._entry`, `grading.grade` |
| Tests | `crates/pact-cli/tests/a_desk_that_listens_reads_and_chooses.rs` (46 broken-once cases), `adapters/python/tests/test_an_accept_line_means_one_thing.py`, Bud Agent Flow `tests/unit/test_choosing.py`, `adapters/python/tests/test_a_desk_that_listens_reads_and_chooses.py`, plus the boundary suite extended to the four new model lines |

---

## §H What is pending

- **Turns reaching a model.** The document carries them and the loader checks them,
  but no transport passes them yet (Pydantic AI: `message_history`, per the table in
  §D).
- **`calls:` and `passes:` at run time.** `pact check` holds them against the
  snapshot, but the Pydantic AI bridge still filters the server's tools by action
  name, so an implementation whose server names differ won't run there yet.
- **Picking an implementation per run.** `chosen-by:` is checked and carried, but
  the reference harness doesn't yet swap the interface for the chosen implementation.
  When it does, the model should be offered the tool under the **interface's** name
  and wording. `tool.description:` is required, so every implementation carries its
  own, and offering that instead ("Gmail, through…") would leak the provider into
  what the model reads.
- **`unlisted-actions: each-call-asks-a-person`** is checked but not yet applied by
  the bridge.
- **The voice transport.** `voice.plan_for` makes the plan, including the
  `pact-picks` choice. Carrying it out (audio streams, turn detection, interruption)
  is a host's job, and no host in this repository does it.
- **The TypeScript port** has no Jinja renderer and no new shapes yet.
- **Shipped standard interfaces** (`pact:tools/email`, `pact:tools/calendar`, …), so
  connector bundles from different authors implement one contract. This is the
  `pact:loop/…` mechanism applied to tools.
- **`pact-sync --url`** is written against the MCP client SDK and untested here: this
  machine is offline and the SDK isn't installed. `--from-file` is tested.
- **`budflow benchmark run`** (a live DeepEval benchmark) is untested here: it downloads the
  benchmark's dataset and asks a served model, and this machine is offline. `record`, and
  `choose-model` on scripted models, are tested.
- **A metric is averaged over the cases it was scored on.** Grading stops at a case's first
  failure, so a metric isn't taken on a case that already failed. The report says how
  many cases each mean is over (`<name>.cases`); taking every named metric on every case
  would cost a judge call per case and is left as a choice to make.
- **Deriving `images` from `accepts:`** the way `documents`/`video` now are. Left as
  it was, to avoid changing existing resolutions in this change.
