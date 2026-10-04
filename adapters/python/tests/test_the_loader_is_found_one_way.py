"""Every command finds the `pact` binary the same way (`loader.pact_binary`).

The order is PACT_BIN, then `pact` on the PATH, then the checkout's release
build, then its debug build. Each step is tested by making it the first one
that can answer.
"""

from __future__ import annotations

import ast
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


def test_release_comes_before_debug(tmp_path: Path) -> None:
    release = _exe(tmp_path / "target" / "release" / "pact")
    _exe(tmp_path / "target" / "debug" / "pact")
    assert pact_binary(environ={"PATH": str(tmp_path / "empty")}, repo=tmp_path) == release


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
            if isinstance(node, ast.Constant) and node.value in ("target/debug/pact", "target/release/pact"):
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
