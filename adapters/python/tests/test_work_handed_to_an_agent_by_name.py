"""P4 — the dynamic-bottom rule: an agent put to work BY VALUE writes its own figure.

PACT ships two halves that arrived together and were never joined. A `run-inputs:`
line of shape `agent` carries the NAME of one of this workspace's agents, validated
as a plain key and then dereferenced by nothing; `limits.asks-itself-at-most:` meters
ACTIVATIONS per request but is only ever reached over the STATIC `team:` graph, which
is the only graph `pact-loader/src/teams.rs` legalises a circle over — and it
legalises one only when every member on it writes its own figure.

Joining the halves naively would hand the model a delegation edge the loader never
saw, so the obligation that makes recursion terminate has to move with the edge:

    An agent may be put to work BY VALUE only if it writes its own
    `limits.asks-itself-at-most:` figure.

That is the same sentence as the static rule, relocated from the circle to the
receivable agent, because under dynamic dispatch the potential call graph is "any
agent an `agent`-shaped value can name" and no smaller graph can be checked ahead
of time.

What this file prevents: a surrounding system naming a bottomless agent, that agent
naming another, and the request recursing to a `RecursionError` — an opaque crash
in place of the authored sentence — while `pact check` printed OK over a document
whose static `team:` graph is acyclic and therefore never asked anyone to count.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import ToolCall, delegate_by_running, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

#: A desk with an EMPTY `team:` — nobody is named at authoring time — and one
#: `run-inputs:` line of shape `agent`. Who does the second look is a fact the
#: ticketing system has and the document does not, which is exactly what the
#: schema's help text says an `agent` line is for: "what is handed over is a name
#: from this same tree, never a place to fetch anything from".
#:
#: `night-shift` writes the figure, so it is receivable by value.
BY_VALUE = {
    "agents": {
        "front-desk": {
            "description": "Takes the request and hands the second look to whoever is on.",
            "instructions": (
                "Answer the question. Hand the second look to the teammate the "
                "ticketing system put on this request, then say what you decided."
            ),
            "run-inputs": {"second-look": "agent"},
            "team": {},
        },
        "night-shift": {
            "description": "Takes a second look at a drafted answer.",
            "instructions": "Say what you see, briefly.",
            "limits": {
                "asks-itself-at-most": 2,
                "when-it-runs-out": "stop-and-say-so",
            },
        },
    }
}


def hands_it_over() -> Script:
    """A model that hands the work to `night-shift` by name on its first step and
    answers on its second. The name is in the script because it is in the tool
    list: an agent admitted by value is OFFERED, and a name the model is never
    shown is a name it can never say."""
    return Script([
        Turn("Handing the second look over.",
             (ToolCall("night-shift", {"question": "does this hold up?"}),)),
        Turn("Second look done; approved."),
    ])


def second_look() -> Script:
    """The member. One turn, no tools — it is asked and it answers."""
    return Script([Turn("Looks right to me.")])


def test_an_agent_named_by_the_surrounding_system_is_put_to_work() -> None:
    """A `run-inputs:` value of shape `agent` becomes a real delegation edge: the
    named agent is offered, run, and metered on the SAME activation counter as a
    static teammate — two entries, one per agent activated, because the root's own
    activation is the first spend and the member's is the second."""
    built: list[str] = []

    def transport_for(member: AgentSpec) -> ReferenceTransport:
        built.append(member.name)
        return ReferenceTransport(second_look())

    bus = Bus()
    meter: dict[str, int] = {}
    spec = AgentSpec.from_document(BY_VALUE, "front-desk")
    result = asyncio.run(
        run(spec, ReferenceTransport(hands_it_over()), "is this right?",
            run_inputs={"second-look": "night-shift"},
            ask_member=delegate_by_running(BY_VALUE, transport_for, bus=bus),
            at_work=meter,
            bus=bus)
    )

    # The work reached the named agent — no "no tool named 'night-shift'", no
    # `waiting-for-another-agent` suspension.
    assert result.halted == "final"
    assert result.output == "Second look done; approved."
    assert result.steps[0].tool_results == ("Looks right to me.",)
    assert built == ["night-shift"]
    # And the delegation is on the trace, under the same event a static teammate
    # emits — one path, not two.
    done = [e for e in bus.seen("step.delegate.completed")]
    assert [e.payload["member"] for e in done] == ["night-shift"]
    assert not list(bus.seen("step.delegate.failed"))
    # The meter counted BOTH activations: the root's own (front-desk) and the
    # member's. 1 each, because each was put to work exactly once.
    assert meter == {"front-desk": 1, "night-shift": 1}


#: The same arrangement with the one line removed: `night-shift` writes no
#: `limits.asks-itself-at-most:`. Its static `team:` graph is still acyclic, so the
#: loader has no circle to refuse and never asks it to count — which is precisely
#: why the obligation has to be checked here, at the value.
NO_BOTTOM = {
    "agents": {
        "front-desk": {
            "description": "Takes the request and hands the second look to whoever is on.",
            "instructions": (
                "Answer the question. Hand the second look to the teammate the "
                "ticketing system put on this request, then say what you decided."
            ),
            "run-inputs": {"second-look": "agent"},
            "team": {},
        },
        "night-shift": {
            "description": "Takes a second look at a drafted answer.",
            "instructions": "Say what you see, briefly.",
        },
    }
}

#: The positive control, built from `NO_BOTTOM` itself so that exactly ONE line
#: separates them. A refusal test alone proves nothing: it cannot tell "refused
#: because the figure is missing" from "this document never worked".
WITH_A_BOTTOM = copy.deepcopy(NO_BOTTOM)
WITH_A_BOTTOM["agents"]["night-shift"]["limits"] = {"asks-itself-at-most": 2}


def _dispatch(document: dict, built: list[str], bus: Bus):
    """One run of `front-desk` that hands the second look to `night-shift` by
    value. The only thing that varies between the refusal and its control is the
    document, which is what makes the pair a control at all."""
    def transport_for(member: AgentSpec) -> ReferenceTransport:
        built.append(member.name)
        return ReferenceTransport(second_look())

    spec = AgentSpec.from_document(document, "front-desk")
    return asyncio.run(
        run(spec, ReferenceTransport(hands_it_over()), "is this right?",
            run_inputs={"second-look": "night-shift"},
            ask_member=delegate_by_running(document, transport_for, bus=bus),
            bus=bus)
    )


def test_an_agent_named_by_value_without_a_bottom_is_refused() -> None:
    """A bottomless agent named by value is that MEMBER'S failure, not a crash:
    it travels the `OverBudget`-shaped path, so `if-someone-fails:` decides what
    happens next, and the text names the line to add rather than the traceback of
    a runtime that gave up. Zero transports are built, because the refusal
    happens before the member is ever run."""
    built: list[str] = []
    bus = Bus()
    result = _dispatch(NO_BOTTOM, built, bus)

    # A failure, not an exception: the run finished and the author's default
    # `if-someone-fails: carry-on` carried on.
    assert result.halted == "final"
    assert result.output == "Second look done; approved."
    assert built == [], "the refused member must never be put to work"
    refused = [e for e in bus.seen("step.delegate.failed")]
    assert refused, "a bottomless agent was accepted by value"
    assert [e.payload["member"] for e in refused] == ["night-shift"]
    reason = refused[0].payload["reason"]
    # The two things a person needs to fix it: who, and which line.
    assert "night-shift" in reason
    assert "asks-itself-at-most" in reason


def test_the_same_document_with_the_bottom_written_succeeds() -> None:
    """The positive control for the refusal above. One added line —
    `asks-itself-at-most: 2` on `night-shift` — and the identical dispatch is
    admitted, run and answered. Without this the refusal would be indistinguishable
    from a document that could never have worked."""
    built: list[str] = []
    bus = Bus()
    result = _dispatch(WITH_A_BOTTOM, built, bus)

    assert result.halted == "final"
    assert result.output == "Second look done; approved."
    assert built == ["night-shift"]
    assert result.steps[0].tool_results == ("Looks right to me.",)
    assert not list(bus.seen("step.delegate.failed"))


#: A plain document with a static team and a `run-inputs:` line that is NOT of
#: shape `agent`. Nothing here can be dispatched by value, so nothing about this
#: run may differ by one byte from what it was before the rule existed.
NO_AGENT_SHAPE = {
    "agents": {
        "desk": {
            "description": "Decides refunds.",
            "instructions": "Ask the helper, then decide.",
            "run-inputs": {"locale": "text"},
            "team": {"helper": "checks the ticket."},
        },
        "helper": {
            "description": "Checks tickets.",
            "instructions": "Say what you see.",
        },
    }
}


def _plain_run(run_inputs: dict | None = None):
    def transport_for(member: AgentSpec) -> ReferenceTransport:
        return ReferenceTransport(Script([Turn("looks fine")]))

    spec = AgentSpec.from_document(NO_AGENT_SHAPE, "desk")
    kwargs = {} if run_inputs is None else {"run_inputs": run_inputs}
    return asyncio.run(
        run(spec,
            ReferenceTransport(Script([
                Turn("Asking the helper.",
                     (ToolCall("helper", {"question": "ok?"}),)),
                Turn("Approved."),
            ])),
            "refund?",
            ask_member=delegate_by_running(NO_AGENT_SHAPE, transport_for),
            **kwargs)
    )


def test_no_agent_shaped_input_no_behaviour_change() -> None:
    """Additive inertness. A document that declares no `agent`-shaped run-input
    produces a byte-equal trace whether the surrounding system supplies its
    run-inputs or not — the admission pass reads the declared shapes, finds none
    that is `agent`, and adds nothing to the tool list, the delegates or the
    trace. The generated sentence never appears where a model or a reader could
    see it."""
    default = _plain_run()
    handed = _plain_run(run_inputs={"locale": "en-GB"})
    assert json.dumps(default.trace()) == json.dumps(handed.trace())
    assert default.halted == handed.halted == "final"
    assert default.output == handed.output == "Approved."
    assert default.steps[0].tool_results == ("looks fine",)
    # And the admission sentence never surfaces on a run that admitted nothing.
    assert "chosen for this request by" not in json.dumps(default.trace())


#: The receivable agent, reached two ways. `desk-by-value` names nobody at
#: authoring time and is handed the name; `desk-by-team` writes the same name
#: under `team:`. Everything else — the member, its figure, the model's script —
#: is identical, so any difference in how far the recursion runs is the dispatch
#: mechanism and nothing else.
TWO_WAYS = {
    "agents": {
        "desk-by-value": {
            "description": "Hands three looks to whoever is on.",
            "instructions": "Hand the work over, then say what you decided.",
            "run-inputs": {"second-look": "agent"},
            "team": {},
        },
        "desk-by-team": {
            "description": "Hands three looks to the night shift.",
            "instructions": "Hand the work over, then say what you decided.",
            "team": {"night-shift": "takes a second look at a drafted answer."},
        },
        "night-shift": {
            "description": "Takes a second look at a drafted answer.",
            "instructions": "Say what you see, briefly.",
            "limits": {
                "asks-itself-at-most": 2,
                "when-it-runs-out": "stop-and-say-so",
            },
        },
    }
}


def asks_three_times() -> Script:
    """One hand-over per step, three steps running, then an answer. Three asks
    against a figure of 2 is the smallest script that can show where the meter
    stops — two is not enough to prove anything stops."""
    return Script([
        Turn("First look.", (ToolCall("night-shift", {"question": "first?"}),)),
        Turn("Second look.", (ToolCall("night-shift", {"question": "second?"}),)),
        Turn("Third look.", (ToolCall("night-shift", {"question": "third?"}),)),
        Turn("Decided."),
    ])


def _three_asks(root: str, run_inputs: dict | None):
    built: list[str] = []
    bus = Bus()

    def transport_for(member: AgentSpec) -> ReferenceTransport:
        built.append(member.name)
        return ReferenceTransport(second_look())

    spec = AgentSpec.from_document(TWO_WAYS, root)
    kwargs = {} if run_inputs is None else {"run_inputs": run_inputs}
    result = asyncio.run(
        run(spec, ReferenceTransport(asks_three_times()), "three looks please",
            ask_member=delegate_by_running(TWO_WAYS, transport_for, bus=bus),
            bus=bus, **kwargs)
    )
    return result, built, bus


def test_a_dynamically_named_agent_spends_the_same_meter() -> None:
    """`asks-itself-at-most: 2` buys two ACTIVATIONS of `night-shift` per request
    however it was reached. Asked three times, it runs twice and the third is
    refused with the spent line named — and the by-value dispatch stops at exactly
    the same number as the `team:` dispatch, which is the whole claim: routing
    through the same `ask` means the meter cannot be escaped by not being on the
    static graph.

    Two, not three, because the figure is 2 and the member's own activations are
    what it counts; the root's activation is spent against the root's own name.
    """
    by_value, value_built, value_bus = _three_asks(
        "desk-by-value", {"second-look": "night-shift"}
    )
    by_team, team_built, team_bus = _three_asks("desk-by-team", None)

    for result, built, bus, how in (
        (by_value, value_built, value_bus, "by value"),
        (by_team, team_built, team_bus, "by team"),
    ):
        assert result.halted == "final", how
        assert result.output == "Decided.", how
        # Exactly the figure: two activations bought, the third refused before a
        # transport is ever built for it.
        assert built == ["night-shift", "night-shift"], how
        refused = [e for e in bus.seen("step.delegate.failed")]
        assert len(refused) == 1, f"{how}: the third activation was not refused"
        assert "asks-itself-at-most" in refused[0].payload["reason"], how

    # And the two dispatches are the same run, not two similar ones.
    assert value_built == team_built
    assert json.dumps(by_value.trace()) == json.dumps(by_team.trace())
