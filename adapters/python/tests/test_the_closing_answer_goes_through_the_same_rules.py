"""A run that ran out of steps is still a run whose answer the rules see (B3).

`_finish`'s own docstring states the guarantee, word for word:

    Routed through `turn.message.after` like every other reply, so a redaction
    rule cannot be escaped by finishing from a stage rather than by running out
    of steps.

Running out of steps was the escape. `when-it-runs-out: answer-with-what-it-has`
made one closing model call, set `result.output` from it, and emitted
`turn.message.completed` — with no `chain.run` anywhere on the path. A card
number an author forbade in an answer arrived whole in the one answer nobody
planned for, and the longer and more expensive the run, the likelier it was to
be this one.

The second guarantee here is the one the fix could easily have broken: a rule
firing on the way past must not make the ceiling unreportable. `limits.RAN_OUT`
is the set a caller asks "did it run out?" with, and this run did run out. So a
stop rule changes the WORDS and never `halted`.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.interceptors import Chain, guard  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.limits import Action, Limits  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"), ToolSpec("payments", "issue a refund")),
)
TOOLS = {"zendesk": lambda a: "lamp, broken", "payments": lambda a: "refunded"}

#: The card number is in the CLOSING answer only — the one made with no tools
#: offered, after the ceiling. A transport that leaked it earlier would prove
#: nothing about the path under test.
CARD = "4111 1111 1111 1111"


class LeaksOnTheWayOut(ReferenceTransport):
    """Calls a tool while it has one, and reads out a card number when it has none.

    This is what withholding tools does to a model, and it is what makes
    `answer-with-what-it-has` a real behaviour rather than a relabelled stop.
    """

    name = "leaks-on-the-way-out"

    async def model_call(self, system, history, tools):
        if not tools:
            return f"Refund issued to card {CARD}.", []
        return "still working", [ToolCall("zendesk", {})]


def never_finishes() -> Script:
    """A model that keeps calling a tool — the shape a ceiling exists for."""
    return Script([Turn("still working", (ToolCall("zendesk", {}),))])


def hiding_chain() -> Chain:
    """The author's own file, through the only path in."""
    return Chain.from_document(
        {
            "agents": {"a": {"interceptors": ["redact"]}},
            "interceptors": {
                "redact": {
                    "description": "Never read a card number back to anybody.",
                    "when": "turn.message.after",
                    "may": ["hide-values"],
                    "rules": ['replace anything that looks like a card number with "***"'],
                }
            },
        },
        "a",
    )


def ran_out_answering(chain: Chain):
    spec = replace(SPEC, max_steps=2, limits=Limits(when_it_runs_out=Action.ANSWER))
    return asyncio.run(run(spec, LeaksOnTheWayOut(never_finishes()), "hello", TOOLS, chain=chain))


def test_a_card_number_in_the_answer_at_the_step_ceiling_is_still_hidden() -> None:
    r = ran_out_answering(hiding_chain())
    assert r.halted == "step-limit", r.halted
    assert CARD not in (r.output or ""), (
        "the closing answer escaped the rule that exists to hide this: " + str(r.output)
    )
    assert "***" in (r.output or ""), r.output


def test_the_recorded_step_is_hidden_too_and_not_only_the_answer() -> None:
    """A redaction visible in the reply and not in the trace is a redaction in
    name only — the trace is what a reviewer reads afterwards."""
    r = ran_out_answering(hiding_chain())
    assert not any(CARD in s.text for s in r.steps), [s.text for s in r.steps]


def test_the_ceiling_is_still_reported_when_a_rule_stops_the_closing_answer() -> None:
    """The half the fix could have broken. `limits.RAN_OUT` is the set a caller
    asks "did it run out?" with, and a stop rule firing on the way past must not
    make the ceiling unreportable: the run did both."""
    chain = Chain()
    chain.add(guard("no-advice", "turn.message.after", lambda p: "A nurse will call you back."))
    r = ran_out_answering(chain)
    assert r.halted == "step-limit", "the ceiling must survive the rule: " + str(r.halted)
    assert r.stopped_by is not None
    assert r.stopped_by.ceiling.field == "steps-at-most"
    assert r.output == "A nurse will call you back."


def test_a_stopped_closing_answer_does_not_survive_in_the_trace() -> None:
    chain = Chain()
    chain.add(guard("no-advice", "turn.message.after", lambda p: "A nurse will call you back."))
    r = ran_out_answering(chain)
    assert not any(CARD in s.text for s in r.steps), [s.text for s in r.steps]


def test_with_no_rules_at_all_the_closing_answer_is_unchanged() -> None:
    """The tightening must not cost the ordinary case anything."""
    r = ran_out_answering(Chain())
    assert r.halted == "step-limit"
    assert r.output == f"Refund issued to card {CARD}."
