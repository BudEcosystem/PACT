"""Learning on a workspace written in the PACT language (docs/99 §4, law 8).

A learning cycle proposes an edit to one agent, and the proposal is held to
`pact check` before it is scored. For a folder that works by copying the tree
and writing the new instructions where they live. In a `.pact` file they live
nowhere that code looked: nothing was written, the author's OWN tree was
checked, and the answer was reported as the proposal's — so on a workspace
written in the language and carrying files, a change that breaks a rule passed.

MUTATION: take `as_a_folder(root)` out of
`checking._write_instructions`. `test_a_change_that_breaks_a_rule…` then gets
`Uncheckable` in place of the checker's own words; take the final `raise` out
as well and it gets `[]` — the broken proposal passes, which is the bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.checking import check_agent_field  # noqa: E402
from pact_adapters.exploding import CarriesPayloads, explode  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.learning import Learner  # noqa: E402
from trees import shown  # noqa: E402

import pytest  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
#: One `.pact` file at the top of a folder, beside documents that stay files.
STAFF = REPO / "examples" / "language" / "staff-desk"
#: Four `.pact` files and nothing else.
HELP = REPO / "examples" / "language" / "help-centre"

BROKEN = "Answer the member of staff, who is {{run-inputs.nobody-declared-this}}."
SOUND = "Answer from the staff handbook. Say which page you read it on."


def test_the_tree_this_is_about_carries_files_the_document_only_points_at(tmp_path) -> None:
    # Otherwise the change goes through the document and never reaches the
    # path this file is about.
    with pytest.raises(CarriesPayloads):
        explode(shown(STAFF), tmp_path / "tree")
    assert list(STAFF.glob("*.pact")) and not (STAFF / "agents").exists()


def test_a_sound_change_passes() -> None:
    assert check_agent_field(shown(STAFF), "helpdesk", "instructions", SOUND, source=STAFF) == []


def test_a_change_that_breaks_a_rule_is_refused_in_the_checkers_own_words() -> None:
    refused = check_agent_field(shown(STAFF), "helpdesk", "instructions", BROKEN, source=STAFF)
    assert refused and any("nobody-declared-this" in r for r in refused), refused


def test_the_authors_own_files_are_not_touched() -> None:
    before = {p: p.read_bytes() for p in STAFF.rglob("*") if p.is_file()}
    check_agent_field(shown(STAFF), "helpdesk", "instructions", BROKEN, source=STAFF)
    assert {p: p.read_bytes() for p in STAFF.rglob("*") if p.is_file()} == before


def test_the_copy_that_is_changed_says_what_the_authors_tree_says(tmp_path) -> None:
    # The step everything above rests on: the tree is copied, and the copy is
    # rewritten as the folder of YAML it stands for — documents left where
    # they are — BEFORE one field of it is changed. If that rewriting lost or
    # moved anything, the checker would be judging a different workspace.
    import shutil

    from pact_adapters import checking

    copy = tmp_path / "staff-desk"
    shutil.copytree(STAFF, copy)
    assert checking.as_a_folder(copy) is True
    assert checking.as_a_folder(copy) is False, "a folder already"
    assert not list(copy.glob("*.pact")), "it is a folder of YAML now"
    assert (copy / "agents" / "helpdesk" / "instructions.md").exists()
    assert (copy / "knowledge" / "staff-handbook" / "documents" / "leave.md").exists()
    assert shown(copy) == shown(STAFF)


def test_a_folder_with_a_runtime_area_is_not_taken_for_one_written_in_the_language(tmp_path) -> None:
    # `.pact/` is a directory every workspace that has run a learning cycle
    # has, and its name ends in `.pact`. Found by the gate: nine tests on
    # `examples/refund-desk` failed with `IsADirectoryError` the first time
    # this code met a checkout that had been used.
    import shutil

    desk = REPO / "examples" / "refund-desk"
    copy = tmp_path / "refund-desk"
    shutil.copytree(desk, copy, ignore=shutil.ignore_patterns(".pact"))
    (copy / ".pact" / "learning").mkdir(parents=True)
    (copy / ".pact" / "learning" / "spend.jsonl").write_text("")
    doc = shown(copy)
    assert check_agent_field(doc, "refund-desk", "instructions", "Decide the refund. Be brief.", source=copy) == []
    refused = check_agent_field(doc, "refund-desk", "instructions", BROKEN, source=copy)
    assert refused and any("nobody-declared-this" in r for r in refused), refused


def test_a_workspace_in_several_files_is_held_the_same_way() -> None:
    # No files to carry, so this one goes through the document — and an agent
    # made from a pattern (`based on desk with …`) takes the change as its own.
    doc = shown(HELP)
    assert check_agent_field(doc, "billing-desk", "instructions", "Answer billing questions, briefly.", source=HELP) == []
    refused = check_agent_field(doc, "billing-desk", "instructions", BROKEN, source=HELP)
    assert refused and any("nobody-declared-this" in r for r in refused), refused


def test_what_the_workspace_says_about_learning_reaches_the_learner() -> None:
    # `learning` / `enabled: propose-only` in `help-centre.pact`.
    doc = shown(HELP)
    spec = AgentSpec.from_document(doc, "billing-desk", source=HELP)
    learner = Learner.from_document(doc, spec, tools={})
    assert learner.permissions.may_apply_without_a_person() != "", (
        "propose-only: nothing applies itself, and the learner says why"
    )
