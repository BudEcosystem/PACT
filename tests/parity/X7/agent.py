"""02P X7: the harness's guardrails are named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.guardrails import InputGuardrail


def ok(text):
    return True


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[InputGuardrail(ok)])
