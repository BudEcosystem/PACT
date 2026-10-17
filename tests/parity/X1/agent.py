"""02P X1: a capability combined from others is read through, each one named."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import CombinedCapability, Thinking, ToolSearch

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[CombinedCapability([Thinking(effort="low"), ToolSearch(max_results=5)])])
