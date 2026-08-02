# Draft designs for the pending fixes — INPUT TO ANALYSIS, NOT A PROPOSAL

**Status:** first-cut designs, written to be attacked. Every one is expected to
change. Numbering follows `93-GAPS.md`.

**Standing constraint for D1 (RAG):** a RAG-capable agentic runtime already
exists. PACT does **not** implement retrieval, embedding, indexing or chunking.
It *declares* what the runtime needs to know and *governs* the parts a reviewer
must be able to read. This is the `50-NOT-COPIED.md` §4 "declared and delegated"
pattern already used for ports, sandboxes, connectors and the durable store.

---

## D1 — `knowledge:` (gap A7)

### The authored surface, no-code tier

```yaml
# knowledge/hr-handbook.yaml
description: The HR handbook everyone asks about.
documents: handbook/**.md
looked-up-by: meaning
passages-at-most: 5
must-cite: yes
```

Five lines, all plain English. An agent names it exactly as it names a tool:

```yaml
# agents/helpdesk/agent.yaml
uses: [hr-handbook]
```

### Why it joins `uses:` rather than getting its own agent field

`agent.uses` is already `names: [tools, skills]`. Adding `knowledge` to that list
buys, at zero cost: per-stage narrowing via `may-use:`, the `available-when:`
mechanism, `loader/nothing-points-at-it` for an unreferenced entry, and the
reachability walk that `money.rs` uses to answer "which agents can reach this".
A separate `knowledge:` field on the agent would need all four re-implemented.

### Field table

| field | type | req | tier | surface | meaning |
|---|---|---|---|---|---|
| `description` | text | ✅ | core | S-GEN | what this is, one line |
| `documents` | text | — | core | S-CAP | where the files are — a path or glob inside the workspace |
| `connect` | text `names: resources` | — | core | S-CAP | a retrieval service the host runs, instead of files |
| `file-types` | list of one-of | — | expert | S-CAP | `text, markdown, pdf, word, slides, spreadsheet, html, code`. Absent = whatever the runtime handles |
| `looked-up-by` | one-of | — | core | S-CTRL | `meaning \| words \| meaning-and-words \| connections \| the-agent-decides` |
| `split-by` | one-of | — | expert | S-CTRL | `paragraph \| heading \| page \| whole-file \| the-runtime-decides` |
| `passages-at-most` | integer `at-least: 1` | — | core | **S-EXEC** | how many pieces come back |
| `must-cite` | yes-no | — | core | S-GOV | whether an answer has to say where it came from |
| `freshest-by` | text | — | expert | S-GOV | which field decides which version of a document wins |
| `available-when` | one-of | — | expert | S-ROUTE | same five values as tool/skill/resource |

### Naming rationale

- **`passages-at-most:`** not `at-most:` — `at-most:` already means two different
  things (`stage.at-most`, `drift.at-most`). Follows the shipped
  `<thing>-at-most` convention (`steps-at-most`, `tokens-at-most`,
  `tool-calls-at-most`, `runs-for-at-most`).
- **`looked-up-by:`** with plain-language values mapping 1:1 to the technical
  terms, named in a schema comment for the expert: `meaning` = dense/embedding,
  `words` = keyword/BM25, `meaning-and-words` = hybrid, `connections` = graph
  RAG, `the-agent-decides` = agentic RAG.
- **`connect:`** reuses `tool.connect`'s exact meaning and `names: resources`
  binding — deliberate reuse, not a second meaning.
- **`documents:`** rather than `from:` — `bundle.from` already means "where the
  folder of definitions is", which is close enough to confuse.

### What the loader must check

1. **Exactly one of `documents:` / `connect:`** — mirrors `reach.rs`'s
   exactly-one-of-three rule for a tool's transport.
2. `connect:` names a real resource (free via `names: resources`).
3. `documents:` resolves to at least one file at check time → otherwise
   `loader/knowledge-with-no-documents`.
4. **`must-cite: yes` requires the agent's `answers-with:` to carry a place to
   put the citation** → depends on gap A4 (`list of <shape>`).
5. A `knowledge` entry nothing names → existing `loader/nothing-points-at-it`.
6. Under `allow-egress: []`, a `connect:` to a non-local endpoint is refused →
   depends on fix B9.

### Known unresolved — for the analysis to settle

- **Trust.** Retrieved text enters the model's context and is the largest
  prompt-injection surface there is. PACT's answer is `trust:`/`sanitises:`,
  which have **0 field declarations**. Does `knowledge:` ship before B16?
- `passages-at-most:` is S-EXEC because attack success rises 6% → 20% → 38% as
  k goes 3 → 5 → 10 while injection *acceptance* stays high. Is a bare integer
  the right control, or does it need a ceiling?
- Is `split-by:` authorable at all by the D13 persona, or should it be
  expert-only with no default shown?

---

## D2 — Output constraints (gap A1)

### The problem restated precisely

The harness **already stops** on an output — `Decision.stop` is honoured at
`turn.message.after` (`harness.py:2848`) and `step.message.after` (`:1262`). What
is missing is that **no sentence form's condition reads the answer's content**.
Both stopping sentences are tool counters bound to `at: [step.tool.before]`.

### The fix: two new sentence forms

```yaml
# interceptors/must-answer-from-the-handbook.yaml
description: An answer that does not cite the handbook is not an answer.
when: turn.message.after
applies-to: every-agent
may: [stop-the-run]
rules:
  - if the answer does not name hr-handbook, stop and say "I can only answer from the handbook."
```

```yaml
# interceptors/no-medical-advice.yaml
description: This desk books appointments; it does not advise.
when: turn.message.after
may: [stop-the-run]
rules:
  - if the answer mentions "diagnos", stop and say "A nurse will call you back."
```

| form | needs | at |
|---|---|---|
| F6 `if the answer does not name <a knowledge>, stop and say "<why>"` | `stop-the-run` | `turn.message.after`, `step.message.after` |
| F7 `if the answer mentions "<text>", stop and say "<why>"` | `stop-the-run` | `turn.message.after`, `step.message.after` |

Both are **deterministic** — a substring test and a name test. Neither invokes a
model. That preserves the property that a suite decidable without a model never
invokes one, and keeps the closed-vocabulary refusal machinery intact.

### Known unresolved — for the analysis to settle

- **`must-not-contain` already exists as an eval rule.** Is F7 the
  `same-setting-twice` mistake, or is "grade a test case" genuinely a different
  act from "stop a live run"? If different, must the two vocabularies agree
  word-for-word?
- F6 depends on D1 shipping (`<a knowledge>` must resolve to something).
- Three of the six blocked personas are **not** output-shaped — Lena needs
  mutual exclusion (A5), Tom needs loop routing, the researcher needs a scored
  route. Does the claim "unblocks six personas" survive?

---

## D3 — Small schema additions

| # | Fix | Design |
|---|---|---|
| **A3** | approvals compare more than money | add `is:` (text) and `is-one-of:` (list of text) beside `more-than:` in `when-this`, each `needs-also: [arg]`. Decidable at check time: `arg:` is already resolved against `inspects:` |
| **A4** | `list of <shape>` | one entry in the `shapes:` anchor, spelled `list of text`, `list of money`… — the vocabulary already parses the compound `one of a, b, c` |
| **A5** | `same-request-key` scope | `at-most-once-across: this-run \| the-team \| the-workspace`, default `this-run`. `Ledger` already survives a park via `Suspension.spent_keys`; only the scope word changes |
| **A2** | `retrieval-context:` on a case | one field; `providers.evaluate_metric` already takes the parameter and its only caller never passes one |
| **A8** | durability declaration | `requires-of-the-runtime: {durable-resume: yes}` on the workspace — same polarity and refusal shape as `allow-egress:` |
| **A12** | unreadable answer shapes | add the missing `Shape.read` branches for `images`, `audio`, `file` |

---

## D4 — Safety fixes

| # | Fix | Design |
|---|---|---|
| **B1/B2/B4** | one `park()` helper filling the whole durable block; all five sites call it; a sixth site that forgets a field fails the suite |
| **B3** | `_ran_out` takes `chain` and routes its closing call through `turn.message.after` |
| **B8** | one validator arm: a mapping under a `type: text` field raises `schema/wrong-type` with the message that already exists for lists |
| **B9** | `resources.<r>.endpoint` joins the egress role table, governed by a sibling `allow-connect:` hostname list |
| **B10** | generalise `loader/profile-selects-nothing` → `loader/reads-nothing`, fired wherever a written line binds nothing on this build |
| **B11** | `asked-of:`/`escalates-to:` may not name a key under `agents:`; then a workspace `people:` map with `names: people` |
| **B12** | an action whose `takes:` declares a `money`-typed argument must state `spends-money:` explicitly; `guarded_by` reads `more-than:`; add `--deny-warnings` |
| **B15** | generalise the reader-table test: every field name any loader module looks up must be a field the schema declares |

---

## D5 — The instrument (B14)

`pact try <agent> "question"` — one turn, against a served model or the
deterministic mock. Not a server; a door. **Sequenced first**, because every
defect above was found by reading and the two worst findings of the review cycle
required running.
