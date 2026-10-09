# The parity suite

One folder per row of the PACT and Pydantic AI parity matrix (Bud Flow's
`docs/02-PACT-PYDANTIC-AI-PARITY.md` §2) that Phase 1 compiles. Each holds:

- a fixture: `tree/`, a PACT workspace read by the real loader, or `spec.yaml`,
  a Pydantic AI `AgentSpec` file;
- `expect.yaml`: `row:`, what the row's test asks (`says:`), the buckets its
  import must land in (`import:`), and for a tree, the scripted model turns
  (`model:`) and what the run must show (`expect:`). Beside those:
  - `variants:`, more runs of the same tree, each replacing some of those keys
    (H3's refusal, O7's last failed check);
  - `host-models:`, the host's model for each id `model:` names (`fails` or
    `answers`), handed to `build_agent(models=...)` (M3);
  - `check:`, files written over the tree (or alone, for a `spec.yaml` row) that
    `pact check` must refuse with the rule `refused:` names, or load (A4, N1);
  - `held-elsewhere:`, a clause of the row's test another PACT test holds, as
    `path::test` (the test must exist).

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

`adapters/python/tests/test_parity.py` runs every folder:

```bash
cargo build -p pact-cli
cd adapters/python && uv run --extra all --extra test pytest tests/test_parity.py -q
```

A row the matrix adds for a later phase gets its folder the day that phase
compiles it, and joins `PHASE_1` (or its own phase's list) in the driver.
