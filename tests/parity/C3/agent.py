"""02P C3: a history processor is named: its body is code."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory


def last_ten(messages):
    return messages[-10:]


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[ProcessHistory(last_ten)])
