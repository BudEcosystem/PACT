"""A stage that an agent answered says how the agent ended.

An agent may have limits, and may be told to answer with what it has when it
reaches one (`when-it-runs-out: answer-with-what-it-has`). The stage that
called it takes that answer and goes on: it IS an answer. But the workflow
could not tell it from a finished one. An author who wanted a part-done answer
looked at before it went to a customer had nothing to write.

`steps.<stage>.ended` is `ran-out` for an agent that reached a limit and
`finished` for one that did not: the word a `repeat` already has, with the same
`ran-out`. It is a word and not a new exit under `then:`, for three reasons.
The stage did answer, and `answered` is the true name of how it ended. A word
can be SHOWN to a person and handed back by the workflow, which an exit cannot.
And nothing that exists changes: a workflow that does not read it runs as it
did. Branching on it is a `decide` with a written rule, which is where every
other "depending on what happened" in a workflow is written.

A host hands the answer back wrapped (`RanOut`); these hold what the runtime
does with it. The shared cases hold the same on `triaged-defects/draft-once`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import Callers, Parked, RanOut, run_workflow  # noqa: E402
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DOC = shown(REPO / "tests/conformance/trees/triaged-defects")
DRAFT = {"draft": "Gate 4 opens on", "good": False}


def draft_once(answer: Any, person=None):
    asked: list[dict[str, Any]] = []

    def ask(question: str, shown_: dict[str, Any]) -> dict[str, Any]:
        asked.append(dict(shown_))
        return {"send": True}

    spec = WorkflowSpec.from_workflow(DOC, "draft-once")
    callers = Callers(agent=lambda name, inputs: answer, person=person or ask)
    out = asyncio.run(run_workflow(spec, {"brief": "A notice."}, callers, document=DOC))
    return out, asked


def test_an_answer_given_on_running_out_is_taken_and_the_stage_says_ran_out() -> None:
    out, asked = draft_once(RanOut(DRAFT))
    assert out.halted == "final", out.said
    # The answer is the agent's, unwrapped: a binding reads its fields as ever.
    assert out.steps["write"] == DRAFT
    assert out.answer == {"draft": "Gate 4 opens on", "ended": "ran-out", "went": "part-done"}
    # A rule read the word and sent the draft to a person, who was shown it.
    assert out.trace == ["write", "check", "look", "reply"]
    assert asked == [{"steps.write.draft": "Gate 4 opens on", "steps.write.ended": "ran-out"}]
    assert out.because["check"] == "The drafter ran out before it finished."


def test_an_agent_that_did_not_run_out_is_finished_and_nobody_looks() -> None:
    out, asked = draft_once(dict(DRAFT))
    assert out.answer["ended"] == "finished" and out.answer["went"] == "whole"
    assert out.trace == ["write", "check", "reply"] and asked == []


def test_a_label_from_an_agent_that_ran_out_stands_and_the_decide_says_ran_out() -> None:
    spec = WorkflowSpec.from_workflow(DOC, "assign-only")
    given = {"kind": "engine", "summary": "Oil pressure low."}

    def run(answer: Any):
        callers = Callers(agent=lambda name, inputs: answer)
        return asyncio.run(run_workflow(spec, given, callers, document=DOC))

    assert run(RanOut({"team": "powerplant"})).answer == {"team": "powerplant", "ended": "ran-out"}
    assert run({"team": "powerplant"}).answer == {"team": "powerplant", "ended": "finished"}


def test_a_stage_that_calls_a_tool_has_no_such_word() -> None:
    # Only an agent has limits of its own to run out of.
    doc = {
        "tools": {"ledger": {"description": "A ledger.", "actions": {"look": {"description": "Look."}}}},
        "workflows": {
            "w": {
                "description": "Look once.", "accepts": {"x": "text"}, "starts-at": "look",
                "steps": {
                    "look": {"does": "call", "call": "ledger/look", "then": {"answered": "say"}},
                    "say": {"does": "answer", "bind": {"how": "steps.look.ended", "what": "steps.look.outcome"}},
                },
            }
        },
    }
    spec = WorkflowSpec.from_workflow(doc, "w")
    out = asyncio.run(
        run_workflow(spec, {"x": "1"}, Callers(tool=lambda t, a, i: {"seen": True}), document=doc)
    )
    assert out.answer == {"what": "answered"}, "`.ended` reads nothing there; `.outcome` is on every stage"


# ── a called workflow that waits ─────────────────────────────────────────────


def fix_and_close(person):
    spec = WorkflowSpec.from_workflow(DOC, "fix-and-close")
    callers = Callers(agent=lambda name, inputs: {"kind": "cabin", "summary": "A seat."}, person=person)
    return asyncio.run(run_workflow(spec, {"report": "Seat 14C."}, callers, document=DOC))


def test_a_run_that_calls_a_workflow_that_waits_is_waiting_too() -> None:
    # It was `stopped`: "the workflow 'sign-off-by-the-team' parked", which
    # every caller read as a failure.
    out = fix_and_close(None)
    assert out.halted == "parked" and out.why == ""
    # Where THIS run waits, which is where a host resumes it; and whose question.
    assert out.parked_at == "close" and out.question == "may-the-team-close"
    assert out.said == (
        "waiting on 'may-the-team-close' at 'close' (asked inside 'sign-off-by-the-team/approve')"
    )


def test_a_host_that_parks_on_the_called_workflows_question_parks_the_caller_too() -> None:
    def later(question: str, shown_: dict[str, Any]):
        raise Parked(question, "approve")

    out = fix_and_close(later)
    assert out.halted == "parked" and out.parked_at == "close"
    # The person WAS asked this time, and the caller's record says so.
    assert [a["question"] for a in out.asked] == ["may-the-team-close"]


def test_once_the_called_workflow_is_answered_the_caller_goes_on() -> None:
    out = fix_and_close(lambda q, s: {"close": True, "answered-by": "dana"})
    assert out.halted == "final" and out.answer == {"close": True, "kind": "cabin"}
    assert [a["question"] for a in out.asked] == ["may-the-team-close"]
