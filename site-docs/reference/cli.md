# Command line

Five verbs. All are **read-only** — none of them ever executes author code.

!!! quote "Why the CLI cannot run your agent"
    *"Validation that runs the thing being validated is not validation, it is a
    supply-chain hazard."* Running models is the adapters' job, and the command
    that scores a suite lives there for that reason.

```
pact check    [PATH]  Load the agent tree and report any problems
pact show     [PATH]  Print the loaded document as JSON
pact waits    [PATH]  Print every wait this tree can produce, with the
                      deadline a runtime must set a timer for
pact discover [PATH]  Find every PACT workspace under PATH and print an
                      inventory a runtime can index (no build step)
pact card <agent> [PATH]
                      Print one agent's A2A Agent Card
pact help             Show this message
```

`PATH` defaults to the current directory.

---

## `pact check`

The one you run constantly.

```console
$ pact check examples/refund-desk
OK — examples/refund-desk loaded cleanly (498 settings).
```

Every problem it reports names the file, the line, what is wrong, and a fix you
can type:

```
error: 'model-for-checking' is set, but 'loop' is not.
  fix: Add a line next to it: `loop: ...` — how this agent thinks:
       `pact:loop/standard`, `pact:loop/plan-then-do`, `pact:loop/react`,
       `pact:loop/reflexion`, `pact:loop/tree-of-thought`,
       `pact:loop/answer-more-than-once`, or the name of a shape
       you wrote in `loops/`.
```

## `pact show`

The loaded document as JSON — what every adapter actually receives. Useful for
seeing what the [Expansion Rule](../concepts/expansion-rule.md) produced from
your tree, and what a `based-on:` inherited.

## `pact waits`

Every point where a run can stop and wait for a person, with the deadline a
runtime must set a timer for. JSON on stdout, warnings on stderr, so the record
stays machine-readable.

This exists because a wait nobody schedules a timer for is a run that waits
forever — which is exactly as long as one without a deadline waits.

## `pact discover`

Every workspace under a path, as an inventory a runtime can index. No build
step, so a host can find and load agents without executing anything.

Each workspace carries its `digest` (the canonical document's), and each of
its workflows under `workflows` carries two more, the ones a waiting run is
pinned to:

- `doc-digest` moves when anything the workflow's run relies on changes: the
  workflow itself, a workflow it calls, or anything of the workspace outside
  its workflows (tools, agents, programs, policies, settings). An edit to a
  workflow it never reaches, to the owners and release settings, or to the
  eval suite and its cases (they grade a run and govern none), leaves it as
  it was, so a run waiting on this workflow can still be resumed.
- `contract-digest` moves only with what its callers rely on: `accepts:`,
  `answers-with:`, `published-as:`, and each port that answers it with its
  `same-conversation-when:` and `if-still-running:`.

```console
$ pact discover tests/trees/workflows-16-trial-booking
[{ …, "digest": "sha256:…",
   "workflows": [
     { "name": "parent-contact", "doc-digest": "sha256:…", "contract-digest": "sha256:…" },
     { "name": "trial-booking", "doc-digest": "sha256:…", "contract-digest": "sha256:…" } ] }]
```

## `pact card`

One agent's **A2A Agent Card** — the interoperability protocol Vercel Eve does
not implement at all (`a2a`, `agent-card` and `acp` match zero files in its
source).

```console
$ pact card refund-desk examples/refund-desk
{
  "protocolVersion": "1.0",
  "name": "Refund Desk",
  "description": "Decides whether a customer's refund request should be approved.",
  "skills": [ { "id": "zendesk", "name": "zendesk", … } ]
}
```

---

## Scoring an eval suite

Not a CLI verb, deliberately — it runs models:

```bash
./scripts/pact-eval <PATH>
```

`scripts/pact-eval` is a wrapper that finds an interpreter with this adapter's
dependencies. The same thing, spelled out:

```bash
cd adapters/python && uv run python -m pact_adapters.evals <PATH>
```

`pact_adapters.scoring` is where the scoring machinery lives, and it is not the
command — running it directly would load a second copy of every case and verdict
class. It says so if you try.

`pact check` tells you whether a suite is **well-formed**. This tells you whether
it **passes**.

## Options

| Option | Effect |
|---|---|
| `--quiet` | only print problems, not the summary |
| `--unsafe-spec` | validate against `$PACT_SPEC` instead of the compiled-in specification. Development builds only, and the source is named on every run that uses it |
