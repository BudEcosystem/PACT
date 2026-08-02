"""A park is a process boundary, and a guarantee that does not cross it is gone.

Five places in `harness.py` parked a run, and each filled the durable block by
hand. Four of the five never set `used`, and `Meter.restored` falls back to the
step index for STEPS ALONE — so seconds, tool calls, tokens and money all
restarted at zero on the other side.

Measured, before the fix, with `tool-calls-at-most: 5`:

    before the park : tool_calls=3 of 5   parked.used={}
    after resume    : halted=final        tool_calls=4
    seven calls against a ceiling of five

Parking is what happens while a person decides whether money may go out. The one
place the guarantee is worth most is the place it was lost.

`Suspension.escalate` had the same hole one field over: it copied `used` and
`granted` and dropped `spent_keys`, so a run put to a second approver could
re-issue a payment the first approver had already let through.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.limits import Limits  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import Suspension  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

HARNESS = Path(__file__).resolve().parents[1] / "src/pact_adapters/harness.py"

SPEC = AgentSpec(
    name="Desk",
    description="Decides refunds",
    instructions="Look, then pay.",
    tools=(ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund")),
    max_steps=12,
    limits=Limits(tool_calls_at_most=5),
)
TOOLS = {"zendesk": lambda a: "ok", "payments": lambda a: "paid"}


def script() -> Script:
    """Three cheap calls, then the gated one, then more."""
    return Script(
        [
            Turn("a", (ToolCall("zendesk", {}),)),
            Turn("b", (ToolCall("zendesk", {}),)),
            Turn("c", (ToolCall("zendesk", {}),)),
            Turn("d", (ToolCall("payments", {}),)),
            Turn("e", (ToolCall("zendesk", {}),)),
            Turn("f", (ToolCall("zendesk", {}),)),
            Turn("g", (ToolCall("zendesk", {}),)),
            Turn("done", ()),
        ]
    )


def parked_then_resumed():
    gate = frozenset({"payments"})
    first = asyncio.run(run(SPEC, ReferenceTransport(script()), "hi", TOOLS, needs_approval=gate))
    assert first.halted == "suspended", first.halted
    # Only this string survives the process.
    blob = first.suspension.to_json()
    resumed = asyncio.run(
        run(
            SPEC,
            ReferenceTransport(script()),
            "hi",
            TOOLS,
            needs_approval=gate,
            resume=Suspension.from_json(blob),
            approved=gate,
        )
    )
    return first, resumed


def test_a_run_cannot_be_given_a_fresh_budget_by_being_interrupted() -> None:
    first, resumed = parked_then_resumed()
    assert first.used.tool_calls == 3
    assert resumed.halted == "tool-call-limit", (
        "the ceiling has to be reached on the far side of the park, not reset by it: "
        f"{resumed.halted}"
    )
    assert resumed.used.tool_calls <= 5, resumed.used.tool_calls


def test_every_park_site_fills_the_same_durable_block() -> None:
    """B4. Five careful edits is what was there; the point of the helper is that
    a sixth site cannot be careful and wrong.

    Read off the source, because what is under test is that no site does this by
    hand any more — a test that parks five ways would prove the five that exist
    work and say nothing about the sixth somebody writes next month.
    """
    text = HARNESS.read_text()
    body = text[: text.index("def _park_state(")] + text[text.index("async def _ran_out(") :]
    stragglers = sorted(
        set(re.findall(r"parked\.(steps|history|step_index|completed|phase|visits|used|granted|spent_keys)\s*=", body))
    )
    assert not stragglers, (
        f"these durable fields are still set by hand outside `_park_state`: {stragglers}. "
        "A park that fills its own block is a park that can forget one."
    )
    calls = text.count("_park_state(")
    assert calls >= 6, f"only {calls - 1} park sites route through the helper"


def test_the_helper_fills_every_field_a_resume_reads() -> None:
    """The other half of B4: the helper itself must not be the site that forgets.

    Held against `Suspension.from_json`, which is the complete list by
    construction — it is what a resume actually reads back.
    """
    text = HARNESS.read_text()
    helper = text[text.index("def _park_state(") : text.index("async def _ran_out(")]
    for field in ("steps", "history", "step_index", "completed", "phase", "visits",
                  "used", "granted", "spent_keys"):
        assert re.search(rf"parked\.{field}\s*=", helper), (
            f"`{field}` crosses the process boundary and the helper does not set it"
        )


def test_an_escalated_wait_keeps_the_keys_the_run_had_already_spent() -> None:
    """B1. An escalation is the same run put to a second person, so a payment
    already issued must not become issuable again by nobody answering in time."""
    parked = Suspension(
        reason="needs-approval",
        step_index=3,
        used={"steps": 3.0, "money": 0.5},
        granted={"payments": "yes"},
        spent_keys=(("payments", "issue-refund", "order-42"),),
    )
    on = parked.escalate(now=1.0)
    assert on.spent_keys == (("payments", "issue-refund", "order-42"),), on.spent_keys
    assert on.granted == {"payments": "yes"}
    assert on.used == {"steps": 3.0, "money": 0.5}
    assert on.correlation_key != parked.correlation_key, "a fresh key, or a late answer lands"


def test_an_escalation_carries_the_same_fields_a_park_does() -> None:
    """One list, held in both places. `escalate` builds a `Suspension` by hand
    too, and it dropped `spent_keys` for exactly as long as nothing compared it
    to the park it came from."""
    parked = Suspension(
        reason="needs-approval",
        steps=[],
        history=[{"role": "user", "content": "hi"}],
        step_index=2,
        completed={"zendesk": "ok"},
        phase="gather",
        visits={"gather": 1},
        used={"steps": 2.0},
        granted={"payments": "yes"},
        spent_keys=(("payments", "issue-refund", "k"),),
    )
    on = parked.escalate(now=9.0)
    for field in ("history", "step_index", "completed", "phase", "visits",
                  "used", "granted", "spent_keys"):
        assert getattr(on, field) == getattr(parked, field), (
            f"`{field}` did not survive the escalation"
        )
