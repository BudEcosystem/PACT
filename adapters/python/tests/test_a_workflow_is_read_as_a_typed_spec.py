"""A workflow (02W §2.2) is read off the document `pact show` prints as one
typed spec, every field by one reader, with the workspace lines it is read
under resolved once (P-1): a runtime is handed `WorkflowSpec`, never the
document.

The tree is `tests/trees/a-workflow-of-every-shape/`, which writes every stage
a workflow has and loads clean under `pact check --deny-warnings`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import Moment, WorkflowSpec  # noqa: E402
from trees import REPO, shown  # noqa: E402

TREE = REPO / "tests/trees/a-workflow-of-every-shape"


@pytest.fixture(scope="module")
def flow() -> WorkflowSpec:
    return WorkflowSpec.from_workflow(shown(TREE), "invoices")


def test_every_workflow_of_the_tree_is_read_by_name() -> None:
    doc = shown(TREE)
    assert [WorkflowSpec.from_workflow(doc, n).name for n in sorted(doc["workflows"])] == ["invoices", "recheck"]


def test_the_workflow_lines_are_read_as_written(flow: WorkflowSpec) -> None:
    assert flow.description.startswith("Goes through an email's attachments")
    assert flow.starts_at == "sort"
    assert flow.accepts == {"attachments": "text", "received-on": "text"}
    assert flow.answers_with == {"posted": "yes or no"}
    assert flow.kept_for == Moment(at="input.received-on", after="7 days")
    assert flow.hides == {"input.attachments": ("logs",)}
    assert flow.published_as == ("tool",)
    assert flow.undone_by == "ledger/unpost"
    assert set(flow.questions) == {"go-ahead"}
    assert flow.base is False


def test_the_workspace_lines_a_workflow_is_read_under_come_with_it(flow: WorkflowSpec) -> None:
    assert flow.time_zone == "America/Chicago"
    assert flow.shapes == {"invoice-line": {"sku": "text", "quantity": "whole number"}}
    assert set(flow.workspace_remembers.declared) == {"paused"}
    assert flow.workspace_remembers.declared["paused"].kept_for == "30 days"
    # Its own `release:` would replace the workspace's whole; it writes none.
    assert flow.release_asks == "may-we-publish"
    (owned,) = flow.owners
    assert (owned.path, owned.owned_by, owned.locked) == ("workflows/invoices/steps/pay", "finance", "here")
    assert owned.locked_until == Moment(at="input.received-on", after="90 days")


def test_each_stage_is_read_with_the_lines_its_does_reads(flow: WorkflowSpec) -> None:
    assert [s.name for s in flow.steps] == [
        "sort", "what-is-it", "approve", "each-attachment", "check-twice", "both", "reply",
    ]
    sort = flow.stage_named("sort")
    assert (sort.does, sort.call, sort.says, sort.then) == ("call", "sorter", "Is this an invoice?", {"answered": "what-is-it"})
    assert flow.stage_named("what-is-it").chooses_between == {"invoice": "approve", "other": "reply"}
    approve = flow.stage_named("approve")
    assert approve.asks == "go-ahead" and approve.then["declined"] == "reply"
    assert approve.nobody_answered == "stop-and-say-so"
    each = flow.stage_named("each-attachment")
    assert (each.over, each.identified_by, each.ordered_by) == ("input.attachments", ("content-hash",), "total")
    assert each.combines_by == {"posted": "vote", "total": "top 1 highest by total"}
    assert each.teamwork == {"waits-for": "everyone"}
    assert each.items_at_most == 20 and each.starts_at == "read"
    read, pay = each.steps
    assert read.bind == {"invoice": "item.content-hash"} and read.then == {"answered": "pay"}
    assert (pay.call, pay.at_most, pay.undone_by) == ("ledger/post", 3, "ledger/unpost")
    again = flow.stage_named("check-twice")
    assert (again.does, again.at_most, again.starts_at) == ("repeat", 2, "recheck")
    (recheck,) = again.steps
    assert (recheck.call, recheck.waits_for_result, recheck.version) == ("recheck", False, "latest")
    both = flow.stage_named("both")
    assert [s.name for s in both.steps] == ["left", "right"] and both.combines_by == {"posted": "keep-all"}
    assert flow.stage_named("reply").does == "answer"


def test_a_stage_left_unwritten_waits_for_its_result_and_stops_on_silence(flow: WorkflowSpec) -> None:
    sort = flow.stage_named("sort")
    assert sort.waits_for_result is True
    assert sort.nobody_answered == "stop-and-say-so"
    assert sort.checks_at_most == 2 and sort.items_at_most is None


def test_a_name_that_is_not_a_workflow_names_what_is() -> None:
    with pytest.raises(KeyError, match="this workspace has: \\['invoices', 'recheck'\\]"):
        WorkflowSpec.from_workflow(shown(TREE), "invoice")


def test_a_moment_written_as_a_length_of_time_counts_after_the_stage_starts() -> None:
    assert Moment.from_written("48h") == Moment(after="48h")
    assert Moment.from_written({"at": "input.x", "before": "24h", "counted-in": "business-days"}) == Moment(
        at="input.x", before="24h", counted_in="business-days"
    )
    assert Moment.from_written(None) is None
