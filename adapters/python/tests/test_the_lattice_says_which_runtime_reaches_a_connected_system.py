"""`connected_tools` — the lattice column that says whether a `connect:` line
reaches the system it names.

## What was missing, and what it cost

`ir.ToolSpec.reaches` carries where a tool goes: one of `connect:`, `url:` and
`says:` (`ir.WAYS_A_TOOL_REACHES`), with the `resources:` entry a `connect:`
names already resolved. The lattice — six keys, published by every adapter,
compared across two runtimes — said nothing about it. So the one question an
author asks about a tool that touches a payment server, *"will this call get
there on the runtime I picked?"*, was the one question the portability instrument
could not answer, and the answer arrived instead as `error: no tool named
'payments'` on the first refund. That is the silent degradation T7 forbids and
FR-4.1.5 requires be reported **before** execution.

## Why the key is spelled `connected_tools`

Not `mcp_tools`. `ResourceSpec.kind` is *carried rather than assumed* — the
schema has one `resource-kind:` today and `ir.py` says in as many words that a
bridge building an MCP client for whatever it is handed *"would be reading a
field that does not say what it thinks it says the first time a second kind
returns"*. A lattice key named after today's one wire format would put that
assumption into the instrument meant to survive it.

Not `connect_transport` either: `Transport` is already the name of the protocol
every one of these classes implements (`harness.Transport`), so a key with
`transport` in it would name the thing rather than the feature. `connected_tools`
sits in the family the other keys already form — `tool_calls`,
`parallel_tool_calls`, `text_with_tool_calls` — and names the IR feature: a tool
that reaches a connected system.

## What the four words mean here

`unsupported` is honest and it is the common case: a transport bound to a MODEL
has no door a `connect:` line can leave by, so the call reaches the model as a
name and the system never. `native` is Pydantic AI's alone, because
`mcp_bridge._live` builds a `pydantic_ai.mcp.MCPToolset` — that runtime's own
client — and `pydantic_ai_interop.build_agent` hands it to a real `Agent`.

Being exact about the door matters, and this file pins it:
:func:`test_the_door_the_native_claim_is_about_is_the_bridge_and_not_the_loop`
holds that even on Pydantic AI, `harness.run` executes host-supplied
implementations and owns no client — so `native` is a claim about the runtime
binding, in the same way LangGraph's `durable_resume: native` is a claim about
its checkpointer rather than about `model_call`.

## Why the tests below are shaped the way they are

L1: a green suite is not evidence. Every assertion here is anchored to something
measured — the word a transport publishes is checked against the module that
actually constructs the client, and against what a `connect:` tool actually does
when it is run. Nothing asserts a list of expected words on its own, because a
list of expected words is a copy of the code that goes green when the code is
wrong in the same direction.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import mcp_bridge  # noqa: E402
from pact_adapters.harness import ToolCall, run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.a2a_transport import A2ATransport  # noqa: E402
from pact_adapters.transports.anthropic_transport import AnthropicTransport  # noqa: E402
from pact_adapters.transports.autogen_transport import AutoGenTransport  # noqa: E402
from pact_adapters.transports.langchain_transport import LangChainTransport  # noqa: E402
from pact_adapters.transports.langgraph_transport import LangGraphTransport  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from pact_adapters.transports.ollama_transport import OllamaTransport  # noqa: E402
from pact_adapters.transports.openai_agents_transport import (  # noqa: E402
    OpenAIAgentsTransport,
)
from pact_adapters.transports.pydantic_ai_transport import PydanticAITransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TS_TRANSPORT = REPO / "adapters" / "typescript" / "src" / "vercel-transport.ts"
OUT_OF_TREE = REPO / "adapters" / "out-of-tree" / "echo_adapter"

KEY = "connected_tools"
VOCABULARY = {"native", "emulated", "degraded", "unsupported"}


def script() -> Script:
    """One turn that calls the connected tool, then one that answers.

    The model reaching for `payments` is the whole event under test: a lattice
    entry about a `connect:` line is worth nothing on a run where nobody calls
    the tool.
    """
    return Script([
        Turn("Issuing the refund.", (ToolCall("payments", {"amount": 30}),)),
        Turn("Refunded."),
    ])


def every_transport() -> dict[str, Any]:
    """One live instance of each of the nine transports in this package.

    Constructed rather than listed by name-and-word, because the point is to ask
    the object what it publishes. `ollama` and `a2a` take an address instead of a
    script and neither opens a socket to build; the two of them are also the
    transports absent from `test_portability.TRANSPORTS`, which is why this file
    does not reuse that mapping — the invariant is about every adapter that
    ships, not every adapter that is in the conformance report.
    """
    return {
        "reference": ReferenceTransport(script()),
        "pydantic-ai": PydanticAITransport(script()),
        "langgraph": LangGraphTransport(script()),
        "langchain": LangChainTransport(script()),
        "autogen": AutoGenTransport(script()),
        "openai-agents": OpenAIAgentsTransport(script()),
        "anthropic": AnthropicTransport(script()),
        "ollama": OllamaTransport("a-model-nobody-serves"),
        "a2a": A2ATransport("http://127.0.0.1:9/agent"),
    }


def a_workspace(*, server: str = "payments-server") -> dict[str, Any]:
    """One agent, one tool, one server, written the way an author writes it.

    A document and not a hand-built `AgentSpec`, so the walk that puts a `Reach`
    on the tool (`uses:` -> `tools.payments.connect` -> `resources.<server>`) is
    the real one. A test that assembled the dataclass itself would prove nothing
    about whether the author's own line survives the adapter boundary.
    """
    return {
        "agents": {"desk": {"instructions": "Decide the refund.", "uses": ["payments"]}},
        "tools": {
            "payments": {
                "description": "Where refunds are issued.",
                "connect": server,
                "actions": {
                    "issue-refund": {
                        "description": "Send money back.",
                        "takes": {"amount": "money"},
                    }
                },
            }
        },
        "resources": {
            server: {
                "resource-kind": "mcp-server",
                "endpoint": "host/payments-mcp",
                "auth": {"by-reference": "host/payments-credential"},
            }
        },
    }


@pytest.fixture()
def spec() -> AgentSpec:
    """The agent, with the `connect:` line already resolved onto its tool."""
    return AgentSpec.from_document(a_workspace(), "desk")


# ───────────────────────────────────────── every adapter answers the question


def test_every_adapter_says_whether_a_connect_line_reaches_the_system_it_names() -> None:
    """Invariant P-2, on the newest column.

    An adapter that omits a feature cannot be compared, and a column present on
    eight adapters and missing from the ninth is worse than one nobody has: the
    comparison still gets made, and the missing row reads as a `no` it never
    said. `test_portability.py` holds the key SETS equal; this holds the one key
    this file is about, so removing it from a single transport fails here by
    name rather than as an opaque set difference.
    """
    published = {name: t.lattice() for name, t in every_transport().items()}
    missing = sorted(n for n, lat in published.items() if KEY not in lat)
    assert not missing, (
        f"{missing} publish no {KEY!r}, so an author cannot compare them on the "
        f"one question a `connect:` tool asks"
    )
    outside = {n: lat[KEY] for n, lat in published.items() if lat[KEY] not in VOCABULARY}
    assert not outside, f"FR-4.1.4 admits four words and these are not among them: {outside}"


def test_the_second_runtime_and_the_out_of_tree_exemplar_answer_it_too() -> None:
    """The two adapters a Python-only test would silently skip.

    The Vercel port runs in Node, so `test_all_seven_targets_publish_the_same_
    lattice_features` needs a working `node` and is skipped where there is none —
    which means a machine without Node could drop the key from the TypeScript
    port and see nothing go red. The out-of-tree echo adapter is skipped by every
    key-set test there is, on purpose (E-1: a new adapter costs zero core
    changes), and is also the exemplar an author copies, so an exemplar quietly
    short a column teaches the omission.

    Read from the SOURCE for exactly that reason: this assertion must hold on a
    box with no Node and no way to import an out-of-tree package.
    """
    ts = TS_TRANSPORT.read_text(encoding="utf-8")
    assert re.search(rf"\b{KEY}\s*:\s*\"(native|emulated|degraded|unsupported)\"", ts), (
        f"{TS_TRANSPORT} publishes no {KEY!r}, so the two ports cannot be "
        f"compared on it"
    )

    echo = (OUT_OF_TREE / "transport.py").read_text(encoding="utf-8")
    assert re.search(rf"\"{KEY}\"\s*:\s*\"(native|emulated|degraded|unsupported)\"", echo), (
        f"the out-of-tree exemplar omits {KEY!r}, which is the omission the next "
        f"adapter author would copy"
    )


# ─────────────────────────────── the word is tied to the code that reaches out


def test_only_the_runtime_that_owns_the_client_claims_a_connect_line_reaches() -> None:
    """The claim is checked against the module that actually builds the client.

    A lattice is only worth reading if a value cannot be raised by editing the
    lattice. `mcp_bridge._live` is the one place in this package that constructs
    an MCP client, and which SDK it constructs is read out of its source here
    rather than named — so an adapter can declare better than `unsupported` only
    while the client belongs to its runtime.

    Without this, `connected_tools: native` on a transport that binds a bare
    `BaseChatModel` would be a one-word edit, published in the matrix, believed
    by an author, and answered at run time by `error: no tool named 'payments'`.
    """
    source = inspect.getsource(mcp_bridge._live)
    imported = re.search(r"from\s+([\w.]+)\s+import\s+MCPToolset", source)
    assert imported, (
        "`mcp_bridge._live` no longer imports an MCP client, so nothing in this "
        f"package reaches a `connect:` server and no adapter may declare {KEY!r} "
        "as anything but `unsupported`"
    )
    owner = imported.group(1).split(".")[0]
    assert owner == "pydantic_ai", owner

    # `native` is the RUNTIME-owns-the-client claim, and it stays anchored to the
    # one place that builds that runtime's client.
    native = sorted(
        name for name, t in every_transport().items() if t.lattice()[KEY] == "native"
    )
    assert native == ["pydantic-ai"], (
        f"{native} claim a `connect:` line reaches NATIVELY, and the only "
        f"runtime client in this package is {owner}'s. Either the claim is false "
        f"or the bridge grew a door this test has not been told about."
    )

    # `emulated` is the other claim in this lattice's vocabulary — PACT provides
    # it ABOVE the transport — and it grew a door after this test was first
    # written: `pact_adapters/mcp/` is PACT's OWN client, and
    # `mcp.calling.tool_impls_for` turns a `connect:` tool into the
    # `harness.ToolFn` the loop already executes. That reaching belongs to PACT
    # rather than to whatever binds the model, so it is the same word on every
    # harness-driven target.
    #
    # Anchored, not asserted as a list of names, for this file's own reason: a
    # value must not be raisable by editing the lattice. The word is legal only
    # while that function exists to make it true, so deleting PACT's client fails
    # here rather than quietly leaving eight adapters claiming a door that closed.
    emulated = sorted(
        name for name, t in every_transport().items() if t.lattice()[KEY] == "emulated"
    )
    if emulated:
        from pact_adapters.mcp import calling as pact_mcp_calling

        assert callable(getattr(pact_mcp_calling, "tool_impls_for", None)), (
            f"{emulated} claim a `connect:` line reaches by emulation, which in "
            "this lattice means PACT provides it above the transport — but "
            "`pact_adapters.mcp.calling.tool_impls_for`, the function that turns "
            "a `connect:` tool into a `harness.ToolFn`, is gone. Nothing "
            "emulates it, so the honest word is `unsupported`."
        )


# ─────────────────────────────────────────── and against what a run actually does


@pytest.mark.parametrize(
    "name",
    sorted(n for n, t in every_transport().items() if t.lattice()[KEY] == "unsupported"),
)
def test_a_connect_line_on_a_model_only_runtime_reaches_nothing(
    spec: AgentSpec, name: str
) -> None:
    """`unsupported` is measured, not asserted.

    Every transport that declares it is run against an agent whose only tool
    carries a real `connect:` line, with the model scripted to call it and no
    implementation supplied — and the call comes back `error: no tool named
    'payments'`. That is the outcome the word predicts, and an adapter whose word
    stopped matching it would be telling an author their reviewed payment server
    is being reached by a run that reaches nothing.

    Two of the nine are declared here and run elsewhere: `a2a` needs an agent
    behind its URL and `ollama` needs a served model behind its endpoint, and
    neither absence is a fact about this column. Their WORD is still asserted on
    the line above, before the skip, so dropping the key or raising it on either
    fails here — the skip costs the behavioural half and not the declaration.

    `a2a` is in this set for a reason worth stating: the remote agent behind that
    URL may hold connections of its own, and none of them is a `connect:` line of
    this author's.
    """
    transports = every_transport()
    assert transports[name].lattice()[KEY] == "unsupported"
    if name in ("a2a", "ollama"):
        pytest.skip(f"{name} needs a live server; its word is held by the class rule")

    # The document really does carry the line. Without this the whole test would
    # pass on a spec with no `connect:` at all — the shape of green that proves
    # nothing.
    (tool,) = spec.tools
    assert tool.reaches is not None and tool.reaches.kind == "connect", tool.reaches
    assert tool.reaches.resource is not None, "the `resources:` entry did not resolve"

    result = asyncio.run(run(spec, transports[name], "Can I get a refund?", {}))
    (said,) = result.steps[0].tool_results
    assert said == "error: no tool named 'payments'", said


def test_the_door_the_native_claim_is_about_is_the_bridge_and_not_the_loop(
    spec: AgentSpec,
) -> None:
    """What `native` does and does not promise, pinned so nobody has to guess.

    Pydantic AI's `native` is a claim about `mcp_bridge` /
    `pydantic_ai_interop.build_agent` — the door that turns a `connect:` line
    into that runtime's own client. It is NOT a claim that `harness.run` will
    dial the server for you: the harness executes host-supplied implementations
    and owns no client on any target, so the same run that is `unsupported`
    everywhere else is unimplemented here too.

    Stated as a test rather than a docstring because the two readings differ by
    exactly one support call: an author who reads `native` as *"the loop connects
    for me"* ships an agent whose refunds are answered `error: no tool named
    'payments'` and has been told, by the matrix, that this target was the one
    that worked.
    """
    pyd = PydanticAITransport(script())
    assert pyd.lattice()[KEY] == "native"

    result = asyncio.run(run(spec, pyd, "Can I get a refund?", {}))
    (said,) = result.steps[0].tool_results
    assert said == "error: no tool named 'payments'", (
        "`harness.run` reached a connected server by itself. If that is now true "
        "it is true on every target, and this column stops being about the "
        "runtime binding."
    )


def test_the_runtime_that_claims_it_either_builds_a_client_or_says_why_not(
    spec: AgentSpec,
) -> None:
    """A `native` that quietly returns nothing is the failure T7 names.

    The bridge is called for real — no stubbed `_live`, no patched `why_no_mcp` —
    with the host answering both references. On a machine with the MCP client
    installed a live client is built; on one without (the ordinary air-gapped
    case, and this box: `pydantic_ai.mcp` raises at import without `fastmcp`) the
    tools are deferred and the reason says what to install. What must never
    happen is the third thing: no connection, no reason, and an agent that
    quietly cannot do half its job.
    """
    (conn,) = mcp_bridge.mcp_toolset_for(
        spec,
        resolve_endpoint=lambda ref: "https://pay.example/mcp",
        resolve_credential=lambda ref: "resolved-by-the-host",
    )
    assert conn.server == "payments-server"
    assert conn.tools == ("payments",), (
        "the tools vanished with the connection, which takes the agent's own "
        "capability off the model's list without saying so"
    )
    assert conn.toolset is not None
    if conn.connected:
        assert conn.why_not == ""
    else:
        assert conn.why_not, (
            "no client and no reason — the exact silence a declared `native` "
            "must never resolve to"
        )
        assert mcp_bridge.why_no_mcp() in conn.why_not or "fix:" in conn.why_not, (
            f"the reason names nothing to do about it: {conn.why_not}"
        )
