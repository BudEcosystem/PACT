"""`cost-per-request-from:` (docs/98 WP-14): a run's money ceiling handed in by
the surrounding system, never above the written `cost-per-request-under:`."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

DOC = {
    "agents": {
        "a": {
            "description": "d",
            "instructions": "i",
            "run-inputs": {"budget": "money"},
            "limits": {
                "cost-per-request-under": "1 USD",
                "cost-per-request-from": "run-inputs.budget",
                "when-it-runs-out": "stop-and-say-so",
            },
        }
    }
}


def _cap(budget):
    seen: dict = {}
    spec = AgentSpec.from_document(DOC, "a")
    assert spec.limits.cost_from == "run-inputs.budget"
    from pact_adapters import harness

    original = harness.granted

    def watching(member, allowance, currency=""):
        out = original(member, allowance, currency)
        seen["cap"] = out.limits.cost_per_request_under
        return out

    harness.granted = watching
    try:
        asyncio.run(run(spec, ReferenceTransport(Script([Turn("ok")])), "go", run_inputs={"budget": budget}))
    finally:
        harness.granted = original
    return seen.get("cap")


def test_a_smaller_budget_handed_in_is_the_ceiling() -> None:
    assert _cap("0.20 USD") == 0.20


def test_a_larger_budget_handed_in_is_held_to_the_written_one() -> None:
    assert _cap("50 USD") == 1.0
