"""02P §8.1, 02W §2.16: R16 narrowed to governed run-time composition.

`teamwork.may-start:` lets an agent bring others in while it runs, and only
inside bounds a person reviewed: `limits.starts-at-most:` and
`limits.nests-at-most:` (which `pact check` requires beside it, WF-33), the
request's one pot, and a narrowed agent's `uses:` never wider than its
starter's. The run-time pieces a runtime needs to hold those bounds the way PACT
reads them live here, beside the join they extend:

* the two figures and the `may-start:` words, read from the document;
* `granted`, the one place a join's share becomes a member's ceiling;
* `ask_team(..., failures=)`, so a runtime's own control flow (a park for a
  person, a stopped process) is never written into the team's outcome as one
  member's failure;
* the refusals, in the words a model is told.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.delegation import (  # noqa: E402
    ANSWERED,
    CANCELLED,
    MayStart,
    Teamwork,
    ask_team,
    asked_too_often,
    Answer,
    Grant,
    Pool,
    Divides,
    beyond_its_starter,
    carried_on_without,
    granted,
    refused_start,
    request_for,
)
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import Limits  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def _doc(limits: dict | None = None, teamwork: dict | None = None) -> dict:
    agent = {"description": "Brings helpers in.", "instructions": "Do it."}
    if limits is not None:
        agent["limits"] = limits
    if teamwork is not None:
        agent["teamwork"] = teamwork
    return {"agents": {"orchestrator": agent, "helper": {"description": "Helps."}}}


def test_may_start_and_its_two_bounds_are_read_from_the_document() -> None:
    doc = _doc(
        limits={"starts-at-most": 20, "nests-at-most": 2, "when-it-runs-out": "stop-and-say-so"},
        teamwork={"may-start": ["catalogue", "narrowed-new"]},
    )
    tw = Teamwork.from_document(doc, "orchestrator")
    assert tw.may_start == (MayStart.CATALOGUE, MayStart.NARROWED_NEW)
    limits = Limits.from_mapping(doc["agents"]["orchestrator"]["limits"])
    assert (limits.starts_at_most, limits.nests_at_most) == (20, 2)
    assert Teamwork().may_start == (), "nobody beyond `team:` unless the author says so"


def test_a_word_teamwork_does_not_know_under_may_start_is_refused() -> None:
    from pact_adapters.delegation import BadTeamwork

    with pytest.raises(BadTeamwork, match="catalogue, narrowed-new"):
        Teamwork.from_document(_doc(teamwork={"may-start": ["anyone"]}), "orchestrator")


def test_a_grant_binds_the_smaller_figure_and_an_unmetered_pot_changes_nothing() -> None:
    doc = _doc(limits={"cost-per-request-under": "0.05 USD", "when-it-runs-out": "stop-and-say-so"})
    member = AgentSpec.from_document(doc, "orchestrator")
    assert granted(member, 0.02).limits.cost_per_request_under == pytest.approx(0.02)
    assert granted(member, 0.02).slo.cost_per_request_under == pytest.approx(0.02)
    assert granted(member, 0.50).limits.cost_per_request_under == pytest.approx(0.05), (
        "a share never raises a ceiling the member set for itself"
    )
    assert granted(member, float("inf")) is member
    open_member = AgentSpec.from_document(_doc(), "helper")
    assert granted(open_member, 0.03).limits.cost_per_request_under == pytest.approx(0.03)
    assert granted(open_member, 0.03, "USD").limits.cost_currency == "USD", "the pot's currency"
    assert granted(member, 0.02, "EUR").limits.cost_currency == "USD", "a member's own line wins"


def test_an_exception_that_is_not_a_failure_leaves_the_join_and_stops_the_others() -> None:
    """A runtime parking the whole run for a person is not one member's answer."""

    class Parked(Exception):
        pass

    stopped: list[str] = []

    async def ask(grant):  # noqa: ANN001
        if grant.member == "a":
            await asyncio.sleep(0)
            raise Parked("a person must answer first")
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            stopped.append(grant.member)
            raise
        return "late"

    class MemberFailed(Exception):
        pass

    with pytest.raises(Parked):
        asyncio.run(ask_team(["a", "b"], ask, Teamwork(), failures=(MemberFailed,)))
    assert stopped == ["b"]


def test_a_failure_named_by_the_runtime_is_still_data() -> None:
    class MemberFailed(Exception):
        pass

    async def ask(grant):  # noqa: ANN001
        if grant.member == "a":
            raise MemberFailed("down")
        return "fine"

    handoff = asyncio.run(ask_team(["a", "b"], ask, Teamwork(), failures=(MemberFailed,)))
    assert [a.state for a in handoff.answers] == ["failed", ANSWERED]
    assert handoff.said("a") == "error: a could not answer: down"


def test_the_default_keeps_every_exception_a_failure() -> None:
    async def ask(grant):  # noqa: ANN001
        if grant.member == "a":
            raise RuntimeError("down")
        await asyncio.sleep(0.01)
        return "fine"

    handoff = asyncio.run(ask_team(["a", "b"], ask, Teamwork()))
    assert handoff.answers[0].state == "failed" and handoff.answers[1].state in (ANSWERED, CANCELLED)


def test_a_start_is_refused_past_either_bound_in_words_a_model_can_act_on() -> None:
    assert refused_start("orchestrator", started=1, starts_at_most=20, nests_left=2) == ""
    assert refused_start("orchestrator", started=0, starts_at_most=None, nests_left=None) == ""
    said = refused_start("orchestrator", started=20, starts_at_most=20, nests_left=2)
    assert "`starts-at-most: 20` is spent" in said and "20 agent(s)" in said
    deep = refused_start("helper", started=1, starts_at_most=20, nests_left=0)
    assert "'helper' may not bring anyone in" in deep and "`nests-at-most:`" in deep


def test_a_narrowed_agent_may_name_only_what_its_starter_uses() -> None:
    assert beyond_its_starter("orchestrator", ["sharepoint-read", "arcgis-read"], ["sharepoint-read"]) == ""
    said = beyond_its_starter("orchestrator", ["sharepoint-read"], ["munis-write", "sharepoint-read"])
    assert "'munis-write' is not among them" in said and "sharepoint-read" in said


def test_asks_itself_at_most_is_said_in_one_place() -> None:
    assert asked_too_often("reviewer", 2) == (
        "'reviewer' has already been put to work 2 time(s) on this request — "
        "`asks-itself-at-most: 2` is spent."
    )


@pytest.mark.skipif(not (REPO / "target").exists() and shutil.which("pact") is None, reason="no loader")
def test_pact_check_refuses_may_start_without_both_bounds(tmp_path: Path) -> None:
    from pact_adapters.loader import pact_binary

    (tmp_path / "agents" / "orchestrator").mkdir(parents=True)
    (tmp_path / "workspace.yaml").write_text("name: w\ndescription: t\nowner: t\nallow-egress: []\n")
    (tmp_path / "agents" / "orchestrator" / "agent.yaml").write_text(
        "description: Brings helpers in.\ninstructions: Do it.\n"
        "teamwork:\n  may-start: [narrowed-new]\n"
        "limits:\n  starts-at-most: 3\n  when-it-runs-out: stop-and-say-so\n"
    )
    out = subprocess.run([str(pact_binary()), "check", str(tmp_path)], capture_output=True, text=True)
    assert out.returncode != 0
    assert "loader/may-start-without-its-bounds" in out.stdout + out.stderr


def test_what_a_member_is_asked_and_what_stands_in_for_one_a_person_let_go() -> None:
    """Said once, here, so a runtime other than the harness hands a member the same words."""
    pool = Pool(0.0, Divides.EVENLY, ["a", "b"])
    first = Grant("b", pool, "check it")
    assert request_for(first) == "check it"
    later = Grant("b", pool, "check it", so_far=(Answer("a", text="it is fine", ok=True, state=ANSWERED),))
    assert request_for(later) == "a said: it is fine\n\ncheck it"
    assert carried_on_without("fraud-checker") == (
        "(no answer: a person said to carry on without fraud-checker)"
    )


def test_the_tree_that_writes_every_phase_1_field_reaches_each_reader() -> None:
    """`may-start:` and its bounds were written by no tree: every test above
    builds the document in Python. `tests/trees/a-desk-that-writes-every-phase-1-field`
    writes each Phase 1 field in a file, and this reads each through the real
    loader and the reader a runtime uses."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from trees import pact, shown

    from pact_adapters.holes import Hole

    root = REPO / "tests" / "trees" / "a-desk-that-writes-every-phase-1-field"
    checked = pact("check", str(root), "--deny-warnings")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    desk = AgentSpec.from_document(shown(root), "desk")
    assert desk.teamwork.may_start == (MayStart.CATALOGUE, MayStart.NARROWED_NEW)
    assert (desk.limits.starts_at_most, desk.limits.nests_at_most) == (4, 1)
    assert [r.kind for r in desk.checked_by] == ["must-contain", "must-call-before"]
    assert desk.checks_at_most == 3
    assert desk.holes == (Hole("run-inputs", "shop"),) and set(desk.run_inputs) == {"shop"}
    (orders,) = desk.tools
    assert orders.answers_with == {
        "look-up": {"total": "money", "status": "one of delivered, in-transit, lost"}
    }
