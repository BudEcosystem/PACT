"""`asks-to-connect:` stopping something — the wait, not the wording.

`resources/payments-server.yaml` says a person is asked before this desk uses the
payments connection. For a round every part of that line worked except the part
that matters: the question was found, the audience and the hour were read, the
screen rendered — and the run called `payments` anyway and reported `final`.
Money moved over a connection nobody had consented to, while `pact check` passed
the file that says otherwise.

What was missing was one decision and one name:

* **which of two waits a person meets first.** `payments` carries rules from two
  of the author's files, and `questions.ASKED_IN_ORDER` now says consent before
  approval, with the argument beside it.
* **what each answer is called.** Both questions ask for `approved` and
  `because`, so a wait named after the call would have let one person's yes to
  the connection release a 300 USD refund they were never shown. Consent is
  granted for the CONNECTION and is answered under the connection's name.

The tests below are the four guarantees that follow. Every one of them loads the
worked example and passes **nothing** — no `gates=`, no `needs_approval=`, no
question built in Python — because a test that hands the gate in proves the gate
works and says nothing about whether the author's line reaches it. That is the
exact shape of the defect this area shipped twice.

Delete `gates=True` from the consent rule in `questions_for` and the gate tests
go red; make `harness.run` read `Gate.must_ask` again — which answered *whether*
and not *why*, and turned its True into `needs-approval` by hand — and the five
run tests go red with `halted == 'final'` and the money moving. That predicate is
gone; `Gate.waits_for` replaced it, and there is no second reader of the same
answers left to disagree with it.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import suspension  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.questions import (  # noqa: E402
    ASKED_IN_ORDER, NEEDS_APPROVAL, NEEDS_PERMISSION, Wait, questions_for,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import Suspension  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples/refund-desk"

#: The one connection the worked example gates, and the file the author gated it
#: in. Written out rather than derived, so a test that renames the server has to
#: say so here too.
CONNECTION = "payments-server"


@pytest.fixture(scope="session")
def document() -> dict:
    """The worked example as `pact check` loads it. No fixture is built here."""
    if not (REPO / "target/debug/pact").exists():
        pytest.skip("build the CLI first")
    out = subprocess.run(
        [str(REPO / "target/debug/pact"), "show", str(EXAMPLE)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


class Watching:
    """Records what actually went over each connection, and when."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def tools(self) -> dict:
        def zendesk(a: dict) -> str:
            self.calls.append(("zendesk", dict(a)))
            return "lamp, 6 days ago, broken, 40 USD"

        def payments(a: dict) -> str:
            self.calls.append(("payments", dict(a)))
            return f"refunded {a.get('amount')}"

        return {"zendesk": zendesk, "payments": payments}


def a_refund_of(amount: str) -> Script:
    return Script([
        Turn("Issuing the refund.",
             (ToolCall("payments", {"order-number": "A-1182", "amount": amount}),)),
        Turn(f"Approved: refunded {amount}."),
    ])


# ───────────────────────────────────────────────── the gate, from the document


def test_the_line_the_author_wrote_makes_the_gate_stop_the_call(document: dict) -> None:
    """`asks-to-connect: may-we-connect` becomes a stop, not a note.

    Read as three lines the author already wrote — `uses:` names `payments`,
    `tools/payments.yaml` connects to `payments-server`, and that resource says a
    person is asked — and nothing else. Delete `gates=True` from the consent rule
    in `questions_for` and this comes back empty, which is what it was for a
    round.
    """
    gate = questions_for(document, "refund-desk")

    assert gate.waits_for("payments", {}) == (Wait(NEEDS_PERMISSION, CONNECTION),), (
        "a call over a connection nobody has allowed has to be a wait"
    )
    # Including the read-only lookup: `asks-to-connect`'s own help says "when
    # this connection has not been allowed yet", and a lookup goes over the
    # connection exactly as a refund does.
    assert gate.waits_for("payments", {"action": "look-up-order"}), (
        "a lookup goes over the connection too"
    )
    # And only for an agent that can reach it. `fraud-checker` uses `zendesk`.
    assert questions_for(document, "fraud-checker").waits_for("payments", {}) == ()


def test_a_call_needing_two_things_lists_them_consent_first(document: dict) -> None:
    """The precedence, as a fact about the gate rather than about one run.

    300 USD is over `policies/approvals.yaml`'s 200 USD line and goes over a
    connection nobody has allowed, so it is two waits. Which one comes first used
    to fall out of declaration order; `ASKED_IN_ORDER` is the decision.
    """
    gate = questions_for(document, "refund-desk")

    assert gate.waits_for("payments", {"amount": "300.00 USD"}) == (
        Wait(NEEDS_PERMISSION, CONNECTION),
        Wait(NEEDS_APPROVAL),
    )
    # 40 USD is under the threshold, so the approval is not among them — the
    # consent gate must not quietly widen a rule the author wrote a figure on.
    assert gate.waits_for("payments", {"amount": "40.00 USD"}) == (
        Wait(NEEDS_PERMISSION, CONNECTION),
    )


def test_the_two_reasons_are_spelled_the_same_here_as_where_a_run_parks() -> None:
    """`questions` cannot import `suspension`, so the words are written twice.

    Pinned rather than trusted: a run parks under `suspension`'s spelling and the
    gate orders under this module's, and two strings that must be equal and live
    in two files drift the moment nobody is looking.
    """
    assert NEEDS_PERMISSION == suspension.NEEDS_PERMISSION
    assert NEEDS_APPROVAL == suspension.NEEDS_APPROVAL
    assert ASKED_IN_ORDER == (suspension.NEEDS_PERMISSION, suspension.NEEDS_APPROVAL)


# ─────────────────────────────────────────────────────── the four guarantees


def test_a_run_that_reaches_a_connection_needing_consent_parks_before_the_call(
    document: dict,
) -> None:
    """(i) Before, not after. Nothing goes over the connection first.

    Measured on this exact run before the gate existed: `payments` was called
    with `{'order-number': 'A-1182', 'amount': '40.00 USD'}` and the run reported
    `final`.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    result = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("40.00 USD")), "refund A-1182",
            seen.tools(), now=0.0)
    )

    assert result.halted == "suspended", result.output
    assert result.suspension is not None
    assert result.suspension.reason == NEEDS_PERMISSION
    assert [n for n, _ in seen.calls] == [], (
        "money moved over a connection nobody has allowed"
    )
    # The wait obeys the question's own file, not a default: 1h, two named
    # approvers, and a silence that ends the run rather than connecting anyway.
    assert result.suspension.waits_for == 3600.0
    assert result.suspension.who_can_answer == ("support-leads", "support-manager")
    assert result.suspension.if_nobody_answers == "stop-and-say-so"
    # And it is answered under the CONNECTION's name.
    assert [e.name for e in result.suspension.asks] == [
        CONNECTION, f"{CONNECTION}.because"
    ]


def test_the_person_is_shown_the_connections_own_words_not_the_refund_approvals(
    document: dict,
) -> None:
    """(ii) The screen is `may-we-connect`'s, all of it.

    `payments` is one name carrying rules from two files, and a person shown the
    wrong one is being asked to approve a refund when what is waiting is whether
    this desk may use the payments connection at all.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    parked = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("40.00 USD")), "refund A-1182",
            seen.tools(), now=0.0)
    ).suspension
    words = parked.in_words

    assert "May we use the payments connection for this?" in words, words
    assert "answer within: 1h" in words, "the deadline read is the one obeyed"
    assert "support-manager" in words, "the audience is the question's `asked-of:`"
    # Not the refund-approval question, and not its half-hour.
    assert "Please check this before it happens." not in words, words
    assert "answer within: 30m" not in words, words
    # A connection is granted FOR something, and that something is quoted data in
    # its own region — a customer's order number cannot read as an instruction.
    assert '"A-1182"' in words and '"40.00 USD"' in words, words


def test_a_call_needing_both_asks_both_in_order_and_neither_answer_clears_the_other(
    document: dict,
) -> None:
    """(iii) Two waits, two answers, and no crossing between them.

    A 300 USD refund over an unallowed connection. Consent first; the yes to it
    does not release the refund; the yes to the refund would not have released
    the connection. The money moves once, after both.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    first = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("300.00 USD")), "refund A-1182",
            seen.tools(), now=0.0)
    ).suspension
    assert first.reason == NEEDS_PERMISSION, "consent is asked before approval"
    assert "May we use the payments connection for this?" in first.in_words

    # The two waits do not share a single answer name, so neither can be answered
    # by the other's yes. This is the whole reason the consent is named for the
    # connection.
    assert [e.name for e in first.asks] == [CONNECTION, f"{CONNECTION}.because"]
    with pytest.raises(suspension.WrongAnswer):
        first.answer(**{"payments": "yes", "payments.because": "fine"})

    allowed = first.answer(**{CONNECTION: "yes", f"{CONNECTION}.because": "known supplier"})
    second = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("300.00 USD")), "refund A-1182",
            seen.tools(), resume=first, answer=allowed, now=1.0)
    ).suspension

    assert second is not None, "allowing the connection is not approving the refund"
    assert second.reason == NEEDS_APPROVAL
    assert "a refund over 200 USD is a management decision" in second.in_words
    assert [e.name for e in second.asks] == ["payments", "payments.because"]
    assert [n for n, _ in seen.calls] == [], "still nothing over the connection"
    with pytest.raises(suspension.WrongAnswer):
        second.answer(**{CONNECTION: "yes", f"{CONNECTION}.because": "fine"})

    approved = second.answer(**{"payments": "yes", "payments.because": "checked the order"})
    done = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("300.00 USD")), "refund A-1182",
            seen.tools(), resume=second, answer=approved, now=2.0)
    )

    assert done.halted == "final", done.output
    assert seen.calls == [("payments", {"order-number": "A-1182", "amount": "300.00 USD"})], (
        "one refund, issued once, after both people said yes"
    )


def test_a_no_to_the_connection_leaves_the_refund_unmade_and_never_asks_about_it(
    document: dict,
) -> None:
    """The other half of the order: a refusal ends it before the money question.

    This is the argument for consent-first doing something. Approval-first would
    have taken somebody's yes on a 300 USD refund and then discovered the
    connection was refused — an approval on record for a payment that never
    happened.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    parked = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("300.00 USD")), "refund A-1182",
            seen.tools(), now=0.0)
    ).suspension
    refused = parked.answer(**{CONNECTION: "no", f"{CONNECTION}.because": "not this account"})
    after = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("300.00 USD")), "refund A-1182",
            seen.tools(), resume=parked, answer=refused, now=1.0)
    )

    assert [n for n, _ in seen.calls] == [], "a no is not a delay"
    # And it is over. A refusal that re-parked would satisfy every line above
    # while asking the same person the same thing for ever, which is what a bare
    # yes-or-no reading of an answer did until `rulings.Ruling` had a third
    # member — see `test_a_person_can_say_no.py`.
    assert after.halted == "final", after.halted
    assert after.suspension is None
    said = json.dumps(after.trace())
    assert "refused:" in said and "not this account" in said, said
    assert "a refund over 200 USD is a management decision" not in (
        after.suspension.in_words if after.suspension else ""
    ), "nobody is asked to approve a refund that cannot be paid"


def test_the_eval_runner_still_scores_every_case_because_asking_only_turns_this_off_too(
    document: dict,
) -> None:
    """(iv) `asking_only()` reaches the consent, because it is a rule.

    This is the property that decided where the wait lives. Seeded into the
    harness's `gated` map it would be one no runner could turn off, so every
    scored case touching `payments` would come back "did not answer" and the
    model under test would be blamed for a connection nobody had granted.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    assert spec.asking.asking_only().waits_for("payments", {"amount": "300.00 USD"}) == ()

    result = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("300.00 USD")), "refund A-1182",
            seen.tools(), asking=spec.asking.asking_only(), now=0.0)
    )

    assert result.halted == "final", result.output
    assert [n for n, _ in seen.calls] == ["payments"]
    # The questions are still there to be asked about — only the parking is off.
    assert spec.asking.asking_only().for_call(
        "payments", {}, NEEDS_PERMISSION
    ) is not None


# ──────────────────────────────────────────────────────── crossing a boundary


def test_what_a_run_has_already_been_allowed_survives_the_process_that_allowed_it(
    document: dict,
) -> None:
    """Two waits about one call mean the first answer has to outlive the second
    park, and a park outlives its process (D23). If `granted` did not travel, the
    run would come back to a permission it had already been given and ask again,
    and again."""
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    first = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("300.00 USD")), "refund A-1182",
            seen.tools(), now=0.0)
    ).suspension
    allowed = first.answer(**{CONNECTION: "yes", f"{CONNECTION}.because": "known supplier"})
    second = asyncio.run(
        run(spec, ReferenceTransport(a_refund_of("300.00 USD")), "refund A-1182",
            seen.tools(), resume=first, answer=allowed, now=1.0)
    ).suspension

    assert second.granted.get(CONNECTION) == "yes", second.granted
    # And it is on the durable record, not only in memory.
    revived = Suspension.from_json(second.to_json())
    assert revived.granted == second.granted


# ─────────────────── two waits meeting the rest of a batch, in one step
#
# Three mechanisms landed in the same round and each was built against a tree
# without the other two: a call can carry TWO waits (this file), a person can
# refuse (`test_a_person_can_say_no.py`), and a batch a person partly answered
# runs the part they allowed (`test_hitl_partial_approval.py`). The interaction
# is nobody's fixture and is where a merge of the three would break, so it is
# held here — one batch in which all three are true at once.


def two_refunds_and_a_lookup() -> Script:
    """One batch: a big refund, a small one, and a read-only ticket lookup.

    The big refund carries both waits — over the connection and over the
    author's 200 USD line. The small one carries only the consent. `zendesk`
    carries neither, so the batch holds every state a call can be in.
    """
    return Script([
        Turn("Reading the ticket and issuing both.", (
            ToolCall("zendesk", {"action": "read-ticket", "ticket-id": "T-1"}),
            ToolCall("payments", {"order-number": "A-300", "amount": "300.00 USD"}),
            ToolCall("payments", {"order-number": "A-040", "amount": "40.00 USD"}),
        )),
        Turn("Done."),
    ])


def test_two_calls_over_one_connection_are_one_consent_and_then_their_own_approvals(
    document: dict,
) -> None:
    """Consent is granted for the CONNECTION, once, and it releases only itself.

    `questions/may-we-connect.yaml` says in its own words that it is asked once
    and not once per customer, so two calls over the same connection are one
    question. What that yes must NOT do is release the 300 USD refund the author
    wrote a separate rule about — which is the whole reason the consent is
    answered under the server's name rather than the call's.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    consent = asyncio.run(
        run(spec, ReferenceTransport(two_refunds_and_a_lookup()), "refund both",
            seen.tools(), now=0.0)
    ).suspension
    assert consent.reason == NEEDS_PERMISSION
    assert [e.name for e in consent.asks] == [CONNECTION, f"{CONNECTION}.because"], (
        "two calls over one connection are one question"
    )
    # The lookup carries no wait at all, so it happens before the run parks — a
    # batch does everything it MAY do rather than deferring it until the last
    # answer arrives. Nothing went over the gated connection.
    assert [n for n, _ in seen.calls] == ["zendesk"], seen.calls

    allowed = consent.answer(**{CONNECTION: "yes", f"{CONNECTION}.because": "known supplier"})
    approval = asyncio.run(
        run(spec, ReferenceTransport(two_refunds_and_a_lookup()), "refund both",
            seen.tools(), resume=consent, answer=allowed, now=1.0)
    ).suspension

    # Only the big one is still waiting: 40 USD is under the author's line, and a
    # consent gate that quietly widened a threshold would be the over-gating this
    # whole area exists to avoid.
    assert approval is not None, "allowing the connection is not approving the refund"
    assert approval.reason == NEEDS_APPROVAL
    assert [e.name for e in approval.asks] == ["payments", "payments.because"]
    # The 40 USD refund the consent cleared HAS run, before the park: each call
    # has its own entry in the step's ledger (its slot), so the small refund's
    # result is its own and cannot be handed to the big one nobody has answered.
    # It used to wait beside the big one, because the ledger was keyed by the
    # tool's name and one entry could not hold two outcomes.
    assert [n for n, _ in seen.calls] == ["zendesk", "payments"], seen.calls
    assert seen.calls[-1][1]["amount"] == "40.00 USD", seen.calls


def test_refusing_the_refund_ends_the_run_without_asking_for_the_consent_again(
    document: dict,
) -> None:
    """A no to the second wait does not send the run back to the first one.

    The consent has to survive the park it was granted at (`Suspension.granted`,
    WAIT-7) — otherwise the run comes back to a permission it already has and
    asks again, and again. The refusal then ends the run rather than re-parking,
    and the record carries the reason the person gave.
    """
    spec = AgentSpec.from_document(document, "refund-desk")
    seen = Watching()

    consent = asyncio.run(
        run(spec, ReferenceTransport(two_refunds_and_a_lookup()), "refund both",
            seen.tools(), now=0.0)
    ).suspension
    allowed = consent.answer(**{CONNECTION: "yes", f"{CONNECTION}.because": "known supplier"})
    approval = asyncio.run(
        run(spec, ReferenceTransport(two_refunds_and_a_lookup()), "refund both",
            seen.tools(), resume=consent, answer=allowed, now=1.0)
    ).suspension
    assert approval.granted.get(CONNECTION) == "yes", approval.granted

    said_no = approval.answer(
        **{"payments": "no", "payments.because": "outside the refund window"}
    )
    after = asyncio.run(
        run(spec, ReferenceTransport(two_refunds_and_a_lookup()), "refund both",
            seen.tools(), resume=approval, answer=said_no, now=2.0)
    )

    assert after.halted == "final", after.halted
    # The 300 USD refund did not happen: a person refused it. The 40 USD one ran
    # once, when the consent cleared it, and the refusal of its sibling does not
    # undo or repeat it: each call has its own entry in the step's ledger.
    assert [n for n, _ in seen.calls] == ["zendesk", "payments"], seen.calls
    assert seen.calls[-1][1]["amount"] == "40.00 USD", seen.calls
    said = json.dumps(after.trace())
    assert "outside the refund window" in said, "the record carries their reason"
    assert "support-leads" in said, "and who was asked"
