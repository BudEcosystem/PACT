"""02P §4: one registry from PACT field to Pydantic AI construct.

`pydantic_ai_registry.yaml` replaced the tables `pydantic_ai_interop.py` kept
by hand. These hold the PACT half whole: every agent, tool and action field the
schema declares has a row. The Pydantic AI half (every capability, `AgentSpec`
field, `ModelSettings` key, message part, stream event, `ToolDefinition` field
and `GraphBuilder` member the installed packages have) is the parity suite's
one completeness check, `test_parity.py::test_s4_*`.
"""

from __future__ import annotations

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


def test_a_field_pydantic_ai_cannot_hold_says_so_and_says_who_holds_it() -> None:
    """A `loss` row is read as "Pydantic AI has nothing that means this", so its construct
    opens with that word and goes on to name who holds the line instead (PACT at check time,
    or the host at run time). A loss row that named a construct would be a mapped row
    mislabelled; one that stopped at "nothing" would leave the reader asking who does it."""
    for name, row in registry().fields.items():
        if row.outcome != "loss":
            continue
        opening, colon, holder = row.construct.partition(":")
        assert opening.split()[0] == "nothing" and colon and holder.strip(), (
            f"{name} is a loss and its construct reads {row.construct!r}.\n"
            "  fix: write it as `nothing: <who holds it, and when>`."
        )


def test_no_row_shares_one_usage_object_across_a_delegation() -> None:
    """AD-R7: the usage object does not cross a delegation boundary. A member checked against
    `usage=ctx.usage` has its own `steps-at-most:` held to its caller's total, so the table
    never offers that as what `team:` becomes."""
    said = {name: row.construct for name, row in registry().fields.items() if "ctx.usage" in row.construct}
    assert not said, f"{sorted(said)} hand a member its caller's usage; a member runs on its own (AD-R7)"


def test_the_hand_kept_tables_are_gone() -> None:
    for name in ("_CAPABILITY_MAPS", "_TOOL_NAMES", "_middleware_reason"):
        assert not hasattr(pydantic_ai_interop, name), f"{name} is a second copy of the registry"


def test_the_importers_and_the_exporter_read_their_words_from_the_registry() -> None:
    reg, m = registry(), pydantic_ai_interop
    spec, agent = reg.through("spec"), reg.through("agent")
    assert {k: r.pact for k, r in spec.items() if r.pact} == m._SPEC_MAPS
    assert {k: r.why for k, r in spec.items() if r.why} == m._SPEC_NOT_PORTABLE
    assert {k: r.left for k, r in spec.items() if r.left} == m._SPEC_SUPPLIES
    assert {k: r.pact for k, r in agent.items() if r.pact} == m._AGENT_MAPS
    assert {k: r.why for k, r in agent.items() if r.why} == m._AGENT_NOT_PORTABLE
    assert {k: r.why for k, r in reg.through("settings").items()} == m._SETTINGS_NOT_PORTABLE
    assert {
        k.split(".", 1)[1]: r.spec_file for k, r in reg.fields.items() if r.spec_file
    } == m._SPEC_CANNOT_TAKE
    # The live importer's losses are the spec file's, word for word (one anchor
    # each in the YAML), plus what only an object has.
    for key in ("end_strategy", "retries", "tool_timeout", "metadata", "instrument"):
        assert agent[key].why == spec[key].why


def test_spec_file_reasons_are_on_agent_fields_only() -> None:
    for key, row in registry().fields.items():
        assert not row.spec_file or key.startswith("agent."), key


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
        ({"names": {"model.x": {"outcome": "loss", "rows": ["A1"]}}}, "starts with one of"),
        ({"names": {"spec.x": {"outcome": "carried", "rows": ["A1"]}}}, "PACT spelling"),
        ({"names": {"spec.x": {"outcome": "loss", "rows": ["A1"], "pact": "`x:`"}}}, "no PACT"),
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
    for name in reg.names:
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

