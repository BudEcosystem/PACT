# pact-adapters

The Python side of PACT: the harness that owns the loop, the loader boundary
(`ir.AgentSpec`), the Pydantic AI bridge, the eval runner and seven transports.

## Install

The core needs three packages (`pydantic-ai-slim`, `pyyaml`, `httpx`):

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

The loader binary is found by `loader.pact_binary()`: `PACT_BIN`, then `pact`
on the `PATH`, then `target/release/pact` and `target/debug/pact` in this
checkout.

## Test

```bash
uv run --extra all --extra test pytest tests/ -q
```

`../../scripts/test-all.sh` runs this after the Rust suite and builds the
loader the suite reads through.
