"""An agent's words, filled for one run, held to the shared cases (`tests/conformance/fill.json`).

The same file is what `crates/pact-loader/tests/fill_cases.rs` replays, and this suite replays
it through the TypeScript port too (`adapters/typescript/src/fill.ts`, which runs the
WebAssembly build of `pact_loader::fill`), so a template reads the same to a model whichever
runtime fills it.

Skips, stated rather than hidden: no `node` able to strip types, or no WebAssembly build
(`cargo build -p pact-fill-wasm --target wasm32-unknown-unknown --release`, which
`scripts/test-all.sh` runs).

    PACT_BLESS=1 pytest tests/test_words_are_filled_as_the_shared_cases_say.py

writes `expect` afresh from this port; read the diff before committing it, because that diff
is the list of things every other port now has to match.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import holes  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
CASES = REPO / "tests" / "conformance" / "fill.json"
WASM = REPO / "target" / "wasm32-unknown-unknown" / "release" / "pact_fill_wasm.wasm"


def _filled(case: dict[str, Any]) -> dict[str, str]:
    try:
        said = holes.fill(
            case["text"],
            run_inputs=case["run-inputs"],
            remembers=case["remembers"],
            language=case["language"],
        )
    except holes.Unfilled:
        return {"refused": "unfilled"}
    except ValueError:
        return {"refused": "not-rendered"}
    return {"said": said}


if os.environ.get("PACT_BLESS"):
    _held = json.loads(CASES.read_text(encoding="utf-8"))
    for _case in _held["cases"]:
        _case["expect"] = _filled(_case)
    CASES.write_text(json.dumps(_held, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

_ALL = json.loads(CASES.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _ALL, ids=[c["name"] for c in _ALL])
def test_a_case_is_what_this_port_fills(case: dict[str, Any]) -> None:
    assert "expect" in case, f"{case['name']} has no `expect` — run with PACT_BLESS=1 and read what it writes"
    assert _filled(case) == case["expect"]


def test_every_case_has_a_name_of_its_own_and_both_languages_are_held() -> None:
    names = [c["name"] for c in _ALL]
    assert len(names) == len(set(names))
    assert {c["language"] for c in _ALL} == {"holes", "jinja"}


def test_the_typescript_port_fills_every_case_as_this_one_does() -> None:
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH, so the TypeScript port cannot run")
    if not WASM.exists():
        pytest.skip(f"{WASM} is missing; fix: cargo build -p pact-fill-wasm --target wasm32-unknown-unknown --release")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", str(REPO / "adapters" / "typescript" / "read-fill.mts"), str(WASM)],
        input=CASES.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == [c["expect"] for c in _ALL]
