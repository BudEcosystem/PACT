"""02P T4: an approval a function decides asks a person for every call, and the function is named."""

from pydantic_ai import Agent
from pydantic_ai.toolsets import ApprovalRequiredToolset, FunctionToolset


def refund(order_number: str) -> str:
    """Refund an order."""
    return "refunded"


tools = ApprovalRequiredToolset(FunctionToolset([refund]), approval_required_func=lambda ctx, tool, args: True)
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", toolsets=[tools])
