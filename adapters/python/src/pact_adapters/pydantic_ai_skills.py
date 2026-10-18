"""Skills both ways: a PACT tree's skills as a `pydantic-ai-harness` Skills directory, and such a
directory as a tree's `skills/` (02P X5).

The two forms are nearly one: a skill is a folder holding `SKILL.md`, YAML frontmatter
(`name`, `description`) and a Markdown body, with `references/`, `scripts/` and `assets/`
beside it. PACT reads more of the frontmatter (`use-when`, `do-not-use-when`, `if-unsure`,
`costs-about`, `available-when`) and keeps the three folders as files of the skill; the
harness's `Skills(<directory>)` offers each skill by its name and description, loads its body
on demand (`load_capability`), reads past any other frontmatter key and never reads, lists or
runs the three folders (its README: "Bundled files are not loaded").

`skills_directory` writes an agent's skills as such a directory: every PACT line is kept in
the frontmatter and the three folders are copied, so importing the directory back gives the
same skills, and the report says which of them Pydantic AI does not act on.
`from_skills_directory` reads one into a tree: the Agent Skills keys PACT has no field for
(`license`, `compatibility`, `metadata`, `allowed-tools`, ...) are named and left out, and so
is anything in a skill's folder other than `SKILL.md` and the three.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from .exporting import ExportReport
from .importing import ImportReport, not_the_folders_own, read_text
from .openapi import Imported, NotImported

__all__ = ["from_skills_directory", "skills_directory"]

#: The frontmatter both read.
_BOTH = ("name", "description")
#: The frontmatter PACT reads and Pydantic AI's `Skills` reads past.
_PACT_ONLY = ("use-when", "do-not-use-when", "if-unsure", "costs-about", "available-when")
#: The folders beside `SKILL.md` PACT keeps and the harness never loads.
_FOLDERS = ("references", "scripts", "assets")


def skills_directory(document: Mapping[str, Any], agent: str, root: Path) -> tuple[dict[str, bytes], ExportReport]:
    """The skills agent `agent` uses (in the loaded `document` of the tree at `root`) as a
    Skills directory: `{"<skill>/SKILL.md": bytes, "<skill>/references/<file>": bytes, ...}`."""
    block = (document.get("agents") or {}).get(agent) or {}
    skills = document.get("skills") or {}
    used = [s for s in block.get("uses") or () if s in skills]
    report = ExportReport(kind="a Skills directory", seen=tuple(f"skills.{s}" for s in used))
    files: dict[str, bytes] = {}
    for name in used:
        skill = skills[name]
        where = f"skills.{name}"
        front = {k: skill[k] for k in (*_BOTH, *_PACT_ONLY) if k in skill}
        front.setdefault("name", name)
        text = "---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=100) + "---\n"
        files[f"{name}/SKILL.md"] = (text + str(skill.get("content") or "")).encode("utf-8")
        report.carried[where] = (
            f"`{name}/SKILL.md`: its name, description and body, which `pydantic_ai_harness.Skills(<directory>)` "
            "offers by its description and loads when the model asks"
        )
        if said := [k for k in _PACT_ONLY if k in skill]:
            report.not_carried[f"{where}.frontmatter"] = (
                f"{', '.join(f'`{k}:`' for k in said)}: kept in the frontmatter, which Pydantic AI's Skills reads past; "
                "it offers the skill by its description alone"
            )
        for folder in _FOLDERS:
            payload = skill.get(folder)
            if not isinstance(payload, Mapping):
                continue
            at = root / str(payload.get("$payload") or f"skills/{name}/{folder}")
            for entry in payload.get("files") or ():
                files[f"{name}/{folder}/{entry['$file']}"] = (at / str(entry["$file"])).read_bytes()
            report.not_carried[f"{where}.{folder}"] = (
                f"`{folder}/`: copied beside SKILL.md; Pydantic AI's Skills does not load, list or run them"
            )
    return files, report


def from_skills_directory(folder: Path) -> Imported:
    """Each `<skill>/SKILL.md` directly under `folder` as the tree's `skills/<skill>/`."""
    if not folder.is_dir():
        raise NotImported(f"{folder.name} is not a folder. Fix: give the directory `Skills(...)` reads.")
    report = ImportReport(kind=f"a Skills directory ({folder.name})")
    files: dict[str, str | bytes] = {}
    for path in sorted(folder.iterdir()):
        report.seen += (path.name,)
        if why := not_the_folders_own(path, folder) or not_the_folders_own(path / "SKILL.md", folder):
            report.not_portable[path.name] = why
            continue
        if not (path / "SKILL.md").is_file():
            report.not_portable[path.name] = "not a skill: the harness reads only a folder that holds `SKILL.md`"
            continue
        name = path.name
        front, body = _skill(path / "SKILL.md")
        if front.get("name") not in (None, name):
            raise NotImported(
                f"{name}/SKILL.md calls itself {front['name']!r}, and a skill's name is its folder's. "
                "Fix: rename one to match, as Pydantic AI's Skills requires."
            )
        report.mapped[name] = f"`skills/{name}/SKILL.md`"
        kept = {k: front[k] for k in (*_BOTH, *_PACT_ONLY) if k in front}
        for key in front:
            report.seen += (f"{name}.{key}",)
            if key in kept:
                report.mapped[f"{name}.{key}"] = f"`{key}:`"
            else:
                report.not_portable[f"{name}.{key}"] = (
                    f"`{key}`, which a PACT skill has no field for (the harness reads past it too); left out"
                )
        if not front.get("description"):
            report.still_to_write += (f"`description:` in skills/{name}/SKILL.md",)
        text = "---\n" + yaml.safe_dump(kept, sort_keys=False, allow_unicode=True, width=100) + "---\n" + body
        files[f"skills/{name}/SKILL.md"] = text
        for inside in sorted(path.iterdir()):
            if inside.name == "SKILL.md":
                continue
            where = f"{name}/{inside.name}"
            report.seen += (where,)
            if why := not_the_folders_own(inside, folder):
                report.not_portable[where] = why
            elif inside.is_dir() and inside.name in _FOLDERS:
                report.mapped[where] = f"`skills/{where}/`, kept as files of the skill"
                for file in sorted(inside.rglob("*")):
                    at = f"{name}/{file.relative_to(path).as_posix()}"
                    if why := not_the_folders_own(file, folder):
                        report.seen += (at,)
                        report.not_portable[at] = why
                    elif file.is_file():
                        files[f"skills/{at}"] = _bytes(file, at)
            else:
                report.not_portable[where] = (
                    "beside SKILL.md and in none of `references/`, `scripts/` or `assets/`, which is all a PACT "
                    "skill keeps; left out. Move it into one of them"
                )
    if not report.mapped:
        raise NotImported(f"{folder.name} holds no skill (a folder with a SKILL.md). Fix: give the Skills directory.")
    report.still_to_write += ("`uses:` naming these skills on the agent that reads them",)
    return Imported(api="", files=files, shapes={}, report=report)


def _bytes(path: Path, shown_as: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as trouble:
        raise NotImported(f"{shown_as} could not be read ({trouble.strerror or type(trouble).__name__}). "
                          "Fix: make it a readable file.") from None


def _skill(path: Path) -> tuple[dict[str, Any], str]:
    text = read_text(path, f"{path.parent.name}/SKILL.md")
    found = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", text, re.DOTALL)
    if not found:
        raise NotImported(f"{path.parent.name}/SKILL.md has no frontmatter. Fix: begin it with `---`, `name:`, `description:`, `---`.")
    try:
        front = yaml.safe_load(found.group(1)) or {}
    except yaml.YAMLError as trouble:
        raise NotImported(f"{path.parent.name}/SKILL.md's frontmatter is not YAML ({' '.join(str(trouble).split())}).") from None
    if not isinstance(front, Mapping):
        raise NotImported(f"{path.parent.name}/SKILL.md's frontmatter is not a map of keys.")
    return dict(front), found.group(2)
