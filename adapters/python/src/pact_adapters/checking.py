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
import hashlib
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


def check_instructions(
    document: Mapping[str, Any], agent: str, text: str, source: "str | Path | None" = None
) -> list[str]:
    """`pact check`'s errors once `agent`'s `instructions:` become `text`.

    Through the document when it can be written out; through a copy of the
    author's own tree when it carries files the document only references (a
    skill's scripts, a program's body), which is the worked example's case."""
    agent = _agent_key(document, agent)
    try:
        return check_document(with_instructions(document, agent, text))
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
        _write_instructions(root, agent, text)
        return _checked(binary, root)


def as_a_folder(root: Path, binary: "Path | None" = None) -> bool:
    """Rewrite a COPY of a tree that is written in the PACT language as the
    folder of YAML it stands for, leaving the files it carries where they are.
    `True` when it was rewritten, `False` when it was a folder already.

    Public, because every runtime that tries a change on a scratch copy has the
    same need (Bud Agent Flow's learning cycle searches `.yaml` and `.md` files
    for the text it replaces, and a `.pact` file is neither). Never call it on
    an author's own tree: it deletes the `.pact` files it rewrites.

    `_write_instructions` knows where an agent's instructions live in a folder.
    In a `.pact` file they are lines of somebody's text, and editing text by
    position is how a change lands in the wrong agent. `pact write` prints the
    tree as one file and `pact build` writes the folder that file stands for —
    the loader's own two directions, each of which reads back what it wrote —
    so the copy says exactly what the author's tree says, in the form this
    module can change one field of."""
    # FILES ending in `.pact`. A workspace's own runtime area is a DIRECTORY
    # called `.pact` (`.pact/learning/` is where a month's spend is kept), and
    # a bare `glob("*.pact")` matches it: every tree that had ever run a
    # learning cycle was taken for one written in the language.
    written = sorted(p for p in root.glob("*.pact") if p.is_file())
    if not written:
        return False
    binary = binary or pact_binary()
    if binary is None:
        raise Uncheckable(
            "the tree is written in the PACT language and there is no `pact` binary here "
            "to write it out as a folder"
        )
    printed = subprocess.run([str(binary), "write", str(root)], capture_output=True, text=True)
    if printed.returncode != 0:
        raise Uncheckable(
            "the tree is written in the PACT language and could not be printed as one "
            f"file to change: {(printed.stderr or printed.stdout).strip()}"
        )
    with tempfile.TemporaryDirectory(prefix="pact-as-a-folder-") as scratch:
        one = Path(scratch) / "workspace.pact"
        one.write_text(printed.stdout)
        out = Path(scratch) / "folder"
        built = subprocess.run(
            [str(binary), "build", str(one), "--to", str(out)], capture_output=True, text=True
        )
        if built.returncode != 0:
            raise Uncheckable(
                "the tree is written in the PACT language and could not be written out "
                f"as a folder to change: {(built.stderr or built.stdout).strip()}"
            )
        for file in written:
            file.unlink()
        for file in sorted(p for p in out.rglob("*") if p.is_file()):
            to = root / file.relative_to(out)
            # `knowledge/handbook.yaml`, where the copy already has a folder
            # `knowledge/handbook/` holding that entry's documents: the entry's
            # own settings go inside its folder, under its own name, or the
            # one entry is written in two places.
            beside = to.with_suffix("")
            if to.suffix == ".yaml" and beside.is_dir():
                to = beside / to.name
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, to)
    return True


def _write_instructions(root: Path, agent: str, text: str) -> None:
    """Put `text` where `agent`'s instructions live in a copied tree.

    A tree in which they live nowhere this knows is NOT checked as it stands:
    that would hold the author's own tree to the checker and report the answer
    as the proposal's, which is how a change that breaks a rule passes."""
    if pact_binary() is not None:
        as_a_folder(root)
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
            return
    # The whole workspace in one file, which is what `pact build` writes when a
    # folder laid out the usual way would not read back the same.
    whole = root / "workspace.yaml"
    if whole.exists():
        body = yaml.safe_load(whole.read_text()) or {}
        entry = (body.get("agents") or {}).get(agent) if isinstance(body, dict) else None
        if isinstance(entry, dict):
            entry["instructions"] = text
            whole.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))
            return
    raise Uncheckable(
        f"nothing in a copy of the tree holds the instructions of the agent {agent!r}, so "
        "the change could not be put in front of the checker"
    )


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


def with_instructions(document: Mapping[str, Any], agent: str, text: str) -> dict[str, Any]:
    """A copy of `document` with one agent's `instructions:` replaced."""
    proposed = copy.deepcopy(dict(document))
    agents = proposed.setdefault("agents", {})
    entry = dict(agents.get(agent) or {})
    entry["instructions"] = text
    agents[agent] = entry
    return proposed


# ------------------------------------------------- what a run instantiates
#
# Law 8 is "anything created during a run must pass the *same* checker at the
# moment it is instantiated" (97 §4, law 8): a `narrowed-new` helper, a skill
# the run wrote, a `run-code` snippet. Each is put in front of the checker the
# same way a proposal is: as the document it would make, the starter's own
# closure with the one new definition added. The functions below build those
# documents, and the same rules are what a second runtime builds them by, so a
# definition checked here and one checked there are the same document.


class NotNarrower(ValueError):
    """A helper was described with something its starter does not have. The
    message is `delegation.beyond_its_starter`'s, so the model reads the same
    sentence whichever runtime refused it."""


def _free_key(entries: Mapping[str, Any] | None, base: str) -> str:
    """`base`, or `base-2`, `base-3`… the first key `entries` does not hold."""
    taken = entries or {}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


_END_RAW = "{% endraw %}"


def literal(text: str, document: Mapping[str, Any]) -> str:
    """Words a model wrote, as the checker must read them: literally.

    A model's `{{ order }}` is an order number it typed, not a hole the run
    fills. Under the default template language that is `\\{{`; under
    `template-language: jinja` it is a raw block, and an `{% endraw %}` inside
    the words is written between two raw blocks as a string.
    """
    if document.get("template-language") != "jinja":
        out, i = [], 0
        while True:
            j = text.find("{{", i)
            if j < 0:
                out.append(text[i:])
                return "".join(out)
            out.append(text[i:j])
            out.append("{{" if j > 0 and text[j - 1] == "\\" else "\\{{")
            i = j + 2
    if not any(mark in text for mark in ("{{", "{%", "{#")):
        return text
    between = "{{ '" + _END_RAW + "' }}"
    return between.join("{% raw %}" + part + _END_RAW for part in text.split(_END_RAW))


def _listed(raw: Any) -> list[str]:
    if raw is None:
        return []
    return [str(x) for x in raw] if isinstance(raw, (list, tuple)) else [str(raw)]


def with_helper(
    document: Mapping[str, Any],
    starter: str,
    instructions: str,
    *,
    description: str | None = None,
    uses: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The document a `narrowed-new` helper makes: `starter`'s own entry under
    the key `<starter>-helper`, told `instructions`, running with the
    starter's `uses:` or the narrower `uses` given, on the starter's model.

    Raises `NotNarrower` when `uses` names anything the starter lacks.
    """
    from .delegation import beyond_its_starter

    agents = dict(document.get("agents") or {})
    entry = {k: v for k, v in dict(agents.get(starter) or {}).items() if k != "name"}
    if uses is not None:
        refused = beyond_its_starter(starter, _listed(entry.get("uses")), list(uses))
        if refused:
            raise NotNarrower(refused)
        entry["uses"] = list(uses)
    said = description.strip() if description and description.strip() else entry.get("description")
    if said is not None:
        entry["description"] = literal(str(said), document)
    entry["instructions"] = literal(instructions, document)
    agents[_free_key(agents, f"{starter}-helper")] = entry
    proposed = copy.deepcopy(dict(document))
    proposed["agents"] = agents
    return proposed


def with_skill(
    document: Mapping[str, Any],
    agent: str,
    name: str,
    description: str,
    content: str,
    *,
    use_when: str | None = None,
) -> dict[str, Any]:
    """The document a skill a run wrote makes: a `skills:` entry, named in
    `agent`'s `uses:` when the agent writes one (an agent without `uses:`
    reaches every skill already)."""
    proposed = copy.deepcopy(dict(document))
    skills = dict(proposed.get("skills") or {})
    key = _free_key(skills, name)
    skill: dict[str, Any] = {"name": name, "description": literal(description, document)}
    if use_when is not None:
        skill["use-when"] = literal(use_when, document)
    skill["content"] = literal(content, document)
    skills[key] = skill
    proposed["skills"] = skills
    agents = dict(proposed.get("agents") or {})
    entry = agents.get(agent)
    if isinstance(entry, Mapping) and entry.get("uses") is not None:
        agents[agent] = {**entry, "uses": [*_listed(entry.get("uses")), key]}
        proposed["agents"] = agents
    return proposed


#: The engine a snippet in each language runs as. A language with no engine
#: here cannot be put in front of the checker, so it is not run.
ENGINES = {"python": "python", "typescript": "typescript"}


def with_program(
    document: Mapping[str, Any],
    language: str,
    code: str,
    *,
    description: str | None = None,
    runs_for_at_most_ms: int | None = None,
) -> dict[str, Any]:
    """The document a `run-code` snippet makes: a nondeterministic
    `programs:` entry under `run-code-<first 12 hex of the code's sha256>`,
    its ceiling the run's own. The body is recorded, never opened, by PACT,
    so the snippet's words are not part of what is checked.

    Raises `Uncheckable` for a language PACT has no engine for.
    """
    engine = ENGINES.get(language)
    if engine is None:
        raise Uncheckable(f"programs here run as {language!r}, which PACT has no engine for")
    digest = hashlib.sha256(code.encode()).hexdigest()[:12]
    said = (description or "").strip() or "A program the agent wrote during the run."
    fuel: dict[str, Any] = {}
    if runs_for_at_most_ms is not None:
        fuel["runs-for-at-most"] = f"{runs_for_at_most_ms}ms"
    fuel["when-it-runs-out"] = "stop-and-say-so"
    proposed = copy.deepcopy(dict(document))
    programs = dict(proposed.get("programs") or {})
    programs[_free_key(programs, f"run-code-{digest}")] = {
        "description": literal(said, document),
        "engine": engine,
        "determinism": "nondeterministic",
        "fuel": fuel,
    }
    proposed["programs"] = programs
    return proposed
