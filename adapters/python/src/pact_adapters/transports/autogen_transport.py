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
from autogen_core.tools import ToolSchema

from ..harness import ToolCall
from ..resolve import default_model, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, what_the_summariser_cost
from ._summarise import summarise_with
from ._tool_choice import can_choose


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
            # `ChatCompletionClient.create` is a MODEL call and this transport
            # does not even choose the client behind it (`runtime = ""`), so a
            # `connect:` line becomes no connection of AUTOGEN's. It reaches the
            # server through PACT's own client above the framework, which is
            # what `emulated` means here; `mock.py` states the rule once.
            "connected_tools": "emulated",
        }

    def apply_settings(self, settings: dict[str, Any]) -> tuple[str, ...]:
        """Take the author's `settings:` block, and say what could not be taken.

        The whole group crossed no adapter boundary for a round — twelve fields,
        two of them `tier: core` — so `max-tokens: 5` and `thinking: high` loaded
        cleanly, validated, and reached no model. On this transport every one of
        the twelve came back on `RunResult.unmetered`, because it had no
        `apply_settings` at all and the harness reports the whole block when a
        transport cannot take it.

        Four are still returned as left over, and none of them is a stub.
        AutoGen's `create` has exactly two doors for a generation parameter — its
        own `tool_choice` keyword and `extra_create_args`, *"Extra arguments to
        pass to the underlying client"* — and the second one's vocabulary is that
        CLIENT's, which this transport does not choose (`runtime = ""`). So the
        question a row in `_CREATE_ARGS` answers is not *"is this an OpenAI
        chat-completions parameter"* — being one only gets it past the client's
        own validator — but *"will the endpoint behind an unknown client DO
        something with it"*. `_CREATE_ARGS` is therefore the intersection over
        the clients a host might bind, and the four below fall outside it:

        * `top-k` — not in the OpenAI chat-completions parameter set at all.
          AutoGen's Ollama client nests it inside an `options` object and its
          Anthropic client takes it top-level, so one spelling would be right on
          one client and silently nothing on another.
        * `thinking` and `parallel-tool-calls` — `reasoning_effort` and
          `parallel_tool_calls` ARE names in that parameter set, so the client's
          validator accepts both and the openai package will post them. Being
          posted is not being honoured: `ollama_transport.py`, the one transport
          here that names its endpoint, records that the OpenAI-compatible
          `/v1/chat/completions` surface *"takes neither"*, and that endpoint is
          what the distribution's default locally-served model answers on. A
          transport that does not even know which client it has cannot claim more
          than the one that does. Losing `thinking` hurts most — it is `tier:
          core` — and it is reported for exactly that reason.
        * `service-tier` — an OpenAI-cloud routing word. Nothing serving weights
          locally routes on it, and no other provider has the concept.

        The two tables are coupled deliberately, and they differ in BOTH
        directions, which is worth saying plainly so a future reader does not
        read them as agreeing: `ollama_transport._WIRE` maps `top-k` and this
        does not, because that transport speaks to a named endpoint and can know;
        this refuses `thinking`, `parallel-tool-calls` and `service-tier` on that
        transport's own finding about the same endpoint. If that finding is ever
        revised against a measured server, both tables move together.

        `tool-choice` is answered here and again at every call, for the reason
        `pydantic_ai_transport.apply_settings` states in full: this says the SDK
        has a shape for the authored value, and it always has; whether a
        PARTICULAR call can carry it depends on the tools THAT call offers, which
        nothing knows yet. `_tool_choice.can_choose` decides that in
        `create_args_for`.
        """
        self._settings = dict(settings)
        return tuple(
            k for k in settings if k not in _CREATE_ARGS and k != "tool-choice"
        )

    def create_args_for(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """The exact keyword arguments this is about to hand `create`.

        Split out of `model_call` so the CALL can be asserted rather than the
        mapping table. The register records why in its own words: *"A test of
        mine failed its own mutation here. The first version asserted `_WIRE`
        membership and what `apply_settings` returned — both true of a transport
        that then drops every setting on the floor."*

        Keys that carry nothing are left ABSENT rather than passed as `None`:
        `create`'s own defaults are `tools=[]` and `tool_choice="auto"`, and
        handing those back explicitly would overwrite a host's own arrangement
        with PACT's silence.
        """
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

        settings = self._settings
        args: dict[str, Any] = {"messages": messages}
        extra = {
            _CREATE_ARGS[k]: v for k, v in settings.items() if k in _CREATE_ARGS
        }
        if extra:
            args["extra_create_args"] = extra
        # The tools go with the call whenever the spec has any — a `tool_choice`
        # naming a tool the client was never given is a setting about nothing,
        # and `ToolSchema` is a plain TypedDict, so this is AutoGen's own shape
        # rather than a dict that resembles it.
        if tools:
            args["tools"] = [_schema_of(t) for t in tools]
        # And only a choice THIS call can carry. `_tool_choice.can_choose` says
        # whether it can; sending it anyway is not merely unhonoured here.
        # autogen-ext's `_openai_client.py` guards the whole translation with
        # `if len(converted_tools) > 0:`, so on a tool-less call the parameter is
        # dropped one layer down whatever PACT passes — and before that it raises
        # `ValueError("tool_choice specified but no tools provided")` when the
        # value is a `Tool`. A named choice on a tool-less call would therefore
        # take the run down, and `required` would vanish silently.
        if "tool-choice" in settings and can_choose(
            settings["tool-choice"], tuple(str(t["name"]) for t in tools)
        ):
            args["tool_choice"] = _tool_choice(settings["tool-choice"], tools)
        return args

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        result = await self._client.create(**self.create_args_for(system, history, tools))
        if isinstance(result.content, list):
            return (result.thought or ""), [
                ToolCall(name=c.name, args=json.loads(c.arguments or "{}"))
                for c in result.content
            ]
        return str(result.content), []


#: The author's key, and the name it travels under inside `extra_create_args`.
#: One mapping per transport, which is what the `settings` group's own header
#: makes possible — *"every key here works on every provider"* — and why the
#: group is closed rather than open.
#:
#: The spelling is the OpenAI chat-completions one. `extra_create_args` is
#: documented as *"Extra arguments to pass to the underlying client"*, so its
#: vocabulary belongs to whichever `ChatCompletionClient` the host bound; this
#: transport declares `runtime = ""` because it does not choose one, and the
#: distribution's default model is locally served over an OpenAI-compatible
#: surface. Every name here was checked against
#: `openai.types.chat.completion_create_params.CompletionCreateParamsBase`.
#:
#: Being in that set is necessary and NOT sufficient, which is the whole of why
#: this table is shorter than it could be. `reasoning_effort`,
#: `parallel_tool_calls` and `service_tier` are all in it — an autogen-ext client
#: would validate them and the openai package would post them — and they are
#: absent here anyway, because `ollama_transport._WIRE`, written by the one
#: transport in this tree that NAMES its endpoint, records that the
#: OpenAI-compatible `/v1/chat/completions` surface honours the first two not at
#: all, and the third is an OpenAI-cloud routing word no locally served model
#: routes on. This table is the intersection over the clients a host might bind;
#: `_WIRE` is one measured client, so it maps `top-k`, which is not in the OpenAI
#: parameter set at all and which this therefore cannot send. The two differ in
#: both directions on purpose and are coupled: revise one against a measured
#: server and the other moves with it. `AutoGenTransport.apply_settings` states
#: the argument in full.
#:
#: `tool-choice` is absent for an unrelated reason — it has a keyword of its own
#: on `create`, so sending it through this door as well would set it twice.
_CREATE_ARGS: dict[str, str] = {
    "max-tokens": "max_tokens",
    "temperature": "temperature",
    "top-p": "top_p",
    "stop-sequences": "stop",
    "seed": "seed",
    "presence-penalty": "presence_penalty",
    "frequency-penalty": "frequency_penalty",
}


#: The three `tool-choice:` words `create`'s own signature spells out. Anthropic
#: says `any` where this says `required`, which is exactly the per-target
#: difference one mapping table each exists to absorb: the author writes one
#: word and it works everywhere.
_PLAIN_CHOICES = ("auto", "required", "none")


class _NamedTool:
    """The one tool a `tool-choice:` NAME points at, as AutoGen's `Tool`.

    `create`'s `tool_choice` is typed `Tool | Literal["auto", "required", "none"]`
    and its docstring says *"A single Tool object to force the model to use"*, so
    a bare `"payments"` is the wrong type. A client reads the name back off
    `schema["name"]` to build the provider's own object, which is the whole of
    what this has to carry — but `autogen_core.tools.Tool` is a
    `@runtime_checkable` Protocol, so every member has to be present or an
    `isinstance` check inside the client fails and the choice is dropped.

    The execution half is deliberately not implemented: PACT owns the loop and
    the harness runs the tool, so a model client that tried to invoke this would
    be doing something no PACT run asks for, and it should say so loudly rather
    than return an empty result.
    """

    def __init__(self, schema: ToolSchema) -> None:
        self._schema = schema

    @property
    def name(self) -> str:
        return self._schema["name"]

    @property
    def description(self) -> str:
        return self._schema.get("description", "")

    @property
    def schema(self) -> ToolSchema:
        return self._schema

    def args_type(self) -> Any:  # pragma: no cover - the loop is PACT's
        raise NotImplementedError("PACT executes this tool, not the model client")

    def return_type(self) -> Any:  # pragma: no cover - the loop is PACT's
        raise NotImplementedError("PACT executes this tool, not the model client")

    def state_type(self) -> Any:
        return None

    def return_value_as_string(self, value: Any) -> str:
        return str(value)

    async def run_json(  # pragma: no cover - the loop is PACT's
        self, args: Any, cancellation_token: CancellationToken, call_id: str | None = None
    ) -> Any:
        raise NotImplementedError("PACT executes this tool, not the model client")

    async def save_state_json(self) -> dict[str, Any]:
        return {}

    async def load_state_json(self, state: Any) -> None:
        return None


def _schema_of(tool: dict[str, Any]) -> ToolSchema:
    """One PACT tool in AutoGen's own `ToolSchema` shape.

    A TypedDict, so this is the SDK's type and not a dict that resembles it —
    `create` takes `Sequence[Tool | ToolSchema]` precisely so a caller that
    already has a schema does not have to wrap a callable it does not have.
    """
    return ToolSchema(
        name=tool["name"],
        description=tool.get("description", ""),
        parameters={
            "type": "object",
            "properties": {
                a: {"type": "string", "description": s}
                for a, s in (tool.get("parameters") or {}).items()
            },
        },
    )


def _tool_choice(value: Any, tools: list[dict[str, Any]]) -> Any:
    """One authored `tool-choice:` in the shape this interface's type demands.

    Its help says *"auto, required, none, or one tool name"*. The three words are
    literals of the parameter's own type and go through unchanged; a NAME is a
    `Tool`, and passing the bare string instead is a type error rather than the
    OpenAI-compatible endpoint's silent no-op — a better failure, and still not
    one to ship. A name that matches no declared tool still becomes a `Tool`
    carrying that name, so the client rejects it by name instead of PACT quietly
    deciding the author meant something else.
    """
    said = str(value).strip()
    if said in _PLAIN_CHOICES:
        return said
    for t in tools:
        if t["name"] == said:
            return _NamedTool(_schema_of(t))
    return _NamedTool(ToolSchema(name=said, description=""))
