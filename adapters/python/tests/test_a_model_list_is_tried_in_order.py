"""02P §3.2 A2 — `model:` may be an ordered list, tried in order when a call fails.

The loader holds every entry to `allow-egress:` and the catalogue
(`crates/pact-cli/tests/a_model_list_is_a_fallback_chain.rs`). This side holds:

* `ir.AgentSpec.models` is the chain in the author's order, and `model` stays
  the one a run starts on, so every reader of a single pin is unchanged;
* every fallback is held to `needs:` exactly as the first model is;
* the two Pydantic AI doors: a spec file holds one model and says so, and a live
  `FallbackModel` imports as the list.
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
    from_pydantic_ai_agent,
    to_pydantic_ai_spec,
)
from pact_adapters.scoring import _bind  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PACT_BIN = REPO / "target" / "debug" / "pact"

NEEDS = """\
images: yes
because: customers attach photos of what arrived
"""


def _tree(root: Path, model: str, needs: str = "") -> Path:
    (root / "agents" / "desk").mkdir(parents=True)
    (root / "workspace.yaml").write_text("name: chain\nallow-egress: []\n")
    (root / "agents" / "desk" / "agent.yaml").write_text(
        f"description: answers\ninstructions: Answer.\nmodel: {model}\n"
    )
    if needs:
        (root / "agents" / "desk" / "needs.yaml").write_text(needs)
    return root


def _document(root: Path) -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    checked = subprocess.run([str(PACT_BIN), "check", str(root)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    shown = subprocess.run([str(PACT_BIN), "show", str(root)], capture_output=True, text=True)
    return json.loads(shown.stdout)


def test_the_chain_reaches_the_spec_in_the_authors_order(tmp_path: Path) -> None:
    doc = _document(_tree(tmp_path / "w", "[qwen2.5-14b-instruct, qwen2.5-7b-instruct]"))
    spec = AgentSpec.from_document(doc, "desk")
    assert spec.models == ("qwen2.5-14b-instruct", "qwen2.5-7b-instruct")
    assert spec.model == "qwen2.5-14b-instruct"


def test_one_model_is_a_chain_of_one(tmp_path: Path) -> None:
    spec = AgentSpec.from_document(_document(_tree(tmp_path / "w", "qwen2.5-7b-instruct")), "desk")
    assert spec.models == ("qwen2.5-7b-instruct",)
    assert spec.model == "qwen2.5-7b-instruct"
    assert AgentSpec.from_document({"agents": {"a": {}}}, "a").models == ()


def test_a_fallback_that_cannot_meet_needs_is_refused(tmp_path: Path) -> None:
    root = _tree(tmp_path / "w", "[qwen2.5-vl-7b-instruct, qwen2.5-7b-instruct]", NEEDS)
    doc = _document(root)
    spec = AgentSpec.from_document(doc, "desk", source=root)
    entry, said, problem = _bind(doc, spec, "desk", "", "", root)
    assert entry is None and problem is None
    assert "`qwen2.5-7b-instruct`, a fallback in `model:`" in said, said
    assert "fix:" in said


def test_a_chain_that_meets_needs_scores_on_its_first_model(tmp_path: Path) -> None:
    root = _tree(tmp_path / "w", "[qwen2.5-vl-7b-instruct]", NEEDS)
    doc = _document(root)
    spec = AgentSpec.from_document(doc, "desk", source=root)
    entry, _, problem = _bind(doc, spec, "desk", "", "", root)
    assert problem is None and entry is not None and entry.name == "qwen2.5-vl-7b-instruct"


def test_a_spec_file_carries_the_first_model_and_names_the_fallbacks(tmp_path: Path) -> None:
    doc = _document(_tree(tmp_path / "w", "[qwen2.5-14b-instruct, qwen2.5-7b-instruct]"))
    spec, report = to_pydantic_ai_spec(doc, "desk")
    assert spec["model"].endswith("qwen2.5:14b-instruct"), spec["model"]
    lost = report.not_carried["model.fallbacks"]
    assert "`qwen2.5-7b-instruct`" in lost and "FallbackModel" in lost


def test_a_live_fallback_model_imports_as_the_list() -> None:
    from pydantic_ai import Agent
    from pydantic_ai.models.fallback import FallbackModel
    from pydantic_ai.models.test import TestModel

    agent = Agent(FallbackModel(TestModel(model_name="first"), TestModel(model_name="second")))
    written, report = from_pydantic_ai_agent(agent)
    assert written["model"] == ["test:first", "test:second"]
    assert "model" in report.mapped
