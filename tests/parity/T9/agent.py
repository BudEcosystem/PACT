"""02P T9: a configured tool search is named; the default one every agent has is not."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import ToolSearch

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[ToolSearch(max_results=20)])
