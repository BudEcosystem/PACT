"""Suspension — one way a run stops, whatever it is stopping for.

Eve parks for five reasons and each is its own mechanism: an approval record
keyed by tool call, an OAuth wait keyed by scope, a subagent wait keyed by child
turn, a session-limit continuation keyed by session, and a deferred input
request. Five state keys, five resume shapes, five guards.

What these hold is that here there is one of each. The strongest of them is
`test_a_new_kind_of_wait_costs_one_line_and_no_new_shape`: if a reason nobody
anticipated needs a second dataclass, a second serialiser or a second guard,
the unification was a rename.
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
from pact_adapters.harness import Step, ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.questions import ANYTHING, Shape  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import (  # noqa: E402
    CONTEXT_TOO_LONG,
    GO_AHEAD,
    NEEDS_APPROVAL,
    NEEDS_PERMISSION,
    OUT_OF_BUDGET,
    REASONS,
    WAITING_FOR_ANOTHER_AGENT,
    Expect,
    PauseRule,
    Resumption,
    Suspension,
    WrongAnswer,
    clears,
    connections_needing_permission,
    correlation_key,
    rule_for,
    suspend,
)
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

TOOLS = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded 40 USD"}
TOOL_SPECS = (ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund"))


def desk(**kw) -> AgentSpec:
    return AgentSpec(
        name="Refund Desk", description="Decides refunds",
        instructions="Decide, then issue the refund.", tools=TOOL_SPECS, **kw
    )


def pay_script() -> Script:
    return Script([
        Turn("Issuing the refund.", (ToolCall("payments", {"amount": 40}),)),
        Turn("Approved: refunded 40 USD."),
    ])


EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "refund-desk"


@lru_cache(maxsize=1)
def worked_example() -> dict:
    """The example tree, loaded by the real Rust loader.

    Cached because several tests below need it and each `pact show` is a
    subprocess. Through the CLI rather than a YAML read, for the reason
    invariant P-1 gives: a Python re-implementation of the Expansion Rule would
    be a second loader, and two loaders drift.
    """
    return json.loads(
        subprocess.run(
            ["cargo", "run", "--quiet", "-p", "pact-cli", "--", "show", str(EXAMPLE)],
            cwd=str(EXAMPLE.parents[1]), capture_output=True, text=True, check=True,
        ).stdout
    )


# ───────────────────────────────────────────────────── one shape, every reason


@pytest.mark.parametrize("reason", REASONS)
def test_every_reason_a_run_can_wait_produces_the_same_shape(reason: str) -> None:
    """The claim, stated directly. Approval, a missing permission, a teammate
    still working, a spent budget and a conversation that will not fit are five
    subsystems in Eve and five values of one field here."""
    parked = suspend(reason, [Expect("decision", GO_AHEAD)], at=3, about=["x"])
    assert type(parked) is Suspension
    assert parked.reason == reason
    assert parked.correlation_key, "every wait is identifiable"
    assert Suspension.from_json(parked.to_json()) == parked


def test_a_new_kind_of_wait_costs_one_line_and_no_new_shape() -> None:
    """A reason nobody anticipated must not need a second dataclass, a second
    serialiser or a second guard. `x-` is the same escape the event lattice
    publishes for subjects, so an author's own wait is not a fork."""
    mine = suspend("x-waiting-for-the-warehouse", [Expect("in-stock", GO_AHEAD)], at=1)
    assert mine.reason == "x-waiting-for-the-warehouse"
    assert Suspension.from_json(mine.to_json()) == mine, "it travels like any other"
    assert mine.answer(**{"in-stock": "yes"}).values == {"in-stock": "yes"}
    assert clears("x-waiting-for-the-warehouse", "yes"), "and a yes means yes"


def test_a_reason_nobody_can_act_on_is_refused_with_the_ones_that_work() -> None:
    with pytest.raises(WrongAnswer) as e:
        suspend("waiting-for-godot")
    assert "is not a reason a run can wait" in str(e.value)
    for known in REASONS:
        assert known in str(e.value), "the message has to list what does work"
    assert "x-" in str(e.value), "and how to add one that does not"


# ───────────────────────────────────────────────────────────── the single guard


def test_an_answer_to_an_older_wait_cannot_resume_the_current_one() -> None:
    """One guard replaces five. A refund approved an hour ago must not clear the
    different refund this run is parked on now, however plausible it looks."""
    first = suspend(NEEDS_APPROVAL, [Expect("payments", GO_AHEAD)], at=0, about=["payments"])
    later = suspend(NEEDS_APPROVAL, [Expect("payments", GO_AHEAD)], at=4, about=["payments"])
    stale = first.answer(payments="yes")

    assert first.accepts(stale)
    assert not later.accepts(stale), "a different wait is a different wait"


def test_answering_the_wrong_wait_says_so_and_runs_nothing() -> None:
    ran: list[int] = []
    tools = {"payments": lambda a: ran.append(1) or "done"}
    parked = asyncio.run(
        run(desk(), ReferenceTransport(pay_script()), "refund me", tools,
            needs_approval=frozenset({"payments"}))
    ).suspension
    assert parked is not None

    with pytest.raises(WrongAnswer) as e:
        asyncio.run(
            run(desk(), ReferenceTransport(pay_script()), "refund me", tools,
                needs_approval=frozenset({"payments"}), resume=parked,
                answer=Resumption("not-this-one", {"payments": "yes"}))
        )
    assert "written for a different wait" in str(e.value)
    assert parked.correlation_key in str(e.value), "name the wait it is actually on"
    assert ran == [], "and nothing ran"


def test_the_same_wait_gets_the_same_name_in_every_framework() -> None:
    """A key derived from what the run was waiting for, not from the process
    that parked it — otherwise resuming is framework-specific and a run parked
    on one adapter cannot be answered on another."""
    a = correlation_key(NEEDS_APPROVAL, 2, ["payments", "zendesk"])
    b = correlation_key(NEEDS_APPROVAL, 2, ["zendesk", "payments"])
    assert a == b, "the order two tools were named in is not part of the wait"
    assert a != correlation_key(NEEDS_APPROVAL, 3, ["payments", "zendesk"])
    assert a != correlation_key(OUT_OF_BUDGET, 2, ["payments", "zendesk"])


# ──────────────────────────────────────────────────────── the deadline, and yes


def test_a_wait_with_no_deadline_never_expires() -> None:
    """Eve's only behaviour, kept — but as one choice among several rather than
    as the absence of any others."""
    parked = suspend(NEEDS_APPROVAL, [Expect("approved", GO_AHEAD)], now=0.0)
    assert not parked.expired(now=10_000_000.0)


def test_nobody_answering_in_time_can_never_become_a_yes() -> None:
    """The property that has to hold structurally rather than by review: no
    combination of settings turns silence into approval."""
    rule = PauseRule.from_question(
        NEEDS_APPROVAL,
        {"answer": {"approved": "yes or no"}, "answer-within": "30m",
         "if-nobody-answers": "decline", "asked-of": ["support-leads"]},
    )
    parked = suspend(NEEDS_APPROVAL, at=0, about=["payments"], now=0.0, rule=rule)
    assert parked.expired(now=1801.0)
    assert parked.if_nobody_answers in ("decline", "escalate", "stop-and-say-so")
    assert not clears(NEEDS_APPROVAL, parked.if_nobody_answers)


def test_a_timeout_that_could_approve_is_refused_where_it_is_written() -> None:
    with pytest.raises(WrongAnswer) as e:
        PauseRule.from_question(
            NEEDS_APPROVAL,
            {"answer": {"approved": "yes or no"}, "if-nobody-answers": "approve"},
        )
    assert "no way to approve on a timeout" in str(e.value)
    assert "decline" in str(e.value), "the fix has to name what can be typed"


def test_escalating_mints_a_new_name_so_the_late_answer_cannot_land() -> None:
    """Escalation is a different question put to different people. Keeping the
    old name would let the answer the first audience never gave arrive after the
    second audience had been asked."""
    parked = suspend(NEEDS_APPROVAL, [Expect("approved", GO_AHEAD)], at=1, about=["payments"])
    passed_on = parked.escalate(now=99.0)
    assert passed_on.correlation_key != parked.correlation_key
    assert not passed_on.accepts(parked.answer(approved="yes"))
    assert passed_on.steps == parked.steps, "the run itself is untouched"


# ─────────────────────────────────────────────────────── the answer, and typing


def test_an_answer_outside_what_was_asked_is_refused_saying_what_to_type() -> None:
    parked = suspend(NEEDS_APPROVAL, [Expect("approved", GO_AHEAD)])
    with pytest.raises(WrongAnswer) as e:
        parked.answer(approved="probably")
    assert "the answer to 'approved'" in str(e.value)
    assert "probably" in str(e.value)
    assert "`approved: " in str(e.value), "the fix must be typeable"


def test_a_half_answered_wait_says_which_line_is_missing_and_what_to_type() -> None:
    parked = suspend(
        NEEDS_APPROVAL, [Expect("approved", GO_AHEAD), Expect("because", ANYTHING)]
    )
    with pytest.raises(WrongAnswer) as e:
        parked.answer(approved="yes")
    assert "missing 'because'" in str(e.value)
    assert "`because:" in str(e.value), "the fix must be typeable"


def test_answering_something_that_was_never_asked_is_refused() -> None:
    parked = suspend(OUT_OF_BUDGET, [Expect("keep-going", GO_AHEAD)])
    with pytest.raises(WrongAnswer) as e:
        parked.answer(approved="yes")
    assert "did not ask for 'approved'" in str(e.value)
    assert "keep-going" in str(e.value), "say what it did ask for"


def test_the_word_the_schema_tells_an_author_to_type_is_a_word_that_works() -> None:
    """`answer: {approved: yes or no}` is what the schema's help text says to
    write, so `yes` has to clear the gate. A vocabulary the harness accepts but
    nobody can author is not an authoring surface."""
    assert Expect.parse("approved", "yes or no").shape == Shape("yes-or-no")
    for reason in (NEEDS_APPROVAL, NEEDS_PERMISSION, OUT_OF_BUDGET, CONTEXT_TOO_LONG):
        assert clears(reason, "yes"), reason
        assert not clears(reason, "no"), reason
        assert not clears(reason, ""), f"{reason}: silence is not a yes"


# ────────────────────────────────────────────────────────────── across a death


def test_a_wait_survives_the_process_that_parked_it() -> None:
    """Durability is the whole point: an approval gate only means something if
    the process may die while a person thinks."""
    parked = suspend(NEEDS_APPROVAL, [Expect("approved", GO_AHEAD)], at=2, about=["payments"])
    parked.awaiting = (ToolCall("payments", {"amount": 40}),)
    parked.steps = [Step(index=0, text="checking", tool_calls=(ToolCall("zendesk", {}),),
                         tool_results=("lamp, broken",))]
    parked.history = [{"role": "user", "content": "refund me"}]
    parked.completed = {"zendesk": "lamp, broken"}
    key = parked.correlation_key

    blob = parked.to_json()
    del parked

    back = Suspension.from_json(blob)
    assert back.reason == NEEDS_APPROVAL
    assert back.awaiting[0].args == {"amount": 40}
    assert back.completed == {"zendesk": "lamp, broken"}
    assert back.steps[0].tool_results == ("lamp, broken",)
    assert back.asks[0].shape == GO_AHEAD, "it must ask for the same typed thing"
    assert json.loads(blob)["correlation-key"] == key


# ─────────────────────────────────────────────────── authored, not hard-coded


def test_the_waiting_rules_come_from_the_questions_the_author_already_wrote() -> None:
    """No `pauses/` kind exists, on purpose. A question already carries the
    wording, the answer shape, who is asked, the deadline and what follows it —
    a second kind holding the same five things would be two places to write one
    thing and two places for them to disagree."""
    doc = {
        "questions": {
            "keep-going": {"says": "Keep going?", "answer": {"keep-going": "yes or no"},
                           "answer-within": "10m", "if-nobody-answers": "stop-and-say-so",
                           "asked-of": ["support-leads"]},
            "is-this-ok": {"says": "Check this.", "answer": {"approved": "yes or no"},
                           "answer-within": "30m", "if-nobody-answers": "escalate",
                           "asked-of": ["support-leads"]},
        },
        "policies": {"approvals": {"ask-a-person": [{"question": "is-this-ok"}]}},
        "agents": {"desk": {"policy": "approvals",
                            "limits": {"when-it-runs-out": "ask-a-person", "asks": "keep-going"}}},
    }
    rules = PauseRule.from_document(doc, "desk")

    budget = rule_for(rules, OUT_OF_BUDGET)
    assert budget is not None and budget.waits_for == 600.0
    assert budget.if_nobody_answers == "stop-and-say-so"
    assert budget.who_can_answer == ("support-leads",)

    approval = rule_for(rules, NEEDS_APPROVAL)
    assert approval is not None and approval.waits_for == 1800.0
    assert approval.if_nobody_answers == "escalate"
    assert [e.name for e in approval.asks_for] == ["approved"]


def test_the_worked_example_can_be_waited_on_without_anyone_writing_code() -> None:
    """D14: the deadline on a refund approval and on a spent budget are both
    things a support lead sets in YAML. This reads them off the real example."""
    rules = PauseRule.from_document(worked_example(), "refund-desk")

    approval = rule_for(rules, NEEDS_APPROVAL)
    assert approval is not None, "the example's approvals policy names a question"
    assert approval.waits_for == 1800.0, "30m, from questions/is-this-ok.yaml"
    assert approval.if_nobody_answers == "escalate"

    budget = rule_for(rules, OUT_OF_BUDGET)
    assert budget is not None, "the example's limits name a question"
    assert budget.waits_for == 600.0, "10m, from questions/keep-going.yaml"
    assert budget.if_nobody_answers == "stop-and-say-so"


def test_a_connection_that_has_not_been_granted_yet_is_a_wait_a_person_can_answer() -> None:
    """Eve's OAuth park, which had no authoring surface here at all: a resource
    carried a credential reference and nothing said what to do when the
    credential was not there. `asks-to-connect` names the question, and the wait
    is then the same wait as every other."""
    #
    # The `tools:` entry and the `uses:` line are not decoration. A rule is
    # derived for the agent that can REACH the server, and this document used to
    # carry neither — so it asserted only that some resource somewhere in the
    # workspace had said `asks-to-connect:`, which is what
    # `connections_needing_permission` stopped being enough.
    doc = {
        "questions": {"may-we-connect": {"says": "Allow this connection?",
                                         "answer": {"approved": "yes or no"},
                                         "answer-within": "1h",
                                         "if-nobody-answers": "decline",
                                         "asked-of": ["support-leads"]}},
        "resources": {"payments": {"resource-kind": "mcp-server",
                                   "asks-to-connect": "may-we-connect"}},
        "tools": {"payments": {"connect": "payments"}},
        "agents": {"desk": {"uses": ["payments"]}},
    }
    rule = rule_for(PauseRule.from_document(doc, "desk"), NEEDS_PERMISSION)
    assert rule is not None, "the resource's question must become a waiting rule"
    assert rule.waits_for == 3600.0
    assert rule.if_nobody_answers == "decline"

    parked = suspend(NEEDS_PERMISSION, at=0, about=["payments"], now=0.0, rule=rule)
    assert [e.name for e in parked.asks] == ["approved"]
    assert parked.expired(now=3601.0)
    assert not clears(NEEDS_PERMISSION, rule.if_nobody_answers)


def test_a_place_that_can_stop_and_ask_has_a_question_to_ask() -> None:
    """A run that parks with nothing to show is indistinguishable from a hang,
    so every `ask-a-person` in the schema is paired with a line naming what gets
    asked. Held here because it is a property of the file, not of one field."""
    text = (Path(__file__).resolve().parents[3] / "spec" / "schema.yaml").read_text()
    assert text.count("which question to put to") >= 3, (
        "each place that can stop and ask must name what it asks"
    )
    assert "asks-to-connect" in text, "a connection that needs granting must be askable"


def test_stopping_to_ask_with_no_question_to_ask_is_refused_before_the_run() -> None:
    """The worst outcome available: a run parked with nothing to show, which
    from the outside is indistinguishable from a hang. Caught where the rules
    are read, because the schema cannot say "required when another field has
    this value" without growing a conditional language."""
    doc = {"agents": {"desk": {"limits": {"when-it-runs-out": "ask-a-person"}}}}
    with pytest.raises(WrongAnswer) as e:
        PauseRule.from_document(doc, "desk")
    assert "names no question to put to them" in str(e.value)
    assert "`asks:" in str(e.value), "the fix must be typeable"
    assert "questions/" in str(e.value), "and say where the question lives"


def test_a_wait_with_no_authored_rule_waits_rather_than_deciding_for_itself() -> None:
    """The conservative direction. A missing rule must never become "carry on"."""
    rules = PauseRule.from_document({"agents": {"desk": {}}}, "desk")
    assert rules == ()
    parked = suspend(NEEDS_APPROVAL, [Expect("approved", GO_AHEAD)],
                     rule=rule_for(rules, NEEDS_APPROVAL))
    assert not parked.expired(now=10_000_000.0)
    assert parked.if_nobody_answers == "stop-and-say-so"


# ───────────────────────────────────────────────────────── wired into the loop


def test_approval_and_delegation_park_the_same_way() -> None:
    """Two of Eve's five park kinds, driven through the real loop, producing one
    halt state and one shape. What differs is the reason and nothing else."""
    parked_for = {}

    parked_for[NEEDS_APPROVAL] = asyncio.run(
        run(desk(), ReferenceTransport(pay_script()), "refund me", TOOLS,
            needs_approval=frozenset({"payments"}))
    )

    delegating = AgentSpec(name="a", description="d", instructions="i",
                           team={"policy-checker": "checks the policy"})
    asks_teammate = Script([Turn("asking", (ToolCall("policy-checker", {}),)), Turn("done")])
    parked_for[WAITING_FOR_ANOTHER_AGENT] = asyncio.run(
        run(delegating, ReferenceTransport(asks_teammate), "refund me", {})
    )

    for reason, got in parked_for.items():
        assert got.halted == "suspended", f"{reason} halted as {got.halted}"
        assert got.suspension is not None and got.suspension.reason == reason
        assert type(got.suspension) is Suspension


def test_a_teammate_who_is_not_here_is_waited_for_rather_than_reported_missing() -> None:
    """Delegation is a wait, not an error. Eve gives it a bespoke park kind and
    a child-turn state key; here it is the same suspension as everything else,
    and the teammate's reply is the result of the call that asked for it."""
    spec = AgentSpec(name="a", description="d", instructions="i",
                     team={"policy-checker": "checks the policy"})
    script = Script([Turn("asking", (ToolCall("policy-checker", {}),)),
                     Turn("Approved, the policy allows it.")])

    first = asyncio.run(run(spec, ReferenceTransport(script), "refund me", {}))
    assert first.halted == "suspended"
    assert first.suspension.reason == WAITING_FOR_ANOTHER_AGENT

    blob = first.suspension.to_json()
    del first

    parked = Suspension.from_json(blob)
    reply = Resumption(parked.correlation_key, {"policy-checker": "the policy allows it"})
    done = asyncio.run(
        run(spec, ReferenceTransport(script), "refund me", {}, resume=parked, answer=reply)
    )
    assert done.halted == "final"
    assert done.steps[0].tool_results == ("the policy allows it",), (
        "the teammate's reply IS the result of the call that delegated to them"
    )


def _budget_doc(steps: int = 2) -> dict:
    return {
        "questions": {"keep-going": {"says": "Keep going?",
                                     "answer": {"keep-going": "yes or no"},
                                     "answer-within": "10m",
                                     "if-nobody-answers": "stop-and-say-so"}},
        "agents": {"desk": {"name": "Desk", "description": "d", "instructions": "i",
                            "limits": {"steps-at-most": steps,
                                       "when-it-runs-out": "ask-a-person",
                                       "asks": "keep-going"}}},
    }


def test_a_run_that_ran_out_of_budget_can_be_given_more_by_a_person() -> None:
    """Eve's session-limit continuation, as the same primitive. `ask-a-person`
    on `when-it-runs-out` is what turns a ceiling into a question, and the
    question is a plain "keep going?" rather than an approval in disguise."""
    spec = AgentSpec.from_document(_budget_doc(), "desk")
    assert spec.when_it_runs_out == "ask-a-person"

    forever = Script([Turn("still working", (ToolCall("zendesk", {}),))])
    out = asyncio.run(run(spec, ReferenceTransport(forever), "hello", TOOLS))
    assert out.halted == "suspended"
    assert out.suspension.reason == OUT_OF_BUDGET
    assert len(out.steps) == spec.max_steps

    more = out.suspension.answer(**{"keep-going": "yes"})
    resumed = asyncio.run(
        run(spec, ReferenceTransport(forever), "hello", TOOLS,
            resume=out.suspension, answer=more)
    )
    assert len(resumed.steps) == 2 * spec.max_steps, "a fresh budget of the same size"


def test_saying_stop_to_a_spent_budget_ends_the_run_rather_than_re_parking() -> None:
    spec = AgentSpec.from_document(_budget_doc(), "desk")
    forever = Script([Turn("still working", (ToolCall("zendesk", {}),))])
    out = asyncio.run(run(spec, ReferenceTransport(forever), "hello", TOOLS))

    stopped = asyncio.run(
        run(spec, ReferenceTransport(forever), "hello", TOOLS, resume=out.suspension,
            answer=out.suspension.answer(**{"keep-going": "no"}))
    )
    assert stopped.halted == "out-of-budget", (
        "a run that asked for more and was told no is not a run that finished"
    )
    assert stopped.suspension is None


def test_a_deadline_passing_stops_the_run_and_says_which_wait_it_was() -> None:
    """Eve parks indefinitely, so a run waiting on an approver who has left the
    company waits forever. Here the wait ends, and says what it was waiting on."""
    parked = asyncio.run(
        run(desk(), ReferenceTransport(pay_script()), "refund me", TOOLS,
            needs_approval=frozenset({"payments"}), now=0.0)
    ).suspension
    parked.waits_for = 1800.0
    parked.if_nobody_answers = "stop-and-say-so"

    late = asyncio.run(
        run(desk(), ReferenceTransport(pay_script()), "refund me", TOOLS,
            needs_approval=frozenset({"payments"}), resume=parked, now=3600.0)
    )
    assert late.halted == "gave-up-waiting"
    assert NEEDS_APPROVAL in late.output, "say which wait was abandoned"


# ────────────────────────────────────── the connection nobody has granted yet


def _connection_gates(doc: dict, agent_key: str = "refund-desk") -> dict[str, str]:
    """Which calls wait for a connection, derived from the document.

    Nothing here is a tool name somebody typed. `connections_needing_permission`
    walks the three lines the author wrote — `uses:`, `connect:`,
    `asks-to-connect:` — and this turns the result into the map the harness
    already takes. Handing it over the `gates=` argument is the ONE piece a host
    still supplies, and it is the piece named in `needs_wiring`: until
    `AgentSpec` carries it, `run()` seeds `gated` from `needs_approval=`,
    `gates=` and the team, and from nothing the author wrote about connections.
    Delete `asks-to-connect:` from `resources/payments-server.yaml` and this is empty,
    which is what makes the tests below tests of the author's line rather than
    of the harness's argument list.
    """
    return {name: NEEDS_PERMISSION for name in connections_needing_permission(doc, agent_key)}


def a_refund_that_reaches_payments() -> Script:
    return Script([
        Turn("Issuing the refund.",
             (ToolCall("payments", {"order-number": "A-1182", "amount": "40.00 USD"}),)),
        Turn("Approved: refunded 40.00 USD."),
    ])


def test_the_worked_example_says_which_connection_has_to_be_allowed_before_it_is_used() -> None:
    """The fixture this whole area was missing. `asks-to-connect:` was in the
    schema, was one of the checked references, and had a test — but no document
    under `examples/` wrote it, so the one Eve park kind PACT claims to have
    generalised was exercised only by a document a test built inline.

    Read as the author wrote it, one hop at a time: `agents/refund-desk` uses
    the TOOL `payments`, `tools/payments.yaml` connects to the SERVER
    `payments-server`, and `resources/payments-server.yaml` says a person is
    asked first. The two names differ on purpose — while both were spelled
    `payments`, anything that skipped the middle hop got the right answer by
    coincidence, and `LoadReport` did exactly that.
    """
    doc = worked_example()
    assert connections_needing_permission(doc, "refund-desk") == {"payments": "may-we-connect"}

    # And only for an agent that can reach it. `fraud-checker` uses `zendesk`
    # and nothing else, so a payments connection is not a wait it can have.
    assert connections_needing_permission(doc, "fraud-checker") == {}
    assert rule_for(PauseRule.from_document(doc, "fraud-checker"), NEEDS_PERMISSION) is None


def test_the_connection_question_governs_the_wait_with_nothing_passed_in() -> None:
    """Everything about the wait except the fact of it comes from
    `questions/may-we-connect.yaml`, reached from the resource's one line. Held
    separately from the run below because this is the part that works today:
    `spec.pauses` is built by `AgentSpec.from_document` and read at
    `harness.py:902`, `rule = rule_for(spec.pauses, reason)`."""
    spec = AgentSpec.from_document(worked_example(), "refund-desk")
    rule = rule_for(spec.pauses, NEEDS_PERMISSION)

    assert rule is not None, "the resource's question must reach the spec"
    assert rule.waits_for == 3600.0, "1h, from questions/may-we-connect.yaml"
    assert rule.who_can_answer == ("support-leads", "support-manager")
    assert rule.if_nobody_answers == "stop-and-say-so"
    assert [e.name for e in rule.asks_for] == ["approved", "because"]
    assert not clears(NEEDS_PERMISSION, rule.if_nobody_answers), (
        "no timeout action may read as a yes"
    )


def test_a_run_that_reaches_the_payments_connection_waits_and_carries_on_after_a_yes() -> None:
    """Eve's scoped-OAuth park, driven end to end over the real example. The
    run stops before anything goes over the connection, the person is told what
    they are being asked, and a yes continues the same run rather than starting
    a new one."""
    doc = worked_example()
    spec = AgentSpec.from_document(doc, "refund-desk")
    ran: list[dict] = []
    tools = {"zendesk": lambda a: "lamp, broken",
             "payments": lambda a: ran.append(dict(a)) or "refunded 40.00 USD"}

    parked = asyncio.run(
        run(spec, ReferenceTransport(a_refund_that_reaches_payments()), "refund A-1182",
            tools, gates=_connection_gates(doc), now=0.0)
    )
    assert parked.halted == "suspended"
    assert ran == [], "nothing may go over a connection nobody has allowed"

    waiting = parked.suspension
    assert waiting.reason == NEEDS_PERMISSION
    assert waiting.who_can_answer == ("support-leads", "support-manager"), (
        "the audience is the question's `asked-of:`, not the harness's guess"
    )
    assert waiting.waits_for == 3600.0
    assert waiting.if_nobody_answers == "stop-and-say-so"
    assert [e.name for e in waiting.asks] == ["payments", "payments.because"]

    # A run parked with nothing to read is, from the outside, a run that has
    # hung — so the park has to carry words, and it has to carry the values the
    # decision needs. Both questions in play name the same two under `shows:`,
    # which is why this holds regardless of which one won.
    assert waiting.in_words.strip(), "a person has to be able to read what they are answering"
    assert '"A-1182"' in waiting.in_words and '"40.00 USD"' in waiting.in_words, (
        "a connection is granted FOR something, and that something is quoted data"
    )
    #
    # WHICH wording arrives, which for a round was reported here rather than
    # asserted. On this exact run `in_words` used to open "Please check this
    # before it happens." with "answer within: 30m" — the approval question —
    # while the wait it belongs to obeyed `may-we-connect`: an hour, and the
    # manager as well as the leads. The gate was asked which question to put
    # without being told WHY the run stopped, and `payments` is a name carrying
    # rules for two different reasons, so it answered with the one that gets
    # asked most and a person was shown one question and answered another.
    # `Gate.for_call` now takes the reason and `Rule.for_reason` says which wait
    # a rule's question is written for, so this is a guarantee rather than a
    # note.
    assert "May we use the payments connection for this?" in waiting.in_words, (
        f"the connection question is what a connection park puts: {waiting.in_words!r}"
    )
    assert "answer within: 1h" in waiting.in_words, (
        "the deadline the person reads is the one the wait actually obeys"
    )

    said_yes = waiting.answer(**{"payments": "yes", "payments.because": "known supplier"})
    done = asyncio.run(
        run(spec, ReferenceTransport(a_refund_that_reaches_payments()), "refund A-1182",
            tools, gates=_connection_gates(doc), resume=waiting, answer=said_yes, now=1.0)
    )
    assert done.halted == "final"
    assert ran == [{"order-number": "A-1182", "amount": "40.00 USD"}], (
        "one refund, issued once, after the connection was allowed"
    )


def test_nobody_allowing_the_connection_ends_the_run_instead_of_connecting_anyway() -> None:
    """`if-nobody-answers: stop-and-say-so` is a line in the question, and this
    is it doing something. Eve parks indefinitely here — a scoped authorisation
    nobody grants is a run that waits forever — and the one outcome that must
    never be reachable is the connection being used because the hour was up."""
    doc = worked_example()
    spec = AgentSpec.from_document(doc, "refund-desk")
    ran: list[dict] = []
    tools = {"zendesk": lambda a: "lamp, broken",
             "payments": lambda a: ran.append(dict(a)) or "refunded 40.00 USD"}

    waiting = asyncio.run(
        run(spec, ReferenceTransport(a_refund_that_reaches_payments()), "refund A-1182",
            tools, gates=_connection_gates(doc), now=0.0)
    ).suspension

    late = asyncio.run(
        run(spec, ReferenceTransport(a_refund_that_reaches_payments()), "refund A-1182",
            tools, gates=_connection_gates(doc), resume=waiting, now=3601.0)
    )
    assert late.halted == "gave-up-waiting"
    assert NEEDS_PERMISSION in late.output, "say which wait was abandoned"
    assert ran == [], "an hour of silence is not a grant"


def test_saying_no_to_the_connection_ends_the_run_rather_than_connecting() -> None:
    """A refusal is not a clearance, and it is not a delay either.

    The `approved` line of the question is what makes "no" sayable at all: a
    question with no `approved` field is taken as granted the moment it is
    answered, so this asserts the shape the fixture chose as much as the
    harness's reading of it.

    It asserted `suspended` for as long as the loop read one bool for "may this
    go past?", which made a refusal and silence the same value and re-parked on
    both. A refusal ends the wait, is written into the run's own record in the
    person's words, and never lets the call happen — which is the one thing the
    old reading and the new one agree on, and the assertion that was already
    here.
    """
    doc = worked_example()
    spec = AgentSpec.from_document(doc, "refund-desk")
    ran: list[dict] = []
    tools = {"zendesk": lambda a: "lamp, broken",
             "payments": lambda a: ran.append(dict(a)) or "refunded 40.00 USD"}

    waiting = asyncio.run(
        run(spec, ReferenceTransport(a_refund_that_reaches_payments()), "refund A-1182",
            tools, gates=_connection_gates(doc), now=0.0)
    ).suspension
    said_no = waiting.answer(**{"payments": "no", "payments.because": "not this account"})

    after = asyncio.run(
        run(spec, ReferenceTransport(a_refund_that_reaches_payments()), "refund A-1182",
            tools, gates=_connection_gates(doc), resume=waiting, answer=said_no, now=1.0)
    )
    assert after.halted != "suspended", "a no is an answer, not another wait"
    assert ran == [], "and nothing went over the connection"
    said = json.dumps(after.trace())
    assert "refused:" in said and "not this account" in said, (
        f"the record has to say a person refused, and why: {said}"
    )


# ───────────────────────── what the screen says, and what the wait will take


def test_the_screen_a_park_puts_up_asks_for_the_names_the_wait_is_keyed_on() -> None:
    """The one park that did not go through `shown.words_for`, and what it cost.

    A tool park clears the rule's contract (`replace(rule, asks_for=())`) so that
    two calls blocked in the same step cannot answer for one another — the wait
    is then keyed on `payments` and `payments.because`. But the screen was
    rendered straight off `Question.for_person()`, which prints the author's own
    `answer:` field names, so it read *"answer with: approved (yes or no),
    because (some text)"* and `w.answer(approved="yes", because="ok")` came back
    *"this wait did not ask for 'approved'"*.

    That is exactly the defect `words_for`'s `contract=` argument exists to
    prevent — its docstring names it: *"how 'answer with: approved' comes to
    appear above a wait keyed on 'decision'"* — and this park was the one not
    passing it. Held on every name the screen offers, so a screen and a contract
    cannot drift apart again by one field.
    """
    doc = worked_example()
    spec = AgentSpec.from_document(doc, "refund-desk")
    waiting = asyncio.run(
        run(spec, ReferenceTransport(a_refund_that_reaches_payments()), "refund A-1182",
            TOOLS, gates=_connection_gates(doc), now=0.0)
    ).suspension

    offered = waiting.in_words.rsplit("answer with: ", 1)[1]
    for e in waiting.asks:
        assert f"{e.name} (" in offered, (
            f"the wait is keyed on {e.name!r} and the screen does not say so: {offered!r}"
        )
    # And the answer the screen tells somebody to type is one the wait takes.
    typed = {e.name: ("yes" if e.shape.kind == "yes-or-no" else "because I say so")
             for e in waiting.asks}
    assert waiting.answer(**typed).values == typed


def test_a_wait_for_another_agent_borrows_nobodys_audience_or_deadline() -> None:
    """§7.14 WAIT-2 configures nothing for this reason, and it must show nothing.

    `questions_for` registers `teamwork.asks` against every member's name, for
    the park where a member FAILED and the author said to ask. A run merely
    WAITING on a teammate this process cannot run is a different park with no
    rule at all — so it used to render the failure question's wording, its
    `asked of: support-leads` and its `answer within: 30m` over a wait whose
    `who_can_answer` was empty and whose `waits_for` was `None`. An audience and
    a deadline borrowed from another question entirely, which is the same mistake
    `Rule.for_reason` was added to fix one park over.
    """
    doc = worked_example()
    spec = AgentSpec.from_document(doc, "refund-desk")
    asks_teammate = Script([
        Turn("Asking the fraud team.", (ToolCall("fraud-checker", {}),)),
        Turn("Done."),
    ])
    waiting = asyncio.run(
        run(spec, ReferenceTransport(asks_teammate), "refund A-1182", TOOLS, now=0.0)
    ).suspension

    assert waiting.reason == WAITING_FOR_ANOTHER_AGENT
    assert waiting.who_can_answer == () and waiting.waits_for is None
    assert "asked of:" not in waiting.in_words, waiting.in_words
    assert "answer within:" not in waiting.in_words, waiting.in_words
    assert "Please check this before it happens." not in waiting.in_words, (
        "the failure question's wording is not this park's"
    )
    # It still shows something: a run stopped with nothing to read is, from the
    # outside, indistinguishable from a run that has hung.
    assert waiting.in_words.strip()
    # And the teammate's reply — free text, not a yes-or-no — is what clears it.
    assert [e.name for e in waiting.asks] == ["fraud-checker"]
    assert waiting.answer(**{"fraud-checker": "no concerns"}).values == {
        "fraud-checker": "no concerns"
    }


# There used to be a test here that a connection the author gated and the run did
# NOT stop for was at least reported on `RunResult.unenforced`. It has gone with
# the gap it reported: `asks-to-connect:` is a `Rule` in the gate now, so the run
# parks before anything goes over the connection and there is nothing left to
# report. Its guarantee is `test_connection_consent.py`'s, which asserts the wait
# rather than the apology for not having one.


def test_two_calls_to_one_tool_in_one_step_are_two_waits_with_two_screens() -> None:
    """The approver sees the call they are approving, and answers only that one.

    `args_of` was `{c.name: c.args for c in calls}` — keyed by TOOL NAME, last
    wins — so two `payments` calls in one step collapsed onto one entry. Measured
    on the worked example's own approvals policy before the fix: a 300 USD refund
    and a 250 USD one parked showing the person `amount: "250.00 USD"` printed
    TWICE, and answering `payments: yes` executed BOTH, including a figure they
    were never shown. `rulings.where`'s own docstring claims "two calls blocked
    in the same step cannot answer for one another"; it was true only of two
    DIFFERENT tools.

    Both figures are over the author's 200 USD line, because that is what makes
    this two APPROVALS. A refund under it is not a wait at all — `more-than: 200
    USD` has to mean 200 in both directions — so a small second call would have
    tested one screen and a silence.
    """
    doc = worked_example()
    spec = AgentSpec.from_document(doc, "refund-desk", EXAMPLE)
    paid: list[dict] = []
    tools = {"zendesk": lambda a: "ok",
             "payments": lambda a: paid.append(dict(a)) or f"paid {a.get('amount')}"}

    def script() -> Script:
        return Script([
            Turn("issuing both", [
                ToolCall("payments", {"order-number": "A-300", "amount": "300.00 USD"}),
                ToolCall("payments", {"order-number": "A-250", "amount": "250.00 USD"}),
            ]),
            Turn("done"),
        ])

    # Two calls over one connection are ONE consent — the question's own file
    # says "asked once, not once per customer" — so it is granted here and what
    # is under test below is the pair of approvals it uncovers.
    out = allowing_the_connection(
        spec, lambda: ReferenceTransport(script()), "two refunds", tools, now=0.0
    )

    assert out.halted == "suspended", out.halted
    assert not paid, "nothing may move before the person has seen it"
    asked = [e.name for e in out.suspension.asks]
    assert "payments" in asked and "payments#1" in asked, asked

    # Each screen carries its OWN figure, and both figures are on the page.
    screen = out.suspension.in_words
    assert '"300.00 USD"' in screen
    assert '"250.00 USD"' in screen
    assert '"A-300"' in screen and '"A-250"' in screen

    # One yes cannot stand for two. Answering only `payments` is refused by name,
    # which is the whole of "two calls blocked in the same step cannot answer for
    # one another" — before this, that one word released both calls.
    with pytest.raises(WrongAnswer) as refused:
        out.suspension.answer(**{"payments": "yes", "payments.because": "checked"})
    assert "payments#1" in str(refused.value), str(refused.value)

    # Answered separately, both go through — each against the figure the person
    # was actually shown.
    resumed = asyncio.run(
        run(spec, ReferenceTransport(script()), "two refunds", tools, now=0.0,
            resume=out.suspension,
            answer=out.suspension.answer(**{
                "payments": "yes", "payments.because": "checked the order",
                "payments#1": "yes", "payments#1.because": "checked that one too",
            }))
    )
    # And then the example's OWN interceptor has the last word: `stop-runaway-refunds`
    # says one refund per request, so the second call ends the run rather than
    # paying. Two mechanisms, in the order the author wrote them — the person is
    # asked about each call separately, and the rule still stops the second.
    assert resumed.halted == "stopped-by-rule", resumed.halted
    assert [p["amount"] for p in paid] == ["300.00 USD"], paid
    assert "second refund" in resumed.output.lower(), resumed.output


# There used to be a test here that a `spends-money: yes` action no approval rule
# names was reported on the spec. It has moved rather than gone: whether an action
# is guarded is a fact about TWO documents read together — a tool file and a
# policy file — which is `pact check`'s question, not a run's, and an author now
# hears it before a customer is waiting rather than in a run afterwards. Its
# guarantee is `crates/pact-loader/src/money.rs` and
# `crates/pact-cli/tests/money_that_moves_with_nobody_asked.rs`.
