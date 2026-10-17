"""02P C5: the harness's compaction is named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.compaction import SlidingWindowCompaction

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[SlidingWindowCompaction(max_messages=10)])
