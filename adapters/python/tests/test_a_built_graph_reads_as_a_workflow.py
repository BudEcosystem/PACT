"""A built pydantic-graph `Graph` read as a PACT workflow, and a workflow lowered to one (02P G1-G9).

`pydantic_graph_reading.workflow_of` reads a graph's structure through its public
attributes and runs no step; `pydantic_graph_lowering.graph_of` builds the 03 §B.2
kernel of a workflow. Held here:

* **G1's test, export then import is the identity**, on #16's and #48's workflows
  (`tests/trees/workflows-16-trial-booking`, `workflows-48-invoices`), and on the tree
  that has a workflow of every shape and #60's (waits that hear events);
* **no step runs** while a graph is read, and a lowered graph's steps are host actions
  still to write: run, each says so;
* **a graph an author built** comes in as a tree `pact check` loads once its host actions
  are bound (`connect`), its decision a rules-rung `decide` reading what the step before
  it answered;
* **nothing is dropped in silence**: one test breaks the reader to show the count fails.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Literal

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.openapi import write_into  # noqa: E402
from pact_adapters.pydantic_ai_registry import registry  # noqa: E402
from pact_adapters.pydantic_graph_lowering import graph_of, structure  # noqa: E402
from pact_adapters.pydantic_graph_reading import workflow_of  # noqa: E402
from trees import pact, shown, write  # noqa: E402

pydantic_graph = pytest.importorskip("pydantic_graph")

from pydantic_graph import GraphBuilder, StepContext, TypeExpression  # noqa: E402

TREES = Path(__file__).resolve().parents[3] / "tests" / "trees"
WORKFLOWS = [
    (tree, name)
    for tree, names in (
        ("workflows-16-trial-booking", ("trial-booking", "parent-contact")),
        ("workflows-48-invoices", ("ap-inbox", "one-invoice")),
        ("a-workflow-of-every-shape", ("invoices",)),
        ("workflows-60-interconnection", ("interconnection",)),
    )
    for name in names
]


@pytest.mark.parametrize(("tree", "name"), WORKFLOWS, ids=[f"{t}:{n}" for t, n in WORKFLOWS])
def test_a_workflow_lowered_to_a_graph_reads_back_as_itself(tree: str, name: str) -> None:
    """G1: the workflow as a built graph, read back, has the same structure: every stage's name,
    what it does, where each of its outcomes goes, and the stages inside each fan and repeat."""
    document = shown(TREES / tree)
    graph, report = graph_of(document, name)
    assert report.silent_losses == (), report.silent_losses
    imported = workflow_of(graph)
    assert imported.report.silent_drops == () and imported.report.unmapped == {}, imported.report.in_words()
    back = yaml.safe_load(imported.files[f"workflows/{name}.yaml"])
    assert structure(back) == structure(document["workflows"][name])


def test_the_lowered_graph_names_every_body_and_runs_none() -> None:
    """What a graph's step does is code: the export names each stage's body as a host action to
    write, and running a lowered step says so rather than inventing one."""
    document = shown(TREES / "workflows-16-trial-booking")
    graph, report = graph_of(document, "trial-booking")
    assert "`call:`" in report.not_carried["steps.tidy"] and "host action" in report.not_carried["steps.tidy"]
    assert {"accepts", "description", "questions"} <= set(report.not_carried)
    with pytest.raises(NotImplementedError, match="stage 'tidy': write the host action"):
        asyncio.run(graph.run(inputs={}))


def _triage(ran: list[str]) -> object:
    g = GraphBuilder(name="triage_tickets", input_type=str, output_type=str)

    @g.step
    async def classify(ctx: StepContext[None, None, str]) -> str:
        ran.append("classify")
        return "bug"

    @g.step
    async def file_bug(ctx: StepContext[None, None, str]) -> str:
        ran.append("file_bug")
        return "filed"

    @g.step
    async def answer_question(ctx: StepContext[None, None, str]) -> str:
        ran.append("answer_question")
        return "answered"

    g.add(
        g.edge_from(g.start_node).to(classify),
        g.edge_from(classify).to(
            g.decision(node_id="kind-of-ticket")
            .branch(g.match(TypeExpression[Literal["bug"]]).to(file_bug))
            .branch(g.match(TypeExpression[Literal["question"]]).to(answer_question))
        ),
        g.edge_from(file_bug, answer_question).to(g.end_node),
    )
    return g.build()


def test_an_authors_graph_comes_in_as_a_tree_that_loads(tmp_path: Path) -> None:
    """A graph built in Python, read without running a step, written with its host actions bound
    to a server: `pact check` loads the tree, and the decide reads the classifier's `kind`."""
    ran: list[str] = []
    imported = workflow_of(_triage(ran), connect="ticket-steps")
    assert ran == [], f"reading the graph ran {ran}"
    root = write(tmp_path / "tree", {"workspace.yaml": "name: imported\nallow-egress: []\n"})
    written = write_into(root, imported)
    assert sorted(written) == ["resources/ticket-steps.yaml", "tools/triage-tickets.yaml", "workflows/triage-tickets.yaml"]
    out = pact("check", str(root))
    assert out.returncode == 0, out.stdout + out.stderr
    loaded = shown(root)
    stage = loaded["workflows"]["triage-tickets"]["steps"]["kind-of-ticket"]
    assert stage["chooses-between"] == {"bug": "file-bug", "question": "answer-question"}
    assert stage["by"][0]["rules"][0]["when"] == [{"value": "steps.classify.kind", "is": "bug"}]
    assert loaded["tools"]["triage-tickets"]["actions"]["classify"]["answers-with"] == {"kind": "one of bug, question"}


def test_a_cycle_with_no_bound_asks_for_one() -> None:
    """An unbounded cycle is refused by PACT, so a cycle whose decision has no `at-most:` note
    is a repeat whose bound is still to write, never a number the import picked."""
    g = GraphBuilder(name="loop")

    @g.step
    async def draft(ctx: StepContext[None, None, None]) -> str:
        return "again"

    g.add(
        g.edge_from(g.start_node).to(draft),
        g.edge_from(draft).to(
            g.decision(node_id="round")
            .branch(g.match(TypeExpression[Literal["again"]]).to(draft))
            .branch(g.match(TypeExpression[Literal["done"]]).to(g.end_node))
        ),
    )
    imported = workflow_of(g.build())
    stage = yaml.safe_load(imported.files["workflows/loop.yaml"])["steps"]["round"]
    assert stage["does"] == "repeat" and "at-most" not in stage
    assert any("`at-most:` on round" in line for line in imported.report.still_to_write)


def test_the_graph_rows_of_the_registry_cross() -> None:
    """WP-39 reads a built graph, so the `graph.` door's rows are no longer losses for want of
    workflows: only a v1 node and a streaming step stay losses (G8)."""
    rows = registry().through("graph")
    assert {n for n, r in rows.items() if r.outcome == "loss"} == {"match_node", "node", "stream"}


def test_a_node_the_reader_skips_is_a_silent_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: a reader that forgets a node's bucket is caught by the computed count."""
    from pact_adapters import pydantic_graph_reading

    real = pydantic_graph_reading._Reading._stage

    def forgetful(self, nid, nodes, fan):  # type: ignore[no-untyped-def]
        out = real(self, nid, nodes, fan)
        self.report.mapped.pop(f"nodes.{nid}", None)
        return out

    monkeypatch.setattr(pydantic_graph_reading._Reading, "_stage", forgetful)
    assert "nodes.classify" in workflow_of(_triage([])).report.silent_drops


def test_two_nodes_that_would_be_one_stage_are_refused() -> None:
    """`file_bug` and `file-bug` are one PACT name: the read refuses rather than keep one."""
    g = GraphBuilder(name="twins")

    async def body(ctx: StepContext[None, None, None]) -> None:
        return None

    first, second = g.step(body, node_id="file_bug"), g.step(body, node_id="file-bug")
    g.add(g.edge_from(g.start_node).to(first), g.edge_from(first).to(second), g.edge_from(second).to(g.end_node))
    with pytest.raises(ValueError, match="both the stage 'file-bug'"):
        workflow_of(g.build())


def test_two_branches_by_one_type_are_two_routes(tmp_path: Path) -> None:
    """pydantic-graph's guard pattern, `match(str, matches=...)` then `match(str)`: both branches
    are `str`, and each keeps its route (`str`, `str-2`), the second named; the tree loads."""
    g = GraphBuilder(name="route", input_type=str)

    @g.step
    async def classify(ctx: StepContext[None, None, str]) -> str:
        return ctx.inputs

    @g.step
    async def urgent(ctx: StepContext[None, None, str]) -> None:
        return None

    @g.step
    async def normal(ctx: StepContext[None, None, str]) -> None:
        return None

    g.add(
        g.edge_from(g.start_node).to(classify),
        g.edge_from(classify).to(
            g.decision(node_id="which")
            .branch(g.match(str, matches=lambda t: t.startswith("urgent")).to(urgent))
            .branch(g.match(str).to(normal))
        ),
        g.edge_from(urgent, normal).to(g.end_node),
    )
    imported = workflow_of(g.build(), connect="steps")
    stage = yaml.safe_load(imported.files["workflows/route.yaml"])["steps"]["which"]
    assert stage["chooses-between"] == {"str": "urgent", "str-2": "normal"}
    assert {"nodes.which.branches.str.matches", "nodes.which.branches.str-2"} <= set(imported.report.not_portable)
    assert imported.report.silent_drops == ()
    root = write(tmp_path / "tree", {"workspace.yaml": "name: imported\nallow-egress: []\n"})
    write_into(root, imported)
    out = pact("check", str(root))
    assert out.returncode == 0, out.stdout + out.stderr


def test_a_step_inside_a_fan_named_as_one_outside_is_its_own_action() -> None:
    """Inside ids are `<outer>/<name>`, so `check` and `fan/check` are two stages of one name in
    two blocks: each calls its own host action, never one merged."""
    from pydantic_graph import reduce_list_append

    g = GraphBuilder(name="wf", input_type=list)

    async def body(ctx: StepContext[None, None, object]) -> list:
        return []

    top, inner = g.step(body, node_id="check"), g.step(body, node_id="fan/check")
    fan = g.join(reduce_list_append, initial_factory=list, node_id="fan")
    g.add(
        g.edge_from(g.start_node).to(top),
        g.edge_from(top).map().to(inner),
        g.edge_from(inner).to(fan),
        g.edge_from(fan).to(g.end_node),
    )
    imported = workflow_of(g.build())
    steps = yaml.safe_load(imported.files["workflows/wf.yaml"])["steps"]
    assert steps["check"]["call"] == "wf/check"
    assert steps["fan"]["steps"]["check"]["call"] == "wf/fan-check"
    assert set(yaml.safe_load(imported.files["tools/wf.yaml"])["actions"]) == {"check", "fan-check"}


def test_a_drawing_label_to_the_end_is_named_and_the_way_is_done() -> None:
    """`.label('all finished')` is how a drawing names an edge; an outcome names a stage or
    `done`, so the way is `done` and the label is named, never written where a stage goes."""
    g = GraphBuilder(name="lab", input_type=str)

    @g.step
    async def greet(ctx: StepContext[None, None, str]) -> str:
        return ctx.inputs

    g.add(g.edge_from(g.start_node).to(greet), g.edge_from(greet).label("all finished").to(g.end_node))
    imported = workflow_of(g.build())
    assert "then" not in yaml.safe_load(imported.files["workflows/lab.yaml"])["steps"]["greet"]
    assert "edges.greet.answered.label" in imported.report.not_portable
