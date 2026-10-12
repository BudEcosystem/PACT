"""A wait hears only its own events (N193): a question's `only-when:` is read as written, and
`Question.hears` holds each line over what the event brought (`event.<field>`) and what the wait
can read (`item.`, `input.`, ...), through the one condition reader (`conditions.all_hold`).

The loader's half (`arrivals.rs`) is `crates/pact-cli/tests/a_wait_hears_only_its_own_events.rs`.
"""

from __future__ import annotations

from pact_adapters.conditions import ABSENT
from pact_adapters.questions import Question

OWN = {"value": "event.custodian-id", "is": {"value": "item.employee-id"}}


def _wait(*lines: dict) -> Question:
    written = {"description": "x", "asked-of": ["acknowledged"], "answer-within": "5 days"}
    return Question.of("acknowledged", {**written, "only-when": list(lines)}, {"ports": {"acknowledged": {}}})


def test_only_when_is_read_as_written() -> None:
    assert _wait(OWN).only_when == (OWN,)
    assert Question.of("p", {"says": "?", "answer": {"ok": "yes or no"}, "asked-of": ["a"]}, {}).only_when == ()


def test_a_wait_hears_the_event_of_its_own_item_and_no_other() -> None:
    item = {"item.employee-id": "E-7"}.get
    wait = _wait(OWN)
    assert wait.hears({"custodian-id": "E-7", "at": "09:00"}, lambda b: item(b, ABSENT)) is True
    assert wait.hears({"custodian-id": "E-8"}, lambda b: item(b, ABSENT)) is False
    assert wait.hears({}, lambda b: item(b, ABSENT)) is False, "an event that names no custodian is not its own"


def test_every_line_must_hold_and_a_field_inside_a_field_is_read() -> None:
    wait = _wait(OWN, {"value": "event.receipt.kind", "is-one-of": ["read", "signed"]})
    read = {"item.employee-id": "E-7"}.get
    assert wait.hears({"custodian-id": "E-7", "receipt": {"kind": "signed"}}, lambda b: read(b, ABSENT))
    assert not wait.hears({"custodian-id": "E-7", "receipt": {"kind": "bounced"}}, lambda b: read(b, ABSENT))


def test_a_wait_with_no_only_when_hears_any_event() -> None:
    wait = Question.of("w", {"description": "x", "asked-of": ["acknowledged"]}, {"ports": {"acknowledged": {}}})
    assert wait.hears({"custodian-id": "anyone"}, lambda b: ABSENT) is True
