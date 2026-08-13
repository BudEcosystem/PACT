"""Two halves of one claim, at the one boundary PACT does not own.

PACT's claim is *what you reviewed is what runs*. An MCP server breaks that claim
in two different places and `src/pact_adapters/mcp_bridge.py` is where both are
either kept or reported:

* **before the connection.** `resources/payments-server.yaml` writes
  `asks-to-connect: may-we-connect`. A bridge that opened the socket and fetched
  the credential first would make that line decorative — the run would park at
  the first CALL, long after money's connection was live and its secret was in
  this process. The whole cost of getting this wrong is already written down in
  `test_connection_consent.py`: for a round the question was found, the audience
  and the hour were read, the screen rendered, and the run called `payments`
  anyway and reported `final`.
* **at the connection.** An MCP server publishes its OWN tool list, with its own
  `inputSchema`, at connect time. `pact check` read what the author wrote; the
  server answers with what it has; the two meet for the first time on a machine,
  at run time, with a customer waiting. A server that grows a tool, drops one, or
  moves an argument's type has changed what the agent can do without one line of
  the workspace moving. That is AD-71, and `check_against_authored` is the only
  thing in the repository that can see it.

**Nothing here asserts what a model said.** Every test below asserts what the
bridge DID: which references it handed to which host callable, in what order,
whether it reached the client constructor at all, and what it put in the reason.
The two host callables are recorders, so "the credential was never looked up" is
a measurement rather than an intention.

**Why `_live` is monkeypatched rather than `fastmcp` installed.** `fastmcp` is not
on this machine and PACT does not install one — `pydantic_ai.mcp` raises
`ImportError` at import without it, which is exactly the air-gapped case D17 is
about. Skipping every test that reaches the constructor would leave the consent
order, the resolution order and the refusals unchecked on the machine PACT is
FOR. So the SDK constructor is the seam: patching it exercises every decision
this module makes and pretends nothing about the client. The two tests that need
a real `MCPToolset` say so with `pytest.importorskip` and skip cleanly here — and
`test_the_absence_of_an_mcp_client_is_reported_and_never_silent` asserts that the
absence they skip on is a sentence somebody is handed, not a silence.

## The mutations these were written from

* Move the `if absent:` line in `_why_not_connect` back above the consent branch:
  `test_consent_is_decided_before_this_machine_is_asked_what_it_has_installed`
  goes red. That ordering is not cosmetic — with the client check first, every
  consent branch is unreachable on a box with no MCP client, so the gate on a
  payments connection would hold only where one could already be opened.
* Delete the `server not in granted` half of the consent branch:
  `test_a_connection_nobody_has_allowed_is_never_opened_and_its_credential_is_never_fetched`
  goes red with the credential resolver recording a call.
* Make `_consent_question` read only `resource.asks_to_connect`:
  `test_the_gate_is_what_says_a_connection_needs_a_yes` goes red.
* Make it read only the gate: `test_a_document_that_asks_to_connect_is_honoured_
  even_when_no_gate_was_built` goes red — the fail-closed direction, which is the
  one that costs money to get wrong.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import mcp_bridge  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.mcp_bridge import (  # noqa: E402
    check_against_authored,
    mcp_toolset_for,
    why_no_mcp,
)
from pact_adapters.questions import Gate, Question, Rule, Shape  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples/refund-desk"


# ───────────────────────────────────────────────────────────── the fixtures


class Asked:
    """A host resolver that records every reference it was handed.

    The order matters as much as the count: consent must be settled before
    anything is asked, so a recorder that only counted could not tell "asked and
    refused" from "never asked".
    """

    def __init__(self, answers: "dict[str, str] | None" = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def __call__(self, reference: str) -> "str | None":
        self.asked.append(reference)
        return self.answers.get(reference)


def a_workspace(
    *,
    asks_to_connect: str = "",
    kind: str = "mcp-server",
    endpoint: str = "host/payments-mcp",
    credential: str = "host/payments-credential",
    server: str = "payments-server",
) -> dict[str, Any]:
    """One agent, one tool, one server — written the way an author writes it.

    A document rather than a hand-built `AgentSpec`, so the walk this module
    depends on (`uses:` -> `tools.<t>.connect` -> `resources.<server>`) is the
    real one. A test that assembled the `ResourceSpec` itself would prove the
    bridge reads a dataclass and say nothing about whether the author's three
    lines reach it.
    """
    resource: dict[str, Any] = {"resource-kind": kind, "endpoint": endpoint}
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


def stub_client(monkeypatch: pytest.MonkeyPatch) -> "list[tuple[str, str, str]]":
    """Replace the SDK constructor with a recorder, and report the client present.

    Returns the list of `(address, server, credential)` it was called with — so
    "a connection was opened" is a fact this test file measured rather than a
    `connected` flag the module set about itself.
    """
    built: list[tuple[str, str, str]] = []

    def _live(address: str, server: str, credential: str) -> Any:
        built.append((address, server, credential))
        return f"MCPToolset<{server}>"

    monkeypatch.setattr(mcp_bridge, "_live", _live)
    monkeypatch.setattr(mcp_bridge, "why_no_mcp", lambda: "")
    return built


# ─────────────────────────────────────────── consent, before anything else


def test_a_connection_nobody_has_allowed_is_never_opened_and_its_credential_is_never_fetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect this module exists to not repeat.

    `asks-to-connect:` means a person decides whether this desk may use the
    connection AT ALL. If the bridge resolves the credential first, the secret is
    in this process and the socket is open before anybody is asked — and the park
    that follows is theatre. So the measurement is not "it did not call the tool"
    but "the host was never asked for the credential", which is the only version
    of the claim a secret cannot leak past.
    """
    built = stub_client(monkeypatch)
    endpoint, credential = Asked({"host/payments-mcp": "https://pay/mcp"}), Asked(
        {"host/payments-credential": "sk-live-not-in-any-file"}
    )

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace(asks_to_connect="may-we-connect")),
        resolve_endpoint=endpoint,
        resolve_credential=credential,
    )

    assert conn.connected is False
    assert built == [], "a client was constructed for a connection nobody allowed"
    assert credential.asked == [], (
        f"the credential reference was handed to the host before anybody said "
        f"yes: {credential.asked}"
    )
    assert endpoint.asked == [], "the endpoint was resolved before consent too"
    assert "may-we-connect" in conn.why_not and "payments-server" in conn.why_not
    # The tools are still there, and they are the tools — a `Connection` that
    # named them and handed back an empty toolset would take the agent's own
    # capability off the model's list with nothing anywhere saying so, which is
    # the same silent degradation as connecting without asking, pointing the
    # other way.
    assert conn.tools == ("payments",)
    assert [d.name for d in conn.toolset.tool_defs] == ["payments"]
    assert set(conn.toolset.tool_defs[0].parameters_json_schema["properties"]) == {
        "order-number", "amount", "action",
    }


def test_the_same_connection_opens_once_a_person_has_said_yes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction, without which the test above passes on a bridge that
    can never connect to anything.

    One document, one difference: the server is named in `allowed`. Consent is
    keyed by the SERVER, which is what `Rule.asked_as` carries and what the
    harness records as `<server>-was-approved` — so the name a person answered
    under is the name this is unlocked by.
    """
    built = stub_client(monkeypatch)
    endpoint, credential = Asked({"host/payments-mcp": "https://pay/mcp"}), Asked(
        {"host/payments-credential": "sk-live-not-in-any-file"}
    )

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace(asks_to_connect="may-we-connect")),
        resolve_endpoint=endpoint,
        resolve_credential=credential,
        allowed=["payments-server"],
    )

    assert conn.connected is True and conn.why_not == ""
    assert built == [("https://pay/mcp", "payments-server", "sk-live-not-in-any-file")]
    assert endpoint.asked == ["host/payments-mcp"]
    assert credential.asked == ["host/payments-credential"]


def test_a_yes_to_one_connection_is_not_a_yes_to_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`allowed` is matched against the server, not merely counted.

    A bridge that treated a non-empty `allowed` as "consent has been dealt with"
    would let one person's yes to the ticketing system open the payments one —
    which is the same mistake, one level up, as the two waits that shared an
    answer key until `Rule.asked_as` existed.
    """
    stub_client(monkeypatch)
    (conn,) = mcp_toolset_for(
        a_spec(a_workspace(asks_to_connect="may-we-connect")),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
        allowed=["zendesk-server"],
    )
    assert conn.connected is False, "a yes about a different server opened this one"


def test_consent_is_decided_before_this_machine_is_asked_what_it_has_installed() -> None:
    """A permission is a fact about a person and holds whatever is installed.

    Nothing is patched here: `fastmcp` really is absent on the machine PACT is
    for, so BOTH refusals are true of `payments-server` and only one of them can
    be reported. It must be the consent one. With the client check first, every
    consent branch below it is unreachable on an air-gapped box — the gate on a
    payments connection would then be enforced only where one could already be
    opened, which is precisely backwards.
    """
    if why_no_mcp() == "":
        pytest.skip("this machine has an MCP client; the ordering shows with none")

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace(asks_to_connect="may-we-connect")),
        resolve_endpoint=Asked(),
        resolve_credential=Asked(),
    )
    assert "may-we-connect" in conn.why_not, (
        f"with no client installed the reason given was about the machine, not "
        f"about the person who has not been asked: {conn.why_not}"
    )


def test_the_gate_is_what_says_a_connection_needs_a_yes() -> None:
    """The consent comes from the rule `questions_for` already built, not from a
    second reading of the same line.

    `questions.questions_for` walks `uses:` -> `tools.<t>.connect` ->
    `resources.<server>.asks-to-connect` and produces
    `Rule(gates=True, for_reason=NEEDS_PERMISSION, asked_as=<server>)`. Here the
    RESOURCE says nothing — the document has no `asks-to-connect:` at all — and
    the gate is handed the rule directly, which is what a host assembling a spec
    does. The connection must still wait, or the rule the whole consent mechanism
    is built on means nothing to the bridge.
    """
    spec = a_spec(a_workspace(asks_to_connect=""))
    asked = Question(
        name="may-we-connect",
        asks="May this desk use the payments connection?",
        answer={"approved": Shape("yes-or-no")},
    )
    gated = spec.__class__(
        **{
            **{f: getattr(spec, f) for f in spec.__dataclass_fields__},
            "asking": Gate(
                {
                    "payments": (
                        Rule(
                            asked,
                            gates=True,
                            for_reason="needs-permission",
                            asked_as="payments-server",
                        ),
                    )
                }
            ),
        }
    )

    (conn,) = mcp_toolset_for(
        gated, resolve_endpoint=Asked(), resolve_credential=Asked()
    )
    assert conn.connected is False
    assert "may-we-connect" in conn.why_not, conn.why_not


def test_a_rule_about_the_same_tool_for_a_different_reason_is_not_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`payments` is the same name in two of the author's files.

    A threshold in `policies/approvals.yaml` and an `asks-to-connect:` in
    `resources/payments-server.yaml` both attach a rule to `payments`, which is
    the reason `Rule.for_reason` and `Rule.asked_as` exist at all. A bridge that
    matched on the tool name alone would read a refund-approval rule as consent
    to the connection — and would then also refuse to connect for a rule that
    says nothing about connecting.
    """
    built = stub_client(monkeypatch)
    spec = a_spec(a_workspace(asks_to_connect=""))
    approval = Question(
        name="is-this-ok",
        asks="Please check this before it happens.",
        answer={"approved": Shape("yes-or-no")},
    )
    with_approval = spec.__class__(
        **{
            **{f: getattr(spec, f) for f in spec.__dataclass_fields__},
            "asking": Gate({"payments": (Rule(approval, gates=True),)}),
        }
    )

    (conn,) = mcp_toolset_for(
        with_approval,
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )
    assert conn.connected is True, (
        f"an approval rule about a CALL was read as consent to the CONNECTION, "
        f"so the connection never opens: {conn.why_not}"
    )
    assert built and built[0][1] == "payments-server"


def test_a_document_that_asks_to_connect_is_honoured_even_when_no_gate_was_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fail-closed half, and the direction that costs money to get wrong.

    A `Gate` can be built by hand — `Gate.of({thing: question})` is a supported
    shape, `asking_only()` returns rules that gate nothing, and a host assembling
    an `AgentSpec` passes whatever gate it has. In every one of those cases the
    DOCUMENT still says `asks-to-connect:`. An unnecessary wait costs somebody a
    click; a missing one opens a payments connection nobody consented to, so the
    two sources are unioned rather than ranked.
    """
    stub_client(monkeypatch)
    spec = a_spec(a_workspace(asks_to_connect="may-we-connect"))
    ungated = spec.__class__(
        **{
            **{f: getattr(spec, f) for f in spec.__dataclass_fields__},
            "asking": Gate({}),
        }
    )
    (conn,) = mcp_toolset_for(
        ungated, resolve_endpoint=Asked(), resolve_credential=Asked()
    )
    assert conn.connected is False, (
        "the gate was empty and the author's `asks-to-connect:` line was ignored"
    )
    assert "may-we-connect" in conn.why_not


# ──────────────────────────────────────── the references, and who resolves them


def test_no_address_and_no_secret_is_ever_read_out_of_the_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`endpoint:` and `auth.by-reference:` are references, never values.

    The schema refuses `bearer-token:` BY NAME because `auth:` was a `map of
    text` for a round and `auth: {bearer-token: sk-live-…}` loaded clean — a
    secret pasted into the one field whose own help says a spec file may not
    contain one, ever. A bridge that connected to whatever `endpoint:` said would
    put that field back under a different name, so what is measured here is that
    the two strings the tree holds reach the HOST and that what reaches the
    client is what the host answered, byte for byte.
    """
    built = stub_client(monkeypatch)
    endpoint = Asked({"host/payments-mcp": "https://payments.internal/mcp"})
    credential = Asked({"host/payments-credential": "sk-live-resolved-by-the-host"})

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace()),
        resolve_endpoint=endpoint,
        resolve_credential=credential,
    )

    assert endpoint.asked == ["host/payments-mcp"], endpoint.asked
    assert credential.asked == ["host/payments-credential"], credential.asked
    assert built == [
        ("https://payments.internal/mcp", "payments-server", "sk-live-resolved-by-the-host")
    ]
    # And the secret is not on anything this function hands back.
    assert "sk-live-resolved-by-the-host" not in conn.why_not
    assert conn.connected is True


def test_a_server_this_host_does_not_publish_is_deferred_and_says_which_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host that publishes three servers handed a workspace naming four is the
    normal case, not an error.

    The tools stay as an `ExternalToolset`, which is Pydantic AI's own shape for
    *"the caller fulfils these"* — the run ends with `DeferredToolRequests` and a
    host decides. Guessing an address, or dropping the tools, are the two
    dishonest answers: one connects somewhere nobody wrote down, the other
    removes a capability the author granted with nothing anywhere saying so.
    """
    built = stub_client(monkeypatch)
    credential = Asked({"host/payments-credential": "sk"})
    (conn,) = mcp_toolset_for(
        a_spec(a_workspace()),
        resolve_endpoint=Asked(),            # publishes nothing
        resolve_credential=credential,
    )
    assert built == [] and conn.connected is False
    assert "host/payments-mcp" in conn.why_not, conn.why_not
    assert type(conn.toolset).__name__ == "ExternalToolset"
    # And the secret was left where it is. There is nothing to do with a
    # credential for a server this machine cannot find, so pulling one into this
    # process is a copy of it in a place nobody asked for.
    assert credential.asked == [], credential.asked


def test_a_resource_with_no_endpoint_line_is_told_which_line_to_add(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A half-written file gets the line somebody would go and add.

    `endpoint:` is not required by the schema, so a `resources/<name>.yaml` with
    only `resource-kind:` in it loads. Falling through to *"this host resolved it
    to nothing"* would blame a platform team for failing to resolve a name nobody
    wrote — a diagnostic that sends the reader to the wrong person, which is the
    `available-when:` failure (*"a warning whose fix is an error is worse than no
    warning at all"*) in a different field.
    """
    stub_client(monkeypatch)
    endpoint = Asked()
    (conn,) = mcp_toolset_for(
        a_spec(a_workspace(endpoint="")),
        resolve_endpoint=endpoint,
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )
    assert conn.connected is False
    assert "no `endpoint:`" in conn.why_not, conn.why_not
    assert endpoint.asked == [], "a host was asked to resolve a name nobody wrote"


def test_a_credential_the_host_cannot_resolve_does_not_become_an_anonymous_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure that would otherwise be invisible.

    An address that resolves and a credential that does not is a connection this
    process CAN open — and it would open it as nobody. The server answers 401, or
    worse answers with its public surface, and the agent quietly has a different
    set of tools than the one that was reviewed. Deferring is the only answer
    that does not silently change what the agent is.
    """
    built = stub_client(monkeypatch)
    (conn,) = mcp_toolset_for(
        a_spec(a_workspace()),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked(),          # knows nothing about this one
    )
    assert built == [] and conn.connected is False
    assert "host/payments-credential" in conn.why_not, conn.why_not


def test_a_resolver_that_raises_is_an_absence_and_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host asked about a server it has never heard of must not take a run down.

    This is `providers._deepeval_classes`' rule one subsystem over: an absence is
    something to report, never a traceback in the middle of somebody's run. The
    caller is about to be told in a sentence what could not be resolved.
    """
    stub_client(monkeypatch)

    def explodes(reference: str) -> str:
        raise RuntimeError("no such registry on this box")

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace()),
        resolve_endpoint=explodes,
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )
    assert conn.connected is False
    assert "host/payments-mcp" in conn.why_not


def test_a_kind_this_bridge_does_not_speak_is_refused_rather_than_assumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`resource-kind:` is carried across the boundary rather than assumed.

    It has one choice today, and the first day it has two, a bridge that built an
    MCP client for whatever it was handed is reading a field that does not say
    what it thinks it says.
    """
    stub_client(monkeypatch)
    (conn,) = mcp_toolset_for(
        a_spec(a_workspace(kind="content-store")),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )
    assert conn.connected is False
    assert "content-store" in conn.why_not


def test_one_toolset_per_server_and_not_one_per_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection is a property of the SERVER.

    Two tools reaching one server are one client and one consent — the
    `may-we-connect` file says so itself: *"This is asked once, not once per
    customer"*. One client per tool would mean two sockets, two credential
    lookups, and a person asked twice for one decision.
    """
    built = stub_client(monkeypatch)
    doc = a_workspace()
    doc["tools"]["look-ups"] = {
        "description": "Reads an order.",
        "connect": "payments-server",
        "actions": {"look-up-order": {"takes": {"order-number": "text"}}},
    }
    doc["agents"]["desk"]["uses"] = ["payments", "look-ups"]
    credential = Asked({"host/payments-credential": "sk"})

    conns = mcp_toolset_for(
        a_spec(doc),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=credential,
    )

    assert len(conns) == 1, [c.server for c in conns]
    assert sorted(conns[0].tools) == ["look-ups", "payments"]
    assert len(built) == 1 and credential.asked == ["host/payments-credential"]


def test_a_tool_that_reaches_somewhere_that_is_not_a_server_is_not_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`connect:`, `url:` and `says:` are three different destinations.

    Only one of them is an MCP server. A bridge that treated a `url:` tool as a
    connection would open a client against an address the author wrote for an
    HTTP call, and one that treated `says:` — words put to a model — as one would
    be inventing a server out of a sentence.
    """
    stub_client(monkeypatch)
    doc = a_workspace()
    doc["tools"]["ask-the-model"] = {"description": "Rewrites a line.", "says": "be polite"}
    doc["tools"]["fetch"] = {
        "description": "Reads a page.",
        "url": "https://example.test/thing",
        "method": "GET",
    }
    doc["agents"]["desk"]["uses"] = ["payments", "ask-the-model", "fetch"]

    conns = mcp_toolset_for(
        a_spec(doc),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )
    assert [c.server for c in conns] == ["payments-server"]
    assert conns[0].tools == ("payments",)


def test_a_connect_line_naming_a_server_this_workspace_has_not_got_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`names: resources` refuses this at check time, so reaching it means the
    document did not come from `pact check`.

    Refusing beats inventing an empty resource: "no endpoint" and "no such
    server" are different facts and only one of them is a typo. A bridge that
    filled in the blanks would connect to nowhere and report why in terms of a
    file that does not exist.
    """
    stub_client(monkeypatch)
    doc = a_workspace()
    doc["resources"] = {}
    (conn,) = mcp_toolset_for(
        a_spec(doc),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )
    assert conn.connected is False
    assert "payments-server" in conn.why_not and "resources/" in conn.why_not


# ────────────────────────────────────────── the machine that has no MCP client


def test_the_absence_of_an_mcp_client_is_reported_and_never_silent() -> None:
    """D17, over this module.

    The air-gapped case is not "the MCP client is slow", it is "`fastmcp` is not
    on this machine and never will be". `pydantic_ai.mcp` raises `ImportError` at
    import without it — it does not degrade and it exports no stub — so an
    unguarded bridge is a module that cannot be imported at all on the machine
    PACT is for. The honest answer is a sentence with two lines to type, one of
    which needs nothing installed, and it must reach the CALLER: a `Connection`
    that came back deferred with an empty reason would be indistinguishable from
    a workspace that named no servers.
    """
    said = why_no_mcp()
    if said == "":
        import pydantic_ai.mcp  # noqa: F401  — then it really is here
        return

    assert "fastmcp" in said or "pydantic-ai-slim[mcp]" in said, said
    assert "fix:" in said, "an absence with no line to type is a shrug"
    # The second line: the one that needs nothing installed at all.
    assert "call_tool" in said, said

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace(asks_to_connect="")),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )
    assert conn.connected is False
    assert conn.why_not == said, (
        "the machine cannot connect and the caller was not told why — a deferred "
        "connection with an empty reason reads as 'this workspace has no servers'"
    )
    assert type(conn.toolset).__name__ == "ExternalToolset"


def test_nothing_this_module_does_opens_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """The air-gap, asserted behaviourally rather than by reading the imports.

    `test_metrics_an_expert_brings.py` takes `socket.socket` away to prove the
    provider layer never reaches a package index; the same instrument belongs
    here, because an MCP bridge is the one module in this package whose whole
    subject is a network connection. Importing it, asking whether a client is
    present, and deciding every refusal above must all happen with no socket in
    the process — otherwise the first thing an air-gapped author learns about
    their `connect:` line is a hang.
    """
    import socket as _socket

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("something opened a socket")

    monkeypatch.setattr(_socket, "socket", refuse)
    monkeypatch.delitem(sys.modules, "pact_adapters.mcp_bridge", raising=False)
    fresh = importlib.import_module("pact_adapters.mcp_bridge")

    fresh.why_no_mcp()
    conns = fresh.mcp_toolset_for(
        a_spec(a_workspace(asks_to_connect="may-we-connect")),
        resolve_endpoint=Asked(),
        resolve_credential=Asked(),
    )
    assert conns and conns[0].connected is False


def test_a_real_toolset_is_what_comes_back_where_the_client_is_installed() -> None:
    """The one thing the seam cannot prove: that the object is the SDK's.

    Skipped on the air-gapped box, which is why every decision above is checked
    without it. `id=` is the server name deliberately — it is the name the
    consent was granted under and the name a durable runtime keys this toolset's
    steps by, so a resumed run can line its toolsets up with the answers a person
    gave about them.
    """
    pytest.importorskip("fastmcp", reason="no MCP client on this machine")
    from pydantic_ai.mcp import MCPToolset

    (conn,) = mcp_toolset_for(
        a_spec(a_workspace()),
        resolve_endpoint=Asked({"host/payments-mcp": "https://pay/mcp"}),
        resolve_credential=Asked({"host/payments-credential": "sk"}),
    )
    assert conn.connected is True
    assert isinstance(conn.toolset, MCPToolset)
    assert conn.toolset.id == "payments-server"


# ────────────────────────────── what the server says it has, against the files


def test_a_tool_the_server_does_not_publish_is_named() -> None:
    """The author reviewed a call that will fail at the far end.

    `pact check` passed the workspace; the server dropped the tool after the
    review. Nothing in the tree moved, so nothing in the tree can say this — the
    server's own answer at connect time is the only place it shows.
    """
    said = check_against_authored(
        {"look-up-order": {"type": "object", "properties": {"order-number": {"type": "string"}}}},
        {"look-up-order": {"order-number": "text"}, "issue-refund": {"amount": "money"}},
    )
    assert len(said) == 1, said
    assert "issue-refund" in said[0] and "does not publish" in said[0]


def test_a_tool_nobody_reviewed_is_named_even_though_nothing_is_missing() -> None:
    """The direction a "does everything I need exist?" check cannot see.

    A server that GREW a tool satisfies every authored name and hands the model a
    capability no reviewer ever read. That is the AD-71 claim failing in the
    quiet direction, and a check that only looked for absences would report the
    workspace as sound.
    """
    said = check_against_authored(
        {
            "issue-refund": {"type": "object", "properties": {"amount": {"type": "string"}}},
            "delete-account": {"type": "object", "properties": {}},
        },
        {"issue-refund": {"amount": "money"}},
    )
    assert len(said) == 1, said
    assert "delete-account" in said[0] and "nobody reviewed" in said[0]


def test_an_argument_that_appeared_and_one_that_vanished_are_different_sentences() -> None:
    """Two failures, two consequences, and a caller who has to act differently.

    An authored argument the server does not take means the call the author
    reviewed is rejected. A published argument nothing declares means the model
    is free to choose what goes in it, with no `takes:` line and no `bind:`
    deciding — which is how a value the surrounding system was supposed to fill
    becomes one the model invents.
    """
    said = check_against_authored(
        {
            "issue-refund": {
                "type": "object",
                "properties": {"amount": {"type": "string"}, "reason": {"type": "string"}},
            }
        },
        {"issue-refund": {"amount": "money", "order-number": "text"}},
    )
    assert len(said) == 2, said
    vanished = [s for s in said if "order-number" in s]
    appeared = [s for s in said if "reason" in s]
    assert vanished and "rejected at the server" in vanished[0]
    assert appeared and "the model is free to choose" in appeared[0]


def test_a_type_that_moved_is_the_one_that_does_not_fail_loudly() -> None:
    """The whole reason this check exists rather than a smoke call.

    A missing tool fails at the first call. A type that changed does not: the
    call is made, the server takes it, and the wrong thing arrives at the far
    end. `amount` declared `money` and published as a `number` is a refund
    amount losing its currency, which is a defect nobody sees until an audit.
    """
    said = check_against_authored(
        {"issue-refund": {"type": "object", "properties": {"amount": {"type": "number"}}}},
        {"issue-refund": {"amount": "money"}},
    )
    assert len(said) == 1, said
    assert "`amount`" in said[0] and "money" in said[0] and "number" in said[0]


def test_two_descriptions_that_agree_produce_no_sentences() -> None:
    """Without this the check could report drift on everything and still look
    like it worked."""
    assert (
        check_against_authored(
            {
                "issue-refund": {
                    "type": "object",
                    "properties": {
                        "order-number": {"type": "string"},
                        "amount": {"type": "string"},
                    },
                }
            },
            {"issue-refund": {"order-number": "text", "amount": "money"}},
        )
        == ()
    )


def test_the_server_is_read_whether_it_hands_back_objects_or_a_mapping() -> None:
    """A client that returns tool objects and one that returns a mapping must be
    read the same.

    A bridge that understood only one shape would report a whole server as empty
    on the other — which reads as "the server publishes nothing you declared",
    total drift, the loudest possible way to be wrong about a server that is
    perfectly fine.
    """
    class Published:
        def __init__(self, name: str, schema: dict) -> None:
            self.name, self.inputSchema = name, schema  # noqa: N815 — the MCP spelling

    schema = {"type": "object", "properties": {"amount": {"type": "string"}}}
    authored = {"issue-refund": {"amount": "money"}}
    assert check_against_authored([Published("issue-refund", schema)], authored) == ()
    assert check_against_authored({"issue-refund": schema}, authored) == ()
    assert check_against_authored(
        [{"name": "issue-refund", "inputSchema": schema}], authored
    ) == ()


def test_a_shape_pact_cannot_parse_is_not_reported_as_drift() -> None:
    """The instrument must not report its own limit as the subject's defect.

    An author's loosely-written shape is not evidence that the server disagrees
    with it, and a check that manufactured a mismatch from a string it could not
    read would be noise on exactly the workspaces least able to afford it.
    """
    assert (
        check_against_authored(
            {"issue-refund": {"type": "object", "properties": {"amount": {"type": "number"}}}},
            {"issue-refund": {"amount": "a currency amount, roughly"}},
        )
        == ()
    )


def test_the_authored_side_can_be_the_tools_the_agent_actually_has() -> None:
    """The convenience form, held to the same answer as the mapping form.

    A caller that has an `AgentSpec` should not have to rebuild `takes:` by hand
    to ask this question. `ToolSpec.parameters` is what the model is shown, which
    is what a server has to be able to accept.
    """
    spec = a_spec(a_workspace())
    published = {
        "payments": {
            "type": "object",
            "properties": {
                "order-number": {"type": "string"},
                "amount": {"type": "string"},
                "action": {"type": "string"},
            },
        }
    }
    assert check_against_authored(published, spec.tools) == ()
    # And it still sees a type that moved through that form.
    published["payments"]["properties"]["amount"] = {"type": "number"}
    said = check_against_authored(published, spec.tools)
    assert len(said) == 1 and "amount" in said[0], said


# ────────────────────────────────────────────────── on the worked example


def test_the_worked_example_reaches_two_servers_and_waits_on_the_one_that_pays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole chain, on the document `pact check` really produces.

    Nothing is constructed by this test: `refund-desk` uses `zendesk` and
    `payments`, those name `zendesk-server` and `payments-server`, and only the
    second has `asks-to-connect:`. So the ticketing connection opens and the
    money one waits — which is the sentence the author wrote across three files,
    arriving as behaviour with no host Python in between (D14).
    """
    if not (REPO / "target/debug/pact").exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    built = stub_client(monkeypatch)
    doc = json.loads(
        subprocess.run(
            [str(REPO / "target/debug/pact"), "show", str(EXAMPLE)],
            capture_output=True, text=True, check=True,
        ).stdout
    )
    spec = AgentSpec.from_document(doc, "refund-desk")
    credential = Asked(
        {"host/payments-credential": "sk-pay", "host/zendesk-credential": "sk-zen"}
    )

    conns = mcp_toolset_for(
        spec,
        resolve_endpoint=Asked(
            {"host/payments-mcp": "https://pay/mcp", "host/zendesk-mcp": "https://zen/mcp"}
        ),
        resolve_credential=credential,
    )

    state = {c.server: c for c in conns}
    assert sorted(state) == ["payments-server", "zendesk-server"]
    assert state["zendesk-server"].connected is True
    assert state["payments-server"].connected is False
    assert "may-we-connect" in state["payments-server"].why_not
    assert credential.asked == ["host/zendesk-credential"], (
        f"the payments credential was fetched before anybody consented: "
        f"{credential.asked}"
    )
    assert [b[1] for b in built] == ["zendesk-server"]
