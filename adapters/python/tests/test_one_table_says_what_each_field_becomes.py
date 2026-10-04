"""02P §4: one registry from PACT field to Pydantic AI construct.

`pydantic_ai_registry.yaml` replaced three tables `pydantic_ai_interop.py` kept
by hand. These hold it whole in both directions: every agent, tool and action
field the schema declares has a row, and every capability class the installed
Pydantic AI exports has an entry, so moving the pin is a test run.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import pydantic_ai_interop  # noqa: E402
from pact_adapters.pydantic_ai_registry import (  # noqa: E402
    KINDS,
    PATH,
    RegistryError,
    main,
    markdown,
    parse,
    registry,
)

REPO = Path(__file__).resolve().parents[3]
SCHEMA = REPO / "spec" / "schema.yaml"


def _schema_fields() -> set[str]:
    groups = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))["groups"]
    return {f"{kind}.{name}" for kind in KINDS for name in groups[kind]["fields"]}


def test_every_field_the_schema_declares_has_a_row() -> None:
    declared, rows = _schema_fields(), set(registry().fields)
    assert not declared - rows, (
        f"{sorted(declared - rows)} are in spec/schema.yaml and not in {PATH.name}.\n"
        "  fix: add a row naming the Pydantic AI construct each becomes."
    )
    assert not rows - declared, f"{sorted(rows - declared)} name fields the schema does not have"


def test_every_capability_pydantic_ai_ships_has_an_entry() -> None:
    capabilities = pytest.importorskip("pydantic_ai.capabilities")
    shipped = {
        name
        for name, value in vars(capabilities).items()
        if inspect.isclass(value) and issubclass(value, capabilities.AbstractCapability)
    }
    shipped |= set(getattr(capabilities, "CAPABILITY_TYPES", {}))
    missing = sorted(shipped - set(registry().capabilities))
    assert not missing, (
        f"Pydantic AI exports {missing} and {PATH.name} has never heard of them.\n"
        "  fix: add each under `capabilities:` with its 02P row and outcome."
    )


def test_the_hand_kept_tables_are_gone() -> None:
    for name in ("_CAPABILITY_MAPS", "_TOOL_NAMES", "_middleware_reason"):
        assert not hasattr(pydantic_ai_interop, name), f"{name} is a second copy of the registry"


@pytest.mark.parametrize("name", ["WebSearch", "WebFetch", "ImageGeneration", "XSearch", "MCP"])
def test_a_tool_capability_imports_as_the_registry_says(name: str) -> None:
    row = registry().capability(name)
    assert row is not None and row.tool
    _, report = pydantic_ai_interop.from_pydantic_ai_spec(
        {"model": "test", "instructions": "x", "capabilities": [name]}
    )
    assert report.mapped[f"capabilities.{name}"] == row.pact


def test_a_capability_with_no_pact_spelling_is_a_named_loss_through_both_doors() -> None:
    reg = registry()
    _, by_spec = pydantic_ai_interop.from_pydantic_ai_spec(
        {"model": "test", "instructions": "x", "capabilities": ["ReinjectSystemPrompt"]}
    )
    said = by_spec.not_portable["capabilities.ReinjectSystemPrompt"]
    assert said == reg.why_not_portable("ReinjectSystemPrompt")
    assert "middleware" in said
    agent_mod = pytest.importorskip("pydantic_ai")
    from pydantic_ai.capabilities import ReinjectSystemPrompt

    live = agent_mod.Agent("test", capabilities=[ReinjectSystemPrompt()])
    _, by_object = pydantic_ai_interop.from_pydantic_ai_agent(live)
    assert by_object.not_portable["capabilities.ReinjectSystemPrompt"] == said


def test_a_loss_with_its_own_reason_says_it() -> None:
    reg = registry()
    assert "host" in reg.why_not_portable("TemporalDurability")
    assert reg.why_not_portable("SomebodysOwnCapability").startswith("`SomebodysOwnCapability`")


@pytest.mark.parametrize(
    ("document", "complaint"),
    [
        ({"fields": {"agent.x": {"construct": "c", "outcome": "kept", "rows": ["A1"]}}}, "not one of"),
        ({"fields": {"agent.x": {"outcome": "carried", "rows": ["A1"]}}}, "construct"),
        ({"fields": {"agent.x": {"construct": "c", "outcome": "carried"}}}, "02P rows"),
        ({"capabilities": {"X": {"outcome": "mapped", "rows": ["X1"]}}}, "PACT spelling"),
        ({"capabilities": {"X": {"outcome": "loss", "rows": ["X1"], "pact": "`uses:`"}}}, "no PACT"),
    ],
)
def test_a_malformed_registry_is_refused(document: dict, complaint: str) -> None:
    with pytest.raises(RegistryError, match=complaint):
        parse({"middleware": "`{name}` is middleware", **document})


def test_the_page_names_every_row(tmp_path: Path) -> None:
    page = markdown()
    reg = registry()
    for key in reg.fields:
        assert f"`{key.split('.', 1)[1]}:`" in page, key
    for name in reg.capabilities:
        assert f"`{name}`" in page, name
    assert "`max-tokens` | `max_tokens`" in page
    target = tmp_path / "MAPPING.md"
    assert main([str(target)]) == 0
    assert target.read_text(encoding="utf-8") == page
    assert main([str(target), "--check"]) == 0
    target.write_text("stale\n", encoding="utf-8")
    with pytest.raises(SystemExit) as stale:
        main([str(target), "--check"])
    assert stale.value.code == 1


def test_the_reader_imports_no_agent_framework() -> None:
    import subprocess

    src = str(Path(__file__).resolve().parents[1] / "src")
    probe = (
        f"import sys; sys.path.insert(0, {src!r})\n"
        "import pact_adapters.pydantic_ai_registry as r; r.registry()\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('pydantic_ai', 'pydantic_graph')]\n"
        "assert not bad, bad\n"
    )
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr

