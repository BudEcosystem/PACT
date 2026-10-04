"""A1, A2 and A4 end to end, against a real model on Pydantic AI.

Opt-in: set `PACT_LIVE_BASE_URL` (an OpenAI-compatible server) and
`PACT_LIVE_MODEL` (a model on it that calls tools). Skipped otherwise, so the
offline suite never reaches a network.

One tree, checked by the real loader, read through `ir.AgentSpec`, and run on
Pydantic AI with only public API, the way a host compiling PACT does:

* A1 — `{{run-inputs.brand}}` is filled by `holes.fill` before the model reads
  the instructions, and the model answers from the filled value;
* A2 — `model: [qwen2.5-14b-instruct, gpt-oss-20b]` becomes a `FallbackModel`
  whose first entry is unreachable, so the answer comes from the second;
* A4 — the tool action's `answers-with:` is the tool's `return_schema`
  (`return_schema_for`), and the host holds the result to it;
* and `usage_limits_for` passes no ceiling the author did not write.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.holes import fill  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.pydantic_ai_interop import return_schema_for, usage_limits_for  # noqa: E402

BASE_URL = os.environ.get("PACT_LIVE_BASE_URL", "")
MODEL = os.environ.get("PACT_LIVE_MODEL", "")
REPO = Path(__file__).resolve().parents[3]
PACT_BIN = REPO / "target" / "debug" / "pact"

pytestmark = pytest.mark.skipif(
    not (BASE_URL and MODEL),
    reason="opt-in: set PACT_LIVE_BASE_URL and PACT_LIVE_MODEL to a served model that calls tools",
)

AGENT = """\
description: Answers order questions for {{run-inputs.brand}}.
instructions: |
  You answer for the shop called {{run-inputs.brand}}. Always use the
  order-status tool to look an order up before you answer, then say the
  shop's name and the order's status in one short sentence.
model: [qwen2.5-14b-instruct, gpt-oss-20b]
run-inputs:
  brand: text
uses: [orders]
"""

TOOL = """\
description: Looks orders up.
connect: orders-server
actions:
  order-status:
    description: The status of one order.
    reads-only: yes
    takes:
      order-number: text
    answers-with:
      status: one of placed, shipped, delivered
"""


def _document(root: Path) -> dict:
    for folder in ("agents", "tools", "resources"):
        (root / folder).mkdir(parents=True)
    (root / "workspace.yaml").write_text("name: live\nallow-egress: []\n")
    (root / "agents" / "desk.yaml").write_text(AGENT)
    (root / "tools" / "orders.yaml").write_text(TOOL)
    (root / "resources" / "orders-server.yaml").write_text(
        "resource-kind: mcp-server\nendpoint: host/orders\n"
    )
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    checked = subprocess.run([str(PACT_BIN), "check", str(root)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    shown = subprocess.run([str(PACT_BIN), "show", str(root)], capture_output=True, text=True)
    return json.loads(shown.stdout)


def test_holes_fallback_and_a_typed_action_on_a_live_model(tmp_path: Path) -> None:
    from pydantic_ai import Agent
    from pydantic_ai.models.fallback import FallbackModel
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.tools import Tool
    from pydantic_ai.toolsets import FunctionToolset

    spec = AgentSpec.from_document(_document(tmp_path / "w"), "desk")
    assert spec.models == ("qwen2.5-14b-instruct", "gpt-oss-20b")
    assert {h.address for h in spec.holes} == {"run-inputs.brand"}
    (tool,) = spec.tools
    returns = return_schema_for(tool, "order-status")
    assert returns is not None

    # The host's catalogue: the first entry points at nothing that answers.
    served = {
        "qwen2.5-14b-instruct": OpenAIChatModel(
            "nothing-here", provider=OpenAIProvider(base_url="http://127.0.0.1:9/v1", api_key="x")
        ),
        "gpt-oss-20b": OpenAIChatModel(MODEL, provider=OpenAIProvider(base_url=BASE_URL, api_key="local")),
    }
    model = FallbackModel(*(served[m] for m in spec.models))

    results: list[dict] = []

    def order_status(**args: str) -> dict:
        results.append({"status": "shipped"})
        return results[-1]

    looked_up = Tool.from_schema(
        order_status,
        name="order-status",
        description="The status of one order.",
        json_schema={
            "type": "object",
            "properties": {"order-number": {"type": "string"}},
            "required": ["order-number"],
        },
    )

    async def typed(ctx, defs):  # type: ignore[no-untyped-def]
        # A4: the action's declared answer is the definition's return schema.
        return [replace(d, return_schema=returns, include_return_schema=True) for d in defs]

    run_inputs = {"brand": "Lumen Lamps"}
    agent = Agent(
        model,
        instructions=fill(spec.instructions, run_inputs=run_inputs),
        description=fill(spec.description, run_inputs=run_inputs),
        toolsets=[FunctionToolset([looked_up]).prepared(typed)],
    )
    limits = usage_limits_for(spec)
    assert limits.request_limit is None
    result = asyncio.run(agent.run("Where is order 1042?", usage_limits=limits))

    assert results, "the model never called the typed action"
    for got in results:
        assert set(got) == set(returns["required"])
        assert got["status"] in returns["properties"]["status"]["enum"]
    said = str(result.output).lower()
    assert "lumen lamps" in said and "shipped" in said, result.output
    asked = [m for m in result.all_messages() if m.kind == "response"]
    assert all(getattr(m, "model_name", "") != "nothing-here" for m in asked)
