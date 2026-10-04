"""The MCP export names the shape PACT's own FRD forbids, before anybody ships it.

`docs/30-FRD.md` FR-4.1.14 is not a preference. It REQUIRES the `2026-07-28` MCP
shape — stateless, no `initialize` handshake, no sessions, an MRTR
`input_required` retry in place of server-initiated requests — and it names
`2025-11-25` as the corpus shape not to target.

Until 2.54, everything reachable through `pydantic_ai.mcp` was the second one.
`pydantic-ai-slim` 2.54 pins `fastmcp-slim[client]>=3.3.0,<5` on its `mcp` extra,
which admits both eras: FastMCP 4 (MCP SDK v2, `LATEST_PROTOCOL_VERSION`
`2026-07-28`) opens a modern session with no `initialize` handshake, and FastMCP
3 (MCP SDK v1, `2025-11-25`) opens a session and awaits
`client.initialize_result`. So a PACT agent exported to Pydantic AI talks over
whichever shape the host's install speaks, and one of the two is the shape PACT's
own requirements rule out.

**That is tolerable on this path and it is not tolerable in silence.** Pydantic
AI owns the connection here — the handshake is in their process, on their pin,
through code PACT does not ship — which is the same reason the export may hand
over the loop at all. But an `ExportReport` that lists the ceilings and the
policy and says nothing about the wire is a report that has been read as *"the
losses are all accounted for"* by somebody who then deploys it. A known-forbidden
protocol shape omitted from the one artifact whose entire purpose is naming what
was lost is the exact silence `ExportReport.silent_losses` exists to prevent;
`silent_losses` cannot catch it, because the wire is not a field of the agent, so
it has to be caught here.

The second half is AD-71. It requires server-authored prose to be PINNED in a
tool snapshot, and `MCPToolset(include_instructions=True)` folds the server's
`initialize` instructions straight into the agent's instruction set.

**That half was re-decided in M5 W3 and the verdict survived, narrower.** The
snapshot now exists — `resources/<server>.yaml` carries `tool-snapshot-digest:`,
`tool-snapshot-taken-at:` and `tool-snapshot-max-age:`, and `mcp_bridge` pins the
server's prose and fences it. None of that reaches an EXPORTED agent, because the
export hands the loop to Pydantic AI: nothing downstream builds a system message
through `harness._system_for`, so nothing fences, and nothing calls
`mcp_bridge.check_snapshot`, so nothing pins. The test below used to assert that
`tool-snapshot-max-age` had zero hits in `spec/schema.yaml`; it went red the day
the field landed, which is exactly what it was for, and it now holds the narrower
claim instead. The drift check that does travel with the exported agent —
`mcp_bridge.check_against_authored` — holds tool NAMES and ARGUMENT SCHEMAS
against the authored ones, so it is PARTIAL mitigation and not AD-71: it cannot
see a sentence the server rewrote under a byte-identical `tools/list`, which is
the injection AD-71 was written from. A report that said "mitigated" would be
worse than one that said nothing, because it would be answered.

The three claims the report makes about the outside world — the pin, the SDK's
protocol version, and the absence of the schema field — are each checked against
the installed package or the file itself, not restated. A caveat that has gone
stale reads exactly like one that is true.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.pydantic_ai_interop import (  # noqa: E402
    from_pydantic_ai_spec,
    to_pydantic_ai_spec,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
SCHEMA = REPO / "spec" / "schema.yaml"
PACT_BIN = REPO / "target" / "debug" / "pact"

pydantic_ai = pytest.importorskip("pydantic_ai")

#: The key the export files the MCP sentence under. Held here as a literal rather
#: than imported from the module, so renaming it in the source without deciding
#: to fails a test instead of quietly moving where a reader has to look.
WHERE = "resources (resource-kind: mcp-server)"


@pytest.fixture(scope="module")
def document() -> dict:
    """The worked example, loaded the only way an adapter may load one (P-1).

    Both its tools `connect:` to `resource-kind: mcp-server` entries, so it is
    the real case rather than a fixture written to make this file pass.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def said(document: dict) -> str:
    """What the export says about the MCP servers this agent's tools reach."""
    _, report = to_pydantic_ai_spec(document, "refund-desk")
    assert WHERE in report.not_carried, (
        "the worked example's tools connect to two `mcp-server` resources and "
        f"the export said nothing about the protocol: {sorted(report.not_carried)}"
    )
    return report.not_carried[WHERE]


# ─────────────────────────────────── what the report must name


def test_the_export_names_the_requirement_this_path_cannot_meet(said: str) -> None:
    """Without the identifier, the caveat is an opinion.

    "MCP here is a bit old" is something a reader weighs against shipping today.
    `FR-4.1.14` is something they can look up, find is a MUST, and take to
    whoever owns the decision — and the two shape dates are what makes the gap
    checkable rather than a mood.

    Pinned as the CLAUSE and not as the bare token, and that is a measured
    correction rather than a preference. The first version of the sibling test
    below asserted only `"AD-71" in said`; the identifier occurs three times in
    this sentence, so deleting the whole verdict left a trailing mention behind
    and all sixteen tests passed — a mutation that removed the finding and
    changed nothing, which is precisely the shape this suite exists to stop. An
    identifier that appears somewhere is not a claim. The claim is the identifier
    next to the verb.
    """
    assert "FR-4.1.14 requires" in said, said
    assert "PACT's own FRD forbids" in said, (
        "the requirement is cited without being said to be BROKEN, which reads "
        "as background rather than as a report of a gap"
    )
    assert "2026-07-28" in said, "the required shape is not named, so the gap has no size"
    assert "2025-11-25" in said, "the shape actually spoken is not named"


def test_the_export_names_the_pin_that_makes_it_unmeetable(said: str) -> None:
    """A gap with no cause reads as an oversight somebody could just fix.

    The reason this export cannot reach the required shape is a dependency
    ceiling in somebody else's package, and a reader who is not told that will
    file it against this repository — or worse, "fix" it by hand-writing an
    MCP client to the `2026-07-28` shape and pointing Pydantic AI at it.
    """
    assert "fastmcp-slim" in said, said
    assert "<5" in said, "the ceiling itself is the fact — without it there is no cause"
    assert "FastMCP 4" in said and "FastMCP 3" in said, (
        "2.54's pin admits both eras, so which shape a run speaks is the host's "
        "install — a sentence naming one shape for every install would be false"
    )


def test_the_export_records_ad_71_and_calls_the_mitigation_partial(said: str) -> None:
    """A mitigation reported without its limit is a mitigation nobody checks again.

    AD-71's own worked injection is a server upgrade that changes a SENTENCE
    while `tools/list` is byte-identical. A drift check over the tool list cannot
    see that, so reporting it as the answer to AD-71 would close the item, and
    the next person to look would find a closed item and move on.
    """
    assert "AD-71 is NOT HELD" in said, (
        "the verdict is the claim, not the identifier. `AD-71` alone appears "
        f"three times in this sentence and survives its own deletion: {said}"
    )
    assert "PARTIAL mitigation" in said, (
        "the words doing the work are `PARTIAL mitigation` — one reported "
        f"without its limit is one nobody revisits: {said}"
    )
    assert "tool-snapshot-max-age" in said, (
        "the missing schema field is what makes the mitigation partial, and "
        "naming it is what lets a reader confirm the claim in one grep"
    )


def test_the_drift_check_the_report_calls_partial_is_the_one_that_exists(
    said: str,
) -> None:
    """A limit stated about no particular mechanism is a limit nobody can check.

    `mcp_bridge.check_against_authored` is the drift check M4 W2 ships, and its
    own docstring calls itself *"the live half of AD-71"*. It compares tool names
    and argument schemas — never a description, never the `initialize`
    instructions string — so the half it is NOT has to be said somewhere, and the
    export report is where a reader is already standing.

    Naming it is a coupling on purpose: if it is renamed or removed, the sentence
    in `_MCP_SHAPE` is describing a mechanism that is not there, and this fails
    rather than the report quietly becoming fiction.
    """
    from pact_adapters import mcp_bridge

    assert hasattr(mcp_bridge, "check_against_authored"), (
        "`pydantic_ai_interop._MCP_SHAPE` names `mcp_bridge.check_against_authored`"
        " as the drift check whose limit it is stating; the name has moved"
    )
    assert "check_against_authored" in said, said
    for half in ("NAMES", "ARGUMENT SCHEMAS"):
        assert half in said, (
            f"the report says the check is PARTIAL without saying which part it "
            f"does cover ({half}), which leaves a reader unable to tell what is "
            f"already guarded from what is not"
        )


def test_the_tolerance_is_stated_with_its_boundary(said: str) -> None:
    """"Tolerable" alone becomes precedent the first time somebody quotes it.

    This shape is acceptable ONLY because Pydantic AI owns the connection. A
    report that said it was tolerable and stopped is a report that will be cited
    to justify a PACT-owned MCP client built the same way — which would break
    FR-4.1.14 outright rather than merely sitting downstream of somebody else's
    pin.
    """
    assert "TOLERABLE ON THIS PATH ONLY" in said, said
    assert "not a precedent" in said, (
        "the boundary is the half that stops this becoming the house default"
    )


def test_the_export_still_loses_nothing_in_silence(document: dict) -> None:
    """The honesty line must not be bought by breaking the mechanism it serves.

    `silent_losses` is computed from the agent block, so adding a key that is not
    a field could not corrupt it — and asserting that here is what stops a later
    change filing the sentence somewhere that does.
    """
    _, report = to_pydantic_ai_spec(document, "refund-desk")
    assert report.silent_losses == (), report.in_words()


def test_the_person_reading_the_report_sees_both_identifiers(document: dict) -> None:
    """`in_words()` is what a human actually reads; a dict nobody prints is not a report.

    `exporting.main` writes `report.in_words()` to stdout and nothing else, so a
    sentence filed in a bucket that method skips would be a caveat that exists
    only in a test.
    """
    _, report = to_pydantic_ai_spec(document, "refund-desk")
    printed = report.in_words()
    assert "FR-4.1.14 requires" in printed, printed
    assert "AD-71 is NOT HELD" in printed, printed
    assert "PARTIAL mitigation" in printed, printed


def test_the_servers_the_caveat_is_about_are_named(said: str) -> None:
    """A protocol warning with no subject sends a reader through the whole tree.

    The worked example reaches two MCP servers and uses a third `uses:` entry
    that is a skill. Naming the two is the difference between "check your MCP
    usage" and "these two connections".
    """
    assert "payments-server" in said and "zendesk-server" in said, said
    assert "refund-policy" not in said, (
        "`refund-policy` is a skill, not a tool, and naming it as an MCP server "
        "would send somebody looking for a resource file that does not exist"
    )


# ─────────────────────────────────── and where it must stay quiet


def test_an_agent_that_opens_no_mcp_connection_is_told_nothing_about_one(
    document: dict,
) -> None:
    """The guard written one degree too broad would look exactly as green.

    `policy-checker` uses one skill and no tool, so it opens no MCP connection at
    all. A protocol caveat printed over every export is noise, and a report whose
    reader has learned to skip it has lost the caveat that matters — which is the
    same failure as not printing it, arrived at by the other road.
    """
    _, report = to_pydantic_ai_spec(document, "policy-checker")
    assert WHERE not in report.not_carried, report.in_words()
    assert not any("FR-4.1.14" in v for v in report.not_carried.values()), report.in_words()
    assert report.silent_losses == ()


def test_a_tool_that_reaches_something_other_than_an_mcp_server_is_not_reported_as_one() -> None:
    """The walk is `uses:` → `tools.connect:` → `resources.resource-kind:`, all three.

    Short-circuiting it — reporting whenever the workspace holds ANY MCP resource
    — would put the caveat on agents whose tools reach an address or ask a model,
    and a caveat that is wrong once is one a reader stops believing.

    The `sandbox` entry is the last hop and it is deliberately a kind the schema
    does not currently offer. `spec/schema.yaml` narrowed `resource-kind:` to the
    single choice `mcp-server` and says in terms that the others *"each return
    with the fields it needs"* — so the day one does, an export that had stopped
    reading the kind would announce an MCP protocol caveat over a sandbox.
    """
    document = {
        "agents": {"a": {"name": "A", "uses": ["ask", "elsewhere", "run-it"]}},
        "tools": {
            "ask": {"description": "put to a model", "says": "what do you think?"},
            "elsewhere": {"description": "an address", "url": "host/thing", "method": "get"},
            "run-it": {"description": "run something", "connect": "a-box"},
        },
        "resources": {
            "unreached": {"resource-kind": "mcp-server", "endpoint": "host/unreached"},
            "a-box": {"resource-kind": "sandbox", "endpoint": "host/a-box"},
        },
    }
    _, report = to_pydantic_ai_spec(document, "a")
    assert WHERE not in report.not_carried, report.in_words()


def test_one_tool_reaching_one_mcp_server_is_enough(document: dict) -> None:
    """`fraud-checker` reaches a single server, and one connection is the case.

    A walk that only fired on the multi-server agent would pass every test above
    while leaving the commonest shape — one desk, one server — unreported.
    """
    _, report = to_pydantic_ai_spec(document, "fraud-checker")
    assert WHERE in report.not_carried, report.in_words()
    assert "zendesk-server" in report.not_carried[WHERE]
    assert "payments-server" not in report.not_carried[WHERE], (
        "only the servers this agent's own tools reach belong in its report"
    )


# ─────────────────────────────────── the same sentence on the way in


def test_both_import_doors_say_the_one_sentence_about_the_protocol() -> None:
    """An author who wrote YAML and one who wrote Python must be told the same thing.

    `_read_capabilities` and `_live_capabilities` are two readers on purpose,
    because a spec entry and a capability object are different shapes. What they
    must never differ on is the answer — the same agent warned through one door
    and not the other is portability that is merely technically true.
    """
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import MCP
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.toolsets import FunctionToolset

    from pact_adapters.pydantic_ai_interop import from_pydantic_ai_agent

    _, filed = from_pydantic_ai_spec({"model": "test", "capabilities": ["MCP"]})
    _, live = from_pydantic_ai_agent(
        Agent(
            TestModel(),
            capabilities=[MCP("https://example.test/mcp", local=FunctionToolset([]))],
        )
    )
    where = "capabilities.MCP.wire-shape"
    assert where in filed.not_portable, sorted(filed.not_portable)
    assert where in live.not_portable, sorted(live.not_portable)
    assert filed.not_portable[where] == live.not_portable[where], (
        "the two doors describe the same protocol in two different sentences"
    )
    assert "FR-4.1.14" in filed.not_portable[where]
    assert "AD-71" in filed.not_portable[where]
    assert filed.silent_drops == () and live.silent_drops == ()


def test_the_capability_still_crosses_and_is_not_merely_warned_about() -> None:
    """The caveat must not be paid for with the mapping.

    A warning that also stopped `MCP` becoming `uses: [mcp]` would be this
    importer refusing a capability it can translate, dressed as honesty.
    """
    agent, report = from_pydantic_ai_spec({"model": "test", "capabilities": ["MCP"]})
    assert agent["uses"] == ["mcp"]
    assert report.mapped["capabilities.MCP"]


# ─────────────────────────────────── the claims, checked against the world


def test_the_pin_the_report_names_is_the_pin_that_is_installed(said: str) -> None:
    """A caveat about somebody else's dependency ceiling goes stale silently.

    The day `pydantic-ai-slim` moves to `fastmcp-slim>=4`, this report becomes a
    confident false statement about the protocol a run speaks — which is worse
    than the silence it replaced, because it has been read and believed. So the
    ceiling is read off the installed distribution's own metadata.
    """
    from importlib.metadata import requires

    declared = [r for r in (requires("pydantic-ai-slim") or []) if "fastmcp" in r]
    assert declared, "pydantic-ai-slim no longer declares fastmcp at all"
    assert any(">=3.3.0,<5" in r.replace(" ", "") or "<5,>=3.3.0" in r.replace(" ", "")
               for r in declared if "extra == 'mcp'" in r or 'extra == "mcp"' in r), (
        f"the pin moved: {declared}. The honesty line in `pydantic_ai_interop."
        "_MCP_SHAPE` names `fastmcp-slim[client]>=3.3.0,<5` and must be rewritten "
        "against what is actually pinned — including deleting its FastMCP 3 half, "
        "if the new floor is 4 and so always speaks the `2026-07-28` shape "
        "FR-4.1.14 requires"
    )
    assert "fastmcp-slim" in said


def test_the_protocol_version_the_report_names_is_the_one_the_sdk_ships(said: str) -> None:
    """`2025-11-25` is quoted as a fact about the installed SDK, so it is read from it.

    If the SDK ships the `2026-07-28` shape and the report still says otherwise,
    an author is being warned off a path that has since become the compliant one
    — and the fix is to delete the caveat, which nobody does for a warning nobody
    is told is wrong.
    """
    types = pytest.importorskip("mcp.types")
    assert types.LATEST_PROTOCOL_VERSION in said, (
        f"the SDK now speaks {types.LATEST_PROTOCOL_VERSION!r} and the report "
        "still names `2025-11-25`"
    )


def test_the_snapshot_ad_71_asks_for_exists_and_this_path_still_does_not_use_it(
    said: str,
) -> None:
    """The grep that decides whether the AD-71 half is true at all.

    This test used to assert the OPPOSITE — that `tool-snapshot-max-age` had zero
    hits in `spec/schema.yaml` — because for as long as that was so, "AD-71 is not
    held" was a statement about PACT and needed no path attached. M5 W3 added the
    field, this went red on the same commit, and the report was re-decided rather
    than the assertion relaxed. That is the whole reason it was written as a grep:
    a caveat whose premise has quietly become false reads exactly like one that is
    still true.

    The claim it now holds is the narrower one, and it is narrower in the
    direction that costs something to get wrong. The mechanism exists; this path
    does not go through it, because the export hands the loop away. If a later
    change makes the export fence or pin server prose, both halves below go red
    and the verdict is re-decided again.
    """
    assert SCHEMA.exists(), SCHEMA
    text = SCHEMA.read_text()
    assert "tool-snapshot-max-age" in text, (
        "`spec/schema.yaml` has lost `tool-snapshot-max-age`, so the report is "
        "citing a snapshot mechanism that is no longer there — re-decide "
        "`pydantic_ai_interop._MCP_SHAPE`"
    )
    assert "The snapshot AD-71 asks for now exists" in said, (
        "the report claimed no snapshot existed and the schema now carries one; "
        "the two must say the same thing or the caveat is fiction"
    )
    # The fix line is the half a reader can act on. Without it the paragraph says
    # "this is broken here" and stops, which is how a known limit becomes a
    # deployed one.
    assert "mcp_bridge.check_snapshot" in said, (
        "the report names the gap without naming the call that closes it"
    )


def test_the_two_mechanisms_the_report_names_as_existing_really_do(said: str) -> None:
    """A caveat that cites a mechanism by name is only honest while it is there.

    `_MCP_SHAPE` now makes a POSITIVE claim — that PACT has a snapshot and a fence
    — in order to bound the negative one about this path. A positive claim about
    code is the kind that rots silently: rename or delete either function and the
    sentence goes on reassuring a reader that the mechanism they are being sent to
    exists.
    """
    from pact_adapters import harness, mcp_bridge

    for name in ("digest_of", "check_snapshot", "quarantined"):
        assert hasattr(mcp_bridge, name), (
            f"`_MCP_SHAPE` names `mcp_bridge.{name}` as the mechanism that exists; "
            f"it does not"
        )
        assert name in said, said
    # The placement half. `_system_for` is what refuses unfenced external text,
    # and the report says so — so its absence would leave the sentence describing
    # a guard that is not there.
    assert hasattr(harness, "_system_for"), "`_MCP_SHAPE` names `harness._system_for`"
    assert "harness._system_for` refuses external text without" in said, said
