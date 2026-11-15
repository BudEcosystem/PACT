"""A value has one text and one fingerprint, whichever runtime computes them.

`in-share: 5%` sends the same five customers in a hundred down the new path in
every runtime only if every runtime reads the same text out of a value and
takes the same fingerprint of it. A person's yes stays bound to the calls they
saw only if the digest the runtime stored is the one it recomputes. And
`tool-snapshot-digest:` pins a server only if the pin is computed the same way
in the runtime that checks it as in the tool that wrote it. All four were
defined by what this port happened to do — three different JSON spellings in
three files — and a second runtime could only match them by reading the code.

`spec/fingerprints.yaml` writes them down, with the rows they are held to. Each
row's value is JSON text, so it means the same thing in every language; this
file checks that the reference gives every row's answer through the functions a
run actually goes through. A second port reads the same file.

Mutation: write `in-share`'s fingerprint over the value's `repr` instead of
`_text`, or drop `sort_keys=True` from `request_digest`. The in-share rows, or
the request-digest rows whose argument keys are not written in sorted order, go
red here.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import conditions, detectors, mcp_bridge, suspension  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TABLE = yaml.safe_load((REPO / "spec" / "fingerprints.yaml").read_text())


def _id(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False)[:60]


def test_the_table_still_holds_the_rows_it_was_written_with() -> None:
    """A pin that can be emptied is not a pin."""
    counts = {part: len(TABLE[part]) for part in ("text", "in-share", "request-digest", "snapshot-digest", "looks-like")}
    counts["declared"] = len(TABLE["declared"]["rows"])
    floors = {"text": 18, "in-share": 9, "request-digest": 9, "snapshot-digest": 5, "looks-like": 11, "declared": 9}
    shrunk = {part: (counts[part], floor) for part, floor in floors.items() if counts[part] < floor}
    assert not shrunk, f"spec/fingerprints.yaml lost rows (now, written with): {shrunk}"


@pytest.mark.parametrize("row", TABLE["text"], ids=_id)
def test_a_value_reads_as_one_text(row: dict) -> None:
    assert conditions._text(json.loads(row["value"])) == row["text"]


@pytest.mark.parametrize("row", TABLE["in-share"], ids=_id)
def test_a_value_falls_in_one_share(row: dict) -> None:
    value = json.loads(row["value"])
    fingerprint = hashlib.sha256(conditions._text(value).encode()).hexdigest()[:15]
    assert fingerprint == row["fingerprint"]
    assert conditions.holds({"in-share": row["in-share"]}, value) is row["holds"]


def test_an_absent_value_is_in_no_share() -> None:
    assert conditions.holds({"in-share": "100%"}, None) is False
    assert conditions.holds({"in-share": "100%"}) is False


@pytest.mark.parametrize("row", TABLE["request-digest"], ids=_id)
def test_a_request_has_one_digest(row: dict) -> None:
    calls = [SimpleNamespace(name=name, args=args) for name, args in json.loads(row["calls"])]
    assert suspension.request_digest(calls) == row["digest"]


@pytest.mark.parametrize("row", TABLE["snapshot-digest"], ids=_id)
def test_a_server_has_one_snapshot_digest(row: dict) -> None:
    assert mcp_bridge.digest_of(json.loads(row["published"]), row["instructions"]) == row["digest"]


@pytest.mark.parametrize("row", TABLE["looks-like"], ids=_id)
def test_a_built_in_detector_recognises_one_set_of_values(row: dict) -> None:
    assert conditions.holds({"looks-like": row["looks-like"]}, json.loads(row["value"])) is row["holds"]


@pytest.mark.parametrize("row", TABLE["declared"]["rows"], ids=_id)
def test_a_declared_detector_reads_its_patterns_one_way(row: dict) -> None:
    written = {name: {"looks-like": patterns} for name, patterns in TABLE["declared"]["detectors"].items()}
    token = detectors.DECLARED.set(detectors.declared_in({"detectors": written}))
    try:
        assert conditions.holds({"looks-like": row["looks-like"]}, json.loads(row["value"])) is row["holds"]
    finally:
        detectors.DECLARED.reset(token)


def test_the_rows_a_one_number_type_port_cannot_reproduce_are_marked() -> None:
    """`number-as-written` is on every row whose answer turns on how a number was written, and on no other.

    The reference keeps `1.0` apart from `1`, writes `1e20` as `1e+20`, and keeps
    integers past 2^53 exact; a port whose numbers are one type does none of the
    three. A row whose answer depends on them and is not marked would read, to
    that port, as a defect in its own code."""

    def turns_on_a_number(value: object) -> bool:
        if isinstance(value, bool) or value is None or isinstance(value, str):
            return False
        if isinstance(value, float):
            return value.is_integer() or abs(value) >= 1e16
        if isinstance(value, int):
            return abs(value) > 2**53
        if isinstance(value, dict):
            return any(turns_on_a_number(v) for v in value.values())
        if isinstance(value, list):
            return any(turns_on_a_number(v) for v in value)
        return False

    for part, key in (("text", "value"), ("request-digest", "calls")):
        for row in TABLE[part]:
            marked = row.get("number-as-written") is True
            assert marked == turns_on_a_number(json.loads(row[key])), (part, row[key])
