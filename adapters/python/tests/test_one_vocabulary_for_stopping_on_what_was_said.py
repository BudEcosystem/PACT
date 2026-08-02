"""Something that constrains what the agent SAYS (A1, F7).

The gap ten cold authors hit first, and the one the format had no answer to.
Every ceiling, gate and redaction bounds what an agent DOES: how many steps, how
much money, which tools, which values are hidden. Nothing bounded what it said.
A clinic desk that must never give medical advice, a bank desk that must never
promise a rate — the single most-wanted rule in the trial — was not expressible.

The root cause was one sentence short. Both stopping sentences count tool calls
and are pinned to `step.tool.before`, so `may: [stop-the-run]` at
`turn.message.after` was a power nothing could use: R24's own defect surviving
inside the list R24 was applied to.

This is the sixth sentence, and its condition reads the answer.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Rule, _breaks  # noqa: E402
from pact_adapters.harness import RunResult, run  # noqa: E402
from pact_adapters.interceptors import Chain, InterceptorError, said_any  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

RULE = (
    'if the answer mentions "diagnosis", "prescription", "dosage", '
    'stop and say "A nurse will call you back about anything clinical."'
)


def document(when: str = "turn.message.after", rules: list[str] | None = None) -> dict:
    return {
        "agents": {"desk": {"interceptors": ["no-medical-advice"]}},
        "interceptors": {
            "no-medical-advice": {
                "description": "This desk books appointments; it does not advise.",
                "when": when,
                "may": ["stop-the-run"],
                "rules": rules if rules is not None else [RULE],
            }
        },
    }


def test_a_rule_can_stop_the_run_on_what_the_agent_said() -> None:
    chain = Chain.from_document(document(), "desk")
    _, decision = chain.run("turn.message.after", {"content": "Your diagnosis is a sprain."})
    assert decision.stop == "A nurse will call you back about anything clinical."


def test_an_answer_that_says_none_of_the_words_goes_through_untouched() -> None:
    chain = Chain.from_document(document(), "desk")
    out, decision = chain.run("turn.message.after", {"content": "Booked you in for Tuesday."})
    assert decision.stop is None
    assert out["content"] == "Booked you in for Tuesday."


def test_what_the_author_wrote_becomes_the_reply_the_customer_reads() -> None:
    """`result.output = decision.stop`, so the words in the rule are not a log
    line — they are what the person on the other end sees. The help says so."""
    spec = AgentSpec(name="Desk", description="Books", instructions="Book it.")
    script = Script([Turn("Your diagnosis is a sprain; take ibuprofen.", ())])
    chain = Chain.from_document(document(), "desk")
    r: RunResult = asyncio.run(
        run(spec, ReferenceTransport(script), "my ankle hurts", {}, chain=chain)
    )
    assert r.output == "A nurse will call you back about anything clinical."
    assert "diagnosis" not in (r.output or "")


def test_the_match_is_case_folded_and_a_prefix_catches_the_whole_family() -> None:
    chain = Chain.from_document(
        document(rules=['if the answer mentions "diagnos", stop and say "no"']), "desk"
    )
    for said in ("Your DIAGNOSIS is clear", "I diagnosed a sprain", "diagnostic imaging"):
        _, d = chain.run("turn.message.after", {"content": said})
        assert d.stop == "no", said


@pytest.mark.parametrize("when", ["step.tool.before", "step.delegate.before"])
def test_a_moment_that_carries_no_answer_is_refused_where_it_is_written(when: str) -> None:
    """The condition reads what came back, so a moment with no answer to read
    would load and do nothing — the failure this vocabulary exists to refuse."""
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(document(when=when), "desk")
    assert "would do nothing" in str(e.value)
    assert "turn.message.after" in str(e.value), "the fix names a moment that works"


def test_a_rule_about_the_incoming_message_is_not_this_rule() -> None:
    """`step.message.before` carries `content` too, and it is the CUSTOMER's.
    A rule about what the agent says must not fire on what was said to it."""
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(document(when="step.message.before"), "desk")
    assert "would do nothing" in str(e.value)


def test_a_rule_naming_no_words_is_refused_with_the_shape_to_type() -> None:
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(
            document(rules=['if the answer mentions nothing at all, stop and say "no"']), "desk"
        )
    assert "not a rule PACT knows" in str(e.value) or "names no words" in str(e.value)


def test_stopping_on_a_word_needs_the_power_to_stop() -> None:
    doc = document()
    doc["interceptors"]["no-medical-advice"]["may"] = ["hide-values"]
    with pytest.raises(InterceptorError) as e:
        Chain.from_document(doc, "desk")
    assert "stop-the-run" in str(e.value)


def test_a_live_stop_and_a_graded_case_use_the_same_words_for_the_same_act() -> None:
    """One matcher, two acts. An author who has written `must-not-contain:` in
    `evals/` has written the live rule, and the two cannot drift because there
    is one function."""
    words = ("diagnosis", "dosage")
    text = "your diagnosis is a sprain"
    assert said_any(words, text) == ["diagnosis"]
    # ...and the eval rule reaches the same verdict through the same call.
    broke = _breaks(Rule("must-not-contain", words), RunResult(output=text), text)
    assert "diagnosis" in broke, broke
    assert _breaks(Rule("must-not-contain", words), RunResult(output="booked"), "booked") == ""

    # The case that tells a SHARED matcher from two that happen to agree: the
    # author wrote the word capitalised. Folding only the haystack and not the
    # needle is the obvious way to write this by hand, and it is wrong in the
    # direction that matters — the rule silently stops catching anything.
    shouty = ("Diagnosis",)
    assert said_any(shouty, text) == ["Diagnosis"], "the needle is folded too"
    assert "Diagnosis" in _breaks(Rule("must-not-contain", shouty), RunResult(output=text), text)
