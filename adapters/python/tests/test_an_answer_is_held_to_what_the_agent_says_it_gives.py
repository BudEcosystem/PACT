"""An agent's answer is held to what the agent says it gives.

`answers-with:` is a promise to whoever calls the agent: a workflow stage that
binds `steps.decide.amount`, a program that reads the field, a person shown it.
The harness put the shape to the model and then handed back whatever came:
"Sure, I think we should refund them." from an agent that gives a decision and
an amount was the run's answer, `halted: final`, and the caller found out when
it read a field that was not there. `checked-by:`, the author's own rules for
an answer, was read by nothing in this loop: the run SAID so (`unenforced`)
and returned the answer unchecked.

The owner's ruling (14 November): "if there is a promised shape, it must be
honored." What is held, and how (`answers_fit`, ruled with Bud Agent Flow):

* a field left out, or a value its shape refuses, does not fit;
* the model is asked again and told what was wrong, in the author's own words
  for the shape, at its next request and at no other;
* at most `checks-at-most:` times in all, 2 unwritten, one count for the shape
  and for `checked-by:`, and the closing answer of a run that reached a limit
  spends from it too;
* still not fitting, the run ends `checks-failed` and hands back no answer;
* a field the agent does not declare is not a reason to ask again and is not
  handed back; an empty reply that arrived is an attempt.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.answers_fit import (  # noqa: E402
    CHECK_FAILED,
    CHECKS_FAILED,
    DID_NOT_FIT,
    Held,
    does_not_fit,
    fields_of,
)
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import RAN_OUT  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.suspension import Suspension  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from trees import shown  # noqa: E402

WORKSPACE = """\
workspace "Refunds"
  description: A desk that decides refunds, and says what it decided.

resource office
  resource-kind: mcp-server
  endpoint: host/office
  description: Where the orders are reached.

tool orders
  description: The order book.
  connect: office
  actions:
    look:
      description: Read one order.
      reads-only: yes
      takes:
        order: text
    refund:
      description: Refund one order.
      needs-a-person: yes
      takes:
        order: text

agent desk
  description: Decides a refund request.
  uses orders
  gives decision: one of approved, declined, amount: money, note: text, optional
  instructions: Decide the refund.

agent strict
  description: Decides a refund request, and gets one try at saying so.
  gives decision: one of approved, declined
  checks-at-most: 1
  instructions: Decide the refund.

agent ruled
  description: Decides a refund request and must say what happens to the money.
  gives decision: one of approved, declined
  checked-by:
    - must-contain: [refund]
      because: say what happens to the money
  instructions: Decide the refund.

agent only-ruled
  description: Says what happens to the money, in its own words.
  checked-by:
    - must-contain: [refund]
  checks-at-most: 3
  instructions: Say what happens to the money.

agent free
  description: Promises nothing about its answer.
  instructions: Help.

agent closes
  description: Looks orders up, and answers with what it has when it runs out.
  uses orders
  gives decision: one of approved, declined
  at most 1 tool calls
  when it runs out: answer with what it has
  instructions: Decide the refund.
"""

GOOD = "The item arrived broken.\\n- decision: approved\\n- amount: 45 USD".replace("\\n", "\n")
VAGUE = "Sure, I think we should refund them."


class Counted(ReferenceTransport):
    """A scripted model that answers by how many times it has been ASKED, and
    keeps the system text of each request. By count and not by the
    conversation (`Script`'s way), because a closing request and the request
    before it are sent the same conversation: only the count tells them apart."""

    def __init__(self, turns: list[Turn], told: list[str]) -> None:
        super().__init__(Script(turns))
        self.turns, self.told = turns, told

    async def model_call(self, system, history, tools):  # type: ignore[override]
        turn = self.turns[min(len(self.told), len(self.turns) - 1)]
        self.told.append(system)
        return turn.text, list(turn.tool_calls)


class Asked:
    def __init__(self, told: list[str]) -> None:
        self.told = told

    @property
    def calls(self) -> int:
        return len(self.told)


def go(tmp_path: Path, agent: str, turns: list[str | Turn], **kw: Any):
    (tmp_path / "refunds.pact").write_text(WORKSPACE, encoding="utf-8")
    spec = AgentSpec.from_document(shown(tmp_path), agent)
    told: list[str] = []
    scripted = [t if isinstance(t, Turn) else Turn(t) for t in turns]
    tools = {"orders": lambda args: "order 7: 45 USD, delivered broken"}

    def again(**more: Any):
        return asyncio.run(
            run(spec, Counted(scripted, told), "Order 7 arrived broken.", tools, **more)
        )

    return again(**kw), told, Asked(told), again


# ── an answer that fits ──────────────────────────────────────────────────────


def test_an_answer_that_fits_is_the_answer_and_its_fields_are_handed_back(tmp_path: Path) -> None:
    out, told, script, _ = go(tmp_path, "desk", [GOOD])
    assert out.halted == "final" and out.output == GOOD
    assert out.answer == {"decision": "approved", "amount": "45 USD"}
    assert script.calls == 1, "nothing was asked twice"
    assert DID_NOT_FIT not in told[0]


def test_an_optional_field_left_out_fits_and_one_the_agent_does_not_declare_is_dropped(
    tmp_path: Path,
) -> None:
    said = GOOD + "\n- mood: cheerful"
    out, _, script, _ = go(tmp_path, "desk", [said])
    assert out.halted == "final" and script.calls == 1, "an extra field is no reason to ask again"
    assert out.output == said, "the reply is the model's, as written"
    assert out.answer == {"decision": "approved", "amount": "45 USD"}, "and it is not handed back"


def test_an_answer_written_as_one_json_record_fits_too(tmp_path: Path) -> None:
    out, _, _, _ = go(tmp_path, "desk", ['{"decision": "declined", "amount": "0 USD", "x": 1}'])
    assert out.halted == "final"
    assert out.answer == {"decision": "declined", "amount": "0 USD"}


# ── one that does not ────────────────────────────────────────────────────────


def test_an_answer_that_does_not_fit_is_asked_for_again_and_told_why(tmp_path: Path) -> None:
    out, told, script, _ = go(tmp_path, "desk", [VAGUE, GOOD])
    assert out.halted == "final" and out.output == GOOD
    assert out.answer == {"decision": "approved", "amount": "45 USD"}
    assert script.calls == 2
    # Told at the second request, last, in the author's words for each field.
    assert DID_NOT_FIT not in told[0]
    assert told[1].endswith(
        "Your last answer did not fit what your answer must contain:\n"
        "- `decision` is missing. It should be: one of approved, declined.\n"
        "- `amount` is missing. It should be: money.\n"
        "Answer again, with every field as it is asked for."
    ), told[1][-400:]
    # `note` is optional, so it is not named. And both replies are on the record.
    assert "`note`" not in told[1]
    assert [s.text for s in out.steps] == [VAGUE, GOOD]


def test_a_value_the_shape_refuses_is_named_with_what_it_should_be(tmp_path: Path) -> None:
    out, told, _, _ = go(tmp_path, "desk", ["- decision: maybe\n- amount: 45 USD", GOOD])
    assert out.halted == "final"
    assert "- `decision` " in told[1] and "approved, declined" in told[1] and "maybe" in told[1]
    assert "`amount`" not in told[1], "the field that fit is not complained about"


def test_it_is_told_once_and_no_request_after_that(tmp_path: Path) -> None:
    # Misfit, then a tool call, then the answer: the notice is in the request
    # that follows the misfit and in no other.
    look = Turn("", (ToolCall("orders", {"action": "look", "order": "7"}),))
    out, told, _, _ = go(tmp_path, "desk", [VAGUE, look, GOOD])
    assert out.halted == "final", out.output
    assert [DID_NOT_FIT in t for t in told] == [False, True, False]


def test_still_not_fitting_the_run_ends_checks_failed_and_hands_back_nothing(tmp_path: Path) -> None:
    out, told, script, _ = go(tmp_path, "desk", [VAGUE, VAGUE, GOOD])
    assert out.halted == CHECKS_FAILED
    assert script.calls == 2, "`checks-at-most:` is 2 unwritten: two attempts in all, no third"
    assert out.answer == {}
    assert out.output == (
        "Stopped without an answer: it was asked for its answer 2 times and none fit "
        "`answers-with:`. In the last one:\n"
        "- `decision` is missing. It should be: one of approved, declined.\n"
        "- `amount` is missing. It should be: money."
    )
    # What it wrote is in the steps, for whoever has to find out why.
    assert [s.text for s in out.steps] == [VAGUE, VAGUE]


def test_checks_at_most_one_fails_at_the_first_miss(tmp_path: Path) -> None:
    out, _, script, _ = go(tmp_path, "strict", [VAGUE, "- decision: approved"])
    assert out.halted == CHECKS_FAILED and script.calls == 1
    assert out.output.startswith(
        "Stopped without an answer: it was asked for its answer once and it did not fit "
        "`answers-with:`."
    )


def test_an_empty_reply_that_arrived_is_an_attempt(tmp_path: Path) -> None:
    out, _, script, _ = go(tmp_path, "strict", ["", "- decision: approved"])
    assert out.halted == CHECKS_FAILED and script.calls == 1


def test_an_agent_that_promises_nothing_is_held_to_nothing(tmp_path: Path) -> None:
    out, _, script, _ = go(tmp_path, "free", [""])
    assert out.halted == "final" and out.output == "" and out.answer == {}
    assert script.calls == 1


# ── the author's own rules, from the same count ──────────────────────────────


def test_a_rule_an_answer_breaks_is_told_and_the_answer_asked_for_again(tmp_path: Path) -> None:
    out, told, script, _ = go(
        tmp_path, "ruled", ["- decision: approved", "A refund is on its way.\n- decision: approved"]
    )
    assert out.halted == "final" and script.calls == 2
    assert told[1].endswith(
        f"{CHECK_FAILED}does not say ['refund'] (say what happens to the money). "
        "Answer again so that it keeps every rule."
    ), told[1][-300:]
    assert all("checked-by" not in u for u in out.unenforced), "it is held now, not reported"


def test_the_shape_and_the_rules_spend_from_one_count(tmp_path: Path) -> None:
    # First it does not fit; then it fits and breaks the rule. Two attempts in
    # all, so that is the end: it does not get two for each.
    out, _, script, _ = go(tmp_path, "ruled", [VAGUE, "- decision: approved", GOOD])
    assert out.halted == CHECKS_FAILED and script.calls == 2
    assert out.output == (
        "Stopped without an answer: it was asked for its answer 2 times and none kept its "
        "`checked-by:` rules. The last one does not say ['refund'] (say what happens to the "
        "money)."
    )


def test_rules_alone_hold_an_answer_that_promises_no_shape(tmp_path: Path) -> None:
    out, _, script, _ = go(tmp_path, "only-ruled", ["Sorry.", "Sorry again.", "We will refund it."])
    assert out.halted == "final" and script.calls == 3 and out.answer == {}


# ── a run that reached a limit ───────────────────────────────────────────────


LOOK = Turn("", (ToolCall("orders", {"action": "look", "order": "7"}),))


def test_a_closing_answer_that_fits_is_the_answer(tmp_path: Path) -> None:
    out, told, asked, _ = go(tmp_path, "closes", [LOOK, "- decision: approved"])
    assert out.halted in RAN_OUT and out.stopped_by is not None
    assert out.output == "- decision: approved" and out.answer == {"decision": "approved"}
    assert asked.calls == 2, "one step, which used the one call, and one closing request"


def test_a_closing_answer_that_does_not_fit_is_asked_for_again_with_no_tools(tmp_path: Path) -> None:
    out, told, _, _ = go(tmp_path, "closes", [LOOK, VAGUE, "- decision: declined"])
    assert out.halted in RAN_OUT, "it did run out, and still says so"
    assert out.answer == {"decision": "declined"}
    # The second closing request is the first, and then why.
    assert told[-1].startswith(told[-2]) and told[-1].endswith(
        "Answer again, with every field as it is asked for."
    )


def test_a_closing_answer_that_never_fits_is_not_handed_back(tmp_path: Path) -> None:
    out, _, _, _ = go(tmp_path, "closes", [LOOK, VAGUE, VAGUE, "- decision: declined"])
    # The ceiling's own word, because it did run out; and no answer.
    assert out.halted in RAN_OUT and out.halted != CHECKS_FAILED
    assert out.answer == {}
    assert out.output == (
        "Stopped before finishing: this run reached the limit you set with "
        "`tool-calls-at-most` (1 of 1 tool calls). It was asked for its answer 2 times and "
        "none fit what it says it gives."
    )


# ── across a pause ───────────────────────────────────────────────────────────


def test_a_run_that_parks_between_two_attempts_is_not_given_the_count_again(tmp_path: Path) -> None:
    # A miss, then a call a person must approve, then two more misses. With the
    # count lost at the pause, the run would be asked a third time.
    refund = Turn("", (ToolCall("orders", {"action": "refund", "order": "7"}),))
    out, _, script, again = go(tmp_path, "desk", [VAGUE, refund, VAGUE, GOOD])
    assert out.halted == "suspended", (out.halted, out.output)
    parked = Suspension.from_json(out.suspension.to_json())
    assert parked.used["answers-asked-for"] == 1
    resumed = again(resume=parked, answer=parked.answer(**{n.name: "yes" for n in parked.asks}))
    assert resumed.halted == CHECKS_FAILED, (resumed.halted, resumed.output)
    assert "2 times" in resumed.output


# ── the reader itself ────────────────────────────────────────────────────────


def test_fields_are_read_off_their_own_lines_the_last_one_winning() -> None:
    shape = {"decision": "one of approved, declined", "items": "list of text"}
    said = "decision: declined\nOn reflection:\n**decision**: approved\n* items: [\"a\", \"b\"]\nother: x"
    assert fields_of(said, shape) == {"decision": "approved", "items": ["a", "b"]}
    assert does_not_fit(said, shape) == ()
    assert fields_of("nothing here", shape) == {}


def test_a_hold_with_nothing_to_hold_counts_nothing() -> None:
    held = Held()
    assert held.wrong("") == "" and held.asked == 0 and not held.holds_anything


def test_a_field_that_streams_is_the_reply_itself() -> None:
    # `reply: stream of text` is what the reply IS as it arrives. Nobody ends a
    # stream with `- reply: ...`; only saying nothing leaves it out.
    shape = {"reply": "stream of text"}
    assert does_not_fit("The total is 42.", shape) == ()
    assert fields_of("The total is 42.", shape) == {"reply": "The total is 42."}
    assert does_not_fit("", shape) == ("`reply` is missing. It should be: stream of text.",)
    both = {"reply": "stream of text", "total": "number"}
    assert does_not_fit("The total is 42.", both) == ("`total` is missing. It should be: number.",)
    assert fields_of("The total is 42.\n- total: 42", both)["total"] == "42"
