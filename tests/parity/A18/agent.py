"""02P A18: a limit on runs at once has no public read, and the import says so."""

from pydantic_ai import Agent
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", max_concurrency=2)
