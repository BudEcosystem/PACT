"""Who answers a stage that waits for people, and what they are shown.

`answered-by:` on a question says how many of `asked-of:` must answer. The
count is over the ENTRIES of `asked-of:`: each is one answerer, a person or a
team one of whose members answers for it. So with `everyone` each is asked and
answers separately; one answer has one answerer.

The reference workflow runtime took one answer whatever the question said, and
kept whatever name or list of names a host put beside it. The first shared
cases written for it then delivered one answer "from" two people. Bud Agent
Flow, whose engine asks each entry, refused to build to them, and was right.

And it showed the person nothing: a waiting stage passed its `bind:`, which it
cannot write, and not the question's `shows:`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DOC = shown(REPO / "tests/conformance/trees/triaged-defects")
REPORT = {"report": "Seat 14C will not recline."}


def asked(workflow: str, answers: list[dict[str, Any]]):
    """Run `workflow`, handing its question each of `answers` in turn."""
    seen: list[dict[str, Any]] = []
    left = list(answers)

    def person(question: str, shown_: dict[str, Any]) -> dict[str, Any]:
        seen.append({question: dict(shown_)})
        return dict(left.pop(0) if len(left) > 1 else left[0])

    spec = WorkflowSpec.from_workflow(DOC, workflow)
    out = asyncio.run(run_workflow(spec, REPORT, Callers(person=person), document=DOC))
    return out, seen  # `seen`: each time the host was gone to for an answer


def yes(who: Any) -> dict[str, Any]:
    return {"close": True, "answered-by": who}


def test_a_team_is_one_answerer_and_who_answered_is_a_list_of_one() -> None:
    out, seen = asked("sign-off-by-the-team", [yes("dana")])
    assert out.halted == "final", out.said
    assert out.answer == {"close": True, "by": ["dana"]}
    assert len(seen) == 1, "the first answer decides"
    assert len(out.asked) == 1, "one entry under `asked-of:`, so one ask"


def test_everyone_is_each_of_asked_of_answering_separately() -> None:
    out, seen = asked("sign-off", [yes("dana"), yes("lee")])
    assert out.halted == "final", out.said
    assert len(seen) == 2, "two are asked of, so two answers are waited for"
    assert len(out.asked) == 2 and out.refused == []
    # In the order the answers arrived, which is not the order they are written.
    assert out.answer["by"] == ["dana", "lee"] and out.answer["close"] is True


def test_one_no_is_a_no_and_the_rest_are_not_waited_for() -> None:
    out, seen = asked("sign-off", [{"close": False, "answered-by": "dana"}, yes("lee")])
    assert out.answer == {"close": False, "by": ["dana"], "outcome": "declined"}
    assert len(seen) == 1, "lee's answer is not waited for"
    assert len(out.asked) == 2, "but lee was asked: both are, at once"


def test_the_stages_fields_are_those_of_the_answer_that_settled_it() -> None:
    """Two people each add a note beside their yes. One value has to be the
    stage's: the last yes that was needed. After a no, it is the no's."""
    out, _ = asked("sign-off", [{**yes("dana"), "note": "first"}, {**yes("lee"), "note": "second"}])
    assert out.answer["note"] == "second"
    out, _ = asked(
        "sign-off",
        [{"close": False, "note": "not yet", "answered-by": "dana"}, {**yes("lee"), "note": "second"}],
    )
    assert out.answer["note"] == "not yet"


def test_a_second_answer_from_somebody_who_answered_is_refused_and_the_wait_stays_open() -> None:
    """Refused, and said so on the result. Not quietly counted once: whoever
    handed it in would believe it had counted."""
    changed = {"close": False, "note": "On second thoughts, no.", "answered-by": "dana"}
    out, seen = asked("sign-off", [yes("dana"), changed, yes("lee")])
    assert out.answer["by"] == ["dana", "lee"] and len(seen) == 3
    assert out.refused == [
        {"question": "may-we-close", "answered-by": "dana", "why": "already-answered"}
    ]
    # And nobody changes their answer by answering again: it is still a yes.
    assert out.answer["close"] is True and out.answer["outcome"] == "answered"


def test_the_same_answer_handed_in_again_is_a_resend_and_refuses_nothing() -> None:
    """Hosts resend: a file of answers passed whole at every resume, a retry
    after a timeout. The same answer from the same person counts once."""
    out, seen = asked("sign-off", [yes("dana"), yes("dana"), yes("lee")])
    assert out.refused == [] and out.answer["by"] == ["dana", "lee"] and len(seen) == 3


def test_nobody_is_everyone_by_answering_again_and_again() -> None:
    out, seen = asked("sign-off", [yes("dana")])
    assert out.halted == "stopped"
    assert "came from somebody who had answered already" in out.said
    assert len(seen) <= 5, "it does not go on asking for ever"
    assert out.refused == [], "the same answer again is a resend, not a refusal"


def test_one_answer_naming_two_people_is_refused_and_the_wait_stays_open() -> None:
    out, _ = asked("sign-off", [yes(["lee", "dana"]), yes("dana"), yes("lee")])
    assert out.refused == [
        {"question": "may-we-close", "answered-by": ["lee", "dana"], "why": "several-people"}
    ]
    assert out.halted == "final" and out.answer["by"] == ["dana", "lee"]


def test_who_answered_is_not_left_in_the_answer() -> None:
    out, _ = asked("sign-off-by-the-team", [yes("dana")])
    assert "answered-by" not in out.answer


def test_the_person_is_shown_what_the_question_says_to_show() -> None:
    _, seen = asked("sign-off-by-the-team", [yes("dana")])
    assert seen == [{"may-the-team-close": {"input.report": "Seat 14C will not recline."}}]


def test_on_a_decide_it_stays_one_name() -> None:
    spec = WorkflowSpec.from_workflow(DOC, "shelve-checked")
    callers = Callers(
        agent=lambda name, inputs: {"shelf": "other"},
        person=lambda question, shown_: {"shelf": "other", "answered-by": "dana"},
    )
    out = asyncio.run(
        run_workflow(spec, {"note": "Invoice 14 is overdue.", "folder": "invoices"}, callers, document=DOC)
    )
    assert out.answer["who"] == "dana"
