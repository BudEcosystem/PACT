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

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.func import entrypoint, task

from ..harness import ToolCall
from ..resolve import default_model, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, tokens_sent, what_the_summariser_cost
from ._summarise import summarise_with


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
            turn = self.script.next_turn(payload["history"])
            return {
                "text": turn.text,
                "calls": [{"name": c.name, "args": dict(c.args)} for c in turn.tool_calls],
                # The system prompt counts with the history because the provider
                # bills it, and a `loop:` that swaps a long instruction in per
                # stage is a cost the author can act on.
                "in": tokens_sent(str(payload.get("system") or ""), payload["history"]),
                "out": tokens_in(
                    (turn.text or "")
                    + "".join(f"{c.name}{dict(c.args)}" for c in turn.tool_calls)
                ),
            }

        @entrypoint(checkpointer=self._saver)
        def _run(payload: dict[str, Any]) -> dict[str, Any]:
            return _call(payload).result()

        self._graph = _run

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
        }

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        out = await self._graph.ainvoke(
            {"system": system, "history": history, "tools": tools}, config
        )
        self._counted = (int(out.get("in") or 0), int(out.get("out") or 0))
        return out["text"], [ToolCall(name=c["name"], args=c["args"]) for c in out["calls"]]
