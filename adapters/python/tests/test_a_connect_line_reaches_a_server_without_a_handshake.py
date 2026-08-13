"""PACT's own MCP client, held to the shape its own requirements demand.

`docs/30-FRD.md` FR-4.1.14 REQUIRES the `2026-07-28` revision — stateless, no
`initialize` handshake, no sessions, the MRTR `input_required` retry in place of
server-initiated requests — and names `2025-11-25` as the shape not to target.
Everything reachable through `pydantic_ai.mcp` is the second one: `pydantic-ai-
slim` pins `fastmcp-slim[client]<4`, that client is MCP SDK v1, and
`MCPToolset.__aenter__` opens a session and awaits an `initialize` result. So a
requirement PACT wrote for itself could not be met by anything PACT already had,
and the consequence of not writing this client is not a missing feature — it is
`pact check` passing a workspace whose `connect:` lines can only be executed over
a protocol shape PACT's own FRD rules out.

**What each half of this file is protecting.**

*The wire.* A handshake, a session id, a missing `MCP-Protocol-Version` header or
a version in the header that disagrees with the one in `_meta` are each, by the
specification's own words, a request a compliant server MUST reject — several of
them with `HeaderMismatch` (-32020) or `-32602`. None of that is visible from a
test that only checks the answer came back, because a fake server that ignores
headers answers happily. So the in-process transport is given the HEADERS as well
as the body, and the assertions are about what went OUT.

*The call.* `examples/refund-desk/tools/payments.yaml` writes *"The only actions
this agent may call. Anything else on the server is refused."* above its
`actions:` block. Nothing on the executing side enforced that sentence: a model
shown `one of look-up-order, issue-refund` that asked for something else would
have had it posted to the payments server. And a PACT tool with actions is ONE
tool with an `action:` argument while an MCP server publishes one tool per
operation, so a client that sent the tool's own name would call a tool no server
has.

*The ruling.* AD-43 — PACT neither launches nor sandboxes a runtime-owned MCP
server. The other thing an MCP endpoint can be is a command to run over stdio,
and starting a process a workspace names is executing its code, which D17 and D23
forbid. `connect:` is CONNECT and never SPAWN, and that has to be a property of
the code rather than a paragraph.

Everything here runs offline, in this process, with no subprocess except the real
Rust loader that produces the authored document — because the question is what an
AUTHOR's tree does, and a document this file wrote would be one it already agrees
with.
"""

from __future__ import annotations

import ast
import json
import socket as _socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consenting import allowing_the_connection  # noqa: E402
from pact_adapters.harness import ToolCall  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.mcp.calling import tool_impls_for  # noqa: E402
from pact_adapters.mcp.client import (  # noqa: E402
    PROTOCOL_VERSION,
    Client,
    NotThisProtocol,
    ServerRefused,
)
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"
SRC = REPO / "adapters" / "python" / "src" / "pact_adapters"
CLIENT = SRC / "mcp"

#: The server the worked example's `payments` tool connects to, and the one its
#: `asks-to-connect: may-we-connect` gates. Spelled out rather than derived, so a
#: tree that renames it has to say so here too.
PAYMENTS = "payments-server"


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    """The worked example through the real Rust loader (invariant P-1)."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture()
def desk(document: dict) -> AgentSpec:
    return AgentSpec.from_document(document, "refund-desk")


class Recorder:
    """An MCP server in this process that answers, and remembers what it was sent.

    The headers are kept as well as the body because half of what this client
    has to get right is only visible there: `MCP-Protocol-Version`, `Mcp-Method`
    and `Mcp-Name` are REQUIRED for compliance and a server that validates them
    rejects the request when any is missing or disagrees with the body.
    """

    def __init__(self, answering=None) -> None:
        self.asked: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self._answering = answering

    def __call__(self, request: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        self.asked.append(request)
        self.headers.append(headers)
        if self._answering is not None:
            return self._answering(request, headers)
        return _complete(request, {"content": [{"type": "text", "text": "ok"}]})

    def client(self, server: str = PAYMENTS) -> Client:
        return Client.in_process(self, server=server)


def _complete(request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request["id"],
        "result": {"resultType": "complete", **result},
    }


def _listing(*tools: dict[str, Any]) -> Any:
    def answer(request, _headers):
        return _complete(request, {"tools": list(tools)})

    return answer


# ───────────────────────────────── the shape FR-4.1.14 requires, on the wire


def test_the_first_thing_ever_said_about_a_server_is_the_request_itself() -> None:
    """No `initialize`, and therefore nothing that could be a session.

    This is the whole of "stateless" in one assertion. SEP-2575 deleted the
    `initialize`/`notifications/initialized` handshake and SEP-2567 deleted
    `Mcp-Session-Id`; a client that opened with either would be speaking
    `2025-11-25`, which is the revision FR-4.1.14 names as the one not to target.

    It matters beyond conformance. A handshake means a connection is a thing that
    must be held open, and a PACT run parks: the whole reason a `connect:` tool
    survives being suspended in one process and resumed in another is that the
    second call is not a continuation of anything.
    """
    server = Recorder(_listing({"name": "issue-refund"}))
    server.client().published_tools()

    assert len(server.asked) == 1, [r["method"] for r in server.asked]
    assert server.asked[0]["method"] == "tools/list"
    said = json.dumps(server.asked)
    for gone in ("initialize", "notifications/initialized", "sessionId", "Mcp-Session-Id"):
        assert gone not in said, f"the client sent `{gone}`, which this revision deleted"
    assert not any(
        "session" in name.lower() for headers in server.headers for name in headers
    ), server.headers


def test_the_version_is_on_the_header_and_in_the_body_and_they_are_the_same() -> None:
    """A mismatch is `HeaderMismatch` (-32020) and a 400, by the spec's own rule.

    The two are required to agree, which is exactly the kind of thing a second
    literal breaks six months later. There is one `PROTOCOL_VERSION` and it is
    read twice; this fails if either place is written by hand.
    """
    server = Recorder()
    server.client().call("issue-refund", {"amount": 40})

    meta = server.asked[0]["params"]["_meta"]
    assert meta["io.modelcontextprotocol/protocolVersion"] == PROTOCOL_VERSION
    assert server.headers[0]["MCP-Protocol-Version"] == PROTOCOL_VERSION
    assert PROTOCOL_VERSION == "2026-07-28", (
        "the client no longer speaks the revision FR-4.1.14 requires — if this "
        "moved on purpose, FR-4.1.14 moved too"
    )


def test_every_request_declares_the_capabilities_a_server_may_rely_on() -> None:
    """`clientCapabilities` is REQUIRED on every request and is empty on purpose.

    A server MUST NOT rely on a capability the client did not declare. Claiming
    `elicitation` here would tell a server it may ask this client for a person's
    input inside a tool call — and it may not: PACT reaches a person by PARKING
    the run, through a question the author wrote, not through a callback in the
    middle of a `tools/call`. `sampling` and `roots` are deprecated in this
    revision and would be worse: a server could ask this process to run a model.
    """
    server = Recorder()
    server.client().call("look-up-order", {})

    meta = server.asked[0]["params"]["_meta"]
    assert meta["io.modelcontextprotocol/clientCapabilities"] == {}, meta
    assert "io.modelcontextprotocol/clientInfo" in meta


def test_the_headers_a_gateway_routes_on_are_the_ones_the_body_says() -> None:
    """`Mcp-Method` on every request and `Mcp-Name` on `tools/call`.

    Both are REQUIRED for compliance, and both are mirrored from the body so an
    intermediary can route without parsing it — which is why a server that
    validates rejects a request whose header and body disagree. Asserted against
    the body rather than against a literal, so a client that mirrored the wrong
    field fails here.
    """
    server = Recorder(_listing({"name": "issue-refund"}))
    client = server.client()
    client.published_tools()
    client.call("issue-refund", {"order-number": "O-9"})

    listed, called = server.asked
    assert server.headers[0]["Mcp-Method"] == listed["method"] == "tools/list"
    assert "Mcp-Name" not in server.headers[0], "`tools/list` names nothing"
    assert server.headers[1]["Mcp-Method"] == called["method"] == "tools/call"
    assert server.headers[1]["Mcp-Name"] == called["params"]["name"] == "issue-refund"


def test_a_name_a_header_cannot_carry_goes_as_the_encoding_the_spec_names() -> None:
    """RFC 9110 allows visible ASCII; anything else MUST be `=?base64?…?=`.

    PACT's own loader holds tool names to lowercase ASCII, so this cannot come
    from a checked workspace — which is exactly why it is worth a test. The name
    on the wire is the ACTION out of a document that may have arrived from
    anywhere, and a header value with a newline in it is a request-smuggling bug
    rather than a formatting one.
    """
    server = Recorder()
    server.client().call("refund\nX-Injected: yes", {})
    said = server.headers[0]["Mcp-Name"]
    assert said.startswith("=?base64?") and said.endswith("?="), said
    assert "\n" not in said


def test_the_accept_header_offers_both_framings_the_client_must_support() -> None:
    """A server MAY answer a single POST with an SSE stream, and the client MUST
    support both. An `Accept` naming only JSON would be this client asking for
    something it is then obliged to accept anyway."""
    server = Recorder()
    server.client().call("issue-refund", {})
    accept = server.headers[0]["Accept"]
    assert "application/json" in accept and "text/event-stream" in accept, accept


# ─────────────────────────────────────────── what a server says it publishes


def test_a_second_page_of_tools_is_not_a_server_that_dropped_them() -> None:
    """`ListToolsResult` is paginated, and a short read is not a small server.

    The consequence is not "some tools are missing". `published_tools` feeds
    `mcp_bridge.check_against_authored`, which reports every authored tool the
    server does not publish — so one unread page turns a healthy server into a
    total-drift report and stops a run that was fine. That is the loudest
    possible way to be wrong.
    """
    pages = {
        "": {"tools": [{"name": "look-up-order"}], "nextCursor": "page-2"},
        "page-2": {"tools": [{"name": "issue-refund"}]},
    }

    def answer(request, _headers):
        return _complete(request, pages[str(request["params"].get("cursor") or "")])

    server = Recorder(answer)
    got = server.client().published_tools()
    assert [t["name"] for t in got] == ["look-up-order", "issue-refund"]
    assert len(server.asked) == 2
    assert server.asked[1]["params"]["cursor"] == "page-2"


def test_a_server_that_repeats_its_cursor_does_not_keep_a_run_waiting() -> None:
    """A page loop with a customer waiting is indistinguishable from a hang, and
    `shown.py`'s own rule says a run must never look hung. The walk stops on a
    cursor it has already followed rather than trusting the server to advance."""
    server = Recorder(
        lambda request, _h: _complete(request, {"tools": [{"name": "x"}], "nextCursor": "same"})
    )
    got = server.client().published_tools()
    assert len(server.asked) == 2, "the client followed the same cursor more than once"
    assert len(got) == 2


def test_what_this_client_lists_is_what_the_drift_check_reads(desk: AgentSpec) -> None:
    """The two halves of the MCP work, joined.

    `mcp_bridge.check_against_authored` is the live half of AD-71 and it has to
    be handed a published tool list by something. This is that something, and if
    the shape it returns were not the shape the check reads, both would pass
    their own tests and neither would ever hold a real server to the review.
    """
    from pact_adapters.mcp_bridge import check_against_authored

    server = Recorder(
        _listing(
            {
                "name": "issue-refund",
                "inputSchema": {
                    "type": "object",
                    "properties": {"order-number": {"type": "string"}},
                },
            }
        )
    )
    published = server.client().published_tools()
    payments = next(t for t in desk.tools if t.name == "payments")

    found = check_against_authored(
        published, {"issue-refund": {"order-number": "text", "amount": "money"}}
    )
    assert any("`amount`" in said for said in found), found
    assert payments.reaches is not None and payments.reaches.value == PAYMENTS


# ────────────────────────────────────────── what one call can come back as


def test_a_result_that_names_no_type_is_a_completed_call() -> None:
    """*"Clients MUST treat an absent `resultType` as `complete`."*

    For servers still on an earlier revision. Reading the absence as "not
    complete" would turn every answer such a server ever gives into a request for
    input nobody asked for, which is a working integration that reports itself as
    permanently stuck.
    """
    server = Recorder(
        lambda request, _h: {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"content": [{"type": "text", "text": "sent 40 USD"}]},
        }
    )
    called = server.client().call("issue-refund", {"amount": 40})
    assert called.complete and called.text == "sent 40 USD"


def test_a_result_type_this_client_cannot_read_is_never_read_as_an_answer() -> None:
    """*"A `resultType` of any value unrecognized by the client MUST be
    considered invalid."*

    An extension's result type has its own fields and its own meaning. Handing
    whatever happened to be in `content` to the model as the outcome would report
    something that did not happen — and for `payments`, that is a refund reported
    as issued.
    """
    server = Recorder(
        lambda request, _h: {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"resultType": "io.example/deferred", "content": []},
        }
    )
    with pytest.raises(NotThisProtocol) as refused:
        server.client().call("issue-refund", {"amount": 40})
    assert "io.example/deferred" in str(refused.value)


def test_a_tool_that_failed_at_the_server_is_data_and_not_a_crash() -> None:
    """MCP puts a tool's own failure in the RESULT, *"otherwise the LLM would not
    be able to see that an error occurred and self-correct"* — which is the same
    rule `harness._call_tool` states for a tool that raises. So `isError` is read
    and carried, and the model is told in the vocabulary the harness already uses.
    """
    server = Recorder(
        lambda request, _h: _complete(
            request,
            {"content": [{"type": "text", "text": "card expired"}], "isError": True},
        )
    )
    called = server.client().call("issue-refund", {"amount": 40})
    assert called.is_error and called.text == "card expired"


def test_an_answer_about_another_request_is_not_this_calls_result() -> None:
    """One POST, one answer — nothing here is multiplexed.

    An id that does not match means the server replied about a different
    request, and reading it as this one's would report an order lookup's outcome
    as a refund's. A broken stream is re-issued as a NEW request by this
    revision's own rule, so a stale answer arriving under an old id is a real
    shape and not a hypothetical.
    """
    server = Recorder(
        lambda request, _h: _complete({"id": request["id"] + 1000}, {"content": []})
    )
    with pytest.raises(NotThisProtocol):
        server.client().call("issue-refund", {"amount": 40})


def test_a_server_that_refuses_says_which_server_and_why() -> None:
    """A JSON-RPC error is a refusal to report, not an empty result to pass on.

    Named with the server, because a host with four connections needs to know
    which one said no.
    """
    server = Recorder(
        lambda request, _h: {
            "jsonrpc": "2.0",
            "id": request["id"],
            "error": {"code": -32021, "message": "elicitation capability required"},
        }
    )
    with pytest.raises(ServerRefused) as refused:
        server.client().call("issue-refund", {"amount": 40})
    said = str(refused.value)
    assert PAYMENTS in said and "elicitation capability required" in said


def test_an_answer_framed_as_a_stream_is_still_an_answer() -> None:
    """The client MUST support both framings of a reply to one POST.

    It advertises both in `Accept`, so a server that chooses `text/event-stream`
    has been invited to — and a client that then could not read it would fail
    every call to that server while claiming on every request that this was fine.
    """
    server = Recorder(
        lambda request, _h: _complete(request, {"content": [{"type": "text", "text": "sent"}]})
    )
    streaming = Client.in_process(server, server=PAYMENTS, media="text/event-stream")
    assert streaming.call("issue-refund", {"amount": 40}).text == "sent"


def test_content_this_run_cannot_show_is_named_rather_than_dropped() -> None:
    """A tool that answered with an image and a client that returned `""` would
    tell the run the call produced nothing — the silent degradation T7 forbids,
    landing in the one place the model's next turn is written from."""
    server = Recorder(
        lambda request, _h: _complete(
            request,
            {"content": [{"type": "image", "data": "…", "mimeType": "image/png"}]},
        )
    )
    said = server.client().call("look-up-order", {}).text
    assert said and "image" in said


def test_a_result_with_only_structure_is_still_something_the_model_can_read() -> None:
    """`structuredContent` with no `content` is a legal result, and an empty
    string for it would read as a call that answered nothing."""
    server = Recorder(
        lambda request, _h: _complete(request, {"content": [], "structuredContent": {"paid": 40}})
    )
    called = server.client().call("issue-refund", {"amount": 40})
    assert json.loads(called.text) == {"paid": 40}
    assert called.structured == {"paid": 40}


# ─────────────────────────────────── MRTR, which replaced every server request


def test_a_server_that_needs_more_is_not_reported_as_a_call_that_happened() -> None:
    """`input_required` is the whole of the HITL shape in this revision.

    Server-initiated requests are gone — a server that needs a person answers
    `input_required` and waits to be asked again. A client that read that result
    as complete would hand the model the empty `content` beside it, and the run
    would carry on believing a refund was issued that the server has not even
    started.
    """
    server = Recorder(
        lambda request, _h: {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "resultType": "input_required",
                "inputRequests": {
                    "confirm": {
                        "method": "elicitation/create",
                        "params": {"mode": "form", "message": "Confirm the refund"},
                    }
                },
                "requestState": "opaque-abc",
            },
        }
    )
    called = server.client().call("issue-refund", {"amount": 40})
    assert not called.complete
    assert called.text == ""
    assert set(called.needs) == {"confirm"}
    assert called.request_state == "opaque-abc"


def test_the_retry_carries_the_answers_the_state_and_a_new_request_id() -> None:
    """MRTR is *retry the original request*, not resume a conversation.

    Three things have to be true at once and each was mutated out to check that
    something fails: the answers go under the SERVER's own keys, `requestState`
    goes back untouched (the client MUST NOT inspect or modify it), and the retry
    is a NEW request with a NEW id — this revision deletes stream resumability
    and says a lost request MUST be re-issued with a new request ID.
    """
    asked: list[dict[str, Any]] = []

    def answer(request, _headers):
        asked.append(request)
        if len(asked) == 1:
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "resultType": "input_required",
                    "inputRequests": {"confirm": {"method": "elicitation/create"}},
                    "requestState": "opaque-abc",
                },
            }
        return _complete(request, {"content": [{"type": "text", "text": "sent 40 USD"}]})

    client = Client.in_process(answer, server=PAYMENTS)
    first = client.call("issue-refund", {"amount": 40})
    second = client.call(
        "issue-refund",
        {"amount": 40},
        answers={"confirm": {"action": "accept", "content": {}}},
        request_state=first.request_state,
    )

    assert second.complete and second.text == "sent 40 USD"
    retry = asked[1]["params"]
    assert retry["inputResponses"] == {"confirm": {"action": "accept", "content": {}}}
    assert retry["requestState"] == "opaque-abc"
    assert retry["arguments"] == {"amount": 40}, "the ORIGINAL request, retried"
    assert asked[1]["id"] != asked[0]["id"], (
        "the retry reused the request id the server has already answered"
    )


def test_a_host_that_can_answer_is_asked_and_a_host_that_cannot_is_not_invented(
    desk: AgentSpec,
) -> None:
    """The same wait, through the `ToolFn` a harness would call.

    With no answerer the model is told the server is waiting and that nothing has
    happened — `not done:`, the word the harness already uses for a call that was
    decided rather than attempted. With one, the retry happens and the model
    reads the result. What must never happen is the middle: an answer this
    process made up for a question a server asked a person.
    """
    rounds: list[dict[str, Any]] = []

    def answer(request, _headers):
        rounds.append(request)
        if "inputResponses" not in request["params"]:
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "resultType": "input_required",
                    "inputRequests": {"confirm": {"method": "elicitation/create"}},
                    "requestState": "s-1",
                },
            }
        return _complete(request, {"content": [{"type": "text", "text": "sent 40 USD"}]})

    clients = {PAYMENTS: Client.in_process(answer, server=PAYMENTS)}
    refund = {"action": "issue-refund", "order-number": "O-9", "amount": 40}

    silent = tool_impls_for(desk, clients)["payments"](dict(refund))
    assert silent.startswith("not done:"), silent
    assert "confirm" in silent and PAYMENTS in silent
    assert len(rounds) == 1, "a host with no answerer still retried"

    rounds.clear()
    answering = tool_impls_for(
        desk, clients, answer_input=lambda key, asked: {"action": "accept", "content": {}}
    )
    assert answering["payments"](dict(refund)) == "sent 40 USD"
    assert len(rounds) == 2


def test_a_server_that_keeps_asking_does_not_keep_a_run_alive_forever(
    desk: AgentSpec,
) -> None:
    """`input_rounds` is a ceiling, and an unbounded retry loop would be one
    nobody wrote: a server able to answer `input_required` forever would hold a
    run open past every limit the author did set."""
    rounds: list[dict[str, Any]] = []

    def answer(request, _headers):
        rounds.append(request)
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "resultType": "input_required",
                "inputRequests": {"confirm": {}},
                "requestState": "s",
            },
        }

    impls = tool_impls_for(
        desk,
        {PAYMENTS: Client.in_process(answer, server=PAYMENTS)},
        answer_input=lambda key, asked: {"action": "accept"},
        input_rounds=2,
    )
    said = impls["payments"]({"action": "issue-refund", "order-number": "O-9", "amount": 40})
    assert said.startswith("not done:"), said
    assert len(rounds) == 3, f"one first call plus two bounded retries, got {len(rounds)}"


# ────────────────────────── the author's own lines, reaching the actual call


def test_the_action_the_author_wrote_becomes_the_tool_the_server_publishes(
    desk: AgentSpec,
) -> None:
    """A PACT tool with `actions:` is ONE tool with an `action:` argument
    (`ir._takes`); an MCP server publishes one tool per operation.

    So `payments` + `action: issue-refund` is `tools/call` for `issue-refund`,
    and `action` is not an argument — it is PACT's way of naming which call this
    is. A client that sent `payments` would call a tool the server does not have;
    one that left `action` in `arguments` would send the server a property its
    own `inputSchema` never declared, which is a rejected call at best.
    """
    server = Recorder()
    impls = tool_impls_for(desk, {PAYMENTS: server.client()})
    impls["payments"](
        {"action": "issue-refund", "order-number": "O-9", "amount": 40, "customer-id": "C-9"}
    )

    params = server.asked[0]["params"]
    assert params["name"] == "issue-refund"
    assert "action" not in params["arguments"], params["arguments"]
    assert params["arguments"] == {
        "order-number": "O-9",
        "amount": 40,
        # The `bind:` line. `tools/payments.yaml` writes `bind: {customer-id:
        # run-inputs.customer-id}`, the harness merges it before the tool is
        # reached, and measured before that existed the call arrived without it —
        # so the identity of whoever the run was for never reached the server.
        "customer-id": "C-9",
    }


def test_an_action_the_author_never_declared_never_leaves_this_process(
    desk: AgentSpec,
) -> None:
    """`tools/payments.yaml`: *"The only actions this agent may call. Anything
    else on the server is refused."*

    Until this client that sentence was enforced by nothing on the executing
    side. The model is shown `one of look-up-order, issue-refund`; a model that
    asked for anything else would have had it posted to the payments server, and
    whether it worked would have been the server's business rather than the
    author's. Nothing is sent, which is the assertion that matters — a refusal
    after the POST is not a refusal.
    """
    server = Recorder()
    impls = tool_impls_for(desk, {PAYMENTS: server.client()})
    said = impls["payments"]({"action": "delete-account", "order-number": "O-9"})

    assert server.asked == [], "an undeclared action reached the server"
    assert said.startswith("not done:"), said
    assert "delete-account" in said and "issue-refund" in said


def test_a_call_that_does_not_say_which_action_it_is_is_not_guessed_at(
    desk: AgentSpec,
) -> None:
    """A model that omits the argument it was shown is a normal Tuesday.

    "There is only one plausible action, it must be that one" would post a refund
    because nobody said not to.
    """
    server = Recorder()
    impls = tool_impls_for(desk, {PAYMENTS: server.client()})
    said = impls["payments"]({"order-number": "O-9", "amount": 40})
    assert server.asked == []
    assert said.startswith("not done:") and "action" in said


def test_a_tool_whose_server_has_no_client_is_absent_and_not_a_stub(
    desk: AgentSpec,
) -> None:
    """The at-most-once ledger is why this is absence rather than an apology.

    `harness.run` reads `call.name in tool_impls` to decide whether a call CAN
    run, and `Ledger.hold` claims a `same-request-key:` BEFORE the tool is
    reached — deliberately, because a call that ran and then timed out may still
    have moved money. A stub that accepted the call and answered *"no client for
    this server"* would spend `order-number` for a call that provably did
    nothing, and the model's next turn would read that the refund already ran.
    """
    impls = tool_impls_for(desk, {})
    assert impls == {}

    only_one = tool_impls_for(desk, {PAYMENTS: Recorder().client()})
    assert set(only_one) == {"payments"}, (
        "`zendesk` reaches `zendesk-server`, which was not among the clients"
    )


def test_a_tool_that_reaches_somewhere_other_than_a_server_is_left_alone() -> None:
    """`url:` and `says:` are the other two ways a tool reaches
    (`ir.WAYS_A_TOOL_REACHES`) and neither is an MCP server. A reader that
    assumed `connect:` would post a refund to a server nobody wrote down."""
    spec = AgentSpec.from_document(
        {
            "agents": {"a": {"uses": ["fetch", "payments"]}},
            "tools": {
                "fetch": {"url": "https://example.test/x", "method": "get"},
                "payments": {"connect": PAYMENTS},
            },
            "resources": {PAYMENTS: {"resource-kind": "mcp-server", "endpoint": "host/p"}},
        },
        "a",
    )
    impls = tool_impls_for(spec, {PAYMENTS: Recorder().client(), "fetch": Recorder().client()})
    assert set(impls) == {"payments"}


def test_a_tool_with_no_actions_is_called_by_its_own_name() -> None:
    """The other half of the action rule, and the one that fails silently.

    A tool with no `actions:` block IS the operation, so its own name is what the
    server publishes. A client that always looked for an `action` argument would
    refuse every call to every such tool with a sentence about a line the author
    never wrote.
    """
    spec = AgentSpec.from_document(
        {
            "agents": {"a": {"uses": ["ping"]}},
            "tools": {"ping": {"connect": "ops", "description": "check"}},
            "resources": {"ops": {"resource-kind": "mcp-server", "endpoint": "host/ops"}},
        },
        "a",
    )
    server = Recorder()
    tool_impls_for(spec, {"ops": server.client("ops")})["ping"]({"host": "db-1"})
    assert server.asked[0]["params"] == {
        "name": "ping",
        "arguments": {"host": "db-1"},
        "_meta": server.asked[0]["params"]["_meta"],
    }


def test_the_harness_runs_the_call_and_the_model_reads_what_the_server_said(
    desk: AgentSpec,
) -> None:
    """The whole thing, end to end, through `harness.run(tool_impls=…)`.

    Every other test here could pass with a `ToolFn` no harness can use. This one
    asserts what the run DID: the payments server received one `tools/call` for
    `issue-refund` with the author's arguments and the bound `customer-id`, and
    the words the server answered are the words in the step's `tool_results` —
    which is what the model is shown on its next turn and therefore what the
    customer is told.

    The run parks once first, because `resources/payments-server.yaml` says a
    person is asked before this desk uses that connection. That park is the
    example doing exactly what it says, and it is also the reason
    `harness.run` may never hold a client of its own: the consent is decided in
    the loop, and the connection is opened outside it.
    """
    server = Recorder(
        lambda request, _h: _complete(
            request, {"content": [{"type": "text", "text": "refunded 40 USD to C-9"}]}
        )
    )
    impls = tool_impls_for(desk, {PAYMENTS: server.client()})

    def script() -> Script:
        return Script(
            [
                Turn(
                    "Refunding.",
                    (
                        ToolCall(
                            "payments",
                            {"action": "issue-refund", "order-number": "O-9", "amount": 40},
                        ),
                    ),
                ),
                Turn("Done."),
            ]
        )

    out = allowing_the_connection(
        desk,
        lambda: ReferenceTransport(script()),
        "refund O-9",
        impls,
        run_inputs={"customer-id": "C-9"},
    )

    assert out.halted == "final", out.halted
    assert len(server.asked) == 1, [r["params"]["name"] for r in server.asked]
    assert server.asked[0]["params"]["name"] == "issue-refund"
    assert server.asked[0]["params"]["arguments"]["customer-id"] == "C-9"
    said = [r for step in out.steps for r in step.tool_results]
    assert "refunded 40 USD to C-9" in said, said


# ───────────────────────────── CONNECT never SPAWN, and the box with no wire


def test_an_address_that_is_a_command_is_refused_naming_the_ruling() -> None:
    """AD-43: PACT neither launches nor sandboxes a runtime-owned MCP server.

    The other thing an MCP endpoint can be is a command over stdio, and starting
    a process a workspace names is executing its code — which D17 and D23 forbid,
    because reviewing an untrusted tree may never be an act of running it. The
    refusal is at the one place an address becomes bytes, so it holds for every
    caller rather than for the ones who remembered.
    """
    for spawning in ("npx -y @acme/payments-mcp", "stdio:///usr/bin/payments", "./server.sh"):
        with pytest.raises(ValueError) as refused:
            Client.over_http(spawning, server=PAYMENTS)
        said = str(refused.value)
        assert "AD-43" in said and "fix:" in said, said

    # And the shape that IS allowed, so the refusal is not simply "everything".
    assert Client.over_http("https://payments.example/mcp", server=PAYMENTS).server == PAYMENTS


def test_nothing_in_this_client_can_start_a_process() -> None:
    """The property, rather than the promise.

    A `connect:` line that could reach `subprocess` is stdio MCP with extra
    steps, and the refusal above would be one `if` somebody removes. This asks
    the source instead: no import that can spawn, anywhere in the package.
    """
    forbidden = {"subprocess", "multiprocessing", "pty", "os", "shutil", "signal"}
    found: dict[str, list[str]] = {}
    for path in sorted(CLIENT.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            named: list[str] = []
            if isinstance(node, ast.Import):
                named = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                named = [node.module.split(".")[0]]
            for name in named:
                if name in forbidden:
                    found.setdefault(path.name, []).append(name)
    assert not found, f"a module that can launch a process: {found}"


def test_this_client_is_independent_of_the_pin_that_forbids_the_shape() -> None:
    """The entire reason this exists separately from the export path.

    `pydantic-ai-slim` pins `fastmcp-slim[client]<4`, which is MCP SDK v1, whose
    `LATEST_PROTOCOL_VERSION` is `2025-11-25` and whose toolset opens a session.
    One import of any of them here and PACT's own client inherits the revision
    its own FRD rules out — through a version pin in somebody else's extra, where
    nothing in this repository could see it move.
    """
    pinned = {"pydantic_ai", "fastmcp", "mcp"}
    found: dict[str, list[str]] = {}
    for path in sorted(CLIENT.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            named = []
            if isinstance(node, ast.Import):
                named = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                named = [node.module.split(".")[0]]
            found.setdefault(path.name, []).extend(n for n in named if n in pinned)
    assert not any(found.values()), f"the client imports the pin it exists to avoid: {found}"


def test_nothing_opens_the_network_stack_at_import() -> None:
    """The air-gap, structurally.

    `urllib` and `http` are imported inside the function that posts, so a machine
    that never connects to anything never loads them — and, more to the point, a
    module that reached for the network at import could not be imported at all on
    the box PACT is for. The sibling assertion below is the behavioural half.
    """
    network = {"urllib", "http", "socket", "ssl"}
    at_module_level: dict[str, list[str]] = {}
    for path in sorted(CLIENT.glob("*.py")):
        for node in ast.parse(path.read_text()).body:
            named = []
            if isinstance(node, ast.Import):
                named = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                named = [node.module.split(".")[0]]
            at_module_level.setdefault(path.name, []).extend(n for n in named if n in network)
    assert not any(at_module_level.values()), at_module_level


def test_a_whole_run_happens_on_a_machine_with_no_socket_at_all(
    desk: AgentSpec, monkeypatch
) -> None:
    """D17, measured rather than asserted in prose.

    Not a promise, a property: any attempt to open a connection anywhere below
    fails this test outright. It is the same seam
    `test_metrics_an_expert_brings.py` uses on the provider layer, pointed at the
    one module in this package whose entire subject is talking to something else.
    """
    monkeypatch.setattr(
        _socket, "socket", lambda *a, **k: pytest.fail("nothing here may open a socket")
    )
    def answer(request, _headers):
        if request["method"] == "tools/list":
            return _complete(request, {"tools": [{"name": "look-up-order"}]})
        return _complete(request, {"content": [{"type": "text", "text": "ok"}]})

    server = Recorder(answer)
    client = server.client()
    assert [t["name"] for t in client.published_tools()] == ["look-up-order"]
    impls = tool_impls_for(desk, {PAYMENTS: client})
    assert impls["payments"]({"action": "look-up-order", "order-number": "O-9"}) == "ok"


def test_the_run_path_did_not_gain_a_client(desk: AgentSpec) -> None:
    """Invariant P-1, and the reason `tool_impls` is the seam.

    PACT's own harness parks on a connection; it does not open one. If `harness`
    ever imported this package, the loop would be reaching past its own gate to
    the thing the gate guards — and the consent in
    `resources/payments-server.yaml` would be decided after the socket was open.
    """
    imported: set[str] = set()
    for node in ast.walk(ast.parse((SRC / "harness.py").read_text())):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "mcp" not in imported, "`harness.py` imports the MCP package"

    # And nothing in `src/` does, either, except the client's own package.
    #
    # Asked of the IMPORTS and not of the text, for the same reason the half
    # above is: a run reaches a server by importing something that opens a
    # socket, and a sentence about the client opens nothing. Grepping the raw
    # text failed on `transports/mock.py`, whose lattice comment EXPLAINS why its
    # `connected_tools` word is `emulated` by naming `mcp.calling.tool_impls_for`
    # — a comment doing exactly what this repository asks comments to do, marked
    # as a P-1 breach. A checker that punishes an accurate explanation teaches
    # people to stop writing them.
    reaching: list[str] = []
    for p in SRC.rglob("*.py"):
        if p.parent == CLIENT:
            continue
        # PACT's OWN client package only. `pydantic_ai.mcp` is a different thing
        # and `mcp_bridge.py` is allowed to import it — that is the export path,
        # where the SDK owns the connection. What P-1 forbids is the run path
        # reaching for `pact_adapters/mcp/`, so the match is anchored to that
        # package by both spellings it can arrive under: the relative one a
        # sibling module writes (`from .mcp...`, level >= 1) and the absolute one.
        pact_client = False
        for node in ast.walk(ast.parse(p.read_text(errors="ignore"))):
            if isinstance(node, ast.Import):
                pact_client |= any(
                    a.name == "pact_adapters.mcp" or a.name.startswith("pact_adapters.mcp.")
                    for a in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                relative = (node.level or 0) >= 1 and (
                    node.module == "mcp" or node.module.startswith("mcp.")
                )
                absolute = node.module == "pact_adapters.mcp" or node.module.startswith(
                    "pact_adapters.mcp."
                )
                pact_client |= relative or absolute
        if pact_client:
            reaching.append(str(p.relative_to(SRC)))
    assert not reaching, reaching


def test_the_client_is_not_a_tenth_thing_that_binds_a_model() -> None:
    """Why this is `pact_adapters/mcp/` and not `pact_adapters/transports/`.

    A `transports/` entry binds a MODEL — `harness.Transport` is a `Protocol`
    whose members are `lattice()` and `model_call()` — and
    `test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py` counts that folder
    because the count means *"this many things bind a model"*. Filing an MCP
    client there would put a tenth entry on a list about the other thing, and the
    usage matrix in register row C5 would be reporting a figure over a set that
    had quietly changed subject.
    """
    assert CLIENT.is_dir() and CLIENT.parent == SRC
    assert not (SRC / "transports" / "mcp").exists()
    source = "\n".join(p.read_text() for p in CLIENT.glob("*.py"))
    assert "def model_call" not in source and "def lattice" not in source
