"""A person can say no, and the run ends.

Eve's request to a human is structurally **exactly two options named approve and
deny**. PACT had only the first one working — and not for want of the concept:
`questions.Answer.declined` has existed as long as `Answer` has, and
`test_typed_questions.py` asserts it three times over. What was missing is that
the loop asked one question of an answer, *may the run go past this?*, and got a
bare `True`/`False` back, so **said no** and **said nothing** were one value.

Measured against `ReferenceTransport`, three tools `a b c`, `needs_approval =
{b, c}`:

    park 1   suspended needs-approval  key=551eea1c  asks=[b, c]
    answer   {b: approve, c: decline}
    park 2   suspended needs-approval  key=d65c28ef  asks=[c]      <- asked again
    answer   {c: decline}
    park 3   suspended needs-approval  key=551eea1c                <- and again
    ran      ['a']

There was no terminating answer. An explicit refusal was indistinguishable from
an approver who had left the company, and the only thing that ever resolved one
was the deadline — which is silence, and which
`test_typed_questions.py:205` already argues must never look like a person's no.

Three guarantees, one per section below:

  (i)   a person who declines gets a run that ends, not a run that asks again;
  (ii)  a declined call is never executed, on this pass or on any resume;
  (iii) the run's own record says a person refused, and says it differently from
        nobody having answered in time.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.questions import Question, Shape  # noqa: E402
from pact_adapters.rulings import Ruling, refused_in_words, ruling  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import (  # noqa: E402
    NEEDS_APPROVAL,
    WAITING_FOR_ANOTHER_AGENT,
    PauseRule,
    Resumption,
    Suspension,
)
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "refund-desk"

THREE = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Read the ticket, refund, and tell the customer.",
    tools=(
        ToolSpec("zendesk", "read the ticket"),
        ToolSpec("payments", "issue a refund"),
        ToolSpec("email", "write to the customer"),
    ),
)

#: Two of the three wait for a person. A batch is where a gate actually fires,
#: and it is the only shape in which "yes to this, no to that" can be said.
GATED = frozenset({"payments", "email"})


class Counter:
    """Every real tool invocation, in order. Exactly-once is the whole point."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def tools(self) -> dict:
        def one(name: str):
            def fn(_args):
                self.calls.append(name)
                return f"{name} done"

            return fn

        return {n: one(n) for n in ("zendesk", "payments", "email")}


def batch() -> Script:
    return Script([
        Turn("Reading the ticket, refunding, and writing to the customer.", (
            ToolCall("zendesk", {"ticket-id": "T-1"}),
            ToolCall("payments", {"amount": 40}),
            ToolCall("email", {"to": "customer"}),
        )),
        Turn("All done."),
    ])


def park(counter: Counter, spec: AgentSpec = THREE):
    return asyncio.run(
        run(spec, ReferenceTransport(batch()), "refund me", counter.tools(),
            needs_approval=GATED, now=0.0)
    )


def resume(counter: Counter, parked: Suspension, said: dict[str, str],
           spec: AgentSpec = THREE, now: float = 1.0):
    """Come back through a real process boundary, carrying one person's answer.

    The answer is built as a `Resumption` rather than through
    `Suspension.answer()` because some of these say nothing about one of the
    things asked, and `answer()` deliberately refuses an incomplete reply. What
    is under test is what the LOOP does with what it is given, including being
    given less than it asked for.
    """
    revived = Suspension.from_json(parked.to_json())
    return asyncio.run(
        run(spec, ReferenceTransport(batch()), "refund me", counter.tools(),
            needs_approval=GATED, resume=revived,
            answer=Resumption(revived.correlation_key, said), now=now)
    )


def refusals_in(result) -> list[str]:
    """Every tool result in the run's own trace that records a refusal."""
    return [r for step in result.trace() for r in step["results"] if r.startswith("refused:")]


# ─────────────── (i) a decline ends the run, rather than asking the same again


def test_a_person_who_declines_gets_a_run_that_ends_rather_than_one_that_asks_again() -> None:
    """The defect, stated as the guarantee it was missing.

    Before this, answering `decline` came back `suspended` and asked about the
    same call under a new correlation key; answering it again asked a third
    time. A refusal is an answer — it ends the wait.
    """
    counter = Counter()
    first = park(counter)
    assert first.halted == "suspended" and first.suspension is not None

    after = resume(counter, first.suspension, {"payments": "approve", "email": "decline"})

    assert after.halted == "final", (
        f"a run a person answered came back {after.halted!r}: a refusal that "
        "re-parks is indistinguishable from silence"
    )
    assert after.suspension is None, "and there is nothing left to answer"


def test_a_run_every_call_of_which_was_refused_still_finishes() -> None:
    """The all-no case, which is where a fix that only handles "some yes, some
    no" would still hang: nothing was cleared, so nothing carried the run on."""
    counter = Counter()
    first = park(counter)
    after = resume(counter, first.suspension, {"payments": "decline", "email": "decline"})

    assert after.halted == "final", after.halted
    assert counter.calls == ["zendesk"], f"only the ungated call ever ran: {counter.calls}"
    assert len(refusals_in(after)) == 2, refusals_in(after)


def test_declining_one_call_still_waits_for_the_one_nobody_has_answered() -> None:
    """A refusal ends ITS OWN wait and nobody else's.

    The dangerous over-correction is a decline that releases the batch: a person
    who refused the email and has said nothing yet about the refund must not
    find the refund issued because of the word they typed about something else.
    """
    counter = Counter()
    first = park(counter)
    after = resume(counter, first.suspension, {"email": "decline"})

    assert after.halted == "suspended", "the unanswered refund still waits"
    assert [e.name for e in after.suspension.asks] == ["payments"], (
        f"and it asks only about what is left: {[e.name for e in after.suspension.asks]}"
    )
    assert "email" not in counter.calls


# ─────────────────── (ii) a declined call is never executed, on any resume


def test_a_declined_call_is_never_executed_on_this_pass_or_on_any_resume() -> None:
    """Exactly-once has to survive the refusal as well as the approval.

    The run comes back twice through a real process boundary, and the record of
    the refusal has to travel with it: `already` is what makes resume
    exactly-once, and a refusal that is not written there would be a call the
    next resume happily makes.
    """
    counter = Counter()
    first = park(counter)

    # Refuse the email; say nothing yet about the refund, so the run parks again
    # and there is a second boundary for the refusal to survive.
    second = resume(counter, first.suspension, {"email": "decline"})
    assert second.halted == "suspended"
    assert "email" not in counter.calls

    third = resume(counter, second.suspension, {"payments": "approve"}, now=2.0)
    assert third.halted == "final", third.halted
    assert counter.calls.count("email") == 0, (
        f"a call a person refused was made anyway: {counter.calls}"
    )
    assert refusals_in(third), "and the refusal survived the second process boundary"


def test_a_refusal_reaches_the_model_as_the_result_of_the_call_it_asked_for() -> None:
    """Not dropped, and not left as an absence.

    A call that was DECIDED and not done is recorded, exactly as a call a rule
    redirected and a tool the stage withheld already are. The alternative is a
    model that asked for something, finds nothing came back, and has nothing to
    tell the customer — T7's silent degradation on the one path a person is
    standing in.
    """
    counter = Counter()
    first = park(counter)
    after = resume(counter, first.suspension, {"payments": "approve", "email": "decline"})

    said = json.dumps(after.trace())
    assert "refused: a person said no" in said, said
    tools_and_results = [
        (c["name"], r)
        for step in after.trace()
        for c, r in zip(step["tools"], step["results"])
    ]
    assert ("email", "refused: a person said no") in tools_and_results, tools_and_results


def test_a_call_a_person_refused_is_published_where_a_cancelled_call_already_is() -> None:
    """`step.tool.cancelled` — the address a call that was decided and not done
    already uses, for a tool the stage withheld and for a call a rule
    redirected. A refusal is not a new kind of event; it is one more reason for
    that one."""
    counter = Counter()
    first = park(counter)
    bus = Bus()
    revived = Suspension.from_json(first.suspension.to_json())
    asyncio.run(
        run(THREE, ReferenceTransport(batch()), "refund me", counter.tools(),
            needs_approval=GATED, resume=revived, bus=bus,
            answer=Resumption(revived.correlation_key,
                              {"payments": "approve", "email": "decline"}),
            now=1.0)
    )
    cancelled = [
        e for e in bus.seen("step.tool.cancelled") if e.payload.get("name") == "email"
    ]
    assert cancelled, [str(e.address) for e in bus.log]
    assert cancelled[0].payload["reason"] == "a person said no"


# ────────── (iii) a person refusing is not the same record as nobody answering


def test_the_record_tells_a_person_refusing_apart_from_nobody_answering_in_time() -> None:
    """Both end the call the same way and they must not read the same way.

    `test_typed_questions.py:205` makes this argument for a single answer — a
    timeout "reads like a decline, so it has to be distinguishable from a person
    having declined, otherwise the record says a support lead refused a refund
    they never saw". This is that argument reaching the run's own transcript,
    which is the artefact anybody actually reads afterwards.
    """
    refused = Counter()
    first = park(refused)
    said_no = resume(refused, first.suspension,
                     {"payments": "approve", "email": "decline"})

    # The same wait, abandoned instead of answered. `if-nobody-answers: decline`
    # is what makes the deadline refuse rather than end the run, so the two
    # outcomes land in the same place and can be compared there.
    with_deadline = AgentSpec(
        name=THREE.name, description=THREE.description,
        instructions=THREE.instructions, tools=THREE.tools,
        pauses=(PauseRule(when=NEEDS_APPROVAL, waits_for=60.0,
                          if_nobody_answers="decline"),),
    )
    silent = Counter()
    parked = park(silent, with_deadline)
    timed_out = asyncio.run(
        run(with_deadline, ReferenceTransport(batch()), "refund me", silent.tools(),
            needs_approval=GATED, resume=parked.suspension, now=999.0)
    )

    theirs = refusals_in(said_no)
    nobodys = refusals_in(timed_out)
    assert theirs and nobodys, (theirs, nobodys)
    assert set(theirs).isdisjoint(nobodys), (
        f"a person refusing and nobody answering left the same line: {theirs}"
    )
    assert all("said no" in line for line in theirs), theirs
    assert all("nobody answered in time" in line for line in nobodys), nobodys


def test_the_record_names_who_refused_and_the_reason_they_gave() -> None:
    """A refusal is a governance fact, so it carries a name and a reason.

    Who comes from the question's own `asked-of:` line, and the reason from the
    `because:` the person typed. Both are the author's vocabulary, not the
    harness's: a question with no `asked-of:` says "a person", which is the
    honest answer rather than an invented team.

    And it says *the person answering for* them rather than naming them as the
    speaker, because a resumption carries no identity — the run knows who was
    asked and does not know who replied, and a record that claims the second is
    the mis-statement this whole area exists to prevent.
    """
    q = Question(
        name="is-this-ok",
        asks="Please check this before it happens.",
        answer={"approved": Shape.parse("yes or no"), "because": Shape.parse("text")},
        asked_of=("support-leads",),
    )
    given = {"email": "no", "email.because": "the customer has not been told yet"}
    assert ruling(NEEDS_APPROVAL, "email", q, given) is Ruling.REFUSED
    assert refused_in_words("email", q, given) == (
        'refused: the person answering for support-leads said no '
        '— "the customer has not been told yet"'
    )

    anonymous = Question(name="q", asks="ok?", answer={"approved": Shape.parse("yes or no")})
    assert refused_in_words("email", anonymous, {"email": "no"}) == (
        "refused: a person said no"
    ), "a question that names no audience must not have one invented for it"


# ────────────────────────────────── the three outcomes, where there were two


def test_saying_no_and_saying_nothing_are_two_outcomes_where_there_was_one_false() -> None:
    """The bug in one line. `_cleared` returned a bool; both of these were
    `False`, and the caller could not tell them apart, so it re-parked on
    both."""
    assert ruling(NEEDS_APPROVAL, "payments", None, {"payments": "approve"}) is Ruling.CLEARED
    assert ruling(NEEDS_APPROVAL, "payments", None, {"payments": "decline"}) is Ruling.REFUSED
    assert ruling(NEEDS_APPROVAL, "payments", None, {}) is Ruling.NOT_YET


def test_an_answer_that_does_not_fit_the_question_is_a_wait_and_not_a_refusal() -> None:
    """The dangerous direction of the widening.

    Reading anything-that-is-not-a-yes as a refusal would turn a mistyped
    `approved:` line into a cancelled refund that nobody chose to cancel. What
    does not fit leaves the run where it was, and the person is told what to
    type — which is what the shapes have always done, and now has to keep doing
    against a third outcome.
    """
    q = Question(
        name="is-this-ok",
        asks="Please check this before it happens.",
        answer={"approved": Shape.parse("yes or no"), "because": Shape.parse("text")},
    )
    assert ruling(NEEDS_APPROVAL, "payments", q, {"payments": "perhaps",
                                                  "payments.because": "x"}) is Ruling.NOT_YET
    # And a whole field missing is still a wait, not a no.
    assert ruling(NEEDS_APPROVAL, "payments", q, {"payments": "no"}) is Ruling.NOT_YET


def test_a_question_that_is_not_a_gate_cannot_be_refused_by_answering_it() -> None:
    """`how-much-to-refund.yaml` has no `approved:` line, and its own comment
    next door says that is what makes a no sayable at all. Answering "how much
    should we refund?" IS the go-ahead, so there is no shape of answer to it
    that means no — which is correct, and is why the worked example writes
    `approved:` on the questions where refusing has to be possible."""
    q = Question(
        name="how-much-to-refund",
        asks="How much should we refund on this order?",
        answer={"amount": Shape.parse("money")},
    )
    assert ruling(NEEDS_APPROVAL, "payments", q, {"payments": "25 USD"}) is Ruling.CLEARED


def test_a_teammates_reply_that_reads_like_a_refusal_is_a_reply_and_not_a_refusal() -> None:
    """A teammate's answer is the RESULT of the call that delegated to them, not
    a permission — so there is no such thing as a teammate refusing.

    Without this the widening would misfile the honest answer: a fraud checker
    replying "no, this order is outside the window" would be recorded as *a
    person having refused the call*, which is a governance fact about somebody
    who was never asked.
    """
    said = "no, this order is outside the window"
    assert ruling(WAITING_FOR_ANOTHER_AGENT, "fraud-checker", None,
                  {"fraud-checker": said}) is Ruling.CLEARED
    assert ruling(WAITING_FOR_ANOTHER_AGENT, "fraud-checker", None, {}) is Ruling.NOT_YET


# ───────────────────────────────── through the author's own line, nothing passed


@lru_cache(maxsize=1)
def worked_example() -> dict:
    """The example tree, loaded by the real Rust loader (invariant P-1).

    A Python re-read of the YAML would be a second loader, and two loaders
    drift.
    """
    return json.loads(
        subprocess.run(
            ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "show", str(EXAMPLE)],
            cwd=str(EXAMPLE.parents[1]), capture_output=True, text=True, check=True,
        ).stdout
    )


def a_refund_over_the_written_limit() -> Script:
    return Script([
        Turn("Refunding.",
             (ToolCall("payments", {"order-number": "A-1182", "amount": "300.00 USD"}),)),
        Turn("Refunded 300.00 USD."),
    ])


def test_the_authors_own_question_lets_a_person_refuse_with_nothing_passed_in() -> None:
    """The whole path, end to end, through lines a support lead wrote.

    Nothing is handed in — no `needs_approval=`, no `asking=`, no `gates=`. The
    wait comes from `policies/approvals.yaml` ("a refund over 200 USD is a
    management decision"), the answer shape and the audience come from
    `questions/is-this-ok.yaml`, and the `approved:` line of that file — whose
    own comment says it "is the word that makes a no mean no" — is what this
    person's refusal is read through.

    A test that built the question in Python would prove the object works and
    say nothing about whether the author's line reaches it. Delete the
    `Ruling.REFUSED` arm from the harness's batch branch and this comes back
    `suspended` instead of `final`; change `asked-of:` in `is-this-ok.yaml` and
    the sentence below changes with it.
    """
    if not (EXAMPLE.parents[1] / "target/debug/pact").exists():
        pytest.skip("build the CLI first")
    spec = AgentSpec.from_document(worked_example(), "refund-desk", EXAMPLE)
    ran: list[dict] = []
    tools = {
        "zendesk": lambda a: "lamp, 6 days ago, broken",
        "payments": lambda a: ran.append(dict(a)) or "refunded 300.00 USD",
    }

    # The payments connection's own consent is granted on the way past. That is
    # `resources/payments-server.yaml` stopping this run for a different authored
    # reason, and it is `test_connection_consent.py`'s guarantee; what is under
    # test here is the refusal that comes after it.
    waiting = allowing_the_connection(
        spec, lambda: ReferenceTransport(a_refund_over_the_written_limit()),
        "refund A-1182", tools, now=0.0,
    )
    assert waiting.halted == "suspended", waiting.output
    assert waiting.suspension.reason == NEEDS_APPROVAL
    assert ran == [], "the money moved before anyone was asked"

    said_no = waiting.suspension.answer(
        **{"payments": "no", "payments.because": "outside the refund window"}
    )
    after = asyncio.run(
        run(spec, ReferenceTransport(a_refund_over_the_written_limit()),
            "refund A-1182", tools, resume=waiting.suspension, answer=said_no, now=1.0)
    )

    assert after.halted == "final", (
        f"a support lead said no and the run came back {after.halted!r}"
    )
    assert ran == [], "and no money moved"
    assert refusals_in(after) == [
        'refused: the person answering for support-leads said no '
        '— "outside the refund window"'
    ], refusals_in(after)


def test_the_worked_example_still_lets_the_same_person_say_yes() -> None:
    """The other direction, on the same authored lines.

    A widening that made every answer terminate the call would pass every
    assertion above and break the thing the gate is for. This is the control.
    """
    if not (EXAMPLE.parents[1] / "target/debug/pact").exists():
        pytest.skip("build the CLI first")
    spec = AgentSpec.from_document(worked_example(), "refund-desk", EXAMPLE)
    ran: list[dict] = []
    tools = {
        "zendesk": lambda a: "lamp, 6 days ago, broken",
        "payments": lambda a: ran.append(dict(a)) or "refunded 300.00 USD",
    }
    waiting = allowing_the_connection(
        spec, lambda: ReferenceTransport(a_refund_over_the_written_limit()),
        "refund A-1182", tools, now=0.0,
    )
    said_yes = waiting.suspension.answer(
        **{"payments": "yes", "payments.because": "checked the order"}
    )
    after = asyncio.run(
        run(spec, ReferenceTransport(a_refund_over_the_written_limit()),
            "refund A-1182", tools, resume=waiting.suspension, answer=said_yes, now=1.0)
    )
    assert after.halted == "final"
    assert ran == [{"order-number": "A-1182", "amount": "300.00 USD"}], ran
    assert refusals_in(after) == [], refusals_in(after)
