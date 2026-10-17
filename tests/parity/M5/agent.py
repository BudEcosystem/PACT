"""02P M5: a model picked by code each run is named."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import SelectModel


def pick(ctx):
    return "test"


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[SelectModel(pick)])
