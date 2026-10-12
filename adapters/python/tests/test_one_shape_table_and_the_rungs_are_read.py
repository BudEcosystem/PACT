"""One table of answer shapes, and the lines a decide by models and people adds (02W §2.5, §2.10,
§2.12, SL §4.7).

The JSON Schema fragment each shape means was a second, hand-kept table in
`pydantic_ai_interop.py` (`_SHAPE_SCHEMAS`) beside the one `questions.Shape` reads, so the two
could come to disagree the first time a shape was added. It is now a column of the one table
(`questions._KINDS`) and read through `Shape.json_schema`. The new lines of a rung, a catalogue row
and a `limits:` group are each read as written, and a ceiling counted across more than one run is
said on `RunResult.unmetered`, never held as if it were one run's.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import pydantic_ai_interop  # noqa: E402
from pact_adapters.conditions import Rung  # noqa: E402
from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.limits import Limits  # noqa: E402
from pact_adapters.moments import RegionLimits  # noqa: E402
from pact_adapters.pydantic_ai_interop import shape_as_json_schema, shape_from_json_schema  # noqa: E402
from pact_adapters.questions import _KINDS, Shape  # noqa: E402
from pact_adapters.resolve import load_catalogue  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def test_the_hand_kept_shape_table_is_gone() -> None:
    assert not hasattr(pydantic_ai_interop, "_SHAPE_SCHEMAS"), "a second copy of the shape table"


@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_every_shape_is_shown_to_a_model_from_its_row_of_the_one_table(kind: str) -> None:
    schema = shape_as_json_schema(Shape.parse(kind))
    assert schema == dict(_KINDS[kind].json_schema)
    schema["type"] = "changed"
    assert _KINDS[kind].json_schema["type"] != "changed", "the table is handed out as a copy"


def test_the_shapes_a_schema_can_say_come_back_as_themselves() -> None:
    for kind in ("text", "yes-or-no", "number", "whole-number"):
        assert shape_from_json_schema(shape_as_json_schema(Shape.parse(kind))) == Shape.parse(kind)
    assert shape_as_json_schema(Shape.parse("one of invoice, other, not-sure")) == {
        "type": "string",
        "enum": ["invoice", "other", "not-sure"],
    }


def test_a_rung_reads_its_agent_its_score_its_disagreement_and_its_person() -> None:
    rung = Rung.from_written({"agent": "attachment-sorter", "if-unsure-below": "85%", "if-it-disagrees": "go-on"})
    assert (rung.agent, rung.if_unsure_below, rung.if_it_disagrees, rung.rules) == (
        "attachment-sorter",
        0.85,
        "go-on",
        (),
    )
    assert rung.goes_on_if_it_disagrees
    person = Rung.from_written({"asks": "what-is-this-attachment"})
    assert not person.goes_on_if_it_disagrees
    assert (person.asks, person.agent, person.if_unsure_below, person.if_it_disagrees) == (
        "what-is-this-attachment",
        "",
        None,
        "keep-its-answer",
    )


def test_the_worked_sorter_is_read_from_its_tree() -> None:
    flow = yaml.safe_load((REPO / "tests/trees/workflows-48-invoices/workflows/ap-inbox.yaml").read_text())
    by = flow["steps"]["each-attachment"]["steps"]["sort"]["by"]
    assert [Rung.from_written(r).agent or Rung.from_written(r).asks for r in by] == [
        "attachment-sorter",
        "what-is-this-attachment",
    ]


def test_a_catalogue_row_says_whether_it_is_a_decision_model() -> None:
    catalogue = load_catalogue(workspace=REPO / "tests/trees/workflows-48-invoices")
    assert catalogue.get("ap-attachment-classifier").kind == "decision"
    assert catalogue.get(catalogue.default).kind == "language"


def test_a_ceiling_counted_across_runs_is_read_and_said() -> None:
    written = {"tokens-at-most": 1000, "when-it-runs-out": "stop-and-say-so", "counted-per": "team",
               "resets-every": "1 day"}
    limits = Limits.from_mapping(written)
    assert (limits.counted_per, limits.resets_every, limits.across_runs) == ("team", 86400.0, ("counted-per",))
    assert Limits.from_mapping({"counted-per": "run"}).across_runs == ()
    region = RegionLimits.from_limits({"counted-per": "input.customer-id", "resets-every": "30 days"})
    assert (region.counted_per, region.resets_every) == ("input.customer-id", 30 * 86400.0)


@pytest.mark.parametrize(("per", "said"), [("team", True), ("run", False)])
def test_a_run_says_it_cannot_keep_a_ceiling_counted_across_runs(per: str, said: bool) -> None:
    # The harness meters one run: a ceiling counted per team is said on `unmetered`, not kept as if
    # this run were all of it. One counted per run is this run's to keep.
    limits = Limits.from_mapping({"tokens-at-most": 1000, "when-it-runs-out": "stop-and-say-so", "counted-per": per})
    spec = replace(AgentSpec(name="Desk", description="Answers", instructions="Answer."), limits=limits)
    result = asyncio.run(run(spec, ReferenceTransport(Script([Turn("done")])), "hello", {}))
    assert ("counted-per" in result.unmetered) is said, result.unmetered
