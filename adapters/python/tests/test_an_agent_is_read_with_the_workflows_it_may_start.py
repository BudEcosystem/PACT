"""An agent is read with the workflows its `uses:` line names (N2).

An agent's `uses:` may name a workflow whose `published-as:` lists `tool`
(`pact check` refuses any other: `loader/a-workflow-nobody-published-as-a-tool`).
A runtime handed `AgentSpec` must know which names are workflows, because a
workflow is neither a tool file, a skill, a set of documents nor a program, and
read as any of them it would reach no run. They are carried as names, sorted
like `tools`; the workflow itself is read by `WorkflowSpec.from_workflow`.

The tree is `tests/trees/an-agent-that-uses-a-workflow/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import AgentSpec, WorkflowSpec  # noqa: E402
from pact_adapters.resolve import strategies_of  # noqa: E402
from trees import REPO, shown  # noqa: E402

TREE = REPO / "tests/trees/an-agent-that-uses-a-workflow"


def test_a_workflow_on_the_uses_line_is_one_the_agent_may_start() -> None:
    document = shown(TREE)
    spec = AgentSpec.from_document(document, "desk", TREE)
    assert spec.workflows == ("order-status",)
    assert spec.tools == ()  # it is not read as a tool file, nor as anything else
    assert spec.skills == () and spec.knowledge == () and spec.programs == ()
    flow = WorkflowSpec.from_workflow(document, "order-status")
    assert flow.published_as == ("tool",)
    assert dict(flow.accepts) == {"order-number": "text"}


def test_an_agent_that_names_no_workflow_starts_none() -> None:
    document = shown(TREE)
    document["agents"]["desk"]["uses"] = []
    assert AgentSpec.from_document(document, "desk", TREE).workflows == ()


def test_a_variant_narrows_the_workflows_as_it_narrows_the_tools() -> None:
    """`variant.may-use:` draws from `workflows` too, so a variant that names none
    has none, and one that names it keeps it."""
    document = shown(TREE)
    document["agents"]["desk"]["variants"] = {
        "no-flows": {"may-use": []},
        "the-flow": {"may-use": ["order-status"]},
    }
    spec = AgentSpec.from_document(document, "desk", TREE)
    ways = strategies_of(spec)
    assert ways["no-flows"](spec).workflows == ()
    assert ways["the-flow"](spec).workflows == ("order-status",)
