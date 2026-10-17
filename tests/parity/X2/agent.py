"""02P X2: hooks are named: their bodies are code."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks

hooks = Hooks()
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[hooks])
