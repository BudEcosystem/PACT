"""What a teammate could not carry out, or could not count, is on the result of
the run that put it to work — and still there after a park.

`delegate_by_running.ask` returns the member's words (`out.output`) and returned
nothing else, so "said, never silent" held for the agent a host ran and for
nobody it asked. A teammate whose reaction could not be carried out, or whose
spend cap could not be metered, was a clean run as far as anyone reading the
caller's `RunResult` could tell.

Found the wrong way round: Bud Agent Flow was told its engine dropped a member's
lines where PACT's did not. PACT's dropped them too. Bud Agent Flow closed it
first, and found the second half itself — a member asked BEFORE a park is not
asked again after it, so a resumed run lost the lines unless they were kept with
the park. The wording, `<member> (put to work by this agent): <its line>`, is
Bud Agent Flow's.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.harness import ToolCall, delegate_by_running, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import Suspension  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from trees import shown, write  # noqa: E402

TREE = {
    "team.pact": """\
workspace "Notes"
  description: A lead that asks a helper, whose own rule cannot be carried out when it is asked.

agent lead
  description: Answers by asking a helper, then posts the answer.
  asks helper: Looks the answer up in the notes.
  uses ledger
  at most 6 steps
  when it runs out: stop and say so
  instructions: Ask the helper, then post what it found.

agent helper
  description: Looks things up.
  uses notes
  # No `asks-itself-at-most:`, so a helper that is put to work by another
  # agent has nobody it can ask in turn: this consult cannot be carried out.
  when the agent is about to call notes/search
    called check-first
    consult checker
  instructions: Search the notes and say what you found.

agent checker
  description: Reads a search before it is made.
  instructions: Say whether the search is a sensible one.

resource office
  resource-kind: mcp-server
  endpoint: host/office
  description: Where the notes and the ledger are reached.

tool notes
  description: The notes.
  connect: office
  actions:
    search:
      description: Search the notes.
      reads-only: yes
      takes:
        phrase: text

tool ledger
  description: Where answers are posted.
  connect: office
  actions:
    post:
      description: Post one answer.
      needs-a-person: yes
      takes:
        answer: text
"""
}

ASK = ToolCall("helper", {"question": "What do the notes say?"})
POST = ToolCall("ledger", {"action": "post", "answer": "The notes say yes."})
HELPERS_LINE = (
    "helper (put to work by this agent): the reaction 'check-first' consults 'checker', and "
    "this run has nobody to run another agent — 'checker' was not asked"
)


def setup(tmp_path: Path):
    doc = shown(write(tmp_path / "notes", TREE))
    lead = AgentSpec.from_document(doc, "lead")
    script = Script([Turn("", (ASK,)), Turn("", (POST,)), Turn("Posted.")])
    searched: list[dict[str, Any]] = []

    def member(spec: AgentSpec) -> ReferenceTransport:
        return ReferenceTransport(Script([
            Turn("", (ToolCall("notes", {"action": "search", "phrase": "yes"}),)),
            Turn("The notes say yes."),
        ]))

    tools = {
        "notes": lambda args: (searched.append(dict(args)), "one note: yes")[1],
        "ledger": lambda args: "posted",
    }
    asker = delegate_by_running(doc, member, tools)
    return lead, script, tools, asker, searched


def test_a_teammates_line_is_on_the_result_of_the_run_that_asked_it(tmp_path: Path) -> None:
    lead, script, tools, asker, searched = setup(tmp_path)
    out = asyncio.run(run(lead, ReferenceTransport(script), "What do the notes say?", tools, ask_member=asker))
    # The lead asked the helper, the helper's search went through unasked —
    # nobody there to consult — and the helper's run said so.
    assert searched == [{"action": "search", "phrase": "yes"}]
    assert HELPERS_LINE in out.unenforced, out.unenforced
    # And it is the HELPER's line, said as the helper's: the lead has no
    # reaction of its own that could not be carried out.
    assert [s for s in out.unenforced if not s.startswith("helper (put to work")] == []


def test_it_is_still_there_after_a_park(tmp_path: Path) -> None:
    lead, script, tools, asker, _ = setup(tmp_path)
    first = asyncio.run(run(lead, ReferenceTransport(script), "What do the notes say?", tools, ask_member=asker))
    assert first.halted == "suspended", (first.halted, first.output)
    assert HELPERS_LINE in first.unenforced
    # Across a process boundary: the park is written down and read back.
    parked = Suspension.from_json(first.suspension.to_json())
    assert parked.from_members == {"unenforced": [HELPERS_LINE], "unmetered": parked.from_members["unmetered"]}
    yes = parked.answer(**{a.name: "yes" for a in parked.asks})
    after = asyncio.run(
        run(lead, ReferenceTransport(script), "What do the notes say?", tools, ask_member=asker,
            resume=parked, answer=yes, now=1.0)
    )
    assert after.halted == "final" and after.output == "Posted."
    # The helper was asked before the park and is not asked again after it, so
    # the resumed run knows of its line only because the park kept it.
    assert HELPERS_LINE in after.unenforced, after.unenforced


def test_a_ceiling_a_teammate_could_not_count_is_said_as_the_teammates(tmp_path: Path) -> None:
    lead, script, tools, asker, _ = setup(tmp_path)
    out = asyncio.run(run(lead, ReferenceTransport(script), "What do the notes say?", tools, ask_member=asker))
    mine = [u for u in out.unmetered if "(put to work by this agent)" not in u]
    theirs = [u for u in out.unmetered if u.startswith("helper (put to work by this agent): ")]
    # Whatever the helper's own run could not count is here, under its name,
    # and assigning to `unmetered` does not fold the helper's lines into the
    # lead's own.
    out.unmetered = out.unmetered + ("something-new",)
    assert [u for u in out._unmetered if "(put to work" in u] == []
    assert tuple(out.unmetered) == (*mine, "something-new", *theirs)
