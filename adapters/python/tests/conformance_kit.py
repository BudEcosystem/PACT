"""Replaying the shared cases (`tests/conformance/*.json`) on PACT's own runtime.

A case is everything a run depends on, written down: the tree, who runs, what
they are asked, what the model writes at each step, what each tool hands back,
what every other agent says when it is woken, what a judge answers and what a
person answers. `expect` is everything another runtime can observe of the run.

Any runtime replays a case the same way and compares its own answer with
`expect`. This file is how PACT's reference harness and reference workflow
runtime do it; `test_the_shared_cases_are_what_this_runtime_does.py` holds the
checked-in `expect` to it, and writes it afresh under `PACT_BLESS=1`.

How a case is replayed, so a second runtime can do the same:

* **`model`** — the lead agent's turns. Turn N is what the model writes at its
  Nth step, counted by the assistant turns already in the conversation, so a
  run resumed after a park carries on where it stopped. Past the last turn, the
  last turn repeats.
* **`tools`** — `{tool: text}`, or `{tool: {action: text, "*": text}}`: what a
  call hands back. A tool is executed only when the run really makes the call.
* **`members`** — what each OTHER agent says when it is run (asked first, told
  after, or asked as a teammate): `{agent: text, "*": text}`. `null` means the
  host has nothing that can run another agent.
* **`judge`** — what the checking model answers each time it is asked.

In `expect`, **`closing`** is what the closing request of a run that answers
with what it has was told about the limit, last in its system text
(`Reached.closing` in `pact_adapters/limits.py`): which ceiling, which calls
the model asked for were not made, and to answer from what it has. `""` when
the run made no closing request.

* **`people`** — one entry for each time the run parks, in order: `"yes"` or
  `"no"`, given to every question of that park. `"nobody"` means no answer is
  given and the time the question allows (`answer-within:`) passes: the run is
  resumed with no answer, at a moment after the wait has run out.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pact_adapters.harness import ToolCall, delegate_by_running, run
from pact_adapters.ir import AgentSpec, WorkflowSpec
from pact_adapters.script import Script, Turn
from pact_adapters.transports.mock import ReferenceTransport
from pact_adapters.workflow_runtime import Callers, run_workflow
from trees import shown

REPO = Path(__file__).resolve().parents[3]
#: How `Reached.closing` begins: what a closing request is told about the limit.
CLOSING_BEGINS = "This run has reached its limit, "
CASES = REPO / "tests" / "conformance"


def _script(turns: list[dict[str, Any]]) -> Script:
    return Script([
        Turn(
            str(t.get("text") or ""),
            tuple(ToolCall(c["name"], dict(c.get("args") or {})) for c in t.get("calls") or ()),
        )
        for t in turns
    ])


def replay_agent(case: dict[str, Any]) -> dict[str, Any]:
    """One agent's run, as `expect` writes it down."""
    doc = shown(REPO / case["tree"])
    spec = AgentSpec.from_document(doc, case["agent"])
    lead = _script(case["model"])
    executed: list[list[Any]] = []
    woken: list[dict[str, str]] = []
    offered: list[list[str]] = []
    closing: list[str] = []

    class Lead(ReferenceTransport):
        async def model_call(self, system, history, tools):  # type: ignore[override]
            offered.append([t["name"] for t in tools])
            # What a closing request was told about the limit: the end of its
            # system text, from the sentence `Reached.closing` begins with.
            at = system.rfind(CLOSING_BEGINS)
            if not tools and at >= 0:
                closing.append(system[at:])
            return await super().model_call(system, history, tools)

    def tool(name: str):
        said = (case.get("tools") or {}).get(name, "")

        def body(args: dict[str, Any]) -> str:
            executed.append([name, dict(args)])
            if isinstance(said, dict):
                return str(said.get(str(args.get("action") or ""), said.get("*", "")))
            return str(said)

        return body

    tools = {t.name: tool(t.name) for t in spec.tools}
    members = case.get("members")

    def member(inner: AgentSpec) -> ReferenceTransport:
        text = members.get(inner.name, members.get("*", "")) if isinstance(members, dict) else ""

        class Member(ReferenceTransport):
            async def model_call(self, system, history, tools):  # type: ignore[override]
                woken.append({"agent": inner.name, "told": str(history[0]["content"])})
                return await super().model_call(system, history, tools)

        return Member(Script([Turn(str(text))]))

    kw: dict[str, Any] = {}
    if members is not None:
        kw["ask_member"] = delegate_by_running(doc, member)
    if case.get("judge") is not None:
        kw["checking_transport"] = ReferenceTransport(Script([Turn(str(case["judge"]))]))

    parks: list[dict[str, Any]] = []
    out = asyncio.run(run(spec, Lead(lead), case["says"], tools, **kw))
    for said in case.get("people") or ():
        if out.halted != "suspended":
            break
        parked = out.suspension
        parks.append({
            "steps-finished": len(out.steps),
            "reason": parked.reason,
            "asks": [a.name for a in parked.asks],
            "executed-so-far": len(executed),
        })
        if said == "nobody":
            # Nobody answers, and the time the question allows goes by.
            assert parked.waits_for is not None, "a wait with no `answer-within:` never runs out"
            out = asyncio.run(
                run(spec, Lead(lead), case["says"], tools, resume=parked,
                    now=parked.parked_at + parked.waits_for + 1.0, **kw)
            )
            continue
        answer = parked.answer(**{a.name: said for a in parked.asks})
        out = asyncio.run(
            run(spec, Lead(lead), case["says"], tools, resume=parked, answer=answer,
                now=float(len(parks)), **kw)
        )
    state = out.reactor.state() if out.reactor is not None else {}
    return {
        "steps": [
            {
                "calls": [{"name": c.name, "args": dict(c.args)} for c in s.tool_calls],
                "results": list(s.tool_results),
            }
            for s in out.steps
        ],
        "offered": offered,
        "closing": closing[-1] if closing else "",
        "executed": executed,
        "woken": woken,
        "parks": parks,
        "reactions": list(out.reactions),
        "reminders": list(state.get("reminders") or ()),
        "unenforced": list(out.unenforced),
        "halted": out.halted,
        "output": out.output,
    }


def replay_workflow(case: dict[str, Any]) -> dict[str, Any]:
    """One workflow's run, as `expect` writes it down."""
    doc = shown(REPO / case["tree"])
    spec = WorkflowSpec.from_workflow(doc, case["workflow"])
    given: list[dict[str, Any]] = []
    shown_to: list[dict[str, Any]] = []
    called: list[dict[str, Any]] = []

    def agent(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        given.append({"agent": name, "given": dict(inputs)})
        says = (case.get("agents") or {}).get(name, {})
        if isinstance(says, list):  # one answer for each time it is asked, the last repeating
            asked = sum(1 for g in given if g["agent"] == name)
            says = says[min(asked, len(says)) - 1]
        return dict(says)

    def tool(name: str, action: str, inputs: dict[str, Any]) -> dict[str, Any]:
        called.append({"tool": f"{name}/{action}", "given": dict(inputs)})
        return dict((case.get("tools") or {}).get(f"{name}/{action}", {}))

    def person(question: str, shown_: dict[str, Any]) -> dict[str, Any]:
        shown_to.append({"question": question, "shown": dict(shown_)})
        return dict((case.get("people") or {}).get(question, {}))

    callers = Callers(agent=agent, tool=tool, person=person if case.get("people") is not None else None)
    out = asyncio.run(run_workflow(spec, case["input"], callers, document=doc))
    return {
        "trace": list(out.trace),
        "given": given,
        "shown": shown_to,
        "called": called,
        "answer": json.loads(json.dumps(out.answer, default=str)),
        "halted": out.halted,
        "parked-at": out.parked_at,
        "question": out.question,
        "said": out.said,
        "unenforced": list(out.unenforced),
    }


def replay(case: dict[str, Any]) -> dict[str, Any]:
    made = replay_workflow(case) if "workflow" in case else replay_agent(case)
    return json.loads(json.dumps(made, sort_keys=True, default=str))
