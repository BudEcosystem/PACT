"""02P H6: a handler for deferred calls is named: its body is code."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import HandleDeferredToolCalls


async def answer(ctx, requests):
    return None


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[HandleDeferredToolCalls(answer)])
