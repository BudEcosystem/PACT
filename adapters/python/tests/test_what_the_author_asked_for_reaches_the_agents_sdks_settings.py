"""The `settings:` block an author writes reaches the Agents SDK's `ModelSettings`.

Measured on this transport before the fix, on a spec carrying all twelve keys,
`RunResult.unmetered` read:

```text
    settings.frequency-penalty, settings.max-tokens,
    settings.parallel-tool-calls, settings.presence-penalty, settings.seed,
    settings.service-tier, settings.stop-sequences, settings.temperature,
    settings.thinking, settings.tool-choice, settings.top-k, settings.top-p
```

— every one of them, because `OpenAIAgentsTransport` had no `apply_settings` and
the transport passed a literal `model_settings=None` into `get_response`.

**Eight of the twelve are SET on the object; only six are reported honoured, and
the gap between those two numbers is the point of the file.** The seam is
`agents.models.interface.Model`, whose `get_response` takes a `ModelSettings`,
and that dataclass is the whole vocabulary a `Model` implementation is
guaranteed to understand. Checked against openai-agents 0.19.1, installed here:
it has fields named `max_tokens`, `reasoning`, `temperature`, `top_p`,
`presence_penalty`, `frequency_penalty`, `tool_choice` and
`parallel_tool_calls`, and it has no field for `top-k`, `stop-sequences`, `seed`
or `service-tier`.

**Four have no field at all**, and not by accident. Reading the two shipped
`Model` implementations:

* `agents/models/openai_responses.py` builds `create_kwargs` with `temperature`,
  `top_p`, `truncation`, `max_output_tokens`, `tool_choice`,
  `parallel_tool_calls`, `reasoning`, `store`, `metadata` and
  `context_management` — and no `stop`, no `seed`, no `service_tier`, no `top_k`.
* `agents/models/openai_chatcompletions.py` builds its own with no `stop`, no
  `seed`, no `service_tier` and no `top_k` either.

The only door left is `ModelSettings.extra_args`, an untyped dict spread
straight into whichever provider call the host's `ModelProvider` chose. Putting
`seed` there is right on OpenAI's own client and is either ignored or a
`TypeError` on anything else, which is precisely the shape the translate-or-
nothing rule forbids. They are reported instead.

**Two have a field, are set on it, and are reported anyway** — `presence-penalty`
and `frequency-penalty`, and they are the reason this file has two separate
tests where one would look tidier. Verified in the installed SDK:
`agents/models/_openai_shared.py` declares `_use_responses_by_default = True`
and `OpenAIProvider` picks `OpenAIResponsesModel` off it, so the RESPONSES
surface is the default one — and `inspect.getsource(agents.models
.openai_responses)` contains neither `presence_penalty` nor `frequency_penalty`,
while `openai_chatcompletions` contains both. So the field is real, the value is
not an approximation, and a host on the Chat Completions path genuinely gets
them — but the default surface drops them silently, and WHICH surface a run gets
is the host's choice and is not knowable from here.

`RunResult.unmetered` is therefore a statement about what this transport can
PROMISE was honoured, not about what it sent. Where the two differ the promise
is deliberately the weaker: an author on the Chat Completions path is told two
settings may not have landed when they did, which is the error pointing in the
survivable direction. The opposite — a key reported honoured that the default
surface silently drops — is the exact defect this whole round exists to close.

`tool-choice` is the inversion worth reading twice.
`ModelSettings.tool_choice` is typed `Literal["auto", "required", "none"] | str
| MCPToolChoice`, and `Converter.convert_tool_choice` in `openai_responses.py`
is what turns the bare string into `{"type": "function", "name": ...}`. So here
the bare name IS the interface — the exact opposite of `ollama_transport.py`,
where a bare name reaches the wire and silently means nothing.

Mutation: in `openai_agents_transport.model_call`, put `model_settings=None`
back on the `get_response` call. `settings_for()` still builds the right object
and `apply_settings` still returns the same six; the object simply never
crosses. Seven went red:

```text
    FAILED test_the_eight_the_sdk_names_a_field_for_are_set_on_the_object
    FAILED test_the_four_the_agents_sdk_has_no_field_for_are_reported_not_guessed
    FAILED test_the_two_the_default_surface_drops_are_sent_and_still_reported
    FAILED test_a_named_tool_choice_goes_through_as_the_bare_name
    FAILED test_a_choice_this_call_cannot_carry_is_not_sent
    FAILED test_the_core_two_both_land_on_the_object
    FAILED test_the_run_still_works_when_the_author_wrote_no_settings
```

Two of those seven went red for a WEAKER reason than they look, and saying so is
the point of recording a mutation at all.
`test_the_four_the_agents_sdk_has_no_field_for_are_reported_not_guessed` and
`test_a_choice_this_call_cannot_carry_is_not_sent` both reach through `t.saw` to
check that nothing was smuggled onto the object, and with the mutation in place
`t.saw` is `None`, so they raise rather than fail an assertion about honesty.
Their honesty halves — the `unmetered` assertions — would have passed either way.

Four stayed GREEN, and the first of them is the register's own warning about
absence-shaped tests, met head on: `test_the_left_over_set_is_exactly_the_six
_and_no_others` is the file's fullest statement of the REPORT, and a transport
that sends nothing at all still makes it true. That is precisely why the report
is not what this file leans on. The other three are
`test_a_tool_choice_arrives_beside_the_tool_it_names`, because the tools travel
on a different keyword; `test_the_call_is_one_the_sdks_own_interface_would
_accept`, because `model_settings` is still a keyword on the call even when its
value is `None`; and `test_the_transport_still_counts_what_the_call_carried`,
which only needs the call to happen.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402

pytest.importorskip(
    "agents", reason="the OpenAI Agents SDK is not installed in this environment"
)

from agents.model_settings import ModelSettings  # noqa: E402
from agents.models.interface import Model, ModelTracing  # noqa: E402

from pact_adapters.transports.openai_agents_transport import (  # noqa: E402
    OpenAIAgentsTransport,
    _ALL_FIELDS,
)


ALL_TWELVE = {
    "max-tokens": 512,
    "thinking": "high",
    "temperature": 0.2,
    "top-p": 0.9,
    "top-k": 40,
    "stop-sequences": ["END"],
    "seed": 7,
    "presence-penalty": 0.5,
    "frequency-penalty": 0.1,
    "tool-choice": "payments",
    "parallel-tool-calls": False,
    "service-tier": "flex",
}

#: The four with no field on `ModelSettings`, and why each is reported rather
#: than pushed through `extra_args`. Held as data so the file states a reason
#: for every left-over key instead of asserting a count.
NO_FIELD = {
    "top-k": "no field, and neither shipped Model puts a top_k in its create kwargs",
    "stop-sequences": "no field; neither the Responses nor the Chat Completions "
                      "request the SDK builds carries a stop",
    "seed": "no field; extra_args would reach OpenAI's own client and nothing else",
    "service-tier": "no field; a raw extra_args kwarg on a host-chosen provider",
}

#: The two with a field that the SDK's DEFAULT surface never forwards. Set on
#: the object — the field is the SDK's own and the value is not a guess — and
#: reported anyway, because which surface a run gets is the host's choice.
ONLY_ON_CHAT_COMPLETIONS = {
    "presence-penalty": "presence_penalty",
    "frequency-penalty": "frequency_penalty",
}


class Recording(OpenAIAgentsTransport):
    """The shipped transport, keeping the `ModelSettings` the SDK seam received.

    Wrapped on the `Model` rather than read off a builder, because the register
    records what a builder-only assertion is worth: *"The first version asserted
    `_WIRE` membership and what `apply_settings` returned — both true of a
    transport that then drops every setting on the floor."*
    """

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.saw: ModelSettings | None = None
        self.saw_tools: list = []
        self.saw_call: dict = {}
        transport = self
        inner = self._model.get_response

        async def get_response(*args, **kwargs):
            transport.saw = kwargs.get("model_settings")
            transport.saw_tools = list(kwargs.get("tools") or [])
            transport.saw_call = dict(kwargs)
            return await inner(*args, **kwargs)

        object.__setattr__(self._model, "get_response", get_response)


def _spec(settings: dict, tools: bool = True) -> AgentSpec:
    return AgentSpec(
        name="refund-desk",
        description="decides refunds",
        instructions="Be brief.",
        tools=(ToolSpec(name="payments", description="pays"),) if tools else (),
        settings=dict(settings),
    )


def _ran(transport: OpenAIAgentsTransport, settings: dict, tools: bool = True):
    return asyncio.run(run(_spec(settings, tools), transport, "hello"))


def test_the_eight_the_sdk_names_a_field_for_are_set_on_the_object() -> None:
    """The object handed to `Model.get_response`, not the mapping table."""
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)

    got = t.saw
    assert isinstance(got, ModelSettings), got
    assert got.max_tokens == 512
    assert got.temperature == 0.2
    assert got.top_p == 0.9
    assert got.presence_penalty == 0.5
    assert got.frequency_penalty == 0.1
    assert got.parallel_tool_calls is False
    assert got.tool_choice == "payments"
    # `thinking:` is the second `tier: core` key and the one that needs an object
    # rather than a copy: the SDK carries it as `openai.types.shared.Reasoning`,
    # whose `effort` literal happens to contain all four of PACT's words.
    assert got.reasoning is not None and got.reasoning.effort == "high", got.reasoning


def test_the_four_the_agents_sdk_has_no_field_for_are_reported_not_guessed() -> None:
    """Honesty beats coverage.

    `ModelSettings.extra_args` would take any of these and spread it into
    whichever provider call the host's `ModelProvider` made. Right on OpenAI's
    own client, ignored or a `TypeError` on anything else — so each is named on
    `RunResult.unmetered` and none of them is sent.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, ALL_TWELVE)

    for key, why in NO_FIELD.items():
        assert f"settings.{key}" in out.unmetered, f"{key} ({why}) was not reported"

    # And nothing smuggled through the untyped doors.
    assert not (t.saw.extra_args or {}), t.saw.extra_args
    assert not (t.saw.extra_body or {}), t.saw.extra_body
    assert not (t.saw.extra_query or {}), t.saw.extra_query


def test_the_two_the_default_surface_drops_are_sent_and_still_reported() -> None:
    """The one case where "sent" and "reported honoured" come apart, deliberately.

    `ModelSettings` names `presence_penalty` and `frequency_penalty`, so they go
    on the object as the SDK's own typed fields — no approximation, and a host
    that bound `OpenAIChatCompletionsModel` really does get them. But
    `_openai_shared._use_responses_by_default` is `True`, `OpenAIProvider` picks
    `OpenAIResponsesModel` off it, and that model's `create_kwargs` contain
    neither. The surface is the HOST's choice and this transport cannot see it.

    So both are set AND both are named on `RunResult.unmetered`. That
    under-claims on the Chat Completions path, which is the survivable error;
    the other direction is a key reported honoured that the default surface
    silently drops, which is the defect this round exists to close.

    This is what distinguishes this test from the four above: those keys are
    never sent at all. These are sent and still not promised.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, ALL_TWELVE)

    for key, field in ONLY_ON_CHAT_COMPLETIONS.items():
        assert getattr(t.saw, field) == ALL_TWELVE[key], (field, t.saw)
        assert f"settings.{key}" in out.unmetered, key

    # Read against the installed SDK rather than trusted: the default surface's
    # own source is the evidence, so this test fails the day the SDK adds them.
    from agents.models import openai_chatcompletions, openai_responses

    responses = inspect.getsource(openai_responses)
    chat = inspect.getsource(openai_chatcompletions)
    for field in ONLY_ON_CHAT_COMPLETIONS.values():
        assert field not in responses, f"{field} is now on the Responses surface"
        assert field in chat, f"{field} left the Chat Completions surface"


def test_the_left_over_set_is_exactly_the_six_and_no_others() -> None:
    """The whole report in one assertion, so a key cannot quietly change side.

    Four are absent from the object; two are on it and unpromised. Nothing else
    is reported, and in particular the six that ARE promised — including both
    `tier: core` keys — are absent from this list.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, ALL_TWELVE)

    left = sorted(u for u in out.unmetered if u.startswith("settings."))
    expected = sorted(
        f"settings.{k}" for k in (*NO_FIELD, *ONLY_ON_CHAT_COMPLETIONS)
    )
    assert left == expected, left
    for promised in ("max-tokens", "thinking", "temperature", "top-p",
                     "tool-choice", "parallel-tool-calls"):
        assert f"settings.{promised}" not in out.unmetered, promised


def test_a_named_tool_choice_goes_through_as_the_bare_name() -> None:
    """Translate or nothing, at the value level — and here the answer is *nothing
    to translate*, which is a finding rather than an omission.

    `ModelSettings.tool_choice` is `Literal["auto", "required", "none"] | str |
    MCPToolChoice`, and `Converter.convert_tool_choice` is the SDK's own code for
    turning the bare name into `{"type": "function", "name": ...}` on the way to
    the provider. Anticipating it here would produce a dict where a string is
    typed, which is the same class of mistake pointing the other way.

    The three words go through as written; this SDK spells the middle one
    `required`, where Anthropic spells it `any`.
    """
    for word in ("auto", "required", "none", "payments"):
        t = Recording(Script([Turn("Decision: approved.")]))
        _ran(t, {"tool-choice": word})
        assert t.saw.tool_choice == word, (word, t.saw.tool_choice)


def test_a_tool_choice_arrives_beside_the_tool_it_names() -> None:
    """A `tool_choice` naming a tool the model was never given is a setting about
    nothing — and worse than nothing here, because the SDK's own
    `_validate_named_function_tool_choice` raises on it. The spec's tools go
    through the same call, as the SDK's `FunctionTool`."""
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, {"tool-choice": "payments"})
    assert [tool.name for tool in t.saw_tools] == ["payments"], t.saw_tools


def test_a_choice_this_call_cannot_carry_is_not_sent() -> None:
    """And the per-CALL half, which on this SDK is the difference between an
    unhonoured setting and a dead run.

    `harness.run` closes every ceiling-terminated run with `model_call(
    instructions, history, [])`, and a stage may offer no tools, so whether a
    choice can be carried is a fact about a particular call.
    `_validate_named_function_tool_choice` RAISES on a name the call did not
    offer, and `required` with nothing to require is a choice about nothing. So
    `_tool_choice.can_choose` leaves the field unset for both — nothing goes in
    their place — while `auto` and `none` are answers a tool-less call can still
    give and do go through.
    """
    for word in ("required", "payments"):
        t = Recording(Script([Turn("Decision: approved.")]))
        _ran(t, {"tool-choice": word}, tools=False)
        assert t.saw.tool_choice is None, (word, t.saw.tool_choice)
    for word in ("auto", "none"):
        t = Recording(Script([Turn("Decision: approved.")]))
        _ran(t, {"tool-choice": word}, tools=False)
        assert t.saw.tool_choice == word, (word, t.saw.tool_choice)


def test_the_core_two_both_land_on_the_object() -> None:
    """`max-tokens:` and `thinking:` are the two `tier: core` keys — the ones a
    non-technical author writes, and the two whose absence from every transport
    started this. Both survive here, and nothing is reported."""
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {"max-tokens": 64, "thinking": "low"})
    assert t.saw.max_tokens == 64
    assert t.saw.reasoning is not None and t.saw.reasoning.effort == "low"
    assert [u for u in out.unmetered if u.startswith("settings.")] == []


def test_the_call_is_one_the_sdks_own_interface_would_accept() -> None:
    """A seam only means something if the call crossing it is one the interface
    takes.

    `Model.get_response` types `tracing` as the `ModelTracing` ENUM and
    `openai_responses.py` calls `tracing.is_disabled()` on it, and it has three
    keyword-only parameters with no defaults. This transport passed
    `tracing=None` and omitted all three for a round, and nothing noticed,
    because the `Model` on the other side is PACT's own and takes `*args,
    **kwargs`. Checked against the real signature here instead of against the
    stand-in's tolerance.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)

    assert isinstance(t.saw_call.get("tracing"), ModelTracing), t.saw_call.get("tracing")

    signature = inspect.signature(Model.get_response)
    required = {
        name
        for name, p in signature.parameters.items()
        if name != "self" and p.default is inspect.Parameter.empty
    }
    assert required <= set(t.saw_call), sorted(required - set(t.saw_call))
    assert set(t.saw_call) <= set(signature.parameters), sorted(
        set(t.saw_call) - set(signature.parameters)
    )


def test_the_run_still_works_when_the_author_wrote_no_settings() -> None:
    """A transport that only works with a `settings:` block is worse than the one
    it replaced. A `ModelSettings` still goes down — the SDK's own default — and
    every mappable field on it is left unset, so nothing is invented."""
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {})
    assert isinstance(t.saw, ModelSettings), t.saw
    for field in _ALL_FIELDS.values():
        assert getattr(t.saw, field) is None, field
    assert t.saw.reasoning is None
    assert [u for u in out.unmetered if u.startswith("settings.")] == []


def test_the_transport_still_counts_what_the_call_carried() -> None:
    """The metering that already landed here must survive the rewiring.

    Both money ceilings read `usage()`, which reads `agents.usage.Usage` off the
    response, so a rewiring that stopped calling `get_response` would put them
    back on `unmetered` without failing anything above.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)
    tokens, _money = t.usage()
    assert tokens > 0, "the call carried nothing the meter could see"
