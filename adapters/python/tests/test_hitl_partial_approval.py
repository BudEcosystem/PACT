"""The HITL fixture, told the truth about a batch a person only PARTLY approved.

`test_hitl_kill_resume.py` exercises the all-or-nothing case: one gated call,
one answer, everything or nothing. That is the easy half. The half that decides
whether an approval gate is worth having is the one where a person looks at
three actions and lets some of them through.

Measured before this fixture existed, on `ReferenceTransport`: one step calling
`zendesk`, `payments` and `email`, with `payments` and `email` gated, answered
`payments: approve` and nothing yet about `email`. The tool log after the resume
was `['zendesk']`. `payments` was approved by a person and never ran, because
the carry-forward inside the park branch executed only calls that were *never
gated* — so a call the person had CLEARED was excluded from the park (rightly)
and from the execution (wrongly), and while `email` went unanswered the approved
refund was deferred again on every resume. A person who approves two of three
actions got none of them, which is not what they said.

These run across the same seven transports the kill test does, and for the same
reason: this is the fixture the architecture says discriminates every
divergence, and a resume that runs different work on different transports is
exactly the divergence it exists to catch.

**The call still waiting here is UNANSWERED, not declined**, and that is
deliberate. What a *refusal* does to a run — end it or park it again — is the
sibling mechanism in `test_a_person_can_say_no.py`, and a fixture that asserted
one of those answers would go red the day the other one shipped. What both
worlds agree on is asserted; where they differ is named and left to that file.
"""

from __future__ import annotations

import asyncio
import json
import sys
from functools import lru_cache
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
#: The sibling fixture's own transport list, imported rather than copied. A
#: second copy would go stale the day an eighth target lands, and the guarantee
#: below is "on every transport", not "on the seven somebody typed here".
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.loops import Does, Loop, Phase  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import (  # noqa: E402
    NEEDS_APPROVAL,
    WAITING_FOR_ANOTHER_AGENT,
    Resumption,
    Suspension,
)
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from test_hitl_kill_resume import TRANSPORTS  # noqa: E402

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Read the ticket, refund, and tell the customer.",
    tools=(
        ToolSpec("zendesk", "read the ticket"),
        ToolSpec("payments", "issue a refund"),
        ToolSpec("email", "write to the customer"),
    ),
)

#: Two of the three need a person. The third does not, so one batch carries all
#: three states an answer can leave a call in: never gated, cleared, and still
#: waiting.
GATED = frozenset({"payments", "email"})


class Counter:
    """Counts every real tool invocation, in the order they happened.

    Order is asserted as well as count: the whole batch is one step on every
    transport, so if the approved half of it runs in a different order under
    LangGraph than under Pydantic AI, the byte-identical-trace claim is false on
    this path.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def tools(self) -> dict:
        def one(name: str, answer: str):
            def fn(_args):
                self.calls.append(name)
                return answer

            return fn

        return {
            "zendesk": one("zendesk", "lamp, 6 days ago, broken, 40 USD"),
            "payments": one("payments", "refunded 40 USD"),
            "email": one("email", "sent"),
        }


def script() -> Script:
    """One batch, three calls, in the order the model asked for them."""
    return Script(
        [
            Turn(
                "Reading the ticket, refunding, and writing to the customer.",
                (
                    ToolCall("zendesk", {"id": "T-1"}),
                    ToolCall("payments", {"amount": 40}),
                    ToolCall("email", {"to": "customer"}),
                ),
            ),
            Turn("Refunded 40 USD."),
        ]
    )


def park(name: str, counter: Counter):
    """Run until the gate stops the batch."""
    return asyncio.run(
        run(SPEC, TRANSPORTS[name](script()), "refund me", counter.tools(),
            needs_approval=GATED, now=0.0)
    )


def resume(name: str, counter: Counter, parked: Suspension, said: dict[str, str],
           now: float = 1.0):
    """Come back through a real process boundary, carrying one person's answer.

    Built as a `Resumption` rather than through `Suspension.answer()` because
    every answer here deliberately says nothing about one of the things asked,
    and `answer()` rightly refuses an incomplete reply. What is under test is
    what the LOOP does when a person answers some of a batch and not the rest.
    """
    revived = Suspension.from_json(parked.to_json())
    return asyncio.run(
        run(SPEC, TRANSPORTS[name](script()), "refund me", counter.tools(),
            needs_approval=GATED, resume=revived,
            answer=Resumption(revived.correlation_key, said), now=now)
    )


# ─────────────────────────────────────────── what a partly-approved batch does


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_approving_two_of_three_actions_runs_exactly_those_two(name: str) -> None:
    first = park(name, counter := Counter())
    assert first.halted == "suspended"
    assert counter.calls == ["zendesk"], "only the ungated call runs before the answer"

    after = resume(name, counter, first.suspension, {"payments": "approve"})

    # The approved refund happened. Before the fix this list was `['zendesk']`.
    assert counter.calls == ["zendesk", "payments"], (
        "a person approved `payments` and it did not run; the whole batch was "
        f"deferred because `email` was still waiting. Ran: {counter.calls}"
    )
    assert after.halted == "suspended", "and the run is still waiting on the rest"


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_the_unanswered_action_stays_unexecuted_and_the_run_parks_on_it_alone(
    name: str,
) -> None:
    first = park(name, counter := Counter())
    after = resume(name, counter, first.suspension, {"payments": "approve"})

    assert "email" not in counter.calls, "nothing runs that nobody has approved"
    assert after.suspension is not None
    assert after.suspension.reason == NEEDS_APPROVAL
    # Parked on the ONE thing still outstanding, not on the whole batch again.
    # The approved call is gone from the question, so nobody is asked twice
    # about something they have already decided.
    assert [e.name for e in after.suspension.asks] == ["email"], (
        f"the second wait still asks about {[e.name for e in after.suspension.asks]}"
    )
    assert after.suspension.correlation_key != first.suspension.correlation_key, (
        "a narrower wait is a different wait, or the first answer clears it again"
    )


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_resuming_twice_never_runs_an_approved_call_twice(name: str) -> None:
    """The exactly-once ledger has to survive a SECOND answer, not just one.

    This is where a fix that merely moved the execution earlier would break: the
    approved call now runs *during* a park, and a park that happens again must
    replay it from the record rather than doing it a second time.
    """
    first = park(name, counter := Counter())
    second = resume(name, counter, first.suspension, {"payments": "approve"})
    third = resume(name, counter, second.suspension, {"email": "approve"}, now=2.0)

    assert third.halted == "final", third.halted
    assert counter.calls.count("zendesk") == 1, counter.calls
    assert counter.calls.count("payments") == 1, counter.calls
    assert counter.calls.count("email") == 1, counter.calls
    # And the order is the batch's own, across two process boundaries.
    assert counter.calls == ["zendesk", "payments", "email"], counter.calls


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_approving_one_call_runs_it_even_when_another_is_refused(name: str) -> None:
    """The item's own probe: `payments: approve, email: decline`.

    Only the tool log is asserted, not the halt state. Whether a refusal ends
    the run or parks it again is `test_a_person_can_say_no.py`'s guarantee, and
    both of its answers leave this list the same: the approved call ran, and the
    refused one did not.
    """
    first = park(name, counter := Counter())
    resume(name, counter, first.suspension, {"payments": "approve", "email": "decline"})

    assert counter.calls == ["zendesk", "payments"], counter.calls


def test_a_partly_approved_batch_leaves_the_same_trace_on_every_transport() -> None:
    """The discriminating assertion, on the path the kill test does not walk.

    The byte-identical-trace claim covers partial approval too, and this is
    where an adapter could most easily invent its own order: the batch is split
    in half by a person and finished across two more processes.
    """
    seen = {}
    for name in TRANSPORTS:
        counter = Counter()
        first = park(name, counter)
        second = resume(name, counter, first.suspension, {"payments": "approve"})
        third = resume(name, counter, second.suspension, {"email": "approve"}, now=2.0)
        seen[name] = {"trace": third.trace(), "output": third.output,
                      "tools": counter.calls}

    reference = seen["reference"]
    for name, got in seen.items():
        assert got == reference, (
            f"{name} diverged from the reference on a partly-approved batch.\n"
            f"  reference: {json.dumps(reference, indent=2)}\n"
            f"  {name}: {json.dumps(got, indent=2)}"
        )


# ──────────────────────────────── what must NOT be swept up by the same change


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_a_tool_the_stage_withheld_does_not_run_while_the_batch_waits(name: str) -> None:
    """A refused call was DECIDED, not deferred, so it is not carried forward.

    Measured before this fixture: on a stage whose `may-use:` lists `zendesk`
    and `payments` only, a model that also called `email` had `email` run anyway
    during the park — the park's own ledger came back holding an `email` entry —
    while the model was told `email` "is not available in the 'gather' stage".
    Narrowing the tools a stage may reach is the cheapest accuracy win PACT has,
    and a gate elsewhere in the batch was quietly undoing it.
    """
    narrowed = Loop(
        name="narrow",
        starts_at="gather",
        steps={
            "gather": Phase(
                "gather", Does.USE_TOOLS,
                {"used-a-tool": "gather", "answered": ""},
                may_use=("zendesk", "payments"),
            )
        },
    )
    counter = Counter()
    first = asyncio.run(
        run(SPEC, TRANSPORTS[name](script()), "refund me", counter.tools(),
            needs_approval=frozenset({"payments"}), loop=narrowed, now=0.0)
    )
    assert first.halted == "suspended"
    assert counter.calls == ["zendesk"], counter.calls
    assert "email" not in first.suspension.completed, (
        f"a withheld tool was run and recorded: {first.suspension.completed}"
    )


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_a_teammate_is_still_asked_after_a_gate_parks_the_batch(name: str) -> None:
    """A call to a teammate is work happening elsewhere, not a local tool.

    Measured before this fixture: a batch of `fraud-checker` plus a gated
    `payments` recorded `error: no tool named 'fraud-checker'` in the park's
    ledger, because the carry-forward handed a member name to `_call_tool`,
    which has no implementation to find for one. A completed call is never
    re-asked, so the resumed run served the model that error and the teammate
    was never asked at all — on a desk whose own `teamwork.yaml` says nobody
    carries on without the fraud check.
    """
    spec = AgentSpec(
        name="Refund Desk", description="Decides refunds",
        instructions="Check for fraud, then refund.",
        tools=(ToolSpec("payments", "issue a refund"),),
        team={"fraud-checker": "Looks for signs the request is not genuine."},
    )
    asked: list[str] = []

    async def ask_member(grant):
        asked.append(grant.member)
        return "no fraud signals"

    counter = Counter()
    two = Script([
        Turn("Checking and refunding.",
             (ToolCall("fraud-checker", {}), ToolCall("payments", {"amount": 40}))),
        Turn("Refunded 40 USD."),
    ])
    first = asyncio.run(
        run(spec, TRANSPORTS[name](two), "refund me", counter.tools(),
            needs_approval=frozenset({"payments"}), ask_member=ask_member, now=0.0)
    )
    assert first.halted == "suspended"
    assert "fraud-checker" not in first.suspension.completed, (
        f"the teammate was answered by the tool path: {first.suspension.completed}"
    )

    revived = Suspension.from_json(first.suspension.to_json())
    after = asyncio.run(
        run(spec, TRANSPORTS[name](two), "refund me", counter.tools(),
            needs_approval=frozenset({"payments"}), ask_member=ask_member,
            resume=revived, answer=Resumption(revived.correlation_key,
                                              {"payments": "approve"}), now=1.0)
    )
    assert asked == ["fraud-checker"], (
        f"the teammate was never asked; {asked} was asked instead"
    )
    assert after.halted == "final", after.halted


def test_two_calls_to_one_tool_wait_together_until_both_are_answered() -> None:
    """One ledger entry cannot hold two outcomes, so the name waits as a whole.

    `already` is keyed by tool NAME. Carrying the approved 300 USD refund
    forward while the 40 USD one is still unanswered would put its result under
    `payments`, and the next resume would hand that same result to the call
    nobody has answered — a refund reported as paid that never happened, and a
    second one silently made from one person's yes about the first. Two calls to
    one name therefore wait together, and answering both releases both, which is
    exactly what happened before any of this changed.
    """
    spec = AgentSpec(
        name="Refund Desk", description="Decides refunds", instructions="Refund.",
        tools=(ToolSpec("payments", "issue a refund"),),
    )
    paid: list[int] = []
    tools = {"payments": lambda a: paid.append(a["amount"]) or f"refunded {a['amount']}"}
    twice = Script([
        Turn("Issuing both.",
             (ToolCall("payments", {"amount": 300}), ToolCall("payments", {"amount": 40}))),
        Turn("Both done."),
    ])
    first = asyncio.run(
        run(spec, ReferenceTransport(twice), "refund both", tools,
            needs_approval=frozenset({"payments"}), now=0.0)
    )
    assert [e.name for e in first.suspension.asks] == ["payments", "payments#1"]

    half = asyncio.run(
        run(spec, ReferenceTransport(twice), "refund both", tools,
            needs_approval=frozenset({"payments"}), resume=first.suspension,
            answer=Resumption(first.suspension.correlation_key,
                              {"payments": "approve"}), now=1.0)
    )
    assert paid == [], f"neither may run while one of the two is unanswered: {paid}"
    assert half.halted == "suspended"
    assert [e.name for e in half.suspension.asks] == ["payments#1"]

    # Answered TOGETHER, both go through, once each. Holding a cleared call back
    # because a same-named sibling is still waiting must cost the ordinary case
    # nothing — this is the assertion that says so.
    both = asyncio.run(
        run(spec, ReferenceTransport(twice), "refund both", tools,
            needs_approval=frozenset({"payments"}), resume=first.suspension,
            answer=first.suspension.answer(**{"payments": "approve",
                                              "payments#1": "approve"}), now=1.0)
    )
    assert both.halted == "final", both.halted
    assert paid == [300, 40], paid


def test_refusing_one_of_two_calls_to_one_tool_stops_both_and_says_why() -> None:
    """The other side of the same limit, and the one the two items disagreed on.

    A refusal ends its own wait (`test_a_person_can_say_no.py`) and a cleared
    call runs before the park (above). Put both in one batch, over ONE tool name,
    and they collide: `already` holds one outcome per name, so the approved 40
    USD refund cannot be carried forward beside the refused 300 USD one — its
    result would be handed to the call a person turned down.

    So a name is decided as a whole, in the refusing direction, which is the safe
    one: the alternative is issuing a refund somebody said no to. What must not
    happen is the record claiming they refused a call they were never shown, so
    it carries the refusal that really happened AND says why the rest of the name
    stopped with it.
    """
    spec = AgentSpec(
        name="Refund Desk", description="Decides refunds", instructions="Refund.",
        tools=(ToolSpec("payments", "issue a refund"),),
    )
    paid: list[int] = []
    tools = {"payments": lambda a: paid.append(a["amount"]) or f"refunded {a['amount']}"}
    twice = Script([
        Turn("Issuing both.",
             (ToolCall("payments", {"amount": 300}), ToolCall("payments", {"amount": 40}))),
        Turn("Both done."),
    ])
    first = asyncio.run(
        run(spec, ReferenceTransport(twice), "refund both", tools,
            needs_approval=frozenset({"payments"}), now=0.0)
    )
    after = asyncio.run(
        run(spec, ReferenceTransport(twice), "refund both", tools,
            needs_approval=frozenset({"payments"}), resume=first.suspension,
            answer=first.suspension.answer(**{"payments": "decline",
                                              "payments#1": "approve"}), now=1.0)
    )

    assert after.halted != "suspended", "a no is an answer, not another wait"
    assert paid == [], f"a refund a person refused must not go out beside one they allowed: {paid}"
    said = [r for step in after.trace() for r in step["results"]]
    assert any("said no" in r for r in said), said
    assert any("cannot hold two answers" in r for r in said), (
        f"the record has to say why the second one stopped too: {said}"
    )


# ─────────────────────────────────────────────── through the author's own line


EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "refund-desk"


@lru_cache(maxsize=1)
def worked_example() -> dict:
    """The example tree, loaded by the real Rust loader (invariant P-1)."""
    import subprocess

    return json.loads(
        subprocess.run(
            ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "show", str(EXAMPLE)],
            cwd=str(EXAMPLE.parents[1]), capture_output=True, text=True, check=True,
        ).stdout
    )


def test_the_authors_own_policy_partly_answered_runs_what_the_person_allowed() -> None:
    """Nothing is passed in: the gate is the author's `policies/approvals.yaml`.

    A test that hands `needs_approval=` in proves the harness works and says
    nothing about whether the author's line reaches it. Here the 300 USD refund
    is stopped by the shipped rule *"a refund over 200 USD is a management
    decision"* — read at `harness.py`'s `asking.waits_for(...)` — and
    `fraud-checker` is stopped because no `ask_member` was supplied and a
    teammate is then work happening elsewhere. Two different reasons to wait, in
    one batch, neither of them written by this file.

    Three, in fact: `resources/payments-server.yaml` gates the payments
    connection, so the batch stops for that first. It is granted on the way past
    because it is `test_connection_consent.py`'s guarantee and not this file's —
    and it is also the sharpest version of what is under test, since the person
    who then approves the refund has already answered one question about this
    same call.

    The person answers the refund. Before the fix that answer bought nothing:
    the teammate still blocked the batch, so the refund they had just approved
    was deferred along with it.
    """
    spec = AgentSpec.from_document(worked_example(), "refund-desk", EXAMPLE)
    ran: list[str] = []
    tools = {
        "zendesk": lambda a: ran.append("zendesk") or "lamp, 6 days ago, broken",
        "payments": lambda a: ran.append("payments") or "refunded 300.00 USD",
    }

    def batch() -> Script:
        return Script([
            Turn("Reading the ticket, refunding, and asking for a fraud check.", (
                ToolCall("zendesk", {"ticket-id": "T-1"}),
                ToolCall("payments", {"order-number": "A-1182", "amount": "300.00 USD"}),
                ToolCall("fraud-checker", {}),
            )),
            Turn("Refunded 300.00 USD."),
        ])

    first = allowing_the_connection(
        spec, lambda: ReferenceTransport(batch()), "refund A-1182", tools, now=0.0
    )
    assert first.halted == "suspended", first.halted
    assert first.suspension.reason == NEEDS_APPROVAL, "the author's 200 USD rule fired"
    assert ran == ["zendesk"], ran

    approved = asyncio.run(
        run(spec, ReferenceTransport(batch()), "refund A-1182", tools, now=0.0,
            resume=first.suspension,
            answer=first.suspension.answer(**{"payments": "yes",
                                              "payments.because": "checked the order"}))
    )
    assert ran == ["zendesk", "payments"], (
        f"the author's policy asked, a person said yes, and nothing moved: {ran}"
    )
    assert approved.halted == "suspended", "and the fraud check is still outstanding"
    assert approved.suspension.reason == WAITING_FOR_ANOTHER_AGENT, (
        approved.suspension.reason
    )
