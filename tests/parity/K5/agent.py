"""02P K5: the harness's planning is named, with the PACT loop to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.planning import Planning

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[Planning()])
