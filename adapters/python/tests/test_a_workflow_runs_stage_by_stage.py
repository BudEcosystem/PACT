"""The reference workflow runtime (docs/98 WP-9): a workflow RUNS.

Until `workflow_runtime.py`, nothing in PACT executed a workflow's stages. Each
test here runs a shipped workflow tree end to end with fake callers — the
host's side — and holds what came back and in what order the stages ran.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def go(tree: str, name: str, inputs: dict[str, Any], callers: Callers, **kw):
    doc = shown(REPO / tree)
    spec = WorkflowSpec.from_workflow(doc, name)
    return asyncio.run(run_workflow(spec, inputs, callers, document=doc, **kw)), doc


class Ledger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, tool: str, action: str, inputs: dict) -> dict:
        self.calls.append((tool, action, inputs))
        if action == "read-invoice":
            return {"total": "10 USD", "vendor": "acme"}
        if action == "post":
            return {"posted": True}
        return {}


ATTACHMENTS = [{"content-hash": "a"}, {"content-hash": "b"}, {"content-hash": "a"}]


def test_every_stage_kind_runs_in_order() -> None:
    ledger = Ledger()
    callers = Callers(
        tool=ledger,
        agent=lambda name, inputs: {"kind": "invoice"},
        person=lambda question, shown: {"go-ahead": True},
    )
    out, _ = go(
        "tests/trees/a-workflow-of-every-shape",
        "invoices",
        {"attachments": ATTACHMENTS, "received-on": "2026-11-10"},
        callers,
    )
    assert out.halted == "final", out.said
    stages = [t.split("/")[0] for t in out.trace]
    assert stages[:4] == ["sort", "what-is-it", "approve", "each-attachment"], out.trace
    assert stages[-1] == "reply", out.trace
    # `identified-by: [content-hash]`: the repeated attachment is one item.
    posted = [c for c in ledger.calls if c[1] == "post"]
    assert [c[2]["invoice"] for c in posted] == ["a", "b"], ledger.calls
    # `posted: vote` across the items.
    assert out.steps["each-attachment"]["posted"] is True
    # `pay` has `undone-by:`, so both posts are recorded with their way back.
    assert [w.undo for w in out.written] == ["ledger/unpost", "ledger/unpost"]
    # `waits-for-result: no`: the recheck runs detached and leaves a reference.
    assert "run" in out.steps["check-twice"] or out.detached


def test_a_decision_by_rules_takes_its_route() -> None:
    ledger = Ledger()
    callers = Callers(
        tool=ledger,
        agent=lambda name, inputs: {"kind": "other"},
        person=lambda question, shown: {"go-ahead": True},
    )
    out, _ = go(
        "tests/trees/a-workflow-of-every-shape",
        "invoices",
        {"attachments": ATTACHMENTS, "received-on": "2026-11-10"},
        callers,
    )
    assert out.halted == "final", out.said
    assert out.trace == ["sort", "what-is-it", "reply"], out.trace
    assert ledger.calls == []


def test_a_no_from_the_person_goes_where_declined_says() -> None:
    callers = Callers(
        tool=Ledger(),
        agent=lambda name, inputs: {"kind": "invoice"},
        person=lambda question, shown: {"go-ahead": False},
    )
    out, _ = go(
        "tests/trees/a-workflow-of-every-shape",
        "invoices",
        {"attachments": ATTACHMENTS, "received-on": "x"},
        callers,
    )
    assert out.trace == ["sort", "what-is-it", "approve", "reply"], out.trace


def test_with_nobody_to_ask_the_run_parks_at_the_question() -> None:
    callers = Callers(tool=Ledger(), agent=lambda name, inputs: {"kind": "invoice"})
    out, _ = go(
        "tests/trees/a-workflow-of-every-shape",
        "invoices",
        {"attachments": ATTACHMENTS, "received-on": "x"},
        callers,
    )
    assert out.halted == "parked", out
    assert (out.parked_at, out.question) == ("approve", "go-ahead")


def test_a_retry_then_a_backup_with_the_same_inputs() -> None:
    asked: list[tuple[str, dict]] = []

    def agent(name: str, inputs: dict) -> dict:
        asked.append((name, dict(inputs)))
        if name == "quick-reader":
            raise RuntimeError("the cheap model timed out")
        return {"answer": "From the notes: yes.", "confidence": "high"}

    out, _ = go(
        "examples/kernel/fallback",
        "answer",
        {"question": "Does it float?", "notes": "It floats."},
        Callers(agent=agent),
    )
    assert out.halted == "final", out.said
    assert [a[0] for a in asked] == ["quick-reader", "quick-reader", "careful-reader"]
    assert asked[2][1] == {"question": "Does it float?", "notes": "It floats."}
    assert out.answer == {"answer": "From the notes: yes."}


def test_with_no_plan_a_failure_stops_and_says_so() -> None:
    def agent(name: str, inputs: dict) -> dict:
        raise RuntimeError("down")

    out, _ = go(
        "examples/kernel/phases",
        "deliver",
        {"brief": "b"},
        Callers(agent=agent),
    )
    assert out.halted == "stopped" and "down" in out.said, out


def test_rounds_remember_and_stop_when_the_plan_is_empty() -> None:
    rounds = {"n": 0}
    readers: list[str] = []
    saved: list[dict] = []

    def agent(name: str, inputs: dict) -> dict:
        if name == "redactor":
            return {"file": "redacted.pdf"}
        if name == "read-supervisor":
            rounds["n"] += 1
            tasks = (
                [{"reader": "academic-context", "question": "rigour?"},
                 {"reader": "activities", "question": "depth?"}]
                if rounds["n"] == 1 else []
            )
            return {"tasks": tasks}
        if name == "card-writer":
            return {"card": f"card from {len(inputs['notes'])} notes"}
        readers.append(name)
        return {"notes": [f"{name} p.3"]}

    def tool(tool: str, action: str, inputs: dict) -> dict:
        if action == "save-draft-reader-form":
            saved.append(inputs)
        return {"materials": "m.pdf"}

    out, _ = go(
        "tests/trees/workflows-79-supervisor",
        "first-read",
        {"application-id": "A-1", "applied-for-aid": False},
        Callers(tool=tool, agent=agent),
    )
    assert out.halted == "final", out.said
    assert rounds["n"] == 2, "the second plan was empty, and `until:` ended the repeat"
    assert sorted(readers) == ["academic-context", "activities"]
    # Each specialist answers a LIST of notes, and `keep-all` keeps each answer
    # whole: one list per reader, across the rounds.
    assert sorted(out.steps["read"]["notes"]) == [["academic-context p.3"], ["activities p.3"]]
    assert saved and saved[0]["card"] == "card from 2 notes", saved


def test_a_workspace_switch_read_from_memory_routes_the_run() -> None:
    out, _ = go(
        "tests/trees/workflows-79-supervisor",
        "first-read",
        {"application-id": "A-1", "applied-for-aid": False},
        Callers(),
        remembered={"ai-reading-paused": True},
    )
    assert out.halted == "final" and out.trace == ["paused"], out


def test_a_call_written_as_a_binding_may_only_reach_what_may_call_lists() -> None:
    def agent(name: str, inputs: dict) -> dict:
        if name == "read-supervisor":
            return {"tasks": [{"reader": "redactor", "question": "?"}]}
        return {"file": "f", "notes": []}

    out, _ = go(
        "tests/trees/workflows-79-supervisor",
        "first-read",
        {"application-id": "A-1", "applied-for-aid": False},
        Callers(tool=lambda t, a, i: {"materials": "m"}, agent=agent),
    )
    # `if-someone-fails: carry-on`: the refused item is kept, marked failed,
    # and the run goes on — the refusal itself is the item's failure.
    items = out.steps["specialists"]["items"]
    assert any("may-call" in str(i.get("failed", "")) for i in items), items
    assert out.halted == "final", out.said
