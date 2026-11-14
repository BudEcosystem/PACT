"""One effect per part, computed by the checker and by the TypeScript port.

Law 1 says a part's effect is computed and never declared, and
`crates/pact-loader/src/effects.rs` is where it is computed: `pact discover`
prints each agent's `effect` and `moves-money`, the exactly-once rules read
it, and `effect:` in a `when-this` gates on it. A runtime that gates calls at
run time, or builds an agent in code with no tree to discover, needs the same
answer without the binary, so `adapters/typescript/src/effects.ts` ports it
function for function. Two readings of "what does this part do" that differ
are a payment one runtime treats as a lookup, so this suite holds the port to
the checker on every document of the corpus the checker loads: every example
and every tree under `tests/trees`, every agent `discover` lists.

Skips, stated rather than hidden: no built CLI (`cargo build -p pact-cli`), or
no `node` able to strip types.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BINARY = REPO / "target" / "debug" / "pact"
PORT = REPO / "adapters" / "typescript"


def _workspaces() -> list[Path]:
    roots = [p.parent for p in (REPO / "examples").rglob("workspace.yaml")]
    roots += [p.parent for p in (REPO / "tests" / "trees").rglob("workspace.yaml")]
    return sorted(set(roots))


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), capture_output=True, text=True)


@pytest.fixture(scope="module", autouse=True)
def _needs_both_ports() -> None:
    if not BINARY.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH, so the TypeScript port cannot run")


def _compared(root: Path, tmp_path: Path) -> list[str]:
    shown = _run(str(BINARY), "show", str(root))
    found = _run(str(BINARY), "discover", str(root))
    if shown.returncode != 0 or found.returncode != 0:
        return []
    document = tmp_path / f"{root.name}.json"
    document.write_text(shown.stdout)
    port = _run("node", "--experimental-strip-types", "--no-warnings", str(PORT / "read-effects.mts"), str(document))
    assert port.returncode == 0, port.stderr
    computed = json.loads(port.stdout)["agents"]
    inventory = json.loads(found.stdout)
    inventories = inventory if isinstance(inventory, list) else [inventory]
    differences = []
    for listed in inventories:
        for agent in listed["agents"]:
            key = agent["id"].removeprefix("pact:")
            checker = {"effect": agent["effect"], "moves-money": agent["moves-money"]}
            if computed.get(key) != checker:
                differences.append(f"{root.relative_to(REPO)} {key}: checker {checker}, port {computed.get(key)}")
    return differences


def test_the_port_computes_every_corpus_agent_as_the_checker_does(tmp_path: Path) -> None:
    compared = 0
    differences: list[str] = []
    for root in _workspaces():
        differences += _compared(root, tmp_path)
        compared += 1
    assert compared > 50
    assert differences == []


def test_a_payment_with_a_refund_still_moves_money_and_a_silent_action_cannot_be_undone(tmp_path: Path) -> None:
    document = tmp_path / "doc.json"
    document.write_text(json.dumps({
        "name": "w",
        "tools": {
            "payments": {"actions": {
                "refund": {"spends-money": "yes", "undone-by": "payments/reverse"},
                "reverse": {"spends-money": "yes"},
            }},
            "crm": {"actions": {"look-up": {"reads-only": "y"}, "note": {}}},
        },
        "agents": {
            "clerk": {"uses": ["crm/look-up"]},
            "writer": {"uses": "crm"},
            "payer": {"uses": ["payments/refund"], "team": {"clerk": "Looks things up."}},
        },
    }))
    port = _run("node", "--experimental-strip-types", "--no-warnings", str(PORT / "read-effects.mts"), str(document))
    assert port.returncode == 0, port.stderr
    assert json.loads(port.stdout)["agents"] == {
        "clerk": {"effect": "reads", "moves-money": False},
        "writer": {"effect": "cannot-be-undone", "moves-money": False},
        "payer": {"effect": "writes", "moves-money": True},
    }
