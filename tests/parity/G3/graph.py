"""02P G3: a decision: one label per `Literal` branch, a branch by type, and a `matches=` function."""

from typing import Literal

from pydantic_graph import GraphBuilder, StepContext, TypeExpression

g = GraphBuilder(name="route", input_type=str, output_type=str)


@g.step
async def classify(ctx: StepContext[None, None, str]) -> str:
    return "refund" if "money" in ctx.inputs else "other"


@g.step
async def refund(ctx: StepContext[None, None, str]) -> str:
    return "refunded"


@g.step
async def urgent(ctx: StepContext[None, None, str]) -> str:
    return "escalated"


@g.step
async def answer(ctx: StepContext[None, None, object]) -> str:
    return "answered"


g.add(
    g.edge_from(g.start_node).to(classify),
    g.edge_from(classify).to(
        g.decision(node_id="which")
        .branch(g.match(TypeExpression[Literal["refund"]]).to(refund))
        .branch(g.match(str, matches=lambda text: text.startswith("urgent")).to(urgent))
        .branch(g.match(object).to(answer))
    ),
    g.edge_from(refund, urgent, answer).to(g.end_node),
)
graph = g.build()
