# Command line

Seven verbs. None of them ever executes author code, and six are
**read-only** — `pact build` is the one that writes, and only into a folder
that is not there yet.

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
pact write    [PATH]  Print the workspace as one PACT-language file
pact build <FILE> --to <FOLDER>
                      Write the folder a PACT-language file stands for
pact about            Say which commit this `pact` was built from
pact help             Show this message
```

`PATH` defaults to the current directory.

---

## `pact check`

The one you run constantly.

```console
$ pact check examples/refund-desk
OK — examples/refund-desk loaded cleanly (498 settings).
Egress: `allow-egress: []`, so nothing here may talk to anything outside this box.
```

The second line says where the workspace draws its boundary: which parts of it
may talk to something outside the machine. It is printed after every check that
finds no problems, and it has three forms:

| `workspace.yaml` writes | The line says |
|---|---|
| no `allow-egress:` line | no boundary is drawn, so every part may talk outside |
| `allow-egress: []` | nothing may |
| `allow-egress: [llm, tools]` | only those parts may |

Leaving the line out is a choice an author may make, and it is also what a
forgotten line looks like, so the tool says which one it read. It is not a
warning: it does not count as one and `--deny-warnings` does not fail on it.
`--quiet` leaves it out. An agent checked on its own (`pact check
agents/desk`) is told the boundary of the workspace around it.

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

Each workspace also carries `egress`, the same boundary `pact check` states,
for a runtime deciding whether to take the tree: `boundary` is `open` (no
`allow-egress:` line, so everything may talk outside), `closed` (`[]`) or
`listed`, and `allows` is the parts written. An absent line and an empty list
are opposite answers, and `allows` is empty for both: read `boundary`.

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

## `pact write`

The workspace at `PATH`, as one file in the [PACT language](../guide/the-pact-language.md).
The text goes to stdout and nothing is written anywhere. Settings that are
files — a knowledge set's documents, a skill's scripts — are named on stderr
and left where they are.

## `pact build`

The folder of YAML and Markdown that a `.pact` file stands for, written into
`--to <folder>`, which must not exist yet or must be empty. What was written is
read back and compared with the file before the command says it is done.

---

## `pact about`

Says what this binary is, in three lines a script can read.

```console
$ pact about
version: 0.1.0
commit: 63a048bbbc5279feefcac453d38a8582090b29db
uncommitted: no
```

| Line | Means |
|---|---|
| `version:` | the release this `pact` says it is |
| `commit:` | the commit the binary was built from, or `unknown` when it was built with no repository around it (a source archive) |
| `uncommitted:` | `no`, `yes` or `unknown`: whether anything the binary is built from — the crates, the specification, the model catalogue, the manifests — differed from that commit when it was built |

Both are fixed when the binary is compiled. They describe the binary, not the
folder you run it in.

**What it is for.** A runtime that pins PACT by commit runs whatever `pact` it
finds on the machine. Checking the source beside it does not check the binary:
one built from an edited checkout, or left over from another commit, looks the
same from outside. A pin check compares `commit:` with its pin and refuses
anything but `uncommitted: no`.
