"""02P G9: a cycle through a decision, a `repeat`; its bound is the decision's note."""

from typing import Literal

from pydantic_graph import GraphBuilder, StepContext, TypeExpression

g = GraphBuilder(name="until-it-fits", input_type=str, output_type=str)


@g.step
async def draft(ctx: StepContext[None, None, str]) -> str:
    return ctx.inputs


@g.step
async def check_length(ctx: StepContext[None, None, str]) -> str:
    return "fits" if len(ctx.inputs) < 80 else "again"


@g.step
async def send(ctx: StepContext[None, None, str]) -> str:
    return "sent"


g.add(
    g.edge_from(g.start_node).to(draft),
    g.edge_from(draft).to(check_length),
    g.edge_from(check_length).to(
        g.decision(node_id="round", note="at-most: 3")
        .branch(g.match(TypeExpression[Literal["again"]]).to(draft))
        .branch(g.match(TypeExpression[Literal["fits"]]).to(send))
    ),
    g.edge_from(send).to(g.end_node),
)
graph = g.build()
