"""02P F4: an answer that is a file is named: `answers-with:` holds named fields."""

from pydantic_ai import Agent
from pydantic_ai import BinaryImage

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", output_type=BinaryImage)
