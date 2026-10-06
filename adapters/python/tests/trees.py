"""A tree written for one test, read through the real loader.

A test about a spelling an author may type has to start from the file, because
the loader is what decides which spellings reach the document: a dict built in
Python proves the reader works on what the test's author chose to hand it, and
says nothing about `never-from: tool output` written without a dash.

One helper rather than a copy per file, for the reason `consenting.py` gives.
The debug build, like every other test that reads through the loader:
`scripts/test-all.sh` builds exactly that one.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
PACT_BIN = REPO / "target" / "debug" / "pact"


def write(root: Path, files: Mapping[str, str]) -> Path:
    """`files` (`relative path -> text`) under `root`, which is returned."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def pact(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the loader; the caller reads `returncode`, `stdout` and `stderr`."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    return subprocess.run([str(PACT_BIN), *args], capture_output=True, text=True)


def shown(root: Path) -> dict[str, Any]:
    """The loaded document (`pact show`), which is all an adapter may read."""
    out = pact("show", str(root))
    assert out.returncode == 0, out.stdout + out.stderr
    return json.loads(out.stdout)
