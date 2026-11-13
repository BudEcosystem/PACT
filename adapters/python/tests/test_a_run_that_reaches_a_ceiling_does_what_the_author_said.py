"""A run that reaches a ceiling does what the author said — all of it.

The first shared cases for limits (`tests/conformance/limits.json`) found two
things this harness did not do, and a third it did only in part.

* **"Keep going" did not let the run keep going.** `when-it-runs-out:
  ask-a-person`, a person answers yes, and the run is granted "a fresh budget
  of the same size". It was granted for the step ceiling alone: a run that had
  reached `tool-calls-at-most` came back with the figure it had already
  reached and parked again at once, with the same question. `Limits.kept_going`
  was written to end exactly that, and nothing here called it.
* **A budget once granted was lost at the next park.** A run told to keep
  going and then parked for anything else came back under the ceilings as
  written, already past them.
* **The closing request was told less than every other.** `answer-with-what-
  it-has` makes one more request with no tools. It was sent the bare
  `instructions:` — without the shape the answer must have and without what a
  reaction had reminded the agent of.

And one thing it said badly. **A run a person refused more budget said nothing
about why it had ended.** Its answer was the model's last words, which for a run
stopped between tool calls is an empty string. It now says which ceiling, and
that a person was asked and said no (`Reached.declined`) — or that nobody
answered in time, which is not the same thing.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import Suspension  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from trees import shown  # noqa: E402

WORKSPACE = """\
workspace "Lookups"
  description: A clerk with a ceiling on lookups.

resource office
  resource-kind: mcp-server
  endpoint: host/office
  description: Where the ledger is reached.

tool ledger
  description: The office ledger.
  connect: office
  actions:
    look:
      description: Read one entry.
      reads-only: yes
      takes:
        entry: text

question keep-looking
  description: Asked when the clerk has used up its lookups.
  says: This clerk has used all its lookups. May it go on?
  answer:
    go-on: yes or no
  asked-of: [office-leads]
  answer-within: 1h
  if-nobody-answers: decline

agent asks
  description: Looks entries up, and asks a person when its lookups run out.
  uses ledger
  limits:
    tool-calls-at-most: 2
    when-it-runs-out: ask-a-person
    asks: keep-looking
  instructions: Look up what you are asked about in the ledger.

agent both
  description: Has a ceiling on steps and on lookups, and can reach the two together.
  uses ledger
  limits:
    steps-at-most: 2
    tool-calls-at-most: 2
    when-it-runs-out: ask-a-person
    asks: keep-looking
  instructions: Look up what you are asked about in the ledger.

agent closes
  description: Looks entries up, and answers with what it has when its lookups run out.
  uses ledger
  gives found: list of text
  at most 2 tool calls
  when it runs out: answer with what it has

  when the agent has taken more than 1 steps
    called be-brief
    remind it: Keep the answer to one line.

  instructions: Look up what you are asked about in the ledger.
"""


def look(entry: str) -> Turn:
    return Turn("", (ToolCall("ledger", {"action": "look", "entry": entry}),))


class Heard(ReferenceTransport):
    """A scripted model that keeps the system text of each request it is sent."""

    def __init__(self, script: Script, told: list[str]) -> None:
        super().__init__(script)
        self.told = told

    async def model_call(self, system, history, tools):  # type: ignore[override]
        self.told.append(f"{len(tools)} tools\n{system}")
        return await super().model_call(system, history, tools)


def go(tmp_path: Path, agent: str, turns: list[Turn], **kw: Any):
    (tmp_path / "lookups.pact").write_text(WORKSPACE, encoding="utf-8")
    spec = AgentSpec.from_document(shown(tmp_path), agent)
    looked: list[str] = []
    told: list[str] = []

    def ledger(args: dict[str, Any]) -> str:
        looked.append(str(args.get("entry")))
        return "entry found"

    def again(**more: Any):
        return asyncio.run(
            run(spec, Heard(Script(turns), told), "Look up five things.", {"ledger": ledger}, **more)
        )

    return again(**kw), again, looked, told


FIVE = [look("a"), look("b"), look("c"), look("d"), look("e"), Turn("All five are there.")]


def test_a_yes_grants_the_same_budget_again_and_a_second_yes_the_same_again(tmp_path: Path) -> None:
    out, again, looked, _ = go(tmp_path, "asks", FIVE)
    assert out.halted == "suspended" and looked == ["a", "b"]
    first = out.suspension
    out = again(resume=first, answer=first.answer(**{"go-on": "yes"}), now=1.0)
    # Two more, and then the same question: a second continuation is a second
    # decision, not a budget with no ceiling.
    assert out.halted == "suspended" and looked == ["a", "b", "c", "d"]
    second = out.suspension
    assert second.budget["tool_calls_at_most"] == 4
    out = again(resume=second, answer=second.answer(**{"go-on": "yes"}), now=2.0)
    assert out.halted == "final" and out.output == "All five are there."
    assert looked == ["a", "b", "c", "d", "e"]


def test_a_no_ends_the_run_and_nothing_more_is_looked_up(tmp_path: Path) -> None:
    out, again, looked, _ = go(tmp_path, "asks", FIVE)
    parked = out.suspension
    out = again(resume=parked, answer=parked.answer(**{"go-on": "no"}), now=1.0)
    assert out.halted == "out-of-budget" and looked == ["a", "b"]


LOOKUPS = "the limit you set with `tool-calls-at-most` (2 of 2 tool calls)"


def test_a_run_a_person_refused_says_which_limit_and_that_somebody_said_no(tmp_path: Path) -> None:
    """It handed back the model's last words. This model's last reply was two
    tool calls and no words, so the person who said no was shown `""`."""
    out, again, _, _ = go(tmp_path, "asks", FIVE)
    parked = out.suspension
    out = again(resume=parked, answer=parked.answer(**{"go-on": "no"}), now=1.0)
    assert out.output == (
        f"Stopped before finishing: this run reached {LOOKUPS}. "
        "A person was asked and said not to keep going."
    )
    # Not "Waiting for a person": nobody is being waited for any more.
    assert "Waiting" not in out.output
    assert out.stopped_by is not None and out.stopped_by.ceiling.field == "tool-calls-at-most"


def test_nobody_answering_in_time_is_not_reported_as_a_person_saying_no(tmp_path: Path) -> None:
    """`answer-within: 1h` and `if-nobody-answers: decline`. The run ends the
    same way, and the sentence does not invent somebody who refused."""
    out, again, looked, _ = go(tmp_path, "asks", FIVE, now=0.0)
    assert out.suspension.waits_for == 3600.0
    out = again(resume=out.suspension, now=2 * 3600.0)
    assert out.halted == "out-of-budget" and looked == ["a", "b"]
    assert out.output == (
        f"Stopped before finishing: this run reached {LOOKUPS}. "
        "A person was asked and nobody answered in time."
    )


def test_the_limit_named_after_a_no_is_the_one_that_stopped_the_run(tmp_path: Path) -> None:
    """Two ceilings reached together. The second step asks for two lookups;
    the first is the second lookup allowed and the other is not run. The run
    is then at `steps-at-most: 2` AND `tool-calls-at-most: 2`, and it was the
    lookups that stopped it. Worked out again afterwards, the step ceiling
    comes first in the fixed order and would be named instead."""
    two = Turn("", (look("b").tool_calls[0], look("c").tool_calls[0]))
    out, again, looked, _ = go(tmp_path, "both", [look("a"), two, Turn("Done.")])
    parked = out.suspension
    assert looked == ["a", "b"] and parked.reached["field"] == "tool-calls-at-most"
    # Across a process, as a host would hold it.
    parked = Suspension.from_json(parked.to_json())
    out = again(resume=parked, answer=parked.answer(**{"go-on": "no"}), now=1.0)
    assert LOOKUPS in out.output and "steps-at-most" not in out.output


def test_a_no_after_a_yes_names_the_figures_the_run_had_been_raised_to(tmp_path: Path) -> None:
    """Two lookups, a yes, two more, a no. The second stop is at four of four,
    and that is what the sentence says — not the two of two of the first."""
    out, again, looked, _ = go(tmp_path, "asks", FIVE)
    first = out.suspension
    out = again(resume=first, answer=first.answer(**{"go-on": "yes"}), now=1.0)
    second = out.suspension
    assert second.reached["at"] == 4 and second.reached["limit"] == 4
    out = again(resume=second, answer=second.answer(**{"go-on": "no"}), now=2.0)
    assert out.halted == "out-of-budget" and looked == ["a", "b", "c", "d"]
    assert "`tool-calls-at-most` (4 of 4 tool calls)" in out.output


def test_a_pause_written_before_it_recorded_the_limit_still_names_one(tmp_path: Path) -> None:
    """A pause from before `reached` existed has none. The ceiling is worked
    out again from what the run had spent, which is right wherever only one
    ceiling was reached."""
    import json

    out, again, _, _ = go(tmp_path, "asks", FIVE)
    old = json.loads(out.suspension.to_json())
    del old["reached"]
    parked = Suspension.from_json(json.dumps(old))
    assert parked.reached == {}
    out = again(resume=parked, answer=parked.answer(**{"go-on": "no"}), now=1.0)
    assert LOOKUPS in out.output and out.output.endswith("said not to keep going.")


def test_an_old_pause_under_a_limit_since_raised_names_no_figure_it_cannot_know(
    tmp_path: Path,
) -> None:
    """The one case with no ceiling to name: a pause that recorded none, and a
    file edited to allow more while the run waited. It still says what
    happened, and makes up no figure."""
    import json

    out, _, _, _ = go(tmp_path, "asks", FIVE)
    old = json.loads(out.suspension.to_json())
    del old["reached"]
    parked = Suspension.from_json(json.dumps(old))
    (tmp_path / "lookups.pact").write_text(
        WORKSPACE.replace("tool-calls-at-most: 2\n    when-it-runs-out: ask-a-person\n    asks: keep-looking\n  instructions", "tool-calls-at-most: 9\n    when-it-runs-out: ask-a-person\n    asks: keep-looking\n  instructions", 1),
        encoding="utf-8",
    )
    raised = AgentSpec.from_document(shown(tmp_path), "asks")
    assert raised.limits.tool_calls_at_most == 9
    out = asyncio.run(
        run(raised, ReferenceTransport(Script(FIVE)), "Look up five things.", {"ledger": lambda a: "x"},
            resume=parked, answer=parked.answer(**{"go-on": "no"}), now=1.0)
    )
    assert out.halted == "out-of-budget" and out.stopped_by is None
    assert out.output == (
        "Stopped before finishing: this run reached a limit and asked whether to keep "
        "going. A person said not to."
    )


def test_the_closing_request_says_a_limit_was_reached_and_which_calls_were_not_made(
    tmp_path: Path,
) -> None:
    """No tools offered is not a message. A live model sent this request with
    no word why its tools had gone wrote a third tool result itself, for a
    lookup never made, and that was the run's answer (five runs of five on
    gpt-4o-mini; none of five once it was told)."""
    three = Turn("", tuple(look(e).tool_calls[0] for e in ("b", "c", "d")))
    out, _again, looked, told = go(tmp_path, "closes", [look("a"), three, Turn('{"found": ["a", "b"]}')])
    assert looked == ["a", "b"] and out.halted == "tool-call-limit"
    closing = told[-1]
    assert closing.startswith("0 tools\n")
    assert closing.endswith(
        "This run has reached its limit, `tool-calls-at-most` (2 of 2 tool calls). "
        "No tool can be called any more.\n"
        "These calls you asked for were NOT made and have no result: "
        'ledger {"action": "look", "entry": "c"}; ledger {"action": "look", "entry": "d"}.\n'
        "Answer now, from the results you already have. Say plainly what you did not "
        "get to. Never write a tool's result yourself."
    )
    # Only the closing request is told so.
    assert all("has reached its limit" not in earlier for earlier in told[:-1])


def test_a_run_stopped_between_replies_has_no_call_to_report_as_not_made(tmp_path: Path) -> None:
    out, _again, looked, told = go(tmp_path, "closes", [look("a"), look("b"), Turn('{"found": ["a", "b"]}')])
    assert looked == ["a", "b"] and out.halted == "tool-call-limit"
    assert "has reached its limit, `tool-calls-at-most` (2 of 2 tool calls)" in told[-1]
    assert "NOT made" not in told[-1]


def test_after_a_yes_the_model_is_told_once_which_calls_were_not_made(tmp_path: Path) -> None:
    """Five lookups asked for in one reply, two allowed, and a person says
    yes. Nothing in front of the model says three of its calls were never
    made. On a small live model that cost the answer: it blamed the limit a
    person had just raised, or repeated lookups it already had. Told which
    calls were not made, it made those (ten runs of ten)."""
    five = Turn("", tuple(look(e).tool_calls[0] for e in "abcde"))
    out, again, looked, told = go(tmp_path, "asks", [five, look("c"), look("d"), Turn("Done.")])
    parked = out.suspension
    assert looked == ["a", "b"] and len(told) == 1
    assert [c["args"]["entry"] for c in parked.reached["not-made"]] == ["c", "d", "e"]
    # Across a process, as a host would hold it.
    parked = Suspension.from_json(parked.to_json())
    out = again(resume=parked, answer=parked.answer(**{"go-on": "yes"}), now=1.0)
    assert looked == ["a", "b", "c", "d"]
    assert told[1].endswith(
        "A person was asked and said to keep going. The limit this run had reached, "
        "`tool-calls-at-most` (2 of 2 tool calls), is now 4 tool calls.\n"
        "These calls you asked for were not made and can be made now: "
        'ledger {"action": "look", "entry": "c"}; ledger {"action": "look", "entry": "d"}; '
        'ledger {"action": "look", "entry": "e"}.\n'
        "Do not repeat a call that already has a result."
    )
    # Once. The request after it is told nothing of the kind.
    assert len(told) == 3 and "said to keep going" not in told[2]


def test_a_no_tells_the_model_nothing(tmp_path: Path) -> None:
    out, again, _, told = go(tmp_path, "asks", FIVE)
    parked = out.suspension
    again(resume=parked, answer=parked.answer(**{"go-on": "no"}), now=1.0)
    assert all("said to keep going" not in request for request in told)


def test_the_sentence_for_a_refusal_carries_what_the_person_said() -> None:
    """`Reached.declined` is the one place this is worded, for every runtime.
    A question that asks for a reason passes it in; PACT's own default step
    ceiling is not called "the limit you set"."""
    from pact_adapters.limits import Action, Limits, Meter, Reached, step_ceiling

    reached = Limits(tool_calls_at_most=2, when_it_runs_out=Action.ASK).reached(
        Meter(tool_calls=2), 0.0
    )
    assert reached is not None
    assert reached.declined("  The month is closed.  ") == (
        f"Stopped before finishing: this run reached {LOOKUPS}. "
        "A person was asked and said not to keep going. The month is closed."
    )
    default = Reached(step_ceiling(8, default=True), 8.0, Action.ASK).declined()
    assert default.startswith("Stopped before finishing: this run reached PACT's default limit, ")
    assert "the limit you set" not in default
    assert default.endswith("A person was asked and said not to keep going.")


def test_a_budget_once_granted_is_carried_by_the_park_and_across_a_process(tmp_path: Path) -> None:
    out, again, looked, _ = go(tmp_path, "asks", FIVE)
    first = out.suspension
    assert first.budget == {}, "nobody has said keep going yet"
    out = again(resume=first, answer=first.answer(**{"go-on": "yes"}), now=1.0)
    second = out.suspension
    # What was granted is in the park itself, and survives being written down.
    assert second.budget["tool_calls_at_most"] == 4 and "steps" in second.budget
    carried = Suspension.from_json(second.to_json())
    assert carried.budget == second.budget
    # Resumed from the written-down park with no answer yet, the run is still
    # under the raised ceiling and waits; it has not reverted to the one
    # written (2), which it is already past.
    out = again(resume=carried, answer=carried.answer(**{"go-on": "yes"}), now=2.0)
    assert out.halted == "final" and looked == ["a", "b", "c", "d", "e"]


def test_the_closing_request_is_told_what_every_other_request_is_told(tmp_path: Path) -> None:
    turns = [look("a"), look("b"), Turn("a and b are there.")]
    out, _again, looked, told = go(tmp_path, "closes", turns)
    assert out.halted == "tool-call-limit" and looked == ["a", "b"]
    assert out.output == "a and b are there."
    closing = told[-1]
    assert closing.startswith("0 tools\n"), "the closing request offers no tool"
    # The agent's own instructions, the shape its answer must have, and what
    # its reaction had reminded it of — as the request before it was told.
    assert "Look up what you are asked about in the ledger." in closing
    assert "found" in closing and "found" in told[-2]
    assert "Keep the answer to one line." in told[-2]
    assert "Keep the answer to one line." in closing
