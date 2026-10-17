"""02P A9: settings made by a function each step are named, not carried."""

from pydantic_ai import Agent
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", model_settings=lambda ctx: {"temperature": 0.1})
