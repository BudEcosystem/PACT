"""D29: a plugin an agent may start without, on a runtime that did not load it.

`if-it-cannot-be-loaded: run-without-it` says the agent can still do its job
without the package — and the cost of that line is that every run has to SAY the
plugin was not there. A run that started without it in silence would answer from
whatever the model already knew while the author, reading their own file,
believed a search had been made. That is the T7 breach, and `unenforced` is the
door every other line this runtime did not carry out leaves by.

The tree is `examples/plugin-desk/`, read through the real loader, so this also
holds the shipped example to doing what its own comments say.
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

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402
from test_the_golden_set_runs_everywhere import _there  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "plugin-desk"
PACT = REPO / "target" / "debug" / "pact"

WITHOUT = (
    "plugin 'web-search' (`npm:@budmh/tool-web`, versions `^0.2.1-rc.3`) was not loaded "
    "by whatever runs this agent, so nothing it adds is here and the agent ran without "
    "it. fix: run it where a runtime loads `npm:` packages."
)

pytestmark = pytest.mark.skipif(not PACT.exists(), reason="build the CLI first: cargo build -p pact-cli")


def document() -> dict:
    out = subprocess.run([str(PACT), "show", str(EXAMPLE)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def spec(doc: dict | None = None) -> AgentSpec:
    return AgentSpec.from_document(doc or document(), "research-desk", source=EXAMPLE)


def answering(s: AgentSpec, **kw):
    script = Script([Turn("Nothing on that has been published.")])
    result = asyncio.run(run(s, ReferenceTransport(script), "What changed this week?", {}, **kw))
    return result, script


def test_the_agent_starts_without_it_and_every_run_says_so() -> None:
    result, script = answering(spec())
    assert result.halted == "final", result.halted
    assert script.calls == 1
    assert result.unenforced.count(WITHOUT) == 1, result.unenforced


def test_a_host_that_loaded_it_has_nothing_to_report() -> None:
    result, _ = answering(spec(), loaded_plugins={"web-search": "0.2.1-rc.3"})
    assert result.halted == "final"
    assert WITHOUT not in result.unenforced
    assert not [u for u in result.unenforced if "web-search" in u], result.unenforced


def test_the_second_port_names_it_in_the_same_words() -> None:
    there = _there(spec())
    if there is None:
        pytest.skip("node or the AI SDK is unavailable")
    here, _ = answering(spec())
    assert there["halted"] == here.halted == "final"
    assert there["unenforced"].count(WITHOUT) == 1, there["unenforced"]


def test_a_plugin_for_every_agent_reaches_an_agent_that_does_not_name_it() -> None:
    """`applies-to: every-agent` is written on the plugin so that an agent cannot
    opt out by leaving it off its own line — the polarity `interceptor.applies-to`
    and `policy.applies-to` already record. The spec, and so the run, has to see
    it on an agent that names nothing."""
    doc = document()
    del doc["agents"]["research-desk"]["plugins"]
    assert spec(doc).plugins == ()
    doc["plugins"]["web-search"]["applies-to"] = "every-agent"
    (plugin,) = spec(doc).plugins
    assert plugin.name == "web-search"
    result, _ = answering(spec(doc))
    assert WITHOUT in result.unenforced
