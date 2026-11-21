"""A member a rule stopped tells its lead what it had already done.

A cashier charges one order, then a counting rule stops its run before a second
charge. The member's reply used to be the bare fact of the stop
(`cashier stopped: stopped-by-rule`), so the lead knew neither the rule's words
nor that the first charge had gone through, and a live lead then told the
customer "not charged" for an order whose money had moved. The lead now reads
the rule's words, then each call holding a `same-request-key:` the member's run
completed, with what it returned. Every runtime writes the same heading
(`harness.COMPLETED_CALLS_HEADING`), so a lead reads one hand-off on each.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import (  # noqa: E402
    COMPLETED_CALLS_HEADING,
    ToolCall,
    delegate_by_running,
    run,
)
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

STOP = "A second charge in one request needs a person. Nothing further was charged."

TEAM: dict[str, Any] = {
    "agents": {
        "desk": {
            "description": "Takes the request and hands the charges to the cashier.",
            "instructions": "Ask the cashier to charge the orders.",
            "team": {"cashier": "charges orders"},
        },
        "cashier": {
            "description": "Charges orders.",
            "instructions": "Charge each order.",
            "uses": ["payments"],
            "interceptors": ["one-charge-per-request"],
        },
    },
    "interceptors": {
        "one-charge-per-request": {
            "when": "step.tool.before",
            "may": ["stop-the-run"],
            "rules": [f'if payments/charge is called more than 1 time in one run, stop and say "{STOP}"'],
        }
    },
    "tools": {
        "payments": {
            "description": "Card payments.",
            "actions": {
                "charge": {
                    "description": "Charge one order.",
                    "takes": {"order": "text"},
                    "spends-money": "yes",
                    "same-request-key": "order",
                },
                "lookup": {"description": "Look up an order.", "takes": {"order": "text"}, "reads-only": "yes"},
            },
        }
    },
}


class Lead:
    """Asks the cashier once, then answers with what the cashier's reply said."""

    def __init__(self) -> None:
        self.read: list[str] = []

    async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
        replies = [str(m.get("content")) for m in history if m.get("role") == "tool"]
        if replies:
            self.read.extend(replies)
            return "Reported.", []
        return "", [ToolCall("cashier", {"question": "charge ORD-1 and ORD-2"})]

    def __getattr__(self, name: str) -> Any:
        if name == "unenforced":
            return lambda: ()
        raise AttributeError(name)


def _hand_off(cashier: list[Turn], charge: Any) -> str:
    def cashier_for(member: AgentSpec) -> ReferenceTransport:
        return ReferenceTransport(Script(cashier))

    impls = {"payments": charge}
    lead = Lead()
    out = asyncio.run(run(
        AgentSpec.from_document(TEAM, "desk"), lead, "Charge ORD-1 and ORD-2.", impls,
        ask_member=delegate_by_running(TEAM, cashier_for, tool_impls=impls),
    ))
    assert out.halted == "final", out.halted
    assert len(lead.read) == 1, lead.read
    return lead.read[0]


def _charge(order: str) -> Turn:
    return Turn("", (ToolCall("payments", {"action": "charge", "order": order}),))


def test_the_lead_reads_the_rule_and_the_charge_that_went_through() -> None:
    made: list[str] = []
    said = _hand_off(
        [_charge("ORD-1"), _charge("ORD-2"), Turn("done")],
        lambda a: (made.append(a["order"]), '{"charged": true, "receipt": "R-1"}')[1],
    )
    assert made == ["ORD-1"], "the rule stopped the second charge before it was made"
    assert said == (
        f"error: cashier could not answer: cashier was stopped by a rule: {STOP}\n"
        f"{COMPLETED_CALLS_HEADING}\n"
        '- payments/charge: {"charged": true, "receipt": "R-1"}'
    ), said


def test_a_member_stopped_before_it_completed_a_claimed_call_says_only_the_rule() -> None:
    def failing(a: dict[str, Any]) -> str:
        raise RuntimeError("the bank is down")

    said = _hand_off(
        [
            Turn("", (ToolCall("payments", {"action": "lookup", "order": "ORD-1"}),)),
            _charge("ORD-1"),
            _charge("ORD-2"),
            Turn("done"),
        ],
        lambda a: failing(a) if a["action"] == "charge" else "due 5 USD",
    )
    assert said == f"error: cashier could not answer: cashier was stopped by a rule: {STOP}", said
    assert COMPLETED_CALLS_HEADING not in said, "a look-up holds no key and a failed charge did not complete"
