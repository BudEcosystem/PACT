"""Two of Pydantic AI's own files as a PACT tree's: an `mcp.json` (02P P2) and a folder of
harness agent definitions (02P K3).

Both are read as data: nothing in them is run, launched or connected to.

**`mcp.json`** (`from_mcp_json`) is the `mcpServers` file `pydantic_ai.mcp.load_mcp_toolsets`
reads (`PA/mcp.py`: Claude Desktop's, Claude Code's and Cursor's shape). Each server becomes
one `resources/<name>.yaml` (`resource-kind: mcp-server`). A `url:` with no credential in it is
the resource's `endpoint:`; a server launched by a `command:`, or reached at an address that
carries `${VAR}`, a password, a query, a `;parameter` or a path segment or host label that reads
as a key (Zapier's MCP addresses carry the account's), is `endpoint: host/<name>`, a name the host binds
(`--server <name>=...`), and how it is launched or what it is sent (`args`, `env`, `cwd`,
`headers`) is the host's and is named, never copied: those are where credentials live.
Pydantic AI prefixes each server's tools with its name (`<name>_<tool>`); the tool file that
says `connect: <name>`, its actions named as the server names them, is still to write.

**A harness agent folder** (`from_agent_folder`) is what `SubAgents(agent_folders=...)` loads:
each Claude-style `*.md` (frontmatter `name`, `description`, `tools`, `model`, `color`, and the
body as instructions) and each Codex-style `*.toml` (`name`, `description`,
`developer_instructions`, ...) becomes `agents/<name>.yaml` with its `description:` and
`instructions:`. Its tool names mean what the author's `tool_resolver` makes of them and its
`model` is ignored by the harness itself (a disk agent runs on its parent's), so both are
named with the line to write; the agent that hands work to these names them in `team:`.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .importing import ImportReport, not_the_folders_own, read_text
from .openapi import Imported, NotImported
from .openapi_shapes import kebab

__all__ = ["from_agent_folder", "from_mcp_json"]

#: What a server's launch line says, which is the host's to hold.
_LAUNCH = {
    "args": "the arguments the host launches it with",
    "env": "the environment the host launches it in, where its credentials usually are; never copied",
    "cwd": "the folder the host launches it in",
    "headers": "what is sent with every request, where a credential usually is; never copied. Write "
    "`auth: {by-reference: <name>}` and have the host hold it",
}
#: Keys `load_mcp_toolsets` reads past (`PA/mcp.py`: "only ignored, never honoured").
_IGNORED = {
    "type": "Pydantic AI ignores it too: the transport is read from the address",
    "disabled": "Pydantic AI ignores it too: a disabled server still loads",
}


def from_mcp_json(document: Mapping[str, Any]) -> Imported:
    """An `mcp.json` mapping as one `resources/<name>.yaml` per server."""
    servers = document.get("mcpServers")
    if not isinstance(servers, Mapping) or not servers:
        raise NotImported("this holds no `mcpServers:` map. Fix: give the `mcp.json` `load_mcp_toolsets` reads.")
    report = ImportReport(kind="an MCP configuration (mcp.json)", seen=tuple(document))
    for key in document:
        if key != "mcpServers":
            report.unmapped[key] = f"`{key}`, which `load_mcp_toolsets` does not read"
    report.mapped["mcpServers"] = "one `resources/<name>.yaml` per server"
    files: dict[str, str] = {}
    owed: list[str] = []
    made: dict[str, str] = {}  # each resource's name, and the server it is
    for name, entry in servers.items():
        where, called = f"mcpServers.{name}", kebab(str(name)) or "server"
        if not isinstance(entry, Mapping) or not ("url" in entry or "command" in entry):
            raise NotImported(f"server {name!r} has neither `command` nor `url`. Fix: give it one, as Pydantic AI needs.")
        first, n = called, 1
        while called in made:  # `my_server` and `my-server` are one PACT name: two servers, two files
            n += 1
            called = f"{first}-{n}"
        made[called] = str(name)
        report.seen += (where, *(f"{where}.{k}" for k in entry))
        report.mapped[where] = f"`resources/{called}.yaml`, its tools offered by Pydantic AI as `{name}_<tool>`" + (
            f" (`{first}` is the server {made[first]})" if called != first else ""
        )
        endpoint = f"host/{called}"
        if "url" in entry:
            address = str(entry["url"])
            if _plain(address):
                endpoint = address
                report.mapped[f"{where}.url"] = "`endpoint:`"
                if not urlsplit(address).hostname in ("localhost", "127.0.0.1", "::1"):
                    owed.append(f"`tools` in workspace.yaml's `allow-egress:`, to reach {called} off this machine")
            else:
                report.not_portable[f"{where}.url"] = (
                    "an address that carries a `${...}`, a password, a query, a `;parameter` or a key in its "
                    "path or host, where credentials live; never "
                    f"copied. It is `endpoint: host/{called}`: bind it with `--server {called}=<the address>`"
                )
        if "command" in entry:
            report.mapped[f"{where}.command"] = (
                f"`endpoint: host/{called}`: a server the host launches and binds under {called} "
                "(a FastMCP client over its command)"
            )
        for key in entry:
            if key in _LAUNCH:
                report.not_portable[f"{where}.{key}"] = _LAUNCH[key]
            elif key in _IGNORED:
                report.not_portable[f"{where}.{key}"] = _IGNORED[key]
            elif key not in ("url", "command"):
                report.unmapped[f"{where}.{key}"] = f"`{key}`, which `load_mcp_toolsets` does not read"
        files[f"resources/{called}.yaml"] = _text(
            {"resource-kind": "mcp-server", "endpoint": endpoint, "description": f"The MCP server {name}, from mcp.json."}
        )
        owed.append(
            f"`tools/{called}.yaml` with `connect: {called}` and one action per tool the server lists, named as "
            f"the server names it (Pydantic AI offers them as `{name}_<tool>`)"
        )
    report.still_to_write = tuple(owed)
    return Imported(api="", files=files, shapes={}, report=report)


#: A path segment or host label that reads as a key, not a word: sixteen or more characters
#: mixing letters and digits, or a known key prefix (`sk-`, `sk_`, `pk_`, `ghp_`, `xoxb-`, ...).
#: Some hosted MCP servers (Zapier's, among others) put the account's secret in the path, and
#: some in a subdomain.
_KEYLIKE = re.compile(r"(?=[^/]*[A-Za-z])(?=[^/]*\d)[^/]{16,}|(?i:sk|pk|rk|ghp|gho|ghs|xox[abprs])[-_][^/]+")


def _plain(address: str) -> bool:
    """Whether an address can be written down as it is: no `${...}`, no password, no query,
    fragment or `;parameter`, and no path segment or host label that reads as a key."""
    if "${" in address:
        return False
    parts = urlsplit(address)
    if parts.scheme not in ("http", "https") or parts.username or parts.password or parts.query or parts.fragment:
        return False
    if ";" in parts.path:  # `;token=...`: `urlsplit` leaves a path parameter in the path
        return False
    words = [*parts.path.split("/"), *(parts.hostname or "").split(".")]
    return not any(_KEYLIKE.fullmatch(word) for word in words)


# ─────────────────────────────────────────────────────────────── agent folders

#: What a definition's own keys become, and the named losses.
_MAPS = {"name": "the agent's file name", "description": "`description:`", "developer_instructions": "`instructions:`"}
_LOSSES = {
    "tools": "tool names the author's `tool_resolver` turns into toolsets (without one the harness offers "
    "none). Write `uses:` naming this tree's tools",
    "allowed-tools": "tool names the author's `tool_resolver` turns into toolsets (without one the harness "
    "offers none). Write `uses:` naming this tree's tools",
    "model": "the harness ignores it too: a disk agent runs on its parent's model, or `agent_overrides`. "
    "Write `model:` naming a catalogue row",
    "effort": "the harness ignores it: `agent_overrides` sets a disk agent's thinking. Write "
    "`settings: {thinking: <level>}`",
    "model_reasoning_effort": "the harness ignores it: `agent_overrides` sets a disk agent's thinking. Write "
    "`settings: {thinking: <level>}`",
    "color": "how an editor shows the agent; the harness ignores it too",
}


def from_agent_folder(folder: Path) -> Imported:
    """Each `*.md` and `*.toml` definition directly in `folder` as `agents/<name>.yaml`."""
    if not folder.is_dir():
        raise NotImported(f"{folder.name} is not a folder. Fix: give the folder `SubAgents(agent_folders=...)` reads.")
    report = ImportReport(kind=f"a folder of harness agent definitions ({folder.name})")
    files: dict[str, str] = {}
    made: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        where = path.name
        report.seen += (where,)
        if why := not_the_folders_own(path, folder):
            report.not_portable[where] = why
            continue
        if path.suffix not in (".md", ".toml") or not path.is_file():
            report.not_portable[where] = "not an agent definition: the harness reads only `*.md` and `*.toml` files"
            continue
        said, body = _definition(path)
        called = kebab(str(said.get("name") or path.stem)) or "agent"
        if called in made:
            report.not_portable[where] = f"a second agent named {called} ({made[called]} came first): the harness keeps the first"
            continue
        made[called] = where
        report.mapped[where] = f"`agents/{called}.yaml`"
        agent: dict[str, Any] = {}
        if said.get("description"):
            agent["description"] = " ".join(str(said["description"]).split())
        instructions = str(said.get("developer_instructions") or body).strip()
        if instructions:
            agent["instructions"] = instructions
            if path.suffix == ".md":
                report.seen += (f"{where}.body",)
                report.mapped[f"{where}.body"] = "`instructions:`"
        for key in said:
            report.seen += (f"{where}.{key}",)
            if key in _MAPS:
                report.mapped[f"{where}.{key}"] = _MAPS[key]
            elif key in _LOSSES:
                report.not_portable[f"{where}.{key}"] = _LOSSES[key]
            else:
                report.not_portable[f"{where}.{key}"] = (
                    "the harness skips a TOML definition that has it" if path.suffix == ".toml" else "the harness reads past it"
                )
        files[f"agents/{called}.yaml"] = _text(agent)
    if not made:
        raise NotImported(f"{folder.name} holds no `*.md` or `*.toml` agent definition. Fix: give the folder that does.")
    team = ", ".join(f"`{n}: <what it does>`" for n in made)
    report.still_to_write = (
        f"`team:` on the agent that hands work to these: {team}",
        *(f"`description:` in agents/{n}.yaml" for n in made if "description:" not in files[f"agents/{n}.yaml"]),
    )
    return Imported(api="", files=files, shapes={}, report=report)


def _definition(path: Path) -> tuple[dict[str, Any], str]:
    """A definition's keys and its body (the instructions of a Markdown one)."""
    text = read_text(path, path.name)
    try:
        if path.suffix == ".toml":
            return dict(tomllib.loads(text)), ""
        found = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)(.*)\Z", text, re.DOTALL)
        if not found:
            return {}, text
        said = yaml.safe_load(found.group(1)) or {}
    except (tomllib.TOMLDecodeError, yaml.YAMLError) as trouble:
        raise NotImported(f"{path.name} could not be read ({' '.join(str(trouble).split())}). Fix: correct it.") from None
    if not isinstance(said, Mapping):
        raise NotImported(f"{path.name}'s frontmatter is not a map of keys. Fix: write `name:`, `description:` lines.")
    return dict(said), found.group(2)


def _text(body: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(body), sort_keys=False, allow_unicode=True, width=100)
