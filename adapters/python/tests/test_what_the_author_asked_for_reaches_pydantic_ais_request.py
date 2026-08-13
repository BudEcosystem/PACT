"""The `settings:` block an author writes reaches Pydantic AI's own request.

`spec/schema.yaml` declares twelve `settings:` fields, two of them `tier: core`
— `max-tokens:` and `thinking:`. `harness.run` hands the block to whatever
transport can take it and puts the rest on `RunResult.unmetered`:

```python
    if spec.settings:
        take = getattr(transport, "apply_settings", None)
        left_over = tuple(spec.settings) if take is None else tuple(take(spec.settings))
        result.unmetered = result.unmetered + tuple(f"settings.{k}" for k in left_over)
```

For a round only two of the nine shipped transports had that method, so on this
one EVERY authored key came back unhonoured. Measured before the fix, on a spec
carrying all twelve:

```text
    settings.max-tokens, settings.thinking, settings.temperature, settings.top-p,
    settings.top-k, settings.stop-sequences, settings.seed,
    settings.presence-penalty, settings.frequency-penalty, settings.tool-choice,
    settings.parallel-tool-calls, settings.service-tier
```

Pydantic AI is the one framework here whose own `ModelSettings` TypedDict names
an analogue for all twelve — `pydantic_ai.settings.ModelSettings` (2.21.0)
carries `max_tokens, thinking, temperature, top_p, top_k, stop_sequences, seed,
presence_penalty, frequency_penalty, tool_choice, parallel_tool_calls,
service_tier`. So this is the transport with the least excuse for dropping any
of it, and the one where translation matters most.

**What is asserted here is the request, not the mapping table.** The register
records the trap in its own words: *"A test of mine failed its own mutation
here. The first version asserted `_WIRE` membership and what `apply_settings`
returned — both true of a transport that then drops every setting on the
floor."* Pydantic AI hands the model function an `AgentInfo`, and `AgentInfo`
carries `model_settings` and `model_request_parameters` — the objects the SDK's
own `Model.prepare_request` produced. Recording those inside `_respond` is
recording what reached the SDK.

Mutation: delete the `model_settings=self.settings_for_request(...)` argument
from `direct.model_request` in `pydantic_ai_transport.model_call`. Measured now:
`10 failed, 4 passed`. Four still pass with every setting dropped on the floor —
`test_only_what_this_model_cannot_do_goes_out_unhonoured`,
`test_a_setting_the_bound_model_cannot_do_is_reported_not_dropped`,
`test_one_authored_word_becomes_this_sdks_own_shape` and
`test_the_run_still_works_when_the_author_wrote_no_settings` — because
`apply_settings` goes on returning the same left-over set whether or not anything
is sent, and because the rest assert an ABSENCE. They are kept and named rather
than deleted: the first is the assertion the gap register's row is phrased in,
and none of them can catch this. The ones that can are the ones that read
`AgentInfo`.

Second mutation, for the guard the first version of this file did not have:
delete the `if key == "tool-choice" and not can_choose(value, offered)` line from
`settings_for_request`. Three tests go red and they go red by RAISING —
`UserError: `tool_choice` was set to "required", but no function tools are
defined` and `UserError: Invalid tool names in `tool_choice`: {'payments'}` — out
of the SDK's own `resolve_tool_choice`. Nothing in the tree caught that before,
because `models/function.py` is the one model in this SDK that never calls it,
so `_Checks` below adds the single line every provider model has.

Third mutation: make `_thinking_reaches` return `True` once the profile thinks,
which is the two questions this transport asked for a round instead of three.
`test_a_thinking_the_sdk_discards_is_reported_even_on_a_thinking_model` goes red
alone: on a `thinking_always_enabled` profile the SDK discards `thinking: none`
and thinks anyway, and PACT was reporting that `tier: core` key as honoured.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402

pydantic_ai = pytest.importorskip(
    "pydantic_ai", reason="Pydantic AI is not installed in this environment"
)

from pydantic_ai.models._tool_choice import resolve_tool_choice  # noqa: E402
from pydantic_ai.models.function import FunctionModel  # noqa: E402

from pact_adapters.transports.pydantic_ai_transport import (  # noqa: E402
    PydanticAITransport,
    _SETTINGS,
    _translated,
)


#: Every key the schema's `settings` group declares, with a value of its own
#: declared type. Written out rather than read off the schema on purpose: the
#: schema is the thing under test, and a test that derives its input from it
#: passes when a field is quietly deleted.
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


class Recording(PydanticAITransport):
    """The shipped transport, with the SDK's own `AgentInfo` kept.

    `_respond` is the function Pydantic AI calls from inside its request
    machinery, so `info` here is what `direct.model_request` produced after
    `Model.prepare_request` ran. Subclassing is the house way to record what
    reached the SDK without a served model.
    """

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.saw_settings: dict | None = None
        self.saw_params = None

    def _respond(self, messages, info):
        self.saw_settings = dict(info.model_settings or {})
        self.saw_params = info.model_request_parameters
        return super()._respond(messages, info)


def _spec(settings: dict) -> AgentSpec:
    return AgentSpec(
        name="refund-desk",
        description="decides refunds",
        instructions="Be brief.",
        tools=(ToolSpec(name="payments", description="pays"),),
        settings=dict(settings),
    )


def _ran(transport: PydanticAITransport, settings: dict):
    return asyncio.run(run(_spec(settings), transport, "hello"))


def test_every_authored_setting_arrives_on_the_sdks_own_request() -> None:
    """All twelve, on the `ModelSettings` Pydantic AI handed the model.

    Eleven land on `AgentInfo.model_settings`. `thinking` is the twelfth and it
    lands somewhere else by the SDK's own design: `Model.prepare_request`
    resolves it against the bound model's profile and strips it from
    `model_settings`, leaving it on `ModelRequestParameters.thinking` when the
    profile supports thinking and nowhere at all when it does not. That is the
    SDK being honest about a capability, and the transport reports the second
    case as unhonoured rather than pretending — `test_a_setting_the_bound_model
    _cannot_do_is_reported_not_dropped` is that half.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)

    saw = t.saw_settings
    assert saw is not None, "the model function was never reached"
    assert saw["max_tokens"] == 512, saw
    assert saw["temperature"] == 0.2, saw
    assert saw["top_p"] == 0.9, saw
    assert saw["top_k"] == 40, saw
    assert saw["stop_sequences"] == ["END"], saw
    assert saw["seed"] == 7, saw
    assert saw["presence_penalty"] == 0.5, saw
    assert saw["frequency_penalty"] == 0.1, saw
    assert saw["parallel_tool_calls"] is False, saw
    assert saw["service_tier"] == "flex", saw
    # A tool NAME. Pydantic AI's `resolve_tool_choice` turns `list[str]` into
    # `('required', {names})`, which the OpenAI model then writes as
    # `{"type": "function", "function": {"name": ...}}` and the Anthropic one as
    # `{"type": "tool", "name": ...}`. A bare `"payments"` is not in that type
    # and would be a silent no-op wherever it were accepted.
    assert saw["tool_choice"] == ["payments"], saw


def test_a_setting_the_bound_model_cannot_do_is_reported_not_dropped() -> None:
    """`thinking:` on a model whose profile does not think.

    `Model.prepare_request` strips `thinking` from `model_settings` and only
    puts it on `ModelRequestParameters` when `profile.supports_thinking` (or
    `thinking_always_enabled`) is set. So handing it over and saying nothing
    would be a `tier: core` field vanishing in silence — the exact shape of the
    defect this whole round is about. The transport asks the same question the
    SDK asks, and reports the key when the answer is no.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {"thinking": "high", "temperature": 0.2})

    assert t.saw_params is not None
    assert t.saw_params.thinking is None, "the SDK dropped it, quietly"
    assert "settings.thinking" in out.unmetered, out.unmetered
    # And only that one. The other key was honoured and must not be reported.
    assert "settings.temperature" not in out.unmetered, out.unmetered


def test_a_model_that_does_think_gets_the_authors_effort_level() -> None:
    """The other half, so the report above is a fact about the model and not a
    permanent excuse.

    `thinking: none` is PACT's word for "do not", and Pydantic AI's
    `ThinkingLevel` spells that `False` rather than a fifth string — one of the
    four values needing translation rather than copying.
    """
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.profiles import ModelProfile

    class Thinks(Recording):
        def __init__(self, *a, **kw) -> None:
            super().__init__(*a, **kw)
            self._model = FunctionModel(
                self._respond, profile=ModelProfile(supports_thinking=True)
            )

    t = Thinks(Script([Turn("Decision: approved.")]))
    out = _ran(t, {"thinking": "high"})
    assert t.saw_params.thinking == "high", t.saw_params
    assert "settings.thinking" not in out.unmetered, out.unmetered

    t2 = Thinks(Script([Turn("Decision: approved.")]))
    _ran(t2, {"thinking": "none"})
    assert t2.saw_params.thinking is False, t2.saw_params


def test_a_service_class_this_sdk_has_no_word_for_is_left_over() -> None:
    """`service-tier:` is free text in the schema and a closed set in the SDK.

    `pydantic_ai.settings.ServiceTier` is `Literal['auto', 'default', 'flex',
    'priority']` and each model translates those four into its provider's own
    spelling. A fifth word has no translation, and `ModelSettings` is a
    `TypedDict` — nothing would stop it being posted to the provider, where it
    is a 400 at best and ignored at worst. Reported instead.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {"service-tier": "turbo"})
    assert "settings.service-tier" in out.unmetered, out.unmetered
    assert (t.saw_settings or {}).get("service_tier") is None, t.saw_settings

    t2 = Recording(Script([Turn("Decision: approved.")]))
    out2 = _ran(t2, {"service-tier": "priority"})
    assert "settings.service-tier" not in out2.unmetered, out2.unmetered
    assert t2.saw_settings["service_tier"] == "priority", t2.saw_settings


def test_only_what_this_model_cannot_do_goes_out_unhonoured() -> None:
    """The twelve, end to end, through `harness.run`.

    Measured on this transport before the fix, all twelve came back:

    ```text
        settings.frequency-penalty, settings.max-tokens,
        settings.parallel-tool-calls, settings.presence-penalty, settings.seed,
        settings.service-tier, settings.stop-sequences, settings.temperature,
        settings.thinking, settings.tool-choice, settings.top-k, settings.top-p
    ```

    Eleven of them now reach the SDK. `thinking:` is the one that does not, and
    the report is a fact about the bound model rather than about the transport:
    the stand-in `FunctionModel` carries Pydantic AI's default profile, which
    does not think, and `test_a_model_that_does_think_gets_the_authors_effort
    _level` is the same transport honouring it on a profile that does.

    Written as an exact set rather than a length, so a key that stops being
    honoured is named here and not merely counted.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, ALL_TWELVE)
    left = sorted(u for u in out.unmetered if u.startswith("settings."))
    assert left == ["settings.thinking"], f"still unhonoured on Pydantic AI: {left}"
    assert set(_SETTINGS) == set(ALL_TWELVE), "the mapping and the schema disagree"


def test_one_authored_word_becomes_this_sdks_own_shape() -> None:
    """Translate or nothing, at the value level.

    Three of `tool-choice:`'s four values are words this SDK also uses; the
    fourth is a NAME, and a name is a `list[str]` here where it is an object on
    both wire formats. `thinking: none` is the other translation.
    """
    assert _translated("tool-choice", "auto") == "auto"
    assert _translated("tool-choice", "required") == "required"
    assert _translated("tool-choice", "none") == "none"
    assert _translated("tool-choice", "payments") == ["payments"]
    assert _translated("thinking", "none") is False
    assert _translated("thinking", "high") == "high"
    # A scalar where the schema says "list of text" still arrives as a list,
    # because `ModelSettings.stop_sequences` is `list[str]` and a bare string is
    # a sequence of characters to anything that iterates it.
    assert _translated("stop-sequences", "END") == ["END"]
    assert _translated("stop-sequences", ["A", "B"]) == ["A", "B"]


def test_the_run_still_works_when_the_author_wrote_no_settings() -> None:
    """The block is optional, and a transport that only works with one is worse
    than the one it replaced."""
    t = Recording(Script([Turn("Decision: approved.", (ToolCall("payments", {}),)), Turn("done")]))
    out = _ran(t, {})
    assert t.saw_settings == {}, t.saw_settings
    assert [u for u in out.unmetered if u.startswith("settings.")] == []


# ─────────────────────────── the tool choice, on a model that checks it (B7a)


class _Checks(FunctionModel):
    """A `FunctionModel` that validates the tool choice the way a provider does.

    `models/function.py` is the ONE model in this SDK that never calls
    `models._tool_choice.resolve_tool_choice`. Every provider model does —
    `openai.py:1318`, `anthropic.py:1407`, `google.py:714`, `groq.py`,
    `mistral.py`, `cohere.py`, `bedrock.py:976`, `xai.py`, `huggingface.py` — and
    it raises `UserError` rather than degrading. So a test driven through the
    plain `FunctionModel` would pass over a transport that aborts every real run,
    which is exactly what happened: the first version of this file certified a
    `tool_choice` that kills any of those nine.

    One line of the provider contract, added at the point every provider calls
    it, so the SDK's own validator is the thing under test rather than a
    re-implementation of it here.
    """

    async def request(self, messages, model_settings, model_request_parameters):
        settings, params = self.prepare_request(model_settings, model_request_parameters)
        resolve_tool_choice(settings, params)
        return await super().request(messages, model_settings, model_request_parameters)


class Checking(Recording):
    """The shipped transport, bound to the model above."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self._model = _Checks(self._respond)


def _one_call(t: PydanticAITransport, settings: dict, tools: list[dict]):
    """One `model_call`, made the way the harness makes them.

    Directly rather than through `run`, because the state under test is a
    PARTICULAR call's tool list: `harness.run` closes a ceiling-terminated run
    with `transport.model_call(spec.instructions, history, [])` (harness.py:2381)
    and narrows the list per stage (harness.py:1268), and both are reached here
    by passing the list this test means.
    """
    t.apply_settings(settings)
    return asyncio.run(t.model_call("Be brief.", [{"role": "user", "content": "hi"}], tools))


PAYMENTS = [{"name": "payments", "description": "pays"}]


@pytest.mark.parametrize("chose", ["required", "payments"])
def test_a_tool_choice_no_call_can_carry_does_not_abort_the_run(chose: str) -> None:
    """The closing call, which offers NO tools, on a model that checks.

    `harness.run` makes exactly this call on every ceiling-terminated run — "one
    closing call with NO tools offered, so the model has to answer from what it
    already has instead of starting more work". Sending the author's
    `tool-choice:` on it is not a degradation, it is the end of the run.
    Measured against pydantic_ai_slim 2.21.0 with
    `ModelRequestParameters(function_tools=[], allow_text_output=True)`::

        ['payments'] -> UserError Invalid tool names in `tool_choice`:
                        {'payments'}. Available tools: none
        'required'   -> UserError `tool_choice` was set to "required", but no
                        function tools are defined.

    Before this transport mapped `tool-choice` at all the key was merely reported
    on `RunResult.unmetered`. A mapping that turns a reported key into a dead run
    is worse than the gap it closed.
    """
    t = Checking(Script([Turn("Decision: approved.")]))
    text, _ = _one_call(t, {"tool-choice": chose, "temperature": 0.2}, [])
    assert text == "Decision: approved."
    assert "tool_choice" not in (t.saw_settings or {}), t.saw_settings
    # And only that key. A call that cannot carry the choice still carries
    # everything else the author wrote.
    assert (t.saw_settings or {}).get("temperature") == 0.2, t.saw_settings


def test_a_tool_choice_naming_a_tool_this_call_does_not_offer_is_not_sent() -> None:
    """A stage narrows the tools; the author's choice narrows with it.

    `harness.run` builds `step_tools` per stage, so a call can offer a subset of
    the agent's tools. `resolve_tool_choice` validates the NAME against THAT
    call's `tool_defs` and raises on a miss, and it is right to: the setting is
    about a tool the model was never given.
    """
    t = Checking(Script([Turn("Decision: approved.")]))
    _one_call(t, {"tool-choice": "payments"}, [{"name": "lookup", "description": "looks up"}])
    assert "tool_choice" not in (t.saw_settings or {}), t.saw_settings

    # The same choice on a call that DOES offer it goes, as a `list[str]` —
    # so this is a rule about the call and not a refusal to send names.
    ok = Checking(Script([Turn("Decision: approved.")]))
    _one_call(ok, {"tool-choice": "payments"}, PAYMENTS)
    assert (ok.saw_settings or {}).get("tool_choice") == ["payments"], ok.saw_settings


@pytest.mark.parametrize(
    "chose,tools,sent",
    [
        ("auto", [], "auto"),
        ("none", [], "none"),
        ("required", PAYMENTS, "required"),
    ],
)
def test_a_tool_choice_a_call_can_carry_is_still_sent(chose, tools, sent) -> None:
    """The other side of the guard, so it is a rule and not a retreat.

    `auto` and `none` are answers a call with no tools can still give — "pick for
    yourself" and "do not call one" are both satisfiable with nothing to pick
    from, and `resolve_tool_choice` returns them unchanged in that state. Only
    `required` and a NAME need the tool set they are about.
    """
    t = Checking(Script([Turn("Decision: approved.")]))
    _one_call(t, {"tool-choice": chose}, tools)
    assert (t.saw_settings or {}).get("tool_choice") == sent, t.saw_settings


def test_a_thinking_the_sdk_discards_is_reported_even_on_a_thinking_model() -> None:
    """The third question `prepare_request` asks, which this transport missed.

    `models/__init__.py` reads, in full::

        if supports_thinking or thinking_always_enabled:
            if not (thinking_value is False and thinking_always_enabled):
                params = replace(params, thinking=thinking_value)

    `thinking: none` is PACT's word for *do not* and translates to `False` here.
    On a profile that thinks ALWAYS, the SDK discards exactly that combination
    and thinks anyway — so a transport asking only the first question reports a
    `tier: core` key as honoured on a run where the SDK provably threw it away.
    """
    from pydantic_ai.profiles import ModelProfile

    class Always(Recording):
        def __init__(self, *a, **kw) -> None:
            super().__init__(*a, **kw)
            self._model = FunctionModel(
                self._respond, profile=ModelProfile(thinking_always_enabled=True)
            )

    t = Always(Script([Turn("Decision: approved.")]))
    out = _ran(t, {"thinking": "none"})
    assert t.saw_params.thinking is None, "the SDK dropped it, quietly"
    assert "settings.thinking" in out.unmetered, out.unmetered

    # And an effort level the same model DOES honour is not reported, so the line
    # above is about the value and not a blanket refusal.
    t2 = Always(Script([Turn("Decision: approved.")]))
    out2 = _ran(t2, {"thinking": "high"})
    assert t2.saw_params.thinking == "high", t2.saw_params
    assert "settings.thinking" not in out2.unmetered, out2.unmetered
