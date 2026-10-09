"""One condition reader (02W §2.6): approval rules, routing rules, `until:` and
`only-when:` all go through `conditions.holds`.

The six words, the four kinds of comparand, `now` supplied by the caller so a
replay decides what the first pass decided, and a date compared in the value's
own zone across a clock change — the risk this package was asked to settle
before the rest was written.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import questions  # noqa: E402
from pact_adapters.conditions import (  # noqa: E402
    ABSENT,
    Chosen,
    RouteRule,
    all_hold,
    choose,
    holds,
)

LONDON = "Europe/London"
#: Noon on the Saturday before the clocks go back (25 October 2026, 02:00 BST).
BEFORE_THE_CHANGE = dt.datetime(2026, 10, 24, 12, 0, tzinfo=ZoneInfo(LONDON))


def test_a_day_is_the_same_time_tomorrow_in_the_values_zone_across_a_clock_change() -> None:
    """`{now-plus: 1 day}` from noon BST is noon GMT the next day: 25 hours on
    the clock. `24h` is 24 hours. A value at 11:30 GMT falls between the two."""
    value = "2026-10-25T11:30:00+00:00"
    assert holds({"less-than": {"now-plus": "1 day"}}, value, now=BEFORE_THE_CHANGE, zone=LONDON) is True
    assert holds({"less-than": {"now-plus": "24h"}}, value, now=BEFORE_THE_CHANGE, zone=LONDON) is False
    # The same moment in UTC, read in the value's zone, gives the same answer.
    utc = BEFORE_THE_CHANGE.astimezone(dt.UTC)
    assert holds({"less-than": {"now-plus": "1 day"}}, value, now=utc, zone=LONDON) is True


def test_a_date_is_compared_by_the_date_in_the_zone() -> None:
    now = BEFORE_THE_CHANGE
    assert holds({"less-than": {"now-plus": "1 day"}}, "2026-10-25", now=now, zone=LONDON) is False
    assert holds({"less-than": {"now-plus": "2 days"}}, "2026-10-25", now=now, zone=LONDON) is True
    assert holds({"more-than": {"now-minus": "1 day"}}, "2026-10-24", now=now, zone=LONDON) is True
    # Late evening in Chicago is already tomorrow in UTC; the zone decides the date.
    chicago = dt.datetime(2026, 3, 7, 23, 0, tzinfo=ZoneInfo("America/Chicago"))
    assert holds({"is": {"value": "today"}}, "2026-03-07", read=lambda _: chicago, zone="America/Chicago") is True


def test_now_is_the_callers_so_a_replay_decides_the_same() -> None:
    line = {"less-than": {"now-plus": "14 days"}}
    due = "2026-11-01"
    first = holds(line, due, now=BEFORE_THE_CHANGE, zone=LONDON)
    earlier = holds(line, due, now=BEFORE_THE_CHANGE - dt.timedelta(days=30), zone=LONDON)
    assert first is True and earlier is False
    assert holds(line, due, now=BEFORE_THE_CHANGE, zone=LONDON) is first
    assert holds(line, due) is None, "with no `now` it cannot be told, and the caller decides"


def test_a_value_with_no_zone_is_read_in_the_zone_and_is_no_moment_without_one() -> None:
    line = {"more-than": {"now-plus": "1h"}}
    assert holds(line, "2026-10-24T14:00:00", now=BEFORE_THE_CHANGE, zone=LONDON) is True
    assert holds(line, "2026-10-24T14:00:00", now=BEFORE_THE_CHANGE) is None


def test_the_six_words() -> None:
    assert holds({"is": "enterprise"}, "Enterprise") is True
    assert holds({"is-one-of": ["enterprise", "government"]}, "government") is True
    assert holds({"is-one-of": ["enterprise", "government"]}, "small") is False
    assert holds({"more-than": "200 USD"}, "210.00 USD") is True
    assert holds({"less-than": "5000 USD"}, "4200.00 USD") is True
    assert holds({"less-than": 0.85}, 0.9) is False
    assert holds({"more-than": "80%"}, 85) is True
    assert holds({"contains-any-of": ["refund", "chargeback"]}, "I want a REFUND now") is True
    assert holds({"contains-any-of": ["refund"]}, ["billing", "Refund"]) is True
    assert holds({"contains-any-of": ["refund"]}, ["refunds"]) is False
    assert holds({"is-empty": "yes"}, ABSENT) is True
    assert holds({"is-empty": "yes"}, "  ") is True
    assert holds({"is-empty": "yes"}, []) is True
    assert holds({"is-empty": "no"}, ["x"]) is True
    assert holds({"is": "yes"}, True) is True
    assert holds({"is": True}, "no") is False


def test_a_value_that_is_not_there_holds_nothing_but_is_empty() -> None:
    for line in ({"is": "x"}, {"more-than": 1}, {"less-than": 1}, {"contains-any-of": ["x"]}):
        assert holds(line, ABSENT) is False, line


def test_what_cannot_be_told_is_said_and_never_guessed() -> None:
    assert holds({"more-than": "NaN USD"}, "300 USD") is None
    assert holds({"more-than": "200 USD"}, "300 EUR") is None, "two currencies"
    assert holds({"less-than": {"value": "steps.po.total"}}, "10 USD") is None, "nothing reads the binding"
    assert holds({"less-than": {"value": "steps.po.total"}}, "10 USD", read=lambda _: "20 USD") is True


def test_every_line_must_hold_and_or_is_two_rules() -> None:
    values = {"input.total": "4000.00 USD", "steps.match.result": "matched", "steps.tax.note": ""}
    read = lambda b: values.get(b, ABSENT)  # noqa: E731
    both = [
        {"value": "input.total", "less-than": "5000 USD"},
        {"value": "steps.match.result", "is": "matched"},
    ]
    assert all_hold(both, read) is True
    assert all_hold([*both, {"value": "steps.tax.note", "is-empty": "no"}], read) is False
    assert all_hold([{"value": "input.total", "more-than": "NaN USD"}], read) is None
    assert all_hold([{"value": "input.total", "more-than": "NaN USD"}, {"value": "input.nothing", "is": "x"}], read) is False


def test_the_first_rule_that_holds_chooses_and_an_unreadable_one_decides_nothing() -> None:
    values = {"input.total": "40000.00 USD", "steps.match.result": "matched"}
    read = lambda b: values.get(b, ABSENT)  # noqa: E731
    tiers = [
        RouteRule.from_written(
            {
                "when": [
                    {"value": "input.total", "less-than": "5000 USD"},
                    {"value": "steps.match.result", "is": "matched"},
                ],
                "choose": "auto",
            }
        ),
        RouteRule.from_written(
            {"when": [{"value": "input.total", "less-than": "50000 USD"}], "choose": "owner", "because": "Under the controller's line."}
        ),
        RouteRule.from_written({"choose": "owner-then-controller"}),
    ]
    assert choose(tiers, read) == Chosen("owner", "Under the controller's line.")
    values["input.total"] = "90000.00 USD"
    assert choose(tiers, read).label == "owner-then-controller"
    values["input.total"] = "90000.00 EUR"
    undecided = choose(tiers, read)
    assert undecided.label is None and "could not be read" in undecided.undecided
    assert choose(tiers[1:2], lambda _: "90000 USD") == Chosen(None), "none held: passed on"


def test_an_approval_gate_reads_through_the_same_function() -> None:
    """The gate keeps its own halves (which action, what `inspects:` allows) and
    asks `conditions.holds` the comparison, so the new words work in a policy."""
    under = {"tool": "orders/ship", "arg": "note", "contains-any-of": ["urgent"]}
    assert questions._atom_stops(under, {"note": "URGENT please"}) is True
    assert questions._atom_stops(under, {"note": "whenever"}) is False
    blank = {"tool": "orders/ship", "arg": "po", "is-empty": "yes"}
    assert questions._atom_stops(blank, {"po": ""}) is True
    assert questions._atom_stops(blank, {"po": "PO-7"}) is False
    small = {"tool": "orders/ship", "arg": "amount", "less-than": "10 USD"}
    assert questions._atom_stops(small, {"amount": "5 USD"}) is True
    assert questions._atom_stops(small, {"amount": "50 USD"}) is False
    # A comparison relative to now has no journaled clock in a gate: it stops and asks.
    soon = {"tool": "orders/ship", "arg": "by", "less-than": {"now-plus": "2 days"}}
    assert questions._atom_stops(soon, {"by": "2026-10-25"}) is True


def test_a_null_argument_stops_the_gate_and_only_a_missing_one_lets_it_by() -> None:
    """A call that carries `amount: null` is not a call with no amount: a tool
    may read null as "refund in full", so the gate cannot tell and asks. Only an
    argument the call does not carry means "not this call"."""
    for word in ("more-than", "less-than"):
        atom = {"tool": "payments/refund", "arg": "amount", word: "200 USD"}
        assert questions._atom_stops(atom, {"amount": None}) is True, word
        assert questions._atom_stops(atom, {}) is False, word
    assert holds({"is-empty": "yes"}, None) is True
    for line in ({"is": "x"}, {"is-one-of": ["x"]}, {"more-than": 1}, {"contains-any-of": ["x"]}):
        assert holds(line, None) is None, line


def test_a_time_of_day_is_compared_as_a_time() -> None:
    """Never by its hour: 14:50 is after 14:30, 09:05 before 09:30, against a
    written time or another time (a `time` value as Python holds it)."""
    assert holds({"more-than": "14:30"}, "14:50") is True
    assert holds({"less-than": "09:30"}, "09:05") is True
    assert holds({"less-than": "09:30"}, "9:45") is False
    assert holds({"more-than": "14:30"}, dt.time(14, 30, 1)) is True
    assert holds({"is": "14:30"}, "14:30:00") is True
    cutoff = {"less-than": {"value": "input.cutoff"}}
    assert holds(cutoff, "16:59", read=lambda _: dt.time(17, 0)) is True
    assert holds(cutoff, "17:01", read=lambda _: "17:00") is False
    # A time of day has no date: against one, or a number, it cannot be told.
    assert holds({"more-than": "2026-10-09"}, "14:30") is None
    assert holds({"more-than": 14}, "14:30") is None
    assert holds({"more-than": "14:30"}, "25:00") is None


def test_a_gate_reads_a_moment_with_no_offset_in_the_workspace_zone() -> None:
    """Models write a date and time without its offset. The gate reads it in
    the workspace's `time-zone:`, so it can be held against a date — and with
    no zone it cannot be told and stops."""
    atom = {"tool": "orders/ship", "arg": "by", "less-than": "2026-10-09"}
    late = {"by": "2030-01-01T10:00:00"}
    assert questions._atom_stops(atom, late, zone="America/Chicago") is False
    assert questions._atom_stops(atom, {"by": "2026-10-08T23:30:00"}, zone="America/Chicago") is True
    assert questions._atom_stops(atom, late) is True, "no zone: cannot be told, so it stops"
    rule = questions.Rule(question=questions.Question.approval(), when=(atom,), gates=True)
    gate = questions.Gate({"orders": (rule,)}, zone="America/Chicago")
    assert gate.waits_for("orders", late) == ()
    assert questions.Gate({"orders": (rule,)}).waits_for("orders", late) != ()
