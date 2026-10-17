"""02P X8: the harness's file system is named: write a sandbox resource."""

from pydantic_ai import Agent
from pydantic_ai_harness.filesystem import FileSystem

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[FileSystem()])
