"""Every operation of the kernel is something a person can write (`docs/100` §9.2).

The seven primitives have 76 operations (`spec/kernel.yaml`). A Rust test
already holds each to a field of the schema or to a place in the syntax
(`every_kernel_operation_is_written_somewhere.rs`). That is a claim about the
specification. This is the claim about what an author can actually do: for
every operation there is a workspace, shipped in this repository and loading
under `pact check`, in which it is written.

Measured the first time this ran (16 November 2026): 72 of 76. Four were
written in no shipped tree at all: `shape.validate`, `shape.parse`
(`answers-with-mode:`), `allowance.period` (`counted-per:`, `resets-every:`)
and `allowance.value` (`cost-per-request-from:`). `examples/core/refund-desk`
now writes them, so an operation that loses its last written example fails
here.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.loader import pact_binary  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: An operation an author writes as syntax inside a value rather than as a
#: field of its own (`written-in:` in the kernel), and how it is recognised.
IN_A_VALUE = {
    "shape.one-of": r"\bone of \w",
    "shape.record": r"\blist of \w",
    "shape.stream": r"\bstream of \w",
    "shape.reference": r"\bagent\b",
    "store.read": r"\b(input|steps|remembers)\.\w",
    "shape.render": r"\{\{",
}


def _fields_by_operation() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict) and "kernel-op" in value:
                    ops = value["kernel-op"]
                    for op in [ops] if isinstance(ops, str) else ops:
                        out.setdefault(op, set()).add(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(yaml.safe_load((REPO / "spec/schema.yaml").read_text()))
    return out


def _written() -> tuple[set[str], str, int]:
    """Every setting name, and every text value, of every shipped tree that loads."""
    binary = pact_binary()
    if binary is None:
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    globs = ("examples/**/workspace.yaml", "examples/**/*.pact",
             "tests/conformance/trees/*/*.pact", "tests/trees/*/workspace.yaml")
    roots = sorted({p.parent for g in globs for p in REPO.glob(g)})
    keys: set[str] = set()
    texts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                keys.add(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            texts.append(node)

    loaded = 0
    for root in roots:
        shown = subprocess.run([str(binary), "show", str(root)], capture_output=True, text=True)
        if shown.returncode == 0:
            walk(json.loads(shown.stdout))
            loaded += 1
    return keys, "\n".join(texts), loaded


def test_every_operation_is_written_in_a_shipped_tree_that_loads() -> None:
    kernel = yaml.safe_load((REPO / "spec/kernel.yaml").read_text())["ops"]
    fields = _fields_by_operation()
    keys, texts, loaded = _written()
    assert len(kernel) == 76 and loaded >= 60, (len(kernel), loaded)
    unwritten = [
        op for op in kernel
        if not (fields.get(op, set()) & keys)
        and not (op in IN_A_VALUE and re.search(IN_A_VALUE[op], texts, re.M))
    ]
    assert not unwritten, (
        f"{len(kernel) - len(unwritten)} of {len(kernel)} operations are written in a shipped "
        f"tree that loads. Not written anywhere: "
        + "; ".join(f"{op} ({', '.join(sorted(fields.get(op, ()))) or kernel[op].get('written-in', '?')})"
                    for op in unwritten)
        + ". Write each in a workspace under `examples/` — `examples/core/refund-desk` is the "
          "one that exists to hold what nothing else writes."
    )


def test_the_four_that_nothing_wrote_are_written_in_the_core_example() -> None:
    binary = pact_binary()
    if binary is None:
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    shown = subprocess.run([str(binary), "show", str(REPO / "examples/core/refund-desk")],
                           capture_output=True, text=True, check=True)
    cashier = json.loads(shown.stdout)["agents"]["cashier"]
    assert cashier["answers-with-mode"] == "prompted"
    assert cashier["limits"]["cost-per-request-from"] == "run-inputs.budget"
    assert cashier["limits"]["counted-per"] == "run" and cashier["limits"]["resets-every"] == "1 day"
