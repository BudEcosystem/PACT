"""The `settings:` block an author writes reaches AutoGen's own model client.

Measured on this transport before the fix, on a spec carrying all twelve keys,
`RunResult.unmetered` read:

```text
    settings.frequency-penalty, settings.max-tokens,
    settings.parallel-tool-calls, settings.presence-penalty, settings.seed,
    settings.service-tier, settings.stop-sequences, settings.temperature,
    settings.thinking, settings.tool-choice, settings.top-k, settings.top-p
```

— every one of them, because `AutoGenTransport` had no `apply_settings` at all
and the harness reports the whole block when a transport cannot take it.

**Eight of the twelve are mapped here, and the other four are the point of the
file.** The seam is `autogen_core.models.ChatCompletionClient.create`, whose
signature (verified against autogen-core 0.7.5, installed here) is

```python
    async def create(
        self, messages, *, tools=[], tool_choice="auto",
        json_output=None, extra_create_args={}, cancellation_token=None,
    ) -> CreateResult
```

so there are exactly two doors for a generation parameter:

* `tool_choice`, which has its own keyword and its own vocabulary — the three
  words `auto`, `required` and `none` go through as written, and a NAMED tool is
  typed `Tool`, not `str`. AutoGen's docstring for it says so: *"A single Tool
  object to force the model to use"*. A bare name here is the wrong TYPE, which
  is a better failure than the OpenAI-compatible endpoint's silent no-op and
  still not one to ship — so `_NamedTool` builds the object.
* `extra_create_args`, documented as *"Extra arguments to pass to the underlying
  client"*, whose vocabulary is therefore that CLIENT's. This transport declares
  `runtime = ""` — the host picks the client — so the question a row in
  `_CREATE_ARGS` has to answer is not *"is this an OpenAI chat-completions
  parameter"* but *"will the endpoint behind an unknown client DO something with
  it"*. Being a name in
  `openai.types.chat.completion_create_params.CompletionCreateParamsBase`
  (openai 2.50.0, installed here) is necessary and not sufficient; every name in
  the table was checked against it, and three names that ARE in it are refused
  anyway, below.

**The four left over, and why each.** They are held in `WILL_NOT_CLAIM` below so
this file states a reason per key rather than asserting a count:

* `top-k` has no spelling in that parameter set at all. AutoGen's Ollama client
  nests it inside an `options` object and its Anthropic client takes it
  top-level, so one spelling would be right on one client and silently nothing
  on another.
* `thinking` and `parallel-tool-calls` DO have spellings there —
  `reasoning_effort` and `parallel_tool_calls` — so a client would validate them
  and the openai package would post them. Being posted is not being honoured.
  `ollama_transport.py` is the one transport in this tree that NAMES its
  endpoint, and it records of the OpenAI-compatible `/v1/chat/completions`
  surface — the surface the distribution's default locally-served model answers
  on — that it *"takes neither"*. A transport that does not know which client it
  has cannot claim more than the one that does.
* `service-tier` is an OpenAI-cloud routing word. Nothing serving weights
  locally routes on it and no other provider has the concept.

**This table and `ollama_transport._WIRE` differ in BOTH directions, on purpose,
and the two files name each other.** `_WIRE` maps `top-k` and this does not,
because that transport speaks to a measured endpoint and can know; this refuses
`thinking`, `parallel-tool-calls` and `service-tier` on that transport's own
finding about the same endpoint. `test_the_two_tables_disagree_only_where_one_of
_them_knows_more` pins the disagreement in the one direction each way, so a
future edit to either table that quietly makes them contradict each other fails
here rather than being read as agreement.

Losing `thinking` hurts most — it is one of the two `tier: core` keys, the ones
a non-technical author writes — and
`test_the_core_key_this_door_can_carry_lands_and_the_other_is_reported` exists to
say so out loud rather than let a coverage figure hide it.

Mutation: in `autogen_transport.model_call`, pass only the messages —
`await self._client.create(self.create_args_for(system, history, tools)["messages"])`
— so the settings are still mapped, the table is still right and
`apply_settings` still returns the same four, but nothing crosses the seam. Five
went red:

```text
    FAILED test_the_eight_autogen_has_a_door_for_reach_the_client
    FAILED test_the_three_plain_words_go_through_as_autogen_spells_them
    FAILED test_a_named_tool_choice_arrives_as_the_object_the_type_demands
    FAILED test_the_core_key_this_door_can_carry_lands_and_the_other_is_reported
    FAILED test_a_choice_a_tool_less_call_can_still_carry_is_sent
```

and five stayed GREEN, which is worth recording rather than hiding:
`test_the_four_autogen_will_not_claim_are_reported_not_guessed` and
`test_a_choice_a_tool_less_call_cannot_carry_is_not_sent` assert ABSENCES, and a
transport that sends nothing at all satisfies both;
`test_the_run_still_works_when_the_author_wrote_no_settings` asserts the same
about a spec with no settings; `test_the_two_tables_disagree_only_where_one_of
_them_knows_more` reads the two tables and never makes a call at all; and
`test_the_transport_still_counts_what_the_call_carried` only needs the call to
happen. They pin the honesty, the coupling and the metering halves, and they are
not what pins the delivery half — which is exactly the register's warning about
seam-shaped tests, met head on rather than argued around.
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
    "autogen_core", reason="AutoGen is not installed in this environment"
)

from autogen_core.tools import Tool  # noqa: E402

from pact_adapters.transports.autogen_transport import (  # noqa: E402
    AutoGenTransport,
    _CREATE_ARGS,
)
from pact_adapters.transports.ollama_transport import _WIRE  # noqa: E402


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

#: What each mapped key is called on the way through `extra_create_args`, and
#: the value the author wrote. Held as data so the file states the whole mapping
#: rather than spot-checking three of it. `tool-choice` is the eighth and is not
#: here: it has a keyword of its own.
THROUGH_THE_DOOR = {
    "max_tokens": 512,
    "temperature": 0.2,
    "top_p": 0.9,
    "stop": ["END"],
    "seed": 7,
    "presence_penalty": 0.5,
    "frequency_penalty": 0.1,
}

#: The four this transport will not claim, the reason for each, and the
#: spellings that must NOT appear on the call. Two of the four have a perfectly
#: valid OpenAI name and are refused anyway, which is the part worth reading:
#: passing a client's validator is not the same as being honoured by the
#: endpoint behind it.
WILL_NOT_CLAIM = {
    "top-k": (
        "no top_k in the OpenAI chat-completions parameter set; AutoGen's Ollama "
        "client nests it in `options` and its Anthropic client takes it top-level",
        ("top_k", "topK", "num_predict", "options"),
    ),
    "thinking": (
        "reasoning_effort IS an OpenAI name, so a client would post it — and the "
        "OpenAI-compatible endpoint ollama_transport.py measures takes it not at all",
        ("reasoning_effort", "reasoning", "thinking"),
    ),
    "parallel-tool-calls": (
        "parallel_tool_calls IS an OpenAI name, and the same measured endpoint "
        "takes it not at all",
        ("parallel_tool_calls",),
    ),
    "service-tier": (
        "an OpenAI-cloud routing word; nothing serving weights locally routes on it",
        ("service_tier",),
    ),
}


class Recording(AutoGenTransport):
    """The shipped transport, keeping what reached `ChatCompletionClient.create`.

    Wrapped on the CLIENT rather than read off a builder, because the register
    records what a builder-only assertion is worth: *"The first version asserted
    `_WIRE` membership and what `apply_settings` returned — both true of a
    transport that then drops every setting on the floor."* What this keeps is
    the keyword arguments AutoGen's own interface received.
    """

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.saw: dict = {}
        inner = self._client.create
        transport = self

        async def create(messages, **kwargs):
            transport.saw = dict(kwargs)
            transport.saw["messages"] = messages
            return await inner(messages, **kwargs)

        object.__setattr__(self._client, "create", create)

    @property
    def sent(self) -> dict:
        """Just the generation parameters, as the underlying client sees them."""
        return dict(self.saw.get("extra_create_args") or {})


def _spec(settings: dict, tools: bool = True) -> AgentSpec:
    return AgentSpec(
        name="refund-desk",
        description="decides refunds",
        instructions="Be brief.",
        tools=(ToolSpec(name="payments", description="pays"),) if tools else (),
        settings=dict(settings),
    )


def _ran(transport: AutoGenTransport, settings: dict, tools: bool = True):
    return asyncio.run(run(_spec(settings, tools), transport, "hello"))


def test_the_eight_autogen_has_a_door_for_reach_the_client() -> None:
    """The call, not the mapping table.

    Seven arrive in `extra_create_args` and the eighth — `tool-choice` — has its
    own keyword, so both doors are read here.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)

    for wire, value in THROUGH_THE_DOOR.items():
        assert t.sent.get(wire) == value, (wire, t.sent)
    # And nothing invented beside them.
    assert set(t.sent) == set(THROUGH_THE_DOOR), t.sent

    # The eighth, through the keyword the interface gives it. A NAME is a
    # `Tool`, so what is asserted is the name that object carries.
    choice = t.saw.get("tool_choice")
    assert isinstance(choice, Tool), choice
    assert choice.name == "payments", choice.name


def test_the_four_autogen_will_not_claim_are_reported_not_guessed() -> None:
    """Honesty beats coverage, and two of these four are the interesting half.

    `top-k` has no OpenAI spelling. `service-tier` has one nothing local routes
    on. But `reasoning_effort` and `parallel_tool_calls` are real names in
    `CompletionCreateParamsBase` — a client would accept them and the openai
    package would post them — and they are still refused, because the one
    transport here that names its endpoint records that that endpoint honours
    neither. A setting posted and ignored is worse than one reported unhonoured,
    since nothing says it did not happen.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, ALL_TWELVE)

    for key, (why, spellings) in WILL_NOT_CLAIM.items():
        assert f"settings.{key}" in out.unmetered, f"{key} ({why}) was not reported"
        for guessed in spellings:
            assert guessed not in t.sent, f"{guessed} was guessed onto the call ({why})"

    left = sorted(u for u in out.unmetered if u.startswith("settings."))
    assert left == sorted(f"settings.{k}" for k in WILL_NOT_CLAIM), left


def test_the_two_tables_disagree_only_where_one_of_them_knows_more() -> None:
    """This table and `ollama_transport._WIRE` are coupled, and they differ in
    both directions. Read casually they look like two answers to one question;
    they are answers to two.

    `_WIRE` is one MEASURED endpoint, so it can map `top-k`, which is not an
    OpenAI chat-completions name at all and which `extra_create_args` therefore
    cannot carry to an unknown client. `_CREATE_ARGS` is the intersection over
    the clients a host might bind, so it refuses `thinking`,
    `parallel-tool-calls` and `service-tier` on `_WIRE`'s own published finding
    about that same endpoint.

    Pinned here so that revising one table against a real server and not the
    other fails a test instead of publishing two contradictory coverage figures.
    """
    only_ollama = set(_WIRE) - set(_CREATE_ARGS) - {"tool-choice"}
    only_autogen = set(_CREATE_ARGS) - set(_WIRE)
    assert only_ollama == {"top-k"}, only_ollama
    assert only_autogen == set(), only_autogen
    # And what AutoGen refuses that `_WIRE` also refuses, for the same reason
    # written down in two places.
    assert "thinking" not in _WIRE and "thinking" not in _CREATE_ARGS
    assert "parallel-tool-calls" not in _WIRE
    assert "parallel-tool-calls" not in _CREATE_ARGS


def test_the_core_key_this_door_can_carry_lands_and_the_other_is_reported() -> None:
    """`max-tokens:` and `thinking:` are the two `tier: core` keys — the ones a
    non-technical author writes, and the two whose absence from every transport
    started this round.

    Only ONE of them survives here, and that is the honest answer rather than a
    shortfall to be papered over. `max_tokens` is an OpenAI name the endpoint
    behind any plausible client acts on. `reasoning_effort` is an OpenAI name
    that the measured OpenAI-compatible endpoint does not act on, so it is named
    on `RunResult.unmetered` and no approximation of it is sent. An author who
    writes `thinking: low` here is TOLD it did not land, which is the whole
    point: the failure this round exists to close is the silent one.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {"max-tokens": 64, "thinking": "low"})
    assert t.sent.get("max_tokens") == 64, t.sent
    assert "reasoning_effort" not in t.sent, t.sent
    left = sorted(u for u in out.unmetered if u.startswith("settings."))
    assert left == ["settings.thinking"], left


def test_the_three_plain_words_go_through_as_autogen_spells_them() -> None:
    """`auto`, `required` and `none` are the interface's own three literals.

    Anthropic spells the middle one `any` and this one does not, which is the
    per-transport difference one mapping table each exists to absorb.
    """
    for word in ("auto", "required", "none"):
        t = Recording(Script([Turn("Decision: approved.")]))
        _ran(t, {"tool-choice": word})
        assert t.saw.get("tool_choice") == word, (word, t.saw.get("tool_choice"))


def test_a_named_tool_choice_arrives_as_the_object_the_type_demands() -> None:
    """Translate or nothing, at the value level.

    `tool_choice` here is typed `Tool | Literal["auto", "required", "none"]`. A
    bare `"payments"` is neither. It also has to arrive alongside the tool it
    names, or it is a setting about nothing — so the spec's tools go through the
    `tools` keyword on the same call.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, {"tool-choice": "payments"})

    choice = t.saw.get("tool_choice")
    assert isinstance(choice, Tool), choice
    assert choice.schema["name"] == "payments", choice.schema
    assert [s["name"] for s in t.saw.get("tools") or []] == ["payments"], t.saw.get("tools")


def test_a_choice_a_tool_less_call_can_still_carry_is_sent() -> None:
    """`none` is an answer a call with nothing to choose from can still give.

    `harness.run` closes every ceiling-terminated run with `model_call(
    instructions, history, [])`, and a stage may offer no tools, so "does this
    call carry the choice" is a per-CALL question that `apply_settings` — asked
    once, before the loop — cannot answer. `_tool_choice.can_choose` answers it,
    and `auto`/`none` pass: neither says anything about a tool that has to exist.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {"tool-choice": "none"}, tools=False)
    assert t.saw.get("tool_choice") == "none", t.saw
    assert not t.saw.get("tools"), t.saw.get("tools")
    assert [u for u in out.unmetered if u.startswith("settings.")] == []


def test_a_choice_a_tool_less_call_cannot_carry_is_not_sent() -> None:
    """And the two that do not pass, which is where the cost is real.

    Read against autogen-ext 0.7.5's `models/openai/_openai_client.py`, the
    reference client for this interface:

    * `required` — the whole translation is guarded by `if len(converted_tools)
      > 0:`, so on a tool-less call the parameter is never set. PACT sending it
      anyway would be a silent drop one layer down wearing the report of a
      delivery.
    * a NAME — worse. That file raises `ValueError("tool_choice specified but no
      tools provided")` when the value is a `Tool` and `tools` is empty, so a
      `tool-choice: payments` on a tool-less call would take the RUN down over a
      generation parameter.

    Nothing goes in their place: not sending is not approximating. The key is
    still reported honoured by `apply_settings`, which is a coarse report of a
    correct run and is named as still-open in the register's row C5 — closing it
    means giving `apply_settings` the spec's tools.
    """
    for word in ("required", "payments"):
        t = Recording(Script([Turn("Decision: approved.")]))
        out = _ran(t, {"tool-choice": word}, tools=False)
        assert "tool_choice" not in t.saw, (word, t.saw)
        assert [u for u in out.unmetered if u.startswith("settings.")] == []


def test_the_run_still_works_when_the_author_wrote_no_settings() -> None:
    """A transport that only works with a `settings:` block is worse than the one
    it replaced. Nothing sent, nothing reported, and no `tool_choice` invented —
    `create`'s own default is `auto`, and passing it explicitly would overwrite a
    host's choice with PACT's silence."""
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {})
    assert t.sent == {}, t.sent
    assert "tool_choice" not in t.saw, t.saw
    assert [u for u in out.unmetered if u.startswith("settings.")] == []
    assert not [k for k in t.sent if k in _CREATE_ARGS.values()], t.sent


def test_the_transport_still_counts_what_the_call_carried() -> None:
    """The metering that already landed here must survive the rewiring.

    `model_call` now hands `create` a keyword-argument dict rather than a bare
    positional list. Both money ceilings read `usage()`, which reads AutoGen's
    own `actual_usage()`, so a rewiring that stopped reaching the client at all
    would put them back on `unmetered` without failing anything above.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)
    tokens, _money = t.usage()
    assert tokens > 0, "the call carried nothing the meter could see"
