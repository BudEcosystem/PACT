# The parity suite

One folder per row of the PACT and Pydantic AI parity matrix (Bud Flow's
`docs/02-PACT-PYDANTIC-AI-PARITY.md` §2) that Phase 1 compiles. Each holds:

- a fixture: `tree/`, a PACT workspace read by the real loader, or `spec.yaml`,
  a Pydantic AI `AgentSpec` file;
- `expect.yaml`: `row:`, what the row's test asks (`says:`), the buckets its
  import must land in (`import:`), and for a tree, the scripted model turns
  (`model:`) and what the run must show (`expect:`).

`adapters/python/tests/test_parity.py` runs every folder:

```bash
cargo build -p pact-cli
cd adapters/python && uv run --extra all --extra test pytest tests/test_parity.py -q
```

A row the matrix adds for a later phase gets its folder the day that phase
compiles it, and joins `PHASE_1` (or its own phase's list) in the driver.
