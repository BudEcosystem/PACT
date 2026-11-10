"""The circuit breaker (docs/98 WP-13): `rests-after:` and `rests-for:` on a tool."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.rests import Rests  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

DOC = {
    "agents": {"a": {"description": "d", "instructions": "i", "uses": ["search"],
                     "limits": {"steps-at-most": 20, "when-it-runs-out": "stop-and-say-so"}}},
    "tools": {"search": {"description": "Search.", "rests-after": 2, "rests-for": "5m",
                         "actions": {"find": {"description": "Find.", "reads-only": "yes"}}}},
}


class Clock:
    now = 100.0

    def __call__(self) -> float:
        return self.now


def test_after_two_failures_in_a_row_the_tool_is_rested_and_the_model_is_told() -> None:
    calls: list[int] = []

    def search(args):
        calls.append(1)
        raise RuntimeError("upstream timed out")

    spec = AgentSpec.from_document(DOC, "a")
    assert spec.rests == {"search": (2, 300.0)}
    call = ToolCall("search", {"action": "find"})
    script = Script([Turn("", (call,)), Turn("", (call,)), Turn("", (call,)), Turn("giving up")])
    clock = Clock()
    rests = Rests()
    out = asyncio.run(run(spec, ReferenceTransport(script), "go", {"search": search}, clock=clock, rests=rests))
    assert len(calls) == 2, "the third call was not made"
    told = [r for s in out.steps for r in s.tool_results]
    assert any("is resting" in r for r in told), told
    # Five minutes later it is tried again.
    clock.now += 301
    assert rests.resting("search", clock()) is None


def test_one_success_resets_the_count() -> None:
    r = Rests()
    assert not r.record("t", True, 0.0, (2, 60.0))
    assert not r.record("t", False, 0.0, (2, 60.0))
    assert not r.record("t", True, 0.0, (2, 60.0)), "one failure since the success"
    assert r.record("t", True, 0.0, (2, 60.0))
    assert r.resting("t", 30.0) == 60.0
