"""The HITL kill test — the fixture the architecture says to write first.

> Request approval mid-tool-batch, kill the process, resume. Then assert
> (i) exactly-once tool execution, (ii) the decision is honoured, (iii) the
> resulting history is identical across both adapters.

One fixture discriminates every divergence the cross-framework semantics audit
found at once: HITL resume semantics, tool barriers, retry budgets, state
addressability, and determinism. If it passes on both adapters, decision D12 is
proven. If it does not, no other conformance result matters.

"Kill" here is real: the suspended state is serialised to JSON and the original
objects are dropped, so nothing in memory can carry the run across the boundary.

Approval used to be its own halt state here, `awaiting-approval`. It is now one
value of `suspension.reason`, because waiting for a person to approve something
and waiting for a teammate, a credential, a fresh budget or a decision about an
oversized conversation are one mechanism with five reasons (G6). Every guarantee
below is unchanged; what changed is that they now hold for all five.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import NEEDS_APPROVAL, Suspension  # noqa: E402
from pact_adapters.transports.anthropic_transport import AnthropicTransport  # noqa: E402
from pact_adapters.transports.autogen_transport import AutoGenTransport  # noqa: E402
from pact_adapters.transports.langchain_transport import LangChainTransport  # noqa: E402
from pact_adapters.transports.langgraph_transport import LangGraphTransport  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.openai_agents_transport import OpenAIAgentsTransport  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import PydanticAITransport  # noqa: E402

#: The SIX Python targets plus the framework-free control. Not seven: the
#: seventh target is Vercel AI, which runs in Node and has no durable resume at
#: all — `VercelAITransport.lattice()` publishes `durable_resume: "unsupported"`,
#: which is the honest answer and the reason it is absent here rather than
#: silently counted.
TRANSPORTS = {
    "reference": ReferenceTransport,
    "pydantic-ai": PydanticAITransport,
    "langgraph": LangGraphTransport,
    "langchain": LangChainTransport,
    "autogen": AutoGenTransport,
    "openai-agents": OpenAIAgentsTransport,
    "anthropic": AnthropicTransport,
}

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund")),
)

#: The tools this run may not call on its own. Named for what it is — a gate —
#: rather than for one reason a gate exists, since `needs_approval=` is now the
#: shorthand for the commonest of five.
GATED = frozenset({"payments"})


class Counter:
    """Counts every real tool invocation. Exactly-once is the whole point."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def tools(self) -> dict:
        def zendesk(_a):
            self.calls.append("zendesk")
            return "lamp, 6 days ago, broken, 40 USD"

        def payments(_a):
            self.calls.append("payments")
            return "refunded 40 USD"

        return {"zendesk": zendesk, "payments": payments}


def script() -> Script:
    """A parallel batch: read the ticket AND issue the refund in one step.
    The second needs approval; the first does not."""
    return Script(
        [
            Turn("Reading the ticket and issuing the refund.",
                 (ToolCall("zendesk", {"id": "T-1"}), ToolCall("payments", {"amount": 40}))),
            Turn("Approved: refunded 40 USD."),
        ]
    )


def serialise(p: Suspension) -> str:
    """Cross the process boundary for real.

    Writing the record down is the primitive's own job now, not this file's: a
    suspension that only one caller knows how to persist is a suspension that
    only survives in that caller's process.
    """
    return p.to_json()


def deserialise(blob: str) -> Suspension:
    return Suspension.from_json(blob)


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_a_gated_tool_parks_the_run(name: str) -> None:
    counter = Counter()
    result = asyncio.run(
        run(SPEC, TRANSPORTS[name](script()), "refund me", counter.tools(),
            needs_approval=GATED)
    )
    assert result.halted == "suspended"
    assert result.suspension is not None
    assert result.suspension.reason == NEEDS_APPROVAL, "and it says what it is waiting for"
    assert "payments" not in counter.calls, "a gated tool must not run before approval"
    assert counter.calls == ["zendesk"], "the ungated half of the batch still runs"


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_kill_and_resume_executes_each_tool_exactly_once(name: str) -> None:
    """(i) exactly-once. The ungated tool already ran before the park; resuming
    must not run it a second time."""
    counter = Counter()
    first = asyncio.run(
        run(SPEC, TRANSPORTS[name](script()), "refund me", counter.tools(),
            needs_approval=GATED)
    )

    # --- process dies here; only this string survives ---
    blob = serialise(first.suspension)
    del first

    resumed = asyncio.run(
        run(SPEC, TRANSPORTS[name](script()), "refund me", counter.tools(),
            needs_approval=GATED, resume=deserialise(blob),
            approved=frozenset({"payments"}))
    )

    assert resumed.halted == "final"
    assert counter.calls.count("zendesk") == 1, f"zendesk ran {counter.calls.count('zendesk')}x"
    assert counter.calls.count("payments") == 1, f"payments ran {counter.calls.count('payments')}x"


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_declining_approval_does_not_run_the_tool(name: str) -> None:
    """(ii) the decision is honoured. Resuming with no approval must park again,
    not quietly proceed."""
    counter = Counter()
    first = asyncio.run(
        run(SPEC, TRANSPORTS[name](script()), "refund me", counter.tools(),
            needs_approval=GATED)
    )
    again = asyncio.run(
        run(SPEC, TRANSPORTS[name](script()), "refund me", counter.tools(),
            needs_approval=GATED,
            resume=deserialise(serialise(first.suspension)), approved=frozenset())
    )
    assert again.halted == "suspended"
    assert "payments" not in counter.calls


def test_the_resumed_history_is_identical_across_all_transports() -> None:
    """(iii) the discriminating assertion. All SIX PYTHON targets must produce the
    same history after a kill and resume, or the loop is not really PACT's."""
    traces = {}
    for name, cls in TRANSPORTS.items():
        counter = Counter()
        first = asyncio.run(
            run(SPEC, cls(script()), "refund me", counter.tools(),
                needs_approval=GATED)
        )
        resumed = asyncio.run(
            run(SPEC, cls(script()), "refund me", counter.tools(),
                needs_approval=GATED,
                resume=deserialise(serialise(first.suspension)),
                approved=frozenset({"payments"}))
        )
        traces[name] = {"trace": resumed.trace(), "output": resumed.output,
                        "tools": counter.calls}

    reference = traces["reference"]
    for name, got in traces.items():
        assert got == reference, (
            f"D12 is not proven: {name} diverged after kill-and-resume.\n"
            f"  reference: {json.dumps(reference, indent=2)}\n"
            f"  {name}: {json.dumps(got, indent=2)}"
        )


def test_an_uninterrupted_run_and_a_resumed_run_reach_the_same_place() -> None:
    """Resume must be transparent: interrupting a run for a human must not
    change what the agent ends up doing."""
    straight_counter = Counter()
    straight = asyncio.run(
        run(SPEC, ReferenceTransport(script()), "refund me", straight_counter.tools(),
            needs_approval=frozenset())
    )

    c = Counter()
    first = asyncio.run(
        run(SPEC, ReferenceTransport(script()), "refund me", c.tools(),
            needs_approval=GATED)
    )
    resumed = asyncio.run(
        run(SPEC, ReferenceTransport(script()), "refund me", c.tools(),
            needs_approval=GATED,
            resume=deserialise(serialise(first.suspension)), approved=frozenset({"payments"}))
    )

    assert resumed.output == straight.output
    assert resumed.trace() == straight.trace()
    assert sorted(c.calls) == sorted(straight_counter.calls)
