"""02P T7: metadata set on a tool's definition is named."""

from pydantic_ai import Agent
from pydantic_ai.toolsets import FunctionToolset


def lookup(order_number: str) -> str:
    """Look an order up."""
    return "shipped"


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", toolsets=[FunctionToolset([lookup]).with_metadata(team="cx")])
