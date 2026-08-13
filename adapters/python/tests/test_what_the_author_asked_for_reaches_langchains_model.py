"""The `settings:` block an author writes reaches LangChain's own model call.

Same defect as `test_what_the_author_asked_for_reaches_pydantic_ais_request.py`
and a very different answer, because the two SDKs have very different amounts to
say about generation parameters. Measured on this transport before the fix, on a
spec carrying all twelve:

```text
    settings.frequency-penalty, settings.max-tokens,
    settings.parallel-tool-calls, settings.presence-penalty, settings.seed,
    settings.service-tier, settings.stop-sequences, settings.temperature,
    settings.thinking, settings.tool-choice, settings.top-k, settings.top-p
```

**Four of the twelve are mapped, and the other eight are the point of the file.**
The seam here is `BaseChatModel`, and `langchain_core` 1.5.3 — the only
`lang*` package installed in this environment — has a name of its own for
exactly four of PACT's keys:

* `stop` is a first-class parameter of `_generate` / `_agenerate` and of
  `bind(stop=...)`.
* `temperature` and `max_tokens` are `langchain_core`'s own SPELLING for the two
  commonest generation parameters — `ModelProfile.temperature` declares whether a
  model supports one, and `BaseChatModel._get_ls_params` reads both off the
  kwargs by exactly those names. Neither is a parameter of `BaseChatModel`
  itself. What delivers them is an integration's `_generate(**kwargs)` putting
  them into the request it builds, which is what `bind()` is documented to be
  for and which **nothing installed here can check**, since no integration
  package is a dependency of this tree. `_get_ls_params` in particular builds
  LangSmith TRACING metadata and sends nothing to any provider, so it is
  evidence about the name and about nothing else; the first version of this file
  cited it as though it were evidence about delivery, and it is not. This bullet
  is therefore a weaker claim than the two either side of it, and it is written
  down as one.
* `tool_choice` is a keyword-only parameter of `BaseChatModel.bind_tools`, whose
  own docstring gives the vocabulary: *"The tool to use. If 'any' then any tool
  can be used."* So PACT's `required` is spelled `any` here — the same word
  Anthropic uses and not the one an OpenAI-compatible endpoint uses — and each
  integration's `bind_tools` is where a NAME becomes that provider's object.

The other eight — `thinking`, `top-p`, `top-k`, `seed`, `presence-penalty`,
`frequency-penalty`, `parallel-tool-calls`, `service-tier` — have no name
anywhere in `langchain_core`. They exist only as kwargs of a concrete
integration, they are spelled differently in each (`top_k` is on
`ChatAnthropic` and not on `ChatOpenAI`; thinking is `reasoning_effort` on one
and a `thinking={...}` dict on another), and no integration package is installed
here to check any of it against. `bind()` forwards an unknown kwarg without
complaint, straight into the provider payload or into an integration's
`model_kwargs`, so guessing a name would produce exactly the failure the
translate-or-nothing rule exists to prevent: a setting in a shape the provider
ignores, with nothing saying it did not happen. They are reported instead.

Mutation: in `langchain_transport.model_call`, replace `runnable` with
`self._model` on the `ainvoke` line — the settings are still computed, still
bound to a runnable, and that runnable is never invoked. Three tests go red,
`test_the_four_settings_langchain_has_a_name_for_reach_the_model`,
`test_a_tool_choice_naming_a_tool_this_call_does_not_offer_is_not_sent` and
`test_an_author_who_wrote_only_the_core_two_is_fully_honoured`, and the rest
still passed — including
`test_the_eight_langchain_has_no_name_for_are_reported_not_guessed`, which
asserts an ABSENCE and is therefore satisfied by a transport that sends nothing
at all. Recorded here rather than deleted: that test is what pins the honesty
half, and it is not what pins the delivery half. The same is true of
`test_a_tool_choice_never_reaches_a_call_without_going_through_bind_tools`,
which is an absence test on purpose.

Second mutation, for the branch this file got wrong the first time: put back
`elif chose is not None: attach["tool_choice"] = _tool_choice(chose)` in
`bound_for_request`. All four parameters of
`test_a_tool_choice_never_reaches_a_call_without_going_through_bind_tools` go
red, including the `none` one — which is why that test is parametrised over the
four authored values rather than written once with the safest of them.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402

pytest.importorskip(
    "langchain_core", reason="LangChain is not installed in this environment"
)

from pact_adapters.transports.langchain_transport import (  # noqa: E402
    LangChainTransport,
    _KWARGS,
    _tool_choice,
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

#: The eight `langchain_core` has no word for, and why each is reported. Held as
#: data so the file states the reason for every left-over key rather than
#: asserting a count.
NO_NAME_IN_CORE = {
    "thinking": "spelled reasoning_effort on one integration and a dict on another",
    "top-p": "an integration kwarg, named nowhere in langchain_core",
    "top-k": "on ChatAnthropic, absent from ChatOpenAI",
    "seed": "on ChatOpenAI, absent from ChatAnthropic",
    "presence-penalty": "OpenAI-shaped only",
    "frequency-penalty": "OpenAI-shaped only",
    "parallel-tool-calls": "OpenAI-shaped only",
    "service-tier": "OpenAI-shaped only, and free text in the schema",
}


class Recording(LangChainTransport):
    """The shipped transport, keeping what LangChain handed `_generate`.

    `stop` and `**kwargs` there are what came through `Runnable.ainvoke` after
    `bind`/`bind_tools` — LangChain's own machinery, not a dict this test built.
    """

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.saw_stop: list | None = None
        self.saw_kwargs: dict = {}
        transport = self

        inner = self._model._generate

        def _generate(messages, stop=None, run_manager=None, **kwargs):
            transport.saw_stop = stop
            transport.saw_kwargs = dict(kwargs)
            return inner(messages, stop=stop, run_manager=run_manager, **kwargs)

        object.__setattr__(self._model, "_generate", _generate)


def _spec(settings: dict) -> AgentSpec:
    return AgentSpec(
        name="refund-desk",
        description="decides refunds",
        instructions="Be brief.",
        tools=(ToolSpec(name="payments", description="pays"),),
        settings=dict(settings),
    )


def _ran(transport: LangChainTransport, settings: dict):
    return asyncio.run(run(_spec(settings), transport, "hello"))


def test_the_four_settings_langchain_has_a_name_for_reach_the_model() -> None:
    """The request, not the mapping table.

    The register records the trap in its own words: *"A test of mine failed its
    own mutation here. The first version asserted `_WIRE` membership and what
    `apply_settings` returned — both true of a transport that then drops every
    setting on the floor."* So this reads `stop` and `**kwargs` inside
    `_generate`, which is where LangChain delivers what was bound.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)

    # `stop` is first-class on `_generate`, not a kwarg — it has its own
    # parameter in the signature, which is what makes it the one PACT key
    # `BaseChatModel` itself is guaranteed to honour.
    assert t.saw_stop == ["END"], t.saw_stop
    assert t.saw_kwargs.get("temperature") == 0.2, t.saw_kwargs
    assert t.saw_kwargs.get("max_tokens") == 512, t.saw_kwargs
    # A tool NAME reaches `_generate` as the bare string, which is what LangChain
    # takes: each integration's own `bind_tools` is what turns it into that
    # provider's object.
    assert t.saw_kwargs.get("tool_choice") == "payments", t.saw_kwargs
    # And the tools went with it, because `tool_choice` without them is a
    # setting about nothing.
    assert [d["name"] for d in t.saw_kwargs.get("tools") or []] == ["payments"], t.saw_kwargs

    # `required` is `any` in LangChain's vocabulary, and the translation happens
    # on the way to the model rather than only inside a helper.
    other = Recording(Script([Turn("Decision: approved.")]))
    _ran(other, {"tool-choice": "required"})
    assert other.saw_kwargs.get("tool_choice") == "any", other.saw_kwargs


def test_the_eight_langchain_has_no_name_for_are_reported_not_guessed() -> None:
    """Honesty beats coverage.

    `bind()` forwards an unknown kwarg without complaint. Sending `top_k` to an
    integration that has no such parameter puts it in the provider payload or in
    `model_kwargs`, and the author is never told. Every one of these is named on
    `RunResult.unmetered` instead, and none of them is sent.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, ALL_TWELVE)

    for key, why in NO_NAME_IN_CORE.items():
        assert f"settings.{key}" in out.unmetered, f"{key} ({why}) was not reported"
    for guessed in ("top_p", "top_k", "seed", "presence_penalty",
                    "frequency_penalty", "parallel_tool_calls", "service_tier",
                    "thinking", "reasoning_effort"):
        assert guessed not in t.saw_kwargs, f"{guessed} was guessed onto the call"

    left = sorted(u for u in out.unmetered if u.startswith("settings."))
    assert left == sorted(f"settings.{k}" for k in NO_NAME_IN_CORE), left


def test_one_authored_word_becomes_langchains_own_word() -> None:
    """Translate or nothing, at the value level.

    `bind_tools(tools, tool_choice=...)` is the method LangChain defines for
    this, and its docstring gives the vocabulary: `any` is the word for "use a
    tool", where an OpenAI-compatible endpoint says `required`. A NAME goes
    through as a bare string on purpose — here the bare string IS the interface,
    and each integration's own `bind_tools` is what turns it into
    `{"type": "function", "function": {"name": ...}}` or `{"type": "tool",
    "name": ...}`. That is the opposite of the ollama case, where the bare string
    reaches the wire and silently means nothing.
    """
    assert _tool_choice("required") == "any"
    assert _tool_choice("auto") == "auto"
    assert _tool_choice("none") == "none"
    assert _tool_choice("payments") == "payments"


@pytest.mark.parametrize("chose", ["required", "payments", "none", "auto"])
def test_a_tool_choice_never_reaches_a_call_without_going_through_bind_tools(
    chose: str,
) -> None:
    """The branch that used to exist here, and why it was worse than nothing.

    On a call with no tools, `bound_for_request` attached the tool choice with
    `bind()` rather than `bind_tools()`. A plain bound kwarg is forwarded by an
    integration's `_generate` straight into the request it builds, and
    `bind_tools` is the ONLY place any integration translates a tool choice. So
    what a provider received was one of two things, measured on the shipped
    transport before this fix::

        required -> bind kwargs: {'tool_choice': 'any'}
        payments -> bind kwargs: {'tool_choice': 'payments'}

    `any` is a word no OpenAI-compatible endpoint accepts. `payments` is a bare
    string such an endpoint accepts and silently ignores. That is the ollama sin
    this file's own docstrings forbid, and it was not an edge case:
    `harness.run` makes one closing call with NO tools on every ceiling-terminated
    run, and a stage that narrows `tools:` produces the same state.

    Parametrised over all four authored values including `none` — the one value
    that IS valid raw on both wire formats — because a test that picked only that
    one certified the branch without exercising the failure. Nothing goes now.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    spec = AgentSpec(
        name="advisor",
        description="answers",
        instructions="Be brief.",
        settings={"tool-choice": chose},
    )
    asyncio.run(run(spec, t, "hello"))
    assert "tool_choice" not in t.saw_kwargs, t.saw_kwargs
    assert "tools" not in t.saw_kwargs, t.saw_kwargs


def test_a_tool_choice_naming_a_tool_this_call_does_not_offer_is_not_sent() -> None:
    """A stage narrows the tools; the author's choice narrows with it.

    `harness.run` builds `step_tools` per stage from the stage's own `tools:`
    line, so a run can reach the model with a subset of the agent's tools or with
    none of them. A `tool_choice` naming a tool that is not in THAT call's list
    is a `{"type": "function", "function": {"name": ...}}` the provider will
    reject — the setting is about something the model was never given. It is left
    off the call rather than approximated.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    spec = AgentSpec(
        name="refund-desk",
        description="decides refunds",
        instructions="Be brief.",
        tools=(ToolSpec(name="lookup", description="looks up"),),
        settings={"tool-choice": "payments"},
    )
    asyncio.run(run(spec, t, "hello"))
    assert [d["name"] for d in t.saw_kwargs.get("tools") or []] == ["lookup"]
    assert "tool_choice" not in t.saw_kwargs, t.saw_kwargs

    # And the same choice DOES go when the call offers the tool it names, so the
    # rule above is about this call and not a refusal to send names at all.
    ok = Recording(Script([Turn("Decision: approved.")]))
    _ran(ok, {"tool-choice": "payments"})
    assert ok.saw_kwargs.get("tool_choice") == "payments", ok.saw_kwargs


def test_an_author_who_wrote_only_the_core_two_is_fully_honoured() -> None:
    """`max-tokens:` and `thinking:` are the two `tier: core` keys — the ones a
    non-technical author writes. Only one of them survives on this target, and
    the run says which.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {"max-tokens": 64, "thinking": "low"})
    assert t.saw_kwargs.get("max_tokens") == 64, t.saw_kwargs
    assert sorted(u for u in out.unmetered if u.startswith("settings.")) == [
        "settings.thinking"
    ]


def test_the_run_still_works_when_the_author_wrote_no_settings() -> None:
    """A transport that only works with a `settings:` block is worse than the
    one it replaced. Nothing bound, nothing reported, and no `stop` invented."""
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {})
    assert t.saw_stop is None, t.saw_stop
    assert not [k for k in t.saw_kwargs if k in _KWARGS.values()], t.saw_kwargs
    assert [u for u in out.unmetered if u.startswith("settings.")] == []


def test_the_transport_still_counts_what_the_call_carried() -> None:
    """The metering that already landed here must survive the rewiring.

    `model_call` used to reach `_agenerate` directly and read
    `ChatResult.generations[0].message`; it now goes through `Runnable.ainvoke`,
    which returns the `AIMessage` itself. Both money ceilings read `usage()`, so
    a rewiring that lost `usage_metadata` would put them back on `unmetered`
    without failing anything above.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)
    tokens, _money = t.usage()
    assert tokens > 0, "the call carried nothing the meter could see"
