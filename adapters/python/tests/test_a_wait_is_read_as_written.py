"""A workflow's waits, ports, deadlines and value tables are read once, typed,
from the document `pact show` prints (02W §2.0, §2.8, §2.9, §2.10, §2.12).

Over #16's tree (`tests/trees/workflows-16-trial-booking/`, 02W §5.1) loaded through
the real loader, and over the one `moment` reader every time field shares.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import PortSpec, WorkflowSpec, values_of  # noqa: E402
from pact_adapters.moments import Moment, RegionLimits, Reminder, reminders  # noqa: E402
from pact_adapters.questions import Question, questions_for  # noqa: E402
from pact_adapters.suspension import (  # noqa: E402
    REASONS,
    WAITING_FOR_A_PERSON,
    WAITING_FOR_A_TIME,
    WAITING_FOR_AN_EVENT,
)
from trees import REPO, shown  # noqa: E402

TRIAL = REPO / "tests/trees/workflows-16-trial-booking"


@pytest.fixture(scope="module")
def doc() -> dict:
    return shown(TRIAL)


# ── the one moment reader ───────────────────────────────────────────────────


def test_a_moment_is_a_bare_length_or_the_group_typed() -> None:
    bare = Moment.from_written("48h")
    assert bare == Moment(after="48h")
    assert bare.from_stage and bare.sign == 1 and bare.offset == dt.timedelta(hours=48)
    before = Moment.from_written({"at": "input.starts-at", "before": "24h", "in-time-zone": "steps.tutor.zone"})
    assert before.at == "input.starts-at" and not before.from_stage
    assert before.sign == -1 and before.offset == dt.timedelta(hours=-24)
    assert before.in_time_zone == "steps.tutor.zone"
    business = Moment.from_written({"after": "20 days", "counted-in": "business-days"})
    assert business.counted_in == "business-days" and business.in_days == 20
    assert Moment.from_written({"after": "20 days"}).counted_in == "calendar-days"
    assert Moment.from_written(None) is None


def test_a_reminder_carries_its_moment_and_its_one_action() -> None:
    (nudge, handover, flow) = reminders(
        [
            {"at": "24h", "nudges": "yes"},
            {"at": "40h", "hands-over-to": ["steps.po.budget-owner-delegate"]},
            {"at": {"after": "10 days", "counted-in": "business-days"}, "runs": "remind-installer"},
        ]
    )
    assert nudge == Reminder(at=Moment(after="24h"), nudges=True)
    assert handover.hands_over_to == ("steps.po.budget-owner-delegate",) and not handover.nudges
    assert flow.runs == "remind-installer" and flow.at.in_days == 10


def test_a_deadline_that_pauses_starts_late_and_has_milestones() -> None:
    limits = RegionLimits.from_limits(
        {
            "finishes-within": {"after": "60 days", "counted-in": "business-days"},
            "starts-from": "fee-paid",
            "paused-during": ["signed", "built"],
            "milestones": [{"at": {"after": "50 days", "counted-in": "business-days"}, "tells": ["pm"]}],
            "at-once-at-most": 2,
            "when-it-runs-out": "carry-on",
        }
    )
    assert limits.finishes_within == Moment(after="60 days", counted_in="business-days")
    assert limits.starts_from == "fee-paid" and limits.paused_during == ("signed", "built")
    assert limits.milestones[0].tells == ("pm",) and limits.at_once_at_most == 2
    assert limits.when_it_runs_out == "carry-on", "a workflow's choice is kept as written"


# ── #16 through the real loader ─────────────────────────────────────────────


def test_a_port_answering_a_workflow_is_read_whole(doc: dict) -> None:
    booked = PortSpec.read(doc, "trial-booked")
    assert booked.answers == "trial-booking" and booked.kind == "event"
    assert booked.signed_with == "host/calendly-signing-secret"
    assert booked.only_when == ({"value": "input.event-type", "is": "Free Trial Lesson"},)
    assert booked.same_conversation_when == ("invitee-uri",) and booked.if_still_running == "skip"
    cancelled = PortSpec.read(doc, "trial-cancelled")
    assert cancelled.accepts == {"invitee-uri": "text"} and cancelled.if_still_running == "stop"
    assert not cancelled.undo and cancelled.then_run == ""
    calls = PortSpec.read(doc, "parent-contact-calls")
    assert calls.kind == "inbound-call" and calls.if_still_running == "queue"


def test_a_ports_timer_lines_are_read() -> None:
    port = PortSpec.read(
        {
            "ports": {
                "nightly": {
                    "every": "nights at 2",
                    "answers": "check-clinic",
                    "in-time-zone": "input.zone",
                    "if-missed": "run-when-back",
                    "per-row-of": "clinics",
                    "bind": {"clinic": "input.name"},
                    "counts-as-the-same-for": "10 minutes",
                    "ordered-by": "received-at",
                    "answer-within": "30s",
                    "undo": "yes",
                    "then-run": "tell-someone",
                }
            }
        },
        "nightly",
    )
    assert (port.in_time_zone, port.if_missed, port.per_row_of) == ("input.zone", "run-when-back", "clinics")
    assert port.bind == {"clinic": "input.name"} and port.counts_as_the_same_for == "10 minutes"
    assert (port.ordered_by, port.answer_within, port.undo, port.then_run) == (
        "received-at", "30s", True, "tell-someone",
    )


def test_a_clock_only_question_has_a_moment_and_no_answer(doc: dict) -> None:
    q = Question.asked_by(doc, "trial-booking", "day-before-the-lesson")
    assert q.asked_of == ("the-clock",) and q.answer == {}, "the clock reads nothing and answers nothing"
    assert q.answer_within == "" and q.within == Moment(
        at="input.starts-at", before="24h", in_time_zone="steps.tutor.zone"
    )


def test_a_question_reads_every_line_a_wait_has() -> None:
    q = Question.of(
        "budget-owner-approves",
        {
            "description": "x",
            "says": "Please approve this invoice.",
            "answer": {"approved": "yes or no"},
            "asked-of": ["steps.po.budget-owner"],
            "answer-within": "48h",
            "answered-by": "enough-of-them",
            "enough-is": 2,
            "asked-in": "slack #ap",
            "urgency": "urgent",
            "not-the-same-as": ["steps.po.raised-by"],
            "needs-signature": "yes",
            "starts-with": {"approved": "steps.match.clean"},
            "ordered-by": "input.invoice.due-on",
            "counts-events-from": "this-wait",
            "reminds-at": [{"at": "24h", "nudges": "yes"}],
        },
        {},
    )
    assert q.answer_within == "48h" and q.within is None
    assert (q.answered_by, q.enough_is, q.asked_in, q.urgency) == ("enough-of-them", 2, "slack #ap", "urgent")
    assert q.not_the_same_as == ("steps.po.raised-by",) and q.needs_signature
    assert q.starts_with == {"approved": "steps.match.clean"} and q.ordered_by == "input.invoice.due-on"
    assert q.counts_events_from == "this-wait" and q.reminds_at[0].nudges
    plain = Question.of("p", {"says": "?", "answer": {"approved": "yes or no"}, "asked-of": ["a"]}, {})
    assert (plain.answered_by, plain.urgency, plain.counts_events_from) == (
        "anyone", "normal", "whenever-they-arrived",
    )


def test_a_question_asked_of_people_still_says_what_an_answer_is() -> None:
    from pact_adapters.questions import Rejected

    with pytest.raises(Rejected):
        Question.of("q", {"says": "?", "asked-of": ["ap-clerks"]}, {})


def test_a_workflow_reads_the_values_its_run_reads_by_name(doc: dict) -> None:
    flow = WorkflowSpec.from_workflow(doc, "trial-booking")
    assert flow.values["trial-pipeline"].value == "Free trial"
    assert set(values_of(doc)) == {"trial-pipeline", "trial-reminder-sms", "lead-stage"}
    day = flow.stage_named("day-before")
    assert day.asks == "day-before-the-lesson" and day.nobody_answered == "consent"


def test_a_value_table_gives_its_rows() -> None:
    values = values_of(
        {
            "values": {
                "holidays": {
                    "shape": "table",
                    "rows-are": "holiday",
                    "value": [{"day": "2026-12-25", "name": "Christmas Day"}],
                }
            }
        }
    )
    assert values["holidays"].rows_are == "holiday"
    assert values["holidays"].rows == ({"day": "2026-12-25", "name": "Christmas Day"},)


def test_an_approval_rule_carries_its_first_times() -> None:
    doc = {
        "agents": {"desk": {"description": "x", "policy": "approvals"}},
        "policies": {
            "approvals": {
                "ask-a-person": [
                    {"when": [{"tool": "pay/send"}], "because": "money", "question": "ok", "first-times": 3}
                ]
            }
        },
        "tools": {"pay": {"actions": {"send": {"description": "x"}}}},
        "questions": {
            "ok": {
                "description": "x",
                "says": "OK?",
                "answer": {"approved": "yes or no"},
                "asked-of": ["leads"],
                "if-nobody-answers": "decline",
            }
        },
    }
    (rule,) = questions_for(doc, "desk").rules["pay"]
    assert rule.first_times == 3


def test_a_workflows_three_waits_are_reasons_a_run_can_wait() -> None:
    for reason in (WAITING_FOR_A_PERSON, WAITING_FOR_A_TIME, WAITING_FOR_AN_EVENT):
        assert reason in REASONS
