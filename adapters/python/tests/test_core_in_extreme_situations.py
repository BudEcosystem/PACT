"""PACT Core in the situations that break a system which only works on the
happy path (`docs/100` §12).

Each test here is one of the plan's scenarios, run on the reference session
with scripted models and tools. What is asserted is the rule the scenario
exists to stress. The scenarios that need a real model are in
`test_core_runs_on_a_live_model.py`; the ones that need a second runtime, or
a run that resumes after waiting for a person, are listed in `docs/100` §17 as
not run.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.cells import act_by_a_cell  # noqa: E402
from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.session import MOST_BYTES, Session, depends_on  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DESK = REPO / "examples/core/refund-desk"

DECIDE_ALL = """\
flow decide-all(orders: list of text) gives summary: text, verdicts: list of verdict
  description: Decide every order in a list, and sum up. Revision {n}.
  each = for each item in input.orders
    limits:
      items-at-most: 50
      at-once-at-most: 5
      when-it-runs-out: stop-and-say-so
    one = desk.decide-one(order: item)
  told = desk.summarise(verdicts: each.items)
  answer with summary: told.summary, verdicts: each.items
"""


@pytest.fixture()
def session():
    opened = Session.open(DESK)
    yield opened
    opened.close()


def answers(name: str, given: dict[str, Any]) -> dict[str, Any]:
    return {"summary": "done"} if name == "desk-summarise" else {"decision": "approved", "reason": "broken"}


# ── 1. the runbook edited mid-incident ───────────────────────────────────────


def test_forty_runs_are_open_while_the_flow_is_rewritten_three_times(session: Session) -> None:
    began: dict[int, str] = {}
    revisions: list[str] = [session.version]

    async def incident() -> list[Any]:
        async def one(i: int) -> Any:
            # A run is handed the workspace as it is when it starts.
            document, began[i] = session.document, session.version
            flow = WorkflowSpec.from_workflow(document, "decide-all")

            async def judge(name: str, given: dict[str, Any]) -> dict[str, Any]:
                await asyncio.sleep(0.001 * (i % 7))
                return answers(name, given)

            out = await run_workflow(
                flow, {"orders": [f"o{i}-{k}" for k in range(3)]},
                Callers(tool=lambda t, a, g: {"facts": "broken"}, agent=judge), document=document,
            )
            return document, out

        async def rewrite() -> None:
            for n in (1, 2, 3):
                await asyncio.sleep(0.004)
                got = await asyncio.to_thread(session.change, DECIDE_ALL.format(n=n))
                assert got.admitted, got.said
                revisions.append(got.version)

        async def staggered(i: int) -> Any:
            await asyncio.sleep(0.0005 * i)
            return await one(i)

        results, _ = await asyncio.gather(
            asyncio.gather(*(staggered(i) for i in range(40))), rewrite()
        )
        return results

    results = asyncio.run(incident())
    assert len(revisions) == 4 and len(set(revisions)) == 4
    for i, (document, out) in enumerate(results):
        # Every run finished, as the flow was written in the version it began with.
        assert out.halted == "final", (i, out.said)
        assert began[i] in revisions
        assert len(out.answer["verdicts"]) == 3
        said = document["workflows"]["decide-all"]["description"]
        assert out.trace[0] == "each" and "Revision" in said or began[i] == revisions[0]
    # And the session ended on the last rewrite.
    assert session.document["workflows"]["decide-all"]["description"].endswith("Revision 3.")


# ── 3. the agent that raises its own ceiling ─────────────────────────────────


@pytest.mark.parametrize("attempt", [
    # A helper that may take more steps than its writer.
    "agent mine(order: text) gives view: text\n  description: Me, with more room.\n  instructions: Carry on.\n"
    "  uses orders\n  at most 60 steps\n  when it runs out: stop and say so\n\n"
    "one = mine(order: input.order)\nanswer with summary: one.view\n",
    # A helper that says nothing about steps, where its writer has a ceiling.
    "agent mine(order: text) gives view: text\n  description: Me, unbounded.\n  instructions: Carry on.\n  uses orders\n\n"
    "one = mine(order: input.order)\nanswer with summary: one.view\n",
    # Itself, written again with a higher figure.
    "agent desk-summarise\n  description: Me again.\n  instructions: Carry on.\n  at most 600 steps\n"
    "  when it runs out: stop and say so\n\none = orders/look(order: input.order)\nanswer with summary: one.answer\n",
])
def test_an_agent_cannot_write_itself_more_room_three_ways(session: Session, attempt: str) -> None:
    before = session.document["agents"]["desk-summarise"]["limits"]
    got = session.cell(attempt, by="desk-summarise", takes={"order": "text"}, gives={"summary": "text"})
    assert not got.admitted and got.refused_by in ("wider", "collision"), (got.refused_by, got.said)
    assert session.document["agents"]["desk-summarise"]["limits"] == before == {
        "steps-at-most": 6, "when-it-runs-out": "stop-and-say-so",
    }


# ── 4. a loop built from two innocent changes ────────────────────────────────


def test_two_changes_that_are_each_sound_and_together_never_end_are_refused_at_the_second(
    session: Session,
) -> None:
    first = session.propose(
        "flow ping(order: text) gives seen: text\n  description: Looks an order up.\n"
        "  one = orders/look(order: order)\n  answer with seen: one.answer\n"
    )
    second = session.propose(
        "flow pong(order: text) gives seen: text\n  description: Asks ping.\n"
        "  one = ping(order: order)\n  answer with seen: one.seen\n"
    )
    assert first.admitted and second.admitted
    held = session.version
    # Now `ping` is changed to ask `pong`. Each flow reads sensibly alone.
    third = session.change(
        "flow ping(order: text) gives seen: text\n  description: Asks pong.\n"
        "  one = pong(order: order)\n  answer with seen: one.seen\n"
    )
    assert not third.admitted and third.refused_by == "checker"
    assert "rule: loader/workflows-that-call-each-other" in third.said[0]
    assert "ping" in third.said[0] and "pong" in third.said[0], "it names the circle"
    assert session.version == held


# ── 7. a case that waits while the workspace changes round it ────────────────


def test_a_waiting_run_moves_by_itself_past_changes_it_never_reaches_and_not_past_its_own(
    session: Session,
) -> None:
    assert session.propose(
        "flow audit(order: text) gives seen: text\n  description: Looks an order up for the auditors. Draft 0.\n"
        "  one = orders/look(order: order)\n  answer with seen: one.answer\n"
    ).admitted
    pinned = session.pinned("decide-all")
    # Thirty changes to a flow the waiting run never reaches.
    for n in range(1, 31):
        got = session.change(
            f"flow audit(order: text) gives seen: text\n  description: Looks an order up for the auditors. Draft {n}.\n"
            "  one = orders/look(order: order)\n  answer with seen: one.answer\n"
        )
        assert got.admitted, got.said
        assert session.still("decide-all", pinned), f"draft {n} of another flow stopped a waiting run"
    # One change to the flow it is a run of.
    assert session.change(DECIDE_ALL.format(n=1).replace("at-once-at-most: 5", "at-once-at-most: 1")).admitted
    assert not session.still("decide-all", pinned), "what the run would do next changed, and nobody was asked"
    assert not session.still("a-flow-that-is-gone", pinned)


# ── 8. a model that floods the checker ───────────────────────────────────────


def test_a_cell_too_big_to_check_is_refused_before_the_checker_is_run(session: Session) -> None:
    for cell in (
        "answer with summary: input.note\n" + "# padding\n" * 600_000,           # five megabytes
        "".join(f"agent a{i}(x: text) gives y: text\n  description: d\n  instructions: i\n\n" for i in range(4_000)),
        "".join("  " * i + f"e{i} = for each item in input.orders\n" for i in range(400)),
    ):
        assert len(cell.encode()) > MOST_BYTES
        started = time.monotonic()
        got = session.cell(cell, by="desk-summarise", takes={"orders": "list of text", "note": "text"},
                           gives={"summary": "text"})
        assert not got.admitted and got.refused_by == "meter"
        assert time.monotonic() - started < 0.5, "it was measured, not checked"
    # And the session is as it was for everybody else.
    assert session.propose(
        "flow ok(order: text) gives seen: text\n  description: Fine.\n  one = orders/look(order: order)\n"
        "  answer with seen: one.answer\n"
    ).admitted


# ── 10. the kill switch ──────────────────────────────────────────────────────


PAYS = ("paid = payments/refund(order: input.order, amount: input.amount)\n"
        "answer with paid: paid.paid\n")
NO_PAYMENTS = """\
agent cashier(order: text) gives paid: yes or no
  description: Pays a refund that has been approved. Payments are withdrawn.
  at most 4 steps
  when it runs out: stop and say so
  instructions: Say that payments are closed.
"""


def test_once_payments_are_withdrawn_no_cell_reaches_them_and_a_run_in_flight_is_not_cut_in_half(
    session: Session,
) -> None:
    takes, gives = {"order": "text", "amount": "money"}, {"paid": "yes or no"}
    paid: list[str] = []

    def tool(name: str, action: str, given: dict[str, Any]) -> dict[str, Any]:
        paid.append(f"{name}/{action}")
        if len(paid) == 1:
            # The owner withdraws payments while this payment is being made.
            assert session.change(NO_PAYMENTS).admitted
        return {"paid": True}

    async def model(system: str, history: list[dict[str, Any]], tools: list[Any]):
        return PAYS, []

    first = asyncio.run(act_by_a_cell(
        session, "cashier", model, "Refund it.", {"order": "A-1", "amount": "45 USD"}, Callers(tool=tool),
        shapes=takes,
    ))
    # The ask that was in flight finished: the payment it was making was made, once.
    assert first.halted == "final" and paid == ["payments/refund"], (first.said, paid)
    # From then on no cell the cashier writes can reach payments.
    assert "uses" not in session.document["agents"]["cashier"]
    after = session.cell(PAYS, by="cashier", takes=takes, gives=gives)
    assert not after.admitted and after.refused_by == "reach"
    assert "payments/refund" in after.said[0]
    assert paid == ["payments/refund"]


# ── 12. a word worth keeping ─────────────────────────────────────────────────


READER = """\
agent reader(order: text) gives view: text
  description: Says what one order is.
  instructions: Say what this order is in five words.
  uses orders
  at most 3 steps
  when it runs out: stop and say so
"""


def test_what_a_run_defined_is_kept_only_with_a_persons_approval(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    session = Session.open(DESK, journal=journal)
    try:
        cell = READER + "\none = reader(order: input.order)\nanswer with summary: one.view\n"
        used = session.cell(cell, by="desk-summarise", takes={"order": "text"}, gives={"summary": "text"})
        assert used.admitted
        session.end(used)
        assert "reader" not in session.document["agents"], "it was for that call"

        nobody = session.promote(READER, proposed_by="desk-summarise", approved_by="")
        assert not nobody.admitted and nobody.refused_by == "promotion"
        assert "without a person's approval" in nobody.said[0]
        assert "reader" not in session.document["agents"]

        kept = session.promote(READER, proposed_by="desk-summarise", approved_by="priya")
        assert kept.admitted and "agents/reader" in kept.names
        assert session.promoted == [{
            "names": ["agents/reader"], "proposed-by": "desk-summarise", "approved-by": "priya",
            "version": session.version,
        }]
        version = session.version
    finally:
        session.close()
    # The journal says who approved it, and a session opened on it has it.
    assert "approved by priya" in journal.read_text()
    again = Session.open(DESK, journal=journal)
    try:
        assert again.version == version and "reader" in again.document["agents"]
    finally:
        again.close()


def test_where_a_workspace_names_its_owners_only_an_owner_approves(tmp_path: Path) -> None:
    import shutil

    owned = tmp_path / "owned"
    shutil.copytree(DESK, owned)
    (owned / "owners.pact").write_text("owner agents/cashier\n  owned-by: priya\n")
    session = Session.open(owned)
    try:
        stranger = session.promote(READER, proposed_by="desk-summarise", approved_by="mallory")
        assert not stranger.admitted and stranger.refused_by == "promotion"
        assert "mallory is not an owner" in stranger.said[0] and "priya" in stranger.said[0]
        assert session.promote(READER, proposed_by="desk-summarise", approved_by="priya").admitted
    finally:
        session.close()


# ── what a run is handed is kept while nothing it depends on has changed ─────


def test_a_change_drops_exactly_what_depended_on_it(session: Session) -> None:
    judge = session.agent("desk-judge")
    cashier = session.agent("cashier")
    assert session.agent("desk-judge") is judge and (session.plans_read, session.plans_reused) == (2, 1)
    # The cashier is rewritten. The judge does not name it, so the judge is kept.
    assert session.change(NO_PAYMENTS).admitted
    assert session.agent("desk-judge") is judge
    assert session.agent("cashier") is not cashier
    assert "Payments are withdrawn" in session.agent("cashier").description
    # The tool the judge uses is rewritten: now the judge is read again.
    assert session.change(
        "tool orders\n  description: The order book, rebuilt.\n  connect: office\n  actions:\n    look:\n"
        "      description: Read one order, with its history.\n      reads-only: yes\n      takes:\n        order: text\n"
    ).admitted
    assert session.agent("desk-judge") is not judge
    # A flow depends on what it calls, and what that calls.
    doc = session.document
    assert depends_on(doc, "workflows", "decide-all") != depends_on(
        {**doc, "agents": {**doc["agents"], "desk-judge": {**doc["agents"]["desk-judge"], "instructions": "x"}}},
        "workflows", "decide-all",
    )
    assert depends_on(doc, "workflows", "decide-all") == depends_on(
        {**doc, "agents": {**doc["agents"], "cashier": {**doc["agents"]["cashier"], "instructions": "x"}}},
        "workflows", "decide-all",
    )


def test_what_an_agents_own_settings_ask_for_and_a_cell_does_not_carry_out_is_said(tmp_path: Path) -> None:
    import shutil

    with_rules = tmp_path / "ruled"
    shutil.copytree(DESK, with_rules)
    text = (with_rules / "refunds.pact").read_text().replace(
        "  instructions: Refund the order you are given, once.\n",
        "  instructions: Refund the order you are given, once.\n  checked-by:\n    - must-contain: [refund]\n",
    )
    (with_rules / "refunds.pact").write_text(text)
    session = Session.open(with_rules)

    async def model(system: str, history: list[dict[str, Any]], tools: list[Any]):
        return "answer with paid: input.ok\n", []

    try:
        out = asyncio.run(act_by_a_cell(session, "cashier", model, "Refund it.", {"ok": True}, Callers()))
        assert out.halted == "final", out.said
        assert [u.split(":", 1)[0] for u in out.unenforced] == ["checked-by"]
        assert "acts by writing a cell here" in out.unenforced[0] and "harness.run" in out.unenforced[0]
        plain = asyncio.run(act_by_a_cell(session, "desk-summarise", model, "x", {"ok": True}, Callers()))
        assert plain.unenforced == []
    finally:
        session.close()
