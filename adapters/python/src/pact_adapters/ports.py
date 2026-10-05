"""What crosses the wall to another port, in one place.

A second implementation is handed a JSON payload built from an `AgentSpec`, and
for as long as that payload existed the tool half of it was written out by hand
at each caller:

    "tools": [{"name": t.name, "description": t.description} for t in spec.tools]

Five copies of one line, in five test files. `ToolSpec` has six fields, so four
were dropped at the wall — and dropping is worse than refusing, because the
second port then cannot honour the line AND cannot report it. `notDoneHere`'s own
docstring calls silence about an unhonoured line the T7 breach it exists to
prevent; it prevented it at the AGENT level, where `interceptors:`, `policy:` and
`team:` are named, while four fields one level down went straight past.

What each one cost, measured:

* `parameters` — the second port offered every tool with `parameters: {}`, so a
  model was told a tool exists and never what it takes. Word for word the defect
  `ir._takes` records and fixes on this side.
* `binds` — the promise that the model cannot see, name or change an argument. A
  port that never receives them cannot fill one.
* `remembers` — `remember-as:`, which that port has no store for.
* `reaches` — where the call GOES, which it has no client for.

The last two it genuinely cannot do. Being a smaller port is allowed; being
smaller in silence is not, and it cannot say what it is smaller by without being
told what it was given.

One function, so the next field added to `ToolSpec` reaches every driver by
existing rather than by somebody remembering five places. Held by
`test_the_second_port_is_told_what_a_tool_takes.py`.
"""

from __future__ import annotations

from typing import Any

from .ir import ToolSpec


#: Which key on the wire carries which field of `ToolSpec`.
#:
#: Declared rather than inferred, because the two vocabularies differ on purpose:
#: the wire uses the AUTHOR's words — `bind`, `remember-as` — so somebody reading
#: a second port's payload beside the YAML that produced it does not have to
#: translate. Without this the boundary guard would have to guess, and a guess is
#: what let four fields fall off the wall in the first place.
WIRE_NAME: dict[str, str] = {
    "name": "name",
    "description": "description",
    "parameters": "parameters",
    "binds": "bind",
    "remembers": "remember-as",
    "reaches": "reaches",
    "answers_with": "answers-with",
    "programs": "program",
    "available_when": "available-when",
    "reads_only": "reads-only",
}


def tool_payload(tool: ToolSpec) -> dict[str, Any]:
    """One tool, as another port is handed it.

    Keys are the wire names — `remember-as` rather than `remembers` — because the
    other side reads them beside the author's own vocabulary and a reviewer
    comparing the two should not have to translate.

    `reaches` is flattened to the three things a sentence about an unmade call
    needs — what kind of place it is, where, and how — rather than the whole
    object. A port that cannot make the call still has to be able to say where it
    would have gone.
    """
    # Every key comes THROUGH `WIRE_NAME`, so the correspondence is decided in one
    # place and read in one place. Writing the wire names out again here would be
    # a second copy of the mapping, which is the shape of the defect this whole
    # module exists to remove.
    out: dict[str, Any] = {
        WIRE_NAME["name"]: tool.name,
        WIRE_NAME["description"]: tool.description,
        WIRE_NAME["parameters"]: dict(tool.parameters),
    }
    if tool.binds:
        out[WIRE_NAME["binds"]] = {a: dict(w) for a, w in tool.binds.items()}
    if tool.remembers:
        out[WIRE_NAME["remembers"]] = dict(tool.remembers)
    if tool.answers_with:
        out[WIRE_NAME["answers_with"]] = {a: dict(w) for a, w in tool.answers_with.items()}
    if tool.programs:
        out[WIRE_NAME["programs"]] = dict(tool.programs)
    if tool.available_when:
        out[WIRE_NAME["available_when"]] = tool.available_when
    if tool.reads_only:
        out[WIRE_NAME["reads_only"]] = dict(tool.reads_only)
    if tool.reaches is not None:
        out[WIRE_NAME["reaches"]] = {
            "kind": tool.reaches.kind,
            "where": tool.reaches.value,
            "method": tool.reaches.method,
        }
    return out
