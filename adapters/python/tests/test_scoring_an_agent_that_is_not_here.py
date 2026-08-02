"""AC-4.3 — evals against a remote agent, over HTTP.

> Evals run against a *remote* agent over A2A/HTTP.

Every other transport binds a **model** and lets PACT's harness own the loop.
`A2ATransport` binds an **agent**: something already running behind a URL that
does its own thinking. The shape is the same one method; what it means is
different, and the tests here are almost all about that difference.

**Remote does not mean off-box.** D17 holds — the stub below is on `localhost`,
which is exactly as remote as anywhere else for the purpose the criterion names:
it is not in this process. Nothing here reaches the network, and the transport
has no default URL, deliberately, so it cannot reach anywhere nobody chose.

The property that matters is not "it works". It is that a score against somebody
else's agent **says so** — the author's loop, rules and ceilings all decide
nothing, and a report that did not name them would attribute another agent's
behaviour to a document it never read.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.transports.a2a_transport import (  # noqa: E402
    METHOD,
    NOT_OURS,
    A2ATransport,
    _the_text_of,
)


class _AnAgent(BaseHTTPRequestHandler):
    """A stand-in for somebody else's agent. Answers, and says nothing else."""

    reply: dict[str, Any] = {}
    seen: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 — the base class names it
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen.append(body)
        out = json.dumps(type(self).reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *_: Any) -> None:
        return          # a test that prints one line per request is unreadable


@pytest.fixture
def agent_at():
    """A stub agent on localhost. Returns `(url, handler)`."""
    _AnAgent.seen = []
    server = HTTPServer(("127.0.0.1", 0), _AnAgent)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", _AnAgent
    finally:
        server.shutdown()
        server.server_close()


def _spec() -> AgentSpec:
    return AgentSpec(
        name="Desk", description="Answers questions.",
        instructions="Answer the question.",
    )


# ────────────────────────────────────────── it reaches an agent


def test_a_run_reaches_the_agent_and_returns_what_it_said(agent_at) -> None:
    url, handler = agent_at
    handler.reply = {
        "jsonrpc": "2.0", "id": "1",
        "result": {"parts": [{"kind": "text", "text": "Approved."}]},
    }
    out = asyncio.run(run(_spec(), A2ATransport(url), "can I have a refund?"))

    assert out.halted == "final", out.halted
    assert out.output == "Approved."
    assert handler.seen, "the agent was never asked"
    sent = handler.seen[0]
    assert sent["method"] == METHOD, sent
    said = sent["params"]["message"]["parts"][0]["text"]
    assert said == "can I have a refund?", sent


def test_the_run_says_which_of_the_authors_mechanisms_decided_nothing(
    agent_at,
) -> None:
    """The property that makes a remote score honest.

    A remote agent owns its own loop, so the author's stages, interceptor rules
    and ceilings hold nothing — and a score that did not say so would attribute
    somebody else's behaviour to a document they never read.
    """
    url, handler = agent_at
    handler.reply = {"result": {"parts": [{"kind": "text", "text": "ok"}]}}
    out = asyncio.run(run(_spec(), A2ATransport(url), "hello"))

    said = "\n".join(out.unenforced)
    for owed in ("loop:", "interceptors:", "limits:"):
        assert owed in said, f"nothing said `{owed}` decides nothing here:\n{said}"
    assert len(out.unenforced) >= len(NOT_OURS)


def test_a_transport_with_nothing_to_say_is_unaffected() -> None:
    """`unenforced()` is asked for the way `usage()` is — optional, and a
    transport that does not have it changes nothing. Otherwise every other
    transport in the suite would have to grow a method to stay silent."""
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    out = asyncio.run(
        run(_spec(), ReferenceTransport(Script([Turn("ok")])), "hello")
    )
    assert out.unenforced == (), out.unenforced


# ─────────────────────────────── and it is honest about what it is not


def test_it_does_not_claim_to_have_seen_tool_calls(agent_at) -> None:
    """The surprising entry in the lattice, and the correct one. The remote agent
    may well use tools; **we do not see them**. Reporting `native` because tools
    were probably involved would claim to have observed something nobody
    observed."""
    url, handler = agent_at
    handler.reply = {"result": {"parts": [{"kind": "text", "text": "done"}]}}
    lattice = A2ATransport(url).lattice()
    assert lattice["tool_calls"] == "unsupported", lattice
    assert lattice["model_call"] == "degraded", lattice
    assert set(lattice.values()) <= {"native", "emulated", "degraded", "unsupported"}


def test_it_has_no_default_url() -> None:
    """A transport that reached somewhere by default is one that can leave this
    machine without anybody choosing to."""
    with pytest.raises(ValueError) as refused:
        A2ATransport("")
    assert "no default" in str(refused.value)


def test_another_agents_cost_is_not_invented(agent_at) -> None:
    """`usage()` is `None` unless the agent volunteered a number. Inventing one
    would put a figure against a spend cap that never bound anything."""
    url, handler = agent_at
    handler.reply = {"result": {"parts": [{"kind": "text", "text": "ok"}]}}
    transport = A2ATransport(url)
    asyncio.run(run(_spec(), transport, "hello"))
    assert transport.usage() is None

    handler.reply = {
        "result": {
            "parts": [{"kind": "text", "text": "ok"}],
            "usage": {"totalTokens": 120, "cost": 0.004},
        }
    }
    volunteered = A2ATransport(url)
    asyncio.run(run(_spec(), volunteered, "hello"))
    assert volunteered.usage() == (120, 0.004)


# ──────────────────────────────────── an odd reply is a report, not a crash


@pytest.mark.parametrize(
    "reply,expected",
    [
        ({"result": {"parts": [{"kind": "text", "text": "hi"}]}}, "hi"),
        ({"result": {"message": {"parts": [{"text": "nested"}]}}}, "nested"),
        ({"result": {"text": "plain"}}, "plain"),
        ({"result": "a bare string"}, "a bare string"),
        ({"error": {"message": "no such agent"}}, "no such agent"),
        ({"result": {"unexpected": 1}}, "no text in the reply"),
    ],
)
def test_an_unfamiliar_reply_is_reported_rather_than_raised(
    reply: dict, expected: str
) -> None:
    """A2A implementations differ in where they put the text. A transport that
    raised on an unfamiliar shape would turn *"that agent answered oddly"* into
    *"the eval crashed"* — a worse report about a thing that did answer."""
    assert expected in _the_text_of(reply)


def test_an_agent_that_counts_and_does_not_price_is_not_recorded_as_free(
    agent_at,
) -> None:
    """The middle answer, and the one this got wrong.

    `None` for the money means *counted, not priced*. `0.0` means *free*, and
    `models/catalog.yaml` forbids exactly that substitution in its own words:
    *"pricing an unsourced row at zero would give the author a spend cap that can
    never be reached, which is strictly worse than having no cap"*.

    `_meter_usage` has handled `None` all along, one line after saying that
    adding `0.0` would be the mistake — so this transport was making a claim the
    harness had already written a paragraph refusing.
    """
    url, handler = agent_at
    handler.reply = {
        "result": {
            "parts": [{"kind": "text", "text": "ok"}],
            "usage": {"totalTokens": 120},          # tokens, and no cost
        }
    }
    transport = A2ATransport(url)
    out = asyncio.run(run(_spec(), transport, "hello"))

    counted = transport.usage()
    assert counted is not None
    tokens, money = counted
    assert tokens == 120
    assert money is None, (
        "the agent counted the call and said nothing about price; recording that "
        "as 0.00 is a spend cap that can never be reached"
    )
    # The token count still reaches the meter, which is the point of splitting
    # the two questions.
    assert out.used is not None and out.used.tokens == 120
    assert out.used.money == 0.0, "and nothing was added to the money meter"
