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
        }

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
        result = await self._model._agenerate(messages)
        msg = result.generations[0].message
        # Off the SDK's own object, not a private tally beside it, so the field a
        # live provider fills in is the one PACT bills from.
        used = getattr(msg, "usage_metadata", None) or {}
        self._counted = (
            int(used.get("input_tokens") or 0),
            int(used.get("output_tokens") or 0),
        )
        calls = [ToolCall(name=c["name"], args=c.get("args") or {}) for c in (msg.tool_calls or [])]
        return (msg.content or ""), calls
