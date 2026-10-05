"""A port, and its clock, read once for every runtime (D24: PACT declares, the runtime connects).

`ports/` reached no Python at all: the loader derived `kind: schedule` from an
`every:` line and no runtime could say when that schedule fires, who may reach
the port, or what makes two messages one conversation. `ir.PortSpec` reads a
port; `schedules.Schedule` reads `every:` with a closed grammar and refuses by
name what it cannot read.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import PortSpec, ports_of  # noqa: E402
from pact_adapters.schedules import Schedule, Unreadable  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PACT_BIN = REPO / "target" / "debug" / "pact"
TUESDAY_NOON = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("written", "line", "fires"),
    [
        ("Friday at 4pm", "0 0 16 * * 5", datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)),
        ("weekday mornings at 9", "0 0 9 * * 1-5", datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)),
        ("Mondays and Thursdays at noon", "0 0 12 * * 1,4", datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)),
        ("every day at 16:30", "0 30 16 * * *", datetime(2026, 10, 6, 16, 30, tzinfo=timezone.utc)),
        ("weekly", "0 0 0 * * 1", datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)),
        ("0 16 * * 5", "0 0 16 * * 5", datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)),
        ("every 10 minutes", "@every 600s", datetime(2026, 10, 6, 12, 10, tzinfo=timezone.utc)),
        ("every 2 seconds", "@every 2s", datetime(2026, 10, 6, 12, 0, 2, tzinfo=timezone.utc)),
    ],
)
def test_every_is_read_into_one_line_a_clock_keeps(written: str, line: str, fires: datetime) -> None:
    schedule = Schedule.parse(written)
    assert schedule.line == line and schedule.written == written
    assert schedule.next_after(TUESDAY_NOON) == fires


def test_an_interval_is_kept_exactly_and_its_slots_do_not_depend_on_when_you_asked() -> None:
    every7 = Schedule.parse("every 7 seconds")
    first = every7.next_after(TUESDAY_NOON)
    slots = [first]
    for _ in range(20):
        slots.append(every7.next_after(slots[-1]))
    assert {(b - a).total_seconds() for a, b in zip(slots, slots[1:])} == {7.0}, "cron's */7 would not"
    assert every7.next_after(first.replace(microsecond=500)) == slots[1]


@pytest.mark.parametrize("bad", ["sometimes", "Friday at 25", "every 0 seconds", "61 * * * *", "0 0 30 2 *"])
def test_a_line_that_is_not_a_time_is_refused_with_the_forms_that_work(bad: str) -> None:
    with pytest.raises(Unreadable, match="Friday at 4pm"):
        Schedule.parse(bad)


def test_the_shipped_ports_are_read_as_written() -> None:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    shown = subprocess.run([str(PACT_BIN), "show", str(REPO / "examples" / "refund-desk")],
                           capture_output=True, text=True, check=True)
    doc = json.loads(shown.stdout)
    by_name = {p.name: p for p in ports_of(doc)}
    review = by_name["weekly-review"]
    assert (review.kind, review.if_still_running, review.answers) == ("schedule", "skip", "refund-desk")
    assert review.schedule.line == "0 0 16 * * 5"
    slack = by_name["slack"]
    assert slack.kind == "conversation" and slack.schedule is None
    assert slack.same_conversation_when == ("they are in the same thread",)
    assert slack.who_can_reach_it == ("people in our Slack workspace",)


def test_a_port_with_every_is_a_timer_and_its_remembers_is_read_like_an_agents() -> None:
    doc = {"ports": {"tick": {"description": "d", "every": "every 2 seconds", "answers": "a",
                              "remembers": {"last-reply": {"description": "where we replied",
                                                           "lasts": "one-conversation"}}}}}
    tick = PortSpec.read(doc, "tick")
    assert tick.kind == "schedule" and tick.who_can_reach_it == ()
    assert tick.remembers.declared["last-reply"].lasts == "one-conversation"
    with pytest.raises(KeyError, match="tick"):
        PortSpec.read(doc, "nope")
