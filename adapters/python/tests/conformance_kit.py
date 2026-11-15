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
the run made no closing request. **`after-a-yes`** is what the model was told
after a person said to keep going (`Reached.raised`): one text for each request
that was told, which is one for each yes, the first request after it and no
other.

* **The clock** — a case runs on its own clock and never on the wall clock:
  the first leg at 0 seconds, each resume at the number of parks so far, and a
  `"nobody"` resume one second after the wait has run out. A replay on the
  wall clock is a different run each day: a wait with `answer-within:` is
  inside its time today and past it tomorrow.
* **`people`** — one entry for each time the run parks, in order: `"yes"` or
  `"no"`, given to every question of that park. `"nobody"` means no answer is
  given and the time the question allows (`answer-within:`) passes: the run is
  resumed with no answer, at a moment after the wait has run out.

**`asked-again`**, in an agent's `expect`, is what the model was told each time
a reply that would have been the answer was not one (`answers_fit`): it did
not fit what the agent says it gives, or broke one of its `checked-by:` rules.
One text for each such reply that was asked for again, told at the request
that follows it and at no other; a closing request asked again is told it
after everything the closing request is told. **`said`** is what the model
wrote at each step, in order, a reply that was not the answer included.
**`answer`** is the fields of the answer for an agent that says what it gives:
each declared field the reply carried, as it was written, and no field the
agent does not declare; `{}` for an agent that declares none and for a run
that did not end in an answer. A run that never got a fitting answer ends
`checks-failed`, or keeps its ceiling's word when it had already run out.

A workflow's case has three more things it may say:

* **`people`**, by question: an answer, or a list of answers in the order they
  arrive, the last repeating. The text `"nobody"` in place of an answer means
  the question's time passed with no answer. `null` for the whole of `people`
  means nobody is there to ask, so the run parks at its first question.
* **`ran-out`** — the agents that reached one of their limits in this run and
  answered with what they had (`when-it-runs-out: answer-with-what-it-has`).
  What each says is still under `agents`; it is the answer of a run that ran
  out, and `steps.<stage>.ended` of the stage that called it is `ran-out`.
* **`ends`** — something outside the run ends it: `{"before": <stage>, "port":
  <port>}`. The arrival at that port, carrying this run's key, lands when the
  run is about to begin that stage (written as `trace` writes it), so every
  stage before it has finished and that one never starts. What the arrival
  does is the port's own lines, read from the tree: `undo:`, `then-run:`.

In a workflow's `expect`: **`why`** is the one word for why a `stopped` run
stopped (`workflow_runtime.STOPPED_BECAUSE`), `""` for any other ending;
**`cancelled-by`** is what ended a `cancelled` run, `{}` otherwise; and
**`started`** is every run it started that nobody waits for, in order, with
what each was given. An undo is a call like any other and is in `called`,
in the order it was made.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pact_adapters.answers_fit import CHECK_FAILED, DID_NOT_FIT
from pact_adapters.harness import ToolCall, delegate_by_running, run
from pact_adapters.ir import AgentSpec, WorkflowSpec
from pact_adapters.script import Script, Turn
from pact_adapters.transports.mock import ReferenceTransport
from pact_adapters.workflow_runtime import Callers, NobodyAnswered, RanOut, run_workflow
from trees import shown

REPO = Path(__file__).resolve().parents[3]
#: How `Reached.closing` begins: what a closing request is told about the limit.
CLOSING_BEGINS = "This run has reached its limit, "
#: How `Reached.raised` begins: what the first request after a yes is told.
RAISED_BEGINS = "A person was asked and said to keep going. "
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
    after_a_yes: list[str] = []
    asked_again: list[str] = []

    class Lead(ReferenceTransport):
        async def model_call(self, system, history, tools):  # type: ignore[override]
            offered.append([t["name"] for t in tools])
            # What a closing request was told about the limit: the end of its
            # system text, from the sentence `Reached.closing` begins with.
            at = system.rfind(CLOSING_BEGINS)
            if not tools and at >= 0:
                closing.append(system[at:])
            # What a request after a person said to keep going was told.
            at = system.rfind(RAISED_BEGINS)
            if at >= 0:
                after_a_yes.append(system[at:])
            # What a request was told because the reply before it was not the
            # answer: it did not fit `answers-with:`, or broke a rule.
            at = max(system.rfind(DID_NOT_FIT), system.rfind(CHECK_FAILED))
            if at >= 0:
                asked_again.append(system[at:])
                # A closing request asked again is the closing request, and
                # then why: `closing` is what the limit told it, without that.
                if closing and closing[-1].endswith(system[at:]):
                    closing[-1] = closing[-1][: -len(system[at:])].rstrip("\n")
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
    # The case's own clock, from 0. This leg ran on the wall clock while every
    # resume below ran on the case's, so a park was stamped with today's time
    # and resumed at second 1: a wait could then never run out. No case's
    # result depended on it. Bud Agent Flow found the same mixture in its own
    # replay, where it did change a result.
    out = asyncio.run(run(spec, Lead(lead), case["says"], tools, now=0.0, **kw))
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
        "closing": closing[0] if closing else "",
        "after-a-yes": after_a_yes,
        "asked-again": asked_again,
        "said": [s.text for s in out.steps],
        "answer": json.loads(json.dumps(out.answer, default=str)),
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
    handed: dict[str, int] = {}
    called: list[dict[str, Any]] = []

    def agent(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        given.append({"agent": name, "given": dict(inputs)})
        says = (case.get("agents") or {}).get(name, {})
        if isinstance(says, list):  # one answer for each time it is asked, the last repeating
            asked = sum(1 for g in given if g["agent"] == name)
            says = says[min(asked, len(says)) - 1]
        # An agent the case says ran out: its answer is one given on reaching
        # a limit, which is how a host that runs agents hands it back.
        return RanOut(dict(says)) if name in (case.get("ran-out") or ()) else dict(says)

    def tool(name: str, action: str, inputs: dict[str, Any]) -> dict[str, Any]:
        called.append({"tool": f"{name}/{action}", "given": dict(inputs)})
        return dict((case.get("tools") or {}).get(f"{name}/{action}", {}))

    def person(question: str, shown_: dict[str, Any]) -> dict[str, Any]:
        handed[question] = handed.get(question, 0) + 1
        says = (case.get("people") or {}).get(question, {})
        if isinstance(says, list):  # the answers as they arrive, the last repeating
            says = says[min(handed[question], len(says)) - 1]
        if says == "nobody":  # the question's time passed with no answer
            raise NobodyAnswered(question)
        return dict(says)

    started: list[dict[str, Any]] = []

    def start(workflow: str, inputs: dict[str, Any]) -> None:
        # Starting a run nobody waits for is the host's. A case records that
        # it was asked for, and with what.
        started.append({"workflow": workflow, "given": dict(inputs)})

    ends = case.get("ends") or {}

    def ended(at: str) -> dict[str, Any] | None:
        return {"port": ends["port"]} if ends and at == ends["before"] else None

    callers = Callers(
        agent=agent,
        tool=tool,
        person=person if case.get("people") is not None else None,
        start=start,
    )
    out = asyncio.run(
        run_workflow(spec, case["input"], callers, document=doc, ended=ended if ends else None)
    )
    assert started == [dict(s) for s in out.started], (started, out.started)
    return {
        "trace": list(out.trace),
        "given": given,
        "shown": list(out.asked),
        "refused": list(out.refused),
        "called": called,
        "answer": json.loads(json.dumps(out.answer, default=str)),
        "halted": out.halted,
        "why": out.why,
        "cancelled-by": dict(out.cancelled_by),
        "started": list(out.started),
        "parked-at": out.parked_at,
        "question": out.question,
        "said": out.said,
        "unenforced": list(out.unenforced),
    }


def replay(case: dict[str, Any]) -> dict[str, Any]:
    made = replay_workflow(case) if "workflow" in case else replay_agent(case)
    return json.loads(json.dumps(made, sort_keys=True, default=str))
