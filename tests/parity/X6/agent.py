"""02P X6: the harness's memory is named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.memory import Memory

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[Memory()])
