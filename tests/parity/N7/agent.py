"""02P N7: a provider's own tool is named."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.native_tools import WebSearchTool

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[NativeTool(WebSearchTool())])
