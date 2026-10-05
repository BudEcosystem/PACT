"""What a runtime that replays a journal needs from PACT's questions at a deadline.

A runtime like Bud Flow does not resume from a `Suspension` record: it replays its
journal, reads each person's answer with `Question.validate`, and applies the
deadline with `Question.when_nobody_answers`. These pin the three pieces of PACT it
reads, so it never needs a copy of them:

* an escalation is asked ONCE — the escalated question stops when nobody answers,
  as `Suspension.escalate` does to the wait, instead of re-asking the same people;
* the people to escalate to are the governing RULE's (`PauseRule.escalates_to`),
  beside its deadline and its audience;
* a refusal read from an `Answer` is said in the same words `refused_in_words`
  uses, and a refusal by silence names nobody (`rulings.refused_because`).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.questions import Question, Shape  # noqa: E402
from pact_adapters.rulings import refused_because, refused_in_words  # noqa: E402
from pact_adapters.suspension import PauseRule  # noqa: E402


def an_approval(**kw: object) -> Question:
    return Question(
        name="is-this-ok",
        asks="Please check this before it happens.",
        answer={"approved": Shape.parse("yes or no"), "because": Shape.parse("text")},
        asked_of=("support-leads",),
        answer_within="30m",
        **kw,  # type: ignore[arg-type]
    )


def test_an_escalation_is_asked_once_and_then_stops_and_says_so() -> None:
    q = an_approval(if_nobody_answers="escalate", escalates_to=("support-manager",))
    nxt = q.when_nobody_answers().ask_instead
    assert nxt is not None and nxt.asked_of == ("support-manager",)
    assert (nxt.if_nobody_answers, nxt.escalates_to) == ("stop-and-say-so", ())
    assert nxt.answer_within == "30m", "the next people get the same time to answer"
    last = nxt.when_nobody_answers()
    assert last.then == "stop-and-say-so" and last.ask_instead is None
    assert last.stop_because == "nobody answered 'is-this-ok' within 30m"


def test_the_rule_carries_who_to_escalate_to() -> None:
    rule = PauseRule.from_question(
        "needs-approval",
        {
            "answer": {"approved": "yes or no"},
            "asked-of": ["support-leads"],
            "answer-within": "30m",
            "if-nobody-answers": "escalate",
            "escalates-to": ["support-manager", "finance"],
        },
    )
    assert rule.escalates_to == ("support-manager", "finance")
    assert PauseRule.from_question("needs-approval", {"answer": {"ok": "yes or no"}}).escalates_to == ()


def test_a_refusal_read_from_an_answer_is_said_as_refused_in_words_says_it() -> None:
    q = an_approval()
    said = q.validate({"approved": "no", "because": "the customer was refunded by phone"})
    given = {"email": "no", "email.because": "the customer was refunded by phone"}
    assert refused_because(q, said) == refused_in_words("email", q, given) == (
        'refused: the person answering for support-leads said no — "the customer was refunded by phone"'
    )
    assert refused_because(None, None) == "refused: a person said no"


def test_a_refusal_by_silence_names_nobody() -> None:
    silence = an_approval().when_nobody_answers().answer
    assert silence is not None and silence.from_silence
    assert refused_because(an_approval(), silence) == "refused: nobody answered within 30m"
