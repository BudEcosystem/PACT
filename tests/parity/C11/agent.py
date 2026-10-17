"""02P C11: the harness's spend limits are named, with the PACT Rule to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.spend import SpendLimits

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[SpendLimits()])
