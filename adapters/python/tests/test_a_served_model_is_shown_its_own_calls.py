"""A served model is shown its own calls, and a server that refuses a field is asked again.

`OllamaTransport` is the one transport here that reaches a real model: anything
that speaks `/chat/completions`, on this machine or hosted. Running the limits
cases' workspace through it on a live model found three things no scripted
model can.

* **The model was not shown its own calls.** A turn that called tools was sent
  as `.`, and each result as a line of the user's: `[result of ledger] rent:
  entry found`. Asked for five lookups with three steps allowed, gpt-4o-mini
  made the same five lookups in every step — fifteen — and ran out of steps.
  Shown the calls as calls, it makes five and answers.
* **A current model could not be reached at all.** gpt-5-nano answers 400 to
  `max_tokens` (it wants `max_completion_tokens`) and to any temperature but
  its own. Every request this transport made carried both.
* What keeps a call's arguments has to survive a tidying step, or a tidied
  conversation goes back to the first defect.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.context_policy import from_history, to_history  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.ollama_transport import OllamaTransport  # noqa: E402
from trees import shown  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def look(*entries: str) -> Turn:
    return Turn("", tuple(ToolCall("ledger", {"action": "look", "entry": e}) for e in entries))


def a_run() -> list[dict[str, Any]]:
    """The conversation a real run keeps: two lookups in one reply, then an answer."""
    spec = AgentSpec.from_document(shown(REPO / "tests/conformance/trees/metered-desk"), "paced")
    seen: list[list[dict[str, Any]]] = []

    class Kept(ReferenceTransport):
        async def model_call(self, system, history, tools):  # type: ignore[override]
            seen.append([dict(m) for m in history])
            return await super().model_call(system, history, tools)

    out = asyncio.run(
        run(spec, Kept(Script([look("rent", "gas"), Turn("Both are there.")])), "Look up rent and gas.",
            {"ledger": lambda args: f"{args['entry']}: entry found"})
    )
    assert out.halted == "final"
    return seen[-1]


def served() -> OllamaTransport:
    return OllamaTransport("some-model", base_url="http://localhost:1/v1", max_tokens=300)


# ── the calls are sent as calls ──────────────────────────────────────────────


def test_the_run_keeps_what_each_call_was_given() -> None:
    turn = next(m for m in a_run() if m["role"] == "assistant")
    assert turn["tool_calls"] == ["ledger", "ledger"]
    assert turn["calls"] == [
        {"name": "ledger", "args": {"action": "look", "entry": "rent"}},
        {"name": "ledger", "args": {"action": "look", "entry": "gas"}},
    ]


def test_a_turn_that_called_tools_is_sent_as_calls_and_each_result_answers_one() -> None:
    messages = served().payload_for("Look things up.", a_run(), [])["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "tool"]
    turn = messages[2]
    assert [c["function"]["name"] for c in turn["tool_calls"]] == ["ledger", "ledger"]
    assert [json.loads(c["function"]["arguments"]) for c in turn["tool_calls"]] == [
        {"action": "look", "entry": "rent"},
        {"action": "look", "entry": "gas"},
    ]
    ids = [c["id"] for c in turn["tool_calls"]]
    assert len(set(ids)) == 2
    assert [(m["tool_call_id"], m["content"]) for m in messages[3:]] == [
        (ids[0], "rent: entry found"),
        (ids[1], "gas: entry found"),
    ]
    # Nothing is put in the user's mouth any more.
    assert not any("[result of" in str(m.get("content")) for m in messages)


def test_two_turns_never_share_an_id() -> None:
    history = a_run()
    twice = history + [m for m in history if m["role"] != "user"]
    messages = served().payload_for("", twice, [])["messages"]
    ids = [c["id"] for m in messages for c in m.get("tool_calls") or ()]
    assert len(ids) == 4 and len(set(ids)) == 4


def test_a_result_with_no_call_before_it_is_never_sent_as_a_tool_message() -> None:
    """Such a message is refused outright by this kind of server. A record
    that cannot be paired is sent the old way, whole."""
    history = a_run()
    turn = next(i for i, m in enumerate(history) if m["role"] == "assistant")

    # Written before arguments were kept.
    older = [dict(m) for m in history]
    del older[turn]["calls"]
    # A result a tidying step removed.
    short = history[: turn + 1] + history[turn + 2 :]
    # A result standing alone.
    alone = [history[0], history[turn + 1]]

    for record in (older, short, alone):
        messages = served().payload_for("", record, [])["messages"]
        assert all(m["role"] != "tool" for m in messages), record
        assert all("tool_calls" not in m for m in messages), record
        assert any("[result of ledger]" in str(m["content"]) for m in messages)


def test_what_a_call_was_given_survives_a_tidying_step() -> None:
    history = a_run()
    again = to_history(from_history(history))
    turn = next(m for m in again if m["role"] == "assistant")
    assert turn["calls"] == [
        {"name": "ledger", "args": {"action": "look", "entry": "rent"}},
        {"name": "ledger", "args": {"action": "look", "entry": "gas"}},
    ]
    assert [m["role"] for m in served().payload_for("", again, [])["messages"]] == [
        "user", "assistant", "tool", "tool",
    ]


def test_a_calls_arguments_count_towards_how_much_the_conversation_holds() -> None:
    """They are sent, so they take room. A record without them is the same
    size it always was."""
    history = a_run()
    older = [{k: v for k, v in m.items() if k != "calls"} for m in history]
    size = lambda record: sum(p.sized() for m in from_history(record) for p in m.parts)  # noqa: E731
    assert size(history) > size(older)
    # And they are not something the model SAID.
    assert all("rent" not in m.text() for m in from_history(history) if m.role == "assistant")


# ── a server that refuses a field is asked again ─────────────────────────────


class Server:
    """A `/chat/completions` that refuses what a current hosted model refuses."""

    def __init__(self, *, takes_max_tokens: bool, takes_temperature: bool) -> None:
        self.takes_max_tokens = takes_max_tokens
        self.takes_temperature = takes_temperature
        self.got: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.got.append(body)
        if "max_tokens" in body and not self.takes_max_tokens:
            return self.refuse(
                "Unsupported parameter: 'max_tokens' is not supported with this model. "
                "Use 'max_completion_tokens' instead."
            )
        if "temperature" in body and not self.takes_temperature:
            return self.refuse(
                "Unsupported value: 'temperature' does not support 0.0 with this model. "
                "Only the default (1) value is supported."
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hello."}}]})

    @staticmethod
    def refuse(message: str) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": message}})


@pytest.fixture
def through(monkeypatch: pytest.MonkeyPatch):
    """Send this transport's requests to a `Server` instead of a network."""
    real = httpx.AsyncClient

    def to(server: Server) -> None:
        monkeypatch.setattr(
            httpx, "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(server), **kw),
        )
        monkeypatch.setattr(
            httpx, "post",
            lambda url, **kw: httpx.Client(transport=httpx.MockTransport(server)).post(
                url, **{k: v for k, v in kw.items() if k != "timeout"}
            ),
        )

    return to


def ask(transport: OllamaTransport) -> str:
    text, _ = asyncio.run(transport.model_call("", [{"role": "user", "content": "Hi."}], []))
    return text


def test_a_model_that_wants_the_ceiling_under_another_name_is_given_it(through) -> None:
    server = Server(takes_max_tokens=False, takes_temperature=True)
    through(server)
    transport = served()
    assert ask(transport) == "Hello."
    refused, sent = server.got
    assert "max_tokens" in refused
    # The figure is sent under the name the model takes. It is not dropped.
    assert sent["max_completion_tokens"] == 300 and "max_tokens" not in sent
    # And the next request is right the first time.
    assert ask(transport) == "Hello." and len(server.got) == 3
    assert server.got[-1]["max_completion_tokens"] == 300


def test_a_model_that_takes_neither_is_reached_all_the_same(through) -> None:
    server = Server(takes_max_tokens=False, takes_temperature=False)
    through(server)
    transport = served()
    assert ask(transport) == "Hello."
    assert len(server.got) == 3
    assert "temperature" not in server.got[-1] and server.got[-1]["max_completion_tokens"] == 300
    assert ask(transport) == "Hello." and len(server.got) == 4


def test_a_temperature_the_author_wrote_is_never_dropped(through) -> None:
    """Dropping it would be a setting quietly not applied. The refusal stands."""
    server = Server(takes_max_tokens=True, takes_temperature=False)
    through(server)
    transport = served()
    assert transport.apply_settings({"temperature": 0.2}) == ()
    with pytest.raises(httpx.HTTPStatusError):
        ask(transport)
    assert len(server.got) == 1 and server.got[0]["temperature"] == 0.2


def test_a_ceiling_the_author_wrote_goes_under_the_name_the_model_takes(through) -> None:
    server = Server(takes_max_tokens=False, takes_temperature=True)
    through(server)
    transport = OllamaTransport("some-model", base_url="http://localhost:1/v1")
    assert transport.apply_settings({"max-tokens": 120}) == ()
    assert ask(transport) == "Hello."
    assert server.got[-1]["max_completion_tokens"] == 120 and "max_tokens" not in server.got[-1]
    assert ask(transport) == "Hello."
    assert server.got[-1]["max_completion_tokens"] == 120 and len(server.got) == 3


def test_a_refusal_this_cannot_put_right_is_still_a_refusal(through) -> None:
    def server(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "The model `nope` does not exist."}})

    through(server)  # type: ignore[arg-type]
    with pytest.raises(httpx.HTTPStatusError):
        ask(served())


def test_the_summarising_model_is_asked_again_and_teaches_nothing_about_the_bound_one(through) -> None:
    server = Server(takes_max_tokens=True, takes_temperature=False)
    through(server)
    transport = served()
    assert transport.write_summary("a long conversation", "a-small-model") == "Hello."
    assert [("temperature" in body) for body in server.got] == [True, False]
    # The bound model may take a temperature perfectly well, and is still sent one.
    assert "temperature" in transport.payload_for("", [{"role": "user", "content": "Hi."}], [])
