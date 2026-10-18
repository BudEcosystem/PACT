"""Skills both ways as a `pydantic-ai-harness` Skills directory (02P X5, `pydantic_ai_skills`).

* **carried**: a tree's skills written as a Skills directory and read back into another tree
  are the same skills, every PACT line, the body and the files beside it;
* **Pydantic AI's own `Skills` reads what is written**: run on the directory, it offers each
  skill by its name and description, and the export says which PACT lines it reads past;
* **a directory from elsewhere**: an Agent Skills key PACT has no field for, and a file in no
  folder PACT keeps, are each named and left out; a skill whose name is not its folder's is
  refused, as the harness refuses it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.openapi import NotImported, write_into  # noqa: E402
from pact_adapters.pydantic_ai_skills import from_skills_directory, skills_directory  # noqa: E402
from trees import shown, write  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DESK = REPO / "examples" / "refund-desk"


def _written(files: dict[str, bytes], at: Path) -> Path:
    for name, body in files.items():
        (at / name).parent.mkdir(parents=True, exist_ok=True)
        (at / name).write_bytes(body)
    return at


def test_a_trees_skills_go_out_as_a_directory_and_come_back_the_same(tmp_path: Path) -> None:
    files, report = skills_directory(shown(DESK), "refund-desk", DESK)
    assert report.silent_losses == ()
    assert sorted(files) == [
        "refund-policy/SKILL.md",
        "refund-policy/references/window-table.md",
        "refund-policy/scripts/check_window.py",
    ]
    assert set(report.not_carried) == {
        "skills.refund-policy.frontmatter", "skills.refund-policy.references", "skills.refund-policy.scripts",
    }
    imported = from_skills_directory(_written(files, tmp_path / "skills"))
    assert imported.report.silent_drops == () and imported.report.not_portable == {}, imported.report.in_words()
    root = write(tmp_path / "tree", {"workspace.yaml": "name: back\nallow-egress: []\n"})
    write_into(root, imported)
    assert shown(root)["skills"] == shown(DESK)["skills"]


def test_pydantic_ais_own_skills_offers_what_is_written(tmp_path: Path) -> None:
    """The directory as the harness's `Skills` reads it: the skill by name and description, the
    PACT lines (`use-when:` and the rest) read past, `load_capability` the one tool."""
    harness = pytest.importorskip("pydantic_ai_harness")
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel
    from pydantic_ai.workspaces import LocalWorkspaceBackend

    files, _ = skills_directory(shown(DESK), "refund-desk", DESK)
    at = _written(files, tmp_path / "skills")
    seen: dict[str, object] = {}

    def respond(messages: list, info: AgentInfo) -> ModelResponse:
        seen["tools"] = [t.name for t in info.function_tools]
        seen["told"] = messages[-1].instructions
        return ModelResponse(parts=[TextPart("ok")])

    skills = harness.Skills(".", workspace=LocalWorkspaceBackend(str(at)))
    asyncio.run(Agent(FunctionModel(respond), capabilities=[skills]).run("go"))
    assert seen["tools"] == ["load_capability"]
    assert "- refund-policy: How to decide a refund, step by step." in str(seen["told"])


def test_what_a_pact_skill_has_no_field_for_is_named_and_left_out(tmp_path: Path) -> None:
    at = write(
        tmp_path / "skills",
        {
            "triage/SKILL.md": "---\nname: triage\ndescription: Sort a ticket.\nlicense: MIT\n"
            "allowed-tools: Read\n---\nSort it.\n",
            "triage/references/codes.md": "| code |\n",
            "triage/NOTES.txt": "scratch\n",
            "README.md": "a library\n",
        },
    )
    imported = from_skills_directory(at)
    assert imported.report.silent_drops == ()
    assert set(imported.report.not_portable) == {"triage.license", "triage.allowed-tools", "triage/NOTES.txt", "README.md"}
    assert set(imported.files) == {"skills/triage/SKILL.md", "skills/triage/references/codes.md"}
    assert "license" not in str(imported.files["skills/triage/SKILL.md"])
    root = write(tmp_path / "tree", {"workspace.yaml": "name: back\nallow-egress: []\n"})
    write_into(root, imported)
    assert shown(root)["skills"]["triage"]["content"] == "Sort it."


def test_a_skill_named_unlike_its_folder_is_refused(tmp_path: Path) -> None:
    at = write(tmp_path / "skills", {"triage/SKILL.md": "---\nname: sorting\ndescription: Sort.\n---\nSort.\n"})
    with pytest.raises(NotImported, match="a skill's name is its folder's"):
        from_skills_directory(at)


def test_a_link_or_a_hidden_file_in_a_skill_is_never_read(tmp_path: Path) -> None:
    """A reference that is a link out of the folder, and a hidden file, are named and left out:
    neither's bytes reach the tree, which the MCP tools would then read back."""
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"TOP SECRET\n")
    folder = write(tmp_path / "skills", {
        "x/SKILL.md": "---\nname: x\ndescription: Does x.\n---\nDo x.\n",
        "x/references/kept.md": "Kept.\n",
        "x/references/.hidden": "TOP SECRET\n",
    })
    (folder / "x" / "references" / "notes.md").symlink_to(outside)
    imported = from_skills_directory(folder)
    assert set(imported.files) == {"skills/x/SKILL.md", "skills/x/references/kept.md"}
    assert not any(b"TOP SECRET" in (b if isinstance(b, bytes) else b.encode()) for b in imported.files.values())
    assert {"x/references/notes.md", "x/references/.hidden"} <= set(imported.report.not_portable)
    assert imported.report.silent_drops == ()


def test_a_skill_that_is_not_utf8_is_refused_said(tmp_path: Path) -> None:
    (tmp_path / "skills" / "x").mkdir(parents=True)
    (tmp_path / "skills" / "x" / "SKILL.md").write_bytes("---\nname: x\n---\nDo x.\n".encode("utf-16"))
    with pytest.raises(NotImported, match="x/SKILL.md is not UTF-8 text"):
        from_skills_directory(tmp_path / "skills")
