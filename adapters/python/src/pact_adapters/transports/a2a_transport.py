"""Scoring an agent that is not in this process (AC-4.3).

> Evals run against a *remote* agent over A2A/HTTP.

Every other transport here binds a **model** and lets PACT's harness own the
loop. This one binds an **agent**: something already running, behind a URL, that
does its own thinking. So the shape is the same — one `model_call` — and what it
means is different, and that difference is the whole reason this file exists
rather than being a flag on another transport.

**PACT's loop does not run.** A remote agent has its own; asking it a question
returns its answer, not one step of ours. So a run over this transport is one
step by construction, and `RunResult.unenforced` says which of the author's
mechanisms therefore held nothing: the loop, the interceptors, the ceilings. An
eval score against a remote agent is a claim about **that agent**, and a report
that did not say so would be attributing somebody else's behaviour to a document
they never read.

**Remote does not mean off-box.** D17 holds: this speaks HTTP, and an agent on
`localhost` is exactly as remote as one anywhere else for the purpose the
criterion names — it is not in this process. Where it may point is
`allow-egress:`'s business, and `egress.py` is where that is decided; nothing
here reaches the network by default, because nothing here has a default URL.
"""

from __future__ import annotations

import json
from typing import Any

from ..harness import ToolCall

#: What an A2A `message/send` looks like on the wire, as a JSON-RPC method name.
#: Written here rather than assembled inline so a reader can see the one thing
#: this speaks.
METHOD = "message/send"

#: What a run over this transport could not carry out, in the words
#: `RunResult.unenforced` uses. Every one is a mechanism the author wrote that a
#: remote agent's own loop makes unreachable.
NOT_OURS = (
    "loop: — the remote agent has its own, so the stages you wrote decide "
    "nothing about how it thinks. A run here is one exchange.",
    "interceptors: — nothing of yours sits between that agent and its model, so "
    "a rule that hides or stops something never runs.",
    "limits: — the ceilings bound what this process does, and this process makes "
    "one call. What the remote agent spends is its own business.",
)


class A2ATransport:
    """One exchange with an agent that is already running, over HTTP."""

    #: Not a model runtime. Declared so `_served` and the catalogue never try to
    #: bind an id here: what this transport talks to is an agent, and an agent is
    #: not a row in `models/catalog.yaml`.
    runtime = "a2a"

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 60.0,
        headers: "dict[str, str] | None" = None,
    ) -> None:
        if not url:
            raise ValueError(
                "an A2A transport needs the agent's URL. There is no default, "
                "deliberately: a transport that reached somewhere by default is "
                "one that can leave this machine without anybody choosing to."
            )
        self.url = url
        self._timeout = timeout
        self._headers = dict(headers or {})
        self._counted: "tuple[int, float] | None" = None

    def lattice(self) -> dict[str, str]:
        """What this can and cannot do, in the four words the lattice uses.

        `tool_calls: unsupported` is the honest entry and the surprising one: the
        remote agent may well use tools, and **we do not see them**. What comes
        back is an answer. Reporting `native` because tools were probably
        involved would be claiming to have observed something nobody observed.
        """
        return {
            "model_call": "degraded",
            "tool_calls": "unsupported",
            "text_with_tool_calls": "unsupported",
            "parallel_tool_calls": "unsupported",
            "streaming": "unsupported",
            "durable_resume": "unsupported",
        }

    def unenforced(self) -> tuple[str, ...]:
        """The author's mechanisms a remote agent makes unreachable.

        Read by `harness.run` through the same door every other unenforced
        sentence uses, so a reader finds them in one place rather than having to
        know that this transport is different.
        """
        return NOT_OURS

    def usage(self) -> "tuple[int, float | None] | None":
        """What the last exchange cost, if the agent said.

        Almost always `None`, and that is a fact worth reporting rather than a
        gap to fill: another agent's token count is not ours to know, and
        inventing one would put a number against a spend cap that never bound
        anything.
        """
        return self._counted

    async def model_call(
        self,
        system: str,
        history: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str, list[ToolCall]]:
        """Ask the remote agent, and return what it said.

        `tools` is deliberately ignored and not silently dropped — `lattice()`
        says `tool_calls: unsupported` and `unenforced()` says why in a sentence.
        Offering a tool list to an agent that has its own is not a smaller
        version of tool calling; it is a different thing wearing its name.
        """
        import httpx

        asked = next(
            (m["content"] for m in reversed(history) if m.get("role") == "user"),
            "",
        )
        body = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": METHOD,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": asked}],
                }
            },
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            reply = await client.post(self.url, json=body, headers=self._headers)
            reply.raise_for_status()
            said = reply.json()

        self._counted = _what_it_cost(said)
        return _the_text_of(said), []


def _the_text_of(reply: Any) -> str:
    """The answer out of an A2A reply, or a sentence saying it had none.

    Tolerant on purpose. A2A implementations differ in where they put the text,
    and a transport that raised on an unfamiliar shape would turn "that agent
    answered oddly" into "the eval crashed" — which is a worse report about a
    thing that did answer.
    """
    if not isinstance(reply, dict):
        return str(reply)
    if "error" in reply and reply["error"]:
        got = reply["error"]
        said = got.get("message") if isinstance(got, dict) else got
        return f"[the remote agent returned an error: {said}]"
    result = reply.get("result", reply)
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for where in ("parts", "content"):
            parts = result.get(where)
            if isinstance(parts, list):
                text = "".join(
                    p.get("text", "") for p in parts if isinstance(p, dict)
                )
                if text:
                    return text
        for key in ("text", "message", "output"):
            if isinstance(result.get(key), str):
                return result[key]
        message = result.get("message")
        if isinstance(message, dict):
            return _the_text_of({"result": message})
    return f"[no text in the reply: {json.dumps(reply)[:200]}]"


def _what_it_cost(reply: Any) -> "tuple[int, float | None] | None":
    """Tokens and money, if the agent volunteered them.

    Three answers, and the middle one is the one this got wrong. `None` means the
    agent said nothing at all — the usual case, see `usage`. `(tokens, None)`
    means it counted the call and did not price it. `(tokens, money)` means it
    said both.

    **The money half was `0.0` when the agent gave tokens and no cost**, which is
    a claim that the call was free. `models/catalog.yaml` forbids exactly this in
    its own words — *"pricing an unsourced row at zero would give the author a
    spend cap that can never be reached, which is strictly worse than having no
    cap"* — and `_meter_usage` already handles `None` for precisely this case,
    one line after saying that adding `0.0` would be the mistake. Written in a
    file that quotes the rule, an hour after reading it.
    """
    if not isinstance(reply, dict):
        return None
    usage = (reply.get("result") or {}).get("usage") if isinstance(
        reply.get("result"), dict
    ) else None
    if not isinstance(usage, dict):
        return None
    tokens = usage.get("totalTokens") or usage.get("total_tokens")
    if not isinstance(tokens, (int, float)):
        return None
    money = usage.get("cost")
    # `None`, not `0.0`. See the docstring: another agent's silence about price is
    # not a price of zero.
    return int(tokens), float(money) if isinstance(money, (int, float)) else None
