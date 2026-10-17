"""02P X4: the harness's code mode is named, with the PACT stage to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.code_mode import CodeMode

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[CodeMode()])
