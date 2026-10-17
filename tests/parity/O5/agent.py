"""02P O5: a `TextOutput` function is named: code."""

from pydantic_ai import Agent
from pydantic_ai import TextOutput


def shout(text: str) -> str:
    return text.upper()


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", output_type=TextOutput(shout))
