"""02P O6: an output function is named: code."""

from pydantic_ai import Agent


def file_claim(order_number: str, reason: str) -> str:
    return "filed"


agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", output_type=file_claim)
