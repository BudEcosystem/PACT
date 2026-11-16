"""A workspace run two ways: changed while it runs, or sealed (`docs/100` §6).

**Interpreted.** `Session.open` keeps a workspace that takes proposals while
runs are going. Each goes through one door, and the judge at it is the `pact`
binary that checks a tree before any run. A change takes effect for what
starts after it; a run already going finishes under the version it began with.

**Pre-compiled.** `compile_plan` checks once and seals. A plan runs with no
checker beside it and refuses every change.

The same document runs on the same runtime either way, which the last tests
here hold.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.session import Plan, Session, compile_plan, fingerprint  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DESK = REPO / "examples/core/refund-desk"

GREET = """\
agent greeter(name: text) gives greeting: text
  description: Greets one person.
  instructions: Greet them by name.
  at most 2 steps
  when it runs out: stop and say so

flow greet-all(names: list of text) gives greetings: list of text
  description: Greet everybody on a list.
  each = for each item in input.names
    limits:
      items-at-most: 10
      when-it-runs-out: stop-and-say-so
    one = greeter(name: item)
  answer with greetings: each.greeting
"""


@pytest.fixture()
def session():
    opened = Session.open(DESK)
    yield opened
    opened.close()


def run(document: Any, flow: str, inputs: dict[str, Any], **callers: Any):
    spec = WorkflowSpec.from_workflow(document, flow)
    return asyncio.run(run_workflow(spec, inputs, Callers(**callers), document=document))


# ── the door ─────────────────────────────────────────────────────────────────


def test_what_is_proposed_and_sound_is_there_for_the_next_run(session: Session) -> None:
    before = session.version
    got = session.propose(GREET)
    assert got.admitted and got.version == session.version != before
    assert set(got.names) == {"agents/greeter", "workflows/greet-all"}
    out = run(session.document, "greet-all", {"names": ["ann", "bob"]},
              agent=lambda name, given: {"greeting": f"hello {given['name']}"})
    assert out.halted == "final" and len(out.answer["greetings"]) == 2


def test_what_is_proposed_and_unsound_changes_nothing_and_is_told_in_the_checkers_words(
    session: Session,
) -> None:
    before, was = session.version, session.document
    got = session.propose(GREET.replace("    limits:\n      items-at-most: 10\n      when-it-runs-out: stop-and-say-so\n", ""))
    assert not got.admitted and got.refused_by == "checker"
    assert "rule: loader/for-each-with-no-ceiling" in got.said[0]
    assert "each = for each item in input.names" in got.said[0], "the line the author wrote"
    assert session.version == before and session.document is was


def test_a_definition_is_changed_in_place_and_only_one_that_is_there(session: Session) -> None:
    told = lambda: session.document["agents"]["cashier"]["instructions"]  # noqa: E731
    assert told() == "Refund the order you are given, once."
    careful = """\
agent cashier(order: text) gives paid: yes or no
  description: Pays a refund that has been approved, after reading the order back.
  uses payments
  at most 4 steps
  when it runs out: stop and say so
  instructions: Read the order number back, then refund it once.
"""
    got = session.change(careful)
    assert got.admitted, got.said
    assert told() == "Read the order number back, then refund it once."
    missing = session.change(careful.replace("agent cashier", "agent nobody"))
    assert not missing.admitted and missing.refused_by == "session"
    assert "no agent called 'nobody' here to change" in missing.said[0]


def test_an_actor_is_changed_as_one_thing(session: Session) -> None:
    # `desk-judge` is the capability `judge` of the actor `desk`: what is
    # written, and so what is changed, is the actor.
    whole = (DESK / "refunds.pact").read_text()
    start = whole.index("actor desk\n")
    actor = whole[start:whole.index("# A function:", start)]
    got = session.change(actor.replace("Say why in one sentence.", "Say why in five words."))
    assert got.admitted, got.said
    assert session.document["agents"]["desk-judge"]["instructions"].endswith("Say why in five words.")


def test_what_something_still_names_cannot_be_taken_away(session: Session) -> None:
    # The actor `desk` uses the tool `orders`. The checker says who still names it.
    got = session.withdraw("tool", "orders")
    assert not got.admitted and got.refused_by == "checker"
    assert "orders" in got.said[0]
    assert "orders" in session.document["tools"]
    # Nothing names the cashier, so it can go; and then it is gone.
    gone = session.withdraw("agent", "cashier")
    assert gone.admitted and "cashier" not in session.document["agents"]


def test_a_workspace_written_as_a_folder_is_changed_the_same_way() -> None:
    opened = Session.open(REPO / "examples/refund-desk")
    try:
        added = opened.propose(GREET)
        assert added.admitted, added.said
        # `fraud-checker` is a folder there (`agents/fraud-checker/`).
        got = opened.change(
            "agent fraud-checker(message: text) gives concern: one of none, low, high, why: text\n"
            "  description: Looks for signs the request is not genuine, and says so plainly.\n"
            "  instructions: Say low unless two signs point the same way.\n"
        )
        assert got.admitted, got.said
        assert opened.document["agents"]["fraud-checker"]["instructions"].startswith("Say low unless")
    finally:
        opened.close()


# ── a run in flight ──────────────────────────────────────────────────────────


def test_a_run_in_flight_finishes_under_the_version_it_began_with(session: Session) -> None:
    asked: list[str] = []

    def judge(name: str, given: dict[str, Any]) -> dict[str, Any]:
        asked.append(name)
        if name == "desk-summarise":
            return {"summary": "all approved"}
        if len(asked) == 1:
            # While the first order is being judged, the flow that is running
            # is rewritten so that nobody is judged at all.
            got = session.change(
                "flow decide-all(orders: list of text) gives received: list of text\n"
                "  description: Decides nothing any more, and says what it was handed.\n"
                "  answer with received: input.orders\n"
            )
            changed.append(got)
        return {"decision": "approved", "reason": "broken"}

    changed: list[Any] = []
    began = session.version
    held = session.document  # what a run is handed when it starts
    out = run(held, "decide-all", {"orders": ["a", "b", "c"]},
              tool=lambda t, a, i: {"facts": "broken"}, agent=judge)
    assert changed and changed[0].admitted, changed and changed[0].said
    # The run that was going judged all three, the way it was written when it began.
    assert out.halted == "final", out.said
    assert asked.count("desk-judge") == 3 and len(out.answer["verdicts"]) == 3
    assert session.version == changed[0].version != began
    # A run started now is the new workspace: nobody is judged.
    asked.clear()
    after = run(session.document, "decide-all", {"orders": ["a", "b", "c"]}, agent=judge)
    assert after.halted == "final", after.said
    assert asked == [] and after.answer == {"received": ["a", "b", "c"]}


# ── the journal ──────────────────────────────────────────────────────────────


def test_a_session_resumed_from_any_point_of_its_journal_is_wholly_before_or_wholly_after(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "journal.jsonl"
    first = Session.open(DESK, journal=journal)
    reached = [first.version]
    assert first.propose(GREET).admitted
    reached.append(first.version)
    assert not first.propose("flow broken() gives x: text\n  description: Broken.\n  one = nobody()\n  answer with x: one.x\n").admitted
    assert first.withdraw("agent", "cashier").admitted
    reached.append(first.version)
    first.close()

    lines = journal.read_text().splitlines(keepends=True)
    assert [json.loads(l)["state"] for l in lines] == [
        "proposed", "admitted", "proposed", "refused", "proposed", "admitted",
    ]
    # Stop the journal after every line, and in the middle of every line: a
    # process that died there. What comes back is one of the versions the
    # session really reached, and never something between two of them.
    for upto in range(len(lines) + 1):
        for cut in (0, 9):
            if cut and upto == len(lines):
                continue
            text = "".join(lines[:upto]) + (lines[upto][:cut] if cut else "")
            copy = tmp_path / f"j-{upto}-{cut}.jsonl"
            copy.write_text(text)
            back = Session.open(DESK, journal=copy)
            try:
                admitted = sum(1 for l in lines[:upto] if json.loads(l)["state"] == "admitted")
                assert back.version == reached[admitted], (upto, cut)
            finally:
                back.close()


def test_a_journal_made_with_another_workspace_is_refused(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    first = Session.open(DESK, journal=journal)
    assert first.propose(GREET).admitted
    first.close()
    other = tmp_path / "other"
    shutil.copytree(DESK, other)
    text = (other / "refunds.pact").read_text().replace("at most 6 steps", "at most 5 steps")
    (other / "refunds.pact").write_text(text)
    with pytest.raises(ValueError, match="not the one the journal was written with"):
        Session.open(other, journal=journal)


# ── pre-compiled ─────────────────────────────────────────────────────────────


def test_a_plan_is_the_workspace_checked_once_and_sealed(tmp_path: Path, session: Session) -> None:
    plan = compile_plan(DESK)
    assert plan.version == session.version == fingerprint(plan.document)
    plan.save(tmp_path / "desk.plan.json")
    back = Plan.load(tmp_path / "desk.plan.json")
    assert back.version == plan.version and back.document == plan.document
    # The same run, from the sealed plan and from the live session.
    callers = dict(
        tool=lambda t, a, i: {"facts": "broken"},
        agent=lambda n, g: ({"summary": "all approved"} if n == "desk-summarise"
                            else {"decision": "approved", "reason": "broken"}),
    )
    sealed = run(back.document, "decide-all", {"orders": ["a", "b"]}, **callers)
    live = run(session.document, "decide-all", {"orders": ["a", "b"]}, **callers)
    assert sealed.halted == live.halted == "final"
    assert sealed.answer == live.answer and sealed.trace == live.trace


def test_a_plan_takes_no_change_and_says_how_to_have_one(tmp_path: Path) -> None:
    plan = compile_plan(DESK)
    for refused in (plan.propose(GREET), plan.change(GREET), plan.withdraw("agent", "cashier"),
                    plan.cell("answer with x: input.x", by="cashier")):
        assert not refused.admitted and refused.refused_by == "sealed"
        assert "pre-compiled" in refused.said[0] and "Session.open" in refused.said[0]
        assert refused.version == plan.version


def test_a_plan_that_was_edited_after_it_was_sealed_is_refused(tmp_path: Path) -> None:
    where = tmp_path / "desk.plan.json"
    compile_plan(DESK).save(where)
    held = json.loads(where.read_text())
    held["document"]["agents"]["cashier"]["limits"]["steps-at-most"] = 400
    where.write_text(json.dumps(held))
    with pytest.raises(ValueError, match="not the plan that was sealed"):
        Plan.load(where)


def test_a_workspace_that_does_not_load_is_not_sealed_or_opened(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    shutil.copytree(DESK, broken)
    (broken / "more.pact").write_text("flow f() gives x: text\n  description: F.\n  one = nobody()\n  answer with x: one.x\n")
    with pytest.raises(ValueError, match="does not load"):
        compile_plan(broken)
    with pytest.raises(ValueError, match="does not load"):
        Session.open(broken)


def test_how_long_the_door_takes_is_measured_and_small(session: Session) -> None:
    took = sorted(session.propose(GREET.replace("greet", f"greet{i}")).took for i in range(5))
    # Two runs of the checker and a copy of the tree. A model call takes seconds.
    assert took[-1] < 3.0, took
    print(f"\n[admission] median {took[2]*1000:.0f} ms, slowest {took[-1]*1000:.0f} ms")
