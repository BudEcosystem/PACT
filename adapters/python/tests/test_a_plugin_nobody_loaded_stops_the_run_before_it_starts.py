"""D29: a plugin an agent may not start without, on a runtime that did not load it.

`plugins/<name>.yaml` asks whatever runs the agent to load a package for it. The
harness loads nothing, so on every transport this repository ships the plugin is
missing; the host that does load one says so through `run(loaded_plugins=)`.
What a missing `refuse-to-start` plugin must NOT do is let the run go ahead: an
agent written to rely on code it did not get is not the agent somebody reviewed,
and the first answer it gives is paid for and wrong.

So the turn ends before a single model call, `halted` says
`plugins-not-loaded`, the sentence names the plugin, its package and its range
and the two ways out, and `turn.run.failed` carries the reason — on every Python
target, and on the second port in the same words. The tree is
`tests/trees/a-desk-that-needs-a-plugin/`, read through the real loader.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.conformance import TARGETS, report  # noqa: E402
from pact_adapters.events import Bus  # noqa: E402
from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from test_the_golden_set_runs_everywhere import TRANSPORTS, _there  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TREE = REPO / "tests" / "trees" / "a-desk-that-needs-a-plugin"
EXAMPLE = REPO / "examples" / "plugin-desk"
PACT = REPO / "target" / "debug" / "pact"

REFUSED = (
    "This agent cannot start: it needs 'crm-tools' (`pypi:acme-crm-tools`, versions "
    "`>=1.4,<2`), and nothing running it loaded it. fix: run it where a runtime loads "
    "`pypi:` packages, or write `if-it-cannot-be-loaded: run-without-it` in the "
    "plugin's file under `plugins/` if the agent can do its job without it."
)

pytestmark = pytest.mark.skipif(not PACT.exists(), reason="build the CLI first: cargo build -p pact-cli")


def spec() -> AgentSpec:
    out = subprocess.run([str(PACT), "show", str(TREE)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return AgentSpec.from_document(json.loads(out.stdout), "desk", source=TREE)


def running(transport_cls=ReferenceTransport, **kw):
    script = Script([Turn("Your account is in good standing.")])
    bus = Bus()
    result = asyncio.run(
        run(spec(), transport_cls(script), "Is my account in good standing?", {}, bus=bus, **kw)
    )
    return result, script, bus


def test_the_plugin_reaches_the_spec_with_its_default_written_out() -> None:
    (plugin,) = spec().plugins
    assert (plugin.name, plugin.package, plugin.version, plugin.if_cannot_load) == (
        "crm-tools", "pypi:acme-crm-tools", ">=1.4,<2", "refuse-to-start"
    )
    assert plugin.registry == "pypi"


def test_a_plugin_nobody_loaded_ends_the_turn_before_a_model_is_called() -> None:
    result, script, bus = running()
    assert result.halted == "plugins-not-loaded", result.halted
    assert result.output == REFUSED
    assert script.calls == 0, "nothing may be paid for before the plugin is known to be missing"
    assert result.trace() == []
    (failed,) = list(bus.seen("turn.run.failed"))
    assert failed.payload == {"reason": "plugins-not-loaded"}


def test_every_python_target_refuses_the_same_way() -> None:
    """The refusal is the harness's, before any transport is asked anything, so a
    target that went ahead would be a target that owns part of the loop."""
    for name, cls in TRANSPORTS.items():
        result, script, _ = running(cls)
        assert (result.halted, result.output, script.calls) == (
            "plugins-not-loaded", REFUSED, 0
        ), name


def test_a_host_that_loaded_it_runs_the_agent_and_says_nothing_about_it() -> None:
    result, script, _ = running(loaded_plugins={"crm-tools": "1.4.2"})
    assert result.halted == "final", result.halted
    assert script.calls == 1
    assert not [u for u in result.unenforced if "crm-tools" in u], result.unenforced


def test_loading_some_other_plugin_is_not_loading_this_one() -> None:
    result, _, _ = running(loaded_plugins={"web-search": "0.2.1"})
    assert result.halted == "plugins-not-loaded"


def test_the_second_port_refuses_in_the_same_words() -> None:
    there = _there(spec())
    if there is None:
        pytest.skip("node or the AI SDK is unavailable")
    assert (there["halted"], there["output"]) == ("plugins-not-loaded", REFUSED)
    assert there["told"] == [], "the second port called a model it had no business calling"
    assert there["trace"] == []


def test_every_target_says_before_execution_that_it_loads_no_plugin() -> None:
    """The lattice column a reader checks before choosing where to run a tree with
    plugins in it. Every transport here publishes `unsupported`, because the
    harness loads nothing — and the conformance report states it ahead of the
    results, which is the AC-2.2 obligation."""
    said = report([EXAMPLE], PACT)
    declared = said["declared-before-execution"]
    assert set(declared) == set(TARGETS)
    assert {name: lattice["plugins"] for name, lattice in declared.items()} == {
        name: "unsupported" for name in TARGETS
    }
    there = _there(spec())
    if there is not None:
        assert there["lattice"]["plugins"] == "unsupported"
