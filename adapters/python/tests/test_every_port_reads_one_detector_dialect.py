"""One detector dialect, read alike by the checker, Python and TypeScript.

A workspace's `detectors:` write the patterns a thing looks like, and a hiding
rule replaces every value one of them finds. A pattern that Python's `re` and
another runtime's engine read differently hides a value on one runtime and
lets it through on another, so `pact check` holds every `looks-like:` line to
the detector dialect (spec/schema.yaml, `detectors`) and refuses the rest with
`loader/looks-like-outside-the-dialect`.

`tests/conformance/detectors.json` holds the cases. This suite holds the
reference to them (each pattern in the dialect, compiled by
`detectors.declared_in`, finds exactly the listed matches), the TypeScript
port (`adapters/typescript/src/detectors.ts`, through `read-detectors.mts`:
the same refusals with the same reasons, the same matches), and the checker
(a tree whose detector writes a pattern outside the dialect is refused). The
Rust reader's refusals are held to the same cases by
`crates/pact-loader/tests/detector_dialect_cases.rs`.

Skips, stated rather than hidden: no `node` able to strip types, and no built
`pact` binary.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pact_adapters.detectors import declared_in

REPO = Path(__file__).resolve().parents[3]
HELD = json.loads((REPO / "tests" / "conformance" / "detectors.json").read_text(encoding="utf-8"))
PACT = REPO / "target" / "debug" / "pact"


def _expected(case: dict) -> dict:
    if case["outside"]:
        return {"outside": True, "reason": case["reason"]}
    return {"outside": False, "finds": case["finds"]}


def test_the_reference_finds_what_every_case_in_the_dialect_lists() -> None:
    wrong = []
    for case in HELD["cases"]:
        if case["outside"]:
            continue
        pattern = declared_in({"detectors": {"thing": {"looks-like": [case["looks-like"]]}}})["thing"]
        finds = []
        for index, text in enumerate(HELD["texts"]):
            found = [match.group(0) for match in re.finditer(pattern, text)]
            if found:
                finds.append({"in": index, "found": found})
        if finds != case["finds"]:
            wrong.append(case["looks-like"])
    assert not wrong, wrong


def test_no_case_in_the_dialect_can_match_an_empty_value() -> None:
    # The dialect leaves out patterns that can match nothing: Python's re and
    # JavaScript step past an empty match differently, so their matches differ.
    for case in HELD["cases"]:
        if not case["outside"]:
            assert all("" not in find["found"] for find in case["finds"]), case["looks-like"]


def test_the_typescript_port_reads_every_case_as_held() -> None:
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH, so the TypeScript port cannot run")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", str(REPO / "adapters" / "typescript" / "read-detectors.mts")],
        input=json.dumps({"texts": HELD["texts"], "cases": HELD["cases"]}),
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    port = json.loads(run.stdout)
    wrong = [
        case["looks-like"] for case, answer in zip(HELD["cases"], port, strict=True) if answer != _expected(case)
    ]
    assert not wrong, wrong


def test_the_checker_refuses_a_tree_whose_detector_is_outside_the_dialect(tmp_path: Path) -> None:
    if not PACT.exists():
        pytest.skip("no built pact binary at target/debug/pact")
    case = next(c for c in HELD["cases"] if c["outside"] and c["looks-like"] == "(?<=x)y")
    (tmp_path / "workspace.yaml").write_text(
        "name: Desk\n"
        "detectors:\n"
        "  order reference:\n"
        "    description: An order reference.\n"
        f"    looks-like:\n      - {json.dumps(case['looks-like'])}\n"
        "    examples:\n      - xy\n",
        encoding="utf-8",
    )
    agent = tmp_path / "agents" / "desk"
    agent.mkdir(parents=True)
    (agent / "agent.yaml").write_text("description: Answers.\ninstructions: Answer.\n", encoding="utf-8")
    run = subprocess.run([str(PACT), "check", str(tmp_path)], capture_output=True, text=True)
    said = run.stdout + run.stderr
    assert run.returncode != 0, said
    assert "loader/looks-like-outside-the-dialect" in said, said
    assert case["reason"] in said, said
