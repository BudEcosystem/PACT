"""LangGraph as a transport (harness lowering).

The seam is `langgraph.func.entrypoint` + `task` — the functional API, not
`StateGraph`. The source audit found this route "implementable and actually
*better* than native", because `StateGraph` would impose its own reducer-based
state model on a loop PACT already owns.

Crucially this goes *through* LangGraph's execution machinery rather than around
it: each model call is a `@task` inside a checkpointed `@entrypoint`, so the
durability and replay semantics are real. A transport that imported LangGraph
and then ignored it would prove nothing.
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.func import entrypoint, task

from ..harness import ToolCall
from ..resolve import default_model, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, tokens_sent, what_the_summariser_cost
from ._summarise import summarise_with
from ._tool_choice import can_choose
# LangGraph's model layer IS `langchain_core`: a `@task` that calls a model calls
# a `BaseChatModel`. The scripted one the LangChain transport already defines is
# that seam, so it is imported rather than written a second time — two copies
# would drift, and the whole point of this transport speaking `langchain_core`'s
# vocabulary is that it is the SAME vocabulary.
from .langchain_transport import _ScriptedChatModel


class LangGraphTransport:
    """Drives one model call as a checkpointed LangGraph task."""

    name = "langgraph"

    #: Which runtime this transport is, in the catalogue's own `served-by:`
    #: vocabulary. Empty on purpose: this is a FRAMEWORK adapter, not a provider
    #: one — a LangGraph task calls whatever model the graph carries —
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
        self._saver = InMemorySaver()
        #: The model the `@task` calls. LangGraph orchestrates; it does not talk
        #: to providers, and the layer it orchestrates model calls THROUGH is
        #: `langchain_core`. Without this the transport had no model object at
        #: all, which is why the settings it put in the checkpointed payload were
        #: read by nothing: a key written, validated, reported honoured and
        #: delivered nowhere is the same defect this round exists to close, moved
        #: one level in.
        self._model = _ScriptedChatModel(script=script)
        #: What the last call carried, in and out. Counted inside the `@task`
        #: and returned through the checkpointed payload rather than kept beside
        #: it — a graph that is replayed replays the figure with everything
        #: else, which is what `durable_resume: native` in the lattice below
        #: promises. Absent for a round: this was one of the three shipped
        #: transports the metering missed, so both money ceilings went out on
        #: `RunResult.unmetered` for every run of it and the same document
        #: terminated at `step-limit` here and `token-limit` on Anthropic.
        self._counted: tuple[int, int] = (0, 0)
        #: What the last summarising call cost, priced on the SUMMARISER's row.
        #: `None` means nobody could price it.
        self._summary: "tuple[int, float] | None" = (0, 0.0)
        #: Whether the catalogue publishes a price for the bound model. See
        #: `AnthropicTransport.__init__` for why this is not the same question as
        #: whether `usage()` exists.
        self.prices_money = can_price(self.model, self.workspace)

        @task
        def _call(payload: dict[str, Any]) -> dict[str, Any]:
            return self._answer(payload)

        @entrypoint(checkpointer=self._saver)
        def _run(payload: dict[str, Any]) -> dict[str, Any]:
            return _call(payload).result()

        self._graph = _run

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The model call, as the `@task` runs it.

        A method rather than a closure body so it can be overridden — this is the
        point at which the model is asked, so it is the point at which a test
        asserts what reached it. `pydantic_ai_transport._respond` is the same
        shape for the same reason.

        `payload["settings"]` is what `apply_settings` could take, already in
        `langchain_core`'s spelling, and this is where it is CONSUMED. For a
        round it was not: the payload carried the key and nothing in the transport
        read it, because the transport called `Script.next_turn` directly and
        held no model object at all. So four keys were taken off
        `RunResult.unmetered` — the author told they were honoured — by a run
        that dropped every one of them. `bind`/`bind_tools` are LangChain's own
        way of attaching them and `_generate` is where they arrive, which is the
        same delivery path the LangChain transport uses and the same one a real
        `ChatOpenAI` would take.

        The token counts stay where they were, taken over the payload rather than
        off the message. This is the transport whose lattice claims
        `durable_resume: native`: the figure belongs to the checkpointed task
        result, so it is derived from what the checkpoint holds and a replayed
        graph replays it without re-deriving it from a call that did not happen
        again.
        """
        system = str(payload.get("system") or "")
        history = payload["history"]
        model = _bound_for_the_task(
            self._model, payload.get("settings") or {}, payload.get("tools") or []
        )
        msg = model.invoke(_messages(system, history))
        text = str(msg.content or "")
        calls = [
            {"name": c["name"], "args": dict(c.get("args") or {})}
            for c in (getattr(msg, "tool_calls", None) or [])
        ]
        return {
            "text": text,
            "calls": calls,
            # The system prompt counts with the history because the provider
            # bills it, and a `loop:` that swaps a long instruction in per
            # stage is a cost the author can act on.
            "in": tokens_sent(system, history),
            "out": tokens_in(
                text + "".join(f"{c['name']}{c['args']}" for c in calls)
            ),
        }

    def usage(self) -> tuple[int, "float | None"]:
        """What the last call carried, and what the catalogue says it cost.

        Counted inside the checkpointed task and read back off its result, so a
        replayed graph reports the same figure. The fullest statement of why the
        price comes from the catalogue rather than from here is on
        `AnthropicTransport.usage`.
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

        Here the second instance is a second checkpointed graph with a
        checkpointer of its own, which is the right shape rather than an
        accident: summarising is not a step of the run being summarised, so it
        must not land in the run's own history of what happened.

        Synchronous for the reason `ollama_transport.py` gives; `_summarise.py`
        says how that is honoured over an async-only seam.
        """
        other = LangGraphTransport(self.script, model=model, workspace=self.workspace)
        said = summarise_with(other, text)
        # Priced on the summarising model's own row, by asking the transport that
        # made the call rather than re-deriving the figure here.
        self._summary = what_the_summariser_cost(other)
        return said

    def lattice(self) -> dict[str, str]:
        # `durable_resume` is `native` here and `unsupported` on Pydantic AI.
        # That asymmetry is the point of publishing a lattice: a spec that needs
        # kill-and-resume can be told which targets can carry it, before it runs.
        return {
            "model_call": "native",
            "tool_calls": "emulated",
            "text_with_tool_calls": "native",
            "parallel_tool_calls": "emulated",
            "streaming": "emulated",
            "durable_resume": "native",
            # What a `@task` binds is a `BaseChatModel` — a model layer — so no
            # `connect:` line becomes a client of LANGGRAPH's. It reaches the
            # server all the same, through PACT's own client above the
            # framework, which is what `emulated` means here; `mock.py` states
            # the rule once for every target that shares it.
            "connected_tools": "emulated",
        }

    def apply_settings(self, settings: dict[str, Any]) -> tuple[str, ...]:
        """Take the author's `settings:` block, and say what could not be taken.

        LangGraph has NO generation parameters. `@entrypoint` and `@task` take a
        payload and hand it to the function inside — there is no `ModelSettings`
        here as there is on Pydantic AI and no `bind()` as there is on LangChain.
        What LangGraph has is a model layer, and that layer is `langchain_core`:
        a `@task` that calls a model calls a `BaseChatModel`, and `_answer` calls
        one. So the vocabulary this transport can honestly speak is that one, and
        it is the same four keys for the same checked reasons
        `langchain_transport.apply_settings` sets out in full — `stop` is a
        parameter of `_generate`, `tool_choice` a parameter of `bind_tools`, and
        `temperature`/`max_tokens` `langchain_core`'s own SPELLING for two
        parameters an integration's `_generate(**kwargs)` is what actually
        delivers. That last one is the weakest of the three and the LangChain
        transport says at length why.

        The other eight are named on `RunResult.unmetered`. They have no name in
        `langchain_core`; they exist only as kwargs of a concrete integration,
        spelled differently in each, and none of those packages is installed here
        to check a guess against.

        What is LangGraph's OWN is where the four go: into the payload the
        `@entrypoint` is invoked with, so they are checkpointed with everything
        else on their way to the model. This is the transport whose lattice says
        `durable_resume: native`, and settings kept beside the graph rather than
        inside its payload would come back at resume time as whatever the host
        had configured — silently, on the one target whose whole claim is that a
        resume is faithful. Being checkpointed is not on its own a reason to
        report a key honoured, and for a round it was the only thing happening to
        them: the payload had a `settings` entry and nothing read it.
        """
        self._settings = dict(settings)
        return tuple(k for k in settings if k not in _CARRIED)

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        out = await self._graph.ainvoke(
            {
                "system": system,
                "history": history,
                "tools": tools,
                # Translated here rather than at the last hop, so what the
                # checkpoint holds is the model layer's own spelling and a resume
                # does not have to translate it again.
                "settings": _settings_for_the_task(getattr(self, "_settings", {})),
            },
            config,
        )
        self._counted = (int(out.get("in") or 0), int(out.get("out") or 0))
        return out["text"], [ToolCall(name=c["name"], args=c["args"]) for c in out["calls"]]


#: The author's key, and the name `langchain_core` gives it — LangGraph's model
#: layer, because LangGraph gives it none. Four rows, and the eight absent ones
#: are absent for the reason `apply_settings` above states: `langchain_core`
#: names them nowhere, and a guessed kwarg is a setting in a shape the provider
#: ignores with nothing saying it did not happen.
#:
#: `stop-sequences` and `tool-choice` are here as well as in `_KWARGS`' LangChain
#: equivalent because on this target every key travels the FIRST leg the same way
#: — through the checkpointed payload — so there is no distinction to keep at
#: this end of it. `_bound_for_the_task` makes it again at the other end, where
#: `stop` is a `bind()` kwarg and `tool_choice` has to go through `bind_tools`.
_CARRIED: dict[str, str] = {
    "max-tokens": "max_tokens",
    "temperature": "temperature",
    "stop-sequences": "stop",
    "tool-choice": "tool_choice",
}


def _settings_for_the_task(said: dict[str, Any]) -> dict[str, Any]:
    """The author's block in the model layer's shape, ready to be checkpointed.

    Two values need translating rather than copying.

    `tool-choice: required` is `any` in `BaseChatModel.bind_tools`' vocabulary —
    *"The tool to use. If 'any' then any tool can be used."* — which is the word
    Anthropic uses and not the word an OpenAI-compatible endpoint uses. One
    authored word working on every target is what the `settings` group's header
    promises. A NAME stays a bare string, because in LangChain the bare string IS
    the interface and each integration's `bind_tools` is what turns it into that
    provider's object.

    `stop-sequences` because the schema says "list of text" and `_generate`'s
    `stop` is `list[str] | None`; a scalar an author wrote as one line is a
    sequence of CHARACTERS to anything that iterates it, which is the quietest
    possible way to send the wrong thing.
    """
    out: dict[str, Any] = {}
    for key, value in said.items():
        if key not in _CARRIED:
            continue
        if key == "tool-choice":
            chose = str(value).strip()
            out["tool_choice"] = "any" if chose == "required" else chose
        elif key == "stop-sequences":
            out["stop"] = (
                [str(value)] if isinstance(value, str) else [str(v) for v in value]
            )
        else:
            out[_CARRIED[key]] = value
    return out


def _messages(system: str, history: list[dict[str, Any]]) -> list[BaseMessage]:
    """PACT history -> `langchain_core` messages, for the model the task calls.

    The same construction `langchain_transport.model_call` uses, because it is
    the same model layer. A tool result is a `ToolMessage` rather than user text:
    a framework that sees a tool result as a user turn counts turns differently,
    and the traces then diverge for a reason that has nothing to do with the
    agent.
    """
    said: list[BaseMessage] = []
    if system:
        said.append(SystemMessage(content=system))
    for m in history:
        if m["role"] == "user":
            said.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            said.append(AIMessage(content=m["content"]))
        elif m["role"] == "tool":
            said.append(ToolMessage(content=m["content"], tool_call_id="c0"))
    return said


def _bound_for_the_task(model: Any, said: dict[str, Any], tools: list[dict[str, Any]]):
    """The runnable the `@task` invokes, with this run's settings attached.

    `said` arrives already in `langchain_core`'s spelling, because
    `_settings_for_the_task` translated it before the checkpoint was written. So
    what is left here is the attaching, and it is LangChain's own two methods:
    `bind_tools` for the tool choice — the only place an integration translates a
    NAME into that provider's object — and `bind` for the rest, which `Runnable`
    hands down to `_generate`.

    `tool_choice` goes only when THIS call can carry it. `_tool_choice.can_choose`
    states the reason in full: `harness.run`'s closing call offers no tools at
    all, and a bare `any` or a bare tool name attached to a call with nothing to
    choose from is a setting in a shape the provider ignores — or rejects — with
    nothing saying it did not happen.
    """
    attach = {k: v for k, v in said.items() if k != "tool_choice"}
    chose = said.get("tool_choice")
    if tools:
        model = model.bind_tools(
            [
                {"name": t["name"], "description": t.get("description", ""),
                 "parameters": {"type": "object", "properties": {}}}
                for t in tools
            ],
            **(
                {"tool_choice": chose}
                if chose is not None
                and can_choose(chose, tuple(str(t["name"]) for t in tools))
                else {}
            ),
        )
    return model.bind(**attach) if attach else model
