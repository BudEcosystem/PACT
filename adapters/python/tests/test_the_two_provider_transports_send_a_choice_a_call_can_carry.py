"""The per-call `tool-choice:` question, on the two transports that never asked it.

`settings.tool-choice`'s help says *"auto, required, none, or one tool name"*, and
three of those four are answers about the tools **this call offers**.
`apply_settings` is asked ONCE, before the loop, so it cannot be where that is
decided — `transports/_tool_choice.py` sets the argument out in full, and five of
the seven transports that map the key decide it per call through `can_choose`.

Two did not: `anthropic_transport.py` and `ollama_transport.py`, the two bound to
a PROVIDER rather than to a framework. Both spread their `_WIRE` table into the
request unconditionally, so an authored `tool-choice:` went out on every call
including the ones that offer no tools at all.

**Why that is a live defect and not an untidiness.** `harness.run` closes every
ceiling-terminated run with `transport.model_call(spec.instructions, history,
[])` — no tools, deliberately, so a run that hit a spend cap answers from what it
already has — and a stage narrows the set besides. On both of these surfaces the
key is rejected in that state rather than ignored: Anthropic documents
`tool_choice` as valid only while providing tools, and the OpenAI-compatible
`/v1/chat/completions` surface refuses a `tool_choice` sent with no `tools`. So
the request each transport would have made is one the provider declines, on
exactly the calls a run makes when it has stopped early.

**Why nobody caught it on the Anthropic side.** That request was a local named
`_request`, built "so the mapping is exercised" and then never read by anything —
no caller, no test, no wire. `apply_settings` reporting seven of the twelve keys
honoured rested on a mapping table and a dict discarded on the next line. That is
the defect this round is named for, one layer down: a seam asserted instead of an
effect. `request_for` exists so the claim can be read.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.anthropic_transport import (  # noqa: E402
    AnthropicTransport,
)
from pact_adapters.transports.ollama_transport import OllamaTransport  # noqa: E402

#: One tool, in the shape `harness.run` hands a transport.
PAYMENTS = [{"name": "payments", "description": "issue a refund", "parameters": {}}]

#: The one exchange every case here builds a request around.
ASKED = [{"role": "user", "content": "hello"}]


def _anthropic() -> AnthropicTransport:
    return AnthropicTransport(Script([Turn("ok")]))


def _ollama() -> OllamaTransport:
    return OllamaTransport("qwen2.5-7b-instruct", base_url="http://localhost:1/v1")


# ───────────────────────────────────── the Anthropic request is reachable at all


def test_the_anthropic_request_exists_where_something_can_read_it() -> None:
    """The mapping is an effect now, not a table and a discarded local.

    Asserted through the method a run itself calls, so severing the settings from
    the request cannot leave this green.
    """
    t = _anthropic()
    left = t.apply_settings(
        {"max-tokens": 256, "temperature": 0.2, "top-p": 0.9, "top-k": 40,
         "stop-sequences": ["END"], "service-tier": "auto", "tool-choice": "auto"}
    )
    assert left == (), left

    request = t.request_for("be brief", ASKED, PAYMENTS)
    assert request["max_tokens"] == 256, request
    assert request["temperature"] == 0.2, request
    assert request["top_p"] == 0.9, request
    assert request["top_k"] == 40, request
    assert request["stop_sequences"] == ["END"], request
    assert request["service_tier"] == "auto", request
    # This provider takes an OBJECT where the OpenAI-compatible one takes a word.
    assert request["tool_choice"] == {"type": "auto"}, request


def test_a_key_this_provider_has_no_field_for_never_reaches_its_request() -> None:
    """Reported unhonoured AND absent from the wire — the two have to agree.

    A key reported on `RunResult.unmetered` that was sent anyway would be the
    report lying in the safe direction; a key sent that is not in `_WIRE` would be
    a setting in a shape the provider ignores, with nothing saying it did not
    happen.
    """
    t = _anthropic()
    left = t.apply_settings(
        {"thinking": "high", "seed": 7, "presence-penalty": 0.5,
         "frequency-penalty": 0.1, "parallel-tool-calls": True}
    )
    assert set(left) == {
        "thinking", "seed", "presence-penalty", "frequency-penalty",
        "parallel-tool-calls",
    }, left

    request = t.request_for("be brief", ASKED, PAYMENTS)
    for absent in ("thinking", "seed", "presence_penalty", "frequency_penalty",
                   "parallel_tool_calls", "reasoning_effort"):
        assert absent not in request, f"{absent} reached a request that cannot take it"


def test_the_author_ceiling_beats_the_hardcoded_one() -> None:
    """`max-tokens:` was 1024 for every run in every workspace for a round."""
    t = _anthropic()
    t.apply_settings({"max-tokens": 5})
    assert t.request_for("", ASKED, [])["max_tokens"] == 5


# ──────────────────────────────── and the choice goes only where it can be carried


@pytest.mark.parametrize("chose", ["required", "payments"])
def test_a_choice_no_tool_less_call_can_carry_is_not_sent_by_either(chose: str) -> None:
    """The closing call of every ceiling-terminated run offers no tools.

    `required` has nothing to be required OF and a NAME names nothing. Neither
    provider ignores the key in that state, so sending it would take down the one
    call a run makes after it has already decided to stop.
    """
    a = _anthropic()
    a.apply_settings({"tool-choice": chose})
    assert "tool_choice" not in a.request_for("", ASKED, []), chose

    o = _ollama()
    o.apply_settings({"tool-choice": chose})
    assert "tool_choice" not in o.payload_for("", ASKED, []), chose


def test_a_choice_naming_a_tool_this_call_does_not_offer_is_not_sent() -> None:
    """A stage narrows the set, and the named tool may not survive the narrowing."""
    a = _anthropic()
    a.apply_settings({"tool-choice": "payments"})
    other = [{"name": "lookup", "description": "", "parameters": {}}]
    assert "tool_choice" not in a.request_for("", ASKED, other)

    o = _ollama()
    o.apply_settings({"tool-choice": "payments"})
    assert "tool_choice" not in o.payload_for("", ASKED, other)


@pytest.mark.parametrize("chose", ["auto", "none"])
def test_the_two_words_a_tool_less_call_can_still_give_are_still_sent(chose: str) -> None:
    """"Pick for yourself" and "do not call one" are satisfiable with nothing to pick.

    The guard has to be a guard and not a blanket drop, or a `tool-choice: none`
    — the one an author writes to stop a model reaching for a tool — would be
    silently discarded on the calls where it matters most.
    """
    a = _anthropic()
    a.apply_settings({"tool-choice": chose})
    assert a.request_for("", ASKED, [])["tool_choice"] == {"type": chose}

    o = _ollama()
    o.apply_settings({"tool-choice": chose})
    assert o.payload_for("", ASKED, [])["tool_choice"] == chose


def test_a_choice_the_call_can_carry_still_goes_in_each_providers_own_shape() -> None:
    """The guard must not cost the translation it is guarding.

    One authored word, two shapes — which is what the `settings` group's header
    promises and what one mapping table per transport exists to deliver.
    """
    a = _anthropic()
    a.apply_settings({"tool-choice": "payments"})
    assert a.request_for("", ASKED, PAYMENTS)["tool_choice"] == {
        "type": "tool", "name": "payments",
    }
    a.apply_settings({"tool-choice": "required"})
    assert a.request_for("", ASKED, PAYMENTS)["tool_choice"] == {"type": "any"}

    o = _ollama()
    o.apply_settings({"tool-choice": "payments"})
    assert o.payload_for("", ASKED, PAYMENTS)["tool_choice"] == {
        "type": "function", "function": {"name": "payments"},
    }
    o.apply_settings({"tool-choice": "required"})
    assert o.payload_for("", ASKED, PAYMENTS)["tool_choice"] == "required"


def test_every_transport_that_maps_a_tool_choice_decides_it_per_call() -> None:
    """The CLASS, not the two instances.

    Five transports guarded this and two did not, and the two that did not were
    the two whose requests no test read. The next transport to map `tool-choice`
    without asking the per-call question should fail here rather than ship a key
    that breaks a run's closing call.
    """
    here = Path(__file__).resolve().parents[1] / "src" / "pact_adapters" / "transports"
    for path in sorted(here.glob("*.py")):
        if path.name.startswith("_"):
            continue
        source = path.read_text()
        if "tool-choice" not in source or "def apply_settings(" not in source:
            continue
        assert "can_choose" in source, (
            f"{path.name} maps `tool-choice:` and never asks whether the call it "
            "is building can carry one — see transports/_tool_choice.py"
        )
