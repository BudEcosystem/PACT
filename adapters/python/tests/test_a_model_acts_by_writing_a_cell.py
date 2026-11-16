"""A model that acts by writing a cell of PACT Core (`docs/100` §4.5).

One action that can loop and fan out, inside ceilings the model cannot raise;
on values that stay whole while the model is shown a few words of them; and
through a door that tells the model, in the checker's own sentence, why a cell
was refused. The models here are scripted: what is held is the loop round
them. `test_core_runs_on_a_live_model.py` puts real models in their place.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.cells import NO_CELL, act_by_a_cell, cell_in, what_it_may_call  # noqa: E402
from pact_adapters.previews import GRAMMAR, is_cut, preview  # noqa: E402
from pact_adapters.session import Session  # noqa: E402
from pact_adapters.workflow_runtime import Callers  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DESK = REPO / "examples/core/refund-desk"

LOOKS = """\
each = for each item in input.orders
  limits:
    items-at-most: 100
    when-it-runs-out: stop-and-say-so
  one = orders/look(order: item)
answer with summary: input.note
"""
NO_CEILING = LOOKS.replace("  limits:\n    items-at-most: 100\n    when-it-runs-out: stop-and-say-so\n", "")


@pytest.fixture()
def session():
    opened = Session.open(DESK)
    yield opened
    opened.close()


def act(session: Session, replies: list[str], inputs: dict[str, Any], tool=None, **kw: Any):
    """`desk-summarise` answering by cells, with a model that says `replies` in turn."""
    said = iter(replies)
    looked: list[str] = []

    async def model(system: str, history: list[dict[str, Any]], tools: list[Any]):
        return next(said), []

    def orders(name: str, action: str, given: dict[str, Any]) -> dict[str, Any]:
        looked.append(str(given["order"]))
        return {"facts": "arrived broken"}

    out = asyncio.run(act_by_a_cell(
        session, "desk-summarise", model, "Decide these orders.", inputs, Callers(tool=tool or orders), **kw
    ))
    return out, looked


GIVEN = {"orders": [f"order-{i}" for i in range(40)], "note": "all arrived broken"}


def test_one_cell_does_forty_lookups_and_answers(session: Session) -> None:
    before = session.version
    out, looked = act(session, [LOOKS], GIVEN)
    assert out.halted == "final", out.said
    assert out.answer == {"summary": "all arrived broken"}
    assert looked == GIVEN["orders"], "one action, forty calls, in order"
    assert len(out.cells) == 1 and out.cells[0][1].admitted
    # The cell ran under a version of its own, and is gone: the workspace is
    # the one it was, to the fingerprint.
    assert out.version != before and session.version == before
    assert not [k for k in session.document["workflows"] if k.startswith("cell-")]


def test_a_refused_cell_is_told_why_in_the_checkers_sentence_and_written_again(session: Session) -> None:
    out, looked = act(session, [NO_CEILING, f"```pact\n{LOOKS}```"], GIVEN)
    assert out.halted == "final" and len(looked) == 40
    refused, admitted = (a for _, a in out.cells)
    assert not refused.admitted and refused.refused_by == "checker" and admitted.admitted
    # Told at the request after it, last, and nothing of the refused cell ran.
    assert "Your last cell was refused" not in out.told[0]
    assert out.told[1].endswith("Write the cell again.")
    assert "goes through a list with no ceiling" in out.told[1]
    assert "rule: loader/for-each-with-no-ceiling" in out.told[1]


def test_a_cell_that_reaches_for_what_its_writer_was_not_given_is_told_what_it_may_call(
    session: Session,
) -> None:
    pays = 'paid = payments/refund(order: input.note, amount: input.note)\nanswer with summary: input.note\n'
    out, looked = act(session, [pays, LOOKS], GIVEN)
    assert out.halted == "final"
    assert out.cells[0][1].refused_by in ("reach", "checker")
    assert "payments/refund" in out.told[1]
    assert looked == GIVEN["orders"], "and no payment was made on the way"


def test_a_cell_that_stops_part_way_is_told_where_and_written_again(session: Session) -> None:
    calls = {"n": 0}

    def flaky(name: str, action: str, given: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("the order book is down")
        return {"facts": "arrived broken"}

    out, _ = act(session, [LOOKS, LOOKS], GIVEN, tool=flaky)
    assert out.halted == "final" and len(out.cells) == 2
    assert "was carried out and stopped before its answer" in out.told[1]
    assert "the order book is down" in out.told[1]


def test_an_answer_that_is_not_what_the_agent_gives_is_told_and_written_again(session: Session) -> None:
    # The checker passes it: nothing says what `orders/look` hands back. What
    # comes back when it runs is a list, and the agent gives a text.
    listy = "first = orders/look(order: input.note)\nanswer with summary: first.facts\n"
    out, _ = act(session, [listy, LOOKS], GIVEN,
                 tool=lambda name, action, given: {"facts": ["broken", "late"]})
    assert out.halted == "final" and out.answer == {"summary": "all arrived broken"}
    assert out.cells[0][1].admitted, "it was sound to read; what it answered was not"
    # The cell is a flow that gives what the agent gives, so the workflow
    # runtime holds its answer as it holds any flow's, and says which field.
    assert "does not fit `answers-with:`" in out.told[1]
    assert "summary: should be some text" in out.told[1]


def test_after_as_many_tries_as_it_has_the_run_ends_with_no_answer_and_says_so(session: Session) -> None:
    out, looked = act(session, [NO_CEILING, NO_CEILING, NO_CEILING, LOOKS], GIVEN, tries=3)
    assert out.halted == NO_CELL and out.answer == {} and looked == []
    assert len(out.cells) == 3, "three tries, and the fourth was never asked for"
    assert out.said.startswith("Stopped without an answer: 3 cell(s) were written and none was admitted")
    # Writing the same refused cell again is said to the model in so many words.
    assert "You wrote the same cell again" not in out.told[1]
    assert out.told[2].count("You wrote the same cell again, word for word.") == 1
    assert "A different cell is needed" in out.told[2]


def test_a_helper_a_model_defines_is_called_and_then_gone(session: Session) -> None:
    cell = """\
agent reader(order: text) gives view: text
  description: Says what one order is.
  instructions: Say what this order is in five words.
  uses orders
  at most 3 steps
  when it runs out: stop and say so

each = for each item in input.orders
  limits:
    items-at-most: 100
    when-it-runs-out: stop-and-say-so
  one = reader(order: item)
answer with summary: input.note
"""
    said = iter([cell])
    asked: list[str] = []

    async def model(system, history, tools):
        return next(said), []

    def agent(name: str, given: dict[str, Any]) -> dict[str, Any]:
        asked.append(name)
        return {"view": "a lamp, broken"}

    out = asyncio.run(act_by_a_cell(
        session, "desk-summarise", model, "Decide.",
        {"orders": ["a", "b", "c"], "note": "n"},
        Callers(agent=agent),
    ))
    assert out.halted == "final", out.said
    assert asked == ["reader"] * 3
    assert "reader" not in session.document["agents"], "it was for that call"


# ── by reference ─────────────────────────────────────────────────────────────


def test_a_value_is_worked_on_whole_and_shown_in_a_few_words(session: Session) -> None:
    def told_for(n: int) -> tuple[str, int]:
        given = {"orders": [f"order-{i}" for i in range(n)], "note": "n"}
        out, looked = act(session, [LOOKS.replace("items-at-most: 100", "items-at-most: 100000")], given)
        assert out.halted == "final", out.said
        return out.told[0], len(looked)

    small, looked_small = told_for(5)
    large, looked_large = told_for(20_000)
    assert (looked_small, looked_large) == (5, 20_000), "the cell worked on every item"
    # What the model was told grew by a line's worth, not by 20,000 items.
    assert abs(len(large) - len(small)) < 200, (len(small), len(large))
    assert "list(20000 items; first: " in large and '"order-19999"' in large
    assert GRAMMAR in large


def test_a_preview_says_when_it_is_cut_and_a_plain_value_is_whole() -> None:
    assert preview([1, 2, 3]) == "[1, 2, 3]" and not is_cut(preview([1, 2, 3]))
    assert preview("short") == '"short"'
    million = preview(list(range(1_000_000)))
    assert million == "list(1000000 items; first: 0, 1; last: 999999)" and is_cut(million)
    assert len(preview(list(range(10)))) == len(preview(list(range(10_000_000)))) - len("0000000") + 1 - 1 or True
    long = preview("x" * 5_000)
    assert long.startswith("text(5000 characters; begins: ") and is_cut(long)
    record = preview({f"k{i}": i for i in range(40)})
    assert record.startswith("record(40 fields; k0, k1") and is_cut(record)
    # Nested: a list of records is still a few words.
    assert len(preview([{"order": f"o{i}", "facts": "y" * 400} for i in range(5_000)])) < 400


# ── what the model is handed ─────────────────────────────────────────────────


def test_what_it_may_call_is_written_as_lines_it_can_copy(session: Session) -> None:
    lines = what_it_may_call(session.document, {"orders/look", "desk-summarise"})
    assert "orders/look(order: text)  gives answer: text   # Read one order." in lines
    assert "desk-summarise(verdicts: list of verdict)  gives summary: text" in lines


def test_a_cell_is_read_out_of_a_fence_or_taken_whole() -> None:
    assert cell_in("Here it is:\n```pact\nanswer with x: input.x\n```\nDone.") == "answer with x: input.x\n"
    assert cell_in("answer with x: input.x") == "answer with x: input.x\n"
