"""docs/98 WP-10: `forks:`, `does: stop`, and `keeps-taking:`.

* `forks: yes` on a loop stage makes each attempt start from the conversation
  as it stood when the stage began — `answer-more-than-once`'s attempts become
  independent samples, which its own description says they are not without it.
* `does: stop` cancels a run a `call` started without waiting for it.
* `keeps-taking: yes` on an `each` takes items added while it runs.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec, WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402


class Counting:
    """A transport that answers by call number and keeps what it was shown."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.seen: list[list[dict[str, Any]]] = []

    async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
        self.seen.append([dict(m) for m in history])
        return self.answers[min(len(self.seen) - 1, len(self.answers) - 1)], []

    def __getattr__(self, name: str) -> Any:  # anything else a transport may be asked
        if name == "unenforced":
            return lambda: ()
        raise AttributeError(name)


def _doc(forks: bool) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "does": "think",
        "at-most": 3,
        "then": {"used-a-tool": "attempt", "answered": "attempt", "too-many-times": "settle"},
    }
    if forks:
        attempt["forks"] = "yes"
    return {
        "agents": {"a": {"description": "d", "instructions": "Answer.", "loop": "votes"}},
        "loops": {
            "votes": {
                "starts-at": "attempt",
                "steps": {
                    "attempt": attempt,
                    "settle": {"does": "answer", "then": {"answered": "done"}},
                },
            }
        },
    }


def _said(history: list[dict[str, Any]]) -> str:
    return " ".join(str(m.get("content")) for m in history)


def test_forked_attempts_never_read_each_other_and_the_next_stage_reads_them_all() -> None:
    t = Counting(["ANSWER-ONE", "ANSWER-TWO", "ANSWER-THREE", "settled"])
    spec = AgentSpec.from_document(_doc(forks=True), "a")
    out = asyncio.run(run(spec, t, "what is 2+2?"))
    assert out.halted == "final", (out.halted, out.output)
    assert len(t.seen) == 4, [_said(h) for h in t.seen]
    assert "ANSWER-ONE" not in _said(t.seen[1])
    assert "ANSWER-ONE" not in _said(t.seen[2]) and "ANSWER-TWO" not in _said(t.seen[2])
    settle = _said(t.seen[3])
    assert "independent attempts at 'attempt'" in settle, settle
    for a in ("ANSWER-ONE", "ANSWER-TWO", "ANSWER-THREE"):
        assert a in settle, settle


def test_without_forks_the_attempts_share_a_conversation() -> None:
    t = Counting(["ANSWER-ONE", "ANSWER-TWO", "ANSWER-THREE", "settled"])
    spec = AgentSpec.from_document(_doc(forks=False), "a")
    asyncio.run(run(spec, t, "what is 2+2?"))
    assert "ANSWER-ONE" in _said(t.seen[1]), "this is the line `forks:` exists to change"


def _flow(steps: dict[str, Any], starts_at: str) -> WorkflowSpec:
    doc = {"workflows": {"w": {"description": "d", "starts-at": starts_at, "steps": steps}}}
    return WorkflowSpec.from_workflow(doc, "w")


def test_a_stop_stage_cancels_what_a_call_started_without_waiting() -> None:
    started: list[str] = []
    finished: list[str] = []

    async def tool(tool: str, action: str, inputs: dict) -> dict:
        started.append(action)
        await asyncio.sleep(5)
        finished.append(action)
        return {}

    spec = _flow(
        {
            "watch": {
                "does": "call",
                "call": "monitor/watch",
                "waits-for-result": "no",
                "then": {"answered": "halt"},
            },
            "halt": {"does": "stop", "stops": "steps.watch.run", "then": {"answered": "reply"}},
            "reply": {"does": "answer"},
        },
        "watch",
    )

    async def go():
        out = await run_workflow(spec, {}, Callers(tool=tool))
        await asyncio.sleep(0)
        return out

    out = asyncio.run(go())
    assert out.halted == "final", out.said
    assert out.steps["halt"] == {"stopped": True}
    assert finished == [], "the detached run was stopped before it finished"
    assert out.detached == {}


def test_an_each_that_keeps_taking_takes_what_arrives_while_it_runs() -> None:
    tasks = [{"id": "t1"}]
    done: list[str] = []

    def tool(tool: str, action: str, inputs: dict) -> dict:
        done.append(inputs["task"])
        if inputs["task"] == "t1":  # planning the first task finds two more
            tasks.extend([{"id": "t2"}, {"id": "t3"}])
        return {"result": f"did {inputs['task']}"}

    spec = _flow(
        {
            "work": {
                "does": "each",
                "over": "input.tasks",
                "keeps-taking": "yes",
                "identified-by": ["id"],
                "limits": {"items-at-most": 10, "when-it-runs-out": "stop-and-say-so"},
                "starts-at": "do",
                "steps": {
                    "do": {"does": "call", "call": "q/run", "bind": {"task": "item.id"}}
                },
                "then": {"answered": "reply"},
            },
            "reply": {"does": "answer", "bind": {"results": "steps.work.result"}},
        },
        "work",
    )
    out = asyncio.run(run_workflow(spec, {"tasks": tasks}, Callers(tool=tool)))
    assert out.halted == "final", out.said
    assert sorted(done) == ["t1", "t2", "t3"], done


def test_a_growing_each_still_stops_at_its_ceiling() -> None:
    tasks = [{"id": "t0"}]

    def tool(tool: str, action: str, inputs: dict) -> dict:
        n = int(inputs["task"][1:])
        tasks.append({"id": f"t{n + 1}"})  # every task finds another, for ever
        return {}

    spec = _flow(
        {
            "work": {
                "does": "each",
                "over": "input.tasks",
                "keeps-taking": "yes",
                "identified-by": ["id"],
                "limits": {"items-at-most": 5, "when-it-runs-out": "stop-and-say-so"},
                "starts-at": "do",
                "steps": {"do": {"does": "call", "call": "q/run", "bind": {"task": "item.id"}}},
            }
        },
        "work",
    )
    out = asyncio.run(run_workflow(spec, {"tasks": tasks}, Callers(tool=tool)))
    assert out.halted == "stopped" and "items-at-most" in out.said, out


def _growing(teamwork: dict[str, Any], fails: tuple[str, ...] = ()) -> tuple[list[dict[str, str]], list[str], WorkflowSpec, Callers]:
    """t1 and t2 to start with; working t1 adds t3. `fails` names tasks whose call raises."""
    tasks = [{"id": "t1"}, {"id": "t2"}]
    done: list[str] = []

    async def tool(tool: str, action: str, inputs: dict) -> dict:
        task = inputs["task"]
        done.append(task)
        if task == "t1":
            tasks.append({"id": "t3"})
        await asyncio.sleep(0)
        if task in fails:
            raise RuntimeError(f"{task} broke")
        return {"did": task}

    spec = _flow(
        {
            "work": {
                "does": "each",
                "over": "input.tasks",
                "keeps-taking": "yes",
                "identified-by": ["id"],
                "teamwork": teamwork,
                "limits": {"items-at-most": 10, "at-once-at-most": 1, "when-it-runs-out": "stop-and-say-so"},
                "starts-at": "do",
                "steps": {"do": {"does": "call", "call": "q/run", "bind": {"task": "item.id"}}},
                "then": {"answered": "reply"},
            },
            "reply": {"does": "answer", "bind": {"items": "steps.work.items"}},
        },
        "work",
    )
    return tasks, done, spec, Callers(tool=tool)


def test_a_growing_each_stops_taking_once_its_teamwork_rule_is_met() -> None:
    tasks, done, spec, callers = _growing({"waits-for": "anyone"})
    out = asyncio.run(run_workflow(spec, {"tasks": tasks}, callers))
    assert out.halted == "final", out.said
    # t1 and t2 run side by side under the gate, so both may have answered when the join reads the first; t3, which
    # t1 added, is never taken.
    assert out.steps["work"]["items"] and all(item.get("did") in ("t1", "t2") for item in out.steps["work"]["items"]), out.steps["work"]
    assert "t3" not in done, "nothing is taken once the rule is met"


def test_a_growing_each_carries_on_past_a_failed_item_when_its_teamwork_says_so() -> None:
    tasks, done, spec, callers = _growing({"if-someone-fails": "carry-on"}, fails=("t2",))
    out = asyncio.run(run_workflow(spec, {"tasks": tasks}, callers))
    assert out.halted == "final", out.said
    assert sorted(done) == ["t1", "t2", "t3"], done
    assert [item for item in out.steps["work"]["items"] if "failed" in item] != [], out.steps["work"]
    assert {"did": "t3"} in out.steps["work"]["items"], out.steps["work"]


def test_a_growing_each_stops_at_a_failed_item_by_default() -> None:
    tasks, done, spec, callers = _growing({}, fails=("t1",))
    out = asyncio.run(run_workflow(spec, {"tasks": tasks}, callers))
    assert out.halted == "stopped", out
    assert "t3" not in done, done


def test_a_stop_undoes_what_the_stopped_run_did() -> None:
    calls: list[tuple[str, dict]] = []

    async def tool(tool: str, action: str, inputs: dict) -> dict:
        calls.append((action, dict(inputs)))
        if action == "print":
            await asyncio.sleep(5)
        return {}

    spec = _flow(
        {
            "start": {
                "does": "call",
                "call": "printer/print",
                "waits-for-result": "no",
                "undone-by": "printer/cancel",
                "bind": {"doc": "input.doc"},
                "then": {"answered": "halt"},
            },
            "halt": {"does": "stop", "stops": "steps.start.run", "then": {"answered": "reply"}},
            "reply": {"does": "answer"},
        },
        "start",
    )
    out = asyncio.run(run_workflow(spec, {"doc": "a"}, Callers(tool=tool)))
    assert out.halted == "final", out.said
    assert out.steps["halt"] == {"stopped": True}
    assert calls[-1] == ("cancel", {"doc": "a"}), calls
