"""Two phases, one checker (law 8 of `docs/97-PRIMITIVES.md`; docs/98 WP-15).

Everything `pact check` promises holds for the tree an author wrote. Law 8 is
that it also holds for anything a run writes: a change a learning cycle
proposes is held to the same checker, the same binary, before it can take
effect — not to a Python re-reading of the rules, which would be a second
semantics and the failure this repository has found more than once.

How: the proposed document is written back out as a tree (`exploding.explode`,
which the round-trip tests already hold to `load(explode(D)) == D`) into a
scratch folder, and `pact check` is run on it. What comes back is the list of
errors in the checker's own words, empty when the change is sound.
"""

from __future__ import annotations

import copy
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

import yaml

from .exploding import CarriesPayloads, ExplodeRefused, explode
from .loader import pact_binary


class Uncheckable(Exception):
    """The change could not be put in front of the checker at all — no `pact`
    binary here, or a document that carries files with no tree to copy. Not a
    refusal: the caller says out loud that the change went unchecked."""


def check_document(document: Mapping[str, Any]) -> list[str]:
    """`pact check`'s errors for this document, in its own words; `[]` when sound.

    A document that cannot be written as a tree at all is refused with the
    exploder's reason, because a change nobody can check is not one to apply.
    """
    binary = pact_binary()
    if binary is None:
        raise Uncheckable("there is no `pact` binary here to check it with")
    with tempfile.TemporaryDirectory(prefix="pact-proposed-") as scratch:
        root = Path(scratch) / "tree"
        try:
            explode(document, root)
        except CarriesPayloads:
            raise  # the caller may have the tree to copy instead
        except ExplodeRefused as refused:
            # Not a refusal of the CHANGE: nothing could put it in front of the
            # checker, which the caller says out loud.
            raise Uncheckable(f"the document cannot be written out as a tree: {refused}") from None
        return _checked(binary, root)


def _agent_key(document: Mapping[str, Any], agent: str) -> str:
    """The key `agent` is filed under: itself, or the one agent whose `name:` it is.

    A host that built its `AgentSpec` by hand knows the display name ("Refund
    Desk") and not the folder ("refund-desk"). One agent carrying that name is
    unambiguous; none, or two, is a change nobody can place, said as such."""
    agents = document.get("agents") or {}
    if agent in agents:
        return agent
    named = [k for k, v in agents.items() if isinstance(v, Mapping) and v.get("name") == agent]
    if len(named) == 1:
        return named[0]
    if named:
        raise Uncheckable(f"{len(named)} agents are named {agent!r}, so the change has no one place to go")
    raise Uncheckable(f"the document has no agent {agent!r} to put the change in")


def check_agent_field(
    document: Mapping[str, Any],
    agent: str,
    field: str,
    value: Any,
    source: "str | Path | None" = None,
) -> list[str]:
    """`pact check`'s errors once `agent`'s `field:` becomes `value`.

    Through the document when it can be written out; through a copy of the
    author's own tree when it carries files the document only references (a
    skill's scripts, a program's body), which is the worked example's case.
    `instructions` is prose and lands in the agent's `instructions.md`; every
    other field is a setting and lands in its `agent.yaml`."""
    agent = _agent_key(document, agent)
    try:
        return check_document(with_field(document, agent, field, value))
    except CarriesPayloads:
        pass
    binary = pact_binary()
    if binary is None:
        raise Uncheckable("there is no `pact` binary here to check it with")
    if not source:
        raise Uncheckable(
            "this document carries files (a skill's scripts, a program's body) and no "
            "tree was given to copy"
        )
    with tempfile.TemporaryDirectory(prefix="pact-proposed-") as scratch:
        root = Path(scratch) / "tree"
        shutil.copytree(source, root)
        if field == "instructions":
            _write_instructions(root, agent, value)
        else:
            _write_setting(root, agent, field, value)
        return _checked(binary, root)


def _write_setting(root: Path, agent: str, field: str, value: Any) -> None:
    """Put `field: value` where `agent`'s settings live in a copied tree."""
    folder = root / "agents" / agent
    settings = folder / "agent.yaml" if folder.is_dir() else root / "agents" / f"{agent}.yaml"
    body = yaml.safe_load(settings.read_text()) if settings.exists() else {}
    body = body if isinstance(body, dict) else {}
    body[field] = value
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))


def _write_instructions(root: Path, agent: str, text: str) -> None:
    """Put `text` where `agent`'s instructions live in a copied tree."""
    folder = root / "agents" / agent
    as_file = folder / "instructions.md"
    if as_file.exists() or folder.is_dir():
        as_file.write_text(text if text.endswith("\n") else text + "\n")
        settings = folder / "agent.yaml"
        if settings.exists():
            body = yaml.safe_load(settings.read_text()) or {}
            if isinstance(body, dict) and "instructions" in body:
                del body["instructions"]
                settings.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))
        return
    flat = root / "agents" / f"{agent}.yaml"
    if flat.exists():
        body = yaml.safe_load(flat.read_text()) or {}
        if isinstance(body, dict):
            body["instructions"] = text
            flat.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))


def _checked(binary: Path, root: Path) -> list[str]:
    out = subprocess.run(
        [str(binary), "check", str(root), "--quiet"],
        capture_output=True,
        text=True,
    )
    if out.returncode == 0:
        return []
    said = (out.stdout + out.stderr).splitlines()
    return [line.strip() for line in said if line.startswith("error:")] or [
        (out.stdout + out.stderr).strip() or "pact check refused the proposed document"
    ]


def with_field(document: Mapping[str, Any], agent: str, field: str, value: Any) -> dict[str, Any]:
    """A copy of `document` with one agent's `field:` replaced."""
    proposed = copy.deepcopy(dict(document))
    agents = proposed.setdefault("agents", {})
    entry = dict(agents.get(agent) or {})
    entry[field] = value
    agents[agent] = entry
    return proposed
