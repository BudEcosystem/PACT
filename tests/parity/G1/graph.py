"""02P G1: a built graph with typed state, deps, input and output, read as a workflow."""

from dataclasses import dataclass, field

from pydantic_graph import GraphBuilder, StepContext


@dataclass
class Notes:
    seen: list[str] = field(default_factory=list)


g = GraphBuilder(name="intake", state_type=Notes, deps_type=dict, input_type=str, output_type=str)


@g.step
async def read_request(ctx: StepContext[Notes, dict, str]) -> str:
    return ctx.inputs


@g.step
async def file_request(ctx: StepContext[Notes, dict, str]) -> str:
    return f"filed: {ctx.inputs}"


g.add(
    g.edge_from(g.start_node).to(read_request),
    g.edge_from(read_request).to(file_request),
    g.edge_from(file_request).to(g.end_node),
)
graph = g.build()
