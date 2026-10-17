"""02P K1: an agent called inside a tool is a tool: the delegation is invisible in code, so only the tool is carried."""

from pydantic_ai import Agent

helper = Agent(name="helper")
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", )


@agent.tool_plain
async def ask_helper(question: str) -> str:
    """Ask the helper."""
    return (await helper.run(question)).output
