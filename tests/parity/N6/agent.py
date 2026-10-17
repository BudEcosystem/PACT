"""02P N6: the harness's advisor is named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.advisor import Advisor

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[Advisor(model="test")])
