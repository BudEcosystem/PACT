"""02P G4: a broadcast to fixed branches and their join, a `together`."""

from pydantic_graph import GraphBuilder, StepContext, reduce_list_append

g = GraphBuilder(name="side-by-side", input_type=str, output_type=list[str])


@g.step
async def check_stock(ctx: StepContext[None, None, str]) -> str:
    return "in stock"


@g.step
async def check_price(ctx: StepContext[None, None, str]) -> str:
    return "12 USD"


both = g.join(reduce_list_append, initial_factory=list[str], node_id="both")
g.add(
    g.edge_from(g.start_node).to(check_stock, check_price),
    g.edge_from(check_stock, check_price).to(both),
    g.edge_from(both).to(g.end_node),
)
graph = g.build()
