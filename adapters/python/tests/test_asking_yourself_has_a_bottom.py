"""`asks-itself-at-most:` — a circle is allowed exactly as far as its figure.

The loader refuses a `team:` circle unless every agent on it writes
`limits.asks-itself-at-most:`; this file holds the other half of that grant —
that the reference harness SPENDS the figure. One request carries one activation
meter (`run.at_work`), the root's own activation is the first spend, and the
activation that would overspend is refused as that member's FAILURE — the same
path `OverBudget` takes — so the author's `if-someone-fails:` decides what
happens next and `when-it-runs-out: stop-and-say-so` is exactly this message
reaching the trace.

Without the meter this document is 93-GAPS B18's opaque failure: an agent that
names itself either recurses without a bottom or fails as "stopped: suspended"
with nothing naming the line that was missing.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import ToolCall, delegate_by_running, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

#: One agent whose team is itself — the circle the loader only allows because
#: the figure is written. No `name:` line, so `AgentSpec.name` is the key the
#: meter counts and `grant.member` carries.
CIRCLE = {
    "agents": {
        "echo-desk": {
            "description": "Answers, then asks itself for one more look before it is done.",
            "instructions": (
                "Answer the question. When you are unsure, ask your teammate — "
                "yourself — for a second look, and prefer the more careful answer."
            ),
            "team": {"echo-desk": "takes one more look at a drafted answer."},
            "limits": {
                "asks-itself-at-most": 2,
                "when-it-runs-out": "stop-and-say-so",
            },
        }
    }
}


def always_asking() -> Script:
    """A model that asks its teammate — itself — on every activation's first
    step, and answers only once the ask has been dealt with."""
    return Script([
        Turn("Taking another look.",
             (ToolCall("echo-desk", {"question": "sure about this?"}),)),
        Turn("Checked twice; the answer stands."),
    ])


def test_a_budgeted_self_ask_stops_at_its_figure() -> None:
    """Figure 2 buys exactly two activations — the root's own and one return —
    and the third is refused with the authored line named."""
    built: list[str] = []

    def transport_for(member: AgentSpec) -> ReferenceTransport:
        built.append(member.name)
        return ReferenceTransport(always_asking())

    bus = Bus()
    spec = AgentSpec.from_document(CIRCLE, "echo-desk")
    result = asyncio.run(
        run(spec, ReferenceTransport(always_asking()), "is this right?",
            ask_member=delegate_by_running(CIRCLE, transport_for, bus=bus),
            bus=bus)
    )

    # The run completes — no RecursionError, no hang, no "stopped: suspended".
    assert result.halted == "final"
    assert result.output == "Checked twice; the answer stands."
    # Activated exactly 2 times: the root run is the first spend and every
    # delegated activation builds a transport, so the refused third never
    # reaches `transport_for`.
    put_to_work = 1 + len(built)
    assert put_to_work == 2
    assert built == ["echo-desk"]
    # The overspend is a member FAILURE, not a crash — the `OverBudget` path —
    # and the text handed to the parent names the line that is spent.
    refused = [e for e in bus.seen("step.delegate.failed")]
    assert refused, "the third activation was never refused"
    assert "asks-itself-at-most" in refused[0].payload["reason"]


#: The same circle, but the agent writes a `name:` line that differs from its
#: map key. The meter counts `AgentSpec.name` ("Echo Desk"); the grant carries
#: the key ("echo-desk"). Before the identity fix the spend check read the key,
#: found nothing spent, and a budgeted agent recursed past its own figure to a
#: RecursionError — the exact opaque crash the figure exists to prevent.
NAMED_CIRCLE = {
    "agents": {
        "echo-desk": {
            "name": "Echo Desk",
            "description": "Answers, then asks itself for one more look before it is done.",
            "instructions": (
                "Answer the question. When you are unsure, ask your teammate — "
                "yourself — for a second look, and prefer the more careful answer."
            ),
            "team": {"echo-desk": "takes one more look at a drafted answer."},
            "limits": {
                "asks-itself-at-most": 2,
                "when-it-runs-out": "stop-and-say-so",
            },
        }
    }
}


def test_a_name_line_does_not_unmeter_the_circle() -> None:
    """A `name:` differing from the map key spends against the same meter —
    figure 2 still buys exactly two activations, and the third is refused
    rather than recursing to a crash."""
    built: list[str] = []

    def transport_for(member: AgentSpec) -> ReferenceTransport:
        built.append(member.name)
        return ReferenceTransport(always_asking())

    bus = Bus()
    spec = AgentSpec.from_document(NAMED_CIRCLE, "echo-desk")
    result = asyncio.run(
        run(spec, ReferenceTransport(always_asking()), "is this right?",
            ask_member=delegate_by_running(NAMED_CIRCLE, transport_for, bus=bus),
            bus=bus)
    )

    assert result.halted == "final"
    assert result.output == "Checked twice; the answer stands."
    put_to_work = 1 + len(built)
    assert put_to_work == 2
    assert built == ["Echo Desk"]
    refused = [e for e in bus.seen("step.delegate.failed")]
    assert refused, "the third activation was never refused"
    assert "asks-itself-at-most" in refused[0].payload["reason"]


#: A plain non-cyclic delegation document — nobody writes the figure, so
#: nobody may be asked to count.
PLAIN = {
    "agents": {
        "desk": {
            "description": "Decides refunds.",
            "instructions": "Ask the helper, then decide.",
            "team": {"helper": "checks the ticket."},
        },
        "helper": {
            "description": "Checks tickets.",
            "instructions": "Say what you see.",
        },
    }
}


def _plain_run(at_work: dict[str, int] | None = None):
    def transport_for(member: AgentSpec) -> ReferenceTransport:
        return ReferenceTransport(Script([Turn("looks fine")]))

    spec = AgentSpec.from_document(PLAIN, "desk")
    kwargs = {} if at_work is None else {"at_work": at_work}
    return asyncio.run(
        run(spec,
            ReferenceTransport(Script([
                Turn("Asking the helper.",
                     (ToolCall("helper", {"question": "ok?"}),)),
                Turn("Approved."),
            ])),
            "refund?",
            ask_member=delegate_by_running(PLAIN, transport_for),
            **kwargs)
    )


def test_an_agent_without_the_line_is_never_asked_to_count() -> None:
    """Additive inertness. A document that never writes the figure produces a
    byte-equal trace whether the meter is left to default or handed in — the
    meter fills, nothing reads it, and the helper's answer arrives exactly as
    it did before the parameter existed."""
    default = _plain_run()
    handed = _plain_run(at_work={})
    assert json.dumps(default.trace()) == json.dumps(handed.trace())
    assert default.halted == handed.halted == "final"
    assert default.output == handed.output == "Approved."
    assert default.steps[0].tool_results == ("looks fine",)
    # And the meter never surfaces where a model or a reader could see it.
    assert "asks-itself-at-most" not in json.dumps(default.trace())
