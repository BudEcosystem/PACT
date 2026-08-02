"""A live local-model transport.

Everything else in this package is scripted, deliberately: determinism is what
lets the conformance suite attribute a divergence to an adapter rather than to
sampling. But determinism cannot answer the question the whole project exists
for — *does a smaller model still meet the contract?* That needs real weights.

Ollama is used because it is local: decision D17 requires the entire pipeline to
run air-gapped, so the accuracy experiment must not depend on a hosted API. The
wire format is OpenAI-compatible, which also makes this the shape a production
gateway transport would take.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..harness import ToolCall
from ..resolve import window_of
from ..script import Script
from ._metering import can_price, priced


class OllamaTransport:
    """One model call against a locally-served model."""

    #: Which runtime this is, in the catalogue's own `served-by:` vocabulary.
    #: Declared so that "the id this transport bound is one this runtime can
    #: serve" is a fact something can check, rather than a thing everybody
    #: assumes. The model is required here, so nothing is defaulted from it.
    runtime = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434/v1",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float = 180.0,
        workspace: str = "",
        _script: Script | None = None,   # accepted for interface symmetry; unused
    ) -> None:
        self.model = model
        #: The workspace root, so a row this machine added to its own
        #: `models/catalog.yaml` is priced and sized. This is the transport that
        #: case is FOR: a locally-served model the distribution has never heard
        #: of is exactly what an air-gapped box runs, and until this reached the
        #: price lookup the row was accepted by `pact check` and never opened by
        #: the thing that meters.
        self.workspace = workspace
        self.name = f"ollama/{model}"
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._temperature = temperature
        # On CPU, generation time dominates: an uncapped model writes 300 tokens
        # where 40 would answer, at roughly five tokens a second. Capping is also
        # honest for this task — the contract asks for a decision, a reason and
        # an amount, not an essay.
        self._max_tokens = max_tokens
        self._timeout = timeout
        self.last_latency_s: float = 0.0
        #: What the last response said it used. Real counts off the wire — this
        #: is the one transport in this package that talks to a server, so it is
        #: the one that never has to estimate.
        self._counted: tuple[int, int] = (0, 0)
        #: What the last summarising call cost, priced on the SUMMARISER's row.
        #: `None` means nobody could price it.
        self._summary: "tuple[int, float] | None" = (0, 0.0)
        #: Whether the catalogue publishes a price for the bound model.
        #:
        #: A model this machine serves and this distribution has no price for
        #: leaves the MONEY ceiling on `RunResult.unmetered` rather than metered
        #: at zero — and keeps `tokens-at-most`, because this transport reads the
        #: counts straight off the wire and can enforce it perfectly well. The
        #: fix an author needs for the money half is a `cost:` block on the row in
        #: their workspace's own `models/catalog.yaml`, not a branch here.
        self.prices_money = can_price(self.model, self.workspace)

    def usage(self) -> tuple[int, "float | None"]:
        """What the last call used, as the server reported it, priced here.

        `prompt_tokens` and `completion_tokens` come back on the
        OpenAI-compatible response, so nothing is estimated: this is the case
        the whole mechanism is shaped for, and the scripted seams imitate it.
        The price is the catalogue's — a locally-served row publishes
        `input-per-mtok: 0 USD`, which is a SOURCED zero and not a missing one,
        so a spend cap over a local model is enforced and correctly never fires.
        """
        return priced(self.model, *self._counted, workspace=self.workspace)

    def summary_usage(self) -> "tuple[int, float] | None":
        """What the last summarising call cost, on the model that made it.

        Separate from `usage()` because `write_summary` binds a SECOND model —
        `harness.Transport` says why. Without it a `summarised-by:` model spends
        outside the author's cap.
        """
        return self._summary

    def context_window(self) -> int | None:
        """How much this locally-served model can hold, from `models/catalog.yaml`.

        Looked up rather than asked for, because Ollama's OpenAI-compatible
        surface does not report it and `num_ctx` is a serving decision the client
        cannot read back. The catalogue is keyed on `(model, provider, runtime)`
        for exactly this reason (arch §4.2), so the row carries the tag Ollama
        answers to — `qwen2.5:7b-instruct` — beside the catalogue id, and one
        row serves both.

        `None` for a model with no row is the honest answer and it is the whole
        point of this being data: the fix for an unlisted model is a line in the
        catalogue, not a branch in this file.
        """
        return window_of(self.model, workspace=self.workspace or None)

    def write_summary(self, text: str, model: str) -> str:
        """One summarising call against a DIFFERENT locally-served model.

        The last hop of `context-policy.summarised-by:`, on the one transport in
        this package bound to real weights. Without it the author's line
        resolved, validated and did nothing: `summarise-older` fired, found no
        summariser, wrote a note, and the ladder fell through to
        `if-it-still-does-not-fit:` on a conversation a summariser would have
        handled. D14 does not allow "a host writes Python for that".

        Synchronous, and deliberately: tidying decides mid-history what to fold,
        so a summariser the tidier has to await would make every strategy async.
        One blocking request, to a model this machine already serves — no
        network leaves the box, so this still holds air-gapped (D17).
        """
        resp = httpx.post(
            self._url,
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Summarise the conversation below. Keep decisions, "
                            "figures and anything a person approved. Be brief."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "temperature": 0.0,
                "stream": False,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        answered = resp.json()
        # What the summarising call cost, priced on the SUMMARISING model's row
        # rather than on this transport's — they are different models, which is
        # the whole point of `summarised-by:`.
        self._summary = _billed(model, answered.get("usage"), self.workspace)
        message = ((answered.get("choices") or [{}])[0].get("message") or {})
        return message.get("content") or ""

    def lattice(self) -> dict[str, str]:
        return {
            "model_call": "native",
            "tool_calls": "native",
            "text_with_tool_calls": "native",
            "parallel_tool_calls": "native",
            "streaming": "emulated",
            "durable_resume": "unsupported",
        }

    def apply_settings(self, settings: dict[str, Any]) -> tuple[str, ...]:
        """Take the author's `settings:` block, and say what could not be taken.

        This transport speaks the OpenAI-compatible `/v1/chat/completions` shape,
        which is where `presence-penalty`, `frequency-penalty` and `tool-choice`
        live — the three keys the gap register recorded as *"writable and reach no
        transport"*. They reached none because the only transport that implemented
        this method was the Anthropic one, whose provider has no penalties at all.
        So the three were unreachable for the reason a reader would least guess:
        not that nothing mapped them, but that the one thing that mapped anything
        could not have.

        `thinking:` and `parallel-tool-calls:` are still returned as left over.
        That is not a stub — this endpoint takes neither, and saying so is what
        puts them on `RunResult.unmetered` instead of dropping them.
        """
        self._settings = dict(settings)
        return tuple(k for k in settings if k not in _WIRE)

    def payload_for(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """The request this transport is about to send.

        Split out of `model_call` so it can be ASSERTED without a served model.
        The first test written for the `settings:` mapping checked `_WIRE`
        membership and what `apply_settings` returned — both true of a transport
        that then dropped every setting on the floor. Severing the settings from
        the payload left the suite green, which is the defect this whole round is
        about, one layer down: a seam tested instead of an effect.
        """
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        for m in history:
            if m["role"] == "user":
                messages.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                messages.append({"role": "assistant", "content": m["content"] or "."})
            elif m["role"] == "tool":
                messages.append(
                    {"role": "user", "content": f"[result of {m['name']}] {m['content']}"}
                )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
            "stream": False,
        }
        if self._max_tokens is not None:
            payload["max_tokens"] = self._max_tokens
        # The author's `settings:` block, on the transport an air-gapped install
        # actually runs. Applied AFTER the two defaults above so a written
        # `temperature:` or `max-tokens:` wins over the constructor's — the
        # constructor's values are what a host chose, and an author's file is
        # more specific than a host's default.
        for key, value in getattr(self, "_settings", {}).items():
            if key in _WIRE:
                payload[_WIRE[key]] = _translated(key, value)
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
                for t in tools
            ]

        return payload

    async def model_call(
        self, system: str, history: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[ToolCall]]:
        payload = self.payload_for(system, history, tools)

        import time

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        self.last_latency_s = time.perf_counter() - started

        # The token vector, straight off the response. Y14 requires the adapter
        # to set whatever flag obtains it where one exists; this surface reports
        # it on a non-streamed request without asking, and `stream: False` above
        # is why — the streamed shape is where `stream_options` decides whether
        # the counts arrive at all.
        used = data.get("usage") or {}
        self._counted = (
            int(used.get("prompt_tokens") or 0), int(used.get("completion_tokens") or 0)
        )

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        calls = [
            ToolCall(
                name=(c.get("function") or {}).get("name", ""),
                args=_loads((c.get("function") or {}).get("arguments")),
            )
            for c in (message.get("tool_calls") or [])
        ]
        return text, calls


def _billed(model: str, used: Any, workspace: str = "") -> "tuple[int, float] | None":
    """One response's `usage` block, priced on `model`'s catalogue row.

    `None` for a model the catalogue cannot price, never `(0, 0.0)`. It was
    `(0, 0.0)` for a round, which handed `charge(0, 0.0)` to the meter the
    author's spend cap reads — a summarising model billed as free. The run now
    reports `summarised-by-cost` on `RunResult.unmetered` instead, which is the
    door every other unmeasurable thing already leaves by.
    """
    counts = used if isinstance(used, dict) else {}
    tokens, money = priced(
        model,
        int(counts.get("prompt_tokens") or 0),
        int(counts.get("completion_tokens") or 0),
        workspace=workspace,
    )
    return None if money is None else (tokens, money)


def _loads(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw or "{}")
        return out if isinstance(out, dict) else {}
    except (TypeError, ValueError):
        return {}


#: The author's key, and this endpoint's. One mapping per transport, which is
#: what the `settings` group's own header makes possible — *"every key here works
#: on every provider"* — and why the group is closed rather than open.
#:
#: `thinking` and `parallel-tool-calls` are deliberately absent: the
#: OpenAI-compatible endpoint takes neither, and a row here that mapped them onto
#: something approximate would make `unmetered` lie by omission.
_WIRE: dict[str, str] = {
    "max-tokens": "max_tokens",
    "temperature": "temperature",
    "top-p": "top_p",
    "top-k": "top_k",
    "stop-sequences": "stop",
    "seed": "seed",
    "presence-penalty": "presence_penalty",
    "frequency-penalty": "frequency_penalty",
    "tool-choice": "tool_choice",
}


#: The three `tool-choice:` words this endpoint takes as they are written.
_PLAIN_CHOICES = ("auto", "required", "none")


def _translated(key: str, value: Any) -> Any:
    """One authored value in this endpoint's shape.

    Only `tool-choice:` needs it, and it needs it in one case out of four. Its
    help says *"auto, required, none, or one tool name"* — the three words go on
    the wire unchanged, and a NAME has to become
    `{"type": "function", "function": {"name": ...}}`. Passing the name through as
    a bare string is accepted by the endpoint and silently means nothing, which is
    the "translate or nothing" line: a setting that arrives in a shape the
    provider ignores is worse than one reported as unhonoured, because nothing
    says it did not happen.
    """
    if key != "tool-choice":
        return value
    said = str(value).strip()
    if said in _PLAIN_CHOICES:
        return said
    return {"type": "function", "function": {"name": said}}
