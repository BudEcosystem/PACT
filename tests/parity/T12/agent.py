"""02P T12: tools behind wrappers are read: prefixes, renames, filters and approval, each named where it changes something."""

from pydantic_ai import Agent
from pydantic_ai.toolsets import ApprovalRequiredToolset, CombinedToolset, FilteredToolset, FunctionToolset, PrefixedToolset, RenamedToolset


def lookup(order_number: str) -> str:
    """Look an order up."""
    return "shipped"


def refund(order_number: str) -> str:
    """Refund an order."""
    return "refunded"


def note(text: str) -> str:
    """Write a note."""
    return "noted"


crm = PrefixedToolset(FunctionToolset([lookup, refund]), prefix="crm")
kept = FilteredToolset(RenamedToolset(FunctionToolset([note]), name_map={"memo": "note"}), filter_func=lambda ctx, tool: True)
agent = Agent(name="desk", description="Answers order questions.", instructions="Answer briefly.", toolsets=[CombinedToolset([ApprovalRequiredToolset(crm), kept])])
