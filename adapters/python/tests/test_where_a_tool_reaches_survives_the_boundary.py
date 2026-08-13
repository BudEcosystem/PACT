"""A tool arrives at the executing side knowing WHERE it reaches, not just what it is called.

`ToolSpec` carried a name, a sentence, an argument list and the `bind:` lines,
and `AgentSpec.from_document` never looked at `connect:`, `url:` or `says:` —
the three lines that say where a call actually goes. The consequence is not
subtle and it is not hypothetical: `connect: payments-server` reached the model
as the tool name `payments` and reached nothing else, so no adapter on this side
of the boundary could open the connection the author wrote down, and
`pact export mcp` could not be written at all. The middle hop that
`examples/refund-desk/tools/payments.yaml` argues at length is load-bearing —
`uses:` names a TOOL, `connect:` names a SERVER, deliberately spelled
differently — was checked by the loader and then dropped at this wall.

`crates/pact-loader/src/reach.rs` guarantees exactly one of the three is
written. These tests hold the ADAPTER to reading whichever one it was, and to
carrying the server a `connect:` names — endpoint, credential reference and
connection consent — so that a bridge never re-walks `resources:` (invariant
P-1: the adapter sees the loaded document only).

Everything here goes through `AgentSpec.from_document`, which is the authored
path. A test that built a `Reach` itself would prove the dataclass works and say
nothing about whether the author's line reaches it, which is the defect this
repository has shipped five times.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec, Reach, ResourceSpec, WAYS_A_TOOL_REACHES  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def worked_example() -> dict[str, Any]:
    """The real worked example through the real loader.

    Not a fixture written here: the question is what an AUTHOR's tree produces,
    and a document this file wrote would be a document this file already agrees
    with.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def one_tool(**lines: Any) -> dict[str, Any]:
    """A workspace whose single agent uses a single tool written as `lines`.

    The smallest document that exercises the boundary, so that a failure names
    the reach line rather than something else the worked example also has.
    """
    return {
        "agents": {"desk": {"description": "x", "instructions": "y", "uses": ["thing"]}},
        "tools": {"thing": {"description": "The one tool.", **lines}},
    }


def reach_of(doc: dict[str, Any]) -> "Reach | None":
    spec = AgentSpec.from_document(doc, "desk")
    assert len(spec.tools) == 1, f"the fixture should build one tool: {spec.tools}"
    return spec.tools[0].reaches


# ─────────────────────────── all three, exhaustively ───────────────────────────


def test_every_way_a_tool_can_reach_somewhere_survives_the_boundary() -> None:
    """Not "the three I remembered" — every way the table names.

    `WAYS_A_TOOL_REACHES` mirrors `WAYS` in `crates/pact-loader/src/reach.rs`,
    and the whole point of both being tables is that a fourth transport costs a
    row rather than a new branch. A reader that handled two of three would leave
    the third loading cleanly and reaching nothing, which is exactly the shape
    `runs-as:` had before it was deleted: authored, validated, and answered by
    `error: no tool named ...` on the first call.
    """
    wrote = {"connect": "payments-server", "url": "host/payments-api", "says": "Refund this."}
    assert set(wrote) == set(WAYS_A_TOOL_REACHES), (
        "a way to reach somewhere was added to `ir.py` and this test does not "
        "write it — which is how the third one comes to be read by nothing"
    )
    for way in WAYS_A_TOOL_REACHES:
        lines: dict[str, Any] = {way: wrote[way]}
        if way == "url":
            lines["method"] = "post"  # the schema's `needs-also:` demands it
        reach = reach_of(one_tool(**lines))
        assert reach is not None, f"`{way}:` reached the adapter as nothing at all"
        assert reach.kind == way, f"`{way}:` arrived spelled `{reach.kind}`"
        assert reach.value == wrote[way], f"`{way}:` lost its value: {reach.value!r}"


def test_the_two_connected_tools_of_the_worked_example_know_which_server_they_reach(
    worked_example: dict[str, Any],
) -> None:
    """The shipped tree, not a fixture. Both of its tools are `connect:` tools.

    `payments` and `zendesk` are spelled differently from `payments-server` and
    `zendesk-server` on purpose, so a reader that skipped the middle hop and
    used the tool's own name would have been right by coincidence — which is
    what `LoadReport` did for a round, taking the connection wait off the
    scheduler's list the moment somebody renamed a tool.
    """
    spec = AgentSpec.from_document(worked_example, "refund-desk", source=EXAMPLE)
    reached = {t.name: t.reaches for t in spec.tools}
    assert set(reached) == {"payments", "zendesk"}, sorted(reached)
    for tool, server in (("payments", "payments-server"), ("zendesk", "zendesk-server")):
        reach = reached[tool]
        assert reach is not None, f"`{tool}` reached the run with no idea where it goes"
        assert reach.kind == "connect", f"`{tool}` is a `connect:` tool: {reach.kind!r}"
        assert reach.value == server, (
            f"`{tool}` reaches {reach.value!r} — the tool's own name is not the "
            f"server's, and the difference is the hop that is being tested"
        )


# ───────────────────────── the server a `connect:` names ─────────────────────────


def test_the_server_arrives_with_its_endpoint_credential_reference_and_consent(
    worked_example: dict[str, Any],
) -> None:
    """The three lines a bridge needs, resolved once, at the boundary.

    Without them on `ToolSpec`, anything that wanted to open the connection
    would have to walk `resources:` again — and invariant P-1 says an adapter is
    handed the loaded document and never the tree, so "walk it again" means
    every reader keeping its own copy of the hop. `asks-to-connect:` in
    particular is a human consent gate on money: the run stops before anything
    goes over the payments connection, and a bridge that did not carry the line
    would connect first and ask afterwards.
    """
    spec = AgentSpec.from_document(worked_example, "refund-desk", source=EXAMPLE)
    payments = next(t for t in spec.tools if t.name == "payments")
    assert payments.reaches is not None
    server = payments.reaches.resource
    assert server is not None, (
        "`connect: payments-server` resolved to no server — the tool knows a "
        "name and a bridge would have to find the endpoint itself"
    )
    assert server.name == "payments-server"
    assert server.kind == "mcp-server"
    assert server.endpoint == "host/payments-mcp"
    assert server.auth_by_reference == "host/payments-credential", (
        "where the credential is kept is what the host resolves; without it the "
        "bridge has an address it may not authenticate to"
    )
    assert server.asks_to_connect == "may-we-connect", (
        "the consent gate on the payments connection has to travel with the "
        "connection — it is what stands between a refund and a person's yes"
    )


def test_the_credential_itself_never_crosses_the_boundary() -> None:
    """`auth:` carries a reference and nothing else, whatever else is in it.

    The schema refuses `bearer-token:` by name because a spec file may not
    contain a credential, ever. Carrying the `auth:` block whole would undo that
    the first time somebody's loader was older than their document: the secret
    would arrive on the far side, in an object adapters print, log and put in
    conformance artifacts.
    """
    doc = one_tool(connect="payments-server")
    doc["resources"] = {
        "payments-server": {
            "resource-kind": "mcp-server",
            "endpoint": "host/payments-mcp",
            "auth": {"by-reference": "host/payments-credential", "bearer-token": "sk-live-2f9c"},
        }
    }
    reach = reach_of(doc)
    assert reach is not None and reach.resource is not None
    assert reach.resource.auth_by_reference == "host/payments-credential"
    assert "sk-live-2f9c" not in repr(reach), (
        "a value from the `auth:` block reached the adapter. Only the reference "
        f"may travel: {reach.resource}"
    )


def test_a_connect_naming_a_server_this_workspace_has_not_got_keeps_the_name_and_no_server() -> None:
    """Two different facts, kept apart.

    `names: resources` refuses this at check time, at the line the author typed.
    If one arrives anyway, "no such server" must not look like "a server with no
    endpoint": the first is a typo somebody fixes in a file and the second is a
    resource nobody finished writing, and an empty `ResourceSpec` would make a
    bridge dial an empty endpoint for both.
    """
    doc = one_tool(connect="paymnets-server")
    doc["resources"] = {"payments-server": {"resource-kind": "mcp-server", "endpoint": "e"}}
    reach = reach_of(doc)
    assert reach is not None
    assert reach.kind == "connect" and reach.value == "paymnets-server", (
        "the name the author wrote is what a diagnostic has to quote back"
    )
    assert reach.resource is None, f"a server was invented for a name nobody published: {reach.resource}"


# ───────────────────────────── `url:` and `says:` ─────────────────────────────


def test_a_url_tool_carries_the_address_and_the_method_beside_it() -> None:
    """`url:` owes a `method:` — the schema says so with `needs-also:` — and a
    call cannot be made without both. An address that arrived without its verb
    would leave the reader choosing one, and the schema deleted exactly that
    advice ("write `post` if you are unsure") for contradicting the checker.
    """
    reach = reach_of(one_tool(url="host/payments-api", method="post"))
    assert reach == Reach(kind="url", value="host/payments-api", method="post"), (
        f"a `url:` tool did not round-trip: {reach}"
    )
    assert reach is not None and reach.resource is None, (
        "a `url:` tool reaches an address, not one of this workspace's servers"
    )


def test_a_method_written_beside_a_connect_does_not_travel_as_if_it_meant_something() -> None:
    """`needs-also:` runs one way: `url:` owes `method:`, and nothing owes it to
    a `connect:`. A `method: delete` sitting beside a `connect:` line is
    governed by nothing and refused by nothing, so carrying it across would tell
    a bridge the author had chosen a verb for a connection where they had not.
    """
    reach = reach_of(one_tool(connect="payments-server", method="delete"))
    assert reach is not None and reach.method == "", (
        f"a `method:` that governs nothing arrived as if it did: {reach}"
    )


def test_a_says_tool_carries_the_wording_and_reaches_no_system() -> None:
    """A `says:` tool is a question put to a model. Its wording IS where it
    reaches, so losing it leaves a tool with a name, an argument list and
    nothing to ask.
    """
    reach = reach_of(one_tool(says="Decide whether this refund is in policy."))
    assert reach == Reach(kind="says", value="Decide whether this refund is in policy."), (
        f"a `says:` tool did not round-trip: {reach}"
    )


# ─────────── the two shapes the loader refuses, if one arrives anyway ───────────


def test_a_tool_that_names_nowhere_arrives_as_an_absence_and_not_as_a_guess() -> None:
    """`reach.rs` makes this an error, and a host may still build a document by
    hand and hand it here.

    The answer that must never be given is a default. A `ToolSpec` that quietly
    read `connect: <the tool's own name>` would send a refund to a server nobody
    wrote down, and the run would look exactly like a working one.
    """
    assert reach_of(one_tool()) is None
    # A half-finished line is the commonest way to arrive here, and it is the
    # one the loader's own test singles out.
    assert reach_of(one_tool(connect="   ")) is None, "an empty `connect:` is not a place"


def test_a_tool_that_names_two_places_says_so_rather_than_picking_one() -> None:
    """The shape `reach.rs` calls the one a portable artifact may not permit:
    two runtimes reading the same folder legitimately doing different things.

    So the reader may not silently pick. It keeps the first in schema order —
    something has to be first — and NAMES the rest, which is what lets a bridge
    refuse the tool instead of reproducing the ambiguity at run time.
    """
    reach = reach_of(one_tool(connect="payments-server", url="host/payments-api", method="post"))
    assert reach is not None
    assert reach.also_written == ("url",), (
        f"the second place this tool names was dropped, so nothing downstream "
        f"can tell this document from a well-formed one: {reach}"
    )
    assert reach.kind == "connect", "the first in schema order, and it is not a decision"


def test_a_well_formed_tool_says_nothing_was_written_twice(
    worked_example: dict[str, Any],
) -> None:
    """The control arm for the test above.

    If `also_written` were populated for every tool, or never populated at all,
    that test would pass while proving nothing. The shipped example is the case
    that must stay empty.
    """
    spec = AgentSpec.from_document(worked_example, "refund-desk", source=EXAMPLE)
    for tool in spec.tools:
        assert tool.reaches is not None and tool.reaches.also_written == (), (
            f"`{tool.name}` passed `pact check` and is reported ambiguous here"
        )


def test_a_hand_built_tool_spec_still_reaches_nowhere_by_default() -> None:
    """Every fixture in this suite that writes `ToolSpec("zendesk", "read the
    ticket")` gets `reaches=None`, and that is the honest answer: nothing about
    that object says where it goes. The field is not allowed to acquire a
    default that means "connect", which would make dozens of existing fixtures
    silently claim a server.
    """
    from pact_adapters.ir import ToolSpec

    assert ToolSpec("zendesk", "read the ticket").reaches is None
    # And the shape a host builds deliberately survives untouched.
    server = ResourceSpec(name="s", kind="mcp-server", endpoint="host/x")
    assert ToolSpec("t", "d", reaches=Reach("connect", "s", resource=server)).reaches.resource is server
