"""A shape is built on three ways, and read the same way everywhere (02W §2.15).

`list of <shape>`, a name from the workspace's `shapes:`, and `<shape>,
optional` — read by `Shape.parse`, the one Python reader, exactly as
`crates/pact-schema/src/shape.rs` reads them for `pact check`. And three new
shapes: `date`, `time` and `date-and-time`, whose values are read to ISO 8601;
a date and time written without a zone is read in the workspace's
`time-zone:`, and refused when there is none.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.pydantic_ai_interop import _answers_with_schema, shape_as_json_schema  # noqa: E402
from pact_adapters.questions import Rejected, Shape  # noqa: E402

SHAPES = {
    "invoice-line": {"sku": "text", "quantity": "whole number", "note": "text, optional"},
    "invoice": {"number": "text", "lines": "list of invoice-line", "due": "date"},
}


@pytest.mark.parametrize(
    ("written", "kind"),
    [("date", "date"), ("a date", "date"), ("time", "time"), ("a time of day", "time"),
     ("date and time", "date-and-time"), ("a date and time", "date-and-time"),
     ("date-and-time", "date-and-time")],
)
def test_each_new_spelling_reads_as_its_shape(written: str, kind: str) -> None:
    assert Shape.parse(written).kind == kind


def test_a_date_and_a_time_of_day_are_read_to_iso_8601() -> None:
    assert Shape.parse("date").read("2026-10-09") == "2026-10-09"
    assert Shape.parse("time").read("09:05") == "09:05:00"
    with pytest.raises(Rejected, match="a date, like `2026-10-09`"):
        Shape.parse("date").read("next tuesday")


def test_a_date_and_time_without_a_zone_is_read_in_the_workspace_zone() -> None:
    chicago = Shape.parse("date and time", zone="America/Chicago")
    # Across the clock change of 8 March 2026: noon is after it, in daylight time.
    assert chicago.read("2026-03-08T12:00") == "2026-03-08T12:00:00-05:00"
    assert chicago.read("2026-03-07T12:00") == "2026-03-07T12:00:00-06:00"
    # A value that carries its zone keeps it.
    assert chicago.read("2026-03-08T12:00:00Z") == "2026-03-08T12:00:00+00:00"


def test_a_date_and_time_with_no_zone_anywhere_is_refused_with_what_to_write() -> None:
    with pytest.raises(Rejected, match="add `time-zone:` to workspace.yaml"):
        Shape.parse("date and time").read("2026-10-09T10:00")


def test_a_list_reads_each_item_in_its_shape() -> None:
    numbers = Shape.parse("list of whole number")
    assert (numbers.kind, numbers.of) == ("list", Shape("whole-number"))
    assert numbers.read(["1", 2]) == [1, 2]
    assert numbers.read("[3, 4]") == [3, 4]
    with pytest.raises(Rejected, match="item 2"):
        numbers.read([1, "two"])
    # A spelling the vocabulary already holds wins: `list of images` is `images`.
    assert Shape.parse("list of images").kind == "images"


def test_a_named_shape_reads_its_parts_and_an_optional_part_may_be_left_out() -> None:
    line = Shape.parse("invoice-line", SHAPES)
    assert line.kind == "named" and line.name == "invoice-line"
    assert line.read({"sku": "A1", "quantity": "3"}) == {"sku": "A1", "quantity": 3}
    with pytest.raises(Rejected, match="leaves out 'quantity'"):
        line.read({"sku": "A1"})
    with pytest.raises(Rejected, match="no part by that name"):
        line.read({"sku": "A1", "quantity": 1, "colour": "red"})
    invoice = Shape.parse("list of invoice", SHAPES)
    read = invoice.read([{"number": "7", "lines": [{"sku": "B", "quantity": 1}], "due": "2026-11-01"}])
    assert read == [{"number": "7", "lines": [{"sku": "B", "quantity": 1}], "due": "2026-11-01"}]


def test_a_named_shape_with_no_workspace_is_no_shape() -> None:
    with pytest.raises(Rejected, match="named under `shapes:` in workspace.yaml"):
        Shape.parse("invoice-line")


def test_a_shape_made_of_itself_is_refused() -> None:
    with pytest.raises(Rejected, match="made of itself"):
        Shape.parse("a", {"a": {"b": "list of b"}, "b": {"a": "a, optional"}})


def test_an_optional_line_reads_nothing_as_none_and_writes_itself_back() -> None:
    optional = Shape.parse("Whole Number ,  optional")
    assert optional.optional and optional.kind == "whole-number"
    assert optional.read(None) is None and optional.read("") is None and optional.read("4") == 4
    for written in ("text, optional", "list of invoice-line", "invoice, optional", "one of a, b"):
        assert Shape.parse(Shape.parse(written, SHAPES).written(), SHAPES) == Shape.parse(written, SHAPES)


def test_every_example_a_person_is_told_to_type_reads_back() -> None:
    for written in ("list of invoice", "invoice-line", "date and time", "time"):
        shape = Shape.parse(written, SHAPES, zone="UTC")
        assert shape.read(shape.example()) is not None, written


def test_the_model_is_shown_each_shape_as_the_json_schema_that_means_it() -> None:
    assert shape_as_json_schema(Shape.parse("date and time")) == {"type": "string", "format": "date-time"}
    assert shape_as_json_schema(Shape.parse("list of number")) == {"type": "array", "items": {"type": "number"}}
    line = shape_as_json_schema(Shape.parse("invoice-line", SHAPES))
    assert line["required"] == ["quantity", "sku"] and "note" in line["properties"]
    answer = _answers_with_schema({"lines": "list of invoice-line", "comment": "text, optional"}, SHAPES)
    assert answer is not None and answer["required"] == ["lines"]


def test_an_agent_spec_carries_the_workspaces_shapes_and_zone() -> None:
    doc = {
        "shapes": SHAPES,
        "time-zone": "America/Chicago",
        "agents": {"a": {"description": "d", "instructions": "i", "answers-with": {"lines": "list of invoice-line"}}},
    }
    spec = AgentSpec.from_document(doc, "a")
    assert spec.shapes["invoice-line"]["quantity"] == "whole number"
    assert spec.time_zone == "America/Chicago"


def test_a_question_in_a_named_shape_is_asked_the_same_in_another_process() -> None:
    """A parked run outlives its process (D23), so the parts of a named shape and
    the zone travel with the question and with the suspension."""
    from pact_adapters.questions import Question
    from pact_adapters.suspension import Expect, Suspension

    doc = {
        "shapes": SHAPES,
        "time-zone": "America/Chicago",
        "questions": {
            "which-lines": {
                "description": "d",
                "says": "Which lines?",
                "answer": {"lines": "list of invoice-line", "by": "date and time"},
                "asked-of": ["the-requester"],
                "answer-within": "1 day",
            }
        },
    }
    asked = Question.from_document(doc, "which-lines")
    again = Question.from_json(asked.to_json())
    assert again.answer == asked.answer
    assert again.answer["by"].read("2026-10-09T09:00") == "2026-10-09T09:00:00-05:00"
    parked = Suspension(reason="needs-approval", asks=tuple(Expect(k, v) for k, v in asked.answer.items()))
    assert Suspension.from_json(parked.to_json()).asks == parked.asks


def test_a_question_line_marked_optional_may_be_left_out_of_the_answer() -> None:
    from pact_adapters.questions import Question

    asked = Question(
        name="q",
        asks="Which lines?",
        answer={"approved": Shape.parse("yes or no"),
                "lines": Shape.parse("list of invoice-line, optional", SHAPES)},
    )
    assert asked.validate({"approved": "yes"}).values == {"approved": True}
    with pytest.raises(Rejected, match="'approved' is missing"):
        asked.validate({"lines": []})
