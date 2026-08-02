"""AC-6.3 — exporting with a loss report.

> Export to Bud `AgentRecord`, A2A Agent Card, and OSSA each produce a loss
> report consistent with the in-repo `ExportReport` shape.

Every target format is **smaller than a PACT agent** — that is what makes them
facades and registry records rather than specifications. So an export that emits
the target and says nothing hands somebody a file that looks like their agent and
is not, and the loss report is the entire value.

`silent_losses` is **computed from the source**, exactly as
`ImportReport.silent_drops` is. A maintained list of known losses is a list
somebody has to remember to extend, and the loss that matters is the one nobody
remembered.

**OSSA is absent and that is a refusal.** No schema for it exists in this
repository or in `gaia-ai-runtime` — the only matches are Italian translation
strings, where `ossa` means "bones". An exporter written against an invented
format is a file that loads nowhere, dressed as an integration.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.exporting import (  # noqa: E402
    _RUNTIME_SUPPLIES,
    ExportReport,
    to_bud_agent_record,
)

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"
#: The real interface, in the runtime that consumes these records.
BUD_TS = Path("/home/bud/ditto/gaia-ai-runtime/goose/ui/desktop/src/acp/bud.ts")


@pytest.fixture(scope="module")
def document() -> dict:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def test_exporting_the_worked_example_loses_nothing_silently(document: dict) -> None:
    """Every field of the agent is carried or named as lost. A field in neither
    is a silent loss, found whether or not anybody expected it."""
    _record, report = to_bud_agent_record(document, "refund-desk")
    assert report.silent_losses == (), (
        f"the agent carries {report.silent_losses} and the report accounts for "
        f"none of it:\n{report.in_words()}"
    )
    assert len(report.not_carried) >= 10, (
        "a registry record is much smaller than a PACT agent; a report claiming "
        f"otherwise is not reading the agent: {report.not_carried}"
    )


def test_what_a_registry_record_can_take_is_actually_taken(document: dict) -> None:
    """Or "loses nothing silently" would be satisfied by an exporter that carried
    nothing and reported everything as lost."""
    record, report = to_bud_agent_record(document, "refund-desk")
    assert record["id"] == "refund-desk"
    assert record["name"] == "Refund Desk"
    assert set(record["skills"]) == {"zendesk", "payments", "refund-policy"}
    assert set(report.carried) >= {"name", "description", "uses", "team"}

    # Teammates are a CAPABILITY, not a skill. Folding them into `skills` would
    # make an index think the supervisor owns what its colleagues do.
    assert record["capabilities"] == [
        "handoff:policy-checker", "handoff:fraud-checker",
    ], record["capabilities"]
    for who in ("policy-checker", "fraud-checker"):
        assert who not in record["skills"]


def test_the_export_claims_no_authority_over_where_it_runs(document: dict) -> None:
    """Six fields are left EMPTY on purpose.

    `version`, `revision`, `status`, `registryKind`, `runtimeBackend` and
    `invocation.url` are registry and deployment facts. PACT owning them would be
    the specification deciding where it runs — and it is precisely because it does
    not that one tree runs in two places.
    """
    record, report = to_bud_agent_record(document, "refund-desk")
    for empty in ("version", "revision", "status", "registryKind", "runtimeBackend"):
        assert record[empty] == "", f"{empty} was invented: {record[empty]!r}"
        assert empty in report.supplied_by_the_runtime
    assert record["invocation"]["url"] == ""
    assert "invocation.url" in report.supplied_by_the_runtime
    # Empty rather than ABSENT, so a consumer sees the field and its emptiness
    # rather than wondering whether the exporter forgot.
    assert set(_RUNTIME_SUPPLIES) <= set(report.supplied_by_the_runtime)


def test_the_report_says_a_registry_cannot_see_governance(document: dict) -> None:
    """The loss that matters most, and the reason each loss is given its own
    sentence rather than defaulting to "unsupported": an index built from these
    records cannot tell a governed agent from an ungoverned one."""
    _record, report = to_bud_agent_record(document, "refund-desk")
    for governed in ("policy", "interceptors", "teamwork", "limits"):
        assert governed in report.not_carried, report.not_carried
    assert "cannot tell a governed agent" in report.not_carried["policy"]


@pytest.mark.skipif(not BUD_TS.exists(), reason="gaia-ai-runtime is not present")
def test_the_record_matches_the_shape_the_runtime_declares() -> None:
    """Read off `bud.ts`, not guessed.

    An exporter written against an invented schema is a file that loads nowhere,
    dressed as an integration — and this repository's characteristic failure is
    exactly that kind of confident wrongness. If `BudAgentRecord` gains a field,
    this fails and somebody decides what PACT should put in it.
    """
    src = BUD_TS.read_text()
    body = src.split("export interface BudAgentRecord extends JsonObject {")[1]
    body = body.split("}")[0]
    declared = set(re.findall(r"^\s*(\w+)\s*[?]?:", body, re.M))
    assert len(declared) > 10, f"the interface did not parse: {declared}"

    doc = json.loads(subprocess.run(
        [str(PACT_BIN), "show", str(EXAMPLE)], capture_output=True, text=True, check=True
    ).stdout)
    record, _report = to_bud_agent_record(doc, "refund-desk")

    # `card` is the A2A card, which `pact card` already emits separately — this
    # exporter does not duplicate it, and that is the one declared field left out.
    missing = declared - set(record) - {"card"}
    assert not missing, (
        f"`BudAgentRecord` declares {sorted(missing)} and this export emits "
        f"neither a value nor an empty one for them"
    )
    invented = set(record) - declared - {"apiVersion", "kind"}
    assert not invented, (
        f"this export emits {sorted(invented)}, which the runtime's own "
        f"interface does not declare"
    )


def test_the_loss_measurement_is_not_decorative() -> None:
    """The mutation, in the suite rather than run by hand. If `silent_losses` can
    be empty with a field genuinely unaccounted for, every assertion above is
    worthless."""
    report = ExportReport(kind="somewhere", seen=("a", "b", "c"))
    report.carried["a"] = "there"
    report.not_carried["b"] = "a reason"
    assert report.silent_losses == ("c",)
    assert "BUG IN THIS EXPORTER" in report.in_words()
    report.not_carried["c"] = "another reason"
    assert report.silent_losses == ()


def test_a_field_nobody_planned_for_is_reported_not_dropped(document: dict) -> None:
    """The same property through the real exporter."""
    doc = json.loads(json.dumps(document))
    doc["agents"]["refund-desk"]["something-invented-later"] = {"x": 1}
    _record, report = to_bud_agent_record(doc, "refund-desk")
    assert report.silent_losses == (), report.in_words()
    assert "something-invented-later" in report.not_carried


def test_ossa_is_refused_rather_than_invented() -> None:
    """AC-6.3 names three targets and this ships two.

    No OSSA/OASF schema exists in this repository or in `gaia-ai-runtime`, so an
    exporter for it would be written against a format nobody can check. That is
    the artifact this project keeps finding: something that looks like coverage.
    """
    from pact_adapters import exporting

    assert not hasattr(exporting, "to_ossa"), (
        "an OSSA exporter appeared — if a schema is now in reach, this test "
        "should be replaced by one that holds it against that schema, the way "
        "`test_the_record_matches_the_shape_the_runtime_declares` does"
    )
    assert "OSSA is not here" in (exporting.__doc__ or ""), (
        "the refusal has to be stated where somebody looking for the exporter "
        "will read it"
    )
