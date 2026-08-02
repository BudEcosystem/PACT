"""What a person's answer does to a wait: cleared, refused, or nothing yet.

Eve's request to a human is, structurally, **exactly two options named approve
and deny**. PACT had only the first one working.

The concept was built. `questions.Answer.declined` exists, and
`tests/test_typed_questions.py` asserts it three times over. What was missing is
that the loop asked one question of an answer — *may the run go past this?* —
and got back a bare `True`/`False`, so **said no** and **said nothing** were the
same value, and the caller re-parked on both. Measured against
`ReferenceTransport` with three tools and `needs_approval={b, c}`: answering
`{b: approve, c: decline}` came back `suspended`, asking about `c` a second time
under a new correlation key; answering `decline` again asked a third time, under
the first key. There was no terminating answer at all. The only way a refusal
ever resolved was the timeout path — which is *silence* — so an explicit refusal
was indistinguishable from an approver who had left the company, and
`test_typed_questions.py:205` is the argument for why those two must never look
alike.

So a wait has three outcomes, not two, and they are named here rather than
recovered from a boolean at each of the three places that ask:

    cleared    a person said yes — the call happens
    refused    a person said no  — the call NEVER happens, and the run carries on
                                   knowing that, exactly as the timeout path
                                   already does at `harness.py`'s `_give_up`
    not-yet    nobody has answered, or what arrived does not fit the question —
               the run stays parked and the person is told what to type

The middle one is the whole of this module. A refusal is an **answer**: it ends
the wait, it is written into the run's own record in the person's words, and the
model reads it as the result of the call it asked for — so it can say something
sensible to the customer instead of the run stopping with nothing to show. What
a refusal is never allowed to do is let the call run, on this pass or on any
resume; that is what putting it in `already` buys, since `already` is what makes
resume exactly-once.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from .questions import APPROVED, Answer, Question, Rejected, quoted
from .suspension import GO_AHEAD, WAITING_FOR_ANOTHER_AGENT, clears


class Ruling(str, Enum):
    """What one person's answer did to one wait.

    Three members, and the third is the one Eve cannot express: its approval is
    a pair of options, so "not yet" has to be the absence of a record rather
    than a value anything can return.
    """

    CLEARED = "cleared"
    REFUSED = "refused"
    NOT_YET = "not-yet"


def where(about: str, field: str, how_many: int) -> str:
    """Where one field of one answer lives among a run's answers.

    The go-ahead keeps the name of the thing it is about, so `payments: yes`
    goes on meaning what it always meant and the `approved=` shorthand needs no
    special case. Everything else the question asks for is carried under
    `<thing>.<field>`, so two calls blocked in the same step cannot answer for
    one another — a real hazard, since a parallel batch is exactly where an
    approval gate fires.
    """
    return about if (field == APPROVED or how_many == 1) else f"{about}.{field}"


def answer_to(
    question: "Question | None", about: str, given: Mapping[str, Any]
) -> "Answer | None":
    """Read one person's answer to `question` out of a run's flat answers.

    `None` means they were never asked, or have not answered yet.
    """
    if question is None:
        return None
    how_many = len(question.answer)
    raw = {
        f: given[where(about, f, how_many)]
        for f in question.answer
        if where(about, f, how_many) in given
    }
    if not raw:
        return None
    return question.validate(raw)


def ruling(
    reason: str, about: str, question: "Question | None", given: Mapping[str, Any]
) -> Ruling:
    """What the answers this run has been given say about one wait.

    This is the widened form of the old `_cleared`, and it is a widening rather
    than a second predicate beside it on purpose: two functions that read the
    same answers and disagree about what "no" means is how a refusal comes to be
    honoured at one park and ignored at the next.

    With no authored question a wait is cleared by a yes and refused by a no,
    both read through the same [`GO_AHEAD`] shape the schema's `yes or no`
    already uses — so `decline`, `deny`, `refused`, `stop` and `n` are all a
    person saying no, because those are the words somebody actually types.

    With one, it is whatever that question calls a go-ahead — which for a
    question with no `approved` field is *having been answered at all*, because
    asking "how much should we refund?" and then asking a second time whether
    the person meant it is Eve's approve/deny pair growing back underneath. Such
    a question can therefore never be refused, which is correct and is why the
    worked example's `is-this-ok.yaml` says in its own comment that the
    `approved:` line "is the word that makes a no mean no".
    """
    if reason == WAITING_FOR_ANOTHER_AGENT:
        # A teammate's reply IS the result of the call that delegated to them,
        # not a permission, so there is no such thing as a teammate refusing.
        # Named rather than left to fall through: a specialist whose honest
        # answer begins "no, this order is outside the window" would otherwise
        # be recorded as *a person having refused the call* — a governance fact
        # about somebody who was never asked.
        return Ruling.CLEARED if clears(reason, given.get(about, "")) else Ruling.NOT_YET

    if question is None:
        said = given.get(about, "")
        if clears(reason, said):
            return Ruling.CLEARED
        try:
            return Ruling.REFUSED if GO_AHEAD.read(said) is False else Ruling.NOT_YET
        except Rejected:
            # Silence, or a word that is neither. Both leave the run parked:
            # this is the only place the three-way reading collapses back to
            # two, and it collapses towards waiting, which is the safe side.
            return Ruling.NOT_YET

    try:
        answered = answer_to(question, about, given)
    except Rejected:
        # An answer that does not fit is not an answer. The run stays parked and
        # the person is told what to type, rather than the value being dropped —
        # and, since this round, rather than a mistyped `approved:` line being
        # read as a refusal and the call cancelled on a typo.
        return Ruling.NOT_YET
    if answered is None:
        return Ruling.NOT_YET
    if answered.approved:
        return Ruling.CLEARED
    return Ruling.REFUSED if answered.declined else Ruling.NOT_YET


def refused_in_words(
    about: str, question: "Question | None", given: Mapping[str, Any]
) -> str:
    """What the record says happened to a call a person refused.

    Deliberately the same opening word as the timeout path's
    `refused: nobody answered in time`, and deliberately a different sentence
    after it. Both are refusals and both belong under `refused:`; what must stay
    tellable apart is *who* refused, because a record saying a support lead
    turned down a refund they were never shown is the exact mis-statement T7
    forbids — and it is the one `test_typed_questions.py:205` already argues for
    at the level of a single answer.

    Who is read off the question they were actually put (`asked-of:`), and their
    reason off the `because:` they typed — two authored lines that, before this,
    were validated on every answer and read by nothing in `src/`.

    The wording is *"the person answering for support-leads"* and not
    *"support-leads said no"*, and the difference is not fussiness. `asked-of:`
    is the audience a question was PUT to; a `Resumption` carries a correlation
    key and values and no identity at all, so this run cannot know which person
    typed the answer, or even that they were one of them. Writing the shorter
    sentence would put a claim in the permanent record that nothing here
    checked, which is the same T7 mis-statement that makes a timeout and a
    refusal have to read differently in the first place. Verifying the answerer
    needs an identity on the resumption, and there is none to read.

    The reason is passed through `quoted` like every other value a person or a
    customer supplied: it lands in the transcript the model reads next, so
    control characters and unbounded length are the same hazard here that
    Y18/AD-46 records for an approver's screen, and one renderer for both is one
    fewer place to forget.
    """
    asked_of = question.asked_of if question is not None else ()
    who = f"the person answering for {', '.join(asked_of)}" if asked_of else "a person"
    try:
        answered = answer_to(question, about, given)
    except Rejected:  # pragma: no cover - only reached if the caller mis-orders
        answered = None
    because = answered.because if answered is not None else ""
    return f"refused: {who} said no" + (f" — {quoted(because)}" if because else "")
