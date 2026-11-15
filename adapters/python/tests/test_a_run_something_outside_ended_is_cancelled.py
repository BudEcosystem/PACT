"""How a workflow's run ends, in a word nobody has to read prose to tell apart.

A run ended in one of three words: `final`, `parked`, `stopped`. Two things
were missing, and both made a dashboard lie.

**A run something OUTSIDE it ended had no word.** A port whose arrival has the
run's key and says `if-still-running: stop` or `cancel-previous`, or a person
at the host's console, ends a run that did nothing wrong and reached no exit of
its own. Counted as `stopped`, a week of customers withdrawing their tickets
reads as a week of failures. It is `cancelled`.

**`stopped` was one word for eight things.** A person's no, a decision nobody
could make, a server that was down and a ceiling that was reached all ended
`stopped`, told apart only by `said`, which is prose. `why` is the one word.

And the reference runtime got one of them wrong: a no, or silence, with no
exit written for it ENDED THE BLOCK instead of stopping the run
(`outcome.declined`: "a no is never quietly carried past"). A workflow that
gives nothing then finished `final` after a person had said no.

The shared cases (`tests/conformance/workflows.json`, on
`trees/booked-visits`) hold what another runtime can replay. These hold the
rest: a host ending a run, an undo that fails, an ending inside a loop that
carries on past failures, and each reason.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import (  # noqa: E402
    STOPPED_BECAUSE,
    Callers,
    NobodyAnswered,
    Stopped,
    run_workflow,
)
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
VISITS = shown(REPO / "tests/conformance/trees/booked-visits")
DEFECTS = shown(REPO / "tests/conformance/trees/triaged-defects")
VISIT = {"visit": "V-204", "customer": "Ms Okafor"}


class Office:
    """The host's side of `booked-visits`: every call made, in order."""

    def __init__(self, broken: str = "") -> None:
        self.calls: list[str] = []
        self.started: list[tuple[str, dict[str, Any]]] = []
        self.broken = broken

    def tool(self, tool: str, action: str, inputs: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(f"{tool}/{action}")
        if f"{tool}/{action}" == self.broken:
            raise RuntimeError("the calendar is down")
        return {}

    def start(self, workflow: str, inputs: dict[str, Any]) -> None:
        self.started.append((workflow, dict(inputs)))


def book(office: Office, ended=None, start: bool = True, person=None):
    callers = Callers(
        tool=office.tool,
        person=person or (lambda q, s: {"confirmed": True}),
        start=office.start if start else None,
    )
    spec = WorkflowSpec.from_workflow(VISITS, "book-visit")
    return asyncio.run(run_workflow(spec, VISIT, callers, document=VISITS, ended=ended))


def at(stage: str, by: dict[str, Any]):
    return lambda here: dict(by) if here == stage else None


# ── cancelled ────────────────────────────────────────────────────────────────


def test_a_run_a_port_ends_is_cancelled_and_never_stopped() -> None:
    office = Office()
    out = book(office, at("confirm", {"port": "visit-called-off"}))
    assert out.halted == "cancelled" and out.why == ""
    assert out.cancelled_by == {"port": "visit-called-off"}
    # The stage it arrived at never began: nobody was asked.
    assert out.trace == ["hold", "file"] and out.asked == []
    # `undo: yes` on the port: newest first.
    assert office.calls == [
        "calendar/hold-slot", "files/open-file", "files/close-file", "calendar/release-slot",
    ]
    # `then-run:`, with the cancelled run's input, as much as that workflow takes.
    assert office.started == [("tell-the-clinic", {"visit": "V-204"})]
    assert out.answer == {}, "a cancelled run hands back nothing"
    assert out.said == (
        "Cancelled by the port `visit-called-off`. What it did was undone, newest first: "
        "file, hold. `tell-the-clinic` was started after it."
    )


def test_the_same_run_with_no_arrival_is_not_cancelled() -> None:
    # The control: `ended` is asked before every stage and says nothing.
    asked_at: list[str] = []
    out = book(Office(), lambda here: asked_at.append(here))
    assert out.halted == "final" and out.cancelled_by == {} and out.why == ""
    assert asked_at == ["hold", "file", "confirm", "reply"]


def test_a_host_that_ends_a_run_itself_says_who_and_whether_to_undo() -> None:
    office = Office()
    out = book(office, at("confirm", {"by": "an operator", "undo": True}))
    assert out.halted == "cancelled" and out.cancelled_by == {"by": "an operator"}
    assert office.calls[-2:] == ["files/close-file", "calendar/release-slot"]
    assert out.said.startswith("Cancelled by an operator. What it did was undone")
    kept = Office()
    out = book(kept, at("confirm", {"by": "an operator"}))
    assert kept.calls == ["calendar/hold-slot", "files/open-file"], "nothing said undo"
    assert out.said == "Cancelled by an operator."


def test_an_undo_that_fails_is_said_and_the_run_is_cancelled_all_the_same() -> None:
    office = Office(broken="calendar/release-slot")
    out = book(office, at("confirm", {"port": "visit-called-off"}))
    assert out.halted == "cancelled"
    assert "undone, newest first: file." in out.said
    assert "Could not be undone: hold (calendar/release-slot: the calendar is down)." in out.said
    # And in the channel a host reads for what was written and not carried out.
    assert any(u.startswith("undo:") and "take those back by hand" in u for u in out.unenforced)


def test_a_follow_up_nothing_here_can_start_is_said_and_not_dropped() -> None:
    out = book(Office(), at("confirm", {"port": "visit-called-off"}), start=False)
    assert out.started == [{"workflow": "tell-the-clinic", "given": {"visit": "V-204"}}]
    assert any(u.startswith("then-run: `tell-the-clinic` was to start") for u in out.unenforced)
    assert "was started after it" not in out.said


def test_an_ending_inside_a_loop_that_carries_on_past_failures_still_ends_the_run() -> None:
    # `if-someone-fails: carry-on` carries on past a branch that FAILED. The
    # run being ended is not a branch failing, and nothing carries on past it.
    doc = {
        "agents": {"reader": {"description": "Reads.", "instructions": "Read."}},
        "workflows": {
            "read-all": {
                "description": "Read each page.",
                "accepts": {"pages": "list of text"},
                "starts-at": "every",
                "steps": {
                    "every": {
                        "does": "each",
                        "over": "input.pages",
                        "limits": {"items-at-most": 5, "at-once-at-most": 1},
                        "teamwork": {"if-someone-fails": "carry-on"},
                        "starts-at": "read",
                        "steps": {"read": {"does": "call", "call": "reader", "bind": {"message": "item"}}},
                        "then": {"answered": "after"},
                    },
                    "after": {"does": "call", "call": "reader", "bind": {"message": "input.pages"}},
                },
            }
        },
    }
    read: list[Any] = []
    seen = {"n": 0}

    def ended(here: str):
        if here == "every/read":
            seen["n"] += 1
            if seen["n"] == 2:
                return {"by": "an operator"}
        return None

    spec = WorkflowSpec.from_workflow(doc, "read-all")
    callers = Callers(agent=lambda name, inputs: read.append(inputs["message"]) or {"ok": True})
    out = asyncio.run(run_workflow(spec, {"pages": ["a", "b", "c"]}, callers, document=doc, ended=ended))
    assert out.halted == "cancelled", (out.halted, out.said)
    assert read == ["a"], "the second page's stage never began, and nothing after it ran"


# ── why a stopped run stopped ────────────────────────────────────────────────


def sign_off(person):
    spec = WorkflowSpec.from_workflow(DEFECTS, "sign-off-by-the-team")
    return asyncio.run(
        run_workflow(spec, {"report": "r"}, Callers(person=person), document=DEFECTS)
    )


def test_a_no_with_no_exit_written_for_it_stops_the_run() -> None:
    # It ended the block, and the run was then told its answer "does not fit".
    out = sign_off(lambda q, s: {"close": False, "answered-by": "dana"})
    assert (out.halted, out.why) == ("stopped", "declined")
    assert "the answer was no" in out.said and "`declined:` exit" in out.said
    assert out.answer == {}


def test_silence_with_no_exit_written_for_it_stops_the_run() -> None:
    def nobody(question: str, shown_: dict[str, Any]):
        raise NobodyAnswered(question)

    out = sign_off(nobody)
    assert (out.halted, out.why) == ("stopped", "nobody-answered")
    assert "nobody answered in time" in out.said


def test_a_no_with_an_exit_written_for_it_goes_there_and_nothing_stops() -> None:
    # The control: `sign-off` writes `declined: reply`.
    spec = WorkflowSpec.from_workflow(DEFECTS, "sign-off")
    out = asyncio.run(
        run_workflow(
            spec, {"report": "r"},
            Callers(person=lambda q, s: {"close": False, "answered-by": "dana"}),
            document=DEFECTS,
        )
    )
    assert out.halted == "final" and out.why == "" and out.answer["outcome"] == "declined"


def _one_stage(stage: dict[str, Any], **more: Any) -> dict[str, Any]:
    return {
        "agents": {"helper": {"description": "Helps.", "instructions": "Help."}},
        "workflows": {
            "w": {"description": "One stage.", "accepts": {"x": "text"}, "starts-at": "s",
                  "steps": {"s": stage}, **more}
        },
    }


def _why(doc: dict[str, Any], callers: Callers, inputs: dict[str, Any] | None = None):
    spec = WorkflowSpec.from_workflow(doc, "w")
    out = asyncio.run(run_workflow(spec, inputs or {"x": "1"}, callers, document=doc))
    return out.halted, out.why


def test_each_reason_a_run_stops_has_its_word() -> None:
    def fails(name: str, inputs: dict[str, Any]):
        raise RuntimeError("down")

    call = {"does": "call", "call": "helper", "bind": {"message": "input.x"}}
    # An exit the author wrote.
    said_so = _one_stage({**call, "then": {"answered": "stop-and-say-so"}})
    assert _why(said_so, Callers(agent=lambda n, i: {})) == ("stopped", "said-so")
    # A call that failed, with no plan for it.
    assert _why(_one_stage(call), Callers(agent=fails)) == ("stopped", "a-call-failed")
    # Nobody on the ladder decided.
    decide = _one_stage(
        {"does": "decide", "chooses-between": {"a": "done", "b": "done"}, "by": [{"agent": "helper"}]}
    )
    assert _why(decide, Callers(agent=lambda n, i: {"label": "not-sure"})) == ("stopped", "nobody-decided")
    # A ceiling whose reaching stops.
    each = _one_stage(
        {"does": "each", "over": "input.x", "limits": {"items-at-most": 1}, "starts-at": "i",
         "steps": {"i": call}},
    )
    assert _why(each, Callers(agent=lambda n, i: {}), {"x": ["a", "b"]}) == ("stopped", "reached-a-limit")
    # What it would hand back is not what it says it gives.
    gives = _one_stage({"does": "answer", "bind": {}}, **{"answers-with": {"total": "money"}})
    assert _why(gives, Callers()) == ("stopped", "does-not-fit")
    # Nothing here can do what is written.
    assert _why(_one_stage(call), Callers()) == ("stopped", "not-runnable")


def test_the_words_are_a_closed_set_and_a_stop_cannot_be_given_another() -> None:
    assert len(STOPPED_BECAUSE) == len(set(STOPPED_BECAUSE)) == 8
    with pytest.raises(AssertionError):
        Stopped("why", "because-i-said")
    assert Stopped("why").because == "not-runnable"
