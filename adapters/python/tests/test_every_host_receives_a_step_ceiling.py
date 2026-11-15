"""Every run has a step ceiling, on every host (law 2, option A — docs/98 WP-3).

`AgentSpec.max_steps` is the author's `steps-at-most`, or `DEFAULT_STEPS` when
they wrote none, and `usage_limits_for` hands it to Pydantic AI either way. This
file used to hold the opposite (`test_a_ceiling_nobody_wrote_is_not_carried.py`):
an unwritten ceiling crossed as `None`, so the same agent stopped at eight steps
on PACT's loop and ran until its money ran out on a foreign one. The owner
decided on 2026-11-10 (docs/97-PRIMITIVES.md §14, decision 2) that "this agent
stops" holds on every host, and that the one way to have no ceiling is an
owner's `limits.unbounded: yes`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import DEFAULT_STEPS, UNBOUNDED_STEPS, AgentSpec  # noqa: E402
from pact_adapters.pydantic_ai_interop import usage_limits_for  # noqa: E402


def _spec(limits: dict | None = None) -> AgentSpec:
    agent = {"description": "d", "instructions": "i"}
    if limits is not None:
        agent["limits"] = limits
    return AgentSpec.from_document({"agents": {"a": agent}}, "a")


def test_no_ceiling_written_is_the_default_ceiling_on_every_host() -> None:
    spec = _spec()
    assert spec.max_steps == DEFAULT_STEPS and not spec.steps_written
    assert not spec.unbounded
    limits = usage_limits_for(spec)
    assert limits.request_limit == DEFAULT_STEPS
    # The other two are still only the author's: neither has a default here.
    assert limits.tool_calls_limit is None
    assert limits.total_tokens_limit is None


def test_what_the_author_wrote_is_what_crosses() -> None:
    spec = _spec(
        {
            "steps-at-most": 3,
            "tool-calls-at-most": 7,
            "tokens-at-most": 900,
            "when-it-runs-out": "stop-and-say-so",
        }
    )
    assert spec.steps_written
    limits = usage_limits_for(spec)
    assert (limits.request_limit, limits.tool_calls_limit, limits.total_tokens_limit) == (3, 7, 900)


def test_an_owners_unbounded_is_the_only_way_to_no_ceiling() -> None:
    spec = _spec({"unbounded": "yes"})
    assert spec.unbounded and not spec.steps_written
    assert spec.max_steps == UNBOUNDED_STEPS
    assert usage_limits_for(spec).request_limit is None


def test_unbounded_no_is_the_default() -> None:
    spec = _spec({"unbounded": "no"})
    assert not spec.unbounded
    assert usage_limits_for(spec).request_limit == DEFAULT_STEPS


def test_a_default_ceiling_is_never_called_the_limit_you_set() -> None:
    """A person told a run stopped at "the limit you set" goes looking for a line
    nobody wrote. The default ceiling says it is PACT's, and how to set one."""
    from pact_adapters.limits import Action, Limits, Meter, Reached, step_ceiling

    said = Reached(step_ceiling(DEFAULT_STEPS, default=True), float(DEFAULT_STEPS), Action.STOP).sentence()
    assert "you set" not in said
    assert f"PACT's default limit, `steps-at-most` ({DEFAULT_STEPS} of {DEFAULT_STEPS} steps)" in said
    assert "write one under `limits:`" in said
    written = Reached(step_ceiling(3), 3.0, Action.STOP).sentence()
    assert "the limit you set with `steps-at-most` (3 of 3 steps)" in written
    meter = Meter(started=0.0)
    meter.steps = DEFAULT_STEPS
    reached = Limits().reached(meter, 0.0, DEFAULT_STEPS, steps_default=True)
    assert reached is not None and reached.ceiling.default
