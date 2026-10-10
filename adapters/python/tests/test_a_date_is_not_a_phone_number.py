"""A date is not a phone number, and a phone number still is.

`anything that looks like a phone number` read eight separated digits as one,
so every ISO date (`2026-07-15`) in a chart, a log or a tool result was hidden
as a phone number: Bud Flow's corpus case #51 read a physical therapy course
"from [removed] to [removed]" and could not tell it lasted seven weeks. A phone
number has ten digits or more, and a run of digits that holds a date is dates.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.interceptors import Chain  # noqa: E402


def _said(text: str) -> str:
    chain = Chain.from_document(
        {"agents": {"a": {}}, "redaction": {"hide": ["anything that looks like a phone number"]}}, "a"
    )
    seen, _ = chain.run("step.message.before", {"content": text})
    return seen["content"]


@pytest.mark.parametrize(
    "text",
    [
        "12 visits from 2026-07-15 to 2026-09-01 (7 weeks)",
        "seen on 2026-10-05 09:00 and again 2026-10-12",
        "two dates side by side: 2026-07-15 2026-09-01",
        "order 4471 of 2026, room 12",
    ],
)
def test_a_date_or_a_short_number_is_left_as_written(text: str) -> None:
    assert _said(text) == text


@pytest.mark.parametrize(
    "phone", ["312-555-0142", "(970) 555-0182", "+44 20 7946 0958", "970 555 0182", "3125550142"]
)
def test_a_phone_number_is_still_hidden(phone: str) -> None:
    said = _said(f"call me on {phone} after 5")
    assert phone not in said and "[removed]" in said, said
