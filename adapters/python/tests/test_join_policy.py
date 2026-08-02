"""Join policy — what happens between asking the team and carrying on.

Eve answers this once, in code: park the parent until every delegated child
resolves, start them one after another, split the token budget evenly. Three
decisions, none of them sayable by an author, and each wrong for some system
that has to ship anyway.

These tests are named for the guarantee each one holds, and every one of them
would fail against Eve's behaviour — which is the point: a join policy that
only *reads* differently is decoration.
"""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.delegation import (  # noqa: E402
    ANSWERED,
    CANCELLED,
    FAILED,
    NOT_ASKED,
    OUT_OF_TIME,
    BadTeamwork,
    Divides,
    Grant,
    OnFailure,
    OverBudget,
    Starts,
    Teamwork,
    Waits,
    ask_team,
)
from pact_adapters.harness import ToolCall, delegate_by_running, run  # noqa: E402
from pact_adapters.interceptors import Chain, guard  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.anthropic_transport import AnthropicTransport  # noqa: E402
from pact_adapters.transports.autogen_transport import AutoGenTransport  # noqa: E402
from pact_adapters.transports.langchain_transport import LangChainTransport  # noqa: E402
from pact_adapters.transports.langgraph_transport import LangGraphTransport  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.openai_agents_transport import OpenAIAgentsTransport  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import PydanticAITransport  # noqa: E402

TRANSPORTS = {
    "reference": ReferenceTransport,
    "pydantic-ai": PydanticAITransport,
    "langgraph": LangGraphTransport,
    "langchain": LangChainTransport,
    "autogen": AutoGenTransport,
    "openai-agents": OpenAIAgentsTransport,
    "anthropic": AnthropicTransport,
}

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

TEAM = ("policy-checker", "fraud-checker", "history-checker")


def answering(delays: dict[str, float] | None = None, failing: set[str] = frozenset()):
    """A team where each member takes a known time and may fail."""
    delays = delays or {}

    async def ask(grant: Grant) -> str:
        await asyncio.sleep(delays.get(grant.member, 0.0))
        if grant.member in failing:
            raise RuntimeError("the ticket system is down")
        return f"{grant.member} says yes"

    return ask


def state_of(handoff, member: str) -> str:
    return next(a.state for a in handoff.answers if a.member == member)


# ─────────────────────────────────────────────────────────── how much is enough


def test_waiting_for_everyone_carries_on_only_when_the_last_one_is_back() -> None:
    h = asyncio.run(ask_team(TEAM, answering({"history-checker": 0.03}), Teamwork()))
    assert h.satisfied
    assert [state_of(h, m) for m in TEAM] == [ANSWERED, ANSWERED, ANSWERED]


def test_waiting_for_anyone_carries_on_after_the_first_reply_of_any_kind() -> None:
    """`anyone` counts a failure as a reply, which is what makes it different
    from `the-first-good-answer` rather than a synonym for it."""
    h = asyncio.run(
        ask_team(
            TEAM,
            answering({"policy-checker": 0.0, "fraud-checker": 1.0, "history-checker": 1.0},
                      failing={"policy-checker"}),
            Teamwork(waits_for=Waits.ANYONE),
        )
    )
    assert state_of(h, "policy-checker") == FAILED
    assert h.satisfied, "a failure is still a reply under `anyone`"
    assert state_of(h, "fraud-checker") == CANCELLED


def test_the_first_good_answer_keeps_waiting_past_the_ones_that_go_wrong() -> None:
    h = asyncio.run(
        ask_team(
            TEAM,
            answering({"policy-checker": 0.0, "fraud-checker": 0.02, "history-checker": 1.0},
                      failing={"policy-checker"}),
            Teamwork(waits_for=Waits.FIRST_GOOD),
        )
    )
    assert h.satisfied
    assert state_of(h, "policy-checker") == FAILED
    assert state_of(h, "fraud-checker") == ANSWERED
    assert [a.member for a in h.good] == ["fraud-checker"]


def test_a_quorum_stops_waiting_once_enough_have_answered() -> None:
    """Eve has no way to say this: two of three agreeing still waits for the
    third, however long it takes."""
    h = asyncio.run(
        ask_team(
            TEAM,
            answering({"policy-checker": 0.0, "fraud-checker": 0.01, "history-checker": 5.0}),
            Teamwork(waits_for=Waits.ENOUGH, enough_is=2),
        )
    )
    assert h.satisfied
    assert len(h.good) == 2
    assert state_of(h, "history-checker") == CANCELLED


def test_a_race_carries_on_at_the_deadline_with_whatever_arrived() -> None:
    started = time.monotonic()
    h = asyncio.run(
        ask_team(
            TEAM,
            answering({"policy-checker": 0.0, "fraud-checker": 0.01, "history-checker": 5.0}),
            Teamwork(waits_for=Waits.IN_TIME, gives_up_after=0.15),
        )
    )
    elapsed = time.monotonic() - started
    assert elapsed < 1.0, f"the deadline did not fire: waited {elapsed:.2f}s"
    assert h.satisfied
    assert state_of(h, "history-checker") == OUT_OF_TIME


def test_a_race_that_nobody_wins_is_a_failure_and_says_so() -> None:
    """"Nothing arrived" must not read like "everyone agreed"."""
    h = asyncio.run(
        ask_team(TEAM, answering({m: 5.0 for m in TEAM}),
                 Teamwork(waits_for=Waits.IN_TIME, gives_up_after=0.05))
    )
    assert not h.satisfied
    assert "nobody answered in time" in h.why


def test_a_member_who_did_not_answer_is_named_rather_than_silently_dropped() -> None:
    """The transcript line is the whole guarantee: a gap where a specialist
    should be reads to the model as agreement."""
    h = asyncio.run(
        ask_team(
            TEAM,
            answering({"policy-checker": 0.0, "fraud-checker": 5.0, "history-checker": 5.0}),
            Teamwork(waits_for=Waits.FIRST_GOOD),
        )
    )
    assert h.unfinished == ("fraud-checker", "history-checker")
    said = h.said("fraud-checker")
    assert "fraud-checker" in said and "no answer" in said


def test_a_quorum_the_batch_cannot_reach_is_reported_not_waited_on() -> None:
    """The model asked one specialist under a two-of-three rule. Hanging until
    a timeout would blame the clock for a decision that was already impossible."""
    h = asyncio.run(
        ask_team(["policy-checker"], answering(),
                 Teamwork(waits_for=Waits.ENOUGH, enough_is=2))
    )
    assert not h.satisfied
    assert "only 1 of the team was asked" in h.why
    assert state_of(h, "policy-checker") == NOT_ASKED


# ────────────────────────────────────────────────────────────── when they start


def test_the_team_works_at_the_same_time_rather_than_one_after_another() -> None:
    """Eve's only behaviour is the serial one. Here it is a choice, and the
    default is the one that does not multiply the customer's wait."""
    live, most = 0, 0

    async def ask(grant: Grant) -> str:
        nonlocal live, most
        live += 1
        most = max(most, live)
        await asyncio.sleep(0.02)
        live -= 1
        return "done"

    asyncio.run(ask_team(TEAM, ask, Teamwork()))
    assert most == 3, f"only {most} member(s) were ever working at once"


def test_taking_turns_never_has_two_members_working_at_once() -> None:
    live, most = 0, 0

    async def ask(grant: Grant) -> str:
        nonlocal live, most
        live += 1
        most = max(most, live)
        await asyncio.sleep(0.01)
        live -= 1
        return "done"

    asyncio.run(ask_team(TEAM, ask, Teamwork(starts=Starts.ONE_AFTER_ANOTHER)))
    assert most == 1


def test_taking_turns_lets_a_later_member_read_what_an_earlier_one_said() -> None:
    """The only thing turns buy. Eve pays the latency and hands over nothing,
    so its serial start is a cost with no matching benefit."""
    seen: dict[str, tuple[str, ...]] = {}

    async def ask(grant: Grant) -> str:
        seen[grant.member] = tuple(a.member for a in grant.so_far)
        return f"{grant.member} says yes"

    asyncio.run(ask_team(TEAM, ask, Teamwork(starts=Starts.ONE_AFTER_ANOTHER)))
    assert seen["policy-checker"] == ()
    assert seen["fraud-checker"] == ("policy-checker",)
    assert seen["history-checker"] == ("policy-checker", "fraud-checker")


def test_working_at_the_same_time_shows_nobody_an_unfinished_answer() -> None:
    seen: dict[str, tuple[str, ...]] = {}

    async def ask(grant: Grant) -> str:
        seen[grant.member] = tuple(a.member for a in grant.so_far)
        return "done"

    asyncio.run(ask_team(TEAM, ask, Teamwork()))
    assert all(v == () for v in seen.values())


# ──────────────────────────────────────────────────────── when one of them fails


def test_carrying_on_after_a_failure_keeps_the_answers_that_did_arrive() -> None:
    """Eve's barrier is all-or-nothing, so one child erroring discards two
    perfectly good sibling answers."""
    h = asyncio.run(
        ask_team(TEAM, answering(failing={"history-checker"}), Teamwork())
    )
    assert h.satisfied
    assert len(h.good) == 2
    assert "the ticket system is down" in h.said("history-checker")


def test_stopping_the_others_gives_up_on_the_first_failure() -> None:
    h = asyncio.run(
        ask_team(
            TEAM,
            answering({"policy-checker": 0.0, "fraud-checker": 5.0, "history-checker": 5.0},
                      failing={"policy-checker"}),
            Teamwork(if_someone_fails=OnFailure.STOP_THE_OTHERS),
        )
    )
    assert not h.satisfied
    assert "stop-the-others" in h.why
    assert state_of(h, "fraud-checker") == CANCELLED


def test_a_failure_can_ask_a_person_instead_of_choosing_for_them() -> None:
    h = asyncio.run(
        ask_team(TEAM, answering(failing={"policy-checker"}),
                 Teamwork(if_someone_fails=OnFailure.ASK_A_PERSON))
    )
    assert h.needs_a_person == "policy-checker"
    assert not h.satisfied


def test_asking_a_person_does_not_cut_the_other_members_short() -> None:
    """`stop-the-others` throws the siblings away; `ask-a-person` keeps them.
    The person is about to be asked whether to carry on without one member, and
    that is a better question with the other answers already in hand."""
    h = asyncio.run(
        ask_team(
            TEAM,
            answering({"policy-checker": 0.0, "fraud-checker": 0.02,
                       "history-checker": 0.02}, failing={"policy-checker"}),
            Teamwork(if_someone_fails=OnFailure.ASK_A_PERSON),
        )
    )
    assert h.needs_a_person == "policy-checker"
    assert {a.member for a in h.good} == {"fraud-checker", "history-checker"}


# ───────────────────────────────────────────────────────────────── the budget


async def spending(amount: float, grant: Grant) -> str:
    grant.spend(amount)
    return f"{grant.member} spent {amount}"


def test_an_even_split_is_the_default_which_is_what_eve_hardcodes() -> None:
    seen: dict[str, float] = {}

    async def ask(grant: Grant) -> str:
        seen[grant.member] = grant.allowance
        return "done"

    asyncio.run(ask_team(TEAM, ask, Teamwork(), budget=0.30))
    assert seen == {m: pytest.approx(0.10) for m in TEAM}


def test_declared_shares_give_one_member_more_than_an_even_split() -> None:
    seen: dict[str, float] = {}

    async def ask(grant: Grant) -> str:
        seen[grant.member] = grant.allowance
        return "done"

    two = ("policy-checker", "fraud-checker")
    asyncio.run(
        ask_team(
            two, ask,
            Teamwork(divides_the_budget=Divides.BY_SHARE,
                     shares={"policy-checker": 0.6, "fraud-checker": 0.4}),
            budget=0.10,
        )
    )
    assert seen["policy-checker"] == pytest.approx(0.06)
    assert seen["fraud-checker"] == pytest.approx(0.04)


def test_a_fixed_share_stops_a_member_spending_past_it() -> None:
    h = asyncio.run(ask_team(TEAM, lambda g: spending(0.20, g), Teamwork(), budget=0.30))
    assert all(a.state == FAILED for a in h.answers)
    assert "only 0.1 is left" in h.answers[0].error


def test_the_refusal_to_overspend_names_a_line_to_type() -> None:
    """A budget message a support lead cannot act on is a budget message that
    gets ignored."""
    h = asyncio.run(ask_team(TEAM, lambda g: spending(0.20, g), Teamwork(), budget=0.30))
    error = h.answers[0].error
    assert "fix:" in error
    assert "`cost-per-request-under`" in error
    assert "`divides-the-budget: as-needed`" in error


def test_a_shared_pot_lets_one_member_use_what_the_others_did_not() -> None:
    """The reason `as-needed` exists. Under an even split this same member is
    refused at a third of the budget, even though nothing else spent a penny."""
    async def ask(grant: Grant) -> str:
        grant.spend(0.25)
        return "done"

    shared = asyncio.run(
        ask_team(["policy-checker"], ask,
                 Teamwork(divides_the_budget=Divides.AS_NEEDED), budget=0.30)
    )
    assert shared.answers[0].state == ANSWERED

    split = asyncio.run(ask_team(TEAM, ask, Teamwork(), budget=0.30))
    assert split.answers[0].state == FAILED


def test_a_shared_pot_still_refuses_once_the_whole_thing_is_gone() -> None:
    """`as-needed` removes the reservation, not the limit."""
    async def ask(grant: Grant) -> str:
        grant.spend(0.20)
        return "done"

    h = asyncio.run(
        ask_team(TEAM, ask, Teamwork(divides_the_budget=Divides.AS_NEEDED,
                                     starts=Starts.ONE_AFTER_ANOTHER), budget=0.30)
    )
    assert [a.state for a in h.answers] == [ANSWERED, FAILED, FAILED]
    assert h.spent == pytest.approx(0.20)


def test_no_declared_budget_means_nothing_is_metered() -> None:
    """An unset limit must never become a limit of nothing — the same rule the
    SLO module keeps for an unset metric."""
    h = asyncio.run(ask_team(TEAM, lambda g: spending(1_000_000.0, g), Teamwork()))
    assert all(a.state == ANSWERED for a in h.answers)


def test_an_overspend_is_typed_so_a_caller_can_tell_it_from_a_model_error() -> None:
    from pact_adapters.delegation import Pool

    pool = Pool(0.10, Divides.EVENLY, ["a", "b"])
    with pytest.raises(OverBudget):
        pool.charge("a", 0.06)


# ─────────────────────────────────────────────── refusing a policy that cannot work


@pytest.mark.parametrize(
    "policy, expect",
    [
        (dict(waits_for=Waits.ENOUGH, enough_is=9), "`enough-is: 3` or fewer"),
        (dict(waits_for=Waits.ENOUGH), "add a line `enough-is: 2`"),
        (dict(waits_for=Waits.IN_TIME), "add a line `gives-up-after: 5s`"),
        (dict(divides_the_budget=Divides.BY_SHARE,
              shares={"policy-checker": 1.0}), "under `shares:`"),
        (dict(divides_the_budget=Divides.BY_SHARE,
              shares={m: 0.5 for m in TEAM}), "add up to 100% or less"),
    ],
)
def test_a_policy_that_can_never_work_is_refused_with_a_line_to_type(
    policy: dict, expect: str
) -> None:
    """Refused at load, not at 3am. Every message names the field, what is
    wrong, and something typeable."""
    with pytest.raises(BadTeamwork) as e:
        Teamwork(**policy).check(TEAM)
    assert expect in str(e.value), str(e.value)
    assert "fix:" in str(e.value)


def test_an_unknown_word_lists_the_ones_that_work() -> None:
    with pytest.raises(BadTeamwork) as e:
        Teamwork.from_document(
            {"agents": {"x": {"team": {"a": "helps"}, "teamwork": {"waits-for": "most"}}}}, "x"
        )
    assert "everyone" in str(e.value) and "fix:" in str(e.value)


def test_a_refused_policy_names_the_agent_it_came_from() -> None:
    """Which of nine agents is wrong is the first thing anyone needs, and it is
    also the folder to open."""
    with pytest.raises(BadTeamwork) as e:
        Teamwork.from_document(
            {"agents": {"refund-desk": {"team": {"a": "helps"},
                                        "teamwork": {"waits-for": "enough-of-them",
                                                     "enough-is": 3}}}},
            "refund-desk",
        )
    assert str(e.value).startswith("refund-desk: ")


def test_no_teamwork_block_is_a_default_rather_than_an_error() -> None:
    """A support lead with two helpers and no opinion must not need one."""
    tw = Teamwork.from_document({"agents": {"x": {"team": {"a": "helps", "b": "helps"}}}}, "x")
    assert tw.waits_for is Waits.EVERYONE
    assert tw.starts is Starts.ALL_AT_ONCE
    assert tw.divides_the_budget is Divides.EVENLY
    assert tw.if_someone_fails is OnFailure.CARRY_ON


# ─────────────────────────────────────────────────────── read from the folder


@pytest.fixture(scope="module")
def document() -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def test_the_join_policy_is_read_from_the_folder_not_written_in_code(document: dict) -> None:
    """D14: the whole mechanism has to be reachable from YAML alone."""
    tw = Teamwork.from_document(document, "refund-desk")
    assert tw.waits_for is Waits.EVERYONE
    assert tw.starts is Starts.ALL_AT_ONCE
    assert tw.divides_the_budget is Divides.BY_SHARE
    assert tw.shares == {"policy-checker": pytest.approx(0.6),
                         "fraud-checker": pytest.approx(0.4)}
    assert tw.if_someone_fails is OnFailure.ASK_A_PERSON


def test_the_authored_shares_are_what_each_member_actually_gets(document: dict) -> None:
    """Config that loads but does not reach the run is decoration."""
    tw = Teamwork.from_document(document, "refund-desk")
    seen: dict[str, float] = {}

    async def ask(grant: Grant) -> str:
        seen[grant.member] = grant.allowance
        return "done"

    asyncio.run(ask_team(["policy-checker", "fraud-checker"], ask, tw, budget=0.05))
    assert seen["policy-checker"] == pytest.approx(0.03)
    assert seen["fraud-checker"] == pytest.approx(0.02)


# ──────────────────────────────────────────────────────────── wired into the loop


SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Ask the team, then decide.",
    tools=(ToolSpec("zendesk", "read the ticket"),),
    team={"policy-checker": "Checks the written policy.",
          "fraud-checker": "Looks for signs it is not genuine."},
)
TOOLS = {"zendesk": lambda a: "lamp, broken"}


def asking_both() -> Script:
    return Script(
        [
            Turn("Consulting the team.",
                 (ToolCall("policy-checker", {"question": "is this covered?"}),
                  ToolCall("fraud-checker", {"question": "does this look real?"}))),
            Turn("Approved."),
        ]
    )


def test_the_harness_routes_team_calls_through_the_join_policy() -> None:
    result = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=answering(), teamwork=Teamwork())
    )
    assert result.halted == "final"
    assert len(result.handoffs) == 1
    assert result.handoffs[0].satisfied
    assert result.steps[0].tool_results == (
        "policy-checker says yes", "fraud-checker says yes"
    )


def test_a_member_that_was_not_waited_for_reaches_the_model_as_a_named_gap() -> None:
    """The join decides; the model is told. Both halves are needed — a race that
    quietly shortens the transcript changes the decision without saying so."""
    result = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=answering({"fraud-checker": 5.0}),
            teamwork=Teamwork(waits_for=Waits.FIRST_GOOD))
    )
    assert "no answer" in result.steps[0].tool_results[1]
    assert "fraud-checker" in result.steps[0].tool_results[1]


def test_the_model_is_offered_each_teammate_with_the_sentence_the_author_wrote() -> None:
    offered: list[dict] = []

    class Watching(ReferenceTransport):
        async def model_call(self, system, history, tools):
            offered.extend(tools)
            return await super().model_call(system, history, tools)

    asyncio.run(
        run(SPEC, Watching(asking_both()), "refund?", TOOLS,
            ask_member=answering(), teamwork=Teamwork())
    )
    names = {t["name"]: t["description"] for t in offered}
    assert "Checks the written policy." in names["policy-checker"]


def test_asking_the_same_teammate_twice_asks_it_twice() -> None:
    """A reply cached across steps would make a second opinion impossible, and
    would silently answer a different question with the first one's answer."""
    asked: list[str] = []

    async def ask(grant: Grant) -> str:
        asked.append(grant.member)
        return f"round {len(asked)}"

    twice = Script(
        [
            Turn("First pass.", (ToolCall("policy-checker", {"question": "a"}),)),
            Turn("Second pass.", (ToolCall("policy-checker", {"question": "b"}),)),
            Turn("Approved."),
        ]
    )
    result = asyncio.run(
        run(SPEC, ReferenceTransport(twice), "refund?", TOOLS, ask_member=ask)
    )
    assert asked == ["policy-checker", "policy-checker"]
    assert result.steps[0].tool_results != result.steps[1].tool_results


def test_the_run_emits_one_delegate_event_per_member_and_one_for_the_join() -> None:
    from pact_adapters.events import Bus

    bus = Bus()
    asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=answering(), teamwork=Teamwork(), bus=bus)
    )
    seen = [str(e.address) for e in bus.log]
    assert seen.count("step.delegate.started") == 2
    assert seen.count("step.delegate.completed") == 2
    assert "step.delegate.requested" in seen
    assert "turn.delegate.completed" in seen


def test_an_interceptor_can_stop_a_delegation_before_anyone_is_asked() -> None:
    """Observe-only hooks cannot do this, which is every hook Eve has."""
    asked: list[str] = []

    async def ask(grant: Grant) -> str:
        asked.append(grant.member)
        return "done"

    chain = Chain()
    chain.add(guard("no-outside-help", "step.delegate.before",
                    lambda p: "this desk decides on its own today"))
    result = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=ask, chain=chain)
    )
    assert result.halted == "stopped-by-rule"
    assert asked == [], "nobody may be asked after the rule stopped it"


def test_a_failing_member_under_ask_a_person_parks_and_keeps_the_good_answer() -> None:
    result = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=answering(failing={"fraud-checker"}),
            teamwork=Teamwork(if_someone_fails=OnFailure.ASK_A_PERSON))
    )
    assert result.halted == "suspended"
    assert result.suspension is not None
    assert result.suspension.completed["policy-checker"] == "policy-checker says yes"


def test_a_person_saying_carry_on_does_not_ask_the_good_member_again() -> None:
    """Exactly-once across a wait, for a teammate as much as for a tool."""
    asked: list[str] = []

    def counting(failing: set[str]):
        async def ask(grant: Grant) -> str:
            asked.append(grant.member)
            if grant.member in failing:
                raise RuntimeError("down")
            return f"{grant.member} says yes"

        return ask

    first = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=counting({"fraud-checker"}),
            teamwork=Teamwork(if_someone_fails=OnFailure.ASK_A_PERSON))
    )
    assert first.halted == "suspended"

    # The process dies here; only the written-down suspension survives.
    from pact_adapters.suspension import Suspension

    parked = Suspension.from_json(first.suspension.to_json())
    resumed = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=counting(set()),
            teamwork=Teamwork(if_someone_fails=OnFailure.ASK_A_PERSON),
            resume=parked, answer=parked.answer(**{"fraud-checker": "approve"}))
    )
    assert resumed.halted == "final"
    assert asked.count("policy-checker") == 1, f"asked twice: {asked}"
    assert "carry on without fraud-checker" in resumed.steps[0].tool_results[1]


def test_a_person_declining_ends_the_run_without_the_member_they_refused() -> None:
    """"Do not carry on without the fraud check" is an ANSWER, not a silence.

    It asserted `suspended` for as long as the loop read one bool for "may this
    go past?" — so a person who said no and a person who had said nothing were
    the same value, and the run asked them again. What a no means here is that
    `fraud-checker`'s slot is filled with a refusal rather than with a reply, so
    the model reads why the check is missing and can say something about it
    instead of the run stopping with nothing to show.
    """
    first = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=answering(failing={"fraud-checker"}),
            teamwork=Teamwork(if_someone_fails=OnFailure.ASK_A_PERSON))
    )
    parked = first.suspension
    again = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=answering(),
            teamwork=Teamwork(if_someone_fails=OnFailure.ASK_A_PERSON),
            resume=parked, answer=parked.answer(**{"fraud-checker": "decline"}))
    )
    assert again.halted != "suspended", "a no is an answer, not another wait"
    said = [r for step in again.steps for r in step.tool_results]
    assert any("refused:" in r and "said no" in r for r in said), said


def test_the_question_named_under_teamwork_attaches_to_every_member(document: dict) -> None:
    """`teamwork.asks` names a written question, and that question is what is
    put about each teammate. A field that loads and is then ignored is
    decoration — and "carry on without the fraud check?" is a different decision
    per specialist, so it attaches per member rather than once per run."""
    from pact_adapters.questions import questions_for

    asking = questions_for(document, "refund-desk")
    for member in ("policy-checker", "fraud-checker"):
        assert member in asking, f"no question attached to {member}"
        # The teamwork park has its OWN question now. It used to share
        # `is-this-ok` with the approvals policy, and `is-this-ok` shows the
        # amount and order number of the CALL being approved — which a teammate
        # who could not answer is not, so both lines were dropped in silence and
        # the person was asked to decide with the wording and nothing else.
        assert asking[member].asks.startswith("One of the checks could not be completed")
        assert set(asking[member].shows) == {
            "who-could-not-answer",
            "why-they-could-not",
            "who-did-answer",
        }, "a teammate park has to show what THIS park really has"


def test_a_failing_teammate_parks_on_a_wait_that_names_that_teammate(document: dict) -> None:
    """Which specialist could not answer is the whole content of the question,
    so it is what the wait is keyed on — two members failing in one step must
    not be answerable by one reply."""
    from pact_adapters.questions import questions_for

    desk = AgentSpec.from_document(document, "refund-desk")
    result = asyncio.run(
        run(desk, ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=answering(failing={"fraud-checker"}),
            teamwork=Teamwork.from_document(document, "refund-desk"),
            asking=questions_for(document, "refund-desk"))
    )
    assert result.halted == "suspended"
    assert result.suspension.reason == "needs-approval"
    assert result.suspension.completed["policy-checker"] == "policy-checker says yes"
    from pact_adapters.suspension import correlation_key

    assert result.suspension.correlation_key == correlation_key(
        "needs-approval", 0, ["fraud-checker"]
    )


def test_without_a_way_to_run_the_team_the_run_still_waits_for_it() -> None:
    """The join policy is an addition, not a replacement: a teammate that lives
    in another process is still a suspension, exactly as before."""
    result = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS)
    )
    assert result.halted == "suspended"
    assert result.suspension.reason == "waiting-for-another-agent"


def test_every_transport_reaches_the_same_place_when_the_team_is_asked() -> None:
    """The join belongs to the harness, not to a framework. Seven transports
    asking the same team under the same policy must produce the same transcript,
    or delegation is the place where portability quietly stops — and delegation
    is exactly where the frameworks' own abstractions differ most."""
    traces = {}
    for name, cls in TRANSPORTS.items():
        r = asyncio.run(
            run(SPEC, cls(asking_both()), "refund?", TOOLS,
                ask_member=answering(), teamwork=Teamwork())
        )
        traces[name] = {"trace": r.trace(), "output": r.output, "halted": r.halted}
    reference = traces["reference"]
    for name, got in traces.items():
        assert got == reference, (
            f"{name} diverged from the reference transport on a delegating run.\n"
            f"  reference: {json.dumps(reference, indent=2)}\n"
            f"  {name}: {json.dumps(got, indent=2)}"
        )


def test_a_run_that_never_asks_the_team_is_unchanged_by_the_mechanism() -> None:
    """It must cost nothing when unused — the same bar the interceptor chain is
    held to."""
    plain = Script([Turn("checking", (ToolCall("zendesk", {}),)), Turn("Approved.")])
    without = asyncio.run(run(SPEC, ReferenceTransport(plain), "refund?", TOOLS))
    with_team = asyncio.run(
        run(SPEC, ReferenceTransport(
            Script([Turn("checking", (ToolCall("zendesk", {}),)), Turn("Approved.")])),
            "refund?", TOOLS, ask_member=answering(), teamwork=Teamwork())
    )
    assert without.trace() == with_team.trace()
    assert without.halted == with_team.halted == "final"


# ────────────────────────────────────────────── the team is run by the same loop


def test_a_teammate_is_run_by_this_same_harness_one_level_down(document: dict) -> None:
    """Delegation is not a second execution model, so it does not get a second
    loop. The child is an agent in the same folder, run by the same `run`."""
    child_scripts = {
        "policy-checker": Script([Turn("Allowed under clause 3.")]),
        "fraud-checker": Script([Turn("Nothing suspicious.")]),
    }

    def transport_for(member_spec: AgentSpec):
        key = {"Policy Checker": "policy-checker", "Fraud Checker": "fraud-checker"}
        return ReferenceTransport(child_scripts[key[member_spec.name]])

    desk = AgentSpec.from_document(document, "refund-desk")
    result = asyncio.run(
        run(desk, ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=delegate_by_running(document, transport_for),
            teamwork=Teamwork())
    )
    assert result.halted == "final"
    assert result.steps[0].tool_results == ("Allowed under clause 3.", "Nothing suspicious.")


def test_the_parents_question_reaches_the_teammate_it_was_meant_for(document: dict) -> None:
    heard: dict[str, str] = {}

    class Listening(ReferenceTransport):
        def __init__(self, script, who):
            super().__init__(script)
            self.who = who

        async def model_call(self, system, history, tools):
            heard[self.who] = history[0]["content"]
            return await super().model_call(system, history, tools)

    def transport_for(member_spec: AgentSpec):
        key = {"Policy Checker": "policy-checker", "Fraud Checker": "fraud-checker"}[
            member_spec.name
        ]
        return Listening(Script([Turn("ok")]), key)

    desk = AgentSpec.from_document(document, "refund-desk")
    asyncio.run(
        run(desk, ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=delegate_by_running(document, transport_for), teamwork=Teamwork())
    )
    assert heard["policy-checker"] == "is this covered?"
    assert heard["fraud-checker"] == "does this look real?"


# ──────────────────────── the ceiling the author wrote is the pot they divide
#
# Everything above proves the SPLIT. These four prove the POT — that the number
# being split is `cost-per-request-under` out of the author's own `limits.yaml`
# and not a figure a host had to know to pass in.
#
# `test_the_authored_shares_are_what_each_member_actually_gets` above hands
# `ask_team` the 0.05 itself, and that is exactly the move that hid this for
# five rounds: it proves `Pool` divides correctly and says nothing about whether
# the author's line ever reaches `Pool`. It did not. `run(..., team_budget=…)`
# was the only source of that number, no caller anywhere supplied it, so the
# most carefully argued line in the worked example — "the money follows the work
# rather than the headcount" — was applied to an empty pot and every
# `step.delegate.started` carried `allowance: inf`.


def test_the_spend_ceiling_the_author_wrote_is_the_pot_the_team_divides(
    document: dict,
) -> None:
    """`cost-per-request-under: 0.05 USD` and 60/40 shares are one sentence
    between them, and it is spoken with nothing passed in.

    NOTHING is handed to `run` here but the asker, and for a round that was not
    true of this test either: it passed `teamwork=Teamwork.from_document(...)`
    while its own docstring said otherwise, which is exactly how the other half
    of the sentence stayed broken for a round after this half was fixed. The pot
    reached `Pool`; the policy that divides it did not, so the author's 60/40
    came out as an even 0.025/0.025. D14 rules out "a host writes code for that"
    for every capability in the core, so the two lines the author typed — one in
    `limits.yaml`, one in `teamwork.yaml` — meet each other on their own.

    Eve has no spend cap of any kind, which is why it can only ever split
    *tokens*, and why its split is even: there is no authored money for shares
    to be shares OF.
    """
    desk = AgentSpec.from_document(document, "refund-desk")
    granted: dict[str, float] = {}
    pot: dict[str, float] = {}

    async def ask(grant: Grant) -> str:
        granted[grant.member] = grant.allowance
        pot[grant.member] = grant.pool.total
        return f"{grant.member} says yes"

    result = asyncio.run(
        run(desk, ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=ask)
    )

    assert result.halted == "final"
    assert pot == {"policy-checker": pytest.approx(0.05),
                   "fraud-checker": pytest.approx(0.05)}, (
        "the pot is not the `cost-per-request-under: 0.05 USD` the author wrote"
    )
    assert granted["policy-checker"] == pytest.approx(0.03), "60% of 0.05 USD"
    assert granted["fraud-checker"] == pytest.approx(0.02), "40% of 0.05 USD"


def test_the_delegate_event_says_what_a_member_may_spend_rather_than_infinity(
    document: dict,
) -> None:
    """The observable that made the gap invisible has to state the ceiling too.

    `step.delegate.started` reported `allowance: inf` on a run whose author had
    written a spend cap, truthfully, and nothing anywhere contradicted it — so
    the one place a reader could have caught this agreed with the defect. An
    infinite allowance under a written ceiling is now the thing this fails on.
    """
    from pact_adapters.events import Bus

    bus = Bus()
    desk = AgentSpec.from_document(document, "refund-desk")
    result = asyncio.run(
        run(desk, ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=answering(),
            teamwork=Teamwork.from_document(document, "refund-desk"), bus=bus)
    )

    assert result.halted == "final"
    started = {
        e.payload["member"]: e.payload["allowance"]
        for e in bus.seen("step.delegate.started")
    }
    assert set(started) == {"policy-checker", "fraud-checker"}
    assert all(math.isfinite(a) for a in started.values()), (
        f"a spend cap was written and the team was told it had none: {started}"
    )
    assert started["policy-checker"] == pytest.approx(0.03)
    assert started["fraud-checker"] == pytest.approx(0.02)


def test_an_agent_that_wrote_no_ceiling_still_leaves_the_team_unmetered() -> None:
    """A limit nobody wrote must never become a limit of nothing.

    `Pool`'s docstring says this and `Slo` keeps the same rule for an unset
    metric, and the wiring is exactly where it could be lost: an unset
    `cost-per-request-under` arriving as a pot of zero would refuse the first
    penny of every team that never asked to be metered. `SPEC` here has no
    `limits:` at all, and spending a million is the proof that nothing is
    counting rather than that the count is generous.
    """
    seen: dict[str, float] = {}
    metered: dict[str, bool] = {}

    async def ask(grant: Grant) -> str:
        seen[grant.member] = grant.allowance
        metered[grant.member] = grant.pool.metered
        grant.spend(1_000_000.0)
        return f"{grant.member} says yes"

    result = asyncio.run(
        run(SPEC, ReferenceTransport(asking_both()), "refund?", TOOLS,
            ask_member=ask, teamwork=Teamwork())
    )

    assert result.halted == "final"
    assert metered == {"policy-checker": False, "fraud-checker": False}
    assert seen == {"policy-checker": math.inf, "fraud-checker": math.inf}


def test_a_host_may_still_override_the_ceiling_the_author_wrote(
    document: dict,
) -> None:
    """The same shape `summarise=`, `tidy=`, `chain=` and `loop=` already have:
    the author's line executes with nothing passed in, and a host that has a
    reason may still pass its own. Resolving the author's ceiling must not turn
    into ignoring the caller — that is how an override quietly stops working."""
    desk = AgentSpec.from_document(document, "refund-desk")
    granted: dict[str, float] = {}

    async def ask(grant: Grant) -> str:
        granted[grant.member] = grant.allowance
        return f"{grant.member} says yes"

    asyncio.run(
        run(desk, ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=ask, teamwork=Teamwork.from_document(document, "refund-desk"),
            team_budget=0.10)
    )

    assert granted["policy-checker"] == pytest.approx(0.06), "60% of the host's 0.10"
    assert granted["fraud-checker"] == pytest.approx(0.04), "40% of the host's 0.10"


# ───────────────────────────── the policy that divides the pot, with nothing passed
#
# The four above prove the POT reaches `Pool`. These prove the POLICY does — the
# `shares:`, the `if-someone-fails:` and the charging — because for a round it
# did not, and the gap was invisible for exactly the reason the pot's was: every
# test that exercised the authored shares handed `teamwork=Teamwork.from_document(…)`
# in by hand, including the one whose own docstring said nothing was passed.


def test_the_shares_the_author_wrote_are_what_the_team_gets_with_nothing_passed(
    document: dict,
) -> None:
    """`shares: 60/40` and `cost-per-request-under: 0.05 USD` meet each other.

    Nothing is handed to `run` but the asker. `run()` read `teamwork or
    Teamwork()` for a round and `Teamwork.from_document` had no caller in `src/`
    at all, so the two lines the author typed came out as an even 0.025/0.025 —
    a split nobody wrote, enforced, on a run whose file says otherwise.
    """
    desk = AgentSpec.from_document(document, "refund-desk")
    granted: dict[str, float] = {}

    async def ask(grant: Grant) -> str:
        granted[grant.member] = grant.allowance
        return f"{grant.member} says yes"

    result = asyncio.run(
        run(desk, ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=ask)
    )

    assert result.halted == "final"
    assert granted["policy-checker"] == pytest.approx(0.03), "60% of 0.05 USD"
    assert granted["fraud-checker"] == pytest.approx(0.02), "40% of 0.05 USD"


def test_a_failing_fraud_checker_asks_a_person_rather_than_approving_the_refund(
    document: dict,
) -> None:
    """`if-someone-fails: ask-a-person`, with nothing handed in.

    The comment above that line in `teamwork.yaml` says what is at stake:
    "Approving a refund without the fraud check is exactly the mistake that
    costs money, so nobody carries on without one." With the policy defaulting
    away to `carry-on`, the same run returned `final` and `Approved.` — the
    refund granted, no fraud check, nothing anywhere saying so.
    """
    desk = AgentSpec.from_document(document, "refund-desk")

    async def ask(grant: Grant) -> str:
        if grant.member == "fraud-checker":
            raise RuntimeError("the ticket system is down")
        return "covered by the policy"

    result = asyncio.run(
        run(desk, ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=ask)
    )

    assert result.halted == "suspended", result.output
    assert result.output != "Approved."
    assert result.suspension is not None
    assert "fraud-checker" in result.handoffs[0].needs_a_person


def test_a_teammate_that_overspends_its_share_is_refused_rather_than_billed(
    document: dict,
) -> None:
    """The allowance has to be charged by the asker PACT actually ships.

    `delegate_by_running` is the only in-repo way to run a teammate, and for a
    round it ran the child and returned its text without touching the grant —
    so `Pool.charge` and `OverBudget` were unreachable on any real run, and a
    member with no `limits:` of its own (which both of these are) spent without
    bound while the parent's pool read `spent 0.0`.
    """

    class Costly(ReferenceTransport):
        """A child whose one model call costs a whole dollar."""

        def usage(self) -> tuple[int, float]:
            return (100, 1.00)

    result = asyncio.run(
        run(AgentSpec.from_document(document, "refund-desk"),
            ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=delegate_by_running(
                document, lambda member: Costly(Script([Turn("checked")]))))
    )

    handoff = result.handoffs[0]
    assert [a.state for a in handoff.answers] == [FAILED, FAILED]
    said = " ".join(a.error for a in handoff.answers)
    assert "tried to spend 1" in said, said
    assert "cost-per-request-under" in said, "the refusal must name the line to raise"
    assert "divides-the-budget: as-needed" in said, "and the other line that fixes it"
    # And the author's own failure rule decides what happens next, rather than
    # the refusal taking the parent down.
    assert result.halted == "suspended"


def test_what_the_team_spent_counts_against_the_ceiling_the_author_wrote(
    document: dict,
) -> None:
    """One pot for the request, not one per delegating step.

    `Pool` was built inside `ask_team`, which is called from inside the step
    loop, so a script that asked the team twice was granted the author's whole
    ceiling twice: measured, 0.10 USD spent under a written 0.05 USD cap with
    nothing refused. `cost-per-request-under` is help-texted as "the most one
    request may cost", and a fresh pot per step is not a reading of that.
    """
    desk = AgentSpec.from_document(document, "refund-desk")
    twice = Script([
        Turn("asking", (ToolCall("policy-checker", {"message": "a"}),)),
        Turn("asking again", (ToolCall("policy-checker", {"message": "b"}),)),
        Turn("Approved."),
    ])
    seen: list[float] = []

    async def ask(grant: Grant) -> str:
        seen.append(grant.allowance)
        grant.spend(0.02)
        return "ok"

    result = asyncio.run(
        run(desk, ReferenceTransport(twice), "Can I get a refund?", TOOLS, ask_member=ask)
    )

    assert seen[0] == pytest.approx(0.03), "60% of 0.05 USD"
    assert seen[1] == pytest.approx(0.01), (
        f"the second step was granted a fresh pot: {seen}"
    )
    assert result.spent == pytest.approx(0.02), (
        "what the team spent has to reach the parent's own meter, or one written "
        "ceiling is one ceiling per level"
    )


def test_a_member_runs_under_the_share_it_was_granted_and_never_a_larger_one(
    document: dict,
) -> None:
    """The grant is the child's own ceiling, not a number the parent remembers.

    `policy-checker/agent.yaml` has no `limits:` at all, so before this the
    child resolved its cost ceiling from its own (empty) file and ran unmetered
    under a parent that had written one — which is one of the few things Eve
    does do.
    """
    ceilings: dict[str, float | None] = {}

    class Watching(ReferenceTransport):
        pass

    def transport_for(member: AgentSpec) -> ReferenceTransport:
        ceilings[member.name] = member.limits.cost_per_request_under
        return Watching(Script([Turn("checked")]))

    asyncio.run(
        run(AgentSpec.from_document(document, "refund-desk"),
            ReferenceTransport(asking_both()), "Can I get a refund?", TOOLS,
            ask_member=delegate_by_running(document, transport_for))
    )

    assert ceilings["Policy Checker"] == pytest.approx(0.03)
    assert ceilings["Fraud Checker"] == pytest.approx(0.02)
