"""`pact-sync` — record what an MCP server says it offers, into the tree (96 §E).

`resources/<server>.yaml` gets a `published:` block: every tool the server
lists, its own wording, its argument schema as published, and one digest over
all of it — the digest `mcp_bridge.digest_of` takes at connect time, so the
two are the same number when nothing has changed and different the moment
anything has.

## Why a separate command, and why in this package

`pact check` is hermetic: it reads files and never opens a connection, which
is what makes reviewing an untrusted workspace safe. Asking a server what it
has is the opposite act, so it is a different verb, run on purpose, by
somebody who may connect — and its output is a diff a reviewer reads in the
pull request, which is the review a hand-copied `takes:` list was standing in
for.

## Two ways in

* `--from-file tools.json` — a `tools/list` response somebody captured. This is
  the air-gapped path (D17): the listing is carried across on purpose and
  recorded here, and nothing in this process touches a network.
* `--url https://...` — ask the server now, through the `mcp` client SDK when it
  is installed. The endpoint in the resource file is a NAME the host resolves,
  never an address, so the address is given here by whoever runs this — the
  same rule `mcp_bridge` keeps: nothing reads an address out of the tree.

Nothing here decides anything. Which actions an agent may call, and what needs a
person, stay written by a person in `tools/`; `pact check` then holds every one
of those lines to the argument names this command recorded.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .mcp_bridge import _attr, _jsonable, digest_of

__all__ = ["published_block", "write_published", "main"]


def _listed(response: Any) -> list[Any]:
    """The tools of a `tools/list` response, a bare list, or a `{name: tool}` map."""
    if isinstance(response, Mapping):
        if "tools" in response:
            return list(response["tools"] or [])
        if "result" in response and isinstance(response["result"], Mapping):
            return list(response["result"].get("tools") or [])
        return [{"name": k, **(v if isinstance(v, Mapping) else {})} for k, v in response.items()]
    return list(response or [])


def published_block(
    tools: Iterable[Any],
    *,
    instructions: str = "",
    server_version: str = "",
    taken_at: "_dt.datetime | None" = None,
) -> dict[str, Any]:
    """The `published:` block for one server, digest included."""
    tools = list(tools)
    when = (taken_at or _dt.datetime.now(_dt.timezone.utc)).astimezone(_dt.timezone.utc)
    recorded: dict[str, Any] = {}
    for entry in tools:
        name = _attr(entry, "name")
        if not name:
            continue
        one: dict[str, Any] = {}
        description = _attr(entry, "description")
        if description:
            one["description"] = str(description)
        for key in ("inputSchema", "input_schema"):
            schema = _attr(entry, key)
            if schema is not None:
                one["takes"] = _jsonable(schema)
                break
        for key in ("outputSchema", "output_schema"):
            schema = _attr(entry, key)
            if schema is not None:
                one["answers-with"] = _jsonable(schema)
                break
        hints = _attr(entry, "annotations")
        if hints:
            one["hints"] = _jsonable(hints)
        recorded[str(name)] = one
    block: dict[str, Any] = {
        "taken-at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "digest": digest_of(tools, instructions),
    }
    if server_version:
        block["server-version"] = server_version
    if instructions:
        block["instructions"] = instructions
    block["tools"] = dict(sorted(recorded.items()))
    return block


def write_published(resource_file: Path, block: Mapping[str, Any]) -> None:
    """Replace the `published:` block of one resource file, keeping the rest.

    Everything a person wrote — comments, the endpoint, the consent question —
    stays exactly as it was; only the machine-written block moves, so the diff a
    reviewer reads is the server's change and nothing else.
    """
    text = resource_file.read_text(encoding="utf-8")
    kept: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        top = line[:1] not in (" ", "\t", "\n", "\r", "") and not line.startswith("#")
        if top:
            skipping = line.startswith("published:")
        if not skipping:
            kept.append(line)
    body = "".join(kept).rstrip("\n") + "\n"
    dumped = yaml.safe_dump(
        {"published": dict(block)}, sort_keys=False, allow_unicode=True, width=100
    )
    resource_file.write_text(
        body
        + "# Written by `pact-sync`. Review the change; do not edit by hand.\n"
        + dumped,
        encoding="utf-8",
    )


def _from_server(url: str, token: str) -> "tuple[list[Any], str, str]":
    """Ask a live server, through the `mcp` client SDK, for its tools."""
    try:
        import asyncio

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as missing:  # pragma: no cover - depends on the machine
        raise SystemExit(
            "error: asking a server needs the MCP client SDK, which is not installed here "
            f"({missing}).\n  fix: `pip install mcp`, or capture the server's `tools/list` "
            "response on a machine that can reach it and pass it with --from-file."
        ) from missing

    async def ask() -> "tuple[list[Any], str, str]":  # pragma: no cover - needs a server
        headers = {"Authorization": f"Bearer {token}"} if token else None
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                hello = await session.initialize()
                listed = await session.list_tools()
                info = getattr(hello, "serverInfo", None)
                return (
                    list(listed.tools),
                    str(getattr(hello, "instructions", "") or ""),
                    str(getattr(info, "version", "") or ""),
                )

    return asyncio.run(ask())


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pact-sync",
        description="Record what an MCP server offers into its resources/<server>.yaml.",
    )
    parser.add_argument("server", help="the resource's name, as `connect:` writes it")
    parser.add_argument("workspace", nargs="?", default=".", help="the workspace folder")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-file", help="a captured `tools/list` response, as JSON")
    source.add_argument("--url", help="the server's address, resolved by you, not the tree")
    parser.add_argument("--token", default="", help="a bearer token for --url; never written")
    parser.add_argument("--instructions", default="", help="the server's own instructions")
    parser.add_argument("--server-version", default="")
    args = parser.parse_args(argv)

    resource = Path(args.workspace) / "resources" / f"{args.server}.yaml"
    if not resource.is_file():
        print(
            f"error: there is no `resources/{args.server}.yaml` in {args.workspace}.\n"
            "  fix: name a server this workspace already connects to.",
            file=sys.stderr,
        )
        return 1
    if args.from_file:
        response = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        tools = _listed(response)
        instructions = args.instructions or str(
            (response.get("instructions") if isinstance(response, Mapping) else "") or ""
        )
        version = args.server_version
    else:  # pragma: no cover - needs a server
        tools, instructions, version = _from_server(args.url, args.token)
        instructions = args.instructions or instructions
        version = args.server_version or version
    block = published_block(tools, instructions=instructions, server_version=version)
    write_published(resource, block)
    print(
        f"Recorded {len(block['tools'])} tool(s) from '{args.server}' into "
        f"resources/{args.server}.yaml ({block['digest']}). Review the change, then run "
        "`pact check`."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
