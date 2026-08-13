"""What reaches the MCP client, and which rule is allowed to hold it back.

`test_a_connection_needs_a_yes_and_the_server_must_publish_what_was_reviewed.py`
holds the decisions `mcp_bridge` makes with the SDK constructor replaced by a
recorder. That seam is the right one for the ORDER of the refusals — it is the
only one that works on a box with no `fastmcp` — and everything downstream of the
last refusal is behind it. Five things are, and each was found by mutating
`mcp_bridge.py` and watching the whole adapter suite stay green:

* **what the constructor is given.** With `_live` patched out, `auth=` could be
  dropped and `id=` could be the address and every test above still passes — the
  connection would open as nobody, and a resumed run could not line its toolsets
  up with the answers a person gave about them. The one test that reaches the real
  `_live` needs `fastmcp`, which is not on the machine PACT is for, so it skips
  exactly where it is needed. Here the SDK MODULE is the seam instead: a fake
  `pydantic_ai.mcp` in `sys.modules` makes `why_no_mcp` answer *"present"* and the
  real `_live` run, so the whole path is exercised on an air-gapped box — and the
  `return ""` at the end of `why_no_mcp`, unreachable here until now, is reached.
* **which rule counts as consent.** `Rule.for_reason` and `Rule.asked_as` are both
  read, and the file above only ever presents a rule that fails BOTH (a plain
  approval: no reason, no server). Either conjunct can be deleted with that suite
  green, and each deletion turns a rule about something else into a wait on the
  connection — or, in the `question.name` case, drops the author's own line and
  opens a connection nobody consented to.
* **an empty `connect:`**, which the loader refuses and this module guards against
  a second time, on the side of the boundary where it would become a call to
  nowhere rather than a message.
* **the order the connections come back in**, which is the servers' and not the
  tools'.
* **every spelling a client publishes its schema under.** The module says it reads
  `inputSchema`, `input_schema`, `parameters_json_schema` and `parameters`; only
  the first was ever tested, and a bridge that read one spelling reports a whole
  healthy server as total drift.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec, Reach  # noqa: E402
from pact_adapters.mcp_bridge import check_against_authored, mcp_toolset_for  # noqa: E402
from pact_adapters.questions import (  # noqa: E402
    NEEDS_PERMISSION,
    Gate,
    Question,
    Rule,
    Shape,
)


class Asked:
    """A host resolver that records every reference it was handed."""

    def __init__(self, answers: "dict[str, str] | None" = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def __call__(self, reference: str) -> "str | None":
        self.asked.append(reference)
        return self.answers.get(reference)


def a_workspace(
    *,
    asks_to_connect: str = "",
    endpoint: str = "host/payments-mcp",
    credential: str = "host/payments-credential",
    server: str = "payments-server",
) -> dict[str, Any]:
    """One agent, one tool, one server — written the way an author writes it."""
    resource: dict[str, Any] = {"resource-kind": "mcp-server", "endpoint": endpoint}
    if credential:
        resource["auth"] = {"by-reference": credential}
    if asks_to_connect:
        resource["asks-to-connect"] = asks_to_connect
    return {
        "agents": {"desk": {"instructions": "decide", "uses": ["payments"]}},
        "tools": {
            "payments": {
                "description": "Where refunds are issued.",
                "connect": server,
                "actions": {
                    "issue-refund": {
                        "description": "Send money back.",
                        "takes": {"order-number": "text", "amount": "money"},
                    }
                },
            }
        },
        "resources": {server: resource},
        "questions": {
            "may-we-connect": {
                "asks": "May this desk use the payments connection?",
                "answer": {"approved": "yes or no"},
            }
        },
    }


def a_spec(doc: dict[str, Any]) -> AgentSpec:
    return AgentSpec.from_document(doc, "desk")


def with_gate(spec: AgentSpec, gate: Gate) -> AgentSpec:
    """The same spec with a different `asking:` — what a host assembling one does."""
    return spec.__class__(
        **{
            **{f: getattr(spec, f) for f in spec.__dataclass_fields__},
            "asking": gate,
        }
    )


def a_fake_sdk(monkeypatch: pytest.MonkeyPatch) -> "list[tuple[str, str, Any]]":
    """A `pydantic_ai.mcp` this machine does not have, in `sys.modules`.

    Not a patch of `mcp_bridge._live`: the point is to run the REAL one. Both
    `why_no_mcp`'s `import pydantic_ai.mcp` and `_live`'s
    `from pydantic_ai.mcp import MCPToolset` resolve out of `sys.modules`, so the
    module is the whole seam and everything between the author's three lines and
    the constructor is the shipped code.
    """
    built: list[tuple[str, str, Any]] = []

    class FakeMCPToolset:
        def __init__(self, address: str, *, id: str, auth: Any) -> None:  # noqa: A002
            self.address, self.id, self.auth = address, id, auth
            built.append((address, id, auth))

    fake = types.ModuleType("pydantic_ai.mcp")
    fake.MCPToolset = FakeMCPToolset  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pydantic_ai.mcp", fake)
    return built


# ───────────────────────────────── what the SDK constructor is actually given


def test_the_address_and_the_secret_the_host_answered_are_what_reach_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The credential goes in as `auth`, and `id` is the SERVER name.

    Both are load-bearing and neither is visible with `_live` replaced. A dropped
    `auth=` connects as nobody — the server answers 401, or worse answers with its
    public surface, and the agent quietly has a different set of tools than the one
    that was reviewed. An `id=` that is the address is a toolset a resumed run
    cannot line up with the answer a person gave about `payments-server`, which is
    the name the consent was granted under.
    """
    built = a_fake_sdk(monkeypatch)

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace()),
        resolve_endpoint=Asked({"host/payments-mcp": "https://payments.internal/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk-live-from-the-host"}),
    )

    assert conn.connected is True, conn.why_not
    assert built == [
        ("https://payments.internal/mcp", "payments-server", "sk-live-from-the-host")
    ], built
    assert conn.toolset is not None and conn.toolset.id == "payments-server"


def test_a_server_that_keeps_no_credential_reaches_the_client_as_no_auth_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`auth=""` and `auth=None` are not the same thing to an SDK.

    A resource with no `auth.by-reference:` is a server that wants none, and the
    empty string is a credential of length zero — a value some clients will send.
    The absence has to arrive as an absence.
    """
    built = a_fake_sdk(monkeypatch)
    credential = Asked({"host/payments-credential": "sk"})

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace(credential="")),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=credential,
    )

    assert conn.connected is True, conn.why_not
    assert built == [("https://pay/mcp", "payments-server", None)], built
    assert credential.asked == [], "a credential was fetched for a server that keeps none"


# ─────────────────────────────────────── which rule is consent to THIS server


def test_a_permission_rule_about_another_server_is_not_consent_to_this_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Rule.asked_as` names the server, and it is read.

    An agent whose tools reach two servers has one `needs-permission` rule per
    server, and they are told apart by `asked_as` alone — `for_reason` is the same
    on both. A bridge that dropped that conjunct would hold the ticketing
    connection shut until somebody answered the question about payments, and would
    report the payments question as the reason.
    """
    built = a_fake_sdk(monkeypatch)
    elsewhere = Question(
        name="may-we-connect-to-zendesk",
        asks="May this desk use the ticketing connection?",
        answer={"approved": Shape("yes-or-no")},
    )
    spec = with_gate(
        a_spec(a_workspace(asks_to_connect="")),
        Gate(
            {
                "payments": (
                    Rule(
                        elsewhere,
                        gates=True,
                        for_reason=NEEDS_PERMISSION,
                        asked_as="zendesk-server",
                    ),
                )
            }
        ),
    )

    (conn,) = mcp_toolset_for(
        spec,
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )

    assert conn.connected is True, (
        f"a permission rule about `zendesk-server` was read as consent standing in "
        f"the way of `payments-server`: {conn.why_not}"
    )
    assert built and built[0][1] == "payments-server"


def test_a_gating_rule_keyed_to_this_server_for_another_reason_is_not_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Rule.for_reason` is read too, and the pair is what identifies consent.

    `asked_as` is not the property of connection rules alone — it is the name a
    wait is answered under whenever the wait is not about the thing the rule hangs
    off. A gate that matched on it would take any rule keyed to `payments-server`
    as the connection question, so a run would wait for the wrong answer and
    `<server>-was-approved` would release the wrong thing.
    """
    built = a_fake_sdk(monkeypatch)
    approval = Question(
        name="is-this-ok",
        asks="Please check this before it happens.",
        answer={"approved": Shape("yes-or-no")},
    )
    spec = with_gate(
        a_spec(a_workspace(asks_to_connect="")),
        Gate(
            {
                "payments": (
                    Rule(
                        approval,
                        gates=True,
                        for_reason="needs-approval",
                        asked_as="payments-server",
                    ),
                )
            }
        ),
    )

    (conn,) = mcp_toolset_for(
        spec,
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )

    assert conn.connected is True, (
        f"a `needs-approval` rule keyed to the server was read as consent to the "
        f"connection: {conn.why_not}"
    )
    assert built and built[0][1] == "payments-server"


def test_a_matching_rule_that_names_no_question_still_waits_on_the_documents_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fail-closed direction inside the branch that already matched.

    `_consent_question` returns `rule.question.name or resource.asks_to_connect`,
    and the fallback is the half that costs money. A `Rule` a host assembled can
    carry a question with no name; the DOCUMENT still says `asks-to-connect:`, and
    an empty answer there does not mean "nobody needs to be asked", it means this
    rule could not say who. Falling through to the author's line is the only
    reading that does not open a payments connection on a missing string.
    """
    built = a_fake_sdk(monkeypatch)
    nameless = Question(
        name="", asks="May this desk use the payments connection?", answer={}
    )
    spec = with_gate(
        a_spec(a_workspace(asks_to_connect="may-we-connect")),
        Gate(
            {
                "payments": (
                    Rule(
                        nameless,
                        gates=True,
                        for_reason=NEEDS_PERMISSION,
                        asked_as="payments-server",
                    ),
                )
            }
        ),
    )

    endpoint, credential = Asked(), Asked()
    (conn,) = mcp_toolset_for(
        spec, resolve_endpoint=endpoint, resolve_credential=credential
    )

    assert conn.connected is False, (
        "a gate rule with no question name dropped the author's `asks-to-connect:` "
        "line and the connection opened with nobody asked"
    )
    assert "may-we-connect" in conn.why_not, conn.why_not
    assert built == [] and credential.asked == [] and endpoint.asked == []


def test_a_connect_line_with_nothing_after_it_names_no_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty `connect:` is skipped, not carried as a server called `""`.

    `ir._reaches` refuses it on the way in — *"`connect:` with nothing after it is
    the commonest half-finished line there is"* — and this is the second half of
    the same guard, on the side of the boundary where the failure would be a call
    to nowhere. It is here rather than trusted to the loader for the reason
    `_reaches` gives about its own argument: a host may assemble an `AgentSpec`
    itself, and *"the checker would have caught it"* is not a property of the
    object in front of you. Without the guard the bridge answers with a
    `Connection` whose `server` is the empty string and whose reason quotes
    `resources/.yaml` — a file nobody can go and open.
    """
    a_fake_sdk(monkeypatch)
    spec = a_spec(a_workspace())
    (tool,) = spec.tools
    blank = tool.__class__(
        **{
            **{f: getattr(tool, f) for f in tool.__dataclass_fields__},
            "reaches": Reach(kind="connect", value=""),
        }
    )
    assembled = spec.__class__(
        **{**{f: getattr(spec, f) for f in spec.__dataclass_fields__}, "tools": (blank,)}
    )

    endpoint, credential = Asked(), Asked()
    assert (
        mcp_toolset_for(
            assembled, resolve_endpoint=endpoint, resolve_credential=credential
        )
        == ()
    ), "an empty `connect:` was carried across as a server with no name"
    assert endpoint.asked == [] and credential.asked == []


# ─────────────────────────── every spelling a client publishes its schema under


def test_the_published_schema_is_read_under_every_spelling_a_client_uses() -> None:
    """`inputSchema`, `input_schema`, `parameters_json_schema`, `parameters`.

    Four names for one thing, because this is handed whatever the client on that
    machine returns: MCP's own `Tool` objects say `inputSchema`, Pydantic AI's
    `ToolDefinition` says `parameters_json_schema`, and the dict forms in between
    use the snake-cased spellings. A reader that knew one of them would find no
    arguments on the other three — and no arguments is not "no drift", it is every
    declared argument reported as vanished and every published one as unreviewed,
    which is the loudest possible way to be wrong about a server that is fine.
    """
    schema = {"type": "object", "properties": {"amount": {"type": "string"}}}
    authored = {"issue-refund": {"amount": "money"}}

    for spelling in ("inputSchema", "input_schema", "parameters_json_schema", "parameters"):
        assert (
            check_against_authored([{"name": "issue-refund", spelling: schema}], authored)
            == ()
        ), f"the `{spelling}` spelling was not read, so a healthy server reads as drift"

    class Definition:
        """Pydantic AI's shape: an object, and the snake-cased spelling."""

        def __init__(self, name: str, parameters_json_schema: dict) -> None:
            self.name, self.parameters_json_schema = name, parameters_json_schema

    assert check_against_authored([Definition("issue-refund", schema)], authored) == ()


def test_the_connections_come_back_in_server_name_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One order, and it is the SERVERS', not the tools'.

    A host prints these, keys a wait off them and compares two runs of the same
    workspace, so the answer has to be in an order the document cannot move. The
    tools here are named against their servers on purpose — `alpha` reaches
    `zendesk-server` and `zed` reaches `archive-server` — because sorting the tools
    and sorting the servers are two different orders, and only one of them is what
    a reader of this list is looking down.
    """
    a_fake_sdk(monkeypatch)
    doc = a_workspace()
    doc["tools"]["alpha"] = {
        "description": "Reads a ticket.",
        "connect": "zendesk-server",
        "actions": {"look-up": {"takes": {"ticket": "text"}}},
    }
    doc["tools"]["zed"] = {
        "description": "Reads an archive.",
        "connect": "archive-server",
        "actions": {"look-up": {"takes": {"ref": "text"}}},
    }
    doc["resources"]["zendesk-server"] = {
        "resource-kind": "mcp-server",
        "endpoint": "host/zendesk-mcp",
    }
    doc["resources"]["archive-server"] = {
        "resource-kind": "mcp-server",
        "endpoint": "host/archive-mcp",
    }
    doc["agents"]["desk"]["uses"] = ["zed", "payments", "alpha"]

    conns = mcp_toolset_for(
        a_spec(doc),
        resolve_endpoint=Asked(
            {
                "host/payments-mcp": "https://pay/mcp",
                "host/zendesk-mcp": "https://zen/mcp",
                "host/archive-mcp": "https://arc/mcp",
            }
        ),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )

    assert [c.server for c in conns] == [
        "archive-server",
        "payments-server",
        "zendesk-server",
    ], [c.server for c in conns]
