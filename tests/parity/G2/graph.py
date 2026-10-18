"""02P G2: `@g.step` steps, each a `call` stage whose body is a host action to write."""

from pydantic_graph import GraphBuilder, StepContext

g = GraphBuilder(name="two-steps", input_type=str, output_type=str)


@g.step
async def look_up(ctx: StepContext[None, None, str]) -> str:
    return ctx.inputs


@g.step(node_id="reply")
async def write_reply(ctx: StepContext[None, None, str]) -> str:
    return f"found {ctx.inputs}"


g.add(g.edge_from(g.start_node).to(look_up), g.edge_from(look_up).to(write_reply), g.edge_from(write_reply).to(g.end_node))
graph = g.build()
