"""A host that runs carried programs is handed everything it needs, from one reader (P6/P7).

`ProgramSpec` used to carry names and an engine and nothing a runner could act
on: what a program takes, what it answers with, what it may spend and where its
body is were in the document and nowhere on this side of the boundary, so a host
had to walk `programs:` itself — a second reading of a grammar (`10m`, `2s`) that
drifts the first time somebody is not looking.

The conformance case (`tests/conformance/programs.json`) is the shared half: a
tree with a real `python` body and a real `wasm` body, and the answers any host
running them must give. A host's own suite runs the cases; this one holds them
to the shapes the tree declares, so the two cannot disagree about what a right
answer is.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.interceptors import Chain  # noqa: E402
from pact_adapters.ir import AgentSpec, ProgramSpec  # noqa: E402
from pact_adapters.loader import pact_binary  # noqa: E402
from pact_adapters.programs import ProgramFuel, body_entry, size  # noqa: E402
from pact_adapters.questions import NEEDS_PERMISSION, Shape, questions_for  # noqa: E402
from pact_adapters.suspension import PauseRule, rule_for  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TREE = REPO / "tests" / "trees" / "a-desk-whose-programs-run"
CASES = REPO / "tests" / "conformance" / "programs.json"


def _load(root: Path) -> dict[str, Any]:
    binary = pact_binary()
    if binary is None:
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    out = subprocess.run([str(binary), "show", str(root)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return _load(TREE)


def test_a_program_carries_its_shapes_its_fuel_and_where_its_body_is(document: dict[str, Any]) -> None:
    spec = ProgramSpec.from_document(document, "check-window")
    assert spec.engine == "python" and spec.determinism == "pure"
    assert spec.takes == {"purchased-on": "text", "today": "text"}
    assert spec.answers_with == {"verdict": "one of inside, outside", "days": "integer"}
    assert spec.fuel == ProgramFuel(runs_for_at_most=2.0, memory_at_most=64_000_000,
                                    when_it_runs_out="stop-and-say-so")
    assert spec.body == "programs/check-window/body"
    assert spec.entry == body_entry(spec.body_files, spec.engine) == "check_window.py"
    wasm = ProgramSpec.from_document(document, "repeat")
    assert wasm.fuel.instructions_at_most == 10_000_000
    assert body_entry(wasm.body_files, "wasm") == "repeat.wasm"


def test_the_agents_own_programs_are_read_by_the_same_reader(document: dict[str, Any]) -> None:
    spec = AgentSpec.from_document(document, "desk", TREE)
    reached = {p.name: p for p in spec.programs}
    assert reached["check-window"] == ProgramSpec.from_document(
        document, "check-window", reached_by=("refund-window/check",)
    )
    (tool,) = spec.tools
    assert tool.programs == {"check": "check-window", "repeat": "repeat"}
    room = tool.reaches.resource if tool.reaches else None
    assert room is not None and room.engines == ("python", "wasm") and room.asks_to_run == "may-we-run"


def test_a_name_the_workspace_does_not_carry_is_refused(document: dict[str, Any]) -> None:
    with pytest.raises(KeyError, match="no program named 'nope'"):
        ProgramSpec.from_document(document, "nope")


def test_a_size_is_read_the_way_the_schema_spells_it() -> None:
    assert size("10m") == 10_000_000 and size("32k") == 32_000 and size("200000") == 200_000
    assert size("0") is None and size("ten") is None and size(None) is None
    assert ProgramFuel.from_document({"runs-for-at-most": "500ms"}).written() == {"runs-for-at-most": 0.5}


def test_a_locked_room_asks_before_its_first_run_and_the_wait_is_the_rooms(document: dict[str, Any]) -> None:
    gate = questions_for(document, "desk", TREE)
    (wait,) = gate.waits_for("refund-window", {"action": "check", "purchased-on": "x", "today": "y"})
    assert (wait.reason, wait.asked_as) == (NEEDS_PERMISSION, "local-room")
    rule = rule_for(PauseRule.from_document(document, "desk"), NEEDS_PERMISSION)
    assert rule is not None and rule.answer_within == "30m"


def test_a_gate_says_which_tools_any_call_could_stop(document: dict[str, Any]) -> None:
    gate = questions_for(document, "desk", TREE)
    assert gate.may_stop("refund-window") and gate.may_stop("refund-window", "repeat")
    assert not gate.may_stop("something-else")


def test_a_chain_names_the_programs_its_rewriting_sentences_run() -> None:
    doc = {
        "programs": {"house-style": {"engine": "wasm"}},
        "interceptors": {
            "in-house-style": {
                "when": "turn.message.after",
                "may": ["change-the-answer"],
                "rules": ["replace the answer with what house-style returns"],
            }
        },
        "agents": {"desk": {"interceptors": ["in-house-style"]}},
    }
    assert Chain.from_document(doc, "desk").programs == ("house-style",)


def test_every_conformance_case_fits_the_shapes_its_program_declares(document: dict[str, Any]) -> None:
    cases = json.loads(CASES.read_text())
    assert (REPO / cases["tree"]) == TREE
    engines = set()
    for case in cases["cases"]:
        spec = ProgramSpec.from_document(document, case["program"])
        engines.add(spec.engine)
        assert set(case["inputs"]) == set(spec.takes)
        assert set(case["answer"]) == set(spec.answers_with)
        for name, value in case["answer"].items():
            Shape.parse(spec.answers_with[name]).read(value)
    assert engines == {"python", "wasm"}  # one case per engine a host may supply


def test_the_file_a_host_starts_is_never_a_guess() -> None:
    """The halves the two shipped bodies never reach: each has exactly one file
    of its engine's kind, so "take the first" and "always `main`" both passed."""
    assert body_entry(("a.py", "b.py"), "python") == "", "several and no `main`: naming one is a guess"
    assert body_entry(("a.py", "main.py", "b.py"), "python") == "main.py"
    assert body_entry(("util.ts", "main.ts", "main.py"), "typescript") == "main.ts"
    assert body_entry(("notes.md", "b.wasm", "a.py"), "wasm") == "b.wasm", "the engine's kind, not the first file"
    assert body_entry(("notes.md",), "python") == "", "nothing of the engine's kind"
    assert body_entry(("main.py",), "ruby") == "", "an engine with no contract starts nothing"
