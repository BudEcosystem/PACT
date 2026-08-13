"""PACT's own MCP client, at the `2026-07-28` STATELESS shape (M5 W3).

`docs/30-FRD.md` FR-4.1.14 does not express a preference. It REQUIRES the
`2026-07-28` revision — no `initialize` handshake, no sessions, the MRTR
`input_required` retry in place of server-initiated requests — and names
`2025-11-25`, the shape in the corpus, as the one not to target. Sampling, Roots,
Logging and DCR are deprecated there and are absent here.

## Why this is a client of PACT's own and not a call into somebody else's

`pydantic_ai.mcp.MCPToolset` is the obvious thing to build on and it is the one
thing that cannot be built on. `pydantic-ai-slim` pins `fastmcp-slim[client]<4`
on its `mcp` extra; that is FastMCP 3, which is MCP SDK v1, whose
`LATEST_PROTOCOL_VERSION` is the literal string `2025-11-25` and whose
`__aenter__` opens a session and awaits an `initialize` result. Every one of
those is a thing FR-4.1.14 rules out, and none of them is PACT's to change: they
arrive through a version pin in a dependency's extra.
`test_the_mcp_export_says_which_shape_it_speaks.py` states that tolerance for the
EXPORT path, where Pydantic AI owns the connection in its own process. It is not
tolerable for a connection PACT itself opens, and being independent of that pin
is the entire reason this module exists separately from the export.

## Why `pact_adapters/mcp/` and not `pact_adapters/transports/`

A `transports/` entry binds a MODEL: `harness.Transport` is a `Protocol` whose
members are `lattice()` and `model_call()`, and
`test_a_remote_agents_bill_is_not_a_ceiling_we_hold.py` counts the files in that
folder because the count means *"this many things bind a model"*. An MCP client
binds a TOOL and has no `model_call` at all, so filing it there would put a
tenth entry on a list whose whole meaning is the other thing — and would make the
usage matrix in `docs/70-PRODUCTION-GAP-REGISTER.md` row C5 report a figure over
a set that had quietly changed subject.

## Why nothing on the run path imports this

Invariant P-1 and AD-43. PACT neither launches nor sandboxes a runtime-owned MCP
server, so `connect:` is never SPAWN: there is no stdio subprocess here, no
command, no argv, because launching a process named by a workspace is code
execution and D17/D23 forbid reviewing an untrusted tree by running it. What
PACT's own harness does with a connection is PARK on it — the consent is a
`Rule` in the gate — so a caller inside `run()` would be the loop reaching past
its own gate to the thing the gate guards. A HOST builds these clients and hands
`mcp.calling.tool_impls_for(...)` to `harness.run(tool_impls=…)`, which is the
seam the harness already has.

## Why the standard library and no dependency at all

The whole of this wire is: POST a JSON object, read a JSON object. `http.client`
and `urllib.request` do that, and choosing them means there is no optional
distribution to be absent — so there is no `why_no_mcp`-shaped sentence to write
here, because on the air-gapped box PACT is for, the answer is never *"install
something"*. That is a stronger position than the one `mcp_bridge.why_no_mcp`
has to take, and it is available only because the `2026-07-28` shape deleted the
session machinery that made an SDK worth having. The import is still made INSIDE
the function that posts, both because nothing may open a socket at import (the
air-gap is asserted behaviourally, by taking `socket.socket` away) and because
an in-process run must never so much as load the HTTP stack.

**Deliberately not implemented, and said here rather than discovered:**
`Mcp-Param-{Name}` headers from the `x-mcp-header` schema extension. They are
routing metadata a server annotates onto its own published `inputSchema`, so
sending them needs the published schema at call time, and what PACT holds at call
time is the AUTHORED `takes:` block. `mcp_bridge.check_against_authored` is where
the two are held against each other; inventing a third opinion here would be a
second place that decides what an argument means.
"""

from __future__ import annotations

import base64
import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping

__all__ = [
    "Called",
    "Client",
    "NotThisProtocol",
    "PROTOCOL_VERSION",
    "Posts",
    "ServerRefused",
]

#: The one revision this client speaks, on the header AND in every request's
#: `_meta`. The two MUST agree — a server that sees them differ rejects the
#: request with `HeaderMismatch` (-32020) — so they are one name read twice
#: rather than two literals somebody keeps in step.
PROTOCOL_VERSION = "2026-07-28"

#: One exchange, reduced to the only two things this client needs from whatever
#: carries it: the bytes and headers that went out, and the media type and bytes
#: that came back.
#:
#: A callable and not a class, so that "an MCP server running inside this
#: process" and "an MCP server across a network" are the same shape to
#: everything above. The media type is returned rather than sniffed because the
#: transport spec lets a server answer a single POST with either
#: `application/json` or `text/event-stream` and says the client MUST support
#: both — guessing from the first byte would be this module deciding what the
#: server meant.
Posts = Callable[[bytes, Mapping[str, str]], "tuple[str, bytes]"]


class ServerRefused(RuntimeError):
    """The server answered, and its answer was *no*.

    A JSON-RPC error response, an HTTP status with nothing in the body, or a
    host that could not be reached at all. Separate from [`NotThisProtocol`]
    because the two want different fixes: this one is somebody else's server
    saying something, and that one is this client and that server disagreeing
    about what the words mean.
    """


class NotThisProtocol(RuntimeError):
    """The answer is not a `2026-07-28` result this client can read.

    Raised rather than papered over, and that is the decision. A client that
    shrugged at an unreadable answer would hand the model an empty tool result,
    which reads as *"the tool ran and returned nothing"* — a call that may have
    moved money, reported to the run as a quiet success. An `UnsupportedProtocol
    VersionError` from a server that speaks only `2025-11-25` arrives here, which
    is the whole point of pinning one version: the mismatch is a sentence a host
    can act on rather than a handshake that silently negotiates down.
    """


@dataclass(frozen=True)
class Called:
    """What one `tools/call` produced.

    `resultType` is polymorphic in this revision, so the two outcomes are two
    fields rather than one string a caller has to remember to check: a result
    that is not `complete` is the MRTR pattern asking for more, and treating it
    as an answer is exactly the failure the `complete` flag exists to make
    impossible.
    """

    #: The `content` blocks as one piece of text — what the model reads next.
    text: str = ""
    #: The server's own `isError`. NOT an exception: the MCP spec says a tool's
    #: own failure belongs in the result *"otherwise the LLM would not be able to
    #: see that an error occurred and self-correct"*, which is the same rule
    #: `harness._call_tool` states for a tool that raises.
    is_error: bool = False
    #: `structuredContent`, whatever JSON it is, untouched.
    structured: Any = None
    #: True unless the server said `input_required`. An absent `resultType` is
    #: `complete` — the spec requires that of clients, for servers on earlier
    #: revisions.
    complete: bool = True
    #: The server's `inputRequests`: its keys are ITS identifiers and the values
    #: are what it wants (an `elicitation/create`, and — until they are removed —
    #: a deprecated `sampling/createMessage` or `roots/list`). Empty on a
    #: complete result, and possibly empty on an incomplete one: both fields of
    #: an `InputRequiredResult` are optional, which is why `complete` is what
    #: decides and this is only what to do about it.
    needs: Mapping[str, Any] = field(default_factory=dict)
    #: `requestState` — opaque, and the spec says clients MUST NOT inspect,
    #: parse, modify or assume anything about it. It is carried back on the
    #: retry unchanged and read by nothing here.
    request_state: str = ""


@dataclass(frozen=True)
class Client:
    """One MCP server, spoken to statelessly.

    No connection is held, because there is nothing to hold: `2026-07-28`
    deleted `initialize`, `notifications/initialized` and `Mcp-Session-Id`, and
    moved the protocol version and the client's capabilities into `_meta` on
    every single request. So this object is not a session — it is an address, a
    credential the host already resolved, and the identity to declare. Two
    calls made a week apart are the same two calls made back to back, which is
    what makes a parked-and-resumed PACT run able to make the second one in a
    different process.
    """

    #: Where the bytes go. Built by [`over_http`] or [`in_process`].
    post: Posts
    #: The key in `resources:` — what the tool's `connect:` line named. Carried
    #: for the sentences a failure produces, so a run with four servers says
    #: WHICH one refused. Never used to look anything up.
    server: str = ""
    #: `io.modelcontextprotocol/clientInfo`. Display, logging and debugging only:
    #: the spec says implementations SHOULD NOT change behaviour on it and SHOULD
    #: NOT rely on it for security decisions, so it is not a second identity and
    #: nothing here reads it back.
    client_name: str = "pact"
    client_version: str = "0.1.0"
    #: Request ids, which MUST be unique among requests this sender has issued
    #: and not yet had an answer to. A counter and not a constant, because the
    #: MRTR retry is *"a new request with a new request ID"* by the spec's own
    #: words — a client that reused the id would be re-sending the request the
    #: server already answered.
    _ids: "Iterator[int]" = field(
        default_factory=lambda: itertools.count(1), compare=False, repr=False
    )

    # ───────────────────────────────────────────────────── how to reach one

    @classmethod
    def over_http(
        cls,
        address: str,
        *,
        server: str = "",
        credential: str = "",
        timeout: float = 30.0,
    ) -> "Client":
        """A client for an address the HOST resolved, over one POST per message.

        `address` is what the host answered for the workspace's `endpoint:`
        reference, and `credential` what it answered for `auth.by-reference:`.
        Neither is ever read out of the tree: `endpoint:` is *"a name your
        platform team publishes"* and the schema refuses `bearer-token:` by name,
        so both arrive here from outside and PACT holds a secret only inside the
        closure below — not on this object, not in a message, not in a log.

        **An address that is not `http://` or `https://` is refused, and that
        refusal is AD-43.** The one other thing an MCP endpoint can be is a
        command to launch over stdio, and PACT neither launches nor sandboxes a
        runtime-owned server: a workspace naming a process to start would make
        reviewing an untrusted tree an act of running its code, which D17 and D23
        forbid. So `connect:` is CONNECT and never SPAWN, and the refusal is here
        — at the one place an address turns into bytes — rather than left as a
        sentence in a document.

        `ValueError` and not one of this module's own errors, because this
        happens where a host builds a client, before any run: it is an argument
        that is wrong, reported to the person who can change it, and not an
        outcome for a model to read.
        """
        said = str(address or "").strip()
        if not said.lower().startswith(("http://", "https://")):
            raise ValueError(
                f"{said!r} is not an address this client can post to. PACT speaks "
                f"MCP over HTTP and will not start a process for a `connect:` "
                f"line — launching a command a workspace names is running its "
                f"code, which is the one thing reviewing a tree may never be "
                f"(AD-43, D17, D23). fix: ask your platform team for the "
                f"`http://` or `https://` endpoint this machine publishes for "
                f"this server, or run the server yourself and give this its URL."
            )

        def _post(body: bytes, headers: Mapping[str, str]) -> "tuple[str, bytes]":
            # Imported HERE, not at module level. Nothing may open a socket at
            # import — the air-gap is asserted behaviourally elsewhere in this
            # suite by replacing `socket.socket` with a failure — and an
            # in-process run must not so much as load the HTTP stack.
            import urllib.error
            import urllib.request

            sending = urllib.request.Request(
                said, data=body, headers=dict(headers), method="POST"
            )
            try:
                with urllib.request.urlopen(sending, timeout=timeout) as answered:
                    return (answered.headers.get_content_type(), answered.read())
            except urllib.error.HTTPError as status:
                # The body is READ rather than discarded, and this is the line
                # that makes a version mismatch legible. `2026-07-28` returns
                # `UnsupportedProtocolVersionError`, `MissingRequiredClient
                # CapabilityError` and `HeaderMismatch` as JSON-RPC errors under
                # HTTP 400 — so a client that raised on the status alone would
                # turn *"I speak these versions instead"* into *"HTTP Error
                # 400"*, and the one answer that says how to fix it is the one
                # it threw away.
                carried = status.read() or b""
                if not carried.strip():
                    raise ServerRefused(
                        f"the server for `{server or said}` answered HTTP "
                        f"{status.code} with an empty body, so it did not say "
                        f"what it objected to."
                    ) from None
                media = status.headers.get_content_type() if status.headers else ""
                return (media or "application/json", carried)
            except urllib.error.URLError as unreachable:
                # The address is named and the credential is not. A host with
                # four servers needs to know which one it cannot reach; nobody
                # ever needs the secret in a message.
                raise ServerRefused(
                    f"nothing answered at the address this host resolved for "
                    f"`{server or 'this server'}`: {unreachable.reason}"
                ) from None

        return cls(post=_post, server=server)

    @classmethod
    def in_process(
        cls,
        answering: Callable[[dict[str, Any], Mapping[str, str]], Any],
        *,
        server: str = "",
        media: str = "application/json",
    ) -> "Client":
        """A client for a server running in this process.

        `answering` is handed the decoded JSON-RPC request AND the headers, and
        returns the whole JSON-RPC response. Both halves are deliberate: the
        headers are where `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name`
        live, and a seam that hid them would leave the one part of this client
        that a compliant server validates — and rejects with `HeaderMismatch`
        when it disagrees with the body — asserted by nothing.

        It is not only a test seam. A host embedding a server in its own process
        gets the same object as one across a network, which is the property that
        lets an air-gapped box run the same document as a connected one.
        """

        def _post(body: bytes, headers: Mapping[str, str]) -> "tuple[str, bytes]":
            asked = json.loads(body.decode("utf-8"))
            said = answering(asked, dict(headers))
            written = json.dumps(said).encode("utf-8")
            if media == "text/event-stream":
                written = b"event: message\ndata: " + written + b"\n\n"
            return (media, written)

        return cls(post=_post, server=server)

    # ────────────────────────────────────────────────── what a server has

    def published_tools(self) -> tuple[dict[str, Any], ...]:
        """Every tool the server publishes, in the order it published them.

        Hand this to `mcp_bridge.check_against_authored` before running
        anything. That is the live half of AD-71 and this is where its first
        argument comes from: a server publishes its own list, with its own
        `inputSchema`, on a machine, after the review — and PACT's claim is that
        what you reviewed is what runs.

        **Paginated, and the pagination is not a nicety.** `ListToolsResult`
        carries `nextCursor`, so a client that read one page of a server with
        many tools would hand the drift check a SHORT list — and the drift check
        would faithfully report every authored tool beyond the first page as
        *"the server does not publish it"*. A false total-drift report is the
        loudest possible way to be wrong, and it would stop a run that was fine.

        A cursor the server repeats ends the walk instead of spinning: a page
        loop with a customer waiting is indistinguishable from a hang, which
        `shown.py`'s own rule says must never happen.
        """
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        cursor = ""
        while True:
            result = self._ask("tools/list", {"cursor": cursor} if cursor else {})
            published = result.get("tools")
            if not isinstance(published, list):
                raise NotThisProtocol(
                    f"`tools/list` at `{self.server or 'this server'}` answered "
                    f"with no `tools` list, so nothing says what it has."
                )
            found.extend(t for t in published if isinstance(t, Mapping))
            cursor = str(result.get("nextCursor") or "")
            if not cursor or cursor in seen:
                return tuple(found)
            seen.add(cursor)

    def call(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        answers: "Mapping[str, Any] | None" = None,
        request_state: str = "",
    ) -> Called:
        """One `tools/call`, and what came back.

        `answers` and `request_state` are the MRTR retry and they are the whole
        of it: this revision deleted server-initiated requests, so a server that
        needs a person's input answers `input_required` and the client RETRIES
        THE SAME CALL carrying `inputResponses` under the server's own keys and
        its `requestState` back unchanged. That is a retry and not a resumption —
        there is no session to resume — which is exactly why it survives a PACT
        run parking, a process ending, and the answer arriving somewhere else.

        A result that is not `complete` comes back as data on [`Called`]. It is
        never answered here: what the server is asking for is a person, and this
        module has no person. Inventing one would be the failure `questions.py`
        exists to prevent, arriving over a wire.
        """
        params: dict[str, Any] = {"name": name, "arguments": dict(arguments)}
        if answers:
            params["inputResponses"] = dict(answers)
        if request_state:
            params["requestState"] = request_state
        result = self._ask("tools/call", params, named=name)

        kind = result.get("resultType")
        # An ABSENT `resultType` is `complete`. The spec requires that of
        # clients, for servers still on an earlier revision — and reading an
        # absence as "not complete" would turn every such server's every answer
        # into a request for input nobody asked for.
        said = "complete" if kind is None else str(kind)
        if said == "input_required":
            needs = result.get("inputRequests")
            return Called(
                complete=False,
                needs=dict(needs) if isinstance(needs, Mapping) else {},
                request_state=str(result.get("requestState") or ""),
            )
        if said != "complete":
            # *"A resultType of any value unrecognized by the client MUST be
            # considered invalid."* Refusing beats guessing: an extension's
            # result type this client cannot read is not an answer, and handing
            # its fields to a model as if it were would report whatever happened
            # to be in `content` as the outcome of a call that did something
            # else.
            raise NotThisProtocol(
                f"`{name}` at `{self.server or 'this server'}` answered with "
                f"`resultType: {said}`, which this client does not know how to "
                f"read. It is not `complete` and it is not `input_required`, so "
                f"nothing here can say whether the call happened."
            )
        return Called(
            text=_as_text(result),
            is_error=bool(result.get("isError")),
            structured=result.get("structuredContent"),
        )

    # ─────────────────────────────────────────────────────────── the wire

    def _ask(
        self, method: str, params: Mapping[str, Any], named: str = ""
    ) -> dict[str, Any]:
        """One JSON-RPC request, posted, and its result read back.

        There is no step before this one. No `initialize`, no
        `notifications/initialized`, no `Mcp-Session-Id` — the first byte this
        client ever sends about a server is the request it actually wants, which
        is what FR-4.1.14 means by stateless and is the single most visible
        difference from everything reachable through `pydantic_ai.mcp`.
        """
        request_id = next(self._ids)
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            # `_meta` rides on the PARAMS, which is where the spec's own example
            # puts it. The protocol version and the client's capabilities travel
            # on every request precisely because there is no prior connection
            # state for a server to look them up in; a request missing either is
            # malformed and MUST be rejected with -32602.
            "params": {
                **dict(params),
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
                    "io.modelcontextprotocol/clientInfo": {
                        "name": self.client_name,
                        "version": self.client_version,
                    },
                    # Empty, and that is a claim rather than a gap: Sampling and
                    # Roots are deprecated in this revision, and elicitation is
                    # NOT declared because declaring it would tell a server it
                    # may ask this client for a person's input. It cannot — a
                    # person is reached by parking the PACT run, not by a call
                    # inside a tool — and a server MUST NOT rely on a capability
                    # the client did not declare, so the honest empty object is
                    # what keeps that true.
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
            },
        }
        headers = {
            "Content-Type": "application/json",
            # Both, because the client MUST list both and MUST support both: a
            # server may answer a single POST with an SSE stream, and an `Accept`
            # naming only JSON would be this client asking for something it then
            # has to be told it cannot have.
            "Accept": "application/json, text/event-stream",
            # The header and `_meta` MUST carry the same version. One name read
            # twice — a second literal here is how a `HeaderMismatch` refusal
            # gets written into a client by hand.
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            # Mirrored so a load balancer or gateway can route without parsing
            # the body. REQUIRED for compliance, and a server that validates
            # rejects the request with -32020 when either is missing.
            "Mcp-Method": method,
        }
        if named:
            headers["Mcp-Name"] = _header_value(named)

        media, answered = self.post(json.dumps(body).encode("utf-8"), headers)
        message = _one_message(media, answered, request_id, self.server)

        refused = message.get("error")
        if isinstance(refused, Mapping):
            raise ServerRefused(
                f"`{method}` at `{self.server or 'this server'}` was refused: "
                f"{refused.get('message') or 'no reason given'} "
                f"(code {refused.get('code')})."
            )
        result = message.get("result")
        if not isinstance(result, Mapping):
            raise NotThisProtocol(
                f"`{method}` at `{self.server or 'this server'}` answered with "
                f"neither a `result` nor an `error`, so nothing says what "
                f"happened."
            )
        return dict(result)


def _one_message(
    media: str, answered: bytes, request_id: int, server: str
) -> dict[str, Any]:
    """The one JSON-RPC message in an answer, whichever way it was framed.

    A server MAY answer a single POST with `text/event-stream` instead of
    `application/json`, and the client MUST support both. The stream is read for
    the message that answers THIS request rather than for its first event,
    because a stream may carry more than one and picking by position would be
    reading whichever arrived first as the reply to whatever was asked.

    An id that does not match is refused rather than accepted. Nothing here is
    multiplexed — one POST, one answer — so a mismatched id means the server
    replied about a different request, and reading it as this one's result is
    how a refund's outcome gets reported as an order lookup's.
    """
    text = answered.decode("utf-8", errors="replace")
    candidates: list[str] = []
    if media == "text/event-stream":
        for event in text.split("\n\n"):
            data = [
                line.partition(":")[2].strip()
                for line in event.splitlines()
                if line.startswith("data:")
            ]
            if data:
                candidates.append("\n".join(data))
    else:
        candidates.append(text)

    for candidate in candidates:
        try:
            message = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(message, Mapping) and message.get("id") == request_id:
            return dict(message)
    raise NotThisProtocol(
        f"`{server or 'this server'}` answered request {request_id} with "
        f"nothing this client could read as its reply"
        + (f" (media type {media!r})" if media else "")
        + ". The answer was "
        + (f"{len(answered)} bytes." if answered else "empty.")
    )


def _as_text(result: Mapping[str, Any]) -> str:
    """A `CallToolResult`'s content as the one string the model reads next.

    A block this cannot render is NAMED rather than dropped. A tool that answered
    with an image and a client that silently returned "" would tell the run the
    call produced nothing, which is the silent degradation T7 forbids — and it is
    worse here than elsewhere, because the model's next turn is written against
    it.

    `structuredContent` is the fallback and not the preference: a server that
    sent both meant the text for a reader.
    """
    said: list[str] = []
    blocks = result.get("content")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, Mapping):
                continue
            written = block.get("text")
            if isinstance(written, str):
                said.append(written)
            else:
                said.append(f"[a {block.get('type') or 'block'} this run cannot show]")
    if said:
        return "\n".join(said)
    structured = result.get("structuredContent")
    return "" if structured is None else json.dumps(structured, ensure_ascii=False)


def _header_value(said: str) -> str:
    """One value, encoded the way an HTTP header may carry it.

    RFC 9110 allows visible ASCII, space and tab; anything else — and any value
    that would be mistaken for the encoding's own marker — MUST go as
    `=?base64?…?=`. PACT's own tool names cannot need it
    (`crates/pact-loader/src/callable.rs` holds them to lowercase ASCII), but the
    name on the wire is the ACTION the author wrote in a document that may have
    come from anywhere, and a header with a newline in it is a request smuggling
    bug rather than a formatting one.
    """
    plain = all(" " <= c <= "~" for c in said)
    if plain and said == said.strip() and not said.startswith("=?base64?"):
        return said
    return "=?base64?" + base64.b64encode(said.encode("utf-8")).decode("ascii") + "?="
