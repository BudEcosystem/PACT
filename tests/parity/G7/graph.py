"""02P G7: a `.transform()` on an edge, a `.label()` to the end, and the end itself."""

from typing import Literal

from pydantic_graph import GraphBuilder, StepContext, TypeExpression

g = GraphBuilder(name="ends", input_type=str, output_type=str)


@g.step
async def check(ctx: StepContext[None, None, str]) -> str:
    return "ok"


@g.step
async def tidy(ctx: StepContext[None, None, str]) -> str:
    return ctx.inputs.strip()


g.add(
    g.edge_from(g.start_node).to(check),
    g.edge_from(check).to(
        g.decision(node_id="outcome")
        .branch(g.match(TypeExpression[Literal["ok"]]).transform(lambda ctx: ctx.inputs.upper()).to(tidy))
        .branch(g.match(TypeExpression[Literal["stuck"]]).label("stop-and-say-so").to(g.end_node))
    ),
    g.edge_from(tidy).to(g.end_node),
)
graph = g.build()
