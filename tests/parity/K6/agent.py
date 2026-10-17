"""02P K6: the harness's coder stack is named: PACT ships templates."""

from pydantic_ai import Agent
from pydantic_ai_harness.repo_context import RepoContext

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[RepoContext()])
