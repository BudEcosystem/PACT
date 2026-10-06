"""Every command finds the `pact` binary the same way (`loader.pact_binary`).

The order is PACT_BIN, then `pact` on the PATH, then the checkout's own build:
whichever of release and debug was built last. Each step is tested by making it
the first one that can answer.
"""

from __future__ import annotations

import ast
import os
import stat
import sys
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADAPTER / "src"))

from pact_adapters.loader import pact_binary  # noqa: E402

SRC = ADAPTER / "src" / "pact_adapters"


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_pact_bin_wins_over_everything(tmp_path: Path) -> None:
    named = _exe(tmp_path / "custom" / "pact-loader")
    _exe(tmp_path / "bin" / "pact")
    _exe(tmp_path / "repo" / "target" / "release" / "pact")
    env = {"PACT_BIN": str(named), "PATH": str(tmp_path / "bin")}
    assert pact_binary(environ=env, repo=tmp_path / "repo") == named


def test_a_pact_bin_naming_nothing_is_not_replaced_by_another_build(tmp_path: Path) -> None:
    _exe(tmp_path / "bin" / "pact")
    env = {"PACT_BIN": str(tmp_path / "missing"), "PATH": str(tmp_path / "bin")}
    assert pact_binary(environ=env, repo=tmp_path) is None


def test_the_path_comes_before_the_checkout(tmp_path: Path) -> None:
    on_path = _exe(tmp_path / "bin" / "pact")
    _exe(tmp_path / "repo" / "target" / "release" / "pact")
    env = {"PATH": str(tmp_path / "bin")}
    assert pact_binary(environ=env, repo=tmp_path / "repo") == on_path


def test_the_build_made_last_answers_whichever_kind_it_is(tmp_path: Path) -> None:
    """Release used to win outright, and the gate builds and tests debug: after a
    change to the loader, a stale release binary went on answering."""
    release = _exe(tmp_path / "target" / "release" / "pact")
    debug = _exe(tmp_path / "target" / "debug" / "pact")
    nowhere = {"PATH": str(tmp_path / "empty")}
    os.utime(release, ns=(1_000, 1_000))
    os.utime(debug, ns=(2_000, 2_000))
    assert pact_binary(environ=nowhere, repo=tmp_path) == debug
    os.utime(release, ns=(3_000, 3_000))
    assert pact_binary(environ=nowhere, repo=tmp_path) == release
    os.utime(debug, ns=(3_000, 3_000))
    assert pact_binary(environ=nowhere, repo=tmp_path) == release, "the same age: the one built to use"


def test_debug_is_the_last_resort(tmp_path: Path) -> None:
    debug = _exe(tmp_path / "target" / "debug" / "pact")
    assert pact_binary(environ={"PATH": str(tmp_path / "empty")}, repo=tmp_path) == debug


def test_nothing_found_is_none(tmp_path: Path) -> None:
    assert pact_binary(environ={"PATH": str(tmp_path)}, repo=tmp_path) is None


def test_no_module_builds_its_own_path_to_the_loader() -> None:
    """A second copy of the search is how the debug-only lookup came to exist."""
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "loader.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            built = ("target/debug/pact", "target/release/pact")
            if isinstance(node, ast.Constant) and node.value in built:
                offenders.append(path.name)
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", "") == "which"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "pact"
            ):
                offenders.append(path.name)
        text = path.read_text()
        if '"target" / "debug" / "pact"' in text or '"target" / "release" / "pact"' in text:
            offenders.append(path.name)
    assert not offenders, f"build the loader path through loader.pact_binary: {offenders}"


def test_no_module_imports_a_private_name_from_pydantic_ai() -> None:
    """A name with an underscore is one the SDK may move in any release, and a
    host that forbids private upstream imports cannot import a module that has
    one. Two were here: `pydantic_ai._utils.run_until_complete` at the top of
    `pact_agent.py`, and `pydantic_ai.agent._AUTO_INJECT_CAPABILITY_TYPES` in a
    function of `pydantic_ai_interop.py`, a module every host imports."""
    upstream = ("pydantic_ai", "pydantic_graph")

    def private(dotted: str) -> bool:
        return dotted.split(".")[0] in upstream and any(part.startswith("_") for part in dotted.split("."))

    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            named: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                named = [f"{node.module}.{alias.name}" for alias in node.names]
            elif isinstance(node, ast.Import):
                named = [alias.name for alias in node.names]
            elif isinstance(node, ast.Attribute):
                named = [ast.unparse(node)]
            offenders += [f"{path.relative_to(SRC)}:{node.lineno}: {n}" for n in named if private(n)]
    assert not offenders, "private Pydantic AI names are imported:\n  " + "\n  ".join(offenders)

