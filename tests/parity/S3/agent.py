"""02P S3: an event stream handler is named: code that watches a run."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessEventStream


async def watch(ctx, events):
    async for _ in events:
        pass


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[ProcessEventStream(watch)])
