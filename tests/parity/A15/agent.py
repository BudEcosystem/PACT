"""02P A15: a tool timeout is named with the tool it is on."""

from pydantic_ai import Agent
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", tool_timeout=5)


@agent.tool_plain
def lookup(order_number: str) -> str:
    """Look an order up."""
    return "shipped"
