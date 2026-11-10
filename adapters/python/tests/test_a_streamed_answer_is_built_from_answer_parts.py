"""`stream of` and the reasoning-token firewall (docs/98 WP-14).

A transport that streams yields parts, each with a kind. The reply is built
from the answer parts only, so reasoning never reaches what the agent says,
however a provider interleaves them; every part is announced on the bus.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import Part, ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.questions import Shape  # noqa: E402


class Streaming:
    def __init__(self) -> None:
        self.turn = 0

    async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
        raise AssertionError("a streaming transport is asked to stream")

    async def model_stream(self, system, history, tools):  # type: ignore[no-untyped-def]
        self.turn += 1
        if self.turn == 1:
            yield Part("reasoning", "The user wants the total; I should look it up. ")
            yield Part("tool-call", call=ToolCall("ledger", {"action": "total"}))
            return
        yield Part("answer", "The total ")
        yield Part("reasoning", "(secret chain of thought) ")
        yield Part("answer", "is 42.")

    def __getattr__(self, name: str) -> Any:
        if name == "unenforced":
            return lambda: ()
        raise AttributeError(name)


def test_reasoning_never_reaches_the_answer_and_every_part_is_announced() -> None:
    doc = {
        "agents": {"a": {"description": "d", "instructions": "i", "uses": ["ledger"],
                         "answers-with": {"reply": "stream of text"}}},
        "tools": {"ledger": {"description": "L", "actions": {"total": {"description": "t", "reads-only": "yes"}}}},
    }
    bus = Bus()
    spec = AgentSpec.from_document(doc, "a")
    out = asyncio.run(run(spec, Streaming(), "what is the total?", {"ledger": lambda a: "42"}, bus=bus))
    assert out.output == "The total is 42.", out.output
    assert "secret" not in out.output
    kinds = [e.payload.get("kind") for e in bus.log if e.payload.get("kind")]
    assert kinds == ["reasoning", "tool-call", "answer", "reasoning", "answer"], kinds


def test_stream_of_is_the_shape_inside_once_it_has_arrived() -> None:
    assert Shape.parse("stream of text") == Shape.parse("text")
    assert Shape.parse("stream of one of yes, no") == Shape.parse("one of yes, no")
