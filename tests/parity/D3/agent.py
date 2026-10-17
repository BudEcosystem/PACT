"""02P D3: the harness's step persistence is named: a PACT run journals every step."""

from pydantic_ai import Agent
from pydantic_ai_harness.step_persistence import StepPersistence

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[StepPersistence()])
