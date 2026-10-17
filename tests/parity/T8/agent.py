"""02P T8: a tool's `prepare=` function is named with the tool it is on."""

from pydantic_ai import Agent
from pydantic_ai import Tool


def lookup(order_number: str) -> str:
    """Look an order up."""
    return "shipped"


async def only_sometimes(ctx, tool_def):
    return tool_def


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", tools=[Tool(lookup, prepare=only_sometimes)])
