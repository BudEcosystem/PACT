# What is true today

Every row was produced by running the command beside it, against this
repository, on the day this page was last touched. Nothing here is inherited
from an earlier document.

## Reproduce the whole thing

```bash
./scripts/test-all.sh
```

| Claim | Value | How to check |
|---|---|---|
| Rust tests | **1263** | `cargo test --workspace` |
| Adapter tests | **2548** | `cd adapters/python && uv run pytest tests/ -q` |
| Total | **3,811** | both of the above |
| TypeScript type-checks | clean | `cd adapters/typescript && npx tsc --noEmit` |
| Lints | clean | `cargo clippy --all-targets` |
| Worked example loads | 498 settings | `cargo run -p pact-cli -- check examples/refund-desk` |
| Schema kinds | **54** | `python3 -c "import yaml;print(len(yaml.safe_load(open('spec/schema.yaml'))['groups']))"` |
| Fields that resolve a name | **42** | `grep -cE '^\s*names:' spec/schema.yaml` |

## What is proven, and what "proven" means

### Framework portability

**30 agents across 11 workspaces**, loaded by the Rust CLI, execute over **seven
targets** across two language runtimes and produce byte-identical traces, tool
sequences and model-call counts. The set is generated from `examples/`, so an
agent added to the tree joins it by existing rather than by somebody remembering.

!!! warning "The bound is part of the claim"
    It covers `instructions:`, `tools:`, `skills:`, `team:`, `answers-with:`,
    `loop:` and the `limits:` ceilings. It does **not** cover the governance keys
    the TypeScript port reports on `unenforced`. See
    [Adapters](../reference/adapters.md) for the exact list.

!!! note "Breadth and depth are different claims"
    The breadth run compares what the model was **told** and **offered** — the
    system text, the stage wording, the written procedures, the declared answer
    shape — over one turn per agent. Comparing only what the model *said back*
    proved nothing: a scripted model says the same thing whatever you tell it,
    and two real defects survived that version of the test.
    Multi-step tool sequences are held in depth for one agent by
    `test_portability.py`. The thesis asks for both.

### Human-in-the-loop durability

Request approval mid-parallel-tool-batch, serialise the paused state, drop every
object, resume in a fresh transport. Each tool executes exactly once, the
decision is honoured, and the resulting history is identical across frameworks.

Passes on the **six Python targets**. The Vercel target has no durable resume and
publishes `durable_resume: unsupported`, so it is not in that suite — counting
the framework-free control arm as a seventh would make "all seven" a sentence
about six.

### Air-gapped operation

No core feature requires a hosted service. Enforced, not just intended:

```
error: `summarised-by: claude-opus-5` is only served off this machine, and this
       workspace says `allow-egress: []` — nothing here may talk to anything
       outside the box.
  fix: write `summarised-by: qwen2.5-7b-instruct`, which runs here; or add `llm`
       to `allow-egress:` in workspace.yaml — which is a change a person has to
       approve.
```

### No code in the authoring surface

The worked example is 43 authored files and contains no executable code. Held by
a test, with the boundary written down: a *skill package* may carry `scripts/` —
files it points at, carried verbatim — because that is a property of that skill,
not of the format.

### Eve capability coverage

**101 of 101** capabilities accounted for: 49 expressible in the schema, 22
declared-and-delegated to the runtime, 30 deliberately refused. Held by
`crates/pact-cli/tests/eve_inventory.rs`, which fails if a row carries no
letter, if an (a) row cites a field the schema lacks, if a (b) row quotes a
section that does not exist, or if the file's stated totals disagree with its own
rows.

## What "verified" does not mean

- **Not benchmarked.** The model-portability figures are existence proofs on one
  task, stated with their scope. They are not accuracy retention in general.
- **Not load-tested.** Latency numbers measured on a contended machine were
  retracted rather than published, because they measured contention.
- **Not human-trialled.** The claim that a non-programmer can author an agent has
  a written protocol and has **not been run**. See
  [Gaps and blockers](gaps.md).
