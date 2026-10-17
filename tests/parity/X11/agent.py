"""02P X11: a runtime capability is named."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import RaiseContentFilterError

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[RaiseContentFilterError()])
