"""02P C4: a provider's own compaction is named."""

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAICompaction

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[OpenAICompaction()])
