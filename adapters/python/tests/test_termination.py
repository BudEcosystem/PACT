"""The termination algebra (G2): every way a run is allowed to end.

Eve has none of this. It has no step limit, no turn limit, no wall-clock limit
and no spend cap anywhere; `stopWhen: isStepCount(1)` is the only stop condition
in the package, and the only bound on a run is a token budget on the session. A
confused agent there loops until it has spent 40M tokens, and stopping that way
is reported the same as answering.

Each test below names one guarantee. Together they are the claim: every ceiling
is enforced, each does what the author's own file says, and none of them can be
mistaken for finishing.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.context_policy import CHARS_PER_TOKEN  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.limits import Action, Limits, Meter  # noqa: E402
from pact_adapters.resolve import default_model, window_of  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import OUT_OF_BUDGET, Suspension  # noqa: E402
from pact_adapters.transports.anthropic_transport import AnthropicTransport  # noqa: E402
from pact_adapters.transports.autogen_transport import AutoGenTransport  # noqa: E402
from pact_adapters.transports.langchain_transport import LangChainTransport  # noqa: E402
from pact_adapters.transports.langgraph_transport import LangGraphTransport  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.openai_agents_transport import OpenAIAgentsTransport  # noqa: E402
from pact_adapters.transports.pydantic_ai_transport import PydanticAITransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

TRANSPORTS = {
    "reference": ReferenceTransport,
    "pydantic-ai": PydanticAITransport,
    "langgraph": LangGraphTransport,
    "langchain": LangChainTransport,
    "autogen": AutoGenTransport,
    "openai-agents": OpenAIAgentsTransport,
    "anthropic": AnthropicTransport,
}

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund")),
)
TOOLS = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}


def never_finishes() -> Script:
    """A model that keeps calling a tool and never answers — the shape a limit
    exists for, and the one Eve cannot bound at all."""
    return Script([Turn("still working", (ToolCall("zendesk", {}),))])


class Ticking:
    """A clock the test drives, so a wall-clock ceiling can be proven in
    microseconds instead of being asserted about and never exercised."""

    def __init__(self, step: float = 1.0) -> None:
        self.at, self.step = 0.0, step

    def __call__(self) -> float:
        self.at += self.step
        return self.at


class Costing(ReferenceTransport):
    """A transport that reports what a call cost. Optional on purpose: a scripted
    model has no price and no tokeniser, and the harness says so rather than
    inventing a number."""

    name = "costing"

    def __init__(self, script: Script, tokens: int = 100, money: float = 0.02) -> None:
        super().__init__(script)
        self._tokens, self._money = tokens, money

    def usage(self) -> tuple[int, float]:
        return self._tokens, self._money


class Cornered(ReferenceTransport):
    """Calls a tool while it has one, and answers when it has none.

    This is what withholding tools actually does to a model, and it is what makes
    `answer-with-what-it-has` a real behaviour rather than a relabelled stop.
    """

    name = "cornered"

    async def model_call(self, system, history, tools):
        if not tools:
            return "Best I can say from the ticket: the lamp arrived broken.", []
        return "still working", [ToolCall("zendesk", {})]


def with_limits(**kwargs) -> AgentSpec:
    return replace(SPEC, limits=Limits(**kwargs))


# ─────────────────────────────────────────────────────────── the ceilings exist


def test_a_step_ceiling_stops_a_model_that_would_otherwise_never_stop() -> None:
    spec = replace(SPEC, max_steps=4, limits=Limits(when_it_runs_out=Action.STOP))
    r = asyncio.run(run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS))
    assert r.halted == "step-limit"
    assert len(r.steps) == 4
    assert r.stopped_by is not None and r.stopped_by.ceiling.field == "steps-at-most"


def test_a_wall_clock_ceiling_stops_a_run_that_is_still_making_progress() -> None:
    """Steps and money can both be well inside budget while the caller waits.
    Eve has no wall-clock bound of any kind, so nothing there ever stops for
    time alone."""
    spec = with_limits(wall_clock_s=3.0)
    r = asyncio.run(
        run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS, clock=Ticking())
    )
    assert r.halted == "time-limit"
    assert r.stopped_by is not None and r.stopped_by.ceiling.field == "runs-for-at-most"
    assert len(r.steps) < SPEC.max_steps, "it stopped for time, not for steps"


def test_a_tool_call_ceiling_stops_before_the_call_that_would_exceed_it() -> None:
    """One step can ask for several tools at once, so a ceiling checked after
    each batch is not a ceiling. The 3rd call must never run."""
    ran: list[str] = []
    spec = with_limits(tool_calls_at_most=2)
    script = Script(
        [Turn("working", (ToolCall("zendesk", {}), ToolCall("payments", {}), ToolCall("zendesk", {})))]
    )
    r = asyncio.run(
        run(spec, ReferenceTransport(script), "hello",
            {"zendesk": lambda a: ran.append("zendesk") or "ok",
             "payments": lambda a: ran.append("payments") or "ok"})
    )
    assert r.halted == "tool-call-limit"
    assert len(ran) == 2, f"the ceiling was 2 and {len(ran)} calls ran: {ran}"


def test_a_spend_ceiling_stops_the_run_while_the_money_is_still_unspent() -> None:
    spec = with_limits(cost_per_request_under=0.05)
    r = asyncio.run(run(spec, Costing(never_finishes(), money=0.02), "hello", TOOLS))
    assert r.halted == "cost-limit"
    assert r.stopped_by is not None
    assert r.stopped_by.at <= 0.06, "it stopped at the ceiling, not long past it"


def test_a_token_ceiling_bounds_a_run_that_no_price_list_can_bound() -> None:
    """A model on your own machine costs nothing per word, so a money cap cannot
    hold it. Tokens are the ceiling that still bites air-gapped (D17) — and they
    are the one bound Eve does have, so this is parity, not a gap."""
    spec = with_limits(tokens_at_most=250)
    r = asyncio.run(run(spec, Costing(never_finishes(), tokens=100), "hello", TOOLS))
    assert r.halted == "token-limit"
    assert r.stopped_by is not None and r.stopped_by.at == 300


def test_a_run_with_no_ceilings_declared_behaves_exactly_as_before() -> None:
    """The algebra must cost nothing when unused."""
    plain = asyncio.run(
        run(SPEC, ReferenceTransport(Script([Turn("checking", (ToolCall("zendesk", {}),)),
                                             Turn("Approved.")])), "refund?", TOOLS)
    )
    assert plain.halted == "final"
    assert plain.output == "Approved."
    assert plain.stopped_by is None


# ─────────────────────────────────────────────────── the action is the author's


def test_stop_and_say_so_names_the_setting_the_author_typed() -> None:
    """A message saying only that a limit was exceeded leaves the reader nowhere
    to go. It has to name the line in their file and both numbers (D13)."""
    spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=Action.STOP))
    r = asyncio.run(run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS))
    assert "steps-at-most" in r.output
    assert "2 of 2 steps" in r.output
    assert "Stopped before finishing" in r.output


def test_answer_with_what_it_has_produces_an_answer_and_still_reports_the_ceiling() -> None:
    """The whole reason this action is safe to offer. Eve's equivalent — running
    out of session tokens — ends the session and reads like any other ending."""
    spec = replace(SPEC, max_steps=3, limits=Limits(when_it_runs_out=Action.ANSWER))
    r = asyncio.run(run(spec, Cornered(never_finishes()), "hello", TOOLS))
    assert "lamp arrived broken" in r.output, "it really answered"
    assert r.halted == "step-limit", "and it is not reported as having finished"
    assert r.stopped_by is not None
    assert r.stopped_by.action is Action.ANSWER


def test_ask_a_person_parks_the_run_the_same_way_every_other_wait_does() -> None:
    """Running out of budget is not a new kind of park. Eve keys a session-limit
    continuation by session, separately from its four other park kinds, and
    reuses its approve/deny widget for a question that is really 'keep going?'."""
    spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=Action.ASK))
    r = asyncio.run(run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS))
    assert r.halted == "suspended"
    assert r.suspension is not None and r.suspension.reason == OUT_OF_BUDGET
    assert r.stopped_by is not None and r.stopped_by.action is Action.ASK


def test_the_declared_action_decides_what_happens_and_nothing_else_does() -> None:
    """Same agent, same model, same trace — three endings, chosen by one line of
    YAML. Stopping silently, asking, and answering anyway are three different
    governance decisions, so none of them can be the harness's to make."""
    endings = {}
    for act in (Action.STOP, Action.ASK, Action.ANSWER):
        spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=act))
        r = asyncio.run(run(spec, Cornered(never_finishes()), "hello", TOOLS))
        endings[act] = r.halted
    assert endings[Action.STOP] == "step-limit"
    assert endings[Action.ASK] == "suspended"
    assert endings[Action.ANSWER] == "step-limit"
    assert len(set(endings.values())) >= 2


# ───────────────────────────────────────────────── running out is not finishing


def test_a_run_that_finished_and_a_run_that_ran_out_are_never_reported_alike() -> None:
    finished = asyncio.run(
        run(SPEC, ReferenceTransport(Script([Turn("Approved.")])), "refund?", TOOLS)
    )
    ran_out = asyncio.run(
        run(replace(SPEC, max_steps=2), ReferenceTransport(never_finishes()), "refund?", TOOLS)
    )
    assert finished.halted == "final" and finished.stopped_by is None
    assert ran_out.halted != "final" and ran_out.stopped_by is not None


def test_two_ceilings_reached_together_report_the_same_one_every_time() -> None:
    """An explanation that changes between identical runs is one nobody can act
    on, so the ceilings are checked in a fixed order rather than a dict's."""
    spec = with_limits(tool_calls_at_most=1, tokens_at_most=1, cost_per_request_under=0.001)
    named = {
        asyncio.run(
            run(spec, Costing(never_finishes()), "hello", TOOLS)
        ).stopped_by.ceiling.field
        for _ in range(5)
    }
    assert len(named) == 1, f"the same trace named different ceilings: {named}"


def test_a_ceiling_the_transport_cannot_measure_is_reported_not_silently_ignored() -> None:
    """T7. An author who wrote a spend cap, got no enforcement, and was told
    nothing has been told something untrue — which is worse than having no cap."""
    spec = with_limits(cost_per_request_under=0.05, tokens_at_most=100)
    r = asyncio.run(run(spec, ReferenceTransport(Script([Turn("done")])), "hello", TOOLS))
    assert set(r.unmetered) == {"cost-per-request-under", "tokens-at-most"}

    metered = asyncio.run(run(spec, Costing(Script([Turn("done")])), "hello", TOOLS))
    assert metered.unmetered == (), "a transport that can measure is not warned about"


def test_the_clock_and_the_step_counter_are_not_the_same_ceiling() -> None:
    """Both are 'how long', and a system with only one of them cannot tell a
    fast loop from a slow single call."""
    fast = asyncio.run(
        run(with_limits(wall_clock_s=1000.0), ReferenceTransport(never_finishes()),
            "hello", TOOLS, clock=Ticking())
    )
    slow = asyncio.run(
        run(with_limits(wall_clock_s=2.0), ReferenceTransport(never_finishes()),
            "hello", TOOLS, clock=Ticking())
    )
    assert fast.halted == "step-limit"
    assert slow.halted == "time-limit"


# ────────────────────────────────────────────────────── the budget is not reset


def test_a_run_parked_for_a_person_cannot_be_given_a_fresh_budget_by_resuming() -> None:
    """Without carrying the meter, parking for an approval would silently reset
    every ceiling — and the cheapest way past a spend cap would be to trip it."""
    spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=Action.ASK))
    first = asyncio.run(run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS))
    assert first.suspension is not None
    assert first.suspension.used["steps"] == 2

    # Across a real process boundary: only this string survives.
    carried = Suspension.from_json(first.suspension.to_json())
    assert carried.used["steps"] == 2


def test_waiting_for_a_person_does_not_count_against_the_wall_clock() -> None:
    """A deadline is about how long the work takes. Charging a run for the hours
    an approver spent at lunch would make every approval gate a latency bug."""
    m = Meter(started=0.0, carried=5.0)
    assert m.seconds(2.0) == 7.0, "work before the park still counts"
    restored = Meter.restored(m.as_dict(2.0), now=1_000_000.0, steps=0)
    assert restored.seconds(1_000_000.0) == pytest.approx(7.0), "the wait does not"


def test_reaching_a_ceiling_is_announced_at_one_address_whichever_ceiling_it_was() -> None:
    """An observer subscribes to `turn.limit` and sees every exhaustion, without
    knowing there are five of them. That is what the lattice buys and what Eve's
    flat union of 28 events cannot express."""
    from pact_adapters.events import Bus

    seen: list[dict] = []
    bus = Bus()
    bus.on("turn.limit", lambda e: seen.append(e.payload))
    spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=Action.STOP))
    asyncio.run(run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS, bus=bus))
    assert len(seen) == 1
    assert seen[0]["limit"] == "steps-at-most"
    assert seen[0]["ceiling"] == 2
    assert seen[0]["action"] == "stop-and-say-so"


def test_an_unenforceable_ceiling_is_announced_before_any_work_is_done() -> None:
    """Told at the start, not discovered at the end: the point of the message is
    that somebody can turn the run off before it spends the money nobody is
    counting."""
    from pact_adapters.events import Bus

    bus = Bus()
    spec = with_limits(cost_per_request_under=0.05)
    asyncio.run(run(spec, ReferenceTransport(Script([Turn("done")])), "hello", TOOLS, bus=bus))
    addresses = [str(e.address) for e in bus.log]
    assert "session.limit.failed" in addresses
    assert addresses.index("session.limit.failed") < addresses.index("step.model.requested")


# ─────────────────────────────────────────────────────── read from the document


@pytest.fixture(scope="session")
def document() -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def test_the_ceilings_are_read_from_the_authors_own_yaml(document: dict) -> None:
    spec = AgentSpec.from_document(document, "refund-desk")
    assert spec.max_steps == 12, "steps-at-most"
    assert spec.limits.tool_calls_at_most == 40
    assert spec.limits.cost_per_request_under == 0.05
    assert spec.limits.when_it_runs_out is Action.ASK


def test_a_promise_with_no_separate_ceiling_is_enforced_as_the_ceiling(document: dict) -> None:
    """`finishes-within: 30s` reads to its author like a stop, so it is one. A
    promise the system will not enforce is worse than no promise: the author
    believes they capped it."""
    spec = AgentSpec.from_document(document, "refund-desk")
    assert spec.limits.wall_clock_s == 30.0
    assert spec.limits.wall_clock_field == "finishes-within"

    # And a file that writes both keeps them apart: the promise is reported, the
    # ceiling stops the run.
    both = Limits.from_mapping({"finishes-within": "30s", "runs-for-at-most": "5m"})
    assert both.wall_clock_s == 300.0
    assert both.wall_clock_field == "runs-for-at-most"


# ──────────────────────────────────── the two ceilings that used to meter nothing
#
# Everything above this line proves the ceilings WORK. What it could not prove is
# that the two money ones ever measured anything outside this file, and for a
# round they did not: `harness._meter_usage` probed an optional `usage()` that NO
# shipped transport implemented, so `Limits.unmeterable` put both
# `cost-per-request-under` and `tokens-at-most` on `RunResult.unmetered` on every
# real run, and the only transport that ever answered was `Costing`, declared a
# few hundred lines up. A mechanism exercised by its own test fixture is
# decoration — the same sentence `test_context_policy.py` had to write about
# `context_window()` one round earlier.
#
# What closed it is data, not code: every row of `models/catalog.yaml` already
# carried `cost: {input-per-mtok, output-per-mtok}`, the transports whose wire
# format supplies token counts read them off the response object they already
# build, and `resolve.price_of` is the one place a price is looked up.

#: A ticket the desk can decide on in four turns, and cheaply. Sized so the run
#: finishes: what this pair of tests is about is whether the ceiling can MEASURE,
#: and a script that broke the cap would answer a different question.
def a_refund_worth_four_turns() -> Script:
    return Script([
        Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("The ticket says the lamp arrived broken 6 days ago."),
        Turn("Rule 2 applies: faulty on arrival, and 6 days is inside the window."),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])


#: What an agent says when it will not stop talking. Repeated to a size, because
#: the size is the whole point: at `claude-haiku-4-5`'s published 5.00 USD per
#: million output tokens, two turns of this cost more than the author's cap.
_SAYS_TOO_MUCH = "the customer wrote back again about the lamp and asked for an update. "

#: The one row `models/catalog.yaml` deliberately publishes as unpriced. Named
#: here rather than inlined so that the day somebody sources its price, one line
#: moves and the test says which row to point at instead.
UNPRICED_ROW = "gpt-5.4"


def talks_past_what_the_model_holds() -> Script:
    """A desk whose own prose outgrows the window, so the summarising rung fires.

    The bulk has to be the AGENT's words and not a tool result: the shipped
    ladder's first rung, `shorten-long-results`, answers an oversized tool result
    on its own, the ladder stops there, and the rung that makes a model call is
    never reached — which is how `summarised-by:` could be missing on five of
    seven transports for a round without a test noticing.
    """
    window = window_of(default_model()) or 32_768
    said = _SAYS_TOO_MUCH * ((window * CHARS_PER_TOKEN) // len(_SAYS_TOO_MUCH) + 1)
    return Script([
        Turn("Checking the ticket.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("The ticket says the lamp arrived broken 6 days ago. " + said),
        Turn("Rule 2 applies: faulty on arrival, and 6 days is inside the window."),
        Turn("Approved: the item arrived damaged within 30 days."),
    ])


def test_a_run_of_the_worked_example_on_a_priced_transport_meters_both_money_ceilings(
    document: dict,
) -> None:
    """The author's `cost-per-request-under:` line, a real transport, nothing else.

    `examples/refund-desk/agents/refund-desk/limits.yaml` writes
    `cost-per-request-under: 0.05 USD`. Until this round every run of it reported
    that ceiling as unenforced, because no shipped transport could say what a
    call cost. Here the only things supplied are the transport and the tools; the
    ceiling, the model binding and the price it is measured against all come off
    disk.

    Both ceilings are named because they leave by one door:
    `Limits.unmeterable` takes a single "can this transport say?" boolean and
    reports every money-or-token ceiling under it, so a run that has stopped
    reporting `cost-per-request-under` has stopped reporting `tokens-at-most`
    too. `limits.yaml` writes no `tokens-at-most` today, so the second half is
    held here on the meter reading rather than on the absence — a token ceiling
    written tomorrow has a real number to be compared against, which is exactly
    what it did not have yesterday.
    """
    spec = AgentSpec.from_document(document, "refund-desk", EXAMPLE)
    transport = AnthropicTransport(a_refund_worth_four_turns())
    r = asyncio.run(
        run(spec, transport, "my lamp arrived broken, please refund",
            {"zendesk": lambda a: "lamp, broken, 6 days ago", "payments": lambda a: "refunded"})
    )

    assert "cost-per-request-under" not in r.unmetered, r.unmetered
    assert "tokens-at-most" not in r.unmetered, r.unmetered
    assert spec.limits.unmeterable(True) == (), "one door, both ceilings"

    # And it measured rather than merely claiming to. A run that reported zero
    # would be the `unknown`-priced row's failure wearing a success's shape.
    assert r.spent > 0.0, f"the spend cap was told the run cost nothing: {r.spent}"
    assert r.used is not None and r.used.tokens > 0, r.used
    assert r.halted == "final", (r.halted, r.spent)


def test_a_spend_cap_stops_the_run_on_the_call_that_breaks_it_and_not_one_later(
    document: dict,
) -> None:
    """What the cap now REFUSES, at the step it refuses it.

    `harness.py` meters immediately after the model call — *"a spend cap enforced
    one step late has already spent the step that broke it"* — and that sentence
    was unfalsifiable while nothing could say what a call cost. Here the desk is
    given a model that answers at length: the first call is inside the author's
    0.05 USD, the second crosses it, and the run stops on the second rather than
    paying for a third.

    Everything the refusal is measured against is authored: the cap and
    `when-it-runs-out: ask-a-person` come from `limits.yaml`, the price comes
    from `models/catalog.yaml`, and the model id comes from the transport's own
    `runtime:`.
    """
    spec = AgentSpec.from_document(document, "refund-desk", EXAMPLE)
    script = Script([Turn(_SAYS_TOO_MUCH * 350)])
    r = asyncio.run(
        run(spec, AnthropicTransport(script), "my lamp arrived broken, please refund",
            {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"})
    )

    assert r.stopped_by is not None
    assert r.stopped_by.ceiling.field == "cost-per-request-under"
    assert r.stopped_by.ceiling.limit == 0.05, "the author's own figure"
    assert r.halted == "suspended", "`when-it-runs-out: ask-a-person` hands it over"
    assert r.spent >= 0.05, f"it stopped before it reached the cap: {r.spent}"

    # The whole of "not one step late": the call that broke the cap is the last
    # one made. A third would have taken the bill past 0.10 USD — twice what the
    # author wrote — and a cap that only notices then is a cap in name.
    assert script.calls == 2, f"model calls made: {script.calls}"
    assert len(r.steps) == 1, "one step finished; the second is the one that broke it"
    assert r.spent < 0.10, f"a third call was paid for: {r.spent}"


def test_an_unpriced_row_drops_the_money_ceiling_and_keeps_the_token_one(
    document: dict,
) -> None:
    """A price nobody published is `None`, never 0.0 — and a token count is not a price.

    `models/catalog.yaml` publishes one row with `cost: {input-per-mtok:
    unknown, output-per-mtok: unknown}`, and it is there on purpose: §4.2 says a
    figure nobody can source is written `unknown` and never guessed. A transport
    bound to it that answered `(tokens, 0.0)` would take the money ceiling off
    `RunResult.unmetered` and then never reach it — a spend cap that can never
    fire, under an author who believes they capped their spend, which is strictly
    worse than having no cap. So the money half comes back `None`.

    **And only the money half.** For a round `can_price` decided whether
    `usage()` existed AT ALL, so an unpriced row took `tokens-at-most` down with
    it — contradicting that field's own help text, which promises *"This is the
    only ceiling that still bites when there is no price list: a model running on
    your own machine costs nothing per word, so a money cap cannot bound it and
    this can."* It landed on exactly the D17 author the workspace override layer
    was built for: somebody on an air-gapped box adds a row for a locally-served
    model with a window and no `cost:` block, and loses their token ceiling as a
    side effect of having no price. The count was knowable the whole time.
    """
    from pact_adapters.resolve import price_of

    assert price_of(UNPRICED_ROW, 1_000, 1_000) is None, (
        f"{UNPRICED_ROW} is priced now; point this test at a row that is not"
    )
    transport = AnthropicTransport(a_refund_worth_four_turns(), model=UNPRICED_ROW)
    assert transport.usage() == (0, None), (
        "a transport that can count and cannot price says exactly that"
    )
    assert transport.prices_money is False

    spec = AgentSpec.from_document(document, "refund-desk", EXAMPLE)
    r = asyncio.run(
        run(spec, transport, "my lamp arrived broken, please refund",
            {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"})
    )
    assert "cost-per-request-under" in r.unmetered, r.unmetered
    assert r.spent == 0.0, "no price, so nothing was billed — and it says so"
    assert r.used is not None and r.used.tokens > 0, (
        f"the tokens were countable all along: {r.used}"
    )

    # The two halves, on a spec that writes both. The money one goes out; the
    # token one stays and BITES — `tokens-at-most: 100` on a model nobody can
    # price still stops the run, which is the whole capability this recovers.
    priced_at_nothing = replace(
        SPEC, limits=Limits(cost_per_request_under=0.05, tokens_at_most=100)
    )
    both = asyncio.run(
        run(priced_at_nothing, AnthropicTransport(never_finishes(), model=UNPRICED_ROW),
            "hello", TOOLS)
    )
    assert set(both.unmetered) == {"cost-per-request-under"}, both.unmetered
    assert both.halted == "token-limit", (both.halted, both.used)
    assert both.stopped_by is not None
    assert both.stopped_by.ceiling.field == "tokens-at-most"


def test_a_transport_that_cannot_count_at_all_still_reports_both(document: dict) -> None:
    """The other end of the split, kept exercised.

    Splitting the gate must not quietly turn "this transport cannot measure
    anything" into "half of it is fine". `ReferenceTransport` is bound to no
    model, so it neither counts tokens nor prices them, and both ceilings go out
    exactly as they always did — `Limits.unmeterable(False)` with nothing said
    about money means as silent about one as about the other.
    """
    spec = replace(SPEC, limits=Limits(cost_per_request_under=0.05, tokens_at_most=100))
    r = asyncio.run(run(spec, ReferenceTransport(never_finishes()), "hello", TOOLS))
    assert set(r.unmetered) == {"cost-per-request-under", "tokens-at-most"}
    assert spec.limits.unmeterable(False) == (
        "cost-per-request-under",
        "tokens-at-most",
    )
    assert spec.limits.unmeterable(True, False) == ("cost-per-request-under",)
    assert spec.limits.unmeterable(True, True) == ()


def test_the_summarising_models_bill_lands_on_the_meter_the_spend_cap_reads(
    document: dict,
) -> None:
    """A `summarised-by:` model cannot spend outside the author's cap.

    `context-policy.summarised-by:` names a SECOND model, so `write_summary`
    builds a second transport and that call's bill never reaches `usage()` on the
    first — `harness.Transport` says so where `summary_usage()` is declared. On a
    long thread that is one uncounted model call per tidy.

    Measured on a binding that makes the arithmetic unambiguous: the work model
    is the distribution default, whose catalogue row publishes `input-per-mtok:
    0 USD` because this machine serves it, so every cent of what follows was
    spent by the summarising model and by nothing else. The author's own
    `long-threads` ladder, its `when-full: 85%`, its rungs and its
    `when-it-runs-out: ask-a-person` all come off disk; the one line changed is
    the one under test — `summarised-by:`, pointed at a row this catalogue does
    publish a price for.

    The control arm is the same run with `summary_usage` out of reach, which is
    exactly what every transport was one round ago. It does not stop, because
    nothing charges it — and it says `summarised-by-cost` out loud rather than
    reporting a spend of zero as though it were a cheap run.
    """
    expensive = json.loads(json.dumps(document))
    expensive["context-policies"]["long-threads"]["summarised-by"] = "claude-opus-5"
    spec = AgentSpec.from_document(expensive, "refund-desk", EXAMPLE)
    assert spec.context_policy.summarised_by == "claude-opus-5"

    tools = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}
    charged = AutoGenTransport(talks_past_what_the_model_holds())
    assert charged.usage() == (0, 0.0), "nothing spent before anything ran"
    paid = asyncio.run(
        run(spec, charged, "my lamp arrived broken, please refund", tools)
    )

    assert any("summarise-older" in t.fired for t in paid.tidyings), paid.tidyings
    assert "summarised-by-cost" not in paid.unmetered, paid.unmetered
    assert paid.stopped_by is not None
    assert paid.stopped_by.ceiling.field == "cost-per-request-under"
    assert paid.spent >= 0.05, paid.spent

    blind = type(
        "AutoGenThatCannotPriceItsSummariser",
        (AutoGenTransport,),
        {"summary_usage": None},
    )
    free = asyncio.run(
        run(spec, blind(talks_past_what_the_model_holds()),
            "my lamp arrived broken, please refund", tools)
    )
    assert "summarised-by-cost" in free.unmetered, free.unmetered
    assert free.spent == 0.0 and free.stopped_by is None
    assert free.halted == "final", (
        "with nobody counting the summariser, the same run walks past the cap"
    )


# ──────────────────────────────────────────────────────── the same on all seven


@pytest.mark.parametrize("name", sorted(TRANSPORTS))
def test_every_transport_stops_at_the_same_ceiling(name: str) -> None:
    """A limit honoured by one framework and not another is not a limit — it is
    a property of whichever adapter happened to run. This is D12 applied to
    termination."""
    spec = replace(SPEC, max_steps=3, limits=Limits(tool_calls_at_most=2))
    r = asyncio.run(run(spec, TRANSPORTS[name](never_finishes()), "hello", TOOLS))
    assert r.halted == "tool-call-limit"
    assert r.stopped_by is not None and r.stopped_by.ceiling.limit == 2


def test_the_money_ceilings_stop_every_transport_at_the_same_step() -> None:
    """The metering landed on FOUR of the seven, and that is not a ceiling either.

    `langchain`, `langgraph` and `pydantic-ai` carried `context_window()` and
    `write_summary()` and no `usage()`, so `harness.run`'s
    `reports_usage = callable(getattr(transport, "usage", None))` was False for
    them and `Limits.unmeterable` put both money ceilings back on
    `RunResult.unmetered`. Measured on one spec with `tokens-at-most: 100`:
    Anthropic reported `halted=token-limit tokens=125`; those three reported
    `unmetered=('cost-per-request-under', 'tokens-at-most') halted=step-limit
    tokens=0`.

    So the unenforced ceiling was only half of it. The same document terminated
    at `token-limit` on one adapter and `step-limit` on another, which is the
    byte-identical-trace claim failing — and it failed for a reason that has
    nothing to do with the agent. `mock.ReferenceTransport` is bound to no model
    and is excluded on purpose: it is the one transport that keeps the
    `unmetered` route exercised, and a failure route nothing reaches is a route
    nobody has checked.
    """
    spec = replace(SPEC, max_steps=20, limits=Limits(tokens_at_most=100))
    endings = {}
    for name, made in sorted(TRANSPORTS.items()):
        if name == "reference":
            continue
        r = asyncio.run(run(spec, made(never_finishes()), "hello", TOOLS))
        endings[name] = (r.halted, r.unmetered, r.used.tokens > 0)
    assert endings, "no real transports in the registry"
    for name, (halted, unmetered, counted) in endings.items():
        assert unmetered == (), f"{name} cannot measure the author's ceiling: {unmetered}"
        assert counted, f"{name} counted no tokens at all"
        assert halted == "token-limit", f"{name} ended as {halted}, not at the ceiling"
    assert len({e[0] for e in endings.values()}) == 1, endings


TS_DIR = REPO / "adapters" / "typescript"

#: The author's own `limits:` block, given to both ports unchanged. Each reads
#: `30s` and `500 JPY` for itself, so agreement is agreement about the
#: specification rather than about a payload one of them pre-digested.
#:
#: **This used to be three keys**, while the comment above it named two figures
#: that were not in it. Three bugs lived in the gap and all three were in the
#: TypeScript port: the currency was hardcoded `"USD"` so `500 JPY` reported as
#: `500 USD`; `feel`, `first-reply-within`, `per-word-under`, `measured-at` and
#: `asks` were dropped with nothing said; and §7.28 accounted for those five under
#: `slo.*`, a row that could never fire because `pact show` nests them here and
#: nothing ever arrives under `slo:`. A hand-written payload puts a field outside
#: the comparison **by construction**, which is the whole reason the gap held.
#:
#: `tool-calls-at-most: 2` is still the ceiling that binds, so what this test
#: asserts about ENDING is unchanged. The rest is here to be read, reported, or
#: refused — and now it is.
WRITTEN = {
    "steps-at-most": 4,
    "tool-calls-at-most": 2,
    "when-it-runs-out": "stop-and-say-so",
    "feel": "interactive",
    "finishes-within": "30s",
    "first-reply-within": "1s",
    "per-word-under": "50ms",
    "measured-at": "p95",
    "cost-per-request-under": "500 JPY",
    "asks": "keep-going",
}

#: What the second port reads out of `WRITTEN`, and what it must SAY it does not.
#: Written out rather than derived, so a key silently moving from one list to the
#: other is a failure here and not a shrug.
NOT_READ_BY_THE_SECOND_PORT = (
    "asks", "feel", "first-reply-within", "measured-at", "per-word-under",
)


def test_the_typescript_port_stops_at_the_same_ceiling_and_says_the_same_words() -> None:
    """Cross-*runtime* agreement about ENDING, not just about stepping.

    Two ports that agree on every step and then end the run on different rules
    have agreed about nothing that matters, and a difference here would be an
    ambiguity in PACT rather than a bug in one language. Eve runs on this
    runtime and has no ceiling of any kind to agree about.
    """
    spec_payload = json.dumps({
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [{"name": "zendesk", "description": "read the ticket"}],
        "maxSteps": 8,
        "limits": WRITTEN,
    })
    script_payload = json.dumps({
        "turns": [{"text": "still working",
                   "toolCalls": [{"name": "zendesk", "args": {"ticket": "T-1"}}]}]
    })
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         spec_payload, script_payload, "hello"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    ts = json.loads(out.stdout)

    from pact_adapters.limits import steps_at_most

    spec = replace(
        SPEC,
        tools=(ToolSpec("zendesk", "read the ticket"),),
        max_steps=steps_at_most(WRITTEN, 8),
        limits=Limits.from_mapping(WRITTEN),
    )
    tools = {"zendesk": lambda a: f"ticket {a.get('ticket')}: lamp, 6 days ago, broken"}
    script = Script([Turn("still working", (ToolCall("zendesk", {"ticket": "T-1"}),))])
    mine = asyncio.run(run(spec, ReferenceTransport(script), "hello", tools))

    assert ts["halted"] == mine.halted == "tool-call-limit"
    assert ts["output"] == mine.output
    assert ts["trace"] == mine.trace()
    assert mine.stopped_by is not None
    assert ts["stoppedBy"]["limit"] == mine.stopped_by.ceiling.field
    assert ts["stoppedBy"]["ceiling"] == mine.stopped_by.ceiling.limit
    assert ts["stoppedBy"]["action"] == mine.stopped_by.action.value

    # THE AUTHOR'S CURRENCY, in both ports. `cost-per-request-under: 500 JPY`
    # reported as `500 USD` here for a round: `money()` threw the currency away
    # and `ceilings()` printed a hardcoded `"USD"`. The Python port fixed it and
    # says why in `limits.py` — *"reporting a spend cap in the wrong currency is a
    # correctness bug and FR-1.4.5 says it normatively"* — and this port kept the
    # bug, so the two disagreed about what one file means.
    money = next(c for c in spec.limits.ceilings() if c.reads == "money")
    assert money.unit == "JPY", money
    assert "USD" not in json.dumps(ts), (
        "the second port named a currency the author never wrote: "
        + json.dumps(ts)[:400]
    )

    # AND EVERY KEY IT DOES NOT READ, said out loud. These five were dropped in
    # silence while §7.28 accounted for them under `slo.*` — a row that could
    # never fire, because `pact show` nests them under `limits:` and nothing ever
    # arrives under `slo:`.
    said = "\n".join(ts["unenforced"])
    for key in NOT_READ_BY_THE_SECOND_PORT:
        assert f"limits.{key}" in said, (
            f"`{key}` reached this port, held nothing, and nothing said so:\n{said}"
        )
    # And it must not claim to be dropping something it does read.
    for key in ("tool-calls-at-most", "when-it-runs-out", "steps-at-most"):
        assert f"limits.{key}" not in said, f"`{key}` IS read here: {said}"


def test_every_python_transport_reports_the_identical_ending() -> None:
    # SIX targets plus the framework-free control, not seven targets. `TRANSPORTS`
    # is the Python registry; the seventh — Vercel AI — runs in Node and is held
    # by `test_the_typescript_port_stops_at_the_same_ceiling_and_says_the_same_words`
    # a few lines up. Counting the control arm as a target made "all seven" a
    # sentence about six.
    endings = {}
    for name, cls in TRANSPORTS.items():
        spec = replace(SPEC, max_steps=3, limits=Limits(when_it_runs_out=Action.STOP))
        r = asyncio.run(run(spec, cls(never_finishes()), "hello", TOOLS))
        endings[name] = {"halted": r.halted, "output": r.output, "trace": r.trace()}
    reference = endings["reference"]
    for name, got in endings.items():
        assert got == reference, (
            f"{name} ended differently from the reference transport.\n"
            f"  reference: {json.dumps(reference, indent=2)}\n"
            f"  {name}: {json.dumps(got, indent=2)}"
        )


def test_both_ports_name_the_currency_the_author_wrote() -> None:
    """`cost-per-request-under: 0 JPY`, so the MONEY ceiling is the one that fires
    and its wording reaches the output.

    The test above sends `500 JPY` and stops on `tool-calls-at-most`, so the cost
    ceiling's unit never appears in the trace — hardcoding `"USD"` back into
    `limits.ts` left it green. A ceiling that is not the one that fired cannot be
    asserted through the report, which is why this needs its own payload rather
    than another assertion up there.

    `0` binds immediately against a scripted transport that spends nothing, and
    that is the point: the figures are degenerate and the NOUN is what is under
    test. Reporting a spend cap in the wrong currency is a correctness bug and
    FR-1.4.5 says so normatively.
    """
    written = {"steps-at-most": 8, "cost-per-request-under": "0 JPY",
               "when-it-runs-out": "stop-and-say-so"}
    spec_payload = json.dumps({
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [{"name": "zendesk", "description": "read the ticket"}],
        "maxSteps": 8,
        "limits": written,
    })
    script_payload = json.dumps({"turns": [{"text": "done"}]})
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         spec_payload, script_payload, "hello"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    ts = json.loads(out.stdout)

    spec = replace(
        SPEC,
        tools=(ToolSpec("zendesk", "read the ticket"),),
        max_steps=8,
        limits=Limits.from_mapping(written),
    )
    mine = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("done")])), "hello", {})
    )

    assert mine.halted == "cost-limit", mine.halted
    assert ts["halted"] == mine.halted, (ts["halted"], mine.halted)
    assert mine.stopped_by is not None
    said = mine.stopped_by.sentence()
    assert "JPY" in said and "USD" not in said, said
    assert said == ts["stoppedBy"]["sentence"], (said, ts["stoppedBy"]["sentence"])


def test_a_cap_with_no_currency_leaves_no_gap_where_one_would_go() -> None:
    """A bare `cost-per-request-under: 0` — no currency written, so there is no
    noun to print.

    `limits.py` appends the unit rather than interpolating it, and says why: a
    money row whose currency nobody wrote would render `"(0 of 0 )"`, a stray space
    where a currency should be. The second port interpolated unconditionally, which
    was invisible while the unit was the hardcoded `"USD"` and became a divergence
    the moment it stopped being.
    """
    written = {"steps-at-most": 8, "cost-per-request-under": 0,
               "when-it-runs-out": "stop-and-say-so"}
    spec_payload = json.dumps({
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [{"name": "zendesk", "description": "read the ticket"}],
        "maxSteps": 8,
        "limits": written,
    })
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         spec_payload, json.dumps({"turns": [{"text": "done"}]}), "hello"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    ts = json.loads(out.stdout)

    spec = replace(
        SPEC, tools=(ToolSpec("zendesk", "read the ticket"),), max_steps=8,
        limits=Limits.from_mapping(written),
    )
    mine = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("done")])), "hello", {})
    )
    assert mine.stopped_by is not None
    said = mine.stopped_by.sentence()
    assert "0 of 0)" in said, said
    assert " )" not in said, f"a stray space where a currency should be: {said!r}"
    assert said == ts["stoppedBy"]["sentence"], (said, ts["stoppedBy"]["sentence"])
