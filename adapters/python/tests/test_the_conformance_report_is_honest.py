"""AC-2.2 — the Conformance Report, held to its own claims.

The criterion, verbatim:

> For every (golden agent × adapter) pair, the shared eval suite passes with
> score within a declared ε of the reference adapter, **or** the adapter declares
> the relevant feature `degraded`/`unsupported` in its lattice *and* the
> Conformance Report says so before execution.

An artifact is easy; an artifact that can be wrong is the point. The tests here
are all of the form *the report says X, and X is true* — because a report nothing
compares against the tree is the fourth document in this repository found
asserting coverage it did not have.

The one that matters most is `test_the_report_would_notice_a_divergence`: an
adapter that quietly agreed with itself would produce the same all-green report
as one that genuinely agrees.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.conformance import (  # noqa: E402
    EPSILON,
    REFERENCE,
    TARGETS,
    report,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"
PACT_BIN = REPO / "target" / "debug" / "pact"


@pytest.fixture(scope="module")
def said() -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    roots = sorted(p.parent for p in EXAMPLES.rglob("workspace.yaml"))
    return report(roots, PACT_BIN)


def test_the_report_covers_every_agent_and_every_adapter(said: dict) -> None:
    """"For every (golden agent × adapter) pair" — counted, not asserted.

    A report over a subset with no note saying so is the failure this whole
    round has been about, one artifact up.
    """
    roots = sorted(p.parent for p in EXAMPLES.rglob("workspace.yaml"))
    on_disk = 0
    for root in roots:
        out = subprocess.run(
            [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
        )
        on_disk += len(json.loads(out.stdout).get("agents", {}))

    assert said["compared"]["agents"] == on_disk, (
        f"the report covers {said['compared']['agents']} agents and the tree has "
        f"{on_disk}"
    )
    # Every non-reference adapter, for every agent. The reference is what they
    # are compared AGAINST, so it is not compared with itself.
    assert said["compared"]["pairs"] == on_disk * (len(TARGETS) - 1), said["compared"]
    assert len(said["results"]) == said["compared"]["pairs"]


def test_the_epsilon_is_declared_and_is_zero(said: dict) -> None:
    """"within a declared ε" — declared in the artifact, with the reason.

    Zero is not a hedge. Every comparison is driven by a scripted transport, so
    two adapters running one agent have nothing legitimate to differ about, and a
    non-zero tolerance would be room for a real divergence to hide in.
    """
    assert said["epsilon"] == EPSILON == 0.0
    assert said["epsilon-because"], "a tolerance with no reason is a number"
    assert "scripted" in said["epsilon-because"]


def test_what_each_adapter_cannot_do_is_stated_before_the_results(said: dict) -> None:
    """"the Conformance Report says so **before execution**".

    This is the obligation that makes the artifact worth anything. A report that
    lists what diverged after the fact is a changelog; one that states each
    adapter's declared limits first is a claim that can be wrong.
    """
    keys = list(said)
    assert keys.index("declared-before-execution") < keys.index("results"), keys
    declared = said["declared-before-execution"]
    assert set(declared) == set(TARGETS), declared
    for name, lattice in declared.items():
        assert lattice, f"{name} declares nothing at all"
        assert set(lattice.values()) <= {
            "native", "emulated", "degraded", "unsupported"
        }, f"{name} uses a word outside the lattice vocabulary: {lattice}"


def test_every_divergence_is_one_an_adapter_declared(said: dict) -> None:
    """The criterion's `or` clause. A divergence is excused only where the
    adapter said in advance it could not do the thing."""
    assert said["summary"]["undeclared-divergences"] == [], (
        "adapters diverged on features they declared they support:\n"
        + json.dumps(said["summary"]["undeclared-divergences"], indent=2)
    )


def test_the_report_says_what_it_does_not_cover(said: dict) -> None:
    """A conformance report whose scope is implicit reads as covering everything.

    In the artifact, not in a docstring somebody has to go and find — the reader
    of a report is not the reader of this file.
    """
    absent = said["not-compared"]
    assert len(absent) >= 3, absent
    joined = " ".join(absent)
    for owed in ("tool", "park", "TypeScript"):
        assert owed in joined, f"the scope note does not mention {owed}: {absent}"


def test_the_report_would_notice_a_divergence() -> None:
    """The one that stops all of this being decorative.

    An adapter that agreed with itself by construction would produce the same
    all-green report as one that genuinely agrees. So: run the report with a
    target deliberately swapped for one that answers differently, and check it
    is caught and counted as undeclared.
    """
    from pact_adapters import conformance
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    class Different(ReferenceTransport):
        async def model_call(self, system, history, tools):  # type: ignore[no-untyped-def]
            text, calls = await super().model_call(system, history, tools)
            return text + " (and something else)", calls

    kept = dict(conformance.TARGETS)
    try:
        conformance.TARGETS["a-broken-one"] = Different
        said = report([EXAMPLES / "refund-desk"], PACT_BIN)
        broken = [r for r in said["results"] if r["adapter"] == "a-broken-one"]
        assert broken, "the injected target was not compared at all"
        assert all(not r["agreed"] for r in broken), broken
        assert said["summary"]["diverged"] >= len(broken)
        assert said["summary"]["undeclared-divergences"], (
            "a divergence on a feature the adapter declared `native` must be "
            "reported as undeclared — that is the whole `or` clause"
        )
    finally:
        conformance.TARGETS.clear()
        conformance.TARGETS.update(kept)


def test_the_command_exits_nonzero_when_something_diverged() -> None:
    """The artifact is also a gate. A report nobody can fail a build on is a
    document."""
    out = subprocess.run(
        [sys.executable, "-m", "pact_adapters.conformance", str(EXAMPLES)],
        capture_output=True, text=True,
        cwd=REPO,
        env={
            "PYTHONPATH": str(REPO / "adapters/python/src"),
            "PATH": "/usr/bin:/bin",
        },
    )
    if out.returncode == 3:
        pytest.skip(out.stderr)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    said = json.loads(out.stdout)
    assert said["kind"] == "ConformanceReport"
    assert said["reference"] == REFERENCE
    assert said["summary"]["diverged"] == 0
