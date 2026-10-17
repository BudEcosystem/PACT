"""02P N2: a provider's code execution is named: `run-code` runs on Bud's own room."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.native_tools import CodeExecutionTool

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[NativeTool(CodeExecutionTool())])
