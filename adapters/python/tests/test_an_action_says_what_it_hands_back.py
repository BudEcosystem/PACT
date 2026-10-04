"""02P §3.2 A4 — `answers-with:` on a tool's action.

The other half of `takes:`, in the vocabulary an agent's `answers-with:` uses.
Held here end to end through the real loader:

* a shape outside the vocabulary is refused at check time, at its line;
* `ir.ToolSpec.answers_with` carries each action's lines, keyed by action;
* every value is one `questions.Shape.parse` reads and
  `pydantic_ai_interop.shape_as_json_schema` turns into a schema fragment —
  which is what a `ToolDefinition.return_schema` is built from.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.pydantic_ai_interop import (  # noqa: E402
    return_schema_for,
    shape_as_json_schema,
)
from pact_adapters.questions import Shape  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PACT_BIN = REPO / "target" / "debug" / "pact"

TOOL = """\
description: Reads the service's metrics.
connect: datadog
actions:
  query-metrics:
    reads-only: yes
    takes:
      query: text
    answers-with:
      latest: number
      unit: one of ms, s
  mute:
    takes:
      monitor: text
"""


def _tree(root: Path, tool: str) -> Path:
    for folder in ("agents", "tools", "resources"):
        (root / folder).mkdir(parents=True)
    (root / "workspace.yaml").write_text("name: typed\nallow-egress: []\n")
    (root / "agents" / "ops.yaml").write_text(
        "description: watches the service\ninstructions: Watch it.\nuses: [datadog]\n"
    )
    (root / "tools" / "datadog.yaml").write_text(tool)
    (root / "resources" / "datadog.yaml").write_text(
        "resource-kind: mcp-server\nendpoint: host/datadog\n"
    )
    return root


def _pact(*args: str) -> subprocess.CompletedProcess[str]:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    return subprocess.run([str(PACT_BIN), *args], capture_output=True, text=True)


def test_each_action_carries_what_it_hands_back(tmp_path: Path) -> None:
    root = _tree(tmp_path / "w", TOOL)
    checked = _pact("check", str(root))
    assert checked.returncode == 0, checked.stdout + checked.stderr
    spec = AgentSpec.from_document(json.loads(_pact("show", str(root)).stdout), "ops")
    (tool,) = spec.tools
    assert tool.answers_with == {"query-metrics": {"latest": "number", "unit": "one of ms, s"}}
    # `answers-with:` is the result, never an argument the model fills.
    assert "latest" not in tool.parameters and "unit" not in tool.parameters


def test_every_declared_shape_becomes_a_schema_fragment(tmp_path: Path) -> None:
    root = _tree(tmp_path / "w", TOOL)
    spec = AgentSpec.from_document(json.loads(_pact("show", str(root)).stdout), "ops")
    fields = spec.tools[0].answers_with["query-metrics"]
    schemas = {k: shape_as_json_schema(Shape.parse(v)) for k, v in fields.items()}
    assert schemas["latest"]["type"] == "number"
    assert schemas["unit"] == {"type": "string", "enum": ["ms", "s"]}


def test_a_shape_outside_the_vocabulary_is_refused_at_its_line(tmp_path: Path) -> None:
    root = _tree(tmp_path / "w", TOOL.replace("unit: one of ms, s", "unit: a bananna"))
    checked = _pact("check", str(root))
    said = checked.stdout + checked.stderr
    assert checked.returncode != 0, said
    assert "rule: schema/not-an-answer-shape" in said, said
    assert "datadog.yaml:10" in said, said


def test_a_tool_that_declares_no_answer_carries_none() -> None:
    doc = {
        "agents": {"ops": {"uses": ["t"]}},
        "tools": {"t": {"actions": {"a": {"takes": {"x": "text"}}}}},
    }
    assert AgentSpec.from_document(doc, "ops").tools[0].answers_with == {}


def test_an_action_answer_is_one_return_schema(tmp_path: Path) -> None:
    root = _tree(tmp_path / "w", TOOL)
    spec = AgentSpec.from_document(json.loads(_pact("show", str(root)).stdout), "ops")
    (tool,) = spec.tools
    assert return_schema_for(tool, "query-metrics") == {
        "type": "object",
        "properties": {
            "latest": {"type": "number"},
            "unit": {"type": "string", "enum": ["ms", "s"]},
        },
        "required": ["latest", "unit"],
        "additionalProperties": False,
    }
    # An action that declares nothing has no return type, not an empty one.
    assert return_schema_for(tool, "mute") is None
    assert return_schema_for(tool, "no-such-action") is None


def test_a_runtime_that_answers_in_text_says_it_checked_nothing() -> None:
    """PACT's own tools answer in text, so the declared return type is named.

    `harness.run` hands a tool's result to the model as a string; a promise it
    cannot keep goes on `RunResult.unenforced`, as an unfilled `bind:` does.
    """
    import asyncio

    import yaml
    from pact_adapters.harness import run
    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.mock import ReferenceTransport

    doc = {
        "agents": {"ops": {"description": "d", "instructions": "i", "uses": ["datadog"]}},
        "tools": {"datadog": yaml.safe_load(TOOL)},
    }
    spec = AgentSpec.from_document(doc, "ops")
    result = asyncio.run(run(spec, ReferenceTransport(Script([Turn("done")])), "go", {}))
    said = [line for line in result.unenforced if line.startswith("answers-with:")]
    assert said == [
        "answers-with: datadog/query-metrics says what it hands back (latest, unit), and "
        "this runtime hands a tool's result to the model as text, unchecked — run it on "
        "a host whose tools return typed results to hold it."
    ], result.unenforced
