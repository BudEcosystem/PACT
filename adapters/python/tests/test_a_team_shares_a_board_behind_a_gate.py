"""The team store (docs/98 WP-8): a fact the lead shares with its team, read and
written by every member, every write through an admission gate.

`docs/remediation/F7` refused a blackboard because nothing one agent wrote could
be read by another. `docs/92-SWARM.md` §6.3 said the accuracy is in the gate,
not the queue. Both are held here: members share one board for the request,
and an entry is written only if it fits `shaped-like:`, meets every
`admitted-when:` line, and the `admitted-by:` judge says yes.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.boards import Board, tool_for  # noqa: E402
from pact_adapters.facts import Facts  # noqa: E402

FINDINGS = {
    "description": "what each solver found",
    "lasts": "one-conversation",
    "shared-with": "the-team",
    "shaped-like": {"claim": "text", "status": "one of open, solved"},
    "admitted-when": [{"value": "entry.status", "is-one-of": ["open", "solved"]}],
}


def fact(**more):
    return Facts.of({"findings": {**FINDINGS, **more}}).declared["findings"]


def test_the_three_lines_are_read_off_the_document() -> None:
    f = fact(**{"admitted-by": "referee"})
    assert f.shared_with == "the-team"
    assert f.admitted_by == "referee"
    assert f.admitted_when == ({"value": "entry.status", "is-one-of": ["open", "solved"]},)
    assert Facts.of({"x": {"description": "x", "lasts": "forever"}}).declared["x"].shared_with == "this-agent"


def test_an_entry_that_fits_is_written_and_read_back_with_its_writer() -> None:
    board = Board()
    _, body = tool_for(fact(), board, "solver-a", None)
    assert json.loads(body({"action": "read"})) == []
    said = body({"action": "write", "entry": {"claim": "x = 3", "status": "open"}})
    assert said.startswith("written"), said
    assert json.loads(body({"action": "read"})) == [
        {"by": "solver-a", "entry": {"claim": "x = 3", "status": "open"}}
    ]


def test_an_entry_that_does_not_fit_the_shape_is_refused_saying_why() -> None:
    board = Board()
    _, body = tool_for(fact(), board, "solver-a", None)
    said = body({"action": "write", "entry": {"claim": "x", "status": "maybe"}})
    assert said.startswith("not written"), said
    assert "must be one of open, solved" in said
    said = body({"action": "write", "entry": {"status": "open"}})
    assert "it has no `claim`" in said, said
    said = body({"action": "write", "entry": {"claim": "x", "status": "open", "mood": "sure"}})
    assert "`mood`" in said, said
    assert board.read("findings") == []


def test_an_entry_the_admission_lines_refuse_is_not_written() -> None:
    board = Board()
    strict = fact(**{"admitted-when": [{"value": "entry.status", "is": "solved"}]})
    _, body = tool_for(strict, board, "solver-a", None)
    said = body({"action": "write", "entry": {"claim": "x", "status": "open"}})
    assert said.startswith("not written") and "does not meet" in said, said
    assert body({"action": "write", "entry": {"claim": "x", "status": "solved"}}).startswith("written")


def test_a_judge_with_nobody_to_ask_it_refuses_every_write() -> None:
    board = Board()
    _, body = tool_for(fact(**{"admitted-by": "referee"}), board, "solver-a", None)
    said = body({"action": "write", "entry": {"claim": "x", "status": "open"}})
    assert said.startswith("not written") and "nobody to ask" in said, said
    assert board.read("findings") == []


def test_the_judge_decides_and_its_reason_reaches_the_writer() -> None:
    board = Board()
    asked: list[tuple[str, str, dict]] = []

    def admit(judge, name, entry):
        asked.append((judge, name, dict(entry)))
        return (entry["claim"] != "x = 4", "x = 4 contradicts the second equation")

    _, body = tool_for(fact(**{"admitted-by": "referee"}), board, "solver-a", admit)
    assert body({"action": "write", "entry": {"claim": "x = 3", "status": "open"}}).startswith("written")
    said = body({"action": "write", "entry": {"claim": "x = 4", "status": "open"}})
    assert "referee said no" in said and "contradicts" in said, said
    assert [a[0] for a in asked] == ["referee", "referee"]
    assert len(board.read("findings")) == 1


def test_a_teammate_writes_and_the_lead_reads_the_same_board() -> None:
    from pact_adapters.harness import ToolCall, delegate_by_running, run
    from pact_adapters.ir import AgentSpec
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    doc = {
        "agents": {
            "lead": {
                "description": "Collects findings.",
                "instructions": "Ask the solver, then read the findings.",
                "team": {"solver": "finds things"},
                "remembers": {"findings": FINDINGS},
            },
            "solver": {"description": "Finds things.", "instructions": "Write what you find."},
        }
    }
    member_script = Script([
        Turn("", (ToolCall("findings", {"action": "write", "entry": {"claim": "x = 3", "status": "solved"}}),)),
        Turn("I wrote it down."),
    ])
    lead_script = Script([
        Turn("", (ToolCall("solver", {"message": "find x"}),)),
        Turn("", (ToolCall("findings", {"action": "read"}),)),
        Turn("x = 3, from the board."),
    ])
    board = Board()
    asker = delegate_by_running(doc, lambda spec: ReferenceTransport(member_script))
    lead = AgentSpec.from_document(doc, "lead")
    out = asyncio.run(
        run(lead, ReferenceTransport(lead_script), "go", ask_member=asker, board=board)
    )
    assert board.read("findings") == [
        {"by": "solver", "entry": {"claim": "x = 3", "status": "solved"}}
    ], (out.halted, out.output, board.entries)
