"""02P G6: join reducers: a sum, the first value, and the author's own."""

from pydantic_graph import GraphBuilder, ReduceFirstValue, StepContext, reduce_sum

g = GraphBuilder(name="reducers", input_type=list[int], output_type=int)


@g.step
async def amounts(ctx: StepContext[None, None, list[int]]) -> list[int]:
    return ctx.inputs


@g.step
async def weigh(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs


@g.step
async def quotes(ctx: StepContext[None, None, int]) -> list[int]:
    return [ctx.inputs, ctx.inputs + 1]


@g.step
async def quote(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs


@g.step
async def batches(ctx: StepContext[None, None, int]) -> list[int]:
    return [ctx.inputs]


@g.step
async def score(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs


def keep_the_highest(current: int, inputs: int) -> int:
    return max(current, inputs)


total = g.join(reduce_sum, initial=0, node_id="total")
first = g.join(ReduceFirstValue[int](), initial=0, node_id="first-quote")
highest = g.join(keep_the_highest, initial=0, node_id="highest")
g.add(
    g.edge_from(g.start_node).to(amounts),
    g.edge_from(amounts).map().to(weigh),
    g.edge_from(weigh).to(total),
    g.edge_from(total).to(quotes),
    g.edge_from(quotes).map().to(quote),
    g.edge_from(quote).to(first),
    g.edge_from(first).to(batches),
    g.edge_from(batches).map().to(score),
    g.edge_from(score).to(highest),
    g.edge_from(highest).to(g.end_node),
)
graph = g.build()
