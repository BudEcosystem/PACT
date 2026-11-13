"""Who answered a stage that waits for people, and what they were shown.

Two things the reference workflow runtime did, found by the first shared case
with a waiting stage in it.

* `steps.<stage>.answered-by` was whatever the host put beside the answer: a
  name when one person answered, a list when several did. A stage reading it
  would fit its shape one day and not the next. On a wait it is a list,
  always; on a `decide` it is one name, because a decision is one person's.
* The person was shown nothing. A waiting stage passed its `bind:`, which it
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


def signed_off(who: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def person(question: str, shown_: dict[str, Any]) -> dict[str, Any]:
        seen.append({question: dict(shown_)})
        return {"close": True, **({"answered-by": who} if who is not None else {})}

    spec = WorkflowSpec.from_workflow(DOC, "sign-off")
    out = asyncio.run(
        run_workflow(spec, {"report": "Seat 14C will not recline."}, Callers(person=person), document=DOC)
    )
    assert out.halted == "final", out.said
    return out.answer, seen


def test_one_person_is_a_list_of_one() -> None:
    answer, _ = signed_off("dana")
    assert answer == {"close": True, "by": ["dana"]}


def test_several_people_are_listed_in_the_order_they_answered() -> None:
    answer, _ = signed_off(["lee", "dana"])
    assert answer["by"] == ["lee", "dana"]
    answer, _ = signed_off(("lee", "dana"))
    assert answer["by"] == ["lee", "dana"]


def test_who_answered_is_not_left_in_the_answer() -> None:
    answer, _ = signed_off("dana")
    assert "answered-by" not in answer


def test_the_person_is_shown_what_the_question_says_to_show() -> None:
    _, seen = signed_off("dana")
    assert seen == [{"may-we-close": {"input.report": "Seat 14C will not recline."}}]


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
