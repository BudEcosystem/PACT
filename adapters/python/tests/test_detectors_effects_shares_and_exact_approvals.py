"""docs/98 WP-12: declared detectors, `effect:`, `in-share:`, `looks-like:`, and
an approval bound to the exact request it approved."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.conditions import holds  # noqa: E402
from pact_adapters.detectors import DECLARED, DetectorError, declared_in  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, WorkflowSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import Resumption  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402


def test_a_share_is_stable_and_about_the_size_it_says() -> None:
    line = {"value": "input.id", "in-share": "5%"}
    picks = [holds(line, f"req-{n}") for n in range(4000)]
    assert 0.03 < sum(picks) / len(picks) < 0.07, sum(picks)
    assert [holds(line, f"req-{n}") for n in range(50)] == picks[:50], "the same value, the same side"


def test_looks_like_reads_built_in_and_declared_detectors() -> None:
    assert holds({"value": "x", "looks-like": "card number"}, "card 4111 1111 1111 1111") is True
    assert holds({"value": "x", "looks-like": "card number"}, "no card here") is False
    held = DECLARED.set(declared_in({"detectors": {"order reference": {
        "description": "An order reference.", "looks-like": ["ORD-[0-9]{8}"], "examples": ["ORD-12345678"]}}}))
    try:
        assert holds({"value": "x", "looks-like": "order reference"}, "see ORD-12345678") is True
        assert holds({"value": "x", "looks-like": "order reference"}, "see ord-12345678") is False
    finally:
        DECLARED.reset(held)
    assert holds({"value": "x", "looks-like": "order reference"}, "ORD-12345678") is None, (
        "outside the workspace that declared it, nobody knows what it looks like"
    )


def test_a_detector_that_misses_its_own_example_is_refused() -> None:
    with pytest.raises(DetectorError, match="own example"):
        declared_in({"detectors": {"ref": {"description": "r", "looks-like": ["REF-[0-9]+"], "examples": ["ref 9"]}}})
    with pytest.raises(DetectorError, match="cannot be read"):
        declared_in({"detectors": {"ref": {"description": "r", "looks-like": ["REF-[0-9"]}}})


def test_a_declared_detector_hides_in_a_sentence() -> None:
    doc = {
        "detectors": {"order reference": {"description": "o", "looks-like": ["ORD-[0-9]{8}"]}},
        "redaction": {"hide": ['replace anything that looks like an order reference with "[ref]"']},
        "agents": {"a": {"description": "d", "instructions": "i"}},
    }
    seen: list[str] = []

    class Seeing(ReferenceTransport):
        async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
            seen.append(" ".join(str(m.get("content")) for m in history))
            return await super().model_call(system, history, tools)

    spec = AgentSpec.from_document(doc, "a")
    asyncio.run(run(spec, Seeing(Script([Turn("ok")])), "where is ORD-12345678?"))
    assert "ORD-12345678" not in seen[0] and "[ref]" in seen[0], seen[0]


DESK = {
    "agents": {"desk": {"description": "d", "instructions": "i", "uses": ["payments"], "policy": "money"}},
    "tools": {
        "payments": {
            "description": "Payments.",
            "actions": {
                "look-up": {"description": "Look an order up.", "reads-only": "yes", "takes": {"order": "text"}},
                "refund": {
                    "description": "Refund.",
                    "takes": {"order": "text", "amount": "money"},
                    "spends-money": "yes",
                    "same-request-key": "order",
                },
            },
        }
    },
    "questions": {
        "ok": {"description": "o", "says": "OK?", "answer": {"approved": "yes or no"},
               "asked-of": ["leads"], "answer-within": "30m", "if-nobody-answers": "stop-and-say-so"}
    },
    "policies": {"money": {"ask-a-person": [{"when": [{"tool": "payments", "effect": "spends"}], "question": "ok"}]}},
}


def _desk_run(calls: list[ToolCall]):
    spec = AgentSpec.from_document(DESK, "desk")
    ran: list[dict] = []
    tools = {"payments": lambda a: (ran.append(dict(a)), "done")[1]}
    turns = [Turn("", (c,)) for c in calls] + [Turn("finished")]
    out = asyncio.run(run(spec, ReferenceTransport(Script(turns)), "go", tools))
    return out, ran


def test_a_policy_on_effect_stops_the_spending_action_and_not_the_lookup() -> None:
    out, ran = _desk_run([ToolCall("payments", {"action": "look-up", "order": "O-1"})])
    assert out.halted == "final" and ran, (out.halted, ran)
    out, ran = _desk_run([ToolCall("payments", {"action": "refund", "order": "O-1", "amount": "10 USD"})])
    assert out.halted == "suspended" and not ran, (out.halted, ran)


def test_an_approval_does_not_apply_to_a_request_changed_after_it_was_seen() -> None:
    out, _ = _desk_run([ToolCall("payments", {"action": "refund", "order": "O-1", "amount": "10 USD"})])
    parked = out.suspension
    assert parked is not None and parked.request_digest
    answer = Resumption(correlation_key=parked.correlation_key, values={"approved": "yes"})
    assert parked.accepts(answer)
    parked.awaiting = (ToolCall("payments", {"action": "refund", "order": "O-1", "amount": "9000 USD"}),)
    assert not parked.accepts(answer), "the person approved 10 USD, not 9000"


def test_a_workflow_routes_a_stable_share_with_in_share() -> None:
    doc = {"workflows": {"w": {"description": "d", "starts-at": "pick", "steps": {
        "pick": {"does": "decide", "chooses-between": {"canary": "new", "stable": "old"}, "by": [{"rules": [
            {"when": [{"value": "input.id", "in-share": "50%"}], "choose": "canary"}, {"choose": "stable"}]}]},
        "new": {"does": "answer", "bind": {"v": "values.new"}},
        "old": {"does": "answer", "bind": {"v": "values.old"}},
    }}}, "values": {"new": {"value": "2"}, "old": {"value": "1"}}}
    spec = WorkflowSpec.from_workflow(doc, "w")
    got = [asyncio.run(run_workflow(spec, {"id": f"r{n}"}, Callers(), document=doc)).answer["v"] for n in range(200)]
    assert 60 < got.count("2") < 140, got.count("2")
