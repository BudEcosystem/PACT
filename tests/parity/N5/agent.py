"""02P N5: an MCP server the provider connects to is named: write a resource Bud connects to."""

from pydantic_ai import Agent
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.native_tools import MCPServerTool

agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", capabilities=[NativeTool(MCPServerTool(id="crm", url="https://crm.example.com/mcp"))])
