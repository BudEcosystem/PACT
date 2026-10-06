"""An agent's own `checked-by:` and `checks-at-most:` (02P O7, A14).

`evals:` grades a recorded case after the fact; `checked-by:` holds the live
answer to the same rule shapes before anyone reads it. The loaded document
carries the rules on `AgentSpec`, read by the door `evals:` uses, and
`evals.first_broken` is the one question a runtime asks of an answer: which
rule, if any, it breaks — deterministic rules first, a `judged:` one only when
something can grade it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import first_broken  # noqa: E402
from pact_adapters.harness import RunResult  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402


def _spec(agent: dict) -> AgentSpec:
    return AgentSpec.from_document({"agents": {"desk": agent}}, "desk")


def test_the_rules_an_answer_must_satisfy_are_carried_with_how_many_tries_it_gets() -> None:
    spec = _spec({
        "checked-by": [
            {"must-contain": ["refund"], "because": "say what happens to the money"},
            {"must-not-contain": ["tomorrow"]},
        ],
        "checks-at-most": 3,
    })
    assert [r.kind for r in spec.checked_by] == ["must-contain", "must-not-contain"]
    assert spec.checks_at_most == 3
    assert spec.checked_by[0].where == "agents/desk/agent.yaml (checked-by)"
    assert _spec({"checked-by": [{"must-contain": ["x"]}]}).checks_at_most == 2, "the schema's default"
    assert _spec({}).checked_by == ()


def test_an_answer_is_told_which_rule_it_breaks_and_why() -> None:
    rules = _spec({"checked-by": [{"must-contain": ["refund"], "because": "say what happens to the money"}]}).checked_by
    assert first_broken(rules, RunResult(output="We will refund you in full.")) == ""
    said = first_broken(rules, RunResult(output="Sorry about that."))
    assert "refund" in said and "say what happens to the money" in said


def test_a_judged_rule_nothing_can_grade_is_reported_and_never_passed_silently() -> None:
    rules = _spec({"checked-by": [{"judged": "is polite"}, {"must-contain": ["refund"]}]}).checked_by
    unenforced: list[str] = []
    assert first_broken(rules, RunResult(output="no"), unenforced=unenforced) == "does not say ['refund']"
    assert unenforced == [], "a deterministic rule decides first, so no grader is reached"
    assert first_broken(rules, RunResult(output="a refund"), unenforced=unenforced) == ""
    assert unenforced and "`judged: is polite` was not applied" in unenforced[0]


def test_a_rule_shape_nobody_can_carry_out_is_reported_not_dropped() -> None:
    spec = _spec({"checked-by": [{"must-rhyme": ["x"]}]})
    assert spec.checked_by == ()
    assert spec.checked_by_unenforced and "is not a rule PACT knows how to carry out" in spec.checked_by_unenforced[0]


def test_pacts_own_pydantic_ai_agent_asks_again_with_the_rule_it_broke() -> None:
    """`build_agent` (PACT's Pydantic AI exporter) holds the same rules: a failing
    answer is sent back with the broken rule's words and the next one is kept."""
    import asyncio

    from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart
    from pydantic_ai.models.function import FunctionModel

    from pact_adapters.pydantic_ai_interop import CHECK_FAILED, build_agent

    seen: list[list] = []
    said = iter(["Sorry about that.", "A full refund is on its way."])

    async def respond(messages: list, info: object) -> ModelResponse:
        seen.append(messages)
        return ModelResponse(parts=[TextPart(next(said))])

    spec = _spec({"name": "Desk", "checked-by": [{"must-contain": ["refund"]}]})
    agent = build_agent(spec, model=FunctionModel(respond))
    result = asyncio.run(agent.run("Refund?"))
    assert result.output == "A full refund is on its way."
    retries = [p for p in seen[1][-1].parts if isinstance(p, RetryPromptPart)]
    assert retries and str(retries[0].content).startswith(CHECK_FAILED)


def test_pacts_own_harness_says_it_holds_none_of_the_three_rather_than_staying_silent() -> None:
    """`harness.run` has no reader for `checked-by:`, `may-start:` or a model
    list. It returned a failing answer with nothing on `unenforced`, so
    `pact-eval` scored an agent whose checks never ran as though they had."""
    import asyncio

    from pact_adapters.harness import run
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    spec = _spec({
        "name": "Desk",
        "checked-by": [{"must-contain": ["refund"]}],
        "model": ["small-one", "big-one"],
        "team": {"helper": "helps"},
        "teamwork": {"may-start": ["narrowed-new"]},
    })
    out = asyncio.run(run(spec, ReferenceTransport(Script([Turn("Sorry about that.")])), "Refund?", {}))
    assert out.output == "Sorry about that.", "the answer breaks the rule and is still returned"
    said = {u.split(":", 1)[0]: u for u in out.unenforced}
    assert "returns the answer unchecked" in said["checked-by"], out.unenforced
    assert "narrowed-new" in said["may-start"], out.unenforced
    assert "big-one" in said["model"] and "small-one" in said["model"], out.unenforced
    # And an agent that wrote none of them is told nothing about them.
    plain = asyncio.run(run(_spec({"name": "Desk"}), ReferenceTransport(Script([Turn("ok")])), "x", {}))
    assert not [u for u in plain.unenforced if u.startswith(("checked-by", "may-start", "model"))]


def _asked(answers: list[str], agent: dict, **kw: object) -> tuple[object, list[list]]:
    """`build_agent` over a model that says `answers` in turn: the agent, and each request."""
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    from pact_adapters.pydantic_ai_interop import build_agent

    seen: list[list] = []
    said = iter(answers)

    async def respond(messages: list, info: object) -> ModelResponse:
        seen.append(messages)
        return ModelResponse(parts=[TextPart(next(said))])

    return build_agent(_spec(agent), model=FunctionModel(respond), **kw), seen


def test_checks_at_most_three_asks_three_times_and_not_twice() -> None:
    """Pydantic AI's own output budget is one retry. With `checks-at-most: 3` the
    run ended at the second failed answer with "Exceeded maximum output retries
    (1)", a ceiling nobody wrote, ahead of the one the author did."""
    import asyncio

    rules = {"name": "Desk", "checked-by": [{"must-contain": ["refund"]}], "checks-at-most": 3}
    agent, seen = _asked(["No.", "Still no.", "A refund is on its way."], rules)
    assert asyncio.run(agent.run("Refund?")).output == "A refund is on its way."
    assert len(seen) == 3

    from pydantic_ai.exceptions import UnexpectedModelBehavior

    agent, seen = _asked(["No.", "Still no.", "Never.", "A refund."], rules)
    try:
        asyncio.run(agent.run("Refund?"))
    except UnexpectedModelBehavior as stopped:
        assert "after 3 attempt(s) the answer still breaks a `checked-by:` rule" in str(stopped)
    else:
        raise AssertionError("a fourth attempt was allowed")
    assert len(seen) == 3, "three attempts, as written"


def test_a_judged_rule_with_nothing_to_grade_it_is_refused_when_the_agent_is_built() -> None:
    """It was skipped: `first_broken` puts an ungradable `judged:` on a list the
    builder never read, so "No. Go away." was returned as a polite answer."""
    import asyncio

    import pytest

    from pact_adapters.judge import Ruling

    rules = {"name": "Desk", "checked-by": [{"judged": "is polite", "because": "customers read this"}]}
    with pytest.raises(ValueError, match=r"`judged: is polite`.*pass `judge=`"):
        _asked(["No. Go away."], rules)

    class Grader:
        asked: list[str] = []

        def grade(self, sentence: str, answer: str, because: str = "", **_: object) -> Ruling:
            self.asked.append(answer)
            polite = "sorry" in answer.lower()
            return Ruling(decided=True, passed=polite, reason="" if polite else "it is curt")

    agent, seen = _asked(["No. Go away.", "Sorry, we cannot do that."], rules, judge=Grader())
    assert asyncio.run(agent.run("Refund?")).output == "Sorry, we cannot do that."
    assert Grader.asked == ["No. Go away.", "Sorry, we cannot do that."] and len(seen) == 2


def test_a_rule_about_what_the_run_did_is_decided_from_the_calls_it_made() -> None:
    """`must-call-before:` reads the run's calls, and the check was handed the
    answer alone, so the rule could never be broken."""
    import asyncio

    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    from pact_adapters.pydantic_ai_interop import CHECK_FAILED, build_agent

    doc = {
        "agents": {"desk": {
            "name": "Desk", "uses": ["orders", "payments"],
            "checked-by": [{"must-call-before": {"call": "payments", "first": "orders"}}],
        }},
        "tools": {"orders": {"description": "Looks an order up."}, "payments": {"description": "Pays."}},
    }
    turns = iter([
        ModelResponse(parts=[ToolCallPart("payments", {}, tool_call_id="c1")]),
        ModelResponse(parts=[TextPart("Refunded.")]),
        ModelResponse(parts=[TextPart("Refunded, sorry for the order of things.")]),
    ])
    seen: list[list] = []

    async def respond(messages: list, info: object) -> ModelResponse:
        seen.append(messages)
        return next(turns)

    agent = build_agent(
        AgentSpec.from_document(doc, "desk"), model=FunctionModel(respond), call_tool=lambda name, args: "ok"
    )
    try:
        asyncio.run(agent.run("Refund O-9"))
    except Exception as stopped:  # noqa: BLE001 — the second attempt still breaks it
        assert "called 'payments' without calling 'orders' first" in str(stopped), stopped
    else:
        raise AssertionError("an answer that paid without looking the order up was returned")
    assert str(seen[2][-1].parts[0].content).startswith(CHECK_FAILED)


def test_the_words_of_a_built_agent_are_filled_or_the_build_is_refused() -> None:
    """`build_agent` handed the model `{{run-inputs.brand}}` as written."""
    import asyncio

    import pytest

    from pact_adapters.holes import Unfilled

    words = {
        "name": "Writer", "description": "Writes for {{run-inputs.brand}}.",
        "run-inputs": {"brand": "text"},
        "instructions": r"Write in the voice of {{run-inputs.brand}}. Sign as \{{signature}}.",
    }
    with pytest.raises(Unfilled, match="brand"):
        _asked(["ok"], words)
    agent, seen = _asked(["ok"], words, run_inputs={"brand": "Acme"})
    assert agent.description == "Writes for Acme."
    asyncio.run(agent.run("Write one."))
    told = seen[0][0].instructions
    assert told == "Write in the voice of Acme. Sign as {{signature}}.", told
