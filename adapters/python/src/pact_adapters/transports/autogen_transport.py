"""AutoGen as a transport (harness lowering).

The seam is `autogen_core.models.ChatCompletionClient` — AutoGen's model
interface, below `AssistantAgent` and below the `Team`/`GroupChat` machinery.

This matters more here than elsewhere: AutoGen's native abstraction is a
conversational actor with a mailbox, and its group chat owns turn-taking. Any
mapping onto `AssistantAgent` would hand AutoGen control of the loop, and its
turn semantics differ from every other target in the set. Taking the model
client instead keeps the loop PACT's.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from autogen_core import CancellationToken, FunctionCall
from autogen_core.models import (
    AssistantMessage,
    ChatCompletionClient,
    CreateResult,
    LLMMessage,
    ModelInfo,
    RequestUsage,
    SystemMessage,
    UserMessage,
)

from ..harness import ToolCall
from ..resolve import default_model, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, what_the_summariser_cost
from ._summarise import summarise_with


class _ScriptedClient(ChatCompletionClient):
    """A ChatCompletionClient backed by the shared script."""

    def __init__(self, script: Script) -> None:
        self._script = script
        self._usage = RequestUsage(prompt_tokens=0, completion_tokens=0)

    async def create(self, messages: Sequence[LLMMessage], **kwargs: Any) -> CreateResult:
        history = _to_history(messages)
        turn = self._script.next_turn(history)
        # `RequestUsage`, filled in rather than left at zero. It was
        # `prompt_tokens=0, completion_tokens=0` for a round, which is why
        # `AutoGenTransport` had no `usage()` to offer and both money ceilings
        # went out on `RunResult.unmetered` on every run. AutoGen's own
        # `actual_usage()` is what the transport reads back, so the accessor a
        # live client fills in is the one PACT bills from.
        self._usage = RequestUsage(
            prompt_tokens=tokens_in("".join(str(_content(m)) for m in messages)),
            completion_tokens=tokens_in(
                (turn.text or "")
                + "".join(f"{c.name}{dict(c.args)}" for c in turn.tool_calls)
            ),
        )
        if turn.tool_calls:
            content: Any = [
                FunctionCall(id=f"c{i}", name=c.name, arguments=json.dumps(dict(c.args)))
                for i, c in enumerate(turn.tool_calls)
            ]
            # `CreateResult.content` is EITHER text OR calls — never both. Every
            # other target in the set can carry an assistant sentence alongside
            # its tool calls, so without somewhere to put it AutoGen would drop
            # the text and diverge. `thought` is AutoGen's own field for exactly
            # this, which turns a lost value into an `emulated` lattice entry
            # rather than a silent difference.
            return CreateResult(
                finish_reason="function_calls", content=content,
                usage=self._usage, cached=False, thought=turn.text or None,
            )
        return CreateResult(
            finish_reason="stop", content=turn.text, usage=self._usage, cached=False
        )

    def create_stream(self, *a: Any, **k: Any):  # pragma: no cover - unused
        raise NotImplementedError("PACT does not stream through this seam")

    async def close(self) -> None:
        return None

    def actual_usage(self) -> RequestUsage:
        return self._usage

    def total_usage(self) -> RequestUsage:
        return self._usage

    def count_tokens(self, messages: Sequence[LLMMessage], **k: Any) -> int:
        return 0

    def remaining_tokens(self, messages: Sequence[LLMMessage], **k: Any) -> int:
        return 1_000_000

    @property
    def capabilities(self) -> Any:
        return self.model_info

    @property
    def model_info(self) -> ModelInfo:
        return ModelInfo(
            vision=False, function_calling=True, json_output=False,
            family="unknown", structured_output=False,
        )


def _content(message: LLMMessage) -> Any:
    """What one AutoGen message carries, whatever kind it is.

    Counted for the token vector, so the SYSTEM message counts too — it is
    input the provider bills for, and a `loop:` that swaps a long instruction in
    per stage is a cost the author can act on.
    """
    return getattr(message, "content", "")


def _to_history(messages: Sequence[LLMMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, UserMessage):
            out.append({"role": "user", "content": m.content})
        elif isinstance(m, AssistantMessage):
            out.append({"role": "assistant", "content": m.content})
    return out


class AutoGenTransport:
    name = "autogen"

    #: Which runtime this transport is, in the catalogue's own `served-by:`
    #: vocabulary. Empty on purpose: this is a FRAMEWORK adapter, not a provider
    #: one — `ChatCompletionClient` is one every provider implements —
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
        self._client = _ScriptedClient(script)
        #: What the last summarising call cost, priced on the SUMMARISER's row.
        #: `None` means nobody could price it.
        self._summary: "tuple[int, float] | None" = (0, 0.0)
        #: Whether the catalogue publishes a price for the bound model. See
        #: `AnthropicTransport.__init__` for why this is not the same question as
        #: whether `usage()` exists.
        self.prices_money = can_price(self.model, self.workspace)

    def usage(self) -> tuple[int, "float | None"]:
        """What the last call carried, and what the catalogue says it cost.

        Read through `ChatCompletionClient.actual_usage()` — AutoGen's own
        accessor, so a live client reports through the same line the scripted
        one does. The fullest statement of why the price comes from the
        catalogue rather than from here is on `AnthropicTransport.usage`.
        """
        used = self._client.actual_usage()
        return priced(
            self.model, used.prompt_tokens, used.completion_tokens, self.workspace
        )

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

        A second `ChatCompletionClient`, not a second agent: AutoGen's native
        answer to "another model summarises" would be another `AssistantAgent`
        in the group chat, which would give AutoGen a turn in a conversation it
        is only meant to be compressing.

        Synchronous for the reason `ollama_transport.py` gives; `_summarise.py`
        says how that is honoured over an async-only seam.
        """
        other = AutoGenTransport(self.script, model=model, workspace=self.workspace)
        said = summarise_with(other, text)
        # Priced on the summarising model's own row, by asking the transport
        # that made the call rather than re-deriving the figure here.
        self._summary = what_the_summariser_cost(other)
        return said

    def lattice(self) -> dict[str, str]:
        return {
            "model_call": "native",
            "tool_calls": "native",
            "parallel_tool_calls": "native",
            # `content` is text XOR calls; the assistant sentence rides in
            # `thought` instead. Semantics preserved, shape not native.
            "text_with_tool_calls": "emulated",
            "streaming": "emulated",
            "durable_resume": "unsupported",
        }

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        messages: list[LLMMessage] = []
        if system:
            messages.append(SystemMessage(content=system))
        for m in history:
            if m["role"] == "user":
                messages.append(UserMessage(content=m["content"], source="user"))
            elif m["role"] == "assistant":
                # Without this the conversation never grows an assistant turn,
                # so a history-driven model replays step 0 forever.
                messages.append(AssistantMessage(content=m["content"], source="agent"))
            elif m["role"] == "tool":
                # AutoGen models tool output as a user turn at this layer; PACT
                # marks it so the script still sees a stable conversation shape.
                messages.append(
                    UserMessage(content=f"[tool {m['name']}] {m['content']}", source="tool")
                )
        result = await self._client.create(messages)
        if isinstance(result.content, list):
            return (result.thought or ""), [
                ToolCall(name=c.name, args=json.loads(c.arguments or "{}"))
                for c in result.content
            ]
        return str(result.content), []
