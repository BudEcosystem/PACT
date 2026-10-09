"""An agent is read with the workspace's own `remembers:` beside its own.

`workspace.remembers:` is "named memory any agent or workflow here may read as
`remembers.<name>`, written only by the stock actions `bud/remember` and
`bud/forget`". A workflow was read with it (`WorkflowSpec.workspace_remembers`);
an agent was read with its own entries alone, so a runtime handed `AgentSpec`
had no way to know what the workspace remembers. It is kept apart from
`facts`, because the agent's own `remember` writes only those.

The tree is `tests/trees/an-agent-that-reads-the-workspace-memory/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import AgentSpec  # noqa: E402
from trees import REPO, shown  # noqa: E402

TREE = REPO / "tests/trees/an-agent-that-reads-the-workspace-memory"


def test_an_agent_is_read_with_the_workspace_memory_kept_apart_from_its_own() -> None:
    spec = AgentSpec.from_document(shown(TREE), "desk", TREE)
    assert set(spec.facts.declared) == {"last-order-seen"}
    assert set(spec.workspace_remembers.declared) == {"house-style"}
    style = spec.workspace_remembers.declared["house-style"]
    assert (style.lasts, style.starts_as) == ("forever", "plain and brief")


def test_the_harness_fills_a_hole_and_a_bind_from_the_workspace_memory() -> None:
    """What `pact check` accepts, PACT's own harness runs: the hole
    `{{remembers.house-style}}` and the bind `style: remembers.house-style` are
    filled from what the host passes as remembered for the workspace's entry."""
    import asyncio

    from pact_adapters.harness import ToolCall, run
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    class Seeing(ReferenceTransport):
        systems: list[str] = []

        async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
            self.systems.append(system)
            return await super().model_call(system, history, tools)

    seen: list[dict] = []
    look = ToolCall("orders", {"action": "look-up", "order-number": "O-1"})
    seeing = Seeing(Script([Turn("Looking.", (look,)), Turn("Shipped.")]))
    spec = AgentSpec.from_document(shown(TREE), "desk", TREE)
    tools = {"orders": lambda a: (seen.append(dict(a)), "order O-1: shipped")[1]}
    result = asyncio.run(
        run(spec, seeing, "where is O-1?", tools, remembered={"house-style": "warm"})
    )
    assert "answer in this style: warm." in seeing.systems[0], seeing.systems[0]
    assert seen and seen[0].get("style") == "warm", seen
    assert not any("house-style" in u for u in result.unenforced), result.unenforced
