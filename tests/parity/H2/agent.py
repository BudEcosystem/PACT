"""02P H2: the harness's background tools are named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.background_tools import BackgroundTools

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[BackgroundTools()])
