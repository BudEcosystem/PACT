"""`examples/kernel/work-queue`, run as shipped (docs/98 §6).

The one kernel workspace with no agent: a workflow over a queue tool. The golden
set runs agents, so this file is where the tree is run rather than only loaded.
It is read through `pact show`, the door every adapter reads through, and run on
the reference workflow runtime with a fake queue: a task that turns up while the
queue is being worked is taken (`keeps-taking: yes`), and the watcher started
without waiting is stopped once the work is done (`does: stop`).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TREE = REPO / "examples" / "kernel" / "work-queue"
PACT_BIN = REPO / "target" / "debug" / "pact"


def test_the_shipped_queue_takes_a_late_task_and_stops_its_watcher() -> None:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    doc = json.loads(
        subprocess.run([str(PACT_BIN), "show", str(TREE)], capture_output=True, text=True, check=True).stdout
    )
    spec = WorkflowSpec.from_workflow(doc, "work")
    tasks: list[dict[str, Any]] = [{"id": "t1"}, {"id": "t2"}]
    done: list[str] = []
    watcher: dict[str, bool] = {"cancelled": False}

    async def tool(tool: str, action: str, inputs: dict[str, Any]) -> dict[str, Any]:
        assert tool == "queue", tool
        if action == "watch":
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                watcher["cancelled"] = True
                raise
            return {}
        done.append(inputs["task"])
        if inputs["task"] == "t1":
            tasks.append({"id": "t3"})  # arrives while the queue is being worked
        return {}

    out = asyncio.run(
        run_workflow(spec, {"queue": "q", "tasks": tasks}, Callers(tool=tool), document=doc)
    )
    assert out.halted == "final", out
    assert done == ["t1", "t2", "t3"], done
    assert watcher["cancelled"], "the watcher started without waiting was never stopped"
