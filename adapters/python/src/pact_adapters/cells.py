"""A model that acts by writing a cell (`docs/100` §4.5).

A cell is a few statements of PACT Core: calls, a `for each`, a `decide`, an
`answer with`, and before them any helper the model wants to define. The model
writes one; the session's door checks it (`session.Session.cell`); it is
carried out by the reference workflow runtime on the WHOLE of each value; and
what comes back is the agent's answer.

What this gives that a list of tool calls does not: one action can loop,
branch and fan out, inside ceilings the model cannot raise; and a value is
worked on where it is, however large, while the model is shown a few words of
it (`previews`).

A refused cell is not the end. The model is told why, in the checker's own
sentence or the session guard's, and writes another, `tries` times in all:
the count an answer that does not fit its shape already has (`answers_fit`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

from .answers_fit import does_not_fit
from .previews import GRAMMAR, preview
from .session import Admission, Session, reach_of
from .workflow_runtime import Callers, run_workflow
from .ir import WorkflowSpec

#: How a run that never got an admitted, finished cell ended.
NO_CELL = "no-cell"

#: The language a cell is written in, as a model is told it. Short on purpose:
#: every line here is read on every request.
PRIMER = """\
You act by writing ONE cell: a few statements that are carried out for you. Reply with the cell and
nothing else: no explanation before it or after it.

An example of a cell (yours will differ):

each = for each item in input.documents
  limits:
    items-at-most: 50
    when-it-runs-out: stop-and-say-so
  page = library/read(document: item)
answer with pages: each.text, note: input.note

What its lines are:
- `page = library/read(document: item)` calls something you were given, with what it takes in the
  brackets, and names its answer `page`. After it, `page.<field>` is a field of that answer.
- `each = for each item in <a list>` carries out the indented statements once for every item of the
  list. Inside it, `item` is the item, and `item.<field>` a field of it. Directly under it, before the
  statements, it must have the three `limits:` lines as shown, with `items-at-most:` no smaller than
  the number of items. Always write `when-it-runs-out: stop-and-say-so`: a cell cannot ask a person.
- After the loop, `each.<field>` is the list of that field of what the loop's LAST statement answered
  in each round, and `each.items` is the list of those whole answers.
- `answer with <field>: <where from>, …` is the last line of the cell.

Every statement is a call, a `for each` or the `answer with`. Every value is a path to something you
were given or something you called: `input.<name>`, `<statement>.<field>`, `item`. There is no line
that only gives a value another name (`x = page.text` is not a statement: write `page.text` where
you need it). You cannot write a value of your own, and you cannot add, compare or join values: to
judge, word or compute something, call something that does. Write nothing on a line
after the statement except, if you want one, a comment that starts with ` # `.

You may define a helper before the statements, and then call it by its name:

agent <name>(<input>: <shape>) gives <field>: <shape>
  description: <one line>
  instructions: <what it is told>
  at most <a number> steps
  when it runs out: stop and say so
"""


@dataclass
class CellRun:
    """How acting by a cell went."""

    #: `final` when a cell was admitted, ran to its end and its answer fits;
    #: `no-cell` when `tries` cells were each refused, stopped or misfit.
    halted: str = "final"
    answer: dict[str, Any] = field(default_factory=dict)
    #: What the run says when it has no answer.
    said: str = ""
    #: Each cell the model wrote, in order, with what the door said to it.
    cells: list[tuple[str, Admission]] = field(default_factory=list)
    #: The version of the workspace the answering cell ran under.
    version: str = ""
    #: The stages the answering cell ran, as the workflow runtime traces them.
    trace: list[str] = field(default_factory=list)
    #: The system text of each request, for whoever wants to see what was told.
    told: list[str] = field(default_factory=list)


def what_it_may_call(document: Mapping[str, Any], allowed: "set[str] | frozenset[str]") -> str:
    """Each thing a cell may call, as a line a model can copy: its name, what
    it takes, and what its answer has."""
    lines = []
    for target in sorted(allowed):
        if "/" in target:
            tool, action = target.split("/", 1)
            body = (((document.get("tools") or {}).get(tool) or {}).get("actions") or {}).get(action) or {}
            takes, gives = body.get("takes") or {}, body.get("answers-with") or {}
        else:
            body = (document.get("agents") or {}).get(target) or (document.get("workflows") or {}).get(target) or {}
            takes, gives = body.get("accepts") or {}, body.get("answers-with") or {}
        said = ", ".join(f"{k}: {v}" for k, v in takes.items())
        back = ", ".join(f"{k}: {v}" for k, v in gives.items()) or "answer: text"
        about = str(body.get("description") or "").strip()
        lines.append(f"  {target}({said})  gives {back}" + (f"   # {about}" if about else ""))
    return "\n".join(lines) or "  (nothing)"


def cell_in(reply: str) -> str:
    """The cell a reply holds: what is inside its code fence, or all of it."""
    fenced = re.search(r"```[a-zA-Z]*\n(.*?)```", reply, re.S)
    return (fenced.group(1) if fenced else reply).strip("\n") + "\n"


async def act_by_a_cell(
    session: Session,
    agent: str,
    model_call: Callable[[str, list[dict[str, Any]], list[Any]], Awaitable[tuple[str, Any]]],
    asked: str,
    inputs: Mapping[str, Any],
    callers: Callers,
    *,
    tries: int = 3,
    may_call: "set[str] | frozenset[str]" = frozenset(),
) -> CellRun:
    """Have `agent` answer `asked` by writing a cell over `inputs`.

    `inputs` are handed to the cell by reference: the model is shown a
    preview of each, and the cell's statements are carried out on the whole
    value. The cell must end in an answer that is what the agent says it
    gives."""
    document = session.document
    spec = (document.get("agents") or {}).get(agent) or {}
    gives = dict(spec.get("answers-with") or {})
    allowed = set(reach_of(document, agent)) | set(may_call)
    takes = {name: _shape_of(value) for name, value in inputs.items()}
    system = "\n\n".join(part for part in (
        str(spec.get("instructions") or "").strip(),
        PRIMER,
        "What you may call:\n" + what_it_may_call(document, allowed),
        GRAMMAR,
        "What you were given:\n" + "\n".join(
            f"  input.{name} ({takes[name]}): {preview(value)}" for name, value in inputs.items()
        ),
        ("Your cell must end with `answer with` and exactly these fields:\n"
         + "\n".join(f"  {k}: {v}" for k, v in gives.items())) if gives else "",
    ) if part)
    out = CellRun()
    history: list[dict[str, Any]] = [{"role": "user", "content": asked}]
    why = ""
    for _ in range(max(1, tries)):
        told = system + (f"\n\n{why}" if why else "")
        out.told.append(told)
        reply, _calls = await model_call(told, history, [])
        text = cell_in(reply)
        admitted = session.cell(text, by=agent, takes=takes, gives=gives, may_call=may_call)
        out.cells.append((text, admitted))
        history.append({"role": "assistant", "content": reply})
        if not admitted.admitted:
            again = len(out.cells) > 1 and out.cells[-2][0] == text
            why = (("You wrote the same cell again, word for word. " if again else "")
                   + "Your last cell was refused, and nothing in it was carried out:\n"
                   + "\n".join(f"- {s}" for s in admitted.said)
                   + ("\nA different cell is needed: change the line the refusal points at, or take it out."
                      if again else "")
                   + "\nWrite the cell again.")
            continue
        try:
            flow = WorkflowSpec.from_workflow(session.document, admitted.main)
            ran = await run_workflow(flow, dict(inputs), callers, document=session.document)
        finally:
            version = admitted.version
            session.end(admitted)
        if ran.halted != "final":
            why = (f"Your last cell was carried out and stopped before its answer: {ran.said}\n"
                   "Write the cell again.")
            continue
        wrong = does_not_fit(json.dumps(ran.answer, default=str), gives, document.get("shapes") or {}) if gives else ()
        if wrong:
            why = ("Your last cell's answer did not fit what you must answer with:\n"
                   + "\n".join(f"- {p}" for p in wrong) + "\nWrite the cell again.")
            continue
        out.answer, out.version, out.trace = dict(ran.answer), version, list(ran.trace)
        return out
    out.halted = NO_CELL
    out.said = (f"Stopped without an answer: {len(out.cells)} cell(s) were written and none was "
                f"admitted and carried out to an answer that fits. {why.splitlines()[0] if why else ''}")
    return out


def _shape_of(value: Any) -> str:
    """The shape a value handed to a cell is written as."""
    if isinstance(value, bool):
        return "yes or no"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (list, tuple)):
        inner = {_shape_of(v) for v in value[:20]} or {"text"}
        return f"list of {inner.pop() if len(inner) == 1 and not next(iter(inner)).startswith(('list', 'map')) else 'text'}"
    return "text"


def callers_of(
    document_of: Callable[[], Mapping[str, Any]],
    tool_impls: Mapping[str, Callable[[dict[str, Any]], Any]],
    transport_for: "Callable[[Any], Any] | None" = None,
) -> Callers:
    """What a cell's calls reach, on PACT's own harness: a tool by the host's
    function for it, an agent by running it (`harness.run`) on the transport
    `transport_for` gives. `document_of` is asked each time, because a cell's
    helpers are in the session's document only while the cell lives."""
    from .harness import run
    from .ir import AgentSpec
    from .workflow_runtime import RanOut, worded

    def tool(name: str, action: str, inputs: dict[str, Any]) -> Any:
        came = tool_impls[name]({**inputs, "action": action})
        try:
            read = json.loads(came) if isinstance(came, str) else came
        except ValueError:
            read = came
        return read if isinstance(read, Mapping) else {"answer": read}

    async def agent(name: str, inputs: dict[str, Any]) -> Any:
        document = document_of()
        spec = AgentSpec.from_document(document, name)
        out = await run(spec, transport_for(spec), worded(document, name, inputs), dict(tool_impls))
        answer = dict(out.answer) or {"answer": out.output}
        if out.halted == "final":
            return answer
        if out.stopped_by is not None and out.answer:
            return RanOut(answer)
        raise RuntimeError(f"{name} did not answer ({out.halted}): {out.output}")

    return Callers(tool=tool, agent=agent if transport_for is not None else None)
