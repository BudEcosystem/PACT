"""LangChain as a transport (harness lowering).

The seam is `BaseChatModel` — LangChain's model interface, below chains, below
AgentExecutor, below LCEL. A `Runnable` pipeline would impose LangChain's own
composition semantics on a loop PACT already owns.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from ..harness import ToolCall
from ..resolve import default_model, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, what_the_summariser_cost
from ._summarise import summarise_with
from ._tool_choice import can_choose


class _ScriptedChatModel(BaseChatModel):
    """A BaseChatModel backed by the shared script."""

    script: Any = None

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kw) -> ChatResult:
        history = [
            {"role": "assistant" if isinstance(m, AIMessage) else "user", "content": m.content}
            for m in messages
            if isinstance(m, (AIMessage, HumanMessage, ToolMessage))
        ]
        turn = self.script.next_turn(history)
        # `AIMessage.usage_metadata` — LangChain's own slot for what a call
        # carried, filled in rather than left absent. It WAS absent for a round,
        # which is why this transport had no `usage()` to offer and both money
        # ceilings went out on `RunResult.unmetered` on every run of it: the
        # metering that closed "two ceilings that have never metered a real call"
        # landed on four of the seven shipped transports and this was one of the
        # three it missed. Measured before this line: the same document
        # terminated at `token-limit` on Anthropic and `step-limit` here, which
        # breaks the byte-identical-trace claim as well as the ceiling.
        #
        # The system message is counted with the rest, because a provider bills
        # it: `SystemMessage` is in `messages` and not in `history`, so it is
        # counted off `messages` directly.
        went_in = tokens_in("".join(str(m.content or "") for m in messages))
        came_out = tokens_in(
            (turn.text or "")
            + "".join(f"{c.name}{dict(c.args)}" for c in turn.tool_calls)
        )
        counted = {
            "input_tokens": went_in,
            "output_tokens": came_out,
            "total_tokens": went_in + came_out,
        }
        if turn.tool_calls:
            msg = AIMessage(
                content=turn.text,
                tool_calls=[
                    {"name": c.name, "args": dict(c.args), "id": f"c{i}"}
                    for i, c in enumerate(turn.tool_calls)
                ],
                usage_metadata=counted,
            )
        else:
            msg = AIMessage(content=turn.text, usage_metadata=counted)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        """What every LangChain integration's `bind_tools` does, and no more.

        `BaseChatModel.bind_tools` raises `NotImplementedError`, and each
        integration implements it as `self.bind(tools=..., tool_choice=...)`
        plus its own translation of the tool choice into the provider's shape.
        Implemented here so the transport can call the method LangChain DEFINES
        for a tool choice rather than smuggling the key in through `bind()` —
        the translation of a NAME into `{"type": "function", ...}` or
        `{"type": "tool", ...}` belongs to the integration, and reaching it
        through `bind_tools` is what leaves it there.
        """
        return self.bind(
            tools=list(tools),
            **({"tool_choice": tool_choice} if tool_choice is not None else {}),
            **kwargs,
        )

    @property
    def _llm_type(self) -> str:
        return "pact-scripted"


class LangChainTransport:
    name = "langchain"

    #: Which runtime this transport is, in the catalogue's own `served-by:`
    #: vocabulary. Empty on purpose: this is a FRAMEWORK adapter, not a provider
    #: one — `BaseChatModel` is an interface every provider implements —
    #: so which runtime sits behind it is the host's choice, and the
    #: distribution's default (locally servable, D17) is the right pick when the
    #: author pinned nothing. `anthropic_transport.py` is the one transport here
    #: that does name a runtime, and it has to: it cannot serve weights
    #: Anthropic does not.
    runtime = ""

    def __init__(
        self, script: Script, model: str | None = None, workspace: str = ""
    ) -> None:
        self.script = script
        self.model = model or default_model()
        #: The workspace root, so a row this workspace added to its own
        #: `models/catalog.yaml` is priced and sized.
        #: `AnthropicTransport.__init__` states the reason in full.
        self.workspace = workspace
        self._model = _ScriptedChatModel(script=script)
        #: What the last call carried, off the `AIMessage` the SDK built. Kept
        #: because `usage()` is asked AFTER `model_call` returns and the message
        #: is not carried past it.
        self._counted: tuple[int, int] = (0, 0)
        #: What the last summarising call cost, priced on the SUMMARISER's row.
        #: `None` means nobody could price it.
        self._summary: "tuple[int, float] | None" = (0, 0.0)
        #: Whether the catalogue publishes a price for the bound model. See
        #: `AnthropicTransport.__init__` for why this is not the same question as
        #: whether `usage()` exists.
        self.prices_money = can_price(self.model, self.workspace)

    def usage(self) -> tuple[int, "float | None"]:
        """What the last call carried, and what the catalogue says it cost.

        Read off `AIMessage.usage_metadata`, LangChain's own slot — so a live
        provider reports through the same line the scripted one does. The
        fullest statement of why the price comes from the catalogue rather than
        from here is on `AnthropicTransport.usage`.
        """
        return priced(self.model, *self._counted, workspace=self.workspace)

    def summary_usage(self) -> "tuple[int, float] | None":
        """What the last summarising call cost, on the model that made it.

        Separate from `usage()` because `write_summary` binds a SECOND model —
        `harness.Transport` says why. Without it a `summarised-by:` model spends
        outside the author's cap. `None` when the catalogue cannot price it.
        """
        return self._summary

    def context_window(self) -> int | None:
        """How much the bound model can hold, from `models/catalog.yaml`.

        Same rule and same source as every other transport here; the fullest
        statement of why is on `AnthropicTransport.context_window`. In short:
        Eve recovers a fact about a model by matching the provider string, so
        there is nowhere to write the fact down when the match is wrong. Here it
        is a catalogue row with a source and an `as-of` date beside it.
        """
        return window_of(self.model, workspace=self.workspace or None)

    def write_summary(self, text: str, model: str) -> str:
        """One summarising call, made with the model `summarised-by:` names.

        Same rule and same shape as every other transport that carries it; the
        fullest statement of why is on `AnthropicTransport.write_summary`. In
        short: a second transport rather than a second code path — same class,
        same script, another model id — because "summarise with a different
        model" is one model call and the harness already knows how to make one.
        `self.model` is untouched, so nothing about the work model changes.

        Synchronous for the reason `ollama_transport.py` gives; `_summarise.py`
        says how that is honoured over an async-only seam. `BaseChatModel` does
        publish a synchronous `invoke`, and it is deliberately not used: the
        other four framework transports have no such seam, and one mechanism
        that works on five beats a shortcut on two beside a bridge for three.
        """
        other = LangChainTransport(self.script, model=model, workspace=self.workspace)
        said = summarise_with(other, text)
        # Priced on the summarising model's own row, by asking the transport that
        # made the call rather than re-deriving the figure here.
        self._summary = what_the_summariser_cost(other)
        return said

    def lattice(self) -> dict[str, str]:
        return {
            "model_call": "native",
            "tool_calls": "native",
            "text_with_tool_calls": "native",
            "parallel_tool_calls": "native",
            "streaming": "emulated",
            "durable_resume": "unsupported",
            # The seam here is `BaseChatModel`, a model INTERFACE with no door a
            # `connect:` line could go out of — so nothing in this file reads
            # `ToolSpec.reaches`, and the reaching is PACT's own client above the
            # framework. `mock.py` states the rule once for every target that
            # shares it.
            "connected_tools": "emulated",
        }

    def apply_settings(self, settings: dict[str, Any]) -> tuple[str, ...]:
        """Take the author's `settings:` block, and say what could not be taken.

        FOUR of the twelve, and the eight left over are the honest part.

        The seam here is `BaseChatModel`, which is an INTERFACE rather than a
        provider — so unlike `ollama_transport.py` there is no wire format to map
        onto, only whatever vocabulary `langchain_core` itself defines. That
        vocabulary is small and it is checkable:

        * `stop` is a parameter of `_generate` / `_agenerate`, in the signature.
        * `tool_choice` is a keyword-only parameter of `bind_tools`.
        * `temperature` and `max_tokens` are `langchain_core`'s own spelling of
          the two commonest generation parameters. **Neither is a parameter of
          `BaseChatModel`**, and this is worth being exact about because the
          first version of this docstring was not: what carries them is an
          integration's `_generate(**kwargs)` forwarding them into the request it
          builds, which is the documented purpose of `bind()` — *"attach runtime
          kwargs"* — and which no test in this tree can check, because no
          integration package is installed here. What `langchain_core` does give
          is the SPELLING, in two places: `ModelProfile.temperature` (*"whether
          the model supports a temperature parameter"*) and
          `BaseChatModel._get_ls_params`, which reads `temperature` and
          `max_tokens` off the kwargs by those names. `_get_ls_params` builds
          LangSmith TRACING metadata and sends nothing to any provider, so it is
          evidence about the NAME and about nothing else. That is a weaker claim
          than the two above it and is written down as one.

        Everything else is a kwarg of a concrete integration, spelled
        differently in each — `top_k` is on `ChatAnthropic` and absent from
        `ChatOpenAI`, `seed` the other way round, and thinking is
        `reasoning_effort` on one and a `thinking={...}` dict on another. `bind()`
        forwards an unknown kwarg without complaint, into the provider payload or
        into an integration's `model_kwargs`, and the author is never told. That
        is the translate-or-nothing line: a setting in a shape the provider
        ignores is worse than one reported unhonoured, because nothing says it
        did not happen. So those eight come back here and land on
        `RunResult.unmetered`.

        This is a floor and not a ceiling. It grows the day a
        `langchain-openai` or `langchain-anthropic` is a dependency of this
        package and its parameter names can be checked against an INSTALLED
        version rather than remembered — and the same dependency is what would
        turn the `temperature`/`max_tokens` claim above from a spelling into a
        measured request payload.

        `tool-choice:` is answered here and again at every call. This says the
        SDK has a shape for the authored value; whether a PARTICULAR call can
        carry it depends on the tools that call offers, which nothing knows yet.
        `bound_for_request` decides that per call, and sends nothing rather than
        an approximation when the answer is no.
        """
        self._settings = dict(settings)
        return tuple(
            k for k in settings if k not in _KWARGS and k not in _FIRST_CLASS
        )

    def bound_for_request(self, tools: list[dict[str, Any]]):
        """The `Runnable` this transport is about to invoke.

        Split out for the reason `ollama_transport.payload_for` was: a test that
        asserts a mapping table and a return value is true of a transport that
        then drops every setting on the floor. `bind` and `bind_tools` are what
        LangChain calls "attaching runtime kwargs", and what they attach is
        delivered to `_generate` — which is where the tests read it.

        `tool_choice` leaves this method through `bind_tools` or it does not
        leave at all. There was a third path here for one round and it was the
        exact defect this round exists to close, pointing the other way: on a
        call with no tools the key was attached with `bind()` instead, and a
        plain bound kwarg is forwarded by an integration straight into the
        request payload without passing through the one method that translates
        it. What a provider then received was `tool_choice: "any"` — a word no
        OpenAI-compatible endpoint accepts — or `tool_choice: "payments"`, a bare
        string such an endpoint accepts and silently ignores. `harness.run` makes
        that call on every ceiling-terminated run, so it was not an edge case.
        """
        said = getattr(self, "_settings", {})
        model = self._model
        chose = said.get("tool-choice")
        offered = tuple(str(t["name"]) for t in tools)
        attach: dict[str, Any] = {
            _KWARGS[k]: v for k, v in said.items() if k in _KWARGS
        }
        if tools:
            # `bind_tools` rather than `bind(tool_choice=...)`, because the
            # method LangChain defines for a tool choice is also the method each
            # integration translates a tool NAME inside.
            model = model.bind_tools(
                [
                    {"name": t["name"], "description": t.get("description", ""),
                     "parameters": {"type": "object", "properties": {}}}
                    for t in tools
                ],
                # And only a choice THIS call can carry. `_tool_choice.can_choose`
                # says why `required` and a NAME both need the tool set they are
                # about; an author whose stage narrowed the tools away gets the
                # call without the key rather than a 400 from the provider.
                **(
                    {"tool_choice": _tool_choice(chose)}
                    if chose is not None and can_choose(chose, offered)
                    else {}
                ),
            )
        stop = said.get("stop-sequences")
        if stop is not None:
            # `stop` has its own parameter on `_generate`, which is what makes it
            # the one PACT key `BaseChatModel` itself is guaranteed to honour.
            attach["stop"] = [str(stop)] if isinstance(stop, str) else [str(s) for s in stop]
        return model.bind(**attach) if attach else model

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        messages: list[BaseMessage] = []
        if system:
            messages.append(SystemMessage(content=system))
        for m in history:
            if m["role"] == "user":
                messages.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                messages.append(AIMessage(content=m["content"]))
            elif m["role"] == "tool":
                messages.append(ToolMessage(content=m["content"], tool_call_id="c0"))
        # Through `Runnable.ainvoke` rather than straight into `_agenerate`,
        # because that is the path the bound kwargs travel: `bind` attaches them
        # to the runnable and LangChain's own machinery hands them down. It
        # returns the `AIMessage` itself rather than a `ChatResult`, so the usage
        # read below is one hop shorter and off the same object.
        runnable = self.bound_for_request(tools)
        msg = await runnable.ainvoke(messages)
        # Off the SDK's own object, not a private tally beside it, so the field a
        # live provider fills in is the one PACT bills from.
        used = getattr(msg, "usage_metadata", None) or {}
        self._counted = (
            int(used.get("input_tokens") or 0),
            int(used.get("output_tokens") or 0),
        )
        calls = [ToolCall(name=c["name"], args=c.get("args") or {}) for c in (msg.tool_calls or [])]
        return (msg.content or ""), calls


#: The author's key, and the kwarg `bind()` attaches. Two rows, and both are the
#: SPELLING `langchain_core` itself uses for these two parameters — in
#: `ModelProfile.temperature`, a capability it declares models may have, and in
#: `BaseChatModel._get_ls_params`, which reads `temperature` and `max_tokens` off
#: the kwargs by exactly those names. What DELIVERS them is an integration's
#: `_generate(**kwargs)` putting them in the request it builds, which is what
#: `bind()` is documented to be for and which nothing installed here can check;
#: `_get_ls_params` itself only fills in LangSmith tracing metadata. See
#: `apply_settings` for that distinction stated at length.
#:
#: Deliberately short. `top_p`, `top_k`, `seed`, `presence_penalty`,
#: `frequency_penalty`, `parallel_tool_calls`, `service_tier` and every spelling
#: of thinking are absent because `langchain_core` names none of them and no
#: integration package is installed here to check a guess against.
_KWARGS: dict[str, str] = {
    "max-tokens": "max_tokens",
    "temperature": "temperature",
}

#: The two keys that do NOT travel as ordinary bound kwargs. `stop-sequences` has
#: its own parameter on `_generate`; `tool-choice` has its own on `bind_tools`.
#: Named here so `apply_settings` counts them as honoured — they are mapped, just
#: not through `_KWARGS`.
_FIRST_CLASS = ("stop-sequences", "tool-choice")


def _tool_choice(value: Any) -> str:
    """One authored `tool-choice:` in LangChain's own vocabulary.

    `BaseChatModel.bind_tools`' docstring gives it: *"The tool to use. If 'any'
    then any tool can be used."* So PACT's `required` is `any` here — the word
    Anthropic uses, not the word an OpenAI-compatible endpoint uses — and one
    authored word working on both targets is what the `settings` group's own
    header promises.

    A NAME goes through as a bare string, and that is the RIGHT answer here where
    it is the wrong one on the ollama transport. There the bare string reaches
    the wire, is accepted, and silently means nothing. Here the bare string IS
    the interface: each integration's `bind_tools` is what turns it into
    `{"type": "function", "function": {"name": ...}}` or `{"type": "tool",
    "name": ...}`, which is why this transport hands it over through that method
    and not through `bind()`.

    That last sentence is now true without exception, and for one round it was
    not — `bound_for_request` had a branch that attached the result of this
    function with `bind()` when the call had no tools, which is the one route on
    which nothing translates it. What this function returns is only ever safe
    downstream of `bind_tools`, so it is only ever called there.
    """
    said = str(value).strip()
    return "any" if said == "required" else said
