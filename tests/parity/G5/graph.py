"""02P G5: a map over a list and its join, an `each`."""

from pydantic_graph import GraphBuilder, StepContext, reduce_list_append

g = GraphBuilder(name="every-line", input_type=list[str], output_type=list[str])


@g.step
async def lines(ctx: StepContext[None, None, list[str]]) -> list[str]:
    return ctx.inputs


@g.step
async def price_line(ctx: StepContext[None, None, str]) -> str:
    return f"{ctx.inputs}: 1 USD"


priced = g.join(reduce_list_append, initial_factory=list[str], node_id="every-line")
g.add(
    g.edge_from(g.start_node).to(lines),
    g.edge_from(lines).map().to(price_line),
    g.edge_from(price_line).to(priced),
    g.edge_from(priced).to(g.end_node),
)
graph = g.build()
