# The parity suite

One folder per agent-level row of the PACT and Pydantic AI parity matrix (Bud
Flow's `docs/02-PACT-PYDANTIC-AI-PARITY.md` §2: A, T, H, O, S, C, M, F, N, P, D,
E, K, X and I; the graph rows are workflows'). Each holds:

- a fixture: `tree/`, a PACT workspace read by the real loader; `spec.yaml`, a
  Pydantic AI `AgentSpec` file; or `agent.py`, a module that builds an `Agent`
  (named `agent`) without running it. A tree's agent is built by `build_agent`
  and imported back through the live door, as an `agent.py`'s is; the live door
  reads the object through Pydantic AI's public API only, and every live import
  also names `not_shown`, what that API does not show;
- or no fixture, for a row with nothing on an agent to import (`import: none`
  and `why:`: the row is a run's, a host's or an export's), or one another
  importer reads (`later:` names the package: WP-39's `mcp.json`, pydantic-evals
  datasets, harness agent folders and Skills);
- `expect.yaml`: `row:`, what the row's test asks (`says:`), the buckets its
  import must land in (`import:`), and for a tree, the scripted model turns
  (`model:`) and what the run must show (`expect:`). Beside those:
  - `import: block:`, lines the imported agent must hold exactly (O4's
    `answers-with-mode:`);
  - `export:`, the keys its export must name as not carried (S2). For a tree
    row, `round-trip:`, `the same digest` when a spec file holds the agent whole
    (S3, PACT → Pydantic AI → PACT: exported, imported back, the same
    `pact show` digest), else why not. For a `spec.yaml` or `agent.py` row, S3's
    other half, Pydantic AI → PACT → Pydantic AI: the imported agent exported
    as a spec file is the source file less what its import named, and imported
    from that file is the agent less what its export named;
  - `variants:`, more runs of the same tree, each replacing some of those keys
    (H3's refusal, O7's last failed check);
  - `host-models:`, the host's model for each id `model:` names (`fails` or
    `answers`), handed to `build_agent(models=...)` (M3);
  - `check:`, files written over the tree (or alone, for a `spec.yaml` row) that
    `pact check` must refuse with the rule `refused:` names, or load (A4, N1);
  - `held-elsewhere:`, a clause of the row's test another PACT test holds, as
    `path::test` (the test must exist).

A row whose 02P Import column says *mapped* or *carried* and whose fixture here
reports a named loss is one PACT does not translate yet (the harness
capabilities, a `tool_choice` list, an output function, a choice between answer
shapes (O3), a file answer (F4), a timeout on one tool); the loss names the PACT
construct to write.

## What each row's test column asks, and where it is held

Every clause of the 02P Test column is asserted by the row's `expect.yaml`, by a
test `held-elsewhere:` names, or is listed here with the reason this path does
not hold it.

| Row | Clause | Why it is not held here |
|---|---|---|
| A14 | "a second `ModelRetry` fails the step at *n* = 1" | PACT's `checks-at-most:` counts attempts in all (`spec/schema.yaml`: "write `1` to fail at the first miss"), so at 1 the first broken answer fails the step and no retry is sent. The row asserts that (`model-asked: 1` on a script that would pass on its third answer) |
| T2 | "the typed stub in `run-code` matches" | `run-code` is Phase 4 (WP-32), not this path |
| H1 | "kill test: approve after a restart, the tool runs once" | `build_agent` keeps no record across a restart; the runtime does (Bud Agent Flow's kill tests) |
| H3 | "edited arguments are re-checked against the gate" | On this path a gate is per tool (`requires_approval`), so an edited call is the call the person just approved and there is nothing to re-check; a gate that reads arguments is the runtime's (Bud Agent Flow, `test_an_edit_that_would_need_a_different_question_is_refused`) |
| O2 | "the typed outputs of 20 use-case fixtures import with no loss" | The use-case fixtures are Bud Agent Flow's corpus; the row holds one typed answer of four shapes |
| O3 | "the chosen kind routes (#10, #33, #76)" | A choice between answer shapes is not translated yet (a named loss), so there is no kind to route; those cases are Bud Agent Flow's corpus |
| O4 | "each mode reaches the request" | The row holds that the mode is carried (`import: block:`); a mode reaching a request is a run's, which this path does not run for a module row |
| T4 | "the gate holds on both sides for the same arguments" | The row holds that every call asks a person and the function is named; a gate on a call's arguments is the runtime's (Bud Agent Flow's policy rules) |
| M6 | "#8 at 0.8: an answer below the threshold goes to the next rung" | The row holds that a decision model's id is carried; the threshold and its rungs are a run's, case #8 of Bud Agent Flow's corpus |
| A12 | "the same tools are offered on both sides" | A `tool_choice` list is not translated yet (a named loss), so the row holds that it is named, not cut to its first |

`adapters/python/tests/test_parity.py` runs every folder:

```bash
cargo build -p pact-cli
cd adapters/python && uv run --extra all --extra test pytest tests/test_parity.py -q
```

T12's *a prefixed MCP server keeps its tool names* needs an MCP client
(FastMCP), which this suite does not install: its `agent.py` holds prefixes,
renames, a filter and approval over function toolsets, and Bud Agent Flow's
`tests/adapters/pydantic_ai/test_pa_imported_agent.py` holds the MCP server, run on the imported tree.
