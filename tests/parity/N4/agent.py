"""02P N4: a provider's file search is named: write `knowledge:`."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.native_tools import FileSearchTool

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[NativeTool(FileSearchTool(file_store_ids=["store"]))])
