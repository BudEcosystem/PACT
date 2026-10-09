# pact-adapters

The Python side of PACT: the harness that owns the loop, the loader boundary
(`ir.AgentSpec`), the Pydantic AI bridge, the eval runner and seven transports.

## Install

The core needs three Python packages (`pydantic-ai-slim`, `pyyaml`, `httpx`) and the loader:

```bash
pip install pact-adapters
```

Each other framework is an extra, named by the transport that binds it:

| Extra | Installs | For |
|---|---|---|
| `anthropic` | `anthropic` | `transports/anthropic_transport.py` |
| `autogen` | `autogen-agentchat`, `autogen-core` | `transports/autogen_transport.py` |
| `langgraph` | `langgraph`, `langchain-core` | `transports/langgraph_transport.py` |
| `langchain` | `langchain-core` | `transports/langchain_transport.py` |
| `openai-agents` | `openai-agents`, `openai` | `transports/openai_agents_transport.py` |
| `deepeval` | `deepeval` | the DeepEval metrics in `providers.py` |
| `all` | every extra above | `pact-conformance`, which compares all seven |
| `test` | `pytest` | the suite |

`pact-adapters` also depends on `pact-loader`, at its own version: the wheel
that carries the `pact` binary (Linux, manylinux 2.28, x86_64 and aarch64; any
other platform builds it from source with a Rust toolchain). The loader is found
by `loader.pact_binary()`: `PACT_BIN`; then, in a checkout, `target/release/pact`
or `target/debug/pact`, whichever was built last; then the `pact` the wheel
installed beside this interpreter (`<venv>/bin/pact`, found with that folder on
no `PATH`); then `pact` on the `PATH`.

## Test

```bash
uv run --extra all --extra test pytest tests/ -q
```

`../../scripts/test-all.sh` runs this after the Rust suite and builds the
loader the suite reads through.
