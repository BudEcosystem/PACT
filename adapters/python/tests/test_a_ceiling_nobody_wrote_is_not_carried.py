"""`usage_limits_for` carries the author's ceilings, and only theirs.

`AgentSpec.max_steps` falls back to this port's own loop bound (`DEFAULT_STEPS`)
when `steps-at-most` is not written. That number is PACT's harness, not the
document, so a host whose loop is Pydantic AI's must not receive it as a
ceiling; and `UsageLimits` caps at `request_limit=50` by default
(pydantic_ai/usage.py:482), which is a ceiling nobody wrote either. So an
unwritten ceiling crosses as `None`, explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import DEFAULT_STEPS, AgentSpec  # noqa: E402
from pact_adapters.pydantic_ai_interop import usage_limits_for  # noqa: E402


def _spec(limits: dict | None = None) -> AgentSpec:
    agent = {"description": "d", "instructions": "i"}
    if limits is not None:
        agent["limits"] = limits
    return AgentSpec.from_document({"agents": {"a": agent}}, "a")


def test_no_limits_written_is_no_ceiling_at_all() -> None:
    spec = _spec()
    assert spec.max_steps == DEFAULT_STEPS and not spec.steps_written
    limits = usage_limits_for(spec)
    assert limits.request_limit is None
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


def test_a_ceiling_written_as_the_default_number_is_still_written() -> None:
    spec = _spec({"steps-at-most": DEFAULT_STEPS, "when-it-runs-out": "stop-and-say-so"})
    assert spec.steps_written
    assert usage_limits_for(spec).request_limit == DEFAULT_STEPS
