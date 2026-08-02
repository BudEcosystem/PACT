"""A stage that narrows to a written procedure rather than to a tool.

`agent.uses:` draws from tools AND skills. `stage.may-use:` narrows what that
agent already has, so it has to draw from the same two sets — and for a round it
did not: `names: [tools, skills]` against `names: [tools, agents]`. The two lists
overlapped on tools and disagreed on both other sets, which meant there was a
thing an agent may use that no stage of its loop could mention.

It bit exactly where it was most visible. `examples/refund-desk/loops/careful.yaml`
exists to put one stage between the looking-up and the customer, and its own
header says what that stage is for: *"say which rule in the refund policy allows
this decision… but it cannot reach the payment system from there."* The rule it
must read is `skills/refund-policy/SKILL.md`, and `may-use:` could not say so.
Writing it produced a diagnostic telling the author to create
`tools/refund-policy.yaml` — a second copy of the policy, under a kind nothing
reads it as. `crates/pact-cli/tests/a_name_the_workspace_already_has.rs` holds
the diagnostic half; this module holds the executing half.

**What this module does NOT claim.** Naming a skill here does not yet change
what a model is shown, because no skill reaches any run at all today:
`AgentSpec.from_document` builds `tools` from `doc["tools"]` filtered by `uses:`,
and a skill named there matches nothing. The guarantee under test is narrower and
is the one that had to exist before the specification could be widened at all:
once `may-use:` may name a skill, a stage naming one the agent HAS must not be
refused, and a stage naming one it has NOT must still be refused before the first
model call. Without this, widening the specification would only have moved the
refusal from `pact check` into Python — the exact "loads clean, fails later, in
another language" failure `names:` was added to end.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.loops import Loop, LoopError  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"

AGENT = "refund-desk"

#: The stage the example's own comment says must be able to read the policy
#: while being denied the money. Found by what it DOES rather than by its name,
#: the way `test_worked_example_loop.py` finds it, so renaming it does not
#: quietly retire this.
CHECKS_ITS_WORK = "check-its-work"


def loaded(tree: Path) -> dict[str, Any]:
    """A tree, through the real Rust loader.

    The same door every other adapter test uses (invariant P-1: adapters consume
    the loaded document and never re-implement the Expansion Rule). `pact show`
    loads; it does not validate — which is what lets this module read an author's
    `may-use:` line before `spec/schema.yaml` has been widened to accept it.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(tree)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def a_tree_whose_checking_stage_reads_the_policy(tmp_path: Path, uses_it: bool = True) -> Path:
    """The worked example with the one line an author would add.

    A copy rather than the example itself, because `spec/schema.yaml` refuses the
    line until the specification is widened (the change is described in this
    round's `needs_wiring`, and `a_stage_narrows_what_the_agent_has_so_it_draws_from_the_same_sets`
    fails until it lands). Everything else in the tree is the author's, unedited.

    `uses_it=False` also removes the skill from the agent's own `uses:` line,
    which is the mistake the refusal below exists to catch.
    """
    dst = tmp_path / "rd"
    shutil.copytree(EXAMPLE, dst)

    loop = dst / "loops" / "careful.yaml"
    text = loop.read_text()
    marker = "    may-use:\n      - zendesk\n"
    assert marker in text, (
        "the example's checking stage no longer narrows to `zendesk` alone, so this "
        "module would be testing a line it wrote rather than one an author did. "
        "fix: update the marker in test_narrowing_a_stage_to_a_skill.py"
    )
    loop.write_text(text.replace(marker, marker + "      - refund-policy\n"))

    if not uses_it:
        agent = dst / "agents" / AGENT / "agent.yaml"
        a = agent.read_text()
        assert "  - refund-policy\n" in a
        agent.write_text(a.replace("  - refund-policy\n", "", 1))
    return dst


def what_the_agent_has(doc: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The two sets `uses:` draws from, split the way the harness will pass them.

    Derived here rather than read off an `AgentSpec` because `ir.py` is a shared
    file this round: the one-line change that gives `AgentSpec` a `skills` field,
    and the one that hands it to `check_against`, are both in `needs_wiring`.
    Everything the split is computed FROM is the author's — the agent's own
    `uses:` line, the workspace's own `tools:` and `skills:` sections.
    """
    agent = doc["agents"][AGENT]
    uses = agent.get("uses") or []
    tools = doc.get("tools") or {}
    skills = doc.get("skills") or {}
    return (
        tuple(u for u in uses if u in tools) + tuple(agent.get("team") or {}),
        tuple(u for u in uses if u in skills),
    )


def the_checking_stage(doc: dict[str, Any]) -> str:
    steps = doc["loops"]["careful"]["steps"]
    found = [n for n, s in steps.items() if s.get("does") == CHECKS_ITS_WORK]
    assert len(found) == 1, f"expected one {CHECKS_ITS_WORK!r} stage, found {found}"
    return found[0]


def test_a_stage_may_narrow_to_a_skill_the_agent_already_uses(tmp_path: Path) -> None:
    doc = loaded(a_tree_whose_checking_stage_reads_the_policy(tmp_path))
    loop = Loop.resolve(doc, doc["agents"][AGENT].get("loop", ""))
    tools, skills = what_the_agent_has(doc)

    assert "refund-policy" in skills, (
        "the refund desk no longer lists the written policy on its `uses:` line, so "
        "there is nothing for a stage to narrow TO"
    )
    stage = loop.phase(the_checking_stage(doc))
    assert stage.may_use is not None and "refund-policy" in stage.may_use

    # The line under test: a name that is a skill rather than a tool must not be
    # read as a typo. Before `check_against` was told about skills this raised,
    # and the author's file was correct — the refusal would have been PACT's.
    loop.check_against(tools, skills)


def test_a_stage_that_narrows_to_a_skill_the_agent_does_not_have_is_refused_before_any_model_call(
    tmp_path: Path,
) -> None:
    # The other half, and the one that makes the first half a narrowing rather
    # than a hole: `may-use:` may only take away. A stage naming a skill its
    # agent never listed is a mistake whichever kind the name turns out to be,
    # and it has to fail at the start of the run rather than in whichever branch
    # happens to enter that stage.
    doc = loaded(a_tree_whose_checking_stage_reads_the_policy(tmp_path, uses_it=False))
    loop = Loop.resolve(doc, doc["agents"][AGENT].get("loop", ""))
    tools, skills = what_the_agent_has(doc)
    assert "refund-policy" not in skills

    with pytest.raises(LoopError) as raised:
        loop.check_against(tools, skills)
    said = str(raised.value)
    assert "refund-policy" in said, said
    assert "`uses:`" in said, f"the fix has to name the line that would accept it: {said}"


def test_narrowing_to_a_skill_leaves_that_stage_no_tools_at_all(tmp_path: Path) -> None:
    # What "the policy skill, and only that" has to mean on the tool side, and
    # the reason a skill is deliberately NOT folded into the tool list: a stage
    # whose `may-use:` names nothing but a written procedure can read it and
    # reach nothing. Eve cannot express this at all — its tool set is resolved
    # once per run, so its checking step sees the payment tool.
    doc = loaded(a_tree_whose_checking_stage_reads_the_policy(tmp_path))
    loop = Loop.resolve(doc, doc["agents"][AGENT].get("loop", ""))
    tools, _ = what_the_agent_has(doc)

    stage = loop.phase(the_checking_stage(doc))
    offered = stage.tools_offered(tools)
    assert "refund-policy" not in offered, (
        "a skill is a document to read, not something to call; offering it as a tool "
        "would hand the model a name nothing can answer"
    )
    assert "payments" not in offered, (
        "the stage whose whole purpose is doubt must not be the stage that can spend "
        "the money — that is what `loops/careful.yaml` exists to demonstrate"
    )
    assert "zendesk" in offered, "the one tool the stage does name must survive"
