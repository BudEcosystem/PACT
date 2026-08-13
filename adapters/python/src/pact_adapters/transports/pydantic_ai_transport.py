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
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition

from ..harness import ToolCall
from ..resolve import default_model, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, tokens_sent, what_the_summariser_cost
from ._summarise import summarise_with
from ._tool_choice import can_choose


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
            # The only `native` in this column, and `native` is the whole of the
            # difference it records. Every harness-driven target reaches a
            # `connect:` server through PACT's own client (`emulated` — see
            # `mock.py`); this is the one RUNTIME that has a client of its own,
            # so `mcp_bridge._live` builds a `pydantic_ai.mcp.MCPToolset` and
            # `pydantic_ai_interop.build_agent` hands it to a real `Agent`. The
            # call leaves the process on the framework's own legs.
            #
            # NOT conditioned on whether `pydantic_ai.mcp` imports on THIS
            # machine. `mcp_bridge.why_no_mcp` answers that per run, with a line
            # to type and the tools deferred rather than dropped; a lattice that
            # changed with the installed extras would make the published matrix
            # a property of one laptop instead of a property of the runtime.
            "connected_tools": "native",
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

    def apply_settings(self, settings: dict[str, Any]) -> tuple[str, ...]:
        """Take the author's `settings:` block, and say what could not be taken.

        Pydantic AI is the one framework here whose own settings object names an
        analogue for all twelve schema fields — `pydantic_ai.settings
        .ModelSettings` carries `max_tokens`, `thinking`, `temperature`, `top_p`,
        `top_k`, `stop_sequences`, `seed`, `presence_penalty`,
        `frequency_penalty`, `tool_choice`, `parallel_tool_calls` and
        `service_tier`, and each concrete `Model` translates them into its
        provider's own spelling. So this is the transport with the least excuse
        for dropping any of it, and for a round it dropped all of it: the block
        loaded, validated, and came straight back on `RunResult.unmetered`.

        Two keys can still come back, and neither is a stub.

        `thinking:` because `Model.prepare_request` resolves it against the bound
        model's PROFILE and silently strips it when the profile does not think.
        Asking that same question here is what turns a `tier: core` field
        vanishing into a `tier: core` field reported. `_thinking_reaches` asks
        all THREE of the questions that method asks, including the third one
        this transport missed for a round: a profile with
        `thinking_always_enabled` discards `thinking: none` and thinks anyway.

        `service-tier:` because the schema types it as free text and this SDK
        types it as `Literal['auto', 'default', 'flex', 'priority']` — four
        words it can translate per provider, and nothing it can do with a fifth.
        `ModelSettings` is a `TypedDict`, so nothing would stop a fifth being
        posted; reporting it is the translate-or-nothing line.

        `tool-choice:` is answered here and again at every call, because the two
        questions are different ones. This says whether the SDK has a shape for
        the authored value, and it always has. Whether a PARTICULAR call can
        carry it depends on the tools THAT call offers, which nothing knows yet:
        `harness.run`'s closing call offers none on purpose and a stage may
        offer a subset. `_tool_choice.can_choose` decides that per call, and the
        transport sends nothing rather than an approximation when the answer is
        no — on this SDK sending it anyway does not degrade, it raises
        `UserError` out of `resolve_tool_choice` and takes the run with it.
        """
        self._settings = dict(settings)
        return tuple(
            k
            for k in settings
            if k not in _SETTINGS
            or (k == "thinking" and not _thinking_reaches(self._model, settings[k]))
            or (k == "service-tier" and str(settings[k]).strip() not in _SERVICE_TIERS)
        )

    def settings_for_request(self, offered: tuple[str, ...] = ()) -> ModelSettings:
        """The `ModelSettings` this transport is about to hand the SDK.

        Split out for the reason `ollama_transport.payload_for` was: a test that
        asserts a mapping table and a return value is true of a transport that
        then drops every setting on the floor. Here the stronger assertion is
        available and is the one the tests make — Pydantic AI hands the model
        function an `AgentInfo` carrying the `model_settings` and
        `model_request_parameters` its own `prepare_request` produced, so what
        reached the SDK can be read on the far side of it.

        `offered` is the tool names THIS call carries, and it is a parameter
        rather than a field because it changes call by call. Every provider model
        in this SDK runs `models._tool_choice.resolve_tool_choice`, which raises
        `UserError` on `required` with no function tools and on a name it cannot
        find — so a `tool-choice:` this call cannot carry is left out of the
        request instead. `models/function.py` is the one model that does NOT call
        it, which is why the tests for this drive a model that does.
        """
        said = getattr(self, "_settings", {})
        wire: ModelSettings = {}
        for key, value in said.items():
            if key not in _SETTINGS:
                continue
            if key == "thinking" and not _thinking_reaches(self._model, value):
                continue
            if key == "service-tier" and str(value).strip() not in _SERVICE_TIERS:
                continue
            if key == "tool-choice" and not can_choose(value, offered):
                continue
            wire[_SETTINGS[key]] = _translated(key, value)  # type: ignore[literal-required]
        return wire

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        self._history = history
        self._system = system
        response = await direct.model_request(
            self._model,
            _to_messages(system, history),
            # The author's `settings:` block, in this SDK's own shape. The
            # per-REQUEST surface rather than `FunctionModel(settings=...)`,
            # because a `settings:` block belongs to the run and the model object
            # is built once in `__init__`. The tool names go with it because
            # `tool_choice` is a statement ABOUT them: this call's `function_tools`
            # is what `resolve_tool_choice` validates it against, and the harness
            # makes calls whose list is empty or narrowed.
            model_settings=self.settings_for_request(
                tuple(str(t["name"]) for t in tools)
            ),
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


#: The author's key, and this SDK's. One mapping per transport, which is what the
#: `settings` group's own header makes possible — *"every key here works on every
#: provider"* — and why the group is closed rather than open.
#:
#: All twelve, uniquely among the transports here, because `ModelSettings` is
#: itself a cross-provider vocabulary: Pydantic AI has already done per-provider
#: translation one layer down, so PACT's job on this target is a rename plus the
#: two value translations `_translated` makes.
_SETTINGS: dict[str, str] = {
    "max-tokens": "max_tokens",
    "thinking": "thinking",
    "temperature": "temperature",
    "top-p": "top_p",
    "top-k": "top_k",
    "stop-sequences": "stop_sequences",
    "seed": "seed",
    "presence-penalty": "presence_penalty",
    "frequency-penalty": "frequency_penalty",
    "tool-choice": "tool_choice",
    "parallel-tool-calls": "parallel_tool_calls",
    "service-tier": "service_tier",
}

#: `pydantic_ai.settings.ServiceTier`, which is a closed set where the schema's
#: `service-tier:` is free text. A word outside it has no translation on any
#: provider and is reported rather than posted.
_SERVICE_TIERS = ("auto", "default", "flex", "priority")

#: The three `tool-choice:` words this SDK also uses. The fourth value its help
#: names — *"one tool name"* — is not a word at all here.
_PLAIN_CHOICES = ("auto", "required", "none")


def _thinking_reaches(model: Any, value: Any) -> bool:
    """Whether this authored `thinking:` would reach the bound model.

    The same THREE questions `Model.prepare_request` asks before it moves the key
    onto `ModelRequestParameters` and out of `ModelSettings` (models/__init__.py,
    pydantic_ai_slim 2.21.0)::

        if supports_thinking or thinking_always_enabled:
            if not (thinking_value is False and thinking_always_enabled):
                params = replace(params, thinking=thinking_value)

    Asked here so the transport reports the key in exactly the cases the SDK
    would drop it — a provider fact, read from the SDK, rather than a permanent
    excuse written into a table.

    The third question is why this takes the VALUE and not only the model, and
    it was missed for a round. `thinking: none` is PACT's word for *do not*, it
    translates to `False` here, and on a profile with `thinking_always_enabled`
    the SDK discards exactly that combination and thinks anyway. Reporting the
    key honoured there tells the author a `tier: core` line held when the SDK
    provably threw it away.
    """
    profile = getattr(model, "profile", None)
    if profile is None:
        return False
    supports = bool(profile.get("supports_thinking", False))
    always = bool(profile.get("thinking_always_enabled", False))
    if not (supports or always):
        return False
    return not (_translated("thinking", value) is False and always)


def _translated(key: str, value: Any) -> Any:
    """One authored value in this SDK's shape.

    Three keys need it.

    `tool-choice:`'s help says *"auto, required, none, or one tool name"*. The
    three words are `ToolChoiceScalar` here and go through unchanged; a NAME is a
    `list[str]`, which `models._tool_choice.resolve_tool_choice` turns into
    `('required', {name})` and each provider then writes in its own shape —
    `{"type": "function", "function": {"name": ...}}` on an OpenAI-compatible
    endpoint, `{"type": "tool", "name": ...}` on Anthropic's. A bare `"payments"`
    is not in `ToolChoice` at all; passed through it would be a setting in a shape
    the provider ignores, which is worse than one reported unhonoured because
    nothing says it did not happen.

    `thinking:`'s `none` is `False` here rather than a fifth string — Pydantic
    AI's `ThinkingLevel` is `bool | Literal['minimal', 'low', 'medium', 'high',
    'xhigh']`, so PACT's four words are three literals and a boolean.

    `stop-sequences:` because the schema says "list of text" and the SDK says
    `list[str]`; a scalar an author wrote as one line is a sequence of CHARACTERS
    to anything that iterates it, which is the quietest possible way to send the
    wrong thing.
    """
    if key == "tool-choice":
        said = str(value).strip()
        return said if said in _PLAIN_CHOICES else [said]
    if key == "thinking":
        said = str(value).strip()
        return False if said == "none" else said
    if key == "stop-sequences":
        return [str(value)] if isinstance(value, str) else [str(v) for v in value]
    return value


def _from_response(response: ModelResponse) -> tuple[str, list[ToolCall]]:
    text = "".join(p.content for p in response.parts if isinstance(p, TextPart))
    calls = [
        ToolCall(name=p.tool_name, args=p.args if isinstance(p.args, dict) else {})
        for p in response.parts
        if isinstance(p, ToolCallPart)
    ]
    return text, calls
