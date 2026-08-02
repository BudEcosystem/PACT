"""OpenAI Agents SDK as a transport (harness lowering).

The seam is `agents.models.interface.Model` — the interface `Runner` calls. The
Agents SDK's native abstraction owns handoffs, guardrails and the agent loop;
implementing `Model` takes the layer beneath all of it, so PACT keeps the loop
and the SDK contributes its request/response plumbing.
"""

from __future__ import annotations

import json
from typing import Any

from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from ..harness import ToolCall
from ..resolve import default_model, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, tokens_sent, what_the_summariser_cost
from ._summarise import summarise_with


class _ScriptedModel(Model):
    def __init__(self, script: Script) -> None:
        self._script = script
        self._history: list[dict[str, Any]] = []
        #: The SDK's own usage object off the last response this built.
        self.usage = Usage()

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        turn = self._script.next_turn(self._history)
        output: list[Any] = []
        if turn.text:
            output.append(
                ResponseOutputMessage(
                    id="m1", type="message", role="assistant", status="completed",
                    content=[ResponseOutputText(type="output_text", text=turn.text,
                                                annotations=[])],
                )
            )
        for i, c in enumerate(turn.tool_calls):
            output.append(
                ResponseFunctionToolCall(
                    id=f"f{i}", type="function_call", call_id=f"c{i}",
                    name=c.name, arguments=json.dumps(dict(c.args)),
                )
            )
        # `agents.usage.Usage`, filled in rather than left at its zeroed default.
        # It was a bare `Usage()` for a round, which is why this transport had no
        # `usage()` to offer and both money ceilings went out on
        # `RunResult.unmetered` on every run. Written onto the response object
        # the SDK already carries, so the field a live model provider fills in is
        # the one PACT bills from.
        went_in = tokens_sent(
            str(kwargs.get("system_instructions") or ""), self._history
        )
        came_out = tokens_in(
            "".join(
                part.text
                for item in output
                if isinstance(item, ResponseOutputMessage)
                for part in item.content
                if isinstance(part, ResponseOutputText)
            )
            + "".join(
                f"{item.name}{item.arguments}"
                for item in output
                if isinstance(item, ResponseFunctionToolCall)
            )
        )
        self.usage = Usage(
            requests=1, input_tokens=went_in, output_tokens=came_out,
            total_tokens=went_in + came_out,
        )
        return ModelResponse(output=output, usage=self.usage, response_id="r1")

    def stream_response(self, *a: Any, **k: Any):  # pragma: no cover - unused
        raise NotImplementedError("PACT does not stream through this seam")


class OpenAIAgentsTransport:
    name = "openai-agents"

    #: Which runtime this transport is, in the catalogue's own `served-by:`
    #: vocabulary. Empty on purpose: this is a FRAMEWORK adapter, not a provider
    #: one — the Agents SDK routes through a host-chosen `ModelProvider` —
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
        #: `models/catalog.yaml` is priced. `AnthropicTransport.__init__` states
        #: the reason in full.
        self.workspace = workspace
        self._model = _ScriptedModel(script)
        #: What the last summarising call cost, priced on the SUMMARISER's row.
        #: `None` means nobody could price it.
        self._summary: "tuple[int, float] | None" = (0, 0.0)
        #: Whether the catalogue publishes a price for the bound model. See
        #: `AnthropicTransport.__init__` for why this is not the same question as
        #: whether `usage()` exists.
        self.prices_money = can_price(self.model, self.workspace)

    def usage(self) -> tuple[int, "float | None"]:
        """What the last call carried, and what the catalogue says it cost.

        Read off `agents.usage.Usage`, the object the SDK's own `ModelResponse`
        already carries. The fullest statement of why the price comes from the
        catalogue rather than from here is on `AnthropicTransport.usage`.
        """
        used = self._model.usage
        return priced(self.model, used.input_tokens, used.output_tokens, self.workspace)

    def summary_usage(self) -> "tuple[int, float] | None":
        """What the last summarising call cost, on the model that made it.

        Separate from `usage()` because `write_summary` binds a SECOND model —
        `harness.Transport` says why. Without it a `summarised-by:` model spends
        outside the author's cap. `None` when the catalogue cannot price that
        model, so the run says `summarised-by-cost` rather than charging zero.
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

        A second `Model`, not a handoff: the Agents SDK's own answer to "another
        model takes this" is a handoff, and a handoff transfers the conversation
        rather than compressing it — the thing being summarised would leave.

        Synchronous for the reason `ollama_transport.py` gives; `_summarise.py`
        says how that is honoured over an async-only seam.
        """
        other = OpenAIAgentsTransport(self.script, model=model, workspace=self.workspace)
        said = summarise_with(other, text)
        # Priced on the summarising model's own row, by asking the transport
        # that made the call rather than re-deriving the figure here.
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
        self._model._history = history
        response = await self._model.get_response(
            system_instructions=system, input=_to_input(history), model_settings=None,
            tools=[], output_schema=None, handoffs=[], tracing=None,
        )
        text = "".join(
            part.text
            for item in response.output
            if isinstance(item, ResponseOutputMessage)
            for part in item.content
            if isinstance(part, ResponseOutputText)
        )
        calls = [
            ToolCall(name=item.name, args=json.loads(item.arguments or "{}"))
            for item in response.output
            if isinstance(item, ResponseFunctionToolCall)
        ]
        return text, calls


def _to_input(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in history:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            out.append({"role": "assistant", "content": m["content"]})
        elif m["role"] == "tool":
            out.append({"role": "user", "content": f"[tool {m['name']}] {m['content']}"})
    return out
