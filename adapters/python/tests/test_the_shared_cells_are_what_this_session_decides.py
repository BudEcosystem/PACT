"""The shared cells (`tests/conformance/cells.json`), held to PACT's own session.

A cell is a piece of PACT Core handed to a running session. What the session's
door says to it — admitted, or refused and by which door — is something a
second runtime has to say the same way, or a cell that is safe on one is an
escape on the other. Most of these are attacks, each written to be stopped by
exactly one rule.

    PACT_BLESS=1 pytest tests/test_the_shared_cells_are_what_this_session_decides.py

writes `expect` afresh from this session; read the diff before committing it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.session import Session  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
HELD = REPO / "tests" / "conformance" / "cells.json"


def decided(session: Session, case: dict[str, Any]) -> dict[str, Any]:
    before = session.document
    got = session.cell(case["cell"], by=case["by"], takes=case["takes"], gives=case["gives"])
    rule = next(
        (line.strip()[len("rule: "):] for said in got.said for line in said.splitlines()
         if line.strip().startswith("rule: ")),
        "",
    )
    defines = sorted(
        f"{kind}/{name}" for kind in ("agents", "workflows", "shapes")
        for name in session.document.get(kind) or {} if name not in (before.get(kind) or {})
    )
    session.end(got)
    assert session.version == got.version if not got.admitted else True
    return {"admitted": got.admitted, "refused-by": got.refused_by, "rule": rule, "defines": defines}


@pytest.fixture(scope="module")
def cases() -> list[dict[str, Any]]:
    held = json.loads(HELD.read_text())
    if os.environ.get("PACT_BLESS"):
        sessions: dict[str, Session] = {}
        for case in held["cases"]:
            session = sessions.setdefault(case["tree"], Session.open(REPO / case["tree"]))
            case["expect"] = decided(session, {k: v for k, v in case.items() if k != "expect"})
        for session in sessions.values():
            session.close()
        HELD.write_text(json.dumps(held, indent=1, ensure_ascii=False) + "\n")
    return held["cases"]


def test_every_cell_is_decided_as_written_down(cases: list[dict[str, Any]]) -> None:
    session = Session.open(REPO / cases[0]["tree"])
    start = session.version
    try:
        for case in cases:
            assert "expect" in case, f"{case['name']} has no `expect:` — run with PACT_BLESS=1"
            assert decided(session, case) == case["expect"], case["name"]
            # A cell's definitions are for the call: once it has ended, the
            # workspace is the one it was, to the fingerprint.
            assert session.version == start, case["name"]
    finally:
        session.close()


def test_the_cases_say_what_they_are_there_to_say(cases: list[dict[str, Any]]) -> None:
    by_name = {c["name"]: c["expect"] for c in cases}
    assert len(by_name) == len(cases) == 21
    admitted = [n for n, e in by_name.items() if e["admitted"]]
    assert len(admitted) == 3, admitted
    # Every door refuses something, and the checker by more than one rule.
    doors = {e["refused-by"] for e in by_name.values() if not e["admitted"]}
    assert doors == {"checker", "floor", "meter", "collision", "reach", "wider"}, doors
    rules = {e["rule"] for e in by_name.values() if e["refused-by"] == "checker"}
    assert {"loader/for-each-with-no-ceiling", "loader/a-binding-to-nothing", "loader/no-such-name"} <= rules
    # The four a model is most likely to be talked into.
    assert by_name["a-payment-by-an-agent-that-was-never-given-payments-is-refused"]["refused-by"] == "reach"
    assert by_name["a-cell-cannot-define-a-tool"]["refused-by"] == "floor"
    assert by_name["a-helper-is-never-given-a-tool-its-writer-does-not-have"]["refused-by"] == "wider"
    assert by_name["a-cell-never-replaces-what-the-workspace-has"]["refused-by"] == "collision"
    # A narrower helper is what a model MAY define, and it is there while the cell lives.
    assert "agents/reader" in by_name["a-narrower-helper-is-admitted-and-may-be-called"]["defines"]
    # Nothing a guard refused had been defined.
    assert all(not e["defines"] for e in by_name.values() if not e["admitted"])
