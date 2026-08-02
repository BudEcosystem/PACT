"""C8 — a workspace nobody can write to still runs, and says what it lost.

`.pact/` is the derived area, and both halves of it — a `watch:` record and the
learning ledgers — were written straight into the workspace. So a read-only
checkout could not run a watch at all, and did not degrade: `base.mkdir` raised
inside a bus handler, which meant **an observability feature took down the run it
was only observing**.

Three properties here, and the second is the one that matters:

* `$PACT_DERIVED_DIR` redirects the whole derived area, so a read-only tree is
  run by pointing it somewhere writable rather than by copying the tree;
* a workspace that can be written to **nowhere** still runs, and reports its
  watches as unwritten rather than raising;
* a workspace that asked for no watch acquires no `.pact/` — D2 says the derived
  area is disposable, not that it appears uninvited.

Where derived output lands is a **deployment fact**, decided by whoever runs
this, which is why it is an environment variable and not a field. A workspace
that named its own would stop being runnable in two places — the same reason
`invocation.url` is left empty when exporting an `AgentRecord`.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.watches import DERIVED_DIR, UNDER, can_be_written, derived_area  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    root = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".pact"))
    return root


def _spec(root: Path) -> AgentSpec:
    out = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return AgentSpec.from_document(json.loads(out.stdout), "refund-desk", source=root)


def _go(spec: AgentSpec) -> Any:
    """A run that actually calls a tool.

    The example's watch is `when: step.tool.completed`, so a script that only
    answers records nothing and every assertion about the record would pass for
    the wrong reason — which is how the first version of this file was written.
    """
    script = Script([
        Turn("Looking it up.", (ToolCall("zendesk", {"ticket": "T-1"}),)),
        Turn("done"),
    ])
    return asyncio.run(
        run(spec, ReferenceTransport(script), "hello", {"zendesk": lambda a: "a ticket"})
    )


# ─────────────────────────────────────────── where the records go


def test_the_derived_area_can_be_pointed_somewhere_else(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fix for a read-only tree: point the area somewhere writable rather
    than copy the tree."""
    elsewhere = tmp_path / "somewhere-writable"
    monkeypatch.setenv(DERIVED_DIR, str(elsewhere))

    out = _go(_spec(workspace))
    assert out.unwatched == (), out.unwatched
    assert (elsewhere / UNDER / "tool-calls.jsonl").exists(), (
        f"the record did not land in $PACT_DERIVED_DIR: "
        f"{sorted(elsewhere.rglob('*')) if elsewhere.exists() else 'nothing there'}"
    )
    assert not (workspace / ".pact").exists(), (
        "the record was ALSO written into the workspace, so pointing the area "
        "elsewhere bought nothing"
    )


def test_without_the_override_it_lands_beside_the_workspace(workspace: Path) -> None:
    """The default is unchanged. A redirect nobody set must behave exactly as
    before, or this is a behaviour change dressed as a fix."""
    assert DERIVED_DIR not in os.environ
    out = _go(_spec(workspace))
    assert out.unwatched == ()
    assert (workspace / UNDER / "tool-calls.jsonl").exists()


# ────────────────────────── a tree nobody can write to, at all


def test_a_read_only_workspace_runs_and_says_its_watch_wrote_nothing(
    workspace: Path,
) -> None:
    """The property that matters. Watching must never be the reason a run fails:
    it changes nothing about what the agent does, and a record is worth less than
    the work it was recording."""
    spec = _spec(workspace)
    mode = workspace.stat().st_mode
    workspace.chmod(mode & ~stat.S_IWUSR)
    try:
        out = _go(spec)          # must not raise
    finally:
        workspace.chmod(mode)

    assert out.halted == "final", out.halted
    assert out.output, "the run produced no answer, so watching did take it down"
    assert "tool-calls" in " ".join(out.unwatched), (
        f"the run survived and said nothing about the record it could not keep: "
        f"{out.unwatched}"
    )


def test_a_learning_ledger_that_cannot_be_written_does_not_fail_the_cycle(
    workspace: Path,
) -> None:
    """The other half of `.pact/`. A learning cycle that fails because it could
    not write down that it happened has turned a bookkeeping problem into a run
    failure."""
    from pact_adapters.learning import MonthlySpend, Proposal, Refusals

    mode = workspace.stat().st_mode
    workspace.chmod(mode & ~stat.S_IWUSR)
    try:
        month = MonthlySpend.at(workspace)
        month.add(1.5, 1)          # must not raise
        assert month.money == 1.5, "the in-process total still has to be right"

        refused = Refusals.at(workspace)
        p = Proposal("instructions", "a", "b")
        refused.add(p, "did not improve")   # must not raise
        # In memory first: losing the record across processes is a cost, losing
        # it inside one would mean scoring the same proposal twice in a cycle.
        assert refused.why(p) is not None
    finally:
        workspace.chmod(mode)


# ───────────────────── and nothing appears where nothing was asked for


def test_a_workspace_that_declared_no_watch_acquires_no_derived_area(
    workspace: Path,
) -> None:
    """The regression this change first caused. Probing for writability CREATES
    the area, and a workspace that declared no `watch:` must not acquire a
    `.pact/` for having been run — D2 says the derived area is disposable, not
    that it appears uninvited."""
    shutil.rmtree(workspace / "watch")
    out = _go(_spec(workspace))
    assert out.halted == "final"
    assert not (workspace / ".pact").exists(), (
        "a workspace that asked for nothing got something"
    )


def test_the_writability_probe_answers_honestly(tmp_path: Path) -> None:
    """Asked once, when the watches are attached, rather than discovered per
    line: a run that reports its watches unwritten from the start is one somebody
    can act on, and one that discovers it on the fortieth event has already said
    nothing about the first thirty-nine."""
    assert can_be_written(None) is False
    assert can_be_written(tmp_path / "fresh" / "watch") is True

    locked = tmp_path / "locked"
    locked.mkdir()
    mode = locked.stat().st_mode
    locked.chmod(mode & ~stat.S_IWUSR)
    try:
        assert can_be_written(locked / UNDER) is False
    finally:
        locked.chmod(mode)

    # And the probe leaves nothing behind that it did not need.
    area = tmp_path / "fresh" / "watch"
    assert not (area / ".writable").exists()


def test_both_halves_of_the_derived_area_agree_on_where_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`watch/` and `learning/` are both under `.pact/`, and a redirect that
    moved one and not the other would put a workspace's records in two places."""
    from pact_adapters.learning import Proposal, Refusals

    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv(DERIVED_DIR, str(elsewhere))
    assert derived_area(tmp_path).is_relative_to(elsewhere)

    refused = Refusals.at(tmp_path)
    refused.add(Proposal("instructions", "a", "b"), "because")
    assert (elsewhere / ".pact" / "learning" / "refused.jsonl").exists(), (
        f"the learning ledger ignored $PACT_DERIVED_DIR: "
        f"{sorted(p for p in tmp_path.rglob('*.jsonl'))}"
    )
