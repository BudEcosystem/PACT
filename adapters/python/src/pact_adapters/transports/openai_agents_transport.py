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
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.tool import FunctionTool
from agents.usage import Usage
from openai.types.shared import Reasoning
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
from ._tool_choice import can_choose


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
        #: The author's `settings:` block, empty until `apply_settings` is given
        #: one. Initialised HERE rather than only there because `harness.run`
        #: calls `apply_settings` only `if spec.settings:` — a transport reused
        #: across a spec with settings and then a spec without would otherwise
        #: carry the first spec's block into the second's request. The harness
        #: builds one transport per run, so this is a guard rather than a fix,
        #: and it is written down so the next reader does not have to re-derive
        #: that the `if` is what makes the reuse safe.
        self._settings: dict[str, Any] = {}
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
            # The seam is `Model.get_response` — one model call. The Agents SDK
            # does have hosted-tool shapes and this transport binds none of
            # them: it takes the LOWEST seam so PACT owns the loop. So a
            # `connect:` line reaches its server through PACT's own client above
            # the framework, which is what `emulated` means; `mock.py` states
            # the rule once for every target that shares it.
            "connected_tools": "emulated",
        }

    def apply_settings(self, settings: dict[str, Any]) -> tuple[str, ...]:
        """Take the author's `settings:` block, and say what could not be taken.

        The whole group crossed no adapter boundary for a round — twelve fields,
        two of them `tier: core` — so `max-tokens: 5` and `thinking: high` loaded
        cleanly, validated, and reached no model. On this transport every one of
        the twelve came back on `RunResult.unmetered`: there was no
        `apply_settings`, and `model_call` handed the SDK a literal
        `model_settings=None`.

        SIX are still returned as left over, and they are left over for two
        different reasons — which is the part this method got wrong for a round
        and is the reason it is worth reading twice.

        FOUR have no field at all. `ModelSettings` is the whole vocabulary a
        `Model` implementation is guaranteed to understand, and it has none for
        `top-k`, `stop-sequences`, `seed` or `service-tier` — nor does either
        shipped `Model` put any of the four into the request it builds. The only
        door left is `extra_args`, an untyped dict spread straight into whichever
        provider call the host's `ModelProvider` chose: right on OpenAI's own
        client, ignored or a `TypeError` on anything else. A setting in a shape
        the provider ignores is worse than one reported unhonoured, because
        nothing says it did not happen.

        TWO have a field and are reported anyway: `presence-penalty` and
        `frequency-penalty`. `ModelSettings` names both, so
        `settings_for` still fills them in — that is the SDK's own typed field
        and not an approximation, and a host that bound the Chat Completions
        surface really does get them (`models/openai_chatcompletions.py` puts
        `frequency_penalty` and `presence_penalty` into its `create_kwargs`).
        But the SDK's DEFAULT surface is the other one: `models/_openai_shared
        .py` declares `_use_responses_by_default = True` and `OpenAIProvider`
        picks `OpenAIResponsesModel` off it, and that model's create kwargs —
        temperature, top_p, truncation, max_output_tokens, tool_choice,
        parallel_tool_calls, reasoning, store, metadata, context_management —
        contain neither penalty. Which surface a run gets is the HOST's choice
        and is not knowable here, so the honest report is the one that
        under-claims: both keys are named on `RunResult.unmetered`, and an author
        on the Chat Completions path is told two settings may not have landed
        when they did. The opposite error is the one this whole round exists to
        close — a key reported honoured that the default surface silently drops.

        So `RunResult.unmetered` is a statement about what this transport can
        PROMISE was honoured, not a statement about what it sent. Where those two
        differ the promise is the weaker of the pair, deliberately.

        `tool-choice` is answered here and again at every call, for the reason
        `pydantic_ai_transport.apply_settings` states in full: this says the SDK
        has a shape for the authored value, and it always has; whether a
        PARTICULAR call can carry it depends on the tools THAT call offers, which
        nothing knows yet. `_tool_choice.can_choose` decides that in
        `settings_for`.
        """
        self._settings = dict(settings)
        # The second clause is deliberately redundant with the first, because
        # `_ONLY_ON_CHAT_COMPLETIONS` is disjoint from `_FIELDS` today. It is
        # written anyway so that moving a key between those two lists changes
        # what is SENT without silently changing what is PROMISED — the two
        # questions this method exists to keep apart.
        return tuple(
            k
            for k in settings
            if (k not in _FIELDS and k not in _TRANSLATED) or k in _ONLY_ON_CHAT_COMPLETIONS
        )

    def settings_for(self, offered: tuple[str, ...] = ()) -> ModelSettings:
        """The author's `settings:` block as the SDK's own dataclass.

        Split out of `model_call` so the OBJECT can be asserted rather than the
        mapping table. The register records why in its own words: *"A test of
        mine failed its own mutation here. The first version asserted `_WIRE`
        membership and what `apply_settings` returned — both true of a transport
        that then drops every setting on the floor."*

        Unwritten keys are left at `None`, which is what every field on
        `ModelSettings` defaults to and what both shipped `Model`s read as
        "omit"; filling them in with a guess would make PACT's silence look like
        an author's instruction.

        `offered` is the tool names THIS call carries, and it is a parameter
        rather than a field because it changes call by call: `harness.run` closes
        every ceiling-terminated run with `model_call(instructions, history, [])`
        and a stage may narrow the set. `_tool_choice.can_choose` decides whether
        the authored choice is one this call can carry, and nothing goes in its
        place when it is not — on this SDK `_validate_named_function_tool_choice`
        RAISES on a name the call did not offer, so an approximation here would
        not merely be unhonoured, it would take the run down.

        The two penalties are set here and reported left over by
        `apply_settings`; that method says why, and the short form is that the
        field is real and the DEFAULT surface drops it.
        """
        settings = self._settings
        made = {
            wire: v
            for k, v in settings.items()
            for wire in (_ALL_FIELDS.get(k),)
            if wire is not None
            and (k != "tool-choice" or can_choose(v, offered))
        }
        if "thinking" in settings:
            # The one key that needs an object rather than a copy. The SDK
            # carries it as `openai.types.shared.Reasoning`, whose `effort`
            # literal contains all four of PACT's `thinking:` words, so the value
            # itself goes through unchanged inside the shape the field is typed
            # for. `openai_chatcompletions.py` reads `.effort` back off it for
            # the Chat Completions surface, so the one field serves both.
            made["reasoning"] = Reasoning(effort=str(settings["thinking"]))
        return ModelSettings(**made)

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        self._model._history = history
        response = await self._model.get_response(
            system_instructions=system, input=_to_input(history),
            model_settings=self.settings_for(tuple(str(t["name"]) for t in tools)),
            # The spec's tools go down with the settings, because a
            # `tool_choice` naming a tool the model was never given is a setting
            # about nothing — and worse than nothing on this SDK, whose
            # `_validate_named_function_tool_choice` raises on it.
            tools=[_tool(t) for t in tools],
            output_schema=None, handoffs=[],
            # `ModelTracing.DISABLED`, not `None`. It was `None` for a round, and
            # nothing noticed because the `Model` on the other side is PACT's own
            # and takes `*args, **kwargs` — but `get_response` types this
            # parameter as the enum and `openai_responses.py` calls
            # `tracing.is_disabled()` on it, so a real `Model` would have raised
            # `AttributeError`. A seam only means something if the call crossing
            # it is one the interface would accept.
            tracing=ModelTracing.DISABLED,
            # The three keyword-only arguments the interface requires and this
            # has nothing to say about. Passed explicitly for the same reason:
            # they have no defaults on `Model.get_response`, so omitting them
            # made this a call only a permissive stand-in could take.
            previous_response_id=None, conversation_id=None, prompt=None,
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


#: The author's key, and the field it becomes on `agents.model_settings.
#: ModelSettings`. One mapping per transport, which is what the `settings`
#: group's own header makes possible — *"every key here works on every
#: provider"* — and why the group is closed rather than open.
#:
#: This is the PROMISED half. `_ONLY_ON_CHAT_COMPLETIONS` below carries two more
#: that are copied onto the object and reported unhonoured anyway, and
#: `_ALL_FIELDS` is what `settings_for` actually reads — so a reader adding a row
#: here should first ask which of the three lists it belongs in.
#:
#: `top-k`, `stop-sequences`, `seed` and `service-tier` are deliberately absent:
#: `ModelSettings` has no field for any of them, and neither
#: `agents/models/openai_responses.py` nor `agents/models/openai_chatcompletions
#: .py` puts one into the request it builds. Only the untyped `extra_args`
#: passthrough could carry them, and that goes to whichever provider the host's
#: `ModelProvider` bound.
#:
#: `tool-choice` is the inversion worth reading twice, and it is why it is HERE
#: rather than in `_TRANSLATED`. The field is typed
#: `Literal["auto", "required", "none"] | str | MCPToolChoice`, and
#: `Converter.convert_tool_choice` is the SDK's own code for turning the bare
#: name into `{"type": "function", "name": ...}`. Anticipating that here would
#: put a dict where a string is typed — the opposite of `ollama_transport.py`,
#: where the bare name reaches the wire and silently means nothing.
#:
#: One residue is recorded rather than papered over: that same converter reads a
#: handful of names as HOSTED tools before it reaches the function branch —
#: `web_search`, `file_search`, `computer`, `mcp`, `code_interpreter`,
#: `image_generation`, `programmatic_tool_calling`. An author whose own tool is
#: called one of those gets the SDK's builtin instead of their action, and
#: nothing says so. There is no other way to name a function through this field,
#: so there is nothing to translate it INTO; the honest fix is a check at
#: authoring time, not a guess here.
_FIELDS: dict[str, str] = {
    "max-tokens": "max_tokens",
    "temperature": "temperature",
    "top-p": "top_p",
    "tool-choice": "tool_choice",
    "parallel-tool-calls": "parallel_tool_calls",
}


#: The keys with a real field on `ModelSettings` that the SDK's DEFAULT model
#: surface never forwards. Set on the object like any other — the field is the
#: SDK's own and the value is not an approximation — and reported on
#: `RunResult.unmetered` anyway.
#:
#: `models/_openai_shared.py` declares `_use_responses_by_default = True` and
#: `OpenAIProvider` picks `OpenAIResponsesModel` off it, so the Responses surface
#: is the default; its `create_kwargs` are temperature, top_p, truncation,
#: max_output_tokens, tool_choice, parallel_tool_calls, reasoning, store,
#: metadata and context_management, and contain neither penalty.
#: `models/openai_chatcompletions.py` does forward both. Which surface a run gets
#: is the HOST's choice — it binds the `ModelProvider` — and is not knowable
#: here, so the promise is the weaker of the pair.
#:
#: This is the ONE place in this file where "sent" and "reported honoured" come
#: apart, and it is separated from `_FIELDS` rather than folded into it so the
#: distinction has a name a reader can follow.
#: `AutoGenTransport.apply_settings` reaches the same conclusion the other way
#: about `reasoning_effort`, where it declines to send at all; the difference is
#: that this field is typed and that one is a string in an untyped bag.
_ONLY_ON_CHAT_COMPLETIONS: dict[str, str] = {
    "presence-penalty": "presence_penalty",
    "frequency-penalty": "frequency_penalty",
}


#: Everything `settings_for` copies onto the object, promised or not. `_FIELDS`
#: alone would leave the two penalties off the request as well as off the
#: report, which would be a second wrong answer rather than a cautious one.
_ALL_FIELDS: dict[str, str] = {**_FIELDS, **_ONLY_ON_CHAT_COMPLETIONS}

#: The keys `settings_for` builds an object for rather than copying a value.
#: Named so `apply_settings` can answer without repeating the list.
_TRANSLATED = ("thinking",)


def _tool(tool: dict[str, Any]) -> FunctionTool:
    """One PACT tool as the SDK's own `FunctionTool`.

    `on_invoke_tool` refuses on purpose: PACT owns the loop and the harness runs
    the tool, so a `Model` that tried to invoke this would be doing something no
    PACT run asks for. It should say so loudly rather than return an empty
    result. `strict_json_schema` is off because the author's `parameters:` are
    descriptions rather than a schema, and claiming strictness for them would be
    a promise this transport cannot keep.
    """

    async def _refuse(_context: Any, _arguments: str) -> Any:  # pragma: no cover
        raise NotImplementedError("PACT executes this tool, not the model")

    return FunctionTool(
        name=tool["name"],
        description=tool.get("description", ""),
        params_json_schema={
            "type": "object",
            "properties": {
                a: {"type": "string", "description": s}
                for a, s in (tool.get("parameters") or {}).items()
            },
        },
        on_invoke_tool=_refuse,
        strict_json_schema=False,
    )


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
