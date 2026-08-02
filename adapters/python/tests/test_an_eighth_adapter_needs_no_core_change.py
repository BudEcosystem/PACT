"""AC-2.5 — an adapter the core has never heard of.

> Adding a *new* adapter (an 8th framework) requires no modification to any core
> package. Proven in CI by building an adapter that lives in a separate
> repository.

`adapters/out-of-tree/echo_adapter/` is that adapter. It is in no package the
core installs, imported by nothing under `adapters/python/src`, and named in no
registry — a test puts its directory on `sys.path` the way a separate checkout
would, and the agent runs.

**The property is structural, not documented.** `Transport` in `harness.py` is a
`Protocol`, so an object with `model_call` IS a transport: nothing is inherited,
nothing is declared, and there is nowhere to register. That is what makes "no
core modification" true rather than merely intended — a registry would be the one
thing that could quietly make it false, and the second test below is the one that
would notice.

**The shortfall, stated:** the criterion asks for a separate *repository*, and
this is a separate *directory*. What a directory proves is that no core change is
needed; what a repository would additionally prove is that no core *release* is
needed. The second needs publishing, which is register row C6.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "adapters" / "python" / "src" / "pact_adapters"
OUT_OF_TREE = REPO / "adapters" / "out-of-tree"

sys.path.insert(0, str(SRC.parent))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402


@pytest.fixture
def eighth():
    """The adapter, imported the way a separate checkout would be."""
    sys.path.insert(0, str(OUT_OF_TREE))
    try:
        from echo_adapter import EchoTransport
        yield EchoTransport
    finally:
        sys.path.remove(str(OUT_OF_TREE))
        sys.modules.pop("echo_adapter", None)
        sys.modules.pop("echo_adapter.transport", None)


def test_it_exists_outside_the_core() -> None:
    assert (OUT_OF_TREE / "echo_adapter" / "transport.py").exists()
    assert not (SRC / "transports" / "echo_adapter.py").exists()


def test_the_core_has_never_heard_of_it() -> None:
    """The check that makes "no core modification" a fact rather than an
    intention. One `import echo_adapter` anywhere in `src/` and the claim is
    false — and it would still pass every behavioural test below."""
    named = [
        str(p.relative_to(REPO))
        for p in SRC.rglob("*.py")
        if "echo_adapter" in p.read_text(errors="ignore")
        or "EchoTransport" in p.read_text(errors="ignore")
    ]
    assert not named, (
        f"the core mentions the out-of-tree adapter in {named} — then it is not "
        f"out of tree, and AC-2.5 is being tested against something the core "
        f"already knows about"
    )
    # And it is not installed, either.
    manifest = (REPO / "adapters" / "python" / "pyproject.toml").read_text()
    assert "echo_adapter" not in manifest and "out-of-tree" not in manifest


def test_there_is_nowhere_a_transport_has_to_register() -> None:
    """A registry would be the one thing that could quietly make this false.

    `Transport` is a `Protocol` — conformance is structural, so an object with
    `model_call` IS one. If the core ever grew a table a transport had to join,
    an eighth adapter would need a core change and nobody would notice until they
    tried to write one.
    """
    protocol = (SRC / "harness.py").read_text()
    assert "class Transport(Protocol):" in protocol, (
        "`Transport` is no longer a Protocol — conformance may have become "
        "nominal, which would mean an adapter has to inherit from the core"
    )
    # `run` takes the transport as an argument and never looks one up.
    assert "transport: Transport," in protocol


def test_the_eighth_adapter_runs_an_agent(eighth) -> None:
    """The behavioural half, with the core untouched."""
    spec = AgentSpec(
        name="Desk", description="Answers questions.",
        instructions="Answer the question.",
    )
    transport = eighth()
    out = asyncio.run(run(spec, transport, "is this ok?"))

    assert out.halted == "final", out.halted
    assert out.output == "you said: is this ok?"
    assert transport.calls == 1


def test_its_optional_methods_are_honoured_like_any_other(eighth) -> None:
    """The six optional methods are optional in the strict sense: an out-of-tree
    transport that offers `usage()` is metered exactly as a core one is, with no
    special casing anywhere."""
    spec = AgentSpec(
        name="Desk", description="d", instructions="Answer.",
    )
    out = asyncio.run(run(spec, eighth(), "hello"))
    assert out.used is not None
    assert out.used.tokens > 0, "the transport reported tokens and nothing counted them"
    # And its lattice is the same four-word vocabulary every other one uses.
    assert set(eighth().lattice().values()) <= {
        "native", "emulated", "degraded", "unsupported"
    }


def test_it_can_be_added_to_a_conformance_report_without_touching_the_core(
    eighth,
) -> None:
    """AC-2.2's `or` clause read from the other side: an eighth adapter joins a
    report by being passed in, not by being known about."""
    from pact_adapters import conformance

    kept = dict(conformance.TARGETS)
    try:
        conformance.TARGETS["echo"] = lambda _script: eighth()
        declared = {
            name: cls(None).lattice() for name, cls in conformance.TARGETS.items()
        }
        assert "echo" in declared
        assert declared["echo"]["model_call"] == "native"
    finally:
        conformance.TARGETS.clear()
        conformance.TARGETS.update(kept)
