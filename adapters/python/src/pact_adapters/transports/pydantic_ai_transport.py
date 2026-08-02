"""Pydantic AI as a transport (harness lowering).

The seam is `pydantic_ai.direct.model_request` — one model call, no agent loop,
no dependency graph, no output validation. The source audit called this "clean
and low-risk", and it is: Pydantic AI's `Agent` class is bypassed entirely, so
none of its control flow can diverge from PACT's.

What is *given up* by not using `Agent` is real and is declared in the lattice
below rather than hidden: output validators, retries, the dependency-injection
context, and history processors all live above `direct` and are PACT's job here.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import direct
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.usage import RequestUsage
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition

from ..harness import ToolCall
from ..resolve import default_model, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, tokens_sent, what_the_summariser_cost
from ._summarise import summarise_with


class PydanticAITransport:
    """Drives one model call through Pydantic AI's lowest-level entry point."""

    name = "pydantic-ai"

    #: Which runtime this transport is, in the catalogue's own `served-by:`
    #: vocabulary. Empty on purpose: this is a FRAMEWORK adapter, not a provider
    #: one — Pydantic AI drives whatever model object it is handed —
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
        self._model = FunctionModel(self._respond)
        self._history: list[dict[str, Any]] = []
        self._system: str = ""
        #: What the last call carried, off `ModelResponse.usage` — Pydantic AI's
        #: own slot, which this transport left at its zeroed default for a round.
        #: That is why it had no `usage()` to offer and both money ceilings went
        #: out on `RunResult.unmetered` for every run of it, and why the same
        #: document terminated at `step-limit` here and `token-limit` on
        #: Anthropic. `write_summary` records that this transport "was one of five
        #: real transports without it"; the same sweep had not been done for
        #: `usage()`.
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

        Read off `ModelResponse.usage`, the object Pydantic AI already returns,
        so a live model reports through the same line the scripted one does. The
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

        For a round this was one of five real transports without it, so the
        author's `summarise-older` rung reported itself unmetered and the ladder
        fell through to `if-it-still-does-not-fit:` on a conversation a
        summariser would have handled. Synchronous for the reason
        `ollama_transport.py` gives; `_summarise.py` says how that is honoured
        over an async-only seam.
        """
        other = PydanticAITransport(self.script, model=model, workspace=self.workspace)
        said = summarise_with(other, text)
        # Priced on the summarising model's own row, by asking the transport that
        # made the call rather than re-deriving the figure here.
        self._summary = what_the_summariser_cost(other)
        return said

    def lattice(self) -> dict[str, str]:
        # Honest per-feature accounting (invariant P-2). `emulated` means PACT's
        # harness provides it above the transport; `unsupported` means nothing
        # provides it on this path and a spec needing it must be refused.
        return {
            "model_call": "native",
            "tool_calls": "native",
            "text_with_tool_calls": "native",
            "parallel_tool_calls": "native",
            "streaming": "emulated",
            "durable_resume": "unsupported",
        }

    def _respond(self, messages: list[Any], info: AgentInfo) -> ModelResponse:
        """Called by Pydantic AI inside its own request machinery."""
        turn = self.script.next_turn(self._history)
        parts: list[Any] = []
        if turn.tool_calls:
            parts = [
                ToolCallPart(tool_name=c.name, args=dict(c.args), tool_call_id=f"c{i}")
                for i, c in enumerate(turn.tool_calls)
            ] + ([TextPart(content=turn.text)] if turn.text else [])
        else:
            parts = [TextPart(content=turn.text)]
        # `RequestUsage` on the response object the SDK already returns, filled
        # in rather than left at its zeroed default. The system prompt counts
        # with the history because a provider bills it.
        went_in = tokens_sent(self._system, self._history)
        came_out = tokens_in(
            (turn.text or "")
            + "".join(f"{c.name}{dict(c.args)}" for c in turn.tool_calls)
        )
        self._counted = (went_in, came_out)
        return ModelResponse(
            parts=parts, usage=RequestUsage(input_tokens=went_in, output_tokens=came_out)
        )

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        self._history = history
        self._system = system
        response = await direct.model_request(
            self._model,
            _to_messages(system, history),
            model_request_parameters=ModelRequestParameters(
                function_tools=[
                    ToolDefinition(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters_json_schema={"type": "object", "properties": {}},
                    )
                    for t in tools
                ],
                allow_text_output=True,
            ),
        )
        return _from_response(response)


def _to_messages(system: str, history: list[dict[str, Any]]) -> list[Any]:
    """PACT history -> Pydantic AI messages.

    Tool results become `ToolReturnPart`s rather than user text, because a
    framework that sees them as user turns will count turns differently and the
    traces will diverge for a reason that has nothing to do with the agent.
    """
    parts: list[Any] = [SystemPromptPart(content=system)] if system else []
    for m in history:
        if m["role"] == "user":
            parts.append(UserPromptPart(content=m["content"]))
        elif m["role"] == "tool":
            parts.append(
                ToolReturnPart(
                    tool_name=m["name"], content=m["content"], tool_call_id="c0"
                )
            )
    return [ModelRequest(parts=parts)]


def _from_response(response: ModelResponse) -> tuple[str, list[ToolCall]]:
    text = "".join(p.content for p in response.parts if isinstance(p, TextPart))
    calls = [
        ToolCall(name=p.tool_name, args=p.args if isinstance(p.args, dict) else {})
        for p in response.parts
        if isinstance(p, ToolCallPart)
    ]
    return text, calls
