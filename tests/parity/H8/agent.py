"""02P H8: the harness's tool-call judge is named, with the PACT line to write."""

from pydantic_ai import Agent
from pydantic_ai_harness.tool_call_judge import ToolCallJudge

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[ToolCallJudge("test", question="Is this call safe?")])
