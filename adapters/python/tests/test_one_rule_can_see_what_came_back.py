"""A rule can see what a tool returned, and not only what is about to go (A1).

`interceptor.when`'s `reaches:` listed five moments and not one of them saw a
RESULT. Every entry was "words are about to leave": before the customer's words
reach the model, before a step's own words are written down, before the reply
goes back, before a value is handed to a tool, before a teammate is asked.

So hiding was one-directional. A card number the agent typed into a `payments`
argument was masked; the same card number `payments` handed back was not — and a
tool result goes into the history and is read to the model on its next turn, so
it leaves by exactly the same door. `redaction.yaml`'s own promise is "what must
never leave this workspace".

The run already reached the moment. `harness.py` emitted `step.tool.completed`
on the bus, and a WATCH could bind there and be accepted while an interceptor
bound there was told *"nothing in a run ever reaches"* it — a message that was
false in the one tree where it mattered.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.interceptors import WIRED, Chain, InterceptorError  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

CARD = "4111 1111 1111 1111"


def hiding_what_comes_back(rules: list[str] | None = None) -> Chain:
    return Chain.from_document(
        {
            "agents": {"desk": {"interceptors": ["hide-what-comes-back"]}},
            "interceptors": {
                "hide-what-comes-back": {
                    "description": "A card number a tool returns must not reach the model.",
                    "when": "step.tool.completed",
                    "may": ["hide-values"],
                    "rules": rules
                    or ['replace anything that looks like a card number with "***"'],
                }
            },
        },
        "desk",
    )


def a_run_whose_tool_returns_a_card(chain: Chain):
    spec = AgentSpec(
        name="Desk", description="Answers", instructions="Look it up.",
        tools=(ToolSpec("lookup", "reads the file"),),
    )
    script = Script([Turn("looking", (ToolCall("lookup", {}),)), Turn("done", ())])
    tools = {"lookup": lambda a: f"card on file: {CARD}"}
    return asyncio.run(run(spec, ReferenceTransport(script), "hi", tools, chain=chain))


def test_a_card_number_a_tool_returned_is_hidden_before_the_model_sees_it() -> None:
    r = a_run_whose_tool_returns_a_card(hiding_what_comes_back())
    assert not any(CARD in str(s.tool_results) for s in r.steps), (
        "the result reached the trace whole: " + str([s.tool_results for s in r.steps])
    )
    assert any("***" in str(s.tool_results) for s in r.steps)


def test_with_no_rule_bound_there_the_result_is_untouched() -> None:
    """The tightening must cost the ordinary case nothing."""
    r = a_run_whose_tool_returns_a_card(Chain())
    assert any(CARD in str(s.tool_results) for s in r.steps)


def test_the_moment_carries_values_and_nothing_it_cannot_honour() -> None:
    """What the address carries is a table, and the table is the thing that
    stops a power going back to being one that loads and does nothing."""
    carries = WIRED["step.tool.completed"]
    assert carries.values, "a result is exactly the shape a hiding rule reads"
    assert not carries.somewhere_else, (
        "the call has already happened — there is nothing left to send elsewhere"
    )
    assert not carries.an_answer, (
        "a tool result is not something the agent said, and a rule about what the "
        "agent says must not fire on what a tool told it"
    )
    assert not carries.which_tool, (
        "counting in order to prevent a call has to happen before the call; "
        "stopping after the money moved is not stopping"
    )


def test_a_counting_rule_is_still_refused_after_the_call_has_happened() -> None:
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(
            {
                "agents": {"desk": {"interceptors": ["too-late"]}},
                "interceptors": {
                    "too-late": {
                        "description": "Count refunds.",
                        "when": "step.tool.completed",
                        "may": ["stop-the-run"],
                        "rules": [
                            'if payments is called more than 3 times in one run, '
                            'stop and say "too many"'
                        ],
                    }
                },
            },
            "desk",
        )
    assert "would do nothing" in str(e.value)
    assert "step.tool.before" in str(e.value), "the fix names the moment that works"


def test_a_rule_can_end_the_run_on_what_a_tool_returned() -> None:
    """Tom's persona: stop at the first failed step. The result is the first
    sight of the failure, so the moment that sees it has to be able to end it."""
    from pact_adapters.interceptors import guard

    chain = Chain()
    chain.add(
        guard(
            "stop-on-failure",
            "step.tool.completed",
            lambda p: "The lookup failed; stopping." if "error" in str(p.get("content", "")) else None,
        )
    )
    spec = AgentSpec(
        name="Desk", description="Answers", instructions="Look it up.",
        tools=(ToolSpec("lookup", "reads the file"),),
    )
    script = Script([Turn("looking", (ToolCall("lookup", {}),)), Turn("done", ())])
    r = asyncio.run(
        run(spec, ReferenceTransport(script), "hi", {"lookup": lambda a: "error: not found"},
            chain=chain)
    )
    assert r.halted == "stopped-by-rule", r.halted
    assert r.output == "The lookup failed; stopping."
