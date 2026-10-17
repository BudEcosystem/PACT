"""A Pydantic AI agent as the files of a PACT tree (02P A1, A23, T1, T12, P1).

What `pact-import FILE --as pydantic-ai-spec --out DIR` writes, and what a host
that holds a live `Agent` writes through the same door (budflow-core's
`budflow import FILE.py --as pydantic-ai --out DIR`): the agent as
`agents/<name>.yaml`, each tool file the live importer makes
(`pydantic_ai_live`), a `resources/<name>.yaml` for each MCP server those
reach, and each nested object of the answer as a shape with parts under
`workspace.yaml`'s `shapes:`. `imported_agent` writes nothing; it returns the files as text with the
report, as `openapi.from_openapi` does, and `openapi.write_into` is the one
door that touches a disk: a file already there with other words refuses the
whole import before anything is written, and one with the same words is left
as it is, so importing the same agent twice writes nothing the second time.
"""

from __future__ import annotations

from typing import Any, Mapping

import yaml

from .openapi import Imported
from .openapi_shapes import kebab

__all__ = ["imported_agent"]


def imported_agent(source: Any, *, name: str = "", connect: str = "") -> Imported:
    """`source` (a live `pydantic_ai.Agent`, or a spec file's mapping) as a tree's files.

    `name` is the agent's file name (kebab case), else its own `name`, else
    `agent`. `connect` is the MCP server the host serves a live agent's Python
    functions from (`pydantic_ai_live.from_pydantic_ai_agent`); a spec file has
    no tools of its own to reach anywhere.
    """
    if isinstance(source, Mapping):
        from .pydantic_ai_interop import from_pydantic_ai_spec

        shapes: dict[str, Any] = {}
        block, report = from_pydantic_ai_spec(source, shapes)
        tools: dict[str, dict[str, Any]] = {}
        servers: tuple[str, ...] = ()
    else:
        from .pydantic_ai_live import imported

        found = imported(source, connect=connect)
        block, tools, servers, report, shapes = found.agent, found.tools, found.servers, found.report, found.shapes
        if connect and any(body.get("connect") == connect for body in tools.values()):
            servers = (*servers, connect)  # the server the host serves the Python tools from
    called = kebab(name or str(block.get("name") or "")) or "agent"
    files = {f"agents/{called}.yaml": _text(block)}
    files.update({f"tools/{tool}.yaml": _text(body) for tool, body in tools.items()})
    files.update(
        {
            f"resources/{server}.yaml": _text(
                {
                    "resource-kind": "mcp-server",
                    "description": f"The MCP server a Pydantic AI agent reached as {server}.",
                }
            )
            for server in servers
        }
    )
    return Imported(api=str(connect or ""), files=files, shapes=shapes, report=report)


def _text(body: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(body), sort_keys=False, allow_unicode=True, width=100)
