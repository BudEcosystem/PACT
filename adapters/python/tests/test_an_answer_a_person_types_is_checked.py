"""A person's typed answer is checked before the run resumes on it (P8 wave 4).

`question.answer:` declares the SHAPE of what a person types — `approved: yes or
no`, `amount: money` — and `Question.validate` holds each field to it, saying
exactly what to type when it does not fit. That is a check on the KIND of value
and it is the only check there is.

Some answers have more to them than a kind. An account number has a checksum. A
refund has a ceiling the policy sets. A date has to be a date that happened. None
of those is expressible as a shape, and until now the only place to put them was
after the fact — the run resumes on the answer, the tool is called with it, and
the mistake is found by whatever is on the other end, having already acted.

`checked-by:` names a carried program that gets the answer first. It is the same
`program:` seam every other surface uses, and it inherits the same rules: the
host runs it, a run with nothing to run it says so rather than pretending, and
the body is in the folder so this works air-gapped.

The value it adds is not validation for its own sake. It is that the person is
told AT THE MOMENT THEY ARE STANDING THERE — the one moment a correction is
free — rather than after the run has moved on.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from pact_adapters.questions import Question, Rejected, Shape  # noqa: E402

#: A question that asks for an amount, and a carried grader that says whether the
#: amount is one this desk may give.
REFUND = {
    "questions": {
        "how-much-to-refund": {
            "description": "Asks a person how much to give back.",
            "says": "How much should we refund on this order?",
            "answer": {"amount": "money"},
            "asked-of": ["the refunds team"],
            "if-nobody-answers": "stop-and-say-so",
            "checked-by": "within-the-ceiling",
        }
    }
}


def _question(doc: dict = REFUND, name: str = "how-much-to-refund") -> Question:
    return Question.from_document(doc, name)


# ──────────────────────────────────────────────────────── the check is reached


def test_an_answer_that_passes_the_check_is_accepted() -> None:
    """The shape holds first, then the program. Both, in that order."""
    q = _question()
    seen: list[dict] = []

    def runner(name: str, args: dict) -> str:
        seen.append({"name": name, **args})
        return "ok"

    answered = q.validate({"amount": "40.00 USD"}, run_program=runner)
    assert answered.values["amount"] == "40.00 USD"
    assert seen and seen[0]["name"] == "within-the-ceiling"
    # It is handed the READ value, not the raw string — so a program never has to
    # re-parse what `Shape.read` already normalised.
    assert seen[0]["amount"] == "40.00 USD"


def test_an_answer_the_program_refuses_is_refused_with_its_words() -> None:
    """The person is told what is wrong, in the grader's own sentence.

    Not a generic "invalid": the program knows why, and the person standing there
    is the only one who can fix it.
    """
    q = _question()

    def runner(name: str, args: dict) -> str:
        return "that is more than this desk may give without a manager"

    with pytest.raises(Rejected) as raised:
        q.validate({"amount": "4000.00 USD"}, run_program=runner)
    said = " ".join(raised.value.problems)
    assert "more than this desk may give" in said


def test_the_shape_is_still_checked_first() -> None:
    """A program never sees a value that is not the shape the author declared.

    Otherwise every grader would have to re-implement the shape vocabulary, and
    two of them would disagree about what `money` is.
    """
    q = _question()

    def never(name: str, args: dict) -> str:
        raise AssertionError("a badly shaped answer must not reach the program")

    with pytest.raises(Rejected):
        q.validate({"amount": "sometime next week"}, run_program=never)


# ─────────────────────────────────────────────────────────── the honest absence


def test_a_check_with_nothing_to_run_it_does_not_silently_pass() -> None:
    """A run with no runner must not quietly accept what it could not check.

    Silently accepting is the failure mode this whole feature exists to remove,
    arriving one level up: the author wrote a check, watched it load, and it
    never ran. The answer is refused and the sentence says why, so the person is
    told rather than the guarantee being dropped.
    """
    q = _question()
    with pytest.raises(Rejected) as raised:
        q.validate({"amount": "40.00 USD"})
    said = " ".join(raised.value.problems)
    assert "within-the-ceiling" in said
    assert "could not" in said or "nothing here can run" in said


# ─────────────────────────────────────────────────────────────── nothing moved


def test_a_question_with_no_check_is_untouched() -> None:
    """Additive inertness: the overwhelming majority of questions have none."""
    plain = {
        "questions": {
            "is-this-ok": {
                "description": "Asks before money moves.",
                "says": "May we refund this?",
                "answer": {"approved": "yes or no"},
                "asked-of": ["whoever is running this agent"],
                "if-nobody-answers": "decline",
            }
        }
    }
    q = _question(plain, "is-this-ok")
    answered = q.validate({"approved": "yes"})
    assert answered.values["approved"] is True
    # And handing a runner in changes nothing for a question that names none.
    def never(name: str, args: dict) -> str:
        raise AssertionError("nothing to run")

    assert q.validate({"approved": "yes"}, run_program=never).values["approved"] is True
