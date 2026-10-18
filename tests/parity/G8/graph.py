"""02P G8: a step that streams, read as a `call` stage and named."""

from collections.abc import AsyncIterator

from pydantic_graph import GraphBuilder, StepContext

g = GraphBuilder(name="streams", input_type=str, output_type=str)


@g.stream
async def words(ctx: StepContext[None, None, str]) -> AsyncIterator[str]:
    for word in ctx.inputs.split():
        yield word


@g.step
async def count(ctx: StepContext[None, None, str]) -> str:
    return ctx.inputs


g.add(g.edge_from(g.start_node).to(words), g.edge_from(words).to(count), g.edge_from(count).to(g.end_node))
graph = g.build()
