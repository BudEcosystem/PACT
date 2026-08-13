"""Anthropic SDK as a transport (harness lowering).

The seam is `anthropic.types.Message` plus the SDK's own content-block model,
driven through a stubbed HTTP layer. Two deliberate choices:

* **`messages.create`, not the hosted agent loop.** The SDK's managed/session
  surface runs the loop server-side with server-side permission evaluation —
  which is a decision D17 (air-gapped) violation hiding inside the convenient
  API. That surface is explicitly not used here.
* **Real SDK types.** Blocks are constructed and read as `TextBlock` /
  `ToolUseBlock`, so the transport exercises Anthropic's actual content model
  rather than a hand-rolled dict that happens to look similar.
"""

from __future__ import annotations

from typing import Any

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from ..harness import ToolCall
from ..resolve import default_for, window_of
from ..script import Script
from ._metering import can_price, priced, tokens_in, tokens_sent, what_the_summariser_cost
from ._tool_choice import can_choose


class AnthropicTransport:
    name = "anthropic"

    #: The one transport in this package that is bound to a PROVIDER rather than
    #: to a framework. It builds `anthropic.types.Message` and reads Anthropic's
    #: content blocks, so it cannot serve weights that runtime does not serve —
    #: which is why the default model comes from the catalogue filtered by this
    #: id rather than from `default_model()`. For a round it did not: the
    #: distribution default is Qwen served by Ollama and vLLM, so this transport
    #: bound an id it cannot run and answered that its model held 32,768 tokens.
    #: A context policy on it was therefore measured against a window belonging
    #: to a different model, silently, which is the T7 breach `unmetered` exists
    #: to prevent.
    runtime = "anthropic-api"

    def __init__(
        self, script: Script, model: str | None = None, workspace: str = ""
    ) -> None:
        self.script = script
        self.model = model or default_for(self.runtime)
        #: The workspace root, when there is one. Carried for exactly one thing:
        #: a workspace may add models the distribution has never heard of, in its
        #: own `models/catalog.yaml`, and until it reached the price lookup that
        #: row was accepted by `pact check` and never opened by the thing that
        #: meters — the same half-connected seam `window_of(..., workspace=)`
        #: closed one field over.
        self.workspace = workspace
        #: The SDK's own usage object off the last `Message` this built. Kept
        #: because `usage()` is asked AFTER `model_call` has returned, and the
        #: `Message` itself is not carried past it.
        self._counted = Usage(input_tokens=0, output_tokens=0)
        #: What the last summarising call cost, priced on the SUMMARISER's row.
        #: `None` means nobody could price it, which is a different fact from
        #: nothing having been spent.
        self._summary: "tuple[int, float] | None" = (0, 0.0)
        #: Whether the catalogue publishes a price for the bound model.
        #:
        #: Published as an attribute rather than folded into whether `usage()`
        #: EXISTS, which is what it was for a round. Tokens are countable on
        #: every call this transport makes; a price is not. Tying both to one
        #: question meant a locally-served model with a window and no `cost:`
        #: block silently lost `tokens-at-most` as well — the one ceiling whose
        #: help text promises it "still bites when there is no price list".
        self.prices_money = can_price(self.model, self.workspace)

    def usage(self) -> tuple[int, "float | None"]:
        """What the last call carried, and what the catalogue says it cost.

        Read off `anthropic.types.Usage` — the field the SDK's own `Message`
        already had, and which this transport hardcoded to `input_tokens=0,
        output_tokens=0` for a round. A live `messages.create` fills that field
        in; the scripted seam counts what it actually built. Either way this
        method reads the response object rather than a private tally, so the one
        line works on both.

        The price is `models/catalog.yaml`'s, looked up through
        `resolve.price_of` on the id this transport bound. Same rule and same
        source as `context_window` above, and for the same reason: Eve recovers
        a fact about a model by matching the provider string, so there is
        nowhere to write the fact down when the match is wrong. `None` for the
        money half means the catalogue publishes no price for this row; the
        token count beside it is still real.
        """
        return priced(
            self.model,
            self._counted.input_tokens,
            self._counted.output_tokens,
            self.workspace,
        )

    def summary_usage(self) -> "tuple[int, float] | None":
        """What the last summarising call cost, on the model that made it.

        `write_summary` binds a SECOND model, so this bill never reaches
        `usage()` above — `harness.Transport` says why the method is separate.
        Without it an author who wrote both a spend cap and a `summarised-by:`
        model is paying for one model call per tidy that no ceiling counts.

        `None` when the summarising model is one the catalogue cannot price. The
        run then reports `summarised-by-cost` on `RunResult.unmetered` rather
        than charging that call at 0.00 USD, which is what it did for a round.
        """
        return self._summary

    def context_window(self) -> int | None:
        """How much the bound model can hold, from `models/catalog.yaml`.

        Eve reads a model's capabilities off the provider string —
        `model.provider.includes("anthropic")` — so a fact about a model is
        recovered by matching a substring, and there is nowhere to write it down
        when the match is wrong. Here it is a catalogue row with a source and an
        `as-of` date beside it, looked up by the id this transport is bound to.

        The script decides what the model *says*; the catalogue decides what it
        can *hold*. Those are different facts, and only the second one is a
        property of the binding rather than of the stand-in — which is why this
        answers where `mock.ReferenceTransport`, bound to no model at all, stays
        silent and lets the run report `context-policy` as unenforced.
        """
        return window_of(self.model, workspace=self.workspace or None)

    def write_summary(self, text: str, model: str) -> str:
        """One summarising call, made with the model `summarised-by:` names.

        The last hop of `context-policy.summarised-by:`. Without it the author's
        line resolved, validated, and did nothing: `summarise-older` fired, found
        no summariser, wrote a note and left the conversation the length it was.

        A second transport rather than a second code path — same class, same
        script, another model id — because "summarise with a different model" is
        one model call and the harness already knows how to make one. Nothing
        about the work model changes; `self.model` is untouched.
        """
        other = AnthropicTransport(self.script, model=model, workspace=self.workspace)
        message = other._message([{"role": "user", "content": text}])
        # What that second call cost, taken from the transport that made it so
        # it is priced on the summarising model's own catalogue row.
        self._summary = what_the_summariser_cost(other)
        return "".join(b.text for b in message.content if isinstance(b, TextBlock))

    def lattice(self) -> dict[str, str]:
        return {
            "model_call": "native",
            "tool_calls": "native",
            "text_with_tool_calls": "native",
            "parallel_tool_calls": "native",
            "streaming": "emulated",
            "durable_resume": "unsupported",
            # Worth being explicit about, because a reader may expect `native`:
            # this PROVIDER publishes a server-side connector that would reach an
            # MCP server, and this transport binds `messages.create` and not
            # that. What a provider can do and what this file does are different
            # claims and a lattice states the second — so the reaching here is
            # PACT's own client above the seam, which is `emulated`; `mock.py`
            # states the rule once for every target that shares it.
            "connected_tools": "emulated",
        }

    def _message(self, history: list[dict[str, Any]], system: str = "") -> Message:
        turn = self.script.next_turn(history)
        content: list[Any] = []
        if turn.text:
            content.append(TextBlock(type="text", text=turn.text))
        for i, c in enumerate(turn.tool_calls):
            content.append(
                ToolUseBlock(type="tool_use", id=f"toolu_{i}", name=c.name, input=dict(c.args))
            )
        # The `Usage` block, filled in rather than zeroed. It was
        # `input_tokens=0, output_tokens=0` for a round, which is why
        # `cost-per-request-under` and `tokens-at-most` were the two ceilings no
        # shipped transport could measure. A live `messages.create` fills this
        # in; a scripted seam counts what it built, and the tool arguments are
        # counted with the text because they are output the provider bills for.
        answered = "".join(
            [b.text for b in content if isinstance(b, TextBlock)]
            + [f"{b.name}{b.input}" for b in content if isinstance(b, ToolUseBlock)]
        )
        message = Message(
            id="msg_1", type="message", role="assistant", model=self.model,
            content=content,
            stop_reason="tool_use" if turn.tool_calls else "end_turn",
            usage=Usage(
                input_tokens=tokens_sent(system, history),
                output_tokens=tokens_in(answered),
            ),
        )
        self._counted = message.usage
        return message

    def apply_settings(self, settings: dict[str, Any]) -> tuple[str, ...]:
        """Take the author's `settings:` block, and say what could not be taken.

        The whole group crossed no adapter boundary for a round — twelve fields,
        two of them `tier: core`, appearing in zero source files — so
        `max-tokens: 5` and `thinking: high` loaded cleanly and reached no
        provider. Optional on the protocol for the reason every other capability
        here is: a transport that cannot honour a key says so, and the run reports
        it, rather than the key being dropped in silence.
        """
        self._settings = dict(settings)
        return tuple(k for k in settings if k not in _WIRE)

    def request_for(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """The `messages.create` request this transport is about to make.

        Split out of `model_call` for the reason `ollama_transport.payload_for`
        was, and it is the same defect one file over: this dict was a LOCAL named
        `_request`, built in the SDK's wire shape "so the mapping is exercised"
        and then never read by anything. Nothing sent it and no test could reach
        it, so `apply_settings` reporting seven of the twelve keys honoured rested
        on a mapping table and a dict thrown away on the next line — a seam
        asserted instead of an effect, which is the defect this whole round is
        about. Returning it makes the claim checkable without a served model.
        """
        settings = getattr(self, "_settings", {})
        offered = tuple(str(t["name"]) for t in tools)
        return {
            "model": self.model,
            "system": system,
            # The author's ceiling if they wrote one. `max-tokens`' help says
            # PACT otherwise uses what the model says it can do — "which is what
            # stops the same tree truncating on one framework and not another" —
            # and 1024 was hardcoded here for every run in every workspace.
            "max_tokens": int(settings.get("max-tokens") or (self.context_window() or 8192) // 8),
            "tools": [
                {"name": t["name"], "description": t.get("description", ""),
                 "input_schema": {
                     "type": "object",
                     "properties": {a: {"type": "string", "description": s}
                                    for a, s in (t.get("parameters") or {}).items()},
                 }}
                for t in tools
            ],
            "messages": _to_messages(history),
            **{
                _WIRE[k]: _translated(k, v)
                for k, v in settings.items()
                # `max-tokens` has its own line above; putting it here as well
                # would set it twice.
                if k in _WIRE and k != "max-tokens"
                # And a tool choice only when THIS call can carry it. The other
                # five transports that map `tool-choice` decide this per call
                # through `_tool_choice.can_choose`; this one did not, because
                # the request it built went nowhere and so nothing ever failed.
                # It is not merely unhonoured on a call with no tools: this
                # provider's `tool_choice` is documented as valid only "while
                # providing tools", and `harness.run` closes every
                # ceiling-terminated run with `model_call(instructions, history,
                # [])` while a stage may narrow the set to nothing or to tools
                # the author's choice does not name. So the live version of this
                # request would have been rejected on exactly the calls a run
                # makes when it stops early.
                and (k != "tool-choice" or can_choose(v, offered))
            },
        }

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        # Built through the same method a test asserts, so the request a run
        # makes and the request a test reads are one object and not two.
        self._last_request = self.request_for(system, history, tools)
        message = self._message(history, system)
        text = "".join(b.text for b in message.content if isinstance(b, TextBlock))
        calls = [
            ToolCall(name=b.name, args=dict(b.input) if isinstance(b.input, dict) else {})
            for b in message.content
            if isinstance(b, ToolUseBlock)
        ]
        return text, calls


#: The author's key, and the provider's. One mapping per transport is what the
#: `settings` group's own header makes possible — *"every key here works on every
#: provider"* — and it is why the group is closed.
_WIRE: dict[str, str] = {
    "max-tokens": "max_tokens",
    "temperature": "temperature",
    "top-p": "top_p",
    "top-k": "top_k",
    "stop-sequences": "stop_sequences",
    "service-tier": "service_tier",
    # This provider DOES take a tool choice — it was missing from this table, not
    # from the API, and the gap register recorded the field as reaching no
    # transport partly because of that. It is the one key here that is not a
    # straight copy; `_translated` is why.
    "tool-choice": "tool_choice",
}

#: What each `tool-choice:` word is in this provider's shape. `required` is
#: spelled `any` here, which is exactly the sort of per-provider difference one
#: mapping table per transport exists to absorb — the author writes one word and
#: it works on every target, which is what the `settings` group's header promises.
_CHOICES: dict[str, dict[str, str]] = {
    "auto": {"type": "auto"},
    "required": {"type": "any"},
    "none": {"type": "none"},
}


def _translated(key: str, value: Any) -> Any:
    """One authored value in this provider's shape.

    Only `tool-choice:` needs translating, and here every one of its four values
    does: this API takes an object where the OpenAI-compatible one takes a bare
    word for three of them. A bare `"auto"` sent here is a type error, not a
    silent no-op — which is the better failure, and still not one to ship.
    """
    if key != "tool-choice":
        return value
    said = str(value).strip()
    return _CHOICES.get(said, {"type": "tool", "name": said})


def _to_messages(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PACT history -> Anthropic messages.

    Tool results are `tool_result` content blocks on a *user* turn, which is
    Anthropic's shape and differs from every other target — precisely the sort
    of divergence a single IR has to absorb.
    """
    out: list[dict[str, Any]] = []
    for m in history:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            out.append({"role": "assistant", "content": m["content"]})
        elif m["role"] == "tool":
            out.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_0",
                             "content": m["content"]}],
            })
    return out
