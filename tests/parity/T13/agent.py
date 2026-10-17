"""02P T13: a toolset a function builds per run is named, and none of its tools is invented."""

from pydantic_ai import Agent
from pydantic_ai.toolsets import FunctionToolset

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", )


@agent.toolset
def per_run(ctx):
    return FunctionToolset([])
