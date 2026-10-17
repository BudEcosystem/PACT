"""02P A5: a dynamic instruction is counted and named, never carried as the author's words."""

from pydantic_ai import Agent
from pydantic_ai import RunContext

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", )


@agent.instructions
def today(ctx: RunContext) -> str:
    return "Today is the day the run starts."
