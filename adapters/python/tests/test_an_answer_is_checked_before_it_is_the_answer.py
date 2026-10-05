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
